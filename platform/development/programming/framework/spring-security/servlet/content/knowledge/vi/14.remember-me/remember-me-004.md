# PersistentTokenBasedRememberMeServices và PersistentTokenRepository

> **Ngữ cảnh:** Spring Security 6 trên **Servlet stack**, Java 17+, Spring Boot 3.x. Chủ đề thuộc **Ghi nhớ đăng nhập (Remember-me)**: cách `PersistentTokenBasedRememberMeServices` duy trì đăng nhập sau khi HTTP session không còn, contract `PersistentTokenRepository`, cấu trúc cặp `series/token`, xoay token, phát hiện token bị sử dụng sai, triển khai bằng `JdbcTokenRepositoryImpl` và các rủi ro vận hành. Đây là cơ chế nhớ đăng nhập của **trình duyệt**; không phải OAuth2 refresh token, API key hay thay thế session.

## 1. Nhớ đăng nhập giải quyết bài toán nào?

Ứng dụng web thường tạo một **HTTP session** sau khi người dùng đăng nhập bằng username/password. Trình duyệt mang session cookie (thường là `JSESSIONID`), server nạp `SecurityContext` từ phiên đó để không cần kiểm tra lại mật khẩu ở mỗi request. Khi phiên hết hạn, browser bị đóng, session bị hủy hoặc server mất state, thông thường người dùng phải đăng nhập lại.

**Remember-me** cho phép ứng dụng sử dụng **một cookie dài hạn riêng** để tự xác thực người dùng khi request mới không có `Authentication` hợp lệ trong `SecurityContext`. Người dùng có thể chọn ô “Ghi nhớ đăng nhập” ở form login. Khi session thông thường hết hạn, cookie remember-me hợp lệ có thể tạo authentication mới, sau đó ứng dụng có thể tiếp tục lưu authentication vào session theo cấu hình.

```text
Lần đăng nhập đầu tiên
   POST /login + username/password + remember-me=on
       |
       +--> Form login xác thực credentials
       +--> PersistentTokenBasedRememberMeServices tạo series/token ngẫu nhiên
       +--> PersistentTokenRepository lưu bản ghi server-side
       +--> Browser nhận cookie remember-me dài hạn
       +--> Ứng dụng cũng có thể tạo HTTP session bình thường

Request sau khi session không còn
   GET /me + cookie remember-me (không có JSESSIONID hợp lệ)
       |
       +--> RememberMeAuthenticationFilter nhận thấy chưa có Authentication
       +--> RememberMeServices đọc cookie
       +--> Repository tra series, đối chiếu token và thời hạn
       +--> Tạo token mới, cập nhật repository + cookie
       +--> Load UserDetails, tạo RememberMeAuthenticationToken
       +--> AuthorizationFilter áp dụng quyền theo policy
```

**Quan trọng:** Remember-me là một **đường xác thực có độ tin cậy thấp hơn đăng nhập nhập lại credentials**, vì người đang sở hữu cookie có thể không phải chủ tài khoản. Các thao tác nhạy cảm nên yêu cầu xác thực đầy đủ (`fullyAuthenticated()`), mật khẩu hiện tại hoặc re-authentication/MFA tùy chính sách.

## 2. Phân biệt session cookie, remember-me cookie và mật khẩu

| Khái niệm | Dữ liệu trình duyệt giữ | Server kiểm tra điều gì? | Vòng đời điển hình |
| --- | --- | --- | --- |
| **Session cookie** | Session ID ngắn, ví dụ `JSESSIONID` | Tìm phiên và `SecurityContext` đã lưu | Theo idle timeout, logout, session store và policy |
| **Persistent remember-me cookie** | Dữ liệu chứa **series/token** theo định dạng của Spring Security | Tra repository, đối chiếu token ngẫu nhiên và thời hạn; có thể xoay token | Có hạn dài hơn session; phụ thuộc tokenValiditySeconds và trạng thái DB |
| **Username/password** | Được người dùng nhập khi login; không nên giữ plaintext ở server | `AuthenticationManager`/provider so raw password với password hash | Căn cứ xác minh ban đầu hoặc xác thực lại |
| **OAuth2 refresh token** | Credential do authorization server phát hành | Token endpoint/authorization server theo chuẩn OAuth2 | Cơ chế khác; không dùng như remember-me token mặc định |

Một trình duyệt có thể đồng thời mang **hai cookie**: session cookie để truy cập nhanh trong phiên hiện tại, remember-me cookie làm phương án khôi phục khi thiếu session. Không suy ra “có cookie remember-me” nghĩa là mỗi request đều chạy auto-login: khi `SecurityContextHolder` đã có `Authentication` từ session, `RememberMeAuthenticationFilter` thường không cần dùng cookie remember-me.

Điều này rất quan trọng khi kiểm thử **rotation**: để chứng minh remember-me hoạt động, phải gửi **request độc lập không mang session hợp lệ**, chỉ mang remember-me cookie.

## 3. Hai lựa chọn remember-me của Spring Security

Spring Security có hai hướng triển khai cơ bản:

### 3.1. Token-based remember-me không cần bảng persistent token

`TokenBasedRememberMeServices` dùng dữ liệu trong cookie và cơ chế kiểm chứng phù hợp, không cần `PersistentTokenRepository` riêng. Nó có những đánh đổi liên quan đến khả năng thu hồi và vòng đời password/key; không nên giả định mọi token-based scheme của Spring Security đều có thể thu hồi riêng từng thiết bị dễ dàng.

### 3.2. Persistent token-based remember-me dùng repository server-side

`PersistentTokenBasedRememberMeServices` (chủ đề bài này) tạo một cặp **`series`** và **`token`** ngẫu nhiên:

- `series`: định danh chuỗi đăng nhập remember-me được lưu trong repository, dùng để tìm bản ghi.
- `token`: giá trị bí mật ngẫu nhiên của lần sử dụng hiện tại; được đối chiếu với giá trị mà server lưu.
- `username`: tài khoản mà series gắn vào.
- `lastUsed`: thời điểm ghi nhận token được tạo/cập nhật gần nhất, dùng cho logic hết hạn.

Mỗi lần một cookie remember-me được dùng thành công để auto-login, dịch vụ thường **giữ nguyên series nhưng tạo token mới**, cập nhật repository và gửi cookie mới. Một cookie cũ chứa token cũ sau khi token đã được xoay không còn hợp lệ.

**Ưu điểm:** có dữ liệu server-side phục vụ kiểm chứng, xoay token và thu hồi; dễ liên kết với quy trình bảo mật. **Đánh đổi:** cần cơ sở dữ liệu/replicated store hoạt động và bảo vệ đúng; request auto-login có thể phát sinh đọc/ghi DB; truy cập song song có thể tạo race condition.

## 4. PersistentTokenBasedRememberMeServices làm những gì?

Lớp `org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices` mở rộng `AbstractRememberMeServices`. Constructor chính dùng ba dependency:

```java
PersistentTokenBasedRememberMeServices services =
        new PersistentTokenBasedRememberMeServices(
                rememberMeKey,
                userDetailsService,
                persistentTokenRepository);

services.setTokenValiditySeconds(14 * 24 * 60 * 60);
services.setParameter("remember-me");
```

Đây là **fragment minh họa nằm trong cấu hình**, không phải class Java độc lập. `rememberMeKey` là chuỗi bí mật ổn định của ứng dụng, `userDetailsService` là nguồn người dùng và `persistentTokenRepository` là bộ lưu token. Nếu cấu hình bằng DSL `http.rememberMe(...)`, Spring Security có thể tự tạo và nối dịch vụ này khi cung cấp `tokenRepository`; không phải lúc nào cũng cần đăng ký bean thủ công.

### 4.1. Khi đăng nhập bằng form thành công

Sau khi form login xác thực username/password, remember-me service được gọi ở success path:

1. Kiểm tra người dùng **đã chọn remember-me** theo tên parameter được cấu hình, trừ khi chính sách `alwaysRemember(true)`.
2. Tạo `series` ngẫu nhiên và `token` ngẫu nhiên.
3. Tạo `PersistentRememberMeToken(username, series, token, date)`.
4. Gọi `PersistentTokenRepository.createNewToken(...)` để lưu bản ghi.
5. Gửi cookie remember-me cho trình duyệt với thời hạn phù hợp.
6. Hoàn tất luồng login; HTTP session bình thường có thể được tạo/lưu riêng.

Cookie persistent không phải mật khẩu được “mã hóa lại”; nó mang credential ngẫu nhiên dành riêng cho remember-me. Không có chuyện service lấy password plaintext từ database để nhét vào cookie.

### 4.2. Khi request mới chỉ còn cookie remember-me

`RememberMeAuthenticationFilter` kiểm tra trường hợp chưa có authentication trong context, gọi `RememberMeServices.autoLogin(...)` khi thích hợp. Với persistent cookie hợp lệ, dịch vụ:

1. Đọc và decode cookie theo định dạng riêng.
2. Yêu cầu đúng hai thành phần cần thiết: `series` và `token`.
3. Dùng `getTokenForSeries(series)` lấy bản ghi từ repository.
4. Nếu không có series, từ chối remember-me.
5. Nếu token trong cookie **không khớp** bản ghi cùng series, xử lý tình huống nghi ngờ token bị đánh cắp/đã bị dùng lại.
6. Nếu token vượt quá thời hạn được cho phép, từ chối.
7. Với token hợp lệ, **tạo token mới**, cập nhật bản ghi bằng `updateToken(...)` và cấp cookie mới.
8. Dùng `UserDetailsService.loadUserByUsername(...)` lấy user hiện tại, rồi cơ chế remember-me tạo `RememberMeAuthenticationToken` phù hợp cho filter.

`RememberMeAuthenticationToken` là kết quả authentication riêng. Nó có thể được xem là authenticated theo contract Spring Security nhưng **không tương đương với đăng nhập đầy đủ** khi hệ thống dùng biểu thức `fullyAuthenticated()`.

### 4.3. Khi logout

`RememberMeServices` cũng tham gia xử lý logout để xóa cookie remember-me và có thể xóa các token server-side của user. `PersistentTokenRepository.removeUserTokens(username)` là thao tác xóa token theo **username**, không phải theo series cụ thể; với `JdbcTokenRepositoryImpl`, thao tác này có thể thu hồi **mọi record remember-me thuộc user**.

Điều này có hệ quả UX: logout trên một thiết bị có thể khiến remember-me ở thiết bị khác không tiếp tục được, tùy flow thực tế và cách repository được cấu hình. Nếu yêu cầu “logout đúng một thiết bị”, cần thiết kế token store/revocation riêng hoặc mở rộng có kiểm soát, không mặc nhiên dựa vào `removeUserTokens(username)`.

## 5. PersistentTokenRepository: contract lưu trữ

Interface `org.springframework.security.web.authentication.rememberme.PersistentTokenRepository` cho phép remember-me service độc lập với loại database.

Các phương thức quan trọng:

```java
public interface PersistentTokenRepository {
    void createNewToken(PersistentRememberMeToken token);

    void updateToken(String series, String tokenValue, Date lastUsed);

    PersistentRememberMeToken getTokenForSeries(String seriesId);

    void removeUserTokens(String username);
}
```

Đây là **chữ ký interface rút gọn để học**, cần import `java.util.Date` và `PersistentRememberMeToken` từ Spring Security nếu tự khai báo, nhưng trong ứng dụng thực hãy sử dụng interface có sẵn.

