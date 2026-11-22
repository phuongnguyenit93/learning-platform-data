# Cấu hình thời hạn phiên và xử lý phiên hết hạn trong Spring Boot web runtime

Khi một người dùng đã có **HttpSession**, server cần quyết định **phiên còn hiệu lực bao lâu khi không có request**, điều gì xảy ra khi trình duyệt tiếp tục gửi cookie mang session ID cũ, và ứng dụng phải trả về **HTTP 401, chuyển hướng đăng nhập hay một thông báo khác**. Ba vấn đề thường bị trộn lẫn: **thời hạn phiên trên server**, **tuổi thọ cookie phía browser** và **thời hạn đăng nhập theo chính sách bảo mật**. Cấu hình sai có thể khiến người dùng phải đăng nhập quá thường xuyên, API trả HTML đăng nhập thay vì JSON 401, hoặc session cũ còn được sử dụng lâu hơn chính sách cho phép.

Bài tập trung vào **Spring Boot 3.x, Java 17+, Spring MVC/Servlet và HttpSession**. Ví dụ sử dụng Spring Boot 3.3, embedded Tomcat và các endpoint trình diễn. Khi dự án dùng **Spring Security** hoặc **Spring Session Redis/JDBC**, có thêm cơ chế cần hiểu riêng. Đoạn demo mô phỏng trạng thái phiên, **không phải hệ thống xác thực sản xuất**.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Giải thích quan hệ giữa **HttpSession**, **session ID**, cookie **JSESSIONID**, lần truy cập gần nhất và **maxInactiveInterval**.
2. Cấu hình thời gian không hoạt động bằng **server.servlet.session.timeout** và biết khi nào cần điều chỉnh bằng **HttpSession.setMaxInactiveInterval(...)**.
3. Phân biệt **idle timeout**, **absolute timeout**, **cookie Max-Age/Expires**, logout/invalidate và phiên bị vô hiệu hóa do chính sách nhiều đăng nhập.
4. Xử lý request khi session mất/hết hạn mà **không vô tình tạo session mới**, đặc biệt khi API phải trả JSON + HTTP 401.
5. Thiết kế trải nghiệm browser hợp lý: giữ form chưa lưu, thông báo phiên hết hạn, chuyển hướng đăng nhập và xử lý 401 trong JavaScript.
6. Hiểu sự khác nhau giữa container local session, **Spring Security** và **Spring Session** phân tán qua Redis/JDBC.
7. Kiểm chứng bằng **MockMvc** và HTTP thật, đo được các lỗi về cookie, proxy, load balancer, restart, cleanup và timeout.

Điều kiện nền: biết Servlet request/response, HTTP status, cookie, Spring MVC controller và chạy ứng dụng Spring Boot bằng Maven/Gradle.

## 2. HttpSession và cookie thực sự liên hệ thế nào?

### 2.1. HttpSession là trạng thái phía server

**HttpSession** đại diện cho trạng thái gắn với một client qua nhiều HTTP request. Session có **ID** và có thể chứa attributes như ngôn ngữ, giỏ hàng hoặc thông tin trạng thái. Với Servlet container mặc định, dữ liệu session thường được quản lý trong runtime của server; hình thức lưu và khả năng phục hồi sau restart tùy container/cấu hình.

Luồng đơn giản:

~~~text
Browser                                      Spring Boot / Servlet container
   |                                                   |
   | POST /demo/session/start                          |
   |-------------------------------------------------->|
   |                              request.getSession(true)
   |                              tạo session S1 nếu chưa có
   |<--------------------------------------------------|
   | Set-Cookie: JSESSIONID=<id>; Path=/; HttpOnly      |
   |                                                   |
   | GET /demo/session/me                              |
   | Cookie: JSESSIONID=<id>                           |
   |-------------------------------------------------->|
   |                              tìm session S1
   |                              xem đã quá idle timeout chưa
   |<--------------------------------------------------|
   | 200 JSON nếu session và thuộc tính còn hợp lệ       |
   |                                                   |
   | ... không có request chạm session quá thời hạn ...  |
   |                                                   |
   | GET /demo/session/me                              |
   | Cookie: JSESSIONID=<id> (cookie có thể vẫn còn)     |
   |-------------------------------------------------->|
   |                              không còn session hợp lệ
   |<--------------------------------------------------|
   | 401 JSON / hoặc UI redirect theo chính sách         |
~~~

Cookie thông thường mang **session ID**, không chứa toàn bộ object Java của HttpSession. Không gửi password, access token nhạy cảm hoặc toàn bộ attributes trong cookie chỉ vì browser cần giữ session ID. HTTP request dùng cookie để server tra session; việc bảo mật cookie, TLS và quản trị session là trách nhiệm chung của ứng dụng, container và Spring Security.

**JSESSIONID** là tên thường gặp khi dùng Servlet container mặc định. Nếu tích hợp **Spring Session**, cookie có thể tên **SESSION** theo cấu hình mặc định của Spring Session; tên thực tế có thể tùy chỉnh. Đừng viết logic dựa trên tên cookie duy nhất mà không kiểm tra cấu hình stack đang chạy.

### 2.2. Tạo, tìm và đóng phiên

| API/thuộc tính | Hành vi | Điểm cần nhớ |
| --- | --- | --- |
| **request.getSession()** | Lấy session hiện tại hoặc tạo mới nếu cần | Có thể làm lỗi hết hạn bị che vì API tự nhận session mới. |
| **request.getSession(true)** | Tương tự, được ghi rõ là cho phép tạo | Chỉ dùng khi thao tác chủ động bắt đầu session là hợp lý. |
| **request.getSession(false)** | Trả session hợp lệ nếu có, ngược lại **null** | Phù hợp kiểm tra phiên trước khi dùng tài nguyên yêu cầu trạng thái. |
| **session.getAttribute("key")** | Đọc attribute đã gắn vào session | Null không nhất thiết là hết hạn; có thể chưa từng set key. |
| **session.setAttribute("key", value)** | Gán dữ liệu vào session | Không thay thế persistence bền vững hoặc transaction database. |
| **session.getMaxInactiveInterval()** | Số giây không hoạt động tối đa | 0 hoặc âm theo Servlet API có nghĩa không timeout do inactivity; không nên dùng cho phiên xác thực thực tế. |
| **session.setMaxInactiveInterval(seconds)** | Đặt idle timeout riêng cho session | Cần kiểm soát đúng quy định; ảnh hưởng session đó, không thay property toàn ứng dụng. |
| **session.getLastAccessedTime()** | Thời điểm bắt đầu request gần đây nhất được client gắn với session | Tính theo milliseconds từ epoch; không phải absolute expiry time. |
| **session.invalidate()** | Vô hiệu hóa session chủ động | Dùng khi logout/thu hồi trạng thái; reference cũ tới session không còn hợp lệ. |
| **request.isRequestedSessionIdValid()** | Kiểm tra ID mà client gửi có còn hợp lệ | Không thể kết luận chính xác nguyên nhân ID không hợp lệ là timeout hay logout. |

**Cảnh báo quan trọng:** Khi request đến với cookie session cũ mà phiên đã hết hạn, **getSession(false)** trả null. Nếu code gọi **getSession()** trước khi kiểm tra, server có thể tạo session khác khiến việc xử lý 401/redirect không như mong đợi.

### 2.3. Session thường dùng sliding idle timeout, không phải absolute timeout

**Idle timeout** là khoảng thời gian tối đa giữa những lần client truy cập session. Ví dụ đặt 30 phút:

~~~text
10:00 - có request hợp lệ              -> mốc hoạt động gần nhất 10:00
10:25 - có request hợp lệ              -> mốc hoạt động dịch sang 10:25
10:50 - có request hợp lệ              -> mốc hoạt động dịch sang 10:50
11:20 - nếu không có request liên quan -> có thể hết hạn vì idle 30 phút
~~~

