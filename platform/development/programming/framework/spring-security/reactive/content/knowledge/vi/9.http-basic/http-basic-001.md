# Cơ chế HTTP Basic và cấu trúc tiêu đề Authorization

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** HTTP Basic  
> **Mục tiêu:** Đọc, tạo và giải thích chính xác `Authorization: Basic ...` theo RFC 7617; hiểu challenge `401/WWW-Authenticate`, quy tắc username/password/charset, và biết tích hợp, thử nghiệm, bảo vệ HTTP Basic trong Spring Security WebFlux.

## 1. HTTP Basic giải quyết vấn đề gì?

HTTP Basic Authentication là một **HTTP authentication scheme** dùng cặp **user-id (username)** và **password** để chứng minh danh tính với HTTP server. Thay vì gửi một JSON login để đổi token, client thường gửi một HTTP header cùng những request cần xác thực:

```http
GET /api/private HTTP/1.1
Host: example.test
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

Đây là ví dụ chuẩn trong **RFC 7617**: giá trị Base64 biểu diễn chuỗi `Aladdin:open sesame`. Nó **không** phải một access token độc lập và **không** phải mật mã. Ai nhận được chuỗi Base64 này đều có thể giải mã và khôi phục username/password; chỉ có HTTPS/TLS bảo vệ dữ liệu trên đường truyền.

Một server có thể yêu cầu client xác thực bằng phản hồi **401 Unauthorized**:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="learning"
```

Sau đó client có thể gửi credentials. Một số HTTP client gửi `Authorization` ngay trong request đầu tiên (preemptive authentication), không cần chờ một lần challenge. Cả hai cách đều dùng cùng cấu trúc Basic.

Đừng nhầm:

- **Authentication:** Cặp user/password có thật và hợp lệ không?
- **Authorization:** Người dùng đã xác thực có được thực hiện hành động/đọc tài nguyên này không?
- **Authorization header:** Tên HTTP header dùng để truyền credentials theo một authentication scheme. Header này **không tự trao quyền**; server vẫn phải xác thực và kiểm tra authorization.

### Sau bài học, bạn có thể

1. Dựng `Authorization: Basic <base64(user-id:password)>` và giải thích chính xác từng phần.
2. Phân biệt header request `Authorization` với header response `WWW-Authenticate`, status **401** với **403**, và Basic với Bearer.
3. Xử lý đúng dấu hai chấm đầu tiên, giới hạn ký tự username và tùy chọn `charset="UTF-8"` của challenge.
4. Giải thích vai trò của `AuthenticationWebFilter`, converter, `ReactiveAuthenticationManager`, `SecurityContext` và authorization trong WebFlux.
5. Chạy một ứng dụng Spring Boot WebFlux dùng HTTP Basic, kiểm thử nhiều trường hợp với `WebTestClient`.
6. Nhận diện các rủi ro: Base64 không bảo mật, TLS, cache credentials của browser, log/proxy, credential replay, CSRF và giới hạn vận hành.

## 2. Phân tích chính xác cấu trúc header Authorization

Cú pháp khái niệm theo RFC 7617:

```text
Authorization: Basic <token68>
                     |
                     +-- Base64(bytes(user-id + ":" + password))
```

Ví dụ:

```text
User-id:                Aladdin
Password:               open sesame
Chuỗi user-pass:        Aladdin:open sesame
Các byte US-ASCII:      41 6c 61 64 64 69 6e 3a 6f 70 ...
Mã hóa Base64:          QWxhZGRpbjpvcGVuIHNlc2FtZQ==
HTTP request header:    Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
```

| Thành phần | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `Authorization` | Tên HTTP request header | Không phải `WWW-Authenticate` của response |
| `Basic` | Tên authentication scheme | Scheme name so khớp không phân biệt chữ hoa/thường; nên ghi chuẩn là `Basic` |
| Dấu cách | Ngăn scheme và credentials | Đừng chèn `username=`, `password=` hay JSON |
| `QWxh...` | Giá trị Base64 dùng cú pháp `token68` | Không phải encryption, chữ ký số hay bearer token |
| Dấu `:` **trước khi mã hóa** | Ngăn username và password | **Dấu `:` đầu tiên** là dấu phân cách |
| Ký tự `=` cuối Base64 | Ký tự padding của Base64 khi cần | Không tự cắt hoặc thay bằng URL-safe Base64 không tương thích |

### 2.1. Các bước tạo header

Cho user-id `Aladdin` và password `open sesame`:

1. Ghép đúng thứ tự: `Aladdin:open sesame`.
2. Mã hóa chuỗi này thành bytes theo bảng mã phù hợp; với chuỗi ASCII mẫu thì UTF-8 và ISO-8859-1 cho cùng bytes.
3. Mã hóa bytes bằng **Base64 tiêu chuẩn**, không phải Base64URL.
4. Thêm tiền tố `Basic `.
5. Đặt vào request header `Authorization`, dùng **HTTPS** cho request thật.

Ở chiều server, bộ chuyển đổi Basic đọc header, kiểm tra scheme, giải mã Base64 và lấy username/password bằng cách chia tại **dấu hai chấm đầu tiên**. Sau đó component authentication mới kiểm tra mật khẩu với user store; việc giải mã thành công **chưa chứng minh** credentials hợp lệ.

### 2.2. Dấu hai chấm: quy tắc đặc biệt dễ sai

RFC 7617 quy định **username không được chứa dấu `:`**. Password **có thể chứa dấu `:`**. Ví dụ:

```text
Raw user-pass: reader:part:two:three
Username:      reader
Password:      part:two:three
```

Không dùng `raw.split(":")` rồi đòi chính xác hai phần: như vậy bạn sẽ phá vỡ password chứa dấu `:`. Trong đoạn minh họa tự giải mã, hãy dùng `indexOf(':')` và tách một lần. Không tự suy rằng server của framework sẽ chấp nhận mọi loại username/password: còn có validation, charset, account state và password encoder.

**Tên người dùng có dấu `:` là không thể biểu diễn hợp lệ** trong cú pháp user-pass này, dù Base64 vẫn encode được bytes. Ví dụ `reader:team:secret` luôn bị hiểu thành username `reader`, password `team:secret` theo ranh giới đầu tiên.

### 2.3. Base64 không phải mã hóa an toàn

Mọi người đều có thể làm phép ngược:

```text
"QWxhZGRpbjpvcGVuIHNlc2FtZQ=="
          |
          v
Base64 decode
          |
          v
"Aladdin:open sesame"
```

