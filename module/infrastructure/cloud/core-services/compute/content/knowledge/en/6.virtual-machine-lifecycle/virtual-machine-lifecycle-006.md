# Delete Locks and Protecting Machines Against Unintended Operations

## Lesson Objectives

Virtual machines can be accidentally deleted during resource cleanup, configuration changes, automation runs, or incident response. For production servers, a single delete operation can disrupt service, lose unbacked-up data, and force recreating numerous dependent resources.

Cloud platforms provide mechanisms such as deletion protection, termination protection, and resource locks to reduce the risk of unintended destructive actions. These mechanisms must be combined with proper access controls, change procedures, and backups.

After this lesson, you will be able to:

- Distinguish delete locks from data protection measures and permission controls.
- Explain the scope and limitations of deletion protection, termination protection, and resource locks.
- Enable, verify, and remove locks under controlled procedures across major cloud platforms.
- Combine resource-level protection, IAM/RBAC, Infrastructure as Code, and operational processes.
- Plan safe replacement or deletion of virtual machines when those actions are genuinely required.

## 1. Why Do Virtual Machines Need Protection?

Throughout a VM's lifecycle, operations teams routinely create, start, stop, reconfigure, back up, replace, and delete machines. Some actions can have severe consequences if the wrong resource is targeted or the wrong command is executed.

Common scenarios:

- An operator accidentally selects a production machine while cleaning up expired test machines.
- An automated script deletes machines by tag or time-to-live (TTL), but the filter is misconfigured.
- A deployment pipeline triggers resource replacement due to an incompatible attribute change.
- An operations team deletes a VM without realizing the boot disk or data disk has a delete-on-termination policy attached.
- An overly privileged account is misused or compromised.
- An autoscaling system shrinks a machine group and terminates an instance that should have been kept.
- Troubleshooting steps are rushed during an incident, resulting in deleting a machine or disk instead of stopping a service.

VM protection aims to reduce the likelihood that a dangerous operation occurs without explicit intent and proper approval. Protection mechanisms should match workload criticality. Temporary test machines may only need tags and an auto-expiry policy; production machines holding critical data require multiple layers of control.

## 2. Distinguishing Lifecycle Operations

Not all operations affecting a virtual machine are equal. Before choosing a protection mechanism, identify which actions must be controlled.

| Operation | Outcome | Risks to Note |
|---|---|---|
| Stop / Deallocate | Powers off the machine, usually keeping configuration and retained disks | Service stops running; some resource types or charges may persist |
| Restart / Reboot | Restarts the operating system or virtual machine | Brief interruption; running processes are disrupted |
| Resize | Changes machine type or CPU/RAM resources | May require stopping the machine; configuration or compatibility may change |
| Reimage / Rebuild | Recreates the operating system or replaces the machine from an image | Data on the OS disk may be lost |
| Detach disk | Removes a volume from the machine | Application loses data access; may cause errors or data corruption if detached during writes |
| Delete / Terminate | Deletes the virtual machine resource | Can lose the machine, dynamic IPs, and dependent resources per platform policy |
| Delete disk / snapshot | Deletes stored data or recovery points | Can cause irreversible data loss |

**Deletion protection** or **termination protection** primarily blocks machine deletion through platform-protected management APIs. It does not by default prevent stop, reboot, resize, OS modifications, actions inside the guest OS, or deleting a standalone volume.

If the goal is protecting data, add backups, snapshots, retention policies, and dedicated protection permissions on disks or snapshots. If the goal is maintaining availability, add redundancy, health checks, and failover procedures.

## 3. Layers of Protection

A solid design typically employs multiple layers. If one layer is misconfigured or bypassed by a highly privileged user, the remaining layers can still reduce risk.

### 3.1. Resource-Level Protection

This is an attribute or flag attached directly to the virtual machine instructing the platform to block deletion. Examples:

- AWS EC2 termination protection.
- Azure resource lock of type CanNotDelete.
- Google Compute Engine deletion protection.

The advantage is that protection status travels with the resource and can usually be inspected via console, CLI, or API. However, each platform has its own scope and exceptions. Verify exact behavior for the service in use, especially when machines belong to an autoscaling group or are managed by a higher-level service.

### 3.2. Resource-Group-Scope Locks

Some platforms support locks at the resource group, project, or management scope level. A parent-scope lock may apply to multiple child resources, depending on the provider's model.

