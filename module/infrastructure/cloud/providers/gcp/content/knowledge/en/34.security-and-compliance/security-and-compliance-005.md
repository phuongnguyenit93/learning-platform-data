# Sensitive Data Protection and Detecting Sensitive Data

In a Google Cloud system, sensitive data can be scattered across BigQuery tables, Cloud SQL databases, Cloud Storage files, user-submitted content, or API payloads. Some data is already classified and governed, yet test copies, staging tables, logs, or overly broadly shared datasets may also exist. If an organization does not know where sensitive data resides and in what form it appears, access controls, encryption, retention, and incident response lack a solid foundation.

**Sensitive Data Protection** is a suite of Google Cloud services that helps discover, classify, inspect, and redact or transform sensitive data. The product was previously commonly known as Cloud Data Loss Prevention (Cloud DLP); the name Cloud Data Loss Prevention still appears in API names, libraries, and some technical documentation. This lesson focuses on how to identify data, interpret scan results, and choose appropriate protections.

## Learning Objectives

After this lesson, you will be able to:

- Recognize direct identifiers, indirect identifiers, and secrets requiring protection.
- Distinguish discovery, inspection, de-identification, and risk analysis in Sensitive Data Protection.
- Select built-in or custom infoType detectors, interpret likelihood levels, and tune results.
- Design a data scanning workflow with appropriate scope, schedule, and result storage.
- Choose data transformations that balance security and analytical utility.
- Assess re-identification risk and protect findings using IAM, logging, and data controls.

## 1. What Is Sensitive Data?

Sensitive data is information whose disclosure, modification, or misuse could harm individuals, organizations, or customers. Sensitivity depends on content, context, legal obligations, and organizational policy.

Common categories include:

| Data Category | Examples | Risk If Exposed |
|---|---|---|
| Personally Identifiable Information (PII) | Full name, email, phone number, address, identification numbers | Impersonation, phishing, privacy violations |
| Protected Health Information (PHI) | Medical records, diagnoses, lab results | Health information disclosure, breach of confidentiality obligations |
| Financial data | Payment card numbers, bank accounts, transaction IDs tied to individuals | Fraud, financial theft |
| Credentials and secrets | API keys, access tokens, passwords, private keys | Account takeover, lateral movement across systems |
| Confidential business information | Contract pricing, product roadmaps, unpublished customer data | Commercial and reputational damage |

Two concepts must be distinguished:

- **Direct identifier:** a value that can point directly to an individual or account, such as an email, phone number, or traceable customer ID.
- **Indirect identifier (quasi-identifier):** a single attribute that may not identify a person on its own, but when combined with other attributes can narrow a group down to one individual. For example, date of birth, postal code, and gender can help re-identify a record.

Removing names or emails does not guarantee data is anonymized. A dataset can still reveal identities when indirect attributes are joined with public data or data from other systems.

## 2. What Does Sensitive Data Protection Do?

Sensitive Data Protection provides related capabilities with distinct purposes:

| Capability | Question to Answer | Primary Output |
|---|---|---|
| Discovery | Where does sensitive data reside and which assets carry high risk? | Data profiles at the asset, table, or column level |
| Inspection | What sensitive values exist inside a specific resource? | Findings with data type, location, and likelihood |
| De-identification | How can we reduce identifiability while preserving data utility? | Masked, replaced, generalized, or tokenized content |
| Risk analysis | After transformation, how easily can the data still be re-identified? | Metrics such as k-anonymity and l-diversity |

These capabilities are often combined into a workflow. Discovery identifies priority areas; inspection provides detailed evidence; de-identification produces data suitable for sharing or analytics; and risk analysis evaluates residual risk.

Sensitive Data Protection does not automatically make every resource secure simply because the API was enabled or a scan was run. Organizations still must decide how to act on findings, configure IAM, restrict access, encrypt data, manage retention, and monitor usage.

## 3. Discovery: Mapping Sensitive Data

Discovery continuously or periodically generates **data profiles** for resources within a scan configuration's scope. Scope can be configured at the organization, folder, or project level depending on data types and service subscription models.

Supported data sources for discovery include assets such as BigQuery, Cloud SQL, Cloud Storage, and Vertex AI; the service also supports discovery for certain sources outside Google Cloud such as Amazon S3 and Azure Blob Storage. A secrets discovery capability focuses on locating exposed secrets in supported locations, such as workload environment variables.

