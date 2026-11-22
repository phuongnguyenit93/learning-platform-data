# OpaqueTokenIntrospector và SpringOpaqueTokenIntrospector theo phiên bản

## 1. Bài toán: Resource Server xác thực một Bearer token mà không tự giải mã được

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, API thường nhận access token qua HTTP:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer 8pABlP0q6sV2...opaque-token...
```

Với **JWT access token có chữ ký**, Resource Server thường sử dụng `JwtDecoder` để xác minh JWS, issuer, audience, thời hạn và các claim. Ngược lại, với **opaque access token**, chuỗi token không cung cấp một cấu trúc JWT mà API có thể tin cậy đọc và xác minh cục bộ. API cần hỏi **Authorization Server** (hoặc một dịch vụ kiểm tra token được ủy quyền) xem token có còn active và mang những thuộc tính gì.

Chuẩn **RFC 7662 — OAuth 2.0 Token Introspection** định nghĩa một endpoint để Resource Server gửi token và nhận trạng thái cùng metadata tương ứng.

Trong Spring Security Servlet:

- **`OpaqueTokenIntrospector`** là *giao diện* mô tả hợp đồng kiểm tra token.
- **`SpringOpaqueTokenIntrospector`** là *một triển khai* gửi HTTP request tới introspection endpoint.
- **`NimbusOpaqueTokenIntrospector`** là triển khai lịch sử, tồn tại trong các phiên bản cũ và được đánh dấu deprecated ở các phiên bản mới.
- **`RestClientOpaqueTokenIntrospector`** là triển khai thay thế dựa trên Spring `RestClient` xuất hiện trong dòng Spring Security 7.1.

Việc biết **đang dùng phiên bản Spring Security nào** rất quan trọng, vì tên class, builder, constructor và cách encoding client credentials đã thay đổi theo thời gian.

> **Nguyên tắc chính:** Application code nên phụ thuộc vào **`OpaqueTokenIntrospector` interface**, chỉ lựa chọn implementation phù hợp với phiên bản framework ở lớp cấu hình. Không đổi implementation để né kiểm tra `active`, scope, issuer, audience hoặc ranh giới truy cập API.

## 2. RFC 7662: introspection request và response

### 2.1. Resource Server gửi gì?

Resource Server được cấp một credential cho **chính nó** để gọi introspection endpoint. Ví dụ request:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <encoded-introspection-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=8pABlP0q6sV2...&token_type_hint=access_token
```

`token` là credential mà API nhận được từ client. `token_type_hint` là tham số gợi ý **không bắt buộc** theo RFC 7662; Spring implementation/hợp đồng provider quyết định request thực tế có gửi tham số này hay không.

**Không nhầm hai loại credential:**

1. Bearer access token của người dùng hoặc ứng dụng gọi API, được gửi **tới Resource Server**.
2. `client-id`/`client-secret` của Resource Server, dùng **để xác thực với introspection endpoint**.

Hai credential không được dùng thay nhau và phải được bảo vệ riêng. Client secret cho introspection không được đặt trong browser hoặc trả về response của API.

### 2.2. Trường hợp active

Một response ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "client_id": "orders-web-client",
  "aud": ["orders-api"],
  "scope": "orders:read orders:export",
  "exp": 1893456000,
  "iat": 1893452400,
  "token_type": "Bearer"
}
```

Response này mang dữ liệu minh họa, không phải phản hồi của một hệ thống đang chạy. Ý nghĩa thường gặp:

| Thuộc tính | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| `active` | Nhà phát hành/dịch vụ introspection xác nhận token đang được công nhận. | Không phải giấy phép truy cập mọi API; cần policy tài nguyên. |
| `scope` | Những phạm vi đã cấp, thường là chuỗi phân cách dấu cách. | Spring có thể chuyển từng scope thành authority `SCOPE_...`. |
| `sub` | Subject theo hợp đồng nhà phát hành. | Không tự động là email hoặc internal user ID. |
| `client_id` | OAuth client được cấp token. | Không thay thế `aud` hoặc quyền của principal. |
| `aud` | Đối tượng nhận dự kiến, nếu được provider công bố. | API có thể cần kiểm tra đúng resource ID. |
| `iss` | Issuer nếu được provider trả về. | Phải áp dụng issuer contract khi có nhiều nguồn. |
| `exp` / `iat` | Mốc hết hạn/phát hành nếu được trả về. | Cần hiểu chính sách thời hạn và dữ liệu được server cung cấp. |
| `token_type` | Kiểu token theo response. | Không biến credential thành JWT có chữ ký. |

Không phải introspection endpoint nào cũng trả **tất cả** các field trên. RFC 7662 đặt `active` là thành phần quan trọng, còn các metadata khác phụ thuộc provider, quyền truy cập introspection và token profile. **Hợp đồng API phải quy định metadata nào bắt buộc để ra quyết định authorization.**

### 2.3. Trường hợp inactive

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": false
}
```

Token có thể đã hết hạn, bị thu hồi, chưa tồn tại hoặc không được nhà phát hành công nhận. Theo RFC 7662, bên kiểm tra không nhất thiết tiết lộ lý do chi tiết cho Resource Server. Một introspector đúng không được tạo principal đã authenticated từ response `active: false`.

**Phân biệt:** HTTP 200 từ introspection endpoint **không có nghĩa token active**. Phải đọc nội dung `active`. Ngược lại, lỗi HTTP 401 tại **introspection endpoint** có thể báo Resource Server đã dùng sai client credentials, không chứng minh Bearer token của người dùng sai.

## 3. Luồng xử lý bên trong Spring Security Servlet

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as OpaqueTokenAuthenticationProvider
    participant I as OpaqueTokenIntrospector
    participant AS as Introspection Endpoint
    participant A as AuthorizationFilter
    C->>F: GET /api/orders + Bearer token
    F->>F: Tạo BearerTokenAuthenticationToken
    F->>M: authenticate(token)
    M->>P: Chọn provider hỗ trợ Bearer token
    P->>I: introspect(rawToken)
    I->>AS: POST token + introspection credentials
    AS-->>I: active + metadata
    alt active=false hoặc lỗi xác thực
        I-->>P: Exception
        P-->>F: AuthenticationException
        F-->>C: Từ chối Bearer credential
    else active=true và chính sách hợp lệ
        I-->>P: OAuth2AuthenticatedPrincipal + authorities
        P-->>M: BearerTokenAuthentication
        M-->>F: Authentication đã xác thực
        F->>A: SecurityContext
        A-->>C: 2xx hoặc 403 theo quyền
    end
```

Vai trò của từng thành phần:

1. `BearerTokenAuthenticationFilter` trích chuỗi token từ HTTP request.
2. `AuthenticationManager`, thường là `ProviderManager`, chuyển `BearerTokenAuthenticationToken` tới provider phù hợp.
3. `OpaqueTokenAuthenticationProvider` gọi `OpaqueTokenIntrospector.introspect(token)`.
4. Introspector hỏi endpoint hoặc nguồn trạng thái đáng tin cậy, trả `OAuth2AuthenticatedPrincipal` nếu token được chấp nhận.
5. Provider xây `BearerTokenAuthentication`, có authorities và attributes từ kết quả introspection.
6. Spring Security đặt authentication vào `SecurityContext`; URL security và method security quyết định quyền.

**Không có bước bắt buộc giải mã chữ ký JWS trong luồng này.** Spring Security không cần token là JWT mới gọi introspection; nó có thể gửi **bất kỳ chuỗi Bearer** được resolver nhận diện tới introspection endpoint. Vì vậy ngay cả JWT cũng có thể được **xác thực bằng introspection** nếu chính sách yêu cầu hỏi Authorization Server để phát hiện revocation.

## 4. OpaqueTokenIntrospector: hợp đồng ổn định qua các phiên bản

Giao diện nằm trong package:

```java
org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector
```

Chữ ký trọng tâm:

```java
@FunctionalInterface
public interface OpaqueTokenIntrospector {

