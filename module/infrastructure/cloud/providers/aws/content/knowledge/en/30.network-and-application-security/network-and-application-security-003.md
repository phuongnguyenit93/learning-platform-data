# Rate-Based Rules and Mitigating Bots and API Abuse

## Lesson Objectives

In the CLOUD_PROVIDERS_AWS ecosystem, protecting networks and applications requires controlling both malicious traffic and how applications handle legitimate yet overly dense request bursts. AWS WAF provides Web ACLs, rules, and rule groups to inspect HTTP requests before they reach the application. Rate-based rules detect request groups exceeding a threshold within a time window and apply actions such as Block, CAPTCHA, or Challenge. When combined with AWS Managed Rules, Bot Control, API Gateway, CloudFront, Application Load Balancer, and application authentication mechanisms, organizations can reduce scraping, credential stuffing, brute force, spam, and endpoint abuse.

After this lesson, learners can:

- Explain how AWS WAF rate-based rules count requests and apply rate limits.
- Choose appropriate evaluation windows, thresholds, aggregation keys, and scope-down statements.
- Properly handle IP addresses when requests pass through a proxy or load balancer.
- Distinguish between Count, Block, CAPTCHA, and Challenge actions.
- Combine rate-based rules with Bot Control and Fraud Control for login and sign-up flows.
- Design layered API protection using AWS WAF, API Gateway, and identity-based rate limiting logic.
- Monitor false positives, analyze WAF logs, and tune rules safely.

## 1. Identifying Bots and API Abuse

A bot is a program that sends automated requests. Bots are not always malicious: search engine crawlers, service health monitors, or partner integrations can be legitimate traffic. Risk arises when bots or automated users send requests to bypass permissions, scrape unauthorized data, create fake accounts, guess passwords, or consume excessive resources.

Common abuse patterns:

| Attack or Abuse Type | Indicators | Impact |
|---|---|---|
| Login brute force | Repeated password attempts against an account or from a source | Account takeover, increased authentication load |
| Credential stuffing | Testing leaked username/password sets across many accounts | Account takeover, fraud |
| Scraping | High-rate harvesting of pricing, inventory, content, or catalogs | Loss of data advantage, increased load |
| Account creation fraud | Creating bulk accounts to claim promotions or spam | Promotion abuse, fake data |
| API enumeration | Sequential probing of IDs or parameters to discover resources | Data leakage, backend load |
| Inventory hoarding | Automated bulk reservations or cart additions | Distorted inventory and shopping experience |
| Layer 7 flood | Sending many valid-looking HTTP requests to expensive endpoints | Exhausted CPU, connections, or database |
| Per-tenant abuse | One tenant or API client consuming most of a shared quota | Impacts other customers |

Do not conclude a request is malicious solely because it comes from a bot or has high frequency. Legitimate crawlers may visit many pages; a company with hundreds of employees behind NAT may share one IP; a mobile app may send many valid requests in a short span. Rules must consider endpoint, identity, action type, behavior, tokens, and system impact.

## 2. Where Does AWS WAF Fit in the Architecture?

AWS WAF inspects HTTP(S) requests at the application layer. A Web ACL can be attached to supported resources such as:

- Amazon CloudFront distributions.
- Application Load Balancers.
- Amazon API Gateway REST APIs.
- AWS AppSync GraphQL APIs.
- Amazon Cognito user pools.
- AWS App Runner, AWS Amplify, and other services per the current supported list.

For regional resources, the Web ACL must be created in the same Region as the resource. For CloudFront, the Web ACL uses the CLOUDFRONT scope and is managed in the us-east-1 (N. Virginia) Region. Each resource can be associated with only one Web ACL at a time; a single Web ACL can be associated with multiple compatible resources within service limits.

Basic flow diagram:

~~~mermaid
flowchart LR
    C[Client or bot] --> E[CloudFront or ALB]
    E --> W[AWS WAF Web ACL]
    W -->|Valid requests| A[API Gateway or application]
    W -->|Block / Challenge / CAPTCHA| R[Response at protection layer]
    A --> B[Services and database]
    W --> L[WAF logs and CloudWatch metrics]
    A --> M[Application metrics and audit logs]
~~~

