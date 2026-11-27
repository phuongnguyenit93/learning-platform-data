# AWS Security Hub and Security Finding Aggregation

## Lesson Objectives

Within the CLOUD_PROVIDERS_AWS ecosystem, protecting an AWS environment requires a centralized place to view risky configurations, vulnerabilities, attack indicators, and security issues detected by multiple services. AWS Security Hub CSPM (Cloud Security Posture Management) helps evaluate resources against security standards, ingest findings from AWS services and partners, normalize them into the AWS Security Finding Format (ASFF), and support triage and remediation tracking. When combined with AWS Organizations, Amazon EventBridge, AWS Security Lake, and services such as GuardDuty, Inspector, and Macie, organizations can build cross-account, cross-Region monitoring and response workflows.

At the time of writing, AWS distinguishes between **AWS Security Hub CSPM** and the new unified **AWS Security Hub** experience. Security Hub CSPM focuses on posture management, security standards, controls, and ASFF findings. The new AWS Security Hub provides a unified view of exposures, threats, vulnerabilities, and security response; it receives OCSF data from Security Hub CSPM alongside other security services to correlate risk and surface attack paths. This lesson focuses on Security Hub CSPM and the finding aggregation mechanism, while explaining its relationship to the new Security Hub experience to avoid service naming confusion.

After this lesson, learners will be able to:

- Distinguish Security Hub CSPM from GuardDuty, Inspector, Macie, and the new AWS Security Hub.
- Explain the relationship between a security standard, control, security check, and finding.
- Prepare AWS Config and enable Security Hub CSPM to collect control findings.
- Read key ASFF fields and distinguish compliance status, workflow status, and record state.
- Integrate findings from AWS services, partner products, and custom sources.
- Manage findings, insights, consolidated control findings, and security scores.
- Design multi-account and multi-Region governance using AWS Organizations declarative policies and cross-Region aggregation.
- Automate triage, notifications, ticket creation, and remediation using Security Hub automation rules with EventBridge.
- Monitor costs, access permissions, and data quality to maintain a reliable monitoring pipeline.

## 1. Role of Security Hub in Security Architecture

Each AWS security service answers a distinct set of questions:

| Service | Primary Question | Data or Output |
|---|---|---|
| AWS Security Hub CSPM | Do resource configurations comply with best practices and security standards? | Control findings, compliance status, security score |
| Amazon GuardDuty | Is there suspicious behavior or threat indicators in accounts, workloads, or network traffic? | Threat detection findings |
| Amazon Inspector | Do EC2 instances, container images, and Lambda functions have vulnerabilities or exposure issues? | Vulnerability findings |
| Amazon Macie | Where is sensitive data in Amazon S3 located and what risks exist? | Sensitive data findings |
| IAM Access Analyzer | Do resource policies share access outside the intended scope? | Access analysis findings |
| AWS Config | How have resource configurations changed and do they comply with Config rules? | Configuration items and rule evaluations |
| New AWS Security Hub | Which combined security signals form critical exposures or attack paths? | OCSF findings, correlated exposures, and security operations context |

Security Hub CSPM does not replace specialized detection services. GuardDuty continues analyzing signals to detect threats; Inspector scans for vulnerabilities; Macie analyzes sensitive data; AWS Config records configurations. Security Hub CSPM aggregates related results into one interface and normalizes findings so security teams can filter, prioritize, and assign remediation.

For example, an EC2 instance might simultaneously have three issues: an administrative port open to the Internet, a package with a critical vulnerability, and GuardDuty detecting unusual outbound connection behavior. Each service generates its own finding. Viewing them together by resource, account, Region, and severity gives security teams context to prioritize that instance over a less urgent risky configuration.

High-level data flow:

~~~mermaid
flowchart TD
    A[AWS Config] --> H[Security Hub CSPM]
    G[GuardDuty] --> H
    I[Inspector] --> H
    M[Macie] --> H
    X[IAM Access Analyzer and partners] --> H
    H --> F[ASFF-normalized findings]
    F --> V[Findings, Insights, Standards, and Security Scores]
    F --> R[Automation rules]
    R --> E[Amazon EventBridge]
    E --> T[Tickets, SNS, Lambda, Step Functions, or SSM]
    F --> L[Amazon Security Lake]
    L --> O[OCSF and security analytics]
    F --> U[New AWS Security Hub]
    U --> P[Exposure correlation and attack path]
~~~

## 2. Security Hub CSPM vs. the New AWS Security Hub

Naming in AWS documentation has evolved alongside the service. Security Hub CSPM was previously referred to simply as AWS Security Hub. Today, AWS distinguishes two complementary services:

| Capability | Security Hub CSPM | New AWS Security Hub |
|---|---|---|
| Focus | Cloud security posture management | Unified cloud security operations |
| Best practice and standards checks | Yes | Uses findings from CSPM |
| Security controls and compliance status | Yes | Displays context from CSPM |
| Primary finding format | ASFF | OCSF |
| Data sources | Control checks, AWS services, and partners | CSPM, GuardDuty, Inspector, Macie, and supported sources |
| Exposure and attack path correlation | Not the primary focus | Yes |
| Triage and response automation | Automation rules and EventBridge | Unified workflows per new Security Hub features |

Security Hub CSPM sends findings to the new Security Hub. The new Security Hub can combine misconfigurations from CSPM, threat findings from GuardDuty, vulnerabilities from Inspector, and sensitive data from Macie to identify high-risk exposures. For example, a vulnerable package may not be a critical exposure if the workload is unreachable externally. Combining the vulnerability with network reachability and permission configuration helps security teams see exploitable attack paths.

OCSF is the Open Cybersecurity Schema Framework, an open schema used to standardize security data. ASFF remains the finding format of Security Hub CSPM. When sending findings into Amazon Security Lake, Security Lake can convert data from ASFF to OCSF for analysis alongside other security sources.

When reading documentation, APIs, or console screens, verify whether you are working with Security Hub CSPM or the new AWS Security Hub. Both services may appear in the same workflow, yet their schemas, pricing models, and feature scopes are not identical.

## 3. Security Standards and Security Controls

A security standard is a set of requirements based on regulations, industry frameworks, or best practices. Each standard consists of multiple controls. A control describes a safeguard that can be evaluated against AWS resources.

Standards supported by Security Hub CSPM include:

- AWS Foundational Security Best Practices (FSBP).
- CIS AWS Foundations Benchmark.
- NIST SP 800-53 Revision 5.
- NIST SP 800-171 Revision 2.
- Payment Card Industry Data Security Standard (PCI DSS).
- AWS Resource Tagging and AI Security Best Practices.
- Additional standards or profiles, including CRI and service-managed standards.

The list and versions of standards may vary by Region and change over time. Check the Standards reference page in AWS documentation before including a standard in an audit scope.

For example, a control may require that an Amazon S3 bucket disallow public read access. Security Hub CSPM evaluates the relevant configuration and generates a finding if the bucket violates it. Another control may require EBS volumes to be encrypted. Each control typically maps to one or more resource types and a specific check.

Distinguish three concepts:

- **Standard:** the overall set of requirements, such as FSBP or CIS.
- **Control:** a safeguard within a standard, such as checking encryption or public access.
- **Finding:** the specific result of a check or a security alert, tied to a resource and detection source.

A control can appear in multiple standards. Without consolidated control findings, Security Hub CSPM may generate multiple findings for the same check, one per standard. When consolidated control findings are enabled, the service generates a single shared finding for that control, reducing noise and duplication.

Security Hub CSPM does not issue compliance certifications on behalf of an organization. A passed control only indicates that the corresponding check passed at evaluation time. Satisfying an entire standard also depends on scope, processes, evidence, and requirements outside automated checks.

## 4. AWS Config as a Key Prerequisite for Control Findings

Security Hub CSPM uses service-linked AWS Config rules to perform most security checks. Therefore, AWS Config must be enabled and the resource recorder must record the resource types evaluated by those controls.

Before enabling standards:

1. Select the AWS accounts and Regions within monitoring scope.
2. Enable AWS Config in each account and Region.
3. Configure the recorder to record required resource types.
4. Verify the Configuration Recorder IAM role has sufficient permissions to record resources.
5. Confirm AWS Config is active and collecting data.
6. Then enable Security Hub CSPM and the required standards.

If required resource types are not recorded, a control may lack enough data to evaluate. Findings may carry a status of WARNING or NOT_AVAILABLE instead of PASSED/FAILED. Do not conclude an environment is secure merely because no failed findings appear.

When deploying across Organizations, ensure AWS Config is configured consistently for member accounts and Regions in scope. Enabling Security Hub CSPM does not automatically ensure every resource type required by every control is recorded by AWS Config.

## 5. Enabling Security Hub CSPM in an Account and Region

Security Hub CSPM can be enabled via the console or API. AWS CLI example:

~~~bash
aws securityhub enable-security-hub \
  --enable-default-standards \
  --region ap-southeast-1
~~~

When enabled via the API with default standards, Security Hub CSPM enables AWS Foundational Security Best Practices and CIS AWS Foundations Benchmark v1.2.0 per documented default behavior. You can omit default standards if you prefer to explicitly select standards afterward.

Check enabled standards:

~~~bash
aws securityhub get-enabled-standards \
  --region ap-southeast-1
~~~

View existing findings:

~~~bash
aws securityhub get-findings \
  --max-results 20 \
  --region ap-southeast-1
~~~

In production environments, do not simply enable the service and consider deployment complete. Verify the Config recorder, standards, controls, integrations, account coverage, Region coverage, and finding access permissions.

