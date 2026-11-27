# Secret Management, Masking Test Data, and Avoiding Sensitive Data in Logs

## Objectives

A secure MySQL system must protect both credentials and the data flowing through the database. Passwords, tokens, encryption keys, personally identifiable data, and transaction details can leak through source code, configuration files, test copies, SQL statements, or logs. Consequently, security does not stop at granting the right privileges to accounts; development and operations teams must also control where secrets live, how test data is generated, and what gets logged.

This lesson belongs to the **DATABASE_MYSQL** module, which covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backups, and handling relational database operational issues. Within this scope, managing secrets and data safely ensures development, deployment, testing, monitoring, and backup workflows do not create additional data-leak paths.

After this lesson, you will be able to:

- Distinguish secrets from sensitive business data and identify where they can appear.
- Store and deliver MySQL credentials through an appropriate secret management mechanism.
- Plan password rotation without unexpected application downtime.
- Generate synthetic test data or mask copied data under controlled procedures.
- Design logs that support diagnostics without recording passwords, tokens, or personal data.
- Audit log sources, backups, and command histories that may contain sensitive data.

## 1. Identifying Secrets and Sensitive Data

**Secrets** are pieces of information capable of granting access or decrypting data, such as MySQL passwords, private keys, API tokens, backup account credentials, encryption keys, and deployment pipeline credentials. Anyone obtaining a secret can impersonate an identity or access the system.

**Sensitive data** is data whose viewing, usage, or sharing must be restricted—such as full names, emails, phone numbers, addresses, government IDs, payment details, health data, order contents, or internal records. This data may not directly grant login access, yet still causes harm if exposed.

Inventory data across each flow:

| Where It Appears | Examples | Primary Controls |
|---|---|---|
| Source code & config | Passwords in `.env` files, YAML, or connection strings | Never commit secrets; fetch from a secret manager at runtime |
| MySQL connections | Account, password, TLS certificates | Dedicated accounts, least privilege, TLS, and rotation |
| Production data | Customer details, transactions | Privilege control, encryption, access limits, and retention |
| Test/staging environments | Copies of real data | Use synthetic data or mask before moving into these environments |
| Logs & observability tools | SQL, bind values, stack traces, request payloads | Log only required fields, redact data, and restrict read access |
| Backups & exports | SQL dumps, binary logs, snapshots | Encryption, access control, retention limits, and deletion procedures |

Never treat logs or backups as harmless data. They can contain copies of table data, statements holding sensitive literals, or accidentally logged credentials.

## 2. Storing MySQL Connection Secrets

Never place real passwords in source code, repositories, Docker images, deployment scripts, shared documentation, or commands saved into shell history. Never use the `root` account for application connections. Create separate accounts per service and per environment, granting only the required privileges on the schemas or tables the service uses.

An example account setup:

```sql
CREATE USER 'inventory_app'@'10.30.4.21'
  IDENTIFIED BY '<value-injected-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE
  ON inventory.*
  TO 'inventory_app'@'10.30.4.21';
```

The bracketed string is a placeholder only, not a usable password. At deployment, the secret manager or orchestration platform injects the real value into the process based on an authenticated workload identity. The account can only connect from the expected host and must satisfy the server's TLS settings.

A secret manager should support workload-identity access control, audit logging of who or which service read a secret, secret versioning, rotation, and revocation. Grant secret-read access only to processes that need it. DBAs should not send passwords over chat or tickets, and operators should not paste secrets into logs for support convenience.

If infrastructure does not yet have a secret manager, a protected config file can serve as an interim step:

- Place the file outside repositories and outside publicly served directories.
- Restrict read permissions strictly to the OS account running the service; on Linux typically equivalent to `0600`, on Windows using matching ACLs.
- Exclude the file from shared images, unencrypted backups, and debug bundles.
- Maintain a workflow to replace the file, restart or refresh connection pools, and revoke the old version.
- Document clearly that this is a host-stored secret requiring protection and rotation like any other secret.

