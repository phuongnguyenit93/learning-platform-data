# Session ID, cookie phiên và dữ liệu được lưu phía máy chủ

Khi ứng dụng web cần nhớ một người dùng đã đăng nhập hoặc giữ giỏ hàng qua nhiều HTTP request, máy chủ có thể tạo một **phiên (session)** và cấp cho trình duyệt một **Session ID**. Trình duyệt thường gửi lại ID này bằng **cookie phiên**, còn dữ liệu gắn với phiên được quản lý phía máy chủ. Đây là nền tảng để hiểu cơ chế đăng nhập dựa trên phiên của ứng dụng Servlet và Spring Security.

Sau bài này, bạn cần phân biệt rõ Session ID, cookie và dữ liệu phiên; mô tả được vòng đời của một phiên; biết cách dùng `HttpSession` trong Servlet; và nhận ra các nguy cơ như đánh cắp phiên, session fixation, CSRF và cấu hình cookie sai.

## 1. Ba khái niệm thường bị nhầm lẫn

| Thành phần | Nằm ở đâu? | Chức năng | Ví dụ |
|---|---|---|---|
| **Session ID** | Là một giá trị định danh được máy chủ cấp; thường xuất hiện trong cookie ở trình duyệt | Giúp máy chủ tra cứu phiên tương ứng; phải khó đoán và không mang ý nghĩa nghiệp vụ | `JSESSIONID=R8eK2p...` |
| **Cookie phiên** | Được trình duyệt lưu theo quy tắc của cookie và gửi trong request phù hợp | Là phương tiện thường dùng để chuyển Session ID giữa trình duyệt và máy chủ | `Cookie: JSESSIONID=R8eK2p...` |
| **Dữ liệu phiên** | Được lưu hoặc quản lý phía máy chủ: bộ nhớ, kho phiên phân tán... | Giữ trạng thái gắn với một phiên | `userId`, giỏ hàng, `SecurityContext` khi cơ chế phù hợp được bật |

**Điểm cốt lõi:** Cookie `JSESSIONID` thông thường **chỉ chứa ID**, không chứa toàn bộ đối tượng người dùng, mật khẩu, quyền hạn hoặc giỏ hàng. Máy chủ dùng ID nhận được để tìm trạng thái phiên. Một cookie *có thể* chứa dữ liệu hay token theo thiết kế khác, vì vậy không được kết luận rằng mọi cookie đều là Session ID.

Session ID **khác** user ID: một người dùng có thể có nhiều phiên trên nhiều trình duyệt hoặc thiết bị; một phiên có thể tồn tại trước khi đăng nhập. Session ID chỉ là khóa tra cứu và không tự chứng minh rằng người dùng đã xác thực thành công.

## 2. Vì sao cần session nếu HTTP không lưu trạng thái?

HTTP xử lý mỗi request độc lập. Nếu chỉ nhìn vào các request rời rạc, máy chủ không mặc nhiên biết hai request đến từ cùng một phiên sử dụng. Cơ chế session bổ sung liên kết đó:

1. Khi cần lưu trạng thái, ứng dụng hoặc servlet container tạo một phiên với ID khó dự đoán.
2. Máy chủ lưu dữ liệu theo phiên và gửi một cookie mang ID cho trình duyệt, thường qua header `Set-Cookie`.
3. Trình duyệt lưu cookie và tự gửi `Cookie` trong các request tiếp theo thỏa điều kiện tên miền, đường dẫn, HTTPS và chính sách SameSite.
4. Máy chủ nhận ID, tra phiên còn hợp lệ, sau đó đọc hoặc cập nhật dữ liệu trong phiên.
5. Phiên có thể hết hạn do không hoạt động, bị hủy khi logout hoặc bị thay ID trong một số thao tác bảo mật.

Ví dụ HTTP minh họa sau khi đăng nhập thành công:

