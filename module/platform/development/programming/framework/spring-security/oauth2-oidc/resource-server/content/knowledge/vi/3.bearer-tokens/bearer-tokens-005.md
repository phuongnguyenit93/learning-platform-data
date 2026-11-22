# Token trong header, query hoặc form: phạm vi hỗ trợ và rủi ro khác nhau

Khi một **OAuth 2.0 Resource Server** nhận HTTP request, điều đầu tiên cần làm là tìm **bearer access token** mà client gửi đến. Ba vị trí có thể bắt gặp là:

1. Header HTTP: `Authorization: Bearer <access-token>`.
2. Phần thân request dạng `application/x-www-form-urlencoded`: tham số `access_token`.
3. Query string của URI: `?access_token=...`.

Dù cả ba cách đều được mô tả trong **RFC 6750**, chúng không có cùng mức độ an toàn, không cùng ràng buộc giao thức và không được Spring Security hỗ trợ mặc định như nhau. **Trong hệ thống hiện đại, hãy gửi bearer access token qua header `Authorization` trên kết nối HTTPS.** Đặc biệt, **RFC 9700 (OAuth 2.0 Security Best Current Practice, 2025) quy định client MUST NOT truyền access token trong URI query parameter**. Khả năng cấu hình đọc query của một framework không phải là khuyến nghị sử dụng nó.

Bài này tập trung vào **access token được client gửi tới Resource Server**, không phải việc Authorization Server trả token tại `/token`, không phải `authorization_code` trong callback đăng nhập và không phải ID token dùng để xác thực OIDC client.

## 1. Bearer token là gì, đi qua những đâu?

**Bearer** nghĩa là bên có quyền sử dụng token (người “mang” token) có thể trình token đó để truy cập tài nguyên theo giới hạn do server áp dụng. Nếu token bị lộ, bên lấy được token có thể thử sử dụng lại nó cho đến khi token hết hạn hoặc bị vô hiệu hóa, trừ khi hệ thống áp dụng các cơ chế ràng buộc người gửi bổ sung. Vì vậy **cách vận chuyển** token là một phần của mô hình bảo mật, dù nội dung token có được ký bằng JWT hay là một chuỗi opaque.

Ví dụ hệ thống:

- `login.example.com`: Authorization Server phát hành access token.
- `shop.example.com`: OAuth Client gửi request.
- `api.example.com`: Resource Server dùng Spring Security để bảo vệ `/api/orders/**`.

Luồng cơ bản:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant R as Spring Security Resource Server
    participant V as JWT Decoder / Token Introspector
    C->>R: HTTPS /api/orders + Bearer access token
    R->>R: BearerTokenResolver tìm credential trong request
    alt Có một token đúng định dạng
        R->>V: Xác thực access token
        V-->>R: Kết quả xác thực / thông tin token
        R->>R: Kiểm tra scope, audience và quyền nghiệp vụ
        R-->>C: 2xx hoặc 403
    else Thiếu hoặc sai token
        R-->>C: 401 hoặc lỗi yêu cầu phù hợp
    end
