# IAM Conditions and conditional access grants on Google Cloud

> **Chapter:** IAM and authentication  
> **Lesson:** IAM Conditions and conditional access grants  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Selecting services, protecting resources, automating releases, and monitoring reliability and cost all require strict access control: the same engineer may need daily log viewing while requiring additional permissions only during incident response.

**IAM Conditions** let you pair an IAM role with a conditional expression to decide **when** a permission is granted. For example, a group can view project logs until the end of a support shift, or access only a set of resources with a matching name prefix or classification tag. Final access still depends on the entire active IAM policy set, including inherited permissions, conditions on other bindings, deny policies, and related access restrictions.

## 1. Learning objectives

After this lesson, you can:

1. Distinguish a standard IAM role binding from a **conditional role binding** and explain how conditional expressions participate in permission evaluation.
2. Read, write, and explain conditions using a subset of **Common Expression Language (CEL)**.
3. Choose the right attributes such as `request.time`, `resource.type`, `resource.name`, and `resource.matchTag()`; recognize limits by service and policy type.
4. Create a time-bound binding on a project via Console or `gcloud`, read it back, test access, and safely revoke it.
5. Spot cases where **unconditional bindings**, inherited permissions, or multiple bindings prevent a new condition from producing the desired restriction.
6. Design access examples for development/production environments, Cloud Storage, and incident response teams without confusing IAM Conditions with network protection or authentication.
7. Troubleshoot access errors using IAM Policy Troubleshooter, audit logs, and checking supported resources/attributes.

## 2. Where do IAM Conditions fit in the IAM system?

### 2.1. IAM allow policies and role bindings

In the standard IAM model, a **principal** (user, group, service account, or supported federated identity) receives a **role** on a resource. A role contains **permissions**; bindings on an organization, folder, or project can be inherited by child resources.

~~~text
Organization
└── Folder
    └── Project: gcp-app-prod
        ├── Cloud Run service
        ├── Cloud SQL instance
        ├── Compute Engine VM
        └── Cloud Storage bucket
~~~

A binding in an allow policy has the conceptual structure:

~~~yaml
bindings:
  - role: roles/logging.viewer
    members:
      - group:incident-response@example.com
    condition:
      title: TemporaryLogAccess
      description: Only for the incident response window
      expression: "request.time < timestamp('2027-01-15T18:00:00Z')"
version: 3
~~~

This is an **illustrative snippet**, not a complete policy to apply directly with an overwrite command. Real IAM policies may also contain `etag`, multiple bindings, and a policy version. When editing a policy, preserve existing bindings and protect concurrency with API-supported mechanisms.

In this example, the group receives `roles/logging.viewer` at the binding scope, **only when the request timestamp is earlier than the specified UTC cutoff**. The timestamp `2027-01-15T18:00:00Z` is illustrative for this lesson; in real usage, use the expiration approved by the resource owner.

### 2.2. A condition is not a default “deny”

In an **allow policy**, a condition attached to a binding only controls **whether that specific binding grants permissions**. If the condition evaluates to false, the binding grants nothing; however, the principal can still receive the same permission from another binding or from a parent resource.

~~~mermaid
flowchart TD
    R["Principal calls an API on a resource"] --> A{"Valid allow binding\nfor the required permission?"}
    A -->|No| N["Not granted by allow"]
    A -->|Has condition| C{"Condition expression = true?"}
    A -->|Unconditional binding| G["Granted by allow"]
    C -->|Yes| G
    C -->|No or unable to evaluate| N
    G --> D{"Deny policy / PAB /\nrelated controls allow?"}
    D -->|Yes| Y["API call may be permitted"]
    D -->|No| X["Access denied"]
    N --> X
~~~

This diagram simplifies evaluation order for learning; in practice, IAM evaluates relevant policies according to each policy type's rules. **A true condition is necessary, not sufficient** for an API call to succeed if a deny policy, Principal Access Boundary (PAB), organization control, service state, or other requirements block the operation.

### 2.3. Four easily confused cases

| State | Outcome to understand |
|---|---|
| Only one conditional binding and condition is `true` | That binding grants the role within its scope, provided no other control blocks it |
| Only one conditional binding and condition is `false` or context lacks required attributes | Binding does not grant permissions via allow |
| An additional **unconditional** binding grants the same permission | The unconditional binding can still grant access even after the conditional binding expires |
| Valid allow binding exists, yet deny policy or PAB blocks | Request is still denied under final policy evaluation |

