# Provisioning Compute via Console, CLI, SDK, and API

Cloud computing enables creating virtual machines, container clusters, and serverless environments on demand. To bring an application into operation, operations teams need to select the right resource type, configure networking and storage, attach access permissions, initialize software, and monitor provisioning status. Providers typically allow performing these tasks via a web console, command-line interface (CLI), software development kit (SDK), or API.

These four approaches share the same control plane and can generally create the same types of resources. The differences lie in how users describe requirements, the level of automation, the ability to integrate into applications, and how changes are controlled. Understanding each approach helps select the right tool for exploratory tasks, repetitive workflows, and large-scale deployment systems.

After this lesson, you will be able to:

- Explain the roles and strengths of the console, CLI, SDK, and API.
- Identify the required information before creating compute resources.
- Execute the virtual machine provisioning workflow via the interface or command line.
- Use an SDK to integrate provisioning operations into a program.
- Understand the lifecycle of an API request, authentication, responses, and error handling.
- Design processes that are repeatable, auditable, secure, and capable of reclaiming resources.

## 1. What Does Compute Provisioning Include?

Provisioning is the process of requesting the platform to create, configure, or reclaim compute resources. For a virtual machine, creating the machine is usually only part of the workflow. A machine may enter an initializing state before the operating system boots and the application is ready to receive traffic.

A virtual machine provisioning request typically needs to specify:

| Component | Decisions Required | Example |
|---|---|---|
| Location | Region, zone, or availability zone | Region close to users and data |
| Image | Operating system or prepared image | Linux LTS with required runtime pre-installed |
| Size | CPU, RAM, GPU, and hardware characteristics | 4 vCPU, 16 GiB RAM |
| Storage | Disk type, capacity, encryption, and deletion policy | 50 GiB SSD, encrypted at rest |
| Network | VPC/VNet, subnet, IP, and firewall rules | Private subnet, allow HTTPS only via load balancer |
| Identity | Role, service account, or managed identity | Read permission for a specific data bucket |
| Initialization | Script, custom image, or deployment configuration | Install monitoring agent and download application |
| Governance | Labels, tags, owner, environment, and expiration | Environment=dev, Owner=platform |
| Lifecycle | Auto-stop, deletion, backup, and replacement | Delete test machine after 8 hours |

For containers, the provisioned target may be a cluster, node pool, task, or workload. For serverless, operators typically declare a function, runtime configuration, memory, maximum execution duration, access permissions, and trigger sources. Although the interfaces differ, the principles regarding location, resources, networking, identity, configuration, and lifecycle remain similar.

### Choosing the Compute Model Before Choosing the Tool

- **Virtual Machine (VM):** suitable when you need control over the operating system, background processes, machine configuration, or software installed directly on the host.
- **Container:** suitable when the application is already packaged as an image and needs consistent deployment across a cluster or orchestration platform.
- **Serverless:** suitable for event-driven tasks or variable workloads where you want the provider to manage most of the underlying servers.

The console, CLI, SDK, and API are ways to control these services. Choosing a tool does not replace the step of analyzing the workload and operational requirements.

## 2. Four Ways to Work with a Cloud Platform

### Console: Operating via Web Interface

The console is the graphical interface provided by the cloud provider. Users log in, select a service, fill out forms, review the configuration, and confirm the action. The console is typically suitable for exploring services, inspecting existing resources, or creating a test environment.

**Strengths**

- Displays provider options and descriptions right where configurations are made.
- Easy to observe status, alerts, and related parameters.
- Useful for beginners or rarely performed operations.

**Limitations**

- Easy to miss a configuration field or create slightly different environments across manual runs.
- Hard to repeat accurately across multiple accounts, regions, or environments.
- Hard to integrate directly into automation pipelines and code-review workflows.

The console can still serve as a place to inspect the results of an automated workflow. However, for repetitive operations, teams should store configurations as code or use automation tools with state management.

### CLI: Controlling via Commands

A CLI (Command-Line Interface) is a program that runs in a terminal. Users pass parameters, configuration files, and subcommands to create, view, update, or delete resources.

For example, the AWS CLI can create an EC2 instance using the command aws ec2 run-instances. Other CLIs have similar commands, though the syntax, resource names, and authentication rules will differ.

