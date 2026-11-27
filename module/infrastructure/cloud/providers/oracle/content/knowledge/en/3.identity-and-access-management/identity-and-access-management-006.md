# Policy Conditions, Network Sources, and Access Control

An IAM policy in Oracle Cloud Infrastructure (OCI) does not have to grant the same permission under every circumstance. Beyond subject, action, and compartment, a policy can include conditions that restrict when a statement applies.

For example, a learner group may read objects from a lab bucket, but only when requests originate from a network source accepted by the organization. This problem combines three parts: the principal's permissions, the policy condition, and how OCI identifies the source of a request.

This lesson guides you through building conditions, using network sources, and verifying effective permissions in a lab environment. The policies and addresses below are learning examples; do not apply them verbatim to a tenancy without substituting real identities, scopes, and addresses.

## 1. Lesson Objectives

After this lesson, you will be able to:

- Read the condition clause in an OCI policy statement.
- Distinguish between `all` and `any` logical combinators.
- Explain the role of `request.networkSource.name`.
- Design a network source based on an appropriate public egress or VCN.
- Distinguish IAM conditions from routes, NSGs, and application connectivity controls.
- Detect other policies that broaden effective permissions beyond expectations.
- Build a test suite covering both allowed and denied scenarios.

This lesson focuses on OCI resource access permissions. Identity domain sign-on rules, SSH connectivity, and in-database privileges are related control layers, but they are not automatically configured by the policies illustrated here.

## 2. Reviewing Policy Statement Structure

General form:

~~~text
Allow <subject> to <verb> <resource-type> in <location> where <condition>
~~~

Key components:

| Component | Question to Answer |
| --- | --- |
| subject | Who or which principal receives the permission? |
| verb | Which level of operation is granted? |
| resource-type | Which type of resource? |
| location | In which tenancy or compartment? |
| condition | Granted only when which conditions evaluate true? |

Example without a condition:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab
~~~

In this example, `Default` is the identity domain name and `LabReaders` is a group within that domain. Replace these with actual names and subject identifier syntax appropriate for your tenancy. If names contain spaces or characters requiring special handling, use OCI-supported quoting/representation.

`learning-lab` is the compartment scope in this example. Policy storage placement and compartment hierarchy must permit the statement to govern that scope. If your environment uses nested compartment paths, specify the scope using supported identifiers rather than relying on a name that might collide.

Never attach a policy in a child compartment and expect it to grant permissions across parent compartments or the entire tenancy.

### 2.1. Conditions Restrict One Grant Statement

Adding a condition:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where request.networkSource.name = 'corpnet'
~~~

The statement means: the matching group receives object read access in the stated scope when the request matches the `corpnet` network source.

It does not mean:

- Every principal coming from `corpnet` has read access.
- This group can read every resource type in the compartment.
- All permissions of this group are restricted to `corpnet`.
- OCI has created routes or firewalls for the user.
- Console sign-in has been restricted to `corpnet`.

A condition is only one part of evaluating that specific grant statement.

### 2.2. Other Policies Can Still Grant Permissions

Suppose in addition to the statement above there is also:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab
~~~

The second statement grants object read access without any network source condition. Within that IAM scope, adding a conditional statement does not narrow the permission already granted by the unconditional statement.

Permissions can come from:

- Multiple policies taking effect together.
- Policies at a parent compartment.
- Other groups of which the user is a member.
- Another principal being used by a tool.

To confirm "only from `corpnet`," inspect all relevant grant paths. Never use a narrow policy to simulate a global deny rule.

## 3. How to Write Conditions

### 3.1. Request Variables and Target Resource Variables

Conditions typically use contextual variables:

| Group | Example | What It Reflects |
| --- | --- | --- |
| Request | `request.networkSource.name` | Network source matching a network source definition |
| Request | `request.operation` | API operation being evaluated |
| Request | `request.permission` | Permission being evaluated for the request |
| Target | `target.bucket.name` | Target bucket for operations supporting this variable |

Not every variable makes sense for every operation. Check which variables and conditions are supported for the specific resource type and API.