Không có secret key, IV, nonce, authentication tag hay kiểm tra tính toàn vẹn mật mã ở bước Base64. Base64 chỉ chuyển bytes sang ký tự có thể ghi trong header. Do đó:

- **HTTP không mã hóa** + Basic gần như gửi password ở dạng đọc được cho bất kỳ bên nào nhìn thấy traffic.
- **HTTPS/TLS** bảo vệ kết nối truyền tải; nhưng reverse proxy, application gateway, server, plugin client hoặc logging middleware ở điểm kết thúc TLS vẫn có thể truy cập header.
- Không lưu chuỗi Basic vào source code, screenshot, ticket, log, monitoring labels hoặc bản dump HTTP.
- Không dùng Base64 của password như một password hash để lưu trong database. Mật khẩu lưu trữ cần algorithm chuyên dụng như BCrypt/Argon2id hoặc encoder được chính sách bảo mật chấp thuận.

## 3. HTTP challenge/response: ai gửi header nào?

Hai header thường bị nhầm:

| Header | Chiều | Ai gửi? | Dùng khi nào? |
| --- | --- | --- | --- |
| `Authorization: Basic ...` | **Client → Server** | Client | Cung cấp credentials cho origin server |
| `WWW-Authenticate: Basic realm="..."` | **Server → Client** | Server | Challenge yêu cầu xác thực hoặc yêu cầu thử lại khi 401 |
| `Proxy-Authorization: Basic ...` | **Client → Proxy** | Client | Credentials dành cho HTTP proxy có authentication riêng |
| `Proxy-Authenticate: Basic realm="..."` | **Proxy → Client** | Proxy | Challenge proxy, thường cùng status 407 |

Không nhét username/password vào `WWW-Authenticate`: header đó mô tả thử thách phía server chứ không mang credentials của client. Không dùng `Proxy-Authorization` khi API origin thông thường yêu cầu `Authorization`.

### 3.1. Luồng có challenge

```text
      HTTP client                              API server
           |                                      |
           | GET /api/private                     |
           |------------------------------------->|
           |                                      | Chưa có credentials
           | 401 Unauthorized                     |
           | WWW-Authenticate: Basic realm="api" |
           |<-------------------------------------|
           |                                      |
           | GET /api/private                     |
           | Authorization: Basic <base64>        |
           |------------------------------------->|
           |                                      | Decode + authenticate
           |                                      | Sau đó authorize
           | 200 OK / 403 Forbidden / 401         |
           |<-------------------------------------|
```

**Không phải client nào cũng đợi challenge.** Với `curl -u`, `HttpHeaders.setBasicAuth`, Postman hoặc client API đã biết server cần Basic, chúng có thể gửi `Authorization` từ request đầu tiên. Điều này không làm thay đổi nghĩa của header.

### 3.2. 401 và 403 không thay thế cho nhau

| Tình huống | Kết quả điển hình trong API WebFlux dùng Basic |
| --- | --- |
| Không gửi credentials, endpoint yêu cầu đăng nhập | **401** với challenge Basic |
| Username không tồn tại / password sai | **401**; authentication thất bại |
| Header `Authorization` không phải Basic khi không bật cơ chế khác | Không có Basic authentication hợp lệ; endpoint protected thường **401** |
| Username/password đúng, có role yêu cầu | Controller có thể trả **200** |
| Username/password đúng nhưng thiếu role/authority | **403**, không phải “password sai” |
| Đường dẫn `permitAll`, không gửi credentials | **200** nếu controller thành công |
| Đường dẫn `permitAll`, lại gửi Basic credentials sai | Basic filter có thể thử xác thực trước và trả **401**; `permitAll` không có nghĩa bỏ qua credentials được gửi |

**401 = cần xác thực hợp lệ** (tên status Unauthorized là lịch sử HTTP, đừng suy nó luôn nói về permission). **403 = đã hiểu yêu cầu nhưng không cho phép**; trong demo dưới, principal đã xác thực nhưng thiếu role. Có hệ thống cố ý trả 404 để giấu tài nguyên, nhưng đó là chính sách khác và không thay đổi bản chất của Basic.

### 3.3. `realm` dùng làm gì?

Trong:

```http
WWW-Authenticate: Basic realm="internal-api"
```

`realm` là một phần của **authentication challenge** và cho client biết protection space/nhóm tài nguyên cần credentials. Theo RFC 7617, `realm` là **bắt buộc** trong Basic challenge. Chuỗi realm không phải password salt, không phải tenant ID đã được xác minh và không phải JWT audience. Đừng đặt dữ liệu nhạy cảm vào realm; một browser có thể hiển thị nó trong hộp thoại đăng nhập.

## 4. Charset và tiếng Việt/Unicode: phải phân biệt RFC với mặc định thư viện

Với username/password **chỉ US-ASCII**, cách chuyển chuỗi thành bytes thường cho cùng kết quả giữa UTF-8 và encoding legacy ASCII-compatible. Với ký tự Unicode (ví dụ `Nguyễn`, `mật-khẩu`), việc không thống nhất charset tạo ra header Base64 khác nhau, dẫn tới xác thực thất bại.

**RFC 7617 không ấn định một charset mặc định duy nhất** cho chuỗi user-pass lịch sử; default phải tương thích US-ASCII. Server **có thể** quảng bá kỳ vọng UTF-8 bằng tham số trên **challenge**:

```http
WWW-Authenticate: Basic realm="api", charset="UTF-8"
```

Các ý chính:

- Trong RFC 7617, giá trị được định nghĩa cho tham số `charset` là **`UTF-8`**. Tham số này ở `WWW-Authenticate`, **không phải** trong chuỗi `Authorization: Basic ...`.
- RFC kỳ vọng xử lý Unicode theo **Normalization Form C (NFC)** trước khi encode thành UTF-8 bytes. Hai chuỗi nhìn giống nhau nhưng tổ hợp Unicode khác nhau có thể không tạo cùng bytes nếu không chuẩn hóa thống nhất.
- Client cũ có thể bỏ qua `charset` hoặc dùng legacy encoding. Khi thiết kế API chấp nhận non-ASCII credentials, phải ghi rõ charset, cấu hình Spring Security/client, và kiểm thử liên thông.
- `HttpHeaders.setBasicAuth(username, password)` mặc định sử dụng **ISO-8859-1** trong Spring; overload `setBasicAuth(username, password, StandardCharsets.UTF_8)` cho phép chọn UTF-8. Không tự cho rằng mọi Basic client dùng UTF-8.
- Đừng sửa mật khẩu người dùng bằng cách tự trim, lowercase hay normalize tùy tiện. Mọi quy tắc về normalization phải thống nhất giữa đăng ký tài khoản, password hashing và authentication.

