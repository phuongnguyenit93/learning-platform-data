# Unit, Integration, and End-to-End Testing Strategies on AWS

Applications running on AWS typically consist of multiple cooperating services: API Gateway receives requests, Lambda or ECS handles business logic, DynamoDB or RDS stores data, SQS and EventBridge transport events, S3 stores files, IAM controls permissions, and CloudWatch monitors operations. A handler function may pass isolated tests yet still fail in a real environment due to missing policy permissions, misconfigured event mappings, inappropriate timeouts, retries creating duplicate data, or mismatched service configurations.

A testing strategy on AWS needs to verify each component at the appropriate level. Unit tests check small units of logic and run fast. Integration tests verify the contract between the application and AWS services or between services. End-to-end (E2E) tests validate a complete business flow across deployed components. These testing layers complement each other; no single layer is sufficient to prove that the entire system works correctly.

AWS provides many tools to support this workflow: AWS SAM CLI and AWS CDK for development, AWS CodeBuild and CodePipeline for CI/CD, CloudFormation for infrastructure deployment, CloudWatch and X-Ray for observability, CloudWatch Synthetics for testing user journeys, AWS Fault Injection Service (FIS) for fault-tolerance testing, and security services for evaluating configurations. You can combine local testing, dedicated AWS environments, and controlled testing in production.

This lesson falls within the CLOUD_PROVIDERS_AWS scope: designing and deploying secure, observable, resilient, and cost-controlled applications. The focus is on building unit, integration, and E2E testing strategies on AWS, selecting environments, managing test data, automating in pipelines, and troubleshooting based on evidence.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between unit tests, component tests, integration tests, contract tests, and end-to-end tests.
- Build a test pyramid suitable for AWS-based applications.
- Determine what should run locally and what needs to be tested on real AWS services.
- Test Lambda, API Gateway, S3, DynamoDB, RDS, SQS, EventBridge, and Step Functions.
- Use AWS SAM CLI, AWS CDK, and CloudFormation in the testing workflow.
- Design test accounts, ephemeral environments, and safe test data.
- Test IAM permissions for both allowed and denied cases.
- Automate testing in CodeBuild, CodePipeline, or a compatible CI/CD platform.
- Design performance, security, resilience, recovery, and smoke tests.
- Monitor results with CloudWatch, X-Ray, CloudTrail, and logs with correlation IDs.
- Evaluate test quality, feedback time, and pipeline cost.

## 2. Why Multiple Testing Layers Are Needed

### 2.1. Testing One Function Does Not Prove the System Works

Suppose you have an order-creation API:

1. API Gateway receives the request.
2. Lambda validates the data and checks permissions.
3. Lambda writes the order to DynamoDB.
4. Lambda sends an event to EventBridge.
5. A consumer processes payment or notifications.
6. A dashboard reads the order status.

A unit test can confirm that the total-calculation function returns the right result. However, it does not prove that:

- API Gateway maps the body and headers properly.
- The Lambda execution role has permission to write to DynamoDB.
- The DynamoDB table has the appropriate key schema.
- The EventBridge rule matches the event.
- The consumer receives the event and handles it idempotently.
- Retries or DLQs work as designed.
- Users can only read orders they are authorized to access.

Therefore, testing must cover logic, service boundaries, and business journeys.

### 2.2. Testing Layers

| Layer | Scope | Objective | Characteristics |
|---|---|---|---|
| Unit test | Small function, class, or module | Verify logic and business rules | Fast, isolated from dependencies |
| Component test | A single component running close to a real environment | Test handler, container, or worker | Can use fake dependencies or local emulators |
| Integration test | Two or more components/services | Test APIs, permissions, events, and real data | Usually requires an AWS test environment |
| Contract test | Producer-consumer contract | Detect breaking schema/API changes | Can run fast in CI |
| End-to-end test | Business flow across the system | Verify real user behavior | Slower, fewer test cases |
| Non-functional test | Performance, security, recovery | Verify operational requirements | Requires dedicated limits and planning |

### 2.3. Test Pyramid

A common strategy has many unit tests, fewer integration tests, and a smaller number of E2E tests. The reason is that unit tests are fast and easy to diagnose; E2E tests provide broad coverage but are time-consuming and easily affected by environment state.

~~~mermaid
flowchart TB
    E["E2E tests<br/>Few, covering core business flows"]
    I["Integration and contract tests<br/>Verify AWS service boundaries"]
    U["Unit tests<br/>Many, fast, and isolated"]
    E --> I --> U
~~~

This is a guiding principle, not a rigid ratio. An event-driven system with high risk at integration boundaries may need more integration tests than a simple CRUD application.

### 2.4. The Test Pyramid Does Not Replace Production Validation

Passing tests before deployment does not prove a release will work in production. DNS configuration, secrets, quotas, real data, traffic patterns, and external dependencies may differ. After deployment, you need smoke tests, health checks, canary or synthetic monitoring, and metric tracking to detect regressions.

## 3. Defining Scope and Testing Criteria

### 3.1. Start from Requirements and Risks

Do not write tests just to increase test count or coverage. First, identify:

- Which business behaviors are critical?
- Which data must never be lost or exposed?
- Which components have permission to modify data?
- Which dependencies can fail or become slow?
- How many requests or events does the system need to handle?
- What are the RPO, RTO, and SLA?
- What is the consequence of failure?

From there, choose tests capable of detecting the corresponding failures. For example, a requirement not to create two orders when a client retries needs unit tests for the idempotency key, integration tests for conditional writes, and E2E tests for the scenario where a request times out after a successful write.

### 3.2. Write Verifiable Acceptance Criteria

A good acceptance criterion describes the input, action, and observable outcome.

For example:

- When an authorized user sends a valid request, the API returns a success status code and creates exactly one order record.
- When an unauthorized user sends a request, the API returns an authorization error and writes no data.
- When a downstream consumer experiences a transient error, the message is retried per policy without creating duplicate side effects.
- When message volume exceeds processing capacity, the backlog is observable and the system recovers after load decreases.
- When the database loses connectivity, the API returns a controlled error and does not leave requests hanging indefinitely.

### 3.3. Traceability

Link test cases to requirements, risks, or issues. When a test fails, the team needs to know which behavior is being protected and whether the release should be blocked. You can store test IDs, requirement IDs, commits, build IDs, and deployment IDs in reports.

### 3.4. Test Severity Classification

| Severity | Example | Action on Failure |
|---|---|---|
| Critical | Incorrect access permissions, lost transactions, data corruption | Block release |
| High | Core business flow fails to complete | Block release or require exception approval |
| Medium | A secondary feature fails | Assess impact and plan a fix |
| Low | Display discrepancy that does not affect data | Log and handle via backlog |

Do not use a single pass/fail criterion for every test. A flaky unit test is not the same as an authorization bug in production.

## 4. Designing Test Environments on AWS

### 4.1. Local Development

A local environment is suitable for:

- Unit tests and logic checks.
- Serialization/deserialization tests.
- Testing handlers with event fixtures.
- Running APIs or Lambda handlers in a compatible runtime.
- Quick contract and validation checks.

Tools:

- AWS SAM CLI supports building, invoking, and running some Lambda/API components locally.
- AWS CDK supports synthesizing templates and testing construct structures.
- DynamoDB Local supports developing and testing some DynamoDB behaviors.
- AWS SDK mocks/stubs support testing applications without calling AWS.
- LocalStack is a third-party AWS service emulator option; you must verify supported features and behaviors before using it as evidence of AWS compatibility.

A local environment does not replace integration tests on AWS. Emulators may not fully replicate IAM, quotas, event delivery, networking, consistency, or actual service limits.

### 4.2. AWS Test Account

Integration and E2E tests typically require a dedicated AWS account or environment. Prefer using AWS Organizations to separate accounts for development, test, staging, and production when organizational scale allows.

Benefits:

- Reduces the risk of tests deleting or overwriting production data.
- Allows separate quotas, policies, and budgets.
- Simplifies cleanup of test resources.
- Provides clearer security boundaries and auditing.
- Enables cross-account testing if the real architecture uses it.

Do not treat a separate VPC within the same production account as a sufficient protective boundary. IAM roles, buckets, event buses, KMS keys, and many other resources may still be shared across the account.

### 4.3. Ephemeral Environments

An ephemeral environment is an environment created for a branch, pull request, or test run and then deleted after completion. It can be deployed using CloudFormation/CDK/SAM and named with the build ID.

A lifecycle:

1. CI creates a stack with a unique name.
2. Provision resources and test data.
3. Run integration/E2E tests.
4. Collect logs, reports, and metrics.
5. Delete the stack and dependent resources.
6. Verify cleanup succeeded.

Ephemeral environments help avoid running tests on shared resources. However, you need to handle resources that are hard to delete, such as non-empty S3 buckets, log groups, snapshots, retained resources, or databases with deletion protection.

### 4.4. Shared Test Environments

A shared test environment can save costs, but conflicts occur easily:

- Two test runs use the same record or queue.
- One test deletes data belonging to another test.
- Messages from an old run are processed in a new run.
- Tests depend on execution order.
- One deployment changes the schema while another test is running.

The solution is namespacing by run ID, isolated data, separate queues/topics, or ephemeral stacks. If a shared environment must be used, manage locks and avoid tests that destroy shared data.

### 4.5. Managing Configuration and Secrets

Test environments must not contain production credentials. Use IAM roles, temporary credentials, AWS Secrets Manager, or Systems Manager Parameter Store as needed.

Separate:

- Non-sensitive environment variables.
- Secrets that require protection.
- Test fixtures.
- Environment-specific endpoints/resource ARNs.

Do not commit secrets, private keys, tokens, or real data to the repository. Pipelines should only grant secrets to the jobs that need them and limit credential lifetimes.

## 5. Unit Testing AWS Applications

### 5.1. Decouple Business Logic from the AWS SDK

A Lambda handler should not contain all validation, calculations, database calls, event publishing, and response formatting in one large function. Separating pure logic from adapters keeps unit tests fast and easy to understand.

Example structure:

~~~text
src/
  handlers/
    create_order.py
  domain/
    order.py
    pricing.py
  adapters/
    order_repository.py
    event_publisher.py
tests/
  unit/
    test_pricing.py
    test_create_order.py
~~~

Domain logic can be tested without instantiating AWS clients. Adapters are responsible for translating business calls into SDK requests.

### 5.2. Example of Testing Pure Logic

~~~python
from decimal import Decimal

def calculate_total(items, tax_rate):
    if not items:
        raise ValueError("Order must contain at least one item")

    subtotal = sum(
        Decimal(str(item["price"])) * item["quantity"]
        for item in items
    )
    return (subtotal * (Decimal("1") + Decimal(str(tax_rate)))).quantize(
        Decimal("0.01")
    )

def test_calculate_total():
    items = [
        {"price": "10.00", "quantity": 2},
        {"price": "5.50", "quantity": 1},
    ]
    assert calculate_total(items, "0.10") == Decimal("28.05")
~~~

This test verifies pricing rules and does not depend on AWS. You should add cases for an empty list, negative quantities, invalid prices, rounding, and boundary tax rates.

### 5.3. Mocking the AWS SDK at the Boundary

When testing adapters, you can mock the client or use a stub to verify that the application calls the right operation and handles responses/errors properly. In Python, botocore Stubber can provide predefined responses for an AWS SDK client. In Java, you can use Mockito to mock AWS SDK v2 interfaces/clients.

Conceptual example:

~~~python
from botocore.stub import Stubber
import boto3

client = boto3.client("dynamodb", region_name="ap-southeast-1")
stubber = Stubber(client)

