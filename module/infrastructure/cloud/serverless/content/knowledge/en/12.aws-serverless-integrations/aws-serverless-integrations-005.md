# Scheduling Functions with EventBridge Scheduler

AWS Lambda is typically triggered by HTTP requests, messages, or events from AWS services. However, many business workloads need to run on a schedule: generating a report every morning, closing expired sessions, sending reminders on a specific date, running month-end reconciliation, or starting a workflow after a few hours. **Amazon EventBridge Scheduler** provides a managed scheduling service to invoke Lambda and many other AWS targets on a one-time or recurring schedule.

Scheduler decouples execution timing from business code. The function focuses purely on handling the event; Scheduler is responsible for storing the schedule, determining when to trigger, sending the request to the target, and applying a retry policy when the request cannot be delivered. The design must still account for late or duplicate event delivery, IAM permissions, invocation limits, time zones, function runtime duration, and error observability.

In a Java serverless application, the handler should process structured events, validate required inputs, and perform work idempotently. Do not use background threads or sleep loops inside Lambda to wait for execution time. Once an invocation finishes, the execution environment is not guaranteed to remain alive for future work.

## 1. EventBridge Scheduler in Serverless Architecture

EventBridge Scheduler is a standalone scheduling service within the Amazon EventBridge ecosystem. You create a schedule, specify the time expression, time zone, flexible time window, and target. When the scheduled time arrives, Scheduler invokes the target API using the specified execution role.

A simple flow:

~~~mermaid
flowchart LR
    A["EventBridge Scheduler"] -->|"At scheduled time"| B["Assume execution role"]
    B -->|"Invoke API"| C["AWS Lambda function"]
    C --> D["Business processing"]
    D --> E[("DynamoDB / S3 / database")]
    A -.->|"Target delivery error"| F["Retry policy"]
    F -.-> G["Scheduler DLQ"]
    C -.->|"Function execution error"| H["Lambda async retry / destination"]
~~~

Core components:

| Component | Responsibility |
|---|---|
| Schedule | Stores time expression, time zone, state, and target delivery configuration |
| Schedule group | Groups schedules for organization, tagging, and management |
| Schedule expression | Describes a one-time or recurring schedule |
| Flexible time window | Allows spreading target delivery across a time interval |
| Target | Resource or API invoked, such as Lambda, SQS, or Step Functions |
| Execution role | IAM role Scheduler assumes to invoke the target |
| Retry policy | Limits retry attempts and maximum age of target delivery |
| Dead-letter queue (DLQ) | Receives information/events when Scheduler fails to deliver to the target per policy |
| Action after completion | Specifies whether to delete a one-time schedule after completion or retain it |

Scheduler is the schedule management service; Lambda remains where business code runs. One schedule can trigger the same function with different payloads, or multiple schedules can invoke specialized functions.

## 2. EventBridge Scheduler vs. Scheduled Rules

EventBridge has traditional scheduled rules, but Scheduler is the more specialized option for new scheduling needs. A scheduled rule belongs to EventBridge rules and emits events onto an event bus or target using rule mechanics. EventBridge Scheduler directly manages schedules and supports one-time schedules, time zones, flexible time windows, retry policies, and DLQs at the schedule level.

| Need | Suitable choice |
|---|---|
| Run a function once at a specific time | EventBridge Scheduler |
| Run on a cron schedule in a local time zone | EventBridge Scheduler |
| Run on a rate interval | EventBridge Scheduler |
| Schedule at large scale with per-schedule retry/DLQ policies | EventBridge Scheduler |
| Filter events by content and route to multiple targets | EventBridge rule on an event bus |
| Coordinate business events across multiple consumers | EventBridge event bus and rules |

Do not confuse scheduling with event routing. Scheduler answers “when should the target be invoked?”; EventBridge event buses and rules answer “which events matching which conditions should be routed where?”. The two mechanisms can be combined: Scheduler can trigger a target that emits an event, and then the event bus routes that event to consumers.

## 3. Three Types of Schedule Expressions

Scheduler supports one-time schedules (`at`), interval schedules (`rate`), and cron schedules (`cron`).

### One-Time Schedules: at

Use **at** when a task only needs to run at a single point in time:

