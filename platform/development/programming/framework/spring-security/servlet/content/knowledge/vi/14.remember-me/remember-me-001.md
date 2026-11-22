# Remember-me và sự khác biệt với kéo dài thời gian sống `HttpSession`

**Module:** Spring Security – Servlet  
**Nhóm:** Ghi nhớ đăng nhập  
**Ví dụ:** Java 17 · Spring Boot 3.3.5 · Spring Security 6.x · Spring MVC/Servlet + Thymeleaf.

## Mục tiêu bài học

Người dùng đánh dấu **“Ghi nhớ đăng nhập”** để có thể quay lại website sau khi phiên thông thường hết hạn mà không phải nhập lại mật khẩu. Spring Security cung cấp cơ chế **remember-me** cho tình huống đó. Tuy nhiên, remember-me **không phải** việc tăng `HttpSession` timeout từ 30 phút thành 14 ngày.

Sau bài học, bạn có thể:

1. Phân biệt **session authentication** với **remember-me authentication**, session cookie (`JSESSIONID`) với remember-me cookie.
2. Giải thích lúc nào Spring Security gọi `RememberMeServices`, lúc nào dựng `RememberMeAuthenticationToken`, và vì sao request sau khi session mất vẫn có thể được xác thực từ remember-me cookie.
3. Hiểu `SessionCreationPolicy` và `server.servlet.session.timeout` ảnh hưởng gì tới session, nhưng **không** đồng nghĩa thay đổi vòng đời remember-me token.
4. Cấu hình form login, checkbox `remember-me`, token validity, signing key, `UserDetailsService`, `logout` và **phân biệt `authenticated()` với `fullyAuthenticated()`**.
5. So sánh remember-me dạng **token được ký trong cookie** với **persistent token** có bảng lưu trữ và token rotation.
6. Đánh giá rủi ro mất cookie, replay, logout, đổi mật khẩu, đổi key, thu hồi quyền, `Secure`/`HttpOnly`/`SameSite`, CSRF và TLS.
7. Xây dựng ứng dụng Spring Boot Java 17 đầy đủ, chạy `mvn test`, quan sát cookies và kiểm thử remember-me bằng MockMvc.

**Thông điệp chính:** `HttpSession` lưu kết quả xác thực của một phiên đang hoạt động; remember-me dùng **một credential dài hạn riêng** để **xác thực lại** khi phiên đó không còn. Hai cơ chế có thời gian sống, rủi ro và chính sách thu hồi khác nhau.

## 1. Hai loại “nhớ”: nhớ phiên đang hoạt động và tự đăng nhập lại

### 1.1. Session login thông thường

Người dùng gửi form login với username/password, `UsernamePasswordAuthenticationFilter` yêu cầu `AuthenticationManager` xác thực. Sau khi thành công, Spring Security có thể lưu `SecurityContext` chứa `Authentication` vào `HttpSession`.

Browser giữ cookie phiên (thường mang tên `JSESSIONID`) để ở các request tiếp theo server tìm đúng session. Không cần gửi lại password ở mỗi request; server sử dụng thông tin đăng nhập đã lưu trong security context của phiên.

```text
POST /perform-login (username + password + CSRF)
  → kiểm tra credentials → xác thực thành công
  → SecurityContext gắn với HttpSession
  → Set-Cookie: JSESSIONID=... (tùy container/cấu hình)
  → GET /api/me + Cookie: JSESSIONID=...
  → lấy Authentication từ SecurityContext của phiên
```

Session có thể mất hiệu lực vì **idle timeout**, logout, invalidation, thay đổi hạ tầng hoặc policy. Khi session hết hiệu lực, `JSESSIONID` cũ không còn đủ để phục hồi danh tính; nếu không có cơ chế khác, request protected sẽ chuyển về login.

### 1.2. Remember-me: credential bổ sung để xác thực lại

Nếu người dùng đã chọn “Ghi nhớ đăng nhập” và cấu hình remember-me được bật, lúc form login thành công, ứng dụng có thể phát thêm một **remember-me cookie**. Khi phiên thường không còn, browser vẫn có thể gửi remember-me cookie còn hạn, để Spring Security **tự động xác thực lại** người dùng.

```text
POST /perform-login (đúng password + remember-me=on + CSRF)
  → Authentication thành công
  → JSESSIONID cho phiên bình thường (nếu có)
  → remember-me=<token> còn hạn dài hơn

Một thời gian sau:
  → session hết hạn / không gửi JSESSIONID
  → browser gửi Cookie: remember-me=<token>
  → RememberMeAuthenticationFilter + RememberMeServices kiểm tra token
  → tạo Authentication dạng remember-me, đưa vào SecurityContext
  → controller có thể cho truy cập endpoint yêu cầu authenticated()
```

Dù cùng tên gọi “nhớ đăng nhập”, **remember-me không biến phiên gốc thành session kéo dài**. Khi remember cookie được chấp nhận, có **một lần authentication mới** trên request đó. Tùy repository/session policy, kết quả có thể lại được lưu vào một phiên mới.

### 1.3. Bảng đối chiếu nhanh

| Tiêu chí | Kéo dài `HttpSession` | Spring Security remember-me |
| --- | --- | --- |
| Cơ chế cốt lõi | Giữ session server-side lâu hơn và gửi session ID qua cookie | Giữ một credential remember-me riêng để xác thực lại sau khi session mất |
| Cookie thường thấy | `JSESSIONID` hoặc cookie session tùy cấu hình | `remember-me` hoặc tên đã cấu hình |
| Nơi giữ danh tính qua request | `SecurityContext` trong session repository | Token cookie được kiểm tra qua `RememberMeServices`; sau đó tạo `Authentication` |
| Thời hạn | Session **idle timeout**; có thể được gia hạn bởi các truy cập tùy cơ chế | Token validity/max-age riêng, thường tính từ lúc token được phát hành; tùy chiến lược có thể rotate |
| Server-side state | `HttpSession` và có thể session store | Token-based có thể không cần token DB; persistent-token cần token repository |
| Logout thông thường | Invalidate session, xóa context/cookie | Phải xóa cookie remember-me; nếu persistent-token, thu hồi record tương ứng |
| Phân biệt mức tin cậy | Login bằng password gần đây có thể được xem là fully authenticated | Spring Security phân loại remember-me authentication riêng, thường không đáp ứng `fullyAuthenticated()` |
| Mất cookie | Mất session identity (nếu không còn credential khác) | Mất khả năng tự đăng nhập lại |
| Token bị sao chép | Session ID có thể bị chiếm dụng | Remember-me token là bearer credential, cũng có nguy cơ bị replay |
| Thay đổi mật khẩu/key | Không nhất thiết làm session hiện tại mất hiệu lực ngay | Tác động tùy chiến lược; token-based signature có thể phụ thuộc password hash và signing key |

**Tối quan trọng:** Có thể có **cả hai cookies trong browser cùng lúc**. Trong khi session còn hợp lệ, Spring Security thường dùng authentication của session; khi session không còn, remember-me mới có cơ hội xác thực lại.

