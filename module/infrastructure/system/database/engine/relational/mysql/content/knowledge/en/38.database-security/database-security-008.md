# Password Policies, Account Locking, Expiration, and Password Rotation

In MySQL, password-based account protection consists of multiple coordinated layers: verifying password quality, preventing reuse of old passwords, setting expiration lifetimes, locking logins after repeated failed authentication attempts, and rotating credentials when needed. Each layer addresses a different risk. Merely enabling a complexity policy cannot replace restricting privileges, encrypting connections, managing secrets, and monitoring login activity.

This lesson belongs to the **DATABASE_MYSQL** module and focuses on administering MySQL in real-world environments: controlled configuration, applying policies by account category, verifying status, and handling operational scenarios. Examples use MySQL 8.0 syntax. Some features have specific version milestones; verify your server version before deploying.

## 1. Distinguishing Password Management Mechanisms

| Mechanism | Question Addressed | MySQL Tooling |
|---|---|---|
| Password strength | Is the password long enough and hard to guess? | **validate_password** component |
| History and reuse | Is a user cycling back to an old password? | **password_history**, **password_reuse_interval** |
| Current password | When changing passwords, must the user confirm the current password? | **password_require_current** |
| Expiration | After how long must the password be replaced? | **default_password_lifetime**, **PASSWORD EXPIRE** |
| Failed-login lockout | After how many failed authentication attempts should the account be locked? | **FAILED_LOGIN_ATTEMPTS**, **PASSWORD_LOCK_TIME** |
| Administrative lock | Does login access for the account need to be disabled immediately? | **ACCOUNT LOCK**, **ACCOUNT UNLOCK** |
| Rotation | How do you replace a secret while minimizing application downtime? | **ALTER USER**, dual password mechanism |

These mechanisms are not synonymous. Password expiration requires the user to change the password; account locking blocks logins; and rotation is the process of replacing a secret and updating the systems that consume it.

### Version Differences to Know

- Password history and current-password requirement policies are supported in the MySQL 8.0 series; account-level configurability depends on the specific release.
- Dual passwords are supported starting in MySQL 8.0.14.
- **FAILED_LOGIN_ATTEMPTS** and **PASSWORD_LOCK_TIME** are supported starting in MySQL 8.0.19.
- MySQL 8.0 supports the **component_validate_password** component; older releases may use the **validate_password** plugin. Installation and management differ between the two forms.

On the running server, check first:

~~~sql
SELECT VERSION();
SHOW VARIABLES LIKE 'default_password_lifetime';
SHOW VARIABLES LIKE 'password_history';
SHOW VARIABLES LIKE 'password_reuse_interval';
SHOW VARIABLES LIKE 'password_require_current';
SHOW VARIABLES LIKE 'validate_password%';
~~~

Do not assume every variable or option exists on every MySQL build. If a statement reports an unknown variable or unsupported syntax, consult the documentation for your exact version and your system's upgrade policy.

## 2. Configuring Password Strength Requirements

The **validate_password** component checks passwords when creating an account or changing a password. It can enforce length, uppercase letters, lowercase letters, digits, special characters, and dictionary checks. This component helps reject weak passwords, though it cannot guarantee by itself that a password is unique across services or has never been leaked.

On MySQL 8.0, you can install the component with the following statement if not already installed:

~~~sql
INSTALL COMPONENT 'file://component_validate_password';
~~~

Inspect current settings:

~~~sql
SHOW VARIABLES LIKE 'validate_password%';
~~~

Example configuring a strong policy:

~~~sql
SET PERSIST validate_password.policy = 'STRONG';
SET PERSIST validate_password.length = 14;
SET PERSIST validate_password.mixed_case_count = 1;
SET PERSIST validate_password.number_count = 1;
SET PERSIST validate_password.special_char_count = 1;
SET PERSIST validate_password.check_user_name = ON;
~~~

Meaning of the parameters:

- **validate_password.policy** selects **LOW**, **MEDIUM**, or **STRONG**. The **STRONG** level adds dictionary checks when a dictionary file is configured.
- **validate_password.length** sets the minimum length.
- **mixed_case_count**, **number_count**, and **special_char_count** define minimum counts for their respective character groups.
- **check_user_name** requires the password not to contain the username according to the component's matching rules.

