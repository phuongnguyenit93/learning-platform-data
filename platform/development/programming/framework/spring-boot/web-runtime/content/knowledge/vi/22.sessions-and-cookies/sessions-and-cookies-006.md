# Lưu phiên trong bộ nhớ và hệ quả khi khởi động lại máy chủ

Trong ứng dụng Spring Boot, **HTTP session** cho phép server giữ một ít trạng thái giữa những request từ cùng một trình duyệt. Ví dụ, request đầu ghi tên người dùng hoặc trạng thái giỏ hàng vào session; request sau trình duyệt gửi lại **session ID** bằng cookie, và server sử dụng ID đó để tra dữ liệu đã lưu. Nhưng nếu session chỉ nằm **trong bộ nhớ của tiến trình Java**, khi tiến trình kết thúc hoặc container/pod được thay mới, dữ liệu session thường biến mất. Cookie vẫn có thể tồn tại trong browser, song nó chỉ là khóa tra cứu, **không phải bản sao dữ liệu session**.

Hệ quả có thể nhìn thấy ngay: người dùng mất trạng thái đăng nhập dựa trên session, giỏ hàng tạm mất dữ liệu, một wizard nhiều bước phải làm lại, hoặc một request gửi kèm cookie cũ nhưng server không còn biết ID đó. **Không được kết luận rằng mọi cách lưu session đều mất sau restart**: Spring Boot có tùy chọn persistence cho servlet container và Spring Session có thể lưu session ở Redis/JDBC. Bài này phân biệt rõ cấu hình **mặc định chỉ lưu trong memory** với những phương án thay thế.

Nội dung dùng **Spring Boot 3.x, Spring MVC/Servlet và Java 17+** làm ví dụ chính; cuối bài đối chiếu ngắn với WebFlux `WebSession`. Các thông số của phiên bản Boot khác cần được kiểm tra theo tài liệu version tương ứng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt browser cookie, session ID và nội dung `HttpSession` trên máy chủ.
- Giải thích cách embedded servlet container giữ session trong memory và tra cứu theo ID.
- Sử dụng `HttpServletRequest.getSession(true)`, `getSession(false)`, `HttpSession.setAttribute/getAttribute`, `invalidate()` và kiểm tra session cũ.
- Chạy một ví dụ Spring Boot rồi chứng minh dữ liệu session còn qua request nhưng biến mất khi **server restart** với cấu hình memory-only.
- Nhận diện ảnh hưởng đến đăng nhập, form nhiều bước, giỏ hàng, load balancing, rolling deployment và failover.
- Phân biệt timeout, logout, restart và mất cookie; biết vì sao các hiện tượng có thể có cùng biểu hiện nhưng nguyên nhân khác nhau.
- Chọn đúng giữa in-memory session, session persistence cục bộ, Spring Session Redis/JDBC và một thiết kế stateless, kèm điều kiện vận hành của từng giải pháp.
- Thiết kế kiểm thử, monitoring và cách ứng xử thân thiện khi session bị mất.

## 2. Session và cookie: dữ liệu nằm ở đâu?

HTTP là giao thức mà mỗi request tự mang thông tin cần thiết; bản thân một chuỗi request không tự hình thành một “phiên đăng nhập” được ghi nhớ. Khi ứng dụng cần trạng thái giữa các request, server có thể tạo **session**:

```text
Lần 1: Browser                                Spring Boot / Tomcat
POST /session/start?visitor=Lan ----------------------->
                                            Tạo session ID S-abc...
                                            Memory map:
                                              S-abc... -> {visitor:"Lan", views:0}
                         <------------------------------
                         Set-Cookie: JSESSIONID=S-abc...
                         
Lần 2: Browser                                Spring Boot / Tomcat
GET /session/status
Cookie: JSESSIONID=S-abc... -------------------------->
                                            Tìm S-abc... trong memory
                                            Đọc visitor và views
                         <------------------------------
                         session=active; visitor=Lan

Sau server restart:
Browser vẫn giữ JSESSIONID=S-abc...
GET /session/status ------------------------------->
                                            Memory map mới: rỗng
                                            Không tìm được S-abc...
                         <------------------------------
                         session=missing
```

Chỉ là sơ đồ minh họa, session ID thực là giá trị ngẫu nhiên không nên công bố. Với embedded Tomcat servlet thông thường, cookie session có tên **`JSESSIONID`** theo cấu hình mặc định. Khi dùng **Spring Session**, cookie có thể là **`SESSION`**, tùy `HttpSessionIdResolver`/`CookieSerializer` và cấu hình của hệ thống. Với WebFlux mặc định, `CookieWebSessionIdResolver` dùng `SESSION`. Vì vậy đừng viết kiểm tra hardcode giả định mọi dự án đều dùng một cookie name.

| Thành phần | Nằm ở đâu? | Có chứa gì? | Qua restart của app? |
| --- | --- | --- | --- |
| Cookie session ID | Browser, được gửi trong HTTP `Cookie` | Thường là một ID opaque | Có thể **vẫn còn**, tùy cookie lifetime/browser |
| `HttpSession` in-memory | Bộ nhớ tiến trình/container Servlet | Map các attribute theo ID | Mặc định **không còn** sau restart của tiến trình |
| Java object lưu trong session | Nằm trong store của session | Ví dụ `cartId`, `locale`, đối tượng tạm | Phụ thuộc store và serialization/persistence |
| Database nghiệp vụ | Dịch vụ dữ liệu riêng | Đơn hàng, người dùng, trạng thái bền vững | Không phụ thuộc restart web instance nếu DB còn |
| Spring Session Redis/JDBC | Kho session bên ngoài ứng dụng | Session attributes + expiration/metadata | Có thể tiếp tục dùng sau app restart nếu store còn, dữ liệu chưa hết hạn và tương thích |
| Cookie chứa token stateless | Browser/client | Token có chữ ký hoặc tham chiếu tùy thiết kế | Không phụ thuộc `HttpSession` in-memory, nhưng phụ thuộc validation, expiry và revocation |

**Cookie không phải Session.** Cookie `JSESSIONID` thường chỉ chứa mã định danh. Không thể “khôi phục giỏ hàng” bằng cách giữ nguyên cookie nếu dữ liệu tương ứng chỉ tồn tại trong memory đã bị giải phóng. Ngược lại, xóa cookie có thể làm browser mất khả năng tìm session đang còn trong store, dù chưa hết thời hạn server-side.

## 3. HttpSession hoạt động thế nào trong Spring MVC/Servlet?

Spring MVC sử dụng Servlet API. Các phương thức trọng tâm của `jakarta.servlet.http.HttpServletRequest` và `jakarta.servlet.http.HttpSession` là:

```java
HttpSession created = request.getSession(true);  // Tạo nếu chưa có
HttpSession maybe = request.getSession(false);   // Chỉ lấy, không tạo
created.setAttribute("cartId", "CART-42");       // Đưa dữ liệu vào session
Object value = created.getAttribute("cartId");  // Tra lại attribute
created.removeAttribute("cartId");              // Xóa một attribute
created.invalidate();                           // Vô hiệu hóa session
```