## 2. Vòng đời chính xác: login → có session → session mất → remember-me

```mermaid
sequenceDiagram
    participant B as Trình duyệt
    participant F as Spring Security Filters
    participant S as HttpSession / SecurityContextRepository
    participant R as RememberMeServices
    participant U as UserDetailsService
    B->>F: POST /perform-login (username, password, remember-me, CSRF)
    F->>U: Xác thực username/password
    U-->>F: UserDetails hợp lệ
    F->>S: Lưu Authentication của login vào session
    F->>R: loginSuccess(request,response,authentication)
    R-->>B: Set-Cookie: remember-me=<token>
    F-->>B: Redirect /api/me; JSESSIONID (nếu có)
    B->>F: GET /api/me với JSESSIONID còn hiệu lực
    S-->>F: Authentication từ session
    F-->>B: 200, rememberMe=false
    Note over B,S: Session hết hạn hoặc không gửi session cookie
    B->>F: GET /api/me chỉ với remember-me cookie
    S-->>F: Không có Authentication của phiên
    F->>R: autoLogin(request,response)
    R->>U: Tìm user, kiểm tra token/điều kiện hợp lệ
    R-->>F: RememberMeAuthenticationToken
    F-->>B: 200, rememberMe=true nếu endpoint cho phép
```

Sơ đồ là mô hình khái niệm của **form login + remember-me**; thứ tự chi tiết của filters/repository phụ thuộc phiên bản và cấu hình. Khi remember-me auto-login thành công, các thành phần có thể lưu context, gọi session strategy và tạo một session mới tùy setup. Không suy luận “remember-me chỉ chạy khi browser đóng rồi mở lại”; điều kiện chính là **request hiện tại chưa có Authentication hợp lệ** và có credential remember-me đủ điều kiện.

### 2.1. Điều kiện nhận remember-me cookie

Các điều kiện điển hình gồm:

- Remember-me được cấu hình trong `SecurityFilterChain` xử lý request đó.
- Không có authentication hiện hành đủ để filter bỏ qua auto-login.
- Browser gửi remember-me cookie theo đúng domain, path, `Secure` và policy cookie.
- Token còn trong thời hạn hợp lệ, không bị sửa và đáp ứng tiêu chí kiểm chứng của strategy.
- Tài khoản vẫn tồn tại, có trạng thái thích hợp; việc thu hồi token/password có hiệu lực phụ thuộc cách implement.
- Token repository còn lưu và nhận đúng token nếu dùng persistent-token strategy.

Khi không có cookie hoặc token sai/hết hạn, request protected vẫn cần đăng nhập thật; **không biến remember-me thất bại thành authenticated tự động**.

## 3. `HttpSession` timeout hoạt động độc lập

`HttpSession` có **max inactive interval**: nếu phiên không có request truy cập trong khoảng thời gian được cấu hình, container có thể hết hạn phiên. Đây là thời gian **không hoạt động**, không phải “ngày hết hạn ghi trên token remember-me”.

Với Spring Boot Servlet:

```properties
# Ví dụ cho môi trường học: session có thể hết hạn sau 60 giây không hoạt động.
server.servlet.session.timeout=1m
```

Hoặc trong servlet code:

```java
// Fragment bên trong handler có HttpServletRequest request:
HttpSession session = request.getSession(false);
if (session != null) {
    session.setMaxInactiveInterval(60); // giây
}
```

Ở Spring Boot 3, import là `jakarta.servlet.http.HttpSession` và `jakarta.servlet.http.HttpServletRequest`. Đây là đoạn minh họa, không phải một class độc lập. Đừng gọi `request.getSession()` chỉ để kiểm tra session, vì hàm này có thể tạo phiên mới; dùng `getSession(false)` khi chỉ muốn quan sát.

**Tăng session timeout từ 30 phút lên 14 ngày không tương đương remember-me:**

1. Server vẫn phải quản lý session và dữ liệu của nó qua thời gian dài.
2. Một session ID bị đánh cắp có thể sống lâu hơn, làm tăng cửa sổ chiếm dụng phiên.
3. Quyền, trạng thái user và authorities đã lưu trong session có thể cũ nếu không có chính sách refresh/invalidation.
4. Tài nguyên session trong Redis/Tomcat hoặc session store tăng theo số phiên và TTL.
5. Không có phân biệt ngữ nghĩa riêng giữa session vừa được login bằng password và identity vừa được tự nhớ qua remember-me.
6. Nếu cookie `JSESSIONID` là session cookie, browser có thể xử lý khác nhau khi đóng/mở so với cookie remember-me có `Max-Age`; không giả định đóng browser luôn hủy hoặc luôn khôi phục session cookie.
7. Session vẫn có thể bị chủ động invalidate/logout và không tự “phục hồi login” nếu không có credential khác.

### 3.1. Timeout 14 ngày ở remember-me không kéo dài phiên gốc 14 ngày

Khi cấu hình:

```java
http.rememberMe(remember -> remember
        .tokenValiditySeconds(14 * 24 * 60 * 60));
```

Mốc này là **14 ngày** cho remember-me token, **không phải** giá trị `server.servlet.session.timeout`. Remember cookie có thể được browser giữ tới hạn đó, nhưng browser/user policy có thể xóa nó trước; token strategy còn phải kiểm tra tính hợp lệ phía server. Với persistent-token, auto-login thành công có thể **rotate** token (và cập nhật thời gian dùng); chính sách thực tế phải kiểm tra để biết cửa sổ hiệu lực được gia hạn hay giới hạn.

Hãy dùng các tham số độc lập theo mục tiêu: session timeout phục vụ **phiên đang hoạt động**, remember-me validity phục vụ **khả năng xác thực lại khi phiên không còn**.

## 4. Remember-me authentication có mức tin cậy khác login trực tiếp

Spring Security phân biệt authentication dựa vào remember-me với đăng nhập đầy đủ bằng credential qua `AuthenticationTrustResolver`. Thường sau auto-login, principal vẫn có username và roles, nhưng `Authentication` là một `RememberMeAuthenticationToken`.

| Rule | User đăng nhập từ form password trong phiên | User chỉ được tự xác thực bằng remember-me cookie |
| --- | --- | --- |
| `.permitAll()` | Cho phép | Cho phép |
| `.authenticated()` | Cho phép | Cho phép nếu remember-me token hợp lệ |
| `.fullyAuthenticated()` | Cho phép | **Không**; thường phải đăng nhập tương tác lại |
| `.hasRole("USER")` | Xét role của user | Có thể cho phép nếu remember-me Authentication có role tương ứng |
| `.hasRole("ADMIN")` | Phụ thuộc role | Phụ thuộc role; không tự yêu cầu password login lại |

Vì vậy với hành động rủi ro cao như thay password, xem dữ liệu đặc biệt nhạy cảm, xóa tài khoản hoặc thêm phương thức thanh toán, **đừng chỉ dựa vào `.authenticated()`** nếu nghiệp vụ yêu cầu bước xác thực gần đây. `.fullyAuthenticated()` loại trừ remember-me, nhưng **không tự bảo đảm** người dùng đã cung cấp password trong vài phút gần đây, có MFA hoặc đúng mức AAL; các yêu cầu “recent login” và step-up authentication cần thiết kế thêm.

