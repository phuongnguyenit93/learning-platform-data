# Thời điểm tạo phiên và liên kết phiên bằng cookie

## 1. Mục tiêu: hiểu chính xác “session được tạo khi nào?”

Trong ứng dụng **Spring Boot dùng Spring MVC/Servlet**, HTTP vốn không giữ trạng thái giữa các request. Hai request gửi tới cùng một server không tự nhiên được coi là của cùng một người dùng. **HttpSession** cho phép server giữ dữ liệu theo từng phiên, còn **session cookie** giúp client gửi lại một định danh để server tìm đúng phiên đó.

Điểm cốt lõi của bài là phân biệt rõ ba thời điểm:

1. **Request đến server:** chưa đủ cơ sở để kết luận server đã tạo một HttpSession. Một endpoint stateless có thể trả lời mà không tạo phiên.
2. **Ứng dụng hoặc framework yêu cầu tạo phiên:** chẳng hạn gọi **request.getSession()** hay **request.getSession(true)** khi chưa có phiên hợp lệ. Lúc đó Servlet container tạo một HttpSession phía server.
3. **Định danh phiên được chuyển cho client và được gửi lại:** với cơ chế theo dõi bằng cookie, response thường chứa **Set-Cookie: JSESSIONID=...**; browser lưu cookie và gửi header **Cookie: JSESSIONID=...** ở request tiếp theo nếu quy tắc Domain, Path, Secure, SameSite cho phép.

**Session không phải cookie.** Session là trạng thái phía server (hoặc kho session dùng chung), còn cookie thường chỉ chứa **mã định danh khó đoán** để tìm lại trạng thái. Một cookie tồn tại không chứng minh phiên phía server còn hợp lệ; một phiên vừa được tạo cũng có thể chưa được client nhận/hoàn trả cookie.

Bài học tập trung vào chủ đề cha **Phiên và cookie**, cơ chế **Servlet HttpSession**, Spring Boot MVC và cách xác nhận bằng HTTP. Không dùng chung cách giải thích này với **Spring WebFlux WebSession** hoặc JWT stateless, vì đó là những mô hình khác.

## 2. Sơ đồ từ request đầu tiên đến request quay lại

Giả sử ứng dụng dùng Spring MVC + embedded Tomcat, cookie tracking, tên cookie mặc định thường là **JSESSIONID** và chưa cài Spring Session. Trên một trình duyệt mới:

~~~text
Client                               Spring Boot / Servlet container
  |                                            |
  | GET /api/catalog (không cần session)       |
  |------------------------------------------->|
  |         Không có lệnh tạo HttpSession      |
  |<-------------------------------------------|
  | 200 OK; thường không có Set-Cookie phiên   |
  |                                            |
  | POST /api/session/visit                    |
  |------------------------------------------->|
  |    Controller gọi request.getSession(true) |
  |    Container tạo session S1, ID ngẫu nhiên |
  |<-------------------------------------------|
  | 200 OK                                    |
  | Set-Cookie: JSESSIONID=ID_S1; Path=/; ...  |
  |                                            |
  | Client lưu ID_S1 nếu policy cho phép       |
  |                                            |
  | GET /api/session/status                   |
  | Cookie: JSESSIONID=ID_S1                  |
  |------------------------------------------->|
  |     Container tra session bằng ID_S1       |
  |     request.getSession(false) trả S1       |
  |<-------------------------------------------|
  | 200 OK; dữ liệu lấy từ session S1          |
  |                                            |
  | ... idle timeout, invalidate hoặc mất S1   |
  |                                            |
  | GET /api/session/status                   |
  | Cookie: JSESSIONID=ID_S1 (có thể vẫn còn) |
  |------------------------------------------->|
  |     Không tìm được session hợp lệ          |
  |     getSession(false) trả null             |
  |<-------------------------------------------|
  | 200 OK; endpoint báo chưa có phiên         |
~~~

**Vì sao response có Set-Cookie chứ request không có?** Header **Set-Cookie** là hướng **server → client**; header **Cookie** là hướng **client → server**. Cookie được liên kết với request **tiếp theo**, sau khi client đã tiếp nhận Set-Cookie, trừ khi một session trước đó đã tồn tại.

Trong thực tế server có thể đặt cookie ở thời điểm khác nếu framework đã tạo session sớm hơn, hoặc có cơ chế session tracking khác. Các mốc trên là **trình tự giải thích phổ biến**, không phải cam kết rằng mọi GET hay mọi POST sẽ hoạt động hệt như ví dụ bất kể middleware nào.

## 3. Servlet API quyết định có tạo session hay chỉ đọc session

**jakarta.servlet.http.HttpServletRequest** cung cấp những phương thức quan trọng:

| Lệnh | Ý nghĩa | Nếu chưa có session hợp lệ |
| --- | --- | --- |
| request.getSession() | Lấy phiên hiện tại, nếu không có thì tạo mới | **Tạo mới** |
| request.getSession(true) | Tương đương getSession() về chính sách tạo | **Tạo mới** |
| request.getSession(false) | Chỉ lấy phiên hợp lệ hiện có | Trả **null**; không tự tạo |
| request.getRequestedSessionId() | ID client đã cung cấp ở request hiện tại, nếu có | Có thể null hoặc là ID đã hết hiệu lực |
| request.isRequestedSessionIdValid() | ID được trình bày có hợp lệ trong context hiện tại không | **false** nếu không hợp lệ/không có |
| request.isRequestedSessionIdFromCookie() | ID yêu cầu lấy từ cookie không | **false** nếu không có ID cookie |
| request.changeSessionId() | Đổi ID của session hiện có, không đổi toàn bộ attributes | Không dùng nếu chưa có session hiện tại |

