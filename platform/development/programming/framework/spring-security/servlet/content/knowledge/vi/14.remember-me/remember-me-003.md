# TokenBasedRememberMeServices và nội dung cookie được ký trong Spring Security Servlet

> **Phạm vi:** Spring Security 6 trên Servlet stack, Java 17+, luồng **Remember Me** khi ứng dụng dùng form login. Trọng tâm là `TokenBasedRememberMeServices`, cookie remember-me **được ký nhưng không mã hóa**, các bước tạo/kiểm tra/khôi phục `Authentication`, hạn sử dụng và giới hạn thu hồi. Ví dụ ứng dụng Spring Boot 3.3.5 có thể chạy để quan sát cookie và quyền `authenticated()` so với `fullyAuthenticated()`.

## 1. Remember Me giải quyết việc gì?

Trong ứng dụng web, **HTTP session** thường giữ trạng thái người dùng vừa đăng nhập. Khi session hết hạn hoặc browser không còn cookie phiên, người dùng thông thường phải điền lại username và mật khẩu. Tính năng **Remember Me** cho phép browser gửi một cookie tồn tại lâu hơn session để ứng dụng nhận diện lại tài khoản mà không yêu cầu đăng nhập tương tác ở mỗi lần truy cập.

Một trải nghiệm thông thường:

1. Người dùng mở trang login và nhập username/password.
2. Người dùng **chủ động chọn** ô “Remember me” trên form.
3. Spring Security xác thực tài khoản thành công và gửi thêm cookie `remember-me` đã được ký.
4. Lúc session đăng nhập mất hoặc hết hạn, browser vẫn giữ và gửi cookie remember-me tới website.
5. Security filter kiểm tra cookie bằng một khóa bí mật trên server và dữ liệu tài khoản hiện tại.
6. Nếu cookie hợp lệ, hệ thống thiết lập một **remember-me authentication** trong `SecurityContext` cho request. Người dùng có thể vào các endpoint yêu cầu `authenticated()`, nhưng những hành động nhạy cảm có thể yêu cầu đăng nhập tương tác lại qua `fullyAuthenticated()`.

**Remember Me khác session:** một `JSESSIONID` thường tham chiếu tới state phiên ở server; remember-me cookie trong cơ chế token-based mang dữ liệu mà server có thể **tự kiểm chứng chữ ký**. Cookie đó không phải HTTP session ID, không phải CSRF token, cũng không phải JWT/OAuth2 access token.

**Remember Me không thay thế xác thực ban đầu:** cookie thường chỉ được phát hành sau khi người dùng đã đăng nhập thành công bằng cơ chế bình thường và chọn ghi nhớ (trừ khi cấu hình `alwaysRemember`). Nếu người dùng chưa từng đăng nhập, một username tự gửi lên không đủ để tạo remember-me authentication đáng tin.

## 2. Đặt TokenBasedRememberMeServices vào Servlet filter chain

Trong Spring Security Servlet, các thành phần liên quan có vai trò khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `UsernamePasswordAuthenticationFilter` | Đọc `POST /login`, tạo yêu cầu username/password và xác thực thông qua `AuthenticationManager` |
| `RememberMeServices` | Interface cho `loginSuccess`, `loginFail`, `autoLogin` và việc xử lý remember-me |
| **`TokenBasedRememberMeServices`** | Tạo cookie có thời gian hết hạn và chữ ký; đọc cookie, xác minh thời hạn/chữ ký với dữ liệu user và secret key |
| `RememberMeAuthenticationFilter` | Khi chưa có authentication phù hợp trong context, thử `RememberMeServices.autoLogin(...)` để khôi phục danh tính từ cookie |
| `RememberMeAuthenticationToken` | Đối tượng `Authentication` biểu diễn đăng nhập qua remember-me |
| `RememberMeAuthenticationProvider` | Kiểm tra token remember-me được tạo theo khóa mà provider tin cậy |
| `UserDetailsService` | Tải tài khoản, encoded password, roles và trạng thái hiện tại; phục vụ kiểm tra cookie |
| `SecurityContextRepository` | Hỗ trợ lưu/tải context theo chính sách ứng dụng; tách biệt với tính hợp lệ của cookie |
| `AuthorizationFilter` | Áp dụng các rule `authenticated()`, `fullyAuthenticated()`, `hasRole(...)` sau khi danh tính được thiết lập |

Sơ đồ khái niệm:

```text
Lần đăng nhập tương tác
  Browser POST /login + username/password + _csrf + remember-me=true
       |
       v
UsernamePasswordAuthenticationFilter
       |
       v
AuthenticationManager / DaoAuthenticationProvider
       |
       +-- Thất bại -> failure handler, không tạo remember-me hợp lệ
       |
       +-- Thành công
              |
              v
      RememberMeServices.loginSuccess(...)
              |
              v
      TokenBasedRememberMeServices tạo signed cookie
              |
              v
      Set-Cookie: remember-me=...; Max-Age=...
              |
              v
      Browser giữ cookie theo thuộc tính trình duyệt

Lần truy cập sau, khi không còn authentication từ session
  GET /account + Cookie: remember-me=...
       |
       v
RememberMeAuthenticationFilter
       |
       v
TokenBasedRememberMeServices.autoLogin(...)
       |  tách các field, kiểm tra thời hạn, user và chữ ký
       |
       +-- Không hợp lệ -> xóa/không chấp nhận cookie, tiếp tục anonymous
       |
       +-- Hợp lệ -> RememberMeAuthenticationToken
                              |
                              v
                  RememberMeAuthenticationProvider
                              |
                              v
                  SecurityContext của request
                              |
                              v
                  AuthorizationFilter kiểm tra quyền
```

