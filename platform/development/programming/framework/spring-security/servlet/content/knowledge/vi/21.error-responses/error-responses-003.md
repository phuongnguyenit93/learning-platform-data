# AccessDeniedHandler khi danh tính không đáp ứng quyền truy cập — Spring Security Servlet

## 1. Vấn đề: đã biết người gọi là ai nhưng vẫn không được phép

Một API thường bảo vệ tài nguyên bằng những quy tắc như `hasRole("ADMIN")`, `hasAuthority("reports:read")` hoặc một chính sách sở hữu tài liệu trong `@PreAuthorize`. Một người dùng có thể **đăng nhập thành công**, nhưng không có quyền thực hiện thao tác cụ thể. Với Spring Security Servlet, đây là tình huống **authorization denied** và thường được phản hồi bằng HTTP **403 Forbidden**.

Ví dụ:

```text
alice đăng nhập với ROLE_USER
    |
GET /api/admin/reports
    |
Authentication hợp lệ: alice / ROLE_USER
    |
Quy tắc cần ROLE_ADMIN
    |
AccessDeniedException
    |
ExceptionTranslationFilter -> AccessDeniedHandler
    |
403 Forbidden
```

Giao diện hoặc API cần trả một phản hồi **an toàn, nhất quán và hữu ích**. Không chỉ chặn truy cập: phải tránh tiết lộ thông tin nội bộ và giúp client hiểu rằng đổi mật khẩu hoặc đăng nhập lại không nhất thiết giải quyết được vấn đề **thiếu quyền**.

Trong Spring Security Servlet, hợp đồng chuyên trách cho tình huống này là interface `AccessDeniedHandler`. Nó khác với `AuthenticationEntryPoint`, vốn phụ trách khởi đầu quá trình xác thực khi người gọi chưa có mức authentication cần thiết.

Bài học thuộc nhóm **Phản hồi lỗi** và tập trung vào đúng đề bài: **AccessDeniedHandler khi danh tính không đáp ứng quyền truy cập**. Nội dung giải thích chuỗi filter, điều kiện được gọi, sự khác nhau giữa 401 và 403, cấu hình hiện đại với `SecurityFilterChain`, API JSON, HTML page, kiểm thử MockMvc và các lỗi triển khai thường gặp.

Phạm vi là **Spring Security Servlet / Spring MVC**, phổ biến ở Spring Security 6.x, Java 17+. Ví dụ sử dụng **Spring Boot 3.3.5** làm mốc học tập nhất quán, **không khẳng định là bản mới nhất hoặc còn trong vòng hỗ trợ** tại thời điểm đọc. Với dự án thực, phải đối chiếu API và chọn phiên bản có cập nhật bảo mật phù hợp.

## 2. Phân biệt authentication và authorization trước khi viết handler

**Authentication (xác thực)** xác định danh tính người gọi. Ví dụ, `BasicAuthenticationFilter` nhận HTTP Basic credentials; `UsernamePasswordAuthenticationFilter` kiểm tra đăng nhập bằng form; resource server kiểm tra Bearer token. Nếu xác thực thành công, framework đặt đối tượng `Authentication` vào `SecurityContextHolder` cho request theo cơ chế tương ứng.

**Authorization (phân quyền)** quyết định người gọi đó được vào URL hay method/nghiệp vụ nào. Ví dụ:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated())
```

Đây là một mảnh cấu hình `HttpSecurity`, không phải file Java chạy riêng. Với người dùng `alice` đã có `ROLE_USER` nhưng không có `ROLE_ADMIN`, `GET /api/admin/reports` bị từ chối bởi authorization. Lúc này, nếu authentication được coi là đủ tin cậy cho quyết định phân biệt danh tính, `AccessDeniedHandler` là nơi trả 403.

Ngược lại, nếu request **chưa có authentication**, hoặc chỉ có authentication quá yếu so với yêu cầu, Spring Security có thể bắt đầu lại flow đăng nhập qua `AuthenticationEntryPoint`. Vì vậy, **không được nói mọi AccessDeniedException đều chắc chắn gọi AccessDeniedHandler**: việc lựa chọn còn phụ thuộc trạng thái anonymous/remember-me và cách framework phân loại authentication.

| Tình huống | Điểm chính | Phản hồi thường gặp |
|---|---|---|
| Không có credentials, URL cần đăng nhập | Chưa authenticated | `AuthenticationEntryPoint` → 401 Basic challenge hoặc redirect form login |
| Credentials sai / token không hợp lệ | Authentication thất bại | Authentication filter/entry point → thường 401 |
| Đã xác thực, thiếu `ROLE_ADMIN` | Authorization bị từ chối | `AccessDeniedHandler` → thường 403 |
| Đã login bằng remember-me, endpoint yêu cầu `fullyAuthenticated()` | Mức authentication chưa đủ | Có thể commence lại authentication thay vì trả 403 thường |
| Đã xác thực, thiếu quyền theo `@PreAuthorize` | Method security từ chối | Thường 403 qua exception translation, nếu exception lan ra đúng chain |
| POST thiếu CSRF token | CSRF protection từ chối request | Thường 403, nhưng **không mặc định handler tùy biến trong exceptionHandling được gọi** |
| Controller tự throw lỗi nghiệp vụ | MVC xử lý exception theo kiến trúc ứng dụng | Không phải mọi lỗi đều đi qua `AccessDeniedHandler` |

**401 không có nghĩa “user đã đăng nhập nhưng không đủ quyền”.** Với HTTP Basic và Bearer, 401 thường cho biết cần xác thực hoặc xác thực không thành công. **403 thường cho biết thông tin định danh đang dùng không được phép cho hành động cụ thể**. Form login có thể dùng redirect thay cho 401; quy tắc status cần thiết kế theo client và authentication mechanism.

## 3. AccessDeniedHandler nằm ở đâu trong SecurityFilterChain?

Spring Security Servlet dùng `FilterChainProxy` để thực thi một `SecurityFilterChain` phù hợp với request. Các filter khác nhau chịu trách nhiệm nạp security context, xác thực, CSRF, xử lý exception và phân quyền.

Luồng rút gọn với một request bị thiếu role:

```text
GET /api/reports/42
   |
