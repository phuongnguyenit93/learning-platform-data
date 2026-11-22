# Đọc dấu vết một yêu cầu từ bộ lọc đầu tiên tới Controller

Một ngày, API `GET /me` đang hoạt động bình thường bỗng trả `401`. Người phụ trách Controller đặt breakpoint trong method `me()` nhưng breakpoint **không bao giờ được gọi**. Họ tưởng ứng dụng không định tuyến đúng, trong khi request thực ra đã tới Spring Boot và bị từ chối **trước khi đi vào Controller**. Một ngày khác, `POST /notes` trả `403` dù username/password đúng; lần này nguyên nhân là CSRF filter không cho phép request đi tiếp. Vì sao biết request dừng ở đâu?

Cần đọc được **dấu vết đi qua Servlet FilterChain**, đặc biệt chuỗi Spring Security filters. Trong Spring MVC, HTTP request đi từ servlet container qua một số container filters, tới `DelegatingFilterProxy`, vào `FilterChainProxy`, được chọn một `SecurityFilterChain`, chạy lần lượt các security filters, rồi **chỉ khi không bị chặn** mới tới `DispatcherServlet` và Controller. Sau khi Controller trả về, lời gọi `chain.doFilter` được tháo ngược, các filter có thể thực thi nốt phần `finally`/post-processing của mình.

Bài học giúp bạn trả lời bằng bằng chứng:

- Request có đi vào Spring Security không?
- `SecurityFilterChain` nào được chọn, những filters nào thực sự được gọi?
- Khi nào `SecurityContext` được nạp, khi nào credentials được kiểm tra, khi nào quyền bị từ chối?
- Vì sao một request dừng trước Controller hoặc chạy Controller rồi mới lỗi?
- Phân biệt `401`, `403`, `302`, `404`, `500` bằng dấu vết thay vì đoán.
- Đọc log `DEBUG`/`TRACE` của Spring Security theo thứ tự và gắn chúng với cùng một request.
- Gắn các **điểm đánh dấu trước/sau** trong security chain để thấy đường vào, đường ra và short-circuit.
- Chạy một ứng dụng **Java 17+ / Spring Boot 4.1.2** và kiểm tra chính xác dấu vết bằng `MockMvc`.

Phạm vi là **Servlet stack** của Spring Security với Spring MVC. WebFlux sử dụng `WebFilter`/`SecurityWebFilterChain` và Reactor Context, không có cùng mô hình `jakarta.servlet.FilterChain` và `DispatcherServlet`.

## 1. Hình dung đường đi của một HTTP request

Sơ đồ từ ngoài vào trong:

~~~text
Client
  |
  |  GET /me
  |  Authorization: Basic <giá trị đã được ẩn>
  v
Reverse proxy / load balancer / TLS termination (nếu có)
  |
  v
Servlet container: Tomcat/Jetty/Undertow
  |
  +--> Các Servlet Filter ở tầng container (nếu đăng ký)
  |       |
  |       v
  +--> DelegatingFilterProxy ("springSecurityFilterChain")
  |       |
  |       v
  |   Spring Bean: FilterChainProxy
  |       |
  |       +--> HttpFirewall xác minh/bọc request
  |       +--> Chọn SecurityFilterChain khớp ĐẦU TIÊN
  |       |
  |       +--> Security Filter A (ví dụ SecurityContextHolderFilter)
  |       +--> Security Filter B (ví dụ CsrfFilter)
  |       +--> Security Filter C (ví dụ BasicAuthenticationFilter)
  |       +--> Security Filter D (ví dụ AnonymousAuthenticationFilter)
  |       +--> Security Filter E (ví dụ ExceptionTranslationFilter)
  |       +--> Security Filter F (ví dụ AuthorizationFilter)
  |       |
  |       v
  +--> Các container filters phía sau, nếu có
  |       |
  |       v
  +--> DispatcherServlet
          |
          +--> HandlerMapping chọn Controller method
          +--> HandlerInterceptor.preHandle nếu có
          +--> Argument resolvers / binding / validation
          +--> Controller
          +--> Service / repository
          +--> Serialize response
          +--> HandlerInterceptor.postHandle / afterCompletion phù hợp
  |
  v
HTTP response
~~~

**Đây là sơ đồ khái niệm**, không phải danh sách/thứ tự chính xác của mọi Spring Security version. Filter nào có mặt phụ thuộc việc bạn bật form login, HTTP Basic, OAuth2 resource server, CSRF, CORS, session, logout, custom filters và các chain riêng. Khi debug, **log danh sách thật từ ứng dụng đang chạy** thay vì copy một danh sách bất biến từ Internet.

### Phân biệt bốn loại thành phần

| Thành phần | Vị trí | Mục đích |
| --- | --- | --- |
| Servlet `Filter` | Trước/sau `DispatcherServlet` | Có thể xem/chặn/bọc request hoặc response |
| `FilterChainProxy` | Spring Security, được gọi bởi `DelegatingFilterProxy` | Chọn một danh sách Spring Security filters theo request |
| `HandlerInterceptor` | Spring MVC, sau khi request tới `DispatcherServlet` | Bổ sung xử lý quanh handler MVC, không thay thế bộ lọc bảo mật |
| Controller/Service | Lớp ứng dụng | Xử lý nghiệp vụ sau các bước đã cho request đi tiếp |

Khi breakpoint Controller không chạy, điều đó **không chứng minh** Controller bị lỗi. Đầu tiên phải hỏi: request có bị một `Filter` chặn, bị `HttpFirewall` reject, bị redirect, hay chưa match được URL/handler?

Một `Filter` có thể không gọi `chain.doFilter`; lúc ấy toàn bộ chuỗi phía sau bị bỏ qua. Đây là hành vi hợp lệ của mô hình Servlet Filters và chính là cách nhiều bộ lọc bảo mật từ chối request.

## 2. chain.doFilter: chiều đi vào và chiều quay ra

Trong Java Servlet, đoạn code điển hình:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    before();                 // Trước downstream
    try {
        chain.doFilter(request, response); // Gọi bước tiếp theo
    } finally {
        after();              // Sau downstream, kể cả khi có exception
    }
}
~~~

Đây là fragment minh họa; `before()` và `after()` là phương thức giả định do ứng dụng cung cấp, không phải API Servlet.

Giả sử filter A, B, C đều gọi `chain.doFilter` và Controller trả thành công:

~~~text
A: before
  B: before
    C: before
      Controller
    C: after
  B: after
A: after
~~~

Thứ tự **vào** là A → B → C → Controller; thứ tự **thoát** là C → B → A. Các khối `finally` chạy ngược theo call stack ngay cả khi một filter sâu hơn ném exception (trừ trường hợp tiến trình/JVM bị chấm dứt bất thường).

Nếu B quyết định trả `403` mà **không gọi `chain.doFilter`**, thì C và Controller không chạy:

~~~text
A: before
  B: before
  B: reject -> response 403
  B: after (nếu B có finally)
A: after
~~~

Dấu vết thiếu C/Controller **không nhất thiết là lỗi logging**; rất có thể pipeline đã short-circuit hợp lệ.

### Vì sao một filter có thể in log “after” nhưng request vẫn chưa xong?

Một filter bao ngoài có thể ghi dòng “after” sau khi downstream hoàn tất, nhưng trước khi container flush toàn bộ response hoặc kết thúc xử lý async. Ngay cả `response.getStatus()` ở một filter **ở sâu trong chuỗi** có thể chưa phản ánh mã HTTP cuối cùng nếu một filter **bao ngoài** bắt exception rồi đổi status sau đó.

Vì thế cần biết **điểm đặt filter** khi diễn giải log. Dấu `after` trong custom filter có thể chứng minh control đã quay về điểm ấy, nhưng không luôn là phép đo trạng thái HTTP cuối cùng.

## 3. FilterChainProxy chọn chain trước khi đi qua các security filters

Mỗi `SecurityFilterChain` gồm một `RequestMatcher` và một danh sách các Spring Security filters. `FilterChainProxy` xét lần lượt và dùng **chain khớp đầu tiên**.

Ví dụ:

~~~text
@Order(1): securityMatcher("/api/**")
@Order(2): securityMatcher("/admin/**")
@Order(3): matcher mặc định, khớp mọi request

GET /api/data    -> API chain
GET /admin/panel -> Admin chain
GET /web/me      -> fallback chain
~~~

Khi đã chọn API chain, nếu API filter trả 401, proxy **không thử tiếp** Admin/Web chain để tìm một cách đăng nhập khác. Các filter nằm trong chain sau cũng **không được thêm vào** chain đầu.

Nếu không có fallback và không chain nào khớp, Spring Security có thể **không bảo vệ request ấy**. Trường hợp này rất khác một request đã vào chain nhưng được `permitAll()`:

- **Không chain match:** không đi qua danh sách security filters mà các chain cung cấp.
- **`permitAll()`:** request đi qua chain được chọn, còn authorization rule quyết định cho phép.

### Đọc đúng matcher trong log

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/public").permitAll()
        .anyRequest().authenticated());
~~~

`securityMatcher` dùng để **chọn chain**. `requestMatchers` bên trong `authorizeHttpRequests` chọn **rule phân quyền sau khi chain đã được chọn**. `anyRequest()` ở đây chỉ xét request thuộc chain đó, **không áp cho mọi URL bên ngoài `/api/**`**.