Đường đi cụ thể có thể thay đổi theo phiên bản, request matcher, cấu hình filter và `SecurityContextRepository`. Nhưng điểm cốt lõi không đổi: **remember-me authentication phải được kiểm chứng ở server**, không tin một cookie chỉ vì nó có username hoặc mang một Base64 đọc được.

## 3. Vì sao gọi là cookie “được ký”?

`TokenBasedRememberMeServices` thường dùng **chữ ký dựa trên digest có khóa bí mật** để phát hiện dữ liệu cookie bị sửa. Phần cookie được mã hóa Base64 để đưa vào một HTTP cookie, nhưng Base64 không giấu nội dung.

Ở định dạng token-based hiện đại, nội dung trước khi mã hóa Base64 thường có cấu trúc khái quát:

```text
username : expirationTime : algorithmName : signatureHex
```

Trong đó:

- **`username`**: tên người dùng được ghi nhớ. Người có cookie có thể xem được sau khi giải Base64.
- **`expirationTime`**: mốc hết hạn do server xác lập, thường biểu diễn bằng **Unix epoch milliseconds** trong token. Nó quyết định hạn kiểm tra server-side, không đơn giản chỉ là thuộc tính `Max-Age` của browser.
- **`algorithmName`**: tên thuật toán digest dùng tính chữ ký, ví dụ SHA-256 trong cấu hình hiện đại.
- **`signatureHex`**: chuỗi digest được tạo từ dữ liệu username, expiration, **mật khẩu đã lưu của tài khoản** và **khóa bí mật** của ứng dụng.

Một công thức minh họa theo mô hình của `TokenBasedRememberMeServices`:

```text
signatureHex =
    HEX( DIGEST_algorithm(
        username + ":" +
        expirationTime + ":" +
        userDetails.getPassword() + ":" +
        serverSecretKey
    ))

cookieValue =
    Base64(username + ":" +
           expirationTime + ":" +
           algorithmName + ":" +
           signatureHex)
```

Đây là **công thức giảng giải ý tưởng**, không phải mã thay thế cho Spring Security. Một số thế hệ cookie/token cũ có khác biệt về số field hoặc cách chọn thuật toán; khi đọc code hoặc vận hành ứng dụng, xác định phiên bản Spring Security và lớp đang phát hành cookie. Không tự parse hard-code bốn field ở controller để “xác thực nhanh”.

**Quan trọng:** `userDetails.getPassword()` thông thường trả **encoded password hash** trong database, không phải mật khẩu plaintext của người dùng. Giá trị hash tham gia tính chữ ký ở phía server nhưng **không xuất hiện trực tiếp như một field của cookie**. Cookie cũng **không cần** chứa secret key.

### Ký không có nghĩa mã hóa

| Thuộc tính | Cookie token-based được ký |
| --- | --- |
| Có thể giải mã Base64 để thấy username/expiration? | **Có** |
| Có được bảo vệ khỏi việc sửa `expirationTime` hoặc username tùy ý? | **Có**, nếu chữ ký/secret được bảo vệ và thuật toán phù hợp |
| Cookie có che giấu username khỏi người có cookie? | **Không** |
| Cookie có phải JWT? | **Không**; định dạng và bộ kiểm tra riêng |
| Cookie có dùng một lần? | **Không**; có thể được gửi lặp lại trong thời gian còn hợp lệ |
| Cookie bị đánh cắp có thể bị phát lại? | **Có**; chữ ký không chống được replay với bản cookie nguyên vẹn |
| Có thể thu hồi một cookie riêng biệt chỉ bằng logout? | Không đáng tin nếu bản sao cookie đã bị đánh cắp và còn hạn |

Một chi tiết bảo mật: đây là **digest có khóa theo cơ chế của Spring Security**, không nên tự gọi một cách mặc định là “JWT signature” hay “HMAC chuẩn” nếu không kiểm tra implementation cụ thể. Ứng dụng nên **dùng lớp framework** thay vì tự viết thuật toán, đặc biệt không dùng MD5 cho token mới.

## 4. Cách cookie được tạo lúc login thành công

Với form login và remember-me được bật, luồng thường gồm:

1. Browser hiển thị form có trường `username`, `password` và checkbox `remember-me`. Form POST còn phải gửi CSRF token hợp lệ.
2. `UsernamePasswordAuthenticationFilter` gọi `AuthenticationManager.authenticate(...)`. Provider xác minh password hash, account flags và authorities.
3. Nếu xác thực thành công, `RememberMeServices.loginSuccess(request, response, successfulAuthentication)` được gọi theo chuỗi xử lý thành công.
4. Dịch vụ nhớ đăng nhập kiểm tra user có yêu cầu remember-me không. Mặc định việc chọn remember-me thường do parameter `remember-me` quyết định, trừ khi cấu hình nhớ luôn.
5. `TokenBasedRememberMeServices` tính `expirationTime`, chọn thuật toán ký theo cấu hình, lấy password hash từ `UserDetailsService`, tính signature và đưa chuỗi token vào cookie.
6. Response phát `Set-Cookie` với tên và thuộc tính theo cấu hình. Browser giữ cookie cho các request tới domain/path tương ứng.
7. Các request trong session hiện tại có thể vẫn dùng `UsernamePasswordAuthenticationToken` do form login; remember-me **không bắt buộc được dùng ngay lập tức** khi session vẫn còn authentication.

