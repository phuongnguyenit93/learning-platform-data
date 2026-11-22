# CORS, preflight và xử lý trước bước yêu cầu token

Khi xây dựng **Spring Security OAuth 2.0 / OIDC Resource Server** cho một ứng dụng web, frontend và API thường nằm ở **hai origin khác nhau**. Ví dụ, ứng dụng JavaScript chạy tại `https://app.example.test` gọi Resource Server tại `https://api.example.test` và gửi **OAuth 2.0 Bearer Access Token** trong header `Authorization`.

Một vấn đề thường gặp là: **frontend có Access Token hợp lệ nhưng trình duyệt vẫn báo lỗi CORS**, hoặc **request OPTIONS bị trả 401 vì không có token**. Lý do là trước request thực, browser có thể gửi **CORS preflight** để hỏi server liệu request cross-origin được phép hay không. Preflight thường **không có Bearer token**, nên nó cần được xử lý **trước bước yêu cầu xác thực token**.

Bài học tập trung vào cách phân biệt **Origin, same-origin policy, CORS và preflight**, cách cấu hình `http.cors(...)` và `CorsConfigurationSource` trong Spring Security, vai trò của filter order, phản hồi lỗi 401/403, mối quan hệ với CSRF và session/cookie, những vấn đề khi chạy sau reverse proxy, và phương pháp kiểm thử. Ví dụ dùng **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet và Java 17+**. Những hostname và token minh họa không phải credential thật.

## 1. Vấn đề thực tế: đã có Bearer token nhưng browser không gọi được API

Giả sử frontend:

~~~text
https://app.example.test
~~~

gọi API:

~~~text
https://api.example.test
~~~

Code JavaScript:

~~~javascript
async function loadOrders(accessToken) {
  const response = await fetch(
    "https://api.example.test/api/orders",
    {
      method: "GET",
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      }
    }
  );

  if (!response.ok) {
    throw new Error("API returned " + response.status);
  }

  return response.json();
}
~~~

Frontend có thể thấy trên DevTools:

~~~text
Access to fetch at 'https://api.example.test/api/orders'
from origin 'https://app.example.test' has been blocked
by CORS policy.
~~~

Một developer mới có thể kiểm tra token, thay JWT, sửa scopes hoặc tắt security. Nhưng **CORS không đồng nghĩa JWT validation**. Đôi khi request chứa JWT thực sự **chưa từng được gửi**: browser đã dừng trước đó vì **preflight thất bại**.

### 1.1. Hai request khác nhau

Với Authorization header cross-origin, browser thường gửi:

~~~text
1. OPTIONS /api/orders
   Origin: https://app.example.test
   Access-Control-Request-Method: GET
   Access-Control-Request-Headers: authorization

   Không có Authorization: Bearer ...
                 |
                 v
   Server trả các Access-Control-Allow-* headers
                 |
                 v
2. GET /api/orders
   Origin: https://app.example.test
   Authorization: Bearer ACCESS_TOKEN
                 |
                 v
   Spring Security xác thực token, kiểm tra scope và dữ liệu
~~~

**Preflight không phải là request nghiệp vụ.** Nó là cơ chế **browser hỏi quyền thực hiện cross-origin request**. Browser cần biết liệu origin, HTTP method và request headers dự kiến có được server chấp thuận hay không trước khi gửi request thật.

Nếu API đòi Bearer token ngay ở request OPTIONS, preflight có thể nhận 401; browser dừng và **không gửi GET** mặc dù ứng dụng JavaScript đã chuẩn bị một Access Token hoàn toàn hợp lệ.

### 1.2. Mục tiêu thiết kế

Một Resource Server đúng cần đạt hai mục tiêu **cùng lúc**:

1. **Cho browser thực hiện CORS preflight hợp lệ mà không cần Bearer token.**
2. **Vẫn yêu cầu Bearer token hợp lệ và đúng quyền ở request API thực tế** như GET, POST, PATCH hoặc DELETE.

Không thể giải quyết bằng việc mở toàn bộ `/api/**` thành `permitAll()`: như vậy có thể làm lộ endpoint nghiệp vụ. Cũng không nên mặc định cho phép mọi `OPTIONS /**` mà bỏ qua Origin/method/header policy. CORS cần được xử lý đúng ở **filter trước authentication**.

## 2. Origin là gì?

Một **origin** của trang web được xác định bởi **scheme + host + port**.

| URL | Origin | So với `https://app.example.test` |
| --- | --- | --- |
| `https://app.example.test/home` | `https://app.example.test` | Cùng origin. |
| `https://app.example.test/api` | `https://app.example.test` | Cùng origin. |
| `https://api.example.test/api` | `https://api.example.test` | Khác host → khác origin. |
| `http://app.example.test` | `http://app.example.test` | Khác scheme → khác origin. |
| `https://app.example.test:8443` | `https://app.example.test:8443` | Khác port → khác origin. |
| `https://app.example.test:443` | Default HTTPS port 443 | Tương đương origin HTTPS mặc định. |

**Path không phải một thành phần của origin.** Hai đường dẫn trên cùng scheme, hostname và port có cùng origin, dù path khác nhau.

### 2.1. Same-Origin Policy

Browser áp dụng **Same-Origin Policy** để giới hạn cách script từ một origin đọc dữ liệu của một origin khác. Chính sách này giúp ngăn một trang web bất kỳ đọc trực tiếp dữ liệu từ site mà user đang đăng nhập.

**CORS — Cross-Origin Resource Sharing** là cơ chế HTTP cho phép server thông báo với browser rằng **một số nguồn truy cập khác origin** được phép thực hiện request và đọc response theo điều kiện đã khai báo.

Ví dụ:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Header này cho browser biết origin `https://app.example.test` được phép tiếp cận response theo CORS. Nó **không cấp OAuth scopes**, không xác minh JWT, không chứng minh user đăng nhập và không thay thế kiểm tra owner/tenant trong domain.

### 2.2. CORS là chính sách của browser

Một script trong browser chịu same-origin/CORS, nhưng `curl`, Postman hoặc một backend HTTP client **không bị browser CORS enforcement**.

Ví dụ:

~~~bash
curl -i \
  -H 'Authorization: Bearer TEST_ACCESS_TOKEN' \
  'https://api.example.test/api/orders'
~~~

Client dòng lệnh có thể gọi API trực tiếp, dù server không trả `Access-Control-Allow-Origin`. Nó vẫn phải cung cấp Bearer token đúng nếu endpoint được bảo vệ.

Vì vậy, **CORS không phải lớp xác thực API** và không phải cách chặn mọi client ngoài origin được cho phép. Để bảo vệ Resource Server, cần JWT/opaque validation, audience, scope và authorization; để giới hạn hạ tầng cần thêm network/gateway policy nếu cần.

## 3. CORS preflight là request gì?

**Preflight** là request `OPTIONS` do browser tự phát sinh trong các tình huống cross-origin yêu cầu kiểm tra quyền trước request thật.

Ví dụ:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Browser hỏi:

- Origin `https://app.example.test` có được phép gọi tài nguyên không?
- Có được gửi **POST** không?
- Có được gửi các request headers **Authorization** và **Content-Type** không?

Phản hồi cho preflight hợp lệ có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-ID
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

`200 OK` chỉ là ví dụ; **204 No Content** cũng có thể phù hợp tùy hạ tầng. Browser quan tâm status thành công cùng các CORS headers phù hợp, không yêu cầu phải có một status thành công cố định cho mọi triển khai.

Nếu preflight được chấp thuận, browser mới gửi request thực:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Content-Type: application/json

{"productCode":"BOOK-01","quantity":2}
~~~

**Chính request POST này** phải qua Bearer authentication, scope authorization và business validation. Preflight OPTIONS không tạo Authentication thay cho POST.

### 3.1. CORS preflight thường không mang token hoặc cookie

