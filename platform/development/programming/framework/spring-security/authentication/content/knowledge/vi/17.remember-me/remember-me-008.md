# Kiểm thử cookie hết hạn, bị sửa, bị đánh cắp hoặc bị phát lại

## 1. Mục tiêu và phạm vi bảo mật

Remember-me (*ghi nhớ đăng nhập*) cho phép browser chứng minh lại danh tính bằng một cookie dài hạn sau khi HTTP session trước đó không còn. Trong Spring Security Servlet, cookie này được xử lý qua `RememberMeAuthenticationFilter`, `RememberMeServices` và thông thường tạo ra `RememberMeAuthenticationToken`. Cookie remember-me **khác** cookie `JSESSIONID`: kéo dài session không kiểm chứng được hành vi phát lại remember-me token, còn chỉ gửi lại `JSESSIONID` sẽ không chứng minh hệ thống đã auto-login.

Bài này hướng dẫn thiết kế và kiểm thử **bốn trường hợp đối với remember-me cookie**:

1. **Hết hạn:** browser vẫn cố gửi cookie cũ hoặc token server-side đã quá tuổi; hệ thống phải từ chối xác thực.
2. **Bị sửa (tampering):** bytes, cấu trúc, chữ ký hoặc cặp series/token không còn hợp lệ; hệ thống không được cấp quyền.
3. **Bị đánh cắp:** một actor khác có được *bản sao* cookie hợp lệ; ta cần hiểu mức độ có thể phát hiện, phạm vi tác hại và cách thu hồi.
4. **Bị phát lại (replay):** cùng một giá trị cookie được sử dụng lại sau một lần sử dụng; kết quả khác nhau giữa hash-based và persistent-token remember-me.

Áp dụng cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Không sử dụng cookie thật của người khác; các ví dụ chỉ dùng user, token và repository giả trong môi trường kiểm thử. Không truy cập trái phép hệ thống bên ngoài.

### 1.1. Phân biệt bốn trạng thái

| Trạng thái | Cookie có được server chấp nhận? | Kết quả cần kiểm thử | Nguy cơ chính |
| --- | --- | --- | --- |
| **Hết hạn** | Không | Không được auto-login; bắt người dùng đăng nhập lại | Chấp nhận credential ngoài thời hạn chính sách |
| **Bị sửa** | Không, nếu chữ ký/format hoặc token DB không khớp | Từ chối, hủy cookie client khi phù hợp, không tiết lộ secret | Bỏ qua kiểm tra integrity hoặc cấp quyền khi parse lỗi |
| **Bị đánh cắp** | **Có thể** vì đây là bản sao credential hợp lệ | Phân biệt hash-based và persistent token; kiểm tra chính sách thu hồi | Kẻ chiếm cookie dùng tài khoản mà không cần password |
| **Replay** | Tùy implementation và thứ tự request | Hash-based có thể dùng lại; persistent-token có rotation và phát hiện mismatch cũ | Credential đã dùng vẫn được chấp nhận vô hạn hoặc phát hiện giả do race |

**Không được kết luận “cookie không bị đánh cắp” chỉ vì chữ ký hợp lệ.** Chữ ký phát hiện dữ liệu đã bị thay đổi, **không** chứng minh ai đang cầm cookie. Một bản sao byte-for-byte có thể hợp lệ về mặt mật mã. Persistent-token rotation có thể nhận ra một dấu hiệu dùng lại giá trị cũ, nhưng không thể xác định chắc chắn actor nào là kẻ tấn công chỉ từ cặp token.

## 2. Hiểu luồng kiểm tra trước khi viết test

Một luồng bình thường sau khi người dùng tick “Remember me”:

~~~text
Lần đăng nhập tương tác thành công
  POST /login + username/password + remember-me=true
        |
        ├── AuthenticationManager xác minh password
        ├── SecurityContext được lưu theo session policy
        └── RememberMeServices.loginSuccess(...)
                ├── hash-based: ký dữ liệu cookie
                └── persistent: tạo series + token, lưu DB
                       |
                       v
           Set-Cookie: remember-me=<secret>

Lần truy cập sau, KHÔNG còn HttpSession đã xác thực
  GET /account/me
  Cookie: remember-me=<secret>
                       |
                       v
           RememberMeAuthenticationFilter
                       |
           SecurityContext chưa có Authentication?
                       |
                      YES
                       |
           RememberMeServices.autoLogin(...)
                       |
          ┌────────────┴────────────┐
          |                         |
       Hợp lệ               Sai/hết hạn/thu hồi
          |                         |
 RememberMeAuthenticationToken    null/exception
          |                         |
 AuthenticationManager           Không có quyền
          |                         |
 Authorization                   Login lại
~~~

Nếu request **vẫn có session hợp lệ với `Authentication`**, remember-me filter thường **không** thực hiện auto-login. Bài test phải xóa/không gửi session cookie và `MockHttpSession` cũ để ép ứng dụng kiểm tra remember-me. Đừng chỉ tạo cookie rồi gọi API trong một session đang fully authenticated: test như vậy có thể đi qua hoàn toàn mà không kiểm tra remember-me token.

### 2.1. Hai triển khai chuẩn

| Đặc điểm | `TokenBasedRememberMeServices` (hash-based) | `PersistentTokenBasedRememberMeServices` |
| --- | --- | --- |
| Dữ liệu cookie | Base64 của username, thời điểm hết hạn, thuật toán, chữ ký | Base64 của `series` và `token` |
| Kiểm chứng | Tính/so sánh chữ ký từ user/password/key và kiểm tra expiry | Tra `PersistentTokenRepository`, so series/token, tuổi record |
| Bản ghi token DB riêng | Không | Có |
| Cookie hợp lệ được dùng lần đầu | Đăng nhập tự động | Đăng nhập tự động **và xoay token** trong DB/cookie |
| Dùng lại chính cookie cũ | **Có thể tiếp tục được chấp nhận** đến hạn hoặc tới khi password/key đổi | Nếu series còn nhưng token DB đã đổi → mismatch, có thể ném `CookieTheftException` |
| Phát hiện bản sao bị dùng lại | Không có cơ chế per-token replay detection mặc định | Có dấu hiệu series/token mismatch sau rotation |
| Thu hồi | Hết hạn, đổi password/key, hoặc biện pháp bổ sung | Xóa record/token theo policy; logout chuẩn có thể thu hồi token của user |
| Kiểm thử trọng tâm | Hạn, chữ ký, replay vẫn thành công, password/key change | Hạn record, series, token rotation, replay mismatch, revoke, concurrency |

Cả hai triển khai đều cần `UserDetailsService`. Cả hai đều phải dùng HTTPS, cookie `HttpOnly`/`Secure` phù hợp và bảo vệ CSRF nếu browser tự gửi cookie để xác thực request đổi trạng thái.

