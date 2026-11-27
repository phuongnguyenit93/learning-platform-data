# Environment Configuration, Secrets, and Data Connectivity in Beanstalk

> **Chapter:** Managed Application Platforms  
> **Module:** CLOUD_PROVIDERS_AWS — exploring the AWS ecosystem across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; developing skills to choose services, deploy securely, monitor, recover, and control costs.

## Learning Objectives

**AWS Elastic Beanstalk** helps deploy and operate web applications on managed AWS resources under a unified environment model. Instead of manually scripting EC2 provisioning, web server configuration, health monitoring, and application updates, development teams can supply source code or containers, pick a platform, and declare environment configuration. However, to connect an application securely to databases, S3, or internal services, you still need a solid grasp of **environment properties**, **secrets**, **IAM roles**, **networking**, and **data resource lifecycles**.

After this lesson, you will be able to:

1. Explain the **application – application version – environment – platform** hierarchy and the AWS resources behind a Beanstalk environment.
2. Distinguish **environment configuration**, **environment properties**, and **secret-backed environment variables**.
3. Configure an application using the Console, EB CLI, AWS CLI, `.ebextensions`, and `.platform` in the proper precedence order.
4. Design secret retrieval from **AWS Secrets Manager** and **AWS Systems Manager Parameter Store**, apply least-privilege IAM, and handle rotation.
5. Connect a Beanstalk application to an **independent Amazon RDS** instance, secure connectivity via VPC, subnets, and security groups, and understand the risks of environment-coupled databases.
6. Separate permissions and configuration across development, staging, and production without exposing passwords in source code or logs.
7. Inspect an environment using the AWS CLI in **read-only** mode to pinpoint configuration, secret, database, health, and network issues.
8. Propose deployment, rollback, monitoring, backup, and cost-control strategies.

## 1. Architecture of an Elastic Beanstalk Environment

### 1.1. Fundamental Concepts

| Concept | Role | Example |
|---|---|---|
| **Application** | Logical container for related versions and environments | `course-platform` |
| **Application version** | Packaged build, source bundle, or deployable artifact | `v1.4.0` |
| **Environment** | Running application version with its AWS configuration and resources | `course-staging`, `course-production` |
| **Platform** | OS, runtime, web/proxy/server, and deployment mechanics | Java on Amazon Linux 2023, Node.js, Docker |
| **Environment configuration** | Option settings for instances, scaling, networking, health, and app | Instance type, subnets, health path |
| **Environment properties** | Key-value variables readable by the app runtime | `APP_ENV=staging`, `DB_HOST=db.internal` |
| **Environment secrets** | Runtime variables populated from a secret/parameter ARN in a store | `DB_PASSWORD` from Secrets Manager |
| **Service role** | IAM role allowing Beanstalk to manage and monitor resources per granted permissions | Service role |
| **EC2 instance profile** | IAM role used by the environment's EC2 instances | Permissions to fetch source, read secrets, call S3 |

A Beanstalk environment is not a single "Beanstalk virtual server." In a typical **load-balanced environment**, AWS manages components such as the load balancer, Auto Scaling group, EC2 instances, security groups, and CloudWatch according to configuration, alongside whatever resources the deployment team enables.

~~~mermaid
flowchart TD
    DEV[Developer / CI-CD] --> EB[Elastic Beanstalk Application]
    EB --> VER[Application Version]
    VER --> ENV[Environment: staging / production]
    ENV --> ALB[Load Balancer per config]
    ENV --> ASG[Auto Scaling Group]
    ASG --> A[EC2 App instance AZ A]
    ASG --> B[EC2 App instance AZ B]
    ALB --> A
    ALB --> B
    A --> DB[(External Amazon RDS)]
    B --> DB
    A --> S3[(S3)]
    B --> S3
    A --> SEC[Secrets Manager / SSM]
    B --> SEC
    IAM[IAM roles + instance profile] -. Protects .-> A
    IAM -. Protects .-> B
    NET[VPC subnets + security groups] -. Restricts network .-> DB
~~~

The diagram illustrates a **reference architecture**; not every environment provisions all of these resources. **Single-instance environments** have a different topology; Beanstalk Standard, Beanstalk Cluster, and individual runtimes/platforms also differ in supported options. This lesson focuses on **Beanstalk Standard environments on EC2**, particularly Java/Spring Boot web apps; consult the relevant documentation if using Beanstalk Cluster or another platform type.

### 1.2. What AWS Manages vs. What the App Team Still Owns

| What AWS Elastic Beanstalk Assists With | What the Application Team Still Owns |
|---|---|
| Orchestrates creation/updates of many AWS resources per environment configuration | Source code, dependencies, release quality, health endpoints |
| Supported runtime platforms and deployment workflows | Platform branch upgrades, compatibility testing, avoiding deprecated runtimes |
| Integrated health monitoring/rolling deployments as configured | Readiness, request draining, SLOs, application fault tolerance |
| EC2, Auto Scaling, ALB, and CloudWatch integration | Least-privilege IAM, security groups, VPC routes, and database permissions |
| Managing environment configurations and application versions | Secret lifecycles, rotation, backup/restore, change-control policies |
| Supporting multi-environment deployments | Account/data/permission isolation, cost control, compliance |

**A managed platform does not replace IAM, secrets management, or database backups.** Beanstalk can report a successful deployment while endpoints still fail if the DB security group blocks connections or a rotated secret has not been refreshed on running instances.

### 1.3. Web Server Environment vs. Worker Environment

- **Web server environment:** serves HTTP/HTTPS requests, typically paired with a load balancer and Auto Scaling for APIs/web apps.
- **Worker environment:** suited for background job processing via a queue and daemon/worker mechanism per Beanstalk capabilities; the application must handle retries, idempotency, and errors.
- Both have **environment configurations**, yet do not share the same default listeners, health checks, request lifecycles, or queue-processing mechanics.

**Example:** a Java API handling logins and course requests belongs in a web environment, whereas sending emails or generating reports can run through a queue/worker. Never rely on local temp files on a web instance as durable storage when Auto Scaling replaces instances.

## 2. Environment Configuration: Three Setting Groups to Distinguish

### 2.1. Environment Configuration

Option settings control infrastructure and runtime characteristics:

| Group | Common Settings | Impact |
|---|---|---|
| Compute/Auto Scaling | Instance type, min/max instances, purchase options | Capacity, scalability, and cost |
| Network | VPC, subnet IDs, public/private placement, security groups | Reachability to app and data stores |
| Load balancer/health | Load balancer type, listeners, health path, health reporting | Routing and failure detection |
| Deployment | Rolling, immutable, traffic splitting, or supported policies | Disruption level and rollback |
| Runtime | Java platform, JVM flags, environment properties | How the app starts and consumes resources |
| Observability | Log streaming, retention, enhanced health | Incident diagnostics and cost |

