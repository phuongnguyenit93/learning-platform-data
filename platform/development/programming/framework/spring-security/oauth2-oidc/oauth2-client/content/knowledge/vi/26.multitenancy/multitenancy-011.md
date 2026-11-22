# 26.11. Tách secret, token, session và dữ liệu định danh theo tenant

## 1. Bài toán: đăng nhập OIDC thành công nhưng vẫn có thể rò rỉ dữ liệu giữa tenants

Một nền tảng SaaS **Employee Portal** phục vụ nhiều tổ chức. Mỗi tổ chức là một **tenant** có nhân viên, cấu hình OIDC, tài nguyên và quyền truy cập riêng.

~~~text
Tenant ACME
  Public host: https://acme.portal.example.com
  OIDC issuer: https://login.acme.example/oidc
  Client registration: portal-acme
  Client secret: ACME_SECRET
  Authorized clients: ACME_TOKENS
  Business data: ACME_DATA

Tenant GLOBEX
  Public host: https://globex.portal.example.com
  OIDC issuer: https://identity.globex.example/oidc
  Client registration: portal-globex
  Client secret: GLOBEX_SECRET
  Authorized clients: GLOBEX_TOKENS
  Business data: GLOBEX_DATA
~~~

Người dùng của ACME đã đăng nhập, nhưng gửi:

~~~http
GET /api/reports?tenant=globex HTTP/1.1
Host: acme.portal.example.com
Cookie: __Host-SESSION=<opaque-session-id>
~~~

Nếu backend tin tham số `tenant=globex` rồi lấy token hoặc dữ liệu của GLOBEX, hệ thống đã vi phạm **tenant isolation**. Ngay cả khi OAuth2/OIDC login, chữ ký ID Token và HTTPS đều đúng, **cross-tenant authorization** vẫn sai.

Một lỗi khác thường kín đáo hơn:

~~~text
Token cache key = "alice"

ACME alice đăng nhập  -> cache["alice"] = AT-ACME
GLOBEX alice đăng nhập -> cache["alice"] = AT-GLOBEX
ACME alice gọi API    -> cache["alice"] trả AT-GLOBEX
~~~

Vấn đề không nằm ở việc Authorization Server phát token không hợp lệ; backend đã dùng **khóa lưu trữ thiếu tenant và client registration**.

Bài này giải thích cách thiết kế bốn lớp cách ly:

1. **Secret isolation** — client secret, private key, mTLS key và secret references.
2. **Token isolation** — access token, refresh token, authorized-client store và vòng đời token.
3. **Session isolation** — session cookie, SecurityContext, OAuth state, nonce, PKCE và login callback.
4. **Identity/data isolation** — `(tenant, issuer, subject)`, memberships, RBAC, business data và audit.

> Bối cảnh kỹ thuật: Java 17+, Spring Boot 3, Spring Security 6, Spring MVC/Servlet OAuth2/OIDC Client; một số mục so sánh WebFlux/Reactive. Các tên tenants, hosts, secrets và token là minh họa. Không có một thuộc tính Spring Security duy nhất tự đảm bảo toàn bộ tenant isolation.

## 2. Tenant ID, issuer, client registration và principal khác nhau

| Khái niệm | Ví dụ | Ý nghĩa bảo mật |
|---|---|---|
| Tenant ID | `acme` | Phạm vi tổ chức/dữ liệu/quyền trong SaaS |
| OpenID issuer | `https://login.acme.example/oidc` | Nhà phát hành identity/token đáng tin |
| Registration ID | `portal-acme` | OAuth2 client cụ thể trong Spring Security |
| Client ID | `acme-portal-web` | ID do Authorization Server cấp cho OAuth client |
| Subject | `sub=employee-42` | Định danh subject trong phạm vi issuer/sector |
| Principal key | `acme:user-42` | Khóa lưu authorized client do hệ thống chọn tin cậy |
| Session ID | Một chuỗi opaque | Browser dùng để tìm server-side session |
| Internal user ID | `u-1038` | ID người dùng trong ứng dụng |

**Tenant ID không nhất thiết bằng issuer.** Có thể:

- Mỗi tenant có một issuer.
- Nhiều tenants dùng chung một issuer.
- Một tenant có nhiều issuers cho nhân viên/đối tác.
- Một issuer cung cấp nhiều ClientRegistration cho từng tenant hoặc cho nhiều chức năng.

Do đó quy tắc `tenantId = token.iss` chỉ an toàn nếu đó thực sự là hợp đồng trust/tenant mapping được quản trị.

### 2.1. Tenant do người dùng yêu cầu chưa phải tenant đã được cấp quyền

Cần phân biệt:

~~~text
candidateTenant
  -> tenant suy ra từ host/path/query/header của request

authenticatedIdentity
  -> danh tính đã được xác thực bằng OIDC hoặc cơ chế tin cậy

authorizedTenant
  -> tenant mà identity thực sự có active membership
     và permission cho operation hiện tại
~~~

**Chỉ dùng authorizedTenant để lấy credential có quyền, truy vấn dữ liệu hoặc đưa ra quyết định bảo mật.**

### 2.2. Isolation ở nhiều tầng

Tenant isolation không chỉ nghĩa là mỗi tenant một database. Một database chung vẫn có thể an toàn khi truy vấn và RLS/ACL đúng, trong khi nhiều database riêng vẫn rò rỉ nếu backend chọn nhầm connection bằng dữ liệu chưa xác minh.

Để bảo vệ đầy đủ, cần **identity trust + authorization + credentials + storage + network/API destination + lifecycle**.

## 3. Kiến trúc tham chiếu

~~~mermaid
flowchart TD
    A["Browser ACME"] --> R["Tenant resolver / trusted ingress"]
    B["Browser GLOBEX"] --> R
    R --> S["Tenant-bound session & authentication"]
    S --> P["Membership + authorization policy"]
    P --> C["Tenant registry / ClientRegistration"]
    C --> CA["portal-acme"]
    C --> CG["portal-globex"]
    CA --> VA["ACME secret reference / Vault"]
    CG --> VG["GLOBEX secret reference / Vault"]
    CA --> IA["ACME OpenID Provider"]
    CG --> IG["GLOBEX OpenID Provider"]
    P --> T["Tenant-aware authorized-client store"]
    T --> TA["ACME tokens"]
    T --> TG["GLOBEX tokens"]
    P --> D["Tenant-filtered business data"]
    P --> API["Allowlisted tenant downstream API"]
~~~

Một request hợp lệ:

~~~text
HTTP request
  -> resolve candidate tenant using configured routing
  -> authenticate user/service
  -> verify membership and resource permission
  -> select tenant-owned ClientRegistration
  -> load authorized client from tenant partition
  -> call only trusted tenant Resource Server
  -> query data constrained by authorized tenant
~~~

Không làm ngược thứ tự bằng cách lấy GLOBEX admin token trước rồi mới xem người dùng ACME có quyền hay không.

## 4. Quy tắc tenant resolution: host, path và header chỉ là input

Những nguồn tenant hay gặp:

~~~text
https://acme.portal.example.com
https://portal.example.com/t/acme/reports
X-Tenant-ID: acme
?tenant=acme
~~~

Từ host/path/header, backend có thể tìm **candidate tenant**. Nhưng chỉ có kết quả membership/authorization mới biến nó thành **authorized tenant**.

### 4.1. Dùng tenant registry được quản trị

Một registry nên lưu:

~~~json
{
  "tenantId": "acme",
  "status": "ACTIVE",
  "publicHost": "acme.portal.example.com",
  "loginRegistrationId": "portal-acme",
  "serviceRegistrationId": "reports-acme-service",
  "issuer": "https://login.acme.example/oidc",
  "reportsApiBaseUri": "https://reports.acme.example",
  "clientSecretRef": "vault://oauth-clients/acme/portal/current"
}
~~~

