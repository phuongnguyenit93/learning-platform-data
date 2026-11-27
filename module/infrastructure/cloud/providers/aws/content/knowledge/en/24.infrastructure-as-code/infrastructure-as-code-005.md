# DeletionPolicy, UpdateReplacePolicy, and Data Resource Protection

An AWS CloudFormation stack manages an e-commerce system: Amazon S3 stores invoices, Amazon DynamoDB stores orders, and Amazon RDS stores payment data. After a few months, the development team needs to change database settings, split stacks, or remove an unused resource. A seemingly small update can cause CloudFormation to replace a resource and delete the old physical resource. Without lifecycle policies designed upfront, critical data can vanish with the stack or during an update.

CloudFormation provides two attributes to decide what happens to a resource when it is deleted or replaced:

- **DeletionPolicy** controls how CloudFormation handles a resource when deleting the stack or when the resource is removed from the template during a stack update.
- **UpdateReplacePolicy** controls how CloudFormation handles the old physical resource when a change forces the resource to be replaced with a new physical resource.

These two attributes are template-level lifecycle protections. To protect production data, combine them with backups/PITR, versioning, deletion protection, stack policies, termination protection, and IAM.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_PROVIDERS_AWS** module. It focuses on predicting CloudFormation behavior, choosing policies for S3/DynamoDB/RDS/EBS, reading change sets, handling retained resources, and designing safe change workflows.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the difference between DeletionPolicy and UpdateReplacePolicy.
2. Distinguish three scenarios: deleting a stack, removing a resource from a template, and replacing a resource during an update.
3. Choose Delete, Retain, RetainExceptOnCreate, or Snapshot for the right context.
4. Understand why Snapshot applies only to specific resource types.
5. Configure policies for S3 buckets, DynamoDB tables, and RDS DB instances.
6. Explain the impact of retained resources on CloudFormation ownership and cost.
7. Combine policies with RDS deletion protection, DynamoDB PITR, S3 Versioning/Object Lock, and EBS snapshots.
8. Distinguish stack policies, termination protection, and IAM.
9. Use change sets to identify replacements before deploying.
10. Design backup, update, rollback, and recovery workflows when data loss risks exist.

## 2. How CloudFormation Manages Logical Resources and Physical Resources

In a template, you declare a resource using a logical ID, such as ProductionDatabase. When creating the stack, CloudFormation provisions the actual resource in AWS and associates a physical ID with it, such as a DB instance identifier or bucket name.

Distinguish between:

- **Logical ID:** resource name inside the template, referenced by other resources.
- **Physical resource:** actual resource existing in AWS.
- **Physical ID:** identifier of the actual resource.
- **Stack ownership:** management relationship between the resource and the CloudFormation stack.

When updating a template, CloudFormation compares the new template with stack state. Depending on which property changed, the resource may be updated in place or require replacement.

If updated in place, the physical ID is usually preserved. If replaced, CloudFormation creates a new resource with a new physical ID, updates dependent references, and handles the old resource according to UpdateReplacePolicy.

If a resource is Retained, it still exists in AWS but is removed from the stack's management scope. Keeping the resource does not mean CloudFormation continues managing it.

## 3. Three Lifecycle Scenarios to Distinguish

| Scenario | CloudFormation action | Governing policy |
|---|---|---|
| Delete the entire stack | Deletes resources belonging to the stack per their policies | DeletionPolicy |
| Remove a resource from the template and update stack | Resource is no longer declared in the new template | DeletionPolicy |
| Change a property requiring Replacement | Creates new resource, shifts references, handles old resource | UpdateReplacePolicy |
| Change a property updated in place | Updates existing resource | Neither policy is triggered |

The easiest mistake to make is thinking **DeletionPolicy protects the old resource during a replacement operation**. If a property change requires Replacement, use UpdateReplacePolicy.

Conversely, UpdateReplacePolicy does not govern what happens when deleting a stack. When deleting a stack, CloudFormation uses DeletionPolicy.

## 4. DeletionPolicy

DeletionPolicy is an attribute placed directly on a resource in the template. It controls whether to retain, snapshot, or delete the resource when CloudFormation deletes the stack or removes the resource from the template during a stack update.

