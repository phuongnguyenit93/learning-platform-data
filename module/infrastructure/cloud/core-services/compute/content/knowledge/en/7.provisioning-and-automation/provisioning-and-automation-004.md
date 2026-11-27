# Idempotency and State Management in Resource Provisioning

Cloud resource provisioning typically spans multiple steps: creating networks, subnets, virtual machines, disks, IP addresses, access permissions, and dependent services. A command may be resent due to a timeout, a pipeline rerun, or an operator retrying after receiving no response. If every run creates new resources, the system can end up with duplicate VMs, orphaned IP addresses, rising costs, and hard-to-control configurations.

**Idempotency** ensures that an operation can be executed repeatedly while still bringing the system to the same desired state. **State management** enables provisioning tools to know which logical resource in the configuration corresponds to which real-world resource, which operations have completed, and what changes need to happen next.

This lesson belongs to the **Provisioning and Automation** chapter of the **CLOUD_CORE_SERVICES_COMPUTE** module. The module helps learners explore cloud compute models from virtual machines and containers to serverless; how to choose CPU, memory, networking, and security settings; and how to deploy applications, scale workloads, ensure availability, and optimize operating costs. In this context, idempotency and state management form the foundation for safely automating the creation, updating, and destruction of resources.

## 1. What Is Idempotency?

An operation is called **idempotent** when executing it once or repeating it multiple times produces the same final state outcome.

For example, a request to ensure a virtual machine is in the **running** state can be executed multiple times. If the machine is already running, subsequent calls should not create another VM; the system simply confirms the current state satisfies the requirement.

Conversely, an operation to "create one more virtual machine" each time it is called is non-idempotent if every invocation spawns a new machine.

### 1.1. Idempotency vs. Running Exactly Once

In distributed systems, a client may send a request and lose connectivity before receiving a response. The client does not know whether the server processed the request. If it retries, the operation may be executed a second time.

Idempotency solves this scenario by ensuring repetitions cause no unintended side effects. It does not mean the request is only processed once. A request may be received multiple times, but all executions must converge on the same outcome according to the operation's contract.

Distinguish between:

- **At-most-once:** the system attempts never to execute the operation more than once, but it may fail to execute if the request is lost.
- **At-least-once:** the system may retry until a response is received, so the same request can be processed multiple times.
- **Effectively-once:** combines retries, operation identifiers, and idempotent handling to achieve the business effect of executing once within a defined scope.

For cloud provisioning, retries are often necessary because networks and services experience transient errors. Therefore, idempotent design is more practical than assuming "each command runs exactly once."

### 1.2. Examples of Idempotent Operations

| Request | First Execution | Repeated Execution | Desired Outcome |
|---|---|---|---|
| Ensure a VM named api-01 exists | Create VM if absent | Find existing VM and confirm configuration | Only one VM with that identity exists |
| Ensure firewall has an HTTPS rule | Add rule if missing | Do not add a duplicate rule | Rule exists exactly once |
| Set machine group replica count to 3 | Set desired capacity to 3 | Set to 3 again | Desired replica count remains 3 |
| Delete an identified resource | Delete resource | Confirm resource is absent | Resource does not exist |
| Increase replica count by 1 | Increase from 3 to 4 | Increase again from 4 to 5 | Non-idempotent if the same request is resent |

The key point is how the request is phrased. "Set replica count to 4" describes a target state. "Increase replica count by 1" describes a relative action. Relative actions easily produce repeated side effects upon retry.

## 2. Designing Idempotent Provisioning Operations

### 2.1. Declaring Target State Instead of Repeating Actions

The declarative approach describes the desired state of resources. The provisioning tool compares the configuration against the current state and decides what to create, update, or delete.

For example, requesting a virtual machine group with three instances:

~~~hcl
resource "example_compute_group" "api" {
  name           = "api-group"
  desired_size   = 3
  machine_type   = "general-purpose"
  image_id       = "image-stable"
  subnet_id      = "subnet-private"
}
~~~

