# Service Catalog and approved infrastructure catalogs

In an AWS environment with multiple development teams, each team may need to create servers, databases, networks, storage buckets, or deployment pipelines. If every team designs and provisions resources their own way, the organization struggles to ensure consistent security configurations, trace accountability, and avoid unexpected costs. Conversely, if every request must wait for an operations team to provision resources manually, development velocity slows down and the operations team becomes a bottleneck.

AWS Service Catalog solves this problem by providing a catalog of IT services and infrastructure templates prepared, reviewed, and approved by the organization for use. Authorized users can select an appropriate product themselves and deploy it within constrained parameters. Through this, the organization standardizes how resources are created on AWS, assigns permissions by group, distributes shared templates across multiple accounts, and preserves audit trails.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, Service Catalog can package standardized configurations for Regions/AZs, IAM, VPCs, compute, storage, databases, integration, and serverless. The catalog is part of a governance model: it guides users along an approved path, while IAM, AWS Organizations, AWS Config, CloudTrail, and other security mechanisms provide additional layers of control and evidence.

## 1. What problem does AWS Service Catalog solve?

AWS Service Catalog is a service for managing a catalog of IT products approved for deployment on AWS. A product can be a single resource or a multi-resource interconnected system. Examples:

- An S3 bucket with encryption, versioning, and public access block enabled.
- A VPC with public and private subnets, route tables, NAT Gateway, and standardized security groups.
- A database cluster with appropriate backup, encryption, monitoring, and connection parameter settings.
- An application environment consisting of compute, load balancer, logging, and required networking components.

Without a catalog, each team may write their own templates, pick instance sizes arbitrarily, configure permissions ad hoc, or forget to apply tags. With a well-governed catalog, the platform team can publish vetted templates, while application teams simply choose a template, fill in allowed parameters, and deploy using granted permissions.

Service Catalog is useful when an organization needs:

1. **Standardization:** reuse vetted platform templates and configurations.
2. **Controlled self-service:** allow project teams to deploy without granting them full AWS administrative permissions.
3. **Audience-based distribution:** offer different portfolios for development, data, operations, or production environments.
4. **Lifecycle management:** release new versions, update running products, and retire older versions through a controlled process.
5. **Traceability:** link products, versions, deployment permissions, tags, and provisioning events to audit workflows.

Service Catalog does not automatically turn every resource in an account into an approved resource. Users can still create resources directly via APIs or other AWS services if IAM and organizational guardrails allow it. Therefore, the catalog must be combined with IAM, Service Control Policies (SCPs), AWS Config, CloudTrail, and change management workflows.

## 2. Core concepts

| Component | Meaning | Governance question to answer |
|---|---|---|
| **Product** | A deployable service or infrastructure template, typically defined by a CloudFormation or Terraform template supported by Service Catalog | Does the template meet security, operational, and cost baselines? |
| **Product version** | A version of the product template and configuration | Which version has been tested and approved for release? |
| **Portfolio** | A collection of products intended for a user group or use case | Which groups can view and deploy which products? |
| **Provisioned product** | An instance of a product deployed by a user whose lifecycle is managed by Service Catalog | Who created it, which version is running, and which resources belong to this instance? |
| **Constraint** | A rule limiting how a product is deployed within a specific portfolio | To what extent can users choose parameters, permissions, and deployment behavior? |
| **TagOption** | A key-value pair managed in Service Catalog's TagOption library to standardize tag choices | Which tag values are permitted when provisioning a product? |
| **Principal** | An IAM user, group, or role granted access to a portfolio | Which identities are permitted to use the catalog? |

### Products and provisioned products are not the same

A product is a reusable definition, such as a template creating a standardized S3 bucket. When a user deploys a product, Service Catalog creates a **provisioned product**. You can think of a product as a blueprint and a provisioned product as a concrete deployment of that blueprint.

For CloudFormation-based products, a provisioned product typically corresponds to a CloudFormation stack containing the resources declared in the template. For Terraform-based products, Service Catalog uses the provisioning mechanism corresponding to that product type. Therefore, do not assume every provisioned product is a CloudFormation stack.