Để đọc trace chính xác, phải biết chain được chọn, nếu không dễ nhìn nhầm một rule nằm trong chain không hề được gọi.

## 4. Những filter thường gặp và dấu hiệu quan sát

Một request username/password hoặc HTTP Basic có thể đi qua nhiều giai đoạn:

| Giai đoạn | Filter/nhóm tương ứng thường gặp | Điều quan sát được |
| --- | --- | --- |
| Chuẩn hóa request | `HttpFirewall` do `FilterChainProxy` áp dụng | Request bị reject sớm với path bất thường, có thể chưa thấy log từng security filter |
| Khôi phục SecurityContext | `SecurityContextHolderFilter` | Context có thể được nạp trì hoãn từ repository, sau request được dọn |
| Security response headers | `HeaderWriterFilter` | Một số headers bảo vệ được viết theo cấu hình |
| CSRF | `CsrfFilter` | POST/PUT/... thiếu hoặc sai token có thể bị 403 trước Authentication |
| Authentication | `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter` hay cơ chế token | Mật khẩu/token được kiểm tra; không hợp lệ có thể kết thúc bằng 401/redirect |
| Anonymous fallback | `AnonymousAuthenticationFilter` | Nếu chưa có identity, có thể đặt AnonymousAuthenticationToken |
| Chuyển exception bảo mật | `ExceptionTranslationFilter` | Chuyển lỗi auth/access thành entry point hoặc AccessDeniedHandler |
| Authorization | `AuthorizationFilter` | Quyết định permit/deny theo request và Authentication |
| MVC dispatch | `DispatcherServlet` | Chọn handler, gọi Controller, xử lý serialization/error |

**Thứ tự thực tế còn có nhiều filters khác**, như `DisableEncodeUrlFilter`, `WebAsyncManagerIntegrationFilter`, `LogoutFilter`, `RequestCacheAwareFilter`, `SecurityContextHolderAwareRequestFilter`. Không được suy từ bảng này rằng tất cả filter luôn hiện diện hoặc rằng CSRF là filter đầu tiên.

Về đại thể: **SecurityContext → exploit protections → authentication → authorization → controller**. Muốn biết chính xác, dùng danh sách filter mà Spring Security in ở DEBUG khi startup hoặc log TRACE cho từng request.

### 4.1. SecurityContextHolderFilter không phải bước xác minh password

`SecurityContextHolderFilter` giúp cung cấp `SecurityContext` từ `SecurityContextRepository` cho request. Nó **không tự kiểm tra mật khẩu**. Với session-based login, context có thể được khôi phục từ HTTP session; với stateless API, filter khác có thể xác thực credentials của request.

Trong Spring Security 6/7, `SecurityContextHolderFilter` tập trung **tải** context, không tự động save thay cho code custom. Sau khi request kết thúc, security context liên kết với thread phải được dọn đúng. Điều đó không tự logout session của người dùng.

### 4.2. BasicAuthenticationFilter có thể chặn trước Controller

Ví dụ:

~~~text
GET /me
Authorization: Basic <base64 username:password, không phải mã hóa bảo mật>
        |
        v
BasicAuthenticationFilter
        |
   password sai
        |
        v
AuthenticationEntryPoint -> HTTP 401
        |
    Không tới Controller
~~~

Với mật khẩu đúng, provider trả `Authentication` hợp lệ; các bước còn lại có thể dùng principal/authorities để phân quyền. Không log Basic credential dưới dạng base64: bất kỳ ai đọc được có thể giải mã và lấy raw password.

### 4.3. CsrfFilter có thể chặn trước cả bước xác thực

Nếu CSRF protection bật cho phương thức ghi và request thiếu token:

~~~text
POST /notes
Authorization: Basic <đã ẩn>
        |
        v
CsrfFilter
        |
    missing / invalid CSRF token
        |
        v
AccessDeniedHandler -> HTTP 403
        |
   BasicAuthenticationFilter có thể chưa chạy
   AuthorizationFilter không chạy
   Controller không chạy
~~~

Đây là lý do **không được suy rằng 403 luôn là thiếu ROLE_...**. Nó có thể đến từ cơ chế CSRF, không phải `AuthorizationFilter`.

### 4.4. ExceptionTranslationFilter chuyển lỗi bảo mật như thế nào?

Một sơ đồ khái niệm:

~~~text
ExceptionTranslationFilter
    |
    +--> gọi downstream: AuthorizationFilter / MVC / service
    |        |
    |        +--> AccessDeniedException hoặc AuthenticationException
    |                 |
    |                 v
    +--> Phân loại trạng thái chủ thể và exception
              |
              +--> Cần xác thực -> AuthenticationEntryPoint
              |       HTTP Basic thường 401 + WWW-Authenticate
              |       Form login thường redirect /login
              |
              +--> Đã xác thực nhưng thiếu quyền
                      -> AccessDeniedHandler
                         thường 403
~~~

Nó **không phải** handler chung cho mọi exception Java. Ví dụ `NullPointerException` trong Controller thường đi theo MVC exception handling và/hoặc error dispatch, không đương nhiên biến thành 403.

Mặt khác, nếu một filter **đứng trước ExceptionTranslationFilter** tự chặn request, ExceptionTranslationFilter sẽ không có cơ hội xử lý lỗi đó. Vì vậy khi tìm nguồn status, không chỉ tìm ExceptionTranslationFilter; còn phải nhìn các filter được đặt ở phía trước nó.

## 5. Đọc log startup: bộ lọc nào được cấu hình?

Thêm cấu hình **chỉ ở môi trường dev/test** vào `application.properties`:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Khi Spring Security khởi tạo chain, có thể thấy dạng log:

~~~text
DEBUG ... DefaultSecurityFilterChain :
  Will secure any request with [
    ...,
    SecurityContextHolderFilter,
    HeaderWriterFilter,
    CsrfFilter,
    BasicAuthenticationFilter,
    AnonymousAuthenticationFilter,
    ExceptionTranslationFilter,
    AuthorizationFilter
  ]
~~~

Đây là **log minh họa được rút gọn**, không phải stdout chính xác của project dưới đây. Phiên bản Security, mode và các tính năng được bật có thể tạo danh sách khác.

Bạn đọc được ba điều:

1. **Matcher:** chain đó sẽ bảo vệ các request nào (`any request` hoặc pattern khác).
2. **Danh sách filter:** các filter thực sự nằm trong chain, theo thứ tự.
3. **Điểm chèn custom filter:** tên custom filter nằm trước/sau filter mốc nào.

Nhưng startup log **không tự chứng minh** request cụ thể đã chọn chain đó. Để biết request nào đã chạy filter nào, cần log per-request.

### Cấu hình TRACE theo phạm vi

Trong dev:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Có thể bật tạm log rộng hơn khi cần:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Những mức log này có thể tạo rất nhiều dòng, làm lộ metadata request và tăng chi phí vận hành. **Không bật TRACE diện rộng thường trực trên production**, không ghi `Authorization`, `Cookie`, raw password, OTP, refresh token, JWT hoặc toàn bộ `Authentication`. Dùng bộ lọc dữ liệu nhạy cảm và giới hạn quyền truy cập log.

### Một trace per-request trông ra sao?

~~~text
DEBUG ... FilterChainProxy : Securing GET /me
TRACE ... FilterChainProxy : Invoking DisableEncodeUrlFilter (1/...)
TRACE ... FilterChainProxy : Invoking WebAsyncManagerIntegrationFilter (2/...)
TRACE ... FilterChainProxy : Invoking SecurityContextHolderFilter (3/...)
TRACE ... FilterChainProxy : Invoking HeaderWriterFilter (4/...)
TRACE ... FilterChainProxy : Invoking CsrfFilter (5/...)
...
TRACE ... FilterChainProxy : Invoking BasicAuthenticationFilter (.../...)
...
TRACE ... FilterChainProxy : Invoking AuthorizationFilter (.../...)
DEBUG ... FilterChainProxy : Secured GET /me
~~~

Đây là **bản viết tắt có dấu ...**, không dùng để so khớp nguyên văn trong test. Số thứ tự, filter names và log format không phải hợp đồng API ổn định. Trọng tâm là **trình tự filter được gọi**.

Từ dòng `Invoking XFilter` ta biết `FilterChainProxy` **chuẩn bị gọi filter X**, không có nghĩa filter X đã cho phép request đi tiếp. Nếu trace dừng ở X, có thể X đã trả response, ném exception hoặc có một nhánh xử lý đặc biệt. Đọc thêm log của chính filter/entry point/handler và response status để kết luận.

## 6. Bốn tình huống điển hình: tìm đúng chỗ dừng

### 6.1. Thành công: Basic hợp lệ, được phép

~~~text
Securing GET /me
  -> SecurityContextHolderFilter
  -> HeaderWriterFilter / CsrfFilter ...
  -> BasicAuthenticationFilter
       xác thực user=mai thành công
  -> AnonymousAuthenticationFilter
       không thay Authentication đã có
  -> ExceptionTranslationFilter
  -> AuthorizationFilter
       rule authenticated() được thỏa
  -> DispatcherServlet
  -> DemoController.me()
  <- Response HTTP 200
~~~

Không phải filter nào cũng in “SUCCESS” riêng. Một lời gọi Controller thành công cùng SecurityContext hợp lệ là dấu hiệu request đã vượt qua các bước trước, nhưng vẫn cần kiểm thử **authorization theo tài nguyên** nếu service đọc dữ liệu riêng tư.