Example retaining an S3 bucket when the stack is deleted:

    Resources:
      InvoiceBucket:
        Type: AWS::S3::Bucket
        DeletionPolicy: Retain

When stack deletion completes, the bucket remains. When an update removes InvoiceBucket from the template, CloudFormation also retains the bucket and removes that resource from the stack's management scope.

### 4.1. DeletionPolicy Values

| Value | Behavior | When appropriate |
|---|---|---|
| Delete | Deletes the physical resource | Ephemeral resources, recreatable data |
| Retain | Keeps the resource and its contents, removes it from the stack | Buckets, databases, or resources needing to outlive the stack |
| RetainExceptOnCreate | Same as Retain, except during rollback of initial creation | Newly created resources when stack creation fails |
| Snapshot | Creates a snapshot before deletion, if supported by resource | Volumes/databases needing a backup at deletion time |

If DeletionPolicy is omitted, the default is Delete, except:

- AWS::RDS::DBCluster defaults to Snapshot.
- AWS::RDS::DBInstance without DBClusterIdentifier defaults to Snapshot.

Do not rely on default exceptions for production data resources. Declaring policies explicitly helps reviewers understand intent and avoids depending on differing defaults across resource types.

### 4.2. RetainExceptOnCreate

RetainExceptOnCreate is useful when a template creates a new data resource yet initial stack creation might roll back.

For example, a pipeline creates a new stack and provisions a bucket. If creation fails, the newly created bucket is likely empty and unused by the application. With Retain, that bucket would be left behind after rollback, creating an orphaned resource. RetainExceptOnCreate lets CloudFormation delete the resource during rollback of the initial create operation itself, while retaining the resource in all subsequent stack operations.

    Resources:
      NewImportBucket:
        Type: AWS::S3::Bucket
        DeletionPolicy: RetainExceptOnCreate

RetainExceptOnCreate is a value for DeletionPolicy; it is not a value for UpdateReplacePolicy.

### 4.3. Snapshot

Snapshot creates a data snapshot of the resource before CloudFormation deletes it. The snapshot exists independently after stack deletion finishes and continues incurring storage charges until deleted.

DeletionPolicy Snapshot currently supports resource types listed by AWS such as:

- AWS::DocDB::DBCluster
- AWS::EC2::Volume
- AWS::ElastiCache::CacheCluster
- AWS::ElastiCache::ReplicationGroup
- AWS::Neptune::DBCluster
- AWS::RDS::DBCluster
- AWS::RDS::DBInstance
- AWS::Redshift::Cluster

Never assume every resource supports snapshots. For instance, a DynamoDB table does not use DeletionPolicy Snapshot; use Retain along with DynamoDB Point-in-Time Recovery or appropriate backups.

## 5. UpdateReplacePolicy

UpdateReplacePolicy controls the fate of the **old physical resource** when a stack update requires CloudFormation to replace the resource.

For example, some property changes on an RDS DB instance require Replacement. CloudFormation creates a new DB instance, updates dependent references to the new resource, and then processes the old instance.

    Resources:
      ProductionDatabase:
        Type: AWS::RDS::DBInstance
        DeletionPolicy: Retain
        UpdateReplacePolicy: Retain
        Properties:
          # Database properties are declared here

Here the two policies protect two different events:

- DeletionPolicy Retain keeps the database if the stack is deleted or the resource is removed from the template.
- UpdateReplacePolicy Retain keeps the old database if an update forces CloudFormation to replace it.

### 5.1. UpdateReplacePolicy Values

| Value | Behavior when resource is replaced |
|---|---|
| Delete | Deletes the old physical resource |
| Retain | Keeps the old physical resource, removes it from the stack |
| Snapshot | Creates a snapshot of the old resource if supported, then deletes the old resource |

If UpdateReplacePolicy is omitted, the default is Delete. There is no RetainExceptOnCreate value for this attribute.

If Snapshot is declared on a resource that does not support snapshots, CloudFormation falls back to the default Delete behavior. Therefore, do not apply Snapshot blindly as a generic policy across all resources.

The AWS-documented list of resources supporting UpdateReplacePolicy Snapshot includes:

- AWS::EC2::Volume
- AWS::ElastiCache::CacheCluster
- AWS::ElastiCache::ReplicationGroup
- AWS::Neptune::DBCluster
- AWS::RDS::DBCluster
- AWS::RDS::DBInstance
- AWS::Redshift::Cluster

