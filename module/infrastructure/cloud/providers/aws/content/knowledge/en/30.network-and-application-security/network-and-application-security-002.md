# AWS WAF Web ACLs, Rules, and Managed Rule Groups

AWS Web Application Firewall (AWS WAF) protects web applications and APIs by inspecting HTTP(S) requests before they reach target resources. Operators define a web access control list (web ACL), order rules by priority, choose actions for matching requests, and set a default action for requests that match no rules. AWS WAF provides custom-built rules, rule groups managed by the operations team, and managed rule groups maintained by AWS or third-party vendors.

In AWS architectures, a web ACL is typically associated with Amazon CloudFront, an Application Load Balancer (ALB), an Amazon API Gateway REST API, AWS AppSync, Amazon Cognito, or other AWS WAF–supported resources. WAF is an application-layer defense. It complements security groups, network ACLs, AWS Network Firewall, AWS Shield, and application authentication/authorization mechanisms.

This lesson focuses on the current version of AWS WAF (WAFv2): how to design web ACLs, select rules, deploy managed rule groups, test before blocking traffic, and operate protection policies safely. In some newer consoles and documentation, AWS refers to a web ACL as a "protection pack (web ACL)"; APIs and CloudFormation resources still use the term WebACL.

## Learning Objectives

After this lesson, learners can:

- Explain the role of a web ACL and select the right scope: REGIONAL or CLOUDFRONT.
- Describe rule evaluation order, the default action, and the meaning of Allow, Block, Count, CAPTCHA, and Challenge.
- Select appropriate statements to inspect IPs, geography, URIs, headers, bodies, SQL injection, XSS, and rate-exceeding traffic.
- Configure AWS Managed Rules and third-party managed rule groups in a testable and updatable manner.
- Use rule overrides, scope-down statements, and labels to reduce false positives.
- Estimate WCUs, understand body inspection limits, and control costs.
- Associate a web ACL with AWS resources, enable logging/metrics, and troubleshoot common errors.

## 1. Where AWS WAF Fits in the Architecture

AWS WAF is a web application firewall service. It identifies attributes of HTTP(S) requests, evaluates them against rules, and decides whether to allow, block, count, or require the client to pass a challenge. WAF helps mitigate risks from common attack patterns such as SQL injection, cross-site scripting (XSS), anomalous requests, bad-reputation IP sources, automated bots, and endpoint abuse.

A simplified flow:

~~~mermaid
flowchart LR
    C["Client / Bot"] --> E["CloudFront or ALB / API Gateway"]
    E --> W["AWS WAF web ACL"]
    W -->|"Allow"| A["Application / API"]
    W -->|"Block / Challenge / CAPTCHA"| X["Deny or verify client"]
    A --> D["Backend data and services"]
~~~

AWS WAF is integrated at the request entry point of the protected resource. Therefore, rules must match where WAF is attached and the request structure visible at that point. If requests pass through CloudFront before reaching an ALB, the source address seen by the ALB or WAF may be the proxy/CDN address, depending on deployment placement and forwarded IP configuration.

AWS WAF does not replace:

- **Security groups and network ACLs:** control network connectivity by address, protocol, and port.
- **AWS Network Firewall:** inspects and controls network flows at the network/transport layers inside a VPC.
- **AWS Shield:** provides DDoS protection; Shield Standard is included by default for AWS services, while Shield Advanced adds enhanced capabilities and support.
- **Application authentication and authorization:** verify identity, resource access permissions, sessions, and business rules.
- **Security controls in application code:** input validation, parameterized queries, output encoding, secret management, and dependency updates.

WAF is an additional defense layer. A request that passes WAF must still be authenticated, authorized, and validated by the application.

## 2. Web ACLs, Scope, and Protected Resources

### 2.1. What Is a Web ACL?

A web ACL is the central resource containing:

- Name, description, ARN, and scope.
- Default action of Allow or Block.
- A list of rules with priority, statement, action, and visibility configuration.
- Referenced rule groups, including managed rule groups.
- CAPTCHA/Challenge, body inspection, custom response, and logging configurations.
- Metrics and sampled request collection settings.

A web ACL can protect one or more compatible resources. Multiple applications can share a web ACL when their protection policies are similar; applications with differing requirements should generally use separate web ACLs so exception rules for one application do not affect others.

### 2.2. Regional and CloudFront Scopes

AWS WAF has two main scopes:

| Scope | Usage | Region of WAF Resource |
|---|---|---|
| REGIONAL | Protects regional resources such as ALB, API Gateway REST API, AppSync, Cognito, App Runner, Amplify, Verified Access, and Amazon Bedrock AgentCore Gateway. | Same Region as the protected resource. |
| CLOUDFRONT | Protects CloudFront distributions at the global edge layer. | Manage the web ACL and related WAF resources in us-east-1 (N. Virginia). |

The scope is chosen when creating the web ACL and cannot be changed by editing an existing web ACL. If the wrong scope is chosen, you generally must create a new web ACL with the right scope and move the association.

Operational notes:

- A REGIONAL web ACL must be in the same Region as the ALB or regional API.
- A CLOUDFRONT web ACL is managed in us-east-1, even though the distribution serves global users.
- A CloudFront distribution is linked through the distribution configuration; it does not use the same association flow as an ALB.
- For ALBs, API Gateway REST APIs, and supported regional resources, AssociateWebACL can be used.
- A WAF resource ARN reflects its scope. For CloudFront, the ARN uses the global segment; for regional resources, the ARN uses the regional segment.