## 3. Hết hạn: phải test ở browser VÀ server

Có **hai lớp hạn dùng** cần tách:

- **Browser expiration:** `Max-Age` hoặc `Expires` quyết định browser có tiếp tục tự gửi cookie không.
- **Server token validity:** kể cả khi client cố tình tự gửi giá trị cookie sau hạn, server **vẫn phải từ chối**. Browser không phải thành phần tin cậy để thực thi chính sách hết hạn.

Để tránh test ngủ 14 ngày, **không dùng `Thread.sleep(...)` chờ token hết hạn**. Hãy tạo dữ liệu hết hạn có kiểm soát hoặc tiêm clock khi ứng dụng sở hữu logic thời gian. Với dịch vụ thư viện Spring Security không có Clock injection công khai ở các điểm liên quan, test trực tiếp protected hook hoặc tạo token đã quá hạn là cách tập trung và nhanh hơn.

### 3.1. Hash-based: expiry nằm trong cookie có chữ ký

Cấu trúc khái quát theo Spring Security 6:

~~~text
Base64(
  username : expiryTimeMillis : algorithmName : signature
)

signature = hash(username : expiryTimeMillis : storedPassword : serverKey)
~~~

Có cơ chế tương thích cookie cũ không mang `algorithmName`. Từ đó:

- Thay `expiryTimeMillis` thành thời điểm tương lai mà **không** tạo lại chữ ký bằng key → **signature mismatch**, cookie bị từ chối.
- Tạo một payload **được ký hợp lệ** nhưng có `expiryTimeMillis` trong quá khứ → phải bị từ chối do **expired**, chứ không phải do signature sai.
- Đặt `Max-Age=0` trên response giúp browser xóa cookie; nhưng một HTTP client có thể cố tình gửi lại raw cookie bất chấp browser. Phải kiểm tra server side.
- `tokenValiditySeconds` ảnh hưởng tới thời hạn server kiểm chứng và cookie lifetime. Một số giá trị âm ở hash-based có ý nghĩa cookie browser-session nhưng thời hạn token server vẫn mặc định có thể dài hơn; không lấy mỗi `Max-Age` làm oracle.

Không nên tự dùng `Base64.decode(...)` trong ứng dụng production để định danh user từ cookie trước khi Spring Security kiểm tra signature. Base64 là encoding, **không phải encryption**, và payload chưa được xác minh có thể bị giả mạo.

### 3.2. Persistent-token: expiry nằm ở tuổi record

Một bản ghi điển hình:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Khi cookie `series:token` khớp DB nhưng ngày `last_used` (gắn với lần tạo/xoay token) quá cũ so với `tokenValiditySeconds`, `PersistentTokenBasedRememberMeServices` sẽ từ chối auto-login. **Việc từ chối token hết hạn không tự động xóa record khỏi bảng**, nên production cần cleanup policy.

Test cần phân biệt:

1. Đúng series và đúng token nhưng record đã hết hạn → từ chối vì expiration.
2. Đúng series nhưng token sai → `CookieTheftException` trước/khác nhánh expiry; có thể thu hồi token của user.
3. Series không tồn tại → lỗi không tìm được persistent token; **không** suy ra kẻ đánh cắp cookie.
4. Browser bỏ cookie vì Max-Age → request không có cookie; không đánh giá được nhánh server-expired.

Nếu chạy Redis/SQL multi-node, phải kiểm tra server time/clock skew và atomicity của cập nhật token. Không lấy thay đổi đồng hồ hệ điều hành trên máy production làm cách kiểm thử.

## 4. Cookie bị sửa: phân loại trước khi kỳ vọng lỗi

“Tamper” là nhóm gồm nhiều thao tác khác nhau:

| Thao tác test | Hash-based | Persistent-token | Kỳ vọng |
| --- | --- | --- | --- |
| Chuỗi Base64 không hợp lệ | Decode thất bại | Decode thất bại | Không đăng nhập, cookie bị hủy khi phù hợp. |
| Có Base64 nhưng sai số lượng phần tử | `InvalidCookieException` / xử lý invalid cookie | `InvalidCookieException` | Không đăng nhập. |
| Đổi username trong payload | Chữ ký không còn khớp hoặc user không tồn tại | Cookie persistent không chứa username như một trường tường minh | Không cấp danh tính khác. |
| Đổi expiry mà giữ signature | Signature sai | Expiry nằm ở record server, không phải trường trong cookie | Không thể kéo dài quyền bằng chỉnh client. |
| Đổi signature | Signature mismatch | Không có trường signature tương tự; thay token tạo mismatch | Không đăng nhập. |
| Đổi token nhưng giữ series đang tồn tại | Không áp dụng cặp series/token | **Có thể kích hoạt `CookieTheftException` và thu hồi token user** | Fail closed; tránh tự biến test tamper thành việc xóa token người dùng thật. |
| Đổi series thành một series không tồn tại | Không áp dụng | Không tìm thấy record | Không đăng nhập, không xác thực danh tính theo cookie. |

**Đừng test tampering trên cookie thật của user production.** Với persistent-token, một lần đổi token trong series hợp lệ có thể làm server **xóa mọi persistent-login token của username** theo implementation chuẩn. Đó là tác động phụ cần giới hạn trong fixture/test environment.

### 4.1. Không khẳng định HTTP 401 cho mọi trường hợp

`AuthenticationProvider`/`RememberMeServices` không tự quy định một status HTTP duy nhất. Khi `autoLogin` không thể cung cấp danh tính, endpoint protected có thể:

- Trả `401 Unauthorized` ở API có `AuthenticationEntryPoint` phù hợp.
- Redirect `302` sang `/login` ở form-login website.
- Trả `403` nếu authorization/CSRF chặn request ở tầng khác.

Do đó test ở tầng **service** nên assert `Authentication == null` hoặc loại exception thích hợp. Test **HTTP integration** nên assert response theo chain/entry point đã cấu hình, không dựa vào giả định 401/302 chung cho mọi app.

## 5. Cookie bị đánh cắp: điều gì phát hiện được?

Một cookie là **bearer credential**: nếu bản sao hợp lệ bị lấy trộm, việc request đến từ user agent/IP khác **không mặc nhiên khiến chữ ký/token sai**. Phải phân biệt kiểm thử **một credential bị sửa** và **một credential hợp lệ được sao chép**.

Tình huống kiểm thử an toàn:

~~~text
Browser A (chủ tài khoản)
  └── có cookie R1 hợp lệ
                 |
        Chỉ trong test fixture:
        sao chép R1 sang client B
                 |
                 v
Browser B (mô phỏng attacker)
  └── gửi chính R1 (không sửa byte nào)
                 |
                 v
Server: kiểm tra R1 theo implementation
~~~