~~~text
at(2026-12-01T09:00:00)
~~~

You can specify the time zone using the `ScheduleExpressionTimezone` property, such as **Asia/Ho_Chi_Minh**. The time in the expression is then interpreted in the configured time zone. One-time schedules fit reminders, expiring due orders, expiring download links, or starting a pre-scheduled job.

An `at` schedule is not a millisecond-precise timer. When the flexible time window is off, Scheduler typically delivers to the target within 60 seconds of the scheduled time; if a flexible window is enabled, delivery occurs within that window. When second- or millisecond-exact deadlines are required, design a dedicated mechanism and verify actual service SLAs.

### Interval Schedules: rate

Use **rate** for recurring intervals:

~~~text
rate(5 minutes)
rate(1 hour)
rate(1 day)
~~~

Rate expresses the interval between runs, suited for periodic tasks not tied to a clock time on a calendar. If you need to run at 09:00 every day in local time, `cron` usually expresses the intent better than `rate(1 day)`, because `rate` is a duration interval rather than a calendar time.

### Cron Schedules

Cron fits schedules by minute, hour, day of month, month, day of week, and year. Scheduler's cron syntax has six fields:

~~~text
cron(minutes hours day-of-month month day-of-week year)
~~~

Examples:

| Requirement | Expression |
|---|---|
| Every day at 09:00 | cron(0 9 * * ? *) |
| Monday through Friday at 09:00 | cron(0 9 ? * MON-FRI *) |
| First day of each month at 08:00 | cron(0 8 1 * ? *) |
| Every Sunday at 23:30 | cron(30 23 ? * SUN *) |
| Every hour at minute 15 | cron(15 * * * ? *) |

In AWS cron expressions, the question mark (`?`) is used in the day-of-month or day-of-week field to indicate no specific value for that field. Normally, only one of those two fields is specified. Verify expressions against Scheduler syntax documentation and test in a non-production environment before enabling real schedules.

## 4. Time Zones and Execution Timing

If `ScheduleExpressionTimezone` is omitted, the schedule is interpreted in UTC. When business logic relies on local time, declare an IANA time zone name, such as:

~~~text
ScheduleExpression: cron(0 9 * * ? *)
ScheduleExpressionTimezone: Asia/Ho_Chi_Minh
~~~

Use named time zones instead of manually adding or subtracting hour offsets in code. This keeps the schedule aligned with business intent and avoids manually editing cron expressions when time zone rules change.

For regions with daylight saving time (DST), verify schedule behavior across clock transitions. Under Scheduler rules, a cron schedule falling in a non-existent local hour during a spring-forward transition is skipped; during a fall-back transition when an hour occurs twice, a schedule in the repeated hour runs only once. If business logic requires running once per calendar day, clarify expectations and test DST transitions. Vietnam does not currently observe DST, but multi-region applications still need to account for this.

Points to distinguish:

- **UTC timestamp:** absolute point in time for storage and reconciliation.
- **Timezone:** rule for interpreting the schedule's calendar time.
- **Scheduled time:** the time the schedule was intended to trigger.
- **Actual delivery time:** the time Scheduler actually sent the request to the target.

Do not use the moment the function starts running as the business period if you need the intended run window. Pass `scheduledTime` in the payload so the job processes the right period even if the target is invoked late.

## 5. Flexible Time Windows and Precision

A flexible time window lets Scheduler distribute target delivery across a time window instead of clustering all schedules at the exact same instant. This reduces bursts when many schedules share the same trigger time and eases pressure on targets.

Two modes:

- **OFF:** does not ask Scheduler to spread delivery across a flexible window. Scheduler still operates with minute-level delivery precision, not hard real-time.
- **FLEXIBLE:** specifies `MaximumWindowInMinutes` so Scheduler picks a delivery time within the configured window.

For example, an internal report can run within a 15-minute window after 09:00 with no business impact. A task settling a due payment or sending a customer-committed notification may need the flexible window turned off, while still accounting for actual service precision and latency.

Do not enable a flexible window just to “avoid clock errors.” It is a trade-off between load spreading and execution timing. Define the maximum latency your business tolerates before configuring it.

## 6. Schedule Groups and Managing Multiple Schedules

A schedule group is a namespace for organizing schedules. You can create groups by application, environment, or business domain, for example:

~~~text
orders-prod
billing-prod
reporting-staging
customer-reminders
~~~

Groups help organize schedule listings, apply tags, separate operational permissions, and monitor by domain. Schedule names must be unique within a group. A schedule ARN includes Region, account, group, and schedule name.

Guiding principles:

- Separate groups by ownership boundaries and environments.
- Use searchable, business-meaningful naming conventions.
- Tag with owner, application, environment, and cost center.
- Scope permissions to create, update, enable/disable, and delete schedules by group when appropriate.
- Avoid creating one giant group if multiple teams require different operational permissions.
- Delete or clean up one-time schedules after completion if retention is unnecessary.

Schedule groups do not replace IAM policies. Effective permissions still depend on the principal calling Scheduler APIs, resource ARNs, and corresponding policies.

## 7. Targets and Execution Roles

A target is the API or resource Scheduler calls when the time arrives. Supported targets include Lambda, SQS, Step Functions, and many other AWS services; Scheduler also supports numerous AWS APIs via universal targets.

When the target is Lambda, Scheduler needs an execution role to call `lambda:InvokeFunction`. This role is distinct from Lambda's own execution role:

- **Scheduler execution role:** assumed by Scheduler to invoke Lambda or send messages to the target.
- **Lambda execution role:** assumed by Lambda when running the handler to access databases, S3, Secrets Manager, and other services.

Permission flow:

~~~mermaid
flowchart TD
    S["EventBridge Scheduler service"] -->|"sts:AssumeRole"| R["Scheduler execution role"]
    R -->|"lambda:InvokeFunction"| L["Lambda function / alias"]
    L -->|"Assume execution role"| LR["Lambda execution role"]
    LR -->|"Read/write per policy"| D[("DynamoDB / S3 / services")]
~~~

The trust policy of the Scheduler role must allow the `scheduler.amazonaws.com` service principal to assume the role. Restrict it using source account and schedule group ARN where appropriate to reduce confused deputy risk.

Illustrative trust policy:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:scheduler:ap-southeast-1:123456789012:schedule-group/orders-prod"
        }
      }
    }
  ]
}
~~~

The role's permissions policy can allow invoking only the exact function or alias:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live"
    }
  ]
}
~~~

If the target is SQS, Step Functions, or another AWS API, the required permissions will differ. Do not grant `lambda:*` or broad administrative permissions to the Scheduler role when it only needs to invoke one function.

## 8. Payloads and Context Attributes

Scheduler sends input to the target. For Lambda, the input is typically JSON received by the handler. The payload should describe the work to perform and not contain secrets or unnecessary sensitive data.

Example event for a report-aggregation function:

~~~json
{
  "jobType": "DAILY_SUMMARY",
  "scheduledTime": "<aws.scheduler.scheduled-time>",
  "executionId": "<aws.scheduler.execution-id>",
  "attemptNumber": "<aws.scheduler.attempt-number>",
  "scheduleArn": "<aws.scheduler.schedule-arn>"
}
~~~

Scheduler supports context attributes to inject execution metadata into the input. Useful attributes include:

- **<aws.scheduler.scheduled-time>:** the time the schedule was intended to run.
- **<aws.scheduler.execution-id>:** identifier for the execution.
- **<aws.scheduler.attempt-number>:** target delivery attempt count.
- **<aws.scheduler.schedule-arn>:** ARN of the schedule.
- **<aws.scheduler.target-arn>:** ARN of the target.
- **<aws.scheduler.group-name>:** name of the schedule group.

Placeholders are substituted by Scheduler when sending the input. Use exact attribute names and valid JSON formatting. Do not place placeholders inside malformed JSON strings or treat values from the event as identity authentication proof.

For recurring schedules, `scheduledTime` helps identify the business period to process. For example, if a run is delayed past midnight, the job can still aggregate the intended date instead of reading the current date from the function's clock.

## 9. Retries and DLQs: Distinguishing Target Delivery Errors from Function Execution Errors

There are two distinct failure layers when Scheduler invokes Lambda asynchronously.

**Layer 1 – Scheduler fails to deliver the request to the target.** For example, Lambda API throttling, permission errors, or temporary target service unavailability. Scheduler's retry policy controls the attempt count and maximum request age. If delivery still fails after the policy expires, Scheduler can send the event to a configured DLQ.