Ví dụ minh họa response (ẩn giá trị bí mật):

```http
HTTP/1.1 302 Found
Set-Cookie: remember-me=<base64-token>; Max-Age=86400; Path=/; HttpOnly
Location: /
```

Đây **không phải transcript cố định**: có thể có `JSESSIONID`, header `Location` khác vì saved request hoặc success handler, và thuộc tính `Secure`/`SameSite` phụ thuộc request HTTPS, reverse proxy, server và cách bạn cấu hình cookie. Tuyệt đối không copy giá trị remember-me thực tế từ production vào tài liệu, log hoặc ticket.

### Phân biệt checkbox và alwaysRemember

Thông thường người dùng phải **tích chọn** remember-me. Nếu bỏ tích thì vẫn có thể login/session bình thường nhưng **không được phát cookie remember-me mới**.

Một số ứng dụng có thể đặt `alwaysRemember(true)`: khi ấy remember-me được phát hành cho mỗi lần login thành công mà không phụ thuộc checkbox. Đây là quyết định ảnh hưởng riêng tư trên thiết bị dùng chung; **không nên bật mà thiếu yêu cầu sản phẩm, chính sách người dùng và đánh giá bảo mật**.

## 5. Cách RememberMeAuthenticationFilter kiểm tra cookie

Khi security context của request chưa có danh tính phù hợp, `RememberMeAuthenticationFilter` thử gọi `rememberMeServices.autoLogin(request, response)`. Với `TokenBasedRememberMeServices`, các bước logic chính là:

1. Đọc cookie có tên đã cấu hình, thường là `remember-me`.
2. Giải Base64 và đọc các field theo format được lớp hỗ trợ.
3. Kiểm tra `expirationTime` đã quá hạn chưa; cookie hết hạn phải bị từ chối dù browser vẫn gửi.
4. Tải `UserDetails` theo username bằng `UserDetailsService`. Tài khoản không tồn tại, disabled, locked hoặc có trạng thái không được phép đăng nhập sẽ không được chấp nhận theo cơ chế kiểm tra phù hợp.
5. Tính lại signature dựa trên dữ liệu cookie, **password hash hiện tại** trong `UserDetails` và **secret key hiện tại**.
6. So sánh với signature trong cookie; nếu dữ liệu bị sửa, secret key khác hoặc password hash thay đổi làm chữ ký không khớp, cookie bị từ chối.
7. Tạo `RememberMeAuthenticationToken`, được `RememberMeAuthenticationProvider` và authentication flow tin cậy xác minh theo key tương ứng.
8. Đặt kết quả vào `SecurityContext` cho request rồi tiếp tục authorization.

Nếu cookie không hợp lệ, Spring Security thường hủy cookie trên response khi có thể và request tiếp tục như chưa xác thực. Một endpoint cần `authenticated()` có thể khởi động form login lại; một endpoint `permitAll()` vẫn có thể truy cập ở trạng thái anonymous.

### Tại sao phải tải UserDetails lại?

Cookie ký **không nên giữ một snapshot quyền vĩnh viễn**. Sau khi cookie được phát hành, tài khoản có thể bị khóa, bị xóa, đổi mật khẩu hoặc thay quyền. Việc lấy `UserDetails` hiện tại giúp ứng dụng áp dụng trạng thái và authorities đáng tin cậy tại thời điểm khôi phục.

Điều này có hai hệ quả:

- **Password hash đổi** thường làm cookie cũ hết hợp lệ, ngay cả khi thời gian hết hạn trên cookie vẫn còn.
- **Quyền đổi** có thể ảnh hưởng quyền của remember-me authentication mới vì hệ thống lấy authorities hiện tại. Với hệ thống cache user, phải hiểu cache invalidation để tránh dùng thông tin cũ.

**Không dựa vào việc sửa role trong cookie** để cấp quyền — token-based cookie không phải nơi client được định nghĩa authorities.

## 6. Authenticated và Fully Authenticated không giống nhau

Remember-me authentication thường mang trạng thái `isAuthenticated()==true`, nhưng Spring Security phân biệt **đăng nhập tương tác đầy đủ** và **được khôi phục từ remember-me** thông qua trust resolver.

Quy tắc authorization:

| Rule | Username/password vừa login thành công | Được khôi phục qua remember-me |
| --- | --- | --- |
| `permitAll()` | Được | Được |
| `authenticated()` | Được | **Thường được** nếu cookie hợp lệ |
| `fullyAuthenticated()` | Được | **Không**; yêu cầu đăng nhập tương tác lại |
| `hasRole("USER")` | Nếu có role USER | Nếu có role USER, tùy rule cụ thể vẫn có thể được |
| `denyAll()` | Không | Không |