Ví dụ UTF-8 trong chính RFC 7617: user `test`, password `123£`; bytes UTF-8 của `test:123£` tạo Base64 `dGVzdDoxMjPCow==`. Đây là test vector để minh họa việc khác encoding tạo bytes khác nhau.

```http
Authorization: Basic dGVzdDoxMjPCow==
```

Chú ý: **không nên tự gắn thêm** `charset=UTF-8` ở sau token Base64 trên request header; trường `Authorization` của Basic dùng `token68`, không có chỗ cho tham số `charset` như challenge.

## 5. Vai trò của HTTP Basic trong Spring Security WebFlux

Trong ứng dụng reactive, không có Servlet `BasicAuthenticationFilter` chạy trên `HttpServletRequest`. Spring Security dùng hệ thống **`WebFilter`** và API reactive.

Luồng lý tưởng hóa:

```text
HTTP request: Authorization: Basic <encoded-user-pass>
         |
         v
Spring Security WebFilter chain
         |
         v
AuthenticationWebFilter  (HTTP Basic)
         |
         v
ServerHttpBasicAuthenticationConverter
    - Nhìn Authorization header
    - Nhận diện scheme Basic
    - Base64 decode user-pass
    - Tạo một Authentication CHƯA xác thực
         |
         v
ReactiveAuthenticationManager
    - Tra UserDetails bằng ReactiveUserDetailsService
    - So khớp password bằng PasswordEncoder
    - Kiểm tra trạng thái tài khoản
         |
       +-------------------------+
       |                         |
    Thành công                 Thất bại
       |                         |
       v                         v
Authentication đã xác thực  AuthenticationException
       |                         |
       v                         v
SecurityContext/Reactor      Failure handler /
Context cho downstream       authentication entry point
       |                         |
       v                         v
AuthorizationWebFilter          thường 401
       |
    +--+------------------------+
    |                           |
đủ quyền                    thiếu quyền
    |                           |
controller                  AccessDeniedException
    |                           |
200/khác                    ExceptionTranslationWebFilter
                                |
                             thường 403
```

Sơ đồ cố ý bỏ qua nhiều filter khác (CSRF, headers, CORS, request cache, context persistence...), không khẳng định mọi error đều do một filter duy nhất sinh ra. Trong WebFlux:

- `ServerHttpSecurity`: nơi cấu hình WebFlux security.
- `SecurityWebFilterChain`: chuỗi WebFilter phục vụ các request đã match.
- `ServerHttpBasicAuthenticationConverter`: đọc credentials Basic từ HTTP exchange.
- `AuthenticationWebFilter`: tổ chức quá trình xác thực reactive.
- `ReactiveAuthenticationManager`: quyết định username/password có hợp lệ không.
- `ReactiveUserDetailsService` / `MapReactiveUserDetailsService`: nguồn thông tin người dùng (in-memory cho demo).
- `PasswordEncoder`: xác minh mật khẩu với hash lưu trữ. **Không** so sánh raw Base64 với DB.
- `ReactiveSecurityContextHolder`: giúp đọc `Authentication` đã xác thực trong Reactor Context downstream.
- `AuthorizationWebFilter`: áp dụng rule `authenticated()`, `hasRole(...)`, `hasAuthority(...)`...
- `ExceptionTranslationWebFilter`: xử lý lỗi từ chối quyền theo trạng thái authentication, thường điều hướng tới challenge hoặc 403.

**Điểm quan trọng:** `Authorization` là header xuất hiện ở **mỗi request mà client chủ động gửi**. Basic protocol không bắt server bắt buộc phải cấp JWT hay session. Tùy cấu hình, Spring Security có thể tích hợp context repository/session; không được suy rằng mọi ứng dụng bật Basic đều tự động stateless.

### 5.1. So sánh Basic với Bearer và form login

| Tiêu chí | HTTP Basic | Bearer token/JWT | Form login/session |
| --- | --- | --- | --- |
| Header/trình tự điển hình | `Authorization: Basic <base64(user:pass)>` | `Authorization: Bearer <token>` | Form POST login, sau đó thường gửi cookie phiên |
| Credential gửi trên request | Username/password được biểu diễn bằng Base64 | Access token | Cookie/session ID sau login |
| Token cấp bởi server có bắt buộc? | **Không** | Thường **Có** | Có session/cookie nếu mô hình phiên |
| Cách server kiểm tra | Password hashing/user store hoặc auth backend | Chữ ký/introspection, expiry, scopes | Session store/identity |
| Nếu bị lộ | Lộ luôn password (có thể tái sử dụng) | Lộ token có thể bị dùng tới khi hết hạn/thu hồi | Lộ phiên/cookie có thể bị chiếm |
| Nơi phù hợp | Tooling, internal API qua HTTPS, trường hợp đơn giản có kiểm soát | API cần token, expiry/scope rõ | Web app browser-based có phiên |

**Không dùng Basic như một phương án thay thế đầy đủ cho OAuth2/OIDC/MFA** trong sản phẩm cần đăng nhập hiện đại, đăng nhập liên kết, thiết bị di động, vòng đời token hoặc phân quyền liên dịch vụ. Basic có thể phù hợp nhưng không tự cung cấp rate limit, session management, OAuth scopes hay MFA.

## 6. Java 17 thuần: tự dựng và giải thích header theo RFC 7617

Ví dụ này chạy **không cần Spring Boot**, mục tiêu là làm rõ wire format. Mọi credentials dưới đây đều là test vector công khai của RFC, **không dùng với tài khoản thật**.