**Strengths**

- Commands can be saved as scripts and re-run in pipelines.
- Can be combined with JSON processing tools, shells, and CI/CD systems.
- Often supports dry-run options or status checks before making changes.

**Limitations**

- Requires knowing the syntax, CLI version, and parameter formats.
- Scripts lacking error checking can create duplicate resources or leave dangling partial resources.
- Configuration depends on the terminal environment, profile, region, and environment variables.

The CLI is suitable for operational tasks with clear procedures, repetitive administrative work, and deployment steps in CI/CD.

### SDK: Controlling from a Program

An SDK (Software Development Kit) is a set of libraries provided by the cloud vendor for a programming language. A program can call functions to create machines, query status, attach labels, modify configurations, or handle events.

For example, a Python application can use an SDK to create a virtual machine after a job record is approved. SDKs typically provide object classes, type checking, pagination, retries, and authentication handling more conveniently than manually crafting HTTP requests.

**Strengths**

- Integrates cloud operations into backends, internal tools, or self-service platforms.
- Can apply business logic, input validation, and audit logging directly inside the program.
- Easy to combine with queues, databases, and orchestration systems.

**Limitations**

- Must manage library versions, dependencies, and runtime compatibility.
- Application code must handle timeouts, retries, asynchronous states, and partial failures.
- Provisioning logic can become difficult to test if tightly coupled to external systems.

An SDK is suitable when an application needs to interact with cloud resources as part of a business workflow.

### API: Direct Communication via Protocol

An API (Application Programming Interface) is the interface a service exposes for other systems to send requests and receive results. For cloud services, APIs typically use HTTPS and JSON data or a provider-specific format. The CLI and SDK largely call these underlying APIs as well.

An API request typically contains:

- The service endpoint and the operation to perform.
- Authentication credentials or a digital signature for the request.
- Headers such as content type, API version, and correlation ID.
- A body describing the resource to be created or modified.

**Strengths**

- Enables integration from any language or environment capable of sending HTTP requests.
- Provides fine-grained control over requests, headers, and responses.
- Useful when building a unified integration layer or when an SDK does not yet support a new feature.

**Limitations**

- Developers must understand request signing mechanisms, tokens, API versions, and error formats.
- Must manually handle pagination, retries, timeouts, polling, and API compatibility.
- A minor error in signing or parameter encoding can cause the request to be rejected.

An API is suitable when low-level integration is needed, to support features not yet in the SDK, or to build a programming-language-independent adapter.

### Quick Comparison

| Criterion | Console | CLI | SDK | API |
|---|---|---|---|---|
| Interaction method | Web forms and buttons | Terminal commands | Functions and objects in code | HTTP requests or service protocol |
| Getting started | Easy | Need to learn syntax | Need to know language and library | Need to understand protocol and auth |
| Repeatability | Low if done manually | Good with scripts | Good with programs | Good with API-calling systems |
| CI/CD integration | Indirect | Very suitable | Suitable | Suitable |
| Result visibility | Visual | Via output and queries | Via responses and logs | Via status codes and responses |
| Granular control | By UI fields | By command parameters | By SDK functions | Most granular at request level |
| Best use cases | Exploration, manual tasks | Operations and pipelines | In-application automation | Custom integrations, adapters |

There is no single best tool for every situation. You can use the console to explore a configuration, then turn the well-understood workflow into CLI scripts, SDK code, or infrastructure as code for consistent deployment.

## 3. Preparing Before Provisioning

A machine creation command succeeding does not guarantee that the application will be secure or function properly. Before invoking any tool, you need to prepare the required information and verify relevant prerequisites.

### Define Resource Requirements

Document requirements for CPU, RAM, GPU, storage capacity, network bandwidth, operating system, CPU architecture, and runtime duration. Based on workload characteristics, select the appropriate machine type. If metrics are not yet available, start with a small configuration in a test environment, measure utilization, and then adjust.

For GPU workloads, verify the GPU model, device memory capacity, number of GPUs per machine, inter-GPU interconnects, and quota in the target region. For container workloads, define both node resources and the requests/limits for each workload.

### Select Image and OS Version

An image is the template used to initialize a machine. You can use a provider-standard image, an organization-maintained image, or an image pre-packaged with the application. Verify that:

- The image has the correct operating system, architecture, and a still-supported version.
- The image comes from a trusted source and has a security patching process.
- GPU drivers, management agents, and required runtimes are compatible.
- The image does not contain sensitive data or secrets unsuitable for cloning.

Do not use an image from an unknown source simply because it has the desired software pre-installed. In production environments, standardize images, track versions, and update them through a formal process.

### Design Networking and Access Permissions

Choose the VPC/VNet, subnet, route table, firewall/security group, and administrative access method. Backend servers usually do not need a public IP address. If they need to receive Internet traffic, place them behind a load balancer or a controlled gateway.

Network rules should restrict source, destination, and ports based on actual needs. For example, SSH ports should not be opened to the entire Internet; use a VPN, bastion host, or controlled remote management service. Application services should only accept traffic from the load balancer or authorized components.

Attach a role or service account with least-privilege permissions. Do not embed long-lived access keys into user data, images, scripts, or source code. Prefer workload identities and the provider's temporary credential issuance mechanisms.

### Prepare Storage and Initialization

Determine disk type, capacity, performance, encryption, snapshots, and deletion policy when the machine is terminated. Data that needs to persist long-term should be placed on an independent storage service or a volume with an appropriate lifecycle.

A startup script or cloud-init can install packages, generate configurations, and start services on first boot. Scripts must run safely, write logs, check for errors, and avoid storing secrets in plaintext. For environments requiring high repeatability, package software into an image or container rather than installing too many steps on every boot.

### Check Quota, Region, and Cost

Confirm that the account has permissions to create resources, sufficient quota is available, and the machine type can be provisioned in the chosen region/zone. Estimate costs for the compute instance, disks, public IPs, snapshots, data transfer, and supporting services. Apply tags or labels immediately upon creation to track owner, environment, project, and cost center.

## 4. Provisioning via Console

Menu names vary by provider, but the workflow for creating a virtual machine typically consists of the following steps:

1. Log in to the console using an authorized account or work identity.
2. Select the correct project/account and region/zone.
3. Open the virtual machine service and choose to create an instance.
4. Select the image, operating system version, and machine type based on required CPU/RAM/GPU.
5. Configure disks, capacity, encryption, and deletion policy.
6. Select the network, subnet, IP address, and firewall rules.
7. Attach a role or service account with least-privilege permissions.
8. Configure administrative access method, startup script, and required metadata.
9. Attach tags/labels for management and cost allocation.
10. Review the configuration summary page, confirm costs, and create the machine.
11. Monitor status until the machine is ready, then verify login, services, and initialization logs.

The summary page before creation is critical: double-check the region, subnet, public IP, access permissions, and disks. A default form selection might open wide network ports or create the machine in a higher-cost region than expected.

The console typically displays states such as Pending, Provisioning, Running, or Failed. Exact names and meanings depend on the service. A Running state only indicates the machine is powered on; it does not prove the application is ready. Check the application's health check or endpoint before routing traffic.

## 5. Provisioning via CLI

The CLI is suitable when you want to save commands, re-run across environments, or integrate operations into a pipeline. Install the official CLI, check its version, configure a profile, and authenticate with an authorized identity.

### Example: Creating an EC2 Machine with AWS CLI

The example below illustrates creating an EC2 instance on AWS. Values such as ami-..., subnet-..., sg-..., and the instance profile name are placeholders; you must replace them with valid resources in your account and region. This is a Bash example.

~~~bash
aws sts get-caller-identity

aws ec2 run-instances \
  --image-id ami-0123456789abcdef0 \
  --instance-type t3.medium \
  --subnet-id subnet-0123456789abcdef0 \
  --security-group-ids sg-0123456789abcdef0 \
  --iam-instance-profile Name=app-instance-profile \
  --metadata-options HttpEndpoint=enabled,HttpTokens=required \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=compute-demo},{Key=Environment,Value=dev},{Key=Owner,Value=platform}]' \
  --count 1
~~~

First, aws sts get-caller-identity confirms the current identity. The run-instances command requires an image, machine type, subnet, security group, and instance profile. Metadata options enforce IMDSv2; block device mapping creates an encrypted disk; tag specification attaches labels to the machine.