This list differs from the DeletionPolicy Snapshot list; for example, AWS::DocDB::DBCluster is in the DeletionPolicy list but not in the current UpdateReplacePolicy list. Check the attribute documentation for the exact event you need to protect.

## 6. Decision Table: Which Policy to Choose?

| Resource and purpose | DeletionPolicy | UpdateReplacePolicy |
|---|---|---|
| S3 bucket storing invoices requiring long-term retention | Retain | Retain |
| DynamoDB table storing orders | Retain | Retain |
| RDS database needing data preserved on delete/replacement | Snapshot or Retain per workflow | Snapshot or Retain per workflow |
| EBS volume needing data preserved for recovery | Snapshot or Retain | Snapshot or Retain |
| Log bucket in test environment with clear lifecycle | Delete | Delete |
| New bucket created in a stack that may roll back on create failure | RetainExceptOnCreate | Retain or Delete depending on replacement needs |

There is no single policy right for every resource. Decide based on data value, recreatability, retention period, cost, audit requirements, and recovery procedures.

## 7. Protecting Amazon S3 Buckets

An S3 bucket can hold data whose lifecycle outlives the application or stack. A baseline configuration:

    Resources:
      InvoiceBucket:
        Type: AWS::S3::Bucket
        DeletionPolicy: Retain
        UpdateReplacePolicy: Retain
        Properties:
          VersioningConfiguration:
            Status: Enabled
          BucketEncryption:
            ServerSideEncryptionConfiguration:
              - ServerSideEncryptionByDefault:
                  SSEAlgorithm: AES256
          PublicAccessBlockConfiguration:
            BlockPublicAcls: true
            IgnorePublicAcls: true
            BlockPublicPolicy: true
            RestrictPublicBuckets: true

### 7.1. Versioning and Retain Solve Different Problems

- Versioning keeps multiple versions of an object, allowing recovery of overwritten or accidentally deleted objects.
- DeletionPolicy Retain keeps the bucket when the stack or resource is removed from CloudFormation.
- UpdateReplacePolicy Retain keeps the old bucket when CloudFormation replaces the bucket.
- Encryption protects stored data, but does not prevent deletion.
- Lifecycle policies manage old version lifecycles and storage costs.

Versioning does not prevent all forms of permanent deletion. Principals with appropriate permissions can still delete a specific version. For data requiring time-bound immutability, see S3 Object Lock.

### 7.2. Object Lock

S3 Object Lock provides a WORM (write once, read many) model protecting object versions from deletion or overwrite during a retention period. Object Lock requires Bucket Versioning.

Two common modes:

- **Governance mode:** most principals cannot delete or alter retention; principals with special bypass permissions can override governance retention.
- **Compliance mode:** an object version cannot be deleted or have its retention period shortened by any user, including the account root user, during the protection period.

Legal hold has no automatic expiration date; it remains until removed. Retention and legal hold apply to specific object versions. They do not prevent a new version or delete marker from being created on the same key.

Object Lock does not replace DeletionPolicy. DeletionPolicy preserves the bucket resource; Object Lock protects object versions inside the bucket.

### 7.3. Non-Empty S3 Buckets Cannot Be Deleted Directly

S3 only allows deleting empty buckets. If DeletionPolicy or UpdateReplacePolicy is Delete yet the bucket still contains objects, the delete operation can fail. For versioned buckets, object versions and delete markers must also be handled properly.

Do not design pipelines assuming CloudFormation automatically purges all objects. If data must be kept, use Retain; if deletion is intended, build a controlled archive/empty step with approval.

### 7.4. Bucket Names and Replacement

If a template declares an explicit BucketName, CloudFormation cannot replace the bucket with the same globally unique name. AWS requires a new name when replacement is needed. UpdateReplacePolicy Retain does not resolve bucket name collisions.

When changing configurations that force replacement, design a destination bucket with a unique name, copy data, update application/DNS/policy references, verify data, and only then handle the old bucket.

## 8. Protecting Amazon DynamoDB Tables