**Hash-based:** B có thể auto-login như A cho đến khi cookie hết hạn hoặc password/key thay đổi. Mỗi lần dùng R1 không tự làm R1 mất hiệu lực, nên test replay ở hai client **có thể đều thành công**. Đây là **giới hạn bảo mật quan trọng cần kiểm soát bằng thời hạn, re-auth, phát hiện bất thường và chính sách remember-me**.

**Persistent-token:** client đầu tiên sử dụng `series=S, token=T1` thành công sẽ cập nhật DB thành `S,T2` và nhận cookie mới. Client còn giữ `S,T1` lúc dùng lại sẽ thấy series đúng nhưng token sai; mặc định `PersistentTokenBasedRememberMeServices` coi đó là dấu hiệu có thể bị đánh cắp, ném `CookieTheftException` và gọi `removeUserTokens(username)`.

### 5.1. Chưa biết ai là người sử dụng đầu tiên

Giả sử kẻ đánh cắp token sử dụng R1 **trước** nạn nhân:

~~~text
DB: S/T1

Attacker B gửi S/T1 → HỢP LỆ
  DB xoay thành S/T2
  B nhận cookie S/T2

Nạn nhân A gửi S/T1 → MISMATCH
  Server nghi cookie theft
  Token của user bị thu hồi
~~~

Lần sử dụng đầu tiên của B **đã thành công**; phát hiện có thể chỉ đến ở request kế tiếp. Token rotation không ngăn được hoàn toàn mọi lần sử dụng đầu tiên của credential bị đánh cắp. Một mismatch cũng **không chứng minh danh tính của thủ phạm**; đó là dấu hiệu cần điều tra.

### 5.2. Concurrency và false positive

Hai request song song từ hai tab hợp lệ có thể cùng gửi `S/T1` trước khi browser nhận cookie mới. Request đầu xoay DB thành `T2`, request thứ hai thấy token cũ và bị coi là mismatch. Nếu dùng implementation mặc định, hành vi revocation có thể xảy ra ngay cả khi không có attacker.

Vì vậy phải test race, retry, multi-tab và transport delay trong staging. Không đơn giản xóa cơ chế so sánh token để tránh false positive: việc đó làm mất lợi ích phát hiện replay. Thay vào đó, xem xét thiết kế request/session transition, đồng bộ hóa ở lớp ứng dụng hoặc dùng cơ chế token riêng đã được đánh giá; thay đổi logic persistent remember-me cần security review.

### 5.3. Từ phát hiện tới ứng phó

Với tín hiệu replay hoặc cookie theft, quy trình thường gồm:

1. Từ chối auto-login và thu hồi token theo policy.
2. Log **loại sự kiện** (mismatch/expired/unknown series) cùng correlation ID, không log raw cookie/series/token.
3. Báo cho chủ tài khoản bằng kênh tin cậy khi phù hợp; tránh thông báo chứa token.
4. Yêu cầu đăng nhập tương tác mới và có thể MFA/step-up cho tác vụ nhạy cảm.
5. Rà soát các phiên HTTP đã xác thực và token khác; thu hồi remember-me **không tự hủy toàn bộ JSESSIONID hiện hữu**.
6. Phân tích concurrent requests để tránh kết luận chắc chắn có trộm cookie từ một dấu hiệu duy nhất.

## 6. Cookie bị phát lại: phải xác định “lần đầu” và “lần sau”

Replay thường có nghĩa **gửi lại cùng credential đã từng được chấp nhận**. Nhưng kết quả khác nhau:

~~~text
HASH-BASED
Cookie R1 → autoLogin thành công
Cookie R1 → autoLogin tiếp vẫn có thể thành công
Cookie R1 → ... đến khi expiry/password/key thay đổi

PERSISTENT
DB: S/T1
Cookie S/T1 → autoLogin thành công
              DB: S/T2, response cookie S/T2

Cookie S/T2 → autoLogin thành công
              DB: S/T3, response cookie S/T3

Cookie S/T1 → series đúng, token cũ
              CookieTheftException, có thể revoke token user
~~~

Đây là lý do bộ test replay phải giữ **bản sao cookie cũ** và không vô tình thay bằng response cookie mới của lần auto-login thứ nhất. Nếu test HTTP client tự động cập nhật cookie jar, việc gửi “cookie lần hai” có thể thực chất là gửi token **đã xoay**, nên luôn 200 và không kiểm tra replay cũ.

Cần test độc lập:

- **Replay cùng raw cookie hash-based:** hai lượt không có session khác nhau; có thể đều được chấp nhận khi còn hạn.
- **Persistent normal rotation:** dùng cookie mới sau response; phải thành công và giá trị token mới khác giá trị cũ, trong khi series giữ nguyên.
- **Persistent stale replay:** gửi lại cookie **cũ** sau khi đã xoay; phải bị từ chối và có tín hiệu mismatch.
- **Persistent unknown series:** không có bản ghi; không đánh đồng với token mismatch.
- **Persistent expired record:** ngay cả token đúng cũng không được xác thực.
- **Replay sau revoke/logout:** không được tự đăng nhập nếu token persistent đã bị xóa khỏi store.

## 7. Điều kiện tiền đề cho kiểm thử đáng tin

Một bộ test chất lượng nên kiểm soát các yếu tố sau:

| Yếu tố | Cách kiểm soát |
| --- | --- |
| **Cookie thật được gửi** | Với HTTP integration, gửi cookie `remember-me` nhưng **không gửi JSESSIONID** và không inject user qua `@WithMockUser`. |
| **Định danh riêng** | Dùng username giả test riêng để không xóa token user thật khi mismatch. |
| **Signing key** | Key test cố định chỉ dùng trong môi trường test; production key lưu trong secret manager. |
| **Password hash** | Với hash-based, dùng `UserDetailsService` ổn định và key/password đúng; không thay user giữa hai lần test trừ khi chính là case password change. |
| **Kho persistent** | `InMemoryTokenRepositoryImpl` chỉ dùng trong unit test; production dùng DB bền vững. |
| **Thời gian** | Dùng token được tạo với `Date` quá khứ hoặc expiry đã được ký hợp lệ; không ngủ hàng ngày. |
| **Cookie jar** | Chụp bản sao token cũ trước auto-login; phân biệt cookie mới từ `Set-Cookie`. |
| **Session** | Không để session login tương tác che đường remember-me. |
| **Status/entry point** | Bảo đảm expectations theo filter chain thật, không lẫn 401/302/403. |
| **Side effects** | Assert repository sau rotation/mismatch/revoke, không chỉ assert HTTP status. |
| **Data safety** | Không in token, cookie, series, password hoặc hash vào log/CI artifacts. |
| **Concurrency** | Chạy thêm test nhiều request song song; không coi mismatch nào cũng chứng minh attack. |

