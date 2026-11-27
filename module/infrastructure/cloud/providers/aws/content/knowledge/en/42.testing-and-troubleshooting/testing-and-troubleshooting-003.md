# Limitations of Local Simulation and Testing with Real Services

## Learning Objectives

When developing applications on AWS, developers typically want to run and test quickly on their local machines before deploying. Mocks, fake services, containers, and emulators shorten feedback loops, validate business logic, and simulate some APIs. However, a local environment cannot fully replicate how AWS operates: IAM policies, resource policies, VPC routing, service quotas, retries, event delivery, eventual consistency, failover, and managed service scalability can all behave differently.

This lesson belongs to the **Testing and Troubleshooting** chapter of the CLOUD_PROVIDERS_AWS module. It helps learners distinguish what can be tested locally from what must be tested on real AWS services, choose appropriate mocks/emulators, build isolated cloud test environments, automate testing, and investigate failures that arise when moving from local to AWS.

After this lesson, learners will be able to:

- Distinguish between unit tests, component tests, integration tests, end-to-end tests, performance tests, and resilience tests.
- Choose mocks, stubs, fakes, AWS Emulator, DynamoDB Local, or AWS SAM CLI based on the objective.
- Identify limitations regarding IAM, account/Region, networking, quotas, timing, performance, and managed-service behavior.
- Design tests on real AWS using isolated accounts or stacks.
- Verify IAM roles, resource policies, KMS, VPCs, security groups, and endpoint policies.
- Test event-driven workflows involving retries, duplicates, DLQs, and eventual consistency.
- Use `cfn-lint` and CloudFormation Guard to validate Infrastructure as Code.
- Automate provisioning, testing, and cleanup of ephemeral environments in CI/CD.
- Design load tests and fault-injection experiments with guardrails.
- Investigate failures that appear only on AWS using request IDs, CloudTrail, CloudWatch, and service logs.

## 1. Why Distinguish Local Simulation from Real AWS?

A local test can confirm that code calls the right SDK method and builds the right parameters. However, that does not prove AWS will accept the request or that the service will behave as the application expects.

Examples:

- A mock SQS client returns a MessageId successfully, yet Lambda's real IAM role lacks `sqs:SendMessage` permission.
- An emulator allows the application to create an S3 bucket, yet a bucket policy, KMS key policy, or organization SCP on AWS denies the operation.
- Lambda runs fine in Docker, yet fails to read secrets when deployed because the execution role lacks `secretsmanager:GetSecretValue`.
- A local queue processes messages almost instantaneously, whereas real SQS has visibility timeouts, retries, redrive policies, and duplicate delivery.
- A single-request test runs fast on a laptop, yet the production endpoint gets throttled under thousands of concurrent requests.
- A function accepts a valid sample event, yet real events from AWS services have different structures, headers, or metadata.

The goal is not to abandon local testing. Use local tests for the questions they answer well, then validate service-, configuration-, and infrastructure-dependent properties on real AWS.

## 2. Testing Layers in an AWS System

| Testing Layer | Scope | Typical Environment | Primary Question |
|---|---|---|---|
| Static validation | Code, template, policy, and schema structure | Local/CI | Is the configuration syntactically and rule-wise valid? |
| Unit test | Individual function or class | Local | Is the business logic correct? |
| Component test | A single component with replaced dependencies | Local/container | Does the component handle inputs, outputs, and errors properly? |
| Local integration test | Multiple components via emulators or containers | Local/CI | Do components communicate per the simulated contract? |
| Cloud integration test | Interaction with real AWS services | AWS test account | Are IAM, networking, APIs, and service behavior correct? |
| End-to-end test | Entire business flow | AWS test/staging | Do events traverse all services and produce the expected result? |
| Performance/load test | Throughput, latency, concurrency, saturation | AWS test environment | Can the system sustain target load? |
| Resilience test | Failover, dependency failures, recovery | Pre-production/AWS FIS | Does the system recover within RTO/RPO? |

Each layer has different goals and costs. Static and unit tests should run frequently because they are fast. Cloud integration tests run once infrastructure is provisioned or changed. Performance and fault-injection tests require dedicated environments, schedules, and explicit guardrails.

~~~mermaid
flowchart TD
    A[Code and IaC change] --> B[Static validation]
    B --> C[Unit tests]
    C --> D[Local component / emulator tests]
    D --> E[Deploy isolated AWS test stack]
    E --> F[Cloud integration tests]
    F --> G[End-to-end tests]
    G --> H[Performance and resilience tests]
    H --> I[Promote to staging / production]
    B -->|Fail| X[Fix before deployment]
    C -->|Fail| X
    D -->|Fail| X
    F -->|Fail| X
    G -->|Fail| X
~~~

## 3. How Do Mocks, Stubs, Fakes, and Emulators Differ?

These concepts are often lumped together as "mocks," yet they serve distinct purposes.

| Type | How It Works | Example | Testing Value |
|---|---|---|---|
| Stub | Returns predefined responses | SQS client returns a fake MessageId | Verifies how code handles a given response |
| Mock | Records interactions to verify calls | Verifies code calls SendMessage with the right QueueUrl | Verifies dependencies are invoked properly |
| Fake | Lightweight implementation of part of real behavior | In-memory repository replacing a database | Verifies business flows with simple state |
| Emulator | Runs a service simulating APIs/state of a service | AWS Emulator or LocalStack | Verifies integration across supported APIs |
| Real service | Calls real AWS services | SQS, S3, DynamoDB in a test account | Verifies actual behavior and configuration |

Over-mocking can make tests verify only the current implementation. If code changes how it calls a dependency while business behavior remains correct, tests may fail unnecessarily. Conversely, overly simple mocks fail to simulate critical errors, retries, or state transitions.

