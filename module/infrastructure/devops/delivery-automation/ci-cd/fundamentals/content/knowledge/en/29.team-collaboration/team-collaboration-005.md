# Managing Approval Permissions and Emergency Procedures

CI/CD pipelines can modify source code, publish artifacts, update infrastructure, run database migrations, and deploy to production. Consequently, permissions to run a workflow, approve a release, and execute high-impact operations must be designed clearly. If every developer can self-approve and deploy to production, quality gates become mere formalities. If every change has to wait on a tiny group of approvers, the process turns into a bottleneck and pushes teams toward workarounds.

Managing approval permissions requires balancing delivery speed, accountability, and risk level. Normal workflows must define who can request, who can review, who can approve, and which identity actually executes the deployment. When an urgent incident demands immediate action, emergency procedures must enable controlled intervention, bound permissions in time and scope, capture full evidence, and require post-incident review.

## 1. Separating Request, Review, Approval, and Execution Permissions

A release involves distinct actions. Never lump all of them into a single "release" permission.

| Permission | Responsibility | Example |
|---|---|---|
| Request | Propose a release or environment change | Developer creates a release request |
| Review | Evaluate code, tests, security, and impact | Code owner reviews pull request |
| Approve | Authorize progression past a specific gate | Release manager approves production |
| Execute | Perform deployment or migration | CI deployment identity |
| Operate | Monitor and mitigate after deployment | On-call engineer |
| Administer | Manage policies, runners, secrets, and permissions | Platform/security administrator |

One person may hold multiple roles in a small organization, but policy must explicitly state when requester and approver must be separated. For example, the person creating a production deployment should not self-approve that exact deployment if policy requires independent approval.

Approval also does not necessarily mean execution permission. The approver authorizes a specific deployment descriptor to be rolled out; the CI identity is the identity authorized to invoke cloud APIs or update clusters. This separation avoids handing out direct production credentials to individuals.

## 2. Building RBAC by Role and Resource Scope

Role-Based Access Control (RBAC) assigns permissions by role rather than granting ad-hoc permissions to individuals. In CI/CD, roles must be scoped specifically to a repository, project, environment, service, or action type.

For example:

| Role | Typical Permissions | Restrictions |
|---|---|---|
| Developer | Create branches, pull requests, run CI | No production deploy permission |
| Code owner | Review changes within owned scope | Does not automatically grant secret access |
| Release operator | Trigger eligible releases | Cannot modify approval policy |
| Production approver | Approve production deployments | Does not implicitly allow altering artifacts |
| Incident commander | Coordinate incident response | Time-bound break-glass permissions |
| Platform admin | Administer runners, environments, and policies | Privileged actions must be audited |
| Deployment identity | Deploy to assigned targets | No interactive user login or org-wide admin rights |

Never grant broader roles than needed. An approver for service A should not automatically be allowed to approve releases for service B. A staging deployment identity should not reach production just because both use the same pipeline.

Use centrally managed groups synchronized with HR onboarding/offboarding and reviewed periodically. Avoid granting long-lived permissions directly to personal accounts when the platform supports auditable groups or role bindings.

## 3. Applying Least Privilege and Separation of Duties

**Least privilege** requires each person and each job to hold only the minimum permissions needed to complete its task. **Separation of duties (SoD)** splits sensitive steps across distinct roles to reduce the risk of human error or abuse.

Commonly applied rules:

- Developers can open pull requests but require approval from another reviewer.
- A release requester cannot self-approve production if policy forbids self-approval.
- Approvers cannot modify the artifact digest after approval.
- Build jobs only have read access to source and write access to authorized registries.
- Deploy jobs only have permission to update the designated service/environment.
- Authority to administer approval policies is separated from authority to trigger releases.
- Production secrets are injected into jobs only after requisite gates pass.

SoD does not always demand two people for every operation. A low-risk change in development may require only automated checks. Production releases, breaking database migrations, or security policy edits may require independent approval or multiple approvers.

Policies must be grounded in impact, reversibility, and blast radius. Never turn approval into a rubber-stamp button click lacking information to evaluate.

## 4. Building an Approval Matrix by Environment and Risk Level

Environments carry different levels of risk. Define an approval matrix as the baseline standard for pipelines.

