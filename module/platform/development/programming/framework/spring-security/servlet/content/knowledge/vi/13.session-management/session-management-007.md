# Phân biệt phiên hết hạn, phiên không hợp lệ và phiên bị thay thế

Trong **Spring Security dành cho ứng dụng Servlet**, người dùng có thể mất trạng thái đăng nhập vì nhiều lý do: HTTP session không còn tồn tại sau thời gian không hoạt động; browser gửi một session ID không được server chấp nhận; hoặc một lần đăng nhập mới đã khiến phiên cũ bị đánh dấu hết hiệu lực theo quy tắc giới hạn đăng nhập đồng thời. Ngoài ra, Spring Security còn **thay đổi session ID sau xác thực để chống session fixation**: hành động này cũng thường được gọi là “thay thế phiên” nhưng không đồng nghĩa với việc người dùng bị logout, timeout hay bị đăng nhập nơi khác đá ra.

Điểm quan trọng nhất của bài học: **timeout là nguyên nhân ở vòng đời session; invalid ID là trạng thái quan sát được của request; concurrency-expired là trạng thái được SessionRegistry đánh dấu; session-ID rotation là biện pháp bảo vệ khi login**. Các trạng thái này có thể dẫn tới cùng triệu chứng “phải đăng nhập lại”, nhưng không thể xử lý hoặc giải thích giống nhau.

Bài học sử dụng ngữ cảnh **Java 17+, Spring Boot 3.x, Spring Security 6.x, Servlet/MVC**. Ta sẽ tìm hiểu Servlet `HttpSession`, cookie `JSESSIONID`, `SessionRegistry`, `ConcurrentSessionFilter`, `InvalidSessionStrategy`, `SessionInformationExpiredStrategy`, `maximumSessions`, các handler redirect, chống session fixation, ví dụ cấu hình, kiểm thử và chẩn đoán. Hành vi chính xác phụ thuộc phiên bản Spring Security, filter chain, servlet container và việc ứng dụng có sử dụng Spring Session hay không.

## 1. Các khái niệm cần tách riêng

Một hệ thống đăng nhập stateful có nhiều thực thể:

- **Session ID**: chuỗi bí mật định danh phiên, thường được browser gửi dưới dạng cookie `JSESSIONID`. Nó giống một bearer secret: ai sở hữu được session ID hợp lệ có thể giả mạo yêu cầu của browser nếu không có cơ chế bảo vệ khác.
- **HttpSession**: dữ liệu phiên phía server. Nó có ID, thuộc tính, các timestamp và giới hạn thời gian không hoạt động; có thể nằm trong servlet container hoặc trong một session store bên ngoài.
- **SecurityContext**: chứa `Authentication` hiện tại, thường được nạp/lưu bởi một `SecurityContextRepository`. Một số cấu hình lưu context vào session, nhưng không phải mọi ứng dụng đều cần session.
- **SessionRegistry**: kho theo dõi principal, session ID và trạng thái phục vụ **concurrent session control**. Nó không thay thế chính session storage.
- **SessionInformation**: thông tin về một phiên mà registry biết, gồm trạng thái expired cho mục tiêu concurrency; cờ expired không phải idle-timeout của container.
- **Servlet request**: có thể báo `getRequestedSessionId()` và `isRequestedSessionIdValid()`, là những tín hiệu nhìn thấy ở thời điểm request, không phải nhật ký đầy đủ nguyên nhân session đã biến mất.

~~~text
Browser
  |
  | Cookie: JSESSIONID=S1
  v
Servlet container / Spring Session store
  |-- S1 tồn tại?    -> HttpSession và các attributes
  |-- S1 không có?   -> request mang ID không hợp lệ
  |
  +-> SecurityContextRepository
  |      -> nạp SecurityContext nếu có theo policy
  |
  +-> SessionRegistry (nếu cấu hình concurrent sessions)
         -> S1 thuộc principal nào?
         -> S1 có bị đánh dấu expired bởi concurrency policy?
~~~

Một session bị timeout có thể khiến **request kế tiếp** dùng cookie S1 bị xem là invalid; đó là hai lớp khái niệm liên quan nhau, không phải hai lý do song song độc lập.

## 2. Bảng đối chiếu bốn tình huống

| Thuật ngữ | Nguyên nhân / bản chất | Tín hiệu có thể quan sát | Xử lý Spring Security liên quan |
| --- | --- | --- | --- |
| **Phiên hết hạn do timeout** | Vượt idle timeout hoặc chính sách lifecycle ở container/session store | Session server biến mất; cookie cũ còn có thể được gửi | Request sau có thể trở thành anonymous, dẫn tới entry point hoặc invalid-session strategy nếu có |
| **Requested session ID không hợp lệ** | ID client gửi không tra ra một session server hợp lệ (có thể do timeout, logout, restart, ID lạ, rotation) | `isRequestedSessionIdValid() == false` ở request có requested ID | `InvalidSessionStrategy` / `invalidSessionUrl` trong chain thực thi phù hợp |
| **Phiên bị thay thế theo concurrent login** | Policy cho login mới và đánh dấu session cũ expired trong registry | `SessionInformation.isExpired() == true`; request cũ được concurrency filter phát hiện | `maximumSessions`, `ConcurrentSessionFilter`, `expiredUrl` |
| **Session ID được đổi sau login** | Bảo vệ chống session fixation | ID trước/sau xác thực khác nhau, session hợp lệ tiếp tục hoạt động | `SessionAuthenticationStrategy`, `sessionFixation(...changeSessionId())` |

Chữ **expired** xuất hiện cả ở idle timeout và `expiredUrl` nên rất dễ gây nhầm. Trong Spring Security concurrent-session management, `expiredUrl` thường là đích cho phiên đã **bị registry đánh dấu expired** vì policy số phiên, **không phải** trang thông báo chung cho mọi servlet timeout.