For instance, an operation listing multiple buckets is not targeting a single bucket. A condition requiring a target variable absent from the request context can prevent that statement from granting permission for that operation.

Do not use a "not equal to a value" comparison to assume a request is definitely allowed when the variable is absent. Evaluation depends on whether the variable applies in context and on OCI's condition evaluation rules.

### 3.2. `all`: Every Condition Must Be True

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where all {target.bucket.name = 'lab-artifacts', request.networkSource.name = 'corpnet'}
~~~

The statement simultaneously requires:

1. The target bucket is `lab-artifacts`.
2. The request matches the `corpnet` network source.

If either condition is false or inapplicable in context, do not assume this statement grants permission.

### 3.3. `any`: Only One Condition Needs to Be True

Example allowing two network sources:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where any {request.networkSource.name = 'corpnet', request.networkSource.name = 'lab-egress'}
~~~

The statement accepts requests matching either listed network source, provided the remaining subject, action, and scope parts also match.

Do not confuse this with the following example:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where any {target.bucket.name = 'lab-artifacts', request.networkSource.name = 'corpnet'}
~~~

This example does not require both the right bucket and the right source simultaneously. Under `any` logic:

- Matching the bucket can satisfy the condition even when the source is not `corpnet`.
- Matching the source can satisfy the condition for a different bucket within the statement's scope.

If the requirement is "the right bucket AND the right source," you must use `all`.

### 3.4. A Truth Table Helps Review Logic

| Right Bucket? | Right Source? | `all` | `any` |
| --- | --- | --- | --- |
| Yes | Yes | True | True |
| Yes | No | False | True |
| No | Yes | False | True |
| No | No | False | False |

This is the logic table when both variables are present in context. When a variable is not supplied by the API or does not apply, check the service's actual evaluation rules.

Before deploying a policy, translate each condition into plain prose. If the business requirement says "and" while the policy uses `any`, revisit it immediately.

## 4. What Is a Network Source?

### 4.1. A Named Network Source Definition

A network source in OCI IAM describes request origins identified by supported network attributes. A policy can reference that source via:

~~~text
request.networkSource.name = 'corpnet'
~~~

A network source can be built from suitable components such as:

- Public IPs or public CIDRs of the access origin.
- A specific VCN and corresponding private IP ranges via supported mechanisms.

The name `corpnet` is a network source name, not a hostname, subnet name, or security list name.

A network source is a tenancy-scoped IAM governance object, not a rule automatically attached to every subnet.

### 4.2. Public Sources Are Usually Post-NAT Addresses

Suppose a learner's laptop has private address `192.168.1.20` and calls OCI APIs over the office network. If traffic traverses office NAT, the public source observed by the service may be the office's egress IP.

Putting `192.168.1.0/24` into the public source list does not make it the public source address of the request.

Trace the actual path:

~~~text
Learner machine
  -> Organization VPN/proxy/NAT
  -> Network path to OCI endpoint
  -> Service receives request
~~~

If a user enables a VPN, routes through a proxy, or switches to mobile data, the egress address can change. Network sources must be designed around organization-approved access paths, not the address shown on a user's local network interface.

A shared public IP also does not uniquely identify one user. IAM still evaluates the principal and all other authorization components.

### 4.3. VCN Sources Require Both Network Identity and Matching IP Ranges

When declaring a VCN source, specify both the exact VCN and private IP ranges per configuration requirements. Never write a `10.x.x.x` range alone and assume every VCN using that range is permitted.

Conceptual example:

~~~text
Network source: lab-private

VCN:           OCID of the authorized lab VCN
Private range: 10.42.4.0/24
~~~

VCN source identification depends on the supported service access path. Accessing OCI services through a service gateway presents different source network context than going out to a public endpoint through NAT or an Internet Gateway.

Do not assume that because an instance resides inside a VCN, all of its requests are recognized as a VCN source. If requests traverse NAT to a public endpoint, check what source context the service actually sees.

Before placing a VCN source into a policy, verify the service, network path, and support conditions for that exact access pattern.

### 4.4. Do Not Rely on Client-Supplied Headers