Do not confuse AWS WAF with AWS WAF Classic. New resources should use WAFv2 (wafv2 in API/CLI and AWS::WAFv2::* in CloudFormation).

### 2.3. Choosing Where to Attach WAF

| Architecture | Typical WAF Attachment Point | What to Verify |
|---|---|---|
| CloudFront → ALB → ECS | CLOUDFRONT web ACL on CloudFront; optionally add regional WAF on ALB if separate policies are needed. | Prevent direct ALB access bypassing the edge; identify true client IP. |
| Internet → ALB → EC2/ECS | REGIONAL web ACL attached to ALB. | Security group accepts only required traffic; body inspection is limited to 8 KB. |
| API Gateway REST API → Lambda | REGIONAL web ACL attached to REST API stage. | Verify stage/association, body inspection, and API authentication. |
| AppSync GraphQL API | REGIONAL web ACL. | Body inspection limits; query depth/complexity still need controls at the GraphQL/app layer. |
| Amazon Cognito user pool | REGIONAL web ACL. | Specialized rules can be used for sign-in flows and account protection. |

AWS WAF does not attach directly to every endpoint type. Before designing, verify whether the resource type in use is supported in that Region and scope.

## 3. How AWS WAF Evaluates Requests

### 3.1. Priority and Evaluation Order

AWS WAF evaluates rules in ascending numerical priority order: priority 0 runs before priority 10. Priority values must be unique within the same web ACL. When a rule produces a terminating action, WAF stops evaluating the remaining rules for that request.

Example:

| Priority | Rule | Action | Outcome |
|---:|---|---|---|
| 0 | Block IPs in deny list | Block | Matching requests are blocked immediately. |
| 10 | AWS Managed Rules CRS | Per rules in group | The rule group may block or continue. |
| 20 | Rate limit /login | Block when over threshold | Rate-limited requests are blocked. |
| 30 | Label internal requests | Count | Counts and continues evaluation. |
| — | Default action | Allow | Applied if no prior terminating action occurred. |

Do not order rules merely by name. Order them according to the desired processing flow and understand which rules can terminate evaluation.

### 3.2. Default Action

The default action is applied if a request does not trigger a terminating action during evaluation.

- **Allow:** suited for public websites/APIs that need to block specific suspicious request patterns. Requests matching no rules are forwarded to the resource.
- **Block:** suited for applications with an explicit allowlist of permitted endpoints/clients. Sufficient Allow rules covering legitimate traffic must be in place before applying.

The default action can only be Allow or Block. Count cannot be set as the default action. Choosing an overly permissive default action can leave gaps; choosing Block without adequate allow rules can take down legitimate users.

### 3.3. Rule Actions

| Action | Type | Behavior |
|---|---|---|
| Allow | Terminating | Lets the request proceed to the protected resource and stops rule evaluation. |
| Block | Terminating | Blocks the request; returns HTTP 403 by default, customizable via custom response. |
| Count | Non-terminating | Records the matching request and continues evaluating the next rule. |
| CAPTCHA | Conditional | Requires the client to solve a CAPTCHA if the token is invalid/expired; if valid, continues like Count. |
| Challenge | Conditional | Runs a silent browser challenge; if the token is valid, continues like Count. |

CAPTCHA and Challenge are suited for browsers accessing HTTPS. API clients, mobile apps, or webhooks unable to process tokens can break if misapplied. These two actions incur additional charges. Do not use CAPTCHA/Challenge as a substitute for account authentication or comprehensive brute-force protection.

### 3.4. Rule Group Action Overrides and Rule Action Overrides

Distinguish between two override levels:

- **Override the entire rule group result (OverrideAction: Count):** forces the outcome of the entire rule group to Count in the web ACL for testing. Inner rules are still evaluated per group logic, but the group result does not block requests.
- **Override one or more inner rules (RuleActionOverrides):** changes the action of specified rules, typically switching a rule suspected of false positives to Count while keeping original actions on other rules.

For example, when a managed rule group mistakenly blocks an upload endpoint, find the specific rule ID in logs and override just that rule to Count or narrow its scope. Do not leave an entire managed rule group in Count mode long-term just to work around a single false positive.

## 4. Rule Statements: Defining Requests to Inspect

A statement describes the conditions for a rule to match a request. Statements can be combined using AND, OR, NOT logic, and scope-down statements can restrict the set of evaluated requests.

### 4.1. Common Match Statements

| Statement | Purpose | Example |
|---|---|---|
| IPSetReferenceStatement | Matches IPv4/IPv6 addresses in an IP set. | Block source IPs identified as attacking. |
| GeoMatchStatement | Matches country/geographic region by IP. | Count requests from regions outside the served market. |
| ByteMatchStatement | Searches for strings or byte patterns in a request component. | Match URIs starting with /admin. |
| RegexPatternSetReferenceStatement | Matches against a regex pattern set. | Detect suspicious paths or parameter formats. |
| SizeConstraintStatement | Checks the size of a request component. | Detect query strings or bodies exceeding expected sizes. |
| SQLiMatchStatement | Detects SQL injection patterns. | Inspect query strings or bodies. |
| XssMatchStatement | Detects cross-site scripting patterns. | Inspect URIs, queries, bodies, or headers. |
| LabelMatchStatement | Matches labels attached to the request by earlier rules. | Block or count request groups classified by a managed rule group. |
| RateBasedStatement | Counts and rate-limits by an aggregation key. | Limit login requests per IP within a time window. |

Request components can include URI path, query string, HTTP method, single header, all headers, cookies, body, JSON body, and supported fingerprint attributes. Choose the exact component instead of unnecessarily inspecting the entire request.

