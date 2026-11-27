# UTL_HTTP, Network ACLs, Wallets, and Calling External Services

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Distributed Integration  
> **Goal:** Call HTTP/HTTPS from PL/SQL in a controlled manner; configure network ACLs for hosts and ports; use Oracle Wallet for TLS verification and client certificates; distinguish database privileges, wallet privileges, and filesystem permissions; handle requests/responses, timeouts, errors, and credentials; design secure, monitorable, and operable outbound integrations.

## 1. The Big Picture

`UTL_HTTP` is a PL/SQL package enabling Oracle Database to send HTTP requests to external services. Applications can use this package to call REST APIs, webhooks, authentication services, or internal endpoints.

A successful HTTPS request requires several independent conditions:

1. The PL/SQL session can execute `UTL_HTTP`.
2. The executing principal holds appropriate network ACL privileges for the hostname and port.
3. The database server can resolve DNS and open a TCP connection to the target or proxy.
4. The OS account running Oracle Database can read the wallet if a wallet is used.
5. The wallet contains the appropriate trust chain and/or required client credentials.
6. The TLS handshake succeeds with a valid hostname and certificate.
7. The HTTP endpoint accepts the method, headers, credentials, and payload.
8. PL/SQL properly handles responses, timeouts, status codes, and errors.

You can visualize the flow as follows:

~~~text
PL/SQL application
       |
       v
    UTL_HTTP
       |
       +---- Network ACL: host / port / principal
       |
       +---- Oracle Wallet: trust / client cert / credentials
       |
       v
Oracle Database server process
       |
       +---- OS permission to read wallet
       |
       +---- DNS / firewall / proxy / route
       |
       v
External HTTP(S) service
       |
       v
HTTP status + headers + response body
~~~

Network ACLs control which database users can connect to which hosts. Wallets support TLS trust and certain certificate/password authentication mechanisms. Filesystem permissions decide whether the Oracle server process can read the wallet. These three layers do not substitute for one another.

## 2. What Does UTL_HTTP Do?

`UTL_HTTP` provides APIs to create requests, set headers, send bodies, receive responses, and read data.

Commonly used APIs:

| API | Purpose |
|---|---|
| `SET_WALLET` | Selects the wallet to use for TLS or credentials |
| `SET_TRANSFER_TIMEOUT` | Sets timeout for data transfer operations |
| `SET_DETAILED_EXCP_SUPPORT` | Enables detailed exception reporting |
| `BEGIN_REQUEST` | Creates an HTTP request |
| `SET_HEADER` | Sets a request header |
| `WRITE_TEXT` / `WRITE_RAW` | Sends the request body |
| `GET_RESPONSE` | Sends the request and receives the response |
| `GET_HEADER_COUNT` / `GET_HEADER` | Reads response headers |
| `READ_TEXT` / `READ_RAW` | Reads the response body |
| `END_RESPONSE` | Closes the response and releases resources |
| `SET_PROXY` | Configures an HTTP proxy when needed |
| `SET_RESPONSE_ERROR_CHECK` | Controls handling of HTTP error statuses |

You can use the utility function `UTL_HTTP.REQUEST` for simple requests, but `BEGIN_REQUEST`/`GET_RESPONSE` is better suited when you need headers, bodies, status codes, timeouts, and detailed error handling.

### 2.1. HTTP Status Codes vs. Oracle Exceptions

A request may connect and receive a successful HTTP-level response where the service returns:

- 400 Bad Request.
- 401 Unauthorized.
- 403 Forbidden.
- 404 Not Found.
- 429 Too Many Requests.
- 500 Internal Server Error.
- 503 Service Unavailable.

These are HTTP status codes. They do not necessarily raise an Oracle exception. Applications must read `STATUS_CODE` and `REASON_PHRASE` to make business decisions.

Conversely, `ORA-24247` or `ORA-29024` are errors occurring before or during network/TLS establishment, where no HTTP response may exist.

### 2.2. UTL_HTTP Is Not an Application Gateway

`UTL_HTTP` is an API for issuing HTTP calls from the database. It does not inherently provide full API gateway or integration platform features:

- Does not automatically manage business OAuth token lifecycles.
- Does not automatically guarantee safe retries.
- Does not automatically guarantee exactly-once delivery.
- Does not automatically manage per-service circuit breakers.
- Does not replace queues/message brokers.
- Does not automatically validate response payload correctness.

Designs must add timeouts, retry policies, idempotency, logging, credential management, and resource limits.

## 3. Network ACLs: Permitting Connections to Hosts

Oracle Network Access Control Lists (network ACLs) define which principals may access network endpoints. With `UTL_HTTP`, evaluate access to hosts and ports.

Since Oracle Database 12c, the standard management approach is appending an ACE (Access Control Entry) via `DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE`. Legacy XML ACL APIs like `CREATE_ACL`, `ADD_PRIVILEGE`, and `ASSIGN_ACL` belong to an older/deprecated model in newer releases; use APIs appropriate to your running release.

### 3.1. The Connect Privilege

