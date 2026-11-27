# IAM, Authorized Views, and Dataset Access Control

An online learning platform stores enrollment events, revenue, and learner profiles in **BigQuery**. The operations team needs full read access for reconciliation, whereas analysts only need enrollment counts per course, and external partners should only see aggregated reports. Granting `BigQuery Data Viewer` at the **project** level to everyone would expose unrelated datasets containing emails, tuition fees, and sensitive data.

This lesson belongs to the **BigQuery** chapter of the **CLOUD_PROVIDERS_GCP** module. We will use **Google Cloud IAM**, permissions at the **dataset/table/view** level, and **authorized views** to share data under least privilege, while tying into project design, Cloud Run/GKE service accounts, auditing, and query costs.

**Objectives:** after this lesson, you will be able to:

1. Distinguish **query job creation** permissions from **table/view read** permissions and understand IAM inheritance scope.
2. Select appropriate roles for data owners, ingestion pipelines, analysts, and service accounts.
3. Create an authorized view in a separate dataset and authorize it to read source tables without granting analysts read access to the source tables.
4. Explain the differences between **authorized views**, **authorized datasets**, row-level access policies, and column-level policy tags/masking.
5. Test both allowed and denied access paths, audit logs, inherited permissions, and revocation workflows.
6. Run the lab with synthetic data without touching real user records.

## 1. BigQuery Authorization Model

BigQuery follows a **resource hierarchy**: organization/folder → project → dataset → table/view/routine. IAM roles granted higher up are **inherited by child resources**. Removing a binding at the dataset level does not revoke permissions inherited from the project or organization.

~~~mermaid
flowchart TB
    ORG["Organization / Folder"] --> P["Project: learning-prod"]
    P --> RAW["Dataset: raw_private"]
    P --> PUB["Dataset: reports_shared"]
    RAW --> T["Table: enrollments<br/>contains email, tuition"]
    PUB --> V["View: enrollment_counts<br/>reporting only"]
    ANALYST["Analyst group"] -->|"dataViewer on view<br/>+ jobs.create on billing project"| V
    V -. "Authorized view<br/>on source dataset" .-> RAW
    ANALYST -. "No direct read<br/>on source table" .-> T
~~~

**Allowing queries through an authorized view** does not grant principals direct read access to `raw_private.enrollments`. Authorization is attached to **the view on the source dataset**, while callers only receive read access to **the view**.

### 1.1. Execution Permissions and Data Permissions Are Separate

| Need | Common Permission/Role | Recommended Scope |
| --- | --- | --- |
| Create/run query jobs | `bigquery.jobs.create` via `roles/bigquery.jobUser` | **Project running/billed for the query job**; not just on the dataset |
| Read a table or view | `bigquery.tables.getData` via `roles/bigquery.dataViewer` | **Specific dataset or single table/view**, per required scope |
| Create/edit tables or views | `roles/bigquery.dataEditor` | Dataset dedicated to pipelines or view authors |
| Manage a dataset and its access controls | `roles/bigquery.dataOwner` | Only datasets owned by that data steward |
| Broad BigQuery administration | `roles/bigquery.admin` | Only dedicated admin accounts; never grant just to run `SELECT` |

For example, an analyst with `roles/bigquery.dataViewer` on a view but **without** `bigquery.jobs.create` on an execution project can inspect metadata yet **cannot run query jobs**. Conversely, having Job User on a project **does not grant read access** to any datasets inside that project.

A job can execute and be billed in a **different project** from where the data lives; Job User is required on the **execution/billing project**, while table/view read permissions are needed on the data resource. On Cloud Run/GKE, attach a dedicated **runtime service account** with just these two scoped permissions rather than baking JSON service account keys into containers.

### 1.2. Permission Scope and Blast Radius

| Binding | What the Principal Gains | Risk |
| --- | --- | --- |
| `roles/bigquery.dataViewer` on data project | Can read tables/views across **all datasets** inheriting the role | Accidental access to sensitive data outside scope |
| `roles/bigquery.dataViewer` on dataset `reports_shared` | Reads all resources in that dataset | Future views/tables added to the dataset become readable too |
| `roles/bigquery.dataViewer` on **a single view** | Reads only that view (and necessary metadata per policy) | Narrowest blast radius, though requires managing more bindings |
| `roles/bigquery.dataEditor` on source dataset | Modifies data/objects in that dataset | Excessive for read-only analysts |
| `roles/bigquery.dataOwner` on source dataset | Manages data and dataset permissions | Grant only to approved data owners/stewards |