```

**Tách hai câu hỏi:** `BearerTokenResolver` quyết định *lấy chuỗi token từ đâu*; `JwtDecoder` hoặc `OpaqueTokenIntrospector` quyết định *token đó có hợp lệ hay không*. Cho phép đọc token trong form/query **không** thay đổi thuật toán xác minh JWT, issuer, audience, expiry, scope hoặc quyền truy cập tài nguyên.

## 2. RFC 6750 định nghĩa ba cách truyền token

RFC 6750 `2` mô tả ba phương thức gửi bearer access token trong request đến protected resource và yêu cầu **client MUST NOT dùng hơn một phương thức trong cùng request**.

| Tiêu chí | Header `Authorization` | Form-encoded body | URI query parameter |
|---|---|---|---|
| Dạng truyền | `Authorization: Bearer TOKEN` | Body `access_token=TOKEN` | URL `?access_token=TOKEN` |
| Quy định RFC 6750 | Client **SHOULD** dùng; Resource Server **MUST** hỗ trợ | Resource Server **MAY** hỗ trợ; chỉ dùng khi đáp ứng điều kiện | Resource Server **MAY** hỗ trợ; RFC 6750 vốn đã không khuyến nghị |
| RFC 9700 (Security BCP) | Phương án tiêu chuẩn cho bearer request | Không có lệnh cấm chung, nhưng nên tránh nếu header dùng được | Client **MUST NOT** gửi access token bằng query như RFC 6750 `2.3` |
| Spring Security Servlet mặc định | **Có** | **Không**; cần bật rõ ràng | **Không**; cần bật rõ ràng nhưng không nên dùng cho hệ thống mới |
| Method HTTP | GET/POST/PUT/PATCH/DELETE… | Phải có body với ngữ nghĩa xác định; **không dùng GET** | RFC 6750 mô tả query; `DefaultBearerTokenResolver` hiện xử lý query khi request là GET và đã bật |
| Khả năng bị lộ | Header vẫn có thể bị log sai cấu hình | Body có thể bị capture/log | URL rất dễ xuất hiện ở log, history, analytics, link, cache, referrer |
| Khuyến nghị triển khai | **Sử dụng** qua HTTPS | Chỉ cân nhắc cho tương thích có giới hạn | **Không sử dụng cho OAuth access token** |

Ở đây, **MUST**, **MUST NOT**, **SHOULD**, **MAY** mang nghĩa quy phạm trong RFC, không phải tên cấu hình Spring. Quan trọng là đọc RFC 6750 cùng tài liệu cập nhật **RFC 9700**: tài liệu cũ vẫn lưu cách truyền qua URL vì lý do lịch sử, nhưng lời khuyên bảo mật đã trở nên chặt chẽ hơn.

## 3. Cách 1 — Token trong header `Authorization`

### 3.1. Cú pháp và ví dụ HTTP

Bearer token được đặt trong **request header**:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
Accept: application/json
```

Trong thực tế có thể dùng `curl`:

```bash
curl --request GET \
  --url https://api.example.com/api/orders/42 \
  --header 'Authorization: Bearer ACCESS_TOKEN_EXAMPLE' \
  --header 'Accept: application/json'
```

Đối với client Java dùng `RestClient`, có thể đặt header theo cách có sẵn trong Spring:

```java
String accessToken = tokenService.currentAccessToken();

String body = restClient.get()
    .uri("https://api.example.com/api/orders/42")
    .headers(headers -> headers.setBearerAuth(accessToken))
    .retrieve()
    .body(String.class);
```

Ví dụ sử dụng trình duyệt hiện đại:

```javascript
const response = await fetch("https://api.example.com/api/orders/42", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken,
    Accept: "application/json"
  }
});

if (!response.ok) {
  throw new Error("Request failed: " + response.status);
}
const order = await response.json();
```

Đoạn `fetch` chỉ minh họa **cách gửi header**; việc lấy và giữ `accessToken` an toàn phụ thuộc kiến trúc client. Không đưa token thật vào source code.

### 3.2. Ưu điểm và giới hạn thực tế

**Ưu điểm:**

- Đây là phương thức Resource Server **bắt buộc hỗ trợ** theo RFC 6750 và được Spring Security hỗ trợ mặc định.
- Token không nằm trong URL; giảm đáng kể rò rỉ qua lịch sử trình duyệt, đường dẫn trong access log, bookmark, chia sẻ liên kết và phân tích lưu lượng URL.
- Header áp dụng được cho cả `GET` và các HTTP method có body; API có thể gửi JSON, multipart hoặc body kiểu khác mà không cần trộn token vào dữ liệu nghiệp vụ.
- Các middleware, gateway và thư viện HTTP phổ biến đều có cơ chế dành riêng cho bearer authentication.

**Giới hạn:** Header **không tự bảo đảm bí mật**. Token vẫn có thể lộ nếu proxy ghi toàn bộ request header, hệ thống tracing thu thập `Authorization`, client in request vào log hoặc dùng kết nối HTTP không bảo vệ. Các tầng gateway, APM, log và debugging cần loại bỏ/che giá trị `Authorization`. TLS và kiểm tra danh tính máy chủ đích vẫn bắt buộc.

