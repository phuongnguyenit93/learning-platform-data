# Thông tin xác thực introspection và luân chuyển bí mật

## 1. Đặt vấn đề: một access token và một credential để kiểm tra token

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, API có thể nhận **opaque access token** và xác thực nó qua endpoint **OAuth 2.0 Token Introspection** của Authorization Server (AS), thay vì tự xác minh JWT bằng public key. Điều dễ nhầm lẫn là luồng này có **hai credential có nguồn gốc và mục đích khác nhau**.

**Credential thứ nhất — Bearer access token của bên gọi API:**

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer 8NsP2s0Y...access-token...
```

**Credential thứ hai — thông tin xác thực của chính Resource Server khi gọi introspection endpoint:**

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <base64-of-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=8NsP2s0Y...access-token...
```

Chuỗi access token trong body là dữ liệu đang được kiểm tra. Basic credential ở HTTP header là bằng chứng Resource Server được phép hỏi AS về token đó. Chúng **không thay thế nhau**:

| Thành phần | Ai giữ và sử dụng? | Dùng với endpoint nào? | Có thể làm gì? |
| --- | --- | --- | --- |
| Bearer **access token** | OAuth client; Resource Server nhận để xử lý request | API nghiệp vụ `/api/**` | Chứng minh ủy quyền cho resource nếu token active và đúng hợp đồng |
| **Introspection client ID** | Resource Server / trusted backend | AS introspection endpoint | Định danh client của Resource Server tại AS, **không phải secret** |
| **Introspection client secret** | Resource Server / secret manager | AS introspection endpoint | Xác thực client của Resource Server theo chính sách AS |
| Private key / certificate dùng cho introspection client auth | Resource Server với cơ chế bất đối xứng hoặc mTLS | AS introspection endpoint | Chứng minh quyền của workload mà không dùng shared secret dạng truyền thống |
| JWT signing private key của AS | Authorization Server | Luồng phát hành JWT | Ký JWT; **không phải** secret để Resource Server gọi introspection |

Một sự cố **introspection client secret hết hạn** có thể khiến tất cả access token hợp lệ đều không thể được kiểm tra. Đây thường là **sự cố xác thực giữa Resource Server và Authorization Server**, không phải mọi user token đồng loạt bị thu hồi.

> **Nguyên tắc:** Tách vòng đời **access token**, **credential gọi introspection**, và **khóa ký JWT**. Luân chuyển một credential không đồng nghĩa tự động luân chuyển hai loại còn lại.

## 2. RFC 7662 và ranh giới tin cậy của introspection

**RFC 7662 — OAuth 2.0 Token Introspection** định nghĩa giao thức Resource Server hỏi AS về trạng thái và metadata của một token. Theo mô hình phổ biến:

1. Client mang access token gọi API.
2. Resource Server trích Bearer token qua `BearerTokenAuthenticationFilter`.
3. `OpaqueTokenAuthenticationProvider` gọi `OpaqueTokenIntrospector.introspect(String token)`.
4. Introspector dùng **credential riêng** để gọi introspection endpoint qua HTTPS.
5. AS xác thực quyền gọi endpoint của Resource Server, kiểm tra token rồi trả response có `active` và metadata.
6. Resource Server tiếp tục áp dụng policy resource, scope và quyền trên dữ liệu.

```mermaid
sequenceDiagram
    participant Client as OAuth Client
    participant API as Spring Resource Server
    participant Vault as Secret Manager
    participant AS as Authorization Server
    Client->>API: Authorization: Bearer access_token
    API->>Vault: Lấy secret đang hoạt động (từ cấu hình/bộ nhớ)
    Vault-->>API: Introspection client credential
    API->>AS: POST introspection (client auth + token)
    AS->>AS: Xác thực API client credential
    alt Client credential sai/hết hạn
        AS-->>API: HTTP 401/403 (tùy chính sách AS)
        API-->>Client: Từ chối an toàn, phân loại dependency/config failure
    else Client credential được phép
        AS->>AS: Xác định trạng thái token
        alt Token inactive
            AS-->>API: 200 {"active": false}
            API-->>Client: Token không được chấp nhận
        else Token active
            AS-->>API: 200 {"active": true, "scope": "...", ...}
            API->>API: Kiểm tra audience, scope, actor/tenant
            API-->>Client: Cho phép hoặc từ chối theo policy
        end
    end
```

Hình trên là sơ đồ khái niệm. Tùy kiến trúc, Resource Server có thể tải bí mật lúc khởi động hoặc nhận bản cập nhật từ secret manager mà **không gọi secret manager trên mỗi HTTP request**. Sơ đồ không hàm ý mỗi lần introspection phải thực hiện một lượt đọc Vault.

### 2.1. Không nhầm HTTP 200 với token hợp lệ

AS có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
```

Nghĩa là **request introspection đã được xử lý**, nhưng token không được công nhận. Một token active có thể được trả:

```json
{
  "active": true,
  "sub": "user-123",
  "client_id": "web-client",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1893456000
}
```

`active=true` chứng tỏ AS chấp nhận token theo ngữ nghĩa endpoint, nhưng API vẫn cần kiểm tra resource binding, scope, tenant và nghiệp vụ khi hợp đồng yêu cầu. **Không cấp quyền quản trị chỉ vì AS xác nhận token active**.

### 2.2. Introspection client được quyền nhìn thấy những gì?

Endpoint introspection có thể tiết lộ thông tin về subject, client, scope, audience và trạng thái token. Vì vậy:

- AS phải **bảo vệ endpoint** bằng authentication/authorization và TLS theo RFC 7662.
- Credential của Resource Server nên chỉ có quyền **introspect những token/resource cần thiết**.
- Không dùng một secret chung có quyền xem token của mọi tenant nếu có thể tách scope/quyền.
- Không gửi response introspection đầy đủ cho bên gọi API.
- AS có thể giới hạn metadata trả về theo resource/client đang introspect; API phải biết hợp đồng dữ liệu cụ thể.

Trong hệ thống nhiều Resource Server, một secret dùng chung làm tăng **blast radius** khi lộ credential. Hãy ưu tiên client registration/cấp quyền riêng theo resource hoặc trust domain khi AS hỗ trợ.

## 3. Client authentication tại introspection endpoint: không chỉ có Basic

OAuth 2.0 cho phép nhiều cơ chế xác thực client, tùy AS và client registration. **Không phải Spring Boot opaque-token properties tự động hỗ trợ mọi cơ chế.** Chỉ lựa chọn một cơ chế mà AS đã đăng ký, có khả năng cấp credential và có implementation client tương ứng.

| Cơ chế | Nguyên lý | Đặc điểm vòng đời |
| --- | --- | --- |
| **`client_secret_basic`** | HTTP Basic Authorization chứa client ID và client secret theo encoding của giao thức | Phải luân chuyển shared secret; tránh log header |
| **`client_secret_post`** | Gửi client ID/secret trong form body khi AS hỗ trợ | Secret nằm trong HTTP body; phải tránh body logging và hạn chế dùng nếu Basic là lựa chọn tốt hơn |
| **`private_key_jwt`** | Resource Server ký một client assertion JWT bằng private key, AS xác minh bằng public key đã đăng ký | Luân chuyển private key/public JWK; quản lý `kid`/`jti`/`exp`, chống replay |
| **mTLS client authentication** | TLS client certificate chứng minh danh tính client, AS gắn certificate với client registration | Luân chuyển certificate/private key và TLS trust; cần cửa sổ overlap |
| **Client authentication tùy chỉnh** | Phụ thuộc vendor hoặc gateway/trust domain | Phải có hợp đồng riêng, không tự giả định tương thích RFC |

**Spring Security Resource Server opaque-token cấu hình mặc định thường dùng introspection URI, client ID và client secret**, phù hợp kịch bản client secret. Với mTLS hoặc `private_key_jwt`, cần cấu hình HTTP client/`OpaqueTokenIntrospector` và Authorization Server theo hợp đồng; không chỉ đặt thêm property `client-secret` rồi kỳ vọng tự chuyển sang cơ chế khác.

### 3.1. HTTP Basic và lỗi encoding

Theo OAuth 2.0, client ID và secret có thể chứa các ký tự như `+`, `:`, `%`, `/`. Cơ chế Basic dành cho OAuth client authentication có quy tắc encoding trước khi đưa vào HTTP Basic credentials. Chỉ nối `clientId + ":" + secret` rồi Base64 một cách tùy tiện **có thể sai** trong những trường hợp credential có ký tự đặc biệt.

Ví dụ giả định:

```text
client_id     = orders:api+introspection
client_secret = p@ss/word+2026
```

**Không bao giờ dùng hai chuỗi này làm secret thật.** Chúng chỉ cho thấy việc double-encoding hoặc không encoding có thể làm AS trả 401 dù client ID/secret về mặt logic là đúng.

Trong Spring Security 6.5+ theo API builder được tài liệu hóa:

```java
OpaqueTokenIntrospector introspector =
        SpringOpaqueTokenIntrospector
                .withIntrospectionUri(introspectionUri)
                .clientId(rawClientId)
                .clientSecret(rawClientSecret)
                .build();
