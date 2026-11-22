# 22.5. Thiết kế OAuth2AuthorizedClientProvider cho grant tùy chỉnh

## 1. Bài toán: Authorization Server hỗ trợ một grant nhưng Spring Security chưa có provider tương ứng

Giả sử hệ thống **Employee Portal** dùng **Spring Boot 3 / Spring Security 6** và có một background worker cần gọi **Reports API**. Authorization Server của tổ chức chấp nhận một loại extension grant nội bộ, dùng **workload ticket** ngắn hạn do một dịch vụ tin cậy phát hành.

Thỏa thuận giao thức giữa OAuth2 Client và Authorization Server:

~~~text
registrationId = reports-with-ticket
grant_type     = urn:example:params:oauth:grant-type:workload-ticket
client_auth    = client_secret_basic (chỉ là một ví dụ)
workload_ticket = một ticket được ký, có audience, hạn dùng và anti-replay
scope          = reports.read (nếu được nhà cung cấp chấp nhận)
~~~

Luồng minh họa:

~~~mermaid
sequenceDiagram
    participant Job as Reports Worker
    participant Manager as OAuth2AuthorizedClientManager
    participant Provider as Custom OAuth2AuthorizedClientProvider
    participant Ticket as Trusted Ticket Issuer
    participant AS as Authorization Server
    participant API as Reports API

    Job->>Manager: authorize(reports-with-ticket, reports-worker)
    Manager->>Provider: authorize(OAuth2AuthorizationContext)
    Provider->>Provider: Kiểm tra grant type, existing token, expiry
    Provider->>Ticket: Xin workload ticket ngắn hạn
    Ticket-->>Provider: Signed ticket, one-time/short-lived
    Provider->>AS: POST token endpoint, custom grant
    AS-->>Provider: OAuth2AccessTokenResponse
    Provider-->>Manager: OAuth2AuthorizedClient mới
    Manager->>Manager: Lưu authorized client theo storage policy
    Manager-->>Job: Authorized client
    Job->>API: Authorization: Bearer access token
    API-->>Job: Báo cáo
~~~

**Vấn đề:** provider chain mặc định thường hỗ trợ các grant phổ biến như `authorization_code`, `refresh_token`, `client_credentials` và những grant khác theo phiên bản. Nó **không tự biết** cách tạo `workload_ticket` hay xử lý `urn:example:...`.

Muốn thêm grant, ta không nên viết token endpoint HTTP call rải rác trong controller hoặc gắn Bearer token bằng một cache tự phát. Ta nên thiết kế **`OAuth2AuthorizedClientProvider` riêng**, tích hợp với `OAuth2AuthorizedClientManager` và kho lưu authorized client của Spring Security.

> **Quan trọng:** Workload Ticket Grant trong bài là **giao thức giả lập để minh họa extension point**, không phải grant OAuth2 tiêu chuẩn và không được mặc nhiên hỗ trợ bởi mọi Authorization Server. Chỉ dùng custom grant khi Authorization Server **thật sự có contract**, đã được threat-model, phân quyền, xác minh ticket và thống nhất với nhóm bảo mật. Nếu một chuẩn hoặc provider có sẵn đáp ứng yêu cầu, hãy ưu tiên nó thay vì phát minh grant mới.

## 2. Mục tiêu thiết kế và ranh giới trách nhiệm

Sau bài học, bạn cần phân biệt được bốn trách nhiệm:

| Thành phần | Chức năng | Không nên làm |
|---|---|---|
| `ClientRegistration` | Mô tả client, grant type, token URI, scopes và client authentication | Không tự thực hiện grant |
| `OAuth2AuthorizedClientProvider` | Quyết định grant này có áp dụng và khi nào cần token mới; tạo `OAuth2AuthorizedClient` | Không tự sở hữu toàn bộ cache/session/database |
| `OAuth2AccessTokenResponseClient<T>` | Gửi request token endpoint theo giao thức và đọc `OAuth2AccessTokenResponse` | Không quyết định Authentication web của người dùng |
| `OAuth2AuthorizedClientManager` | Điều phối provider chain, tải/lưu authorized client và success/failure handlers | Không tự định nghĩa quyền nghiệp vụ của Resource Server |

Khi thiết kế grant tùy chỉnh, cần giải quyết các câu hỏi:

1. **Registration nào** được phép dùng grant?
2. **Nguồn bằng chứng** (ticket/assertion/subject token) đến từ đâu và có đáng tin không?
3. Provider nên thực hiện grant khi nào: **chưa có token**, **token sắp hết hạn**, **token bị revoke**?
4. Token response có được xác minh và chuyển thành đúng `OAuth2AuthorizedClient` không?
5. **PrincipalName** và **registrationId** có được giữ nhất quán khi lưu?
6. Lỗi nào cần retry, lỗi nào cần yêu cầu cấp quyền lại, lỗi nào cần xóa authorized client?
7. Flow có dùng được từ **Servlet**, **Reactive** và **background worker** không, hay phải có implementation tương ứng?

**Một OAuth2AuthorizedClientProvider tốt là một adapter giao thức có ranh giới rõ**, không phải “đoạn mã bất kỳ lấy được access token”.

## 3. Extension Grant trong OAuth 2.0 là gì?

Trong token request OAuth 2.0, tham số `grant_type` cho biết client muốn dùng cơ chế cấp quyền nào.

Một số giá trị quen thuộc:

~~~text
authorization_code
refresh_token
client_credentials
~~~

Các **extension grants** có thể dùng URI tuyệt đối định danh grant. Ví dụ một chuẩn đã được định nghĩa là:

~~~text
urn:ietf:params:oauth:grant-type:token-exchange
~~~

được mô tả trong **RFC 8693 — OAuth 2.0 Token Exchange**. Một chuẩn khác là JWT Bearer Authorization Grant của **RFC 7523**:

~~~text
urn:ietf:params:oauth:grant-type:jwt-bearer
~~~

Trong khi đó, URI của bài:

~~~text
urn:example:params:oauth:grant-type:workload-ticket
~~~

là **URI ví dụ mang tính giáo dục**. Nó **không** có nghĩa hệ thống đang triển khai đầy đủ Token Exchange hoặc JWT Bearer Grant theo RFC. Không thay đổi tên grant rồi kỳ vọng áp dụng được các quy tắc an ninh của một RFC khác.

### 3.1. Cần phân biệt grant tùy chỉnh và tham số tùy chỉnh

Hai trường hợp thường bị nhầm:

**Trường hợp A — Grant mới thật sự:**

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Aworkload-ticket
&workload_ticket=...
~~~

**Trường hợp B — Grant chuẩn nhưng thêm extension parameters:**

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&resource=https%3A%2F%2Freports.example.test
~~~

Trường hợp B có thể chỉ cần **tùy chỉnh request parameters converter** của token-response client/provider đã có; không nhất thiết viết `OAuth2AuthorizedClientProvider` mới.

**Quy tắc lựa chọn:** chỉ viết provider mới khi **điều kiện áp dụng grant, loại request, token exchange hoặc lifecycle** thực sự khác những grant Spring Security đã hỗ trợ.

### 3.2. Không nhầm “custom grant” với việc bypass Authorization Server

Grant tùy chỉnh vẫn phải:

- Gọi token endpoint của **Authorization Server tin cậy**.
- Xác thực OAuth client theo policy.
- Chuyển bằng chứng/credential qua HTTPS.
- Được Authorization Server thẩm định bằng chứng, audience, issuer, hạn dùng, chống replay và chính sách cấp quyền.
- Trả OAuth2 token response hợp lệ.
- Được Resource Server kiểm tra access token và authorization như bình thường.

Không nên tự ký một chuỗi rồi gán tên `access_token` ở Client nếu Authorization Server không phát hành/chấp nhận nó.

## 4. Kiến trúc mở rộng Spring Security OAuth2 Client

~~~mermaid
flowchart TD
    C["Service / Controller / Job"] --> A["OAuth2AuthorizeRequest"]
    A --> M["OAuth2AuthorizedClientManager"]
    M --> Reg["ClientRegistrationRepository"]
    M --> Store["OAuth2AuthorizedClientRepository / Service"]
    M --> Chain["Delegating OAuth2AuthorizedClientProvider"]
    Chain --> Code["Authorization Code Provider"]
    Chain --> Refresh["Refresh Token Provider"]
    Chain --> CC["Client Credentials Provider"]
    Chain --> Custom["Custom WorkloadTicketProvider"]
    Custom --> Ticket["TrustedTicketSupplier"]
    Custom --> TR["OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>"]
    TR --> AS["Authorization Server /token"]
    AS --> TR
    TR --> Custom
    Custom --> M
    M --> Store
    M --> C
    C --> API["Resource Server / Reports API"]
~~~

Khi **các providers** được ghép thành chuỗi, mỗi provider trả:

- **Một `OAuth2AuthorizedClient` mới** nếu nó thực hiện grant thành công.
- **`null`** nếu grant không áp dụng hoặc không cần cấp token mới trong contract đồng bộ.
- **Exception** nếu quá trình grant được chọn thất bại.

Manager không cần biết chi tiết `workload_ticket`; nó chỉ biết **provider chain** trả token, không có kết quả hoặc lỗi.

## 5. Hợp đồng OAuth2AuthorizedClientProvider

Trên Servlet/Spring Security OAuth2 Client đồng bộ, interface là:

~~~java
package org.springframework.security.oauth2.client;

public interface OAuth2AuthorizedClientProvider {
    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context
    );
}
~~~

Trong API thật, kết quả có thể là `null` theo contract. Diễn giải:

| Giá trị trả về | Nghĩa |
|---|---|
| `OAuth2AuthorizedClient` | Provider đã thực hiện grant/re-authorization và có authorized client kết quả |
| `null` | Provider không áp dụng hoặc không cần re-authorize; manager có thể giữ existing client hoặc thử provider kế tiếp |
| `OAuth2AuthorizationException` / lỗi phù hợp | Grant đã được chọn nhưng thất bại |

**Trả null không đồng nghĩa authentication thất bại.** Nếu token hiện tại còn hạn, custom provider thường trả null để manager tiếp tục sử dụng authorized client đã lưu.

### 5.1. OAuth2AuthorizationContext chứa gì?

Một context có thể cung cấp:

~~~java
ClientRegistration registration = context.getClientRegistration();
Authentication principal = context.getPrincipal();
OAuth2AuthorizedClient existing = context.getAuthorizedClient();
~~~

Và các **attributes** đã được manager ánh xạ. Context chỉ đáng tin ở mức **nguồn tạo ra nó**. Một attribute do browser tự nhập chưa được xác thực không được coi là signed assertion hay quyền của nhân viên.

### 5.2. Không dùng provider để đọc Session hoặc Principal một cách tùy tiện

Một custom provider có thể được gọi trong:

- Servlet request, có `HttpServletRequest` và SecurityContext.
- Background job, không có browser session.
- Test với `OAuth2AuthorizationContext` được tạo thủ công.

Nếu provider phụ thuộc ngầm vào `SecurityContextHolder` hoặc request thread, nó khó tái sử dụng và dễ lấy nhầm principal. **Ưu tiên dữ liệu từ `OAuth2AuthorizationContext` và nguồn dịch vụ đã được xác thực**.

## 6. Mô hình ví dụ: workload ticket được phát bởi dịch vụ tin cậy

Ta giả định tổ chức có một **Trusted Ticket Issuer** nội bộ. Issuer chỉ phát ticket cho workload đã xác thực và ticket có:

- **issuer** xác định rõ.
- **audience** trùng token endpoint/chính sách của Authorization Server.
- **subject/workload ID** ổn định.
- **issued-at/expiration** ngắn hạn.
- **unique ID** hoặc nonce chống phát lại.
- Chữ ký hoặc proof được Authorization Server xác minh.

Đây là **giả định phía server**, không phải Spring Security tự cung cấp. Mã giáo dục sẽ không tự triển khai ký JWT, key rotation hay xác minh ticket. Những yếu tố đó phải được đặc tả, kiểm thử và quản lý bởi nhóm bảo mật/IdP.

Một ticket có thể được tạo qua:

~~~java
public interface TrustedTicketSupplier {
    String issueFor(
        String clientRegistrationId,
        String trustedPrincipalName
    );
}
~~~

**Điểm tin cậy:** `trustedPrincipalName` phải do ứng dụng xác định, không phải `?user=admin` do người gọi HTTP tự chọn.

### 6.1. Vì sao không nhận ticket qua request attribute tùy ý?

Ví dụ nguy hiểm:

~~~java
// Không nên để browser tự đưa assertion mà provider coi là trusted.
String ticket = request.getAttribute("ticket");
~~~

Nếu cần truyền ticket từ một hệ thống ngoài, phải xác thực nguồn, binding tới client/principal/tenant, kiểm tra audience, TTL và anti-replay. Provider không được “nâng cấp” một chuỗi tùy ý thành credential đáng tin chỉ vì nó được đặt trong `OAuth2AuthorizeRequest`.

## 7. Khai báo AuthorizationGrantType riêng

Spring Security dùng `AuthorizationGrantType` để biểu diễn giá trị `grant_type`:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;

public final class WorkloadTicketGrant {
    private WorkloadTicketGrant() {}

    public static final AuthorizationGrantType TYPE =
        new AuthorizationGrantType(
            "urn:example:params:oauth:grant-type:workload-ticket"
        );
}
~~~

Trong triển khai thực tế, hãy dùng URI grant do Authorization Server của bạn **chính thức định nghĩa**, không copy URI giả lập ở trên vào production.

### 7.1. Kết nối grant type với ClientRegistration

~~~java
ClientRegistration registration =
    ClientRegistration.withRegistrationId("reports-with-ticket")
        .clientId("reports-ticket-client")
        .clientSecret("runtime-secret-placeholder")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(WorkloadTicketGrant.TYPE)
        .tokenUri("https://login.example.test/oauth2/token")
        .scope("reports.read")
        .build();
~~~

Client ID/secret ở đây chỉ là **fixture minh họa**. Với Spring Boot, registration thường đọc từ configuration + secret store, không hard-code như production.

## 8. Định nghĩa request type cho grant tùy chỉnh

Một `OAuth2AccessTokenResponseClient<T>` có type parameter là request grant. Thiết kế class riêng giúp compiler và code phân biệt grant tùy chỉnh với `OAuth2ClientCredentialsGrantRequest` hoặc `OAuth2RefreshTokenGrantRequest`.

~~~java
package com.example.oauth.custom;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.endpoint
    .AbstractOAuth2AuthorizationGrantRequest;

public final class WorkloadTicketGrantRequest
        extends AbstractOAuth2AuthorizationGrantRequest {

    private final String workloadTicket;

    public WorkloadTicketGrantRequest(
        ClientRegistration registration,
        String workloadTicket
    ) {
        super(WorkloadTicketGrant.TYPE, registration);

        if (workloadTicket == null || workloadTicket.isBlank()) {
            throw new IllegalArgumentException(
                "workloadTicket must not be blank"
            );
        }

        this.workloadTicket = workloadTicket;
    }

    public String getWorkloadTicket() {
        return workloadTicket;
    }
}
~~~

**Không override `toString()` để in ticket**, không viết logger theo object grant request và không đưa ticket vào exception message.

### 8.1. Request type không phải HTTP request

`WorkloadTicketGrantRequest` là một **domain object** cho token-response client. Một lớp khác vẫn cần chuyển nó thành HTTP form-encoded POST tới token endpoint.

Không nhầm `OAuth2AuthorizeRequest` (đầu vào của manager) với `WorkloadTicketGrantRequest` (đầu vào của token-response client).

## 9. Token-response client: đổi grant request lấy OAuth2AccessTokenResponse

Contract đồng bộ:

~~~java
import org.springframework.security.oauth2.client.endpoint
    .OAuth2AccessTokenResponseClient;

OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>
~~~

Implementation cần:

1. Lấy token URI **chỉ từ ClientRegistration đáng tin**, không từ user input.
2. Dùng HTTP POST với `application/x-www-form-urlencoded`.
3. Đặt `grant_type` là URI custom.
4. Đặt bằng chứng vào tham số `workload_ticket` theo contract.
5. Xác thực client bằng method đã đăng ký, ví dụ client_secret_basic/mTLS/private_key_jwt.
6. Parse token response thành `OAuth2AccessTokenResponse`.
7. Map OAuth2 token error response thành lỗi có error code đúng.
8. Giới hạn timeout, body size, retry và không log credential.

### 9.1. HTTP request minh họa

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=urn%3Aexample%3Aparams%3Aoauth%3Agrant-type%3Aworkload-ticket&workload_ticket=<url-encoded-ticket>
~~~

Token response minh họa:

~~~json
{
  "access_token": "EXAMPLE_AT",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "reports.read"
}
~~~

Một Authorization Server cũng có thể trả `refresh_token` nếu custom grant contract cho phép. **Không tự giả định** refresh token được cấp, hoặc refresh token dùng được với registration này nếu chưa thỏa thuận.

### 9.2. Tách adapter giao thức và HTTP transport

Một mẫu dễ test là tách:

~~~java
public interface WorkloadTicketTokenEndpoint {
    OAuth2AccessTokenResponse exchange(
        WorkloadTicketGrantRequest request
    );
}
~~~

và adapter:

~~~java
public final class WorkloadTicketTokenResponseClient
        implements OAuth2AccessTokenResponseClient<
            WorkloadTicketGrantRequest> {

    private final WorkloadTicketTokenEndpoint endpoint;

    public WorkloadTicketTokenResponseClient(
        WorkloadTicketTokenEndpoint endpoint
    ) {
        this.endpoint = endpoint;
    }

    @Override
    public OAuth2AccessTokenResponse getTokenResponse(
        WorkloadTicketGrantRequest request
    ) {
        return endpoint.exchange(request);
    }
}
~~~

Đây là **adapter thực thi contract**, không phải một HTTP client hoàn chỉnh. `WorkloadTicketTokenEndpoint` sẽ có implementation dùng `RestClient` (Spring Framework 6.1+) hoặc HTTP stack được tổ chức cho phép, áp dụng OAuth2 form conversion, client authentication và error mapping đúng.

**Ưu điểm:** Provider không cần quan tâm codec/TLS/proxy; unit test có thể thay endpoint bằng fake mà không gọi mạng.

### 9.3. Không copy token client của grant khác một cách máy móc

Một token client cho `client_credentials` được thiết kế với request type `OAuth2ClientCredentialsGrantRequest`. Nếu grant cần `workload_ticket` riêng, không nên cast request sang type khác hoặc lén thay `grant_type` sau khi signing.

Nếu grant thực chất là `client_credentials` cộng thêm parameter, hãy dùng **extension hooks của token client chuẩn**. Chỉ xây request type mới khi bản chất grant khác.

## 10. Hiện thực provider custom trên Servlet — phần quan trọng nhất

Ví dụ này dùng:

- `WorkloadTicketGrant.TYPE` để match registration.
- `TrustedTicketSupplier` cấp bằng chứng mới theo policy.
- `OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>` thực hiện trao đổi token.
- `Clock` và `Duration clockSkew` kiểm soát thời điểm cấp lại.

~~~java
package com.example.oauth.custom;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.endpoint
    .OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.client.registration.ClientRegistration;

public final class WorkloadTicketAuthorizedClientProvider
        implements OAuth2AuthorizedClientProvider {

    private final TrustedTicketSupplier ticketSupplier;
    private final OAuth2AccessTokenResponseClient<
        WorkloadTicketGrantRequest> tokenClient;

    private Clock clock = Clock.systemUTC();
    private Duration clockSkew = Duration.ofSeconds(60);

    public WorkloadTicketAuthorizedClientProvider(
        TrustedTicketSupplier ticketSupplier,
        OAuth2AccessTokenResponseClient<
            WorkloadTicketGrantRequest> tokenClient
    ) {
        this.ticketSupplier =
            Objects.requireNonNull(ticketSupplier);
        this.tokenClient =
            Objects.requireNonNull(tokenClient);
    }

    public void setClock(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public void setClockSkew(Duration clockSkew) {
        if (clockSkew == null || clockSkew.isNegative()) {
            throw new IllegalArgumentException(
                "clockSkew must not be negative"
            );
        }
        this.clockSkew = clockSkew;
    }

    @Override
    public OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context
    ) {
        ClientRegistration registration =
            context.getClientRegistration();

        // 1. Grant không khớp: provider này không xử lý.
        if (!WorkloadTicketGrant.TYPE.equals(
            registration.getAuthorizationGrantType()
        )) {
            return null;
        }

        OAuth2AuthorizedClient existing =
            context.getAuthorizedClient();

        // 2. Token hiện tại còn đủ hạn: không cấp lại.
        if (existing != null &&
            !isExpiredOrNearExpiry(existing.getAccessToken())) {
            return null;
        }

        String principalName = context.getPrincipal().getName();
        if (principalName == null || principalName.isBlank()) {
            throw new IllegalArgumentException(
                "A trusted principal is required"
            );
        }

        // 3. Bằng chứng được phát bởi một nguồn server-side tin cậy.
        String ticket = ticketSupplier.issueFor(
            registration.getRegistrationId(),
            principalName
        );

        // 4. Token exchange được cách ly trong response client.
        WorkloadTicketGrantRequest grantRequest =
            new WorkloadTicketGrantRequest(registration, ticket);

        OAuth2AccessTokenResponse response =
            tokenClient.getTokenResponse(grantRequest);

        // 5. Tạo authorized client cho đúng registration/principal.
        return new OAuth2AuthorizedClient(
            registration,
            principalName,
            response.getAccessToken(),
            response.getRefreshToken()
        );
    }

    private boolean isExpiredOrNearExpiry(
        OAuth2AccessToken accessToken
    ) {
        Instant expiresAt = accessToken.getExpiresAt();

        // Không có expiry tin cậy: tránh coi token vô hạn.
        if (expiresAt == null) {
            return true;
        }

        return !clock.instant().plus(clockSkew)
            .isBefore(expiresAt);
    }
}
~~~

**Đây là provider minh họa với quy tắc cấp lại bằng ticket mới.** Thực tế cần bổ sung error handling, controls cho issuer, audience, token type, concurrency, metrics và timeout phù hợp contract.

### 10.1. Vì sao phải kiểm tra AuthorizationGrantType trước?

Một manager có thể cấu hình nhiều providers. Nếu provider tùy chỉnh bỏ qua grant type, nó có thể gọi token endpoint custom ngay cả khi registration là `authorization_code` hoặc `client_credentials`.

~~~java
if (!WorkloadTicketGrant.TYPE.equals(
    registration.getAuthorizationGrantType())) {
    return null;
}
~~~

Đây là **chốt phân nhánh đầu tiên**.

### 10.2. Vì sao existing authorized client còn hạn thì trả null?

Manager thường tải authorized client đã lưu trước khi gọi provider. Nếu token chưa tới hạn cần cấp lại:

~~~java
if (existing != null && !isExpiredOrNearExpiry(...)) {
    return null;
}
~~~

Provider không nên xin ticket/token mới trên **mọi request**. Việc cấp token liên tục gây:

- Tải token endpoint.
- Tăng chi phí cryptographic signing/verification.
- Race khi nhiều request cùng cập nhật storage.
- Rate limiting và sự cố dây chuyền nếu IdP chậm.

`null` nghĩa là **provider không thực hiện authorization mới ở lần gọi này**; manager có thể giữ authorized client hiện tại theo contract của manager.

### 10.3. Clock skew phải được kiểm soát

Với token hết hạn lúc `10:05:00Z` và clock skew 60 giây, provider có thể xin token mới từ `10:04:00Z`.

Nếu token lifetime chỉ 90 giây mà skew 80 giây, token bị coi là “sắp hết hạn” rất sớm. Cần căn cứ latency, đồng hồ hệ thống và expiry semantics thực tế.

Không sửa `expiresAt` trong authorized-client store để ép refresh; hãy điều chỉnh provider policy.

### 10.4. Ticket phải mới và có phạm vi

`ticketSupplier.issueFor(...)` phải phát ticket cho đúng workload và thời điểm, không tải một ticket vô thời hạn từ cấu hình tĩnh.

**Một ticket hợp lệ với workload A không tự chứng minh workload B được phép dùng nó.** Nếu hệ thống nhiều tenant, kiểm tra binding tới tenant và quyền của worker ở cấp Authorization Server.

### 10.5. Không swallow exception rồi trả token cũ

Sai:

~~~java
try {
    return tokenClient.getTokenResponse(grantRequest);
} catch (RuntimeException ex) {
    return oldAuthorizedClient; // Sai loại trả về và sai cả policy.
}
~~~

Đừng “fallback” thành công khi grant đã thất bại; provider cần phát lỗi thích hợp để manager/consumer xử lý. Khi token endpoint từ chối ticket, trả authorized client cũ đã hết hạn sẽ che mất sự cố và gây 401 lặp.

## 11. Nếu token endpoint không trả Bearer token?

Ví dụ ứng dụng gọi Resource Server bằng:

~~~http
Authorization: Bearer <access-token>
~~~

thì response cần tương thích với `Bearer` token và yêu cầu của Resource Server. Một token response có:

~~~json
{
  "access_token": "opaque-value",
  "token_type": "Bearer",
  "expires_in": 300
}
~~~

có thể được chuyển thành:

~~~java
OAuth2AccessTokenResponse response =
    OAuth2AccessTokenResponse.withToken("opaque-value")
        .tokenType(OAuth2AccessToken.TokenType.BEARER)
        .expiresIn(300)
        .scopes(Set.of("reports.read"))
        .build();
~~~

Đây chỉ là **cách dựng fixture response**. Với response thật, phải kiểm tra:

- `access_token` có mặt, không rỗng.
- `token_type` được hỗ trợ.
- `expires_in` hợp lệ theo contract.
- Scopes phản ánh **response thực tế**, không tự tăng scope.
- Các tham số extra được xử lý theo policy.

**Không tự nhận mọi giá trị `token_type` là Bearer** chỉ vì downstream client đang gọi `setBearerAuth()`. Nếu Authorization Server yêu cầu proof-of-possession hoặc token binding riêng, phải dùng integration tương ứng.

## 12. Token endpoint errors phải giữ nguyên ngữ nghĩa OAuth2

Ví dụ token endpoint từ chối ticket:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Workload ticket expired"
}
~~~

Một implementation tốt nên chuyển error thành `OAuth2AuthorizationException` hoặc exception OAuth2 phù hợp, bảo toàn **error code** mà không làm lộ ticket.

Các lỗi cần phân biệt:

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `unsupported_grant_type` | AS không chấp nhận custom grant URI | Kiểm tra hợp đồng grant/version |
| `invalid_grant` | Ticket không hợp lệ, hết hạn, audience sai hoặc đã dùng | Có thể cấp ticket mới theo policy; không retry mù |
| `invalid_client` | Client authentication sai/mTLS thất bại | Sửa credential/configuration |
| `unauthorized_client` | Client chưa được phép dùng custom grant | Sửa registration/policy AS |
| `invalid_scope` | Scope không được phép | Sửa cấu hình/policy, không retry cùng request |
| HTTP 429 | Token endpoint rate limiting | Backoff, không tạo request storm |
| HTTP 500/503/timeout | Transport/AS outage | Retry có giới hạn và timeout/deadline |
| Response sai JSON/schema | Protocol contract không khớp | Fail closed, theo dõi integration |

### 12.1. Không retry one-time ticket tùy tiện

Nếu ticket là **one-time proof**:

~~~text
Client gửi ticket T1 tới AS
AS đã consume T1 và cấp token
Network lỗi trước khi client nhận response
Client retry cùng T1 -> invalid_grant
~~~

Không thể khẳng định ticket chưa được dùng chỉ vì HTTP client timeout. Muốn retry, cần **sinh ticket mới khi contract cho phép**, xác định lại trạng thái, hoặc thiết kế idempotency ở token endpoint. Không tự động lặp cùng form request vô hạn.

### 12.2. HTTP error mapping của RestClient

Nếu tự viết `RestClient` token-response adapter, `retrieve()` thường ném HTTP status exception cho lỗi 4xx/5xx. Nếu chỉ để nguyên exception transport, manager failure handler có thể **không thấy `invalid_grant` như một OAuth2 error code**.

Vì vậy token client cần **parse OAuth2 error response có giới hạn**, map vào loại lỗi phù hợp và giữ error code cho policy. Không log raw body nếu nó chứa credential.

