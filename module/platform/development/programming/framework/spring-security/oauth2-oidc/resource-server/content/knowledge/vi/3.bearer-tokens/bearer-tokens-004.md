# Nguồn token mặc định và tùy chỉnh tên header theo hợp đồng

## 1. Bearer token được đọc từ đâu?

Trong **Spring Security OAuth 2.0 Resource Server**, một yêu cầu truy cập API thường mang access token qua header HTTP:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOi...
~~~

Resource Server cần tìm chuỗi access token trong request trước khi kiểm tra JWT signature, thời hạn, issuer, audience và quyền truy cập. Thành phần thực hiện việc tìm chuỗi token được gọi là **BearerTokenResolver**.

Mặc định, Spring Security đọc từ **`Authorization: Bearer <access_token>`**. Đây cũng là cách chuyển Bearer token phổ biến theo RFC 6750. Một số hệ thống tích hợp lại có hợp đồng nhận token từ header riêng:

~~~http
X-Access-Token: Bearer <access_token>
~~~

Khi đó, cấu hình có thể đổi **tên header được đọc** để phù hợp với client hoặc API gateway. Cần phân biệt:

- **Nguồn token:** HTTP header, form body hoặc query parameter.
- **Định dạng giá trị:** có tiền tố `Bearer ` hay một chuỗi token thô?
- **Kiểm tra token:** token thực sự được phát hành cho API này, còn hạn và có quyền hay không?

Đổi tên header tác động lên nguồn token; nó không làm thay đổi những kiểm tra tin cậy của access token.

## 2. Hành vi mặc định của Spring Security

### 2.1. Cấu hình Resource Server cơ bản

Ví dụ Spring Boot sử dụng Spring MVC và JWT access token:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

URI trên chỉ là ví dụ; cần thay bằng issuer thực tế mà ứng dụng tin cậy.

Security configuration:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );
        return http.build();
    }
}
~~~

Ví dụ này để Spring Security sử dụng resolver mặc định. Client gọi:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Không cần tự đọc `request.getHeader("Authorization")` trong controller; filter Spring Security xử lý chuỗi token trước khi request đi vào nghiệp vụ.

### 2.2. Các thành phần tham gia

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenResolver"]
    C --> D{"Có bearer token?"}
    D -->|Không| E["Tiếp tục chuỗi filter; endpoint bảo vệ yêu cầu xác thực"]
    D -->|Có| F["AuthenticationManager"]
    F --> G["JwtDecoder hoặc OpaqueTokenIntrospector"]
    G --> H{"Token hợp lệ?"}
    H -->|Không| I["401 Unauthorized"]
    H -->|Có| J["Authentication trong SecurityContext"]
    J --> K["Kiểm tra scope/authority và quyền nghiệp vụ"]
    K --> L{"Được phép?"}
    L -->|Không| M["403 Forbidden"]
    L -->|Có| N["Controller xử lý"]
~~~

`BearerTokenResolver` chỉ **trích xuất** token. `JwtDecoder` hoặc thành phần xác thực opaque token mới quyết định token có đáng tin. Authorization rules còn quyết định request đã xác thực có được phép gọi tài nguyên hay không.

### 2.3. `DefaultBearerTokenResolver`

`DefaultBearerTokenResolver` là implementation mặc định dựa trên RFC 6750. Nó:

1. Tìm giá trị từ header `Authorization`.
2. Nhận giá trị theo scheme `Bearer`, rồi tách lấy phần token.
3. Trả về `null` nếu không có token Bearer ở nguồn đang kiểm tra.
4. Không mặc định đọc access token từ query parameter `access_token`.
5. Không mặc định đọc access token từ body form-encoded `access_token`.

Ví dụ:

| Request | Resolver mặc định |
|---|---|
| `Authorization: Bearer abc.def.ghi` | Trích xuất `abc.def.ghi` để xác thực |
| `Authorization: Basic abcdef` | Không xem là Bearer token |
| `X-Access-Token: Bearer abc.def.ghi` | Không đọc header riêng |
| `Authorization: abc.def.ghi` | Không đáp ứng định dạng Bearer |
| `GET /api/orders?access_token=abc` | Không chấp nhận token qua URL theo mặc định |

