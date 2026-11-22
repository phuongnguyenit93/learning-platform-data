# Giới hạn kích thước cookie và dữ liệu nhạy cảm trong phiên

## 1. Hai nơi lưu trữ dễ bị nhầm: cookie và HttpSession

Trong ứng dụng **Spring Boot Web MVC trên Servlet**, người dùng có thể giữ trạng thái giữa các HTTP request qua **cookie phiên**. Tuy nhiên, cookie và HttpSession có vai trò khác nhau:

- **Cookie** là cặp tên–giá trị được browser/client giữ, nhận từ response **Set-Cookie** và gửi lại dưới request header **Cookie** khi Domain, Path, Secure, SameSite cùng các chính sách khác cho phép.
- **HttpSession** là bộ chứa attribute do Servlet container hoặc session repository như Spring Session quản lý **phía server**. Dữ liệu có thể nằm trong RAM, Redis, JDBC tùy triển khai.
- **Session ID cookie** (thường là **JSESSIONID** với Servlet container mặc định) chỉ nên chứa một **mã định danh phiên mờ, ngẫu nhiên, khó đoán**. Nó cho server tra đúng session. Các attribute trong HttpSession **không tự được copy vào cookie**.
- **Database/object storage** là nơi tốt hơn cho hồ sơ người dùng, tài liệu, tệp lớn và dữ liệu bền vững; session chỉ giữ ID/reference nhỏ nếu thật sự cần.

Chính vì vậy, một giá trị lớn hơn 4 KiB vẫn có thể nằm trong HttpSession, trong khi JSESSIONID không lớn theo. Điều đó **không có nghĩa HttpSession không giới hạn tài nguyên hoặc luôn an toàn**. Bài này giải thích cả giới hạn kỹ thuật cookie và các giới hạn về bảo mật, bộ nhớ, vòng đời của dữ liệu trong phiên.

Phạm vi: **Spring Boot 3.3.x + Java 17+ + Spring MVC/Servlet**, dùng cookie tracking. **Spring WebFlux WebSession** là một mô hình API khác; các nguyên tắc cookie/privacy vẫn đúng nhưng không áp nguyên code HttpSession của bài sang WebFlux.

## 2. Giới hạn kích thước cookie: phải hiểu là byte và khả năng của browser

### 2.1. Mốc 4.096 byte trong RFC 6265

RFC 6265, mục 6.1, nêu mức năng lực **SHOULD** mà user agent thông dụng hỗ trợ tối thiểu:

| Giới hạn được khuyến nghị | Giá trị |
| --- | ---: |
| Dung lượng cho mỗi cookie, gồm tên, giá trị và thuộc tính theo cách tính trong RFC | **Ít nhất 4.096 byte** |
| Số cookie trên một domain | **Ít nhất 50** |
| Tổng cookie trong user agent | **Ít nhất 3.000** |

Đây là **khuyến nghị về mức hỗ trợ tối thiểu**, không phải một ngưỡng cố định giống nhau trên mọi Chrome, Firefox, Safari hay mọi phiên bản. Một browser có thể tính độ dài hơi khác, chặn cookie, evict cookie khi đầy hoặc không gửi lại cookie vì privacy settings. Server phải xử lý được khi client **không giữ hoặc không gửi** cookie.

Trong thực hành, cụm “cookie có hạn mức khoảng 4 KiB” có nghĩa **không nên dựa vào cookie để chứa dữ liệu dài**. Một ID phiên thông thường nên nhỏ hơn mốc đó rất nhiều. Đừng coi 4 KiB là ngân sách nên dùng hết.

Nguồn: https://www.rfc-editor.org/rfc/rfc6265.html#section-6.1

### 2.2. Java String.length() không phải kích thước cookie

**String.length()** đếm đơn vị UTF-16; cookie vận chuyển byte sau encoding. Ví dụ:
- **theme=dark**: 10 ký tự ASCII, 10 byte UTF-8.
- **note=Tiếng Việt**: 15 đơn vị UTF-16, **19 byte UTF-8** do các dấu tiếng Việt.

