# Tạo phản hồi thành công, thất bại phù hợp với REST API khi xác thực tùy chỉnh

## 1. Mục tiêu: xác thực là nghiệp vụ, HTTP response là hợp đồng của API

Một REST API thường được gọi bởi web frontend, mobile app hoặc service khác. Các client này cần nhận **HTTP status**, **JSON response** và **thông tin xác thực** theo một hợp đồng rõ ràng, thay vì bị chuyển hướng tới trang HTML đăng nhập.

Khi tự viết một điểm xác thực, ứng dụng phải trả lời tách bạch:

1. **Request có đúng định dạng không?** JSON hợp lệ, đủ trường, content type phù hợp.
2. **Thông tin xác thực có được chấp nhận không?** Username/password, API key, token hoặc cơ chế đã chọn.
3. **Đã xác thực nhưng có đủ quyền vào tài nguyên không?** Đây là authorization, khác authentication.
4. **Thành công thì client sử dụng kết quả ra sao?** Nhận thông tin user, access token hoặc cookie/session theo thiết kế thực tế.
5. **Thất bại thì client khôi phục thế nào?** Đọc mã lỗi ổn định mà không làm lộ thông tin nhạy cảm.

Trong **Spring Security Servlet**, API phản hồi thành công/thất bại có thể được xử lý trong controller, trong `AuthenticationSuccessHandler` / `AuthenticationFailureHandler` của authentication filter, qua `AuthenticationEntryPoint` đối với người chưa xác thực, hoặc qua `AccessDeniedHandler` khi đã xác thực nhưng thiếu quyền.

**Nguyên tắc quan trọng:** Không nhầm các điểm xử lý này. Một response JSON đẹp không biến một custom authentication flow thành an toàn nếu bạn bỏ qua `AuthenticationManager`, lưu token không đúng hoặc làm lộ trạng thái tài khoản.

Bài này dùng **Spring Boot 3.x, Spring Security 6.x, Java 17+ và Servlet stack**. Ví dụ chạy được ở phần 7 mô phỏng **API stateless dùng Bearer token ngẫu nhiên**: `POST /api/auth/login` trả token JSON khi thành công; request sau gửi `Authorization: Bearer <token>`; response 400/401/403 cũng là JSON. Token demo được lưu trong bộ nhớ và có thời hạn ngắn, **không phải token service production**.

## 2. Chọn mã HTTP theo ý nghĩa thực tế

| Tình huống | Status điển hình | Ý nghĩa trong API |
| --- | --- | --- |
| Request đăng nhập hợp lệ, xác thực thành công và trả token | **200 OK** | Client nhận JSON chứa token và thời hạn |
| Login thành công nhưng không cần response body | **204 No Content** | Phù hợp khi kết quả xác thực được quản lý theo cơ chế khác và không cần trả nội dung |
| Body JSON sai cú pháp, thiếu tham số bắt buộc hoặc không đúng schema | **400 Bad Request** | Đầu vào request chưa đúng hợp đồng |
| Username/password sai, tài khoản không được phép xác thực, Bearer token thiếu/hết hạn/không hợp lệ | **401 Unauthorized** | Request chưa được xác thực hợp lệ cho thao tác này |
| Đã xác thực hợp lệ nhưng role/permission không đủ | **403 Forbidden** | Có danh tính hợp lệ nhưng không được phép thực hiện |
| API path không tồn tại | **404 Not Found** | Resource không tìm thấy; auth policy có thể từ chối trước khi request vào MVC |
| Quá nhiều lần thử đăng nhập hoặc vượt rate limit | **429 Too Many Requests** | Cần chính sách hạn chế tần suất và có thể có `Retry-After` |
| Lỗi hạ tầng/identity provider không khả dụng | **5xx** phù hợp | Không nên giả mọi sự cố hệ thống thành “mật khẩu sai” |

Hai điểm thường bị nhầm:

- **401 không có nghĩa “không có role ADMIN”.** Đó thường là 403 *sau khi* danh tính hợp lệ được xác thực. Nếu có custom entry point hay chính sách che giấu resource, kết quả có thể khác; nên định nghĩa một hợp đồng nhất quán.
- **403 không phải mặc định cho mật khẩu sai.** Một request `POST /login` thiếu CSRF token có thể bị từ chối 403 **trước bước** kiểm tra mật khẩu, nhưng đó là CSRF failure, không phải kết luận về account.

Mã 200 hay 201 tùy contract và tài nguyên được tạo. Trong ví dụ cấp bearer token, ta dùng **200** với body chứa thông tin token; không chọn 201 chỉ vì request là POST.

## 3. Thiết kế JSON response ổn định

### 3.1. Thành công khi login

Một hợp đồng ví dụ:

~~~json
{
  "tokenType": "Bearer",
  "accessToken": "<opaque-random-token>",
  "expiresIn": 900
}
~~~

`accessToken` trong ví dụ chỉ là **giá trị giả minh họa**, không phải token thật. `expiresIn` đo bằng **giây**. API dùng header `Cache-Control: no-store` để giảm khả năng response có token được cache ngoài ý muốn.

Không trả password, password hash, secret key, full `Authentication` object hay các dữ liệu nội bộ không cần thiết. Chỉ trả phần client cần để gọi API.

Nếu ứng dụng dùng session cookie thay vì token, response thành công có thể chỉ trả user/profile; cookie phải được cấu hình `Secure`, `HttpOnly`, `SameSite` phù hợp và flow cần xem xét CSRF. **Không kết hợp hai mô hình mà không hiểu cách trình duyệt tự gửi credentials.**

### 3.2. Thất bại vì credentials

~~~json
{
  "code": "AUTHENTICATION_FAILED",
  "message": "Thông tin đăng nhập không hợp lệ."
}
~~~

Response 401 này có thể được dùng **chung** cho username không tồn tại, mật khẩu sai, tài khoản locked, disabled, expired hoặc credentials expired trong màn hình đăng nhập công khai. Không trả thông tin như:

~~~json
{
  "code": "USER_EXISTS_BUT_LOCKED",
  "message": "Tài khoản alice hiện đã bị khóa"
}
~~~

Đoạn thứ hai là **anti-pattern**: người chưa xác thực có thể dùng nó để dò username và trạng thái account.

Các mã lỗi public nên mô tả **hành động tiếp theo của client**, không phản ánh đầy đủ cấu trúc exception nội bộ. Hệ thống vẫn có thể ghi audit nguyên nhân ở nơi được bảo vệ, theo chính sách dữ liệu phù hợp.