```

Builder nhận **giá trị chưa URL-encode** rồi xử lý mã hóa phù hợp. Khi nâng cấp mã cũ đã **lưu secret ở dạng percent-encoded**, không tiếp tục nạp nguyên chuỗi đã encode vào builder rồi mã hóa lần hai.

### 3.2. Basic khác Bearer token của caller

Trong một request tới AS:

```http
POST /oauth2/introspect HTTP/1.1
Authorization: Basic <introspection-client-credential>
Content-Type: application/x-www-form-urlencoded

token=<caller-access-token>
```

Basic ở đây không phải `Authorization: Bearer` của người dùng. AS cần phân biệt Resource Server đang hỏi **token nào**, Resource Server đó **là client nào** và **được phép introspect token ở phạm vi nào**.

**Không chuyển nguyên Bearer token làm Basic password**, cũng không dùng introspection client secret làm access token để gọi API. Nếu cần gọi một endpoint khác của AS bằng Bearer credential, phải có registration và flow riêng theo hợp đồng.

### 3.3. Mã thông báo client assertion cho private_key_jwt

Trong mô hình `private_key_jwt`, Resource Server thường phải ký một JWT client assertion ngắn hạn có các claim cần thiết, ví dụ `iss`/`sub` định danh client, `aud` hướng tới endpoint được AS yêu cầu, `exp`, `iat`, `jti`. AS phải xác minh chữ ký và chính sách chống replay.

Sơ đồ khái niệm:

```text
Resource Server private key
  -> ký client assertion JWT
  -> gửi client_assertion_type + client_assertion trong introspection request
Authorization Server
  -> tìm public key đã đăng ký của introspection client
  -> kiểm tra chữ ký, aud, thời hạn và jti
  -> chỉ sau đó introspect access token của caller
```

Đây là một loại JWT **xác thực client khi gọi introspection**, **khác** JWT access token của người dùng. `kid` trên client assertion giúp AS chọn public key của client đã được đăng ký; `kid` không tự tạo trust.

## 4. Cấu hình Spring Boot thông dụng, không lộ secret trong source

Một Servlet Resource Server dùng introspection có thể khai báo:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Các biến môi trường trong ví dụ phải được provision qua **secret manager/triển khai an toàn**; không ghi secret production vào file YAML được commit lên Git.

Ví dụ SecurityFilterChain:

```java
@Configuration
class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

Với dependency/configuration Spring Boot phù hợp và không có custom bean thay thế, Boot có thể tự tạo `OpaqueTokenIntrospector` từ ba properties. `OpaqueTokenAuthenticationProvider` gọi introspector để lấy principal/authorities. Sau đó URL/method authorization kiểm tra scope.

**Không nên mặc định gọi `oauth2ResourceServer().jwt()` khi AS cấp opaque token.** Nếu cấu hình JWT, Spring dùng `JwtDecoder`; nếu cấu hình opaque, Spring dùng `OpaqueTokenIntrospector`. Token có dạng JWT vẫn có thể được gửi tới introspection nếu chain chủ động chọn opaque-token flow.

### 4.1. Không ghi bí mật vào cấu hình ví dụ chạy thật

Không làm:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: orders-api
          client-secret: my-actual-long-lived-secret # KHÔNG COMMIT
```

Trong môi trường sản xuất, dùng một trong những cơ chế phù hợp:

- Secret manager (Vault, cloud secret manager hoặc giải pháp nội bộ có IAM).
- Kubernetes Secret volume được kiểm soát RBAC/namespace/encryption, cùng cơ chế đọc lại an toàn.
- Deployment injection có giới hạn đọc, rotation và audit.
- Secret reference trong hệ thống quản lý cấu hình có quyền truy cập tối thiểu.

**Environment variables** tiện cho cấu hình nhưng vẫn có thể bị lộ qua process inspection, crash dumps, log diagnostics hoặc quyền xem cấu hình của nền tảng. Không coi “đã đưa vào environment variable” là đủ nếu không có IAM, phân quyền, audit và quy trình luân chuyển.

### 4.2. Bảo vệ cả client ID và secret như tài sản có ngữ nghĩa khác nhau

Client ID thường **không phải bí mật**, nhưng tiết lộ nó có thể giúp attacker xác định registration đang dùng. Client secret là **bí mật xác thực**. Secret manager có thể lưu cả hai cùng một cấu hình versioned để tránh hiện tượng deploy lấy client ID mới nhưng secret cũ.

Nếu đổi **client registration** trong một lần migration, cặp `(client-id, client-secret)` nên được coi là **một credential bundle nhất quán**, không cập nhật hai trường ở hai thời điểm không kiểm soát.

## 5. OpaqueTokenIntrospector là điểm mở rộng cần giữ ổn định

Trong Spring Security Servlet, interface:

```java
package org.springframework.security.oauth2.server.resource.introspection;

public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

Hợp đồng này cho phép:

- Để Boot xây `SpringOpaqueTokenIntrospector` từ properties.
- Chủ động xây `SpringOpaqueTokenIntrospector` khi cần tùy chỉnh HTTP client.
- Bọc bằng decorator để kiểm tra thêm issuer/audience, metrics hoặc policy fail-closed.
- Thay thế underlying implementation khi nâng cấp framework mà không đổi service/business code.

Ví dụ bean cho **Spring Security 6.5+**:

```java
@Configuration
class IntrospectionConfiguration {

    @Bean
    OpaqueTokenIntrospector introspector(
            @Value("${introspection.uri}") String uri,
            @Value("${introspection.client-id}") String clientId,
            @Value("${introspection.client-secret}") String clientSecret) {

        return SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();
    }
}
```

Builder trên được bổ sung vào dòng Spring Security **6.5**; dự án cũ hơn cần sử dụng constructor/`RestOperations` có sẵn ở phiên bản đang chạy. Dòng Spring Security mới hơn cũng có `RestClientOpaqueTokenIntrospector` dùng `RestClient` từ **7.1**. Khi triển khai, hãy xem version của dependency `spring-security-oauth2-resource-server` thực tế; code bean phải tương thích phiên bản cụ thể.

**Nếu đã tự định nghĩa `OpaqueTokenIntrospector` bean**, việc tự động cấu hình của Boot có thể lùi bước, còn cấu hình `.opaqueToken(opaque -> opaque.introspector(...))` ở chain có thể ghi đè lựa chọn bean. Vì vậy cần kiểm tra **introspector nào thực sự được dùng**.

## 6. Bản chất của “luân chuyển bí mật” (secret rotation)

**Secret rotation** là quá trình thay thế credential xác thực Resource Server khi gọi introspection endpoint mà vẫn bảo đảm:

1. API **không bao giờ chấp nhận token chưa được introspect đúng**.
2. Không làm lộ secret cũ hoặc mới.
3. Tránh gián đoạn dịch vụ trong phạm vi khả năng AS hỗ trợ.
4. Có thể chứng minh credential mới đã hoạt động **trước khi vô hiệu credential cũ**, nếu có cửa sổ overlap.
5. Giảm thời gian một secret đã nghi lộ còn được dùng.
6. Có runbook rollback và kế hoạch xử lý sự cố rõ ràng.

