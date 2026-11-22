# HttpSession, cookie và mối quan hệ giữa trình duyệt với máy chủ

**Phạm vi:** Nền tảng HTTP và Jakarta Servlet trong ứng dụng web chạy trên Servlet container (ví dụ Apache Tomcat 10.1). Bài này giải thích cơ chế phiên; chưa giả định người dùng đã đăng nhập hoặc đã dùng Spring Security.

## 1. Vì sao cần cookie và phiên?

HTTP hoạt động theo mô hình **request → response**. Một request tự nó không có bộ nhớ về request trước: máy chủ nhận đường dẫn, phương thức, header, body và gửi response. Vì thế, khi trình duyệt gọi <code>GET /cart</code> lần thứ hai, giao thức HTTP không tự nói hai lần gọi thuộc cùng một trình duyệt.

Ứng dụng muốn nhớ giỏ hàng, tùy chọn hoặc trạng thái đăng nhập cần một cơ chế liên kết các request. Hai thành phần thường phối hợp:

- **Cookie**: cặp tên/giá trị trình duyệt lưu theo quy tắc miền, đường dẫn và thời hạn. Máy chủ có thể yêu cầu lưu cookie bằng header <code>Set-Cookie</code>; trình duyệt gửi cookie phù hợp trong header <code>Cookie</code> của request kế tiếp.
- **HttpSession**: đối tượng phiên do Servlet container quản lý ở phía máy chủ, chứa các attribute theo một định danh phiên (session ID). Container thường dùng cookie tên <code>JSESSIONID</code> để nhận ra phiên của request.

**Điểm phân biệt cốt lõi:** <code>JSESSIONID</code> thường chỉ là một định danh khó đoán trên trình duyệt; dữ liệu của <code>HttpSession</code>, như <code>cart</code> hoặc <code>viewCount</code>, nằm ở phía máy chủ. Cookie có thể dùng cho nhiều mục đích khác và không phải cookie nào cũng chỉ chứa session ID.

| Khía cạnh | Cookie HTTP | HttpSession trong Servlet |
| --- | --- | --- |
| Nằm ở đâu? | Trong kho cookie của trình duyệt, được gửi lại theo phạm vi áp dụng | Do container quản lý phía máy chủ |
| Ai tạo/quản lý? | Máy chủ gửi <code>Set-Cookie</code>, trình duyệt quyết định lưu/gửi theo chính sách | Ứng dụng tạo/truy xuất qua <code>HttpServletRequest</code>; container quản lý ID/vòng đời |
| Dữ liệu đi qua mạng | Tên và giá trị cookie được gửi ở request phù hợp | Thường chỉ session ID đi qua cookie; attribute không tự gửi |
| Thời gian sống | Theo <code>Max-Age</code>/<code>Expires</code> hoặc chính sách session cookie của trình duyệt | Theo thời gian không hoạt động, hủy phiên và cấu hình container |
| Phạm vi chia sẻ | Theo domain/path và các chính sách cookie | Theo ứng dụng web và cơ chế lưu phiên được cấu hình |

## 2. Dòng chảy thực tế giữa browser và server

Giả sử ứng dụng Servlet ở <code>https://app.example</code> và cần nhớ giỏ hàng:

~~~text
Trình duyệt                            Servlet container / ứng dụng
    |  GET /cart (chưa có JSESSIONID)          |
    |----------------------------------------->|
    |                            getSession() tạo HttpSession S1
    |                            lưu cart trong S1
    |  200 OK + Set-Cookie: JSESSIONID=abc...  |
    |<-----------------------------------------|
    |  Lưu cookie theo Path/Domain/chính sách  |
    |                                          |
    |  GET /cart + Cookie: JSESSIONID=abc...   |
    |----------------------------------------->|
    |                            tra session ID -> S1
    |                            đọc/cập nhật cart trong S1
    |  200 OK + nội dung giỏ hàng              |
    |<-----------------------------------------|
~~~

Các header rút gọn để minh họa (ID thật do container sinh và thường khác mỗi phiên):

~~~http
GET /cart HTTP/1.1
Host: app.example

HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: text/html;charset=UTF-8
~~~

Ở request tiếp theo, trình duyệt tự thêm header, miễn cookie đủ điều kiện được gửi:

~~~http
GET /cart HTTP/1.1
Host: app.example
Cookie: JSESSIONID=opaque-session-id
~~~