### File `BasicHeaderExample.java`

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class BasicHeaderExample {

    public static void main(String[] args) {
        String userId = "Aladdin";
        String password = "open sesame";

        String userPass = userId + ":" + password;
        String token = Base64.getEncoder().encodeToString(
            userPass.getBytes(StandardCharsets.UTF_8));
        String header = "Basic " + token;

        // Chỉ in header vì đây là test vector công khai, không có bí mật thật.
        System.out.println("Authorization: " + header);

        String afterScheme = header.substring("Basic ".length());
        String decoded = new String(
            Base64.getDecoder().decode(afterScheme),
            StandardCharsets.UTF_8
        );

        int firstColon = decoded.indexOf(':');
        String decodedUser = decoded.substring(0, firstColon);
        String decodedPassword = decoded.substring(firstColon + 1);

        System.out.println("user-id=" + decodedUser);
        System.out.println("password-matches="
            + decodedPassword.equals("open sesame"));

        // Password có dấu hai chấm vẫn hợp lệ: chỉ tách dấu đầu tiên.
        String valueWithColons = "reader:a:b:c";
        int separator = valueWithColons.indexOf(':');
        String parsedUser = valueWithColons.substring(0, separator);
        String parsedPassword = valueWithColons.substring(separator + 1);

        System.out.println("colon-user=" + parsedUser);
        System.out.println("colon-password=" + parsedPassword);
    }
}
```

Lưu file và chạy:

```bash
javac BasicHeaderExample.java
java BasicHeaderExample
```

**Stdout chính xác:**

```text
Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==
user-id=Aladdin
password-matches=true
colon-user=reader
colon-password=a:b:c
```

**Bài học từ ví dụ:**

- `Base64.getEncoder()` dùng Base64 thông thường của RFC 4648.
- `getBytes(StandardCharsets.UTF_8)` chọn cách chuyển text sang bytes. Với test vector ASCII, kết quả khớp RFC.
- Lấy substring sau `"Basic "` chỉ có ý nghĩa trong ví dụ do **code tự tạo header hợp lệ**. Với request nhận từ mạng phải xử lý whitespace/scheme/token, Base64 lỗi, giới hạn độ dài header, encoding, thiếu colon và các trường hợp bất thường một cách an toàn. **Đừng tự tạo bộ xác thực production chỉ bằng đoạn này**.
- `decoded.indexOf(':')` tìm dấu phân cách đầu tiên, chứ không cắt password ở dấu `:` thứ hai.
- Một giá trị Base64 giải mã được **không chứng minh** rằng password đúng. Phải chuyển credentials cho authentication manager và password encoder.
- Việc in token chỉ dành cho RFC test vector. **Tuyệt đối không in header Authorization thật** ra console, log hoặc exception message.

## 7. Project WebFlux hoàn chỉnh: HTTP Basic trên API reactive

Chọn Java **17+**, Maven và Spring Boot **3.5.16** để có một baseline phát hành cụ thể; Spring Boot 3.5.16 là phiên bản cuối được hỗ trợ OSS của nhánh 3.5.x, **không phải lựa chọn production mới trong năm 2026**. Với hệ thống thực tế, chọn nhánh Spring Boot còn hỗ trợ OSS (ví dụ 4.x), rồi cập nhật API/versions theo migration guide. Các ví dụ bên dưới sử dụng Spring Security 6.x do Boot 3.5.x quản lý.

Cấu trúc file:

```text
reactive-http-basic-demo/
├── pom.xml
└── src/
    ├── main/java/demo/basic/
    │   ├── BasicApplication.java
    │   ├── SecurityConfig.java
    │   └── ApiController.java
    └── test/java/demo/basic/
        └── BasicAuthenticationTests.java
