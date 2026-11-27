# Data Classification, Read Access Controls, and Masking Sensitive Information

A Spring Boot application may encrypt data in databases and object storage yet still expose sensitive information if all support agents can read full customer profiles, APIs return unnecessary sensitive fields, or logs record raw requests. Data protection starts with three questions: **what data is sensitive, who truly needs to read it, and how much of it do they need to see**.

Three activities must work together: **data classification**, **read access control**, and **masking/removing sensitive information**. Classification clarifies the impact if data is exposed. Authorization limits which resources, rows, columns, or fields a principal can access. Masking, redaction, and tokenization reduce how much real data is displayed when business logic does not need the full value.

This lesson belongs to the **Data Protection** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with managed services from AWS, Azure, and Google Cloud, covering identity/permissions, storage, messaging, data, secret protection, testing, and evaluating differences across cloud providers. The focus of this lesson is designing data policies from collection through deletion, enforcing permissions at the API and data platform layers, and preventing leaks via responses, logs, caches, reports, and test environments.

## 1. Learning Objectives and Running Scenario

After this lesson, you will be able to:

1. Classify data by sensitivity, impact, and handling obligations.
2. Distinguish between data classification, sensitivity labels, data discovery, and authorization policies.
3. Design read permissions following least privilege, RBAC, ABAC, tenant, row, column, and field boundaries.
4. Distinguish between masking, redaction, pseudonymization, tokenization, hashing, and encryption.
5. Apply distinct response DTOs for users with different privilege levels in Spring Boot.
6. Use AWS, Azure, and Google Cloud capabilities for data discovery, permission filtering, and value masking.
7. Protect data across logs, traces, caches, events, exports, and non-production environments.
8. Test allowed access, denied access, and masked outputs.

Running scenario: `customer-service` manages customer profiles including name, email, phone number, address, national ID, transaction history, and support notes. Support agents need to verify customers but generally do not need to see full national IDs or phone numbers. Payment operators need certain additional fields; analysts only need de-identified data.

~~~mermaid
flowchart TD
    A["Data collection"] --> B["Classification and labeling"]
    B --> C["Define purpose, retention, and owner"]
    C --> D["Design permissions: principal / tenant / row / column"]
    D --> E["API and database enforce authorization"]
    E --> F["Mask / redact / tokenize by role"]
    F --> G["Responses, exports, logs, and analytics"]
    G --> H["Audit, access review, and retention deletion"]
~~~

**Classification indicates the level of protection data requires. Authorization decides who may read it. Masking decides which values are displayed.** These three practices are related, yet none replaces the others.

## 2. Classifying Data Before Designing Permissions

### 2.1. Impact-based classification

A simple model might use four tiers:

| Tier | Meaning | Examples | Recommended handling |
| --- | --- | --- | --- |
| **Public** | Approved for broad publication | User guides, published pricing tables | Integrity and version control |
| **Internal** | Internal organizational use only | Operational codes, internal process docs | Organization accounts only |
| **Confidential** | Exposure causes significant impact | Email, phone number, contracts, purchase history | Role/purpose-based access, encryption, auditing, masking |
| **Restricted** | Exposure causes severe harm or breaches obligations | Passwords, access tokens, encryption keys, full national IDs, highly sensitive payment data | Very few principals allowed, never logged, proper encryption, heightened controls and monitoring |

Tier names are just examples. Organizations must define criteria, owners, retention periods, and controls for each tier. Do not treat a `CONFIDENTIAL` label as a legal standard or assume it automatically satisfies regulatory obligations.

### 2.2. Classification by data category

| Category | Examples | Questions to ask |
| --- | --- | --- |
| Direct identifier | Full name, email, phone number, passport number | Does the full value need to be stored/displayed? |
| Indirect identifier | Date of birth, region, job title, postal code | Can combining multiple fields identify an individual? |
| Authentication secret | Passwords, API keys, access tokens, refresh tokens | Must it be stored? Can a secret manager replace it? |
| Financial | Account numbers, payment details, transactions | Who needs to read it? Is masking or tokenization required? |
| Health/special-category | Health records or data designated sensitive under applicable law | What are the legal basis, purpose, permissions, and retention? |
| Business confidential | Contract pricing, strategy, partner data | Which groups need to know? Are sharing restrictions required? |
| Technical sensitive | Private keys, private certificate material, connection strings | Can it be excluded from responses/logs and moved to secret/key management? |

A single data column can belong to multiple categories. For instance, a customer ID is not directly PII yet can become an indirect identifier when joined with another table.

### 2.3. Do not classify based on column names alone

Not every column named `email` holds a real email; nor is a `note` column always harmless. Examine:

- Actual contents and business context.
- Linkability with other data sources.
- Degree of individual identifiability or trade secret sensitivity.
- Impact if read, modified, lost, or unavailable.
- Intended consumers and access purpose.
- Legal, contractual, data residency, and retention obligations.

