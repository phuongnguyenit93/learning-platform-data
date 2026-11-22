# ServerBearerTokenAuthenticationConverter và nguồn token đầu vào

## 1. Vấn đề: token đến Resource Server bằng đường nào?

Một API dùng **Spring WebFlux + Spring Security OAuth 2.0 Resource Server** thường nhận access token qua HTTP Authorization header:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9...
~~~

Nhưng hệ thống thực tế có thể xuất hiện nhiều biến thể:

- Client chuẩn gửi **Authorization: Bearer ACCESS_TOKEN**.
- Một reverse proxy chuyển credential qua header khác.
- Client cũ đặt token trong **URI query parameter**.
- Client cũ dùng **application/x-www-form-urlencoded body parameter**.
- Request có **nhiều nguồn token** và các giá trị mâu thuẫn.
- WebSocket handshake, SSE, gateway hoặc ứng dụng browser khiến người viết code muốn chọn đường khác để truyền token.

Trước khi kiểm tra chữ ký JWT, issuer, audience hay scope, Resource Server phải quyết định **đọc credential nào từ HTTP request**. Trong **kiến trúc WebFlux**, một thành phần quan trọng thực hiện việc đó là:

**ServerBearerTokenAuthenticationConverter**

Đây là một **ServerAuthenticationConverter** đọc HTTP request trong **ServerWebExchange** và tạo một yêu cầu Authentication chứa Bearer token **chưa được xác thực**.

Điểm cốt lõi:

> Converter trích xuất credential từ request; nó **không quyết định token có hợp lệ hay được cấp quyền không**. Đó là việc của ReactiveAuthenticationManager, ReactiveJwtDecoder hoặc ReactiveOpaqueTokenIntrospector, và authorization policy ở phía sau.

Nếu không phân biệt hai trách nhiệm này, lập trình viên có thể vô tình tin JWT payload chưa xác minh, chấp nhận token từ nguồn không an toàn hoặc viết thêm filter xác thực chồng lên OAuth Resource Server chuẩn.

## 2. Vị trí trong kiến trúc WebFlux

Spring WebFlux sử dụng mô hình **reactive**, dựa trên **Publisher/Mono/Flux**, khác với Servlet API truyền thống.

Sơ đồ luồng khái niệm:

~~~text
HTTP request
  |
  v
WebFlux WebFilter chain
  |
  v
Spring Security WebFilterChainProxy
  |
  v
AuthenticationWebFilter (Resource Server Bearer)
  |
  +-- ServerBearerTokenAuthenticationConverter
  |      ServerWebExchange -> Mono<Authentication>
  |      Trích Bearer token từ nguồn được phép
  |
  v
ReactiveAuthenticationManager
  |
  +-- JWT: ReactiveJwtDecoder, JWT validators
  |      signature, alg, iss, aud, exp, nbf, token profile
  |
  +-- Opaque: ReactiveOpaqueTokenIntrospector
         hỏi Authorization Server về trạng thái token
  |
  v
Authenticated principal + GrantedAuthorities
  |
  v
ReactiveSecurityContextHolder / authorization
  |
  v
Handler / domain service
~~~

Các vai trò:

| Thành phần | Mục đích |
|---|---|
| **ServerWebExchange** | Request/response và context của HTTP exchange trong WebFlux |
| **ServerAuthenticationConverter** | Chuyển request thành một yêu cầu Authentication trong Mono |
| **ServerBearerTokenAuthenticationConverter** | Trích credential Bearer từ header hoặc nguồn được cho phép |
| **BearerTokenAuthenticationToken** | Mang chuỗi token thô, **chưa xác thực** |
| **AuthenticationWebFilter** | Điều phối converter, ReactiveAuthenticationManager và kết quả xác thực |
| **ReactiveAuthenticationManager** | Xác thực credential bằng decoder/introspection phù hợp |
| **ReactiveJwtDecoder** | Xác minh JWT và validators |
| **ReactiveOpaqueTokenIntrospector** | Kiểm tra opaque token qua introspection |
| **SecurityWebFilterChain** | Chuỗi WebFilter bảo vệ các exchanges |
| **ServerHttpSecurity** | DSL cấu hình Spring Security cho WebFlux |
| **ReactiveSecurityContextHolder** | Truy cập SecurityContext theo Reactor Context |
| **Reactive AuthorizationManager / method security** | Quyết định truy cập sau authentication |

Không dùng các kiểu Servlet làm ví dụ chính:

~~~text
Servlet:
  HttpServletRequest
  DefaultBearerTokenResolver
  SecurityFilterChain
  HttpSecurity
  BearerTokenAuthenticationFilter

WebFlux:
  ServerWebExchange
  ServerBearerTokenAuthenticationConverter
  SecurityWebFilterChain
  ServerHttpSecurity
  AuthenticationWebFilter
~~~

Hai stack cùng tuân theo Bearer semantics nhưng **extension points và kiểu dữ liệu khác nhau**. Mang một HttpServletRequest-based resolver vào WebFlux không giải quyết được bài toán tại ServerWebExchange.

## 3. API của ServerBearerTokenAuthenticationConverter

Trong Spring Security hiện đại, class thuộc package:

~~~java
org.springframework.security.oauth2.server.resource.web.server.authentication
    .ServerBearerTokenAuthenticationConverter
~~~

Class triển khai:

~~~java
org.springframework.security.web.server.authentication
    .ServerAuthenticationConverter
~~~

Chữ ký khái niệm của interface:

~~~java
public interface ServerAuthenticationConverter {

    Mono<Authentication> convert(ServerWebExchange exchange);
}
~~~

**Không cần định nghĩa lại interface** này trong ứng dụng; Spring Security đã cung cấp. Điểm cần nhớ là kết quả trả về **Mono<Authentication>**, không phải một chuỗi token thô và không phải kiểu Servlet Authentication kết quả đã xác thực.

Các tình huống đầu ra:

| HTTP request | Kết quả converter về mặt logic |
|---|---|
| Không có Bearer credential từ nguồn được cấu hình | **Mono.empty()**: converter không tạo authentication request |
| Có Bearer token hợp lệ về hình thức | **Mono** phát ra BearerTokenAuthenticationToken chưa xác thực |
| Có credential malformed/không hợp lệ theo transport policy | **Mono.error(...)**, thường là OAuth2AuthenticationException tương ứng |
| Có token nhưng chữ ký JWT sai | Converter vẫn có thể phát ra credential; **decoder mới bác bỏ** |
| Có token nhưng thiếu scope | Converter vẫn có thể phát ra credential; **authorization mới bác bỏ** |

### Mono.empty() không có nghĩa endpoint công khai

Khi converter trả Mono.empty(), điều đó chỉ có nghĩa **không trích được credential phù hợp**. Tại endpoint **permitAll**, request có thể tiếp tục. Tại endpoint **authenticated()**, authorization sẽ yêu cầu authentication và thường trả **401 Bearer challenge**.

~~~text
Converter: Mono.empty()
   |
   +-- /api/public/info  -> có thể được phép
   |
   +-- /api/orders       -> 401 nếu policy yêu cầu auth
~~~

**Không viết code coi Mono.empty() tương đương authentication thành công.**

### BearerTokenAuthenticationToken còn chưa xác thực