Một vòng đời credential:

```mermaid
flowchart LR
    NEW["Tạo secret mới<br/>trong AS/secret manager"] --> STAGE["Phân phối bản mới<br/>cho Resource Servers"]
    STAGE --> ACT["Kích hoạt bản mới<br/>theo phiên bản"]
    ACT --> CHECK["Xác nhận introspection<br/>bằng credential mới"]
    CHECK --> RETIRE["Thu hồi secret cũ<br/>theo cửa sổ được phép"]
    RETIRE --> AUDIT["Kiểm tra audit, xóa<br/>bản sao/backup không cần"]
```

Không nên chỉ “đổi chuỗi trong YAML rồi restart” mà chưa biết AS có hỗ trợ **hai secret active đồng thời** hay không. Nếu AS chỉ cho một secret mỗi client, việc thay secret có thể khiến các instance cũ mất khả năng introspect ngay lập tức.

### 6.1. Trước khi rotation phải hỏi Authorization Server

- Một client registration có thể có **hai client secret song song** trong giai đoạn chuyển tiếp không?
- Có chức năng tạo secret mới mà **không thu hồi secret cũ ngay** không?
- Client ID có giữ nguyên trong rotation hay phải tạo **client ID mới**?
- Secret mới bắt đầu hiệu lực lúc nào; có độ trễ phân phối/cache không?
- Có thể kiểm tra credential mới trên introspection endpoint thử nghiệm mà không phải thao tác token thật không?
- Credential cũ có thể bị thu hồi độc lập và có log xác nhận khi nào ngừng được dùng không?
- Quy trình khẩn cấp khi nghi lộ secret khác quy trình định kỳ như thế nào?
- Có hỗ trợ **mTLS** hoặc `private_key_jwt` làm phương án giảm rủi ro shared secret không?

Những khả năng này **thuộc AS/provider**, không do Spring Security tự quyết định.

## 7. Kịch bản A: AS chấp nhận đồng thời secret cũ và mới

Đây là điều kiện thuận lợi để **luân chuyển không gián đoạn hoặc gần không gián đoạn**, nếu áp dụng đúng.

Giả sử có:

```text
client_id = orders-api-introspector
secret_v1 = [old secret — do not log]
secret_v2 = [new secret — do not log]
```

### Giai đoạn 1 — Chuẩn bị

1. Tạo `secret_v2` trong AS bằng nguồn ngẫu nhiên/độ mạnh theo chính sách.
2. **Giữ `secret_v1` active** trong AS.
3. Lưu `secret_v2` vào secret manager dưới **version mới**, không ghi vào Git, ticket hoặc Slack.
4. Xác minh quyền đọc secret chỉ thuộc service account/deployment cần dùng.
5. Chuẩn bị rolling deployment hoặc cơ chế cập nhật introspector đã được kiểm thử.

### Giai đoạn 2 — Chuyển Resource Servers

1. Roll out ứng dụng/secret reference để từng instance dùng `secret_v2`.
2. Giữ các instance chưa cập nhật tiếp tục dùng `secret_v1` trong cửa sổ overlap.
3. Từ mỗi vùng/cluster, chạy **health probe có xác thực** tới introspection endpoint theo phương án an toàn.
4. Theo dõi số lỗi introspection client auth, 401/403 từ AS, timeout và latency.
5. Nếu lỗi, rollback instance về bundle cũ **khi AS vẫn cho phép v1**.

### Giai đoạn 3 — Thu hồi bản cũ

1. Xác nhận **mọi instance** đang sử dụng v2, bao gồm background jobs, standby, disaster-recovery và long-lived processes.
2. Kiểm tra AS logs xem còn request với v1 không.
3. Vô hiệu `secret_v1` tại AS.
4. Theo dõi lỗi sau thu hồi trong một cửa sổ giám sát.
5. Gỡ v1 khỏi secret manager/CI/CD runtime copies theo retention/audit policy.

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant SM as Secret Manager
    participant RS1 as Resource Server v1
    participant RS2 as Resource Server v2
    AS->>AS: Tạo secret_v2, giữ v1 active
    AS->>SM: Secret v2 (qua workflow được ủy quyền)
    SM-->>RS2: Phân phối v2
    RS1->>AS: Introspect bằng v1
    AS-->>RS1: Thành công
    RS2->>AS: Introspect bằng v2
    AS-->>RS2: Thành công
    RS2->>AS: Probe/traffic xác nhận v2 ổn định
    AS->>AS: Thu hồi v1 sau khi rollout toàn bộ
    RS2->>AS: Tiếp tục dùng v2
    AS-->>RS2: Thành công
```

**Không đặt thời gian overlap tùy tiện:** Nó phải xét số lượng instance, tốc độ rollout, cache cấu hình, client auth logs, thời gian phát hiện lỗi và yêu cầu thu hồi khi nghi lộ.

## 8. Kịch bản B: AS chỉ cho một secret active trên mỗi client

Một số Authorization Server khi “regenerate client secret” sẽ **lập tức vô hiệu hóa secret cũ**. Với rolling deployment, đây là rủi ro:

```text
T0: Tất cả Resource Server dùng secret_v1.
T1: AS thay v1 bằng v2 ngay.
T2: Instance còn dùng v1 gọi introspection → AS trả 401.
T3: Chỉ sau khi instance được cập nhật, introspection mới chạy lại.
```

Trong trường hợp này, không thể bảo đảm **zero downtime** chỉ bằng thứ tự “đổi AS trước” hay “đổi ứng dụng trước”. Cần thiết kế phương án khác:

### 8.1. Tạo hai client registrations độc lập

Nếu AS hỗ trợ, tạo:

```text
orders-introspector-v1 → secret_v1 (đang hoạt động)
orders-introspector-v2 → secret_v2 (mới)
```

Cấp quyền introspection **tương đương nhưng tối thiểu** cho v2; xác minh scope, audience/resource visibility và rate limits. Khi v2 đã hoạt động, rolling deployment các Resource Server sang **cặp `(client-id-v2, secret-v2)`**. Sau khi v2 phục vụ ổn định, thu hồi client registration v1.

Đây là **blue-green introspection client registration**, không phải phát hành access token mới cho người dùng. Quyền của hai client registrations phải được review: đừng vô tình cấp quyền mở rộng khi tạo v2.

### 8.2. Cắt chuyển đồng bộ có cửa sổ gián đoạn

Nếu AS không hỗ trợ nhiều secrets và không cho nhiều client registrations tương đương, một khoảng gián đoạn **có thể không tránh được**. Khi đó:

- Lập lịch maintenance window hoặc traffic draining.
- Chuẩn bị secret mới/cấu hình trên instance chưa active trước khi chuyển.
- Đổi AS và chuyển runtime theo quy trình phối hợp.
- Kiểm tra introspection từng vùng trước khi nhận traffic.
- Công bố rõ tình trạng vận hành thay vì **fail-open** với token chưa được xác thực.

Không được hứa “không downtime” nếu provider không hỗ trợ overlap hoặc quy trình cutover không có tính nguyên tử.

## 9. Kịch bản C: rotation khẩn cấp khi nghi secret đã bị lộ

Luân chuyển định kỳ tối ưu tính liên tục. **Rotation khẩn cấp** ưu tiên **chấm dứt khả năng lạm dụng secret bị lộ**.

Quy trình điển hình:

1. Xác định phạm vi: client registration nào, AS nào, môi trường nào và Resource Servers nào có thể bị ảnh hưởng.
2. Ưu tiên **thu hồi/khóa credential nghi lộ** nhanh theo chính sách ứng cứu, dù có thể gây gián đoạn.
3. Cấp credential mới qua kênh an toàn, giới hạn quyền introspection; không tái dùng secret cũ ở môi trường khác.
4. Rà soát AS logs, token metadata truy vấn bất thường và các hoạt động quản trị quanh credential.
5. Triển khai credential mới và xác nhận API không còn phụ thuộc bản cũ.
6. Làm sạch bản sao secret trong CI/CD variables, logs, file tạm, crash dumps, môi trường thử nghiệm và tài liệu nếu có.
7. Phân tích nguồn lộ, cập nhật IAM/rotation interval và thủ tục phòng ngừa.

**Không giữ secret nghi đã bị lộ active chỉ để đạt zero downtime.** Có thể dùng phương án blue-green hoặc thay đổi khẩn cấp, nhưng quyết định cần dựa trên mức độ rủi ro.

### 9.1. Lộ introspection secret gây tác hại gì?

Điều này tùy quyền client ở AS:

- Nếu credential chỉ cho phép introspection, attacker có thể **truy vấn trạng thái và metadata của token mà họ biết/đoán/đánh cắp được**, tùy policy AS.
- Nếu secret bị tái sử dụng cho client credentials grant, token endpoint hoặc API quản trị, tác động có thể **lớn hơn nhiều**.
- Nếu introspection endpoint không giới hạn token/resource visibility, có thể tạo kênh rò rỉ thông tin cross-tenant.
- Nếu secret được hardcode ở nhiều dịch vụ, việc thu hồi ảnh hưởng đồng thời nhiều nơi.

Hãy cấp **quyền tối thiểu**, tách client registration theo chức năng và tránh dùng một credential chung cho introspection và những hành động nhạy cảm khác nếu AS cho phép.

## 10. Tách secret rotation khỏi access-token và signing-key rotation

Ba thao tác khác nhau:

| Thao tác | Thay thế thứ gì? | Ảnh hưởng chủ yếu |
| --- | --- | --- |
| **Introspection secret rotation** | Credential Resource Server dùng để xác thực với AS introspection endpoint | Khả năng gọi `introspect` của API |
| **Access token rotation/refresh** | Access token mà OAuth client gửi tới API | Quyền/phiên của một client, token expiry/revocation |
| **JWT signing-key rotation** | Private/public key dùng ký và xác minh JWT, với `kid`/JWKS | Xác minh chữ ký JWT; có thể ảnh hưởng client assertion nếu khóa đó cũng phục vụ client auth theo hợp đồng |

Khi đổi **introspection client secret**, access token của người dùng **không bắt buộc bị phát hành lại**. AS vẫn có thể xác nhận các token cũ active bằng credential mới nếu policy của AS không thay.

Khi AS xoay **JWT signing key**, một opaque-token Resource Server dùng introspection có thể không cần quản lý public JWKS cho chính access token. Nhưng nếu Resource Server dùng **`private_key_jwt` client authentication** hoặc một lớp JWT khác, phải quản lý keys của cơ chế đó độc lập.

Điều này quan trọng trong điều tra:

```text
Tất cả opaque access token cùng lúc bị API từ chối
  -> kiểm tra introspection client credentials, AS endpoint, TLS, network.