| Environment/Change | Automated Conditions | Recommended Approval |
|---|---|---|
| Local/dev | Basic build and tests | No manual approval required |
| Shared test | CI, integration tests, and scans pass | Team owner when changes impact shared environment |
| Staging | Verified artifact, smoke tests pass | Release owner or service owner per policy |
| Standard production | Required checks, provenance, validation, and release record complete | Independent approver or authorized group |
| High-risk production | Migration, security, rollback, and business-impact review | Two-person rule or quorum approval |
| Emergency change | Confirmed incident, minimal scope, appropriate runbook | Break-glass per policy; mandatory post-review if waiting is impossible |

This is a reference model. Organizations must define specific risk thresholds and authorized approvers. A small hotfix may require fewer steps than an IAM change, major data migration, or payment flow update.

The approval matrix must be encoded in policy and environment protection rules. If it exists only in documentation without pipeline enforcement, workflow runners can bypass it.

## 5. Binding Approvals to a Specific Deployment Request

Approvers must know exactly what will be deployed. A generic approval like "approve release 2.8.1" is insufficient if tags or configurations can still mutate.

A deployment request should identify:

- Release ID and service.
- Artifact repository, version, and digest.
- Source commit and build run.
- Provenance, signature, and security scan results.
- Configuration version and checksum.
- Target environment, account, region, cluster, and namespace.
- Associated database migrations or infrastructure changes.
- Deployment strategy, rollout batch size, and timeout.
- Post-deployment guardrails and rollback/roll-forward plan.
- Requester and timestamp.

After approval, the pipeline must consume the exact approved inputs. If the digest, config version, or target changes, the prior approval no longer represents the new request; re-verification and fresh approval are required per policy.

You can generate a fingerprint from a normalized deployment descriptor. The pipeline records the fingerprint in the approval record and compares it right before execution. This catches silent input tampering after approval.

## 6. Providing Enough Context for Approvers to Decide

Approval is meaningful only when reviewers understand the impact and evidence. Approval screens should display or link to:

- Change summary and related pull requests.
- Artifact digest and build provenance.
- Tests, quality gates, and security scans.
- Database migrations and compatibility assessments.
- Target environment and affected resource scope.
- Staging results and post-deploy validation.
- Rollout plan, guardrails, and rollback plan.
- Known risks, dependencies, and limitations.

Do not force approvers to open half a dozen systems and correlate events by timestamp manually. The release record should aggregate essential evidence and link back to source reports.

Approvers must have options to approve, reject, or request changes with a reason. Rejection reasons should be recorded so the team fixes the exact issue rather than staring at a bare "rejected" status.

## 7. Protecting Environments in GitHub Actions

GitHub Actions supports environment protection rules. You can configure required reviewers, wait timers, and deployment branch/tag restrictions in repository or organization environment settings, depending on your plan and platform policies.

A workflow can declare the environment on its deploy job:

~~~yaml
name: Deploy production

on:
  workflow_dispatch:
    inputs:
      release_id:
        description: Approved release identifier
        required: true
        type: string

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Verify approved release descriptor
        env:
          RELEASE_ID: ${{ inputs.release_id }}
        run: ./scripts/verify-approved-release.sh "$RELEASE_ID"

      - name: Deploy
        env:
          RELEASE_ID: ${{ inputs.release_id }}
        run: ./scripts/deploy-release.sh "$RELEASE_ID"
~~~

A job referencing the `production` environment is subject to the protection rules configured for that environment. This YAML example does not create required reviewers by itself; environment protections must be configured in the platform, and permissions to edit those protections must be restricted.

If policy requires an independent approver, enable the option preventing the workflow initiator from self-reviewing when the platform supports it. Also audit the reviewer list, bypass permissions, and who can modify environment protection rules. Declaring `environment: production` without appropriate protection rules does not create an approval gate.

Verification scripts must look up an immutable release descriptor, verify that approval matches the exact fingerprint, and re-verify artifact/config/target before deploying. Never trust a user-supplied release ID without verifying its origin and state.

The `id-token: write` permission is only needed when the job uses OIDC to obtain short-lived cloud credentials. If OIDC is not used, omit this permission and use an appropriate least-privilege identity mechanism.

## 8. Branch Protection and Required Checks

Production approval does not replace source code review. Branch protection or rulesets ensure changes pass through pull requests, required status checks, and code owner reviews before merging.

Controls may include:

- Requiring pull requests instead of direct pushes to protected branches.
- Requiring an appropriate number of approvals.
- Requiring code owner review for sensitive paths like workflows, IaC, and policies.
- Dismissing stale approvals when new commits arrive per policy.
- Requiring status checks from trusted workflows.
- Restricting who holds bypass authority.
- Auditing all ruleset and branch protection changes.