Avoid passing passwords directly as command-line arguments, such as `mysql -u inventory_app -pMyPassword`. Process arguments can appear in process lists, execution logs, or command history. Use `mysql -u inventory_app -p` for interactive prompting during manual tasks; for automated applications, fetch secrets from a protected delivery mechanism. Do not rely on general environment variables such as `MYSQL_PWD` to hold long-lived passwords, as process environments can be exposed through diagnostic tools or system configurations.

## 3. Rotating and Revoking Secrets

Secrets must be rotated when scheduled by policy, when personnel or services change access rights, upon signs of exposure, or if an environment is compromised. Rotation frequency should reflect risk level, automation capability, and operational readiness; never pick a fixed schedule without the ability to execute it safely.

A typical rotation workflow:

1. Identify all accounts, services, connection pools, background jobs, and operational tools using that secret.
2. Generate the new secret in the secret manager and prepare workload configuration updates.
3. Update the MySQL account or credential following a tested transition strategy.
4. Deploy the new secret, refresh connections, and confirm business flows work cleanly.
5. Check authentication logs and look for instances still using the old credential.
6. Revoke the old credential, confirm no new connections succeed with it, and record the change outcome.

MySQL 8.0.14 and later support dual passwords per account, enabling a two-phase credential cutover. Illustrative example:

```sql
-- Transition phase: the current password remains accepted
ALTER USER 'inventory_app'@'10.30.4.21'
  IDENTIFIED BY '<new-secret>' RETAIN CURRENT PASSWORD;

-- Once all clients have switched to the new secret
ALTER USER 'inventory_app'@'10.30.4.21'
  DISCARD OLD PASSWORD;
```

Substitute placeholder values through the secret management channel; never paste real passwords into tickets or deployment logs. Verify your MySQL version before using dual passwords. On versions lacking dual-password support, create a replacement account with the same privileges, shift workloads to the new account, verify operation, and then lock or drop the old account per procedure.

Do not confuse changing a password with revoking all existing access. Open connections may stay active; inspect connection pools and active sessions. During an incident, you may need to lock the account, terminate sessions, revoke related tokens, and review access logs in parallel.

## 4. Creating Safe Test Data

Prefer **synthetic data** generated specifically for testing. Synthetic data avoids carrying real customer information and can be crafted to cover edge cases such as null values, Unicode characters, long strings, refund transactions, or inconsistent states.

If a production copy is required to reproduce a bug, define the purpose and scope before extraction. Extract only the needed tables and columns; perform data masking inside a controlled zone before moving data into staging/test; restrict who can access it; encrypt in transit and at rest; and set a deletion deadline. Never copy an unmasked production dump first and simply hope the test environment is adequately protected.

Data masking replaces or transforms values so testers cannot see original data. Distinguish clearly:

- **Display masking:** the UI hides part of a value, such as showing only the last four digits. The original data still exists and anyone able to query directly can still read it.
- **Pseudonymization:** replaces identifiers with another code that can still be linked back, such as using tokens or a separately held mapping table. This remains protected data.
- **Anonymization:** transforms data so individuals can no longer be reasonably re-identified in the usage context. Dropping names or emails alone is often insufficient if remaining fields can be combined to re-identify someone.

## 5. Designing Masking Rules

Before transforming data, identify which test requirements must be preserved. A test dataset typically needs to preserve table structure, foreign keys, data types, lengths, value distributions, inter-record relationships, and edge cases. It does not need to preserve actual production values.

| Data Field | How to Create Test Data | What to Verify |
|---|---|---|
| Full name | Generate synthetic names from a mock dataset | Length, Unicode, empty/null values |
| Email | `CONCAT('user-', id, '@example.invalid')` | Unique, valid format, never sends real mail |
| Phone number | Use an internal reserved test number range | Never dials real people |
| Address | Generate mock addresses or coarsen to broad regions | No specific personal street addresses remain |
| Birth/transaction dates | Shift dates by a defined rule or generate fresh dates | Preserves ordering, intervals, and timezones needed for tests |
| Free-text content | Wipe, replace with synthetic text, or filter by rules | Avoid names, account numbers, or emails embedded in notes |
| Tokens/credentials | Replace with non-working dummy values | Never reuse production tokens |

