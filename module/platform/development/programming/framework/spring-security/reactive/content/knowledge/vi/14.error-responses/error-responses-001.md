# Phân biệt lỗi xác thực, lỗi phân quyền và lỗi nghiệp vụ

## 1. Vì sao phải phân biệt đúng loại lỗi?

Một ứng dụng Spring Security Reactive trên WebFlux không chỉ trả dữ liệu thành công mà còn phải giải thích chính xác **vì sao request không được xử lý**. Ba tình huống dễ bị nhập nhằng:

1. **Lỗi xác thực (authentication failure):** server chưa xác minh được danh tính người gọi, ví dụ thiếu access token, mật khẩu sai, token hết hạn.
2. **Lỗi phân quyền (authorization failure):** danh tính đã được xác minh nhưng không được phép truy cập tài nguyên hoặc thao tác.
3. **Lỗi nghiệp vụ (business/domain error):** request đã đi qua những bước bảo mật cần thiết, nhưng dữ liệu hoặc trạng thái nghiệp vụ không thỏa điều kiện; ví dụ hết hàng, đơn hàng không thể hủy, mã giảm giá không hợp lệ.

Ba loại lỗi này không nên bị trả về giống hệt nhau. Nếu mọi lỗi đều thành HTTP 401, client sẽ liên tục yêu cầu đăng nhập khi lỗi thực sự là hết hàng. Nếu mọi lỗi đều thành HTTP 500, hệ thống theo dõi vận hành sẽ nghĩ có sự cố server dù đây là quy tắc nghiệp vụ dự kiến. Nếu “không đủ quyền” trả 200 và một body ghi “failed”, nhiều client/cache/monitoring có thể hiểu sai.

### Sau bài học, bạn có thể

- Nêu rõ ý nghĩa HTTP **401**, **403**, **400**, **404**, **409**, **422**, **429** và **5xx** trong ngữ cảnh WebFlux.
- Phân biệt `AuthenticationException`, `AccessDeniedException` và exception tự định nghĩa trong domain.
- Chỉ ra lỗi nào được xử lý trong **Spring Security WebFilter chain**, lỗi nào đến từ controller/service hoặc WebFlux error infrastructure.
- Cấu hình `ServerAuthenticationEntryPoint` và `ServerAccessDeniedHandler` hợp lý mà không làm mất HTTP Basic challenge.
- Trả lỗi nghiệp vụ bằng `ProblemDetail` (RFC 9457) và `@RestControllerAdvice`.
- Chạy ví dụ Java 17+, Spring Boot WebFlux và `WebTestClient`, thử độc lập các ca 401/403/400/404/409/422.
- Thiết kế error contract tránh lộ dữ liệu nhạy cảm, không nuốt lỗi, không lẫn lỗi validation với quyền truy cập và không làm hỏng reactive pipeline.

Đây là bài thuộc nhóm **Phản hồi lỗi** của module Spring Security Reactive. Các ví dụ dùng HTTP Basic để dễ kiểm chứng; với OAuth2 Resource Server/JWT, nguyên tắc phân loại lỗi vẫn giữ nguyên nhưng challenge, body và cơ chế xác thực thay đổi theo cấu hình thực tế.

## 2. Ba câu hỏi ở ba tầng

Hãy hình dung request `GET /api/orders/42` đi qua ba tầng quyết định:

~~~text
HTTP request
      |
      v
(1) AUTHENTICATION
    "Bạn là ai? Credentials có hợp lệ?"
      |
      +-- Thiếu/sai credentials --> lỗi xác thực
      |                           thường 401
      |
      v
(2) AUTHORIZATION
    "Danh tính đó có quyền gọi route / xem đơn hàng này?"
      |
      +-- Không có quyền -------> lỗi phân quyền
      |                           thường 403;
      |                           có thể 404 để tránh lộ sự tồn tại
      |
      v
(3) BUSINESS / DOMAIN
    "Dữ liệu và trạng thái có cho phép thực hiện nghiệp vụ?"
      |
      +-- Input hỏng -----------> 400 hoặc 422 tùy hợp đồng
      +-- Object không tồn tại -> 404
      +-- Xung đột trạng thái --> 409
      +-- Quy tắc khác --------> 4xx phù hợp
      |
      v
Success: 2xx
~~~

Sơ đồ là khái niệm, **không phải thứ tự tuyệt đối mọi WebFilter**. Ví dụ CSRF filter có thể từ chối POST với **403** trước khi controller hoặc authorization xử lý; lỗi cú pháp HTTP có thể được WebFlux/HTTP server phát hiện từ sớm. Không được suy luận “mọi 403 là thiếu role” hoặc “mọi 400 đều do nghiệp vụ”.

Ba câu hỏi có thể độc lập:
- “Mật khẩu sai” xảy ra trước khi có authenticated principal đáng tin.
- “Mật khẩu đúng nhưng thiếu role ADMIN” không phải lỗi mật khẩu.
- “Người dùng đủ quyền nhưng kho hết hàng” không phải lỗi bảo mật.

## 3. Bảng so sánh nhanh

| Tiêu chí | Xác thực | Phân quyền | Nghiệp vụ |
| --- | --- | --- | --- |
| Câu hỏi | Danh tính đã được chứng minh chưa? | Người gọi có được làm việc này không? | Điều kiện dữ liệu/trạng thái có cho phép thao tác không? |
| Ví dụ | Token thiếu/hết hạn/chữ ký sai, username/password sai | User thường gọi API admin; đọc object không thuộc tenant | Số lượng vượt tồn kho; đơn hàng đã giao không thể hủy |
| Exception thường gặp | `AuthenticationException`, `BadCredentialsException` và các biến thể | `AccessDeniedException`, lỗi authorization manager | `DomainException` hoặc exception riêng của ứng dụng |
| Điểm xử lý điển hình | Authentication filter/entry point/failure handler | Authorization filter, `ServerAccessDeniedHandler` | Service/controller, `@ExceptionHandler` hoặc WebFlux error handler |
| HTTP phổ biến | **401** | **403** | **400/404/409/422** (tùy lỗi) |
| Client nên làm | Lấy/cập nhật credentials, đăng nhập lại nếu cần | Không retry y nguyên chỉ bằng refresh token; cần quyền/đổi tài nguyên | Sửa input, xử lý conflict, hiển thị thông báo nghiệp vụ |
| Logging/metrics | Nhãn auth_failure | Nhãn access_denied | Domain error code cụ thể, không lộ secrets |

**Lưu ý:** 401/403 còn có thể xuất hiện do nhiều cơ chế ngoài ba cột: HTTP server, reverse proxy, WAF, CSRF hoặc API gateway. Bảng mô tả cách thiết kế ứng dụng thông thường, không thay thế điều tra tầng tạo response thật.

## 4. HTTP 401: chưa xác thực thành công

**401 Unauthorized** theo HTTP là tín hiệu server yêu cầu **authentication** hợp lệ cho tài nguyên. Tên “Unauthorized” khá dễ gây hiểu nhầm; cách dùng thực tế là **chưa xác thực thành công**, không phải “đã xác thực nhưng thiếu quyền”.