stubber.add_response(
    "put_item",
    {"ConsumedCapacity": {"CapacityUnits": 1.0}},
    {
        "TableName": "orders-test",
        "Item": {
            "orderId": {"S": "order-123"},
            "status": {"S": "PENDING"},
        },
    },
)

with stubber:
    response = client.put_item(
        TableName="orders-test",
        Item={
            "orderId": {"S": "order-123"},
            "status": {"S": "PENDING"},
        },
    )
    assert response["ConsumedCapacity"]["CapacityUnits"] == 1.0
~~~

This is an example of testing request/response behavior at the SDK boundary. Stubber does not verify IAM permissions, the real table schema, networking, or DynamoDB service behavior. Those parts require integration tests on AWS.

### 5.4. Mock Just Enough

Over-mocking can make tests prove only that the mocks work. Do not mock every internal class and assert call counts for each function if what matters is the business outcome.

What you should mock:

- Clock when testing time-dependent behavior.
- Random generator when deterministic output is needed.
- External APIs outside the test scope.
- AWS clients in adapter unit tests.

What you should not mock:

- The entire domain logic.
- Every internal function within the same module.
- Assumed responses that do not match the AWS API.

For each mock, clearly define the contract it represents and have an integration test verify that contract.

### 5.5. Test Cases and Property-Based Testing

Unit tests should cover:

- Happy path.
- Missing or wrongly typed inputs.
- Boundary values.
- Duplicate requests.
- Timeouts/exceptions from dependencies.
- Retries and idempotency.
- Access permissions and validation.

Property-based testing can generate diverse inputs to verify invariants—for example, that the total amount is non-negative when all items are valid, or that encoding then decoding an event preserves required fields. Use an appropriate library for your language and pin seeds so results are reproducible.

## 6. Component Testing and Testing Lambda

### 6.1. Testing a Lambda Handler

A Lambda handler receives an event and context and returns a response or performs side effects. Unit/component tests need to verify:

- Event shape matching the trigger source.
- Validation and error mapping.
- Timeout-sensitive logic.
- Idempotency.
- Structured logging.
- Not writing sensitive data to logs.

Create separate fixtures for API Gateway proxy events, SQS events, EventBridge events, S3 notifications, or DynamoDB Streams. Do not reuse one generic JSON event for all triggers because their envelopes and semantics differ.

### 6.2. AWS SAM CLI

AWS SAM CLI can:

- Build the application from a template.
- Invoke a Lambda function locally with a JSON event.
- Run an API Gateway-compatible local endpoint for certain API types.
- Create packages/deployment artifacts.
- Validate templates and assist with stack deployments.

Example:

~~~bash
sam build
sam local invoke CreateOrderFunction --event events/api-create-order.json
~~~

Example of running an API locally:

~~~bash
sam local start-api
~~~

SAM local is useful for rapid development loops, but it does not fully simulate IAM, service integrations, concurrency, VPC networking, or all AWS runtime behaviors. You must test the deployed function in a test account.

### 6.3. Lambda Execution Role

Lambda runs using an execution role. Testing on AWS needs to verify:

- The role has the least-privilege permissions required.
- Resource ARNs and Regions are correct.
- KMS permissions if data is encrypted.
- VPC security groups, subnets, and endpoints if the function runs inside a VPC.
- Secrets/parameters are readable.
- Permission boundaries or SCPs do not block the operation.

Unit tests cannot prove that a role has real permissions. Integration tests should invoke the flow using the deployed function and test both allowed and denied operations.

### 6.4. Lambda Retries and Duplicates

Retry behavior depends on the invocation source:

- Synchronous invocation usually returns errors to the caller; the caller decides whether to retry.
- Asynchronous invocation has built-in retry behavior and configurable destinations/DLQs.
- SQS event source mappings poll the queue and process batches; failures can cause messages to be redelivered.
- Stream event source mappings have configurable checkpoint and retry semantics.

Do not assume every trigger shares the same retry behavior. Test the actual configuration, partial batch responses, maximum record age, retry attempts, and DLQs/destinations as appropriate.

### 6.5. Testing Concurrency and Cold Starts

For latency-sensitive workloads, measure:

- Duration and init duration.
- Concurrent executions.
- Throttles.
- Memory and CPU behavior.
- Database connection reuse.
- Timeout behavior when dependencies are slow.

Do not run a single local invocation to draw performance conclusions. You need representative load in an AWS test environment with near-production concurrency and data.

## 7. Integration Testing with AWS Services

### 7.1. Principles

Integration tests need to verify real contracts between components. A test should:

1. Create or identify dedicated test resources.
2. Prepare input data.
3. Call the real service/API.
4. Wait for the result using a condition with a timeout.
5. Read the output and verify the state.
6. Clean up created data/resources.

Use resource names containing a build ID or test run ID to avoid conflicts. Cleanup should run even when tests fail; use teardown hooks and a scheduled cleanup job for leftover resources.

### 7.2. Amazon S3

Cases to verify:

- PutObject and GetObject with the actual role.
- Bucket policies and KMS encryption.
- Event notifications or EventBridge events after object creation.
- Prefixes, metadata, and content types.
- Multipart uploads and cleanup of incomplete uploads if used by the application.
- Versioning and restoration when the application relies on object versions.
- Lifecycle rules not deleting data that is still needed.

S3 provides strong read-after-write consistency for supported object operations, yet event notifications and downstream consumers remain asynchronous flows. Tests should wait for events via polling with a timeout rather than a fixed sleep.

### 7.3. Amazon DynamoDB

Verify:

- Partition keys and sort keys.
- Conditional writes and optimistic locking.
- Update expressions.
- TTL behavior against business expectations.
- GSI/LSI queries.
- Transactions when using TransactWriteItems.
- IAM policies restricting tables/indexes.
- Throttling and retries.