Ví dụ phân quyền:

```java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/sign-in", "/public/ping").permitAll()
        .requestMatchers("/api/strong").fullyAuthenticated()
        .anyRequest().authenticated());
```

Đây là **fragment**. Ví dụ project ở phần 8 cung cấp class/import và các tests hoàn chỉnh.

### 4.1. `isAuthenticated()` chưa đủ phân biệt remember-me

Một `RememberMeAuthenticationToken` hợp lệ có thể có `isAuthenticated() == true`. Nếu business code dùng `authentication.isAuthenticated()` để coi người dùng “vừa nhập password”, đó là đánh giá sai.

Dùng `AuthenticationTrustResolver`, hoặc rule `.fullyAuthenticated()` tại security layer, để xác định remembered identity:

```java
AuthenticationTrustResolver trust = new AuthenticationTrustResolverImpl();
boolean remembered = trust.isRememberMe(authentication);
boolean fullyAuthenticated = trust.isFullyAuthenticated(authentication);
```

`AuthenticationTrustResolver` và `AuthenticationTrustResolverImpl` nằm trong `org.springframework.security.authentication`. Đoạn code là fragment cần biến `Authentication authentication` hợp lệ ở method hiện hành.

## 5. Hai chiến lược remember-me phổ biến của Spring Security

### 5.1. Token-based remember-me: cookie có thông tin được ký

Một cấu hình thường dùng là **token-based remember-me**, sử dụng `TokenBasedRememberMeServices`. Token gửi về client chứa các thành phần phục vụ việc kiểm tra người dùng, thời hạn và **signature** dựa trên secret key và thông tin credential phía server. Nó **không phải** lưu nguyên mật khẩu vào cookie.

Đặc điểm:

- Có thể không cần bảng remember-me token riêng ở database.
- `UserDetailsService` cần đọc user khi tự xác thực lại.
- `key` là secret quan trọng; nên đủ mạnh, lưu ở secret manager hoặc environment và nhất quán giữa các instance nếu muốn cookie dùng được qua nhiều node.
- Thay signing key có thể làm toàn bộ cookie phát trước đó không còn xác minh được.
- Với chiến lược token-based chuẩn, tính hợp lệ có thể phụ thuộc encoded password của user. Đổi mật khẩu/hash có thể làm token cũ mất hiệu lực.
- **Cookie được ký vẫn là bearer credential**: người khác sao chép được cookie còn hạn có thể dùng nó nếu server chấp nhận, không cần biết plaintext password.
- Xóa cookie lúc logout **không thu hồi bản sao đã bị đánh cắp** của một token stateless còn hợp lệ. Muốn revocation có thể cần store/version/key rotation hoặc chiến lược persistent-token.
- Không gọi cookie này là “JWT”. Nó có cấu trúc riêng theo Spring Security/version, không phải một access token chuẩn OAuth2.
- Thay đổi encoded password hash **vì startup tạo lại hash với salt mới** cũng có thể làm token cũ mất hiệu lực, dù raw password không đổi. Ví dụ demo tạo BCrypt hash mới khi khởi động; xem lưu ý phần 8.

Một cấu hình có thể dùng:

```java
http.rememberMe(remember -> remember
        .rememberMeParameter("remember-me")
        .userDetailsService(userDetailsService)
        .key(rememberSigningKey)
        .tokenValiditySeconds(14 * 24 * 60 * 60));
```

Không hardcode secret thật trong code; `rememberSigningKey` cần được cung cấp bởi cấu hình có kiểm soát. Phần code trên là fragment, không phải chương trình hoàn chỉnh.

### 5.2. Persistent-token remember-me: server giữ series/token

Spring Security còn cung cấp `PersistentTokenBasedRememberMeServices` kết hợp `PersistentTokenRepository` (ví dụ `JdbcTokenRepositoryImpl`) và bảng token persistent.

Đường đi khái niệm:

```text
Login thành công + chọn remember-me:
  → sinh series và token ngẫu nhiên
  → lưu record (username, series, token, last_used) vào DB
  → gửi remember-me cookie tới browser

Auto-login bằng remember-me cookie:
  → tra record theo series
  → so sánh token
  → nếu hợp lệ: tạo token mới, cập nhật record và cookie (rotation)
  → nếu token không khớp: xử lý như sự kiện nghi bị đánh cắp token

Logout:
  → có thể xóa token record liên quan tới user khỏi repository
  → xóa remember-me cookie phía browser
```

Đặc điểm:

- Cần **durable storage** để remember-me tồn tại qua restart/server instances.
- Có thể thu hồi token bằng việc xóa row/series của user; Spring Security có logic xử lý token không khớp có thể làm mất hiệu lực các token của user để hạn chế replay.
- Token rotation làm cookie mới thay đổi sau auto-login, nhưng đồng thời có thể gây **race** nếu browser có request song song dùng token cũ. Cần đánh giá UX, log và chiến lược chống replay/race ở ứng dụng thật.
- Database mất dữ liệu, read replica không đồng bộ hoặc token lookup lỗi có thể khiến auto-login thất bại.
- `PersistentTokenRepository` phải được bảo vệ như kho chứa **credential**; token nên có đủ entropy, dùng TLS, hạn chế quyền truy cập và retention.
- Khi logout trên nhiều thiết bị, cần phân biệt **thu hồi tất cả token của account** và **chỉ thu hồi một thiết bị**, phụ thuộc implementation/token model. Không mặc định cơ chế repository đơn giản đã hỗ trợ device-specific logout như sản phẩm cần.
- Lịch hết hạn/cookie lifetime, cleanup DB rows và chiến lược xử lý tài khoản bị khóa phải được kiểm thử.

#### 5.2.1. Schema database điển hình

Spring Security `JdbcTokenRepositoryImpl` thường sử dụng bảng `persistent_logins`:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Đây là cấu trúc minh họa tương thích với ví dụ JDBC token repository thông dụng. Trong production, cân nhắc loại dữ liệu/indexes, schema migration, cleanup và chính sách truy cập cho DB.

#### 5.2.2. Fragment cấu hình nếu dùng JDBC

Khi muốn chuyển project demo sang persistent token, cần thêm `spring-boot-starter-jdbc`, JDBC driver, `DataSource`/schema và bean repository:

```java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
```

Imports gồm `javax.sql.DataSource`, `org.springframework.security.web.authentication.rememberme.PersistentTokenRepository`, `org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl`. Trong cấu hình remember-me thay bằng:

```java
http.rememberMe(remember -> remember
        .userDetailsService(userDetailsService)
        .tokenRepository(persistentTokenRepository)
        .key(rememberSigningKey)
        .tokenValiditySeconds(14 * 24 * 60 * 60));
```

