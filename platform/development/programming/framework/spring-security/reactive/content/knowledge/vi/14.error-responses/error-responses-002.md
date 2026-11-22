# Phân biệt 401 Unauthorized với 403 Forbidden trong Spring Security Reactive

## 1. Mục tiêu và vấn đề thường gặp

Khi một REST API chạy trên **Spring WebFlux + Spring Security** từ chối request, client có thể nhận **401 Unauthorized** hoặc **403 Forbidden**. Hai mã rất dễ bị hiểu sai vì chữ Unauthorized trong tên 401 nghe giống “không có quyền”. Trong ngữ nghĩa HTTP hiện đại, điểm khác biệt chính là:

- **401 Unauthorized**: request chưa cung cấp bằng chứng xác thực hợp lệ cho tài nguyên đang yêu cầu. Client có thể cần đăng nhập, gửi credential hoặc làm mới token theo giao thức.
- **403 Forbidden**: server hiểu request nhưng không cho phép thực hiện. Một trường hợp điển hình là **người dùng đã xác thực thành công nhưng thiếu authority/role/permission**.

Một REST API tốt không chỉ trả đúng status mà còn duy trì giao thức authentication (**WWW-Authenticate** nếu cần), thông điệp lỗi an toàn, quy tắc truy cập thống nhất, log dễ chẩn đoán và test rõ ràng.

Sau bài học bạn sẽ:

1. Phân biệt **authentication (xác thực danh tính)** và **authorization (phân quyền)**, đồng thời giải thích vì sao 401/403 không phải từ đồng nghĩa.
2. Hiểu 401/403 theo **RFC 9110**, HTTP Basic và Bearer token.
3. Nhìn được luồng exception trong **SecurityWebFilterChain**: AuthenticationWebFilter, AuthorizationWebFilter, ExceptionTranslationWebFilter và các thành phần xử lý lỗi reactive.
4. Sử dụng **ServerAuthenticationEntryPoint** và **ServerAccessDeniedHandler** đúng chỗ.
5. Viết Java 17+ Spring Boot WebFlux trả JSON 401/403 nhất quán, không lộ credential và không đổi ý nghĩa của WWW-Authenticate.
6. Kiểm thử request thiếu credential, sai credential, user thường thiếu ROLE_ADMIN, admin đủ quyền, permitAll và denyAll.
7. Xử lý những ngoại lệ dễ gây nhầm: **403 do CSRF**, CORS preflight, form login redirect, bearer token hết hạn, 404/405, lỗi 5xx và quyền theo tài nguyên.

**Chú ý:** 401 không mang ý nghĩa “đã xác thực nhưng thiếu quyền”, còn 403 không mặc nhiên có nghĩa “mật khẩu sai”. Tuy vậy, status cuối cùng còn phụ thuộc authentication scheme, security chain, exception handler và quyết định bảo mật của endpoint.

## 2. Đọc đúng ngữ nghĩa HTTP: RFC 9110

### 2.1. 401 Unauthorized

Theo HTTP Semantics (RFC 9110), 401 chỉ ra request thiếu thông tin xác thực hợp lệ cho tài nguyên mục tiêu. Khi server gửi response **401**, nó **MUST** gửi ít nhất một challenge tương ứng trong header **WWW-Authenticate**.

Ví dụ HTTP Basic:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="lesson-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

Ở đây:

- **Status 401**: chưa có credential hợp lệ.
- **WWW-Authenticate: Basic realm="lesson-api"**: client được yêu cầu dùng HTTP Basic trong vùng bảo vệ tương ứng.
- **JSON body**: hợp đồng thông tin cho ứng dụng khách; không thay thế challenge theo chuẩn.
- **no-store**: hạn chế cache phản hồi có liên quan bảo mật.
- **message**: không tiết lộ username tồn tại hay không, raw password, token hay stack trace.

Các tình huống phổ biến: endpoint yêu cầu authenticated nhưng không có header; header Basic có username/password sai; bearer token hết hạn hoặc không hợp lệ. Tuy nhiên, mỗi scheme có challenge riêng; không bao giờ dùng Basic challenge ở endpoint chỉ hỗ trợ Bearer.

### 2.2. 403 Forbidden

403 có nghĩa server hiểu request nhưng **từ chối thực hiện**. Người gọi có thể đã xác thực, hoặc server có lý do từ chối khác; RFC không khẳng định mọi 403 đều phải có một Authentication hợp lệ.

Ví dụ caller đã đăng nhập nhưng thiếu ROLE_ADMIN:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

Một 403 thông thường **không bắt buộc** kèm WWW-Authenticate. Nếu thêm Basic challenge cho user đã đăng nhập nhưng thiếu quyền admin, client có thể hiểu nhầm rằng gửi lại cùng password sẽ khắc phục quyền hạn.

**Phân biệt chính xác hơn:** 401 gắn với việc chưa đáp ứng yêu cầu **authentication**, còn 403 là một quyết định **refusal**; trong Spring Security, người đã xác thực mà không có authority thường nhận 403. Một hệ thống có thể chủ động trả 404 thay vì 403 để không công khai sự tồn tại của tài nguyên, nhưng phải thiết kế chính sách và test nhất quán.

### 2.3. Bảng so sánh nhanh