Một nguyên tắc để ghi log đúng: **không khẳng định lý do chỉ từ phản hồi HTTP 302 hoặc 401**. Redirect tới /login có thể đơn giản do request chưa xác thực; nó không chứng minh người dùng bị concurrency-expired.

## 3. Trạng thái 1: HttpSession hết hạn vì timeout

Servlet container/session store có thể hủy một `HttpSession` sau khoảng thời gian không hoạt động (idle timeout). Ví dụ với timeout 15 phút:

~~~text
10:00  Alice đăng nhập -> session S1 tồn tại
10:05  Alice yêu cầu GET /profile -> session S1 còn hoạt động
10:20+ Không còn tương tác trong khoảng thời gian idle timeout
       -> session store/container có thể xóa hoặc hết hạn S1
10:30  Browser gửi Cookie JSESSIONID=S1
       -> server không tìm được S1
       -> SecurityContext lưu trong S1 không còn để nạp
~~~

Thời điểm chính xác phụ thuộc servlet container, session store và chu kỳ cleanup. Đây không phải đồng hồ đếm cố định trên browser; browser có thể tiếp tục giữ cookie sau khi dữ liệu phía server hết hạn.

Ví dụ cấu hình Spring Boot:

~~~properties
server.servlet.session.timeout=15m
~~~

Giá trị này hướng tới Servlet session timeout. Nếu dùng Spring Session Redis/JDBC hoặc cấu hình session qua một nơi khác, cần đối chiếu chính sách TTL thực tế, cookie lifetime, hạ tầng và giá trị được framework nhận. Đừng mặc định đây là thời hạn hiệu lực tối đa của mọi access token, JWT hoặc tài khoản người dùng.

### Request sau timeout phản hồi gì?

- **Web form login**: request mới vào tài nguyên bảo vệ thường không còn authentication lưu trong session, có thể chuyển tới trang login bằng 302.
- **API JSON**: có thể trả 401 nếu entry point API được cấu hình như vậy.
- **Invalid-session handling**: khi request có requested session ID cũ và filter/strategy tương ứng được kích hoạt, có thể redirect hoặc trả lỗi đặc thù.
- **Không có cookie**: thường chỉ là một request mới chưa đăng nhập; khó phân biệt với người chưa từng login.

Session timeout thực sự là **sự kiện ở session store/container**. Nếu chỉ nhìn thấy S1 không tồn tại, ứng dụng chưa thể khẳng định nó đã hết hạn do không hoạt động; logout, hủy phiên từ admin, server restart hoặc cookie/ID sai cũng có thể cho trạng thái giống vậy. Muốn có reason code đáng tin, phải ghi nhận lifecycle event tại đúng nơi phát sinh.

### Timeout khác access token expiration

Bearer JWT có thể hết hạn do claim `exp` và resource server có thể trả 401 dù không dùng `HttpSession`. HTTP session timeout không tự thu hồi JWT stateless đã cấp trước đó, cũng không nên dùng `expiredUrl` để xử lý mọi bearer token lỗi.

## 4. Trạng thái 2: request mang session ID không hợp lệ

Session ID không hợp lệ được xác định tại thời điểm Servlet request đi vào server. Nguyên nhân bao gồm:

1. Session thật sự đã idle timeout.
2. User logout và server đã invalidate session.
3. Session bị admin hoặc ứng dụng chủ động thu hồi.
4. Server restart làm mất dữ liệu session in-memory.
5. Client gửi cookie lỗi, giả, bị cắt hoặc không thuộc session store này.
6. Session ID vừa được rotate khi login nhưng client vẫn gửi ID cũ.
7. Load balancer gửi request tới node không chia sẻ session data trong mô hình lẽ ra phải sticky/shared.
8. Đường dẫn Domain/Path của cookie bị cấu hình sai khiến browser gửi nhầm cookie.

Servlet API dùng để quan sát:

~~~java
// Fragment Java chạy trong Servlet, không phải chương trình JDK độc lập.
String id = request.getRequestedSessionId();
boolean valid = request.isRequestedSessionIdValid();
~~~

Nếu không có requested ID, `id` có thể là `null`. Nếu `valid=false`, **đừng** tự kết luận idle timeout. Session ID là thông tin nhạy cảm, không nên log trực tiếp trong request logs, metrics hoặc analytics.

### invalidSessionUrl và InvalidSessionStrategy

Với cấu hình Spring Security Servlet phù hợp:

~~~java
http.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid"));
~~~

Cấu hình này định hướng phản hồi khi **request đã trình bày ID không hợp lệ** và cơ chế phát hiện invalid session thực sự chạy. Cơ chế `InvalidSessionStrategy` có thể dùng cho response tùy biến:

~~~java
http.sessionManagement(session -> session
    .invalidSessionStrategy(myInvalidSessionStrategy));
~~~

`myInvalidSessionStrategy` là object/bean ứng dụng cung cấp; đây là fragment, không phải class đầy đủ. Nó có thể trả JSON 401, xóa cookie cũ hoặc chuyển hướng; phải tự thiết kế nội dung để không tiết lộ thông tin không thể chứng minh.

**Lưu ý riêng Spring Security 6:** `SessionManagementFilter` không mặc định hiện diện trong mọi cấu hình mới. Một số authentication mechanisms chủ động gọi `SessionAuthenticationStrategy` mà không dùng logic phát hiện ở `SessionManagementFilter`. Do đó chỉ khai báo `invalidSessionUrl(...)` chưa đủ để suy ra mọi URL/chain sẽ kích hoạt chiến lược; phải xem filter chain thực tế hoặc kiểm thử tích hợp đúng version.

### Tránh redirect vòng lặp

Nếu browser tiếp tục gửi cookie `JSESSIONID` sai, request vào chính trang `/session-invalid` vẫn có thể bị strategy chặn và redirect ngược tới `/session-invalid`. Để tránh:

- Đảm bảo trang báo lỗi là public và có quy tắc xử lý invalid cookie rõ ràng.
- Xóa cookie session cũ **đúng tên, Path, Domain, Secure** tương ứng hoặc thiết lập lại session hợp lệ theo policy.
- Nếu là API, ưu tiên trả status/error contract thay vì redirect HTML mà client không thể xử lý.
- Test trên browser và reverse proxy thật. Không giả định xóa cookie với `Path=/` sẽ xóa được cookie trước đó có `Path=/portal`.
- Không tạo session mới trên mọi request tới trang báo lỗi nếu điều đó gây lặp hoặc che mất bằng chứng debug.

### Logout cũng dẫn tới ID cũ không hợp lệ

Một `SecurityContextLogoutHandler` có thể invalidate session khi logout. Khi browser gửi lại cookie cũ, server có thể không còn nhận ID. Đây là hành vi chủ động kết thúc phiên, **không** phải timeout hay concurrency-expiration. Vì vậy thông điệp nên trung tính nếu ứng dụng không biết chính xác lý do.

## 5. Trạng thái 3: phiên bị loại bởi chính sách đăng nhập đồng thời

Giả sử tài khoản Alice chỉ được phép có **một phiên hoạt động tại một thời điểm**:

~~~text
Browser A                    SessionRegistry                  Browser B
  | Login Alice -> session S1     |                                |
  |-----------------------------> | register S1                    |
  |                               |                                |
  |                               |       Login Alice -> session S2|
  |                               | <------------------------------|
  |                               | mark S1 expired, register S2   |
  |                               |                                |
  | GET /private với S1           |                                |
  |-----------------------------> |                                |
  |       ConcurrentSessionFilter kiểm tra S1 đã expired         |
  |       xử lý logout / invalidate và expired-session strategy  |
  |<----------------------------- |                                |
  | 302 -> /session-replaced (nếu cấu hình redirect)               |
~~~

Điểm cốt lõi:

- `SessionRegistry` giữ `SessionInformation` cho các phiên mà cơ chế concurrent-session management biết đến.
- Khi giới hạn số phiên bị vượt và policy cho login mới, một phiên cũ có thể bị gọi `expireNow()`: **đánh dấu** nó expired trong registry.
- `ConcurrentSessionFilter` phát hiện trạng thái này trong request tiếp theo từ phiên cũ, xử lý logout/invalidation theo contract và gọi `SessionInformationExpiredStrategy` hoặc redirect đã cấu hình.
- Nếu browser A không gửi request mới, việc nhận biết “bị đá” ở UI A có thể chưa xảy ra ngay tại thời điểm B login. Muốn cập nhật giao diện A tức thì phải có kênh sự kiện riêng, không suy ra HTTP filter tự đẩy thông báo real-time.

### Hai chế độ maximumSessions

~~~java
// Cho phép login mới, đánh dấu một phiên cũ hết hiệu lực.
http.sessionManagement(session -> session
    .maximumSessions(1)
      .maxSessionsPreventsLogin(false)
      .expiredUrl("/session-replaced"));
~~~

~~~java
// Không cho login mới nếu đã đạt giới hạn session hoạt động.
http.sessionManagement(session -> session
    .maximumSessions(1)
      .maxSessionsPreventsLogin(true));
~~~

| Policy | Alice login ở A | Alice login tiếp ở B | Điều xảy ra với A |
| --- | --- | --- | --- |
| Không giới hạn | S1 hoạt động | S2 có thể hoạt động | S1 thường không bị đá do policy này |
| `maximumSessions(1)`, `maxSessionsPreventsLogin(false)` | S1 hoạt động | S2 được chấp nhận | S1 được đánh dấu expired, được xử lý khi A request lại |
| `maximumSessions(1)`, `maxSessionsPreventsLogin(true)` | S1 hoạt động | Login B bị từ chối theo policy | S1 tiếp tục hoạt động |
| S1 đã timeout và registry dọn đúng | S1 không còn | B login | Không nên kết luận “B đã đá A” |

Với `maxSessionsPreventsLogin(true)`, status hoặc trang lỗi cho browser B phụ thuộc loại authentication, provider/strategy và failure handler; không mặc định luôn là HTTP 403.

### expiredUrl không xử lý timeout thông thường

Khi `ConcurrentSessionFilter` nhận ra một session đã bị đánh dấu expired trong registry, cấu hình `expiredUrl("/session-replaced")` có thể đưa request tới trang này. Nó **không** phải trình xử lý chung cho browser gửi cookie của session đã bị container dọn do timeout. Session đã bị hủy thường không còn một phiên sống để registry/filter đánh dấu và xử lý theo cùng lối đi.

### Sự kiện session destroyed và HttpSessionEventPublisher

Để registry nắm được phiên nào đã bị hủy, với Servlet sessions và `SessionRegistryImpl` có thể cấu hình:

~~~java
@Bean
HttpSessionEventPublisher httpSessionEventPublisher() {
    return new HttpSessionEventPublisher();
}
~~~

Mã này là fragment trong class Spring `@Configuration`; cần import `org.springframework.security.web.session.HttpSessionEventPublisher` và `org.springframework.context.annotation.Bean`. Nó chuyển sự kiện Servlet session tới listener quan tâm để cleanup registry trong cấu hình tương ứng. Nếu sự kiện không được phát hoặc không đi tới registry, phiên đã timeout có thể vẫn bị tính là active, làm policy `maximumSessions` từ chối login oan.

Trong hệ thống **nhiều node**, registry in-memory không tự đồng bộ cả cluster. Khi dùng Spring Session, hãy tích hợp registry dựa trên session repository có khả năng phù hợp với distributed sessions và session events; đừng mặc định đăng ký `HttpSessionEventPublisher` là đủ để đồng bộ mọi node.

## 6. Một cách hiểu khác của “phiên bị thay thế”: đổi session ID khi login