Đây là **fragment cho biến thể JDBC**, không thuộc project runnable token-based phía dưới. Để chạy biến thể JDBC phải tự bảo đảm schema đã được tạo, DataSource hoạt động và lưu token đủ lâu. Không thêm repository vào Spring context rồi tưởng framework tự tạo table/migrations cho mọi database. Với cluster, token store cần dùng chung.

### 5.3. So sánh chiến lược

| Yêu cầu | Token-based có chữ ký | Persistent-token |
| --- | --- | --- |
| Bảng remember-me riêng | Không bắt buộc | Có |
| Qua restart | Phụ thuộc key ổn định, password hash/record ổn định và còn hạn | Phụ thuộc persistent DB, key/config và record còn hạn |
| Thu hồi một token đã bị sao chép | Khó nếu không bổ sung state/rotation hoặc thay key/password | Có khả năng thu hồi bằng dữ liệu server, tùy token model |
| Logout xóa cookie phía browser | Có | Có |
| Logout có thu hồi cookie bị copy không? | Không chắc; token ký còn hạn có thể bị replay | Có thể thu hồi tại DB; phải biết implementation xóa token theo user/series |
| Request auto-login | Xác minh signature và user | Tra DB, kiểm tra token, thường rotate |
| Vận hành | Ít hạ tầng hơn | Cần DB, cleanup, concurrency strategy |
| Phù hợp | Ứng dụng nhỏ, yêu cầu revocation đơn giản và hạn dùng ngắn có cân nhắc | Ứng dụng cần kiểm soát server-side các credential ghi nhớ |

**Không nhầm:** Cả hai đều khác với **session timeout**. Persistent-token có DB riêng và vẫn dùng cookie, chứ không chỉ kéo dài `JSESSIONID`.

## 6. Cookie, session, logout và bảo mật

### 6.1. Cookie remember-me là credential dài hạn

Cookie remember-me có thể khôi phục danh tính mà **không cần nhập lại password**. Vì vậy đối xử với nó như secret:

- **HTTPS bắt buộc** ở môi trường thật. Cookie có `Secure` khi appropriate và server/proxy cần nhận diện scheme HTTPS đúng.
- `HttpOnly` giúp hạn chế JavaScript truy cập cookie, nhưng không giải quyết mọi XSS/CSRF và không thay TLS.
- `SameSite` cần được kiểm tra cho browser/client thực tế; chính sách này có khác biệt giữa browser và không thay thế CSRF protection.
- Giới hạn domain/path để browser không gửi cookie tới host/path không cần thiết; tránh đặt cookie trên domain rộng nếu không cần.
- Chọn token lifetime theo rủi ro, không chỉ theo ý muốn “khỏi đăng nhập lâu”.
- Rotate/signing key an toàn; có thể cần hỗ trợ key migration hoặc chấp nhận mọi cookie cũ hết hiệu lực.
- Không log `Cookie`, `Set-Cookie`, token remember-me hoặc request headers chứa secret.
- Có cơ chế cảnh báo đăng nhập bất thường, thiết bị mới, thay password, khóa tài khoản và chủ động vô hiệu hóa credential.
- Cân nhắc yêu cầu MFA/recent authentication cho hành động nhạy cảm; `fullyAuthenticated()` là bước đầu nhưng không tự cung cấp MFA.

**Lưu ý dev local:** Mẫu dưới đây chạy trên `http://localhost` với password giả để học. Cookie `Secure` nên được yêu cầu khi deploy HTTPS; nếu luôn bật `Secure` trong ví dụ localhost HTTP thì browser thường không gửi cookie như mong muốn. Đừng tái sử dụng cấu hình dev không-TLS trong production.

### 6.2. Logout phải xóa những gì?

Một luồng form login với remember-me thường cần:

1. Invalidate phiên `HttpSession` hiện tại khi logout.
2. Xóa `SecurityContext` và session cookie theo policy.
3. Gửi cookie remember-me với thời hạn hết hiệu lực để browser xóa credential.
4. Nếu dùng persistent-token, xóa/revoke token records tương ứng theo implementation.
5. Bảo vệ logout endpoint khỏi CSRF (ví dụ POST có CSRF token khi CSRF bật).
6. Xác định có cần thu hồi các phiên/remember-me tokens khác của cùng user hay không.

**Rủi ro trọng yếu:** Với signed token-based cookie, logout chủ yếu khiến browser bỏ cookie. Một bản sao cookie đã bị đánh cắp **có thể còn dùng được** tới khi hết hạn hoặc key/password hash thay đổi. Session logout không tự thu hồi bearer cookie đã bị sao chép.

Ngược lại, **session timeout** không nhất thiết kích hoạt cleanup của remember-me cookie. Điều này là chủ đích: remember-me tồn tại để login lại sau session timeout.

### 6.3. Tại sao bật `rememberMe()` không thay session policy?

`rememberMe()` thêm chiến lược auto-login và cookie; `sessionManagement` quy định cách Spring Security quản lý/giới hạn các phiên. Bạn có thể cấu hình thời gian session khác với token validity. Những thành phần có thể cùng tồn tại.

`SessionCreationPolicy.STATELESS` có thể phù hợp với API Basic/Bearer tự xác thực mỗi request, nhưng không phải lựa chọn mặc định tối ưu cho browser **form login + remember-me** nếu dự kiến sau login giữ session. Khi form login dùng session, policy như `IF_REQUIRED` thường phù hợp và việc remember-me auto-login có thể tạo một phiên mới sau khi session cũ biến mất.

Không dùng `rememberMe()` để làm access token dài hạn cho API mobile/bearer. Cookie và browser-oriented behavior khác hệ thống OAuth2/OIDC token lifecycle.

### 6.4. Không hiểu sai browser “đóng tab” hoặc “đóng browser”

Không có quy tắc duy nhất rằng đóng tab làm session cookie mất hoặc browser restart chắc chắn xóa phiên. Browser có session restore và chính sách cookie khác nhau. Một cookie remember-me thường có `Max-Age` để có thể sống lâu hơn phiên cookie, nhưng người dùng/cài đặt bảo mật vẫn có thể xóa trước. Khi test, **cố tình bỏ JSESSIONID** hoặc invalidate session, không dùng “đóng tab” làm điều kiện test duy nhất.

### 6.5. Tránh user enumeration và stale authorities

Khi remember-me tự xác thực lại, `UserDetailsService` hoặc user repository có thể đọc lại tài khoản và authorities. Nếu tài khoản bị khóa, vô hiệu hóa hoặc role thay đổi, cần đánh giá cách cập nhật/chặn quyền ở lần auto-login tiếp theo. Bản ghi session hiện tại có thể chứa authorities cũ; remember-me không tự giải quyết mọi vấn đề đồng bộ quyền và phân quyền.

Không viết thông báo lỗi chi tiết cho attacker biết username nào tồn tại hoặc cookie nào từng hợp lệ. Với truy cập đáng ngờ, ghi audit an toàn và cân nhắc giới hạn tần suất.

## 7. Lập kế hoạch bài demo: những gì sẽ chứng minh được