DynamoDB tables do not support DeletionPolicy Snapshot according to CloudFormation's snapshot-supported resource list. For critical tables, Retain is typically combined with Point-in-Time Recovery (PITR).

    Resources:
      OrdersTable:
        Type: AWS::DynamoDB::Table
        DeletionPolicy: Retain
        UpdateReplacePolicy: Retain
        Properties:
          BillingMode: PAY_PER_REQUEST
          AttributeDefinitions:
            - AttributeName: pk
              AttributeType: S
          KeySchema:
            - AttributeName: pk
              KeyType: HASH
          PointInTimeRecoverySpecification:
            PointInTimeRecoveryEnabled: true
            RecoveryPeriodInDays: 35

PITR provides continuous backups managed by DynamoDB. The recovery period is configurable from 1 to 35 days; it defaults to 35 days if unspecified. When restoring, DynamoDB creates a new table rather than overwriting the source table.

### 8.1. Choosing Protection Mechanisms

- Retain protects the table from CloudFormation deleting it when the stack/resource is removed.
- UpdateReplacePolicy Retain preserves the old table if an update requires replacement.
- PITR protects data against accidental writes/deletes within the recovery window.
- On-demand backups suit specific backup milestones or separate retention requirements.
- IAM restricts which principals can delete tables, modify backups, or disable PITR.

PITR does not replace DeletionPolicy. Conversely, Retain does not help recover an item overwritten or deleted inside a still-active table. The two mechanisms address two different types of risk.

## 9. Protecting Amazon RDS Databases

RDS offers multiple layers of protection:

- DeletionPolicy decides whether the resource is retained, deleted, or snapshotted on stack/resource deletion.
- UpdateReplacePolicy decides the fate of the old DB instance on replacement.
- DeletionProtection blocks database deletion while enabled.
- BackupRetentionPeriod configures how long automated backups are kept for eligible DB instances.
- Manual snapshots provide an independent recovery point.

Example fragment for an RDS DB instance:

    Resources:
      ProductionDatabase:
        Type: AWS::RDS::DBInstance
        DeletionPolicy: Snapshot
        UpdateReplacePolicy: Snapshot
        Properties:
          Engine: mysql
          DBInstanceClass: db.t3.micro
          AllocatedStorage: "20"
          MasterUsername: dbadmin
          ManageMasterUserPassword: true
          StorageEncrypted: true
          BackupRetentionPeriod: 7
          DeletionProtection: true

This is an illustrative fragment. In a real stack, also declare networking/subnet/security groups, tags, engine version, and properties appropriate for the engine, Region, workload, and security standards.

### 9.1. DeletionProtection Is Not DeletionPolicy

DeletionProtection is an RDS-level attribute. When enabled, RDS forbids deleting the database. If CloudFormation needs to delete the resource, the operation may fail until deletion protection is intentionally turned off.

DeletionPolicy Snapshot does not automatically disable DeletionProtection. When a protected database must be deleted, the workflow must be controlled: confirm backups, toggle DeletionProtection, review the change set, and execute deletion with approval.

For Aurora, deletion protection is managed on the DB cluster. Member DB instances do not use the DeletionProtection property the same way standalone DB instances do.

### 9.2. Replacement Can Cause Data Loss

AWS recommends taking a database snapshot before updating a stack if a change requires replacement. For RDS DB instances, certain properties have Replacement update behavior. Check the Update requires column in the resource reference for each property.

During replacement, CloudFormation creates a new DB instance, shifts dependencies, and deletes the old instance. Automated snapshots may be deleted when a DB instance is deleted or replaced; manual snapshots are kept. Never rely on automated backups as the sole safety net for a critical replacement.

### 9.3. Snapshots and Recovery

A snapshot only creates a recovery point; it does not automatically cut over the application to the new database or verify data correctness. After taking a snapshot, identify:

1. Snapshot identifier and creation timestamp.
2. KMS key encrypting the snapshot and key access permissions.
3. How to restore into a new DB instance/cluster.
4. How to switch application endpoints/secrets/configs.
5. How to verify data, schema, and access permissions.
6. When the old database is permitted to be deleted.

Snapshots and retained DBs continue incurring costs until deleted.

## 10. Protecting Amazon EBS Volumes

EBS volumes hold filesystems, database files, or application data attached to EC2. If a stack deletes a volume, data can be lost with the volume lifecycle.

