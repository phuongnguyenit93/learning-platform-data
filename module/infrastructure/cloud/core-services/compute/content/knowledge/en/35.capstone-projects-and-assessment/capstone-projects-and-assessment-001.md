# Building a Multi-Zone Web Service with an Automated Deployment Pipeline

In this capstone project, you will design and deploy a web service capable of continuing to serve traffic when a zone experiences an outage, while automatically testing and releasing new versions through a CI/CD pipeline. The project brings together compute, networking, storage, identity, security, monitoring, and automation into an operable system.

We use AWS as the concrete implementation example: Application Load Balancer (ALB) handling HTTPS across multiple Availability Zones (AZs), Amazon ECS running containers on AWS Fargate in private subnets, Amazon RDS for PostgreSQL deployed Multi-AZ, Amazon ECR storing images, and GitHub Actions deploying via OIDC. The architectural concepts apply to other clouds using their corresponding services.

The goal is not merely to run multiple replicas of an application. You must prove that traffic is distributed across multiple zones, the application recovers when a task or zone becomes unavailable, new versions are released in a controlled manner, data is not lost when tasks are replaced, and sufficient metrics exist to detect failures.

After completing this project, you will be able to:

- Design a multi-zone web tier with a load balancer and stateless compute.
- Separate public, application, and database subnets; configure security groups for least-privilege access flows.
- Deploy a container service with health checks, autoscaling, and a rollback mechanism.
- Build a pipeline for automated testing, building, scanning, publishing images, and deploying.
- Manage database schemas, secrets, logs, metrics, backups, and recovery procedures.
- Validate availability through controlled fault testing and document the results.

## 1. Problem Statement and Acceptance Criteria

You are tasked with building an internal web service with an API and a status check page. The application accepts HTTPS requests, reads/writes sample order data, and provides health check endpoints. Users must not access tasks or the database directly.

Functional requirements:

- The home page or an API endpoint returns the application version and an instance/task identifier to observe request distribution.
- The readiness endpoint returns success only when the application is ready to receive traffic.
- The liveness endpoint indicates that the process is still running.
- The API can read and write a test record in PostgreSQL.
- The application does not store sessions or important uploaded data on the container's ephemeral filesystem.

Operational requirements:

| Item | Acceptance Target |
|---|---|
| Fault isolation | ALB and application tasks run across at least two AZs |
| Replica count | At least two healthy tasks under normal operation |
| Recovery | When a task is stopped, ECS creates a replacement task and ALB only routes traffic to healthy targets |
| Zone fault tolerance | When one AZ is unavailable during testing, the service continues serving from the remaining AZ within designed capacity limits |
| Database | Database resides in private subnets, with Multi-AZ failover and appropriate backups |
| Deployment | Commits to the release branch trigger automated tests, image builds, and deployment |
| Rollback | A failed deployment can automatically roll back or restore the previous revision per the runbook |
| Security | No secrets in source code or images; tasks have least-privilege permissions |
| Observability | Logs, metrics, alarms, and deployment history are available |

Before implementing, align on service objectives with the application owner: availability target, RTO (recovery time objective), RPO (acceptable data loss), throughput, latency, and budget. Examples in this guide use illustrative targets; production requires approval based on actual requirements.

## 2. Reference Architecture

~~~mermaid
flowchart LR
  U[Users] --> DNS[Route 53 + ACM]
  DNS --> ALB[ALB - public subnets<br/>AZ-a / AZ-b]
  ALB --> ECS[ECS Fargate - private app subnets<br/>2+ tasks]
  ECS --> DB[RDS PostgreSQL<br/>private DB subnets - Multi-AZ]
  CI[GitHub Actions - OIDC] --> ECR[ECR image registry]
  ECR --> ECS
  ECS --> SM[Secrets Manager]
  ECS --> CW[CloudWatch logs / metrics / alarms]
~~~

Request flow:

1. Users access the service hostname. DNS points to the ALB, and TLS certificates are managed by AWS Certificate Manager (ACM).
2. The ALB receives HTTPS on listener 443, checks target health, and forwards requests to healthy ECS tasks through an IP-type target group.
3. The ECS service runs Fargate containers in private subnets across at least two AZs.
4. The application accesses PostgreSQL over the private network. The database only accepts connections from the application security group.
5. The ECS execution role allows the ECS agent to retrieve secrets declared in the task definition; if the application itself calls Secrets Manager via the SDK, grant least-privilege secret read permissions to the task role. Logs are sent to CloudWatch Logs.
6. GitHub Actions authenticates to AWS via OIDC, pushes the image to ECR, and instructs ECS to deploy a new task definition revision.

