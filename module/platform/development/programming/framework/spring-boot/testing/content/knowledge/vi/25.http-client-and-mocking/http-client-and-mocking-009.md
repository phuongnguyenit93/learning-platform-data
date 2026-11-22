# Kiểm tra propagation của token, correlation ID và header cần thiết

Một ứng dụng Spring Boot có thể vừa nhận HTTP request từ client vừa gọi tiếp một HTTP service khác. Khi chuyển tiếp, ứng dụng thường phải truyền **Authorization token**, **correlation ID** và một số **header bắt buộc của downstream contract**. Nhưng **propagation không phải sao chép mọi header**: credential có audience và scope; correlation ID là metadata có thể bị giả mạo; proxy, cookie và hop-by-hop headers thường không phù hợp để chuyển sang downstream. Một dòng `outboundHeaders.addAll(inboundHeaders)` có thể khiến service gửi token nhầm host, leak session cookie hoặc tin nhầm tenant ID do client tự cung cấp.

Bài học thuộc phần **HTTP client và giả lập** của module **Spring Boot – testing**. Nó hướng dẫn phân biệt header nào phải truyền, tạo mới, xác thực, đổi tên, loại bỏ; cách kiểm việc truyền qua **controller → application context → RestClient → downstream**; cách viết positive/negative tests và khi nào cần network integration thay vì mocks. Ví dụ dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter 5, MockMvc, @RestClientTest và MockRestServiceServer**.

**Ranh giới bảo mật phải nói rõ:** Token trong ví dụ là token giả do test tạo; code demo chỉ kiểm **cú pháp Bearer và propagation**, **không** xác thực JWT signature, issuer, audience, expiry, scope hay authorization. Không triển khai nguyên mẫu gateway này ở production mà thiếu **Spring Security resource server/OAuth2 client** phù hợp. Khi production dùng token exchange hoặc service credentials, test propagation cần được giữ nhưng nguồn token phải thay bằng cơ chế bảo mật được phê duyệt.

## 1. Mục tiêu học tập

- Phân biệt **token relay**, **client credentials**, **token exchange**, **correlation ID**, **W3C trace context** và **HTTP headers contract**.
- Xác định đúng **trust boundary** giữa inbound, gateway/application và downstream service.
- Tạo allowlist các header được phép đi qua; không propagate session cookie, proxy credential hoặc header do caller giả mạo.
- Kiểm header `Authorization: Bearer ...` được tạo đúng, không nhân đôi chữ `Bearer` hoặc giữ token từ request trước.
- Kiểm correlation ID hợp lệ được giữ/canonicalize, vắng mặt thì được tạo, sai dạng thì bị từ chối theo policy.
- Kiểm một request-specific `X-Client-Channel` và `Accept: application/json` trên outbound client.
- Hiểu khác biệt giữa **MockMvc inbound** và **MockRestServiceServer outbound**, và vì sao cả hai không chứng minh network/TLS/redirect.
- Viết runnable Java 17+, Spring Boot 3.5 với một controller, policy, RestClient, DTO và ba lớp test.
- Thiết kế test âm tính cho missing token, invalid ID, cookie leak, untrusted host, 401/429/5xx, retry và concurrency.
- Tổ chức tracing/MDC/async context sao cho một user không dùng nhầm correlation ID hay token của user khác.
- Biết chọn test level ít tốn kém nhất nhưng vẫn quan sát được rủi ro cần bắt.

## 2. Sơ đồ truyền header

```text
Client
  |
  | GET /api/proxy/BOOK
  | Authorization: Bearer demo-user-token.123
  | X-Correlation-ID: 15cf0e17-83eb-42bc-a85f-0c70d7be1293
  | X-Client-Channel: WEB
  | Cookie: browser_session=...         <-- KHÔNG relay
  | X-Forwarded-For: attacker-input     <-- KHÔNG tin mù
  v
Spring MVC / security filter chain
  |
  +-- Authenticate/authorize (production requirement)
  +-- Header policy (validate/generate correlation)
  +-- RelayContext per invocation
  v
CatalogClient / RestClient
  |
  | GET /api/catalog/BOOK
  | Authorization: Bearer demo-user-token.123   <-- chỉ nếu trust/aud OK
  | X-Correlation-ID: 15cf0e17-...
  | X-Client-Channel: WEB
  | Accept: application/json
  | No Cookie / no Proxy-Authorization
  v
Trusted catalog downstream
  |
  v
Gateway response:
  | X-Correlation-ID: 15cf0e17-...
  | JSON CatalogItem body
  | No token, no downstream Set-Cookie
```

Bốn quyết định độc lập: **(1) nhận thông tin nào? (2) tin/validate thông tin nào? (3) chuyển đúng thông tin nào sang downstream? (4) trả header nào về client?** Cùng một tên header có thể có policy khác nhau ở chiều request và response.

## 3. Token relay, delegated access và service identity

| Cơ chế | Credential đến từ đâu | Được dùng khi nào? | Test phải quan sát gì? |
|---|---|---|---|
| **Token relay** | Credential inbound đã xác thực, phù hợp downstream | User delegation được phép | Token đúng, audience/scope, không rò host khác |
| **OAuth2 client_credentials** | Authorized client manager gọi token endpoint | Service tự gọi API với danh tính app | Chọn registration, scope, refresh/reuse đúng |
| **Token exchange / on-behalf-of** | Exchange inbound token lấy token audience mới | Token inbound không được dùng trực tiếp ở API B | Audience mới, identity delegation, expiry, exchange failure |
| **Anonymous downstream** | Không cần Authorization | Public endpoint | Không vô tình forward caller token |
| **mTLS/proof-of-possession** | Certificate/key hoặc sender-constrained token | High-security integration | TLS handshake, identity, không chỉ header text |

Đừng hiểu chữ `Authorization` như “đã xác thực”. Một HTTP request có dòng `Bearer abc` vẫn có thể giả mạo hoặc hết hạn. Khi dùng Spring Security resource server, phải xác minh token ở ingress và **bảo đảm downstream được phép nhận token đó**. Nếu user token chỉ có `aud=api-A`, không tự relay nó tới `api-B`. Nếu cần đại diện user cho API B, dùng một luồng ủy quyền/token exchange được hệ thống hỗ trợ, không sửa claims của JWT bằng tay.

### 3.1. RFC 6750 và Bearer grammar

Với header:

```http
Authorization: Bearer mF_9.B5f-4.1JqM
```

Scheme `Bearer` không phân biệt hoa/thường; Bearer token theo RFC 6750 thường gồm chữ, số, `- . _ ~ + /` và dấu `=` cuối. `HttpHeaders.setBearerAuth(token)` của Spring cần **chỉ phần token**, không phải toàn bộ `Bearer ...`.

Sai:

```java
// PHẢN VÍ DỤ: dễ thành "Bearer Bearer abc".
headers.setBearerAuth("Bearer abc");
```

Đúng:

```java
headers.setBearerAuth("abc");
```

Không đưa bearer credential vào URL query, application logs, tracing baggage, MDC hoặc exception text. **Bearer token phải được truyền trên HTTPS** khi đi qua network.

## 4. Correlation ID là metadata, không phải credential

