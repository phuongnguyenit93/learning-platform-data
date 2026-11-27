# Data De-identification, Masking, and Tokenization

Systems on Google Cloud often need to use real data for analytics, testing, customer support, or model training. However, real data can contain names, emails, phone numbers, addresses, identification numbers, financial details, or health information. If every user and every environment accesses these values directly, the risk of data leakage and misuse increases.

**De-identification**, **masking**, and **tokenization** are techniques that reduce the ability to link data back to an individual or lower the sensitivity of shared values. They operate differently and provide different levels of protection. Some techniques discard the original information, some retain partial information so users can still work, and some allow restoring the original value when a protected key or mapping table is available.

In the CLOUD_PROVIDERS_GCP module, this topic connects to IAM, Cloud Storage, BigQuery, Dataflow, Cloud KMS, and data governance workflows. Google Cloud provides Sensitive Data Protection (formerly known as Cloud Data Loss Prevention or Cloud DLP) to detect and transform sensitive data. BigQuery also offers column-level access control policies and query-time data masking. Choosing the right technique must start from the intended data use, whether reversibility is required, re-identification risk, and the access permissions of each user group.

After this lesson, you will be able to:

- Distinguish de-identification, anonymization, pseudonymization, masking, and tokenization.
- Select appropriate transformations for emails, phone numbers, dates of birth, account numbers, and analytical data.
- Use Sensitive Data Protection to inspect and transform content containing sensitive information.
- Design deterministic or reversible tokens using cryptographic keys or mapping vaults.
- Apply data masking and column-level security in BigQuery.
- Build a de-identification pipeline with key management, IAM controls, and re-identification risk checks.

## 1. Distinguishing Key Concepts

### De-identification

De-identification is the process of transforming data to reduce or remove attributes that can directly identify an individual. For example, a dataset supporting analytics might replace names with pseudonyms, mask phone numbers, generalize dates of birth into age bands, and drop detailed street addresses.

De-identification is typically a collection of techniques. The output may still preserve useful attributes such as age groups, broad regions, or transaction types. Therefore, de-identification does not automatically mean the data is completely anonymized. An individual can still be inferred from the remaining combination of attributes or by cross-referencing another data source.

### Anonymization and Pseudonymization

- **Anonymization:** transforming data so that individuals can no longer be identified using means reasonably likely to be used in the processing context. This is a strong objective; auxiliary data, linkability, and the access environment must all be evaluated.
- **Pseudonymization:** replacing direct identifiers with pseudonyms or surrogate values. Data can still be linked back to an individual if a key, mapping table, or supplementary information remains.

For example, replacing `customer@example.com` with `CUST-8F21` is pseudonymization if another system still stores the mapping from `CUST-8F21` back to the original email. Removing names and emails is not sufficient for anonymization if the record still contains an exact date of birth, a small postal code, and a rare transaction history.

### Masking

Masking replaces all or part of a value with masking characters, fixed strings, or transformed values. For example:

| Original Value | Masking Approach | Illustrative Output |
|---|---|---|
| `lan.nguyen@example.com` | Replace with data type label | `[EMAIL_ADDRESS]` |
| `0901234567` | Partially mask digits | `******4567` |
| `Nguyen Thi Lan` | Mask name | `N*************` |
| `1988-04-23` | Keep year only | `1988-01-01` or `1988` depending on rule |
| `123456789012` | Keep last four digits only | `********9012` |

Masking is typically suitable for support interfaces, logs, reports, or environments where users only need partial information. Masking data in a displayed result does not mean the original data has been altered or deleted from the source.

### Tokenization

Tokenization replaces a sensitive value with a token used across other systems. For example, a payment card number is replaced with `tok_7d91a2`. Analytics applications can use the token as a join key without knowing the real card number.

Tokenization has two common models:

1. **Token vault:** a system generates a random token and stores the token–original value pair in a separate mapping vault. Recovering the original value requires querying the vault under controlled permissions.
2. **Cryptographic tokenization:** uses a keyed cryptographic transformation to produce a replacement value. Some tokenization methods produce the same output for the same input; authorized users with the appropriate key can recover the original value via supported decryption workflows.

Tokens can be generated randomly or deterministically. Deterministic tokens allow joining records for the same customer across multiple systems, but also expose linkability of customer activity. Random tokens reduce linkability when each generation yields a different value, though joining data requires a vault or a separate identifier mechanism.