AWS WAF operates at the HTTP layer and can block requests before the backend receives them. It does not replace lower-layer network protection, user authentication, data access control, or in-application resource limits. For DDoS, consider AWS Shield and appropriate protections across network, transport, and application layers.

## 3. How Do Rate-Based Rules Work?

A rate-based rule tracks the number of requests matching the rule's conditions over an evaluation window. AWS WAF groups requests by an aggregation key. Each group is called an aggregation instance. When the request count for an instance exceeds the threshold, the rule applies its action to subsequent requests belonging to that instance that still match the scope-down statement.

For example, if the aggregation key is the IP address, each IP has its own counter:

| IP | Requests in Window | Threshold | Result |
|---|---:|---:|---|
| 198.51.100.10 | 420 | 1,000 | Below threshold |
| 198.51.100.20 | 1,450 | 1,000 | Subsequent requests may have the action applied |
| 203.0.113.8 | 85 | 1,000 | Below threshold |

The threshold is the per-evaluation-window limit for each aggregation instance, not the total request count across the entire Web ACL. If a rule limits by IP, 1,000 requests from one IP and 1,000 requests from another IP are counted separately. If a rule combines IP with HTTP method, each IP-and-method pair is a distinct instance.

A rule can include a scope-down statement to count only a subset of requests, such as POST requests to a login endpoint. In that case, GET requests to the home page or requests to other endpoints do not enter this rule's counter.

Rate-based rules are not exact transaction counters for billing or enforcing business quotas. AWS WAF estimates request rates and enforces rate limits near the configured threshold; exact counts are not guaranteed. Treat the rule as an availability protection and anomalous-traffic mitigation mechanism.

## 4. Evaluation Window and Threshold

AWS WAF supports the following evaluation windows:

| Value | Lookback Period | When to Consider |
|---:|---|---|
| 60 seconds | 1 minute | Fast reaction for sensitive endpoints |
| 120 seconds | 2 minutes | Balance responsiveness and short-term fluctuations |
| 300 seconds | 5 minutes | Default, suitable for many cases |
| 600 seconds | 10 minutes | Detecting longer-sustained behavior |

The default is 300 seconds. The evaluation window is how far back WAF looks each time it estimates the rate; it does not mean WAF only checks once per window. WAF evaluates frequently on its own evaluation schedule.

The lowest configurable limit is 10 requests within the evaluation window. Thresholds should be chosen based on normal endpoint traffic, client types, and protection goals. For example, a login endpoint typically has a lower threshold than a public catalog read endpoint; expensive report-export or search endpoints may need tighter limits.

Rate-based rules have several important operational characteristics:

- WAF enforces limits near the threshold, without guaranteeing exact enforcement.
- There may be a delay of a few minutes before WAF detects and begins rate limiting; when traffic subsides, the rule also takes time to stop applying the action. Rate-drop latency is typically under 30 seconds per AWS documentation.
- When changing the threshold, evaluation window, aggregation settings, forwarded IP, or scope-down on a running rule, counters may reset and rate-limiting activity may be disrupted for up to about a minute.
- Each rate-based rule instance has its own tracker. Two identically configured rules in two different Web ACLs do not share counters.
- If a rule group containing a rate-based rule is used in multiple places, each usage creates a separate tracking instance.

Do not use rate-based rules as the sole limit for customer quotas, billable transaction counts, or exact resource limits. These requirements should be enforced in the application or API layer after identity authentication.

## 5. Choosing an Aggregation Key

The aggregation key determines which requests are counted together. By default, rate-based rules aggregate by source IP. AWS WAF supports many other options, including IP address, forwarded IP, ASN, header, cookie, query argument, query string, URI path, HTTP method, label namespace, and JA3/JA4 fingerprint. Multiple custom keys can be combined for finer-grained aggregation instances.

| Key | Usage Example | Considerations |
|---|---|---|
| Source IP | Limit requests by network source | Source may be a proxy or NAT |
| Forwarded IP | Extract client IP from a header written by a trusted proxy | Safe only when the header is controlled |
| HTTP method | Separate GET and POST | One client can create multiple instances |
| URI path | Limit login or search endpoints separately | Consider dynamic paths and variations |
| Header or cookie | Group by client/session identifier | Do not trust unverified client-supplied values |
| Query argument | Limit by query type | Values can create high cardinality |
| Label namespace | Limit request groups labeled by earlier rules | The label-emitting rule must run first |
| JA3/JA4 fingerprint | Detect client groups with similar TLS fingerprints | Fingerprints are not user identities |
| ASN | Group by carrier or autonomous system | May group many legitimate users together |