Security Hub CSPM uses a service-linked role to perform service-managed tasks. Operators and delegated administrators still need appropriate IAM permissions to enable the service, configure standards, view findings, update workflows, or manage Organizations policies.

## 6. Organizing Findings with the AWS Security Finding Format (ASFF)

Security Hub CSPM normalizes findings from various sources into ASFF. The goal is for different products to share a common structure for searching, filtering, correlating, and handing off to response systems.

Common ASFF fields:

| Field | Meaning |
|---|---|
| Id | Finding identifier generated by the provider |
| ProductArn | ARN of the product generating the finding |
| GeneratorId | Component or control generating the finding |
| AwsAccountId | Associated AWS account |
| Region | Region of the finding |
| Title | Short title |
| Description | Description of the issue and context |
| Severity | Severity level |
| Types | Finding classification |
| Resources | Affected resources |
| CreatedAt / UpdatedAt | Creation and update timestamps |
| Compliance | Compliance status if the finding relates to a control |
| Workflow | Customer investigation status |
| RecordState | Whether the finding is active or archived |
| Remediation | Remediation guidance or link |

Abbreviated finding example:

~~~json
{
  "SchemaVersion": "2018-10-08",
  "Id": "example-finding-id",
  "ProductArn": "arn:aws:securityhub:ap-southeast-1::product/aws/securityhub",
  "GeneratorId": "security-control/EC2.2",
  "AwsAccountId": "123456789012",
  "Region": "ap-southeast-1",
  "Title": "EC2 security group allows unrestricted SSH access",
  "Description": "An inbound rule allows SSH access from 0.0.0.0/0.",
  "Severity": {
    "Label": "HIGH"
  },
  "Workflow": {
    "Status": "NEW"
  },
  "RecordState": "ACTIVE",
  "Resources": [
    {
      "Type": "AwsEc2SecurityGroup",
      "Id": "arn:aws:ec2:ap-southeast-1:123456789012:security-group/sg-0123456789abcdef0"
    }
  ]
}
~~~

The example above illustrates only key fields. Real findings can include many more attributes, such as ProductFields, UserDefinedFields, Network, Process, ThreatIntelIndicators, Vulnerabilities, and detailed resource objects.

For control findings, SecurityControlId and SecurityControlArn are especially useful when writing automation. AWS recommends filtering by control ID or ARN rather than Title or Description, since titles and descriptions may change over time.

## 7. Severity, Compliance Status, and Workflow Status

These three status groups answer different questions and should not be used interchangeably.

**Severity** indicates the importance or impact of the issue. Common labels are CRITICAL, HIGH, MEDIUM, LOW, and INFORMATIONAL. Severity helps prioritize investigations, but must be paired with resource criticality and exploitability.

**Compliance.Status** describes the security check outcome of a control finding:

| Value | Meaning |
|---|---|
| PASSED | Resource met the control condition at check time |
| FAILED | Resource did not meet the condition |
| WARNING | Could not determine PASSED or FAILED, e.g., missing AWS Config recording for the resource type |
| NOT_AVAILABLE | Check could not complete, resource was deleted, or evaluation does not apply |

**Workflow.Status** tracks the operations team's investigation progress:

| Value | Meaning |
|---|---|
| NEW | New finding requiring review |
| NOTIFIED | Resource owner has been notified |
| SUPPRESSED | Reviewed and determined no action needed per policy |
| RESOLVED | Remediated and confirmed resolved |

**RecordState** indicates whether a finding is active or archived. A finding can have Workflow.Status set to RESOLVED while RecordState remains ACTIVE. This is not contradictory: the issue has been handled in the workflow, while the finding record remains active to preserve history.

Security Hub CSPM can automatically change the workflow status of a control finding. For example, when compliance transitions from PASSED to FAILED, WARNING, or NOT_AVAILABLE, workflow status may reset to NEW to request investigation. When a control finding reaches PASSED compliance, the service automatically sets workflow status to RESOLVED.

Do not use SUPPRESSED to hide issues merely because findings are noisy. Before suppressing, document a justification, owner, scope, review expiration date, and approval record if required by organizational policy.

## 8. Reading Control Status and Security Score

Security Hub CSPM aggregates the statuses of findings belonging to the same control to produce a control status:

- **Passed:** all associated findings are PASSED.
- **Failed:** at least one finding is FAILED.
- **Unknown:** WARNING or NOT_AVAILABLE findings exist, with no FAILED findings.
- **No data:** no findings exist yet to evaluate, or no applicable data exists.
- **Disabled:** control is disabled in the account and Region.

The security score shows the percentage of passed controls out of the scored controls set. Controls with No data status are excluded from the denominator. Archived or suppressed findings are excluded when determining control status. Therefore, bulk suppression can make the score appear higher while actual risk remains unresolved.