## 13. Cấu hình ClientRegistration trong Spring Boot

Trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-with-ticket:
            provider: company
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: "urn:example:params:oauth:grant-type:workload-ticket"
            scope:
              - reports.read
        provider:
          company:
            token-uri: https://login.example.test/oauth2/token
~~~

Nếu provider hỗ trợ discovery, có thể chọn `issuer-uri` theo hợp đồng. Khi cấu hình token URI thủ công, đảm bảo endpoint **HTTPS**, client authentication và scope đã được đăng ký.

**Không nhầm** YAML `authorization-grant-type` với một lệnh kích hoạt sẵn provider. YAML chỉ xây `ClientRegistration`; ta còn phải **gắn custom provider vào manager**.

### 13.1. Không hard-code secret hoặc ticket

`REPORTS_CLIENT_SECRET` là placeholder lấy từ secret manager/runtime. Ticket phải được cấp động bởi nguồn đã xác thực, không đặt trong YAML/Git:

~~~yaml
# Không làm như sau:
custom:
  workload-ticket: "a-real-long-lived-secret"
~~~

Ticket có hạn dùng và anti-replay sẽ mất ý nghĩa nếu được tái sử dụng như mật khẩu cố định.

## 14. Kết nối provider với AuthorizedClientServiceOAuth2AuthorizedClientManager

Đối với **background worker/queue job Servlet hoặc ứng dụng không có HTTP request**, manager phù hợp là:

~~~java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

Nó không cần `HttpServletRequest`.

~~~java
package com.example.oauth.custom;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;

@Configuration
public class CustomGrantManagerConfig {

    @Bean("workloadTicketManager")
    OAuth2AuthorizedClientManager workloadTicketManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients,
        TrustedTicketSupplier ticketSupplier,
        OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest> tokenClient
    ) {
        OAuth2AuthorizedClientProvider custom =
            new WorkloadTicketAuthorizedClientProvider(
                ticketSupplier, tokenClient
            );

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(custom);
        return manager;
    }
}
~~~

Trong code trên, `tokenClient` được inject theo generic type tương ứng. Nếu hệ thống có nhiều OAuth2AccessTokenResponseClient beans, dùng qualifier/bean name rõ ràng để tránh nhầm token client của grant khác.

### 14.1. Manager đảm nhận việc gì?

Về logic:

~~~text
manager.authorize()
  -> tìm registration
  -> tải authorized client theo registrationId + principalName
  -> tạo OAuth2AuthorizationContext
  -> customProvider.authorize(context)
  -> nếu có authorized client mới: lưu theo success handler
  -> trả authorized client cho caller
~~~

**Provider không cần gọi `authorizedClients.saveAuthorizedClient(...)` thủ công** trong happy path thông thường. Đó là trách nhiệm của manager/success handler. Nếu provider tự lưu ngay, có thể làm trùng ghi hoặc lưu token trước khi lifecycle policy được thực thi.

### 14.2. Khi nào dùng DefaultOAuth2AuthorizedClientManager?

Trong **Servlet web request** có Authentication và HTTP request/response, thường dùng:

~~~java
DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        oauth2AuthorizedClientRepository
    );

manager.setAuthorizedClientProvider(customProvider);
~~~

Khác biệt nằm ở **storage/context**, không phải bản chất custom provider. Manager web phối hợp `OAuth2AuthorizedClientRepository` và request context; manager service phối hợp `OAuth2AuthorizedClientService`.

Không dùng `DefaultOAuth2AuthorizedClientManager` trong scheduled job nếu không có Servlet request rồi kỳ vọng manager tự tìm `HttpServletRequest`.

## 15. Compose custom provider với provider chuẩn

Một ứng dụng có thể vừa có:

- OIDC login qua authorization code.
- Refresh token cho user.
- Client credentials cho machine clients.
- Workload Ticket Grant cho một loại registration chuyên biệt.

Ta có thể ghép providers:

~~~java
import org.springframework.security.oauth2.client
    .DelegatingOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client
    .OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider standard =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();

OAuth2AuthorizedClientProvider combined =
    new DelegatingOAuth2AuthorizedClientProvider(
        standard,
        customProvider
    );

manager.setAuthorizedClientProvider(combined);
~~~

Đây là **đoạn minh họa cấu hình một manager**; biến `manager` và `customProvider` phải được định nghĩa ở ứng dụng. Không tạo thêm managers trùng bean name không cần thiết.

### 15.1. Provider chain không đổi grant type của registration

Một registration:

~~~text
reports-with-ticket -> workload-ticket grant
reports-service     -> client_credentials
company-login       -> authorization_code
~~~

được mỗi provider xem xét theo grant/điều kiện của nó. Chỉ thêm provider custom vào chain **không biến client_credentials thành workload ticket grant**.

### 15.2. Thứ tự provider có ý nghĩa

Thứ tự ảnh hưởng khi nhiều providers cùng có khả năng xử lý existing client. Ví dụ một registration có refresh token và một provider custom có thể reissue token bằng ticket.

Nếu `refreshToken()` được xét trước, nó có thể làm mới token khi gần hết hạn; nếu custom provider được xét trước và tự cấp token mới ngay, refresh provider có thể không có cơ hội chạy.

**Không cấu hình các providers với quy tắc grant chồng lấn mà không xác định precedence.** Nếu grant custom không muốn sử dụng refresh token, hãy nói rõ trong provider policy và manager chain; đừng dựa vào thứ tự ngẫu nhiên.

## 16. Gọi manager trong background job

Service job có thể gọi:

~~~java
package com.example.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportsGateway {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient reportsApi;

    public ReportsGateway(
        @Qualifier("workloadTicketManager")
        OAuth2AuthorizedClientManager manager,
        RestClient.Builder restClientBuilder
    ) {
        this.manager = manager;
        this.reportsApi = restClientBuilder
            .baseUrl("https://reports.example.test")
            .build();
    }

    public String fetchDailySummary() {
        OAuth2AuthorizeRequest authorization =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-with-ticket")
                .principal("reports-worker")
                .build();

        OAuth2AuthorizedClient client =
            manager.authorize(authorization);

        if (client == null) {
            throw new IllegalStateException(
                "No authorized client for reports-with-ticket"
            );
        }

        return reportsApi.get()
            .uri("/api/daily-summary")
            .headers(headers -> headers.setBearerAuth(
                client.getAccessToken().getTokenValue()
            ))
            .retrieve()
            .body(String.class);
    }
}
~~~

`reports-worker` là **service principal name cho storage**, không phải tên một nhân viên đang login. `RestClient.Builder` cần timeout/TLS/proxy và quản lý URL theo môi trường; code giản lược để thể hiện cách dùng manager.

**Không nhận client registration ID hoặc principal name tùy ý từ request của browser** rồi gọi manager bằng quyền của backend. Đây có thể trở thành confused deputy và cho phép truy xuất token của account khác.

## 17. HTTP client integration có tự biết custom grant không?

`RestClient` hoặc `WebClient` không cần hiểu cách tạo `workload_ticket` nếu chúng được tích hợp với **manager có custom provider**.

~~~text
RestClient/WebClient
    -> manager.authorize(...)
    -> custom provider
    -> token response client
    -> authorized client
    -> Bearer header đến Resource Server
~~~

Nhưng nếu bạn tạo `RestClient.create(...)` hoặc `WebClient.create(...)` rồi không gắn OAuth2 integration, HTTP client **không tự gọi manager**.

### 17.1. RestClient OAuth2 interceptor (Spring Security 6.4+)

~~~java
OAuth2ClientHttpRequestInterceptor oauth2 =
    new OAuth2ClientHttpRequestInterceptor(
        workloadTicketManager
    );

RestClient reportsApi = RestClient.builder()
    .baseUrl("https://reports.example.test")
    .requestInterceptor(oauth2)
    .build();
~~~

Đoạn này giả sử `workloadTicketManager` đã được cấu hình và request attributes/principal context cung cấp đủ thông tin. Trong background job, cách **explicit authorize** ở mục 16 có thể dễ kiểm soát hơn, vì interceptor mặc định thường có cách resolve principal từ HTTP request/security context nếu không được chỉ định.

### 17.2. Chọn registration rõ ràng

Trong Servlet RestClient integration, có thể dùng request attribute resolver:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

String result = reportsApi.get()
    .uri("/api/daily-summary")
    .attributes(clientRegistrationId("reports-with-ticket"))
    .retrieve()
    .body(String.class);
~~~

Với background job không có Authentication của user, phải cung cấp **principal context** phù hợp hoặc gọi manager trực tiếp; chỉ đặt registration attribute chưa chắc đủ cho mọi interceptor cấu hình.

**Không dùng default authorized client cho tất cả outgoing HTTP requests** trong hệ thống gọi nhiều API/tenants. Token không được gửi sang host không thuộc audience/trust boundary.

## 18. Lưu trữ authorized client và không làm lộ ticket

Manager sử dụng:

~~~java
OAuth2AuthorizedClientService
~~~

hoặc:

~~~java
OAuth2AuthorizedClientRepository
~~~

tùy context. Một authorized client thường keyed theo:

~~~text
(clientRegistrationId, principalName)
("reports-with-ticket", "reports-worker")
~~~

**Không cần lưu workload ticket trong OAuth2AuthorizedClient**. Ticket là bằng chứng ngắn hạn được sử dụng để xin access token; nếu cần trace, chỉ lưu **ticket ID đã được xử lý an toàn** chứ không lưu raw ticket.

### 18.1. Token at rest