Free-text support notes can contain card numbers, OTP codes, or health information even when the schema merely declares a text column. Scan contents and establish rules for input, display, storage, and logging.

### 2.4. Data inventory and ownership

Maintain a minimal inventory for each dataset/table/object:

| Attribute | Example |
| --- | --- |
| Data asset | `customer_profile` |
| Owner | Customer Operations |
| Data steward | Data Governance Team |
| Classification | Confidential |
| Sensitive fields | `email`, `phone`, `national_id` |
| Purpose | Customer support and request handling |
| Consumers | Customer API, support portal, analytics |
| Storage | PostgreSQL, object storage |
| Retention | Per business/legal policy |
| Access policy | Support reads masked; compliance receives full access upon approval |
| Protection | TLS, at-rest encryption, row/column authorization, masking |
| Audit | Who read/exported, when, purpose, and outcome |

The inventory must be updated whenever schemas, data flows, APIs, consumers, or processing purposes change—not just scanned once at deployment time.

## 3. How Sensitivity Labels and Data Classification Differ

**Data classification** typically identifies the types of data contained in an asset, such as email addresses, passport numbers, bank accounts, or customer identifiers.

**Sensitivity labels** express sensitivity levels or handling rules in an enterprise context, such as Public, Internal, Confidential, or Highly Confidential.

**Data discovery** is the process of locating assets and detecting sensitive data within them. **Authorization** is the mechanism that enforces access permissions at runtime.

| Concept | Question answered | Example |
| --- | --- | --- |
| Discovery | Where is sensitive data located? | Finding buckets containing national IDs |
| Classification | What types of data does the asset contain? | The `national_id` column is a government identifier |
| Sensitivity label | What handling tier applies to the asset? | `Restricted` |
| Authorization | Which principal is allowed to read? | `support-agent` only reads profiles in assigned tenants |
| Masking | Which value does the reader see? | Displays `•••• 4821` instead of the full number |

A label only has teeth when paired with enforcement policies. Adding `Restricted` metadata to an object does not automatically block principals who hold `GetObject` permission. You still need IAM/bucket policies, database permissions, API authorization, and verification processes.

## 4. Principles for Designing Read Access

### 4.1. Least privilege and default deny

Each principal should receive only the permissions needed for its current task:

- Default deny unless an explicit allow rule applies.
- Grant permissions scoped by resource, action, data scope, and duration.
- Separate read, write, export, share, admin, and decrypt permissions.
- Prefer roles/groups rather than manually granting permissions to individual users.
- Review and revoke permissions when people change roles, leave teams, or complete assignments.
- Never grant broad permissions just to make 403 errors disappear during development.

For example, a support agent may view names and order statuses, while seeing only masked emails/phone numbers. A payment operator might need a payment token field; that does not mean they need to read support notes or full customer histories.

### 4.2. RBAC and ABAC

**RBAC (Role-Based Access Control):** permissions attach to roles, such as `support-agent`, `payment-operator`, `compliance-auditor`.

**ABAC (Attribute-Based Access Control):** decisions are evaluated using attributes of the principal, resource, action, and environment, for example:

- Principal belongs to the `support` team.
- Resource has a `tenantId` matching an authorized tenant.
- Record carries classification `Confidential`.
- Action is `read`.
- Request occurs during business hours or from a managed device.

RBAC is straightforward for coarse-grained roles; ABAC fits conditions based on tenant, region, classification, or business state. Both approaches can be combined.

### 4.3. Distinguishing permissions across layers

| Layer | Permission example | What to verify |
| --- | --- | --- |
| API endpoint | `customer:read` | Is the caller allowed to invoke this operation? |
| Resource/object | `customerId=123` | Does the caller have access to this specific record? |
| Tenant | `tenant_id` | Does the data belong to the current tenant? |
| Row | Orders in assigned region | Does the query filter to the right record subset? |
| Column | Exclude `national_id` | Do DB/queries/views restrict columns? |
| Field/API response | Return masked email only | Does the DTO omit unnecessary fields? |
| Export/report | Export approved data only | Are there separate permissions, auditing, and row limits? |
| Logs/traces | Never log PII/tokens | Does the logging pipeline enforce redaction and access control? |

Protecting an endpoint with a role is insufficient if a user can swap `customerId` in the URL and read another tenant's profile. Always enforce authorization at the object/tenant level.

### 4.4. Tenant isolation

Never take a tenant ID from the request body/query string and trust it directly. Tenant context must be derived from the authenticated principal or a verified delegation mechanism.

Repository query example:

~~~java
public interface CustomerRepository extends JpaRepository<Customer, UUID> {
    Optional<Customer> findByIdAndTenantId(UUID id, UUID tenantId);
}
~~~

Service:

~~~java
@Service
public class CustomerQueryService {
    private final CustomerRepository repository;
    private final CurrentTenant currentTenant;