The values above are starting examples only. Organizations must weigh application compatibility, password entry workflows, and security requirements. A long, unique, randomly generated password or a sufficiently long passphrase is often more valuable than forcing users to vary characters according to a predictable pattern.

**SET GLOBAL** changes values while the server is running without saving them across the next restart. **SET PERSIST** saves values so MySQL reloads them after restart. In infrastructure-managed environments, update configuration in the authoritative configuration source, record the approver, and verify status after deployment. Do not run global configuration statements directly on production without assessing impact.

If using an older MySQL release with the plugin instead of the component, follow the plugin installation instructions for your OS and version. Do not mix instructions for the component and the plugin.

## 3. Preventing Password Reuse

If users can cycle back and forth among a few familiar passwords, expiration policies lose effectiveness. MySQL provides two mechanisms to restrict this:

- Password history: rejects a number of most recently used passwords.
- Password reuse interval: rejects passwords used within a specified time period.

Server-wide defaults can be set:

~~~sql
SET PERSIST password_history = 5;
SET PERSIST password_reuse_interval = 365;
SET PERSIST password_require_current = ON;
~~~

Example applying explicit policies to an account:

~~~sql
CREATE USER 'analyst'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_A_SECRET'
  PASSWORD HISTORY 5
  PASSWORD REUSE INTERVAL 365 DAY
  PASSWORD REQUIRE CURRENT;
~~~

The account name, host, and policy values must be tailored to your system. The password string in the example is a placeholder only, not a password to deploy. Never place real secrets in source code, documentation, tickets, or shared command histories.

**PASSWORD REQUIRE CURRENT** requires supplying the current password when changing passwords according to the mechanism supported by client and server. You can use **PASSWORD REQUIRE CURRENT OPTIONAL** or **PASSWORD REQUIRE CURRENT DEFAULT** to choose different behavior as needed. This option must be tested against the application's password-change flow; an automated password changer may not have the current-password context.

History policies do not replace generating sufficiently strong passwords. Nor do they make a compromised secret safe. When password exposure is suspected, replace it immediately and audit where the secret was stored or used.

## 4. Setting Password Expiration

The global variable **default_password_lifetime** specifies the default lifetime in days. A value of **0** means passwords do not automatically expire by default. For example, setting a 180-day default:

~~~sql
SET PERSIST default_password_lifetime = 180;
~~~

You can set an individual lifetime when creating or altering an account:

~~~sql
CREATE USER 'report_reader'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_A_SECRET'
  PASSWORD EXPIRE INTERVAL 90 DAY;

ALTER USER 'report_reader'@'10.20.%'
  PASSWORD EXPIRE INTERVAL 90 DAY;
~~~

Three common options:

~~~sql
-- Follow the server's default lifetime
ALTER USER 'report_reader'@'10.20.%' PASSWORD EXPIRE DEFAULT;

-- Do not automatically expire this account's password
ALTER USER 'service_worker'@'10.20.%' PASSWORD EXPIRE NEVER;

-- Mark the password as expired immediately
ALTER USER 'temporary_user'@'localhost' PASSWORD EXPIRE;
~~~

Accounts with **PASSWORD EXPIRE NEVER** are not governed by the server's default lifetime. Therefore, when setting a global policy, review account-level exceptions. Do not inadvertently set **NEVER** on highly privileged user accounts.

Password expiration can cause outages if an account is used by applications, background jobs, connection pools, or backup processes. Before applying it, identify the account owner, where the secret is stored, the update workflow, and how to test connections after rotation. Service accounts require a coordinated rotation process; setting a short expiration cycle without an automated secret update process frequently brings down systems.

## 5. Locking Accounts After Repeated Failed Logins

Starting in MySQL 8.0.19, you can configure the number of consecutive failed authentication attempts before automatically locking an account and the lock duration in days.

~~~sql
CREATE USER 'app_login'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_A_SECRET'
  FAILED_LOGIN_ATTEMPTS 5
  PASSWORD_LOCK_TIME 1;

ALTER USER 'app_login'@'10.20.%'
  FAILED_LOGIN_ATTEMPTS 5
  PASSWORD_LOCK_TIME 1;
~~~

In the example, the account is locked after five consecutive failed login attempts for a lock duration of one day. **PASSWORD_LOCK_TIME** is measured in days. Use **UNBOUNDED** if an administrator must unlock the account manually:

~~~sql
ALTER USER 'sensitive_admin'@'10.20.%'
  FAILED_LOGIN_ATTEMPTS 3
  PASSWORD_LOCK_TIME UNBOUNDED;
~~~

Locking due to failed logins differs from proactive administrative locking. When new logins must be stopped immediately, an administrator can lock the account:

~~~sql
ALTER USER 'app_login'@'10.20.%' ACCOUNT LOCK;
~~~

Unlock after verifying the root cause:

~~~sql
ALTER USER 'app_login'@'10.20.%' ACCOUNT UNLOCK;
~~~

Locking an account blocks new authentication attempts. It does not automatically terminate previously established connections. If existing sessions must also be stopped, identify and terminate those connections separately per operational procedures while considering the impact on in-flight transactions.

Setting thresholds too low can lock out legitimate users due to typos or let an attacker deliberately cause disruption by triggering lockouts. Choose thresholds and lock durations based on account sensitivity, login patterns, user support capacity, and alerting mechanisms. For critical administrative accounts, maintain a controlled emergency unlock procedure.

## 6. Rotating Passwords Safely

Password rotation is the process of replacing an active secret with a new secret, updating storage locations, and verifying every dependent component. Common situations requiring rotation include:

- A secret reaches its scheduled rotation interval per internal policy.
- Personnel owning or managing the secret change roles.
- Signs indicate the secret was leaked, shared improperly, or logged.
- Applications, environments, or service providers change.

For human accounts, verify the requester and use the organization's approved password-reset flow. For service accounts, coordinate updates across the secret manager, application configurations, connection pools, background workers, and relevant deployments.

### Using Dual Passwords to Minimize Disruption

Starting in MySQL 8.0.14, an account can temporarily retain both its current password and a new password. This is useful when updating secrets across multiple applications that cannot switch over simultaneously.

**Step 1: set the new password while retaining the current password**

~~~sql
ALTER USER 'app_login'@'10.20.%'
  IDENTIFIED BY 'NEW_SECRET_FROM_SECRET_MANAGER'
  RETAIN CURRENT PASSWORD;
~~~

**Step 2: update the secret manager and deploy applications**

Store the new secret in the approved vault, update application instance configurations, reinitialize or refresh connection pools according to your workflow, and verify logins and required queries. Monitor authentication errors to catch instances still using the old secret.

**Step 3: discard the old password after verification**

~~~sql
ALTER USER 'app_login'@'10.20.%' DISCARD OLD PASSWORD;
~~~

After this statement, the old password is no longer accepted. Run it only after confirming all dependent components have switched to the new password and having a remediation plan ready if verification fails.

Dual passwords are a temporary transition window, not a reason to keep multiple secrets indefinitely. Time-box the transition window, record who performed it, and close the window with **DISCARD OLD PASSWORD**.

### Emergency Rotation When Exposure Is Suspected

When a secret is compromised, prioritize blocking unauthorized access and replacing the secret as quickly as possible. Depending on incident severity, you may lock the account first, identify active sessions, update the secret in the secret manager, change the password, roll out the new configuration, and unlock the account after verification. If service continuity must be preserved, plan a controlled transition and minimize the time the old password remains valid.

Do not merely change the password and close the incident. Inspect login logs, source addresses, timestamps, account privileges, anomalous queries, and where the secret may have leaked. If the account holds overly broad privileges, narrow them according to least privilege.

## 7. Checking Status and Verifying Policies

**SHOW CREATE USER** displays configured account attributes:

~~~sql
SHOW CREATE USER 'app_login'@'10.20.%'\G
~~~

The output may include encrypted or hashed credentials and sensitive configuration data. Only authorized personnel should view it; never copy raw output into tickets or broadly shared documents.

Administrators can inspect selected statuses from **mysql.user**:

~~~sql
SELECT
  user,
  host,
  account_locked,
  password_expired,
  password_last_changed,
  password_lifetime,
  failed_login_attempts,
  password_lock_time
FROM mysql.user
WHERE user = 'app_login';
~~~

Columns and read permissions may vary by version and configuration. This query is strictly for inspection; never update system tables directly to modify policies. Use **CREATE USER**, **ALTER USER**, and MySQL-supported administrative statements to modify accounts.

After applying a policy, verify with a low-privilege test account:

1. Create a test account with the intended policy.
2. Attempt to set or change to a weak password to confirm strength checks work.
3. Attempt to reuse an old password in the test environment.
4. Test expiration behavior and the password reset flow.
5. Attempt failed logins within a controlled test to confirm lockout behavior.
6. Confirm a locked account cannot open new connections and can be unlocked via proper procedure.
7. For dual passwords, confirm both secrets work during the transition window, then confirm the old password is rejected after discarding it.

Never deliberately trigger account lockouts or expire production accounts just to test. Use staging or approved test accounts.

## 8. Handling Common Scenarios

### Client Reports Password Has Expired

MySQL may reject normal operations and require changing the password before continuing. Use the approved password reset flow. With the MySQL CLI client, depending on version and configuration, the **--connect-expired-password** option allows connecting in an expired-password state to change the password. Do not disable expiration server-wide just to handle one account.

### Legitimate User Is Locked Out

Verify the exact **user** and **host** pair, identify the source of failed logins, inspect application and connection pool configs, and then wait out the lock duration or run **ACCOUNT UNLOCK** per procedure. If errors come from an application instance still holding an old password, fix the configuration source before unlocking so the account does not lock out again.

### New Password Is Rejected

Check **validate_password** policy, length, character classes, username checks, and dictionary settings. If the password is rejected due to history or reuse interval, check **password_history** and **password_reuse_interval**. Do not hastily lower global policies; pinpoint the exact rule causing the error and handle it at the narrowest scope.

### Application Loses Connectivity After Rotation

Verify that the secret manager holds the updated secret version, all instances loaded the new configuration, connection pools are not still using old credentials, and the account is not locked or expired. If still inside a dual-password window and the old password is retained, it can serve as a temporary fallback per the incident plan. Once resolved, finish discarding the old password.

## 9. Combining Password Policies with Account Protection

Password policies are only one part of MySQL security. A solid operational configuration should combine:

- Separate accounts per person or application; avoid shared administrative accounts.
- Source host restrictions matching networks that genuinely require access, rather than allowing connections from everywhere.
- Least privilege by job role; avoid application accounts with **SUPER** or broad administrative privileges when unnecessary.
- Mandatory TLS connections when authentication data traverses untrusted networks; consider client certificates for sensitive systems.
- Storing passwords in a secret manager, restricting who and what processes can read them, logging change history, and keeping secrets out of source code and logs.
- Monitoring failed logins, account lockouts, account changes, and policy changes.
- Procedures to revoke or lock accounts immediately when personnel, applications, or integrations no longer require access.
- Testing backups and recovery per procedure; protect backups at the same level as production data.

Not every account needs the same policy. Personal administrative accounts, application accounts, reporting accounts, and temporary accounts have different lifecycles and authentication patterns. Design policies by account category, assign owners, and review exceptions periodically.

## 10. Recommended Rollout Workflow

Before changing production, inventory accounts, owners, allowed hosts, dependent applications, current privileges, expiration status, and rollback plans. Categorize accounts into human, service, administrative, and temporary accounts.

Next, test the configuration in a test environment running the same MySQL version. Verify application compatibility with password expiration, confirm password-reset flows, measure lockout impact, and rehearse rotation. Finalize thresholds, intervals, exceptions, and who is authorized to unlock accounts.

During rollout, make changes in small batches, record before-and-after configs, verify application logins, and monitor authentication errors. Assign an on-call owner to handle locked accounts or expired passwords. After completion, review exception accounts and remove exceptions that are no longer justified.

Operational checklist:

- [ ] Verified MySQL version and supported features.
- [ ] Chosen an appropriate strength policy and tested it in a test environment.
- [ ] Configured password history and reuse rules as required.
- [ ] Decided expiration lifetimes per account category and reviewed exceptions.
- [ ] Configured failed-login lockout with sensible thresholds and durations.
- [ ] Assigned responsibility for unlocking accounts and handling auth incidents.
- [ ] Established secret rotation workflows for applications and connection pools.
- [ ] Verified logs, account privileges, TLS, and secret storage locations.
- [ ] Documented changes and prepared a tested rollback plan.

## Conclusion

Effective MySQL password management requires coordinating strength policies, history, expiration, login lockouts, and rotation procedures. Apply policies by account category, verify version compatibility, test first in a safe environment, and validate all dependent applications after every change. A policy only has value when users and systems can comply while maintaining stable operations and secrets are always stored and replaced under control.