### 3.3. Thất bại vì sai schema

~~~json
{
  "code": "INVALID_REQUEST",
  "message": "Yêu cầu không hợp lệ."
}
~~~

Response **400** có thể dùng cho JSON sai, trường username/password không hợp lệ về cấu trúc hoặc body thiếu. Không nên trả 200 với body `"success": false` chỉ để tránh xử lý HTTP status: như vậy client, proxy, monitoring và retry logic khó phân biệt request đúng và sai.

### 3.4. Đã login nhưng thiếu quyền

~~~json
{
  "code": "FORBIDDEN",
  "message": "Không có quyền truy cập tài nguyên."
}
~~~

Response **403** không nên tiết lộ rule phân quyền nội bộ hoặc dữ liệu tài nguyên khác. Ví dụ người dùng đã login với `ROLE_USER` nhưng yêu cầu `GET /api/admin` chỉ dành cho `ROLE_ADMIN`.

### 3.5. Gợi ý contract cho lỗi

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `code` | Mã lỗi ổn định, machine-readable | Client phân nhánh bằng code, không phân tích chuỗi thông báo |
| `message` | Thông điệp an toàn, dễ hiểu | Có thể bản địa hóa; không chứa stack trace/secret/account state |
| `requestId` | ID tương quan cho hỗ trợ vận hành (nếu hệ thống có) | Tạo ở infrastructure; không dùng token hoặc session ID làm requestId |
| `details` | Danh sách lỗi validation không nhạy cảm (tùy chọn) | Không đưa bảng user, exception class, SQL hoặc thông tin bảo mật |
| HTTP status | Ý nghĩa ở transport | Không dùng `200` cho mọi lỗi; phản ánh đúng 400/401/403/429/5xx |

Hãy nhất quán về content type `application/json` hoặc `application/problem+json`. Một dự án có thể chọn **RFC 9457 Problem Details** và `ProblemDetail` của Spring, hoặc schema `code/message` riêng như ví dụ này; không nhất thiết dùng cả hai cho cùng endpoint. Quan trọng là document schema và test.

## 4. Những điểm mở rộng quan trọng trong Spring Security

### 4.1. AuthenticationManager và AuthenticationProvider

Phần kiểm tra credentials nên do `AuthenticationManager`/`AuthenticationProvider` đáng tin cậy xử lý, không tạo token đã authenticated chỉ dựa trên username do client gửi:

~~~java
Authentication result = authenticationManager.authenticate(
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword
    )
);
~~~

Đây là **snippet tích hợp**. `authenticationManager`, `username` và `rawPassword` được cung cấp từ thành phần đăng nhập đã validate input. `result` chỉ được coi là đã xác thực khi provider chấp nhận credentials. Với provider dựa trên `UserDetails`, trạng thái tài khoản như locked/disabled/expired cũng có thể làm authentication thất bại.

**Sai nguy hiểm:**