Project dưới đây minh họa **token-based remember-me** để không cần cấu hình DB. Các URL:

| URL | Quyền | Hành vi |
| --- | --- | --- |
| `GET /public/ping` | Public | Trả `"pong"` |
| `GET /sign-in` | Public | Hiển thị form login Thymeleaf với checkbox `remember-me` |
| `POST /perform-login` | Form login processing | Đọc username/password/CSRF và optional checkbox; do Spring Security filter xử lý, không có MVC POST controller |
| `GET /api/me` | `.authenticated()` | Trả JSON username và cờ `rememberMe` |
| `GET /api/strong` | `.fullyAuthenticated()` | Chỉ session/login thực sự; remembered identity phải đăng nhập tương tác lại |
| `POST /logout` | Spring Security logout filter | Invalidate session, clear context và cookie remember-me; CSRF vẫn yêu cầu |
| `GET /sign-in?error` | Public | Form hiển thị lỗi chung, không tiết lộ user tồn tại |
| `GET /sign-in?logout` | Public | Form hiển thị trạng thái logout |

**Tài khoản demo:** `student` / `demo-pass`; chỉ sử dụng cục bộ. Password được băm bằng BCrypt và tạo mới khi Spring context khởi động. **Vì hash mới có salt khác**, token-based remember-me cookie của instance cũ có thể bị vô hiệu sau restart **dù signing key không đổi**. Project vì vậy chứng minh auto-login **khi ứng dụng đang chạy và session mất**, không hứa persist remember-me qua restart. Trong production, hash tài khoản được lưu bền vững (DB) và signing key được quản lý ổn định.

Cấu hình demo:

```properties
server.servlet.session.timeout=1m
app.remember-me.key=${REMEMBER_ME_KEY:demo-key-only-change-it-in-production}
```

`1m` dành cho **session không hoạt động**. Token remember-me sẽ cấu hình **14 ngày** trong Java config. Hai tham số độc lập.

## 8. Project Spring Boot đầy đủ

### 8.1. Cây thư mục

```text
remember-me-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/remember/
    │   │   ├── RememberMeApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── SignInController.java
    │   │   └── ApiController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/sign-in.html
    └── test/java/demo/remember/
        └── RememberMeApplicationTests.java
```

Yêu cầu JDK 17+, Maven 3.6.3+ và khả năng tải dependency lần đầu.

### 8.2. `pom.xml`

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
    <groupId>demo</groupId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
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

Starter Web cung cấp Spring MVC/Servlet; Starter Security cung cấp filters/remember-me; Thymeleaf render form. Spring Boot BOM quản lý các version tương thích. Không cần `spring-boot-starter-jdbc` với **token-based** variant.

### 8.3. `src/main/java/demo/remember/RememberMeApplication.java`

```java
package demo.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
```

### 8.4. `src/main/resources/application.properties`

```properties
server.servlet.session.timeout=1m
app.remember-me.key=${REMEMBER_ME_KEY:demo-key-only-change-it-in-production}
```

Khi chạy production, set `REMEMBER_ME_KEY` bằng secret đủ mạnh lưu trong secret manager, tránh log và đồng bộ across instances. Dev default được chọn chỉ để bài học chạy được trên localhost. Nếu cần xoay key, hiểu rằng cookie được ký bằng key cũ có thể hết hiệu lực.

### 8.5. `src/main/java/demo/remember/SecurityConfig.java`

```java
package demo.remember;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService userDetailsService,
            @Value("${app.remember-me.key}") String rememberSigningKey)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET,
                        "/public/ping", "/sign-in").permitAll()
                .requestMatchers("/api/strong").fullyAuthenticated()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .loginPage("/sign-in")
                .loginProcessingUrl("/perform-login")
                .defaultSuccessUrl("/api/me", true)
                .failureUrl("/sign-in?error")
                .permitAll());

        http.rememberMe(remember -> remember
                .rememberMeParameter("remember-me")
                .userDetailsService(userDetailsService)
                .key(rememberSigningKey)
                .tokenValiditySeconds(14 * 24 * 60 * 60));

        http.logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/sign-in?logout")
                .invalidateHttpSession(true)
                .deleteCookies("JSESSIONID")
                .permitAll());

        // CSRF vẫn bật; form POST phải mang CSRF token.
        return http.build();
    }
}
```

**Hai đồng hồ thời gian khác nhau:**

- `server.servlet.session.timeout=1m`: phiên `HttpSession` có thể hết hạn khi không hoạt động một phút. Đó không phải TTL của remember-me cookie.
- `tokenValiditySeconds(14 * 24 * 60 * 60)`: nhớ danh tính trong 1.209.600 giây (14 ngày) theo chính sách token. Cookie vẫn có thể bị browser hoặc user xóa sớm, hoặc bị backend từ chối vì account/key/hash không còn phù hợp.

`rememberMeParameter("remember-me")` làm checkbox form có `name="remember-me"` trở thành tín hiệu **opt-in**; nếu không chọn, một login mới thông thường **không được phát remember-me cookie**. Có lựa chọn `alwaysRemember(true)` nếu nghiệp vụ thực sự muốn luôn phát cookie, nhưng mặc định opt-in minh bạch thường dễ giải thích và có lợi về quyền riêng tư.

**Không** gọi `.sessionCreationPolicy(SessionCreationPolicy.STATELESS)` trong project này: ứng dụng muốn giữ phiên browser bình thường và chỉ dùng remember-me khi không còn session. `HttpSession` không bị thay thế bằng cookie remember-me; hai mechanism cùng phối hợp.

**Không tự viết** `@PostMapping("/perform-login")` hoặc `@PostMapping("/logout")`: các URL này được xử lý bởi security filters. Với CSRF bật, logout qua POST có token hợp lệ; truy cập GET `/logout` không giống POST logout.

### 8.6. `src/main/java/demo/remember/SignInController.java`

```java
package demo.remember;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class SignInController {

    @GetMapping("/sign-in")
    public String signIn() {
        return "sign-in";
    }
}
```

Khi khai báo `.loginPage("/sign-in")`, bạn cần cung cấp **GET trang login riêng**; framework không tự tạo template HTML cho URL tùy chỉnh. Handler trả view `sign-in` để Thymeleaf tìm `templates/sign-in.html`.

### 8.7. `src/main/resources/templates/sign-in.html`

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập và ghi nhớ</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}">
        Tài khoản hoặc mật khẩu không hợp lệ.
    </p>
    <p th:if="${param.logout}">
        Bạn đã đăng xuất.
    </p>

    <form th:action="@{/perform-login}" method="post">
        <label for="username">Tài khoản</label>
        <input id="username"
               type="text"
               name="username"
               autocomplete="username"
               required>

        <label for="password">Mật khẩu</label>
        <input id="password"
               type="password"
               name="password"
               autocomplete="current-password"
               required>

        <label for="remember-me">
            <input id="remember-me"
                   type="checkbox"
                   name="remember-me"
                   value="on">
            Ghi nhớ đăng nhập
        </label>

        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
