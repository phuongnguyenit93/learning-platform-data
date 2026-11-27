# Assessing Security Posture with Microsoft Defender for Cloud

A system running smoothly on Azure is not necessarily configured securely. Virtual machines may lack updates, storage accounts may allow public access, applications may use overly broad permissions, or critical data may not be properly monitored. To manage these risks across multiple subscriptions and resource groups, an organization needs a continuous way to gain visibility into security configurations, identify weaknesses, and track remediation.

**Microsoft Defender for Cloud** is Microsoft's cloud security posture management and workload protection service. This lesson focuses on how to use the **Cloud Security Posture Management (CSPM)** capabilities of Defender for Cloud to assess Azure resources: reviewing recommendations, understanding **Secure score**, prioritizing risks, performing remediation, and verifying results. This is part of deploying, monitoring, and protecting application architectures on Azure, alongside identity management with Microsoft Entra ID, organizing resources by subscription/resource group, network controls, and data management.

## Learning Objectives

After this lesson, you will be able to:

1. Explain the concept of security posture and distinguish posture management from threat detection.
2. Identify the key components in Defender for Cloud used for security assessments.
3. Interpret Secure score, recommendation statuses, and affected resource scopes.
4. Assess an Azure subscription using the Azure portal following a repeatable process.
5. Prioritize, assign ownership, remediate, and verify security findings.
6. Distinguish technical assessments from compliance certification and recognize the limitations of assessment results.

## 1. What Is Security Posture?

**Security posture** reflects how well an organization's resources, configurations, identities, and processes meet required security controls at a given point in time. Rather than only asking "is an attack happening right now?", a posture assessment asks:

- Which resources exist and under which governance scope do they fall?
- Which configurations fail to meet policies or recommendations?
- Which weaknesses could expose data or services?
- Which issues need to be fixed first, and who is responsible?
- After remediation, what evidence demonstrates that risk has been reduced?

For example: an Azure Storage Account may function normally while still allowing overly broad access from public networks. This is a **security posture** issue even when there is no evidence of exploitation. If the system detects anomalous access patterns or malicious activity against the data, that is a **threat detection and response** issue.

Defender for Cloud supports both directions, though features and protection scope vary by service plan.

| Capability | Primary Question | Example Outcome |
|---|---|---|
| CSPM — Cloud Security Posture Management | What configuration and governance weaknesses exist in the system? | Recommendations on permissions, networking, updates, or data protection settings |
| CWPP — Cloud Workload Protection Platform | Does a workload show signs of being attacked or exploited? | Security alerts for servers, databases, storage, or other services when the corresponding protection plan is enabled |
| Regulatory compliance governance | Which standards or requirements do measured controls satisfy? | Status of controls mapped to a standards framework |

**Important:** A recommendation indicates a condition to evaluate and remediate; it does not automatically prove an incident has occurred. Conversely, having no attack alerts does not mean current configurations are secure.

## 2. What Does Defender for Cloud Provide?

Defender for Cloud aggregates information about resources and security findings across the Azure scopes it is authorized to observe. Common CSPM-related capabilities include:

- **Asset inventory / Inventory:** discover resources and find resources with associated findings.
- **Security recommendations:** specific checks on configuration and security status, accompanied by affected resources, risk descriptions, and remediation guidance.
- **Secure score:** a composite metric to track adoption of scored security controls.
- **Security controls:** groups of recommendations related to a security objective, such as managing permissions or restricting network access.
- **Regulatory compliance:** shows the status of controls mapped to built-in or configured standards and policy sets.
- **Attack path analysis and advanced CSPM capabilities:** can help analyze potential chains leading to critical assets when the service plan, environment, and support conditions align.
- **Workflow automation and governance integrations:** helps route findings into remediation workflows, alerts, or work-tracking systems as configured by the organization.

Foundational CSPM visibility and recommendations are available without enabling paid workload protection plans. Advanced capabilities, such as Defender CSPM or workload-specific Defender plans, may incur charges and have limitations by resource type or region. Before enabling any plan, review **Environment settings**, subscription scope, included features, and current Microsoft pricing pages. Do not assume that opening the Defender for Cloud blade means all features are already activated.

### Scope and Data Sources

In Azure, operators typically start from one or more **subscriptions**. Defender for Cloud can aggregate resources across connected or authorized scopes. When an organization connects AWS accounts, GCP projects, or Azure Arc-enabled servers, visibility also depends on the corresponding connectors, enabled plans, and collection settings.

Results must always be interpreted alongside the **measurement scope**: a high score in a sandbox subscription does not reflect the security posture of an unassessed production subscription.