Security Hub CSPM typically generates initial control statuses within about 30 minutes after a user first opens the Summary or Security standards page; subsequent updates are typically based on the preceding 24 hours of data. In some Regions such as China and AWS GovCloud (US), initial status generation may take longer. AWS Config resource recording must be configured for control status and scores to appear.

Do not use the security score as sole evidence to claim compliance. The score does not reflect every procedural requirement, non-AWS applications, approved exceptions, or full business risk. Review control details, findings, resources, evaluation timestamps, and account/Region scope before reporting.

## 9. Consolidated Control Findings and Noise Reduction

A control can belong to multiple standards. If multiple standards are enabled without consolidated control findings, the same security check can produce one finding per standard. This increases finding volume and complicates deduplication in ticketing or SIEM tools.

Consolidated control findings generate one finding per control check, even when the control belongs to multiple standards. This feature is enabled by default for accounts enabling Security Hub CSPM from February 23, 2023 onward. For older accounts, check the current configuration.

You can check and enable it with the AWS CLI:

~~~bash
aws securityhub update-security-hub-configuration \
  --control-finding-generator SECURITY_CONTROL \
  --region ap-southeast-1
~~~

The value SECURITY_CONTROL enables consolidated control findings. STANDARD_CONTROL switches back to per-standard findings.

When switching modes, Security Hub CSPM may generate new findings and archive old ones. The transition can take up to 24 hours, during which both finding formats may appear. Before switching, verify which ASFF fields external integrations, EventBridge rules, SOAR playbooks, and dashboards rely on.

## 10. Integrating Findings from AWS Services and Partners

After enabling Security Hub CSPM, you can activate finding source integrations. Some AWS integrations activate automatically when both Security Hub CSPM and the source service are enabled; others require explicit configuration or acceptance.

Common sources:

| Source | Finding Types |
|---|---|
| GuardDuty | Suspicious behavior, credential compromise, unusual connections or activity |
| Inspector | Vulnerabilities in EC2, container images, and Lambda |
| Macie | Sensitive data and risks related to S3 |
| IAM Access Analyzer | Resource policies or access permissions outside intended scope |
| AWS Firewall Manager | Network protection or WAF policy violations |
| AWS Health | Security events, abuse notifications, or changes tied to account risk |
| IoT Device Defender | IoT device security issues |
| Third-party products | Findings from CSPM, EDR, vulnerability scanners, SIEMs, or other security tools |

Integration does not mean Security Hub CSPM re-runs the analysis of every source. The service receives findings generated by providers, normalizes them, and displays them. During investigation, open the finding details and inspect ProductArn, ProductName, GeneratorId, and provider guidance to understand the underlying data.

Partner products can submit findings through supported integration mechanisms. For custom sources, BatchImportFindings can create or update findings owned by that provider. Customers or SOAR tools acting on their behalf use BatchUpdateFindings to update workflow and investigation fields. BatchUpdateFindings does not create new findings and supports up to 100 finding identifiers per request.

## 11. Filtering Findings and Creating Custom Insights

The Findings page can contain a large volume of records. Filter by attributes such as:

- AwsAccountId, Region, ResourceType, and ResourceId.
- ProductArn or ProductName.
- Severity.Label.
- Workflow.Status and RecordState.
- Compliance.Status.
- Types, Title, or control-related fields.

Example filters.json file:

~~~json
{
  "WorkflowStatus": [
    {
      "Value": "NEW",
      "Comparison": "EQUALS"
    }
  ],
  "SeverityLabel": [
    {
      "Value": "HIGH",
      "Comparison": "EQUALS"
    }
  ],
  "RecordState": [
    {
      "Value": "ACTIVE",
      "Comparison": "EQUALS"
    }
  ]
}
~~~

Query findings:

~~~bash
aws securityhub get-findings \
  --filters file://filters.json \
  --max-results 50 \
  --region ap-southeast-1
~~~

A custom insight is a saved query to track a meaningful set of findings. For example:

- CRITICAL/HIGH findings in production accounts.
- EC2 findings with administrative ports open to the Internet.
- Findings unresolved for more than 7 days.
- GuardDuty findings within a specific OU.
- Findings linked to resources tagged with Owner or Application.

Insights help security teams track trends and actionable lists. Insights do not remediate resources themselves and do not replace ticketing or remediation workflows.

## 12. Multi-Account Governance with AWS Organizations Declarative Policies

As of November 20, 2026, AWS recommends using **Security Hub CSPM declarative policies** to manage multi-account and multi-Region configurations in AWS Organizations. Announced on November 13, 2026, this capability replaces central configuration as the recommended mechanism for new deployments.

A declarative policy can specify:

- Which Regions have Security Hub CSPM enabled and disabled.
- Which standards are enabled.
- Which controls are enabled or disabled.
- Parameters for certain controls.
- Policy attachment targets: organization root, OU, or specific account.
- Automatic inheritance of policies by new accounts or accounts moving between OUs.

Example policy enabling Security Hub CSPM across all supported Regions, using FSBP, and enabling default controls:

~~~json
{
  "securityhub_cspm": {
    "cspm_enablement": {
      "enable_in_regions": {
        "@@assign": ["ALL_SUPPORTED"]
      },
      "disable_in_regions": {
        "@@assign": []
      }
    },
    "cspm_standards_controls": {
      "default": {
        "enabled_standards": {
          "@@assign": [
            "aws-foundational-security-best-practices/v/1.0.0"
          ]
        },
        "controls_configuration": {
          "default_control_association_status": {
            "@@assign": "ENABLED"
          }
        }
      }
    }
  }
}
~~~

The policy above shows the basic structure. In real organizations, you can define regional overrides for Regions needing different standards or controls. Review overrides carefully because a regional override replaces the default configuration for that Region rather than automatically merging every setting from default.

Before applying a policy, ensure AWS Config already records the required resource types and the service-linked role AWSServiceRoleForSecurityHub exists in the management account or delegated administrator account. Policies do not configure AWS Config automatically. If using a delegated administrator, register that account with AWS Organizations and enable Security Hub CSPM administrative permissions per AWS guidance. You can check the service-linked role using aws iam get-role --role-name AWSServiceRoleForSecurityHub.

General CLI workflow:

~~~bash
# Enable trusted access for Security Hub CSPM
aws organizations enable-aws-service-access \
  --service-principal securityhub.amazonaws.com

# Optional: register a delegated administrator account
aws organizations register-delegated-administrator \
  --account-id 111122223333 \
  --service-principal securityhub.amazonaws.com

# Enable the delegated administrator in the home Region
aws securityhub enable-organization-admin-account \
  --admin-account-id 111122223333 \
  --region ap-southeast-1

# Enable the Security Hub CSPM policy type on the organization root
aws organizations enable-policy-type \
  --root-id r-example \
  --policy-type SECURITYHUB_CSPM_POLICY

# Create a declarative policy
aws organizations create-policy \
  --name "securityhub-cspm-baseline" \
  --description "Enable Security Hub CSPM and FSBP across supported Regions" \
  --type SECURITYHUB_CSPM_POLICY \
  --content file://securityhub-cspm-policy.json

# Attach the policy to an OU or organization root
aws organizations attach-policy \
  --policy-id p-example \
  --target-id r-example
~~~

Replace root ID, policy ID, and target ID with your organization's actual values. Execute from a principal authorized to administer the corresponding Organizations policy type. Test first on a sandbox OU, preview the impact, and verify account/Region coverage before attaching to the root.

Declarative policies and central configuration cannot be used simultaneously in the same organization. If you currently use central configuration, use the import tool in the Security Hub CSPM console to migrate existing settings to declarative policies before making changes. Do not attach an experimental policy to a production account without understanding that using declarative policies changes the central configuration governance mechanism across the entire organization.

Central configuration remains supported for existing organizations using it, but is now considered the legacy mechanism. For new deployments, prefer declarative policies.

## 13. Cross-Region Aggregation and Home Region

Cross-Region aggregation centralizes findings, finding updates, insights, control compliance statuses, and security scores from multiple Regions into a single **home Region**. Some legacy APIs still refer to this as the aggregation Region.

Create a finding aggregator from the intended home Region:

~~~bash
aws securityhub create-finding-aggregator \
  --region ap-southeast-1 \
  --region-linking-mode SPECIFIED_REGIONS \
  --regions ap-southeast-2 eu-west-1
~~~

Region linking modes:

- ALL_REGIONS: links all supported Regions and automatically includes new Regions once supported by the service and opted into by the account.
- ALL_REGIONS_EXCEPT_SPECIFIED: links all except an excluded list of Regions.
- SPECIFIED_REGIONS: links only the specified list.
- NO_REGIONS: links no Regions.

The home Region does not automatically enable Security Hub CSPM in linked Regions. Each account and Region must have Security Hub CSPM, Config, and required controls enabled. Only Regions with Security Hub CSPM enabled send data for aggregation.

Declarative policies and cross-Region aggregation are separate configurations. Declarative policies determine which accounts/Regions enable Security Hub CSPM and which controls run; the finding aggregator determines where finding data from Regions is aggregated. If a policy enables a Region that is not in the linked Regions list, the delegated administrator may not see that Region's findings in the home Region.

For controls evaluating global resources such as IAM, pay attention to findings generated across multiple Regions. Configure controls and Region coverage to prevent duplicates or misinterpreting multiple findings as multiple distinct resources.

## 14. Delegated Administrator and Member Account Permissions