    OAuth2AuthenticatedPrincipal introspect(String token);
}
```

Trong thực tế, phương thức có thể ném exception khi token không hợp lệ hoặc introspection không thực hiện được.

Điểm quan trọng:

- Tham số là **chuỗi token**, không phải toàn bộ header `Authorization`.
- Return type là `OAuth2AuthenticatedPrincipal`, chứa attributes, authorities và tên principal.
- **Trả principal là một tín hiệu token đã vượt bước introspection**. Không tự trả principal cho `active: false`.
- Có thể tạo một **custom implementation/decorator** để bổ sung policy, metrics hoặc cache có kiểm soát.
- Khi đổi HTTP implementation bên dưới, code business chỉ cần phụ thuộc vào interface này.

Các loại exception liên quan:

| Loại | Ý nghĩa điển hình |
| --- | --- |
| `BadOpaqueTokenException` | Token bị từ chối vì không hợp lệ, inactive hoặc không đạt một điều kiện chấp nhận. |
| `OAuth2IntrospectionException` | Lỗi trong quá trình introspection, bao gồm một số vấn đề request/response/remote service. |
| `AuthenticationException` ở tầng provider/filter | Spring Security chuyển lỗi xác thực phù hợp thành Bearer response. |

**Không đánh đồng mọi lỗi introspection với token bị thu hồi.** Ví dụ timeout, DNS, TLS failure hoặc client credentials sai là sự cố liên lạc/cấu hình. Cần xử lý **fail-closed** (không tự chấp nhận token) nhưng phân loại lỗi vận hành và phản hồi HTTP một cách phù hợp; 5xx/503 có thể thích hợp với lỗi hạ tầng thay vì luôn tuyên bố token sai.

## 5. SpringOpaqueTokenIntrospector là gì?

`SpringOpaqueTokenIntrospector` là implementation gửi introspection request HTTP theo cấu hình, giải thích response và tạo `OAuth2AuthenticatedPrincipal`. Nó nằm cùng package với interface:

```java
import org.springframework.security.oauth2.server.resource.introspection
        .SpringOpaqueTokenIntrospector;
```

Tên **SpringOpaqueTokenIntrospector** dễ gây hai nhầm lẫn:

1. Nó **không phải** một giao diện mới thay `OpaqueTokenIntrospector`; nó **implements** giao diện đó.
2. Chữ “Spring” trong tên class **không có nghĩa mọi phiên bản Spring Security đều có cùng builder/constructor**.

Đặc biệt, một đoạn code được viết cho 6.5+ có thể **không compile** trên 6.4 hoặc 5.6 chỉ vì sử dụng `withIntrospectionUri(...)` builder chưa xuất hiện ở phiên bản đó.

## 6. Bảng thay đổi API theo phiên bản Spring Security

Các mốc sau là **mốc của thư viện Spring Security**, không phải số version Spring Boot. Trong dự án Boot, hãy xem dependency-managed `spring-security-oauth2-resource-server` thực sự được resolve, không suy từ một bài viết blog hoặc tên Spring Boot starter.

| Dòng phiên bản Spring Security | API/hành vi đáng chú ý | Khuyến nghị khi viết code |
| --- | --- | --- |
| **5.2–5.5** | `OpaqueTokenIntrospector` và `NimbusOpaqueTokenIntrospector` có từ giai đoạn hỗ trợ introspection ban đầu. | Dùng API có thật trong bản đang chạy; các ví dụ Nimbus có thể phù hợp dự án legacy. |
| **5.6–6.4** | `SpringOpaqueTokenIntrospector` đã xuất hiện (Since 5.6); dùng constructor/`RestOperations` phù hợp. | Với 5.6+, có thể chọn Spring implementation; **không dùng builder 6.5** nếu dependency chưa hỗ trợ. |
| **6.5** | `SpringOpaqueTokenIntrospector.withIntrospectionUri(...).clientId(...).clientSecret(...).build()` được bổ sung; constructor ba tham số `(uri,id,secret)` bị deprecated (forRemoval). `NimbusOpaqueTokenIntrospector` được tài liệu 6.5 đánh dấu deprecated, khuyến nghị dùng Spring implementation. | Với 6.5+, **ưu tiên builder** và chuyển code phụ thuộc Nimbus khi phù hợp. |
| **7.0** | Hướng dẫn migration nêu xử lý encoding client ID/secret được điều chỉnh theo RFC, builder nhận **giá trị chưa URL-encode**; cơ chế mặc định mới hỗ trợ encoding cho bạn. | Kiểm tra kỹ special characters của introspection client credentials khi nâng cấp từ 6.x. |
| **7.1+** | Có thêm `RestClientOpaqueTokenIntrospector` sử dụng Spring `RestClient` (Since 7.1), bên cạnh `SpringOpaqueTokenIntrospector` dựa trên `RestOperations`/`RestTemplate`. | Có thể dùng RestClient implementation khi library hỗ trợ; không copy code này sang 6.x/7.0. |

Hai lưu ý quan trọng:

- `SpringOpaqueTokenIntrospector` **không được “đổi tên” thành `OpaqueTokenIntrospector`**: interface vẫn được sử dụng. Implementation và builder mới là phần thay đổi.
- `NimbusOpaqueTokenIntrospector` từng là lựa chọn của nhiều tutorial cũ; việc thấy code Nimbus không có nghĩa **đây là API được khuyến nghị cho phiên bản mới**. Không kết luận nó bị xóa khỏi mọi bản chỉ vì đã deprecated; phải xem Javadoc đúng dependency đang dùng.

### 6.1. Tránh trộn documentation của các phiên bản

Ví dụ:

```java
// API builder dùng cho Spring Security 6.5+.
SpringOpaqueTokenIntrospector.withIntrospectionUri(uri)
        .clientId(id)
        .clientSecret(secret)
        .build();
```

Nếu dự án ở **Spring Security 6.3**, IDE báo không tìm thấy `withIntrospectionUri` thì nguyên nhân có thể là **builder chưa xuất hiện**, không phải thiếu một import bí ẩn.

Tương tự:

```java
// Chỉ có ở Spring Security 7.1+.
RestClientOpaqueTokenIntrospector.withIntrospectionUri(uri)
        .clientId(id)
        .clientSecret(secret)
        .build();
