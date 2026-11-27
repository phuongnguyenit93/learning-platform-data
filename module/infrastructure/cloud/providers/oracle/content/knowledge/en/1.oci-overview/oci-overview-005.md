# OCIDs, Service Endpoints, and Resource Lifecycle

When working with Oracle Cloud Infrastructure (OCI), three questions appear in almost every operation: **which resource are we referring to**, **where should the request be sent**, and **what is the resource ready to do**. OCIDs, service endpoints, and resource lifecycles answer those questions respectively.

These three concepts are closely related yet do not substitute for one another. Having the right OCID does not mean the account is permitted to access it. Sending a request to the right endpoint does not guarantee the resource resides in that region. Receiving a successful resource-creation response also does not mean the application inside is serving users yet.

This lesson builds a disciplined approach to reading and checking OCI resource information before diving into IAM, VCN, Compute, storage, and Oracle database services.

## 1. Lesson Objectives

After this lesson, you can:

- Distinguish OCIDs, display names, compartments, and service access addresses.
- Explain the main components commonly seen inside an OCID.
- Select the right region, realm, and endpoint context when calling an API.
- Distinguish infrastructure state from application readiness.
- Handle asynchronous requests, work requests, and state polling properly.
- Avoid creating duplicate resources or deleting the wrong resource during automation.
- Record sufficient information for operations, troubleshooting, and cost control.

## 2. Identifying an OCI Resource

### 2.1. What Is an OCID?

OCID stands for **Oracle Cloud Identifier**, a unique identifier assigned by OCI to resources that use this identification mechanism.

For example, when creating a Compute instance, the resource is assigned an OCID. API calls that retrieve information, change state, or terminate the instance typically use the OCID to specify the exact target object.

Do not assume every child object in every service has its own OCID. Some APIs locate objects by name, path, or composite key. In Object Storage, for instance, object operations typically use namespace, bucket name, and object name rather than a per-object OCID.

The key takeaway is: use the exact identifier type required by the resource's API, rather than trying to turn every name or path into an OCID.

### 2.2. OCID Differs From Display Name

Display names serve humans. OCIDs serve exact resource referencing.

| Property | Display Name | OCID |
| --- | --- | --- |
| Purpose | Readable, easy to find in the Console | Identifies a specific resource |
| Who determines it | Usually set by the user or a tool | Assigned by OCI |
| Guaranteed globally unique | No | Yes, for OCID identifiers |
| Reliable for distinguishing two resources with the same name | No | Yes |
| Suitable as direct reference in many resource APIs | Only when the API supports lookup by name | Yes, when the API requires an OCID |
| Changes when the resource is renamed | Name changes if the service supports it | OCID of the same resource stays unchanged |

Two instances in two compartments can both be named **app-prod-01** while having two different OCIDs. A new instance created to replace an old one also receives a new OCID, even if you reuse the same name.

Therefore, an automation script that searches by name and picks the first result risks operating on the wrong resource. If lookup by name is necessary, add conditions such as compartment, region, tags, and state, and explicitly handle multiple matches.

### 2.3. Compartment OCID and Resource OCID Do Not Play the Same Role

A resource creation command typically needs a **compartment OCID** to specify where the resource is placed. A command to retrieve or update a specific resource typically needs the **resource OCID** of that exact resource.

For example:

~~~text
compartment-id : which governance scope does the resource belong to?
instance-id    : which specific Compute instance are we operating on?
subnet-id      : into which specific subnet should the VNIC be placed?
~~~

You cannot pass a VCN OCID into a subnet ID field just because the subnet resides in that VCN. Similarly, a tenancy OCID does not substitute for an instance OCID.

The tenancy serves as the root compartment in appropriate API contexts, but that does not mean you can pass the tenancy OCID for every parameter ending in “id”.

## 3. Reading OCIDs at the Right Level

### 3.1. General Structure

The general form used to explain OCID structure is:

~~~text
ocid1.<RESOURCE_TYPE>.<REALM>.[REGION][.FUTURE_USE].<UNIQUE_ID>
~~~

In this representation, square brackets indicate parts that may be absent or empty in certain OCID formats; they are not characters to copy into API requests.