Khi serialize cookie, dữ liệu còn có thể cần percent encoding, Base64URL hoặc định dạng khác. Một chuỗi Unicode trên màn hình có thể tốn nhiều byte hơn số ký tự. Nếu cookie có chữ ký/chunk metadata, dung lượng lại tăng.

Để kiểm tra giới hạn thật, đo **name=value sau encode và các thuộc tính Set-Cookie**, đồng thời thử trên browser mục tiêu. Không lấy một con số String.length() và khẳng định “dưới 4 KiB nên chắc chắn hợp lệ”.

### 2.3. Một cookie nhỏ vẫn góp vào header rất lớn

Nhiều cookie khớp URL được trình duyệt gửi trong cùng request:

~~~http
Cookie: JSESSIONID=<opaque-id>; theme=dark; lang=vi; consent=accepted
~~~

**Request Cookie** chứa name=value, thường không gửi lại các thuộc tính Set-Cookie như HttpOnly/Secure/Expires. Tuy nhiên, **tổng số cookie** có thể tốn nhiều KiB. Mỗi request khớp scope lại gửi cookie, kể cả endpoint không cần đến giá trị đó.

Hậu quả của cookie/header quá lớn:
1. Tăng byte request, thời gian truyền và tài nguyên proxy/server.
2. Chạm giới hạn **request header size** của ingress, proxy hoặc web container, có thể nhận **400** hoặc **431 Request Header Fields Too Large** tùy cấu hình.
3. Browser có thể từ chối Set-Cookie quá dài hoặc dọn cookie cũ.
4. Các tầng logging nếu vô tình log nguyên header Cookie có thể phát tán session token.

**HTTP 431** nói về header request quá lớn, **không** tự chứng minh một cookie riêng vượt 4 KiB. Cookie lớn cũng không nhất thiết gây 431: nó có thể bị browser từ chối từ lúc nhận response Set-Cookie.

### 2.4. Vì sao không chia một JSON thành nhiều cookie?

Chia profile JSON thành cookie_1, cookie_2, cookie_3 tránh được một phần ngưỡng của **một cookie** nhưng tổng HTTP header vẫn lớn. Một mảnh có thể bị browser loại, client có thể sửa, và phải quản lý tính toàn vẹn, version, TTL, thứ tự ghép. Vì vậy giải pháp đúng thường là:
- Cookie: chỉ chứa định danh nhỏ hoặc preference ít byte.
- Server: giữ trạng thái tối thiểu có TTL.
- Database/storage: giữ đối tượng lớn cần truy vấn hoặc tồn tại lâu.

## 3. HttpSession không chịu giới hạn cookie 4 KiB, nhưng chịu giới hạn của server

Ở Spring MVC, code có thể dùng:

~~~java
// Fragment trong Controller/Servlet; chưa phải chương trình độc lập.
HttpSession session = request.getSession(true);
session.setAttribute("cartId", "cart-456");
session.setAttribute("itemCount", 3);
~~~

Mô hình:

~~~text
Browser                                   Server-side state
Cookie: JSESSIONID=ID_A  -------->       HttpSession[ID_A]
                                            cartId="cart-456"
                                            itemCount=3
~~~

Khi client gửi JSESSIONID ở request khác, container/session repository tra ID để tìm attributes. Browser **không tự nhận** cartId và itemCount trong cookie.

**getSession(true)**: lấy session hợp lệ hiện có hoặc tạo khi chưa có. **getSession(false)**: chỉ đọc session hợp lệ, trả null nếu không có. **invalidate()** làm session mất hiệu lực.

Nhưng nếu ứng dụng nhét String dài, file hoặc toàn bộ entity vào session, chi phí tăng ở nơi lưu:
- **Container in-memory**: heap, garbage collection, metadata, số concurrent session.
- **Spring Session Redis/JDBC**: serialization/deserialization, network I/O, RAM Redis hoặc dung lượng DB, replication, timeout, backup và độ tương thích object.
- **Nhiều replica**: local session ở instance A không tự có ở B chỉ vì browser gửi cùng cookie.

Ví dụ **10.000 session × 20 KiB payload ≈ 195,3 MiB** payload thô; thực tế dùng nhiều hơn bởi object overhead, metadata và bản sao. Hãy đo qua metrics/heap hoặc byte đã serialize, không dùng số này làm dự báo tuyệt đối.

