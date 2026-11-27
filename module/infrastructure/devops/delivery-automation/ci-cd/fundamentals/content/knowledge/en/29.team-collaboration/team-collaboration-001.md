# Aligning Responsibilities Across Development, QA, Security, and Operations

## Learning Objectives

After completing this lesson, you will be able to:

- Explain why quality and release readiness are shared responsibilities across multiple roles.
- Identify the responsibilities of development, QA, security, and operations in each CI/CD stage.
- Distinguish between those who execute the work, the person ultimately accountable, those consulted, and those who need to be informed.
- Design a RACI matrix and decision authority for changes, quality gates, releases, and incidents.
- Shift testing, security, and operational requirements left into the development process.
- Design quality gates with clear owners, criteria, evidence, and exception-handling workflows.
- Organize release readiness, information handoff, and post-deployment verification.
- Coordinate incident response, rollbacks, and post-incident improvements without creating responsibility silos.

## 1. Why Aligning Responsibilities Matters

A software change moves through multiple teams: developers write code, QA runs tests, security evaluates risks, and operations deploys and maintains the service. If each team only finishes its own piece and throws responsibility over the wall to the next team, gaps easily appear.

For example:

- Developers assume QA will catch every bug before release.
- QA only tests against assigned test cases and lacks authority to require fixes for architectural risks.
- Security is only invited to review right before production, discovering issues too late.
- Operations receives an artifact without configuration instructions, dashboards, or rollback guidance.
- When a release causes an incident, teams argue over who has to handle it instead of restoring the service together.

CI/CD shortens the time from change to release, but speed only matters when roles coordinate at the right time. An automated pipeline does not automatically define who is responsible for test criteria, who approves risks, who manages production, and who decides to halt a rollout.

The goal is to build **a continuous chain of accountability from the moment a change is conceived until the service is operating stably**. Every activity needs an owner, completion criteria, evidence, and an escalation path when standards are not met.

Shared responsibility does not mean everyone is vaguely accountable together. Every critical decision still requires one clearly accountable person or role, along with the appropriate executing and consulted roles.

## 2. The Four Core Role Groups

Team names and organizational structures may differ across companies. One person may wear multiple hats in a small team; what matters is that capabilities and decision-making authority are clearly defined.

### 2.1. Development

Development is responsible for designing and building software changes that are testable, deployable, and maintainable.

Typical responsibilities include:

- Clarifying technical requirements and expected behavior.
- Designing code, APIs, schemas, and dependency interactions.
- Writing unit tests, component tests, and appropriate code-level checks.
- Reviewing code and resolving findings from tests, scans, or reviews.
- Declaring dependencies, configurations, and migrations.
- Producing reproducible artifacts traceable to a source revision.
- Providing information on changes, limitations, feature flags, and known risks.
- Assisting in investigating and fixing defects when a release causes impact.

Developers are not only responsible for making code compile. They must understand how their changes affect data, security, performance, and operability.

### 2.2. Testing and Quality Assurance (QA)

QA helps determine whether the product meets requirements and whether risks are under control. QA is not the sole team responsible for quality.

Typical responsibilities include:

- Building a risk-based testing strategy.
- Defining test scope, test data, and test environments.
- Designing test cases, exploratory tests, and automated tests.
- Verifying business flows, integrations, regressions, and compatibility.
- Evaluating test suite reliability and flaky tests.
- Analyzing failures and distinguishing product bugs from environment issues.
- Providing test reports and release readiness recommendations.
- Participating in post-deploy verification and investigating real-world defects.

QA must be involved from requirements clarification and design rather than merely receiving a build close to the release date. QA also needs the authority to raise risks and request evidence, while final acceptance criteria must be defined together with the product owner and relevant stakeholders.

### 2.3. Security

Security helps identify and reduce security risks across source code, dependencies, infrastructure, build processes, and runtime environments.

Typical responsibilities include:

- Advising on threat modeling and security requirements.
- Defining baselines for SAST, SCA, secret scanning, IaC, and image scanning.
- Defining severity levels, remediation SLAs, and exception policies.
- Reviewing high-risk changes such as authentication, authorization, cryptography, or sensitive data handling.
- Guiding secret management, identity, and least-privilege permissions.
- Verifying provenance, artifact integrity, and the software supply chain.
- Supporting incidents related to vulnerabilities or compromise.
- Tracking outstanding risks and remediation deadlines.