~~~java
// KHÔNG dùng: client tự khai user/role rồi server đánh dấu authenticated.
Authentication forged = UsernamePasswordAuthenticationToken.authenticated(
    usernameFromRequest, null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
~~~

Snippet trên minh họa cách **tự cấp quyền trái phép** nếu danh tính và quyền đến trực tiếp từ client. Constructor/method tạo authenticated token chỉ dùng khi thông tin đã được một bước kiểm chứng đáng tin cậy chấp nhận.

### 4.2. AuthenticationSuccessHandler

`AuthenticationSuccessHandler` thuộc luồng authentication được quản lý bởi security filter (ví dụ custom `AuthenticationFilter` hoặc filter kế thừa `AbstractAuthenticationProcessingFilter`). Nó quyết định **response khi filter xác thực thành công**.

Ví dụ mô tả mẫu JSON:

~~~java
AuthenticationSuccessHandler success = (request, response, authentication) -> {
    response.setStatus(HttpServletResponse.SC_OK);
    response.setContentType("application/json;charset=UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write("{\"status\":\"AUTHENTICATED\"}");
};
~~~

Đây là **snippet**, cần import các kiểu Java/Spring Security liên quan. Phần response trên chỉ xác nhận thành công, **không tự cấp token hay lưu session**. Nếu đây là login endpoint cho client cần duy trì authentication, handler hoặc tầng service phải dùng cơ chế session/token hợp lệ. Không thể suy ra request sau đã được đăng nhập chỉ vì đã nhận HTTP 200.

### 4.3. AuthenticationFailureHandler

`AuthenticationFailureHandler` xử lý **authentication thất bại bên trong filter**:

~~~java
AuthenticationFailureHandler failure = (request, response, exception) -> {
    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
    response.setContentType("application/json;charset=UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write(
        "{\"code\":\"AUTHENTICATION_FAILED\",\"message\":\"Thông tin đăng nhập không hợp lệ.\"}"
    );
};
~~~

Không trả `exception.getMessage()` trực tiếp cho client. `BadCredentialsException`, `LockedException`, `DisabledException`, `CredentialsExpiredException` là thông tin kỹ thuật có thể phục vụ audit nội bộ nhưng không phù hợp để tiết lộ trong response công khai.

Nếu bạn tự xác thực trong **REST controller** thay vì security filter, `AuthenticationSuccessHandler`/`AuthenticationFailureHandler` **không tự động được gọi**. Controller có thể trả `ResponseEntity` theo cùng contract, như ví dụ đầy đủ ở phần 7.

### 4.4. AuthenticationEntryPoint

`AuthenticationEntryPoint` xử lý request tới resource cần authentication khi **chưa có authentication hợp lệ**. Với REST API, nó thường trả JSON **401** thay vì redirect `302` tới form login.

Ví dụ request:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
~~~

Và phản hồi:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Bearer
Cache-Control: no-store

{"code":"UNAUTHORIZED","message":"Yêu cầu xác thực hợp lệ."}
~~~

`WWW-Authenticate: Bearer` là challenge thường phù hợp với resource yêu cầu Bearer token. Không gắn Bearer challenge một cách mù quáng cho API chỉ dùng session hoặc mTLS. Với Bearer scheme chuẩn, các tham số lỗi chi tiết có quy tắc riêng; demo chỉ sử dụng header tổng quát.

### 4.5. AccessDeniedHandler

`AccessDeniedHandler` xử lý **authorization failure** khi đã có principal xác thực nhưng thiếu quyền. Response cho REST API thường là JSON **403**; không chuyển về trang HTML đăng nhập. Nếu một request anonymous gây `AccessDeniedException`, `ExceptionTranslationFilter` có thể chuyển sang `AuthenticationEntryPoint` để nhận 401 — vì vậy không phải mọi `AccessDeniedException` đều trả 403.

### Bảng chọn đúng điểm xử lý

| Trường hợp | Điểm mở rộng thường phù hợp |
| --- | --- |
| Custom authentication filter thành công | `AuthenticationSuccessHandler` |
| Custom authentication filter thất bại | `AuthenticationFailureHandler` |
| REST controller tự gọi `AuthenticationManager.authenticate` | `ResponseEntity` + xử lý `AuthenticationException` có kiểm soát |
| GET resource bảo vệ thiếu bearer token | `AuthenticationEntryPoint` |
| GET resource đã authenticated nhưng không đủ role | `AccessDeniedHandler` |
| JSON body sai cấu trúc | MVC exception handler / `@RestControllerAdvice` |
| Validation hoặc business exception | Tầng controller/advice/service mapping phù hợp, không coi là authentication failure |

**Không nhầm `failureUrl` của form login với response của REST API.** `failureUrl` thường tạo redirect `302` đến HTML login page; API client thường cần 401 JSON nhất quán.

## 5. Stateless Bearer token và session cookie là hai lựa chọn khác nhau

### 5.1. Demo trong bài: Bearer token cho mỗi request

~~~text
POST /api/auth/login, JSON username/password
  |
  v
AuthenticationManager xác minh credentials
  |
  +-- thất bại -> 401 JSON generic
  |
  +-- thành công -> tạo token ngẫu nhiên (opaque) và TTL
                     |
                     v
                 200 JSON { tokenType, accessToken, expiresIn }
                     |
                     v
Client gửi: Authorization: Bearer <token>
                     |
                     v
Bearer filter tra hash token trong token store
                     |
                     +-- không hợp lệ/expired -> 401 JSON
                     |
                     +-- hợp lệ -> gắn Authentication vào SecurityContext
                                      |
                                      v
                             authorization rule
                                      |
                                      +-- thiếu role -> 403 JSON
                                      +-- đủ quyền -> Controller -> 200 JSON
~~~

Trong mô hình này **không dùng cookie/session làm credential**. Bearer token là dữ liệu bí mật: ai sở hữu token còn hiệu lực có thể được coi là người dùng tương ứng. Vì thế phải truyền bằng HTTPS, tránh đưa vào URL, log hay local storage dễ bị XSS lấy cắp; client cần chiến lược lưu trữ phù hợp với nền tảng. Khi token hết hạn thì client đăng nhập lại hoặc dùng refresh flow được thiết kế riêng.

Ví dụ sử dụng **opaque token ngẫu nhiên** và store in-memory để dễ hiểu. Nó không phải JWT, không thể tự kiểm chứng offline bằng chữ ký, không sống qua restart và không dùng được giữa nhiều server instance. Production có thể dùng OAuth2/OIDC + Spring Security Resource Server hoặc token service có store với TTL/revocation đủ tin cậy, thay vì tự sáng chế bearer scheme.

### 5.2. Nếu chọn session cookie

Nếu ứng dụng trả cookie sau login và browser tự gửi cookie ở request tiếp theo, cần quản lý session, SameSite/Secure/HttpOnly, CSRF và session fixation. Việc tắt CSRF chỉ vì gọi endpoint là REST **không đúng**. Bài demo stateless có thể tắt CSRF trong điều kiện **không sử dụng cookie/credentials được browser tự đính kèm** để xác thực. Nếu bổ sung cookie trong tương lai phải đánh giá lại.

### 5.3. JWT khác opaque token

JWT thường chứa claims và chữ ký được verify bằng key; không nên chỉ decode payload rồi tin vào role. Opaque token thường cần tra cứu token store hoặc introspection. Dù chọn loại nào, cần kiểm tra expiry, issuer/audience/scope, thu hồi, quyền hiện hành và chính sách bảo vệ khóa/trạng thái. **Ví dụ này chỉ minh họa logic phản hồi REST và một cơ chế token tối thiểu cho phát triển**, không được xem là chuẩn triển khai OAuth2.

## 6. Hợp đồng cụ thể của REST API ví dụ

| Request | Credentials | Kết quả dự kiến |
| --- | --- | --- |
| `POST /api/auth/login` | Username/password đúng | 200, JSON token |
| `POST /api/auth/login` | Password sai, username không tồn tại, locked | 401, mã `AUTHENTICATION_FAILED` chung |
| `POST /api/auth/login` | JSON sai hoặc thiếu trường | 400, mã `INVALID_REQUEST` |
| `GET /api/public` | Không cần | 200, JSON public |
| `GET /api/me` | Thiếu Bearer token | 401, mã `UNAUTHORIZED` |
| `GET /api/me` | Token giả/expired | 401, mã `UNAUTHORIZED` |
| `GET /api/me` | Token hợp lệ của alice | 200, JSON username |
| `GET /api/admin` | Token hợp lệ của alice (USER) | 403, mã `FORBIDDEN` |
| `GET /api/admin` | Token hợp lệ của admin (ADMIN) | 200, JSON admin-ok |

Các response 401 cho token trên tài nguyên bảo vệ sẽ có `WWW-Authenticate: Bearer`. Mã và thông điệp từ lỗi đăng nhập không xác nhận account có tồn tại, đang bị khóa hay đã hết hạn hay không.

## 7. Ví dụ đầy đủ: Spring Boot 3, Security 6, Java 17, JSON + opaque bearer token

Đây là một **project Spring Boot Maven** hoạt động với HTTP JSON từ đầu đến cuối. Nó gồm:

- `AuthenticationManager` dựa trên `DaoAuthenticationProvider` để kiểm tra password BCrypt và trạng thái `UserDetails`.
- `POST /api/auth/login` nhận JSON, trả 200 token hoặc 400/401 JSON.
- `TokenService` tạo 32 byte token ngẫu nhiên bằng `SecureRandom`, lưu **SHA-256 fingerprint** làm key trong `ConcurrentHashMap` và TTL 15 phút. Token gốc chỉ trả cho client.
- `BearerTokenFilter` xác minh token trên request tiếp theo, tạo `SecurityContext` mới cho request, gắn `Authentication` chỉ sau khi token hợp lệ.
- `AuthenticationEntryPoint` cho 401 JSON, `AccessDeniedHandler` cho 403 JSON, `@RestControllerAdvice` cho JSON sai.
- Test `MockMvc` xác minh login success, login failure, thiếu token, token sai và quyền ADMIN.

**Giới hạn cố ý:** in-memory token store mất sau restart, không chia sẻ giữa nhiều replica, không tự xóa hết token expired chưa được truy cập, không có refresh token, token revoke, replay/device binding, rate limiting, account-state recheck mỗi request hoặc OAuth2 interoperability. **Không triển khai nguyên trạng trong production.** Mục tiêu là thấy rõ trách nhiệm của response và luồng xác thực; khi triển khai thực tế ưu tiên thư viện/token infrastructure được kiểm định.

### 7.1. Cấu trúc

~~~text
rest-auth-response/
├── pom.xml
└── src/
    ├── main/java/com/example/restauth/
    │   ├── RestAuthApplication.java
    │   ├── SecurityConfig.java
    │   ├── ApiError.java
    │   ├── ApiErrors.java
    │   ├── TokenService.java
    │   ├── BearerTokenFilter.java
    │   ├── ApiController.java
    │   └── ApiExceptionAdvice.java
    └── test/java/com/example/restauth/AuthApiTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>rest-auth-response</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
~~~

**`src/main/java/com/example/restauth/RestAuthApplication.java`**

~~~java
package com.example.restauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RestAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(RestAuthApplication.class, args);
    }
}
~~~