## 3. Secure Score: Reading Its True Meaning

**Secure score** is a metric summarizing adherence to scored controls within the assessed scope. Related recommendations are grouped into security controls. Each control contributes points according to Defender for Cloud rules, based on the state of the resources to which that control applies.

Hypothetical example: the dashboard shows a subscription's Secure score is **68%**. This indicates there are controls that can be improved; it does **not** mean the subscription is "68% secure," nor can you conclude the probability of attack is 32%. It is a management indicator for prioritization under the product's scoring rules.

When reading Secure score, check:

1. **Scope:** which subscription or set of subscriptions does the score belong to?
2. **Security control:** which control groups are losing the most points?
3. **Recommendation:** which specific condition is preventing full points?
4. **Affected resources:** which resources are marked unhealthy?
5. **Max score / potential increase:** how much could improving a control impact the overall metric?
6. **Trend over time:** did the score change because configurations were fixed, new resources were added, or assessment rules changed?

Do not optimize the score mechanically. A recommendation with a small Secure score impact can still be urgent if it involves customer data or servers directly exposed to the Internet. Conversely, a recommendation that only makes sense in a specific architectural context may require an exception analysis before enforcement.

## 4. Understanding a Security Recommendation

A recommendation is the core unit of action when assessing security posture. Exact content may vary by service, UI version, policy, and active plan; typically, operators should look for:

| Information Field | How to Use It |
|---|---|
| Name and description | Understand which condition is being evaluated |
| Severity / risk | Identify the severity level rated by the system |
| Status | Determine healthy, unhealthy, not applicable, or equivalent status |
| Affected resources | List exact resource IDs, subscriptions, and resource groups to address |
| Remediation steps | Find fix instructions, supported actions, and impacts to consider |
| Secure score impact | Understand the expected impact of improving a scored control |
| Exemption / governance | Record exemptions or assignees according to the organization's mechanisms |

**Healthy** generally means the evaluated condition is currently satisfied. **Unhealthy** indicates the resource does not yet meet the condition. **Not applicable** indicates the check does not apply to that resource or scenario. New findings may take time to refresh after configuration changes. Read each recommendation rather than relying solely on colors or counts.

Some checks are generated from **Azure Policy** or tied to policy assessments. Recommendations can depend on which policies are assigned, which protection plans are enabled, and what data has been collected successfully. Thus, two subscriptions can have different recommendation sets even if they use similar services.

### Interpretation Example

Suppose a recommendation reports **"Storage accounts should restrict public network access"** and lists two affected storage accounts. The operator should not immediately block all public access, but instead ask: which applications access this account, does traffic currently flow over the public endpoint or a private endpoint, are there batch jobs outside the Azure network, and would the change cause an outage?

After defining the target design, the team can apply appropriate network restrictions, test application connectivity, and wait for re-evaluation. The status turning healthy is **configuration evidence** that the setting improved; verifying business-level security still requires testing access and data permissions.

## 5. Preparation Before Assessment

An exercise in reading and analyzing security posture can be performed in read-only mode without necessarily modifying resources.

### 5.1. Define the Scope

Record:

- The signed-in Microsoft Entra tenant.
- The subscriptions and resource groups belonging to the workload under assessment.
- The environment (dev/test/prod), application group, and owners.
- Critical services: Azure Virtual Machines, App Service, Azure SQL Database, Storage Accounts, Virtual Networks, Key Vault, and identity services.
- Critical data or business processes to guide risk prioritization.

Throughout our running example, suppose the sales system has subscription **sub-sales-prod**, resource group **rg-sales-prod**, API on App Service, transaction data on Azure SQL Database, product images on a Storage Account, and keys/secrets on Key Vault. These names are illustrative examples, not actual existing Azure resources.

### 5.2. Verify Access Permissions

To view security information, the account needs appropriate read permissions on the subscription or resource group, such as a security reader role like **Security Reader** within the granted scope. Actions like modifying configurations, creating exemptions, changing policies, or enabling Defender plans require separate permissions and may require approval.

If you do not see a subscription or a recommendation, check the tenant, scope, role assignments, and Defender for Cloud configuration before concluding there are no issues. Do not elevate your own permissions merely to complete a lab exercise.

### 5.3. Check Plans and Costs

In **Environment settings**, identify which subscriptions are monitored and which Defender plans are enabled. Record currently available capabilities before running an assessment. Enabling a paid Defender plan or advanced scanning feature may incur costs; only make changes after approval from the subscription owner.

## 6. Hands-On Assessment Using the Azure Portal

Page names and layouts may change across UI versions. The process below focuses on the tasks to perform so it remains applicable even if menus shift slightly.