Với request thường xuyên, phiên có thể sống lâu hơn nhiều so với 30 phút tính từ lúc login. Đây là **sliding idle timeout**, không phải “người dùng được đăng nhập tối đa 30 phút kể từ lần đầu”. Các request heartbeat, AJAX polling hoặc auto-refresh có thể tiếp tục làm mới mốc hoạt động; websocket/push và công việc chạy nền không nhất thiết có tác động giống request HTTP gắn với session.

**Absolute timeout** là hạn cứng tính từ lần tạo/đăng nhập, ví dụ bắt buộc xác thực lại sau 8 giờ dù người dùng vẫn thao tác. HttpSession idle timeout **không tự cung cấp hạn này**. Nếu có chính sách absolute lifetime, phải có timestamp và kiểm tra thực sự tại security boundary, hoặc dùng cơ chế được framework/security platform hỗ trợ. Không chỉ tăng/giảm server.servlet.session.timeout rồi cho rằng đã thiết lập absolute lifetime.

### 2.4. Hết hạn và dọn dẹp không luôn xảy ra đúng giây cuối

Container thường phát hiện session hết hạn khi có request truy cập session, hoặc trong một tác vụ quét session nền. Vì vậy **thời điểm resource được dọn** và **thời điểm request cũ không còn được chấp nhận** có thể khác nhau vài giây hoặc theo chu kỳ quét. Không dùng một tác vụ background chờ đến đúng giây expiration để đảm bảo dữ liệu nghiệp vụ được commit.

Một session với timeout 60 giây không có nghĩa browser sẽ tự nhận push notification ở giây 60. Nếu UI không chủ động gọi server, browser vẫn hiển thị trang cũ; khi người dùng hành động lần nữa, request mới cho thấy session không còn hợp lệ.

## 3. Cấu hình thời hạn phiên trong Spring Boot

### 3.1. Property chính: server.servlet.session.timeout

Với **Spring Boot 3.3** trên Servlet stack, property:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
~~~

đặt thời gian **inactivity** của HttpSession. **30m** là một giá trị mặc định thường thấy trong Spring Boot 3.3. Có thể đặt đơn vị thời gian như **s**, **m**, **h**, nhưng lưu ý embedded Servlet container cụ thể có thể **làm tròn hoặc áp dụng độ phân giải theo phút**. Với Tomcat, không nên phụ thuộc vào timeout 2–3 giây để viết test ổn định; dùng timeout theo phút cho thử nghiệm thực tế.

Tương đương file **application.properties**:

~~~properties
server.servlet.session.timeout=30m
~~~

Ví dụ **thử nghiệm ngắn hơn**:

~~~yaml
server:
  servlet:
    session:
      timeout: 1m
~~~

Không dùng cấu hình quá ngắn như 1 phút cho production chỉ vì demo dễ quan sát. Thời gian production phải cân bằng yêu cầu bảo mật, độ nhạy dữ liệu, UX, quy định nội bộ và hành vi của các tab/browser/background request.

**Điểm quan trọng:** Đây là cấu hình của **Servlet HttpSession**. Với ứng dụng WebFlux, property dành cho reactive session là **server.reactive.session.timeout**, không phải server.servlet.session.timeout. Với Spring Session phân tán, có thêm **spring.session.timeout** được giải thích ở phần sau.

### 3.2. Cấu hình theo môi trường

Có thể dùng Spring profiles:

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: session-expiry-demo

server:
  port: 8080
  servlet:
    session:
      timeout: 30m
      cookie:
        http-only: true
        same-site: lax
~~~

**src/main/resources/application-local.yml**:

~~~yaml
server:
  servlet:
    session:
      timeout: 1m
~~~

Chạy với profile local:

~~~bash
java -jar target/session-expiry-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=local
~~~

Khi bật profile local, **timeout: 1m** ghi đè giá trị **30m** của cấu hình chung. Kiểm tra các override qua biến môi trường, command-line args hoặc hệ thống cấu hình ngoài nếu chạy trong container. Không suy luận chỉ từ file YAML là config thực tế đã được áp dụng.

**Cú pháp duration:** Hãy ghi rõ đơn vị **30m**, **1h**, thay vì chỉ ghi số trần trong ví dụ đào tạo. Theo tài liệu Boot, khi không có suffix, nhiều duration property dùng seconds, nhưng code dễ bị hiểu nhầm và một số container vẫn có độ phân giải riêng.

### 3.3. Đặt timeout riêng cho từng session bằng Java

Có tình huống session quản trị phải hết hạn nhanh hơn session bình thường. Servlet API cho phép:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.setMaxInactiveInterval(5 * 60); // 300 giây
}
~~~

Đây là **đoạn method minh họa**, không phải file Java chạy riêng. **setMaxInactiveInterval** nhận **int số giây**, không nhận java.time.Duration. Đặt trong xử lý session được quản lý phù hợp sau khi đã xác thực quyền/ngữ cảnh; không cho client gửi giá trị timeout tự do để tăng thời gian sống phiên. Việc đặt interval theo từng request có thể làm policy khó kiểm soát, nên ưu tiên cấu hình tập trung trừ khi thật sự có yêu cầu rõ.

Theo Servlet API, **0 hoặc giá trị âm có thể làm session không tự timeout do inactivity**. Không dùng cách đó để “khắc phục” người dùng phàn nàn phải đăng nhập lại: nó làm phiên tồn tại lâu và tăng nguy cơ bị chiếm dụng session ID. Muốn “ghi nhớ tôi” là một bài toán xác thực có token/remember-me riêng, không phải bỏ thời hạn server session.

## 4. Cookie Max-Age không bằng HttpSession timeout

### 4.1. Hai bộ đếm khác chỗ lưu trữ

- **server.servlet.session.timeout:** server quyết định khi nào HttpSession không còn hợp lệ do inactivity.
- **server.servlet.session.cookie.max-age:** browser quyết định thời gian giữ cookie nếu cookie có Max-Age. Không tự đặt tuổi thọ của **HttpSession** trên server.
- **Cookie HttpOnly:** JavaScript trong browser không đọc được cookie thông qua document.cookie; không ngăn cookie được gửi trong HTTP request.
- **Cookie Secure:** browser chỉ gửi qua kết nối được coi là an toàn, thông thường HTTPS.
- **Cookie SameSite:** hạn chế một số tình huống cookie được gửi trong cross-site request; không thay cho CSRF protection hoặc authentication.
- **Cookie Path/Domain:** giới hạn phạm vi URL và host mà browser gửi cookie; có thể khác khi deploy dưới context path/proxy.

Ví dụ cấu hình cookie:

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
        max-age: 2h
~~~

Đây là **ví dụ triển khai HTTPS**, không phải config để copy vào demo chạy HTTP localhost. Nếu đặt **Secure=true** mà truy cập HTTP thông thường, browser có thể không gửi cookie; endpoint nhìn như phiên bị mất liên tục.

**Cấu hình trên không khiến phiên server sống 2 giờ**. Server vẫn có thể cho session hết hạn sau 20 phút không hoạt động, dù browser còn cookie trong 2 giờ. Khi gửi cookie cũ, server không tìm được session hợp lệ; ứng dụng phải xử lý lại.

Trường hợp ngược lại, **cookie Max-Age ngắn hơn idle timeout** có thể khiến browser xóa ID trong khi server còn giữ session đến khi nó tự hết hạn. Như vậy session phía server thành “mồ côi” tạm thời. Vì thế, chính sách cookie và server session cần được thiết kế nhất quán, không giả định chúng là cùng một timer.

