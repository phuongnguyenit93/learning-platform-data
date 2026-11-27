# Rollback and Resource Cleanup When Deployment Fails

Cloud infrastructure or application deployments typically involve multiple sequential operations: creating virtual machines, attaching disks, configuring networks, granting permissions, installing software, updating services, and shifting user traffic. If even a single step fails, the system can end up in a half-deployed state: some resources have been created, some configurations have changed, while the application cannot yet serve requests.

**Rollback** returns the system to a known stable state or applies a compensating change to restore service. **Resource cleanup** handles temporary resources, partially created resources, or resources no longer needed after a failed deployment. The two are related yet serve different goals: service recovery prioritizes correctness and availability; cleanup protects data and prevents leaving behind resources that incur cost or risk.

In **CLOUD_CORE_SERVICES_COMPUTE**, rollback and cleanup are essential parts of provisioning and automation. They enable pipelines to handle failures safely when creating virtual machines, configuring networks, deploying containers, changing images, or updating machine groups. A sound process must know which resources may be deleted, which must be retained, which state must be restored, and how to verify the system is stable.

## 1. What Problems Do Rollback and Cleanup Solve?

A deployment can fail at several points:

- **Before resource creation:** configuration validation, quota, permissions, or input parameter checks fail.
- **During provisioning:** a VM is created but disk attachment fails; a network interface exists while security configuration is incomplete.
- **After provisioning:** agents fail to start, the image is incompatible, or the application fails health checks.
- **During traffic cutover:** some users hit the new version while error rates rise or latency breaches SLOs.
- **After deployment:** data issues, configuration bugs, or incompatible dependencies are discovered.

If a pipeline simply stops at the failing step, previously created resources can remain active. This leads to:

- Ongoing charges for VMs, disks, IPs, load balancers, or NAT gateways.
- Unmanaged resources or resources missing from the IaC tool's state.
- Partially configured machines or services causing conflicts on redeployment.
- Temporary access permissions, security groups, or endpoints left open.
- Half-written data or multiple versions writing concurrently to the same store.
- Operations teams losing visibility into which version the system is currently running.

Rollback focuses on restoring operational state. Cleanup focuses on reclaiming resources that are no longer needed. Sometimes rollback must happen before cleanup; other times failed resources must be kept temporarily to collect logs, snapshots, or forensics before deletion.

## 2. Distinguishing Rollback, Roll Forward, and Cleanup

Three distinct actions are often lumped together as rollback, yet they have different meanings:

| Action | Objective | Example |
| --- | --- | --- |
| Rollback | Return to a prior stable version or configuration | Point the load balancer back to the old machine group |
| Roll forward | Fix the defect with a newer version | Release a patch resolving the bug in the just-deployed release |
| Cleanup | Reclaim resources no longer needed after deployment | Delete temporary build machines, test disks, and ephemeral IPs |

Not every failure should trigger a rollback. If the new release wrote data in a format the old version cannot read, rolling back the application can break the service further. In such cases, rolling forward or restoring data via formal procedures may be safer.

Cleanup also does not mean deleting every resource touched during the deployment. Databases, object storage, disks holding user data, encryption keys, logs, and shared resources may need to persist after a failed release.

## 3. Designing a Failure-Handling Workflow

Pipelines should explicitly define pre-run state, which resources belong to the deployment, and what actions to take when each phase fails.

~~~mermaid
flowchart TD
    A["Start deployment"] --> B["Validate inputs and permissions"]
    B --> C["Record release ID and resource list"]
    C --> D["Provision and configure"]
    D --> E["Run health and functional checks"]
    E --> F{"Release criteria met?"}
    F -- "Yes" --> G["Shift traffic / confirm release"]
    G --> H["Mark deployment successful"]
    F -- "No" --> I["Freeze changes and capture evidence"]
    I --> J["Restore stable version or configuration"]
    J --> K["Verify service"]
    K --> L["Clean up eligible temporary resources"]
    L --> M["Reconcile state and remaining resources"]
    M --> N["Report outcome and retained resources"]
~~~

A controlled deployment workflow typically includes:

1. Generating a unique deployment identifier (release ID or operation ID).
2. Recording the pre-deployment version, target configuration, and planned resources to create or modify.
3. Executing provisioning in phases; saving resource IDs after each successful operation.
4. Checking health, readiness, smoke tests, and critical SLOs.
5. Shifting traffic or marking the release successful only once criteria are met.
6. Upon failure, halting subsequent steps and blocking other pipelines from conflicting actions.
7. Collecting logs, status, events, and metadata needed for investigation.
8. Performing rollback or roll forward depending on the change type.
9. Cleaning up temporary resources belonging strictly to the release and permitted by policy.
10. Reconciling live state with the infrastructure management tool's state.