Correlation ID thường là một UUID mà nhiều services cùng ghi vào log để xác định một luồng request:

```http
X-Correlation-ID: 15cf0e17-83eb-42bc-a85f-0c70d7be1293
```

Policy ví dụ:

1. Caller gửi UUID hợp lệ → normalize chữ thường.
2. Caller không gửi → tạo một UUID mới.
3. Caller gửi ID sai định dạng → HTTP 400, không gọi downstream.
4. Outbound dùng **chính giá trị đã quyết định**.
5. Gateway response trả client **cùng correlation ID**.
6. Khi retry cùng logical request, có thể dùng ID logic ổn định nếu policy định nghĩa như vậy.
7. ID không chứa PII, secret, control character, hoặc độ dài không giới hạn.

Correlation ID có thể do client tự gửi nên là **untrusted input** trước khi validate. Nó không chứng minh user, tenant, permission hoặc tính hợp lệ của token. Nếu hệ thống muốn **trả lại ID cả khi xử lý lỗi**, correlation filter/exception handler cần tạo ID **trước** controller và đảm bảo response error cũng mang ID; demo chính tập trung happy-path, lỗi validation được trả 400/401.

### 4.1. Không so UUID random bằng một UUID khác

Phản ví dụ:

```java
assertEquals(
        UUID.randomUUID().toString(),
        actualCorrelationId);
```

Đúng hơn:

```java
String returned = response.getHeader("X-Correlation-ID");
assertEquals(returned, UUID.fromString(returned).toString());
assertEquals(returned, capturedOutboundContext.correlationId());
```

Đây là snippet; `response` và `capturedOutboundContext` được lấy từ test setup, không phải biến định nghĩa trong file runnable.

## 5. W3C Trace Context không đồng nghĩa Correlation ID

Trace context có:

```http
traceparent: 00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01
tracestate: congo=t61rcWkgMzE
```

`traceparent` gồm version, trace-id, parent-id và flags. Khi một service tạo child span, **parent/span ID có thể thay đổi hợp lệ** giữa inbound/outbound; trace-id liên kết distributed trace vẫn liên tục. Vì vậy:

- Đừng copy nguyên `traceparent` trong custom RestClient interceptor khi đã dùng Micrometer Tracing/OpenTelemetry.
- Để tracing propagator quản lý `traceparent`, `tracestate` và baggage.
- Khi test trace continuity, assert các spans có đúng quan hệ parent/child, không chỉ so text của traceparent.
- Không đặt token hoặc dữ liệu người dùng nhạy cảm vào baggage.
- `X-Correlation-ID` là header nghiệp vụ/operations có thể cùng tồn tại, nhưng phải có một owner cho nó.

Nếu team dùng tracing và correlation ID riêng, cần tài liệu giải thích cách search log bằng từng ID. Không sinh ba IDs khác nhau ở gateway/filter/controller một cách vô thức.

## 6. Header matrix: truyền, tạo, lọc, không truyền

| Header | Hành vi đề xuất | Vì sao/test |
|---|---|---|
| `Authorization` | Chỉ relay nếu token hợp lệ, audience/scope/trust phù hợp | Security boundary |
| `X-Correlation-ID` | Validate hoặc generate rồi dùng nhất quán | Log liên service |
| `traceparent`, `tracestate` | Tracing instrumentation quản lý | Parent/span semantics |
| `Accept` | Set theo downstream contract | GET JSON: `application/json` |
| `Content-Type` | Set theo outbound body | GET không cần copy Content-Type của inbound |
| `X-Client-Channel` | Allowlist nếu downstream yêu cầu | Không tin giá trị tùy ý |
| `Idempotency-Key` | Chỉ truyền với mutation/retry contract | Chống double side effect |
| `X-API-Version` | Adapter set theo API version | Không mù quáng dùng version caller gửi |
| `Cookie` | Không relay theo mặc định | Browser session không thuộc downstream |
| `Proxy-Authorization` | Không relay | Credential proxy nhạy cảm |
| `Forwarded`/`X-Forwarded-*` | Chỉ trusted proxy chain xử lý | Client có thể forge |
| `Host`, `Content-Length` | Để HTTP client/transport tạo | Mỗi hop có host/body khác |
| `Connection`, `Transfer-Encoding` | Hop-by-hop, không copy | HTTP framing/connection-specific |
| `Origin`, `Referer` | Không mặc định forward | Browser/CORS context |
| `Set-Cookie` ở response | Không copy tự động về caller | Cookie scope/domain leak |
| `Location` ở response | Map theo public API contract | Có thể lộ internal host |

**Mỗi downstream nên có một allowlist riêng.** “Tất cả headers except Cookie” vẫn là policy quá rộng. Không dùng `headers.addAll(inboundHeaders)` rồi cố lọc một vài field mà quên các field mới có thể xuất hiện sau này.

## 7. Những header của identity dễ bị spoof

Các header `X-User-ID`, `X-Tenant-ID`, `X-Role` hoặc `X-Forwarded-User` nghe như chứa thông tin xác thực, nhưng caller bên ngoài có thể tự gửi chúng. Nếu code dùng chúng trực tiếp để lấy dữ liệu, đó có thể là **privilege escalation**.

Thay vì:

```java
// PHẢN VÍ DỤ: tin user identity do caller tự khai báo.
String tenant = servletRequest.getHeader("X-Tenant-ID");
queryInvoicesFor(tenant);
```

hãy lấy identity/tenant từ **SecurityContext đã xác thực**, hoặc từ một header do trusted gateway ký/chèn trong một mạng có bảo vệ và client external không thể giả mạo. Test phải thử caller tự gửi tenant/role khác và xác minh policy từ chối hoặc bỏ qua.

Trong demo, `X-Client-Channel` chỉ là **metadata kênh** để downstream thống kê/format, không phải quyền người dùng. `PARTNER` trong allowlist cũng **không** chứng minh client là đối tác đã xác thực.

## 8. Inbound và outbound response headers phải có allowlist khác nhau

Khi gateway nhận downstream response:

- Body JSON có thể được deserialize thành DTO rồi serialize lại theo public API.
- `Set-Cookie` của downstream không tự động thuộc quyền cookie domain của gateway.
- `WWW-Authenticate` của downstream có thể lộ internal realm/client IDs.
- `Location` có thể là URL nội bộ không muốn public.
- `Content-Length` có thể sai nếu body được transform.
- `X-Correlation-ID` có thể dùng ID do gateway đã quyết định, không tin response downstream tự đổi ID.

Vì vậy bài ví dụ chỉ phản hồi **JSON CatalogItem** và `X-Correlation-ID`. Không chuyển Authorization hay Set-Cookie về browser. Cần test response header negative cases nếu gateway từng proxy thẳng `ResponseEntity` của downstream.

## 9. Chọn test theo boundary, không theo tên annotation