```

### 7.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-http-basic-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

`spring-boot-starter-webflux` đưa WebFlux/Reactor vào classpath; `spring-boot-starter-security` tích hợp WebFlux security; `starter-test` và `spring-security-test` dùng để chạy test. Không thêm `spring-boot-starter-web` của Servlet chỉ để phục vụ HTTP Basic; mục tiêu bài này là **reactive WebFilter**.

### 7.2. `src/main/java/demo/basic/BasicApplication.java`

```java
package demo.basic;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BasicApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicApplication.class, args);
    }
}
```

### 7.3. `src/main/java/demo/basic/SecurityConfig.java`

```java
package demo.basic;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Tài khoản/mật khẩu hard-coded chỉ dùng ở môi trường học.
        // Mật khẩu trong UserDetails vẫn được lưu ở dạng hash BCrypt.
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader123"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .roles("ADMIN")
            .build();

        UserDetails colon = User.withUsername("colon")
            .password(encoder.encode("part:two"))
            .roles("READER")
            .build();

        return new MapReactiveUserDetailsService(reader, admin, colon);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {

        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/admin").hasRole("ADMIN")
                .pathMatchers("/api/private", "/api/me").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Tại sao cấu hình này được viết như vậy?**

1. `@EnableWebFluxSecurity` cấu hình Spring Security cho **Spring WebFlux**; thành phần đầu ra là `SecurityWebFilterChain`.
2. `httpBasic(basic -> basic.authenticationManager(manager))` bật cơ chế Basic và chỉ định **reactive authentication manager** kiểm tra credentials. Đây là lambda DSL hiện đại của Spring Security 6, không phải Servlet `HttpSecurity`.
3. `MapReactiveUserDetailsService` là user store in-memory. `UserDetailsRepositoryReactiveAuthenticationManager` lấy UserDetails, đối chiếu password qua `PasswordEncoder`.
4. `BCryptPasswordEncoder` băm password trong user store của demo. Server nhận **raw password** qua Basic nhưng so khớp với **hash BCrypt**, không lấy Base64 làm password hash.
5. `roles("ADMIN")` tạo authority `ROLE_ADMIN`; `hasRole("ADMIN")` đòi authority này. User `reader` đăng nhập hợp lệ vẫn bị 403 ở `/api/admin`.
6. User `colon` có password `part:two` minh họa **dấu hai chấm trong password vẫn hợp lệ**: Basic lấy username trước dấu hai chấm đầu tiên, password là phần còn lại.
7. `formLogin(form -> form.disable())` tắt form login redirect để ví dụ tập trung vào Basic; ứng dụng vẫn được bảo vệ ở HTTP layer.
8. Ví dụ chỉ có GET, không tắt CSRF; nếu thêm POST hoặc ứng dụng browser tự gửi Basic credentials, cần đánh giá CSRF theo mô hình client.

**Đặc điểm production:** Băm BCrypt trong demo xảy ra lúc khởi động vì hard-coded password chỉ để luyện tập. Hệ thống thật không đặt mật khẩu thực vào source; lấy hash từ user repository an toàn, có HTTPS, theo dõi authentication failures và bảo vệ brute force.

### 7.4. `src/main/java/demo/basic/ApiController.java`

```java
package demo.basic;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    @GetMapping("/private")
    public Mono<String> privateInfo() {
        return Mono.just("private OK");
    }

    @GetMapping("/admin")
    public Mono<String> adminInfo() {
        return Mono.just("admin OK");
    }

    @GetMapping("/me")
    public Mono<String> currentUser() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .map(name -> "user=" + name);
    }
}
```

Trong `/api/me`, username được lấy từ **Authentication của Spring Security**, không đọc `Authorization` rồi tự Base64-decode trong controller. Khi `ReactiveAuthenticationManager` xác thực thành công, Spring Security cung cấp SecurityContext cho reactive chain. Nếu bạn tự decode một Basic header trong business controller, bạn có thể bỏ qua kiểm tra hash, trạng thái tài khoản, authorization và khả năng bảo vệ của framework.

### 7.5. Client nào dùng header này?

Có ba cách gọi tương đương **về ý định** khi credentials thuộc ASCII:

```bash
# Client tự tạo Basic header qua curl.
curl -i -u reader:reader123 http://localhost:8080/api/private
```

```java
// Đoạn trong WebTestClient/WebClient request, không phải file Java độc lập:
.headers(headers -> headers.setBasicAuth("reader", "reader123"))
```

```http
GET /api/private HTTP/1.1
Host: localhost:8080
Authorization: Basic <base64-cua-reader:reader123>
```

Dòng HTTP cuối là **mẫu cấu trúc**, không phải header có thể gửi nguyên văn: placeholder phải được thay bằng Base64 thật của `reader:reader123`. Dùng `HttpHeaders.setBasicAuth` hoặc client library để tránh sai định dạng. Không tự copy nhầm password test `reader123` vào các hệ thống khác.

## 8. Kiểm thử HTTP Basic bằng WebTestClient

Để kiểm tra cơ chế Basic, phải gửi **Authorization header thật** hoặc dùng helper `setBasicAuth`; một `mockUser()` đã cấp sẵn Authentication không chứng minh parser Base64 hoặc password matching hoạt động.

Bộ test sau dùng `@SpringBootTest` để nạp đúng `SecurityConfig`, rồi `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` để chạy WebFilter chain trong test, không cần mở cổng mạng thật.

### `src/test/java/demo/basic/BasicAuthenticationTests.java`

```java
package demo.basic;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class BasicAuthenticationTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicGetWorksWithoutCredentials() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void protectedGetWithoutHeaderReturns401() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void correctUsernameAndPasswordAreAccepted() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void wrongPasswordReturns401() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUsernameReturns401() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("nobody", "reader123"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserWithoutRoleGets403() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminWithCorrectRoleGets200() {
        client.get().uri("/api/admin")
            .headers(h -> h.setBasicAuth("admin", "admin123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("admin OK");
    }

    @Test
    void basicHeaderCanBeBuiltByBase64() {
        String original = "reader:reader123";
        String encoded = Base64.getEncoder().encodeToString(
            original.getBytes(StandardCharsets.UTF_8));

        client.get().uri("/api/private")
            .header(HttpHeaders.AUTHORIZATION, "Basic " + encoded)
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void passwordMayContainColons() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("colon", "part:two"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("private OK");
    }

    @Test
    void securityContextProvidesAuthenticatedName() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("user=reader");
    }

    @Test
    void publicUrlWithWrongBasicCredentialsMayStillFail() {
        client.get().uri("/api/public")
            .headers(h -> h.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**11 test** này phân tách rõ ba lớp:

- **Wire format:** `basicHeaderCanBeBuiltByBase64` gửi tự tay `Authorization: Basic <encoded>`, không dùng `mockUser`.
- **Authentication:** Có/không credentials, username không tồn tại, password sai, password chứa dấu `:`.
- **Authorization:** User hợp lệ thiếu `ROLE_ADMIN` trả 403; admin hợp lệ trả 200.
- **Context reactive:** `/api/me` đọc người dùng được Spring Security xác thực.
- **Filter behavior:** Header Basic sai trên đường dẫn `permitAll` có thể vẫn kích hoạt authentication filter và dẫn đến 401. Test xác nhận hành vi với cấu hình hiện tại.

Nếu thay Basic bằng JWT hoặc session login, phải đổi cả cách gửi credentials lẫn test authentication; chỉ test `mockUser` không đủ chứng minh header parser hoặc password hash matching.

### 8.1. Ma trận phản hồi dự kiến

| HTTP request | Đầu vào | HTTP status dự kiến | Body thành công |
| --- | --- | --- | --- |
| `GET /api/public` | Không Basic | 200 | `public OK` |
| `GET /api/private` | Không Basic | **401** | Không cố định; có `WWW-Authenticate` |
| `GET /api/private` | `reader:reader123` | 200 | `private OK` |
| `GET /api/private` | `reader:wrong` | **401** | Không cố định |
| `GET /api/private` | `nobody:reader123` | **401** | Không cố định |
| `GET /api/admin` | `reader:reader123` | **403** | Không cố định |
| `GET /api/admin` | `admin:admin123` | 200 | `admin OK` |
| `GET /api/private` | Base64 của `reader:reader123` | 200 | `private OK` |
| `GET /api/private` | `colon:part:two` | 200 | `private OK` |
| `GET /api/me` | `reader:reader123` | 200 | `user=reader` |
| `GET /api/public` | `reader:wrong` | **401** | Không cố định |

Không kiểm tra JSON body của lỗi 401/403 trong ví dụ này: Spring Security/Boot có thể thay đổi body lỗi theo exception handling và content negotiation. Bài này quan tâm **Basic credentials và status/challenge**; nếu thiết kế REST error JSON thống nhất, hãy cấu hình handler riêng và test header/status/body tương ứng.

## 9. Chạy thử bằng Maven và curl

### 9.1. Chạy bộ test

Yêu cầu: **Java 17+** và Maven tương thích với Spring Boot 3.5. Từ thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Dự kiến Maven Surefire ghi **11 tests, 0 failures, 0 errors**, sau đó `BUILD SUCCESS`. Thời gian, plugin output và tên provider có thể khác theo môi trường. Đây là **kết quả kỳ vọng từ mã**, không phải khẳng định đã chạy trong mọi môi trường.

Nếu test không khởi động, kiểm tra Java version, `spring-boot-starter-webflux`, `spring-boot-starter-security`, `spring-boot-starter-test` và `spring-security-test`. Các class nằm dưới cùng root package `demo.basic` với `@SpringBootApplication`.

### 9.2. Khởi động WebFlux server

```bash
mvn spring-boot:run
```

Mặc định trong ví dụ này, server lắng nghe `localhost:8080` nếu cổng không bị thay đổi trong configuration.

Mở terminal thứ hai và gọi:

```bash
# Không credentials: public -> 200; private -> 401.
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private

# Đúng/sai Basic credentials.
curl -i -u reader:reader123 http://localhost:8080/api/private
curl -i -u reader:wrong http://localhost:8080/api/private

# Đúng danh tính nhưng thiếu role -> 403.
curl -i -u reader:reader123 http://localhost:8080/api/admin

# Admin đủ quyền -> 200.
curl -i -u admin:admin123 http://localhost:8080/api/admin

# Password có dấu :; username là colon, password là part:two.
curl -i -u colon:part:two http://localhost:8080/api/private

# Xem danh tính Spring Security đã xác thực.
curl -i -u reader:reader123 http://localhost:8080/api/me
```

Trên Windows PowerShell, có thể cần dùng `curl.exe` thay `curl`. Với API thật, nên dùng HTTPS và phương thức cấp credentials an toàn của client; `-u user:password` trong lệnh shell có thể bị lưu lại trong command history hoặc process inspection. Không dùng `curl -v`/proxy debug trên credentials thật nếu logs bị thu thập; hãy lọc header nhạy cảm.

### 9.3. Kiểm tra challenge từ server

```bash
curl -i http://localhost:8080/api/private
```

Một phản hồi điển hình:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

Giá trị `realm`, header phụ và body không phải cam kết của ví dụ; framework/config có thể khác. Điều test chính thức xác nhận là **401** và có **`WWW-Authenticate`**, không cố định realm.

### 9.4. Đừng hiểu lệnh `curl -u` như "mã hóa password"

Khi dùng `-u reader:reader123`, client tạo Basic header bằng Base64. Đây là **encoding của user-pass** để trình bày trên wire. Không có password hash từ client: **hash được lưu ở server**, còn server nhận password do client gửi qua kênh HTTPS rồi xác minh bằng BCrypt. Chỉ khi TLS bảo vệ kết nối, credentials mới được mã hóa trong quá trình truyền.

## 10. Cách gửi Basic trong các Java HTTP client

### 10.1. `HttpHeaders` của Spring

Trong Spring WebFlux `WebClient` hoặc `WebTestClient`, nên ưu tiên API dựng header thay vì tự ghép Base64 bằng tay:

```java
// Đoạn dùng trong builder/request của WebClient/WebTestClient:
.headers(headers -> headers.setBasicAuth("reader", "reader123"))
```

Với credentials Unicode, chọn charset tường minh và kiểm tra server thực sự hỗ trợ:

```java
.headers(headers ->
    headers.setBasicAuth("nguoi-dung", "mật-khẩu",
                         java.nio.charset.StandardCharsets.UTF_8))
```

Đây là snippet đặt trong lời gọi request có API `headers(Consumer<HttpHeaders>)`, không phải file Java độc lập. Nếu client/server muốn hỗ trợ Unicode đúng chuẩn RFC, kiểm tra cả `WWW-Authenticate: Basic ..., charset="UTF-8"` và normalization. Đừng suy `charset` tự được thêm vào header request.

### 10.2. WebClient dùng cho một API HTTP Basic

Một đoạn được đặt trong method của service có thể viết:

```java
WebClient client = WebClient.builder()
    .baseUrl("https://api.example.test")
    .build();

Mono<String> response = client.get()
    .uri("/api/private")
    .headers(headers -> headers.setBasicAuth("reader", "reader123"))
    .retrieve()
    .bodyToMono(String.class);
```

Đoạn này **minh họa API**, cần import `org.springframework.web.reactive.function.client.WebClient` và `reactor.core.publisher.Mono` cùng credentials được cấp qua cơ chế secret management trong ứng dụng thật. `https://api.example.test` là host giả, không phải endpoint có thể gọi ngay. Tránh gắn Basic header làm default cho một `WebClient` có thể được dùng để gọi **nhiều origin khác nhau**, vì nguy cơ gửi credentials sai đích.

### 10.3. `java.net.http.HttpClient` (Java 17)

JDK không bắt buộc dùng Spring để gửi header:

```java
String encoded = java.util.Base64.getEncoder().encodeToString(
    "reader:reader123".getBytes(java.nio.charset.StandardCharsets.UTF_8));

java.net.http.HttpRequest request = java.net.http.HttpRequest
    .newBuilder(java.net.URI.create("https://api.example.test/api/private"))
    .header("Authorization", "Basic " + encoded)
    .GET()
    .build();
```

Đây là đoạn dựng `HttpRequest`, **không thực hiện network request**. Khi thật sự gửi request, dùng `HttpClient` với TLS mặc định thích hợp, xử lý status 401/403 và tránh ghi header. Ưu tiên thư viện/credential provider hỗ trợ Basic chuẩn khi có thể, thay vì tự dựng header cho mọi tích hợp.

## 11. Các vấn đề bảo mật phải giải quyết ngoài Base64

### 11.1. Luôn dùng HTTPS/TLS và kiểm tra certificate

- Base64 có thể đảo ngược ngay; **Basic qua HTTP plaintext không an toàn**.
- Sử dụng HTTPS với validation chứng chỉ và hostname chuẩn. Tránh tắt certificate verification chỉ để "chạy được".
- Ở hệ thống có reverse proxy/TLS termination, cần bảo vệ hop từ proxy đến ứng dụng và tránh ghi log `Authorization` tại proxy.
- Cấu hình HSTS khi phù hợp với website và hạ tầng; chuyển hướng HTTP → HTTPS cần thiết kế để không rò rỉ credentials trong request HTTP ban đầu. Tốt nhất client chỉ gửi credentials tới URL HTTPS ngay từ đầu.

### 11.2. Basic gửi password lặp lại, không có expiry/scope riêng cho từng request

Client có thể gửi cùng username/password trên mọi request cần bảo vệ. Nếu password bị lộ, attacker có thể tiếp tục sử dụng tới khi password bị đổi/thu hồi tài khoản hoặc có biện pháp khác. HTTP Basic không tự cấp token ngắn hạn, refresh token, rotation hay phân biệt scope.

Hệ thống thật nên có password policy, MFA khi yêu cầu, chống brute-force/rate limit, credential rotation, thông báo bất thường, giới hạn truy cập và cách thay đổi/khóa tài khoản.

### 11.3. Browser có thể cache/replay credentials

Trình duyệt có thể lưu credentials Basic cho **protection space** tương ứng. Phương thức "logout Basic" không tương đương xóa một session server rõ ràng như form login. Việc gửi 401 hay đổi realm không phải luôn là phương pháp logout đáng tin cậy trên mọi browser.

Nếu frontend chạy trong browser và yêu cầu logout, nhiều phiên/thiết bị, MFA hoặc kiểm soát chính sách token, một kiến trúc dựa trên session/OIDC/OAuth2 thường thích hợp hơn HTTP Basic đơn thuần.

### 11.4. CSRF và CORS không tự biến mất vì dùng Basic

- **CSRF:** Trình duyệt có thể tự gắn lại credentials HTTP Basic cho các request trong protection space. Với thao tác thay đổi trạng thái từ browser, CSRF vẫn cần đánh giá. Không tắt CSRF chỉ vì "API dùng Basic" hoặc vì thấy 403 trong POST test.
- **CORS:** JavaScript cross-origin với `Authorization` header có thể phát sinh preflight; cần cấu hình `OPTIONS`, allowed origins, methods, headers và credential policy đúng. CORS không phải authentication, và `Access-Control-Allow-Origin` không chứng minh danh tính.
- **XSS:** Nếu một trang bị XSS hoặc JavaScript client quản lý credentials không đúng, kẻ tấn công có thể chiếm quyền sử dụng session/credentials. TLS không tự chữa XSS.

### 11.5. Những chỗ lộ secrets phổ biến

| Chỗ | Rủi ro | Phòng tránh |
| --- | --- | --- |
| HTTP access log / reverse proxy | Ghi `Authorization: Basic <...>`, dễ decode | Redact header `Authorization`; kiểm soát log retention |
| APM/trace/spans | Thu thập mọi request header làm tag | Không instrument secrets; dùng allowlist |
| Shell history/process list | `curl -u user:password` nằm trong command | Dùng cơ chế lấy secret an toàn, không ghi password trên command line production |
| Ticket/screenshot | Đính kèm trace gồm Base64 | Xóa/redact header trước khi chia sẻ |
| Source code/test fixture | Commit password thật | Dùng credentials giả cho test, secrets từ quản lý tập trung cho production |
| HTTP redirect | Client có thể gửi credential tới URL không mong muốn nếu cấu hình sai | Giới hạn origin/redirect; không tự forward Authorization tới host khác |
| Client connection không TLS | Bị nghe lén trên mạng | Bắt buộc HTTPS với certificate validation |

### 11.6. Rate limiting, user enumeration và password storage

Một API Basic thường phơi ra endpoint xác thực trên nhiều request. Cần:

- Dùng **password hashing** chậm phù hợp như BCrypt/Argon2id; không lưu raw password, không lưu raw Base64.
- Đối xử nhất quán khi username không tồn tại hoặc password sai, tránh phản hồi tiết lộ thông tin giúp dò tài khoản.
- Giới hạn tốc độ và phát hiện credential stuffing. Không vô hạn retry password sai từ client.
- Xử lý lỗi identity provider/database khác với sai password; không mặc định biến sự cố dịch vụ thành `401 BAD_CREDENTIALS`.
- Giữ HTTPS, mã hóa kết nối tới các backend quan trọng, audit ở mức không chứa secrets.

## 12. Lỗi thường gặp khi viết và dùng Authorization: Basic

| Triệu chứng | Nguyên nhân điển hình | Cách xử lý |
| --- | --- | --- |
| Gửi `Authorization: reader:reader123` nhưng 401 | Thiếu `Basic` và Base64 | Dùng `setBasicAuth`/`curl -u` |
| Dùng `Authorization: Bearer <base64>` | Nhầm scheme Bearer với Basic | Dùng `Basic <token>`; Bearer dành cho token |
| Header dùng Base64 của **mật khẩu** mà không có username | Sai cấu trúc user-pass | Mã hóa `username + ":" + password` |
| Username chứa dấu `:` gây login sai | RFC dùng dấu `:` đầu làm separator | Chọn user-id không chứa `:` |
| Password chứa `:` bị cắt phần sau | Decoder tự `split(":")` không đúng | Chỉ tách ở dấu `:` đầu tiên |
| UTF-8 credentials bị 401 | Encoding/normalization client-server không thống nhất | Kiểm tra challenge `charset="UTF-8"`, overload `setBasicAuth(..., UTF_8)` và test vector |
| `charset=UTF-8` được thêm sau Base64 của request | Nhầm challenge param với credentials | Chỉ đặt charset trong `WWW-Authenticate` theo RFC |
| Đọc được Base64 tưởng đã xác thực | Mới decode, chưa kiểm tra password | Dùng `ReactiveAuthenticationManager` và `PasswordEncoder` |
| Không gửi Basic mà 401 | Endpoint protected yêu cầu authentication | Kiểm tra `WWW-Authenticate`; cấp credentials hợp lệ |
| Password đúng vẫn 403 | Đăng nhập thành công nhưng thiếu role | Xem authorities và `hasRole`/`hasAuthority` |
| Cấu hình `SecurityFilterChain` không chạy trong WebFlux | Dùng API Servlet thay API reactive | Dùng `SecurityWebFilterChain` và `ServerHttpSecurity` |
| Endpoint public nhưng Basic sai trả 401 | Authentication filter xử lý credentials gửi lên trước khi controller | Test riêng trường hợp public+wrong credentials |
| `WWW-Authenticate` bị thiếu vì custom error handler | Handler tự tạo 401 mà không giữ challenge phù hợp | Khôi phục challenge đúng Basic và test header |
| API trên browser bị 403 khi POST | Có thể do CSRF, không phải role | Xác định nguồn 403; dùng chiến lược CSRF đúng |
| Test dùng `mockUser` luôn pass | Test không dùng Basic header thật | Thêm test `setBasicAuth`/header Base64 thật |
| Request có header đúng nhưng Basic không hoạt động | Security matcher/chain chọn khác hoặc Basic bị tắt | Kiểm tra `.httpBasic(...)`, `securityMatcher`, chain order |
| 401 xuất hiện khi gửi Basic đến HTTP | Có thể credential leak dù request bị từ chối | Chuyển sang HTTPS ngay; thay secret đã gửi qua HTTP nếu có nguy cơ lộ |
| Browser không “logout” Basic | Browser giữ credential cho realm/protection space | Thiết kế authentication/session khác nếu logout có ràng buộc mạnh |

## 13. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Header nào thuộc request, header nào thuộc response?

**Trả lời:** `Authorization: Basic ...` thuộc request do client gửi; `WWW-Authenticate: Basic realm="..."` thuộc response của server, thường đi với status 401.

**Câu 2.** `QWxhZGRpbjpvcGVuIHNlc2FtZQ==` có phải chuỗi bí mật được mã hóa an toàn không?

**Trả lời:** Không. Đó là Base64 của `Aladdin:open sesame`, có thể đảo ngược ngay. Basic cần TLS để bảo vệ đường truyền.

**Câu 3.** Với chuỗi `reader:pass:a:b`, username và password là gì?

**Trả lời:** Username là `reader`, password là `pass:a:b`. Chỉ dấu hai chấm đầu tiên là separator.

**Câu 4.** Có thể gửi user-id `team:reader` trong Basic mà giữ nguyên đúng username không?

**Trả lời:** Không. Username chứa dấu `:` không hợp lệ theo RFC 7617; server hiểu phần trước dấu đầu là user-id.

**Câu 5.** Header `Authorization: Basic <base64>` có chứa tham số `charset=UTF-8` không?

**Trả lời:** Không. Tham số charset được RFC 7617 định nghĩa cho challenge `WWW-Authenticate` của server. Client dùng charset đã thống nhất để tạo bytes trước Base64.

**Câu 6.** Vì sao `reader:reader123` có thể nhận 403 ở `/api/admin`?

**Trả lời:** Authentication bằng Basic có thể thành công, nhưng `reader` chỉ có `ROLE_READER`, không có `ROLE_ADMIN`; authorization từ chối.

**Câu 7.** Vì sao `mockUser("reader")` không đủ kiểm thử cơ chế HTTP Basic?

**Trả lời:** Vì mock user cung cấp principal đã xác thực, thường bỏ qua bước đọc header, Base64 decode và so khớp password. Cần test gửi credentials thật bằng `setBasicAuth` hoặc header.

**Câu 8.** Nếu API dùng HTTP Basic qua HTTPS, password có được băm tự động ở phía client trước khi gửi không?

**Trả lời:** Không theo đặc tả Basic. Client gửi Base64 của cặp username/password; HTTPS mã hóa đường truyền, còn server có trách nhiệm xác minh password với hash được lưu.

**Câu 9.** Vì sao request không có `Authorization` vẫn có thể trả 401, dù authentication filter không báo "password sai"?

**Trả lời:** Request không có credentials có thể được đưa qua bước authorization, bị từ chối vì thiếu danh tính hợp lệ; entry point của Spring Security tạo 401/challenge. Không có authentication attempt sai từ Basic converter.

**Câu 10.** Có thể tin rằng dùng Basic thì browser-based POST sẽ miễn nhiễm CSRF không?

**Trả lời:** Không. Browser có thể tái gửi credentials, và CSRF phải được đánh giá theo hành vi browser/client cùng cơ chế xác thực thực tế; không tắt CSRF theo mặc định chỉ vì Basic.

### Bài tập ngắn

1. Thay tài khoản `reader` trong `SecurityConfig` bằng một username khác (không chứa `:`) và dùng test `setBasicAuth` để xác minh.
2. Thay password của user `colon` bằng `a:b:c`; kiểm tra endpoint vẫn trả 200 với `setBasicAuth("colon", "a:b:c")`.
3. Gọi endpoint `/api/admin` với hai user `reader` và `admin`; giải thích vì sao status khác nhau dù cả hai đã xác thực thành công.
4. Bổ sung một test kiểm tra `WWW-Authenticate` trong phản hồi 401 khi không credentials; không so sánh exact realm nếu cấu hình có thể thay đổi.
5. Thử lệnh `curl -i` trên localhost chỉ với tài khoản demo. Với môi trường bên ngoài, chuyển sang HTTPS và tránh hiển thị credentials trong lịch sử lệnh.

## 14. Checklist trước khi sử dụng Basic trong dự án thật

- [ ] Có yêu cầu business rõ ràng cho việc dùng Basic thay vì bearer token, OIDC hoặc session.
- [ ] **HTTPS/TLS bắt buộc**; không bỏ qua certificate verification.
- [ ] `Authorization` được redact ở application logs, reverse proxy, tracing và error reporting.
- [ ] Có chính sách password, password hashing, credential rotation và rate limiting.
- [ ] Username không chứa dấu `:`; quy tắc Unicode/charset giữa các client và server được kiểm thử.
- [ ] API định nghĩa rõ 401/`WWW-Authenticate` và 403 theo các trường hợp.
- [ ] WebFlux dùng `SecurityWebFilterChain`, không trộn các lớp Servlet.
- [ ] Có integration tests gửi **Basic header thật**, test cả credentials sai và đúng role/thiếu role.
- [ ] Đã cân nhắc Browser Basic cache, CSRF, CORS và logout kỳ vọng.
- [ ] Không lưu password, raw Base64 hoặc raw token vào test artifacts/logs của production.
- [ ] Không dựa vào Base64 như lớp bảo mật; chính sách authorization được kiểm tra độc lập với authentication.

## 15. Tóm tắt và tài liệu chính thức

**Tóm tắt một câu:** HTTP Basic chuyển `username:password` thành bytes rồi Base64, gửi bằng **`Authorization: Basic <token68>`** trong HTTP request; server phải dùng HTTPS, xác thực password và áp dụng phân quyền, còn **`WWW-Authenticate: Basic realm="..."`** là lời challenge từ server khi cần authentication.

| Đặc tính cần nhớ | Quy tắc |
| --- | --- |
| Scheme | `Basic` |
| Chuỗi trước Base64 | `user-id:password` |
| Dấu `:` | Dấu đầu là separator; password có thể chứa `:`, username thì không |
| Base64 | Encoding, **không phải encryption** |
| Header request | `Authorization: Basic <encoded>` |
| Challenge response | `401` + `WWW-Authenticate: Basic realm="..."` |
| Sai credentials | Thường 401 |
| Đã xác thực nhưng thiếu role | Thường 403 |
| Charset Unicode | Thỏa thuận rõ; server có thể challenge `charset="UTF-8"` |
| Spring Security reactive | `AuthenticationWebFilter`, `ReactiveAuthenticationManager`, `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Bảo vệ thực tế | TLS + password hashing + logging hygiene + authorization + rate limit |

**Tài liệu tham khảo chuẩn và chính thức:**

- RFC 7617 – The “Basic” HTTP Authentication Scheme (cú pháp, charset, realm, Base64): https://www.rfc-editor.org/rfc/rfc7617.html
- RFC 9110 – HTTP Semantics (authentication framework, Authorization, 401/403): https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 4648 – The Base16, Base32, and Base64 Data Encodings: https://www.rfc-editor.org/rfc/rfc4648.html
- Spring Security 6.5 – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – `ServerHttpSecurity` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 – `ServerHttpBasicAuthenticationConverter` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerHttpBasicAuthenticationConverter.html
- Spring Security – Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security 6.5 – Reactive Security Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
- Spring Boot 3.5.16 release notice (version baseline; nhánh 3.5 đã hết OSS support): https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
