# Instance Metadata Service and Enforcing IMDSv2 on Amazon EC2

The **Instance Metadata Service (IMDS)** is a service available to every Amazon EC2 instance that allows software running inside the instance to retrieve information about that machine: instance ID, Region, Availability Zone, certain networking details, and—when an **IAM instance profile** is attached—temporary security credentials for the corresponding IAM role. Because this endpoint can issue credentials to workloads, controlling access to IMDS is a critical part of EC2 security.

**IMDSv2** uses session tokens to access metadata. When **HttpTokens = required** is set, EC2 accepts only IMDSv2 requests bearing a valid token, reducing several metadata-endpoint abuse risks compared to IMDSv1. However, securing IMDS does not stop at toggling one option: applications and SDKs must be compatible, IAM policies must constrain permissions, and containerized workloads must have their network path to the endpoint verified.

This lesson belongs to the **EC2 Instances** chapter of the **CLOUD_PROVIDERS_AWS** module. Understanding IMDS helps learners explore the AWS ecosystem from Regions/AZs, IAM, and VPC to compute, storage, databases, integration, and serverless; design applications with secure authorization, monitoring, and strong resilience; and avoid unexpected operational costs caused by misconfiguration or faulty deployments.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. State what **IMDS** provides and distinguish metadata, user data, instance profiles, and IAM role credentials.
2. Explain the difference between **IMDSv1** and **IMDSv2**, and the roles of HTTP PUT, session tokens, time-to-live (TTL), and HTTP GET.
3. Configure EC2 to enforce IMDSv2 with **HttpTokens = required**, while understanding **HttpEndpoint**, **HttpPutResponseHopLimit**, **HttpProtocolIpv6**, and **InstanceMetadataTags**.
4. Explain the precedence order among instance/launch template settings, account-level Regional defaults, and AMIs.
5. Use the AWS CLI and safe HTTP commands to inspect IMDSv2 configuration/access without printing sensitive credentials to logs.
6. Plan a migration from IMDSv1 to IMDSv2 across EC2 fleets, ASGs, SDKs, agents, and containers without disrupting applications.
7. Diagnose common issues such as **401 Unauthorized**, timeouts fetching tokens, and missing role credentials.

## 2. What Is IMDS and When Is It Used?

