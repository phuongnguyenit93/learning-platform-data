# Thời gian sống, hết phiên và thao tác đăng xuất

## 1. Mục tiêu và tình huống học tập

Bài học thuộc **Phiên và cookie** trong **Spring Security - fundamentals**. Sau khi hoàn thành, bạn có thể:

1. Giải thích vòng đời một phiên đăng nhập dựa trên `HttpSession`: khởi tạo, xác thực, tái sử dụng, gia hạn hoạt động, hết hạn và hủy.
2. Phân biệt **idle timeout**, **absolute session lifetime**, **browser cookie lifetime**, **remember-me lifetime**, thời hạn access/refresh token và thời điểm thu hồi quyền.
3. Cấu hình thời gian không hoạt động cho phiên Servlet bằng `server.servlet.session.timeout`; hiểu giới hạn của cơ chế này và không nhầm nó với thời hạn cố định tính từ login.
4. Nhận biết phiên đã hết hoặc session ID không hợp lệ; hiểu `invalidSessionUrl`, cách xử lý request tiếp theo và sự khác biệt với session bị đánh dấu hết hạn do kiểm soát đăng nhập đồng thời.
5. Sử dụng quy trình logout tiêu chuẩn của Spring Security: `LogoutFilter`, `POST /logout`, CSRF token, hủy `HttpSession`, xóa `SecurityContext`, xóa cookie và chuyển hướng.
6. Chạy ứng dụng Java 17+ Spring Boot 3.5.12, quan sát session/cookie với trình duyệt, kiểm thử login–logout bằng `MockMvc`, và giải thích điều mà các bài test không thể tự chứng minh.
7. Xác định các rủi ro thực tế: session fixation, session hijacking, auto-logout sai, “logout” chỉ ở giao diện, phiên trên nhiều thiết bị, SSO và token còn hiệu lực.

**Phạm vi:** ứng dụng **Spring MVC/Servlet** sử dụng `HttpSecurity`, `HttpSession` và cookie phiên. WebFlux dùng `WebSession`/reactive security context và có các API cấu hình tương ứng nhưng không thể sao chép nguyên lớp Servlet sang WebFlux. Bài tập này tập trung vào **phiên xác thực dựa trên server**, không tự biến mọi use case thành JWT/stateless.

## 2. Phiên đăng nhập sống như thế nào?

Một phiên xác thực Servlet thường trải qua luồng:

```text
Người dùng mở trang
    │
    ▼
GET /account khi chưa đăng nhập
    │
    └─ Spring Security yêu cầu xác thực → chuyển đến /login
                                          │
                                          ▼
                              POST /login + username/password
                              + CSRF token hợp lệ
                                          │
                                      xác thực thành công
                                          │
                                          ▼
                              Authentication trong SecurityContext
                                          │
                              lưu ngữ cảnh cho request sau
                              bằng HttpSession thích hợp
                                          │
                                          ▼
                              Browser nhận cookie JSESSIONID
                                          │
               ┌──────────────────────────┴────────────────────────┐
               │                                                   │
        GET /account                                     Không còn hoạt động
        Cookie: JSESSIONID=...                            trong timeout
               │                                                   │
               ▼                                                   ▼
        server tìm lại session                            session hết hạn/
        và xác định user                                 bị loại khỏi store
               │                                                   │
               ▼                                                   ▼
             200 OK                                 request sau không thể
                                                    dùng session cũ
               │
               └── POST /logout + CSRF token hợp lệ
                           │
                           ▼
                  hủy phiên hiện tại
                  xóa security context / CSRF token
                  xử lý cookie
                           │
                           ▼
                  GET /account kế tiếp
                  cần đăng nhập lại
```

**Ý tưởng cốt lõi:** cookie thường giữ **session ID**, còn **trạng thái login** (thường gồm `SecurityContext` và `Authentication`) nằm trong server/session store. Cả việc *hết hạn do thời gian* và *logout chủ động* đều làm mất khả năng sử dụng lại phiên, nhưng **nguyên nhân, cơ chế, dấu vết audit và trải nghiệm** không giống nhau.

**Không tự động đồng nhất:** Spring Security xác thực request, Servlet container quản lý vòng đời `HttpSession`/session ID, còn browser quyết định gửi cookie theo scope và thuộc tính của nó. Spring Session có thể thay phần lưu trữ session bằng một kho phân tán. Bất kỳ cấu hình thực tế nào cũng cần biết thành phần nào quản lý hạn dùng.

## 3. Phân biệt các loại thời hạn: không có một “expiry” duy nhất

| Khái niệm | Bắt đầu đếm từ đâu? | Khi nào hết? | Nơi thực thi điển hình |
| --- | --- | --- | --- |
| **Idle timeout / max inactive interval** | Từ lần session được truy cập gần nhất theo container | Không được sử dụng trong khoảng đã cấu hình | Servlet container / session store |
| **Absolute session lifetime** | Thời điểm tạo hoặc xác thực lại, tùy policy | Sau một thời hạn tối đa bất kể vẫn hoạt động | Chính sách bổ sung ở ứng dụng/IdP |
| **Cookie Max-Age/Expires** | Khi browser nhận cookie | Browser không nên tiếp tục gửi cookie sau hạn | Browser |
| **Session cookie (không Max-Age cố định)** | Khi browser nhận cookie | Theo vòng đời phiên của browser; có thể chịu session restore | Browser |
| **Remember-me cookie/token** | Khi phát hành “remember me” | Theo thời hạn và trạng thái token remember-me | Browser + Spring Security / token store |
| **Access token expiry (`exp`)** | Theo giá trị thời gian tuyệt đối trong token | Resource server không chấp nhận token sau hạn (theo clock skew policy) | OAuth2 Resource Server / IdP |
| **Refresh token expiry/revocation** | Theo chính sách refresh token | Không thể dùng token đó xin access token mới nữa | Authorization Server / IdP |
| **Concurrent-session expiration** | Khi chính sách số phiên làm một phiên bị đánh dấu hết | Khi Spring Security phát hiện/loại phiên cũ | Session registry và Spring Security |