### 7.2. Kiểu JSON lỗi dùng chung

**`src/main/java/com/example/restauth/ApiError.java`**

~~~java
package com.example.restauth;

// Java record giúp Jackson xuất JSON {"code": "...", "message": "..."}.
public record ApiError(String code, String message) {
}
~~~

**`src/main/java/com/example/restauth/ApiErrors.java`**

~~~java
package com.example.restauth;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;

public final class ApiErrors {

    private ApiErrors() {
    }

    public static void write(ObjectMapper mapper, HttpServletResponse response,
                             int status, String code, String message)
            throws IOException {

        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setHeader("Cache-Control", "no-store");

        if (status == HttpServletResponse.SC_UNAUTHORIZED) {
            response.setHeader("WWW-Authenticate", "Bearer");
        }

        mapper.writeValue(response.getWriter(), new ApiError(code, message));
    }
}
~~~

Hàm này chỉ xuất JSON lỗi đã được **lựa chọn an toàn** bởi code phía server. Nó không nhận và không in `AuthenticationException#getMessage`. `WWW-Authenticate: Bearer` được dùng cho response 401 ở các endpoint yêu cầu Bearer. Nếu hệ thống dùng HTTP Basic hoặc session, header challenge phải thay tương ứng.

### 7.3. TokenService: phát hành và tra cứu token demo

**`src/main/java/com/example/restauth/TokenService.java`**

~~~java
package com.example.restauth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.stereotype.Service;

@Service
public class TokenService {

    public static final long TOKEN_SECONDS = 900;

    private final SecureRandom random = new SecureRandom();
    private final ConcurrentMap<String, TokenRecord> tokens =
        new ConcurrentHashMap<>();

    private record TokenRecord(
        String username,
        Set<String> authorityNames,
        Instant expiresAt
    ) {
    }

    public String issue(Authentication authenticated) {
        byte[] secret = new byte[32];
        random.nextBytes(secret);

        String rawToken = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(secret);

        Arrays.fill(secret, (byte) 0);

        Set<String> authorityNames = authenticated.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toUnmodifiableSet());

        TokenRecord record = new TokenRecord(
            authenticated.getName(),
            authorityNames,
            Instant.now().plus(Duration.ofSeconds(TOKEN_SECONDS))
        );

        // Giữ SHA-256 fingerprint thay cho bản rõ token trong map.
        tokens.put(fingerprint(rawToken), record);
        return rawToken;
    }

    public Optional<Authentication> authenticate(String token) {
        // Token trong ví dụ: Base64URL của 32 byte -> 43 ký tự.
        if (token == null || !token.matches("[A-Za-z0-9_-]{43}")) {
            return Optional.empty();
        }

        String key = fingerprint(token);
        TokenRecord record = tokens.get(key);

        if (record == null) {
            return Optional.empty();
        }

        if (!Instant.now().isBefore(record.expiresAt())) {
            tokens.remove(key, record);
            return Optional.empty();
        }

        var granted = record.authorityNames().stream()
            .map(SimpleGrantedAuthority::new)
            .toList();

        Authentication result = UsernamePasswordAuthenticationToken.authenticated(
            record.username(), null, granted
        );
        return Optional.of(result);
    }

    private static String fingerprint(String token) {
        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            byte[] digest = sha256.digest(
                token.getBytes(StandardCharsets.US_ASCII)
            );
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
~~~

**Giải thích:**

- Token tạo từ **32 byte random** có entropy rất cao; chuỗi được URL-safe Base64 encode thành 43 ký tự, không phải username/password.
- Map chỉ lưu **SHA-256 fingerprint của token**, không giữ plaintext token làm key; đây chỉ là cách giảm phơi bày dữ liệu trong RAM, không phải giải pháp thay thế vault/KMS hoặc kiểm soát bộ nhớ.
- TTL được kiểm tra khi dùng token. Nếu token expired, trả empty và xóa mục tương ứng. Token không được truy cập sau expiry có thể vẫn nằm trong map, nên store production cần **TTL eviction thực sự**.
- Authorities được snapshot tại thời điểm phát token. Nếu admin thu hồi quyền hoặc khóa account, token cũ trong demo **có thể còn dùng được đến hết TTL**, vì không truy vấn database lại mỗi request. Production cần chính sách revoke/revalidation/risk-appropriate lifetime.
- `UsernamePasswordAuthenticationToken.authenticated(...)` ở đây chỉ được tạo **sau khi** tìm thấy token ngẫu nhiên đã phát hành và còn hiệu lực trong token store do server kiểm soát. Tuyệt đối không làm điều tương tự từ role do client tự cung cấp.
- `ConcurrentHashMap` chỉ an toàn trong **một JVM**, không phải session store phân tán và không cung cấp auditing, concurrency policy hay cluster synchronization cho hệ thống thật.

### 7.4. BearerTokenFilter: xác minh mỗi request

**`src/main/java/com/example/restauth/BearerTokenFilter.java`**

~~~java
package com.example.restauth;

import java.io.IOException;
import java.util.Optional;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class BearerTokenFilter extends OncePerRequestFilter {

    private final TokenService tokens;
    private final ObjectMapper mapper;

    public BearerTokenFilter(TokenService tokens, ObjectMapper mapper) {
        this.tokens = tokens;
        this.mapper = mapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();

        // Đăng nhập kiểm tra username/password; không dùng Bearer cũ.
        return !path.startsWith("/api/")
            || path.equals("/api/auth/login");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String authorization = request.getHeader("Authorization");

        if (authorization == null) {
            // URL công khai hoặc anonymous sẽ được authorizeHttpRequests xét.
            chain.doFilter(request, response);
            return;
        }

        if (!authorization.startsWith("Bearer ")) {
            reject(response);
            return;
        }

        String rawToken = authorization.substring("Bearer ".length());
        Optional<Authentication> authenticated = tokens.authenticate(rawToken);

        if (authenticated.isEmpty()) {
            reject(response);
            return;
        }

        // Tạo context MỚI cho request hiện tại, không sửa instance cũ.
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated.get());
        SecurityContextHolder.setContext(context);

        // SecurityContextHolderFilter của Spring Security quản lý dọn holder.
        chain.doFilter(request, response);
    }

    private void reject(HttpServletResponse response) throws IOException {
        ApiErrors.write(mapper, response,
            HttpServletResponse.SC_UNAUTHORIZED,
            "UNAUTHORIZED",
            "Yêu cầu xác thực hợp lệ.");
    }
}
~~~