### 3.3. Header Bearer không phải token trong cookie

`Authorization: Bearer ...` do client chủ động đặt. Cookie `Cookie: session=...` có thể được trình duyệt tự động gửi dựa trên domain, path và chính sách cookie, có cơ chế rủi ro/CSRF khác. Nếu ứng dụng sử dụng **BFF hoặc session cookie**, backend có thể lưu access token phía server và tự đặt `Authorization` khi gọi API. Đừng đồng nhất cookie session với việc truyền access token qua RFC 6750.

### 3.4. CORS không phải lý do chuyển sang query

Trong một SPA ở `https://shop.example.com` gọi API ở `https://api.example.com`, header `Authorization` có thể kích hoạt CORS preflight. API cần cấu hình CORS đúng origin/method/header được phép, ví dụ `Authorization` và `Content-Type` theo nhu cầu. **Không đưa token vào query để tránh preflight.** CORS là cơ chế kiểm soát khả năng đọc phản hồi từ trình duyệt; không thay thế xác thực/ủy quyền của Resource Server.

## 4. Cách 2 — Token trong form-encoded request body

### 4.1. Khi nào RFC 6750 cho phép?

Cách này gửi tham số `access_token` trong **phần thân** của HTTP request:

```http
POST /api/legacy/search HTTP/1.1
Host: api.example.com
Content-Type: application/x-www-form-urlencoded

access_token=ACCESS_TOKEN_EXAMPLE&keyword=keyboard
```

Theo RFC 6750 `2.2`, client **không được dùng form-body method nếu thiếu bất kỳ điều kiện nào sau đây**:

1. Header `Content-Type` là `application/x-www-form-urlencoded`.
2. Body được mã hóa đúng theo quy tắc `application/x-www-form-urlencoded`.
3. Body là một phần duy nhất (single-part), không phải multipart.
4. Nội dung được mã hóa trong body gồm các ký tự ASCII theo ràng buộc của RFC.
5. HTTP method có định nghĩa ngữ nghĩa cho request body; **GET không được dùng**.

Nếu body có cả thông số nghiệp vụ, các cặp `key=value` phải được mã hóa và phân tách đúng bằng `&`. Ví dụ:

```bash
curl --request POST \
  --url https://api.example.com/api/legacy/search \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'access_token=ACCESS_TOKEN_EXAMPLE' \
  --data-urlencode 'keyword=keyboard'
```