Example: you add a temporary `roles/logging.viewer` binding for `alice@example.com`, but Alice already has unconditional `roles/logging.viewer` from another group at the organization level. When the condition expires, Alice **still retains log viewing access** from the inherited binding. To genuinely enforce a time limit, inspect the **effective grant paths**, not just the newest binding.

## 3. Expression structure and the CEL language

An IAM condition typically has three fields:

| Field | Required? | Meaning |
|---|---|---|
| `title` | Yes | Identifying name for the condition, e.g., `IncidentAccessUntilJan15` |
| `description` | No | Business purpose, ticket, approver, expiration timestamp |
| `expression` | Yes | Logical CEL expression evaluated against the request context |

CEL in IAM Conditions supports a **subset** of the CEL language, including comparison operators, type-specific functions, and logical operators. You cannot call arbitrary JavaScript or Python functions, make HTTP queries, or fetch external data during permission evaluation.

### 3.1. Comparisons and logic

~~~cel
// Example A: Access valid only before a timestamp.
request.time < timestamp('2027-01-15T18:00:00Z')

// Example B: Access valid only within a time window.
request.time >= timestamp('2027-01-10T00:00:00Z') &&
request.time < timestamp('2027-01-15T18:00:00Z')

// Example C: Matching resource type and specific name prefix.
resource.type == 'compute.googleapis.com/Instance' &&
resource.name.startsWith('projects/example-proj/zones/asia-southeast1-a/instances/dev-')
~~~

These three snippets are shown for reading comprehension; `//` comments explain the examples, so when entering into the Condition editor use a **valid single expression** without pasting multiple examples into one field.

| Symbol | Meaning | Example |
|---|---|---|
| `&&` | AND: all clauses must be true | Time window **and** resource type |
| `\|\|` | OR: at least one clause is true | Resource group A **or** B |
| `!` | NOT: negation | `!resource.matchTag(...)` |
| `==`, `!=` | Equal / not equal | `resource.type == '...'` |
| `<`, `<=`, `>`, `>=` | Comparisons | `request.time < timestamp('...')` |
| `startsWith()`, `endsWith()` | String prefix/suffix matching on supported attributes | `resource.name.startsWith('projects/...')` |

Use parentheses `(...)` to avoid precedence mistakes, especially when combining `&&` and `\|\|`. An overly broad OR condition can unintentionally widen access:

~~~cel
// Risk illustration only: access may be granted if EITHER clause is true.
resource.matchTag('123456789012/environment', 'dev') ||
request.time < timestamp('2027-01-15T18:00:00Z')
~~~

If the intent is “**must be the dev environment AND not yet expired**”, use `&&`.

### 3.2. Time and time zones

`request.time` represents when the request is evaluated. Comparing against `timestamp('...Z')` is straightforward to audit because `Z` denotes UTC. For schedules in local time zones, CEL provides supported time component functions and timezone parameters, though you must verify exact expressions and handle holidays/DST if applicable.

For example, a cutoff in Vietnam time: **18:00 on 2027-01-15 (UTC+7)** equals **11:00 UTC on 2027-01-15**. To expire at 18:00 Vietnam time, use:

~~~cel
request.time < timestamp('2027-01-15T11:00:00Z')
~~~

Do not write `2027-01-15T18:00:00Z` if the business requirement is 18:00 Vietnam time; that would expire at 01:00 the next morning in Vietnam time.

## 4. Attribute groups to know

| Group | Representative attributes / functions | Appropriate usage | Caveat |
|---|---|---|---|
| **Time** | `request.time` | Time-bound access, support windows | Broadly supported in allow conditions; use transparent UTC |
| **Resource type** | `resource.type` | Restrict role to a specific resource type | Type value must match exact official name |
| **Resource name** | `resource.name` | Target specific names or prefix/suffix groups | Only available on supported resource types; formats vary |
| **Service** | `resource.service` | Service scope where supported | Does not replace checking resource type when relying on name |
| **Resource Manager tags** | `resource.matchTag()`, `resource.hasTagKey()` | Distinguish environments/resource groups via tags | These are **tags**, different from labels; requires proper inheritance config |
| **Access level / HTTP** | `request.auth.access_levels`, `request.host`, `request.path` | Certain supported **IAP** scenarios | Not universally meaningful across all Google Cloud APIs |
| **Destination IP/port** | `destination.ip`, `destination.port` | **IAP TCP tunneling** conditions | Not a general-purpose IP filter for IAM |
| **API-specific** | `api.getAttribute(...)` | Constraints per supported API/call | Use only with documented permissions and services |