Một lưu ý rất quan trọng: **cookie hết hạn ở browser** và **token hết hạn ở server** phải được kiểm tra riêng. Client tùy chỉnh hoặc attacker có thể vẫn gửi raw cookie sau khi browser bình thường đã xóa.

## 8. Dự án test Spring Boot 3.x / Java 17+ / JUnit 5

Ví dụ dưới đây gọi **trực tiếp RememberMeServices và các hook protected được expose trong test subclass**, thay vì đi qua browser. Cách này kiểm tra chính xác token signature, expiry, series rotation, mismatch và tác động trên repository mà không cần HTTP session thật. Mọi token đều là giả; test không cần database ngoài.

Trong một Spring Boot 3.x Gradle project đã có plugin/dependency management, cấu hình:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn đưa vào build.gradle hiện hữu**, không phải build file độc lập. `spring-boot-starter-test` cung cấp JUnit 5 và Spring Mock request/response; `spring-boot-starter-security` cung cấp remember-me services.

File cần tạo trong dự án:

~~~text
src/test/java/com/example/remembertest/RememberCookieSecurityTest.java
~~~

### 8.1. Test fixture và các test đầy đủ

~~~java
package com.example.remembertest;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.authentication.rememberme.CookieTheftException;
import org.springframework.security.web.authentication.rememberme.InMemoryTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentRememberMeToken;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.RememberMeAuthenticationException;
import org.springframework.security.web.authentication.rememberme.TokenBasedRememberMeServices;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RememberCookieSecurityTest {

    private static final String KEY = "only-a-test-secret-not-for-production";
    private static final String USERNAME = "student";
    private static final String STORED_PASSWORD = "{noop}demo-password";
    private static final String COOKIE_NAME = "remember-me";
    private static final int TWO_WEEKS = 14 * 24 * 60 * 60;

    private static UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername(USERNAME)
                .password(STORED_PASSWORD)
                .roles("USER")
                .build()
        );
    }

    private static Authentication authenticatedUser() {
        UserDetails user = users().loadUserByUsername(USERNAME);
        return UsernamePasswordAuthenticationToken.authenticated(
            user, null, user.getAuthorities());
    }

    private static MockHttpServletRequest withCookie(Cookie cookie) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setCookies(cookie);
        return request;
    }

    private static MockHttpServletRequest optInLoginRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("remember-me", "true");
        return request;
    }

    private static Cookie issuedCookie(TokenBasedRememberMeServices service) {
        MockHttpServletResponse response = new MockHttpServletResponse();
        service.loginSuccess(
            optInLoginRequest(), response, authenticatedUser());
        Cookie cookie = response.getCookie(COOKIE_NAME);
        assertNotNull(cookie);
        return cookie;
    }

    private static class InspectableHash extends TokenBasedRememberMeServices {
        InspectableHash() {
            super(KEY, users());
            setTokenValiditySeconds(TWO_WEEKS);
            afterPropertiesSet();
        }

        // Chỉ expose protected hook để tạo chữ ký ĐÚNG cho test expiry.
        String sign(long expiresAt, String username, String storedPassword) {
            return makeTokenSignature(expiresAt, username, storedPassword);
        }
    }

    private static class InspectablePersistent
            extends PersistentTokenBasedRememberMeServices {
        InspectablePersistent(InMemoryTokenRepositoryImpl repository) {
            super(KEY, users(), repository);
            setTokenValiditySeconds(TWO_WEEKS);
            afterPropertiesSet();
        }

        // Chỉ dùng trong unit test: bypass autoLogin() wrapper để
        // assert chính xác loại exception và side effect repository.
        UserDetails inspect(String series, String token) {
            return processAutoLoginCookie(
                new String[] {series, token},
                new MockHttpServletRequest(),
                new MockHttpServletResponse()
            );
        }
    }

    private static class StoreFixture {
        final InMemoryTokenRepositoryImpl repository =
            new InMemoryTokenRepositoryImpl();
        final InspectablePersistent service =
            new InspectablePersistent(repository);

        void put(String series, String token, Date lastUsed) {
            repository.createNewToken(
                new PersistentRememberMeToken(
                    USERNAME, series, token, lastUsed));
        }
    }

    private static String base64(String text) {
        return Base64.getEncoder().encodeToString(
            text.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void hashCookieCanAuthenticateWithoutAnHttpSession() {
        InspectableHash service = new InspectableHash();
        Cookie cookie = issuedCookie(service);

        Authentication result = service.autoLogin(
            withCookie(cookie), new MockHttpServletResponse());

        assertNotNull(result);
        assertEquals(USERNAME, result.getName());
        assertTrue(result.isAuthenticated());
    }

    @Test
    void hashCookieTamperingIsRejected() {
        InspectableHash service = new InspectableHash();
        Cookie original = issuedCookie(service);

        String raw = new String(
            Base64.getDecoder().decode(original.getValue()),
            StandardCharsets.UTF_8);
        String[] fields = raw.split(":", -1);
        assertTrue(fields.length == 4 || fields.length == 3);

        // Giữ format Base64 hợp lệ, nhưng thay phần chữ ký.
        fields[fields.length - 1] = "bad-signature";
        Cookie tampered = new Cookie(
            COOKIE_NAME, base64(String.join(":", fields)));

        MockHttpServletResponse response = new MockHttpServletResponse();
        Authentication result = service.autoLogin(
            withCookie(tampered), response);

        assertNull(result);
        Cookie cancelled = response.getCookie(COOKIE_NAME);
        assertNotNull(cancelled);
        assertEquals(0, cancelled.getMaxAge());
    }

    @Test
    void expiredHashCookieIsRejectedEvenWithValidSignature() {
        InspectableHash service = new InspectableHash();

        long past = System.currentTimeMillis()
            - Duration.ofDays(2).toMillis();
        String signature =
            service.sign(past, USERNAME, STORED_PASSWORD);

        // Format ba trường vẫn được Spring Security hỗ trợ để đọc
        // cookie cũ không có algorithmName.
        String oldButSigned = base64(
            USERNAME + ":" + past + ":" + signature);
        Cookie expired = new Cookie(COOKIE_NAME, oldButSigned);

        assertNull(service.autoLogin(
            withCookie(expired), new MockHttpServletResponse()));
    }

    @Test
    void hashCookieCanBeReplayedWhileStillValid() {
        InspectableHash service = new InspectableHash();
        Cookie original = issuedCookie(service);

        // Hai request KHÔNG đính kèm HttpSession cũ;
        // đều trình lại đúng cookie remember-me.
        Authentication first = service.autoLogin(
            withCookie(original), new MockHttpServletResponse());
        Authentication second = service.autoLogin(
            withCookie(original), new MockHttpServletResponse());

        assertNotNull(first);
        assertNotNull(second);
        assertEquals(USERNAME, first.getName());
        assertEquals(USERNAME, second.getName());
    }

    @Test
    void persistentValidUseRotatesTokenButKeepsSeries() {
        StoreFixture f = new StoreFixture();
        f.put("series-1", "token-old", new Date());

        UserDetails user = f.service.inspect(
            "series-1", "token-old");

        PersistentRememberMeToken rotated =
            f.repository.getTokenForSeries("series-1");
        assertEquals(USERNAME, user.getUsername());
        assertNotNull(rotated);
        assertEquals("series-1", rotated.getSeries());
        assertNotEquals("token-old", rotated.getTokenValue());
    }

    @Test
    void replayOfOldPersistentTokenDetectsMismatchAndRevokes() {
        StoreFixture f = new StoreFixture();
        f.put("series-2", "token-before-rotation", new Date());

        // Client A dùng cookie hợp lệ và làm server xoay token.
        f.service.inspect("series-2", "token-before-rotation");
        PersistentRememberMeToken changed =
            f.repository.getTokenForSeries("series-2");
        assertNotNull(changed);
        assertNotEquals(
            "token-before-rotation", changed.getTokenValue());

        // Client B giữ bản sao cũ: cùng series nhưng token sai.
        assertThrows(CookieTheftException.class, () ->
            f.service.inspect(
                "series-2", "token-before-rotation"));

        // Implementation chuẩn xóa token của username khi mismatch.
        assertNull(f.repository.getTokenForSeries("series-2"));
    }

    @Test
    void persistentUnknownSeriesIsRejected() {
        StoreFixture f = new StoreFixture();

        assertThrows(RememberMeAuthenticationException.class, () ->
            f.service.inspect("series-not-stored", "any-token"));

        // Không có record để gán lỗi cho một user cụ thể.
        assertNull(f.repository.getTokenForSeries("series-not-stored"));
    }

    @Test
    void expiredPersistentRecordIsRejectedAndNotAutoDeleted() {
        StoreFixture f = new StoreFixture();
        Date old = Date.from(Instant.now().minus(Duration.ofDays(30)));
        f.put("series-expired", "correct-old-token", old);

        assertThrows(RememberMeAuthenticationException.class, () ->
            f.service.inspect(
                "series-expired", "correct-old-token"));

        // Spring Security từ chối vì quá hạn, nhưng không tự
        // dọn record hết hạn khỏi repository.
        assertNotNull(f.repository.getTokenForSeries("series-expired"));
    }

    @Test
    void persistentTamperWithKnownSeriesTriggersTheftSignal() {
        StoreFixture f = new StoreFixture();
        f.put("series-known", "real-token", new Date());

        assertThrows(CookieTheftException.class, () ->
            f.service.inspect("series-known", "modified-token"));

        assertNull(f.repository.getTokenForSeries("series-known"));
    }

    @Test
    void persistentExplicitRevocationPreventsFurtherLogin() {
        StoreFixture f = new StoreFixture();
        f.put("series-revoked", "token-before-revoke", new Date());

        f.repository.removeUserTokens(USERNAME);

        assertNull(f.repository.getTokenForSeries("series-revoked"));
        assertThrows(RememberMeAuthenticationException.class, () ->
            f.service.inspect(
                "series-revoked", "token-before-revoke"));
    }
}
~~~

### 8.2. Vì sao tách unit test dịch vụ khỏi HTTP test?

Các test `InspectablePersistent.inspect(...)` **gọi trực tiếp hook `processAutoLoginCookie`** để kiểm tra chính xác `CookieTheftException` và side effect trên `PersistentTokenRepository`. Khi đi qua public `RememberMeServices.autoLogin(...)` và `RememberMeAuthenticationFilter`, một số lỗi có thể được bắt/đổi thành “không auto-login”, cookie bị xóa và request tiếp tục sang cơ chế authentication entry point. Vì thế không mặc định rằng client HTTP sẽ nhận một response body chứa tên exception.

Cần nhớ hai lớp assert:

- **Unit test service/repository:** loại exception, token rotation, record còn/mất, signature/expiry.
- **MockMvc/integration test:** cookie có thực sự gửi tới filter không, `SecurityContext` còn trống hay được khôi phục, endpoint có cho remembered authentication không, có status/redirect hợp lệ không.

Trong `hashCookieTamperingIsRejected`, test thay chữ ký thành một chuỗi sai nhưng giữ Base64/định dạng phân tách hợp lệ. Đây là **kiểm thử integrity**, không phải kiểm thử payload decode lỗi. Cần một test riêng cho cookie không phải Base64 nếu ứng dụng có custom cookie decoder.

Trong `expiredHashCookieIsRejectedEvenWithValidSignature`, dùng legacy 3-field cookie được Spring Security 6.x hỗ trợ để tạo **expiry đã qua nhưng signature đúng**. Test này phân biệt expiry enforcement với signature mismatch mà không cần chờ thực tế.

Trong `hashCookieCanBeReplayedWhileStillValid`, việc cả hai lần auto-login thành công **không phải test failure**: nó chứng minh hạn chế của hash-based implementation và lý do cần cân nhắc persistent-token/step-up.

Test persistent dùng `InMemoryTokenRepositoryImpl` chỉ trong bộ test. Nó không phù hợp production và không mô phỏng locking/transaction/replication của cơ sở dữ liệu.

### 8.3. Chạy kiểm thử

~~~bash
./gradlew test --tests com.example.remembertest.RememberCookieSecurityTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.remembertest.RememberCookieSecurityTest
~~~

Nếu project dùng đúng Spring Boot 3.x, Java 17+, Spring Security 6.x và dependencies của mục 8, các assertion mô tả kỳ vọng hành vi; Gradle thường báo `BUILD SUCCESSFUL` khi tất cả pass. **Không coi đây là log đã chạy**: kết quả thực tế còn phụ thuộc version cụ thể và môi trường của bạn.

Đoạn test là mã JUnit, không phải ứng dụng `public static void main(...)` chạy bằng `javac` thuần; nó cần classpath của Spring Security, Spring Test và JUnit. Không dùng key/username/password giả trong code làm cấu hình sản xuất.

## 9. Bổ sung kiểm thử ở tầng HTTP với MockMvc

Unit test `RememberMeServices` vẫn chưa chứng minh filter chain và authorization của ứng dụng thật. Ở tầng HTTP, bài test nên:

1. Đăng nhập tương tác với lựa chọn `remember-me=true` và CSRF token hợp lệ nếu form login bật CSRF.
2. Nhận cookie `remember-me` từ response, giữ nó **trong fixture kín**.
3. Trong request tiếp theo, **không gửi lại `JSESSIONID` hoặc `MockHttpSession` của lần login**.
4. Gọi endpoint chỉ yêu cầu `authenticated()`.
5. Assert principal được remember-me khôi phục.
6. Gọi endpoint nhạy cảm dùng `fullyAuthenticated()`; người dùng remembered phải bị yêu cầu xác thực tương tác lại.
7. Làm mất hiệu lực token (expiry/revoke/tamper) và assert endpoint không còn chấp nhận remember-me.

Ví dụ cách tạo request trong một test Spring Boot có `MockMvc` (đây là fragment cần test fixture và cấu hình chain phù hợp):

~~~java
MvcResult login = mvc.perform(
        post("/login")
            .with(csrf())
            .param("username", "student")
            .param("password", "demo-password")
            .param("remember-me", "true"))
    .andExpect(status().is3xxRedirection())
    .andReturn();

Cookie remember = login.getResponse().getCookie("remember-me");
assertNotNull(remember);

// KHÔNG gọi .session(...) ở request dưới.
// Chỉ gửi cookie nhớ đăng nhập, không có session authenticated.
mvc.perform(get("/account/me").cookie(remember))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.remembered").value(true));
~~~

Đoạn này **không phải file test độc lập**: cần `@SpringBootTest`, `@AutoConfigureMockMvc`, bean `SecurityFilterChain` bật `formLogin()`/`rememberMe()`, `UserDetailsService` demo, controller trả trường `remembered` và các static imports của MockMvc. Với một cấu hình web session đúng, test chứng minh browser không cần gửi session cũ để auto-login nhờ remember-me.

**Lưu ý:** @WithMockUser hoặc `SecurityMockMvcRequestPostProcessors.user(...)` làm request có authentication trực tiếp; khi đó `RememberMeAuthenticationFilter` có thể không chạy. Không dùng chúng trong test chính của remember-me.

### 9.1. Bộ integration test nên có hai trình duyệt độc lập

Với token bị đánh cắp và replay, dùng hai HTTP clients/cookie jars riêng:

~~~text
Client A — legitimate
  Login + remember-me -> token R1
  Session cookie được loại khỏi test auto-login

Client B — simulated stolen-cookie actor
  Chỉ nhận bản sao R1 trong môi trường test

Kiểm tra theo thứ tự:
  1) B gửi R1
  2) A gửi R1
  3) A hoặc B nhận cookie mới R2?
  4) Store có revoke không?
  5) Có session mới được tạo trước/sau một auto-login?
  6) Quyền endpoint fullyAuthenticated có bị vượt không?