`vault://` là URI minh họa cho một secret reference, **không phải cú pháp chuẩn của Spring Security**. Trong production, áp dụng API/config adapter của secret manager tương ứng.

Registry phải được cập nhật qua quy trình quản trị, không để một HTTP user tự thay issuer/secret reference/token endpoint.

### 4.2. Xác thực Host và Forwarded headers

Khi sử dụng reverse proxy:

~~~text
Browser -> HTTPS acme.portal.example.com
Ingress -> HTTP portal-service:8080
~~~

Ingress phải normalize `Host`, `Forwarded` và `X-Forwarded-Host` theo trust boundary; strip/overwrite header do Internet client tự gửi.

Nếu ứng dụng tin `X-Forwarded-Host: globex.portal.example.com` do attacker gửi, tenant resolver có thể bị lừa chọn GLOBEX. Cấu hình `server.forward-headers-strategy` cần đi cùng **proxy trust**, không tự bảo đảm header đáng tin.

### 4.3. Không cho user chọn registration tùy ý

Sai:

~~~java
String registrationId =
    httpRequest.getParameter("tenant") + "-admin";
~~~

Kẻ tấn công có thể thử một registration đặc quyền. Thay vào đó dùng:

~~~text
authorized tenant -> registry allowlist -> permitted registration ID
~~~

## 5. Secret isolation: tách OAuth2 credentials theo tenant

Một confidential OAuth client có thể dùng:

- `client_secret_basic` hoặc `client_secret_post`.
- `private_key_jwt` và private key.
- mTLS certificate/private key.
- Secret của trusted ticket signer hoặc hệ thống cấp workload credential.

Với ACME và GLOBEX, mỗi client cần credential theo bản ghi tại Authorization Server. **Cùng IdP không đồng nghĩa được dùng chung client secret**.

### 5.1. Thiết kế khóa secret

Một logical key:

~~~text
(tenantId, registrationId, credentialVersion)
~~~

Ví dụ:

~~~text
oauth-clients/acme/portal/v4
oauth-clients/acme/reports-service/v2
oauth-clients/globex/portal/v7
~~~

Tránh cache secret với key `oauthClientSecret` chung mọi tenants.

### 5.2. Không đưa raw secret vào tenant database

Một bảng cấu hình có thể chứa:

~~~text
tenant_id
registration_id
issuer_uri
client_id
secret_ref
status
~~~

Trong đó `secret_ref` chỉ là pointer đến Vault/KMS. Credential thật cần được quản lý bằng storage/ACL/audit/rotation policy.

### 5.3. Workload access và blast radius

Nếu microservice ACME có thể gọi API Vault đọc mọi GLOBEX secrets, tên prefix `/acme/` chỉ là convention, không phải isolation. Muốn ranh giới mạnh hơn cần:

- Secret manager ACL theo workload/tenant.
- IAM/service accounts với least privilege.
- Audit mọi lần đọc/rotate.
- Mã hóa truyền tải và at rest.
- Có thể tách pods/processes hoặc secret broker cho nhóm tenants có mức cách ly cao.

Một SaaS process chung đôi khi buộc phải có quyền phục vụ nhiều tenants; cần hiểu mức độ giảm blast radius thực tế và không quảng bá namespace như một security boundary tuyệt đối.

## 6. Ví dụ Spring Boot ClientRegistration per tenant