In real-world environments, pass configurations via reviewed JSON files or securely managed environment variables. Avoid putting tokens or passwords directly in commands because shell history and pipeline logs may record that content.

### Monitoring and Managing the Machine After Creation

The creation command may return before the operating system is ready. Use status query commands to confirm:

~~~bash
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=compute-demo" \
  --query "Reservations[].Instances[].[InstanceId,State.Name,PrivateIpAddress]" \
  --output table

aws ec2 wait instance-status-ok \
  --instance-ids i-0123456789abcdef0
~~~

describe-instances helps check the ID, state, and private IP address. wait instance-status-ok waits until instance status checks pass or times out. Afterward, you still need to check the application via a health endpoint or monitoring tool.

When the test environment is no longer needed, stop or delete the machine according to data policies:

~~~bash
aws ec2 terminate-instances \
  --instance-ids i-0123456789abcdef0
~~~

Terminating can delete volumes configured with DeleteOnTermination; retained volumes and snapshots may continue to incur charges. Always check storage and backup policies before deleting resources.

### Writing Controlled CLI Scripts

A deployment script should perform these steps: confirm identity, validate parameters, verify quota and networking, create resources, wait for status, run health checks, record IDs, and handle errors. If a step fails, the script needs to store information so it can resume or reclaim already created resources.

Do not use a resource name as a unique identifier if that name can collide. Store the ID returned by the platform, attach deployment-identifying labels, and check for existing resources before creating new ones.

## 6. Provisioning via SDK

An SDK allows programs to call cloud services using structured functions. The example below uses Python and boto3 to create an EC2 instance. You need to install the library in your runtime environment with pip install boto3, configure AWS credentials via profile or role, and replace the placeholder IDs.

~~~python
import boto3
from botocore.exceptions import BotoCoreError, ClientError

region = "ap-southeast-1"
ec2 = boto3.client("ec2", region_name=region)

try:
    response = ec2.run_instances(
        ImageId="ami-0123456789abcdef0",
        InstanceType="t3.medium",
        MinCount=1,
        MaxCount=1,
        SubnetId="subnet-0123456789abcdef0",
        SecurityGroupIds=["sg-0123456789abcdef0"],
        IamInstanceProfile={"Name": "app-instance-profile"},
        MetadataOptions={
            "HttpEndpoint": "enabled",
            "HttpTokens": "required",
        },
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvda",
                "Ebs": {
                    "VolumeSize": 30,
                    "VolumeType": "gp3",
                    "Encrypted": True,
                    "DeleteOnTermination": True,
                },
            }
        ],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "compute-demo"},
                    {"Key": "Environment", "Value": "dev"},
                    {"Key": "Owner", "Value": "platform"},
                ],
            }
        ],
        ClientToken="compute-demo-deployment-2026-01",
    )
    instance_id = response["Instances"][0]["InstanceId"]
    print(f"Created instance: {instance_id}")

    waiter = ec2.get_waiter("instance_status_ok")
    waiter.wait(InstanceIds=[instance_id])
    print("Instance status checks passed")

except (ClientError, BotoCoreError) as error:
    print(f"Provisioning failed: {error}")
    raise
~~~

In the example:

- The client is created for a specific region.
- run_instances accepts machine configuration, networking, identity, metadata, disks, and tags.
- ClientToken is a deduplication token providing idempotency within the service's defined time window. In a real design, the token must be tied to a logical deployment and stored stably so retries do not inadvertently create new machines.
- The waiter waits for the machine's status checks. The application still needs its own health check step.
- Errors from the service or SDK layer are captured and propagated for the calling flow to handle.

This snippet only illustrates the provisioning flow. A complete internal service needs input validation, machine count limits, requester authorization checks, audit logging, timeouts, and a cleanup strategy if the deployment fails midway.

### Error Management and Retries in SDKs

Not every error should be retried:

- Authentication or permission errors usually require fixing the identity configuration.
- Invalid parameters or invalid images require fixing the input.
- Exceeding quota requires requesting a quota increase or choosing a different configuration.
- Temporary capacity shortages can be retried with backoff and jitter if the operation is safe.
- A timeout does not mean the operation failed: the resource may have been created while the response was lost. Before resending, query by client token, tag, or deployment ID to determine the outcome.