Token và refresh token (nếu được cấp) là credential. Với persistent store, cần:

- Hạn chế quyền đọc/ghi.
- Encryption-at-rest và key management nếu policy yêu cầu.
- Xóa/retention phù hợp.
- Không log raw token hoặc ticket.
- Không trả credential qua API debug cho frontend.
- Bảo vệ backup và access logs.

### 18.2. Principal name ổn định

Không nên dùng:

~~~java
.principal(UUID.randomUUID().toString())
~~~

trên mỗi request nếu đây là cùng một service job và bạn muốn cache/reuse authorized client. Mỗi principalName mới có thể tạo một storage key mới.

Ngược lại, **không dùng một principalName chung** cho các tenants hoặc quyền khác nhau nếu điều đó phá vỡ isolation. Chọn key theo security boundary đã thiết kế.

## 19. Success/failure handlers của manager

Provider trả authorized client nhưng **manager** mới điều phối storage và lifecycle.

Ví dụ logic:

~~~text
Provider authorize:
  -> token exchange success
  -> return new OAuth2AuthorizedClient

Manager:
  -> success handler lưu authorized client
  -> return token cho consumer
~~~

Nếu custom manager thay success handler mặc định, đảm bảo **token mới được lưu**. Nếu không, mỗi lần gọi có thể xin token lại dù AT hiện tại còn hạn.

### 19.1. Failure handler phải hiểu error code

Nếu token endpoint trả `invalid_grant`, manager có thể loại authorized client cũ theo chính sách nhất định. Nhưng không nên xóa token của mọi user/registration vì một lỗi riêng.

Với custom grant:

1. Xác định error code nào chứng minh **existing authorized client không còn dùng được**.
2. Xác định lỗi nào do **ticket mới** bị từ chối nhưng access token cũ có thể vẫn hợp lệ.
3. Chọn policy cleanup cho đúng registration/principal.
4. Tránh xóa token mới hơn sau race giữa refresh/reissue và error handler.
5. Phân biệt lỗi token endpoint với lỗi Resource Server.

**Không tự nghĩ “invalid_grant luôn có nghĩa access token cũ đã bị revoke”.** Nó có thể chỉ nói **ticket hiện tại không hợp lệ**. Muốn xóa existing authorized client hay giữ lại phải căn cứ extension grant contract và trạng thái token.

## 20. Token còn hạn không bảo đảm Resource Server chấp nhận

Một access token có `expiresAt` trong tương lai nhưng Reports API vẫn có thể từ chối:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Vì:

- Token bị revoked.
- Audience không phù hợp.
- Issuer hoặc signature không đúng.
- Token binding/confirmation thiếu.
- Resource Server áp dụng policy khác.

Provider chỉ biết token metadata phía OAuth2 Client. Resource Server tự quyết định token có chấp nhận được cho request đó hay không.

Nếu có bằng chứng `invalid_token`, ứng dụng có thể loại authorized client cũ theo policy rồi gọi manager để xin token mới, nhưng **không retry vô hạn** với cùng grant/configuration.

### 20.1. HTTP 403 insufficient_scope

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

thường nghĩa token có thể hợp lệ nhưng không đủ quyền. Xin token mới theo grant và scope cũ **không tự tăng quyền**. Cần sửa client registration, consent/AS policy hoặc business authorization đúng thẩm quyền.

## 21. Đặc biệt: custom grant là một phần của hệ thống bảo mật

Một grant tùy chỉnh làm tăng bề mặt tấn công. Threat model cần xem:

| Rủi ro | Biện pháp |
|---|---|
| Ticket bị copy rồi replay | TTL ngắn, nonce/jti, one-time semantics, replay cache tại AS |
| Ticket có audience sai | AS kiểm tra audience exact; client không tự đổi token URI |
| Workload tự khai subject của user khác | Issuer xác thực workload, AS kiểm tra mapping và delegation |
| Client secret bị lộ | Secret store, mTLS/private_key_jwt khi phù hợp, rotation |
| Ticket bị log | Không log payload/header/body token request |
| Lỗi proxy/TLS | HTTPS, truststore/CA hợp lệ, không disable validation |
| Cấp scope quá rộng | Least privilege, allowlist scopes, tenant/resource authorization |
| Nhầm token giữa tenants | Tách registration/principal/storage/security policies |
| Retry one-time ticket | Retry có điều kiện; không replay credential đã consume |
| Token response injection | Chỉ tin TLS endpoint; parse token_type/expiry/response strict |
| SSRF từ dynamic token URI | URI cấu hình server-side, không lấy từ request không tin cậy |
| Rate-limit bypass | Backoff, quotas, concurrency limits |

**Security của custom grant nằm chủ yếu ở Authorization Server**: xác minh ticket, issuer, audience, expiry, replay và policy trước khi cấp token. Provider ở client chỉ là một phần của thiết kế.

## 22. Trường hợp user-delegated: custom grant không được vượt quyền OIDC

Nếu mục tiêu là **gọi API thay mặt người dùng đã đăng nhập OIDC**, khác hoàn toàn một workload ticket cho machine identity.

Ví dụ không an toàn:

~~~text
Browser nhập ?sub=admin
   -> Portal tạo ticket cho admin
   -> AS cấp access token với quyền admin
~~~

Nếu custom grant hỗ trợ delegation, cần:

- Trusted principal từ Authentication đã xác thực.
- Consent hoặc chính sách ủy quyền rõ ràng.
- Binding giữa subject token/ticket và OAuth client.
- Kiểm tra tenant, audience, scope.
- Logging/audit phù hợp.
- Không dùng `email` làm khóa identity bất biến khi OIDC có `(iss, sub)`.

Một service principal trong `OAuth2AuthorizeRequest` **chỉ là input để tìm authorized client**, không phải bằng chứng AS sẽ coi token là của người đó. Không cấp quyền theo một chuỗi principal do caller tự đặt.

## 23. Khi nào nên dùng RFC 8693 Token Exchange thay vì grant riêng?

Nếu bài toán là **đổi một security token đã có lấy token khác** để gọi API khác, hãy xem **RFC 8693 Token Exchange**:

~~~text
grant_type = urn:ietf:params:oauth:grant-type:token-exchange
subject_token = ...
subject_token_type = ...
requested_token_type = ...
audience/resource = ...
~~~

Đừng tự biến các tham số đó thành một grant “gần giống” mà không phân tích rõ:

- Subject token có thể được ủy quyền cho ai?
- Actor token có phải đang đại diện dịch vụ trung gian không?
- Có impersonation/delegation không?
- Token output cần audience/scope nào?
- Authorization Server có hỗ trợ token exchange không?

**Tùy phiên bản Spring Security**, có thể đã có provider/token client cho token exchange hoặc extension hooks phù hợp. Nên kiểm tra thư viện hiện có trước khi viết code custom. Mục tiêu của bài là hiểu provider SPI, không khuyên tự viết lại chuẩn khi không cần.

## 24. Reactive: cùng ý tưởng, khác interface và execution model

Trong **Spring WebFlux**, provider tương ứng:

~~~java
org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientProvider
~~~

với contract:

~~~java
Mono<OAuth2AuthorizedClient> authorize(
    OAuth2AuthorizationContext context
);
~~~

So sánh:

| Tiêu chí | Servlet / đồng bộ | Reactive / WebFlux |
|---|---|---|
| Provider interface | `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| Kết quả không áp dụng | `null` | `Mono.empty()` |
| Token response client | `OAuth2AccessTokenResponseClient<T>` | `ReactiveOAuth2AccessTokenResponseClient<T>` |
| Manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| User web request manager | `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| Background service manager | `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Token I/O | Có thể blocking với RestClient | Nên non-blocking với WebClient |

**Không truyền provider đồng bộ vào Reactive manager** bằng cách cast type hoặc gọi `.block()` trên event-loop. Với WebFlux hãy thiết kế implementation reactive riêng.

## 25. Thiết kế Reactive WorkloadTicket provider

Giả sử có nguồn ticket bất đồng bộ:

~~~java
public interface ReactiveTrustedTicketSupplier {
    Mono<String> issueFor(
        String clientRegistrationId,
        String trustedPrincipalName
    );
}
~~~

Và token response client reactive:

~~~java
ReactiveOAuth2AccessTokenResponseClient<
    WorkloadTicketGrantRequest>
~~~

Provider có thể viết:

~~~java
package com.example.oauth.custom;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint
    .ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import reactor.core.publisher.Mono;

public final class ReactiveWorkloadTicketProvider
        implements ReactiveOAuth2AuthorizedClientProvider {

    private final ReactiveTrustedTicketSupplier ticketSupplier;
    private final ReactiveOAuth2AccessTokenResponseClient<
        WorkloadTicketGrantRequest> tokenClient;
    private final Clock clock;
    private final Duration clockSkew;

    public ReactiveWorkloadTicketProvider(
        ReactiveTrustedTicketSupplier ticketSupplier,
        ReactiveOAuth2AccessTokenResponseClient<
            WorkloadTicketGrantRequest> tokenClient,
        Clock clock,
        Duration clockSkew
    ) {
        this.ticketSupplier = ticketSupplier;
        this.tokenClient = tokenClient;
        this.clock = clock;
        this.clockSkew = clockSkew;
    }

    @Override
    public Mono<OAuth2AuthorizedClient> authorize(
        OAuth2AuthorizationContext context
    ) {
        return Mono.defer(() -> {
            ClientRegistration registration =
                context.getClientRegistration();

            if (!WorkloadTicketGrant.TYPE.equals(
                registration.getAuthorizationGrantType())) {
                return Mono.empty();
            }

            OAuth2AuthorizedClient existing =
                context.getAuthorizedClient();

            if (existing != null &&
                !isNearExpiry(existing.getAccessToken())) {
                return Mono.empty();
            }

            String principalName = context.getPrincipal().getName();

            return ticketSupplier.issueFor(
                    registration.getRegistrationId(),
                    principalName
                )
                .flatMap(ticket -> tokenClient.getTokenResponse(
                    new WorkloadTicketGrantRequest(
                        registration, ticket
                    )
                ))
                .map(response -> new OAuth2AuthorizedClient(
                    registration,
                    principalName,
                    response.getAccessToken(),
                    response.getRefreshToken()
                ));
        });
    }

    private boolean isNearExpiry(OAuth2AccessToken token) {
        Instant expiresAt = token.getExpiresAt();
        return expiresAt == null ||
            !clock.instant().plus(clockSkew).isBefore(expiresAt);
    }
}
~~~

Đây là code minh họa cho **Reactive SPI**, cần validate input, exception mapping, metrics và token response strict theo production policy. Nó cho thấy:

- `Mono.defer` không tạo ticket trước khi có subscription.
- Grant không khớp hoặc token chưa cần cấp lại → `Mono.empty()`.
- `ticketSupplier.issueFor(...)` trả Mono, không block event-loop.
- `flatMap` gọi token endpoint khi có ticket.
- `map` tạo authorized client mới.

### 25.1. Nếu nguồn ticket là blocking

Nếu thư viện ticket issuer thực tế có I/O **blocking**, không gọi trực tiếp trên Reactor event-loop. Có thể bọc bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` khi đã đánh giá tài nguyên và tải, hoặc tốt hơn dùng HTTP client reactive đúng nghĩa.