### 4.2. Text Transformations

Before matching, WAF can transform data to normalize a request component. Common transformations include:

- LOWERCASE: converts strings to lowercase.
- URL_DECODE: decodes URL encoding.
- HTML_ENTITY_DECODE: decodes HTML entities.
- COMPRESS_WHITE_SPACE: normalizes whitespace.
- CMD_LINE: normalizes certain characters commonly found in command lines.
- NORMALIZE_PATH and NORMALIZE_PATH_WIN: normalizes paths according to respective OS rules.

Transformations execute in priority order. A string may change across multiple steps; test with real requests and avoid overly broad transformations that increase false positives.

### 4.3. Combining Conditions

Suppose you need to block requests to /admin from IPs outside the administrative network. You can use AND to combine a URI path starts-with /admin condition and a NOT condition against an allowed IP set. Logical conditions should be structured clearly so operators understand which requests are blocked.

Do not place a managed rule group statement inside AND/OR/NOT. A managed rule group is referenced directly as a rule in the web ACL. A rule group reference also cannot be nested inside another statement.

## 5. Rate-Based Rules: Limiting Requests by Rate

Rate-based rules help mitigate brute force, credential stuffing, scraping, or endpoint abuse. WAF counts requests by an aggregation key and applies the action to requests exceeding the limit.

Key settings:

- Limit: request threshold within the evaluation window; the lowest allowed value is 10.
- EvaluationWindowSec: window of 60, 120, 300, or 600 seconds; default is 300 seconds.
- AggregateKeyType: aggregation method, typically IP, forwarded IP, custom keys, or constant.
- ScopeDownStatement: limits requests included in the counter, e.g., only the /login URI.
- Action: Count, Block, CAPTCHA, or Challenge; rate-based rules cannot use Allow as the limiting action.

Rate limiting is enforced near the configured threshold, not as an exact transaction counter. WAF evaluates periodically and there can be latency when traffic spikes or drops rapidly. Do not use rate-based rules as a business quota counter requiring transactional precision.

### 5.1. Example: Rate-Limiting a Login Endpoint

An API has a /login endpoint. We want to track requests per IP over 5 minutes and block when exceeding 500 requests.

~~~yaml
- Name: RateLimitLogin
  Priority: 20
  Statement:
    RateBasedStatement:
      Limit: 500
      EvaluationWindowSec: 300
      AggregateKeyType: IP
      ScopeDownStatement:
        ByteMatchStatement:
          FieldToMatch:
            UriPath: {}
          PositionalConstraint: STARTS_WITH
          SearchString: /login
          TextTransformations:
            - Priority: 0
              Type: NONE
  Action:
    Block: {}
  VisibilityConfig:
    SampledRequestsEnabled: true
    CloudWatchMetricsEnabled: true
    MetricName: RateLimitLogin
~~~

This example only illustrates rule structure. The threshold of 500 is not a universal recommendation; measure normal traffic, account for shared NAT users, and determine client behavior before choosing a threshold.

### 5.2. Choosing an Aggregation Key

- **Source IP:** uses the source IP address WAF receives. If requests pass through a proxy or load balancer, this address may be the proxy's.
- **Forwarded IP:** reads the address from a configured header, typically X-Forwarded-For. Trust only headers overwritten by a trusted proxy; if clients can send the header themselves without upstream stripping/overwriting, attackers can spoof IPs.
- **Custom keys:** combine IP, HTTP method, header, cookie, query argument, or label namespace as needed.
- **Constant:** aggregates all matching requests into a single counter; must include a scope-down statement to define which requests are counted.

Requests missing a component chosen as an aggregation key may be excluded from the corresponding counter instance. Verify real request structure and fallback behavior when using forwarded IP.

Each rate-based rule maintains its own counter. Two identical rules in different places do not share counting state. A rate-based rule inside a rule group is also scoped to that group instance.

### 5.3. Rate Limiting Does Not Replace Login Protection

IP-based rate limits can affect legitimate users in offices, schools, or mobile networks sharing NAT. For login endpoints, combine:

- Rate-based rules in WAF to dampen burst traffic.
- Per-account or per-identity limits in the application.
- MFA, passwordless, or authentication mechanisms resistant to credential stuffing.
- Monitoring failed logins and detecting anomalies.
- Backoff, controlled lockouts, and account recovery workflows.

WAF does not have full business account context when requests have not yet been authenticated by the application.

## 6. AWS Managed Rules and Managed Rule Groups

A managed rule group is a collection of rules maintained by a provider. When added to a web ACL, WAF evaluates its inner rules per the provider's published configuration. Operators can configure version, scope-down statements, and override actions.

Managed rule groups generally deploy an initial defense layer faster than authoring dozens of rules manually. However, managed rules do not know every application nuance. Test against real traffic and check for false positives before enabling Block.

### 6.1. Common AWS Managed Rules Groups