**Không áp dụng cách này cho JSON, multipart hoặc GET:**

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"access_token":"ACCESS_TOKEN_EXAMPLE","productId":123}
```

Đoạn JSON trên **không phải** form-encoded bearer transport của RFC 6750 và **không được** `DefaultBearerTokenResolver` nhận như một access token theo mặc định. Đặt `access_token` vào một trường JSON nghiệp vụ không khiến Spring Security tự xác thực request.

### 4.2. Rủi ro và tình huống tương thích

Form-body giảm rủi ro lộ qua URL nhưng **không giấu được token khỏi hệ thống đọc/log request body**. Dữ liệu có thể xuất hiện trong APM, middleware, reverse proxy, error report, debug dump, web application firewall hoặc các bản sao lưu request. Nó còn tạo sự phụ thuộc vào content type, cách parse body và cách ứng dụng sử dụng tham số form.

RFC 6750 nói phương thức này **SHOULD NOT** dùng, trừ trường hợp môi trường trình duyệt tham gia không thể truy cập header `Authorization`. Với ứng dụng hiện đại hỗ trợ `fetch`, `XMLHttpRequest` hoặc HTTP client đầy đủ, trường hợp ấy rất hiếm.

Một use case có thể gặp là **client legacy** bị ràng buộc chỉ gửi được HTML form. Nếu bắt buộc duy trì tương thích, giới hạn endpoint chấp nhận form, dùng HTTPS, che token khỏi logs, có vòng đời token ngắn, ràng buộc audience/scope và lập kế hoạch chuyển sang header.

> **Dễ nhầm:** OAuth 2.0 **token endpoint** thường dùng `application/x-www-form-urlencoded` cho các grant như `authorization_code` và `refresh_token`. Điều đó không có nghĩa **Resource Server** nên chấp nhận bearer access token qua form; đây là hai giao dịch khác nhau.

## 5. Cách 3 — Token trong URI query parameter

### 5.1. Cú pháp từng được mô tả

RFC 6750 `2.3` ghi nhận cách gửi token qua `access_token` trong query:

```http
GET /api/orders/42?access_token=ACCESS_TOKEN_EXAMPLE HTTP/1.1
Host: api.example.com
```

**Đây chỉ là ví dụ nhận diện một cách truyền cũ, không phải mẫu nên sao chép vào ứng dụng.** RFC 6750 đã cảnh báo cách này không nên dùng; **RFC 9700 `4.3.2` sau đó quy định client MUST NOT truyền access token trong URI query parameter theo RFC 6750 `2.3`**. Vì vậy một client mới phải dùng header.

### 5.2. Tại sao URL là nơi nguy hiểm?

Khi token nằm trong URL, nó rất dễ đi qua các hệ thống vốn được thiết kế để ghi hoặc chia sẻ địa chỉ:

| Nơi token có thể rò rỉ | Tình huống điển hình |
|---|---|
| **Access log của proxy / web server / API gateway** | Dòng log lưu request target `/api/orders?access_token=...`. |
| **Browser history, bookmark và autocomplete** | Người dùng mở URL từ thanh địa chỉ hoặc lưu trang. |
| **Referrer** | URL chứa token có thể bị gửi qua `Referer` trong một số điều kiện/chính sách; không dựa vào chính sách referrer để giữ bí mật token. |
| **Analytics, APM, error tracking, tracing** | Công cụ thu thập `url`, `path` hoặc query string. |
| **Cache, CDN, proxy** | Hệ thống trung gian có thể giữ URL, cache key hoặc metadata; `Cache-Control` có ích nhưng không ngăn mọi hình thức ghi nhận URL. |
| **Sao chép/chia sẻ liên kết** | Token dính vào link trong chat, ticket, email, ảnh chụp màn hình hoặc trang tài liệu. |
| **Công cụ giám sát / bảo mật** | WAF, monitoring và công cụ kiểm thử có thể ghi lại toàn bộ URI. |

**HTTPS không xóa các rủi ro này.** TLS bảo vệ dữ liệu trên đường truyền giữa các điểm kết nối phù hợp, nhưng hệ thống ở đầu cuối/TLS termination vẫn thấy URL và có thể lưu URL. Che token khỏi các header log vẫn chưa đủ nếu token đã nằm trong query.

**Không xem việc cấu hình** `Cache-Control: no-store`, `private` hoặc `Referrer-Policy` là giải pháp để hợp thức hóa query bearer token. Các kiểm soát này chỉ giảm một phần nguy cơ và không thay thế yêu cầu RFC 9700.

### 5.3. URL ký sẵn không đồng nghĩa `access_token` của OAuth

Một số hệ thống cung cấp **presigned URL**, chứa chữ ký có hạn dùng trong query cho việc tải tệp hoặc truy cập một tài nguyên cụ thể. Đó là cơ chế ủy quyền **khác**, với cấu trúc chữ ký, audience, thời hạn và mô hình rủi ro riêng. Không suy từ việc presigned URL tồn tại rằng OAuth bearer access token nên được nhúng vào `?access_token=...`.

### 5.4. Nếu hệ thống legacy đang dùng query token

Đối với hệ thống đã triển khai sai hoặc có hợp đồng tích hợp cũ, ưu tiên chuyển đổi:

1. Xác định client/endpoint đang gửi `access_token` trong query; tránh xuất giá trị token trong báo cáo kiểm kê.
2. Thay client để gửi `Authorization: Bearer ...`; hỗ trợ cấu hình CORS hoặc gateway nếu liên quan.
3. Thu hẹp quyền/audience và thời hạn access token, luân chuyển token đã có nguy cơ xuất hiện trong log.
4. Làm sạch hoặc kiểm soát quyền truy cập của log, analytics, history và cache chứa URL cũ theo chính sách dữ liệu.
5. Tắt khả năng chấp nhận query ở Resource Server và giám sát request lỗi để phát hiện client còn dùng cách cũ.

Việc một API “đang chạy được với query token” không chứng minh cách làm phù hợp với Security BCP.

## 6. Spring Security Resource Server đọc token như thế nào?

### 6.1. Mặc định chỉ tìm trong `Authorization`

Với ứng dụng **Spring MVC / Servlet**, Spring Security dùng một `BearerTokenResolver` để trích bearer credential. Triển khai mặc định là `DefaultBearerTokenResolver`, tìm header `Authorization` và **không bật** tham số form hoặc query.

Các thành phần thường tham gia:

```text
HTTP request
    |
    v