## 2. Choosing a Technique by Objective

No single transformation fits every data field. First determine what data recipients need to do and whether recovering the original value is required.

| Technique | Output | Reversible? | Suitable Scenario |
|---|---|---|---|
| Redaction / replace with label | Drops sensitive value or replaces with data type | No | Sharing sample data, removing unnecessary fields |
| Character masking | Masks a portion of characters | Not from masked output | Support UIs, confirming an account |
| Generalization / bucketing | Converts exact values into groups or ranges | Cannot recover exact value | Analysis by age band, income bracket, geographic region |
| Date shifting | Shifts dates by a controlled interval | Not without shift metadata; can preserve date intervals | Preserving time intervals in test or analytics data |
| One-way hash | Generates a fixed fingerprint from a value | Not decryptable; low-entropy inputs can be guessed | Matching or deduplication when anti-enumeration design is used |
| Deterministic encryption | Same input and context produce the same ciphertext | Yes, with key and decryption workflow | Consistent record linkage requiring controlled recovery |
| Format-preserving encryption (FPE) | Ciphertext retains configured character set and length | Yes, with appropriate key | Legacy systems requiring fixed format or length |
| Token vault | Random token pointing to original value in mapping store | Yes, via vault | Payments, customer identity, and multi-system integration |

### Quick Selection Rules

- If users only need to know sensitive data was present, replace with a data type label or redact the value.
- If only partial verification is needed, mask unnecessary characters.
- If analytics only need trends, generalize values into broader groups, ranges, or time buckets.
- If records must be joined without reading original values, consider deterministic tokens or keyed hashes.
- If business processes require recovery, use a token vault or keyed encryption alongside access controls and audit logging.

Do not use plain unsalted hashes for emails, phone numbers, or identifiers with small value spaces. Attackers can precompute hashes of common values and match them. Keyed hashing (HMAC) or keyed tokenization mitigates dictionary guessing, though keys and matching permissions still require protection.

## 3. Detecting Sensitive Data with Sensitive Data Protection

Sensitive Data Protection is Google Cloud's managed sensitive data service, previously commonly known as Cloud DLP. The service can inspect content, detect information using built-in or organization-defined `infoType` detectors, evaluate likelihood levels, and apply transformations.

Common infoTypes include:

- `EMAIL_ADDRESS`: email addresses.
- `PHONE_NUMBER`: phone numbers.
- `PERSON_NAME`: person names.
- `CREDIT_CARD_NUMBER`: payment card numbers.
- `US_SOCIAL_SECURITY_NUMBER`: US Social Security numbers.
- Other infoTypes for dates, addresses, accounts, and identifiers per the supported catalog.

The infoType catalog depends on language and data type. For internal data such as customer IDs, contract codes, or employee IDs, custom infoTypes using regular expressions, dictionaries, or custom rules may be required. Do not assume a built-in infoType accurately recognizes every format used by your organization.

### Inspect and De-identify Workflow

1. Identify the data source, types of information to detect, and processing purpose.
2. Configure `inspectConfig`: infoTypes, minimum likelihood, exclusion rules, and context conditions if needed.
3. Submit content to Sensitive Data Protection or create an inspection job for a supported data source.
4. Evaluate findings, match counts, and false positive/false negative rates on a representative sample.
5. Configure `deidentifyConfig` to select transformations per infoType or per data field.
6. Write transformed outputs to a location with appropriate access permissions and verify original data does not leak into logs or unintended outputs.

Sensitive Data Protection supports two core operation groups:

- **Inspect:** locates and classifies sensitive data. This operation does not modify source data.
- **De-identify:** applies configured transformations to content or data fields.

For small payloads, the `content:inspect` and `content:deidentify` APIs can be invoked directly within application flows. For large datasets in Cloud Storage or BigQuery, use inspection jobs, job triggers, templates, and supported data processing integrations. Choose synchronous vs. job-based execution based on data size, latency requirements, quotas, and cost.

### Commonly Used Transformations