Những tình huống thường gặp:
- Không có `Authorization` header đối với API cần credentials.
- Header Basic có username/password sai.
- Bearer token đã hết hạn, sai chữ ký, sai issuer/audience hoặc không hợp lệ theo Resource Server.
- Cơ chế xác thực không nhận được thông tin để chứng minh danh tính.

Với HTTP Basic, một response đúng giao thức thường có:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Header `WWW-Authenticate` đưa ra challenge để client biết cơ chế cần dùng. Nếu viết custom error handler làm mất challenge, browser hoặc HTTP client có thể không xử lý được quy trình xác thực đúng như mong đợi.

Với Bearer Resource Server, challenge có thể ở dạng `WWW-Authenticate: Bearer ...` theo chuẩn liên quan, và chi tiết `invalid_token` hoặc scope có thể xuất hiện theo cấu hình. Không tự chép nguyên thông tin nhạy cảm từ token vào thông báo lỗi.

### 4.1. Kết quả 401 không tự đảm bảo có body JSON

Một Spring Security WebFilter có thể chỉ đặt status và header, không có body giống `ProblemDetail` của controller. Vì thế client không nên mặc định mọi 401 đều có JSON body giống lỗi nghiệp vụ. Nếu API yêu cầu một error envelope thống nhất, cần cấu hình **ngay tại entry point/failure handler** của Spring Security, không chỉ thêm `@RestControllerAdvice`.

### 4.2. Client nên làm gì?

- Nếu thiếu credentials và người dùng chưa login: đưa người dùng tới flow authentication phù hợp.
- Nếu token access hết hạn: có thể dùng refresh flow đã được bảo vệ, nhưng có giới hạn số lần thử.
- Nếu sai password/invalid token: báo lỗi phù hợp, tránh vô hạn retry.
- **Không tự cấp thêm quyền** hoặc bỏ authorization rule để “sửa 401”.
- Không đưa raw password, Authorization header hoặc token vào log frontend/server.

## 5. HTTP 403: đã có danh tính nhưng không đủ quyền

**403 Forbidden** thường có nghĩa server hiểu request nhưng **không cho phép** hành động. Ví dụ:
- User có `ROLE_USER` gọi `/api/admin/metrics` cần `ROLE_ADMIN`.
- User đọc đơn hàng thuộc về người khác.
- Người dùng không có authority/scope cần thiết.
- Tenant/ABAC policy hoặc rule `denyAll()` từ chối request.

Khác với 401, việc gửi lại **y nguyên** credentials thường không giúp giải quyết 403. Client cần điều chỉnh đối tượng truy cập, tài khoản/quyền hoặc xin cấp quyền qua quy trình hợp lệ.

### 5.1. 403 không luôn là lỗi phân quyền role

Trong Spring Security WebFlux, **CSRF** có thể trả **403** cho request POST/PUT/PATCH/DELETE thiếu hoặc sai token, dù HTTP Basic/JWT có hợp lệ. Reverse proxy và WAF cũng có thể trả 403. Vì vậy, hãy ghi nhận source của lỗi qua log/trace đúng cách, không đoán mọi 403 đều do `hasRole`.

### 5.2. Anonymous bị chặn có nhất thiết 403 không?

Không. Khi authorization yêu cầu quyền nhưng request chưa có authentication phù hợp, Spring Security có thể khởi động authentication entry point, dẫn tới **401** thay vì đưa request vào access-denied handler. Ứng dụng còn có thể dùng redirect tới login ở mô hình browser.

Cần xét **authentication state** cùng loại exception và cấu hình handler. Không viết điều kiện cứng “AccessDeniedException luôn 403”.

### 5.3. Khi nào trả 404 để che giấu tài nguyên?

Với một tài nguyên chỉ chủ sở hữu biết, API đôi khi chủ động trả **404 Not Found** cho người không được quyền xem để không tiết lộ sự tồn tại. Quyết định này phải nhất quán với threat model và data-access policy; 404 **không thay thế kiểm tra quyền**.

Không được thực hiện lookup trái phép rồi lộ dữ liệu qua timing, thông báo, cache hoặc thứ tự phân quyền. Cần có một mẫu service bảo vệ quyền sở hữu/tài nguyên nhất quán.

## 6. Lỗi nghiệp vụ: không phải mọi lỗi là 401/403

Khi danh tính và quyền hợp lệ, request vẫn có thể không được xử lý vì **điều kiện nghiệp vụ**. Một số cách ánh xạ phổ biến:

| HTTP | Tình huống | Vì sao phù hợp |
| --- | --- | --- |
| **400 Bad Request** | Sai cú pháp/định dạng tham số, thiếu field bắt buộc, kiểu dữ liệu không chuyển được | Request không đúng hợp đồng đầu vào |
| **404 Not Found** | ID tài nguyên không tồn tại/không được công bố cho người gọi | Tài nguyên được yêu cầu không tìm thấy |
| **409 Conflict** | Trạng thái hiện tại mâu thuẫn với thao tác: hết chỗ, phiên bản cập nhật cũ, tồn kho cạnh tranh | Cần xử lý xung đột trạng thái hiện tại |
| **422 Unprocessable Content** | Đầu vào đúng format nhưng vi phạm quy tắc semantic đã định nghĩa, ví dụ số lượng phải lớn hơn 0 | Nội dung có thể hiểu được nhưng không thể xử lý theo quy tắc |
| **429 Too Many Requests** | Đã vượt rate limit theo chính sách | Cần giảm tần suất hoặc đợi, có thể có `Retry-After` |
| **503 Service Unavailable** | Phụ thuộc quan trọng tạm thời không sẵn sàng hoặc hệ thống bảo trì/quá tải | Lỗi hạ tầng tạm thời, không phải lỗi dữ liệu do user |
| **500 Internal Server Error** | Lỗi server không được dự kiến: bug, NullPointerException, cấu hình hỏng | Không biến stack trace thành nội dung cho client |

Không có một ánh xạ HTTP duy nhất cho **mọi** domain. Ví dụ “mã giảm giá đã hết hạn” có thể được thiết kế là 400/409/422 tùy hợp đồng đã công bố, nhưng phải **nhất quán**, có machine-readable error code và test.

### 6.1. Phân biệt 400, 409 và 422 qua ví dụ

API xem trước khả năng đặt hàng:

~~~text
GET /api/orders/preview?quantity=abc
    -> 400: query parameter không chuyển được thành số nguyên

GET /api/orders/preview?quantity=0
    -> 422: kiểu dữ liệu hợp lệ, nhưng số lượng không thỏa quy tắc > 0

GET /api/orders/preview?quantity=9
    -> 409: số lượng hợp lệ về ngữ nghĩa, nhưng tồn kho hiện tại không đáp ứng

GET /api/orders/preview?quantity=2
    -> 200: có thể tạo preview
~~~

Đây là **GET read-only**: nó không đặt hàng, giảm tồn kho hay thực hiện giao dịch. Nếu sau này đổi sang endpoint tạo đơn thật bằng POST, cần thêm kiểm tra quyền, transaction/idempotency và CSRF khi client browser sử dụng ambient credentials. Không dùng GET có side effect để tránh việc phải gửi CSRF token.

### 6.2. Business error không đồng nghĩa exception hệ thống

Một việc kinh doanh dự kiến bị từ chối không nên ném `NullPointerException` chỉ để báo “không còn hàng”. Dùng exception/model domain riêng có tên và code rõ ràng, ví dụ `InsufficientStockException` hoặc `OrderAlreadyShippedException`.