BearerTokenAuthenticationFilter
    |
    v
BearerTokenResolver (DefaultBearerTokenResolver)
    |-- Authorization: Bearer ...     -> được đọc mặc định
    |-- form body: access_token=...   -> mặc định không đọc
    |-- URI query: access_token=...   -> mặc định không đọc
    |
    v
AuthenticationManager / JWT Decoder hoặc OpaqueTokenIntrospector
    |
    v
SecurityContext + authorization rules
```

Các dependency Gradle (Groovy DSL) tối thiểu của ứng dụng Spring Boot đã được cấu hình plugin:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

Ví dụ cấu hình JWT Resource Server:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
```

`issuer-uri` cần trùng issuer được tin cậy của nhà phát hành token. Ngoài xác minh chữ ký, thời hạn và issuer, API thực tế phải xác minh **audience** được phát hành cho API này, cùng scope/chính sách truy cập. Nếu triển khai sử dụng opaque token, thay bằng cấu hình introspection phù hợp; **vị trí mang bearer token vẫn là một vấn đề riêng**.

Cấu hình bảo vệ endpoint chỉ bằng access token trong header theo mặc định:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

`SCOPE_orders.read` minh họa quyền được ánh xạ từ scope `orders.read` theo converter mặc định của JWT Resource Server. Code trên giả định ứng dụng đã cấu hình issuer/JWK metadata phù hợp và chỉ nhận access token cho API. Nếu API có trạng thái phiên/cookie hoặc nhiều security filter chain, cần cấu hình bảo mật tương ứng với kiến trúc thực tế.

### 6.2. Chỉ khi bắt buộc: cho phép `access_token` trong form

Spring cung cấp `DefaultBearerTokenResolver#setAllowFormEncodedBodyParameter(true)`. Cấu hình minh họa:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LegacyApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

        // Chỉ bật nếu thực sự phải hỗ trợ legacy form clients.
        resolver.setAllowFormEncodedBodyParameter(true);

        // Không bật query bearer token.
        resolver.setAllowUriQueryParameter(false);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/legacy/search")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(resolver)
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Đây là **một cấu hình thay thế** cho `ApiSecurityConfig` ở trên, không phải hai bean `SecurityFilterChain` nên copy nguyên vào cùng ứng dụng mà không thiết kế `securityMatcher`/thứ tự rõ ràng.

**Phạm vi cụ thể của resolver trên Servlet:**

- `setAllowFormEncodedBodyParameter` mặc định là `false`; khi bật, resolver chỉ xét body dạng `application/x-www-form-urlencoded`, không dùng cho `GET`.
- `setAllowUriQueryParameter` mặc định là `false`; trong triển khai `DefaultBearerTokenResolver` hiện hành, cách đọc query được giới hạn vào request `GET` khi bật.
- Cả hai tham số là cấu hình của **nơi trích token**, không phải cơ chế tự chuyển nội dung JSON sang form, không phải kiểm tra chữ ký và không cấp token mới.
- Header vẫn được chấp nhận theo chuẩn. Nếu request chứa bearer credential trong nhiều nguồn, resolver có thể phát hiện xung đột và từ chối như một request không hợp lệ.