Chỉ một access token bị active=false
  -> kiểm tra riêng token expiry/revocation và policy AS.

JWT validation lỗi sau JWKS rotation
  -> điều tra signing-key/JWKS; không tự đổi introspection secret.
```

## 11. Bí mật được nạp lúc nào? Rủi ro “đã đổi secret trong Vault nhưng API vẫn dùng bản cũ”

Một bean được tạo khi Spring context khởi động:

```java
@Bean
OpaqueTokenIntrospector introspector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    return SpringOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();
}
```

Thông thường bean này giữ HTTP client/credentials được dựng từ **các giá trị đã inject lúc khởi tạo**. Nếu secret manager đổi bản mới, **không được giả định bean tự đọc lại secret trên mỗi request**.

Kết quả có thể là:

```text
Vault current secret = v2
Running instance bean = vẫn dùng v1
AS đã thu hồi v1   = introspection 401
```

Các cách nạp bản mới:

1. **Rolling restart/redeploy**: mỗi instance khởi tạo bean mới với v2; đơn giản và dễ xác minh.
2. **Refresh cấu hình có kiểm soát**: ứng dụng dùng cơ chế refresh thực sự xây lại dependency/HTTP client và có test concurrency/lifecycle.
3. **Dynamic delegation**: một wrapper ổn định trỏ sang một introspector mới đã được khởi tạo khi có event rotation.

**Không tự dùng `@RefreshScope`, file watcher hoặc polling** mà không hiểu cơ chế bean destruction/refresh, credential leak, exception handling và request đang xử lý. Tùy môi trường, rolling redeploy ổn định có thể là lựa chọn tốt hơn.

### 11.1. Containerized deployments

Một Kubernetes Secret được cập nhật không đồng nghĩa:

- Biến môi trường trong process đang chạy đổi ngay.
- Spring `@Value` sẽ được re-inject tự động.
- Introspection HTTP client đã tạo lúc startup được rebuild.

Secret dạng **environment variable** thường yêu cầu restart process/pod để nhận giá trị mới. Secret được mount dạng file có thể thay đổi trên volume theo cơ chế nền tảng, nhưng application phải **chủ động đọc lại và nạp credential**. Hãy test đúng platform và CSI/secret manager provider đang dùng.

## 12. Dynamic reload bằng delegate: chỉ thay implementation sau khi chuẩn bị

Một cách tách business code khỏi rotation là giữ interface `OpaqueTokenIntrospector` ổn định, nhưng bên trong dùng `AtomicReference` tới introspector hiện hành.

Ví dụ **Spring Security 6.5+**:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
        .SpringOpaqueTokenIntrospector;

public final class SwappableOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final AtomicReference<OpaqueTokenIntrospector> current;

    public SwappableOpaqueTokenIntrospector(
            OpaqueTokenIntrospector initial) {
        this.current = new AtomicReference<>(initial);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        return current.get().introspect(token);
    }

    public void activate(OpaqueTokenIntrospector replacement) {
        current.set(replacement);
    }

    public static OpaqueTokenIntrospector createDelegate(
            String uri,
            String clientId,
            String rawClientSecret) {
        return SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(rawClientSecret)
                .build();
    }
}
```

Một coordinator được ủy quyền có thể:

```java
OpaqueTokenIntrospector next =
        SwappableOpaqueTokenIntrospector.createDelegate(
                trustedUri, newClientId, newRawSecret);

// Chỉ kích hoạt sau khi xác nhận registration/credential mới sẵn sàng.
swappableIntrospector.activate(next);
```

**Đây là skeleton kiến trúc**, không phải hệ thống rotation tự động hoàn chỉnh. Những việc cần triển khai bên ngoài ví dụ:

- Chỉ nhận update từ **secret manager/control plane đã xác thực**, không từ HTTP client.
- Cấu hình introspection URI, TLS, timeout và auth method đã được phê duyệt.
- Kiểm tra credential mới thực sự dùng được trước khi kích hoạt.
- Không lưu/log hai bản secret lâu hơn cần thiết.
- Quản lý lifecycle, connections và tài nguyên của HTTP client cũ nếu implementation sở hữu chúng.
- Ghi version/ID **không nhạy cảm** trong metric/log để xác nhận rollout.
- Kiểm soát đồng thời: request đã lấy `current.get()` trước khi swap có thể vẫn dùng delegate cũ.
- Luân chuyển trên **mọi instance**; `AtomicReference` chỉ giải quyết trong **một JVM**, không đồng bộ cả cluster.

### 12.1. Vì sao cần cửa sổ overlap dù có AtomicReference?

Giả sử một request đã bắt đầu `introspect` bằng secret v1, sau đó một thread khác gọi `activate(v2)`. Request cũ có thể vẫn đang dùng v1 khi AS thu hồi v1, nên thất bại.

Vì vậy dynamic swap chỉ giúp tránh recreate Spring context; nó **không thay thế** việc phối hợp AS active secrets, in-flight requests và thứ tự thu hồi cũ.

## 13. Có nên tự động retry bằng secret cũ hoặc mới?

Một số đội muốn cấu hình:

```text
Thử introspection bằng v2.
Nếu AS trả 401, tự thử bằng v1.
```

Đây không phải mặc định an toàn cho mọi hệ thống:

- Kéo dài khoảng thời gian credential cũ được dùng, trái mục tiêu rotation khi nghi lộ.
- Có thể tạo double load và làm lộ khác biệt trạng thái khi fallback.
- Nếu HTTP 401 do một vấn đề khác (registration sai, TLS proxy hoặc client auth failure), retry liên tục có thể gây **retry storm**.
- Hai client registrations có thể có **quyền introspection khác nhau**, nên kết quả active/metadata khác nhau.
- Dễ quên gỡ fallback, khiến v1 tồn tại vô thời hạn.

Trong **rotation định kỳ có overlap**, một cơ chế fallback **ngắn hạn, bị giới hạn, có feature flag và metrics** đôi khi khả thi, nhưng chỉ khi AS contract và threat model cho phép. Không retry token inactive (`active=false`) bằng secret khác với mục đích “tìm cách làm token active” — đó có thể là vi phạm resource scope/visibility.

Nếu secret đã nghi lộ, **không fallback sang v1** chỉ để tăng availability. Thông thường an toàn và dễ vận hành hơn là thực hiện **rolling update/blue-green** có kiểm soát, thay vì làm logic xác thực phức tạp cho từng request.

## 14. Tùy chỉnh HTTP client khi cần mTLS, proxy hoặc timeout

Introspection phụ thuộc network. Một client production có thể cần:

- TLS certificate validation, trust store phù hợp và chống nối tới endpoint giả.
- mTLS client certificate nếu AS đăng ký `tls_client_auth` hoặc `self_signed_tls_client_auth`.
- Connect/read timeout và giới hạn concurrency.
- Proxy được phê duyệt, giới hạn egress host/port.
- Rate limiting/circuit breaker/backoff hợp lý.
- Logging redaction cho `Authorization` và body chứa `token`.

Với những phiên bản hỗ trợ, `SpringOpaqueTokenIntrospector` có thể nhận một `RestOperations` tùy chỉnh; Spring Security 7.1+ có `RestClientOpaqueTokenIntrospector` sử dụng `RestClient`.

### 14.1. HTTP client xác thực Basic khi tự tạo

Ví dụ khái niệm với `RestTemplate`:

```java
RestTemplate restTemplate = new RestTemplate();
restTemplate.getInterceptors().add(
        new BasicAuthenticationInterceptor(clientId, clientSecret));

OpaqueTokenIntrospector introspector =
        new SpringOpaqueTokenIntrospector(
                introspectionUri, restTemplate);
```

**Quan trọng:** Đây là ví dụ về việc **cấu hình authentication cho HTTP client**, không phải hướng dẫn đầy đủ về RFC 6749 encoding và rotation. Với credential có ký tự đặc biệt, cần đối chiếu version và wire behavior. Nếu không cần tùy chỉnh HTTP client, dùng builder Spring Security 6.5+ với **raw credentials** sẽ giảm nguy cơ sai encoding.

Không nên tự tạo `RestOperations` mà quên gắn client authentication; một introspector sẽ gửi token mà không có credential phù hợp, AS từ chối.

### 14.2. Introspection URI không được lấy từ token

Endpoint phải đến từ **cấu hình/trust domain được phê duyệt**:

```text
trusted_uri = https://login.example.test/oauth2/introspect
```

Không làm:

```java
// SAI: URL do bên gửi token đề nghị dẫn đến SSRF/key trust confusion.
String introspectionUri = request.getHeader(
        "X-Introspection-Endpoint");
```

Nếu API nhận nhiều issuer, mỗi issuer phải có endpoint/credential/policy **được cấu hình tin cậy trước**, và cơ chế định tuyến không được tự tạo issuer từ giá trị chưa xác thực.

## 15. Luân chuyển mTLS certificate và private_key_jwt key

Nếu hệ thống dùng xác thực client **không dựa trên shared secret**, vẫn có vòng đời credential cần quản lý.

### 15.1. mTLS

Một Resource Server có certificate và private key được AS tin theo client registration:

```text
Resource Server -> TLS handshake với client certificate C1
Authorization Server -> xác minh certificate/trust policy
Authorization Server -> cho phép gọi introspection endpoint
```

Rotation cần:

1. Tạo certificate/private key mới C2 trong HSM/KMS/keystore nếu phù hợp.
2. Đăng ký C2/trust chain hoặc phương thức nhận diện mới ở AS trước khi dùng.
3. Xác minh TLS handshake và quyền introspection của C2.
4. Triển khai keystore/HTTP client dùng C2.
5. Giữ C1 trong cửa sổ overlap nếu chính sách AS cho phép, lưu ý connection pooling/TLS session reuse.
6. Thu hồi C1 và gỡ key cũ, theo dõi certificate expiry và revocation.

Không nhầm certificate dùng **TLS client authentication** với public JWK dùng **xác minh JWS access token**.

### 15.2. private_key_jwt

Nếu introspection endpoint chấp nhận client assertion:

```text
Client assertion:
  iss = introspection client ID
  sub = introspection client ID
  aud = AS endpoint identifier theo hợp đồng
  exp = thời hạn rất ngắn
  jti = mã chống replay
  signed_by = client private key K1
```

Rotation:

- Công bố/đăng ký **public key K2** hoặc JWKS mới với AS.
- Giữ K1/K2 song song theo cửa sổ được phép.
- Chuyển ký client assertion sang private key K2 và `kid` tương ứng.
- Xác nhận AS chấp nhận assertion mới và từ chối replay.
- Thu hồi K1 khi mọi instance đã chuyển.

`kid` chỉ giúp AS chọn public key đã đăng ký cho client; **không tự tạo sự tin cậy**. Private key phải được bảo vệ, có expiry/lifecycle và không đưa vào source control.

**Không có cấu hình property Spring Boot opaque-token mặc định nào được phép suy diễn là tự xử lý toàn bộ mTLS/private_key_jwt rotation.** Cần implementation và kiểm thử protocol thật.

## 16. Điều gì xảy ra khi introspection client credential sai?

Có ba tình huống rất dễ nhầm:

**Tình huống A — Caller gửi access token không hợp lệ:**

```text
API gọi AS bằng credential introspection hợp lệ.
AS trả {"active": false}.
Kết luận: token caller không được chấp nhận.
```

**Tình huống B — API dùng introspection secret hết hạn/sai:**

```text
API gọi AS bằng Basic credential cũ.
AS trả HTTP 401 (hoặc phản hồi auth failure theo policy).
Kết luận: lỗi client authentication giữa API và AS.
```

**Tình huống C — AS tạm thời không truy cập được:**

```text
API timeout/TLS/DNS/connect error/HTTP 5xx.
Không có response introspection đáng tin cậy.
Kết luận: dependency unavailable; không được giả định token valid.
```

| Tín hiệu | Lớp lỗi | Phải làm gì |
| --- | --- | --- |
| `active: false` | Token của caller không active | Không tạo authenticated principal |
| AS HTTP 401/403 | Credential/quyền introspection của Resource Server | Kiểm tra registration, secret version, encoding, TLS, scopes |
| AS HTTP 429 | Giới hạn số request | Giảm tải/backoff có giới hạn, không fail-open |
| AS HTTP 5xx hoặc timeout | AS/network unavailable | Fail-closed; cảnh báo sự cố dependency |
| AS trả JSON malformed | Protocol response không hợp lệ | Không tin metadata; lỗi có kiểm soát |
| AS trả active=true nhưng thiếu audience bắt buộc | Sai contract resource | Từ chối theo policy hoặc sửa cấu hình provider |
| Token active=true, thiếu scope endpoint | Authorization | Thường 403, không đổi introspection secret |

### 16.1. API trả HTTP gì cho client?

Trong Bearer Resource Server:

- Không có Bearer token khi endpoint cần xác thực → thường **401**.
- Token được xác định inactive → thường **401 invalid_token**.
- Token active và được xác thực nhưng thiếu scope → thường **403 insufficient_scope**.
- Lỗi AS client credentials hoặc AS unavailable → phụ thuộc exception mapping/handler Spring Security và triển khai. Một số cấu hình có thể trả 401 cho lỗi trong authentication chain, nhưng **về mặt vận hành** không được gắn nhãn “caller token invalid” nếu nguyên nhân thực là client secret sai; lỗi hạ tầng có thể được phản hồi như 5xx/503 theo policy.

