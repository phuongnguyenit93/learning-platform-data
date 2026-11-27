# Choosing Containers on VMs or Managed Container Services

Packaging an application into a container enables it to carry the necessary libraries and runtime configuration. However, a container image still needs an environment to launch, allocate CPU and memory, connect to networks, store logs, recover from failures, and scale when load increases. There are two common deployment approaches: self-managing containers on virtual machines (VMs) or using a cloud provider's managed container service.

This decision directly affects the operational workload the team must handle, the level of infrastructure control, scaling behavior, availability, and total cost. There is no single best choice for every application; you must choose based on workload characteristics, technical requirements, and your team's operational capabilities.

After this lesson, you will be able to:

- Explain the team's responsibilities when running containers on VMs versus using managed services.
- Compare the two models across control, scaling, availability, security, and cost.
- Select the appropriate model for a workload and justify your reasoning.
- Validate a container deployment before moving to a production environment.

## 1. Containers Running on Virtual Machines

In this model, the team provisions VMs in the cloud network, manages the operating system, and installs a container runtime such as Docker Engine or containerd. Then, the application is launched using commands, Docker Compose, or a process manager such as systemd. The VM provides CPU, memory, disk, and network interfaces; containers share the host operating system's kernel.

For example, an internal API with relatively stable traffic can run on a Linux VM. A reverse proxy on the VM receives HTTPS traffic and forwards requests to an application port bound only on loopback:

```bash
docker run -d \
  --name orders-api \
  --restart unless-stopped \
  --cpus=1 \
  --memory=768m \
  --publish 127.0.0.1:8080:8080 \
  --env-file /etc/orders-api.env \
  registry.example.com/orders-api:1.4.2
```

In this example, CPU and memory limits prevent a single container from easily exhausting the VM's resources. The restart policy helps relaunch the container after the process exits or Docker restarts. Port `8080` is bound only on loopback so the reverse proxy on the same VM can access it; external users enter through the protected HTTPS entry point. The environment file must have restricted read permissions. For production, secrets should be fetched from a secret manager, and you should use scanned images identified by digest rather than relying on a mutable tag.

The team is responsible for the entire host layer: updating and hardening the operating system, patching the kernel, updating the container runtime, configuring firewalls, managing SSH and access permissions, monitoring disk space, rotating logs, backing up data, updating images, and troubleshooting VM incidents. If multiple replicas are required for fault tolerance, the team must also design load balancers, health checks, VM distribution across availability zones, and mechanisms to replace failed VMs.

Running containers on VMs gives significant control over the operating system, networking, monitoring agents, and process placement. This model fits when a workload requires specialized host-level software or configuration, needs to run long-term under steady load, or when the organization already has mature VM management processes. In return, scaling and maintaining availability typically require more automation work.

A single VM remains a single point of failure. `--restart` only restarts the container on that machine; it cannot recover when the VM, disk, or availability zone fails. To achieve high availability, you need multiple VMs across appropriate zones, load balancing, and verified traffic failover when an instance becomes unhealthy.

## 2. Managed Container Services

Managed container services provide an orchestration layer or container execution environment operated by the cloud provider. Users typically declare the image, CPU, memory, replica count, network configuration, access permissions, and scaling policies. The platform takes responsibility for part of the work such as scheduling containers, monitoring processes, replacing failed replicas, or managing the underlying infrastructure.

The term "managed" does not mean all responsibilities are transferred to the provider. The scope of management depends on the product and deployment mode:

- **AWS ECS with AWS Fargate:** declare tasks and services; Fargate provisions the environment to run tasks without the team having to directly manage worker VMs. The team still configures tasks, IAM task roles, networking, storage, logs, and scaling policies.
- **Amazon EKS, Google Kubernetes Engine (GKE), and Azure Kubernetes Service (AKS):** provide a managed Kubernetes control plane. Node management still depends on the usage mode; some modes automate more, but the team still needs to understand workloads, cluster configuration, permissions, networking, and Kubernetes operations.
- **Google Cloud Run and Azure Container Apps:** provide a higher-level container execution environment that can automatically adjust instance counts based on requests or events. Some configurations can scale to zero; in that case, cold start latency and application requirements must be accounted for.

For example, an e-commerce API that experiences heavy traffic spikes during peak hours can be packaged into an image and deployed as a service on Cloud Run or Azure Container Apps. On AWS, the same image can be declared as a task definition and run on ECS Fargate. The team configures CPU, memory, ports, configuration variables, secret references, health checks, permissions to call other services, and instance count limits. The platform launches replicas according to the configuration and can scale them up or down based on the chosen policy.