### 4.2. Cookie phiên không có Max-Age

Nếu cookie không có Max-Age/Expires, browser thường coi đó là **session cookie** và gắn vòng đời với browser session. Tuy nhiên, một số browser khôi phục tab và session cookie khi mở lại theo cơ chế session restore. Vì vậy **không thể lấy việc đóng browser làm biện pháp đảm bảo tuyệt đối** logout hoặc xóa server session.

Ngược lại, việc browser xóa cookie không ngay lập tức dọn object HttpSession trên server. Server xử lý timeout/cleanup theo chính sách riêng; nếu cần logout tường minh, hãy **invalidate** session server.

### 4.3. Cách cookie ảnh hưởng API

Đối với client browser dùng cookie, request có thể phải dùng cơ chế gửi credentials theo origin, CORS và SameSite. Nếu frontend khác domain và gọi fetch mà không gửi cookie, API sẽ nhìn thấy **không có session**, dù server session còn sống. Đây là vấn đề **cookie delivery**, không phải timeout.

Tránh xử lý mọi lỗi HTTP 401 là “hết hạn vì idle”: nó cũng có thể do chưa đăng nhập, cookie không gửi, session bị revoke, security policy thay đổi hoặc session store tạm không truy cập được. Thông báo UI nên tôn trọng sự không chắc chắn, ví dụ **“Phiên không còn hợp lệ, vui lòng đăng nhập lại”**.

## 5. Khi phiên hết hạn, server phải làm gì?

### 5.1. Phân biệt các trạng thái

~~~text
Request đến endpoint yêu cầu session
               |
               v
request.getSession(false)
       |                    |
       | có session         | null
       v                    v
kiểm tra trạng thái         không tự getSession() tạo mới
nghiệp vụ / quyền           |
       |                    v
       |                API -> 401 + JSON
       |                UI  -> 302/303 tới login phù hợp
       |
       +-- hợp lệ -> xử lý request và trả response
       |
       +-- attribute thiếu / policy không hợp lệ
                   -> 401/403 hoặc redirect tùy nguyên nhân
~~~

**Không tạo session mới chỉ để hiển thị lỗi.** Một lỗi thường gặp:

~~~java
HttpSession session = request.getSession();
if (session.getAttribute("USER") == null) {
    // Ở đây session cũ có thể đã hết hạn nhưng getSession() vừa tạo phiên mới.
}
~~~

**Đoạn trên là ví dụ anti-pattern**, không phải cách xử lý được khuyến nghị. Thay bằng **getSession(false)** khi chỉ muốn kiểm tra session hiện hữu. Tuy nhiên, trong ứng dụng thật có Spring Security, hãy để security filter chain chịu trách nhiệm xác thực thay vì tự kiểm tra một attribute tên USER cho mọi endpoint.

### 5.2. API nên trả 401 có cấu trúc, không phải HTML 200

Đối với REST API sử dụng session authentication, khi request yêu cầu xác thực nhưng không có session/authentication hợp lệ, phản hồi thường là:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
Cache-Control: no-store

{"state":"missing_or_expired"}
~~~

**401 Unauthorized** biểu thị cần xác thực. **403 Forbidden** thường dành cho người đã xác thực nhưng không có quyền thực hiện hành động. **200 OK + trang login** là phản hồi sai cho API JSON: frontend có thể cố parse HTML thành JSON và hiện lỗi không rõ nguyên nhân.

Không có HTTP status chuẩn **440** trong IANA HTTP status registry để biểu thị timeout; một số nền tảng dùng 440 theo quy ước riêng, nhưng API công khai nên ưu tiên 401 hoặc hợp đồng lỗi được thống nhất. Nếu dùng **RFC 9457 Problem Details**, có thể trả application/problem+json với status 401, title và type phù hợp. Không đưa session ID hay token vào error response.

### 5.3. UI/browser có thể chuyển hướng login

Ứng dụng server-rendered MVC có thể xử lý một request điều hướng trang bằng cách redirect:

~~~java
@GetMapping("/account")
public String account(HttpServletRequest request, Model model) {
    HttpSession session = request.getSession(false);
    if (session == null || session.getAttribute("CURRENT_USER") == null) {
        return "redirect:/login?reason=session";
    }
    model.addAttribute("user", session.getAttribute("CURRENT_USER"));
    return "account";
}
~~~

Đây là **đoạn minh họa thuộc một @Controller** có view/login được cấu hình riêng, **không phải file Java độc lập**. Trong hệ thống xác thực thật, nên dựa trên Spring Security Authentication và entry point. Khi redirect, kiểm tra context path, relative URL và tránh open redirect từ tham số người dùng. Không đưa thông tin nhạy cảm hoặc nội dung form của user vào query string.

Với SPA/JavaScript app gọi API, nên để API trả **401 JSON** rồi frontend chủ động:

1. Hủy trạng thái “đang đăng nhập” chỉ ở phía UI, không giả định đã logout khỏi mọi thiết bị.
2. Giữ hoặc khôi phục dữ liệu chưa lưu khi chính sách cho phép; không tự động gửi lại một POST có side effect.
3. Hiện thông báo phiên không hợp lệ và hướng dẫn đăng nhập lại.
4. Sau khi xác thực lại, chỉ retry request an toàn hoặc request có idempotency key theo thiết kế.

Nếu dùng fetch, chú ý redirect 302 từ server có thể bị browser **tự theo** đến trang login; JavaScript nhìn thấy HTML thay vì trực tiếp thấy 401. Hãy phân biệt flow điều hướng trang và flow API ngay từ security configuration.

## 6. Demo chạy được: timeout + 401 + invalidate mà không tự tạo session

Ví dụ sau trình diễn **HttpSession và idle timeout**, không dùng Spring Security. Endpoint **/demo/session/start** chỉ gắn cờ demo, **không xác thực mật khẩu**; tuyệt đối không biến cờ demo thành một login production.

### 6.1. Tạo project

Tạo Spring Boot project Java 17+ bằng **https://start.spring.io** với Maven, Spring Boot **3.3.x**, group **com.example**, artifact **session-expiry-demo**, package **com.example.sessionexpiry**, dependency:

- **Spring Web**
- **Spring Boot Starter Test**

Ví dụ tên file:

~~~text
session-expiry-demo/
  pom.xml
  mvnw
  mvnw.cmd
  src/main/java/com/example/sessionexpiry/
    SessionExpiryApplication.java
    DemoSessionController.java
  src/main/resources/
    application.yml
  src/test/java/com/example/sessionexpiry/
    DemoSessionControllerTest.java
~~~

Không thêm Spring Security vào project này nếu muốn chạy đúng demo đơn giản, vì security auto-configuration thay đổi yêu cầu authentication/CSRF và hành vi POST. Phần Spring Security ở mục 8 trình bày cách tiếp cận riêng cho ứng dụng thật.

### 6.2. pom.xml tối thiểu, biên dịch với Java 17

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
    <artifactId>session-expiry-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-test</artifactId>
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

Version **3.3.13** ở đây là mốc cố định để đọc cú pháp; trong dự án mới phải chọn phiên bản được tổ chức hỗ trợ, cập nhật bảo mật và kiểm tra tài liệu tương ứng. Không pin dependency Spring Framework/Tomcat thủ công khác version do Spring Boot quản lý nếu không có lý do rõ.

### 6.3. Main class

**src/main/java/com/example/sessionexpiry/SessionExpiryApplication.java**

~~~java
package com.example.sessionexpiry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionExpiryApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionExpiryApplication.class, args);
    }
}
~~~

### 6.4. Cấu hình demo 1 phút

**src/main/resources/application.yml**

~~~yaml
spring:
  application:
    name: session-expiry-demo