**Always inspect inherited IAM** before claiming a user "has no access" to the source table. Someone who holds `project Editor` or project-level BigQuery Data Viewer can still read the raw table directly even if you scoped the view properly.

### 1.3. Access Control Is Managed in Two Ways

BigQuery supports **IAM policies** on datasets/tables/views as well as **dataset access entries (ACLs)**, which include special entities such as **authorized views** and **authorized datasets**. Authorized view entries are not regular service accounts you bind roles to; they represent permission to read the source tables **through that view**.

Note a change in some environments: when **fine-grained dataset ACL permission enforcement** is enabled, reading/updating dataset access controls requires `bigquery.datasets.getIamPolicy` and `bigquery.datasets.setIamPolicy` respectively, alongside operation-specific permissions. Automation relying solely on `bigquery.datasets.update` can fail once enforcement is active. Verify permissions, API versions, and org configs before automating—never escalate to Owner to work around a 403.

## 2. Authorized Views: Sharing Results Without Sharing Source Tables

A **logical view** is a saved `SELECT` query; normally, callers need read permissions on all underlying tables referenced by that view. An **authorized view** is a view **authorized by the source dataset** to read underlying tables on the caller's behalf, strictly within the SQL logic defined by the view.

~~~mermaid
sequenceDiagram
    participant U as Analyst
    participant J as BigQuery query job
    participant V as reports_shared.enrollment_counts
    participant R as raw_private.enrollments
    U->>J: SELECT * FROM view
    J->>J: Check jobs.create + view read access
    J->>V: Execute saved SQL
    V->>R: Access table via authorized view entry
    R-->>V: Rows matching query
    V-->>U: Only columns/rows permitted by view
    Note over U,R: Direct SELECT on source table by U must be denied
~~~

### 2.1. Three Permissions Must Work Together

1. **Data owner** creates the view in a **separate shared dataset** and authorizes that view on the **source dataset**.
2. **Consumer** receives `roles/bigquery.dataViewer` **on the view** (or the shared dataset), and **no** Data Viewer on the source dataset.
3. **Consumer** holds `bigquery.jobs.create` on the project executing queries, with appropriate quotas and billing controls.

Both the source dataset and the authorized view dataset must be in the **same location**. Never place raw tables and shared views in the same dataset and grant Data Viewer on that dataset: role inheritance would expose **the raw tables too**.

### 2.2. What Does an Authorized View Not Guarantee?

- A view exposes whatever **its SQL query is written to return**; it does not automatically enforce k-anonymity, privacy budgets, or prevent re-identification from tiny groups.
- Using `SELECT *` in a view risks leaking newly added columns from the source table; specify an **explicit column list** and review SQL edits.
- If a consumer already has broad access to the source dataset via project-level IAM, an authorized view **does not revoke** that access.
- View SQL must undergo code review and change control: editing a view to add columns or drop filters widens data exposure.
- With an **authorized dataset**, every existing and future view in that dataset inherits source access; therefore, permission to **create or edit views** in that dataset becomes a sensitive privilege.

For individual authorized views, editing the view's SQL requires elevated checks from the source data owner. Never assume holding Data Editor on the view's dataset lets someone freely alter an already-authorized view's SQL; verify change controls against BigQuery policy.

## 3. Lab: Two Datasets and One Authorized View

**Goal:** analysts can view **enrollment counts per course**, but cannot read emails, tuition fees, or the raw table. All mutating commands below are for an **approved lab project only**; BigQuery may charge for queries, storage, and jobs. Never use real learner data.

### 3.1. Resources and Identities

| Resource | Function | Permissions |
| --- | --- | --- |
| `bq_iam_raw_lab` | Private dataset holding `enrollments` table | Data owner and approved ETL pipeline |
| `bq_iam_shared_lab` | Shared dataset holding only `active_by_course` view | Analysts read the view; owner manages SQL |
| `analyst@example.com` | Illustrative principal for permission testing | Job User on execution project + Data Viewer **on the view** |
| View authorization | Access entry on `bq_iam_raw_lab` | Lets the view query source table without granting analysts table access |