**Layer 2 – Lambda accepted the event, but the handler fails during execution.** With asynchronous invocation, Lambda manages execution retries according to the function's asynchronous invocation configuration. Lambda's DLQ or on-failure destination handles failures at this layer.

~~~mermaid
flowchart TD
    A["Schedule time reached"] --> B["Send Invoke request"]
    B --> C{"Lambda API accepted request?"}
    C -->|"No"| D["Scheduler retry policy"]
    D --> E{"Retries left?"}
    E -->|"Yes"| B
    E -->|"No"| F["Scheduler DLQ"]
    C -->|"Yes, accepted"| G["Lambda async queue"]
    G --> H["Function handler"]
    H --> I{"Handler succeeded?"}
    I -->|"Yes"| J["Completed"]
    I -->|"No"| K["Lambda async retry policy"]
    K --> L{"Retries left?"}
    L -->|"Yes"| H
    L -->|"No"| M["Lambda DLQ / on-failure destination"]
~~~

With a Lambda target, choose the appropriate invocation type. When using **Event**, Lambda receives the event asynchronously; Scheduler treats target acceptance of the request as successful delivery. Scheduler retries do not replace Lambda's asynchronous execution retries.

This has operational significance: the Scheduler DLQ can be empty while the handler is still failing and events are landing in Lambda's failure destination. Monitor both layers.

Retries must have bounds and backoff. Do not use retries to mask permission misconfigurations or malformed payloads. When replaying events from a DLQ, preserve business identifiers and ensure the handler is idempotent.

## 10. Idempotency for One-Time and Recurring Schedules

Scheduler may deliver to a target multiple times during certain retry or network failure scenarios. A one-time schedule does not guarantee side effects happen only once. Recurring schedules can also re-run when events are redelivered or functions retry.

Design idempotency around the **business run**, not just the invocation count. For a daily summary schedule, the key could be:

~~~text
scheduleArn + scheduledTime + jobType
~~~

Do not use the attempt number as an idempotency key because different attempts belong to the same scheduled run.

An illustrative Java handler:

~~~java
public record ScheduledJobEvent(
        String jobType,
        String scheduledTime,
        String executionId,
        String attemptNumber,
        String scheduleArn) {}

public final class DailySummaryHandler
        implements RequestHandler<ScheduledJobEvent, Void> {

    private final IdempotencyService idempotency;
    private final SummaryService summaryService;

    @Override
    public Void handleRequest(
            ScheduledJobEvent event,
            Context context) {

        String key = event.scheduleArn()
                + "#" + event.scheduledTime()
                + "#" + event.jobType();

        idempotency.executeOnce(key, () ->
                summaryService.generateForScheduledTime(
                        event.jobType(),
                        Instant.parse(event.scheduledTime())
                )
        );

        return null;
    }
}
~~~

The service classes in the example are application abstractions. `executeOnce` must be implemented using atomic operations in a durable state store, with `PROCESSING`/`COMPLETED` states, leases, or recovery mechanisms if a worker dies mid-run. Simply checking “does the key exist?” and writing in two separate steps is insufficient because two concurrent invocations can both pass the check.

If the job calls a payment service or creates external resources, pass the idempotency key down to the dependency when supported. If cross-system transactions are impossible, persist step-by-step state and maintain reconciliation or compensation procedures.

## 11. One-Time Schedules and Cleaning Up After Completion

An **at** schedule usually only needs to run once. After execution completes, the schedule may still exist as a completed resource. The `ActionAfterCompletion` property lets you choose the action after the final run—commonly **DELETE** to automatically remove the one-time schedule once done.

Use DELETE when the schedule is merely a temporary timer for a single job. Retain the schedule when you need to inspect its configuration or manage its lifecycle via a separate workflow. For recurring schedules, do not delete after each run because future occurrences remain.

When creating a schedule for an expiring order, you can use a deterministic name such as **order-expiry-ord-1042**, group by environment, and include order ID and scheduled time in the payload. When an order is canceled early, the application can disable or delete the corresponding schedule. The handler must still read the current order status before acting, because schedule deletion and the invocation can race concurrently.