Some index queries have eventual consistency. Tests should not assume every GSI query reflects writes immediately. If business logic requires consistent reads, choose an appropriate read mode and data model.

### 7.4. Amazon RDS/Aurora

Verify:

- Connectivity over the real network path.
- Security groups and subnet routing.
- Database credentials/Secrets Manager.
- Schema migrations.
- Transaction commits/rollbacks.
- Constraints, indexes, and query behavior.
- Connection pools and connection limits.
- Failover or reconnection if required by the workload.

Test migrations on a dedicated database with representative data and backups/snapshots as required. Do not run destructive migrations on a shared database without an approval process.

### 7.5. Amazon SQS

Verify:

- SendMessage and ReceiveMessage.
- Visibility timeout.
- Long polling.
- Redrive policy and DLQ.
- Batch size and partial batch responses.
- Duplicate delivery and idempotency.
- FIFO ordering and message groups when using FIFO queues.

SQS standard queues provide at-least-once delivery; consumers must tolerate duplicates. FIFO queues provide ordering/deduplication features but do not eliminate all business-layer idempotency requirements.

### 7.6. Amazon EventBridge

Verify:

- Event schemas and required fields.
- Event buses, rule patterns, and targets.
- Input transformers.
- Retry policies and DLQs.
- Permissions for targets.
- Duplicate events and consumer idempotency.
- Archive/replay if used by the application.

A rule whose pattern does not match can prevent an event from reaching its target without causing the producer publish call to fail. Test both positive and negative event pattern cases.

### 7.7. API Gateway

Verify:

- Routes and methods.
- Request/response mappings.
- JWT/IAM/Lambda authorizers.
- CORS.
- Validation and error mapping.
- Throttling and quotas.
- Timeout/integration behavior.
- Access logging and stage configuration.

Test the API directly through the deployed endpoint to verify gateway configuration. Handler unit tests cannot catch misconfigured mapping templates or authorizers.

### 7.8. AWS Step Functions

Verify:

- State transitions and branching.
- Retry/Catch.
- Timeouts and heartbeats.
- Input/output paths.
- Service integration permissions.
- Callback patterns or wait states.
- Compensation when a step fails.

Unit tests for function/task logic are still necessary. Integration tests must execute the state machine in a test account to verify service integrations and the execution role.

### 7.9. Lambda with SQS or EventBridge

Example flow:

1. Send a message containing a testRunId to SQS.
2. The event source mapping triggers Lambda.
3. Lambda writes the result to a DynamoDB test table.
4. The test polls DynamoDB by testRunId.
5. Verify record count and status.
6. Clean up messages/records.

Tests need timeouts and diagnostics when waiting too long. Avoid fixed sleeps of several seconds because faster or slower environments will make tests flaky.

## 8. Contract Testing and Schema Compatibility

### 8.1. Why Contract Testing Is Needed

In event-driven systems, producers and consumers can be deployed independently. A producer renaming a field or changing a data type can break consumers even when each service passes its own unit tests.

Contract tests verify:

- Event name/type.
- Required fields and optional fields.
- Data types and formats.
- Version.
- Field semantics.
- Backward/forward compatibility according to the chosen strategy.

### 8.2. Event Versioning

Example order event:

~~~json
{
  "version": "1",
  "source": "commerce.orders",
  "detail-type": "OrderCreated",
  "detail": {
    "orderId": "order-123",
    "customerId": "customer-456",
    "totalAmount": 125.50,
    "currency": "VND"
  }
}
~~~

When adding a field, older consumers can usually ignore unknown fields if parsers are designed flexibly. Renaming a field or changing its type can break the contract. Use a schema registry or JSON Schema/Avro/Protobuf appropriate for your system to manage versions.

### 8.3. Consumer-Driven Contracts

Consumers describe the parts of an event/API they require. Producers run contract tests to ensure changes do not break registered consumers. This is valuable when multiple teams develop independently and cannot run full E2E suites for every change.

## 9. End-to-End Testing

### 9.1. Choosing Critical Flows

E2E tests should focus on high-value or high-risk business journeys. For example:

- Logging in and creating an order.
- Completing payment and updating status.
- Uploading a file and processing it asynchronously.
- Ensuring users can only read data belonging to their own tenant.
- Completing a multi-step workflow and rolling back on failure.

There is no need to test every input combination via E2E if unit/integration tests already cover them. Keep the number of E2E tests moderate to reduce execution time and flakiness.

### 9.2. Testing Through Deployed Endpoints

E2E tests should follow the same communication path as real users or clients:

1. Obtain a test token from an identity provider or safe fixture.
2. Send requests through API Gateway/ALB/custom domain.
3. Track status via APIs or event/result stores.
4. Verify data and side effects.
5. Verify access permissions.
6. Clean up test data.

Do not invoke the Lambda function directly if the goal is to test API Gateway, authorizers, routing, and integration mappings.

### 9.3. Correlation IDs

Attach a testRunId or correlationId to requests and propagate it through logs and events. When an E2E test fails, you can search logs across API Gateway, Lambda, SQS, EventBridge, and consumers using the same ID.

Do not use correlation IDs as credentials or include personal data in them.

### 9.4. Polling Instead of Sleeping

Asynchronous flows require waiting for completion states. Use polling with:

- An overall timeout.
- Exponential backoff or an appropriate interval.
- Specific success conditions.
- Early failure conditions.
- Diagnostics upon timeout.

For example: wait for order status to transition from PENDING to PAID or FAILED. On timeout, report the testRunId, query execution ID, or message ID for investigation.

### 9.5. Testing Idempotency

Send the same request twice with the same idempotency key. The expected result is a single business transaction, even if the client did not receive the first response and retried.

Verify:

- The database contains only one business record.
- Downstream events do not cause duplicate side effects, or consumers deduplicate them.
- The retry response is consistent with the original transaction.
- The idempotency key has an appropriate TTL/retention.

