# Ranh giới trách nhiệm của Spring Web và Spring Security

## 1. Bài toán: cùng là HTTP nhưng không cùng trách nhiệm

Một REST API viết bằng Spring Boot có thể nhận request, đọc JSON, kiểm tra dữ liệu, xác thực người dùng, kiểm tra quyền, chống CSRF, áp dụng CORS và trả lỗi. Vì cả hai thư viện đều tham gia xử lý HTTP, lập trình viên dễ nhầm rằng `@RestController` tự bảo vệ endpoint, hoặc `SecurityFilterChain` tự biết cách validate DTO.

**Spring Web (Spring MVC)** chịu trách nhiệm chính về *web request/response application layer*: định tuyến tới controller, bind tham số, chọn converter đọc/ghi body, gọi handler, validate đầu vào theo cấu hình, resolve view hoặc serialize JSON, và xử lý các lỗi MVC.

**Spring Security** chịu trách nhiệm chính về *bảo vệ request và method*: cơ chế xác thực (authentication), quyết định quyền truy cập (authorization), lưu/truyền `SecurityContext`, phòng chống một số tấn công web như CSRF, thiết lập security headers, tích hợp CORS đúng thứ tự, quản lý session/authentication khi dùng các cơ chế tương ứng.

Hai thư viện **kết hợp với nhau nhưng không thay thế nhau**. Ví dụ:
- `@GetMapping("/orders/{id}")` định tuyến ở Spring MVC.
- `http.authorizeHttpRequests(...)` kiểm tra người dùng có được đi qua một URL/method ở security filter chain.
- `@PreAuthorize("hasRole('ADMIN')")` bảo vệ method/service khi method security được bật.
- `@Valid @RequestBody CreateOrder` kiểm tra cấu trúc/constraint của DTO, không xác minh user có quyền tạo đơn.
- `@RestControllerAdvice` biến lỗi từ MVC/service thành JSON, nhưng không mặc nhiên bắt được lỗi bị filter chặn **trước** khi vào DispatcherServlet.

### Kết quả học tập

1. Vẽ đúng pipeline Servlet container → security filters → `DispatcherServlet` → controller/service.
2. Phân biệt `SecurityFilterChain` với `HandlerMapping`, `AuthorizationFilter` với `@RequestMapping`.
3. Biết đặt CORS, CSRF, authentication, authorization, validation và business invariants ở tầng nào.
4. Phân biệt HTTP 400, 401, 403, 404, 415, 500 và nơi phát sinh chúng.
5. Viết một ứng dụng Spring Boot 3.x Java 17+ có Spring MVC + Spring Security + method security + MockMvc tests thực tế.
6. Tránh các sai lầm khi nhiều filter chains, nhiều `@ControllerAdvice`, chuyển sang stateless bearer token hoặc xử lý session/cookie.

**Phạm vi:** Servlet-based Spring MVC, Java 17+, ví dụ Spring Boot 3.3.5 với Spring Security 6.3.x theo BOM tương ứng. Spring WebFlux có `SecurityWebFilterChain` và kiến trúc reactive khác, không áp dụng nguyên xi cách cấu hình dưới đây.

## 2. Vị trí mỗi thành phần trong pipeline HTTP

~~~text
Browser / client
      |
      v
Reverse proxy / load balancer / API gateway (nếu có)
      |
      v
Servlet container (Tomcat, Jetty ...)
      |
      v
Servlet FilterChain
      |
      +--> Những filter ngoài Spring Security, nếu có
      |
      +--> DelegatingFilterProxy (thường bean "springSecurityFilterChain")
               |
               v
           FilterChainProxy
               |
               +--> chọn SecurityFilterChain phù hợp request
                      |
                      +--> CORS / CSRF / security headers
                      +--> SecurityContext, authentication
                      +--> authorization, exception translation
                      |
                      v
               tiếp tục filter chain
      |
      v
DispatcherServlet (Spring MVC)
      |
      +--> HandlerMapping / @RequestMapping
      +--> HandlerAdapter / argument resolvers
      +--> @RequestBody / @RequestParam / validation
      +--> Controller method --> Service/domain/data
      +--> ReturnValueHandler / HttpMessageConverter / ViewResolver
      +--> HandlerExceptionResolver / @ControllerAdvice
      |
      v
HTTP response đi ngược qua filters/proxy
      |
      v
Browser / client
~~~

Sơ đồ là mô hình kiến trúc, **không bảo đảm một thứ tự tuyệt đối cho mọi filter cụ thể**: thứ tự và số filter phụ thuộc cấu hình/phiên bản, dispatcher type, custom filters, nhiều chains, async/error dispatch. Điểm quyết định là security filters có thể **dừng request trước khi MVC chạy**; nếu đi tiếp thì MVC mới định tuyến đến controller.

### 2.1. `DelegatingFilterProxy`

Servlet container quản lý Servlet `Filter`, còn Spring quản lý các bean. `DelegatingFilterProxy` làm cầu nối: từ filter trong container đến bean Spring, thông thường tên `springSecurityFilterChain`. Spring Boot/Spring Security thường auto-configure cầu nối; không cần tự khai báo `web.xml` trong Boot starter hiện đại.

### 2.2. `FilterChainProxy` và `SecurityFilterChain`

`FilterChainProxy` quản lý nhiều `SecurityFilterChain`; **chỉ chain đầu tiên khớp request được áp dụng**. Một chain có thể yêu cầu session/cookie login, chain khác xử lý bearer token, chain khác chỉ áp dụng cho API; nếu path không khớp chain nào, request có thể **không được bảo vệ bởi các chains đó**.

Ví dụ khái niệm:

~~~text
Chain #1: /api/**       -> bearer token, stateless, API policies
Chain #2: /admin/**     -> web login, session, CSRF
Chain #3: /**           -> fallback deny/explicit policies
~~~

Đây không phải bộ cấu hình thực thi. **Thứ tự chain là một phần chính sách bảo mật**: chain `/**` đứng trước chain chuyên biệt có thể làm chuyên biệt không bao giờ được chọn. Không đánh đồng “match chain” với “permit URL”:
- `securityMatcher("/api/**")` quyết định **chain nào** xử lý request.
- `requestMatchers("/api/public/**").permitAll()` bên trong `authorizeHttpRequests` quyết định **quy tắc quyền** của request mà chain đã chọn.

`permitAll` không đồng nghĩa bỏ các filter CSRF, CORS, security headers hoặc logging; trong khi một đường bị loại hoàn toàn bởi `web.ignoring()` có thể bỏ qua các cơ chế bảo vệ khác. Thông thường nên ưu tiên `permitAll` cho tài nguyên công khai nếu vẫn muốn áp dụng security headers/chain.