| Test | Công cụ | Chạy TCP thật? | Có thể phát hiện |
|---|---|---:|---|
| Pure policy | JUnit Jupiter | Không | Missing token, invalid UUID, channel allowlist |
| Inbound MVC | `@WebMvcTest` + `MockMvc` | Không | Header-to-context, response header, 400/401, zero client calls |
| Outbound client | `@RestClientTest` + `MockRestServiceServer` | Không | Exact URL/method/headers, omitted headers, token bleed |
| Wire-level HTTP | WireMock/MockWebServer | Có | Redirect, proxy, TLS, HTTP client framing/timeout |
| Full app | `@SpringBootTest(RANDOM_PORT)` + trusted stub | Có | Security filter, controller, service, client, real server |
| Partner sandbox | Controlled remote endpoint | Có | Actual identity/TLS/gateway/rate-limit contract |

`MockMvc` không mở HTTP socket; `MockRestServiceServer` thay request factory của client bằng mock. Đừng gọi chúng là real network integration. Nhưng chúng thường là **cấp test rẻ nhất** để bắt header bị quên/thêm nhầm; thêm một số real HTTP tests khi rủi ro nằm ở transport.

## 10. `@RestClientTest` và `MockRestServiceServer`

Spring Boot 3.5 hỗ trợ:

```java
@RestClientTest(CatalogClient.class)
class CatalogClientHeaderTest {

    @Autowired CatalogClient client;
    @Autowired MockRestServiceServer server;
}
```

Test slice auto-configure `RestClient.Builder` và mock REST server. Bean `CatalogClient` thật chạy logic dựng outbound request; khi nó gọi `RestClient`, mock server bắt request và trả response stub.

`MockRestServiceServer` có thể assert:

- URL, HTTP method, query params.
- `Authorization`, `X-Correlation-ID`, channel, `Accept`.
- Header vắng mặt bằng custom `RequestMatcher`.
- Request count/order và response status/body.
- Nếu request không xảy ra, `server.verify()` phải fail.

Spring Framework lưu ý: khi cần kiểm **transport thực tế**, mock web server có khả năng tốt hơn, vì MockRestServiceServer không mô phỏng network library/proxy/redirect. Tách hai mục đích đó ra giúp test không tạo confidence giả.

## 11. `RestClient` phải dùng header theo request

Một RestClient có thể là singleton do Spring inject:

```java
@Bean
RestClient downstream(RestClient.Builder builder) {
    return builder.baseUrl("https://trusted-api.internal")
            .build();
}
```

Không làm:

```java
// PHẢN VÍ DỤ: token user A giữ trong singleton shared client.
return builder.defaultHeader(
        HttpHeaders.AUTHORIZATION, "Bearer token-user-A")
        .build();
```

Nếu user B dùng cùng client, credential A có thể xuất hiện ở request B. Dùng request spec:

```java
client.get()
        .uri("/api/items/{id}", id)
        .headers(h -> {
            h.setBearerAuth(context.accessToken());
            h.set("X-Correlation-ID", context.correlationId());
        })
        .retrieve()
        .body(Item.class);
```

Đây là snippet với `Item`/`context` giả định. Truyền context qua method parameters giúp tránh singleton mutable field/ThreadLocal. Nếu có interceptor cho tracing/OAuth2, phải xác định rõ nó có ghi đè các header này không.

## 12. Spring Security/OAuth2 production integration

Spring Security 6.5 cung cấp `OAuth2ClientHttpRequestInterceptor` dùng `OAuth2AuthorizedClientManager` cho `RestClient`. Ví dụ:

```java
// Snippet; yêu cầu spring-security-oauth2-client,
// OAuth2AuthorizedClientManager và client registration.
OAuth2ClientHttpRequestInterceptor interceptor =
        new OAuth2ClientHttpRequestInterceptor(manager);

RestClient protectedClient = RestClient.builder()
        .requestInterceptor(interceptor)
        .baseUrl("https://trusted-api.internal")
        .build();
```

Nó có thể lấy token, dùng authorized client và refresh khi cần; phải cấu hình principal/clientRegistrationId resolver phù hợp, nhất là với `client_credentials` (scope ứng dụng thay vì từng user). Không đồng thời set Bearer theo tay **và** bằng OAuth2 interceptor nếu chưa có chính sách precedence và test xác nhận request cuối.

Nếu API A là resource server nhận JWT, phải xác thực **issuer, signature, expiration, audience và scopes** qua Spring Security trước khi quyết định relay. Một token inbound dành cho API A không tự nhiên hợp lệ cho API B. Token exchange hoặc service credentials là giải pháp tùy kiến trúc.

## 13. Ví dụ runnable: yêu cầu của ứng dụng demo

- Inbound endpoint: `GET /api/proxy/{sku}`.
- Downstream cố định: `{demo.catalog.base-url}/api/catalog/{sku}`.
- Header bắt buộc: `Authorization: Bearer ...` và `X-Client-Channel` thuộc tập `WEB`, `MOBILE`, `PARTNER`.
- Correlation ID: UUID dạng `8-4-4-4-12`, giữ nếu hợp lệ; nếu thiếu generate.
- Outbound: Bearer, correlation, client channel, `Accept: application/json`.
- Outbound **không** có browser Cookie/Proxy-Authorization/X-Forwarded-For.
- Response: JSON `CatalogItem(sku,title)` và `X-Correlation-ID`, không phản hồi token.
- Path sku: chữ hoa/số/dấu gạch nối để ngăn malformed URL.
- Test token giả, host `catalog.example.test`; không thực hiện outbound network.

### 13.1. Cây source files

```text
header-propagation-demo/
  settings.gradle
  build.gradle
  src/main/java/com/example/headerprop/
    HeaderPropagationApplication.java
    RelayContext.java
    HeaderRelayPolicy.java
    CatalogItem.java
    CatalogClient.java
    ProxyController.java
  src/test/java/com/example/headerprop/
    HeaderRelayPolicyTest.java
    ProxyControllerTest.java
    CatalogClientHeaderTest.java
```

Ba nhóm tests:

1. `HeaderRelayPolicyTest`: Pure JUnit policy.
2. `ProxyControllerTest`: `@WebMvcTest` + Mockito mock CatalogClient.
3. `CatalogClientHeaderTest`: `@RestClientTest` + MockRestServiceServer với CatalogClient thật.

Các file từ mục 14–21 được viết đầy đủ; code blocks có nhãn “snippet” ở mục khác không phải file runnable độc lập.

## 14. Gradle files

**`settings.gradle`**

```groovy
rootProject.name = 'header-propagation-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` mang MVC/RestClient/Jackson, starter-test mang JUnit/Mockito/Spring Test. Không cần Docker, real API token, Redis hoặc OAuth server để chạy các mocks. **Đây là bài testing về propagation**, không phải reference security deployment: production phải bổ sung security dependencies và policy riêng.

## 15. Application và request-scoped context

**`src/main/java/com/example/headerprop/HeaderPropagationApplication.java`**

```java
package com.example.headerprop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HeaderPropagationApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderPropagationApplication.class, args);
    }
}
```

**`src/main/java/com/example/headerprop/RelayContext.java`**

```java
package com.example.headerprop;

public record RelayContext(
        String accessToken,
        String correlationId,
        String clientChannel) {
}
```

Context này là object **mới theo request**, không giữ trong singleton. Đừng log record vì `toString()` mặc định có thể chứa token. Trong production có thể tách token thành security-specific type được redact hoặc đưa vào authorized-client mechanism.

## 16. Header policy: parsing và kiểm dữ liệu đầu vào