    public CustomerQueryService(
            CustomerRepository repository,
            CurrentTenant currentTenant) {
        this.repository = repository;
        this.currentTenant = currentTenant;
    }

    @PreAuthorize("hasAuthority('customer:read')")
    public Customer findVisibleCustomer(UUID customerId) {
        UUID tenantId = currentTenant.requiredTenantId();

        return repository.findByIdAndTenantId(customerId, tenantId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));
    }
}
~~~

This example requires enabling method security with `@EnableMethodSecurity` and providing a `CurrentTenant` that extracts the tenant from the authenticated security context. Never allow clients to pass an arbitrary `tenantId` to cross data boundaries.

### 4.5. Row-level security in databases

For multi-tenant data, database Row-Level Security (RLS) can provide defense-in-depth against queries missing a tenant predicate. RLS does not replace application authorization; it acts as an additional safeguard.

Illustrative PostgreSQL example:

~~~sql
ALTER TABLE customer_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_profile FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_customer_read
ON customer_profile
FOR SELECT
USING (
  tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

The application must set tenant context safely within the same transaction/connection before querying—for instance via `SET LOCAL` or `set_config(..., true)` inside a transaction. With connection pooling, ensure a previous tenant's session variable never leaks into the next request. The application database role must not have owner/superuser privileges or `BYPASSRLS`, as those bypass policies. Test with the exact database role used in production.

## 5. Restricting Access at Row, Column, and Field Levels

### 5.1. Row-level access

Row-level access limits **which records** a principal can read.

Examples:

- Support teams only read customers in their assigned region.
- Tenant A cannot read Tenant B's rows.
- Agents only view tickets assigned to them.
- Analysts only view data belonging to approved business units.

This can be enforced at the database (RLS), data warehouse, API query layer, or multiple layers simultaneously. Never rely on UI filtering as a security measure; clients can call APIs directly or alter queries.

### 5.2. Column-level access

Column-level access limits **which fields** can be queried:

- Operations teams read `customer_id`, `status`, and `created_at`.
- Customer care teams read `name`, `email`, and `phone` subject to masking policies.
- Compliance teams are authorized to view certain sensitive fields upon approval.
- Analysts cannot access `national_id`, `payment_token`, or free-text notes.

Enforce via database grants, secure views, column policy tags, or data lake permissions. Check `SELECT *`, views, stored procedures, exports, and integrated query engines.

### 5.3. Field-level authorization in APIs

APIs should return DTOs tailored to the use case. Never directly serialize JPA entities containing all sensitive columns.

~~~java
public record CustomerSupportView(
        UUID id,
        String displayName,
        String maskedEmail,
        String maskedPhone,
        String accountStatus) {
}

public record CustomerComplianceView(
        UUID id,
        String displayName,
        String email,
        String phone,
        String nationalId) {
}
~~~

The service can cleanly separate permissions:

~~~java
@Service
public class CustomerViewService {

    @PreAuthorize("hasAuthority('customer:read')")
    public CustomerSupportView supportView(UUID customerId) {
        Customer customer = loadAuthorizedCustomer(customerId);

        return new CustomerSupportView(
                customer.getId(),
                customer.getDisplayName(),
                Masking.maskEmail(customer.getEmail()),
                Masking.maskPhone(customer.getPhone()),
                customer.getAccountStatus().name());
    }

    @PreAuthorize("hasAuthority('customer:read:restricted')")
    public CustomerComplianceView complianceView(UUID customerId) {
        Customer customer = loadAuthorizedCustomer(customerId);

        return new CustomerComplianceView(
                customer.getId(),
                customer.getDisplayName(),
                customer.getEmail(),
                customer.getPhone(),
                customer.getNationalId());
    }
}
~~~

`loadAuthorizedCustomer` must still verify tenant/object ownership. `customer:read:restricted` must be granted through an approval and auditing workflow. DTOs do not replace authorization; they ensure only authorized fields are actually serialized.

### 5.4. Do not rely on hiding fields in the UI

Hiding columns or replacing values with asterisks in the frontend does not protect an API if the JSON payload still returns full data. Any user can inspect the Network tab, invoke the endpoint directly, or download an export file.

Ensure the server only sends fields the recipient is authorized to view. Check response bodies, GraphQL resolvers, WebSocket events, search endpoints, and export files.

## 6. Masking, Redaction, Tokenization, and Pseudonymization

| Technique | How it works | Can original value be restored? | When to use |
| --- | --- | --- | --- |
| **Masking** | Replaces part or all of a value with placeholder characters | Usually not from the masked output | Support displays or reports |
| **Redaction** | Completely removes sensitive fields/segments from output | No, unless a separate original copy exists | Logs, shared documents, responses |
| **Static masking** | Produces a modified dataset copy before provisioning to another environment | Usually not | Test/dev, data sandboxes |
| **Dynamic masking** | Masks values at query/display time based on permissions | Original data remains intact | Support portals, database queries |
| **Pseudonymization** | Replaces identifiers with pseudonyms linkable via a mapping/key | Yes, if mapping/key is retained | Analytics, research |
| **Tokenization** | Replaces values with tokens; mappings live in a separate vault/service | Yes, via a controlled token service | Payment/account identifiers |
| **Hashing** | Produces a one-way digest | Not directly | Comparisons/lookups when properly designed |
| **Encryption** | Encrypts with a key | Yes, when holding the key | Storing/transmitting data that must be recoverable |

### 6.1. Partial masking

Examples:

| Original value | Displayed value |
| --- | --- |
| `phuong@example.com` | `p•••••@example.com` |
| `0901234821` | `••••••4821` |
| `4111111111111234` | `••••••••••••1234` |
| `AB1234567` | `•••••4567` |

Reveal only the portion needed for user verification. For some data types, even the last four characters can be sensitive; decide based on your threat model and applicable regulations.

### 6.2. Redaction

Redaction removes values from shared output:

~~~text
Request body:
{"email":"phuong@example.com","accessToken":"eyJ..."}

Redacted log:
{"email":"[REDACTED]","accessToken":"[REDACTED]"}
~~~

Redaction suits logs, error messages, support bundles, and externally shared documents. If the system still requires correlation, use a random request ID or a controlled surrogate identifier.

### 6.3. Pseudonymization and tokenization

Pseudonymization substitutes an identifier with a surrogate code:

~~~text
customerId: 8421 -> customerRef: CUST-7F2A
~~~

Mappings must be separately protected, access-restricted, and audited. If the same token appears across multiple datasets, recipients may correlate records; deterministic tokenization aids joins but increases linkability.

Tokenization typically uses a vault or dedicated mapping service. Do not store the mapping table in the same database/schema with the same read permissions as the tokenized data if the goal is reducing re-identification risk.

### 6.4. Hashing is not anonymization by default

Hashes of emails, phone numbers, or national IDs can be reversed via dictionary or brute-force attacks because the input space is small and structured. Unsalted hashes are also easy to correlate across systems.

- Use dedicated password hashing (Argon2id, bcrypt, or PBKDF2 per policy) for passwords.
- For identifiers needing deterministic lookup, consider a keyed HMAC with a protected key rather than a plain hash.
- If the original value must be recoverable, use tokenization or encryption with key management.
- Never claim data is anonymous merely because names were removed; combined fields can still re-identify individuals.

### 6.5. Encryption and masking serve different purposes

Encryption protects stored/transmitted values from anyone lacking the key; an application authorized to decrypt still sees plaintext. Masking restricts which values are shown in a given context; original data may still exist in the database. Both can be used together: encrypt at rest, authorize the reader, and then mask the response.

## 7. Masking in Spring Boot

### 7.1. Write purposeful masking functions

Simple example for email and phone:

~~~java
package com.example.customer;

public final class Masking {
    private Masking() {
    }

    public static String maskEmail(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }

        int at = value.indexOf('@');
        if (at <= 0 || at == value.length() - 1) {
            return "[REDACTED]";
        }

        String local = value.substring(0, at);
        String domain = value.substring(at + 1);
        return local.substring(0, 1) + "••••@" + domain;
    }

    public static String maskPhone(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }

        String digits = value.replaceAll("\\D", "");
        if (digits.length() < 4) {
            return "[REDACTED]";
        }

        return "••••••" + digits.substring(digits.length() - 4);
    }
}
~~~