Some settings apply lightweight changes, while others can **replace EC2 instances**, trigger rolling updates, or affect capacity. Never treat `update-environment` as an instantaneous zero-disruption operation.

### 2.2. Environment Properties

**Environment properties** are key-value pairs exposed by Beanstalk for the application to read at runtime, usually via environment variables.

Example for **non-sensitive** values:

~~~text
APP_ENV=staging
LOG_LEVEL=INFO
DB_HOST=course-db.cluster-xxxx.ap-southeast-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=course
S3_BUCKET=course-content-staging
AWS_REGION=ap-southeast-1
~~~

**Do not place** `DB_PASSWORD`, API tokens, private keys, or connection strings containing passwords directly in plaintext environment settings, repositories, EB CLI history, or source bundles. While environment properties provide flexible configuration, values can surface in management consoles, process environments, diagnostic outputs, or logs if handled carelessly.

### 2.3. Secret-Backed Environment Properties

Beanstalk supports retrieving values from **AWS Secrets Manager** and **SSM Parameter Store** depending on the current platform version. In Beanstalk Standard, two namespaces are key:

~~~text
aws:elasticbeanstalk:application:environment
    -> environment variables whose Value is plain configuration text.

aws:elasticbeanstalk:application:environmentsecrets
    -> environment variables whose Value is a secret/parameter ARN;
       Beanstalk fetches the actual value when bootstrapping instances.
~~~

Platform versions released from **March 26, 2025** onward support referencing secrets into environment variables per AWS documentation. **Do not assume an older platform version has the same capability**; verify the branch/version used by your environment.

Certain platform versions released from **January 13, 2026** onward also support extracting a **top-level JSON key** from a Secrets Manager ARN, provided the platform meets the supported version and documented constraints.

## 3. Configuration Methods and Precedence Order

### 3.1. Console, EB CLI, AWS CLI, Configuration Files

| Method | Used For | Characteristics |
|---|---|---|
| **Elastic Beanstalk Console** | Viewing/editing environment, runtime variables, monitoring, and update policies | Friendly for exploration; prone to out-of-band drift outside Git without governance |
| **EB CLI** | Creating/selecting environments, deploying, checking status, `setenv`, `config` | Convenient for development and small teams |
| **AWS CLI / API** | Automating creation/updates of option settings, checking status | Suits IaC/CD with approvals; easy to audit |
| **`.ebextensions/*.config`** | Customizing **Beanstalk Standard** alongside the source bundle | Declarative YAML/JSON tied to the application version |
| **Saved configurations** | Saving reusable environment configuration templates | Follows precedence rules relative to `.ebextensions` |
| **`.platform/hooks`** | Pre/post-deployment scripts on supported Linux platforms | Executes during deployments; requires permission and error control |
| **IaC (CloudFormation/CDK/Terraform...)** | Managing infrastructure and differences across environments | Supports review, drift detection, and controlled repeatability |

**Version note:** AWS currently distinguishes **Beanstalk Standard** and **Beanstalk Cluster**. The `.ebextensions` mechanics in this guide apply to Standard; Cluster differs in configuration surfaces and container image workflows. Do not copy these YAML examples verbatim to Cluster.

### 3.2. Precedence Order in a Standard Environment

For the same option:

~~~text
Highest
  1. Settings applied directly to the environment via API/Console/EB CLI
  2. Saved configuration
  3. .ebextensions configuration files
  4. Default values
Lowest
~~~

For example, suppose the source bundle includes:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    APP_ENV: development
~~~

but the environment was updated directly via `eb setenv APP_ENV=production`. The direct setting has **higher** precedence, so deploying a source bundle that still specifies `APP_ENV: development` will not revert production back to development.

**Operational consequence:** configuration in Git does not always reflect the full **effective configuration**. If an `.ebextensions` edit "has no effect," inspect environment-level overrides and saved configs. Removing an override requires `options-to-remove` or the AWS-supported removal mechanism—not just deleting the line from your source file.

### 3.3. Reference Source Bundle Layout

~~~text
course-api/
├── .ebextensions/
│   ├── 00-app-env.config
│   └── 01-secrets.config
├── .platform/
│   ├── hooks/
│   │   └── predeploy/
│   │       └── 10-verify-config.sh
│   └── confighooks/
│       └── postdeploy/
│           └── 20-check-health.sh
├── src/
│   └── ...
├── Procfile
└── build artifact / source code
~~~

This is an **illustrative layout**. Not every runtime requires a `Procfile`; artifact placement, build steps, and launch commands depend on the platform. `.platform` directories depend on platform and hook support; **never run hooks as root** or modify system files without understanding the lifecycle.

### 3.4. `.ebextensions` Example for Non-Sensitive Variables

Hypothetical file `.ebextensions/00-app-env.config`:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    APP_ENV: "staging"
    LOG_LEVEL: "INFO"
    DB_HOST: "course-db.xxxxxx.ap-southeast-1.rds.amazonaws.com"
    DB_PORT: "5432"
    DB_NAME: "course"
    S3_BUCKET: "course-content-staging"
~~~

This is an **educational example**, not a file created in a repository. The RDS endpoint and bucket name are placeholders. Never hard-code production settings into a file shared across every environment; keep sensible defaults in Git and override environment differences via reviewed IaC/environment configuration.

### 3.5. When Do Platform Hooks Run?

On supported Linux platforms:

- `.platform/hooks/prebuild`: before application setup/build;
- `.platform/hooks/predeploy`: after preparation, before deploying the app to the runtime;
- `.platform/hooks/postdeploy`: after deployment;
- `.platform/confighooks/...`: runs during **configuration deployments** when only settings change.

Example script that **never prints secrets**:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

: "${DB_HOST:?DB_HOST is required}"
: "${DB_PORT:?DB_PORT is required}"
: "${DB_NAME:?DB_NAME is required}"

echo "Required database configuration keys are present."
~~~

**Warning:** Platform hooks can execute with elevated privileges, especially on Linux. Never enable `set -x` in a hook that has access to credentials; never echo environment variables, pass secrets via command-line arguments, or write them to stdout. A failing hook can fail the entire deployment—test hooks in a sandbox first.

## 4. Environment Properties in Java/Spring Boot Applications

### 4.1. Reading Environment Variables Without Tying to a Specific Machine

Java apps can use `System.getenv("APP_ENV")` or Spring Boot's externalized configuration. Example `application.properties`:

~~~properties
spring.application.name=course-api
server.port=5000

app.environment=${APP_ENV:development}
logging.level.root=${LOG_LEVEL:INFO}

spring.datasource.url=jdbc:postgresql://${DB_HOST}:${DB_PORT:5432}/${DB_NAME}
spring.datasource.username=${DB_USER}
spring.datasource.password=${DB_PASSWORD}
~~~

