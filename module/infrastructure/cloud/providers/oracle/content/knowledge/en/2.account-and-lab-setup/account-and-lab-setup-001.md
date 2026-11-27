# Account Registration and Understanding Free Tier, Trial, and Paid Scope

## Objectives and Scope

In the **Account and Lab Setup** chapter of the Oracle Cloud Infrastructure (OCI) module, the first step is identifying which type of account you are using, what resources you are allowed to create, and when you will be billed. This provides the foundation for deploying labs covering tenancy, compartments, IAM, VCN, Compute, storage, and Oracle databases in a controlled manner.

After this lesson, you will be able to:

- Prepare registration details, choose a home region, and verify the account after activation.
- Distinguish between Always Free, Free Trial, and Pay As You Go paid accounts.
- Classify resources that can be kept when the trial expires and resources that must be handled beforehand.
- Create a lab plan with resource limits, cost tracking, and a rebuild strategy.

This lesson uses public policies verified as of **November 20, 2026**. Entitlements, supported regions, and limits are subject to change; during practice, cross-check official documentation against the subscription, usage, and configuration details inside your own tenancy. Do not rely on a single screenshot or an outdated tutorial as the sole basis for concluding that a resource is free.

## 1. Understanding Three Concepts Before Registering

**Free Tier** is the program name consisting of two parts: **Always Free** benefits and a time-limited **Free Trial**. **Pay As You Go (PAYG)** is a paid account model billed by usage. An account in a trial can still use Always Free resources; when upgraded to PAYG, the account can still receive eligible Always Free entitlements. Refer to [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).

| Concept | Nature | How to use in learning |
| --- | --- | --- |
| Always Free | Specific usage levels or configurations provided free under service conditions | Serves as a baseline for small labs; check total usage before creating more |
| Free Trial | Time-limited promotional credits used to try eligible services | Short-term experiments with a scheduled end date and data export |
| PAYG | Paid usage-based subscription that retains eligible free entitlements | Used when a lab requires configurations outside the free scope and has a cost estimate |

A cost figure currently showing zero is not enough to prove a service belongs to Always Free. It may be covered by trial credits or the billing data may not have updated yet. The question to answer is: **which entitlement does this configuration qualify for, within what scope, and until when?**

### 1.1. Trial Credits Are a Limited Promotional Allowance