Cần tránh nhầm **request.getRequestedSessionId()** với **request.getSession(false).getId()**:
- **Requested session ID** là thông tin từ phía client, có thể cũ, giả, không hợp lệ.
- **Current session ID** là ID của HttpSession hợp lệ mà container đã trả về.
- Khi session không tồn tại, gọi getSession(false).getId() trực tiếp sẽ ném **NullPointerException**. Kiểm tra null trước.
- Khi một request gửi cookie ID cũ, getRequestedSessionId() vẫn **có thể trả ID cũ**, trong khi isRequestedSessionIdValid() là false và getSession(false) là null.

### 3.1. Đọc mà không tạo: getSession(false)

~~~java
// Fragment trong Spring MVC Controller hoặc Filter; không phải file độc lập.
HttpSession session = request.getSession(false);
if (session == null) {
    // Chưa có phiên hợp lệ: hiển thị trạng thái khách.
} else {
    Object cart = session.getAttribute("cart");
    // Đọc cart nếu nó đã được lưu.
}
~~~

Đây là lựa chọn phù hợp cho endpoint chỉ muốn **quan sát** trạng thái, ví dụ kiểm tra người dùng có giỏ hàng tạm hay không. Một GET xem sản phẩm thuần túy không nhất thiết phải tạo session nếu không có nhu cầu lưu trạng thái.

Tuy nhiên, **chỉ riêng code Controller không gọi getSession(true)** chưa chứng minh request đó không tạo session. Một Filter, framework, JSP, cơ chế CSRF hoặc authentication flow có thể đã tạo phiên trước khi Controller được gọi.

### 3.2. Tạo khi có nhu cầu: getSession(true)

~~~java
// Fragment trong Spring MVC; nên dùng cho hành động thật sự cần state.
HttpSession session = request.getSession(true);
session.setAttribute("preferredLanguage", "vi");
~~~

Nếu request đã liên kết được với phiên hợp lệ, **trả lại phiên cũ**, không tạo thêm phiên mới chỉ vì gọi true. Nếu chưa có, tạo session mới, gán ID và lưu attribute. Vì vậy **“getSession(true) được gọi” không đồng nghĩa “phiên mới chắc chắn được tạo”**.

### 3.3. HttpSession.isNew() nói gì?

**session.isNew()** cho biết session mới hoặc client chưa tham gia session bằng thông tin theo dõi mà container nhận biết. Nó hữu ích khi phân tích request đầu tiên nhưng **không phải** chỉ báo tuyệt đối “user vừa đăng nhập”, “session được tạo đúng tại dòng code này” hoặc “client sẽ nhận được cookie”.

Nếu client không gửi lại cookie vì chặn cookie, sai scope hoặc bỏ cookie, mỗi request gọi getSession(true) **có thể** tạo phiên mới và isNew() lại true. Khi logout và tạo phiên mới, “new session” cũng không đồng nghĩa “người dùng mới”.

## 4. Khi nào session cookie được phát hành?

Khi ứng dụng tạo session mới và dùng **COOKIE tracking**, Servlet container thường thêm **Set-Cookie** vào HTTP response để chuyển session ID. Ví dụ minh họa; ID cố tình dùng ký hiệu giả, không phải token thật:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=<opaque-id>; Path=/; HttpOnly; SameSite=Lax
Content-Type: text/plain;charset=UTF-8

active=true, visits=1
~~~

Trong response thật, tên cookie, Path, Secure, SameSite, Max-Age và các thuộc tính khác phụ thuộc cấu hình/container. **Không** giả định response nào cũng có Set-Cookie hoặc luôn có cùng tập thuộc tính.

### 4.1. Thời điểm quan trọng: trước khi response bị commit

Response headers phải được gửi **trước** phần body đã commit. Nếu ứng dụng cố gọi getSession(true) **sau khi response đã commit** trong tình huống cần viết cookie mới, container có thể không thể tạo/liên kết phiên như mong muốn và Servlet API có thể báo **IllegalStateException**. Hãy tạo session tại giai đoạn xử lý request còn có thể ghi headers, không làm nó muộn trong một stream đã flush response.

Không dùng thao tác “đợi đến khi render xong rồi mới tạo session”; nếu session phục vụ nghiệp vụ của request, tạo hoặc truy xuất nó trong luồng xử lý có lifecycle rõ ràng.

### 4.2. Một cookie được gửi khi nào ở request kế tiếp?

Browser đánh giá scope và chính sách cookie:

- **Host/Domain:** cookie mặc định chỉ cho host đã đặt; Domain được cấu hình có thể mở rộng cho subdomain phù hợp.
- **Path:** chỉ gửi tới URL path được quy tắc cookie cho phép; app context path có thể ảnh hưởng Path mặc định.
- **Secure:** cookie Secure chỉ được gửi qua kênh được browser coi là an toàn, chủ yếu HTTPS; đừng trông chờ Secure cookie hoạt động giống nhau trên HTTP local.
- **SameSite:** ảnh hưởng gửi cookie trong ngữ cảnh cross-site.
- **Expires/Max-Age:** cookie có thể hết hạn ở client trước khi session server hết hạn, hoặc còn tồn tại khi server đã xóa session.
- **Chính sách browser:** chặn cookie, privacy settings, bên thứ ba, partitioning và hành vi restore có thể thay đổi việc gửi.

**Cookie không cô lập theo cổng TCP** như **localhost:8080** và **localhost:9090**. Hai dịch vụ trên cùng host có thể chia sẻ cookie scope và cùng tên cookie nếu Path/Domain trùng, gây xung đột phát triển. Cổng không phải thuộc tính scope của HTTP cookie.

### 4.3. Cookie session không có nghĩa cookie chứa dữ liệu session

Không lưu user object, mật khẩu, giỏ hàng đầy đủ hay quyền hạn trong **JSESSIONID**. Browser thường chỉ giữ một chuỗi ID. Server dùng ID đó để tìm **HttpSession** trong kho của container hoặc trong kho chung nếu dùng Spring Session.