~~~yaml
# application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-acme:
            provider: acme-oidc
            client-id: ${ACME_OIDC_CLIENT_ID}
            client-secret: ${ACME_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read

          portal-globex:
            provider: globex-oidc
            client-id: ${GLOBEX_OIDC_CLIENT_ID}
            client-secret: ${GLOBEX_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read

        provider:
          acme-oidc:
            issuer-uri: https://login.acme.example/oidc
          globex-oidc:
            issuer-uri: https://identity.globex.example/oidc
~~~

ClientRegistration `portal-acme` và `portal-globex` có **registration IDs riêng**. Những giá trị placeholder nên đến từ secret manager hoặc runtime environment an toàn, không commit client secrets thật trong source code.

### 6.1. Cùng issuer vẫn có thể có registrations riêng

Nếu ACME và GLOBEX cùng issuer:

~~~text
issuer = https://login.saas.example
~~~

hai registrations vẫn có thể dùng chung provider alias trong YAML, nhưng khác client IDs/secrets/scopes/redirects.

**Sử dụng một provider chung không có nghĩa hai tenants dùng chung token hoặc memberships.**

### 6.2. Không phải mỗi tenant đều cần issuer riêng

Tenant là business isolation boundary; issuer là identity trust boundary. Một hệ thống có một OP chuẩn phục vụ nhiều tenants vẫn cần RBAC và data isolation theo tenant.

### 6.3. RegistrationId phải duy nhất trong repository chung

`ClientRegistrationRepository.findByRegistrationId(String)` không có tham số tenant. Nếu dùng một repository chung, đặt IDs như `portal-acme`, `portal-globex` giúp tránh trùng. Không dùng `portal` cho cả hai trong cùng repository rồi phụ thuộc vào ThreadLocal chưa được kiểm chứng.

## 7. Rotation client secret theo tenant

Ví dụ:

~~~text
ACME:   portal secret v4 -> v5
GLOBEX: portal secret v7 vẫn giữ
~~~

Một quy trình rotation:

1. Xác minh đúng tenant và registration.
2. Tạo credential mới tại Authorization Server.
3. Lưu vào secret manager dưới version mới và gắn ACL.
4. Cập nhật ClientRegistration/secret resolver theo cơ chế deployment có chủ đích.
5. Test token exchange của tenant đó.
6. Thu hồi credential cũ theo cửa sổ rotation.
7. Quan sát `invalid_client` và audit.

Không tự rotate/disable GLOBEX vì chỉ có ACME gặp sự cố.

### 7.1. Rotation không đồng nghĩa token revocation

Thay client secret **không bảo đảm** mọi access token/refresh token cũ đã bị thu hồi. Authorization Server có policy riêng về revocation và token validity. Khi nghi credential bị lộ, đánh giá cả token grants và sessions theo incident response.

### 7.2. Không giữ secret vô hạn trong cache

Secret resolver có thể cache bản mã/credential tạm thời nhưng cần TTL, invalidation và xử lý version. Nếu chỉ cập nhật Vault mà process giữ client secret cũ suốt đời, token endpoint có thể tiếp tục trả `invalid_client`.

## 8. Dynamic onboarding và issuer discovery phải được kiểm soát

Khi có hàng ngàn tenants, hard-code YAML có thể không phù hợp. Ứng dụng có thể implement `ClientRegistrationRepository` với nguồn tenant registry/secret manager.

Quy trình onboarding an toàn:

~~~text
Tenant application
  -> verify organization ownership
  -> approve OIDC issuer and public endpoints
  -> inspect discovery metadata and exact issuer
  -> register OAuth client/redirect URIs
  -> assign secret reference and ACL
  -> approve scopes/audience/claim mapping
  -> activate tenant
~~~

Không chấp nhận một issuer URI do browser tự nhập rồi tự động tạo trusted OAuth client.

### 8.1. SSRF từ OIDC discovery

Ví dụ URLs không được chấp nhận chỉ vì hợp lệ về cú pháp:

~~~text
http://localhost:8080/admin
http://169.254.169.254/
https://unapproved.example/.well-known/openid-configuration
~~~

Issuer onboarding cần HTTPS, allowlist, DNS/IP egress restrictions, redirect checks, metadata issuer matching và policy chống SSRF/DNS rebinding. Không tắt issuer verification vì “IdP của tenant có cách cấu hình lạ”.

### 8.2. Một tenant có nhiều issuers

Nếu cùng ACME có IdP nhân viên và IdP đối tác, external identity cần chứa đúng issuer; provider configuration phải tách trust boundaries. Không dựa chỉ vào email của hai issuers để ghép user.

## 9. Token isolation: authorized client phải tách theo tenant và registration

Spring Security sử dụng:

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
~~~

Nó mang:

~~~text
ClientRegistration
principalName
accessToken
refreshToken (nếu được cấp)
~~~

Một authorized client ACME **không được dùng** cho GLOBEX chỉ vì hai issuers cùng hostname hoặc hai user có cùng email.

### 9.1. Storage key nên mô tả cả tenant

~~~text
(tenantId, clientRegistrationId, trustedPrincipalKey)
~~~

| Tenant | Registration | Principal | Token |
|---|---|---|---|
| acme | portal-acme | acme-u42 | AT-A |
| globex | portal-globex | globex-u42 | AT-G |
| acme | reports-acme-service | reports-job-acme | AT-AS |
| globex | reports-globex-service | reports-job-globex | AT-GS |

Không key bằng:

~~~text
oauth2:access-token:<username>
oauth2:access-token:<email>
oauth2:access-token:<issuer>
~~~

vì username/email/issuer không phân biệt đủ client/tenant.

### 9.2. Spring Security default OAuth2AuthorizedClientService

Giao diện đồng bộ có các phương thức:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

**Không có tenantId tham số riêng.** Nếu dùng service chuẩn trên một store chung, registration IDs cần được namespace duy nhất theo tenant/client. Nếu phải partition bằng tenant thêm vào key, ứng dụng cần adapter/repository khác hoặc storage scope được thiết kế rõ.

### 9.3. Key prefix không tự bảo đảm authorization

Redis key:

~~~text
oauth2:acme:portal-acme:acme-u42
oauth2:globex:portal-globex:globex-u42
~~~

giảm nguy cơ collision. Nhưng nếu một method bất kỳ có thể lấy `oauth2:globex:*` mà không có tenant authorization, data vẫn có thể lộ. **Prefix và ACL/policy phải đi cùng nhau**.

### 9.4. Principal không lấy từ user input

Sai:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("portal-globex")
    .principal(requestParameterUserName)
    .build();
~~~

Điều đó có thể khiến backend tìm authorized client của một principal khác theo storage key. Trong user-delegated flow, principal phải là Authentication đã được Spring Security xác minh và phù hợp tenant.

## 10. Access token phải phù hợp Resource Server và tenant

Ví dụ một token:

~~~text
iss = https://login.acme.example/oidc
aud = reports-acme-api
scope = reports.read
tenant_id = acme (nếu token contract có claim này)
~~~

Không được gửi nó tới:

~~~text
https://reports.globex.example
~~~

với kỳ vọng token được tin vì signature hợp lệ. Resource Server phải kiểm tra:

- Issuer đáng tin theo policy.
- Signature/JWT hoặc token introspection.
- Audience/resource indicator.
- Scopes/roles.
- Tenant binding và membership nếu áp dụng.
- Resource ownership.
- Expiration và revocation.

**Client JWT decoder không được đọc unverified claims rồi cho chúng quyền tenant.** Issuer/audience/tenant claims chỉ là bằng chứng sau khi đã được xác minh đúng contract.

### 10.1. Access token không phải ID Token

OIDC ID Token phục vụ authentication của OAuth client; access token mới là token dùng cho Resource Server. Không lấy ID Token ACME gửi sang GLOBEX API hoặc dùng ID Token thay quyền dữ liệu.

### 10.2. Không tự nâng scope trong client

Sửa `OAuth2AuthorizedClient` hoặc JSON payload của JWT không cấp thêm quyền. Scopes/audience phải được Authorization Server cấp, và API kiểm tra.

## 11. Refresh-token rotation và concurrency

Hai tenants có token families:

~~~text
ACME:
  RT-A1 -> RT-A2 + AT-A2

GLOBEX:
  RT-G1 -> RT-G2 + AT-G2
~~~

Không ghi RT-A2 lên row GLOBEX, không retry RT-A1 vô hạn nếu provider có rotation/reuse detection.

### 11.1. Race trong cùng tenant

~~~mermaid
sequenceDiagram
    participant A as Node A
    participant B as Node B
    participant DB as Authorized Client Store
    participant OP as ACME Token Endpoint

    A->>DB: load RT-A1
    B->>DB: load RT-A1
    A->>OP: refresh RT-A1
    B->>OP: refresh RT-A1
    OP-->>A: AT-A2, RT-A2
    OP-->>B: invalid_grant / provider behavior
    A->>DB: save RT-A2
    B->>DB: failure handler must not delete newer RT-A2
~~~

Mitigations khi tải cao:

- Single-flight/locking per tenant+registration+principal.
- Optimistic versioning và compare-and-update.
- Failure cleanup có thế hệ token/known version.
- Token endpoint rate limiting và timeout.
- Không khóa toàn bộ mọi tenants vì một client đang refresh.

Local `synchronized` không bảo vệ race giữa nhiều pods.

### 11.2. Phân biệt lỗi

| Error | Tầng | Hướng xử lý |
|---|---|---|
| `invalid_grant` | Token endpoint | Refresh token/code không hợp lệ; cleanup theo policy |
| `invalid_client` | Token endpoint | Secret/client auth sai, xem registration |
| `401 invalid_token` | Resource Server | Access token bị từ chối; xem correct client/token |
| `403 insufficient_scope` | Resource Server | Thiếu quyền, không retry để nâng quyền |
| HTTP 503/timeout | Transport/AS/API | Lỗi hạ tầng, không mặc định xóa token |

Không xóa authorized clients của mọi tenants chỉ vì một request gặp 503.

## 12. Chọn token bằng manager trong Servlet request

Ví dụ sau chỉ mang tính mô tả contract; `tenantBinding` phải được registry/policy cấp sau khi user được xác minh:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

String registrationId = tenantBinding.loginRegistrationId();

OAuth2AuthorizeRequest authorization = OAuth2AuthorizeRequest
    .withClientRegistrationId(registrationId)
    .principal(authentication)
    .build();

OAuth2AuthorizedClient authorizedClient =
    authorizedClientManager.authorize(authorization);
~~~

Điều kiện:

1. Tenant đã được xác minh membership.
2. Registration thuộc tenant đúng.
3. Authentication được Spring Security xác thực.
4. User-delegated token thực sự được cấp cho registration/tenant đó.
5. Manager/repository phù hợp Servlet request context.

**Không tự gọi manager của registration GLOBEX với principal ACME chỉ để mong có quyền GLOBEX.** Nếu cần quyền user ở tenant khác, phải có authorization/consent tương ứng.

### 12.1. Manager cho background jobs

Một task dùng client_credentials không có HttpServletRequest thường cần:

~~~java
AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

với provider `clientCredentials()`:

~~~java
OAuth2AuthorizeRequest serviceRequest = OAuth2AuthorizeRequest
    .withClientRegistrationId("reports-acme-service")
    .principal("reports-job:acme")
    .build();
~~~

`reports-job:acme` là service storage principal, không phải người dùng được IdP xác thực. Tenant identity của job cần đến từ trusted job configuration/validated message metadata.

## 13. WebClient/RestClient: token đúng nhưng URL sai vẫn nguy hiểm

Một HTTP gateway phải chọn **cả registration và destination** từ tenant catalog đáng tin:

~~~text
ACME:
  portal-acme -> https://reports.acme.example

GLOBEX:
  portal-globex -> https://reports.globex.example
~~~

Không làm:

~~~java
String target = request.getParameter("target");
webClient.get().uri(target)
    .headers(h -> h.setBearerAuth(token))
    .retrieve();
~~~

Đây là nguy cơ SSRF/credential exfiltration.

### 13.1. Domain DTO cho tenant registry

~~~java
public record TenantOAuthBinding(
    String tenantId,
    String loginRegistrationId,
    String serviceRegistrationId,
    java.net.URI reportsApiBaseUri
) {}
~~~

Đây là **kiểu do ứng dụng định nghĩa**. Registry phải validate URI HTTPS, active tenant, allowlisted clients/destinations và lưu trữ.

### 13.2. Gateway minh họa checks trước token use

~~~java
package com.example.portal.reports;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class TenantReportsGateway {
    private final TenantRegistry registry;
    private final TenantAccessPolicy policy;
    private final OAuth2AuthorizedClientManager manager;
    private final WebClient.Builder webClientBuilder;

    public TenantReportsGateway(
        TenantRegistry registry,
        TenantAccessPolicy policy,
        OAuth2AuthorizedClientManager manager,
        WebClient.Builder webClientBuilder
    ) {
        this.registry = registry;
        this.policy = policy;
        this.manager = manager;
        this.webClientBuilder = webClientBuilder;
    }

    // Được gọi trong Servlet request đã authenticated.
    public Mono<String> readReport(
        String candidateTenant,
        Authentication authentication
    ) {
        TenantOAuthBinding binding =
            registry.requireActiveTenant(candidateTenant);

        // Bắt buộc xác minh quyền trước khi lấy token của tenant.
        policy.assertCanReadReports(
            authentication, binding.tenantId());

        // Nếu cần delegated token, login phải bound đúng tenant.
        policy.assertLoginBoundToTenant(
            authentication,
            binding.tenantId(),
            binding.loginRegistrationId());

        OAuth2AuthorizeRequest authorization =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(binding.loginRegistrationId())
                .principal(authentication)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(authorization);
        if (client == null) {
            return Mono.error(new IllegalStateException(
                "Tenant authorized client unavailable"));
        }

        // API URI đến từ registry tin cậy, không từ input browser.
        return webClientBuilder
            .baseUrl(binding.reportsApiBaseUri().toString())
            .build()
            .get()
            .uri("/api/reports")
            .headers(h -> h.setBearerAuth(
                client.getAccessToken().getTokenValue()))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

`TenantRegistry` và `TenantAccessPolicy` là **application services chưa được định nghĩa trong snippet**:

~~~java
public interface TenantRegistry {
    TenantOAuthBinding requireActiveTenant(String tenantId);
}

public interface TenantAccessPolicy {
    void assertCanReadReports(
        Authentication authentication, String tenantId);
    void assertLoginBoundToTenant(
        Authentication authentication,
        String tenantId,
        String expectedRegistrationId);
}
~~~

Đây là ví dụ thứ tự security checks, không phải project chạy độc lập. Production nên quản lý WebClient/connection pools theo lifecycle thay vì tạo HTTP client tùy tiện ở mỗi request. Với Servlet + WebClient asynchronous, manager cần Servlet/security context phù hợp ở thời điểm `authorize()`.

### 13.3. Không forward Bearer token sang redirect host ngoài allowlist

Nếu downstream API trả redirect tới hostname khác, HTTP client không được tự gửi Bearer token sang host lạ. Base URL cố định không tự ngăn absolute URIs do input đưa vào; vẫn cần destination validation.

## 14. Session isolation: session cookie không phải access token

Một browser request:

~~~http
Cookie: JSESSIONID=<opaque-id>
~~~

thường chỉ mang **session identifier**. Server-side `HttpSession` giữ `SecurityContext` và có thể chứa `OAuth2AuthorizationRequest` trong login flow. Authorized-client repository/service giữ access/refresh token theo cấu hình.

### 14.1. Ba storage/lifecycle khác nhau

~~~text
Browser:
  opaque session cookie

Portal session store:
  session ID, authenticated identity, active/bound tenant
  state/nonce/PKCE correlation while login pending

OAuth2 authorized-client store:
  tenant + registration + principal -> access/refresh tokens
~~~

Session TTL không đồng nghĩa token TTL. Browser logout local không tự revoke token ở OP.

### 14.2. Mô hình session theo tenants

| Mô hình | Ưu điểm | Rủi ro/cần làm |
|---|---|---|
| Subdomain riêng + host-only cookie | Browser tự tách phạm vi cookie | HTTPS, callback/host binding đúng |
| Origin riêng | Isolation browser mạnh hơn | Cấu hình DNS/cert/routing |
| Chung host, tenant trong URL path | Deployment đơn giản | Server-side session tenant partition bắt buộc |
| Chung session với active tenant | Dễ chuyển tenant | Recheck membership + token/context switching |
| Session store tách theo tenant | Giảm blast radius | Quản trị multi-store/TTL/lookup |

Cookie Path/Domain là **browser transport policy**, không phải authorization decision.

## 15. Host-only cookie và prefix __Host-

Với:

~~~text
https://acme.portal.example.com
https://globex.portal.example.com
~~~

nên cân nhắc session cookie **host-only**:

~~~http
Set-Cookie: __Host-SESSION=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix `__Host-` yêu cầu Secure, Path=/ và không có Domain. Browser sẽ không gửi host-only cookie của ACME cho hostname GLOBEX.

### 15.1. Vì sao không đặt Domain chung?

~~~http
Set-Cookie: SESSION=abc; Domain=portal.example.com; Path=/; Secure
~~~

có thể khiến cookie được gửi tới nhiều tenant subdomains. Khi đó server phải kiểm soát nghiêm session tenant binding; mở Domain rộng không phải cách tạo IdP SSO.

SSO ở OpenID Provider có cookie riêng của IdP. **Không cần chia sẻ Portal session cookie giữa tenants để dùng chung IdP SSO.**

### 15.2. Shared host theo path

~~~text
https://portal.example.com/t/acme/
https://portal.example.com/t/globex/
~~~

có thể dùng chung browser session. Session phải lưu `boundTenantId`/active tenant và kiểm tra membership trên mỗi request. Đặt Cookie Path hẹp **không thay** backend RBAC/tenant checks.

## 16. SameSite, OAuth callback và tenant correlation

Authorization Code Flow của ACME:

~~~text
GET /oauth2/authorization/portal-acme
  -> generate state=S-A
  -> save original authorization request in ACME session
  -> redirect to ACME OpenID Provider
  -> browser callback /login/oauth2/code/portal-acme?code=...&state=S-A
~~~

Browser phải gửi đúng cookie session để Spring Security tìm lại authorization request gốc.

### 16.1. Bảng SameSite

| SameSite | Cross-site top-level GET callback | Cross-site form_post POST |
|---|---|---|
| Strict | Thường không gửi cookie | Không gửi |
| Lax | Thường gửi cookie | Thường không gửi |
| None; Secure | Có thể gửi | Có thể gửi, còn browser privacy/CSRF policy |

Với GET callback, Lax thường thực dụng. Với OIDC `response_mode=form_post` cần xem cookie None; Secure và CSRF callback POST handling có chủ đích. **Không tắt CSRF toàn app, state, nonce hoặc PKCE để chữa callback.**

### 16.2. Cookie host mismatch

Nếu ACME bắt đầu ở:

~~~text
https://acme.portal.example.com/oauth2/authorization/portal-acme
~~~

nhưng callback tới:

~~~text
https://globex.portal.example.com/login/oauth2/code/portal-acme
~~~

browser không gửi ACME host-only cookie, và callback host/registration cũng lệch. Sửa redirect URI, public host/proxy và tenant binding; không mở cookie Domain bừa bãi.

## 17. Bind session và OAuth authorization request với tenant

Một mô hình server-side session:

~~~text
sessionId
boundTenantId
authenticatedInternalUserId
authenticationIssuer
authenticationSubject
loginRegistrationId
securityContext
createdAt / lastAccessedAt
~~~

Đây là **application model**, không phải fields mặc định của `HttpSession`.

Tại callback cần đối chiếu:

~~~text
expectedTenant from original authorization request
expectedRegistrationId
expectedIssuer
state
nonce
PKCE code_verifier
redirect URI
~~~

Không cho callback query `?tenant=globex` tự thay expected tenant của state ACME.

### 17.1. OAuth mix-up

Khi nhiều Authorization Servers được hỗ trợ, app phải tránh xử lý authorization response của issuer A bằng token endpoint/client của issuer B. Sử dụng state-bound original request, registration/issuer binding, callback validation và OIDC issuer/ID Token checks; nếu giao thức có issuer identification trong authorization response, kiểm tra theo chuẩn phù hợp.

**Không tự chọn token endpoint từ một issuer URL chưa xác minh trong callback.**

### 17.2. Session fixation protection

Spring Security có thể rotate session ID sau authentication:

~~~text
Before login: S1
After login: S2
~~~

Đây có thể là hành vi bảo mật đúng. Quan trọng là S1 đúng tenant trong callback và S2 vẫn giữ tenant-bound authenticated context sau login.

### 17.3. Multiple tabs và concurrent logins

Nếu tab A bắt đầu ACME login và tab B bắt đầu GLOBEX login gần nhau trong một shared session, authorization-request repository có thể gặp overwrite/collision tùy implementation. Khi cần multi-flow support, thiết kế pending requests keyed theo state/tenant với TTL và replay protection, không dùng một global `pending_oauth_request` cho mọi attempts.

## 18. Cấu hình Spring Boot Servlet session cookie

~~~yaml
# application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-SESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

Đây là cấu hình chung ở application/container. Khi mỗi tenant có host riêng, host-only cookies được browser phân biệt theo hostname.

Nếu chung host, cấu hình này **không tự tạo session tenant partitions**; cần explicit server-side binding hoặc tách origins.

### 18.1. Spring Session cookie serializer

Khi ứng dụng dùng Spring Session Redis/JDBC:

~~~java
@Bean
CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer =
        new DefaultCookieSerializer();
    serializer.setCookieName("__Host-SESSION");
    serializer.setCookiePath("/");
    serializer.setUseSecureCookie(true);
    serializer.setUseHttpOnlyCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
~~~

Đây là snippet minh họa, cần dependency/bean imports của Spring Session. Không đặt `Domain` nếu dùng `__Host-` cookie. Kiểm tra `Set-Cookie` thật ở browser; Spring Session có thể dùng cookie `SESSION` khác `JSESSIONID` của container.

### 18.2. Multi-node session storage

Nếu Node A tạo OAuth authorization request rồi callback đến Node B mà B không có server-side session, flow vẫn thất bại dù cookie đúng. Dùng shared Spring Session store hoặc routing strategy có chủ đích; **SameSite không sửa session store inconsistency**.

Nếu session store chung nhiều tenants, bảo vệ cả key namespace và backend tenant binding.

## 19. Identity isolation: từ OIDC (iss, sub) tới tenant membership

Trong OIDC, `sub` chỉ được hiểu trong ngữ cảnh issuer. Với tenant data, một logical identity key thường là:

~~~text
(tenantId, issuer, subject)
~~~

Ví dụ:

~~~text
ACME:
  tenantId = acme
  iss = https://login.acme.example/oidc
  sub = 42

GLOBEX:
  tenantId = globex
  iss = https://identity.globex.example/oidc
  sub = 42
~~~

Hai `sub=42` không chứng minh hai identities là cùng người khi issuers khác nhau. Nếu cùng issuer và subject, membership ở từng tenant vẫn độc lập.

### 19.1. Internal user vs tenant memberships

Một thiết kế:

~~~text
app_user:
  global internal user ID

tenant_membership:
  tenant ID
  user ID
  role
  status

external_identity:
  tenant ID
  issuer
  subject
  mapped internal user ID
~~~

User có thể có cùng internal ID trong ACME/GLOBEX nhưng role khác nhau. Không áp dụng một global `ROLE_ADMIN` cho mọi tenants nếu policy là tenant-scoped.

### 19.2. Email không phải stable identity key

Email có thể đổi, chưa verified, bị tái cấp hoặc trùng. Không tự map hai accounts chỉ vì:

~~~text
email = alice@example.com
~~~

Account linking cần verified identity evidence hoặc authoritative mapping, không chỉ email string.

### 19.3. Pairwise OIDC subjects

Một OP có thể cấp pairwise `sub` khác theo sector/client registration ngay cả với cùng người. Cùng email và issuer nhưng khác `sub` không được auto-link; khác subject cũng không đủ kết luận là người khác. Cần explicit/authoritative linking policy.

## 20. SQL schema tham khảo

Đây là **schema do ứng dụng tự thiết kế**, không phải bảng mặc định Spring Security:

~~~sql
CREATE TABLE tenant (
    id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE app_user (
    id VARCHAR(80) PRIMARY KEY
);

CREATE TABLE tenant_membership (
    tenant_id VARCHAR(80) NOT NULL,
    app_user_id VARCHAR(80) NOT NULL,
    status VARCHAR(30) NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (tenant_id, app_user_id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
    FOREIGN KEY (app_user_id) REFERENCES app_user(id)
);

CREATE TABLE external_identity (
    id VARCHAR(80) PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    app_user_id VARCHAR(80) NOT NULL,
    UNIQUE (tenant_id, issuer, subject),
    FOREIGN KEY (tenant_id, app_user_id)
        REFERENCES tenant_membership(tenant_id, app_user_id)
);

CREATE TABLE tenant_oauth_registration (
    tenant_id VARCHAR(80) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    client_id VARCHAR(256) NOT NULL,
    secret_ref VARCHAR(512),
    registration_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (tenant_id, registration_id),
    UNIQUE (registration_id),
    FOREIGN KEY (tenant_id) REFERENCES tenant(id)
);

CREATE TABLE tenant_authorized_client (
    tenant_id VARCHAR(80) NOT NULL,
    registration_id VARCHAR(120) NOT NULL,
    principal_key VARCHAR(256) NOT NULL,
    encrypted_access_token BLOB,
    encrypted_refresh_token BLOB,
    expires_at TIMESTAMP,
    token_generation BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, registration_id, principal_key),
    FOREIGN KEY (tenant_id, registration_id)
        REFERENCES tenant_oauth_registration(tenant_id, registration_id)
);
~~~

SQL chỉ minh họa thiết kế; kiểu `BLOB`, foreign keys và timestamps cần điều chỉnh theo DBMS. Cột `encrypted_access_token` phải thực sự được mã hóa bởi storage adapter/KMS, không phải chỉ đổi tên.

### 20.1. Vì sao UNIQUE(registration_id)?

Một `ClientRegistrationRepository` chung được tra bằng registrationId, không có tenant param. Unique ID trên phạm vi repository/store giúp tránh việc một client `portal` ở ACME ghi đè client `portal` ở GLOBEX.

### 20.2. Query phải luôn mang tenant predicate

Không chỉ:

~~~sql
SELECT * FROM invoice WHERE id = :invoiceId;
~~~

Mà:

~~~sql
SELECT *
FROM invoice
WHERE tenant_id = :authorizedTenantId
  AND id = :invoiceId;
~~~

`:authorizedTenantId` phải được backend xác minh, không copy nguyên query param.

### 20.3. Row-Level Security là defense-in-depth

PostgreSQL RLS có thể thêm một lớp tenant filter tại DB. Nhưng cần quản lý connection pool tenant context, transaction lifetime, roles bypass RLS và các privileged/admin operations. RLS không thay application authorization hoặc external identity validation.

## 21. Cache, object storage, search và queues cũng phải tách

| Nơi lưu | Anti-pattern | Thiết kế cần xem xét |
|---|---|---|
| Redis cache | `report:100` | `tenant:acme:report:100` + ACL |
| OAuth cache | `alice` | Tenant+registration+principal |
| Search index | Query không tenant filter | Tenant-scoped search & authorization |
| Object storage | `reports/2026.pdf` | Bucket/path/ACL + tenant binding |
| Queue | Job chỉ có userId | Authenticated producer + tenant & authorization context |
| CDN | Cache private response public | Private/no-store or correctly partitioned cache |
| Logs/traces | Token/email in labels | Safe IDs, redaction, cardinality controls |

**Cache prefix không tự giải quyết việc backend có quyền đọc mọi data.** Need authorization và store policies.

## 22. Tenant switching phải bảo toàn quyền và token context

Giả sử người dùng là member của cả ACME và GLOBEX, chọn “Switch tenant”:

~~~http
POST /api/tenant/switch HTTP/1.1
Content-Type: application/json
Cookie: __Host-SESSION=<opaque>

{"tenantId":"globex"}
~~~

Backend phải:

1. Xác thực request và áp CSRF protection cho session-based actions.
2. Kiểm tra active membership ở GLOBEX.
3. Xác định login/consent của GLOBEX đã tồn tại chưa.
4. Không dùng ACME delegated token cho GLOBEX API.
5. Cập nhật activeTenant trong session/transaction nhất quán.
6. Xóa request caches/derived data thuộc ACME.
7. Lấy role/permissions của GLOBEX và audit chuyển tenant.

Không chỉ chạy:

~~~java
session.setAttribute("activeTenant", request.getTenantId());
~~~

rồi dùng mọi quyền trước đó. Chuyển context không tự cấp quyền.

### 22.1. Hai subdomains

Nếu tenant URLs khác host, có thể redirect tới GLOBEX host; browser host-only cookies giúp tách sessions. IdP có thể tái sử dụng SSO, nhưng GLOBEX vẫn cần authorization request/callback và membership checks riêng.

### 22.2. Một host chung

Nếu cùng `portal.example.com` và chỉ khác path, session cookie thường chung. Khi đó server-side tenant binding/active tenant policy và tenant-scoped data access phải được triển khai cực kỳ cẩn thận.

## 23. Phân quyền tenant-specific khác phân quyền toàn cục

Một user có thể:

~~~text
Tenant ACME:
  role = REPORTS_ADMIN

Tenant GLOBEX:
  role = REPORTS_VIEWER
~~~

Không gắn `ROLE_REPORTS_ADMIN` vào Authentication rồi cho mọi tenant dữ liệu nếu role thực chất là tenant-scoped.

Một policy interface minh họa:

~~~java
public interface TenantAuthorizationService {
    void requireMembership(
        Authentication authentication, String tenantId);

    void requirePermission(
        Authentication authentication,
        String tenantId,
        String permission);

    void requireResourceOwnership(
        String tenantId, String resourceId);
}
~~~

`@PreAuthorize("hasRole('ADMIN')")` chưa tự biết tenant nào; có thể cần custom authorization bean/method security kiểm tra membership và resource ownership.

### 23.1. Disabled membership

User có thể bị disable ở ACME nhưng vẫn active ở GLOBEX. OIDC authentication thành công không tự chứng minh membership ACME còn active.

### 23.2. Tenant claim từ token

Nếu IdP phát `tenant_id` claim, phải xác minh token và mapping claim tới tenant policy. Không tin header hoặc unverified JWT payload tự khai tenant.

## 24. Session logout, OAuth token cleanup và OP logout là ba việc khác

Khi user logout ACME:

~~~text
ACME browser session: invalidate.
ACME authorized clients: cleanup/revoke theo policy.
ACME OP SSO session: logout nếu cần/OP hỗ trợ.
GLOBEX state: không tự hủy nếu không có policy chung.
~~~

### 24.1. Local cleanup không revoke token ở AS

Xóa `OAuth2AuthorizedClient` khỏi database không chắc token đã bị thu hồi tại Authorization Server. Cần token revocation endpoint hoặc OP policy riêng nếu yêu cầu.

### 24.2. Back-channel logout

Nếu nhận back-channel logout từ một OP, kiểm tra issuer, signature, audience, logout token event/subject/session binding và map đúng tenant/registration. Không tìm sessions bằng email rồi hủy mọi tenants.

### 24.3. Deprovision tenant

Một quy trình gồm:

- Ngừng login và token authorization mới cho tenant.
- Disable service jobs/queue consumers liên quan.
- Rotate/revoke client secrets và authorized clients theo policy.
- Invalidate sessions và cache.
- Ngăn API/business data access.
- Xóa/retain identity/business records theo luật và data retention.
- Rà soát backups, object storage, logs và search indexes.
- Audit việc deprovision, tránh ảnh hưởng tenants khác.

## 25. Encryption, KMS và blast radius

Khi shared database lưu token/PII, có thể dùng envelope encryption:

~~~text
ACME ciphertext -> data key A -> KMS policy/key A
GLOBEX ciphertext -> data key G -> KMS policy/key G
~~~

Thiết kế có thể giảm phạm vi ảnh hưởng nếu một key bị lộ, nhưng phải có:

- KMS IAM và quyền decrypt theo workload.
- Key rotation và versioning.
- Audit key use.
- Backup/recovery an toàn.
- Chính sách xóa keys/data khi tenant deprovision.

**Per-tenant KMS key không đủ** nếu app process có quyền decrypt tất cả tenants và user-controlled tenant ID quyết định key nào được dùng.

## 26. Reactive / WebFlux: không dùng ThreadLocal tenant bừa bãi

Spring WebFlux dùng Reactive SecurityContext/Reactor Context; không nên giữ tenant hiện tại trong static mutable variable hoặc dựa vào ThreadLocal mặc định khi pipeline đổi scheduler.

### 26.1. Các thành phần tương ứng

| Servlet | Reactive |
|---|---|
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| `HttpServletRequest` context | `ServerWebExchange` / Reactor context |

Service-based manager dành cho background jobs; manager của web request dùng repository và request context phù hợp.

### 26.2. Truyền authorized tenant rõ ràng

~~~java
public Mono<String> readReport(
    String candidateTenant,
    Authentication principal
) {
    return tenantPolicy.verify(candidateTenant, principal)
        .flatMap(authorizedTenant ->
            tenantGateway.readWithTenantRegistration(
                authorizedTenant, principal));
}
~~~

`tenantPolicy`/`tenantGateway` là application services, không phải built-ins. `verify()` trả immutable authorized tenant context. **Reactor Context chỉ vận chuyển dữ liệu; nó không tự chứng minh dữ liệu tenant đáng tin.**

## 27. Test cross-tenant isolation: negative tests quan trọng hơn happy path

| Kịch bản | Kết quả cần đảm bảo |
|---|---|
| ACME user request tenant=globex | 403 trước khi lấy GLOBEX token |
| ACME session cookie tới GLOBEX host | Host-only cookie không match |
| OAuth state ACME tới callback GLOBEX | Từ chối, không đổi sang GLOBEX registration |
| ACME ID Token có issuer GLOBEX | Reject wrong issuer |
| ACME AT gọi GLOBEX API | Resource Server từ chối audience/tenant |
| Hai users cùng username ở hai tenants | Không collision authorized-client store |
| Hai external users cùng email | Không auto-link |
| ACME RT rotate | Không overwrite GLOBEX RT |
| ACME invalid_grant cleanup | Không xóa GLOBEX authorized client |
| Admin role ACME, viewer GLOBEX | Không có admin quyền ở GLOBEX |
| Tenant suspended | Session/token còn cũng không được đọc dữ liệu |
| ACME secret rotation | GLOBEX token client không bị đổi secret |
| Resource ID giống ở hai tenants | Query/cache chỉ trả authorized tenant |
| Two pods refresh cùng token | Không xóa token mới vì stale failure |
| Spoofed X-Forwarded-Host | Không đổi authorized tenant/issuer |
| Dynamic issuer là localhost | Onboarding từ chối/SSRF prevention |

### 27.1. Unit test authorization rule

~~~java
@Test
void acmeUserCannotUseGlobexAuthorizedClient() {
    Authentication acme = authenticatedAcmeFixture();

    assertThrows(AccessDeniedException.class, () ->
        tenantPolicy.assertCanReadReports(acme, "globex"));
}
~~~

Đây là **test fragment**; `authenticatedAcmeFixture()` và `tenantPolicy` do application/test định nghĩa. Test cần kiểm tra policy fail trước khi manager/secret store được gọi.

### 27.2. Test authorized-client store key

~~~text
Given:
  (acme, portal-acme, alice) -> AT-A
  (globex, portal-globex, alice) -> AT-G

Then:
  load ACME returns AT-A
  load GLOBEX returns AT-G
  removing ACME does not remove GLOBEX
~~~

Nếu dùng Spring Security default service với key `(registrationId, principalName)`, xác minh registration IDs unique theo tenant trong store chung.

### 27.3. Test callback mix-up

~~~text
Given: authorization request ACME, state=S-A
When:  callback /login/oauth2/code/portal-globex uses S-A
Then:  must not authenticate as GLOBEX
~~~

Không tắt state/nonce/PKCE/issuer validation chỉ để integration tests dễ viết.

## 28. Kịch bản lỗi: token cache keyed bằng username

Giả sử:

~~~java
cache.put(authentication.getName(), authorizedClient);
~~~

ACME/GLOBEX đều có `alice`. Các thao tác nối tiếp có thể ghi đè token. Kết quả một request ACME mang GLOBEX token:

- Resource Server đúng sẽ từ chối, nhưng client vẫn đã vi phạm credential isolation.
- Resource Server cấu hình sai có thể rò rỉ dữ liệu.
- Cleanup token sai còn gây logout/re-authorization hàng loạt.

Khắc phục:

1. Dừng cache key thiếu tenant/registration.
2. Invalidate các entries đã có thể bị nhiễm.
3. Xác định affected sessions/tokens/requests bằng audit.
4. Rotate/revoke credentials khi cần.
5. Thêm negative tests cho trùng principal names.

**401 từ Resource Server không có nghĩa hệ thống chưa gặp vấn đề bảo mật.**

## 29. Kịch bản lỗi: cookie Domain rộng cho mọi tenants

Một cookie:

~~~http
Set-Cookie: SESSION=abc; Domain=portal.example.com; Secure; HttpOnly
~~~

có thể được gửi tới nhiều subdomains. Nếu server chỉ tra session ID rồi cho phép tenant theo request host, có thể gây session confusion.

Giải pháp:

- Host-only cookies nếu tenants nằm ở subdomains.
- Bound tenant ID trong server-side session.
- Từ chối request có tenant khác session unless có switch flow được authorize.
- Giữ state/registration/issuer correlation ở callback.
- Không dùng cookie Path/Domain như thay authorization.

## 30. Tenant kill switch và incident response

Một SaaS cần khả năng suspend tenant:

~~~text
tenant.status = SUSPENDED
~~~

Hệ thống phải:

1. Từ chối OAuth login initiation mới theo tenant.
2. Ngừng tự cấp service token mới.
3. Chặn mọi business API access tại authorization layer.
4. Invalidate tenant sessions theo policy.
5. Cleanup/revoke authorized clients và rotate secrets nếu cần.
6. Dừng jobs/queues/webhooks liên quan.
7. Audit và xác minh không ảnh hưởng tenants khác.

**Chỉ xóa ClientRegistration không đủ**, vì user có thể còn session/token và Resource Server vẫn phục vụ data.

### 30.1. Tenant-scoped và global incidents

Secret ACME bị lộ có thể chỉ ảnh hưởng ACME nếu isolation đúng. Nhưng một bug global cache key làm trộn authorized clients có thể cần điều tra toàn bộ SaaS, không chỉ tenant phát hiện đầu tiên.

## 31. Monitoring/audit không lộ secrets

Metrics/events nên phân biệt:

~~~text
oauth.login.failure{tenant=acme,registration=portal-acme}
oauth.token.refresh.failure{tenant=globex,registration=portal-globex}
tenant.authorization.denied{tenant=acme,reason=cross_tenant}
session.tenant_mismatch{tenant=globex}
secret.rotation.event{tenant=acme,registration=portal-acme}
~~~

Các tên này là **ví dụ instrument do ứng dụng tạo**, không phải mặc định Spring Security phát tất cả.

Không log:

~~~text
client_secret=<actual>
access_token=<actual>
refresh_token=<actual>
private_key=<actual>
Cookie: SESSION=<actual>
Authorization: Bearer <actual>
authorization_code=<actual>
OIDC id_token=<actual>
~~~

Audit nên ghi tenant ID, registration ID, internal user ID đã kiểm soát, action, resource ID, allow/deny decision, correlation ID và timestamp. Không đưa email/subject/token vào metric labels quá chi tiết.

## 32. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| ACME user thấy GLOBEX data | Tenant filter/RBAC/cache thiếu | Kiểm tra query, policy, RLS |
| Token bị hoán đổi giữa tenants | Key thiếu tenant/registration | Sửa store key và invalidate cache |
| Chỉ ACME invalid_client | ACME client secret sai/rotate | Kiểm tra Vault và IAM record |
| Cả tenants invalid_client | Secret resolver/cấu hình global lỗi | Kiểm tra deployment |
| Callback ACME vào GLOBEX | Redirect/correlation sai | Kiểm tra state, issuer, host, registration |
| authorization_request_not_found | Cookie/session store hoặc concurrent login | Browser DevTools/Redis |
| Browser gửi cookie A sang B | Domain cookie rộng | Host-only + server tenant binding |
| User admin ACME có quyền admin GLOBEX | Role không tenant-scoped | Membership/RBAC policy |
| Users cùng email bị gộp | Auto-link bằng email | Dùng tenant+issuer+sub |
| Refresh ACME xóa GLOBEX token | Failure handler phạm vi rộng | Scoped cleanup/token generation |
| Tenant suspended vẫn đọc data | Chỉ disable login | Enforce status mỗi API request |
| X-Forwarded-Host đổi tenant | Header spoofing | Ingress strip/overwrite |
| Discovery gọi localhost | Dynamic issuer SSRF | Allowlist + network policy |
| Scale nhiều pods mới lỗi | Local session/token store | Shared storage |
| API 403 dù token hợp lệ | Scope/role/resource permission | Không retry token vô hạn |
| HTTP 503 làm mất mọi token | Error mapping/cleanup sai | Chỉ xử lý invalid token/grant |

### 32.1. Thứ tự điều tra

~~~text
Cross-tenant access / login / token failure
    |
    v
Tenant candidate đến từ đâu?
    |
    v
Authenticated principal + issuer/subject hợp lệ?
    |
    v
Tenant membership/resource permission được xác minh?
    |
    v
ClientRegistration thuộc đúng tenant?
    |
    v
Secret reference đúng tenant và version?
    |
    v
Authorized-client key đúng tenant+registration+principal?
    |
    v
Session/callback state/nonce/PKCE bound đúng tenant?
    |
    v
Downstream audience/URL và DB/cache tenant filtering đúng?
    |
    v
Kiểm tra rotation, revocation, concurrency và audit.
~~~

## 33. Các anti-pattern cần tránh

**1. Tin `X-Tenant-ID` hoặc query tenant như quyền truy cập.** Input cần membership/authorization.

**2. Cache token chỉ theo email/username.** Dễ collision giữa issuers/tenants.

**3. Một client secret global cho nhiều independent clients.** Tăng blast radius và có thể sai contract.

**4. Lưu raw secrets trong tenant database và cấp quyền đọc không giới hạn.** Dùng secret manager/ACL.

**5. Cho user tự chọn OAuth registration/issuer/token endpoint bất kỳ.** Dễ SSRF/confused deputy.

**6. Dùng ACME token gọi GLOBEX API vì cùng provider.** Audience/scope/tenant rights khác.

**7. Cookie Domain rộng để “chia sẻ SSO”.** SSO của OP khác Portal session.

**8. Không bind tenant vào state/authorization request.** Nguy cơ callback mix-up.

**9. Auto-link user bằng email.** Không ổn định/không luôn verified.

**10. Áp ROLE_ADMIN toàn cục cho mọi tenants.** Quyền thường có phạm vi tenant.

**11. Query resource chỉ theo id, bỏ tenant_id.** Dẫn tới IDOR/cross-tenant disclosure.

**12. Xóa mọi tokens khi một tenant invalid_grant/503.** Cleanup phải scoped.

**13. Tắt CSRF/state/nonce/PKCE để login đa tenant dễ chạy.** Làm yếu bảo mật.

**14. Cho rằng per-tenant KMS key là đủ khi backend có decrypt-all quyền.** Cần IAM/authorization.

**15. Chỉ test happy path.** Phải test người dùng tenant A không thể dùng secret/token/session/data B.

## 34. Bài tập thực hành

### Bài 1 — Tenant từ query

~~~http
GET /api/reports?tenant=globex HTTP/1.1
Cookie: __Host-SESSION=<acme-session>
~~~

**Câu hỏi:** Có nên lấy GLOBEX token ngay không?

**Đáp án:** Không. Cần xác minh user membership/permissions tại GLOBEX và token của login/grant tương ứng trước.

### Bài 2 — Token cache key

~~~text
key = issuer + ":" + username
~~~

**Câu hỏi:** Vì sao chưa đủ?

**Đáp án:** Một issuer có nhiều clients/tenants, và username có thể trùng. Cần tenant+registration+trusted principal key hoặc partition tương đương.

### Bài 3 — Same issuer, khác tenants

ACME/GLOBEX dùng một issuer nhưng client IDs riêng.

**Câu hỏi:** Có dùng một provider configuration không?

**Đáp án:** Có nếu issuer/endpoints thật sự chung. Nhưng client registrations, secrets, authorized clients và tenant data vẫn độc lập.

### Bài 4 — Cookie Domain

~~~http
Set-Cookie: SESSION=...; Domain=portal.example.com; Secure; HttpOnly
~~~

**Câu hỏi:** Nguy cơ gì khi hai tenant ở hai subdomains?

**Đáp án:** Cookie có thể được gửi sang cả hai hosts. Dùng host-only cookie khi phù hợp và bắt buộc server session tenant binding.

### Bài 5 — RT rotation race

Node A đã lưu RT-A2; node B gặp invalid_grant từ RT-A1.

**Câu hỏi:** Có nên xóa toàn bộ ACME/GLOBEX authorized clients?

**Đáp án:** Không. Cần single-flight/version-aware cleanup theo đúng authorized client; không xóa token mới hoặc cross-tenant records.

### Bài 6 — Trùng email

~~~text
ACME: iss=A, sub=11, email=jane@example.com
GLOBEX: iss=G, sub=92, email=jane@example.com
~~~

**Câu hỏi:** Có tự gộp cùng internal user không?

**Đáp án:** Không. Dùng authoritative identity mapping/account linking; email không phải stable identity key.

### Bài 7 — SSO không phải tenant authorization

User đã login ACME; OP SSO trả nhanh callback GLOBEX nhưng user không có membership GLOBEX.

**Câu hỏi:** Cho truy cập GLOBEX không?

**Đáp án:** Không. Authentication/SSO thành công khác tenant membership và resource permission.

### Bài 8 — Dynamic issuer

Admin nhập issuer URL tùy ý khiến backend discovery ngay.

**Câu hỏi:** Rủi ro?

**Đáp án:** SSRF, metadata trust confusion. Cần allowlist/ownership verification, HTTPS, DNS/egress rules và issuer metadata validation.

### Bài 9 — Suspended tenant

Tenant bị suspend nhưng web session/access token còn hạn.

**Câu hỏi:** Chỉ xóa ClientRegistration có đủ?

**Đáp án:** Không. Phải enforce tenant.status và permissions trên API, invalidate sessions, dừng jobs và cleanup/revoke tokens theo policy.

### Bài 10 — Test isolation

ACME và GLOBEX có cùng principalName `alice`.

**Câu hỏi:** Kiểm thử tối thiểu?

**Đáp án:** Save/load/remove authorized client riêng, deny cross-tenant authorization, verify callback state/issuer, resource audience và DB/cache tenant filter.

## 35. Checklist triển khai

| Câu hỏi | Điều cần bảo đảm |
|---|---|
| Tenant IDs có canonical format? | Có, không nhận tự do |
| Tenant candidate được resolve từ nguồn nào? | Trusted routing/registry |
| User được authorize vào tenant chưa? | Membership/permission trước token use |
| Issuer metadata được verify? | Đúng issuer, HTTPS, anti-SSRF |
| Registration ID unique theo store? | Không collision |
| SecretRef theo tenant/registration/version? | Có |
| Vault/KMS ACL giới hạn? | Có |
| Client credential rotation riêng? | Có |
| Authorized-client key tenant-scoped? | Có |
| Token encrypted/ACL phù hợp? | Có |
| Refresh rotation/concurrency xử lý? | Có nếu cần |
| Failure handler scoped? | Không xóa toàn issuer |
| API destination allowlisted? | Có |
| Resource Server kiểm tra audience/scope? | Có |
| Session cookie Secure/HttpOnly? | Có ở production |
| Host-only cookie khi có subdomains? | Ưu tiên |
| Session bound tenant? | Có |
| OAuth state/nonce/PKCE đúng tenant? | Có |
| Proxy headers trusted? | Ingress strip/overwrite |
| Identity key theo (tenant,iss,sub)? | Có identity mapping phù hợp |
| Account linking kiểm chứng? | Không nối chỉ bằng email |
| Role/permission tenant-scoped? | Có |
| DB query và cache có tenant filter? | Có |
| Logout/deprovision có cleanup? | Có |
| Tenant kill switch đã test? | Có |
| Logs không lộ tokens/secrets? | Có |
| Cross-tenant negative tests? | Có |

## 36. Tổng kết

Trong **Spring Security OAuth 2.0/OIDC Client đa tenant**, tách **secret, token, session và dữ liệu định danh** là bài toán thiết kế xuyên suốt, không chỉ việc thêm tiền tố tenant trong YAML. **Secret** phải thuộc đúng tenant/registration và được quản lý qua secret manager/ACL. **OAuth2AuthorizedClient** phải được chọn/lưu theo registration/principal đã xác minh, có tenant namespace hoặc storage partition tương đương. **Browser session/cookie và OAuth callback** phải giữ đúng tenant, state, nonce, PKCE, registration và issuer. **Identity và business data** cần mapping theo tenant/issuer/subject, tenant membership, RBAC và resource ownership.

Nhiều tenants có thể **dùng chung một issuer** mà vẫn tách credentials, tokens, sessions và permissions. Ngược lại, nhiều issuers cần callback/issuer binding chặt để chống mix-up. Khi dùng shared database/Redis, phải bảo đảm composite keys, tenant-scoped authorization, encryption, ACL và cross-tenant negative tests.

**Nguyên tắc quan trọng nhất:** tenant do browser yêu cầu chỉ là **candidate**; tenant được backend xác minh quyền mới là **authorized tenant**. Mỗi thao tác lấy secret, load token, xác thực callback, đọc session hoặc truy vấn dữ liệu phải giữ ranh giới này. Đó là nền tảng giúp một sự cố của tenant được cô lập thay vì lan sang toàn bộ SaaS.