The lab operator needs permissions to **create datasets/tables/views**, read the source table, and **authorize the view on the source dataset**. IAM/view authorization should be applied by an authorized data owner; the analyst tests using a separate identity. Never generate JSON service account keys.

### 3.2. Create Both Datasets in the Same Location

In Cloud Shell/Bash using a **dedicated lab project**, verify these names do not already exist and pick a location meeting residency rules:

~~~bash
export PROJECT_ID="YOUR_APPROVED_LAB_PROJECT"
export LOCATION="US"
export RAW_DS="bq_iam_raw_lab"
export SHARED_DS="bq_iam_shared_lab"

gcloud config set project "$PROJECT_ID"

# READ-ONLY: verify current project and existing datasets.
gcloud config get-value project
bq ls --project_id="$PROJECT_ID"

# MUTATING: run only if these dataset names do not exist in the LAB project.
bq --location="$LOCATION" mk --dataset "$PROJECT_ID:$RAW_DS"
bq --location="$LOCATION" mk --dataset "$PROJECT_ID:$SHARED_DS"
~~~

If either dataset name already exists, **stop** and pick approved unique names; never alter or delete another team's datasets. Both source and view must share the **same location**; note that `US` is a multi-region and **not** equivalent to region `us-central1`.

### 3.3. Create a Table Containing Both Sensitive and Shareable Columns

Run in BigQuery Studio (GoogleSQL) inside your **lab project**, replacing `YOUR_PROJECT` with your real project ID:

~~~sql
CREATE TABLE `YOUR_PROJECT.bq_iam_raw_lab.enrollments` (
  enrollment_id STRING NOT NULL,
  learner_id STRING NOT NULL,
  course_id STRING NOT NULL,
  status STRING NOT NULL,
  email STRING,
  tuition_usd NUMERIC
);

INSERT INTO `YOUR_PROJECT.bq_iam_raw_lab.enrollments`
  (enrollment_id, learner_id, course_id, status, email, tuition_usd)
VALUES
  ('e1', 'u1', 'java-basic', 'ACTIVE', 'u1@example.invalid', 30),
  ('e2', 'u2', 'java-basic', 'ACTIVE', 'u2@example.invalid', 20),
  ('e3', 'u3', 'java-basic', 'ACTIVE', 'u3@example.invalid', 25),
  ('e4', 'u4', 'java-basic', 'ACTIVE', 'u4@example.invalid', 20),
  ('e5', 'u5', 'python-basic', 'ACTIVE', 'u5@example.invalid', 35),
  ('e6', 'u6', 'python-basic', 'CANCELLED', 'u6@example.invalid', 35);
~~~

**Note:** `example.invalid` is a reserved dummy domain for test data; this script holds no real personal data. Never make lab datasets public. `CREATE TABLE` and `INSERT` persist real data when run—use an approved project and budget.

### 3.4. Create a Logical View Restricting Columns and Rows

In the **separate shared dataset**, create the view:

~~~sql
CREATE VIEW `YOUR_PROJECT.bq_iam_shared_lab.active_by_course` AS
SELECT
  course_id,
  COUNT(*) AS active_enrollments
FROM `YOUR_PROJECT.bq_iam_raw_lab.enrollments`
WHERE status = 'ACTIVE'
GROUP BY course_id
HAVING COUNT(*) >= 3;
~~~

`HAVING COUNT(*) >= 3` only hides tiny groups in this **example**. A threshold of 3 is **not** a privacy guarantee: combining multiple reports, shifting filters, or external knowledge can still re-identify learners. The core control here is that **the view excludes `email`, `learner_id`, and `tuition_usd`**.

With the sample rows, expected output is **one row** for `java-basic` with `active_enrollments = 4`. `python-basic` is omitted because it has only one `ACTIVE` record.

### 3.5. Grant Permissions in the Right Order

**Step A — Authorize the view on the source dataset.**

1. Sign in as the **data owner** permitted to edit access controls on `bq_iam_raw_lab`.
2. BigQuery Console → select source dataset `bq_iam_raw_lab` → **Sharing → Authorize views**.
3. Enter `YOUR_PROJECT.bq_iam_shared_lab.active_by_course` and click **Add authorization**.
4. Confirm the entry appears on the source dataset and covers only the reviewed view.