| Group | Purpose | When to Consider |
|---|---|---|
| AWSManagedRulesCommonRuleSet (Core Rule Set/CRS) | Common web exploit patterns, anomalous requests, and protocol checks. | Baseline layer for many websites/APIs. |
| AWSManagedRulesKnownBadInputsRuleSet | Request patterns known to be malicious inputs. | Complements CRS. |
| AWSManagedRulesSQLiRuleSet | Patterns related to SQL injection. | Applications with data-query endpoints. |
| AWSManagedRulesAmazonIpReputationList | Bad-reputation IPs based on AWS threat intelligence. | Block sources with known attack activity. |
| AWSManagedRulesAnonymousIpList | Sources such as anonymous proxies, VPNs, or Tor exit nodes per AWS lists. | When application policy requires evaluating anonymous traffic. |
| Rule groups for Linux, Unix/POSIX, Windows, PHP, or WordPress | Platform/application-specific exploit patterns. | Enable only when relevant to the stack. |
| AWSManagedRulesAdminProtectionRuleSet | Protects common administrative pages. | Applications with matching admin endpoints. |
| Bot Control | Classifies and controls bots. | Websites/APIs facing scraping or automation; incurs additional cost. |
| AWSManagedRulesATPRuleSet (Account Takeover Prevention) | Detects account takeover attempts in login flows. | Applications requiring login protection with suitable integration setup. |
| AWSManagedRulesACFPRuleSet (Account Creation Fraud Prevention) | Detects fraud signals in account creation flows. | Public sign-up services exposed to abuse risk. |

Managed rule group names and capabilities can change over time. Check the provider's list and documentation for your target Region/scope before deploying. Most baseline AWS Managed Rules carry no separate fee, whereas advanced groups such as Bot Control, ATP, or ACFP incur additional charges. Managed rule groups from AWS Marketplace may carry vendor subscription fees.

### 6.2. Adding a Managed Rule Group to a Web ACL

A managed rule group is declared via ManagedRuleGroupStatement, typically including:

- VendorName: AWS or the managed rule group provider.
- Name: rule group name.
- Version: version string if the group supports versioning and you want to pin a specific version.
- ScopeDownStatement: restricts the set of evaluated requests.
- RuleActionOverrides: overrides actions of individual inner rules if needed.

CloudFormation example:

~~~yaml
- Name: AWSManagedCommonRules
  Priority: 10
  OverrideAction:
    None: {}
  Statement:
    ManagedRuleGroupStatement:
      VendorName: AWS
      Name: AWSManagedRulesCommonRuleSet
      RuleActionOverrides:
        - Name: SizeRestrictions_BODY
          ActionToUse:
            Count: {}
  VisibilityConfig:
    SampledRequestsEnabled: true
    CloudWatchMetricsEnabled: true
    MetricName: AWSManagedCommonRules
~~~

In the example, the SizeRestrictions_BODY rule is overridden to Count so operators can observe its impact on upload endpoints. Rule names must match the exact names published by the managed rule group. Check logs, sampled requests, and the group's documentation before applying overrides.

### 6.3. Rule Group Versioning

Some managed rule groups provide versions:

- **Default version:** the provider manages the recommended version. For versioned AWS Managed Rules, AWS sends an SNS notification before switching the default to another static version; IP reputation rule groups are an exception and do not provide versioning/SNS update notifications.
- **Static version:** selects a specific version to allow time for testing and approval before upgrading. Versions have a lifecycle and can expire.
- **LATEST:** always tracks the newest static version. This option is currently supported for AWS WAF Bot Control; changes may arrive without advance notice under standard version notification mechanics.

Do not pin a version and forget to upgrade it. Establish a process to receive notifications, test new versions, compare false positives, and update before the old version expires.

### 6.4. Tuning Managed Rules

Safe workflow:

1. Create the web ACL in a staging or test environment.
2. Enable managed rule groups with Count/appropriate overrides to observe traffic.
3. Send both valid request suites and simulated attack requests through the application.
4. Enable logging, inspect rule IDs, labels, URIs, request components, and actions.
5. Identify which rules cause false positives; examine specific endpoints and payloads.
6. Override only the necessary rules to Count or narrow the group using a scope-down statement.
7. Run in Count mode on production traffic for a representative period.
8. Switch to blocking actions per rule group; monitor metrics and application errors after rollout.

Do not add a broad Allow rule at a lower priority number before all managed rules just to bypass a false positive. That approach can let malicious requests through and prevent downstream protection rules from evaluating.

## 7. Scope-Down Statements and Labels

### 7.1. Scope-Down Statements

A scope-down statement narrows the set of requests evaluated by a rule group or rate-based rule. Examples:

- Apply Bot Control only to `/search` and `/catalog` URIs.
- Run the SQLi managed rule group only on endpoints accepting search inputs.
- Rate-limit only requests whose URI starts with `/login`.
- Inspect only requests from a group of countries or carrying a specific label.

A scope-down statement acts as a pre-filter before the rule group or rate-based rule processes a request. It does not alter the rules inside a managed rule group. Statements used in scope-down must be nestable per WAF rules; a managed rule group statement cannot be nested inside a scope-down.

### 7.2. Labels

Rules can attach labels to matching requests. Subsequent rules can use LabelMatchStatement to act on those labels. Managed rule groups can also emit labels describing the request type or matched rule.

Example of using labels:

1. A managed rule group detects a request showing signs of SQL injection but is configured as Count for observation.
2. A subsequent rule inspects labels within the managed rule group's namespace.
3. Custom rules can block a specific set of labels, Count another set, or attach additional labels for logs/metrics.

Label namespaces and label names are case-sensitive. A rule matching a label must execute after the rule that generates the label. If an earlier rule produced a terminating action, subsequent rules will not run.

## 8. WCUs and Design Limits

AWS WAF uses Web ACL Capacity Units (WCUs) to represent the compute resources required for rule evaluation. Each statement has a base WCU cost; factors such as regexes, text transformations, JSON body inspection, and nested logic can increase WCUs.

Key limits per current AWS documentation:

| Item | Published Limit |
|---|---:|
| Maximum WCUs per web ACL | 5,000 |
| Maximum WCUs per rule group | 5,000 |
| Maximum rate-based rules per web ACL | 10 |
| Minimum threshold for rate-based rules | 10 requests |
| Maximum IPs per IP set | 10,000 |
| Maximum reference statements per web ACL | 50 |
| Maximum reference statements per rule group | 50 |
| WCU threshold above which extra cost beyond base price applies | Over 1,500 WCUs |