**Vì sao không bật query?** `setAllowUriQueryParameter(true)` có tồn tại để phục vụ trường hợp tương thích đặc biệt, nhưng việc client truyền OAuth access token trong query trái với RFC 9700. Nên để giá trị mặc định `false` hoặc chỉ nghiên cứu đường di trú legacy; không dùng tùy chọn này trong một API mới.

### 6.3. Còn WebFlux và header tùy chỉnh?

Cấu hình trên dùng **Servlet** `DefaultBearerTokenResolver`. Với ứng dụng **Reactive WebFlux**, đường xử lý dựa trên `ServerBearerTokenAuthenticationConverter`, có API và cách cấu hình riêng; không copy nguyên `SecurityFilterChain` Servlet sang `SecurityWebFilterChain`.

Spring cũng hỗ trợ cấu hình **tên header khác** cho một số kiến trúc proxy đặc biệt bằng `setBearerTokenHeaderName`. Đó là trường hợp tùy biến ingress, không thay thế chuẩn `Authorization` cho client công khai. Cần đánh giá rõ proxy nào đặt header, có chặn header do client tự khai báo hay không và token được che khỏi log như thế nào. Tránh tạo thêm nhiều kênh nhận token không cần thiết.

## 7. Nếu client gửi hai token cùng lúc thì sao?

RFC 6750 `2` nói **mỗi request không được dùng hơn một phương thức truyền bearer token**. Không nên thiết kế “ưu tiên header, nếu không hợp lệ thì lấy token query” vì dễ tạo khác biệt giữa gateway, proxy và application, đồng thời tạo cơ hội *credential confusion*.

Ví dụ **không hợp lệ** về nguyên tắc:

```http
POST /api/legacy/search HTTP/1.1
Host: api.example.com
Authorization: Bearer TOKEN_IN_HEADER
Content-Type: application/x-www-form-urlencoded

access_token=TOKEN_IN_BODY&keyword=keyboard
```

Khi đã bật nguồn form, `DefaultBearerTokenResolver` có xử lý phát hiện nhiều bearer token và báo lỗi `invalid_request` thay vì tự chọn token. Các middleware khác cũng cần nhất quán về chỗ nào là nguồn credential đáng tin.

Các tình huống cần phân biệt:

- **Token chỉ trong header:** được parser mặc định trích và đưa vào bước xác thực.
- **Token chỉ trong form, cờ form đang tắt:** không được resolver coi là bearer credential; endpoint bảo vệ thường phản hồi không có thông tin xác thực.
- **Token chỉ trong query, cờ query đang tắt:** tương tự, query không phải credential được chấp nhận.
- **Token sai chữ ký/hết hạn:** lỗi xác thực token, không liên quan việc token đến từ header hay form.
- **Nhiều token từ các nguồn được bật:** có thể là `invalid_request`; không phải chọn token “mạnh hơn” hoặc “mới hơn”.
- **Token hợp lệ nhưng thiếu scope:** lỗi phân quyền, thường `403 Forbidden`.

Phân biệt **bị từ chối vì vị trí truyền token** và **bị từ chối vì nội dung token** giúp xử lý đúng tầng.

## 8. So sánh phản hồi HTTP và ý nghĩa lỗi

| Tình huống | HTTP thường gặp | Ý nghĩa |
|---|---|---|
| `GET` không có bearer token đến endpoint bảo vệ | `401 Unauthorized` | Client chưa cung cấp credential mà API chấp nhận. |
| `GET` chỉ có `?access_token=...` với resolver mặc định | `401 Unauthorized` | Query bị bỏ qua; không được xem là header bearer token. |
| `POST` chỉ có form `access_token=...` nhưng chưa bật hỗ trợ | `401 Unauthorized` | Form không được đọc thành bearer credential. |
| Header có bearer token hết hạn, sai chữ ký hoặc sai audience | `401 Unauthorized`, có thể kèm `invalid_token` | Credential được đọc nhưng không hợp lệ cho API. |
| Header bearer hợp lệ nhưng thiếu scope cần thiết | `403 Forbidden`, có thể kèm `insufficient_scope` | Đã xác thực nhưng chưa có đủ quyền. |
| Request đưa đồng thời bearer token vào header và form khi cả hai được bật | `400 Bad Request`, có thể kèm `invalid_request` | Vi phạm quy tắc một phương thức truyền token. |