Vì sao cần `fullyAuthenticated()`? Remember-me cookie là **bằng chứng tồn tại lâu hơn**, dễ bị đánh cắp trên thiết bị dùng chung. Với tác vụ như đổi mật khẩu, thêm phương thức thanh toán hoặc quản trị nhạy cảm, ứng dụng thường yêu cầu người dùng cung cấp xác thực đầy đủ lại.

Minh họa:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/account/sensitive").fullyAuthenticated()
        .requestMatchers("/account").authenticated()
        .anyRequest().permitAll());
```

Đây là fragment Java trong `SecurityFilterChain`, không phải class chạy độc lập. Với form login, khi user chỉ có remember-me authentication truy cập `/account/sensitive`, `ExceptionTranslationFilter` thường yêu cầu tương tác đăng nhập lại; không nên giả định luôn trả 403 thay vì redirect, vì entry point và security config quyết định HTTP response.

Một lưu ý quan trọng: `fullyAuthenticated()` là sự phân biệt trong cơ chế authentication của Spring Security, **không tự thay thế MFA, reauthentication timeout hoặc xác minh giao dịch rủi ro cao**. Với thao tác nhạy cảm, yêu cầu bảo mật cụ thể có thể nghiêm ngặt hơn.

## 7. Token-based remember-me khác Persistent Token Repository

Spring Security có hai kiểu remember-me thường gặp:

| Khía cạnh | `TokenBasedRememberMeServices` | `PersistentTokenBasedRememberMeServices` |
| --- | --- | --- |
| Cơ sở | Cookie có dữ liệu và chữ ký phụ thuộc server key/password hash | Cookie tham chiếu series/token trong server-side persistent store |
| Có cần database token riêng để kiểm tra? | **Không bắt buộc**, cần `UserDetailsService` | **Có**, cần `PersistentTokenRepository` |
| Kiểm tra cookie | Expiry + signature + user hiện tại | Đối chiếu token/series với kho dữ liệu |
| Thu hồi **một thiết bị** | Khó; không có token record độc lập cho từng thiết bị | Có thể xóa token/series tương ứng |
| Phát hiện token bị dùng trái phép | Giới hạn do cookie có thể replay | Có cơ chế token rotation và phát hiện mismatch tùy implementation |
| Phù hợp | Hệ thống đơn giản, yêu cầu revoke từng thiết bị thấp | Hệ thống cần quản lý phiên ghi nhớ/thiết bị chặt chẽ hơn |

`TokenBasedRememberMeServices` **không phải OAuth2 access token** và `PersistentTokenBasedRememberMeServices` **không phải một JWT service**. Hai cơ chế là remember-me của Spring Security Servlet, dùng cho trường hợp và threat model cụ thể.

**Quyết định thiết kế:** nếu cần “đăng xuất khỏi tất cả thiết bị”, “thu hồi riêng thiết bị bị mất” hoặc kiểm soát token reuse, persistent-token repository và cơ chế quản lý thiết bị có thể phù hợp hơn. Với signed token-based cookie, không có một hàng database mặc định cho mỗi cookie để xóa riêng lẻ.

## 8. Thời hạn, chữ ký, key rotation và logout

### 8.1. Hai loại thời hạn cần phân biệt

Một remember-me cookie có:

- **Thời hạn server-side trong dữ liệu đã ký** (`expirationTime`). Khi hết hạn, server từ chối; sửa timestamp để gia hạn sẽ làm chữ ký không còn hợp lệ.
- **Thời hạn browser cookie** (`Max-Age` hoặc `Expires`). Trình duyệt quyết định còn gửi cookie hay không.

Không chỉ nhìn `Max-Age` để kết luận server chắc chắn chấp nhận cookie. Server vẫn cần kiểm tra signed expiration, username và signature.

Trong ví dụ thực hành, ta đặt `tokenValiditySeconds(86400)`, tương đương **24 giờ**. Đây là giá trị demo; production phải chọn TTL theo rủi ro, độ nhạy cảm tài khoản, khả năng thu hồi và thiết bị dùng chung. Đừng để thời gian quá dài chỉ vì muốn người dùng ít đăng nhập.

### 8.2. Thay đổi password hash

Vì signature phụ thuộc `UserDetails.getPassword()`, đổi mật khẩu hoặc thay đổi hash có thể khiến cookie đã phát trước đó không vượt qua kiểm tra chữ ký.

Có một chi tiết dễ bất ngờ: BCrypt dùng salt. Nếu ứng dụng demo **tạo lại hash từ cùng plaintext mỗi lần khởi động**, hash thường sẽ khác sau restart, khiến cookie nhớ đăng nhập cũ **không còn hợp lệ dù password demo không đổi**. Trong sản phẩm thật, password hash cần được lưu bền vững trong database, không tạo lại ở mỗi startup.

### 8.3. Thay đổi secret key

`TokenBasedRememberMeServices` cần **server secret key ổn định và đủ bí mật**. Nếu app có nhiều instance, các instance phải có **cùng key** (hoặc một chiến lược phiên bản/rotation có chủ đích). Nếu mỗi node dùng một key khác, người dùng có thể bị remember-me thất bại khi request chuyển node.

- Lộ key khiến kẻ tấn công có thể giả mạo cookie trong các điều kiện nhất định; cần xem đây là secret quan trọng.
- Rotate key có thể **vô hiệu hóa toàn bộ cookie ký bằng key cũ**. Đó là hành vi có thể mong muốn khi phát hiện rò rỉ nhưng ảnh hưởng UX của tất cả người dùng.
- Không commit secret vào source, không ghi ra logs, không truyền nó như một browser query parameter.
- Đặt key bằng secrets manager hoặc môi trường triển khai và có quy trình rotation/restart rõ ràng.

### 8.4. Logout có thu hồi cookie không?

Trong logout flow thông thường, Spring Security gọi các logout handlers (bao gồm phần remember-me nếu cấu hình), xóa cookie ở browser qua response phù hợp.

Nhưng **xóa cookie trên browser hiện tại không thể thu hồi bản sao đã bị đánh cắp ở nơi khác** nếu cookie token-based đó vẫn chưa hết hạn và user/key vẫn chưa thay đổi. Đây là rủi ro **replay** của bearer-style remember-me cookie. Muốn thu hồi ngay một cookie cụ thể, cân nhắc persistent token store hoặc một thiết kế có revocation record.

## 9. Ví dụ ứng dụng chạy được: Java 17 + Spring Security 6

Dự án Spring Boot 3.3.5 dưới đây dùng một `UserDetailsService` in-memory và form login mặc định. Khi chọn checkbox **Remember me**, cấu hình `rememberMe(...)` tạo **`TokenBasedRememberMeServices` theo mặc định** cho username/password. Cấu hình chia sẻ key với `RememberMeAuthenticationProvider` do RememberMeConfigurer tạo, tránh tự gắn một provider không tương thích.

Các endpoints:

- `GET /`: public, trả văn bản hướng dẫn.
- `GET /account`: chỉ cần `authenticated()`.
- `GET /account/sensitive`: cần `fullyAuthenticated()`, từ chối/trình ra login lại nếu chỉ có remember-me authentication.
- `GET /logout`: không chủ đích dùng làm logout qua GET; **logout mặc định Spring Security được bảo vệ bởi CSRF và sử dụng thao tác phù hợp**.

Tài khoản demo: `lan` / `demo123`, role `USER`. Không dùng tài khoản này trong production.

### 9.1. Cấu trúc thư mục

```text
remember-me-demo/
├── pom.xml
└── src/main/java/example/remember/
    ├── RememberMeApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>remember-me-demo</artifactId>
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