**`src/main/java/com/example/headerprop/HeaderRelayPolicy.java`**

```java
package com.example.headerprop;

import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class HeaderRelayPolicy {

    private static final Pattern BEARER_TOKEN =
            Pattern.compile("^[A-Za-z0-9._~+/-]+=*$");

    private static final Pattern STRICT_UUID = Pattern.compile(
            "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" +
            "[0-9a-fA-F]{12}$");

    private static final Set<String> CHANNELS =
            Set.of("WEB", "MOBILE", "PARTNER");

    private HeaderRelayPolicy() {
    }

    public static RelayContext fromInbound(
            String authorization,
            String correlationId,
            String clientChannel) {

        String token = parseBearer(authorization);
        String correlation = normalizeCorrelation(correlationId);
        String channel = requireChannel(clientChannel);

        return new RelayContext(token, correlation, channel);
    }

    static String parseBearer(String authorization) {
        if (authorization == null
                || authorization.length() > 8192
                || !authorization.regionMatches(
                        true, 0, "Bearer ", 0, 7)) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "Bearer credentials required");
        }

        String token = authorization.substring(7);
        if (token.isEmpty()
                || !BEARER_TOKEN.matcher(token).matches()) {
            throw new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED,
                    "Invalid Bearer credential format");
        }

        return token;
    }

    static String normalizeCorrelation(String incoming) {
        if (incoming == null || incoming.isBlank()) {
            return UUID.randomUUID().toString();
        }

        if (incoming.length() != 36
                || !STRICT_UUID.matcher(incoming).matches()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid X-Correlation-ID");
        }

        return UUID.fromString(incoming).toString();
    }

    static String requireChannel(String incoming) {
        if (incoming == null || !CHANNELS.contains(incoming)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid X-Client-Channel");
        }
        return incoming;
    }
}
```

**Phạm vi chính xác:**

- Token parser chỉ kiểm **format**; nó **không xác thực** bất cứ credential thật nào.
- `Bearer` scheme được chấp nhận không phân biệt hoa/thường.
- Parser cố ý yêu cầu đúng **một ASCII space** sau scheme; RFC 6750 cho phép `1*SP`, nên demo chặt hơn chuẩn. Nếu cần đầy đủ protocol syntax, cập nhật parser/tests.
- 8192 là giới hạn **ví dụ** để tránh header quá dài, không phải con số bắt buộc của RFC.
- UUID chuẩn hóa lowercase; invalid ID bị 400; value null/blank được generate.
- `X-Client-Channel` là allowlist metadata, **không phải** xác minh đối tác.
- Không đưa raw token hoặc input độc hại vào error message.

## 17. DTO và HTTP client

**`src/main/java/com/example/headerprop/CatalogItem.java`**

```java
package com.example.headerprop;

public record CatalogItem(String sku, String title) {
}
```

**`src/main/java/com/example/headerprop/CatalogClient.java`**

```java
package com.example.headerprop;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogClient {

    private final RestClient client;

    public CatalogClient(
            RestClient.Builder builder,
            @Value("${demo.catalog.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public CatalogItem fetch(String sku, RelayContext context) {
        CatalogItem item = client.get()
                .uri("/api/catalog/{sku}", sku)
                .accept(MediaType.APPLICATION_JSON)
                .headers(headers -> {
                    headers.setBearerAuth(context.accessToken());
                    headers.set(
                            "X-Correlation-ID",
                            context.correlationId());
                    headers.set(
                            "X-Client-Channel",
                            context.clientChannel());
                })
                .retrieve()
                .body(CatalogItem.class);

        if (item == null) {
            throw new IllegalStateException(
                    "Catalog returned empty JSON body");
        }
        return item;
    }
}
```

RestClient có `baseUrl` từ cấu hình service, **không nhận URL từ user**. Khi test dùng `http://catalog.example.test`, MockRestServiceServer chặn request trong JVM nên không thực hiện TLS/network. Khi production, downstream base URL phải là trusted HTTPS origin, không phải arbitrary callback URL; phải có redirect policy chống cross-origin token leakage. Method `fetch` chỉ truyền headers từ `RelayContext`; nó không có access vào toàn bộ inbound HttpHeaders.

## 18. Controller inbound → outbound context

**`src/main/java/com/example/headerprop/ProxyController.java`**

```java
package com.example.headerprop;

import java.util.regex.Pattern;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/proxy")
public class ProxyController {

    private static final Pattern SKU =
            Pattern.compile("^[A-Z0-9-]{1,40}$");

    private final CatalogClient catalog;

    public ProxyController(CatalogClient catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            path = "/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CatalogItem> get(
            @PathVariable String sku,
            @RequestHeader(
                    name = HttpHeaders.AUTHORIZATION,
                    required = false) String authorization,
            @RequestHeader(
                    name = "X-Correlation-ID",
                    required = false) String correlationId,
            @RequestHeader(
                    name = "X-Client-Channel",
                    required = false) String clientChannel) {

        if (!SKU.matcher(sku).matches()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid sku");
        }

        RelayContext context = HeaderRelayPolicy.fromInbound(
                authorization, correlationId, clientChannel);

        CatalogItem item = catalog.fetch(sku, context);

        return ResponseEntity.ok()
                .header(
                        "X-Correlation-ID",
                        context.correlationId())
                .body(item);
    }
}
```

Chỉ có ba inbound header values được chọn cho request context. `Cookie` và `X-Forwarded-For` không được đọc/truyền, giảm khả năng đi qua trust boundary sai. Không trả Authorization trong body/response header. Lưu ý demo kiểm SKU trước policy; một production security filter nên xử lý authentication trước controller để tránh unauthorized callers nhận những thông tin không cần thiết.

## 19. Pure JUnit: kiểm parsing và policy

**`src/test/java/com/example/headerprop/HeaderRelayPolicyTest.java`**

```java
package com.example.headerprop;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HeaderRelayPolicyTest {

    private static final String ID =
            "15cf0e17-83eb-42bc-a85f-0c70d7be1293";

    @Test
    void retainsValidHeaders() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "Bearer demo-user-token.123", ID, "WEB");

        assertEquals("demo-user-token.123", c.accessToken());
        assertEquals(ID, c.correlationId());
        assertEquals("WEB", c.clientChannel());
    }

    @Test
    void bearerSchemeIsCaseInsensitive() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "bearer token-for-test", ID, "MOBILE");

        assertEquals("token-for-test", c.accessToken());
    }

    @Test
    void createsIdWhenMissing() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "Bearer token-for-test", null, "PARTNER");

        assertNotNull(c.correlationId());
        assertEquals(
                c.correlationId(),
                UUID.fromString(c.correlationId()).toString());
    }

    @Test
    void canonicalizesUppercaseUuid() {
        RelayContext c = HeaderRelayPolicy.fromInbound(
                "Bearer token-for-test",
                ID.toUpperCase(), "WEB");

        assertEquals(ID, c.correlationId());
    }

    @Test
    void rejectsMissingBearer() {
        ResponseStatusException ex = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        null, ID, "WEB"));

        assertEquals(
                HttpStatus.UNAUTHORIZED, ex.getStatusCode());
    }

    @Test
    void rejectsInvalidCorrelationAndChannel() {
        ResponseStatusException badId = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        "Bearer token-for-test",
                        "not-a-uuid", "WEB"));

        assertEquals(
                HttpStatus.BAD_REQUEST, badId.getStatusCode());

        ResponseStatusException badChannel = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        "Bearer token-for-test",
                        ID, "UNTRUSTED"));

        assertEquals(
                HttpStatus.BAD_REQUEST,
                badChannel.getStatusCode());
    }

    @Test
    void rejectsInjectedCredentialText() {
        ResponseStatusException ex = assertThrows(
                ResponseStatusException.class,
                () -> HeaderRelayPolicy.fromInbound(
                        "Bearer abc\r\nX-Injected: yes",
                        ID, "WEB"));

        assertEquals(
                HttpStatus.UNAUTHORIZED, ex.getStatusCode());
    }
}
```