### What Does a Data Profile Contain?

Depending on resource type, a profile can provide:

- Predicted infoTypes in the data, such as email addresses or payment card numbers.
- Data sensitivity level and data risk level.
- Data size, shape, null percentage, and estimated uniqueness.
- Resource metadata and security signals, such as encryption status or public sharing where supported.
- Timestamp of the most recent profile and metrics for tracking changes.

For BigQuery or Cloud SQL, profiles can be generated across multiple levels such as project, table, and column. This helps security teams pinpoint which tables hold extensive sensitive data, which columns have high unique identifier counts, or which assets require access reviews first.

A data profile is a high-level classification and statistical summary. It is not a complete list of every individual sensitive value in a table. If you need the exact location of every phone number or email, run inspection on the target resource.

### Configuring Discovery

A scan configuration typically specifies:

1. Scope of resources to profile.
2. Data sources and asset types included in scope.
3. Associated detection configuration or inspection template.
4. Profiling frequency and behavior when changes are detected.
5. Actions after profile generation, such as saving a copy of results, publishing to Pub/Sub, or sending insights to another security service.

Discovery processes data where it is stored and stores profile metadata in the region or multi-region corresponding to the profiled resource, per the service's support model. During design, always verify location, data residency, and endpoint options aligned with organizational requirements.

### When to Start with Discovery

Use discovery when the organization lacks a complete data map, has many projects or teams creating resources, or wants to track newly appearing data over time. It is well suited for uncovering shadow data: test tables, legacy buckets, data copies, or resources not yet brought under standard governance workflows.

## 4. Inspection: Finding Exact Locations of Sensitive Data

Inspection performs a detailed scan of a resource or payload to generate **findings** for content matching detection rules. A finding can include:

- **infoType:** category of data detected.
- **likelihood:** confidence level that the content matches the infoType.
- **location:** position of the content within text, field, row, or file.
- **quote:** the detected value snippet, if configuration allows returning it.

A quote can contain the sensitive data itself. In production environments, enable quote storage only when there is a clear requirement and the output location is properly secured.

There are three common ways to invoke inspection:

| Method | Characteristics | Suitable Use Case |
|---|---|---|
| Inspection job | Creates an asynchronous job to scan a supported resource | Scanning BigQuery tables, Cloud Storage buckets, or Datastore kinds |
| Hybrid inspection job | Sends payloads from any source into a job for inspection and stores findings | Integrating data from applications, non-Google Cloud systems, or custom pipelines |
| **content.inspect** | Sends content directly via the DLP API and receives synchronous results | Inspecting a request, text snippet, or content needing immediate response |

Inspection jobs can be scheduled to repeat using job triggers. When a job finishes, actions can be configured such as saving findings to BigQuery or sending notifications via Pub/Sub. When scanning large volumes of resources across many projects, use discovery first to map assets, then select resources for detailed inspection.

### Example: Inspecting API Input Content

A customer support application receives text entered by users. Before saving the content into the ticketing system, the application can send the payload to **content.inspect** to look for emails and phone numbers.

File **inspect-request.json**:

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
  "item": {
    "value": "Please contact an.nguyen@example.com or 0900000000."
  }
}
~~~

Send the request to the DLP API:

~~~bash
curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" -H "Content-Type: application/json" "https://dlp.googleapis.com/v2/projects/PROJECT_ID/content:inspect" --data-binary @inspect-request.json
~~~

Before running the example, enable the appropriate API in your project, configure credentials, and grant necessary permissions to the calling identity. The values in the example are mock data only. **includeQuote: false** avoids returning the literal matched string; the application still needs to handle findings and locations according to business logic.

Inspection only detects and reports according to configuration. If input content should be redacted before storage, the application must invoke a de-identification workflow or perform a controlled processing step itself.

## 5. InfoType Detectors: Defining What Data Types to Find

Sensitive Data Protection uses **infoType detectors** to recognize types of information. Hundreds of built-in detectors exist. Common detectors include:

| InfoType | Example Content Recognized |
|---|---|
| **EMAIL_ADDRESS** | Email addresses |
| **PHONE_NUMBER** | Phone numbers |
| **CREDIT_CARD_NUMBER** | Payment card numbers |
| **IP_ADDRESS** | IP addresses |
| **PERSON_NAME** | Person names |
| **DATE_OF_BIRTH** | Dates of birth |
| **US_SOCIAL_SECURITY_NUMBER** | US Social Security numbers |
| **AUTH_TOKEN** | Certain supported authentication token formats |

The detector catalog is specific to countries, formats, and data types. Do not assume a detector tailored for one country accurately recognizes formats across all countries. For internal identifiers or enterprise-specific data, check whether a built-in detector fits or whether a custom infoType is needed.

### Built-in Detectors and Context

Detectors can rely on multiple signals: character patterns, checksums, prefixes, digit limits, or surrounding words. For instance, a digit string shaped like an ID number is not necessarily a valid ID; checksums and context improve precision.

Some detectors depend on context. If the system fails to detect expected data types due to missing nearby keywords, you may need to tune the detector or use a custom detector. Always declare the exact list of infoTypes to scan to avoid checking unrelated types, which increases latency and generates unnecessary findings.

### Likelihood Is Not Legal Probability

Sensitive Data Protection assigns a likelihood level to each finding:

- **VERY_UNLIKELY**
- **UNLIKELY**
- **POSSIBLE**
- **LIKELY**
- **VERY_LIKELY**

Likelihood expresses the detector's confidence in a match based on pattern and context. It is not a data sensitivity score, not the probability that an individual will be identified, and does not replace security specialist judgment.

The **minLikelihood** setting filters out findings below a desired threshold. A higher threshold can reduce false positives but may miss real data. A lower threshold increases recall but often creates more results to review. Test configurations on a representative dataset and evaluate both false positives and false negatives before broad rollout.

### Custom InfoType Detectors

When data follows proprietary formats, custom detectors can be created:

- **Regex detector:** matches strings using regular expressions, suited for structured case IDs, contract codes, or employee IDs.
- **Small custom dictionary:** matches against a small list of values, such as system names or confidential project codenames.
- **Large custom dictionary / stored infoType:** handles large keyword lists stored and managed separately.

For example, support case IDs follow the pattern **CASE-** followed by eight digits. A custom regex detector can be created:

~~~regex
CASE-[0-9]{8}
~~~

Regex defines structure only. If a random string happens to share a similar structure, the detector can still match falsely. Set an appropriate likelihood and add context rules such as keywords **ticket**, **case_id**, or column names.

### Inspection Rules: Tuning Results

Detectors can be combined with rule sets:

- **Hotword rule:** increases or adjusts likelihood when a keyword appears near the matched value. For instance, a code formatted like **123-4-56789** is more credible when adjacent to the word **MRN**.
- **Exclusion rule:** removes unwanted matches, such as test email addresses or fixed sample strings.
- **Adjustment rule:** adjusts likelihood based on context or related detectors.

Rules are evaluated in configured order. Test rule sets against representative data because an overly broad exclusion rule can hide real data, while an overly generic hotword can increase false positives.

## 6. Templates and Repeatable Scanning Workflows

Sensitive Data Protection supports inspection templates and de-identification templates for reusing configurations. Templates let teams share reviewed lists of infoTypes, likelihood thresholds, rule sets, and transformations.

An operational workflow should include these steps:

1. **Define objectives:** determine where data lives, which data types require protection, and who will consume the results.
2. **Choose scope:** start with a representative project, dataset, or bucket; expand to folders or the organization once cost and permissions are validated.
3. **Select detectors:** explicitly declare infoTypes, custom detectors, and rule sets suited to the data.
4. **Choose method:** discovery for broad profiling; inspection jobs for detailed findings; **content.inspect** for synchronous content; hybrid jobs for arbitrary sources.
5. **Set schedule and sampling:** align scan frequency with data change rates; use sampling or scope limits during pilot checks.
6. **Protect results:** restrict who can read findings, avoid storing quotes unless needed, and select storage with appropriate IAM.
7. **Act on findings:** update classifications, access permissions, retention rules, or produce de-identified datasets.
8. **Monitor:** publish events via Pub/Sub, integrate with Security Command Center or operational systems where appropriate; periodically review profiles and results.

