"""회원가입·본인 정보 (로그인·로그아웃은 django.contrib.auth.urls 기본 뷰 사용)"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


def signup(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = UserCreationForm(request.POST)       # 중복 아이디·비밀번호 불일치·약한 비밀번호 검사
        if form.is_valid():
            user = form.save()                       # 일반 회원으로 생성 (is_staff=False)
            messages.success(request, f"{user.username}님, 가입이 완료되었습니다. 로그인해 주세요.")
            return redirect("login")
    else:
        form = UserCreationForm()
    return render(request, "accounts/signup.html", {"form": form})


@login_required                                     # 비로그인 → /accounts/login/?next=/accounts/me/
def me(request):
    jobs = request.user.analysis_jobs.all()          # 본인 작업만 (관리자도 여기서는 본인 것만)
    return render(request, "accounts/me.html", {
        "job_count": jobs.count(),
        "recent_jobs": jobs[:5],
    })