This turns a **standard logical view** into an **authorized view**. Never add the analyst as Data Viewer on `bq_iam_raw_lab`; doing so would let them query raw rows directly and defeat the architecture.

**Step B — Grant the consumer read access to the view.**

5. On **view `active_by_course`** (or the shared dataset holding only approved views), open **Sharing → Permissions** and grant `BigQuery Data Viewer` to the approved analyst group.
6. On the **query execution project**, grant `BigQuery Job User` (`roles/bigquery.jobUser`) to the analyst. The job project can differ from the view's project, provided locations, quotas, and policies align.
7. Verify the analyst has **no** inherited source read access from project/org IAM or another group.

**Step C — Test as the consumer identity.**

~~~sql
-- Expected: succeeds; returns only course_id and active_enrollments.
SELECT *
FROM `YOUR_PROJECT.bq_iam_shared_lab.active_by_course`;

-- Expected: Access Denied for an analyst WITHOUT source table permissions.
SELECT email, tuition_usd
FROM `YOUR_PROJECT.bq_iam_raw_lab.enrollments`
LIMIT 1;
~~~

Never run the negative test as the data owner, as that proves nothing about analyst permissions. If querying the source table **still succeeds**, audit inherited bindings, other group memberships, or shared resource paths—do not treat the lab as passing.

### 3.6. Inspect Permissions and Clean Up

These **read-only** commands inspect dataset metadata and ACLs accessible to the caller:

~~~bash
bq show --format=prettyjson "$PROJECT_ID:$RAW_DS"
bq show --format=prettyjson "$PROJECT_ID:$SHARED_DS"
bq show --format=prettyjson "$PROJECT_ID:$SHARED_DS.active_by_course"
~~~

Output can contain internal details about datasets and principals; **never paste full JSON into public tickets**. IAM roles granted at the project level may **not appear directly** in dataset ACLs—always inspect ancestor IAM policies.

**Lab cleanup:** the data owner revokes the analyst's view access, removes the **authorized view entry** on the source dataset, and then deletes only the view, two datasets, and synthetic table **created by this lab** after confirming no one else uses them. Never run `bq rm -r -f` on unverified projects/datasets, and never delete production datasets. Logs and billing charges may continue appearing after cleanup.

## 4. How Do Authorized Views and Authorized Datasets Differ?

| Mechanism | Unit Authorized by Source Dataset | Best Suited For | Risks to Control |
| --- | --- | --- | --- |
| **Authorized view** | **One specific view** | Sharing a few owner-reviewed reports/query paths | View SQL changes; consumers granted extra roles unexpectedly |
| **Authorized dataset** | **Dataset containing views** | Many views governed under one policy and owner group | **New or edited** views in the authorized dataset can access source data |
| **Authorized routine** | Approved routine | Exposing parameterized queries/functions via a controlled interface | Routine logic and edit rights must be reviewed |
| **Data Viewer on source dataset** | **Principal** reads source tables directly | Internal teams authorized for raw data | Does not hide source tables from consumers |

### 4.1. Why Do Authorized Datasets Require Strict Control Over View Authors?

If `reports_shared` is authorized **at the dataset level** against `raw_private`, anyone allowed to create or edit views in `reports_shared` can expose source data through a new or expanded SQL view (within the authorization scope). Therefore, **never grant all analysts `Data Editor`** on an authorized dataset.

Recommended workflow:

1. Data owner designates **trusted view publishers**, separate from read-only consumers.
2. Only trusted engineers/CI pipelines hold permissions to create or update views in the authorized dataset.
3. Enforce code review on SQL, filters, aggregations, column lists, and referenced sources; test for unintended exposure.
4. Audit dataset access entries and all views periodically; alert on newly created or altered views.
5. Revoke dataset authorization if governance requirements are no longer met.

For just a few reports, prefer **authorizing individual views** to keep blast radius narrow. Authorized datasets reduce per-view setup toil at the cost of **higher publishing governance responsibility**.

### 4.2. Location and Other Constraints

- The source dataset and the dataset holding the authorized view must reside in the **same BigQuery location**. Different projects can participate if IAM, location, and org policies permit.
- An authorized view is a **logical view**: querying it executes against the source tables at runtime rather than creating a sanitized physical copy.
- When source data is sensitive, evaluate **column-level security**, row-level policies, data masking, IAM deny policies, and **VPC Service Controls** together. Never assume a view bypasses lower-level policies or try to design view filters to circumvent them.
- Cross-region or cross-perimeter references face additional service/compliance restrictions; verify current configuration and documentation.