~~~

Với persistent token, **thứ tự A/B có thể đảo ngược**, nhưng chỉ client đầu tiên dùng R1 thành công trước rotation. Client dùng R1 sau đó có thể gây mismatch. Không hiển thị raw token trong báo cáo CI; dùng kết quả boolean, opaque fixture IDs và correlation IDs.

### 9.2. Cookie jar phải được điều khiển

Các thư viện HTTP client có thể tự động thay cookie cũ bằng response `Set-Cookie` mới. Điều này tốt cho sử dụng bình thường nhưng làm test replay không đúng mục tiêu.

Cần hai tình huống **tách biệt**:

- **Normal flow:** cập nhật cookie jar sau mỗi response; dùng R2 rồi R3, xác nhận ứng dụng tiếp tục auto-login.
- **Attack simulation:** chụp bản sao R1 từ đầu, cố tình giữ nguyên ở client khác; sau khi server xoay thành R2, gửi lại R1 và kiểm tra từ chối/mismatch.

Không giải mã token trong browser rồi tự chỉnh các trường ở frontend production. Việc xây dữ liệu test token thuộc test harness/unit test, không phải code nghiệp vụ.

## 10. Quy trình E2E khi cookie đã hết hạn

Để kiểm tra browser behavior, tạo môi trường staging với thời hạn remember-me ngắn có chủ đích, ví dụ 2 phút. Không nên tăng thời gian thực thi test bằng cách ngủ 2 phút trong mọi lần CI; dùng integration test có clock hỗ trợ, hoặc một test profile chuyên biệt.