Một CORS preflight thông thường được browser gửi **không mang credential của request chính**, gồm Authorization Bearer header hoặc cookie. Đó là lý do nó phải được xử lý trước filter yêu cầu người dùng xác thực.

Không yêu cầu JavaScript tự thêm `Authorization` vào preflight: browser tạo request này và không cho ứng dụng tự gắn Bearer token vào request OPTIONS do browser quản lý.

Nếu developer viết `fetch` với method OPTIONS bằng tay, đó là **request ứng dụng tự gửi**, không nhất thiết là CORS preflight theo browser. Hai loại OPTIONS cần được phân biệt bằng **`Origin`** và **`Access-Control-Request-Method`**.

### 3.2. Khi nào browser gửi preflight?

Trong nhiều tình huống, browser gửi preflight khi request cross-origin **không thuộc nhóm CORS-safelisted requests**. Các trường hợp phổ biến:

- Gửi **Authorization header**, ví dụ `Authorization: Bearer ...`.
- Dùng HTTP method **PUT, PATCH, DELETE**.
- Gửi `Content-Type: application/json` (không thuộc các Content-Type safelisted).
- Gửi các custom headers như `X-Tenant-ID`, `X-Request-ID` hoặc `X-Requested-With` nếu không thuộc nhóm safelisted.
- Request có các đặc tính khác khiến browser cần preflight theo Fetch/CORS rules.

| Request của JavaScript | Thường có preflight? | Lý do |
| --- | --- | --- |
| GET cross-origin, không custom header | Có thể **không** | GET có thể thuộc nhóm safelisted. |
| GET + `Authorization: Bearer ...` | **Có** | Authorization không phải request-header safelisted. |
| POST + `Content-Type: application/json` | **Có** | Content-Type không thuộc nhóm safelisted. |
| POST với form Content-Type safelisted, không custom header | Có thể **không** | Có thể thuộc nhóm request đơn giản theo CORS. |
| PATCH + Bearer | **Có** | Method và Authorization đều cần kiểm tra. |
| DELETE + Bearer | **Có** | Method không safelisted. |

Browser có thể **cache preflight thành công** nên DevTools không nhất thiết thấy OPTIONS trước *mỗi* GET/POST. Không coi việc không thấy OPTIONS ở một lần gọi là bằng chứng CORS đã bị tắt.

### 3.3. OPTIONS bình thường và preflight không giống nhau

Request:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
~~~

không có `Origin` và `Access-Control-Request-Method` nên **không phải CORS preflight** theo cách nhận diện phổ biến. Nó có thể là một OPTIONS request ứng dụng/hạ tầng muốn xử lý bình thường, và **không mặc nhiên được phép không cần token**.

Ngược lại:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

là preflight cần được CORS processor xử lý trước khi Spring Security yêu cầu Bearer token. Cấu hình CORS đúng giúp tránh phải mở mọi OPTIONS request cho tất cả client bằng một wildcard rule.

## 4. Ý nghĩa các CORS headers

### 4.1. Nhóm request headers

| Header | Ai gửi? | Ý nghĩa |
| --- | --- | --- |
| `Origin` | Browser | Origin nơi JavaScript thực hiện request. |
| `Access-Control-Request-Method` | Browser ở preflight | Method dự kiến của request thực. |
| `Access-Control-Request-Headers` | Browser ở preflight | Những request-header names dự kiến mà browser phải xin phép. |
| `Authorization` | Request thực của client | Bearer Access Token; **không phải** header cần gửi trong preflight. |

Ví dụ `Access-Control-Request-Headers: authorization,content-type` chứa **tên header**, không chứa Access Token. Preflight chỉ hỏi liệu header `Authorization` có được sử dụng hay không, chứ không cung cấp giá trị.

### 4.2. Nhóm response headers

| Header | Vai trò |
| --- | --- |
| `Access-Control-Allow-Origin` | Origin được phép đọc response theo CORS. |
| `Access-Control-Allow-Methods` | Các HTTP methods được phép dùng cho cross-origin request. |
| `Access-Control-Allow-Headers` | Tên request headers browser được phép gửi, ví dụ `Authorization`, `Content-Type`. |
| `Access-Control-Allow-Credentials` | Chỉ rõ browser có thể cho phép credentialed response trong CORS flow tương ứng; chỉ dùng nếu thiết kế cho phép. |
| `Access-Control-Max-Age` | Gợi ý thời gian cache kết quả preflight tại browser, có giới hạn do browser áp dụng. |
| `Access-Control-Expose-Headers` | Các response headers JavaScript được phép đọc ngoài tập safelisted, ví dụ `WWW-Authenticate`. |
| `Vary` | Thông báo cho shared caches rằng response khác nhau tùy Origin/preflight request parameters. |

Không nhầm:

~~~http
Access-Control-Allow-Headers: Authorization
~~~

với:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Header đầu cho phép browser **gửi header tên Authorization** ở request thật; header thứ hai cho phép **origin cụ thể** truy cập response. Cần các điều kiện đồng thời đúng nếu browser phải gửi Bearer token cross-origin.

### 4.3. Thiếu một header cũng có thể khiến preflight thất bại

Ví dụ:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Content-Type
~~~

Browser vẫn từ chối vì **POST không nằm trong Allowed Methods** và **Authorization không nằm trong Allowed Headers**. Đây là lỗi CORS policy, không phải JWT sai chữ ký.

Ngược lại, nếu server cho phép preflight nhưng request thực thiếu/đưa sai token, request thật có thể nhận **401**. CORS và Bearer authentication là **hai quyết định khác nhau**.

## 5. Vì sao phải xử lý CORS trước Spring Security authentication?

Trong Servlet Resource Server, Spring Security có các security filters như **`BearerTokenAuthenticationFilter`** và **`AuthorizationFilter`**. Nếu preflight đi qua logic yêu cầu token **trước khi CORS được xử lý**, server có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Browser không xem đây là preflight được chấp thuận nên dừng request. Frontend thường chỉ thấy **CORS error** chứ không nhận response JSON của endpoint API.

### 5.1. Thứ tự lý tưởng

~~~text
OPTIONS /api/orders (preflight, không có token)
                  |
                  v
        CORS processor / CorsFilter
                  |
          Origin được phép?
          Method được phép?
          Headers được phép?
             /           \
           Không         Có
            |            |
            v            v
       CORS reject   Preflight response
                     Access-Control-Allow-*
                          |
                          v
                     Browser tiếp tục
                     request thật

GET /api/orders (Authorization: Bearer ...)
                  |
                  v
          CORS check origin
                  |
                  v
          Bearer authentication
                  |
                  v
          HTTP authorization
                  |
                  v
          Domain authorization
~~~

**CORS processor cần được áp dụng trước khi yêu cầu xác thực Bearer token**. Với cấu hình đúng, preflight hợp lệ có thể được trả lời **ngay tại CORS layer** mà không đi qua JWT decoder hoặc controller.

### 5.2. Spring Security khuyến nghị tích hợp CORS

Spring Security có DSL:

~~~java
http.cors(Customizer.withDefaults());
~~~

Khi có **`UrlBasedCorsConfigurationSource`** phù hợp, Spring Security có thể tích hợp xử lý CORS vào security filter chain. Đó là lựa chọn đơn giản và rõ ràng cho API Servlet.

Điều quan trọng là không chỉ khai báo `permitAll()` cho OPTIONS. **`permitAll()` nằm ở authorization**, có thể quá muộn nếu Bearer authentication xử lý preflight trước; đồng thời nó không tự tạo các **`Access-Control-Allow-*` response headers** browser cần.

### 5.3. Trường hợp không có CORS configuration

Nếu chỉ thêm:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

thì có thể xảy ra:

1. OPTIONS đi qua security authorization.
2. Không có CORS processor nào trả lời Origin/Method/Headers đúng.
3. Response là 200/404/405 nhưng thiếu Access-Control-Allow-Origin.
4. Browser vẫn chặn request thật.