Example:

    Resources:
      DataVolume:
        Type: AWS::EC2::Volume
        DeletionPolicy: Snapshot
        UpdateReplacePolicy: Snapshot
        Properties:
          AvailabilityZone: !Ref AvailabilityZone
          Size: 100
          VolumeType: gp3
          Encrypted: true

A Snapshot policy preserves a volume snapshot prior to deletion or replacement. However, a snapshot of an actively written volume does not automatically guarantee application consistency. For databases or multi-volume filesystems, quiesce writes, flush data, or use an appropriate application-consistent backup workflow.

## 11. Stack Policies to Protect Resources from Unintended Updates

DeletionPolicy and UpdateReplacePolicy dictate how resources are handled when CloudFormation deletes or replaces them. They do not block all stack updates.

A **stack policy** is a JSON policy attached to a stack to deny specific update actions on protected logical resources. For example, allow updating other resources while blocking replacement and deletion of ProductionDatabase:

    {
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "Update:*",
          "Principal": "*",
          "Resource": "*"
        },
        {
          "Effect": "Deny",
          "Action": [
            "Update:Replace",
            "Update:Delete"
          ],
          "Principal": "*",
          "Resource": "LogicalResourceId/ProductionDatabase"
        }
      ]
    }

Common actions:

| Action | Meaning |
|---|---|
| Update:Modify | Property change, with no interruption or partial interruption |
| Update:Replace | Creates a new resource replacing the current resource |
| Update:Delete | Removes the resource from the stack |
| Update:* | All update actions |

Stack policies apply only during stack updates. They do not replace IAM policies and do not prevent someone from calling service APIs to modify resources directly. Once a stack policy is attached, updates not explicitly allowed are denied; Deny always overrides Allow.

## 12. Termination Protection and IAM

Two additional protective layers commonly used for production stacks:

### 12.1. Termination Protection

Termination protection blocks deleting the entire stack. This feature is disabled by default. When enabled, `DeleteStack` requests fail and the stack remains unchanged.

It can be enabled via the AWS CLI:

    aws cloudformation update-termination-protection \
      --stack-name production-data \
      --enable-termination-protection

Termination protection only guards against deleting the stack. It does not stop a stack update from removing a resource from the template. If an update removes a resource, DeletionPolicy still determines that resource's behavior.

### 12.2. IAM

IAM controls which principals are allowed to invoke CloudFormation and service APIs. Apply least privilege for actions such as UpdateStack, DeleteStack, SetStackPolicy, UpdateTerminationProtection, DeleteDBInstance, DeleteTable, DeleteBucket, and related backup/restore permissions.

Stack policies are a guardrail in the update workflow. IAM is the access control layer. Both must be designed together.

## 13. Comparing Protection Mechanisms

| Mechanism | What does it protect? | What does it NOT protect? |
|---|---|---|
| DeletionPolicy | Resources when stack is deleted or removed from template | Replacement due to property updates |
| UpdateReplacePolicy | Old physical resource during replacement | Stack deletion |
| Resource deletion protection | Prevents the service from deleting the resource when enabled | Data loss from object/item writes or deletes |
| Stack policy | Specific update actions on resources in the stack | DeleteStack or direct calls via service APIs |
| Termination protection | Deleting the entire stack | Resource removal via stack update |
| IAM | Who can call which API/action | Logical mistakes by an authorized principal |
| Backup/PITR/Versioning | Data recovery capability | Does not automatically block resource deletion operations |

No single attribute provides complete data protection. Combine the lifecycle layer, permissions layer, backup layer, and operational layer.

## 14. Change Set Review Process Before Updating

Before deploying a template that changes data resources:

1. Create a change set for the existing stack.
2. Read the list of resources to be Added, Modified, Removed, or Replaced.
3. Find every data resource marked for Replacement.
4. Open the resource reference to confirm which property requires Replacement.
5. Check DeletionPolicy and UpdateReplacePolicy on that resource.
6. Verify snapshots/PITR/versioning and KMS keys are accessible.
7. Check whether a stack policy blocks the update.
8. Estimate costs for retained resources and snapshots.
9. Confirm the application can cut over to the new resource.
10. Execute the change set only after review and approval.