Ngược lại, database mất kết nối không phải “đơn hàng không tồn tại”. Đừng map mọi lỗi repository/timeout thành 404 hoặc 409 chỉ vì client sẽ không thấy 500. Cần giữ đúng bản chất sự cố để vận hành nhận biết.

## 7. Điểm bắt lỗi trong Spring Security Reactive khác WebFlux controller

Trong ứng dụng WebFlux, quá trình xử lý thường bao gồm:

~~~text
Incoming HTTP
     |
     v
SecurityWebFilterChain
     |
     +--> AuthenticationWebFilter
     |       +--> Authentication conversion / manager
     |       +--> authentication failure handler
     |
     +--> ExceptionTranslationWebFilter / authorization
     |       +--> ServerAuthenticationEntryPoint (thường 401/challenge)
     |       +--> ServerAccessDeniedHandler (thường 403)
     |
     v
DispatcherHandler / RouterFunction / Controller
     |
     +--> @ExceptionHandler / @RestControllerAdvice
     |       +--> Domain exceptions -> 404/409/422
     |       +--> Binding/validation errors -> 400...
     |
     v
WebFlux ErrorWebExceptionHandler / framework error handling (khi cần)
     |
     v
Response
~~~

**Sơ đồ là khái niệm, không khẳng định thứ tự chính xác của mọi filter.** Authentication failure handler, exception translation, CSRF và routing có cơ chế riêng. Lỗi từ security filter có thể được xử lý trước khi controller được gọi.

### 7.1. Những class cần nhớ

| Thành phần | Trách nhiệm |
| --- | --- |
| `AuthenticationWebFilter` | Tiến hành authentication attempt, gọi converter/manager, xử lý success/failure |
| `ServerAuthenticationEntryPoint` | Khởi đầu authentication khi cần có danh tính; có thể trả 401 + challenge hoặc redirect |
| `ServerAuthenticationFailureHandler` | Xử lý một authentication attempt bị từ chối, tùy mechanism |
| `ServerAccessDeniedHandler` | Phản hồi khi access bị từ chối, thường 403 cho user đã xác thực |
| `ExceptionTranslationWebFilter` | Chuyển `AccessDeniedException` downstream sang entry point hoặc access-denied handler phù hợp |
| `@RestControllerAdvice` + `@ExceptionHandler` | Mapping exception của handler/controller/service sang HTTP response |
| `ErrorWebExceptionHandler` | Cơ chế xử lý lỗi cấp thấp của WebFlux/Boot |
| `ProblemDetail` | Dạng body tuân theo RFC 9457 cho lỗi API, không tự chọn nơi bắt security exception |

**Không dùng `ExceptionTranslationFilter` (Servlet) cho WebFlux.** Đối tượng reactive là `ExceptionTranslationWebFilter` và các interface có tên `Server...`. Không mang `HttpSecurity`, `HttpServletRequest`, `AuthenticationEntryPoint` của Servlet sang `ServerHttpSecurity`.

### 7.2. Vì sao @RestControllerAdvice không bắt mọi lỗi 401/403?

`@RestControllerAdvice` làm việc trong lớp xử lý controller và các lỗi liên quan. Request có thể bị Spring Security chặn **trước khi đến DispatcherHandler**. Khi đó `@ExceptionHandler(AuthenticationException.class)` đặt trong controller advice không bảo đảm được gọi.

Nếu API cần thống nhất body lỗi bảo mật, cấu hình **entry point** và **access denied handler** tại `ServerHttpSecurity.exceptionHandling(...)`, đồng thời xem cả failure handler của authentication mechanism. Không chỉ đặt một global `@ExceptionHandler(Exception.class)` rồi hy vọng bắt mọi filter exception.

### 7.3. Không nuốt AccessDeniedException

Ví dụ sai ở tầng service/controller:

~~~java
// SAI: biến thiếu quyền thành trạng thái thành công.
return service.loadSensitiveData()
        .onErrorResume(AccessDeniedException.class,
                ex -> Mono.just(new DataDto("hidden")));
~~~

Đây là snippet minh họa, không phải class chạy độc lập. Nếu một service phát `AccessDeniedException` vì thiếu quyền, việc thay bằng dữ liệu giả và HTTP 200 có thể che lấp một vi phạm an ninh. Chỉ xử lý exception khi có chính sách rõ ràng và đảm bảo response không sai semantics.

Tương tự, một `onErrorResume(Throwable.class, ...)` nằm quá cao trong pipeline có thể vô tình biến 401/403/500 thành 200. Mọi fallback phải giới hạn đúng loại lỗi và có test.

## 8. Thiết kế response body: dùng ProblemDetail và mã nghiệp vụ

Spring Framework WebFlux hỗ trợ **RFC 9457 Problem Details for HTTP APIs** qua `org.springframework.http.ProblemDetail`. Một response ví dụ:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Requested quantity is not available",
  "instance": "/api/orders/preview",
  "code": "INSUFFICIENT_STOCK"
}
~~~

Các trường chuẩn:
- `type`: URI nhận diện loại vấn đề, mặc định có thể là `about:blank`.
- `title`: tiêu đề ngắn, thường không thay đổi cho mỗi lần xuất hiện.
- `status`: mã HTTP tương ứng.
- `detail`: giải thích có thể hiển thị an toàn cho client.
- `instance`: URI của request bị ảnh hưởng.
- `code` trong ví dụ là **extension property do ứng dụng thêm**, không phải trường bắt buộc trong RFC 9457.

Đối với client, nên dựa vào **HTTP status** cho lớp xử lý tổng quát và **error code ổn định** cho hành động nghiệp vụ, thay vì phân tích câu tiếng Anh/tiếng Việt trong `detail`.

### 8.1. Vì sao nên thống nhất error contract?

- Frontend có thể hiển thị lỗi đăng nhập, thiếu quyền và hết hàng đúng thông điệp.
- Mobile/backend client có thể tự quyết định retry hay yêu cầu user sửa dữ liệu.
- Dashboard có thể phân biệt auth failure, denied, input invalid, conflict và server outage.
- Backend không cần để lộ raw exception message, SQL hoặc stack trace.
- Tài liệu API/OpenAPI có thể khai báo các response 4xx/5xx với schema rõ ràng.

Nhưng **thống nhất contract không nhất thiết ép mọi response có body**. Một số HTTP statuses hoặc cơ chế authentication chuẩn có header bắt buộc/quan trọng; không làm mất `WWW-Authenticate` của HTTP Basic/Bearer chỉ vì muốn trả JSON. Nếu thêm body cho security response, phải thiết kế riêng và test.

### 8.2. Bật hỗ trợ Problem Details cho lỗi WebFlux chuẩn

Spring Boot hỗ trợ:

~~~yaml
spring:
  webflux:
    problemdetails:
      enabled: true
~~~

Nó cho phép nhiều **lỗi WebFlux built-in** được biểu diễn theo Problem Details. Cấu hình này **không tự động biến mọi lỗi bên trong Spring Security WebFilter** thành JSON ProblemDetail. Những lỗi authentication/authorization xử lý ở security layer vẫn cần entry point/handler tương ứng nếu muốn một body thống nhất.