Do đó **mở OPTIONS** không thay thế việc cấu hình **CORS policy và filter order**.

## 6. Cấu hình hoàn chỉnh Spring Boot + Spring Security Resource Server

Giả sử API ở `https://api.example.test`, frontend được phép ở **`https://app.example.test`**. API dùng JWT Bearer Access Token và không dùng cookie/session làm cơ chế xác thực.

### 6.1. Dependencies

Ví dụ Gradle Groovy DSL với version do Spring Boot quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

### 6.2. application.yml cho JWT Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/demo
          audiences:
            - orders-api
~~~

`issuer-uri` định nghĩa Authorization Server đáng tin cậy. `audiences` được hỗ trợ trên những phiên bản Spring Boot phù hợp để yêu cầu token được phát hành cho `orders-api`; nếu phiên bản khác, bổ sung audience validator. Ngoài issuer/audience, Resource Server cần JWT signature, expiration, algorithm và những token profile validators phù hợp.

**Cấu hình này không tự giải quyết CORS.** CORS được cấu hình riêng ở Spring Security filter chain và `CorsConfigurationSource`.

### 6.3. Bean CorsConfigurationSource

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Chỉ cho phép frontend đã được phê duyệt.
        cors.setAllowedOrigins(
            List.of("https://app.example.test"));

        // Các HTTP methods mà frontend có thể dùng.
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "PATCH",
                    "DELETE", "OPTIONS"));

        // Các request headers trình duyệt được gửi.
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type",
                    "X-Request-ID"));

        // Cho frontend đọc header này khi API trả 401/403.
        cors.setExposedHeaders(
            List.of("WWW-Authenticate", "X-Request-ID"));

        // Ví dụ dùng Bearer header, không dùng cookie credentials.
        cors.setAllowCredentials(false);

        // Browser có thể cache preflight theo giới hạn của nó.
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Giải thích từng lựa chọn:

- `allowedOrigins`: chỉ chứa những origin được ứng dụng cho phép, **không kèm path** như `/home`. Scheme, host, port phải khớp.
- `allowedMethods`: danh sách các method browser được phép gọi cross-origin; **không tự cấp quyền POST/DELETE** ở Spring Security. Nó chỉ là CORS policy.
- `allowedHeaders`: bao gồm **Authorization** và **Content-Type** nếu frontend gửi Bearer và JSON body. HTTP header names không phân biệt hoa/thường.
- `exposedHeaders`: cho phép frontend đọc response header **WWW-Authenticate** để hiểu lỗi authentication/authorization khi browser đang ở cross-origin context.
- `allowCredentials(false)`: ví dụ chỉ sử dụng token chủ động thêm vào header, **không cần CORS credentialed cookie session**. Nếu thiết kế dựa vào cookie, tham khảo mục 11.
- `maxAge`: browser có thể cache preflight theo policy riêng của browser; không làm token lâu hết hạn hơn.
- `registerCorsConfiguration("/api/**", ...)`: CORS policy được áp dụng trên đường dẫn API. Các route ngoài `/api/**` cần policy riêng nếu được gọi cross-origin.

**Lưu ý về cấu hình:** Khi khai báo `CorsConfigurationSource` tùy chỉnh, phải bảo đảm SecurityFilterChain sử dụng chính bean đó. Với nhiều bean cùng loại hoặc thiết lập MVC CORS song song, framework có thể không tự xác định được một source duy nhất; cần cấu hình rõ để tránh policy bất đồng.

### 6.4. SecurityFilterChain: CORS trước Bearer token authentication

~~~java
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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // Tích hợp CORS vào Spring Security filter chain.
            .cors(Customizer.withDefaults())

            // Chỉ áp dụng khi API dùng Bearer header, không dùng cookie.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET,
                    "/api/public/catalog").permitAll()

                .requestMatchers(
                    HttpMethod.GET,
                    "/api/orders",
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(
                    HttpMethod.POST,
                    "/api/orders")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.PATCH,
                    "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .anyRequest().denyAll())

            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Điều đáng chú ý:** Cấu hình trên **không khai báo một rule `OPTIONS /**.permitAll()`**. CORS processor tích hợp đúng có thể nhận diện và xử lý preflight trước khi đến logic yêu cầu Bearer token. Các request API thật vẫn phải thỏa mãn rule scope.

Trong ví dụ chỉ có một chain không giới hạn bằng `securityMatcher`, nên nó là chính sách áp dụng cho các request khác nữa với fallback `denyAll()`. Nếu ứng dụng dùng nhiều chains, cần xử lý riêng như mục 10.

Không tắt CSRF toàn ứng dụng chỉ vì một API có JWT. Khi backend vừa phục vụ API Bearer vừa phục vụ **web OIDC Login bằng cookie/session**, phải tách security chains và chiến lược CSRF phù hợp.

### 6.5. Controller ví dụ

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record CreateOrder(String productCode, int quantity) {}

@RestController
@RequestMapping("/api")
public class OrdersController {

    @GetMapping("/public/catalog")
    Map<String, Object> catalog() {
        return Map.of("items", List.of("BOOK-01"));
    }

    @GetMapping("/orders")
    Map<String, Object> listOrders() {
        // Minh họa response, chưa có truy vấn database.
        return Map.of("orders", List.of());
    }

    @PostMapping("/orders")
    ResponseEntity<Map<String, Object>> create(
            @RequestBody CreateOrder input) {
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("created", true));
    }
}
~~~

Controller dùng để quan sát behavior CORS/security, **không có quyền nghiệp vụ hoàn chỉnh**. Một hệ thống thực tế còn cần validate input, authorization theo user/tenant và kiểm soát owner của từng đơn hàng.

## 7. Browser gửi hai request khác nhau như thế nào?

### 7.1. Preflight của GET có Authorization header

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Trong luồng đúng, CORS processor xem origin `https://app.example.test` có nằm trong `allowedOrigins`, GET trong `allowedMethods`, và Authorization trong `allowedHeaders`. Nếu có, server phản hồi với các `Access-Control-Allow-*` tương ứng.

Sau đó browser gửi:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Ở **request thật**, `BearerTokenAuthenticationFilter` mới xác thực JWT bằng decoder. Nếu token hợp lệ nhưng thiếu `SCOPE_orders.read`, request vẫn bị từ chối **403 Forbidden** sau preflight thành công.

### 7.2. Preflight của POST JSON

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Preflight thành công cho phép browser gửi:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
Content-Type: application/json

{"productCode":"BOOK-01","quantity":2}
~~~

Vẫn phải yêu cầu `SCOPE_orders.write` trong Spring Security; việc CORS cho phép POST **không cấp quyền ghi**. CORS chỉ là điều kiện để browser **được gửi request**, không phải điều kiện để API **xử lý thành công**.

### 7.3. Không có Origin thì sao?

Một HTTP client không thuộc browser có thể gửi:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Không có `Origin`, request có thể được xử lý như một yêu cầu API thông thường mà không cần CORS response headers. Nó **vẫn phải qua JWT validation và authorization**. Thiếu Origin không phải bằng chứng caller đáng tin, cũng không phải lý do để bỏ yêu cầu Access Token.

## 8. CORS thành công nhưng API vẫn trả 401 hoặc 403

Nên phân biệt ít nhất bốn tình huống:

| Tình huống | Preflight | Request thật | Điều frontend thấy |
| --- | --- | --- | --- |
| Origin/Method/Headers được phép, Bearer token hợp lệ, scope đủ | Thành công. | 200/201 tùy API. | Đọc được response. |
| Preflight hợp lệ, request thật không có/sai token | Thành công. | **401 Unauthorized**. | Có thể đọc HTTP 401 nếu actual response có CORS headers. |
| Preflight hợp lệ, token đúng nhưng thiếu scope | Thành công. | **403 Forbidden**. | Có thể đọc HTTP 403 nếu actual response có CORS headers. |
| Origin hoặc headers không được CORS chấp nhận | Thất bại. | Browser thường **không gửi request thật**. | CORS/network error ở JavaScript. |