**Không** coi HttpSession là database, cache toàn cục hay storage upload. Một file 5 MiB vẫn là dữ liệu lớn dù nó không đi vào JSESSIONID.

## 4. Những loại dữ liệu nên và không nên cất trong phiên

| Loại dữ liệu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Session ID ngẫu nhiên | Cookie session HttpOnly/Secure | Client chỉ mang khóa tra state |
| Theme, locale, tùy chọn không nhạy cảm | Cookie rất nhỏ hoặc preference store | Có thể mất; validate giá trị |
| Cart ID, số lượng item, cờ workflow ngắn | HttpSession/cache session | State tạm, nhỏ, có TTL |
| Hồ sơ cá nhân đầy đủ | Database/identity service | Phân quyền, cập nhật, retention |
| Danh sách hàng nghìn sản phẩm | Database/cache riêng | Không nhân bản vào mỗi session |
| Ảnh, PDF, file upload, binary payload | Private file/object storage | Tránh tràn heap/session store |
| Password, OTP chưa bảo vệ, API key, private key | Credential/secret store theo policy | Không lưu tự phát trong session hoặc cookie |
| Authorization state | Spring Security hoặc identity policy | Không tin cookie role=admin |
| JWT/JWS mang nhiều PII | Tránh; token tối thiểu khi thật sự cần | Signature không che payload; token có thể rất dài |
| Dữ liệu phải tồn tại sau restart | DB/object store hoặc session repository phù hợp | Session local có thể mất |

**Dữ liệu nhạy cảm trong HttpSession cũng cần bảo vệ.** Spring Security có thể lưu SecurityContext theo cơ chế framework nếu ứng dụng dùng session-based auth, nhưng code nghiệp vụ không nên tự lưu thêm password, access token, raw secret hay toàn bộ user profile không cần thiết.

**Giữ ID, không giữ cả object:** session có thể giữ một reportId; khi cần report, backend lấy từ kho dữ liệu, xác thực chủ sở hữu và quyền rồi mới trả kết quả.

## 5. Cookie không tự có tính bí mật hoặc tính toàn vẹn

### 5.1. HttpOnly, Secure, SameSite giải quyết những vấn đề khác nhau

- **HttpOnly**: hạn chế JavaScript thông thường đọc cookie từ document.cookie, nhưng **không mã hóa giá trị**; browser owner và backend vẫn có thể nhìn thấy.
- **Secure**: yêu cầu browser gửi cookie qua kết nối an toàn, thường HTTPS; không tự bật TLS và không mã hóa dữ liệu cookie lưu trên thiết bị.
- **SameSite**: hạn chế việc gửi cookie trong một số ngữ cảnh cross-site. Đây là **defense-in-depth cho CSRF**, không thay cơ chế CSRF token/origin validation.
- **Domain/Path**: quyết định phạm vi gửi cookie; **không** phải quyền truy cập nghiệp vụ.
- **Max-Age/Expires**: vòng đời cookie phía browser; **khác** server idle timeout.

Ví dụ nguy hiểm:

~~~http
Set-Cookie: userProfile={"email":"private@example.org"}; Path=/; HttpOnly; Secure
~~~

Ngay cả với HttpOnly và Secure, giá trị userProfile vẫn nằm ở client và không tự được mã hóa. Không để thông tin cá nhân, số giấy tờ, mật khẩu, dữ liệu thanh toán hoặc credential trong cookie thông thường.

### 5.2. Signed cookie khác encrypted cookie; JWT không mặc định bí mật

- **Cookie ký**: chống sửa payload nếu chữ ký được kiểm tra đúng, nhưng payload **vẫn có thể đọc được**.
- **Cookie mã hóa/xác thực**: yêu cầu key management, nonce, rotation, chống replay, expiry, giới hạn size. Mã hóa không làm cookie thành storage vô hạn.
- **JWT JWS**: payload là Base64URL encode và được ký; **không** tự được mã hóa. Người cầm JWT có thể đọc claim nếu chỉ ký.
- **Opaque session ID**: không tiết lộ thông tin người dùng theo nội dung ID; server giữ trạng thái liên quan phía sau.