<code>Secure</code> và <code>SameSite=Lax</code> trong ví dụ là **cấu hình minh họa**, không bảo đảm container mặc định phát ra đúng các attribute này. Chúng cần được kiểm tra và cấu hình theo container/hạ tầng thực tế.

Lưu ý các tình huống thường gặp:

- **Hai tab trong cùng profile trình duyệt** thường dùng chung kho cookie cho cùng phạm vi nên cùng sử dụng một HttpSession; mở thêm tab không mặc nhiên tạo phiên mới.
- **Trình duyệt khác hoặc cửa sổ riêng tư** thường có kho cookie tách biệt nên nhận session ID khác.
- **Xóa cookie** khiến trình duyệt mất khả năng trình ID cũ; điều này không tự động xóa tức thì đối tượng phiên đang còn ở server.
- **Phiên hết hạn hoặc bị hủy** khiến ID cũ không còn ánh xạ tới HttpSession hợp lệ; lần tiếp theo ứng dụng gọi <code>getSession()</code> có thể tạo phiên mới.
- **Không có cookie** không đồng nghĩa không có phiên: phiên có thể vừa được tạo nhưng client chưa nhận/gửi ID; ứng dụng cũng có thể cấu hình phương án theo dõi khác.

## 3. Cookie được lưu và gửi theo quy tắc nào?

Header phản hồi <code>Set-Cookie</code> tạo/cập nhật một cookie. Header yêu cầu <code>Cookie</code> chỉ chứa các cặp tên/giá trị đủ điều kiện gửi; các attribute như <code>HttpOnly</code> không xuất hiện trong header <code>Cookie</code>.

| Attribute | Tác dụng và điều cần nhớ |
| --- | --- |
| <code>Path</code> | Giới hạn đường dẫn request nhận cookie; sai path có thể khiến server “mất phiên”. |
| <code>Domain</code> | Điều khiển phạm vi host; bỏ qua thường tạo host-only cookie cho host đã phát hành. Không mở rộng domain tùy tiện. |
| <code>Secure</code> | Chỉ gửi cookie qua kết nối an toàn theo chính sách trình duyệt; nên bật cho session cookie ở production qua HTTPS. |
| <code>HttpOnly</code> | Ngăn JavaScript đọc cookie bằng <code>document.cookie</code>, nhưng trình duyệt **vẫn tự gửi** nó trong HTTP request hợp lệ. |
| <code>SameSite=Strict</code> | Hạn chế gửi cookie trong ngữ cảnh cross-site; phù hợp khi không cần điều hướng liên site mang phiên. |
| <code>SameSite=Lax</code> | Cho phép một số điều hướng top-level an toàn theo quy tắc trình duyệt; thường cân bằng trải nghiệm và phòng vệ CSRF. |
| <code>SameSite=None</code> | Cho phép cookie trong các ngữ cảnh cross-site được hỗ trợ; trình duyệt hiện đại thường đòi <code>Secure</code>, và chính sách chặn third-party cookie vẫn có thể áp dụng. |
| <code>Max-Age</code>/<code>Expires</code> | Điều khiển thời hạn phía trình duyệt. Không đồng nhất với thời hạn HttpSession phía máy chủ. |

Cookie không có <code>Max-Age</code>/<code>Expires</code> là *session cookie* của trình duyệt; thời điểm xóa thực tế tùy trình duyệt và chức năng khôi phục phiên. Cookie có thời hạn dài cũng không giữ cho HttpSession tồn tại nếu server đã hết hạn phiên.

Để bảo vệ dữ liệu, **không đặt mật khẩu, session attribute nhạy cảm hoặc thông tin cá nhân dạng rõ vào cookie**. Với cookie chứa session ID, ai lấy được một ID còn hiệu lực có thể có cơ hội mạo danh phiên (session hijacking). HTTPS, quản lý cookie đúng và chống XSS giúp giảm rủi ro.

## 4. Vòng đời HttpSession và Servlet API

Servlet dùng <code>HttpServletRequest</code> để lấy phiên:

| Lời gọi | Ý nghĩa |
| --- | --- |
| <code>request.getSession()</code> hoặc <code>getSession(true)</code> | Trả về phiên hiện tại; tạo phiên nếu chưa có. |
| <code>request.getSession(false)</code> | Trả về phiên đang hợp lệ, hoặc <code>null</code>; không tạo phiên mới. Dùng khi chỉ muốn kiểm tra trạng thái. |
| <code>session.getId()</code> | Đọc ID phiên; không ghi ID vào log công khai, URL hoặc response body production. |
| <code>session.isNew()</code> | Cho biết client chưa tham gia phiên theo nhận biết của container; thường <code>true</code> trong request tạo phiên. |
| <code>session.setAttribute(name, value)</code> | Lưu một object theo key trong phiên phía server. |
| <code>session.getAttribute(name)</code> | Đọc object; trả <code>null</code> nếu không có. |
| <code>session.removeAttribute(name)</code> | Xóa một attribute. |
| <code>session.setMaxInactiveInterval(seconds)</code> | Đặt ngưỡng không hoạt động theo giây cho phiên; <code>0</code> hoặc số âm có nghĩa không tự timeout theo quy tắc Servlet API (cần cân nhắc cấu hình container). |
| <code>session.invalidate()</code> | Hủy phiên, làm các attribute không còn dùng được qua phiên đó. Không mặc nhiên bảo đảm cookie browser đã bị xóa. |
| <code>request.changeSessionId()</code> | Đổi ID của phiên hiện có, hữu ích sau khi xác thực để giảm session fixation; không cần tạo HttpSession mới. |

Một phiên có thể kết thúc do <code>invalidate()</code>, timeout không hoạt động, hoặc thay đổi/vận hành container. <code>getMaxInactiveInterval()</code> trả số giây cấu hình, không phải số giây còn lại. Mỗi request truy cập phiên được container nhận biết theo cơ chế quản lý thời điểm truy cập của Servlet; không nên coi đây là đồng hồ đếm ngược tuyệt đối từ lúc login.

Attribute là object Java phía server, **không tự được đồng bộ sang trình duyệt**. HttpSession cũng không tự khóa mọi thao tác trên object: hai request đồng thời từ hai tab có thể cập nhật cùng một counter/giỏ hàng dẫn đến race condition. Với dữ liệu quan trọng, dùng thiết kế cập nhật đồng thời phù hợp, thay vì dựa vào giả định mỗi phiên chỉ có một request tại một thời điểm.

## 5. Ví dụ Servlet chạy được: cùng cookie thì cùng bộ đếm

Ví dụ dùng **Java 17+, Maven, Jakarta Servlet 6.0 và Tomcat 10.1**. Đây là ứng dụng demo độc lập, không cần Spring Boot. Cấu trúc tệp:

~~~text
session-demo/
├── pom.xml
└── src/main/java/com/example/session/CounterServlet.java
~~~

Tạo <code>pom.xml</code>:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>session-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>
    </dependencies>
    <build>
        <finalName>session-demo</finalName>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo <code>src/main/java/com/example/session/CounterServlet.java</code>:

~~~java
package com.example.session;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;

@WebServlet("/counter")
public class CounterServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response) throws IOException {
        HttpSession session = request.getSession(); // Tạo nếu chưa tồn tại.
        Integer oldCount = (Integer) session.getAttribute("viewCount");
        int count = (oldCount == null) ? 1 : oldCount + 1;
        session.setAttribute("viewCount", count);
        session.setMaxInactiveInterval(15 * 60);

        response.setContentType("text/plain;charset=UTF-8");
        response.getWriter().println("count=" + count);
        response.getWriter().println("new=" + session.isNew());
    }

    @Override
    protected void doPost(HttpServletRequest request,
                          HttpServletResponse response) throws IOException {
        HttpSession existing = request.getSession(false);
        if (existing != null) {
            existing.invalidate();
        }
        response.setStatus(HttpServletResponse.SC_NO_CONTENT);
    }
}
~~~

Giải thích: <code>GET /counter</code> lấy/tạo phiên và tăng attribute <code>viewCount</code>. <code>POST /counter</code> hủy phiên hiện tại nếu có, trả HTTP 204. Đây là demo vòng đời phiên, **không phải endpoint logout có xác thực hoàn chỉnh**. Đoạn cập nhật counter cố ý đơn giản: hai request song song có thể gây lost update; không dùng kiểu read–increment–write này cho số liệu quan trọng.

Chạy tại thư mục dự án:

~~~bash
mvn clean package
~~~