Every component declared in a custom aggregation key must be present in a request for that request to be evaluated and rate-limited. For example, if a rule uses IP + header `X-Client-Type`, requests missing that header will not be counted by the rule. Therefore, verify key stability on real traffic.

### 5.1. Forwarded IP and Proxies

If requests pass through a reverse proxy or load balancer, the source IP seen by WAF may be the last proxy's address. A forwarded IP in a header, such as `X-Forwarded-For`, can be used to obtain the client address.

Use forwarded IP only when the proxy architecture is trusted. The proxy must strip or overwrite client-supplied headers and set the client IP value according to a verified rule. If the application directly trusts an arbitrary client-sent header, attackers can alter the header to evade rate limits.

With forwarded IP, WAF uses the first address in the header for rate-based rules. If the header is present but the IP is invalid, configure fallback behavior as MATCH or NO_MATCH. MATCH places requests with invalid IPs into a single invalid-value group; NO_MATCH skips the request for the rule. If the header is absent, a statement using the header evaluates as No match; this case does not trigger fallback behavior. Verify this behavior carefully to avoid creating a bypass when headers are missing.

## 6. Scope-Down Statements and Rule Ordering

A scope-down statement narrows the set of requests tracked by a rate-based rule. Requests that do not match the scope-down are not counted and are not rate-limited by that rule.

Examples:

- Limit only POST requests to `/api/login`.
- Limit only requests to `/api/search` with complex queries.
- Limit only traffic carrying suspicious bot labels.
- Apply rate limits only to a group of countries or a specific content type.
- Limit only requests with headers or paths matching the target endpoint.

Statements such as Byte match, Regex pattern set, IP set, Geo match, Label match, and AND/OR/NOT can be used inside scope-down. Check WCUs and rule complexity when combining multiple conditions.

AWS WAF evaluates rules in ascending priority order. Rules with lower priority numbers run first. If you want to rate-limit requests based on labels from a managed rule group or Bot Control, the label-emitting rule must run before the rate-based rule. If an earlier rule uses Block or Allow and terminates evaluation, downstream rate-based rules will not run for that request. When observing labels before deciding, you can set the rule group's override action to Count during testing.

A rate-based statement cannot be nested inside another statement. It can be placed directly in a Web ACL or rule group with a scope-down inside the rate-based statement.

## 7. Actions: Count, Block, CAPTCHA, and Challenge

Rate-based rules support actions such as Block, Count, CAPTCHA, and Challenge; do not use Allow as the action for a rate-based rule.

| Action | Behavior | When to Use |
|---|---|---|
| Count | Counts and optionally attaches labels/headers to threshold-exceeding requests, then continues Web ACL evaluation | Observation and tuning before blocking |
| Block | Blocks threshold-exceeding requests | APIs or endpoints where excessive requests must be rejected |
| CAPTCHA | Requires the client to solve a CAPTCHA when lacking a valid token | Interactive browser flows |
| Challenge | Executes a browser challenge to verify the client | Distinguishing real browsers from automated tools |

Key point: the Count action does not rate-limit traffic. It only records threshold-exceeding requests and continues evaluating subsequent rules. If the goal is to stop excessive requests from reaching the backend, select an appropriate blocking or challenge action.

With CAPTCHA or Challenge, WAF handles requests based on token status. Requests exceeding the threshold that carry a valid, unexpired token can proceed; requests exceeding the threshold without a valid token receive a Challenge or CAPTCHA. Thus, CAPTCHA/Challenge is not a mechanism that throttles every request above the threshold.

For machine-to-machine APIs, CAPTCHA or browser challenges are usually unsuitable because clients cannot interact. Use Block or custom responses for API clients while designing client-side retry/backoff. For browsers, Challenge or CAPTCHA can curb bots, but tokens, SDK integration, and user experience must be tested.

## 8. Combining AWS WAF Bot Control and Fraud Control