Ai chiếm được một session ID hợp lệ có thể mạo danh session nếu hệ thống chỉ dựa vào cookie đó để chứng thực. Vì vậy ID phải khó đoán, truyền qua HTTPS, không lộ qua log/query string, có cơ chế logout/timeout và được bảo vệ khỏi fixation/hijacking.

## 5. HttpSession có vòng đời riêng với cookie

Trong Servlet, **HttpSession** có các thuộc tính và phương thức:

| Thành phần | Ý nghĩa |
| --- | --- |
| session.getId() | ID của phiên hiện tại; coi là dữ liệu nhạy cảm |
| session.getCreationTime() | Mốc tạo session phía server |
| session.getLastAccessedTime() | Mốc truy cập gần nhất do container ghi nhận |
| session.getAttribute(name) | Dữ liệu phiên phía server |
| session.setAttribute(name, value) | Ghi attribute vào phiên |
| session.removeAttribute(name) | Xóa attribute cụ thể |
| session.getMaxInactiveInterval() | Khoảng không hoạt động tối đa, tính theo giây |
| session.setMaxInactiveInterval(seconds) | Đổi idle timeout của phiên này |
| session.invalidate() | Làm session hiện tại không còn hợp lệ, tháo gỡ attributes |
| session.isNew() | Kiểm tra trạng thái mới/đã được client tham gia |

**Idle timeout** thường được tính theo khoảng không có request nào hợp lệ liên kết tới session. Một request hợp lệ có thể cập nhật thời điểm truy cập session, ngay cả khi logic nghiệp vụ chỉ đọc; chính xác cách container ghi nhận theo Servlet lifecycle.

Phân biệt ba loại hết hạn:

1. **Cookie phía browser hết hạn/biến mất:** client không gửi ID nữa, dù server có thể còn giữ phiên trong một khoảng thời gian.
2. **Server session hết hạn hoặc bị invalidate:** client có thể vẫn gửi cookie cũ nhưng server không tìm thấy phiên hợp lệ.
3. **Đăng nhập/hệ thống chủ động đổi session ID:** session có thể giữ attribute nhưng ID cũ không còn hợp lệ; client phải nhận/giữ ID mới.

Một **browser session cookie** thường không có Max-Age/Expires cố định; nhưng trình duyệt có cơ chế restore phiên sau khi mở lại nên không được coi “đóng tab/browser” là bằng chứng chắc chắn server đã logout hoặc session hết hạn.

### 5.1. Điều gì xảy ra khi cookie cũ vẫn được gửi?

~~~text
Cookie: JSESSIONID=ID_OLD
             |
             v
Container lookup session(ID_OLD)
             |
     +-------+--------+
     |                |
 Có, còn hợp lệ     Không còn hợp lệ
     |                |
getSession(false)   getSession(false)
 -> session cũ       -> null
     |                |
Có thể dùng tiếp     getSession(true)
                     -> tạo session mới ID_NEW
                     -> Set-Cookie mới nếu cần
~~~

**Một cookie được browser gửi không tự tạo lại nội dung cũ.** Session phải tồn tại trong kho phù hợp và còn hiệu lực. Nếu ứng dụng dùng session store in-memory rồi restart, cookie cũ có thể tồn tại nhưng session không còn. Việc mất dữ liệu và tính bền vững phụ thuộc container/session repository và cấu hình triển khai.

## 6. Chạy ví dụ thực tế: một request chỉ đọc và một request chủ động tạo phiên

Ví dụ bên dưới là dự án **Spring Boot 3.3.13 + Spring MVC + Java 17 + Maven** chạy được. Nó cố ý không thêm Spring Security/Spring Session để **không có lớp middleware ngoài ví dụ tự tạo session**, giúp nhìn rõ hành vi getSession(false) so với getSession(true). Response trả text/plain để không bị nhiễu bởi định dạng JSON.

### 6.1. Cấu trúc dự án

~~~text
cookie-session-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/cookiesession/
    │   └── CookieSessionDemoApplication.java
    └── resources/
        └── application.yml
~~~

**pom.xml:**

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
    <artifactId>cookie-session-demo</artifactId>
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

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080
  servlet:
    session:
      timeout: 15m
      tracking-modes: cookie
      cookie:
        http-only: true
        same-site: lax
        path: /
~~~

**Giải thích:** demo dùng cookie tracking, idle timeout mục tiêu 15 phút, HttpOnly, SameSite=Lax và Path=/ trên host local. **Không đặt secure: true trong demo HTTP localhost** để curl có thể gửi lại cookie bình thường. Ở môi trường HTTPS production, cấu hình **server.servlet.session.cookie.secure: true**, dùng TLS, reverse proxy/trusted forwarding phù hợp. Giá trị timeout và độ chính xác có thể chịu quy tắc làm tròn của Servlet container.

### 6.2. Tệp Java đầy đủ

**src/main/java/com/example/cookiesession/CookieSessionDemoApplication.java:**

~~~java
package com.example.cookiesession;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CookieSessionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CookieSessionDemoApplication.class, args);
    }
}

@RestController
class SessionController {

    @GetMapping(
            path = "/api/session/status",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String status(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "active=false, visits=0\n";
        }

        Integer visits = (Integer) session.getAttribute("visits");
        int count = visits == null ? 0 : visits;
        return "active=true, visits=" + count + "\n";
    }

