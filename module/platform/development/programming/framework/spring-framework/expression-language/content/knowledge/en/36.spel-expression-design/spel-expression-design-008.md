# Manage SpEL Expressions Like Versioned and Reviewed Source Code

In a Spring application, a SpEL expression can determine how values are computed, data is filtered, features are shown, or business rules are executed. When expressions are stored in configuration, a database, or an admin system, they remain executable logic capable of affecting application behavior. Therefore, expressions must be managed with discipline similar to source code: stable identifiers, version history, clear ownership, reviews, testing, and a release workflow.

Expressions should not be treated as strings that can be edited directly in production without leaving a trace. A small change such as adjusting a threshold, changing a property, or adding a method call can alter business outcomes. Version management makes it possible to know exactly which expression is running, who changed it, how the change was tested, and how to roll back to a prior version.

This lesson explains how to design an expression lifecycle, from storage and identifier assignment to review, testing, release, rollback, and runtime operation.

## 1. Why Must Expressions Be Managed Like Source Code?

An expression may be shorter than a Java class, yet it still contains executable logic. For example:

~~~text
status == 'ACTIVE' and balance >= 100
~~~

Changing the threshold from 100 to 500 can disqualify an entire group of accounts. Adding a method call or bean reference can significantly expand the behavior executed during evaluation.

If expressions are edited directly in a database without versioning or an audit trail, the development team struggles to answer key questions:

- Which value is currently running in production?
- Who changed the expression and when?
- Was that change reviewed and tested?
- Is the expression compatible with the current DTO and property versions?
- When an error occurs, can the previous version be restored deterministically?

Managing expressions like source code establishes a traceable change history and helps control the impact of each release.

## 2. Assign a Stable Identifier to Each Expression

Each expression should have a stable ID independent of its content and version number.

For example:

~~~text
account.eligibility
checkout.free-shipping
invoice.tax-rate
document.read-policy
~~~

The ID is used to reference the expression in configuration, logs, tests, and release systems. Do not use the expression content itself as the identifier, because the content changes with each revision.

An expression record can include the following fields:

| Field | Purpose |
|---|---|
| expressionId | Stable identifier of the rule |
| version | Immutable version of the content |
| expressionText | Stored SpEL string |
| description | Description of business purpose |
| owner | Responsible team or person |
| inputSchemaVersion | Version of the input data structure |
| expectedResultType | Expected result type |
| status | Draft, reviewed, approved, active, or retired |
| createdAt / createdBy | Timestamp and creator |
| reviewedAt / reviewedBy | Timestamp and reviewer |
| changeReference | Link to pull request or ticket |

Separating expressionId from version allows a rule to have multiple versions while callers continue using the same identifier.

## 3. Store Immutable Revisions

Once an expression has been approved or released, do not directly edit the content of that revision. Changes create a new revision.

For example:

| Expression ID | Version | Content |
|---|---:|---|
| account.eligibility | 1 | status == 'ACTIVE' |
| account.eligibility | 2 | status == 'ACTIVE' and age >= 18 |
| account.eligibility | 3 | status == 'ACTIVE' and age >= 21 |

Revisions 1, 2, and 3 remain preserved for historical lookup. The active status only identifies which revision is currently in use for a specific environment or tenant.

Do not overwrite the content of a released revision. If a bug fix is needed, create a new revision and link it to the previous revision. This practice supports auditing, rollback, and reproducing past decision outcomes.

Incrementing integers can be used for versions. If the organization has clear conventions, semantic versioning or build numbers can also be used. What matters is that versions are unique, ordered or clearly linked by lineage, and never reused for different content.

## 4. Manage Expressions in Source Control

If expressions change alongside the software development cycle, storing them in a repository lets you leverage existing Git workflows: branches, pull requests, diffs, reviews, and release tags.

Example directory structure:

~~~text
config/
  expressions/
    account-eligibility.spel
    free-shipping.spel
    document-read-policy.spel
  expression-manifest.yml
  expression-tests/
    AccountEligibilityTest.java
    FreeShippingTest.java
~~~

A manifest can describe IDs, files, versions, and result types:

~~~yaml
expressions:
  - id: account.eligibility
    version: 3
    file: expressions/account-eligibility.spel
    inputSchema: account-rule-view-v2
    resultType: Boolean
    owner: account-platform
~~~