Data and operational components:

- RDS Multi-AZ maintains a synchronous standby replica to support failover. The standby of a Multi-AZ DB instance is not a read replica for scaling read queries.
- S3 can be used to store uploaded files or durable artifacts; do not use the container's writable layer for persistent data storage.
- CloudWatch stores logs/metrics; CloudTrail records administrative API activity.
- AWS WAF can be attached to the ALB if the application needs web-layer request filtering.
- NAT Gateways or VPC endpoints provide connectivity from private subnets to ECR, CloudWatch, Secrets Manager, and required AWS services. Choose the approach based on networking requirements and cost.

### Subnet and Security Group Layout

| Tier | AZ-a | AZ-b | Primary Access Rules |
|---|---|---|---|
| Public | Public subnet A: ALB node, NAT if chosen | Public subnet B: ALB node, NAT if chosen | Internet to ALB on 443; 80 redirects to 443 only |
| Application | Private app subnet A: ECS tasks | Private app subnet B: ECS tasks | Accepts application port only from the ALB security group |
| Database | Private DB subnet A | Private DB subnet B | Accepts PostgreSQL port only from the application security group |

Create a DB subnet group spanning subnets in multiple AZs. Use security groups referencing the source security group rather than opening the database to the entire VPC CIDR. Do not assign public IPs to ECS tasks or the database.

If using NAT Gateways, deploying one per AZ gives private subnet traffic a local egress path and avoids relying on a single NAT; the trade-off is additional hourly and data processing charges. VPC endpoints for ECR, S3, CloudWatch Logs, and Secrets Manager can reduce NAT dependency, but require appropriate endpoint policies, DNS, and security group configuration.

## 3. Preparing the Web Application

The application must meet specific characteristics to run multiple replicas:

- Stateless: sessions reside in tokens or a shared store like Redis if needed; do not hold session state in a single task's RAM.
- Externalized configuration: database endpoints, log levels, and feature flags come from environment configuration.
- Secret separation: database passwords are retrieved from Secrets Manager; do not bake secrets into the image.
- Graceful shutdown: handle SIGTERM, stop accepting new requests, and finish in-flight requests within the time window ECS allows.
- Health endpoints: readiness reflects ability to accept requests; liveness detects a hung process.
- Safe database access: bounded connection pool, timeouts, and controlled retries.

Example response structure for observing replicas:

~~~json
{
  "status": "ok",
  "version": "1.8.0",
  "instance": "task-id-or-hostname"
}
~~~

Do not expose sensitive information such as internal hostnames, private IPs, secrets, connection strings, or stack traces on public endpoints. If you need to verify which task is serving, use a truncated identifier or build revision.

### Health Checks

| Endpoint | Meaning | Success Condition |
|---|---|---|
| /health/live | Process is alive | Runtime and event loop are not hung |
| /health/ready | Can accept new requests | App has loaded configuration, connected to essential dependencies, and is ready to serve |
| /version | Identifies running build | Returns non-sensitive version and build SHA |

Avoid having readiness check too many non-essential dependencies. If an auxiliary analytics service temporarily fails, the entire web tier does not necessarily need to be pulled from the load balancer. Conversely, if the database is a mandatory dependency and the app cannot serve read/write requests, readiness should reflect that state in a way that avoids creating an overload loop.

## 4. Infrastructure as Code (IaC)

Manage VPC, subnets, routes, security groups, ALB, ECS, ECR, IAM, and RDS with Terraform or an organization-approved IaC tool. Store configurations in Git for review, reproducibility, and change tracking.

A repository structure you can use:

~~~text
web-multizone/
  app/
    src/
    Dockerfile
    tests/
  infra/
    modules/
      network/
      alb/
      ecs-service/
      database/
    environments/
      staging/
      production/
  deploy/
    task-definition.json
    scripts/
      smoke-test.sh
      rollback.sh
  .github/
    workflows/
      ci-cd.yml
~~~