Never mark a skippable job as a required check. Ensure check names are stable and results bind to the exact commit being merged. When workflows run on untrusted code from forks, never expose production secrets or registry write permissions.

## 9. Multi-Tier Approvals and Quorum

Some changes demand multiple perspectives: the service owner understands business logic, the security reviewer understands permissions and data, the database owner understands migrations, and operations understands runnability.

Approvals can be structured by change type:

| Change | Required Approvers |
|---|---|
| Service logic bug fix | Service owner/reviewer |
| API contract change | Service owner and consumer owner when needed |
| Major database migration | Database owner and release owner |
| IAM/secret policy | Security or platform owner |
| Production infrastructure | Platform/operations owner |
| Emergency change | Incident commander and break-glass policy approver |

Quorum is the count or combination of roles needed for an approval to take effect. For example, a release may require one service owner and one production approver; an IAM change may require a mandatory security approver.

Avoid ambiguous rules such as "any two people." If two approvers are required, specify whether they must belong to distinct teams, whether the requester counts, and whether approvals invalidate if inputs change.

## 10. Standard Approval Workflow

A typical production release flow can run as follows:

~~~mermaid
flowchart TD
    A[Release request] --> B[Validate descriptor]
    B --> C[Required CI and security gates]
    C --> D[Staging deployment]
    D --> E[Post-deploy validation]
    E --> F[Prepare approval evidence]
    F --> G{Authorized approver}
    G -- Reject --> H[Return for changes]
    G -- Approve --> I[Revalidate approved fingerprint]
    I --> J[Production deployment]
    J --> K[Post-deploy guardrails]
    K --> L[Close release record]
~~~

Every step needs an explicit status: requested, validating, awaiting approval, approved, rejected, deploying, verified, or failed. Timeouts or missing evidence must never automatically transition to approved.

Approvals can expire if a request is not deployed within a defined window—especially if dependencies, policies, or environment state have shifted. Before deploying, the pipeline should verify that approval is still valid.

## 11. What Are Elevated Privileges and Break-Glass?

Break-glass is an emergency access procedure for resolving incidents when normal approval paths cannot meet required response times. For example:

- Production is down and requires an immediate rollback.
- An expiring secret or certificate is disrupting service.
- A security flaw requires disabling an endpoint or revoking credentials immediately.
- A migration or configuration loss of recoverability requires urgent intervention.
- The pipeline approval service is down during a confirmed incident.

Break-glass is not a shared account with a password stored on a wiki. It is a privileged access mechanism with identity, scope, duration, rationale, and auditability. Emergency privileges must be granted under least privilege and revoked once the task finishes.

If your platform supports temporary roles via an identity provider, prefer Just-in-Time (JIT) access and short-lived credentials. Avoid keeping long-lived production access keys on runners or personal laptops.

## 12. Designing a Controlled Break-Glass Workflow

A reference workflow:

1. **Declare the incident:** create an incident ID, severity level, and designate an incident commander.
2. **State the required action:** service, environment, resource, and emergency rationale.
3. **Verify the requester:** enforce MFA or strong authentication per policy.
4. **Grant JIT access:** minimal role, specific resource scope, and short TTL.
5. **Emergency approval:** an independent approver when possible; otherwise log why waiting is impossible.
6. **Execute the action:** follow a prepared runbook and record commands/actions and outcomes.
7. **Monitor:** verify service health, metrics, audit logs, and side effects.
8. **Revoke access:** let TTL expire or explicitly revoke immediately upon completion.
9. **Post-incident review:** an independent reviewer audits actions, data impact, and evidence.
10. **Update runbooks:** document root cause and preventive measures.

Break-glass access should enforce limits on duration and usage frequency. Granting emergency access must never automatically escalate into org-wide or cloud-wide administrator privileges.

## 13. When Pre-Approval Can Be Bypassed with Mandatory Post-Review

Some situations require acting faster than waiting for an approver. Policy may permit an on-call group to execute predefined actions immediately, followed by mandatory independent post-review.

Apply this strictly within explicitly defined boundaries:

- Eligible incident types.
- Authorized individuals or roles.
- Pre-approved set of actions, such as rolling back to a verified artifact or toggling off a feature flag.
- Permitted environments and services.
- Limits on duration, invocation count, and impact scope.
- Requirements to notify stakeholders and open an incident.
- Deadline and accountable owner for post-review.

Never allow "bypass all approvals during an incident." A self-typed incident label from the workflow runner does not prove authorization to skip gates. Require a verified incident record or policy invoked by an incident commander.

