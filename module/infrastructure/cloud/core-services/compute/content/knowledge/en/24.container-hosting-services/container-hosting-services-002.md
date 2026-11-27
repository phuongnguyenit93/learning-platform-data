# Task, Service, Revision, and Container Deployment Units

In cloud container platforms, an application is typically described using multiple object layers. A **task** represents a single container execution; a **service** manages a long-running application and maintains its desired state; a **revision** records a version of the deployment configuration; and a **deployment unit** defines the part of the system that is released, replaced, scaled, or rolled back together.

Accurately distinguishing these concepts helps you design how applications run, choose update strategies, and troubleshoot incidents. This is an important part of learning cloud compute capacity models: beyond selecting CPU, memory, and networking, operators must know which object the platform is managing and how the platform is responsible for recovering that object.

## 1. Conceptual Model

The relationship between these objects can be visualized as follows:

~~~mermaid
flowchart TD
    A["Container image<br/>packaged and identified"] --> B["Task definition / runtime configuration"]
    B --> C["Revision 17"]
    C --> D["Service"]
    D --> E["Task 1"]
    D --> F["Task 2"]
    D --> G["Task 3"]
    E --> H["Container"]
    F --> I["Container"]
    G --> J["Container"]
    K["Revision 18"] --> D
    D -. "roll out and gradually replace" .-> L["Tasks running new revision"]
~~~

The diagram illustrates a common model: a runtime configuration produces a revision; the service uses that revision to create and maintain tasks. When a new revision arrives, the service orchestrates replacing the old tasks. Specific naming and object boundaries vary by provider, so you should map them against the model of the platform you are using.

## 2. Task: A Unit of Execution

A task is an execution instance launched by the platform from a container configuration. Depending on the platform, a task may consist of one container or a group of containers that must run together. For example, a task may contain the main application and a sidecar for log collection or proxying.

A task typically has the following operational attributes:

- **Image:** the container image and version to run. In production environments, identify it by digest—such as `registry.example.com/checkout-api@sha256:...`—to ensure the same configuration always pulls the exact same image.
- **Resources:** vCPU count, memory limits or requests, ephemeral storage, and accelerator settings if any.
- **Networking:** listening ports, network mode, subnets, security groups, or corresponding network policies.
- **Identity and permissions:** service account or task role with least-privilege permissions required.
- **Application configuration:** environment variables, secret references, startup arguments, and logging configuration.
- **Health checks:** health check commands or endpoints so the platform knows whether the container is ready to serve traffic.

A task has its own lifecycle: created, transitioning to running, potentially becoming unhealthy, stopped, or exited. One-off tasks typically fit bounded jobs such as running migrations, processing a data batch, or performing maintenance tasks. Once a task finishes, the platform does not necessarily relaunch it.

In Amazon ECS, a **task** is an instantiation of a task definition. A task definition revision describes containers, images, CPU, memory, networking, permissions, and logging. You can run a task directly for one-off work or let an ECS service manage multiple tasks for long-running applications.

Do not equate a task with a container. A single task can hold multiple containers whose lifecycles and configurations coordinate together. Conversely, an individual container does not decide the replica count of the entire application or how traffic is load-balanced across replicas.

## 3. Service: Managing Long-Running Applications

A service is a logical object representing an application or workload that must be kept running. A service typically declares a desired state and delegates continuously reconciling actual state to the platform scheduler.

For example, the `checkout-api` service might require three tasks to always be available. If one task stops abnormally, the controller detects that the healthy task count is below the desired count and launches a replacement task. If load increases, autoscaling can raise the task count; when load drops, the service can scale down the number of replicas according to the configured policy.

Services typically handle or integrate the following capabilities:

- Maintaining the desired replica count and replacing failed tasks.
- Distributing traffic through a load balancer or service discovery.
- Running health checks and admitting only eligible replicas into service.
- Orchestrating updates via rolling, blue-green, or platform-supported deployment strategies.
- Integrating autoscaling, network policies, availability zones, and monitoring.

A service is not synonymous with a single process or a single task. One service can manage multiple tasks simultaneously. Availability also depends on how tasks are distributed across availability zones, dependency health, load balancer configuration, and resilience when a zone experiences an outage.

Distinguish between two scenarios:

| Execution Mode | Typical Behavior | Suitable Examples |
|---|---|---|
| Standalone task execution | Operator or schedule triggers once; the task can terminate upon completion | Database migrations, batch jobs, file processing |
| Service-managed execution | Platform maintains replica count, replaces failed tasks, and manages endpoints | APIs, web backends, continuous workers |

For queue-processing workers, a service may not need an HTTP load balancer, yet it still needs to maintain the worker count, grant permissions to read the queue, emit metrics, and scale based on queue depth.

## 4. Revision: Versioned Deployment Configuration

A revision is a versioned record of a deployment configuration. A revision is typically tied to the image, resources, environment variables, referenced secrets, ports, startup commands, and runtime settings. When a new revision is created, the platform retains old revisions so you can inspect history or shift traffic back if the deployment model supports it.

A revision should be treated as an identifiable and reproducible configuration snapshot. For example:

- Revision 17 runs the `checkout-api` image with digest A, 0.5 vCPU, and 1 GiB of memory.
- Revision 18 runs digest B, increases memory to 2 GiB, and updates a configuration variable.
- The service begins deploying revision 18, creates new tasks, runs health checks, and gradually drains tasks from revision 17.

In Amazon ECS, revisions belong to a **task definition**. When registering a new task definition, ECS creates a new revision; the service can be updated to use that revision. Running tasks do not mutate their configuration in place: the service deploys new tasks from the new revision and replaces old tasks according to deployment settings.

In Google Cloud Run, a revision is an immutable version of the corresponding service or job configuration. With a Cloud Run service, multiple revisions can coexist and receive different percentages of traffic. This supports canary deployments or shifting 100% of traffic back to a previous revision. The task concept in Cloud Run typically relates to job executions; for HTTP services, use Cloud Run's proper terms: instance and revision.

Do not rely on mutable image tags like `latest` to uniquely identify a revision. If a tag is re-pushed with different contents, the same configuration string can run different images at different times. Using immutable digests, storing build metadata, and keeping a link between revisions and commits or releases makes tracing and rollbacks far more reliable.

Revisions also do not guarantee that the entire system can roll back safely. If a new version modified the database schema in a way the old version cannot read, shifting traffic back to an old revision may still cause errors. Data changes require backward-compatibility strategies, multi-step migrations, and a dedicated recovery plan.

## 5. Container Deployment Units

A deployment unit is the scope impacted by a single release. When defining this unit, answer: which object gets a new version, which object gets replaced, where is traffic shifted, and what does a rollback revert to the previous version?

There is no single definition that applies across all platforms:

| Platform | Execution Object | Management or Routing Object | Typical Deployment Unit |
|---|---|---|---|
| Amazon ECS | Task running from a task definition | ECS service maintains task count and can integrate with a load balancer | Service deployment, consisting of tasks in the deployed task set or configuration revision |
| Google Cloud Run | Instance serving requests; task in Cloud Run Jobs | Cloud Run service provides an endpoint and manages traffic splitting | Revision; traffic can be shifted across multiple revisions |
| Kubernetes | Pod containing one or more containers | Service provides a stable network endpoint; Deployment manages ReplicaSets and rollouts | Deployment/ReplicaSet rollout; Pods are the execution instances replaced |

In a simple application, one service may correspond to one deployment unit. In a multi-component system, APIs, workers, and schedulers may be separate services with independent release cadences. Grouping components that do not need to update together into a single unit forces a small change to redeploy the entire group, increasing blast radius and release time.

Conversely, splitting too finely increases the number of configurations, endpoints, access permissions, pipelines, and alerts to operate. Split deployment units along responsibility boundaries, scaling requirements, security requirements, and release independence.

A task containing a main application and a sidecar is usually deployed together because they must coordinate within the same execution. However, an API and a worker reading the same queue should often be two separate services: the API scales on HTTP traffic, while the worker scales on pending work volume.

## 6. Practical Example: Deploying a Checkout API on ECS Fargate

Suppose a development team operates a payment API named `checkout-api`. The application needs three replicas, listens on port 8080, and is accessed via an Application Load Balancer.

### 6.1. Declaring the Task Configuration

The illustrative configuration below describes the main attributes of the task definition; this is simplified YAML for learning the model, not a complete ECS JSON task definition file.