IMDS is an endpoint attached to **each EC2 instance**, accessible from the operating system or authorized processes on that instance. Its well-known IPv4 address is **169.254.169.254** (a link-local address), with paths under **/latest/**. This is not a standard public Internet endpoint; returned data describes **the instance making the request**, not the entire AWS account.

| Information Group | Example Content | Practical Use |
|---|---|---|
| Instance identity | Instance ID, AMI ID, instance type | Correlating logs/metrics to the exact machine, startup diagnostics |
| Deployment location | Region, Availability Zone, instance identity document details | Detecting environment and configuring service endpoints |
| Networking | Local IPv4, MAC, supported network interface details | Network observability and agent configuration |
| User data | Initialization data passed at launch | Bootstrap scripts, initial installation/configuration |
| IAM role credentials | Temporary credentials for the role attached via instance profile | SDK/CLI calls to S3, DynamoDB, CloudWatch... per IAM role |
| Instance tags (when enabled) | Selected instance tags exposed via metadata | Workload configuration and classification if approved |

**Note:** not every field or feature exists on every instance family, image, or version; some items depend on configuration. Always check documentation for the metadata version in use.

### 2.1. How Does Metadata Differ from User Data?

**Metadata** is information provided by EC2 about the instance. **User data** is content supplied by the deployer when creating the instance, typically for bootstrapping. Both can be accessed from inside the instance via their respective paths, so **never place passwords, API keys, or long-lived secrets directly in user data**. For sensitive values, use an appropriate secrets management service paired with an IAM role.

### 2.2. IMDS and IAM Instance Profiles

For EC2 to call AWS APIs under a role's permissions, you normally attach an **IAM role to the instance via an instance profile**. AWS delivers temporary credentials to the instance; the SDK or AWS CLI automatically fetches and refreshes those credentials through the provider chain when no higher-priority credential source is present.

~~~mermaid
flowchart LR
    APP["Application / AWS SDK<br/>on EC2"] -->|"1. Fetch IMDSv2 token"| IMDS["Instance IMDS"]
    IMDS -->|"2. Metadata / role credentials"| APP
    PROFILE["IAM instance profile + role"] -. "Role permissions granted to EC2" .-> IMDS
    APP -->|"3. API request signed with<br/>temporary credentials"| S3["S3 / DynamoDB / CloudWatch"]
    S3 -->|"4. IAM and resource policies<br/>evaluate access"| APP
~~~

An IMDSv2 token is only for **querying metadata**; it **is not** an AWS access key, cannot substitute for SigV4 signing, and **does not grant IAM permissions**. API authorization still comes from the role, applicable policies, and request context.

**Best practice:** let the AWS SDK/CLI manage credential lifecycles automatically through the **default credential provider chain** and instance role. Do not manually read and write access keys/secret keys/session tokens retrieved from metadata into files, logs, or source code.

## 3. Comparing IMDSv1 and IMDSv2

| Criterion | IMDSv1 | IMDSv2 |
|---|---|---|
| How metadata is accessed | Direct HTTP GET | HTTP PUT to get a token, then GET/HEAD with the token |
| Token | None | Per-instance session token |
| Token lifetime | Not applicable | From **1 to 21,600 seconds** (up to 6 hours) |
| Can be requested from inside the instance | Yes, if the instance permits it | Yes, if the IMDS endpoint is enabled |
| Required header to read metadata | No token header needed | **X-aws-ec2-metadata-token** |
| SSRF/proxy mitigation controls | Few constraints at the IMDS layer | Separate PUT, session token, rejects certain proxy headers, and response hop limit |
| Which EC2 setting enforces it | **HttpTokens = optional** still accepts it | **HttpTokens = required** rejects tokenless requests |

If an instance sets **HttpTokens = optional**, both IMDSv1 and IMDSv2 can work. Only **HttpTokens = required** actually **enforces IMDSv2**; software merely choosing IMDSv2 does not mean IMDSv1 is disabled on the instance.

### 3.1. Why Is IMDSv2 More Secure?

A classic risk is **Server-Side Request Forgery (SSRF)**: a web application is tricked into sending HTTP requests to an attacker-chosen address. If the web server can reach IMDS, metadata or role credentials can leak when the application layer has a vulnerability and lacks additional controls.

IMDSv2 adds multiple hurdles against common abuse techniques:

- Requires starting with an **HTTP PUT** to obtain a token before sending a GET with the token header; a simple GET-only SSRF vector has a much harder time satisfying this flow.
- The token endpoint rejects PUT requests containing **X-Forwarded-For**, mitigating certain exploits through misconfigured reverse proxies.
- Tokens are bound to the instance that created them and remain valid only for the requested TTL; a token cannot be reused from another instance.
- **HttpPutResponseHopLimit** caps the IP hop count on **the PUT token response**, helping restrict unintended traversal across proxies/containers.

**Do not misunderstand:** IMDSv2 is a **defense-in-depth** layer. Malware or processes that already have permission to execute PUT and GET from inside the instance can still obtain a token and query metadata. Therefore, continue patching SSRF/RCE flaws, restricting metadata access for unneeded processes, enforcing least-privilege IAM, and isolating workloads.

## 4. IMDSv2 Token Mechanism Step by Step

### 4.1. Request Flow

~~~mermaid
sequenceDiagram
    participant App as Process on EC2
    participant IMDS as 169.254.169.254
    App->>IMDS: PUT /latest/api/token<br/>TTL header
    IMDS-->>App: Session token
    App->>IMDS: GET /latest/meta-data/instance-id<br/>X-aws-ec2-metadata-token
    IMDS-->>App: Instance ID
    Note over App,IMDS: Generate a new token when TTL expires
~~~

**Step 1 — fetch a token.** Run the command below **directly inside an authorized EC2 Linux test instance**. This example stores the token in a shell variable so it is not printed to the terminal:

~~~bash
TOKEN=$(curl -fsS --noproxy '*' \
  -X PUT 'http://169.254.169.254/latest/api/token' \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600')
~~~

**Step 2 — read metadata with the token.**

~~~bash
curl -fsS --noproxy '*' \
  -H "X-aws-ec2-metadata-token: $TOKEN" \
  'http://169.254.169.254/latest/meta-data/instance-id'
~~~

**Step 3 — reuse within the valid window.** The same token can serve subsequent GET/HEAD requests for the duration of the TTL. Once expired, request another token via PUT. TTL is the IMDSv2 session lifetime, **not the lifetime of IAM role credentials**.

These commands use **/latest/api/token** to fetch a token and **/latest/meta-data/** to read metadata; when writing code, do not substitute an arbitrary dated version path for the token endpoint. Using **--noproxy '*'** prevents internal requests from accidentally routing through an environment-configured HTTP proxy.

### 4.2. Behavior When the Token Is Missing

When **HttpTokens = required**, a metadata GET without a valid token receives **HTTP 401 Unauthorized**. You can check the status code in a lab environment:

~~~bash
curl -sS --noproxy '*' -o /dev/null -w '%{http_code}\n' \
  'http://169.254.169.254/latest/meta-data/instance-id'
~~~

If it returns **401**, the endpoint is rejecting tokenless GET requests. To verify IMDSv2 works, proceed to test a PUT token request and a valid GET. If it **times out** or fails to connect, do not immediately conclude the instance “enforces IMDSv2”: IMDS might be disabled, container/host networking might be blocked, a proxy may be misconfigured, or an OS issue may exist.

### 4.3. IPv6 Endpoint

IMDS can use the IPv6 address **[fd00:ec2::254]** on **Nitro-based EC2 instances in IPv6-capable subnets**, when **HttpProtocolIpv6 = enabled**. The IPv6 endpoint is not automatically enabled just because a subnet is IPv6-only; it must be explicitly configured. When the IPv6 endpoint is enabled, the IPv4 endpoint remains enabled if IMDS is enabled. The IMDSv2 token flow over IPv6 works the same way as over IPv4.

An example IPv6 GET URL looks like **http://[fd00:ec2::254]/latest/meta-data/instance-id**, also requiring the appropriate token header. Not every EC2 instance type supports enabling this endpoint.

## 5. IMDS Configuration Options

| Metadata Option | Key Values | Meaning and Recommendation |
|---|---|---|
| **HttpEndpoint** | **enabled / disabled** | Enables/disables IMDS; disabling prevents apps/agents needing metadata or role credentials from accessing them this way |
| **HttpTokens** | **optional / required** | **required** enforces IMDSv2; optional still accepts IMDSv1 requests |
| **HttpPutResponseHopLimit** | Integer **1–64** at instance level | Hop limit on **the PUT token response**; typically choose the lowest value matching topology—containers often need **2** tested |
| **HttpProtocolIpv6** | **enabled / disabled** | Enables the IMDS IPv6 endpoint when the instance type/subnet meets prerequisites |
| **InstanceMetadataTags** | **enabled / disabled** | Controls whether instance tags can be read via IMDS; enable only when workloads need it and tags hold no sensitive info |

**Critical technical point:** **HttpPutResponseHopLimit** is not the session token's TTL. The max 21,600-second session TTL is an HTTP header sent during PUT; the hop limit is the IP hop cap on the **response packet** when IMDS returns the token. A low value increases isolation, but also affects containers that introduce an extra network hop.

### 5.1. Containers on EC2

In some container setups, requests from a container's network namespace to IMDS traverse an extra hop. If the token response has hop limit **1**, the PUT response may never reach the containerized process. When apps/agents require IMDS, AWS documentation recommends evaluating **HttpPutResponseHopLimit = 2** or redesigning the architecture to pass configuration (e.g., Region) and credentials via dedicated mechanisms.

Do not raise the hop limit to a huge number just to silence timeouts. First determine **whether the container truly needs access to the host's IMDS**. With ECS, prefer **task roles** to grant per-task permissions; with EKS, consider pod-level identity mechanisms where appropriate. These approaches reduce the need for containers to share the host's instance profile.

### 5.2. IMDS Tags Are Not a Secrets Store

When **InstanceMetadataTags** is enabled, processes with IMDS access can read supported tags. Tags can be used to reference environment or configuration metadata, but never store passwords, service tokens, sensitive connection strings, or secret keys in tags. If tag access is unneeded, keep the feature disabled.

## 6. Configuration Precedence and Scope of Impact

At instance launch, AWS determines **each metadata option individually** in this order:

1. **Launch-time configuration** (including `RunInstances` parameters or an EC2 Launch Template).
2. **Account-level default in that Region** if no explicit value is provided at launch.
3. **AMI configuration** for supported options such as **ImdsSupport = v2.0**, if neither upper tier specifies a value.

For example, an AMI with **ImdsSupport = v2.0** can default **HttpTokens = required** and hop limit **2** when no higher-precedence setting overrides it. Yet if the launch config explicitly sets **HttpTokens = optional**, that value can override the AMI/account default **unless enforcement or a policy blocks it**. Account-level defaults do not automatically alter existing EC2 instances.

| Configuration Tier | Applies To | What to Check |
|---|---|---|
| **Instance / Launch Template** | Instances launched with that config | Which Launch Template version the Auto Scaling Group actually uses |
| **Regional account default** | **New** instances in the account/Region when launch does not override | Varies by Region; does not modify existing instances |
| **AMI ImdsSupport v2.0** | New instances using the AMI when no stronger override exists | AMI version, launch options, and account defaults |
| **Account/organization enforcement** | Blocks configurations violating IMDSv2 enforcement | Can cause IMDSv1 launch requests to **fail** |
| **IAM/SCP conditions** | Restricts who can launch/modify metadata options | Prevents users from downgrading settings during create/modify |

AWS also supports **HttpTokensEnforced** at appropriate scopes to enforce IMDSv2 configuration. Enforcement is evaluated **after** metadata options are resolved through the precedence order; if the resulting setting still allows IMDSv1, the launch request can be rejected. This is a stronger control than merely setting an account default, since a default can be overridden explicitly without enforcement.

**When using an Auto Scaling Group (ASG):** verify the Launch Template and version referenced by the ASG. Updating a template for future launches does not automatically reconfigure already-running instances. Plan replacements/instance refreshes in line with your application's SLOs and recovery behavior.

## 7. Configuring and Checking with AWS CLI

The following examples use **Region ap-southeast-1** and placeholder instance IDs. Replace them with values from an environment you are authorized to access. **Describe** commands are read-only; **modify** commands alter live configuration, so run them only after verifying application compatibility.

### 7.1. Inventorying Instances Using IMDSv1 or IMDSv2

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Metadata:MetadataOptions}' \
  --output json
~~~

Inspect **MetadataOptions.HttpTokens**, **HttpEndpoint**, **HttpPutResponseHopLimit**, **HttpProtocolIpv6**, **InstanceMetadataTags**, and **State** (application status of the option, if returned). Instances with **HttpTokens = optional** can still accept IMDSv1; instances with **required** accept only IMDSv2.

To check a single instance:

~~~bash
aws ec2 describe-instances \
  --region ap-southeast-1 \
  --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[0].Instances[0].MetadataOptions' \
  --output json
~~~

When inventorying across multiple accounts/Regions, iterate over every managed account/Region, because output from one Region **does not represent the entire organization**.

### 7.2. Enforcing IMDSv2 on an Existing Instance

After confirming that agents, SDKs, applications, and containers are compatible, modify the instance with **ModifyInstanceMetadataOptions**:

~~~bash
aws ec2 modify-instance-metadata-options \
  --region ap-southeast-1 \
  --instance-id i-0123456789abcdef0 \
  --http-endpoint enabled \
  --http-tokens required \
  --http-put-response-hop-limit 1
~~~

This command sets the instance to **IMDSv2-only** with a hop limit of 1. If the instance runs containers needing an extra hop to obtain IMDS tokens, evaluate **2** separately instead of forcing 1 across every workload.

After modifying, re-run **describe-instances** and confirm the option state is **applied**. Then test the actual application and SDK; a successful CLI response does not guarantee every metadata-dependent process continues functioning normally.

### 7.3. Configuration in Infrastructure as Code

Example Terraform snippet **inside an `aws_instance` resource**:

~~~hcl
metadata_options {
  http_endpoint               = "enabled"
  http_tokens                 = "required"
  http_put_response_hop_limit = 1
  instance_metadata_tags      = "disabled"
}
~~~

This snippet illustrates only the **metadata_options** block, not a complete Terraform configuration. For Auto Scaling Groups, configure the corresponding attributes inside the **Launch Template** used by the ASG. Regardless of whether Terraform, CloudFormation, or the CLI configures it, verify the final metadata options on newly launched instances.

### 7.4. Defaults and Enforcement Policies

At fleet scale, govern across three complementary layers:

- **Launch Template / IaC**: declare **HttpTokens = required** directly in deployment definitions.
- **Account-level defaults and enforcement**: default new instances to IMDSv2 and block launches permitting IMDSv1 once the organization is ready.
- **IAM/SCP/organization controls**: restrict permissions to modify metadata options or launch non-compliant configurations.

AWS provides EC2 condition keys to require IMDSv2 at launch and restrict option modifications. One commonly used condition key is **ec2:MetadataHttpTokens**. Policy design must verify which APIs support which keys, as a flawed policy can inadvertently block legitimate deployments.

## 8. Role of IAM and AWS SDKs When Accessing Metadata

### 8.1. Do Not Store Long-Term Access Keys on EC2

Suppose an EC2 order-processing service needs to read S3 and write to DynamoDB. Recommended architecture:

1. An IAM role scoped to **s3:GetObject** on the granted prefix and required DynamoDB permissions on the specific table.
2. An instance profile attaching the role to EC2.
3. Application using the SDK/CLI default credential provider chain to obtain temporary credentials at runtime.
4. **HttpTokens = required** so the instance IMDS rejects IMDSv1-style metadata requests.
5. CloudTrail and permission monitoring tools to audit API calls and trim excess privileges.

**Example with AWS SDK for Java 2.x** (demonstrating the default provider chain; project dependencies, bucket, and Region must be configured per project):

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

import java.nio.file.Paths;

public class DownloadReport {
    public static void main(String[] args) {
        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            s3.getObject(
                GetObjectRequest.builder()
                    .bucket("example-report-bucket")
                    .key("reports/current.csv")
                    .build(),
                Paths.get("/tmp/current.csv")
            );
        }
    }
}
~~~

The code contains no access keys or secret keys. The AWS SDK resolves credentials via the **default credential provider chain**; on EC2, if no higher-priority source exists, the SDK fetches credentials from the instance profile over IMDSv2. Credential environment variables or explicitly configured profiles **can take precedence over the EC2 role**, so always verify the runtime identity when troubleshooting `AccessDenied`.

**Do not assume** every legacy SDK version supports IMDSv2. Before disabling IMDSv1, upgrade SDKs/CLIs/agents to supported versions and test real credential paths—including startup code, scripts, bootstraps, cron jobs, and sidecars.

### 8.2. IMDSv2 Does Not Replace Least Privilege

If an EC2 role grants **s3:*** across every bucket or overly broad IAM admin rights, enabling IMDSv2 does not fix the over-permissioning flaw. Software authorized to run on the instance and reach IMDS can still obtain that role's credentials under permitted conditions.

The rule is: **dedicated role per workload**, tightly scoped actions/resources/conditions, short-lived credentials, no secret leakage, and restricting which processes can reach metadata.

## 9. Transitioning from IMDSv1 to Enforced IMDSv2

Do not enable **HttpTokens = required** everywhere at once before knowing which workloads still rely on IMDSv1. Legacy apps, agents, or scripts sending plain GET requests to metadata may stop retrieving Region or credential info and lose the ability to call AWS APIs.

### Step 1 — Inventory Resources and Metadata Dependencies

List EC2 instances, Auto Scaling Groups, Launch Templates, AMIs, OSes, monitoring agents, CLIs/SDKs, and running containers. Identify which processes contact **169.254.169.254** and whether they use IMDSv2 tokens.

**Deliverable:** a table of instances/accounts/Regions, current **HttpTokens** settings, owners, and affected applications.

### Step 2 — Observe CloudWatch Before Modifying

Amazon EC2 emits metrics that help evaluate IMDSv1 usage:

| CloudWatch Metric | Interpretation | Transition Use |
|---|---|---|
| **MetadataNoToken** | Number of **successful metadata accesses without a token**; shows active IMDSv1 usage while allowed | Prioritize fixing apps/agents still generating IMDSv1 calls |
| **MetadataNoTokenRejected** | Number of IMDSv1-style requests rejected after IMDSv1 is disabled | Spot incompatible workloads post-transition |
| **ImdsV1Enabled** | Whether the instance permits IMDSv1; **1** when HttpTokens is optional, **0** when required | Audit configuration posture, even when there is no traffic |

Two important caveats:

- **MetadataNoToken = 0** over a window does not prove all code has abandoned IMDSv1: infrequent jobs may not have run during that period, or metrics may not emit when zero requests occur.
- **ImdsV1Enabled** reflects configuration permitting IMDSv1, **not request volume**. To inventory instances still allowing IMDSv1, combine this metric with EC2 inventory data.

You can also use the AWS-provided **IMDS Packet Analyzer** to pinpoint processes still making IMDSv1 calls in authorized test environments; evaluate packet-capture permissions, host resources, and security policies before enabling the tool.

### Step 3 — Remediate Remaining IMDSv1 Consumers

- Upgrade outdated SDKs/CLIs/agents to versions supporting IMDSv2.
- Replace direct GET scripts with the **PUT token → token-authenticated GET** flow.
- Check bootstraps, cloud-init, user data, admin scripts, and background jobs.
- For containers, determine whether host IMDS access is required; if so, check networking and hop limit.
- Verify the credential provider chain and automatic IAM role credential refresh.

### Step 4 — Test in a Representative Environment

Pick a low-risk instance group or staging environment. Set **HttpTokens = required**, test token acquisition, exercise real application flows, restart agents/containers if needed, and watch **MetadataNoTokenRejected**.

If adjusting the hop limit is needed, pick the smallest value that works; for containers with an extra network hop, evaluate **2** per AWS guidance.

### Step 5 — Roll Out in Waves with a Recovery Plan

Plan phased rollouts per instance group/ASG with an appropriate rollback path, deployment window, and monitoring. Do not overlook the risk that an incompatible setting breaks SDK credential retrieval and triggers widespread **AccessDenied** errors.

**Recovery procedures must obey security policy:** first fix the SDK, container config, or hop limit. Temporarily re-enabling IMDSv1 is an approved, time-bound exception only where permitted; if account-level enforcement is active, downgrading may be blocked.

### Step 6 — Lock Down Configuration for Future Launches

Once metrics and testing pass, update Launch Templates, account defaults, enforcement, and IAM/SCPs. Run instance refreshes if needed to replace older instances; monitor **ImdsV1Enabled** to prevent fleets from drifting back to **optional**.

## 10. Advanced Security: IMDSv2 Is Only One Layer of Defense

### 10.1. SSRF, Remote Code Execution, and Network-Capable Applications

IMDSv2 blocks SSRF/proxy flows that cannot issue a PUT and attach the token to a GET. However, if an application suffers **remote code execution** and an attacker runs code inside the instance, IMDSv2 cannot stop that process from performing the normal token-retrieval sequence. Likewise, containers able to reach the host's IMDS still require proper privilege limits and isolation.

Always combine:

- Input validation against SSRF, restricting URLs/hosts the application can reach, and patching libraries.
- **Least-privilege IAM roles** and separating permissions across workloads.
- **Host firewalls** or host/container network policies restricting which processes can reach IMDS; check both IPv4 and IPv6 if enabled.
- Protecting credentials from logs, traces, debug output, shell history, and insecure storage.
- Monitoring CloudTrail and alerting on anomalous role usage patterns.

**Security groups and VPC NACLs** govern VPC traffic, but should not be treated as sufficient to block processes *inside EC2* from reaching the link-local IMDS address. When process-level control is needed, enforce controls at the OS/container layer and verify effectiveness.

### 10.2. When Can HttpEndpoint Be Disabled Completely?

If a workload **needs neither metadata nor credentials via IMDS**, consider setting **HttpEndpoint = disabled** to shrink the attack surface. However, doing so can break apps or AWS agents that rely on instance profiles, user data/metadata, bootstrap utilities, or Region discovery.

Never disable the endpoint merely because you didn't observe direct calls in a short test. Confirm every dependency, alternate credential mechanism, and operational procedure beforehand.

### 10.3. Enterprise Networking and Forwarding Devices

On certain Nitro-based instances running virtual routers or network appliances, packet forwarding toward IMDS addresses can introduce unintended risks. AWS recommends blocking forwarded traffic destined for IMDS addresses on forwarding devices where applicable. Check both **169.254.169.254** and **fd00:ec2::254** if the IPv6 endpoint is enabled.

## 11. Diagnosing IMDSv2 Issues by Symptom

| Symptom | Common Causes | Verification and Fix |
|---|---|---|
| Metadata GET returns **401 Unauthorized** | **HttpTokens = required** yet token is missing/expired | Fetch token via PUT, attach token header to GET, check TTL |
| PUT token times out inside container, works on host | **HttpPutResponseHopLimit** too low for network hops | Check metadata options, network namespaces; evaluate hop limit 2 or dedicated credentials |
| Both PUT and GET fail to connect | **HttpEndpoint = disabled**, firewall/proxy, or routing issue | Check `describe-instances`, host firewall, proxy settings, network prerequisites |
| HTTP test command routes through corporate proxy | `HTTP_PROXY`/`HTTPS_PROXY` or `NO_PROXY` misconfigured | Bypass proxy for IMDS addresses; check SDK/agent proxy settings |
| EC2 cannot obtain instance profile credentials | No role/profile attached, IMDS disabled, or legacy/incompatible SDK | Verify instance profile, SDK provider chain, and IMDS; never log secrets |
| App still gets **AccessDenied** despite reading metadata | Role lacks permissions or credentials come from another source | Run STS `GetCallerIdentity` and IAM policy evaluation to confirm principal/action/resource |
| AWS CLI works on host, containerized app fails | Different credential env, hop limit, proxy, or task role | Check identity/SDK inside container, task role config, and IMDS path |
| New EC2 still has **HttpTokens = optional** despite IMDSv2 AMI | Launch Template or account setting overrides with higher precedence | Check precedence order for each metadata option |
| Launch fails when configured as **optional** | Account/org enforces IMDSv2 or IAM/SCP blocks it | Inspect EC2 error message, account defaults/enforcement, and Launch Template |
| **MetadataNoTokenRejected** spikes after rollout | Some process still calls IMDSv1 | Trace agent/script, upgrade SDK, re-test |
| Cannot read IMDS over IPv6 | IPv6 endpoint not enabled or instance/subnet unsupported | Check Nitro support, IPv6 subnet, **HttpProtocolIpv6** |
| Metadata still accessible when IMDSv1 was thought disabled | Software merely uses v2 while instance remains **HttpTokens = optional** | Directly verify metadata options show **required** |

### 11.1. Distinguishing Three Frequently Conflated Failures

**Failure to obtain a token** is an IMDS reachability, HTTP configuration, or hop-limit issue. **Obtaining a token yet failing to get credentials** points to the instance profile, metadata endpoint/role path, or how the SDK uses the credential chain. **Having credentials yet failing S3/DynamoDB calls** is an IAM, resource, policy condition, or target service issue. Each has a different fix—and none should be “solved” by attaching an overly broad **AdministratorAccess** policy.

### 11.2. Confirming the Active Principal with STS

If EC2 has the AWS CLI and you need to investigate an AWS API `AccessDenied`:

~~~bash
aws sts get-caller-identity --region ap-southeast-1
~~~

This reveals the account and ARN of the identity **the AWS CLI is actually using**, which you can compare against the expected instance role. If the ARN shows another user/role, inspect environment variables, shared credentials files, container task roles, and `AssumeRole` flows before touching the instance profile. Do not dump the entire environment or print raw temporary credentials when unnecessary.

## 12. Real-World Scenarios and Exercises

### Scenario A — Web API on EC2 and SSRF Risk

A Java web API runs on EC2. The app accepts user-supplied URLs to fetch external data. EC2 has a role with permission to read S3 data. The security team worries an input URL could trick the app into hitting the metadata address.

**Question:** does merely setting **HttpTokens = required** completely eliminate the risk?

**Suggested approach:** IMDSv2 blocks simple GET-only SSRF flows but does not eliminate SSRF/RCE. Validate URLs and redirects, block link-local destinations at appropriate app/network layers, restrict IMDS access by process where feasible, minimize IAM permissions, and verify logging/monitoring. The SDK should still use the instance role cleanly rather than storing long-term access keys.

### Scenario B — Container Fails to Receive Token

A containerized app on EC2 worked when **HttpTokens = optional**. After switching to **required**, the app can no longer call S3; fetching a token from the host still works normally.

**Question:** is this necessarily an S3 bucket policy error?

**Suggested approach:** check PUT token requests from inside the container, **HttpPutResponseHopLimit**, proxies, and the credential provider chain first. The token response may be dropped due to the container's extra network hop; if the workload needs host IMDS, evaluate hop limit **2**, or prefer appropriate **task/pod identity** mechanisms. Only after confirming credentials are retrieved should you inspect IAM/S3 policies.

### Scenario C — ASG Launches Non-Compliant Instances

An organization updates its AMI to support IMDSv2, yet the Auto Scaling Group still launches some instances with **HttpTokens = optional**. Existing instances also remain unchanged after configuring the account default.

**Question:** where could the setting be overridden?

**Suggested approach:** check the active Launch Template version, the account default for that exact Region, and AMI attributes in precedence order. Account defaults do not retroactively update running instances; handle existing instances separately. When ready, consider enabling **enforcement** so launches permitting IMDSv1 are rejected, combined with monitoring **ImdsV1Enabled**.

### Scenario D — Token Works, Still Getting AccessDenied

A job retrieves the instance ID via IMDSv2, then the SDK calls **dynamodb:PutItem** and receives **AccessDeniedException**.

**Question:** does successfully reading metadata prove the role has permission to write to DynamoDB?

**Suggested approach:** no. Verify the instance profile, active principal via STS, policy granting **dynamodb:PutItem** on the table ARN, any permission boundaries/SCPs/resource policies, and the Region. IMDSv2 governs only **how metadata is fetched**; it grants no DynamoDB permissions.

## 13. Production IMDSv2 Rollout Checklist

- [ ] Identified all EC2 instances and owners across relevant accounts/Regions.
- [ ] Mapped which applications/agents/SDKs/scripts/containers require metadata or role credentials.
- [ ] Evaluated **MetadataNoToken**, **MetadataNoTokenRejected**, and **ImdsV1Enabled** over a representative period.
- [ ] Upgraded SDKs/CLIs/agents and updated IMDSv1 GET scripts to the token-based flow.
- [ ] Set **HttpTokens = required** and verified **HttpEndpoint** is configured appropriately.
- [ ] Set **HttpPutResponseHopLimit** to match actual topology; tested from inside containers if applicable.
- [ ] Reviewed **HttpProtocolIpv6** and **InstanceMetadataTags** against actual needs and security limits.
- [ ] Verified precedence across Launch Templates, account defaults, AMIs, and enforcement.
- [ ] Enforced least-privilege IAM roles, default credential provider chain, and SSRF mitigations.
- [ ] Tested PUT token, GET metadata, SDK credential retrieval, and business API calls in a test environment.
- [ ] Monitored runtime behavior and prepared a recovery plan if metadata option changes break an app.
- [ ] Verified new instances from ASGs/Launch Templates, added controls to prevent downgrades, and documented operational decisions.

## 14. Key Takeaways

**IMDS** enables processes on EC2 to read instance metadata and, when an instance profile is attached, obtain temporary IAM role credentials. **IMDSv2** requires a **PUT request to fetch a session token** used on subsequent metadata requests; **HttpTokens = required** disables IMDSv1 access. **HttpPutResponseHopLimit** controls the hop limit of token responses, which is especially important for containers. Safe deployment requires verifying **final instance settings, SDK versions, least-privilege IAM, SSRF defenses, CloudWatch monitoring, and tested rollout plans** together.

### Official AWS Reference Documentation

- [Use the Instance Metadata Service to access instance metadata](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html) — IMDSv2 PUT/GET, tokens, and TTL.
- [Configure instance metadata options](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html) — options, precedence order, and enforcement.
- [Configure instance metadata options for new instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html) — Launch Templates, AMIs, and new-instance defaults.
- [Modify instance metadata options for existing instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-existing-instances.html) — updating running instances and IPv6 support.
- [Transition to using IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-transition-to-version-2.html) — migration path and monitoring metrics.
- [Limit access to the Instance Metadata Service](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-metadata-limiting-access.html) — host firewalls and restricting IMDS access.
- [CloudWatch metrics for your EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/viewing_metrics_with_cloudwatch.html) — `MetadataNoToken` and related metrics.
- [IAM roles for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html) — instance profiles and temporary credentials.
- [AWS SDK for Java 2.x default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — runtime credential resolution.