### Ví dụ minh họa idle timeout

Giả sử server đặt **idle timeout 10 phút**:

```text
09:00  Đăng nhập
09:06  GET /account sử dụng session hợp lệ → thời điểm hoạt động được cập nhật
09:14  GET /account sử dụng session hợp lệ → vẫn chưa quá 10 phút tính từ lần dùng
09:25  GET /account khi đã không dùng session trong >10 phút
       → session cũ có thể đã bị container/store loại
       → request không còn danh tính đăng nhập cũ
```

Đây là **ví dụ hành vi**, không phải bảo đảm đúng tại giây thứ 600. Container/store có thể dọn session lúc truy cập lại hoặc qua tiến trình cleanup; request đang chạy, độ phân giải timeout và môi trường có thể ảnh hưởng thời điểm quan sát. Thời hạn thường được xét dựa trên lần session được truy cập, không nhất thiết mọi request đều gia hạn nếu request đó không sử dụng session.

**Câu hỏi quan trọng:** một browser có AJAX polling mỗi 30 giây có thể vô tình duy trì phiên lâu hơn mong muốn nếu các request polling thực sự truy cập session. Nếu yêu cầu “bắt buộc đăng nhập lại sau 8 giờ bất kể hoạt động”, **idle timeout không đáp ứng**; cần một giới hạn tuyệt đối được thực thi ở server/identity layer.

### Idle timeout ≠ absolute lifetime

- **Idle timeout:** “Người dùng không dùng phiên trong 10 phút thì phiên hết.”
- **Absolute lifetime:** “Phiên không được sống quá 8 giờ kể từ thời điểm được thiết lập, dù người dùng liên tục tương tác.”
- **Reauthentication age:** “Trước một thao tác nhạy cảm, lần xác thực gần nhất không được quá 15 phút.” Đây là điều kiện *fresh login* riêng, có thể không buộc hủy mọi phiên.

Spring Boot cấu hình thời gian không hoạt động của Servlet session; nó **không tự cấp một chính sách absolute lifetime toàn diện** chỉ vì đã có `server.servlet.session.timeout`.

## 4. HttpSession, JSESSIONID và SecurityContext thực sự chứa gì?

Một ứng dụng Spring Security Servlet stateful thông thường có mối quan hệ:

```text
Browser                              Server
┌────────────────────┐              ┌─────────────────────────────────┐
│ Cookie             │              │ HttpSession store               │
│ JSESSIONID=abc...   │ ─── ID ────>│ session[abc...]                 │
│                    │              │   ├─ SecurityContext            │
└────────────────────┘              │   │   └─ Authentication           │
                                    │   │       ├─ principal            │
                                    │   │       └─ authorities          │
                                    │   └─ thuộc tính phiên khác        │
                                    └─────────────────────────────────┘
```

Đây là cách hoạt động **điển hình** khi dùng session login; không phải mọi ứng dụng đều cấu hình `SecurityContextRepository` theo cùng một cách. Ở Spring Security 6, các filter lưu/đọc context cần được hiểu theo đúng version; với form login tiêu chuẩn, Spring Security có cơ chế lưu Authentication để request sau khôi phục.

**Cookie session không phải “bản sao session”.** Browser mang một token định danh mờ (session ID) để server tra trạng thái. Nếu một người khác lấy được ID hợp lệ, họ có thể thử giả mạo phiên; vì thế phải bảo vệ cookie ID và luồng truyền tải.

**Đừng trả session ID qua API chỉ để debug.** Dữ liệu ví dụ bên dưới chỉ in `maxInactiveInterval` và trạng thái có/không có session, **không in ID hay SecurityContext**.

## 5. Cấu hình thời gian sống trong Spring Boot

Với ứng dụng Spring Boot dùng embedded Servlet container như Tomcat:

**`src/main/resources/application.properties`**

```properties
# Idle timeout của Servlet HttpSession trong môi trường demo
server.servlet.session.timeout=10m

# Phần cookie phù hợp demo; production cần HTTPS và Secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

- `10m` nghĩa là **10 phút không hoạt động**; Spring Boot chuyển cấu hình xuống servlet container/session manager.
- `HttpSession.getMaxInactiveInterval()` trả về số **giây** của giới hạn không hoạt động mà session nhìn thấy.
- `server.servlet.session.timeout` là thời gian session **phía server**, không phải tuổi cookie.
- `server.servlet.session.cookie.max-age` (nếu cấu hình) chỉ định hạn giữ cookie **ở browser**; nó không bảo đảm session tương ứng còn tồn tại phía server.
- `server.servlet.session.cookie.secure=true` nên bật trong môi trường HTTPS production; không bật một cách mù quáng khi đang chạy `http://localhost:8080` nếu bạn cần browser gửi cookie trong bài thực hành cục bộ.
- Với Spring Session (Redis/JDBC...), repository riêng có thể quản lý TTL/session timeout; kiểm tra cấu hình `spring.session.timeout` hoặc policy của repository phù hợp, đừng giả định mọi session store đều hành xử giống embedded Tomcat.

**Sự kiện hết hạn không đồng nghĩa có một response tự động gửi tới browser.** Server không thể tự đẩy HTTP redirect tới tab đang đứng yên chỉ vì session vừa hết. Thông thường **request tiếp theo** mới phát hiện và buộc đăng nhập lại. Nếu UI cần đồng hồ đếm ngược hoặc thông báo trước khi hết phiên, đó là thêm một cơ chế UX và phải đồng bộ với quyết định **server-side**, không chỉ dùng một JavaScript timer.

### Đổi timeout cho từng session (fragment minh họa)

```java
HttpSession session = request.getSession(false);
if (session != null) {
    session.setMaxInactiveInterval(600); // 600 giây = 10 phút
}
```