| Component | Meaning |
| --- | --- |
| ocid1 | Marker of the OCID format |
| RESOURCE_TYPE | Resource type, such as instance, vcn, or compartment |
| REALM | Cloud deployment realm to which the resource belongs |
| REGION | Region info if that OCID type uses it |
| FUTURE_USE | Reserved segment in the identifier structure |
| UNIQUE_ID | System-generated portion ensuring uniqueness |

This is not a rule for users to construct OCIDs manually. In real work, copy the full OCID from the Console, an API response, or deployment tool output.

In documentation and shared examples, it can be masked like this:

~~~text
Masked instance OCID:
ocid1.instance.<realm>.<region>.<masked-identifier-part>
~~~

The string above is only a conceptual illustration, not a valid OCID for calling an API.

### 3.2. Do Not Over-Infer From the OCID String

Parts of an OCID help recognize the resource type or deployment context. However, do not parse the string to infer all operational details.

An OCID is not a reliable source for inferring:

- Current display name.
- Current compartment.
- Running or stopped state.
- IP address or hostname for connecting.
- Business owner.
- Effective IAM policies.
- Usage or cost.

To obtain that information, call the appropriate API or inspect the relevant configuration and management systems.

Do not split an OCID on dots and assign fixed meanings to every position across all services. Segments that may be empty, formatted differently, or omit region info must be handled according to official service and tool documentation.

In particular, the region portion of an OCID is not a contract for constructing URLs manually. A safer approach is to configure the region in the SDK/CLI and let the tool's supported endpoint resolution handle it.

### 3.3. Stable Identifier Over the Lifecycle of the Same Resource

As long as it remains the same resource, changes such as renaming or stopping and starting an instance do not create a new OCID for that instance.

When a resource is destroyed and a replacement resource is created, the new object has a new identifier. Reusing the old name, old tags, or the same business role does not make it the old resource.

For resource types that support moving compartments, moving changes the governance location of the same resource and should not be mistaken for recreating it. However, verify move support, conditions, and IAM effects for the exact service.

This matters when managing:

- IaC tool outputs and state.
- Application or automation configs referencing OCIDs.
- Dashboards, alarms, and log filters tied to resources.
- Allowlists or integration configs storing identifiers.
- Resource replacement procedures in a standby region.

### 3.4. An OCID Is Not Authentication Credentials

Knowing an OCID does not mean you are granted permission to use the resource. Requests still require a valid identity and appropriate IAM permissions; the network path to the endpoint must also work.

Even so, an OCID can reveal resource types and infrastructure structure. Sharing logs, screenshots, and configuration data should be governed according to organizational rules.

Distinguish clearly:

| Information | Role |
| --- | --- |
| Resource OCID | Resource identifier |
| User or principal | Identity sending the request |
| API signing key, token, or corresponding credentials | Proves identity under the authentication mechanism |
| IAM policy | Defines permitted actions |
| Endpoint | Address receiving service requests |

Do not include private keys or tokens in examples just to prove an OCID is accessible.

## 4. Service Endpoints: Where Do Requests Go?

### 4.1. An Endpoint Is the Address of a Service Interface

A service endpoint is the network address a client uses to communicate with a service. For HTTPS APIs, an endpoint typically consists of scheme and hostname; specific requests add path, parameters, and headers.

One way to picture it:

~~~text
https://<service-hostname>/<API-path>/<identifier-or-resource>
        __________________/ _________________________________/
           destination          specific operation/object
~~~

In the commercial realm, a common endpoint pattern for core infrastructure APIs is:

~~~text
https://iaas.<region>.oraclecloud.com
~~~

This is an illustrative pattern, not a complete URL while the `<region>` placeholder remains. Do not apply this domain suffix to every realm or every service.

An OCID inside a request parameter does not replace the endpoint. Conversely, the Compute endpoint does not by itself specify which instance the user wants to retrieve.

### 4.2. Region and Realm Are Two Different Layers

A **Region** is an OCI deployment area. Many resources such as VCNs and Compute instances are tied to a specific region.

A **Realm** is a cloud domain comprising a set of regions and corresponding deployment boundaries. Do not assume every realm uses the same DNS suffix or has identical service availability.

To send a request properly, you usually need to know:

1. The identity and tenancy used to authenticate.
2. The region of the resource or the region required by the service operation.
3. The service and API type to call.
4. The endpoint resolution mechanism appropriate for the realm and environment.
5. IAM policies and connectivity to the endpoint.