### Step 1: Open Defender for Cloud and Select the Scope

1. Sign in to the **Azure portal** at https://portal.azure.com.
2. Search for **Microsoft Defender for Cloud** using the service search bar.
3. Select the subscription scope you have read access to and ensure it is the subscription for the workload under assessment.
4. Record the assessment timestamp, resource count, and enabled plans.

If the scope shows multiple subscriptions, use filters to avoid mixing resources across environments. All statements about scores and recommendations must be tied to a specific scope.

### Step 2: Review Security Overview and Secure Score

On the overview page, locate **Secure score** or the corresponding posture management section. Read the current score and inspect the security controls contributing to it. Select a control with unhealthy resources and examine the recommendations inside.

Record at least three details: the score at assessment time, the controls needing the most improvement, and which resource groups contain the most affected resources. Do not draft a remediation plan before understanding the business role of those resources.

### Step 3: Filter and Inspect Recommendation Details

Open **Recommendations**, then:

1. Filter by subscription or resource group.
2. Review recommendations with unmet status and relevant priority/risk levels.
3. Open a recommendation to read the rationale, configuration requirement, and remediation guidance.
4. List the affected resources with their exact resource IDs.
5. Identify estimated effort, responsible owner, and potential disruption.

When a recommendation affects multiple resources, do not assume every resource carries the same risk level. For example, a VM in an isolated test network and a VM running a payment system with Internet access require different priorities.

### Step 4: Use Inventory to Check Coverage

Open **Inventory** if supported by your active scope and plan. Search for a specific resource, such as the Storage Account holding application data, and inspect related findings and statuses.

Cross-check this list against the expected list of resources in the subscription. Missing resources may be due to scope, permissions, connectors, data collection status, or resource type support characteristics. Investigate coverage before claiming all resources have been assessed.

### Step 5: Review Regulatory Compliance

If the **Regulatory compliance** section has data, select the standards framework applicable to the organization. Inspect which controls are passed, failed, or have no data, and trace back to the underlying recommendations or resources.

This dashboard helps track technical controls against mapped standards. It does not automatically certify that the organization meets all legal, contractual, or audit requirements. Requirements involving human processes, business evidence, and non-Azure controls must still be assessed separately.

### Step 6: Record a Baseline and Create a Plan

Save a brief report containing scope, assessment date, Secure score, critical recommendations, affected resources, priority, assignee, and target re-verification date. This serves as the **baseline** to compare before and after remediation.

For production environments, configuration changes must go through the organization's change management process. If you are only doing a read-only assessment exercise, you can stop at recording the baseline without modifying resources.

## 7. Prioritizing Remediation by Real-World Risk

Recommendations and Secure score help organize work, but remediation priority must reflect the application's context.

Consider:

1. **Exposure level:** is the resource reachable from the Internet, from the internal network, or only via private connectivity?
2. **Data sensitivity:** does the resource store personal data, payment data, credentials, or test data?
3. **Exploitability:** are there access paths, permissions, or settings that facilitate an attack?
4. **Business impact:** if the resource is compromised or goes down, what damage does the business suffer?
5. **Blast radius / prevalence:** is a misconfiguration repeated across many resources or subscriptions?
6. **Feasibility and remediation impact:** is there a safe, low-disruption fix that can be executed early?

Hypothetical example for subscription **sub-sales-prod**:

| Hypothetical Finding | Context | Initial Assessment | Planned Action |
|---|---|---|---|
| Storage holding order documents has overly broad network access | Sensitive data, has integrations over public network | High priority | Identify valid traffic flows, design private endpoint or appropriate firewall restrictions |
| Production VM has management port open to all addresses | Direct attack surface, high admin privilege | Very high priority | Narrow source access, adopt secure management access, test before/after change |
| A test account is missing an owner tag | No sensitive data, low direct impact | Lower priority | Add tags and accountability policy |
| Key Vault access permissions are overly broad | Stores secrets used by production API | High priority | Review role assignments and reduce permissions, test app access |

This is illustrative data showing the reasoning process, not actual Defender for Cloud output. Final priorities must be confirmed by the responsible owner based on real resources.

### Organizing Work with Accountability

Each finding should have at minimum:

- **Owner:** the person or team with the permissions and knowledge to fix it.
- **Priority and rationale:** clearly state the asset, impact, and exposure path.
- **Action:** configuration change, architectural change, or controlled risk acceptance.
- **Due date:** aligned with risk level and operational capacity.
- **Verification evidence:** recommendation status, Azure configuration, and test results.