| Transformation | Behavior | Notes |
|---|---|---|
| `replaceWithInfoTypeConfig` | Replaces value with a label such as `[EMAIL_ADDRESS]` | Useful when preserving data category metadata |
| `redactConfig` | Deletes detected content | Reduces output data; may remove context |
| `characterMaskConfig` | Masks selected characters | Must define mask character count and masking direction |
| `cryptoHashConfig` | Produces a keyed hash | Irreversible; still assess linkability and value guessing |
| `cryptoDeterministicConfig` | Keyed deterministic encryption | Reversible; same input/context produces consistent output |
| `cryptoReplaceFfxFpeConfig` | Format-preserving encryption per configuration | Use only when format retention is truly needed and domain size is assessed |
| `dateShiftConfig` | Shifts dates by a configured range | Choose consistent context if preserving date relationships for an individual |
| `bucketingConfig` | Converts numbers into ranges | Reduces precision while preserving analytical value |
| `timePartConfig` | Retains selected time components | Suitable when only year, month, or day of week is needed |

Transformations can be applied by infoType or by record field. For structured data, map each field explicitly and define separate rules for columns with different meanings. Some fields such as transaction IDs may need to stay intact for reconciliation, whereas names and phone numbers must be removed or tokenized.

## 4. Hands-On: Masking Emails and Phone Numbers in Content

The following example uses `content:deidentify` to replace emails with the `[EMAIL_ADDRESS]` label and mask part of a phone number. This illustrates a small text payload; for tables or large files, use the processing mechanism suited to your data source.

### Step 1: Enable the API and Set Project

~~~bash
export PROJECT_ID="data-protection-prod"

gcloud services enable dlp.googleapis.com --project="$PROJECT_ID"
~~~

The calling account needs permissions to use Sensitive Data Protection in the project. In production environments, use the workload's service account with least-privilege IAM and never store access tokens in source code.

### Step 2: Prepare the Request

The JSON request below illustrates detecting emails and phone numbers, replacing emails with the infoType label, and masking the first six characters of phone numbers:

~~~json
{
  "inspectConfig": {
    "infoTypes": [
      { "name": "EMAIL_ADDRESS" },
      { "name": "PHONE_NUMBER" }
    ],
    "minLikelihood": "POSSIBLE",
    "includeQuote": false
  },
  "deidentifyConfig": {
    "infoTypeTransformations": {
      "transformations": [
        {
          "infoTypes": [{ "name": "EMAIL_ADDRESS" }],
          "primitiveTransformation": {
            "replaceWithInfoTypeConfig": {}
          }
        },
        {
          "infoTypes": [{ "name": "PHONE_NUMBER" }],
          "primitiveTransformation": {
            "characterMaskConfig": {
              "maskingCharacter": "*",
              "numberToMask": 6,
              "reverseOrder": false
            }
          }
        }
      ]
    }
  },
  "item": {
    "value": "Contact Lan via lan.nguyen@example.com or 0901234567."
  }
}
~~~

Save the request in a protected file, such as `request.json`. Do not put real customer data into shell history, public examples, or logging systems. Tune `minLikelihood` using real sample data; too low a threshold produces many false positives, while too high a threshold may miss real data.

### Step 3: Call the API

~~~bash
curl -X POST \
  "https://dlp.googleapis.com/v2/projects/${PROJECT_ID}/locations/global/content:deidentify" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  --data-binary @request.json
~~~

In the response, the `item.value` field contains the transformed content. Illustrative output:

~~~text
Contact Lan via [EMAIL_ADDRESS] or ******4567.
~~~

This example illustrates a single payload. Inspect the actual API response, findings, and output data before putting a configuration into a pipeline. If part of an email or phone number needs to be preserved, adjust masking rules and test across varied formats.

### Step 4: Verify Output and Protect Data

- Confirm emails and phone numbers are processed properly with no original values left in the output.
- Test formats containing spaces, country codes, hyphens, and missing values.
- Check for false negatives (missed sensitive data) and false positives (normal text misidentified).
- Write processed outputs only to shared areas; restrict access to the raw zone.
- Do not log requests containing raw data or sensitive responses in application logs.

## 5. Reversible Tokenization and Deterministic Tokens

Tokenization is useful when multiple systems need to share a surrogate identifier. For example, support, analytics, and reporting systems can all use `customer_token` to join transactions without storing real emails or account numbers.

### Token Vault

In the vault model, a dedicated service generates random tokens and stores the mapping:

~~~text
Source system
   |
   | real account number
   v
Tokenization service
   |--------------------> Token vault (token <-> original value)
   |
   v
tok_7d91a2
   |
   v
BigQuery / reporting / analytics applications
~~~

The vault must be protected like a sensitive data store: separate project or security boundary, encryption, strict IAM, audit logging, purpose-bound access control, and lookup rate limiting. Only services with a valid business need should be allowed to call detokenization. Never share a copy of the vault with analytics teams.