**Điểm cần tránh:** lớp filter này **không gắn `@Component` và không được khai báo làm Servlet `Filter` bean**. Nó được tạo trong `SecurityConfig` và thêm **chỉ một lần** bằng `http.addFilterBefore(...)`. Nếu một `Filter` vừa là Spring bean được Boot tự đăng ký ở servlet container, vừa được thêm vào security filter chain, nó có thể chạy hai lần hoặc sai thứ tự.

Đây là parser/token filter **tối giản cho demo**, chỉ nhận đúng dạng `Bearer <43 ký tự Base64URL>`. Theo chuẩn HTTP, authentication scheme có quy tắc parsing/case riêng; production nên dùng **Spring Security OAuth2 Resource Server** hoặc một implementation Bearer parser được kiểm định, không sao chép parser này nguyên trạng.

### 7.5. SecurityConfig: AuthenticationManager và JSON 401/403

**`src/main/java/com/example/restauth/SecurityConfig.java`**

~~~java
package com.example.restauth;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        String hash = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(hash)
                .roles("USER")
                .build(),

            User.withUsername("admin")
                .password(hash)
                .roles("ADMIN")
                .build(),

            User.withUsername("locked")
                .password(hash)
                .roles("USER")
                .accountLocked(true)
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(userDetailsService);
        provider.setPasswordEncoder(passwordEncoder);
        return new ProviderManager(provider);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            TokenService tokens,
            ObjectMapper mapper) throws Exception {

        // Tạo instance filter riêng, không để Boot auto-register
        // như Servlet Filter ngoài Spring Security.
        BearerTokenFilter bearerFilter = new BearerTokenFilter(tokens, mapper);

        return http
            // CHỈ hợp lý cho stateless Bearer header, không dùng session cookie.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(AbstractHttpConfigurer::disable)
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .logout(AbstractHttpConfigurer::disable)

            .exceptionHandling(ex -> ex
                .authenticationEntryPoint((request, response, exception) ->
                    ApiErrors.write(mapper, response, 401,
                        "UNAUTHORIZED",
                        "Yêu cầu xác thực hợp lệ."))
                .accessDeniedHandler((request, response, exception) ->
                    ApiErrors.write(mapper, response, 403,
                        "FORBIDDEN",
                        "Không có quyền truy cập tài nguyên."))
            )

            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/auth/login").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )

            .addFilterBefore(
                bearerFilter,
                UsernamePasswordAuthenticationFilter.class
            )
            .build();
    }
}
~~~

Trong ví dụ này, `httpBasic` và `formLogin` bị tắt để **không redirect 302** hoặc sinh HTML login cho API. Controller tự nhận JSON username/password. `csrf` bị disable **vì mô hình demo stateless không dùng cookie làm credential**; đừng copy cấu hình này vào web session/cookie app. `ExceptionTranslationFilter` và các handler tùy chỉnh trả response JSON trong trường hợp 401/403 của tài nguyên.

### 7.6. ApiController: 200, 400, 401 và API bảo vệ

**`src/main/java/com/example/restauth/ApiController.java`**

~~~java
package com.example.restauth;

import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    private final AuthenticationManager authenticationManager;
    private final TokenService tokens;

    public ApiController(
            AuthenticationManager authenticationManager,
            TokenService tokens) {
        this.authenticationManager = authenticationManager;
        this.tokens = tokens;
    }

    public record LoginRequest(String username, String password) {
    }

    public record LoginSuccess(
        String tokenType,
        String accessToken,
        long expiresIn
    ) {
    }

    public record Profile(String username) {
    }

    @PostMapping(
        path = "/auth/login",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> login(@RequestBody LoginRequest request) {
        if (request == null ||
            request.username() == null || request.username().isBlank() ||
            request.password() == null || request.password().isBlank()) {

            return ResponseEntity.badRequest()
                .cacheControl(CacheControl.noStore())
                .body(new ApiError(
                    "INVALID_REQUEST", "Yêu cầu không hợp lệ."));
        }

        try {
            Authentication authenticated = authenticationManager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    request.username(), request.password()
                )
            );

            String token = tokens.issue(authenticated);
            return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new LoginSuccess(
                    "Bearer", token, TokenService.TOKEN_SECONDS));

        } catch (AuthenticationException ex) {
            // Mọi lỗi credentials/account state có cùng public response.
            // Không trả ex.getMessage() hoặc class của exception.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .cacheControl(CacheControl.noStore())
                .body(new ApiError(
                    "AUTHENTICATION_FAILED",
                    "Thông tin đăng nhập không hợp lệ."));
        }
    }

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/me")
    public Profile me(Authentication authentication) {
        return new Profile(authentication.getName());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("status", "admin-ok");
    }
}
~~~

Đây là **mô hình custom login trong REST controller**: `AuthenticationManager` quyết định xác thực; controller quyết định HTTP response; không cần `formLogin().successHandler(...)` hoặc `failureHandler(...)` cho route này. Token phát hành sau authentication thành công **không tự cập nhật session**, và client phải gửi lại token cho từng request.