The resource name and attributes in this example illustrate HCL syntax; real providers have their own schemas. Once desired_size is already 3, re-running the same configuration should not create three additional machines. The tool reconciles state and provider APIs to determine whether the system has already reached that state.

The imperative approach describes individual actions—such as calling APIs to "create machine," "attach disk," or "add rule." It can still be idempotent if each step checks existing resources, uses stable identifiers, and handles already-completed cases.

### 2.2. Using Stable Identifiers

A repeated operation needs to know it is referring to the same object. A stable identifier can be:

- A resource ID issued by the cloud provider.
- A logical name unique within a scope such as a project or account.
- Management tags or labels such as environment=production and service=api.
- A client-generated idempotency key for a business request.
- A natural key with a uniqueness constraint, if supported by the service.

Do not rely solely on a display name if that name can collide across projects, regions, or accounts. Define the full scope and store the resource ID after creation succeeds.

### 2.3. Idempotency Keys for APIs

Some APIs support an **idempotency key** field or header. The client generates a unique key for a resource creation intent and resends the same key on retries. The server uses that key to recognize requests belonging to the same operation and returns the recorded result instead of creating a new resource.

Illustrative example:

~~~http
POST /v1/instances
Idempotency-Key: create-api-01-2026-11-22-001
Content-Type: application/json

{
  "name": "api-01",
  "machine_type": "general-purpose",
  "image": "image-stable"
}
~~~

If the client times out and resends the same request with the same key, the API can return the result of the prior operation. If the same key is sent with a different payload, the API typically rejects it or reports a conflict per the service contract.

When using idempotency keys, check the API documentation for:

- How long the server retains keys and results.
- Uniqueness scope of the key: per account, endpoint, region, or tenant.
- How concurrent requests with the same key are handled.
- Behavior when the payload changes.
- Response returned while the initial operation is still in progress.
- How to query status if the client misses the response.

Never assume every POST API supports idempotency keys. If the service does not support them, the application must design its own checking and reconciliation mechanism.

### 2.4. HTTP Methods Do Not Automatically Guarantee Full Business Idempotency

Under HTTP semantics, PUT and DELETE are defined as idempotent; GET is safe and idempotent. POST is generally non-idempotent by default. However, actual effects depend on the API contract.

For example:

- **PUT /instances/api-01** can set the resource configuration to the submitted representation. Resending the same payload targets the same state.
- **DELETE /instances/api-01** can leave the resource in a non-existent state. Subsequent calls still target that state, even though the response might be 404.
- **POST /instances** typically creates a new resource each time; safe retries require an idempotency key or another deduplication rule.

An API may return a new timestamp, request ID, or audit record on every call, even when the final resource state does not change. Therefore, when evaluating idempotency, clarify whether you mean resource state, HTTP response, or all secondary side effects.

## 3. State in Infrastructure as Code Tools

### 3.1. Three States to Distinguish

When using Infrastructure as Code (IaC) tools, there are three key concepts:

1. **Desired state:** the target state described in configuration files.
2. **Actual state:** the state of resources currently existing on the cloud provider.
3. **Recorded state:** the state recorded by the tool, including mappings between resource addresses in configuration and real resource IDs along with necessary attributes.

~~~mermaid
flowchart LR
    D["Desired state<br/>IaC file"]
    S["Recorded state<br/>State backend"]
    A["Actual state<br/>Cloud API"]
    D --> P["Plan / Reconcile"]
    S --> P
    A --> P
    P --> C["Create / Update / Delete"]
    C --> A
    A --> R["Refresh / Read"]
    R --> S
~~~

The tool needs all three views to plan changes. The configuration file states what the operator wants; state records which objects the tool manages; the cloud API reports what the live resources actually look like.