This is a display example, not a library for every international format. Before masking, determine how data is normalized and whether recipients need country codes, extensions, or domains preserved. Never use masked outputs as primary identifiers or exact-match lookup keys.

### 7.2. Authorization first, masking second

A sound flow:

1. Authenticate the caller and resolve the tenant.
2. Check object/record read permissions.
3. Load only the permitted set of fields.
4. Select the response DTO matching permissions and purpose.
5. Mask fields that must be obscured.
6. Serialize the response.
7. Emit an audit event containing no plaintext.

Do not load the entire entity, log the entity, and only mask at the controller layer. Plaintext passing through intermediate components can end up retained.

### 7.3. Using method security

Enable method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Require a dedicated authority for restricted data:

~~~java
@PreAuthorize("hasAuthority('customer:read:restricted')")
public CustomerComplianceView readRestrictedProfile(UUID customerId) {
    // Verify tenant/object ownership before reading sensitive fields.
    return customerViewService.loadComplianceView(customerId);
}
~~~

The `customer:read:restricted` authority must come from a trusted identity provider/authorization server or policy engine. Never allow clients to assert roles or authorities via request headers.

### 7.4. Jackson and serialization

Do not treat `@JsonIgnore`, `@JsonView`, or a Jackson filter as complete authorization. They can help with serialization, yet data can still be exposed via other endpoints, logs, mappers, or internal code.

Prefer:

- Separate DTOs per use case.
- Explicit mapping from entity to DTO.
- Never serializing entities directly.
- Never returning raw database projections from controllers without reviewing every field.
- Testing actual JSON output to ensure sensitive fields are absent.
- Avoiding a single global serializer to mask all fields when different endpoints require different privileges.

## 8. Access Restrictions and Masking Across Cloud Providers

Cloud services can support discovery, classification, fine-grained access, or masking at various layers. They do not replace Spring Boot API authorization.

### 8.1. AWS: Macie, Lake Formation, and IAM

**Amazon Macie** helps discover sensitive data in Amazon S3:

- Maintains bucket inventories and evaluates security/access configurations.
- Uses automated sensitive data discovery or targeted discovery jobs to analyze objects.
- Identifies data types using managed identifiers and custom identifiers.
- Generates findings for security teams to investigate and remediate.

Macie is a discovery/monitoring tool; it does not automatically block reads on objects with findings. Act on findings using IAM, bucket policies, lifecycles, encryption, and remediation workflows.

**AWS Lake Formation** provides data filters to control data in the Data Catalog:

- Column-level filtering: grants only specific columns.
- Row-level filtering: returns only rows matching an expression.
- Cell-level filtering: combines row and column restrictions.
- Applies to integrated query engines such as Amazon Athena and Redshift Spectrum depending on service/region support.

Conceptual data filter example:

~~~json
{
  "Name": "support-orders",
  "DatabaseName": "sales",
  "TableName": "orders",
  "RowFilter": {
    "FilterExpression": "tenant_id='tenant-42'"
  },
  "ColumnWildcard": {
    "ExcludedColumnNames": ["national_id", "payment_token"]
  }
}
~~~

This illustrates the filter structure, not a complete ready-to-apply policy. Filters must be created via the Lake Formation API/console and `SELECT` granted to the target principal. Lake Formation data filtering applies only to supported engines/paths; direct S3 object access still requires IAM and bucket policies.

For Spring Boot applications reading S3 directly, use appropriate IAM roles/task roles/workload identities scoped to required buckets/prefixes and actions. Do not expect Lake Formation to automatically restrict direct `GetObject` calls from the SDK.

### 8.2. Azure: Microsoft Purview and SQL Dynamic Data Masking

**Microsoft Purview** supports data discovery/classification and sensitivity labeling across supported sources:

- Classification identifies data types such as personal names, license numbers, or account details.
- Sensitivity labels describe sensitivity tiers per organizational policy.
- Scanning/cataloging shows where data resides and who owns it.
- Labels/classifications are governance metadata; connect them to appropriate permissions, policies, and protection workflows.

Verify data sources, licensing, preview/GA status, and product roadmaps before choosing specific Purview features for a new system. Never assume a catalog label automatically blocks API reads.

**Azure SQL Dynamic Data Masking (DDM)** obscures values in query results for principals lacking permission to view unmasked data:

~~~sql
ALTER TABLE dbo.Customer
ALTER COLUMN Email
ADD MASKED WITH (FUNCTION = 'email()');

ALTER TABLE dbo.Customer
ALTER COLUMN Phone
ADD MASKED WITH (FUNCTION = 'partial(0, "XXXXXX", 4)');
~~~

Users granted read access without `UNMASK` receive masked output per the policy. `UNMASK` can be granted at database/schema/table/column scope depending on supported versions and syntax.

~~~sql
GRANT UNMASK ON dbo.Customer (Email) TO CustomerComplianceReader;
~~~

DDM **does not alter data stored in the table** and does not block privileged access: administrative principals such as server admins, Entra admins, or `db_owner` can still see original data. DDM reduces exposure for non-privileged query users; database permissions, row/column security, and admin access controls are still required.

### 8.3. Google Cloud: Sensitive Data Protection and BigQuery

**Sensitive Data Protection** inspects, classifies, and de-identifies data in text, storage, and certain data platforms:

- Built-in infoType detectors and custom detectors.
- Redaction and replacement.
- Partial value masking.
- Crypto-based tokenization/pseudonymization.
- De-identification for analytics datasets or application payloads.

Choose transformations according to requirements. Redaction removes data; masking replaces part of the characters; tokenization can be reversible if keys/mappings are retained. Never assume every transformation fully anonymizes data.

**BigQuery** supports multi-level access controls:

- IAM at project/dataset/table levels.
- Row-level security to filter rows by policy.
- Column-level access control using policy tags to restrict sensitive columns.
- Data masking policies for users allowed to query while seeing only masked values in supported configurations.

Illustrative row access policy example:

~~~sql
CREATE ROW ACCESS POLICY region_support
ON `analytics-prod.sales.orders`
GRANT TO ("group:support-north@example.com")
FILTER USING (region = "north");
~~~

Syntax and principal identifiers must match your actual project, dataset, table, and groups. Policy tags must be attached to columns with corresponding taxonomy permissions; tagging alone is insufficient without data policies and proper IAM.