### 2.3. `DispatcherServlet` và `HandlerMapping`

Sau security filters, `DispatcherServlet` phối hợp `HandlerMapping`/`HandlerAdapter` tìm `@Controller` hoặc `@RestController`. Spring MVC quyết định:
- `GET /api/orders/42` có handler không?
- `@PathVariable("id")`, `@RequestParam`, `@RequestHeader`, `@RequestBody` lấy dữ liệu ở đâu?
- JSON có giải mã được không?
- `@Valid`/method validation báo lỗi gì?
- Return DTO đi qua converter nào? Có render view hay trả body?
- Có `@ExceptionHandler`/`ResponseEntityExceptionHandler` nào xử lý exception được ném trong MVC không?

Spring Security không tự tạo endpoint `POST /api/orders` chỉ vì đã cấu hình `requestMatchers(HttpMethod.POST, "/api/orders")`. Ngược lại, MVC handler có tồn tại **không bảo đảm** user được phép tới nó. Hai cấu hình cần đồng bộ trong test.

## 3. Bảng trách nhiệm và ranh giới tin cậy

| Câu hỏi | Thành phần chính | Không nên nhầm với |
| --- | --- | --- |
| URL nào gọi method Java? | Spring MVC `HandlerMapping`, `@RequestMapping` | Quyền user được gọi method |
| Đọc JSON thành DTO? | MVC `HttpMessageConverter` và argument resolver | Authentication |
| Bind và validate form/query/body? | MVC + Jakarta Bean Validation | Permission/ownership |
| Ai đang gọi? | Spring Security authentication, `Authentication` | Field `userId` do client tự gửi |
| User được phép thao tác? | Security request rules, method security và service/domain authorization | CORS allow-origin |
| Chống form POST giả mạo dùng cookie? | CSRF protection và thiết kế cookie/session | `@Valid` trên DTO |
| Cross-origin browser có được đọc response? | CORS policy được MVC/Security phối hợp | Xác thực/ủy quyền người dùng |
| Thiết lập HSTS, frame options, CSP ...? | Security header configuration, proxy/web server phù hợp | JSON validation |
| Body của API và status thành công? | MVC controller/return handlers | Security filter quyết định mọi status |
| Lỗi thiếu credential/không đủ quyền? | Security `AuthenticationEntryPoint`, `AccessDeniedHandler` | Mặc định `@RestControllerAdvice` |
| Business invariant và phân quyền tài nguyên? | Domain/service + authorization logic | Chỉ kiểm URL prefix |

Một request có thể **vượt qua CORS nhưng bị 401**, có thể **đã authenticate nhưng bị 403**, hoặc **được phép hoàn toàn nhưng body JSON sai nên 400**. Đây là ba nguyên nhân khác nhau, không nên gom vào thông báo “CORS lỗi” hay “Spring controller không chạy”.

## 4. Authentication khác Authorization

**Authentication** trả lời “ai là principal?”. Trong Spring Security, một `Authentication` thường chứa principal, credentials (đã/đang được xử lý), authorities và trạng thái authenticated. Cơ chế xác thực có thể là username/password, HTTP Basic, form login, bearer token, OAuth2/OIDC hoặc custom; không mặc định phải dùng phiên Servlet cho mọi ứng dụng.

**Authorization** trả lời “principal có được thực hiện việc này không?”. Ví dụ `hasRole('ADMIN')`, `hasAuthority('orders:write')`, kiểm tra owner/tenant trong domain service, hoặc phương thức từ chối khi account bị khóa.

~~~text
Request --> xác thực identity --> kiểm quyền --> xử lý business
                |                   |
                |                   +-- không đủ quyền --> 403 thường gặp
                +-- thiếu/không hợp lệ --> 401 thường gặp với HTTP Basic/Bearer
~~~

Không tuyệt đối hóa status:
- HTTP Basic/Bearer thiếu xác thực thường dẫn đến **401 Unauthorized** (tên HTTP lịch sử dù nghĩa là “chưa xác thực”), có thể có `WWW-Authenticate`.
- Principal đã đăng nhập nhưng thiếu role thường **403 Forbidden**.
- `CsrfFilter` chặn POST thiếu CSRF token cũng có thể **403** dù credential đúng.
- Endpoint cố ý giấu sự tồn tại tài nguyên có thể trả 404 theo chính sách.
- Authentication mechanism, exception handlers và thứ tự filters ảnh hưởng status thực tế.

### 4.1. `SecurityContextHolder` và principal trong controller

Spring Security gắn `SecurityContext` với request/thread execution theo cơ chế đã cấu hình; `Authentication` có thể được truy cập qua `SecurityContextHolder` hoặc method argument `@AuthenticationPrincipal`. Trong MVC, tham số `Principal` hoặc `Authentication` cũng có thể được resolver cung cấp khi tích hợp Security.

~~~java
@GetMapping("/api/private/me")
public Map<String, String> me(Principal principal) {
    return Map.of("user", principal.getName());
}
~~~

Đây là fragment minh họa; không tự chạy độc lập. Không lấy `userId` từ body rồi tin nó là danh tính người dùng. Với API nhiều tenant, tenant ID từ path/header **phải được so khớp với principal/quyền**; chỉ kiểm `authenticated()` không đủ bảo vệ quyền truy cập đối tượng khác.

### 4.2. Role và authority

Spring Security thường lưu role với tiền tố `ROLE_`. Khi dùng `roles("ADMIN")` trong `UserDetails`, authority được tạo là `ROLE_ADMIN`. Biểu thức `hasRole('ADMIN')` kiểm `ROLE_ADMIN`, còn `hasAuthority('orders:read')` kiểm chính authority đó. Không tùy ý trộn `hasRole('ROLE_ADMIN')` với `hasRole('ADMIN')` mà không hiểu prefix và method configuration.

Role phù hợp nhóm quyền chung; permission theo tài nguyên, ownership và tenant có thể cần quyết định tại service/domain. `hasRole('ADMIN')` ở URL không thay thế mọi business rule.

## 5. Request-level authorization và method security

### 5.1. URL rules bên trong `SecurityFilterChain`

Một cấu hình request authorization có thể nói:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .requestMatchers("/api/private/**").authenticated()
    .anyRequest().denyAll())
~~~

Đây là fragment trong `HttpSecurity`. Nó quyết định request có đủ điều kiện qua `AuthorizationFilter`; **chưa biết handler thuộc controller nào, DTO có hợp lệ không, hoặc dữ liệu có thuộc user không**.