Không tự thiết kế cơ chế crypto/cookie riêng nếu Spring Security và session framework đã xử lý được bài toán. Nếu JWT chứa quyền, cần giải quyết token hết hạn, thu hồi và quyền stale; một claim “admin” từng hợp lệ không phải hợp đồng cấp quyền vĩnh viễn.

### 5.3. Session cookie phải được bảo vệ như bearer secret

Người sở hữu session ID hợp lệ có thể chiếm phiên trong hệ thống dựa vào ID đó. Do đó:
1. Dùng ID ngẫu nhiên do framework/container tạo, không tự dùng email/userId.
2. HTTPS suốt phiên; Secure + HttpOnly ở production.
3. SameSite phù hợp và CSRF protection cho hành động thay đổi trạng thái.
4. Phòng chống XSS, session fixation và token leakage.
5. Invalidate khi logout; thay session ID khi nâng quyền theo framework.
6. Không đưa session ID vào URL, logs, analytics, stack trace chia sẻ.
7. Giới hạn cookie Domain/Path theo thực tế; cookie **không** cô lập bởi TCP port.

## 6. Vì sao dữ liệu nhạy cảm trong HttpSession vẫn có thể bị lộ?

“Phía server” không đồng nghĩa “không ai đọc được”. Ví dụ:
- Code log toàn bộ session attributes hoặc đối tượng SecurityContext chứa chi tiết người dùng.
- Heap dump, debug endpoint hoặc crash report có dữ liệu trong RAM.
- Redis/DB session store có ACL yếu, không bật TLS khi cần hoặc backup không được bảo vệ.
- User profile trong attribute bị một API trả nhầm cho request khác do lỗi authorization.
- Session ID bị đánh cắp hoặc session fixation dẫn tới truy cập dữ liệu đúng ID nhưng sai người.
- Serialization lưu toàn bộ object graph không cần thiết; các bản sao/backup giữ dữ liệu quá lâu.
- Stale permission trong session khiến người đã bị thu hồi quyền vẫn truy cập được.

Các biện pháp tương ứng:
- Tối thiểu hóa attribute; lưu khóa nhỏ thay vì object lớn.
- TTL/idle timeout, dọn attribute sau workflow.
- Bảo vệ session store bằng ACL, encryption, TLS, backup retention đúng policy.
- Không log cookie hoặc nội dung session nhạy cảm; giới hạn heap dump/debug.
- Dùng Spring Security để quản lý xác thực/ủy quyền, refresh/invalidate khi quyền thay đổi.
- Kiểm tra quyền ở mỗi thao tác nhạy cảm, không chỉ dựa vào một cờ cũ trong session.
- Không serialize JPA/Hibernate Entity có lazy relation vào session nếu không có kế hoạch version/serialization rõ ràng.

Cookie ID nhỏ và “khó đoán” giúp chống đoán mò; nó **không** chống kẻ đã đánh cắp ID thật. Security là nhiều lớp phòng vệ.

## 7. Session timeout không phải cookie expiry

Một cookie có **Max-Age=24h** có thể còn trong browser trong khi HttpSession server hết hạn sau **15 phút** không hoạt động. Khi đó browser gửi cookie cũ nhưng server không còn state hợp lệ. Ngược lại, nếu browser xóa cookie trước, server có thể còn state đến hết TTL nhưng client không liên kết lại được.

Cần phân biệt:
- Cookie Max-Age/Expires: phía client.
- HttpSession idle timeout/invalidate: phía server.
- Session store TTL/eviction: phía repository.
- Logout: phải vô hiệu server-side, không chỉ xóa cookie phía client.

Đóng trình duyệt không phải luôn là bằng chứng session đã bị xóa: browser có cơ chế khôi phục session cookie. Đừng dùng “close tab” như một biện pháp logout bảo mật.

### 7.1. Multi-replica và cookie đúng nhưng session sai

Nếu instance A có HttpSession local còn B không có, load balancer chuyển request từ A sang B sẽ gây mất state dù cookie hoàn toàn hợp lệ. Có thể dùng sticky session/affinity, session repository chia sẻ như Spring Session Redis/JDBC, hoặc thiết kế stateless nếu nghiệp vụ phù hợp. Mỗi lựa chọn có chi phí và rủi ro riêng.