The advantage of random tokens is that they reveal no mathematical relationship to the original value. The tradeoff is that the vault becomes critical for availability, backup, recovery, and access control. If the mapping is lost, recovering original values may become impossible.

### Cryptographic Tokenization

Sensitive Data Protection supports cryptographic transformations such as deterministic encryption and format-preserving encryption. Keys can be managed via Cloud KMS and the service's key configurations. When using Cloud KMS-protected keys, the Sensitive Data Protection service agent needs permissions to use the CryptoKey as required by the transformation.

**Deterministic encryption** produces stable ciphertext for the same input value and same context. This enables joining records across datasets, while allowing anyone viewing tokens to see which records share the same value. If the same key is reused across multiple purposes or data domains, unintended cross-domain linkability risk rises.

**Format-preserving encryption (FPE)** preserves character structure or length within a selected alphabet. For example, a numeric-only code can be transformed into a numeric string of the same length. FPE does not automatically guarantee strong security: small value domains, predictable structures, or known plaintexts can weaken protection. Use it only when target systems strictly require that format and the algorithm is supported by the service.

A one-way hash is not a reversible token. If stable linkage is needed without decryption, consider keyed hashing. If recovery is required, choose a vault or keyed encryption and establish clear decryption authorization workflows.

### Context and Linkage Scope

With certain deterministic encryption schemes, a context can limit the domain in which a token is meaningful. For instance, the same email can produce different tokens per tenant or per processing purpose. This reduces cross-system data linkage, though encryption and decryption steps must agree on the exact context.

Do not place directly identifying information into the context if it will appear in logs or metadata. Clearly define who manages contexts, how they are versioned, and how applications reuse contexts to prevent decryption errors.

## 6. Data Masking in BigQuery

BigQuery supports column-level access control and data masking. These can be combined:

- **Column-level security with policy tags:** restricts which user groups can read sensitive columns.
- **Data masking policies:** returns masked or transformed values to users granted masked-reader access.
- **Authorized views or standard views:** exposes a processed subset of fields and expressions to a specific user group.
- **Row-level access policies:** restricts which rows users can view; this is row-level control and does not replace column masking.

Data masking policies are applied at query time. Users with appropriate permissions see masked values while users authorized to read raw data see original values per policy. Data stored in the source table is not overwritten by dynamic masking.

### Example Creating a View Showing Masked Data

A view is a simple option to illustrate publishing processed data. The example below displays only part of the email and the last four digits of the phone number:

~~~sql
CREATE OR REPLACE VIEW `analytics.customer_support_view` AS
SELECT
  customer_id,
  CONCAT(
    SUBSTR(email, 1, 1),
    '***@',
    SPLIT(email, '@')[SAFE_OFFSET(1)]
  ) AS email_masked,
  CONCAT('******', RIGHT(phone_number, 4)) AS phone_masked,
  DATE_TRUNC(date_of_birth, YEAR) AS birth_year_group
FROM `restricted_raw.customers`;
~~~

The view above is illustrative only and assumes `email` and `phone_number` have valid formats. In production, handle `NULL` values, malformed emails, and phone numbers with country codes. Grant permissions on the view and source dataset according to least privilege; if using an authorized view, grant only the permissions required for the view to read the source table.

A hand-written view is not equivalent to BigQuery's dynamic data masking policy feature. When centralized column- and role-based masking governance is needed, configure data policies and policy tags per BigQuery documentation. Test both users who should see masked data and users authorized to see raw data. Do not grant permissions on the source dataset to groups that only need view access.

### Choosing BigQuery Masking vs. De-identification Before Storage?

| Need | Recommended Approach |
|---|---|
| Different users need different detail levels in the same table | Data masking policies and column-level security |
| Need to produce a shared dataset with identifiers removed or transformed | De-identify before writing to target dataset or bucket |
| Need mock data for development and testing | Generate synthetic data or a de-identified copy; do not assume masked views suffice |
| Need to link customers across tables without exposing identifiers | Tokenize with a vault or key-managed deterministic encryption |
| Need to restrict users by region, organization, or record group | Row-level access policies, combined with masking if needed |

## 7. Data Processing Architecture on Google Cloud

A de-identification pipeline should separate raw data, transformed data, and consumption zones:

~~~mermaid
flowchart LR
    A[Applications / Cloud Storage / BigQuery] --> B[Restricted-access raw zone]
    B --> C[Sensitive Data Protection]
    C --> D[Inspect and evaluate findings]
    D --> E[De-identify / masking / tokenization]
    E --> F[De-identified curated zone]
    F --> G[BigQuery / reporting / Dataflow / ML]
    H[Cloud KMS and IAM] --> C
    H --> I[Token vault if recovery needed]
    E --> I
~~~

Components must be designed together:

1. **Raw source:** Cloud Storage, BigQuery, or operational systems. Restrict which users and service accounts can read original data.
2. **Inspection:** Sensitive Data Protection inspects infoTypes and records results in alignment with audit requirements.
3. **Transformation:** apply rules by field, infoType, and intended purpose. Do not apply the same transformation to every field.
4. **Curated zone:** store only data necessary for analytics or sharing. Apply appropriate IAM, retention, and partitioning.
5. **Consumer:** BigQuery, Dataflow, dashboards, or ML workloads receive only appropriately processed data.
6. **Key management:** Cloud KMS protects keys used for cryptographic transformations; a token vault manages mappings when recovery is needed.

For large or near-real-time pipelines, Dataflow can orchestrate reading, transforming, and writing data while invoking Sensitive Data Protection APIs in line with throughput and quotas. Design retries, dead-letter handling, concurrency limits, and idempotency so data is neither lost nor unexpectedly double-processed.

## 8. Key Management, IAM, and Auditing

### Separation of Duties

- **Data owner:** decides which fields are processed, intended usage, and how much detail to retain.
- **Privacy/security administrator:** approves rules, detection thresholds, transformations, and retention periods.
- **Pipeline service account:** only reads the required raw zone, calls APIs, and writes to the curated zone.
- **Key administrator:** manages CryptoKeys, key versions, rotation, and IAM permissions.
- **Data consumer:** accesses only processed or role-masked datasets.

Do not grant raw data read permissions to the entire analytics team for deployment convenience. Scope permissions at the project, dataset, bucket, table, or column level depending on the resource type.

### Protecting Tokenization Keys

For cryptographic transformations, keys should be managed in Cloud KMS under appropriate lifecycle policies. Grant key usage permissions only to the required service agent or workload identity on the exact CryptoKey. Never place raw keys in source code, public environment variables, repository config files, or logs.

When rotating keys, understand the impact on existing tokens. Tokens generated using older key versions may still require those versions for recovery. Rotation plans must preserve readability of older data, support token re-encryption if needed, and include recovery testing. Disabling or destroying a key version while data still depends on it can permanently prevent decryption.

### Auditing and Monitoring

Monitor at a minimum:

- Who reads raw data, who calls inspect/de-identify, and who reads the curated zone.
- Changes to templates, infoTypes, transformations, and likelihood thresholds.
- Who generates tokens, who requests re-identification, or who queries the token vault.
- IAM changes on buckets, datasets, data policies, policy tags, and CryptoKeys.
- API errors, quota usage, processing times, finding counts, and transformation rates.
- Instances where raw data appears in logs, temporary copies, or shared zones.

Do not write full finding contents or plaintext values into application logs unless necessary. Store summary statistics, finding types, counts, and correlation IDs to enable investigation without leaking sensitive data.

## 9. Assessing Re-identification Risk

A dataset stripped of names and emails can still identify individuals if sufficiently distinctive attribute combinations remain. For example, exact birth date, gender, small postal code, and clinic visit date can form a rare combination. Anyone holding auxiliary data from public sources or other systems can cross-reference and deduce identities.

Risk mitigation measures:

- **Data minimization:** retain only fields genuinely needed for the defined purpose.
- **Generalization:** reduce granularity of age, dates, locations, and occupation categories.
- **Suppression:** remove records or attributes that are too rare to protect via generalization.
- **Aggregation:** publish aggregate figures instead of individual records when individual-level data is unnecessary.
- **K-anonymity:** assess whether every combination of quasi-identifiers appears in at least k records.
- **L-diversity and distribution checks:** evaluate diversity of sensitive attributes within each equivalence class, avoiding groups with many records that all reveal the same sensitive attribute.
- **Linkage testing:** test cross-referencing processed data against auxiliary sources recipients could access.

K-anonymity and l-diversity are risk analysis tools, not absolute guarantees. Consider release context, group sizes, auxiliary data, repeated query capabilities, and previously published information.

### Example: Customer Dataset for Analytics