Quotas apply per account and Region; some quotas are fixed while others support increase requests. Check the AWS WAF quotas page before large-scale deployments, as quotas and pricing can change.

### 8.1. WCU Budgeting

- Use managed rule groups relevant to your stack; do not enable every group just because it exists.
- Check the WCU of managed rule groups via provider metadata/DescribeManagedRuleGroup.
- Calculate WCUs for custom rules and scope-down statements.
- Use IP sets and regex pattern sets to reuse data instead of creating duplicate statements.
- Review text transformations and body/JSON inspection scope.
- Use CheckCapacity or equivalent capacity checks before updating a web ACL via API/CLI.
- Monitor costs for WCUs, request inspection, advanced managed groups, CAPTCHA/Challenge, and logging.

WCUs are not a simple rule count limit. Two web ACLs with the same number of rules can consume vastly different WCUs depending on statements and complexity.

## 9. Body Inspection Limits and Oversize Handling

AWS WAF only inspects the portion of the request body forwarded to WAF by the underlying service. If the body exceeds the limit, the excess portion is not inspected by WAF.

| Resource | Body Inspection Limit |
|---|---|
| Application Load Balancer | Fixed 8 KB |
| AWS AppSync | Fixed 8 KB |
| CloudFront | Default 16 KB; can be increased in 16 KB increments up to 64 KB |
| API Gateway, Cognito, App Runner, Verified Access, Bedrock AgentCore Gateway | Default 16 KB; can be increased up to 64 KB per supported configuration |
| AWS Amplify | Uses CloudFront limits |

Increasing the body inspection limit may incur additional charges for traffic exceeding the default limit. AWS WAF does not support request body inspection rules for gRPC traffic. When a resource receives a body larger than the limit, the truncated portion is excluded from matching.

For Body or JsonBody, choose OversizeHandling:

- CONTINUE: continues inspecting the portion of the body WAF received.
- MATCH: treats the request as matching the statement.
- NO_MATCH: treats the request as not matching the statement.

The default is CONTINUE. If a rule has a Block action and uses MATCH, requests with oversized bodies may be blocked. If it uses NO_MATCH, large requests may pass that rule uninspected. Choose based on endpoint type and how the application handles payloads.

Other request components also have limits. When inspecting all headers or cookies, WAF may inspect only up to the first 8 KB and 200 items. Inspecting a single header may have different limits. Check the specific limits for the component in use.

## 10. Creating a Web ACL with CloudFormation

Below is an example regional web ACL for an ALB. The web ACL defaults to Allow, adds the AWS Managed Rules Common Rule Set, and adds a rate-based rule for /login. The SizeRestrictions_BODY rule is overridden to Count so operators can observe it before deciding to block large payloads.

~~~yaml
Parameters:
  ApplicationLoadBalancerArn:
    Type: String
    Description: ARN of the regional Application Load Balancer to protect

Resources:
  ShopWebACL:
    Type: AWS::WAFv2::WebACL
    Properties:
      Name: shop-api-web-acl
      Description: Web ACL for the shop API
      Scope: REGIONAL
      DefaultAction:
        Allow: {}
      VisibilityConfig:
        SampledRequestsEnabled: true
        CloudWatchMetricsEnabled: true
        MetricName: shop-api-web-acl
      Rules:
        - Name: AWSManagedCommonRules
          Priority: 10
          OverrideAction:
            None: {}
          Statement:
            ManagedRuleGroupStatement:
              VendorName: AWS
              Name: AWSManagedRulesCommonRuleSet
              RuleActionOverrides:
                - Name: SizeRestrictions_BODY
                  ActionToUse:
                    Count: {}
          VisibilityConfig:
            SampledRequestsEnabled: true
            CloudWatchMetricsEnabled: true
            MetricName: aws-managed-common-rules
        - Name: RateLimitLogin
          Priority: 20
          Action:
            Block: {}
          Statement:
            RateBasedStatement:
              Limit: 500
              EvaluationWindowSec: 300
              AggregateKeyType: IP
              ScopeDownStatement:
                ByteMatchStatement:
                  FieldToMatch:
                    UriPath: {}
                  PositionalConstraint: STARTS_WITH
                  SearchString: /login
                  TextTransformations:
                    - Priority: 0
                      Type: NONE
          VisibilityConfig:
            SampledRequestsEnabled: true
            CloudWatchMetricsEnabled: true
            MetricName: rate-limit-login

  ShopWebACLAssociation:
    Type: AWS::WAFv2::WebACLAssociation
    Properties:
      WebACLArn: !GetAtt ShopWebACL.Arn
      ResourceArn: !Ref ApplicationLoadBalancerArn
~~~

In a real template, ApplicationLoadBalancerArn must be passed as a parameter or reference an ALB resource created in the same stack. The web ACL and ALB must reside in the same Region. If deploying for CloudFront, change the scope to CLOUDFRONT, deploy the WAF resources in us-east-1, and attach the ARN in the CloudFront distribution configuration; do not use AWS::WAFv2::WebACLAssociation as in the ALB example.

Before deploying, verify metric names, rule names, WCUs, CloudFormation execution role permissions, and the impact of association on production traffic. On an existing stack, web ACL changes can immediately affect live traffic.

## 11. Managing with the AWS CLI

The commands below illustrate operations on a regional web ACL in ap-southeast-1.

List web ACLs:

~~~bash
aws wafv2 list-web-acls \
  --scope REGIONAL \
  --region ap-southeast-1
~~~

Get a web ACL configuration:

~~~bash
aws wafv2 get-web-acl \
  --name shop-api-web-acl \
  --scope REGIONAL \
  --id <WEB_ACL_ID> \
  --region ap-southeast-1
~~~

List supported resources in the Region:

~~~bash
aws wafv2 list-resources-for-web-acl \
  --web-acl-arn <WEB_ACL_ARN> \
  --resource-type APPLICATION_LOAD_BALANCER \
  --region ap-southeast-1
~~~

Associate a web ACL with an ALB:

~~~bash
aws wafv2 associate-web-acl \
  --web-acl-arn <WEB_ACL_ARN> \
  --resource-arn <ALB_ARN> \
  --region ap-southeast-1
~~~

Check the web ACL associated with a resource:

~~~bash
aws wafv2 get-web-acl-for-resource \
  --resource-arn <ALB_ARN> \
  --region ap-southeast-1
~~~

Disassociate a web ACL from an ALB:

~~~bash
aws wafv2 disassociate-web-acl \
  --resource-arn <ALB_ARN> \
  --region ap-southeast-1
~~~

For CloudFront, use `--scope CLOUDFRONT` and `--region us-east-1` when managing WAF resources. Attaching the web ACL is performed in the CloudFront distribution configuration. Do not run disassociate in production without a plan to replace the protection layer.

When updating a web ACL via API/CLI, GetWebACL returns a LockToken. Pass the current token to UpdateWebACL; if the configuration was modified by another process, the stale token will be rejected. Re-read the web ACL before updating to avoid overwriting another team's changes.

## 12. Logging, Metrics, and Visibility

### 12.1. CloudWatch Metrics

Each web ACL and rule can configure VisibilityConfig:

- CloudWatchMetricsEnabled: sends metrics to Amazon CloudWatch.
- MetricName: metric name; use only supported characters and avoid reserved names such as All and Default_Action.
- SampledRequestsEnabled: enables request sampling to view requests matching rules.

Metrics track Allowed, Blocked, Counted, CAPTCHA, and Challenge requests per web ACL/rule. When a rule's action or priority changes, compare metrics before and after the change.

### 12.2. WAF Logging

AWS WAF can write request logs to:

- Amazon CloudWatch Logs.
- Amazon S3.
- Amazon Data Firehose delivery streams.

Log destination names must follow the `aws-waf-logs-` prefix required by the destination type. Logs typically contain action, terminating rule, rule group, labels, HTTP request details, and relevant investigative fields. Enable log filters to retain important records such as Block, CAPTCHA, Challenge, or requests with specific labels while controlling log volume.

Examples of questions logs help answer:

- Which rule blocked the request?
- Which labels did the managed rule group emit?
- Which URI, method, or header triggered the match?
- Was the request rate-limited?
- Did a recent rule change increase false positives?

### 12.3. Protecting Sensitive Data

Request logs and sampled requests can contain session IDs, tokens, emails, query parameters, or personal data. Follow these practices:

- Use data protection to protect sensitive fields in log data and sampled requests as supported by configuration.
- Use RedactedFields for URI path, query string, single header, and HTTP method in the logging configuration where appropriate.
- Note that logging field redaction does not automatically apply to sampled requests.
- Disable sampling or configure data protection if sampled requests might contain secrets/PII.
- Restrict IAM permissions to read logs, encrypt log destinations, and set appropriate retention.
- Never include access tokens, passwords, or payment card data in URLs/query strings.

Redaction only affects the correspondingly configured request component. For example, redacting a SingleHeader does not automatically mask data from rules matching against Headers. Inspect logging and sampling configurations separately.

## 13. Testing and Safe Rollout

AWS recommends testing and tuning web ACLs before enforcing them on production traffic. A practical rollout path:

1. **Create staging:** attach the web ACL to a test environment receiving production-like requests.
2. **Enable logging and metrics:** ensure rule IDs, labels, request components, and actions can be identified.
3. **Run valid test cases:** login, search, upload, API pagination, webhooks, mobile clients, and administrative workflows.
4. **Run security test cases:** test SQLi/XSS payloads, anomalous URIs, rate-exceeding requests, denied IPs, and large request bodies.
5. **Enable Count:** switch rules or managed rule groups under evaluation to Count on live traffic for a representative period.
6. **Review false positives:** cross-check matched requests against business logic rather than relying solely on rule names.
7. **Apply minimal overrides:** adjust only the specific problematic rule, statement, or scope-down.
8. **Gradually switch to Block/Challenge:** roll out by rule group and monitor error rates, conversion, API latency, and blocked request counts.
9. **Prepare rollback:** keep the pre-change configuration and a procedure to revert the web ACL to a safe version.
10. **Monitor post-rollout:** set alarms for spikes in BlockedRequests, CountedRequests, CAPTCHA/Challenge, and application errors.

Count mode does not guarantee requests will pass in every scenario if an earlier rule already produced a terminating action. During testing, verify the entire priority order and default action.

## 14. Integration with Java and Spring Boot Applications

Because AWS WAF sits in front of the application, Java applications do not need to call the WAF SDK on every request. Backend teams primarily coordinate through HTTP contracts and operations:

- Identify public endpoints, login, upload, search, and admin endpoints.
- Log correlation IDs in the application to link with WAF logs; avoid logging secrets or unnecessary PII.
- Define rate-limit thresholds based on client behavior and real load.
- Return consistent error handling when WAF blocks requests; clients may receive 403 before requests reach the backend.
- If using CAPTCHA/Challenge, the frontend must support tokens/cookies and appropriate retry flows.
- If the application sits behind CloudFront or an ALB, clearly define trusted IP sources and how proxies populate forwarded headers.