**Distinguish tags and labels:** Resource Manager **tags** are built to enforce policy across the resource hierarchy and use syntax like `resource.matchTag('123456789012/environment', 'dev')`. **Labels** are administrative/cost metadata on resources and do not automatically become `resource.matchTag` attributes. Never substitute labels for tags expecting IAM to recognize them.

### 4.1. Limitations when using `resource.name`

This is one of the most frequent sources of confusion. Resource names in CEL are **not necessarily the display name** in Console and **do not support `*` wildcards** like shell globs.

Example name of a VM:

~~~cel
resource.type == 'compute.googleapis.com/Instance' &&
resource.name.startsWith(
  'projects/example-proj/zones/asia-southeast1-a/instances/dev-'
)
~~~

A condition relying solely on `resource.name` can fail if a permission is checked against a resource type **that does not support the name attribute**. Google Cloud recommends scoping with **`resource.type`** when checking names. If a role includes permissions to read VMs, disks, instance templates, networks, or IAM across multiple layers, a condition on `Instance` alone can render auxiliary operations unavailable.

**Lesson:** verify each permission required by an operation, the resource type on which that permission is evaluated, and the table of supported attributes. Never assume “VMs starting with dev- mean every VM admin action will work” simply because an expression looks right.

## 5. Scenario A: granting time-bound log viewing access

**Context:** the incident response team needs log viewing permissions on project `training-incident` until the end of their shift. They do not need to modify services and must not retain log viewing access after the deadline. A Google Group `incident-response@example.com` is used as the principal for easy membership management.

**Approach:** grant `roles/logging.viewer` with a `request.time < ...` condition directly on the project, using the approved cutoff time.

### 5.1. Creating via Google Cloud Console

1. In Console, select the target sandbox project `training-incident`.
2. Go to **IAM & Admin → IAM**, click **Grant access** or edit an appropriate binding.
3. Add principal `group:incident-response@example.com` and role **Logs Viewer** (`roles/logging.viewer`).
4. In the IAM Condition section, choose to add a condition; set title `IncidentReadOnlyUntilJan15`, and a description listing ticket/owner and deadline.
5. In the **Condition editor**, enter:

~~~cel
request.time < timestamp('2027-01-15T18:00:00Z')
~~~

6. Use any linter/syntax validator provided by Console, save the condition, verify details, and **Save** the IAM change.
7. Confirm the IAM policy now shows the binding/condition with the right role, principal, and expiration. Then test access using an account within the assigned scope.

This operation **modifies live IAM permissions** and requires `resourcemanager.projects.getIamPolicy`, `resourcemanager.projects.setIamPolicy`, and related permissions; only perform it on an authorized project with approval.

### 5.2. Creating via gcloud in Cloud Shell

~~~bash
# Example: substitute PROJECT_ID and group before running.
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="group:incident-response@example.com" \
  --role="roles/logging.viewer" \
  --condition="title=IncidentReadOnlyUntilJan15,description=Approved incident window,expression=request.time < timestamp('2027-01-15T18:00:00Z')"
~~~

The `--condition` flag takes `title=...`, `description=...`, and `expression=...` pairs. Expressions containing commas may require `gcloud`'s specific delimiter/escaping syntax; check `gcloud help` on your installed version. Examples are written for Bash/Cloud Shell; PowerShell on Windows uses different line-continuation syntax.

To **read back** the bindings on the project:

~~~bash
gcloud projects get-iam-policy PROJECT_ID --format=json
~~~

Verify that the returned JSON shows the exact `role`, `members`, and `condition.title/description/expression`. Never rely solely on a “command succeeded” message: you must also verify **whether the principal has effective access** in real access scenarios.

### 5.3. Scenario-based testing

| Test case | Expectation from new binding | Conditions to verify |
|---|---|---|
| Group member, before cutoff, viewing logs | Binding can grant `roles/logging.viewer` | Right project, right group, not blocked by deny/PAB |
| Group member, after cutoff | Binding **no longer grants** the role | No unconditional binding or other group grants the same permission |
| User outside the group | Binding grants no access | May still hold the role from elsewhere |
| Group member tries to edit/delete logs | Logs Viewer role does not grant corresponding write/edit permissions | Must also inspect any other assigned roles |
| Command run immediately after granting | IAM synchronization delay may occur | Wait for propagation; retry with timestamps recorded |