```

Nếu một dự án 6.5 không compile dòng trên, cần chọn `SpringOpaqueTokenIntrospector` phù hợp phiên bản, không ép thêm các JAR Spring Security 7.1 vào một dependency set 6.5 gây lệch phiên bản.

## 7. Cách cấu hình đơn giản nhất: Spring Boot properties

Với Spring Boot có hỗ trợ auto-configuration cho opaque Resource Server, **nhiều trường hợp không cần tự tạo introspector bean**:

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

Đây là ví dụ cấu hình; `INTROSPECTION_CLIENT_ID`/`INTROSPECTION_CLIENT_SECRET` phải được cấp qua secret manager/environment tương ứng. Không commit credential thật lên source control.

Và:

```java
@Configuration
class OpaqueApiSecurity {

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

Khi không có bean custom thay thế, Boot có thể cấu hình `OpaqueTokenIntrospector` mặc định theo properties và Spring Security kết nối nó với `OpaqueTokenAuthenticationProvider`. Về nguyên tắc, phần code service/controllers không phải biết implementation HTTP cụ thể.

### 7.1. Dependencies

Với Spring Boot:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Trong các dòng Spring Security hiện đại, chức năng opaque token thường có trong module `spring-security-oauth2-resource-server`, với HTTP dependencies phù hợp do Boot quản lý. Tài liệu Spring Security 5.5 cũ từng yêu cầu thêm dependency Nimbus OAuth 2.0/OIDC SDK cho triển khai Nimbus mặc định; khi nâng cấp, không nên bê nguyên yêu cầu dependency lịch sử vào 6.5/7.x mà không kiểm tra dependency graph thực tế.

**Đừng khai báo thủ công nhiều version Spring Security khác nhau** chỉ để một class có mặt. Nếu API thiếu builder, hãy chọn cách cấu hình có sẵn trong phiên bản đã được dự án quản lý hoặc nâng cấp cả dependency set có kiểm soát.

### 7.2. Kết quả authorization

Giả sử introspection trả:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export"
}
```

Spring Security thường tạo authorities:

```text
SCOPE_orders:read
SCOPE_orders:export
```

Request `GET /api/orders` đòi `SCOPE_orders:read` có thể đi tiếp vào controller. Request cần `SCOPE_orders:write` phải bị từ chối ở authorization nếu principal không có quyền đó.

**`active: true` không đồng nghĩa “đủ scope”.** Authentication và authorization là hai bước khác nhau.

## 8. Tạo bean SpringOpaqueTokenIntrospector trên Spring Security 6.5+

Từ **6.5**, có thể dùng builder để cấu hình introspection URI cùng client credentials ở dạng **chưa mã hóa URL**:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
        .SpringOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        return SpringOpaqueTokenIntrospector
                .withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();
    }
}
```

Builder trong Spring Security 6.5+ có các điểm cần nhớ:

- `withIntrospectionUri(uri)` bắt đầu tạo `SpringOpaqueTokenIntrospector.Builder`.
- `clientId(clientId)` và `clientSecret(clientSecret)` nhận **giá trị thô, chưa URL-encode** theo Javadoc builder.
- `build()` trả một `SpringOpaqueTokenIntrospector` có thể gán cho interface `OpaqueTokenIntrospector`.
- Việc khai báo bean custom có thể khiến Boot không tạo bean mặc định; phải bảo đảm bean đó được chain đang xử lý request sử dụng.

Ví dụ dùng cùng properties với mục 7 nhưng đây là **cách thay thế có chủ đích**, không phải luôn phải khai báo song song. Khi properties auto-configuration đã đáp ứng nhu cầu, dùng properties sẽ gọn hơn; chỉ tạo bean để tùy chỉnh HTTP client, validation, metrics hoặc nguồn response.

### 8.1. Lưu ý trong môi trường đã tùy chỉnh SecurityFilterChain

Khai báo bean `OpaqueTokenIntrospector` không tự biến một chain đang gọi `oauth2ResourceServer().jwt()` thành opaque Resource Server. Chain phải được cấu hình:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

Hoặc dùng explicit introspector cho đúng chain:

```java
.oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(opaque ->
        opaque.introspector(customIntrospector)))
```

API cấu hình `jwt()` sử dụng `JwtDecoder`; API cấu hình `opaqueToken()` sử dụng `OpaqueTokenIntrospector`. Không giả định Spring sẽ tự nhìn chuỗi có dấu chấm hay không để chọn một trong hai cho mỗi request.

## 9. Dự án cũ: NimbusOpaqueTokenIntrospector

Trong nhiều codebase Spring Security 5.x, cách tạo introspector như sau:

```java
// Ví dụ legacy: kiểm tra constructor trên đúng Spring Security version.
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    return new NimbusOpaqueTokenIntrospector(
            uri, clientId, clientSecret);
}
```

Với phiên bản có class này, code dùng Nimbus có thể vẫn hoạt động. Nhưng khi ứng dụng đã nâng cấp lên **Spring Security 6.5**, tài liệu Javadoc đánh dấu `NimbusOpaqueTokenIntrospector` deprecated và hướng tới `SpringOpaqueTokenIntrospector`.

Không nên **thay tên class một cách cơ học** mà bỏ qua:

- Cách HTTP request được tạo và gửi.
- Cách client ID/secret được URL-encode khi tạo Basic authentication.
- Chính sách timeout/TLS/proxy.
- Cách mapping response thành principal và authorities.
- Các custom request entity converters hay interceptors đã đăng ký.
- Bộ test phụ thuộc hành vi cụ thể của implementation cũ.

Khi nâng cấp từ Nimbus sang Spring, hãy giữ interface của ứng dụng là `OpaqueTokenIntrospector` và chạy integration tests với **introspection endpoint giả lập** để xác minh wire format và response behavior.

### 9.1. SpringOpaqueTokenIntrospector trước 6.5

`SpringOpaqueTokenIntrospector` đã tồn tại từ **5.6**, nhưng builder `withIntrospectionUri` chỉ xuất hiện ở **6.5**.

Trong các phiên bản 5.6–6.4, code mẫu dùng constructor:

```java
OpaqueTokenIntrospector introspector =
        new SpringOpaqueTokenIntrospector(
                introspectionUri, clientId, clientSecret);
```

Constructor ba tham số vẫn có mặt trong Javadoc 6.5 nhưng bị `@Deprecated(since="6.5", forRemoval=true)`. Javadoc constructor đề cập client credentials theo cách đã URL-encode; builder 6.5+ chủ động nhận **unencoded credentials**. Vì thế, với credentials có ký tự đặc biệt như `:`, `@`, `+`, `/` hoặc Unicode, phải kiểm tra bản Spring Security cụ thể và **không tự encode thêm lần nữa khi dùng builder**.

Ví dụ cũ có thể chạy đúng khi client ID/secret chỉ chứa ký tự đơn giản, nhưng lại lỗi **401 từ introspection endpoint** sau khi đổi secret chứa ký tự đặc biệt. Đó thường là dấu hiệu **encoding/Basic auth** chưa đúng, không phải Bearer token bị revoke.

## 10. Phiên bản 7.1+: RestClientOpaqueTokenIntrospector

Các Javadoc từ Spring Security **7.1** có thêm `RestClientOpaqueTokenIntrospector`, dùng Spring `RestClient` để gọi introspection endpoint. Đây là **tùy chọn implementation mới**, không phải một tên khác của interface.

```java
// Spring Security 7.1+.
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    return RestClientOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();
}
```

Code cần import `org.springframework.security.oauth2.server.resource.introspection.RestClientOpaqueTokenIntrospector` và class interface. Nếu dự án 7.0 hoặc 6.x không nhận ra class này, đó là **khác biệt phiên bản được mong đợi**.

So sánh ngắn:

| Lựa chọn | HTTP client bên dưới | Mốc sử dụng | Nhận xét |
| --- | --- | --- | --- |
| `NimbusOpaqueTokenIntrospector` | Triển khai lịch sử trong Spring Security, liên quan Nimbus SDK. | Có từ 5.2; deprecated ở 6.5. | Phù hợp đọc/duy trì legacy, không ưu tiên khi viết code mới trên 6.5+. |
| `SpringOpaqueTokenIntrospector` | Spring `RestOperations`/`RestTemplate`. | Có từ 5.6; builder từ 6.5. | Lựa chọn chủ đạo ở nhiều bản 6.5/7.0. |
| `RestClientOpaqueTokenIntrospector` | Spring `RestClient`. | Từ 7.1. | Phù hợp dự án 7.1+ muốn cấu hình HTTP bằng RestClient. |