Do not use a single default configuration for all data. For example, customer data in BigQuery may need **EMAIL_ADDRESS**, **PHONE_NUMBER**, and **CREDIT_CARD_NUMBER**, whereas application logs may need detectors for tokens, IP addresses, and internal codes.

## 7. De-identification: Transforming Sensitive Data

De-identification transforms sensitive values to reduce identifiability or exposure. Transformations must match how the data will be used after processing.

| Transformation | How It Works | Example |
|---|---|---|
| Redaction | Removes all or part of a value | Stripping email addresses from ticket text |
| Replacement | Replaces with a fixed placeholder or surrogate | Replacing names with `[PERSON]` |
| Masking | Replaces selected characters with a masking character | `0901234567` becomes `******4567` |
| Bucketing / generalization | Replaces exact values with ranges or groups | Age 27 becomes group `25–34` |
| Date shifting | Shifts dates by a controlled random interval | Shifting medical visit dates to preserve temporal intervals |
| Time extraction | Retains only the time portion needed for analysis | Keeping hour of day while dropping specific date |
| Crypto-based tokenization | Replaces values with cryptographically generated tokens | Email replaced with a deterministic token |

### Choosing Transformations by Requirement

- If data only needs to be shown to support staff, masking may suffice so they can confirm the last few digits.
- If identifiers do not need to be retained, redaction or replacement minimizes remaining sensitive data.
- If analysis by age group or region is needed, bucketing preserves overall trends without exposing exact values.
- If multiple records for the same person must be linked without storing plaintext identifiers, pseudonymization producing deterministic tokens may fit.
- If temporal trend analysis is needed without real calendar dates, date shifting or time extraction preserves partial data structure.

### Pseudonymization and Cryptographic Tokenization

Sensitive Data Protection supports multiple tokenization techniques, including:

- **Deterministic encryption with AES-SIV:** the same input and corresponding context tweak produce a consistent token; reversible with the appropriate key. This method does not preserve the input's character set.
- **Format-preserving encryption (FPE-FFX):** produces an encrypted value with the same length and within a specified character alphabet; useful when target systems require preserving format. Character sets and lengths have limits, so input requirements must be checked.
- **Crypto hash:** produces a one-way hash, suitable when matching or joining on hashed values without needing to recover the original value.

With reversible methods, encryption keys become sensitive assets. Cloud KMS can be used to wrap Sensitive Data Protection encryption keys. Restrict key usage and administration permissions, store keys securely, govern re-identification capabilities, and maintain rotation/recovery procedures. Tokenization alone does not automatically guarantee absolute anonymity.

### Transforming Structured Data

For tabular data, transformations should be chosen across two dimensions:

- **InfoType transformation:** applied when values in a column or text match a selected detector.
- **Record transformation:** applied to one or more specific fields/columns according to record structure, even without relying on an infoType detector.

For example, in a customer table, you might tokenize **customer_id**, mask **phone_number**, redact **email**, and bucket **age**. Retain join keys necessary for analytics, while assessing whether the remaining combination of columns could re-identify individuals.

De-identification can be performed via **content.deidentify** for content sent directly to the API or through supported stored-data processing pipelines. For production data, write outputs to a copy or target area, verify quality, and only then switch consumers to the transformed dataset.

## 8. Risk Analysis: Checking Re-identification Potential

A dataset stripped of names, emails, or phone numbers can still expose individuals through quasi-identifiers. Sensitive Data Protection supports risk analysis metrics on structured data in BigQuery.

| Metric | Meaning |
|---|---|
| k-anonymity | Each combination of quasi-identifiers in a record appears in at least k records in the dataset |
| l-diversity | Each group of records sharing the same quasi-identifiers has sufficient diversity in sensitive attributes |
| k-map | Compares re-identification likelihood against a larger reference dataset |
| δ-presence | Estimates the likelihood that an individual is present in the dataset |

For example, if a record with age 34, postal code, and gender matches only one person in the dataset, re-identification risk may be high. Generalizing age into bands and reducing geographic granularity can increase the number of indistinguishable records. However, raising k-anonymity alone does not guarantee data cannot be inferred; l-diversity and additional checks may be needed to assess sensitive attributes.