Some IAM resources or operations have their own region scope and rules, including the role of the home region. Therefore, do not mechanically apply Compute's regional endpoint model to every identity administration operation.

An OCID without a region segment also does not mean you can arbitrarily call any endpoint.

### 4.3. API Endpoints Differ From Application Addresses

One instance can be associated with several different addresses:

| Address or Identifier | What It Is Used For |
| --- | --- |
| Instance OCID | Reference the instance in management APIs |
| Compute API endpoint | Send requests to retrieve info or manage the instance |
| Private IP | Connect to the OS or application over a private network |
| Public IP if configured | Connect according to an appropriate public access architecture |
| Load balancer DNS | Users access the application through the load balancing layer |
| Database management or connection endpoint | Manage or connect to the database service using the right endpoint type |

You do not SSH to an OCID. Nor do you SSH to the Compute API hostname to log into an instance.

Likewise, a database service's API endpoint is not automatically the hostname in a SQL connection string. A database connection string may also require port, service name, certificates, or a wallet depending on the service and configuration.

### 4.4. Control Plane and Data Plane

You can distinguish them by purpose:

- **Control plane** serves management: creating, configuring, retrieving metadata, changing state, or deleting resources.
- **Data plane** serves using the data or capabilities of the resource: reading an object, connecting to a database, or sending requests to an application.

An API to create a bucket and a request to read object content are different operations, even though both live in the Object Storage ecosystem. A request to create a database and a SQL session also have different connection mechanisms.

Exact endpoint boundaries depend on the service; not every service separates control plane and data plane into two completely different hostnames.

When diagnosing errors, know which operation is failing. “The Console sees the database” does not prove the application can establish a SQL connection to that database.

### 4.5. Public Endpoints, Private Endpoints, and Network Paths

A public endpoint can still require strict authentication and IAM. Having a “public” access address does not mean the data is public.

A private endpoint requires connectivity and DNS resolution compatible with the private network. Merely changing a hostname in client config does not create routes, VPNs, FastConnect, or required access permissions.

Layers to verify typically include:

~~~text
DNS -> network path -> TLS -> authentication -> IAM -> valid API request
~~~

Not every error surfaces in this exact order, yet separating layers avoids fixing the wrong cause. If DNS cannot resolve, loosening IAM permissions will not fix DNS. If the request signature is invalid, adding a new route will not fix the signature.

## 5. What Is a Resource Lifecycle?

### 5.1. A Resource Moves Through Multiple States

A resource lifecycle describes the states and transitions from the moment creation is requested until the resource ceases to exist or is no longer usable.

A conceptual model:

~~~text
Creation requested
      |
Provisioning
      |
Ready for use
      |
Updating or executing an operation
      |
Ready again
      |
Deleting
      |
Deleted or terminated
~~~

Those labels are a learning model, not a universal set of lifecycle-state values across all OCI APIs.

Each service has its own set of states. “Available” for a volume may be represented differently from “running” for Compute. Nor does a bucket have a start/stop cycle like an instance.

### 5.2. Compute Instance Example

Some common states when operating a Compute instance:

| State | Basic Operational Meaning |
| --- | --- |
| PROVISIONING | OCI is provisioning the instance |
| RUNNING | The instance is in a running state from the Compute service's perspective |
| STOPPING | Stop operation in progress |
| STOPPED | Instance is stopped |
| STARTING | Start operation in progress |
| TERMINATING | Resource termination in progress |
| TERMINATED | Instance has been terminated |

Specific states and transition paths must be checked against the operation type and current API used. This table focuses on the common flow and does not list every special scenario.

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> RUNNING
    RUNNING --> STOPPING
    STOPPING --> STOPPED
    STOPPED --> STARTING
    STARTING --> RUNNING
    RUNNING --> TERMINATING
    STOPPED --> TERMINATING
    TERMINATING --> TERMINATED
~~~

The diagram simplifies the normal operational flow. It does not fully depict error paths, special operations, or state transition conditions for every instance type.

### 5.3. RUNNING Does Not Mean the Application Is Ready

When an instance transitions to RUNNING, several things may still be pending:

- The operating system is still finishing boot.
- Cloud-init is still installing packages or running scripts.
- The application has not finished starting.
- Secrets have not been fetched yet.
- The database is not accepting connections yet.
- The backend has not passed load balancer health checks yet.
- Routes, DNS, or security rules are incomplete.