If creating many one-time schedules per user or per resource, establish a strategy for managing schedule count, cleaning up completed schedules, handling deleted resources, and reconciling orphaned schedules.

## 12. Creating Schedules with the AWS CLI

Example creating a schedule that runs a report-aggregation function at 09:00 on weekdays in Vietnam time:

~~~bash
aws scheduler create-schedule \
  --name weekday-daily-summary \
  --group-name reporting-prod \
  --schedule-expression "cron(0 9 ? * MON-FRI *)" \
  --schedule-expression-timezone "Asia/Ho_Chi_Minh" \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target '{
    "Arn": "arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live",
    "RoleArn": "arn:aws:iam::123456789012:role/scheduler-invoke-daily-summary",
    "Input": "{\"jobType\":\"DAILY_SUMMARY\",\"scheduledTime\":\"<aws.scheduler.scheduled-time>\",\"executionId\":\"<aws.scheduler.execution-id>\",\"scheduleArn\":\"<aws.scheduler.schedule-arn>\"}",
    "LambdaParameters": {
      "InvocationType": "Event"
    },
    "RetryPolicy": {
      "MaximumEventAgeInSeconds": 3600,
      "MaximumRetryAttempts": 5
    },
    "DeadLetterConfig": {
      "Arn": "arn:aws:sqs:ap-southeast-1:123456789012:scheduled-target-dlq"
    }
  }' \
  --state ENABLED
~~~

The ARNs, account ID, Region, role, and queue in the example are illustrative values; replace them with resources from your deployment environment. The Scheduler execution role needs permission to invoke the exact alias and permission to send messages to the DLQ. If the queue is encrypted with a customer-managed KMS key, the relevant policies must also permit the required operations.

For a one-time schedule, you can use:

~~~bash
aws scheduler create-schedule \
  --name expire-order-ord-1042 \
  --group-name orders-prod \
  --schedule-expression "at(2026-12-01T09:00:00)" \
  --schedule-expression-timezone "Asia/Ho_Chi_Minh" \
  --action-after-completion DELETE \
  --flexible-time-window '{"Mode":"OFF"}' \
  --target file://target.json \
  --state ENABLED
~~~

Putting the target JSON in a separate file avoids escaping errors for complex payloads. Before enabling a schedule, verify the expression, time zone, ARN, role, target payload, and DLQ. Use a test environment or a near-future schedule to verify end-to-end.

## 13. Modeling with CloudFormation

Schedules and groups can be managed with CloudFormation. Abbreviated example:

~~~yaml
Resources:
  ReportingScheduleGroup:
    Type: AWS::Scheduler::ScheduleGroup
    Properties:
      Name: reporting-prod

  DailySummarySchedule:
    Type: AWS::Scheduler::Schedule
    Properties:
      Name: weekday-daily-summary
      GroupName: !Ref ReportingScheduleGroup
      State: ENABLED
      ScheduleExpression: cron(0 9 ? * MON-FRI *)
      ScheduleExpressionTimezone: Asia/Ho_Chi_Minh
      FlexibleTimeWindow:
        Mode: OFF
      Target:
        Arn: arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live
        RoleArn: !GetAtt SchedulerExecutionRole.Arn
        Input: '{"jobType":"DAILY_SUMMARY","scheduledTime":"<aws.scheduler.scheduled-time>"}'
        LambdaParameters:
          InvocationType: Event
        RetryPolicy:
          MaximumEventAgeInSeconds: 3600
          MaximumRetryAttempts: 5
        DeadLetterConfig:
          Arn: !GetAtt ScheduledTargetDLQ.Arn

  SchedulerExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: scheduler.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: InvokeDailySummary
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - lambda:InvokeFunction
                Resource: arn:aws:lambda:ap-southeast-1:123456789012:function:daily-summary:live
              - Effect: Allow
                Action:
                  - sqs:SendMessage
                Resource: !GetAtt ScheduledTargetDLQ.Arn
~~~

This is a modeling example, not a complete production template. A production trust policy should include conditions restricting the source account and schedule group ARN. Declare the DLQ queue, KMS policies if using a customer-managed key, tagging, and necessary security/operational attributes. In real stacks, use `GetAtt` or `Sub` to avoid hardcoding ARNs and ensure proper resource dependencies.