Risk analysis should be run before de-identification to select a strategy and after de-identification to verify results. Every reduction in data detail can lower analytical utility; balance privacy requirements against dataset utility.

## 9. Integrating Results into Security Workflows

Data profiles and findings only deliver value when fed into operational workflows:

- **BigQuery:** stores scan results, builds reports, and analyzes sensitive data trends.
- **Pub/Sub:** publishes events to trigger remediation workflows or notifications.
- **Security Command Center:** centralizes findings and prioritizes security risk remediation when properly integrated.
- **Google Security Operations:** feeds discovery insights into security analytics workflows within supported scope.
- **Knowledge Catalog:** attaches profile metadata to data assets so users understand sensitivity levels before use.

For example, discovery detects a BigQuery table containing email and payment card columns. A workflow can create a ticket for the data owner, request an IAM review, apply classification policies, and run inspection on the table. After verification, the data team produces a de-identified copy for analytics.

Do not automatically delete data or revoke permissions based solely on a single low-likelihood finding. Identify severity, owner, data source, and remediation approval workflows. Automated actions require clear criteria, logging, and traceability.

## 10. IAM, Data Residency, and Protecting Scan Results

Sensitive Data Protection requires permissions to call APIs and access corresponding source or destination resources. Job creators, template managers, finding readers, and service agents may require distinct permissions.

Predefined roles include:

- **roles/dlp.admin:** administers Sensitive Data Protection, including jobs and templates.
- **roles/dlp.user:** performs service operations according to granted permissions.
- **roles/dlp.reader:** reads permitted resources and results.
- **roles/dlp.jobsEditor:** manages jobs within the role's permission scope.
- **roles/dlp.orgdriver** and **roles/dlp.projectdriver:** provide permissions needed for the DLP service account to generate data profiles at the organization/folder or project scope respectively.

Permission lists vary by feature and resource. Consult current IAM role/permission tables to grant least privilege. Permissions to read BigQuery, Cloud Storage, or write results must still be evaluated separately for sources and destinations.

**Grant service agent roles only to the corresponding service agent.** Do not assign **roles/dlp.serviceAgent** to human users or regular application service accounts. When enabling a feature requiring a service agent, allow Google Cloud to provision the service principal and assign the right permissions per that feature's documentation.

The roles **roles/dlp.orgdriver** and **roles/dlp.projectdriver** also serve the Sensitive Data Protection service account during discovery workflows. Grant them to the designated service agent following discovery setup guidance; do not treat them as ordinary roles for finding viewers.

Findings can contain data locations, column names, metadata, and sometimes quotes. Therefore:

- Store results in a project/dataset/bucket with restricted IAM.
- Enable **includeQuote** only when there is a business justification, and protect quotes like the original data.
- Avoid writing sensitive content into application logs or Pub/Sub notifications unless necessary.
- Separate permissions for creating jobs, viewing results, and handling raw source data.
- Monitor access to findings and changes to scan configurations.
- Define retention periods for results, de-identified copies, and tokenization keys.

For data residency requirements, verify the locations of sources, scan configurations, profile/finding storage, and supported regional endpoints. Do not assume that merely selecting a regional endpoint satisfies all residency obligations; verify documentation for each feature and source service.

## 11. Limitations and Operational Considerations

Sensitive Data Protection supports many data types and detectors, yet results still depend on formatting, language, context, and configuration. A detector may miss values that deviate from expected formats or falsely match strings with similar structures. Use known sample datasets to measure precision and recall before wide rollout.

When scanning large datasets:

- Prioritize high-sensitivity assets, broadly accessed assets, or assets without clear owners.
- Start with discovery to identify areas worth inspecting.
- Specify only needed infoTypes; avoid unrelated detectors.
- Use sampling, time limits, or scope limits when appropriate.
- Estimate costs by operation type and volume of processed data before scaling out.
- Monitor runtime, finding counts, and costs per resource group.

Sensitive Data Protection also does not replace Secret Manager, Cloud KMS, IAM, VPC Service Controls, encryption at rest, or data governance policies. Secret Manager manages the lifecycle of secrets applications need; Sensitive Data Protection helps detect or transform sensitive content. Cloud KMS manages cryptographic keys; IAM decides which principals can access resources. These services complement one another in a data protection architecture.