Mock at external dependency boundaries and keep business logic independent of the SDK. Use cloud integration tests to verify contracts that mocks cannot prove.

## 4. Unit Testing Business Logic and Verifying SDK Calls

Consider a component that sends order events to SQS. Business logic constructs the message body; the SQS client is merely an adapter.

~~~python
import json

def publish_order(queue_client, queue_url, order):
    message = {
        "eventType": "OrderCreated",
        "orderId": order["order_id"],
        "amount": order["amount"]
    }

    return queue_client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message)
    )
~~~

A mock can verify the message and parameters:

~~~python
from unittest.mock import Mock
import json

def test_publish_order_sends_expected_message():
    queue = Mock()
    queue.send_message.return_value = {"MessageId": "test-message-1"}

    result = publish_order(
        queue,
        "https://sqs.example.test/orders",
        {"order_id": "ORD-1001", "amount": 250000}
    )

    assert result["MessageId"] == "test-message-1"
    queue.send_message.assert_called_once()

    args = queue.send_message.call_args.kwargs
    assert args["QueueUrl"] == "https://sqs.example.test/orders"

    body = json.loads(args["MessageBody"])
    assert body["eventType"] == "OrderCreated"
    assert body["orderId"] == "ORD-1001"
~~~

This test proves the code constructs the right message and calls the dependency with the right URL. It does not prove the queue exists, the role has send permissions, the KMS key policy is valid, or SQS actually accepts the message.

## 5. Stubbing the AWS SDK with Botocore Stubber

With Python/Boto3, Botocore Stubber validates API operations and expected parameters. It is more useful than a generic mock when catching mismatched field names or data types.

~~~python
import boto3
from botocore.stub import Stubber

sqs = boto3.client(
    "sqs",
    region_name="ap-southeast-1",
    aws_access_key_id="test",
    aws_secret_access_key="test"
)

queue_url = "https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders"

expected_params = {
    "QueueUrl": queue_url,
    "MessageBody": "{\"eventType\": \"OrderCreated\"}"
}

response = {
    "MD5OfMessageBody": "00000000000000000000000000000000",
    "MessageId": "message-test-001"
}

with Stubber(sqs) as stubber:
    stubber.add_response(
        "send_message",
        response,
        expected_params
    )

    result = sqs.send_message(**expected_params)

    assert result["MessageId"] == "message-test-001"
    stubber.assert_no_pending_responses()
~~~

Stubber verifies that requests match the SDK contract and returns simulated responses. It does not call SQS, nor does it check IAM, queue policies, KMS, or networking. When you need to verify those conditions, run integration tests against a real queue in a test account.

## 6. AWS Emulator: Local API Testing

AWS Emulator is an AWS API emulator published by AWS that can run on developer machines or in CI. The AWS CLI and AWS SDKs can point to the emulator endpoint; requests are handled by the emulator instead of a real AWS account. The service supports stateful resources within a session and publishes fidelity checks with each release.

AWS Emulator is suited for:

- Developing and testing API integrations locally.
- Running CI tests without an AWS account or AWS resources.
- Creating resources, reading back state, and testing certain validation errors.
- Prototyping applications using AWS APIs prior to deployment.

Limitations to keep in mind:

- The emulator does not evaluate IAM identity policies and resource-based policies the way AWS does; do not use it as security test evidence.
- The emulator does not isolate state by AWS account and Region. One emulator instance should be treated as a single unified account/Region environment.
- Fidelity varies by service and API operation. AWS states the emulator matches AWS most closely on control-plane APIs; data-plane fidelity and IaC support vary by service. Unimplemented APIs may return HTTP 501 NotImplemented. Always check the fidelity table for the release in use.
- AWS documents that behavior parity is tested against AWS in us-west-2, except global services which are tested in us-east-1. Regional differences in feature availability may not be reflected.
- Resource state is stored in memory and lost when the emulator stops.
- The emulator is not designed or tested for long-running workloads or load testing.

Because the emulator updates frequently, pin its version in CI and record the version in test reports. When upgrading versions, re-run contract test suites and check fidelity for the APIs your application uses.

## 7. LocalStack and Third-Party Emulators

LocalStack is a popular option for emulating multiple AWS services in a single local environment. It can be used to test multi-service flows such as S3 → SQS → Lambda or API Gateway → Lambda → DynamoDB.

Third-party emulators offer convenient API coverage and developer experience, yet their behavior does not necessarily match AWS across every feature. Before adopting one, check:

- Which services and API operations are supported.
- Which features are only partially emulated.
- To what extent IAM and resource policies are enforced.
- Whether events, retries, visibility timeouts, and eventual consistency behave equivalently.
- Whether VPC, PrivateLink, KMS, STS, and cross-account flows are supported.
- Whether the version and licensing fit your CI/team.

Do not infer that because an emulator supports S3 APIs it emulates all S3 behaviors, such as event notifications, lifecycle rules, replication, Object Lock, KMS, or cross-account access.

## 8. DynamoDB Local: Useful, Not a Replacement for the DynamoDB Managed Service

DynamoDB Local lets you develop applications without calling the DynamoDB web service. It can run via Docker, Maven, or a downloadable archive. The default endpoint is localhost:8000.

Docker example:

~~~bash
docker run --rm -p 8000:8000 amazon/dynamodb-local \
  -jar DynamoDBLocal.jar -sharedDb -inMemory
~~~

Calling the CLI against the local endpoint:

~~~bash
aws dynamodb list-tables \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1
~~~

DynamoDB Local is well suited for testing repositories, key conditions, query expressions, serialization, and basic read/write flows. However, its behavior differs from the managed DynamoDB service in critical ways:

- Does not support separating AWS accounts and Regions like the real service.
- Provisioned throughput settings are ignored; local cannot be used to test throttling or capacity behavior.
- Scans run sequentially; Parallel Scan and Segment/TotalSegments do not behave like the real service.
- CreateTable/UpdateTable/DeleteTable typically complete nearly instantaneously and tables may always report ACTIVE; control-plane timing is not fully simulated.
- Reads often appear strongly consistent due to local speed, even though DynamoDB Local documents read behavior as eventually consistent.
- Does not support Point-in-Time Recovery.
- Streams shard and partitioning behavior differ from the managed service.
- Performance depends on the developer workstation and cannot predict latency, throughput, or durability on AWS.

If your application depends on GSI creation states, throttling, Streams, PITR, TTL, or transaction behavior, test those parts against real DynamoDB. Use local for query logic, not as evidence of capacity or resilience.

## 9. AWS SAM CLI: Running Lambda and API Gateway Locally

AWS SAM CLI can execute Lambda functions inside Docker containers with a runtime close to the Lambda environment. SAM local is helpful for:

- Testing handlers and event parsing.
- Debugging functions in an IDE.
- Sending sample API Gateway, SQS, S3, or EventBridge events.
- Running a local API for frontend or component tests.
- Reducing deployment time in the development loop.

Basic commands:

~~~bash
sam build
sam local invoke OrderFunction --event events/order-created.json
sam local start-api
~~~

An important limitation: if the Lambda function calls the AWS SDK, requests can go to real AWS resources unless endpoints are configured to point to an emulator or fake dependency. Thus, SAM local does not automatically turn S3, SQS, DynamoDB, or Secrets Manager into local services.

Before running local tests, verify which credentials and endpoints the code uses. Never let a local test accidentally delete objects or send messages to a production account. Use dedicated profiles, explicit endpoints, and test-prefixed resources.

## 10. Local Simulation Cannot Verify IAM and Resource Policies

IAM is one of the biggest differences between local environments and real AWS.

A local test may run using developer credentials with Administrator permissions. Yet once deployed, Lambda runs with a different execution role. Issues that often appear only on AWS:

- Trust policy does not allow Lambda or ECS to assume the role.
- Identity policy is missing actions.
- Resource policy on S3, SQS, SNS, KMS, or Secrets Manager denies access.
- Explicit Deny in an SCP, permissions boundary, or session policy.
- KMS key policy does not permit the service principal or role.
- Cross-account trust is misconfigured.
- VPC endpoint policy blocks API requests.
- Role session or credential source differs from application assumptions.

To test security, deploy test workloads with the exact IAM roles, resource policies, and service integrations used in production. Use IAM Access Analyzer, CloudTrail, and error responses to verify actual permissions. Never rely on an emulator or mock to claim least privilege has been verified.

## 11. Local Simulation Cannot Fully Replicate VPCs and Networking

Network behavior depends on many resources that emulators cannot fully represent:

- VPCs, subnets, and route tables.
- Stateful security group rules.
- Stateless Network ACL rules.
- NAT Gateways, Internet Gateways, and egress paths.
- VPC endpoints and endpoint policies.
- PrivateLink, Transit Gateway, peering, and DNS resolution.
- Route 53 private hosted zones and resolver rules.
- TLS certificates, hostname verification, and proxies.
- Cross-AZ or cross-Region network behavior.

A local container reaching an endpoint does not prove a Lambda function placed in a private subnet can call that API. Tests must run from the actual network boundary: an EC2 test instance, Lambda test function, ECS task, or EKS pod inside the target VPC.

When testing connectivity, record the source subnet/security group, destination hostname, resolved IP, port, route, and endpoint policy. Inspect each hop rather than merely observing a generic application timeout.

## 12. API Contracts and Schema Compatibility

Contract tests verify that both sides of an integration agree on inputs, outputs, and error behavior. They remain valuable even before real AWS resources exist.

For example, an `OrderCreated` event must include schema version, order ID, amount, and event timestamp. Consumers must define behavior when fields are missing or a new version arrives.

A good contract defines:

- Required and optional fields.
- Data types, formats, enums, and bounds.
- Schema version and compatibility policy.
- Idempotency key or event ID.
- Error responses and retryability.
- Content type and encoding.
- Event source and metadata.
- PII/secret fields that must not be logged.

Contract tests can run locally. However, cloud integration tests are still needed to confirm that real events emitted by AWS services match the shape and metadata expected by consumers.

## 13. Validating Infrastructure as Code Before Deployment

CloudFormation templates, SAM templates, or IaC configurations can be statically checked before provisioning resources.

Two helpful tools:

- `cfn-lint` checks template structure, resource properties, values, references, and certain best-practice rules against the CloudFormation resource schema.
- CloudFormation Guard checks JSON/YAML against policy-as-code rules, such as requiring bucket encryption or forbidding security groups from opening SSH to the Internet.

Examples:

~~~bash
cfn-lint --regions ap-southeast-1 template.yaml
~~~

~~~bash
cfn-guard validate \
  --rules security-rules.guard \
  --data template.yaml \
  --type CFNTemplate
~~~

`cfn-lint` does not prove a CloudFormation stack will succeed in a specific account. Nor does Guard enforce controls server-side on its own; to block changes at provisioning time, look at CloudFormation Hooks or appropriate governance controls.

Static validation does not replace deployment tests. Resource quotas, service-linked roles, account settings, Region availability, IAM permissions, and dependency states are only fully verified against AWS.

## 14. When Must You Test with Real AWS Services?

Test on real AWS when the outcome depends on:

| Property to Verify | Why Real AWS Is Required |
|---|---|
| IAM and resource policies | Requires evaluation by the AWS authorization engine |
| KMS | Requires real key policies, grants, and service integrations |
| VPC and PrivateLink | Requires real routes, SGs, NACLs, DNS, and endpoints |
| Service quotas/throttling | Quotas and throttling are enforced per account/Region |
| Managed service timing | Provisioning, failover, retries, and state transitions have real timing |
| Event delivery | Requires verifying integrations, retries, duplicates, and DLQs |
| Performance | Requires real compute, storage, networking, and capacity |
| Regional feature availability | Features and quotas can vary by Region |
| Backup/restore | Requires testing snapshots, restores, and data durability workflows |
| Failover/resilience | Requires simulating resource failures and observing real recovery |

You do not need to deploy a full production stack for every commit. Cloud tests can be split into small smoke tests after each deploy, integration suites on a schedule or pre-release, and performance/resilience tests on a separate plan.

## 15. Designing AWS Test Accounts and Isolated Environments

Test environments need clear boundaries so tests never touch production data or resources.

Common options:

- Separate AWS account per developer.
- Shared team account where each test uses unique stack names and resource prefixes.
- Separate AWS Organizations accounts for dev/test/staging.
- Ephemeral accounts created per pipeline or landing zone when supported by the organization.

Principles:

1. Separate production accounts from dev/test.
2. Use IAM roles scoped by workload and environment.
3. Use resource tags to identify owner, environment, build ID, and expiry.
4. Never copy production PII or secrets to test without approval and masking.
5. Use dedicated S3 buckets, queues, topics, tables, and secrets for testing.
6. Configure appropriate budget alerts and service quotas.
7. Use IaC for repeatable environment creation and teardown.
8. Avoid shared resource names that collide across parallel test runs.

If a team shares an account, generate unique suffixes from pipeline run IDs and delete only the matching stack after testing. Never use wildcard cleanup that might delete someone else's resources.

## 16. Test Data: Synthetic and Anonymized Data

Test data directly impacts result reliability and security risk.

Data types to consider:

- Synthetic data generated from expected schemas and distributions.
- Masked data with identifiers removed or transformed.
- Small fixtures for unit/component tests.
- Approved representative datasets for performance tests.
- Edge-case data such as nulls, Unicode, large payloads, duplicate IDs, out-of-order events, and malformed JSON.

A strong test dataset covers happy paths, boundaries, invalid inputs, and retries. Synthetic data should mirror realistic string lengths, cardinality, skew, sizes, and distributions; an overly uniform dataset can hide hot partitions or query bottlenecks.

Never write real data into test reports, CloudWatch logs, or CI artifacts without proper access controls and retention.

## 17. Testing Service Integrations Layer by Layer

An integration test should verify resources, permissions, and data flow together.

Example order flow:

1. API Gateway receives the request.
2. Lambda validates and writes the order to DynamoDB.
3. Lambda sends an `OrderCreated` event to EventBridge.
4. A rule routes the event to SQS.
5. Consumer Lambda processes it and writes fulfillment state.
6. CloudWatch records logs and metrics.

Tests calling only the Lambda handler directly do not verify API Gateway mappings, EventBridge rules, queue policies, DLQs, or Lambda event source mappings.

Include at least one end-to-end test running on real AWS that creates a test order, waits for downstream state, and verifies records/events. Use a unique order ID to avoid collisions and maintain a dedicated cleanup policy.

~~~mermaid
sequenceDiagram
    participant T as Test runner
    participant A as API Gateway
    participant L as Order Lambda
    participant D as DynamoDB
    participant E as EventBridge
    participant Q as SQS
    participant C as Consumer Lambda
    T->>A: POST test order
    A->>L: Invoke handler
    L->>D: PutItem
    L->>E: PutEvents
    E->>Q: Deliver event
    Q->>C: Event source mapping
    C->>D: Update fulfillment state
    T->>D: Poll for expected state
    D-->>T: Fulfillment status
~~~

## 18. Testing Event-Driven Behavior: Retries, Duplicates, and DLQs

Event-driven systems are typically asynchronous. An API returning HTTP 202 or a successful Lambda invocation does not prove downstream processing completed.

Scenarios to test:

- Event arrives once and consumer succeeds.
- Event is delivered more than once.
- Consumer succeeds in business work but crashes before acking/deleting the message.
- Handler experiences a transient error and is retried.
- Message exceeds `maxReceiveCount` and moves to the DLQ.
- Message visibility timeout expires while still processing.
- Events arrive out of order.
- Event is missing a field or carries a new schema version.
- Downstream service throttles or times out.
- EventBridge rule/target is disabled or lacks permissions.

Consumers should be idempotent. Store event IDs or business keys alongside processing state inside a transaction/conditional write so duplicates do not cause duplicate side effects.

For SQS, test visibility timeout, message retention, redrive policy, and DLQ behavior using a real queue. For Lambda, verify retry semantics by event source type; asynchronous invocation behaves differently from SQS/Kinesis event source mappings.

## 19. Eventual Consistency and Timing in Cloud Tests

Some AWS operations do not complete immediately. For example:

- CloudFormation stacks transition through multiple states.
- Lambda versions/aliases or event source mappings take time to update.
- IAM policy propagation can have latency.
- S3 event notifications and EventBridge deliveries are asynchronous.
- DynamoDB GSIs or stream resources have creating/deleting states.
- ECS tasks, EKS workloads, or EC2 instances take time to boot.
- DNS caches and service discovery may hold stale entries.

Tests should not rely on long fixed sleeps for every scenario. Use polling with timeouts and backoff:

~~~python
import time

def wait_until(check, timeout_seconds=120, interval_seconds=2):
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(interval_seconds)

    raise TimeoutError("Condition was not met before timeout")
~~~

The `check` function should execute a read-only operation and return once the desired condition is met. Timeouts should reflect SLOs or expected provisioning durations. On timeout, record the last observed state, request ID, and resource ARN for investigation.

## 20. Testing S3, DynamoDB, and RDS

| Service | What Local Tests Can Verify | What Cloud Tests Must Verify |
|---|---|---|
| S3 | SDK parameters, object serialization, basic put/get via emulator | Bucket policies, KMS, versioning, lifecycle, event notifications, replication, Object Lock, access points |
| DynamoDB | Key design, query expressions, marshalling, basic CRUD with local DB | Throughput, throttling, GSI/LSI timing, Streams, TTL, PITR, transactions, and hot partitions |
| RDS/Aurora | SQL logic with an engine-compatible database container | IAM DB auth, subnet groups, SGs, failover, parameter groups, backup/restore, and managed maintenance |

A local database container can test SQL and repository logic, yet it does not represent RDS failover, Multi-AZ, storage performance, or backup restoration.

For S3, test both bucket policies and KMS key policies when objects are encrypted with customer managed keys. For DynamoDB, test conditional writes, transaction conflicts, throttling, and hot partitions in a test account under representative traffic.

## 21. Testing Lambda, API Gateway, and Step Functions

Local Lambda testing is useful for handler logic and event parsing. Cloud tests need to verify:

- Execution role and trust relationship.
- Timeout, memory, ephemeral storage, and concurrency.
- Environment variables and Secrets Manager integration.
- VPC attachment, subnet IP capacity, and NAT/endpoint paths.
- Event source mappings, batch size, and partial batch responses.
- Async retries, destinations, or DLQs.
- API Gateway authorizers, throttling, mapping templates, and CORS.
- Step Functions state transitions, retry/catch, timeouts, and service integrations.

For Step Functions, testing a state machine locally or with mocked service integrations can verify branching logic. End-to-end tests on AWS are needed to verify IAM roles, service integrations, payload paths, and real execution statuses.

Never use the same production Lambda function to test events that cause side effects. Create a test function/alias or separate stack and use dedicated test data.

## 22. Testing IAM and Security on AWS

Security tests must execute under real principals and resource policies. A test suite should include:

- Positive tests: valid principals can perform required actions.
- Negative tests: unauthorized principals are denied.
- Resource scope tests: roles can only access intended buckets/tables/queues/secrets.
- Cross-account tests: trusts and resource policies permit the right accounts/roles.
- KMS tests: encryption/decryption is properly allowed or denied.
- VPC endpoint tests: requests traverse the proper endpoint and policy.
- Audit tests: CloudTrail records monitored API calls.

Negative test example: an application role has read access to the `test/orders/*` prefix but must not read `test/payroll/*`. Call both real resources in the test account to verify allow and deny.

Do not use Administrator privileges in integration tests, as doing so hides least-privilege errors. Tests should assume the exact application role via STS or run the workload under its actual execution role.

## 23. Testing Quotas, Throttling, and Retries

Service quotas are part of the operational contract. Local emulators cannot predict account/Region quotas.

Testing should consider:

- API request rate and burst quotas.
- Lambda concurrency and reserved concurrency.
- SQS throughput and message size.
- Kinesis shard capacity or on-demand capacity.
- DynamoDB read/write capacity and hot partitions.
- API Gateway throttling.
- SageMaker endpoint invocation concurrency.
- RDS connection limits and connection pools.
- Bedrock model quotas/token throughput.

Do not intentionally induce throttling in production to test it. Use a test account, appropriate quotas, and bounded workloads. When throttled, clients should use exponential backoff with jitter and cap total retries. Unbounded retries can worsen overload incidents.

## 24. Performance Testing and Load Testing

Performance tests measure processing times and resource usage at a defined load level. Load tests increase load to see how the system performs under expected peak conditions. Stress tests push beyond target load to find breaking points. Soak tests sustain load over long periods to detect leaks, backlogs, or gradual degradation.

Metrics to monitor:

| Metric | Meaning |
|---|---|
| p50/p95/p99 latency | Median and tail latency |
| Throughput | Requests/transactions completed per second |
| Error rate | Percentage of failed requests |
| Throttles/rejections | Requests rejected due to quota/capacity |
| Queue depth/age | Backlog and wait time |
| CPU/memory/network | Compute resources |
| Database connections/latency | Database load and responsiveness |
| Cost per request/job | Workload unit cost |

Load tests must use near-realistic payloads and data distributions. Run from network locations matching production clients. If the production application runs inside a VPC, test from the corresponding VPC to measure the real network path.

Do not use local emulators as AWS performance evidence. CPU, disk, network, and scaling on a developer workstation do not represent managed services.

## 25. Resilience Testing and Chaos Engineering with AWS FIS

AWS Fault Injection Service (AWS FIS) lets you run fault-injection experiments on real AWS resources. It can be used to test applications during service-supported disruptions such as instance termination, CPU/memory stress, API throttling, or failover.

An experiment template includes:

- **Actions:** actions that inject faults or alter state.
- **Targets:** resources impacted, selectable by tags or conditions.
- **Stop conditions:** CloudWatch alarms that automatically halt the experiment when thresholds are breached.
- **Role:** IAM role allowing FIS to execute actions on resources.
- **Experiment report:** status, executed actions, and outcomes.

AWS FIS performs real actions on real resources. Start in test/pre-production, define steady state, formulate a hypothesis, choose small targets, and configure stop conditions before running. Never run fault injection in production just because you created an experiment template.