Irreversible actions—such as deleting data, broad IAM changes, or database restores—require separate controls. Whenever possible, prepare safe pre-approved mechanisms ahead of incidents to reduce the need for emergency overrides.

## 14. Technical Enforcement of Break-Glass Boundaries

Policies only work when systems enforce the limits technically.

Controls include:

- JIT roles with short TTLs scoped by account/project/resource.
- MFA or strong authentication at elevation time.
- Ephemeral credentials rather than shared static secrets.
- Session recording or command auditing for sensitive actions where supported.
- Controlled network boundaries and runners.
- Preventing emergency permissions from outliving the incident.
- Real-time alerts whenever break-glass is activated.
- Automatic revocation on expiration.
- Mandatory post-review and confirmation of revocation.

When using cloud IAM, create dedicated emergency roles with narrow policies. These roles must never carry permission to alter IAM policies themselves or delete audit logs. Identity administrators require a separate oversight process.

Never store emergency credentials in pipeline files, repositories, or shared environment variables. If a platform maintains an emergency access account, enforce vaulting, rotation, periodic checks, and auditing of every login.

## 15. Example Emergency Rollback Workflow in CI/CD

You can create a dedicated workflow for emergency rollbacks that only accepts a release ID already recorded in the release registry. The workflow should never accept an arbitrary image tag and deploy it blindly.

Example GitHub Actions skeleton:

~~~yaml
name: Emergency rollback

on:
  workflow_dispatch:
    inputs:
      incident_id:
        description: Approved incident identifier
        required: true
        type: string
      release_id:
        description: Previously verified stable release
        required: true
        type: string

permissions:
  contents: read

jobs:
  emergency-rollback:
    runs-on: ubuntu-latest
    environment: production-emergency
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Verify incident and rollback target
        env:
          INCIDENT_ID: ${{ inputs.incident_id }}
          RELEASE_ID: ${{ inputs.release_id }}
        run: |
          ./scripts/verify-emergency-authorization.sh \
            "$INCIDENT_ID" "$RELEASE_ID"

      - name: Execute rollback
        env:
          INCIDENT_ID: ${{ inputs.incident_id }}
          RELEASE_ID: ${{ inputs.release_id }}
        run: |
          ./scripts/rollback-release.sh \
            --incident "$INCIDENT_ID" \
            --release "$RELEASE_ID"

      - name: Verify service recovery
        run: ./scripts/verify-production-health.sh
~~~

The `production-emergency` environment needs its own policy governing who may invoke it and how access is granted. If environment configuration requires pre-approval, clearly define the on-call/incident commander group and escalation steps when an approver is unavailable. This workflow is a skeleton only; scripts must verify the incident, authorization, release digest, config compatibility, and database state.

Never treat an input incident ID as proof of authorization. Scripts must verify the incident actually exists and the actor is authorized for that action class. After rollback, the workflow must log the outcome and trigger post-review per policy.

## 16. Distinguishing Emergency Rollback from Hotfix

A rollback returns the system to a previously verified release. A hotfix introduces a new change to fix the root cause while preserving needed parts of the current version.

| Criterion | Emergency Rollback | Emergency Hotfix |
|---|---|---|
| Goal | Restore previous stable version | Fix defect with a new artifact |
| Speed | Can be fast if target is already ready | Requires minimal build and testing |
| Risk | Schema/config incompatibility or losing recent changes | New code is not fully tested |
| Evidence | Prior release, digest, and compatibility | Commit, build provenance, tests, and scans |
| Follow-up recovery | Investigate faulty release and plan re-release | Track hotfix and merge back into main development branch |

Rollback is not always safe. If the database already ran a breaking migration or new data was written under the new schema, reverting to an older image may crash the app. In that case, you may need a roll-forward or compatible hotfix.

Hotfixes must never skip testing entirely. At minimum, run compile/build, targeted tests, required scans, and artifact verification. Once the incident is contained, merge or cherry-pick the fix back to the main branch so it isn't lost in the next release.

## 17. Post-Review After Using Emergency Access

Every break-glass invocation requires an independent review once the system stabilizes. Post-review is not for blaming the on-call responder, but for confirming privileges were used properly and reducing recurrence risk.

Post-review contents:

- Incident ID, severity, timestamps, and incident commander.
- Identities of requester, approver, and deployment identity.
- Permissions granted, scope, TTL, and revocation timestamp.
- Artifact/config/target before and after the intervention.
- Commands or actions executed and their outcomes.
- Health check, SLI, and business validation evidence.
- Impact on data, migrations, and dependencies.
- Approvals or gates bypassed, rationale, and authorizing policy.
- Time to detect, respond, and recover.
- Corrective action items with owners and due dates.