### 9.3. RememberMeApplication.java

```java
package example.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
```

### 9.4. SecurityConfig.java

```java
package example.remember;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails lan = User.withUsername("lan")
                .password(encoder.encode("demo123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(lan);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService users) throws Exception {

        String key = System.getenv("REMEMBER_ME_KEY");
        if (key == null || key.length() < 32) {
            throw new IllegalStateException(
                    "REMEMBER_ME_KEY must be a stable secret of at least 32 characters");
        }

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/account/sensitive").fullyAuthenticated()
                .requestMatchers("/account").authenticated()
                .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());

        // Khi có UserDetailsService, cấu hình này dùng
        // TokenBasedRememberMeServices theo cơ chế remember-me mặc định.
        // Key cũng được dùng để đăng ký provider kiểm tra remember-me token.
        http.rememberMe(remember -> remember
                .key(key)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(24 * 60 * 60)
        );

        // CSRF giữ mặc định. POST /login và logout theo form cần token.
        return http.build();
    }
}
```

**Giải thích các lựa chọn quan trọng:**

1. `REMEMBER_ME_KEY` được lấy từ **biến môi trường**, không hard-code. Giá trị cần ổn định qua restart và giống nhau giữa các instance. Ràng buộc “ít nhất 32 ký tự” ở ví dụ là một quy tắc demo nhằm tránh secret rất ngắn; production cần key được tạo ngẫu nhiên đủ entropy, không chỉ một chuỗi dễ đoán dài 32 ký tự.
2. `rememberMe(...)` có `userDetailsService(users)` và `key(key)`: Spring Security có thể cấu hình `TokenBasedRememberMeServices` và `RememberMeAuthenticationProvider` tương thích. Không thêm một `new TokenBasedRememberMeServices` thứ hai dùng key khác.
3. `rememberMeParameter("remember-me")` là tên checkbox/field trên form, khác `rememberMeCookieName("remember-me")` là tên cookie gửi về browser. Hai tên bằng nhau ở demo nhưng thuộc hai kênh dữ liệu khác nhau.
4. `tokenValiditySeconds(24 * 60 * 60)` đặt thời hạn của remember-me token ở đây là **24 giờ**.
5. `authenticated()` ở `/account` chấp nhận remember-me authentication hợp lệ, trong khi `fullyAuthenticated()` ở `/account/sensitive` buộc người dùng xác thực lại theo chính sách.
6. `formLogin(Customizer.withDefaults())` cung cấp trang login mặc định và xử lý form POST. Chúng ta không tự xây controller POST chứa password. Không vô hiệu hóa CSRF.
7. Hash BCrypt của user demo **được tạo lại khi restart**; vì chữ ký dựa trên hash, cookie từ lượt chạy trước thường hết hiệu lực. Dữ liệu account thực phải dùng password hash lưu bền vững.

### 9.5. DemoController.java

```java
package example.remember;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home:open /account, then sign in with remember-me";
    }

    @GetMapping("/account")
    public String account(Authentication auth) {
        return "user=" + auth.getName()
                + ";authenticationType=" + auth.getClass().getSimpleName();
    }

    @GetMapping("/account/sensitive")
    public String sensitive(Authentication auth) {
        return "sensitive:" + auth.getName();
    }
}
```

