# Routing Policies, Virtual Hostnames, and Session Persistence

In the **Application Load Balancing** chapter of the **CLOUD_PROVIDERS_ORACLE** module, this lesson combines three OCI Load Balancer capabilities: serving multiple domains, routing HTTP requests to the appropriate application group, and keeping requests from the same session on a single backend.

The running scenario is a store with a web frontend, an API, and an admin portal. These components share one load balancer while having different backend sets and session management requirements. The configuration must align with DNS, TLS, IAM, VCN networking, health checks, and monitoring for stable operations, automation, and cost control.

## 1. Objectives and Scope

After this lesson, learners will be able to:

- Distinguish the roles of virtual hostnames, routing policies, and session persistence.
- Write routing conditions with explicit path boundaries and ordering.
- Connect DNS records, hostname resources, and listener certificates.
- Choose between application-managed cookies and load-balancer-managed cookies.
- Test new sessions, existing sessions, mismatched hostnames, and failed backends.
- Plan configuration changes while tracking user impact.

This lesson applies to **OCI Load Balancer**, using the HTTP/HTTPS model and the **oci lb** command group. The examples do not assume these cookie features apply unchanged to OCI Network Load Balancer or TCP listeners.

The domains **shop.example.com** and **admin.example.com** are illustrative names. When practicing, use a lab domain you control along with matching DNS resolution and certificates.

## 2. Three Decisions Along the Request Path

| Capability | Primary decision | Example |
| --- | --- | --- |
| Virtual hostname | Which listener matches the request's hostname? | `shop.example.com` to `shop_https` |
| Routing policy | Which backend set receives the HTTP request? | `/api/orders` to `api_bs` |
| Session persistence | Which eligible backend continues receiving the session? | Cart session returns to `shop-a` |

Do not use cookies to replace application selection conditions. Nor should you treat an admin domain name as proof that the caller has been granted admin privileges.

~~~mermaid
flowchart TD
    Request["HTTPS request"] --> Host["Matching hostname and listener"]
    Host --> Shop["shop_https"]
    Host --> Admin["admin_https"]
    Shop --> Rules["Routing policy shop_routes"]
    Rules -->|"Matches /api or /api/"| Api["Backend set api_bs"]
    Rules -->|"No match"| Web["Default backend set shop_bs"]
    Admin --> AdminSet["Default backend set admin_bs"]
    Web --> Cookie["Check session and eligible backends"]
    Cookie --> A["shop-a"]
    Cookie --> B["shop-b"]
~~~

The diagram is a logical breakdown for design and troubleshooting, not a description of the service's internal processes. Final proof remains requests arriving at the right application and being handled properly.

## 3. Virtual Hostnames: Multiple Applications on One Address

### DNS Records, Hostname Resources, and Certificates

These three objects solve different tasks:

| Object | Responsibility |
| --- | --- |
| DNS record | Helps clients find the load balancer address from the domain name |
| Virtual hostname resource | Declares a hostname or pattern to bind to a listener |
| TLS certificate | Lets clients verify the identity of the HTTPS service |

Creating a hostname resource in Load Balancer does not automatically create a DNS record. Multiple domains can point to the same load balancer address, but each still requires proper DNS resolution setup. OCI virtual hostnames support HTTP and HTTPS listeners. [Source: Virtual Hostnames](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/hostname_management.htm).

Mapping example:

~~~text
DNS:
  shop.example.com  → load balancer address
  admin.example.com → same load balancer address

Hostname resources:
  shop_host  = shop.example.com
  admin_host = admin.example.com

Listeners:
  shop_https  :443 → shop_host  → shop_bs, with shop_routes
  admin_https :443 → admin_host → admin_bs
~~~

The name **shop_host** is the configuration resource name, while **shop.example.com** is the hostname clients use. When attaching to a listener, select the exact resource created.