Nếu authentication thành công mà việc phát token gặp lỗi hệ thống, không nên trả 200 “login succeeded” giả khi client thực tế chưa có credential dùng tiếp. Hãy trả 5xx an toàn qua error handling và alert vận hành. Không bắt mọi `RuntimeException` rồi đổi thành 401; điều đó che lấp lỗi hạ tầng.

### 7.7. ApiExceptionAdvice: lỗi JSON sai cũng là JSON

**`src/main/java/com/example/restauth/ApiExceptionAdvice.java`**

~~~java
package com.example.restauth;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadableJson(
            HttpMessageNotReadableException exception) {

        // Không trả exception.getMessage(): có thể lộ chi tiết parser.
        return ResponseEntity.badRequest()
            .cacheControl(CacheControl.noStore())
            .body(new ApiError(
                "INVALID_REQUEST", "Yêu cầu không hợp lệ."));
    }
}
~~~

Adviser này xử lý JSON không đọc được. Những lỗi khác như unsupported media type 415, method not allowed 405, validation tùy biến, 404 và 5xx có thể cần error contract riêng nếu dự án yêu cầu **mọi** response lỗi đều cùng JSON schema. Không trả stack trace công khai; ở production hãy có error handling và observability tổng thể.

### 7.8. Test với Spring Security MockMvc

**`src/test/java/com/example/restauth/AuthApiTests.java`**

~~~java
package com.example.restauth;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthApiTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    private MvcResult login(String username, String password)
            throws Exception {

        return mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of(
                    "username", username,
                    "password", password
                ))))
            .andReturn();
    }

    private String successfulToken(String username) throws Exception {
        MvcResult login = mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of(
                    "username", username,
                    "password", "demo-pass"
                ))))
            .andExpect(status().isOk())
            .andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.tokenType").value("Bearer"))
            .andExpect(jsonPath("$.accessToken").isNotEmpty())
            .andExpect(jsonPath("$.expiresIn").value(900))
            .andReturn();

        return mapper.readTree(
            login.getResponse().getContentAsString()
        ).get("accessToken").asText();
    }

    @Test
    void loginAndReadResource() throws Exception {
        String token = successfulToken("alice");

        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void allCredentialFailuresAreGeneric() throws Exception {
        for (Map<String, String> credentials : new Map[] {
                Map.of("username", "alice", "password", "wrong"),
                Map.of("username", "does-not-exist", "password", "demo-pass"),
                Map.of("username", "locked", "password", "demo-pass")
        }) {
            mvc.perform(post("/api/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(mapper.writeValueAsString(credentials)))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("AUTHENTICATION_FAILED"))
                .andExpect(jsonPath("$.message").value(
                    "Thông tin đăng nhập không hợp lệ."));
        }
    }

    @Test
    void invalidJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not valid json"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void missingAndFakeBearerAreUnauthorized() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
            .andExpect(header().string("WWW-Authenticate", "Bearer"));

        mvc.perform(get("/api/me")
                .header("Authorization", "Bearer not-a-real-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    }

    @Test
    void validUserWithoutRoleGetsForbidden() throws Exception {
        String token = successfulToken("alice");

        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("FORBIDDEN"));
    }

    @Test
    void adminTokenCanAccessAdmin() throws Exception {
        String token = successfulToken("admin");

        mvc.perform(get("/api/admin")
                .header("Authorization", "Bearer " + token))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("admin-ok"));
    }
}
~~~

**Lưu ý kỹ thuật về test:** Trong `allCredentialFailuresAreGeneric`, mã Java dùng mảng generic `Map[]` để gộp các trường hợp; một số compiler có thể cảnh báo `unchecked` với foreach. Cảnh báo không ảnh hưởng kết quả nhưng trong code production nên chuyển thành `List.of(Map.of(...), ...)` để type-safe. Có thể dùng cùng nguyên tắc khi mở rộng test với disabled/expired.

Nhóm test này không dùng `@WithMockUser` để giả lập thành công đăng nhập vì cần kiểm tra **đường đi thật của credential JSON và token**. `@WithMockUser` hữu ích cho test authorization riêng, nhưng không chứng minh endpoint login hoặc token service hoạt động.

### 7.9. Chạy project và quan sát

Cần JDK 17+, Maven và tải dependency khi build lần đầu:

~~~bash
mvn test
mvn spring-boot:run
~~~

Kết quả **kỳ vọng** sau `mvn test` là build/test thành công, nếu môi trường có dependency phù hợp. Những test và lệnh này **chưa được thực thi trong tài liệu**, nên không coi kết quả là số liệu quan sát trực tiếp.

Ở terminal khác, dùng curl (PowerShell có thể cần `curl.exe`):

~~~bash
curl -i http://localhost:8080/api/public
# Dự kiến 200; body {"status":"public-ok"}

curl -i http://localhost:8080/api/me
# Dự kiến 401; JSON code UNAUTHORIZED

curl -i -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"wrong"}'
# Dự kiến 401; JSON code AUTHENTICATION_FAILED

curl -i -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"demo-pass"}'
# Dự kiến 200; JSON tokenType, accessToken, expiresIn
~~~

**Không copy token thật vào tài liệu/log/chat.** Trong môi trường học tập, lấy giá trị `accessToken` từ response ngay trên máy local, rồi gọi:

~~~bash
curl -i http://localhost:8080/api/me \
  -H 'Authorization: Bearer REPLACE_WITH_TEST_TOKEN'
# Dự kiến 200; {"username":"alice"}

curl -i http://localhost:8080/api/admin \
  -H 'Authorization: Bearer REPLACE_WITH_TEST_TOKEN'
# Dự kiến 403; {"code":"FORBIDDEN",...}
~~~

Hai dòng dùng `REPLACE_WITH_TEST_TOKEN` chỉ là placeholder trong lệnh minh họa, **không phải token hợp lệ**. Với token admin lấy từ login bằng username `admin` và password `demo-pass`, request `GET /api/admin` sẽ nhận JSON `{"status":"admin-ok"}`.

**Các kết quả mẫu không phải bằng chứng code đã chạy.** Việc build và kiểm thử thực tế cần Maven/JDK, runtime log và quan sát HTTP tương ứng; mọi chỉnh sửa vào API contract phải cập nhật test.

## 8. Tại sao 401, 403 và 302 khác nhau trong Spring Security?