For production incident response, consider **Privileged Access Manager (PAM)** if your organization needs request/approval workflows and time-bound privileged access instead of repeated manual grants and revocations.

## 6. Scenario B: restricting access to the development environment via Resource Manager tags

**Context:** the QA team needs to view resources tagged `environment=dev` within a folder containing multiple projects. Production environments must remain outside the new binding's scope.

Suppose the organization has numeric ID `123456789012`, tag key `environment`, and tag value `dev`, properly created and bound under Resource Manager tags.

~~~cel
resource.matchTag('123456789012/environment', 'dev')
~~~

This expression checks the **effective tag** of the resource in supported contexts. If you also want an expiration:

~~~cel
resource.matchTag('123456789012/environment', 'dev') &&
request.time < timestamp('2027-01-15T18:00:00Z')
~~~

**Checks before deployment:**

- Confirm the tag key/value exists and use the exact namespaced name or ID per Google Cloud docs. Tags can inherit from organization/folder/project depending on configuration.
- Choose an appropriate **read-only** role; bind the role at a scope covering the dev resources to be viewed.
- Check for **unconditional bindings** held by the principal at other organization/folder/project levels; this tag condition cannot revoke those automatically.
- Verify how the service evaluates tags, any extra permissions needed for listing, and behavior when a resource has no tag attached.
- Do not treat tags as a replacement for VPC firewalls, Cloud Run ingress settings, Cloud SQL private networking, or data residency controls.

If a dev project is mistakenly tagged `environment=prod`, requests may be denied or behave unexpectedly. Permissions to modify tags and edit tag policies must be controlled separately so nobody can alter tags to escalate their own access.

## 7. Scenario C: conditioning by object name in Cloud Storage

**Context:** the documentation team is allowed to read files in bucket `academy-training-assets` under least privilege.

Example condition matching only **object** resources under the prefix `objects/materials/`:

~~~cel
resource.type == 'storage.googleapis.com/Object' &&
resource.name.startsWith(
  'projects/_/buckets/academy-training-assets/objects/materials/'
)
~~~

Reading the expression:

- `resource.type` checks that the resource type is a Cloud Storage **Object**.
- `resource.name` uses Cloud Storage's **resource name format**, not `gs://...`.
- `startsWith` matches only names starting with that string; an object `objects/materials-v2/foo.pdf` is **not** under `objects/materials/`.
- Do not use `*` wildcards because `resource.name` does not interpret wildcard syntax.

**Important caveat on listing permissions:** a role such as `roles/storage.objectViewer` contains permissions evaluated at different levels; for instance, `storage.objects.list` is typically evaluated on the **bucket**, whereas reading object contents is evaluated on the **object**. A condition allowing only `resource.type == Object` can permit reading objects by known name while **disallowing listing**. If directory-style listing is needed, evaluate **managed folders**, IAM at the corresponding scope, and Cloud Storage–supported solutions instead of implicitly opening full-bucket listing.

**Do not assume:** prefix conditions do not replace choosing the right bucket scope, configuring uniform bucket-level access, verifying real paths, and applying other data protection policies. Test `get` and `list` requirements separately in a test environment.

## 8. Distinguishing conditions in allow, deny, and Principal Access Boundary

The term “IAM Conditions” appears across different policy types. Never copy an expression from an allow binding into a deny rule without checking supported attributes and **evaluation semantics**.

| Condition location | When does the condition affect access? | Typical attributes | Notes |
|---|---|---|---|
| **Allow policy role binding** | Grants the role if expression is `true` | Time, resource attributes, tags, and certain API/IAP attributes | `false` or unable to evaluate yields no grant |
| **Deny policy deny rule** | Applies deny if expression is `true` **or cannot be evaluated** | Resource tags per current support | Do not mechanically reuse allow `request.time` examples |
| **PAB policy binding** | Decides which principal sets the PAB policy applies to | `principal.type`, `principal.subject` | PAB binding conditions do not grant roles |
| **Unified Access Policies (UAP)** | Condition depends on rule type, permission, and service | IAM attributes or service-provided attributes | Support/release status may vary; check current docs |

Example **deny** condition using a production environment tag:

~~~cel
resource.matchTag('123456789012/environment', 'prod')
~~~