With HTTPS, clients typically send SNI during the TLS handshake and then send the hostname in the HTTP request. Test using the application's real URL to exercise both TLS identity and routing. Changing only the HTTP Host header in a direct-to-IP call does not fully replace testing HTTPS domain names.

### Exact Match, Wildcards, and the Default Path

OCI prioritizes exact matches first, then longest asterisk-prefixed wildcard patterns, then longest asterisk-suffixed patterns. Virtual hostnames are not regular expressions. When no name matches, the service still has a port default-listener mechanism: a listener without a bound hostname is the default; if all listeners bind hostnames, the first hostname configured on that port serves as the default. [Source: Defining Hostnaming](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/hostname_management.htm).

For example, **shop.example.com** and ***.example.com** can coexist to serve different needs. A listener wildcard rule does not automatically provision a wildcard certificate and does not change TLS client hostname verification rules.

Design an intentional default listener for the port in use. In the lab, that listener can use **reject_bs**, a backend set that only returns a response declining unknown hostnames. Backends in this group still need a functioning dedicated health check endpoint, such as `/ready` returning 200 while application requests return 404.

Do not assume every unlisted hostname is dropped by the service before reaching the application. With HTTPS, unknown names can also be rejected by the client during certificate verification before any HTTP response occurs.

## 4. Routing Policy: Choosing a Backend Set per Request

### Structure and Ordering

A routing policy is an ordered list of rules attached to an HTTP or HTTPS listener. Each rule has a condition and an action forwarding to an existing backend set. The service stops at the first matching rule; when no rule matches, the request goes to the listener's default backend set. [Source: Routing Policies](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/routing-policy_management.htm).

Distinguish two policy types:

- **Routing policy** selects the application group, such as `shop_bs` or `api_bs`.
- **Load balancing policy** on the backend set chooses how to distribute among servers in the group.

A rule forwarding to `api_bs` does not specify the load split ratio between `api-a` and `api-b`. Nor does it automatically create health checks, add backends, or open network permissions.

### Conditions with Clear Boundaries