## 10. Infrastructure as Code Testing

### 10.1. Why IaC Testing Is Needed

Application code may be correct while deployed infrastructure is misconfigured: public buckets, overly permissive Lambda roles, SQS visibility timeouts shorter than processing time, overly broad security group inbound rules, or APIs without access logging enabled.

IaC tests catch configuration defects before deployment.

### 10.2. AWS CDK Assertions

AWS CDK supports synthesizing CloudFormation templates and writing assertions to verify resources are configured properly. You can verify:

- Lambda runtime, timeout, and memory.
- IAM policy actions/resources.
- S3 Block Public Access and encryption.
- SQS DLQ and redrive policy.
- DynamoDB encryption and point-in-time recovery.
- API Gateway logging/throttling.

Illustrative TypeScript example:

~~~typescript
import { Template } from "aws-cdk-lib/assertions";
import { App, Stack } from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";

test("data bucket blocks public access", () => {
  const app = new App();
  const stack = new Stack(app);

  new s3.Bucket(stack, "DataBucket", {
    blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    enforceSSL: true,
  });

  const template = Template.fromStack(stack);
  template.hasResourceProperties("AWS::S3::Bucket", {
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
  });
});
~~~

This example tests the synthesized template. It does not prove the bucket is deployed properly or that account-level policies do not alter the outcome; post-deployment checks are still required.

### 10.3. CloudFormation Validation

In CI, you can:

- Validate template syntax.
- Lint CloudFormation templates.
- Check drift or change sets per workflow.
- Use CloudFormation Guard to enforce configuration rules.
- Validate dependencies and parameters.

CloudFormation Guard helps validate templates against policies such as encryption, public access, or network configuration. It does not replace security reviews and runtime tests.

### 10.4. Post-Deployment Verification

After deployment:

- Verify resources exist and have the expected configuration.
- Verify IAM roles can be assumed and required operations succeed.
- Verify log groups, alarms, and dashboards.
- Verify S3 public access settings and encryption.
- Verify security groups/routing.
- Verify service integrations.

IaC unit tests and post-deployment integration tests must go together.

## 11. Security Testing

### 11.1. Positive and Negative IAM Tests

Do not test only that a role can perform required actions. You must also verify that the role cannot access out-of-scope resources.

Example:

| Principal | Action | Expected Result |
|---|---|---|
| Order Lambda role | PutItem into orders table | Allow |
| Order Lambda role | Scan payroll table | Deny |
| Analyst role | Query granted curated dataset | Allow |
| Analyst role | Read raw PII prefix | Deny |
| Unauthenticated user | Call API requiring login | Deny |

Test real permissions in a test account using production-equivalent roles. The IAM Policy Simulator can assist with policy analysis, but it does not replace end-to-end testing with actual resource policies, SCPs, permission boundaries, and KMS key policies.

### 11.2. Authentication and Authorization Testing

Cases to include:

- Valid token.
- Expired token.
- Token with wrong issuer/audience.
- User not belonging to the tenant.
- User has a role but lacks permission on the resource.
- Request with a forged tenant ID.
- Direct access to object URLs or endpoints.

Check both responses and side effects. Rejected requests must not create records, emit events, or leak data in error messages.

### 11.3. Dependency and Vulnerability Scanning

CI can scan dependencies, container images, IaC, and secrets. Amazon Inspector helps detect vulnerabilities for supported resources; Amazon ECR enhanced scanning integrates with Inspector for container images as configured. Other tools can supplement with SAST, DAST, and license checks.

Scan findings should include severity, exploitability, owner, and remediation SLA. Do not automatically treat every finding as the same risk level; evaluate runtime exposure and exploitability.

### 11.4. Data and Privacy Testing

- Use synthetic or masked data.
- Do not copy production PII into test environments without approval.
- Restrict access to test artifacts.
- Clean up data after tests.
- Verify logs do not contain tokens, secrets, or sensitive data.
- Verify encryption at rest and in transit.

## 12. Performance and Load Testing

### 12.1. Objectives

Performance tests measure latency, throughput, concurrency, error rates, and resource utilization. Load tests verify the system handles expected load; stress tests find limits; spike tests evaluate sudden surges; soak tests uncover memory leaks or degradation over long durations.

### 12.2. Designing Workloads

Define:

- Requests per second or messages per second.
- Read/write ratio.
- Payload sizes.
- Request distribution and bursts.
- Concurrency.
- Duration.
- Acceptable error rate.
- Target p50, p95, and p99 latencies.

Use representative data and realistic behavior. A test hitting a single simple endpoint may not reflect real workloads if production involves joins, fan-out, or downstream calls.

### 12.3. Tools on AWS

You can use:

- The Distributed Load Testing on AWS solution to provision and coordinate load generators using a reference architecture.
- AWS CodeBuild or dedicated compute to run k6, JMeter, or an appropriate tool.
- CloudWatch to monitor service metrics.
- X-Ray/OpenTelemetry to pinpoint bottlenecks across requests.
- AWS Lambda Power Tuning for certain Lambda workloads to compare memory/latency/cost configurations.

Distributed Load Testing on AWS is a solution deployed on AWS, not a default free service. Account for the cost of load generators, networking, logs, and the services under test.

### 12.4. Monitoring Service Limits

Load tests may hit quotas or service limits before the application reaches its true limit. Monitor:

- Lambda concurrency and throttles.
- API Gateway throttling.
- DynamoDB throttled requests and consumed capacity.
- SQS queue depth and age of oldest message.
- Kinesis shard/throughput limits.
- RDS connection count and CPU.
- NAT Gateway/egress and network bottlenecks.

Distinguish between application limits, service limits, and load generator limits. If the test environment has lower quotas than production, interpret results in context.

### 12.5. Safety During Load Testing