For example, a Spring Boot service has `/api/login`, `/api/search`, and `/api/files` endpoints. WAF can apply a rate-based rule to `/api/login`, a baseline managed rule group across the web ACL, a scope-down SQLi rule group for the search endpoint, and appropriate body size checks for uploads. The application must still enforce password hashing, MFA, parameterized SQL, validation, and authorization.

## 15. Design Scenario: Protecting an Online Store

An online store deploys CloudFront in front of an ALB, with backends running on ECS and data in RDS. Requirements include blocking malicious requests, mitigating bot scraping, curbing login brute-force attempts, and protecting APIs.

A deployable design:

- CLOUDFRONT web ACL attached to the distribution to filter traffic at the edge.
- AWS Managed Rules CRS and Known Bad Inputs as a baseline; run in Count mode before switching rules to Block.
- IP reputation managed rule group to address known bad sources.
- Rate-based rules scoped down to `/login` and `/api/auth`, with distinct thresholds for browser/mobile clients.
- Bot Control if scraping or automation is a significant risk and budget permits.
- Regional WAF on the ALB if separate policies are needed; ALB security group accepts traffic only from the CloudFront origin-facing prefix list or approved sources.
- CloudWatch metrics, WAF logs, and alerts for BlockedRequests, rate limits, and false positives.
- IAM roles and a pipeline deploying the web ACL via CloudFormation, with change reviews and rollback.

Do not apply the same rate-limit threshold to every endpoint. `/health`, static assets, login, search, and upload have different request characteristics. In particular, if the ALB remains directly accessible from the Internet, users can bypass the CloudFront web ACL; protect the origin with network controls and proper access configuration.

## 16. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Valid requests receive 403 | Managed rule false positive, overly broad custom rule, priority order, or default Block. | Locate the terminating rule in WAF logs; switch that specific rule to Count to verify. |
| Rate limit blocks users sharing a network | Multiple users share one public IP/NAT. | Adjust threshold, choose an appropriate aggregation key, or add a specific scope-down. |
| Rate limit fails to identify client IP | WAF sees proxy/CDN IP or incorrect forwarded header. | Check topology and whether upstream overwrites trusted headers. |
| SQLi/XSS rules miss large payloads | Body exceeds WAF inspection limit. | Check body size limit and OversizeHandling; consider increasing the limit if supported. |
| Managed rule group is not evaluated | Wrong vendor/name/version, wrong scope, scope-down excludes requests, or group not added to web ACL. | Inspect ManagedRuleGroupStatement configuration, WCUs, and logs. |
| UpdateWebACL rejected | Stale LockToken or missing permissions. | Call GetWebACL, retrieve the fresh LockToken, and verify IAM permissions. |
| CloudFront rejects web ACL | Wrong regional scope or Region used. | Use CLOUDFRONT scope, us-east-1 Region, and update distribution config. |
| No sampled requests appear | Sampling disabled, requests match no rules, or data protection settings. | Check VisibilityConfig and logs; do not rely on samples as a complete audit log. |
| Logs fail to reach destination | Wrong destination prefix, service-linked role permissions, or S3/KMS/Firehose policy. | Check logging configuration, IAM, bucket/key policies, and delivery status. |
| WCU exceeds capacity | Too many managed groups or complex statements. | Run CheckCapacity, audit WCUs, and remove redundant rules. |

## 17. Hands-On Lab: Protecting a Regional API with WAF

Objective: create a regional web ACL, add a managed rule group and a rate-based rule, attach it to a staging ALB, enable metrics/logging, and test for false positives.

### Step 1: Determine Scope and Resources

- Select the ALB's Region, e.g., ap-southeast-1.
- Identify the ALB ARN, listeners, target groups, and endpoints to protect.
- Confirm the ALB is not reachable from unapproved sources.
- Choose a default action matching the traffic model; for a public API, you can start with Allow and add blocking rules.

### Step 2: Create the Web ACL

Create a REGIONAL web ACL with DefaultAction Allow, enabling metrics and sampled requests for staging. Add AWSManagedRulesCommonRuleSet with a Count override for rules likely to affect upload endpoints.

### Step 3: Add a Rate-Based Rule

Create a rule limiting `/login` by IP. Start in Count mode and observe peak-hour traffic and shared NAT traffic. Switch to Block only after the threshold is validated.

### Step 4: Attach the Web ACL to the ALB

Use CloudFormation association or `aws wafv2 associate-web-acl`. Verify with `get-web-acl-for-resource` and confirm real requests hitting the ALB are evaluated.

### Step 5: Enable Logging and Metrics

Send logs to CloudWatch Logs or S3/Firehose with a destination matching the required prefix. Verify metrics for the web ACL and individual rules. Configure data protection/redaction for sensitive fields.

### Step 6: Test

- Send valid requests to login, search, and upload.
- Send test requests with SQLi/XSS patterns in the test environment.
- Send bursts of requests to test the rate-based rule.
- Inspect logs to identify terminating rules, labels, and actions.
- Switch false-positive rules to Count, and adjust scope-down or inspected components.
- Repeat testing before enabling Block.

### Step 7: Prepare for Operations

Store the CloudFormation template in the repository, require change reviews, configure alarms for elevated Block rates, document owners for each rule, and periodically review managed rule versions. Roll back using the approved template/configuration if legitimate traffic is blocked.