Security cannot inspect every line of code on behalf of developers. Developers are responsible for fixing defects in what they build; security defines standards, advises, and verifies risks that require specialized expertise or independent oversight.

### 2.4. Operations and Platform (Operations/Platform)

Operations and platform teams ensure software can be deployed, observed, scaled, and recovered in real-world environments.

Typical responsibilities include:

- Managing environments, networking, compute, storage, and the deployment platform.
- Providing pipeline runners, identities, and secure secret mechanisms.
- Defining deployment strategies, approvals, and change control.
- Building monitoring, logging, tracing, alerting, and dashboards.
- Defining SLIs/SLOs, capacity, and resource limits.
- Managing backups, restores, rollbacks, and disaster recovery.
- Verifying readiness, health, and post-deploy state.
- Coordinating incidents and ensuring runbooks are usable.
- Providing operability feedback starting at the design phase.

Operations should not have to guess how to run an application after receiving an artifact. Developers must supply runtime requirements and change details; platform/operations provides the foundation and operational constraints.

## 3. Shared Responsibility and Distinct Decision Authority

Some activities require multiple teams to participate, yet decision authority must remain explicit.

For example:

- Developers implement code fixes.
- QA determines whether test evidence is sufficient according to the test strategy.
- Security determines whether a finding violates policy or requires an exception.
- Operations confirms that the environment, capacity, and recovery capabilities meet deployment conditions.
- The release owner or authorized release approver decides whether to proceed based on evidence and risk acceptance.

Any team can recommend halting a release, but policy must specify who has the authority to block by policy and who has the authority to grant an exception. An individual should never bypass mandatory controls simply because of a deadline.

Authority can be categorized as follows:

| Authority Type | Examples | How It Is Governed |
|---|---|---|
| Execute | Fix code, run tests, deploy | Granted by job, environment, and scope |
| Review | Review code, test results, security findings | Assign reviewers with domain expertise |
| Approve | Approve a release or exception | Tied to policy and audit |
| Block | Block a gate when mandatory conditions fail | Clearly define triggers and resolution steps |
| Coordinate | Coordinate a release or incident | Designate release owner/incident commander |
| Risk Accept | Accept an outstanding finding | Requires owner, rationale, scope, and expiry |

Separation of duties helps prevent conflicts of interest. For example, the person authoring a production change should not be the sole approver of that change if policy requires independent review.

## 4. Using RACI to Clarify Responsibilities

RACI is a way to describe each role's participation in an activity:

- **R — Responsible:** the person or role who directly executes the work.
- **A — Accountable:** the person or role ultimately accountable for ensuring the activity is completed.
- **C — Consulted:** those who must be consulted before a decision or execution.
- **I — Informed:** those who need to be notified of the outcome.

Each activity should have one clear A role. There can be multiple R and C roles, but if no one is A, work easily falls through the cracks; if too many people are A, decision-making becomes ambiguous.

Example reference matrix:

| Activity | Development | QA | Security | Operations | Release owner |
|---|---|---|---|---|---|
| Clarify requirements and acceptance criteria | R | C | C | C | A |
| Technical design and APIs | A/R | C | C | C | I |
| Unit/component tests | A/R | C | C | I | I |
| Test strategy and regression | R | A | C | C | I |
| Threat model for high-risk changes | R | C | A | C | I |
| Fix security findings in code | A/R | I | C | I | I |
| Security policy and exception review | C | I | A/R | C | I |
| Build and artifact creation | A/R | C | C | C | I |
| Manage runners and deployment platform | C | I | C | A/R | I |
| Confirm release readiness | R | R | C | R | A |
| Production approval per policy | C | C | C | C | A/R |
| Post-deploy monitoring | R | C | C | A/R | I |
| Incident coordination | R | C | C | R | A |
| Post-incident review | R | R | R | R | A |

This matrix is only a starting point. Organizations must adapt it to their actual structure, system classification, and internal policies. For activities with high security or data risk, an independent approval outside the roles in this table may be required.

RACI does not replace a decision-making process. It must be paired with documentation specifying completion criteria, blocking authority, backup delegates during absences, and how disagreements are resolved.

## 5. Collaborating from Requirements and Design

Effective collaboration starts before a pull request exists.