One product can be added to multiple portfolios. This lets an organization reuse the same template while distributing it to different groups with separate permissions and constraints. For example, an application environment product can appear in both Development and Production portfolios; the Production portfolio can restrict parameters more tightly and use a different launch role.

### Portfolios and access permissions

A portfolio is the organization and distribution layer for products. Administrators can create portfolios by function, business unit, environment, or risk tier, for example:

- **Developer Sandbox:** experimental templates with small sizes, short lifetimes, and cost limits.
- **Application Platform:** VPCs, compute, load balancers, and logging per platform team standards.
- **Data Platform:** buckets, databases, and data pipelines with encryption, backups, and data classification.
- **Production Services:** operationally tested templates with monitoring, backups, and change approval requirements.

When an IAM principal is granted portfolio access and holds the required Service Catalog permissions, the user can browse and deploy products offered in that portfolio. Permissions to view or deploy from the catalog must still be granted via IAM; knowing a product's name does not mean a user is allowed to use that product.

### Product versions and lifecycle

A product can have multiple versions reflecting changes in templates, patches, security configurations, or architecture. When an administrator adds a version to a product, the new version becomes available to users who currently have access to the product. Publishing a new version does not mean all running provisioned products are automatically updated. Administrators must decide how and when to update existing instances, test impact, and track results.

A versioning process should have an owner, change notes, test results, release date, and deprecation plan. If a critical bug is discovered, administrators can stop offering that version for new deployments using the product's version management capabilities, then plan how to remediate running instances using the affected version.

## 3. How Service Catalog controls deployments

Service Catalog coordinates multiple control layers. Each layer answers a different question: who can use the catalog, which permissions create resources, which parameters may be chosen, and where deployment events are sent.

### 3.1. IAM: who administers and who uses?

Two permission groups should be separated:

- **Catalog administrator:** creates products and versions, manages portfolios, assigns principals, configures constraints, TagOptions, and shares portfolios.
- **End user:** views authorized products, deploys, updates, or terminates provisioned products within permitted boundaries.

Do not grant catalog administration permissions to all end users. Use role-based IAM roles, IAM groups, or centralized identity mechanisms to grant permissions to teams. When personnel switch teams or leave projects, administrators simply adjust membership or the corresponding role.

Portfolio access permissions and Service Catalog API execution permissions are two parts that must be evaluated together. Users need appropriate Service Catalog permissions to perform actions; portfolio access determines which products are distributed to that principal. Additionally, permissions to read resource status via CloudFormation or related services may be needed for users to inspect full deployment results.

### 3.2. Launch constraint: using a dedicated IAM role to create resources

A launch constraint associates an IAM role with a product in a portfolio. When an end user deploys, updates, or terminates a product, Service Catalog uses the configured role to perform the required provisioning operations.

This model separates user permissions from resource creation permissions. For example, a developer may be allowed to deploy an application environment product without having permissions to create any arbitrary EC2 instance type, edit IAM policies, or modify network configurations directly. The launch role should have only the actions and resources required by the product's template.

When designing a launch role:

1. The trust policy must allow the Service Catalog service to assume the role.
2. The permission policy must cover CloudFormation or Terraform operations and the services used by the product.
3. Restrict resource ARNs, actions, and conditions according to each service's capabilities; avoid granting broad admin permissions just to get the first deployment working.
4. Consider confused-deputy protection conditions using **aws:SourceAccount** and **aws:SourceArn** per current AWS guidance.
5. Test launch, update, and terminate operations because the role must support the full product lifecycle.

A launch constraint applies to a specific product-portfolio association. It does not automatically become a global setting for that product across all portfolios. If the same product appears in multiple portfolios, each association must be reviewed and configured appropriately.

A launch role also does not replace the end user's Service Catalog permissions. Permissions such as deploying or updating provisioned products must be granted to the principal via IAM following the end-user model; do not put user catalog-control permissions into the launch role.