Đây là **snippet** nằm trong handler/servlet có `HttpServletRequest request`, không phải một class hoàn chỉnh. `request.getSession()` tương đương gọi chế độ có thể tạo session. Khi chỉ muốn kiểm tra “người dùng đã có session hợp lệ chưa?”, dùng **`getSession(false)`** để tránh vô tình sinh hàng loạt session cho các lượt request công khai.

Hai API khác hữu ích:

- `request.getRequestedSessionId()` cho biết ID session mà client đã yêu cầu, nếu có; **không đồng nghĩa ID hợp lệ**.
- `request.isRequestedSessionIdValid()` cho biết ID client gửi có tương ứng session hợp lệ tại phía server ở request hiện tại hay không.

Ví dụ browser gửi cookie cũ sau khi server restart: `getRequestedSessionId()` có thể vẫn có giá trị nhưng `isRequestedSessionIdValid()` trả `false`. Một request không có cookie hợp lệ cũng có thể có `getSession(false) == null`, nên chỉ nhìn null không phân biệt được “lần đầu truy cập”, “timeout”, “logout” hay “restart”. Muốn giải thích chính xác nguyên nhân cho người dùng, cần thêm thông tin vòng đời, observability và bối cảnh.

### 3.1. Session attributes nằm ở memory của container

Với cấu hình servlet session memory-only, container có một session manager giữ các instance `HttpSession` và thuộc tính tương ứng. Session manager có thể quản lý timeout và xóa session sau khi không hoạt động đủ lâu. Đây là **memory trong server process**, không phải cookie store ở browser.

Nếu các attribute là object lớn, số lượng session tăng có thể tạo áp lực lên heap/GC. Ví dụ lưu toàn bộ danh sách đơn hàng, 10 MB ảnh, hoặc kết quả truy vấn lớn trong mỗi session khiến RAM tiêu thụ xấp xỉ theo số người dùng hoạt động và dữ liệu mỗi session. Session có timeout nhưng chưa hết hạn vẫn chiếm tài nguyên theo chính sách container.

### 3.2. Session không phải toàn bộ trạng thái người dùng

Các dữ liệu cần **tồn tại lâu dài** như đơn hàng đã thanh toán, thông tin tài khoản, bản ghi công việc và giỏ hàng cần khôi phục sau nhiều ngày thường nên nằm trong database hoặc kho dữ liệu bền vững với user/cart ID. Session có thể chỉ lưu một **định danh** đến dữ liệu đó. Khi session bị mất, ứng dụng vẫn có thể hỗ trợ người dùng đăng nhập lại rồi khôi phục dữ liệu từ database, thay vì mất sạch nếu tất cả chỉ nằm trong memory của session.

## 4. Boot 3.x mặc định: vì sao restart làm mất session?

Spring Boot 3.3 cung cấp các cấu hình servlet session sau (trích những key liên quan):

```properties
server.servlet.session.persistent=false
server.servlet.session.timeout=30m
```

Theo bảng properties chính thức của Boot 3.3, `persistent` mặc định là **false** và timeout mặc định là **30 phút**. Có thể cấu hình lại thời gian timeout. Giá trị timeout là khoảng không hoạt động tối đa của session theo hợp đồng container; nó **không** có nghĩa ứng dụng bảo đảm session tồn tại đủ 30 phút bất kể server restart, pod chết hoặc store bị xóa.

Khi ứng dụng dừng và tạo process mới:

1. Bộ nhớ heap và map session của process cũ không còn.
2. Embedded container mới khởi tạo một session manager/store memory mới.
3. Browser có thể tiếp tục gửi cookie session ID cũ.
4. ID cũ không tra được trong session manager mới, nên session server-side không được phục hồi.
5. Nếu code gọi `getSession(false)`, kết quả có thể là `null`. Nếu code gọi `getSession(true)`, server có thể tạo một session mới và trả cookie mới.
6. Các attribute trước đây như `visitor`, `cartId`, form progress hay authentication context gắn vào session cũ không tự chuyển sang session mới.

### 4.1. Các loại restart cần phân biệt

| Tình huống | Điều xảy ra với memory-only session |
| --- | --- |
| Dừng bằng Ctrl+C rồi `bootRun` lại | Session của instance cũ mất |
| Deploy phiên bản JAR mới tạo JVM mới | Session local của instance cũ mất |
| Container/pod bị xóa rồi tạo mới | Session local mất; volume không tự giữ Java heap |
| Process crash/OOM kill | Session local mất và có thể chưa chạy cleanup đầy đủ |
| Rolling restart nhiều replicas | Mỗi replica mất session riêng khi bị thay, trừ khi store/route được thiết kế phù hợp |
| Restart riêng browser | Có thể mất session cookie nếu cookie không có expiry lâu dài; ngay cả khi server còn data, client có thể mất ID |
| Network interruption ngắn nhưng server không restart | Không nhất thiết mất session, tùy timeout và kết nối |
| Store Redis/JDBC bên ngoài vẫn còn | Có thể phục hồi session qua instance mới, tùy timeout, cấu hình và khả năng truy cập store |

**Một ngoại lệ quan trọng:** Spring Boot và servlet container có các tùy chọn **persist session lên disk** khi dừng/khởi động lại, vì thế câu “mọi HttpSession đều mất sau restart” là sai. Điều đúng là **trong mô hình mặc định memory-only, không có cơ chế bảo toàn session qua restart**.

## 5. Ví dụ Java 17+ hoàn chỉnh: tạo, đọc và mất session sau restart

Ví dụ chạy một Spring Boot MVC ứng dụng độc lập có ba chức năng chính: tạo session, tăng biến đếm và quan sát session đã có. Nó không triển khai login/thanh toán thật, để phân biệt vòng đời session khỏi nghiệp vụ xác thực.

### 5.1. Tạo dự án

Dùng Spring Initializr tạo ứng dụng **Spring Boot 3.x**, **Java 17+**, Gradle/Groovy, chọn dependency **Spring Web** (Servlet MVC). Trong `build.gradle` do Initializr tạo, đoạn quan trọng là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **khối dependencies**, không phải file Gradle hoàn chỉnh; Initializr phải cung cấp plugin, repositories, Spring Boot version và Gradle Wrapper. Boot 4 có tên starter MVC khác với Boot 3, nên không lẫn những ví dụ version trong cùng dự án.

Tạo file **`src/main/java/demo/SessionMemoryApplication.java`**:

```java
package demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SessionMemoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionMemoryApplication.class, args);
    }
}

@RestController
@RequestMapping(
        path = "/session",
        produces = MediaType.TEXT_PLAIN_VALUE
)
class SessionController {

    @PostMapping("/start")
    public String start(
            @RequestParam(defaultValue = "Lan") String visitor,
            HttpServletRequest request) {

        HttpSession session = request.getSession(true);
        session.setAttribute("visitor", visitor);
        session.setAttribute("views", 0);
        return "session=started\n";
    }

    @GetMapping("/status")
    public String status(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "session=missing\n";
        }

        String visitor = (String) session.getAttribute("visitor");
        Integer views = (Integer) session.getAttribute("views");

        return "session=active\n"
                + "visitor=" + visitor + "\n"
                + "views=" + views + "\n";
    }

    @PostMapping("/visit")
    public String visit(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "session=missing\n";
        }

        Integer previous = (Integer) session.getAttribute("views");
        int next = previous == null ? 1 : previous + 1;
        session.setAttribute("views", next);
        return "views=" + next + "\n";
    }

    @PostMapping("/end")
    public String end(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) {
            return "session=missing\n";
        }

        session.invalidate();
        return "session=invalidated\n";
    }
}
```

Chỉ class `SessionMemoryApplication` là `public`, nên hai class trong một file Java này hợp lệ. `SessionController` ở cùng package `demo` được Spring Boot component scanning phát hiện. Mọi endpoint ở đây trả text, không cần Thymeleaf vì `@RestController` dùng response body.

Tạo `src/main/resources/application.properties`:

```properties
server.port=8080
server.servlet.session.persistent=false
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

`persistent=false` được đặt tường minh để thí nghiệm có kết quả rõ dù ai đó thay cấu hình sau này. `timeout=15m` là khoảng không hoạt động tối đa, không phải tuổi thọ bảo đảm. Ở local HTTP, chưa đặt `server.servlet.session.cookie.secure=true` vì cookie `Secure` chỉ nên được gửi qua HTTPS theo cấu hình trình duyệt; production dùng TLS và thiết lập cookie security phù hợp.

### 5.2. Chạy chương trình

Từ thư mục dự án:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Nếu đang có ứng dụng khác chiếm cổng 8080, dừng ứng dụng cũ hoặc đổi `server.port`. Khi server đã khởi động, dùng terminal thứ hai để gửi HTTP requests. `javac SessionMemoryApplication.java` đơn lẻ sẽ không chạy được vì cần Spring/Servlet dependencies; Gradle Wrapper cung cấp build classpath.

### 5.3. Trước khi tạo session

```bash
curl -s http://localhost:8080/session/status
```

Body **chính xác** của endpoint trong ví dụ:

```text
session=missing
```

Ở request này `getSession(false)` chỉ kiểm tra, không buộc tạo session mới.

### 5.4. Tạo session và lưu cookie vào file

Trên Linux/macOS, dùng `curl`:

```bash
curl -i -c session.cookies -b session.cookies \
  -d 'visitor=Lan' http://localhost:8080/session/start