When a change is proposed, teams should jointly clarify:

- What behavior will change?
- Which users or systems are affected?
- Are there changes to APIs, events, schemas, or data?
- Is sensitive data or new permissions involved?
- At which layers is testing required?
- Are there latency, throughput, availability, or capacity requirements?
- Can it be rolled out gradually or behind a feature flag?
- If it fails, can it be rolled back or does it require a forward fix?
- Are new dashboards, alerts, or runbooks needed?

Developers are responsible for proposing the technical design. QA contributes testability and acceptance criteria. Security identifies threats and required controls. Operations evaluates runtime behavior, capacity, and recovery.

You do not need to hold a large meeting for every change. You can use ticket checklists, pull request templates, or asynchronous reviews. Only high-risk changes require a cross-functional design review.

## 6. Shift-Left: Bringing Testing and Security in Early

Shift-left means detecting issues early when the cost to fix is usually lower and the blast radius is smaller.

For example:

- QA participates in writing acceptance criteria before code is finished.
- Developers write unit tests alongside their changes.
- Security reviews threat models when designing authentication or data flows.
- IaC scans run when a pull request modifies infrastructure.
- Secret scans run before code is merged.
- Dependency policies are checked before an artifact is published.
- Operations reviews logging, metrics, and rollback requirements before production.

Shift-left does not mean shifting all QA or security responsibilities onto developers. It brings domain specialists in at the right moment and embeds their criteria into the workflow.

Several controls should be automated in CI:

- Linting and static analysis.
- Unit and component tests.
- Dependency and secret scanning.
- IaC validation.
- License policy checks.
- Container image scanning.
- Contract tests.
- Build reproducibility or provenance checks.

Evaluations requiring expert judgment—such as threat modeling, usability, risk acceptance, or resilience architecture—still require human involvement.

## 7. Setting Quality Gates with Clear Owners and Evidence

A quality gate is a condition that must be met before a pipeline advances to the next step. A gate is only valuable when you know:

- What are the criteria?
- Who owns the criteria?
- What evidence proves the criteria are met?
- When is the gate evaluated?
- If it fails, who handles it?
- Are exceptions allowed, and who approves them?

For example:

| Gate | Primary Owner | Evidence |
|---|---|---|
| Code review | Development | Approval and review status |
| Unit tests | Development | Test report and commit SHA |
| Regression/integration tests | QA | Test report, scope, and environment |
| Security baseline | Security | Scanner report, policy revision |
| Artifact integrity | Platform/Security | Digest, provenance, and signature |
| Capacity/readiness | Operations | Capacity check, health, and rollout plan |
| Release readiness | Release owner | Gate summary and risk record |
| Post-deploy verification | Operations with Development/QA | Runtime metrics, smoke tests, and deployment record |

Gates must distinguish between a failure and missing evidence. If a scanner did not run, you cannot conclude there are no findings. If a test report belongs to an older commit, it cannot be used for the current commit.

Policy versions, report IDs, and gate decisions should be stored for future traceability.

## 8. Handling Exceptions and Risk Acceptance

Not every finding can be fixed immediately. Some cases require a controlled exception, but exceptions must not become a routine way to bypass gates.

An exception request should state:

- The failing finding or condition.
- Affected systems and versions.
- Why it cannot be remediated yet.
- Risk severity and impact.
- Temporary compensating controls.
- Person responsible for remediation.
- Expiration date.
- Person authorized to accept the risk.
- Evidence and approval decision.

Security findings must be accepted by a role authorized under policy, not solely by the developer who authored the change. Availability or capacity risks must involve the operations owner. Exceptions must have an expiry and be re-evaluated if the scope changes.

A single blanket approval should not be used to bypass multiple unrelated gates. Each exception must have a clearly defined scope.

## 9. Responsibilities in Pull Requests and Code Review

A pull request is a key coordination point across developers, QA, security, and sometimes operations.

A good pull request should describe:

- The problem and expected behavior.
- Scope of the change.
- API/schema/event changes.
- Tests executed and results.
- Migrations or data impact.
- Security considerations.
- New configurations and secrets, if any.
- Monitoring/alerts that need updating.
- Deployment and rollback approach.
- Feature flag or rollout strategy.

Reviewers should focus on their domain responsibilities:

- Developers review logic, maintainability, and compatibility.
- QA reviews test coverage, edge cases, and acceptance behavior.
- Security reviews relevant threats and controls.
- Operations/platform reviews runtime or infrastructure impact when needed.

Not every pull request needs approvals from all four groups. Select appropriate reviewers based on risk classification. However, mandatory policies such as code owners, protected branches, or security approvals must be enforced automatically rather than relying on the PR author's memory.

## 10. Responsibilities When Building and Operating Pipelines

The pipeline itself is part of the production system. Workflow changes can open up permissions, bypass gates, or corrupt artifacts.

Development and platform teams must coordinate to define:

- Which workflows are owned by the project and which are owned by the platform?
- Who is allowed to modify reusable workflows?
- Which jobs are granted permission to read source, write to registries, or deploy?
- Which runners are used for untrusted code?
- At which step are secrets provided?
- Where are artifacts and reports stored?
- How are versions of shared actions/workflows pinned?
- Who responds when a runner or registry experiences an outage?

Security must review changes affecting trust boundaries, token permissions, secret handling, and provenance. Operations/platform is responsible for runner capacity, networking, quotas, and platform availability. Development is responsible for project configuration and fixing repository-specific pipelines within permitted boundaries.

Production permissions should not be granted to all jobs just because the final job needs to deploy. Separate validation, build, publish, and deploy into jobs or workflows with least privilege.

## 11. Preparing for Release Readiness

Release readiness is a comprehensive assessment before releasing. It is not simply seeing all jobs turn green.

A release readiness review should check:

- Source commits and pull requests have been reviewed.
- Mandatory tests ran against the exact source revision.
- Security scans cover sufficient scope and the correct policy revision.
- Artifact digest and provenance are valid.
- Migrations are compatible with the currently running version.
- Environment configuration has been validated.
- Deployment strategy matches platform capabilities.
- Capacity and change window have been confirmed.
- Dashboards, alerts, and runbooks are ready.
- Rollback or recovery plan is actionable.
- Owners and on-call support have been identified.
- Active exceptions are valid and have documented risk acceptance.

A release can pass all automated checks and still not be ready if no one is on call, capacity is insufficient, or a database change lacks a recovery plan.

The release owner consolidates evidence and coordinates the decision. Domain teams confirm their respective areas of responsibility, while final approval authority follows organizational policy.

## 12. Handoff from Development to Operations

A handoff should not be just sending a link to an artifact. Operations needs enough information to deploy, observe, and troubleshoot incidents.

A deployment handoff should include:

- Release ID, source commit, and artifact digest.
- Summary of changes and new dependencies.
- Config revision and required secret references.
- Migrations or data changes.
- Deployment strategy and rollout steps.
- Health endpoints and readiness criteria.
- Relevant dashboards, alerts, and SLOs.
- Runbooks and common operational procedures.
- Rollback/recovery constraints.
- Feature flags and kill switches.
- Technical owner and contact channels.
- Known issues and outstanding exceptions.

Developers must explain application behavior and known limitations. Operations/platform confirms the environment can meet the requirements. QA can provide test reports and flows requiring smoke testing. Security provides findings or conditions that still require monitoring.

A solid handoff prevents operations from having to reverse-engineer the change during the release window.

## 13. Post-Deployment Monitoring Is a Cross-Functional Responsibility

After deployment, both technical state and business behavior must be verified.

Operations typically monitors:

- Instance readiness and restarts.
- Error rates, latency, and saturation.
- Queue lag and dependency health.
- Traffic distribution and rollout status.
- Alerts and SLOs.

Development assists in analyzing logs, traces, code paths, and runtime errors. QA verifies smoke tests, critical user journeys, and potential regressions in the live environment. Security monitors anomalous signals or security issues if the release changes the attack surface.

Teams must agree on an observation window and rollout stop conditions. For example, if error rates exceed a threshold during a canary, the pipeline pauses or aborts per policy. The on-call operator coordinates the action; developers help identify root cause and deliver fixes.

A release should not be marked complete merely because the deployment command succeeded. Only mark a release complete once actual runtime health and mandatory checks have been verified.

## 14. Coordinating During Incidents and Rollbacks

When production experiences an incident, the first priority is protecting users and restoring service. Assigning individual blame must not slow down containment.

An incident model may include:

- **Incident commander:** coordinates, sets priorities, and assigns tasks.
- **Operations/on-call:** assesses scope, mitigates impact, controls traffic, and executes runbooks.
- **Development:** analyzes code and dependencies and provides fixes.
- **QA:** helps reproduce issues, verifies fixes, and checks critical flows.
- **Security:** joins if there are signs of compromise, leaked secrets, or vulnerabilities.
- **Communications/product owner:** updates stakeholders and makes user-impact decisions per process.

Reference workflow:

1. Confirm the incident and designate an incident commander.
2. Assess impact severity, affected services, and impacted users.
3. Halt the rollout or throttle traffic if needed.
4. Disable feature flags, roll back the artifact, or apply appropriate mitigation.
5. Check data and side effects; perform separate data recovery if needed.
6. Verify service health and critical journeys.
7. Update stakeholders on status.
8. Collect the timeline, decisions, and evidence.
9. Hold a post-incident review and track action items.

Rollback is not always the first choice. If the fault lies in an external dependency, configuration, or data, rolling back code may not resolve it. Decisions must be grounded in evidence and compatibility.

## 15. Post-Incident Review and System Improvement

A post-incident review should focus on how systems and processes allowed the incident to occur, be detected, and be handled.

Useful questions include:

- Which change triggered the incident?
- Which controls caught or missed the fault?
- Did the test environment represent production accurately?
- Were security or operational reviews involved at the right time?
- Did the pipeline provide sufficient evidence and traceability?
- Could blast radius have been reduced with feature flags or a canary?
- Were runbooks complete and accurate?
- Were roles and responsibilities clear during the incident?
- What slowed down recovery?
- What needs to change across code, tests, policies, pipelines, or operations?

Action items need an owner, deadline, priority, and verification method for completion. Avoid vague tasks like "improve monitoring" without specifying the exact metrics, alerts, services, and responsible owner.

A good review does not seek someone to blame. It identifies systemic conditions that must change to reduce the likelihood or impact of future incidents.

## 16. Communication and Collaboration Cadence

Teams need communication channels suited to the risk level and rate of change.

Useful mechanisms include:

- Tickets or change requests for goals, scope, and owners.
- Pull requests for code changes and reviews.
- Pipeline reports for tests, scans, and artifact evidence.
- Release records for release decisions.
- Runbooks for operational procedures.
- Incident channels or bridges for active incidents.
- Post-incident reviews for lessons learned and action items.

Information must be clear and traceable. Avoid sending a "deployed" message without a release ID, environment, artifact digest, or verification results.

Meetings should focus on decisions requiring multi-party input: design reviews, risk reviews, release readiness, or incident reviews. Information that can be documented in tickets or reports should be exchanged asynchronously to reduce wait times.

## 17. Example: A Change Moving Through the Roles

Suppose a development team adds a refund API to a payment service.

**Requirements and Design Phase**

- Development describes the API, authorization, and state transitions.
- QA defines acceptance criteria, test cases for partial refunds, and idempotency requirements.
- Security reviews access permissions, abuse prevention, and sensitive data.
- Operations evaluates rate limits, monitoring, alerts, and payment provider dependency handling.
- Product/release owner determines risk level and rollout scope.

**Pull Request Phase**

- Developers write code, unit tests, and contract tests.
- QA reviews error cases, duplicate requests, and indeterminate states.
- Security checks authorization and scanner findings.
- The pipeline produces test reports, scan reports, and artifact provenance.
- Reviewers approve according to code ownership and policy.

**Staging Phase**

- The artifact is promoted by digest.
- QA runs integration and end-to-end tests against a sandbox.
- Operations verifies dashboards, alerts, and rollback procedures.
- Security confirms remaining findings are resolved or have valid exceptions.

**Production Phase**

- The release owner confirms readiness.
- Authorized approvers sign off per policy.
- Operations deploys a canary.
- Development and QA monitor error rates, duplicate refunds, and critical journeys.
- If thresholds pass, the rollout continues; if not, the rollout halts and mitigation is executed.

**Post-Release**

- The deployment record links the artifact, configuration, and environment.
- The team monitors metrics and user feedback.
- If an incident occurs, roles coordinate under incident command.
- Post-incident action items are assigned to specific owners.

This example shows that no single team owns all of quality. Each team contributes its expertise to a shared decision and provides evidence for the release owner to act upon.