## 5. Row- and Column-Level Controls: When Authorized Views Aren't Enough

Authorized views excel when **shared data maps cleanly to a small set of reviewed SQL queries**. However, with hundreds of tenants, complex roles, and sensitive fields accessed through multiple paths, layer additional controls.

### 5.1. Row-Level Access Policies

A **row-level access policy** uses SQL predicates to restrict **which rows** a principal or group can read from a table. For instance, a regional reporting team can access only rows matching their assigned region.

| Mechanism | When to Use | Caveat |
| --- | --- | --- |
| Filter inside an **authorized view** | Small number of fixed, owner-reviewed perspectives | Does not protect other query paths hitting the source table |
| **Row-level access policy** on table | Row filtering bound directly to table and principals | Must test per identity, role, and interacting policies |
| **Application authorization** | Per-learner/per-order access or live transactional checks | BigQuery does not replace backend business authorization |

**Never use a single shared view to promise "each user sees only their own orders" if access depends on caller identity that the view SQL cannot enforce.** For multi-tenant data, evaluate per-tenant datasets, row-level security, or a backend service enforcing authorization.

### 5.2. Column-Level Policy Tags and Data Masking

In `enrollments`, `email` and `tuition_usd` may require protection **even when a user has read access to the source dataset**:

1. Data stewards classify sensitive columns.
2. Create **taxonomies/policy tags** (or equivalent governance tags) and attach them to schema columns.
3. Enforce access policies and grant **Fine-Grained Reader** only to principals authorized to view raw values.
4. Where masked values suffice, configure **data masking** rules and grant Masked Reader per policy.
5. Test the exact same query as a full reader, a masked reader, and an unauthorized user.

**Column policy tags add an orthogonal layer beyond dataset IAM.** Holding Data Viewer on a dataset **does not automatically** grant read access to policy-tagged columns. With views, verify **permissions on underlying source columns** per enforcement rules—a view doing `SELECT email` cannot bypass column-level policies.

At the same time, an authorized view excluding `email` and `tuition_usd` cleanly narrows the **shared contract**, while policy tags and masking enforce protection across arbitrary queries and consumers. Never equate a column-hiding view with cryptographic encryption or irreversible anonymization of raw data.

### 5.3. Combined Model for Multi-Team Organizations

| Group | Job Execution | Data Access | Notes |
| --- | --- | --- | --- |
| **ETL ingestion** | Job User on pipeline project | Data Editor scoped to source dataset | Never grant project-wide read if pipeline writes one dataset |
| **Finance team** | Job User on approved project | Data Viewer on source dataset + needed policy tags | Audit sensitive column reads and exports |
| **Course analysts** | Job User on execution project | Data Viewer on authorized report views | Zero direct access to source dataset |
| **External partners** | Granted only under contract | Dedicated view, aggregated data, strict quotas/perimeter | Test against re-identification and scraping |
| **Cloud Run reporting API** | Runtime SA with job creation if needed | Read only approved views | Still enforce end-user authorization in app code |

Use **Google Groups** to manage users with shared access profiles, separate admins/deployers/consumers, and review bindings periodically. Never grant `roles/bigquery.admin` or `Owner` just to run a dashboard.

## 6. Auditing, Revocation, and Cost Control

### 6.1. Periodic Access Review Workflow

A structured checklist prevents missing indirect access paths:

1. Identify the **actual principal** running queries (user, group, or runtime service account) and the **execution project**.
2. Inspect **inherited IAM** from organization/folder/project down to direct bindings on datasets, tables, and views.
3. Audit **authorized view/dataset/routine entries** on source datasets; document the owner and purpose of each.
4. Inventory shared **views**, current SQL definitions, who can edit views, and referenced columns/tables.
5. Review policy tags, masking, row policies, IAM deny policies, and VPC Service Controls if enabled.
6. Run **negative access tests** using an unauthorized representative identity rather than trusting IAM tables alone.
7. Remove stale bindings/authorizations and verify active pipelines and approved reports keep working.

**Deleting or renaming a view does not close every path to data.** Analysts might still read source tables via another group, materialized/copied tables, or previously exported query results. During incident-driven revocation, audit **copies, exports, and saved query results** per policy—not just a single ACL.