State is not a complete, always-fresh mirror of the cloud. It is management metadata the tool uses to track resources. If someone modifies a resource directly in the console, recorded state may not immediately reflect that change. If state is lost, cloud resources may still exist, but the tool loses its linkage to them.

### 3.2. Resource Address and Resource ID

In Terraform, each resource has a logical address, for example:

~~~hcl
resource "example_instance" "api" {
  name = "api-01"
}
~~~

The address in configuration is **example_instance.api**. The cloud provider may assign a different ID such as **inst-7f31a2**. State stores the link between the logical address and the real ID, along with attributes read or managed by the provider.

If you rename the resource block from **example_instance.api** to **example_instance.backend** without declaring an address move, Terraform may interpret the change as destroying the old object and creating a new one. For critical resources, use a moved block or appropriate state move command to preserve the linkage.

Example:

~~~hcl
moved {
  from = example_instance.api
  to   = example_instance.backend
}
~~~

This syntax informs the tool that the logical address was renamed while still representing the same underlying resource. Verify the Terraform version and module scope before applying the change.

### 3.3. State Can Contain Sensitive Data

State can contain IP addresses, hostnames, metadata, connection attributes, passwords, or sensitive values depending on the provider and configuration. Marking a variable as sensitive mainly controls how Terraform displays values in certain outputs; it does not mean the data is excluded from state.

Therefore:

- Restrict read and write permissions on state under least privilege.
- Use a remote backend with encryption at rest and in transit.
- Protect backend access credentials using a secret manager or appropriate identity mechanism.
- Never commit state or backups containing state into public repositories.
- Never dump state contents into logs, tickets, or unprotected artifacts.
- Establish backup storage and appropriate retention policies.
- Audit backend access permissions and audit logs.

## 4. Local vs. Remote State Storage

### 4.1. Local State

When starting with Terraform, state is often stored in a local file such as **terraform.tfstate**.

The advantage is ease of setup, making it suitable for individual experimentation. However, local state carries risks:

- Exists only on one person's machine.
- Hard to share accurately across multiple team members or pipelines.
- Easily overwritten when multiple people operate concurrently.
- Can be lost if the machine or workspace is deleted.
- Easily committed accidentally to Git if not carefully managed.

Local state is suited for labs or small test environments where multiple people do not jointly manage a set of resources.

### 4.2. Remote State

In team environments, state is typically stored in a remote backend such as object storage or a state management service. The backend should support appropriate capabilities:

- Durable storage with recovery capabilities.
- Encryption in transit and at rest.
- Access control per user or pipeline.
- Versioning or backups for state recovery.
- Locking to prevent concurrent state writes, if supported by the backend.
- Audit logs and retention policies.

Illustrative backend configuration example:

~~~hcl
terraform {
  backend "s3" {
    bucket       = "company-terraform-state"
    key          = "compute/production/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
  }
}
~~~

This is an S3 backend example; bucket name and region are illustrative values only. The backend must be created and granted permissions before running terraform init. Configure locking using the mechanism supported by your Terraform version and backend. Do not assume that enabling encryption alone provides locking or backups.

### 4.3. State Locking

**State locking** prevents multiple processes from modifying the same state at the same time. If two pipelines run apply concurrently, both could read an older version of state and write inconsistent changes.

The locking flow typically works as follows:

1. Terraform requests a lock from the backend.
2. If locking succeeds, Terraform reads state and performs plan/apply.
3. Upon completion or supported interruption, Terraform releases the lock.
4. If the process fails abnormally, the lock may need to be handled according to the backend and tool documentation.

Do not manually delete a lock simply because a pipeline appears to be running long. First verify that the process holding the lock has terminated and state is no longer being updated. The force-unlock command can corrupt state if misused. Only personnel responsible for state management should perform it after verification.

### 4.4. Splitting State by Management Scope

It is not necessary to store every resource of the entire organization in a single state. You can split state by environment, application, service group, or administrative domain.