Response body cố ý cho thấy **class của Authentication** để quan sát khác biệt trong lab. Không nên xuất tùy tiện object Authentication đầy đủ, credentials, claims hoặc các thông tin nhạy cảm vào response production.

### 9.6. Chạy ứng dụng

Trong shell POSIX/macOS/Linux, đặt một secret demo riêng, sau đó khởi động:

```bash
export REMEMBER_ME_KEY="demo-change-this-to-a-long-random-secret-2026"
mvn spring-boot:run
```

Giá trị trên **chỉ dành cho localhost**, không dùng làm key của hệ thống thật. Trên PowerShell, biến môi trường cần được thiết lập theo cú pháp PowerShell trước khi chạy Maven.

Lúc khởi động thành công, Tomcat mặc định phục vụ tại `http://localhost:8080`. Ở production phải dùng **HTTPS** để bảo vệ password, session cookie và remember-me cookie khỏi bị đọc trên đường truyền.

### 9.7. Thử Remember Me trong browser

1. Mở cửa sổ browser riêng tư mới để không có session/cookie cũ.
2. Truy cập `http://localhost:8080/account`. Vì chưa đăng nhập, browser thường được chuyển đến `/login`.
3. Trong trang login mặc định có remember-me được bật, chọn checkbox **Remember me**, nhập `lan` / `demo123` và gửi form. Spring Security sẽ xử lý CSRF token của generated form.
4. Khi đăng nhập thành công, vào `/account`. Kết quả điển hình:

```text
user=lan;authenticationType=UsernamePasswordAuthenticationToken
```

5. Mở Developer Tools → Storage/Cookies. Bạn có thể thấy cả cookie session (như `JSESSIONID`) và `remember-me`; đừng sao chép/chia sẻ giá trị đầy đủ của cookie.
6. **Chỉ xóa cookie `JSESSIONID`**, giữ cookie `remember-me`, không bấm Logout. Refresh `/account`.
7. Nếu cookie hợp lệ và các thành phần remember-me hoạt động, kết quả điển hình chuyển thành:

```text
user=lan;authenticationType=RememberMeAuthenticationToken
```

8. Truy cập `/account/sensitive` trong trạng thái chỉ được khôi phục bằng remember-me. Rule `fullyAuthenticated()` yêu cầu đăng nhập tương tác lại; với form login, bạn thường thấy redirect đến login thay vì nội dung `sensitive:lan`.
9. Sau khi đăng nhập tương tác lại, truy cập `/account/sensitive` sẽ trả:

```text
sensitive:lan
```

**Cần phân biệt:** browser vẫn có remember-me cookie nhưng `JSESSIONID` bị xóa không đồng nghĩa browser “logout”. Cơ chế remember-me được thiết kế để nhận diện lại user. Nếu muốn kiểm tra thất bại do cookie hết hạn hoặc bị sửa, dùng một môi trường test riêng và tránh sửa cookie production.

### 9.8. Vì sao không dùng curl POST /login chỉ với username/password?

Spring Security Servlet thường bật CSRF cho form login. Request `POST /login` cần **CSRF token đúng và cookie phiên liên quan**. Một lệnh như:

```bash
# Thiếu CSRF token; thường bị từ chối trước khi login:
curl -i -d 'username=lan&password=demo123&remember-me=on' \
  http://localhost:8080/login
```

thường **không** thành công khi CSRF đang bật. Không tắt CSRF cho cả website chỉ để thực hiện demo. Browser generated form cho phép thử đúng flow và dễ quan sát cookie nhất.

Một cách test tự động đầy đủ là dùng `spring-security-test` + `MockMvc` với CSRF hỗ trợ, sau đó kiểm tra header `Set-Cookie`, authentication token class và rule `fullyAuthenticated()`; đừng giả định `@WithMockUser` tự tạo remember-me cookie thực.

## 10. Đọc và kiểm tra cookie: nên và không nên làm gì?

Trong môi trường local, bạn có thể xem **tên cookie**, `Max-Age`, `Path`, `Secure`, `HttpOnly` trong Developer Tools. Để hiểu định dạng, có thể giải Base64 của **cookie do chính demo tạo**; tuy nhiên giải Base64 **không kiểm tra chữ ký**.

Không dùng JavaScript trong browser đọc cookie bằng `document.cookie` như một test bảo mật bắt buộc. Cookie remember-me thường được bảo vệ bằng thuộc tính `HttpOnly`, nên JavaScript phía trang không nên có quyền đọc giá trị. Developer Tools vẫn có thể hiển thị cho người vận hành trên máy test.

Khi debug cookie:

| Biểu hiện | Cần kiểm tra |
| --- | --- |
| Không thấy cookie `remember-me` sau login | Checkbox `remember-me` đã chọn chưa, login có thực sự thành công, nhớ đăng nhập đã bật chưa? |
| Cookie xuất hiện nhưng biến mất sau logout | Remember-me logout handler đã clear cookie theo policy; đây là behavior mong đợi |
| Cookie tồn tại nhưng refresh vẫn anonymous | Hết hạn, key không khớp, password hash đổi, tài khoản disabled, user service lỗi, domain/path hoặc browser không gửi cookie |
| Một node nhận, node khác từ chối | Các node có thể dùng khác secret key hoặc khác user/password data |
| Refresh qua HTTPS không gửi cookie | Kiểm tra `Secure`, domain/path, SameSite, reverse proxy và browser policy |
| Cookie từng hợp lệ nhưng sau restart hết hiệu lực | Key random lại, hoặc password hash in-memory BCrypt bị tạo lại |
| Cookie bị sửa username/expiration nhưng không được nhận | Signature check đã phát hiện chỉnh sửa; đúng behavior |
| Cookie vẫn hoạt động sau khi user bấm logout ở một máy khác | Signed token không có per-device revocation record mặc định; đánh giá threat model |
| Vào được `/account` nhưng không vào được `/account/sensitive` | `authenticated()` chấp nhận remember-me, `fullyAuthenticated()` thì không |

Không log hay gửi kèm **toàn bộ cookie signed** vào support ticket: ai có bản cookie hợp lệ có thể phát lại nó trong thời gian sống nếu hệ thống thiếu biện pháp ràng buộc khác.

## 11. Những hiểu lầm bảo mật phổ biến

### “Cookie có signature thì người đánh cắp cũng không dùng được”

**Sai.** Chữ ký ngăn sửa nội dung mà không biết secret, nhưng **không ngăn gửi lại nguyên một cookie hợp lệ**. Đây là lý do HTTPS, HttpOnly, Secure, giới hạn TTL, chống XSS, CSRF và kiểm soát hành động nhạy cảm rất quan trọng.

### “Base64 mã hóa thông tin người dùng”

**Sai.** Base64 có thể decode ngược được. Username, expirationTime và algorithmName không phải bí mật được bảo vệ bằng mã hóa; signature chỉ giúp phát hiện sửa đổi.

### “Remember-me cookie giống session ID”

**Sai.** Session ID tham chiếu tới state server-side; token-based remember-me cookie được kiểm chứng bằng chữ ký và dữ liệu user. Cookie remember-me có thể được chấp nhận ngay cả khi không còn `JSESSIONID` đang hoạt động.

### “Đổi password luôn giữ cookie cũ”

**Không đúng với token-based remember-me bình thường.** Chữ ký phụ thuộc password hash hiện tại; thay đổi hash thường làm cookie cũ hết hợp lệ. Đây là một ưu điểm về thu hồi hàng loạt, nhưng cũng là lý do phải lưu password hash ổn định chứ không tạo mới mỗi lần khởi động.

### “Logout xóa cookie nghĩa là đã thu hồi mọi bản sao”

**Không được bảo đảm.** Logout thường xóa cookie ở browser hiện tại, còn bản cookie bị đánh cắp có thể vẫn ký hợp lệ cho tới khi hết hạn/đổi password/key. Nếu ứng dụng đòi revoke riêng thiết bị, cần cơ chế lưu và quản lý token server-side phù hợp.

### “Remember Me đủ để cho phép đổi password”

**Không nhất thiết.** Bảo vệ route nhạy cảm bằng `fullyAuthenticated()` hoặc cơ chế reauthentication/step-up phù hợp, thay vì dựa vào `authenticated()` cho mọi thao tác.

### “Đã ký thì khỏi cần CSRF”

**Sai.** Browser tự động gửi cookies (bao gồm remember-me cookie) tới origin phù hợp. Một trang độc hại có thể cố kích hoạt request mà browser kèm cookie, nên các thao tác thay đổi trạng thái cần CSRF protection theo threat model. Remember-me signature **không phải CSRF token**.

## 12. Lưu ý triển khai production

- **Cookie:** giới hạn `Path` và `Domain` đúng nhu cầu; đặt `Secure` khi phục vụ qua HTTPS, dùng `HttpOnly` và `SameSite` theo mô hình browser. Với TLS termination ở reverse proxy, cấu hình trusted forwarded headers đúng để server nhận biết scheme HTTPS. Không đặt `Domain` rộng một cách vô tình.
- **Key:** secret ngẫu nhiên đủ entropy, lưu trong secrets manager, đồng bộ ở cluster, có quy trình rotate và hiểu ảnh hưởng tới cookie đang sống.
- **TTL:** chọn khoảng sống thấp phù hợp rủi ro; người dùng thiết bị dùng chung cần dễ bỏ chọn Remember me. Xem xét khác biệt giữa remember-me 24 giờ và session login vài phút.
- **Password:** lưu BCrypt/Argon2/PBKDF2 hash theo chính sách, bảo đảm `UserDetailsService` lấy hash ổn định. Thay key hoặc hash có thể khiến tất cả token cũ không dùng được.
- **CSRF:** giữ hoặc thiết kế bảo vệ thích hợp cho thao tác thay đổi trạng thái bằng cookie/session; đừng disable mù vì nghĩ cookie được ký.
- **XSS:** `HttpOnly` giảm khả năng script đọc cookie nhưng không ngăn mọi tác hại của XSS; cần CSP và xử lý input/output đúng.
- **Account state:** tài khoản disabled/locked/deleted phải không được auto-login qua cookie cũ; kiểm tra behavior theo provider, user checker và cache thực tế.
- **Audit:** không ghi nguyên token vào logs. Theo dõi sự kiện login tương tác, auto-login, failure, logout, thay đổi password và key rotation bằng thông tin đủ an toàn.
- **Khu vực nhạy cảm:** dùng `fullyAuthenticated()` cho thao tác cần user tương tác lại; với MFA/recent auth cần rule sâu hơn.
- **Thu hồi theo thiết bị:** nếu yêu cầu thật sự tồn tại, cân nhắc `PersistentTokenBasedRememberMeServices` và kho token; cookie ký thuần không cho revoke một bản sao riêng dễ dàng.
- **Multi-instance:** secret key và dữ liệu user phải nhất quán; nếu hash khác nhau giữa node, remember-me behavior không ổn định.