### 6.2. Audit Logs and Change Investigation

BigQuery emits audit records for administrative actions and query/data-access events according to product capabilities and Logging configuration. When investigating, ask:

- **Who** granted `dataViewer`, `dataEditor`, or modified dataset ACLs / authorized view entries?
- **Who** ran `CREATE VIEW` or altered the SQL definition of a shared view?
- **Which principal** ran the query, in which project/location, touching which view or table?
- Did the **query job** export or copy data to another dataset or Cloud Storage bucket?

Starter filter in Logs Explorer:

~~~text
protoPayload.serviceName="bigquery.googleapis.com"
~~~

Narrow further by resource, principal, method, timestamp, and enabled log types. **Do not** assume every event appears in the same log type or instantaneously; BigQuery uses structured audit metadata, and Data Access logs may carry restricted viewing permissions. Avoid exposing query text containing sensitive literals in public incident reports.

### 6.3. Authorized Views Are Not Free Physical Copies

A logical view executes its SQL against underlying source tables when queried. Implications:

| Action | Consequence |
| --- | --- |
| Analysts query the view repeatedly | Incurs **query processing costs** under on-demand or capacity/edition billing |
| View selects many columns or lacks partition filters | Can scan far more source data than necessary |
| View aggregates a huge source table | Still pays compute to scan/aggregate the underlying source |
| Running `LIMIT 10` on the view | Does not guarantee reduced **bytes scanned** on the source query |
| Creating a materialized view or snapshot table | Changes storage/refresh costs and permission rules; must be redesigned separately |

**Security and cost are two separate dimensions.** An authorized view can be airtight on exposed columns/rows while still running expensive scans. Use **dry runs**, partition pruning, clustering, billing budgets/quotas, and job telemetry. Billing budget alerts **are not hard caps**.

### 6.4. Controlled View Change Process

For a view shared across many analysts:

1. Review the SQL diff, added/removed columns, filters, joins, aggregations, re-identification risk, and new data sources.
2. Test in a **staging** dataset/view in the same location using synthetic data and a consumer test account.
3. Verify **permission-denied** on the raw source table alongside view accuracy, scanned bytes, and latency.
4. Authorized maintainers deploy the SQL and confirm source dataset authorization did not expand unexpectedly.
5. Record change logs, owners, rollback steps, and negative test results; monitor post-release query costs.

With **authorized datasets**, apply this workflow to **every new view**, not just the initial one. Never grant Data Editor on an authorized dataset to consumers.

## 7. Diagnosing Access Errors

| Error / Symptom | Common Cause | Safe Verification |
| --- | --- | --- |
| `Access Denied: User does not have bigquery.jobs.create` | Principal lacks Job User on the **execution project** | Check execution project and its IAM bindings |
| Analyst can view view metadata but cannot query it | Missing view read permission, job permission, or source authorization | Check layer by layer: job → view → source authorization |
| Direct query on source table is denied | Least-privilege design is working | This is the **expected** negative test outcome |
| Analyst can read source table despite view-only intent | Inherited role or another group grants direct access | Audit ancestor IAM and group memberships; revoke with approval |
| Authorized view fails after dataset/table change | Source path, location, or authorization entry is stale | Verify view SQL and source dataset authorization |
| `Permission denied` on a specific column | Policy tag / column-level security or masking role | Check taxonomy/tag policy, source column, and principal roles |
| Query blocked by VPC Service Controls | Project/perimeter/ingress-egress rules | Inspect VPC SC violation logs and perimeter policy; never disable perimeter as a "quick fix" |
| IAM granted yet Cloud Run app still fails | Runtime SA differs from deployer identity, or wrong job project | Verify active revision's service account and job project |
| Role revoked yet user still sees old numbers | Cached query results, exports, or independent copies | Audit caches, data copies, and revocation procedures |
| View query succeeds yet bill spikes | Repeated queries, full scans, missing partition filters, high concurrency | Inspect bytes processed/billed, dry runs, jobs, and query plans |

**Tip for triaging 403s:** first identify whether the failure occurs at **job creation**, **reading the view**, **view-to-source authorization**, or **column/row checks**. Never add `BigQuery Admin` to a project to bypass a 403—that undermines the entire data-sharing boundary.

### 7.1. Three Quick Triage Questions

