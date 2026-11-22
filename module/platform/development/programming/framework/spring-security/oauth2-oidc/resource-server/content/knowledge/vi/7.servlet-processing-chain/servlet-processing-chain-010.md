# Đường đi khi không có token, token sai hoặc quyền không đủ

## 1. Cùng một endpoint, ba nguyên nhân bị từ chối khác nhau

Một API Spring Boot được cấu hình làm **OAuth 2.0 Resource Server** có thể nhận ba loại request đến cùng endpoint:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer invalid.jwt.value
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <VALID_ACCESS_TOKEN_WITHOUT_ORDERS_READ>
~~~

Nếu `GET /api/orders` yêu cầu scope `orders.read`, ba request có thể đều bị từ chối, nhưng **lý do và đường đi qua Spring Security Servlet filter chain không giống nhau**:

1. **Không có token:** chưa có bằng chứng xác thực; Bearer filter thường tiếp tục chuỗi, sau đó authorization không cho truy cập endpoint bảo vệ.
2. **Có token nhưng token không hợp lệ:** Bearer filter trích xuất token và gọi cơ chế xác thực; quá trình xác thực thất bại và thường trả lỗi ngay tại nhánh Bearer authentication.
3. **Token hợp lệ nhưng thiếu quyền:** xác thực thành công và tạo `Authentication`; sau đó quy tắc authorization từ chối truy cập.

Với các xử lý thông thường của Spring Security Resource Server, hai trường hợp đầu thường dẫn đến **401 Unauthorized**, trường hợp thứ ba thường dẫn đến **403 Forbidden**. Tuy nhiên, request sai cú pháp Bearer theo RFC 6750 có thể dẫn tới **400 Bad Request**, và endpoint công khai có thể cho request không token đi tiếp.

**Mục tiêu bài học:** theo dõi chính xác request trong **Servlet stack**, phân biệt `BearerTokenAuthenticationFilter` với `AuthorizationFilter`, hiểu vai trò `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler`, rồi áp dụng để chẩn đoán 400/401/403.

## 2. Mô hình Servlet security filter chain

Spring Security không đợi controller tự tìm token. Việc kiểm soát diễn ra trước Spring MVC controller.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet container"]
    B --> C["DelegatingFilterProxy"]
    C --> D["FilterChainProxy"]
    D --> E["Chọn SecurityFilterChain khớp đầu tiên"]
    E --> F["SecurityContextHolderFilter và các filter hỗ trợ"]
    F --> G["BearerTokenAuthenticationFilter"]
    G --> H["Các filter bảo mật phía sau"]
    H --> I["ExceptionTranslationFilter"]
    I --> J["AuthorizationFilter"]
    J --> K["DispatcherServlet / Controller nếu được phép"]
~~~

Sơ đồ thể hiện **những mốc xử lý liên quan**, không phải danh sách filter cố định hoặc đầy đủ cho mọi cấu hình. Ví dụ ứng dụng còn có thể có CORS, CSRF, logout, request cache, custom filters và filter cho hình thức đăng nhập khác.

Các thành phần chính:

| Thành phần | Nhiệm vụ trong luồng |
|---|---|
| `DelegatingFilterProxy` | Chuyển lời gọi từ Servlet container vào Spring Security bean |
| `FilterChainProxy` | Chọn `SecurityFilterChain` đầu tiên phù hợp request |
| `SecurityFilterChain` | Xác định các security filters sẽ chạy cho request |
| `SecurityContextHolderFilter` | Chuẩn bị/quản lý SecurityContext cho vòng đời request |
| `BearerTokenAuthenticationFilter` | Tìm Bearer token và yêu cầu xác thực token nếu token được cung cấp |
| `BearerTokenResolver` | Trích xuất token từ request (mặc định `Authorization: Bearer ...`) |
| `AuthenticationManager` | Chuyển authentication request tới provider phù hợp |
| `JwtAuthenticationProvider` | Xác thực JWT bằng `JwtDecoder` và tạo authentication |
| `OpaqueTokenAuthenticationProvider` | Xác thực opaque token bằng introspection |
| `AnonymousAuthenticationFilter` | Cung cấp anonymous authentication khi chưa có principal, nếu được bật |
| `ExceptionTranslationFilter` | Chuyển lỗi xác thực/phân quyền từ phần chuỗi phía sau nó thành response thích hợp |
| `AuthorizationFilter` | Quyết định cho phép/từ chối request theo `AuthorizationManager` |

**Mấu chốt:** `BearerTokenAuthenticationFilter` xử lý **authentication** của Bearer token; `AuthorizationFilter` thực hiện **authorization**. `ExceptionTranslationFilter` hỗ trợ xử lý ngoại lệ từ phần chuỗi phía sau, nhưng không phải là nơi bắt duy nhất cho mọi lỗi Bearer authentication.

### 2.1. Điều kiện tiên quyết: đúng SecurityFilterChain

Nếu một ứng dụng có nhiều `SecurityFilterChain`, `FilterChainProxy` chọn **chain đầu tiên khớp request**. Nếu request rơi vào chain không bật Resource Server thì Bearer token có thể không được xử lý như kỳ vọng.

Ví dụ:

~~~java
http.securityMatcher("/api/**");
~~~

có nghĩa chuỗi này chỉ áp dụng cho các request phù hợp `/api/**`. Còn:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

là các **quy tắc quyền** sau khi chain đã được chọn.

Vì vậy, khi phân tích một response 401/403, phải xác định **request đã vào chain nào** trước khi kết luận có vấn đề với JWT.

## 3. Cấu hình ví dụ thống nhất cho các tình huống

Giả định có Orders API với các quy tắc:

- `GET /api/orders` cần `orders.read`.
- `POST /api/orders` cần `orders.write`.
- `GET /api/public/ping` được truy cập mà không cần đăng nhập.
- Resource Server xác thực **JWT access token** phát hành bởi một issuer tin cậy.
- API sử dụng Bearer token ở header `Authorization`.

### 3.1. Dependencies

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

### 3.2. Cấu hình issuer

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

Đây là issuer **minh họa**. Khi chạy thực tế phải lấy issuer chính xác của Authorization Server, cấu hình khóa xác minh JWT phù hợp và kiểm tra `aud` của access token theo hợp đồng Orders API.

Khi ứng dụng sử dụng `issuer-uri`, Spring Security có thể dùng metadata của issuer để xác định bộ public key/JWKS. Không được hiểu rằng cấu hình này tự bảo đảm mọi access token đều dành cho Orders API: **audience validation cần được áp dụng theo API** nếu mặc định chưa có.

### 3.3. SecurityFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            // Chỉ phù hợp với API thực sự xác thực bằng Bearer token
            // ngoài cookie, không dùng cookie/session đăng nhập.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/orders", "/api/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/orders", "/api/orders/**"
                ).hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Dòng `oauth2ResourceServer(...jwt(...))` kích hoạt cơ chế xác thực JWT Bearer token cho chain này. Không cần đăng ký `BearerTokenAuthenticationFilter` thủ công.

**Giới hạn ví dụ:** `SecurityFilterChain` ở trên chỉ khớp `/api/**`. Ứng dụng thực tế cần bảo đảm những đường dẫn khác cũng có chính sách bảo vệ phù hợp, bằng một chain khác hoặc chain mặc định. Nếu request không khớp bất kỳ chain nào, Spring Security sẽ không áp dụng các filter bảo mật của nó cho request đó.

### 3.4. Quy ước HTTP và principal

Client gửi:

~~~bash
curl -i \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  https://api.example.test/api/orders
~~~

Spring Security trích xuất chuỗi token từ header, xác thực và ánh xạ scope thành authority. Theo cấu hình phổ biến, scope `orders.read` tạo authority `SCOPE_orders.read`; vì thế `hasAuthority("SCOPE_orders.read")` kiểm tra được quyền.

Giả định token hợp lệ có các claim minh họa:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "scope": "orders.read"
}
~~~

Đây chỉ là **payload JSON minh họa**, không phải JWT đã ký thật.

## 4. Nhánh thứ nhất: request không có Bearer token

### 4.1. Không có token thì Bearer filter làm gì?

Request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
~~~

Đường đi thường gặp:

~~~mermaid
sequenceDiagram
    participant Client
    participant Bearer as BearerTokenAuthenticationFilter
    participant Resolver as BearerTokenResolver
    participant Anonymous as AnonymousAuthenticationFilter
    participant Authorization as AuthorizationFilter
    participant Exception as ExceptionTranslationFilter
    participant Entry as AuthenticationEntryPoint

    Client->>Bearer: GET /api/orders (không token)
    Bearer->>Resolver: resolve(request)
    Resolver-->>Bearer: null
    Bearer->>Anonymous: tiếp tục filter chain
    Anonymous->>Authorization: anonymous principal (nếu bật)
    Authorization-->>Exception: AccessDeniedException
    Exception->>Entry: commence(request, response, exception)
    Entry-->>Client: 401 + WWW-Authenticate: Bearer
~~~

Một số filter trong sơ đồ đã được gộp để tập trung vào nhánh nghiệp vụ. Trong thứ tự thực tế, `ExceptionTranslationFilter` nằm trước `AuthorizationFilter` và bắt ngoại lệ được ném ở phần filter chain tiếp theo. `AnonymousAuthenticationFilter` thường chạy trước hai thành phần đó.

**Chi tiết cần nhớ:** `BearerTokenAuthenticationFilter` **không nhất thiết ném lỗi** chỉ vì không thấy token. Nó thường gọi tiếp `FilterChain.doFilter(...)`. Chính rule `hasAuthority(...)` hoặc `authenticated()` ở giai đoạn authorization mới khiến request vô danh không được vào endpoint bảo vệ.

### 4.2. `AnonymousAuthenticationFilter` có nghĩa là đã đăng nhập không?