Managed services significantly reduce the work of maintaining hosts or control planes, making multi-replica deployments and automatic recovery easier. Even so, the team remains responsible for image quality, vulnerabilities in application libraries, API design, data, application permissions, ingress/egress configuration, secrets, alerting, and application-level incident response. The platform can restart a container, but it cannot automatically fix a logic bug causing every replica to return errors.

## 3. Comparing the Two Models

| Criterion | Containers on VMs | Managed Container Services |
|---|---|---|
| Control | Control over VM, OS, runtime, and how containers run | Control over workload configuration; lower access to hosts or control plane depending on the service |
| Operational overhead | Self-patch OS/runtime, manage disk capacity, runtime, processes, and VM capacity | Provider manages part of the infrastructure; team manages images, service configuration, permissions, networking, and applications |
| Scaling | Manually add VMs/containers or pair with autoscaling groups, load balancers, and orchestration tools | Typically includes built-in scaling by CPU, memory, request count, or events; thresholds and limits must be configured |
| Recovery | Self-configure restarts, health checks, VM replacement, and zone distribution | Platform can usually replace failed replicas; must configure replica counts, zone distribution, and proper health checks |
| Cost | Typically pay for provisioned VM capacity, even when idle; can be cost-effective under steady utilization | Can be billed per resource/instance/duration/request; convenient for variable loads, though platform, networking, and observability fees add up |
| Flexibility | Easy to customize OS, agents, devices, and host-level configurations | Constrained by the service's features, runtime, quotas, and networking model |
| Persistent data | Can attach VM disks, but backup and disk lifecycle management are required | Typically uses an ephemeral filesystem; persistent data should be placed in databases, object storage, or supported volumes |
| Portability | OCI images are relatively easy to move; VM scripts and configurations may be environment-dependent | Images remain portable; IAM, networking, autoscaling, and deployment configs are often provider-specific |

### Differences in Scaling and Availability

With VMs, handling increased load may require adding more containers onto machines with spare capacity or provisioning additional VMs. When scaling across multiple VMs, you need mechanisms to distribute images, keep configurations consistent, register instances with a load balancer, and deregister unhealthy hosts. VM autoscaling typically reacts to host-level metrics; it does not inherently understand all application characteristics.

With managed services, the platform can spin up additional replicas based on CPU, memory, concurrent requests, or queues. However, autoscaling is not unlimited: account quotas, database connection limits, startup times, concurrency limits, and the scalability of downstream dependencies can all become bottlenecks. You must set maximum thresholds and run load tests before going to production.

Similarly, managed services do not automatically guarantee application availability. Configure an appropriate minimum replica count, proper health checks, availability zone distribution if supported by the product, and ensure dependencies are also fault-tolerant. A service with a single replica or depending on a single standalone database can still experience outages.

### Differences in Cost

You should not compare solely on CPU and memory pricing. Total operating cost can include:

`Total cost = compute + storage + network + load balancer + registry + logs/metrics + licenses + operational effort`

VMs can be cost-effective when workloads run continuously with steady utilization and VMs are well utilized. However, idle VMs still incur charges, and you must factor in operator time for patching, on-call incident response, and maintaining availability. Managed services can reduce operational time and fit fluctuating loads, though costs can rise due to minimum instance counts, execution duration, requests, egress traffic, NAT, load balancers, or high-volume logs. For services with scale-to-zero, factor in cold starts and latency requirements as well.

## 4. Choosing a Model by Workload

Prefer containers on VMs when one or more of the following conditions apply:

- Steady load, running continuously, and able to make good use of a provisioned pool of VMs.
- The application requires specialized agents, system libraries, network configurations, or host-level control.
- The organization already has a reliable team and established processes for VM administration, patching, monitoring, and recovery.
- Small, internal, or edge workloads where a simple deployment model and host-level control are required.

Prefer managed container services when:

- Traffic fluctuates hourly, seasonally, or around events and requires automatic scaling up and down of replicas.
- The team wants to focus on the application and reduce node or control plane management.
- Built-in workflows for multi-replica deployments, health checks, failed instance replacement, and rollbacks are needed.
- The workload fits within the platform's runtime, networking, storage, and quota limits.

A hybrid approach can also be used. For instance, a legacy system requiring a specialized agent continues running on a VM, while a new API runs on a managed service. Regardless of the model chosen, keep images compliant with the OCI standard, externalize application configuration outside the image, and automate the build, scan, and release pipeline to minimize differences across environments.