A client address written in an application header does not become the source IAM evaluates for network sources.

Never instruct users to add `X-Forwarded-For` or similar headers to satisfy a condition. Determine origins using OCI-supported mechanisms and actual network paths.

## 5. Network Sources Do Not Replace Other Layers

| Layer | Purpose | Does a Network Source Configure It? |
| --- | --- | --- |
| Route table, gateway | Establish network routing paths | No |
| NSG, security list | Control traffic per network architecture | No |
| IAM policy | Allow principals to perform resource operations | Network source acts as a condition when referenced |
| TLS and API authentication | Protect transport, verify identity | No |
| SSH and OS accounts | Server access | No |
| Database users, roles, and SQL privileges | Access inside the database | No |
| Identity domain sign-on policy | Control login sessions per identity configuration | Not altered automatically by resource policies |

A request can be denied by IAM even when network connectivity works. Conversely, a principal with valid IAM permissions still cannot reach the endpoint without proper routing or DNS.

A network source condition in a resource policy does not inherently block OCI Console sign-in from other networks. A user may succeed in signing in while a specific resource operation is denied.

Access paths such as public objects, pre-authenticated requests, or data-plane protocols have separate authorization mechanisms that must be reviewed independently. Never claim that a single conditional IAM policy covers every way data can be read in the system.

## 6. Designing the Lab Scenario

### 6.1. Business Requirements

The learner group needs to:

- Read objects in the `lab-artifacts` bucket of the `learning-lab` compartment.
- Perform these requests only from an organization-approved egress.
- Not write or delete objects.
- Not read objects in other buckets via the lab statements.
- Not modify the network source definition themselves.

The illustrative principal is the `Default/LabReaders` group. Resources and network sources must be prepared or scoped appropriately by the lab administrator.

### 6.2. What to Confirm Beforehand

| Component | Required Information |
| --- | --- |
| Principal | Exact account, domain, and group |
| Scope | Actual compartment OCID, bucket, and region |
| Public source | Actual egress of the permitted access path |
| Private source (if used) | VCN, private range, and service access path |
| Baseline permissions | Other policies currently granting access to the principal |
| Test data | An existing non-sensitive object |
| Access path | Actual endpoint and tool used to call the service |

CIDRs such as `198.51.100.0/24` or `203.0.113.0/24` appearing in documentation examples are reserved documentation ranges. Never copy them as your organization's real egress.

If the real public egress is unknown, confirm it with your network administrator through approved organizational channels. Never substitute a laptop's private IP.

## 7. Creating the Network Source and Conditional Policy

### 7.1. Separating Administrators and Users

An IAM administrator or authorized delegate creates the network source, reviews policies, and logs changes. The learner group receives only the permissions needed to use the required resources.

In particular, never grant a restricted group the ability to edit the network source so they can widen allowed sources themselves. Changing one IP range in a network source can affect multiple policies referencing it.

There is no need to grant tenancy-wide administrator rights to learners just to run verification tests.

### 7.2. Creating the Network Source

In the IAM administration section of the Console, open Network Sources or the equivalent feature in the current UI.

Follow these steps:

1. Give it a clear purpose-driven name, such as `corpnet`.
2. Describe the owning team, egress path, and intended scope of use.
3. Declare public IPs/CIDRs or VCN sources according to design.
4. Check CIDR formatting and boundaries.
5. Verify you did not accidentally include an overly broad range.
6. Save and read back the definition.

Never use `0.0.0.0/0` as a "quick fix" when a source fails to match. That configuration defeats the goal of restricting public origins.

Successfully creating the network source only confirms the definition was saved. It does not prove test requests will match or that policies reference it properly.

### 7.3. Granting Conditional Object Read Access

Primary illustrative policy:

~~~text
Allow group Default/LabReaders to read objects in compartment learning-lab where all {target.bucket.name = 'lab-artifacts', request.networkSource.name = 'corpnet'}
~~~

This statement focuses on object read access in the target bucket. Do not use `manage object-family` when the goal is only reading.

Before saving, verify:

- The subject specifies the right domain and group.
- The compartment matches the right scope and policy attachment location.
- The bucket name matches the assigned resource.
- The network source exists and is referenced by exact name.
- `all` is used to require both conditions simultaneously.
- No other unconditional statement grants broader overlapping permissions.

Comparison rules and target variables must be checked against the exact Object Storage operations you plan to use rather than extrapolated to other services.

### 7.4. Console Navigation Permissions May Require Another Statement

Reading objects and listing buckets are two distinct operations. If learners need to view the bucket list in the Console, appropriate metadata permissions may be required.

Supplemental example:

~~~text
Allow group Default/LabReaders to inspect buckets in compartment learning-lab where request.networkSource.name = 'corpnet'
~~~

This statement allows scoped `inspect` capability without granting object content reads across all buckets. It can expose metadata of multiple buckets in the compartment, so add it only if the lab goals accept that level of visibility.

Do not mechanically attach a `target.bucket.name` condition to a multi-bucket list operation and assume it will return a single-row filtered list. IAM policies are not per-object result filters for every API.

If you want to avoid granting broad listing access, test directly against the provided bucket and object names using an appropriate CLI/API tool. Any secondary Console operations still require separate evaluation.

### 7.5. Controlled Propagation Waiting

After editing a policy or network source, it may take time for changes to propagate completely.

Do not rapidly tweak multiple conditions just because the first attempt failed. Record the change timestamp, wait within your operational runbook threshold, and re-test the exact same case.

Meanwhile, verify the principal, endpoint, bucket, and network source. Waiting longer will not fix a misspelled group name or wrong CIDR.

## 8. Testing Both Allow and Deny Directions

### 8.1. Test Matrix

Below are the expected outcomes for permissions from the lab statements, assuming no other policy grants broader access:

| Principal and Request | Source | Expected Outcome |
| --- | --- | --- |
| `LabReaders` reads known object in `lab-artifacts` | Matches `corpnet` | Allowed |
| Same principal reads same object | Does not match `corpnet` | Not granted by lab statements |
| `LabReaders` reads object in another bucket | Matches `corpnet` | Not granted by lab object-read statement |
| `LabReaders` writes or deletes lab object | Matches `corpnet` | Not granted by lab statements |
| Principal without corresponding grant reads object | Matches `corpnet` | Not allowed solely due to network source |
| `LabReaders` lists buckets | Matches `corpnet` | Depends on whether `inspect buckets` statement was added |

Do not run write or delete tests against valuable data. Mutation tests require authorized disposable resources or appropriate permission-evaluation methods.

For read-only labs, verify the allowed/denied read cases and audit statements to assess mutation rights, explicitly noting any cases not executed live.

### 8.2. Use the Same Identity When Comparing Two Sources

To conclude that a network condition is working, hold steady:

- Principal and authentication configuration.
- API or operation.
- Endpoint and region.
- Bucket, object, and namespace name if required by the API.
- Timing relative to the policy change.

Change only the source access path according to an approved test plan. If you use user A in the office and user B at home, differing results do not prove the cause is the network source.

Never turn on an unauthorized VPN or borrow someone else's machine to test bypassing conditions.

### 8.3. Example Checking Object Metadata with OCI CLI

This is a learning example, not an automatically executed command. It requires OCI CLI authenticated with the right principal, appropriate region, and an existing test object.

~~~powershell
$env:OCI_OS_NAMESPACE = "<actual-namespace>"
$env:OCI_LAB_REGION = "<bucket-region>"

oci os object head --namespace-name $env:OCI_OS_NAMESPACE --bucket-name lab-artifacts --name policy-check.txt --region $env:OCI_LAB_REGION
~~~

The `head` operation reads object metadata without downloading content to a file or creating objects. Replace placeholder values with actual lab values.

Test the same operation from an authorized access path and from an out-of-scope path within your approved test scope.

If the command fails, do not immediately blame the network source. Confirm the object exists, namespace is accurate, region is correct, principal is right, and network connectivity works.

### 8.4. Do Not Use the Console Alone as Evidence

A single Console page can invoke multiple APIs: listing buckets, fetching metadata, listing objects, and reading objects. One denied auxiliary call can make the page display an error even when the target operation's policy is valid.