Khi dùng Spring Session, cookie có thể tên **SESSION** thay vì JSESSIONID theo DefaultCookieSerializer. Đừng hard-code một tên duy nhất khi kiểm tra ứng dụng có session hay không.

## 8. Spring Boot cấu hình cookie/session ở đâu?

Với Spring Boot 3.3 Servlet stack, một cấu hình tham khảo cho **production qua HTTPS**:

~~~yaml
server:
  servlet:
    session:
      tracking-modes: cookie
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Giải thích:
- **tracking-modes: cookie**: dùng cookie để liên kết phiên thay vì URL session tracking.
- **timeout**: timeout không hoạt động phía server, không đặt giới hạn dung lượng cookie.
- **http-only**: giảm nguy cơ JS đọc ID.
- **secure**: browser chỉ gửi trên kết nối an toàn; production phải có HTTPS và cấu hình reverse proxy/trusted headers đúng.
- **same-site**: giúp chống một số cross-site request; vẫn cần CSRF protection.
- **path**: chọn phạm vi URL phù hợp, không cần quá rộng nếu app chỉ ở một context path.

Các property **server.servlet.session.cookie** chủ yếu điều khiển **cookie session**, không tự áp lên **mọi cookie tùy biến**. Với cookie tùy biến, dùng Spring **ResponseCookie** hoặc cơ chế cấu hình SameSite phù hợp. Với Spring Session, kiểm tra CookieSerializer/repository thực tế.

**Môi trường demo local HTTP** ở phần tiếp theo **không bật Secure** để curl qua localhost có thể gửi lại cookie. Đừng sao chép cấu hình local này lên production.

## 9. Ví dụ Spring Boot MVC Java 17 chạy được

Ứng dụng mẫu chứng minh:
1. GET **/api/state** không tạo session khi chưa có.
2. POST **/api/session/demo** lưu String **8.192 ký tự ASCII vào HttpSession phía server** chỉ để đối chiếu với ngưỡng cookie 4 KiB.
3. POST **/api/preference** tạo cookie nhỏ **theme=dark**.
4. GET lại với cookie jar tra đúng session và theme.
5. DELETE **/api/session/demo** invalidate session nhưng không xóa cookie theme.

Đây là **demo kỹ thuật**, không phải khuyến nghị lưu 8 KiB hoặc dữ liệu nhạy cảm vào session trong production. Thực tế nên lưu ID nhỏ, dữ liệu lớn trong DB/object store.

### 9.1. Cấu trúc và pom.xml

~~~text
cookie-session-budget/
├── pom.xml
└── src/main/
    ├── java/com/example/cookiebudget/
    │   └── CookieSessionBudgetApplication.java
    └── resources/application.yml
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>cookie-session-budget</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**src/main/resources/application.yml**, chỉ dành cho local HTTP:

~~~yaml
server:
  port: 8080
  servlet:
    session:
      tracking-modes: cookie
      timeout: 15m
      cookie:
        http-only: true
        same-site: lax
        path: /
~~~

Không bật Secure trên HTTP local. Production cần HTTPS và **server.servlet.session.cookie.secure: true**, cùng Secure cho cookie tùy biến nếu phải được bảo vệ.

### 9.2. Java code một file đầy đủ

**src/main/java/com/example/cookiebudget/CookieSessionBudgetApplication.java**:

~~~java
package com.example.cookiebudget;

import java.time.Duration;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieSessionBudgetApplication {
    public static void main(String[] args) {
        SpringApplication.run(CookieSessionBudgetApplication.class, args);
    }
}

@RestController
class BudgetController {

    private static final String KEY = "demoText";
    private static final int DEMO_LENGTH = 8192;

    @GetMapping(path = "/api/state", produces = MediaType.TEXT_PLAIN_VALUE)
    String state(HttpServletRequest request,
                 @CookieValue(name = "theme", required = false) String theme) {
        HttpSession session = request.getSession(false);
        Object data = session == null ? null : session.getAttribute(KEY);
        int length = data instanceof String value ? value.length() : 0;

        String safeTheme = "dark".equals(theme) || "light".equals(theme)
                ? theme : "absent";

        return "sessionActive=" + (session != null)
                + ", storedChars=" + length
                + ", theme=" + safeTheme + "\n";
    }