Separate variables per environment. Do not commit state files, secrets, or files containing passwords. With Terraform, use encrypted remote state, enable versioning, and use state locking to prevent two pipelines from applying simultaneously. Production applies should require review/approval and IAM permissions scoped to the workspace/account.

### ECS Service Configuration Skeleton

The following Terraform snippet illustrates key attributes of an ECS service; the ARNs, subnets, security groups, and task definition are inputs created by infrastructure modules:

~~~hcl
resource "aws_ecs_service" "web" {
  name            = "web-production"
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.web.arn
  launch_type     = "FARGATE"
  desired_count   = 2

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_app_subnet_ids
    security_groups  = [aws_security_group.web_task.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 8080
  }
}
~~~

For this configuration to work, the Fargate target group uses target type IP; the ALB HTTPS listener must forward to the target group; the task definition declares `awsvpc` network mode, a container named `web`, port 8080, a log driver, and an execution role. The service must be placed in private subnets in at least two AZs. For a replica service, ECS distributes tasks across AZs within the provided subnets/capacity; after deployment, you must still verify actual task placement.

A `desired_count` of 2 is the minimum baseline in this example. If one AZ fails, one task may remain to serve traffic. Ensure the remaining task has enough capacity for the required load; for higher loads, set a higher desired count and autoscaling minimum capacity to maintain headroom when an AZ is unavailable.

### Target Group and Database Configuration

The target group needs:

- Target type IP for Fargate `awsvpc` networking.
- Health check path `/health/ready`.
- Success codes matching the application's response.
- Interval, timeout, and unhealthy threshold chosen based on startup time and recovery needs.
- Deregistration delay sufficient for in-flight requests to finish when a task is replaced.

Database:

- RDS PostgreSQL placed in a private DB subnet group with subnets in at least two AZs.
- Enable Multi-AZ deployment, encryption at rest, backup retention, and deletion protection for production.
- Only the application security group is permitted to connect on port 5432.
- Set application connection limits and monitor database connections.
- Retrieve the password from Secrets Manager; rotate secrets on a schedule compatible with the connection pool.

Multi-AZ improves database availability but does not replace backups and restore testing. Failover can cause brief connection interruptions; the application must reconnect with backoff and without creating a retry storm.

## 5. Automated CI/CD Pipeline

The pipeline must separate CI (verifying artifact quality) and CD (releasing artifacts to environments). Every image must have an immutable tag based on commit SHA or digest; do not use the `latest` tag as the sole identifier for production.

Release flow:

~~~mermaid
flowchart TD
  A[Commit / Pull Request] --> B[Lint and unit tests]
  B --> C[Build container image]
  C --> D[Scan image and dependencies]
  D --> E[Push image to ECR by commit SHA]
  E --> F[Register task definition revision]
  F --> G[Run compatible migration]
  G --> H[Update ECS service]
  H --> I[Wait for service stability and health checks]
  I --> J[Smoke test via ALB]
  J --> K[Monitor metrics and errors]
  K --> L{Within thresholds?}
  L -->|Yes| M[Complete release]
  L -->|No| N[Rollback revision]
~~~

Steps to implement:

1. Pull requests run lint, unit tests, dependency scans, and IaC checks. Do not deploy to production from an unreviewed pull request.
2. When merged into the release branch, build the image once and scan for vulnerabilities. Tag with the commit SHA, push to ECR, and record the image digest.
3. Render the task definition with the new image digest, CPU/memory, port, log configuration, and secret references.
4. Register the new task definition revision.
5. If there are schema changes, run the migration runner as an ECS one-off task using the same image and least-privilege database permissions; migrations must be backward-compatible with currently running tasks.
6. Update the ECS service and wait for deployment completion.
7. Run smoke tests through the ALB/Route 53 hostname.
8. Monitor alarms, error rates, latency, task counts, and database health during an observation window.
9. If health checks or critical alarms fail, roll back the task definition to the previous revision and document the cause.

### Authenticating the Pipeline with OIDC

GitHub Actions should use OpenID Connect to obtain temporary AWS credentials. Configure the IAM role trust policy to restrict access to the exact GitHub organization/repository and allowed branch or environment. Grant only the required permissions, such as pushing to the specific ECR repository, registering task definitions, updating the specific ECS service, reading deployment status, and `iam:PassRole` scoped strictly to the task execution role/task role.