Change sets help predict changes, yet do not guarantee an update will succeed. Some failures appear only during execution, such as quotas, dependencies, permissions, duplicate resource names, or enabled resource deletion protection.

## 15. Retained Resources: Managing After Detaching from the Stack

When CloudFormation Retains a resource:

- The physical resource still exists in the account and Region.
- The resource is no longer under the old stack's management scope.
- The resource continues incurring costs.
- The stack will not automatically update that resource in subsequent updates.
- To manage it again with CloudFormation, use the resource import workflow if the resource type supports it and meets import conditions.

After retaining, record the physical ID, ARN, Region, owner, data, backup policy, KMS key, and operational procedures. Add tags indicating ownership status to prevent forgotten orphaned resources.

Do not treat Retain as a cleanup operation. It transfers resource management responsibility to another process or owner.

## 16. Real-World Scenarios

### Scenario A — Deleting Application Stack While Keeping Invoice Bucket

An application stack is about to be decommissioned, yet invoices must be preserved.

**Solution:** Set DeletionPolicy Retain on the bucket. Enable Versioning and an appropriate lifecycle policy. After stack deletion, verify the bucket still exists, assign a new owner, and monitor costs.

### Scenario B — Property Change Causes RDS Replacement

A property on the DB instance has Replacement update behavior.

**Solution:** Create a restorable snapshot/backup, set UpdateReplacePolicy Snapshot or Retain per workflow, inspect the change set, prepare endpoint cutover, and keep the old resource until new data is verified.

### Scenario C — Removing a DynamoDB Table from a Template

The development team moves a table into a separate stack.

**Solution:** Use DeletionPolicy Retain so the table is not deleted when removed from the old template. Then import the table into the new stack if the resource type and state meet import requirements. Verify PITR and permissions before/after the move.

### Scenario D — Stack Creation Fails After Creating a Bucket

A pipeline creates a bucket, then another resource errors and triggers stack rollback.

**Solution:** If the new bucket does not need to survive a create rollback, use RetainExceptOnCreate. If data could already have been written to the bucket during bootstrapping, evaluate carefully before choosing it.

### Scenario E — S3 Bucket Cannot Be Deleted

A change set plans to delete a bucket, yet the bucket still contains object versions.

**Solution:** Check data policy, archiving/retention, and handle versions/delete markers per workflow. If the bucket must be kept, change its policy to Retain via a reviewed stack update. Never bulk-delete objects merely to make stack deletion succeed.

### Scenario F — RDS DeletionProtection Is Enabled

CloudFormation needs to delete a database, yet RDS rejects it due to deletion protection.

**Solution:** Verify backups and approvals, disable deletion protection via a controlled change, and then perform deletion with the appropriate DeletionPolicy. Never remove protection just to clear a pipeline error without verifying data.

### Scenario G — UpdateReplacePolicy Snapshot on an Unsupported Resource

A resource outside the snapshot-supported list declares UpdateReplacePolicy Snapshot.

**Solution:** CloudFormation falls back to Delete on replacement. Choose Retain or a service-specific backup mechanism; do not rely on Snapshot if the resource does not support it.

## 17. Production Data Protection Checklist

- [ ] Every S3 bucket holding critical data has an appropriate DeletionPolicy.
- [ ] Resources subject to replacement have an evaluated UpdateReplacePolicy.
- [ ] Snapshot is not used on unsupported resources.
- [ ] S3 Versioning is enabled when object version recovery is needed.
- [ ] S3 Object Lock is used when WORM/immutable retention is required.
- [ ] DynamoDB PITR is enabled with a recovery period meeting RPO.
- [ ] RDS automated backups and manual snapshots have clear retention.
- [ ] RDS DeletionProtection is enabled on critical databases.
- [ ] Critical EBS volumes have application-consistent backups/snapshots.
- [ ] KMS keys for backups/snapshots are protected with restore permissions verified.
- [ ] Stack policies block unintended replacement/deletion on critical resources.
- [ ] Termination protection is enabled on production stacks needing protection.
- [ ] IAM restricts permissions to delete stacks, tables, buckets, databases, and backups.
- [ ] Change sets are reviewed before changes that may trigger Replacement.
- [ ] Retained resources have an owner, tags, inventory, and cost plan.
- [ ] Restore, cutover, and post-recovery cleanup have been rehearsed.