```http
HTTP/1.1 302 Found
Location: /profile
Set-Cookie: JSESSIONID=demoR8eK2p; Path=/; Secure; HttpOnly; SameSite=Lax
```

Request kế tiếp gửi cookie phù hợp:

```http
GET /profile HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=demoR8eK2p
```

Giá trị `demoR8eK2p` chỉ để minh họa; ID thật phải được hệ thống sinh với tính ngẫu nhiên đủ mạnh. Header `Set-Cookie` chứa các thuộc tính `Path`, `Secure`, `HttpOnly`, `SameSite`; header `Cookie` ở request chỉ gửi cặp tên–giá trị. Cookie cũng có thể chưa xuất hiện nếu endpoint không cần tạo phiên.

Với Servlet container thông thường, tên cookie mặc định thường là `JSESSIONID`. Tên này **có thể được cấu hình khác**; chẳng hạn một ứng dụng dùng Spring Session có thể dùng cookie `SESSION`. Vì vậy không nên viết logic nghiệp vụ phụ thuộc cứng vào một tên cookie cụ thể nếu hệ thống cho phép thay đổi.

## 3. Dữ liệu thực sự được lưu và tra cứu như thế nào?

Có thể hình dung kho phiên ở máy chủ như sau:

```text
Trình duyệt A
  Cookie: JSESSIONID=S-A
                         Máy chủ / kho phiên
                         S-A -> { userId: "u42", cartCount: 3 }
                         S-B -> { userId: "u99", cartCount: 1 }
Trình duyệt B
  Cookie: JSESSIONID=S-B
```

Trình duyệt A không nhận được đối tượng `{ userId, cartCount }` chỉ vì máy chủ có lưu đối tượng đó; nó chỉ mang khóa `S-A`. Nếu phiên `S-A` bị xóa hoặc hết hạn thì việc gửi lại ID cũ không phục hồi dữ liệu cũ.

Ví dụ Java 17 độc lập sau chỉ **mô phỏng phép tra cứu** để làm rõ ranh giới giữa cookie và kho dữ liệu. Nó không thay thế `HttpSession` hay bộ sinh Session ID an toàn của servlet container.

Tệp `SessionLookupDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class SessionLookupDemo {
    public static void main(String[] args) {
        Map<String, Map<String, String>> serverSessions = new HashMap<>();
        String demoSessionId = "demo-123";
        serverSessions.put(
                demoSessionId,
                Map.of("userId", "u42", "cartCount", "3")
        );

        String cookieHeader = "JSESSIONID=" + demoSessionId;
        String receivedId = cookieHeader.substring("JSESSIONID=".length());
        Map<String, String> state = serverSessions.get(receivedId);

        System.out.println("Cookie: " + cookieHeader);
        System.out.println("userId tren server: " + state.get("userId"));
        System.out.println("cartCount tren server: " + state.get("cartCount"));
        System.out.println("Cookie co chua userId? " + cookieHeader.contains("userId"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac SessionLookupDemo.java
java SessionLookupDemo
```

Kết quả chính xác:

```text
Cookie: JSESSIONID=demo-123
userId tren server: u42
cartCount tren server: 3
Cookie co chua userId? false
```

Chương trình dùng ID cố định cho đầu ra dễ kiểm chứng. Ứng dụng thật **không** tự dùng `demo-123`, ID tuần tự hoặc dữ liệu dễ đoán làm Session ID; servlet container quản lý việc tạo và kiểm soát ID.

## 4. `HttpSession` trong ứng dụng Servlet

Trong Servlet API, `jakarta.servlet.http.HttpSession` là giao diện thao tác dữ liệu phiên. Với Spring Boot 3 và Spring MVC, package Servlet sử dụng `jakarta.servlet.*`, không phải `javax.servlet.*` của các thế hệ cũ.

Các thao tác quan trọng:

| Lệnh | Ý nghĩa |
|---|---|
| `request.getSession()` | Lấy phiên hiện có hoặc **tạo phiên mới** nếu chưa có |
| `request.getSession(false)` | Chỉ lấy phiên hiện có; trả `null` nếu không có phiên hợp lệ |
| `session.getId()` | Lấy Session ID hiện tại |
| `session.setAttribute(name, value)` | Ghi dữ liệu thuộc phiên phía máy chủ |
| `session.getAttribute(name)` | Đọc dữ liệu thuộc phiên |
| `session.removeAttribute(name)` | Xóa một thuộc tính của phiên |
| `session.invalidate()` | Hủy phiên hiện tại; ID cũ không còn tra được phiên đó |
| `session.setMaxInactiveInterval(seconds)` | Thiết lập khoảng không hoạt động tối đa trước khi phiên hết hạn |

Ví dụ controller Servlet dùng một phiên để đếm số lượt truy cập. Đây là mã dùng trong **dự án Spring Boot Web MVC có dependency Servlet/Spring Web**, không phải chương trình Java độc lập:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VisitController {
    @GetMapping("/visits")
    public String visits(HttpServletRequest request) {
        HttpSession session = request.getSession();
        Integer previous = (Integer) session.getAttribute("visits");
        int current = previous == null ? 1 : previous + 1;
        session.setAttribute("visits", current);
        return "Luot truy cap trong phien: " + current;
    }
}
```

Nếu cùng một trình duyệt gọi `/visits` hai lần, gửi lại cookie hợp lệ và phiên chưa hết hạn, response lần lượt là `Luot truy cap trong phien: 1` và `Luot truy cap trong phien: 2`. Trình duyệt khác với phiên khác sẽ có bộ đếm riêng. Ví dụ này minh họa lưu trạng thái; phép đọc–tăng–ghi **không an toàn trước các request đồng thời**, nên không dùng nguyên mẫu bộ đếm này cho dữ liệu cần tính nhất quán trong production.

Nếu chỉ cần kiểm tra phiên đã tồn tại, hãy dùng `request.getSession(false)` để tránh vô tình tạo phiên cho mỗi request:

```java
HttpSession session = request.getSession(false);
if (session == null) {
    // Chưa có phiên hợp lệ: xử lý theo yêu cầu endpoint.
}
```

Đừng lưu mật khẩu thô, bí mật dài hạn hoặc đối tượng quá lớn vào session. Dữ liệu phiên ngốn bộ nhớ/dung lượng kho lưu trữ; với cụm máy chủ nhiều instance, việc giữ session chỉ trong RAM của một instance có thể khiến request chuyển sang instance khác không tìm thấy trạng thái. Có thể dùng cơ chế chia sẻ phiên như Spring Session kết hợp kho lưu trữ phù hợp hoặc kiến trúc cân bằng tải được thiết kế cho trạng thái đó.

## 5. Spring Security sử dụng phiên để duy trì đăng nhập ra sao?

Ở ứng dụng **Spring Security Servlet** dùng xác thực có trạng thái, kết quả xác thực thành công thường được biểu diễn bởi `Authentication` trong `SecurityContext`. Tùy cấu hình `SecurityContextRepository`, context có thể được lưu trong `HttpSession` (ví dụ `HttpSessionSecurityContextRepository`, sử dụng thuộc tính `SPRING_SECURITY_CONTEXT`). Những request phù hợp về sau có thể đọc lại context từ phiên để biết người dùng đã xác thực.

Dòng xử lý về mặt ý tưởng:

1. Người dùng xác thực thông qua cơ chế được ứng dụng cấu hình, chẳng hạn form login.
2. Spring Security thiết lập `Authentication` hợp lệ và cơ chế đăng nhập thích hợp lưu trạng thái bảo mật khi cần.
3. Browser gửi Session ID trong cookie ở request tiếp theo.
4. Bộ lọc bảo mật sử dụng repository đã cấu hình để có `SecurityContext`, sau đó áp dụng các quy tắc phân quyền.
5. Khi logout hoặc phiên không còn hợp lệ, context của phiên cũ không còn được dùng để xác thực request mới.

**Không phải mọi ứng dụng Spring Security đều lưu đăng nhập trong `HttpSession`.** API dùng Bearer token và chính sách stateless có thể xác thực mỗi request từ token mà không đọc SecurityContext của HTTP session. Ngay cả trong ứng dụng stateful, việc gọi `getSession()` chỉ tạo phiên; hành động đó **không tự đăng nhập** người dùng.

Ví dụ cấu hình cơ bản cho Spring Security 6 trên Servlet (đặt trong ứng dụng Spring Boot, kèm các import):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/visits").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
                .build();
    }
}
```