| Phương thức | Khi nào được gọi | Đặc điểm cần bảo đảm |
| --- | --- | --- |
| `createNewToken` | Sau login thành công và bật remember-me | Lưu username, series, token, lastUsed; series phải unique |
| `getTokenForSeries` | Khi cookie đến và cần auto-login | Tra đúng series hoặc trả null; không “đoán” user từ cookie |
| `updateToken` | Khi auto-login thành công và xoay token | Cập nhật token value và thời gian đồng nhất; hỗ trợ kiểm soát race |
| `removeUserTokens` | Khi logout, nghi ngờ cookie theft hoặc policy thu hồi | Xóa/thu hồi các series thuộc user theo contract |

### 5.1. PersistentRememberMeToken chứa gì?

`PersistentRememberMeToken` là một data object chứa:

```text
username:  "learner"
series:    <random-series>
token:     <random-token-value>
date:      <last-used-timestamp>
```

Các chuỗi random là ví dụ dạng dữ liệu, **không phải token hợp lệ**. Mã Java có getter như `getUsername()`, `getSeries()`, `getTokenValue()` và `getDate()`.

Không cần lưu password hash hoặc mật khẩu gốc trong bảng remember-me. Password hash vẫn nằm trong user store dành cho `DaoAuthenticationProvider`; remember-me credentials được quản lý riêng.

### 5.2. Implement repository tùy chỉnh

Nếu dùng Redis/JPA hoặc remote store, triển khai interface đúng contract. Các yêu cầu thiết kế:

- `series` unique và lookup nhanh, không bị đoán dễ.
- Ghi token **atomic** để tránh hai request cùng series ghi đè lẫn nhau.
- Mọi node ứng dụng chia sẻ cùng store hoặc một store có tính nhất quán phù hợp.
- Clock/timezone và `lastUsed` thống nhất; thường lưu timestamp UTC.
- Xóa token trên logout/revocation, không cache token stale quá lâu.
- Bảo vệ dữ liệu DB, backup và log: giá trị series/token là **credential nhạy cảm**.
- Nếu áp dụng optimistic locking/cas hoặc hash-at-rest cho token, phải xem xét tương thích với dịch vụ chuẩn và kiểm thử failure/concurrency.

**Không** viết repository lưu token vào `HashMap` cục bộ cho môi trường có nhiều node rồi gọi đó là “persistent” vì token sẽ mất khi process restart hoặc request sang node khác.

## 6. JDBC implementation và bảng persistent_logins

`JdbcTokenRepositoryImpl` là implement có sẵn của `PersistentTokenRepository`. Nó sử dụng `DataSource` để tạo, đọc, cập nhật và xóa các persistent tokens.

Schema mặc định tương đương:

```sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

| Cột | Vai trò |
| --- | --- |
| `username` | Danh tính user được remember |
| `series` | Khóa chính định danh chuỗi remember-me |
| `token` | Giá trị bí mật hiện tại để so với cookie |
| `last_used` | Thời điểm cập nhật token, làm căn cứ expiry |

Đây là bảng của **remember-me**, không phải bảng Spring Session và cũng không phải bảng `users`. Mỗi user có thể có nhiều bản ghi `series` (nhiều trình duyệt/thiết bị); PK đặt trên series chứ không đặt trên username.

### 6.1. Về việc tạo bảng

`JdbcTokenRepositoryImpl` có `setCreateTableOnStartup(true)` để tạo table khi khởi động trong một số kịch bản demo. **Không bật bừa trong production:** khởi động lại có thể gặp lỗi table đã tồn tại và schema migration phải do Flyway/Liquibase hoặc quy trình triển khai DB đảm trách.

Trong dự án demo phía dưới dùng tệp `schema.sql` với `CREATE TABLE IF NOT EXISTS` của H2. Với database production, hãy dùng migration phù hợp dialect thực tế; `IF NOT EXISTS` không có cú pháp giống hệt ở mọi engine.

### 6.2. Khi nào phải dọn dữ liệu cũ?

Token hết hạn theo service không mặc định đồng nghĩa mọi row database được xóa tức thì. Tùy repository/flow, expired rows có thể tồn tại cho tới khi có cleanup hoặc thao tác revoke. Đối với DB lớn, xây lịch cleanup an toàn theo policy thời hạn và thời điểm cuối dùng; kiểm tra clock/timezone, indices và tác động với các phiên đang dùng.

Không xóa dựa trên “ngày tạo account” khi cơ chế expiry dựa vào `lastUsed` và tokenValiditySeconds. Nếu có quy tắc bảo vệ riêng như absolute maximum age, phải thiết kế thêm trường/dữ liệu phù hợp.

## 7. Cookie series/token: phân tích security

Định dạng logic của persistent remember-me cookie gắn hai giá trị:

```text
series:token
    |
    v