This condition is meaningful only as part of a **fully configured deny rule**, alongside the denied principals and permissions. Simply writing a CEL string does not create a deny rule. Deny has its own precedence semantics; never treat a deny expression as if it were an allow condition.

**PAB** defines which resources principals are eligible to access under an access boundary policy; it grants no permissions on its own. **Organization Policy** sets configuration governance constraints. **VPC Service Controls** add a data exfiltration protection perimeter for supported services. These are complementary layers chosen to fit the problem, not alternate syntax for a conditional role binding.

## 9. How IAM Conditions affect Compute Engine, GKE, Cloud Run, and data

In practice, conditions must serve a specific operation. When designing the Google Cloud module, use these questions to avoid picking the wrong attributes:

| Workload / service | Common access goal | What to check before applying a condition |
|---|---|---|
| **Compute Engine** | Administer `dev-` VMs or view VMs during a support window | Many operations also require permissions on disks, templates, and networks; which resource type/name is evaluated? |
| **GKE** | Access cluster management APIs with an IAM condition | GKE management IAM differs from in-cluster Kubernetes RBAC; conditions do not replace RBAC |
| **Cloud Run** | Allow only specific service accounts to invoke or deploy a service | Choose the right `roles/run.invoker`/deploy role and scope; ingress and HTTP auth still require configuration |
| **Cloud Storage** | Read objects in one document group | Distinguish object `get` from bucket `list`, `resource.name` format, and managed folder permissions |
| **Cloud SQL** | Manage instances or connect to data | Cloud SQL IAM admin differs from DB account privileges and network connectivity |
| **BigQuery** | Query datasets/tables conditionally | Check dataset/table scope, row/column security where needed; do not treat IAM Conditions as row filters |
| **Secret Manager** | Read a secret during incident handling | Check permissions and secret/version name format; avoid project-wide grants when unnecessary |
| **CI/CD** | Service account gets deployment permissions for a limited window | Bind minimal roles for the pipeline; restrict impersonation and log actions |

**Common boundary:** IAM Conditions govern **permissions on Google Cloud resources**, and do not automatically govern end-user authorization logic inside your Java/Spring Boot API. Applications still need JWT/session validation and business-layer authorization; GKE has Kubernetes RBAC; Cloud SQL has database-engine privileges.

## 10. Verification, troubleshooting, and lifecycle management

### 10.1. Pre-grant checklist

1. Record the requirement clearly: **who** (principal), **what action** (permission/role), **where** (resource/scope), **when**, and **why**.
2. Choose the **least-privileged predefined/custom role** that fits the operation, avoiding `roles/owner` and `roles/editor`.
3. Pick auditable conditions: time, resource type/name, or tags where supported.
4. List all **effective bindings** that could grant the same permission, including groups and organization/folder/project ancestors.
5. Verify resource format, service support, and auxiliary permissions required by the operation.
6. Set title/description containing context, owner, and deadline; link a ticket per internal process.
7. Test in a sandbox first, and document a revocation plan or recovery procedure in case users get locked out.

### 10.2. Using Policy Troubleshooter

**Policy Troubleshooter for IAM** investigates requests by triple:

- **Principal:** who calls the API (user/group/service account or relevant identity).
- **Permission:** atomic permission such as `logging.logEntries.list` or the actual permission required by the operation.
- **Resource:** target resource in the proper format.

Troubleshooter aggregates relevant allow/deny/PAB policies and explains why access is allowed or denied based on observable data. When conditions depend on time or contextual attributes, still verify the **request context** and test the real operation in a sandbox if needed. Access to the troubleshooter and visibility into policies are themselves governed by IAM.

**Do not confuse:**
- `PERMISSION_DENIED` is not always a bug in the IAM Condition itself; it can be a missing role, wrong account, deny/PAB, disabled API, or service constraint.
- `NOT_FOUND` does not prove a resource does not exist if view permissions are restricted.
- IAM policy changes can take time to propagate; do not loop into granting broader roles as a “quick fix”.

### 10.3. Audit logs and change control

For situational access grants, record:

| Attribute | Example data to retain |
|---|---|
| Requester and approver | Requester, approving team |
| Principal and role | `group:incident-response@example.com` + `roles/logging.viewer` |
| Scope | Project ID or specific resource |
| Condition | Title, expression, UTC expiry |
| Evidence | Ticket, business justification, policy version before/after |
| Validation | Which allow/deny cases were tested, and when |
| Cleanup | Owner responsible for revocation, cleanup date, readback result |