**Case A — Browser tự xóa cookie:**

~~~text
Login có Remember me
  ↓
Set-Cookie: remember-me=...; Max-Age=120
  ↓
Chờ bằng test profile / giả lập browser expiration
  ↓
Cookie không còn được browser gửi
  ↓
Endpoint protected yêu cầu login lại
~~~

**Case B — Client vẫn gửi token đã hết hạn:**

~~~text
Tạo token server-side đã quá hạn trong test fixture
  ↓
Gửi Cookie: remember-me=<expired-token>
  ↓
Spring Security không cấp RememberMeAuthenticationToken
  ↓
Endpoint protected yêu cầu login lại
~~~

Case B là **bảo đảm bảo mật quan trọng hơn**: browser compliance không thay server expiration check. Với persistent record, case B dựng record date cũ trong repository. Với hash-based, tạo payload có timestamp cũ **và chữ ký hợp lệ**, như `InspectableHash.sign(...)`.

Đừng thay đổi đồng hồ production, cookie thật hoặc token thật của user chỉ để chứng minh hết hạn.

## 11. Logout, password reset và thu hồi token

Một số test “cookie bị đánh cắp / phát lại” sẽ cho kết luận sai nếu chỉ nhìn response sau logout:

- Logout hủy `HttpSession` nhưng nếu remember-me cookie vẫn còn hợp lệ và không được dọn, request sau có thể tự đăng nhập lại.
- Hash-based remember-me logout thường hủy cookie trên browser hiện tại, nhưng **không có danh sách token DB để tự vô hiệu tất cả bản sao đã bị sao chép**.
- Với persistent-token implementation chuẩn, khi logout handler nhận được `Authentication` phù hợp, nó có thể gọi `removeUserTokens(username)`, thu hồi nhiều token của user. Điều này khác với “chỉ quên thiết bị hiện tại”.
- Password reset có thể làm hash-based token cũ mất hiệu lực vì chữ ký phụ thuộc password hash. Persistent-token record **không tự bị xóa chỉ vì thay password**: ứng dụng cần chính sách thu hồi chủ động.
- Đổi signing key ở hash-based cũng có thể vô hiệu cookie cũ, nhưng cần có key rotation plan và quản lý secret đồng nhất qua các node.

Bộ test nên chứng minh ít nhất:

| Sự kiện | Hash-based | Persistent-token |
| --- | --- | --- |
| Logout hiện tại | Cookie browser bị xóa; bản sao bị đánh cắp có thể vẫn còn hạn | Cookie browser bị xóa; DB tokens được thu hồi theo handler/policy |
| Password đổi | Token ký theo password cũ mất hiệu lực | Chủ động xóa persistent token theo chính sách |
| User khóa/vô hiệu | `UserDetailsService`/checker phải chặn auto-login | Tương tự, cần kiểm tra user status |
| Remember-me token đã bị revoke | Không có per-token revoke mặc định | Tra DB không thấy series, từ chối |
| HTTP session bị xóa | Cookie remember-me có thể auto-login mới | Tương tự nếu persistent token còn hợp lệ |
| Endpoint đòi full login | `fullyAuthenticated()` không nhận remembered-only | Tương tự |