Rate-based rules detect high-frequency requests by a chosen key. They do not automatically identify every type of bot or fraudulent behavior. AWS WAF offers specialized managed rule groups to add detection signals.

### 8.1. Bot Control

AWS WAF Bot Control offers two main protection levels:

- **Common:** identifies many self-identifying bots such as crawlers, scrapers, and automated browsers. The rule group attaches labels to detected traffic and can block unverified bots per policy.
- **Targeted:** includes Common plus deeper detection for sophisticated bots, such as browser interrogation, fingerprinting, behavioral heuristics, rate limiting, CAPTCHA, and silent browser challenges.

Bot Control attaches labels by bot category and inspection result. Labels can drive custom rules: allow verified crawlers, limit unattributed crawlers, or block unauthorized scraping bots. Define clearly which bots benefit the product; do not block all crawlers indiscriminately, as doing so can disrupt search indexing, monitoring, or legitimate partners.

Targeted protection may require integrating the AWS WAF application integration SDK to collect tokens and session signals. This feature incurs additional charges; review pricing, endpoint scope, and integration requirements before enabling.

### 8.2. Fraud Control for Login and Sign-Up

AWS WAF Fraud Control provides two specialized managed rule groups:

- **Account Takeover Prevention (ATP):** inspects requests to login endpoints, detecting anomalous login behavior, leaked credential attempts, and credential stuffing. With CloudFront, ATP can also inspect application responses to track login success/failure rates.
- **Account Creation Fraud Prevention (ACFP):** inspects account registration endpoints, detecting bulk account creation and suspicious activity based on IP, session, account details, and tokens.

ATP and ACFP do not replace in-application authentication. They add risk signals and risk-management actions at the WAF layer. Both have endpoint configuration and application integration requirements and incur additional charges. Per current AWS documentation, ATP/ACFP are not available for Amazon Cognito user pools. Some response inspection capabilities apply only when the Web ACL protects CloudFront.

## 9. Designing Layered API Protection

APIs require multiple layers of control because a request can be syntactically valid while still abusing business logic.

| Layer | Mechanism | Goal |
|---|---|---|
| Edge | CloudFront, AWS WAF, Shield | Block malicious requests before reaching origin |
| HTTP/API gateway | AWS WAF on API Gateway REST API, API Gateway throttling | Absorb request bursts and protect stages/methods |
| Authentication | IAM, Cognito, Lambda authorizer, or suitable auth mechanism | Identify the client or user |
| Application | Quotas per user, tenant, verified API key, token buckets, and idempotency | Protect business logic and shared resources |
| Data/service | Connection pools, queues, circuit breakers, database limits | Prevent valid requests from exhausting downstream resources |
| Observability | WAF logs, API metrics, application traces, and audit logs | Detect, investigate, and tune |

AWS WAF can be attached to an API Gateway REST API and is evaluated before other access controls such as resource policies, IAM policies, Lambda authorizers, or Cognito authorizers. Therefore, WAF is well suited to blocking requests based on HTTP characteristics before API Gateway processes authentication.

API Gateway throttling uses a token bucket and can be configured at the account/Region, API, stage, method, or usage plan level depending on the API type. Usage plan throttling and quota limits are best-effort targets, not hard limits; clients can occasionally exceed quotas. API keys in usage plans identify clients for usage management and must not be used as authentication or authorization mechanisms. Use IAM, Cognito, or Lambda authorizers for authentication and authorization.

IP-based rate limits cannot replace per-user quotas. Many users can share a NAT IP; a botnet can distribute requests across many IPs. For per-account, per-tenant, or per-subscription limits, the application must enforce quotas after authenticating the principal. If WAF uses a custom header for grouping, that header must be generated or verified by a trusted component; never trust arbitrary client-supplied identity headers.

## 10. Tuning Thresholds and Avoiding False Positives

Too low a threshold can block legitimate users. Too high a threshold makes the rule react too late. Base thresholds on normal traffic and the impact of endpoint abuse.

Tuning workflow:

1. Collect baselines by endpoint, method, time of day, client type, and source network.
2. Identify sensitive endpoints such as login, signup, password reset, search, checkout, or export.
3. Choose the evaluation window and aggregation key.
4. Add a scope-down to count only requests matching the target endpoint and method.
5. Enable Count during an observation phase.
6. Compare threshold-exceeding request counts with logs, metrics, and legitimate user behavior.
7. Adjust thresholds, keys, scope-down, and exceptions for legitimate crawlers/monitors.
8. Switch to Block, CAPTCHA, or Challenge based on client type.
9. Monitor false positives, 403/429 rates, login success rates, backend latency, and request volume post-rollout.

Scenarios to consider:

- **Corporate NAT or proxies:** many legitimate users may share one IP. Per-IP thresholds must be high enough or combined with additional keys.
- **Mobile carrier NAT:** large numbers of devices can share egress addresses.
- **Good crawlers:** verify bot identity and exempt only truly necessary bots.
- **Health checks:** use a clear scope-down or allowlist for authenticated health checks without overly broad exemptions.
- **Dynamic endpoints:** URIs containing IDs can create many aggregation instances; consider normalizing paths or limiting by label/HTTP method.
- **Campaign traffic:** flash sales or media events shift baselines. Prepare a time-bounded threshold-increase procedure and monitoring.

Do not change multiple properties of a rate-based rule simultaneously in production because configuration edits can reset counters. Use staging or Count mode to validate before switching actions.

## 11. Example: Rate-Limiting Configuration for a Login Endpoint

Suppose a login API runs behind an Application Load Balancer in the ap-southeast-1 Region. The goal is to track requests to `POST /api/login` and block an IP exceeding roughly 1,000 requests in a 5-minute window.

Example CloudFormation fragment for `AWS::WAFv2::WebACL`:

~~~yaml
Resources:
  ApiWebAcl:
    Type: AWS::WAFv2::WebACL
    Properties:
      Name: ApiRateProtection
      Scope: REGIONAL
      DefaultAction:
        Allow: {}
      VisibilityConfig:
        CloudWatchMetricsEnabled: true
        MetricName: ApiRateProtection
        SampledRequestsEnabled: true
      Rules:
        - Name: LimitLoginBySourceIp
          Priority: 10
          Action:
            Block: {}
          Statement:
            RateBasedStatement:
              Limit: 1000
              EvaluationWindowSec: 300
              AggregateKeyType: IP
              ScopeDownStatement:
                AndStatement:
                  Statements:
                    - ByteMatchStatement:
                        FieldToMatch:
                          UriPath: {}
                        PositionalConstraint: EXACTLY
                        SearchString: /api/login
                        TextTransformations:
                          - Priority: 0
                            Type: NONE
                    - ByteMatchStatement:
                        FieldToMatch:
                          Method: {}
                        PositionalConstraint: EXACTLY
                        SearchString: POST
                        TextTransformations:
                          - Priority: 0
                            Type: NONE
          VisibilityConfig:
            CloudWatchMetricsEnabled: true
            MetricName: LimitLoginBySourceIp
            SampledRequestsEnabled: true
~~~

This is an example rule configuration inside a regional Web ACL. After creation, a Web ACL association must be created with the corresponding ALB or API Gateway REST API. For CloudFront, use the CLOUDFRONT scope and create the Web ACL in us-east-1.

How to read the configuration:

- `Limit` 1000 is an example threshold per aggregation instance within the evaluation window.
- `EvaluationWindowSec` 300 corresponds to 5 minutes.
- `AggregateKeyType` IP groups requests by source IP.
- `ScopeDownStatement` feeds only requests matching the exact path and method into the counter.
- `Action` Block blocks requests belonging to instances that exceeded the threshold.
- `VisibilityConfig` enables CloudWatch metrics and sampled requests for monitoring.

During initial rollout, change Action to Count to observe. Once confirmed not to block legitimate traffic, switch to Block or an appropriate action. The 1,000 threshold is not a general recommendation for every API; measure real traffic and adjust accordingly.

## 12. Example: Combining Labels and Rate-Based Rules

A managed rule group or Bot Control can attach labels to suspected bot requests. Then, a rate-based rule uses the label namespace as a scope-down or aggregation key to limit that traffic group.

Design flow:

~~~mermaid
flowchart TD
    A[Request enters Web ACL] --> B[Bot Control or managed rule group]
    B --> C{Has bot label?}
    C -- No --> D[Continue to other rules]
    C -- Yes --> E[Rate-based rule matches label]
    E --> F{Exceeds threshold?}
    F -- No --> G[Continue evaluation]
    F -- Yes --> H[Block or Challenge]
~~~

To design this properly:

1. Place the label-emitting rule group before the rate-based rule.
2. If the rate rule needs to evaluate labeled requests, ensure the preceding rule does not terminate evaluation with Allow or Block.
3. You can override selected managed rule group rules to Count during tuning so labels are emitted while requests continue evaluation.
4. Use appropriate label namespaces to distinguish bot categories or behavior groups.
5. Set actions and thresholds according to each group's impact; do not necessarily block all bots.

A rate-based rule only executes its action or applies its label when a request is actively rate-limited. Therefore, a label emitted by a rate-based rule does not mark every request matching its scope-down; it reflects requests currently exceeding the threshold for an aggregation instance.

## 13. Logging and Monitoring

Enable visibility on each rule and Web ACL to generate CloudWatch metrics. Choose recognizable metric names by endpoint and protection goal. Track:

- AllowedRequests, BlockedRequests, CountedRequests, CaptchaRequests, and ChallengeRequests.
- Request counts by rule, Web ACL, and resource.
- Blocked request rates by endpoint and method.
- Backend 4xx/5xx rates, latency, CPU, database connections, and queue depth.
- Login success/failure, password resets, signup success, and new account counts.
- Rate at which legitimate users encounter CAPTCHA/Challenge or receive denied responses.

Sampled requests can be enabled to inspect a sample of requests evaluated by WAF. Sampled requests are useful during tuning, but they do not replace full logs and may contain sensitive information.

AWS WAF supports logging to supported destinations such as Amazon Data Firehose, Amazon CloudWatch Logs, and Amazon S3 per current service configuration. When enabling logging:

- Select the correct Web ACL and destination.
- Use logging filters to reduce unnecessary log volume.
- Redact headers or fields containing tokens, cookies, credentials, and sensitive data.
- Restrict IAM access to log destinations.
- Encrypt data and set appropriate retention.
- Do not treat sampled requests or redacted logs as a complete record for every investigative requirement.

When detecting a spike, correlate WAF logs with CloudFront/ALB access logs, API Gateway execution/access logs, and application logs. Analyze source IP, URI, method, user agent, labels, token status, response codes, and timestamps. Multi-layer data helps distinguish bots, NATs, buggy clients, and legitimate traffic surges.

## 14. Response Process for API Abuse

A response playbook can follow these steps:

1. **Confirm the signal:** identify which metrics spiked, which endpoints are impacted, and when it started.
2. **Classify:** determine whether it is brute force, scraping, credential stuffing, a request flood, or a legitimate traffic spike.
3. **Mitigate impact:** enable pre-tested rules, adjust thresholds carefully, or add a scope-down for the abused endpoint.
4. **Protect users:** avoid broad blocks if NATs or large customers are impacted; use CAPTCHA/Challenge for browser traffic where appropriate.
5. **Protect the backend:** enable API Gateway throttling, limit service concurrency, and use queues or circuit breakers as needed.
6. **Protect accounts:** require additional authentication, enforce temporary policy-based lockouts, check for credential compromise, and notify users per procedure.
7. **Monitor recovery:** track blocked/count metrics, latency, error rates, and business success rates.
8. **Investigate and improve:** preserve logs, identify sources, update runbooks, and add tests for the incident scenario.

If a rule causes false positives, switching its action to Count can restore traffic during analysis, but weigh the risk if an attack is ongoing. Configuration changes require an owner, timestamp, rationale, and rollback plan.

## 15. Costs and Limits to Account For

AWS WAF charges per Web ACL, rule, and inspected request volume; certain managed rule groups such as Bot Control and Fraud Control carry additional fees. Custom aggregation keys consume more WCUs than basic IP keys. A rate-based rule has a base WCU cost plus additional WCUs per custom aggregation key; scope-down statements also add WCUs based on the statements used.

Factors to budget for:

- Number of Web ACLs and protected resources.
- Number of rules and WCUs in each Web ACL.
- Request volume and requests inspected by managed rule groups.
- Costs for Bot Control, ATP, ACFP, and intelligent threat mitigation features.
- Costs for CloudWatch metrics, log delivery, Firehose, S3 storage, and log queries.
- Data transfer between CloudFront, ALB, API Gateway, and backend.

Using scope-down statements to send only relevant requests to managed rule groups can help control cost and narrow analysis scope. However, do not narrow scope so aggressively that abusable endpoints are skipped. Measure traffic, assess risk, and balance cost against protection.

## 16. Suggested Practice

An online store exposes the following endpoints:

- `GET /products`: read product catalog.
- `GET /search`: search and filter products.
- `POST /api/login`: sign in.
- `POST /api/signup`: register an account.
- `POST /api/checkout`: create an order.

The operations team detects a sharp traffic spike across many IPs. The database begins overloading; login and signup failure rates rise while the product catalog is being scraped.

Build a layered plan:

| Endpoint | Recommended Controls | Rationale |
|---|---|---|
| `/products` | Bot Control, rate rule by bot label or fingerprint | Reduce scraping while keeping legitimate crawlers |
| `/search` | Rate-based rule by IP + path or fingerprint | Curb repetitive search requests |
| `/api/login` | Rate-based rule by IP, ATP, and backend per-account limits | Mitigate brute force and credential stuffing |
| `/api/signup` | ACFP, Challenge/CAPTCHA, and business limits | Curb fake account creation |
| `/api/checkout` | Authentication, idempotency keys, per-user/tenant quotas, and backend protection | Prevent duplicate orders and preserve resources |

Practice steps:

1. Create a Web ACL matching the CloudFront or ALB scope.
2. Enable logging and metrics; establish traffic baselines.
3. Create a rate-based rule for `POST /api/login` in Count mode.
4. Use a scope-down to exclude requests outside the target endpoint.
5. Verify impact on NATs and legitimate clients.
6. Enable Bot Control at an appropriate level and evaluate labels.
7. Consider ATP for login and ACFP for signup if architecture, endpoints, and budget meet requirements.
8. Switch rules to enforcing actions after tuning.
9. Add per-user/tenant quotas after application authentication.
10. Test load, false positives, response codes, and backend resilience.

The expected outcome is a system that curtails bots and abusive requests without disrupting legitimate customers, while providing sufficient logs for investigation and continuous improvement.

## Conclusion

AWS WAF rate-based rules are HTTP-layer request-rate controls. Rule effectiveness depends on the chosen evaluation window, threshold, aggregation key, scope-down, and action. Bot Control and Fraud Control add detection for bots, credential stuffing, and signup fraud; CloudFront, ALB, API Gateway, and the application form a multi-layered defense.

IP-based rate limits do not replace authentication and business quotas. Combine WAF with API Gateway throttling, identity authentication, per-user or per-tenant limits, backend protections, and continuous monitoring. Tuning in Count mode, checking false positives, protecting forwarded IPs, and logging safely enable sustainable rate limiting.

## References

- [Using rate-based rule statements in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html)
- [Rate-based rule high-level settings](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-high-level-settings.html)
- [Rate-based rule caveats](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-caveats.html)
- [Aggregating rate-based rules](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html)
- [Rate-based rule aggregation instances and counts](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-instances.html)
- [Applying rate limiting to requests](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-request-limiting.html)
- [Using scope-down statements](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-scope-down-statements.html)
- [Using forwarded IP addresses](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-forwarded-ip-address.html)
- [AWS WAF Bot Control](https://docs.aws.amazon.com/waf/latest/developerguide/waf-bot-control.html)
- [AWS WAF Fraud Control account takeover prevention](https://docs.aws.amazon.com/waf/latest/developerguide/waf-atp.html)
- [AWS WAF Fraud Control account creation fraud prevention](https://docs.aws.amazon.com/waf/latest/developerguide/waf-acfp.html)
- [Resources that you can protect with AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html)
- [Protecting API Gateway REST APIs with AWS WAF](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html)
- [Usage plans and API keys for REST APIs in API Gateway](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html)
- [AWS WAF logging](https://docs.aws.amazon.com/waf/latest/developerguide/logging.html)
- [AWS WAF pricing](https://aws.amazon.com/waf/pricing/)