Do not use the number of closed recommendations as the sole metric. A flawed change can increase Secure score while causing a service outage or introducing new risks.

## 8. Remediating and Verifying Results

Recommendations in Defender for Cloud may include manual instructions, links to resources, or automated remediation capabilities for certain conditions. Availability of **Fix**, **Quick fix**, or remediation options depends on the recommendation, service plan, and user permissions.

Recommended workflow:

1. **Read the exact requirement:** e.g., restricting network access, not merely "improve security."
2. **Analyze impact:** identify all dependent applications, identities, network addresses, and services.
3. **Choose the minimal change:** use RBAC, network rules, managed identities, or appropriate protection settings.
4. **Test in a suitable environment:** prefer testing in a staging/test environment whenever possible.
5. **Execute approved change:** record who made the change and the before/after configuration.
6. **Test the application:** confirm legitimate users still have access, data flows work, and no new errors appear in logs.
7. **Wait for re-evaluation:** recommendations and Secure score may take time to update after changes.
8. **Verify from two sources:** check status in Defender for Cloud and actual configuration on the resource.

If the recommendation remains unhealthy, re-check the technical condition, scope, ingestion latency, and any remaining affected resources. If the condition is met but the system has not re-evaluated yet, monitor or investigate data collection issues; do not self-certify as secure simply because the team clicked save.

### When a Recommendation Cannot Be Followed Directly

A legacy system may not be compatible with the recommended security setting. In this case, record a **controlled exception**: technical justification, applicable resources, residual risk, compensating controls, approver, and review expiration date. If the environment supports exemptions or governance workflows, use the feature matching organizational policy.

**An exemption does not make the risk disappear.** It indicates the organization has made a governance decision regarding that check. Never create exemptions solely to make reports or Secure score look better.

## 9. Querying Assessments Across Scopes with Azure Resource Graph

Beyond the Azure portal, users with appropriate read permissions can use **Azure Resource Graph** to aggregate certain security assessment data. This is useful when viewing multiple subscriptions or exporting lists for analysis. Data schemas may vary by assessment type and supportability; inspect actual data before automating.

The following KQL query illustrates counting assessments by status:

~~~kusto
securityresources
| where type =~ "microsoft.security/assessments"
| extend assessmentStatus = tostring(properties.status.code)
| summarize totalAssessments = count() by assessmentStatus
| order by totalAssessments desc
~~~

To view assessment names alongside their statuses:

~~~kusto
securityresources
| where type =~ "microsoft.security/assessments"
| extend recommendationName = tostring(properties.displayName),
         assessmentStatus = tostring(properties.status.code)
| project subscriptionId, name, recommendationName, assessmentStatus
| order by assessmentStatus asc
~~~

You can run these queries in **Resource Graph Explorer** when your account has permission to query the selected subscriptions and security assessment data is populated in the table. Results represent **assessment records**, not necessarily unique resource counts: a single resource can have multiple assessments. Therefore, do not use this total count as a direct substitute for Secure score or unhealthy resource counts shown on another page.

If the query returns no results, check the selected subscriptions, access permissions, collection prerequisites, and returned resource types. Do not prematurely conclude that the subscription has no security risks.

## 10. Integrating Posture Assessment with Azure Governance

A security report only holds lasting value when findings translate into operational work. In an organization using multiple subscriptions and resource groups, tie the CSPM process to existing governance mechanisms:

| Azure Component | Role in the Process |
|---|---|
| Microsoft Entra ID | Identifies users, groups, workload identities, and authentication methods |
| Azure RBAC | Controls who can view and modify security settings at each scope |
| Management group / subscription | Defines governance boundaries, environment separation, and accountable units |
| Resource group / tags | Helps identify application owners and finding remediation routing |
| Azure Policy | Enforces or evaluates configuration rules within assigned scopes |
| Defender for Cloud | Aggregates recommendations, posture metrics, and supported security insights |
| Azure Monitor | Tracks operational metrics, logs, and alerts after changes |
| Cost Management | Tracks security service costs and the financial impact of enabled configurations |

A practical division of responsibility is: the security team defines configuration standards and priorities, the platform team manages policies and subscription boundaries, and application teams remediate configurations for workloads they own. Teams jointly verify outcomes using technical evidence.

### Tracking Trends Instead of One-Time Snapshots

Establish a recurring assessment schedule and re-assess after major changes such as adding subscriptions, deploying new apps, opening public endpoints, altering network connectivity, or expanding permissions. In each period, compare:

- Secure score within the **same scope** and major changes to the control set.
- Outstanding high-risk recommendations.
- New resources lacking an owner or insufficient assessment coverage.
- Time from detection to remediation and verification.
- Exemptions nearing expiration or awaiting review.