| Tiêu chí | 401 Unauthorized | 403 Forbidden |
| --- | --- | --- |
| Ý nghĩa chủ đạo | Thiếu/sai credential so với scheme mà endpoint yêu cầu | Server từ chối thao tác |
| Caller thường gặp | Chưa login, token sai, token hết hạn | Đã login nhưng thiếu role/scope/quyền theo bản ghi |
| WWW-Authenticate | Bắt buộc có challenge theo RFC 9110 khi phản hồi 401 | Thông thường không cần; một số scheme có thông tin bổ sung |
| Client nên làm gì? | Có thể cần đăng nhập/cấp credential hợp lệ/làm mới token | Không tự retry vô hạn; có thể yêu cầu quyền hoặc đổi thao tác |
| Có phải lỗi nghiệp vụ 4xx khác? | Không dùng thay 400/404/409 | Không dùng thay 400/404/409 nếu không liên quan quyền |
| Có nên phân biệt sai username và sai password trong body? | Không nên | Không áp dụng |
| Có nên trả 200 kèm {"error":...}? | Không | Không |

## 3. Authentication, authorization và tài nguyên

**Authentication** trả lời “caller là ai?” và phải kiểm chứng credential bằng cơ chế tin cậy. **Authorization** trả lời “caller này có được thực hiện hành động với request/tài nguyên này không?”.

Sơ đồ:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    +--> AuthenticationWebFilter (Basic, Bearer, ...)
    |      |
    |      +--> Thiếu credential: có thể không tạo Authentication
    |      +--> Credential sai: authentication failure
    |      +--> Credential đúng: Authentication được tin cậy
    |
    +--> AuthorizationWebFilter / rule authorizeExchange
    |      |
    |      +--> Endpoint permitAll: cho qua bước URL authorization
    |      +--> Endpoint authenticated: cần caller được xác thực
    |      +--> Endpoint hasRole/hasAuthority: cần quyền cụ thể
    |      +--> Endpoint denyAll: từ chối tất cả
    |
    +--> ExceptionTranslationWebFilter / các error handler
    |      |
    |      +--> Cần xác thực: ServerAuthenticationEntryPoint
    |      +--> Có xác thực nhưng thiếu quyền: ServerAccessDeniedHandler
    |
    v
Controller / RouterFunction / Service
    |
    v
Business authorization (owner, tenant, record policy)
    |
    v
Response
~~~

Đây là sơ đồ khái niệm, không cam kết thứ tự tất cả WebFilter trong từng phiên bản/cấu hình. Một lỗi authentication có thể được xử lý trực tiếp bởi filter xác thực, còn lỗi authorization thường đi qua exception translation. Vì thế đôi khi cần cấu hình entry point cả trong **httpBasic(...)** và **exceptionHandling(...)** để thống nhất JSON.

### 3.1. SecurityContext và AnonymousAuthenticationToken

Một Authentication có thể chứa principal, authorities và cờ isAuthenticated. **AnonymousAuthenticationToken** là representation dành cho người chưa đăng nhập, không phải kết quả kiểm tra password. Trong một số cấu hình, token anonymous báo isAuthenticated() là true vì semantics của token, nhưng quy tắc **authenticated()** của Spring Security vẫn **không coi anonymous là login thật**.

**Đừng tự viết:**

~~~java
// Sai nếu dùng riêng lẻ để quyết định caller đã đăng nhập:
if (authentication != null && authentication.isAuthenticated()) {
    return secretData;
}
~~~

Thay vào đó, dùng DSL **.authenticated()**, **hasRole(...)**, **hasAuthority(...)** hoặc AuthenticationTrustResolver phù hợp; kiểm tra owner/tenant ở service/repository. Không cần tạo anonymous Authentication đặc quyền để xử lý request thiếu credential.

### 3.2. Được xác thực chưa có nghĩa đủ quyền

Alice có ROLE_USER:

- GET /api/me yêu cầu authenticated → hợp lệ.
- GET /api/admin/report yêu cầu ROLE_ADMIN → bị từ chối (thường 403).
- GET /api/orders/42 yêu cầu authenticated → qua URL rule, **nhưng** service vẫn phải đảm bảo order 42 thuộc Alice hoặc Alice được phép đọc nó.

Nếu API chỉ dùng authenticated mà không kiểm tra bản ghi, đó có thể là lỗ hổng **IDOR/BOLA**. Mã status đúng không thể thay thế việc thiết kế authorization đúng.

## 4. Ma trận quyết định 401/403 trong REST API

Dùng bảng sau để dự đoán hành vi trước khi viết code:

| Tình huống | Xác thực | Kiểm tra quyền | Kết quả điển hình |
| --- | --- | --- | --- |
| GET public không có credential | Không cần | permitAll | 200 |
| GET protected không có credential | Không có danh tính hợp lệ | authenticated | **401**, Basic/Bearer challenge tùy scheme |
| GET protected sai password | Thất bại | Chưa đủ điều kiện authorization | **401** |
| GET protected dùng bearer token hết hạn | Token không hợp lệ | Chưa đủ điều kiện authorization | **401**, Bearer invalid_token theo cơ chế |
| GET protected có user hợp lệ | Thành công | authenticated | 200 |
| GET admin bằng user ROLE_USER | Thành công | hasRole ADMIN không đạt | **403** |
| GET admin bằng ROLE_ADMIN | Thành công | hasRole ADMIN đạt | 200 |
| GET endpoint denyAll khi đã login | Thành công | denyAll | **403** theo cấu hình Basic thông dụng |
| GET endpoint denyAll khi chưa login | Không hợp lệ/thiếu | denyAll | Có thể **401** khi entry point được dùng |
| POST thiếu CSRF với CSRF bật | Có thể đã login hoặc chưa | **CSRF filter** từ chối | Thường **403** — không nhất thiết lỗi role |
| OPTIONS preflight bị từ chối | Có thể không gửi credential | **CORS** | Status do CORS/security config, có thể 403/401 |
| GET bản ghi thuộc người khác | Có thể đã login | owner check từ chối | Có thể 403 hoặc 404 theo chính sách |
| URL không tồn tại | Không phải bản thân lỗi authentication | Routing | 404, nhưng security có thể chặn trước |
| Request sai HTTP method | Không phải bản thân lỗi authentication | Routing | 405, nhưng security có thể chặn trước |
| Cơ sở dữ liệu danh tính hỏng | Không thể xác minh vì lỗi hệ thống | Không được cấp quyền | 5xx/503 thích hợp, không phải 401 mặc định |
| Client gửi quá nhiều request | Vấn đề rate limiting | Không phải role | 429 nếu chính sách rate limit áp dụng |