When updating a schedule via the `UpdateSchedule` API, resend all desired properties because omitted fields may be reset to defaults or cleared according to update semantics. With IaC, review diffs before deploying to avoid accidentally altering the time zone, target role, or schedule state.

## 14. Managing Schedules: Create, Update, Pause, and Delete

A schedule lifecycle typically includes:

1. Creating the schedule in a group.
2. Verifying target, execution role, expression, and state.
3. Enabling the schedule.
4. Monitoring invocations and results.
5. Updating the expression or target when business rules change.
6. Pausing via the `DISABLED` state during maintenance if needed.
7. Deleting the schedule when no longer needed.

For recurring schedules, disabling can be useful during maintenance or when a dependency is unavailable. However, disabling does not automatically handle missed runs. When re-enabling, determine whether missed periods need catch-up runs. Scheduler should not be treated as a queue storing every missed run for automatic full replay.

For per-customer scheduled jobs, when the underlying business resource is deleted or canceled, update the corresponding schedule. Store the schedule ARN or identifier in business metadata so it can be accurately disabled/deleted. Schedule cleanup must be idempotent because delete operations can be retried.

## 15. Limits, Scaling, and Designing to Avoid Bursts

A system may have many schedules firing at the top of the hour or start of the day. If all of them invoke the same function or hit the same database simultaneously, the target can be throttled even though each individual schedule is valid.

Mitigations:

- Enable flexible time windows for work that does not require exact timestamps.
- Spread trigger minutes using cron expressions when business logic allows.
- Set appropriate reserved concurrency on Lambda.
- Limit worker concurrency and connection pools.
- Route heavy work through SQS or a workflow to absorb load.
- Use batch processing with explicit bounds.
- Design idempotency for duplicate invocations.
- Monitor target throttling and backlog age.
- Do not create a schedule per record if one aggregate schedule can scan due records in batches.

If hundreds of thousands of records expire, a schedule running every minute and querying an index by `expiresAt` can be more suitable than creating one schedule per record. Conversely, if each customer has an individual execution time and needs independent lifecycle management, separate schedules can be reasonable. Weigh schedule count, cost, service quotas, and cleanup complexity.

## 16. Observability and Troubleshooting

Monitor both Scheduler's target delivery and the function's business completion.

On the Scheduler side, observe CloudWatch metrics in the `AWS/Scheduler` namespace, including invocation attempts, target errors/throttling, dropped invocations, or DLQ deliveries according to service-provided metrics. Use CloudTrail to inspect administrative actions such as creating, updating, enabling/disabling, and deleting schedules.

On the Lambda side, monitor:

- Invocations, Errors, Duration, and Throttles.
- Concurrent executions and timeouts.
- Async event age, retries, and destination/DLQ if using asynchronous invocation.
- Handler logs with request ID, schedule ARN, and scheduled time.
- Business metrics such as completed jobs, skipped duplicates, failures, and late runs.

Common troubleshooting scenarios:

| Symptom | Where to check |
|---|---|
| Schedule does not run | State, expression, time zone, start/end date, group, and flexible window |
| Scheduler cannot invoke Lambda | Execution role trust, `lambda:InvokeFunction`, ARN/alias, target policy, and Region |
| Scheduler DLQ growing | Target API throttling, permissions, target availability, and Scheduler retry policy |
| Lambda is invoked but job fails | Lambda logs, function timeout, dependencies, async retry/DLQ |
| Job runs twice | Duplicate delivery, retries, idempotency key, and state claim operation |
| Job runs late | Flexible window, service delivery precision, throttling, and concurrency |
| Old schedules still exist | `ActionAfterCompletion`, cleanup workflow, and schedule group inventory |
| Schedule enabled but no logs | Check Scheduler metrics first, then Lambda invocations and log-writing permissions |

Logs should record `scheduleArn`, `scheduledTime`, `executionId`, `jobType`, idempotency outcome, and processing duration. Do not log secrets or full payloads if they contain sensitive data.

## 17. Security and Data Protection

Scheduler can pass payloads to targets and assume roles to call APIs. Therefore, security must be designed for both schedule data and execution permissions.