Copy <code>target/session-demo.war</code> vào thư mục <code>webapps</code> của Tomcat 10.1 rồi khởi động Tomcat. Ứng dụng được deploy theo context path <code>/session-demo</code>. Trên shell có <code>curl</code>:

~~~bash
# Lần 1: lưu Set-Cookie của server vào cookie jar.
curl -i -c cookies.txt http://localhost:8080/session-demo/counter

# Lần 2: gửi lại cùng cookie jar.
curl -i -b cookies.txt -c cookies.txt http://localhost:8080/session-demo/counter

# Hủy HttpSession; sau đó thử GET với cookie cũ.
curl -i -X POST -b cookies.txt http://localhost:8080/session-demo/counter
curl -i -b cookies.txt -c cookies.txt http://localhost:8080/session-demo/counter
~~~

Kết quả **phần body dự kiến khi gọi tuần tự**:

~~~text
Lần GET 1:
count=1
new=true

Lần GET 2 cùng cookie:
count=2
new=false

POST:
HTTP 204, không có body

GET sau invalidate:
count=1
new=true
~~~

Header <code>Set-Cookie</code>, session ID, thứ tự/các header HTTP khác tùy Tomcat và môi trường. Nếu bỏ <code>-b cookies.txt</code> giữa các lần gọi, curl không tự “nhớ” cookie như trình duyệt, nên server có thể tạo phiên mới và counter quay về 1. Nếu mới deploy ở một context path khác thì chỉnh URL theo đường dẫn thực tế.

## 6. Cookie phiên, xác thực và Spring Security liên hệ thế nào?

**HttpSession không đồng nghĩa với đăng nhập.** Servlet có thể tạo phiên để lưu giỏ hàng của khách chưa xác thực. Ngược lại, hệ thống có thể xác thực mỗi request bằng token mà không dùng HttpSession để giữ trạng thái đăng nhập.

Khi ứng dụng Servlet dùng Spring Security theo mô hình session, chuỗi filter bảo mật xử lý request trước servlet/controller. Sau khi đăng nhập thành công, thông tin xác thực có thể được lưu dưới dạng <code>SecurityContext</code> liên kết với phiên tùy cấu hình. Ở request sau, cookie gửi session ID giúp hệ thống tìm lại phiên và phục hồi ngữ cảnh xác thực theo cơ chế đã cấu hình. Không suy ra rằng mọi ứng dụng Spring Security đều tạo session: cấu hình như <code>SessionCreationPolicy.STATELESS</code> nhằm tránh dùng HttpSession để lưu SecurityContext cho các request.

Phân biệt ba thứ trong một hệ thống:

1. **Session ID** là khóa tra cứu phiên; nó cần khó đoán và bảo vệ như bí mật.
2. **Authentication state** nói request hiện được xác thực với danh tính nào; có thể gắn với session hoặc token.
3. **Authorization** là kiểm tra người dùng có quyền thực hiện hành động cụ thể hay không; chỉ có cookie hợp lệ chưa đủ để cấp quyền.

Khi login, nên đổi session ID hiện có để chống **session fixation** (kẻ tấn công tìm cách khiến nạn nhân dùng sẵn một ID mà kẻ đó biết). Servlet hỗ trợ <code>request.changeSessionId()</code>; Spring Security có chiến lược bảo vệ session fixation theo cấu hình. Khi logout, cần hủy trạng thái xác thực/phiên phù hợp, xử lý cookie nếu cần, và ngăn reuse phiên cũ. Chỉ xóa giao diện người dùng hoặc xóa một biến JavaScript không có tác dụng hủy HttpSession phía server.

## 7. Bảo mật phiên và cookie trong thực tế