## 12. Real-World Scenario: Protecting Customer Data Before Sharing with Analytics

An e-commerce company stores customer information in BigQuery. The transactions table contains customer ID, email, phone number, shipping address, purchase timestamp, and order value. The analytics team needs the data to calculate repeat purchase rates and analyze regional trends.

**Step 1 — Discovery:** the security team configures discovery across the data project. Profiles reveal a transactions table containing emails and phone numbers, along with several columns showing high uniqueness.

**Step 2 — Inspection:** the team creates an inspection job for the target table, selecting **EMAIL_ADDRESS**, **PHONE_NUMBER**, and a detector tailored to internal customer IDs. Findings are saved to a separately protected BigQuery table, with quote storage disabled unless needed.

**Step 3 — Selecting transformations:** emails and phone numbers are tokenized so records can still be linked by customer; detailed addresses are generalized to region; transaction timestamps are adjusted to the granularity needed for analysis. Fields unnecessary for analytics are dropped from the shared dataset.

**Step 4 — Risk analysis:** the team evaluates k-anonymity and l-diversity on the transformed dataset. If a small group remains easily identifiable from the combination of region and transaction timestamp, the team increases generalization or reduces granularity.

**Step 5 — Release controls:** the processed dataset is saved in a separate dataset accessible only to the analytics team. The security team validates metric quality and joinability before approving usage.

This workflow retains attributes needed for analytics, reduces sharing of plaintext identifiers, and produces evidence of how data was processed. Tokenization keys and raw source datasets remain governed under separate policies.

## 13. Sensitive Data Protection Implementation Checklist

- [ ] Identified data types requiring protection and the organization's classification policy.
- [ ] Inventoried data sources, projects, owners, and scan scopes.
- [ ] Selected discovery or inspection based on objectives and required granularity.
- [ ] Explicitly declared built-in/custom infoTypes and tested detectors on representative data.
- [ ] Tuned likelihood, hotword, exclusion, and adjustment rules to control false positives/false negatives.
- [ ] Defined scan schedules, sampling, scope limits, and budget.
- [ ] Selected transformations aligned with post-processing data usage needs.
- [ ] Assessed re-identification risk on de-identified data.
- [ ] Protected findings, quotes, templates, and scan configurations with appropriate IAM.
- [ ] Verified regional endpoints, locations, and data residency meet organizational requirements.
- [ ] Established owners, finding handling workflows, remediation tracking, and periodic audits.

## Conclusion

Sensitive Data Protection helps organizations understand where sensitive data resides, which data types are present, and how to protect them. Discovery provides maps and high-level profiles; inspection pinpoints exact locations; infoType detectors identify data categories; de-identification reduces identifiability; and risk analysis evaluates residual risk. Effective implementation combines properly tuned detectors, controlled scan scopes, least-privilege IAM, protected findings, and verifiable remediation workflows.

## References

- [Sensitive Data Protection overview](https://docs.cloud.google.com/sensitive-data-protection/docs/sensitive-data-protection-overview)
- [Learn about your data through discovery and inspection](https://docs.cloud.google.com/sensitive-data-protection/docs/learn-about-your-data)
- [Overview of sensitive data discovery](https://docs.cloud.google.com/sensitive-data-protection/docs/data-profiles)
- [InfoTypes and infoType detectors](https://docs.cloud.google.com/sensitive-data-protection/docs/concepts-infotypes)
- [Creating and scheduling inspection jobs](https://docs.cloud.google.com/sensitive-data-protection/docs/creating-job-triggers)
- [Inspect Google Cloud storage and databases](https://docs.cloud.google.com/sensitive-data-protection/docs/inspecting-storage)
- [De-identifying sensitive data](https://docs.cloud.google.com/sensitive-data-protection/docs/deidentify-sensitive-data)
- [Transformation reference](https://docs.cloud.google.com/sensitive-data-protection/docs/transformations-reference)
- [Pseudonymization](https://docs.cloud.google.com/sensitive-data-protection/docs/pseudonymization)
- [Measuring re-identification and disclosure risk](https://docs.cloud.google.com/sensitive-data-protection/docs/compute-risk-analysis)
- [Sensitive Data Protection roles and permissions](https://docs.cloud.google.com/sensitive-data-protection/docs/access-control/roles-permissions)