Base64(...) -> cookie remember-me
```

Đây chỉ là **biểu diễn khái niệm**; implementation có thể escape/encode theo API nội bộ. Base64 không mã hóa bí mật. Cookie remember-me hoạt động như **bearer credential**: nếu bị đánh cắp, người khác có thể thử dùng cookie đó để auto-login.

### 7.1. Vì sao phải có cả series và token?

- `series` giúp tra bản ghi ổn định theo một dòng remember-me.
- `token` được **xoay vòng sau khi auto-login thành công**, làm một cookie cũ hết hiệu lực khi token đã cập nhật.
- Khi server tìm được series nhưng token khác giá trị lưu, đó có thể là dấu hiệu credential bị lấy cắp hoặc đã có người dùng token trước.
- Tùy logic service, sự kiện đáng ngờ có thể thu hồi các persistent tokens của username đó.

So với một cookie tĩnh dài hạn, rotation có thể giúp phát hiện sử dụng lại token đã cũ. Tuy nhiên, **không phải bằng chứng chắc chắn bị đánh cắp**: hai request song song từ cùng trình duyệt cũng có thể dùng cùng cookie cũ trong lúc token đang xoay.

### 7.2. Vấn đề concurrent request khi session hết hạn

Giả sử trình duyệt mở cùng lúc hai request với cookie `series=S, token=T0`:

```text
Request A: gửi S,T0       Request B: gửi S,T0
       |                         |
       v                         v
  tra DB thấy T0             tra DB thấy T0 hoặc T1
       |
  cập nhật DB thành T1
       |
  trả cookie S,T1
                                 |
                          nếu B đọc sau khi A update:
                          DB đã là T1, B gửi T0
                          -> token mismatch, nghi ngờ theft
                          -> có thể revoke tokens
```

Kết quả phụ thuộc interleaving, DB và client nhận cookie theo thứ tự nào. Với cơ chế persistent remember-me chuẩn, một request dùng lại token cũ khi series đã cập nhật có thể kích hoạt `CookieTheftException` và `removeUserTokens(username)`.

**Không nên sửa bằng cách bỏ token rotation hoặc tắt kiểm tra token mismatch** chỉ vì người dùng bị logout khi nhiều tab request song song. Biện pháp phù hợp hơn là giảm tình huống nhiều request cần nhớ đăng nhập đồng thời (ví dụ quản lý session sau lần auto-login đầu), đo lỗi race, kiểm thử thực tế và nếu cần thiết kế repository/flow phù hợp hơn theo đánh giá bảo mật.

### 7.3. Hạn dùng: cookie và lastUsed

`setTokenValiditySeconds(...)` quy định thời gian remember-me được chấp nhận theo cơ chế của service. Khi auto-login thành công, token và `lastUsed` thường được cập nhật, cookie mới được phát; vì vậy cần hiểu **cơ chế thời hạn trượt** của token này, không mặc định đây là một absolute lifetime cố định tính từ lần login đầu.

Bộ lưu token phải còn record hợp lệ; một cookie còn thời hạn ở browser **không có nghĩa** server sẽ chấp nhận nếu record đã bị xóa, token sai hoặc user không còn hợp lệ. Ngược lại, bản ghi DB tồn tại nhưng cookie hết hạn/không được gửi cũng không tạo được auto-login.

Nếu sản phẩm yêu cầu **maximum lifetime tuyệt đối** hoặc bắt buộc re-auth sau thời gian cố định, cần thiết kế kiểm soát riêng thay vì chỉ dựa vào việc cập nhật `lastUsed`.

### 7.4. Key bảo vệ dịch vụ không thay việc giữ bí mật token

Constructor nhận `key` dùng trong hệ sinh thái remember-me authentication và kiểm tra tin cậy nội bộ của token. **Không** hiểu nó là khóa AES để “decrypt” persistent cookie, cũng không dùng key như phương pháp thay thế cho DB token secrecy. Key phải ổn định giữa các node/restart trong cùng ứng dụng và được bảo vệ bằng secret management. Thay đổi key có thể làm remember-me authentication trước đó không còn hợp lệ tùy cấu hình.

### 7.5. Cookie attributes

Sử dụng HTTPS, `Secure`, `HttpOnly`, `SameSite` phù hợp với giao thức và client; đặt domain/path ở phạm vi cần thiết. Không truyền remember-me token trong URL, không log Cookie header, không dùng LocalStorage tùy tiện để sao chép credential. SameSite giảm một số nguy cơ CSRF nhưng không thay CSRF token với những ứng dụng cookie-based cần bảo vệ request thay đổi trạng thái.

## 8. Dự án Spring Boot chạy được: remember-me với JDBC

Demo dùng **Java 17+**, **Spring Boot 3.3.5 / Spring Security 6.x**, **Gradle 8.5**. Ta dùng H2 file database cho môi trường local để persistent token records còn sau khi restart process; tài khoản học tập được tạo trong memory. Đây **không phải cấu hình production**: không dùng H2 file hoặc demo secret để quản lý người dùng thật.

### 8.1. Chức năng demo

- `GET /` công khai.
- `GET /me` cần `authenticated()`; trả tên user và loại Authentication.
- `GET /settings` yêu cầu `fullyAuthenticated()`, từ chối/redirect để đăng nhập lại khi chỉ có remember-me.
- `POST /login` do `formLogin()` xử lý, có CSRF, username/password và tùy chọn `remember-me=on`.
- `JdbcTokenRepositoryImpl` lưu cặp series/token trong bảng `persistent_logins`.

### 8.2. Cấu trúc tệp

```text
jdbc-remember-me-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/main/resources/
    application.properties
    schema.sql
  src/test/java/demo/
    PersistentRememberMeTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'jdbc-remember-me-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot quản lý phiên bản Spring Security, JDBC và H2 phù hợp trong BOM của `3.3.5`. Không cần thêm `spring-data-jpa` nếu chỉ dùng `JdbcTokenRepositoryImpl`.

### 8.3. Cấu hình datasource và secret cho local

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:file:./rememberme-db;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