Example hypothesis:

"If one EC2 instance in the Auto Scaling group is terminated, the error rate does not exceed 1% and the service recovers within 3 minutes."

Measure baseline metrics before the experiment, execute the action on a single target, monitor CloudWatch metrics, and verify the system meets RTO. If a stop alarm triggers, halt the experiment and remediate before retrying.

## 26. Testing Backup, Restore, and Disaster Recovery

Having successful snapshots or backups does not guarantee the application can recover on time.

A restore test must verify:

1. Backups/snapshots are created on schedule.
2. Retention and encryption keys remain available.
3. Restore permissions exist in the target account/Region.
4. New resources can be provisioned from backups.
5. Applications can connect to restored resources.
6. Data and consistency are verified.
7. DNS/endpoints/secrets/configs are switched to the restored resources.
8. Actual RTO and RPO are measured.
9. Runbooks can be executed by another on-call engineer.

For RDS, test snapshot restores and application connectivity. For DynamoDB, test PITR or on-demand backup restores. For S3, test versioning, replication, and object recovery. For EBS/EC2, test snapshot restores and booting. For multi-Region architectures, verify permissions, KMS, networking, and service quotas in the target Region as well.

## 27. Automating Cloud Tests with Infrastructure as Code

Cloud test environments should be created from versioned templates rather than manual clicks. You can use CloudFormation, AWS SAM, AWS CDK, or Terraform to:

- Create resources and IAM roles.
- Configure event sources and permissions.
- Provision test data fixtures.
- Export stack outputs for test runners.
- Attach owner/build/expiry tags.
- Delete resources when tests finish.

A typical pipeline:

~~~mermaid
flowchart TD
    A[Commit / Pull request] --> B[Lint code and IaC]
    B --> C[Unit and component tests]
    C --> D[Local emulator tests]
    D --> E[Deploy ephemeral AWS stack]
    E --> F[Cloud integration tests]
    F --> G[End-to-end smoke tests]
    G --> H[Publish test report]
    H --> I[Delete ephemeral stack]
    F -->|Failure| J[Collect logs and resource state]
    G -->|Failure| J
    J --> I
~~~

If a stack fails midway through deployment, cleanup must also handle partially created resources. Preserve logs and CloudFormation events before deleting the stack so investigative evidence is not lost.

## 28. Example Cloud Integration Test with AWS SAM

A pipeline can build and deploy a dedicated stack for each run:

~~~bash
sam build

sam deploy \
  --stack-name orders-it-build-1042 \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Environment=Integration
~~~

After deploying, fetch API endpoints or resource ARNs from CloudFormation stack outputs and run integration tests:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-it-build-1042 \
  --query "Stacks[0].Outputs"
~~~

The test runner can call the API, submit a test order, and poll downstream state. After saving the test report, delete the exact ephemeral stack:

~~~bash
sam delete --stack-name orders-it-build-1042
~~~

Stack names should contain a build ID or UUID to prevent collisions. Only clean up stacks created by the pipeline, and verify account/Region before deletion. If resources must be kept for investigation, use TTL tags and controlled cleanup workflows.

## 29. Managing Cost and Cleanup of Test Environments

Cloud tests use real resources and therefore incur charges. A forgotten test run can leave behind NAT Gateways, RDS instances, OpenSearch domains, SageMaker endpoints, EBS volumes, or log groups.

Controls:

- Set budgets and billing alarms on test accounts.
- Tag resources with `Owner`, `Environment`, `BuildId`, `CreatedAt`, and `ExpiresAt`.
- Enforce timeouts/TTLs on test runs.
- Delete endpoints, clusters, databases, and NAT resources after tests.
- Restrict instance sizes and parallel test concurrency.
- Use schedules to stop stoppable resources.
- Retain logs/test artifacts only as long as needed.
- Run scheduled cleanup jobs for stacks orphaned after pipeline failures.
- Inspect resources not managed by CloudFormation before manual deletion.

Some resources take time to delete or continue billing during deletion. Track deletion status rather than assuming a delete command means the resource is already gone.

## 30. Investigating Failures That Appear Only on AWS

When local tests pass but cloud tests fail, gather evidence in order:

1. **Identity:** principal ARN, assumed role session, credential source.
2. **Request:** API action, resource ARN, request ID, Region, and timestamp.
3. **Authorization:** identity policy, resource policy, SCP, permission boundary, KMS key policy.
4. **Network:** VPC, subnet, routes, SGs, NACLs, endpoints, and DNS.
5. **Service state:** resource status, deployment events, quotas, throttling, and service health.
6. **Data:** event payload, schema version, idempotency key, and encryption.
7. **Timing:** timeouts, retries, visibility timeout, event delivery delay, and eventual consistency.
8. **Observability:** CloudWatch logs/metrics, CloudTrail events, X-Ray traces, and service-specific logs.

Evidence sources:

| Source | Used For |
|---|---|
| CloudTrail | Identifying who called an AWS API, action, resource, and error |
| CloudWatch Logs | Viewing application logs, Lambda logs, and service logs |
| CloudWatch Metrics | Identifying throttling, saturation, queues, and health |
| X-Ray / OpenTelemetry | Tracing requests across multiple services |
| CloudFormation Events | Finding resource provisioning failures |
| Service-specific events | Checking ECS, RDS, Lambda, SageMaker, or other resource states |
| AWS Health Dashboard | Checking service events affecting the account/Region |

Always record request IDs, stack IDs, resource ARNs, and UTC timestamps. Never include secrets, access keys, or sensitive payloads in tickets/logs when sharing errors.

## 31. Tool and Environment Selection Matrix