Fragment này cần `HttpServletRequest request` và import Servlet `jakarta.servlet.http.HttpSession`; không phải chương trình độc lập. `setMaxInactiveInterval` điều chỉnh **idle timeout** của session đó; nó không tạo absolute TTL. Không đặt timer tùy ý theo dữ liệu người dùng nếu policy phải được server bảo vệ.

## 6. Khi hết phiên, request tiếp theo sẽ ra sao?

Tình huống phiên hết do không hoạt động:

1. Browser có thể **vẫn giữ** cookie `JSESSIONID` cũ nếu cookie chưa bị xóa/hết hạn bên browser.
2. Servlet container nhận session ID nhưng không tìm thấy một `HttpSession` còn hiệu lực.
3. Spring Security không thể khôi phục Authentication của phiên trước.
4. Nếu request là `GET /account` được bảo vệ bằng form login, ứng dụng thường chuyển người dùng về `/login` (302) hoặc xử lý theo `AuthenticationEntryPoint` được cấu hình.
5. Sau khi đăng nhập lại, server dùng session/ID hợp lệ mới; không được “tin” vào cookie cũ.

**Phân biệt:** “session hết hạn” (session cũ không còn hoạt động) khác “session ID không hợp lệ” (cookie cũ, cookie giả, session store bị xóa, logout, session ID không tồn tại). Trên request, hai nguyên nhân này đôi khi trông giống nhau. Không xây UX luôn khẳng định “bạn vừa hết thời gian” khi có thể là cookie không hợp lệ hoặc người dùng đã logout.

### invalidSessionUrl

Spring Security Servlet hỗ trợ xử lý khi request gửi session ID không hợp lệ:

```java
http.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid")
);
```

Đây là **fragment tùy chọn**, không có trong demo runnable mục 9. Cần endpoint/public route `/session-invalid` và phải bảo đảm không redirect vòng lặp; cookie cũ không bị xóa có thể khiến request tới đường xử lý cũng bị coi là invalid. `invalidSessionUrl` phù hợp với một số luồng Servlet nhưng nên kiểm thử với cách lưu session và Spring Security version thực tế.

**Đừng nhầm `invalidSessionUrl` với `expiredUrl` trong `maximumSessions(...)`:** `expiredUrl`/`SessionInformationExpiredStrategy` phục vụ việc session bị đánh dấu hết hiệu lực bởi **concurrent session control**, thường do vượt số phiên được phép. Một session hết vì **idle timeout** không phải cùng một sự kiện với session bị Spring Security “expire” do concurrency policy.

Với REST/API, redirect HTML thường không phải trải nghiệm phù hợp; cân nhắc trả 401 với response chuẩn và yêu cầu client xác thực lại. Với browser form login, redirect tới trang login thường dễ hiểu hơn.

### Trường hợp cần giữ dữ liệu form đang nhập

Nếu session hết khi user đang điền một form, đừng âm thầm gửi POST thay user khi session đã hết. Một ứng dụng tốt có thể:

- Cảnh báo sắp hết thời gian nếu thiết kế bảo mật cho phép.
- Lưu nháp không nhạy cảm ở nơi phù hợp và có kiểm soát.
- Yêu cầu đăng nhập lại trước khi thực hiện thao tác.
- Bảo đảm dữ liệu chưa được gửi không bị lộ qua URL/log.
- Xử lý CSRF token cũ sau reauthentication, không dùng lại một token đã bị vô hiệu hoặc không còn thuộc phiên hiện hành.

## 7. Logout đúng nghĩa trong Spring Security

**Đăng xuất chủ động** là hành động bảo mật: chấm dứt việc chấp nhận session hiện hành và dọn các thông tin liên quan. **Ẩn nút** hoặc đổi state frontend thành `loggedOut=true` không đủ.

Với Spring Security servlet và cấu hình mặc định có CSRF:

- `GET /logout` có thể hiển thị **trang xác nhận** logout.
- **`POST /logout` với CSRF token hợp lệ** kích hoạt quy trình logout.
- `LogoutFilter` xử lý logout trong security filter chain, trước phần lớn quyết định authorization HTTP; thông thường không cần tự viết controller logout.
- Các `LogoutHandler` mặc định thực hiện những thao tác cần thiết như **invalidate `HttpSession`**, xóa `SecurityContextHolder`/`SecurityContextRepository` liên quan, dọn saved CSRF token và remember-me authentication nếu đã cấu hình; logout success handler đưa user tới `/login?logout` khi dùng form login mặc định.
- Nếu cấu hình thêm `deleteCookies("JSESSIONID")`, server cố gắng gửi chỉ thị xóa cookie; cơ chế này có thể cần điều chỉnh cookie Path/Domain tùy servlet container và proxy. **Hiệu lực bảo mật chính là vô hiệu hóa session phía server**, không phụ thuộc cookie xóa được hay không.

Hình dung:

```text
POST /logout + cookie + CSRF token
              │
              ▼
       Security LogoutFilter
              │
        LogoutHandlers
          ├─ SecurityContextLogoutHandler
          │    ├─ invalidate current HttpSession
          │    ├─ clear Authentication/SecurityContext
          │    └─ clear stored SecurityContext as configured
          ├─ CsrfLogoutHandler (cleanup CSRF token)
          └─ remember-me handler (nếu dùng remember-me)
              │
              ▼
          LogoutSuccessHandler
              │
              └─ 302 Location: /login?logout
```

Một lời gọi tới `GET /logout` **không nên được coi là thao tác logout thật** khi CSRF đang bật. Nếu tắt CSRF, hành vi của GET/logout có thể khác; không tắt CSRF chỉ để làm được thao tác logout qua link GET.

### CSRF trên logout: vì sao POST quan trọng?

