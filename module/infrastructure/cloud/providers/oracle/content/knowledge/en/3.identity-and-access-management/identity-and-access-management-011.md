# Password Policies, MFA, and Sign-In Session Management

An account with OCI administrative privileges can create Compute instances, modify networks, access data, or adjust IAM. If an account is protected solely by a password, password exposure can become the starting point of an incident spanning multiple services.

In Oracle Cloud Infrastructure, three layers work together: **password policies** govern user passwords, **multi-factor authentication (MFA)** raises authentication assurance, and **sign-in session management** controls how long and under what conditions authentication results remain usable. These layers protect identity; resource operation permissions are still decided by their corresponding authorization mechanisms.

This lesson belongs to the **IAM Identity and Access Management** chapter, focusing on OCI IAM with **identity domains**. Tenancies using the legacy IAM model may have different screens and mechanisms; do not apply identity domain steps verbatim to a legacy Authentication Settings screen.

## 1. Confirm the Exact Scope Before Configuring

Before modifying policies, answer four questions:

1. Which tenancy and identity domain is the user signing in to?
2. Is the password verified at OCI or at an external identity provider?
3. Is the target application the OCI Console, My Apps, or a federated application?
4. Does the session or credential to control belong to a browser, an identity provider, or an API?

### 1.1. Different Policy Types Have Different Responsibilities

| Component | Primary Responsibility | Does Not Automatically Do |
| --- | --- | --- |
| Password policy | Password rules and certain account lockout behaviors on failed logins | Grant permission to create Compute or read buckets |
| MFA settings | Verification factors allowed for use in the domain | Ensure every sign-in path already mandates MFA |
| Sign-on policy | Conditions allowing sign-in, step-up authentication requirements, and app scope | Replace IAM policies granting resource permissions |
| Session settings | Domain session duration and persistent sign-in options | Globally change lifetimes of all tokens and app sessions |
| Console session idle timeout | Inactivity duration before OCI Console signs out | Change session timeouts of every SSO application |
| IAM authorization policy | Who can do what with cloud resources | Set password length or configure MFA |

For example, someone who completes MFA can still receive a permission error reading Object Storage. That may be an authorization gap, not evidence that MFA failed to work.

### 1.2. Local Users and Federated Users

A **Local user** authenticates with credentials managed by the identity domain. The domain's password policy applies directly to that password.

A **Federated user** is redirected to an identity provider (IdP), such as a corporate identity system, for authentication. If the password is verified at the IdP, changing the password policy in OCI does not change the IdP's password policy.