### 8.4. Quick comparison

| Need | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Discovering sensitive data | Amazon Macie for S3 | Microsoft Purview and SQL discovery/classification | Sensitive Data Protection |
| Row-level access | Lake Formation data filters/RLS for integrated engines | Database RLS and applicable data service policies | BigQuery row-level security |
| Column-level access | Lake Formation column filters | SQL permissions/views and service capabilities | BigQuery policy tags |
| Dynamic masking | Depends on query/data service; Lake Formation filters perform access filtering, not value masking | Azure SQL Dynamic Data Masking | BigQuery data masking policies |
| De-identification/tokenization | Appropriate app/service and KMS | Appropriate app/Key Vault or service | Sensitive Data Protection transformations |
| API authorization | IAM role for workload + Spring Security/API policy | Managed Identity/Entra ID + Spring Security/API policy | Workload Identity/service account + Spring Security/API policy |

## 9. Protecting Logs, Traces, Events, and Error Responses

An application can protect its database yet inadvertently create plaintext copies in log aggregators, tracing backends, message queues, or support bundles.

### 9.1. Data that should never be logged directly

Generally never log:

- Passwords, access tokens, refresh tokens, API keys.
- Private keys, encryption keys, connection strings.
- Payment card numbers, national IDs, full dates of birth.
- Full emails/phone numbers without a clear purpose and authorization.
- Request/response bodies containing PII or restricted data.
- SQL bind parameters containing sensitive data.
- Full entities/DTOs or exception messages containing payloads.

You can log pseudonymized actor IDs, internal resource IDs, request IDs, actions, classifications, outcomes, policy decisions, and correlation IDs.

Example:

~~~java
log.info(
        "customer_read actorRef={} customerRef={} view={} outcome={}",
        actorReference,
        customerReference,
        "SUPPORT_MASKED",
        "ALLOWED");
~~~

Never log full customer objects just for debugging convenience. Audit logs need enough context for investigation while respecting the logging system's own classification.

### 9.2. Redact before logging

Do not rely on a log aggregator to mask data after collection. Once raw PII enters collectors, buffers, disks, or third-party telemetry, the data has already been copied.

- Log only allowlisted fields.
- Use structured logging instead of interpolating whole objects into messages.
- Redact request headers such as `Authorization`, cookies, and API keys.
- Disable body logging on endpoints receiving sensitive data.
- Check exceptions, validation errors, and SQL logging.
- Restrict log read access and retention.
- Test log output with sentinel data to catch leaks.

### 9.3. Tracing and metrics

Distributed tracing can automatically capture URLs, headers, query parameters, and exceptions. Never put emails, tokens, or account numbers into span attributes. Metric labels must not contain user IDs or sensitive values, as that both leaks data and creates high cardinality.

### 9.4. Events and dead-letter queues

Message brokers often retain payloads for retries, replay, or error handling. If events contain PII:

- Include only the fields consumers need.
- Consider tokens/references instead of full payloads.
- Scope permissions separately for topics/subscriptions and DLQs.
- Apply retention, encryption, and auditing.
- Mask data in events destined for analytics.
- Never put secrets or authentication tokens into messages.
- Control replay/export permissions because they enable bulk data extraction.

## 10. Caches, Search, Exports, and Non-Production Environments

### 10.1. Caches can leak data across users

If caching responses masked by user permissions, the cache key must incorporate the tenant, principal/role, or view type appropriately. If the cache key is only `customerId`, a full response cached for a high-privilege user could be served to a low-privilege user.

Principles:

- Authorization must be checked before returning a cache hit.
- Never share the same cache entry between full and masked views without explicit partitioning.
- Tenant must be part of both the cache key and lookup path.
- Set TTLs aligned with permission revocation and data update timelines.
- Invalidate caches when roles/permissions change.
- Never cache restricted plaintext longer than necessary.

### 10.2. Search indexes

Search engines create copies of database data. Classification and read controls must extend to the index:

- Exclude sensitive fields from the index if searching on them is unnecessary.
- If lookup is required, use controlled tokens/keyed hashes.
- Never return snippets/highlights containing fields the caller cannot read.
- Enforce tenant filters and authorization on every query.
- Restrict exports, autocomplete, suggestions, and debug endpoints.

### 10.3. Exports and reports

Exports carry high risk because they create durable files that can be downloaded and shared. Require:

- Dedicated export permissions rather than inheriting record-read permissions by default.
- Limits on row counts, fields, tenants, and time ranges.
- Masking or omitting fields per classification.
- Auditing who generated the export, its purpose, scope, and who downloaded it.
- Expiring download links with re-verified access permissions.
- Retention policies and cleanup of temporary files.
- Protecting downloaded files commensurate with their sensitivity.

### 10.4. Test and staging data

Never copy a raw production database into dev and rely on internal networking for protection.