## 18. Misconceptions to Avoid

1. **Having WAF means the application is secure.** WAF only filters requests by rules; the application must still authenticate, authorize, and validate data.
2. **Managed Rules fit every application out of the box.** Managed groups must be tuned to actual endpoints and payloads.
3. **Count means the request is guaranteed to be Allowed.** Earlier or subsequent rules can still trigger a terminating action; the default action decides when no terminating action fires.
4. **Higher priority numbers run first.** Lower numerical priority values run first.
5. **Rate limits are exact quotas.** WAF enforces near the threshold, not as an exact transactional counter.
6. **X-Forwarded-For is always trustworthy.** Only trust headers controlled by a trusted proxy.
7. **WAF inspects the entire body.** WAF only receives the portion of the body within the resource's inspection limit.
8. **RedactedFields hides data in sampled requests.** Logging field redaction does not apply to sampling.
9. **All managed rule groups are free.** Certain advanced groups and Marketplace groups carry separate charges.
10. **A web ACL's scope can be changed after creation.** Scope must be chosen correctly up front; the wrong scope typically requires creating a new resource.
11. **A CloudFront web ACL resides in the user's Region.** WAF resources for CloudFront are managed in us-east-1.
12. **A Block rule placed first is always best.** Allow/Block rules terminate evaluation; ordering must reflect policy.
13. **Increasing WCUs just requires a quota increase.** Web ACLs have a fixed 5,000 WCU limit; above 1,500 WCUs can incur additional charges.
14. **WAF replaces account-level brute-force protection.** IP rate limiting must be combined with per-account controls and MFA.

## 19. Self-Check Questions

**1. In which Region does a regional web ACL protect an ALB?**

The web ACL must be in the same Region as the ALB. For CloudFront, WAF resources are managed in us-east-1.

**2. Between a rule with priority 5 and priority 20, which runs first?**

Priority 5 runs first because AWS WAF evaluates rules in ascending numerical order.

**3. What happens when a Count rule matches a request?**

WAF records the match and continues evaluating the next rule.

**4. Why can placing an Allow rule at the top of the list prevent subsequent Block rules from running?**

Allow is a terminating action, so WAF stops rule evaluation once a request matches.

**5. When should OverrideAction Count be used on a managed rule group?**

When you need to observe the impact of the entire group during testing without letting the group block requests yet.

**6. When should RuleActionOverrides be used?**

When only one or a few inner rules cause false positives and you need to override the action solely for those rules.

**7. Why can a rate-based rule by source IP affect multiple users?**

Multiple users can share a single public IP through NAT or a proxy.

**8. When is it safe to use forwarded IP?**

When requests pass through a trusted proxy that controls the forwarded IP header and strips forged client values.

**9. Does WAF inspect the entire body if it exceeds the inspection limit?**

No. WAF only receives the portion of the body forwarded by the resource within the configured limit.

**10. What is the purpose of a scope-down statement?**

It restricts which requests are evaluated by a rate-based rule or managed rule group, such as only the `/login` endpoint.

**11. What is the benefit of a static managed rule group version?**

It lets operators test and approve a version before changing the rules protecting production.

**12. Does field redaction in logging mask sampled requests?**

No. You must use data protection for sampled requests or disable sampling if sensitive data is present.

## 20. Production Operations Checklist

- [ ] Web ACL uses the correct scope and Region.
- [ ] Associated only with approved resources.
- [ ] Default action matches the access model.
- [ ] Rule priorities and terminating actions have been reviewed.
- [ ] Managed rule groups have been run in Count mode and tuned on representative traffic.
- [ ] Managed rule versions have a notification and upgrade process.
- [ ] Rate-based rules use thresholds and aggregation keys grounded in real traffic data.
- [ ] Forwarded IP is used only when proxies are trusted and control the header.
- [ ] Body inspection limits and oversize handling fit each endpoint.
- [ ] WCUs and costs have been estimated.
- [ ] CloudWatch metrics, WAF logging, and alarms are active.
- [ ] Logs/samples are protected from exposing secrets and PII.
- [ ] CloudFormation or IaC is the reviewed source of configuration.
- [ ] Rollback procedures and rule owners are documented.
- [ ] Regular reviews are scheduled for false positives, quotas, costs, and managed rule updates.

## References

- [Configuring protection in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl.html)
- [Resources that you can protect with AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html)
- [Associating or disassociating protection with an AWS resource](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-associating-aws-resource.html)
- [How AWS WAF handles rule and rule group actions](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-rule-actions.html)
- [Using match rule statements in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statements-match.html)
- [Aggregating rate-based rules in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-aggregation-options.html)
- [Using managed rule groups in AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-using-managed-rule-groups.html)
- [AWS Managed Rules rule groups list](https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-list.html)
- [Using versioned managed rule groups](https://docs.aws.amazon.com/waf/latest/developerguide/waf-managed-rule-groups-versioning.html)
- [Overriding rule group actions](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-rule-group-override-options.html)
- [Testing and tuning your AWS WAF protections](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-testing.html)
- [Web ACL capacity units (WCUs)](https://docs.aws.amazon.com/waf/latest/developerguide/aws-waf-capacity-units.html)
- [AWS WAF quotas](https://docs.aws.amazon.com/waf/latest/developerguide/limits.html)
- [Considerations for managing body inspection](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-setting-body-inspection-limit.html)
- [Configuring logging for a protection pack (web ACL)](https://docs.aws.amazon.com/waf/latest/developerguide/logging-management-configure.html)
- [AWS::WAFv2::WebACL CloudFormation resource](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-wafv2-webacl.html)