In practice, the manifest schema and format should be aligned consistently with the project's build tools. The manifest holds management metadata, while expression files contain the raw SpEL content.

Benefits of source control:

- Inspect exact diffs between revisions.
- Review expressions alongside related DTO or Java code changes.
- Tie revisions to commits or releases.
- Run automated tests in CI.
- Restore a prior version via a reviewed change.

If business needs require administrators to modify rules without releasing the application, revisions can be stored in a database or rule service. Even then, maintain export/import, audit logs, approvals, and a mechanism to sync approved revisions back to a controlled repository.

## 5. Document Purpose and Data Contracts

An expression is only meaningful when we know what data it reads and how its result is used. Every expression should have a business description along with an input/output contract.

For example:

~~~text
ID: account.eligibility
Purpose: Determine whether an account is eligible to use the feature.
Root type: AccountRuleView
Input schema: account-rule-view-v2
Result type: Boolean
Allowed properties: status, age, balance
Owner: account-platform
~~~

The input contract should describe:

- Properties permitted to be read.
- Data type of each property.
- Which properties can be null.
- Maximum size of collections if any.
- Data conversion or normalization rules.
- DTO or schema version the expression depends on.

The output contract should specify the result type, such as Boolean, String, or BigDecimal, along with the business meaning of each value.

If a property is renamed or its data type changes, treat it as a compatibility change that must be checked against every expression depending on that schema.

## 6. Review Expressions Like Code

Reviewing does not just check whether an expression parses. Reviewers need to understand the business intent and the objects the expression can access.

A review process can check:

1. Do the ID and description accurately reflect the purpose?
2. Does the expression read the right properties and use the right data types?
3. Are null, empty, and boundary cases defined?
4. Does the expression invoke methods or reference beans? If so, are the reason and access permissions clear?
5. Does the root object contain data or behavior beyond what is needed?
6. Does the result match the type expected by the caller?
7. Are there tests for true, false, and edge cases?
8. Is the change compatible with the active input schema version?
9. Are release and rollback plans in place?

Reviews should involve both business-domain and technical reviewers when expressions affect critical decisions. Do not approve merely because an expression is short or easy to read.

## 7. Write Tests Tied to Each Revision

Each revision should have a test suite representing input cases and expected outcomes. Tests use the parser and EvaluationContext directly when the goal is validating the expression.

For example:

~~~java
class AccountEligibilityTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    private final Expression expression =
            parser.parseExpression(
                    "status == 'ACTIVE' and age >= 18 and balance > 0"
            );

    @Test
    void acceptsEligibleAccount() {
        AccountRuleView source =
                new AccountRuleView(
                        "ACTIVE",
                        25,
                        new BigDecimal("150.00")
                );

        SimpleEvaluationContext context =
                SimpleEvaluationContext.forReadOnlyDataBinding()
                        .build();

        Boolean result = expression.getValue(
                context,
                source,
                Boolean.class
        );

        assertTrue(result);
    }

    @Test
    void rejectsInactiveAccount() {
        AccountRuleView source =
                new AccountRuleView(
                        "SUSPENDED",
                        25,
                        new BigDecimal("150.00")
                );

        SimpleEvaluationContext context =
                SimpleEvaluationContext.forReadOnlyDataBinding()
                        .build();

        Boolean result = expression.getValue(
                context,
                source,
                Boolean.class
        );

        assertFalse(result);
    }
}
~~~

The test suite should include:

- Typical cases returning true.
- Typical cases returning false.
- Values right at the threshold and immediately on both sides of the threshold.
- Nulls and missing nested properties.
- Empty collections or collections at maximum size limits.
- Result types violating the contract.
- Non-existent properties after schema changes.
- Parse errors and evaluation errors.

Tests should be tied to specific revisions so released versions' results can be reproduced. When an expression changes, re-run all related tests rather than only updating the expected value of a failing test.

## 8. Verify Compatibility with the Input Schema

Expressions often depend on DTO or read-model properties. Schema changes can break older expressions.

For example, revision 2 uses the property accountStatus:

~~~text
accountStatus == 'ACTIVE'
~~~

If a new DTO renames the property to status, the old expression may throw evaluation errors.

This can be managed using one of the following approaches:

- Bind each revision to a specific inputSchemaVersion.
- Maintain a compatible DTO adapter during the transition period.
- Create a new expression revision at the same time the schema changes.
- Validate all active expressions before releasing a new schema.
- Have a deprecation policy for retiring support for old schemas.