`IF_REQUIRED` cho phép Spring Security tạo session khi cơ chế bảo mật cần; đây cũng là chính sách thường dùng cho ứng dụng dựa trên phiên. Cấu hình ví dụ không tắt CSRF. Cần hiểu chính sách tạo session:

- `ALWAYS`: Spring Security chủ động tạo session.
- `IF_REQUIRED`: chỉ tạo khi cần.
- `NEVER`: Spring Security không tạo session mới nhưng có thể sử dụng session đã tồn tại.
- `STATELESS`: Spring Security không tạo hoặc sử dụng `HttpSession` để lấy `SecurityContext`; code ứng dụng khác vẫn có thể chủ động gọi Servlet API để tạo session, nên không nên diễn giải là toàn hệ thống tuyệt đối không có session.

Spring Security 6 sử dụng các cơ chế lưu `SecurityContext` tùy cấu hình; nếu tự viết quy trình đăng nhập và gắn `Authentication` thủ công vào `SecurityContextHolder`, chỉ đặt vào thread-local chưa bảo đảm đăng nhập được duy trì ở request sau. Phải lưu context qua `SecurityContextRepository` thích hợp hoặc dùng sẵn cơ chế xác thực của framework.

## 6. Thuộc tính cookie quyết định phạm vi và mức bảo vệ

| Thuộc tính | Ý nghĩa và cách sử dụng |
|---|---|
| `HttpOnly` | JavaScript thông thường không đọc được cookie qua `document.cookie`; giảm khả năng lấy ID qua XSS, nhưng không ngăn XSS gửi request thay người dùng |
| `Secure` | Trình duyệt chỉ gửi cookie qua kết nối HTTPS (ngoại lệ/chi tiết localhost tùy trình duyệt); nên bật khi triển khai HTTPS |
| `SameSite=Lax` | Giảm gửi cookie ở một số request cross-site; thường phù hợp với nhiều ứng dụng web thông thường |
| `SameSite=Strict` | Hạn chế cross-site mạnh hơn, có thể ảnh hưởng luồng chuyển hướng và trải nghiệm đăng nhập |
| `SameSite=None` | Cho phép gửi trong ngữ cảnh cross-site phù hợp; trình duyệt hiện đại yêu cầu kèm `Secure` |
| `Path`, `Domain` | Giới hạn URL path/host mà cookie được gửi; tránh mở rộng phạm vi khi không cần |
| `Max-Age` / `Expires` | Điều khiển thời gian browser giữ cookie; không đồng nghĩa với thời gian phiên server còn hiệu lực |

Ví dụ cấu hình Spring Boot cho cookie phiên của servlet container, áp dụng khi ứng dụng được phục vụ qua HTTPS:

```properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
```

`server.servlet.session.timeout` là thời gian không hoạt động của phiên phía máy chủ (cách thực thi có thể phụ thuộc container), còn `cookie.max-age` nếu cấu hình là chính sách lưu cookie ở trình duyệt. Chúng là **hai vòng đời riêng**: browser có cookie nhưng server đã xóa phiên thì request vẫn không được coi là đã đăng nhập. Tương tự, xóa cookie khỏi trình duyệt không tự xóa bản ghi phiên trên server ngay tại thời điểm đó.