According to the [OCI Free Tier documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm), the trial program provides **300 USD in credits, valid for up to 30 days**, applicable to eligible services. The trial ends when the time expires or the credits are exhausted, whichever comes first; eligibility also depends on the country and registration terms stated on the [Free Tier page](https://www.oracle.com/cloud/free/).

Credits are not withdrawable cash and are not a monthly recurring budget. When planning, record the expiration date and remaining balance shown in the Console instead of assuming every account receives the exact same offer.

Learning example: a lab testing a database outside Always Free is scheduled to run for two hours, export its data, and be deleted in the same session. Having plenty of remaining credits is not a reason to leave resources running until the final day.

### 1.2. Free Entitlements Are Conditional per Resource

When inspecting a resource, review all of the following together:

1. **Service and configuration:** machine type, OCPU count, RAM, storage type, or database Always Free option.
2. **Entitlement scope:** tenancy-wide total, monthly total, per-region, or per-resource.
3. **Dependent components:** boot volumes, backups, data transfer, and integrated components.
4. **Already consumed capacity:** older resources can still consume your allowance even if the current lab has just started.

In OCI, a *shape* is the Compute configuration; a boot volume is the machine's startup disk. Therefore, choosing the right shape only checks part of a lab.

## 2. Preparing Information and Choosing a Home Region

### 2.1. What You Need to Prepare

Prepare an email address you control long-term, a phone number, accurate contact information, and a valid payment method. Oracle allows one Free Trial or Always Free account per person. The FAQ currently accepts credit cards and debit cards that function like credit cards; it does not accept cards requiring a PIN, virtual cards, single-use cards, or prepaid cards. See [Oracle Cloud Free Tier FAQ](https://www.oracle.com/cloud/free/faq/).

Use a dedicated password for your cloud account and store it in a password manager. Do not send passwords, OTP codes, card details, or private keys to lab assistants. For school- or company-issued accounts, use the credentials provided by your administrator instead of registering an extra account to obtain credits.

Card verification may place a **temporary authorization hold** (*authorization hold*). This hold is separate from service usage charges; the release time depends on your bank. Oracle describes this mechanism in [Managing Account Upgrades and Payment Method](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/changingpaymentmethod.htm). Check the transaction status with your bank if needed, rather than only looking at a balance-decrease notification.

### 2.2. Home Region Is a Decision to Weigh Beforehand

The home region is the geographic region where your account and initial identity resources are created. Oracle explicitly states that **you cannot change your home region after signing up** in [Managing Regions](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingregions.htm). Always Free Compute and Autonomous Database instances must be created in the home region according to the [Free Tier documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

Before choosing, evaluate:

- Which regions actually appear in the sign-up form and offer the services you need to study?
- Is network latency from your location suitable for SSH, Console, and test applications?
- Does your lab data have specific location requirements from your organization?
- Do your lab guides use a different region or Availability Domain than your account?

For learners in Vietnam, you can evaluate the Asian regions offered during sign-up, but verify the current list yourself. Close geographic proximity does not guarantee available capacity for free shapes. Do not pick a region solely because a blog post claims it can always provision instances.

## 3. Registration Flow and First-Time Verification

Follow the [Sign Up for the Free Oracle Cloud Promotion guide](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm):

1. Start from the [Oracle Cloud Free Tier page](https://www.oracle.com/cloud/free/) and choose to sign up.
2. Enter your country, full name, and email; complete the email verification step.
3. Set a password, cloud account name, and choose the home region you evaluated.
4. Fill in your address and phone number, and complete the required verification steps.
5. Add a payment method; review the terms before submitting the trial request.
6. Wait for tenancy provisioning, receive the welcome email, and sign in to the OCI Console.

The cloud account name identifies your cloud account when signing in. Once inside the Console, record your tenancy name, home region, active identity domain, and subscription details so you can verify the correct environment on future logins. Save these details in appropriate personal notes; do not commit authentication secrets to a source repository.

### 3.1. Verify the Account Before Creating Instances

There is no need to create Compute or Database resources during this check. The goal is to establish clear evidence of your environment:

| Item to verify | Result to record |
| --- | --- |
| Sign-in | Signed into the right tenancy and user, completed required MFA |
| Region | Know your home region and the currently selected region in the Console |
| Subscription | Know whether the account is in trial, post-trial Free Tier, or PAYG |
| Entitlements | Know the remaining credit balance and expiration date if on trial |
| Billing | Distinguish card verification from a paid account upgrade |
| Resource creation capability | Know where to check Limits, Quotas and Usage |

Menu names and locations may change. You can search by function such as Billing & Cost Management, subscription, Cost Analysis, or Limits, Quotas and Usage; read the page content carefully before confirming any account-modifying action.

### 3.2. Complete Access Protection

Complete MFA enrollment according to your identity domain's sign-in policy, store recovery options in an appropriate place, and test signing in again before ending the setup session. Do not disable MFA requirements just to bypass the login step. Console MFA is described by Oracle in [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

For subsequent labs, you should create a user or group granted permissions as needed and a dedicated compartment for labs. Administrator accounts used for identity and billing management should be protected separately; avoid sharing a single administrator login across an entire class. Detailed IAM configurations will be covered in the corresponding lesson.

## 4. Reading Always Free Scope by Resource

At the reference date of this lesson, [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) describes:

| Component | Entitlement stated in documentation |
| --- | --- |
| Compute AMD | Up to two VMs using the `VM.Standard.E2.1.Micro` shape |
| Compute Arm A1 | 1,500 OCPU-hours and 9,000 GB-hours of RAM per month for `VM.Standard.A1.Flex`; equivalent to a total of 2 OCPUs and 12 GB RAM for an Always Free tenancy |
| Block Volume | 200 GB shared across eligible boot volumes and block volumes |

These numbers represent total entitlements, not allowances reset per VM or per compartment. The documentation also notes that idle Always Free VMs may be reclaimed. Therefore, keep source code and important data in appropriate locations, and prepare a way to rebuild your lab.

Calculation example set by this lesson: two A1 machines running concurrently for 100 hours, each using 1 OCPU and 6 GB RAM, will consume:

```text
OCPU-hours = (1 × 100) + (1 × 100) = 200
GB-hours RAM = (6 × 100) + (6 × 100) = 1,200
```

This shows how to sum usage across multiple machines, not a conclusion that the entire lab is free. You still must check remaining runtime in the month as well as attached storage and networking components.

A Java lab might include a VM running the application, a volume holding the OS, a bucket storing test data, and a database. List every component before deploying. One eligible VM does not automatically prove that the database or every option on the same creation screen is also eligible.

For Databases, verify the Always Free toggle and the limits displayed in the creation workflow. Do not generalize that every service named Oracle Database, every Autonomous Database configuration, or every upgrade option falls within the free tier.

## 5. Distinguishing Creation Permissions, Service Limits, Quotas, and Capacity

Failure to create a resource does not necessarily mean you ran out of credits. Distinguish the following layers:

| Control layer | Question to answer | Where to check |
| --- | --- | --- |
| IAM | Does the user have permission to perform the action in this compartment? | User, group, policy, and selected compartment |
| Service limit | How much of this resource does Oracle allocate to the tenancy in this scope? | Limits, Quotas and Usage, matching service and region |
| Compartment quota | How much does the administrator allow this compartment to use? | Quota policy applied to the compartment |
| Capacity | Does the underlying infrastructure currently have room to provision the requested resource? | Provisioning error message and deployment scope |
| Entitlement | Is that usage covered by the free allowance? | Free Tier terms and total usage |

Oracle sets service limits; administrators set compartment quotas. Having available quota does not mean the resource is free. Refer to [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm) and [Overview of Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm). Capacity is a separate infrastructure availability layer, described in [Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

Example: a lab needs another VM but is rejected. Before modifying the configuration, record the exact error message and timestamp. If the error relates to access rights, review IAM; if it relates to limits, check usage and quotas; if it is out of capacity, do not automatically switch to a larger shape and assume it remains free.

## 6. What Happens When the Trial Ends?

If you do not upgrade, the account remains active and can continue using eligible Always Free resources. Paid resources created with trial credits will be reclaimed by Oracle if the account is not upgraded. Notably, current documentation warns that A1 usage exceeding the Always Free tenancy allowance may result in all existing A1 instances being disabled and then terminated after 30 days if not upgraded. See [When Your Trial Period Ends](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

Do not treat the post-trial handling window as a backup schedule. Choose one of three paths for each resource **before** the promotion ends:

| Decision | Work to complete |
| --- | --- |
| Keep within Always Free scope | Cross-check total usage and adjust configurations early enough |
| End the experiment | Export data, keep necessary configuration descriptions, delete unneeded resources |
| Continue with PAYG | Estimate costs, audit existing resources, and complete an intentional upgrade |

A sample study plan might dedicate the first session to account setup, subsequent sessions to IAM and networking, and only then test credit-consuming services. Set a self-review checkpoint a few days before the trial deadline. This checkpoint is chosen by you to allow time for cleanup; it is not a grace period guaranteed by Oracle.

After scaling down configurations, check total remaining resources. Deleting only a VM while leaving dependent resources behind can cause your lab inventory to misrepresent what is still provisioned.

## 7. Upgrading to PAYG When There Is a Clear Need

PAYG is suitable when labs need to exceed the Always Free allowance, require services outside the free scope, or need to keep paid resources after the trial. Upgrading is accepting the billing mechanism for corresponding usage; it should not be done just to test whether a provisioning error goes away.

Oracle provides the upgrade workflow in the Console; for supported flows, look under **Billing & Cost Management → Upgrade and Manage Payment**. Upgrade and payment management permissions belong to the Administrators group. Exact flows may vary by country and account; see [Managing Account Upgrades and Payment Method](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/changingpaymentmethod.htm).

Before confirming:

1. Inventory all existing resources, including those created experimentally using credits.
2. Finalize the configuration to keep, runtime duration, and the person responsible for lab cleanup.
3. Build a cost estimate using the [OCI Cost Estimator](https://www.oracle.com/cloud/costestimator.html), reading the billing unit of each line item.
4. Review the terms, payment method, and applicable taxes or currencies.
5. Set up appropriate cost tracking and resource limits.

After upgrading, re-read your subscription type and promotion status in the Console. Do not treat remaining trial credits as a reason to skip checking running resources. Eligible Always Free usage may still remain free; usage outside those conditions must be evaluated under paid billing.

## 8. Setting Up Cost Controls for Labs

### 8.1. Use Compartments to Scope Practice

Creating a dedicated lab compartment, such as `oci-learning`, gives you a clear boundary when granting permissions, listing resources, and tracking costs. Creating a compartment does not automatically set a budget or block paid resources.

For each lab, record at minimum the resource name, service, region, compartment, purpose, and planned deletion date. When learning automation, keep deployment configurations so you can rebuild the environment, rather than leaving resources running indefinitely out of fear of losing configuration.

### 8.2. Budgets Send Alerts

An OCI Budget is a **soft threshold** for tracking actual or forecasted spending and sending alerts. Budgets do not automatically block usage when a threshold is reached. Oracle currently evaluates alerts on a 24-hour cycle; do not treat budget emails as an instant cost shutoff mechanism. Refer to [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

Personal planning example: if you accept at most 10 USD for a paid lab in a month, you can set alerts at 50%, 80%, and 100%, and establish a personal rule to stop the experiment upon receiving the first unexpected alert. These thresholds are work-organization examples, not a guarantee that your bill will stop at 10 USD.

### 8.3. Quotas Limit Resource Quantities

Compartment quotas restrict the quantity of resources for supported services—for example, limiting the number of cores provisioned in a lab. Quota policies can be created from **Limits, Quotas and Usage** as described in the [Compartment Quotas documentation](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm).

Quotas control specified resource units, not a monetary cap across all services. When designing limits, review dependent resources and quota-editing permissions as well; if the learner can raise the quota themselves, that limit is no longer an independent constraint on them.

### 8.4. Cost Analysis Helps Locate Cost Sources

Use **Cost Analysis** to view costs over time, filter by compartment or region, and group by service. When you need to identify the exact consuming item, inspect the product description or SKU. Oracle documentation currently notes that data can take up to **48 hours** to appear; seeing zero right after creating a resource does not prove there is no charge. See [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

A useful practice habit is writing down an estimate before running, inventorying after the session, and reconciling against reports once data updates. If an unplanned line item appears, locate the corresponding resource before continuing to create more.

## 9. Cleaning Up Labs Component by Component

**Stop** and **Terminate** serve different purposes. Billing while a VM is stopped depends on the shape; shutting down the OS inside the VM does not automatically stop Compute billing. See [Resource Billing for Stopped Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

When terminating an instance, OCI provides an option to keep the boot volume. Retained volumes must be tracked separately; terminate is not a reversible operation. See the [Compute FAQ](https://www.oracle.com/cloud/compute/faq/).

Your end-of-lab procedure should follow an established checklist:

1. Export data you need to keep and verify the export before deleting.
2. Delete or stop resources in accordance with the session goal and corresponding billing policy.
3. Check boot volumes, block volumes, backups, buckets, databases, and created networking components.
4. Retain only components with a specific justification, an owner, and a next review date.
5. Re-check every region you used; then reconcile against Cost Analysis once data updates.

Example: if you only learned how to create and connect to a VM, the artifact to keep can be your notes and deployment configuration. You do not need to leave a machine running just to prove you completed the exercise.

## 10. Troubleshooting Common Issues

| Situation | How to handle within this lesson's scope |
| --- | --- |
| Card verification does not complete | Verify entered details and supported card types; contact your bank about verification status if needed |
| Authorization hold appears but cannot access Console | Distinguish payment verification from tenancy provisioning; record the timestamp and error message with sensitive info removed |
| Cannot create the desired VM | Classify whether the error is IAM, service limit, quota, or capacity before changing configuration |
| Trial expired and paid resources are gone | Cross-check resource types against post-trial policies; use saved exports or configurations to continue your study plan |
| Unexpected costs appear | Stop creating new resources, identify the relevant service and region, and inventory dependent components |
| Lost MFA access | Use your prepared recovery method or official support channel |

For sign-up, login, or MFA issues, the FAQ directs users to Oracle Cloud Support Chat. Free Tier does not include an SLA; support for Always Free-only accounts is limited. See [Oracle Cloud Free Tier FAQ](https://www.oracle.com/cloud/free/faq/). Treat free labs as environments that may need to be rebuilt and prepare your data accordingly.

## 11. Practice: Creating Your Account Profile and First Lab Plan

This exercise does not yet require creating paid services or upgrading to PAYG. The expected output is an environment profile and a well-grounded deployment decision.

### Step 1 — Record the Environment

Fill in the actual values from the Console in your personal notes:

```text
Tenancy name:
Home region:
Selected region:
Login identity domain:
Subscription type:
Remaining credits, if any:
Trial end date and time, if any:
MFA enrolled and re-login tested:
Payment method owner:
```

Do not put passwords, card numbers, OTPs, recovery codes, or private keys into this form.

### Step 2 — List Planned Resources

The example below is a planning framework for a small Java application and does not assert that these selections will be free:

| Component | What to verify before creating | End-of-lab plan |
| --- | --- | --- |
| Application VM | Shape, CPU architecture, total cores/RAM, home region | Keep deployment config; delete when testing ends |
| Boot volume | Size, performance config, total existing volumes | Decide explicitly whether to keep after deleting VM |
| Object Storage if needed | Capacity, operations, and data transfer for the lab | Delete test data as scheduled |
| Database if needed | Always Free option or credit/PAYG-billed portion | Export data and verify the export |

If you have not yet verified the free eligibility or pricing of a component, mark it **do not deploy yet**. Finish reading its configuration and billing units before adding it to the plan.

### Step 3 — Set Limits and a Check Schedule

Record an acceptable personal budget, compartment scope, allowed services, and lab cleanup time. If on a trial, add a review milestone before the expiration date. For future paid labs, add appropriate budgets and quotas and verify who has permission to manage those settings.

### Completion Criteria

- Successfully signed back in and identified the correct tenancy and home region.
- Explicitly stated whether the account is in trial, post-trial, or PAYG status.
- Classified each lab component as Always Free, trial credit, or planned paid usage.
- Know where to view limits, quotas, and cost data.
- Have a resource cleanup schedule, a place to store necessary data, and a way to rebuild the environment.

Once you have all of this information, you are ready to begin OCI infrastructure labs with clear resource boundaries and cost accountability.