With federation, determine where MFA runs, how federated login paths are configured, and which direct login paths still exist. Never assume having SSO means everyone uses MFA, or that OCI must always prompt for a second MFA after the IdP. An overview of models is presented by Oracle in [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

## 2. Password Policies in an Identity Domain

A password policy defines the requirements a password must satisfy when set or changed. When administering them, inspect the policy, assigned groups, and priority together rather than looking at a single criteria table.

### 2.1. Common Setting Groups

| Setting | Meaning | Considerations |
| --- | --- | --- |
| Minimum and maximum length | Bounds on password length | Allow long passwords and password manager compatibility |
| Character requirements | Counts of letters, digits, special characters, or distinct characters | Excessive constraints often yield predictable password patterns |
| Disallowed values | Restricts personal info or disallowed strings per supported options | Check actual capabilities of the policy type |
| Password history | Restricts reusing previous passwords | Does not prevent reusing the same password on another service |
| Password expiration | Validity period of a password | Must fit organizational requirements and rotation processes |
| Account lock threshold | Consecutive failed attempts triggering lockout | Balance brute-force defense against accidental user lockouts |
| Automatic account unlock | Auto-unlocks after a configured period | Does not mean the cause of failed sign-ins was resolved |

OCI identity domains offer options such as Simple, Standard, and Custom. Custom permits adjusting criteria; Simple and Standard use fixed presets for those policy types. Oracle describes fields and group-to-policy relationships in [Creating a Password Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/passwordpolicies/Managing-Password-Policies_set-password-policies-your-identity-domain.htm).

Never treat a set of values seen in a screenshot as the default for every tenancy. A domain may have been customized, migrated from a legacy system, or have different policies applied to different groups.

### 2.2. Choosing Passwords and Expiration Periods

Passwords should be long, unique to the account, and managed with an appropriate tool. Avoid company names, usernames, birth dates, or incrementing trailing digits in a familiar pattern.

Password expiration and changing a password during an incident are two separate matters:

- Expiration is scheduled rotation per configured duration.
- When password compromise is suspected, act immediately per incident procedures, even if the password has not expired.
- Changing a password does not replace reviewing active sessions, MFA factors, and API credentials.

In identity domains, a value of `0` in the expiration field can mean passwords do not automatically expire. That is a configuration meaning, not a blanket recommendation. If the organization has password lifecycle requirements, reflect them explicitly in the design.

### 2.3. Account Lockout Is Not Account Deactivation

An account locked due to failed attempts can be unlocked over time or by an authorized administrator. An account deactivated for offboarding or an incident is a different administrative state.

For example, if the lockout threshold is five consecutive failures, a user mistyping multiple times can be locked out even when their password is still valid. Setting the threshold too low can also make it easier for an attacker to deliberately disrupt logins.

Distinguish three counters if the domain configures them separately:

- Failed password sign-ins.
- Failed MFA verifications.
- Failed account recovery attempts.

Unlocking for failed password attempts does not necessarily clear a lock from another mechanism.

### 2.4. Priority Determines Which Policy Takes Effect

One person can belong to multiple groups. In the identity domain password policy model, the highest-priority policy among policies attached to the user's groups is applied; criteria are not automatically merged into one strictest composite policy.

Design example:

| Group | Policy | Illustrative Priority |
| --- | --- | --- |
| `oci-security-lab-users` | `lab-password-policy` | 2 |
| `oci-project-users` | `project-password-policy` | 5 |

If a user belongs to both groups, the policy at priority 2 takes precedence over priority 5. In this UI, a smaller number indicates higher priority.

Consequently, adding a user to a group can change their effective password requirements. When investigating discrepancies between two accounts, check group memberships and priorities before concluding the system applied the wrong rule.

Do not assume editing criteria immediately signs everyone out or forces immediate re-entry of all existing passwords. Check reset behavior, password-change prompts, and when the policy is evaluated in the specific flow.

## 3. MFA: Factors, Enrollment, and Enforcement

MFA uses multiple factors to raise confidence in the identity signing in. A password and a secret question both rely on something the user knows; adding just any extra prompt does not deliver protection equivalent to an independent authentication device.

### 3.1. Common Factors

| Factor | Usage | What to Understand |
| --- | --- | --- |
| Mobile app passcode, typically TOTP | Enter a code generated by an authenticator app | Can generate codes offline; device clock must be accurate |
| Mobile app notification | Approve prompt on a mobile app | Approve only requests you initiated yourself |
| FIDO authenticator | Use a hardware security key or compatible device authenticator | Requires compatible hardware and browser; prepare a backup device plan |
| Email or SMS, if allowed | Receive and enter verification code | Protection depends on email, phone number, and recovery channels |
| Bypass code | Use backup code within configured limits | Sensitive secret material, not a way to permanently skip MFA |

Which factors actually appear depends on domain settings, sign-on rules, and supported capabilities. Never assume every factor in this table is permitted for the OCI Console.

Oracle describes these factors and how users manage them in [Managing 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/manage-2-step-verification.htm).

For administrative accounts, favor strong organization-supported mechanisms such as FIDO where appropriate. OTP codes can be entered into phishing sites and relayed; push notifications can also be accidentally approved by users. User training therefore remains part of MFA design.

### 3.2. Three States That Must Not Be Conflated

```text
Domain allows a factor
            ↓
User enrolls and verifies the factor
            ↓
Sign-on policy requires the factor on the corresponding access path
```

Enabling TOTP in a domain does not prove everyone has enrolled. A user having enrolled also does not prove every application enforces that factor.

Conversely, enforcing a factor before users can enroll or use it will cause lockouts. Design enrollment and recovery flows before broadening enforcement.

### 3.3. Avoid Confusing MFA Settings with Sign-On Policies

MFA settings govern available factors and related options. Sign-on policies govern when access is allowed, when step-up factors are required, who they apply to, and which applications they cover.

Items to inspect in a sign-on rule include:

- User or group conditions.
- Applications and authentication paths protected by the policy.
- Network or other contextual conditions if present.
- Allow or deny action.
- Whether an additional factor is required.
- Whether enrollment is mandatory or optional.
- Required factor(s) and verification frequency.
- Exclusion conditions and rule priority order.

Oracle explains coordinating both pieces in [Configuring Multifactor Authentication Settings](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/configure-multi-factor-authentication-settings.htm).

## 4. Sign-On Policies and Rule Evaluation Order

### 4.1. Policies Attached to Applications

An application can be attached to a dedicated sign-on policy; if no dedicated policy applies, examine the behavior of the Default Sign-On Policy. Editing the default rule will not necessarily change the OCI Console flow if the Console is already attached to its own dedicated policy.

Before editing, check application assignments and active rules. Oracle describes relationships among applications, policies, and sign-on conditions in [Managing Sign-On Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/managingsignonpolicies.htm).

### 4.2. An Earlier Broad Rule Can Shadow a Needed Rule

The table below is a design model for analyzing order, not OCI IAM policy statements:

| Illustrative Order | Condition | Intended Action |
| --- | --- | --- |
| 1 | Access from a defined blocked network range | Deny |
| 2 | Selected administrator group | Allow after meeting required MFA |
| 3 | Selected application user group | Allow with application MFA requirement |
| 4 | Remaining cases | Handle per approved baseline rule |

Rules are evaluated by priority. A very broad allow rule positioned before a rule requiring MFA for administrators can cause actual behavior to diverge from the intended design.

Never read an "MFA for admins" rule in isolation; inspect all rules ordered ahead of it. Reordering steps are described in [Changing the Priority of a Rule for a Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/change-priority-sign-rule-policy.htm).

### 4.3. Security Policy for OCI Console

A domain may already include the **Security Policy for OCI Console**, containing preconfigured MFA rules for administrators and users. If present, start by inspecting its status, attached apps, and active rules.

Never create a weaker login path just to make a lab screen resemble an old guide. Nor should you lower existing MFA requirements merely because a test group has not enrolled a factor yet. Oracle describes this policy and protecting administrative recovery in [Identity Domains With the Security Policy for OCI Console](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_identity_domains_signon_policy.htm).

My Profile and My Apps can also enforce their own default MFA protection. Being prompted for MFA again when entering security management pages does not prove the Console session is broken. See [Default MFA Security for Identity Domains My Profile and My Apps Pages](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/default_mfa_access_for_identity_domains_my_profile.htm).

## 5. Session Management: Multiple Clocks Running Together

After authentication, browsers typically use cookies or session state to maintain access. Re-entering a password for every click is impractical; keeping sessions alive too long increases the window in which a stolen session remains usable.

### 5.1. Types of Timeouts and Lifetimes

| Type | Measured From | Consequence on Expiration |
| --- | --- | --- |
| Identity domain session duration | Time since the session was established | Domain session expires even during active use |
| OCI Console idle timeout | Inactivity duration per Console mechanism | Console prompts to re-establish access |
| My Apps idle timeout | Inactivity within My Apps per corresponding config | Affects My Apps scope |
| External IdP session lifetime | IdP rules | May prompt for re-authentication at the IdP |
| Application session or OAuth token | Configuration and mechanics of that app or token | Must be handled per that protocol and application |

**Session duration** and **idle timeout** do not replace each other. Oracle documents identity domain session duration as a lifetime independent of whether the user is active in [Setting Session Limits](https://docs.oracle.com/en-us/iaas/Content/Identity/sessionsettings/session-limits.htm).

### 5.2. Example Distinguishing Maximum Lifetime from Inactivity

Suppose in a test environment:

- Domain session duration is 120 minutes.
- Console idle timeout is 15 minutes.
- Keep me signed in is disabled.
- No other renewal behavior alters this illustrative scenario.

The user signs in at 09:00:

| Timeline | Expiration Condition to Consider |
| --- | --- |
| Active steadily from 09:00 until nearly 11:00 | Domain session still hits the 120-minute ceiling |
| Last activity at 09:20, then left idle | Console may end the access session after roughly 15 minutes of inactivity |
| Returns after Console idle timeout | May be routed through the SSO flow to re-establish access |

The arithmetic 09:20 plus 15 minutes illustrates idle timeout semantics, not a promise that every browser tab changes screens at exactly 09:35. Detecting expiration and re-prompting for credentials also depends on the next request, SSO state, and sign-on rules.

An expired Console session also does not always mean the user must re-type a password immediately: an active IdP or SSO session can participate in re-authentication. To force fresh authentication or re-prompt MFA, review both sign-on policies and IdP behavior.

### 5.3. OCI Console Has Its Own Idle Timeout Setting

Per Oracle documentation, open the Profile menu, choose Console settings, and configure Session idle timeout. This is a tenancy-level setting; permission to change it also differs from editing an individual user account.

Never use the My Apps idle timeout field as proof that you changed the OCI Console timeout. Steps and permission scopes are documented in [Changing the Session Time-Out](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/console_topic-session-timeout.htm).

### 5.4. Keep Me Signed In Differs from Trusted Device

**Keep me signed in** helps persist sign-in state per domain configuration. **Trusted device** concerns remembering a device and suppressing or altering step-up factor prompts under permitted conditions.

These two mechanisms are not identical and do not replace password policies. Neither should be used on shared workstations merely because MFA prompts feel inconvenient.

When enabling persistent sign-in, review lifetimes, re-authentication triggers, and sign-on rules. Sign-on policies can still compel re-verification. Oracle describes these options in [Changing Data Sharing Settings](https://docs.oracle.com/en-us/iaas/Content/Identity/sessionsettings/data-sharing-settings.htm).

### 5.5. Closing Tabs, Signing Out, and Revoking Sessions

Closing a tab is not signing out. Closing the browser also does not guarantee all persistent cookies were cleared.

Signing out of one application does not guarantee all sessions at the IdP, domain, and other applications end together. In federated setups, verify logout behavior configured across all parties.

Clearing cookies on one machine only resets state on that machine; it is no proof that copies of credentials or sessions on other devices were invalidated.

## 6. Recovery and Administrative Continuity

Strong MFA without a recovery plan can lock an organization out when a phone is lost, a security key breaks, or a policy is misconfigured.

### 6.1. Design Recovery as Part of Security

Prepare:

- Backup factors where policy and devices allow.
- Functional and protected recovery channels.
- Procedures to verify anyone requesting support.
- Authorized staff who can unlock accounts, reset factors, and handle login incidents.
- Tested emergency administrative paths before broadening enforcement.

An unprotected recovery email becomes a weak link even when the OCI account uses strong MFA. Help desk procedures must also never issue bypass codes based solely on a display name or unverified chat message.

Account recovery mechanisms are configured separately from sign-in factor enrollment; Oracle describes this scope in [Managing Account Recovery](https://docs.oracle.com/en-us/iaas/Content/Identity/accountrecovery/understand-account-recovery.htm).

### 6.2. Backup Administration

In its MFA guidance, Oracle requires preparing backup access and provides instructions for excluding at least one administrator from relevant rules to avoid total lockout. When using this mechanism, govern it as a dedicated emergency break-glass account: restrict usage, protect credentials, monitor every access, and test periodically.

Another approach in deployment guides is preparing an administrative REST API client before applying configurations that could block all interactive logins. A highly privileged client is a sensitive identity that must be managed accordingly.

Keeping an open admin browser tab helps during testing, but it does not replace a recovery path: that session can still expire.

### 6.3. Bypass Codes and Resetting Factors

A bypass code is backup verification data that allows completing verification. Never paste codes into group chats, logs, or shared documents.

Distinguish user-generated codes from administrator-issued codes. For admin-generated codes, OCI supports configuring expiration and usage count; when granting temporary support, choosing short lifetimes and minimal use counts bounds impact. Details are in [Generating a Bypass Code for a User](https://docs.oracle.com/en-us/iaas/Content/Identity/users/generate-bypass-codes-user-accounts.htm).

Resetting factors is not changing a password, and changing a password does not remove enrolled factors. When an MFA device is suspected compromised, audit existing factors, re-enroll on a trusted device, and address active sessions.

## 7. Controlled Practice in a Dedicated Environment

The practice goal is observing each policy layer and demonstrating real sign-in paths. The steps below run on a **test identity domain**; tenancy-wide changes, such as Console idle timeout, require a dedicated lab tenancy or observation of existing values only if shared.

### 7.1. Prepare Targets and Permissions

Prepare:

1. An administrator authorized to manage the required security settings.
2. A test local user account; never use an admin account as an error-testing target.
3. Group `oci-security-lab-users`, containing only the test user.
4. Clearly identified target application and sign-in path.
5. A compatible MFA device or app, with recovery ready.
6. A dedicated browser profile for the test user.

Permissions to manage domain settings and permissions to alter tenancy-level Console settings must be identified separately. Never assign tenancy-wide admin rights to the test user just to test sign-in.

Before editing, record current policies, assignments, rule priorities, MFA status, and session settings. Never store passwords, enrollment QR codes, or bypass codes in lab evidence.

### 7.2. Create or Verify Password Policy for the Test Group

You can use the following illustrative values in a dedicated environment:

| Parameter | Illustrative Value |
| --- | --- |
| Minimum length | 16 characters |
| Maximum length | 128 characters |
| Prior passwords remembered | 5 |
| Lockout threshold on failed attempts | 5 consecutive attempts |
| Auto-unlock | After 15 minutes |
| Password expiration | Per requirement chosen for the test environment |

These are practice values, not OCI defaults or a mandatory standard for every organization. If existing settings are stronger, do not weaken requirements just to match this table.

In the domain's Password policies:

1. Create a Custom policy or select the prepared test policy.
2. Attach group `oci-security-lab-users`.
3. Check priority relative to policies attached to other groups the user belongs to.
4. Save changes.
5. In the test user's browser profile, open the password change flow.
6. Verify a password failing length criteria is rejected; then set a unique password satisfying all criteria.

Do not publish copyable sample passwords. Generate unique passwords with an appropriate tool and record only whether criteria passed or failed.

Never test consecutive failed attempts on an administrative account. Lockout testing, if needed, must run only on a lab account with a ready unlock path and controlled attempt counts.

### 7.3. Enroll and Verify MFA

First inspect the MFA policy protecting the target application. If the OCI Console already requires MFA, work within the existing requirement; do not disable and re-enable it just to simulate enrollment.

In the test domain:

1. Administrator confirms permitted factors.
2. User enrolls a factor in the sign-in flow or My Profile per UI.
3. Complete factor verification.
4. Prepare appropriate recovery.
5. Confirm the rule applies to the user and target application requiring MFA.
6. Sign out and open a fresh test browser session to avoid stale SSO state.
7. Sign in via the right path and observe the factor prompt.

If an enrollment QR code appears, that is secret setup material: never screenshot it into public reports. Once complete, retain evidence only of the factor method and enrollment status.

User-side instructions are in [Setting Up Account Recovery and 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/manage_security_and_2_step_verification.htm).

### 7.4. Verify Sign-In Sessions

In a dedicated environment, for example set the domain session duration to 30 minutes. If the lab tenancy allows changing idle timeout, a 5-minute Console idle timeout makes observation easier; if the tenancy is shared, only record the current setting.

Run two independent scenarios:

| Scenario | How to Execute | What to Record |
| --- | --- | --- |
| Idle | Sign in, note time, leave untouched past threshold, then send a new action | Whether Console prompts to sign in again and what SSO flow follows |
| Active | Sign in with a fresh session, interact periodically past session duration | How the domain session expires and how the system re-establishes auth |

Record login time, last activity time, re-prompt time, active policy, and Keep me signed in state. If using federation, also note whether the IdP session remained active.

Never conclude "MFA was bypassed" simply because no password screen appeared. Determine which authentication state was reused and whether the rule requires a fresh factor for that scenario.

### 7.5. Practice Completion Criteria

| Check | Required Evidence |
| --- | --- |
| Right domain and local user | Recorded identity along with sign-in path |
| Password policy active | Non-compliant password rejected; compliant password accepted |
| MFA enrollment complete | Factor verified and recovery prepared |
| MFA enforcement properly scoped | Fresh sign-in to target app passes through the required prompt |
| Idle timeout understood | Last activity time and observed re-prompt time recorded |
| Session duration understood | Maximum lifetime distinguished from inactivity |
| Backup admin path works | Tested recovery path aligned with design |

At the end of the lab, restore any modified domain- or tenancy-level settings to their intended baseline. Remove test users, groups, and policies when no longer needed; avoid deleting objects referenced by other applications.

## 8. Diagnosing Common Scenarios

| Symptom | Possibilities to Check | Targeted Action |
| --- | --- | --- |
| Users A and B get different password rules | Different groups, priorities, or auth sources | Compare effective policies and IdP |
| Password is right yet login fails | Locked account, deny rule, MFA, or wrong domain | Identify exact failing step and account status |
| MFA enrolled yet app doesn't prompt | Policy not attached to app, earlier rule matched, remembered session/device | Check assignments, priority, and a fresh session |
| Desired factor not shown | Domain hasn't allowed it or rule restricts factors | Check both MFA settings and rules |
| TOTP codes repeatedly fail | Clock drift, wrong account in app, stale enrollment | Sync clock and confirm right factor |
| Push arrives when user isn't signing in | Possible uninitiated login attempt | Deny, record, and report per incident procedure |
| Changed My Apps timeout yet Console unchanged | Configured the wrong layer | Check Console settings separately |
| Changed password yet tool still calls API | Tool uses API key, token, or different identity | Identify actual credential instead of rotating password again |
| Admin locked out right after configuring MFA | Rule too broad, wrong order, or no valid factor | Use prepared recovery path; don't randomly edit every rule |

A `NotAuthorized` error on resource actions after signing in usually points to investigating IAM authorization policies, not relaxing MFA requirements.

When sending details for support, provide timestamps, domain, application, error codes, and relevant event IDs. Never send passwords, session cookies, OTPs, tokens, or enrollment QR codes.

## 9. Revoking Access on Offboarding or Incidents

Password policies, MFA, and session timeouts are preventive measures; they do not replace revocation workflows.

A response sequence can include:

1. Identify whether the user is local or federated and the impacted resource scope.
2. Deactivate or restrict the identity per authority to block new sign-ins.
3. Inspect and terminate persistent sessions, IdP sessions, and related app sessions.
4. Rotate passwords or reset factors if compromise is possible.
5. Audit API signing keys, auth tokens, customer secret keys, and other credentials.
6. Remove permissions, group memberships, or application assignments as needed.
7. Review logs for activity before and after revocation.

For Keep me signed in, users can view and clear remembered sessions; administrators have corresponding actions in user management per granted permissions. Clearing this session type must not be interpreted as revoking every access token or every service session. Oracle documents the user-side action in [Clearing Your Keep Me Signed-In Sessions](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/access-your-signed-in-sessions.htm).

Changing a Console password does not rotate an API signing key. Browser MFA also does not add an OTP step to every request signed with an API key. Credentials require their own lifecycles and revocation procedures; see credential scope in [IAM Credentials](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_Credentials.htm).

For workloads on Compute, evaluate appropriate workload identities such as Instance Principals instead of running automation with a user account holding long-lived login sessions.

## 10. Monitoring and Maintaining Policies

Track signals meaningful to your deployment model:

- Unusual spikes in failed sign-ins.
- Repeated MFA rejections or failures.
- Unexpected factor enrollments, modifications, or resets.
- Bypass code generation or break-glass account usage.
- Changes to password policies, sign-on rules, assignments, or session settings.
- Sign-ins continuing after expected access revocation time.

Use identity domain reports and logs, OCI Audit, and IdP logs matched by event type; do not assume every source captures every authentication step completely. Timestamps, identities, and applications help correlate incident timelines.

When updating policies, evaluate both security and operability: do users hold valid factors, does recovery work, who handles support, and which applications are impacted? Monitor a pilot group before expanding broadly.

Administrative accounts require regular reviews of permissions, sign-in paths, and exceptions. For regular users, inspect group memberships too since they can alter effective password policies and sign-on rules. For federated users, maintain clear accountability between IdP admins and OCI admins.

A verifiable design must specify: where passwords are verified, which access paths require MFA, under which conditions each session type expires, and how access is terminated when needed.