Conversely, seeing a bucket name in the Console does not prove permission to read objects. Verify the exact action referenced by the business requirement.

Record outcomes per specific API or operation rather than simply writing "Console works" or "Console errored."

## 9. Investigating Unexpected Results

### 9.1. Still Readable Outside the Allowed Source

Check:

1. Whether the actual principal is really the test account.
2. Whether another group grants read or admin permissions.
3. Whether an unconditional statement exists at a parent compartment or another scope.
4. Whether the request actually traversed a different egress, or still exited via corporate VPN/proxy.
5. Whether the read went through the designed IAM API or through another sharing mechanism.
6. Whether the network source was configured more broadly than intended.
7. Whether you are inspecting fresh service data or cached content.

A narrow policy never revokes a broad permission granted elsewhere. Locate that grant path and remediate it per governance responsibility.

### 9.2. Still Denied Inside the Allowed Source

Check:

- Domain name, group name, and group membership.
- Policy placement and actual compartment of the resource.
- Whether the condition variable applies to the API being called.
- Whether bucket and object names are exact.
- Whether the real egress falls inside the declared CIDR.
- For VCN sources, whether the VCN and service access path match.
- Whether permissions exist for auxiliary operations invoked by the tool.
- Whether the recent change has had adequate time to propagate.

Never resolve this by opening all sources or escalating to `manage all-resources`. Identify the mismatched condition first.

### 9.3. Cannot Reach the Endpoint

If DNS, TLS, or network transport fails before receiving an API response, check the network path and endpoint first.

IAM conditions do not create a service gateway, NAT Gateway, or private endpoint connectivity. A valid policy cannot fix a missing route.

Nor should you treat a timeout as proof that IAM blocked access properly. A permission denial must be distinguished from an unreachable service.

### 9.4. Using Audit and Request IDs

When corresponding data is available, cross-reference:

- Timestamp and principal.
- Service, operation, and resource.
- Request ID.
- Source address or network details actually recorded by the event.
- Outcome and error message.

Do not assume every Audit event contains the network source name or a full explanation of which statement made the decision. Detail varies by service and event type.

Keep test data minimal; never include private keys, tokens, or authentication headers in reports.

## 10. Governing Network Source Changes

### 10.1. Shared Definitions Carry Wide Blast Radius

If multiple policies reference `corpnet`, adding one CIDR to `corpnet` expands the network condition across all of those statements simultaneously.

Before making a change, know:

- Which policies reference it.
- Which groups and resources are affected.
- Who owns the new range and whether it is stable.
- Whether you are expanding into an overly broad shared network.
- How to test and roll back to the previous configuration.

Do not audit policies only when editing statements; modifying a network source is also an access-control change.

### 10.2. Avoid Depending on Unstable Egress

A network source based on the public IP of a residential connection can stop working when the ISP rotates addresses. Users can also exit through multiple egress points depending on VPNs or failover paths.

An operational plan should specify:

- Approved sources.
- How updates are handled when egress changes.
- Approvers.
- Expiration dates for exceptions.
- Post-change verification procedures.

Never solve inconvenience by opening huge IP ranges without impact assessment.

### 10.3. Preserve Appropriate Administrative Recovery

Before rolling out conditions broadly, test with a lab group and non-critical resources. Administrators must have an organization-approved recovery plan if a misconfiguration disrupts legitimate access.

This does not mean creating an unmanaged admin account outside all controls. Recovery paths must themselves be protected, assigned, and tested.

## 11. Complete Practical Workflow

### Step 1: Confirm Inputs

Obtain or verify:

- Test identity and associated groups.
- Existing compartment, bucket, and object.
- Permitted network source and out-of-scope test source.
- Person authorized to create policies and network sources.
- Broad statements that must be accounted for in effective permissions.

Do not alter shared environment policies solely to make lab results easier to observe.

### Step 2: Record Baseline Permissions

Run the permitted read test operation and record the result. Identify which existing permissions produced the baseline result before adding new statements.

If the principal already holds broad administrative permissions, do not use it as evidence for conditional read policy effectiveness. Use a test principal with an appropriate permission scope.

