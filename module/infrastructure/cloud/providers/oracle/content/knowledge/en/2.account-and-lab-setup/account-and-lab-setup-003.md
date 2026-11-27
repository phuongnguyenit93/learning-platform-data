# Protecting the Initial Administrator Account and Enabling MFA

## Objectives and Scope

The initial administrator account in Oracle Cloud Infrastructure (OCI) can affect the identities, access permissions, and resources of the entire tenancy. Before creating a VCN, Compute, storage, or databases for labs, you must protect this account and verify that you can still sign in if your phone or primary authentication method fails.

This lesson belongs to the **Account and Lab Setup** chapter of the Oracle module. Expected outcomes include:

- Identifying the exact account, identity domain, and sign-in path in use.
- Protecting your password, recovery email, and authentication device.
- Enrolling MFA, checking policies that enforce MFA, and testing sign-in in a fresh session.
- Preparing recovery options without creating long-term MFA bypass exceptions.
- Separating the administrator account from everyday lab activities and automation credentials.

Navigation paths were verified against Oracle documentation as of **November 20, 2026**. The UI may vary by tenancy type and identity domain. The primary flow in this lesson targets **IAM with Identity Domains**; the environment identification section helps avoid mistakenly applying instructions written for the legacy model.

## 1. Why Protect the Administrator Account from the Start?

In a tenancy with identity domains, the Default identity domain contains the initial administrator user and the `Administrators` group. The default policy grants this group permission to manage resources across the tenancy. See [The Default Identity Domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm).

If those credentials are compromised, an unauthorized actor can perform actions up to the account's permissions: alter IAM, affect data, or create cost-incurring resources. Therefore, protecting the administrator account also helps protect your budget and your ability to recover the learning environment.

Do not share a single administrator account among multiple people. Each person needs their own account and permissions appropriate for their work. For a personal account, keep the administrator account for identity management, billing, and incident recovery; create separate users for labs once you learn how to grant compartment-scoped permissions.

### 1.1. Successful Sign-In Differs from Having Admin Permissions

Keep two questions separate:

- **Authentication:** did the system verify the right person is signing in? Passwords and MFA participate in this step.
- **Authorization:** what is that person allowed to do after signing in? Groups, roles, and IAM policies determine the scope of allowed actions.

Someone who signs in with MFA may still lack permission to view resources. Conversely, granting extra administrative permissions will not fix an OTP error or logging into the wrong domain.

Identity domain administrator roles also require reading their exact scope. In particular, administrative rights over a secondary domain do not equate to tenancy-wide administrative rights, as Oracle notes in [The Default Identity Domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm). When designating recovery helpers, check actual permissions rather than relying only on role names.

## 2. What Does MFA Protect?