In an Organizations model, designate a dedicated security account as delegated administrator. This account manages Security Hub CSPM configuration, aggregates findings, and coordinates response. The Organizations management account retains organization administration duties; avoid using it for daily security operations.

The delegated administrator can view member account findings according to administrative permissions and scope. Member accounts can still view their own findings and address account-scoped issues. Permissions to update findings, manage standards, integrations, and automation depend on the governance model and IAM policies.

Principles:

- Separate Organizations administrative permissions, Security Hub configuration permissions, and finding handling permissions.
- Use IAM Identity Center or an appropriate federation mechanism to grant responder access.
- Allow only authorized personnel to update workflow status or suppress findings.
- Use dedicated roles for automation and restrict modifiable resources/actions.
- Audit changes to standards, controls, policy attachments, and finding updates via CloudTrail.
- Do not share credentials between the delegated administrator and member accounts.

## 15. Automation Rules in Security Hub CSPM

Automation rules automatically update or suppress findings based on criteria. For example:

- Change severity based on resource tags or criticality.
- Set Workflow.Status to SUPPRESSED for findings approved as exceptions.
- Add notes and UserDefinedFields to attach ticket IDs.
- Set Workflow.Status to NOTIFIED when a finding is assigned to an owner.
- Adjust severity for partner findings according to internal rules.

Filter on stable fields such as SecurityControlId, ProductArn, ResourceType, ResourceId, or tags. Avoid relying on Title/Description because providers may update these fields.

Automation rules execute in near real-time and run before EventBridge rules. Consequently, EventBridge receives findings after fields have been updated by automation rules. This ordering matters if EventBridge rules filter on Severity or Workflow.Status.

Do not automatically suppress all low-severity findings. A LOW finding can signal a larger issue when combined with vulnerabilities, exposure, or critical resources.

## 16. Automating Response with Amazon EventBridge

Security Hub CSPM sends new and updated findings to EventBridge. EventBridge can trigger Lambda, Step Functions, SNS, SQS, Systems Manager Automation, API destinations, or forward events to another account's event bus.

Example event pattern filtering NEW and ACTIVE CRITICAL/HIGH findings:

~~~json
{
  "source": [
    "aws.securityhub"
  ],
  "detail-type": [
    "Security Hub Findings - Imported"
  ],
  "detail": {
    "findings": {
      "Severity": {
        "Label": [
          "CRITICAL",
          "HIGH"
        ]
      },
      "Workflow": {
        "Status": [
          "NEW"
        ]
      },
      "RecordState": [
        "ACTIVE"
      ]
    }
  }
}
~~~

An EventBridge rule can invoke a Lambda function to create a ticket or send an SNS notification. For remediation, it can invoke Step Functions to orchestrate checking resource owners, verifying state, requesting approval, and running Systems Manager Automation.

Sample response flow:

~~~mermaid
flowchart TD
    A[Security Hub CSPM finding] --> B[Automation rule updates finding]
    B --> C[EventBridge receives event]
    C --> D{Matching severity and resource?}
    D -- No --> E[Keep in triage queue]
    D -- Yes --> F[Create ticket and notify owner]
    F --> G[Verify remediation permissions and conditions]
    G --> H{Approval required?}
    H -- Yes --> I[Wait for authorized approver]
    H -- No --> J[Run remediation]
    I --> J
    J --> K[Re-verify resource]
    K --> L[Update workflow and store audit trail]
~~~

Practical example: Security Hub CSPM detects a security group allowing SSH from 0.0.0.0/0. EventBridge routes the finding to Lambda. Lambda checks Environment and Owner tags along with existing change tickets. If it is production, the workflow creates a ticket and requests approval. Once approved, Systems Manager Automation or an IaC workflow updates the rule. After remediation, AWS Config and Security Hub CSPM re-evaluate; the finding updates when the state changes.

Automation must be idempotent. EventBridge may redeliver events; workflows must not create duplicate tickets or repeat unintended configuration changes. Use finding ID, resource ARN, and processing state as deduplication keys. For potentially disruptive actions, require approval, rollback capability, and post-verification steps.

## 17. Updating Workflow and Notes on Findings

Use BatchUpdateFindings to update workflow status, notes, severity, confidence, criticality, and certain customer-editable fields. The API does not create new findings; providers use BatchImportFindings for findings they own.

Example updating a finding to RESOLVED:

~~~bash
aws securityhub batch-update-findings \
  --finding-identifiers Id="FINDING_ID",ProductArn="PRODUCT_ARN" \
  --workflow Status="RESOLVED" \
  --note Text="Remediated by change CHG-1234 and verified.",UpdatedBy="security-operations" \
  --region ap-southeast-1
~~~

You must pass both the Id and ProductArn of the finding. Retrieve these values via GetFindings. BatchUpdateFindings supports up to 100 findings per request and updates may take a few minutes to reflect.