Không tạo `WWW-Authenticate` tiết lộ secret version, nội dung Basic header, nội bộ AS URL hoặc stack trace. API có thể trả một mã lỗi công khai chung, còn log nội bộ có correlation ID và phân loại nguyên nhân.

## 17. Validation của principal sau introspection

Introspection response có thể chứa `scope`, `sub`, `client_id`, `aud`, `iss`, nhưng **không phải endpoint nào trả cùng metadata**. Spring Security thường ánh xạ các scope thành authorities `SCOPE_...` và principal thành `OAuth2AuthenticatedPrincipal`.

Ví dụ controller:

```java
@GetMapping("/api/me")
public Map<String, String> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    Object subject = principal.getAttribute("sub");
    return Map.of(
            "subject",
            subject == null ? "unknown" : subject.toString());
}
```

Ví dụ chỉ minh họa cách đọc attribute; production cần hợp đồng dữ liệu và chính sách riêng tư. Không trả toàn bộ introspection response hoặc secret ra frontend.

**Tuyệt đối không**:

- Coi `active=true` là quyền gọi mọi resource.
- Dùng email hoặc tên hiển thị làm định danh ổn định nếu chưa có contract.
- Tự thêm `ROLE_ADMIN` chỉ vì một claim tùy chỉnh có chuỗi `"admin"`.
- Cấp mọi scope cho user vì introspection credentials của API có quyền rộng.
- Dùng kết quả introspection của **token khác** do cache key sai.

### 17.1. Ràng buộc audience bằng decorator

Nếu issuer cam kết trả `aud`, một policy wrapper có thể bắt buộc token hướng đến chính API:

```java
public final class ResourceBindingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public ResourceBindingIntrospector(
            OpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = delegate;
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

        Object aud = principal.getAttribute("aud");
        boolean accepted =
                (aud instanceof String one
                        && expectedAudience.equals(one))
                || (aud instanceof Collection<?> many
                        && many.contains(expectedAudience));

        if (!accepted) {
            throw new BadOpaqueTokenException(
                    "Access token is not for this resource");
        }
        return principal;
    }
}
```

Các imports được lược bớt. Wrapper này chỉ nhận principal do **delegate đã introspect thành công**; nếu credential introspection của API sai, delegate phải ném exception và wrapper **không tự tạo user giả**.

Nếu AS không trả `aud` nhưng bảo đảm introspection credential chỉ kiểm tra được token của đúng resource, phải mô tả và kiểm thử **bảo đảm tương đương**; không nên tự dựng audience từ input của client.

## 18. Caching introspection khi đang luân chuyển credential

Caching làm giảm số lần gọi AS nhưng có những ảnh hưởng cần xét trong secret rotation.

### 18.1. Hai vòng đời cache khác nhau

1. **Credential cache:** process/bean đang giữ secret v1 hoặc v2, có thể cần khởi tạo lại sau rotation.
2. **Introspection result cache:** API đang giữ metadata `active=true` và authorities cho một access token, có TTL theo policy.

Không được nhầm “đã thay secret” với “đã làm mới mọi kết quả introspection”. Nếu result cache vẫn trả principal đã xác thực, một outage do secret sai **có thể không xuất hiện cho đến khi cache miss**, khiến rollout tưởng thành công.

### 18.2. Kiểm tra rotation không chỉ qua cache hit

Một probe hợp lệ cần buộc chạy **real introspection request bằng credential mới**, không chỉ trả kết quả từ cache cũ. Có thể dùng một token kiểm thử được AS phát hành/cho phép, với quyền rất hạn chế; tránh đưa production access token vào công cụ giám sát chung.

Khi sử dụng caching:

- TTL không vượt token expiry và giới hạn revocation SLA.
- Không lưu nguyên token trong logs/metrics hoặc key cache có thể quan sát.
- Cache result cần gắn với đúng issuer/resource-policy context nếu có nhiều AS/tenant.
- Có chiến lược vô hiệu hóa cache khi thay đổi policy hoặc phát hiện token bị revoke.
- Không để result cache làm bằng chứng “secret mới hoạt động” trong khi mọi request thật vẫn dùng v1.

**Đừng tăng TTL vô hạn để che lỗi 401 từ introspection endpoint.** Đó là cách biến outage hoặc credential compromise thành rủi ro chấp nhận token đã bị thu hồi.

## 19. Giám sát rotation bằng tín hiệu an toàn

Những chỉ số cần theo dõi:

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| Introspection HTTP 2xx, 401/403, 429, 5xx | AS có chấp nhận client credentials không? |
| Introspection latency/timeouts | AS/network có đáp ứng SLA không? |
| `active=false` rate | Có sự thay đổi bất thường trong trạng thái token của caller không? |
| Credential version **identifier** theo instance | Instance nào còn chạy v1? |
| Số request được AS ghi nhận bằng v1/v2 | Đã đủ điều kiện thu hồi v1 chưa? |
| Cache hit/miss | Probe có thật sự chạm AS hay chỉ lấy cache? |
| API 401/403/5xx | Đang lỗi token/authorization hay hạ tầng introspection? |
| Số instance chưa rollout | Vùng/worker nào còn dùng secret cũ? |

Chỉ log **version ID không nhạy cảm** như `credential-generation=2026-11-B`, không log actual secret, hash đơn giản của secret, Basic Authorization header hay raw access token.

### 19.1. Không bật HTTP wire logging vô kiểm soát

Trong lúc debug, các HTTP client interceptors, reverse proxies hoặc APM agents có thể ghi:

- Header `Authorization: Basic ...` chứa credential Resource Server.
- Request body form chứa `token=...` là Bearer access token.
- JSON introspection response chứa subject, scope, email hoặc metadata nhạy cảm.

Phải có cơ chế **redaction ở mọi lớp** (HTTP client, proxy, tracing, diagnostics, error reporting). Không xuất các thông tin này lên dashboard công khai.

### 19.2. Sự khác biệt quan trọng khi phân tích log

```text
API trả 401 cho user request
    !=
AS trả HTTP 401 cho API introspection request
```

Hai sự kiện ở **hai hop HTTP khác nhau**. Nếu không phân biệt, đội vận hành có thể yêu cầu toàn bộ người dùng đăng nhập lại trong khi nguyên nhân là **secret của Resource Server đã hết hạn**.

## 20. Kiểm thử chiến lược luân chuyển

Một bộ test thực tế cần bao phủ **wire protocol**, **secret lifecycle** và **authorization behavior**.

### 20.1. Unit test wrapper fail-closed

Test một delegate throw exception:

```java
OpaqueTokenIntrospector failingDelegate = token -> {
    throw new OAuth2IntrospectionException(
            "Introspection service unavailable");
};

OpaqueTokenIntrospector guarded =
        new ResourceBindingIntrospector(
                failingDelegate, "orders-api");

assertThrows(OAuth2IntrospectionException.class,
        () -> guarded.introspect("test-token"));
```

Test minh họa rằng decorator **không tự trả principal** khi delegate thất bại. Không cần HTTP server cho bài test này. Tên exception/import cần khớp phiên bản Spring Security đang dùng.

### 20.2. HTTP protocol test với mock AS

Có thể dùng WireMock, MockWebServer hoặc test HTTP endpoint để xác minh:

1. Introspection request gửi **POST** tới URL tin cậy.
2. Có form parameter `token` bằng đúng token nhận từ caller.
3. Client authentication đúng dạng mà AS đã đăng ký.
4. Client ID/secret có ký tự đặc biệt được encode **đúng một lần**.
5. `active=true` tạo principal/authorities đúng.
6. `active=false` không tạo authentication.
7. HTTP 401 tại introspection endpoint được ghi là **client-auth failure**, không phải token revoke.
8. 5xx/timeout/TLS error **không làm ứng dụng fail-open**.
9. Logs/metrics không chứa secret và token.

### 20.3. Test rotation có overlap

Giả sử mock AS chấp nhận v1 và v2:

| Bước | AS chấp nhận | Resource Server dùng | Kỳ vọng |
| --- | --- | --- | --- |
| 1 | v1 | v1 | Introspection hoạt động |
| 2 | v1 và v2 | v1 | Hoạt động như trước |
| 3 | v1 và v2 | v2 ở một phần instance | Cả hai nhóm vẫn hoạt động |
| 4 | v1 và v2 | v2 ở tất cả instance | Probe real introspection đều pass |
| 5 | chỉ v2 | v2 ở tất cả instance | Hoạt động sau thu hồi v1 |
| 6 | chỉ v2 | cố tình dùng v1 trong negative test | AS từ chối credential cũ |

Test cần chứng minh **credential cũ thực sự không còn dùng được** sau thu hồi; việc ghi `v2` lên deployment manifest không đủ.

### 20.4. Test provider chỉ cho một secret

| Điều kiện | Kỳ vọng |
| --- | --- |
| AS đã đổi v1 → v2, instance còn v1 | Introspection client auth thất bại |
| AS dùng v2, instance đã cập nhật v2 | Introspection pass |
| Dùng registration blue-green v1 và v2 cùng được phép | Có thể rolling migration không gián đoạn |
| Blue-green v2 thiếu quyền introspect `orders-api` | Không coi v2 “đã sẵn sàng” chỉ vì HTTP Basic hợp lệ |

Với cutover không overlap, test phải giúp đội vận hành biết **điểm có thể gián đoạn** và các health gates cần đạt trước khi mở traffic.

### 20.5. Test đồng thời khi swap delegate

Nếu dùng `SwappableOpaqueTokenIntrospector`:

- Một request đã lấy delegate v1 vẫn có thể đang chạy khi v2 được activate.
- Request mới sau swap phải dùng v2.
- Không có thời điểm `current` là `null`.
- Rollback chỉ được phép khi credential cũ vẫn còn active và chưa nghi lộ.
- Test multi-instance/cluster cần chạy ở tầng orchestration; `AtomicReference` không tự đồng bộ giữa các JVM.

### 20.6. MockMvc qua filter chain thật

Ví dụ phác thảo:

```java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer active-read"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer active-no-scope"))
        .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer inactive"))
        .andExpect(status().isUnauthorized());
```

Các ví dụ giả định test introspection endpoint hoặc `OpaqueTokenIntrospector` fake đã được cấu hình phân loại ba giá trị token và controller thực sự trả 200 khi hợp lệ. Đây **không phải kết quả test đã chạy**.