**Đọc được chuỗi token không đồng nghĩa với xác thực thành công.** Ví dụ `abc.def.ghi` có thể là token giả, hết hạn hoặc không đúng issuer.

## 3. Đổi tên header theo hợp đồng tích hợp

Giả sử client bắt buộc dùng:

~~~http
GET /api/orders HTTP/1.1
X-Access-Token: Bearer eyJhbGciOi...
~~~

Đây là hợp đồng thay **tên header**, còn giá trị vẫn mang scheme **Bearer**. Spring Security hỗ trợ trực tiếp bằng `DefaultBearerTokenResolver#setBearerTokenHeaderName`.

### 3.1. Cấu hình Java

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();

        // Hợp đồng: X-Access-Token: Bearer <access_token>
        resolver.setBearerTokenHeaderName("X-Access-Token");

        return resolver;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Việc truyền resolver vào DSL thể hiện rõ filter chain dùng header nào. Điều này đặc biệt hữu ích nếu ứng dụng có nhiều `SecurityFilterChain` cho những đường dẫn có cách xác thực khác nhau.

**Lưu ý quan trọng:** `setBearerTokenHeaderName("X-Access-Token")` chỉ đổi tên header được đọc; nó **vẫn yêu cầu giá trị kiểu `Bearer <token>`**. Ví dụ:

~~~http
X-Access-Token: eyJhbGciOi...
~~~

không phù hợp với resolver ở trên vì thiếu scheme `Bearer`.

Với resolver đã đổi tên, đừng giả định nó tự đọc `Authorization` làm phương án dự phòng. Nếu client vẫn gửi `Authorization: Bearer ...`, endpoint bảo vệ thường trả 401 vì token không xuất hiện tại nguồn mới được cấu hình.

### 3.2. Tên header dưới dạng cấu hình triển khai

Khi tên header phụ thuộc hợp đồng môi trường, có thể tạo property ứng dụng riêng:

~~~yaml
app:
  security:
    bearer-header: X-Access-Token

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