Session fixation là tấn công trong đó kẻ xấu tìm cách ép nạn nhân sử dụng một session ID mà kẻ xấu đã biết trước. Sau khi người dùng login, nếu server tiếp tục dùng chính ID cũ ấy, kẻ xấu có thể tận dụng để truy cập phiên đã xác thực.

Spring Security có thể bảo vệ bằng `SessionAuthenticationStrategy`:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId()));
~~~

Diễn tiến minh họa:

~~~text
Trước khi login:
  Cookie: JSESSIONID=S-before (anonymous, phiên đã tồn tại)

POST /login thành công:
  SessionAuthenticationStrategy dùng changeSessionId()

Sau khi login:
  Cookie: JSESSIONID=S-after (authenticated, phiên hợp lệ)
~~~

ID S-before và S-after khác nhau; session hiện có thường được giữ các attributes phù hợp khi dùng `changeSessionId()`. Đây **không** phải Alice đã bị browser B thay thế, cũng không phải session hết hạn do không hoạt động.

Nếu browser tiếp tục gửi ID S-before sau rotation, request sau đó có thể báo invalid session ID. Để kết luận “đây là ID đã rotate”, cần dấu vết của **sự kiện rotation**, không chỉ `isRequestedSessionIdValid()==false`.

Trong một custom `AuthenticationFilter` hoặc controller tự triển khai login, phải xác minh session fixation strategy thật sự được thực hiện sau authentication. Không suy ra mọi authentication mechanism đều tự động chạy các strategies của form login.

### So sánh hai dạng “thay thế”

| Tiêu chí | Session ID rotation | Concurrent-session replacement |
| --- | --- | --- |
| Kích hoạt | Chính browser đang login | Browser/session khác login cùng principal và vượt policy |
| Thay đổi | Định danh của phiên khi login | Trạng thái của phiên cũ trong registry |
| Mục tiêu | Chống session fixation | Giới hạn số phiên đồng thời |
| Tài khoản cũ bị logout? | Không phải ý nghĩa của thao tác này | Có thể bị logout/invalidate khi request lại |
| API liên quan | `sessionFixation(...changeSessionId())` | `maximumSessions`, `SessionRegistry`, `ConcurrentSessionFilter` |

Cả hai cơ chế có thể chạy trong cùng một lần login B: ID của B được rotate và session A bị đánh dấu expired. Do đó không được gộp chúng thành một nguyên nhân.

## 7. Các thành phần Spring Security và trách nhiệm chính

| Thành phần | Khi nào liên quan | Không nên hiểu nhầm |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Nạp/làm sẵn context cho request, dọn holder khỏi thread sau request | Không tự chứng minh session đã timeout |
| `SecurityContextRepository` | Đọc/lưu context theo session hoặc repository khác | Không phải SessionRegistry concurrency |
| `AuthenticationEntryPoint` | Request chưa được xác thực nhưng cần authentication | Redirect /login không đồng nghĩa concurrency-expired |
| `SessionManagementFilter` | Khi được cấu hình trong chain, có thể phát hiện requested invalid session ID và gọi strategy | Không mặc định có mặt trong mọi Spring Security 6 chain |
| `InvalidSessionStrategy` | Request có invalid session ID, phản hồi 302/401/JSON | Không luôn phân biệt timeout với logout/ID giả |
| `SessionRegistry` | Ghi nhận principal/sessionInfo, cờ expired | Không phải Servlet session store |
| `ConcurrentSessionFilter` | Kiểm tra sessionInfo đã expired khi request tới | Không phát thông báo realtime tới browser không gửi request |
| `SessionInformationExpiredStrategy` | Handler phản hồi khi concurrency-expired | Không phải handler cho mọi timeout |
| `SessionAuthenticationStrategy` | Việc cần làm sau login: ID rotation, registration, concurrency | Không tự xác minh username/password |
| `LogoutHandler` | User logout hoặc filter concurrency xử lý theo policy | Không phải servlet timeout trong mọi trường hợp |

Một application có nhiều `SecurityFilterChain`. Mỗi request đi qua chain khớp đầu tiên; một API chain chỉ dùng Bearer token có thể **không** sử dụng các filter session/concurrency giống web form login chain. Khi phân tích log, phải biết request thuộc chain nào và filter nào thực sự đã chạy.

### Các URL xử lý sự kiện khác nhau

~~~java
// Fragment DSL; các URL có ý nghĩa khác nhau.
.formLogin(form -> form
    .defaultSuccessUrl("/private"))
.sessionManagement(session -> session
    .invalidSessionUrl("/session-invalid")
    .maximumSessions(1)
      .maxSessionsPreventsLogin(false)
      .expiredUrl("/session-replaced"))
~~~

- `defaultSuccessUrl`: đích sau **login thành công**.
- `invalidSessionUrl`: dành cho **invalid requested session ID** nếu strategy được áp dụng.
- `expiredUrl`: dành cho **session bị concurrency policy đánh dấu expired**.
- `failureUrl`: dành cho **login thất bại** (credential sai, provider từ chối).
- `logoutSuccessUrl`: dành cho **logout thành công**.
- Session fixation ID change **không cần** một trang lỗi redirect.

## 8. Ví dụ Spring Boot 3/Spring Security 6 cấu hình session

Ví dụ sử dụng form login với một user demo, timeout 15 phút và giới hạn một phiên hoạt động. Đường dẫn `/session-replaced` và `/session-invalid` là trang công khai. Khi dùng trong môi trường thật phải bổ sung logic dọn cookie và chống redirect loop.

### 8.1. Dependencies Maven

Trong `pom.xml` của project đã có Spring Boot parent/BOM phù hợp:

~~~xml
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
~~~

Không ghép ngẫu nhiên version Spring Security khác BOM. Class Spring phụ thuộc classpath, **không thể chạy bằng javac JDK thuần**; ví dụ Java thuần độc lập được đặt ở mục 11.