Do not store long-lived AWS access keys in GitHub Secrets when OIDC can be used. GitHub still needs non-secret configuration values such as AWS region, ECR repository, and ECS cluster/service names. Application secrets should reside in Secrets Manager or Parameter Store and be accessed by the task runtime via the task role.

Distinguish the two ECS roles:

- **Task execution role:** used by the ECS agent to pull images from ECR, write logs, and retrieve secrets according to supported configurations.
- **Task role:** permissions for the application itself when calling S3, SQS, or other AWS APIs.

Do not combine pipeline deployment permissions into the application task role. Restrict trust policies, IAM permissions, and resource scopes so that a vulnerability in the application does not automatically grant infrastructure deployment privileges.

### Rolling Deployment and Blue/Green

ECS rolling deployment gradually replaces old tasks with new tasks according to healthy percent thresholds. The deployment circuit breaker can mark a deployment as failed and roll back if the service is unstable. This is the simpler choice for this project.

Blue/green deployment uses two target sets or revisions to shift traffic in a controlled way, optionally supporting bake time and fast rollback. This model requires CodeDeploy/ECS configuration or an equivalent mechanism, two target groups, and a dedicated testing workflow. Do not shift traffic to the new version before health checks and smoke tests pass.

## 6. Safe Database Migrations

A deployment can run old and new task versions concurrently. Therefore, the database schema must remain compatible during the transition period.

Use the expand-and-contract pattern:

1. Expand: add new columns/tables/indexes without breaking existing code.
2. Deploy new code that can read both old and new schemas; begin writing new data if needed.
3. Backfill data in bounded batches while monitoring locks and replication lag.
4. Verify the new data and switch reads to the new structure.
5. Once no old tasks remain and the rollback window has passed, contract: remove old columns or structures in a separate release.

Do not run destructive migrations before new tasks are ready. Do not assume rolling back the application will automatically roll back the schema. For incompatible changes, prepare a dedicated migration plan, backups, and a tested restore point.

## 7. Autoscaling and Capacity When Losing a Zone

ECS Service Auto Scaling can adjust the desired count based on CPU, memory, or an appropriate metric such as request count per target. Configure:

- Minimum capacity sufficient to maintain at least two tasks and headroom when an AZ fails.
- Maximum capacity aligned with quotas, the database connection budget, and financial budget.
- Scale-out that responds quickly enough to traffic increases.
- Scale-in with cooldowns and protection for tasks actively processing requests.

Do not scale the application independently of the database. If each task opens 20 connections and the service can scale up to 30 tasks, the database could receive up to 600 connections from the web tier. Set pool limits based on database capacity, use RDS Proxy if appropriate, and test peak scale.

### Testing N-1 Capacity

N-1 means the system can still meet its defined objectives when losing one infrastructure unit—here, one AZ. As a rough calculation, if each task safely handles 100 requests/second and you need to sustain 150 requests/second when one AZ is lost, at least two tasks must remain after the failure, or per-task capacity must be increased. Do not rely on the pre-failure desired task count; calculate based on remaining tasks and actual capacity.

With exactly two AZs, a desired count of 2 typically places one task in each AZ. When one AZ is lost, only one task remains; this configuration meets the target only if the single remaining task can handle the entire required load. If you need two surviving tasks after losing any AZ, provision enough capacity in each AZ so that a single AZ retains two tasks—for example, four tasks total—and verify actual distribution. Another option is using three AZs with at least one task per AZ, leaving two tasks when one AZ is lost. The final count must be based on peak load, headroom, quotas, and database limits.

Run tests in staging:

1. Record task count, AZ placement, ALB healthy targets, and baseline latency.
2. Generate representative load and confirm the service has sufficient headroom.
3. Perform a controlled stop of tasks in one AZ or simulate removing a subnet/target according to the staging runbook.
4. Confirm the ALB stops routing traffic to unhealthy targets and ECS launches replacement tasks in the remaining available AZs if configuration and capacity allow.
5. Measure error rate, p95 latency, throughput, and recovery time.
6. Check database connections, failover events, and retry behavior.
7. Restore the configuration, confirm tasks rebalance, and document the results.

Do not attempt to disable entire subnets or production resources to simulate failures without a change plan, blast-radius analysis, approvals, and a rollback plan. In production, you can conduct controlled game days by draining targets or stepping down capacity according to approved procedures.