    @PostMapping(path = "/api/session/demo",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    String demo(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute(KEY, "x".repeat(DEMO_LENGTH));
        return "storedChars=" + DEMO_LENGTH + "\n";
    }

    @PostMapping(path = "/api/preference",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    ResponseEntity<String> preference() {
        ResponseCookie cookie = ResponseCookie.from("theme", "dark")
                .path("/")
                .httpOnly(true)
                .sameSite("Lax")
                .maxAge(Duration.ofDays(1))
                .build();

        return ResponseEntity.ok()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .body("themeCookieSet=dark\n");
    }

    @DeleteMapping(path = "/api/session/demo",
                   produces = MediaType.TEXT_PLAIN_VALUE)
    String logoutDemo(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return "sessionInvalidated=true\n";
    }
}
~~~

**Giải thích chi tiết:**
- **getSession(false)** trong GET không tự tạo state.
- **getSession(true)** trong POST tạo session khi chưa có; nếu client đã có session hợp lệ thì có thể dùng lại.
- **session.setAttribute** lưu String 8.192 ký tự tại server, **không** đưa 8.192 ký tự vào cookie.
- Cookie theme độc lập với JSESSIONID, chỉ là preference không nhạy cảm; HttpOnly được đặt vì demo không cần JS đọc.
- **@CookieValue** nhận giá trị client cung cấp; chỉ chấp nhận dark/light, không lấy một cookie nào làm role/permission.
- Không log session.getId(), không đưa nó vào URL hoặc response.
- **invalidate()** chấm dứt server session cũ; cookie theme vẫn còn theo vòng đời riêng.
- Demo không cài Spring Security; ứng dụng auth thật nên dùng framework quản lý login/logout, CSRF, fixation và authorization.

### 9.3. Build và chạy

Ở thư mục **cookie-session-budget**, cần Java 17+, Maven, cổng 8080 còn trống:

~~~bash
mvn package
java -jar target/cookie-session-budget-1.0.0.jar
~~~

Lệnh curl dưới đây chạy ở terminal khác. Với PowerShell trên Windows dùng **curl.exe** thay vì alias curl nếu cần hỗ trợ các cờ chuẩn.

**Bước 1 — chưa có cookie/session:**

~~~bash
curl -s http://localhost:8080/api/state
~~~

Body:

~~~text
sessionActive=false, storedChars=0, theme=absent
~~~

**Bước 2 — tạo session, lưu Set-Cookie vào jar:**

~~~bash
curl -i -c demo-cookies.txt -X POST \
  http://localhost:8080/api/session/demo
~~~

Body:

~~~text
storedChars=8192
~~~

Response thường có header **Set-Cookie: JSESSIONID=...** chứa một ID ngẫu nhiên nhỏ, **không chứa** toàn bộ 8.192 ký tự. File demo-cookies.txt chứa token, nên đừng đưa vào Git, log hoặc chat công khai.

**Bước 3 — gửi ID phiên và nhận thêm cookie theme:**

~~~bash
curl -i -b demo-cookies.txt -c demo-cookies.txt -X POST \
  http://localhost:8080/api/preference
~~~

Body:

~~~text
themeCookieSet=dark
~~~

**Bước 4 — GET với cả hai cookie:**

~~~bash
curl -s -b demo-cookies.txt http://localhost:8080/api/state
~~~

Body:

~~~text
sessionActive=true, storedChars=8192, theme=dark
~~~

**Bước 5 — invalidate session:**

~~~bash
curl -s -b demo-cookies.txt -X DELETE \
  http://localhost:8080/api/session/demo
curl -s -b demo-cookies.txt http://localhost:8080/api/state
~~~

Body lần lượt:

~~~text
sessionInvalidated=true
~~~

~~~text
sessionActive=false, storedChars=0, theme=dark
~~~

Giải thích: session server cũ đã mất hiệu lực, còn custom cookie theme độc lập vẫn được client gửi. Đây là **body của từng HTTP response**, không phải toàn bộ stdout khi curl chạy có cờ -i.

Không đặt toàn bộ session attributes vào JSON response trong demo, vì mục tiêu đang kiểm tra **nơi lưu dữ liệu**. Nếu code trả nội dung profile ra body, đó là quyết định API của ứng dụng chứ không phải Servlet tự xuất toàn bộ session qua cookie.

## 10. Java 17 độc lập: chứng minh String.length() khác UTF-8 byte length

Tạo file **CookieBytesDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;

public class CookieBytesDemo {
    public static void main(String[] args) {
        String ascii = "theme=dark";
        String unicode = "note=Tiếng Việt";

        System.out.println("asciiChars=" + ascii.length());
        System.out.println("asciiBytes=" +
                ascii.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("unicodeChars=" + unicode.length());
        System.out.println("unicodeBytes=" +
                unicode.getBytes(StandardCharsets.UTF_8).length);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac -encoding UTF-8 CookieBytesDemo.java
java CookieBytesDemo
~~~

Stdout **chính xác**:

~~~text
asciiChars=10
asciiBytes=10
unicodeChars=15
unicodeBytes=19
~~~

Đây là số byte UTF-8 của chuỗi được chọn, **không** cộng thêm percent encoding, tên/thuộc tính trong Set-Cookie. Không nên dùng dữ liệu người dùng thật để kiểm tra ngưỡng.

## 11. Phát hiện dữ liệu session/cookie phình to và rò rỉ

### 11.1. Metrics hữu ích

| Quan sát | Ý nghĩa |
| --- | --- |
| Tổng Cookie header bytes và số cookie/request | Tìm request phình to |
| HTTP 400/431 ở proxy hoặc container | Phân biệt header limit với logic ứng dụng |
| Cookie bị DevTools đánh dấu blocked | Xem size, Domain, Path, Secure, SameSite |
| Số phiên đang active và idle time | Dự báo footprint và timeout |
| Heap/GC, session attribute count | Phát hiện session in-memory nặng |
| Serialized session bytes trong Redis/JDBC | Tìm đối tượng lớn, network/store cost |
| Store eviction, deserialization failure, backup size | Tìm rủi ro khi scale/nâng phiên bản |
| Session invalidation/logout failure | Phát hiện phiên không được thu hồi |

**Không ghi raw session ID/cookie value làm metric label**; vừa rò rỉ bearer secret vừa làm metrics có cardinality không kiểm soát. Đừng log nguyên Cookie header để “debug dễ hơn”. Dùng correlation ID độc lập, log có masking và retention.

### 11.2. Những lỗi thường gặp

| Tình huống | Phân tích | Hướng sửa |
| --- | --- | --- |
| Browser không gửi cookie vừa nhận | Cookie bị từ chối/evict hoặc scope không khớp | Kiểm tra DevTools, size, Secure/SameSite/Domain/Path |
| Nhiều cookie, API trả 431 | Tổng request header vượt limit | Giảm dữ liệu cookie, đo tổng header, kiểm tra proxy |
| Redis RAM tăng dù cookie nhỏ | HttpSession serialized payload lớn | Chỉ lưu reference, hạn số lượng/TTL |
| Pod A có session, Pod B không có | Local session không chia sẻ | Shared store/affinity với trade-off rõ |
| JWT signed lộ email trong payload | Ký không mã hóa | Giảm claim hoặc dùng token opaque/mã hóa khi cần |
| Cookie role=admin thay được | Backend tin dữ liệu client | Authorization từ framework/store tin cậy |
| HttpOnly bật nhưng vẫn CSRF | Browser tự gửi cookie | CSRF protection và SameSite đúng threat model |
| Logout xóa cookie nhưng token cũ vẫn dùng được | Server chưa invalidate/revoke | Hủy session server-side |
| Session còn nhưng cookie đã hết | Hai vòng đời khác nhau | Thiết kế fallback/login lại |
| Entity ORM trong session gây lỗi sau deploy | Serialization/schema khác phiên bản | Lưu ID/value nhỏ, migration strategy |

## 12. Checklist bảo mật và vận hành

- Dùng cookie **ngắn và ít**, không đặt profile, file hoặc secret vào cookie.
- Đếm byte sau encode và xem **tổng request header**, không chỉ một cookie.
- Session ID chỉ là định danh khó đoán do framework cấp; không để ID trong URL/log.
- Bật HTTPS, Secure, HttpOnly, SameSite và scope hợp lý cho cookie phiên ở production.
- XSS/CSRF defense và authorization là yêu cầu riêng; cookie flags không thay được.
- Dữ liệu nhạy cảm dù lưu phía server vẫn cần data minimization, ACL, TLS, encryption/backup policy và retention.
- Giữ session attribute nhỏ, dọn sớm và có timeout; dữ liệu lớn chuyển sang DB/object storage.
- Không tin cookie do client gửi, luôn validate preference/identifier; không cấp quyền theo cookie role.
- Với Spring Session distributed, kiểm tra TTL, byte serialization, version compatibility, store health và rollout.
- Logout invalidate/revoke server-side, xóa cookie theo scope khi cần.
- Test cookie bị xóa, bị sửa, bị chặn, session expire, nhiều cookie, request header limit, multi-replica.
- Đo metrics tổng hợp mà không thu thập token hay attribute nhạy cảm.

## 13. Bài tập củng cố

**1. HttpSession giữ String 12 KiB. Browser có phải lưu cookie 12 KiB không?**  
Không trong cơ chế HttpSession server-side thông thường. Cookie giữ session ID; String ở server.

**2. Vì sao 15 cookie, mỗi cookie 1 KiB, vẫn có thể làm request lỗi?**  
Tổng header có thể vượt limit proxy/server, dù từng cookie đều dưới mức khoảng 4 KiB.

**3. HttpOnly và Secure có che giấu email lưu trực tiếp trong cookie không?**  
Không. HttpOnly hạn chế JS, Secure yêu cầu vận chuyển an toàn; không tự mã hóa.

**4. Một claim email trong JWT JWS signed có được mã hóa không?**  
Không mặc định; payload signed có thể decode. Integrity khác confidentiality.

**5. Cookie Max-Age 1 ngày, HttpSession timeout 15 phút. Sau 2 giờ idle, session cũ còn không?**  
Thường không nếu server đã expire session, dù browser vẫn giữ cookie.

**6. Tại sao không nên lưu byte[] PDF trong HttpSession?**  
Tốn heap/serialized store, nhân theo số session, gây GC/network/replication chi phí lớn.

**7. Một cookie role=admin tự sửa bằng DevTools được backend tin. Lỗi gì?**  
Tin client data không được xác thực; cần authorization đúng framework/server-side.

**8. Vì sao xóa cookie khi logout chưa đủ?**  
Bản sao session ID bị lấy từ trước có thể còn sử dụng nếu server session chưa bị invalidate.

**9. Dùng Spring Session Redis có hết giới hạn bộ nhớ không?**  
Không; chỉ chuyển chi phí sang Redis/network/serialization và các giới hạn store.

**10. Nếu browser gửi JSESSIONID nhưng request rơi vào instance không có phiên, có phải cookie sai không?**  
Không nhất thiết; có thể session local không chia sẻ giữa replica.

## 14. Kết luận

**Cookie bị giới hạn bởi browser và HTTP header**, vì vậy chỉ nên mang một ID phiên mờ hoặc tùy chọn nhỏ, không nhạy cảm. **HttpSession server-side không chịu ngưỡng cookie 4 KiB**, nhưng vẫn chịu giới hạn RAM, storage, serialization, timeout và an toàn thông tin.

Mô hình thực tế thường tốt hơn là: **Cookie nhỏ → Session ID an toàn → Session state tối thiểu → Dữ liệu lớn/nhạy cảm ở database hoặc kho riêng có bảo vệ**. Chọn đúng tầng lưu trữ, giới hạn vòng đời và kiểm soát quyền quan trọng hơn việc cố nhét thêm dữ liệu vào cookie hoặc session.

## Tài liệu tham khảo chính thức

- RFC 6265 §6.1 — Cookie limits: https://www.rfc-editor.org/rfc/rfc6265.html#section-6.1
- MDN — Set-Cookie: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
- MDN — HTTP Cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — CSRF Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- Spring Boot 3.3 — Servlet Web Applications/SameSite: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Application Properties: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Jakarta Servlet 6.0 — HttpSession: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