**Không suy luận chỉ từ status:** 403 có thể do CSRF, CORS, rule URL, method security hay quyền đối tượng. 401 có thể do không gửi credential, sai password, token hết hạn hoặc authentication filter không hỗ trợ scheme mà client chọn. Chẩn đoán phải dựa trên luồng request, log đã lọc và test.

## 5. 401/403 phụ thuộc cơ chế xác thực

### 5.1. HTTP Basic

Client gửi header:

~~~http
Authorization: Basic <base64(username:password)>
~~~

Base64 **không phải mã hóa bảo mật**; chỉ gửi HTTP Basic qua **HTTPS** trong môi trường thật.

- Thiếu header trên endpoint protected → thường 401 với Basic challenge.
- Header chứa username/password sai → 401.
- Header hợp lệ nhưng thiếu ROLE_ADMIN → 403.
- Header hợp lệ và đủ quyền → 2xx theo nghiệp vụ.

Nếu muốn custom JSON mà vẫn tuân theo Basic, giữ:

~~~http
WWW-Authenticate: Basic realm="lesson-api"
~~~

Client HTTP biết phải gửi credential theo Basic. Trình duyệt có thể hiển thị hộp thoại đăng nhập khi gặp challenge; đây là hành vi client, không phải lý do để phá chuẩn HTTP.

### 5.2. Form login dùng cookie/session

Trong ứng dụng **formLogin()** dùng cho browser, một caller chưa đăng nhập mà vào URL cần bảo vệ thường được **chuyển hướng HTTP 302** tới trang đăng nhập, thay vì nhận JSON 401. Đăng nhập sai cũng có thể chuyển hướng về /login?error. Một user đã login nhưng thiếu quyền có thể nhận **403**.

Vì vậy đừng viết test “mọi request chưa đăng nhập luôn 401” cho ứng dụng có form login browser. Đối với REST API cần status JSON, chọn cơ chế hoặc entry point rõ ràng, và tách security chain giữa API/browser nếu cần.

**Lưu ý:** 302 là chiến lược UX của entry point trong cấu hình form login; không phải nguyên nghĩa HTTP 401 bị thay đổi. Các test phải bám cấu hình thực tế.

### 5.3. OAuth2 Resource Server với Bearer token

Bearer có challenge khác Basic:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Đối với token không hợp lệ/hết hạn, RFC 6750 mô tả thông tin **error="invalid_token"** đi kèm 401 khi thích hợp. Khi token hợp lệ nhưng không có scope cần thiết, **403 Forbidden** và thông tin **insufficient_scope** có thể được trả theo chuẩn OAuth2.

Ví dụ minh họa theo ngữ nghĩa Bearer:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Trong Bearer, **403 đôi khi cũng có WWW-Authenticate** với thông tin insufficient_scope; không áp dụng tuyệt đối quy tắc “chỉ 401 mới có WWW-Authenticate”. Ngược lại, khi chưa có token, Resource Server có thể chỉ trả WWW-Authenticate: Bearer mà không tiết lộ chi tiết lỗi.

**Điều cấm:** không hard-code Basic challenge cho một API chỉ chấp nhận Bearer token. Với Spring Security Resource Server, dùng các entry point/denied handler dành cho Bearer, giữ nguyên semantics issuer, signature, expiry, audience và scope mapping.

### 5.4. Nhiều SecurityWebFilterChain