```

Ở Windows PowerShell, chạy trên một dòng:

```powershell
curl.exe -i -c session.cookies -b session.cookies -d "visitor=Lan" http://localhost:8080/session/start
```

Body trả về:

```text
session=started
```

Trong response header sẽ có `Set-Cookie` chứa một `JSESSIONID` mới (giá trị ID cụ thể thay đổi giữa các lần chạy). Cờ `-c session.cookies` lưu cookie jar; `-b session.cookies` gửi lại cookie đã có. **Không công bố hoặc đưa session ID từ cookie jar vào tài liệu/log** vì nó có thể hoạt động như credential tạm thời nếu ứng dụng có authentication thật.

### 5.5. Đọc lại session và tăng lượt truy cập

```bash
curl -s -b session.cookies http://localhost:8080/session/status
```

Body:

```text
session=active
visitor=Lan
views=0
```

Gọi:

```bash
curl -s -b session.cookies -X POST http://localhost:8080/session/visit
```

Body:

```text
views=1
```

Đọc `/session/status` lần nữa với cùng cookie sẽ thấy `views=1`. Nếu gọi `/session/status` bằng một cookie jar **khác** hoặc request không có cookie, bạn sẽ nhận `session=missing`, vì browser/client đó không đưa ID session đã tạo.

### 5.6. Dừng server, khởi động lại và dùng cùng cookie jar

Dừng tiến trình đang chạy bằng Ctrl+C, sau đó chạy lại:

```bash
./gradlew bootRun
```

Đừng xóa `session.cookies` hoặc đổi port/context path trong lúc thử. Khi server mới đã sẵn sàng:

```bash
curl -s -b session.cookies http://localhost:8080/session/status
```

Body kỳ vọng:

```text
session=missing
```

Đây là thí nghiệm xác nhận trọng tâm: **cookie jar vẫn chứa ID cũ, nhưng map in-memory trong server mới không chứa session tương ứng**. Nếu ngay sau restart bạn gửi `POST /session/start`, server tạo session mới với một ID mới và trả `Set-Cookie` mới; nếu không giữ cookie mới, request sau vẫn có thể tiếp tục gửi ID cũ.

Đối với `getSession(false)`, application không tạo session chỉ để đọc status. Nếu dùng `getSession(true)` trong `status` thì sau restart một request có cookie cũ có thể **âm thầm tạo session rỗng mới**; biểu hiện với người dùng có thể là “giỏ hàng trở về 0” thay vì một lỗi rõ ràng.

### 5.7. Phân biệt explicit logout với restart

Khi ứng dụng còn chạy và bạn có cookie hợp lệ:

```bash
curl -s -b session.cookies -X POST http://localhost:8080/session/end
```

Body:

```text
session=invalidated
```

`HttpSession.invalidate()` chủ động vô hiệu hóa session trên server. Browser có thể vẫn giữ cookie ID cũ cho tới khi được thay hoặc xóa; server sẽ không xem ID đó là session còn hợp lệ. Hệ thống đăng nhập thực tế cũng nên xóa/expire cookie phù hợp và dùng cơ chế logout của Spring Security thay vì coi ví dụ `/end` là giải pháp xác thực hoàn chỉnh.

### 5.8. Kết quả của ví dụ phụ thuộc điều kiện nào?

- Chỉ một JVM Spring Boot memory-only; không có Spring Session, custom session store hay disk persistence.
- `server.servlet.session.persistent=false` để chắc chắn không phục hồi từ disk.
- Cùng cookie jar qua các HTTP requests và qua restart **server**; không restart browser vì browser có thể tự xóa session cookies.
- Không có Spring Security hoặc middleware khác tự tạo session.
- Tải thử đơn giản, không có nhiều server sau load balancer.

Nếu điều kiện khác (chẳng hạn có Redis Spring Session), kết quả sau restart có thể là `session=active`; đó là biểu hiện của store bền hơn, không phải lỗi của ví dụ.

## 6. Không phải mọi mất session đều do restart

Các tình huống đều có thể dẫn tới một request không tìm thấy session:

| Nguyên nhân | Dấu hiệu | Gợi ý chẩn đoán |
| --- | --- | --- |
| Server/JVM restart | Session đồng loạt biến mất trên instance vừa thay | Đối chiếu startup time, deployment/pod restart |
| Session idle timeout | Một user không hoạt động quá lâu mới bị mất | Xem `server.servlet.session.timeout`, last access |
| Logout/`invalidate()` | Mất ngay sau thao tác logout | Đọc logout flow, cookie expiration, server log |
| Browser xóa cookie/đổi browser/profile | Client không gửi ID cũ | Quan sát header `Cookie` tại phía client/dev tools |
| Cookie domain/path/SameSite/Secure sai | Cookie không được gửi trên một số route/origin | Kiểm tra domain, path, HTTPS và site context |
| Gửi tới instance khác trong cụm | Session chỉ nằm ở memory của instance cũ | Kiểm tra route/affinity và session store |
| Load balancer failover | Request chuyển node khi node cũ chết | Kiểm tra health/route và local memory |
| Redis/JDBC hết TTL hoặc bị lỗi | Session ngoài app không truy cập được | Kiểm tra datastore/TTL/connection và error metrics |
| Session ID bị xoay khi authentication | ID trước login không còn hợp lệ | Kiểm tra session fixation protection |
| Thay đổi phiên bản serializer/class | Store vẫn còn nhưng không deserialize được attribute | Kiểm tra lỗi serializer/schema compatibility |

Một mã `JSESSIONID` vẫn còn trong request chỉ chứng minh browser gửi một ID. Nó **không** chứng minh người dùng có phiên hợp lệ hay server đã khôi phục dữ liệu. Đừng tự động trả “bạn đã bị logout do restart” nếu ứng dụng không có bằng chứng xác định nguyên nhân.

### 6.1. Timeout không phải Max-Age của cookie

`server.servlet.session.timeout` điều khiển vòng đời inactivity của **server-side session**. `server.servlet.session.cookie.max-age` điều khiển cookie có được trình duyệt giữ sau thời gian nhất định hay không; hai giới hạn này khác nhau. Cookie có `Max-Age` dài hơn thời gian session sống vẫn không giúp khôi phục session đã expired ở server. Ngược lại, browser xóa session cookie có thể khiến session còn tồn tại trong memory nhưng client không còn ID để tìm.

Timeout thường được đánh giá theo hoạt động của session trên server và các thời điểm access, không đồng nghĩa với một đồng hồ bất biến từ lúc đăng nhập. Đối với yêu cầu bảo mật, cân nhắc cả **idle timeout** và **absolute lifetime** nếu sản phẩm cần, thay vì mặc định kéo dài vô hạn khi có request.

## 7. Hệ quả trên giao diện và hệ thống nghiệp vụ

### 7.1. Người dùng “bị đăng xuất” sau khi deploy

Với ứng dụng sử dụng Spring Security form login, authentication thường được duy trì bằng một security context liên kết session theo cấu hình phù hợp. Khi local session bị mất, yêu cầu tiếp theo không tìm thấy authentication đó; người dùng có thể được chuyển về trang đăng nhập hoặc nhận 401/403 tùy security config, endpoint và client. **Không hứa rằng mọi app đều trả 302**: response phụ thuộc cơ chế authentication/authorization.

Khi Spring Security được cấu hình stateless (ví dụ API dùng bearer token và không lưu auth trong `HttpSession`), server restart **không tự** làm mất trạng thái token chỉ vì memory session bị xóa; còn hiệu lực token phụ thuộc cách xác thực token, thời hạn, keys và revocation.

### 7.2. Giỏ hàng và thao tác nhiều bước

Nếu giỏ hàng hoặc wizard form chỉ tồn tại trong session memory, restart có thể làm mất nội dung. Với giỏ hàng quan trọng, một phương án là lưu dữ liệu trong database gắn với account ID hoặc cart ID bền vững; session chỉ giữ định danh ngắn. Khi user đăng nhập lại, ứng dụng có thể truy xuất dữ liệu và tiếp tục.

Nếu một biểu mẫu dài chứa dữ liệu nhạy cảm, cần rõ chính sách autosave, TTL, xóa dữ liệu và consent; không mặc định session memory là phương pháp lưu an toàn và bền. Mất session cũng có thể làm token CSRF gắn với session cũ mất hiệu lực, khiến submit của tab đang mở thất bại sau restart. Cần thông báo để user tải lại form và tránh thực hiện nửa chừng các side effect.

### 7.3. Đồng thời nhiều tab

Nhiều tab của cùng browser thường gửi chung cookie session phù hợp domain/path, vì vậy chúng có thể dùng cùng một `HttpSession`. Nếu một tab gọi logout/`invalidate()` hoặc server restart, tab khác có thể vẫn hiển thị UI cũ đến khi gửi request tiếp theo. UI vẫn “đang đăng nhập” trên màn hình **không** chứng minh server còn authentication state.

### 7.4. Khi request đang xử lý bị gián đoạn

Server restart có thể cắt request đang chạy bất kể session lưu ở đâu. Chuyển session sang Redis không làm một request HTTP dở dang tự hoàn thành hay tự rollback giao dịch. Với thao tác tạo đơn/thanh toán, phải có transaction, idempotency key và cơ chế kiểm tra kết quả trước khi retry. Session persistence chỉ giải quyết **trạng thái phiên giữa request**, không thay thế durability của nghiệp vụ.

## 8. Nhiều replicas, load balancing và rolling deployment

Giả sử hệ thống chạy hai Spring Boot instances A và B sau load balancer:

```text
Browser: Cookie JSESSIONID=S-100
          |
          v
      Load balancer
       /         \
      v           v
 Instance A     Instance B
 Memory:        Memory:
 S-100 ->       (không có S-100)
  {visitor:Lan}