Kết quả cụ thể phụ thuộc cấu hình `SecurityFilterChain`, exception handling, gateway và bản Spring Security. Với Resource Server mặc định, phản hồi từ cơ chế bearer authentication thường dùng header `WWW-Authenticate`, ví dụ:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Header này là phần của **phản hồi** để thông báo lỗi bearer authentication; nó không phải nơi client gửi access token. Client phải xử lý `401`/`403` theo ngữ nghĩa phù hợp, không tự “thử lại bằng query” để vượt cấu hình header.

## 9. Bảo vệ token trên toàn đường truyền

Đưa token vào header là lựa chọn tốt nhất trong ba phương thức, nhưng vẫn cần bảo vệ **toàn bộ vòng đời**:

### 9.1. Bảo vệ kênh và đích nhận

- Dùng **HTTPS** từ client đến API; bảo vệ cả các kết nối giữa proxy/gateway và backend theo kiến trúc.
- Xác minh TLS certificate và đúng hostname của API; tránh gửi token cho endpoint không tin cậy.
- Giới hạn `audience` để token dành cho API A không được API B chấp nhận. Giới hạn `scope`, lifetime và quyền dữ liệu ở mức cần thiết.
- Cân nhắc sender-constrained token như mTLS-bound access token hoặc DPoP trong môi trường đòi hỏi giảm khả năng replay; đây là cơ chế bổ sung, không phải lý do sử dụng query.

### 9.2. Kiểm soát log và giám sát

Những hệ thống nên che hoặc tránh ghi token thật:

- Client console logs, HTTP client debug/interceptors, crash report.
- API gateway, reverse proxy, WAF, load balancer.
- Application access log, tracing spans, request/response logging middleware.
- APM, monitoring, ticket support, analytics và bản ghi phát lại request.

Nên log **correlation ID**, HTTP method, route template, status, thời gian xử lý, mã lỗi và định danh chủ thể đã chuẩn hóa khi thực sự cần; không log `Authorization`, `access_token`, raw request body chứa credential hoặc toàn bộ query string.

### 9.3. Tách bảo vệ token khỏi phương thức lưu token

- **Transport:** token được gửi từ client đến API qua `Authorization`.
- **Storage:** token được giữ ở memory, phía backend, secret store hoặc phương thức phù hợp loại client và threat model.
- **Validation:** server xác minh token và quyền.
- **Revocation/rotation:** Authorization Server hoặc cơ chế khác quản lý vòng đời.

Đổi từ query sang header là một cải thiện quan trọng nhưng không tự khắc phục việc lưu token kém an toàn trong trình duyệt, token quá nhiều quyền, thiếu audience validation hay lộ token qua APM.

## 10. Tình huống triển khai và quyết định kỹ thuật

### Tình huống A — SPA gọi JSON REST API

SPA dùng `fetch` gửi JSON body và bearer header:

```http
POST /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
Content-Type: application/json

{"productId":123,"quantity":2}
```

**Chọn header.** Token nằm độc lập với dữ liệu tạo đơn hàng. Nếu cross-origin, cấu hình CORS đúng; nếu kiến trúc dùng BFF, backend có thể thực hiện request đến API với bearer header thay cho trình duyệt.

### Tình huống B — Client cũ chỉ gửi được HTML form

Một hệ thống cũ có thể chỉ gửi request `POST application/x-www-form-urlencoded`. Nếu không thể sửa client ngay, API có thể bật hỗ trợ form tạm thời cho endpoint cần thiết, giám sát chặt, che body logs và lên lịch chuyển sang header. Không biến tương thích tạm thời thành cấu hình mặc định cho tất cả API.

### Tình huống C — Gửi liên kết tải báo cáo qua email