Bộ test có **7 methods**. Bài kiểm chuỗi CRLF chạy ở tầng Java policy; trong actual servlet, server/proxy cũng có thể chặn CRLF hoặc header invalid trước controller. Đừng bắt buộc test HTTP thực phải chuyển được malicious header qua lớp framing của container để kiểm policy; có thể test lower layer riêng.

## 20. `@WebMvcTest`: kiểm controller nhận/biến đổi header

**`src/test/java/com/example/headerprop/ProxyControllerTest.java`**

```java
package com.example.headerprop;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProxyController.class)
class ProxyControllerTest {

    private static final String ID =
            "15cf0e17-83eb-42bc-a85f-0c70d7be1293";

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogClient catalog;

    @Test
    void forwardsValidatedContextAndReturnsSameId()
            throws Exception {

        RelayContext expected = new RelayContext(
                "demo-user-token.123", ID, "WEB");

        when(catalog.fetch("BOOK", expected))
                .thenReturn(new CatalogItem(
                        "BOOK", "Spring Boot"));

        mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer demo-user-token.123")
                        .header("X-Correlation-ID", ID)
                        .header("X-Client-Channel", "WEB"))
                .andExpectAll(
                        status().isOk(),
                        header().string("X-Correlation-ID", ID),
                        jsonPath("$.sku").value("BOOK"),
                        jsonPath("$.title").value("Spring Boot"));

        verify(catalog).fetch("BOOK", expected);
    }

    @Test
    void generatesIdThenReturnsExactlyThePassedId()
            throws Exception {

        when(catalog.fetch(eq("BOOK"), any(RelayContext.class)))
                .thenReturn(new CatalogItem(
                        "BOOK", "Spring Boot"));

        MvcResult result = mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Client-Channel", "WEB"))
                .andExpectAll(
                        status().isOk(),
                        header().exists("X-Correlation-ID"))
                .andReturn();

        ArgumentCaptor<RelayContext> captor =
                ArgumentCaptor.forClass(RelayContext.class);
        verify(catalog).fetch(eq("BOOK"), captor.capture());

        String actual = result.getResponse()
                .getHeader("X-Correlation-ID");
        assertEquals(actual, captor.getValue().correlationId());
        assertEquals(actual, UUID.fromString(actual).toString());
    }

    @Test
    void missingTokenNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/BOOK")
                        .header("X-Correlation-ID", ID)
                        .header("X-Client-Channel", "WEB"))
                .andExpect(status().isUnauthorized());

        verifyNoInteractions(catalog);
    }

    @Test
    void missingChannelNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Correlation-ID", ID))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }

    @Test
    void invalidCorrelationNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/BOOK")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Correlation-ID", "bad-id")
                        .header("X-Client-Channel", "WEB"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }

    @Test
    void invalidSkuNeverCallsCatalog() throws Exception {
        mvc.perform(get("/api/proxy/book")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer token-for-test")
                        .header("X-Client-Channel", "WEB"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(catalog);
    }
}
```

Bộ test có **6 methods**. Nó chạy controller và policy thật nhưng `CatalogClient` là Mockito mock. Vì vậy kết quả chứng minh **inbound header → RelayContext → adapter method invocation** và status/response header, **không** chứng minh RestClient đã đặt Authorization trên outbound HTTP request. Bài test `@RestClientTest` dưới đây kiểm ranh giới tiếp theo.

## 21. `@RestClientTest`: kiểm request cuối cùng của client

**`src/test/java/com/example/headerprop/CatalogClientHeaderTest.java`**

```java
package com.example.headerprop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.client.MockRestServiceServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

@RestClientTest(CatalogClient.class)
@TestPropertySource(properties =
        "demo.catalog.base-url=http://catalog.example.test")
class CatalogClientHeaderTest {

    private static final String BASE =
            "http://catalog.example.test";

    private static final String ID =
            "15cf0e17-83eb-42bc-a85f-0c70d7be1293";

    @Autowired
    CatalogClient catalog;

    @Autowired
    MockRestServiceServer server;

    @Test
    void setsRequiredHeadersAndBlocksUnnecessaryOnes() {
        server.expect(requestTo(BASE + "/api/catalog/BOOK"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer demo-user-token.123"))
                .andExpect(header("X-Correlation-ID", ID))
                .andExpect(header("X-Client-Channel", "WEB"))
                .andExpect(header(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE))
                .andExpect(request -> {
                    HttpHeaders actual = request.getHeaders();
                    assertFalse(actual.containsKey(HttpHeaders.COOKIE));
                    assertFalse(actual.containsKey(
                            "Proxy-Authorization"));
                    assertFalse(actual.containsKey(
                            "X-Forwarded-For"));
                })
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"title\":\"Java 17\"}",
                        MediaType.APPLICATION_JSON));

        CatalogItem item = catalog.fetch("BOOK",
                new RelayContext(
                        "demo-user-token.123", ID, "WEB"));

        assertEquals("BOOK", item.sku());
        assertEquals("Java 17", item.title());
        server.verify();
    }

    @Test
    void secondInvocationDoesNotInheritFirstUsersToken() {
        server.expect(requestTo(BASE + "/api/catalog/BOOK"))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer token-user-A"))
                .andExpect(header(
                        "X-Correlation-ID",
                        "11111111-1111-4111-8111-111111111111"))
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"title\":\"A\"}",
                        MediaType.APPLICATION_JSON));

        server.expect(requestTo(BASE + "/api/catalog/PEN"))
                .andExpect(header(
                        HttpHeaders.AUTHORIZATION,
                        "Bearer token-user-B"))
                .andExpect(header(
                        "X-Correlation-ID",
                        "22222222-2222-4222-8222-222222222222"))
                .andRespond(withSuccess(
                        "{\"sku\":\"PEN\",\"title\":\"B\"}",
                        MediaType.APPLICATION_JSON));

        CatalogItem first = catalog.fetch("BOOK",
                new RelayContext(
                        "token-user-A",
                        "11111111-1111-4111-8111-111111111111",
                        "WEB"));

        CatalogItem second = catalog.fetch("PEN",
                new RelayContext(
                        "token-user-B",
                        "22222222-2222-4222-8222-222222222222",
                        "MOBILE"));

        assertEquals("A", first.title());
        assertEquals("B", second.title());
        server.verify();
    }

    @Test
    void usesOnlyConfiguredDownstreamBaseUrl() {
        server.expect(requestTo(BASE + "/api/catalog/BOOK"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        "{\"sku\":\"BOOK\",\"title\":\"Safe\"}",
                        MediaType.APPLICATION_JSON));

        CatalogItem item = catalog.fetch("BOOK",
                new RelayContext("token-for-test", ID, "WEB"));

        assertEquals("Safe", item.title());
        server.verify();
    }
}
```