**Không dùng `RestClientOpaqueTokenIntrospector` trong WebFlux reactive chain.** Với WebFlux, Spring Security có **`ReactiveOpaqueTokenIntrospector`** và implementation reactive tương ứng, khác giao diện đồng bộ trong Servlet stack. Bài học này tập trung Servlet.

## 11. Client credentials encoding: thay đổi quan trọng khi nâng cấp 6.5 → 7

Khi gọi RFC 7662 introspection endpoint, Resource Server phải xác thực với Authorization Server. Một cách phổ biến là HTTP Basic. Cách biểu diễn `client_id` và `client_secret` trong Basic khi chứa ký tự không an toàn cho URL cần tuân thủ yêu cầu giao thức và phiên bản thư viện.

Ví dụ credentials giả định:

```text
client_id     = orders:api+introspection
client_secret = p@ss/word:with+chars
```

Đây là các chuỗi minh họa, không phải secret thật.

Điểm cần nhớ theo tài liệu migration Spring Security:

- Constructor cũ `SpringOpaqueTokenIntrospector(uri, clientId, clientSecret)` bị deprecated từ 6.5, và Javadoc có cảnh báo về credential encoding.
- Builder `SpringOpaqueTokenIntrospector.withIntrospectionUri(uri).clientId(...).clientSecret(...).build()` xuất hiện từ 6.5, **nhận giá trị unencoded và xử lý encode**.
- Hướng dẫn migration sang 7.0 khuyến nghị dùng builder vì luồng mới tự encoding client credentials theo RFC.
- Nếu dự án đã lưu `clientId`/`clientSecret` dưới dạng percent-encoded trong secret manager cho constructor cũ, **không đưa nguyên dữ liệu đã encoded đó vào builder** mà không xác nhận; có thể dẫn đến double encoding và 401 introspection.

### 11.1. Ví dụ lỗi double encoding

Giả sử secret logic có ký tự `+`. Khi URL-encode, `+` có thể thành `%2B`. Nếu một lớp tự encode giá trị thành `%2B`, rồi builder lại encode một lần nữa, chuỗi có thể biến thành `%252B`. Authorization Server giải mã một lần sẽ thấy `%2B` thay vì `+`, khiến Basic authentication thất bại.

Không kết luận đơn giản rằng **“client secret sai”** khi token bị từ chối. Cần xác định credential được lưu ở dạng gì, implementation phiên bản nào đang encode và endpoint kiểm tra gì.

### 11.2. Chiến lược migration an toàn

1. Xác định Spring Security version và implementation cũ.
2. Xác định credential trong secret manager là **raw** hay **đã encode**.
3. Dùng builder cho 6.5+/7.x với **raw client ID/secret** theo hợp đồng.
4. Test một credential có dấu `+`, `:`, `@` nếu issuer cho phép, **qua HTTP mock endpoint**, không log secret.
5. Xác nhận introspection server nhận đúng danh tính client và trả JSON đúng.
6. Sau đó mới rollout, theo dõi lỗi endpoint, 401/5xx, latency và tỷ lệ active=false.

**Không ghi Basic Authorization header, token hoặc secret vào stdout/test snapshots/log** chỉ để xem encoding. Có thể assert request metadata/giá trị đã giải mã trong mock test hoặc dùng secret placeholder.

## 12. Tùy biến HTTP client và timeout

Introspection là một **remote call** nên latency và availability của Authorization Server ảnh hưởng trực tiếp tới API.

`SpringOpaqueTokenIntrospector` có constructor nhận `RestOperations`, phù hợp khi cần cấu hình:

- Connection timeout và read timeout.
- Proxy, TLS trust và mTLS nếu Authorization Server yêu cầu.
- Connection pooling/retry có kiểm soát.
- Basic authentication hoặc client authentication cơ chế khác theo contract.
- Metrics/tracing đã loại bỏ dữ liệu nhạy cảm.

Ví dụ hướng tiếp cận với Spring Boot `RestTemplateBuilder` (tên API timeout có thể khác giữa các đời Boot):

```java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        RestTemplateBuilder builder,
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    RestOperations rest = builder
            .basicAuthentication(clientId, clientSecret)
            .setConnectTimeout(Duration.ofSeconds(3))
            .setReadTimeout(Duration.ofSeconds(3))
            .build();

    return new SpringOpaqueTokenIntrospector(uri, rest);
}
```

Ví dụ trên minh họa phong cách builder của một số dòng Spring Boot 3.x; các bản Boot mới có thể đổi tên method cấu hình timeout. **Đối chiếu API theo bản Boot đang dùng**, và bảo đảm `RestOperations` tự xác thực với introspection endpoint đúng theo hợp đồng. Không copy constructor `(uri, RestOperations)` mà quên gắn credentials lên HTTP client.

Trong Spring Security 7.1+, có thể cân nhắc `RestClientOpaqueTokenIntrospector` với `RestClient` tùy chỉnh. Khi chọn HTTP client, cần giữ chính sách URL, TLS, HTTP status, credential encoding và response parsing nhất quán.

### 12.1. Timeout không phải lý do để fail-open

Nếu introspection server quá chậm hoặc tạm thời mất kết nối, **không được**:

```java
// SAI: lỗi mạng nhưng vẫn chấp nhận mọi token.
try {
    return delegate.introspect(token);
} catch (RuntimeException exception) {
    return makeAdminPrincipal();
}
```

Ứng dụng phải phân biệt **token invalid** với **dependency unavailable**, đồng thời không cấp quyền cho token chưa được xác nhận. Có thể áp dụng circuit breaker, bounded retry hoặc cache phù hợp SLA revocation, nhưng phải định nghĩa rõ policy khi không có dữ liệu introspection hợp lệ.

## 13. Principal và authorities trả về có cấu trúc gì?

Introspector trả `OAuth2AuthenticatedPrincipal`; provider tạo `BearerTokenAuthentication` khi authentication thành công. Spring Security có thể lấy authorities từ `scope`:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export",
  "client_id": "web-client",
  "aud": ["orders-api"]
}
```

Kết quả logic:

```text
Authentication type: BearerTokenAuthentication
Principal type:      OAuth2AuthenticatedPrincipal
principal.name:      thường từ sub nếu provider trả sub
authorities:         SCOPE_orders:read
                     SCOPE_orders:export
```

Trong một số bản Spring Security mới còn có authority biểu diễn **authentication factor**; vì vậy không nên test `getAuthorities().size() == 2` như quy tắc bất biến cho mọi phiên bản. Hãy kiểm tra **authority cần thiết thực sự có mặt** và không có quyền nhạy cảm ngoài dự kiến.

### 13.1. Controller đọc attributes

```java
@GetMapping("/api/me")
public Map<String, Object> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Map.of(
            "subject", principal.getAttribute("sub"),
            "client", principal.getAttribute("client_id"));
}
```

Đây là ví dụ minh họa: `Map.of` không chấp nhận `null`, nên trong code production phải xử lý trường hợp provider **không trả `sub` hoặc `client_id`**. Không phải introspection response nào cũng chứa đầy đủ metadata; cũng không nên trả nguyên raw attributes cho client.

Nếu dùng `BearerTokenAuthentication`:

```java
@GetMapping("/api/token-info")
public String tokenSubject(BearerTokenAuthentication authentication) {
    Object subject = authentication.getTokenAttributes().get("sub");
    return subject == null ? "unknown" : subject.toString();
}
```

Ví dụ trên chỉ nên dùng để học cách truy cập principal; endpoint production cần chính sách tiết lộ thông tin. **Không trả Bearer token**, client secret hoặc toàn bộ introspection response ra API công khai.

### 13.2. Scope không thay thế object-level authorization

`SCOPE_orders:read` cho phép thực hiện hành động đọc theo policy. Nó không chứng minh user được đọc **mọi đơn hàng**. API vẫn phải kiểm tra owner/tenant/role:

```java
@PreAuthorize(
    "hasAuthority('SCOPE_orders:read') "
    + "and @orderPolicy.canRead(authentication, #orderId)")