Retrying a resource creation request without idempotency can create multiple identical machines. For non-idempotent operations, design a deduplication lock or state reconciliation process.

## 7. Provisioning via API

The API is the foundation of the console, CLI, and SDK. When calling it directly, a program must follow the authentication protocol and request format specified by the provider.

An API workflow typically includes these steps:

1. Obtain short-lived credentials from an identity provider or workload identity mechanism.
2. Build the request including endpoint, method, headers, and body.
3. Sign the request or attach an access token as required by the service.
4. Send the HTTPS request with an appropriate timeout.
5. Read the HTTP status code and response body.
6. If the operation is asynchronous, extract the operation ID and poll status until completion.
7. Record the request ID, operation ID, and result for auditing or investigation.

### Example Machine Creation Request Structure

Provider APIs do not share a single endpoint or schema. The JSON below is an illustrative example modeled after a compute management API, not a directly callable endpoint:

~~~http
POST /v1/projects/project-demo/instances
Authorization: Bearer <short-lived-access-token>
Content-Type: application/json
Idempotency-Key: deploy-2026-001
~~~

~~~json
{
  "name": "app-worker-01",
  "location": {
    "region": "region-a",
    "zone": "zone-a"
  },
  "machine": {
    "image": "linux-lts-approved",
    "cpu": 4,
    "memoryGiB": 16
  },
  "network": {
    "subnet": "private-app-subnet",
    "publicIp": false,
    "firewallPolicy": "app-worker-policy"
  },
  "identity": {
    "serviceAccount": "app-worker"
  },
  "storage": [
    {
      "sizeGiB": 50,
      "encrypted": true,
      "deleteWithInstance": true
    }
  ],
  "labels": {
    "environment": "dev",
    "owner": "platform"
  }
}
~~~

The API may return 200 OK or 201 Created if the resource is created synchronously; for long-running operations, the service may return 202 Accepted with an operation ID. Clients need to consult the API documentation to know exactly which status means creation is finished.

Example asynchronous response:

~~~json
{
  "operationId": "op-7f12a",
  "status": "PENDING",
  "resource": "instances/app-worker-01"
}
~~~

The client uses the operation ID to poll status. Upon completion, the response may contain the resource ID, network addresses, or detailed errors. Do not treat 202 Accepted as meaning the application is ready.

### Status Codes and Handling

| HTTP status | Common Meaning | Handling Approach |
|---|---|---|
| 200/201 | Request succeeded or resource created | Read response and verify resource status |
| 202 | Request accepted, processing in background | Save operation ID and poll per documentation |
| 400 | Malformed request or invalid parameters | Fix schema and input data |
| 401 | Missing or invalid token | Refresh authentication credentials |
| 403 | Identity lacks permission | Check IAM policy and permission scope |
| 404 | Resource or endpoint does not exist | Check ID, region, and API version |
| 409 | State conflict or duplicate resource | Read conflict details and reconcile state |
| 429 | Rate limited or quota exceeded | Backoff, reduce call rate, or request quota increase |
| 500/503 | Service-side error or temporary unavailability | Retry with limits if operation is safe; track request ID |

Never retry infinitely. Use exponential backoff with jitter, cap total retry duration, and distinguish recoverable errors from configuration errors. If a machine creation request times out, check the resource status before resending.

## 8. From Individual Actions to Repeatable Automation

The console, CLI, SDK, and API can all create resources. To operate reliably, teams need a process that clearly defines inputs, desired state, change permissions, and failure handling.

### Imperative vs. Declarative

**Imperative** describes the actions to execute: create a machine, attach a disk, add a network rule, then start the service. The CLI and SDK are commonly used this way.

**Declarative** describes the desired state: require a machine with a specific image, size, network, and tags. The tool compares the current state with the declared state and creates, updates, or replaces resources to reach the desired state.

Infrastructure as Code (IaC) is the practice of storing infrastructure configurations as code that can be reviewed, versioned, and deployed repeatably. Terraform, OpenTofu, and other IaC tools can use provider APIs to execute changes. IaC is particularly useful when an environment consists of multiple interdependent resources such as networking, IAM, virtual machines, load balancers, and monitoring.