Examples:

- **network/shared/terraform.tfstate:** shared networking.
- **compute/dev/api/terraform.tfstate:** compute for the API in dev.
- **compute/prod/api/terraform.tfstate:** compute for the production API.
- **compute/prod/worker/terraform.tfstate:** compute for production workers.

Splitting state limits blast radius, reduces contention, and clarifies permissions. However, multiple states introduce dependencies between groups. Clearly define output interfaces, access permissions, and deployment ordering across them.

## 5. Reconciliation Workflows and Safe Repeated Operations

### 5.1. Plan Before Apply

A common IaC workflow includes:

~~~bash
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
~~~

- **init** initializes providers and the backend.
- **validate** checks configuration structure.
- **plan** compares configuration, state, and provider data to compute expected changes.
- **apply** executes the planned changes.

Re-running the same configuration after the system has reached the desired state typically produces an empty plan. This is an indicator that configuration and state have converged at the time of inspection. However, an empty plan does not guarantee resources will not change afterward or that no external side effects exist.

Do not auto-apply every change in production without proper review, approval workflows, and permission boundaries.

### 5.2. Safe Retries on API Timeouts

Suppose a client sends a VM creation request. The server might create the VM successfully, yet the response is lost. If the client calls the creation endpoint again without an idempotency key or duplicate check, it could create two VMs.

A safer workflow:

1. Generate an operation ID or idempotency key for the provisioning intent.
2. Send requests with the same identifier on retries.
3. If the API returns an operation ID, save it and poll operation status.
4. If the request times out and the API does not support idempotency keys, search for the resource by stable identifier or pre-assigned tag.
5. Only send a new creation request after confirming the resource was not created.
6. Record the resource ID and outcome in state or a management data store.

Pseudocode logic example:

~~~python
def ensure_instance(spec, operation_key):
    result = cloud.find_by_operation_key(operation_key)

    if result is not None:
        return cloud.wait_until_ready(result.id)

    try:
        result = cloud.create_instance(
            spec=spec,
            idempotency_key=operation_key
        )
    except TimeoutError:
        result = cloud.find_by_operation_key(operation_key)
        if result is None:
            raise

    return cloud.wait_until_ready(result.id)
~~~

This is pseudocode. Real APIs may use different field names, operation mechanisms, and idempotency key retention windows. If an API does not support keys, find_by_operation_key is only safe when the service allows storing and querying a reliable unique identifier. Two concurrent clients could still both find "not yet existing" and both create; additional race-prevention mechanisms such as unique constraints, locks, or create-if-absent APIs are required.

### 5.3. Handling Asynchronous Operations

Many provisioning APIs return an operation ID instead of waiting for a VM or database to become ready. In such cases, resource creation and the resource reaching the ready state are two separate phases.

Clients should:

- Store the operation ID and resource ID once available.
- Poll status at intervals with backoff.
- Distinguish pending, running, succeeded, and failed states according to the API.
- Enforce an overall timeout and retry cap.
- On lost responses, query the operation before sending a new creation request.
- Handle eventual consistency: a newly created resource may not immediately appear in every read or list API.

Do not treat "request accepted" as synonymous with "resource ready." Pipelines need to wait for health conditions or target state before running dependent steps.

## 6. Drift, Refresh, and State Reconciliation

### 6.1. State Can Differ from Reality

State is a tool's record at a point in time. Actual state can change because:

- An operator makes direct edits in the console.
- Another pipeline or tool modifies the resource.
- The cloud provider updates metadata or system status automatically.
- A resource is deleted outside Terraform.
- A previous operation completed partially and then failed.

Discrepancies among desired state, recorded state, and actual state must be detected before continuing provisioning.

### 6.2. Refresh and Plan

Terraform can read live state from providers to update observed information in state during plan or refresh. Exact commands and behaviors vary by Terraform version; use current workflows rather than relying on legacy refresh commands.