Yêu cầu “đưa access token vào URL để người nhận chỉ việc click” là **không phù hợp** với OAuth bearer transport hiện đại. Giải pháp tốt hơn tùy sản phẩm là đưa người nhận tới trang cần đăng nhập, phát hành mã tải có mục đích/hạn dùng riêng, hoặc dùng một cơ chế presigned URL được thiết kế cho tài nguyên cụ thể. Không nhúng OAuth access token vào link.

### Tình huống D — WebSocket hoặc SSE

Một số browser API có giới hạn trong cách đặt header lúc tạo kết nối (ví dụ native `WebSocket` API). Điều này không mặc nhiên cho phép dùng OAuth `access_token` trong query theo RFC 9700. Hãy thiết kế một cơ chế xác thực thích hợp: phiên backend, cookie an toàn khi phù hợp, bước trao đổi thông tin xác thực trong giao thức ứng dụng hoặc token riêng có audience và thời hạn giới hạn theo thiết kế. Đánh giá CORS/origin, CSRF, replay và logging của giao thức cụ thể. Không trộn bearer access token với URL chỉ vì HTTP client bị giới hạn.

## 11. Bảng quyết định nhanh

| Nếu bạn đang xây… | Cách phù hợp |
|---|---|
| REST API Spring Security mới | Chỉ nhận `Authorization: Bearer ACCESS_TOKEN` qua HTTPS. |
| JSON API nhận GET/POST/PATCH/DELETE | Đưa access token trong header; giữ JSON body cho dữ liệu nghiệp vụ. |
| Client form cũ không thể gửi header | Chỉ cân nhắc `access_token` trong form body nếu đáp ứng RFC 6750 và chủ động bật hỗ trợ có kiểm soát; ưu tiên kế hoạch di trú. |
| API có `?access_token=...` do client cũ | Chuyển client sang header; không mở rộng hoặc thiết kế API mới dựa trên query. |
| Hệ thống cần cho phép chia sẻ URL tải tệp | Dùng thiết kế URL ký riêng hoặc luồng đăng nhập/ủy quyền phù hợp; không dùng OAuth bearer access token trong query. |
| Server có JWT access token | Xác minh chữ ký, issuer, audience, thời hạn và quyền **sau khi** nhận bearer header. |
| Server có opaque access token | Dùng introspection và kiểm tra quyền **sau khi** nhận bearer header. |

## 12. Tài liệu chuẩn và tài liệu Spring Security

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html), đặc biệt `2.1` (Authorization header), `2.2` (form body), `2.3` (URI query), `3` (WWW-Authenticate) và `5` (Security Considerations).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html), đặc biệt `4.3.2` (Access Token in Browser History) với yêu cầu client **MUST NOT** gửi access token trong URI query parameter.
- [Spring Security — OAuth 2.0 Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html), mô tả mặc định header và cấu hình đọc form/custom header.
- [Spring Security — DefaultBearerTokenResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html), mô tả các cờ `setAllowFormEncodedBodyParameter`, `setAllowUriQueryParameter` và giá trị mặc định của chúng.

## 13. Ghi nhớ

Ba vị trí có thể gặp trong tài liệu lịch sử là **header**, **form body** và **query string**, nhưng chúng không tương đương:

- **Header `Authorization`:** chuẩn tương tác giữa OAuth client và Resource Server; Spring Security hỗ trợ mặc định; nên dùng.
- **Form body `access_token`:** cơ chế tương thích có điều kiện, chỉ cho request form hợp lệ; Spring Security yêu cầu bật rõ ràng; cần đánh giá rủi ro body logging và hạn chế use case.
- **Query `access_token`:** có trong RFC 6750 để mô tả thực hành cũ, nhưng bị RFC 9700 cấm đối với OAuth client; Spring Security không bật mặc định và API mới không nên chấp nhận.

**Bearer token là credential nhạy cảm.** Đặt đúng trong header chỉ là lớp đầu tiên; hệ thống vẫn phải có HTTPS, redaction cho log, xác minh token đúng audience/scope, kiểm tra quyền với tài nguyên và vòng đời token phù hợp.