## 13. Bài tập và kiểm tra hiểu biết

1. **`TokenBasedRememberMeServices` dùng làm gì?** Phát hành và xác minh signed remember-me cookie dựa trên user, expiry, password hash và server secret.
2. **Cookie token-based có được mã hóa không?** Không theo nghĩa bảo mật nội dung; Base64 decode được, chữ ký giúp phát hiện sửa dữ liệu.
3. **Cookie chứa password plaintext hoặc hash ở field riêng không?** Không; password hash được dùng phía server tính lại signature.
4. **Người dùng không tích chọn remember-me thì sao?** Thông thường không phát hành cookie mới, trừ khi cấu hình alwaysRemember.
5. **Sau khi xóa JSESSIONID, cookie remember-me còn dùng được không?** Có thể, nếu browser gửi cookie còn hạn và chữ ký/user hợp lệ.
6. **Tại sao hash đổi có thể vô hiệu hóa cookie?** Signature phụ thuộc `UserDetails.getPassword()` hiện tại.
7. **Vì sao app restart làm cookie demo hết hiệu lực dù raw password không đổi?** BCrypt tạo hash salted mới trong in-memory user store mỗi lần khởi động; signature đã dùng hash cũ.
8. **Sự khác nhau giữa `RememberMeAuthenticationToken` và `UsernamePasswordAuthenticationToken` là gì?** Token trước là danh tính được khôi phục qua remember-me; token sau thường đại diện cho đăng nhập tương tác username/password.
9. **`authenticated()` và `fullyAuthenticated()` có tương đương khi remember-me?** Không; remember-me thường thỏa authenticated nhưng không thỏa fullyAuthenticated.
10. **Có thể lấy username/expiry từ cookie để tự cấp authentication không?** Không, phải kiểm chứng chữ ký, trạng thái user và quy trình provider của Spring Security.
11. **Logout có thu hồi mọi cookie bị sao chép không?** Không đảm bảo; không có per-device revocation store mặc định.
12. **Khi nhiều node dùng key khác nhau thì sao?** Cookie do node A ký có thể bị node B từ chối; cần key nhất quán hoặc chiến lược rotation.
13. **Vì sao signed cookie vẫn cần HTTPS?** Vì kẻ đánh cắp nguyên cookie có thể replay, dù không thể sửa chữ ký.
14. **Cookie remember-me có phải CSRF token không?** Không; browser có thể tự gửi cookie trong request bị CSRF.

## 14. Checklist vận hành

- [ ] Chỉ phát cookie sau login đã xác thực và lựa chọn nhớ đăng nhập phù hợp chính sách.
- [ ] Dùng `TokenBasedRememberMeServices`/`RememberMeConfigurer` đúng chuẩn, không tự tạo chữ ký từ dữ liệu client bằng thuật toán tự chế.
- [ ] Bảo vệ secret key, đồng bộ khi chạy nhiều instance và có kế hoạch rotation.
- [ ] Đặt thời hạn hợp lý cho cả signed expiration và browser cookie; test hết hạn tại server.
- [ ] Dùng hash mật khẩu đã lưu ổn định, tránh tái hash ngẫu nhiên ở mỗi startup.
- [ ] Kiểm tra `RememberMeAuthenticationFilter` và `RememberMeAuthenticationProvider` được cài đúng chain/key.
- [ ] Không dùng dữ liệu username/role giải Base64 như bằng chứng xác thực.
- [ ] Bảo vệ URL nhạy cảm bằng `fullyAuthenticated()` hoặc cơ chế step-up mạnh hơn.
- [ ] Dùng HTTPS, HttpOnly/Secure/SameSite thích hợp, chống XSS và CSRF.
- [ ] Test mất session cookie nhưng còn remember-me cookie, thử cookie bị sửa/hết hạn/password đổi/account khóa.
- [ ] Hiểu rằng logout xóa cookie hiện tại không bảo đảm thu hồi bản sao token đã bị lấy cắp.
- [ ] Nếu cần quản lý thiết bị, cân nhắc persistent-token repository và cơ chế thu hồi server-side.

**Tóm tắt:** `TokenBasedRememberMeServices` phát hành **cookie Base64 chứa username, thời hạn, thông tin thuật toán và chữ ký**. Server dùng **secret key + password hash hiện tại** để kiểm chứng cookie khi session không còn authentication. Chữ ký bảo vệ **tính toàn vẹn**, không bảo vệ **tính bí mật** và không chống **replay** khi cookie bị đánh cắp. `RememberMeAuthenticationFilter` tạo danh tính nhớ đăng nhập, còn `fullyAuthenticated()` giúp yêu cầu người dùng đăng nhập tương tác lại ở những tài nguyên quan trọng.