public OrderDto readOrder(@P("orderId") UUID orderId) {
    // ...
}
```

`@orderPolicy` là bean do ứng dụng triển khai, phải đọc danh tính và dữ liệu tin cậy. Nếu principal của opaque token không chứa user subject, đừng tự gán `email` hay tên hiển thị làm khóa quyền sở hữu.

## 14. Bổ sung resource/audience policy bằng decorator

Introspection endpoint có thể trả `active: true` cho token hợp lệ **trong hệ sinh thái issuer**, nhưng token đó chưa chắc được phát hành cho **API hiện tại**. Nếu hợp đồng yêu cầu `aud=orders-api` và introspection response trả claim `aud`, API có thể kiểm tra thêm trước khi tạo principal tin cậy.

Ví dụ decorator:

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
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
        boolean matches =
                (aud instanceof String value
                        && expectedAudience.equals(value))
                || (aud instanceof Collection<?> values
                        && values.contains(expectedAudience));

        if (!matches) {
            throw new BadOpaqueTokenException(
                    "Access token is not for this resource");
        }

        return principal;
    }
}
```

Decorator chỉ nhận principal từ delegate **sau khi delegate đã introspect thành công**. Nó không tự gửi HTTP và không tạo principal nếu token inactive.

Cấu hình sử dụng:

```java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${introspection.uri}") String uri,
        @Value("${introspection.client-id}") String clientId,
        @Value("${introspection.client-secret}") String clientSecret) {

    OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector
                    .withIntrospectionUri(uri)
                    .clientId(clientId)
                    .clientSecret(clientSecret)
                    .build();

    return new AudienceCheckingIntrospector(delegate, "orders-api");
}
```

Ví dụ bean sử dụng builder **Spring Security 6.5+**. Nếu hệ thống đang ở 6.4 hoặc cũ hơn, thay phần tạo delegate bằng implementation được version đó hỗ trợ; **giữ nguyên interface decorator**.

### 14.1. Giới hạn quan trọng

- Nếu introspection endpoint **không trả `aud`**, một policy bắt buộc audience theo ví dụ sẽ **từ chối**. Phải thống nhất với issuer về metadata/endpoint resource-binding, không suy đoán mọi provider có `aud`.
- Nếu issuer trả `aud` với kiểu khác string/list-string, cần quy định parser/validator đúng contract; không tự chuyển object tùy ý thành chuỗi.
- `Collection.contains` không phải cơ chế authorization đầy đủ, mà chỉ là **một điều kiện resource identifier**.
- Cùng với audience, có thể cần xác minh `iss`, `client_id`, expiry, actor kind, tenant và scope theo hợp đồng.
- Nếu remote introspection service đã bảo đảm token **chỉ active đối với đúng Resource Server hiện tại** dựa trên client credentials/context, có thể không cần duplicate audience check; nhưng bảo đảm đó phải được tài liệu hóa và kiểm thử.

## 15. Custom mapping authorities: không cấp thêm quyền từ metadata lạ

Một introspection response có thể chứa scope nhưng API muốn ánh xạ một số giá trị sang authorities theo hợp đồng riêng. Có hai tầng tùy biến khác nhau:

1. Tùy biến **`OpaqueTokenIntrospector`** để kiểm tra hoặc biến đổi `OAuth2AuthenticatedPrincipal`/attributes/authorities.
2. Tùy biến **`OpaqueTokenAuthenticationConverter`** để tạo kết quả `Authentication` từ principal đã introspect, nếu version cung cấp extension point tương ứng.

Trong Spring Security 6.3+ `SpringOpaqueTokenIntrospector` có setter `setAuthenticationConverter(...)` dùng converter từ `OAuth2TokenIntrospectionClaimAccessor` sang `OAuth2AuthenticatedPrincipal`. Đừng nhầm setter này với `OpaqueTokenAuthenticationConverter` ở tầng provider: **chúng xử lý hai bước khác nhau**.

### 15.1. Mẫu decorator chỉ giữ authorities được cho phép

Nếu muốn không nhận các scope ngoài contract, có thể xây một principal mới từ principal đã introspect:

```java
OpaqueTokenIntrospector rawIntrospector = /* delegate đáng tin */;

OpaqueTokenIntrospector constrained = token -> {
    OAuth2AuthenticatedPrincipal principal =
            rawIntrospector.introspect(token);

    Set<String> allowed = Set.of(
            "SCOPE_orders:read", "SCOPE_orders:write");

    List<GrantedAuthority> authorities = principal.getAuthorities()
            .stream()
            .filter(a -> allowed.contains(a.getAuthority()))
            .toList();

    return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities);
};
```

Code là ví dụ ở mức ý tưởng và cần các imports `DefaultOAuth2AuthenticatedPrincipal`, `GrantedAuthority`, `Set`, `List`. Khi các phiên bản mới có thêm authority loại authentication-factor, việc lọc bỏ **mọi** authority không thuộc allowlist có thể ảnh hưởng security policy; hãy xác định rõ những authorities nào cần giữ/chặn và áp dụng contract theo version. Nếu mục tiêu là **từ chối token có scope sai hợp đồng**, cần ném exception thay vì chỉ lọc đi các quyền.

Đừng lấy `roles` hoặc `permissions` bất kỳ từ introspection response rồi tự cấp `ROLE_ADMIN`. Chỉ map dữ liệu từ nguồn đã được xác thực, với allowlist và chính sách cấp quyền rõ ràng.

### 15.2. Nếu vừa có scope vừa có roles

```json
{
  "active": true,
  "scope": "orders:read",
  "roles": ["ADMIN"]
}
```

Ứng dụng phải định nghĩa:

- `roles` có phải claim đáng tin cậy do issuer phát hay không?
- Role này có thuộc **orders-api** hay một ứng dụng khác?
- Nó tương ứng với authority nào, ví dụ `ROLE_ADMIN` hay `ORDER_ADMIN`?
- Có được phép kết hợp scope và role trong cùng authorization rule không?

Không nên tự hiểu `"ADMIN"` là quyền quản trị toàn hệ thống chỉ vì introspection trả về field đó. Sai lầm này là **privilege escalation do ánh xạ quyền**, không phải lỗi HTTP client hay introspection version.

## 16. Introspection với JWT: không chỉ dành cho chuỗi không đọc được

Opaque token support trong Spring Security thực chất chọn **cách xác minh token qua introspection**, không buộc chuỗi token phải thiếu dấu chấm.

Giả sử issuer phát JWT có chữ ký, nhưng doanh nghiệp yêu cầu **kiểm tra trạng thái thu hồi theo server** trước mỗi request. API có thể cấu hình:

```java
.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()))
```

rồi chuyển cả chuỗi JWT đến introspection endpoint. Khi đó:

- `JwtDecoder` không phải thành phần quyết định theo đường opaque đã chọn.
- Thông tin principal/authorities đến từ response introspection.
- Dù chuỗi token có header/payload JWT, **không tự đọc payload chưa được API xác minh** để cấp quyền.
- Nếu muốn cả xác minh chữ ký cục bộ lẫn introspection, đó là **thiết kế custom** phải xác định thứ tự, lỗi, hiệu năng và contract; không mặc định diễn ra khi bật `opaqueToken()`.

**Không dùng định dạng chuỗi token làm “bộ chọn bảo mật” dựa vào dấu chấm hoặc độ dài** nếu chưa có chính sách rõ. Khi hệ thống thật sự hỗ trợ hai cơ chế token, hãy tách theo chain/client/issuer hoặc dùng resolver được thiết kế an toàn.