Bộ test có **3 methods**, mỗi method gọi `server.verify()`. Nếu client không gửi request dự kiến, verify phải fail. Khi set đúng RestClient.Builder của slice, mock server thay request factory và không mở socket. `@RestClientTest` có thể reset mock server expectations giữa test methods; nếu một project tự bind mock server hoặc dùng static client, phải reset có chủ đích.

### 21.1. Kiểm header vắng mặt cũng quan trọng như header hiện diện

`header("Authorization", "...")` phát hiện thiếu/sai token. Nhưng một request vẫn có thể đồng thời mang `Cookie` hoặc `Proxy-Authorization` từ một interceptor khác. Vì vậy custom matcher:

```java
.andExpect(request ->
        assertFalse(request.getHeaders()
                .containsKey(HttpHeaders.COOKIE)))
```

là cần thiết khi policy yêu cầu cookie không được gửi. Nếu app dùng OAuth2 interceptor, verify request **sau khi interceptor xử lý**. Không chỉ assert một DTO response thành công rồi coi header secure.

## 22. Lệnh chạy và kết quả kỳ vọng

Từ Gradle project có wrapper:

```bash
./gradlew test --tests com.example.headerprop.HeaderRelayPolicyTest --tests com.example.headerprop.ProxyControllerTest --tests com.example.headerprop.CatalogClientHeaderTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests com.example.headerprop.HeaderRelayPolicyTest --tests com.example.headerprop.ProxyControllerTest --tests com.example.headerprop.CatalogClientHeaderTest
```

| Class | Số methods | Ranh giới |
|---|---:|---|
| `HeaderRelayPolicyTest` | 7 | Parse/validation thuần Java |
| `ProxyControllerTest` | 6 | Inbound/controller/HTTP error, CatalogClient mocked |
| `CatalogClientHeaderTest` | 3 | Outbound RestClient thật, mock response factory |
| **Tổng** | **16** | Header propagation theo từng ranh giới |

**Kết quả dự kiến:** Với Java 17, Spring Boot 3.5.x và build dependencies đúng, tests dự kiến pass. Chưa có Gradle wrapper trong code block; nếu project mới, cần dùng Gradle/IDE để tạo wrapper theo convention. Không có stdout business cố định. JUnit report thường ở `build/reports/tests/test/index.html`. **Các ví dụ được rà soát ở mức mã nguồn nhưng chưa chạy Gradle trong repository thực tế**.

## 23. MockMvc và MockRestServiceServer vẫn để hở những gì?

Dù cả hai nhóm test pass:

- Chưa kiểm HTTP/TLS handshake, socket timeouts hay proxy.
- Chưa kiểm redirect cross-origin làm rò Bearer.
- Chưa kiểm JWT signature, issuer, expiry, `aud` và scopes.
- Chưa kiểm gateway chặn duplicate Authorization/header smuggling.
- Chưa kiểm Spring Security filter chain (demo không cấu hình).
- Chưa kiểm Micrometer Tracing tạo span đúng.
- Chưa kiểm Reactor Context/@Async propagation.
- Chưa kiểm downstream failure mapping trong controller.
- Chưa kiểm concurrency dưới nhiều users khi security context phải được propagate.

**Đó là giới hạn có chủ đích**, không phải “test thiếu toàn diện”: mỗi cấp test có mục tiêu riêng. Bổ sung real mock-server tests và security integration khi risk register nói những boundary đó quan trọng.

## 24. Tại sao không dùng `headers.addAll(inboundHeaders)`?

```java
// PHẢN VÍ DỤ: chuyển mọi thông tin do browser cung cấp.
client.get().uri("/resource")
        .headers(out -> out.addAll(inboundHeaders))
        .retrieve().body(String.class);
```

Nó có thể chuyển:

- `Authorization` chưa được validate hoặc không đúng audience.
- Cookie chứa session/browser state.
- `Proxy-Authorization` của proxy.
- `Host` hoặc `X-Forwarded-Host` khiến confused routing.
- `X-User-ID` do client forge.
- `Content-Length` không đúng body mới.
- `Connection`/`Transfer-Encoding` chỉ có nghĩa từng hop.
- Headers tùy biến không tồn tại trong allowlist hôm nay nhưng được thêm ngày mai.

Thay bằng:

```java
// Snippet: context đến từ verified security/policy boundary.
client.get().uri("/resource")
        .headers(h -> {
            h.setBearerAuth(context.accessToken());
            h.set("X-Correlation-ID", context.correlationId());
            h.set("X-Client-Channel", context.clientChannel());
            h.setAccept(List.of(MediaType.APPLICATION_JSON));
        })
        .retrieve().body(String.class);
```

Đây là snippet; code runnable `CatalogClient` đã chọn allowlist phù hợp mà không cần `inboundHeaders`. Trong production, có thể thay Bearer source bằng OAuth2 interceptor thay vì set thủ công.

## 25. Headers có nhiều giá trị và normalization

HTTP có thể có repeated header fields; nhiều servers/proxies có thể hợp nhất chúng theo quy tắc khác nhau. `Authorization`, forwarded identity và host là những nơi đặc biệt nhạy. Nếu client gửi hai Authorization values, không được chọn tùy tiện một giá trị mà trust gateway chọn khác.

Ở ingress/security filter, có thể kiểm:

```java
// Snippet servlet filter:
List<String> values =
        Collections.list(
                request.getHeaders(HttpHeaders.AUTHORIZATION));

if (values.size() != 1) {
    throw new BadCredentialsException(
            "Expected one Authorization value");
}
```

Với project production cần imports và framework error handling. Test duplicate headers có thể cần run qua proxy/server thật vì MockMvc có parsing khác. Đừng dựa vào case-sensitivity của tên HTTP headers: `authorization` và `Authorization` là cùng semantic header field.

### 25.1. Header injection và giới hạn độ dài

Correlation ID quá dài, chứa `\r`/`\n`, Unicode control, whitespace hoặc ký tự không nằm trong contract có thể phá logs/headers. Validate ở boundary và cấu hình max header size tại gateway/server. Test cả policy và wire-level nếu request smuggling là rủi ro; servlet container có thể từ chối malformed header trước khi controller chạy.

## 26. Context propagation trong async và reactive code

Trong synchronous servlet path, bạn có thể đọc Spring SecurityContext/MDC ở request thread. Nhưng với `@Async`, `CompletableFuture`, scheduled jobs hoặc Reactive `WebClient`:

- ThreadLocal không tự đi theo mọi thread switch.
- Một thread pool có thể reuse threads giữa users.
- Không copy SecurityContext chứa credential sang background job mà không có policy/TTL.
- Reactor Context/Security ReactiveSecurityContextHolder cần được dùng đúng khi chạy reactive.
- Correlation/tracing context phải được propagate và cleanup qua task boundary.
- Không dùng `static String currentToken` hoặc singleton field giữ user token.