Each phase should define timeouts, success criteria, failure criteria, and resumption rules when interrupted. An API timeout does not prove a resource was not created; query actual status before retrying.

## 4. Tracking Resource Ownership

Safe cleanup starts with identifying which resources were created by which deployment. Without ownership tracking, automated cleanup could accidentally delete resources in use by another workload.

### 4.1. Applying Tags or Labels

Apply consistent metadata to automatically provisioned resources:

| Tag/label | Purpose | Example |
| --- | --- | --- |
| application | Identifies the application | checkout-api |
| environment | Identifies the environment | staging |
| release-id | Links resource to a specific deployment | rel-20261122-042 |
| owner | Accountable team | platform-team |
| managed-by | Managing tool or pipeline | ci-image-deploy |
| lifecycle | Lifecycle rule | temporary |
| expires-at | Timestamp for review/deletion | 2026-11-23T02:00:00Z |

Metadata examples can be attached to VMs, disks, NICs, security groups, load balancers, snapshots, and supporting resources. Exact tag names depend on the platform; what matters is having a shared convention that pipelines consistently enforce.

Not every resource supports tagging at creation time. For those resources, record their IDs in a deployment manifest or state immediately after the API returns.

### 4.2. Release Resource Manifest

A manifest lists created or modified resources along with allowed failure actions. Example:

~~~yaml
release:
  id: rel-20261122-042
  application: checkout-api
  environment: staging
  previous_version: v2.8.1
  target_version: v2.9.0

resources:
  - id: vm-123
    type: virtual-machine
    action_on_failure: delete
    ownership: release
  - id: disk-456
    type: data-disk
    action_on_failure: retain
    ownership: shared-data
  - id: lb-backend-789
    type: load-balancer-backend
    action_on_failure: restore
    ownership: shared-service
~~~

This is an illustrative example, not a universal cross-provider schema. Pipelines must inspect the manifest prior to cleanup and delete only resources with eligible ownership. Resources without a verified owner should be flagged for investigation rather than deleted automatically.

## 5. Rollback by Deployment Strategy

The rollback procedure depends on how the new version is introduced into service.

### 5.1. Rolling Deployment

Rolling deployments replace groups of instances or pods in batches. If health checks fail:

- Pause the rollout so remaining healthy instances are not replaced.
- Retain the old version if it is still serving properly.
- Revert already updated instances to the prior image or configuration.
- Check capacity to ensure enough healthy machines serve traffic.
- Resume rollout only after fixing the root cause and re-testing.

One risk of rolling deployments is that both versions run simultaneously for a period. APIs, message formats, and data schemas must remain backward-compatible during the transition.

### 5.2. Blue-Green Deployment

Blue-green maintains two environments: blue actively serving and green hosting the new version. The pipeline validates green before shifting traffic.

If green fails after cutover:

1. Switch routes or listeners back to blue.
2. Verify health and error rates on blue.
3. Keep green temporarily to gather logs if needed.
4. After investigation, delete temporary green resources according to the manifest.

This strategy enables rapid traffic reversal, though it requires enough capacity to run both environments and requires accounting for any data mutations written while green was live.

### 5.3. Canary Deployment

Canary sends only a small percentage of traffic to the new version. If latency, error rates, or business metrics cross thresholds:

- Stop increasing traffic percentage.
- Route 100% of traffic back to the stable version.
- Halt or scale down the canary after collecting necessary diagnostics.
- Inspect queues, caches, and data touched by the canary.

Do not base rollback decisions solely on CPU or health endpoints. Monitor error rates, p95/p99 latency, throughput, saturation, and business metrics.

### 5.4. Infrastructure Changes with Infrastructure as Code

With Terraform, CloudFormation, or other IaC tools, an apply run may create several resources before a later resource fails. State may end up partially updated.

The handling workflow should:

1. Preserve the outputs and logs from the apply run.
2. Inspect state and live resource status on the provider.
3. Run plan/preview to identify discrepancies.
4. Determine which resources were created, which are shared, and which must be kept.
5. Fix the root cause and either re-apply or plan a narrowly scoped cleanup.