Browser có thể tự gửi cookie xác thực với request cross-site tùy `SameSite` và ngữ cảnh. Nếu logout thực hiện qua GET hoặc POST không kiểm tra CSRF, site khác có thể buộc người dùng đăng xuất hoặc dẫn tới side effect không mong muốn (*logout CSRF*).

Vì vậy, với browser session-cookie, nên dùng **POST /logout + CSRF token** và giữ cơ chế Spring Security mặc định. Với form login mặc định, Spring Security đã cung cấp phần giao diện tạo token. Với UI custom, bạn phải gửi token theo cấu hình `CsrfTokenRepository`/request handler đang dùng.

### Cần xóa gì khi logout?

| Thành phần | Hành động phù hợp |
| --- | --- |
| Session hiện hành trên server | Invalidate/delete để không thể dùng lại ID |
| `SecurityContext` | Clear ở request hiện tại và repository phù hợp |
| CSRF token liên quan session | Invalidate/clear để không dùng trạng thái cũ |
| Browser session cookie | Gửi chỉ thị xóa khi phù hợp; khớp Path/Domain |
| Remember-me cookie/token | Hủy/dọn theo cơ chế remember-me đã bật |
| Access token JWT tự chứa | Logout session web **không tự thu hồi** JWT đã phát |
| Refresh token / IdP SSO session | Cần quy trình revoke/federated logout riêng nếu có |
| Tab khác trên cùng browser profile | Nhận thông tin sau request tiếp theo; UI nên xử lý nhất quán |
| Phiên ở thiết bị khác | Không mặc nhiên bị logout khi chỉ hủy session hiện hành |

**Logout hiện hành ≠ logout toàn bộ thiết bị.** Nếu yêu cầu “Đăng xuất tất cả thiết bị”, cần một chính sách/khả năng quản lý session trung tâm hoặc token revoke phù hợp, không chỉ gọi `request.getSession().invalidate()` trên một request.

## 8. Bảo mật cookie và session khi triển khai thật

| Rủi ro | Biện pháp |
| --- | --- |
| Bị lấy session ID trên đường truyền | HTTPS toàn tuyến, cookie `Secure`, tránh downgrades |
| JavaScript đọc session cookie khi có XSS | `HttpOnly` giúp giảm trộm cookie bằng JS; vẫn cần chặn XSS |
| Request giả mạo từ trang khác | CSRF token, `SameSite`, kiểm tra Origin/Referer khi phù hợp |
| Session fixation | Đổi session ID sau login/đổi độ tin cậy; Spring Security có cơ chế session fixation protection |
| Session còn hiệu lực quá lâu | Idle timeout, absolute lifetime theo policy, step-up auth |
| Cookie tồn tại nhưng server session không còn | UX yêu cầu login lại; không khôi phục quyền từ cookie mồ côi |
| Quên hủy context khi tự viết logout | Dùng Spring Security `logout` DSL thay vì tự xóa biến |
| Rò rỉ ID/token vào log | Không log cookie, session ID, `Authorization` headers hoặc JWT |
| Session nằm trên một instance duy nhất | Session store chia sẻ (Spring Session Redis/JDBC) hoặc hạ tầng hỗ trợ rõ ràng |
| Quyền bị thu hồi nhưng session đang giữ authorities cũ | Thiết kế cập nhật/revalidate/expire session khi đổi role |

**Lưu ý cookie Path/Domain:** Nếu ứng dụng chạy sau reverse proxy hoặc trên đường dẫn con, việc xóa cookie phải sử dụng phạm vi đúng để browser chấp nhận. `deleteCookies("JSESSIONID")` không cam kết giải quyết mọi proxy/container; kiểm thử trong trình duyệt thực tế, tránh báo “logout lỗi” chỉ dựa vào còn thấy cookie khi session phía server đã bị hủy.

**Session fixation:** nếu session ID do kẻ tấn công cố định trước login mà không được đổi, có thể dẫn đến chiếm phiên sau xác thực. Spring Security có cấu hình session fixation protection trong luồng authentication; với Servlet 3.1+, đổi ID không nhất thiết hủy mọi thuộc tính của session. Kiểm tra behavior theo yêu cầu ứng dụng nếu bạn tự tùy biến authentication flow.

## 9. Ví dụ runnable: form login, idle timeout và logout có CSRF

Dự án sau dùng **Java 17+, Spring Boot 3.5.12, Spring Security 6.x, Gradle 8.4+**. Có một `SecurityFilterChain` bao phủ ứng dụng, HTTP form login, session Servlet 10 phút không hoạt động, một tài khoản demo, và logout tiêu chuẩn qua POST.

Demo gồm ba endpoint:

| Endpoint | Quyền | Ý nghĩa |
| --- | --- | --- |
| `GET /public` | Công khai | Chứng minh route không cần login |
| `GET /account` | Phải đăng nhập | Khôi phục user từ session |
| `GET /account/session-info` | Phải đăng nhập | Xem max inactive interval mà không lộ session ID |

`GET /login` và `GET /logout` được Spring Security cung cấp giao diện mặc định phù hợp; `POST /login` và `POST /logout` do Spring Security filters xử lý. Không tự tạo controller trùng các đường dẫn này.

### 9.1. Cấu trúc

```text
session-lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/sessionlifecycle/
    │   │   ├── SessionLifecycleApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── AccountController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/sessionlifecycle/
            └── SessionLifecycleTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'session-lifecycle-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.12'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot ở đây cần dependency ngoài JDK, vì vậy `gradle test`/`gradle bootRun` là cách chạy toàn bộ project; `javac`/`java` trần không có Spring classpath thì không biên dịch được. Đảm bảo Gradle 8.4+ tương thích, hoặc dùng Gradle Wrapper đã cấu hình phiên bản phù hợp.

### 9.2. Cấu hình timeout/cookie

**`src/main/resources/application.properties`**

```properties
server.servlet.session.timeout=10m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Cấu hình demo chạy qua HTTP localhost để dễ thử. **Không sao chép nguyên cách chạy HTTP sang production**: triển khai thực tế phải dùng HTTPS và cấu hình `Secure` cho session cookie. 10 phút ở đây là idle timeout, không phải cookie Max-Age hoặc 10 phút tính cố định từ login.