```

Các tên trường phải khớp filter/form login:

- `name="username"` và `name="password"` dùng mặc định của `UsernamePasswordAuthenticationFilter`.
- `name="remember-me"` khớp cấu hình `.rememberMeParameter("remember-me")`.
- `th:action="@{/perform-login}"` khớp `.loginProcessingUrl("/perform-login")`.

Với Spring Security + Spring MVC + Thymeleaf, khi render form thông qua tích hợp tương ứng, `th:action` tham gia quá trình xử lý thêm hidden CSRF parameter khi CSRF bật. Nếu sử dụng HTML/JSP khác, phải đưa CSRF token vào POST theo repository hiện dùng. **`permitAll()` cho login URL không tắt CSRF**.

### 8.8. `src/main/java/demo/remember/ApiController.java`

```java
package demo.remember;

import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    private final AuthenticationTrustResolver trust =
            new AuthenticationTrustResolverImpl();

    @GetMapping(value = "/public/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/me")
    public MeResponse me(Authentication authentication) {
        return new MeResponse(
                authentication.getName(),
                trust.isRememberMe(authentication));
    }

    @GetMapping("/api/strong")
    public String strong() {
        return "FULL_LOGIN_REQUIRED";
    }

    public record MeResponse(String username, boolean rememberMe) {}
}
```

Khi login bằng password và dùng session đang có, `/api/me` dự kiến trả `{"username":"student","rememberMe":false}`. Khi phiên bị mất và request chỉ còn remember-me cookie được chấp nhận, `/api/me` dự kiến trả `{"username":"student","rememberMe":true}`. Đây là **khác biệt về loại `Authentication`**, không phải khác biệt về username.

Endpoint `/api/strong` đòi `.fullyAuthenticated()`. Nếu chỉ được nhớ qua cookie, Spring Security thường chuyển hướng người dùng tới trang sign-in để xác thực lại. Không xem `trust.isRememberMe` là một trường về thời gian đăng nhập gần nhất; nó chỉ phân loại cơ chế authentication hiện tại.

## 9. Chạy project và quan sát browser

Tại thư mục `remember-me-demo`:

```bash
mvn clean test
mvn spring-boot:run
```

Mặc định app nghe tại `http://localhost:8080`. Vì ví dụ sử dụng HTTP và demo credentials nên chỉ chạy trên máy cục bộ để học. Ứng dụng thật phải dùng **HTTPS** khi vận chuyển password, session cookie hoặc remember-me cookie.

1. Mở `http://localhost:8080/sign-in`.
2. Nhập `student` / `demo-pass`, **không tick** “Ghi nhớ đăng nhập”. Đăng nhập sẽ đưa bạn tới `/api/me`, `rememberMe=false`. Browser có thể có `JSESSIONID`, nhưng không được phát remember-me cookie mới.
3. Logout bằng một form POST có CSRF token hợp lệ (hoặc dùng test); quay lại `/sign-in`, đăng nhập lần nữa **có tick** checkbox.
4. Quan sát `Set-Cookie` của response login và cookie lưu trong browser. Lúc này có thể có `JSESSIONID` **và** `remember-me`. Đừng chia sẻ giá trị hai cookies đó.
5. Dùng browser devtools trên **dữ liệu demo** để xóa riêng `JSESSIONID` nhưng giữ `remember-me`, hoặc đợi session hết hạn theo policy; reload `/api/me`.
6. Nếu remember-me cookie hợp lệ và user vẫn còn, request có thể được tự xác thực lại; JSON trả `rememberMe=true`.
7. Truy cập `/api/strong` bằng remember-me token: phải xác thực tương tác lại. Đăng nhập lại bằng password rồi truy cập `/api/strong` sẽ được cho phép trong phiên login đầy đủ.
8. Logout bằng POST hợp lệ và quan sát server gửi cookie xóa remember-me. Sau khi browser thực sự xóa cookie này, request mới không có session/remember cookie phải yêu cầu đăng nhập.

**Không coi đóng browser là một phép test determinisitic**: trình duyệt có session restore và cài đặt cookie khác nhau. Việc xóa riêng session cookie có kiểm soát giúp quan sát đúng cơ chế. Nếu bạn dùng H2/token repository ở biến thể persistent, diễn biến thêm phần lookup/rotation token.

### 9.1. Cookie expiration không giống session idle timeout

Khi dùng devtools/Application/Cookies, đừng suy luận rằng `Expires/Max-Age` của cookie `JSESSIONID` phải bằng chính xác `server.servlet.session.timeout`. Session cookie thường chỉ giữ session ID; **server** quyết định phiên có hợp lệ theo inactivity/expiration và policy. Remember-me cookie có thời hạn tương ứng token (theo cấu hình), nhưng vẫn có thể bị chủ động xóa.

## 10. Bộ kiểm thử MockMvc: chứng minh hai cơ chế khác nhau

MockMvc có thể kiểm thử Spring Security filters mà không cần trình duyệt và không mở một network port. Các test này không xác minh thực tế browser có giữ cookie sau restart hay không, nhưng giúp kiểm tra **token phát khi opt-in**, **sự tái xác thực nếu chỉ có remember cookie** và **authorization phân biệt remember-me**.

### 10.1. `src/test/java/demo/remember/RememberMeApplicationTests.java`

```java
package demo.remember;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeApplicationTests {

    @Autowired
    MockMvc mvc;

    private MvcResult login(boolean remember) throws Exception {
        MockHttpServletRequestBuilder request = post("/perform-login")
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/api/me")))
                .andReturn();
    }

    @Test
    void loginPageHasRememberCheckbox() throws Exception {
        mvc.perform(get("/sign-in"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("name=\"remember-me\"")));
    }

    @Test
    void unauthenticatedPrivateRequestRedirectsToLogin()
            throws Exception {
        mvc.perform(get("/api/me")
                        .accept(MediaType.TEXT_HTML))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in")));
    }

    @Test
    void loginWithoutRememberDoesNotSetRememberCookie()
            throws Exception {
        MvcResult loggedIn = login(false);
        assertNull(loggedIn.getResponse().getCookie("remember-me"));

        MockHttpSession session = (MockHttpSession)
                loggedIn.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"))
                .andExpect(jsonPath("$.rememberMe").value(false));
    }

    @Test
    void optingInIssuesRememberCookieWithSeparateLifetime()
            throws Exception {
        MvcResult loggedIn = login(true);
        Cookie cookie = loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        assertEquals(14 * 24 * 60 * 60, cookie.getMaxAge());
    }

    @Test
    void rememberCookieCanAuthenticateWithoutOriginalSession()
            throws Exception {
        MvcResult loggedIn = login(true);
        Cookie cookie = loggedIn.getResponse().getCookie("remember-me");
        assertNotNull(cookie);

        MockHttpSession prior = (MockHttpSession)
                loggedIn.getRequest().getSession(false);
        assertNotNull(prior);
        prior.invalidate(); // Chỉ bỏ session, không xóa remember cookie.

        mvc.perform(get("/api/me").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("student"))
                .andExpect(jsonPath("$.rememberMe").value(true));
    }

    @Test
    void rememberMeIsNotFullyAuthenticated() throws Exception {
        Cookie cookie = login(true).getResponse()
                .getCookie("remember-me");
        assertNotNull(cookie);

        mvc.perform(get("/api/strong").cookie(cookie))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in")));
    }

    @Test
    void strongEndpointWorksAfterInteractiveLogin()
            throws Exception {
        MockHttpSession session = (MockHttpSession)
                login(false).getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/strong").session(session))
                .andExpect(status().isOk())
                .andExpect(content().string("FULL_LOGIN_REQUIRED"));
    }

    @Test
    void badPasswordDoesNotIssueRememberCookie() throws Exception {
        MvcResult result = mvc.perform(post("/perform-login")
                .with(csrf())
                .param("username", "student")
                .param("password", "wrong")
                .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in?error")))
                .andReturn();

        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void invalidRememberCookieDoesNotAuthenticate() throws Exception {
        Cookie bad = new Cookie("remember-me", "invalid-token");
        mvc.perform(get("/api/me").cookie(bad))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in")));
    }

    @Test
    void logoutClearsRememberCookie() throws Exception {
        Cookie cookie = login(true).getResponse()
                .getCookie("remember-me");
        assertNotNull(cookie);

        MvcResult out = mvc.perform(post("/logout")
                .with(csrf())
                .cookie(cookie))
                .andExpect(status().is3xxRedirection())
                .andExpect(header().string("Location",
                        containsString("/sign-in?logout")))
                .andReturn();

        Cookie cleared = out.getResponse().getCookie("remember-me");
        assertNotNull(cleared);
        assertEquals(0, cleared.getMaxAge());
    }
}
```