### 6.2. Sai password: chặn ở authentication

~~~text
Securing GET /me
  -> các filter đầu chain
  -> BasicAuthenticationFilter
       AuthenticationManager/Provider từ chối credentials
       AuthenticationEntryPoint xử lý
  <- HTTP 401
  (không chạy AuthorizationFilter hoặc Controller trong flow này)
~~~

Tùy cơ chế, filter/entry point có thể khác; đừng ép mọi login thất bại đều phải có exception class `BadCredentialsException` trong log công khai. Trong hệ thống thật, lỗi kho user không hoạt động và password sai cần được phân loại nội bộ, nhưng response bên ngoài tránh dò tài khoản.

### 6.3. Đúng password nhưng thiếu quyền: chặn ở authorization

~~~text
Securing GET /admin
  -> BasicAuthenticationFilter
       user=mai xác thực thành công
  -> AuthorizationFilter
       đòi ROLE_ADMIN; mai chỉ có ROLE_USER
       throw AccessDeniedException
  <- ExceptionTranslationFilter/AccessDeniedHandler
  <- HTTP 403
  (Controller /admin không chạy)
~~~

Nếu code trong `AuthorizationFilter` ném exception, những filter **ở sâu hơn** không được chạy, còn `finally` của filter đang bao quanh đoạn downstream có thể vẫn thực thi trước khi handler đổi response status.

### 6.4. Thiếu CSRF: bị từ chối trước bước authorization

~~~text
Securing POST /notes
  -> SecurityContextHolderFilter
  -> HeaderWriterFilter
  -> CsrfFilter
       missing or invalid CSRF token
       AccessDeniedHandler -> 403
  <- HTTP 403
  (không nhất thiết chạy BasicAuthenticationFilter,
   AnonymousAuthenticationFilter, AuthorizationFilter hay Controller)
~~~

Nếu bạn chỉ đặt custom filter **ngay trước AuthorizationFilter**, bạn sẽ **không thấy custom log** ở tình huống này. Đó là hệ quả vị trí chèn filter, không phải request không vào Spring Security.

## 7. Project chạy được: đánh dấu request tại ba điểm quan trọng

Chúng ta sẽ tạo một dự án Servlet Spring MVC có ba dấu vết chính:

1. **ENTRY:** một custom `OncePerRequestFilter` được gắn **trước `SecurityContextHolderFilter`** trong security chain. Nó là checkpoint đầu của **phần chain mà ta muốn quan sát**, không khẳng định đây là filter đầu tiên của toàn Servlet container; một số filter chuẩn có thể đứng trước nó.
2. **BEFORE_AUTHORIZATION:** một custom filter khác được gắn **trước `AuthorizationFilter`**, sau các bước authentication thông thường. Nó ghi tên chủ thể đang được nhận diện (chỉ trong request attribute của môi trường học).
3. **CONTROLLER:** Controller ghi dấu khi method thực sự được gọi.

Mỗi filter còn có một dấu `finally` khi downstream trả quyền điều khiển. Với request thành công, thứ tự dự kiến:

~~~text
01 security-entry
02 before-authorization:mai
03 controller
04 after-authorization
05 security-exit
~~~

Với request bị chặn **trước authorization**, không có dấu 02/03/04; vẫn có thể thấy dấu 01/05. Với request bị từ chối **bởi AuthorizationFilter**, có dấu 02 và 04, nhưng không có dấu 03.

**Cảnh báo quan trọng:** hai custom filters dưới đây chỉ viết vào **attribute của HttpServletRequest**, được test đọc lại. Chúng không đưa traces ra header/body HTTP và không log passwords. Đây là minh họa an toàn hơn cho việc quan sát vị trí. Nó không thay thế distributed tracing/observability thực tế.

### 7.1. Cấu trúc

~~~text
servlet-filter-trace-lab/
  pom.xml
  src/main/java/com/example/trace/
    FilterTraceApplication.java
    SecurityConfiguration.java
    TraceSupport.java
    DemoController.java
  src/test/java/com/example/trace/
    FilterTraceIntegrationTest.java
~~~

Các API được dùng: Java 17, Spring Boot **4.1.2**, Spring Security do Boot BOM quản lý, `OncePerRequestFilter`, `SecurityContextHolderFilter`, `AuthorizationFilter`, `Authentication` và MockMvc.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-filter-trace-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot parent quản lý dependency versions cho Security, Spring MVC và test. Không cần thêm các version `spring-security-web`/`spring-security-test` bằng tay. Trong Spring Boot 4, starter MVC có tên `spring-boot-starter-webmvc`; tránh copy dependency `spring-boot-starter-web` từ bài hướng dẫn Boot 3 mà không kiểm tra khác biệt.

### 7.3. Main class

Tạo `src/main/java/com/example/trace/FilterTraceApplication.java`:

~~~java
package com.example.trace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterTraceApplication.class, args);
    }
}
~~~

### 7.4. TraceSupport.java: giữ dấu trên HttpServletRequest

Tạo `src/main/java/com/example/trace/TraceSupport.java`:

~~~java
package com.example.trace;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

// Được gọi bởi Spring Security filters/Controller trong cùng request.
// Không expose trace attribute ra response trong production.
final class TraceEvents {
    static final String ATTRIBUTE =
        TraceEvents.class.getName() + ".EVENTS";

    private TraceEvents() {
    }

    @SuppressWarnings("unchecked")
    static void add(HttpServletRequest request, String step) {
        List<String> steps =
            (List<String>) request.getAttribute(ATTRIBUTE);
        if (steps == null) {
            steps = new ArrayList<>();
            request.setAttribute(ATTRIBUTE, steps);
        }
        steps.add(step);
    }

    @SuppressWarnings("unchecked")
    static List<String> snapshot(HttpServletRequest request) {
        List<String> steps =
            (List<String>) request.getAttribute(ATTRIBUTE);
        return steps == null ? List.of() : List.copyOf(steps);
    }
}

// Không dùng @Component / @Bean cho filter này:
// chỉ thêm bằng HttpSecurity.addFilterBefore để tránh đăng ký 2 lần.
final class EntryTraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        TraceEvents.add(request, "01 security-entry");
        try {
            filterChain.doFilter(request, response);
        } finally {
            TraceEvents.add(request, "05 security-exit");
        }
    }
}

final class BeforeAuthorizationTraceFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        String name = (auth == null) ? "none" : auth.getName();

        TraceEvents.add(
            request, "02 before-authorization:" + name);

        try {
            filterChain.doFilter(request, response);
        } finally {
            TraceEvents.add(request, "04 after-authorization");
        }
    }
}
~~~

Lưu ý: `TraceSupport.java` chứa **ba lớp package-private**, không có lớp `public`. Java cho phép điều đó; tên file không bắt buộc trùng tên các lớp package-private. Cả ba cùng package với Controller và SecurityConfiguration nên được truy cập trực tiếp.

Điểm cần nắm:

- `EntryTraceFilter` được chạy trước `SecurityContextHolderFilter`, vì vậy khi vừa enter **chưa nên kỳ vọng** `SecurityContextHolder` đã có principal của request. Nó chỉ ghi marker.
- `BeforeAuthorizationTraceFilter` được đặt trước `AuthorizationFilter`; với HTTP Basic hợp lệ, Authentication đã được đặt, nên nó có thể đọc `auth.getName()`.
- `TraceEvents` là request attribute **chỉ cho demo đồng bộ**. Không biến `ArrayList` này thành kho trace concurrent/async production; nếu có async cần xử lý thread-safety và lifecycle.
- Mỗi filter sử dụng `try/finally`, giúp quan sát chiều unwind ngay cả khi downstream ném exception.
- `OncePerRequestFilter` có quy tắc riêng với async/error dispatch. “Once” không có nghĩa request chỉ có một dispatch duy nhất trong mọi tình huống; cần kiểm tra `shouldNotFilterAsyncDispatch()`/`shouldNotFilterErrorDispatch()` nếu mở rộng.

### 7.5. SecurityConfiguration.java

Tạo `src/main/java/com/example/trace/SecurityConfiguration.java`:

~~~java
package com.example.trace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .addFilterBefore(
                new EntryTraceFilter(),
                SecurityContextHolderFilter.class
            )
            .addFilterBefore(
                new BeforeAuthorizationTraceFilter(),
                AuthorizationFilter.class
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Chúng ta dùng **một `SecurityFilterChain`** có matcher mặc định khớp mọi request để tránh vấn đề nhiều chain khi học trace. HTTP Basic giúp gửi credentials cho từng request bằng `curl` hoặc MockMvc.

Vì sao đặt hai checkpoint ở hai vị trí khác nhau?

| Filter tự viết | Vị trí | Trông thấy gì? |
| --- | --- | --- |
| `EntryTraceFilter` | Trước `SecurityContextHolderFilter` | Request đã đi vào đoạn security chain chứa marker |
| `BeforeAuthorizationTraceFilter` | Trước `AuthorizationFilter` | Authentication sau bước Basic/anonymous của request, nếu downstream tới được đây |
| `AuthorizationFilter` | Sau checkpoint 02 | Có thể chặn và không cho Controller chạy |
| Controller | Sau các filters | Chỉ được gọi khi request đã vượt qua security filtering và handler được match |

**Không gắn `@Component` lên các filter demo.** Nếu Spring Boot tự đăng ký một bean `Filter` ở Servlet container và bạn cũng `addFilterBefore` cùng object/class vào security chain, nó có thể chạy hai lần hoặc sai vị trí. Hai class riêng biệt cũng giúp framework xác định chính xác thứ tự custom filter theo loại filter, thay vì thêm nhiều instance của một class ở các slot khác nhau.

### 7.6. DemoController.java

Tạo `src/main/java/com/example/trace/DemoController.java`:

~~~java
package com.example.trace;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage(HttpServletRequest request) {
        TraceEvents.add(request, "03 controller");
        return "public";
    }

    @GetMapping("/me")
    public String me(
            HttpServletRequest request,
            Authentication authentication) {
        TraceEvents.add(request, "03 controller");
        return "hello-" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin(
            HttpServletRequest request,
            Authentication authentication) {
        TraceEvents.add(request, "03 controller");
        return "admin-" + authentication.getName();
    }

    @PostMapping("/notes")
    public String createNote(
            HttpServletRequest request,
            Authentication authentication) {
        TraceEvents.add(request, "03 controller");
        return "created:" + authentication.getName();
    }
}
~~~

Các method đơn giản để **không nhầm nghiệp vụ với bảo mật**. Trong ứng dụng thật, service phải kiểm tra thêm quyền trên resource, owner, tenant và transaction; `hasRole("ADMIN")` không tự cho phép đọc mọi dữ liệu.

`POST /notes` dùng để minh họa CSRF, không lưu dữ liệu thật. Mã không disable CSRF; bài test sẽ cố tình gửi một request thiếu token để quan sát nó bị chặn.

### 7.7. MockMvc integration test: kiểm tra thứ tự bằng request attribute

Tạo `src/test/java/com/example/trace/FilterTraceIntegrationTest.java`:

~~~java
package com.example.trace;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterTraceIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulRequestVisitsBothFiltersAndController()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/me").with(httpBasic("mai", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello-mai"))
            .andReturn();

        assertEquals(List.of(
            "01 security-entry",
            "02 before-authorization:mai",
            "03 controller",
            "04 after-authorization",
            "05 security-exit"
        ), TraceEvents.snapshot(result.getRequest()));
    }

    @Test
    void missingCredentialsStopBeforeController()
            throws Exception {
        MvcResult result = mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(events.contains("01 security-entry"));
        assertTrue(events.contains("05 security-exit"));
        assertFalse(events.contains("03 controller"));
    }

    @Test
    void wrongPasswordStopsBeforeController()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/me").with(httpBasic("mai", "incorrect")))
            .andExpect(status().isUnauthorized())
            .andReturn();

        assertFalse(
            TraceEvents.snapshot(result.getRequest())
                .contains("03 controller"));
    }

    @Test
    void missingRoleStopsAtAuthorization()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/admin").with(httpBasic("mai", "demo-password")))
            .andExpect(status().isForbidden())
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(
            events.contains("02 before-authorization:mai"));
        assertTrue(events.contains("04 after-authorization"));
        assertFalse(events.contains("03 controller"));
    }

    @Test
    void missingCsrfTokenStopsBeforeAuthorization()
            throws Exception {
        MvcResult result = mvc.perform(
                post("/notes").with(httpBasic("mai", "demo-password")))
            .andExpect(status().isForbidden())
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(events.contains("01 security-entry"));
        assertFalse(events.contains("03 controller"));
        assertFalse(
            events.stream().anyMatch(s ->
                s.startsWith("02 before-authorization")));
    }

    @Test
    void validCsrfAndPasswordReachController()
            throws Exception {
        MvcResult result = mvc.perform(
                post("/notes")
                    .with(csrf())
                    .with(httpBasic("mai", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("created:mai"))
            .andReturn();

        assertEquals(List.of(
            "01 security-entry",
            "02 before-authorization:mai",
            "03 controller",
            "04 after-authorization",
            "05 security-exit"
        ), TraceEvents.snapshot(result.getRequest()));
    }

    @Test
    void publicEndpointStillRunsSecurityFilters()
            throws Exception {
        MvcResult result = mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(events.contains("01 security-entry"));
        assertTrue(events.contains("03 controller"));
        assertTrue(events.contains("05 security-exit"));
    }

    @Test
    void adminCanReachAdminController()
            throws Exception {
        mvc.perform(
                get("/admin")
                    .with(httpBasic("admin", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-admin"));
    }
}
~~~

Đây là **tám integration tests** đi qua Spring Security và Spring MVC, không phải test controller gọi trực tiếp. Chúng tập trung vào ba câu hỏi:

- Khi **cho phép**, thứ tự marker có khớp chiều vào/ra dự kiến không?
- Khi **bị chặn**, marker Controller có vắng mặt không và checkpoint nào còn xuất hiện?
- Khi `/public` được `permitAll`, request có **vẫn đi qua security filters** không? Có.

Test `missingCsrfTokenStopsBeforeAuthorization` thể hiện một logic đặc biệt quan trọng: request bị `CsrfFilter` chặn **trước** custom checkpoint trước `AuthorizationFilter`, nên không có dòng marker 02 dù đã đi vào Spring Security.

Một vài chi tiết kỹ thuật khi đọc tests:

1. `httpBasic("mai","demo-password")` của Spring Security Test tạo Authorization header cho MockMvc request, không tự đánh dấu Mai đã authenticated; `BasicAuthenticationFilter` vẫn kiểm tra mật khẩu qua provider.
2. `csrf()` cung cấp token CSRF hợp lệ cho test POST; không cần tắt CSRF trong `SecurityFilterChain`.
3. `@SpringBootTest` + `@AutoConfigureMockMvc` lấy filter chain thật của ứng dụng mẫu.
4. Trace lưu trong request attribute, nên test lấy lại bằng `result.getRequest()` để tránh phụ thuộc timestamp/thứ tự thread.
5. Đây là **demo đồng bộ** với một request không async dispatch; nếu thêm `Callable`, `DeferredResult` hoặc `@Async`, cần bổ sung test lifecycle.
6. Khi một filter bao ngoài như `ExceptionTranslationFilter` xử lý lỗi từ `AuthorizationFilter`, marker `04 after-authorization` có thể được ghi trong `finally` **trước** khi filter bao ngoài thực sự ghi status 403. Vì vậy test kiểm tra marker và HTTP status **riêng**, không giả vờ marker 04 biết được status cuối.

### 7.8. Chạy lệnh

Trong thư mục chứa `pom.xml`:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Kết quả có thể quan sát:

- Lệnh `mvn test` sẽ chạy **8 tests**; các test được thiết kế để pass với Spring Boot 4.1.2 và dependency tương thích theo BOM.
- `GET /me` với password demo đúng trả body `hello-mai`.
- Anonymous `GET /me` và password sai thường trả HTTP 401 vì HTTP Basic.
- `GET /admin` với Mai trả 403; với Admin trả 200 và body `admin-admin`.
- `POST /notes` thiếu token CSRF trả 403; test có `csrf()` và Basic đúng trả 200, body `created:mai`.
- `GET /public` trả 200 nhưng vẫn có markers thuộc security chain.

Đây là **kết quả dự kiến theo code và tài liệu**, chưa phải báo cáo về một lần chạy Maven thực tế trong môi trường của người học. Log trên console có thể có timestamp, thread name, bootstrap warnings và các chi tiết khác tùy máy.

Thử thủ công với **password giả chỉ dùng local**:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/admin
curl -i -u admin:demo-password http://localhost:8080/admin
~~~

Đầu ra/status quan trọng (rút gọn, không giả vờ là transcript HTTP đầy đủ):

~~~text
GET /public                   -> 200 body=public
GET /me without credentials   -> 401
GET /me as mai                -> 200 body=hello-mai
GET /admin as mai             -> 403
GET /admin as admin           -> 200 body=admin-admin
~~~

Không dùng `curl -u` với password thật trên máy dùng chung vì secret có thể lộ qua command history/process inspection. Không gửi HTTP Basic trên Internet mà không có TLS.

**Không thử POST bằng `curl -X POST` rồi kết luận Basic lỗi khi thấy 403.** CSRF là một cơ chế khác: cần cung cấp cookie và token hợp lệ hoặc dùng MockMvc `.with(csrf())` trong test, không tự tắt phòng vệ để minh họa.

## 8. Đọc dấu vết trong ứng dụng thật, nơi không có TraceEvents

Project trên là một cách **đánh dấu checkpoint** để hiểu cơ chế. Trên hệ thống thật, bạn thường có:

- Trace ID hoặc correlation ID do gateway/observability tạo.
- Access log của reverse proxy/load balancer.
- Servlet container access log.
- Spring Security `FilterChainProxy` DEBUG/TRACE.
- Authentication success/failure events.
- Application logger ở Controller/Service.
- Database span/metrics nếu observability instrumentation phù hợp.
- AccessDeniedHandler/AuthenticationEntryPoint logging (đã redact).

Để “theo một request” không trộn với request khác, cần cùng một **correlation ID**, nhưng ID đó phải được phát/kiểm soát bởi phía đáng tin. Nếu client gửi `X-Request-ID`, hãy validate định dạng/độ dài và tránh cho giá trị không tin cậy gây log injection; nhiều hệ dùng ID riêng do gateway tạo hoặc thay thế giá trị không hợp lệ.

Ví dụ **log minh họa đã ẩn dữ liệu nhạy cảm**:

~~~text
19:42:10.101 INFO  [req=9af3] ingress GET /me
19:42:10.102 DEBUG [req=9af3] FilterChainProxy Securing GET /me
19:42:10.105 TRACE [req=9af3] Invoking BasicAuthenticationFilter
19:42:10.121 INFO  [req=9af3] auth outcome=success actorId=101
19:42:10.122 TRACE [req=9af3] Invoking AuthorizationFilter
19:42:10.124 INFO  [req=9af3] controller=me outcome=success
19:42:10.126 INFO  [req=9af3] egress status=200 durationMs=25
~~~

Đây không phải mẫu log mặc định tự có ở Spring Security; các dòng `ingress`, `auth outcome`, `controller`, `egress` là các điểm mà đội vận hành **có thể thiết kế**. Log của framework cũng không tự có cùng `req` field trừ khi cấu hình tracing/MDC hoặc structured logging propagation thích hợp.

### Khi gắn MDC

MDC logger thường dựa trên `ThreadLocal`. Trong request Servlet đồng bộ, một servlet filter ngoài có thể gắn correlation ID vào MDC đầu request và **xóa trong finally** để không rò sang request khác trên pooled thread. Với async dispatch, thread chuyển đổi hoặc reactive pipeline, cần cơ chế propagation phù hợp, không mặc định ThreadLocal tự truyền.

Mảnh code ý tưởng:

~~~java
String requestId = validatedRequestIdOrNewId(request);
org.slf4j.MDC.put("requestId", requestId);
try {
    chain.doFilter(request, response);
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

Đây là **fragment**, các biến và hàm `validatedRequestIdOrNewId` chưa được định nghĩa. Mục đích là giải thích ownership của MDC, không phải bảo đảm logging filter đó đã được đăng ký trước mọi filter của Spring Security.

**Đừng dùng username/email, session ID hay JWT làm trace ID.** Correlation ID phải không tiết lộ thông tin riêng tư và không đóng vai trò credential.

## 9. Gỡ lỗi theo triệu chứng: thấy log nào, thiếu log nào?

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra tiếp |
| --- | --- | --- |
| Không có access log tại app | Request có thể bị proxy/firewall/network chặn trước app | Gateway logs, route, DNS, container listener |
| Access log có request nhưng không có Spring Security log | Không chain match, proxy registration sai, log level chưa đủ | `springSecurityFilterChain`, `securityMatcher`, log config |
| `FilterChainProxy` ghi `Securing...`, rồi firewall reject | Path không phù hợp policy | `StrictHttpFirewall`, encoded slash, semicolon, double slash |
| Log dừng tại `CsrfFilter`, trả 403 | Thiếu hoặc sai CSRF | Cookie/token, HTTP method, origin, response handler |
| Log dừng tại Basic authentication, trả 401 | Password/token sai hoặc provider lỗi | Authentication event/error nội bộ; tránh lộ credentials |
| Có dấu trước authorization nhưng không có Controller, trả 401 | Chưa được xác thực hoặc anonymous bị yêu cầu login | Entry point, chain, `authenticated()` |
| Có dấu trước authorization nhưng không có Controller, trả 403 | Thiếu role/authority hoặc policy | `AuthorizationFilter`, AccessDeniedHandler, authorities |
| Controller breakpoint chạy nhưng response 500 | Lỗi handler/service/serialization hoặc security method exception | Controller logs, stack trace đã lọc, exception handler |
| Controller chạy nhưng response 403 | Có thể method security hoặc service policy ném AccessDeniedException | `@PreAuthorize`, service permission, ExceptionTranslationFilter |
| GET /api trả 302 /login thay vì 401 | Có thể request rơi vào form-login chain | `@Order`, `securityMatcher`, entry point |
| GET /login trả 404 | Endpoint filter-generated nằm ngoài security matcher, hoặc không có handler | chain bảo vệ login URL, formLogin config |
| Request chạy 2 lần custom filter | Filter đăng ký ở container và trong HttpSecurity, hoặc dispatcher | Bean `FilterRegistrationBean`, `addFilterBefore`, dispatcher |
| Chỉ request ban đầu có context; request sau anonymous | Context không được save/session cookie không gửi, hoặc stateless policy | `SecurityContextRepository`, session ID, explicit-save |
| Trace bị trộn giữa hai user | Dùng static/global mutable trace, MDC không clear, thread reuse | Per-request state và context propagation |

**Đừng kết luận từ một dòng log đơn lẻ.** Cần kết hợp request method/path, correlation ID, status cuối, security chain được chọn và dấu vết Controller.

## 10. Điểm chặn khác nhau tạo 401/403/302/404/500

### HTTP 401 Unauthorized

Thường là request **chưa có Authentication hợp lệ** và entry point của Basic/Bearer yêu cầu chứng minh danh tính. Với Basic, có thể có `WWW-Authenticate`. `401` không có nghĩa cứ thấy Controller thì password sai: phần lớn trường hợp nó dừng ở filter.

### HTTP 403 Forbidden

Có thể là:

1. Authenticated user thiếu authority.
2. CSRF token thiếu/sai ở phương thức ghi.
3. CORS/security policy riêng hoặc custom filter.
4. Method security trong service từ chối.
5. AccessDeniedHandler custom trả 403.

**Chỗ dừng khác nhau**. Phải đọc trace xem `CsrfFilter`, `AuthorizationFilter` hay service đã từ chối.

### HTTP 302 Redirect

Với form login, chưa đăng nhập có thể được chuyển hướng đến `/login`. Không được coi mọi 302 là lỗi kinh doanh; nó có thể là security entry point. Một số flow còn redirect sau login, logout hoặc OAuth2. Khi trace nhiều request, redirect có thể tạo **request mới**; correlation ID không nhất thiết giống nhau nếu không có thiết kế nối span/trace.

### HTTP 404 Not Found

Có thể `DispatcherServlet` không tìm thấy handler, hoặc endpoint filter-generated như `/login` không nằm trong chain mà bạn nghĩ. `404` **không chứng minh** Spring Security có/không bảo vệ URL. Một request có thể đã qua tất cả security filters rồi vẫn không có Controller mapping.

### HTTP 500 Internal Server Error

Có thể từ Controller, Service, serializer, Servlet filter hoặc exception handler. Nếu exception phát sinh **trước** `DispatcherServlet`, `@ControllerAdvice` không tự nhiên xử lý mọi exception ấy; cần cơ chế xử lý lỗi ở cấp filter/container. Khi lỗi xảy ra trong MVC handler, `HandlerExceptionResolver` và error dispatch có thể tham gia.

**Chính sách an toàn:** log nội bộ có thông tin đủ để khắc phục, nhưng body trả client tránh stack trace, SQL, private key, token và mô tả chính xác cấu hình bảo mật.

## 11. Dòng “Invoking XFilter” không có nghĩa “đã đi qua XFilter”

Với per-request TRACE:

~~~text
TRACE ... Invoking BasicAuthenticationFilter (8/15)
~~~

Ý nghĩa cốt lõi là `FilterChainProxy` đang **gọi** filter ấy. Có nhiều kết quả khác nhau:

- Filter gọi tiếp `chain.doFilter`: một dòng `Invoking NextFilter` có thể theo sau.
- Filter nhận dạng credential không hợp lệ và trực tiếp gửi 401: không có dòng NextFilter.
- Filter ném exception được xử lý bởi filter bao ngoài: có thể thấy log exception/entry point ở phần unwind.
- Filter chuyển hướng, ví dụ logout/login success: request kết thúc hoặc thành request khác, không tới controller ban đầu.
- Filter quyết định pass-through nhưng Controller sau đó bị MVC interceptor chặn: trace Spring Security có thể đã hoàn tất trước phần lỗi nghiệp vụ.

Bạn cần phân biệt **chuỗi lệnh gọi** với **kết quả thật** của filter. Không chỉ nhìn số `(7/15)` rồi kết luận 7 filters đã cho phép request.

### Startup filter list so với runtime invocation

| Nguồn | Cho biết | Không chứng minh |
| --- | --- | --- |
| `DefaultSecurityFilterChain` DEBUG lúc startup | Những filters được cấu hình trong mỗi chain | Request cụ thể đã đi qua tất cả |
| `FilterChainProxy` TRACE trong request | Những filters được bắt đầu gọi trên request cụ thể | Filter đã gọi downstream hoặc trả thành công |
| Authentication provider logs/events | Kết quả xác minh danh tính | Đã có quyền với tài nguyên |
| Authorization/access denied logs | Lý do truy cập bị từ chối theo policy | Controller chắc chắn đã chạy |
| Controller logs | Handler method đã được gọi | Những tác vụ async/callback phía sau đã hoàn tất |
| Container/proxy access log | Method/path/status cuối tương ứng | Chi tiết logic filter nào gây status |

Dùng **nhiều lớp bằng chứng** khi xử lý sự cố nghiêm trọng, đặc biệt nếu proxy, dispatcher hoặc async có thể sửa đường đi.

## 12. Khi cần biết filter nào đứng trước/sau filter khác

Spring Security chuẩn hóa thứ tự nhiều filter quan trọng. Bạn có thể dùng các API:

~~~java
http.addFilterBefore(customFilter, BasicAuthenticationFilter.class);
http.addFilterAfter(customFilter, BasicAuthenticationFilter.class);
http.addFilterAt(customFilter, BasicAuthenticationFilter.class);
~~~

Đây là các **fragment**, không phải chương trình độc lập; `customFilter` cần đúng kiểu Servlet `Filter` và phải hiểu thứ tự đã được đăng ký. `addFilterAt` không có nghĩa một class khác ở cùng vị trí tự động được loại bỏ hoàn toàn trong mọi tình huống; cần đọc hợp đồng cụ thể và test.

Việc chọn vị trí phụ thuộc dữ liệu cần:

| Muốn làm gì? | Đặt checkpoint ở đâu? | Vì sao |
| --- | --- | --- |
| Biết request đã vào Spring Security sớm | Trước `SecurityContextHolderFilter` hoặc near entry trong chain | Chưa phụ thuộc authentication |
| Cần xem SecurityContext hiện tại | Sau khi context holder được nạp/đã có identity phù hợp | Trước đó identity có thể null |
| Quan sát Basic authentication outcome | Chèn marker trước/sau Basic theo mục đích, kết hợp event/provider logs | Password sai có thể dừng ở Basic |
| Cần role/identity trước authorization | Sau authentication/anonymous, trước `AuthorizationFilter` | Có identity để đánh giá policy |
| Quan sát Controller có chạy | HandlerInterceptor, controller instrumentation hoặc service logs | Security filter không bảo đảm controller đã được gọi |
| Quan sát kết quả cuối của request | Container-level outer filter/access log với async awareness | Filter ở sâu có thể chưa thấy status cuối |

Không tự đăng ký một `@Component Filter` ngoài Servlet container rồi còn `addFilterBefore` nó vào Security chain: có thể **chạy hai lần**. Với filter demo, chúng ta chỉ tạo `new EntryTraceFilter()` và `new BeforeAuthorizationTraceFilter()` khi build `HttpSecurity`, không đăng ký như bean `Filter` độc lập.

## 13. “Bộ lọc đầu tiên” là điểm nào?

Cụm “bộ lọc đầu tiên” có **ít nhất ba cách hiểu**:

1. Filter đầu tiên ở tầng **reverse proxy/gateway**. Nó thậm chí không chạy trong JVM.
2. Filter đầu tiên trong **Servlet container chain**. Có thể là request logging, character encoding hoặc tracing, đứng trước `DelegatingFilterProxy`.
3. Filter đầu tiên trong **SecurityFilterChain đã được chọn**. Danh sách có thể bắt đầu bằng filter nội bộ như `DisableEncodeUrlFilter`, tùy cấu hình/version.

Checkpoint `EntryTraceFilter` trong demo được đặt **trước `SecurityContextHolderFilter`**, không nhất thiết đứng trước mọi Spring Security filter. Vì vậy nó không đo trực tiếp gateway ingress hoặc `HttpFirewall` rejection trước khi chain khởi chạy.

Nếu request bị reject bởi firewall **trước khi chọn chain**, marker `EntryTraceFilter` có thể không có dù HTTP request đã tới container. Muốn quan sát toàn hành trình, kết hợp **container ingress trace** với Spring Security filter TRACE và Controller trace.

### Mảnh cấu hình một container-level filter quan sát từ bên ngoài

Đây là **fragment nâng cao** (không cần cho project demo chạy được):

~~~java
// Fragment: cần implementation IngressFilter do ứng dụng cung cấp.
@Bean
FilterRegistrationBean<IngressFilter> ingressFilter() {
    var registration =
        new FilterRegistrationBean<>(new IngressFilter());
    registration.addUrlPatterns("/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
    return registration;
}
~~~

Container filter này có thể ghi “received GET /me” trước khi tới Spring Security (tùy các filter registration khác), rồi log status khi downstream hoàn tất. Muốn chắc chắn filter nào chạy trước filter nào ở container, phải kiểm tra các registration order và dispatcher types thực tế, không dựa vào `@Order` của các `SecurityFilterChain`.

**Đừng dùng filter outer để log request body/password.** Nếu cần correlation ID, chỉ xử lý các trường metadata được phê duyệt; với response async cần cẩn trọng bởi `chain.doFilter` có thể trả trong khi công việc chưa hoàn tất.

## 14. Khi request không tới Controller, kiểm tra cả MVC routing

Một request có thể vượt qua **toàn bộ Spring Security filters** nhưng vẫn không tới handler mong muốn, vì `DispatcherServlet` còn thực hiện:

1. Xác định `HandlerMapping` nào có mapping.
2. So khớp HTTP method và đường dẫn.
3. Kiểm tra các điều kiện `consumes`, `produces`, params, headers, versioning nếu có.
4. Thực thi `HandlerInterceptor.preHandle`, có thể trả `false`.
5. Resolve arguments và bind/validate input; có thể ném lỗi trước khi gọi method.
6. Gọi Controller method.
7. Chạy conversion/serialization, response handling.
8. Xử lý exception qua resolver/advice và có thể error dispatch.

Vì vậy “trace cho thấy `AuthorizationFilter` đã gọi xong” chưa chắc Controller được chạy. Có thể request không match MVC mapping, body JSON sai định dạng hoặc filter/interceptor khác dừng nó.

### Với ControllerAdvice

`@ControllerAdvice` hoặc `@RestControllerAdvice` là cơ chế xử lý exception trong MVC, **không phải** cách xử lý thay thế cho toàn bộ lỗi trước DispatcherServlet. Một `AuthenticationEntryPoint` hoặc `AccessDeniedHandler` thường xử lý lỗi phát sinh ở Security filter chain, còn advice xử lý các exception thuộc MVC.

Nếu một exception nghiệp vụ phát sinh ở service và được advice xử lý thành 400/500, log Spring Security vẫn có thể ghi filter chain hoàn thành. Đọc stack trace thật và thứ tự dispatch thay vì tự quy mọi lỗi cho Security.

## 15. Request dispatch, async và trace có thể nhiều vòng

Servlet có các dispatcher types như `REQUEST`, `FORWARD`, `ERROR` và `ASYNC`. Một URL có thể sinh thêm dispatch:

~~~text
REQUEST /me
  |
  +--> Security filters
  +--> DispatcherServlet / Controller
           |
           +--> exception
                   |
                   v
                ERROR dispatch /error
                   |
                   +--> bộ lọc/handler chạy theo config
~~~

`OncePerRequestFilter` có cơ chế tránh gọi nhiều lần trong một số dispatch theo contract, và có thể được tùy chỉnh bằng:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;  // demo bỏ qua async dispatch
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;  // demo bỏ qua error dispatch
}
~~~

Đây là **fragment** cho custom `OncePerRequestFilter`. Nhiều giá trị mặc định phù hợp với việc bỏ qua các dispatch trên nhưng vẫn phải kiểm tra phiên bản và container. Đừng suy luận số dòng trace luôn bằng số HTTP requests khi một request có async/error dispatch.

Với long-running async request, Filter “after” trong request đầu có thể chạy trước khi kết quả async cuối được gửi. Dùng event `AsyncListener`, interceptor async/observability phù hợp nếu cần đo **thời gian thực sự đến khi hoàn tất response**.

### SecurityContext qua async

Spring Security có cơ chế tích hợp async của Servlet/MVC để hỗ trợ mang context trong các tình huống nhất định. Nhưng không mặc định rằng tự tạo `new Thread` hoặc `ExecutorService` sẽ có `SecurityContextHolder` tương ứng; có thể cần `DelegatingSecurityContextExecutor` hoặc truyền `CurrentActor` theo chính sách. Nếu thiếu ngữ cảnh hoặc leak context, log theo thread ID không đủ để phân biệt các users.

## 16. Những lỗi đo lường trace thường gặp

1. **“Không thấy Controller log tức request không đến backend.”** Sai; filter/proxy có thể chặn.
2. **“Có FilterChainProxy log nghĩa tất cả filters đã chạy hết.”** Không; filter có thể short-circuit.
3. **“Invoking CsrfFilter nghĩa CSRF đã pass.”** Không; đó là lúc gọi filter, không phải kết quả.
4. **“401 nghĩa thiếu ROLE_ADMIN.”** Thường là chưa xác thực; thiếu role của user đã xác thực thường 403.
5. **“403 luôn do AuthorizationFilter.”** Có thể do CSRF hoặc filter tùy biến.
6. **“Mật khẩu đúng mà POST 403 thì DaoAuthenticationProvider sai.”** Có thể CSRF chặn trước cả Basic filter.
7. **“ExceptionTranslationFilter bắt mọi exception của ứng dụng.”** Không; chủ yếu dịch các exception security tương ứng.
8. **“`SecurityContextHolderFilter` luôn xác minh mật khẩu.”** Không; nó nạp context.
9. **“Thấy anonymousUser nghĩa request đã login thành công.”** Không; đó thường là anonymous authentication fallback.
10. **“permitAll nghĩa request không có security filters.”** Không; vẫn đi qua chain.
11. **“Một request có thể chạy nhiều SecurityFilterChain cộng dồn.”** Không; chọn chain khớp đầu tiên.
12. **“Không có fallback chain nghĩa URL mặc nhiên bị chặn.”** Không; có thể bypass Spring Security.
13. **“Status đọc bên trong filter sâu luôn là status cuối.”** Không; filter ngoài có thể đổi status sau.
14. **“Dòng after thiếu chắc chắn filter không chạy.”** Có thể filter không có log finally, async hoặc exception bất thường.
15. **“Chỉ một HTTP request luôn chỉ một Servlet dispatch.”** Không; ERROR/FORWARD/ASYNC có thể phát sinh.
16. **“OncePerRequestFilter bảo đảm đúng một lần trong mọi dispatch.”** Không nên suy như vậy; cần hiểu skip/dispatch options.
17. **“ControllerAdvice sẽ bắt hết AuthenticationException ở các filters.”** Không; MVC advice không thay Security entry point.
18. **“Trace ID dùng JWT hoặc session cookie sẽ tiện hơn.”** Không; đưa secrets vào logs là rủi ro nghiêm trọng.
19. **“TRACE bật vĩnh viễn production càng tốt.”** Không; chi phí lớn và nguy cơ lộ metadata nhạy cảm.
20. **“In full Authentication vào log là an toàn vì Spring đã xóa credentials.”** Custom principal/details có thể chứa dữ liệu nhạy cảm.
21. **“Có 200 là chắc request được phân quyền đúng.”** Không; có thể chain không match hoặc policy thiếu.
22. **“Bật DEBUG ở Spring MVC tự hiện tất cả security filter invocations.”** Không; cần logger tương ứng của Spring Security.
23. **“`@Order` trên filter và `@Order` trên SecurityFilterChain tương đương.”** Không; một bên container/filter order, một bên chain selection.
24. **“Tự viết custom Filter @Component và addFilterBefore không thể chạy trùng.”** Có thể double registration.
25. **“TRACE log có thể được dùng để khôi phục password khi người dùng quên.”** Không; không bao giờ log credentials.
26. **“Browser redirect /login là cùng một request đang tiếp tục.”** Redirect tạo HTTP request mới.
27. **“Bộ lọc chưa gọi downstream nên phải xảy ra lỗi 500.”** Không; filter có thể hoàn tất một response hợp lệ.
28. **“Spring Security biết role từ URL mà không cần Authentication.”** Authorization cần identity hoặc policy đặc thù; không nhận role tự khai từ client.
29. **“Thread ID đủ để nối log request trong pool thread.”** Không; thread được tái sử dụng, cần correlation ID/span.
30. **“Test dùng @WithMockUser chứng minh Basic password được xác minh thật.”** Không; đó là fixture authentication được dựng sẵn.
31. **“Test 200 cho /public chứng minh filter chain chắc chắn chạy.”** Không; cần trace/filter assertion hoặc test các endpoint được bảo vệ.
32. **“Chỉ nhìn tên custom marker trước AuthorizationFilter là biết mọi filter nào ở trước nó đã thành công.”** Nó chứng minh luồng đã tới checkpoint, không cho biết từng chính sách được kiểm tra ra sao.

## 17. Ma trận kiểm thử khi một endpoint đột nhiên lỗi

| Request | Chặng cần tới | Kỳ vọng | Kiểm tra dấu vết |
| --- | --- | --- | --- |
| Anonymous `GET /public` | Security chain + Controller | 200 | Có marker entry, authz, controller, unwind |
| `GET /me` Basic đúng | Auth + Authorization + Controller | 200 | Đúng `Authentication.getName()`, marker đủ 5 |
| `GET /me` không credentials | Authorization → entry point | 401 | Không có marker Controller |
| `GET /me` password sai | Basic filter | 401 | Không có Controller, có auth failure |
| `GET /admin` Mai thiếu role | AuthorizationFilter | 403 | Có marker trước authz, không có Controller |
| `GET /admin` Admin đủ role | Controller | 200 | Có Controller, đúng body |
| `POST /notes` thiếu CSRF | CsrfFilter | 403 | Không tới marker trước authorization |
| `POST /notes` có CSRF + Basic đúng | Controller | 200 | Có đầy đủ 5 marker |
| `GET /unknown` | Security chain, sau đó MVC routing | Tùy auth; nếu authenticated thường 404 | Có thể qua Security rồi không có handler |
| Login form chưa auth | AuthenticationEntryPoint form | 302 | Redirect tới login URL trong chain đúng |
| URL encoded bất thường | HttpFirewall | Có thể 400/reject | Có thể chưa tới custom security marker |
| `/api/**` thiếu fallback | Không chain match | Nguy cơ bypass | Không có filter trace, nhưng Controller có thể chạy |
| Exception trong service | Controller/Service | 5xx/handler-specific | Controller marker có, xem stack trace đã lọc |
| ERROR dispatch | Servlet ERROR path | Tùy policy | Có thể thêm vòng filter/log |
| Async processing | Chuyển thread/dispatch | Tùy kết quả | Correlation ID chứ không chỉ thread name |

**Cần test đường đi âm tính**: một request bị chặn đúng chỗ là kết quả bảo mật hợp lệ. Chỉ test các tình huống thành công dễ che lấp lỗ hổng fallback matcher hoặc role check chưa chạy.

### Khi đánh giá bug report

Một mẫu ghi nhận hữu ích, **không chứa credential**:

~~~text
Request ID: req-2026-0012
Method/path: POST /notes
Expected: 200
Actual: 403
Chain matched: catch-all servlet security chain
Last observed filter: CsrfFilter
Security decision: invalid/missing CSRF token
Controller invoked: no
Sensitive data in report: none
Root cause hypothesis: frontend không gửi token CSRF hợp lệ
Fix/verification: gửi token qua flow chuẩn; MockMvc.with(csrf())
~~~

Đây là ví dụ dữ liệu giả để huấn luyện đọc trace, không phải log sự cố thật. “Last observed filter” phải đến từ evidence của ứng dụng đang chạy, không điền theo suy đoán.

## 18. Chương trình Java 17 thuần: học stack trước/sau với stdout chính xác

Để hiểu cơ chế `chain.doFilter` mà không cần chạy Spring Boot, ta có thể mô phỏng một danh sách filter dùng `Runnable`. Chương trình **không thay thế Spring Security**, chỉ dạy flow gọi lồng nhau và short-circuit.

Tạo file `FilterWalkthrough.java`:

~~~java
import java.util.List;

public class FilterWalkthrough {

    @FunctionalInterface
    interface Filter {
        void apply(Runnable next);
    }

    static Filter trace(String name) {
        return next -> {
            System.out.println("> " + name);
            try {
                next.run();
            } finally {
                System.out.println("< " + name);
            }
        };
    }

    static Filter reject(String name) {
        return next -> {
            System.out.println("> " + name);
            System.out.println("RESPONSE 403");
            // Không gọi next.run(), nên các bước sau bị bỏ qua.
        };
    }

    static Runnable compose(
            List<Filter> orderedFilters,
            Runnable controller) {
        Runnable current = controller;

        for (int i = orderedFilters.size() - 1; i >= 0; i--) {
            Filter filter = orderedFilters.get(i);
            Runnable downstream = current;
            current = () -> filter.apply(downstream);
        }
        return current;
    }

    public static void main(String[] args) {
        System.out.println("=== ALLOWED ===");
        compose(
            List.of(
                trace("Entry"),
                trace("SecurityContext"),
                trace("Authentication"),
                trace("Authorization")
            ),
            () -> System.out.println("CONTROLLER")
        ).run();

        System.out.println("=== DENIED ===");
        compose(
            List.of(
                trace("Entry"),
                trace("SecurityContext"),
                trace("Authentication"),
                reject("Authorization")
            ),
            () -> System.out.println("CONTROLLER")
        ).run();
    }
}
~~~

Biên dịch và chạy bằng Java 17:

~~~bash
javac FilterWalkthrough.java
java FilterWalkthrough
~~~

Stdout **chính xác theo logic đoạn code Java thuần**:

~~~text
=== ALLOWED ===
> Entry
> SecurityContext
> Authentication
> Authorization
CONTROLLER
< Authorization
< Authentication
< SecurityContext
< Entry
=== DENIED ===
> Entry
> SecurityContext
> Authentication
> Authorization
RESPONSE 403
< Authentication
< SecurityContext
< Entry
~~~

Học từ stdout:

1. Khi mọi filter gọi downstream, Controller chạy trước khi những dòng `< ...` xuất hiện.
2. Khi filter `reject("Authorization")` không gọi `next.run()`, Controller không chạy; cũng không có dòng `< Authorization` vì filter reject không có `finally`.
3. Các filter phía trước vẫn trở lại qua call stack và in dòng `< Authentication`, `< SecurityContext`, `< Entry`.
4. Chương trình không mô phỏng JWT/CSRF/Spring MVC chính xác, không có `FilterChainProxy` thật, không có HttpServletRequest/Response thật. Nó chỉ cho thấy quy tắc **đi vào — short-circuit — tháo ngược**.

## 19. Bài tập áp dụng

**Bài 1 — kiểm tra điểm dừng của CSRF:** Bật Spring Security TRACE trong project demo; chạy test `missingCsrfTokenStopsBeforeAuthorization`. Xác nhận `CsrfFilter` xuất hiện, custom marker trước authorization không có và Controller không được gọi. Đối chiếu 403 với tình huống thiếu role.

**Bài 2 — đổi thứ tự markers:** Thay điểm đặt `EntryTraceFilter` bằng `addFilterAfter(..., BasicAuthenticationFilter.class)` trong một nhánh test riêng. Nhận xét vì sao khi password sai marker ấy có thể biến mất, dù request đã vào security chain.

**Bài 3 — thêm form login:** Thêm `.formLogin(Customizer.withDefaults())` và xác minh `GET /me` khi anonymous có redirect theo entry point phù hợp với cấu hình. Nếu giữ cả Basic và form login, phải hiểu `RequestMatcher` chọn entry point; không suy mọi unauthenticated GET đều có một response như nhau.

**Bài 4 — đặt custom filter ở container:** Dùng `FilterRegistrationBean` tạo trace ngoài Spring Security rồi so sánh nó với checkpoint EntryTraceFilter. Với request bị firewall reject, filter container có thể ghi log trong khi security checkpoint không chạy.

**Bài 5 — nhiều SecurityFilterChain:** Tách `/api/**` và fallback web, gắn hai checkpoint cho từng chain. Kiểm tra `GET /api/private` và `GET /web/private` đi qua các filters đúng chain, không trộn hai danh sách.

**Bài 6 — chẩn đoán 404:** Thử một URL không có Controller mapping trong khi người dùng đã authenticated. Xác minh trace security đã chạy nhưng DispatcherServlet không tìm thấy handler. So sánh với URL `/login` khi endpoint do filter xử lý.

**Bài 7 — exception ở service:** Cho một service ném `AccessDeniedException` hoặc một exception nghiệp vụ, rồi đọc response/log. Phân biệt đường xử lý của `ExceptionTranslationFilter` và MVC exception handling.

**Bài 8 — request IDs:** Tạo một correlation ID cho mỗi request, đưa vào MDC trong một servlet filter tin cậy và dọn trong finally. Kiểm tra hai request chạy trên cùng thread không dùng nhầm ID cũ; không log token/cookies.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Request đi từ Servlet container đến Spring Security qua hai thành phần nào?

*Trả lời:* Container gọi `DelegatingFilterProxy`, proxy delegate tới bean `FilterChainProxy`, rồi proxy chọn `SecurityFilterChain` phù hợp.

**Câu 2.** `FilterChainProxy` chạy tất cả SecurityFilterChain khớp URL không?

*Trả lời:* Không. Nó lấy chain khớp đầu tiên theo thứ tự cấu hình; các chain sau không được cộng dồn.

**Câu 3.** Một filter có `doFilter` nhưng không gọi `chain.doFilter` thì Controller có chạy không?

*Trả lời:* Không, trừ khi có một đường gọi khác riêng. Trong Servlet FilterChain đang xét, downstream sẽ không được tiếp tục.

**Câu 4.** Vì sao các log “after” có thứ tự ngược với “before”?

*Trả lời:* Vì `chain.doFilter` là lời gọi lồng nhau; khi downstream trả về, call stack được tháo ngược.

**Câu 5.** `DEBUG DefaultSecurityFilterChain` lúc startup có chứng minh `BasicAuthenticationFilter` đã chạy cho request hiện tại không?

*Trả lời:* Không; nó chỉ cho biết filter nằm trong cấu hình chain. Phải xem per-request trace/matcher.

**Câu 6.** Log `Invoking CsrfFilter` có nghĩa CSRF token hợp lệ chưa?

*Trả lời:* Chưa. Nó chỉ cho biết filter được gọi; hãy xem log/result tiếp theo.

**Câu 7.** Password đúng nhưng `POST /notes` trả 403 trước Controller, nên xem filter nào?

*Trả lời:* Đặc biệt kiểm tra `CsrfFilter`, CSRF token và HTTP method; 403 không chỉ do role.

**Câu 8.** Khi user đã xác thực nhưng thiếu `ROLE_ADMIN`, ai thường quyết định truy cập và ai dịch exception?

*Trả lời:* `AuthorizationFilter` quyết định theo rule; `ExceptionTranslationFilter` có thể xử lý `AccessDeniedException` qua `AccessDeniedHandler`, thường 403.

**Câu 9.** `SecurityContextHolderFilter` có tự kiểm tra password không?

*Trả lời:* Không. Nó giúp cung cấp context; authentication provider/filter phụ trách xác minh bằng chứng.

**Câu 10.** Một Controller không được gọi nhưng URL vẫn trả 200 có thể xảy ra không?

*Trả lời:* Có. Một filter có thể tự hoàn tất response hoặc một endpoint như login/logout có thể do security filter xử lý.

**Câu 11.** `permitAll` và không match SecurityFilterChain khác nhau ở đâu?

*Trả lời:* `permitAll` vẫn đi qua security filters của chain; không có chain match có thể bỏ qua toàn bộ lớp bảo vệ ấy.

**Câu 12.** Vì sao không nên in Authorization header khi bật debug?

*Trả lời:* Basic chứa thông tin username:password được encode base64 chứ không mã hóa an toàn; Bearer chứa token có thể bị dùng lại.

**Câu 13.** Dấu “04 after-authorization” xuất hiện trong log có chứng minh final status là 200 không?

*Trả lời:* Không. Filter bao ngoài có thể bắt exception sau điểm này và trả 401/403.

**Câu 14.** Tại sao một request có thể có nhiều đoạn log filter dù chỉ có một request của client?

*Trả lời:* Servlet có thể thực hiện `FORWARD`, `ERROR`, `ASYNC` dispatch; còn login redirects có thể tạo request mới riêng.

**Câu 15.** Test `@WithMockUser` có chứng minh `BasicAuthenticationFilter` đã xác minh raw password không?

*Trả lời:* Không. Nó có thể dựng sẵn Authentication test; muốn kiểm tra password cần đưa Basic header hoặc dùng authentication flow thật.

**Câu 16.** Khi một endpoint 404, làm sao phân biệt Security và MVC?

*Trả lời:* Kiểm tra security chain đã được chọn/hoàn thành chưa, controller mapping có hay không, endpoint có do filter sinh ra hay không, và response/error dispatch.

## 21. Checklist điều tra một request từ đầu đến cuối

- [ ] Có request method, path, timestamp và correlation ID không mang credential.
- [ ] Có trace ở gateway/proxy và container để biết request đã tới ứng dụng chưa.
- [ ] Xác minh `springSecurityFilterChain` đã được đăng ký đúng một lần.
- [ ] Xác minh đúng `SecurityFilterChain` đã match, không rơi vào fallback ngoài ý muốn hoặc không chain.
- [ ] Xem danh sách security filters khi startup và trace per-request khi cần.
- [ ] Đọc đúng sự khác nhau giữa `Invoking XFilter` và “XFilter đã cho phép request đi tiếp”.
- [ ] Kiểm tra `HttpFirewall` với path/encoding bất thường trước khi kết luận lỗi controller.
- [ ] Kiểm tra `SecurityContextHolderFilter`/repository và Authentication có mặt đúng lúc.
- [ ] Khi 401, kiểm tra cơ chế authentication, entry point, credentials và lỗi provider an toàn.
- [ ] Khi 403, phân biệt CSRF, authorization, custom policy và method security.
- [ ] Khi 302, xác minh redirect, request cache, form/OAuth2 entry point và request mới.
- [ ] Khi 404, kiểm tra Servlet mapping, MVC HandlerMapping và filter-generated endpoints.
- [ ] Khi 500, phân biệt lỗi filter, controller/service, serializer và error dispatch.
- [ ] Không xem `permitAll` là bỏ qua security filters; không xem status 200 là bằng chứng đủ.
- [ ] Dùng `try/finally` khi gắn tracing filter để nhìn chiều unwind, nhưng không suy status cuối từ filter sâu.
- [ ] Nếu có custom filter, tránh double registration giữa Servlet container và `HttpSecurity`.
- [ ] Kiểm tra dispatcher types, async completion và request/session correlation khi thấy log lặp.
- [ ] Không dùng ThreadLocal/MDC mà quên cleanup hoặc propagation khi chuyển thread.
- [ ] Không log Authorization/Cookie/password/JWT/OTP/full Authentication/request body nhạy cảm.
- [ ] Bổ sung integration tests với request hợp lệ, thiếu credentials, sai password, thiếu role, thiếu CSRF và Controller được/không được gọi.
- [ ] Chỉ bật TRACE trong môi trường kiểm soát/thời gian ngắn và có quy trình giảm level sau điều tra.
- [ ] Giữ bảo vệ owner/tenant/resource-level trong service, không chỉ URL role.
- [ ] Sau khi sửa, test lại các negative paths và các chain khác để tránh vô tình tạo lỗ hổng mới.

### Tổng kết

Để đọc dấu vết một HTTP request trong Spring Security Servlet, hãy theo ba bước: **(1) xác định request đã vào container và `FilterChainProxy` chưa, (2) xác định chain và filter cuối thật sự được gọi, (3) xác định Controller/Service có được thực thi và response được hoàn tất ở lớp nào**.

Cơ chế `chain.doFilter` tạo hai chiều **đi vào** và **tháo ngược**; một filter có thể trả response ngay và chặn tất cả downstream. `FilterChainProxy` chỉ chọn chain khớp đầu tiên; trong chain ấy, CSRF có thể chặn trước authentication, authentication có thể dừng trước authorization, và authorization có thể ngăn Controller. Vì thế **thiếu một dấu vết không phải bằng chứng “request chưa đến backend”**: nó có thể là bằng chứng request bị chặn đúng tại một tầng bảo mật.

Tư duy debug hữu ích nhất không phải “Controller có lỗi gì?”, mà là **“request đi được đến checkpoint nào, filter nào quyết định không gọi bước tiếp, và bộ xử lý nào ghi status cuối?”**.

### Tài liệu chính thức

- [Spring Security — Servlet Architecture and Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — FilterChainProxy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security — SecurityFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html)
- [Spring Security — Java Configuration and Multiple Chains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — SecurityContext Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Spring MVC MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Framework — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