Before making a decision, answer the following questions:

1. What are the baseline and peak loads? Does traffic fluctuate enough for autoscaling to deliver real value?
2. Does the application require host-level access, special devices, a persistent filesystem, or network protocols unsupported by the platform?
3. Can the team handle on-call duties and patch VMs/clusters? Is that operational time worthwhile compared to managed service fees?
4. How many replicas and what availability level does the application need, and can its dependencies keep up?
5. How do networking, logs, storage, minimum instance counts, and cold starts impact total cost and user experience?

## 5. Example of Deploying the Same Image on Both Models

Suppose the team develops an `orders-api` service. The image is built and pushed to a shared registry:

```bash
docker build -t registry.example.com/orders-api:1.4.2 .
docker push registry.example.com/orders-api:1.4.2
```

**Option A — Running on a VM:** provision a Linux VM in an appropriate subnet, allow administrative access only from trusted sources, install an approved runtime, configure a reverse proxy, and launch the container with resource limits. For production, manage configurations using automation tools, use a secret manager, ship logs and metrics to a centralized system, and prepare a VM replacement procedure. If HA is needed, deploy multiple VMs across availability zones behind a load balancer.

**Option B — Running on a managed service:** create a service from the same image, select CPU and memory, set minimum/maximum replica counts or scaling policies, and configure health checks, ingress, service permissions, secret references, and log destinations. For example, ECS Fargate runs tasks based on a task definition; Cloud Run or Azure Container Apps deploys the image as a service and adjusts instances per configuration. Check concurrency limits, timeouts, startup time, and how the platform handles ephemeral filesystems.

Both options use the same image but differ in capacity provisioning and operations. If the API has a high, steady baseline load, the VM option may be easier to budget and utilize efficiently. If load varies widely, the managed option can reduce machine scaling and instance recovery work. The final decision should be based on load testing and total cost estimation, not just a single compute unit price.

## 6. Pre-Production Checklist Verification

Perform the following checks for both models:

1. **Image:** verify the exact version or digest, scan for vulnerabilities, keep secrets out of the image, and run the application as a non-root user whenever possible.
2. **Application health:** expose appropriate readiness/health endpoints; verify the application receives traffic only when ready and is removed from the load balancer when unhealthy.
3. **Resources:** set reasonable CPU/memory limits, run load tests, and watch for CPU throttling, abnormal memory growth, or OOM errors.
4. **Networking and permissions:** open only necessary ingress, encrypt connections, restrict egress, use service identities with least privilege, and access databases over private networks when appropriate.
5. **Secrets and data:** retrieve secrets from a secret management system; do not store critical data in the container's writable layer or ephemeral filesystem. Use databases, object storage, or platform-supported persistent volumes.
6. **Scaling and fault tolerance:** test load spikes, hit the maximum scale threshold, stop a replica, and verify traffic continues to be served by the remaining replicas. Check quotas and dependency load capacity.
7. **Observability and recovery:** verify logs, metrics, traces, and alerts are actionable; test deploying a new version, rolling back, and restoring data according to runbooks.

On a Linux VM, you can quickly check status and resources using:

```bash
docker ps --filter name=orders-api
docker logs --tail=100 orders-api
docker stats --no-stream orders-api
curl -fsS http://127.0.0.1:8080/health
```

The `curl` command must be run from the VM or an environment with network reachability to the health check endpoint. For managed services, check the deployment/revision status, desired and running replica counts, launch events, application logs, CPU/memory metrics, request counts, and health check results. Then send a test request to the public or internal endpoint to verify the network path and actual response.

## Selection and Operations Checklist

- [ ] Documented baseline load, peak load, latency requirements, and availability targets.
- [ ] Determined whether the application requires VM control, agents, or host-level configurations.
- [ ] Compared total costs across compute, networking, storage, logs, and operational effort.
- [ ] Verified the platform supports required ports, protocols, volumes, runtimes, and quotas.
- [ ] Configured secure images, least-privilege permissions, secrets, and resource limits.
- [ ] Tested health checks, scaling, recovery when a replica fails, and rollback.
- [ ] Confirmed logs, metrics, alerts, and critical data are persisted outside the container lifecycle.

Choose the model your team can operate reliably within current budget and skill constraints. VMs fit when host-level control is required and self-management capability exists; managed services fit when you want to reduce infrastructure toil and leverage platform-provided orchestration, recovery, or scaling.