```

Nếu request đầu đến A tạo session, request sau bị gửi sang B thì B có thể không tìm thấy `S-100`. Có thể xảy ra ngay cả **không có restart**, nếu load balancer không giữ affinity.

### 8.1. Sticky session giải quyết được phần nào?

**Sticky session** (session affinity) cố gắng đưa các request có cùng client/session đến đúng instance. Nó có thể giảm việc mất session do đổi node khi node còn hoạt động, nhưng **không bảo vệ** khi instance A restart, pod bị thay, autoscale down hoặc node chết. Affinity cũng tạo coupling giữa user và một instance, gây khó khăn khi scale-out/rolling deploy.

| Tình huống | Sticky + memory-only | Store chia sẻ Redis/JDBC |
| --- | --- | --- |
| Hai request liên tiếp, A và B đều khỏe | Có thể ổn khi luôn route A | Có thể đọc cùng session khi cả hai app dùng chung store |
| A bị crash và browser chuyển sang B | Session A mất | Có thể tiếp tục nếu store còn và session chưa expired |
| Rolling deploy thay A | Session A mất khi pod bị loại | App mới có thể truy cập session ở store ngoài |
| Store Redis bị xóa/restart không có persistence | Không dùng Redis, nhưng A vẫn có session nếu còn sống | Có thể mất session do store mất dữ liệu |
| Version mới đổi class session attribute không tương thích | Mỗi node dùng riêng memory, rủi ro ở migration | Deserialization/compatibility cần giải quyết toàn cluster |

Hãy hiểu **thêm nhiều replicas không biến memory-only thành distributed session**. Khi chọn shared store, cần cấu hình đồng nhất application version/serialization, TTL, cookie, secret, network và health policy.

### 8.2. Readiness và graceful shutdown

Readiness probe giúp tránh gửi request mới tới instance chưa sẵn sàng hoặc đang bị gỡ khỏi service, còn graceful shutdown giúp xử lý các request đang thực thi. Nhưng cả hai **không giữ lại một Java heap session** sau khi process biến mất. Khi yêu cầu người dùng duy trì login qua rolling deployment, cần session store ngoài instance hoặc cơ chế xác thực không phụ thuộc memory local.

## 9. Phương án 1: tiếp tục dùng session trong memory

Memory-only hợp lý trong tình huống:

- Dự án học tập, ứng dụng nội bộ nhỏ hoặc prototype chấp nhận mất phiên sau restart.
- State tạm ít quan trọng, có thể dựng lại dễ dàng.
- Một instance, traffic thấp, không cần chuyển session giữa các node.
- Yêu cầu vận hành ưu tiên đơn giản và UX chấp nhận đăng nhập lại khi deploy.

Ưu điểm: không cần Redis/JDBC session store, access trong memory nhanh và ít thành phần hệ thống. Chi phí: session mất khi JVM chết, khó failover; memory footprint tăng cùng số user và attribute; không phù hợp nếu cần giữ phiên ổn định qua deploy.

Đừng “khắc phục” bằng cách đặt timeout rất dài: timeout dài giữ object lâu hơn trên heap mà vẫn không cứu được session sau restart. Hạn chế kích thước attribute, đặt timeout theo rủi ro bảo mật, tránh lưu file/blob hoặc thông tin có thể truy xuất lại từ database.

## 10. Phương án 2: persistent servlet session trên disk

Spring Boot 3.x có cấu hình cho tính năng lưu session của servlet container, ví dụ:

```properties
server.servlet.session.persistent=true
server.servlet.session.store-dir=/path/to/durable/sessions
```

Đây là **ví dụ cấu hình lựa chọn**, không áp dụng cùng lúc với demo memory-only ở phần 5. Đường dẫn phải là thư mục hợp lệ cho runtime và container. Hành vi thực tế phụ thuộc embedded container (Tomcat/Jetty/Undertow), thời điểm stop/start, khả năng serialize attributes, quyền đọc/ghi, phiên bản ứng dụng và vòng đời file. Với Tomcat, session persistence khi shutdown bình thường có thể serialize session ra file rồi đọc lại lúc startup; nếu object không `Serializable` hoặc gặp crash/cấu hình không phù hợp, khôi phục có thể không hoàn chỉnh.

**Không coi disk persistence cục bộ là giải pháp session HA mặc định**:

- Disk của một pod/container thường không được giữ khi instance bị thay trừ khi gắn storage phù hợp.
- Một directory của node A không tự chia sẻ với node B.
- Crash/power loss không giống shutdown thành công.
- Deserialize dữ liệu object từ version cũ có thể lỗi khi class thay đổi.
- Cần bảo vệ file session vì có thể chứa thông tin nhạy cảm.

Lựa chọn này có thể dùng cho nhu cầu restart **cùng instance và storage** với điều kiện rõ, nhưng nếu cần failover và nhiều replicas, shared session store thường phù hợp hơn. Boot mặc định `server.servlet.session.persistent=false`, nên không suy rằng Tomcat tự lưu session trong mọi ứng dụng Boot.

## 11. Phương án 3: Spring Session lưu ở Redis

**Spring Session** cung cấp cơ chế lưu session ngoài servlet container. Với ứng dụng Servlet MVC và Redis, Spring Session thay implementation quản lý `HttpSession` bằng store Redis; application vẫn có thể gọi `HttpSession.setAttribute/getAttribute`. Spring Boot 3.x tự cấu hình khi có các module phù hợp và Redis connection.

Sơ đồ:

```text
                Browser
                   |
               SESSION cookie
                   |
                Ingress
                 /   \
                v     v
             Pod A   Pod B
                \     /
                 \   /
                 Redis
             Session store
                S-1 -> {cartId:42, ...}
```

Nếu pod A được thay, pod B có thể tìm cùng session ID ở Redis, **nếu** Redis vẫn hoạt động, session chưa expired, các app dùng chung namespace/config phù hợp và thuộc tính có thể deserialize. Cookie khi dùng Spring Session có thể khác tên cookie container mặc định; hướng dẫn Spring Session Redis ghi nhận cookie `SESSION` trong ví dụ của họ. Luôn kiểm tra response thực tế.

### 11.1. Dependencies cho Boot 3.x

Giữ `spring-boot-starter-web`, thêm module Spring Session Redis và Redis client. Ví dụ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Đây là **snippet cấu hình** dùng trong một dự án có Spring Boot 3.x BOM; không phải một dự án hoàn chỉnh có Redis server. Spring Session 3.x documentation dùng `org.springframework.session:spring-session-data-redis`; Spring Boot 4.x có thêm các starter session riêng, vì vậy không copy nhầm dependency theo major version khác.

### 11.2. Kết nối Redis và session timeout

Ví dụ `application.properties`:

```properties
spring.data.redis.host=localhost
spring.data.redis.port=6379