Không gọi `.block()` trong `ReactiveOAuth2AuthorizedClientProvider.authorize(...)`.

### 25.2. Subscription và cancellation

Publisher thường lazy:

~~~java
Mono<OAuth2AuthorizedClient> result =
    reactiveProvider.authorize(context);
~~~

Chỉ tạo `Mono` không có nghĩa token endpoint đã được gọi. Manager/WebClient/scheduler sẽ subscribe. Nếu request bị hủy, upstream có thể bị cancel; **cancellation không bảo đảm ticket chưa được consume** tại Authorization Server.

## 26. Gắn custom provider vào Reactive manager

Đối với background worker WebFlux/Reactive:

~~~java
package com.example.oauth.custom;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;

@Configuration
public class ReactiveCustomGrantConfig {

    @Bean("reactiveWorkloadTicketManager")
    ReactiveOAuth2AuthorizedClientManager manager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClients,
        ReactiveWorkloadTicketProvider customProvider
    ) {
        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(customProvider);
        return manager;
    }
}
~~~

Đây là **manager service-based reactive**, không cần `ServerWebExchange`, phù hợp với scheduled job.

Nếu custom grant được dùng trong **WebFlux HTTP user request**, manager tương ứng có thể là `DefaultReactiveOAuth2AuthorizedClientManager` với `ServerOAuth2AuthorizedClientRepository`; cách gắn provider vẫn tương tự nhưng storage/context khác.

### 26.1. Một bước WebClient reactive

~~~java
Mono<String> data = manager.authorize(
        OAuth2AuthorizeRequest
            .withClientRegistrationId("reports-with-ticket")
            .principal("reports-worker")
            .build()
    )
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No authorized client")
    ))
    .flatMap(client -> reportsWebClient.get()
        .uri("/api/daily-summary")
        .headers(headers -> headers.setBearerAuth(
            client.getAccessToken().getTokenValue()
        ))
        .retrieve()
        .bodyToMono(String.class)
    );
~~~

Không gọi `.subscribe()` rồi bỏ qua kết quả nếu application cần quản lý job status/error. Trả Mono cho framework hoặc scheduler có quản lý subscription.

## 27. Concurrency: nhiều request cùng muốn cấp token

Giả sử hai threads/jobs cùng lấy authorized client `reports-with-ticket / reports-worker`:

~~~mermaid
sequenceDiagram
    participant A as Job A
    participant B as Job B
    participant Store as Authorized Client Store
    participant Ticket as Ticket Issuer
    participant AS as Authorization Server

    A->>Store: load client (AT-1 near expiry)
    B->>Store: load client (AT-1 near expiry)
    A->>Ticket: issue T2
    B->>Ticket: issue T3
    Ticket-->>A: T2
    Ticket-->>B: T3
    A->>AS: custom grant T2
    B->>AS: custom grant T3
    AS-->>A: AT-2
    AS-->>B: AT-3
    A->>Store: save AT-2
    B->>Store: save AT-3
~~~

Hai token mới có thể đều hợp lệ, nhưng gây:

- Nhiều ticket được phát không cần thiết.
- Nhiều token requests.
- Race ghi cache.
- Tăng tải Authorization Server.
- Khó phân tích vì token bị thay liên tục.

### 27.1. Cần single-flight hoặc lock không?

Tùy throughput và policy:

- Một worker đơn giản có thể không cần lock phức tạp.
- Nhiều pods có thể cần **distributed single-flight**, optimistic concurrency hoặc lock theo `(registrationId, principalName)`.
- Lock chỉ giải quyết phần cấp token, không bảo đảm job **exactly-once**.
- Không khóa toàn bộ mọi users/tenants chỉ vì một registration cần token.

### 27.2. Một lần refresh/reissue thất bại có thể xóa token mới hơn

Nếu Job A được AT-2 trước, Job B thất bại và failure handler xóa authorized client theo registration/principal **sau khi** AT-2 được lưu, B có thể xóa token mới.

Với tải cao hoặc token binding nghiêm ngặt, cân nhắc **version/generation-aware cleanup** và test race condition. Các repository/service tiêu chuẩn không nhất thiết cung cấp compare-and-delete tự động.

## 28. Token cache, expiresAt và policy cấp lại

Một provider cần chính sách rõ cho existing token:

| Trạng thái | Chính sách khuyến nghị |
|---|---|
| Không có authorized client | Cấp token mới nếu grant và evidence hợp lệ |
| Existing access token còn hạn đủ xa | Trả `null` / `Mono.empty()` để giữ token |
| Token sắp hết hạn | Cấp token mới theo clock skew |
| Token hết hạn | Cấp token mới nếu ticket service/AS sẵn sàng |
| Token bị Resource Server tuyên bố invalid | Cleanup có kiểm soát rồi reauthorize |
| Token response không có expiresAt tin cậy | Fail closed hoặc chính sách cấp lại bảo thủ; không coi vô hạn |
| Token thiếu scope/audience | Kiểm tra ClientRegistration/AS policy, không tự tăng quyền |

**Expiry metadata không bảo đảm token chưa revoked.** Resource Server còn quyền từ chối token khi issuer/audience/signature/policy không phù hợp.

### 28.1. Không tạo ticket trước khi chắc chắn cần token mới

Đặt `ticketSupplier.issueFor(...)` **sau** kiểm tra existing authorized client để tránh phát một ticket không cần dùng. Với one-time ticket, tạo sớm rồi không sử dụng còn gây khó khăn cho audit/capacity.

## 29. Timeout, retry và circuit breaker

Token endpoint là phụ thuộc nhạy cảm. Khi IdP chậm, hàng trăm requests cùng chờ có thể kéo sập Portal.

Nên áp dụng:

- **TCP connect timeout**.
- **Response/read timeout**.
- **Overall deadline** cho authorization attempt.
- **Rate limit/bulkhead** cho token requests.
- **Backoff và jitter** với lỗi transient phù hợp.
- **Circuit breaker** nếu kiến trúc cần và policy cho phép.
- Giới hạn số lần retry, không vượt SLO caller.

### 29.1. Không retry mọi lỗi

| Lỗi | Retry? |
|---|---|
| HTTP 503, 429 từ AS | Có thể, theo backoff/Retry-After và budget |
| `invalid_client` | Không; sửa client auth |
| `unauthorized_client` | Không; sửa AS policy |
| `invalid_scope` | Không; sửa scopes |
| `invalid_grant` với ticket one-time | Không retry cùng ticket mù quáng |
| TLS certificate invalid | Không; sửa trust/mTLS |
| Network timeout sau khi gửi ticket | Kết quả không xác định; cần policy/idempotency |

**Retry ở token-response client và retry ở job/WebClient không được chồng vô hạn.** Một job có thể nhân nhiều lần token request nếu cả hai tầng đều retry.

## 30. Observability và logging an toàn

Một custom grant mới cần metrics để biết nó đang hoạt động:

| Event/metric | Ý nghĩa |
|---|---|
| Grant selected | Provider quyết định xử lý đúng grant |
| Grant skipped | Không áp dụng vì registration khác hoặc token còn hạn |
| Ticket issuance attempted | Có yêu cầu Trusted Ticket Supplier |
| Ticket issuance failure | Nguồn ticket lỗi hoặc từ chối |
| Token exchange attempted | Có HTTP POST đến token endpoint |
| Token exchange success/failure | Grant được cấp hay bị từ chối |
| Authorized client saved/loaded | Manager/storage hoạt động |
| Token reissue count | Có cấp token quá nhiều lần không |
| Client credentials/AS error code | Phân biệt lỗi cấu hình và lỗi transient |
| Resource Server 401/403 | Phân biệt token invalid và thiếu quyền |
| Principal/registration mismatch | Dấu hiệu cấu hình hoặc bảo mật |

**Không log**:

~~~text
workload_ticket=<real-ticket>
access_token=<real-token>
refresh_token=<real-refresh-token>
client_secret=<real-client-secret>
Authorization: Bearer <real-token>
Authorization: Basic <real-secret>
~~~

Không đưa token hoặc ticket vào OpenTelemetry span attributes, metric labels hoặc exception messages. Chỉ ghi metadata đã che, route template, registration ID được allowlist, error code và correlation ID.

## 31. Testing provider: tách logic khỏi HTTP token endpoint

Để test một custom provider, không cần gọi Authorization Server thật. Các test quan trọng:

1. Registration có grant type khác → `authorize()` trả `null`.
2. Registration đúng, chưa có token → supplier được gọi và token response client trả AT.
3. Token còn hạn đủ xa → không xin ticket và không gọi token endpoint.
4. Token nằm trong clock skew → token được cấp lại.
5. Context principalName đúng → authorized client trả về giữ đúng principal.
6. Token client trả OAuth2 error → provider phát lỗi, không giả thành công.
7. Ticket supplier lỗi → không gọi token endpoint.
8. Response không hợp lệ → fail closed, không lưu credential sai.
9. Hai registrations/tenants → không dùng nhầm ticket hoặc token.
10. Đồng thời nhiều requests → quan sát race/reissue/store theo policy.

### 31.1. Unit test với fake token client

Đoạn Java/JUnit 5:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.endpoint
    .OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

import static org.junit.jupiter.api.Assertions.*;

class WorkloadTicketProviderTest {

    @Test
    void customGrantCreatesAuthorizedClientForTrustedPrincipal() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-with-ticket")
                .clientId("test-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(WorkloadTicketGrant.TYPE)
                .tokenUri("https://login.example.test/token")
                .scope("reports.read")
                .build();

        OAuth2AuthorizationContext context =
            OAuth2AuthorizationContext
                .withClientRegistration(registration)
                .principal(new TestingAuthenticationToken(
                    "reports-worker", "ignored", "ROLE_SERVICE"))
                .build();

        AtomicInteger tickets = new AtomicInteger();
        TrustedTicketSupplier supplier = (id, principal) -> {
            tickets.incrementAndGet();
            assertEquals("reports-with-ticket", id);
            assertEquals("reports-worker", principal);
            return "FAKE_SIGNED_TICKET";
        };

        OAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest> fake =
            request -> {
                assertEquals("FAKE_SIGNED_TICKET",
                    request.getWorkloadTicket());
                return OAuth2AccessTokenResponse
                    .withToken("FAKE_ACCESS_TOKEN")
                    .tokenType(OAuth2AccessToken.TokenType.BEARER)
                    .expiresIn(300)
                    .scopes(Set.of("reports.read"))
                    .build();
            };

        WorkloadTicketAuthorizedClientProvider provider =
            new WorkloadTicketAuthorizedClientProvider(supplier, fake);
        provider.setClock(Clock.fixed(
            Instant.parse("2026-11-16T00:00:00Z"),
            ZoneOffset.UTC
        ));
        provider.setClockSkew(Duration.ofSeconds(30));

        OAuth2AuthorizedClient result =
            provider.authorize(context);

        assertNotNull(result);
        assertEquals("reports-worker", result.getPrincipalName());
        assertEquals("reports-with-ticket",
            result.getClientRegistration().getRegistrationId());
        assertEquals("FAKE_ACCESS_TOKEN",
            result.getAccessToken().getTokenValue());
        assertEquals(1, tickets.get());
    }
}
~~~

Đây là unit test **provider logic**, không kiểm tra HTTP token request, OAuth2 client authentication, ticket signature hay Resource Server. Test tích hợp cần xác nhận token client gửi đúng `grant_type`, parameter encoding và xử lý OAuth2 errors với mock server.

### 31.2. Test token còn hạn không gọi supplier

Với context chứa existing client có access token còn hạn nhiều phút, spy/fake supplier nên ghi nhận:

~~~text
provider.authorize(contextWithFreshToken) -> null
ticketSupplier calls = 0
tokenResponseClient calls = 0
~~~

Với token sắp hết hạn trong clock skew:

~~~text
provider.authorize(contextNearExpiry) -> OAuth2AuthorizedClient mới
ticketSupplier calls = 1
tokenResponseClient calls = 1
~~~

`contextWithFreshToken` và `contextNearExpiry` ở đây là các fixture do test tự tạo; không phải class/variable có sẵn của Spring Security.

### 31.3. Test failure không làm manager lưu sai token

Giả lập `OAuth2AuthorizationException` từ token client. Xác nhận:

- Provider không trả authorized client giả.
- Manager failure handler được gọi theo contract.
- Storage cleanup chỉ áp dụng với lỗi được chính sách cho phép.
- Không log raw ticket.
- Không retry vô hạn lỗi `invalid_client` hoặc ticket đã consume.

## 32. Testing Reactive provider với StepVerifier

Ở Reactive, cần kiểm tra ba tín hiệu:

~~~text
Mono.empty()       -> provider không áp dụng
Mono.just(client)  -> token exchange thành công
Mono.error(error)  -> grant thất bại
~~~

Ví dụ test với fake supplier/client:

~~~java
ReactiveTrustedTicketSupplier ticketSupplier =
    (registrationId, principalName) ->
        Mono.just("FAKE_SIGNED_TICKET");

ReactiveOAuth2AccessTokenResponseClient<WorkloadTicketGrantRequest>
    tokenClient = request -> Mono.just(
        OAuth2AccessTokenResponse
            .withToken("FAKE_ACCESS_TOKEN")
            .tokenType(OAuth2AccessToken.TokenType.BEARER)
            .expiresIn(300)
            .build()
    );

ReactiveWorkloadTicketProvider provider =
    new ReactiveWorkloadTicketProvider(
        ticketSupplier,
        tokenClient,
        Clock.systemUTC(),
        Duration.ofSeconds(60)
    );

StepVerifier.create(provider.authorize(context))
    .assertNext(client -> {
        assertEquals("FAKE_ACCESS_TOKEN",
            client.getAccessToken().getTokenValue());
    })
    .verifyComplete();
~~~

`context` là fixture tạo từ `OAuth2AuthorizationContext` với registration custom grant và principal hợp lệ. Đối với grant không khớp:

~~~java
StepVerifier.create(provider.authorize(otherGrantContext))
    .verifyComplete();
~~~

Để kiểm tra **non-blocking behavior**, fake token client có thể trả Mono trì hoãn; đảm bảo không có `.block()` trong provider. Đối với sự cố concurrent requests, test cần xem storage/manager chứ không chỉ StepVerifier của một request.

## 33. Integration test: manager thực sự sử dụng custom provider

Một test đơn lẻ gọi provider trực tiếp không chứng minh service đã wire đúng manager. Cần test:

~~~text
Given:
  ClientRegistrationRepository có reports-with-ticket
  OAuth2AuthorizedClientService trống
  manager có WorkloadTicketAuthorizedClientProvider
  fake ticket supplier và fake token endpoint

When:
  manager.authorize(
    registrationId=reports-with-ticket,
    principal=reports-worker
  )

Then:
  provider được chọn
  token endpoint nhận custom grant theo contract
  manager trả authorized client đúng principal
  authorized-client service lưu token
  gọi authorize lần sau với token còn hạn không xin ticket mới
~~~

Test khác:

~~~text
Given:
  manager vừa có standard client_credentials provider
  vừa có custom workload-ticket provider

When:
  authorize(reports-service, reports-worker)

Then:
  dùng client_credentials provider
  custom ticket supplier không được gọi
~~~

**Đây là kiểm thử wiring**, thường phát hiện lỗi mà unit test riêng provider không thấy: quên `setAuthorizedClientProvider()`, injector chọn manager sai, registration grant type không khớp, hoặc token client bean không được sử dụng.

## 34. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Manager trả null dù registration tồn tại | Chưa gắn custom provider hoặc grant URI không khớp | So sánh `authorization-grant-type` và `WorkloadTicketGrant.TYPE` |
| Provider không bao giờ được gọi | Service dùng manager khác | Kiểm tra `@Qualifier` và HTTP integration |
| Ticket supplier không được gọi | Existing token còn hạn, grant không khớp hoặc provider chain khác đã xử lý | Kiểm tra context/clockSkew/chain order |
| Custom grant bị AS từ chối | AS không hỗ trợ URI, client không được phép | Kiểm tra `unsupported_grant_type`, `unauthorized_client` |
| Invalid grant liên tục | Ticket sai audience/TTL/replay/binding | Kiểm tra issuer policy, không log ticket |
| Invalid client | Client secret/mTLS/private_key_jwt sai | Kiểm tra client auth method và secret rotation |
| Token endpoint timeout | Proxy/TLS/connect/response timeout | Kiểm tra token response client riêng |
| Có token nhưng API 401 | Token sai issuer/audience/revoked/expired | Kiểm tra Resource Server Bearer error |
| API 403 | Thiếu scope/resource permission | Không retry như token expired |
| Cấp token mới trên mọi request | Provider luôn reissue hoặc storage key không ổn định | Kiểm tra existing client/expiry/principalName |
| Token mới được cấp nhưng lần sau không tìm thấy | Manager success handler không lưu hoặc dùng sai service | Kiểm tra repository/service |
| Node A lưu token, Node B không thấy | Store in-memory per-node | Shared storage nếu kiến trúc yêu cầu |
| Lỗi chỉ khi nhiều requests | Race cấp ticket/token/save | Cân nhắc single-flight/versioning |
| Reactive thread bị block | Dùng sync supplier/RestClient hoặc `.block()` | Chọn reactive transport, điều phối blocking hợp lý |
| OAuth2 login không đổi behavior | Chỉ thay manager gọi API, không thay login token client | Phân biệt `oauth2Login().tokenEndpoint()` |
| WebClient không đính Bearer | Chưa gắn OAuth2 filter hoặc chưa gọi manager | Kiểm tra consumer HTTP client |
| Ticket lộ trong logs | Wire logging/raw exception | Tắt logging sensitive và rotate credential |