Setting Workflow.Status to RESOLVED records the customer's investigation outcome. It does not remediate the resource itself. To confirm remediation, verify the resource via API, Config, or appropriate operational checks. If the provider detects the issue recurring, the finding may return to a state requiring investigation.

## 18. Connecting Security Hub CSPM to Amazon Security Lake

Security Lake centralizes security data in OCSF format. When Security Hub CSPM findings are enabled as a Security Lake source, Security Lake receives findings via an independent stream and converts ASFF to OCSF.

This combination is useful when organizations need to:

- Retain security data long-term for investigation and analytics.
- Query findings alongside CloudTrail, VPC Flow Logs, and other sources.
- Build dashboards or correlation detections using OCSF-compatible analytics tools.
- Share data with SIEM systems without manually normalizing every provider format.

Security Lake does not manage findings or modify Security Hub CSPM settings. To update Workflow.Status or handle control findings, continue operating via the Security Hub CSPM console, API, or CLI. Security Lake serves data storage and analytics; Security Hub CSPM serves posture management and finding workflows.

## 19. Monitoring Data Quality and Troubleshooting

An aggregation system is only useful when coverage and input data are complete. When findings do not appear or security scores look abnormal, check in order:

| Symptom | Possible Cause | Troubleshooting Direction |
|---|---|---|
| No control findings | AWS Config not enabled or missing resource recording | Check recorder, resource types, and Region |
| Missing member account findings | Account not linked to delegated administrator or service not enabled | Check Organizations, service access, and account status |
| Missing findings from other Regions | Region lacks Security Hub CSPM enabled or is not linked | Check Region policies and home Region aggregation |
| Control status is Unknown | Config lacks data or check cannot determine result | Check Config recorder, permissions, and resource state |
| Duplicate findings | Multiple standards generating separate findings or duplicate integrations | Check consolidated control findings and ProductArn |
| Finding stays NEW after remediation | Check has not re-run or resource still fails requirement | Check Config evaluation and latest update timestamp |
| Finding disappears from list | RecordState is ARCHIVED or filter excludes record | Check RecordState and active filters |
| EventBridge not triggering | Incorrect source, detail-type, event pattern, or target permissions | Check EventBridge metrics, DLQ, and roles |
| Automation updates wrong finding | Filter too broad or relies on Title/Description | Use SecurityControlId, ProductArn, and ResourceId |
| Score does not match expectations | No data, suppressed, or archived findings affect calculation | Inspect individual controls and score timestamps |

During investigation, capture finding ID, ProductArn, account, Region, resource ARN, timestamp, severity, compliance status, and workflow status. Cross-check with the original provider and CloudTrail to determine which component created, updated, or suppressed the finding.

For permission errors, inspect IAM policies of operators, the delegated administrator, and roles used by EventBridge/Lambda/Step Functions. Never grant broad Security Hub admin permissions just to fix one workflow; scope down required actions and resources.

## 20. Security, Retention, and Cost Control

Findings may contain resource ARNs, configurations, network details, application metadata, and incident-related information. Protect them as sensitive operational data.

Protection principles:

- Grant finding view permissions only to those who need them.
- Separate read access, workflow updates, and standards administration.
- Control access to Security Lake, S3, and log destinations.
- Log changes via CloudTrail.
- Never include credentials, tokens, or sensitive data in notes or user-defined fields.
- Set retention periods aligned with investigative and compliance requirements.
- Define procedures for partner-submitted findings and validate provider trustworthiness.

Security Hub CSPM includes a 30-day free trial when first enabled for an account and Region. During the trial, Security Hub CSPM itself incurs no charges, though services it relies on such as AWS Config may incur separate fees. After the trial, CSPM costs depend on the number of security checks, finding ingestion events, and automation rule evaluations. Current pricing also includes an ongoing free tier of 10,000 finding ingestion events per month; check the pricing page and AWS Pricing Calculator to estimate actual costs.

The new AWS Security Hub has a separate pricing model based on monitored resources and additional capabilities such as threat analytics. Do not lump Security Hub CSPM, GuardDuty, Inspector, Macie, Security Lake, CloudWatch, and EventBridge costs into a single estimate. Source services, Config items, log storage, and data queries can incur separate charges.

Optimization measures:

- Enable only standards and controls aligned with protection and audit requirements.
- Use consolidated control findings to reduce duplicate findings.
- Use automation rules and insights to reduce manual work.
- Optimize logging and retention while keeping sufficient investigative data.
- Review account/Region coverage to avoid enabling services out of scope.
- Track costs by account, Region, and finding source.

## 21. Hands-On Scenario: Centralizing Findings for an Online Store

An e-commerce company runs applications across multiple AWS accounts: production, staging, development, and security tooling. The system uses CloudFront, ALB, EC2, ECS, S3, RDS, and Lambda. The security team wants to detect weak configurations, vulnerabilities, and attack indicators, then route findings to the appropriate owning teams.