- Use synthetic data whenever possible.
- Apply static masking before creating non-production snapshots.
- Tokenize or pseudonymize identifiers when join relationships must be preserved.
- Preserve distributions/formats needed for tests without keeping real values.
- Inspect data in backups, objects, logs, and events after creating test copies.
- Restrict permissions and retention for non-production copies.

## 11. Retention, Deletion, and Data Minimization

Classification must tie directly into the data lifecycle:

1. Collect strictly for the stated purpose and only required fields.
2. Assign an owner, classification, retention period, and access policy.
3. Store in locations with proper permissions and protections.
4. Share only with consumers having an approved purpose.
5. Mask/de-identify when moving data to analytics, support, or testing.
6. Delete or anonymize when purpose/retention expires, per legal and contractual obligations.
7. Verify copies across caches, indexes, exports, events, backups, and replicas per policy.

Never keep data "just in case we need it later" without a defined purpose, legal basis, and expiration. Backups have their own retention schedules; deletion workflows must explicitly describe how backups/archives are handled within service capabilities.

## 12. Testing Classification, Permissions, and Masking

### 12.1. Role matrix

Draft a permission matrix before writing tests:

| Actor | Same-tenant profile | Cross-tenant profile | Email/phone | National ID | Export |
| --- | --- | --- | --- | --- | --- |
| Support agent | Read | Denied | Masked | Field absent | No |
| Payment operator | Payment-required fields only | Denied | Purpose-scoped | Field absent | No |
| Compliance reader | Per approved scope | Per approved scope | Full if approved | Full if approved | With audit/approval |
| Analyst | De-identified dataset | Per dataset policy | Tokenized/removed | Removed | Approved dataset |
| Anonymous | Denied | Denied | Absent | Absent | No |

The matrix must match policies across the IdP, Spring Security, databases, cloud storage, and data warehouses.

### 12.2. Positive and negative authorization tests

Test:

- Support reads a same-tenant record and receives the masked DTO.
- Support switching `customerId` to another tenant is denied or receives 404 per anti-enumeration policy.
- Support cannot invoke restricted endpoints.
- Payment operator reads only required fields.
- Compliance reader requires specific permissions and actions are audited.
- Anonymous/expired identities cannot access data.
- Tenant context does not bleed across connection pools or async executors.

Do not check HTTP status alone; verify the response body contains no sensitive fields even when an endpoint returns 200.

### 12.3. Masking and serialization tests

Unit test example:

~~~java
@Test
void masksEmailForSupportView() {
    assertThat(Masking.maskEmail("phuong@example.com"))
            .isEqualTo("p••••@example.com");
}

@Test
void masksPhoneAndKeepsOnlyLastFourDigits() {
    assertThat(Masking.maskPhone("0901234821"))
            .isEqualTo("••••••4821");
}
~~~

Beyond unit tests, serialize DTOs and inspect the JSON:

- No `nationalId`.
- No original email/phone.
- No access tokens or unnecessary internal key references.
- No fields hidden merely because the frontend does not display them.

### 12.4. Testing database and cloud policies

- Execute queries using the exact runtime database role; verify RLS.
- Use a principal lacking `UNMASK` to confirm Azure SQL returns masked results.
- Use a BigQuery principal lacking policy tag permissions to verify columns are blocked/masked and row policies filter correctly.
- For Lake Formation, test queries via the integrated engine with a principal granted the filter.
- Confirm Macie findings trigger remediation/actions; do not assume findings block access by themselves.
- Test IAM/bucket policies directly when Spring Boot calls object storage.

### 12.5. Testing logs, caches, and exports

- Send sentinel requests containing fake emails/tokens; assert logs contain no raw values.
- Read a masked response then switch roles; ensure the cache does not serve the wrong view.
- Test cache keys across two tenants; ensure no cross-tenant hits occur.
- Exports must enforce the same authorization/masking as APIs.
- DLQs, traces, and error responses must not contain restricted payloads.
- Verify retention and deletion of test data.

## 13. Troubleshooting Common Issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| UI masks email but API returns full email | Frontend-only masking | Mask/omit fields in the server response |
| User reads another tenant's records | Missing object/tenant authorization | Tenant-scoped queries and database RLS |
| `SELECT *` exposes sensitive columns | Overly broad DB role or missing column policy | Grant per column/view, reduce privileges |
| Azure DDM still returns plaintext | Caller holds `UNMASK` or elevated admin role | Review roles, `UNMASK` scope, and admin principals |
| BigQuery user sees every row | Row access policy unattached or IAM principal too broad | Check policies, principals, and table permissions |
| Lake Formation filter has no effect | Unintegrated query engine/path or caller has direct S3 access | Check engine, Lake Formation grants, and IAM/S3 access |
| Macie detects PII but objects remain readable | Macie is discovery/monitoring, not enforcement | Remediate via IAM, bucket policies, and workflows |
| Logs contain request bodies | Logging interceptor/trace capture too broad | Allowlist log fields, disable body logging, redact before collector |
| Cache serves full data to support | Cache key fails to distinguish roles/views | Partition caches or cache data per privilege level |
| Tokenized data can still be re-identified | Mapping/token key leaked or deterministic tokens overused | Protect vaults/keys, limit linkability and re-identification rights |
| Staging data still contains real PII | Masking skipped on backups/exports/indexes | Audit entire data flow and rebuild non-production datasets |