app.security.remember-me-key=demo-local-key-change-before-production
```

`H2 file` tạo dữ liệu trên đĩa của máy chạy demo, khác `jdbc:h2:mem:...` vốn không tồn tại qua restart process. Khi ứng dụng chạy trong container với filesystem tạm, dữ liệu vẫn có thể mất khi container được thay thế.

**Cảnh báo:** key trong properties chỉ dùng cho **local demo**, không đủ để dùng ở production. Với môi trường thực, inject bí mật đủ mạnh và ổn định qua biến môi trường/secret manager (ví dụ biến `APP_SECURITY_REMEMBER_ME_KEY` theo cơ chế cấu hình của Spring Boot); không commit secret production, không đổi key tùy tiện qua mỗi lần deploy.

`src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
```

Schema này dùng cú pháp `IF NOT EXISTS` của H2 để ứng dụng demo có thể khởi động lại khi file DB đã tồn tại. Với MySQL/PostgreSQL hay hệ thống production, dùng DDL/migration tương ứng, quyền DB tối thiểu và chính sách bảo vệ backup.

### 8.4. Lớp khởi động

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 8.5. SecurityConfig: dùng PersistentTokenRepository từ JDBC

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails user = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        return repository;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            PersistentTokenRepository tokens,
            Environment environment) throws Exception {

        String rememberMeKey = environment.getRequiredProperty(
                "app.security.remember-me-key");

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/").permitAll()
                .requestMatchers("/settings").fullyAuthenticated()
                .anyRequest().authenticated());

        http.formLogin(form -> form
                .defaultSuccessUrl("/me", true)
                .permitAll());

        http.rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(users)
                .tokenRepository(tokens)
                .rememberMeParameter("remember-me")
                .rememberMeCookieName("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60));

        http.logout(logout -> logout.logoutSuccessUrl("/"));

        return http.build();
    }
}
```

**Đọc từng phần:**

1. `UserDetailsService` là nơi dịch vụ remember-me tìm lại user từ username đã lưu trong token record. Nếu user đã bị xóa, disabled hoặc có policy thay đổi, luồng authentication có thể thất bại/từ chối theo cơ chế liên quan; hãy kiểm thử policy trạng thái user cụ thể.
2. `PersistentTokenRepository` là contract; `JdbcTokenRepositoryImpl` sử dụng cùng `DataSource` với bảng `persistent_logins`. Bean không gọi `setCreateTableOnStartup(true)`, vì `schema.sql` đã quản lý tạo bảng cho demo.
3. `http.rememberMe(...tokenRepository(tokens))` yêu cầu nhánh **persistent token based**. Spring Security tích hợp remember-me với form-login, auto-login filter và provider thích hợp.
4. `rememberMeParameter("remember-me")` buộc client gửi parameter chọn nhớ đăng nhập; khi không có/không bật opt-in, một form login bình thường không nhất thiết tạo persistent remember-me cookie.
5. `rememberMeCookieName("remember-me")` đặt tên cookie để dễ theo dõi trong test.
6. `tokenValiditySeconds(14 * 24 * 60 * 60)` dùng hạn 14 ngày cho demo; đây không phải gợi ý thời hạn tối ưu cho mọi sản phẩm.
7. `fullyAuthenticated()` phân biệt remember-me với đăng nhập bằng credentials đầy đủ trên `/settings`.
8. Không gọi `csrf.disable()`. Form login và logout có cookie cần CSRF protection; test dùng token CSRF hợp lệ.

**Không tự triển khai `AuthenticationProvider` đặc biệt để xác thực persistent cookie** trong ví dụ này. DSL remember-me tạo/nối các thành phần cần thiết; nếu tự custom `RememberMeServices`, phải hiểu cách bộ lọc và provider được gắn vào chain.

### 8.6. Controller hiển thị loại Authentication

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName() + ":"
                + authentication.getClass().getSimpleName();
    }

    @GetMapping("/settings")
    public String settings(Authentication authentication) {
        return "settings-for-" + authentication.getName();
    }
}
```

Một session sau form login đầy đủ thường có `UsernamePasswordAuthenticationToken`, còn request được auto-login bằng remember-me có `RememberMeAuthenticationToken`. Vì vậy `/me` minh họa sự khác biệt giữa hai con đường xác thực. `/settings` yêu cầu `fullyAuthenticated()` để không cho cookie remember-me đơn độc thay thế bước nhập lại password.

Không dùng tên class của authentication làm quy tắc phân quyền production; thay bằng authorization DSL, `AuthenticationTrustResolver` hoặc chính sách re-authentication đã được Spring Security hỗ trợ.

### 8.7. Kiểm thử MockMvc: opt-in, cookie-only, rotation, full authentication

`src/test/java/demo/PersistentRememberMeTest.java`:

```java
package demo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:rememberme-test;DB_CLOSE_DELAY=-1"
})
@AutoConfigureMockMvc
class PersistentRememberMeTest {

    @Autowired
    MockMvc mvc;