Converter có thể tạo:

~~~java
new BearerTokenAuthenticationToken(rawToken)
~~~

Đối tượng này chứa credential người gọi trình bày. Nó **không nói token đã có chữ ký đúng**, không được dùng claim JWT hoặc tên người dùng chưa xác minh làm principal tin cậy.

## 4. Nguồn mặc định: HTTP Authorization header

Theo cấu hình mặc định, Resource Server WebFlux tìm Bearer token trong:

~~~http
Authorization: Bearer ACCESS_TOKEN
~~~

Đây là phương thức truyền được khuyến nghị trong RFC 6750, phù hợp với HTTP authentication framework.

Ví dụ:

~~~bash
curl -i https://orders.example.com/api/orders \
  -H 'Authorization: Bearer ACCESS_TOKEN'
~~~

Trong Java reactive client:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("https://orders.example.com")
        .build();

Mono<String> result = webClient.get()
        .uri("/api/orders")
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(String.class);
~~~

Đoạn code là một ví dụ **client gửi credential**, không phải implementation của converter trong Resource Server.

### Vì sao nên chọn header?

- Đúng mục đích của HTTP authentication.
- Tách Bearer credential khỏi URL và application request body.
- Ít nguy cơ ghi token vào browser history/query logs hơn cách truyền qua URI.
- Dễ cấu hình gateway loại bỏ token trước khi log headers.
- Dùng được với nhiều HTTP methods, body types và reactive streaming.
- Giúp một nơi thống nhất quản lý Bearer token source.

**Authorization header cũng chứa credential bí mật**, nên không được log nguyên nó. Dùng TLS, không chia sẻ token qua URL, đặt giới hạn request/header size phù hợp và kiểm soát forwarding ở proxy.

## 5. Cách converter đọc Bearer header

Hãy phân biệt:

~~~http
Authorization: Bearer eyJhbGciOi...
~~~

với:

~~~http
Authorization: Basic dXNlcjpwYXNz
~~~

và:

~~~http
Authorization: DPoP ...
~~~

**ServerBearerTokenAuthenticationConverter** trích token theo **Bearer scheme** mà nó được cấu hình hỗ trợ, không mặc định nhận bất kỳ authentication scheme nào.

Các trường hợp:

| Header | Diễn giải |
|---|---|
| Authorization: Bearer abc | Bearer credential có thể được chuyển cho authentication manager |
| Authorization: bearer abc | Theo HTTP scheme semantics, tên scheme không phân biệt hoa/thường; implementation xử lý theo cú pháp được hỗ trợ |
| Authorization: Basic abc | Không phải Bearer credential cho converter này |
| Không có Authorization | Converter thường không tạo credential |
| Authorization: Bearer | Sai/thiếu token; lỗi transport phụ thuộc parser |
| Authorization: Bearer abc def | Có thể malformed theo cú pháp Bearer |
| Hai Authorization headers | Proxy/container có thể chuẩn hóa khác nhau; cần kiểm tra chính sách thực tế |

**Quan trọng:** Converter quyết định **có thể trích token**; **ReactiveJwtDecoder** hoặc **ReactiveOpaqueTokenIntrospector** quyết định token đó có được chấp nhận hay không. Một chuỗi không có chữ ký hợp lệ vẫn có thể vượt qua bước extract nhưng sẽ bị reject ở authentication.

### Không có nghĩa converter decode JWT

Một JWT thường có ba phần được ngăn bằng dấu chấm. Opaque token có thể là chuỗi ngẫu nhiên không có cấu trúc đó. Converter chỉ lấy **credential string**, không tự biến nó thành JWT, không xác minh JWT signature hay kiểm tra issuer.

~~~text
Authorization: Bearer abc.def.ghi
  -> converter trích abc.def.ghi
  -> ReactiveJwtDecoder verify và validate
  -> token invalid nếu không đúng

Authorization: Bearer opaque-random-id
  -> converter trích opaque-random-id
  -> ReactiveOpaqueTokenIntrospector hỏi AS
  -> active/inactive theo response đáng tin
~~~

Do đó cùng một converter có thể phục vụ **JWT Resource Server** và **opaque token Resource Server**, còn backend authentication manager khác nhau.

## 6. Cấu hình WebFlux Resource Server giữ nguồn mặc định

Với Spring Boot, một cấu hình JWT Resource Server có thể dùng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