    @PostMapping(
            path = "/api/session/visit",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String visit(HttpServletRequest request) {
        HttpSession session = request.getSession(true);

        Integer visits = (Integer) session.getAttribute("visits");
        int next = (visits == null ? 0 : visits) + 1;
        session.setAttribute("visits", next);

        return "active=true, visits=" + next + "\n";
    }

    @PostMapping(
            path = "/api/session/logout",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return "active=false, visits=0\n";
    }

    @GetMapping(
            path = "/api/session/trace",
            produces = MediaType.TEXT_PLAIN_VALUE
    )
    String trace(HttpServletRequest request) {
        boolean clientSuppliedId = request.getRequestedSessionId() != null;
        boolean valid = request.isRequestedSessionIdValid();
        boolean fromCookie = request.isRequestedSessionIdFromCookie();

        return "clientSuppliedId=" + clientSuppliedId
                + ", valid=" + valid
                + ", fromCookie=" + fromCookie + "\n";
    }
}
~~~

Điều quan trọng trong code:

- **GET /api/session/status** chỉ gọi **getSession(false)**. Khi không có phiên, nó không tự tạo session. Nó cũng không gửi ID cho client trong body.
- **POST /api/session/visit** gọi **getSession(true)**. Lần đầu có thể tạo session; các lần sau với cookie hợp lệ dùng lại session đó. Dùng POST vì nó làm thay đổi bộ đếm phía server.
- **POST /api/session/logout** gọi **invalidate()** nếu có session. Nó **không** tạo phiên mới để logout, và **không** tự thiết lập cookie xóa ở browser; phần 9 bàn cách làm logout production.
- **GET /api/session/trace** kiểm tra ID mà client trình bày và tính hợp lệ của nó, **không in nguyên session ID** để tránh đưa token vào log, URL hoặc response.
- Không dùng session để xác thực người dùng thật trong demo. Session tồn tại chỉ để ghi một thuộc tính đơn giản, bộ đếm visits.

**Giới hạn đồng thời:** code dùng Integer rồi tăng qua getAttribute/setAttribute, không phải phép tăng **atomic** nếu cùng một session nhận nhiều request song song. Demo chỉ dùng request tuần tự; ứng dụng thực cần thiết kế đồng bộ/atomic update hoặc repository có concurrency control phù hợp. HttpSession không tự bảo đảm mọi thao tác mutable attribute của bạn là thread-safe.

### 6.3. Build và chạy

Mở terminal ở thư mục cookie-session-demo:

~~~bash
mvn package
java -jar target/cookie-session-demo-1.0.0.jar
~~~

Yêu cầu có **JDK 17+**, Maven và cổng 8080 chưa bị chiếm. Khi ứng dụng sẵn sàng, dùng terminal khác để gửi request. Với Windows PowerShell, gọi **curl.exe** thay vì alias curl nếu muốn đúng cờ curl.

### 6.4. Thử lần 1: chỉ đọc, chưa có session

~~~bash
curl -i http://localhost:8080/api/session/status
curl -i http://localhost:8080/api/session/trace
~~~

**Body** kỳ vọng với client chưa cung cấp cookie:

~~~text
active=false, visits=0
~~~

~~~text
clientSuppliedId=false, valid=false, fromCookie=false
~~~

Trong app demo chưa có middleware tự tạo phiên, response từ **status/trace** không cần Set-Cookie session. Header server, timestamp và Content-Type thực tế có thể khác theo container; điều quan trọng là **chưa có lệnh tạo session**.

### 6.5. Thử lần 2: tạo phiên và lưu cookie vào cookie jar

~~~bash
curl -i -c session-cookies.txt -X POST \
  http://localhost:8080/api/session/visit
~~~

Body:

~~~text
active=true, visits=1
~~~

Response HTTP thường chứa header tương tự (ID ở đây là ký hiệu minh họa):

~~~http
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; SameSite=Lax
~~~

**Cờ -c** của curl lưu cookie server phát hành vào file cookie jar. Dùng một terminal hoặc thư mục làm việc nhất quán để đọc lại đúng file này. Nếu HTTP request trước đó đã tạo session bằng cách nào khác hoặc browser gửi cookie còn hợp lệ, giá trị visits không nhất thiết là 1; thí nghiệm dùng tiến trình vừa khởi động và client chưa có session.

### 6.6. Thử lần 3: gửi cookie cũ để liên kết với đúng phiên

~~~bash
curl -i -b session-cookies.txt \
  http://localhost:8080/api/session/status

curl -i -b session-cookies.txt \
  http://localhost:8080/api/session/trace
~~~

Body tương ứng:

~~~text
active=true, visits=1
~~~

~~~text
clientSuppliedId=true, valid=true, fromCookie=true
~~~

**Cờ -b** buộc curl nạp cookie trong jar vào request phù hợp với domain/path. Container nhận ID, tìm session hiện tại rồi trả lại attributes đã lưu. Bằng chứng “cùng phiên” ở đây không phải server đã nhận request thứ hai, mà là **cookie hợp lệ cho phép tìm lại state visits=1**.

Thử tăng bộ đếm bằng request dùng lại cookie:

~~~bash
curl -i -b session-cookies.txt -c session-cookies.txt -X POST \
  http://localhost:8080/api/session/visit
~~~

Body kỳ vọng:

~~~text
active=true, visits=2
~~~

Nếu bỏ **-b session-cookies.txt** ở lệnh POST thứ hai, curl không gửi cookie cũ và server có thể tạo **session mới** với visits=1. Việc đặt cờ -c chỉ lưu cookie **response**, không tự gửi cookie cũ trừ khi có -b hoặc cấu hình khác tương đương.

### 6.7. Thử lần 4: invalidate session và gửi lại cookie cũ

~~~bash
curl -i -b session-cookies.txt -X POST \
  http://localhost:8080/api/session/logout

curl -i -b session-cookies.txt \
  http://localhost:8080/api/session/status
~~~

Body của hai response trong demo:

~~~text
active=false, visits=0
~~~

~~~text
active=false, visits=0
~~~

Phiên cũ bị **invalidate()** phía server; nếu client vẫn gửi cookie cũ, getSession(false) không nhận được session đã bị invalid. Khi gọi **GET /api/session/trace** với cookie cũ, kết quả thường là **clientSuppliedId=true, valid=false, fromCookie=true**. Tuy vậy không nên cứng hóa cách client/browser xử lý cookie sau logout; framework hoặc container có thể có logic cookie khác khi cấu hình mở rộng.

Thử tiếp **POST /api/session/visit** với cookie cũ: **getSession(true)** có thể tạo phiên mới và phát một **JSESSIONID mới**. Cookie cũ không hồi sinh attributes của phiên đã hủy.

### 6.8. Thử lần 5: không có cookie thì request không tự có “ký ức”

Mở cookie jar mới hoặc chạy:

~~~bash
curl -i -X POST http://localhost:8080/api/session/visit
curl -i -X POST http://localhost:8080/api/session/visit
~~~

Mỗi lệnh curl không dùng -b sẽ không gửi lại ID từ lệnh trước, nên trong mô hình demo thông thường mỗi request tạo **phiên mới với visits=1**. Trình duyệt thật thường tự duy trì cookie, nên hành vi khác curl khi không dùng cookie jar.

Để xem toàn bộ header, dùng **curl -i**; để chỉ xem body, dùng **curl -s**. Khi thực hành phải phân biệt body minh họa với stdout thực tế do curl in ra (gồm progress meter hoặc headers nếu bật).

## 7. Các trường hợp làm session xuất hiện “sớm hơn mong đợi”

Khi ứng dụng thực tế báo có JSESSIONID ngay sau GET đầu tiên, đừng vội kết luận Servlet tạo session cho mọi request. Cần tìm đoạn code/framework đã yêu cầu phiên:

### 7.1. Filter, Interceptor, Controller hoặc view gọi getSession()

Một Filter dùng request.getSession() chỉ để đọc một attribute đã **vô tình tạo phiên**. Một Controller hoặc argument resolver cũng có thể tham gia lấy session khi cần. Nếu chỉ muốn kiểm tra tồn tại, dùng **getSession(false)** ở nơi có thể.

~~~java
// SAI nếu mục tiêu chỉ kiểm tra một trạng thái đã tồn tại:
HttpSession s = request.getSession();
Object flag = s.getAttribute("flag");

// ĐÚNG cho cách đọc không tạo:
HttpSession existing = request.getSession(false);
Object flag = existing == null ? null : existing.getAttribute("flag");
~~~

Hai đoạn là **fragment**, cần HttpServletRequest và import HttpSession; không phải file Java độc lập.

### 7.2. JSP và cơ chế model lưu trong session

Một trang JSP có **session support** mặc định trong nhiều cách sử dụng, hoặc framework lưu model attributes vào HttpSession, có thể khiến session xuất hiện trong quá trình render. Kiểm tra tag/directive JSP và nơi dùng **@SessionAttributes** nếu có. Không nhầm **@SessionAttribute** đọc attribute với **@SessionAttributes** quản lý các model attributes liên quan một luồng tương tác.

### 7.3. Spring Security có thể tạo session nếu cần

Spring Security hỗ trợ nhiều chính sách với **SessionCreationPolicy**:

| Chính sách | Vai trò trong Spring Security |
| --- | --- |
| ALWAYS | Chủ động tạo HttpSession |
| IF_REQUIRED | Chỉ tạo khi Security cần đến theo cơ chế được cấu hình |
| NEVER | Security không tự tạo, nhưng có thể dùng session đã tồn tại |
| STATELESS | Security không tạo và không dùng HttpSession để lấy SecurityContext |

**Đây là chính sách của Spring Security**, không phải một lệnh cấm Servlet API toàn ứng dụng. Ngay cả với SessionCreationPolicy.STATELESS, đoạn code nghiệp vụ trực tiếp gọi **request.getSession(true)** vẫn có khả năng tạo HttpSession. Ngược lại, một flow dùng cookie-based login, CSRF token repository hoặc saved request có thể cần session theo policy và configuration cụ thể.

Fragment cấu hình sau thể hiện ý định stateless cho tầng Security, **không phải project độc lập**:

~~~java
http.sessionManagement(session ->
        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

Cần có HttpSecurity và import SessionCreationPolicy trong SecurityFilterChain phù hợp. Không nên sao chép fragment vào ứng dụng demo có session mà vẫn muốn thấy cookies làm việc: Security stateless và ứng dụng session-based phục vụ hai mục tiêu khác nhau.

### 7.4. Redirect đăng nhập và session fixation

Khi đăng nhập thành công, framework bảo mật có thể **thay đổi session ID** để tránh session fixation. Kết quả là user vẫn đăng nhập trong flow hợp lệ nhưng cookie ID mới được phát hành; đừng cho rằng một session ID phải giữ nguyên từ lúc khách truy cập đến khi logout.

Servlet hỗ trợ **request.changeSessionId()** khi đã có session hợp lệ, còn Spring Security cung cấp cơ chế session fixation protection. Để an toàn, **để Spring Security quản lý quá trình xác thực, đổi ID và logout** theo cấu hình chuẩn thay vì tự dùng session ID làm vé đăng nhập.

## 8. Cấu hình Spring Boot: timeout và chính sách cookie

Các thuộc tính của Boot 3.3 cho Servlet session:

| Thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| server.servlet.session.timeout | 15m | Idle timeout của HttpSession |
| server.servlet.session.tracking-modes | cookie | Chọn mode theo dõi session; cookie hoặc mode khác theo Servlet |
| server.servlet.session.cookie.name | JSESSIONID | Tên cookie (nếu dùng container session) |
| server.servlet.session.cookie.path | / | Path cookie dùng để quyết định request được gửi kèm |
| server.servlet.session.cookie.domain | app.example.com | Domain cookie nếu được cấu hình; không nên mở rộng vô cớ |
| server.servlet.session.cookie.http-only | true | Ngăn JavaScript thông thường đọc cookie qua document.cookie |
| server.servlet.session.cookie.secure | true | Chỉ gửi qua kênh an toàn; dùng với HTTPS ở production |
| server.servlet.session.cookie.same-site | lax | Giảm việc gửi cookie trong một số ngữ cảnh cross-site |
| server.servlet.session.cookie.max-age | 30m | Thời hạn cookie ở browser, **khác** server idle timeout |

Mặc định **server.servlet.session.timeout** được Boot 3.3 công bố là **30m**, nhưng bài thực hành chọn 15m để dễ phân biệt việc cấu hình. Không giả định tất cả containers và session stores áp dụng độ chính xác tới mili giây; Servlet container có thể có granularity riêng.

**Không đồng nhất cookie max-age với session timeout**: bạn có thể có cookie lưu 30 phút nhưng phiên server hết sau 15 phút không hoạt động, hoặc cookie hết sau 5 phút trong khi session còn tồn tại phía server. Khi đó request mới không thể nối lại phiên nếu client đã mất ID.

### 8.1. SameSite trong thực tế

- **Strict:** hạn chế cookie trong các trường hợp cross-site chặt hơn, có thể ảnh hưởng link từ site ngoài.
- **Lax:** thường phù hợp website có điều hướng thông thường, nhưng không bảo đảm ngăn toàn bộ CSRF.
- **None:** cho phép các tình huống cross-site nếu browser cho phép; trên browser hiện đại thường yêu cầu **Secure**.
- **Same-site khác same-origin:** hai origin khác nhau vì scheme/host/port không nhất thiết là hai site khác nhau theo tiêu chí browser.

Chỉ đổi SameSite không thay cho **CSRF protection** trong ứng dụng dùng cookie để xác thực. Không dùng cấu hình SameSite=None một cách mặc định chỉ vì frontend và backend có port khác nhau; xem yêu cầu CORS, SameSite, domain/host và browser thực tế trước.

### 8.2. HttpOnly và Secure bảo vệ những gì?

- **HttpOnly** hạn chế JavaScript trên trang đọc trực tiếp giá trị cookie; nó **không** ngăn browser tự gửi cookie trong request và không tự chặn hành vi XSS gửi các request thay người dùng.
- **Secure** yêu cầu truyền cookie qua kênh an toàn theo quy tắc browser; nó **không** mã hóa dữ liệu session lưu phía server và không tự bật HTTPS.
- **HTTPS/TLS** bảo vệ dữ liệu truyền trên đường mạng; vẫn cần kiểm soát session ID, timeout và cookie scope.
- **Path/Domain** giúp giới hạn việc gửi cookie nhưng **không** phải ranh giới phân quyền; các ứng dụng dùng chung domain có thể tác động cookie tùy scope.

Trong môi trường có TLS termination ở reverse proxy, cần cấu hình proxy và trusted forwarding phù hợp để ứng dụng hiểu request gốc an toàn; hoặc đặt thuộc tính Secure rõ ràng. Không tắt Secure trên production chỉ để workaround cookie không được gửi mà chưa phân tích host/scheme/scope.

## 9. Logout đúng: invalidate server khác xóa cookie browser

Gọi:

~~~java
HttpSession s = request.getSession(false);
if (s != null) {
    s.invalidate();
}
~~~

sẽ làm **session phía server mất hiệu lực**. Điều này là trọng tâm bảo mật: cookie cũ không còn nối đến phiên đã hủy. Nhưng **invalidate() không đồng nghĩa tự động mọi client đều xóa cookie ngay**; browser có thể vẫn giữ JSESSIONID cũ cho đến khi cookie hết hạn hoặc server gửi lệnh xóa phù hợp.

Muốn xóa cookie phía client, server phát **Set-Cookie cùng tên/scope phù hợp với Max-Age=0** (và Path/Domain tương ứng); nên dùng logout handler/cookie serializer chuẩn của security/session framework để tránh xóa nhầm scope.

Ví dụ minh họa header xóa khi cookie trước đó có Path=/:

~~~http
Set-Cookie: JSESSIONID=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax
~~~

Ở production HTTPS, cookie nên mang Secure theo cấu hình. Khi cookie trước đó dùng Path hoặc Domain khác, xóa không đúng scope có thể chỉ tạo một cookie rỗng khác mà không xóa cookie cũ.

Một logout an toàn thường gồm các bước:
1. Xác thực rằng đây là yêu cầu logout hợp lệ và chống CSRF theo mô hình cookie-based authentication.
2. Hủy session phía server và SecurityContext theo cơ chế framework.
3. Phát cookie deletion nếu cần; dọn dữ liệu tạm khác (remember-me, refresh token) theo chính sách.
4. Không tái tạo session vô tình trong trang/redirect hiển thị sau logout.
5. Kiểm tra request tiếp theo với cookie cũ không truy cập được tài nguyên cần xác thực.

Trong demo ở phần 6, endpoint logout chỉ làm bước invalidate để minh họa khác biệt giữa **cookie vẫn tồn tại** và **phiên đã chết**; nó không phải một logout authentication production hoàn chỉnh.

## 10. Sự cố khi scale: cookie giống nhau nhưng replica khác nhau

Giả sử có hai instance:

~~~text
Browser
   | Cookie: JSESSIONID=abc
   v
Load Balancer
   |
   +--> Instance A: memory store có session abc
   |
   +--> Instance B: memory store không có abc
~~~

Nếu request tạo phiên đến **A** nhưng request tiếp theo đến **B**, và hai instance chỉ dùng **session in-memory riêng**, B có thể coi ID là không hợp lệ. Browser đã gửi cookie hoàn toàn đúng; vấn đề nằm ở **nơi lưu session phía server**.

Các lựa chọn thiết kế:

- **Sticky session / session affinity:** load balancer ưu tiên đưa một client về cùng instance. Có thể giúp dùng session local nhưng không bảo đảm khi instance chết/rolling deploy, và làm cân bằng tải khó hơn.
- **Shared session store bằng Spring Session Redis/JDBC:** nhiều replica tra session theo ID từ kho chung. Cần thiết kế TTL, serialization, availability, capacity, bảo mật, transaction và sự thay đổi schema dữ liệu.
- **Stateless authentication phù hợp:** tránh dựa vào HttpSession nếu nghiệp vụ thật sự không cần trạng thái server; đổi lại phải giải quyết token revocation/expiry và threat model riêng.

**Cảnh báo tên cookie:** với **Servlet session mặc định**, thường gặp JSESSIONID; với **Spring Session dùng DefaultCookieSerializer**, tên mặc định là **SESSION**. Đừng hard-code chỉ chấp nhận tên JSESSIONID trong mọi ứng dụng Spring. Khi dùng Spring Session, xem cấu hình CookieSerializer và **spring.session.timeout** cùng các property liên quan; khi session repository được thay thế, lifecycle lưu trữ không còn chỉ phụ thuộc memory store của container.

Một cookie hợp lệ về cú pháp không chứng minh session store đang hoạt động. Mất kết nối Redis, không serialize được attribute hoặc lệch tên cookie/scope đều có thể làm request không nối lại được state.

## 11. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Khả năng nguyên nhân | Cách xác minh |
| --- | --- | --- |
| GET trang bất kỳ lập tức có JSESSIONID | Filter, JSP, Security, model/session logic đã gọi getSession(true) hoặc tương đương | Trace thời điểm tạo session, soát Filter/Interceptor/Security |
| Mỗi request lại có session mới | Client không gửi Cookie, sai Path/Domain/Secure/SameSite, cookie bị chặn | DevTools Network/Storage, curl -c/-b, kiểm tra headers |
| Cookie được gửi nhưng session mất | Idle timeout, invalidate, restart, replica khác hoặc session store mất dữ liệu | isRequestedSessionIdValid(), logs, store, LB routing |
| Logout xong vẫn thấy JSESSIONID trong browser | Đã invalidate nhưng chưa xóa cookie hoặc xóa sai Path/Domain | Request cũ có được từ chối không; Set-Cookie Max-Age=0 |
| Cookie bị browser loại bỏ | Sai Domain, SameSite=None thiếu Secure, HTTPS/scope không hợp lệ | Browser DevTools Issues/Network; response headers |
| Cookie có HttpOnly nên không thấy bằng document.cookie | HttpOnly hoạt động đúng | Xem DevTools cookie storage hoặc request Cookie header |
| Cookie chạy trong tab này nhưng tab khác cũng có trạng thái | Cookies thường chia sẻ theo profile và scope, không phải theo tab | Tạo profile/incognito độc lập nếu muốn thử client mới |
| User bị mất đăng nhập khi load balancer đổi Pod | Local in-memory session không chia sẻ | Kiểm tra sticky/session repository, rolling restart |
| Session được tạo sau khi body đã flush | Response committed trước khi viết session cookie | Kiểm tra điểm gọi getSession() và response commit |
| Tưởng STATELESS của Security cấm mọi HttpSession | Controller tự gọi getSession(true) hoặc thư viện khác tạo | Tách policy Security với Servlet API |
| CORS cho phép nhưng browser không gửi cookie | Thiếu credentials, cookie scope/SameSite, third-party cookie policy | Kiểm tra fetch credentials, CORS origin/credentials, DevTools |
| Cookie là SESSION chứ không phải JSESSIONID | Dùng Spring Session/CookieSerializer tùy biến | Kiểm tra dependency và tên cookie thực tế |

### 11.1. Cách debug không làm lộ token

Trong DevTools:
1. Mở **Network** và chọn request tạo phiên.
2. Xem response headers có **Set-Cookie** hay không; lý do browser chấp nhận/chặn cookie nếu có.
3. Chọn request kế tiếp, xem request headers có **Cookie** tương ứng không.
4. Kiểm tra Path/Domain/Secure/SameSite/Expires và URL thực tế.
5. Tại server, log **có hay không có session**, isNew(), session creation event/counter và boolean valid, **không log nguyên ID phiên**.

Không đưa JSESSIONID thật vào ticket, screenshot công khai, URL query, stdout chia sẻ hoặc công cụ analytics không bảo mật. Nếu bắt buộc liên kết log request, dùng request correlation ID độc lập, không dùng cookie phiên làm trace ID.

### 11.2. Dùng HttpSessionListener khi cần quan sát vòng đời

Trong ứng dụng Servlet có thể đăng ký **jakarta.servlet.http.HttpSessionListener** để nhận sự kiện **sessionCreated** và **sessionDestroyed** ở mức container. Ví dụ fragment (không phải chương trình hoàn chỉnh):

~~~java
@WebListener
public class SessionLifecycleLogger implements HttpSessionListener {
    @Override
    public void sessionCreated(HttpSessionEvent event) {
        log.info("Session created");
    }

    @Override
    public void sessionDestroyed(HttpSessionEvent event) {
        log.info("Session destroyed");
    }
}
~~~

Để chạy fragment trong Boot, cần import Servlet annotations/interfaces, cấu hình phát hiện/đăng ký Servlet component phù hợp (ví dụ @ServletComponentScan hoặc một ServletListenerRegistrationBean), và một logger. **Không** in session ID thô. Thời điểm hủy do timeout có thể được xử lý bất đồng bộ/đợt quét của container; không kỳ vọng event đến đúng mili giây hết hạn.

Với Spring Session distributed, cách quản lý event/expired session và repository khác container local; chọn công cụ quan sát phù hợp kho thực tế.

## 12. Bài tập tình huống: dự đoán server có tạo cookie không

**Bài 1.** Client gọi GET /api/session/status trên ứng dụng demo mới, không gửi cookie. Trong method có getSession(false). Session mới có được tạo không?

**Đáp án:** Không bởi method này. getSession(false) trả null; response không cần Set-Cookie phiên. Trong ứng dụng khác, Filter/Security có thể đã tạo session trước đó.

**Bài 2.** Client gọi POST /api/session/visit lần đầu, nhận Set-Cookie, nhưng request thứ hai không gửi Cookie. Bộ đếm là 1 hay 2?

**Đáp án:** Thường là 1 ở cả hai request nếu mỗi lần tạo một session mới. Server không có cách nối hai request vào cùng session khi thiếu ID hoặc cơ chế tracking tương đương.

**Bài 3.** Client gửi Cookie: JSESSIONID=OLD nhưng OLD đã timeout. getRequestedSessionId() trả gì, getSession(false) trả gì?

**Đáp án:** getRequestedSessionId() có thể trả OLD (ID client trình bày); isRequestedSessionIdValid() false; getSession(false) null. Nếu gọi getSession(true), có thể tạo session mới.

**Bài 4.** Sau đăng nhập, JSESSIONID đổi nhưng giỏ hàng còn dữ liệu. Có nhất thiết là lỗi không?

**Đáp án:** Không. Framework có thể đổi ID để chống session fixation trong khi vẫn giữ session attributes theo chiến lược thích hợp. Cần kiểm tra luồng authentication đã được cấu hình.

**Bài 5.** Browser còn cookie JSESSIONID sau khi logout. User có chắc còn đăng nhập không?

**Đáp án:** Không. Nếu server đã invalidate session và auth state, cookie cũ không phục hồi session. Dù vậy nên xóa cookie phía client đúng scope và kiểm tra bảo mật của request tiếp theo.

**Bài 6.** Có 3 replica, chỉ lưu session trong RAM của từng replica. Client giữ cookie đúng nhưng thỉnh thoảng bị coi là khách. Vì sao?

**Đáp án:** Request có thể tới replica không có session tương ứng. Cần session affinity được quản lý hoặc kho session dùng chung (Spring Session) nếu hệ thống muốn giữ session qua replicas/restart.

**Bài 7.** Dùng SessionCreationPolicy.STATELESS nhưng code Controller gọi request.getSession(true). Vì sao vẫn thấy Set-Cookie?

**Đáp án:** STATELESS là policy cho thành phần Spring Security, không khóa API Servlet của ứng dụng. Controller vẫn có thể chủ động tạo HttpSession; cần sửa code/framework để đạt mục tiêu stateless toàn tuyến.

**Bài 8.** Cookie có Max-Age=24h, session có idle timeout 15m. User quay lại sau 2 giờ, browser vẫn gửi cookie. Có thể nối lại phiên cũ không?

**Đáp án:** Thông thường không nếu session server đã hết hạn do inactivity, dù cookie phía client còn. Cookie lifetime không kéo dài lifetime của HttpSession.

**Bài 9.** Server gửi Set-Cookie: JSESSIONID=...; Secure qua HTTPS, nhưng client tiếp theo gọi HTTP. Điều gì có thể xảy ra?

**Đáp án:** Cookie Secure không được gửi qua HTTP thông thường. Server có thể không thấy ID và tạo phiên mới nếu handler gọi getSession(true). Dùng HTTPS nhất quán; không hạ Secure để “chữa” lỗi.

## 13. Checklist thực hành cho code review

- **Mục đích session:** Chỉ dùng HttpSession khi thật sự cần trạng thái server giữa request; API stateless không nên tạo session vô ý.
- **Thời điểm tạo:** Xác định dòng code hoặc middleware nào gọi getSession(true)/getSession(); không đánh đồng mỗi HTTP request với một session mới.
- **Đọc không tạo:** Với endpoint chỉ kiểm tra, ưu tiên getSession(false) và xử lý null.
- **Ghép nối:** Kiểm tra Set-Cookie response đầu và Cookie request sau, cùng quy tắc Domain/Path/Secure/SameSite.
- **Hiệu lực:** Kiểm tra ID được trình bày có valid không; cookie tồn tại không đồng nghĩa session server tồn tại.
- **Bảo mật:** HTTPS, Secure, HttpOnly, SameSite phù hợp, CSRF protection và chống session fixation bằng framework.
- **Logout:** Invalidate phía server và xóa cookie phía client đúng scope khi cần; không tạo session vô tình sau logout.
- **Timeout:** Phân biệt server idle timeout với cookie Max-Age/Expires và session restore của browser.
- **Scale:** Nếu có nhiều replica, xác định kho session là local hay shared; không trông chờ cookie tự vận chuyển attributes.
- **Thử nghiệm:** Dùng curl -c/-b hoặc DevTools để quan sát headers và state; không log/hiển thị ID thật.
- **Phiên bản framework:** Phân biệt Servlet HttpSession, Spring Session và WebFlux WebSession trước khi chọn property/API.

## 14. Kết luận

**HttpSession được tạo khi ứng dụng/framework cần một phiên mới**, điển hình bằng **request.getSession() / request.getSession(true)**; **request.getSession(false)** chỉ đọc phiên hợp lệ hiện có và không tạo mới. Khi dùng cookie tracking, **Set-Cookie** chuyển ID từ server sang browser, **Cookie** gửi ID đó ở những request sau, giúp Servlet container tìm lại session phía server.

Một cookie chỉ là **phương tiện liên kết**: nó không chứa mặc nhiên toàn bộ trạng thái, không làm session đã timeout sống lại, không bảo đảm client đang authenticated và không tự chia sẻ session giữa các instance. Muốn xác định “session có được tạo chưa?” hãy quan sát **lời gọi API tạo phiên, header Set-Cookie/Cookie và trạng thái session server** theo đúng thứ tự, thay vì suy luận từ một JSESSIONID đơn lẻ.

## Tài liệu tham khảo chính thức

- Jakarta Servlet 6.0 — HttpServletRequest: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpServletRequest.html
- Jakarta Servlet 6.0 — HttpSession: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/HttpSession.html
- Spring Boot 3.3 — Common Application Properties (Servlet Session): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — Servlet Web Applications / SameSite Cookies: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Session — CookieSerializer, default cookie name and shared-session settings: https://docs.spring.io/spring-session/reference/api.html