| Approach | Description | Key Considerations |
|---|---|---|
| Manual console | Operator modifies each field | Document configurations and check for drift |
| CLI script | Sequential commands | Check exit codes, retries, and cleanup |
| SDK program | Provisioning logic inside an application | Separate business logic, testing, and auditing |
| Direct API | Manually build requests to the service | Authentication, schema, versioning, and retries |
| Declarative IaC | Describe desired state | Review plans, manage state, and detect drift |

For long-lived resources, IaC typically provides better change control. For short-lived or event-driven tasks, CLI/SDK/API may be more suitable. Approaches can be combined, provided a single clear source of state management is defined so two processes do not modify the same resource simultaneously.

### A Sample Provisioning Pipeline

~~~mermaid
flowchart TD
    A["Receive compute request"] --> B["Authenticate requester and validate parameters"]
    B --> C["Check quota, policy, and cost"]
    C --> D["Create resources via CLI, SDK, API, or IaC"]
    D --> E["Wait for operation completion"]
    E --> F["Check health and security configuration"]
    F --> G{"Meets criteria?"}
    G -- "Yes" --> H["Record ID, tags, and audit log"]
    G -- "No" --> I["Reclaim or rollback per policy"]
    I --> J["Log error and notify operations system"]
~~~

A pipeline should record the requester, approved configuration, code version, resource ID, creation timestamp, and check results. These records aid debugging when errors occur and support cost allocation.

## 9. Security in the Provisioning Workflow

Provisioning has the authority to create infrastructure and incur costs. Therefore, the identity invoking the tool and the resource configurations must be controlled.

- **Least privilege:** grant only the permissions required for allowed resource types, projects, and regions.
- **Temporary credentials:** prefer short-lived tokens, roles, or workload identities over long-lived keys.
- **Network isolation:** open only necessary ports; use private subnets and controlled administrative access points.
- **Secure metadata:** enable platform-supported secure metadata mechanisms; restrict metadata access from workloads.
- **Encryption:** encrypt volumes, snapshots, and data in transit according to organizational policy.
- **Image governance:** use only approved, vulnerability-scanned, and patched images.
- **Audit trail:** log the caller, action, request ID, configuration, and timestamp of changes.
- **Secret handling:** store secrets in a secret manager; do not write them into user data, tags, or logs.
- **Policy guardrails:** block non-compliant configurations such as unintended public IPs, unencrypted disks, or out-of-budget machine types.

Separate permissions for creating resources, modifying networking, and deleting data. Within pipelines, only allow deployments to designated projects/accounts and environments.

## 10. Lifecycle and Cost Monitoring

Compute resources can outlive their original purpose if no reclamation rules exist. Every resource should have an owner, project, environment, and an expiration date or lifecycle policy.

Key metrics to monitor include:

- Machine counts by status, region, and machine type.
- Actual CPU, RAM, GPU, storage, and network utilization.
- Time from request submission until the machine or application is ready.
- Provisioning success rate, quota errors, permission errors, and capacity shortage errors.
- Cost by project, owner, environment, and work unit.
- Unowned resources, idle machines, orphaned disks, and unused IPs.

For development environments, machines can be automatically stopped after hours or deleted after expiration. For production environments, integrate maintenance schedules, backups, availability requirements, and approval processes.

### Stop and Delete Are Two Different Operations

**Stop/deallocate** typically releases compute capacity while retaining certain resources like disks. Compute charges may stop, but storage, static IPs, or related services may still incur fees.

**Terminate/delete** removes the machine object. Volumes, snapshots, IPs, and data may be kept or deleted depending on policy. Before deleting, determine what data must be preserved, whether backups can be restored, and whether dependent resources will be affected.

Automated reclamation should include allowlists/denylists, grace periods, and complete logging. Do not delete solely based on low CPU over a short period; a machine might be waiting for a scheduled task or serving as standby capacity.

## 11. Common Provisioning Issues