Nếu dùng:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))));
```

thì `jwt()` của Spring Security Test có thể **bỏ qua introspection** bằng cách tạo sẵn Authentication giả lập. Loại test này hữu ích cho authorization, nhưng **không chứng minh secret/Basic client authentication, rotation hoặc `active` validation**.

## 21. Runbook triển khai: mẫu kiểm soát từng mốc

Một runbook rotation định kỳ có thể được chuẩn hóa như sau.

### Trước rollout

1. Xác nhận chủ sở hữu AS, credential registration, quyền introspection và môi trường liên quan.
2. Kiểm tra AS hỗ trợ overlap hay phải sử dụng hai client registrations.
3. Tạo credential mới, lưu secret manager version mới, giới hạn IAM/độc lập người phê duyệt.
4. Chuẩn bị deploy config/secret reference, đảm bảo client ID và secret đi **cùng bundle**.
5. Thiết lập dashboard cho AS client-auth failures, API 401/403/5xx và cache misses.
6. Chuẩn bị kiểm tra với một token thử nghiệm có quyền tối thiểu, qua **real introspection path**.

### Trong rollout

1. Bật v2 ở AS nhưng chưa thu hồi v1 nếu có overlap.
2. Triển khai canary instance sử dụng v2.
3. Kiểm tra AS ghi nhận v2, request active/inactive cho kết quả đúng, scope/audience không thay đổi.
4. Triển khai từng nhóm instance, quan sát cả các vùng DR/standby.
5. Chặn rollout nếu HTTP 401 từ AS, TLS error hoặc active metadata thay đổi bất thường.
6. Không chuyển sang fail-open hay tăng cache TTL vô hạn để che lỗi.

### Sau rollout

1. Chứng minh không còn traffic introspection hợp lệ bằng v1 trong cửa sổ theo dõi.
2. Thu hồi v1 ở AS.
3. Negative test v1 bị từ chối; positive test v2 tiếp tục hoạt động.
4. Xóa bản copy v1 trong runtime/secret store theo retention policy, rà soát CI/CD và tooling.
5. Lưu audit: thời điểm, credential **version identifier**, người/cơ chế phê duyệt, kết quả kiểm thử, incidents.
6. Cập nhật lịch rotation tiếp theo và cảnh báo trước ngày hết hạn.

### Điều kiện dừng / rollback

- **Rollback về v1** chỉ khi v1 **vẫn active và không bị nghi lộ**.
- Nếu v1 đã bị thu hồi vì sự cố, không được tái kích hoạt chỉ để phục hồi dịch vụ mà không qua phê duyệt an ninh.
- Nếu v2 chưa có quyền introspection đúng resource, **không thu hồi v1** trong quy trình định kỳ cho đến khi sửa xong và test pass.
- Nếu AS không hỗ trợ overlap, dùng kế hoạch cutover/blue-green/maintenance đã phê duyệt thay vì dựa vào rollback không chắc chắn.

## 22. Các anti-pattern cần tránh

### 22.1. Dùng chung một secret production trên nhiều môi trường

Dev/staging/prod cần trust boundary riêng. Một secret dùng chung làm lộ môi trường ít bảo vệ ảnh hưởng cả production. Tách client registration và quyền introspection theo môi trường khi AS hỗ trợ.

### 22.2. Hardcode hoặc commit secret vào source

Kể cả xóa commit sau đó, secret có thể còn trong Git history, build artifacts, logs hoặc cache CI. Nếu phát hiện lộ, cần **thu hồi và cấp mới**, không chỉ xóa dòng trong repository.

### 22.3. Giữ secret cũ vô thời hạn vì sợ downtime

Overlap chỉ là cửa sổ chuyển tiếp. Không có bước thu hồi cũ, rotation thực tế chưa hoàn tất và blast radius không giảm.

### 22.4. Đổi secret trong Vault rồi mặc định Spring bean tự cập nhật

Bean được dựng từ `@Value` thường giữ credential lúc khởi động. Cần restart/refresh/delegate swap có kiểm soát, không đoán cấu hình được reload.

### 22.5. Nhầm HTTP 401 của AS với Bearer token của người dùng sai

AS từ chối client credentials của Resource Server là sự cố của dịch vụ kiểm tra token. Phải phân loại đúng để sửa secret/registration/encoding và không yêu cầu mọi user refresh token vô ích.

### 22.6. Bỏ kiểm tra `active` để tránh phụ thuộc AS

Một HTTP 200 với `active=false` vẫn là token bị từ chối. Khi AS timeout, không có cơ sở tạo principal tin cậy.

### 22.7. Cho client gửi introspection URL tùy ý

Endpoint introspection chứa credential của Resource Server; chuyển URL theo input có thể gây SSRF và rò rỉ Basic credential. Cố định allowlist URL/tin cậy TLS.

### 22.8. Gửi credential cùng token của caller trong logs hoặc telemetry

Header Basic và body `token` đều nhạy cảm. Mask/redact tại HTTP client, reverse proxy và APM.

### 22.9. Chỉ test success mà không test secret đã hết hạn

Nếu test luôn mock `OAuth2AuthenticatedPrincipal`, nó bỏ qua HTTP client và không phát hiện encoding/rotation failure. Cần protocol tests với AS mock và negative tests.

### 22.10. Coi client_id trong introspection response là introspection client_id

`client_id` **trong response** thường chỉ OAuth client **được cấp access token**. Client ID dùng trong Basic để gọi introspection là một registration **khác** của Resource Server. Đừng dùng nhầm response client ID làm credential hoặc quyền của API.

### 22.11. Chấp nhận token active của resource khác

Nếu API là `orders-api`, token `aud=payments-api` không mặc nhiên hợp lệ chỉ vì AS trả active=true. Bảo đảm resource binding từ AS hoặc validator của API.

### 22.12. Dùng cùng quyền introspection cho mọi tenant

Một credential có thể xem token/metadata của các tenant khác nếu AS không giới hạn. Dùng least privilege, tenant isolation và phân quyền introspection thực sự thay vì chỉ đặt tên secret khác nhau.

## 23. Tình huống xử lý thực tế

### Tình huống A — API lỗi đồng loạt sau khi thay secret

Giả sử mọi request Bearer đều trả 401 trong khoảng vài phút sau khi AS rotate credential. Log AS cho thấy `invalid_client` hoặc Basic auth failure đối với `orders-introspector`. Khả năng cao là process còn dùng secret cũ hoặc gặp double-encoding. Kiểm tra secret version được nạp, bean lifecycle, phương thức encode và AS registration; **không tự kết luận user tokens hết hạn**.

### Tình huống B — Canary chạy được, production pods cũ bắt đầu lỗi

AS cho v1/v2 active, canary v2 pass. Operator thu hồi v1 quá sớm, trong khi một số pod chưa redeploy. Các pod đó tiếp tục dùng v1 và introspection fail. Cần giữ overlap cho đến khi xác nhận **toàn bộ instances** đã nhận v2. Nếu AS đã thu hồi v1, cần hoàn tất rollout hoặc áp dụng runbook rollback được phê duyệt.

### Tình huống C — AS không hỗ trợ nhiều secret

Tổ chức không thể rollout liên tục nếu regenerate secret lập tức vô hiệu v1. Giải pháp là đăng ký client introspection mới v2 với quyền tương đương nếu provider hỗ trợ; nếu không, lập maintenance/cutover có kiểm soát. Không hứa zero downtime chỉ nhờ Kubernetes rolling update.

### Tình huống D — Secret chứa ký tự đặc biệt

Client secret mới có ký tự `+` và `%`. Code cũ đã percent-encode trước, code builder mới lại tự encode. AS trả HTTP 401. Sử dụng **raw credentials** với builder hỗ trợ 6.5+ theo hợp đồng, test wire-level Basic authentication bằng mock endpoint. Không log header Basic.

### Tình huống E — AS timeout trong giờ cao điểm

Nhiều request đồng thời gọi introspection, AS vượt giới hạn hoặc TLS proxy lỗi. Không nên bắt exception rồi return principal mặc định. Cân nhắc timeout, bounded backoff, rate limiting, caching theo revocation SLA và circuit breaker an toàn.

### Tình huống F — Quyền của v2 khác v1

AS admin tạo một client registration mới để rotate secret nhưng quên cấp permission introspect token của `orders-api`. Basic authentication v2 thành công nhưng AS không trả metadata như trước. Cần kiểm tra **resource permissions**, response `active` và scope/audience trong canary; chỉ xác nhận migration thành công khi semantics tương đương.

### Tình huống G — mTLS cert tới hạn

Certificate Resource Server dùng để xác thực introspection sắp hết hạn. Rotation private key/cert cần được AS tin trước khi chuyển traffic, và HTTP client phải thực sự nạp keystore mới. Đừng nhầm certificate client auth với JWT public JWKS dùng xác minh access token.

### Tình huống H — Token của caller active nhưng thiếu scope

AS introspection trả `active=true`, `scope="orders:read"`. Client gọi endpoint yêu cầu `SCOPE_orders:write`. **Authentication thành công**, authorization từ chối (thường 403). Đổi introspection secret không cấp thêm scope cho token.

## 24. Câu hỏi tự kiểm tra

**1. Có mấy credential trong luồng Resource Server → AS introspection?** Ít nhất phải phân biệt Bearer token của caller và credential riêng xác thực Resource Server với endpoint introspection.

**2. HTTP 200 từ AS có bảo đảm token active không?** Không. Cần kiểm tra `active` trong response.

**3. Introspection client secret có phải JWT signing key của AS không?** Không. Chúng phục vụ những luồng xác thực khác nhau.

**4. Vì sao không lưu secret trực tiếp trong application.yml thuộc Git?** Có thể bị lộ qua source, history, artifacts và tooling; cần secret management, IAM và rotation.

**5. SpringOpaqueTokenIntrospector builder trong 6.5+ nhận secret raw hay percent-encoded?** Nhận **raw/unencoded**; builder xử lý encoding theo API version.

**6. Đổi secret trong secret manager thì Spring bean đã tạo lúc startup tự động dùng bản mới không?** Không mặc định; cần cơ chế refresh/redeploy/delegate swap được thiết kế.

**7. Khi AS chỉ cho một secret active, rolling update có mặc nhiên zero downtime không?** Không. Cần blue-green registration hoặc cutover được phối hợp; có thể phải chấp nhận maintenance window.

**8. Có nên giữ secret cũ active vô hạn để giảm rủi ro outage không?** Không. Cần thời hạn overlap và bước thu hồi.

**9. Khi nghi secret bị lộ, có nên ưu tiên availability bằng cách giữ v1?** Không. Quy trình ứng cứu cần giảm lạm dụng; có thể phải thu hồi v1 khẩn cấp.

**10. Introspection endpoint trả 401 có chứng minh Bearer token của user không hợp lệ không?** Không; nhiều khả năng là credential/quyền của Resource Server chưa đúng, cần phân biệt theo hop HTTP.

**11. Có thể cache active=true vô thời hạn để không cần gọi AS khi lỗi không?** Không; điều đó phá vỡ revocation/expiry semantics.

**12. Secret rotation có bắt buộc làm user đăng nhập lại không?** Không mặc định. Đổi credential nội bộ để introspect không đồng nghĩa đổi access token của caller.

**13. `client_id` trong introspection response có nhất thiết bằng client ID Resource Server dùng Basic không?** Không. Response có thể nêu OAuth client được cấp token, còn Basic dùng identity của Resource Server.

**14. Nếu dùng private_key_jwt, cần xoay loại khóa nào?** Private key ký client assertion và public key/JWKS đã đăng ký với AS, cùng policy `kid`/`jti`/`exp`.

**15. Vì sao test `MockMvc.jwt()` không đủ kiểm tra rotation?** Vì nó có thể tạo authentication giả lập, bỏ qua `OpaqueTokenIntrospector` và request client authentication tới AS.

## 25. Tài liệu và chuẩn để tìm hiểu thêm

- **RFC 7662 — OAuth 2.0 Token Introspection:** endpoint, `active`, quyền truy cập và response metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6749 — OAuth 2.0 Authorization Framework:** client authentication, confidential clients và các quy tắc `client_secret_basic`. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** truyền Bearer access token và các lỗi 401/403. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client auth bằng certificate. https://www.rfc-editor.org/rfc/rfc8705
- **RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants:** JWT client assertion. https://www.rfc-editor.org/rfc/rfc7523
- **Spring Security — Servlet OAuth 2.0 Resource Server Opaque Token:** cấu hình introspection, `OpaqueTokenIntrospector` và Spring implementation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Boot — OAuth2 Resource Server:** auto-configuration, properties `opaquetoken.*` và custom introspector bean. https://docs.spring.io/spring-boot/reference/security/oauth2.html
- **Spring Security — Migration to 7 (Opaque Token Credentials):** hướng thay đổi encoding client ID/secret khi nâng cấp. https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html

**Kết luận:** Credential dùng gọi introspection là **danh tính máy-máy của Resource Server trước Authorization Server**, không phải Bearer token của user. Bảo vệ credential bằng **TLS, least privilege, secret manager, logging redaction** và một quy trình rotation có thể kiểm chứng. Khi AS hỗ trợ overlap, triển khai secret mới trước rồi mới thu hồi bản cũ; nếu không hỗ trợ, dùng client registration blue-green hoặc cutover có kiểm soát. Với Spring Security, phải biết introspector bean được tạo từ phiên bản secret nào và cách client authentication được encode; khi có lỗi, phân biệt **token inactive**, **client authentication failure** và **AS/network unavailable**, luôn **fail-closed** thay vì chấp nhận access token chưa được kiểm tra.