`Secure` ở môi trường HTTPS là rất quan trọng; nếu bật khi kiểm thử qua HTTP thông thường, trình duyệt có thể không gửi cookie khiến request liên tục tạo phiên mới. Khi chạy sau reverse proxy/ingress, phải cấu hình HTTPS và forward headers đúng theo hạ tầng để máy chủ nhận biết scheme của kết nối. Không tin mù quáng mọi `X-Forwarded-*` từ nguồn không được kiểm soát.

## 7. Vòng đời phiên: tạo, đổi ID, hết hạn và logout

**Tạo phiên:** Tại request đầu tiên cần phiên, container tạo ID và dữ liệu phiên ban đầu có thể rỗng. Không giả định cứ truy cập website là có cookie `JSESSIONID`.

**Đổi Session ID khi đăng nhập:** Session fixation xảy ra khi kẻ tấn công khiến nạn nhân dùng trước một Session ID mà kẻ đó đã biết rồi chờ nạn nhân đăng nhập. Biện pháp quan trọng là **thay Session ID khi xác thực thành công**. Trong Spring Security Servlet hiện đại, `changeSessionId` là cơ chế bảo vệ thường được áp dụng theo mặc định khi khả dụng; phương thức này đổi ID của phiên hiện tại, thường giữ lại thuộc tính phiên. Không tự triển khai luồng đổi ID tùy tiện nếu framework đã hỗ trợ.

**Hết hạn do không hoạt động:** Session thường có thời gian idle timeout. Khi hết hạn, ID cũ không còn tra được trạng thái trước đó. Máy chủ có thể tạo một phiên khác nếu request tiếp theo cần, đồng nghĩa browser có thể nhận cookie ID mới. Điều này khác với logout chủ động và khác với thời hạn lưu cookie.

**Logout:** Trong ứng dụng dùng session, logout đúng cách phải loại bỏ trạng thái xác thực và vô hiệu hóa phiên theo chính sách áp dụng; với Spring Security form login, logout handler mặc định thường invalidate `HttpSession`. Đồng thời có thể xóa cookie ở browser theo cấu hình để giảm nhầm lẫn. Chỉ xóa cookie ở phía client không đủ để bảo đảm phiên đã bị thu hồi trên server nếu ID cũ từng bị đánh cắp.

**Nhiều tab hoặc nhiều thiết bị:** Các tab chung một browser profile thường chia sẻ cookie theo cùng phạm vi nên chia sẻ session; hai thiết bị hoặc profile riêng thường có Session ID khác nhau. Logout một session không mặc nhiên thu hồi mọi session khác của cùng một tài khoản nếu ứng dụng chưa triển khai cơ chế đó.

## 8. Nguy cơ và quy tắc bảo mật cần nhớ

1. **Session hijacking:** Ai nắm được Session ID còn hiệu lực có thể mạo danh phiên trong điều kiện phù hợp. Luôn dùng HTTPS, hạn chế rò ID trong log/URL, đặt `HttpOnly`, `Secure`, chính sách `SameSite` phù hợp, và bảo vệ ứng dụng khỏi XSS. Đừng xem Session ID là dữ liệu công khai.
2. **Session fixation:** Thay ID sau đăng nhập; không cho phép nhận một ID cố định do client chọn rồi xem đó là phiên đã xác thực.
3. **CSRF:** Với xác thực bằng cookie, trình duyệt có thể tự đính cookie vào request. `HttpOnly` **không ngăn CSRF** và `SameSite` không thay thế tất cả biện pháp phòng vệ. Giữ bảo vệ CSRF thích hợp cho các thao tác thay đổi trạng thái; Spring Security Servlet bật CSRF theo mặc định trừ khi cấu hình khác.
4. **Phân quyền:** Sự tồn tại của session chỉ chứng minh có phiên, không chứng minh user có quyền. Quyền truy cập phải được xác định từ trạng thái xác thực đáng tin cậy và kiểm tra tại từng tài nguyên.
5. **Dữ liệu phiên:** Lưu tối thiểu, không lưu credential/bí mật không cần thiết; cân nhắc cập nhật đồng thời, serialization và timeout, nhất là khi phân tán.
6. **CORS / cookie cross-origin:** Nếu frontend gọi API khác origin, việc gửi cookie còn phụ thuộc `credentials` của request, response CORS và chính sách cookie. Không mở tùy tiện credentialed CORS cho mọi origin.