Nếu một chain dành cho /api/** dùng Bearer và một chain khác dành cho browser dùng form login, **cùng tình trạng chưa đăng nhập** có thể cho kết quả 401 trên API nhưng 302 trên web. Đây là kết quả có chủ đích nếu đã cấu hình chính xác matcher và thứ tự.

Khi có nhiều chain, kiểm tra securityMatcher, @Order và cơ chế authentication/authorization của **chain thực sự chọn request**. Đừng gộp tất cả lỗi qua một entry point Basic toàn cục nếu có các giao thức khác.

## 6. API xử lý lỗi trong Spring Security Reactive

Các interface liên quan:

| API reactive | Khi được dùng | Kết quả |
| --- | --- | --- |
| **ServerAuthenticationEntryPoint** | Cần yêu cầu client xác thực | Mono<Void>, thường ghi 401/challenge |
| **ServerAccessDeniedHandler** | Đã xác thực nhưng không đáp ứng authorization, hoặc trường hợp từ chối khác | Mono<Void>, thường ghi 403 |
| **ServerAuthenticationFailureHandler** | Một lần thử authenticate thất bại ở AuthenticationWebFilter | Mono<Void>, có thể ủy quyền tới entry point |
| **ServerHttpSecurity.exceptionHandling(...)** | Đăng ký entry point/denied handler cho exception translation | Áp dụng với authorization errors |
| **ServerHttpSecurity.httpBasic(...)** | Cấu hình Basic filter, entry point, failure handler | Áp dụng với Basic credential |
| **ReactiveAuthenticationManager** | Xác minh Authentication input | Mono<Authentication> hoặc error |
| **SecurityWebFilterChain** | Chạy WebFilter và quy tắc bảo mật | Bảo vệ cả Controller và RouterFunction |

Đúng package của WebFlux:

~~~java
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.web.server.ServerWebExchange;
~~~

Không nhầm với servlet AuthenticationEntryPoint, AccessDeniedHandler, HttpServletRequest, HttpServletResponse hoặc HttpSecurity. Chúng có chữ ký và vòng đời khác.

### 6.1. AuthenticationEntryPoint

Signature chức năng:

~~~java
Mono<Void> commence(
        ServerWebExchange exchange,
        AuthenticationException exception);
~~~

Nhiệm vụ: khởi tạo phản hồi yêu cầu xác thực, thường đặt 401 và WWW-Authenticate phù hợp cơ chế Basic/Bearer. Không tự tạo Authentication được cấp quyền trong handler lỗi.

### 6.2. AccessDeniedHandler

Signature chức năng:

~~~java
Mono<Void> handle(
        ServerWebExchange exchange,
        AccessDeniedException denied);
~~~

Nhiệm vụ: ghi phản hồi từ chối truy cập khi authorization thất bại. Với user đã xác thực nhưng thiếu role/authority, thường ghi 403. Không biến nó thành 401 chỉ để client bật màn hình login nếu credential đã hợp lệ.

### 6.3. AuthenticationFailureHandler

Trong một filter xác thực cụ thể, failure handler có thể xử lý bad credentials và ủy quyền tới entry point. **ServerAuthenticationEntryPointFailureHandler** là adapter để dùng entry point trong luồng này. Lưu ý một **AuthenticationServiceException** có thể là lỗi hệ thống và cần xử lý khác với sai password, không nên bắt toàn bộ lỗi rồi tự động đổi thành 401 nếu điều đó giấu lỗi identity store.

### 6.4. Vì sao @RestControllerAdvice không đủ?

HTTP security filters xử lý request **trước khi controller được gọi**, nên exception do filters xử lý không nhất thiết đi qua @ExceptionHandler trong @RestControllerAdvice. Lỗi authentication/authorization nên được tùy chỉnh tại **SecurityWebFilterChain** hoặc handler phù hợp; controller advice xử lý lỗi nghiệp vụ, validation và các exception đi ra từ controller/service theo phạm vi được framework hỗ trợ.

Đừng đặt @ExceptionHandler(Exception.class) trả 403 cho mọi exception. Làm vậy biến NullPointerException, timeout và lỗi database thành “không có quyền”, che giấu sự cố server và làm sai metric.

### 6.5. Thiết kế JSON error contract

Một hợp đồng đơn giản:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "Authentication required"
}
~~~

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Access denied"
}
~~~

Các tiêu chí:

- Status vẫn là **401/403** thật, không trả 200 kèm error body.
- Content-Type đúng **application/json**, body encode UTF-8.
- Với Basic 401, phải có **WWW-Authenticate: Basic realm="..."**.
- Không trả raw exception message, password, Authorization header, cookie session, hash, JWT claims hoặc stack trace.
- Dùng mã code ổn định cho client; lời message có thể được địa phương hóa nhưng tránh làm lộ thông tin tài khoản.
- Có thể thêm requestId do server tạo/kiểm soát nếu cần correlation/audit.
- Đặt Cache-Control: no-store để tránh cache lỗi liên quan security.
- Nếu dùng application/problem+json, phải tuân thủ RFC 9457 Problem Details (type/title/status/detail/instance phù hợp) và test schema, không chỉ đổi header.

**Không sử dụng status 403 thay cho response cần 401 chỉ để che giấu việc authentication thất bại**, cũng không báo chính xác “username tồn tại nhưng password sai” cho client không đáng tin.

## 7. Demo Java 17+: HTTP Basic API phân biệt 401 và 403

Demo dùng **Spring Boot 3.5.16**, Java 17+ và Gradle 8.x tương thích. Bản 3.5.16 có sẵn ở Maven Central, nhưng đây là bản OSS cuối cùng của nhánh 3.5.x theo thông báo Spring Boot; khi triển khai mới production nên chọn một nhánh còn được cập nhật hoặc hỗ trợ thương mại thích hợp. Bài chọn 3.5.16 để mã mẫu dùng Spring Security 6.x và các API WebFlux phổ biến.

Mục tiêu quan sát:

| Request | Điều kiện | Kết quả |
| --- | --- | --- |
| GET /public/ping | Không cần login | 200 JSON |
| GET /api/me | Yêu cầu authenticated | 401 nếu thiếu/sai credential; 200 nếu đúng |
| GET /api/admin/report | ROLE_ADMIN | 403 cho ROLE_USER; 200 cho ROLE_ADMIN |
| GET /closed/feature | denyAll | 403 cho user đã đăng nhập |
| GET /unlisted | denyAll mặc định | 403 cho user đã đăng nhập |

Dữ liệu người dùng demo:

- alice / alice-pass: ROLE_USER.
- admin / admin-pass: ROLE_USER, ROLE_ADMIN.

**Cấu trúc file:**

~~~text
reactive-401-403/
├── settings.gradle
├── build.gradle
├── src/main/java/example/errors/ErrorsApplication.java
├── src/main/java/example/errors/SecurityConfig.java
├── src/main/java/example/errors/ApiController.java
└── src/test/java/example/errors/HttpErrorsTest.java
~~~

### 7.1. settings.gradle

~~~groovy
rootProject.name = 'reactive-401-403'
~~~

### 7.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý phiên bản Spring Framework/Security/Reactor qua dependency management; không tự ghim Spring Security không tương thích. Với dự án thật, nên tạo Gradle Wrapper để các thành viên dùng cùng bản Gradle.

### 7.3. ErrorsApplication.java

~~~java
package example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ErrorsApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — phân biệt entry point và denied handler

~~~java
package example.errors;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    private static final String CHALLENGE =
            "Basic realm=\"lesson-api\"";

    private static final String AUTHENTICATION_JSON =
            "{\"code\":\"AUTHENTICATION_REQUIRED\","
            + "\"message\":\"Authentication required\"}";

    private static final String AUTHORIZATION_JSON =
            "{\"code\":\"ACCESS_DENIED\","
            + "\"message\":\"Access denied\"}";

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }

    @Bean
    ServerAuthenticationEntryPoint jsonAuthenticationEntryPoint() {
        return (exchange, error) ->
                writeError(exchange,
                        HttpStatus.UNAUTHORIZED,
                        AUTHENTICATION_JSON,
                        true);
    }

    @Bean
    ServerAccessDeniedHandler jsonAccessDeniedHandler() {
        return (exchange, error) ->
                writeError(exchange,
                        HttpStatus.FORBIDDEN,
                        AUTHORIZATION_JSON,
                        false);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerAuthenticationEntryPoint jsonAuthenticationEntryPoint,
            ServerAccessDeniedHandler jsonAccessDeniedHandler) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .pathMatchers("/closed/**").denyAll()
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic
                        .authenticationEntryPoint(
                                jsonAuthenticationEntryPoint))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                                jsonAuthenticationEntryPoint)
                        .accessDeniedHandler(
                                jsonAccessDeniedHandler))
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    private static Mono<Void> writeError(
            ServerWebExchange exchange,
            HttpStatus status,
            String json,
            boolean challenge) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);

        HttpHeaders headers = response.getHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (challenge) {
            headers.set(HttpHeaders.WWW_AUTHENTICATE, CHALLENGE);
        }

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        headers.setContentLength(bytes.length);

        return response.writeWith(Mono.just(
                response.bufferFactory().wrap(bytes)));
    }
}
~~~

**Lưu ý kỹ thuật:**

1. **jsonAuthenticationEntryPoint** trả 401, Basic challenge và JSON an toàn.
2. **jsonAccessDeniedHandler** trả 403, JSON khác; không tự thêm Basic challenge cho user thiếu role.
3. **httpBasic.authenticationEntryPoint(...)** xử lý luồng HTTP Basic cần phản hồi yêu cầu xác thực.
4. **exceptionHandling.authenticationEntryPoint(...)** xử lý lúc authorization yêu cầu login nhưng caller chưa có danh tính phù hợp.
5. **exceptionHandling.accessDeniedHandler(...)** xử lý thiếu quyền đối với request đã có authentication.
6. **Rule cụ thể /api/admin/** đặt trước /api/**, nếu đảo thứ tự user thường có thể đi qua rule rộng.
7. **anyExchange().denyAll()** không mở nhầm URL chưa được liệt kê.
8. **writeError** trả Mono<Void> và ghi data buffer qua ServerHttpResponse reactive. Không gọi block() hoặc subscribe() thủ công.
9. Dữ liệu JSON cố định nên không cần escape biến động; khi cần hiển thị requestId hoặc metadata từ input, dùng serializer JSON chuẩn và lọc dữ liệu.
10. Demo chỉ dùng GET, giữ mặc định CSRF. Nếu bổ sung POST, phải xử lý CSRF đúng mô hình client, không vô hiệu hóa chỉ để test dễ hơn.

**Bảo mật mật khẩu:** password trong source chỉ là fixture học tập; hash bằng BCrypt khi tạo UserDetails. Đừng dùng mật khẩu cố định, username nhạy cảm hoặc HTTP không TLS trong production. Không trả nguyên Authentication/UserDetails ra client.

### 7.5. ApiController.java

~~~java
package example.errors;

import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p ->
                Map.of("username", p.getName()));
    }

    @GetMapping("/api/admin/report")
    public Mono<Map<String, String>> report() {
        return Mono.just(Map.of("report", "ok"));
    }

    @GetMapping("/closed/feature")
    public Mono<Map<String, String>> disabled() {
        return Mono.just(Map.of("feature", "hidden"));
    }
}
~~~

Controller không tự kiểm tra password hay quyền; các rule URL đã chặn request không hợp lệ trước khi handler trả dữ liệu. Đối với API thực tế có data theo user, service vẫn cần kiểm tra quyền sở hữu record.

### 7.6. Chạy ứng dụng

Ở thư mục reactive-401-403, cần JDK 17+ và Gradle 8.x tương thích:

~~~bash
gradle bootRun
~~~

Ứng dụng sẽ dùng cổng 8080 theo cấu hình mặc định của Spring Boot nếu không bị override. Trong môi trường localhost có thể thử qua HTTP; production phải dùng HTTPS để bảo vệ Basic credential.

## 8. Quan sát bằng curl

Ở terminal Bash khác, thử:

~~~bash
# 1. Công khai: không cần login.
curl -i http://localhost:8080/public/ping

# 2. Chưa có credential, endpoint protected.
curl -i http://localhost:8080/api/me

# 3. Có Basic credential sai.
curl -i -u alice:wrong-pass http://localhost:8080/api/me

# 4. Có username không tồn tại.
curl -i -u unknown:some-pass http://localhost:8080/api/me

# 5. Đã đăng nhập đúng, được vào profile.
curl -i -u alice:alice-pass http://localhost:8080/api/me

# 6. Đăng nhập đúng nhưng thiếu ROLE_ADMIN.
curl -i -u alice:alice-pass http://localhost:8080/api/admin/report

# 7. Đủ ROLE_ADMIN.
curl -i -u admin:admin-pass http://localhost:8080/api/admin/report

# 8. DenyAll: ngay cả admin cũng không vào được.
curl -i -u admin:admin-pass http://localhost:8080/closed/feature

# 9. Route chưa liệt kê: bị default deny.
curl -i -u admin:admin-pass http://localhost:8080/unlisted
~~~

**Các HTTP response đại diện dưới đây là kết quả dự kiến của demo, không phải log thực nghiệm của một server đã được chạy.** Header do Netty/proxy thêm có thể khác; thứ tự property JSON không phải hợp đồng.

**Chưa có credential hoặc credential sai:**

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="lesson-api"
Content-Type: application/json
Cache-Control: no-store

{"code":"AUTHENTICATION_REQUIRED","message":"Authentication required"}
~~~

**Alice đăng nhập đúng:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"username":"alice"}
~~~

**Alice thiếu role admin:**

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json
Cache-Control: no-store

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

**Admin hợp lệ:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"report":"ok"}
~~~

**Admin vào endpoint denyAll:**

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"ACCESS_DENIED","message":"Access denied"}
~~~

Nếu cùng một URL dùng form login, status có thể khác (đặc biệt 302 redirect). Nếu đặt API sau gateway hoặc đổi ExceptionHandlingSpec/HttpBasicSpec, phải cập nhật kỳ vọng theo hợp đồng thật, không sao chép máy móc bảng này.

### 8.1. Ma trận kết quả cho demo

| Request | Xác thực | Quyền | Dự kiến |
| --- | --- | --- | --- |
| /public/ping không header | Không yêu cầu | permitAll | 200 |
| /api/me không header | Thiếu | authenticated | **401** + Basic challenge |
| /api/me sai password | Thất bại | Không có danh tính hợp lệ | **401** + Basic challenge |
| /api/me username không tồn tại | Thất bại | Không có danh tính hợp lệ | **401**, không lộ username |
| /api/me với alice | Thành công ROLE_USER | authenticated | 200 |
| /api/admin/report với alice | Thành công ROLE_USER | Thiếu ROLE_ADMIN | **403** |
| /api/admin/report với admin | Thành công ROLE_ADMIN | Có ROLE_ADMIN | 200 |
| /closed/feature với admin | Thành công ROLE_ADMIN | denyAll | **403** |
| /unlisted với admin | Thành công ROLE_ADMIN | default denyAll | **403** |

Trên Windows PowerShell, dùng **curl.exe** thay vì alias curl và nhập các lệnh trên một dòng. Có thể thêm tham số -v hoặc -i để xem WWW-Authenticate; tránh sao chép Authorization/cookie thật từ log ra tài liệu công khai.

## 9. Kiểm thử tích hợp bằng WebTestClient

Kiểm thử quan trọng nhất là request **thực sự đi qua WebFilter**, vì unit test gọi thẳng controller không kích hoạt authentication và authorization.

Tệp **src/test/java/example/errors/HttpErrorsTest.java**:

~~~java
package example.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HttpErrorsTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsAccessibleWithoutAuthentication() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingCredentialsProduces401ChallengeAndJson() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"lesson-api\"")
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectHeader().valueEquals(
                        HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED")
                .jsonPath("$.message")
                .isEqualTo("Authentication required");
    }

    @Test
    void invalidPasswordProduces401Not403() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(
                        HttpHeaders.WWW_AUTHENTICATE,
                        "Basic realm=\"lesson-api\"")
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void unknownUsernameDoesNotRevealAccountExistence() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("unknown", "some-pass"))
                .exchange()
                .expectStatus().isUnauthorized()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("AUTHENTICATION_REQUIRED");
    }

    @Test
    void validCredentialsAllowProfile() {
        client.get().uri("/api/me")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice");
    }

    @Test
    void loggedInUserWithoutAdminRoleGets403() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.WWW_AUTHENTICATE)
                .expectHeader().contentType(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
                .jsonPath("$.message").isEqualTo("Access denied");
    }

    @Test
    void adminCanReadReport() {
        client.get().uri("/api/admin/report")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.report").isEqualTo("ok");
    }

    @Test
    void denyAllRejectsEvenAdmin() {
        client.get().uri("/closed/feature")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden()
                .expectBody()
                .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void unlistedRouteIsNotAutomaticallyPublic() {
        client.get().uri("/unlisted")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Chạy bằng:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** 9 test PASS, Gradle kết thúc với **BUILD SUCCESSFUL** nếu môi trường và dependencies được cấu hình đúng. Test dùng RANDOM_PORT và WebTestClient do Spring Boot cấu hình, không cần tự chạy server demo ở cổng 8080.

### 9.1. Ba assertion quan trọng nhất

1. **401 thiếu credential** phải mang WWW-Authenticate; không chỉ test status.
2. **401 sai credential** phải giống lỗi thiếu credential ở contract công khai, không tiết lộ username tồn tại.
3. **403 thiếu quyền** phải xảy ra khi Authentication đã thành công; không thay bằng 401 và không trả dữ liệu admin.

Cần thêm test cho method security, CSRF, owner check, gateway và multi-chain nếu sản phẩm thực tế có chúng; demo chỉ kiểm tra URL authorization.

### 9.2. Test không được bỏ qua auth filters

Sai cách:

~~~java
// Minh họa khái niệm: gọi controller trực tiếp bỏ qua WebFilter.
ApiController controller = new ApiController();
controller.report().subscribe();
~~~

Đoạn này không kiểm tra policy /api/admin/report, và subscribe thủ công không phù hợp cho unit test phản hồi HTTP. Nếu cần test Reactor publisher độc lập, dùng **StepVerifier**; nếu cần test 401/403, dùng **WebTestClient** qua SecurityWebFilterChain.

### 9.3. Cần test cả hai đối tượng và trạng thái khác nhau

Trong dự án nhiều role, cần ít nhất user chưa login, sai credential, ROLE_USER và ROLE_ADMIN. Test một endpoint chỉ với admin thành công **không chứng minh** ROLE_USER sẽ bị chặn. Tương tự, endpoint chỉ test thiếu cookie mà không thử cookie hợp lệ thiếu quyền có thể không phân biệt được 401 với 403.

## 10. Những tình huống đặc biệt dễ nhầm

### 10.1. 403 do CSRF, không phải thiếu role

Trong web app dùng cookie/session, CSRF protection thường áp dụng cho các method không an toàn như POST, PUT, PATCH, DELETE. Nếu POST /api/orders thiếu token CSRF, WebFilter có thể từ chối **403 dù Authentication và role đúng**.

Do đó, khi debug:

- Kiểm tra method và CSRF đã bật chưa.
- Kiểm tra request có CSRF token đúng kiểu (form field/header) và cookie/session tương ứng chưa.
- Nếu test role ở POST, cần thỏa cả CSRF hoặc cấu hình CSRF theo kiến trúc phù hợp.
- Không tắt CSRF toàn hệ thống chỉ để làm test authorization pass.

Ví dụ matrix:

| Request | Credential | CSRF | Role | Kết quả có thể |
| --- | --- | --- | --- | --- |
| POST /orders | Hợp lệ | Thiếu | Đúng | 403 do CSRF |
| POST /orders | Hợp lệ | Đúng | Thiếu | 403 do authorization |
| POST /orders | Hợp lệ | Đúng | Đúng | 2xx theo nghiệp vụ |
| POST /orders | Thiếu | Thiếu | Không rõ | Có thể bị CSRF từ chối trước authn |

Không nên suy luận nguyên nhân chỉ từ status; log an toàn/metric và test biến từng yếu tố giúp xác định filter nào trả lỗi.

### 10.2. CORS preflight và trình duyệt

Một preflight OPTIONS có thể không chứa credential. Nếu CORS configuration bị thiếu hoặc filter order không đúng, request có thể bị chặn với 401/403 và frontend hiển thị “CORS error”. Đây không nhất thiết là user thiếu role.

Giải pháp là cấu hình CORS cho trusted origins, methods, allowed headers và credential policy phù hợp; xử lý preflight đúng thứ tự, không mở public dữ liệu nhạy cảm chỉ để cho OPTIONS đi qua. Dùng curl so sánh với browser Network để tách lỗi CORS và lỗi authentication.

### 10.3. Form login redirect khác HTTP status REST

Form login có thể trả 302 tới /login khi caller chưa xác thực, còn API HTTP Basic/Bearer thường trả 401. Không dùng test REST mặc định để áp đặt 401 cho trang web browser nếu không đổi entry point.

Một ứng dụng hybrid có thể tách SecurityWebFilterChain theo matcher; cần test riêng behavior cho /api/** và /web/**. Đừng đưa Basic challenge lên form login HTML không chủ đích.

### 10.4. 401 không có nghĩa luôn được refresh token

Client chỉ nên refresh access token khi authentication mechanism và error contract cho thấy token hết hạn/lỗi có thể khắc phục bằng refresh. Với sai Basic password, gọi refresh vô hạn là sai. Với Bearer insufficient_scope (403), refresh cùng scope thường không giải quyết thiếu quyền.

Giới hạn số lần retry, tránh login/refresh loop, và phân biệt lỗi hệ thống 5xx với invalid credential 401.

### 10.5. 404 và 405 có thể bị security chặn trước

Một request đến URL không có handler nhưng bị anyExchange().denyAll() có thể nhận 401/403 trước khi DispatcherHandler biết rằng URL không tồn tại. Do đó status 403 không chứng minh controller/service đã chạy, và status 404 không chứng minh URL có policy đúng.

Khi kiểm thử security, dùng **endpoint thực sự tồn tại**, với nhiều danh tính; test unknown path là một bài kiểm tra fail-closed riêng.

### 10.6. DenyAll và người chưa xác thực

Rule **denyAll()** từ chối cả user chưa login lẫn admin. Nhưng hệ thống exception translation có thể trả 401 cho người chưa xác thực và 403 cho người đã login. Không nên viết “denyAll luôn trả 403” như một luật bất biến.

### 10.7. Quyền theo object

Ví dụ Alice yêu cầu GET /api/orders/42, nhưng đơn hàng 42 thuộc Bob. Tùy policy, service có thể trả **403** hoặc **404 để che sự tồn tại**. Dù dùng status nào, không được trả dữ liệu của Bob cho Alice.

Mẫu minh họa:

~~~java
// Minh họa tích hợp; OrderDto/repository do ứng dụng cung cấp.
public Mono<OrderDto> getOrder(String orderId, String verifiedUserId) {
    return repository.findByIdAndOwnerId(orderId, verifiedUserId);
}
~~~

verifiedUserId phải lấy từ Authentication/subject đã được xác minh. Không đọc username trong query parameter rồi tin rằng client là chủ tài nguyên.

### 10.8. Lỗi xác thực do hạ tầng

Nếu identity database timeout, manager không biết password đúng hay sai vì không truy xuất được account. Đừng biến mọi lỗi nội bộ thành 401; điều đó khiến client cố nhập lại mật khẩu, che giấu sự cố vận hành. Nên fail closed và trả 5xx/503 thích hợp theo contract, đồng thời ghi metric nội bộ có kiểm soát.

## 11. Checklist để triển khai API thực tế

**Thiết kế status và challenge:**

1. Viết ma trận endpoint: public, authenticated, role/scope, owner/tenant.
2. Chọn authentication mechanism rõ ràng: Basic, cookie form login, JWT/Bearer, mTLS hoặc cơ chế khác.
3. Khi trả 401, cung cấp **WWW-Authenticate** phù hợp scheme (RFC 9110).
4. Với Basic, realm là chuỗi tĩnh do server kiểm soát; với Bearer, giữ error semantics phù hợp RFC 6750.
5. Trả 403 cho caller đã xác thực nhưng thiếu quyền theo policy.
6. Không biến mọi exception thành 401/403; để lỗi hệ thống và validation có status thích hợp.
7. Không cache lỗi liên quan bảo mật nếu hợp đồng chứa thông tin nhạy cảm.
8. Không xuất token/password/hash/stack trace trong JSON hoặc log.
9. Kiểm tra URL rules theo thứ tự cụ thể trước rộng; kết thúc deny-by-default nếu phù hợp.
10. Giữ method security và owner/tenant checks độc lập với status ở URL.
11. Khi dùng nhiều chain, kiểm tra securityMatcher/@Order, entry point và authentication scheme tương ứng.
12. Với browser/cookie, test CSRF và CORS; với API stateless, đánh giá dựa trên threat model thật.
13. Test thiếu credential, sai credential, đúng credential thiếu quyền, đủ quyền và đường không công bố.
14. Test behavior qua gateway/proxy nếu proxy có rewrite/auth/filter riêng.

**Giám sát:**

- Ghi endpoint template, category như AUTHN_FAILURE/AUTHZ_DENIED/CSRF_DENIED, mã status và correlation ID nếu có.
- Chỉ ghi actor/subject đã được xác minh khi phù hợp; không log raw Authorization header hoặc toàn bộ principal.
- Giới hạn rate login/password attempts và theo dõi bất thường, không trả khác biệt hữu ích cho user enumeration.
- Đối với bất thường tỷ lệ 401/403, tách theo loại client, scheme và URL trước khi kết luận người dùng nhập sai password.

## 12. Bài tập thực hành

1. GET /api/me thiếu Authorization Basic nhận status nào và cần header nào?
2. GET /api/me gửi password sai có được coi là “đã đăng nhập nhưng thiếu quyền” không?
3. Alice ROLE_USER gọi GET /api/admin/report thì 401 hay 403 trong demo? Tại sao?
4. Admin gọi /closed/feature bị denyAll; status nào dự kiến với demo?
5. Nếu POST /api/orders của Admin trả 403 khi CSRF bật, có thể kết luận Admin thiếu ROLE_ORDER_WRITE không?
6. Với form login browser, vì sao request chưa login có thể trả 302 thay cho 401?
7. Bearer token hết hạn và bearer token hợp lệ nhưng thiếu scope khác nhau thế nào?
8. WWW-Authenticate có bắt buộc trên 401 theo RFC 9110 không? Có nên dùng Basic challenge cho Bearer API không?
9. Khi chỉ sửa ServerAccessDeniedHandler, vì sao nhánh sai password có thể vẫn dùng body lỗi mặc định?
10. Tại sao @RestControllerAdvice không luôn bắt được AuthenticationException trong SecurityWebFilterChain?
11. Khi một route chưa tồn tại nhưng policy denyAll, 403 có chứng minh handler đã chạy không?
12. Test nào nên được thêm để phát hiện Basic username không tồn tại bị lộ trong message?
13. Tại sao trả 200 kèm {"error":true} không thay được 401/403?
14. Với tài nguyên do Bob sở hữu, Alice đã đăng nhập có thể đọc không nếu URL chỉ có authenticated()?
15. Lỗi identity store timeout có được trả 401 mặc định không?

**Đáp án gợi ý:** (1) 401 và WWW-Authenticate: Basic realm; (2) không, authentication chưa hợp lệ; (3) 403 vì đã login nhưng không có ROLE_ADMIN; (4) 403 khi admin đã xác thực; (5) không, CSRF có thể chặn trước; (6) entry point của form login chuyển hướng; (7) invalid_token thường 401, insufficient_scope thường 403; (8) cần challenge thích hợp, không dùng sai scheme; (9) credential sai được xử lý ở authentication filter/entry point chứ không nhất thiết là denied handler; (10) security filter chạy trước controller; (11) không; (12) so sánh code/message public của unknown username với wrong password; (13) làm sai semantics HTTP, client/proxy/observability; (14) không mặc nhiên, phải kiểm tra owner; (15) không, lỗi hạ tầng cần xử lý 5xx/503 và fail closed.

## 13. Tài liệu đối chiếu

- RFC 9110 — HTTP Semantics, 401 Unauthorized và 403 Forbidden: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 7617 — The Basic HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
- Spring Security Javadoc — ServerHttpSecurity.HttpBasicSpec: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HttpBasicSpec.html
- Spring Security Javadoc — ServerHttpSecurity.ExceptionHandlingSpec: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.ExceptionHandlingSpec.html
- Spring Security Javadoc — ServerAuthenticationEntryPoint: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/ServerAuthenticationEntryPoint.html
- Spring Security Javadoc — ServerAccessDeniedHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authorization/ServerAccessDeniedHandler.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Boot 3.5.16 Release: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** Trong Spring Security Reactive, **401** thường phát sinh khi request thiếu hoặc không có credential hợp lệ và cần một **authentication challenge** đúng scheme; **403** thường phát sinh khi caller đã xác thực nhưng bị **authorization** từ chối. Đừng chỉ nhìn tên Unauthorized/Forbidden: kiểm tra filter, authentication mechanism, rule URL, role/scope, CSRF/CORS và quyền theo tài nguyên. Dùng **ServerAuthenticationEntryPoint** cho 401, **ServerAccessDeniedHandler** cho 403, trả JSON an toàn và kiểm thử cả hai luồng với WebTestClient.