### 9.3. Ứng dụng chính

**`src/main/java/com/example/sessionlifecycle/SessionLifecycleApplication.java`**

```java
package com.example.sessionlifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
```

### 9.4. SecurityFilterChain: form login + logout tiêu chuẩn

**`src/main/java/com/example/sessionlifecycle/SecurityConfiguration.java`**

```java
package com.example.sessionlifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/account", "/account/session-info")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form.permitAll())
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            )
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}alice123")
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(alice);
    }
}
```

**Giải thích kỹ:**

1. `/public` đi qua HTTP authorization `permitAll()`; không có nghĩa bỏ qua toàn bộ security filters.
2. `/account` và `/account/session-info` đòi Authentication hợp lệ. Người dùng anonymous vào route này được chuyển đến trang login mặc định.
3. `anyRequest().denyAll()` chặn các endpoint không được liệt kê. `formLogin(form -> form.permitAll())` cấp quyền vào giao diện/cơ chế login chuẩn.
4. `logout` DSL sử dụng `LogoutFilter` và handlers tiêu chuẩn. `invalidateHttpSession(true)` hủy session hiện tại, `clearAuthentication(true)` dọn authentication liên quan; Spring Security cũng xử lý lưu trữ security context/CSRF theo cơ chế logout. `deleteCookies("JSESSIONID")` cố gắng xóa cookie browser ở scope thích hợp.
5. Không có `csrf().disable()`. Với cấu hình này, thao tác logout thực tế phải dùng **POST với CSRF token hợp lệ**. Spring Security tạo trang xác nhận khi GET /logout và có giao diện form login mặc định.
6. Session timeout **không nằm trong `HttpSecurity` của code này** vì đã được đặt tại `server.servlet.session.timeout=10m` cho Servlet container. `SessionCreationPolicy` không cần khai báo tùy tiện để form login sử dụng session theo luồng mặc định.
7. `{noop}` lưu password rõ **chỉ dùng trong bài thực hành trên máy cục bộ**. Không triển khai tài khoản này lên Internet/production; cần password encoder mạnh, storage và transport an toàn.

**Lưu ý về output login/logout:** sau login, browser có thể được chuyển về URL đã yêu cầu trước đó hoặc default success URL. Sau logout, cấu hình chủ động chuyển về `/login?logout`. Không giả định mọi lần POST /login thành công đều trả body text 200; đó thường là redirect.

### 9.5. Controller chỉ đọc user và timeout, không lộ session ID

**`src/main/java/com/example/sessionlifecycle/AccountController.java`**

```java
package com.example.sessionlifecycle;

import java.security.Principal;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/account")
    public String account(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/account/session-info")
    public String sessionInfo(Principal principal, HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "user=" + principal.getName() + ";session=absent";
        }

        return "user=" + principal.getName()
            + ";idleTimeoutSeconds=" + session.getMaxInactiveInterval();
    }
}
```

`request.getSession(false)` **không tạo mới** session chỉ để hiển thị thông tin; nếu không tồn tại, nó trả `null`. Với form login stateful thông thường, request đã xác thực sẽ có session, nhưng code vẫn xử lý `null` để tránh `NullPointerException` nếu cấu hình authentication thay đổi.

Endpoint chỉ trả username và số giây không hoạt động được cấu hình; không xuất `session.getId()` hoặc giá trị cookie. **Số giây là idle timeout của session**, không phải “thời gian còn lại” tính tới hết hạn.

### 9.6. Chạy ứng dụng và thao tác bằng browser

Cần **JDK 17+** và **Gradle 8.4+**. Tại thư mục `session-lifecycle-demo`:

```bash
gradle test
gradle bootRun
```

Nếu có Gradle Wrapper đúng version, dùng `./gradlew test` và `./gradlew bootRun` (Linux/macOS), hoặc `gradlew.bat test` và `gradlew.bat bootRun` (Windows).

**Trình tự thử:**

1. Mở `http://localhost:8080/public` → body **`public`**.
2. Mở `http://localhost:8080/account` khi chưa đăng nhập → trình duyệt thường được redirect tới `/login`.
3. Nhập username `alice` và password `alice123` trong form mặc định. Spring Security tạo/ghi nhớ session xác thực và trả response chuyển hướng.
4. Mở `http://localhost:8080/account` → body **`hello alice`**.
5. Mở `http://localhost:8080/account/session-info` → body dạng **`user=alice;idleTimeoutSeconds=600`** khi embedded container đã áp dụng cấu hình 10 phút như kỳ vọng. Con số có thể phản ánh cấu hình container thực tế nếu đã bị override.
6. Mở Developer Tools → Application/Storage → Cookies: có thể thấy session cookie mang tên `JSESSIONID` (tùy container, context path và thiết lập cookie); không sao chép giá trị cookie vào log hoặc báo cáo.
7. Thử mở `http://localhost:8080/logout` bằng browser: Spring Security hiển thị trang xác nhận logout nếu CSRF được bật. Xác nhận qua form sẽ gửi **POST /logout** có token hợp lệ.
8. Sau logout, mở lại `/account` → phải đăng nhập lại, vì session hiện hành đã bị hủy.

**Kiểm chứng thời gian chờ 10 phút:** đăng nhập, rồi **không gửi request nào sử dụng session** trong thời gian dài hơn 10 phút (nên chừa biên do container/cleanup), sau đó truy cập lại `/account`. Kỳ vọng cần login lại. Nếu UI/browser có polling hoặc tab khác liên tục gọi server với session, thao tác này không chứng minh idle timeout đã chạy vì nó có thể đang được gia hạn.