- Test only designated accounts and endpoints.
- Set budgets and time limits.
- Use controlled ramp-up and ramp-down.
- Have a kill switch and an operator monitoring.
- Do not generate load against third-party services without permission.
- Do not run stress tests on production without planning and approval.
- Verify cleanup after testing.

## 13. Resilience, Chaos, and Disaster Recovery Testing

### 13.1. Resilience Testing

Test the system when dependencies are slow or failing:

- Database connection timeouts.
- SQS consumer stopped.
- Lambda throttling.
- External API returning 5xx.
- DNS or network disruptions.
- KMS or secret access failures.
- One Availability Zone unavailable in a test scenario.

Verify that retries, circuit breakers, timeouts, fallbacks, DLQs, backpressure, and alerts work properly.

### 13.2. AWS Fault Injection Service

AWS Fault Injection Service (FIS) enables running controlled fault injection experiments on supported AWS resources. It can be used to test scenarios such as injecting latency, disrupting networking, or stopping resources using service-supported actions.

An experiment requires:

1. Defining a hypothesis and objective.
2. Selecting explicit target resources.
3. Setting an IAM role with least-privilege permissions.
4. Configuring stop conditions and CloudWatch alarms.
5. Notifying operators and limiting the blast radius.
6. Running in an appropriate environment.
7. Observing impact and halting when thresholds are breached.
8. Recording results, fixing the system, and re-running.

Do not run fault injection arbitrarily in production. Start in test/staging and only expand with an approved risk-control plan.

### 13.3. Backup and Restore Testing

A successful backup job does not prove recoverability. Restore tests must:

- Restore a snapshot or backup into an isolated environment.
- Inspect the schema and data.
- Verify the application can connect.
- Check permissions and KMS keys.
- Measure recovery time.
- Compare data against the RPO.
- Run business smoke tests after restoration.

### 13.4. RPO and RTO

- RPO (Recovery Point Objective): maximum acceptable data loss measured in time.
- RTO (Recovery Time Objective): target time to restore service.

DR tests must measure actual RPO/RTO. For example, if the target RTO is 60 minutes but restoring the database and updating endpoints takes 3 hours, the architecture does not yet meet requirements.

### 13.5. Failover Testing

Test failing over to a database replica, backup Region, or standby queue/consumer if the architecture includes those components. Verify:

- DNS/endpoints and client reconnection.
- No split-brain or unintended concurrent writes.
- Secrets, certificates, and KMS keys are available.
- Event backlogs are processed.
- Data consistency after failover.
- Failback procedures can be executed.

## 14. CI/CD and Test Automation

### 14.1. Reference Pipeline

A pipeline can be divided into stages:

~~~mermaid
flowchart LR
    A[Commit / Pull request] --> B[Lint + SAST + dependency scan]
    B --> C[Unit tests]
    C --> D[Build artifact + IaC synth]
    D --> E[Template / policy tests]
    E --> F[Deploy ephemeral test stack]
    F --> G[Integration + contract tests]
    G --> H[E2E + smoke tests]
    H --> I[Deploy staging]
    I --> J[Performance / security / resilience checks]
    J --> K[Approval / release]
    K --> L[Canary or rolling deployment]
    L --> M[Production smoke + monitoring]
    M --> N[Promote or rollback]
~~~

Not every commit needs to run full performance or chaos tests. You can run unit and IaC tests on every pull request, integration/E2E on the main branch, and load/chaos/DR tests on a schedule or before major releases.

### 14.2. AWS CodeBuild

CodeBuild runs build/test commands in a build environment. You can use a buildspec to:

- Install dependencies.
- Run linters and unit tests.
- Build Lambda/container artifacts.
- Synthesize CloudFormation from CDK.
- Run contract/integration tests.
- Generate reports and store artifacts.

Abbreviated buildspec example:

~~~yaml
version: 0.2
phases:
  install:
    runtime-versions:
      python: 3.12
    commands:
      - pip install -r requirements-dev.txt
  build:
    commands:
      - python -m pytest tests/unit --junitxml=reports/unit.xml
      - sam build
reports:
  unit-tests:
    files:
      - reports/unit.xml
    file-format: JUNITXML
~~~

The runtime version must be supported by the CodeBuild image. This example only illustrates structure; projects should pin dependencies and create the report directory before writing files.

### 14.3. AWS CodePipeline

CodePipeline orchestrates source, build, test, approval, and deployment actions. You can use CodeBuild actions for unit/integration tests, CloudFormation actions for stack deployments, and manual approvals before production if required by process.

Pipelines should store artifacts and reports by build ID for investigation. Do not allow a test stage to use broader credentials than the deployment stage requires.

### 14.4. GitHub Actions or Other CI Systems

AWS does not require using CodePipeline. GitHub Actions, Jenkins, or other CI platforms can deploy to AWS using OpenID Connect (OIDC) to obtain temporary credentials via an IAM role. Prefer federation and short-lived roles over long-lived access keys stored in CI secrets.

### 14.5. Quality Gates

A quality gate may require:

- Unit tests pass.
- Critical integration tests pass.
- IaC security checks pass.
- No secrets in artifacts.
- Coverage meets thresholds for critical code.
- No unresolved critical vulnerabilities.
- E2E smoke tests pass.
- Deployment alarms in a healthy state.

Coverage is only one metric. 95% line coverage does not prove tests have proper assertions or validate critical behavior.

### 14.6. Cleanup and Artifact Retention

CI should:

- Delete ephemeral stacks after testing.
- Clean up objects, queue messages, and test data.
- Retain reports/logs long enough for investigation.
- Have scheduled cleanup for orphaned stacks.
- Track test environment costs.
- Avoid deleting artifacts or logs needed for auditing prematurely.

## 15. Post-Deployment Testing and Production Validation

### 15.1. Smoke Tests

A smoke test is a short post-deployment check to verify the system is ready. Examples:

- The API health endpoint returns a successful response.
- Authentication works.
- A test resource can be created and read.
- A queue consumer receives a sample message.
- Database connections and migrations are valid.

Smoke tests should have minimal side effects and include cleanup. Do not use tests that create real transactions or send notifications to real customers.

### 15.2. CloudWatch Synthetics

CloudWatch Synthetics uses canaries to run scripts that check endpoints or user journeys on a schedule. Canaries can verify API responses, TLS, DNS, or simple workflows and emit metrics/alarms on failure.

Canaries should use test accounts, isolated data, and protected secrets. If a canary runs against a production endpoint, design requests to avoid side effects and avoid accessing real user data.

### 15.3. Deployment Strategies

Common strategies:

- Rolling deployment: gradually replace instances/tasks.
- Blue/green: deploy a new environment and shift traffic.
- Canary: shift a portion of traffic and observe before expanding.
- Linear: increase traffic in steps.

AWS CodeDeploy supports deployment patterns for integrated compute targets, such as Lambda and ECS blue/green. Choose a strategy based on rollback capability, schema compatibility, and startup time.

### 15.4. Automated Rollback

Rollback can be triggered when alarms or deployment health checks fail. Define:

- Metric/error thresholds.
- Observation duration.
- Rollback conditions.
- Target artifact version to revert to.
- How to handle backward-incompatible database migrations.
- How to handle messages already created by the new consumer version.

Rolling back code does not automatically roll back data or schemas. Use expand-and-contract migrations so old and new versions can coexist during the transition window.

## 16. Observability and Troubleshooting Test Failures

### 16.1. Structured Logging

Logs should include fields such as:

- timestamp.
- level.
- service/function name.
- environment.
- requestId or correlationId.
- testRunId/buildId.
- operation.
- outcome/errorCode.
- duration.

Do not log secrets, tokens, private keys, or full sensitive payloads. Use redaction and restrict log read permissions.

### 16.2. CloudWatch

CloudWatch Logs, Metrics, Alarms, and Dashboards help monitor:

- Lambda errors, duration, throttles, and concurrency.
- API Gateway 4xx/5xx and latency.
- SQS queue depth and age of oldest message.
- DynamoDB throttling and consumed capacity.
- RDS CPU, connections, storage, and failover events.
- Step Functions execution failures.
- Custom business metrics.

Correlate test failures with metrics/logs in the exact time window. Use testRunId to find related requests.

### 16.3. AWS X-Ray and Distributed Tracing

AWS X-Ray or OpenTelemetry can trace requests across multiple services. Traces help determine whether latency lies in the API, Lambda, database, downstream HTTP calls, or queue processing.

To make traces useful:

- Propagate trace/correlation context.
- Enable instrumentation for appropriate services.
- Avoid excessive cardinality in metric dimensions.
- Keep trace sampling appropriate for the load.
- Protect traces if metadata contains sensitive information.

### 16.4. CloudTrail

CloudTrail records control-plane API activity and configured data events. When a test or deployment fails due to permissions, CloudTrail helps identify which principal called which API and the exact authorization error.

Not all data events are enabled by default; configure the event types and resources to audit. Overly broad logging can increase costs.

### 16.5. Classifying Test Failures

| Failure Type | Symptom | Remediation |
|---|---|---|
| Product defect | Consistently wrong assertions | Fix code or requirements |
| Environment defect | Missing or misconfigured endpoints/resources | Fix IaC/test environment |
| Permission defect | AccessDenied or KMS denied | Inspect roles, policies, boundaries, SCPs |
| Flaky test | Passes/fails intermittently without code changes | Eliminate races, fixed sleeps, shared data |
| Quota/throttling | Throttled or rate exceeded | Throttle load, check quotas |
| Test data defect | Invalid or stale fixtures | Versioned data setup |
| External dependency | Third-party API failure | Mock in unit tests, contract tests, or dedicated test sandbox |

Do not retry indefinitely to turn flaky tests into passes. Record retry counts and preserve the first failure for investigation.

## 17. Managing Test Data

### 17.1. Synthetic Data

Synthetic data is generated for testing and contains no real user information. You can generate:

- Fake customers.
- Orders with boundary states and values.
- Sample documents.
- Schema-compliant events.
- Large datasets for load testing.

Synthetic data improves reproducibility and avoids privacy risks. Ensure data matches production distributions closely enough for performance and edge-case tests to be meaningful.

### 17.2. Masking Production Data

If production data is needed to reproduce a bug, follow an approved process, minimize fields, mask or tokenize PII, restrict accounts, encrypt data, and set short retention. Do not copy production snapshots onto laptops or shared test accounts without controls.

### 17.3. Data Isolation

Each test run should have its own namespace or key prefix. For example:

~~~text
test-run-8f31/orders/order-001
test-run-8f31/events/order-created
test-run-8f31/uploads/input.csv
~~~

Use the run ID to isolate data and prevent one test's cleanup from deleting another run's resources.

### 17.4. Cleanup and TTL

Set TTL/lifecycle policies on temporary data where appropriate. However, TTL is not instant cleanup; DynamoDB TTL deletes items via a background mechanism. For tests that require immediate cleanup, call delete explicitly and verify the result.

## 18. Example Testing Strategy: Order API on AWS

### 18.1. Architecture

An order service application includes:

- API Gateway receiving requests.
- Lambda handling order creation.
- DynamoDB storing orders.
- EventBridge emitting OrderCreated.
- SQS receiving events for consumers.
- Consumer Lambda updating processing status.
- CloudWatch recording logs and metrics.

~~~mermaid
flowchart LR
    U[Client] --> A[API Gateway]
    A --> L[Create Order Lambda]
    L --> D[(DynamoDB)]
    L --> E[EventBridge]
    E --> Q[SQS]
    Q --> C[Consumer Lambda]
    C --> D
    A -. logs/metrics .-> O[CloudWatch]
    L -. traces .-> X[X-Ray]
    C -. traces .-> X