`DB_USER` and `DB_PASSWORD` are resolved only at runtime; **never put actual password values in the repository**. `server.port=5000` is an example, not a fixed port across all Beanstalk Java platforms. Reverse proxies, `PORT`, and launch mechanisms vary—verify the application port and health check.

### 4.2. Distinguishing Public Keys from Keys That Must Be Protected

| Key | Example | Recommended Management |
|---|---|---|
| `APP_ENV` | `staging` | Plain environment property/IaC |
| `DB_HOST` | Internal RDS endpoint | Plain environment property if policy permits |
| `DB_PORT` | `5432` | Plain environment property |
| `DB_NAME` | `course` | Plain property or secret depending on sensitivity |
| `DB_USER` | Database username | Can be stored in Secrets Manager alongside the password |
| `DB_PASSWORD` | Password | Secret-backed property or runtime API |
| `PAYMENT_API_TOKEN` | Partner token | Secrets Manager with rotation/revocation |
| `S3_BUCKET` | Data bucket | Plain environment property; IAM role enforces access |
| `AWS_ACCESS_KEY_ID` | Static key | **Avoid placing** in environment; prefer instance role/STS |

**Never treat environment variables as an absolute secret vault.** They can be read by processes, debugging libraries, heap dumps, or crash reporters. Restrict OS/IAM permissions, disable debug mode in production, and never dump full configuration.

### 4.3. Validating Configuration at Startup

The application should **fail fast** if a critical variable is missing, without printing secret values in the error:

~~~java
public final class DatabaseSettings {
    public static String require(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing required config: " + key);
        }
        return value;
    }

    private DatabaseSettings() {}
}
~~~

Log only the missing **key name**—never log all of `System.getenv()` or a JDBC URL with embedded credentials. Keep health endpoints returning only status, without leaking DB hostnames, secret names, or stack traces.

## 5. Secrets Manager and SSM Parameter Store

### 5.1. Two Approaches to Consuming Secrets

**Approach A — Native environment secrets (Beanstalk bootstrap):**

1. Create a secret in AWS Secrets Manager or a parameter in SSM Parameter Store.
2. Grant the **EC2 instance profile role** IAM permission to read that specific ARN.
3. Configure `aws:elasticbeanstalk:application:environmentsecrets` with the variable name and ARN.
4. When an instance bootstraps, Beanstalk fetches the secret/parameter value and injects it into the runtime environment.
5. The application reads it like a standard environment variable.

**Approach B — Application calls the Secrets Manager/SSM API directly:**

1. Grant the instance role least-privilege permission to retrieve the secret.
2. The application uses the AWS SDK with the default credential chain—no embedded access keys.
3. Implement caching, TTL/refresh, retries, timeouts, and rotation handling.
4. Never log secret values; monitor API errors, quotas, and costs.

| Criterion | Native Environment Secrets | Direct SDK Calls |
|---|---|---|
| Application code | Usually just reads env vars | Requires SDK integration and API handling |
| Secret retrieval | At bootstrap and environment refresh operations | When the application calls the API |
| Rotation | **Does not auto-update** env vars on running instances | Can proactively refresh/cache by design |
| IAM | EC2 instance profile must be allowed to read the secret | Runtime IAM role must be allowed to read |
| Complexity | Less app code, requires managing env refreshes | More code, flexible update control |
| Failure modes | Bootstrap can fail on bad ARN/permissions | Runtime can fail if Secrets Manager/SSM is unreachable |
| Cost | Secret store/API requests and environment resources | Secret store/API requests, cache/call frequency |

**Do not pick native env vars if your business requires instant secret updates without a refresh workflow.** Conversely, for DB connections with planned rotation, native environment secrets can be simple once sync latency is controlled.

### 5.2. `environmentsecrets` Namespace Example

Hypothetical file `.ebextensions/01-secrets.config`:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environmentsecrets:
    DB_USER: "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12:username"
    DB_PASSWORD: "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12:password"
    PARTNER_API_TOKEN: "arn:aws:ssm:ap-southeast-1:111122223333:parameter/aws-lab/partner-token"
~~~

**Careful explanation:**

- `DB_USER` and `DB_PASSWORD` in this example use **top-level JSON key extraction** from Secrets Manager, available only on **platform versions released on or after January 13, 2026** that support this feature. The JSON secret is assumed to contain `username` and `password` keys.
- `PARTNER_API_TOKEN` references an SSM parameter ARN and receives the parameter value as a variable. **JSON-key extraction is not supported with SSM Parameter Store**.
- Real Secrets Manager ARNs include a **service-generated random suffix**; the example string is not a live ARN.
- If your platform does not yet support JSON-key extraction, use single-value secrets or have the application fetch and safely parse the JSON via the AWS SDK.
- Older platforms released before environment secrets support may reject this namespace.
- **Store only the ARN/reference**, never the actual secret value inside `.config` files.

The AWS Console also lets you choose **Source = Secrets Manager or SSM Parameter Store** for runtime variables and enter the ARN. When configuring via CLI/API, use the exact same namespace shown above.

### 5.3. Least-Privilege IAM Model for Beanstalk to Read Secrets

Example IAM identity policy attached to the environment's **EC2 instance profile role**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOneDatabaseSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12"
    },
    {
      "Sid": "ReadOneSSMParameter",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:111122223333:parameter/aws-lab/partner-token"
    }
  ]
}
~~~

This is an **illustrative policy**; do not attach it to an IAM role outside your authority. If the secret or parameter uses a **customer-managed KMS key**, you may also need `kms:Decrypt` permission and an allowing **KMS key policy**. Some setups further restrict VPC endpoints, principals, encryption contexts, or service conditions—test all conditions.

**Distinguishing Service Role from Instance Profile:** when Beanstalk populates environment variables from Secrets Manager/SSM in a Standard environment, the **EC2 instance profile role** requires permission to fetch the secret/parameter per AWS documentation. Granting those permissions only to the Beanstalk service management role that EC2 does not assume will not fix bootstrap failures.

### 5.4. Secret Rotation: Values Do Not Sync Automatically

This is the single most important operational point.

~~~mermaid
sequenceDiagram
    participant SM as Secrets Manager
    participant EB1 as Beanstalk EC2 instance A
    participant EB2 as Beanstalk EC2 instance B
    participant OPS as Operator / Automation
    SM-->>EB1: Initial bootstrap: password v1
    SM-->>EB2: Initial bootstrap: password v1
    OPS->>SM: Rotate secret to password v2
    Note over EB1,EB2: Running instances can still hold v1
    OPS->>EB1: Refresh environment / restart app server
    EB1->>SM: Fetch v2 via Beanstalk mechanism
    OPS->>EB2: Refresh environment / restart app server
    EB2->>SM: Fetch v2
    Note over EB1,EB2: Both instances now use v2 after successful refresh
~~~