When multiple tables reference the same customer, use the exact same pseudonymization key across every relationship under test to preserve referential integrity. If each table is transformed independently, logical foreign keys break and business bugs stop reproducing.

Simple example on an isolated test copy:

```sql
UPDATE customer
SET full_name = CONCAT('Test Customer ', id),
    email = CONCAT('user-', id, '@example.invalid'),
    phone = NULL;
```

Run this statement only on a confirmed test environment after taking a snapshot or ensuring recoverability. The example assumes columns `id`, `full_name`, `email`, and `phone`; adjust for your real schema. If other tables store emails or phone numbers for the same customers, mask those copies using consistent rules.

Do not use `SHA2(email, 256)` or unkeyed hashes as a default anonymization measure. Emails, phone numbers, and IDs often have small or predictable domains; an attacker can hash common candidates and compare digests. If stable linkage across datasets is needed, consider random tokens or keyed HMACs with a separately protected secret key, and still treat the output as controlled pseudonymized data.

Dates can be shifted by a per-individual offset to preserve intervals between events. However, shifted dates may still reveal behavioral patterns or link with external datasets. Keep only the temporal precision required for testing; consider rounding to day/week or generating fresh synthetic data.

## 6. Avoiding Sensitive Data in Application Logs

Logs should answer operational questions: which request failed, when, which service handled it, which error category occurred, and how long it took. Most cases do not require logging full payloads, SQL statements with interpolated values, or customer records.

Never write the following into standard logs:

- Passwords, access tokens, session cookies, private keys, or connection strings containing credentials.
- Full card numbers, security codes, banking details, or personal identifiers without an approved need.
- Full request/response payloads when they may contain personal data or secrets.
- Query text containing sensitive literals, returned row data, or dumps.
- Secrets inside exceptions, stack traces, environment variables, or driver-generated error messages.

Instead, log correlation IDs, request IDs, service names, operation types, error codes, durations, and internal identifiers assessed as safe. Example:

```json
{
  "event": "customer_lookup_failed",
  "request_id": "req-7f31",
  "service": "customer-api",
  "customer_ref": "cust-test-1042",
  "db_error_code": 1146,
  "duration_ms": 18
}
```

This example uses a mock reference ID and contains no email, name, password, or full SQL statement. Internal identifiers can still constitute personal data if they can be linked back; assess them against your organization's data classification policy.

## 7. Parameterized Queries and SQL Logging

Use prepared statements or parameterized queries in applications to separate SQL structure from input values. Never concatenate user data into SQL strings:

```sql
SELECT id, status
FROM orders
WHERE customer_id = ? AND created_at >= ?;
```

The driver passes values for placeholders via its API. At the application layer, log the operation name and normalized statement template; do not log bind values if they may hold sensitive data. Prepared statements also reduce SQL injection risk when used properly.

Parameterized queries do not guarantee that logs at every layer automatically redact values. Drivers, tracing agents, proxies, audit plugins, or log configurations may capture statements and parameters differently. Test actual behavior using dummy test data before enabling verbose logging.

MySQL has multiple observability sources with different purposes:

| Source | Data Risk | How to Operate |
|---|---|---|
| General query log | Can record received statements and literals | Enable only during investigations; restrict duration, read access, and storage |
| Slow query log | Can contain query text and values | Used for tuning; check logged fields and redact before sharing |
| Audit log/plugin | Can record identities, objects, and statements | Configure event filters, access controls, and appropriate retention |
| Error log | Can expose file paths, config details, or data from errors | Review messages, limit detail, and protect files |
| Performance Schema/tracing | Can store SQL text or statement details | Restrict viewers, retention, and collected data |
| Binary log/backups | Can contain data changes or full data copies | Treat as sensitive data; encrypt, control access, and enforce retention |