At least three check levels should be separated:

| Level | Question |
| --- | --- |
| Infrastructure state | Which state does the OCI service report for the resource? |
| Connectivity | Can clients reach the required port or endpoint? |
| Business readiness | Can the application actually serve real requests? |

For example, a RUNNING instance returning HTTP 503 is not yet eligible to receive user traffic. A database visible in the Console where the application login fails is also not considered ready.

### 5.4. Stop Differs From Terminate

Stopping and terminating are two different operations.

**Stop** transitions the instance to a stopped state via the supported mechanism. The resource keeps its identifier for management and can be restarted when conditions are met.

**Terminate** ends the instance. If you want an instance serving again afterward, you typically must create a new resource or restore according to a prepared plan; do not treat this as a pause button.

Effects on the boot volume, block volumes, IPs, and related resources must be verified from operation options and each resource's rules. Do not assume terminate deletes everything, nor assume everything will be kept.

Costs must also be checked by service, resource type, and pricing model. A stopped instance does not mean attached volumes, backups, public IPs, or related networking components all stop incurring charges.

## 6. A Successful Request Does Not Guarantee Work Is Complete

### 6.1. API Response and Final Outcome

Many cloud operations execute asynchronously. The API accepts the request first, while provisioning or modifying the resource happens afterward.

Typical flow:

~~~text
Client sends create request
        |
API authenticates, authorizes, and accepts
        |
Client receives response with resource or work info
        |
OCI continues processing
        |
Client checks until succeeded, failed, or timed out
~~~

HTTP 202 typically indicates the request was accepted for processing. HTTP 201 may return a newly created resource that is not yet in a usable state. Do not rely on a success HTTP status code alone to conclude the application is working.

Read the API contract: does the response include the resource, what is the initial state, is there a work request, and where must the final outcome be checked?

### 6.2. Work Requests

Some OCI services or operations return a **work request**, representing asynchronous work.

When supported by the API, the response may provide the work identifier via the **opc-work-request-id** header. Clients use that identifier with the appropriate work request API to view progress, results, logs, or errors provided by the service.

Not every asynchronous operation has a work request, and there is no single work request endpoint applying to all services.

A job may pass through these conceptual stages:

~~~text
Accepted -> In Progress -> Succeeded
                        -> Failed
                        -> Canceled, if the operation supports it
~~~

Actual state names depend on the API. When writing automation, use the exact state set of the service being called.

A work request ID differs from a resource OCID. One resource can be associated with many work requests over its lifecycle.

### 6.3. Request IDs for Investigation

A response may include **opc-request-id**, used to correlate a specific request when investigating errors.

Three identifier types must be stored for their proper purposes:

| Type | Question Answered |
| --- | --- |
| Resource OCID | Which resource? |
| Work request ID | Which asynchronous job? |
| Request ID | Which API call? |

Do not use a request ID in place of an instance ID when calling an API to fetch instance details. Nor should having a request ID be taken as proof that the job succeeded.

If an operation fails, useful details usually include timestamp, service, region, operation, related resource OCID, request ID, and the error with sensitive data masked.

### 6.4. Re-Reading Resources and Consistency

After creating or modifying a resource, reads across different interfaces may not reflect the new state simultaneously.

For example:

- A create response already includes the OCID, yet the Console list has not updated immediately.
- One read observes an intermediate state.
- The IAM system or a dependent component needs extra time before a change takes full effect.

Do not treat a first read that does not yet show the result as definitive proof that creation failed.

Nor should “need to wait” be used as an excuse to overlook the wrong region, wrong principal, or missing permissions. Verify the request context first, then wait or retry within defined limits.

## 7. Writing State-Aware Automation

### 7.1. Conditional and Bounded Waiting

An error-prone approach is:

~~~text
Send create command
Sleep fixed 30 seconds
Continue configuring application
~~~

Thirty seconds may be too long for one run yet too short for another.

A better workflow:

~~~text
1. Submit the operation and save the OCID/work ID if provided in the response.
2. Pick the target state defined by the API.
3. Poll the resource or work request using the method supported by the service.
4. Stop when:
   - the target state is reached;
   - a terminal failure state is encountered;
   - or the timeout is exceeded.
5. Only afterward check application connectivity and readiness.
~~~