## 35. Các anti-pattern cần tránh

**1. Tạo grant mới chỉ để thêm một tham số vào client_credentials.** Xem extension hooks của token response client trước.

**2. Dùng URI grant tự chế nhưng giả định mọi IdP hiểu nó.** Extension grant yêu cầu contract và cấu hình Authorization Server.

**3. Lấy ticket trực tiếp từ browser mà không kiểm tra trust binding.** Có thể bị impersonation hoặc replay.

**4. Provider tự lưu token trong database rồi manager lại lưu lần nữa.** Dễ tạo state không nhất quán.

**5. Không kiểm tra authorization grant type của ClientRegistration.** Provider có thể xử lý nhầm registration.

**6. Luôn xin token mới dù existing token còn hạn.** Làm tăng tải, race và rate limiting.

**7. Trả token cũ đã hết hạn khi token endpoint lỗi.** Che mất failure và gây 401 lặp.

**8. Tự coi refresh token là luôn có.** Custom grant có thể không cấp refresh token.

**9. Gắn client secret hoặc raw ticket vào log.** Credential có thể bị đánh cắp.

**10. Dùng `.block()` trong Reactive provider.** Làm nghẽn event loop.

**11. Dùng `principalName` do client nhập để lấy token của account khác.** Có nguy cơ confused deputy.

**12. Retry one-time ticket sau timeout một cách mù quáng.** AS có thể đã consume.

**13. Xóa mọi authorized clients khi một registration gặp invalid_grant.** Hậu quả vượt phạm vi.

**14. Dùng custom grant để cấp token thay mặt user mà bỏ qua consent và authorization policy.** Đây là lỗi bảo mật thiết kế.

**15. Coi local token cleanup là remote token revocation.** Hai cơ chế khác nhau.

## 36. Bài tập thực hành

### Bài 1 — Grant URI sai

YAML:

~~~yaml
authorization-grant-type: "urn:example:params:oauth:grant-type:workload-ticket"
~~~

Provider:

~~~java
new AuthorizationGrantType("workload_ticket")
~~~

**Câu hỏi:** Vì sao provider không được chọn?

**Hướng giải:** Grant type phải match **chính xác giá trị URI** theo `AuthorizationGrantType.equals(...)`. Tên rút gọn không giống URI.

### Bài 2 — Provider trả null

Existing authorized client có AT còn hạn 10 phút, skew 60 giây; provider trả null.

**Câu hỏi:** Có nghĩa token manager không thể gọi API không?

**Hướng giải:** Không. Provider báo không cần cấp lại; manager có thể tiếp tục dùng existing authorized client đã lưu. Null không đồng nghĩa login failure.

### Bài 3 — Ticket do người dùng tự gửi

Controller nhận:

~~~http
GET /bff/reports?ticket=USER_SUPPLIED_TICKET
~~~

và truyền ticket đó thẳng tới AS bằng custom grant.

**Câu hỏi:** Rủi ro là gì?

**Hướng giải:** Ticket có thể bị giả mạo/replay hoặc cấp cho subject khác. Phải có nguồn tin cậy, kiểm tra issuer/audience/TTL/anti-replay và binding tới principal/tenant theo contract.

### Bài 4 — Không có refresh token

AS cấp access token 5 phút, không có refresh token.

**Câu hỏi:** Provider tùy chỉnh có thể xin token mới bằng cách nào?

**Hướng giải:** Nếu contract cho phép, phát **ticket mới** rồi gọi custom grant một lần nữa. Không tạo refresh token bằng cách sao chép ID Token hoặc session cookie.

### Bài 5 — Hai worker cùng xin token

Job A và B cùng thấy AT gần hết hạn, phát T2 và T3, xin AT-2 và AT-3.

**Câu hỏi:** Điều này có làm cả hai token vô hiệu ngay không?

**Hướng giải:** Không thể kết luận; tùy AS policy. Nhưng có thể gây tải và race storage. Thiết kế single-flight/locking/versioning theo yêu cầu, không giả định mỗi registration chỉ có một request.

### Bài 6 — Servlet vs Reactive

Ứng dụng WebFlux muốn dùng class `WorkloadTicketAuthorizedClientProvider` đồng bộ trong `ReactiveOAuth2AuthorizedClientManager`.

**Câu hỏi:** Có nên bọc `.block()` để dùng chung?

**Hướng giải:** Không. Thiết kế `ReactiveOAuth2AuthorizedClientProvider` và `ReactiveOAuth2AccessTokenResponseClient` riêng; nếu thư viện ticket blocking, tách nó khỏi event-loop bằng cơ chế điều phối thích hợp.

### Bài 7 — 403 sau token exchange thành công

Token được cấp nhưng Reports API yêu cầu `reports.admin`, registration chỉ có `reports.read`.

**Câu hỏi:** Retry grant 10 lần có giúp nâng quyền không?

**Hướng giải:** Không. Cần sửa scope/policy và quyền Resource Server, không dùng retry để tăng quyền.

### Bài 8 — Token response client không map lỗi OAuth2

AS trả:

~~~json
{"error":"invalid_grant"}
~~~

nhưng RestClient adapter chỉ ném một HTTP 400 exception chung.

**Câu hỏi:** Hệ quả?

**Hướng giải:** Manager/failure handler có thể mất error code OAuth2 và cleanup sai hoặc không hoạt động. Token client cần parse OAuth2 error response an toàn và chuyển thành exception phù hợp.

## 37. Checklist trước khi triển khai custom grant

| Câu hỏi | Điều phải xác định |
|---|---|
| Có thật sự cần grant mới? | Đã xem chuẩn/hook/provider sẵn có |
| AS có hỗ trợ custom grant URI? | Có hợp đồng giao thức và cấu hình client |
| Grant type là gì? | URI nhất quán giữa registration/provider/token request |
| Ticket/assertion từ đâu? | Trusted issuer, audience, TTL, anti-replay |
| Principal có đáng tin? | Từ server/authentication, không từ input tùy ý |
| Request type có riêng? | `AbstractOAuth2AuthorizationGrantRequest` nếu cần |
| Token client có đúng contract? | `OAuth2AccessTokenResponseClient<T>` hoặc reactive variant |
| Client auth có đúng? | Basic/mTLS/private_key_jwt theo registration |
| Token response có validate? | token_type, expires_in, scopes, error mapping |
| Provider match grant? | Dùng `AuthorizationGrantType.equals` |
| Existing token còn hạn xử lý ra sao? | Không xin token lại không cần thiết |
| Clock skew có phù hợp? | Theo token lifetime/latency |
| Manager nào sử dụng? | Servlet web/service hoặc Reactive web/service |
| Provider đã gắn vào chain chưa? | Có `setAuthorizedClientProvider(...)` |
| Storage nào được dùng? | Repository/service và principalName nhất quán |
| Cleanup và failure policy? | Phân loại invalid_grant, invalid_client, 401/403 |
| Ticket có thể replay không? | AS kiểm tra one-time semantics và event ID |
| Retry có an toàn không? | Không replay one-time ticket tùy tiện |
| Có concurrency multi-node? | Single-flight/versioning nếu cần |
| Resource Server có kiểm tra audience/scope? | Có, không coi tokenPresent là đủ quyền |
| Logging có lộ credential? | Không log ticket/AT/RT/client secret |
| Có tests unit/integration? | Provider selection, token exchange, storage, error và race |
| Có vận hành/rotation? | Monitor, secret rotation, rollback và incident response |

## 38. Tổng kết

**`OAuth2AuthorizedClientProvider`** là extension point thích hợp khi cần hỗ trợ một **OAuth 2.0 grant tùy chỉnh** trong Spring Security Client. Provider quyết định grant có áp dụng không, kiểm tra authorized client hiện tại, dùng bằng chứng hợp lệ để gọi `OAuth2AccessTokenResponseClient<CustomGrantRequest>` và trả `OAuth2AuthorizedClient` mới. **Manager** điều phối provider chain và storage; **token-response client** xử lý giao thức HTTP/token endpoint; **Resource Server** chịu trách nhiệm kiểm tra token và quyền tài nguyên.

Với Servlet, provider implement `OAuth2AuthorizedClientProvider.authorize(OAuth2AuthorizationContext)` và trả authorized client hoặc `null`. Với Reactive, implement `ReactiveOAuth2AuthorizedClientProvider` và trả `Mono<OAuth2AuthorizedClient>`, `Mono.empty()` hoặc error signal. Cả hai cần được **gắn vào manager đang thực sự được consumer sử dụng**, không chỉ khai báo một bean rồi mong mọi RestClient/WebClient tự biết grant mới.

Custom grant phải được thiết kế như **một giao thức bảo mật đã thỏa thuận với Authorization Server**, không phải mẹo để bypass login, consent hay audience/scope. Cần kiểm soát ticket/assertion, client authentication, token response parsing, clock skew, storage, concurrency, retry và logging. Khi một **chuẩn hoặc provider có sẵn** đáp ứng bài toán, hãy ưu tiên nó. Khi thực sự phải mở rộng, một provider nhỏ, được test kỹ, tách HTTP transport và có ranh giới tin cậy rõ ràng sẽ giúp hệ thống dễ duy trì và an toàn hơn.