server:
  port: 8080
  servlet:
    session:
      timeout: 1m
      cookie:
        http-only: true
        same-site: lax
~~~

Cookie Secure không được bật trong demo HTTP localhost vì không có HTTPS. Trong production, chạy HTTPS, cân nhắc **secure: true**, kiểm soát forward headers từ reverse proxy đáng tin cậy và cấu hình cookie Path/Domain/SameSite theo thực tế. Không hạ bảo vệ cookie trong production để cho demo hoạt động.

### 6.5. Controller demo: chủ động tạo, kiểm tra và hủy session

**src/main/java/com/example/sessionexpiry/DemoSessionController.java**

~~~java
package com.example.sessionexpiry;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/session")
public class DemoSessionController {
    private static final String DEMO_ACTIVE = "DEMO_ACTIVE";

    public record Message(String state) { }

    @PostMapping("/start")
    public ResponseEntity<Message> start(HttpServletRequest request) {
        // Chỉ để minh họa vòng đời HttpSession, không xác thực người dùng.
        HttpSession session = request.getSession(true);
        session.setAttribute(DEMO_ACTIVE, Boolean.TRUE);

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Message("started"));
    }

    @GetMapping("/me")
    public ResponseEntity<Message> me(HttpServletRequest request) {
        // Không tự tạo session mới chỉ để kiểm tra.
        HttpSession session = request.getSession(false);

        if (session == null
                || !Boolean.TRUE.equals(session.getAttribute(DEMO_ACTIVE))) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .cacheControl(CacheControl.noStore())
                    .body(new Message("missing_or_expired"));
        }

        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(new Message("active"));
    }

    @PostMapping("/stop")
    public ResponseEntity<Void> stop(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }

        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
    }
}
~~~

**Điều cần kiểm tra trong code:**

- **start** gọi getSession(true) vì đây là endpoint duy nhất chủ động mở trạng thái demo.
- **me** gọi **getSession(false)**, không mở session mới khi không có ID hợp lệ.
- Khi thiếu session **hoặc** thiếu DEMO_ACTIVE, API trả **401 JSON**. Hai tình huống được gộp vào một trạng thái vì chúng không chứng minh riêng được “hết hạn do không hoạt động”.
- **stop** chỉ invalidate session nếu có, **không** tạo session mới. Kết quả 204 nghĩa là không còn response body, không được ghi JSON ra response này.
- **CacheControl.noStore()** yêu cầu không cache nội dung liên quan session; cache browser/proxy không được dùng để quyết định phiên có còn hiệu lực.
- Không đưa ID của session vào JSON response hoặc log công khai. Cookie ID là thông tin cần được bảo vệ.
- Không lưu password hay secret trong session attributes; nếu có dữ liệu nhạy cảm, giảm tối đa thông tin lưu và áp dụng cơ chế xác thực/ủy quyền thật.

### 6.6. Chạy demo và thử session bằng curl

Linux/macOS:

~~~bash
./mvnw spring-boot:run
~~~

Windows:

~~~text
mvnw.cmd spring-boot:run
~~~

Hoặc đóng gói executable JAR:

~~~bash
./mvnw clean package
java -jar target/session-expiry-demo-0.0.1-SNAPSHOT.jar
~~~

Mở terminal thứ hai. **-c** ghi cookie vào file, **-b** gửi lại cookie:

~~~bash
curl -i -c cookies.txt -b cookies.txt -X POST http://localhost:8080/demo/session/start
curl -i -b cookies.txt http://localhost:8080/demo/session/me
~~~

Kỳ vọng với API demo:

~~~http
HTTP/1.1 200
Content-Type: application/json

{"state":"started"}
~~~

Request **/me** ngay sau đó có response body:

~~~json
{"state":"active"}
~~~

File **cookies.txt** có thể chứa cookie JSESSIONID, nên chỉ dùng cho test nội bộ và **không commit vào git / không chia sẻ**. Header thực tế có thể khác như charset, server name, Cache-Control, Set-Cookie/Path; body JSON như trên là phần do controller định nghĩa.

Để quan sát idle timeout thực:

1. Gọi **/demo/session/start** và lưu cookie.
2. **Không gọi /demo/session/me**, không làm request nào liên quan session trong thời gian vượt quá **1m** (nên cho thêm dư thời gian do container có thể làm tròn và cleanup theo chu kỳ).
3. Sau thời gian không hoạt động, gọi **curl -i -b cookies.txt http://localhost:8080/demo/session/me**.
4. Kỳ vọng **HTTP 401** cùng body **{"state":"missing_or_expired"}**.

Nếu liên tục gọi /me để “kiểm tra xem đã hết hạn chưa”, chính những request này có thể gia hạn thời điểm truy cập session và khiến nó **không bao giờ hết hạn trong lúc bạn kiểm tra**. Khi cần đo chính xác, dùng client không polling, xem timestamp và cấu hình session/container.

Để kiểm tra invalidate chủ động:

~~~bash
curl -i -b cookies.txt -X POST http://localhost:8080/demo/session/stop
curl -i -b cookies.txt http://localhost:8080/demo/session/me
~~~

Response của **stop** là **204 No Content**; request **me** tiếp theo trả 401. Cookie cũ có thể vẫn tồn tại trong file/browser dù server session đã bị invalidate; việc xóa cookie là một vấn đề riêng.

### 6.7. MockMvc test: bảo đảm không tạo phiên mới để xử lý lỗi

**src/test/java/com/example/sessionexpiry/DemoSessionControllerTest.java**