**Thu hồi remember-me không nhất thiết hủy các HTTP session đang authenticated.** Nếu sản phẩm yêu cầu “Đăng xuất tất cả thiết bị”, cần phối hợp session store/registry, remember-me tokens, API tokens và các cơ chế khác.

## 12. Kiểm thử cookie attributes và browser security

Một token đủ mạnh nhưng cookie được gửi sai scope vẫn nguy hiểm. Kiểm tra `Set-Cookie` trong test hoặc DevTools:

| Thuộc tính | Kỳ vọng bảo mật |
| --- | --- |
| `Secure` | Production chỉ gửi qua HTTPS. |
| `HttpOnly` | JavaScript thường không cần đọc remember-me token; bật để giảm nguy cơ lấy trộm qua XSS. |
| `SameSite` | Theo topologie cùng-site/cross-site; không vô cớ bật `None`; bảo vệ CSRF riêng. |
| `Domain` | Không mở rộng đến subdomain không cần thiết. |
| `Path` | Giới hạn route/host phù hợp; logout phải xóa cookie đúng Path/Domain. |
| `Max-Age` / `Expires` | Hạn browser phù hợp với token validity server, không quá dài không cần thiết. |
| Cookie name | Tên phải khớp trong filter/services, tránh xung đột với cookie khác. |

**Không nhầm** session cookie `JSESSIONID` với cookie `remember-me`. Cấu hình `server.servlet.session.cookie.*` thường tác động session cookie; nhớ đăng nhập do `RememberMeServices` quản lý. Kiểm tra từng cookie riêng, không mặc định mọi flag giống nhau.

CORS cũng không phải cơ chế chống cookie theft hay CSRF. Nếu backend dựa trên cookie được browser tự gửi, hãy giữ bảo vệ CSRF cho request thay đổi trạng thái. Khi browser gọi API khác origin, `credentials: "include"`, CORS allowlist và cookie `SameSite` phải được đánh giá riêng.

Với XSS, `HttpOnly` làm JS khó đọc cookie nhưng không ngăn script chạy trong origin hợp lệ gửi request dưới danh tính người dùng. Cần CSP, output encoding và tránh DOM injection.

## 13. Testing HTTP status: kỳ vọng theo authentication level

Một endpoint nhạy cảm có thể có chính sách:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/sensitive").fullyAuthenticated()
    .requestMatchers("/account/**").authenticated()
    .anyRequest().permitAll()
);
~~~

Từ đó:

| Trạng thái | `GET /account/me` | `GET /account/sensitive` |
| --- | --- | --- |
| Có session xác thực đầy đủ | Cho phép | Cho phép, nếu có quyền bổ sung tương ứng |
| Chỉ có remember-me hợp lệ | Cho phép | Yêu cầu login tương tác lại / step-up |
| Cookie tampered | Không được auto-login | Không được truy cập |
| Cookie expired | Không được auto-login | Không được truy cập |
| Persistent token bị replay và revoke | Không được auto-login sau revoke | Không được truy cập |
| Không có cookie | Chưa xác thực | Chưa xác thực |

Trong ứng dụng web form-login, unauthenticated/remembered-only truy cập endpoint bảo vệ có thể bị **redirect 302** tới login; ở API entry point, có thể là **401**. Nếu request có CSRF violation, có thể nhận **403** trước cả remember-me handler. Vì vậy **không coi status 403/401/302 là bằng chứng duy nhất token hợp lệ hay không**; test service/repository và principal/trust level để hiểu nguyên nhân.

Một user remembered có thể có `Authentication.isAuthenticated()==true`, nhưng `AuthenticationTrustResolver.isRememberMe(authentication)` là true và `isFullyAuthenticated(authentication)` là false. Không sử dụng mỗi cờ `isAuthenticated` để cho phép đổi mật khẩu, thanh toán, bật MFA hoặc xóa tài khoản.

## 14. Debug khi test thất bại

| Dấu hiệu | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| Cookie đã sửa mà test vẫn 200 | Session cũ hoặc `@WithMockUser` đang xác thực sẵn | Bỏ JSESSIONID/session mock, xem filter có chạy không. |
| Cookie hết hạn vẫn được “chấp nhận” | Chỉ kiểm tra Max-Age phía browser, chưa test server | Gửi raw expired token trực tiếp tới service. |
| Persistent replay cũ vẫn 200 | HTTP client tự cập nhật token mới | Giữ **bản sao token cũ** trong cookie jar độc lập. |
| Persistent mismatch xóa nhiều thiết bị | `removeUserTokens(username)` được gọi | Xác minh scope revocation, policy logout/incident. |
| Unknown series bị báo như theft | Test gắn nhầm token vào series đang tồn tại | Tạo series thật sự chưa có trong repository. |
| Token hết hạn mà record còn | Cleanup chưa chạy | Đó có thể là hành vi chuẩn; kiểm tra job cleanup riêng. |
| Hash cookie từ ngày hôm qua bỗng mất hiệu lực | Password hash hoặc signing key thay đổi | Kiểm tra key qua deployments và user changes. |
| Remember-me cookie không hiện trong response | Không opt-in, param không đúng, login không thành công | Kiểm tra loginSuccess, form param, cookie flags. |
| Remember-me hoạt động nhưng endpoint nhạy cảm redirect | `fullyAuthenticated()` hoạt động | Đây có thể là expected behavior. |
| Test persistent song song flake | Rotation và request dùng token cũ cạnh tranh | Test với barrier/2 clients, đánh giá race. |
| Logout xong nhưng auto-login lại | Cookie hoặc DB token chưa được xóa | Kiểm tra logout handlers, Path/Domain và policy. |
| Test local chạy, production không giữ cookie | HTTPS, Secure, SameSite, proxy, browser third-party restrictions | Kiểm tra trên origin thực và DevTools Network. |

### 14.1. Nguyên tắc log an toàn

Không log các thông tin sau:

- Raw header `Cookie`, `Set-Cookie` hoặc `Authorization`.
- Giá trị `remember-me`, `JSESSIONID`, series/token đầy đủ.
- Password gốc, BCrypt hash hay signing key.
- URL chứa token/cookie, response body debug vô tình echo token.

Log nên dùng correlation ID, loại cơ chế (hash-based/persistent), loại lỗi (expired/tampered/unknown-series/mismatch), username hoặc user ID được che/giảm lộ theo yêu cầu privacy, và trạng thái revocation. Với `CookieTheftException`, ghi “suspected replay” thay vì khẳng định có theft đã được chứng minh.

## 15. Kiểm thử lỗi hệ thống và tính nhất quán dữ liệu