## 17. Hiệu năng, revocation và cache

Với introspection không cache, mỗi request Bearer được gửi tới Authorization Server hoặc introspection service. Điều này giúp Resource Server nhìn thấy trạng thái thu hồi tương đối sớm nhưng tạo dependency runtime mới:

```text
API latency ≈ xử lý nghiệp vụ + latency introspection + chi phí mạng khác
```

Một số hệ thống có nhiều request mỗi giây có thể cân nhắc cache kết quả introspection:

| Cách làm | Lợi ích | Rủi ro |
| --- | --- | --- |
| Không cache | Revocation có thể được phản ánh ở mỗi lần gọi endpoint. | Tăng latency/tải Authorization Server, dễ bị ảnh hưởng bởi lỗi mạng. |
| Cache ngắn hạn | Giảm remote calls/latency. | Token vừa bị revoke có thể còn được chấp nhận trong khoảng TTL. |
| Cache dài hạn | Giảm tải lớn. | Làm suy yếu khả năng thu hồi nhanh, phụ thuộc expiry/profile. |
| Cache fail-open khi AS down | Có vẻ tăng availability. | **Nguy hiểm:** token chưa được xác nhận vẫn có thể được cấp quyền. |

Nếu cache, cần:

1. Giới hạn TTL theo **thời gian còn hiệu lực** của token và SLA revocation, không cache vượt `exp` nếu có.
2. Chỉ cache kết quả **active=true đã được kiểm tra đầy đủ**, và xử lý inactive/error riêng theo policy.
3. Bảo vệ cache như dữ liệu credential-sensitive; không công bố raw token làm key trong log/metrics.
4. Dùng key hash an toàn hoặc abstraction không lộ token; xét collisions, invalidation và policy version/tenant scope.
5. Tính khả năng thay đổi quyền/tenant trong thời gian cache.
6. Kiểm tra cache stampede, retry storm và downtime của introspection endpoint.

**Không có một TTL “luôn đúng” cho mọi hệ thống.** Token của giao dịch tài chính có thể yêu cầu revocation gần real-time; API ít nhạy cảm có thể chấp nhận bounded staleness theo hợp đồng.

## 18. Phân loại lỗi: token invalid khác introspection service unavailable

| Sự kiện | Ở đâu xảy ra? | Cách hiểu | Phản hồi API/điều tra |
| --- | --- | --- | --- |
| Client không gửi Bearer token | HTTP Bearer filter | Thiếu credential. | Endpoint yêu cầu auth thường **401**. |
| Introspection trả `{"active":false}` | Issuer xác minh trạng thái | Token không được chấp nhận. | Thường **401 invalid_token**. |
| Introspection trả active=true nhưng thiếu `orders:read` | Authorization | Token được nhận nhưng thiếu quyền. | Thường **403 Forbidden**. |
| Introspection trả active=true nhưng `aud` không thuộc API | Resource policy | Token không dành cho API này. | Từ chối authentication, thường 401 nếu áp dụng trong introspector. |
| Introspection endpoint trả 401 do sai client secret | Resource Server → AS | **Cấu hình credentials của Resource Server** sai. | Không tự nhận token hợp lệ; cảnh báo vận hành. |
| HTTP 503/timeout khi introspect | Dependency AS/network | Không thể xác nhận token. | Fail-closed; phân loại sự cố dịch vụ, 5xx/503 có thể phù hợp tùy handler. |
| Introspection response malformed | API/AS protocol | Không có kết quả xác thực đáng tin cậy. | Từ chối và ghi lỗi protocol có kiểm soát. |
| Token được introspect nhưng thiếu metadata bắt buộc | Contract issuer/API | Không đủ dữ liệu đánh giá quyền. | Từ chối theo policy; sửa issuer contract. |
| Resource Server đã dùng sai `jwt()` thay vì `opaqueToken()` | Security config | Nhầm cơ chế xác thực. | Xác minh chain và introspector/decoder được dùng. |

Trong production, không đưa thông điệp chi tiết như `client_secret rejected` hoặc URL nội bộ của introspection endpoint vào `WWW-Authenticate`. Client thường chỉ cần lỗi Bearer an toàn; logs nội bộ/phân loại metric giúp operator phân biệt invalid token với outage.

### 18.1. Những thứ cần theo dõi

- Introspection request count, latency percentile và timeout rate.
- Tỷ lệ `active=false`, tách khỏi HTTP 4xx/5xx của introspection endpoint.
- Lỗi xác thực credentials/TLS tới issuer.
- Cache hit/miss, TTL và mức stale theo SLA.
- Phản hồi API 401/403 theo route và nguyên nhân được chuẩn hóa.
- Hiệu ứng khi xoay introspection client secret.

Không dùng raw access token, Basic header hoặc giá trị secret làm metric labels. Những trường từ input chưa xác thực có thể gây high cardinality hoặc rò rỉ thông tin.

## 19. Kiểm thử theo phiên bản và theo lớp trách nhiệm

### 19.1. Unit test cho decorator/policy

Với `AudienceCheckingIntrospector` ở mục 14, có thể dùng một fake delegate để test policy mà không cần HTTP:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
        .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
        .OpaqueTokenIntrospector;

class AudienceCheckingIntrospectorTest {

    private OpaqueTokenIntrospector fake(String audience) {
        return token -> new DefaultOAuth2AuthenticatedPrincipal(
                "user-123",
                Map.of(
                        "sub", "user-123",
                        "aud", List.of(audience)),
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")));
    }

    @Test
    void acceptsExpectedAudience() {
        var guard = new AudienceCheckingIntrospector(
                fake("orders-api"), "orders-api");

        OAuth2AuthenticatedPrincipal principal =
                guard.introspect("test-token");

        assertEquals("user-123", principal.getName());
    }

    @Test
    void deniesOtherResourceAudience() {
        var guard = new AudienceCheckingIntrospector(
                fake("payments-api"), "orders-api");

        assertThrows(BadOpaqueTokenException.class,
                () -> guard.introspect("test-token"));
    }
}
```

Đây là unit test cho **decorator**, không chứng minh HTTP introspection endpoint hoặc xác minh client credentials. Fake delegate tự trả principal và không có logic `active=false`; lớp kiểm tra URL/response phải được test ở tầng khác.

### 19.2. HTTP client tests với mock introspection endpoint

Với `SpringOpaqueTokenIntrospector` hoặc `RestClientOpaqueTokenIntrospector` phiên bản phù hợp, cần kiểm tra:

1. Gửi POST tới **introspection URI đã cấu hình**, không theo URL do Bearer token tự khai.
2. Header `Content-Type: application/x-www-form-urlencoded` và tham số `token` đúng nguyên vẹn.
3. Client authentication đáp ứng hợp đồng và **client ID/secret có ký tự đặc biệt không bị double-encode**.
4. Response `active=true` tạo principal có attributes và scope đúng.
5. Response `active=false` bị từ chối.
6. HTTP 401 do introspection client credentials sai được phân loại khác với token inactive.
7. HTTP 429/5xx, timeouts, JSON malformed hoặc TLS failure **không tạo authenticated principal**.
8. Không để sensitive token/secret xuất hiện trong log, exception response hoặc test snapshots.

Có thể dùng **WireMock**, **MockWebServer** hoặc test HTTP server tương đương để kiểm tra wire format. Khi dùng test secrets, chỉ assert trên mock server hoặc môi trường được bảo vệ, không log giá trị thực.

### 19.3. Integration test qua Spring Security filter chain

Giả sử API có endpoint:

```java
@GetMapping("/api/orders")
List<OrderDto> orders() {
    return orderService.listVisibleOrders();
}
```

Bài test tích hợp có thể inject introspector giả lập qua `@TestConfiguration`/test bean hoặc dùng mock introspection endpoint:

```java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-active-read"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-active-no-scope"))
        .andExpect(status().isForbidden());

mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-inactive"))
        .andExpect(status().isUnauthorized());
```

Ví dụ giả định test introspector hoặc mock endpoint **thực sự** phân loại ba token trên theo kịch bản, endpoint trả 200 khi hợp lệ và Spring Security filter chain được bật. Cần bổ sung test setup/beans/service mocks theo dự án.

**Không nhầm với**:

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))));
```

`jwt()` của Spring Security Test có thể dựng Authentication giả lập và **bỏ qua `OpaqueTokenIntrospector`**. Nó hữu ích để test authorization logic nhưng không chứng minh request introspection đã được gửi hoặc xử lý `active`.

### 19.4. Ma trận tương thích phiên bản

| Hạng mục | 5.2–5.5 | 5.6–6.4 | 6.5–7.0 | 7.1+ |
| --- | --- | --- | --- | --- |
| `OpaqueTokenIntrospector` interface | Có | Có | Có | Có |
| `NimbusOpaqueTokenIntrospector` | Có | Có | Có thể còn nhưng deprecated ở 6.5 | Xem API chính xác; không chọn mặc định cho code mới |
| `SpringOpaqueTokenIntrospector` | Không dùng trước 5.6 | Có | Có | Có |
| `SpringOpaqueTokenIntrospector.Builder` | Không | Không | Có | Có |
| Constructor Spring ba string không deprecated | Không áp dụng | Có theo API từng phiên bản | Deprecated từ 6.5 | Deprecated/subject to removal theo API |
| `RestClientOpaqueTokenIntrospector` | Không | Không | Không | Có từ 7.1 |
| Test credential encoding đặc biệt | Cần | Cần | **Đặc biệt quan trọng lúc migration 7** | Cần |

Ma trận dựa trên mốc public API, không suy đoán việc implementation nào được Boot lựa chọn trong mọi minor release. Cách đáng tin nhất là kiểm tra **`spring-security-oauth2-resource-server` đã resolve**, Javadoc đúng dòng version và wire test với issuer mà ứng dụng thật sử dụng.

## 20. Một số anti-pattern cần tránh

### 20.1. Coi opaque token là JWT hỏng

Opaque token không bắt buộc có ba phần JWS. Nếu issuer phát opaque access token, dùng introspection hợp lệ; không cố Base64URL-decode string và tạo `JwtAuthenticationToken` thủ công.

### 20.2. Chỉ kiểm tra HTTP status 200 của introspection

RFC 7662 có thể trả 200 với `{"active":false}`. Chỉ success khi kết quả **active=true** và đạt policy resource/claims phù hợp.

### 20.3. Dùng client secret trên frontend

Introspection client credentials thuộc Resource Server/trusted backend. Đưa chúng vào SPA/mobile app hoặc frontend configuration có thể cho phép bên thứ ba gọi endpoint introspection trái phép.

### 20.4. Đổi từ Nimbus sang Spring rồi bỏ qua URL encoding

Constructor legacy và builder mới có semantics khác về credentials. Sau nâng cấp, sai encoding có thể khiến mọi introspection request trả HTTP 401. Kiểm tra client ID/secret dạng raw/unencoded và wire behavior.

### 20.5. Không xem phiên bản khi copy builder

`SpringOpaqueTokenIntrospector.withIntrospectionUri` là API 6.5+; `RestClientOpaqueTokenIntrospector` là 7.1+. Đừng copy code từ 7.1 vào dự án 6.3 và “sửa” bằng cách ghép JAR lệch version.

### 20.6. Trả principal khi service introspection timeout

Timeout có nghĩa **chưa xác minh được**. Không tự cấp quyền trong nhánh catch; fail-closed và xử lý availability/caching có kiểm soát.

### 20.7. Coi active=true là đủ cho mọi API

Token có thể active nhưng dành cho resource khác. Khi contract yêu cầu resource-binding, kiểm tra `aud` hoặc policy tương đương, đồng thời kiểm tra scope, tenant và ownership.

### 20.8. Dùng email/name để cấp quyền

Introspection có thể trả `email`, `name` hoặc `preferred_username`; chúng thường là metadata có thể thay đổi, không phải khóa principal bất biến. Dùng identity contract `(iss, sub)` hoặc mapping nội bộ được xác thực theo provider.

### 20.9. Gắn `.authenticated()` rồi coi endpoint đã đủ bảo vệ

`.authenticated()` kiểm tra token hợp lệ; nếu endpoint đòi `orders:read`, phải kiểm tra authority `SCOPE_orders:read` hoặc custom authorization policy.

### 20.10. Cache vô thời hạn kết quả active

Việc cache active token không giới hạn làm suy yếu revocation và expiry. Nếu cần cache, đặt TTL có ràng buộc, đo rủi ro và test các trường hợp token revoke khi đang cache.

## 21. Quy trình lựa chọn implementation cho dự án

Khi phải cấu hình opaque Resource Server hoặc nâng cấp từ tutorial cũ, có thể đi qua các quyết định sau:

```mermaid
flowchart TD
    START["Có Bearer token cần introspection"] --> V{"Dòng Spring Security?"}
    V -->|"5.2–5.5"| NIM["API legacy NimbusOpaqueTokenIntrospector"]
    V -->|"5.6–6.4"| SPR["SpringOpaqueTokenIntrospector<br/>constructor/RestOperations"]
    V -->|"6.5–7.0"| BUILDER["SpringOpaqueTokenIntrospector<br/>withIntrospectionUri builder"]
    V -->|"7.1+"| CHOICE{"Muốn RestClient?"}
    CHOICE -- "Có" --> REST["RestClientOpaqueTokenIntrospector"]
    CHOICE -- "Không / RestOperations" --> BUILDER
    NIM --> POLICY["Cấu hình credentials, active/status, resource policy"]
    SPR --> POLICY
    BUILDER --> POLICY
    REST --> POLICY
    POLICY --> TEST["Test inactive/active/error/encoding/scopes/HTTP"]
    TEST --> DEPLOY["Triển khai, monitoring, revocation SLA"]
```

Đây không phải sơ đồ “class cũ luôn hỏng” mà là hướng chọn **API có sẵn và được khuyến nghị theo phiên bản**. Nếu Spring Boot properties đã đáp ứng hoàn toàn, có thể không cần chọn class thủ công; Boot/Spring Security sẽ xử lý wiring.

### 21.1. Danh sách câu hỏi trước khi merge cấu hình

1. Dependency Spring Security Resource Server thực tế là **phiên bản nào**?
2. Dùng **Servlet** hay WebFlux? Interface đồng bộ hay reactive?
3. Issuer có hỗ trợ RFC 7662 introspection endpoint không?
4. Resource Server dùng cơ chế nào để xác thực tới endpoint: Basic, mTLS hoặc hợp đồng khác?
5. Client ID/secret đang lưu **raw** hay **encoded**?
6. Cần kiểm tra `aud` hoặc resource policy nào ngoài `active` và scope?
7. Scope được trả theo format nào và được chuyển thành authorities ra sao?
8. Có cần custom `RestOperations`, `RestClient`, timeout hoặc proxy?
9. Khi endpoint không truy cập được, API có policy fail-closed và phản hồi lỗi hạ tầng rõ không?
10. Cache token introspection có phù hợp yêu cầu revocation không?
11. Mỗi SecurityFilterChain có đang dùng đúng introspector, thay vì nhầm JWT decoder không?
12. Test đã đi qua **real Bearer filter + introspector path** chưa, hay chỉ dùng mock `jwt()`?