~~~yaml
family: checkout-api
revision: 17
runtime: FARGATE
networkMode: awsvpc
cpu: 512
memory: 1024
containers:
  - name: api
    image: registry.example.com/checkout-api@sha256:IMAGE_DIGEST_A
    port: 8080
    environment:
      APP_ENV: production
    secrets:
      DATABASE_URL: secret-reference
    healthCheck:
      command: ["CMD-SHELL", "curl -f http://localhost:8080/health/ready"]
    logging:
      driver: awslogs
taskRole: checkout-api-runtime-role
~~~

The task role should only have permissions the application genuinely needs, such as reading a specific secret or writing to a specific bucket. Never embed passwords or tokens directly in the image or in configuration files committed to source control.

### 6.2. Creating the Service and Maintaining Replica Count

The `checkout-api` service uses task definition revision 17 with a desired count of 3. The service runs tasks in the selected subnets, attaches them to the load balancer target group, and enables health checks.

A desired count of 3 is a target state, not a guarantee that exactly three healthy tasks exist at every moment. During deployments or when a zone fails, the number of available tasks can temporarily fluctuate depending on deployment limits, cluster capacity, and startup time.

To increase availability, distribute tasks across multiple Availability Zones, configure appropriate health checks, and reserve enough capacity to start new tasks while old tasks continue serving. If deployment settings demand too many new tasks simultaneously, capacity may be insufficient; if too few active tasks are permitted, the service may suffer under-provisioning during replacement.

### 6.3. Releasing a New Revision

The team publishes a new image with digest B, then registers task definition revision 18. Revision 18 may update the image, increase memory to 2 GiB, and update a backward-compatible setting. The service is updated to use revision 18.

Typical rolling deployment flow:

1. The platform launches one or more new tasks from revision 18.
2. The new tasks start, load configuration and secrets, and pass health checks.
3. The load balancer adds the new tasks to the serving pool once targets become healthy.
4. The platform stops routing new requests to old tasks and waits for in-flight connections to finish during the drain period.
5. Tasks running revision 17 are gradually terminated until the service reaches its desired state on revision 18.

For APIs with long-running requests, set appropriate graceful shutdown and deregistration delay durations. If a task is killed immediately while processing a request, users may see errors even though the rollout reports success.

### 6.4. Post-Deployment Verification

You can use the AWS CLI to inspect the revision, service status, and running tasks:

~~~bash
aws ecs describe-task-definition \
  --task-definition checkout-api:18

aws ecs describe-services \
  --cluster prod \
  --services checkout-api

aws ecs list-tasks \
  --cluster prod \
  --service-name checkout-api \
  --desired-status RUNNING
~~~

After retrieving the task ARNs, use `describe-tasks` to inspect each task's status, task definition ARN, stop reason, and container health. Also check load balancer target health, startup logs, error metrics, and latency. A service with the right number of running tasks can still fail to serve requests if targets are not healthy, the application binds the wrong port, or a dependency is failing.

Only conclude the release once you have verified:

- The service is steady and the new tasks are running revision 18.
- Healthy task count matches the desired level, properly distributed across availability zones.
- Target group reports healthy and a test request through the endpoint succeeds.
- Error rates, latency, CPU, memory, and logs show no anomalies.
- Critical business flows, such as order creation or payment confirmation, work properly.

If checks fail, halt any traffic ramp-up and redeploy the previous revision following the platform's rollback procedure. After rolling back, still verify tasks, target health, and live requests; a completed rollout status does not replace functional verification.

## 7. Release Strategies and Operational Trade-offs

**Rolling deployment** replaces tasks or instances in batches. This approach utilizes existing capacity well and typically suits stateless services. However, two revisions can coexist for a period of time; the application and data schema must remain compatible across versions.

**Blue-green deployment** prepares a new environment or task group alongside the old group, then switches traffic over. This provides fast cutover and a clear fallback point, but requires extra capacity to run in parallel and careful handling of connections, sessions, and data during cutover.

**Canary deployment** routes a small percentage of traffic to the new revision, monitors errors and latency, and then gradually increases traffic. This reduces the initial blast radius, though it requires reliable metrics, clear stop criteria, and revision-based traffic routing capabilities.

When choosing a strategy, consider the following factors:

| Factor | What to Decide | Risk if Misconfigured |
|---|---|---|
| Task count and spare capacity | Are there enough CPU, memory, quotas, and IPs to run new tasks alongside old ones? | Deployment stalls or insufficient serving replicas |
| Health checks | Checking process liveness, readiness, or reachability to which dependencies? | Unready tasks receive traffic or healthy tasks are repeatedly replaced |
| Shutdown duration | How long does the app need to reject new requests and finish in-flight ones? | Dropped requests, connection errors, or prolonged shutdowns |
| Autoscaling | Scaling by CPU, requests, concurrency, or queue length? | Under-capacity during traffic spikes or high cost when idle |
| Config and secrets | Which configs does a revision reference; how are secrets authorized and rotated? | Revisions hard to reproduce or sensitive data exposed |
| Data and rollback | Is the old version compatible with schemas and data written by the new version? | App rollback succeeds while business logic still fails |

For stateless workloads, tasks can be replaced at any time if state and sessions are stored externally. For stateful workloads, design volumes, synchronization mechanisms, and dedicated recovery procedures; never assume replacing a task preserves that task's local data.

Increasing task count also does not automatically make an application faster. Check database connection limits, queue throughput, network quotas, and dependency capacity. If each task opens too many connections, scaling out can overload downstream systems.

## 8. Quick Cross-Platform Mapping

When working with a provider's documentation or console, locate the exact corresponding object instead of mechanically applying terminology from another platform:

- **Amazon ECS:** task definitions describe configuration; tasks are executions; services maintain task counts; each task definition registration creates a new revision.
- **Google Cloud Run:** services provide endpoints; revisions store configuration versions and can receive specific traffic splits; job executions use tasks for finite jobs.
- **Kubernetes:** Pods are the container execution unit; Deployments manage rollouts via ReplicaSets; Services provide stable network endpoints. Kubernetes has no Task object that maps 1-to-1 to an ECS Task.

When learning a new platform, identify four things: which configuration produces a running unit, which controller maintains replica counts, which version is retained, and which object receives traffic during deployment.

## 9. Lifecycle Verification Steps

You can apply the following workflow to every container release:

1. **Pre-release:** verify the image digest, target revision, CPU/memory, ports, runtime permissions, secrets, and health checks.
2. **At start:** confirm the service is currently on the old revision and has sufficient capacity to run side-by-side per the deployment strategy.
3. **During rollout:** watch task counts per revision, startup status, health checks, service events, and target health.
4. **Post-rollout:** verify which revision is receiving traffic, probe the endpoint, and run business smoke tests; compare error rate, latency, CPU, and memory.
5. **On failure:** stop ramping traffic, collect events/logs, roll back to a compatible revision, and re-verify functionality after rollback.

With Cloud Run, you can inspect a service and its revision list using the following commands; replace the revision name and region for your environment:

~~~bash
gcloud run services describe checkout-api --region asia-southeast1
gcloud run revisions list --service checkout-api --region asia-southeast1
~~~

With Kubernetes, rollout status and Deployment history can be checked with:

~~~bash
kubectl rollout status deployment/checkout-api -n production
kubectl rollout history deployment/checkout-api -n production
~~~

Commands only report the state of platform objects. You still must inspect live requests, application logs, and metrics to confirm users can actually use the service.

## 10. Design and Release Checklist

- [ ] Determined whether the task is a one-off job or a service-maintained execution.
- [ ] Identified which containers belong together in one task and why they coordinate.
- [ ] Image is pinned by digest; revision is traceable back to a build or commit.
- [ ] CPU, memory, ports, networking, runtime permissions, secrets, and logging are declared.
- [ ] Service has appropriate desired count, health checks, zone distribution, and autoscaling policies.
- [ ] Selected deployment unit and rolling, blue-green, or canary strategy matching availability requirements.
- [ ] Application handles graceful shutdown and is compatible with coexisting revisions during rollout.
- [ ] Defined success verification criteria, stop conditions, and rollback plan.
- [ ] Post-release checked active revision, healthy tasks, target health, live requests, logs, and metrics.
- [ ] Evaluated the impact of schema, session, and data changes on rollbacks.

When you understand tasks, services, revisions, and deployment units, operators can read platform state accurately, predict the impact of each release, and select the right scaling or recovery approach. This forms the foundation for operating container workloads reliably, securely, and cost-effectively in the cloud.