### 8.2. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
# Với production dùng HTTPS, thiết lập secure cookie theo deployment:
# server.servlet.session.cookie.secure=true
~~~

### 8.3. Main class

Tạo `src/main/java/com/example/session/SessionLifecycleApplication.java`:

~~~java
package com.example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig

Tạo `src/main/java/com/example/session/SecurityConfig.java`:

~~~java
package com.example.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.session.HttpSessionEventPublisher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-only-pass"))
                .roles("USER")
                .build());
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/session-invalid",
                                 "/session-replaced").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .defaultSuccessUrl("/private")
                .permitAll())
            .sessionManagement(session -> session
                .invalidSessionUrl("/session-invalid")
                .sessionFixation(fixation -> fixation.changeSessionId())
                .maximumSessions(1)
                    .maxSessionsPreventsLogin(false)
                    .expiredUrl("/session-replaced"));
        return http.build();
    }
}
~~~

Giải thích:

1. `formLogin` tạo cơ chế đăng nhập form, có thể dùng trang GET /login mặc định. Demo user/password chỉ dùng **cục bộ**, tuyệt đối không hardcode credentials production.
2. `maximumSessions(1)` chọn giới hạn một phiên cho mỗi principal registry nhận biết.
3. `maxSessionsPreventsLogin(false)` cho phép login B, đánh dấu phiên A hết hiệu lực.
4. `expiredUrl("/session-replaced")` xử lý request A khi concurrency filter thấy phiên đã bị đánh dấu expired.
5. `invalidSessionUrl("/session-invalid")` diễn tả nhánh invalid requested ID, chỉ có hiệu lực khi cơ chế invalid-session detection được kích hoạt đúng trong chain.
6. `sessionFixation(...changeSessionId())` bảo vệ ID khi login thành công; không phải chính sách đá session A.
7. `HttpSessionEventPublisher` hỗ trợ cleanup registry theo sự kiện vòng đời Servlet session.

**Lưu ý:** Với một số cấu hình Spring Security 6 hoặc custom authentication filter, invalid-session strategy có thể không chạy như kỳ vọng nếu `SessionManagementFilter` vắng mặt. Cần kiểm tra filter chain và integration test, không khẳng định mọi browser sẽ được redirect tới /session-invalid chỉ dựa vào snippet.

### 8.5. Các endpoint

Tạo `src/main/java/com/example/session/SessionPages.java`:

~~~java
package com.example.session;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionPages {
    @GetMapping("/")
    public String home() {
        return "home";
    }

    @GetMapping("/private")
    public String privatePage() {
        return "private";
    }

    @GetMapping("/session-invalid")
    public String invalid() {
        return "Session ID is no longer valid";
    }

    @GetMapping("/session-replaced")
    public String replaced() {
        return "Session ended by concurrent-login policy";
    }
}
~~~

Hai trang thông báo ở đây chỉ trả text, không cần Authentication; sản phẩm thật nên dùng view/JSON phù hợp, có chiến lược xử lý cookie stale và không tiết lộ thông tin không có bằng chứng.

### 8.6. Thử bằng hai cửa sổ độc lập

Chạy với Maven Wrapper/JDK phù hợp:

~~~bash
./mvnw spring-boot:run
~~~

1. Mở browser profile A, vào `/private` và đăng nhập `alice`. Xác nhận truy cập nội dung private.
2. Mở browser profile B độc lập (không chia sẻ cookie jar), login cùng `alice`.
3. Khi B được chấp nhận, quay lại A và **gửi request mới** tới `/private`. Với concurrency policy/registry/filter hoạt động, A được xử lý theo expired strategy và có thể bị redirect tới `/session-replaced`.
4. B vẫn truy cập được nội dung riêng.
5. Đổi sang `maxSessionsPreventsLogin(true)` trong test profile rồi lặp lại: B sẽ bị từ chối login mới khi A còn active.
6. Thử cookie stale sau logout/session timeout: nếu invalid session handler hoạt động, có thể tới `/session-invalid`. Quan sát có redirect loop không.
7. Kiểm tra ID session trước/sau lần login hợp lệ (không công khai ID) để xác minh session fixation protection.

**Hai tab trong cùng profile không phải hai phiên độc lập** vì browser thường chia sẻ cookie. Dùng hai profiles/cửa sổ private khác nhau hoặc hai HTTP clients có cookie jars riêng.

## 9. Kiểm thử MockMvc và giới hạn mô phỏng

MockMvc cho phép test đường form login với hai `MockHttpSession` độc lập. Đây là kiểm thử integration của Spring Security filter chain, **không** chứng minh một Redis/session store production hết hạn theo thời gian đúng như cấu hình.

### 9.1. Test concurrent login

Tạo `src/test/java/com/example/session/ConcurrentLoginTest.java`:

~~~java
package com.example.session;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConcurrentLoginTest {
    @Autowired MockMvc mvc;

    @Test
    void secondLoginExpiresPriorSession() throws Exception {
        MockHttpSession browserA = new MockHttpSession();
        MockHttpSession browserB = new MockHttpSession();

        mvc.perform(post("/login").session(browserA).with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/private").session(browserA))
            .andExpect(status().isOk());

        mvc.perform(post("/login").session(browserB).with(csrf())
                .param("username", "alice")
                .param("password", "demo-only-pass"))
            .andExpect(status().is3xxRedirection());

        // Request tiếp theo của A mới biểu lộ trạng thái expired.
        mvc.perform(get("/private").session(browserA))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/session-replaced"));

        mvc.perform(get("/private").session(browserB))
            .andExpect(status().isOk());
    }
}
~~~

Các assertion trên là **kỳ vọng cho cấu hình minh họa và Spring Security filter/registry hoạt động tương thích**. Nếu test thất bại, trước tiên kiểm tra registration của session trong registry, request matcher/chain, policy B, session ID rotation, lifecycle events và cách MockMvc mô phỏng session. Không bỏ test chỉ vì hiện tượng của container và mock khác nhau.

Test concurrency không nên chạy song song với test khác cùng username và registry mà không reset trạng thái. Tốt nhất dùng isolated application context, test principal riêng hoặc cleanup state theo thiết kế.

### 9.2. Kiểm thử idle timeout như thế nào?

Đừng dùng `Thread.sleep(15 * 60 * 1000)` trong MockMvc và coi đó là phép thử đáng tin: mock sessions không mặc nhiên vận hành scheduler/TTL giống embedded container hoặc distributed store. Cách tốt hơn:

- Unit test `InvalidSessionStrategy` để kiểm tra status, body, cookie cleanup và không redirect loop.
- Integration test với **embedded servlet container/session store thật**, profile timeout ngắn, request sequence và cookie jar thật.
- Test riêng concurrency expiration bằng hai sessions.
- Test session fixation bằng quan sát session ID được rotate sau login, không log giá trị.
- Test browser thực cho cookie Path/Domain/SameSite/Secure, đặc biệt sau logout và invalid cookie.

### 9.3. Cookie bogus trong MockMvc chưa chắc đủ

Gửi header `Cookie: JSESSIONID=bogus` với MockMvc không nhất thiết khiến mock request có `getRequestedSessionId()` và `isRequestedSessionIdValid()` giống servlet container thật. Vì vậy không nên suy luận “MockMvc đã gửi cookie bogus thì invalidSessionUrl bắt buộc phải chạy”. Khi muốn chứng minh invalid requested ID, dùng container thật hoặc test strategy trực tiếp với mock request được thiết lập đủ thuộc tính.

### 9.4. @WithMockUser không chứng minh session concurrency

`@WithMockUser` có thể đặt Authentication đã có sẵn lên thread test. Nó hữu ích cho authorization, nhưng không tự tạo hai browser sessions/login theo `SessionAuthenticationStrategy`. Bài toán “browser B đá browser A” cần đi qua luồng authentication và đăng ký registry thực tế.

## 10. Khi nào nên trả 302, 401, 403?

Không có ánh xạ duy nhất giữa session reason và HTTP status:

- Web form login thường dùng `302 Location: /login` cho request thiếu authentication.
- API không sử dụng browser redirect thường trả `401 Unauthorized` và JSON/error contract.
- `403 Forbidden` thường phản ánh user đã xác thực nhưng thiếu quyền, hoặc POST bị CSRF filter từ chối; không nên coi mọi 403 là session expiration.
- Concurrency-expired có thể dùng redirect tới `expiredUrl`, hoặc custom `SessionInformationExpiredStrategy` trả JSON/401.
- Browser B bị từ chối login vì đạt maximumSessions có thể qua authentication failure handling, không bảo đảm luôn là 401/403 cố định.

Không ghi thông điệp “Có người khác đã đăng nhập vào tài khoản của bạn” chỉ vì thấy một 401. Nếu ứng dụng cần thông báo nguyên nhân cụ thể, phải lấy reason code từ event/concurrency handler tin cậy, không tự suy đoán từ cookie hoặc URL.

### Xử lý trang báo lỗi cho an toàn

Các trang `/session-invalid` và `/session-replaced` nên public. Cần kiểm tra invalid cookie đã được dọn hoặc strategy có cơ chế bỏ qua đúng route để tránh vòng lặp. Một custom session strategy trả JSON có thể rõ ràng hơn cho SPA; nhưng không được tiết lộ session ID, cookie, password, principal hay internal state trong response.

### Logout khác timeout và session bị thay thế

Logout chủ động là một hành động có chủ đích. Có thể invalidate session, xóa authentication và cookie; nó không phải idle timeout. Sau logout, nếu client gửi lại JSESSIONID cũ, ID có thể invalid. Đừng dùng `expiredUrl` để đại diện cho cả logout.

### RequestCache và deep links

Nếu request bị chuyển sang login, Spring Security có thể lưu request trong `RequestCache`. Khi session cũ hết hạn, saved request cũng có thể mất. Khi người dùng login lại, không tự tin một tham số `next` tùy ý từ client để redirect ra ngoài; dùng target đã được kiểm soát. Redirect không cấp quyền truy cập: request mới vẫn phải qua authorization.

## 11. Java 17 độc lập: nhận diện các tín hiệu server biết

Chương trình sau **chạy được chỉ bằng JDK 17**, mô phỏng quyết định dựa trên: có requested session ID không, server còn session không, registry đã đánh dấu concurrency expired không và có sự kiện ID rotation tin cậy không.

Đặc biệt nó **không cố phân biệt timeout với ID tự bịa** nếu cả hai đều chỉ cho cùng tín hiệu “lookup session không thành công”. Đây là bài học trọng tâm về giới hạn của quan sát.

Lưu tệp `SessionStatusDecisionDemo.java`:

~~~java
public class SessionStatusDecisionDemo {

    record Snapshot(boolean hasRequestedId,
                    boolean serverSessionExists,
                    boolean registryExpired,
                    boolean idWasRotated) {}

    static String classify(Snapshot s) {
        if (s.idWasRotated()) {
            return "ROTATED_ID_NOT_TIMEOUT";
        }
        if (!s.hasRequestedId()) {
            return "NO_SESSION_ID";
        }
        if (!s.serverSessionExists()) {
            return "INVALID_OR_EXPIRED_UNKNOWN_REASON";
        }
        if (s.registryExpired()) {
            return "CONCURRENCY_EXPIRED";
        }
        return "ACTIVE";
    }

    public static void main(String[] args) {
        System.out.println("new: " + classify(
            new Snapshot(false, false, false, false)));
        System.out.println("stale: " + classify(
            new Snapshot(true, false, false, false)));
        System.out.println("unknown-id: " + classify(
            new Snapshot(true, false, false, false)));
        System.out.println("superseded: " + classify(
            new Snapshot(true, true, true, false)));
        System.out.println("rotation: " + classify(
            new Snapshot(true, true, false, true)));
        System.out.println("active: " + classify(
            new Snapshot(true, true, false, false)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SessionStatusDecisionDemo.java
java SessionStatusDecisionDemo
~~~

Stdout **chính xác**:

~~~text
new: NO_SESSION_ID
stale: INVALID_OR_EXPIRED_UNKNOWN_REASON
unknown-id: INVALID_OR_EXPIRED_UNKNOWN_REASON
superseded: CONCURRENCY_EXPIRED
rotation: ROTATED_ID_NOT_TIMEOUT
active: ACTIVE
~~~

Hàm `classify` không phải Spring API. Đó là mô hình JDK đơn giản nhằm chỉ ra: `stale` sau timeout và `unknown-id` chưa bao giờ tồn tại **không thể phân biệt nếu chỉ biết lookup thất bại**. Muốn phân loại chính xác phải thu thập lifecycle event, audit hoặc trạng thái registry do server quản lý, không được lấy request body/header do client tự gửi làm bằng chứng.

## 12. Chẩn đoán sự cố trong production

Khi người dùng báo “tôi bị đá khỏi hệ thống”, nên điều tra:

1. **Request thuộc loại authentication nào?** Form login/session, HTTP Basic, OAuth2 login hay stateless Bearer JWT? Nếu không dựa session, đừng debug SessionRegistry trước.
2. **Có requested session ID không?** Không có cookie khác với cookie cũ sai. Tránh log giá trị ID.
3. **Server có tìm thấy HttpSession không?** Kiểm tra TTL, session store, load balancer, restart và cookie attributes.
4. **Có event timeout/hủy session không?** Chỉ dựa trên event đáng tin mới kết luận “idle timeout”.
5. **SessionRegistry biết phiên đó không?** Nếu registry có `SessionInformation.isExpired()` và policy concurrency đã đánh dấu, đây là dấu hiệu “bị thay thế” có cơ sở.
6. **maxSessionsPreventsLogin đang true hay false?** Cần phân biệt từ chối login mới và kick session cũ.
7. **Có HttpSessionEventPublisher/Spring Session integration đúng không?** Stale registry entries có thể làm sai việc đếm active sessions.
8. **Có session fixation rotation sau login không?** ID thay đổi có thể là biện pháp an toàn bình thường.
9. **Request đang đi qua SecurityFilterChain nào?** Những filter như `SessionManagementFilter` hoặc `ConcurrentSessionFilter` có chạy không?
10. **Response ai tạo?** AuthenticationEntryPoint, InvalidSessionStrategy, SessionInformationExpiredStrategy, AccessDeniedHandler hay failure/logout handler?
11. **Có redirect loop không?** Kiểm tra cookie path/domain và trang báo lỗi public.
12. **Nhiều node?** Một registry in-memory có thể không nhìn thấy session trên node khác; cần distributed session coordination thích hợp.
13. **Test lại với hai cookie jars**; tránh hai tabs dùng cùng cookie khiến kết luận sai.

Ví dụ reason codes do **ứng dụng tự định nghĩa**, không phải enum Spring Security có sẵn:

~~~text
SESSION_IDLE_TIMEOUT
SESSION_ID_INVALID
SESSION_CONCURRENCY_EXPIRED
SESSION_ID_ROTATED
USER_LOGOUT
SESSION_REVOKED_BY_ADMIN
~~~

Chỉ phát sự kiện `SESSION_IDLE_TIMEOUT` khi có chứng cứ timeout từ session store/lifecycle; `SESSION_ID_INVALID` chỉ phản ánh request và không gán bừa nguyên nhân. Khi cần correlate, dùng request ID và metadata an toàn; **không log session cookie, raw session ID, JWT hoặc SecurityContext chứa credentials**.

## 13. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách làm |
| --- | --- | --- |
| “expiredUrl cho tất cả phiên timeout” | Trang concurrency không chạy khi idle timeout | Dùng invalid-session/entry point tùy ngữ cảnh |
| “invalidSessionUrl chứng minh idle timeout” | Gán sai nguyên nhân cho logout/ID giả/rotation | Thông báo trung tính nếu không có lifecycle event |
| “isRequestedSessionIdValid=false = bị đá bởi login B” | Nhầm tín hiệu request với registry policy | Kiểm tra SessionRegistry/concurrency event |
| “Đổi JSESSIONID sau login nghĩa là login khác đã thay thế” | Nhầm bảo vệ fixation với concurrent login | Phân biệt session ID rotation |
| “maximumSessions(1) luôn cấm login mới” | Sai UX/bảo mật kỳ vọng | Chọn `maxSessionsPreventsLogin` theo policy |
| “Hai tab browser là hai session khác nhau” | Test concurrent login sai | Hai profiles/cookie jars độc lập |
| “RegistryExpired đồng nghĩa đã hủy session ngay” | Hiểu sai thời điểm filter xử lý | Test request tiếp theo của phiên cũ |
| “SessionRegistryImpl tự đồng bộ tất cả node” | Giới hạn session bị bỏ qua giữa node | Dùng registry/store phù hợp cluster |
| “Cookie cũ tự hết khi server xóa session” | Stale cookies gây lỗi/loop | Cookie invalidation đúng Path/Domain |
| “Logout hay invalidSessionStrategy đều như timeout” | Thông báo audit sai | Reason code tách biệt theo sự kiện |
| “JWT hết hạn thì cần ConcurrentSessionFilter” | Trộn token validation với HttpSession | Xử lý bearer auth độc lập |
| “MockMvc chắc chắn mô phỏng timeout thực” | Test yếu hoặc thất bại giả | Embedded server/session store integration |
| “Trang expired vẫn cần authentication cũ” | Redirect loop hoặc bị 401/302 liên tiếp | Trang thông báo công khai, cookie cleanup |
| “401 luôn là timeout” | Chẩn đoán nhầm password/token/session | Xem entry point, provider và logs an toàn |

## 14. Bài tập tự kiểm tra

**Câu 1.** Alice login trên browser A, không hoạt động quá timeout. Sau đó browser gửi cookie cũ và server không thấy session. Có thể kết luận chắc Alice bị browser B đá không?

**Đáp án:** Không. Server thấy requested ID không còn hợp lệ; nếu có event timeout đáng tin mới nói rõ idle timeout. Không có dữ kiện nào chứng minh policy concurrency đã thay thế.

**Câu 2.** Alice login ở A và B, `maximumSessions(1).maxSessionsPreventsLogin(false)`. B thường được nhận hay bị chặn?

**Đáp án:** B được nhận; registry có thể đánh dấu phiên A expired theo chính sách. Khi A gửi request mới, ConcurrentSessionFilter xử lý theo expired-session strategy.

**Câu 3.** Thay thành `maxSessionsPreventsLogin(true)`. A bị đá không?

**Đáp án:** Khi A còn active và giới hạn đã đạt, B bị từ chối login mới theo policy; A tiếp tục hoạt động nếu không có nguyên nhân khác khiến nó mất hiệu lực.

**Câu 4.** Một session ID đổi sau form login thành công. Có phải timeout không?

**Đáp án:** Không. Có thể là session fixation protection `changeSessionId()`. ID mới của cùng hành trình xác thực được dùng để hạn chế session fixation; không cần báo “phiên hết hạn”.

**Câu 5.** Browser gửi `JSESSIONID=bogus` chưa từng tồn tại và nhận 302 tới /session-invalid. Có thể biết đây là timeout bao lâu không?

**Đáp án:** Không. ID chưa từng tồn tại cũng có thể được coi invalid. Strategy chỉ có tín hiệu ID không hợp lệ; muốn nói thời gian timeout cần dữ liệu server tin cậy khác.

**Câu 6.** Vì sao có thể xảy ra redirect loop tới /session-invalid?

**Đáp án:** Browser tiếp tục gửi cookie invalid vào chính trang /session-invalid, strategy lại redirect. Cần xử lý public route và cookie cleanup đúng Path/Domain, không tin rằng permitAll một mình giải quyết mọi trường hợp.

**Câu 7.** API dùng JWT Bearer, token hết hạn, server trả 401. Có nên cấu hình expiredUrl để xử lý?

**Đáp án:** Không nhất thiết và thường không đúng. JWT token expiration thuộc bearer authentication/resource server, không phải SessionRegistry concurrency-expiration của HTTP sessions.

**Câu 8.** App dùng hai nodes với session store Redis chung, nhưng SessionRegistryImpl nằm trong RAM mỗi node. Có thể dựa vào maximumSessions để giới hạn toàn cluster không?

**Đáp án:** Không được mặc định. Registry/cleanup phải được tích hợp với distributed session repository và events phù hợp; registry in-memory của một node không tự thấy mọi session trên node khác.

**Câu 9.** Test dùng hai tab chung browser, khi tab B login lại thì tab A vẫn thấy đăng nhập. Có chứng minh maximumSessions không hoạt động không?

**Đáp án:** Không. Hai tab thường chung cookie, có thể là một session duy nhất. Test bằng hai profiles hoặc hai HTTP clients với cookie jars độc lập.

**Câu 10.** Một response 403 xảy ra sau POST login. Có thể kết luận session timeout không?

**Đáp án:** Không. Có thể CSRF filter chặn POST, authorization từ chối, hoặc chính sách riêng. Kiểm tra filter nào tạo response trước khi xác định nguyên nhân.

## 15. Checklist áp dụng

- [ ] Xác định hệ thống dùng HTTP session, Spring Session hay Bearer JWT; không dùng session handlers cho token lifecycle khác.
- [ ] Hiểu idle timeout và cookie lifetime là hai phạm vi khác nhau, tránh suy đoán nguyên nhân chỉ từ cookie.
- [ ] Phân biệt **timeout**, **invalid requested ID**, **concurrency expired** và **fixation ID rotation** trong event/UX.
- [ ] Kiểm tra `invalidSessionUrl/InvalidSessionStrategy` có filter thực thi trong Spring Security 6 chain đang dùng.
- [ ] Cấu hình `maximumSessions` + `maxSessionsPreventsLogin` theo yêu cầu; không bỏ qua lựa chọn true/false.
- [ ] Đảm bảo `ConcurrentSessionFilter`/SessionRegistry hoạt động, session destroyed events được phản ánh đúng.
- [ ] Với multi-node, sử dụng distributed registry/session store integration tương thích; tránh registry cục bộ cho policy toàn cluster.
- [ ] Bật session fixation protection phù hợp, đặc biệt trong custom authentication flow.
- [ ] Dọn cookie invalid đúng Path/Domain/Secure/SameSite; trang báo lỗi công khai và không redirect loop.
- [ ] Test hai cookie jars, login mới, request tiếp theo của phiên cũ, logout, timeout và ID rotation.
- [ ] Tách API status/JSON khỏi browser redirect; không coi 401/302/403 là chẩn đoán nguyên nhân.
- [ ] Log an toàn theo reason code có bằng chứng, không lộ session ID hoặc authentication secrets.

**Kết luận:** **Phiên hết hạn** là vấn đề vòng đời phía session store; **phiên không hợp lệ** là ID request không còn tra ra một phiên hợp lệ; **phiên bị thay thế do concurrent login** là một trạng thái được SessionRegistry quản lý; **đổi session ID khi login** là phòng vệ session fixation. Chỉ khi phân biệt đúng bốn hiện tượng này, ta mới nên lựa chọn `invalidSessionUrl`, `expiredUrl`, thông báo UI và chiến lược kiểm thử phù hợp.