Kết quả **dự kiến 10 test PASS** nếu project và phiên bản thư viện phù hợp. Thực thi:

```bash
mvn test
```

**Giải thích từng nhóm test:**

- Hai test đầu kiểm tra trang login công khai/redirect protected.
- Login **không tick checkbox** chứng minh session authentication hoạt động nhưng không phát thêm remember cookie.
- Login có tick checkbox chứng minh remember token được phát với lifetime độc lập.
- Test invalidate `MockHttpSession` rồi gửi **chỉ remember-me cookie** chứng minh session cũ không cần còn tồn tại để có auto-login.
- `.fullyAuthenticated()` từ chối `RememberMeAuthenticationToken`, còn session sau password login cho phép endpoint mạnh.
- Mật khẩu sai không tạo remember cookie.
- Token giả bị từ chối.
- Logout gửi lệnh clear cookie qua `Set-Cookie` tương ứng.

Các test dùng `.with(csrf())` từ `spring-security-test` để tạo CSRF token hợp lệ cho MockMvc; **client thật không thể gửi literal `csrf()`**. Browser cần CSRF token từ trang/view/repository đang dùng.

**Giới hạn:** `MockMvc` không chạy clock thật cho idle timeout 1 phút, không test Browser Session Restore, TLS handshake, cookie policy giữa các browser, distributed session hay token rotation của persistent DB. Muốn kiểm tra timeout thực, dùng embedded server/browser hoặc integration test điều khiển container clock/session lifetime. Kết quả test dự kiến chưa phải log đã chạy ở môi trường production.

### 10.2. Vì sao test login HTTP không gửi thẳng password vào URL?

Form login phải dùng POST có request body và CSRF hợp lệ. Không gắn password vào query string vì URLs có thể nằm trong history, referrer và access log. Trong test, `.param(...)` mô phỏng form parameters với giá trị demo. Khi chạy thật, truyền form qua HTTPS và không log request body chứa credentials.

## 11. Troubleshooting

### 11.1. Tăng session timeout mà browser vẫn bắt login sau khi mở lại

Có thể browser không giữ session cookie, session bị invalidate, session store mất dữ liệu hoặc thời gian inactivity đã trôi qua. **Session timeout chỉ điều khiển session server-side**, không bảo đảm browser giữ và gửi `JSESSIONID` lâu tương ứng. Nếu muốn auto-login sau session hết hạn, hãy cân nhắc remember-me theo threat model.

### 11.2. Tick “Ghi nhớ đăng nhập” nhưng không có remember cookie

Kiểm tra:

1. Form có `name="remember-me"` và value được gửi khi checkbox checked không?
2. Đã bật `.rememberMe(...)` trên đúng `SecurityFilterChain` chưa?
3. `loginProcessingUrl` khớp POST action và POST có CSRF token đúng chưa?
4. Authentication form login thực sự thành công chưa? Remember cookie không nên phát khi mật khẩu sai.
5. Có cấu hình `alwaysRemember`, custom `RememberMeServices`, cookie name/path hoặc proxy viết lại cookies không?
6. Browser có chặn cookie vì `Secure` trên HTTP, SameSite, domain/path hoặc policy riêng không?
7. Nếu login qua custom REST JSON endpoint, remember-me listener có được gọi đúng hay không? Không tự kỳ vọng form-login RememberMeServices làm việc với mọi controller đăng nhập tùy chỉnh.

### 11.3. Có remember cookie nhưng không tự đăng nhập

Kiểm tra cookie đã được **gửi lại** trong request chưa. Sau đó xem:

- Cookie hết hạn hoặc signature/token không hợp lệ.
- Signing key thay đổi giữa các instance/restart.
- Password hash của user đổi; ví dụ InMemoryUserDetailsManager BCrypt băm lại sau mỗi startup.
- User bị disabled/locked/deleted hoặc không được phép tự xác thực.
- Với persistent token, record bị xóa, hết hạn, token lệch sau rotation, repository không kết nối.
- Một security chain khác nhận URL trước và **không bật remember-me**.
- Môi trường dev dùng HTTP với cookie `Secure` nên cookie không được gửi.

Đừng kết luận `HttpSession` timeout gây remember-me thất bại; hai thời hạn khác nhau.

### 11.4. Vẫn vào `/api/me` được nhưng `/api/strong` yêu cầu login

Đó có thể là **hành vi đúng**. RememberMeAuthenticationToken được `.authenticated()` chấp nhận, nhưng `.fullyAuthenticated()` yêu cầu login đầy đủ hơn. Hãy test JSON `rememberMe` ở `/api/me` để biết loại authentication. Không tắt `.fullyAuthenticated()` để tránh lỗi nếu nghiệp vụ thực sự đòi xác thực lại.

### 11.5. Logout xong vẫn đăng nhập lại được khi dùng cookie bị copy

Nếu dùng token-based signed cookie, server không có bản ghi token để thu hồi từng bản sao cookie. Logout xóa cookie **trên browser nhận response** nhưng một bản sao đã bị lấy cắp có thể được gửi lại tới khi token hết hạn, password hash/key thay đổi. Khi cần revocation chủ động, dùng persistent token hoặc một cơ chế session/token revocation khác và test thật.

### 11.6. Sau restart, remember cookie bị từ chối dù chưa đủ 14 ngày