~~~java
package com.example.sessionexpiry;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoSessionControllerTest {
    @Autowired
    MockMvc mvc;

    @Test
    void missingSessionReturns401WithoutCreatingNewSession()
            throws Exception {
        MvcResult result = mvc.perform(get("/demo/session/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.state")
                        .value("missing_or_expired"))
                .andReturn();

        assertNull(result.getRequest().getSession(false));
    }

    @Test
    void startUseAndStopSession() throws Exception {
        MvcResult started = mvc.perform(post("/demo/session/start"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("started"))
                .andReturn();

        HttpSession rawSession = started.getRequest().getSession(false);
        assertNotNull(rawSession);
        MockHttpSession session = (MockHttpSession) rawSession;

        mvc.perform(get("/demo/session/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("active"));

        mvc.perform(post("/demo/session/stop").session(session))
                .andExpect(status().isNoContent());

        mvc.perform(get("/demo/session/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.state")
                        .value("missing_or_expired"));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Test kiểm tra **hợp đồng ứng dụng**: không tạo session khi chỉ kiểm tra, tạo session có attribute, trả 200, invalidate và trả 401 khi không có phiên. **MockMvc không chứng minh server thật sẽ tự idle-expire sau đúng 60 giây**, vì nó chạy Servlet request mô phỏng và bài test không chờ đồng hồ. Muốn kiểm tra timeout theo container phải dùng HTTP integration test hoặc bài thử curl khi ứng dụng thật chạy.

Nếu muốn mô phỏng bất hoạt trong unit test, đừng dùng Thread.sleep(60000) như chiến lược test chính; có thể kiểm tra logic session policy tách biệt với **Clock** giả, còn thời điểm cleanup của container được xác nhận bằng test integration phù hợp. Không bắt test phụ thuộc vào độ chính xác tuyệt đối của background cleaner.

## 7. Xử lý hết hạn trong UI, API và trường hợp nhiều tab

### 7.1. Browser có thể không biết session đã mất cho đến request tiếp theo

Session là trạng thái server-side. Một form đang được người dùng nhập có thể nằm yên nhiều phút; hết hạn của server không tự xóa chữ họ đang gõ. Khi bấm Submit, API nhận cookie cũ và trả 401/redirect. Trải nghiệm được khuyến nghị:

- Thông báo rõ ràng “Phiên đã hết hiệu lực, vui lòng đăng nhập lại”.
- Giữ dữ liệu form ở client **nếu không chứa thông tin nhạy cảm và chính sách cho phép**, không upload lên server chưa xác thực.
- Sau login, khôi phục navigation/dữ liệu có chủ đích; tránh tự động gửi lại giao dịch thanh toán, đặt hàng hoặc thao tác có side effect.
- Nếu UI có nhiều tab, xử lý nhất quán khi một tab logout hoặc session hết hạn. Không coi biến localStorage là bằng chứng server session vẫn hoạt động.
- Đừng giữ session sống bằng polling tự động chỉ để né logout. Heartbeat gia hạn session có thể vi phạm yêu cầu bảo mật về inactivity.

### 7.2. Trả 401 hay redirect?

| Tình huống | Hành vi thường phù hợp | Lưu ý |
| --- | --- | --- |
| Fetch / XHR tới REST API yêu cầu đăng nhập | **401 JSON/Problem Details** | Frontend chuyển hướng hoặc hiện login theo logic của nó. |
| Điều hướng trang MVC server-rendered | **302/303 tới login** | Chỉ với navigation hợp lệ; không đưa dữ liệu nhạy cảm vào URL. |
| Người dùng đã xác thực nhưng thiếu quyền | **403** | Không gọi mọi 403 là “session expired”. |
| Lệnh logout thành công | Invalidate, xóa cookie theo policy, redirect/204 | Không chỉ xóa UI state mà bỏ quên server session. |
| Phiên bị revoke bởi admin/chính sách | **401/redirect** tùy bề mặt | Nguyên nhân khác idle timeout, có thể thông báo chung. |
| Lỗi Redis/session store | Phân loại lỗi hạ tầng và bảo mật | Không giả định mất kết nối backend là do user không hoạt động. |

**Quan trọng:** HTTP 401 không nhất thiết luôn do session timeout. Cần correlation/request ID trong log thay vì đưa session ID vào log, và theo dõi số lần 401, 403, tỷ lệ login lại và lỗi session store. Ở phía client, tránh vòng lặp redirect /login → API → /login hoặc retry vô hạn khi session đã mất.

### 7.3. Phân biệt session vừa hết hạn với người chưa từng đăng nhập

Nếu chỉ dùng **getSession(false)** thì cả hai trường hợp có thể trả null. **request.getRequestedSessionId()** và **request.isRequestedSessionIdValid()** có thể giúp biết client từng gửi ID nhưng ID không hợp lệ; chúng **không chỉ ra nguyên nhân** invalid là idle timeout, logout, server restart, forged ID hay session registry revoke.

Do đó, một thông báo thống nhất là đúng: **"Phiên không tồn tại hoặc không còn hợp lệ"**. Nếu hệ thống cần lý do chính xác để audit, phải lưu event theo chính sách hạ tầng/session store và tránh phơi bày chi tiết đủ để kẻ tấn công suy luận giá trị session ID.

### 7.4. Cơ chế client-side timer chỉ là UX, không phải xác thực

Một banner “Phiên còn 2 phút” có thể dựa trên giá trị idle timeout hoặc timestamp trả từ server. Tuy nhiên, client clock có thể lệch, request từ tab khác có thể gia hạn phiên và server có thể revoke session bất kỳ lúc nào. **Server luôn là nguồn quyết định quyền truy cập.** Không dùng bộ đếm JavaScript để cho phép truy cập vào API đã yêu cầu 401.

## 8. Spring Security: handling session expired đúng lớp bảo mật

Demo HttpSession ở mục 6 cố ý **không xác thực thật**. Trong ứng dụng có username/password, role, CSRF, session fixation protection hoặc concurrent login, **Spring Security** nên quản lý identity và quyền. Không tự định nghĩa login production bằng cách gắn Boolean.TRUE vào session rồi tin rằng client đã được xác thực.

### 8.1. Session timeout và Security là hai lớp khác nhau

**Servlet container** kiểm soát HttpSession hết hạn do inactivity. **Spring Security** sử dụng thông tin xác thực từ security context, thường lưu qua session trong form-login flow. Khi session hết hạn, security context cũ cũng không còn được khôi phục từ phiên đó; request đến tài nguyên protected cần xác thực lại.

**server.servlet.session.timeout** vẫn là timeout nền của servlet session. Spring Security có các chiến lược riêng cho session fixation, invalid session ID, invalid session URL, concurrent session management và logout. Không có một property kiểu “spring.security.session.timeout” chung cho mọi thứ tương đương server.servlet.session.timeout.

### 8.2. invalidSessionUrl và InvalidSessionStrategy

Spring Security hỗ trợ:

~~~java
http.sessionManagement(session ->
        session.invalidSessionUrl("/login?reason=session"));
~~~

Đây là **đoạn cấu hình trong SecurityFilterChain đã có sẵn**, không phải file Java độc lập. Nó có thể điều hướng khi request mang **invalid session ID**. Một số stack mặc định như form login có behavior đặc thù; cần test thực tế với Spring Security version, filter chain và entry point đã chọn.

**Lưu ý cốt lõi:** invalid session ID không chứng minh chắc đó là timeout. Khi logout làm session mất hiệu lực mà browser tiếp tục gửi cookie cũ, người dùng cũng có thể bị đưa tới URL “session invalid”. Spring Security documentation cảnh báo tình huống báo nhầm và khuyến nghị dọn cookie khi logout.

Nếu endpoint API bắt buộc trả **401 JSON**, **invalidSessionUrl** kiểu redirect có thể không phù hợp. Hãy sử dụng **InvalidSessionStrategy** hoặc security entry point xử lý riêng **/api/**, trong khi navigation HTML đi login. Một ví dụ minh họa ở mức ý tưởng:

~~~text
Nếu request thuộc /api/** và cần authentication nhưng session không hợp lệ:
    HTTP 401 application/problem+json
Nếu request là navigation HTML và session không hợp lệ:
    chuyển hướng login được kiểm soát
Nếu request là /login hoặc static public resource:
    tránh vòng lặp redirect do cookie cũ
~~~

Không copy một đoạn lambda redirect chung cho toàn bộ filter chain mà quên test login page, static resources, API và CSRF. Request đến API có **Authorization: Bearer ...** có thể dùng cơ chế stateless khác; đừng buộc nó tuân theo session timeout của browser login khi API thực tế không dựa vào HttpSession.

### 8.3. expiredUrl của maximumSessions không phải general idle timeout

Spring Security có thể giới hạn đồng thời:

~~~java
http.sessionManagement(session -> session
        .maximumSessions(1)
        .expiredUrl("/login?reason=another-login"));
~~~

Đây cũng là **đoạn cấu hình minh họa bên trong SecurityFilterChain**. **expiredUrl** trong **concurrent session control** liên quan tới phiên bị đánh dấu expired vì vượt giới hạn số session (ví dụ login ở nơi khác). **Không dùng expiredUrl để diễn giải mọi idle timeout**. Khi dùng concurrent session control cần các thành phần như **SessionRegistry** và thường cần **HttpSessionEventPublisher** để theo dõi session lifecycle, tùy cấu hình Spring Security.

Phân biệt:

| Nguyên nhân | Ai quản lý chủ yếu? | Hành vi cần thiết |
| --- | --- | --- |
| Inactivity vượt maxInactiveInterval | Servlet container / Spring Session | Session không còn hợp lệ, xử lý lần request tiếp theo. |
| Logout user | Security/logout handler + session owner | Invalidate session, xử lý cookie, security context. |
| Login thứ hai vượt maximumSessions | Spring Security concurrent session control | Session cũ bị đánh dấu expired hoặc chặn login mới theo policy. |
| Không gửi cookie vì SameSite/CORS | Browser/cookie policy | Server không tìm thấy session, nhưng không phải timeout. |
| Server restart khi session chỉ lưu local | Container/runtime | Session cũ có thể mất; cần login lại hoặc session store chung. |
| Token JWT access hết hạn | Token validation | Không đồng nghĩa HttpSession idle timeout. |

### 8.4. Logout, cookie và session fixation protection

Khi logout, server phải thu hồi/invalid session theo cơ chế authentication thực tế. Spring Security có thể cấu hình:

~~~java
http.logout(logout -> logout
        .invalidateHttpSession(true)
        .deleteCookies("JSESSIONID"));
~~~

**Đoạn minh họa, không phải ứng dụng độc lập.** Xóa cookie có thể phụ thuộc cookie **Path/Domain** và container; cần test trên browser thực tế. Với Spring Session, tên cookie có thể là **SESSION** chứ không phải JSESSIONID. Một cách khác ở môi trường HTTPS có hỗ trợ là dùng **Clear-Site-Data** theo policy, nhưng không xóa toàn bộ dữ liệu site tùy tiện.

**Session fixation protection** của Spring Security thường thay đổi session ID sau khi xác thực thành công (ví dụ changeSessionId trên Servlet hiện đại). Nó khác với idle timeout; mục đích ngăn kẻ tấn công ép nạn nhân sử dụng session ID biết trước. Không tự vô hiệu hóa bảo vệ này để giữ một ID cố định qua login.

## 9. Spring Session: khi session cần tồn tại trên nhiều instance

### 9.1. Giới hạn của local HttpSession

Trong một ứng dụng chạy **một JVM**, container local session có thể đủ. Nhưng khi triển khai nhiều replicas:

~~~text
Browser -- Cookie ID --> Load Balancer
                               |
                               +--> Instance A: session S1
                               |
                               +--> Instance B: không có S1
~~~

Nếu request ban đầu đến A, request sau đến B và không có shared session store/sticky routing phù hợp, B có thể trả 401 dù user vừa hoạt động. Nếu instance A bị restart, local session cũng có thể mất. Đừng vội tăng timeout để chữa lỗi **không cùng session store**.

### 9.2. Redis/JDBC với Spring Session

**Spring Session** có thể thay thế triển khai HttpSession mặc định bằng repository được lưu trong Redis hoặc JDBC. Với Spring Boot và starter tương ứng, tự động cấu hình có thể cung cấp **SessionRepositoryFilter** để Servlet request nhìn thấy session dùng shared store.

Ví dụ với Redis trong một ứng dụng Spring Boot có dependency session-data-redis và cấu hình Redis hợp lệ:

~~~yaml
spring:
  session:
    timeout: 30m
    redis:
      namespace: myapp:sessions
~~~

Trong Spring Boot có Spring Session auto-configuration, **spring.session.timeout** đặt thời hạn session cho store. Nếu thuộc tính này không được cấu hình trong Servlet app, auto-configuration có thể fallback sang **server.servlet.session.timeout**. Khi dùng **@EnableRedisHttpSession/@EnableJdbcHttpSession** để tự cấu hình repository, auto-configuration có thể back off; cần tuân thủ thuộc tính của cấu hình chủ động thay vì khẳng định mọi property đều được áp dụng.

**Không thêm dependency Spring Session vào demo rồi trông đợi nó hoạt động ngay** nếu chưa cung cấp Redis/JDBC store và cấu hình phù hợp. Thêm store là thay đổi kiến trúc liên quan tính sẵn sàng, serialization, scale, bảo mật kết nối và deployment.

### 9.3. TTL, cleanup và sự kiện expiration

Redis có cơ chế TTL/eviction, JDBC repository thường cần cleanup job. **Session logic không chấp nhận ID đã hết hạn** là yêu cầu quan trọng, nhưng event dọn dẹp/tác vụ nền không nhất thiết chạy đúng thời điểm ở từng giây. Spring Session còn có các cơ chế event/session expiration khác nhau theo repository; không viết nghiệp vụ quan trọng phụ thuộc duy nhất vào callback expiration.

Session attributes trong shared store phải phù hợp cơ chế serialize, chi phí dữ liệu và retention policy. Tránh lưu object graph lớn, credential, resource mở hoặc object không serializable. Không dùng session làm database chính cho cart/order khi dữ liệu đó cần transaction và độ bền cao.

### 9.4. Lưu ý khi bật HTTPS/proxy

Khi chuyển frontend/backend qua domain khác, phải xác nhận Set-Cookie thật: **Name, Domain, Path, HttpOnly, Secure, SameSite**. Khi HTTPS kết thúc tại reverse proxy, ứng dụng cần biết scheme thực tế nếu tự xác định secure-cookie/redirect và có thể dùng forward-header strategy phù hợp với hạ tầng đáng tin cậy.

**CORS không sửa được cookie có SameSite policy sai.** CORS chỉ kiểm soát quyền đọc response và preflight; cookie delivery còn phụ thuộc browser, credentials mode, third-party cookie restrictions và Secure/SameSite. Không tắt CSRF protection chỉ vì API trả 401 khi session hết hạn.

## 10. Absolute timeout, re-authentication và idle timeout theo rủi ro

### 10.1. Khi nào idle timeout là chưa đủ?

Một hệ thống quản trị tài chính hoặc truy cập tài liệu nhạy cảm có thể yêu cầu:

- **Idle timeout:** ví dụ 15 phút không có hoạt động hợp lệ.
- **Absolute lifetime:** ví dụ không quá 8 giờ kể từ khi xác thực.
- **Re-authentication:** yêu cầu nhập lại mật khẩu/MFA cho thao tác nhạy cảm.
- **Server-side revocation:** admin có thể thu hồi session ngay cả khi nó vừa được sử dụng.
- **Concurrent-session policy:** giới hạn số thiết bị/phiên hoạt động.

Các ngưỡng trên **chỉ là ví dụ**, không phải tiêu chuẩn bắt buộc cho mọi tổ chức. Không lấy max-age của cookie thay thế cho absolute lifetime; cookie có thể bị xóa hoặc giữ lâu hơn, nhưng quyết định truy cập phải được thực thi server-side.

### 10.2. Cơ chế triển khai hạn cứng

Một cách tiếp cận ở mức kiến trúc:

~~~text
Sau khi xác thực thành công:
    ghi authTime do server tạo vào security principal/session record
Mỗi request cần authentication:
    nếu chưa có session/security context -> 401 / login
    nếu now > authTime + absoluteLifetime:
        thu hồi hoặc invalidate session
        yêu cầu xác thực lại
    nếu còn hạn:
        kiểm tra role/permissions và xử lý request
~~~

**Không lưu timestamp do client gửi làm nguồn tin cậy.** Đặt policy trong security filter/service được gọi trên mọi protected request, không chỉ trong một controller. Cần dùng clock có thể inject/test, xử lý phân tán/time skew khi nhiều instance và tránh race giữa các request đồng thời. Nếu có “remember me”, thiết kế token riêng và bảo vệ rotate/revoke đúng, không tự mở vô hạn maxInactiveInterval.

### 10.3. Cần xử lý request đang chạy thế nào?

Idle timeout được định nghĩa theo khoảng giữa các client access; một request đang xử lý lâu có thể còn hiệu lực trong lúc request được phục vụ, tùy Servlet container và API. Không suy ra rằng timer sẽ tự cắt một HTTP request dài đúng giây expiration. Với streaming/SSE/WebSocket, chính sách timeout connection, access token, authorization định kỳ và idle app logic cần được thiết kế riêng.

Nếu một giao dịch dài vượt session policy, đừng cố giữ session sống bằng cách phát request giả. Dùng transaction/job management và idempotency để đảm bảo việc ghi dữ liệu không bị lặp hoặc mất khi user phải đăng nhập lại.

## 11. Session invalidation events và việc dọn tài nguyên

### 11.1. Listener không phải bộ đếm thời gian tức thì

Servlet có **HttpSessionListener** với callback khi session được tạo/hủy; framework có thể dùng listener cho thống kê hoặc cleanup. Nhưng khi một session hết hạn do idle, callback hủy có thể đến theo cách container quản lý/cleanup, **không đảm bảo được gọi tại một thời điểm tường minh mà frontend nhìn thấy**.

Nếu cần cleanup resource thuộc session, cân nhắc model dữ liệu và lifecycle thích hợp. Không lưu trực tiếp thread, socket, transaction hoặc JDBC Connection sống lâu trong session để rồi chờ listener đóng. Nếu event không đến do crash/SIGKILL, resource sẽ phải được phục hồi/dọn bằng cơ chế bền vững khác.

### 11.2. Invalidate không tự xóa mọi cookie trên browser

**session.invalidate()** làm session server mất hiệu lực và khiến attribute binding được xử lý theo lifecycle, nhưng cookie browser là dữ liệu được lưu phía client. Nếu cần xóa nó, server phải trả **Set-Cookie** hết hạn với thông tin Path/Domain phù hợp hoặc dùng logout handler của framework. Một cookie stale có thể quay trở lại cùng ID sau logout, dẫn đến phát hiện **invalid session** chứ không phải “timeout” đúng nghĩa.

Đừng dùng response header xóa cookie như thay thế việc vô hiệu hóa session server. Cần làm cả hai theo chính sách, đặc biệt khi có nhiều tab hay cookie lưu trong file cURL.

### 11.3. @PreDestroy của singleton khác session expiration

**@PreDestroy** trên singleton bean chạy khi bean/container context bị hủy, thường là shutdown ứng dụng, không phải mỗi lần một user session hết hạn. Không gọi nó để dọn session của một người dùng. Servlet listener, Spring Session events hoặc business timeout riêng có vai trò khác và cũng cần thiết kế hồi phục khi event không đến.

## 12. Test và quan sát trên production

### 12.1. Bộ kiểm thử tối thiểu

| Trường hợp | Điều phải chứng minh | Dụng cụ phù hợp |
| --- | --- | --- |
| Không gửi cookie, gọi API protected | **401**, không tự tạo session | MockMvc hoặc HTTP integration. |
| Tạo session, gọi lại ngay | API trả trạng thái hợp lệ | MockMvc + cookie jar / browser. |
| Im lặng hơn idle timeout | Không còn được chấp nhận session cũ | HTTP thật trên container/session store thật. |
| Gọi API liên tục trước timeout | Gia hạn nếu request gắn session; không bị timeout sai | HTTP integration có kiểm soát thời gian. |
| Logout invalidate | Cookie/ID cũ không dùng lại được | HTTP test, test Security logout. |
| Browser không gửi cookie do SameSite/Secure | Server báo không có session, dù store có thể còn | Browser Network + server logs. |
| Nhiều replicas/restart | Session có/mất đúng chính sách store | Staging/load balancer test. |
| Session expired trong POST có side effect | Không ghi hai lần khi user login lại | Transaction/idempotency integration test. |
| UI redirect và API JSON | Không trả HTML 200 cho endpoint JSON | Contract test + browser navigation test. |
| Spring Security concurrent maxSessions | Session cũ bị revoke đúng policy | Security integration với hai login. |

**Không dựa duy nhất vào unit test của getSession(false)** để khẳng định timeout của Tomcat/Redis đang chạy đúng. Các tầng đó là trách nhiệm khác nhau.

### 12.2. Quan sát an toàn

Ghi nhận metric như **số HTTP 401**, số user login lại, session creation/destruction, latency/session store error và tỉ lệ 401 sau deploy. Có thể sử dụng Spring Boot Actuator/Micrometer theo khả năng instrumentation. Tuy nhiên **không ghi nguyên JSESSIONID, SESSION cookie, bearer token hoặc password vào log**.

Khi cần trace một request, dùng **correlation ID** độc lập với credential/session ID. Nếu thực sự cần ghép session theo security audit, dùng hệ thống audit kiểm soát quyền truy cập và chính sách ẩn danh/retention; đừng cho session ID vào URL hoặc thông báo lỗi.

### 12.3. Kiểm tra config thực tế

Khi timeout không giống YAML:

1. Kiểm tra active profile, property precedence, environment variables và startup arguments.
2. Xác nhận là **Servlet MVC** hay **WebFlux**, có **Spring Session** hoặc không.
3. Nếu dùng Spring Session, kiểm tra **spring.session.timeout**, các option repository tự cấu hình và TTL của store.
4. Nếu dùng external Servlet container/WAR, xem cấu hình context/container có ghi đè timeout không.
5. Kiểm tra code có **setMaxInactiveInterval** cho từng session hoặc có interceptor tự cập nhật trạng thái không.
6. Xác nhận request heartbeat/AJAX nào đang chạm session, không chỉ click của người dùng.
7. Đo trên đúng instance/proxy/container, không chỉ trên MockMvc.

## 13. Lỗi thường gặp và cách xử lý

### 13.1. “Đặt timeout 15 phút nhưng người dùng không bao giờ bị logout”

**Nguyên nhân có thể:** frontend polling, keep-alive gọi endpoint dùng session, nhiều tab cùng gửi request hoặc timeout đang bị override. **Chẩn đoán:** kiểm tra HTTP requests thực tế và last-accessed behavior, tìm setMaxInactiveInterval, property tại runtime. **Giải pháp:** tách request health/stateless khỏi session, loại polling không cần, xác định rõ idle vs absolute lifetime. Nếu policy cần hạn cứng, thực thi absolute expiry server-side.

### 13.2. “Mới đăng nhập vài phút đã nhận 401”

**Nguyên nhân:** cookie không được gửi (SameSite, Secure, Path, Domain, credentials), request đi vào replica khác có local session, server restart, session store mất kết nối, hoặc Spring Security redirect/login flow cấu hình sai. **Chẩn đoán:** so Set-Cookie và Cookie trong Network tab; xác nhận instance, session store và logs. Không tăng timeout mù quáng khi lỗi thực ra là cookie delivery.

### 13.3. “Phiên hết hạn nhưng API trả HTML trang login”

**Nguyên nhân:** form login/invalidSessionUrl redirect chung cho mọi request, browser fetch tự theo redirect. **Giải pháp:** API protected trả 401 JSON hoặc Problem Details; navigation UI mới redirect. Viết test đảm bảo Content-Type và status của endpoint API.

### 13.4. “Tại sao logout xong lại báo session expired?”

**Nguyên nhân:** browser vẫn gửi cookie session ID cũ sau invalidate; InvalidSessionStrategy xem đó là invalid session. **Giải pháp:** logout handler xóa cookie đúng name/Path/Domain, tránh vòng lặp redirect, thiết kế thông điệp không tuyên bố nguyên nhân chắc chắn nếu không biết.

### 13.5. “Hết hạn đúng 60 giây không ổn định”

**Nguyên nhân:** container làm tròn timeout theo phút, background cleanup và thời gian phát hiện khi request đến khác nhau; có request khác chạm session. **Giải pháp:** test với margin thời gian phù hợp, tránh Thread.sleep cực ngắn, không test chính sách bằng kiểm tra microsecond. Nếu nghiệp vụ đòi hạn chính xác tuyệt đối, xây security policy/expiry check riêng.

### 13.6. “Cookie Max-Age 2 giờ nhưng session chỉ dùng được 20 phút”

**Nguyên nhân:** browser còn ID nhưng server đã cho session hết hạn do inactivity. **Giải pháp:** hiểu đúng hai TTL; chọn cookie age nhất quán, trả 401/redirect khi session cũ mất, không coi cookie tồn tại là đủ quyền.

### 13.7. “Trong cluster, request lúc được lúc không”

**Nguyên nhân:** session local không chia sẻ giữa replicas và load balancer phân phối request khác instance. **Giải pháp:** dùng shared store như Spring Session Redis/JDBC hoặc sticky session khi phù hợp, đồng thời có chính sách failover; test rolling restart và store outage. Không giả định sticky routing thay thế hoàn toàn cho độ bền phiên.

### 13.8. “Spring Security expiredUrl không chạy khi idle”

**Nguyên nhân:** expiredUrl thuộc concurrent session control maximumSessions, không phải handler chung cho idle timeout. **Giải pháp:** cấu hình xử lý **invalid session ID**, authentication entry point hoặc app-level 401 theo filter chain. Phân biệt phiên bị đá do đăng nhập ở thiết bị khác với phiên hết hạn không hoạt động.

### 13.9. “Đã xóa cookie mà request vẫn có session?”

**Nguyên nhân:** cookie xóa sai Path/Domain, browser có cookie khác tên/namespace, Spring Session dùng SESSION thay JSESSIONID hoặc vẫn tồn tại một cơ chế authentication khác. **Giải pháp:** xem tất cả Set-Cookie/Cookie ở browser, kiểm tra SecurityContext và shared store, logout đúng owner.

### 13.10. “Session listener chưa chạy ngay khi qua timeout”

**Nguyên nhân:** background cleanup không chạy tại đúng giây hết hạn, Redis/JDBC có lịch TTL/cleanup và event semantics riêng. **Giải pháp:** không dùng listener làm nơi duy nhất thực thi nghiệp vụ critical; đưa thời hạn vào logic kiểm tra quyền và thiết kế cleanup bền vững.

## 14. Checklist trước khi triển khai

- [ ] Đã xác định app dùng **Servlet HttpSession**, WebFlux session hay stateless token.
- [ ] Đã chọn giá trị **server.servlet.session.timeout** (hoặc spring.session.timeout nếu dùng Spring Session) theo yêu cầu bảo mật và UX.
- [ ] Đã phân biệt rõ **idle timeout** với **absolute lifetime**, không giả định chúng giống nhau.
- [ ] Code kiểm tra session dùng **request.getSession(false)** khi không nên tạo session mới.
- [ ] Request API hết session/authentication trả **401 JSON**, không trả HTML 200 hoặc redirect ngoài hợp đồng.
- [ ] Request UI điều hướng trả login/điều hướng phù hợp, tránh vòng lặp.
- [ ] Logout invalidate session phía server và xử lý cookie phía browser theo tên/Path/Domain đúng.
- [ ] Cookie nhạy cảm được thiết kế với **HttpOnly, Secure, SameSite, Path/Domain** phù hợp HTTPS/proxy.
- [ ] **Cookie Max-Age** không bị hiểu nhầm là thời hạn dữ liệu HttpSession trên server.
- [ ] CORS/credentials/third-party cookie restrictions đã được kiểm chứng nếu frontend khác origin.
- [ ] Có Spring Security cho xác thực thực tế, session fixation protection và authorization.
- [ ] Nếu có **maximumSessions**, hiểu đúng expiredUrl và test concurrent-login policy.
- [ ] Nếu có Spring Session Redis/JDBC, đã kiểm tra store TTL, serialization, cleanup và behavior khi store lỗi.
- [ ] Không lưu credential/secret, resource mở hay object graph lớn trong session.
- [ ] Có test cho **no cookie, active session, idle-expired, invalidate/logout, multi-tab, multi-instance**.
- [ ] Không sử dụng event session expiration làm cơ chế duy nhất bảo đảm commit nghiệp vụ.
- [ ] Log/metrics không làm lộ session ID hoặc token.

## 15. Câu hỏi tự kiểm tra

**1. server.servlet.session.timeout=30m có nghĩa user tự logout đúng sau 30 phút tính từ login?** Không. Đây là **inactivity timeout**; request có liên quan session có thể làm mới mốc hoạt động.

**2. Cookie JSESSIONID còn sau 2 giờ có nghĩa HttpSession còn hiệu lực?** Không. Cookie age và server session timeout độc lập; cookie stale có thể trỏ tới session đã hết hạn.

**3. Tại sao getSession(false) phù hợp cho API kiểm tra phiên?** Vì nó không tạo phiên mới nếu không tìm thấy session hợp lệ; ứng dụng có thể trả 401 đúng.

**4. Nếu request mang session ID không hợp lệ, biết chắc nó đã timeout hay bị logout không?** Không. Có nhiều nguyên nhân session ID invalid; API nên trả thông điệp/response phù hợp mà không suy đoán nguyên nhân.

**5. Spring Security invalidSessionUrl có dùng cho API JSON không?** Có thể cấu hình, nhưng nó thường redirect, dễ phá hợp đồng API. API cần entry point/invalid-session strategy trả 401 có cấu trúc.

**6. expiredUrl của maximumSessions có tự xử lý mọi idle timeout không?** Không. Nó phục vụ chính sách session đồng thời; idle timeout và invalid session là luồng khác.

**7. Khi nào dùng spring.session.timeout?** Khi Spring Session auto-configuration đang quản lý session repository. Nếu không đặt nó trong Servlet app, cấu hình có thể fallback sang server.servlet.session.timeout.

**8. Vì sao MockMvc test trả 401 chưa chứng minh idle 1 phút?** MockMvc kiểm tra handler logic nhưng không mô phỏng đầy đủ clock/cleanup của container thật. Cần HTTP integration hoặc bài thử chạy server thật với thời gian chờ.

**9. Nếu một dashboard tự polling mỗi 20 giây, idle timeout 15 phút có tác dụng không?** Nếu những request polling chạm session, chúng có thể gia hạn session liên tục. Phải xác định thế nào là hoạt động có ý nghĩa nếu chính sách yêu cầu inactivity của người dùng.

**10. Tại sao session timeout không thay thế policy bảo vệ giao dịch quan trọng?** Vì thời hạn phiên không đảm bảo retry/idempotency hay commit. Khi session mất giữa một giao dịch, hệ thống vẫn phải có transaction và cơ chế khôi phục phù hợp.

## 16. Tài liệu chính thức

1. [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): **server.servlet.session.timeout**, cookie flags, **spring.session.timeout**, reactive session.
2. [Jakarta Servlet — HttpSession API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpsession): **getSession**, **getLastAccessedTime**, **setMaxInactiveInterval**, **invalidate** và lifecycle semantics.
3. [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): **invalidSessionUrl**, **InvalidSessionStrategy**, session fixation, logout, concurrent session control.
4. [Spring Session — Spring Boot with Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared **HttpSession** và Redis-backed session.
5. [Spring Boot — Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html): auto-configuration và quan hệ **spring.session.timeout** / **server.servlet.session.timeout**.
6. [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie): Max-Age, Expires, HttpOnly, Secure, SameSite và phạm vi cookie.

**Tổng kết:** **server.servlet.session.timeout** điều chỉnh thời gian không hoạt động của HttpSession, nhưng **không đặt absolute lifetime và không điều khiển cookie Max-Age**. Khi session không còn hợp lệ, đường xử lý phải rõ ràng: **API trả 401 có cấu trúc, UI điều hướng phù hợp, server không tự tạo lại session để che lỗi**. Với ứng dụng xác thực thật, hãy phối hợp Spring Security; với nhiều instance, kiểm soát shared session store bằng Spring Session và luôn kiểm chứng trên runtime đang triển khai.