Chú ý thứ tự matcher: đặt quy tắc chuyên biệt trước, fallback `anyRequest()` sau. `permitAll` chỉ nói không yêu cầu authenticated principal cho route; CSRF vẫn có thể áp dụng cho unsafe HTTP method và CORS vẫn kiểm origin.

### 5.2. `@EnableMethodSecurity` và `@PreAuthorize`

Với Spring Security 6.x, annotation `@PreAuthorize` trên method/service cần `@EnableMethodSecurity` (hoặc cấu hình tương đương). Boot security starter **không mặc định bật method-level authorization** cho mọi project.

~~~java
@Service
class ReportService {
    @PreAuthorize("hasRole('ADMIN')")
    public Report readReport(long id) {
        return new Report(id, "internal");
    }
}
~~~

Fragment chưa khai báo/import kiểu `Report`. Ý nghĩa: khi method được Spring-managed proxy chặn theo cấu hình, người dùng thiếu role ADMIN bị từ chối ngay cả khi URL-level chỉ yêu cầu `authenticated()`.

**Ranh giới AOP proxy:** self-invocation gọi từ method này sang method khác **trong cùng object** thường không đi qua proxy, nên `@PreAuthorize` của method đích có thể không chạy. Không đặt mọi kiểm soát quan trọng ở một method nội bộ rồi gọi qua `this.method()`. Test đường gọi thật qua Spring bean boundary, hoặc dùng security strategy khác phù hợp.

Trong reactive stack annotation/method interception có khác biệt về ngữ cảnh; tài liệu ở đây tập trung Servlet MVC.

### 5.3. Defence in depth

Thiết kế tốt dùng nhiều lớp:
- Tầng gateway/network hạn chế nguồn hoặc tốc độ nếu cần; không coi gateway là người quyết định duy nhất.
- Tầng Security filter chặn request chưa xác thực và rule URL thô.
- Method security bảo vệ service use cases, kể cả khi một controller khác gọi cùng service.
- Domain/repository kiểm owner/tenant/data scope, tránh IDOR (Insecure Direct Object Reference).
- Bean Validation kiểm tra cấu trúc/chất lượng input; không thay permission.

Không dùng một role string do client tự gửi trong JSON để quyết định được phép cập nhật trường `isAdmin`. Nguồn authority phải đến từ authentication và authorization configuration, không từ body.

## 6. Validation khác Security: HTTP 400 không phải 401/403

Một request:

~~~http
POST /api/private/notes HTTP/1.1
Authorization: Basic <encoded-credentials>
Content-Type: application/json

{"text":""}
~~~

Có nhiều bước:
1. Browser/client gửi HTTP request.
2. Security CORS/CSRF/authentication/authorization có thể từ chối trước MVC.
3. Nếu Security cho qua, MVC parse JSON vào DTO.
4. `@Valid` kiểm `@NotBlank` và có thể ném `MethodArgumentNotValidException`.
5. Controller/service chỉ chạy khi request đã qua những ranh giới bắt buộc.

Như vậy cùng một request có thể nhận:
- **401** nếu chưa xác thực theo cơ chế HTTP Basic.
- **403** nếu có credentials nhưng thiếu CSRF token (với CSRF đang bật) hoặc không đủ quyền.
- **400** nếu qua bảo vệ nhưng body JSON sai hoặc vi phạm validation.
- **201** nếu hợp lệ và method tạo resource thành công (nếu API thiết kế status 201).

Không dựa vào thứ tự cố định giữa mọi lỗi trên một request chứa đồng thời nhiều vấn đề (CSRF, auth, body invalid). Kết quả phải kiểm thử theo SecurityFilterChain thực tế, không đoán từ controller annotation.

### 6.1. `@Valid` và `@Validated` không là security rules

`@Valid @RequestBody` kích hoạt Bean Validation trên DTO theo điều kiện Spring MVC. `@Validated` của Spring thường dùng validation groups/AOP method validation, **khác** `@EnableMethodSecurity` và `@PreAuthorize`. Cả hai có từ “method validation/security” nhưng không giải quyết cùng một mục tiêu.

Một field ownerId có `@NotNull` chỉ bảo đảm nó khác null, **không chứng minh** user hiện tại sở hữu ownerId. Business authorization phải so với principal và dữ liệu ở trusted store.

## 7. CORS là điểm giao giữa Web và Security

CORS dùng `Origin` và response headers để browser quyết định script từ origin khác có thể đọc response hay không. Nó **không xác thực principal** và **không ngăn curl/server-side HTTP client gọi API**.

Spring MVC cung cấp `@CrossOrigin` và `WebMvcConfigurer.addCorsMappings`; Spring Security có `http.cors(...)` để tích hợp cơ chế CORS vào security filter chain đúng thời điểm.

~~~text
Cross-origin browser:
  OPTIONS preflight (thường không mang cookie)
     -> CORS policy đánh giá Origin, method, request headers
     -> Nếu được phép, actual request mới gửi
     -> Actual request vẫn qua authentication, CSRF, authorization
     -> Actual response vẫn phải có CORS headers phù hợp
~~~

Nếu security filter đòi session/login trước khi xử lý OPTIONS, browser có thể bị 401/403 ở preflight, không bao giờ gửi POST thật. Giải pháp là cấu hình CORS sớm/phù hợp, không phải bỏ authentication ở actual POST.

### 7.1. Một policy mẫu

~~~java
@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(600);
    }
}
~~~

Đây là phần Java chưa có imports; phần app hoàn chỉnh bên dưới có file đầy đủ. `allowCredentials(true)` yêu cầu origin cụ thể thay vì `"*"`. Browser vẫn có thể chặn cookie theo `SameSite`, `Secure` và third-party cookie policy. Ngược lại, chỉ vì CORS cho phép một origin không có nghĩa tất cả user từ origin đó được quyền đọc các tài nguyên riêng tư.

**Không đồng nhất `Access-Control-Allow-Headers` với permission:** cho phép gửi `Authorization` header không có nghĩa token hợp lệ. Không dùng Origin header làm authentication proof, và không tự echo mọi origin vô điều kiện.

## 8. CSRF, authentication cookie và ý nghĩa của stateless

### 8.1. Tại sao có CSRF?

Nếu browser tự đính kèm session cookie (hoặc một credential tự gửi như Basic trong một số ngữ cảnh), website độc hại có thể khiến browser phát request thay đổi dữ liệu đến site đích. Dù response bị CORS chặn đọc, request **có thể đã được server xử lý** nếu đó là simple request. CSRF protection yêu cầu một điều kiện bổ sung mà trang độc hại không dễ đáp ứng.