- Use dedicated execution roles or roles scoped by target group, following least privilege.
- Restrict trust policies by source account and schedule group where appropriate.
- Allow invoking only the necessary function ARN or alias.
- Grant `sqs:SendMessage` to the exact DLQ queue; check KMS policies if the queue is encrypted.
- Do not put passwords, tokens, or secrets in schedule `Input`.
- Pass reference identifiers and let Lambda read secrets from Secrets Manager/Parameter Store using its own execution role.
- Enable encryption of schedule data with a customer-managed KMS key if key control is required.
- Restrict principals permitted to create, update, disable, and delete schedules.
- Enforce authorization in the function before performing side effects; payload fields do not prove caller or tenant identity.
- Delete or shorten the lifecycle of schedules and payloads when no longer needed.

Schedule input can persist in resource configuration and appear in admin or audit tools. Put only the minimum necessary data into the payload.

## 18. When to Use Scheduler vs. Queue Delays vs. Workflow Timers

Not every future task requires a dedicated schedule.

| Need | Typically suitable mechanism |
|---|---|
| One-time run at a specific point in time | EventBridge Scheduler `at` |
| Recurring schedule by hour/day/week/month | EventBridge Scheduler `cron` |
| Run at a fixed interval | EventBridge Scheduler `rate` |
| Wait a short interval before delivering a message | Queue delay or appropriate message visibility |
| Orchestrate multiple steps, retries, and long waits between steps | AWS Step Functions with a Wait state |
| Process batches of due records | Scheduler triggering a sweeper function |
| Route business events to multiple consumers | EventBridge event bus and rules |

For example, an order expiring after 30 minutes can use a dedicated `at` schedule if a per-order timer is desired. If there are millions of orders and a query every minute can scan due orders via an index, a recurring schedule triggering a sweeper may be simpler and cheaper. If the process spans multiple steps such as awaiting payment, reminding the customer, canceling the order, and restoring inventory, Step Functions can model state and timers more clearly.

Do not use Scheduler as a substitute for queues on high-volume workloads needing buffering, or as a substitute for a workflow engine when multi-step orchestration and long-lived state are needed.

## 19. Production Schedule Design Checklist

Before enabling a schedule, verify:

1. Is the requirement one-time, interval-based, or cron-based?
2. Is the `at`, `rate`, or `cron` expression syntactically valid and aligned with business intent?
3. Is the time zone explicitly specified? Is there any DST impact?
4. Does the flexible time window match acceptable business latency?
5. Are the target ARN and invocation type correct?
6. Does the Scheduler execution role have a scoped trust policy and least-privilege permissions?
7. Does the Lambda execution role have permissions to the required databases, S3, or dependencies?
8. Are the retry policy and Scheduler DLQ configured?
9. If Lambda runs asynchronously, have Lambda async retries and failure destinations been verified?
10. Is the handler idempotent by scheduled time and business key?
11. Does the payload include `scheduledTime` and required identifiers?
12. Do one-time schedules have the right `ActionAfterCompletion` setting?
13. Is there a process to disable, update, delete, and clean up orphaned schedules?
14. Have quotas, bursts, concurrency, and dependency budgets been checked?
15. Are metrics, alarms, logs, and CloudTrail in place for investigation?
16. Have duplicate delivery, target throttling, handler failures, and DLQ replay been tested?
17. Does IaC manage the schedule group, schedule, role, DLQ, and target?

## Conclusion

EventBridge Scheduler runs Lambda or other AWS services on one-time, rate, or cron schedules without keeping a process alive to wait for trigger time. The schedule defines timing and target; the flexible window spreads load; the execution role grants permission to invoke the target; retries and DLQs handle target delivery failures. When Lambda receives events asynchronously, Lambda's own retries and failure destinations are a separate layer to configure and monitor.

For Java functions, accept structured payloads, use `scheduledTime` to determine the business period, persist state durably, and guarantee idempotency per schedule and intended time. Pick explicit time zones, cap concurrency, clean up one-time schedules after completion, and monitor both Scheduler and Lambda. When work involves multiple steps or long waits, consider Step Functions; when buffering and message retries are needed, use a queue. Choosing the right resource for the shape of the work makes schedules easier to operate and keeps costs predictable.