- **HTTPS + Secure:** chỉ dùng session cookie qua HTTPS trên production. Cấu hình <code>Secure</code> cho cookie phù hợp với TLS ở phía client; khi sau reverse proxy, kiểm tra ứng dụng nhận đúng thông tin scheme qua cơ chế proxy header đáng tin cậy.
- **HttpOnly:** hạn chế đọc session cookie qua JavaScript, giảm một đường khai thác XSS để lấy ID. Nó **không ngăn XSS thực hiện request thay người dùng** và không thay thế biện pháp chống XSS.
- **SameSite và CSRF:** trình duyệt tự gắn cookie vào request phù hợp, nên website khác có thể tìm cách khiến browser gửi request đổi trạng thái bằng phiên nạn nhân. <code>SameSite</code> giảm một số rủi ro, nhưng các ứng dụng dựa trên cookie vẫn cần chính sách CSRF đúng, ví dụ CSRF token cho thao tác thay đổi trạng thái và không thay đổi trạng thái bằng GET.
- **Timeout và logout:** đặt timeout không hoạt động phù hợp; <code>invalidate()</code> khi logout; không đặt các object nhạy cảm/lớn trong session nếu không cần. Một cookie chưa hết hạn có thể trỏ tới session đã hết hạn.
- **Không lộ session ID:** không đưa ID vào log, analytics, URL, lịch sử trình duyệt hoặc báo lỗi. ID bị đánh cắp có thể được dùng cho session hijacking cho đến khi hết hiệu lực hoặc bị thu hồi.
- **Cookie scope tối thiểu:** giới hạn Domain/Path khi phù hợp; không mở rộng cookie tới các subdomain không tin cậy. Nếu cần cookie cross-site, hiểu rõ <code>SameSite=None; Secure</code> và chính sách third-party cookie của trình duyệt.

Một đặc điểm dễ nhầm: **Same-Origin Policy, CORS và SameSite là những lớp khác nhau**. CORS chủ yếu kiểm soát việc JavaScript ở origin khác đọc response; nó không tự ngăn mọi form submission hay mọi request mang cookie. SameSite dựa trên ngữ cảnh *site*; hai origin khác nhau chưa chắc là hai site khác nhau.

Với ứng dụng frontend gọi API khác origin bằng <code>fetch</code>, trình duyệt thường không gửi cookie cross-origin trừ khi chỉ định tùy chọn phù hợp, ví dụ:

~~~javascript
fetch("https://api.example.com/profile", {
  credentials: "include"
});
~~~

Phía server cũng phải cấu hình CORS credentials với origin cụ thể được phép (không dùng wildcard <code>*</code> cho credentialed response); cookie còn phải qua các kiểm tra Domain/Path/SameSite/Secure và chính sách trình duyệt. <code>credentials: "include"</code> không vượt qua các hạn chế cookie này.

## 8. Khi không dùng cookie: URL rewriting và giới hạn của nó

Servlet hỗ trợ các phương án theo dõi phiên, trong đó có **URL rewriting**: ID phiên có thể được gắn vào URL khi cần (ví dụ thành phần <code>;jsessionid=...</code> tùy container). Nếu ứng dụng cần tạo URL có khả năng mang session ID theo cơ chế này, sử dụng <code>response.encodeURL(...)</code> hoặc <code>encodeRedirectURL(...)</code> thay vì tự nối ID.

Tuy nhiên, session ID trong URL có thể rò rỉ qua lịch sử, log, bookmark, chia sẻ link hoặc các luồng điều hướng. Với web application cần bảo mật, cookie an toàn thường là lựa chọn ưu tiên và có thể cấu hình chỉ theo dõi phiên qua cookie. URL rewriting chỉ nên được hiểu như khả năng của Servlet, không phải giải pháp mặc định để xử lý browser chặn cookie.

## 9. Vận hành: hết hạn phiên, nhiều máy chủ và request đồng thời

**Timeout phía server không phải cookie expiration.** Nếu thời gian không hoạt động là 15 phút, container có thể loại bỏ HttpSession sau ngưỡng đó; cookie cũ vẫn có thể nằm trong browser. Request gửi ID cũ chỉ giúp server biết ID được yêu cầu, không chứng minh phiên còn hợp lệ. Có thể dùng <code>request.isRequestedSessionIdValid()</code> để kiểm tra ID phiên được client gửi còn hợp lệ trong ngữ cảnh request; gọi <code>getSession()</code> sau khi phiên cũ hết hạn có thể tạo phiên mới.

**Nhiều instance:** nếu ứng dụng chạy sau load balancer mà dữ liệu phiên chỉ nằm trong RAM của instance A, request tiếp theo sang B có thể không tìm thấy phiên. Cần chiến lược vận hành như session affinity (sticky sessions), chia sẻ/lưu trữ phiên tập trung, hoặc thiết kế không trạng thái theo nhu cầu. Khả năng tồn tại qua restart và replication phụ thuộc container/cấu hình; không mặc định HttpSession là kho dữ liệu bền vững.