### 8.1. Request chưa authenticated

Khi `GET /api/me` thiếu Bearer token, `BearerTokenFilter` cho request tiếp tục với security context không có user. Rule `anyRequest().authenticated()` yêu cầu user, `ExceptionTranslationFilter` dùng `AuthenticationEntryPoint` để trả **401 JSON**. Không bật form login nên không chuyển `302 /login`.

### 8.2. Token có nhưng không hợp lệ

Nếu client gửi `Authorization: Bearer xyz`, filter kiểm tra format và token store, rồi chủ động trả **401 JSON** thống nhất. Không đưa chi tiết “token tồn tại nhưng vừa hết hạn” vào response. Client chỉ cần biết phải lấy lại credential hợp lệ.

### 8.3. Token hợp lệ nhưng thiếu role

Khi client có token hợp lệ của alice với authority `ROLE_USER`, filter tạo `Authentication` và gắn vào context; yêu cầu `/api/admin` đòi `ROLE_ADMIN` nên `AccessDeniedHandler` trả **403 JSON**. Đây không phải lỗi username/password của lần login trước.

### 8.4. JSON login sai

Khi client gửi sai mật khẩu, `DaoAuthenticationProvider` ném `AuthenticationException` và controller bắt **đúng loại ngoại lệ đó** để trả 401. Không bắt `Exception` rồi coi mọi sự cố database, serialization, token store là “bad credentials”.

### 8.5. JSON không hợp lệ

Parser của Spring MVC ném `HttpMessageNotReadableException`; `@RestControllerAdvice` trả **400 JSON**. Lỗi parser không nằm trong `AuthenticationManager` nên không đi qua `AuthenticationFailureHandler`. Đây là một điểm quan trọng khi tự viết REST login.

## 9. Những rủi ro khi viết custom REST authentication

### 9.1. Không dựa vào status một mình để xác định lỗi

Client nên dùng cả HTTP status và mã `code` ổn định. Ví dụ 401 từ login và 401 từ protected resource đều mang ý nghĩa chưa xác thực, nhưng hướng xử lý có thể khác: login 401 yêu cầu kiểm tra credentials; resource 401 có thể yêu cầu token mới. Dù vậy, không để sự khác biệt trở thành kênh lộ trạng thái account.

### 9.2. Đừng tiết lộ lý do xác thực nội bộ

Cùng 401 public cho password sai, username không tồn tại và account locked/disabled là khuyến nghị thực tế để giảm user enumeration. Tuy nhiên **phản hồi giống nhau chưa đủ** nếu timing, response size, headers, rate-limit policy hoặc các endpoint recovery khác cho thấy trạng thái account.

Cần rate limiting theo tín hiệu phù hợp, detection, audit, MFA và quy trình recovery có xác minh danh tính. Không phát lại exception message/class hoặc raw username/password vào URL và log.

### 9.3. Tránh tự quản lý token khi đã có hạ tầng tiêu chuẩn

Demo dùng opaque token tự viết để thấy 200/401/403. Trong production:

- Ưu tiên **Spring Security OAuth2 Resource Server** với JWT/opaque token introspection, hoặc authorization server/IdP được vận hành đúng.
- Thiết lập expiry, refresh, revoke/blacklist, rotation, issuer/audience/scope, transport HTTPS, protection trước XSS/token theft.
- Có store phân tán với TTL eviction, phân quyền truy cập, audit, khả năng mở rộng và xử lý lúc backend restart.
- Không đưa token vào query string hoặc HTML, không log Authorization header và không trả token trong exception.
- Với JWT, không chỉ đọc payload; phải xác minh chữ ký/thuật toán/khoá/claims theo cấu hình tin cậy.

### 9.4. Authorization vẫn phải kiểm tra nghiệp vụ

Token hợp lệ không đồng nghĩa người dùng có thể xem mọi dữ liệu. Khi truy cập order, invoice hoặc dữ liệu đa tenant, service cần kiểm tra **ownership, tenant scope, quyền theo đối tượng**, không chỉ `authenticated()`. 403 hoặc 404 theo chính sách che giấu tài nguyên có thể phù hợp; không tiết lộ sự tồn tại của đối tượng nhạy cảm nếu không có quyền.

### 9.5. CSRF và CORS không phải một vấn đề

Trong demo, client gắn Bearer token bằng header và server không sử dụng session cookie làm auth credential, nên tắt CSRF trong security config có cơ sở đối với mô hình đó. Nếu trình duyệt dùng cookie hoặc HTTP Basic được gửi tự động, nguy cơ CSRF phải được đánh giá riêng. **CORS không thay thế CSRF** và không phải authentication; nó giới hạn việc browser đọc/gửi cross-origin theo policy, không ngăn client ngoài browser gọi API.

### 9.6. Ghi log và observability

Log nên có request ID, endpoint, timestamp, loại failure nội bộ đã được chuẩn hóa và context vận hành tối thiểu với quyền truy cập phù hợp. Không ghi plaintext password, token, cookie, full Authorization header, stack trace ra response. Khi output lỗi công khai thống nhất, observability nội bộ vẫn phải đủ để xử lý lỗi hạ tầng thay vì biến tất cả thành 401.

### 9.7. Cache và dữ liệu cá nhân

Response cấp access token phải có `Cache-Control: no-store`, dùng HTTPS, hạn chế thông tin người dùng. Resource có dữ liệu nhạy cảm cũng cần policy cache phù hợp. Đừng dựa vào response JSON chỉ chứa username trong demo để suy luận mọi profile cá nhân đều có thể cache công khai.

## 10. Checklist kiểm thử trước khi đưa REST login vào production

**Đầu vào và authentication**

1. JSON đúng schema + credentials đúng → 200 với token theo contract.
2. Username không tồn tại, password sai, account locked/disabled/expired → 401 với thông báo chung, không lộ user state.
3. JSON malformed hoặc thiếu field → 400 JSON, không leak parser stack trace.
4. Sai `Content-Type`/method → policy 415/405 hoặc error mapping nhất quán.
5. Tốc độ thử login lớn → chính sách throttling/rate limit/audit; không chỉ trông chờ BCrypt cost.

**Token và authorization**

6. Không gửi Bearer → 401 + challenge phù hợp.
7. Token bị sửa, sai format, hết hạn, đã revoke → 401.
8. Token hợp lệ nhưng thiếu quyền → 403.
9. Token hợp lệ và đủ quyền → endpoint trả đúng dữ liệu.
10. Token user A không đọc/sửa dữ liệu chỉ thuộc user B; tenant isolation được test.
11. Restart/redeploy/multi-instance/secret rotation hoạt động theo thiết kế production, không phụ thuộc memory store demo.