Servlet FilterChain -> FilterChainProxy
   |
SecurityContext / Authentication filters
   |
ExceptionTranslationFilter
   |  try {
   |      downstream filters
   |        |
   |        +-- AuthorizationFilter
   |               |
   |               +-- hasRole('ADMIN') = false
   |               +-- AccessDeniedException
   |  } catch (AccessDeniedException) {
   |      kiểm tra trạng thái authentication
   |      nếu cần xác thực -> AuthenticationEntryPoint
   |      nếu đã xác thực nhưng thiếu quyền -> AccessDeniedHandler
   |  }
   |
HTTP 403 và body/redirect/forward tùy handler
```

**`ExceptionTranslationFilter` không phải authorization engine**. Nó dịch một số exception bảo mật (như `AuthenticationException` hoặc `AccessDeniedException`) từ phần downstream thành HTTP response/khởi đầu authentication phù hợp. Tùy request, nó có thể xóa SecurityContext, lưu request để phục hồi sau login hoặc gọi authentication entry point. Với người dùng đã xác thực đầy đủ nhưng thiếu quyền, nó ủy quyền cho `AccessDeniedHandler`.

### Interface AccessDeniedHandler

Contract trọng tâm:

```java
public interface AccessDeniedHandler {
    void handle(
        HttpServletRequest request,
        HttpServletResponse response,
        AccessDeniedException accessDeniedException
    ) throws IOException, ServletException;
}
```

Đây là chữ ký minh họa tương ứng với Servlet API trên Spring Security 6/Jakarta Servlet. Khi implement class thực, import interface từ `org.springframework.security.web.access.AccessDeniedHandler`, exception từ `org.springframework.security.access.AccessDeniedException`, Servlet classes từ `jakarta.servlet.*`.

Ba đối số:

- `request` chứa method, URI, attributes, security context và thông tin request cần thiết.
- `response` cho phép đặt status code, content type, headers, body hoặc chuyển trang.
- `accessDeniedException` mô tả sự kiện từ chối. **Thông điệp exception có thể chứa chi tiết framework/chính sách; không gửi nguyên `getMessage()` cho client trong production.**

Handler là **điểm trả phản hồi**, không phải nơi sửa quyền. Nó không nên thêm `ROLE_ADMIN`, xóa `SecurityContext` để “qua được request”, hoặc chạy lại controller bằng một danh tính khác. Việc user có quyền nào phải được quyết định trước tại authorization layer.

## 4. AccessDeniedHandler mặc định và các phương án trả phản hồi

### 4.1. AccessDeniedHandlerImpl

Spring Security có implementation `AccessDeniedHandlerImpl`. Theo cách cấu hình, nó có thể gửi status `403`, hoặc forward đến một error page đã xác định.

Ví dụ sử dụng một đường dẫn error page:

```java
http.exceptionHandling(ex -> ex
    .accessDeniedPage("/access-denied"));
```

Đây là mảnh cấu hình, không phải toàn bộ application. Khi forward nội bộ đến error page, request vẫn thuộc cùng quá trình xử lý phía server; **không tự coi forward là một redirect mới từ browser**. Cần bảo đảm endpoint error page có mapping và security policy thích hợp để tránh lỗi vòng lặp hoặc bị chặn ngay lần forward.

Điểm thiết kế với web HTML:

- Trang thông báo nên dùng ngôn ngữ dễ hiểu, ví dụ “Bạn không có quyền thực hiện thao tác này”.
- Không tiết lộ tên quyền nội bộ, object IDs của tenant khác hoặc thông tin nhạy cảm từ exception.
- Không thêm một rule `permitAll("/**")` chỉ để error page hiển thị.
- Nếu hiển thị đường dẫn hoặc tham số do user cung cấp, phải encode output để tránh XSS.
- Kiểm thử cả dispatcher type `FORWARD`/`ERROR` nếu hệ thống sử dụng và Spring Security filter mapping có áp dụng.
- Đừng dùng error page đơn lẻ để giải quyết yêu cầu API JSON; HTML và REST client có hợp đồng phản hồi khác nhau.

### 4.2. HttpStatusAccessDeniedHandler

Một số API chỉ cần status 403 không có body; `HttpStatusAccessDeniedHandler` hoặc handler tự viết có thể dùng khi phù hợp phiên bản. Đối với API nội bộ có client chuyên biệt, body machine-readable sẽ tiện hơn.

Ưu điểm của status-only response là ít tiết lộ thông tin. Nhược điểm là client khó phân biệt lỗi thiếu quyền và lỗi khác có status 403 nếu không có một hợp đồng response rõ.

### 4.3. Custom JSON AccessDeniedHandler

REST API thường muốn response tương tự:

```json
{
  "status": 403,
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền truy cập tài nguyên này",
  "path": "/api/reports/42"
}
```

Dữ liệu mẫu cố ý không có password, session ID, bearer token, raw authorities, stack trace hoặc exception class. `path` chỉ là URI path và vẫn có thể nhạy cảm: nếu URL nhúng thông tin nhận dạng, cần loại bỏ hoặc thay bằng template an toàn theo policy.

Các quyết định implementation:

1. Đặt đúng **status 403**, không trả HTTP 200 rồi ghi `"status":403` trong body.
2. Đặt `Content-Type: application/json` và encoding UTF-8, dùng Jackson/ObjectMapper để serialize đúng.
3. Đặt `Cache-Control: no-store` cho response lỗi nhạy cảm khi phù hợp.
4. Trả một **mã lỗi ổn định** cho client, không đưa message framework nguyên văn ra ngoài.
5. Không gọi `response.sendRedirect("/login")` cho user đã đăng nhập nhưng thiếu quyền nếu API contract cần 403.
6. Không ghi body nếu response đã committed; vì header/status không thể thay đổi đáng tin sau khi đã gửi bytes.
7. Nếu có logging/audit, ghi tối thiểu thông tin xác thực đã được chuẩn hóa và correlation ID, không log raw Authorization/Cookie headers.

**Bảo mật không đến từ việc JSON có đẹp hay không.** Handler chỉ làm response nhất quán; authorization policy trước đó vẫn phải đúng.

## 5. AuthenticationEntryPoint khác AccessDeniedHandler

Hai extension points thường nằm cạnh nhau trong `exceptionHandling`:

```java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(customEntryPoint)
    .accessDeniedHandler(customAccessDeniedHandler));
