from django.contrib.auth.forms import PasswordChangeForm


class AccountPasswordChangeForm(PasswordChangeForm):
    """আমার অ্যাকাউন্ট পাতায়—বর্তমান ও নতুন পাসওয়ার্ড দিয়ে পরিবর্তন।"""

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields['old_password'].label = 'বর্তমান পাসওয়ার্ড'
        self.fields['new_password1'].label = 'নতুন পাসওয়ার্ড'
        self.fields['new_password2'].label = 'নতুন পাসওয়ার্ড (নিশ্চিত করুন)'
        self.fields['old_password'].help_text = ''
        self.fields['new_password2'].help_text = ''
        self.fields['new_password1'].help_text = (
            'কমপক্ষে ৮ অক্ষর। যেকোনো অক্ষর বা সংখ্যা ব্যবহার করা যাবে।'
        )
        for name in ('old_password', 'new_password1', 'new_password2'):
            self.fields[name].widget.attrs.update(
                {
                    'autocomplete': (
                        'current-password'
                        if name == 'old_password'
                        else 'new-password'
                    ),
                    'class': 'account-password-input',
                }
            )
        self.fields['new_password1'].widget.attrs['minlength'] = '8'
        self.fields['new_password2'].widget.attrs['minlength'] = '8'