| Symptom | Possible Cause | Inspection and Resolution |
|---|---|---|
| Access denied / 403 | Role lacks permission or policy blocks action | Check identity, scope, and audit logs |
| Image not found | Wrong region, ID, or image was removed | Verify image in the correct account and region |
| Insufficient capacity | Region lacks capacity for the machine type | Try another zone, alternative machine type, or reservation |
| Quota exceeded | Account limit reached | Check quota, reclaim excess resources, or request increase |
| Machine running but cannot SSH | Wrong route, firewall, IP, or access key | Check network path and use approved management channel |
| Machine running but app not ready | Startup script failed, missing dependency, or failed health check | Inspect system log, cloud-init log, and application log |
| Command timed out but machine exists | Request was processed but response was lost | Look up by client token, tag, or operation ID before retrying |
| Abnormally high cost | Idle machines, oversized machine type, or orphaned supporting resources | Review cost reports, utilization, and orphaned resources |

When investigating, record the request ID, operation ID, resource ID, timestamp, and region. This information helps operations teams look up provider-side logs.

## 12. Comprehensive Example: Creating a Worker for a Test Environment

A team needs to create a worker machine to process a queue in the development environment. The machine requires 4 vCPU, 16 GiB RAM, an encrypted disk, no public IP, and access restricted to the application subnet.

The workflow can be implemented as follows:

1. The application team submits a request specifying purpose, owner, expiration, and expected load.
2. The system verifies the requester has permission to create workers in the dev project.
3. The pipeline checks quota, approved image, private subnet, and security group.
4. The machine is created via CLI or SDK with a role that can only read the queue and write results to target storage.
5. The startup script installs the monitoring agent, fetches non-secret configuration, and starts the worker.
6. The pipeline waits for the machine to become ready and then calls the health check. If checks fail, the resource is marked as failed and handled per the reclamation policy.
7. Tags record Environment=dev, Owner=team-app, Purpose=queue-worker, and ExpiresAt so cleanup systems can identify it.
8. After testing ends, the worker is stopped or deleted; data that must be kept is moved to independent storage.

For a single test machine, the console may suffice for initial validation. When the team needs to create multiple workers on demand or on a schedule, the same configuration should be converted into a reviewed CLI script, SDK program, or IaC module.

## 13. Pre- and Post-Provisioning Checklist

**Before Creation**

- [ ] Selected compute model and configuration appropriate for the workload.
- [ ] Verified image, architecture, version, and source.
- [ ] Checked region, zone, quota, and capacity availability.
- [ ] Defined subnet, firewall, IP, and administrative access method.
- [ ] Attached role/service account with least-privilege permissions.
- [ ] Configured storage, encryption, and data retention policy.
- [ ] Estimated costs and attached governance tags/labels.
- [ ] Prepared testable startup script or deployment image.

**After Creation**

- [ ] Saved resource ID, request ID, and operation ID.
- [ ] Confirmed machine status and application health check.
- [ ] Verified initialization logs, access permissions, and network connectivity.
- [ ] Confirmed monitoring, alerting, and cost allocation.
- [ ] Assigned owner and lifecycle expiration.
- [ ] Tested stop, delete, and data recovery procedures.

## 14. Practice Exercise

A team needs to create 20 identical worker machines across two regions to run batch jobs. The machines only run for a few hours, need to access a queue, and write results to object storage. The team wants to minimize manual operations and avoid creating duplicate machines when pipelines time out.

1. Would you choose console, CLI, SDK, API, or IaC as the primary deployment method? Explain based on frequency, repeatability, and pipeline integration.
2. List the parameters that must be standardized before provisioning the 20 machines.
3. Design a mechanism to prevent duplicates when a machine creation request times out even though the service may have processed it successfully.
4. Propose IAM permissions, network configuration, and how credentials should be provided to the workers.
5. Define how to monitor health, cost, and reclaim the machines after the batch finishes.

Hint: consider declaring a shared configuration, using a stable deployment ID or idempotency key, checking status before retrying, scoping permissions to specific resources, and attaching tags with owner/expiration. Also account for boot time, storage, and cross-region data transfer.

## Conclusion

The console aids exploration and visual operations; the CLI suits scripts and pipelines; the SDK brings provisioning capabilities into programs; and the API enables protocol-level integration. Regardless of the method used, the process must still define compute configuration, networking, storage, identity, cost, and lifecycle. When automating, always check status after each operation, design idempotency and safe retries, keep audit logs, run health checks, and reclaim resources according to policy.