Never delete the state file to try starting over from scratch. State is the management record linking configuration to live resources; deleting it blinds the tool to existing infrastructure. Never destroy an entire workspace just because an apply failed, especially when the workspace holds shared resources or critical data.

## 6. Handling Partially Created Resources

Mid-flight failures are common in distributed systems. For example, a VM creation API call may finish on the provider side while the client times out before receiving the ID. If the pipeline blindly resends the request, it could spin up a second VM.

### 6.1. Idempotency and Status Queries

An idempotent operation can be retried without causing unintended side effects. When an API supports idempotency keys, use the release ID or operation ID as the unique key for the creation request.

If the API lacks idempotency key support:

- Use naming conventions incorporating the release ID.
- Query resources by tag, name, or operation ID before retrying.
- Check asynchronous provider operation status.
- Record resource IDs as early as possible.
- Distinguish client-side timeouts from provider-confirmed failures.

Never treat a timed-out API call as a guaranteed failure. Verify live state before retrying or cleaning up.

### 6.2. Asynchronous Operations

Many APIs provisioning VMs, disks, or load balancers return an operation ID and continue processing in the background. Pipelines must poll or listen for events until the operation completes, fails, or times out.

If a pipeline is canceled while the provider is still processing, a subsequent reconciliation job should locate in-flight operations and decide whether to wait, cancel, or clean up per policy. Never delete dependent resources while the parent creation operation is still running.

### 6.3. Cleanup in Dependency Order

Resources have dependency relationships. For example, a VM uses a NIC; a NIC sits in a subnet; a disk attaches to a VM; a backend pool references a VM. When deleting, detach links and process in reverse creation order.

General example order:

1. Stop receiving traffic or deregister backends from the load balancer.
2. Drain in-flight requests and stop workloads.
3. Detach dependent volumes or devices if required.
4. Delete temporary VMs or container workloads.
5. Delete NICs, ephemeral disks, addresses, and security rules owned solely by the release.
6. Delete temporary networks or resource groups once no dependencies remain.
7. Reconcile the inventory of remaining resources.

Exact ordering depends on the provider and resource types. If a resource is still referenced, the provider may reject deletion; the pipeline should log the error and continue cleaning up independent resources rather than aborting the whole cleanup.

## 7. Resources That Must Not Be Deleted Automatically

Certain resources must be preserved even when a deployment fails:

- Databases holding real data or user-modified data.
- Persistent disks not yet confirmed to have valid backups.
- Object storage containing user files, artifacts, or diagnostic logs.
- Snapshots and backups required for recovery.
- KMS keys or secrets used by multiple services.
- Shared VPCs, subnets, route tables, NATs, firewalls, or security groups.
- Load balancers and DNS records actively serving the stable version.
- State files, manifests, and metadata needed for reconciliation.

Automated cleanup should combine an allowlist of ephemeral resource types with a denylist of critical resources. Whenever unsure whether a disk or bucket holds data worth keeping, move it to a pending-confirmation state or retain it per policy.

### 7.1. Protecting Data and Schema Changes

Rolling back an application does not automatically roll back a database. A migration might add columns, alter data types, drop columns, or write records in a new format. The old application version may be incompatible with the new schema.

The **expand-and-contract** strategy reduces risk:

1. Expand the schema in a backward-compatible way, such as adding nullable columns.
2. Deploy an application version capable of reading/writing both old and new structures during transition.
3. Backfill data and verify consistency.
4. Switch the application to the new structure.
5. Drop the old structure only once no active version relies on it.

For destructive or irreversible migrations, take backups, verify restore capability, and prepare a roll-forward plan before deploying. Never use automated rollback to wipe data just written by a new release.

## 8. Container and Kubernetes Application Rollback

In Kubernetes, a Deployment stores revision history and supports reverting to a previous revision. Example:

~~~bash
kubectl rollout status deployment/checkout-api
kubectl rollout undo deployment/checkout-api
kubectl rollout history deployment/checkout-api
~~~

These commands illustrate rolling back a Deployment revision. They do not automatically reverse database migrations, external side effects, independent ConfigMap/Secret edits, CRDs, or data inside PersistentVolumes.

With Helm, rolling back a release can restore chart manifests to a prior revision via Helm's release history. Inspect hooks, migration Jobs, retained resources, and changes outside the chart. Never assume a single helm rollback command undoes everything executed inside hooks.

Before cleaning up test pods or namespaces:

- Collect logs, events, pod status, and health check results.
- Verify whether PersistentVolumeClaims contain data that must be retained.
- Check whether Services, Ingresses, load balancers, and secrets are shared.
- Delete temporary workloads using release labels.
- Delete PVCs or namespaces only when storage retention policies allow.

## 9. Automated Cleanup and Handling Orphaned Resources

Orphaned resources are resources that still exist without clear active management by a pipeline, application, or operations team. They occur when jobs are canceled, runners lose connectivity, or cleanup steps fail.

A periodic cleanup job can:

1. Search for resources tagged with managed-by and lifecycle=temporary.
2. Check whether expires-at has passed the allowed deadline.
3. Verify the corresponding release is in a failed, canceled, or completed state.
4. Confirm the resource is no longer referenced by active workloads.
5. Log the candidate deletion list and rationale.
6. Run in dry-run mode or request approval based on risk level.
7. Delete resources in dependency order.
8. Record results, errors, and items needing manual handling.

Never delete solely based on resource age. An old disk might be a retained backup; an unattached IP for weeks might be reserved for an upcoming deployment. Evaluate tags, release state, dependencies, and retention policies together.

### 9.1. TTL Policy Example

~~~yaml
cleanup_policy:
  selector:
    managed-by: ci-provisioner
    lifecycle: temporary
  require_release_state:
    - failed
    - canceled
  grace_period: 24h
  dry_run_by_default: true
  protected_resource_types:
    - database
    - persistent-volume
    - backup
    - kms-key
  require_owner_for_unknown_resources: true
~~~

This is an illustrative configuration. A 24-hour TTL is only an example; retention periods must fit investigation windows, usage schedules, and organizational retention requirements.

## 10. Sample Pipeline with Rollback and Cleanup Steps

The example below shows how to structure steps in a pipeline. Command names are placeholders and must be replaced with your organization's and provider's tools.

~~~yaml
stages:
  - prepare
  - provision
  - deploy
  - verify
  - finalize

variables:
  RELEASE_ID: "rel-20261122-042"

prepare:
  stage: prepare
  script:
    - validate-inputs
    - record-previous-release
    - create-resource-manifest

provision:
  stage: provision
  script:
    - provision-resources --release "$RELEASE_ID"
    - record-resource-identifiers

deploy:
  stage: deploy
  script:
    - deploy-version
    - wait-for-readiness

verify:
  stage: verify
  script:
    - run-smoke-tests
    - check-error-rate-and-latency

finalize:
  stage: finalize
  script:
    - mark-release-successful
    - cleanup-superseded-temporary-resources
  when: on_success

rollback:
  stage: finalize
  script:
    - capture-failure-evidence
    - restore-previous-traffic-and-version
    - verify-service-health
    - cleanup-eligible-release-resources
    - reconcile-provider-state
  when: on_failure
~~~

In real pipelines, the rollback job must execute even when an earlier stage job fails. Configure job dependencies and execution conditions per your CI/CD engine; some systems require always/when-always rules or a dedicated workflow. Cleanup commands must read the manifest and verify ownership and allowed resource types before executing.

Never put credentials directly into pipeline variables or logs. Use the CI/CD secret store and least-privilege workload identities. Rollback permissions may need to update routes or deployments; cleanup permissions should only be allowed to delete temporary resource types within the release scope.

## 11. Tracking Rollback and Cleanup Outcomes

Pipelines must not declare success simply because a rollback or delete command exited with code 0. Verify actual live state.

| Verification Area | Metrics or Evidence | Pass Criteria |
| --- | --- | --- |
| Service | Health checks, error rate, p95/p99, throughput | Back within SLO thresholds |
| Version | Image ID, deployment revision, release ID | Actively serving the expected version |
| Traffic | Backend pools, routes, DNS, or traffic splits | Traffic flows to the stable group |
| Data | Migration status, replication lag, integrity checks | No unexpected discrepancies or data loss |
| Resources | Lists of VMs, disks, NICs, IPs, volumes, load balancers | Temporary resources handled; retained resources intact |
| IaC State | Plan, state, and live resources | No unexplained differences remain |
| Security | IAM, firewalls, secrets, and temporary endpoints | Temporary access and paths revoked |
| Cost | Running resources and retained storage | No temporary resources incurring off-policy charges |

If service is restored yet cleanup failed, report two separate outcomes: **service recovery** and **resource cleanup**. For example, rollback succeeded while a temporary disk could not be deleted because an attachment remained. The pipeline can mark the service stable and raise a ticket/alert for cleanup rather than claiming everything succeeded.