**Test hữu ích:** gọi gần đồng thời hai users A/B, downstream mock capture headers của từng call, assert không request nào dùng nhầm token/correlation của user kia. Một test lần lượt A rồi B (đã có trong sample) phát hiện stale state cơ bản; concurrency test mới bảo vệ race thực tế.

## 27. MDC và logging

Ví dụ filter:

```java
// Snippet ở filter; chưa có mã nguồn class độc lập.
MDC.put("correlationId", correlationId);
try {
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("correlationId");
}
```

`finally` cần thiết vì servlet worker threads được tái sử dụng. Nếu quên clear, log request B có thể mang ID request A. Không cho access token vào MDC, response error payload hoặc tracing baggage.

Nếu filter đã generate correlation ID, controller không nên generate lại; cần **một owner** cho ID. Demo tạo ở controller để dễ hiểu; production có thể tạo sớm hơn trong filter và đặt vào request attributes/tracing context cho mọi branches (kể cả lỗi).

### 27.1. Test log redaction

Chạy request có một synthetic token đặc biệt, capture structured logs trong test, assert token không xuất hiện. Không dùng token thật trong testcase. Nếu dùng tracing, kiểm span attributes/ baggage không chứa Authorization. Đây là test riêng vì các test RestClient không tự quan sát logs.

## 28. Retry, timeout và `Idempotency-Key`

Khi client retry một request:

- GET thường idempotent về semantics, nhưng vẫn phải giới hạn attempts/timeouts/backoff.
- POST thanh toán/tạo order có thể đã commit dù client timeout; retry không có idempotency policy có thể tạo hai side effects.
- `Idempotency-Key` nên giữ **cùng giá trị cho cùng logical operation**, không tạo key mới cho mỗi attempt.
- Correlation ID có thể ổn định ở mức request; tracing tạo spans/attempts riêng.
- Access token có thể được OAuth2 authorized client manager làm mới hợp lệ; không được lấy token từ user khác.
- Interceptor có thể chạy mỗi attempt; `headers.set` tránh tích lũy duplicate header values nếu request được tái sử dụng.

Test retry nên có stub 503 rồi 200 hoặc network timeout, assert số attempts và exact headers, không chỉ assert cuối cùng trả 200. Đặc biệt với POST, mock repository/side effects hoặc dùng integration sandbox kiểm **at-most-once/idempotent semantics** phù hợp.

**Không chuyển `Idempotency-Key` đến mọi downstream chỉ vì caller gửi:** key có thể bị reuse ở trust boundary khác hoặc collide. Hợp đồng phải quy định scope (endpoint, account, operation).

## 29. Redirect cross-origin và SSRF

Giả sử trusted API trả:

```http
HTTP/1.1 302 Found
Location: https://untrusted.example/collect
```

Nếu HTTP client tự follow redirect và chuyển Authorization sang host mới, token bị lộ. Hành vi redirect khác nhau theo HTTP client factory/version/proxy; **không suy đoán** từ tên RestClient.

Cách bảo vệ:

1. Outbound base URL cố định/trusted; không lấy từ query/body của caller.
2. HTTPS, hostname validation và network egress policy.
3. Cấu hình redirect theo chính sách (tắt hoặc same-origin).
4. Real HTTP mock servers: server A trả 302 tới server B, assert server B **không nhận Authorization**.
5. Giới hạn redirect count, kiểm URL scheme/host/IP, không follow file:// hoặc localhost metadata service.
6. Không nhầm SSRF test với `MockRestServiceServer`, vì mock thay request factory và không theo network redirect thực.

`@RestClientTest` đủ để xác nhận code dùng baseURL dự kiến; **không chứng minh** redirect/TLS/proxy transport an toàn.

## 30. Downstream 401/403/429/5xx và error mapping

Một request có Authorization đúng ở mặt **cú pháp** vẫn có thể bị downstream từ chối do token hết hạn, sai audience/scope hoặc user thiếu quyền. Những error paths cần test:

| Downstream | Cần phân biệt | Public behavior gợi ý |
|---|---|---|
| 401 | Invalid user token hay service credential lỗi | Map error theo contract; không lộ token |
| 403 | User/service không đủ quyền | Không “retry để vượt quyền” |
| 429 | Rate limit | Retry/backoff theo policy, không storm |
| 5xx | Service failure | 502/503 hoặc error code rõ |
| Timeout | Network ambiguity, commit có thể xảy ra | 504/recovery/idempotency |
| Invalid JSON | Downstream contract broken | Không phản hồi body thô |
| Missing response header | Downstream header contract fail | Report correlation, không leak internals |

`RestClient.retrieve()` có default error handling cho 4xx/5xx; có thể ném `RestClientResponseException`. Demo không cấu hình error mapping ngoài happy path. Production có thể dùng `onStatus(...)` và `@RestControllerAdvice` cùng DTO lỗi công khai. Test cả status, response headers được phép, no raw secret, no body stack trace, correlation ID consistency.

## 31. Mock vs wire-level: đừng nhầm hai loại bảo đảm

`MockRestServiceServer` thay HTTP request factory trong client under test. Nó rất hiệu quả để hỏi: **“Đã dựng request đúng với các headers/value yêu cầu chưa?”**

WireMock/OkHttp MockWebServer thực sự mở HTTP port để hỏi: **“HTTP library, redirects, proxies, cookies, timeouts và TLS vận hành ra sao?”**

Khi muốn một integration test đầy đủ:

```text
MockMvc or real inbound HTTP
    |
    v
Spring Security filter chain thật
    |
    v
Controller + Service + RestClient production request factory
    |
    v
WireMock/MockWebServer on randomized port
    |
    +-- verify Authorization/correlation
    +-- return 401/503/302 as needed
    +-- capture retries and redirect traffic
```

Với `@SpringBootTest(RANDOM_PORT)` phải dùng **real inbound HTTP client** nếu muốn kiểm cả servlet transport; MockMvc trong full context vẫn là **mock servlet pipeline**. Không gọi test của demo là end-to-end; demo chủ yếu kiểm hai boundary rẻ và rõ.

## 32. Duplicate header, precedence và interceptor ownership

Có thể nhiều thành phần cùng set Authorization hoặc correlation:

```text
API gateway
 -> Security filter
 -> Correlation filter
 -> Controller
 -> RestClient request-spec headers
 -> OAuth2 interceptor
 -> Tracing interceptor
 -> ClientHttpRequestFactory
 -> Network proxy
```

Nếu cả controller và interceptor đều đặt token, thứ tự có thể thay đổi sau refactor. Nếu filter tạo ID A nhưng controller lại tạo ID B, logs không nối được. Nếu retry interceptor dùng `add` thay vì `set`, header values có thể bị nhân đôi.

**Giải pháp:** Mỗi header có **một owner**, một precedence contract và tests ở boundary sau cùng. Khi team thêm OAuth2 interceptor, cập nhật tests với chính interceptor ấy; đừng chỉ assert context nội bộ rồi suy ra final outbound header vẫn giống nhau.

## 33. Bảng lỗi dễ gặp