Spring Security mặc định cung cấp CSRF protection cho nhiều ứng dụng Servlet; những method “unsafe” như POST, PUT, PATCH, DELETE thường yêu cầu token hợp lệ khi CSRF được bật.

**CORS không thay CSRF**; `@Valid` và HTTP method mapping cũng không.

### 8.2. Vì sao demo không tắt CSRF?

Để minh họa ranh giới, ví dụ hoàn chỉnh giữ CSRF **bật**. Một POST với username/password đúng nhưng thiếu CSRF token có thể nhận 403 trước khi đến controller. Test POST có cả authentication và `csrf()` sẽ kiểm được input/response của MVC.

Trong resource server nhận **bearer token chỉ qua Authorization header** và không dùng credentials do browser tự đính kèm, ứng dụng có thể có mô hình CSRF khác và quyết định bỏ CSRF có chủ đích. Nhưng cấu hình `SessionCreationPolicy.STATELESS` **không tự chứng minh** rằng mọi browser client miễn nhiễm CSRF; phải đánh giá cơ chế credential và điểm tạo side effects trước khi tắt.

### 8.3. Session state và API stateless

`SessionCreationPolicy.STATELESS` nói Spring Security không tạo/dùng `HttpSession` để lấy `SecurityContext` theo chính sách đó. Nó không ngăn hoàn toàn code ứng dụng gọi `request.getSession(true)`. HTTP Basic có thể xác thực mỗi request; bearer token API thường không cần session login. Web UI login bằng form thường dùng session và CSRF token.

Vì vậy đừng đưa một cấu hình “stateless + csrf.disable()” vào mọi ứng dụng Spring Security như công thức tối ưu. Chọn xác thực/cookies/CSRF theo threat model.

## 9. Các HTTP error paths: ai thực sự trả response?

| Tình huống | Điểm xử lý thường gặp | Status điển hình |
| --- | --- | --- |
| Không có/không hợp lệ HTTP Basic credential trên route riêng tư | Security authentication + `AuthenticationEntryPoint` | 401 |
| Có principal nhưng thiếu role từ request-level rule | Security `AccessDeniedHandler` | 403 |
| POST thiếu CSRF token (CSRF bật) | Security `CsrfFilter`/access denied processing | 403 |
| CORS preflight không hợp lệ | CORS processor ở filter hoặc handler mapping | Thường 403 hoặc browser chặn |
| Route đúng, body JSON malformed | Spring MVC converter / `HandlerExceptionResolver` | 400 |
| `@Valid` DTO không đạt | Spring MVC validation / advice | 400 |
| Media type không được handler nhận | Spring MVC mapping/converter | 415 |
| Không có handler khớp | MVC có thể trả 404 **nếu request đi qua Security** | 404 |
| Method bảo vệ bởi `@PreAuthorize` và không đủ role | Method security proxy, lỗi đi ngược call chain | 403 thường gặp |
| Exception nội bộ trong service | Handler/advice/container theo cấu hình | 500 |
| Controller return DTO bình thường | MVC return value handler/converter | 200/201... theo code |

Lưu ý: với `anyRequest().denyAll()`, một URL chưa có MVC handler vẫn có thể nhận 401/403 **trước** khi MVC kết luận 404. Do đó **không dùng HTTP status duy nhất để suy luận controller mapping có tồn tại**. Khi debug, kiểm request đã qua filter chain chưa.

### 9.1. Vì sao `@RestControllerAdvice` không bắt mọi Security exception?

`@RestControllerAdvice` được MVC chọn qua `HandlerExceptionResolver` trong `DispatcherServlet`. Lỗi xảy ra **ngoài MVC** như 401 từ `AuthenticationEntryPoint` hoặc 403 được filter chain xử lý sẽ không tự động đi qua advice.

Spring Security dùng:
- `AuthenticationEntryPoint` khi cần bắt đầu/đòi xác thực.
- `AccessDeniedHandler` khi quyết định từ chối quyền phù hợp.
- `ExceptionTranslationFilter` để chuyển một số security exceptions thành hành vi HTTP.

Nếu API yêu cầu error schema RFC 9457 đồng nhất, có thể viết các handler trên trả `ProblemDetail` hoặc gọi một shared error serializer, nhưng phải giữ **status 401/403 chính xác**, headers như `WWW-Authenticate` khi protocol đòi, và không lộ auth details. Không dùng catch-all `@ExceptionHandler(Exception.class)` rồi trả 400/500 cho mọi lỗi an ninh.

### 9.2. Method security exception có thể xuất hiện trong MVC call

`@PreAuthorize` đặt trên service gọi từ controller thường ném `AccessDeniedException` bên trong call chain MVC. Tùy `HandlerExceptionResolver`, filter exception translation và custom advice, ngoại lệ có thể đi ngược về Security filter và trở thành 403. Nếu viết một advice catch-all nuốt `AccessDeniedException` và biến nó thành 500/200, bạn có thể làm thay đổi HTTP semantics và log. Hãy test đúng URL/service với đầy đủ filter chain.

## 10. Ví dụ Spring Boot 3.3.5: Web + Security đúng ranh giới

Ứng dụng demo có:
- Public GET không cần đăng nhập.
- GET `/api/private/me` yêu cầu HTTP Basic và trả principal name.
- GET `/api/private/reports/{id}` yêu cầu authenticated ở URL và **ADMIN tại service**.
- POST `/api/private/notes` cần HTTP Basic, **CSRF token** và DTO body hợp lệ.
- CORS cho một frontend origin cụ thể. OPTIONS preflight được xét mà không cần cookie.
- MockMvc tests giữ nguyên Security filter chain, kiểm 200/201, 400, 401, 403 và preflight.

Không có database/persistent login. Username/password hard-coded chỉ để **demo local**, không được đưa vào production. Độ dài các đoạn code được giữ ở mức đọc hiểu nhưng là các file Java hợp lệ khi đặt đúng cấu trúc.

~~~text
web-security-boundary/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/boundary/
    │   ├── BoundaryApplication.java
    │   ├── config/SecurityConfig.java
    │   ├── config/CorsConfig.java
    │   ├── domain/ReportService.java
    │   └── web/BoundaryController.java
    └── test/java/com/example/boundary/
        └── BoundaryIntegrationTest.java
~~~

### 10.1. Gradle dependencies

`settings.gradle`:

~~~groovy
rootProject.name = 'web-security-boundary'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các starter:
- Web: Servlet MVC, Jackson, controller/JSON.
- Security: `SecurityFilterChain`, HTTP Basic, CSRF, request authorization.
- Validation: Jakarta Bean Validation provider cho `@NotBlank`.
- `spring-security-test`: helpers `httpBasic()`, `csrf()` trong MockMvc.