# Spring Session timeout trong Boot 3.x
spring.session.timeout=15m
spring.session.redis.namespace=demo:sessions
```

Cần Redis thực sự đang chạy và có thể kết nối. Ứng dụng production phải có authentication/TLS/network policy/secret management thích hợp; không giữ password rõ trong source control. Các module/driver/timeout phải tương thích đúng bản Spring Boot.

Nếu chỉ có **một** Spring Session store module trên classpath trong Boot 3.3, Boot có thể auto-select store đó; thêm nhiều store modules mà không hiểu thứ tự ưu tiên có thể gây chọn sai. Hãy quan sát startup logs, Redis key/TTL và hành vi reload thật để xác nhận.

### 11.3. Giữ session qua restart cần những điều kiện gì?

- Redis không mất dữ liệu trong thời gian app restart; nếu Redis cũng restart không có persistence/replication phù hợp, session có thể vẫn mất.
- Session chưa hết TTL/idle timeout và clock/time policy đồng nhất.
- Dữ liệu session attributes có format serialize/deserialize tương thích giữa các phiên bản app.
- Cookie domain/path và cookie name được các instances thống nhất.
- Người dùng vẫn dùng đúng cookie hoặc cơ chế nhận diện session ID khác.
- Redis có capacity đủ, không bị eviction theo chính sách memory vượt quá dự kiến.
- Session store được bảo vệ, quan sát và sao lưu/HA tương xứng với mức độ quan trọng.

Đừng lưu nguyên toàn bộ entity graph, token mật hoặc object khó serialize vào session. Lưu giá trị nhỏ (user ID, locale, cart ID) cùng namespace/version rõ ràng. **Spring Session không bảo đảm Redis tự trở thành kho dữ liệu bền vững vĩnh viễn**; đó là trách nhiệm thiết kế Redis/TTL/backup/failover và chính sách của ứng dụng.

### 11.4. Hậu quả khi Redis lỗi

Một web app trước đó lưu session trong memory nay có thể bị phụ thuộc vào Redis trên mỗi request cần state. Nếu Redis unavailable, request liên quan session có thể chậm/lỗi, tùy cấu hình. Phải có timeout, capacity planning, metrics cho Redis latency/availability và kế hoạch khi store sự cố. Chỉ “cài thêm Redis” mà không vận hành Redis đúng có thể chuyển rủi ro từ **pod restart làm mất session** sang **session store là điểm lỗi chung**.

## 12. Phương án 4: Spring Session JDBC

Spring Session cũng có thể dùng **database quan hệ** làm nơi lưu session. Trong Boot 3.x, có thể thêm Spring Session JDBC module và cấu hình DataSource/driver cùng schema phù hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.session:spring-session-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Đây là **snippet Gradle**; cần cung cấp `spring.datasource.url`, username/password qua cấu hình an toàn, PostgreSQL thật và session schema. Trong môi trường demo có thể dùng cơ chế khởi tạo schema của Spring Session JDBC đúng phiên bản; production nên quản lý migration bằng Flyway/Liquibase và kiểm soát quyền DDL thay vì luôn bật auto-create. Tham khảo Boot 3.3 Spring Session JDBC và module docs để biết tên bảng/scheme chính xác.

**Đánh đổi:** database có thể cung cấp dữ liệu session qua nhiều app instances, nhưng làm tăng số thao tác đọc/ghi, số connection, cleanup expired sessions, lock/concurrency và storage. Với lưu lượng session cao, kiểm tra connection pool, query/TTL/cleanup và index; không quyết định theo tên “JDBC bền vững” mà bỏ qua năng lực database.

## 13. Phương án 5: tách session khỏi dữ liệu nghiệp vụ hoặc dùng stateless auth

Có hai câu hỏi khác nhau:

1. Người dùng cần **giữ xác thực** qua restart?
2. Người dùng cần **giữ dữ liệu nghiệp vụ** qua restart?

Có thể giải quyết bằng hai lớp riêng. Ví dụ authentication dùng session Redis, trong khi giỏ hàng được lưu ở database qua cart ID. Hoặc API dùng bearer token xác thực stateless, còn dữ liệu nghiệp vụ vẫn nằm trong database. Một token ký số hợp lệ có thể được xác minh trên instance mới nếu signing keys, expiry và validation policy còn phù hợp; tuy nhiên logout/revocation, rotation và việc token bị đánh cắp cần chiến lược riêng. **“JWT” không tự đồng nghĩa an toàn, cũng không tự giữ cart hay dữ liệu server-side.**

| Lựa chọn | Ưu điểm | Giới hạn |
| --- | --- | --- |
| In-memory `HttpSession` | Đơn giản, nhanh, không cần store | Mất state khi process restart/failover |
| Disk persistence của servlet container | Có thể phục hồi khi restart cùng storage, nếu điều kiện phù hợp | Không phải HA mặc định; cần serialization, disk durable |
| Spring Session + Redis | Chia sẻ session giữa replicas, hợp lý cho traffic cao | Redis availability/TTL/eviction/serialization là yếu tố mới |
| Spring Session + JDBC | Chia sẻ và lưu session trong DB | Database throughput, schema, cleanup, connection cost |
| Stateless token auth + database nghiệp vụ | Web instance không cần giữ auth session trên heap | Token expiry/revocation, CSRF nếu dùng cookie, key management |
| Sticky session + local memory | Giảm routing sang node sai khi node sống | Vẫn mất session khi node thay hoặc chết |

Chọn theo SLO, mức độ chấp nhận đăng nhập lại, số instances, lưu lượng, chi phí hạ tầng, yêu cầu bảo mật và cách deploy. Không thay session store để chữa một lỗi nghiệp vụ đòi hỏi transaction hoặc durability thực sự.

## 14. WebFlux: WebSession cũng có vấn đề vòng đời tương tự

Ứng dụng **Spring WebFlux** không sử dụng Servlet `HttpSession` trong đường xử lý reactive thông thường. Nó dùng `org.springframework.web.server.WebSession`, truy cập bất đồng bộ qua `ServerWebExchange.getSession()`. Spring Framework có `InMemoryWebSessionStore` kiểu map-based; với store memory này, app process restart làm session mất. `CookieWebSessionIdResolver` mặc định dùng cookie tên `SESSION`.

Snippet sau chỉ áp dụng cho **dự án WebFlux riêng**, không đưa vào dự án MVC ở phần 5:

```java
@GetMapping("/reactive/visit")
public Mono<String> visit(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        Integer old = session.getAttribute("views");
        int next = old == null ? 1 : old + 1;
        session.getAttributes().put("views", next);
        return "views=" + next;
    });
}
```

Đây là **snippet** trong reactive controller có import `Mono`, `ServerWebExchange` và `@GetMapping`; không runnable độc lập. Việc ghi attribute có thể làm session được bắt đầu theo API WebFlux. Nếu cần session qua restart/replicas, Spring Session hỗ trợ reactive Redis store cùng `WebSessionManager` phù hợp; không giả định có thể lấy nguyên `HttpSession` của Servlet để dùng trong WebFlux.

So sánh:

| MVC / Servlet | WebFlux |
| --- | --- |
| `HttpSession` | `WebSession` |
| `HttpServletRequest.getSession(false)` | `ServerWebExchange.getSession()` trả `Mono<WebSession>` |
| Cookie thường `JSESSIONID` với container | Cookie resolver thường `SESSION` |
| Embedded container local session manager | `InMemoryWebSessionStore` khi không có external store |
| Spring Session có thể thay `HttpSession` store | Spring Session có thể cung cấp reactive session store |
| Memory-only session mất sau restart | Memory-only `WebSession` cũng mất sau restart |

**Không trộn starter và code tùy tiện**: bài mẫu ở trên là Spring MVC với `spring-boot-starter-web`, còn WebFlux cần `spring-boot-starter-webflux` và API reactive tương ứng.

## 15. Bảo mật của session ID và dữ liệu lưu phiên

### 15.1. Session ID hoạt động như credential

Nếu session đang gắn với người dùng đã đăng nhập, người khác có được ID đó có thể thử mạo danh người dùng nếu hệ thống không có kiểm soát bổ sung. Không đưa session ID lên URL, log công khai, analytics, lỗi HTTP hoặc chụp màn hình. Cookie session cần chính sách:

- **HttpOnly**: JavaScript trong browser không đọc được cookie qua `document.cookie`; vẫn phải phòng chống XSS.
- **Secure**: chỉ gửi cookie qua HTTPS; dùng cùng TLS deployment và reverse proxy headers đúng.
- **SameSite**: giới hạn việc browser gửi cookie trong cross-site context; chọn Lax/Strict/None tùy nhu cầu, `None` thường phải kèm Secure.
- **Domain/Path**: giới hạn phạm vi cookie tới hostname/routes cần thiết, tránh scope quá rộng.
- **Timeout**: giới hạn idle session và absolute lifetime nếu nghiệp vụ yêu cầu.

Trong Spring Boot Servlet có các cấu hình như `server.servlet.session.cookie.http-only`, `.secure`, `.same-site`, `.domain`, `.path` và `.max-age`. Khi dùng Spring Session cần kiểm tra nó có sử dụng cookie serializer/ID resolver riêng hay không trước khi áp dụng thuộc tính container.

### 15.2. Session fixation

Nếu một session ID được giữ nguyên qua bước xác thực trong các tình huống không an toàn, kẻ tấn công có thể thử ép nạn nhân dùng ID mà kẻ tấn công đã biết (*session fixation*). Spring Security hỗ trợ thay đổi session ID khi đăng nhập qua cơ chế session fixation protection phù hợp. Đừng tự triển khai login bằng `session.setAttribute("loggedIn", true)` trong demo rồi dùng nó làm cấu hình xác thực production. Nếu tự có authentication protocol, cần dùng security framework và rotate ID sau đăng nhập theo hợp đồng Servlet/Spring Security.

### 15.3. Dữ liệu nhạy cảm và serialization

Tránh đặt mật khẩu, access token không cần thiết, toàn bộ hồ sơ cá nhân và object chứa connection/resource vào session. Với external store/disk persistence, object có thể cần khả năng serialize, thay đổi version có thể làm restore lỗi hoặc phát lộ dữ liệu không cần thiết. Hạn chế session attributes thành dữ liệu nhỏ, đơn giản, có TTL và có thể tái tạo; xử lý encryption, ACL và retention của store đúng chính sách.

### 15.4. CSRF và cookie authentication

Cookie có thể được browser tự gửi cùng request. Nếu authentication dựa trên cookie/session, state-changing requests cần CSRF protection phù hợp (ví dụ Spring Security CSRF). Chuyển sang Redis không tự giải quyết CSRF; chuyển sang token cũng không tự an toàn nếu token lưu trong cookie và tự gửi. Khi session mất sau restart, CSRF token cũ có thể không còn khớp: UI nên hướng dẫn refresh/reload và tránh âm thầm submit lại thao tác quan trọng.

## 16. Thiết kế ứng xử khi phiên bị mất

### 16.1. Trải nghiệm người dùng

Nếu cần session mà không còn session hợp lệ:

- Trang server-rendered có thể redirect về login hoặc trang giải thích phiên đã hết hạn.
- API nên trả mã phản ánh trạng thái authentication/authorization đúng contract, ví dụ 401 nếu chưa xác thực; không tự trả 500 vì session đã mất như một sự cố chưa xử lý.
- Với form nhiều bước, lưu bản nháp vào nguồn bền vững có permission và TTL nếu cần khôi phục.
- Trước khi gửi lại giao dịch, kiểm tra transaction/idempotency status để tránh thao tác trùng.
- Tránh hiển thị lý do “server vừa restart” nếu chưa có bằng chứng; một thông điệp “Phiên đã hết hạn hoặc không còn hợp lệ, vui lòng đăng nhập lại” thường chính xác hơn.

Với API mẫu trong phần 5, `GET /session/status` trả text `session=missing` để học. Nó **không phải** một endpoint authentication/authorization production; trong ứng dụng thật phải dùng Spring Security và HTTP status thích hợp.

### 16.2. Tránh tạo session không cần thiết

Nếu mọi request đến trang public đều gọi `getSession(true)`, server có thể tạo session cho cả bot/health checks, làm tăng số lượng object lưu trên heap. Hãy dùng `getSession(false)` khi chỉ kiểm tra session hiện có; chỉ tạo session lúc thực sự cần state. Với health probes, static assets hoặc API stateless, tránh buộc tạo session nếu không có lý do.

### 16.3. Không dùng session cho tiến trình lâu dài

Một background job, upload kéo dài hoặc việc xuất báo cáo nên có task ID và trạng thái bền vững trong database/queue phù hợp. Khi web instance restart, worker hoặc job có thể tiếp tục dựa trên nguồn dữ liệu đó; session không có hợp đồng bảo đảm hoàn thành một công việc dở dang. Nếu user phải đăng nhập lại, quyền xem task nên được xác minh lại bằng identity thay vì dựa duy nhất vào session ID cũ.

## 17. Giám sát và kiểm thử session restart trong môi trường triển khai

Các phép kiểm thử nên có:

1. **Normal flow:** tạo session qua request, lưu cookie, đọc lại attribute và cập nhật counter khi process chưa restart.
2. **Restart:** dừng rồi khởi động lại đúng JVM với memory-only, gửi cookie cũ, xác nhận session không được tìm thấy; tạo session mới thành công.
3. **Timeout:** đặt timeout ngắn ở môi trường thử, không gửi request trong khoảng timeout, kiểm tra server invalidates session.
4. **Logout:** gọi `invalidate()`, dùng lại cookie cũ và kiểm tra không còn dữ liệu.
5. **Two-node:** request đầu vào A, request sau vào B; xác nhận memory-only không chia sẻ state nếu không có affinity.
6. **Rolling deploy:** kiểm tra người dùng có bị logout không khi thay pod; đối chiếu với shared store.
7. **Redis/JDBC failure:** mô phỏng store timeout/unavailable, bảo đảm lỗi có giới hạn thời gian và alert rõ.
8. **Serializer upgrade:** khi đổi phiên bản app, thử đọc session tạo từ version cũ trước khi rollout.
9. **High concurrency:** số session đang hoạt động, memory footprint/GC, tốc độ tạo/expire session và cookie cardinality.
10. **Security:** HttpOnly/Secure/SameSite, cookie scope, session ID rotation, logout, CSRF và các request không có quyền.

### 17.1. Chỉ số và log cần có

- Process restart count, JVM uptime, container/pod replacement, deploy timestamps.
- Số active sessions, session creation/expiration/invalidation rate nếu container/store expose.
- Heap usage, GC pauses, session object sizes hoặc các điểm retention nếu memory-only.
- Redis/JDBC latency, errors, availability, eviction, TTL/expired keys nếu external store.
- Tỉ lệ 401/302 đến login hoặc lỗi “session expired” sau deployment.
- User-visible error rate khi đang làm form/giỏ hàng/checkout.
- Không log raw session ID hoặc session attributes nhạy cảm; có thể dùng mã correlation riêng và dữ liệu thống kê có kiểm soát.

Đừng kết luận chỉ từ số `JSESSIONID` cookies được gửi: mỗi request có thể tiếp tục mang ID cũ sau khi session phía server đã bị xóa. Chỉ số quan trọng là **ID có tra được state đúng không** và **ứng dụng có xử lý được khi không tìm thấy không**.

## 18. Những ngộ nhận và cách sửa

| Nhận định sai | Giải thích |
| --- | --- |
| “Cookie còn thì session còn.” | Cookie chỉ giữ ID; store phía server có thể đã mất dữ liệu. |
| “Timeout 30 phút nghĩa là server restart vẫn giữ session 30 phút.” | Timeout là inactivity policy, không phải tính bền vững qua process restart. |
| “Thêm sticky sessions bảo đảm đăng nhập không mất khi deploy.” | Khi node đang giữ session chết/thay, affinity không khôi phục memory của node. |
| “Spring Boot luôn lưu session xuống disk vì dùng Tomcat.” | Boot 3.3 mặc định `server.servlet.session.persistent=false`. |
| “Đặt cookie Max-Age một tháng là giữ login một tháng.” | Server-side session có thể expire/invalidate/restart trước cookie; cần thiết kế authentication persistence riêng. |
| “Redis chắc chắn không mất session.” | Redis có TTL, eviction, outage, restart/persistence và serialization constraints. |
| “JWT lưu giỏ hàng và tránh mọi server state.” | JWT chỉ là một định dạng token; dữ liệu nghiệp vụ vẫn cần persistence và revocation/expiry có tradeoff. |
| “Mọi lỗi 401 sau deploy là do session mất.” | Còn có invalid token, cookie scope, security config, clock, store hoặc authorization. |
| “Bắt đầu session ở mọi GET không ảnh hưởng gì.” | Session objects/cookies/heap và quản lý expiration có chi phí khi lưu lượng lớn. |
| “Lưu cả entity JPA trong session thuận tiện và an toàn.” | Có thể tạo dữ liệu stale, serialization issues, memory pressure và rò rỉ thông tin. |
| “Đổi sang Spring Session sẽ bảo toàn mọi HTTP request dở dang.” | Session store chỉ lưu state giữa requests; request/transaction dở dang cần cơ chế riêng. |
| “Logout chỉ cần xóa cookie.” | Server session cần invalidate và authentication/session cleanup theo security contract; cookie và server state là hai lớp. |

## 19. Bài tập vận dụng

**Câu 1.** Một browser đã có cookie `JSESSIONID=abc` và server vừa restart trong chế độ memory-only. Cookie còn có nghĩa sẽ đăng nhập sẵn không?  
**Đáp án:** Không. Server mới không còn map session tương ứng; cookie cũ không đủ khôi phục authentication/session attributes.

**Câu 2.** Handler chỉ muốn biết session có tồn tại, nhưng gọi `request.getSession()`. Có vấn đề gì?  
**Đáp án:** API có thể tạo session mới. Dùng `request.getSession(false)` để kiểm tra mà không tạo session.

**Câu 3.** Dự án dùng 4 pods với sticky sessions; người dùng trên pod A. Khi A bị xóa, có giữ giỏ hàng trong `HttpSession` local không?  
**Đáp án:** Không, dữ liệu trong memory A mất; sticky session không sao chép state sang pod khác.

**Câu 4.** Đã thêm Spring Session Redis và restart ứng dụng, nhưng người dùng vẫn mất session. Nêu ít nhất ba điều phải kiểm tra.  
**Đáp án:** Redis có còn dữ liệu/TTL không, các app cùng Redis namespace không, cookie name/domain/path còn đúng không, session attributes có deserialize được không, và Redis có bị eviction/restart không có persistence không.

**Câu 5.** Vì sao giỏ hàng quan trọng không nên chỉ giữ trong `HttpSession` memory?  
**Đáp án:** Session có thể mất do restart/timeout/failover và không có hợp đồng dữ liệu bền vững; nên lưu dữ liệu nghiệp vụ trong database theo định danh an toàn.

**Câu 6.** Nếu nâng `server.servlet.session.timeout` từ 30 phút lên 24 giờ, app có giữ session qua restart không?  
**Đáp án:** Không đối với memory-only. Nó chỉ thay đổi thời gian hết hạn khi session còn trong store, và có thể làm tăng tài nguyên cần giữ.

**Câu 7.** Tại sao browser có thể giữ cookie cũ sau `session.invalidate()`?  
**Đáp án:** Invalidate xóa session phía server, không bảo đảm xóa cookie phía browser trong mọi triển khai; cần quản lý cookie expiration theo chính sách/logout.

**Câu 8.** Hệ thống API dùng bearer JWT với signing key nhất quán, không có `HttpSession`. Web pod restart có tự làm JWT mất hiệu lực không?  
**Đáp án:** Không chỉ vì pod restart, nếu key và chính sách xác minh vẫn tương thích. Nhưng token expiry, revoke và sự cố key management vẫn ảnh hưởng.

## 20. Checklist trước khi triển khai

- [ ] Đã xác định rõ session là memory-only, disk persistence hay Spring Session external store.
- [ ] Đã hiểu cookie chỉ chứa session ID và khác dữ liệu session.
- [ ] Đã kiểm tra default `server.servlet.session.persistent`/timeout của Boot version đang dùng.
- [ ] Không dùng `getSession(true)` khi chỉ muốn kiểm tra phiên hiện hữu.
- [ ] Không lưu dữ liệu nghiệp vụ không thể mất chỉ trong `HttpSession` local.
- [ ] Khi có nhiều instances, đã thử routing qua node khác và failover.
- [ ] Với Redis/JDBC, có cấu hình TTL, capacity, persistence/HA, serialization và timeout.
- [ ] Đã thử restart ứng dụng thật mà giữ cookie jar không đổi.
- [ ] Có UX phù hợp khi session không còn hợp lệ, tránh gửi trùng giao dịch.
- [ ] Có logout/invalidation, session fixation protection, cookie HttpOnly/Secure/SameSite và CSRF theo hệ thống xác thực.
- [ ] Session attributes nhỏ, đủ mức cần thiết và không chứa credential nhạy cảm.
- [ ] Đã quan sát lỗi session, deploy timestamp, process restart và resource usage.
- [ ] Đã kiểm thử rolling deploy, timeout, store failure và migration version nếu cần giữ session ổn định.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Common Application Properties: server.servlet.session](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 — Servlet Web Applications: Customizing Embedded Servlet Containers](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Spring Session](https://docs.spring.io/spring-boot/3.3/reference/web/spring-session.html)
- [Spring Session 3.3 — Boot với Redis](https://docs.spring.io/spring-session/reference/3.3/guides/boot-redis.html)
- [Spring Session 3.3 — WebSession Integration](https://docs.spring.io/spring-session/reference/3.3/web-session.html)
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Framework 6.1 — WebSession](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework 6.1 — CookieWebSessionIdResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html)
- [Apache Tomcat 10.1 — Manager Component and Persistence Across Restarts](https://tomcat.apache.org/tomcat-10.1-doc/config/manager.html)

**Điều cần nhớ:** với Spring Boot dùng session **trong bộ nhớ tiến trình**, restart làm mất các session attributes của instance cũ, cho dù browser vẫn có thể gửi ID cũ. Muốn giữ trải nghiệm người dùng qua rollout/failover, cần quyết định rõ dữ liệu nào phải lưu bền, triển khai session store phù hợp, cấu hình cookie an toàn và kiểm thử restart thực tế trên cùng cookie thay vì chỉ nhìn server đã mở cổng.