### 3.3. Template constraint: restricting parameters users can choose

A template constraint restricts the parameter values end users are allowed to enter when deploying a product. For example, a shared template may support multiple EC2 instance types, while the Development portfolio allows only small types and the Production portfolio allows only a vetted set of instance types.

Template constraints enable reusing a general template while enforcing portfolio-specific rules. You can restrict:

- Instance types or compute configurations.
- CIDRs or IP address ranges.
- Volume sizes.
- Environment selections or service configurations.
- Parameters impacting security and cost.

Place validation inside the template itself when a rule must hold across all deployment paths. Then use template constraints to narrow choices further per portfolio. Remember that template constraints only govern deployment through the product; they do not stop someone with sufficient permissions from creating similar resources directly via APIs.

### 3.4. Other constraints

AWS Service Catalog supports several constraint types. Applicability may depend on product type and deployment method.

| Constraint type | Purpose | Example |
|---|---|---|
| **Launch** | Selects the IAM role Service Catalog uses for provisioning | Database product uses a role with permissions only to create and manage required databases |
| **Template** | Restricts input parameters | Production portfolio allows only approved instance configurations |
| **Notification** | Sends notifications about stack events via Amazon SNS | Operations team receives alerts when a product deployment fails |
| **Stack Set** | Configures product deployment across multiple accounts and Regions via CloudFormation StackSets | Distribute baseline logging or shared resources to multiple accounts |
| **Tag Update** | Controls the ability to update tags after a product has been provisioned | Allow operational processes to add owner or cost center tags per policy |

Constraints are attached to a product within a portfolio. Therefore, test against the exact portfolio users actually use, not only the base template or a test portfolio.

## 4. Standardizing tags with TagOptions

Tags help identify owners, environments, applications, cost centers, and data classification levels. If each team chooses key names and values independently, cost allocation data and resource queries become inconsistent. For example, for the same environment concept, tags might appear as **Environment**, **environment**, or **Env** with values **production**, **prod**, or **prd**.

Service Catalog provides the TagOption library so administrators can define allowed key-value pairs. A TagOption is managed metadata inside Service Catalog, not an AWS tag immediately upon creation. When TagOptions are attached to a product or portfolio and a user deploys the product, Service Catalog aggregates the applicable choices and applies the resulting tags to the provisioned product.

For example, a portfolio has these TagOptions:

| Key | Defined values |
|---|---|
| **Environment** | dev, test, prod |
| **CostCenter** | CC100, CC200 |
| **DataClassification** | public, internal, confidential |
| **OwnerTeam** | platform, payments, analytics |

When a product has these TagOptions attached, users may be required to pick appropriate values during deployment. If a key has only one value, Service Catalog can apply that value automatically. When the same key has multiple values attached at both portfolio and product levels, available values are combined according to TagOption rules; administrators should avoid conflicting configurations that leave no valid tag values.

TagOptions are particularly useful for standardizing tags on CloudFormation provisioned products. AWS Service Catalog currently does not support TagOptions for Terraform Open Source or Terraform Cloud products, so verify the product type before designing your tagging workflow.

TagOptions help users pick from a governed set of values, yet organizations should still use complementary tag governance mechanisms. AWS Organizations Tag Policies can standardize keys, casing, and values for supported services; IAM conditions or SCPs can block certain tagless operations where APIs support corresponding condition keys; AWS Config can detect resources missing or having invalid tags. Do not assume creating TagOptions alone guarantees every resource in the account has mandatory tags.

## 5. Sharing catalogs across multiple AWS accounts

In a multi-account model, the platform team can manage products in a central account and distribute portfolios to member accounts.

AWS Service Catalog supports sharing portfolios account-to-account or via AWS Organizations. With reference sharing, the portfolio is imported into the recipient account and stays synchronized with the source portfolio. Products and constraints managed by the source account update automatically with source changes; recipient account administrators can grant access to local principals and, depending on the model, add local configurations in a separate portfolio.

You can share with:

- A specific AWS account.
- An Organizational Unit (OU).
- The entire organization.

Sharing via AWS Organizations fits when the organization has a clear OU structure. For example, the Production portfolio can be shared with the Production OU; experimental portfolios are shared only with the Sandbox OU. Using OUs aligns portfolio access with the organization's account management hierarchy.

Points to check when sharing:

1. AWS Organizations integration must be enabled for Service Catalog; enabling trusted integration belongs to the management account.
2. Sharing with organization nodes is performed by the management account or an appropriately registered delegated administrator.
3. Portfolio importing and sharing must be designed per Region; reference sharing does not make a portfolio automatically appear in all Regions.
4. When an account moves to another OU, portfolio access may change according to the target OU's sharing scope.
5. A shared resource cannot be re-shared arbitrarily; clearly design source accounts, distribution accounts, and consumer accounts.

Reference portfolio sharing differs from deploying a copy of a catalog. To distribute a configuration copy to multiple accounts, consider CloudFormation StackSets to deploy the required catalog resources. With copies, changes at the source must be redeployed via the corresponding workflow. Choosing between models depends on ownership requirements, local customization needs at recipient accounts, and update methods.

## 6. Workflow for building an approved infrastructure catalog

A catalog is valuable when every product has clear acceptance criteria, an owner, and a lifecycle. The reference workflow below fits platform teams managing multiple AWS services.

### Step 1: Define requirements and standards

Gather requirements from consumer teams, then define a baseline for each product. For a data storage product, standards might include encryption, blocking public access, versioning, data classification tags, logging, and retention policies. For a compute product, standards might include approved AMIs, security groups, subnets, logging, instance profile permissions, and size limits.

Each product should define:

- Technical owner and support team.
- Permitted user groups, accounts, and Regions.
- Parameters allowed to be modified.
- Required IAM permissions and cost limits.
- Backup, logging, monitoring, encryption, and patching requirements.
- Testing criteria, approval workflow, and review cadence.

### Step 2: Package the template

Create a CloudFormation template or a Terraform template type supported by Service Catalog. The template should clearly express resources, dependencies, parameters, outputs, and default security settings. Use parameter validation to reject invalid inputs directly in the template.

The abbreviated example below creates an S3 bucket with server-side encryption, versioning enabled, and public access blocked. In environments requiring centralized key management, the organization can replace the sample encryption configuration with an approved AWS KMS key and add corresponding key policy permissions.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Approved S3 bucket baseline for application data

Parameters:
  Environment:
    Type: String
    AllowedValues:
      - dev
      - test
      - prod
    Default: dev
  DataClassification:
    Type: String
    AllowedValues:
      - internal
      - confidential
    Default: internal

Resources:
  ApplicationDataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        IgnorePublicAcls: true
        BlockPublicPolicy: true
        RestrictPublicBuckets: true
      VersioningConfiguration:
        Status: Enabled
      Tags:
        - Key: Environment
          Value: !Ref Environment
        - Key: DataClassification
          Value: !Ref DataClassification

Outputs:
  BucketName:
    Description: Name of the provisioned data bucket
    Value: !Ref ApplicationDataBucket
~~~

This is only a minimal baseline example, not a complete production template. Before releasing, evaluate requirements for KMS, bucket policies, access logging, lifecycle, replication, backups, data access permissions, and organizational retention rules.

### Step 3: Test and approve the version

Deploy the template in a test account and verify both success and failure paths. Confirm actual resources match the design, permissions do not exceed needs, tags are applied, logs are retrievable, and update/terminate operations behave as expected.

Record the template version, source commit or artifact, test results, approver, and release notes. Once a product is published, version information should let operators determine the exact configuration that created a provisioned product.

### Step 4: Create the product and portfolio

Import the approved template into Service Catalog as a product. Create a version with a clear description, then add the product to the appropriate portfolio. You can reuse the same product across multiple portfolios to avoid maintaining nearly identical template copies.

### Step 5: Configure permissions and constraints