Bốn nhóm chính chưa bao phủ toàn bộ rủi ro. Với persistent-token implementation dùng SQL/Redis, cần thử thêm:

1. **Repository timeout khi auto-login:** request không được tự cấp quyền nếu không kiểm chứng được token. Không coi lỗi DB là cookie hợp lệ.
2. **Update token thất bại sau validate:** không trả kết quả giả như đã xoay thành công nếu DB không lưu được token mới.
3. **Hai node cùng cập nhật series:** đảm bảo consistency/transaction semantics, kiểm tra race; bộ repository mặc định không thay thế thiết kế distributed locking.
4. **Record bị xóa giữa read và update:** request phải fail closed hoặc có error handling rõ ràng.
5. **Clock skew:** các node cần đồng bộ thời gian; tokenValiditySeconds được kiểm tra server-side.
6. **User bị disabled/locked sau khi token phát hành:** phải kiểm tra trạng thái user hiện tại, không chỉ token.
7. **Secret rotation ở hash-based:** key mới làm token cũ mất hiệu lực có chủ đích; không để key thay đổi ngẫu nhiên.
8. **Token cleanup job:** bản ghi hết hạn được dọn theo lịch, nhưng cleanup không xóa token còn hiệu lực.
9. **Cookie domain/path mismatch trong logout:** token không bị browser xóa có thể auto-login lại.
10. **SecurityContext/session persistence sau remembered auto-login:** bảo đảm quy tắc session fixation/session creation và step-up đúng, không biến remembered thành full authentication chỉ vì session mới được tạo.

Đặc biệt, việc một remembered user được khôi phục vào session mới **không tự biến authentication đó thành fully authenticated**. Cấp quyền vẫn phải dựa trên trust level/chính sách.

## 16. QA matrix tổng hợp cho bài thực hành

| Case ID | Loại cookie | Thiết lập | Kỳ vọng |
| --- | --- | --- | --- |
| RM-EXP-01 | Hash | Cookie expiry đã qua, chữ ký hợp lệ | Auto-login bị từ chối. |
| RM-EXP-02 | Persistent | Record cũ quá `tokenValiditySeconds`, token đúng | Từ chối, record có thể vẫn ở store. |
| RM-EXP-03 | Cả hai | Browser không gửi cookie đã hết Max-Age | Endpoint đòi login, không được tự xác thực. |
| RM-TAMP-01 | Hash | Đổi signature nhưng giữ format | Không auto-login, cancel cookie khi phù hợp. |
| RM-TAMP-02 | Hash | Base64/field format sai | Không auto-login, không leak stack trace. |
| RM-TAMP-03 | Persistent | Series có, token sai | Dấu hiệu mismatch; thu hồi theo implementation chuẩn. |
| RM-TAMP-04 | Persistent | Series không tồn tại | Từ chối, không kết luận theft. |
| RM-REPLAY-01 | Hash | Gửi lại cookie còn hạn qua hai clients | Cả hai **có thể** auto-login; ghi nhận rủi ro. |
| RM-REPLAY-02 | Persistent | S/T1 hợp lệ → cập nhật S/T2 | Auto-login thành công, series giữ nguyên. |
| RM-REPLAY-03 | Persistent | Gửi lại S/T1 sau xoay | `CookieTheftException` tại service, revoke token. |
| RM-REPLAY-04 | Persistent | Dùng S/T2 sau xoay | Tiếp tục auto-login và xoay T3. |
| RM-THEFT-01 | Hash | Bản sao cookie dùng từ client B | Có thể dùng đến khi hết hạn/change key/password. |
| RM-THEFT-02 | Persistent | Client B dùng cookie trước client A | B có thể thành công lần đầu; A sau đó mismatch. |
| RM-RACE-01 | Persistent | Hai request đồng thời dùng S/T1 | Kiểm tra false-positive và policy xử lý. |
| RM-REVOKE-01 | Persistent | Server xóa token record | Cookie cũ không còn xác thực được. |
| RM-REVOKE-02 | Hash | Password/key thay đổi | Cookie ký theo dữ liệu cũ không còn hợp lệ. |
| RM-LOGOUT-01 | Cả hai | Logout đúng handler, client sau request mới | Không tự login lại qua cookie đã xóa/thu hồi. |
| RM-TRUST-01 | Cả hai | Chỉ còn remember cookie; endpoint `fullyAuthenticated()` | Bắt login tương tác lại. |
| RM-SESSION-01 | Cả hai | Xóa JSESSIONID nhưng giữ remember-me | Thực sự test nhánh remember-me, không phải session. |
| RM-OPS-01 | Persistent | Store lỗi hoặc unavailable | Fail closed, audit và status theo policy. |

## 17. Tổng kết và quyết định thiết kế

Bài học quan trọng không phải chỉ là “test cookie trả 401”, mà là **chứng minh hệ thống xử lý đúng trạng thái credential**:

- **Hết hạn:** server từ chối dù client vẫn gửi raw cookie.
- **Bị sửa:** signature hoặc token DB không khớp; không cấp Authentication.
- **Bị đánh cắp:** bản sao hợp lệ có thể được sử dụng; hash-based không tự phát hiện replay, persistent-token chỉ có tín hiệu khi giá trị cũ xuất hiện sau rotation.
- **Bị phát lại:** giữ nguyên bản sao R1 để test; đừng để cookie jar tự thay bằng R2 và làm sai kết luận.
- **Persistent-token mismatch:** có thể kích hoạt `CookieTheftException` và thu hồi token user, nhưng concurrency có thể tạo dấu hiệu tương tự.
- **Từ chối remembered-only ở endpoint nhạy cảm:** `fullyAuthenticated()` / step-up/MFA phải được kiểm tra độc lập.
- **Không nhầm session cookie với remember-me cookie:** test phải loại session cũ để exercise đúng `RememberMeAuthenticationFilter`.

Ưu tiên **unit test dịch vụ + repository** để kiểm tra expiry, integrity, rotation, exception và revocation; sau đó **MockMvc/E2E với cookie jars độc lập** để chứng minh browser/filter/authorization hoạt động. Dùng dữ liệu giả, không log secret, và kết hợp HTTPS, cookie security, CSRF protection, cleanup, cảnh báo vận hành và quy trình ứng phó sự cố.

### Tài liệu tham khảo

- Spring Security 6.5 Reference — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security 6.5 API — TokenBasedRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/TokenBasedRememberMeServices.html
- Spring Security 6.5 API — PersistentTokenBasedRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html
- Spring Security 6.5 API — AbstractRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html
- Spring Security 6.5 API — PersistentTokenRepository: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html
- Spring Security 6.5 API — PersistentRememberMeToken: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentRememberMeToken.html
- Spring Security 6.5 Reference — Servlet Authentication and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 Reference — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