Per AWS documentation, Beanstalk **does not automatically pick up new values** in environment variables when Secrets Manager/Parameter Store entries are updated or rotated. You must trigger a refresh, such as an **UpdateEnvironment** or **RestartAppServer** operation per current guidance.

**Notable risk:** if Auto Scaling launches a new instance after rotation, the new instance may pull **v2** while older instances still hold **v1**. During transition, the same environment holds **two credential values**. For DB password rotation, use a strategy allowing dual active credentials during the transition window or coordinate rotation and refreshes cleanly before revoking the old credential once all instances have switched.

Recommended rotation workflow:

1. Verify secret read permissions, health, and rollback plan.
2. Set up dual-user/alternating-user rotation or a service-supported rotation model to avoid disruption.
3. Rotate/update the secret via an approved workflow.
4. Proactively refresh Beanstalk instances and watch for version skew or connection errors.
5. Verify application health, DB authentication, connection pools, and background jobs.
6. Revoke the old credential/access after the safety window.
7. Log an audit event and update the runbook.

**Never print old and new values to compare them**, even in CI logs. Compare secret version metadata or purpose-built safe telemetry instead.

### 5.5. Never Leak Secrets Through Logs, CLI, or Diagnostics

- Never pass plaintext passwords in `eb setenv DB_PASSWORD=...`, because shell history and diagnostic outputs risk exposing them.
- Avoid running `eb printenv` or dumping full `describe-configuration-settings` output in CI or chat; they can expose environment properties, ARNs, and sensitive metadata.
- Never run `aws secretsmanager get-secret-value` as a verification step and paste the output into issues, chat, or logs. When checking only whether a secret exists, inspect **metadata**, not `SecretString`.
- Never place secrets in `.ebextensions`, `.platform` scripts, `Procfile`, Dockerfiles, container images, Git tags, or unencrypted backups.
- Enforce least-privilege IAM, KMS, log retention, access auditing, and an incident response procedure for leaked credentials.

## 6. Connecting to Amazon RDS: Integrated vs. External Database

### 6.1. Two Models to Distinguish

Beanstalk supports pairing with RDS in two common ways:

| Criterion | RDS Coupled to Beanstalk Environment | Independent / External RDS |
|---|---|---|
| Goal | Labs, simpler connectivity experiments | Preferred for production due to separate lifecycle |
| Resource creation | Beanstalk can create/manage RDS under coupled config | RDS created and managed independently of the environment |
| Environment properties | Can inject `RDS_HOSTNAME`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_USERNAME`, `RDS_PASSWORD` | **You configure** DB endpoint, port, name, and credentials |
| Lifecycle | Depends on environment/coupled DB configuration and deletion policy | Not deleted just because a Beanstalk environment is terminated |
| Sharing across blue/green | Less flexible when tightly coupled | Can serve multiple environments per policy and compatibility |
| Risk | Terminating the environment can affect the DB if policies are overlooked | Requires managing backups, networking, credentials, and connections separately |
| Recommendation | Labs/dev or controlled short-lived needs | Production with independent backups/DR and ownership |

**Do not assume "Elastic Beanstalk backs up every DB automatically."** RDS maintains its own snapshot, backup, and retention policies. When using a coupled DB, check the **database deletion policy**, retain/snapshot/delete options, and decoupling steps. Never terminate a production environment without confirming whether the database will be affected.

### 6.2. Coupled RDS: `RDS_*` Variables Provided by Beanstalk

In an environment-coupled RDS configuration, Beanstalk can populate:

~~~text
RDS_HOSTNAME
RDS_PORT
RDS_DB_NAME
RDS_USERNAME
RDS_PASSWORD
~~~

These variables serve the **integrated database model**; with an **external** RDS, do not expect Beanstalk to generate them automatically.

An application can migrate from coupled to external by **standardizing app variable names**—such as `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD`—then updating environment configuration and secret references. Decoupling the database itself requires a dedicated procedure, not just editing environment properties.

### 6.3. External RDS: Recommended Architecture for Multi-Environment Production

~~~mermaid
flowchart TD
    U[Users] --> LB[Beanstalk ALB]
    subgraph VPC["Customer VPC"]
      subgraph A["Private app subnet - AZ A"]
        EC2A[Beanstalk app instance A]
      end
      subgraph B["Private app subnet - AZ B"]
        EC2B[Beanstalk app instance B]
      end
      subgraph DBN["Private DB subnets"]
        RDS[(RDS / Aurora Multi-AZ as needed)]
      end
    end
    LB --> EC2A
    LB --> EC2B
    EC2A -->|TLS + TCP 5432| RDS
    EC2B -->|TLS + TCP 5432| RDS
    SM[Secrets Manager] -->|Env secrets bootstrap / SDK| EC2A
    SM -->|Env secrets bootstrap / SDK| EC2B
    ROLE[Instance profile IAM] -. Secret access .-> SM
    SG[DB SG: inbound from app SG] -. Network boundary .-> RDS
~~~

**Rule:** place the database in appropriate DB subnets, typically **not publicly accessible**, accepting traffic only from the app's security group on the exact DB port. The ALB has a different security group from the app instances; do not allow inbound DB traffic from the ALB SG when it is the app instances that open DB connections.

### 6.4. Checking Routing and Security Groups

Assuming PostgreSQL:

~~~text
ALB SG:
  Inbound 443 from permitted clients
  Outbound to app on application port

App SG:
  Inbound from ALB SG on backend port
  Outbound TCP 5432 to RDS SG
  Egress to required AWS APIs via VPC routes/endpoints

RDS SG:
  Inbound TCP 5432 from App SG
  Never open 0.0.0.0/0 for PostgreSQL
~~~

NACL and route table effects must also be checked in locked-down networks. App and DB usually share a VPC, or communicate over managed peering/Transit Gateway/VPN with permitted DNS, routing, and SGs. Private subnets calling Secrets Manager, S3, ECR, or CloudWatch may require **VPC endpoints or NAT** depending on the service; do not assume Beanstalk automatically provisions all egress paths.

### 6.5. Database Connectivity Must Account for TLS, Pooling, and Timeouts

A Java application typically uses a connection pool (such as HikariCP). Verify:

- **DB endpoint** and DNS in the right Region/VPC.
- **TCP port** permitted by SG/NACL.
- **TLS** and server certificate verification per RDS/driver standards with the right CA bundle.
- Pool sizing calculated against max EC2 instances; avoid `(instance count × pool size)` exceeding the DB's `max_connections`.
- Clear connection timeouts, retry/backoff, failover handling, and transaction boundaries.
- Password rotation coordinated with connection pool lifecycles so all instances do not lose auth simultaneously.
- Schema migrations compatible with blue/green deployments.

**Sizing example:** an environment has 6 EC2 instances, each allowing a pool of up to 20 connections; the app tier alone can open **120 connections** before counting background jobs or DB tooling. Never take laptop pool sizes as production defaults.

### 6.6. Data Connections Beyond RDS

| Service | Used For | Secure Connection Pattern |
|---|---|---|
| **S3** | Files, images, backups, reports | AWS SDK + instance role, bucket policy, VPC endpoint if appropriate |
| **DynamoDB** | Key-value/document NoSQL | SDK + least-privilege IAM, endpoint if appropriate |
| **ElastiCache/Redis** | Cache/sessions/queues per design | Private VPC, SG, TLS/auth if supported |
| **SQS** | Asynchronous tasks, worker jobs | SDK + instance role; retries, DLQ, idempotency |
| **Secrets Manager/SSM** | Secrets and configuration | IAM/KMS + API or native environment secrets |
| **RDS/Aurora** | Relational data | VPC SG, private endpoint, TLS, backups |
| **CloudWatch Logs** | Logs/telemetry | IAM, VPC connectivity, retention and cost |

**Beanstalk does not merge data services into a single lifecycle** merely because they are referenced in environment variables. Data ownership and backup strategies must be decided independently.

## 7. Designing Dev, Staging, Production, and Blue/Green

### 7.1. What Must Be Separated

| Component | Development | Staging | Production |
|---|---|---|---|
| Application version | Work in progress | Release candidate | Approved release |
| Beanstalk environment | `course-dev` | `course-staging` | `course-prod` |
| Database | Synthetic, small dataset | Representative test dataset | Real data, backups/retention |
| Secret ARN | `aws-lab/dev/...` | `aws-lab/staging/...` | `aws-lab/prod/...` |
| IAM role | Dev resources only | Staging only | Production only |
| Network | Sandbox VPC/subnets | Production-like | Tight network, multi-AZ |
| Logging | Enough to debug; no secrets | Test observation | Alerting/audit, compliant retention |
| Capacity | Minimal, scheduled shutdown | Enough for load testing | Sized for SLO/peak |
| Change approval | Lightweight | Team review | Formal approval and rollback |

**Never share a master DB password** across environments. If staging can reach the production DB, a code bug or smoke test can corrupt live data. Stronger account, VPC, and IAM separation sharply reduces blast radius.

### 7.2. Blue/Green and Data

Beanstalk supports **swapping environment URLs** or traffic-switching workflows depending on configuration. A blue/green model runs two independent environments:

~~~mermaid
flowchart LR
    DNS[DNS / Client] --> BLUE[Blue env - current]
    DNS -. After cutover .-> GREEN[Green env - candidate]
    BLUE --> DB[(External RDS)]
    GREEN --> DB
    SM[Secrets Manager] --> BLUE
    SM --> GREEN
~~~

Key points:

1. Blue/green must use **validated secrets and permissions** for both environments.
2. Two app versions sharing a database require **backward-compatible** schema changes (expand-and-contract).
3. Green must have SG/network access to the DB and AWS APIs, not merely a healthy ALB.
4. Rolling back the app does not revert schema or data mutations.
5. Traffic cutover via DNS/URL mapping is affected by cache TTLs, sessions, and connection draining.
6. The older environment continues **accruing charges** until cleaned up per procedure.

### 7.3. Safely Deploying Environment Property Changes

A change like `LOG_LEVEL=DEBUG` has a very different impact from changing VPC, subnets, or instance types. Per AWS documentation, certain option changes can trigger an environment update or reprovision instances.

Workflow:

~~~text
1. Read the effective configuration of the target environment.
2. Identify which options change and whether secrets/DB/network are affected.
3. Review the change plan, cost impact, and rollback path.
4. Apply in staging and run smoke/integration tests.
5. Observe health, 5xx rates, latency, logs, and DB connectivity.
6. Roll out to production via rolling/immutable/blue-green as appropriate.
7. Re-verify config/secret refresh across all instances.
8. Keep a rollback window, then retire old versions/environments per policy.
~~~

## 8. Health, Logging, Monitoring, and Recovery

### 8.1. Layered Health

Beanstalk reports environment health and integrates ALB health checks, yet an environment status of **Green/Ok** does not prove business APIs behave correctly.

| Signal | What It Shows | What It Does Not Prove |
|---|---|---|
| **Environment Status=Ready** | Config/deployment reached a managed steady state | App DB queries or secret refreshes succeeded |
| **Enhanced health Green/Ok** | Monitored system health indicators look good | Absence of subtle business-logic bugs |
| **ALB target healthy** | Health endpoint responds as expected | All routes or database operations work |
| **EC2 running** | Instance exists and is booted | Java process can read the DB secret |
| **`/health` 200** | App-defined endpoint criteria pass | RTO/RPO or data correctness are met |

To keep health endpoints meaningful, distinguish **liveness** (process alive) from **readiness** (able to serve traffic), avoiding heavy probes that overload the DB. If readiness always runs an expensive DB query, a slow DB can trigger a cascading outage.

### 8.2. Logging and CloudWatch

Enable as needed:

- Environment logs and platform logs, with log streaming to CloudWatch Logs where supported.
- Structured Java logs free of PII and credentials.
- ALB metrics: HTTP 4xx/5xx, latency, healthy hosts, request counts.
- EC2 metrics: CPU, memory via agent when needed, EBS/network, Auto Scaling changes.
- DB metrics: CPU, connection count, latency, storage, failover events.
- CloudTrail for config changes, IAM/Secrets Manager permissions, and administrative actions as applicable.

**Prevent sensitive data from entering logs:** full HTTP `Authorization` headers, DB connection URLs containing credentials, `System.getenv()`, and secret values must be redacted or never logged. Ingestion, retention, and log query costs can spike if `DEBUG` is left on long-term.

### 8.3. Backup and Recovery

- RDS backups, snapshots, and PITR/Multi-AZ matching RPO/RTO requirements.
- S3 versioning/lifecycle if application files are critical.
- Source code, application versions, and configs/IaC stored in controlled repositories/artifact stores.
- Secrets Manager rotation/version history and emergency recovery/access procedures.
- Practice standing up a new environment from approved configuration against an **external database** when DR requires it.

**Never treat a Beanstalk application version or environment snapshot as a DB data backup.** App lifecycles and data lifecycles must stay decoupled when independent recovery is required.

## 9. Costs and Lingering Resource Risks

### 9.1. How Does Beanstalk Bill?

AWS Elastic Beanstalk orchestrates resources, while charges come mainly from the **underlying AWS resources consumed**, such as:

| Component | Cost Source | How to Control |
|---|---|---|
| EC2 instances | Running hours, instance type, OS/license, public IPv4 | Right-sizing, Auto Scaling, lab cleanup schedule |
| Load balancer | ALB/NLB hours and traffic/LCU/NLCU per service | Tear down unneeded test environments |
| EBS | Capacity, IOPS, snapshots | Audit leftover root/data volumes |
| RDS/Aurora | Instance/compute, storage, backups, I/O | External DB with explicit lifecycle and backup/retention |
| Networking | NAT Gateway, data transfer, endpoints | Choose subnets/routes carefully and measure egress |
| Secrets Manager/SSM/KMS | Secrets, parameters, API requests, keys/requests per pricing | Cache sensibly; avoid tight polling loops |
| Logs/monitoring | CloudWatch ingestion, retention, custom metrics | Tune log levels and retention |
| DNS/certificates | Route 53 and related components | Manage domain records and certificates |

Terminating an environment does **not** guarantee every external resource created for the app was removed. An **external RDS** is designed to **survive independently** and keep billing—a major safeguard for data durability, but one requiring budget ownership.

### 9.2. Tagging and Budgets

Example tags:

~~~text
Project=course-platform
Environment=staging
Owner=team-cloud
ManagedBy=iac
CostCenter=training
DeleteAfter=2026-12-01
~~~

Use AWS Cost Explorer/Budgets and organizational tagging/governance policies. **A budget alert does not automatically stop charges**, and a `DeleteAfter` tag does not trigger auto-deletion unless your organization builds automation for it.

## 10. Lab 1 — Reading Beanstalk Configuration with the AWS CLI

> **Objective:** verify an existing sandbox Beanstalk environment and read metadata, platform info, health, and **non-sensitive** option settings without altering configuration. You do not need to create a new environment or RDS to complete the core lab. Some admin commands can return environment variables containing secrets; **never print full configuration or upload raw outputs** without inspecting them first.

### 10.1. Verify Identity and Region

Bash / AWS CloudShell example:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
aws elasticbeanstalk describe-applications \
  --region ap-southeast-1 \
  --query 'Applications[].{Name:ApplicationName,Created:DateCreated}' \
  --output table
~~~

If CloudShell already provides logged-in credentials and no `aws-lab-dev` profile exists, omit `export AWS_PROFILE=...` and `--profile`. Use only authorized accounts.

### 10.2. View Environments and Platform

~~~bash
APP=course-api
REGION=ap-southeast-1

aws elasticbeanstalk describe-environments \
  --application-name "$APP" \
  --region "$REGION" \
  --query 'Environments[].{Name:EnvironmentName,ID:EnvironmentId,Status:Status,Health:Health,Version:VersionLabel,Platform:PlatformArn}' \
  --output table
~~~

If the application does not exist yet, the output may be empty; do not create resources in production. Check `PlatformArn`/`SolutionStackName` for the active platform and verify environment secrets support, runtime, and platform updates.

### 10.3. Read Safe Option Settings Selectively

Avoid dumping all `describe-configuration-settings` output since it may include environment properties. Query only the autoscaling namespace:

~~~bash
ENV=course-staging

aws elasticbeanstalk describe-configuration-settings \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --region "$REGION" \
  --query "ConfigurationSettings[].OptionSettings[?Namespace=='aws:autoscaling:asg'].{Option:OptionName,Value:Value}" \
  --output table
~~~

**Do not** run `--output json` across all `OptionSettings` and paste it into chat or pipeline logs. If auditing environment secrets, list only option names and **never print `Value`**:

~~~bash
aws elasticbeanstalk describe-configuration-settings \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --region "$REGION" \
  --query "ConfigurationSettings[].OptionSettings[?Namespace=='aws:elasticbeanstalk:application:environmentsecrets'].OptionName" \
  --output text
~~~

Even **variable names** can reveal system details; share only within authorized teams.

### 10.4. View Health and Recent Events

~~~bash
aws elasticbeanstalk describe-environments \
  --application-name "$APP" \
  --environment-names "$ENV" \
  --region "$REGION" \
  --query 'Environments[].{Status:Status,Health:Health,HealthStatus:HealthStatus,URL:CNAME}' \
  --output table

aws elasticbeanstalk describe-events \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --region "$REGION" \
  --max-records 10 \
  --query 'Events[].{Time:EventDate,Level:Severity,Message:Message}' \
  --output table
~~~

**Warning:** Event messages can occasionally contain application configuration details. Never publish raw output containing internal addresses, user identifiers, or sensitive values. When enhanced health is off, some fields may be empty.

### 10.5. View Secret Metadata Without Reading the Secret Value

If authorized and using a sandbox ARN:

~~~bash
SECRET_ARN="arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12"

aws secretsmanager describe-secret \
  --secret-id "$SECRET_ARN" \
  --region "$REGION" \
  --query '{Name:Name,ARN:ARN,RotationEnabled:RotationEnabled,LastChangedDate:LastChangedDate}' \
  --output json
~~~

This command **does not fetch `SecretString`**. If the caller lacks `secretsmanager:DescribeSecret`, `AccessDenied` may be expected least-privilege behavior. Do not request `GetSecretValue` just to complete a metadata check.

### 10.6. Inspect RDS and Associated Security Groups

If granted RDS read permissions:

~~~bash
DB_ID=course-db-staging

aws rds describe-db-instances \
  --db-instance-identifier "$DB_ID" \
  --region "$REGION" \
  --query 'DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Status:DBInstanceStatus,MultiAZ:MultiAZ,PubliclyAccessible:PubliclyAccessible,Port:Endpoint.Port,VpcSGs:VpcSecurityGroups[].VpcSecurityGroupId}' \
  --output json
~~~

Check `PubliclyAccessible`, VPC security groups, port, and high availability. Output alone does not confirm the SG allows the App SG; inspect inbound rules if authorized. **Never open the DB port to `0.0.0.0/0` to fix a timeout.**

## 11. Lab 2 — Controlled Configuration Change Example (Optional)

> Execute only if you have your own **Beanstalk Standard sandbox environment**, approved change permissions, and a rollback plan. `update-environment` can trigger restarts or rolling replacements and may incur charges. All IDs and ARNs below are examples, not live resources.

### 11.1. Updating Non-Sensitive Variables with the EB CLI

Inside an EB CLI-configured application directory with the sandbox environment selected:

~~~bash
# STATE-CHANGING EXAMPLE - DO NOT RUN IN PRODUCTION
eb setenv APP_ENV=staging LOG_LEVEL=INFO
~~~

**Never use `eb setenv DB_PASSWORD=...`** for secret management. Command parameters and environment variables may be logged or saved in shell history.

Check environment health, application logs, and run an API smoke test after updating. If configuration is managed by IaC, apply changes through the approved pipeline instead of direct edits that cause drift.

### 11.2. Updating a Secret ARN via the AWS CLI

Illustrative `secret-options.json` (ARN/reference only, no secret value):

~~~json
[
  {
    "Namespace": "aws:elasticbeanstalk:application:environmentsecrets",
    "OptionName": "DB_PASSWORD",
    "Value": "arn:aws:secretsmanager:ap-southeast-1:111122223333:secret:aws-lab/course-db-AbCd12:password"
  }
]
~~~

Only after verifying platform support for top-level JSON extraction (if using `:password`), IAM roles, KMS policies, and secret metadata should you consider:

~~~bash
# STATE-CHANGING EXAMPLE - ONLY WHEN APPROVED
aws elasticbeanstalk update-environment \
  --application-name "$APP" \
  --environment-name "$ENV" \
  --option-settings file://secret-options.json \
  --region "$REGION"
~~~

This operation **does not create the secret**; the secret must already exist and be readable. Be mindful of how AWS handles in-progress environment updates, configuration precedence, and instance lifecycles. Avoid changing multiple sensitive options at once if it obscures failure root causes.

### 11.3. Post-Change Verification and Rollback

1. Inspect environment status and events without printing secret values.
2. Check application health, DB connectivity (via a safe app endpoint), ALB 5xx metrics, and redacted logs.
3. If the update fails on IAM/ARN/KMS, inspect the **EC2 instance profile** first.
4. If the change breaks the app, revert to the previous configuration/ARN per plan; rollback may also trigger restarts/updates.
5. Ensure old and new instances are synced on secrets if rotation just occurred.
6. Clean up only within lab scope; **never terminate an external RDS** holding data you need to keep.

There is no "quick cleanup command to delete the secret/DB" in this lab because that risks data loss or breaking shared resources. Resource destruction must follow ownership and organizationally approved policies.

## 12. Layered Troubleshooting

| Symptom | Possible Cause | Safe Check |
|---|---|---|
| Changed `.ebextensions`, but variable did not change | Option overridden by environment-level or saved config | Compare precedence and effective settings (without printing secrets) |
| `.ebextensions/*.config` has no effect | Wrong location, wrong `.config` suffix, invalid YAML, or not Standard | Check packaging, platform mode, and events |
| Environment update hangs or reprovisions EC2 | Option change affects resource lifecycle | Inspect change scope, events, health, and rolling policy |
| App cannot see `DB_PASSWORD` | Wrong namespace, unsupported platform, ARN/KMS/IAM error | Check platform version, secret metadata, and instance profile |
| Some instances fail DB auth after secret rotation | Old/new secret values coexist; instances not refreshed | Compare rotation/instance replacement events; refresh per plan |
| `AccessDenied` fetching secret | Missing `secretsmanager:GetSecretValue`/`ssm:GetParameter`/`kms:Decrypt` | Check role, resource ARN, key policy, and conditions |
| `DB_HOST` resolves, but TCP times out | RDS SG blocks traffic, NACL/route/VPC misconfigured | Check source app SG, DB port, and networking |
| DB reports invalid password | Secret mismatches user, out-of-sync rotation, wrong account/Region | Check secret reference and rotation state without printing credentials |
| DB reports too many connections | Pool size × instances exceeds DB limit | Measure connections/pools, right-size, consider RDS Proxy |
| App returns 503 while environment shows Healthy | Health endpoint does not reflect real path; dependency failing | Check ALB targets, app logs, DB/downstream APIs |
| EB CLI diagnostics expose sensitive data | Tool/app prints full config/env | Stop sharing logs, rotate exposed secrets, redact |
| New deploy still uses old config | Precedence, build missing `.ebextensions`, or config update unfinished | Inspect version, packaging, events, and config sources |
| Blue/green code rollback still hits data errors | Incompatible database migration | Use expand-and-contract schemas, backup/restore, rollout plan |
| RDS charges continue after terminate | External DB or retention policy kept the resource | Check Cost Explorer, DB ownership, and deletion policy |
| Cannot reach Secrets Manager from private subnet | Missing NAT/VPC endpoint or DNS/SG issue on endpoint | Check VPC egress, PrivateLink endpoint, and IAM |

### 12.1. Short Diagnostic Workflow

~~~text
1. Confirm AWS account, Region, application, environment, and platform.
2. Check environment status, health, and events.
3. Inspect effective configuration and precedence WITHOUT printing secrets.
4. Check environment / environmentsecrets namespaces and version support.
5. Check EC2 instance profile IAM, secret/parameter ARNs, and KMS policies.
6. Check VPC/subnets/security groups, DNS, and paths to RDS/Secrets Manager.
7. Check TLS, DB credential rotation, connection pools, and database health.
8. Inspect redacted app logs and ALB/EC2/RDS metrics.
9. Fix the right layer, smoke-test, and assess impact.
10. Keep rollback, backups, and post-lab cleanup ownership clear.
~~~

## 13. Design Scenario: Course Registration Platform

### 13.1. Problem Statement

A team builds a **Spring Boot** application with a course management API:

- Traffic spikes during registration openings; requires a load-balanced environment across at least two AZs.
- Transactional data in **PostgreSQL on RDS** must survive environment replacements.
- The app uploads documents to **S3** and calls a notification service with an API token.
- Secrets must live in Secrets Manager/SSM, never in the repository or plaintext environment properties.
- Staging and production need separated permissions, auditing, CloudWatch logs, backups, and cost control.
- Periodic DB password rotation must not disconnect all instances simultaneously.

### 13.2. Reference Design

| Component | Choice | Rationale |
|---|---|---|
| Application | One app with at least staging/prod environments | Same codebase, distinct config |
| Compute | Beanstalk Standard, load-balanced, multi-AZ Auto Scaling | Sufficient capacity and safe instance replacement |
| App config | `APP_ENV`, `DB_HOST`, `DB_PORT`, `DB_NAME` | Non-sensitive variables with clear source governance |
| Secrets | `DB_USER`/`DB_PASSWORD` in Secrets Manager; API token in SSM/Secrets Manager | No plaintext in source |
| Secret access | EC2 instance profile scoped only to that environment's ARNs | Least privilege |
| Database | External RDS in private DB subnets, Multi-AZ per RTO/RPO | Decouples data lifecycle from app environment |
| Network | Private app instances, App SG → DB SG on exact port | Reduces attack surface |
| API ingress | ALB HTTPS with valid certificate and health checks | Protects clients and tracks target health |
| S3 | Private S3 bucket + appropriate IAM role/bucket policy | Avoids static AWS credentials |
| Rotations | Controlled refresh, dual credentials/zero-downtime plan | Prevents old/new instances mismatching passwords |
| Logging | Redacted logs, CloudWatch metrics/events | Diagnostics, auditing, alerts |
| Recovery | Tested RDS backup/restore, deploy rollback/blue-green | Data durability and availability |
| Cost | Right-sizing, tagging, Budgets, lab environment cleanup | Controls EC2/RDS/NAT/ALB spend |

### 13.3. Analysis Questions

1. Why shouldn't `DB_PASSWORD` be placed in `.ebextensions` under the standard `environment` namespace?
2. In a load-balanced environment with multiple EC2 instances, what happens after a secret rotates before all instances are refreshed?
3. If the database must survive terminating the environment, which RDS model should you use?
4. `DB_HOST` is set, yet DB requests time out: do you check DNS, SGs, or secrets first?
5. Why is attaching `AdministratorAccess` to the Beanstalk service role the wrong fix for an EC2 instance `AccessDenied` error?
6. Why does blue/green deployment require checking database schema backward compatibility?
7. If scaling increases from 2 to 8 instances, what issue can the DB connection pool cause?
8. If an environment-level option overrides `.ebextensions`, where should you edit to avoid drift?
9. When the AWS CLI only needs secret metadata, why avoid calling `GetSecretValue`?
10. After deleting an environment, which resources might still incur charges?
11. Which platform versions support environment secrets and JSON-key extraction, and why verify the live version?
12. If Beanstalk health is Green while user logins fail, what metrics or tests are missing?

**Brief hints:**

1. Plaintext config risks exposure and complicates rotation; reference a secret store.
2. Old and new instances can hold two passwords; use a refresh plan and dual credentials.
3. External/decoupled RDS managed independently of the environment.
4. Check network paths, SGs, ports, and DNS first; focus on credentials for 401/DB auth failures.
5. Roles, IAM resource policies, permissions boundaries/SCPs, and service context must match responsibility; broad permissions expand risk.
6. The older app version must still read the schema throughout the rollback window.
7. Total DB connections exceed limits; calculate max instances × pool size.
8. Review the higher-precedence config source and manage changes via IaC/pipeline rather than only editing the file.
9. Metadata suffices to verify existence/rotation; reading the value increases exposure risk.
10. External RDS, EBS, snapshots, NAT, ALB, S3/logs, domains/metrics.
11. Secret env vars on platform releases from Mar 26, 2025; JSON-key extraction from Jan 13, 2026 with constraints; always verify the platform.
12. Add business tests, redacted app logs, DB/KMS/secrets telemetry, ALB 5xx metrics, and traces.

## 14. Misconceptions to Avoid

**"Elastic Beanstalk is just EC2 with a deploy button."** Incomplete. It manages environment configuration and coordinates many resources and lifecycles; still, the team remains responsible for operating the application and data.

**"All Beanstalk environment variables are encrypted secrets."** False. Plain environment properties are not equivalent to Secrets Manager for secret governance; distinguish the two namespaces.

**"Putting a Secret ARN in the standard `environment` namespace makes Beanstalk read the value."** False. `aws:elasticbeanstalk:application:environment` passes a literal string. To have Beanstalk fetch the secret into the variable, use `aws:elasticbeanstalk:application:environmentsecrets` on a supported platform.

**"Secret rotation automatically updates all running instances."** False. Native environment secrets are fetched during bootstrap/refresh; rotation does not automatically sync running instances.

**"You only need to grant IAM permissions to the service role."** False. For native secret-backed env vars on Standard environments, check the **EC2 instance profile role** and KMS policy.

**"RDS attached to Beanstalk is always preserved when deleting the environment."** False. Coupled RDS lifecycles depend on configuration and deletion policies; production should favor an external/decoupled database.

**"Editing `.ebextensions` overrides everything."** False. Direct environment configuration and saved configs take higher precedence.

**"DB connection failures can only be caused by a wrong password."** False. DNS, subnets, security groups, TLS, database state, and connection limits can all cause failures.

**"Beanstalk health Green proves business logic works."** False. You need SLOs, application health checks, synthetic tests, metrics, and DB/app logs.

**"No additional charges apply because Beanstalk is free."** False. Underlying AWS resources and integrated services are billed.

## 15. Pre-Production Checklist

### Configuration

- [ ] Confirmed **Beanstalk Standard vs. Cluster**, platform branch/version, and runtime compatibility.
- [ ] Defined dev/staging/prod strategy with clear data and permission boundaries.
- [ ] Verified precedence order across direct options, saved configs, `.ebextensions`, and defaults.
- [ ] Environment properties contain only appropriate values, with zero hard-coded passwords.
- [ ] Secret references use `environmentsecrets` on a supported platform or SDK retrieval by design.
- [ ] Least-privilege IAM configured for the **instance profile**, KMS key policy, and network path to the secret store.
- [ ] Secret rotation and refresh workflow tested, accounting for coexisting old/new values.
- [ ] Hooks/scripts never print secrets or run unapproved commands.

### Data Connectivity and Operations

- [ ] RDS data lifecycle decoupled from the Beanstalk app when long-term retention is required.
- [ ] App SG ↔ DB SG, TCP ports, DNS, and network routing tested.
- [ ] DB TLS, connection pooling, timeouts, backups, and failover meet SLOs.
- [ ] S3/DynamoDB/SQS access uses IAM roles, never embedded access keys.
- [ ] Health checks, CloudWatch logs/metrics/alerts, and retention configured.
- [ ] Rehearsed smoke tests, staged rollouts, rollbacks, and schema compatibility.
- [ ] Tested backup/restore plan, including resilience if an app environment is terminated.
- [ ] Tags, budgets, Cost Explorer, and lab cleanup schedules in place.
- [ ] CLI/CI logs never emit `SecretString`, plaintext env values, or access credentials.

**Expected outcome:** You know how to declare a Beanstalk environment with clear configuration precedence, pass sensitive values cleanly via secret stores, establish secure private RDS connectivity, and coordinate deployments/rotations without outages. You can inspect configurations via CLI without exposing secrets and explain impacts on resilience and cost.

## Official AWS Documentation

- [AWS Elastic Beanstalk: Environment configuration](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options.html)
- [Configuration options for Beanstalk Standard environments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options-general.html)
- [Environment variables and other software settings](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/environments-cfg-softwaresettings.html)
- [Advanced customization with .ebextensions](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/ebextensions.html)
- [Setting configuration options after environment creation](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/environment-configuration-methods-after.html)
- [Elastic Beanstalk platform hooks](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.hooks.html)
- [Using Elastic Beanstalk with Secrets Manager and SSM Parameter Store](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.secrets.html)
- [Fetch secrets into Elastic Beanstalk environment variables](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.secrets.env-vars.html)
- [Elastic Beanstalk integration with RDS databases](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.managing.db.html)
- [Using Elastic Beanstalk with Amazon RDS](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.RDS.html)
- [AWS Elastic Beanstalk pricing](https://aws.amazon.com/elasticbeanstalk/pricing/)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Application Note:** All account IDs, ARNs, RDS endpoints, environment names, IAM roles, and config values in examples are hypothetical. AWS updates platform releases, secret integrations, IAM conditions, and pricing over time and across Regions. Before deploying or updating production, verify AWS documentation and live environments, test in a sandbox, protect data, and follow change approval processes.