`app.security.bearer-header` là **property do dự án tự định nghĩa**, không phải một property mà Spring tự động dùng để đổi resolver.

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            @Value("${app.security.bearer-header}") String headerName)
            throws Exception {

        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
        resolver.setBearerTokenHeaderName(headerName);

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(resolver)
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Hai cách cấu hình `@Bean BearerTokenResolver` và khai báo resolver trực tiếp bên trong `SecurityFilterChain` là những lựa chọn độc lập; ứng dụng chỉ cần chọn một cách phù hợp kiến trúc. Mục tiêu là truyền đúng instance resolver vào filter chain cần bảo vệ.

Tên header HTTP không phân biệt chữ hoa và chữ thường, nhưng tài liệu tích hợp nên dùng một cách viết chuẩn để hai phía triển khai nhất quán.

### 3.3. Ví dụ `Proxy-Authorization`

Spring Security có ví dụ sử dụng hằng HTTP:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
~~~

Request phù hợp:

~~~http
Proxy-Authorization: Bearer <ACCESS_TOKEN>
~~~

`Proxy-Authorization` có ngữ nghĩa riêng liên quan đến proxy trong HTTP, vì vậy chỉ chọn nó khi hợp đồng giữa gateway/proxy và backend thực sự yêu cầu. Các proxy trung gian có thể xử lý header này khác header ứng dụng thông thường.

## 4. Header riêng có token thô: một hợp đồng khác

So sánh:

~~~http
X-Access-Token: Bearer eyJhbGciOi...
~~~

và:

~~~http
X-Access-Token: eyJhbGciOi...
~~~

Trường hợp đầu: thay tên header bằng `DefaultBearerTokenResolver#setBearerTokenHeaderName`.

Trường hợp thứ hai: **không có scheme Bearer**. Trong một số tích hợp với provider/gateway gửi giá trị token hoặc identity assertion thô trong custom header, Spring Security cung cấp `HeaderBearerTokenResolver`:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.HeaderBearerTokenResolver;

// Header theo hợp đồng chứa trực tiếp JWT, không có tiền tố Bearer.
BearerTokenResolver resolver =
    new HeaderBearerTokenResolver("X-JWT-Assertion");
~~~

Resolver này lấy giá trị của header riêng làm giá trị để xử lý xác thực. Nó không tự chứng minh header do gateway đáng tin cậy tạo ra. Nếu provider gửi identity assertion không phải access token dành cho API, hệ thống còn phải xác định rõ cơ chế xác thực, loại token và trust boundary trước khi dùng.

**Không chuyển sang đọc token thô chỉ để né lỗi client gửi thiếu `Bearer`.** Sửa client theo hợp đồng là hướng ưu tiên. Nếu hợp đồng thực sự yêu cầu token thô, hãy đặc tả rõ ai được quyền đặt header, định dạng, issuer, audience, TTL và cách ứng dụng xác thực.

## 5. Không nhầm đổi tên header với bật nguồn query/form

Ngoài HTTP header, `DefaultBearerTokenResolver` có hai tùy chọn liên quan transport:

### 5.1. Form-encoded body parameter

~~~java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(true);
~~~

Cách này có thể đọc `access_token` trong request form-encoded ở những điều kiện hỗ trợ:

~~~http
POST /api/process HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=<ACCESS_TOKEN>&action=check
~~~

Tùy chọn này **mặc định là `false`**. Chỉ bật nếu yêu cầu tương thích thực sự bắt buộc; token trong body có thể bị ghi vào log payload hoặc bị xử lý không phù hợp ở hạ tầng.

### 5.2. URI query parameter

~~~java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowUriQueryParameter(true);
~~~

Ví dụ URL:

~~~http
GET /api/orders?access_token=<ACCESS_TOKEN> HTTP/1.1
~~~

Tùy chọn này cũng **mặc định là `false`**. RFC 6750 khuyến cáo hạn chế cách truyền qua URI: URL có thể xuất hiện trong browser history, proxy logs, access logs, monitoring, analytics hoặc bị chia sẻ ngoài ý muốn.

Nếu chỉ cần đổi header từ `Authorization` sang `X-Access-Token`, hãy **giữ cả hai tùy chọn form/query ở giá trị mặc định**. Thay tên header không đòi hỏi mở thêm nguồn token.

### 5.3. Tránh nhiều nguồn nhập token mơ hồ

Một request có token trong header và URL/form sẽ tạo vấn đề: hệ thống nên tin giá trị nào? `DefaultBearerTokenResolver` có xử lý một số trường hợp token xuất hiện ở nhiều nguồn khi bật nhận query/form, nhưng thiết kế API nên chọn **một nguồn token rõ ràng**. Không xây fallback tùy ý từ header cũ sang header mới khi chưa quy định chính sách kiểm soát và thứ tự ưu tiên.

## 6. Cấu hình header độc lập với JWT và phân quyền

Một access token được trích xuất thành công chưa chắc được phép sử dụng.

Ví dụ token có:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "aud": ["inventory-api"],
  "scope": "items.read",
  "exp": 2000000000
}
~~~

Đây là payload minh họa, không phải JWT đã ký. Giả sử Orders API chỉ chấp nhận token có `aud` chứa `orders-api`, token trên phải bị từ chối dù nó nằm đúng header và có chữ ký hợp lệ của cùng issuer.

Các bước xử lý nên phân biệt:

| Tầng | Câu hỏi | Thành phần tiêu biểu |
|---|---|---|
| Token resolution | Token đang nằm trong header nào và đúng scheme chưa? | `BearerTokenResolver` |
| Authentication | Token có hợp lệ, đúng issuer, audience, hạn, chữ ký hoặc introspection không? | `JwtDecoder` / opaque token introspector |
| Authorization | Chủ thể có authority/scope và quyền tài nguyên cần thiết không? | `authorizeHttpRequests` và nghiệp vụ |

Một endpoint có thể yêu cầu scope như sau:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

Import thêm `org.springframework.http.HttpMethod` khi sử dụng đoạn trên. Với JWT và claim scope được hỗ trợ, Spring Security mặc định ánh xạ `orders.read` thành authority `SCOPE_orders.read`.

Khi token là **opaque token**, resolver vẫn có thể đọc cùng header, còn Resource Server sử dụng `opaqueToken(...)` và introspection thay cho `jwt(...)`. Định dạng header và cách xác thực chuỗi token là hai quyết định khác nhau.

## 7. Minh họa hợp đồng với API Gateway

Một kiến trúc có thể dùng quy ước:

~~~mermaid
sequenceDiagram
    participant Client as Web / Mobile Client
    participant Gateway as API Gateway
    participant API as Spring Resource Server
    Client->>Gateway: Authorization: Bearer access_token
    Gateway->>API: X-Access-Token: Bearer access_token
    API->>API: BearerTokenResolver đọc X-Access-Token
    API->>API: Xác thực access token và phân quyền
    API-->>Gateway: HTTP response
    Gateway-->>Client: HTTP response
~~~

Sơ đồ chỉ là **ví dụ một hợp đồng chuyển header**. Trong nhiều hệ thống, gateway có thể giữ nguyên `Authorization`; không cần đổi tên nếu không có yêu cầu.

Đối với custom header do gateway đặt, cần đặc tả:

- **Đường vào:** client gửi header nào, gateway nhận và chuyển đổi ra sao.
- **Đường ra:** backend chỉ đọc header nào, có hỗ trợ phiên bản cũ không.
- **Nguồn đáng tin:** gateway có xóa giá trị custom header do client bên ngoài tự gửi trước khi đặt giá trị nội bộ không.
- **Đường mạng:** backend có thể bị gọi trực tiếp để bypass gateway không.
- **Xác thực:** gateway, backend hoặc cả hai thực hiện các kiểm tra token gì.
- **Ghi log:** các header chứa token có được che/mask khỏi log và telemetry không.

Đổi tên header **không mã hóa token** và không tự tạo thêm bảo mật. Cần TLS cho các đường truyền phù hợp, giới hạn quyền truy cập mạng, xử lý header nội bộ đúng chính sách và tránh phát tán token trong log.

Đặc biệt, một header tên `X-Access-Token` không tự chứng minh request đến từ gateway. Nếu backend tin header do gateway tạo, hạ tầng phải bảo đảm client không tự chèn giá trị giả và gọi thẳng backend để vượt kiểm soát.

## 8. Ví dụ gọi API và diễn giải kết quả

Giả sử Orders API có cấu hình `X-Access-Token` dạng `Bearer <token>` và bảo vệ endpoint `GET /api/orders`.

### Trường hợp A: đúng nguồn và đúng cú pháp

~~~bash
curl -i \
  -H "X-Access-Token: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Resolver lấy token; hệ thống kiểm tra tính hợp lệ và quyền. Có thể trả `200 OK` nếu mọi bước thành công.

### Trường hợp B: gửi theo header cũ

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Nếu filter chain chỉ đọc `X-Access-Token` và không có cơ chế xác thực khác, endpoint bảo vệ thường trả **401 Unauthorized** vì không lấy được token.

### Trường hợp C: thiếu scheme

~~~bash
curl -i \
  -H "X-Access-Token: <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

`DefaultBearerTokenResolver` không nhận đây là Bearer header theo quy tắc đã cấu hình. Endpoint được bảo vệ thường trả **401**.

### Trường hợp D: sai token

~~~bash
curl -i \
  -H "X-Access-Token: Bearer invalid.token.value" \
  https://api.example.test/api/orders
~~~

Resolver có thể lấy chuỗi nhưng bước JWT validation từ chối nó; thông thường là **401**.

### Trường hợp E: hợp lệ nhưng thiếu scope

Token đã xác thực thành công nhưng không có `SCOPE_orders.read` cho endpoint yêu cầu quyền đó thì thông thường là **403 Forbidden**.

Bảng kết quả:

| Request | Resolver `X-Access-Token` | Kết quả dự kiến |
|---|---|---|
| `X-Access-Token: Bearer <valid_access_token>` | Có token | 200 nếu đủ quyền, ngược lại 403 |
| `Authorization: Bearer <valid_access_token>` | Không đọc header cũ | 401 nếu không có xác thực khác |
| `X-Access-Token: <token>` | Không khớp cú pháp Bearer | 401 |
| Không có header token | Không có token | 401 |
| `X-Access-Token: Bearer <expired_token>` | Có token nhưng hết hạn | 401 |
| `X-Access-Token: Bearer <token_with_wrong_audience>` | Có token nhưng không dành cho API | 401 nếu đã cấu hình audience validation |

Bảng giả định endpoint thực sự yêu cầu xác thực và hệ thống dùng xử lý lỗi Resource Server thông thường; gateway, filter riêng hoặc nghiệp vụ có thể thêm điều kiện và thông báo lỗi.