## 18. Anti-Patterns in Team Collaboration

| Anti-Pattern | Consequence | How to Improve |
|---|---|---|
| Development throws builds over the wall to QA | QA receives changes late without context | Involve QA from requirements and design |
| QA is solely responsible for quality | Developers invest less in testing and maintainability | Quality is a shared responsibility; QA leads test strategy |
| Security only reviews right before production | Late discovery, expensive fixes | Shift-left and automate baselines |
| Operations only joins at deployment time | Missing observability, capacity, and recovery | Join design/release readiness based on risk |
| No owner for quality gates | Gates fail with no one resolving them | Assign owners, SLAs, and escalation paths |
| Too many people approving simultaneously | Slow decisions and diluted accountability | RACI with one clear A |
| Developers bypass security findings on their own | Risk acceptance lacks independence | Policy-based exceptions with proper approval |
| Handoff contains only an artifact | Operations lacks configs and runbooks | Structured deployment handoff |
| Releasing based solely on a green pipeline | Misses readiness and runtime risks | Review evidence and production conditions |
| Incidents focus on blaming individuals | Reduces collaboration, yields weak action items | System-focused post-incident reviews |
| Decisions are not recorded | Hard to audit and debates repeat | Store release/incident records |
| Action items are never closed | The same faults recur repeatedly | Assign owners, deadlines, and effectiveness checks |

## 19. Responsibility Alignment Checklist

Before promoting a change to production, confirm:

- [ ] There is an owner for the change and a release coordinator.
- [ ] Development, QA, Security, and Operations are engaged according to risk level.
- [ ] Acceptance criteria and test strategy are clear.
- [ ] Developers own unit/component tests and code-level defect fixes.
- [ ] QA provides test scope, results, and residual risks.
- [ ] Security policies, findings, and exceptions have clear owners.
- [ ] Operations confirms environment, capacity, observability, and recovery.
- [ ] Quality gates have defined criteria, evidence, and accountable owners.
- [ ] Authority to block, approve, and accept risk is explicitly defined.
- [ ] Pull requests document data/schema/config impacts.
- [ ] Artifacts, reports, and releases are linked by ID/digest.
- [ ] Deployment handoff includes runbooks, dashboards, alerts, and rollback constraints.
- [ ] A risk-based release readiness review is performed.
- [ ] Post-deploy monitoring owners and rollout stop conditions are defined.
- [ ] Incident commander and on-call escalation path are established.
- [ ] Post-incident action items have owners, deadlines, and verification methods.

## 20. Self-Assessment Exercise

A team is preparing to release an internal money transfer feature. Current state:

- Developers have finished code and unit tests.
- QA only receives the build on the final day before release.
- Security has not reviewed authorization or the threat model.
- Operations does not know whether the change requires a migration.
- The pipeline reports green, but there is no integration test report.
- The release manager does not know who has authority to approve a security exception.
- There is no dedicated runbook or dashboard for the transfer flow.

Redesign the collaboration model:

1. Which roles need to be involved during the requirements and design phase?
2. Which scenarios should acceptance criteria and the test strategy cover?
3. Who is responsible for fixing authorization flaws, and who verifies policy compliance?
4. Who needs to verify migrations and data compatibility?
5. How should the pipeline handle a missing integration report?
6. Which roles should be included in the RACI for release readiness?
7. Who has authority to approve production release and risk exceptions?
8. What dashboards, alerts, and runbooks does operations need?
9. If a canary increases transfer errors, who coordinates the incident and who executes mitigation?
10. What action items must be completed before the next release?

A sound approach brings QA, security, and operations in before code is finished; assigns owners to each gate; requires complete reports; prepares a deployment handoff; and releases only after authorized approvers have reviewed both evidence and residual risks.

## Conclusion

Effective CI/CD collaboration requires a continuous chain of accountability across development, testing, security, and operations. Development builds testable and operable changes; QA leads test strategy and provides quality evidence; Security defines and advises on risk controls; Operations safeguards environments, deployments, observability, and recovery. The release owner coordinates decisions based on policy and evidence.

Define RACI and decision authority, engage domain expertise early, assign owners to every quality gate, prepare structured release handoffs, and align on incident response. When every activity has clear ownership, completion criteria, and evidence, teams can release faster while preserving service quality, security, and reliability.