## 9. Ví dụ hoàn chỉnh Java 17+: bảo mật trước, nghiệp vụ sau

Ta sẽ xây dựng một API WebFlux nhỏ, có đủ:
- Endpoint công khai.
- Endpoint yêu cầu người dùng đã đăng nhập.
- Endpoint riêng của ADMIN.
- Lỗi input: 400.
- Lỗi tài nguyên không tồn tại: 404.
- Lỗi điều kiện số lượng: 422.
- Lỗi tồn kho: 409.
- Lỗi xác thực: 401.
- Lỗi phân quyền: 403.

Để dễ chạy bằng `curl`, demo dùng HTTP Basic với tài khoản in-memory. **Chỉ dùng trên localhost** vì password demo có `{noop}` và Basic credentials không được mã hóa bằng Base64. Production cần HTTPS, password hashing mạnh, rate limit, audit và cơ chế đăng nhập thích hợp.

Sử dụng Spring Boot **3.5.7**, Java 17, Gradle và Spring Security Reactive 6.x. Mã ví dụ được thiết kế theo API công khai; kết quả HTTP là kỳ vọng khi chạy đúng dự án, không phải báo cáo một lần build thực tế.

### 9.1. Cấu trúc file

~~~text
reactive-error-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── ApiController.java
    │   │   ├── DomainExceptions.java
    │   │   └── DomainErrorAdvice.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        └── ErrorResponseTest.java
~~~

### 9.2. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-error-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý các phiên bản thư viện WebFlux, Spring Security và Reactor qua dependency management. Khi đưa vào hệ thống thật, chọn nhánh Boot đang được tổ chức hỗ trợ và có bản vá mới; version ở đây chỉ để demo có cấu hình rõ ràng.

### 9.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: reactive-error-demo
  webflux:
    problemdetails:
      enabled: true
~~~

Tùy chọn này giúp lỗi framework chuẩn (ví dụ không chuyển được tham số `quantity=nope` sang `int`) có response Problem Details khi được bộ xử lý WebFlux tương ứng giải quyết. Nó không thay thế các custom `@ExceptionHandler` của lỗi domain hay Spring Security handlers.

### 9.4. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.5. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.HttpStatusServerAccessDeniedHandler;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/public")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin/metrics")
                                .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.GET,
                                "/api/products/**",
                                "/api/orders/preview")
                                .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint(
                                new HttpBasicServerAuthenticationEntryPoint())
                        .accessDeniedHandler(
                                new HttpStatusServerAccessDeniedHandler(
                                        HttpStatus.FORBIDDEN)))
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}readerpass")
                .roles("READER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}adminpass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }
}
~~~

**Phân tích từng quyết định:**
1. `/api/public` không cần login.
2. `/api/admin/metrics` cần role `ADMIN`.
3. `/api/products/**` và `/api/orders/preview` yêu cầu xác thực, nhưng không yêu cầu ADMIN.
4. `anyExchange().denyAll()` chặn route/method không được khai báo. Điều này có thể khiến một URL không khớp controller trả 403 **trước khi** WebFlux dự định trả 404.
5. HTTP Basic dùng cho demo để thử 401, không phải là phương án mặc định cho sản phẩm thực.
6. `HttpBasicServerAuthenticationEntryPoint` là entry point Reactive cho Basic: có thể tạo 401 kèm challenge `WWW-Authenticate`.
7. `HttpStatusServerAccessDeniedHandler(HttpStatus.FORBIDDEN)` phản hồi 403 khi authorization từ chối và handler đó được áp dụng.
8. `formLogin` tắt để không có 302 redirect tới trang đăng nhập HTML trong ví dụ.
9. CSRF vẫn giữ mặc định. Các endpoint ở demo chỉ sử dụng GET, nên không cần mã CSRF token cho lệnh thử này. Nếu thêm POST, phải đánh giá CSRF đúng cách.
10. User in-memory và `{noop}` là giả lập không an toàn cho production.

**Không nhầm role với authority:** `hasRole("ADMIN")` thông thường kiểm tra authority `ROLE_ADMIN`; `hasAuthority("ADMIN")` là chuỗi khác. Hai user demo chỉ có role đã khai báo.

### 9.6. DomainExceptions.java

`src/main/java/demo/DomainExceptions.java`:

~~~java
package demo;

// Các class package-private hợp lệ cùng một file Java;
// file không chứa public class nên không có ràng buộc tên public.

final class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException() {
        super("Product not found");
    }
}

final class InvalidQuantityException extends RuntimeException {
    InvalidQuantityException() {
        super("Quantity must be positive");
    }
}

final class StockConflictException extends RuntimeException {
    StockConflictException() {
        super("Requested quantity exceeds available stock");
    }
}
~~~

Mỗi exception có **ngữ nghĩa domain riêng** và không cần phụ thuộc Spring Security. Đây là những lỗi được dự kiến trong use case, khác với `BadCredentialsException` hoặc `AccessDeniedException`.

### 9.7. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record ProductView(long id, String name) {
    }

    public record PreviewView(String status, int quantity, int stock) {
    }

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/admin/metrics")
    public Mono<String> adminMetrics() {
        return Mono.just("admin-only");
    }

    @GetMapping("/api/products/{id}")
    public Mono<ProductView> product(@PathVariable long id) {
        if (id != 1L) {
            return Mono.error(new ProductNotFoundException());
        }
        return Mono.just(new ProductView(1L, "Notebook"));
    }

    @GetMapping("/api/orders/preview")
    public Mono<PreviewView> preview(@RequestParam int quantity) {
        if (quantity < 1) {
            return Mono.error(new InvalidQuantityException());
        }
        if (quantity > 5) {
            return Mono.error(new StockConflictException());
        }
        return Mono.just(new PreviewView("AVAILABLE", quantity, 5));
    }
}
~~~

**Vì sao dùng `Mono.error`?** Trong Reactor, lỗi là một terminal signal của Publisher. `Mono.error(new InvalidQuantityException())` không biến lỗi thành giá trị thành công; WebFlux có thể chuyển nó vào exception-handling thích hợp.

Controller chỉ làm thao tác **read-only** để minh họa status. Dữ liệu kho được hard-code là 5; một hệ thống thật phải kiểm tra tồn kho trong transaction phù hợp khi xác nhận đặt hàng. Preview 200 **không bảo đảm** hàng còn khi user thực hiện POST đặt hàng sau đó.

Chú ý:
- `quantity=nope` sẽ bị lỗi **chuyển kiểu dữ liệu đầu vào** trước khi logic domain xét `quantity < 1`.
- `quantity=0` chuyển sang `int` thành công rồi mới vi phạm business rule.
- `quantity=9` là giá trị hợp lệ nhưng xung đột với tồn kho minh họa.
- `id=99` khớp route và authorization, nhưng dữ liệu không có nên domain trả 404.
- Không đặt role check trong controller để “chữa” security; controller chỉ tiếp nhận request đã qua HTTP rules cần thiết.

### 9.8. DomainErrorAdvice.java

`src/main/java/demo/DomainErrorAdvice.java`:

~~~java
package demo;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class DomainErrorAdvice {

    @ExceptionHandler(ProductNotFoundException.class)
    public ProblemDetail productNotFound(ProductNotFoundException ignored) {
        return problem(
                HttpStatus.NOT_FOUND,
                "Product not found",
                "The requested product does not exist",
                "PRODUCT_NOT_FOUND");
    }

    @ExceptionHandler(InvalidQuantityException.class)
    public ProblemDetail invalidQuantity(InvalidQuantityException ignored) {
        return problem(
                HttpStatus.UNPROCESSABLE_ENTITY,
                "Invalid quantity",
                "Quantity must be at least 1",
                "INVALID_QUANTITY");
    }

    @ExceptionHandler(StockConflictException.class)
    public ProblemDetail stockConflict(StockConflictException ignored) {
        return problem(
                HttpStatus.CONFLICT,
                "Stock conflict",
                "Requested quantity is not available",
                "INSUFFICIENT_STOCK");
    }

    private static ProblemDetail problem(
            HttpStatus status,
            String title,
            String detail,
            String code) {

        ProblemDetail result = ProblemDetail.forStatusAndDetail(status, detail);
        result.setTitle(title);
        result.setProperty("code", code);
        return result;
    }
}
~~~

**Điểm cần hiểu:**
- `@RestControllerAdvice` chỉ đăng ký mapping cho **exception domain** phát sinh trong WebFlux handler/controller flow; không cố bắt `AuthenticationException` của Security filters.
- `ProblemDetail.forStatusAndDetail(...)` đặt status và detail phù hợp.
- `setProperty("code", ...)` đưa thêm **machine-readable code** vào JSON; Spring WebFlux/Jackson xử lý extension property theo cơ chế ProblemDetail.
- `@Order(HIGHEST_PRECEDENCE)` đặt advice này ưu tiên cao so với các advice khác, nhưng vì handler chỉ nhận ba class cụ thể nên không nuốt lỗi WebFlux chuẩn.
- Không có `@ExceptionHandler(Exception.class)` catch-all để làm mọi lỗi thành 409/500 hoặc khiến security error bị che.
- Public detail cố ý **không chứa SQL, inventory nhạy cảm, username, token, secret hay stack trace**.

Với `spring.webflux.problemdetails.enabled=true`, lỗi binding WebFlux built-in như `quantity=nope` có thể được Boot/Spring xử lý thành 400 theo RFC 9457 mà không cần ép nó thành `InvalidQuantityException`.

## 10. Chạy thử bằng curl và đối chiếu từng tầng

Trong thư mục dự án:

~~~bash
gradle bootRun
~~~

Nếu có Gradle Wrapper, dùng `./gradlew bootRun` trên macOS/Linux hoặc `gradlew.bat bootRun` trên Windows. Mặc định HTTP server nghe ở `http://localhost:8080`.

**Các lệnh sau chỉ dành cho local demo**. Trong môi trường thật, HTTP Basic phải đi qua HTTPS; đừng gõ mật khẩu thật vào shell history.

~~~bash
# 1. Công khai, không credentials
curl -i http://localhost:8080/api/public

# 2. Thiếu credentials ở route cần authentication
curl -i http://localhost:8080/api/products/1

# 3. Sai Basic password
curl -i -u reader:wrong http://localhost:8080/api/products/1

# 4. Đúng credentials, có dữ liệu
curl -i -u reader:readerpass http://localhost:8080/api/products/1

# 5. Đã đăng nhập nhưng thiếu role ADMIN
curl -i -u reader:readerpass http://localhost:8080/api/admin/metrics

# 6. Đúng role ADMIN
curl -i -u admin:adminpass http://localhost:8080/api/admin/metrics

# 7. Business: sản phẩm không tồn tại
curl -i -u reader:readerpass http://localhost:8080/api/products/99

# 8. Request input sai kiểu
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=nope'

# 9. Dữ liệu đúng kiểu nhưng vi phạm quy tắc semantic
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=0'

# 10. Business conflict: yêu cầu vượt kho
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=9'

# 11. Thành công
curl -i -u reader:readerpass \
  'http://localhost:8080/api/orders/preview?quantity=2'
~~~

Bảng kết quả kỳ vọng:

| Lệnh | HTTP | Tầng quyết định | Nội dung nổi bật |
| --- | --- | --- | --- |
| 1 | **200 OK** | Public authorization | `public` |
| 2 | **401 Unauthorized** | Authentication entry point | Có thể có `WWW-Authenticate: Basic ...` |
| 3 | **401 Unauthorized** | Authentication failure handler | Password sai |
| 4 | **200 OK** | Authentication + route + domain | JSON product id=1 |
| 5 | **403 Forbidden** | Authorization | Reader thiếu ADMIN |
| 6 | **200 OK** | Authorization cho ADMIN | `admin-only` |
| 7 | **404 Not Found** | DomainErrorAdvice | `code=PRODUCT_NOT_FOUND` |
| 8 | **400 Bad Request** | WebFlux request parameter binding | Query không chuyển được thành int |
| 9 | **422 Unprocessable Content** | DomainErrorAdvice | `code=INVALID_QUANTITY` |
| 10 | **409 Conflict** | DomainErrorAdvice | `code=INSUFFICIENT_STOCK` |
| 11 | **200 OK** | Use case thành công | `status=AVAILABLE` và `quantity=2` |

**Cẩn trọng:** bảng nêu status mong đợi từ mã và cấu hình mẫu. Body/header của các lỗi built-in có thể khác theo version, content negotiation và entry point. Không cố viết assertion so sánh toàn JSON khi response có `instance` hay timestamp thay đổi.

### 10.1. Ví dụ domain ProblemDetail

Khi gọi `quantity=9`, một body hợp lý:

~~~json
{
  "type": "about:blank",
  "title": "Stock conflict",
  "status": 409,
  "detail": "Requested quantity is not available",
  "instance": "/api/orders/preview",
  "code": "INSUFFICIENT_STOCK"
}
~~~

Trường `instance` có thể được framework tự thêm theo request. Không yêu cầu thứ tự JSON keys cố định. Với các lỗi security 401/403, body có thể trống vì chúng được xử lý ở filter layer; status và challenge/headers vẫn là hợp đồng HTTP quan trọng.

## 11. Test WebFlux bằng WebTestClient

Thử thủ công giúp hiểu request; **automated tests** giúp ngăn bug khi refactor security hoặc domain. Test dùng Spring Security Test để áp security chain vào WebTestClient khi bind application context.