**Nhiều request song song:** một trình duyệt có thể gửi đồng thời nhiều request dùng cùng JSESSIONID. Đối tượng session không bảo đảm mọi attribute bên trong an toàn khi nhiều luồng cập nhật. Trong ứng dụng thực tế, bảo vệ các cập nhật dùng chung và ưu tiên lưu dữ liệu nghiệp vụ có yêu cầu nhất quán trong database hoặc dịch vụ lưu trữ phù hợp.

## 10. Chẩn đoán lỗi bằng Browser DevTools và curl

Nếu ứng dụng “mất đăng nhập” hoặc “mỗi lần refresh đều có session mới”, kiểm tra theo thứ tự:

1. Trong **Network**, phản hồi đầu tiên có <code>Set-Cookie</code> hay không? Session có thực sự được tạo chưa (ứng dụng có gọi <code>getSession()</code> không)?
2. Trong **Application/Storage → Cookies**, cookie có được trình duyệt chấp nhận không? Kiểm tra cảnh báo blocked cookie và các thuộc tính Domain, Path, SameSite, Secure, expiry.
3. Ở request tiếp theo, trong **Request Headers** có <code>Cookie: JSESSIONID=...</code> không? Đối chiếu đúng host, path, giao thức, browser profile và tùy chọn credentials.
4. Nếu cookie đã gửi, session ID có hợp lệ không? Kiểm tra timeout, <code>invalidate()</code>, thay ID sau login, restart container và việc điều phối nhiều instance.
5. Nếu phiên còn nhưng state bị sai, kiểm tra có tạo session mới nhầm qua <code>getSession()</code>, ghi đè attribute, sử dụng key khác nhau hoặc cập nhật đồng thời không.

| Triệu chứng | Nguyên nhân đáng kiểm tra |
| --- | --- |
| Mỗi request đều <code>new=true</code> | Cookie không được lưu/gửi; curl thiếu <code>-b</code>; Domain/Path/SameSite/Secure sai; client bị chặn cookie. |
| Cookie có mặt nhưng mất giỏ hàng | Phiên hết hạn/hủy; request sang instance khác không có session state; attribute bị ghi đè. |
| Hai tab thấy cùng giỏ hàng | Cùng profile và phạm vi cookie nên chia sẻ session; đây thường là hành vi đúng. |
| Xóa cookie mà server vẫn có session | Browser chỉ bỏ định danh phía client; server hủy theo timeout hoặc quy trình invalidate. |
| Logout nhưng request cũ còn quyền | Chưa hủy authentication/session hoặc token còn hiệu lực; cần kiểm tra luồng logout và chính sách xác thực. |
| API khác origin không nhận cookie | Thiếu credentials, CORS chưa đúng, hoặc cookie không đủ điều kiện gửi theo chính sách trình duyệt. |

## 11. Tự kiểm tra kiến thức

**Tình huống A:** Browser gửi <code>Cookie: JSESSIONID=X</code> nhưng server đã timeout phiên X. Browser có tự khôi phục giỏ hàng cũ từ cookie không? **Không.** Cookie thường chỉ giữ ID, không chứa attribute giỏ hàng; server cần tạo phiên mới hoặc lấy dữ liệu nghiệp vụ từ nơi lưu bền vững nếu ứng dụng đã thiết kế như vậy.

**Tình huống B:** Hai tab gửi request tăng <code>viewCount</code> đồng thời. Kết quả có chắc tăng đúng 2 không? **Không.** Hai request có thể đọc cùng giá trị cũ và ghi đè nhau nếu ứng dụng không kiểm soát cạnh tranh.

**Tình huống C:** Cookie bật <code>HttpOnly</code> có loại bỏ hoàn toàn CSRF không? **Không.** HttpOnly hạn chế JavaScript đọc giá trị cookie, trong khi browser vẫn tự gắn cookie vào những request đủ điều kiện; cần chính sách CSRF, SameSite và xử lý các thao tác thay đổi trạng thái thích hợp.

**Ghi nhớ:** HTTP request độc lập về giao thức; cookie giúp trình duyệt mang thông tin giữa các request; HttpSession giúp Servlet container liên kết ID với state phía server. Bảo vệ session ID và quản lý đúng vòng đời phiên là nền tảng trước khi học cơ chế đăng nhập/ủy quyền của Spring Security.