Reconciliation steps:

1. Check the active workspace and backend.
2. Run plan to see what changes Terraform detects.
3. Identify whether differences stem from configuration, state, or out-of-band actions.
4. Decide whether to update configuration, import resources into state, or restore the desired state.
5. Re-review the plan after adjustments before applying.

Do not run apply just to "clear the diff" without understanding why the resource changed. A plan might propose replacing a VM, disk, or IP address and cause disruption if applied at the wrong time.

### 6.3. Importing Existing Resources

If a resource was created manually or by another tool and needs to be brought under Terraform management, you can import it into state. Importing binds a real resource ID to a logical address in configuration.

Example using an import block:

~~~hcl
import {
  to = example_instance.api
  id = "inst-7f31a2"
}
~~~

After declaring the corresponding resource and import block, run plan to preview the result. Add configuration matching the existing resource before applying; if declared configuration differs from reality, the plan may propose modifying or replacing the resource.

Importing does not automatically author your full desired configuration, nor does it make out-of-band changes acceptable. After importing, verify critical attributes, dependencies, lifecycle rules, and management permissions.

## 7. State Protection and Recovery

### 7.1. Backups and Versioning

State is critical data. If state is deleted or overwritten erroneously, the tool can lose track of resources even though those resources still exist.

Recommendations:

- Enable versioning or snapshots on the backend when supported by the service.
- Save a backup before sensitive state operations.
- Test restoration procedures periodically.
- Log who made changes and when.
- Require approval workflows for state replacement, import, or migration operations.
- Limit who has direct write access to the backend.

State backups do not replace application data backups. State only assists the infrastructure management tool; it does not contain disk contents, databases, or object storage needed to restore business data.

### 7.2. Losing State Does Not Mean Losing Resources

If the state file is lost, do not immediately run apply assuming all resources do not exist. Terraform may attempt to recreate resources that still exist on the cloud, causing duplicates or name-already-in-use errors.

The recovery workflow should be:

1. Pause pipelines that could write to the same state.
2. Locate the latest valid state backup or version.
3. Determine the scope of managed resources and cross-check against cloud APIs.
4. Restore state or import existing resources under their resource addresses.
5. Run plan and carefully inspect every create, delete, or replace action.
6. Resume applying only after state and configuration are verified.

If state corruption is suspected, avoid manually editing JSON. Use official tool commands and guides, preserve a copy of the original state, and document every recovery action.

### 7.3. Migrating Backends

When moving from local state to a remote backend or from one backend to another, use tool-supported migration procedures. In Terraform, **terraform init -migrate-state** can help transfer state when backend configuration changes.

Before migrating:

- Back up the current state.
- Confirm access permissions on the new backend.
- Verify encryption, versioning, and locking.
- Pause concurrent pipelines or operations.
- Run migration per the guide for your active version.
- Verify the new state and run plan to confirm there are no unexpected changes.

Never copy state using plain file operations while an apply is running.

## 8. Dependencies, Ordering, and Consistency

Provisioning often involves dependencies. For example, a VM needs a subnet and security group; a volume needs a compatible zone; a load balancer needs healthy backends.

IaC tools can infer dependencies from resource references or use explicit dependency declarations. However, dependencies in the graph only solve operation ordering—they do not automatically guarantee the underlying service is ready at the application layer.

Example:

~~~hcl
resource "example_instance" "api" {
  name      = "api-01"
  subnet_id = example_subnet.private.id

  depends_on = [
    example_security_group.api
  ]
}
~~~

In the example, the VM references the subnet, so the tool can infer the dependency on the subnet. depends_on adds an explicit dependency on the security group if the provider or configuration cannot express the relationship through a referenced attribute. Actual schemas depend on the provider.

A provisioning operation can return success before the underlying service is genuinely ready. Add appropriate health checks, wait conditions, or connectivity checks. Avoid relying on fixed sleeps as the sole readiness check, since initialization times vary with load and platform state.