## 8. Security and Operations

### Security

- ALB accepts HTTPS only; use an ACM certificate and redirect HTTP to HTTPS.
- ECS tasks have no public IP; inbound traffic is allowed only from the ALB security group.
- Database is private; inbound traffic is allowed only from the application security group.
- Use a least-privilege IAM task role; separate execution role and deployment role.
- Store secrets in Secrets Manager, never in Git, images, logs, or plaintext task definitions.
- Build images from maintained base images, scan for CVEs, and deploy by digest.
- Enable encryption for EBS/RDS/ECR and logs per organizational requirements.
- Record an audit trail for changes to IAM, networking, task definitions, services, and databases.

### Observability

| Group | Metrics/Logs | Suggested Alarms |
|---|---|---|
| ALB | Request count, target response time, HTTP 4xx/5xx, healthy host count | Healthy targets below threshold; spike in 5xx or latency |
| ECS | Running/pending task count, CPU, memory, deployment failures | Running tasks below desired; sustained high CPU/memory |
| RDS | CPU, free storage, connections, read/write latency, failover events | Connections near limit; low storage; rising latency |
| Application | Request rate, p50/p95/p99 latency, exceptions, dependency timeouts | Rising error rate; p95 exceeds SLO |
| Pipeline | Build/test/scan/deploy results, task definition revision | Deployment failure or image scan critical findings |

Logs should include request ID, version/build SHA, and appropriate log levels. Avoid logging passwords, access tokens, personal data, or sensitive request payloads. Set retention based on operational needs and cost.

### Short Incident Runbook

**ALB reports no healthy targets:** check ECS running tasks, target health reason, container port, health path, security groups, and startup logs.

**ECS tasks keep restarting:** check exit codes, OOM events, secret access, image pulls, startup timeouts, and database connectivity.

**Database connections spike:** check task count, connection pool per task, retry loops, and slow queries; throttle scaling if needed and recover to safe thresholds.

**New deployment causes errors:** halt further rollouts, inspect health checks/alarms, roll back the task definition revision, verify database schema compatibility, and record the faulty build SHA.

**An AZ becomes unavailable:** confirm the ALB still has healthy targets in other AZs, check task capacity and the database endpoint; monitor latency and autoscaling during failover.

## 9. Testing and Verification Commands

Replace hostnames and resource names with values from your environment. The verification commands below do not modify infrastructure.

Check HTTPS and endpoints:

~~~bash
curl -fsS https://web.example.com/health/ready
curl -fsS https://web.example.com/version
~~~

Send multiple requests to observe multiple tasks serving:

~~~bash
for i in $(seq 1 20); do
  curl -fsS https://web.example.com/version
  echo
done
~~~

Inspect the ECS service and tasks:

~~~bash
aws ecs describe-services \
  --cluster web-production \
  --services web-production \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,deployments:deployments[*].status}' \
  --output yaml

aws ecs list-tasks \
  --cluster web-production \
  --service-name web-production
~~~

Check ALB target health:

~~~bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:REGION:ACCOUNT:targetgroup/web/ID \
  --output table
~~~

Inspect application logs:

~~~bash
aws logs tail /ecs/web-production --since 15m --follow
~~~

Wait for deployment completion:

~~~bash
aws ecs wait services-stable \
  --cluster web-production \
  --services web-production
~~~

The waiter command only confirms the service reached a stable state according to ECS; it does not prove the application meets SLOs. Always run smoke tests and monitor metrics after the waiter completes.

### Acceptance Test Matrix

| Scenario | How to Test | Expected Result |
|---|---|---|
| Normal operation | Send continuous requests through ALB | 2+ healthy tasks, successful responses |
| Task failure | Stop one staging task | ALB deregisters target, ECS launches replacement task |
| Valid release deploy | Merge valid commit | Image scanned/pushed, service updated, smoke test passes |
| Faulty deploy | Use test build with failing health check in staging | Circuit breaker or pipeline detects failure and rolls back |
| Database failover | Execute per approved RDS test procedure | App reconnects, bounded errors, data remains consistent |
| AZ unavailable | Simulate by draining targets/tasks per runbook | Service continues serving from remaining AZs within committed capacity |
| Traffic surge | Run gradual load test | Autoscaling activates, database is not overloaded, latency stays within target |
| Secret rotation | Rotate secret in test environment | Tasks pick up new secret per procedure without baking secrets into images |