Example allowing schema `APP_SCHEMA` to connect to `api.example.com` on HTTPS port 443:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(
        host       => 'api.example.com',
        lower_port => 443,
        upper_port => 443,
        ace        => xs$ace_type(
            privilege_list => xs$name_list('connect'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

Meaning:

- `HOST` is the target hostname.
- `LOWER_PORT` and `UPPER_PORT` restrict permitted ports.
- `PRIVILEGE_LIST` holds network privileges.
- `PRINCIPAL_NAME` is the granted database user.
- `PRINCIPAL_TYPE` identifies the principal type.

Restricting exact hostnames and ports minimizes outbound exposure. If only HTTPS is needed, never grant a wide port range from 1 to 65535.

### 3.2. The Resolve Privilege for DNS

When using hostnames, the database must resolve names. `resolve` can be granted separately:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_HOST_ACE(
        host => 'api.example.com',
        ace  => xs$ace_type(
            privilege_list => xs$name_list('resolve'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

The `resolve` privilege is not bound to a port range. It permits the principal to resolve the hostname per ACL rules.

In many configurations, `connect` is the primary privilege for opening a network connection; `resolve` is needed when the flow uses DNS hostnames. Grant the right privileges per release and how endpoints are resolved. Do not grant `resolve` for all hosts when only a specific hostname is needed.

### 3.3. Grant by Specific Host

Prefer:

~~~text
api.example.com
payments.internal.example
identity.example.net
~~~

Avoid broad wildcards unless genuinely required:

~~~text
*
*.example.com
~~~

Wildcards can open access to far more systems than intended. If an application has a bug or is compromised, the wider the allowed host scope, the greater the outbound risk.

### 3.4. ACLs Are Not Firewalls

Network ACLs are controls at the Oracle Database layer. They do not:

- Open firewalls or security groups.
- Create network routes.
- Grant OS DNS resolver permissions.
- Configure proxies.
- Allow OS accounts to read wallets.
- Guarantee the endpoint is up.

The database host still needs appropriate egress firewall rules, DNS, routing, and proxy policies. Enforce allowlists in both Oracle ACLs and network firewalls.

## 4. Inspecting Network ACLs

### 4.1. Viewing Host ACEs

DBAs can view current ACEs:

~~~sql
SELECT host,
       lower_port,
       upper_port,
       ace_order,
       grant_type,
       principal,
       privilege,
       start_date,
       end_date
FROM dba_host_aces
ORDER BY host, lower_port, principal, privilege;
~~~

Use the view matching your privileges, such as `USER_HOST_ACES` or `ALL_HOST_ACES` if supported and granted.

Check:

- Is the host an exact FQDN?
- Are ports granted too broadly?
- Is the principal the executing schema?
- Are privileges correctly `connect`/`resolve`?
- Do grants have expiration dates?
- Are there deny ACEs or ACE ordering effects?

### 4.2. Viewing Wallet ACEs

~~~sql
SELECT wallet_path,
       ace_order,
       grant_type,
       principal,
       privilege,
       start_date,
       end_date
FROM dba_wallet_aces
ORDER BY wallet_path, principal, privilege;
~~~

If the application uses a client certificate or password in a wallet, verify the exact wallet path and principal.

### 4.3. Revoking ACEs

When an endpoint no longer needs access, DBAs can use `DBMS_NETWORK_ACL_ADMIN.REMOVE_HOST_ACE` or `REMOVE_WALLET_ACE` with matching ACE details. Verify syntax for your release and re-check dictionary views after revocation.

Do not delete an entire host's ACL if other applications still depend on it. Revoke only the specific ACE/principal/privilege.

### 4.4. Error ORA-24247

`ORA-24247: network access denied by access control list (ACL)` usually indicates the executing principal lacks required network privileges for the host/port.

Investigation workflow:

1. Identify the database user and PL/SQL call stack.
2. Identify the actual hostname/port the request is connecting to.
3. Check whether the request goes through a proxy or redirect.
4. Query `DBA_HOST_ACES`.
5. Verify privileges granted to the appropriate principal.
6. Add the minimal required ACE.
7. Retest using the same account and execution context.

Never solve it by granting privileges to `PUBLIC` or wildcard hosts.

## 5. Which Principal Needs the ACL When Called from a Package?

When `UTL_HTTP` is called directly in an anonymous block, the principal is typically the session's executing user.

When `UTL_HTTP` resides inside a stored PL/SQL unit, consider `AUTHID`:

- `AUTHID DEFINER`: code executes under the owner's privileges in definer-rights context.
- `AUTHID CURRENT_USER`: code executes under the invoker's privileges per invoker-rights rules.

Therefore, which schema needs the ACE depends on the execution context. Never assume the application login user is always the principal checked when calls originate inside a definer-rights package.

Package example:

~~~sql
CREATE OR REPLACE PACKAGE api_owner.external_api
AUTHID DEFINER
AS
    PROCEDURE check_service;
END external_api;
/
~~~

If code inside the package performs network calls under definer rights, evaluate `API_OWNER`'s network privileges. If using invoker rights, check the invoker's privileges. Test with the actual application user and production call path.

Do not grant ACEs to every user just to silence errors in a package. Explicitly document `AUTHID` and principal in the design.

## 6. Oracle Wallet and HTTPS

HTTPS uses TLS to protect data in transit and verify server identity. An Oracle Wallet can store:

- Trusted root CA certificates.
- Intermediate CA certificates.
- User/client certificates.
- Corresponding private keys.
- Credentials/passwords for supported features.

For HTTPS server authentication, `UTL_HTTP` uses the wallet to verify the certificate chain against configured trust anchors.

For mutual TLS (mTLS), the client must also present a certificate and prove private key possession when requested by the server.

### 6.1. Trust Chain

Certificate chain example:

~~~text
API server certificate
       |
       v
Intermediate CA
       |
       v
Root CA
~~~

The wallet needs the appropriate trust anchor and necessary intermediate certificates depending on how the server serves the chain. Missing CAs or expired certificates can cause the TLS handshake to fail.

The server certificate must also match the hostname the application calls, typically via Subject Alternative Name (SAN). A valid, unexpired certificate with a mismatched SAN can still be rejected.

### 6.2. Creating a Wallet

Example creating an auto-login wallet on the database server:

~~~bash
orapki wallet create \
  -wallet /u01/app/oracle/wallets/api \
  -auto_login
~~~

Run the command on a host with Oracle Wallet tooling following your organization's security procedures. Entering a wallet password may be required depending on options.

Add a trusted certificate:

~~~bash
orapki wallet add \
  -wallet /u01/app/oracle/wallets/api \
  -trusted_cert \
  -cert root-ca.pem
~~~

If the chain requires intermediate CAs, add the corresponding certificates in order following approved PKI procedures.

Display wallet contents:

~~~bash
orapki wallet display \
  -wallet /u01/app/oracle/wallets/api
~~~

Never grab certificates arbitrarily from unverified sources. Verify certificate fingerprints/issuers and trusted issuing authorities.

### 6.3. Auto-Login Wallets

A wallet may contain:

- `ewallet.p12`: password-protected wallet.
- `cwallet.sso`: auto-login wallet used by Oracle to open the wallet per configuration.

Auto-login avoids embedding wallet passwords in PL/SQL code, making file read permissions critical. Any OS principal able to read an auto-login wallet may be able to use its contents according to those file permissions.

Protect the wallet folder and files, restrict owner/group, back up the wallet securely, and establish a certificate/key rotation procedure.

### 6.4. OS Permissions on the Wallet

The wallet path is a database-server-side path. The OS account running Oracle Database must have read permission on wallet files and traverse permissions on parent directories.

Verification example on Linux:

~~~bash
ls -ld /u01/app/oracle/wallets/api
ls -l /u01/app/oracle/wallets/api
namei -l /u01/app/oracle/wallets/api
~~~

Never use `chmod 777`. Restrict filesystem permissions to the necessary account/group. On Windows, check NTFS ACLs for the Oracle Database service account.

### 6.5. Setting the Wallet in UTL_HTTP

Example:

~~~sql
BEGIN
    UTL_HTTP.SET_WALLET(
        path     => 'file:/u01/app/oracle/wallets/api',
        password => NULL
    );
END;
/
~~~

For password-protected wallets, supply the password through an organization-approved secret management mechanism; never hardcode passwords in package source or shared scripts.

The path must point to the server-side wallet directory using the `file:` prefix per `UTL_HTTP` syntax. It is not a path on the machine running SQL Developer or `expdp`.

### 6.6. Do Not Disable TLS Verification

Never work around `ORA-29024` by disabling certificate validation or accepting untrusted certificates.

Check:

- Does the wallet contain the right root/intermediate CAs?
- Does the server send the complete chain?
- Is any certificate expired or not yet valid?
- Does the SAN match the hostname?
- Do the server and database have accurate clocks?
- Is the wallet path correct and OS-readable?
- Is a TLS inspection proxy swapping certificates?

If a TLS inspection proxy is present, the proxy's CA must be approved and trusted per security policy.

## 7. Wallet ACLs for Client Certificates and Passwords

Beyond host ACEs, Oracle provides wallet ACEs to control which principals may use credentials stored in a wallet.

### 7.1. Client Certificates

If an application uses a client certificate for mTLS authentication, it may need `use_client_certificates` granted on the wallet:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_WALLET_ACE(
        wallet_path => 'file:/u01/app/oracle/wallets/api',
        ace         => xs$ace_type(
            privilege_list => xs$name_list('use_client_certificates'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

The wallet must contain the matching client certificate and private key. The remote server must also trust the CA that issued the client certificate and enforce validation policy on it.

### 7.2. Password Credentials in the Wallet

If an application uses password credentials stored in a wallet via supported Oracle APIs, it may need the `use_passwords` privilege:

~~~sql
BEGIN
    DBMS_NETWORK_ACL_ADMIN.APPEND_WALLET_ACE(
        wallet_path => 'file:/u01/app/oracle/wallets/api',
        ace         => xs$ace_type(
            privilege_list => xs$name_list('use_passwords'),
            principal_name => 'APP_SCHEMA',
            principal_type => xs_acl.ptype_db
        )
    );
END;
/
~~~

Grant only the wallet privileges needed. Do not grant both `use_client_certificates` and `use_passwords` if the application does not use both mechanisms.

Wallet ACEs do not replace host ACEs. The principal still requires network permission to connect to the endpoint.

### 7.3. Wallet Trust and Client Authentication Are Different

- Trust certificates let the client verify the server.
- Client certificates let the server verify the client.
- Password credentials support certain authentication schemes.
- Network ACLs decide whether a principal may connect to a host/port.

Do not confuse installing a root CA into a wallet with granting network ACL privileges.

## 8. Calling HTTPS GET with UTL_HTTP

The example below sends a `GET` to a health endpoint, reads status and response body, and always closes the response when finished.

~~~sql
DECLARE
    l_req           UTL_HTTP.REQ;
    l_resp          UTL_HTTP.RESP;
    l_buffer        VARCHAR2(32767);
    l_response_open BOOLEAN := FALSE;
BEGIN
    UTL_HTTP.SET_DETAILED_EXCP_SUPPORT(TRUE);
    UTL_HTTP.SET_TRANSFER_TIMEOUT(30);

    UTL_HTTP.SET_WALLET(
        path     => 'file:/u01/app/oracle/wallets/api',
        password => NULL
    );

    l_req := UTL_HTTP.BEGIN_REQUEST(
        url          => 'https://api.example.com/v1/health',
        method       => 'GET',
        http_version => 'HTTP/1.1'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'User-Agent',
        'Oracle-Database-Integration'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Accept',
        'application/json'
    );

    l_resp := UTL_HTTP.GET_RESPONSE(l_req);
    l_response_open := TRUE;

    DBMS_OUTPUT.PUT_LINE(
        'HTTP status: ' || l_resp.status_code ||
        ' ' || l_resp.reason_phrase
    );

    BEGIN
        LOOP
            UTL_HTTP.READ_TEXT(l_resp, l_buffer, 32767);
            DBMS_OUTPUT.PUT_LINE(SUBSTR(l_buffer, 1, 2000));
        END LOOP;
    EXCEPTION
        WHEN UTL_HTTP.END_OF_BODY THEN
            NULL;
    END;

    UTL_HTTP.END_RESPONSE(l_resp);
    l_response_open := FALSE;

EXCEPTION
    WHEN OTHERS THEN
        IF l_response_open THEN
            BEGIN
                UTL_HTTP.END_RESPONSE(l_resp);
            EXCEPTION
                WHEN OTHERS THEN
                    NULL;
            END;
        END IF;

        RAISE;
END;
/
~~~

For illustrative examples, replace hostname, wallet path, and endpoint with approved values. Never write sensitive response payloads to `DBMS_OUTPUT` or application logs.

### 8.1. Why Must END_RESPONSE Be Called?

A response holds network resources and read state. Failing to close the response can leave the session holding connections/resources longer than necessary.

In production code:

- Close the response once the body is fully read.
- Close the response when an exception occurs after `GET_RESPONSE` succeeds.
- Never swallow the original exception merely because cleanup failed.
- Cap body size and processing time.
- Do not store large full responses in `VARCHAR2`.

### 8.2. Reading Response Headers

You can inspect header count and each individual header:

~~~sql
DECLARE
    l_resp   UTL_HTTP.RESP;
    l_name   VARCHAR2(256);
    l_value  VARCHAR2(4000);
    l_index  PLS_INTEGER;
BEGIN
    -- After GET_RESPONSE has returned l_resp:
    l_index := 1;

    WHILE l_index <= UTL_HTTP.GET_HEADER_COUNT(l_resp) LOOP
        UTL_HTTP.GET_HEADER(
            l_resp,
            l_index,
            l_name,
            l_value
        );

        DBMS_OUTPUT.PUT_LINE(l_name || ': ' || l_value);
        l_index := l_index + 1;
    END LOOP;
END;
/
~~~

This logic goes after `GET_RESPONSE` in the same block; do not call it on an uninitialized response.

## 9. Handling HTTP Status Codes

HTTP `2xx` generally indicates protocol-level success, yet the body still must be verified against the contract.

Example:

~~~sql
IF l_resp.status_code BETWEEN 200 AND 299 THEN
    -- Handle successful response per API contract.
    NULL;
ELSIF l_resp.status_code = 401 THEN
    -- Credential/token invalid or expired.
    NULL;
ELSIF l_resp.status_code = 429 THEN
    -- Rate limit: apply backoff per Retry-After if present.
    NULL;
ELSIF l_resp.status_code >= 500 THEN
    -- Server-side error or service temporarily unavailable.
    NULL;
ELSE
    -- 4xx or other status: handle per API contract.
    NULL;
END IF;
~~~

Do not treat every received response as successful. Even an HTTP 200 response can contain a business error inside JSON. Parse the payload and verify business codes.

`UTL_HTTP.SET_RESPONSE_ERROR_CHECK` can change how the package reports HTTP client/server error statuses. When enabled, error statuses can be converted into corresponding exceptions. Pick one consistent handling style: either check status manually or enable error checks and handle the raised exceptions.

## 10. Sending a JSON POST

Example sending UTF-8 JSON. The body is converted to `RAW` to calculate `Content-Length` in bytes rather than characters.

~~~sql
DECLARE
    l_req       UTL_HTTP.REQ;
    l_resp      UTL_HTTP.RESP;
    l_body      VARCHAR2(32767) := '{"orderId":1001,"status":"PAID"}';
    l_body_raw  RAW(32767);
    l_buffer    VARCHAR2(32767);
    l_open      BOOLEAN := FALSE;
BEGIN
    UTL_HTTP.SET_TRANSFER_TIMEOUT(30);
    UTL_HTTP.SET_WALLET(
        'file:/u01/app/oracle/wallets/api',
        NULL
    );

    l_body_raw := UTL_I18N.STRING_TO_RAW(l_body, 'AL32UTF8');

    l_req := UTL_HTTP.BEGIN_REQUEST(
        'https://api.example.com/v1/orders',
        'POST',
        'HTTP/1.1'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Content-Type',
        'application/json; charset=UTF-8'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Accept',
        'application/json'
    );

    UTL_HTTP.SET_HEADER(
        l_req,
        'Content-Length',
        TO_CHAR(UTL_RAW.LENGTH(l_body_raw))
    );

    UTL_HTTP.WRITE_RAW(l_req, l_body_raw);

    l_resp := UTL_HTTP.GET_RESPONSE(l_req);
    l_open := TRUE;

    DBMS_OUTPUT.PUT_LINE(
        'HTTP status: ' || l_resp.status_code
    );

    BEGIN
        LOOP
            UTL_HTTP.READ_TEXT(l_resp, l_buffer, 32767);
            DBMS_OUTPUT.PUT_LINE(SUBSTR(l_buffer, 1, 2000));
        END LOOP;
    EXCEPTION
        WHEN UTL_HTTP.END_OF_BODY THEN
            NULL;
    END;

    UTL_HTTP.END_RESPONSE(l_resp);
    l_open := FALSE;

EXCEPTION
    WHEN OTHERS THEN
        IF l_open THEN
            BEGIN
                UTL_HTTP.END_RESPONSE(l_resp);
            EXCEPTION
                WHEN OTHERS THEN
                    NULL;
            END;
        END IF;
        RAISE;
END;
/
~~~

This example uses a small body. For large payloads, stream `CLOB`/`RAW` in chunks, calculate byte length according to the encoding, or use a transfer mechanism supported by the endpoint. Never assume `LENGTH(text)` always equals UTF-8 `Content-Length`.

### 10.1. Authorization Header

An API may require a bearer token:

~~~sql
UTL_HTTP.SET_HEADER(
    l_req,
    'Authorization',
    'Bearer ' || l_access_token
);
~~~

Tokens must be retrieved from a secret store or organization-approved credential mechanism. Never hardcode tokens in package source, store them in log tables, or print them to `DBMS_OUTPUT`.

When tokens expire, follow a controlled refresh process. Avoid having many sessions concurrently refreshing the same token and causing a request storm.

### 10.2. Basic Authentication

Some APIs use HTTP Basic authentication. Basic authentication merely Base64-encodes credentials in the header without encrypting secrets; use it only over HTTPS with valid certificate validation.

If storing credentials in Oracle Wallet, check supported wallet credential APIs and the `use_passwords` privilege. Never store usernames/passwords in source code or URL query strings.

## 11. Timeouts, Retries, and Resource Management

### 11.1. Transfer Timeout

~~~sql
BEGIN
    UTL_HTTP.SET_TRANSFER_TIMEOUT(30);
END;
/
~~~

Set timeouts matching SLAs and endpoint processing times. Overly long timeouts hold database sessions and resources too long. Overly short timeouts cause false errors when endpoints have legitimate latency.

`SET_TRANSFER_TIMEOUT` governs `UTL_HTTP` data transfer operations in the session. Do not assume it replaces all timeouts at DNS, TCP, proxies, load balancers, or the application layer.

### 11.2. Bounded Retries

Retries fit certain transient errors:

- 429 Too Many Requests.
- 502/503/504.
- Certain recoverable connection or timeout errors.

However, do not retry every error:

- 400 usually indicates an invalid request.
- 401/403 usually requires fixing credentials/authorization.
- 404 may mean a non-existent endpoint or resource.
- 409 may be a business conflict.
- `POST` may already have been processed even if the client timed out before receiving the response.

Retries should include:

- Maximum attempt count.
- Exponential backoff and jitter.
- Maximum total elapsed duration.
- Handling of `Retry-After` if present.
- Idempotency keys for state-changing create/update operations.
- Logging attempt count and correlation ID.

### 11.3. Do Not Hold Transaction Locks During Network Calls

A database transaction should avoid holding row locks while waiting on HTTP services whenever possible.

Dangerous example:

1. `BEGIN` transaction.
2. `UPDATE` order and hold lock.
3. Call external API taking 30 seconds.
4. Wait for response, then `COMMIT`.

During that time, the session holds locks and transaction resources. If the API slows down, database contention spikes.

A usually better pattern:

1. Record business changes and an outbox event in the same transaction.
2. `COMMIT`.
3. A worker/job reads the outbox.
4. Call the external service outside a long transaction.
5. Record the result and retry per status.
6. Use idempotency keys to prevent duplicate side effects.

The outbox pattern coordinates database transactions and HTTP services without keeping transactions open across network calls.

## 12. Proxies and Outbound Networking

Some environments require an HTTP proxy for outbound traffic.

`UTL_HTTP` provides `SET_PROXY` to configure a session proxy. Conceptual example:

~~~sql
BEGIN
    UTL_HTTP.SET_PROXY(
        proxy            => 'proxy.internal.example:8080',
        no_proxy_domains => 'internal.example'
    );
END;
/
~~~

Verify syntax, proxy authentication, and TLS inspection details for your Oracle release and environment.

When using a proxy:

- The database host must be able to reach the proxy.
- Firewalls must allow traffic to the proxy host/port.
- Network ACLs must match the actual endpoint and routing path.
- Proxies may perform TLS inspection and swap certificates.
- The wallet must trust the approved CA if the proxy terminates TLS.
- `no_proxy_domains` must be configured accurately.
- Proxy logs and database logs need correlation IDs.

Never put proxy passwords in code or public parameter files.

## 13. ACL, Wallet, and UTL_HTTP: Privilege Matrix

| Activity | Primary Control |
|---|---|
| Connecting to `api.example.com:443` | Host ACE `connect` |
| Resolving `api.example.com` | Host ACE `resolve` when needed |
| Verifying TLS server certificate | Wallet trust chain and TLS configuration |
| Presenting client certificate | Wallet containing cert/key and `use_client_certificates` ACE when needed |
| Retrieving password credential from wallet | `use_passwords` ACE when used by API |
| Reading wallet file | OS permissions of the Oracle Database service account |
| Connecting via proxy | ACL/network route/firewall along the actual path |
| Sending HTTP requests | `UTL_HTTP` execution privilege and API contract |
| Reading/writing application data | Separate table/package privileges, not granted by network ACLs |

Network ACLs do not grant `SELECT`/`UPDATE` on tables. Wallet ACEs do not grant host `connect`. OS permissions do not substitute for database privileges.

## 14. Diagnosing Common Errors

| Error | Possible Cause | Investigation Direction |
|---|---|---|
| `ORA-24247` | Missing network ACL privilege | Principal, hostname, port, host ACE |
| `ORA-29273` | `UTL_HTTP` request failed, outer wrapper error | Inspect detailed SQL error and exception stack |
| `ORA-29024` | Certificate validation failure | Trust chain, expiry, SAN, clock, proxy |
| `ORA-28759` | Cannot open wallet/file | Wallet path, file existence, OS permissions |
| `ORA-29257` | Host unknown | DNS, resolver, `resolve` ACE |
| `ORA-29260` | Network error | Route, firewall, proxy, remote endpoint |
| `ORA-29276` | Transfer timeout | Endpoint latency, network, timeout setting |
| HTTP 401 | Invalid credential/token | Token expiry, auth scheme, wallet credential |
| HTTP 403 | Server denied access | API scope/role, mTLS identity, policy |
| HTTP 404 | Wrong endpoint/resource | URL, API version, path |
| HTTP 429 | Rate limit | Backoff, request rate, `Retry-After` |
| HTTP 5xx | External service error | Remote health, retry policy, circuit breaker |
| Empty response | Endpoint returned empty body or wrong read | Status, `Content-Length`, transfer encoding |
| Garbled Unicode | Encoding mismatch | `Content-Type` charset, `AL32UTF8` conversion |
| Only one RAC node fails | Inconsistent wallet/path/DNS/ACL | Mounts, file permissions, node configuration |

### 14.1. Enabling Detailed Exception Support

~~~sql
BEGIN
    UTL_HTTP.SET_DETAILED_EXCP_SUPPORT(TRUE);
END;
/
~~~

Inside an exception handler you can inspect:

~~~sql
DBMS_OUTPUT.PUT_LINE(SQLERRM);
DBMS_OUTPUT.PUT_LINE(UTL_HTTP.GET_DETAILED_SQLERRM);
~~~

Detailed error info may expose URLs, hostnames, or sensitive data. When logging, redact tokens, credentials, and payloads.

### 14.2. Isolating by Layer

Investigate in order:

1. **PL/SQL:** Does the package compile, and does the caller have `EXECUTE`?
2. **ACL:** Does the principal have `connect`/`resolve` for the right host/port?
3. **DNS/network:** Can the database server resolve and connect?
4. **Wallet/filesystem:** Is the wallet path right, OS-readable, with a valid certificate chain?
5. **TLS:** Are handshake, hostname, protocol, and ciphers compatible?
6. **HTTP:** Status code, headers, endpoint, and auth?
7. **Business payload:** JSON/XML schema, encoding, and business outcome?

Never change certificates, ACLs, and firewalls simultaneously before knowing which layer is failing. Each change should have evidence and a verification step.

## 15. Securing Outbound Integrations

Databases often hold sensitive data and high-privilege data access. If a database user can call arbitrary URLs, a bug in PL/SQL or the application can become an access path to internal systems.

### 15.1. SSRF and URL Allowlists

Server-Side Request Forgery (SSRF) happens when untrusted input controls the destination accessed by the server.

Do not do this:

~~~sql
l_url := p_user_supplied_url;
l_resp := UTL_HTTP.GET_RESPONSE(UTL_HTTP.BEGIN_REQUEST(l_url));
~~~

If callers can supply arbitrary URLs, they may attempt to reach:

- `localhost` or loopback.
- Link-local addresses.
- Cloud instance metadata endpoints.
- Private admin endpoints.
- Internal databases/services.
- Infrastructure-management-only endpoints.

Secure design:

- URLs/hostnames allowlisted on the server.
- Enforce HTTPS scheme where required by business/security rules.
- Restrict ports.
- Never let callers pass arbitrary hostnames.
- Validate redirect destinations.
- Block private/link-local/metadata IP ranges at firewalls/egress proxies.
- Govern DNS and avoid wildcard ACLs.
- Never rely on client-side validation.

### 15.2. Redirects

HTTP `3xx` can direct requests to a different hostname. If the application follows redirects automatically, the actual destination may differ from the initial URL.

For sensitive endpoints:

- Inspect `3xx` status and `Location` header.
- Only follow redirects to allowlisted hosts.
- Never forward `Authorization` headers to another host unless permitted.
- Limit maximum redirects.
- Verify ACLs and egress firewalls for the new destination.

Never treat an allowlisted URL as guaranteeing every redirect from it is safe.

### 15.3. Never Put Credentials in URLs

Avoid:

~~~text
https://api.example.com/data?token=secret
~~~

URLs can appear in logs, proxies, tracing, and error messages. Use `Authorization` headers or credential mechanisms supported by the API.

### 15.4. TLS and Certificates

- Use HTTPS only for sensitive data/credentials.
- Verify hostname and certificate chain.
- Reject expired or unapproved self-signed certificates.
- Protect private keys in wallets.
- Maintain a certificate rotation schedule.
- Monitor expiration dates before expiry.
- Keep database server clocks synchronized.

### 15.5. Least Privilege

- Grant host ACEs only for needed hostnames/ports.
- Grant wallet ACEs only to schemas requiring them.
- Never grant to `PUBLIC`.
- Avoid wildcard hosts unless required.
- Never grant `CREATE ANY DIRECTORY` or broad system privileges just to make a wallet work.
- Keep wallet filesystem permissions minimal.
- Separate integration schemas from application owners when needed.

## 16. Calling External Services in Application Architecture

### 16.1. When to Call Directly from the Database?

May be suitable when:

- Requests are small with short timeouts.
- Integration is part of a controlled stored workflow.
- High throughput is not needed.
- Network failures can be handled cleanly.
- There is a clear operational owner for endpoints and credentials.
- Long transactions/locks are not held.

### 16.2. When to Use the Application Tier or a Message Broker?

Consider moving HTTP calls to the application tier when:

- API calls have variable or high latency.
- Complex OAuth token refresh flows are needed.
- Circuit breakers, rate limiting, and retry queues are required.
- Multiple services or tenants use differing endpoints.
- Large payloads must be processed.
- Outbound requests must scale independently of the database.
- Distributed-system-level observability/tracing is needed.
- Database transactions must not depend on external availability.

The database should focus on transactions and persistence. The application tier or an integration platform is generally better suited to managing complex HTTP communication.

### 16.3. Outbox Pattern

An example:

~~~text
Business transaction
       |
       +---- UPDATE ORDERS
       |
       +---- INSERT OUTBOX_EVENT
       |
       +---- COMMIT
                  |
                  v
             Outbox worker
                  |
                  v
             UTL_HTTP / API
                  |
                  v
             Remote service
                  |
                  v
        Mark delivered / retry
~~~

The outbox event commits alongside business changes. A worker sends the HTTP request after commit. If the endpoint fails, the event stays pending for retry.

Include unique event IDs, idempotency keys, retry schedules, dead-letter states, and backlog monitoring. Outbox does not automatically yield exactly-once delivery; the remote API must support idempotency or the consumer must deduplicate.

## 17. Logging and Observability

Every outbound call should log:

- Request/correlation ID.
- Integration name.
- Allowlisted target service name.
- HTTP method.
- Start/end timestamps.
- Elapsed time.
- HTTP status code.
- Retry count.
- Error class/code.
- Payload size.
- Response size.
- Business outcome.

Do not log:

- Passwords.
- Bearer tokens.
- Private keys.
- Wallet passwords.
- Full sensitive request/response payloads.
- Unnecessary personal data.

Use `module`/`action` or correlation IDs to link database calls with application traces. Create metrics for success rate, timeout rate, 4xx/5xx counts, p95 latency, retry count, and queue backlog.

### 17.1. Measuring Latency

Break down timing across:

- Database processing before the call.
- DNS/connect/TLS setup.
- Time to first byte.
- Body transfer.
- JSON/XML parsing.
- Database commit after response.

`UTL_HTTP` does not replace end-to-end distributed tracing. If tracing across applications, proxies, and external services is required, design a shared correlation ID.

### 17.2. Circuit Breakers and Rate Limits

If an endpoint fails continuously, continuing to call it can tie up database sessions. Implement a circuit breaker in the application tier or job scheduler:

- Closed: allow requests through.
- Open: pause calls once failures exceed threshold.
- Half-open: send probe requests to test recovery.

Rate limits prevent the database from creating huge bursts exceeding remote service quotas. Retries must use backoff and jitter to avoid all sessions retrying simultaneously.

## 18. Runbook: Configuring UTL_HTTP to an HTTPS Endpoint

### Step 1 — Identify Endpoint and Owner

Record:

- Hostname FQDN.
- Port.
- Scheme.
- API owner.
- Authentication method.
- TLS requirements.
- Proxy requirements.
- Rate limits.
- Timeouts/SLA.
- Data classification.

### Step 2 — Verify Network from the Database Host

Check DNS, routing, firewalls, proxies, and outbound policies from the database host itself—not just from a DBA laptop.

### Step 3 — Prepare the Wallet

- Obtain the certificate chain from trusted authorities.
- Verify issuer, fingerprint, SAN, and validity dates.
- Import trust certificates into the wallet.
- Import client certificate/private key if using mTLS.
- Protect wallet files and backups/keys.
- Confirm the Oracle service account can read them.

### Step 4 — Configure Network ACL

Grant `connect` for host/port and `resolve` when needed to the exact executing principal. If the package uses `AUTHID DEFINER`, check the package owner; if `CURRENT_USER`, check the invoker.

### Step 5 — Configure Wallet ACE If Needed

Grant `use_client_certificates` or `use_passwords` according to the credential feature used. Do not grant broader privileges than required.

### Step 6 — Test from a Real Session

Run a `GET` to the health endpoint using the real user and call path. Record HTTP status, response time, and secret-redacted exception details.

### Step 7 — Test Failure Modes

Test scenarios in a non-production environment:

- Host missing ACL.
- Wrong port.
- Wrong wallet path.
- Expired/untrusted certificate.
- Endpoint returning 401/429/500.
- Timeout.
- Large response body.
- Redirect to a non-allowlisted host.

### Step 8 — Production Readiness

- Monitoring and alerting in place.
- Timeout/retry policies configured.
- Credential rotation plan defined.
- Endpoint owner and escalation path documented.
- Log retention and redaction implemented.
- Rollback plan for ACL/wallet configs.
- Failover/network outage testing completed.

## 19. Common Verification Queries

### 19.1. Network ACL

~~~sql
SELECT host,
       lower_port,
       upper_port,
       principal,
       privilege,
       grant_type
FROM dba_host_aces
WHERE principal = 'APP_SCHEMA'
ORDER BY host, lower_port, privilege;
~~~

### 19.2. Wallet ACL

~~~sql
SELECT wallet_path,
       principal,
       privilege,
       grant_type
FROM dba_wallet_aces
WHERE principal = 'APP_SCHEMA'
ORDER BY wallet_path, privilege;
~~~

### 19.3. Checking Database/Container Identity

~~~sql
SELECT sys_context('USERENV', 'DB_NAME') AS db_name,
       sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'SESSION_USER') AS session_user,
       sys_context('USERENV', 'CURRENT_USER') AS current_user,
       sys_context('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
~~~

### 19.4. Checking UTL_HTTP Availability

DBAs verify the package and `EXECUTE` privileges per policy:

~~~sql
SELECT owner,
       object_name,
       object_type,
       status
FROM all_objects
WHERE object_name = 'UTL_HTTP'
ORDER BY owner, object_type;
~~~

Never grant `EXECUTE` broadly to `PUBLIC` just to make a test query work. Grant package privileges to integration schemas per the security baseline.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Granting ACL only, missing OS permissions | Oracle cannot read wallet or connect | Check OS account and filesystem |
| Installing certificate only, no host ACE | `ORA-24247` | Grant `connect`/`resolve` for target host |
| Granting wildcard ACL | Database can reach unintended endpoints | Allowlist FQDN and port |
| Using wallet on laptop | Database server cannot read it | Place wallet on server-side path |
| Confusing wallet trust with client certificate | Misconfigured TLS/mTLS | Distinguish server trust from client identity |
| Disabling TLS validation to bypass `ORA-29024` | Loss of server identity verification | Fix trust chain/SAN/clock |
| Failing to close response | Holds network resources | Always call `END_RESPONSE` |
| No timeout set | Session can hang indefinitely | Configure timeout per SLA |
| Treating HTTP 500 as a SQL exception | Status codes mishandled | Inspect response status |
| Retrying `POST` unconditionally | Duplicate transactions | Idempotency keys and retry policy |
| Calling API inside a lock-holding transaction | Increased lock duration and contention | Outbox/asynchronous worker |
| Taking URLs from user input | SSRF against internal endpoints | Server-side allowlist and egress controls |
| Not handling redirects | `Authorization` leaked to other hosts | Validate `Location` and host |
| Logging tokens/payloads | Credential/data exposure | Redaction and secret management |
| Testing only from client machine | Fails to reflect database host networking | Test from server/database session |
| Not checking all RAC nodes | One node has different wallet/path | Synchronize wallet and OS access |

## 21. Hands-On Exercises

Perform in a lab environment against organization-controlled test endpoints.

### Exercise 1 — Create Host ACE

Create an ACL for the test schema to a single hostname and port 443. Query `DBA_HOST_ACES` to confirm.

### Exercise 2 — Test Missing Privilege

Call `UTL_HTTP` without a `connect` ACE. Observe `ORA-24247`, then grant least privilege and retest.

### Exercise 3 — DNS Resolution

Test a valid hostname and an unresolvable hostname. Distinguish `resolve` ACL errors from DNS/network failures.

### Exercise 4 — Wallet Trust

Create a test wallet, import the test endpoint's root/intermediate CA, and configure `SET_WALLET`. Verify the TLS handshake.

### Exercise 5 — Certificate Errors

Use a test endpoint with an untrusted certificate or hostname mismatch. Observe the TLS error and restore the proper trust chain.

### Exercise 6 — mTLS

Create a test client certificate, configure the wallet and `use_client_certificates` ACE. Confirm the server recognizes the client identity.

### Exercise 7 — GET and Status Codes

Call test endpoints returning 200, 401, 404, and 500. Handle HTTP status codes separately from Oracle exceptions.

### Exercise 8 — UTF-8 POST

Send JSON containing Unicode characters. Compute byte-based `Content-Length` and confirm the server receives the exact payload.

### Exercise 9 — Timeouts

Call a test endpoint with added latency. Adjust `SET_TRANSFER_TIMEOUT` and measure timing/exceptions.

### Exercise 10 — Response Cleanup

Simulate an exception mid-body read. Confirm `END_RESPONSE` is invoked.

### Exercise 11 — SSRF Controls

Test a URL outside the allowlist and a redirect to another hostname. Confirm server-side validation and egress policies block them.

### Exercise 12 — Outbox

Create an outbox event, run a worker calling the API, simulate a remote outage, and retry. Verify idempotency prevents duplicate side effects.

## 22. Pre-Production Checklist

- [ ] Endpoint FQDN, port, protocol, and owner identified.
- [ ] Server-side allowlist enforced; no arbitrary URLs accepted.
- [ ] Network ACL grants only required hosts/ports.
- [ ] `connect` and `resolve` granted appropriately per DNS usage.
- [ ] ACL principal matches actual `AUTHID`/call context.
- [ ] Firewall, DNS, routes, and proxy permit controlled outbound traffic.
- [ ] Wallet resides on a protected server path.
- [ ] Oracle OS service account has read access to the wallet.
- [ ] Trust chain and hostname SAN verified.
- [ ] Client certificate/private key protected if using mTLS.
- [ ] Wallet ACEs `use_client_certificates`/`use_passwords` granted only when needed.
- [ ] No hardcoded tokens/passwords/private keys.
- [ ] Timeouts set per SLA.
- [ ] HTTP statuses and response bodies handled explicitly.
- [ ] Responses always closed on both success and exception paths.
- [ ] Bounded retries, backoff, and idempotency implemented.
- [ ] No transactions/row locks held while awaiting external services.
- [ ] Redirects controlled without leaking credentials to other hosts.
- [ ] Logs include correlation IDs and secret redaction.
- [ ] Metrics exist for success/error/timeout/latency/rate limits.
- [ ] Runbooks exist for certificate rotation, ACL revocation, and endpoint outages.
- [ ] Tested with actual database user/package owner and server environment.

## 23. Core Takeaways

- `UTL_HTTP` lets PL/SQL send HTTP/HTTPS requests from Oracle Database to external services.
- Network ACLs control which principals may connect to hostnames/ports; firewalls and network routes must still allow traffic.
- For specific API hosts, grant `connect` on needed ports and `resolve` when DNS name resolution requires it.
- ACLs do not grant wallet read access, table privileges, or network routes.
- `DIRECTORY` objects and wallet paths are distinct concepts; wallet paths are referenced directly by `UTL_HTTP` using file URI syntax.
- Wallets store trust certificates, client certificates/private keys, or credentials depending on use case; server trust and client authentication are separate concerns.
- The OS account running Oracle Database must be able to read wallet files; never use `777` permissions.
- Wallet ACEs `use_client_certificates`/`use_passwords` are granted only when the corresponding credential feature is used.
- `AUTHID DEFINER` and `CURRENT_USER` determine the executing principal; grant ACLs for the right context and test with real users.
- `ORA-24247` typically relates to network ACLs; `ORA-29024` relates to certificate validation; `ORA-29273` is a general `UTL_HTTP` wrapper requiring detailed error inspection.
- HTTP 4xx/5xx are response statuses and must be handled separately from Oracle exceptions.
- Always set timeouts, limit response sizes, close responses, and log with secrets redacted.
- Retries must have limits, backoff, and idempotency; a timeout after `POST` does not prove the server never processed the request.
- Never hold transactions or row locks while waiting on external services; consider outbox/asynchronous workers.
- Never accept arbitrary URLs from users; defend against SSRF with allowlists, specific ACLs, redirect validation, and egress firewalls.
- Never disable TLS certificate validation to fix errors; fix the trust chain, SAN, expiry, and clock.
- Calling HTTP from the database suits small, controlled integrations; complex workloads are usually better managed in the application/integration tier.

### Oracle Reference Documentation

- [Oracle Database PL/SQL Packages and Types Reference — UTL_HTTP](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_HTTP.html) — HTTP request/response APIs, wallet, proxy, timeout and exception handling.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_NETWORK_ACL_ADMIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_NETWORK_ACL_ADMIN.html) — Host ACE, wallet ACE and network ACL administration.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Network access control, wallet privileges and least privilege.
- [Oracle Database Security Guide — Using Oracle Wallet](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/) — Wallet management, certificates and credential protection.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Database server processes, operating-system access and administration.
- [Oracle Database PL/SQL Packages and Types Reference — UTL_I18N](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/UTL_I18N.html) — Character set conversion for HTTP payloads.

Network ACL APIs, wallet behavior, TLS protocol support and UTL_HTTP features vary by Oracle release and platform. Confirm the exact database version, certificate requirements, package privileges and license terms; test ACL, wallet, timeout, redirect, response cleanup and failover in a representative non-production environment before production use.