WebFlux Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersWebFluxSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/public/**").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

**Không cần tự tạo converter** khi chỉ nhận token từ Authorization header mặc định. Resource Server DSL thiết lập bộ nhận Bearer token phù hợp.

Khác Servlet:

~~~java
// WebFlux:
SecurityWebFilterChain api(ServerHttpSecurity http)

// KHÔNG phải cấu hình WebFlux:
SecurityFilterChain api(HttpSecurity http)
~~~

### Các giới hạn của ví dụ

- Issuer phải được tin cậy và discovery/JWKS phải chính xác.
- Cần kiểm tra **audience** dành cho orders-api và access-token profile; chỉ có issuer-uri không tự thay thế mọi validators.
- Authorities **SCOPE_...** được lấy từ scope của token đã xác thực theo mapping mặc định phù hợp.
- Một user có scope write vẫn có thể bị domain policy từ chối thao tác với order cụ thể.
- CSRF/CORS cần thiết kế theo cách API phục vụ browser/cookie/Bearer clients; không tùy tiện disable CSRF mà chưa phân tích.

## 7. Tùy biến header: setBearerTokenHeaderName

Spring Security hỗ trợ đổi tên header mà converter đọc. Ví dụ có một **trusted reverse proxy** đưa Bearer token vào header **Proxy-Authorization** theo hợp đồng nội bộ.

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.web.server.authentication
        .ServerBearerTokenAuthenticationConverter;

ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
~~~

Rồi gắn vào WebFlux DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenConverter(converter)
        .jwt(Customizer.withDefaults()));
~~~

**Ý nghĩa:** thay đổi nơi converter đọc token trong request; nó **không làm converter tin token** và không thay đổi các JWT/opaque token validators.

### Ví dụ đầy đủ: gắn converter vào SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class CustomBearerSourceSecurity {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        ServerBearerTokenAuthenticationConverter converter =
                new ServerBearerTokenAuthenticationConverter();

        converter.setBearerTokenHeaderName(
                HttpHeaders.PROXY_AUTHORIZATION);

        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/api/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .bearerTokenConverter(converter)
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Đây là cấu hình minh họa. **Thực tế việc dùng Proxy-Authorization cần cân nhắc kỹ**:

1. Header đó có ý nghĩa trong proxy authentication theo HTTP; không phải một header ứng dụng tùy tiện.
2. Chỉ nên áp dụng khi có **hợp đồng proxy architecture** rõ ràng.
3. Gateway phải **xóa header cùng tên do client bên ngoài tự gửi**, rồi chỉ set giá trị tin cậy theo chính sách.
4. Phải kiểm soát proxy hop, TLS/mTLS, downstream trust và logs.
5. Đổi header không thể thay JWT issuer/audience/token purpose validation.
6. Phải làm rõ rằng Authorization header tiêu chuẩn có còn được chấp nhận hay không; setBearerTokenHeaderName chọn **header dùng để trích Bearer** theo cấu hình converter đó, không tự thêm cơ chế fallback tùy tiện.

**Mặc định tốt hơn cho phần lớn API là giữ Authorization header.** Nếu gateway có thể forward header chuẩn một cách an toàn, không cần phát minh header mới.

## 8. Custom header không tự tạo ra nguồn đáng tin

Ví dụ một API chấp nhận:

~~~http
X-Access-Token: ATTACKER_VALUE
~~~

Nếu bất kỳ client Internet nào cũng có thể tự set **X-Access-Token**, việc đổi từ Authorization sang X-Access-Token **không tăng mức tin cậy**. Nó chỉ chuyển nơi nhận credential.

Nguy cơ:

- Gateway có thể truyền đồng thời Authorization và custom header, tạo **credential confusion**.
- Một route có thể dùng custom header nhưng route khác dùng Authorization.
- Logging/middleware không biết custom header là secret và ghi giá trị.
- Proxy header injection khiến backend nhận token mà frontend không có chủ đích gửi.
- Các WebFilter độc lập có thể đọc hai nguồn khác nhau, xác thực hai principal không thống nhất.

Giải pháp:

~~~text
Internet client
     |
     v
Trusted gateway:
  - Strip client-supplied private credential headers
  - Validate/forward theo policy
  - Chỉ phát sinh downstream credential header khi được phép
     |
     v
Resource Server:
  - Converter đọc một nguồn xác định
  - JWT/opaque token vẫn được validate
~~~

Nếu client có thể trực tiếp gọi backend, cấu hình trust boundary của gateway không giúp gì. Backend cần bị giới hạn network access hoặc có phương thức xác thực proxy đáng tin phù hợp.

## 9. Nguồn token trong URI query parameter

Một số hệ thống cũ gửi access token như:

~~~http
GET /api/orders?access_token=ACCESS_TOKEN HTTP/1.1
Host: orders.example.com
~~~

RFC 6750 có mô tả cơ chế URI query nhưng **không khuyến khích** sử dụng. Trong ServerBearerTokenAuthenticationConverter, cờ:

~~~java
converter.setAllowUriQueryParameter(true);
~~~

có thể cho phép đọc token từ URI query parameter theo contract converter. **Mặc định giá trị này là false.**

Ví dụ cấu hình (chỉ khi chấp nhận rủi ro của hệ thống legacy):

~~~java
ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setAllowUriQueryParameter(true);

http.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenConverter(converter)
        .jwt(Customizer.withDefaults()));
~~~

### Vì sao nguy hiểm?

Bearer token là một credential: ai có token có thể gọi API trong phạm vi token nếu không có ràng buộc sở hữu khóa khác. Đưa token vào URL có thể làm nó xuất hiện trong:

- Access logs của reverse proxy/nginx/API gateway.
- Browser history, bookmarks và cache.
- Analytics URLs và monitoring dashboards.
- Copy/paste liên kết qua chat hoặc email.
- HTTP Referer trong những trường hợp cấu hình/policy cho phép.
- Tracing spans và distributed logging của các hệ thống trung gian.
- Alerting rules hoặc hệ thống báo lỗi ghi lại full URL.
- Screenshots và công cụ phát hiện sự cố.

**Không dùng query token làm giải pháp mặc định cho SSE hoặc browser API.** Nếu môi trường không thể gửi Authorization header, cần xem **cơ chế truy cập chuyên biệt** (ví dụ gateway, handshake/credential exchange, one-time scoped token), không tự đánh đổi bí mật Bearer token mà chưa có đánh giá rủi ro.

### Tắt mặc định quan trọng

~~~java
converter.setAllowUriQueryParameter(false);
~~~

Dù đây là mặc định, có thể ghi rõ để thể hiện policy khi có đội vận hành lâu dài, nhưng không cần cấu hình thủ công cho trường hợp thông thường.

## 10. Form-encoded body parameter: có hỗ trợ nhưng cần chú ý phiên bản

RFC 6750 mô tả một cách truyền token qua form body, dưới những ràng buộc về phương thức và media type. Ví dụ:

~~~http
POST /api/orders HTTP/1.1
Host: orders.example.com
Content-Type: application/x-www-form-urlencoded

access_token=ACCESS_TOKEN&quantity=1
~~~

**Spring Security 6.5 trở lên** đã bổ sung API:

~~~java
converter.setAllowFormEncodedBodyParameter(true);
~~~

Mặc định **false**. Khi dùng phiên bản Spring Security **trước 6.5**, class ServerBearerTokenAuthenticationConverter có thể **không có** phương thức setter này. Không sao chép ví dụ từ phiên bản mới sang 6.2 rồi nghĩ code không biên dịch là lỗi cấu hình.

Ví dụ cho phiên bản hỗ trợ:

~~~java
ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setAllowFormEncodedBodyParameter(true);

http.oauth2ResourceServer(oauth2 -> oauth2
        .bearerTokenConverter(converter)
        .jwt(Customizer.withDefaults()));
~~~

**Đây là ví dụ tương thích với API từ 6.5**, không phải cấu hình được khuyến nghị cho mọi service. Nếu request body là JSON hoặc streaming, không được tự giả định converter sẽ tìm access_token trong bất kỳ JSON field nào.

### Vì sao phải cân nhắc?

- Body parameter dễ bị log bởi form capture, API tracing hoặc error reporting.
- Có thể xung đột với application form fields và các giới hạn RFC 6750.
- Một WebFilter khác hoặc custom code có thể cố consume reactive body trước converter.
- Body parsing trong WebFlux là bất đồng bộ và cần được xử lý cẩn thận.
- Nếu vừa cho token trong header vừa trong body, phải kiểm soát **duplicate source conflict**.
- Không được coi HTTP body access_token là quyền tự động; token vẫn phải được decoder/introspector xác minh.

**Khuyến nghị:** ưu tiên Authorization header. Form-body token là một trường hợp đặc biệt cần hợp đồng rõ, không phải cơ chế mặc định để giải quyết lỗi frontend.

## 11. Tổng hợp các nguồn Bearer token

| Nguồn | Ví dụ | Mặc định WebFlux converter | Đánh giá |
|---|---|---|---|
| **Authorization header** | Authorization: Bearer abc | **Có** | Phương án tiêu chuẩn |
| **Custom header** | Proxy-Authorization: Bearer abc | Không, trừ khi đặt header name | Dùng khi có trusted proxy contract |
| **URI query** | ?access_token=abc | **Không** | Có rủi ro lộ qua URL |
| **Form-urlencoded body** | access_token=abc | **Không** | Setter hỗ trợ từ 6.5; cân nhắc RFC/media type |
| **JSON body field** | {"access_token":"abc"} | **Không** theo converter mặc định | Không nên tự coi JSON field là Bearer transport |
| **Cookie** | Cookie: access_token=abc | **Không** | Không tự trộn cookie/session với Bearer |
| **WebSocket subprotocol/query** | token trong handshake | Không mặc định như HTTP Bearer header | Cần thiết kế handshake riêng |
| **Server-side session** | Cookie session | Không thuộc nhiệm vụ converter Bearer | Authentication mechanism khác |
| **Custom request attribute** | exchange attribute | Không mặc định | Chỉ từ nguồn tin cậy với converter được thiết kế riêng |

Đặc biệt, **Bearer credential khác cookie session**. Một Resource Server stateless dựa trên Authorization header không nên tự lấy cookie của browser làm Bearer token khi chưa xử lý CSRF, SameSite và session trust model.

## 12. Xử lý khi request mang nhiều credential

Theo RFC 6750, client không nên gửi access token bằng **nhiều phương thức trong cùng request**. Ví dụ:

~~~http
POST /api/orders?access_token=QUERY_TOKEN HTTP/1.1
Authorization: Bearer HEADER_TOKEN
Content-Type: application/x-www-form-urlencoded

access_token=BODY_TOKEN&quantity=1
~~~

Có ba token candidates, các giá trị có thể khác nhau.

**Đừng viết converter tùy biến kiểu “ưu tiên header, nếu không được thì query, rồi body” mà không có duplicate/conflict policy.** Nếu hai tầng chọn hai credential khác nhau, đó có thể là **credential confusion**.

Một policy nên xác định:

1. Chỉ cho phép những nguồn đã được cấu hình rõ.
2. Có nhiều nguồn token được nhận diện trong cùng request thì **từ chối request** thay vì đoán token nào đúng.
3. Header có multiple Authorization values phải được gateway và WebFlux xử lý thống nhất.
4. Không bao giờ cho token query/body tự ghi đè một header khác mà caller hoặc proxy đã đưa vào.
5. Không cho phép client Internet tự set private proxy credential header.
6. Log **error category**, không log các token values.

### Không khẳng định framework phát hiện mọi dạng duplicate

Một số duplicate header được reverse proxy chuẩn hóa trước khi vào ứng dụng. Nếu form/query không được bật, chúng có thể không được xem là credential source; do đó không phải mọi tổ hợp input đều dẫn đến lỗi duplicate theo đúng implementation.

Muốn biết chính xác, cần **đánh giá hành vi của ServerBearerTokenAuthenticationConverter tại phiên bản và cấu hình đang triển khai**. Tránh ràng buộc business logic vào giả định "mọi duplicate token đều được converter phát hiện".

## 13. Lỗi transport và lỗi token validation không giống nhau

Ba nhóm điển hình:

**Nhóm A — Không có credential phù hợp**

~~~http
GET /api/orders HTTP/1.1
~~~

Converter có thể trả Mono.empty(). Nếu route yêu cầu authenticated, response thường **401** với Bearer challenge.

**Nhóm B — Hình thức Bearer request sai**

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer
~~~

Hoặc có nhiều phương thức truyền token bị cấm. Converter có thể phát sinh OAuth2AuthenticationException/BearerTokenError. Tùy loại lỗi, HTTP **400 invalid_request** hoặc **401 invalid_token** có thể xuất hiện theo Spring Security implementation.

**Nhóm C — Converter nhận credential nhưng token không hợp lệ**

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer INVALID_SIGNATURE_JWT
~~~

Converter chỉ trích được chuỗi; ReactiveJwtDecoder xác minh JWT và từ chối. Response điển hình **401 invalid_token**.

**Nhóm D — Token hợp lệ nhưng không đủ quyền**

~~~http
GET /api/admin HTTP/1.1
Authorization: Bearer VALID_READ_ONLY_TOKEN
~~~

Resource Server xác thực token; WebFlux authorization không cho quyền. Response điển hình **403 insufficient_scope** nếu thực sự thiếu OAuth scope, hoặc một 403 domain policy khác.

| Giai đoạn | Trạng thái | Lỗi điển hình |
|---|---|---|
| Converter | Không tìm được Bearer | Mono.empty(); protected route có thể trả 401 |
| Converter | Bearer transport malformed/ambiguous | Mono.error; status theo BearerTokenError |
| ReactiveJwtDecoder | Signature, issuer, audience, exp sai | 401 invalid_token |
| ReactiveOpaqueTokenIntrospector | AS trả active=false | 401 invalid_token |
| Authorization | Thiếu scope | 403 insufficient_scope khi thích hợp |
| Domain policy | Không có membership/ownership | 403 hoặc domain-specific response |
| Upstream introspection | Timeout/HTTP 5xx/RS secret sai | Lỗi dependency; không tự kết luận token invalid |

**Không coi việc converter trả token là chứng chỉ token còn hiệu lực.**

## 14. Không tách JWT claims bằng tay trong converter

Một anti-pattern:

~~~java
// Không nên: ở đây token chưa được xác thực.
String raw = exchange.getRequest()
        .getHeaders()
        .getFirst(HttpHeaders.AUTHORIZATION);

// Parse JWT payload và lấy sub, roles...
// Sau đó tự tạo Authentication authenticated.
~~~

Sai ở hai điểm:

1. **JWT payload chưa được xác minh mật mã**. Attacker có thể tự tạo chuỗi JSON khai **roles=["ADMIN"]**, **sub="victim"**, **iss="trusted-idp"** mà không có chữ ký hợp lệ.
2. Converter được giao nhiệm vụ **credential extraction**, không phải tạo danh tính đã authenticated. Làm vậy có thể bypass JWT validators.

Luồng đúng:

~~~text
HTTP header
   |
   v
ServerBearerTokenAuthenticationConverter
   |
   v
BearerTokenAuthenticationToken(raw token, chưa xác thực)
   |
   v
ReactiveAuthenticationManager
   |
   v
ReactiveJwtDecoder / ReactiveOpaqueTokenIntrospector
   |
   v
Authenticated principal và authorities
~~~

Nếu cần thêm claim-to-authority mapping, dùng extension points **sau khi JWT được xác thực**, ví dụ reactive JWT authentication converter, không biến ServerBearerTokenAuthenticationConverter thành nơi cấp quyền.

## 15. Các kiểu reactive cần phân biệt

Trong WebFlux:

~~~java
Mono<Authentication>
Mono<Jwt>
Mono<OAuth2AuthenticatedPrincipal>
Mono<AuthorizationDecision>
Flux<Order>
~~~

Nhưng ý nghĩa khác nhau:

- **Mono<Authentication> từ ServerAuthenticationConverter:** request xác thực được tạo từ raw token.
- **Mono<Jwt> từ ReactiveJwtDecoder:** token đã qua xử lý cryptographic/claim validation theo decoder.
- **Mono<OAuth2AuthenticatedPrincipal> từ introspector:** principal từ introspection đáng tin.
- **Reactive AuthorizationManager:** quyết định có cho phép access hay không.
- **Flux/Mono từ business handler:** response data được tạo sau khi security policy cho request qua.

### Vì sao không block() trong converter?

Reactor/WebFlux ưu tiên non-blocking I/O. Không nên viết:

~~~java
// Anti-pattern trong WebFlux request path:
Authentication auth = someMono.block();
return Mono.just(auth);
~~~

Blocking trên event-loop có thể giảm throughput hoặc gây lỗi runtime. Nếu cần đọc request body hoặc hỏi nguồn dữ liệu, dùng reactive operators/các API tương ứng. Đặc biệt, **credential extraction không nên gọi AS hay database chỉ để quyết định tên người dùng**.

Một converter chuyên biệt chỉ nên diễn đạt nguồn credential và hoàn thành nhanh, trong khi authentication manager xử lý xác minh theo chiến lược reactive phù hợp.

## 16. WebFlux không có HttpServletRequest và ThreadLocal security context mặc định

Các khác biệt thường gặp:

| Servlet | WebFlux |
|---|---|
| HttpServletRequest | ServerWebExchange |
| BearerTokenResolver | ServerAuthenticationConverter |
| DefaultBearerTokenResolver | ServerBearerTokenAuthenticationConverter |
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| Servlet Filter | WebFilter |
| SecurityContextHolder thường dùng thread-local | ReactiveSecurityContextHolder theo Reactor Context |
| JwtDecoder | ReactiveJwtDecoder |
| OpaqueTokenIntrospector | ReactiveOpaqueTokenIntrospector |

Một ví dụ dễ sai là copy config:

~~~java
// Servlet style: không dành cho WebFlux configuration.
@Bean
SecurityFilterChain api(HttpSecurity http) { ... }
~~~

sang ứng dụng chỉ dùng WebFlux. Đúng là:

~~~java
@Bean
SecurityWebFilterChain api(ServerHttpSecurity http) { ... }
~~~

Một lỗi khác là dùng SecurityContextHolder.getContext() ở luồng reactive và cho rằng security context luôn có giá trị trên thread hiện tại. Trong WebFlux, context có thể di chuyển qua luồng và dùng **Reactor Context**; cần truy cập theo **ReactiveSecurityContextHolder** hoặc qua reactive argument resolution phù hợp.

## 17. ReactiveSecurityContextHolder và downstream authorization

Sau khi authentication manager chấp nhận Bearer token, Spring Security đưa authentication vào reactive security context. Handler/service có thể dùng:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication());
}
~~~

Đừng lấy **token string** rồi tự suy ra user trong business handler. Nên dùng authenticated principal và identity mapping theo hợp đồng, ví dụ JWT **(iss, sub)** đã được xác thực hoặc metadata introspection tin cậy.

Một WebFlux controller có thể nhận Principal:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Mono<String> me(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }
}
~~~

Ví dụ này tập trung vào principal đã được framework cung cấp sau security pipeline; **getName()** không nhất thiết là global user key trong multi-issuer, vì có thể chỉ là **sub**. Đừng dùng nó thay **issuer + subject** nếu ứng dụng tin nhiều issuer.

## 18. Custom converter: khi nào thật sự cần?

Một số trường hợp có thể có lý do tùy biến:

1. Gateway nội bộ chỉ được phép chuyển Bearer credential qua một header riêng và loại bỏ nguồn Internet tự gửi.
2. Có một token transport contract đặc biệt cho một nhóm route.
3. Cần giới hạn chặt một nguồn token hoặc xử lý duplicate header theo quy tắc enterprise.
4. Có một migration tạm thời giữa các client transport với khoảng thời gian sunset rõ.
5. Security team cần kiểm soát request metadata trước khi credential được chuyển cho authentication manager.

Nhưng nếu yêu cầu chỉ là **kiểm tra JWT issuer/audience**, không cần custom ServerAuthenticationConverter; hãy dùng **ReactiveJwtDecoder + validators**.

Nếu yêu cầu là **mapping scope/roles sang authorities**, dùng JWT authentication converter hoặc reactive authorization mapping **sau token validation**.

Nếu yêu cầu là **quyền domain theo tenant/order**, dùng authorization policy hoặc method security, không đặt logic này vào Bearer token extraction.

Nếu yêu cầu là **lấy token từ một HTTP header khác**, trước hết xem **setBearerTokenHeaderName(...)** có đủ không, thay vì viết cả custom implementation.

## 19. Khung custom ServerAuthenticationConverter an toàn

Nếu cần logic transport riêng, vẫn nên giữ output là **BearerTokenAuthenticationToken chưa xác thực** và từ chối các tình huống mâu thuẫn.

Khung khái niệm:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class TrustedHeaderBearerConverter
        implements ServerAuthenticationConverter {

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        // Đây chỉ là ví dụ khi một trusted gateway đã bảo vệ header.
        String value = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Trusted-Bearer");

        if (value == null || value.isBlank()) {
            return Mono.empty();
        }

        // Không tự coi header này là đáng tin nếu client Internet tự gửi.
        // Một implementation thực phải kiểm tra cú pháp Bearer/duplicate,
        // giới hạn độ dài và có chính sách lỗi rõ ràng.
        if (!value.startsWith("Bearer ")) {
            return Mono.empty(); // Minh họa; có thể cần reject theo policy.
        }

        String token = value.substring("Bearer ".length());

        if (token.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "Malformed trusted bearer header"));
        }

        Authentication request =
                new BearerTokenAuthenticationToken(token);
        return Mono.just(request);
    }
}
~~~

**Đoạn này là khung minh họa, không đủ an toàn để copy vào production** vì còn phải xử lý cú pháp Bearer theo RFC, duplicate credential sources, limits, response error semantics, proxy trust và cách exception được translate. Ví dụ dùng IllegalArgumentException để nhấn mạnh nhánh lỗi, trong implementation thật cần dùng **Spring Security authentication exception/BearerTokenError** phù hợp, không để generic exception trở thành HTTP 500 không kiểm soát.

**Ưu tiên class chuẩn** khi chỉ đổi header:

~~~java
ServerBearerTokenAuthenticationConverter converter =
        new ServerBearerTokenAuthenticationConverter();

converter.setBearerTokenHeaderName("X-Trusted-Bearer");
~~~

Nếu cần cùng lúc hỗ trợ nhiều header, không nên tự xếp thứ tự ưu tiên mà không định nghĩa chính sách “những credential mâu thuẫn sẽ bị từ chối”. Một custom converter an toàn là thành phần security-sensitive và cần được review độc lập.

## 20. Test trực tiếp converter bằng MockServerWebExchange

Mục tiêu của unit test converter là xác minh **token được lấy từ nguồn mong muốn**, không kiểm tra chữ ký JWT.

Với Spring Test và Reactor Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.server.authentication.ServerBearerTokenAuthenticationConverter;
import reactor.test.StepVerifier;

class BearerConverterTest {

    private final ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    @Test
    void readsAuthorizationBearerHeader() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/api/orders")
                                .header(HttpHeaders.AUTHORIZATION,
                                        "Bearer example-token"));

        StepVerifier.create(converter.convert(exchange))
                .assertNext(authentication -> {
                    assertThat(authentication)
                            .isInstanceOf(BearerTokenAuthenticationToken.class);
                    BearerTokenAuthenticationToken token =
                            (BearerTokenAuthenticationToken) authentication;
                    assertThat(token.getToken())
                            .isEqualTo("example-token");
                })
                .verifyComplete();
    }

    @Test
    void noBearerProducesEmptyMono() {
        MockServerWebExchange exchange =
                MockServerWebExchange.from(
                        MockServerHttpRequest.get("/api/orders"));

        StepVerifier.create(converter.convert(exchange))
                .verifyComplete();
    }
}
~~~

Những tests này xác minh:

- Authorization header được chuyển thành yêu cầu Authentication chứa đúng raw token.
- Không có Bearer token thì converter hoàn thành rỗng.

**Chúng không chứng minh JWT đã được xác thực**, vì converter không chạy ReactiveJwtDecoder. Cần test khác cho JWT signature/issuer/audience và WebFlux SecurityWebFilterChain.

### Test custom header

~~~java
@Test
void supportsConfiguredProxyHeader() {
    ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    converter.setBearerTokenHeaderName(
            HttpHeaders.PROXY_AUTHORIZATION);

    MockServerWebExchange exchange =
            MockServerWebExchange.from(
                    MockServerHttpRequest.get("/api/orders")
                            .header(HttpHeaders.PROXY_AUTHORIZATION,
                                    "Bearer forwarded-token"));

    StepVerifier.create(converter.convert(exchange))
            .assertNext(authentication -> {
                BearerTokenAuthenticationToken request =
                        (BearerTokenAuthenticationToken) authentication;
                assertThat(request.getToken()).isEqualTo("forwarded-token");
            })
            .verifyComplete();
}
~~~

Phải kiểm tra riêng gateway không cho client tự set Proxy-Authorization, vì unit test converter không chứng minh ranh giới proxy.

## 21. Test khi không bật query token

Một trường hợp:

~~~java
@Test
void ignoresUriQueryTokenByDefault() {
    ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    MockServerWebExchange exchange =
            MockServerWebExchange.from(
                    MockServerHttpRequest.get(
                            "/api/orders?access_token=query-token"));

    StepVerifier.create(converter.convert(exchange))
            .verifyComplete();
}
~~~

Nếu muốn kiểm tra behavior **khi bật**:

~~~java
@Test
void canReadQueryTokenWhenExplicitlyEnabled() {
    ServerBearerTokenAuthenticationConverter converter =
            new ServerBearerTokenAuthenticationConverter();

    converter.setAllowUriQueryParameter(true);

    MockServerWebExchange exchange =
            MockServerWebExchange.from(
                    MockServerHttpRequest.get(
                            "/api/orders?access_token=query-token"));

    StepVerifier.create(converter.convert(exchange))
            .assertNext(authentication -> {
                BearerTokenAuthenticationToken request =
                        (BearerTokenAuthenticationToken) authentication;
                assertThat(request.getToken()).isEqualTo("query-token");
            })
            .verifyComplete();
}
~~~

Hai ví dụ thể hiện **rủi ro được cấu hình rõ**; việc hỗ trợ query token không phải khuyến nghị cho production.

### Test form body cần lưu ý version

Từ Spring Security **6.5**, có thể có bài test với **setAllowFormEncodedBodyParameter(true)**, dùng POST và form-urlencoded body. Khi project đang dùng phiên bản cũ hơn, không nên viết bài test gọi API chưa tồn tại.

Trong WebFlux, cần tạo đúng body publisher và Content-Type cho MockServerHttpRequest, tránh kiểm thử bằng một request JSON nhưng kỳ vọng resolver xem JSON như form data.

## 22. WebTestClient và SecurityWebFilterChain integration tests

Kiểm thử converter trực tiếp chưa đủ. Với Resource Server thật, cần test request qua chain:

~~~text
WebTestClient request
   |
   v
SecurityWebFilterChain
   |
   v
ServerBearerTokenAuthenticationConverter
   |
   v
ReactiveAuthenticationManager / ReactiveJwtDecoder
   |
   v
Authorization decisions
   |
   v
Response status / WWW-Authenticate
~~~

Ma trận tình huống:

| Input | Kỳ vọng cần xác minh |
|---|---|
| GET protected không token | 401 Bearer challenge |
| GET public không token | Không buộc 401 |
| JWT hợp lệ qua Authorization header | Authentication được thiết lập |
| JWT sai signature | Không authenticated, thường 401 |
| JWT sai issuer | Không authenticated |
| JWT sai audience | Không authenticated nếu validator bắt buộc |
| JWT đúng nhưng thiếu SCOPE_orders.read | Đã xác thực, thường 403 |
| Token nằm query khi không bật query source | Không được nhận làm Bearer token |
| Token nằm query sau khi bật tùy chọn | Converter có thể trích token; vẫn phải validate |
| Token từ custom header sau cấu hình | Converter trích token từ header được chọn |
| Có cả header và query token với policy cấm duplicate | Bị từ chối theo transport policy |
| Bearer header malformed | Status/challenge đúng error code converter |
| Opaque introspection active=false | Authentication từ chối |
| Opaque introspection AS timeout | Fail closed; không xem là active=false |
| Gateway tự thêm/strip header | Chỉ nguồn được tin cậy được chấp nhận |
| CORS preflight OPTIONS | Không bị nhầm với request Bearer thiếu token |
| POST form-body token trên version hỗ trợ | Behavior đúng policy transport |

**Spring Security Test mockJwt() có thể tạo Authentication test mà bỏ qua ReactiveJwtDecoder thực.** Dùng nó để test authorization policy; không coi nó là bằng chứng signature, issuer hoặc audience validation của production đã chạy.

Các tình huống trên là **thiết kế kịch bản kiểm thử**, không phải kết quả đã thực thi trong bài viết này.

## 23. Nếu request bị 401, làm sao biết lỗi nằm ở converter?

Tách theo các bước:

~~~text
[1] Request có Authorization header không?
       |
       v
[2] Header có Bearer scheme và cú pháp phù hợp không?
       |
       v
[3] Converter có được gắn trong đúng SecurityWebFilterChain không?
       |
       v
[4] Converter đang đọc Authorization hay header khác?
       |
       v
[5] Query/form token đã được bật chưa?
       |
       v
[6] Converter có trả Mono.empty, Mono.error hay Authentication?
       |
       v
[7] Nếu đã có BearerTokenAuthenticationToken, decoder có chấp nhận?
       |
       v
[8] JWT issuer/audience/alg/exp/profile hợp lệ không?
       |
       v
[9] Nếu token hợp lệ, scope/authority đủ không?
~~~

Nếu converter không tìm token vì frontend chỉ gửi query string, việc thay **JwtDecoder**, JWKS hoặc issuer-uri không giải quyết nguyên nhân.

Ngược lại, nếu converter đã trích Bearer token nhưng decoder từ chối vì signature, thay header name cũng không giải quyết.

### Bảng chẩn đoán

| Triệu chứng | Gợi ý nguyên nhân |
|---|---|
| Header Bearer đúng nhưng converter luôn empty | Converter đang đọc custom header, sai SecurityWebFilterChain hoặc gateway strip Authorization |
| Query access_token có giá trị nhưng 401 | Query token bị tắt mặc định |
| Form body access_token không được nhận | Form parsing chưa bật, method/media type không phù hợp hoặc version trước 6.5 |
| Có token nhưng 401 invalid_token | JWT/opaque validation thất bại hoặc transport malformed tùy error |
| Có token, đã authenticated nhưng 403 | Thiếu SCOPE_ authority hoặc domain policy từ chối |
| Custom proxy header hoạt động ở staging nhưng fail ở production | Gateway header policy khác nhau |
| Cùng token đôi lúc thành công, đôi lúc thất bại | Multiple gateways/instances có cấu hình converter hoặc decoder khác nhau |
| Bearer token bị xuất hiện trong logs | Logging policy đang thu thập header/query |
| Endpoint permitAll vẫn trả 401 khi gửi token sai | Authentication filter có thể cố xác thực Bearer token được gửi dù route không yêu cầu; cần hiểu chain behavior |
| CORS preflight 401 | OPTIONS bị authentication yêu cầu hoặc CORS chưa xử lý đúng thứ tự |

**Cần xác định một hop hoặc component cụ thể**, không phỏng đoán rằng mọi 401 là token expired.

## 24. Multiple SecurityWebFilterChain và source policy khác nhau

Một ứng dụng có thể có nhiều chuỗi bảo vệ, ví dụ API công khai và API nội bộ. Nếu mỗi chain dùng Bearer converter khác nhau, cần hiểu **security matcher** để biết route thực tế đang nằm trong chain nào.

Khái niệm:

~~~text
Chain A: /api/internal/**
  -> Proxy-Authorization Bearer
  -> JWT issuer internal
  -> permissions riêng

Chain B: /api/public/**
  -> Authorization Bearer hoặc permitAll
  -> JWT issuer public
  -> permissions riêng
~~~

Lỗi thường gặp:

- Một path vô tình khớp chain khác và converter đọc sai header.
- Gateway chỉ thêm custom header cho một số routes.
- Public endpoint thuộc chain vẫn có Bearer filter và có thể kiểm tra token sai nếu client gửi token.
- Internal header được client trực tiếp đưa vào route public.
- Custom converter của chain A có source policy rộng hơn dự kiến.

**Không sửa filter chain bằng cách bỏ validation**. Cần thiết kế matcher, order, endpoint boundary và trust policy nhất quán.

Trong một chương trình lớn, có thể ưu tiên một nguồn token thống nhất cho các API, tránh nhiều đường credential song song trừ khi mỗi trust zone thực sự yêu cầu.

## 25. Reactive WebClient propagation không phải token extraction

Một thành phần khác có tên gần giống là:

**ServerBearerExchangeFilterFunction**

Nó hỗ trợ một **WebClient** mang Bearer token từ SecurityContext hiện tại sang downstream service theo hành vi được cấu hình.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient downstreamClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
~~~

Đây là **outbound propagation**, không phải **inbound extraction**:

~~~text
Inbound:
  HTTP request -> ServerBearerTokenAuthenticationConverter
  -> kiểm tra access token

Outbound:
  Authenticated request -> WebClient
  -> ServerBearerExchangeFilterFunction
  -> Authorization: Bearer đến downstream service
~~~

Quan trọng:

- Không tự động refresh access token đã hết hạn.
- Chỉ forward token khi downstream **được phép nhận cùng token**, đặc biệt xét audience/token exchange và least privilege.
- Không biến token của user dành cho service A thành token có thể dùng ở service B chỉ bằng cách copy Authorization header.
- Tránh truyền access token tới endpoint ngoài trust boundary.
- Không dùng ServerBearerExchangeFilterFunction thay JWT decoder hoặc converter inbound.

## 26. WebSocket, SSE và browser clients: vì sao không dùng query token tùy tiện?

Một số browser APIs có giới hạn cách set Authorization header, nhất là một số cơ chế handshake hoặc APIs như EventSource. Điều này thường khiến đội phát triển định chuyển Bearer token vào URL query string.

Nhưng URL query là nguồn dễ lộ nhất trong các nguồn được nhắc tới. Những cách giảm rủi ro có thể gồm:

1. Nếu giao thức/client hỗ trợ, giữ **Authorization header**.
2. Thiết kế gateway hoặc endpoint **credential exchange** tạo một vé truy cập ngắn hạn, có audience/resource hẹp và chỉ dùng một lần khi cần.
3. Với WebSocket, định nghĩa một authentication handshake riêng có nguồn credential, TLS, replay protection và lifecycle phù hợp.
4. Không đưa long-lived access token vào URL chỉ vì dễ triển khai.
5. Cân nhắc cookie/session và CSRF/SameSite nếu sử dụng browser ambient credentials; đừng ngụy trang cookie thành Bearer mà không thiết kế threat model.
6. Không cho client tự lựa chọn URL introspection/JWKS hoặc token validation rules.
7. Đối với Server-Sent Events, kiểm tra client options và thực tế network environment thay vì mặc định query là lựa chọn duy nhất.

**ServerBearerTokenAuthenticationConverter được thiết kế cho HTTP request extraction**. Authentication cho một WebSocket message hoặc connection lâu dài có thể có vòng đời và security handshake riêng; không nên suy luận mọi message được converter kiểm tra lại.

## 27. Câu chuyện bảo mật: credential source là ranh giới tin cậy

Một Bearer token có thể hợp lệ về chữ ký nhưng bị đưa vào request qua nguồn không được phép hoặc bị proxy giả mạo. Authentication phải kết hợp hai câu hỏi:

**A. Tôi nhận credential từ đâu?**

~~~text
Authorization header?
Trusted gateway header?
Query parameter?
Form body?
Session cookie?
~~~

**B. Credential đó có hợp lệ và đủ quyền không?**

~~~text
JWT: signature + issuer + audience + time + profile
Opaque: trusted introspection + active + audience
Authorization: authorities + tenant + resource policy
~~~

Converter giải quyết chủ yếu **A**; decoder/introspector và authorization giải quyết **B**.

Các nguyên tắc quan trọng:

- Chỉ bật những transport thực sự được yêu cầu.
- Giữ **Authorization header** làm mặc định.
- Không cho multiple credential sources tự ghi đè nhau.
- Chặn spoofing của private proxy headers.
- Không đọc JWT claims chưa xác minh.
- Không log token ở header, query, form body hoặc trace.
- Giữ JWT/opaque authentication trong cơ chế Resource Server chuẩn.
- Xem CSRF/CORS và browser credential model nếu có cookie/session.
- Validate issuer, audience, token purpose và scope độc lập với nơi lấy token.
- Đo lường error categories mà không tiết lộ Bearer credential.

## 28. Tình huống minh họa từ đầu đến cuối

Giả sử một WebFlux API có cấu hình:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Và chỉ dùng Authorization header.

### Tình huống 1: access token hợp lệ

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer VALID_JWT
~~~

Converter trả một yêu cầu Bearer authentication. ReactiveJwtDecoder xác minh JWT; Resource Server tạo authenticated principal, rồi kiểm tra **SCOPE_orders.read**. Nếu đủ quyền, request tiếp tục.

### Tình huống 2: token nằm trong query

~~~http
GET /api/orders?access_token=VALID_JWT HTTP/1.1
~~~

Với query token mặc định bị tắt, converter **không trích token đó**. Nếu route yêu cầu auth và không có credential khác, request thường **401**. Thay JWT signing key không chữa được lỗi này; cần sửa client dùng Authorization header.

### Tình huống 3: header đúng nhưng token sai

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer BAD_SIGNATURE_JWT
~~~

Converter có thể trích token nhưng ReactiveJwtDecoder từ chối. HTTP thường **401 invalid_token**.

### Tình huống 4: token hợp lệ nhưng thiếu quyền

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer JWT_WITH_ORDERS_READ
~~~

JWT được xác thực, nhưng thiếu **SCOPE_orders.write**. Authorization thường **403**, không phải converter error.

### Tình huống 5: proxy custom header

~~~http
GET /api/orders HTTP/1.1
Proxy-Authorization: Bearer FORWARDED_JWT
~~~

Nếu converter được đặt tên header **Proxy-Authorization** và gateway bảo vệ nguồn header, converter có thể trích token. JWT vẫn cần được ReactiveJwtDecoder xác minh. Nếu converter vẫn dùng mặc định, Proxy-Authorization có thể **không được coi là Bearer credential** của Resource Server.

### Tình huống 6: hai nguồn token

~~~http
GET /api/orders?access_token=QUERY_TOKEN HTTP/1.1
Authorization: Bearer HEADER_TOKEN
~~~

Nếu query support bật, cần có policy ngăn credential collision. Không tự nhận token nào “mạnh” hơn vì ký tự của nó trông giống JWT hơn.

## 29. Danh sách lỗi thiết kế thường gặp

| Sai lầm | Vì sao nguy hiểm? | Hướng khắc phục |
|---|---|---|
| Dùng DefaultBearerTokenResolver của Servlet cho WebFlux | Sai integration API | Dùng ServerBearerTokenAuthenticationConverter |
| Dùng HttpSecurity/SecurityFilterChain trong app WebFlux | Sai security stack | Dùng ServerHttpSecurity/SecurityWebFilterChain |
| Tự parse JWT trong converter rồi set authenticated=true | Bypass signature/claim validation | Converter chỉ trích credential |
| Coi Mono.empty là access allowed | Không có authentication request | Authorization policy quyết định route có yêu cầu auth không |
| Đưa Bearer access token vào query | Lộ qua logs/history/referrer | Dùng Authorization header |
| Bật form body source khi app đang dùng Spring Security trước 6.5 | API setter có thể chưa tồn tại | Chú ý version; ưu tiên header |
| Nhận custom proxy header từ Internet trực tiếp | Header spoofing | Gateway strip/rewrite và giới hạn network |
| Header/query/body đồng thời nhưng không kiểm soát xung đột | Credential confusion | Reject duplicate sources theo contract |
| Custom converter gọi block() | Có thể chặn reactive event-loop | Dùng reactive APIs và phân tầng |
| Đọc SecurityContextHolder thread-local trong Reactor flow | Không nhất quán qua reactive context | Dùng ReactiveSecurityContextHolder |
| Sai audience nhưng cho qua vì header đúng | Token của API khác được chấp nhận | Validate issuer, aud, type, signature |
| Token valid nhưng thiếu scope lại coi converter lỗi | Nhầm authentication với authorization | Phân lớp lỗi đúng |
| Tự cấp quyền từ scope trong raw token | Chưa verify token | Decoder/introspector trước authority mapping |
| Chỉ bật query để xử lý SSE/WebSocket | Tăng nguy cơ lộ token | Thiết kế handshake/short-lived credential |
| Dùng ServerBearerExchangeFilterFunction thay inbound converter | Nhầm outbound propagation | Tách WebClient propagation và Resource Server extraction |
| Ghi Authorization header vào logs | Lộ Bearer credential | Redact/sanitize credentials |
| Thêm nhiều JWT filters để xử lý header | Chồng chéo hoặc bypass authentication | Mở rộng Resource Server DSL |
| Mock JWT test rồi tin decoder đã verify signature | Test chỉ tạo authentication giả | Integration tests qua decoder thật |

## 30. Nguyên tắc tổng kết

~~~text
                          HTTP request
                               |
                               v
                 ServerWebExchange (WebFlux)
                               |
                               v
         ServerBearerTokenAuthenticationConverter
           - Authorization header mặc định
           - Custom header theo trusted contract
           - Query/form chỉ khi chủ động bật
           - Output: Mono<Authentication request>
                               |
                               v
             ReactiveAuthenticationManager
               JWT decoder hoặc opaque introspection
                               |
                               v
                  Verified Authentication
                               |
                               v
                 Reactive authorization
                               |
                               v
                   Domain/business handler
~~~

Ghi nhớ:

1. **ServerBearerTokenAuthenticationConverter trích Bearer credential từ ServerWebExchange, không xác thực JWT.**
2. **Mặc định đọc Authorization: Bearer**, không nhận query hoặc form body trừ khi được cấu hình.
3. **setBearerTokenHeaderName(...)** cho phép chọn header khác; chỉ sử dụng với trust boundary rõ ràng.
4. **setAllowUriQueryParameter(true)** có thể mở URI query token, nhưng Bearer trong URL có nguy cơ rò rỉ cao.
5. **setAllowFormEncodedBodyParameter(true)** xuất hiện từ Spring Security **6.5**, không mặc định khả dụng trên bản cũ.
6. **Mono.empty()** nghĩa là converter không tạo authentication request; endpoint protected vẫn có thể trả 401.
7. **Mono.error** phản ánh lỗi transport/converter; token sai chữ ký chỉ được xác định ở decoder/introspector.
8. **JWT/opaque token acceptance và business authorization** phải luôn nằm sau credential extraction.
9. **Không dùng Servlet APIs để giải thích WebFlux security**, không block reactive pipeline và không dùng ThreadLocal context như giả định duy nhất.
10. **Ưu tiên đường HTTP authentication chuẩn**, kiểm soát duplicate/header spoofing và tuyệt đối không log raw Bearer token.

**Kết luận:** Việc chọn nguồn token là bước nhỏ nhưng quan trọng trong kiến trúc WebFlux Resource Server. Converter quyết định chuỗi credential nào được gửi tiếp để xác thực; cấu hình sai nguồn token có thể dẫn đến lỗi 401 khó hiểu hoặc nguy cơ credential confusion. Giữ Authorization header làm mặc định và sử dụng các extension points của Spring Security sẽ bảo đảm quá trình trích token, xác thực và phân quyền được tách bạch.

## 31. Tài liệu tham khảo

- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Bearer Tokens:** nguồn Authorization header, custom header với ServerBearerTokenAuthenticationConverter, WebClient Bearer propagation. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/bearer-tokens.html
- **Spring Security API — ServerBearerTokenAuthenticationConverter:** convert(ServerWebExchange), setBearerTokenHeaderName, setAllowUriQueryParameter, và setAllowFormEncodedBodyParameter từ phiên bản hỗ trợ. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html
- **Spring Security 6.2.8 API — ServerBearerTokenAuthenticationConverter:** ví dụ đối chiếu API cũ chưa có form-body setter. https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/oauth2/server/resource/web/server/authentication/ServerBearerTokenAuthenticationConverter.html
- **Spring Security Reference — Reactive JWT Resource Server:** ServerHttpSecurity, SecurityWebFilterChain và ReactiveJwtDecoder. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive OAuth 2.0 Resource Server Opaque Token:** ReactiveOpaqueTokenIntrospector và API introspection. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — WebFlux Security:** reactive filter chain và security context. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security API — ServerAuthenticationConverter:** interface convert(ServerWebExchange) và Mono<Authentication>. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/authentication/ServerAuthenticationConverter.html
- **Spring Security API — AuthenticationWebFilter:** sử dụng converter và reactive authentication manager. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** HTTP Authorization header, form body, URI query và các Bearer errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token:** JWT claims và expiration. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** xác thực opaque access token. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 8725 — JSON Web Token Best Current Practices:** validation, token substitution và token misuse. https://www.rfc-editor.org/rfc/rfc8725