| Question to Answer | Suitable Tool/Environment | Need Further Testing on Real AWS? |
|---|---|---|
| Is the pricing function correct? | Unit test | No, if independent of AWS |
| Is the SDK called with the right parameters? | Mock or Stubber | Yes, if verifying the service accepts the request |
| Does Lambda parse sample events properly? | SAM local | Yes, to verify real event integrations |
| Is DynamoDB query logic correct? | DynamoDB Local or emulator | Yes, for throughput, Streams, PITR, GSI timing |
| Do services exchange messages over APIs? | AWS Emulator/LocalStack | Yes, to verify IAM, networking, and service behavior |
| Does the IAM role have the right permissions? | AWS test account with real role | Yes |
| Do PrivateLink/VPC routes work? | Workload inside test VPC | Yes |
| Can the stack be created in account/Region? | Deploy CloudFormation/SAM/CDK | Yes |
| Does the system handle peak load? | AWS load test environment | Yes |
| Does the app recover after a fault? | AWS FIS pre-production experiment | Yes |

A strong test suite combines multiple tools. Emulators do not compete with AWS integration tests; each validates a different layer.

## 32. Case Study: Testing an Order Processing System

An e-commerce application uses API Gateway, Lambda, DynamoDB, EventBridge, and SQS. The team wants to verify the `OrderCreated` flow prior to release.

**Local layer:**

- Unit tests check validation, pricing, and event construction.
- Stubber verifies the SDK calls `PutItem`/`PutEvents` with the right parameters.
- SAM local runs handlers with API Gateway event and SQS event fixtures.
- AWS Emulator or LocalStack tests API flows across supported services.

**Cloud integration layer:**

- Provision an ephemeral stack with real API Gateway, Lambda, DynamoDB, EventBridge, and SQS.
- Use least-privilege execution roles.
- Submit a test order through API Gateway.
- Poll DynamoDB until fulfillment state updates.
- Verify the event enters the right queue and the consumer processes it properly.
- Resend the same event ID to test idempotency.
- Send a malformed event to verify error handling and DLQ behavior.
- Inspect CloudTrail, Lambda logs, and CloudWatch metrics.

**Performance and resilience layer:**

- Ramp up request rate in the test account and monitor p95/p99, throttling, Lambda concurrency, and queue age.
- Temporarily reduce consumer capacity or apply appropriate fault injection to verify backlog handling and recovery.
- Verify stop conditions and runbooks before every FIS experiment.

After testing, archive reports, CloudFormation events, log links, and metrics. Clean up only the stack matching the build ID; do not delete shared team data or resources.

## 33. Lab: Comparing Local and Cloud Tests

Perform with synthetic project data or in an approved AWS test account.

### Step 1: Write Unit Tests

Create an order-processing function and test valid cases, missing fields, negative amounts, and duplicate event IDs. Run tests without AWS credentials.

### Step 2: Verify SDK Calls with Stubber

Stub an SQS or DynamoDB operation. Verify the operation name, input parameters, and response/error paths.

### Step 3: Run SAM Local

Use sample JSON events to invoke the Lambda handler. Explicitly identify whether SDK calls point to real AWS or an emulator.

### Step 4: Run an Emulator

Create local resources and execute an API flow supported by the emulator. Record the emulator version, service/API operations, and fidelity limitations.

### Step 5: Deploy a Test Stack to AWS

Use IaC to create resources tagged with `Environment=Integration` and a unique `BuildId`. Confirm the CLI points to the right account and Region.

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

### Step 6: Run Cloud Integration Tests

Send test events, verify data, and check downstream state. Verify roles and resource policies using the workload's actual identity.

### Step 7: Record Differences

Compare responses, timing, errors, retries, permissions, and state transitions between local and AWS. Classify each difference as an emulator gap, configuration issue, IAM issue, network issue, or service behavior.

### Step 8: Cleanup

Confirm the stack name and account/Region, then delete the ephemeral stack. Check for leftover resources and retain necessary test reports/logs.

## 34. Production Readiness Checklist for Testing Strategy

### Coverage

- [ ] Unit tests exist for business logic and edge cases.
- [ ] Component tests exist for adapters and serialization.
- [ ] Local integration tests cover simulatable flows.
- [ ] Cloud integration tests cover IAM, networking, and managed-service behavior.
- [ ] End-to-end tests cover critical business workflows.
- [ ] Performance tests align with SLOs and peak traffic.
- [ ] Resilience/restore tests align with RTO/RPO.

### Local Simulation

- [ ] Emulator versions are pinned in CI.
- [ ] Required API/feature fidelity has been verified.
- [ ] Emulators are never used as security or performance proof.
- [ ] AWS SAM local cannot accidentally call production resources.
- [ ] DynamoDB Local limitations are accounted for in test design.
- [ ] Credentials and endpoints are clearly isolated.

### AWS Test Environment

- [ ] Test accounts/environments are separated from production.
- [ ] Roles and resource policies mirror production for the permissions under test.
- [ ] Network paths match real workloads.
- [ ] Test data is synthetic or masked.
- [ ] Service quotas and Region availability have been verified.
- [ ] Resources carry owner/build/expiry tags.
- [ ] Budgets, alarms, and cleanup automation are active.

### CI/CD and Operations

- [ ] `cfn-lint`/Guard run before deployment.
- [ ] Integration tests run only after the stack reaches a ready state.
- [ ] Test reports include request IDs, resource ARNs, and timestamps.
- [ ] Failure logs are collected before cleanup.
- [ ] Retries and polling use timeouts/backoff.
- [ ] Fault injection has hypotheses, targets, and stop conditions.
- [ ] Restore tests validate actual RTO/RPO.
- [ ] A process exists to handle orphaned test stacks.