An implementation plan:

1. Use AWS Organizations and designate a delegated administrator for Security Hub CSPM.
2. Create declarative policies for production, staging, and development OUs; enable FSBP in required Regions.
3. Enable AWS Config recorders for relevant resource types in all in-scope accounts and Regions.
4. Enable Security Hub CSPM, GuardDuty, Inspector, Macie, and IAM Access Analyzer as needed.
5. Configure cross-Region aggregation to a home Region so the security team has a single pane of glass.
6. Enable consolidated control findings to reduce duplicate findings across standards.
7. Create custom insights for CRITICAL/HIGH findings, findings by application owner, and unresolved findings.
8. Create automation rules to attach ticket IDs, adjust severity by resource criticality, and suppress approved exceptions.
9. Use EventBridge to create tickets, send SNS alerts, and invoke Step Functions or Systems Manager Automation when remediation is needed.
10. Store findings in Security Lake for long-term investigation and correlation analysis.
11. Track security score, control status, account/Region coverage, finding age, and time to resolution.

Example assignment rules:

| Finding Category | Owner | Action |
|---|---|---|
| Public access or overly permissive security group | Cloud platform | Inspect network/resource policies and remediate |
| EC2/ECR/Lambda vulnerability | Application owner | Upgrade versions, rebuild images, or deploy patches |
| GuardDuty threat finding | Security operations | Investigate activity, credentials, and blast radius |
| S3 sensitive data finding | Data owner and security | Verify data, policies, encryption, and access |
| IAM external access | IAM team | Review trust policies, resource policies, and external principals |

Measure effectiveness using metrics: percentage of accounts/Regions covered, percentage of controls with data, count of NEW CRITICAL/HIGH findings, finding age, mean time to assign owner, remediation time, and recurrence rate.

## Conclusion

AWS Security Hub CSPM aggregates findings from security checks, AWS services, and partners into ASFF so security teams can filter, prioritize, and track investigations. Aggregation quality depends on AWS Config recording, enabled standards and controls, integrations, account/Region coverage, and workflow management processes.

In multi-account deployments, AWS Organizations declarative policies are now the recommended approach to manage Security Hub CSPM configurations; cross-Region aggregation remains a separate configuration to funnel findings to a home Region. Automation rules and EventBridge turn findings into tickets, alerts, and controlled remediation. The new AWS Security Hub adds OCSF, exposure correlation, and attack paths to enrich risk context when combining multiple security sources.

## References

- [What is AWS Security Hub CSPM?](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html)
- [What are AWS Security Hub and Security Hub CSPM?](https://docs.aws.amazon.com/securityhub/latest/userguide/)
- [AWS Security Finding Format (ASFF)](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)
- [Creating and updating findings in Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html)
- [Understanding security standards](https://docs.aws.amazon.com/securityhub/latest/userguide/standards-view-manage.html)
- [Standards reference for Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/standards-reference.html)
- [Enabling and configuring AWS Config](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-setup-prereqs.html)
- [Evaluating compliance status and control status](https://docs.aws.amazon.com/securityhub/latest/userguide/controls-overall-status.html)
- [Setting the workflow status of findings](https://docs.aws.amazon.com/securityhub/latest/userguide/findings-workflow-status.html)
- [Consolidated control findings](https://docs.aws.amazon.com/securityhub/latest/userguide/controls-findings-create-update.html)
- [Managing accounts with declarative policies](https://docs.aws.amazon.com/securityhub/latest/userguide/accounts-orgs-policies.html)
- [Security Hub CSPM policy syntax and examples](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_security_hub_cspm_syntax.html)
- [Declarative policies and central configuration](https://docs.aws.amazon.com/securityhub/latest/userguide/orgs-policies-and-central-config.html)
- [Understanding cross-Region aggregation](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-aggregation.html)
- [Enabling cross-Region aggregation](https://docs.aws.amazon.com/securityhub/latest/userguide/finding-aggregation-enable.html)
- [AWS service integrations with Security Hub CSPM](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-internal-providers.html)
- [Automatically modifying and acting on findings](https://docs.aws.amazon.com/securityhub/latest/userguide/automations.html)
- [Configuring EventBridge for Security Hub findings](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-cwe-all-findings.html)
- [AWS Security Hub CSPM events in EventBridge](https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-securityhub.html)
- [Security Hub CSPM findings in Security Lake](https://docs.aws.amazon.com/security-lake/latest/userguide/security-hub-findings.html)
- [Introduction to the new AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub-v2.html)
- [AWS Security Hub CSPM pricing](https://aws.amazon.com/security-hub/cspm/pricing/)
- [AWS Security Hub unified experience pricing](https://aws.amazon.com/security-hub/pricing/)