Inspect **Cloud Audit Logs** for IAM policy changes per log configuration and service support. Store only necessary details and control who can view audit logs, as logs can contain identifiers and sensitive metadata.

### 10.4. Revoking roles properly

When access is no longer needed, **remove the temporary binding** or remove the principal from the binding per procedure, then verify again. **Do not delete only the `condition` field** when your goal is revocation: turning a conditional binding into an unconditional binding can **permanently expand permissions**.

If editing policies via API/JSON, follow a **read–modify–write** pattern and preserve `etag`, `version`, and all other bindings. For conditions in allow policies, use the policy version supporting conditions (typically **version 3**). Avoid reading a policy, dropping `condition`, or accidentally overwriting a colleague's concurrent update.

## 11. Common design mistakes

| Mistake | Consequence | Proper fix |
|---|---|---|
| Adding a condition to a role when the principal already has an unconditional grant | Permissions remain after expiration | Inspect all effective access and inherited bindings |
| Attaching a condition to basic roles `roles/owner`, `roles/editor`, `roles/viewer` | Not supported for conditional allow bindings | Use another predefined role or suitable custom role |
| Attaching a condition to `allUsers` or `allAuthenticatedUsers` in an allow binding | Syntax/capability not supported in this case | Design supported authentication and member types |
| Using `resource.name` alone on a role spanning multiple resource types | Some permissions are not granted or behave unexpectedly | Pair with `resource.type` and test each permission |
| Using `*` to wildcard resource names | Condition does not behave like a glob | Use `startsWith()`, `endsWith()`, and exact format |
| Using **labels** instead of **tags** | `resource.matchTag` has no matching data | Configure Resource Manager tags |
| Using `request.ip` as a universal IAM attribute | No such general attribute exists across all Google Cloud APIs | Use IAP/access levels/service-supported network controls |
| Using an allow `request.time` condition inside a deny policy | Wrong supported attribute set | Check the attribute reference by policy type |
| Testing only `get` and forgetting `list` | Console/CLI fails to list even when object names are known | Check permissions on both bucket and object |
| Deleting the condition instead of deleting the binding | Accidentally creates an unconditional grant | Revoke the binding/principal properly |
| Using IAM conditions to replace internal API authorization | Leaks or wrongly blocks business data | Implement authorization checks inside the application and each service |

## 12. Guided practice: designing a policy for an incident response team

**Problem:** a company has project `retail-prod` containing Cloud Run Orders API, Cloud SQL, Cloud Storage, and centralized logs. The incident response team `ir-team@example.com` needs to **view logs from 2027-01-10 until before 2027-01-15 18:00 Vietnam time**, and strictly needs no permissions to modify workloads. The project already has other bindings.

### Step 1 — Translate requirements into IAM

| Component | Design |
|---|---|
| Principal | `group:ir-team@example.com` |
| Scope | Project `retail-prod` (simulate in sandbox first) |
| Role | `roles/logging.viewer` |
| Start timestamp | 2027-01-10 00:00 Vietnam time = 2027-01-09 17:00 UTC |
| End timestamp | 2027-01-15 18:00 Vietnam time = 2027-01-15 11:00 UTC |
| Additional controls | Audit overlapping grants from other groups, log changes, track expiration |

Expression:

~~~cel
request.time >= timestamp('2027-01-09T17:00:00Z') &&
request.time < timestamp('2027-01-15T11:00:00Z')
~~~

Using `>=` and `<` at the two boundaries avoids ambiguity at exact boundary timestamps. In real practice, replace example timestamps with approved times.

### Step 2 — Predict outcomes

| Request | Under the new binding |
|---|---|
| IR team member accesses on 2027-01-12 | Can be granted permissions by Logs Viewer |
| IR team member accesses on 2027-01-09 at 16:59 UTC | Not granted permissions by this binding |
| IR team member accesses on 2027-01-15 at 11:00 UTC | Not granted permissions by this binding |
| Staff outside IR team accesses on 2027-01-12 | Not granted permissions by this binding |
| IR team member tries to modify Cloud SQL | This role does not grant Cloud SQL admin permissions |
| IR member holds an additional unconditional grant from organization | May still view logs through that other grant path |

### Step 3 — Self-check

