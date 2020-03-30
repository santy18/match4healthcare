from django.shortcuts import render
from django.template import loader
from django.http import HttpResponse

from apps.mapview.utils import plzs
from apps.iamstudent.models import Student
from apps.ineedstudent.models import Hospital
from apps.ineedstudent.forms import HospitalForm, EmailToHospitalForm
from django.utils.translation import gettext_lazy as _

from django.shortcuts import render

from django.http import HttpResponse
from django.template import loader
from apps.mapview.utils import plzs, get_plzs_close_to
import django_tables2 as tables
from django_tables2 import TemplateColumn

from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from apps.accounts.decorator import student_required, hospital_required
from django.contrib.admin.views.decorators import staff_member_required

from functools import lru_cache
from apps.mapview.views import get_ttl_hash
from django.core.mail import EmailMessage
from django.conf import settings
from apps.iamstudent.models import EmailToHospital

from django.views.decorators.gzip import gzip_page


class StudentTable(tables.Table):
    info = TemplateColumn(template_name='info_button.html')
    checkbox = TemplateColumn(template_name='checkbox_studenttable.html')

    class Meta:
        model = Student
        template_name = "django_tables2/bootstrap4.html"
        exclude = ['uuid','registration_date','id']
        fields = ['user']


# Should be safe against BREACH attack because we don't have user input in reponse body
@gzip_page
def hospital_overview(request):
    locations_and_number = prepare_hospitals(ttl_hash=get_ttl_hash(60))
    template = loader.get_template('map_hospitals.html')
    context = {
        'locations': list(locations_and_number.values()),
    }
    return HttpResponse(template.render(context, request))

@lru_cache(maxsize=1)
def prepare_hospitals(ttl_hash=None):
    hospitals = Hospital.objects.filter(appears_in_map=True)
    locations_and_number = {}
    for hospital in hospitals:
        cc = hospital.countrycode
        plz = hospital.plz
        key = cc + "_" + plz
        if key in locations_and_number:
            locations_and_number[key]["count"] += 1
            locations_and_number[key]["uuid"] = None
        else:
            lat, lon, ort = plzs[cc][plz]
            locations_and_number[key] = {
                "uuid": hospital.uuid,
                "countrycode": cc,
                "plz": plz,
                "count": 1,
                "lat": lat,
                "lon": lon,
                "ort": ort
            }
    return locations_and_number

@login_required
def hospital_list(request, countrycode, plz):

    if countrycode not in plzs or plz not in plzs[countrycode]:
        # TODO: niceren error werfen
        return HttpResponse("Postleitzahl: " + plz + " ist keine valide Postleitzahl in " + countrycode)

    lat, lon, ort = plzs[countrycode][plz]

    table = HospitalTable(Hospital.objects.filter(plz=plz))
    table.paginate(page=request.GET.get("page", 1), per_page=25)
    context = {
        'countrycode': countrycode,
        'plz': plz,
        'ort': ort,
        'table': table}

    return render(request, "list_hospitals_by_plz.html", context)


class HospitalTable(tables.Table):
    info = TemplateColumn(template_name='info_button.html')

    class Meta:
        model = Hospital
        template_name = "django_tables2/bootstrap4.html"
        fields = ['firmenname','ansprechpartner','telefon','plz']
        exclude = ['uuid','registration_date','id']

class ApprovalHospitalTable(HospitalTable):
    info = TemplateColumn(template_name='info_button.html')
    status = TemplateColumn(template_name='approval_button.html')
    delete = TemplateColumn(template_name='delete_button.html')
    class Meta:
        model = Hospital
        template_name = "django_tables2/bootstrap4.html"
        fields = ['firmenname','ansprechpartner','user','telefon','plz','user__validated_email']
        exclude = ['uuid','registration_date','id']

@login_required
def hospital_view(request,uuid):
    h = Hospital.objects.filter(uuid=uuid)[0]
    if request.POST and request.user.is_student and request.user.validated_email:
        s = request.user.student

        email_form = EmailToHospitalForm(request.POST)

        if email_form.is_valid():
            start_text = _("Hallo %s,\n\nSie haben von %s (%s) eine Antowrt auf Ihre Anzeige bekommen. "
                           "Falls Sie keine Anfragen mehr bekommen möchten, deaktivieren Sie Ihre "
                           "Anzeige im Profil online.\n\n" % (h.ansprechpartner, s.name_first, request.user.email))
            message = start_text + email_form.cleaned_data['message']
            EmailToHospital.objects.create(student=s,hospital=h,message=email_form.cleaned_data['message'],subject=email_form.cleaned_data['message'])


            email = EmailMessage(
                subject='[match4healthcare]' + email_form.cleaned_data['subject'],
                body=message,
                from_email=settings.NOREPLY_MAIL,
                to=[h.user.email]
            )
            email.send()

            return render(request,'hospital_contacted.html')

    email_form = EmailToHospitalForm(initial={'subject': _('Neues Hilfsangebot'),
                                              'message': _('')})
    return render(request, 'hospital_view.html', {'hospital': h,
                                                  'mail': h.user.username,
                                                  'email_form': email_form})