## 9. Practicing Idempotent Workflows with Terraform

### 9.1. Declaring Stable Resources

Example of a VM group with a fixed desired count:

~~~hcl
variable "environment" {
  type = string
}

variable "instance_count" {
  type    = number
  default = 2
}

resource "example_instance" "worker" {
  count         = var.instance_count
  name          = format("worker-%s-%d", var.environment, count.index + 1)
  machine_type  = "general-purpose"
  image_id      = "image-stable"
  subnet_id     = "subnet-private"
}
~~~

The configuration describes two workers with stable names based on environment and index. When re-run with the same variables and state, Terraform recognizes the already managed instances and creates no duplicates.

If instance_count changes from 2 to 3, Terraform adds one instance. If reduced from 3 to 2, Terraform proposes deleting the corresponding instance. Before applying, check lifecycle policies and the impact on data or connections of the deleted resource.

### 9.2. Re-running and Inspecting Plans

Practice workflow:

~~~bash
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
terraform plan
~~~

The final plan typically shows no changes if configuration, state, and actual state are aligned. If changes still appear, investigate the cause: provider-returned defaults, out-of-band attribute mutations, unstable data, or configuration not accurately representing live state.

### 9.3. Controlled Parallel Execution

In teams, multiple pipelines may want to provision resources simultaneously. You need to:

- Use a shared state backend for a single management scope.
- Enable locking if supported by the backend.
- Avoid having two independent pipelines manage the same resource address.
- Use concurrency groups or deployment queues in CI/CD.
- Separate state when two teams have independent ownership scopes.
- Clearly define ownership of shared resources.

State locking only protects concurrent writes to the same state via the backend mechanism. It does not stop a console user or another tool from modifying resources outside state. Combine it with IAM permissions, change processes, and drift detection.

### 9.4. Idempotency in Configuration Management with Ansible

Ansible generally operates under a state-declaration model. Specialized modules take a desired state and check before making changes—for instance, ensuring a package is installed or a service is running:

~~~yaml
- name: Configure web service
  hosts: web
  become: true
  tasks:
    - name: Ensure Nginx is installed
      ansible.builtin.package:
        name: nginx
        state: present

    - name: Ensure Nginx is enabled and running
      ansible.builtin.service:
        name: nginx
        enabled: true
        state: started
~~~

Running the playbook multiple times with the same variables and target hosts will not reinstall the package or restart the service if the state is already correct. Modules report changed only when an action is needed.

Command or shell modules generally have no awareness of the command's business state. For example, a command creating a directory or downloading a file may re-run and cause side effects. When no specialized module exists, add guard conditions like creates or removes where appropriate:

~~~yaml
- name: Generate a one-time initialization marker
  ansible.builtin.command:
    cmd: /usr/local/bin/initialize-app
    creates: /var/lib/my-app/initialized
~~~

The creates condition skips the command when the marker file already exists. This approach is only safe if the marker is created strictly upon task completion and continues to reflect the required state. Avoid simple markers for operations that can partially complete or require checking multiple attributes; in those cases, write a module capable of inspecting actual state.

The changed_when attribute only adjusts whether a task reports as changed; by itself it does not prevent the command from running again. To achieve idempotency, verify conditions before execution or use modules with state semantics.

## 10. Common Mistakes

**Confusing retries with idempotency.** Resending a resource creation command can spawn new objects if the API lacks deduplication support. Stable identifiers and retry rules are essential.

**Using random names on every run.** If a new name is generated each time, the system cannot recognize it as the same provisioning intent. Use business-stable IDs or keys.

**Assuming state is the infrastructure itself.** State is a management record; cloud resources exist independently. Losing state does not delete resources, nor does it mean you should recreate everything.

**Assuming sensitive encrypts state.** The sensitive attribute controls visibility in certain outputs; it does not replace backend encryption and access controls.