Cấu hình ví dụ cố ý dùng Spring Boot 3.3.5 / Security 6.x APIs. Nếu dùng Boot 4.x / Security 7.x, đối chiếu migration guide vì DSL, package/module và deprecated APIs có thể thay đổi; không trộn code version theo docs “current”.

### 10.2. Entry point

`src/main/java/com/example/boundary/BoundaryApplication.java`:

~~~java
package com.example.boundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
~~~

### 10.3. Security filter chain

`src/main/java/com/example/boundary/config/SecurityConfig.java`:

~~~java
package com.example.boundary.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers("/api/private/**").authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-user-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password(encoder.encode("local-admin-password"))
                        .roles("ADMIN")
                        .build());
    }
}
~~~

**Vì sao mỗi dòng nằm ở đây?**
- `cors(...)` kết nối policy CORS MVC với security flow, để preflight được xử lý trước việc cần auth.
- `csrf(...)` giữ kiểm tra CSRF cho unsafe methods, giúp chứng minh POST thiếu token bị 403 ngay cả khi đăng nhập đúng.
- Public/Private matchers chỉ quyết định quyền ở request level.
- `anyRequest().denyAll()` là fallback đóng; với một URL không tồn tại nhưng rơi vào fallback có thể thấy 401/403 thay vì 404.
- `httpBasic(...)` bật cơ chế authentication ở lớp Security; MVC không tự giải mã username/password ở controller.
- `@EnableMethodSecurity` cần thiết để `@PreAuthorize` trên ReportService thực sự được thực thi.
- UserDetailsService in-memory và password hard-coded là local demo, không phải mẫu production user store. Việc dùng BCrypt là để không lưu raw password trong cấu trúc `UserDetails`.
- Không có `formLogin(...)`, vì bài tập trung HTTP Basic. Không gắn `@PreAuthorize` trên các controller để giả vờ có method security nếu chưa bật proxy support.

### 10.4. CORS policy do Spring Web định nghĩa, Security tích hợp

`src/main/java/com/example/boundary/config/CorsConfig.java`:

~~~java
package com.example.boundary.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "Authorization", "X-CSRF-TOKEN")
                .allowCredentials(true)
                .maxAge(600);
    }
}
~~~

Đây là policy tường minh ở Web layer; Security `http.cors(...)` bảo đảm request đi qua xử lý CORS phù hợp trong security chain. Chỉ origin `https://app.example.test` được phép; wildcard `"*"` không thể kết hợp với credentialed CORS. Preflight có thể được chấp thuận **không cần xác thực**, còn actual GET/POST vẫn chịu `authorizeHttpRequests`, authentication và CSRF theo method.

Demo để `allowCredentials(true)` nhằm thể hiện giao diện credentialed; điều này **không tự khiến frontend gửi cookie**. Cookie còn phụ thuộc `fetch(credentials)`, SameSite, Secure và browser policy; HTTP Basic header không tự được CORS cho phép nếu không qua authentication.

Không cần thêm custom CorsFilter thứ hai khi policy này đã được Security/MVC tích hợp đúng. Nếu production có API gateway xử lý OPTIONS hoặc nhiều SecurityFilterChain, phải test toàn chuỗi cụ thể.

### 10.5. Service được bảo vệ bằng method security

`src/main/java/com/example/boundary/domain/ReportService.java`:

~~~java
package com.example.boundary.domain;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public record Report(long id, String summary) {}

    @PreAuthorize("hasRole('ADMIN')")
    public Report read(long id) {
        return new Report(id, "internal-demo");
    }
}
~~~

Security request rules `/api/private/**.authenticated()` chỉ đòi một user hợp lệ, còn `@PreAuthorize` yêu cầu authority `ROLE_ADMIN` cho **một use case cụ thể**. Vì controller gọi bean `ReportService` được Spring quản lý qua proxy, method security kiểm thêm quyền.

Không gọi `this.read(id)` từ một method khác **bên trong cùng bean** nếu mục tiêu là rely vào AOP interceptor của `@PreAuthorize`. Với hệ thống thật, các use cases nhạy cảm còn cần kiểm object ownership/tenant từ database.

### 10.6. Web controller: chỉ xử lý HTTP/application input

`src/main/java/com/example/boundary/web/BoundaryController.java`:

~~~java
package com.example.boundary.web;

import com.example.boundary.domain.ReportService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import java.security.Principal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class BoundaryController {

    private final ReportService reports;

    public BoundaryController(ReportService reports) {
        this.reports = reports;
    }

    public record NoteInput(@NotBlank String text) {}
    public record NoteReceipt(String text, String actor) {}

    @GetMapping("/public/ping")
    public Map<String, String> ping() {
        return Map.of("status", "UP");
    }

    @GetMapping("/private/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/private/reports/{id}")
    public ReportService.Report report(@PathVariable("id") long id) {
        return reports.read(id);
    }

    @PostMapping(path = "/private/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<NoteReceipt> create(
            Principal principal,
            @Valid @RequestBody NoteInput input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new NoteReceipt(input.text(), principal.getName()));
    }
}
~~~

`@RestController`, `@GetMapping`, `@PostMapping`, `@PathVariable`, `@RequestBody` và `@Valid` đều là phần Web/MVC + Bean Validation. Không có code “tự kiểm HTTP Basic” trong controller. Đối với private endpoints, `Principal` được cung cấp khi security authentication đã thành công.

`NoteInput` kiểm tra dữ liệu text không blank, không chứng minh user có quyền tạo note cho đối tượng khác. Demo trả receipt tạm và không lưu dữ liệu; production cần service/persistence, constraints về độ dài/nội dung, audit và transaction. `ReportService.read()` là nơi method security làm việc; controller vẫn map report thành JSON qua converter.

## 11. Kiểm thử tích hợp MockMvc với SecurityFilterChain thật

`src/test/java/com/example/boundary/BoundaryIntegrationTest.java`:

~~~java
package com.example.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BoundaryIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteIsAccessibleWithoutAuthentication() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void privateRouteRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/private/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicAuthenticationSetsPrincipalForMvc() throws Exception {
        mvc.perform(get("/api/private/me")
                        .with(httpBasic("alice", "local-user-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void methodSecurityBlocksNonAdmin() throws Exception {
        mvc.perform(get("/api/private/reports/9")
                        .with(httpBasic("alice", "local-user-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void methodSecurityAllowsAdmin() throws Exception {
        mvc.perform(get("/api/private/reports/9")
                        .with(httpBasic("admin", "local-admin-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.summary").value("internal-demo"));
    }

    @Test
    void authenticatedPostWithoutCsrfStillFails() throws Exception {
        mvc.perform(post("/api/private/notes")
                        .with(httpBasic("alice", "local-user-password"))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void validPostWithAuthenticationAndCsrfReachesController()
            throws Exception {
        mvc.perform(post("/api/private/notes")
                        .with(httpBasic("alice", "local-user-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"hello\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.text").value("hello"))
                .andExpect(jsonPath("$.actor").value("alice"));
    }

    @Test
    void invalidDtoIsMvcValidationNotAuthenticationFailure()
            throws Exception {
        mvc.perform(post("/api/private/notes")
                        .with(httpBasic("alice", "local-user-password"))
                        .with(csrf())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"text\":\"\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void corsPreflightIsProcessedBeforeAuthentication() throws Exception {
        mvc.perform(options("/api/private/notes")
                        .header("Origin", "https://app.example.test")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers",
                                "content-type,x-csrf-token"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin",
                        "https://app.example.test"))
                .andExpect(header().string("Access-Control-Allow-Credentials",
                        "true"));
    }

    @Test
    void disallowedOriginCannotUsePreflight() throws Exception {
        mvc.perform(options("/api/private/notes")
                        .header("Origin", "https://evil.example.test")
                        .header("Access-Control-Request-Method", "POST")
                        .header("Access-Control-Request-Headers",
                                "content-type"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Test phân tách trách nhiệm:**
- `publicRoute...` chứng minh `permitAll`, không cần Basic credential.
- `privateRoute...` nhận 401 trước khi controller hoạt động.
- `basicAuthentication...` chứng minh Security xác thực, MVC nhận principal.
- `methodSecurityBlocks...` và `methodSecurityAllows...` chứng minh role ADMIN được kiểm ở service, không chỉ URL.
- `authenticatedPostWithoutCsrf...` chứng minh CSRF là ranh giới riêng của authentication.
- `validPost...` chứng minh đủ auth + CSRF thì MVC mới đọc/validate body và trả 201.
- `invalidDto...` với auth/CSRF đầy đủ trả 400 do Web/validation.
- `corsPreflight...` chứng minh OPTIONS không cần username/password để kiểm CORS policy.
- `disallowedOrigin...` kiểm allowlist, không echo Origin tùy ý.

MockMvc có Spring Security test helpers nhờ `spring-security-test`. Không dùng `@AutoConfigureMockMvc(addFilters=false)` cho các test về auth/CSRF: làm vậy bỏ filter chain và biến 401/403 thành kết quả sai. Không chỉ test controller trực tiếp bằng gọi Java method nếu mục tiêu là xác minh HTTP security boundary.

Nếu code về Spring Security hoặc validation được tùy chỉnh trong dự án thực, statuses/body có thể đổi theo entry point/advice. Test ở đây mô tả app demo với cấu hình hiện tại. Để kiểm tra browser cookie, SameSite, reverse proxy và preflight cache, cần thêm end-to-end HTTP/browser tests.

## 12. Chạy ứng dụng qua curl: chứng minh từng tầng

Tạo Gradle wrapper tương thích với Java 17/Spring Boot 3.3 nếu project chưa có. Khi đã có wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Trên Windows dùng `.\gradlew.bat test` và `.\gradlew.bat bootRun`. Hai lệnh chạy ở terminal/tác vụ phù hợp; `bootRun` thường giữ server chạy ở port 8080.

### 12.1. Public GET

~~~bash
curl -i 'http://localhost:8080/api/public/ping'
~~~

Dự kiến status 200, body:

~~~json
{"status":"UP"}
~~~

### 12.2. Private GET không có credentials

~~~bash
curl -i 'http://localhost:8080/api/private/me'
~~~

Dự kiến HTTP **401** (có thể có `WWW-Authenticate`). Không phải thiếu controller: request bị Security yêu cầu xác thực.

### 12.3. Private GET có Basic credentials

~~~bash
curl -i -u alice:local-user-password \
  'http://localhost:8080/api/private/me'
~~~

Dự kiến HTTP **200**:

~~~json
{"user":"alice"}
~~~

`curl -u` gửi credential HTTP Basic qua header Authorization sau encoding, **không mã hóa an toàn trên đường truyền nếu dùng HTTP thật**. Demo local dùng HTTP cho dễ kiểm; production phải dùng HTTPS và không đặt mật khẩu demo trong Git/config public.

### 12.4. Thiếu role ADMIN ở service

~~~bash
curl -i -u alice:local-user-password \
  'http://localhost:8080/api/private/reports/9'
~~~

Dự kiến **403 Forbidden**, dù request đã được xác thực ở SecurityFilterChain. Đó là quyết định của `@PreAuthorize` trên `ReportService.read`, không phải do `@GetMapping`.

~~~bash
curl -i -u admin:local-admin-password \
  'http://localhost:8080/api/private/reports/9'
~~~

Dự kiến **200**:

~~~json
{"id":9,"summary":"internal-demo"}
~~~

### 12.5. POST có Basic nhưng thiếu CSRF

~~~bash
curl -i -u alice:local-user-password \
  -X POST 'http://localhost:8080/api/private/notes' \
  -H 'Content-Type: application/json' \
  -d '{"text":"hello"}'
~~~

Dự kiến **403** do CSRF khi cấu hình demo giữ token validation. Đừng kết luận password sai chỉ từ status này. Để thử thành công trong integration test, dùng `SecurityMockMvcRequestPostProcessors.csrf()` như mục 11.

Với HTTP client thật, muốn POST hợp lệ phải lấy token từ cơ chế `CsrfTokenRepository` và gửi đúng cookie/header/parameter theo ứng dụng. Demo chưa mở endpoint cấp CSRF token, nên **không bịa một token hay lệnh curl thành công**. Nếu cần SPA cookie-based, cân nhắc `CookieCsrfTokenRepository` và thiết kế endpoint/CSRF token request handler phù hợp phiên bản, đồng thời bảo vệ against XSS.

### 12.6. Preflight OPTIONS không mang Basic credentials

~~~bash
curl -i -X OPTIONS 'http://localhost:8080/api/private/notes' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

CORS config của demo cho phép origin, method, headers; status 2xx và `Access-Control-Allow-Origin: https://app.example.test` (thường 200). **Không có nghĩa browser đã được cấp quyền POST**: actual request vẫn cần authentication, CSRF và authorization.

Một preflight từ `https://evil.example.test` sẽ bị CORS từ chối (thường 403) trong app. curl không tự chạy cơ chế CORS như trình duyệt, nó chỉ gửi đúng HTTP request bạn mô tả.

## 13. Ranh giới Spring Security và CORS khi có nhiều chains

### 13.1. Multiple SecurityFilterChain

Khi xây ứng dụng vừa có web UI dùng form login, vừa có REST API dùng bearer token, thường cần nhiều chains. Ví dụ thiết kế khái niệm:

~~~text
@Order(1): /api/**    -> resource server, bearer auth, API authorization
@Order(2): /**        -> form login, session, CSRF, web pages
~~~

Không copy ví dụ này thành code runnable; cần dependency OAuth2 Resource Server/JWT, issuer/audience validation, session/CSRF policy, error handlers và matcher order cụ thể. Hãy thiết kế sao cho **không có gap** giữa các chains và tránh chain catch-all đứng trước chain chuyên biệt.

### 13.2. `securityMatcher` khác `requestMatchers`

~~~java
// Fragment khái niệm, không phải file cấu hình đầy đủ:
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .anyRequest().authenticated());
~~~

`securityMatcher` quyết định request có được xử lý bởi chain này; `requestMatchers` quyết định quyền bên trong chain. Nếu bạn chỉ có chain giới hạn `/api/**` mà không có fallback chain cho `/admin/**`, admin routes có thể nằm ngoài SecurityFilterChain đó. **Kiểm tra `FilterChainProxy` và logs/debug chain matching** trong các integration tests quan trọng.

### 13.3. MVC matcher và Security matcher cần nhất quán

Spring MVC có semantics của URL patterns, path variables và context/servlet path; Spring Security có `RequestMatcher` phù hợp theo config. Mismatched pattern có thể tạo vùng không bảo vệ hoặc từ chối nhầm; nhất là khi custom servlet path, encoded path, reverse proxy rewrites, trailing slash, matrix variables.

Đừng dựa vào string-prefix check tự chế như `request.getRequestURI().startsWith("/admin")` làm authorization. Dùng matcher Spring Security đúng và test cả encoding/normalization nếu ứng dụng có input URL phức tạp.

## 14. Security headers và trách nhiệm hạ tầng

Spring Security có cơ chế phát security response headers (ví dụ cache-control cho protected responses, `X-Content-Type-Options`, `X-Frame-Options`, HSTS trên HTTPS khi cấu hình phù hợp). Spring MVC chịu trách nhiệm content type/response serialization; reverse proxy hoặc server có thể thiết lập TLS, HSTS, Content Security Policy và các headers khác.

| Nhu cầu | Thành phần thường chịu trách nhiệm | Lưu ý |
| --- | --- | --- |
| HTTPS termination | Proxy/load balancer/container | Forwarded headers phải được xử lý đáng tin |
| HSTS | Spring Security/proxy | Chỉ có ý nghĩa khi HTTPS và host đáp ứng policy |
| CSP cho HTML/JS | Security headers hoặc proxy | Cần policy phù hợp frontend, không bật wildcard script vô tội vạ |
| CORS allowlist | MVC `CorsConfiguration` + Security CORS integration | Không thay authentication |
| Session cookie flags | Container/Spring Boot/Security/proxy | `Secure`, `HttpOnly`, `SameSite` là chính sách khác CORS |
| Error serialization | MVC `ProblemDetail`/advice; Security entry point/denied handler | Đồng nhất schema cần hai đường xử lý |
| Rate limiting | Gateway/filter/service chuyên trách | Spring Security core không mặc định thay thế mọi rate limiter |
| Authorization dữ liệu/tenant | Security method + domain/repository | URL role chưa đủ |

Không khẳng định mọi security header đều được bật mặc định và đúng cho mọi product. Trong triển khai thật, hãy xem response thực qua browser/HTTP và thiết lập security policy có chủ đích.

## 15. Sai lầm thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xác minh |
| --- | --- | --- |
| Thấy `@RestController` nên nghĩ route an toàn | Controller annotation không là authentication/authorization | Kiểm `SecurityFilterChain` và negative tests |
| Security cho `/api/**` nhưng URL trả 404 | Chỉ có security matcher, MVC handler không tồn tại | Kiểm MVC mappings |
| Controller breakpoint không chạy, HTTP 401 | Filter chain yêu cầu authentication trước MVC | Inspect Basic/bearer entry point và filter chain |
| Đã đăng nhập mà POST bị 403 | Thiếu CSRF hoặc quyền | Kiểm CSRF token và AccessDeniedHandler |
| HTTP 403 khi đọc report dù `authenticated()` | `@PreAuthorize` yêu cầu role ADMIN | Kiểm service method proxy/authorities |
| `@PreAuthorize` không có tác dụng | Chưa bật `@EnableMethodSecurity` hoặc self-invocation | Kiểm bean/proxy và integration tests |
| Basic user có `ADMIN` mà vẫn bị chặn | Nhầm role vs authority/prefix | Kiểm `ROLE_ADMIN` và `hasRole('ADMIN')` |
| CORS preflight 401 | Security đòi auth trước xử lý CORS | `http.cors(...)`, source policy và chain order |
| OPTIONS 200 nhưng POST vẫn 403 | CORS chỉ cho phép browser gửi; actual thiếu auth/CSRF | Inspect actual request filters |
| Browser báo CORS nhưng backend log 500 | Error response không có allow-origin | Kiểm status/log, CORS trên error path |
| Cookie không gửi dù CORS cho phép | SameSite/Secure/domain/third-party policy | Browser devtools và fetch credentials |
| `@ControllerAdvice` không bắt Basic auth 401 | Lỗi xử lý ở filter trước DispatcherServlet | Tạo `AuthenticationEntryPoint` nếu cần custom JSON |
| Catch-all advice biến AccessDeniedException thành 500 | Advice nuốt security exception trong MVC | Giữ semantics, test full filter chain |
| Unknown route trả 403 thay 404 | `anyRequest().denyAll()` chặn trước MVC | Xem fallback policy |
| Security test luôn nhận 200 | Test bỏ filter bằng `addFilters=false` | Bật filter chain, dùng `spring-security-test` |
| MVC test thiếu 400 validation | Thiếu validation provider/`@Valid` hoặc request chưa qua Security | Bổ sung starter và test auth/CSRF trước |
| Hai filter security chạy bất thường | Đăng ký filter thủ công và qua SecurityFilterChain | Kiểm double registration/filter order |
| Nhiều security chains, path bị lọt | Sai `securityMatcher` hoặc thứ tự `@Order` | Test từng route + fallback |
| Stateless nhưng vẫn có JSESSIONID | Component khác tạo session, không chỉ SecurityContext | Trace `getSession(true)`, filters/MVC |
| CORS allow-origin `*` và credentials=true | Browser không chấp nhận wildcard credentialed | Dùng allowlist chính xác |
| Client có `userId` trong JSON và sửa được đơn người khác | Thiếu object-level authorization | Kiểm principal với entity owner/tenant ở service |

## 16. Khi nào dùng API nào? Cây quyết định

~~~text
Yêu cầu cần xử lý?
|
+-- Định tuyến HTTP URL/method?          -> Spring MVC @RequestMapping
+-- Đọc query/path/header/JSON?          -> MVC argument resolvers/converters
+-- Kiểm JSON/form DTO?                  -> Jakarta Bean Validation @Valid
+-- Biến return value thành JSON?        -> @RestController / HttpMessageConverter
|
+-- Xác định user/client?                -> Spring Security Authentication
+-- User có được gọi route không?        -> authorizeHttpRequests
+-- User có được gọi service method?     -> @EnableMethodSecurity + @PreAuthorize
+-- User có sở hữu tài nguyên không?     -> domain authorization với principal
+-- Ngăn forged cookie-authenticated POST? -> CSRF policy
+-- CORS browser cross-origin?          -> MVC CorsConfiguration + Security cors
+-- Bảo vệ session/cookie/security headers? -> Security/container/proxy
|
+-- Tạo error JSON?
      +-- MVC parse/validation/domain exception -> @RestControllerAdvice
      +-- 401/403 từ filters                 -> AuthenticationEntryPoint
                                               / AccessDeniedHandler
~~~

**Thứ tự thiết kế hợp lý:** xác định authentication mechanism và threat model → định nghĩa request-level và method/domain authorization → xác định CSRF/CORS/session/header policies → định nghĩa Web DTO/validation/response → test xuyên filter chain và MVC. Không xây controller “cho chạy được” rồi mới cố bọc security bằng vài regex URL.

## 17. Checklist triển khai và review

1. Kiểm chính xác Spring Boot/Spring Framework/Security versions; dùng API/docs khớp version.
2. Vẽ request path từ Servlet container qua `DelegatingFilterProxy`/`FilterChainProxy` tới `DispatcherServlet`.
3. Định nghĩa một hoặc nhiều `SecurityFilterChain` có matcher và fallback rõ ràng; test chain order.
4. Chọn authentication method hợp với client, tránh hard-coded credential ở production.
5. Bật request authorization, và `@EnableMethodSecurity` nếu dùng `@PreAuthorize`.
6. Kiểm domain ownership/tenant/data scope; tránh IDOR dù role hợp lệ.
7. Xác định nơi bật/giữ CSRF dựa trên cookie/credential model; không disable chỉ vì là REST.
8. Cấu hình CORS allowlist ở nguồn rõ ràng, tích hợp Security trước authentication cho preflight.
9. Thiết kế request DTO + Bean Validation riêng khỏi authentication/authorization.
10. Chuẩn hóa 400 từ MVC và 401/403 từ Security mà không làm mất headers/protocol semantics.
11. Giữ filter chain thật trong MockMvc tests; test public/private, role, method security, CSRF, CORS, invalid DTO.
12. Kiểm cookies/TLS/forwarded headers, response headers và error paths qua E2E/proxy.
13. Tránh self-invocation cho method security và duplicate filter registration.
14. Kiểm application logs và security diagnostics có kiểm soát; không log password/token/cookie.
15. Đừng giả định Spring Security tự định tuyến MVC hay MVC tự bảo vệ endpoint.

### Câu hỏi tự kiểm tra

**1.** Spring MVC controller nhận JSON sai và user chưa xác thực thì HTTP sẽ luôn 400?

**Trả lời:** Không. Security filters có thể dừng request trước khi MVC đọc JSON; với HTTP Basic route private, response có thể 401. Khi muốn kiểm lỗi JSON, test với auth/CSRF hợp lệ.

**2.** Vì sao `@GetMapping("/admin")` không đảm bảo chỉ admin vào?

**Trả lời:** `@GetMapping` chỉ định tuyến. Phải thiết lập request/method/domain authorization riêng.

**3.** `permitAll()` có đồng nghĩa vô hiệu hóa CSRF/CORS không?

**Trả lời:** Không. Nó chỉ cho qua một rule authorization; các filter bảo vệ khác có thể tiếp tục kiểm.

**4.** Tại sao method có `@PreAuthorize` vẫn chạy nếu gọi từ `this.method()`?

**Trả lời:** Spring AOP proxy thường không intercept self-invocation. Dùng Spring bean boundary/test phù hợp.

**5.** CORS preflight được phép có nghĩa POST sẽ thành công?

**Trả lời:** Không. Actual POST vẫn phải qua authentication, CSRF, authorization, MVC validation và business logic.

**6.** Ai thường tạo HTTP 401 cho unauthenticated Basic request?

**Trả lời:** Spring Security authentication entry point, không phải controller `@ExceptionHandler` của MVC.

**7.** Tại sao có thể nhận 403 thay vì 404 ở route không tồn tại?

**Trả lời:** `anyRequest().denyAll()` ở filter chain có thể chặn trước khi request đến `DispatcherServlet`.

**8.** Vai trò của `@Valid` có thay `@PreAuthorize` không?

**Trả lời:** Không. `@Valid` kiểm dữ liệu; `@PreAuthorize` kiểm quyền gọi method.

## 18. Tài liệu chính thức

- [Spring Security 6.3 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.3/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain` và thứ tự filter.
- [Spring Security 6.3 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/authorize-http-requests.html): `authorizeHttpRequests`, `requestMatchers` và matcher scope.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, AOP proxy và các annotations khác.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection trong ứng dụng Servlet và SPA considerations.
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): preflight phải được xử lý trước authentication, tích hợp với Spring MVC.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter): `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- [Spring Framework — Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html): handler mapping, adapter, view và exception resolution.
- [Spring Framework — Spring MVC Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html): mappings, argument resolvers, response bodies.
- [Spring Framework — Validation trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): `@Valid`, method validation và các loại lỗi.
- [Spring Boot 3.3 — Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): auto-configuration và cách ứng dụng tùy chỉnh `SecurityFilterChain`.

**Ghi nhớ:** Spring Web giải quyết việc **request được ánh xạ, đọc, validate và phản hồi như thế nào**; Spring Security giải quyết việc **ai đang gọi, được phép làm gì và request được bảo vệ ra sao**. CORS là phần giao, nhưng không phải authentication; CSRF và authorization là ranh giới riêng. Kiểm thử đủ **filter chain + DispatcherServlet + service** mới phản ánh đúng hành vi và an toàn của endpoint.