**MFA (Multi-Factor Authentication)** requires multiple factors to verify identity. In the familiar flow, a user enters a password and then provides an additional code or confirmation from a registered device. This serves as an extra layer of protection when only the password is exposed. Refer to [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

Example:

```text
Account password
        ↓
Additional factor from registered device
        ↓
Authentication completes
        ↓
IAM permissions determine allowed actions
```

Two different passwords are still the same category of secret—something the user knows; asking for a second password should not be treated as equivalent to possessing a separate authentication device.

### 2.1. Enabling Factors, Enrolling Factors, and Enforcing MFA Are Three Distinct Steps

| Item to verify | Meaning | Evidence required |
| --- | --- | --- |
| Domain allows factor | Administrator enables methods users are permitted to use | Desired factor appears in domain configuration |
| User is enrolled | Account is linked to an app or device | Enrollment completed and verified successfully |
| Policy requires MFA | Application sign-in flow mandates an additional factor | Fresh sign-in session is governed by the scoped policy |

Oracle distinguishes administrator configuration from user self-service enrollment in [Setting Up Account Recovery and 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/manage_security_and_2_step_verification.htm). Therefore, seeing an app generate codes on your phone is not enough to prove the Console enforces MFA for your administrator account.

### 2.2. Console MFA Has Its Own Scope

Console sign-in policies do not automatically protect all other credentials. API private keys, tool tokens, SSH keys, and browser sessions must be managed appropriately for how they are used. OCI Console MFA policies apply to the Console sign-in flow as described in [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

For instance, enabling MFA is not a license to commit API private keys into Git or use a tenancy-wide administrator account for every automation task. When learning OCI automation, you will need to grant properly scoped permissions and protect each credential type individually.

## 3. Preparing Before Enrolling or Changing Policies

### 3.1. Identify the Exact Tenancy, Domain, and Sign-In Path

Record the tenancy name, username, and identity domain of your current session. In the Console, look under **Identity & Security → Domains**. If Domains is present, open the active domain and locate **Security → Sign-on policies**. If Domains is absent, consult the guidance branch for tenancies without identity domains. See [Determining the Tenancy Type](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/determining_the_tenancy_type.htm).

Do not assume the signed-in user always resides in a domain named `Default`, especially in migrated or multi-domain tenancies. Check the actual session details and user record.

If signing in via an external identity provider such as Microsoft Entra ID or Okta, verify MFA at the IdP and the federation flow into OCI. Do not conclude the account is protected just because a different local user enrolled MFA. Oracle distinguishes IdP-based MFA scenarios in [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

### 3.2. Protect Passwords and Recovery Email

Use a unique password for the administrator account, save it in a password manager, and never share it in chat, source code, or lab documents. Protect the mailbox used for notifications and account recovery as well; a compromised mailbox weakens your recovery path.

Under **User settings → My profile → Security**, check the recovery methods permitted by the domain. Options may include a recovery email, phone number, or other choices depending on configuration. Choose details you reliably control and complete verification if prompted. Refer to [Setting Account Recovery Options](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/set-your-account-recovery-options.htm).

Do not assume resetting a password will restore a lost MFA factor. Those two issues may require separate recovery steps.

### 3.3. Prepare Devices and Recovery Paths

Before your setup session:

- Prepare a compatible phone or authentication device with a screen lock and active access.
- Install the app from the official store referenced in Oracle documentation; verify the publisher.
- Sync date and time on the device if using time-based codes.
- Prepare a place to store recovery codes separate from the primary authentication phone.
- Know who can assist with domain administration or how to contact official support if access is lost.

When modifying domain-level policies, keep your current admin session open while testing a new session. However, an old session can expire or demand re-authentication; it is not a guaranteed recovery path. Before making changes affecting all users, have a tested alternate admin path and complete all prerequisites in Oracle's guide.

## 4. Inspecting the MFA Policy for OCI Console

In the active identity domain, locate the **Security Policy for OCI Console** policy. According to the built-in configuration described by Oracle, the policy contains two rules: `MFA for administrators` takes priority first, followed by `MFA for all users`. This configuration requires enrolling and providing an additional factor when signing into the Console. Refer to [Identity Domains With the Security Policy for OCI Console Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_identity_domains_signon_policy.htm).

Check the active status, assigned Console application, and effective rules. Having the right policy name while it is disabled, altered, or missing the target users is not sufficient to confirm completion.

If the built-in policy is already active and functioning properly, proceed to factor enrollment and login testing; there is no need to create a duplicate custom-named policy. Oracle recommends keeping the built-in configuration as a best practice in the [Console policy guide](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_identity_domains_signon_policy.htm).

For a reviewed policy that is not yet active, activation is found on the policy details page under **Actions → Activate sign-on policy**, followed by confirmation. Only do this after completing recovery preparation and verifying the target scope. See [Activating a Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/activate-sign-policies.htm).

## 5. Enrolling an Authentication Factor for the Administrator Account

### 5.1. Choose a Method Supported by the Domain

| Method | How it works | What to watch out for in practice |
| --- | --- | --- |
| Mobile app passcode | App generates OTP codes; works even when the phone is offline | Select the right account entry in the app and enter a valid code |
| Mobile app notification | App receives sign-in approval or denial prompts | Only approve prompts that you just initiated yourself |
| FIDO authenticator | Uses an external security key or supported built-in method | Verify compatibility and recovery before making it your primary factor |
| Bypass code | Uses pre-generated codes to verify when needed | Protect like an authentication secret; never use as a shared login method |

Oracle describes factors and third-party TOTP app support in [Configuring Authentication Factors](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/configure-authentication-factors.htm). Which methods appear to users also depends on domain configuration and type. Do not enable every factor just to have more choices.

The flow below uses **Oracle Mobile Authenticator (OMA)**. OMA can generate OTPs or receive sign-in notifications depending on how it is enrolled; see [Overview of the Oracle Mobile Authenticator App](https://docs.oracle.com/en-us/iaas/Content/Identity/mobileauthapp/use-oracle-mobile-authenticator-app.htm).

### 5.2. Enrolling When Prompted at Sign-In

When the policy requires enrollment, follow the **Enable Secure Verification** screen or equivalent verification setup step. Use the app matching your chosen method, complete account linking, and finish the final verification step. The account should only be considered enrolled once the Console confirms the process is complete.

Do not stop merely because an account entry appeared in the mobile app. You may have completed the linking step without finishing browser verification.

### 5.3. Enrolling from My Profile If Not Yet Done

If the interface allows self-service enrollment:

1. Open **Profile → User settings**.
2. Under **My profile**, select **Security**.
3. Under **2-Step verification**, select **Enable** if not already enabled.
4. Choose a supported factor and follow the displayed steps.
5. Complete **Verify** to finish activation.

This flow is described in [Activating 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/enroll-2-step-verification-first-login.htm).

With OMA and a QR code, the UI may display **Mobile app → Configure**. Open OMA on your phone, select **Add account**, scan the QR code shown in the Console, and complete verification. Refer to [Adding an Account to the OMA App by Scanning the QR Code](https://docs.oracle.com/en-us/iaas/Content/Identity/mobileauthapp/add-account-oma-app-scanning-qr-code.htm).

**Enrollment QR codes and manual setup keys are secrets.** Do not screenshot them into exercise reports, commit them to Git, or share screens showing them. If you need completion evidence, capture the enrolled status after closing the secret display.

### 5.4. Proper Habits When Using MFA

OTP codes do not automatically defeat all phishing attacks. Attackers can trick users into entering codes on a fake page and replay them while the code remains valid. NIST notes this limitation for OTPs in [SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html).

Therefore:

- Open the sign-in page from a verified URL or saved bookmark.
- Verify the exact page and account before entering a password or OTP.
- Deny sign-in notifications you did not initiate.
- Never read OTPs or bypass codes aloud to anyone claiming to be support staff.
- If repeated unexpected prompts occur, record the timestamps and inspect your account from a trusted device.

Setting up MFA is one part of access protection; how you handle daily authentication prompts also determines its effectiveness.

## 6. Preparing Recovery While Preserving MFA Protection

### 6.1. Generate and Store Bypass Codes

After enrolling 2-Step Verification, if the domain permits bypass codes:

1. Open **Profile → User settings → Security**.
2. Locate **Bypass codes** and select **Generate**.
3. Store the codes in a secure place accessible even when your primary phone is unavailable.
4. Close the code display once safely stored.

These codes can be used as an alternative verification factor when you do not have your device, per [Generating a Bypass Code](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/generate-bypass-code.htm).

Note the validity conditions and usage count displayed in your workflow; do not assume a code lasts forever. In lab notes, record only **generated and stored**, not the actual code values.

For example, keeping a screenshot of recovery codes solely on the same phone running OMA does not solve losing that phone. The purpose of a recovery path is remaining usable when the primary factor is unavailable.

### 6.2. Identify Support Administrators or Backup Admin Identities

If another administrator exists, confirm they have permission to manage authentication factors in the exact identity domain. If you set up a backup administrator identity for a personal tenancy, protect that identity with MFA as well, test signing in, and safeguard its recovery methods appropriately.

Two accounts relying solely on the same single phone do not provide independent recovery if that phone is lost. At the same time, a backup account should not become a shared administrator account for everyday lab activities.

An administrator with appropriate permissions can reset a user's authentication factors. Resetting clears registered factors and requires the user to re-enroll on next sign-in; see [Resetting Authentication Factors for User Accounts](https://docs.oracle.com/en-us/iaas/Content/Identity/users/reset-authentication-factors-user-accounts.htm).

### 6.3. Do Not Equate Bypass Codes with Disabling MFA in Policy

These two mechanisms have different impacts:

- A bypass code is an alternate verification method permitted by the system under defined conditions.
- An MFA exemption lets a user or group sign in without any additional factor requirement.

Do not create permanent exemptions for administrator accounts out of fear of losing a phone. Prepare recovery options and test them instead. If your organization has an emergency access procedure, it should define ownership, storage, testing, and review schedules.

Recovery codes also do not fix every failure mode. Disabled accounts, access-denying rules, or missing IAM permissions must be resolved according to their root cause.

## 7. Verifying Effectiveness with a Fresh Sign-In Session

Keep your existing session open during testing, then open a clean browser profile or a Chrome/Edge private window to avoid reusing an SSO session. Use a browser supported by OCI; if using Firefox, prefer a fresh profile because Private Browsing mode is not supported by Oracle by default, per the [sign-in troubleshooting guide](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signinginIdentityDomain.htm). Manually enter the verified sign-in URL and select the right tenancy, domain, and user.

Verify against these criteria:

| Check | Expected outcome |
| --- | --- |
| Sign in to right admin account | Flow targets the right domain and right user |
| Primary factor | Verification code or push notification works and Console accepts it |
| MFA prompt | Cannot claim completion solely from an already-open old session |
| Alternative path | Know how to select an alternate method permitted by the domain |
| Admin permissions | After sign-in, required permissions to manage the environment remain intact |
| Written record | Includes test timestamp and result; contains no authentication secrets |

When an alternative method is needed, the verification screen may offer **Show alternative login methods**. Select an enrolled method or permitted bypass code; see [Signing In to an Identity Domain Using an Alternative Login Method](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/sign-in-identity-domain-alternative-login-method.htm).

Do not intentionally enter wrong codes repeatedly to test security; this can trigger account lockout. When testing a recovery code consumes a use, replenish your recovery material according to actual capabilities and conditions.

If the new session does not prompt for MFA, check the following before making changes:

1. Is it genuinely a fresh session, or does the browser still hold SSO or trusted-device state?
2. Is the user signing in locally or through an external IdP?
3. Is the policy active and assigned to the Console application?
4. Which rule matches the user, and are there exemptions or rule ordering differences?
5. Is the additional-factor frequency set to match your goal?

A screenshot showing "MFA enabled" does not substitute for an actual sign-in test result.

## 8. When No Built-In Console Policy Exists

This is a domain-level configuration branch to follow per [Identity Domains Without the Security Policy for OCI Console Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_with_identity_domains.htm):

1. Complete Oracle's prerequisites, including an administrative recovery path via a properly authorized client application and stored bypass codes.
2. Under **Security → MFA**, enable the required factors and configure them.
3. Create a sign-on policy with a rule requiring an additional factor; verify `Enrollment: Required` and frequency `Every time` as intended.
4. Check which groups/users match the rule and the evaluation order.
5. Assign the **Console** application, activate the policy, and then test a fresh sign-in session.

A rule targeting only administrators can lock out other users if no appropriate rule exists for them. Do not deploy by copying a single isolated rule while skipping the rest of the guide and recovery path.

An administrative client application is a privileged credential that must be managed separately. This recovery path must be designed, stored, and tested before broad changes; do not treat an open browser session as a substitute for it.

## 9. Replacing a Phone, Losing a Device, and Recovering Access

### 9.1. Preparing to Replace a Phone

Plan ahead before wiping your old device. Verify your account has an alternate verification path and identify an administrator who can assist. Transferring phone data does not prove your account's OMA binding works on the new phone.

Oracle instructs enrolling OMA on a new device or re-enrolling an existing device via a factor reset performed by an identity domain administrator, followed by re-enrollment. See [Registering New And Reregistering Existing Mobile Devices](https://docs.oracle.com/en-us/iaas/Content/Identity/mobileauthapp/registering_mobile_devices_with_oma.htm).

After re-enrolling, test a fresh sign-in session and update your notes on active factors and recovery options. Do not consider a device migration finished merely because the app installed successfully.

### 9.2. If a Phone Is Lost or the App Was Deleted

Proceed via whichever path remains available:

1. If you have an alternate factor or valid bypass code, use it to verify.
2. If a reset is needed, contact an administrator with permissions in the right domain; verify identity before requesting the reset.
3. After the reset, re-enroll your factor, test a fresh login, and review recovery methods.
4. If no usable administrative path remains, contact Oracle Cloud Support via official channels.

Oracle provides Live Chat guidance for Free Tier sign-in and MFA issues when unable to access the Console at [Troubleshooting Signing In to the Console — Contacting Support](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signinginIdentityDomain.htm). Support will require account-holder verification; do not assume instant recovery.

Resetting a user's factors is a sensitive operation. Do not process it based merely on an unverified message claiming to be the account owner, and do not disable MFA for the entire domain to resolve one person's issue.

### 9.3. Classifying Errors Before Acting

| Symptom | What to check |
| --- | --- |
| OTP rejected | Right account entry in the app, code still valid, device clock synchronized |
| No push received | Network connectivity, notification permissions, pending requests inside OMA; use alternate factor if available |
| Security or desired factor not visible | Right domain and self-service/MFA settings permitted by administrator |
| Sign-in succeeds but lacks permissions | Groups, roles, and IAM policies; do not reset MFA to fix authorization errors |
| Not prompted for extra factor | SSO session, trusted device state, IdP path, policy, and matching rule |
| Reset completed but old app still generates codes | Codes generated locally on the device do not prove server-side binding remains valid |
| Received an approval prompt you did not initiate | Deny the prompt, inspect the account, and notify the appropriate administrator |

Oracle covers clock sync, checking pending notifications, and switching to passcode in [Using the Oracle Mobile Authenticator](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/use-oracle-mobile-authenticator-app.htm).

## 10. Reducing Admin Privilege Usage in Everyday Labs

After securing and testing the administrator account, prepare lab users with permissions tailored to their needs. Someone who only needs to create Compute instances in a learning compartment should not default to full tenancy privileges for convenience.

Access division can be documented as follows:

| Access type | Purpose | Recommended usage |
| --- | --- | --- |
| Tenancy admin | IAM, foundational setup, billing, incident recovery | Use only when corresponding privileges are needed, with tested MFA and recovery |
| Lab user | Practice services within permitted scope | Permissions scoped by lesson and compartment, separate identity |
| Automation | Deploy or manage defined workloads | Dedicated credentials and permissions per environment |

This is a work-organization model; specific IAM policies are designed in the authorization lesson. Do not remove admin permissions from the active identity before verifying an alternate admin path. Reducing privileges must preserve your ability to administer and recover the tenancy.

Likewise, do not pre-create multiple API keys or privileged tokens just in case of an unspecified scenario. For every credential created, document its purpose, where it is used, its owner, and how to revoke it.

## 11. Monitoring Events After Setup

With appropriate permissions, inspect identity domain sign-in and audit reports to verify test timestamps. Useful events include successful/failed sign-ins, MFA factor enrollment, bypass code generation, and sign-on policy changes. Reports can show the matched rule and authentication level; see [Audit Log Report](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/audit-log.htm).

Use events as corroborating evidence for login tests. Match the exact user, timestamp, and protected resource; do not draw conclusions from an event belonging to a different session.

If you receive unexpected notifications about password changes, MFA resets, or recovery code generation, inspect your account from a verified Console URL. Record timestamps and relevant events before contacting an administrator; do not attach QR codes, OTPs, or bypass codes to support requests.

## 12. Practice Exercise and Completion Criteria

### Step 1 — Create an Environment Record

Use a secret-free template:

```text
Tenancy name:
Actual identity domain:
Admin username:
Sign-in path: local / external IdP
Policy applied to Console:
Verified policy status and rule scope:
Registered primary factor:
Prepared recovery path:
Fresh login test timestamp:
Authentication and required permission result:
Support person/channel if access is lost:
```

Do not enter passwords, QR keys, OTPs, bypass codes, private keys, or session tokens into this template.

### Step 2 — Complete Enrollment and Recovery Setup

Enroll a factor following the flow appropriate for your domain. Generate bypass codes if permitted and store them securely. Verify recovery information, support contacts, and the permission scope needed to handle loss of the primary authentication device.

### Step 3 — Test a Fresh Session

Sign in from a clean session in a supported browser, complete the additional factor, and confirm that necessary admin permissions remain intact. If testing an alternate path, record the result and replenish recovery material as needed. Only close the setup session after verifying that the new login path works.

### Step 4 — Record Verifiable Results

This exercise is complete when:

- The exact tenancy, identity domain, user, and MFA enforcement point are identified.
- The administrator account has enrolled a factor and completed verification testing.
- The policy applies properly to the Console sign-in flow, not merely showing enrollment status.
- A fresh sign-in session works with the expected authentication requirements.
- A recovery path exists and you understand its limits when a device is lost or a policy is misconfigured.
- Result documentation contains no authentication secrets and no unintended MFA exemptions remain.
- A plan exists to use lower-privilege identities for daily lab work.

These outcomes allow you to continue building an OCI environment with authorization and automation while keeping control over the initial administrator account.