This is useful when you need to protect the VM, disks, and related resources together. However, broad lock scopes can interfere with legitimate pipelines or routine maintenance. Identify exactly which resources inherit the lock and test before applying in production.

### 3.3. Access Control via IAM/RBAC

IAM (Identity and Access Management) and RBAC (Role-Based Access Control) define who is permitted to perform which actions.

A good configuration should:

- Grant permissions based on job roles and responsibilities.
- Separate routine operational permissions from resource deletion permissions.
- Grant machine, disk, or snapshot deletion rights only to groups that genuinely need them.
- Use time-bound temporary privileges for exceptional operations.
- Require strong authentication and additional approval for high-privilege accounts.
- Periodically review accounts, service accounts, role assignments, and access keys.

Resource-level delete locks and IAM complement each other. Anyone authorized to modify protection attributes can disable the lock and then delete the machine; therefore, lock-removal permissions must also be restricted.

### 3.4. Guardrails in Infrastructure as Code

When VMs are managed via Terraform or other Infrastructure as Code (IaC) tools, rules can be added to stop deployment plans from accidentally destroying resources.

Terraform example:

~~~hcl
resource "aws_instance" "production" {
  ami                    = var.ami_id
  instance_type          = "m6i.large"
  disable_api_termination = true

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
~~~

In this example:

- `disable_api_termination` enables EC2 termination protection.
- `lifecycle.prevent_destroy` instructs Terraform to reject any plan that attempts to destroy this resource block while it remains in configuration.

`prevent_destroy` is a Terraform guardrail, not a cloud platform lock. If the resource block is removed from configuration, that lifecycle rule no longer applies to the resource in the current config. Therefore, combine plan reviews, access control, and native platform protection mechanisms.

For critical resources, pipelines should highlight destroy/replace actions clearly and require authorized approval before applying.

### 3.5. Backups and Recoverability

A delete lock is not a backup. It only reduces the likelihood of executing one type of management operation. It does not protect data from application bugs, malware, file deletions inside the guest OS, filesystem corruption, errors by users with write access, or zone outages.

Define clearly:

- Which data resides on the boot disk, data disks, databases, or object storage.
- Backup frequency and retention period.
- Recovery Point Objective (RPO): maximum acceptable data loss.
- Recovery Time Objective (RTO): maximum desired recovery time.
- Who has permission to delete backups and snapshots.
- How restores are tested and data is verified after recovery.

Backups should be protected with separate permissions, retention policies, and appropriate anti-deletion safeguards. If backups live in the same account with the same admin permissions as the source machine, a compromised account can delete both.

## 4. AWS EC2: Termination Protection

Amazon EC2 supports a termination protection attribute on instances. When enabled, requests to terminate the instance through standard management operations are blocked until the attribute is disabled.

Enable termination protection using the AWS CLI:

~~~bash
aws ec2 modify-instance-attribute \
  --instance-id i-0123456789abcdef0 \
  --disable-api-termination
~~~

Check status:

~~~bash
aws ec2 describe-instance-attribute \
  --instance-id i-0123456789abcdef0 \
  --attribute disableApiTermination
~~~

Once approved to delete the machine, disable protection:

~~~bash
aws ec2 modify-instance-attribute \
  --instance-id i-0123456789abcdef0 \
  --no-disable-api-termination
~~~

Then execute the terminate operation following the approved procedure.

Key points to remember:

- Termination protection governs instance termination requests via management APIs; it is not a data backup mechanism.
- It does not replace separate protection for EBS volumes, snapshots, Elastic IPs, or dependent resources.
- With Auto Scaling groups, also configure and understand instance scale-in protection policies. EC2 termination protection does not replace Auto Scaling's protection against scale-in selection.
- Other AWS services may manage instance lifecycles under their own rules. Check the behavior of higher-level services before relying on this protection flag.
- Authorized users can disable the protection attribute. Permissions to modify this attribute must also be restricted.

## 5. Azure: Resource Locks

Azure provides resource locks to restrict operations on Resource Manager resources. Two common lock types are:

| Lock Type | Primary Effect | When to Use |
|---|---|---|
| CanNotDelete | Allows reads and updates per existing permissions but blocks deleting resources within the lock scope | When you want to ensure a VM or resource group remains intact |
| ReadOnly | Blocks write operations on resources within the lock scope | When you want to freeze configuration changes during a special window |

For preventing VM deletion, CanNotDelete is usually more appropriate than ReadOnly. ReadOnly can block legitimate updates and disrupt normal operations.

Example creating a CanNotDelete lock on a VM using the Azure CLI:

~~~bash
az lock create \
  --name protect-prod-vm \
  --lock-type CanNotDelete \
  --resource-group rg-prod \
  --resource-name vm-prod-01 \
  --resource-type Microsoft.Compute/virtualMachines
~~~

List locks in a resource group:

~~~bash
az lock list --resource-group rg-prod --output table
~~~

When deletion is approved, a user authorized to manage locks can remove the lock:

~~~bash
az lock delete \
  --name protect-prod-vm \
  --resource-group rg-prod
~~~

After removing the lock, proceed with VM deletion under the approved change process.

Notes when using Azure locks:

- A lock on a resource group can be inherited by child resources; a lock on a single VM applies only to that resource and does not automatically protect all related resources.
- If you need to protect the VM, disks, and other critical resources together, verify the lock scope and which resources inherit it.
- Resource locks operate at the Azure Resource Manager control plane. They do not stop users with OS-level privileges from deleting files or modifying data inside the VM.
- Locks can affect automation, resizing, updates, or valid write operations. Test in non-production first and document operational exceptions.
- Users with lock management permissions can still delete locks. Restrict permissions to create, modify, and delete locks.

## 6. Google Compute Engine: Deletion Protection

Google Compute Engine supports deletion protection for VMs. When enabled, instance deletion is blocked until protection is turned off.

Enable deletion protection:

~~~bash
gcloud compute instances update vm-prod-01 \
  --deletion-protection
~~~

Inspect instance configuration:

~~~bash
gcloud compute instances describe vm-prod-01 \
  --zone asia-southeast1-b
~~~

In the output, check the `deletionProtection` field.

Once deletion is approved:

~~~bash
gcloud compute instances update vm-prod-01 \
  --no-deletion-protection \
  --zone asia-southeast1-b
~~~

Only then execute the instance deletion command.

Things to keep in mind:

- Deletion protection applies to the configured instance; it does not implicitly protect all disks, snapshots, or other resources.
- Restrict permissions both to update the `deletionProtection` attribute and to delete instances.
- If the VM belongs to a managed instance group or automated workflow, check how the higher-level service handles instance replacement and deletion.
- VM protection does not replace backups for data on boot disks or persistent disks.

## 7. Choosing the Right Protection Scope

Do not enable the same lock type across every resource without considering how each is operated. Balance protection level against the ability to perform legitimate changes.

| Machine Type | Recommended Mechanisms | Rationale |
|---|---|---|
| Production machine running critical services | Deletion/termination protection, IAM-restricted deletion, backups, and approval workflow | High impact from accidental deletion |
| Database server | VM and disk protection, retained backups, separated delete permissions | Must protect both compute and data |
| Bastion or management host | Delete protection, MFA, strict access controls, and auditing | Losing the machine can disrupt administrative access |
| Staging machine | Time-bound protection aligned with release or test cycles | Needs stability during testing while still allowing periodic cleanup |
| Short-lived dev machine | Owner/expiry tags and controlled cleanup policies | Automated cleanup after expiry is acceptable |
| Instance in autoscaling group | Group-level protection and appropriate scale-in policies | Instance lifecycle is managed by the orchestrator |

For production machines, apply a combined approach:

1. Enable native delete protection on the VM.
2. Separately protect critical disks or snapshots.
3. Restrict terminate/delete permissions and lock-removal permissions.
4. Require review whenever an IaC plan includes destroy or replace actions.
5. Maintain independent backups and test recovery.
6. Log the actor, reason, timestamp, and outcome of every protection state change.

## 8. Controlled VM Deletion Workflow

Delete locks do not mean a machine will never be deleted. Old, faulty, or superseded machines still need to be decommissioned properly. A sound workflow clarifies the reason, scope, and recoverability before removing locks.

~~~mermaid
flowchart TD
    A["Request to delete or replace VM"] --> B["Verify exact resource and owner"]
    B --> C["Check workloads, dependencies, and data"]
    C --> D["Confirm backups and rollback plan"]
    D --> E["Review / approve change"]
    E --> F["Temporarily remove lock under granted permissions"]
    F --> G["Delete VM or execute replacement"]
    G --> H["Verify status of disks, IPs, and related resources"]
    H --> I["Update inventory, audit logs, and ticket"]
~~~

Steps to follow:

1. **Verify identity:** check account/project/subscription, region/zone, machine name, ID, environment, and owner. Never rely solely on display names.
2. **Check dependencies:** identify what traffic the machine serves and any attached load balancers, disks, IPs, monitoring, or scheduled jobs.
3. **Assess data:** confirm what data must be kept, latest backup, restore capability, and retention duration.
4. **Choose action:** stop, detach, rebuild, replace, or delete. Pick the least disruptive action that meets the objective.
5. **Obtain approval:** require an authorized reviewer to confirm the target resource and execution window. For critical systems, require peer review.
6. **Temporarily remove protection:** only authorized personnel may disable deletion protection or remove a resource lock. Record the reason and time window.
7. **Execute and verify:** verify the operation result and the status of disks, IPs, backups, and dependent resources.
8. **Restore guardrails:** if the machine still exists or a replacement was created, re-enable protection on the new resource per baseline.
9. **Record:** update inventory, tickets, change logs, and records of reclaimed resources.

When replacing a production machine, deploy the new machine from a tested image/template, verify health checks, shift traffic incrementally, and only then delete the old machine. This preserves a rollback path if the new machine misbehaves.

## 9. Auditing and Detecting Anomalous Changes

A protection mechanism is only effective when the organization tracks its status and detects when it is removed.

Monitor:

- Which production machines lack deletion/termination protection.
- Which resource locks have been removed or modified.
- Who modified protection attributes, IAM roles, or policies.
- Requests to delete VMs, disks, snapshots, and backups.
- Destroy/replace operations in IaC pipelines.
- Changes occurring out-of-process or outside approved windows.

Use provider audit logs, event rules, policy compliance tools, or a SIEM system to detect changes. Alerts should include the resource details, acting identity, action taken, timestamp, and runbook link.

Review protection coverage on a schedule and after major deployments. A compliance dashboard can categorize machines by environment, owner, criticality, and guardrail status. Tags such as `Environment=production` or `Criticality=high` aid classification, though tags only provide real protection when paired with policy enforcement or controlled automation.

## 10. Limitations and Common Misconceptions

**Assuming delete locks protect data:** locks do not stop bad writes, malware, file deletions inside the guest OS, or filesystem corruption. Maintain backups and test restores.

**Assuming protecting a VM protects its disks:** disks can be independent resources with separate lifecycle policies. Check the delete behavior of boot and data disks, and protect critical disks/snapshots individually.

**Assuming admins cannot remove locks:** many mechanisms allow users with the right permissions to turn off protection or delete locks. Restrict guardrail-removal permissions as well.

**Putting ReadOnly on everything:** read-only locks can block valid updates, breaking agents, pipelines, and operational workflows. For anti-deletion goals, consider delete-only locks first.

**Forgetting autoscaling and managed services:** managed machine groups may have separate scale-in, replacement, or reclamation mechanics. Check the orchestrator's policies instead of relying solely on per-VM flags.

**Using IaC guardrails as the sole protection:** `prevent_destroy` stops certain Terraform plans but does not block direct deletion via console or API. Enforce cloud-layer guardrails and access controls as well.

**Removing a lock and forgetting to re-enable it:** after maintenance or replacement, protection state can be overlooked. Add guardrail restoration to checklists and automated compliance checks.

**Treating snapshots as complete backups:** snapshots may be inconsistent with an actively writing application unless coordinated with freeze/quiesce or an application-aware backup mechanism. Test restores at the application level.

## 11. Production Machine Protection Checklist

- [ ] Machine is classified by environment, criticality, and owner.
- [ ] Deletion/termination protection is enabled and verified via API/CLI.
- [ ] Critical disks and snapshots have dedicated protection policies.
- [ ] IAM/RBAC restricts VM, disk, and snapshot deletion as well as lock removal.
- [ ] Sensitive administrative privileges require strong authentication and periodic review.
- [ ] IaC plans containing destroy/replace operations require review and approval.
- [ ] Backups meet RPO/RTO targets and have been restore-tested.
- [ ] An audited break-glass procedure exists for emergencies.
- [ ] Alerts trigger when protection settings or resource locks change.
- [ ] Checklists cover removing locks, performing changes, and re-enabling guardrails.
- [ ] Autoscaling and managed service policies have been verified.
- [ ] Inventory accurately reflects current protection status.

Delete locks reduce the chance of losing machines to unintended management actions. To genuinely protect workloads, combine resource-level guardrails, IAM/RBAC permissions, IaC change controls, auditing, and independent backups. When deletion or replacement is necessary, verify the exact resource, assess data and dependencies, obtain approval, temporarily remove locks, and restore protection policies once complete.