Condition syntax includes operators such as **eq**, **sw**, and combinators **any(...)**, **all(...)**. String comparisons are case-sensitive by default; **(i '...')** is used when intentionally comparing case-insensitively. [Source: Routing Policy Language](https://docs.oracle.com/en-us/iaas/Content/Balance/Concepts/routing_policy_conditions.htm).

Example for the API group:

~~~text
any(
  http.request.url.path eq '/api',
  http.request.url.path sw '/api/'
)
~~~

This expression distinguishes a path segment boundary:

| Path | Result of example condition |
| --- | --- |
| `/api` | Matches |
| `/api/` | Matches |
| `/api/orders` | Matches |
| `/apiv2/orders` | Does not match |
| `/API/orders` | Does not match with case-sensitive config |
| `/cart` | Does not match |

If you only use the prefix **/api**, the string **/apiv2/orders** would also match. Write conditions matching the URL contract, and test near-miss inputs as well.

Example of a condition combining hostname and path:

~~~text
all(
  http.request.headers[(i 'host')] eq (i 'shop.example.com'),
  http.request.url.path sw '/api/'
)
~~~

This pattern handles requests whose Host value matches the expression. If clients might send a hostname with a port, add corresponding test cases and conditions. For labs that already separate listeners by virtual hostname, the `/api` rule does not need to repeat the Host condition.

Path and query are distinct fields: **/api/orders?status=open** still has path **/api/orders**. If routing by query or header is needed, clearly document the business rationale and accepted values.

### Order Matters More Than Perceived Specificity

Suppose a system has two rules:

~~~text
1. Path starts with /api/         → api_bs
2. Path starts with /api/reports/ → reports_bs
~~~

A request to **/api/reports/monthly** matches the first rule, so the second rule is never reached. To send that path to the reports group, place its rule ahead of the broader rule.

Do not assume the system automatically chooses the rule with the longest path the way some virtual hostname patterns work. These are two different selection mechanisms.

Routing conditions based on client-supplied headers, query strings, or cookies also do not authenticate the caller. For example, a header like **X-Environment: preview** should only serve as an environment selector when overall access controls are properly designed.

### Illustrative JSON Configuration

The main lab policy has one rule, and the listener's default backend set is `shop_bs`:

~~~json
{
  "name": "shop_routes",
  "conditionLanguageVersion": "V1",
  "rules": [
    {
      "name": "route_api",
      "condition": "any(http.request.url.path eq '/api', http.request.url.path sw '/api/')",
      "actions": [
        {
          "name": "FORWARD_TO_BACKENDSET",
          "backendSetName": "api_bs"
        }
      ]
    }
  ]
}
~~~

This is a policy representation example, not a full load balancer creation payload. In the OCI CLI, **--rules** takes the list inside the `rules` field; `name` and `condition-language-version` are passed separately. [Source: OCI CLI routing-policy create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/routing-policy/create.html).

The forwarding action in the example does not automatically strip the **/api** prefix. The backend must handle the incoming path; if rewriting is needed, design and test that mechanism separately. Likewise, a routing rule is not a browser redirect response.

## 5. Session Persistence: Keeping a Session on One Backend

### When Is It Needed and What Data Is Preserved?

A legacy store might keep shopping carts in each server's RAM. If the next request lands on another server, the cart may vanish. Session persistence helps requests in a session return to the right backend, but it does not copy the cart to other servers.

Distinguish these concepts:

| Concept | Role |
| --- | --- |
| Application session or auth cookie | Identifies the session per application logic |
| Load balancer persistence cookie or token | Assists in selecting a backend for the session |
| Session state store | Stores cart, login data, or business state |

The presence of a routing cookie does not prove a user is logged in. A session routed to another healthy backend also does not prove that backend holds prior session data.

### Application Cookie Stickiness

In this mode, configure the cookie name issued by the application. For example, the backend returns:

~~~http
Set-Cookie: APPSESSID=opaque-application-value; Path=/; Secure; HttpOnly
~~~

Persistence activates only when the backend response includes `Set-Cookie` with the configured name; if no matching cookie is present yet, requests follow the normal distribution policy. An asterisk can match any cookie, though specifying an exact name makes intent clearer. [Source: Application Session Persistence Configuration](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/load_balancer/models/oci.load_balancer.models.SessionPersistenceConfigurationDetails.html).

Example configuration at the backend set level:

~~~json
{
  "cookieName": "APPSESSID",
  "disableFallback": false
}
~~~

If a real Java application uses a different name such as `JSESSIONID`, configure the cookie actually emitted rather than guessing from the framework name. Also inspect `Path`, `Domain`, and client policy for that cookie.

Routing metadata generated by the load balancer for persistence should be treated as opaque data. Applications should not parse it to infer user permissions or identity.

### Load Balancer Cookie Stickiness

When the application does not issue a suitable cookie or you want to decouple routing mechanics, the load balancer can insert a cookie. Application cookie and load balancer cookie modes are mutually exclusive within the same backend set. [Source: Load Balancer Cookie Configuration](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/load_balancer/models/oci.load_balancer.models.LBCookieSessionPersistenceConfigurationDetails.html).

Illustrative configuration for `shop_bs`:

~~~json
{
  "cookieName": "X-Oracle-OCI-ShopRoute",
  "disableFallback": false,
  "path": "/",
  "maxAgeInSeconds": 1800,
  "isSecure": true,
  "isHttpOnly": true
}
~~~

Omit `Domain` in the example so the cookie is scoped to the host that sent the response. `Max-Age` 1800 seconds is an illustrative lab choice, not an OCI default or recommended session lifetime for every application.

### Cookie Scope and Attributes

| Attribute | Impact to check |
| --- | --- |
| Name | Avoid colliding with cookies issued by the application itself |
| Domain | Determines which hosts the client sends the cookie back to |
| Path | Determines which URL paths receive the cookie |
| Max-Age | Cookie lifetime; does not mean session data stays alive on the server that long |
| Secure | Client sends the cookie only over secure protocols |
| HttpOnly | Restricts JavaScript from accessing the cookie via client-side APIs |

Do not set `Domain` broadly to `example.com` just because multiple domains share one load balancer. In the example, `shop` and `admin` are two different applications; the cookie holding `shop` sessions must be scoped appropriately to `shop`.

OCI does not allow attaching a backend set with `Secure=true` cookie persistence to an HTTP listener. Therefore, the configuration in this example is used with HTTPS. Options and behavior for `Domain`, `Path`, `Secure`, and `HttpOnly` are described in [Load Balancer Session Persistence](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/sessionpersistence.htm).

If you change `Path` to **/cart**, that cookie will not be sent for all shop paths. Evaluate whether pages such as `/checkout` also need the same session.

## 6. Interaction Among Routing, Persistence, and Availability

### Group Selection Rules Must Still Be Respected

A client holding a `shop_bs` cookie may still send **/api/orders**. The expected outcome is that the request goes to `api_bs` per the routing policy, rather than going back to `shop-a` simply because a cookie was present.

Verify cookies by target group, name, scope, and actual persistence settings. Oracle documentation notes that path routing rules take precedence and cookies invalid for the target are ignored. [Source: LB Cookie Session Persistence Configuration](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/load_balancer/models/oci.load_balancer.models.LBCookieSessionPersistenceConfigurationDetails.html).

When changing a routing policy, clients carrying older cookies are a separate test group. Testing only in an incognito browser can miss bugs affecting existing sessions.

### Fallback When a Session's Backend Becomes Unavailable

By default, fallback to another backend is permitted. If **disableFallback=true** is configured, requests for that session can receive HTTP 502 when the pinned backend is unusable. Sessions continuing to send cookies to an unavailable backend can continue failing. [Source: Common Load Balancer Errors](https://docs.oracle.com/en-us/iaas/Content/Balance/Troubleshooting/common_load_balancer_errors.htm).

| Option | When old backend fails | What the application still must solve |
| --- | --- | --- |
| `disableFallback=false` | Can fail over to another backend | Recover session, read shared state, or prompt re-login |
| `disableFallback=true` | Does not move session to another backend via fallback | Accept error, plan backend recovery, and handle cookies/sessions |

Allowing fallback maintains service continuity but does not preserve RAM-only data. Disabling fallback also does not turn machine memory into a durable data store.

Choose the setting based on the business consequence of switching servers. If a transaction might be retried after failure, the application needs proper idempotency/deduplication rules independent of stickiness.

### Drain Does Not Cut All Existing Sessions

A backend in drain state is still considered available for existing persisted sessions; new requests not belonging to those sessions are not routed to the draining server. [Source: Session Persistence — Fallback](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/sessionpersistence.htm).

Therefore, during maintenance:

1. Enable drain and observe active connections and sessions.
2. Define wait-completion criteria based on the application.
3. Handle long-lived sessions per the deployment plan.
4. Stop the service once ready for maintenance.
5. Restore and verify before returning the machine to service.

Overly long cookie lifetimes can prolong session migration. Do not treat drain as clearing all sessions or as proof that the server is no longer handling requests.

## 7. Designing a Multi-Application Lab

### Prepared Resources

Use a lab OCI Load Balancer reachable from the test machine, backend sets with healthy backends, and identifying endpoints:

| Backend set | Contract used for testing |
| --- | --- |
| `shop_bs` | `/cart` returns `service=shop` and `node=shop-a` or `shop-b` |
| `api_bs` | `/api/orders` returns `service=api` along with node name |
| `admin_bs` | `/` returns simulated admin page |
| `reject_bs` | `/ready` returns 200, application requests return a reject or not-found response |

No real customer data or real admin accounts are needed. Endpoints must actually be deployed on backends; the load balancer does not generate this content.

Prepare client-trusted certificates covering `shop` and `admin`, along with corresponding lab DNS. If using a private load balancer, the test machine must have network reachability to the private IP.

### Permissions and Networking

The configuring identity needs Load Balancer management permissions in the right compartment. When modifying DNS, certificates, or logs, corresponding permissions for those resources are also required. Do not grant tenancy-wide permissions just to avoid identifying missing resource permissions.

Network paths include client to the load balancer HTTPS port, load balancer to application ports, and health checks to backends. Check NSGs, security lists, routes, and OS firewalls together.

Hostnames and paths do not create authorization boundaries between users. The admin site still needs authentication and permission checks at the application layer or designed protection mechanisms.

### Configuring in Dependency Order

Perform in the Console to clearly observe each link:

1. Confirm backends for `shop_bs`, `api_bs`, `admin_bs`, and `reject_bs` are healthy.
2. Create hostname resources `shop_host` and `admin_host`.
3. Create `shop_routes` following the `/api` rule template in this lesson.
4. Configure `shop_https` on 443 with `shop_host`, default `shop_bs`, and `shop_routes`.
5. Configure `admin_https` on 443 with `admin_host` and default `admin_bs`.
6. Prepare the default listener without a hostname per the design, using `reject_bs`.
7. Attach the appropriate certificates and verify HTTPS settings on each listener.
8. Enable load balancer cookie persistence on `shop_bs` per the illustrative configuration.
9. Leave `api_bs` and `admin_bs` according to their defined session requirements; the lab does not need the same cookie on every group.
10. Verify DNS, then run the request matrix.

Wait for each change's work request to finish before executing dependent changes. Creating a policy successfully does not prove the policy is attached to a listener.

## 8. Illustrating Automation and Reading Back Configuration

The commands below are practice material, not commands already run on a tenancy. Replace sample variables before running OCI CLI in PowerShell.

### Create Two Hostname Resources

~~~powershell
$Region = 'REPLACE_WITH_REGION'
$LoadBalancerId = 'REPLACE_WITH_LOAD_BALANCER_OCID'
$Hostnames = @(
    @{ Name = 'shop_host'; Hostname = 'shop.example.com' },
    @{ Name = 'admin_host'; Hostname = 'admin.example.com' }
)

foreach ($HostnameItem in $Hostnames) {
    $CreateArgs = @(
        'lb', 'hostname', 'create',
        '--region', $Region,
        '--load-balancer-id', $LoadBalancerId,
        '--name', $HostnameItem.Name,
        '--hostname', $HostnameItem.Hostname,
        '--wait-for-state', 'SUCCEEDED',
        '--max-wait-seconds', '300'
    )
    oci @CreateArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Check the work request for hostname $($HostnameItem.Name)"
    }
}
~~~

Only run creation if these resources do not already exist. The hostname resource is added to the load balancer; it still needs to be bound to a listener and have DNS configured. [OCI CLI hostname create reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/hostname/create.html).

If it times out, inspect the work request and current state before retrying. Do not assume a timeout means the service did not create the resource.

### Read Back Routing Policy

~~~powershell
$GetRoutingArgs = @(
    'lb', 'routing-policy', 'get',
    '--region', $Region,
    '--load-balancer-id', $LoadBalancerId,
    '--routing-policy-name', 'shop_routes'
)
oci @GetRoutingArgs
~~~

Verify conditions, rule order, and `backendSetName` against the design. Then verify in the Console that the listener actually references `shop_routes`. [OCI CLI routing-policy get reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/routing-policy/get.html).

For automation pipelines, store the desired configuration in the project's configuration management system, read current state, and control concurrent changes. Avoid submitting an update with an incomplete list that wipes out configurations used by another application.

## 9. Testing Routing and Cookies

### Required Test Matrix

| Host | Path | Session | Expected routing outcome in lab |
| --- | --- | --- | --- |
| `shop.example.com` | `/cart` | New | `shop_bs`, receives persistence cookie |
| `shop.example.com` | `/cart` | Has cookie | Continues to session's eligible backend if still available |
| `shop.example.com` | `/api` | Any | `api_bs` |
| `shop.example.com` | `/api/orders` | Has shop cookie | `api_bs` |
| `shop.example.com` | `/apiv2/orders` | Any | Default `shop_bs` per active rule |
| `admin.example.com` | `/` | New | `admin_bs` |
| Undeclared host | `/` | Any | Default path if request passes TLS |
| `shop.example.com` | `/cart` | Old cookie, backend failed | Behavior per `disableFallback` setting |

The table specifies the **target group**, not claiming every URL returns HTTP 200. For example, `shop_bs` may return 404 for `/apiv2/orders` because the application does not serve that path.

### Testing HTTPS Before Changing Shared DNS

You can run curl on a test machine with reachability to the load balancer:

~~~powershell
$LoadBalancerIp = 'REPLACE_WITH_LOAD_BALANCER_IP'
$ShopResolve = 'shop.example.com:443:{0}' -f $LoadBalancerIp

curl.exe --http1.1 --resolve $ShopResolve --silent --show-error --dump-header - 'https://shop.example.com/api/orders'
~~~

The `--resolve` option supplies the host/port-to-IP mapping for the call while the URL keeps the hostname under test. The certificate must still be valid and trusted by the client. Use `curl.exe` to invoke the actual curl executable in PowerShell. [Source: curl --resolve](https://curl.se/docs/manpage.html#--resolve).

This command tests a single request without keeping cookies across runs. When testing the default listener at the HTTP layer, you can keep valid SNI for `shop` while changing `Host`:

~~~powershell
curl.exe --http1.1 --resolve $ShopResolve --header 'Host: unknown.example.com' --silent --show-error --dump-header - 'https://shop.example.com/'
~~~

This is an intentional test for a mismatched `Host` after the TLS step. It does not prove a certificate will be valid when users visit `https://unknown.example.com/`.

### Testing Sessions with a Cookie Container

Once lab DNS works, use a dedicated cookie container for client A:

~~~powershell
$ShopUri = 'https://shop.example.com/cart'
$SessionA = New-Object Microsoft.PowerShell.Commands.WebRequestSession

1..5 | ForEach-Object {
    $Response = Invoke-WebRequest -Uri $ShopUri -WebSession $SessionA -UseBasicParsing
    [pscustomobject]@{
        StatusCode = $Response.StatusCode
        Body = $Response.Content
    }
}

$SessionA.Cookies.GetCookies([uri]$ShopUri) |
    Select-Object Name, Domain, Path, Secure, HttpOnly
~~~

Verify the same node via response bodies and access logs. The cookie table only prints attributes; do not print cookie values into reports.

Create another `WebRequestSession` for client B to test an independent session. Two sessions may happen to pick the same backend; that alone does not prove misconfiguration.

With application cookie mode, call the exact action that makes the application issue `APPSESSID` before testing stickiness. Sending an anonymous request that does not issue a cookie and expecting it to stay on the same server is an incomplete test.

### Controlled Fault Testing

Using lab backends:

1. Start a session and record which node handles it.
2. Make that node fail its health check or stop its service as planned.
3. Wait for relevant status updates and call again using the same cookie container.
4. Compare the outcome against `disableFallback`.
5. Check business state on the new node if failed over.
6. Restore the backend and start a new session to compare.

When testing `disableFallback=true`, record the error code and logs rather than concluding a generic network failure. Never alter a production system's configuration just to observe an HTTP status code.

## 10. Troubleshooting Common Errors

| Symptom | Investigation direction |
| --- | --- |
| Both `shop` and `admin` return the same app | DNS/IP, hostname resources, listener bindings, and default listener |
| HTTPS fails before seeing content | Domain in URL, SNI, certificate, and trust chain |
| `/api/orders` goes to `shop` | Rule not attached, condition mismatch, or listener using another policy |
| Specific rule never runs | Broader rule placed ahead in rule order |
| Backend receives `/api/...` then returns 404 | Path contract and rewrite assumptions |
| Refresh changes node despite application persistence | Whether backend emits `Set-Cookie`; whether client stores and resends it |
| Only some pages lose stickiness | `Domain`, `Path`, `Secure`, redirects, and cookie scope |
| Has `shop` cookie yet API calls wrong app | Routing/backend set bindings and per-target-group cookie settings |
| Only old clients get 502 after a node fails | Stale persistence cookie and `disableFallback` |
| Drained yet server still gets requests | Existing persisted sessions and open connections |

During investigation, capture UTC timestamps, host, path, observed listener or target group, and handling node. Correlate load balancer logs with application logs using a correlation ID if supported by the application.

You do not need to log full `Cookie`, `Authorization`, or session payloads to know which server handled a request. Use synthetic node-identifying values and redact sensitive data in evidence.

If cookies work in a test tool but fail in a browser, check both browser cookie policies and actual browser redirect flows. Do not edit routing rules before confirming whether the cookie is even being sent.

## 11. Operations, Changes, and Architectural Choices

### Changing Routing While Sessions Exist

Before applying changes:

- Record the current policy, listener bindings, and persistence settings.
- Confirm the new backend set is healthy and handles the right paths.
- Prepare test cases for both new sessions and old cookies.
- Identify which changes are reversible and what session data needs handling.

After applying, monitor error rates, latency, node distribution, and responses on critical paths. If rollback is needed, restore the exact binding configuration and retest with existing clients as well.

Do not assume rolling back a policy revives lost RAM data on a backend or undoes user transactions already committed.

### Stateless, Shared Session Store, and Stickiness

Applications with shared session state are typically more resilient when backends change. They still require designing session expiration, store access permissions, failure behavior, and recovery capabilities.

Stickiness can reduce cache overhead or support a legacy application, but you must have an answer for when the session-holding server is lost. If the session store resides in Oracle Database or another service, include that dependency in availability and capacity checks.

Do not pick `IP_HASH` assuming every IP always represents a single user. NAT can aggregate many users behind one IP, while mobile clients can change IPs.

### Sharing a Load Balancer and Controlling Cost

Sharing an address and load balancer across multiple applications can reduce the number of resources to operate. In return, applications share capacity, blast radius on configuration edits, and change windows.

Deciding whether to share or separate must consider:

- Total traffic and standby capacity.
- Required independence between operations teams.
- TLS, access, and logging policies.
- Consequences if default settings or rules are misconfigured.
- Load balancer, backend, and monitoring costs in the actual environment.

Do not assume hostname count or rule count automatically creates a fixed standalone fee. Check actual resources and pricing terms before budgeting.

## 12. Consolidation Lab Exercise

Complete in the lab environment:

1. Diagram the mapping across DNS, virtual hostnames, listeners, routing policies, and backend sets.
2. Run the full host/path matrix, including `/api`, `/api/orders`, and `/apiv2/orders`.
3. Confirm an unknown hostname follows the designed default path.
4. Compare a client that drops cookies with a client using a cookie container.
5. Switch `shop_bs` between the two persistence modes, enabling only one mode at a time and creating a fresh test session.
6. Compare fallback enabled vs. disabled when a session's backend becomes unavailable.
7. Test drain and explain why an existing session can still reach that server.
8. Propose a way to preserve the shopping cart when failing over to another backend.

Deliverables: configuration map, rule order, cookie scope, evidence of handling nodes, and failure behavior. Revert experimental settings modified for testing and clean up lab resources only after verifying no dependencies remain.

A complete design must answer three questions: which listener does this domain hit, which group does this request go to, and when the session-holding backend becomes unready, how does the user continue?