Record recovery time, error count, p95 latency, throughput, and remaining task count for each scenario. If results fall short, adjust capacity, timeouts, health checks, autoscaling, or dependencies before declaring acceptance.

## 10. Costs and Trade-offs

A multi-zone design increases availability but incurs additional costs:

- ALB has hourly and usage-based charges.
- ECS Fargate is billed by CPU, memory, and task runtime.
- RDS Multi-AZ costs more than single-AZ deployments.
- NAT Gateways, VPC endpoints, data transfer, and log ingestion can represent a significant share.
- Two minimum tasks run continuously even during low traffic.

Optimize by sizing CPU/memory from benchmarks, setting sensible autoscaling min/max bounds, reducing log noise, using VPC endpoints where beneficial, and choosing appropriate retention. Do not drop to a single task or remove Multi-AZ if doing so violates committed availability requirements. For staging, you can use start/stop schedules or smaller configurations to cut costs while preserving the ability to test the architecture.

## 11. Extending to Azure and Google Cloud

If you need to implement the same objectives on another platform, map components by role:

| Architectural Role | AWS in This Project | Azure | Google Cloud |
|---|---|---|---|
| HTTPS load balancing | Application Load Balancer | Azure Application Gateway or Azure Load Balancer depending on L7/L4 | External Application Load Balancer |
| Multi-zone compute | ECS Fargate service | Azure Container Apps, AKS, or VM Scale Sets | Cloud Run, GKE, or regional Managed Instance Group |
| Container registry | Amazon ECR | Azure Container Registry | Artifact Registry |
| Managed relational database HA | RDS Multi-AZ | Azure Database for PostgreSQL zone-redundant HA if region/SKU supports it | Cloud SQL HA regional |
| Secret management | AWS Secrets Manager | Azure Key Vault | Secret Manager |
| Metrics/logs | CloudWatch | Azure Monitor / Log Analytics | Cloud Monitoring / Cloud Logging |
| CI/CD identity | GitHub OIDC assume IAM role | GitHub OIDC federated credential with Entra ID | Workload Identity Federation |

Do not copy subnet, firewall, identity, or deployment configurations verbatim across clouds. Verify zone models, service limits, failover semantics, quotas, and pricing in the target region.

## 12. Project Deliverables

When complete, the repository should contain:

- Web app source code and Dockerfile.
- Unit/integration tests and instructions to run locally.
- IaC for networking, ALB, ECS, ECR, database, IAM, and logging.
- Task definition configuration and per-environment parameters.
- CI/CD pipeline and OIDC trust policy documentation.
- Runbooks for deploy, rollback, secret rotation, database recovery, and AZ failure.
- Test report including architecture, diagrams, load test results, simulated failures, and metrics.
- Monthly cost estimate with explicit assumptions.

## Final Acceptance Checklist

- [ ] ALB has an HTTPS listener and properly configured target group health checks.
- [ ] ALB is placed in public subnets across at least two AZs.
- [ ] ECS tasks run in private subnets across at least two AZs with no public IPs.
- [ ] At least two healthy tasks run under normal conditions with sufficient headroom for losing one AZ.
- [ ] Security groups allow only the ALB to call the application and the application to call the database.
- [ ] Database has Multi-AZ, backups, encryption, and restore testing.
- [ ] Application is stateless, handles graceful shutdown, and exposes readiness/liveness endpoints.
- [ ] Images are scanned, immutably tagged, and stored in the registry.
- [ ] GitHub Actions authenticates via OIDC with least-privilege deployment permissions.
- [ ] Pipeline runs tests, build, scan, publish, migration, deploy, waiter, and smoke tests.
- [ ] Task definition rollback and schema compatibility procedures are in place.
- [ ] Dashboards/alarms exist for ALB, ECS, database, application, and pipeline.
- [ ] Task failures, deployments, database failover, load increases, and AZ failures have been tested in an appropriate environment.
- [ ] Runbooks, acceptance documentation, and cost estimates are complete.

A multi-zone web service is considered complete only when you have evidence of traffic distribution, recovery, repeatable deployments, and observability. Store test results alongside IaC configurations so another team can reproduce the system and verify operational targets.