Nếu app demo băm BCrypt lại tại startup, hash thay đổi; signature cookie token-based thường phụ thuộc password hash và key, nên cookie cũ bị từ chối. Trong ứng dụng thật, encoded password phải lưu bền vững trong database và signing key không tùy tiện thay đổi. Với persistent token, DB token repository cũng cần bền vững qua restart.

### 11.7. Session vừa được “nhớ lại” nhưng role là role cũ

Session có thể đã lưu authorities từ thời điểm login. Với remember-me, user details thường được đọc lại khi tự xác thực nên có cơ hội cập nhật, nhưng không thay thế chính sách revocation/authorization theo thời gian thực. Những hành động nhạy cảm nên kiểm tra lại trạng thái tài khoản/quyền nếu nghiệp vụ yêu cầu.

### 11.8. Coi “14 ngày remember-me” như “14 ngày session active”

Cookie validity độc lập với session inactivity interval. Khi remember-me tự xác thực, có thể tạo session **mới** với idle timeout thường. Điều này không làm token remember-me tự biến thành JSESSIONID và không bảo đảm hoạt động vô hạn nếu user không quay lại đúng lúc/cookie hết hạn.

### 11.9. Không thấy cookie trong MockMvc hoặc browser devtools

`Set-Cookie` là response header; `Cookie` là request header. Kiểm tra đúng request login success với checkbox, status redirect và response cookie. Một số cơ chế browser không hiển thị cookie HttpOnly qua JavaScript nhưng vẫn hiển thị trong devtools; không dựa vào `document.cookie` để khẳng định cookie không tồn tại.

### 11.10. Tắt CSRF để POST login/logout chạy

Trong app browser dùng session cookie, CSRF là một phần quan trọng của threat model. `permitAll()` chỉ bỏ authorization requirement tại URL, **không tắt CsrfFilter**. Form Thymeleaf POST cần CSRF token; logout nên thực hiện POST có token hợp lệ. Không tắt CSRF toàn cục chỉ để “test nhanh”.

## 12. Checklist thiết kế remember-me cho sản phẩm

1. **Phân biệt mục tiêu:** muốn idle session lâu hơn hay muốn auto-login **sau khi session mất**? Hai nhu cầu không tương đương.
2. **Chỉ phát token khi user đồng ý?** Kiểm tra checkbox, privacy policy và UX của thiết bị dùng chung.
3. **Định nghĩa lifetime:** session idle timeout và remember-me validity độc lập; có rolling window hay hard max lifetime không?
4. **Dùng HTTPS/cookies an toàn:** `Secure`, `HttpOnly`, `SameSite`, domain/path, HSTS, proxy TLS termination được kiểm tra.
5. **Token strategy:** token-based ký cookie hay persistent DB token? Cần revoke theo user/device, rotate và cảnh báo replay không?
6. **Signing key:** secret đủ mạnh, lưu ngoài source, nhất quán khi cluster, có chiến lược rotation và xử lý cookies cũ.
7. **Password hash ổn định:** nếu token-based phụ thuộc encoded password, đừng băm lại mỗi startup trong production.
8. **Endpoint nhạy cảm:** sử dụng `.fullyAuthenticated()` hoặc explicit step-up/MFA/recent-login policy thay vì `.authenticated()` ở mọi nơi.
9. **CSRF:** form login/logout có CSRF token, tránh cross-site state-changing requests; đừng dùng GET cho logout khi CSRF bật.
10. **Logout:** session invalidation + cookie clear + repository token revocation khi có DB; xác định phạm vi một thiết bị hay tất cả.
11. **Account disabled/password change:** kiểm tra behavior auto-login, session cũ, token cũ và cơ chế buộc xác thực lại.
12. **Kiểm thử:** không tick checkbox, tick checkbox, session hết hạn nhưng remember còn, token lỗi, logout, fullyAuthenticated, key/password rotation, concurrent use nếu persistent.
13. **Quan sát an toàn:** redaction token/headers và không log giá trị của `remember-me`/`JSESSIONID`.
14. **Cookie theft:** token cookie là bearer credential; cân nhắc phát hiện thiết bị bất thường, MFA và giảm cửa sổ sống.
15. **Session lifecycle:** session fixation protection, maximum sessions, session registry và session store nếu app yêu cầu; remember-me không tự cấu hình những thứ này thay bạn.

## 13. Bài tập tự luyện

**Bài 1 — Đổi thời hạn session:** Đặt `server.servlet.session.timeout=30s`, giữ tokenValiditySeconds 14 ngày. Dùng browser xóa riêng `JSESSIONID` và thử `/api/me` với remember cookie. Giải thích vì sao authentication vẫn có thể thành công.

**Bài 2 — Không tick checkbox:** Login bằng password không chọn remember-me. Xóa session rồi truy cập `/api/me`; phải chuyển về login. Thêm test dựa trên session không được gửi và remember cookie không có.

**Bài 3 — Policy fullyAuthenticated:** Chuyển `/api/strong` từ `.fullyAuthenticated()` sang `.authenticated()` và so sánh remember cookie có vào được không. Giải thích trade-off bảo mật và khi nào cần step-up authentication.

**Bài 4 — Đổi signing key:** Thay `REMEMBER_ME_KEY` ở một instance trong cluster dev. Quan sát token của node trước có thể không xác minh được ở node khác. Đề xuất key management thống nhất.

**Bài 5 — Persistent token:** Thêm `spring-boot-starter-jdbc`, H2 cho local, bảng `persistent_logins` và `JdbcTokenRepositoryImpl`. Viết test token rotation và logout revocation; giải thích race khi nhiều request đồng thời.

**Bài 6 — Đổi password:** Với token-based strategy, lưu hash ổn định rồi đổi password. Kiểm tra token cũ có bị từ chối không; so sánh với session cũ đã có authentication. Xác định policy cần chủ động invalidate session.

**Bài 7 — Phạm vi logout:** Giả sử user có ba thiết bị remembered. Phân biệt logout thiết bị A, thu hồi tất cả remember-me tokens và khóa account; nêu data model cần có nếu cần danh sách thiết bị.

**Bài 8 — Browser security:** Kiểm tra flags `Secure`, `HttpOnly`, `SameSite` ở HTTPS deployment. Giải thích vì sao cookie chưa hết hạn không bảo đảm server sẽ chấp nhận hoặc browser sẽ gửi nó.

## Kết luận

**Kéo dài thời gian sống `HttpSession` giữ lâu hơn một phiên đã đăng nhập. Remember-me lại lưu một credential riêng để có thể tự xác thực lại khi phiên đó đã mất.** Với Spring Security Servlet, remember-me có thể tạo `RememberMeAuthenticationToken` và được `.authenticated()` chấp nhận, nhưng `.fullyAuthenticated()` có thể yêu cầu đăng nhập tương tác lại cho tác vụ nhạy cảm. Token được ký trong cookie và persistent token có mô hình revocation/rotation khác nhau; cả hai cần HTTPS, giới hạn thời gian, cookie protection, logout và kiểm thử bảo mật có chủ đích.