## 35. Self-Check Exercises

### Question 1

How do unit tests and integration tests differ?

**Answer:** Unit tests check an isolated unit of code; integration tests check multiple components interacting across dependencies or services.

### Question 2

Does a passing mock test prove the real AWS API call will succeed?

**Answer:** No. Mocks only return predefined behavior; they do not verify the real service, IAM, resource policies, networking, or quotas.

### Question 3

Does AWS Emulator evaluate IAM identity policies and resource-based policies the same way AWS does?

**Answer:** No. Never use AWS Emulator as security testing evidence.

### Question 4

Why might an emulator fail to catch VPC errors?

**Answer:** Emulators do not fully replicate real VPC route tables, security groups, NACLs, endpoint policies, PrivateLink, and DNS.

### Question 5

Does AWS SAM local automatically emulate every AWS service called by Lambda?

**Answer:** No. SDK calls can hit real AWS resources unless explicitly pointed to an emulator or replacement dependency.

### Question 6

Can DynamoDB Local be used to benchmark provisioned throughput?

**Answer:** No. Provisioned throughput settings are ignored; performance depends on the local machine.

### Question 7

Why can local DynamoDB hide eventual consistency or GSI timing issues?

**Answer:** Local operations usually complete very quickly, tables may always appear ACTIVE, and reads often appear strongly consistent.

### Question 8

Which credentials should cloud integration tests use?

**Answer:** They should use a dedicated workload/test IAM role with least-privilege permissions mirroring production.

### Question 9

Why test both positive and negative authorization?

**Answer:** Positive tests prove required permissions work; negative tests prove the role cannot access out-of-scope resources.

### Question 10

How should an SQS consumer handle duplicate messages?

**Answer:** Design for idempotency using event IDs or business keys and persist processing state so duplicates do not cause duplicate side effects.

### Question 11

Why avoid long fixed sleeps in integration tests?

**Answer:** They slow down tests and do not guarantee resources are ready; use polling with timeouts/backoff and check real state.

### Question 12

What does `cfn-lint` check?

**Answer:** It checks template structure, resource properties, values, references, and rules against the CloudFormation schema.

### Question 13

Does CloudFormation Guard replace `cfn-lint`?

**Answer:** No. Guard evaluates policy-as-code against JSON/YAML data; `cfn-lint` validates template schemas and structure.

### Question 14

Does the CloudFormation Guard CLI automatically block every deployment?

**Answer:** No. Guard CLI is a pipeline validation step; CloudFormation Hooks or server-side governance controls are needed to block provisioning.

### Question 15

Why must performance tests run on real AWS?

**Answer:** You need real compute, networking, storage, quotas, and managed scaling; emulators/local hardware do not represent production capacity.

### Question 16

Does AWS FIS act on simulated resources?

**Answer:** AWS FIS executes actions on real AWS resources; it requires targets, IAM permissions, hypotheses, and stop conditions.

### Question 17

What evidence should be preserved if a test stack fails mid-deployment?

**Answer:** CloudFormation events, request IDs, resource statuses, CloudWatch logs/metrics, and deployment outputs before cleanup.

### Question 18

Why does every parallel test run need unique resource names?

**Answer:** To prevent collisions, data overwrites, or accidentally cleaning up another run's resources.

### Question 19

A local test passes, yet the AWS test fails with 403. What should you check first?

**Answer:** The actual principal, identity policy, resource policy, SCP, permissions boundary, KMS policy, and endpoint policy.

### Question 20

Is having successful backups enough to prove disaster recovery?

**Answer:** No. You must restore, verify data, confirm application connectivity, and measure actual RTO/RPO.

## 36. Official References

- [How to test serverless functions and applications](https://docs.aws.amazon.com/lambda/latest/dg/testing-guide.html)
- [Local testing with AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/using-sam-cli-local-testing.html)
- [AWS Emulator documentation](https://docs.aws.amazon.com/emulator/)
- [What is AWS Emulator and its limitations](https://docs.aws.amazon.com/emulator/latest/userguide/what-is-service.html)
- [Fidelity in AWS Emulator](https://docs.aws.amazon.com/emulator/latest/userguide/fidelity.html)
- [DynamoDB Local setup](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html)
- [DynamoDB Local usage notes and differences](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.UsageNotes.html)
- [Validate CloudFormation templates with cfn-lint](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cfn-lint.html)
- [Validate templates with CloudFormation Guard](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-guard.html)
- [Testing CloudFormation Guard rules](https://docs.aws.amazon.com/cfn-guard/latest/ug/testing-rules.html)
- [CloudFormation best practices](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/best-practices.html)
- [What is AWS Fault Injection Service](https://docs.aws.amazon.com/fis/latest/userguide/what-is.html)
- [Planning AWS FIS experiments](https://docs.aws.amazon.com/fis/latest/userguide/getting-started-planning.html)
- [Test resiliency using chaos engineering](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_testing_resiliency_failure_injection_resiliency.html)
- [Best practices for testing serverless applications](https://docs.aws.amazon.com/prescriptive-guidance/latest/serverless-application-testing/best-practices.html)
- [Challenges when testing serverless applications](https://docs.aws.amazon.com/prescriptive-guidance/latest/serverless-application-testing/challenges.html)
- [Pre-deployment activities and integration testing](https://docs.aws.amazon.com/prescriptive-guidance/latest/resilience-lifecycle-framework/pre-deployment.html)

Service features, emulator fidelity, quotas and regional availability change over time. Pin tool versions in CI, inspect the official compatibility/fidelity documentation for the APIs under test, and keep at least one test stage against the actual AWS services used by the application.