Do not leave the general query log enabled long-term just to gather extra visibility. When investigating, define the exact question to answer, enable the right log source for a short window, restrict who can read it, and disable or restore configuration afterward. Never assume MySQL or a plugin automatically masks all sensitive data across all versions and modes.

## 8. Protecting Logs, Backups, and Command History

Even when log contents are minimized, logs themselves require protection:

- Store logs in locations with least-privilege access; separate log-read rights from application admin rights when appropriate.
- Encrypt logs in transit to centralized logging systems and at rest.
- Set retention periods aligned with operational, investigative, and legal requirements; automatically purge expired logs.
- Restrict downloading logs to personal workstations or attaching them to tickets; if sharing is needed, filter and redact data first.
- Monitor unusual access and protect logs against unauthorized alteration or deletion.
- Re-audit logs whenever drivers, proxies, audit plugins, or tracing configs change, because logged fields can shift.

Backups, snapshots, SQL dumps, and binary logs must be protected at least as strictly as the original data. Encrypt backups, manage keys separately, restrict who can download or restore them, and test expiration deletion workflows. Never load a production dump file into a test environment prior to running a masking pipeline.

When using the MySQL client, note that interactive command history such as `.mysql_history` can retain statements and values typed by users. Avoid typing secrets directly inside SQL statements on shared terminals; control history file permissions and clear sensitive entries per OS procedures. Never enable broad debugging or packet capture in production without understanding what data may be captured.

## 9. Control Workflow Before Moving Data to Test or Enabling Logs

Before creating a test copy:

1. Define the testing purpose, exact tables/columns required, and authorized users.
2. Prefer synthetic data; if a real copy is required, obtain approval under the organization's data governance process.
3. Mask identifiers, free-text fields, tokens, and every copy of sensitive fields across related tables.
4. Verify foreign keys, uniqueness, data distributions, and edge cases after transformation.
5. Scan sample rows for leftover emails, phone numbers, tokens, or credential strings.
6. Grant access only to the test team and set an expiration date for the copy.

Before enabling or changing logging:

1. State the operational question the logs must answer.
2. List log sources, logged fields, and log destinations.
3. Use dummy data to verify actual logged content at every layer.
4. Configure filtering/masking, access permissions, encryption, and retention limits.
5. Enable only within the required scope and timeframe; assign an owner responsible for disabling or reviewing the setting.
6. After the investigation, inspect log files, downloads, and shared tickets to verify no unintended sensitive copies remain.

## 10. Hands-on Scenario

A development team needs to reproduce a customer order-filtering bug and wants to turn on the general query log to inspect the SQL queries. The production dump contains emails, phone numbers, and street addresses; the application also logs request payloads when errors occur.

Design a remediation workflow in steps:

- Create a structurally equivalent synthetic dataset; if a production copy is required, extract only relevant tables/columns and mask data before granting the team access.
- Maintain relationships across `customer`, `orders`, and `order_item` using the same reference-key substitution rule.
- Replace emails with `example.invalid` addresses, strip or replace phone numbers and addresses, and scrub free-text note fields.
- Update application logging to record `request_id`, operation type, error code, duration, and a mock customer reference; drop the payload.
- If the general query log is needed for investigation, enable it only for a bounded window using dummy data, restrict readers, and disable it once collection finishes.
- Audit slow logs, audit logs, tracing, binary logs, and downloaded files to confirm no out-of-scope real data remains.

**Completion criteria:** the team can still reproduce the bug and analyze queries, while the test environment contains no real personal identifiers and logs aid diagnostics without leaking secrets or sensitive payloads.

## Conclusion

Secret management, data masking, and secure logging must be designed together. Provision secrets by workload identity, store and rotate them through controlled workflows, prefer synthetic data for testing, mask all necessary copies of data, and log only fields needed for operations. In MySQL, treat the general log, slow log, audit log, Performance Schema, binary logs, backups, and command histories as potential sources of sensitive information; verify actual settings, restrict access, and enforce retention limits before use.