~~~

### 18.2. Unit Tests

- Calculate total amount and tax.
- Validate item quantity, currency, and address.
- Validate idempotency key.
- Determine valid order state transitions.
- Map domain errors to HTTP responses.
- Handle event schemas.

Mock the repository and event publisher at the boundary to test logic independently.

### 18.3. Integration Tests

- Deploy a dedicated test stack.
- Invoke the real Create Order Lambda or API.
- Verify the record is written to the DynamoDB test table.
- Verify the EventBridge rule matches OrderCreated.
- Verify the message arrives in SQS.
- Invoke the consumer via event source mapping or send a message per test flow.
- Verify final status and DLQ behavior when the consumer fails.
- Run negative role tests to verify out-of-scope tables cannot be accessed.

### 18.4. E2E Tests

- Send a request through API Gateway with a valid token.
- Poll the API until the order reaches a terminal state.
- Verify the order is created only once when retrying with the same idempotency key.
- Call the API with a user from another tenant and verify the order cannot be read.
- Send a malformed-schema request and verify no event is emitted.

### 18.5. Non-Functional Tests

- Load test order creation at expected throughput.
- Check p95/p99 latency and throttling.
- Temporarily pause the consumer, observe queue backlog and recovery.
- Test DLQ and replay.
- Restore a DynamoDB backup to an isolated environment and run smoke tests.
- Monitor cost per order during the test run.

## 19. Common Mistakes When Building a Test Strategy

| Mistake | Consequence | Fix |
|---|---|---|
| Writing only unit tests | Misses IAM, networking, and service integration issues | Add integration tests on AWS |
| Writing only E2E tests | Slow pipeline, hard-to-localize failures | Increase unit and contract tests |
| Mocking all AWS services | Tests miss policy or event mapping errors | Test key flows with real services |
| Using production data in tests | Privacy risk and data corruption | Use synthetic/masked data and separate accounts |
| Sharing resources across tests | Race conditions and flaky tests | Namespace by run or use ephemeral stacks |
| Fixed sleeps waiting for events | Unstable tests | Poll with conditions and timeouts |
| Not testing negative permissions | Overly broad permissions go undetected | Add IAM deny/authorization tests |
| Checking only deployment success | Application may still be broken | Run smoke tests and canary validation |
| Not testing retries/duplicates | Multiple side effects created | Test idempotency and inject failures |
| Skipping cleanup | Resources and costs accumulate | Implement teardown and orphan cleanup |
| Coverage as the sole goal | Many tests without protecting behavior | Prioritize risks and meaningful assertions |
| Chaos tests without stop conditions | Can cause unexpected outages | Limit blast radius and configure alarms |

## 20. AWS Testing Strategy Checklist

### Design

1. Identify business flows, requirements, and risks.
2. Categorize unit, component, contract, integration, and E2E tests.
3. Identify AWS services and boundaries needing real testing.
4. Define test data, accounts, environments, and cleanup.
5. Define pass/fail criteria and quality gates.

### Implementation

1. Separate domain logic from AWS adapters.
2. Write unit tests for happy paths, boundaries, and failure paths.
3. Test IaC and IAM policies.
4. Create isolated test environments.
5. Run integration tests with real AWS resources for critical flows.
6. Run E2E tests through deployed endpoints.
7. Collect logs, metrics, traces, and test reports.

### Pre-Release

1. Check performance and quotas.
2. Check authorization and sensitive data handling.
3. Check retries, DLQs, and idempotency.
4. Check backup/restore and failover as required.
5. Run smoke tests on staging.
6. Define rollback conditions and owners.

### Post-Release

1. Run safe smoke tests.
2. Monitor canaries and CloudWatch alarms.
3. Observe error rates, latency, and business metrics.
4. Roll back if defined thresholds are breached.
5. Retain test reports and deployment traceability.
6. Clean up test data/resources per retention policy.

## 21. Conclusion

An AWS testing strategy must combine unit, component, contract, integration, and end-to-end tests. Unit tests verify logic quickly; integration tests validate service boundaries, IAM, networking, and event behavior; E2E tests prove business flows work across deployed components. Non-functional layers add evidence for performance, security, fault tolerance, and recovery.

AWS SAM CLI and CDK support the development loop, CodeBuild and CodePipeline automate CI/CD, CloudFormation manages infrastructure, and CloudWatch, X-Ray, and CloudTrail aid investigation. Test accounts, ephemeral environments, synthetic data, and cleanup reduce both risk and cost. After deployment, smoke tests, canaries, and production monitoring continue validating the release under real conditions.

A strong test strategy starts with requirements and risks, selects the right test layer for each behavior, verifies both allowed and denied cases, and keeps results reproducible. With clear quality gates, safe test data, and adequate observability in the pipeline, teams can ship changes on AWS with higher confidence.

## 22. Official References

- [AWS Well-Architected Framework – Testing](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_testing.html)
- [AWS Serverless Application Model – Testing and debugging](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli.html)
- [AWS CDK – Testing constructs](https://docs.aws.amazon.com/cdk/v2/guide/testing.html)
- [AWS CodeBuild](https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html)
- [AWS CodePipeline](https://docs.aws.amazon.com/codepipeline/latest/userguide/welcome.html)
- [AWS CloudFormation Guard](https://docs.aws.amazon.com/cfn-guard/latest/ug/what-is-guard.html)
- [CloudWatch Synthetics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Synthetics_Canaries.html)
- [AWS X-Ray](https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html)
- [AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [Distributed Load Testing on AWS](https://docs.aws.amazon.com/solutions/latest/distributed-load-testing-on-aws/solution-overview.html)
- [AWS IAM policy simulator](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html)
- [AWS CodeDeploy deployment configurations](https://docs.aws.amazon.com/codedeploy/latest/userguide/deployment-configurations.html)