```

Đây là mảnh code; `customEntryPoint` và `customAccessDeniedHandler` phải là beans/objects có định nghĩa, không phải biến có sẵn.

- `AuthenticationEntryPoint` bắt đầu authentication cho người gọi chưa đủ mức xác thực. Với API Basic, ví dụ là 401 cùng header `WWW-Authenticate`. Với web form, có thể redirect login.
- `AccessDeniedHandler` xử lý việc người dùng đã có authentication phù hợp nhưng thiếu authorization. Thông thường trả 403.

**Không dùng một custom AccessDeniedHandler để “đồng nhất” tất cả lỗi auth thành 403**, bởi 401 còn quan trọng đối với client authentication protocol. Nếu muốn cả 401 và 403 đều trả JSON, hãy tạo **hai** component phù hợp và bảo toàn semantics của từng authentication mechanism.

### Anonymous và remember-me là hai tình huống đặc biệt

Ở một URL yêu cầu `authenticated()`, anonymous authentication không được coi là người dùng hợp lệ. Nếu authorization từ chối, `ExceptionTranslationFilter` có thể nhận thấy anonymous và gọi `AuthenticationEntryPoint`.

Với `RememberMeAuthenticationToken`, biểu thức `fullyAuthenticated()` đòi mức xác thực cao hơn remember-me; framework có thể bắt đầu flow xác thực lại. Vì thế không viết test cứng “mỗi AccessDeniedException luôn nhận 403 JSON do custom handler” mà bỏ qua loại Authentication thực tế.

### Đổi mật khẩu và thay role

Nếu user đã đăng nhập, rồi bị hạ role trong database, Authentication trong server-side session có thể còn authorities cũ. `AccessDeniedHandler` **không tự kiểm tra lại role trong database**; nó chỉ phản hồi khi authorization engine đã từ chối. Để giảm quyền có hiệu lực trên session cũ, cần thêm session revocation, security version hoặc per-request permission revalidation. Không kỳ vọng thay đổi message 403 sẽ đóng lỗ hổng stale authorities.

## 6. @PreAuthorize cũng có thể dẫn đến AccessDeniedHandler

Ở tầng service:

```java
@PreAuthorize("hasRole('ADMIN')")
public String sensitiveReport() {
    return "SENSITIVE";
}
```

Nếu `@EnableMethodSecurity` được bật, method được gọi **qua Spring-managed proxy**, và một user đã xác thực nhưng thiếu ROLE_ADMIN gọi method, method-security interceptor có thể ném `AccessDeniedException` (hoặc subtype thích hợp).

Khi exception đó **lan ra khỏi MVC/controller** theo đúng call stack HTTP, `ExceptionTranslationFilter` nằm trong filter chain có thể xử lý bằng `AccessDeniedHandler`. Đây là đường khác với việc `AuthorizationFilter` từ chối một URL. Ví dụ runnable có test riêng để kiểm chứng cả hai.

**Một lưu ý kỹ thuật:** nếu `@ControllerAdvice` hoặc custom exception resolver bắt `AccessDeniedException` ngay trong MVC và trả response trước, exception có thể không còn đến security exception translation. Điều này không nhất thiết sai nếu được thiết kế có chủ đích, nhưng cần bảo đảm các response 401/403 nhất quán và không che policy.

Nếu một method security check bị bypass do self-invocation, `AccessDeniedHandler` không có cơ hội xử lý vì không có exception được ném. Do đó phải kiểm thử annotation thực sự được áp dụng; handler không thể sửa lỗi thiếu enforcement.

## 7. CSRF có thể trả 403 mà không đi qua handler đã cấu hình ở exceptionHandling

Đây là bẫy rất dễ gây hiểu sai.

Một request `POST /api/reports` của Editor có đúng role vẫn có thể bị **CsrfFilter** từ chối do thiếu CSRF token. Status cũng thường là **403**, nhưng điều này **không chứng minh** `AccessDeniedHandler` tùy biến ở `http.exceptionHandling(...)` đã được gọi.

Lý do: vị trí của `CsrfFilter` trong chain và cơ chế xử lý lỗi CSRF có thể **sử dụng đường xử lý AccessDenied riêng**, thay vì luôn ném exception xuống `ExceptionTranslationFilter`. Chính xác từng hook tùy phiên bản/cấu hình; không coi response JSON của handler chung là hợp đồng bắt buộc cho mọi CSRF failure.

Khi kiểm thử role trên POST/PUT/PATCH/DELETE, phải cung cấp CSRF token hợp lệ nếu CSRF đang bật. Chỉ khi đó một 403 có thể được quy về authorization role/service rõ ràng hơn.

Ví dụ MockMvc:

```java
mvc.perform(post("/api/reports")
        .with(httpBasic("reader", "reader-pass"))
        .with(csrf())
        .contentType(MediaType.TEXT_PLAIN)
        .content("Quarterly"))
    .andExpect(status().isForbidden());