Assign appropriate principals to the portfolio. Create a launch role with least-privilege permissions and attach a launch constraint for each product-portfolio association. Add template constraints to restrict parameters by user group. Configure a notification constraint if operations teams need provisioning events via SNS; use a Stack Set constraint when deploying products across multiple accounts and Regions.

### Step 6: Attach TagOptions and share

Define a consistent tag set and attach TagOptions to the portfolio or product when the product type supports them. Share the portfolio to accounts or OUs per your governance model. After sharing, verify principals in recipient accounts see the right products, only allowed options, and no out-of-scope permissions.

### Step 7: Monitor, review, and improve

Monitor provisioned product status, CloudFormation or Terraform events, SNS notifications, and CloudTrail. Use AWS Config or Security Hub to inspect actual configurations against applicable controls. Periodically review unowned products, outdated versions, overly broadly shared portfolios, over-privileged roles, and unneeded provisioned products.

## 7. Example: publishing a data bucket product for multiple teams

Suppose an organization has three teams: Analytics, Payments, and Platform. The Platform team owns the standard bucket template. The Analytics team needs buckets for internal data; the Payments team needs buckets for sensitive data requiring KMS encryption and stricter access permissions.

One possible design:

1. Platform creates the **Application Data Bucket** product from a reviewed template and publishes versions via a formal workflow.
2. Create the **Data Platform** portfolio and add the product to it.
3. Create a launch role for the product, permitting only required operations on relevant resources.
4. Add TagOptions for **OwnerTeam**, **Environment**, **CostCenter**, and **DataClassification**.
5. Create appropriate portfolios or constraints for each data classification tier. For Payments, permit only choices and configurations meeting sensitive data standards.
6. Share portfolios with target OUs or accounts using AWS Organizations.
7. Grant portfolio access to the Analytics and Payments IAM roles.
8. Record deployment events via CloudTrail; use AWS Config to verify encryption, public access block, and other configuration requirements.

Governance flow diagram:

~~~mermaid
flowchart TD
    A[Platform team defines baseline] --> B[Template tested and approved]
    B --> C[Product and product version]
    C --> D[Portfolio by team or environment]
    D --> E[IAM principal and launch constraint]
    E --> F[End user deploys provisioned product]
    F --> G[CloudTrail, Config, and operational notifications]
    G --> H[Review, version updates, and improvements]
~~~

In this example, Analytics and Payments can share the same base product while receiving different portfolios or constraints. If two teams have fundamentally different architectural requirements, the Platform team should consider separating products for easier testing and accountability. Do not create multiple portfolios just to mask differences that have not yet been modeled in templates.

## 8. Audit evidence to retain

An approved catalog must allow answering: who is permitted to deploy, which products are approved, which versions are in use, which resources were created, and whether actual configurations are compliant.

| Audit question | Evidence to collect |
|---|---|
| Who is allowed to view and deploy products? | IAM policies, portfolio principal lists, IAM Identity Center or related role configurations |
| Which products are approved? | Product IDs, portfolios, descriptions, owners, versions, source templates, and approval records |
| Which products did users deploy? | Provisioned product records, product versions, deployment timestamps, and principal identifiers |
| Are resource creation permissions restricted? | Launch constraints, trust policies, permission policies, and permission review results |
| Which parameters are allowed? | Templates, parameter validations, and template constraints attached to the portfolio |
| Which team or cost center owns the resources? | TagOptions, actual tags, owner, environment, cost center, and cost reports |
| Who modified the catalog or sharing permissions? | CloudTrail events, change history, change requests, and approvers |
| Do live resources comply with the baseline? | AWS Config evaluations, Security Hub findings, deployment logs, and remediation results |

CloudTrail traces API operations and administrative changes; AWS Config evaluates resource configurations against rules; Security Hub can aggregate security findings from integrated sources. These tools complement Service Catalog: the catalog defines the approved deployment path provided by the organization, while auditing tools verify who acted and whether live resources meet requirements.

Do not save only screenshots of the portfolio page. Evidence should include resource identifiers, timestamps, principals, versions, and event sources so everything can be cross-referenced. For significant changes, link AWS events to organizational tickets or change requests.