`src/test/java/demo/ErrorResponseTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ErrorResponseTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicRouteAllowsAnonymous() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingCredentialsReturn401() {
        client.get().uri("/api/products/1")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                .valueMatches("WWW-Authenticate", "Basic.*");
    }

    @Test
    void wrongCredentialsReturn401() {
        client.get().uri("/api/products/1")
                .headers(h -> h.setBasicAuth("reader", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void readerCannotCallAdminEndpoint() {
        client.get().uri("/api/admin/metrics")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallAdminEndpoint() {
        client.get().uri("/api/admin/metrics")
                .headers(h -> h.setBasicAuth("admin", "adminpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void knownProductIsSuccessful() {
        client.get().uri("/api/products/1")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.name").isEqualTo("Notebook");
    }

    @Test
    void missingProductIsDomain404() {
        client.get().uri("/api/products/99")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
                .jsonPath("$.status").isEqualTo(404);
    }

    @Test
    void malformedQuantityIsFramework400() {
        client.get().uri("/api/orders/preview?quantity=nope")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void zeroQuantityIsDomain422() {
        client.get().uri("/api/orders/preview?quantity=0")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_QUANTITY");
    }

    @Test
    void excessQuantityIsDomain409() {
        client.get().uri("/api/orders/preview?quantity=9")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.code").isEqualTo("INSUFFICIENT_STOCK");
    }

    @Test
    void validPreviewIs200() {
        client.get().uri("/api/orders/preview?quantity=2")
                .headers(h -> h.setBasicAuth("reader", "readerpass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("AVAILABLE")
                .jsonPath("$.quantity").isEqualTo(2);
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Dự kiến **11 test** hoàn thành với các file/dependencies đã nêu. Đây là phân tích mã để người học có thể tự thử, **không phải khẳng định Gradle đã chạy tại đây**.

Điểm nổi bật:
- Test 401 thiếu credentials kiểm tra cả `WWW-Authenticate` để giữ giao thức Basic.
- Test 403 có credentials hợp lệ nhưng thiếu role.
- Test 404/409/422 xác nhận lỗi do domain phát ra cùng `code` ổn định, không phân tích `detail` bằng text.
- Test 400 xác nhận sai kiểu dữ liệu bị WebFlux từ chối trước business validation.
- Không có test POST vì demo chỉ GET; thêm thao tác ghi phải xét CSRF, HTTP semantics, transaction và idempotency.

## 12. Vì sao có lúc lỗi “business” lại thành 500?

Giả sử nghiệp vụ phát:

~~~java
return inventoryRepository.reserve(id, quantity)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("Insufficient stock")));
~~~

Đây chỉ là snippet minh họa, thiếu repository và không phải một class chạy độc lập. Nếu không có handler phù hợp, `IllegalStateException` có thể đi vào xử lý lỗi chung và bị trả 500. Vì thế:
- Không dùng exception hệ thống chung để biểu diễn mọi quy tắc business dự kiến.
- Định nghĩa exception/error code domain rõ ràng.
- Mapping đúng tại `@ExceptionHandler` hoặc error mapper có phạm vi phù hợp.
- Không bắt mọi `Exception` rồi tự trả 409 vì sẽ che lỗi lập trình hay lỗi hạ tầng thật.

### 12.1. Vì sao không dùng onErrorResume để biến lỗi thành 200?

Ví dụ anti-pattern:

~~~java
// SAI: client nhận 200 dù đặt hàng thất bại.
return orderService.placeOrder(command)
        .onErrorResume(ex -> Mono.just(
                new OrderResult("FAILED", null)));
~~~

Không có `@ResponseStatus` hoặc `ResponseEntity` thì controller thường trả 200 với body “FAILED”. Một số client có thể coi đó là thành công và bỏ qua việc xử lý retry/rollback.

Mẫu hợp lý:

~~~java
return orderService.placeOrder(command)
        .onErrorMap(OutOfStockRepositoryException.class,
                ex -> new StockConflictException());
~~~

Đây là snippet minh họa, không phải ví dụ chạy riêng. Nó chỉ chuyển **đúng lỗi liên quan đến business state** sang exception domain; các lỗi khác tiếp tục nổi lên đúng bản chất.

### 12.2. Nguy cơ response đã bắt đầu truyền

Với WebFlux streaming (`Flux`, Server-Sent Events), response có thể đã gửi headers/những bytes đầu tiên. Nếu Publisher phát lỗi **sau khi response đã committed**, server không thể tự đổi status 200 thành 409/500 nữa. Cần:
- Xác thực, phân quyền và kiểm tra những điều kiện có thể kiểm tra **trước khi** bắt đầu stream.
- Thiết kế protocol báo lỗi trong event stream nếu nghiệp vụ thực sự streaming.
- Không giả định một `@ExceptionHandler` luôn có thể dựng HTTP response mới sau khi headers đã gửi.
- Tránh buffer toàn bộ stream chỉ để đổi status nếu ảnh hưởng memory/latency và không cần thiết.

## 13. Trả 401/403 dạng JSON đồng nhất: thiết kế như thế nào?

Mã demo giữ error response security theo giao thức HTTP Basic (status/challenge), còn lỗi domain dùng ProblemDetail. Nhiều API muốn một envelope có `code` cho cả security error; việc này làm được, nhưng phải triển khai **ở đúng tầng**.

### 13.1. Entry point và denied handler

Trong Spring Security Reactive:

~~~java
// Chữ ký khái niệm của hai functional interfaces:
// KHÔNG phải class Java chạy độc lập.

ServerAuthenticationEntryPoint entryPoint =
        (exchange, authenticationException) -> {
            // đặt 401, WWW-Authenticate nếu scheme yêu cầu,
            // serialize body an toàn, kết thúc bằng Mono<Void>
            return Mono.empty();
        };

ServerAccessDeniedHandler deniedHandler =
        (exchange, accessDeniedException) -> {
            // đặt 403 và serialize body an toàn
            return Mono.empty();
        };
~~~

**Quan trọng:** snippet trên chỉ mô tả giao diện callback; nếu dùng nguyên `Mono.empty()` mà không set status/headers thì **không phải implementation hoạt động đúng**. Trong sản phẩm thật, dùng implementation tiêu chuẩn hoặc viết response writer bảo đảm status, content type, headers, body serialization và error propagation.

Có thể cấu hình:

~~~java
// Trong SecurityWebFilterChain đã xây dựng.
.exceptionHandling(ex -> ex
        .authenticationEntryPoint(customEntryPoint)
        .accessDeniedHandler(customDeniedHandler))
~~~

Đây là snippet kết nối các bean đã được khai báo, không phải một chương trình độc lập. Nếu dùng HTTP Basic, phải giữ `WWW-Authenticate` khi trả 401; nếu dùng Bearer thì giữ challenge đúng chuẩn Bearer. Đừng chỉ ghi `application/problem+json` rồi bỏ yêu cầu của giao thức authentication.

### 13.2. Authentication failure handler là điểm bổ sung

Một số authentication mechanism có **failure handler riêng** trong `AuthenticationWebFilter`. Vì vậy, custom `ServerAuthenticationEntryPoint` cho authorization anonymous **không tự đảm bảo** mọi lần sai mật khẩu/token cũng ra cùng JSON body. Kiểm tra:
- Request thiếu credentials.
- Request có credentials sai.
- Request có token hết hạn.
- Request đã xác thực nhưng thiếu authority.
- Request POST thiếu CSRF token.

Từng loại có thể đi qua entry point, failure handler, access-denied handler hoặc CSRF handler khác nhau. Một test duy nhất cho 401 không đủ chứng minh tính nhất quán của error envelope.

### 13.3. ProblemDetail có nên dùng cho lỗi security không?

Có thể dùng format RFC 9457 trong 401/403 nếu triển khai writer phù hợp. Nhưng việc chọn format không được làm thay đổi semantics: 401 vẫn là 401, challenge vẫn phải giữ; 403 không được đổi sang 401 chỉ để frontend mở login; 404 che sự tồn tại chỉ khi policy đã quyết định.

Một error code có thể là `AUTHENTICATION_REQUIRED`, `INVALID_CREDENTIALS` hoặc `ACCESS_DENIED` nhưng phải cẩn thận không tiết lộ rằng một username có tồn tại, token có quyền cụ thể hay tài nguyên có ở tenant khác.

## 14. Cách client nên phản ứng với từng status

| HTTP | UI/Mobile | Backend/service client | Retry |
| --- | --- | --- | --- |
| 401 | Yêu cầu login/re-authentication hoặc refresh token đúng quy trình | Cấp lại token hợp lệ, cảnh báo cấu hình credentials | Có thể thử **giới hạn** sau refresh, không vòng lặp vô tận |
| 403 | Hiển thị không đủ quyền hoặc điều hướng về khu vực cho phép | Không tự gửi lại y nguyên như 401 | Không nếu quyền/chính sách không đổi |
| 400 | Yêu cầu sửa input sai định dạng | Sửa serialization/contract | Không retry cùng payload |
| 404 | Thông báo không tìm thấy hoặc không có quyền xem tùy policy | Xác minh ID, namespace, tenant | Không retry mù quáng |
| 409 | Yêu cầu refresh dữ liệu hoặc giải quyết xung đột | Tải state mới, dùng optimistic locking/idempotency | Chỉ retry khi đã xử lý conflict |
| 422 | Hiển thị lỗi validation/semantic cụ thể | Sửa payload/logic domain | Không retry cùng payload |
| 429 | Thông báo chờ, giảm tần suất | Backoff có giới hạn; tôn trọng Retry-After | Có, với backoff và giới hạn |
| 500 | Thông báo lỗi hệ thống và mã yêu cầu hỗ trợ | Log/trace; circuit breaker hợp lý | Tùy idempotency và loại thao tác |
| 503 | Thông báo tạm gián đoạn | Backoff/circuit breaker, xem Retry-After | Có thể, tránh gây thundering herd |

Client không được tự quyết định “403 nghĩa là token hết hạn” rồi refresh liên tục. Việc xử lý error code/status cần được thống nhất trong API contract và viết test integration giữa frontend/backend.

### 14.1. Idempotency quan trọng khi retry

Retry POST tạo đơn có thể nhân đôi giao dịch nếu server đã xử lý nhưng response thất lạc. Với thao tác ghi, cần thiết kế **idempotency key** hoặc kiểm soát transaction/phiên bản để retry an toàn; status 409/503/timeout không tự quyết định retry có an toàn hay không.

### 14.2. Đừng dùng thông điệp tự nhiên làm logic

Thay vì:

~~~javascript
if (problem.detail.includes("stock")) {
  // ...
}
~~~

hãy dựa vào mã ổn định:

~~~javascript
if (response.status === 409 && problem.code === "INSUFFICIENT_STOCK") {
  // Hiển thị tình huống thiếu tồn kho.
}
~~~

Hai đoạn là snippet JS minh họa; trong code thật phải kiểm tra `Content-Type` và parse JSON an toàn vì security errors hoặc gateway responses không phải lúc nào cũng có `application/problem+json`.

## 15. Logging, observability và không làm lộ thông tin

Một error contract tốt phải hữu ích cho cả người dùng lẫn vận hành, nhưng không tiết lộ dữ liệu nhạy cảm.

### 15.1. Điều có thể log

- Correlation/request ID đã được tạo và kiểm tra.
- HTTP method, route template (không đưa token/password vào path).
- HTTP status, safe error code như `PRODUCT_NOT_FOUND`.
- Loại exception nội bộ, thời gian xử lý, source subsystem.
- Bằng chứng liên quan đến policy ở mức phù hợp, không ghi toàn bộ credentials.
- Metrics tổng hợp như số 401, 403, 409, 500 theo route.

### 15.2. Điều không nên trả về/log

- `Authorization` header, raw password, Bearer token, session ID, CSRF token.
- SQL truy vấn có dữ liệu người dùng, stack trace, thông tin máy chủ nội bộ.
- Danh sách quyền/roles bí mật, tenant IDs không được công khai.
- Chẩn đoán “username này tồn tại nhưng mật khẩu sai” nếu có nguy cơ user enumeration.
- Chi tiết upstream exception chưa được sanitize.
- Toàn bộ response body của giao dịch nhạy cảm.

Client nhận mã lỗi ổn định và một thông điệp chung an toàn; log server có thể lưu stack trace trong hệ thống kiểm soát truy cập khi thật sự cần debug. Không đồng nhất việc 4xx với “không cần giám sát”: nếu 401/403/409 tăng bất thường, có thể là tấn công, bug client hoặc xung đột hệ thống.

### 15.3. 401 và 403 trong thống kê

Nếu một auth filter trả 401 mà controller không chạy, metric đếm exception ở `@ControllerAdvice` sẽ **không nhìn thấy** lỗi đó. Quan sát ở tầng HTTP server/filter/gateway/observability phù hợp để lấy đủ các status, tránh dashboard chỉ đo business errors rồi kết luận không có auth failures.

## 16. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Lỗi sai mật khẩu trả 403 | Client hiểu nhầm quyền thay vì authentication | Trả 401/challenge phù hợp |
| User đã login thiếu role trả 401 | Frontend thử login lại không cần thiết | Thông thường dùng 403 |
| Mọi lỗi nghiệp vụ trả 500 | Che bản chất và làm monitoring báo sai sự cố | Map domain errors tới 4xx phù hợp |
| Domain exception cho role thiếu | Phân quyền bị đặt lẫn trong business error contract | Dùng authorization/AccessDeniedException hoặc chính sách tài nguyên |
| `@RestControllerAdvice` cố bắt mọi security filter error | Không chạy khi filter từ chối sớm | Cấu hình entry point/denied/failure handler |
| Custom 401 làm mất `WWW-Authenticate` | Client Basic/Bearer khó xử lý đúng | Giữ challenge theo giao thức |
| Mọi 403 đều được coi là thiếu role | CSRF, WAF, deny-all có thể là nguyên nhân | Điều tra tầng phát sinh |
| `permitAll` trên route nhạy cảm chỉ để nhìn thấy 404 | Có thể vô tình mở endpoint mới | Giữ deny-by-default và tách policy 404 rõ ràng |
| `onErrorResume(Exception.class, ...)` trả 200 | Nuốt security/domain/infra errors | Chỉ bắt lỗi cụ thể, giữ status đúng |
| Error JSON chứa stack trace hoặc token | Rò rỉ bí mật | Sanitized ProblemDetail và logging an toàn |
| 422 cho mọi input invalid | Trộn parsing failure và domain validation | Định nghĩa rõ 400 vs 422 theo hợp đồng |
| 409 cho database timeout | Client hiểu nhầm conflict | Giữ 5xx/503 cho lỗi hạ tầng tạm thời |
| 404 cho user không có quyền mà không kiểm tra sở hữu | Che dấu lỗi authorization thật | Kiểm tra quyền trước, chọn status theo policy |
| Dùng `block()` trong WebFlux để bắt lỗi | Chặn event-loop và phá reactive model | Dùng `Mono.error`, `onErrorMap`, handlers |
| Tự `subscribe()` để log/ghi response | Tách subscription/cancellation và request lifecycle | Compose publisher, dùng observability framework |
| Retry 401/403/409 vô hạn | Tăng tải và có thể nhân đôi giao dịch | Phân loại retry và idempotency |
| Chỉ test happy path 200 | 401/403/404/409 mapping có thể regress | Viết test âm tính tại từng boundary |

## 17. Checklist khi thiết kế lỗi cho một endpoint mới

Trước khi đưa endpoint vào production, trả lời:

1. **Client chưa xác thực:** status và challenge là gì? Login/refresh flow nào?
2. **Client xác thực sai:** failure handler nào xử lý? Có rò username/token không?
3. **Client thiếu quyền:** dùng 403 hay cố ý 404 để không lộ tài nguyên? Quy tắc nhất quán không?
4. **Request sai cấu trúc:** invalid JSON, sai query type, thiếu field trả 400 như thế nào?
5. **Request đúng cấu trúc nhưng sai domain:** 422 hay code nào? Error code có ổn định không?
6. **Trạng thái xung đột:** phiên bản lạc hậu, kho thiếu, giao dịch trùng trả 409 khi nào?
7. **Tài nguyên không tồn tại:** 404 có gây rò dữ liệu tenant khác không?
8. **Server/phụ thuộc hỏng:** giữ 500/503, trace và thông báo an toàn thế nào?
9. **Reactive:** error phát trước hay sau response committed? Flux/SSE xử lý thế nào?
10. **Security chain:** filter nào xử lý 401/403, controller advice nào xử lý domain?
11. **CSRF/CORS:** POST từ browser có thể bị 403 vì CSRF không? Preflight đã được giải quyết?
12. **Thông tin client:** có HTTP status chuẩn và machine-readable `code` chưa?
13. **Headers:** `WWW-Authenticate`, `Retry-After` hoặc caching headers có đúng không?
14. **Monitoring:** metrics/trace có thấy cả lỗi từ security filters và business handlers không?
15. **Tests:** đã có ca anonymous, wrong credentials, wrong role, invalid input, domain conflict, missing resource và happy path chưa?

### 17.1. Các kịch bản nên test thêm

- Route không được khai báo nhận response từ `anyExchange().denyAll()`, không phải 404 mặc định.
- Thêm resource thuộc tenant khác, kiểm tra quyền không bị bypass bởi việc chỉ check role.
- Token JWT hết hạn/sai issuer/audience với đúng Resource Server config, không phân loại nhầm thành domain 404.
- Request body JSON không parse được vs model binding không hợp lệ.
- POST browser thiếu CSRF token vs thiếu authentication; không suy luận từ một status.
- Domain conflict xảy ra **sau** bước kiểm tra quyền, không lộ thông tin kho trước khi auth.
- Service timeout, database unreachable, transaction rollback, response streaming đã committed.
- Error body không chứa stack trace/credentials trong production.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** User chưa gửi credentials, GET endpoint được bảo vệ. Đây là lỗi gì?

> Authentication chưa hoàn tất; thường HTTP 401, với Basic có `WWW-Authenticate`.

**Câu 2.** User có username/password đúng nhưng không có ROLE_ADMIN. Đây là lỗi gì?

> Authorization. Thường HTTP 403, không phải 401.

**Câu 3.** User có quyền gọi API nhưng yêu cầu đặt nhiều hơn tồn kho. Nên trả 401 hay 403 không?

> Không. Đó là domain conflict; ví dụ trả 409 + code `INSUFFICIENT_STOCK`.

**Câu 4.** `quantity=nope` và `quantity=0` khác nhau gì?

> `nope` không chuyển thành số nguyên: lỗi input 400. `0` parse thành công nhưng vi phạm quy tắc dương: ví dụ domain 422.

**Câu 5.** 403 có luôn là thiếu role không?

> Không. CSRF, deny-all, gateway hoặc policy khác cũng có thể từ chối 403.

**Câu 6.** Vì sao `@RestControllerAdvice` có thể không bắt 401?

> Request bị Spring Security WebFilter chặn trước khi tới controller; cần entry point/failure handler tại security layer.

**Câu 7.** `ProblemDetail` dùng để làm gì?

> Biểu diễn lỗi HTTP theo RFC 9457 với type/title/status/detail/instance và extension properties như `code`.

**Câu 8.** Có nên bắt mọi exception và trả 409 để frontend dễ xử lý không?

> Không. Lỗi server, lỗi mạng, lỗi lập trình không phải business conflict.

**Câu 9.** Trả 404 thay 403 có khiến tài nguyên tự được bảo vệ không?

> Không. Vẫn phải kiểm tra quyền thật; 404 chỉ là lựa chọn response theo chính sách tiết lộ thông tin.

**Câu 10.** Vì sao không retry POST khi nhận 503/timeout một cách vô hạn?

> Tác vụ có thể đã hoàn tất trước khi response mất. Cần giới hạn retry và thiết kế idempotency.

**Câu 11.** Vì sao Basic 401 thường cần `WWW-Authenticate`?

> Đây là HTTP authentication challenge cho client biết cơ chế cần cung cấp credentials.

**Câu 12.** Trong reactive streaming, vì sao không thể luôn chuyển 200 thành 500 khi Flux báo lỗi?

> Nếu response đã committed headers/body, HTTP status không còn có thể thay đổi; cần kiểm tra sớm hoặc có protocol báo lỗi trong stream.

## 19. Tổng kết

Lỗi xác thực, lỗi phân quyền và lỗi nghiệp vụ **không cùng một loại**:

~~~text
Thiếu/sai credentials     --> AUTHENTICATION --> thường 401
Đã login nhưng thiếu quyền --> AUTHORIZATION  --> thường 403
Input sai cấu trúc          --> WEB INPUT      --> thường 400
Resource không có           --> DOMAIN/ROUTE   --> 404 (tùy policy)
Trạng thái xung đột         --> DOMAIN         --> 409
Input hợp lệ cú pháp nhưng vi phạm quy tắc
                            --> DOMAIN         --> 422 theo hợp đồng
Lỗi hệ thống/infra          --> SYSTEM         --> 5xx
~~~

Trong **Spring Security Reactive**, dùng đúng điểm mở rộng: `ServerAuthenticationEntryPoint` hoặc authentication failure handler cho lỗi xác thực; `ServerAccessDeniedHandler` và authorization policy cho lỗi thiếu quyền; `@RestControllerAdvice`/`ProblemDetail` cho lỗi domain của controller/service. Dùng HTTP statuses rõ ràng, giữ authentication challenge, cung cấp error code ổn định và kiểm thử từng tầng qua `WebTestClient`.

### Tài liệu tham khảo chính thức

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Javadoc — `ServerHttpSecurity` (exceptionHandling): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security Javadoc — `HttpBasicServerAuthenticationEntryPoint`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/HttpBasicServerAuthenticationEntryPoint.html
- Spring Security Javadoc — `HttpStatusServerAccessDeniedHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/HttpStatusServerAccessDeniedHandler.html
- Spring Security Javadoc — `ExceptionTranslationWebFilter`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authorization/ExceptionTranslationWebFilter.html
- Spring Framework — Error Responses in WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Boot — Reactive Web Applications, Problem Details: https://docs.spring.io/spring-boot/reference/web/reactive.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
- RFC 9110 — HTTP Semantics: https://www.rfc-editor.org/rfc/rfc9110