```

Mảnh này chỉ nằm trong test đã có biến `mvc` và import đầy đủ. `with(csrf())` giúp loại nguyên nhân CSRF thiếu token trong request trên, nên lỗi của Reader có thể là do thiếu quyền POST. Với một test khác cố ý không gửi CSRF, chỉ khẳng định status/behavior theo CSRF policy, **không khẳng định payload JSON của custom handler luôn giống case authorization**.

Nếu API sử dụng bearer Authorization header mà browser không tự đính kèm credential, CSRF policy có thể khác; nhưng không tắt CSRF toàn cục chỉ để mọi test pass. Với form/cookie/Basic trong browser, cần phân tích đầy đủ cơ chế credential tự gửi.

## 8. API Bearer/JWT: đừng vô tình phá WWW-Authenticate

Một API OAuth 2.0 resource server dùng Bearer token có semantics riêng của challenge:

- Token thiếu, sai hoặc hết hạn thường dẫn đến authentication failure, 401 và header `WWW-Authenticate: Bearer ...` theo hợp đồng phù hợp.
- Token hợp lệ nhưng thiếu scope có thể dẫn đến 403 kèm Bearer-specific header/metadata thích hợp, như `insufficient_scope` tùy tình huống và configuration.
- Spring Security có `BearerTokenAccessDeniedHandler` cho use case này.

Nếu override mọi `AccessDeniedHandler` bằng JSON đơn giản mà **bỏ header `WWW-Authenticate` cần thiết**, client OAuth có thể không còn hiểu lỗi theo giao thức. Cần cân nhắc delegate đến Bearer handler/giữ header rồi bổ sung body phù hợp, hoặc tách `SecurityFilterChain` theo loại client.

**Ví dụ chính** dùng HTTP Basic, không dùng OAuth2 Resource Server; do đó không khẳng định custom JSON handler của demo là production-ready cho bearer-protected APIs. Tùy framework version, API của `BearerTokenAccessDeniedHandler` và thông tin available scopes cần được đối chiếu tài liệu chính thức.

## 9. Chọn status và mức thông tin trong lỗi từ chối

Đối với object-level permissions, việc một request trả 403 hay 404 có thể là một quyết định về **rò rỉ sự tồn tại của tài nguyên**. Ví dụ một tài liệu thuộc tenant khác: trả 403 có thể tiết lộ rằng một ID hợp lệ đang tồn tại.

Có thể thiết kế:

- Với route quản trị và user đã đăng nhập nhưng thiếu role: trả 403 có mã `ACCESS_DENIED`.
- Với một tài nguyên không thuộc tenant của caller: truy vấn giới hạn theo tenant, không tìm thấy thì trả 404 theo policy để tránh phân biệt “không tồn tại” với “không được thấy”.
- Với tài nguyên bị khóa do nghiệp vụ, xem xét `409 Conflict` hoặc `423 Locked` chỉ khi thực sự mang đúng semantics và không lộ thông tin.
- Với account chưa login, trả 401/redirect theo AuthenticationEntryPoint và chính sách login.

**AccessDeniedHandler không nên tự chuyển mọi 403 thành 404 một cách mù quáng**. Quyết định che sự tồn tại phải nằm ở tầng resource/tenant policy; handler chung không đủ thông tin để biết nguồn nào nên được giấu. Test cần bao gồm user khác tenant và tài nguyên không tồn tại, không chỉ hai role ADMIN/USER.

### Đừng đưa nguyên exception vào response

Sai:

```java
// Không khuyến nghị cho production:
response.getWriter().write(ex.getMessage());
```

Thông điệp có thể chứa tên class, biểu thức quyền, chi tiết tài khoản hoặc nội dung thay đổi giữa framework versions. Dùng error code ổn định, message thân thiện, và nếu cần một correlation ID không đoán được. Server-side logs cũng không nên in raw credentials, cookie, session ID hoặc bearer token.

### Status code quan trọng hơn body giả lập

Không trả:

```json
{"status":403,"message":"denied"}
```

với HTTP status 200. Client, HTTP cache, monitoring và policy response đều dựa vào mã trạng thái thật; body không thể thay thế HTTP status.

## 10. Project mẫu chạy được: Spring Boot 3.3.5, Java 17, Maven

Ví dụ tự chứa có:

- HTTP Basic với tài khoản `reader`, `editor`, `admin`.
- `GET /api/reports/{id}` chỉ ROLE_ADMIN.
- `POST /api/reports` cho EDITOR hoặc ADMIN và cần CSRF.
- `GET /api/service-report` chỉ yêu cầu authenticated ở HTTP nhưng bị kiểm tra ROLE_ADMIN tại service bằng `@PreAuthorize`.
- `GET /public` công khai.
- Các URL không khai báo bị `denyAll()`.
- `JsonAccessDeniedHandler` trả JSON 403 chung cho authorization denial đi qua ExceptionTranslationFilter.

Demo cố ý không sửa dữ liệu thật, không có database, không phải dự án production. Các password cố định chỉ phục vụ kiểm thử cục bộ, **không đưa lên môi trường công khai**. HTTPS là điều kiện bắt buộc để dùng Basic credentials an toàn trên mạng.

### 10.1. Cấu trúc thư mục

```text
access-denied-demo/
├── pom.xml
└── src/
    ├── main/java/example/accessdenied/
    │   ├── AccessDeniedApplication.java
    │   ├── SecurityConfig.java
    │   ├── JsonAccessDeniedHandler.java
    │   ├── ReportService.java
    │   └── ReportController.java
    └── test/java/example/accessdenied/
        └── AccessDeniedFlowTest.java