1. Verify UTC timestamps and their Vietnam-time equivalents for both boundaries.
2. Check title, description, and presence of **both** time conditions.
3. Inspect the project's IAM policy and inherited policies; detect any overlapping grants on other principals/groups.
4. Simulate “before window”, “inside window”, “exactly at end boundary”, and “outside group” cases.
5. Run Policy Troubleshooter for the log-reading permission and appropriate resource, paired with real tests when authorized.
6. Record the owner responsible for removing the binding; do not delete the `condition` field to revoke.

## 13. Self-assessment questions

1. **Binding X** unconditionally grants `roles/storage.objectViewer` to group A on a folder; **binding Y** conditionally grants the same role on a child bucket. When Y expires, does access from X automatically disappear? Why?
2. In an allow policy, a condition returns `false`. Is that equivalent to an **explicit deny** for the principal?
3. Why must you pay attention to `resource.type` and the supported resource list when checking `resource.name`?
4. Compare `resource.matchTag('123456789012/environment','dev')` with labels `env=dev` on a VM.
5. Why can a condition limited to `Object` cause a bucket `list` command to fail?
6. In deny policies and PAB policy bindings, are the semantics and attribute sets identical to allow bindings?
7. An engineer wants to restrict IAM permissions by IP across all Google Cloud APIs using `request.ip`. Is this design accurate? Name alternatives to research.
8. You added a conditional grant, yet the user still has access after expiration. Outline the investigation sequence.

**Suggested answers:**

1. No; the unconditional grant from the folder can still provide the same permission.
2. No; that binding grants no role, but the principal can still receive access from another binding.
3. Because not all resource types/permissions support `name` in the same way; `type` establishes the right evaluation context.
4. IAM tags are Resource Manager tags with dedicated syntax and policy mechanics; labels are not equivalent.
5. `storage.objects.list` is typically evaluated on the bucket, not the object; separate permissions and scopes must be checked.
6. No; deny conditions mainly support resource tags with different evaluation rules, while PAB binding conditions apply the policy to principals.
7. No; investigate IAP attributes, access levels, or service-specific network controls.
8. Look for unconditional bindings, other groups, or inherited permissions; verify principal, scope, UTC expiration, permission type, and effective policy, then run Troubleshooter.

## 14. Checklist for applying IAM Conditions

- [ ] Identified principal, role/permission, scope, and condition objective.
- [ ] Selected the least-privileged role and identified accompanying permissions.
- [ ] Checked for bindings that could grant equivalent permissions, including at ancestors.
- [ ] Used valid CEL, UTC timezone, `resource.type`, and proper `resource.name` format.
- [ ] Distinguished Resource Manager **tags** from labels and verified inheritance.
- [ ] Verified attribute support for the exact service, resource type, and policy type.
- [ ] Confirmed conditions do not replace deny/PAB, network policies, or business authorization.
- [ ] Tested both allowed and denied cases, including boundary expiration times.
- [ ] Recorded approval context, change trail, and owner responsible for revocation.
- [ ] Read back the IAM policy after changes and did not accidentally turn a binding unconditional.

## 15. Official documentation

Syntax and attribute support can be updated by Google Cloud. When implementing on real projects, verify against current docs and CLI help for your installed version:

- [Overview of IAM Conditions](https://docs.cloud.google.com/iam/docs/conditions-overview)
- [Attribute reference for IAM Conditions](https://docs.cloud.google.com/iam/docs/conditions-attribute-reference)
- [Resource attributes for IAM Conditions](https://docs.cloud.google.com/iam/docs/conditions-resource-attributes)
- [Manage conditional role bindings](https://docs.cloud.google.com/iam/docs/managing-conditional-role-bindings)
- [gcloud projects add-iam-policy-binding](https://docs.cloud.google.com/sdk/gcloud/reference/projects/add-iam-policy-binding)
- [Troubleshoot IAM-related policies](https://docs.cloud.google.com/iam/docs/troubleshoot-policies)
- [IAM policy types and evaluation](https://docs.cloud.google.com/iam/docs/policy-types)

**Key takeaway:** IAM Conditions are a tool to **narrow when a single binding grants access**, using expressions that must be valid in supported contexts. Effective security requires checking **all effective permissions**, using least-privileged roles, testing edge cases, and managing the binding lifecycle. From that foundation, teams deploying on Google Cloud can protect Compute Engine, GKE, Cloud Run, storage, and database resources while meeting operational, release, and incident-response needs.