## 9. Common risks and how to handle them

### Granting overly broad permissions to the launch role

If a launch role has account-wide administrative permissions, users can indirectly create resources or make changes beyond the product's intent. Review actions and resources per template, separate roles by product or product group with similar needs, and test with least privilege.

### Assuming having a catalog blocks all other resource creation paths

Service Catalog manages product distribution and deployment. If IAM still allows users to call EC2, RDS, S3, or other APIs directly, they can create resources outside the catalog. Use IAM, SCPs, and other guardrails to enforce approved creation paths; use Config to detect remaining drift.

### Publishing products without an owner

Old templates may contain AMIs, parameters, or settings that are no longer suitable. Every product needs an owner, a review schedule, a version release process, and a support contact. Maintain a plan to notify and remediate provisioned products running outdated versions.

### Confusing publishing a version with updating instances

Adding a new version to the catalog does not mean running instances are updated immediately. Administrators must plan provisioned product updates, assess whether changes are breaking, and monitor post-update results.

### Sharing portfolios with the wrong scope

Sharing with the entire organization may be broader than necessary. Choose target OUs or accounts following least privilege, review delegated administrators, verify permissions in recipient accounts, and re-evaluate when accounts move between OUs.

### Conflicting TagOptions or treating them as account-wide enforcement

TagOption values must be governed consistently across portfolios and products. Check for duplicate keys, overlapping values, and whether the product type supports TagOptions. For tagging requirements on resources created outside the catalog, additionally use Tag Policies, IAM/SCP conditions, and AWS Config per service support.

### Deleting a product while forgetting running provisioned products

Removing a product from a portfolio stops new deployments, though previously created provisioned products can keep running. Before retiring a product, list existing instances, identify owners, decide whether to update, migrate, or terminate, and assess data impact.

## 10. Pre-publication checklist for a product

- [ ] Product has a clear purpose, owner, support group, and Region/account scope.
- [ ] Template reviewed for IAM, networking, encryption, backups, logging, monitoring, and cost.
- [ ] Parameters have validation; portfolio constraints tested.
- [ ] Launch role has the right trust policy and least-privilege permissions.
- [ ] Product version has a description, template source, and test results.
- [ ] Portfolio granted only to appropriate principals and user groups.
- [ ] TagOptions or alternative tagging mechanisms meet classification and cost allocation requirements.
- [ ] Cross-account sharing targets the right OUs/accounts and is verified on the recipient side.
- [ ] CloudTrail, AWS Config, SNS, or related monitoring systems can provide required evidence.
- [ ] Processes exist for version updates, handling legacy instances, and retiring products.

## 11. Key takeaways

AWS Service Catalog turns organization-prepared infrastructure templates into a controlled self-service catalog. Products describe what can be deployed; versions manage changes; portfolios distribute products by team; principals define users; constraints limit how deployments happen; launch roles separate provisioning permissions from personal permissions; TagOptions standardize tag choices.

For the catalog to truly support auditing and compliance, organizations must maintain product lifecycles, restrict permissions with IAM and org-level guardrails, distribute portfolios to exact account/OU scopes, and correlate CloudTrail events with resource states via AWS Config or related security tools. The catalog creates the paved road; governance and monitoring layers verify infrastructure is deployed and operated along that road.

## References

- [Overview of AWS Service Catalog](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/what-is_concepts.html)
- [Using AWS Service Catalog Constraints](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/constraints.html)
- [AWS Service Catalog Launch Constraints](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/constraints-launch.html)
- [AWS Service Catalog TagOption Library](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/tagoptions.html)
- [Sharing a Portfolio](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/catalogs_portfolios_sharing_how-to-share.html)
- [Granting Access to Users](https://docs.aws.amazon.com/servicecatalog/latest/adminguide/catalogs_portfolios_users.html)
- [Launching a Product](https://docs.aws.amazon.com/servicecatalog/latest/userguide/enduser-launch.html)