**Preflight thành công không bảo đảm request thật được cấp quyền.** Nó chỉ mở đường cho browser gửi request.

### 8.1. Ví dụ 401 sau preflight hợp lệ

Browser gửi GET nhưng token đã hết hạn:

~~~http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.test
WWW-Authenticate: Bearer error="invalid_token"
~~~

Đây là response API bình thường. Nếu CORS header có mặt và phù hợp, frontend có thể đọc `response.status === 401`. Nếu cấu hình đã expose `WWW-Authenticate`, frontend cũng có thể đọc header này qua `response.headers.get("WWW-Authenticate")`.

Không nên giải quyết lỗi này bằng cách thêm `permitAll()` cho API: token phải được làm mới hoặc client phải xác thực lại theo OAuth flow phù hợp.

### 8.2. Ví dụ 403 sau preflight hợp lệ

Token có `orders.read` nhưng client gọi POST:

~~~http
HTTP/1.1 403 Forbidden
Access-Control-Allow-Origin: https://app.example.test
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

CORS vẫn hoạt động. Lỗi nằm ở **authorization**: client không có `orders.write`. Refresh một token cùng quyền không tự làm phát sinh scope mới.

### 8.3. Khi actual 401/403 bị hiển thị thành “CORS error”

Nếu authentication/authorization handler trả 401/403 **mà không có `Access-Control-Allow-Origin`**, browser có thể chặn JavaScript đọc response. Frontend thường thấy lỗi CORS thay vì mã HTTP chính xác.

Do đó cấu hình cần bảo đảm **CORS processing diễn ra trước các security error handlers**, để response lỗi của request từ origin được phép vẫn có các CORS headers phù hợp. Điều này giúp frontend phân biệt **token sai** với **thiếu scope** mà không mở rộng quyền.

Nếu 401/403 do **API gateway, CDN hoặc reverse proxy** tạo ra trước khi request đến Spring Security, những response đó cũng cần CORS policy đúng cho origin hợp lệ. Chỉ cấu hình CORS ở Java backend không thể sửa các response bị chặn từ tầng mạng phía trước.

## 9. Có nên permitAll cho OPTIONS?

Không nên coi:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
~~~

là giải pháp CORS mặc định. Nó có ba vấn đề:

1. **Không tự tạo CORS headers** phù hợp để browser chấp nhận.
2. **Quy tắc authorization có thể chạy sau authentication filter**; nếu filter đã từ chối preflight thì `permitAll` quá muộn.
3. **Mở tất cả OPTIONS requests** có thể không phù hợp với những endpoint có OPTIONS nghiệp vụ hoặc với nhiều security chains.

Một số ứng dụng có yêu cầu cụ thể để allow OPTIONS tại gateway hoặc policy HTTP; đó phải là quyết định tường minh, không thay việc cấu hình **CORS source** và filter order.

### 9.1. Khi nào một OPTIONS request cần token?

Một **OPTIONS request không phải CORS preflight** có thể được API xử lý như HTTP request bình thường. Nó không tự được miễn xác thực chỉ vì method là OPTIONS.

Preflight chuẩn được nhận diện bởi:

- Method **OPTIONS**.
- Header **Origin**.
- Header **Access-Control-Request-Method**.

Nếu caller cố gửi `OPTIONS` tùy ý vào endpoint nội bộ để thực hiện nghiệp vụ, nó phải đi qua chính sách được thiết kế cho endpoint đó. **CORS filter được dùng để xử lý đúng preflight**, không làm tất cả OPTIONS trở thành một lỗ hổng quyền truy cập.

### 9.2. Nếu preflight trả 404/405?

Trường hợp thường gặp là CORS processor **không được tích hợp** hoặc request bị routing khác xử lý trước. Browser gửi OPTIONS nhưng nó đi đến DispatcherServlet/controller không khai báo OPTIONS, dẫn đến 404/405.

Giải pháp là kiểm tra **CORS filter và path registration** trước khi vội thêm `@RequestMapping(method=OPTIONS)` vào từng controller. Khi CORS được tích hợp đúng, một preflight hợp lệ thường được xử lý ở filter, không cần controller viết endpoint OPTIONS thủ công.

## 10. Nhiều SecurityFilterChain: đảm bảo OPTIONS vào đúng chain

Một ứng dụng có thể chia:

~~~text
/api/**       -> Bearer JWT Resource Server
/web/**       -> OIDC Login và HTTP session
/actuator/**  -> Management policy riêng
fallback      -> denyAll
~~~

Ở Spring Security:

- `http.securityMatcher(...)` quyết định **SecurityFilterChain nào áp dụng** cho request.
- `authorizeHttpRequests().requestMatchers(...)` quyết định **quyền bên trong chain đã chọn**.
- `@Order` xác định thứ tự ưu tiên giữa các chains; chain đầu tiên khớp được chọn.

### 10.1. Cấu hình API chain với CORS

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

Đây là **phương án cấu trúc nhiều chains**, thay thế chứ không triển khai đồng thời với một-chain example ở mục 6. Nhóm API ở ví dụ này dùng `authenticated()` để tập trung minh họa routing; trong production, thay bằng các **scope/authority rules** phù hợp từng endpoint.

Điều quan trọng là `securityMatcher("/api/**")` **không giới hạn method**: cả OPTIONS preflight và GET/POST thực đều đi vào cùng API chain, nơi có CORS processor.

### 10.2. Lỗi chain chỉ match GET/POST

Một cấu hình không cẩn thận có thể chọn chain dựa trên **method GET**:

~~~text
API chain: chỉ khớp GET /api/**
Preflight: OPTIONS /api/orders
         -> không khớp API chain
         -> rơi vào fallback chain
         -> bị chặn trước CORS policy của API
~~~

Lúc này GET có thể được cấp quyền trong test trực tiếp nhưng browser vẫn không gửi được GET thật do OPTIONS rơi vào chain khác. Hãy thiết kế chain matchers bao phủ **preflight và request thật** của cùng API, hoặc đặt CORS filter bên ngoài toàn bộ security chains theo kiến trúc đã được kiểm soát.

### 10.3. OIDC Login và session-cookie khác API Bearer

Khi backend phục vụ đồng thời:

- **Web routes** xác thực qua session/cookie sau `oauth2Login()`.
- **API routes** xác thực bằng `Authorization: Bearer`.

thì cần tách rõ:

1. CORS: origin nào được phép gọi endpoint nào?
2. CSRF: form/session-cookie có cần CSRF token không?
3. Session policy: browser web dùng session, API Bearer có thể stateless.
4. Entry points: web login có thể redirect, API thường trả 401 Bearer challenge.
5. CORS filter chain: preflight không bị điều hướng đến login page.

Đừng áp `csrf.disable()` hoặc `SessionCreationPolicy.STATELESS` lên mọi web route chỉ để giải quyết vấn đề preflight của API.

## 11. CORS, cookie credentials và CSRF khác nhau ra sao?

### 11.1. Bearer header và cookie session

Hai kiến trúc frontend có thể cùng dùng browser nhưng cơ chế credential khác:

| Kiến trúc | Credential request thực | Lưu ý chính |
| --- | --- | --- |
| **Bearer API** | Header `Authorization: Bearer ...` do client chủ động gửi. | CORS phải cho phép Authorization; JWT/opaque validation ở request thật. |
| **Web session** | Cookie do browser tự gửi theo cookie policy. | CORS credentials và CSRF/SameSite cần thiết kế cùng nhau. |
| **BFF (Backend for Frontend)** | Browser dùng session cookie với BFF; BFF gọi API server-side. | Browser có thể không trực tiếp mang Access Token; CSRF và cookie vẫn quan trọng ở BFF. |

Không có quy tắc rằng mọi API Spring Security dùng JWT đều phải để `allowCredentials=true`. Nếu không sử dụng cookie/certificate trong cross-origin credentialed request, cấu hình **không bật credentials** giúp giảm bề mặt và tránh nhầm lẫn.

### 11.2. Khi dùng cookies và credentials mode

Với cross-origin requests cần browser gửi cookies/session, CORS policy có thể phải trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

Frontend có thể dùng:

~~~javascript
fetch("https://api.example.test/web/profile", {
  credentials: "include"
});
~~~

Khi dùng credentialed requests, **không sử dụng `Access-Control-Allow-Origin: *`** để cho phép mọi origin. Server phải trả origin cụ thể được cho phép và không phản chiếu Origin một cách vô điều kiện. Cookies còn chịu các quy tắc **SameSite, Secure, Domain, Path**; CORS không tự khiến browser luôn gửi cookies.

**Quan trọng:** Nếu server dùng cookies để xác thực, **CORS không thay CSRF protection**. Một cross-origin simple request có thể được gửi và gây side effect trước khi browser kiểm soát khả năng JavaScript đọc response. Cookie tự gắn vào request là lý do CSRF phải được đánh giá riêng.

### 11.3. Ví dụ CSRF không bị CORS chặn một cách chắc chắn

Giả sử website ngân hàng dùng session cookie và một endpoint:

~~~http
POST /transfer HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=...

amount=100&to=another-account
~~~

Nếu request có dạng được browser gửi **không cần preflight**, CORS policy có thể chỉ ngăn script bên ngoài **đọc response**; nó không chắc chắn ngăn server xử lý chuyển tiền. Do đó cần CSRF token, SameSite cookie policy và các biện pháp chống CSRF phù hợp — **không được dùng CORS làm cơ chế bảo vệ duy nhất**.

### 11.4. “allowCredentials” không cấp quyền OAuth

`Access-Control-Allow-Credentials: true` là cơ chế browser/CORS. Nó **không có nghĩa JWT được tự động cấp scope**, không tự tạo session, cũng không thay `Authorization: Bearer`.

Ngược lại, `Access-Control-Allow-Credentials: false` không tự bảo vệ API khỏi mọi request không hợp lệ. Resource Server vẫn cần xác thực và phân quyền request thật.

## 12. Những cấu hình CORS không an toàn cần tránh

### 12.1. Mở tất cả origins vì phát triển cho nhanh

Ví dụ:

~~~java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowedMethods(List.of("*"));
cors.setAllowedHeaders(List.of("*"));
~~~

Với một API chứa dữ liệu nhạy cảm, cấu hình này mở khả năng đọc response cross-origin rộng hơn nhiều so với nhu cầu. Nó không xóa JWT authentication, nhưng có thể làm tăng khả năng truy cập từ trang web bên ngoài khi client đã có credential.

Cần đánh giá tập frontend được phép, đặc biệt nếu website còn dùng cookie/session. Không bật `allowCredentials(true)` với wildcard origin literal theo cách vi phạm CORS; Spring có thể từ chối tổ hợp cấu hình đó.

### 12.2. Tự phản chiếu Origin

Ví dụ nguy hiểm:

~~~java
// KHÔNG LÀM:
response.setHeader(
    "Access-Control-Allow-Origin",
    request.getHeader("Origin"));
~~~

Đoạn này tin Origin do caller gửi và mở access cross-origin cho bất kỳ website nào. `Origin` là input phục vụ **kiểm tra allowlist**, không phải giá trị server nên tin vô điều kiện.

### 12.3. Cho phép mọi subdomain không kiểm soát

Nếu frontend ở `app.example.test`, không nên vội cho phép `https://*.example.test`: một subdomain phục vụ nội dung người dùng tải lên hoặc bị chiếm quyền có thể trở thành origin được chấp thuận.

Spring cho phép cấu hình `allowedOriginPatterns` cho một số trường hợp cần match linh hoạt, nhưng phải xét:

- Ai có thể tạo subdomain?
- Subdomain có chạy JavaScript không đáng tin không?
- Có domain tên gần giống/IDN/port/scheme khác không?
- Có được phép gửi cookie credentials không?
- Các origin phát triển như localhost có bị đưa vào production không?

**Allowlist cụ thể** thường đơn giản và dễ kiểm tra hơn pattern quá rộng.

### 12.4. Dùng scheme HTTP trên frontend production

Origin `http://app.example.test` và `https://app.example.test` khác nhau. Không thêm HTTP origin vào production chỉ để browser hết báo CORS nếu web app cần HTTPS. CORS không giải quyết việc bảo vệ token trên đường truyền; API và frontend phải dùng TLS phù hợp.

### 12.5. Mở tất cả response headers

Không nên expose những headers mang thông tin nhạy cảm chỉ vì frontend muốn debug. `Access-Control-Expose-Headers` nên giới hạn vào headers thực sự cần đọc, ví dụ `WWW-Authenticate` hoặc request correlation ID.

Không bao giờ trả Bearer Access Token trong response header cho client không có quyền. **CORS expose headers không phải cách quản lý Access Token**.

## 13. Không nhầm CORS của Authorization Server với CORS của Resource Server

Trong một hệ thống OAuth 2.0 / OIDC có ít nhất hai địa chỉ:

~~~text
Authorization Server:
  https://identity.example.test

Resource Server API:
  https://api.example.test
~~~

Frontend có thể:

1. Điều hướng browser đến **Authorization Endpoint** của Authorization Server để login.
2. Nhận authorization code ở redirect URI của OAuth2 Client.
3. Dùng các cơ chế OAuth2 Client phù hợp (ví dụ Authorization Code + PKCE) để lấy Access Token.
4. Gửi Access Token đến **Resource Server** để gọi API.

CORS cho API Resource Server không tự cho frontend gọi **Authorization Server token endpoint** cross-origin. Token endpoint, discovery, JWKS, userinfo và authorization endpoint có các chính sách/contract riêng.

### 13.1. Không dùng fetch để thay authorization redirect

OAuth2 Authorization Endpoint thường được dùng qua **top-level browser navigation/redirect**, không phải một fetch cross-origin chờ JSON để hiển thị trang đăng nhập. Browser CORS cho `fetch` vào Authorization Endpoint có thể bị chặn theo thiết kế và không nên được “sửa” bằng mở CORS rộng rãi trên IdP.

### 13.2. CORS của API chỉ phục vụ request tới API

Cấu hình:

~~~java
source.registerCorsConfiguration("/api/**", cors);
~~~

chỉ áp dụng cho những request tới URL đã đăng ký tại chính Spring application đó. Nếu frontend gửi request đến IdP ở domain khác, **IdP** mới là nơi quyết định CORS. Nếu frontend gọi API qua gateway domain khác, **gateway và backend** phải phối hợp thống nhất về CORS.

### 13.3. API gateway có thể thay đổi behavior

Ví dụ:

~~~text
Browser
  -> https://gateway.example.test/api/orders
  -> API Gateway
  -> Spring Resource Server
~~~

Gateway có thể:

- Tự xử lý preflight OPTIONS và không forward đến Spring.
- Chặn OPTIONS vì policy gateway chỉ cho GET/POST.
- Yêu cầu Authorization ở gateway trước khi CORS chạy.
- Tự thêm hoặc xóa `Access-Control-Allow-Origin`.
- Trả 401/403 trước khi backend có cơ hội xử lý.

**Nếu gateway trả response, CORS phải được giải quyết ở gateway hoặc bởi một lớp nằm trước khi nó chặn request.** Cấu hình `http.cors()` ở backend không sửa được phản hồi bị tạo ra hoàn toàn ở tầng gateway.

Nên chọn rõ một nơi làm **source of truth** cho chính sách CORS, hoặc phối hợp các tầng để cùng chấp nhận một allowlist. Không để proxy và backend sinh nhiều `Access-Control-Allow-Origin` không nhất quán, vì browser có thể từ chối response.

## 14. Cache preflight, Vary và hiệu năng

### 14.1. Access-Control-Max-Age

Server trả:

~~~http
Access-Control-Max-Age: 1800
~~~

nghĩa là browser có thể cache kết quả preflight trong một khoảng thời gian gợi ý. Browser còn có giới hạn nội bộ riêng, nên không bảo đảm cache chính xác 1800 giây trên mọi browser.

**Preflight cache không phải token cache**. Nó không lưu Authentication của user, không kéo dài `exp` của JWT và không cho phép API bỏ bước xác thực token ở request thật.

### 14.2. Vary giúp tránh cache lẫn origins

Với server cho phép nhiều origins theo allowlist, response có thể khác nhau tùy Origin:

~~~http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Shared cache/CDN cần tôn trọng những chiều biến thiên đó để không phát response CORS của origin A cho origin B. `CorsFilter` chuẩn thường xử lý các headers liên quan, nhưng proxy phía trước vẫn có thể cache/sửa response; phải kiểm tra hành vi end-to-end.

### 14.3. Không thay đổi CORS policy mà quên cache

Nếu vừa loại bỏ một origin khỏi allowlist, browser có thể giữ **preflight cache cũ** trong thời gian ngắn. Mặc dù preflight cached, **request thật vẫn phải đi qua CORS check và authentication** ở server. Không dựa riêng vào preflight như biện pháp thực thi quyền đối với dữ liệu.

Đối với response chứa dữ liệu user nhạy cảm, cache HTTP nên có chính sách riêng như `Cache-Control` phù hợp. Đừng trộn preflight cache với response caching hay JWT caching.

## 15. Kiểm thử bằng curl: mô phỏng preflight đúng

**curl không tự thực thi CORS policy** như browser, nhưng có thể dùng để quan sát những headers server trả cho một request mô phỏng preflight.

### 15.1. Preflight hợp lệ

~~~bash
curl -i -X OPTIONS \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Kết quả mong đợi (phụ thuộc triển khai):

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-ID
~~~

**Không cần gửi Bearer token** trong lệnh mô phỏng preflight. Nếu nhận 401 Bearer challenge, kiểm tra CORS filter order và nơi nào đã yêu cầu token trước CORS processor.

### 15.2. Preflight từ origin không được phép

~~~bash
curl -i -X OPTIONS \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://evil.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Với Spring CORS processor, origin không được cho phép thường nhận phản hồi **403 Invalid CORS request** hoặc không có CORS allowance phù hợp. Browser sẽ **không gửi request thật** khi preflight bị từ chối.

Không yêu cầu mọi hệ thống phải dùng đúng message body “Invalid CORS request”; chỉ cần chính sách không cấp quyền CORS cho origin không được phép.

### 15.3. Request API thật không có token

~~~bash
curl -i \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://app.example.test'
~~~

Dự kiến:

~~~http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.test
WWW-Authenticate: Bearer
~~~

Response được phép có CORS header nhưng **không có token nên API vẫn 401**. Đây là behavior mong muốn; không phải CORS bị hỏng.

### 15.4. Request API thật với token

~~~bash
curl -i \
  'https://api.example.test/api/orders' \
  -H 'Origin: https://app.example.test' \
  -H 'Authorization: Bearer TEST_ACCESS_TOKEN'
~~~

Nếu token thực sự hợp lệ, đúng issuer/audience và có scope đọc, request có thể qua HTTP authorization. Nếu không, API trả 401 hoặc 403 tùy lỗi. Đừng paste Access Token thật vào terminal được ghi history/log dùng chung; với thử nghiệm nên dùng fixture token hoặc cách xử lý secrets an toàn.

**Lưu ý:** curl luôn gửi request thật khi được yêu cầu; nó không tự dừng sau một preflight không thành công như browser. Do đó test curl cần được kết hợp với test browser hoặc MockMvc để xác nhận security behavior đúng.

## 16. Kiểm thử Spring Security CORS bằng MockMvc

Mục tiêu test:

1. Preflight hợp lệ **không yêu cầu Bearer token**.
2. Origin không được phép **không nhận CORS allowance**.
3. Request thật vẫn yêu cầu JWT.
4. CORS success không tự cấp scope.
5. HTTP 401/403 của request thật vẫn có CORS headers để frontend đọc response.

### 16.1. Ví dụ test với SpringBootTest

Giả sử `ApiCorsConfig`, `ApiSecurityConfig` và `OrdersController` ở mục 6 được dùng. Test định nghĩa decoder giả chỉ để tránh cần kết nối tới Authorization Server khi khởi tạo application context; các request `with(jwt())` tạo Authentication test mà **không gọi decoder**.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(CorsPreflightHttpTest.TestDecoder.class)
class CorsPreflightHttpTest {

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException(
                    "Synthetic decoder rejects raw tokens");
            };
        }
    }

    @Test
    void validPreflightDoesNotRequireBearerToken() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                containsString("Authorization")));
    }

    @Test
    void unknownOriginIsRejected() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://evil.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualRequestStillRequiresJwt() throws Exception {
        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"));
    }

    @Test
    void validPrincipalWithReadScopeCanAccessGet()
            throws Exception {
        mvc.perform(get("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isOk());
    }

    @Test
    void readerCannotPostEvenIfCorsAllowsPost()
            throws Exception {
        mvc.perform(post("/api/orders")
                .header(HttpHeaders.ORIGIN,
                    "https://app.example.test")
                .contentType("application/json")
                .content("{\"productCode\":\"BOOK-01\",\"quantity\":2}")
                .with(jwt().authorities(
                    new SimpleGrantedAuthority(
                        "SCOPE_orders.read"))))
            .andExpect(status().isForbidden())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"));
    }
}
~~~

Các test trên chứng minh **CORS + HTTP authorization** nếu ứng dụng có đủ controller và beans trong ví dụ. Khi dự án đã định nghĩa `JwtDecoder` production riêng, cần điều chỉnh bean test để không tạo xung đột. Nếu thay controller thật hoặc đường dẫn policy khác, cập nhật expected status tương ứng.

**Quan trọng:** `with(jwt())` của `spring-security-test` tạo principal đã xác thực trực tiếp, **không kiểm tra chữ ký JWT, issuer, audience hoặc expiration**. Vì vậy, test cần thêm riêng decoder bằng JWT được ký với test key. Còn preflight test quan sát path có Origin/Access-Control-Request-Method và không có Authorization header.

### 16.2. Test OPTIONS không phải preflight

Để tránh vô tình mở mọi OPTIONS, bổ sung test:

~~~java
mvc.perform(options("/api/orders"))
    .andExpect(status().isForbidden());
~~~

Với **SecurityFilterChain một-chain có `anyRequest().denyAll()`**, OPTIONS không có Origin/Access-Control-Request-Method sẽ không được CORS filter xử lý như preflight; nếu request không có authentication, tùy entry point của Spring Security, mã có thể là **401 thay vì 403**. Trong test thực tế, hãy xác nhận **nó không được cho phép** theo policy thay vì cứng nhắc mặc định một mã HTTP. Nếu muốn test chính xác status, đưa cả authentication fixture để tránh khác biệt anonymous/entry point.

### 16.3. Test sai method và sai header

Ví dụ preflight hỏi dùng method không nằm trong allowed methods:

~~~java
mvc.perform(options("/api/orders")
        .header(HttpHeaders.ORIGIN,
            "https://app.example.test")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
            "TRACE"))
    .andExpect(status().isForbidden());
~~~

Với request header chưa được cho phép:

~~~java
mvc.perform(options("/api/orders")
        .header(HttpHeaders.ORIGIN,
            "https://app.example.test")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
            "x-unapproved-header"))
    .andExpect(status().isForbidden());
~~~

Những bài test này xác nhận policy không đơn thuần cho qua mọi OPTIONS request có Origin hợp lệ.

### 16.4. Cần kiểm tra request không gọi JwtDecoder ở preflight?

Một test nâng cao có thể dùng một `JwtDecoder` spy/mock và xác nhận không có lời gọi `decode` khi browser gửi **OPTIONS preflight hợp lệ không chứa Authorization header**. Tuy nhiên, nếu test chỉ tạo decoder giả và preflight không mang token, decoder thường không được gọi trong mọi trường hợp; quan trọng hơn là response **được CORS processor cho phép trước yêu cầu authentication** và endpoint thật vẫn được bảo vệ.

Nên có integration test với **frontend/browser thật** hoặc một test browser automation để xác nhận trình duyệt thực sự gửi request GET/POST sau khi OPTIONS thành công. MockMvc không mô phỏng hoàn toàn browser CORS enforcement, preflight caching hoặc network proxy.

## 17. Khi frontend còn báo lỗi, tìm nguyên nhân theo từng lớp

### 17.1. Ma trận triệu chứng và nguyên nhân

| Triệu chứng | Khả năng nguyên nhân | Việc cần kiểm tra |
| --- | --- | --- |
| OPTIONS trả **401 Bearer** | Authentication chạy trước CORS hoặc preflight rơi vào chain khác. | `http.cors()`, `CorsConfigurationSource`, filter chain order, gateway. |
| OPTIONS trả **403 Invalid CORS request** | Origin/method/headers không được allowlist hoặc không match CORS path. | `allowedOrigins`, `allowedMethods`, `allowedHeaders`, `/api/**`. |
| OPTIONS trả 404/405 | CORS filter không xử lý, request đi tới routing/controller. | Filter registration/chain selection trước khi thêm OPTIONS controller. |
| OPTIONS trả 200 nhưng thiếu `Access-Control-Allow-Origin` | Response không phải CORS approval hợp lệ. | CORS source, Origin và proxy headers. |
| OPTIONS trả 200, ACAO đúng nhưng thiếu Authorization trong Allow-Headers | Browser không được gửi Bearer header. | Danh sách `allowedHeaders`. |
| GET thực trả 401 | Bearer token thiếu, sai chữ ký/audience/issuer/exp. | Decoder và auth entry point, không mở public endpoint. |
| POST thực trả 403 | Token đúng nhưng thiếu write scope hoặc quyền domain. | `SCOPE_orders.write`, policy dữ liệu. |
| API trả 401/403 nhưng JavaScript chỉ thấy CORS error | Response lỗi thiếu ACAO hoặc proxy chặn trước backend. | CORS on error responses, gateway/CDN. |
| Chạy curl thành công nhưng browser lỗi | curl không enforce CORS. | DevTools Network, OPTIONS và CORS response headers. |
| Dev hoạt động, production lỗi | Khác scheme/host/port, CDN hoặc HTTPS reverse proxy. | Origin production, gateway, environment config. |
| Cookie không được gửi | Credentials mode/SameSite/Secure/Domain/CORS policy chưa phù hợp. | Cookie policy và CORS credentials; kiểm tra CSRF riêng. |
| CORS có lúc hoạt động, có lúc sai origin | Shared cache không tôn trọng Vary hoặc nhiều node config khác nhau. | CDN/cache `Vary`, deployment consistency. |

### 17.2. Dùng DevTools đúng cách

Trong Chrome/Firefox/Safari DevTools:

1. Mở **Network**, bật lọc Fetch/XHR hoặc xem request theo path.
2. Tìm request **OPTIONS** trước request GET/POST.
3. Đọc **Request Headers**: Origin, Access-Control-Request-Method, Access-Control-Request-Headers.
4. Đọc **Response Headers**: Access-Control-Allow-Origin/Methods/Headers, Vary và status.
5. Nếu OPTIONS thành công, kiểm tra **request thật** có Authorization header và response 401/403/2xx không.
6. Nếu không thấy OPTIONS, xét browser cache preflight hoặc request có thuộc nhóm cần preflight không.
7. Nếu gateway/redirect xuất hiện, kiểm tra URL thực, status và nơi response được tạo.

Tránh sao chép Bearer Token từ DevTools vào ticket/chat/screenshot công khai. Có thể che header/token và chỉ chia sẻ status, Origin, method, names của headers cùng request ID.

### 17.3. Không sửa lỗi CORS bằng cách tắt Spring Security

Một phản ứng nguy hiểm:

~~~java
// KHÔNG LÀM để "sửa CORS".
.authorizeHttpRequests(auth -> auth
    .anyRequest().permitAll())
~~~

Hoặc:

~~~java
// KHÔNG LÀM trong môi trường thật chỉ để né OPTIONS:
.oauth2ResourceServer(oauth -> { })
~~~

Những thay đổi này có thể làm mất bảo vệ Bearer token trên API. **Đúng hướng là sửa policy CORS và filter order**, giữ nguyên yêu cầu xác thực và phân quyền request thật.

## 18. Những trường hợp đặc biệt cần nhận diện

### 18.1. Preflight bị redirect

Browser gửi:

~~~text
OPTIONS https://api.example.test/api/orders
~~~

nhưng proxy trả:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/sign-in
~~~

Đây là dấu hiệu preflight bị xử lý như một request chưa đăng nhập. CORS preflight không nên bị điều hướng qua login UI; nó cần được trả lời bằng CORS headers phù hợp tại resource origin, **trước yêu cầu Bearer token**. Một số trình duyệt/môi trường xử lý redirects trên preflight khác nhau, nên tốt nhất tránh phụ thuộc vào redirect để cho phép preflight.

### 18.2. HTTPS redirect ở proxy

Nếu client frontend gọi `http://api.example.test` và server redirect sang HTTPS, preflight có thể bị ảnh hưởng bởi redirect hoặc mixed-content policy. Frontend nên dùng **URL HTTPS cuối cùng** ngay từ đầu. Không dùng CORS workaround để cho phép truyền Bearer token qua HTTP.

### 18.3. Gateway thực hiện auth trước CORS

Một gateway có JWT plugin có thể yêu cầu Authorization trên **mọi** method, kể cả OPTIONS. Khi đó Spring Resource Server phía sau dù có `http.cors()` vẫn không thấy OPTIONS.

Hãy điều chỉnh thứ tự gateway: xử lý CORS preflight hợp lệ trước auth tại gateway, hoặc cấu hình một CORS layer phù hợp ở trước JWT/auth plugin. **Không** mở request thật như GET/POST theo cách tương tự.

### 18.4. Reverse proxy thay đổi path

Ví dụ browser gọi:

~~~text
https://gateway.example.test/orders-api/api/orders
~~~

nhưng proxy rewrite thành:

~~~text
/api/orders
~~~

`CorsConfigurationSource` trong Spring phải match **path mà ứng dụng thực sự nhận**, không phải tự suy từ URL trước proxy. Nếu đăng ký `/api/**` nhưng backend nhìn thấy `/orders-api/api/**`, CORS policy có thể không áp dụng.

### 18.5. CORS response bị thêm hai lần

Nếu cả gateway và Spring đều đặt:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

và hạ tầng biến thành hai giá trị header không hợp lệ, browser có thể từ chối response. Nên quy định rõ nơi phát CORS headers và bảo đảm các tầng không sinh các giá trị xung đột. Chỉ cho phép origin đã được phê duyệt, không tự phản chiếu bất kỳ Origin nào.

### 18.6. Nội dung tải xuống hoặc streaming

Nếu frontend cần đọc `Content-Disposition` để lấy tên file hoặc `X-Request-ID` để tracing, có thể phải thêm tên header vào **`exposedHeaders`**. Đây là quyền **đọc response header** từ JavaScript, không phải permission tải file; endpoint vẫn phải xác thực token và kiểm tra quyền dữ liệu.

### 18.7. Phương thức ngoài GET/POST

Các method như PATCH, DELETE, HEAD, OPTIONS và những method ứng dụng tự định nghĩa cần được xét rõ:

- Có được dùng cross-origin không?
- Có handler thực ở backend không?
- Có rule JWT scope phù hợp không?
- Browser sẽ preflight trong trường hợp nào?
- Proxy/gateway có forward và kiểm soát chúng nhất quán không?

Cho phép `DELETE` trong `Access-Control-Allow-Methods` **không** cho phép người dùng xóa tài nguyên. Nó chỉ xác nhận browser có thể gửi method cross-origin; authorization vẫn cần được kiểm tra.

## 19. Mối quan hệ với trạng thái web và các security headers khác

Trong chương **Trạng thái và bảo vệ web**, cần nhìn CORS trong bức tranh rộng hơn của browser security:

| Cơ chế | Mục tiêu | Không thay thế được |
| --- | --- | --- |
| **CORS** | Kiểm soát browser cross-origin request/response sharing. | JWT validation, authorization, CSRF. |
| **CSRF protection** | Chống request gây side effect ngoài ý muốn khi browser tự đính kèm credential. | CORS policy hoặc phân quyền dữ liệu. |
| **SameSite/Secure cookies** | Hạn chế cách browser gửi cookie và bảo vệ cookie qua HTTPS. | Xác minh Bearer token, CORS allowlist. |
| **Content Security Policy (CSP)** | Giảm một số nguy cơ nạp/thực thi nội dung không đáng tin. | OAuth scope, CORS, authorization. |
| **HTTPS/TLS** | Bảo vệ dữ liệu trên đường truyền, nhận diện server. | Quyết định origin, token scope, owner/tenant. |
| **JWT/opaque token validation** | Xác minh credential do nguồn đáng tin cấp cho đúng API. | CORS, CSRF, resource-level authorization. |
| **HTTP/domain authorization** | Quyết định user/client có quyền trên endpoint và tài nguyên. | CORS hoặc TLS. |

Trong một ứng dụng **BFF dùng session cookie**, thay đổi CORS có thể ảnh hưởng browser web, nhưng **không được tắt CSRF** chỉ để preflight qua được. Trong một **Bearer Resource Server stateless**, cookie không được dùng làm credential nên policy CSRF có thể khác. Hãy xác định chính xác kiến trúc credential của từng đường dẫn.

## 20. Những ngộ nhận và lỗi thường gặp

| Ngộ nhận | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| “Frontend có JWT hợp lệ thì OPTIONS cũng phải gửi JWT.” | Browser preflight thường không mang Bearer credential. | Xử lý CORS trước authentication. |
| “permitAll OPTIONS là đủ cho CORS.” | Không tự sinh CORS headers, auth filter có thể chạy trước. | `http.cors()` + CORS source/gateway đúng thứ tự. |
| “CORS 200 nghĩa API request cũng 200.” | Preflight và request thật là hai request khác nhau. | JWT/scope check vẫn áp cho GET/POST/PATCH. |
| “CORS chặn được curl/Postman.” | CORS được browser enforce. | Resource Server vẫn phải kiểm tra token và quyền. |
| “Access-Control-Allow-Headers: Authorization nghĩa JWT hợp lệ.” | Chỉ cho phép browser gửi tên header. | `JwtDecoder` hoặc introspection mới xác thực token. |
| “CORS trả 403 luôn là user thiếu scope.” | CORS 403 có thể do Origin/method/header. | Phân loại preflight và actual request. |
| “JWT trả 401 thì phải tắt Security để hết lỗi CORS.” | Có thể token thật sự invalid. | Đảm bảo CORS header trên 401, sửa authentication riêng. |
| “Origin lấy từ header thì phải phản chiếu lại.” | Header do caller gửi, không phải trusted allowlist. | So Origin với allowlist trước khi trả ACAO. |
| “Wildcard origin an toàn với cookie.” | Credentialed CORS cần origin cụ thể và bảo vệ CSRF. | Cấu hình origins rõ, cookies/CSRF riêng. |
| “CORS thay cho CSRF.” | Simple requests có thể gây side effect dù không đọc được response. | CSRF protection khi browser tự gửi session credential. |
| “Các route ngoài /api/** cũng được CORS nếu có bean.” | Registration path/chain có thể không bao phủ. | Thiết kế CORS policies cho từng nhóm endpoint. |
| “MockMvc jwt() kiểm tra cả preflight và token signature.” | Helper tạo Authentication giả, bỏ qua JwtDecoder. | Test CORS + JWT decoder ký thật ở tầng riêng. |
| “curl GET thành công thì browser GET chắc chắn thành công.” | curl không tạo/check preflight. | Mô phỏng OPTIONS và kiểm thử browser thực. |
| “Mở CORS ở backend sửa được gateway 401.” | Gateway đã từ chối trước backend. | Sửa CORS/auth order tại gateway. |
| “Preflight cache giúp JWT khỏi hết hạn.” | Cache CORS và token hoàn toàn khác nhau. | Request thật luôn kiểm tra token theo security design. |

## 21. Quy trình triển khai an toàn

1. **Vẽ sơ đồ các origins:** frontend, API gateway, Resource Server và Authorization Server. Ghi rõ scheme/host/port của từng origin.
2. **Xác định credential flow:** API nhận Bearer header hay web dùng cookie/session? Có BFF không? Không áp một chính sách CSRF/CORS cho mọi nơi khi credential khác nhau.
3. **Lập allowlist frontend origins:** chỉ cho phép những domain thực sự vận hành ứng dụng; tách dev/staging/prod.
4. **Lập danh sách method và headers:** GET/POST/PATCH/DELETE nào được frontend dùng; có Authorization và Content-Type JSON không?
5. **Đặt CORS xử lý trước authentication:** dùng `http.cors()` với `CorsConfigurationSource` hoặc cấu hình gateway tương đương, tránh buộc preflight mang Bearer token.
6. **Giữ request thật được bảo vệ:** JWT/opaque validation, audience, issuer, expiration, scope/authority và domain authorization.
7. **Kiểm tra multiple chains và path rewrite:** OPTIONS và GET/POST của cùng API phải gặp đúng CORS policy; có fallback security chain cho URL khác.
8. **Kiểm tra 401/403 actual response:** origin được phép phải nhận CORS headers phù hợp ngay cả khi token invalid hoặc scope thiếu; không sửa bằng `permitAll()`.
9. **Không bật credentials vô cớ:** với cookie/session, cấu hình allowCredentials, SameSite, Secure và CSRF có chủ đích; không wildcard origin với credentialed response.
10. **Kiểm thử âm tính:** origin lạ, method lạ, custom header không được phép, no-token OPTIONS, no-token GET, invalid token, insufficient scope, gateway errors.
11. **Kiểm tra browser DevTools và reverse proxy:** xác nhận preflight thành công trước actual request và không có redirect/login page hay duplicate CORS headers.
12. **Theo dõi vận hành:** phân biệt `cors_preflight_denied`, `invalid_token`, `insufficient_scope`, gateway timeout và auth provider outage; không log Bearer token.

**Ghi nhớ:** **CORS preflight là lời hỏi của browser trước request thật**, thường **không chứa Bearer token**. Trong Spring Security Resource Server, cần để **CORS được xử lý trước khi yêu cầu authentication**, bằng CORS filter/configuration source hoặc gateway được thiết kế đúng. **Chỉ preflight mới được cho qua theo CORS policy; request GET/POST/PATCH/DELETE thực vẫn phải xác thực token và kiểm tra quyền.** CORS không thay JWT validation, CSRF hay authorization trên dữ liệu.

## Tài liệu tham khảo

- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- [Spring Security — Multiple HttpSecurity instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html).
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- [MDN — Preflight request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request).
- [Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