## 9. Những sai lầm thường gặp

### 9.1. Tưởng đổi tên header sẽ làm resolver đọc JWT thô

`setBearerTokenHeaderName` chỉ đổi tên header, **không loại bỏ tiền tố `Bearer`**. Nếu giá trị hợp đồng không có scheme, phải xử lý đúng định dạng từ đầu, không âm thầm chấp nhận mọi chuỗi.

### 9.2. Tự đọc token trong controller rồi quyết định quyền

~~~java
String token = request.getHeader("X-Access-Token");
~~~

Đoạn code chỉ đọc input. Nó không thay thế chữ ký, issuer/audience, kiểm tra hết hạn, authority và chính sách dữ liệu. Cấu hình nguồn qua `BearerTokenResolver` để Spring Security tạo principal đã xác thực trước khi controller được gọi.

### 9.3. Nhầm ID Token với access token

OIDC **ID Token** dùng để OIDC client xác nhận danh tính đăng nhập. Resource Server cần **OAuth 2.0 access token dành cho API**. Đổi header nhận ID Token không biến ID Token thành access token có thể dùng cho API.

### 9.4. Chỉ kiểm tra resolver mà quên audience

Một JWT có chữ ký đúng nhưng cấp cho dịch vụ khác vẫn không nên được chấp nhận ở API này. Cần validator audience và các kiểm tra token phù hợp; tên header không giải quyết vấn đề này.

### 9.5. Cho mọi client dùng nhiều header theo cơ chế fallback

Một số client gửi `Authorization`, số khác gửi `X-Access-Token`. Nếu cần migration, hãy định nghĩa chính xác thời hạn, điểm nhận, ưu tiên và hành vi khi request chứa cả hai; tránh fallback tùy tiện làm mơ hồ nguồn tin cậy.

### 9.6. Quên đổi cấu hình ở gateway hoặc client

Nếu backend chuyển sang `X-Access-Token` nhưng gateway vẫn chuyển `Authorization` thì backend sẽ không nhìn thấy token. Hợp đồng vận chuyển phải được thay đổi nhất quán ở cả hai đầu.

## 10. Ví dụ áp dụng nhanh theo hợp đồng cụ thể

Hợp đồng mới:

~~~text
Endpoint: GET /api/orders
Header:   X-Partner-Authorization
Value:    Bearer <access_token>
~~~

Resolver tương ứng:

~~~java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setBearerTokenHeaderName("X-Partner-Authorization");

http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(resolver)
    .jwt(Customizer.withDefaults())
);
~~~

Client gửi:

~~~http
GET /api/orders HTTP/1.1
X-Partner-Authorization: Bearer eyJhbGciOi...
~~~

Cần bảo đảm access token do issuer đáng tin phát hành, dành cho Orders API, còn hạn và có quyền `orders.read`. Các đặc điểm của token này không thay đổi chỉ vì header khác tên.

Nếu hợp đồng lại là `X-Partner-Authorization: <jwt-thô>`, câu hỏi cấu hình khác nằm ở **cú pháp giá trị header**; có thể cần `HeaderBearerTokenResolver` và chính sách tin cậy bổ sung.

## 11. Ghi nhớ

- Mặc định Spring Security Servlet Resource Server tìm token từ **`Authorization: Bearer <access_token>`**.
- `DefaultBearerTokenResolver#setBearerTokenHeaderName(...)` thay đổi **header được đọc**, vẫn sử dụng scheme Bearer.
- Với hợp đồng chứa token thô trong custom header, cần giải pháp phù hợp như `HeaderBearerTokenResolver` và xác định rõ ranh giới tin cậy.
- Tham số body và query để truyền token **không được bật mặc định**; tránh sử dụng nếu không có yêu cầu thực sự cần thiết.
- Trích xuất token, xác thực token và phân quyền là những bước độc lập.
- Với API OAuth 2.0 thông thường, nên giữ `Authorization: Bearer ...` vì tương thích tiêu chuẩn; chỉ đổi header khi hợp đồng tích hợp yêu cầu rõ ràng.

### Tài liệu tham khảo

- [Spring Security — OAuth 2.0 Resource Server Bearer Tokens (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html)
- [Spring Security API — HeaderBearerTokenResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/HeaderBearerTokenResolver.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)