| Triệu chứng | Root cause có thể | Kiểm tra |
|---|---|---|
| Downstream 401 dù inbound có token | Header mất, wrong audience/scope, expiry | RestClientTest + security token validation |
| `Bearer Bearer abc` | Truyền cả scheme vào `setBearerAuth` | Chỉ truyền token |
| User B gửi token của A | Singleton defaultHeader / mutable field | Request-local headers, concurrency |
| Cookie xuất hiện ở downstream | `headers.addAll(...)` | Allowlist + absence matcher |
| Response thiếu correlation | Không cùng owner hoặc missing filter | Capture outbound + response |
| Correlation ID thay trên mỗi hop | Nhiều nơi generate mới | Generate một lần, validate/reuse |
| Traceparent bị mất child span | Manual copying overrides tracer | W3C tracing instrumentation |
| Headers double-added | Các interceptors cùng `add` | `set` + final outgoing matcher |
| Mock server test pass, production redirect leak | Mock không dùng network transport | Real HTTP redirect test |
| Missing channel | Contract/policy thiếu | 400 before outbound |
| Invalid token format vẫn đi tới API | Không có header validation | Pure policy + MVC zero interaction |
| Header quá dài gây 431 | Gateway/server max header length | Boundary size policy |
| Token trong logs | Print full HttpHeaders/RelayContext | Redaction/log test |
| Test async flaky | ThreadLocal context mất hoặc leaked | Context propagation tests |
| MockMvc pass nhưng downstream header sai | CatalogClient là mock | @RestClientTest |
| Client test pass nhưng HTTP proxy fail | Request factory/TLS/proxy khác | Wire-level integration |
| Downstream 429 làm retry storm | Không có backoff/budget | Retry contract test |

## 34. Bài tập thực hành

### A — Duplicate Bearer

Code `headers.setBearerAuth("Bearer abc")` sẽ sai ở đâu? Viết test assert exact outgoing Authorization bằng `MockRestRequestMatchers.header` và sửa dùng `"abc"`.

### B — Correlation ID thiếu

Inbound không có `X-Correlation-ID`. Thay vì so với một UUID random mới, capture ID từ response và `RelayContext`, assert cùng giá trị và dạng UUID.

### C — Correlation bị inject

Client gửi ID chứa newline/control chars hoặc UUID thiếu segment. Policy demo phản hồi gì? HTTP client có được gọi không? Dùng `verifyNoInteractions`.

### D — Identity header giả

Client tự gửi `X-Tenant-ID=admin`. Gateway nên lấy tenant từ đâu? Nêu test chứng minh user A không thể truy cập tenant B dù giả header.

### E — Token wrong audience

Inbound JWT audience A, downstream yêu cầu audience B. Có thể copy Authorization không? Mô tả OAuth2 token exchange hoặc client credentials tùy trường hợp.

### F — Test bị đánh lừa bởi mock

`@WebMvcTest` pass vì CatalogClient mock trả success, nhưng code RestClient thực quên `X-Correlation-ID`. Test nào bắt lỗi đó? Vì sao cần `@RestClientTest`?

### G — Rò Cookie

Một refactor dùng `headers.addAll(inboundHeaders)` và bắt đầu forward Cookie. Thêm absence matcher nào? Vì sao không chỉ kiểm status 200?

### H — Redirect

HTTP client follow 302 từ trusted host sang untrusted host. MockRestServiceServer đã verify request đầu đúng. Có chứng minh không leak token không? Thiết kế hai real mock HTTP servers để kiểm.

### I — Retry POST

Downstream đã commit nhưng client timeout, retry với key mới. Rủi ro và chính sách dùng `Idempotency-Key` là gì?

### J — WebClient và Reactor Context

Một WebClient call chạy trên scheduler khác, không còn ThreadLocal token của servlet request. Hãy đề xuất context design và test chạy đồng thời A/B để phát hiện token bleed.

### K — Correlation vs traceparent

Trace-id giữ nguyên nhưng parent-id trên outbound khác inbound. Có nhất thiết sai không? Cách test quan hệ spans đúng hơn so raw header là gì?

### L — Header contract thay đổi

Downstream mới yêu cầu `X-API-Version=v2`. Nên cập nhật allowlist của adapter, tests hay proxy toàn bộ headers? Giải thích lý do.

## 35. Checklist cho code review

- [ ] Chỉ propagate header theo allowlist của từng downstream.
- [ ] Không relay Bearer token qua trust boundary sai hoặc dùng token sai audience/scope.
- [ ] Token inbound được xác thực ở production; demo header parser không bị hiểu nhầm là authn.
- [ ] Không log token trong URL, logs, MDC, tracing baggage hoặc error response.
- [ ] Không set Authorization mặc định từ token user A trên singleton RestClient.
- [ ] `setBearerAuth` nhận token value, không có scheme.
- [ ] Correlation ID được validate/generate một lần, trả về client và downstream nhất quán.
- [ ] Tracing propagator quản lý `traceparent`/`tracestate`.
- [ ] `X-Client-Channel`/version/idempotency được kiểm đúng contract.
- [ ] Cookies, proxy credentials và forwarded headers giả mạo không được relay.
- [ ] Host/Content-Length/hop-by-hop do transport quản lý.
- [ ] Response headers có allowlist khác request headers.
- [ ] `@WebMvcTest` có tests cho 400/401 và zero downstream invocation.
- [ ] `@RestClientTest` verify method/URL, exact headers và missing headers.
- [ ] Client test có `server.verify()`.
- [ ] Token/correlation không bị dùng chéo qua hai request liên tiếp.
- [ ] Async/reactive context được propagate và clear đúng.
- [ ] Idempotency retry có key stable và giới hạn retry.
- [ ] Real mock-server test có mặt nếu rủi ro nằm ở redirect/TLS/proxy.
- [ ] Security integration test kiểm issuer/audience/scope/expiry/authorization.
- [ ] Downstream 401/429/5xx/timeout có mapping không leak secrets.
- [ ] Base URL fixed/trusted, không lấy URL tùy ý từ client.
- [ ] Không dùng real tokens/PII trong test fixtures.
- [ ] Test scopes trung thực: controller mock khác outbound mock khác real HTTP.

**Kết luận:** Header propagation an toàn đòi hỏi **policy, trust boundary và kiểm thử đúng cấp độ**. Token là credential có audience/scope, correlation ID là metadata cần định dạng/chính sách thống nhất, W3C trace context thuộc tracing instrumentation. Kiểm cả header **cần có** và header **bắt buộc vắng mặt**; dùng request-local context thay vì mutable singleton; kết hợp `@WebMvcTest` và `@RestClientTest` để bắt lỗi ở hai phía và bổ sung wire-level/security tests nơi mocks không quan sát được.

### Tài liệu tham khảo chính thức

- Spring Boot 3.5 — `@RestClientTest` + `MockRestServiceServer`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — REST Clients `RestClient`/`WebClient`: https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html
- Spring Framework 6.2 — Testing HTTP Client Code, mock vs wire: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-client.html
- Spring Security 6.5 — OAuth2AuthorizedClientManager và RestClient interceptor: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- W3C Trace Context — traceparent/tracestate: https://www.w3.org/TR/trace-context/
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110
- OWASP — SSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