Cẩn thận với suy luận **“có `JSESSIONID` nghĩa là đã đăng nhập”**: request ẩn danh vẫn có thể có session để giữ giỏ hàng hoặc CSRF state. Chỉ kiểm tra Session ID không phải kiểm tra `Authentication`.

## 9. Cách tự quan sát bằng Developer Tools

Trên một ứng dụng Servlet mà bạn có quyền kiểm thử, có thể đối chiếu đúng cơ chế mà không cần đọc dữ liệu bí mật:

1. Mở **Network** và truy cập endpoint được biết có tạo session, ví dụ `/visits` ở ví dụ trên. Xem response header `Set-Cookie`. Nếu không thấy header, xác minh endpoint có thực sự tạo phiên hay đã có phiên hợp lệ từ trước.
2. Trong mục **Application / Storage → Cookies**, quan sát tên, domain, path, `Secure`, `HttpOnly`, `SameSite`, expiration; không chia sẻ giá trị ID thật khi chụp màn hình hoặc ghi log.
3. Gửi request tiếp theo cùng browser profile; ở Network, quan sát request header `Cookie`. Nếu cookie đúng và server session còn hiệu lực, endpoint `/visits` sẽ tăng giá trị lượt truy cập.
4. Mở cửa sổ riêng tư hoặc xóa cookie tương ứng; request mới thường bắt đầu một phiên khác khi endpoint cần. Kiểm tra logout/hết hạn để thấy ID cũ không còn cấp lại trạng thái xác thực.
5. Với môi trường có nhiều instance, kiểm tra kịch bản chuyển instance và xác nhận kho session dùng chung hoặc chiến lược routing đáp ứng thiết kế.

Để kiểm tra cookie bằng dòng lệnh trong môi trường thử nghiệm có URL thực tế phù hợp, `curl -c cookies.txt` lưu cookie từ response và `curl -b cookies.txt` gửi lại cookie đó. Cần dùng endpoint và scheme (HTTP/HTTPS) phù hợp, đồng thời lưu ý `Secure` chỉ được gửi qua HTTPS. Tệp cookie có thể chứa Session ID đang hoạt động nên phải được bảo vệ và xóa sau kiểm thử.

## 10. Tự kiểm tra hiểu đúng

- Browser có `JSESSIONID`, nhưng không gửi trong request do `Path`, `SameSite` hoặc `Secure`: server sẽ không nhận được ID qua cookie ở request ấy, nên không thể dùng nó để tra phiên theo đường truyền đó.
- Browser gửi đúng ID nhưng phiên trên server đã hết hạn: cookie không thể phục hồi phiên cũ.
- Hai request gửi cùng ID trong khi phiên còn sống: về nguyên tắc chúng cùng trỏ tới một phiên; vấn đề cập nhật đồng thời vẫn phải được xử lý.
- Đổi Session ID sau đăng nhập giúp ngăn fixation; việc này khác với việc cấp một user ID mới.
- API stateless xác thực bằng Bearer token không đồng nghĩa với đăng nhập dựa trên cookie `JSESSIONID`; phải đọc cấu hình cơ chế xác thực đang dùng.

**Ghi nhớ:** `Session ID` là khóa tra cứu, **cookie phiên là phương tiện vận chuyển khóa**, còn **dữ liệu phiên nằm và được quản lý ở máy chủ**. Spring Security chỉ coi người dùng đã xác thực khi cơ chế bảo mật khôi phục hoặc xác minh được `Authentication` hợp lệ, không phải chỉ vì browser có cookie phiên.