When the score changes abruptly, check whether new resources, new configurations, new scopes, or evaluation logic updates occurred. Do not attribute every metric fluctuation to a single configuration fix.

## 11. Limitations and Common Misconceptions

**"A high Secure score means we cannot be attacked."** Secure score only reflects the scored controls within the assessed scope and point in time. It does not replace application security testing, vulnerability management, runtime monitoring, or incident response.

**"Having a recommendation means the system is compromised."** A recommendation describes an unmet configuration or posture condition; attack detection is a separate signal stream and depends on enabled protection plans.

**"Marking an exemption means it is fixed."** An exemption is a governance decision accepting a specific risk with clear justification and scope. Technical risk may still remain.

**"Once Defender for Cloud is enabled, every resource is scanned identically."** Scope, coverage, and data depend on subscriptions, resource types, connectors, permissions, plans, and collection configurations.

**"Regulatory compliance shows passed, so we are fully compliant with regulations."** The dashboard only provides evidence for mapped and evaluated controls. Compliance also involves policies, people, processes, records, and systems outside the product's scope.

**"Every recommendation can be fixed with one button."** Some conditions have remediation features, but many configurations require architectural changes, dependency identification, or business verification before execution.

**"Every Defender plan can be enabled at no cost."** Workload protection plans and advanced CSPM have separate billing mechanisms. Check scope, pricing, and approval before enabling.

## 12. Case Study Exercise

A subscription contains an e-commerce application with three tiers: App Service running the API, Azure SQL Database storing orders, and a Storage Account storing customer documents. The security team observes three hypothetical findings:

1. The Storage Account has network settings allowing broad access.
2. An application identity is granted permissions broader than actually needed on the resource group.
3. The subscription lacks an assigned owner to handle several medium-priority recommendations.

Create an action plan:

- Identify affected assets and data in each finding.
- Record scope, owner, exposure, and business impact.
- Order remediation steps and explain your reasoning.
- Identify technical changes that must be tested prior to rollout.
- Describe how to test the application and how to verify the recommendation turns healthy.
- Specify what data must be included in the security team's periodic report.

A sound plan typically prioritizes items that could expose customer data or allow an identity to escalate privileges, while mapping legitimate traffic flows to avoid breaking the application. Assigning remediation owners should happen immediately, even for lower-severity recommendations.

## 13. Practical Checklist

| Task | Completion Evidence |
|---|---|
| Identify subscription, resource group, and assessment date | Scope names, expected resource list, and baseline capture timestamp |
| Verify permissions and Defender plans | Recorded visibility, active plans, limits, and costs if any |
| Review Secure score | Score and controls needing improvement within the exact scope |
| Review recommendations | List of findings, resource IDs, statuses, and remediation guidance |
| Check asset inventory | Resource coverage confirmed or gaps documented |
| Review regulatory compliance if available | Failed controls and mapping limitations documented |
| Prioritize by business impact | Owner, due date, risk, and change plan |
| Remediate and test | Before/after configuration, functional and access control testing |
| Re-evaluate | Updated recommendations and Secure score; exemptions managed |
| Monitor periodically | Trend reports, remaining findings, and next actions |

## Self-Check Questions

1. How does security posture differ from detecting an active attack?
2. Does an 85% Secure score prove the probability of being attacked is only 15%? Why or why not?
3. When a recommendation reports a Storage Account has not restricted public access, what should you check before fixing it?
4. Why can two similar subscriptions display different numbers of recommendations?
5. When a recommendation turns healthy, what must the team do to ensure the application still works and access permissions are correct?
6. Why is a regulatory compliance dashboard insufficient to conclude an organization satisfies all legal requirements?
7. What is the difference between exempting a recommendation and actually remediating the configuration?
8. If the team is not permitted to enable a paid plan, what read and analysis steps can they still perform?

## References

- Microsoft Learn — *What is Microsoft Defender for Cloud?*: https://learn.microsoft.com/azure/defender-for-cloud/defender-for-cloud-introduction
- Microsoft Learn — *Cloud security posture management*: https://learn.microsoft.com/azure/defender-for-cloud/concept-cloud-security-posture-management
- Microsoft Learn — *Secure score and security controls*: https://learn.microsoft.com/azure/defender-for-cloud/secure-score-security-controls
- Microsoft Learn — *Review security recommendations*: https://learn.microsoft.com/azure/defender-for-cloud/review-security-recommendations
- Microsoft Learn — *Regulatory compliance dashboard*: https://learn.microsoft.com/azure/defender-for-cloud/regulatory-compliance-dashboard