## 14. Comprehensive Hands-On Exercise

`customer-service` stores multi-tenant profiles in PostgreSQL and object storage. The application runs on Spring Boot, uses one cloud provider for object storage, and a data warehouse for analytics.

Data includes name, email, phone, national ID, address, payment token, support notes, and order history.

**Tasks:**

1. Classify each field as Public/Internal/Confidential/Restricted and document owner, purpose, and retention.
2. Design a role matrix for support, payment, compliance, analyst, and anonymous users.
3. Ensure queries always filter tenants using the authenticated identity; consider database RLS.
4. Build `CustomerSupportView` with only required fields and masked email/phone.
5. Create a restricted endpoint with dedicated permissions, auditing, and tenant/object ownership checks.
6. Design redaction for logs, traces, exceptions, and DLQs.
7. Produce a tokenized or de-identified analytics dataset; restrict re-identification permissions.
8. Compare discovery, row/column policies, and masking capabilities of the AWS, Azure, or Google Cloud services in use.
9. Write positive/negative tests for tenant isolation, `UNMASK`, column policies, caching, exports, and logs.
10. Establish an access review and retention-based deletion procedure.

**Self-assessment questions:**

- How does classification differ from authorization?
- Why does a sensitivity label not automatically block an API from reading data?
- Why should a tenant ID never be trusted if taken only from a query parameter?
- What two problems do row-level security and column-level security solve?
- How does dynamic masking differ from encryption and static masking?
- Why is hashing an email not anonymization by default?
- Does Macie automatically block `GetObject` when it detects PII?
- Why does Azure SQL DDM not replace database authorization?
- What parts of data do BigQuery policy tags and row-level security control?
- Why must cache keys account for tenant and permissions?
- Why should raw requests never be logged and masked only later in a log aggregator?

**Guided answers:** classification describes sensitivity and data types while authorization decides which principal may read; labels are merely metadata until tied to enforcement; tenant must come from authenticated identity; RLS limits rows while column security limits columns; DDM masks query outputs while original data stays intact; identifier hashes can be brute-forced; Macie discovery is not enforcement; DDM does not block privileged principals; policy tags restrict columns while row policies filter rows; caches must partition by tenant/view; redaction must happen before data enters the logging pipeline.

## 15. Official References

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): data not to log, masking/sanitization, log read access, and retention.
- [Amazon Macie – Discovering sensitive data](https://docs.aws.amazon.com/macie/latest/user/data-classification.html): automated discovery and targeted discovery jobs for S3.
- [Amazon Macie – Monitoring data security and privacy](https://docs.aws.amazon.com/macie/latest/user/monitoring-s3.html): bucket inventory, access/security findings, and sensitive data findings.
- [AWS Lake Formation – Data filtering and cell-level security](https://docs.aws.amazon.com/lake-formation/latest/dg/data-filtering.html): row-level, column-level, and cell-level filtering.
- [AWS Lake Formation – Row-level security policies](https://docs.aws.amazon.com/lake-formation/latest/dg/rls-policies.html): policy filters and interaction with column permissions.
- [Microsoft Purview – Data classification](https://learn.microsoft.com/azure/purview/concept-classification): system/custom classifications and distinguishing classification from sensitivity labels.
- [Azure SQL – Dynamic Data Masking](https://learn.microsoft.com/en-us/azure/azure-sql/database/dynamic-data-masking-overview): masking query results, granular `UNMASK`, and limitations of DDM.
- [Google Cloud – Sensitive Data Protection overview](https://docs.cloud.google.com/sensitive-data-protection/docs/sensitive-data-protection-overview): inspecting, classifying, and de-identifying data.
- [Google Cloud – De-identify and re-identify sensitive data](https://docs.cloud.google.com/sensitive-data-protection/docs/inspect-sensitive-text-de-identify): pseudonymization/tokenization and re-identification.
- [Google Cloud – BigQuery row-level security](https://docs.cloud.google.com/bigquery/docs/row-level-security-intro): filtering rows by user/group.
- [Google Cloud – BigQuery data masking and policy tags](https://docs.cloud.google.com/bigquery/docs/column-level-security-intro): column controls and masking in queries.

**Remember:** data classification provides the foundation for deciding permissions and presentation; permissions must be enforced at the server/data layer; masking must occur before data enters responses, logs, caches, or exports. A well-protected system not only keeps data encrypted, but ensures **the right person, for the right purpose, within the right scope, sees the right level of detail**.