## 22. Tình huống thực hành

### A. Dự án Spring Security 6.3 báo không tìm thấy withIntrospectionUri

Code copy từ tài liệu 6.5+ có builder. Trong 6.3, chọn `SpringOpaqueTokenIntrospector` constructor/`RestOperations` được phiên bản hỗ trợ hoặc nâng cấp dependency đồng bộ. Không tạo một fake class cùng tên để làm code compile.

### B. Dự án 6.5 còn dùng Nimbus và có warning deprecated

Đây là cảnh báo cần kiểm tra API migration, không tự chứng minh token validation hỏng. Ưu tiên `SpringOpaqueTokenIntrospector` builder khi phù hợp, kiểm tra lại Basic credentials encoding, response active, scope và timeout với mock introspection server.

### C. Nâng cấp sang 7.0 thì introspection endpoint trả 401

Nếu JWT/opaque token của user trước đây chạy bình thường nhưng AS liên tục báo 401 khi **Resource Server gọi introspection**, kiểm tra client ID/secret, percent-encoding và double-encoding trước khi cho rằng mọi user token đều invalid.

### D. Spring Security 7.1 muốn dùng RestClient

Chọn `RestClientOpaqueTokenIntrospector` và cấu hình RestClient nếu version hỗ trợ. Giữ API code phụ thuộc `OpaqueTokenIntrospector` và kiểm thử wiring; không thay đổi cách cấp scope hoặc audience chỉ vì HTTP client thay đổi.

### E. Token là JWT nhưng phải kiểm tra revocation ngay

API có thể dùng `opaqueToken()` để introspect cả chuỗi JWT với AS. Điều này đưa quyết định token validity vào AS và thêm latency; phải thiết kế availability và cache theo SLA, không tự tin claim JWT chưa được introspect.

### F. active=true nhưng scope thiếu

Spring Security có thể xác thực token và tạo principal không có `SCOPE_orders:write`. Một endpoint cần write phải trả 403 theo authorization policy, không phải “nâng cấp” authorities trong introspector để client đi qua.

### G. active=true nhưng token thuộc API khác

Nếu metadata có `aud=["payments-api"]` trong khi API mong đợi `orders-api`, decorator hoặc policy của Resource Server nên từ chối theo hợp đồng. Không chấp nhận token chỉ vì cùng issuer và active=true.

### H. Introspection service tạm thời trả 503

Không thể xác nhận token. Resource Server không được fail-open. Hệ thống nên có timeout, alert, circuit breaker/cache theo SLA và phân loại đây là **sự cố xác thực phụ thuộc dịch vụ** thay vì tự gắn nhãn mọi token bị revoke.

## 23. Câu hỏi tự kiểm tra

**1. `OpaqueTokenIntrospector` là interface hay implementation?** Là interface mô tả `introspect(String token)` và trả `OAuth2AuthenticatedPrincipal`.

**2. `SpringOpaqueTokenIntrospector` khác `OpaqueTokenIntrospector` ở đâu?** Là một implementation cụ thể dùng HTTP introspection; code nghiệp vụ nên phụ thuộc interface.

**3. `SpringOpaqueTokenIntrospector` có từ phiên bản nào?** Theo Javadoc: Spring Security **5.6**.

**4. Builder `withIntrospectionUri` có từ khi nào?** Spring Security **6.5**; không dùng nguyên ví dụ builder trên 6.4.

**5. Khi nào constructor `SpringOpaqueTokenIntrospector(uri,id,secret)` bị deprecated?** Từ **6.5**, Javadoc khuyến nghị builder.

**6. `NimbusOpaqueTokenIntrospector` có phải API mới được khuyến nghị cho 6.5?** Không. Javadoc 6.5 đánh dấu deprecated và hướng dùng Spring implementation.

**7. `RestClientOpaqueTokenIntrospector` có từ phiên bản nào?** Từ **7.1**, dùng Spring RestClient.

**8. Builder 6.5+ cần client ID/secret raw hay percent-encoded sẵn?** Dùng **raw/unencoded**; builder xử lý encoding theo Javadoc. Tránh double encoding.

**9. Introspection endpoint trả HTTP 200 và `active=false` thì sao?** Token không được chấp nhận; HTTP status 200 chỉ nói introspection request đã được xử lý.

**10. Token active=true có tự đủ quyền gọi mọi API không?** Không. Còn phải kiểm tra resource/audience, scopes và object-level policies.

**11. Khi introspection timeout có được cấp một principal mặc định không?** Không. Phải fail-closed và xử lý sự cố dependency theo chính sách.

**12. `JwtDecoder` có tự được gọi khi cấu hình `opaqueToken()` không?** Không theo đường xác thực mặc định của opaque Resource Server; lựa chọn này dựa trên introspection, dù chuỗi token có định dạng JWT.

**13. `MockMvc jwt()` có kiểm tra introspection HTTP không?** Không. Nó có thể bypass introspector bằng authentication giả lập.

**14. Opaque token có bắt buộc là chuỗi ngẫu nhiên không có dấu chấm?** Không. Spring opaque path có thể chuyển cả JWT tới introspection endpoint; “opaque” mô tả **cách Resource Server xác minh** trong trường hợp này.

**15. Khi cache introspection thì rủi ro lớn nhất là gì?** Kết quả active cũ có thể còn được chấp nhận sau revocation hoặc thay đổi quyền; cần TTL và chính sách cache phù hợp.

## 24. Tài liệu chính thức và tiêu chuẩn

- **RFC 7662 — OAuth 2.0 Token Introspection:** https://www.rfc-editor.org/rfc/rfc7662 — `active`, request và response introspection.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** https://www.rfc-editor.org/rfc/rfc6750 — truyền Bearer credentials và lỗi `invalid_token`/`insufficient_scope`.
- **Spring Security Reference — Servlet OAuth 2.0 Resource Server Opaque Token:** https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security 6.5 API — OpaqueTokenIntrospector:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html
- **Spring Security 6.5 API — SpringOpaqueTokenIntrospector:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html
- **Spring Security 6.5 API — SpringOpaqueTokenIntrospector.Builder:** https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.Builder.html
- **Spring Security 6.5 API — NimbusOpaqueTokenIntrospector:** https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/introspection/NimbusOpaqueTokenIntrospector.html
- **Spring Security 6.5 Migration to 7 — OAuth 2.0 credential encoding:** https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html
- **Spring Security 7.1 API — RestClientOpaqueTokenIntrospector:** https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/RestClientOpaqueTokenIntrospector.html
- **Spring Security — Servlet Architecture:** https://docs.spring.io/spring-security/reference/servlet/architecture.html — `FilterChainProxy`, `SecurityFilterChain`, authentication và authorization filters.

**Kết luận:** `OpaqueTokenIntrospector` là **hợp đồng xác minh token** ổn định; `SpringOpaqueTokenIntrospector` là implementation HTTP được hỗ trợ từ Spring Security 5.6, có builder tiện lợi từ 6.5; `NimbusOpaqueTokenIntrospector` là lựa chọn legacy, deprecated trong dòng 6.5; `RestClientOpaqueTokenIntrospector` xuất hiện ở 7.1. Khi nâng cấp, phải kiểm tra **đúng dependency version, cách encode introspection client credentials, HTTP client, response `active`, resource/audience policy, scope mapping, timeout và tests**. Đổi implementation không được làm thay đổi ranh giới: **token chưa được introspect thành công và thẩm định đúng hợp đồng không thể trở thành principal được phép truy cập API**.