**Response và vòng đời**

12. Lỗi 401/403 có `Content-Type` phù hợp, schema JSON ổn định, không redirect 302/HTML bất ngờ.
13. Login success không gửi password/secret; token nằm trong field đã quy định với `Cache-Control: no-store`.
14. Hệ thống log không chứa token/password/Authorization header.
15. Client xử lý expiration, refresh/logout, retry và 429 theo contract; không lặp vô hạn khi 401.
16. CORS/CSRF, HTTPS, security headers, session policy phù hợp loại credentials thực tế.
17. Kiểm tra lỗi 5xx, DB outage, token store outage; không ngụy trang mọi lỗi vận hành thành “bad credentials”.

## 11. Các hiểu nhầm phổ biến

| Hiểu nhầm | Điều đúng |
| --- | --- |
| “Đăng nhập sai trả 403 vì không có quyền.” | Credentials không hợp lệ thường là **401**; đã xác thực nhưng thiếu role mới thường là **403** |
| “REST login có thể dùng `failureUrl` để chuyển tới HTML.” | API client thường cần **JSON/status ổn định**, không redirect form |
| “Dùng `AuthenticationSuccessHandler` thì session/token được tạo tự động trong mọi custom filter.” | Success handler chỉ phản hồi theo code của bạn; persistence/issuance phải được cấu hình đúng |
| “Trả 200 với body success=false cho mọi lỗi là đủ.” | HTTP status vẫn cần đúng để client và hạ tầng xử lý |
| “`AuthenticationFailureHandler` xử lý được mọi 403 và JSON parse failure.” | Nó xử lý authentication failure tại filter, không bao trùm MVC validation/authorization/CSRF |
| “User không tồn tại nên trả USER_NOT_FOUND cho dễ debug.” | Dễ tạo user enumeration; public thường nên dùng lỗi credentials chung |
| “Có Bearer token thì token chắc chắn còn hợp lệ.” | Cần xác minh issuer/store, expiry, scope và chính sách revoke |
| “Đã trả 200 token thì tài khoản luôn được phép gọi mọi endpoint.” | Authorization vẫn phải kiểm tra role/permission/ownership |
| “Đặt token trong URL giúp client tiện hơn.” | URL dễ bị lưu ở log/history/referrer; dùng Authorization header |
| “Cứ tắt CSRF cho mọi REST API.” | Phụ thuộc credentials; **cookie-based auth vẫn cần đánh giá CSRF** |
| “Đăng ký filter làm @Component rồi addFilterBefore lần nữa.” | Có thể bị Boot đăng ký ngoài Security chain và chạy hai lần |
| “Token lưu trong ConcurrentHashMap là token service production.” | Không có phân tán, TTL eviction, revoke, audit và bền vững |
| “Cùng 401 JSON là đã chống được mọi enumeration.” | Còn timing, header, response size, recovery endpoint và rate-limit behavior |
| “Catch(Exception) rồi return 401 giúp API đơn giản.” | Che lỗi hạ tầng và tạo contract sai, gây khó phát hiện sự cố |

## 12. Tự kiểm tra

**1.** API login nhận đúng JSON nhưng password sai. Nên trả gì?

**Đáp:** Thường **401** và mã lỗi công khai chung như `AUTHENTICATION_FAILED`; không khẳng định username tồn tại hoặc bị khóa.

**2.** User đã đăng nhập và gửi Bearer token hợp lệ nhưng thiếu `ROLE_ADMIN` cho `/api/admin`?

**Đáp:** Thường **403** từ authorization/`AccessDeniedHandler`; không phải lỗi login để đưa vào `AuthenticationFailureHandler`.

**3.** Body `POST /api/auth/login` chứa JSON sai cú pháp?

**Đáp:** **400** từ MVC exception handling; chưa phải trường hợp password sai.

**4.** `AuthenticationSuccessHandler` tự động cấp JWT hoặc lưu session chứ?

**Đáp:** Không. Thành phần xử lý phải chủ động dùng cơ chế cấp token/lưu security context phù hợp. 200 không tự tạo quyền cho request sau.

**5.** Tại sao resource API không nên redirect `302 /login` khi thiếu token?

**Đáp:** API client cần HTTP 401 JSON/challenge phù hợp để biết cần credential; redirect HTML làm hỏng contract và retry logic.

**6.** Vì sao không gửi `LockedException` và thông điệp account disabled ra response?

**Đáp:** Trạng thái này giúp người chưa xác thực dò user và hiểu trạng thái nội bộ. Giữ phản hồi public chung, audit nội bộ an toàn và dùng recovery sau khi đã xác minh danh tính.

**7.** Vì sao ví dụ dùng `SecurityContextHolder.createEmptyContext()` trong bearer filter?

**Đáp:** Để gắn `Authentication` đã xác minh vào một `SecurityContext` mới cho request hiện tại; không sửa context có thể được chia sẻ từ nguồn khác.

**8.** Nếu ứng dụng thật dùng cookie/session thay Bearer header thì có thể copy nguyên `csrf.disable()` không?

**Đáp:** Không. Credentials do browser tự gửi có nguy cơ CSRF; phải thiết kế CSRF/cookie/session policy phù hợp.

**9.** Tại sao token tự tạo lưu trong memory của ví dụ không dùng ngay cho nhiều server production?

**Đáp:** Mỗi JVM có map riêng, restart mất token, không có store phân tán, revoke hoặc TTL eviction hoàn chỉnh. Cần hạ tầng token đáng tin cậy.

**10.** Khi xác thực thất bại do database outage, catch mọi `Exception` rồi trả 401 có đúng không?

**Đáp:** Không. Lỗi hệ thống cần được xử lý/giám sát như lỗi vận hành với 5xx phù hợp và thông điệp an toàn, không nên giả thành mật khẩu sai.

**Ghi nhớ:** **REST authentication response phải phản ánh đúng trạng thái: 200 khi đăng nhập thành công, 400 khi request sai, 401 khi chưa xác thực hợp lệ, 403 khi đã xác thực nhưng thiếu quyền.** Dùng JSON contract ổn định, không lộ account state, tách controller/filter success-failure khỏi entry point/access denied, và quản lý token/session nhất quán với cơ chế đã chọn.