    private Cookie loginAndGetRememberMeCookie() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123")
                        .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie cookie = login.getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        return cookie;
    }

    @Test
    void anonymousRequestNeedsLogin() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginWithoutRememberMeDoesNotCreatePersistentCookie()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "learner")
                        .param("password", "study123"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        assertNull(login.getResponse().getCookie("remember-me"));
    }

    @Test
    void rememberMeCookieReauthenticatesWithoutSession()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        // Request mới KHÔNG dùng session của form login.
        mvc.perform(get("/me").cookie(cookie))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        "learner:RememberMeAuthenticationToken"));
    }

    @Test
    void successfulAutoLoginRotatesPersistentToken()
            throws Exception {
        Cookie original = loginAndGetRememberMeCookie();

        MvcResult restored = mvc.perform(get("/me")
                        .cookie(original))
                .andExpect(status().isOk())
                .andReturn();

        Cookie rotated = restored.getResponse().getCookie("remember-me");
        assertNotNull(rotated);
        assertNotEquals(original.getValue(), rotated.getValue());
    }

    @Test
    void rememberMeDoesNotSatisfyFullyAuthenticated()
            throws Exception {
        Cookie cookie = loginAndGetRememberMeCookie();

        mvc.perform(get("/settings").cookie(cookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void loginRequiresCsrfToken() throws Exception {
        mvc.perform(post("/login")
                        .param("username", "learner")
                        .param("password", "study123")
                        .param("remember-me", "on"))
                .andExpect(status().isForbidden());
    }
}
```

**Kết quả kỳ vọng:** 6 test PASS với project và dependency đã nêu. Chúng chứng minh:

- Chưa login, `/me` yêu cầu authentication.
- Không chọn checkbox thì form-login thành công không cấp persistent remember-me cookie.
- Lấy cookie remember-me từ response login, **không dùng session của login request**, request mới vẫn nhận `RememberMeAuthenticationToken`.
- Auto-login thành công cấp cookie mới vì token đã được xoay.
- Một remember-me authentication không đủ điều kiện `fullyAuthenticated()` ở `/settings`.
- Form login không có CSRF token bị từ chối.

**Điểm cần tránh:** không dùng `@WithMockUser` để test persistent remember-me, vì annotation đặt sẵn authentication vào test context và làm `RememberMeAuthenticationFilter` không cần chạy. Không tự copy `MockHttpSession` từ login request sang test auto-login; như vậy sẽ vô tình kiểm tra session thay vì cookie remember-me.

Trong một số container/browser hoặc tích hợp khác, cookie attributes, redirect và session handling có thể khác MockMvc. Cần kiểm thử E2E với HTTPS, reverse proxy và browser thật trước khi triển khai production.

### 8.8. Chạy ứng dụng

Tại thư mục `jdbc-remember-me-demo`:

```bash
gradle test
gradle bootRun
```

Nếu project dùng Gradle Wrapper, có thể gọi `./gradlew test` và `./gradlew bootRun` (macOS/Linux) hoặc `.\gradlew.bat test` và `.\gradlew.bat bootRun` (Windows PowerShell).

Thử trên browser ở `http://localhost:8080`:

1. Mở `/me` khi chưa login: dự kiến chuyển đến trang login.
2. Trên trang login, nhập `learner` / `study123` và bật tùy chọn **Remember me** (hoặc dùng form gửi parameter `remember-me=on`).
3. Quan sát response login có cookie `remember-me`. Cookie thực tế là dữ liệu runtime, không cần và không nên chép vào log.
4. Xóa **chỉ cookie session** của browser hoặc dùng test không mang session; giữ cookie `remember-me`.
5. Gọi `/me`: dự kiến danh tính được khôi phục thành `learner:RememberMeAuthenticationToken`.
6. Gọi `/settings` chỉ với cookie remember-me: phải yêu cầu đăng nhập đầy đủ theo policy `fullyAuthenticated()`.
7. Kiểm tra bảng `persistent_logins` trên DB local: sau remember-me login có row với username/series/token/last_used; sau auto-login thành công token và last_used có thể thay đổi. **Không công khai giá trị series/token.**

Nếu dùng `curl`, phải xử lý cookie jar **và CSRF token của trang login**, không gửi POST login thẳng mà bỏ CSRF. Vì trang form-login mặc định sinh token theo request/session, thử bằng browser thường dễ quan sát hơn. HTTP localhost chỉ dành cho demo; dùng HTTPS ở môi trường thực.

## 9. Điều gì xảy ra nếu logout, đổi password hoặc khóa tài khoản?

### 9.1. Logout

Khi logout đúng cơ chế Spring Security, remember-me logout handler có thể hủy cookie và gọi repository xóa token thuộc username. Với repository JDBC mặc định, `removeUserTokens(username)` có phạm vi tất cả remembered series của user đó.

Ứng dụng có yêu cầu **logout trên một thiết bị**, “logout tất cả thiết bị”, “xóa thiết bị đã ghi nhớ” hay “thu hồi các phiên đang hoạt động” cần phân biệt: nhớ đăng nhập và HTTP session là **hai nguồn state khác nhau**. Xóa persistent tokens không tự bảo đảm vô hiệu hóa mọi session vẫn đang tồn tại; và invalidate một session không nhất thiết xóa mọi remember-me token nếu không thực hiện logout/revocation đúng flow.

### 9.2. Đổi mật khẩu

Persistent token không phải password hash. Vì vậy việc thay password trong `UserDetailsService`/database **không tự động chứng minh** các persistent tokens đã lưu bị xóa. Nếu chính sách muốn bắt tất cả thiết bị đăng nhập lại sau đổi password, phải chủ động `removeUserTokens(username)` và cân nhắc session invalidation/revocation.

Đừng nói “token cookie vẫn hợp lệ vì mật khẩu đúng” — remember-me phục hồi user từ repository/cookie, không lặp bước so password trên mỗi auto-login.

### 9.3. Khóa hoặc vô hiệu hóa account

Khi auto-login, dịch vụ có thể load `UserDetails` hiện tại. Tuy nhiên, hệ thống cần kiểm tra cẩn thận account status và authorization policy: nếu user đã disabled, locked hoặc hết quyền, phải có cơ chế **fail closed** và thu hồi token/session phù hợp. Không dựa duy nhất vào sự tồn tại của row `persistent_logins` để cấp quyền vĩnh viễn.

### 9.4. Secret hoặc database bị mất

Nếu file H2 của demo bị xóa, repository mất các series/token đã lưu; cookie còn trên browser sẽ không tìm thấy series và auto-login thất bại. Nếu ứng dụng nhiều node dùng database riêng không đồng bộ, một cookie có thể chạy ở node A và bị từ chối ở node B. Production nên dùng shared store/cluster phù hợp.

Nếu remember-me key bị rotate mà các node dùng key khác nhau, authentication token provider có thể không chấp nhận kết quả nhất quán. Quản lý key theo môi trường, ổn định khi deploy, có kế hoạch rotation với tác động lên các cookie đã phát hành.

## 10. Khả năng mở rộng và rủi ro triển khai production

### 10.1. Database availability

Mỗi lần thực sự cần persistent auto-login sẽ phải tra và thường cập nhật token server-side. Khi database down, không thể tin cookie một cách độc lập. Cần timeout, connection pool, retry policy có giới hạn và phản hồi an toàn; **không** cho auto-login thành công chỉ vì không kết nối được DB.

### 10.2. Atomicity và race conditions

Repository JDBC tiêu chuẩn cung cấp các thao tác CRUD theo contract. Với độ trễ mạng, nhiều tab và các request đồng thời, vòng đọc–kiểm tra–cập nhật có thể gặp race. Cần kiểm thử những đường này. Nếu xây repository riêng, cân nhắc optimistic concurrency/compare-and-set và cách tránh vô tình nhận replay; không tự thay đổi behavior nhận token cũ mà chưa phân tích an ninh.

### 10.3. Token lưu trong DB vẫn là credential

Với persistent remember-me cổ điển, giá trị token có thể được lưu ở dạng phục vụ so khớp trực tiếp. Nếu DB bị đọc trái phép, dữ liệu này phải được coi là nhạy cảm: kết hợp series/token có thể hỗ trợ giả mạo cookie còn hiệu lực. Bảo vệ DB, backup, quyền truy cập và log; nếu cần hash-at-rest, phải thiết kế repository custom, kiểm tra nguyên tắc so khớp và tương thích dịch vụ chuẩn.

Không dùng `PasswordEncoder` để băm một chiều random token rồi mong `JdbcTokenRepositoryImpl` mặc định tự hiểu hash đã biến đổi; service mặc định so token theo định dạng nó biết. Khi thay đổi storage semantics, cần implement repository và luồng verification tương ứng.

### 10.4. Cookie security và CSRF

Persistent remember-me cookie là bearer credential dài hạn. Dùng HTTPS, cấu hình `Secure`, `HttpOnly`, `SameSite`, domain/path chặt chẽ, HSTS khi phù hợp, và không đưa cookie vào URL. Với browser tự gửi cookie, CSRF protection vẫn quan trọng khi thực hiện POST/PUT/DELETE. Không tắt CSRF toàn bộ chỉ vì đã bật remember-me.

### 10.5. Cookie theft và người dùng hợp pháp bị logout

`CookieTheftException` có thể xảy ra khi token cookie không khớp token DB dù series tồn tại. Nó là **dấu hiệu cần điều tra**, không phải xác nhận pháp lý rằng có kẻ tấn công. Request song song sau khi session mất cũng có thể gây tình huống token bị xoay trước khi request khác được xử lý.

Log/metric nên ghi **mã sự kiện**, correlation ID, username theo chính sách dữ liệu, số lượng lần fail; **không** ghi raw cookie, series/token hoặc các secret. Khi có dấu hiệu tấn công thật, áp dụng revocation và cảnh báo theo chính sách.

### 10.6. Device management và token series

Một user có thể có nhiều series ở các browser/thiết bị. `PersistentTokenRepository.removeUserTokens(username)` xóa theo user, không theo một series. Nếu sản phẩm cho người dùng xem và revoke **từng thiết bị**, hãy thiết kế thêm data model/metadata và API revoke theo series có kiểm soát; không hiển thị token bí mật trên UI quản lý thiết bị.

### 10.7. Lựa chọn thời hạn hợp lý

14 ngày trong demo chỉ là giá trị học tập. Hệ thống ngân hàng/health/admin console có thể không nên dùng remember-me hoặc cần giới hạn phiên mạnh, MFA/re-auth. Với ứng dụng ít nhạy cảm hơn có thể cân nhắc trải nghiệm người dùng nhưng cần transparency, opt-in và logout. Timeouts cho HTTP session, remember-me token và access token của hệ thống khác cần được quản lý riêng.

## 11. Troubleshooting: nhớ đăng nhập không hoạt động

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Login đúng nhưng không có cookie remember-me | Không chọn checkbox, tham số sai tên, flow không gọi rememberMe success | Kiểm tra `rememberMeParameter` và response sau login hợp lệ |
| Có cookie nhưng request mới vẫn chuyển login | Cookie không được gửi, sai path/domain/Secure, session test không đúng, DB thiếu series | Kiểm tra cookie trong Network, token store và range URL |
| Sau server restart cookie mất hiệu lực | In-memory DB, key đổi, token không bền, cookie/session config | Dùng DB bền, key ổn định, kiểm tra schema |
| Trả lỗi vì bảng `persistent_logins` không tồn tại | Chưa chạy migration/schema | Kiểm tra DDL, datasource, quyền database |
| Lỗi table đã tồn tại lúc startup | Dùng `setCreateTableOnStartup(true)` khi table đã có | Dùng migration idempotent phù hợp thay vì bật mãi |
| Tự auto-login được một lần rồi mất remember-me | Token rotation, cookie mới không được lưu, request song song với token cũ | Kiểm tra `Set-Cookie` sau auto-login, replay/concurrency |
| Có `CookieTheftException` | Series có nhưng token sai/stale, có thể do replay hoặc race | Không log token; điều tra song song, DB write và security events |
| `fullyAuthenticated()` không cho vào trang nhạy cảm | Remember-me auth được coi là chưa full authentication | Behavior đúng; yêu cầu nhập lại credentials |
| Đã logout nhưng còn session/thiết bị khác | Session và token là hai state riêng; phạm vi revoke khác nhau | Kiểm tra logout handler, `removeUserTokens` và session invalidation |
| Đổi mật khẩu mà browser khác vẫn được nhớ | Chưa revoke persistent tokens và sessions | Thu hồi tokens theo user và policy |
| Nhiều node: lúc được lúc không | Token DB/key không đồng nhất giữa các node | Dùng shared store, key nhất quán và clock/timezone chuẩn |

### Cách debug không lộ bí mật

Có thể bật DEBUG cho Spring Security trong môi trường thử nghiệm:

```properties
logging.level.org.springframework.security=DEBUG
```

Không bật logging toàn bộ Cookie/Authorization headers ở production. Các dòng về SecurityFilterChain chỉ xác nhận filter chạy; chúng không chứng minh `getTokenForSeries` đã tìm bản ghi, token được xoay hay client nhận cookie mới. Hãy đo ranh giới repository/remember-me service có kiểm soát và kiểm thử HTTP request không có session.

## 12. Checklist kiểm thử trước khi triển khai

1. **Opt-in:** login có `remember-me=on` cấp cookie; login không chọn không cấp.
2. **Cookie-only:** tách session, gửi request mới chỉ có remember-me cookie, xác nhận được `RememberMeAuthenticationToken`.
3. **Rotation:** sau auto-login, cookie mới khác cookie cũ; DB token/`last_used` được cập nhật.
4. **Replay detection:** cookie có series tồn tại nhưng token sai dẫn đến từ chối và revocation theo contract; test riêng có kiểm soát.
5. **Expiry:** cookie hết hạn, record hết hạn hoặc bị xóa không cho auto-login; đừng chỉ tin browser Max-Age.
6. **Password/account changes:** khóa/disable account hoặc thay password có dẫn đến yêu cầu re-auth/revoke theo policy không?
7. **Authorization:** endpoint `authenticated()` và `fullyAuthenticated()` có hành vi khác nhau với remember-me.
8. **Logout:** xóa remember-me cookie và repository token theo phạm vi mong muốn, không nhầm với session invalidation.
9. **Multi-device:** các series độc lập và behavior khi revoke theo username được thống nhất UX.
10. **Concurrency:** nhiều request song song sau session expiry không làm app mất ổn định; có quan sát tình huống false theft alert.
11. **Persistence:** restart process/nhiều node vẫn đọc repository chung đúng; key và datasource đồng nhất.
12. **Cookie/CSRF:** HTTPS, cookie flags, domain/path, CSRF, logout và các POST nhạy cảm được kiểm thử.
13. **Secret/DB:** không hard-code key thật, không log token, backup được bảo vệ, schema migration an toàn.
14. **Monitoring:** metric cho create/rotate/revoke/fail, không đưa credential vào telemetry.

## 13. Câu hỏi tự kiểm tra

1. **Persistent remember-me khác HTTP session ở đâu?** Session cookie trỏ tới `HttpSession` thông thường, còn persistent remember-me cookie mang series/token có repository riêng và dùng để khôi phục authentication khi chưa có context.
2. **`PersistentTokenRepository` có phải user database không?** Không. Nó lưu username/series/token/lastUsed phục vụ remember-me; tài khoản và password hash do user store đảm trách.
3. **Vì sao cần cả series và token?** Series xác định record, token ngẫu nhiên giúp kiểm tra possession và xoay giá trị sau auto-login.
4. **Khi auto-login thành công, series có đổi không?** Thông thường series giữ nguyên, token và `lastUsed` được cập nhật, cookie mới được phát.
5. **Một cookie có thể hoạt động sau khi DB xóa record không?** Không theo cơ chế chuẩn; không tìm thấy series hợp lệ thì auto-login bị từ chối.
6. **`CookieTheftException` có luôn chứng minh attacker không?** Không. Nó có thể xuất hiện vì token cũ được dùng lại hoặc race giữa request đồng thời.
7. **Vì sao `fullyAuthenticated()` có thể từ chối remember-me?** Remember-me là dạng authentication kém đảm bảo hơn việc người dùng vừa xác thực đầy đủ, nên endpoint nhạy cảm có thể yêu cầu login lại.
8. **`removeUserTokens(username)` thường thu hồi một thiết bị hay tất cả?** Contract xóa theo username; với repository JDBC mặc định, nó ảnh hưởng mọi series của user.
9. **Đổi password có tự xóa persistent tokens không?** Không được giả định. Ứng dụng cần policy revoke tokens/sessions riêng.
10. **Tại sao không lưu remember-me token trong log?** Nó là bearer credential có thể giúp mạo danh người dùng.
11. **Dùng H2 in-memory để demo “persistent qua restart” có đúng không?** Không; H2 in-memory thường mất sau restart process. Demo dùng H2 file để minh họa persistence local.
12. **TokenValiditySeconds có phải absolute lifetime kể từ lần login đầu?** Không nên coi vậy: persistent service có thể cập nhật token/lastUsed khi auto-login, tạo hiệu ứng sliding expiration.
13. **Có thể tự thay nhớ đăng nhập bằng JWT dài hạn không?** Không nên coi đó là tương đương; JWT/token lifecycle, rotation, revocation và threat model khác, cần thiết kế riêng.

**Ghi nhớ:** `PersistentTokenBasedRememberMeServices` kết hợp một **cookie dài hạn chứa series/token** với `PersistentTokenRepository` server-side. Sau login opt-in, dịch vụ tạo bản ghi; khi session không còn, `RememberMeAuthenticationFilter` có thể dùng cookie để khôi phục `RememberMeAuthenticationToken`, đồng thời **xoay token** và cập nhật repository. `JdbcTokenRepositoryImpl` là lựa chọn JDBC có sẵn với bảng `persistent_logins`. Đây là một dạng bearer credential dài hạn, cần HTTPS, cookie security, dữ liệu DB được bảo vệ, revocation và kiểm thử replay/concurrency. Với thao tác nhạy cảm, hãy dùng `fullyAuthenticated()` hoặc re-authentication thay vì coi remember-me là tương đương đăng nhập bằng password.