## 12. Handling Failures When Rollback Itself Fails

Rollback is itself an operation that can fail. The old version may lack sufficient capacity, routes might fail to update, pipeline credentials might expire, or data mutations might make the prior version incompatible.

Prepare for this by having:

- **Fallback:** keep traffic on a stable environment or switch to a maintenance page when immediate recovery is impossible.
- **Bounded retries:** retry only idempotent operations with backoff and state checks.
- **Escalation:** alert on-call engineers when rollback times out or fails health checks.
- **Evidence:** preserve logs, events, manifests, and snapshots needed for investigation.
- **Runbooks:** clearly specify who has authority to decide on roll forward, backup restore, or traffic shifts.
- **Reconciliation:** re-run reconciliation once the provider recovers or permissions are restored.

In distributed systems, not every side effect can be undone. For example, sent emails, confirmed payment transactions, or outbound webhooks cannot be erased by rolling back a deployment. Applications must use **compensating actions** such as issuing refunds, emitting corrective events, or recording pending reconciliation states. Compensating actions should carry transaction IDs and deduplication guards.

## 13. Real-World Example: Failed VM Group Deployment

A pipeline deploys a new version of a Java service by provisioning three VMs, attaching disks, registering backends in a load balancer, and deploying the new image. Two VMs start cleanly; the third fails to boot due to a missing driver in the image. The group health check fails, so the pipeline halts before shifting full traffic.

Team response:

1. Mark the release as failed and lock other pipelines from modifying the same resource group.
2. Save boot logs, image ID, operation IDs, and status of all three VMs.
3. Keep the old backend group actively serving users.
4. Deregister the two new VMs from the backend pool so they receive no traffic.
5. Delete the two release-owned test VMs and their NICs after confirming they hold no data requiring retention.
6. Retain the diagnostic disk of the failed VM during investigation, tagging it to block automated cleanup.
7. Reconcile the manifest against live resources; confirm the load balancer, network, and shared disks remain intact.
8. Fix the image, generate a new release ID, and re-run the pipeline from the beginning with the tested image.

If the team deleted the entire resource group or network upon failure, the existing service could lose connectivity. If it deleted the failed disk too soon, it would lose evidence needed to diagnose the boot failure. Cleanup scope must follow ownership and investigative needs.

## 14. Checklist Before Enabling Automated Cleanup

- [ ] Resources carry tags or manifest entries identifying the exact release and owner.
- [ ] Release is in a failed/canceled state with no provisioning operations still running.
- [ ] Resources are not referenced by the stable version or any other workload.
- [ ] Data requiring retention is identified and backed up/checkpointed appropriately.
- [ ] Resources belong to types permitted for deletion on the allowlist.
- [ ] Dependency detachment order is defined.
- [ ] Logs, events, and snapshots needed for investigation are saved.
- [ ] Cleanup permissions are restricted to the release scope.
- [ ] Dry-run mode, outcome logging, and retry/alert mechanisms exist.
- [ ] Post-cleanup reconciliation detects any remaining orphaned resources.

This checklist should be translated into policy and automated checks wherever possible. Data-bearing and shared resources require dedicated safeguards and proper approvals.

## 15. Operational Principles

1. **Separate service recovery from resource cleanup:** prioritize returning the system to stability, then clean up per policy.
2. **Track ownership:** use release IDs, tags, labels, and manifests to identify resources belonging to a deployment.
3. **Design for idempotency:** retries must never spawn extra resources or unintended side effects.
4. **Reconcile before deleting:** verify provider state, dependencies, and IaC state.
5. **Protect data:** never delete databases, persistent disks, backups, or shared resources merely because a deployment failed.
6. **Clean up in dependency order:** remove traffic and workloads first, then handle underlying resources.
7. **Preserve evidence:** capture required logs, events, manifests, and snapshots prior to cleanup.
8. **Verify outcomes:** check health, version, data, remaining resources, and cost.
9. **Plan for rollback failures:** maintain fallbacks, escalation paths, and roll-forward or compensating action plans.
10. **Monitor orphaned resources:** use conditional TTLs, dry-runs, and retention policies for safe cleanup.

Rollback and cleanup are two halves of a single resilient deployment process. When pipelines know which stable version to restore, which resources belong to a release, and which data must be preserved, a failed deployment can be handled under control. This protects the service, curbs runaway costs, and keeps cloud infrastructure in a manageable state.