If permissions have not yet been revoked, revoke them immediately before closing the incident. If audit logs are missing or out-of-scope actions occurred, treat it as a security event requiring investigation.

## 18. Audit Trails and Approval Integrity

Approvals and break-glass actions must leave auditable evidence. Audit records should capture:

- Actor and role at the time of action.
- Action requested, approved, or executed.
- Release/incident ID.
- Deployment descriptor fingerprint.
- Artifact digest and target.
- Timestamp, outcome, and rationale.
- Approver identity and approval decision.
- Permissions/roles granted and validity window.
- Break-glass activation, renewal, and revocation.
- Links to logs, test reports, and post-deployment evidence.

Audit logs must be protected against tampering or deletion by the same identity that performs deployments. Forward audit events to a centralized store with separate write permissions and a retention policy.

Do not record secrets or unnecessary personal data in audit records. Correlation IDs, release IDs, and resource identities are usually sufficient to stitch events together.

## 19. Periodic Access Reviews and Personnel Changes

Approval permissions quickly go stale when staff change roles, teams transfer ownership, or projects retire.

Establish processes to:

- Review approver group memberships on a regular schedule.
- Revoke permissions when personnel leave the team or change roles.
- Remove temporary privileges after a release or incident.
- Audit unused service accounts and tokens.
- Review who holds bypass rights on branch or environment protections.
- Audit who can edit workflows and approval policies.
- Evaluate permissions of external contributors and bots.
- Periodically test emergency accounts and recovery mechanisms.

Every role needs an owner accountable for certifying its membership list. Never let a production approver group exist with nobody accountable for maintaining it.

## 20. Testing Approval and Break-Glass Procedures

Permission workflows must be tested before you depend on them during a real outage.

Scenarios to verify:

| Scenario | Expected Outcome |
|---|---|
| Unauthorized user attempts to approve | Cannot pass the gate |
| Deployment author attempts self-approval | Blocked when policy forbids self-approval |
| Artifact digest changes after approval | Prior approval is invalidated |
| Target environment changes after approval | Requires re-verification/fresh approval |
| Required check fails | Cannot deploy to production |
| Approver does not respond | Request expires or escalates per policy |
| Break-glass role TTL expires | Subsequent actions are blocked |
| User leaves the team | Permissions are revoked |
| Emergency rollback targets unverified release | Blocked |
| Post-review incomplete | Incident/recovery record cannot be closed per policy |

Run game-day drills: simulate a failed production deployment, unavailable approver, JIT elevation, rollback, and post-review. The goal is verifying both response speed and audit traceability.

Never test break-glass using live production credentials in an uncontrolled environment. Use staging or a sandbox with equivalent policies.

## 21. Checklist for Approval Management and Emergency Procedures

Before putting a release workflow into operation, check:

- [ ] Request, review, approve, execute, and operate permissions are separated.
- [ ] RBAC is scoped by repository, service, and environment.
- [ ] Least privilege and separation of duties are enforced according to risk.
- [ ] Approval matrix clearly defines approvers for each change class.
- [ ] Approvals bind to a specific release descriptor, artifact digest, config, and target.
- [ ] Input changes after approval force re-verification or re-approval.
- [ ] Approvers receive complete test, scan, migration, and rollback evidence.
- [ ] Branch protection and required checks are enforced.
- [ ] Self-approval and bypasses are controlled.
- [ ] Environment protections have appropriate reviewers, wait timers, and branch restrictions.
- [ ] Break-glass requires explicit incident ID, rationale, scope, TTL, and identity.
- [ ] Emergency privileges use JIT/short-lived credentials and MFA per policy.
- [ ] Emergency actions are audited and monitored.
- [ ] Privileges are revoked immediately upon completion or TTL expiry.
- [ ] Independent post-review and completion deadlines are enforced.
- [ ] Rollback targets are verified and schema/config-compatible.
- [ ] Approval and break-glass procedures are tested and rehearsed.
- [ ] Approver groups and bypass rights are reviewed periodically.

Effective approval management ensures release decisions have clear accountability and supporting evidence. Well-designed break-glass procedures let operations respond rapidly during incidents while preserving permission boundaries, audit trails, and post-incident review. When approvals bind to exact verified inputs and emergency privileges exist only within the required window, CI/CD can ship software quickly while maintaining strong production control.