Do not rename or delete properties and wait for errors to surface in production. CI can load all registered expressions and evaluate them against fixtures matching the target schema.

## 9. Environment-Based Release Workflow

An expression revision should move through explicit states. For example:

<escape>Draft → Reviewed → Approved → Staged → Active → Retired</escape>

- Draft: author is drafting and running initial tests.
- Reviewed: technical and business reviews have been completed.
- Approved: accepted by an authorized approver.
- Staged: deployed to a staging environment or a small canary group.
- Active: selected to handle live requests.
- Retired: no longer selected for new requests but retained for history.

Do not allow a draft to automatically become active merely because it was saved successfully. Saving a revision and activating a revision are two separate operations.

Releases can progress across development, staging, and production environments. At each step, retain the version and activation configuration so you know which environment is running which revision.

## 10. Safe Revision Activation

Instead of directly updating running expression text, use an active version reference:

~~~text
account.eligibility -> version 3
~~~

Activation can follow these steps:

1. Identify the approved revision.
2. Confirm test and input schema compatibility.
3. Load the revision into the staging environment.
4. Evaluate against sample datasets or shadow traffic if appropriate.
5. Compare results against the currently active revision.
6. Approve switching the active pointer to the new revision.
7. Monitor parse/evaluation errors and result distributions after switching.

The active pointer should be updated atomically or through a configuration mechanism with clear consistency guarantees. Avoid a state where a request uses half the content of the old version and half the metadata of the new version.

If multiple tenants or user groups use different versions, the active version must be resolved per scope and explicitly logged.

## 11. Rollback and Reproducing Past Decisions

Because prior revisions are never overwritten, rollback can simply switch the active pointer back to a known stable revision.

For example:

~~~text
account.eligibility
  active: 3
  previous: 2
~~~

If version 3 causes errors, version 2 can be reactivated after confirming input schema and dependency compatibility.

To reproduce a past decision, store sufficient information:

- Expression ID and version used.
- Input schema version.
- Application or rule runtime version.
- Evaluation timestamp.
- Correlation ID or appropriate business ID.
- Outcome and error code if any.

It is not necessary to store all personal input data in logs. Minimized snapshots or controlled test data can be saved if reproduction is needed. Follow the application's data protection policies.

## 12. Manage Expression Caches and Revision Updates

Parsing an expression into an Expression object can be cached to avoid repeatedly re-parsing the same content. Cache keys should include both identifier and version, not just ID.

Example key:

~~~text
account.eligibility:v3
~~~

When a new version is activated, create a new cache entry or refresh the cache through a controlled mechanism. Do not mutate an Expression object currently used by other requests by modifying a shared context.

Key principles:

- Bounded cache capacity.
- Use keys consisting of expression ID and revision.
- Do not use unbounded caches for user-created expressions.
- Never share a mutable EvaluationContext across requests.
- Create appropriate contexts and root objects for each evaluation.
- Define invalidation behavior when the active version changes.
- Track cache hits, misses, and parse errors.

Parsers and Expressions can be reused under an appropriate design, whereas contexts usually hold per-evaluation variables and root objects. Keeping these two lifecycles separate prevents cross-request data leaks.

## 13. Audit Trail and Change Permissions

The expression management system should record who created, edited, reviewed, approved, activated, or retired a revision.

An audit record can include:

| Attribute | Content |
|---|---|
| expressionId | ID of the rule |
| fromVersion / toVersion | Previous and next revisions |
| actor | User or service performing the action |
| action | Create, edit, review, approve, activate, rollback |
| timestamp | Timestamp |
| changeReference | Pull request, ticket, or reason |
| environment | Affected environment |
| outcome | Success or failure |

Permissions should separate roles:

- Author can create revisions.
- Reviewer can review and request changes.
- Approver can approve.
- Operator can activate approved revisions.
- Auditor can read history and status.

One person may hold multiple roles under organizational policy, but sensitive actions require proper audit trails and control workflows.

## 14. Security Controls for Versioned Expressions

Versioning and reviews do not make an expression safe by themselves. Expressions are still evaluated in an EvaluationContext with whatever capabilities are provided.

For expressions stored or modified outside source code:

- Treat content as executable code, not harmless configuration strings.
- Allow only authorized users to create or modify revisions.
- Restrict root objects and accessible properties.
- Do not provide bean references, type access, or method invocation unless required.
- Use SimpleEvaluationContext when its restricted feature set satisfies requirements.
- Never concatenate request data directly into expression text.
- Validate result types and limit input resources.
- Never allow unreviewed revisions to be activated automatically.

If users need to author conditions themselves, consider a rule model or allowlisted DSL. Do not rely on successful parsing, content hashes, or versioning as substitutes for access control and evaluation capability limits.

## 15. Post-Release Monitoring and Incident Handling

After activating a new revision, monitoring metrics helps detect errors early:

- Evaluation counts by expression ID and version.
- True/false result ratios or result distributions matching business expectations.
- Parse and evaluation errors.
- Evaluation latency.
- Cache miss counts.
- Fallback frequency or usage of previous revisions.
- Result discrepancies between new and old revisions during trial phases.

Do not log sensitive contents of root objects or expressions unless necessary. Use expression ID, version, correlation ID, and error codes for tracing.

When an incident occurs:

1. Identify the expression ID and version currently in use.
2. Check the most recent change and approver.
3. Determine whether the error lies in parsing, evaluation, schema, data, or business logic.
4. If impact is severe, switch the active pointer back to a stable revision.
5. Create a bug-fix revision and add tests reproducing the incident.
6. Record the root cause and resolution in the change history.

## 16. Example Data Model for Revision Management

A simple model can separate identifier metadata from individual revision contents:

~~~java
public class ExpressionDefinition {
    private final String id;
    private final String description;
    private final String owner;

    public ExpressionDefinition(
            String id,
            String description,
            String owner) {
        this.id = id;
        this.description = description;
        this.owner = owner;
    }

    public String getId() {
        return id;
    }

    public String getDescription() {
        return description;
    }

    public String getOwner() {
        return owner;
    }
}

public class ExpressionRevision {
    private final String expressionId;
    private final int version;
    private final String expressionText;
    private final String inputSchemaVersion;
    private final String resultType;

    public ExpressionRevision(
            String expressionId,
            int version,
            String expressionText,
            String inputSchemaVersion,
            String resultType) {
        this.expressionId = expressionId;
        this.version = version;
        this.expressionText = expressionText;
        this.inputSchemaVersion = inputSchemaVersion;
        this.resultType = resultType;
    }

    public String getExpressionId() {
        return expressionId;
    }

    public int getVersion() {
        return version;
    }

    public String getExpressionText() {
        return expressionText;
    }

    public String getInputSchemaVersion() {
        return inputSchemaVersion;
    }

    public String getResultType() {
        return resultType;
    }
}
~~~

The model above merely illustrates separating metadata and revisions. Real applications may store these objects in Git, a database, or a rule registry. Keep revisions immutable after approval and store active state in a separate structure.

## 17. Checklist for an Expression Change

| Stage | Verification Item |
|---|---|
| Authoring | ID, purpose, owner, and input schema are clear |
| Revision | New version created; released versions are not overwritten |
| Review | Business intent, property access, and method/bean behavior reviewed |
| Testing | True, false, null, boundary, and result type tests exist |
| Compatibility | DTO and schema are compatible with the revision |
| Approval | Approved by an authorized approver |
| Staging | Verified in staging environment with test data |
| Activation | Active pointer switched under control |
| Monitoring | Metrics, logs, and alerts exist for the new version |
| Rollback | Can revert to a stable revision |
| Audit | Actor, timestamp, and change reference recorded |

## 18. Key Takeaways

- SpEL expressions contain logic capable of affecting application behavior, so manage them like source code.
- Every expression should have a stable ID, owner, description, input schema, and result type.
- Released revisions should be immutable; every change creates a new version.
- Source control supports diff reviews, automated testing, and linking expressions to commits/releases.
- Reviews must examine business meaning, properties, methods, access privileges, and null/boundary cases.
- Tie tests to each revision so outcomes can be reproduced.
- Verify compatibility between expression versions and input schema versions.
- Separate draft, approved, and active states; saving a revision does not mean activating it.
- Roll back by switching the active pointer back to a stable revision.
- Cache Expressions by ID and version; never share a mutable EvaluationContext across requests.
- Audit create, review, approve, activate, and rollback actions.
- Versioning does not replace security controls, access restrictions, or EvaluationContext resource limits.