**Multiple pipelines applying the same state without locking.** Can lead to overwrites or corrupted state. Use a remote backend with locking and pipeline orchestration.

**Manually editing state JSON.** A single erroneous edit can break resource linkages or cause the tool to propose accidental deletions. Use official state/import/moved commands and back up first.

**Importing resources without matching configuration.** Importing only records the ID in state. Mismatched configuration can produce plans that unexpectedly replace or modify resources.

**Treating request acceptance as resource readiness.** An API may return an operation ID while the VM is still initializing. Poll status and run health checks.

**Deleting a lock that is actively in use.** Force-unlocking at the wrong moment can let two processes write state concurrently. Verify running processes and backend status first.

**Treating an empty plan as a permanent guarantee.** A plan only reflects observed data at execution time. The system can be modified immediately afterward by another person or tool.

## 11. Pre-Automation Provisioning Checklist

- [ ] Describe desired state rather than only listing creation actions.
- [ ] Choose stable resource IDs, logical names, or idempotency keys.
- [ ] Verify whether the API supports idempotency keys and key retention duration.
- [ ] Design retries with backoff, retry caps, and operation polling on timeouts.
- [ ] Distinguish desired state, actual state, and recorded state.
- [ ] Use an appropriate remote backend for team environments.
- [ ] Enable locking if supported by the backend and coordinate pipelines.
- [ ] Encrypt state, restrict access permissions, and never commit state to Git.
- [ ] Enable versioning/backups and test recovery procedures.
- [ ] Establish workflows for refresh, import, and moving resource addresses.
- [ ] Inspect plans before apply and verify status after apply.
- [ ] Handle dependencies and readiness with health checks or wait conditions.
- [ ] Log operation IDs, resource IDs, and outcomes without exposing secrets.
- [ ] Maintain runbooks for lost state, timeouts, stuck locks, or failed applies.

## 12. Takeaways

- **Idempotency** ensures repeated operations bring resources to the same target state, making retries safer.
- **Desired state, actual state, and recorded state** are three distinct perspectives that must be reconciled.
- **Idempotency keys** help APIs recognize retries of the same intent, when supported by the service.
- **Terraform state** links resource addresses to resource IDs and stores information needed for lifecycle management.
- **Remote backends, locking, encryption, and backups** enable teams to manage state safely and consistently.
- **Import and moved blocks** support bringing existing resources under management or renaming logical addresses without recreating resources.
- **Retries must account for operation state and eventual consistency.** A timeout does not prove an operation failed.
- **Plans and health checks** verify that the system has reached the desired state before proceeding to subsequent steps.

## Key Terms

| Term | Meaning |
|---|---|
| Idempotency | Property where repeating an operation still produces the same final state. |
| Desired state | Resource state specified by declarative configuration. |
| Actual state | State of resources currently existing in the cloud system. |
| Recorded state | State recorded by the IaC tool to track resources. |
| State backend | Location where an IaC tool stores state. |
| State locking | Mechanism locking state to prevent concurrent writes. |
| Idempotency key | Key enabling an API to identify retries of the same request. |
| Resource address | Logical address of a resource in IaC configuration. |
| Resource ID | Resource identifier issued by a provider or platform. |
| Refresh | Process of reading live state to update management records. |
| Import | Bringing existing resources under IaC management scope. |
| Configuration drift | Difference between standard configuration and actual live state. |
| Reconcile | Comparing actual state and bringing it to desired state. |
| Eventual consistency | Consistency model where reads may take time to reflect recent updates. |
| Retry with backoff | Retrying with increasing wait intervals to reduce pressure on services. |
| Ansible module | Component executing a configuration management task, typically capable of checking desired state. |
| creates | Ansible command condition to skip execution when a specified file already exists. |
| changed_when | Ansible expression controlling whether a task reports as changed; does not itself prevent command re-execution. |