The SDK/CLI may provide waiters for specific operations. Check options of the exact command or method, rather than assuming all commands share the same wait mechanism.

If implementing polling yourself, use sensible wait intervals, back off gradually when appropriate, and add small jitter to avoid many clients calling simultaneously. Respect service limits and API retry guidance.

### 7.2. Client Timeout Does Not Mean the Cloud Stopped

Suppose the client waits 10 minutes and times out. The job on OCI may still be processing and finish afterward.

Automation must distinguish:

| Scenario | Interpretation |
| --- | --- |
| Work request reports failed | The service reported the job did not succeed |
| Client timed out | The client did not observe the outcome within the time limit |
| Network dropped while sending request | It may be unknown whether OCI received the request |
| Resource reached target state | The awaited infrastructure condition has been satisfied |

Before sending a new create request, check the existing job or resource using the details already received. Recreating immediately can provision two resources and incur unintended costs.

### 7.3. Retries and Safe Idempotency

Not every call can be repeated without causing additional side effects.

Some operations support **opc-retry-token** to help handle repeated requests within the scope and timeframe specified by the API. When using this mechanism:

- Use the same token when resending the same logical operation.
- Keep the request payload consistent with the API contract.
- Do not generate a new token on every retry of the same operation if the goal is to avoid duplicate creation.
- Do not reuse a token to represent a different business operation.
- Do not treat the token as an infinitely persistent deduplication mechanism.

Only use a retry token header or parameter when supported by the API. Do not add it to every endpoint and assume it takes effect.

For transient errors, retry according to service guidance. For invalid parameters or missing permissions, resending the exact same request multiple times usually will not resolve the root cause.

### 7.4. Avoiding Overwrites With ETags When Supported

Some APIs return an ETag and support the **If-Match** condition on updates or deletes.

Conceptual example:

~~~text
Client A reads resource -> receives ETag version 1
Client B updates        -> resource now has ETag version 2
Client A updates with If-Match version 1
                        -> precondition is no longer true
~~~

This mechanism helps detect that data changed since the client read it. It does not replace IAM and is not a lock across an entire multi-step workflow.

When encountering a precondition error, re-read, review the changes, and decide how to proceed. Dropping the condition to retry immediately can overwrite someone else's valid change.

## 8. Practice Reading Information With the OCI CLI

This section illustrates a **read-only** operation on a Compute instance. Commands are learning content and are not executed automatically in this lesson.

### 8.1. Prerequisites

You need:

- OCI CLI installed and authenticated via an appropriate mechanism.
- A principal with permission to read the instance being inspected.
- The exact region of the instance.
- The full OCID of the instance.
- Network path to the corresponding API endpoint.

The example below uses PowerShell and two environment variables prepared by the learner:

~~~powershell
$env:OCI_REGION = "<instance-region>"
$env:OCI_INSTANCE_OCID = "<full-instance-ocid>"
~~~

Strings inside angle brackets are placeholders. Do not use a masked OCID in a real call.

### 8.2. Reading the Instance

~~~powershell
if ([string]::IsNullOrWhiteSpace($env:OCI_REGION)) {
    throw "Missing OCI_REGION."
}

if ([string]::IsNullOrWhiteSpace($env:OCI_INSTANCE_OCID)) {
    throw "Missing OCI_INSTANCE_OCID."
}

$instanceJson = oci compute instance get --instance-id $env:OCI_INSTANCE_OCID --region $env:OCI_REGION --output json
$ociExitCode = $LASTEXITCODE

if ($ociExitCode -ne 0) {
    throw "Failed to read instance. Check CLI error, region, and IAM permissions."
}

$instanceResponse = ($instanceJson -join [Environment]::NewLine) | ConvertFrom-Json
$instanceData = $instanceResponse.data

[pscustomobject]@{
    Id            = $instanceData.id
    DisplayName   = $instanceData.'display-name'
    CompartmentId = $instanceData.'compartment-id'
    Lifecycle     = $instanceData.'lifecycle-state'
}
~~~

The get command uses the instance OCID to specify the object and the region to choose the service call context. CLI authentication configuration provides the identity; the OCID does not play that role.

Do not embed private keys or tokens in the script. If you need to choose a different authentication configuration, use the profile/configuration mechanism supported by the CLI.

### 8.3. Interpreting Results Properly

Once you have output, answer:

1. Does **Id** match the resource you intended to check?
2. Does **DisplayName** match expectations, and could it collide in name with another resource?
3. Is **CompartmentId** the expected governance scope?
4. Is **Lifecycle** the desired terminal state or an intermediate state?
5. After infrastructure state, which application conditions still need verification?

Do not use a RUNNING result to automatically conclude that a website, SSH, or database is reachable.

If you can read the resource yet cannot connect to the application, move on to checking network paths, service ports, the OS, certificates, and application configuration.

### 8.4. Cross-Checking in the Console

In the OCI Console, you can open the resource details page to cross-check the corresponding details:

- OCID and display name.
- Compartment.
- Active region.
- Current state.
- Related resources, such as VNIC, subnet, or volumes if applicable.

Section names and display layouts may vary by service. The purpose of this step is to verify the exact same resource, not merely find a matching name.

## 9. Diagnosing Common Scenarios

### 9.1. Have the OCID Yet the API Reports Not Found or Not Authorized

Some OCI responses may not let callers directly distinguish a non-existent resource from a resource they lack permission to access.

Useful check order:

1. Is the OCID complete, the right resource type, and free of extra whitespace?
2. Is the command using the right principal, profile, and tenancy?
3. Are the region and endpoint matching the resource's context?
4. Does the resource still exist, or was it replaced by a new resource?
5. Does the principal have appropriate permissions in the current compartment?
6. Are there recent IAM changes whose propagation/effect needs verification?

Do not work around this by granting tenancy-wide admin rights just to test. First identify the exact target and required permissions.

### 9.2. DNS, TLS, or Timeout Errors

If you cannot connect to an endpoint, check:

- Whether the hostname matches the service, region, and realm.
- Whether DNS from the client runtime environment resolves properly.
- Whether proxies, VPNs, firewalls, and routes permit the path.
- For private endpoints, whether private network connectivity and corresponding DNS are configured properly.
- Whether TLS verification succeeds and the trust chain is valid.
- Whether system time and request signing align once connected.

Do not disable TLS verification as a long-term fix. That hides symptoms and undermines endpoint authenticity.

### 9.3. Prolonged Intermediate State

If a resource stays in provisioning or updating for a long time:

1. Determine whether this is the state of the resource or of a work request.
2. Read the job's logs and errors if provided by the service.
3. Check quotas, limits, provisioning capacity, network dependencies, and applicable config conditions.
4. Cross-check the request ID and timestamp.
5. Continue waiting within defined limits or escalate to incident handling procedures.

Do not send multiple concurrent start, stop, update, or delete requests to “nudge” the resource. Operations may conflict with the current state and complicate investigation.

### 9.4. Unable to Delete a Resource

Causes may include another operation in progress on the resource, remaining dependencies, unmet deletion prerequisites, or missing principal permissions.

Read the actual error and check dependency relationships. For example, deleting a network component may require handling attached components first according to service rules.

A successful delete work request must also be checked against cleanup goals: were child resources, volumes, backups, or other endpoints intentionally kept?

Do not treat a temporarily empty Console list as the sole proof that all related resources and costs have been reclaimed.

## 10. Lifecycle Tied to Cost, IAM, and Availability

### 10.1. Controlling Cost Across a Resource Set

An application system usually comprises multiple resources with separate lifecycles:

~~~text
Application
  + Compute instance
  + Boot/block volumes
  + Load balancer
  + Configured public IP
  + Object Storage/backups
  + Database
  + Networking and monitoring components
~~~

Stopping or deleting one instance does not mean this entire set stops or is deleted with it. Cleanup policies must identify each component, data to retain, and their cost-accrual conditions.

Track tags, owners, expiration periods, and OCID references to locate orphaned resources after experiments or system replacements.

### 10.2. Changing Compartments Can Change Effective Permissions

For resources that support moving compartments, the OCID of the same resource may remain unchanged while effective access permissions change according to policies applied at the new location.

This can affect:

- Automation reading or managing the resource.
- Operators responsible for the application.
- Systems collecting monitoring data.
- Integrations with related IAM conditions.

Therefore, a stable identifier does not mean stable access permissions. Verify permissions and service-specific constraints before and after the move.

### 10.3. Resource Replacement and DR

When redeploying in another region, expect:

- New OCIDs for newly created resources.
- Target-region API endpoints.
- Application or database endpoints that may change.
- IAM, networking, and secrets that must fit the new architecture.
- Monitoring filters or automation referencing old OCIDs that need updating.

A stable DNS name can help applications reduce dependence on deployment addresses, yet it does not automatically move state, data, or IAM permissions.

For databases, a dedicated data protection and recovery plan is needed. Recreating infrastructure resources does not mean data and transactions have been recovered.

## 11. Synthesis Scenario

### Context

A pipeline creates a Compute instance for a learning application. The create call returns an OCID, yet the pipeline loses connectivity before observing the final state.

The operator sees the Console does not yet display the instance in the list they just opened and considers rerunning the entire creation step.

### Analysis

Three things have not been distinguished:

1. Was the request accepted by the service?
2. Which state has the resource reached?
3. Is the application ready yet?

Not seeing the result in the list yet does not answer all three questions. Rerunning immediately could create an extra instance if the first attempt succeeded.

### How to Handle It

- Confirm the pipeline's region, principal, and compartment.
- Use the received OCID to read the resource directly through the appropriate endpoint.
- Check the work request if the operation provided that information.
- If PROVISIONING, keep monitoring with a bounded timeout instead of recreating.
- If RUNNING is reached, verify OS initialization and application health checks.
- If failed, collect the error, request ID, and state of related resources before deciding to retry.
- If the create operation must be retried, apply a safe retry mechanism supported by the API and check against existing resources.
- Once complete, record the OCID and required endpoints in appropriate deployment outputs.

### Information That Should Be Stored

| Category | Data |
| --- | --- |
| Context | Environment, region, compartment, and execution identity at the needed level |
| Resource | OCID, display name, resource type, and owner |
| Operation | Request type, timestamp, request ID, work request ID if any |
| Outcome | Final infrastructure state and health check result |
| Access | API endpoint or application endpoint to use, avoiding mixing roles |
| Operations | Retention period, data retention rules, and teardown procedure |

Do not store secret keys or full authentication headers just to have extra investigation details.

## 12. Self-Check

### Question 1: Do two instances with the same name share the same OCID?

No. Display names are not guaranteed unique. Each instance is a separate resource and has its own OCID.

### Question 2: Does renaming an instance change its OCID?

No, as long as it remains the same instance and renaming is supported. Creating a new instance with the old name is a different case and creates a new identifier.

### Question 3: Can an OCID be used to SSH?

No. SSH requires a reachable address or hostname, network path, port, credentials, and matching OS configuration. OCIDs are used to reference resources in corresponding APIs.

### Question 4: Does an API returning HTTP success mean the application is ready?

No. The API may only have accepted the request or created the resource in an intermediate state. You must monitor infrastructure state, then verify connectivity and application readiness.

### Question 5: Should a client timeout trigger immediate re-creation?

No. First verify whether the resource or job was accepted. A client timeout does not prove the cloud operation failed or was canceled.

### Question 6: Are the right endpoint and the right OCID enough to read a resource?

Not yet. Proper identity authentication, appropriate IAM permissions, and working network connectivity are also needed. Some operations also have service-specific conditions.

### Question 7: Does Stop guarantee zero remaining costs?

No. Check the pricing model and state of all related resources, including storage, backups, addresses, and remaining service components.

## 13. Checklist When Working With OCI Resources

- [ ] Identified the exact resource type and identifier required by the API.
- [ ] Obtained the full OCID from a trusted source, without using masked strings.
- [ ] Distinguished display name, resource OCID, and compartment OCID.
- [ ] Selected the right principal, tenancy, region, and endpoint.
- [ ] Verified authentication, IAM, and network path prerequisites.
- [ ] Read the state actually returned by the API, without applying generic labels across all services.
- [ ] Distinguished request acceptance from job completion.
- [ ] Captured request ID and work request ID when provided by the service.
- [ ] Implemented bounded waiting, error handling, and duplicate-creation prevention on retries.
- [ ] Verified application readiness after infrastructure readiness.
- [ ] For stop, delete, or terminate, understood retained data and resources that continue to exist.
- [ ] After replacement or DR, updated OCID references, endpoints, and monitoring.

When reading an OCI response, combine three pieces of information: **resource identifier**, **service call context**, and **observed state**. With all three in place, deployment, automation, and incident investigation rest on clearer evidence.