~~~text
1. Who is executing?
   -> user or service account email; group memberships and inherited roles
2. Where is the job running?
   -> project/region used to submit the query, jobs.create, and quotas
3. What data is being read?
   -> view/table; Data Viewer; authorized view entry on source;
      plus policy tags, row policies, or perimeter if present
~~~

IAM and view authorization changes can take a brief moment to propagate. After deploying changes, re-test with a **fresh query** as the target principal—never use a stale cached result as proof of current permissions.

## 8. Scenario Exercises and Solutions

### Scenario A — Analyst Can Still Read Emails

The data team created an authorized view exposing only `course_id` and `COUNT(*)` and granted Data Viewer on the view. Yet an analyst can still run:

~~~sql
SELECT email
FROM `PROJECT_ID.raw_private.enrollments`
LIMIT 10;
~~~

**Question:** Is the authorized view broken? What should you check?

**Solution:** Not necessarily. The analyst may hold **Data Viewer on the source project**, belong to a group granted a role at the folder level, or have a direct binding on the source dataset/table. Audit inherited permissions and group memberships, then revoke overly broad roles with approval—**do not** merely tweak the view SQL.

### Scenario B — Authorized Dataset and View Creation Rights

`reports_shared` is authorized at the dataset level on `raw_private`. A user with `roles/bigquery.dataEditor` on `reports_shared` creates a new view: `SELECT email, tuition_usd FROM raw_private.enrollments`.

**Question:** Where is the risk, and how do you fix it?

**Solution:** Authorizing an **entire dataset** makes view creation/editing a sensitive privilege that can alter what source data is exposed. Restrict view creation/editing to **trusted publishers**, require SQL code reviews and negative tests, and use **individual authorized views** whenever broad dataset authorization isn't needed.

### Scenario C — Cloud Run Has Only Job User

Service `reports-api` on Cloud Run uses service account `reports-runtime`. It has `roles/bigquery.jobUser` on the execution project, yet querying the view returns 403.

**Question:** What additional permission should be granted?

**Solution:** Grant **Data Viewer on the view** (or approved shared dataset) to the **actual runtime service account**—never `BigQuery Admin` or project-wide Data Viewer. Confirm the source dataset authorized the view, and verify the Cloud Run revision's active service account matches `reports-runtime`.

### Scenario D — Aggregated View Still Leaks Information

A view returns course completions per cohort. One cohort has **a single learner**; a partner knows who that learner is and infers their completion status.

**Question:** Is stripping names and emails from SQL enough protection?

**Solution:** No. Evaluate **group sizes, suppression thresholds, auxiliary datasets, repeated/slicing queries**, and sharing agreements. A `HAVING COUNT(*) >= n` clause helps mitigate small-cell exposure but does not guarantee anonymity. Consider pre-reviewed aggregated tables, restricting arbitrary slicing, policy tags, and export controls based on risk.

### Scenario E — Can Read View, Cannot Run Job

An analyst has `BigQuery Data Viewer` on a view in `data-prod`; they submit queries from `analysis-sandbox` and get an error missing `bigquery.jobs.create`.

**Question:** Where should you grant permission under least privilege?

**Solution:** Grant `roles/bigquery.jobUser` on **`analysis-sandbox`**, where jobs are created and billed, while keeping Data Viewer scoped to the view in `data-prod`. Verify both resource locations and org policies; do not grant Job User or broad Data Viewer on `data-prod` if jobs are not run there.

### Quantitative Exercise — Logical View Costs

A report queried through an authorized view scans roughly **1 GiB of source data** per run according to initial measurements. There are 100 analysts, each running it four times per day.

1. Estimate daily processed volume assuming **no caching or optimization**. — `100 × 4 × 1 GiB = 400 GiB/day`.
2. If partition filtering cuts average bytes scanned to 0.25 GiB/run, what is the new estimate? — **100 GiB/day**.
3. Why can't you multiply 400 GiB by a single unit rate to guarantee the exact bill? — Billing could be **on-demand or capacity**, and caching, minimum billing thresholds, free tiers/editions, and query changes all apply.
4. Does reducing bytes scanned grant or revoke IAM permissions? — **No**; IAM and cost optimization are independent controls.

### Self-Check