| Original Field | Analytics Purpose | Recommended Treatment |
|---|---|---|
| customer_id | Join transactions of the same customer | Tenant- or purpose-scoped deterministic token |
| full_name | Not needed for analytics | Remove or replace with label |
| email | Only need user grouping | Drop or tokenize if record linkage is required |
| phone_number | Support staff need to confirm account | Mask in UI; exclude full number from analytics dataset |
| date_of_birth | Analysis by age band | Convert to age band or birth year |
| postal_code | Regional analysis | Generalize to broader region |
| transaction_amount | Revenue analysis | Keep amount if needed, or bucket when only distribution is needed |
| transaction_timestamp | Trend analysis | Round to day/week if exact timestamp is unnecessary |

These rules create a dataset useful for analytics while reducing direct identifiers. Before sharing, check whether the combination of `age_group`, `region`, and `transaction_date` renders any customer unique.

## 10. Common Errors and Troubleshooting

| Symptom | Possible Cause | Troubleshooting Direction |
|---|---|---|
| Sensitive Data Protection misses data | Unsuitable infoType, proprietary format, or likelihood threshold too high | Create custom infoType, add context rules, and test with representative samples |
| Too many false positives | Threshold too low or overly broad detection rules | Raise threshold, use hotword/exclusion rules, and test samples |
| API call denied | API not enabled or principal lacks IAM | Check API, project, location, and service account permissions |
| Encryption returns key error | Wrong key resource, inactive key version, or missing KMS permission | Verify CryptoKey, version status, and service agent permissions |
| Unable to recover token | One-way hash used, vault lost, or mismatched context | Verify transformation type; restore vault/key version or supply matching context |
| Unexpected identical tokens across systems | Same key or context reused across multiple domains | Separate keys/contexts by tenant, environment, or purpose |
| Users still see raw data in BigQuery | Direct read permission on source dataset/table or masking policy not applied | Check IAM, policy tags, data policies, and direct access paths |
| Processed dataset can still identify individuals | Quasi-identifiers remain or auxiliary data permits linkage | Apply generalization, suppression, aggregation, and linkage testing |

## 11. Pre-Sharing Checklist

- [ ] Defined purpose, recipients, and usage duration for the data.
- [ ] Classified direct identifiers, quasi-identifiers, and sensitive attributes.
- [ ] Selected masking, generalization, hashing, tokenization, or redaction per requirement.
- [ ] Tested Sensitive Data Protection on representative data and measured false positives/false negatives.
- [ ] Checked edge-case formats, NULL values, and multilingual data.
- [ ] Separated raw and curated zones; granted raw access only to principals strictly needing it.
- [ ] Protected keys with Cloud KMS or a token vault; governed rotation and recovery.
- [ ] Verified BigQuery policy tags, data policies, views, and direct access permissions.
- [ ] Checked logs, temporary copies, exports, and data in development environments.
- [ ] Evaluated re-identification risk with auxiliary data and linkage testing.
- [ ] Recorded template versions, configurations, and approvers for reproducibility.

## 12. Conclusion

De-identification, masking, and tokenization help organizations derive value from data while reducing exposure of sensitive information. Masking fits when users only need to see partial values; tokenization fits when surrogate identifiers or record linkage are needed; irreversible transformations fit when recovering original data is unnecessary. Sensitive Data Protection aids in detecting and transforming data, BigQuery provides query-time access control and masking layers, and Cloud KMS protects keys for cryptographic transformations.

A sound workflow starts by defining the purpose before picking a technique, restricts access to raw data, tests detection accuracy, secures keys, and evaluates re-identification risk. De-identified data must still be governed according to its usage context and organizational data protection requirements.

## References

- [Sensitive Data Protection documentation](https://cloud.google.com/sensitive-data-protection/docs)
- [Inspect and de-identify sensitive data](https://cloud.google.com/sensitive-data-protection/docs/inspecting-and-risk-analysis)
- [De-identification transformations](https://cloud.google.com/sensitive-data-protection/docs/deidentify-sensitive-data)
- [De-identify and re-identify content](https://cloud.google.com/sensitive-data-protection/docs/deidentify-reidentify)
- [BigQuery data masking introduction](https://cloud.google.com/bigquery/docs/column-data-masking-intro)
- [BigQuery column-level security](https://cloud.google.com/bigquery/docs/column-level-security-intro)
- [Cloud KMS documentation](https://cloud.google.com/kms/docs)