### Step 3: Configure Under Control

The authorized administrator:

1. Creates or reuses the properly scoped network source.
2. Adds the object read statement using `all`.
3. Adds `inspect buckets` only if needed and metadata visibility is accepted.
4. Records the configuration along with the change timestamp.
5. Waits for propagation and then verifies.

### Step 4: Execute the Test Matrix

Prioritize:

- Right principal, right bucket, right source.
- Same principal and target, out-of-scope source.
- Right source, out-of-scope target.
- Distinguish object read operations from bucket list operations.

For cases you are not authorized to run, explicitly mark them as not tested rather than marking them passed.

### Step 5: Report Outcomes

| Test Case | Principal | Actual Source | Operation and Target | Expected | Observed | Conclusion |
| --- | --- | --- | --- | --- | --- | --- |
| Valid read | Lab identity | Matches `corpnet` | HEAD lab object | Allowed | Actual result | Pass or investigate |
| Outside source | Same identity | Does not match | Same object | Not granted by lab policy | Actual result | Pass or investigate |
| Outside bucket | Same identity | Matches `corpnet` | Object in another bucket | Not granted by lab read statement | Actual result | Pass or investigate |

If results differ from expectations, document the verified root cause or missing evidence. Never draw conclusions from an error code alone without checking target objects and baseline grants.

### Step 6: Wrap Up the Lab

- Remove lab-only statements when instructed.
- Check referencing policies before modifying or deleting a network source.
- Keep shared network sources intact if others still use them.
- Revoke test group memberships per procedure.
- Archive the final configuration and permissible test evidence.

Never delete buckets or data merely to close an IAM exercise if they belong to another lab or are shared.

## 12. Self-Check

### Question 1: How do `all` and `any` differ?

`all` requires every condition inside to be true; `any` requires at least one condition to be true. When the business requirement is both the right bucket and the right source, using `any` can widen permissions unintentionally.

### Question 2: Given an unconditional read policy, does adding a read policy with a network source narrow access?

No. A conditional statement does not cancel a broader statement. You must inspect effective permissions across all relevant sources.

### Question 3: Is a laptop's private IP the public source OCI APIs see?

Usually not, if requests traverse NAT to a public endpoint. Identify the real egress and how the service recognizes the origin.

### Question 4: Does creating a network source automatically block SSH from external networks?

No. SSH requires controlling network paths, NSGs/security lists, and OS configuration. IAM conditions apply to resource operations governed by the corresponding policies.

### Question 5: Why can reading an object succeed via a direct CLI/API tool while the Console still shows an error?

The Console may invoke extra list or metadata APIs that have not been granted. Check each operation individually rather than treating all Console calls as a single permission.

### Question 6: Does a request timeout prove the network source denied it?

No. Timeouts can stem from DNS, routing, firewalls, or endpoints. Distinguish connectivity failures from service authorization denials.

### Question 7: Can someone authorized to edit a network source affect access permissions?

Yes. Widening a source definition can cause multiple referencing policies to accept additional requests. Permission to edit network sources must be governed as an access-control change.

## 13. Verification Checklist

- [ ] Subject, domain, and group are accurate.
- [ ] Policy placement and target compartment are verified.
- [ ] Verb and resource type are sufficient without exceeding lab requirements.
- [ ] Condition variables apply to the exact APIs used.
- [ ] `all` or `any` accurately reflects business requirements.
- [ ] Network source uses actual egress or VCN rather than illustrative documentation addresses.
- [ ] Paths through NAT, proxies, or service gateways are identified where relevant.
- [ ] Other statements and groups that could grant broad access have been audited.
- [ ] IAM is distinguished from networking, Console sign-in, and application data access.
- [ ] Both allowed and denied cases were tested with an appropriate principal.
- [ ] Results were verified per specific operation, source, and target object.
- [ ] Ownership and a change process exist for the network source.

Policy conditions are effective when they accurately reflect request context and are verified alongside all effective permissions. Network sources add a constraint on where requests originate; identities, resource scopes, and network layers must still be designed completely.