1. **Does `bigquery.jobs.create` replace view read permissions?** — No; separate data access permissions are required.
2. **Can Data Viewer granted at the project level inherit down to multiple datasets?** — Yes, which is why project-wide grants are often overly broad.
3. **Where is an authorized view configured?** — On the **source dataset** the view needs to read.
4. **Does an analyst need Data Viewer on the source table when querying only an authorized view?** — No.
5. **Should you put the view and source table in the same dataset and grant viewer on that dataset?** — No, if the source table must stay hidden.
6. **Does an authorized dataset authorize future views created inside it?** — Yes, within that policy scope; view authors must be strictly trusted.
7. **Does an authorized view automatically guarantee complete anonymization of aggregates?** — No; re-identification risks must still be evaluated.
8. **Can a policy tag restrict a column even if a user holds Data Viewer on the dataset?** — Yes, when enforced.
9. **Does deleting a dataset binding revoke a role inherited from the project?** — No.
10. **Is querying a logical view with only a few columns guaranteed to be free?** — No; query processing charges still follow underlying scans and the billing model.

## 9. Implementation Checklist for Data Owners

| Item | Completion Criteria |
| --- | --- |
| **Ownership** | Source dataset and shared views have owners, SQL reviewers, and a review schedule. |
| **Resource separation** | Raw tables live in a **different dataset** from shared views; locations match. |
| **Inherited IAM** | Audited from organization/folder/project/dataset/table/view and Google Groups. |
| **Job permissions** | Consumers hold `bigquery.jobs.create` only on the intended execution project. |
| **Data permissions** | Consumers read only required views/tables, never raw source tables. |
| **Authorization entries** | Source datasets authorize only reviewed views/datasets. |
| **SQL authoring rights** | Trusted publishers separated from consumers; all view changes code-reviewed. |
| **Row/column protection** | Policy tags, masking, and row policies evaluated for sensitive fields. |
| **Testing** | Positive queries through the view, negative queries directly on source, and export/copy checks. |
| **Auditing** | Logs enabled, on-call owner assigned, revocation runbook covers copies and inherited roles. |
| **Cost/SLOs** | Query plans/dry runs, partition filters, quotas, billing, and latency monitored. |

## 10. Official Google Cloud Documentation

- [BigQuery — Control access to resources with IAM](https://cloud.google.com/bigquery/docs/control-access-to-resources-iam): IAM at project/dataset/table/view scope and inheritance.
- [BigQuery — Access control with IAM](https://cloud.google.com/bigquery/docs/access-control): roles, permissions, dataset sharing, and security principles.
- [BigQuery — Create an authorized view](https://cloud.google.com/bigquery/docs/create-authorized-views): two-dataset walkthrough, analyst permissions, and view authorization.
- [BigQuery — Authorized views](https://cloud.google.com/bigquery/docs/authorized-views): authorization scope, view SQL, and permission notes.
- [BigQuery — Authorized datasets](https://cloud.google.com/bigquery/docs/authorized-datasets): authorizing a dataset of views and required permissions.
- [BigQuery — Changes to dataset-level access controls](https://cloud.google.com/bigquery/docs/dataset-access-control): `getIamPolicy`/`setIamPolicy` and fine-grained ACL enforcement.
- [BigQuery — Row-level security](https://cloud.google.com/bigquery/docs/row-level-security-intro): row-based read controls.
- [BigQuery — Column-level access control](https://cloud.google.com/bigquery/docs/column-level-security-intro): policy tags and column access checks.
- [BigQuery — Data masking](https://cloud.google.com/bigquery/docs/column-data-masking-intro): masked vs. unmasked reader permissions.
- [BigQuery — Audit logs](https://cloud.google.com/bigquery/docs/reference/auditlogs): BigQuery operations and audit metadata.
- [BigQuery — Estimate query costs](https://cloud.google.com/bigquery/docs/best-practices-costs): dry runs, bytes processed, and cost controls.
- [BigQuery pricing](https://cloud.google.com/bigquery/pricing): query, storage, and edition pricing at deployment time.

**Conclusion:** effective BigQuery protection requires **granting the right principal the right operation at the right scope**. Consumers typically need **Job User on the execution project** plus **Data Viewer on the approved view/dataset**; authorized views are authorized by the source dataset to query underlying tables **without exposing direct read access** to consumers. Treat setup as complete only after verifying inherited permissions, view SQL, denied negative tests, audit/revocation runbooks, and real query costs.