Không. Filter này có thể đặt một `AnonymousAuthenticationToken` để hệ thống có một representation nhất quán cho request chưa xác thực. Token anonymous này **không được xem như người dùng đã đăng nhập** khi kiểm tra `authenticated()`.

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/orders/**").authenticated()
);
~~~

Request không token đến `/api/orders/42` không đáp ứng `authenticated()` mặc dù có thể thấy một anonymous principal trong `SecurityContext`.

Tự kiểm tra `authentication != null` rồi xem đó là đăng nhập hợp lệ có thể sai khi anonymous authentication được bật. Hãy dùng cấu hình authorization của Spring Security hoặc `AuthenticationTrustResolver` phù hợp.

### 4.3. Vì sao không token thường là 401?

Khi authorization từ chối một request chưa được xác thực đầy đủ, `ExceptionTranslationFilter` có thể xác định request đang vô danh và gọi **`AuthenticationEntryPoint`** để bắt đầu yêu cầu xác thực.

Với Resource Server Bearer, entry point thông thường là `BearerTokenAuthenticationEntryPoint`. Response có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Đối với trường hợp chỉ đơn giản **chưa gửi token**, RFC 6750 khuyến nghị không cung cấp mã lỗi như `invalid_token` trong challenge. Vì vậy không nên mặc định mọi 401 đều có `error="invalid_token"`.

### 4.4. Không token nhưng endpoint `permitAll`

Request:

~~~http
GET /api/public/ping HTTP/1.1
Host: api.example.test
~~~

Với rule `permitAll()`, request không có Bearer token có thể đi thẳng tới controller và nhận `200 OK`. Việc có `BearerTokenAuthenticationFilter` trong chain không đồng nghĩa **mọi endpoint trong chain phải có token**.

Đó là lý do API có thể cùng sử dụng một filter chain cho cả endpoint công khai lẫn endpoint yêu cầu scope: **filter authentication có thể chạy, còn policy authorization tùy từng endpoint**.

## 5. Nhánh thứ hai: token có mặt nhưng không hợp lệ

### 5.1. Token sai và không token đi hai nhánh khác nhau

Request:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer invalid.jwt.value
~~~

`BearerTokenResolver` có thể trích xuất chuỗi `invalid.jwt.value` vì header có dạng Bearer. Filter sau đó thực hiện:

~~~text
BearerTokenAuthenticationFilter
    |
    v
BearerTokenResolver -> "invalid.jwt.value"
    |
    v
BearerTokenAuthenticationToken
    |
    v
AuthenticationManager
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder
    |
    v
Xác thực thất bại
    |
    v
AuthenticationFailureHandler / Bearer entry point
    |
    v
401 Unauthorized (thường kèm invalid_token)
~~~

Ở nhánh này, failure xảy ra **trong Bearer authentication** trước khi request tới `AuthorizationFilter`. Vì thế giải thích “cứ 401 là do `AuthorizationFilter` từ chối” là không đúng.

Trong quá trình thất bại, filter xử lý/dọn `SecurityContext` theo cơ chế Spring Security để không dùng một authentication thất bại làm principal cho request.

### 5.2. Các lý do phổ biến khiến JWT không hợp lệ

| Vấn đề | Bước thường phát hiện | Hành vi |
|---|---|---|
| Chuỗi không phải JWS JWT hợp lệ theo hợp đồng | JWT parser/decoder | Thất bại xác thực |
| Chữ ký không khớp khóa tin cậy | JwtDecoder | Thất bại xác thực |
| Token hết hạn (`exp`) | JwtDecoder/validator | Thất bại xác thực |
| Token chưa có hiệu lực (`nbf`) | JwtDecoder/validator | Thất bại xác thực |
| Issuer sai (`iss`) | Validator issuer | Thất bại xác thực |
| Audience sai (`aud`), khi đã cấu hình validator | Validator audience | Thất bại xác thực |
| Thuật toán JWS không được phép | Decoder/signature verifier | Thất bại xác thực |
| Token thiếu claim bắt buộc theo hợp đồng | Validator tùy chỉnh | Thất bại xác thực |
| ID Token bị gửi thay access token | Kiểm tra audience/typ/token profile phù hợp | Phải bị từ chối |
| Opaque token bị thu hồi hoặc không active | Opaque token introspector | Thất bại xác thực |

Với JWT access token, Spring Security thường tự có các kiểm tra cơ bản như signature, issuer và thời hạn theo cấu hình. Audience, loại token và custom claim cần được xác nhận với profile/phiên bản và cấu hình ứng dụng. Không nên cho rằng chỉ cần ký hợp lệ là đủ để chấp nhận mọi JWT.

### 5.3. Lỗi khi trích xuất Bearer token

Nếu header sai cú pháp hoặc request cung cấp credential Bearer theo nhiều nguồn không được phép, **`DefaultBearerTokenResolver`** có thể ném `OAuth2AuthenticationException` trước khi tạo `BearerTokenAuthenticationToken`.

Ví dụ một request sai định dạng:

~~~http
Authorization: Bearer token1, Bearer token2
~~~

Đây **không phải** cách truyền nhiều token hợp lệ đến cùng một API. Theo `BearerTokenResolver` và profile của Bearer, lỗi có thể được phân loại là `invalid_request` thay vì `invalid_token`.

Không nên tùy tiện gộp mọi lỗi ở bước resolver thành “JWT signature sai”, vì resolver lúc đó **chưa kiểm tra JWT**.

### 5.4. 400 và 401 không đồng nghĩa

RFC 6750 định nghĩa các Bearer error code quan trọng:

| Mã lỗi | Ý nghĩa | HTTP thường dùng |
|---|---|---|
| `invalid_request` | Request Bearer sai cấu trúc, có tham số/nguồn không hợp lệ hoặc trùng lặp | **400 Bad Request** |
| `invalid_token` | Token hết hạn, bị thu hồi, bị hỏng hoặc không hợp lệ vì lý do khác | **401 Unauthorized** |
| `insufficient_scope` | Access token hợp lệ nhưng thiếu phạm vi quyền được yêu cầu | **403 Forbidden** |

Trong Spring Security, `BearerTokenAuthenticationEntryPoint` có thể dựa trên `BearerTokenError` để xây dựng status/header phù hợp. Vì vậy **header Bearer sai cú pháp có thể là 400**, trong khi token đúng cú pháp nhưng không xác thực được thường là 401.

Không phải mọi chuỗi header không giống Bearer đều tự động tạo 400. Ví dụ `Authorization: Basic abc` có thể chỉ được resolver xem là **không có Bearer token**, và endpoint bảo vệ trả 401 do chưa xác thực. Hành vi chính xác còn phụ thuộc cú pháp, nguồn token, resolver và cấu hình hiện hành.

### 5.5. Ví dụ header lỗi xác thực

Với token được cung cấp nhưng không hợp lệ, phản hồi theo Bearer có thể là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Với lỗi format Bearer được phân loại `invalid_request`:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

Các ví dụ chỉ minh họa dạng phản hồi; header có thể chứa realm, error_description hoặc chi tiết khác theo cấu hình, và một số reverse proxy có thể thay đổi response. Không trả toàn bộ token hoặc claim nhạy cảm trong lỗi.

## 6. Nhánh thứ ba: token hợp lệ nhưng thiếu quyền

### 6.1. Authentication thành công chưa có nghĩa được vào endpoint

Giả sử token được issuer tin cậy ký và hợp lệ, nhưng chỉ có scope `profile`:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 2000000000,
  "scope": "profile"
}
~~~

Nếu đây là token thật, đã ký đúng và đáp ứng validators, Bearer authentication **thành công**. Spring Security tạo một `Authentication` đã được xác thực và đặt vào `SecurityContext`.

Tuy nhiên endpoint `GET /api/orders` yêu cầu:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

Khi authority không có, `AuthorizationFilter` từ chối request.

~~~mermaid
sequenceDiagram
    participant Client
    participant Bearer as BearerTokenAuthenticationFilter
    participant Decoder as JwtDecoder
    participant Context as SecurityContext
    participant Authorization as AuthorizationFilter
    participant Exception as ExceptionTranslationFilter
    participant Handler as AccessDeniedHandler

    Client->>Bearer: GET /api/orders + Bearer token
    Bearer->>Decoder: xác thực JWT
    Decoder-->>Bearer: token hợp lệ
    Bearer->>Context: đặt JwtAuthenticationToken
    Bearer->>Authorization: tiếp tục filter chain
    Authorization->>Context: lấy authorities
    Context-->>Authorization: SCOPE_profile
    Authorization-->>Exception: AccessDeniedException
    Exception->>Handler: handle(request, response, exception)
    Handler-->>Client: 403 Forbidden
~~~

Đây là **authorization failure**. Resource Server đã nhận diện caller, nhưng caller không đủ quyền gọi endpoint.

### 6.2. `BearerTokenAccessDeniedHandler` và `insufficient_scope`

Spring Security Resource Server có **`BearerTokenAccessDeniedHandler`** để xử lý truy cập bị từ chối trong ngữ cảnh Bearer token. Khi request thực sự có authentication phù hợp của OAuth 2.0 và bị từ chối quyền, handler có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Tùy hoàn cảnh và authentication hiện tại, handler có thể trả challenge không kèm `insufficient_scope`. Không mặc định rằng mọi `403`, đặc biệt từ controller hoặc gateway, đều có header trên.

### 6.3. Scope khác quyền sở hữu dữ liệu

Một token có scope `orders.read` có thể vượt qua rule endpoint, nhưng người dùng vẫn chỉ được xem đơn hàng của tenant mình.

Ví dụ:

~~~http
GET /api/orders/123 HTTP/1.1
Authorization: Bearer <VALID_TOKEN_WITH_ORDERS_READ>
~~~

Các bước:

1. Token hợp lệ → Bearer authentication thành công.
2. Có `SCOPE_orders.read` → endpoint authorization cho phép.
3. Service kiểm tra order 123 thuộc tenant/chủ thể nào.
4. Nếu không có quyền với order 123, tầng nghiệp vụ có thể trả **403**, hoặc **404** nếu API dùng chính sách không tiết lộ sự tồn tại của tài nguyên.

**403 tại tầng nghiệp vụ** không có nghĩa `BearerTokenAuthenticationFilter` hoặc `AuthorizationFilter` thất bại; request có thể đã vượt qua cả hai.

### 6.4. Scope và role là hai loại quyền khác nhau

Mặc định, Spring Security có cơ chế ánh xạ scope token như `orders.read` thành authority `SCOPE_orders.read`. Nếu tổ chức dùng role riêng như `roles: ["ADMIN"]`, claim đó **không tự động trở thành** `ROLE_ADMIN` hoặc `SCOPE_orders.read` trong mọi cấu hình.

Muốn dùng role/permission tùy chỉnh, cần một `JwtAuthenticationConverter` hoặc chính sách ánh xạ rõ ràng. Token hợp lệ nhưng sai tên authority có thể gây 403; không nên khắc phục bằng cách tắt authorization.

## 7. `ExceptionTranslationFilter`: khi nào gọi EntryPoint, khi nào gọi AccessDeniedHandler?

`ExceptionTranslationFilter` chuyển **`AuthenticationException`** hoặc **`AccessDeniedException`** từ phần xử lý phía sau nó thành HTTP response với cơ chế bảo mật phù hợp.

Hai hướng xử lý chính:

| Tình huống | Thành phần kết thúc | Ý nghĩa |
|---|---|---|
| Chưa có xác thực hợp lệ và endpoint cần bảo vệ | `AuthenticationEntryPoint` | Yêu cầu client cung cấp credential; thường 401 với Bearer |
| Request đã xác thực phù hợp nhưng bị từ chối quyền | `AccessDeniedHandler` | Báo thiếu quyền; thường 403 |
| Token lỗi ngay trong `BearerTokenAuthenticationFilter` | Failure handler/entry point của Bearer filter | Thường 401, hoặc 400 khi Bearer request sai cấu trúc |

Cần chú ý **vị trí filter**: `BearerTokenAuthenticationFilter` thường chạy **trước `ExceptionTranslationFilter`**. Vì vậy lỗi phát sinh trong Bearer filter được chính cơ chế failure handling của Bearer filter xử lý, chứ không đợi `ExceptionTranslationFilter` bắt từ phía sau.

### 7.1. Logic khi gặp AccessDeniedException

Khi `AuthorizationFilter` hoặc logic bảo vệ phía sau ném `AccessDeniedException`:

- Nếu caller chưa xác thực đầy đủ (ví dụ anonymous), `ExceptionTranslationFilter` thường dùng **`AuthenticationEntryPoint`** để trả challenge 401.
- Nếu caller đã xác thực và thiếu quyền, nó dùng **`AccessDeniedHandler`** để trả 403.

Đây là lý do cùng một loại `AccessDeniedException` có thể dẫn tới **401** hoặc **403** tùy trạng thái authentication. Điều này phù hợp với hai ý nghĩa HTTP: **chưa có xác thực hợp lệ** so với **đã xác thực nhưng không được phép**.

### 7.2. Entry point và denied handler mặc định cho Bearer

Trong Resource Server, các thành phần phổ biến là:

~~~java
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
~~~

Khi cấu hình `oauth2ResourceServer(...)`, Spring Security áp dụng cách xử lý lỗi Bearer thích hợp theo cơ chế hiện hành. Trong cấu hình mặc định, **không cần tạo lại hai handler chỉ để có 401/403**.

Có thể chỉ định tường minh khi cần kiểm soát:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(
        new BearerTokenAuthenticationEntryPoint()
    )
    .accessDeniedHandler(
        new BearerTokenAccessDeniedHandler()
    )
);
~~~

Đoạn trên minh họa các handler của Resource Server. Ở ứng dụng có nhiều cơ chế đăng nhập hoặc nhiều security chains, cần đặt handler phù hợp với **chain/API request** để tránh thay entry point của browser/OIDC login ngoài ý định.

### 7.3. Đừng ép mọi lỗi thành cùng một status

Một cấu hình custom kiểu “khi bất kỳ security exception nào xảy ra thì trả 401” sẽ làm mất sự khác biệt quan trọng:

- Client không biết token cần được cấp lại hay caller cần xin thêm scope.
- Log và monitoring không phân biệt authentication với authorization.
- Hành vi khác với ngữ nghĩa RFC 6750 cho `invalid_request`, `invalid_token` và `insufficient_scope`.

Nếu API có format lỗi JSON riêng, có thể tùy chỉnh body, nhưng vẫn nên giữ HTTP status và `WWW-Authenticate` phù hợp.

## 8. Bảng quyết định 400, 401 và 403

Giả định Resource Server nhận JWT và endpoint `GET /api/orders` yêu cầu `SCOPE_orders.read`:

| Input | Xử lý token | Xử lý quyền | HTTP thường gặp |
|---|---|---|---|
| Không có `Authorization` | Không có Bearer token | Anonymous bị từ chối | **401** |
| `Authorization: Basic ...` | Không được xem là Bearer token | Không có xác thực Bearer | **401** nếu không có auth khác |
| `Authorization: Bearer invalid.jwt.value` | Xác thực JWT thất bại | Chưa tới authorization | **401** |
| Bearer token hết hạn | Validator thời gian từ chối | Chưa tới authorization | **401** |
| Bearer token sai chữ ký | Decoder từ chối | Chưa tới authorization | **401** |
| Bearer token sai issuer | Validator issuer từ chối | Chưa tới authorization | **401** |
| Bearer token sai audience và có audience validator | Validator audience từ chối | Chưa tới authorization | **401** |
| Bearer request sai cấu trúc, phân loại `invalid_request` | Resolver từ chối | Chưa tới authorization | **400** |
| JWT hợp lệ, `scope: "profile"` | Xác thực thành công | Thiếu `SCOPE_orders.read` | **403** |
| JWT hợp lệ, có `orders.read` | Xác thực thành công | Rule endpoint cho phép | Có thể **200** |
| JWT hợp lệ, có scope nhưng khác tenant | Xác thực thành công | Quyền dữ liệu bị từ chối | **403** hoặc **404** |
| Không token, `GET /api/public/ping` | Không xác thực Bearer | `permitAll` | Có thể **200** |
| Token sai, `GET /api/public/ping` trong cùng chain | Bearer authentication có thể thất bại trước authorization | Chưa đến `permitAll` | Thường **401** |

Đây là kết quả **thông thường**, không phải cam kết tuyệt đối cho mọi ứng dụng. Gateway, filter riêng, handler ngoại lệ, phiên bản Spring và quy tắc business có thể thay đổi chi tiết response.

**Tình huống dễ nhầm nhất:** `permitAll` chỉ cho phép bỏ qua **quy tắc authorization của endpoint**, không tắt `BearerTokenAuthenticationFilter` cho request đó.

## 9. Tại sao endpoint `permitAll` vẫn có thể trả 401?

Giả sử chain chứa:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
)
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
);
~~~

Request không token:

~~~http
GET /api/public/ping HTTP/1.1
~~~

Bearer filter không tìm token và cho request đi tiếp. `AuthorizationFilter` gặp `permitAll`, nên request được cho phép.

Nhưng request:

~~~http
GET /api/public/ping HTTP/1.1
Authorization: Bearer broken.token
~~~

Bearer filter **nhìn thấy một Bearer token** và có thể thử xác thực nó. Nếu xác thực thất bại, filter trả lỗi trước khi request tới `AuthorizationFilter`. Do đó endpoint public vẫn có thể trả **401**.

Đây là kết quả của pipeline xác thực, không phải bug của `permitAll`.

Nếu có một khu vực công khai cần **tách hẳn Bearer authentication**, có thể thiết kế `SecurityFilterChain` riêng với matcher cụ thể và thứ tự rõ ràng. Cách này phải được đánh giá cùng toàn bộ routes để không vô tình để endpoint bảo vệ nằm ngoài các chain phù hợp.

## 10. Nhiều SecurityFilterChain: nguồn lỗi ít được chú ý

Trong ứng dụng vừa có web login vừa có API token, một request API đôi khi khớp **chain sai**.

Ví dụ sơ đồ kiến trúc:

~~~mermaid
flowchart TD
    A["Request"] --> B["FilterChainProxy"]
    B --> C{"Request khớp chain đầu?"}
    C -->|"/api/**"| D["API chain: Bearer Resource Server"]
    C -->|"Không"| E["Fallback chain: Web / policy khác"]
    D --> F["Bearer auth + API authorization"]
    E --> G["Web login / denyAll / policy khác"]
~~~

Giả sử một chain tổng quát `/**` có thứ tự cao hơn chain `/api/**`. Vì `FilterChainProxy` lấy **first matching chain**, chain `/**` có thể nhận tất cả request khiến API chain không bao giờ chạy.

Hậu quả có thể là:

- API trả **302 redirect** đến trang đăng nhập vì đang dùng browser login entry point.
- API không đọc Bearer token.
- Header Bearer đúng nhưng API vẫn 401/403 theo cơ chế khác.
- Rule scope dự định cho `/api/**` không được áp dụng.

Ví dụ hai chain:

~~~java
@Configuration
public class SplitSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll()
            );
        return http.build();
    }
}
~~~

Code này là **ví dụ thay thế** cho cấu hình một chain ở phần đầu, không đặt cả hai cùng lúc vào cùng ứng dụng mà không điều chỉnh. Những import của ví dụ có thể lấy từ phần cấu hình trước, thêm `org.springframework.core.annotation.Order`.

**Một request chỉ chạy security chain đầu tiên khớp**. Vì thế muốn phân tích 401/403 chính xác cần bắt đầu từ matcher và thứ tự chain, sau đó mới theo dõi Bearer filter.

## 11. JWT và opaque token: nhánh lỗi giống nhau ở HTTP nhưng khác bên trong

### 11.1. JWT access token

~~~text
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder
    |
    +-- chữ ký sai -> authentication failure
    +-- issuer sai -> authentication failure
    +-- token hết hạn -> authentication failure
    +-- audience sai (nếu validator có) -> authentication failure
    |
    v
JwtAuthenticationToken
    |
    v
AuthorizationFilter
~~~

JWT decoder thường xác minh chữ ký với public key/JWKS của issuer và kiểm tra claim validators. Việc đọc claim qua Base64URL không chứng minh token hợp lệ.

### 11.2. Opaque access token

~~~text
BearerTokenAuthenticationFilter
    |
    v
OpaqueTokenAuthenticationProvider
    |
    v
OpaqueTokenIntrospector
    |
    +-- active=false / không hợp lệ -> authentication failure
    +-- active=true + attributes -> Authentication
    |
    v
AuthorizationFilter
~~~

Với opaque token, Resource Server có thể dùng `oauth2ResourceServer(...opaqueToken(...))` để gọi introspection endpoint theo hợp đồng. Token hết hạn/bị thu hồi hoặc không active thường dẫn đến lỗi authentication.

Nếu introspection endpoint **không thể kết nối**, timeout hoặc gặp lỗi hạ tầng, kết quả có thể là lỗi dịch vụ khác với `invalid_token`; không được tự mặc định mọi network failure là token không hợp lệ. Tùy cấu hình cần xử lý availability và quan sát sự cố riêng.

### 11.3. OIDC ID Token không phải Bearer access token cho API

Một OIDC **ID Token** được phát hành cho OIDC client để chứng minh kết quả xác thực người dùng, thường có audience là client ID. Resource Server phải nhận **access token dành cho API**.

Nếu client gửi ID Token vào:

~~~http
Authorization: Bearer <OIDC_ID_TOKEN>
~~~

API cần từ chối theo yêu cầu audience, token type hoặc token profile, dù JWT đó có thể mang chữ ký hợp lệ của cùng issuer. Không “sửa” 401 bằng cách bỏ audience validation.

## 12. Những khác biệt khi có CORS preflight và CSRF

### 12.1. CORS preflight thường không mang Bearer token

Trình duyệt có thể gửi:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://shop.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight là request kiểm tra chính sách CORS, thường **không kèm access token**. Nếu ứng dụng đòi Bearer authentication trước khi xử lý preflight, frontend có thể báo lỗi CORS dù access token của request thật hợp lệ.

Spring Security hỗ trợ tích hợp CORS bằng:

~~~java
http.cors(Customizer.withDefaults());
~~~

Ứng dụng còn phải cung cấp cấu hình CORS tương thích origin/method/header thực tế, ví dụ `CorsConfigurationSource`. CORS cần được xử lý đúng thứ tự trước authentication đối với preflight.

**Đừng nhầm lỗi CORS với JWT sai.** Nếu preflight bị từ chối, browser có thể không gửi request GET/POST thật, nên Bearer filter chưa từng xử lý access token dự định.

### 12.2. CSRF và token ngoài cookie

Ví dụ tắt CSRF ở API chain chỉ phù hợp khi cơ chế xác thực thực sự là **Bearer token được client chủ động gửi, không dùng cookie để tự động gửi credential**. Nếu frontend/web vẫn dùng cookie đăng nhập, cần kiểm tra rủi ro CSRF và cấu hình bảo vệ thích hợp.

Một response 403 cũng có thể đến từ **CSRF filter**, trước khi endpoint authorization chạy. Vì thế không nên kết luận “403 chắc chắn là thiếu scope” khi chưa biết filter/handler nào tạo ra response.

## 13. Sửa mã lỗi có làm hệ thống an toàn hơn không?

Không nên “sửa 401 thành 403” hoặc “sửa 403 thành 401” bằng cách bắt mọi exception chung chỉ để khớp một client. HTTP status phản ánh giai đoạn thất bại và giúp chẩn đoán.

### 13.1. `AuthenticationEntryPoint`

Được dùng khi cần thách thức/yêu cầu xác thực hoặc khi Bearer authentication thất bại theo cơ chế tương ứng.

Với RFC 6750, response thường có `WWW-Authenticate: Bearer` để client biết scheme. Khi access token đã gửi nhưng sai, có thể có `error="invalid_token"`.

### 13.2. `AccessDeniedHandler`

Được dùng khi request đã xác thực nhưng bị từ chối quyền. `BearerTokenAccessDeniedHandler` hỗ trợ phản hồi theo Bearer với `insufficient_scope` khi điều kiện tương ứng.

### 13.3. Body JSON tùy biến

API có thể muốn body:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Permission required",
  "traceId": "trace-123"
}
~~~

Đó là quyết định về **format phản hồi**. Nếu tùy biến handler để viết JSON, cần giữ status/header chính xác và không đưa token hoặc thông tin mật vào body/log.

Không nên tiết lộ chi tiết như “chữ ký thuộc khóa nào”, “tài khoản nào có quyền”, “mật khẩu/cert nào không hợp lệ” trong response công khai.

## 14. Cách quan sát chính xác đường đi request

### 14.1. Đọc log khi phát triển

Có thể bật debug trong local/dev:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Log có thể hiển thị chuỗi filter được chọn, request được bảo vệ và nguyên nhân xác thực/phân quyền thất bại. Nếu thật sự cần, `TRACE` chi tiết hơn, nhưng cũng tăng độ ồn và rủi ro log dữ liệu nhạy cảm.

Tránh log nguyên Bearer token, header `Authorization`, response introspection đầy đủ hoặc secret/JWKS private key. Trong production, nên log mã lỗi, endpoint, correlation ID và metadata ít nhạy cảm.

### 14.2. Thứ tự chẩn đoán 401

1. Request đã đi vào đúng `SecurityFilterChain` chưa?
2. `BearerTokenResolver` có tìm đúng nguồn header chưa?
3. Token có được truyền dưới dạng `Authorization: Bearer <token>` không?
4. Có lỗi sai cú pháp request (`invalid_request`) hay lỗi nội dung token (`invalid_token`)?
5. JWT có đúng issuer, chữ ký, thuật toán, hạn, audience/profile theo hợp đồng không?
6. Nếu opaque, introspection endpoint có trả token active không, có sự cố kết nối không?
7. Nếu có nhiều authentication entry point, response đang được tạo bởi handler nào?

Thứ tự này xác định **lỗi ở tầng nào**. Không hạ rule endpoint thành `permitAll` hoặc vô hiệu hóa JWT validation để làm hết 401.

### 14.3. Thứ tự chẩn đoán 403

1. Token đã xác thực thành công chưa?
2. Rule `requestMatchers` nào đang áp dụng?
3. Claim `scope` được chuyển thành authority nào? Tên `SCOPE_orders.read` có đúng không?
4. Có role/authority tùy chỉnh với prefix khác không?
5. Request bị từ chối ở `AuthorizationFilter`, `CsrfFilter`, method security hay service nghiệp vụ?
6. Có kiểm tra owner/tenant hoặc ACL của bản ghi không?

Một 403 có thể đến từ nhiều tầng; phải xác định nơi quyết định thay vì chỉ xem HTTP status.

### 14.4. Kiểm thử rule và kiểm thử Bearer pipeline là hai phạm vi

Trong Spring Security Test, dùng `jwt()` của MockMvc thường tạo authentication giả lập để kiểm thử authorization, ví dụ:

~~~java
mockMvc.perform(
    get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        ))
);
~~~

Điều này hữu ích để thử rule, nhưng **không tự chứng minh** rằng Bearer token thực tế được tách từ HTTP header, JWT signature được xác minh và claim validators chạy đúng.

Đối với luồng đầy đủ, các phép thử tích hợp nên gửi token test qua header thật, dùng issuer/JWK test có kiểm soát và xác minh hành vi thiếu token, token hết hạn, chữ ký sai, audience sai, thiếu scope và sai header. Không dùng token production trong bài kiểm thử.

## 15. Ma trận thực hành với curl

Sử dụng các placeholder; token thật phải được cấp bởi Authorization Server test và có audience cho Orders API.

### Case A — Không có token

~~~bash
curl -i https://api.example.test/api/orders
~~~

**Dự kiến:** 401 khi endpoint yêu cầu Bearer authentication. Header có thể là `WWW-Authenticate: Bearer` không có error code.

### Case B — Sai JWT

~~~bash
curl -i \
  -H "Authorization: Bearer invalid.jwt.value" \
  https://api.example.test/api/orders
~~~

**Dự kiến:** 401 với lỗi xác thực token (thường `invalid_token`).

### Case C — Token hợp lệ nhưng thiếu scope

~~~bash
curl -i \
  -H "Authorization: Bearer <TOKEN_SCOPE_PROFILE_ONLY>" \
  https://api.example.test/api/orders
~~~

**Dự kiến:** 403 vì đã xác thực nhưng thiếu `orders.read`. Với Bearer access denied handling phù hợp, có thể có `insufficient_scope`.

### Case D — Đủ scope

~~~bash
curl -i \
  -H "Authorization: Bearer <TOKEN_SCOPE_ORDERS_READ>" \
  https://api.example.test/api/orders
~~~

**Dự kiến:** authorization ở endpoint cho phép, controller xử lý; status cuối còn phụ thuộc logic ứng dụng.

### Case E — Endpoint công khai, không token

~~~bash
curl -i https://api.example.test/api/public/ping
~~~

**Dự kiến:** endpoint `permitAll` được truy cập nếu không bị chặn bởi các filter hoặc policy khác.

### Case F — Endpoint công khai nhưng token sai

~~~bash
curl -i \
  -H "Authorization: Bearer invalid.jwt.value" \
  https://api.example.test/api/public/ping
~~~

**Dự kiến:** có thể 401 dù endpoint `permitAll`, do Bearer filter xử lý token lỗi trước authorization.

### Case G — Sai định dạng Bearer request

~~~bash
curl -i \
  -H "Authorization: Bearer token1, Bearer token2" \
  https://api.example.test/api/orders
~~~

**Dự kiến:** request Bearer không đúng quy tắc; resolver có thể phân loại là `invalid_request` và phản hồi 400. Hành vi tùy resolver/cú pháp, nên dùng một access token hợp lệ trên mỗi request theo hợp đồng.

## 16. Tình huống thực tế: cùng một người gọi nhưng status khác nhau

Giả sử phía frontend gọi:

~~~text
GET /api/orders/42
~~~

Hợp đồng:

- Access token phải có issuer tin cậy và audience `orders-api`.
- GET endpoint yêu cầu `SCOPE_orders.read`.
- Order 42 thuộc tenant `tenant-A`.
- Người gọi thuộc tenant `tenant-B` thì không được xem order 42.

Các request tương ứng:

| Token / trạng thái | Nơi phát hiện | Phản hồi dự kiến |
|---|---|---|
| Không có token | Authorization yêu cầu authenticated caller | 401 |
| Token hết hạn | Bearer authentication / JwtDecoder | 401 |
| Token sai `aud` | JwtDecoder với audience validator | 401 |
| Token đúng audience nhưng chỉ có `orders.write` | Authorization rule thiếu `orders.read` | 403 |
| Token có `orders.read` nhưng thuộc `tenant-B` | Service/ownership policy | 403 hoặc 404 |
| Token hợp lệ, có `orders.read` và thuộc `tenant-A` | Vượt security và business checks | Trả dữ liệu phù hợp, thường 200 |

**Không dùng email hoặc tên hiển thị thay kiểm tra chủ sở hữu theo `sub`/tenant đã xác thực.** Khi service có logic multi-tenancy, phải xác định owner từ dữ liệu đáng tin và policy nghiệp vụ.

## 17. Những nhầm lẫn thường gặp

### 17.1. “Không có token” và “token sai” đều là 401 nên giống nhau

Không giống nhau về đường đi. Thiếu token thường khiến Bearer filter cho request đi tiếp rồi authorization đưa ra challenge. Token sai được trích xuất và bị từ chối ngay tại bước authentication. Phân biệt giúp tìm đúng nơi cần sửa.

### 17.2. “403 là JWT chưa được xác minh”

Thường không chính xác trong endpoint bearer có rule scope. Nếu JWT sai chữ ký hoặc hết hạn, bước authentication thường trả 401. 403 thường là token hợp lệ nhưng không đạt authorization, hoặc một filter/chính sách khác như CSRF từ chối.

### 17.3. “Đặt `permitAll` là bỏ qua Bearer filter”

Không đúng. `permitAll` chỉ là rule authorization. Nếu chain vẫn bật Resource Server và request gửi Bearer token không hợp lệ, lỗi authentication có thể xảy ra trước khi authorization tới rule này.

### 17.4. “Mọi lỗi 401 đều do `ExceptionTranslationFilter` bắt”

Không đúng. Lỗi Bearer token trong `BearerTokenAuthenticationFilter` được xử lý bởi cơ chế failure handling/entry point của chính filter. `ExceptionTranslationFilter` xử lý ngoại lệ ở phần chuỗi downstream mà nó bao quanh.

### 17.5. “Có `Authentication` trong SecurityContext là authenticated user”

Không chắc. Có thể đó là anonymous authentication. Cần dựa vào policy `authenticated()`/authorities và loại principal phù hợp.

### 17.6. “Cứ thêm scope vào JWT payload là đủ quyền”

Nếu tự chỉnh payload JWT, signature sẽ không còn hợp lệ. Scope phải được Authorization Server cấp và được Resource Server xác minh. Ngoài scope còn có audience và quyền trên từng tài nguyên.

### 17.7. “Tắt CSRF khi thấy 403 sẽ giải quyết”

Chỉ tắt CSRF trong trường hợp thiết kế API không dựa trên cookie/session browser; 403 cũng có thể do authority, ownership hoặc filter khác. Việc sửa không đúng nguyên nhân có thể làm giảm bảo vệ của ứng dụng.

### 17.8. “JWT có chữ ký hợp lệ thì ID Token cũng dùng để gọi API được”

Không. ID Token dành cho OIDC client; API phải chấp nhận **access token dành cho chính API**, kiểm tra audience, loại token và profile đúng hợp đồng.

## 18. Ghi nhớ để áp dụng

Khi request bị từ chối, hãy gắn kết quả với **giai đoạn trong chuỗi Servlet**:

~~~text
FilterChainProxy chọn SecurityFilterChain
               |
               v
BearerTokenAuthenticationFilter
  |           |
  |           +-- Token có nhưng sai -> authentication failure -> 401
  |                 (request Bearer sai cấu trúc có thể -> 400)
  |
  +-- Không có token -> tiếp tục, chưa có authenticated principal
  |
  +-- Token hợp lệ -> SecurityContext có Authentication
               |
               v
AuthorizationFilter / quyền nghiệp vụ
  |           |
  |           +-- Chưa xác thực + endpoint bảo vệ -> 401
  |           +-- Đã xác thực nhưng thiếu quyền -> 403
  |           +-- Đủ quyền -> controller, rồi kiểm tra business access
~~~

- **401**: request cần xác thực hoặc token được cung cấp không hợp lệ.
- **400**: một số lỗi **`invalid_request`** do yêu cầu Bearer sai cấu trúc.
- **403**: caller đã xác thực nhưng không được phép; cũng có thể do policy/filter khác như CSRF.
- `AuthenticationEntryPoint` và `AccessDeniedHandler` quyết định phản hồi phù hợp theo từng nhánh.
- Cấu hình `SecurityFilterChain`, matcher và thứ tự chain quyết định liệu Bearer processing có chạy hay không.
- Thông tin scope có trong token chỉ giúp authorization ở mức policy; quyền đối tượng vẫn cần kiểm tra khi xử lý nghiệp vụ.

### Tài liệu tham khảo

- [Spring Security Reference — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security API — BearerTokenAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html)
- [Spring Security API — BearerTokenAuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html)
- [Spring Security API — BearerTokenAccessDeniedHandler](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)