```

### 10.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>access-denied-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

Không thêm version riêng cho Spring Security dependencies khi Spring Boot BOM đang quản lý, để tránh trộn các bản không tương thích.

### 10.3. Entry point

File `src/main/java/example/accessdenied/AccessDeniedApplication.java`:

```java
package example.accessdenied;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AccessDeniedApplication {
    public static void main(String[] args) {
        SpringApplication.run(AccessDeniedApplication.class, args);
    }
}
```

### 10.4. JsonAccessDeniedHandler

File `src/main/java/example/accessdenied/JsonAccessDeniedHandler.java`:

```java
package example.accessdenied;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;

public final class JsonAccessDeniedHandler implements AccessDeniedHandler {

    private final ObjectMapper mapper;

    public JsonAccessDeniedHandler(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       AccessDeniedException denied) throws IOException {
        // Nếu response đã gửi headers/body thì không thể đổi status chắc chắn.
        if (response.isCommitted()) {
            return;
        }

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", HttpServletResponse.SC_FORBIDDEN);
        body.put("code", "ACCESS_DENIED");
        body.put("message", "Bạn không có quyền truy cập tài nguyên này");
        body.put("path", request.getRequestURI());

        mapper.writeValue(response.getWriter(), body);
    }
}
```

**Tại sao dùng Jackson?** `ObjectMapper` serialize đúng ký tự tiếng Việt và escape các chuỗi JSON do request cung cấp, tránh tự ghép bằng `"\"" + path + "\""`. Không đưa query string vào body demo. Production có thể loại bỏ `path` khi URL chứa dữ liệu nhạy cảm; thay bằng một error ID và trace correlation.

**Tại sao không dùng `sendError(403)`?** `sendError` cho container cơ hội dispatch tới error page mặc định; nếu muốn kiểm soát chính xác JSON body, có thể dùng `setStatus` rồi ghi JSON. Dùng `sendError` không sai, nhưng tương tác với container/error page cần hiểu rõ. Handler trong ví dụ viết body một lần và không tự forward/redirect.

**Tại sao không throw lại AccessDeniedException trong handler?** Handler là nơi chuyển exception thành response. Nếu throw lại không có chủ đích, có thể tạo 500 hoặc bị xử lý lại ở tầng khác. Với lỗi IOException thực, logging và vận hành theo chính sách chung, không trả một JSON giả thành công.

**Response committed:** trong tình huống lỗi ném ra sau khi response đã bắt đầu stream, không thể biến an toàn response đã commit thành HTTP 403 mới. Cần thiết kế stream/async error riêng và log an toàn. Guard ở ví dụ chỉ tránh ghi status/body không hợp lệ, không có nghĩa request đã được kiểm soát hoàn hảo.

### 10.5. SecurityConfig — cấu hình cả method và HTTP security

File `src/main/java/example/accessdenied/SecurityConfig.java`:

```java
package example.accessdenied;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
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
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("READER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    JsonAccessDeniedHandler jsonDenied(ObjectMapper mapper) {
        return new JsonAccessDeniedHandler(mapper);
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http, JsonAccessDeniedHandler deniedHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/*")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAnyRole("EDITOR", "ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/service-report")
                    .authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(ex -> ex
                .accessDeniedHandler(deniedHandler))
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Ý nghĩa:

- `@EnableMethodSecurity` để `@PreAuthorize` trên ReportService được áp dụng qua Spring proxy.
- `httpBasic()` là cơ chế xác thực. Thiếu/sai HTTP Basic credentials thường tạo **401 challenge** qua entry point; custom `AccessDeniedHandler` **không làm thay đổi** hành vi đó.
- `GET /api/reports/{id}` chỉ ADMIN ở HTTP authorization. Reader đã login bị từ chối và nhận JSON 403.
- `POST /api/reports` chỉ EDITOR hoặc ADMIN. CSRF vẫn bật; POST đúng role nhưng thiếu CSRF có thể bị chặn bởi CSRF filter.
- `GET /api/service-report` chỉ cần authenticated ở HTTP, nhưng service method yêu cầu ADMIN, để kiểm chứng lỗi từ method security cũng được xử lý.
- `anyRequest().denyAll()` ngăn đường dẫn/method chưa khai báo mặc nhiên được phép. Với một resource thật, cần thêm authorization ở object/tenant layer.

**Quan trọng:** cấu hình không disable CSRF. Nó cố ý để một test chứng minh response 403 từ CSRF có thể khác JSON của `exceptionHandling`. Không lấy việc “handler không được gọi ở case CSRF” làm lý do tắt CSRF.

### 10.6. Service có @PreAuthorize

File `src/main/java/example/accessdenied/ReportService.java`:

```java
package example.accessdenied;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public String sensitive() {
        return "SERVICE_REPORT";
    }
}
```

Method security ném exception trước khi chạy method nếu caller không có role ADMIN. Nếu annotation bị bỏ hoặc method không đi qua Spring proxy, test Reader ở `/api/service-report` sẽ phát hiện policy bị thiếu.

### 10.7. Controller đơn giản

File `src/main/java/example/accessdenied/ReportController.java`:

```java
package example.accessdenied;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/public")
    public String publicEndpoint() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/reports/{id}")
    public String byId(@PathVariable long id) {
        return "REPORT:" + id;
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    public String create(@RequestBody String title) {
        return "CREATED:" + title;
    }

    @GetMapping("/api/service-report")
    public String sensitive() {
        return reports.sensitive();
    }
}
```

Controller chỉ trả chuỗi cố định để test status/body. Không có database và không ghi báo cáo thật; handler và security code phải được kiểm thử tương ứng trong một ứng dụng có nghiệp vụ thực.

### 10.8. MockMvc integration tests

File `src/test/java/example/accessdenied/AccessDeniedFlowTest.java`:

```java
package example.accessdenied;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessDeniedFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsAccessibleAnonymously() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));
    }

    @Test
    void anonymousAdminRequestGetsAuthenticationChallenge() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("WWW-Authenticate",
                containsString("Basic")));
    }

    @Test
    void incorrectPasswordReturns401NotCustom403() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("admin", "incorrect")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerIsDeniedByHttpAuthorizationWithJson403()
            throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value(403))
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.path").value("/api/reports/42"))
            .andExpect(header().string("Cache-Control", "no-store"));
    }

    @Test
    void forbiddenResponseDoesNotRevealExceptionClass() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden())
            .andExpect(content().string(
                not(containsString("AccessDeniedException"))));
    }

    @Test
    void adminCanReadProtectedReport() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("REPORT:42"));
    }

    @Test
    void readerIsDeniedByServiceMethodSecurityAsJson403()
            throws Exception {
        mvc.perform(get("/api/service-report")
                .with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"))
            .andExpect(jsonPath("$.path").value("/api/service-report"));
    }

    @Test
    void adminMayCallSecuredService() throws Exception {
        mvc.perform(get("/api/service-report")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("SERVICE_REPORT"));
    }

    @Test
    void editorMayCreateWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Quarterly"))
            .andExpect(status().isCreated())
            .andExpect(content().string("CREATED:Quarterly"));
    }

    @Test
    void readerIsDeniedPostEvenWithValidCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "reader-pass"))
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("Quarterly"))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void editorWithoutCsrfIsDeniedIndependentlyOfRole()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-pass"))
                .contentType(MediaType.TEXT_PLAIN)
                .content("Quarterly"))
            .andExpect(status().isForbidden());
        // Không khẳng định JSON handler chung được gọi cho CSRF 403.
    }

    @Test
    void unknownRouteIsDeniedByFallback() throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }
}
```

Bộ test có **12 test cases**, bao trùm:

1. Public endpoint trả 200 cho anonymous.
2. Anonymous vào endpoint private bị 401 cùng Basic challenge.
3. Sai password bị 401 thay vì JSON 403.
4. Reader đã authenticated nhưng thiếu role tại HTTP rule nhận JSON 403, có code/path/cache header.
5. Response không lộ tên `AccessDeniedException`.
6. Admin được gọi resource với ROLE_ADMIN.
7. Reader vào service method có `@PreAuthorize` bị JSON 403 — phân biệt với denial ở `AuthorizationFilter`.
8. Admin vào service method thành công.
9. Editor có CSRF hợp lệ được POST.
10. Reader có CSRF hợp lệ nhưng vẫn bị 403 do thiếu role; JSON handler được quan sát.
11. Editor đúng role nhưng thiếu CSRF bị 403; test cố ý **không** assert cùng JSON.
12. URL chưa được cấp quyền bị `denyAll()`, custom handler trả 403.

**Đây là kỳ vọng từ mã bài học, không phải tuyên bố đã thực thi.** Muốn xác nhận thực tế, cần tạo đúng files, chạy Maven tests ở môi trường có dependencies và kiểm tra kết quả. Test cũng không thay cho việc kiểm thử reverse proxy, nhiều filter chains, async streaming hoặc OAuth2 Resource Server.

### 10.9. Lệnh chạy

Trong thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Nếu app chạy ở localhost:8080 (mặc định khi cổng còn trống):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/reports/42
curl -i -u reader:reader-pass http://localhost:8080/api/reports/42
curl -i -u admin:admin-pass http://localhost:8080/api/reports/42
```

Status/body dự kiến:

```text
GET /public anonymous           -> 200 PUBLIC_OK
GET /api/reports/42 anonymous   -> 401 + WWW-Authenticate: Basic ...
GET /api/reports/42 reader      -> 403 + JSON ACCESS_DENIED
GET /api/reports/42 admin       -> 200 REPORT:42
```

Mật khẩu mẫu chỉ phục vụ bài tập. Không dùng `curl -u username:password` với credential thật khi shell history/process list có thể lưu chúng; production phải dùng TLS và secret management phù hợp.

## 11. Những sai lầm thường gặp khi viết AccessDeniedHandler

### 11.1. Nhầm 401 và 403

**Sai:** trả 403 cho mọi request chưa đăng nhập và đã đăng nhập nhưng thiếu role. Việc này có thể phá hợp đồng HTTP Basic/Bearer challenge và khiến client không biết phải xác thực hay không.

**Đúng:** dùng `AuthenticationEntryPoint` cho trường hợp authentication chưa đủ, `AccessDeniedHandler` cho authorization denial khi có authentication đủ theo trust resolver.

### 11.2. Trả HTTP 200 với JSON lỗi 403

Status body không thay HTTP status. Hãy dùng `response.setStatus(HttpServletResponse.SC_FORBIDDEN)` và mã lỗi machine-readable, kiểm thử cả hai.

### 11.3. Gửi raw exception.getMessage() ra ngoài

Thông tin có thể tiết lộ policy nội bộ, role name, object ID, Java classes hoặc implementation. Dùng message chung và mã lỗi ổn định. Nếu muốn hỗ trợ debug, correlation ID chỉ nên trỏ đến audit log đã được bảo vệ.

### 11.4. Handler tự sửa Authentication hoặc authorities

Handler là response boundary. Không tự set user thành admin hoặc chạy lại request với quyền khác; quyền phải được tính trong authorization manager/policy từ nguồn tin cậy.

### 11.5. Chỉ thêm @RestControllerAdvice

`@ControllerAdvice` xử lý lỗi trong MVC lifecycle nhưng các filter của Spring Security có thể từ chối **trước khi controller được gọi**. Vì vậy một handler ở MVC không thay thế hoàn toàn `AccessDeniedHandler` cấu hình cho security filter chain.

### 11.6. Chỉ cấu hình error page và quên API client

Một browser web cần HTML có thể hợp lý; client REST cần status/content-type và JSON schema. Nếu cùng app có hai loại client, có thể tách filter chains hoặc chọn handler theo route/Accept header với chính sách rõ. Không tự trả HTML 200 cho AJAX chỉ vì error page render đẹp.

### 11.7. Tắt CSRF để JSON 403 đồng nhất

CSRF filter có đường xử lý riêng và đúng lý do. Đừng tắt CSRF chỉ để test POST không còn 403; hãy gửi token hợp lệ, rồi mới kiểm tra role. Với API architecture khác, phân tích lại CSRF theo credential được browser gửi tự động.

### 11.8. Thay Bearer handler mà quên header

Nếu API OAuth2 yêu cầu `WWW-Authenticate`/`insufficient_scope`, custom handler phải giữ protocol semantics cần thiết. Không copy nguyên demo HTTP Basic cho Bearer resource server.

### 11.9. Forward/redirect tạo vòng lặp

Một access denied page cũng có thể bị security chặn nếu không được phép truy cập/forward theo cấu hình. Kiểm tra URL error page, filter mapping, dispatcher type và các rules thứ tự. Không mở mọi route bằng `permitAll("/**")` để làm error page hoạt động.

### 11.10. Response đã committed

Handler không thể thay đổi status đã gửi qua network. Với streaming, async và Servlet error dispatch, cần thiết kế cơ chế xử lý lỗi sớm hoặc signal lỗi theo protocol stream; không để exception trở thành response thành công giả.

### 11.11. Lẫn lỗi ứng dụng và thiếu quyền

Một `NullPointerException`, repository timeout hoặc HTTP 409 do xung đột nghiệp vụ **không phải** `AccessDeniedException`. Không catch mọi exception rồi trả 403: việc đó che sự cố và làm khó vận hành. Ngược lại, khi policy thực sự từ chối, đừng trả 500 kèm stack trace.

### 11.12. Không kiểm tra “denial” đến từ đâu

HTTP authorization, method security, CSRF, route policy, CORS, gateway và object-level policy đều có thể gây kết quả “không truy cập được”. Bắt đầu debug bằng method/path, authentication type, authorities, chain đã chọn, rule, CSRF và handler đã được gọi; tránh kết luận chỉ từ mã 403.

## 12. Lưu ý khi triển khai nhiều SecurityFilterChain

Một ứng dụng có thể cấu hình:

```text
/api/** -> API SecurityFilterChain:
           Basic/Bearer, JSON error, no form redirect

/web/** -> Web SecurityFilterChain:
           Form login, HTML access-denied page

fallback -> deny-by-default
```

Mỗi chain có thể có `exceptionHandling` riêng, với entry point và denied handler tương ứng. Vì `FilterChainProxy` chọn **chain đầu tiên phù hợp**, một matcher rộng ở thứ tự trước có thể làm API đi vào web chain và trả HTML/redirect ngoài ý muốn.

Khi tách chains, luôn test:

- API anonymous → đúng 401/WWW-Authenticate.
- API authenticated nhưng thiếu quyền → đúng 403 JSON.
- Web chưa login → redirect login phù hợp.
- Web đã login nhưng thiếu quyền → trang lỗi đúng status/forward policy.
- Unknown route/method → fallback chặt chẽ.
- CSRF và bearer-specific semantics ở từng chain.

Không chỉ kiểm tra tên bean `JsonAccessDeniedHandler` đã được tạo; bean đó phải thực sự được nối vào **SecurityFilterChain khớp request** mới có tác dụng.

## 13. Logging, audit, observability

Access denied là tín hiệu bảo mật hữu ích, nhưng nếu log mọi 403 cùng stack trace, hệ thống dễ ngập log và lộ dữ liệu. Một bộ thông tin vận hành có kiểm soát có thể gồm:

- Thời điểm và correlation/request ID được sinh/chuẩn hóa ở phía server.
- Authentication principal identifier đã được policy cho phép ghi (ưu tiên ID thay vì email đầy đủ).
- Method và **route template** như `GET /api/reports/{id}` thay vì URL chứa dữ liệu nhạy cảm.
- Tên security policy/matcher hoặc nhóm error code ổn định.
- Kết quả `ACCESS_DENIED`, HTTP 403, application/module.
- Trace ID để tìm log nội bộ theo quyền truy cập phân cấp.

**Không log** raw HTTP Basic header, JWT, session cookie, CSRF token, password, secret, full request body chứa PII. Đừng tự ghép exception.getMessage() vào user-facing JSON hoặc unredacted metrics labels.

Với một endpoint thường xuyên trả 403, hãy phân biệt cấu hình sai (nhiều user hợp lệ bị chặn) với các request dò quét/bot/abuse. Rate limiting, WAF hoặc threat detection không thay cho authorization logic.

## 14. Checklist trước khi phát hành

- [ ] Hiểu khác biệt giữa `AuthenticationEntryPoint` và `AccessDeniedHandler`; anonymous/remember-me được xử lý theo mức authentication.
- [ ] Có policy `hasRole`/`hasAuthority` và object-level authorization đúng, không chỉ custom JSON lỗi.
- [ ] Custom handler đặt HTTP status 403 thật, mã lỗi ổn định, body JSON được encode, content type đúng.
- [ ] Handler không phát tán exception text, credentials hoặc thông tin nội bộ không cần thiết.
- [ ] Có xử lý khi response đã committed; không nhân đôi body hay redirect ngoài ý muốn.
- [ ] API Basic/Bearer giữ challenge/headers đúng; OAuth2 Resource Server không bị mất `WWW-Authenticate` cần thiết.
- [ ] 401/403 đã được test riêng cho anonymous, sai credential và authenticated nhưng thiếu quyền.
- [ ] CSRF 403 được kiểm tra riêng; method-role test trên POST gửi CSRF hợp lệ.
- [ ] Method security được bật với `@EnableMethodSecurity`; test phủ cả denial ở HTTP và service.
- [ ] Nếu có web HTML, forward/redirect access denied page được kiểm tra status, URL, dispatcher type và vòng lặp.
- [ ] Nếu có nhiều chains, mỗi chain nối đúng handler và entry point theo client.
- [ ] Object/tenant access policy có quy tắc che sự tồn tại resource (403/404) nhất quán khi cần.
- [ ] Log và audit có thông tin điều tra nhưng không chứa raw secrets hoặc dữ liệu nhạy cảm.
- [ ] Các response lỗi nhạy cảm có cache policy phù hợp, ví dụ `no-store`.
- [ ] Không dùng response format như một biện pháp thay thế việc thực thi security authorization.

### Câu hỏi tự kiểm tra

**1.** User đã login với `ROLE_USER` nhưng gọi `GET /api/admin/reports` cần `ROLE_ADMIN`. Extension point nào thường tạo phản hồi?  
**Đáp án:** Khi authentication đủ để phân biệt danh tính và authorization từ chối, `AccessDeniedHandler` thường trả 403.

**2.** User anonymous truy cập URL private. Tại sao không khẳng định custom AccessDeniedHandler luôn trả 403?  
**Đáp án:** `ExceptionTranslationFilter` có thể phân loại anonymous và gọi `AuthenticationEntryPoint` để yêu cầu xác thực (401 hoặc login redirect).

**3.** HTTP Basic password sai mà server trả 401, đó có phải lỗi AccessDeniedHandler?  
**Đáp án:** Không. Đây là authentication failure được xử lý bởi authentication mechanism/entry point.

**4.** POST Editor có đủ quyền nhưng thiếu CSRF token nhận 403. Vì sao body có thể khác custom JSON 403?  
**Đáp án:** CSRF filter có đường xử lý lỗi riêng; không đảm bảo `exceptionHandling.accessDeniedHandler(...)` được gọi cho mọi CSRF denial.

**5.** `@PreAuthorize` từ chối ở service nhưng handler JSON không được gọi. Những nguyên nhân nào cần kiểm tra?  
**Đáp án:** Method security có bật không, method có đi qua Spring proxy không, exception có bị MVC resolver/controller advice bắt mất không, request có đi qua SecurityFilterChain phù hợp không.

**6.** Có nên luôn dùng `response.getWriter().write(exception.getMessage())`?  
**Đáp án:** Không. Exception text có thể lộ implementation/policy; dùng code và message an toàn, log riêng theo quy trình.

**7.** API Bearer có 403 do thiếu scope; chỉ trả JSON mà bỏ `WWW-Authenticate` có thể gây gì?  
**Đáp án:** Client OAuth2 có thể không hiểu semantics giao thức; cần giữ header/handler phù hợp.

**8.** Handler có được coi là nơi cập nhật role, permissions hoặc thu hồi session không?  
**Đáp án:** Không. Nó phản hồi một lần authorization đã bị từ chối. Thay đổi quyền/session là chính sách riêng.

**9.** Tại sao test POST reader bị 403 cần `with(csrf())`?  
**Đáp án:** Để request không bị CSRF filter chặn trước khi đến authorization, qua đó kiểm chứng thật việc thiếu role.

**Kết luận:** Trong Spring Security Servlet, `AccessDeniedHandler` là **điểm chuyển một quyết định từ chối quyền hợp lệ thành HTTP response**, thường là 403 đối với người đã xác thực nhưng thiếu quyền. Cần phân biệt rõ với `AuthenticationEntryPoint` cho 401/đăng nhập lại, với đường xử lý CSRF, và với lỗi nghiệp vụ khác. Một implementation tốt phải **giữ status thật, không tiết lộ thông tin, bảo toàn semantics HTTP Basic/Bearer, kiểm thử cả URL lẫn method security**, và không dùng response đẹp để che một policy phân quyền sai.