**Không đợi 10 phút trong unit test:** thời gian dọn session thực do container/store quyết định; test kiểm tra tính đúng của logout có thể dùng `MockMvc`, còn thời gian expiry thực nên dùng integration/environment test có clock/idle và session store phù hợp.

### 9.7. Kiểm chứng nhanh bằng curl

`curl` không tự hoàn tất form login có CSRF token, nên chỉ dùng những request dễ xác minh:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/account

# Thiếu CSRF token: không phải một thao tác login/logout hợp lệ
curl -i -X POST http://localhost:8080/logout
```

Kết quả dự kiến:

- `GET /public` → **200**, body `public`.
- `GET /account` khi anonymous → **302**, thường có `Location: /login`.
- `POST /logout` không kèm CSRF token → thường **403** khi CSRF mặc định đang bật. Trường hợp này **không chứng minh đã logout**.

Nếu muốn tự động hóa form login bằng HTTP client thật, phải lấy CSRF token/cookie từ trang login, gắn lại đúng cookie jar và gửi token theo cấu hình repository/handler. Không nên copy một CSRF token từ session cũ sang session mới hoặc bỏ CSRF chỉ để làm demo.

### 9.8. Bộ test MockMvc: phiên tái sử dụng và logout thực sự

**`src/test/java/com/example/sessionlifecycle/SessionLifecycleTests.java`**

```java
package com.example.sessionlifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLifecycleTests {

    @Autowired
    MockMvc mvc;

    private MockHttpSession loginAsAlice() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("alice").password("alice123")
            )
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);
        return session;
    }

    @Test
    void publicIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void successfulLoginCreatesReusableSession() throws Exception {
        MockHttpSession session = loginAsAlice();

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndSessionRemainsUsable()
            throws Exception {
        MockHttpSession session = loginAsAlice();

        mvc.perform(post("/logout").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/account").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));
    }

    @Test
    void validLogoutInvalidatesCurrentSession() throws Exception {
        MockHttpSession session = loginAsAlice();

        mvc.perform(post("/logout").session(session).with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        mvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutOfOneBrowserSessionDoesNotLogoutAnother()
            throws Exception {
        MockHttpSession sessionOne = loginAsAlice();
        MockHttpSession sessionTwo = loginAsAlice();

        mvc.perform(post("/logout").session(sessionOne).with(csrf()))
            .andExpect(status().is3xxRedirection());

        assertTrue(sessionOne.isInvalid());

        mvc.perform(get("/account").session(sessionTwo))
            .andExpect(status().isOk())
            .andExpect(content().string("hello alice"));
    }
}
```

**Tại sao test này phù hợp với bài học?**

- `formLogin()` từ `spring-security-test` dựng POST login kèm CSRF token hợp lệ; vì vậy test **không tắt CSRF**.
- `successfulLoginCreatesReusableSession` chứng minh session sau login có thể được dùng lại trong lời gọi khác.
- `logoutWithoutCsrfIsRejectedAndSessionRemainsUsable` chứng minh POST logout không có CSRF bị chặn, **không** làm người dùng đăng xuất.
- `validLogoutInvalidatesCurrentSession` kiểm tra redirect logout và đối tượng MockHttpSession đã invalidated. Không thử gắn lại một `MockHttpSession` đã invalidated vào request mới: mock Servlet API có thể ném exception; trình duyệt thật gửi cookie cũ rồi container quyết định ID đó không còn hợp lệ.
- `logoutOfOneBrowserSessionDoesNotLogoutAnother` cho thấy logout mặc định chỉ nhắm session hiện tại; session khác của cùng tài khoản không tự bị hủy.

**Giới hạn test:** `MockMvc`/`MockHttpSession` không tự mô phỏng đầy đủ đồng hồ dọn expired session, cookie store thật, TLS, SameSite browser, proxy hay cơ chế chia sẻ session Redis. Bộ test này **không chứng minh session được tự dọn đúng sau 600 giây wall-clock**; cần integration test trên container/session store thực để xác minh timeout.

## 10. Nâng cấp: kiểm soát phiên tuyệt đối và thao tác nhạy cảm

Một số ứng dụng cần chính sách nghiêm ngặt hơn idle timeout:

- **Absolute lifetime:** session phải hết sau 8 giờ kể từ login. Lưu thời điểm xác thực (trusted server time), đánh giá giới hạn ở mỗi đường vào phù hợp, hủy session/đòi login lại khi quá ngưỡng. Nếu store là Redis, có thể cần TTL tuyệt đối hoặc một guard tường minh; không chỉ trông vào idle TTL.
- **Step-up reauthentication:** yêu cầu nhập lại mật khẩu/MFA khi chuyển tiền hoặc đổi email, dù session vẫn hoạt động; ghi thời điểm xác thực gần nhất bằng nguồn tin cậy.
- **Concurrent session limit:** giới hạn số phiên cùng một principal, ví dụ khi yêu cầu “chỉ một thiết bị đang đăng nhập”. Cơ chế này cần session registry và theo dõi lifecycle đúng, nhất là khi dùng nhiều nodes; nên phân biệt “ngăn login phiên mới” với “làm phiên cũ expired”.
- **Global logout/forced logout:** cần quản lý toàn bộ sessions hoặc token state của user trong kho chung; chức năng logout mặc định của một request không tự làm điều đó.
- **Role change:** authorities có thể đã được lưu trong Authentication của session cũ. Khi quyền bị hạ, cần chiến lược làm mới/thu hồi session, không mặc định mọi session cập nhật ngay.

### Ví dụ fragment giới hạn số phiên đồng thời

```java
http.sessionManagement(session -> session
    .maximumSessions(1)
    .maxSessionsPreventsLogin(true)
);
```

Đây là **fragment**, không phải cấu hình đủ cho hệ thống phân tán. Nó minh họa ngăn đăng nhập phiên thứ hai khi đã đạt một session, chứ **không đặt idle timeout**. Trong ứng dụng thực cần cấu hình session registry, sự kiện destroy, principal equality và cách quản lý nhiều node/session store phù hợp. Tùy cấu hình, khi không chặn login mới, Spring Security có thể đánh dấu session cũ **expired**; đây là ngữ nghĩa khác idle timeout của container.

**Không trộn lẫn `expiredUrl` trong concurrent session control với `invalidSessionUrl` cho session ID không hợp lệ**. Hãy test riêng sự kiện nhiều thiết bị, request sau session idle timeout và logout chủ động.

## 11. Remember-me, JWT và SSO: vì sao tưởng đã hết phiên mà vẫn có thể đăng nhập?

### Remember-me khác với HttpSession

Spring Security có tính năng remember-me nếu **được bật và cấu hình**. Khi session đã hết, cookie remember-me hợp lệ có thể giúp tạo một Authentication mới và trải nghiệm giống “vẫn đăng nhập”. Điều này không có nghĩa session cũ chưa hết.

- Remember-me token/cookie có thời hạn và lifecycle riêng.
- Cần bảo vệ token, xem xét persistent token store, rotation, replay và revoke.
- Logout đúng bằng Spring Security có thể gọi remember-me cleanup handler khi chức năng đã được cấu hình.
- Với chức năng nhạy cảm, có thể yêu cầu **fully authenticated** thay vì chấp nhận remember-me authentication tùy policy.

### JWT/access token không bị hủy bởi HttpSession.invalidate()

Một ứng dụng browser đồng thời sử dụng OAuth2/OIDC hoặc phát access token cho API có nhiều loại trạng thái. `POST /logout` hủy session của ứng dụng **không tự** revoke JWT đã phát, refresh token hoặc session tại Identity Provider.

Ví dụ:

```text
Browser session (App A)        → đã logout
JWT access token (API B)       → có thể còn hợp lệ đến exp/revoke
IdP SSO browser session       → có thể vẫn đăng nhập
Refresh token                 → có thời hạn/revoke riêng
```

Nếu yêu cầu “đăng xuất toàn hệ thống”, cần thiết kế đăng xuất liên ứng dụng/federated logout (ví dụ OIDC RP-Initiated Logout hoặc Back-Channel Logout tùy IdP), hủy token/refresh token và logout session từng ứng dụng trong phạm vi được phép.

Không đồng nhất “xóa cookie ở tab này” với “mọi nơi đã mất quyền truy cập”.

## 12. Các tình huống thực tế và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Login thành công nhưng request sau lại yêu cầu login | Cookie không được gửi, session hết, đổi node thiếu shared store, cấu hình context repository | Kiểm tra Set-Cookie, Path/Domain, Secure/SameSite, session store và filter chain |
| User liên tục thao tác nhưng vẫn bị logout sau một mốc cố định | Có absolute TTL hoặc IdP/token policy | Phân biệt idle timeout với absolute lifetime; xem logs an toàn |
| User im lặng lâu nhưng vẫn dùng được | AJAX polling gia hạn phiên, remember-me, timeout khác dự kiến | Xem activity thực tế, max inactive interval, remember-me |
| Vừa logout đã vào lại được mà không nhập mật khẩu | Remember-me, IdP SSO hoặc token khác còn hợp lệ | Kiểm tra flow login lại và cookie/token còn tồn tại |
| Cookie JSESSIONID vẫn hiện sau logout | Cookie deletion không khớp Path/Domain, browser chưa xử lý, hoặc session bị hủy nhưng cookie còn | Kiểm tra session server không còn hiệu lực; không chỉ dựa cookie |
| POST /logout bị 403 | CSRF token thiếu/không hợp lệ | Kiểm tra token/session; dùng POST và CSRF |
| GET /logout hiện trang xác nhận | CSRF đang bật, đây là hành vi dự kiến | Xác nhận để gửi POST hợp lệ |
| API trả 401 sau khi browser logout | Authentication không còn; API có cơ chế credentials riêng | Phân biệt session, Basic/Bearer và security chains |
| Session hay mất khi scale nhiều server | Store riêng từng instance hoặc route/load balancer không giữ session | Dùng Spring Session / shared store hoặc chiến lược được chọn |
| User hạ role nhưng vẫn có quyền cũ | Authentication trong session vẫn có authorities cũ | Thiết kế revoke/refresh session khi đổi role |
| Điều hướng tới “session expired” liên tục | invalidSessionUrl + stale cookie/redirect loop | Xem cookie ID, logout cookie clearing, URL public và filter order |
| Timeout quá ngắn trong unit test không xảy ra | MockMvc không có timer cleanup container thật | Test trên embedded/live container và session store thực |

### Checklist bảo mật trước khi đưa vào production

1. Quyết định **idle timeout**, **absolute lifetime** và **khi nào bắt reauthentication** bằng yêu cầu nghiệp vụ, không dùng một con số cho tất cả.
2. Bảo vệ cookie: HTTPS, Secure, HttpOnly, SameSite/Path/Domain phù hợp.
3. Giữ **CSRF protection** cho form/session-cookie và logout; test đường POST hợp lệ và thiếu token.
4. Xác minh login có session fixation protection; session ID không bị log hay đưa vào URL.
5. Logout phải **invalidate server session và xóa SecurityContext**; cookie cleanup chỉ là phần bổ sung.
6. Kiểm tra phiên khác trên cùng tài khoản: logout một phiên hay toàn bộ, giới hạn concurrent sessions, truy vết thiết bị.
7. Nếu có remember-me, bearer token hoặc SSO, thiết kế vòng đời/revoke **riêng** từng loại.
8. Kiểm tra timeout và cookie trong browser thật trên môi trường tương đương production, cả sau load balancer.
9. Kiểm tra việc cập nhật role hoặc khóa tài khoản tác động đến session còn hiệu lực.
10. Logging/audit phải có đủ thông tin điều tra **mà không lộ token/session ID/password**.

## 13. Câu hỏi tự kiểm tra

**1.** Session có idle timeout 10 phút, user gửi request sử dụng session mỗi 5 phút. Session có nhất thiết hết sau 10 phút kể từ login không?

**Đáp án:** Không. Idle timeout thường tính từ lần session được sử dụng gần nhất. Nếu cần hết sau một mốc từ login, phải có absolute lifetime riêng.

**2.** Cookie có Max-Age 2 giờ thì server session chắc chắn còn 2 giờ?

**Đáp án:** Không. Browser giữ cookie lâu không buộc server session tồn tại; server có thể timeout/invalidate sớm hơn. Ngược lại, server session có thể còn dù browser đã xóa cookie, nhưng client thường không còn ID để truy cập nó.

**3.** Người dùng mở tab nhưng không tương tác. Server có chủ động gửi 302 khi phiên hết không?

**Đáp án:** Không tự phát một HTTP response khi không có request. Request tiếp theo mới thường bộc lộ việc session đã hết. UI timer chỉ là bổ sung, không thay quyết định server.

**4.** Với Spring Security mặc định còn CSRF, thao tác GET /logout có luôn đăng xuất ngay không?

**Đáp án:** Không. Spring Security thường hiển thị trang xác nhận để gửi POST /logout kèm CSRF token; không nên dùng GET làm hành động thay đổi trạng thái.

**5.** Vì sao POST /logout thiếu CSRF token thường trả 403?

**Đáp án:** CSRF filter chặn request thay đổi trạng thái không có token hợp lệ. Trong demo, session cũ vẫn được sử dụng sau POST bị chặn, chứng minh logout chưa thực thi.

**6.** Xóa cookie JSESSIONID ở frontend có chắc server đã hủy phiên không?

**Đáp án:** Không. Server session có thể vẫn tồn tại đến khi timeout và ID bị lộ trước đó có thể còn dùng được. Logout đúng cần invalidate session server.

**7.** Người dùng logout ở laptop. Có chắc session ở điện thoại cũng bị hủy?

**Đáp án:** Không. Logout mặc định nhắm session hiện hành. Muốn logout mọi thiết bị cần quản lý/thu hồi toàn bộ phiên của user theo cơ chế riêng.

**8.** Khi đã cấu hình `invalidSessionUrl`, session ID không hợp lệ có nghĩa chắc chắn quá idle timeout?

**Đáp án:** Không. ID có thể bị invalid do logout, cookie cũ, store bị xóa hoặc lý do khác. Không tự kết luận chính xác nguyên nhân chỉ từ một redirect.

**9.** `expiredUrl` trong concurrent sessions có giống `invalidSessionUrl` không?

**Đáp án:** Không. `expiredUrl` gắn với session bị đánh dấu expired do giới hạn số phiên; `invalidSessionUrl` xử lý request mang session ID không hợp lệ ở ngữ cảnh phù hợp.

**10.** Tại sao sau khi HttpSession hết, user đôi khi vẫn được đăng nhập lại mà không nhập password?

**Đáp án:** Nếu remember-me được bật hoặc IdP SSO vẫn còn session, có thể có cơ chế xác thực lại bằng token/cookie khác. Phiên cũ không nhất thiết còn sống.

**11.** JWT access token có tự mất hiệu lực khi browser logout khỏi ứng dụng web không?

**Đáp án:** Không mặc định. Cần xem token expiration, revocation/introspection và cơ chế logout SSO/resource server riêng.

**12.** Có thể dùng `MockMvc` để chứng minh container dọn session đúng ở giây thứ 600 không?

**Đáp án:** Không. `MockMvc` giúp test filter/login/logout/session dùng lại; việc idle timeout thực phụ thuộc container/store, nên cần integration test thực tế với khoảng thời gian hoặc cơ chế clock phù hợp.

## 14. Tóm tắt

- **Idle timeout** là thời gian không hoạt động; **absolute lifetime** là hạn tối đa không phụ thuộc hoạt động; **cookie lifetime** là thời hạn browser giữ cookie. Ba điều này **khác nhau**.
- Với form login stateful, browser thường mang **JSESSIONID**, server lưu phiên và `SecurityContext`. Phiên có thể hết do inactivity, bị invalidate hoặc bị chính sách concurrency làm mất hiệu lực.
- `server.servlet.session.timeout=10m` cấu hình thời gian không hoạt động cho Servlet session, không tự sinh absolute TTL hoặc tự định nghĩa chính sách reauthentication.
- **Logout đúng:** sử dụng `POST /logout` với CSRF token hợp lệ; Spring Security xử lý invalidate `HttpSession`, clear context/CSRF và redirect. Xóa cookie là một phần bổ sung, không phải biện pháp duy nhất.
- **Không đồng nhất** session hết hạn, session ID không hợp lệ, concurrency-expired session và logout chủ động.
- **Remember-me, JWT, refresh token và SSO** có vòng đời riêng; hủy một session web không tự thu hồi mọi thứ.
- Dùng **MockMvc** cho hành vi login/logout và **test thực trên Servlet container/store** cho idle expiry, cookie/path/TLS và session sharing.
- Bảo mật phiên cần kết hợp CSRF, HTTPS, cookie flags, session fixation protection, least privilege, thu hồi quyền và thiết kế đa thiết bị.

## 15. Tài liệu tham khảo chính thức

- Spring Security — Logout and Logout Handlers: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — Session Management, timeouts và invalid sessions: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — CSRF protection: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — Remember-me authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/rememberme.html
- Spring Security — Testing Form Login (MockMvc): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/form-login.html
- Spring Security — Testing Logout (MockMvc): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html
- Spring Security — Testing CSRF (MockMvc): https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Boot 3.5 — Servlet session configuration properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — System requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Session — Distributed session persistence: https://docs.spring.io/spring-session/reference/