## 18. Review Questions

1. In which scenarios does DeletionPolicy apply?
2. When does UpdateReplacePolicy apply?
3. Does an in-place property update trigger either of these two policies?
4. If DeletionPolicy is omitted, what is the usual default behavior?
5. Which two RDS resource types have a special default DeletionPolicy of Snapshot?
6. Does Retain delete the resource from AWS?
7. When Retained, does the resource remain under the stack's management scope?
8. How does RetainExceptOnCreate handle a stack create rollback?
9. Does UpdateReplacePolicy support RetainExceptOnCreate?
10. Does Snapshot apply to all CloudFormation resources?
11. Why does DeletionPolicy not protect the old resource during replacement?
12. Why is UpdateReplacePolicy needed for databases?
13. What problem does S3 Versioning solve?
14. Which feature must be enabled on a bucket for S3 Object Lock?
15. How does Object Lock Compliance mode differ from Governance mode?
16. Why does Retain not replace DynamoDB PITR?
17. Up to how many days can DynamoDB PITR restore?
18. Can RDS DeletionProtection cause stack deletion to fail?
19. Does a stack policy replace IAM?
20. Does termination protection block a stack update from deleting a resource removed from the template?
21. Why can a non-empty S3 bucket fail to delete when policy is Delete?
22. What behavior results from setting UpdateReplacePolicy Snapshot on an unsupported resource?
23. What kinds of changes does a change set help detect?
24. Do retained resources continue incurring charges?
25. When should RetainExceptOnCreate be used?

**Quick answers:** (1) stack deletion and resource removal during updates; (2) replacement; (3) no; (4) Delete, except for the noted RDS exceptions; (5) DBCluster and DBInstance without DBClusterIdentifier; (6) no; (7) no; (8) deletes the newly created resource when rolling back the initial create operation; (9) no; (10) no; (11) replacement uses UpdateReplacePolicy; (12) retains or snapshots the old physical database; (13) stores multiple object versions; (14) Versioning; (15) Governance allows special bypass permissions, while Compliance cannot be bypassed during retention; (16) Retain does not restore data-level changes; (17) 35 days; (18) yes; (19) no; (20) no; (21) S3 only deletes empty buckets; (22) falls back to Delete; (23) Add/Modify/Remove/Replace; (24) yes; (25) when a new resource should be deleted if stack creation rolls back, yet retained in subsequent deletions.

## 19. Summary

DeletionPolicy and UpdateReplacePolicy govern two different moments in the CloudFormation lifecycle:

- DeletionPolicy applies when deleting a stack or removing a resource from a template.
- UpdateReplacePolicy applies when an update forces a resource to be replaced.
- Delete removes the resource; Retain keeps the resource outside the stack; Snapshot creates a snapshot if the resource supports it.
- RetainExceptOnCreate belongs only to DeletionPolicy and is useful for initial stack create rollbacks.
- RDS, DynamoDB, S3, and EBS must combine policies with service-native backups and protections.
- Stack policies guard updates; termination protection guards stack deletion; IAM controls who can call APIs.
- Retained resources and snapshots continue incurring charges and require owner management.
- Always review change sets, verify replacement behavior, and test restores before modifying production data resources.

A safe IaC design makes clear **which resources are permitted to be deleted, which data must be preserved, what replacement will create, and who owns recovery**.

### Official AWS Documentation

1. DeletionPolicy attribute: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-deletionpolicy.html
2. UpdateReplacePolicy attribute: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-attribute-updatereplacepolicy.html
3. CloudFormation best practices: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html
4. Prevent updates to stack resources: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html
5. Protect CloudFormation stacks from being deleted: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-protect-stacks.html
6. AWS::RDS::DBInstance resource: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-rds-dbinstance.html
7. DynamoDB point-in-time recovery: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html
8. DynamoDB PointInTimeRecoverySpecification: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-dynamodb-table-pointintimerecoveryspecification.html
9. AWS::S3::Bucket resource: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3-bucket.html
10. S3 Object Lock: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
11. Deleting an Amazon RDS DB instance: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html
12. Amazon DynamoDB backup and restore: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Backup-and-Restore.html
