# Cookie, phiên và tính không lưu trạng thái của HTTP

HTTP được thiết kế theo mô hình request/response: mỗi request cần mang đủ thông tin để máy chủ xử lý request đó. Giao thức không yêu cầu máy chủ phải nhớ trạng thái của request trước. Đặc điểm này thường được gọi là **stateless** (không lưu trạng thái ở cấp giao thức).

Trong ứng dụng web, người dùng lại cần các trải nghiệm có trạng thái như đăng nhập, giỏ hàng, tùy chọn giao diện và quy trình nhiều bước. Cookie và session là hai cơ chế phổ biến để nối các request độc lập thành một trải nghiệm liên tục. Hiểu rõ vai trò của từng cơ chế giúp thiết kế API, cấu hình Spring Boot và bảo vệ ứng dụng đúng cách.

## 1. HTTP stateless có nghĩa gì?

Một HTTP request có thể được xử lý độc lập dựa trên method, URL, header, body và thông tin xác thực được gửi kèm. Máy chủ không cần ghi nhớ rằng cùng client đã gọi một endpoint trước đó.

Ví dụ:

~~~http
GET /products/42 HTTP/1.1
Host: shop.example.com
Accept: application/json
~~~

Máy chủ có thể xử lý request này dựa trên đường dẫn và dữ liệu hiện có. Request tiếp theo đến cùng máy chủ vẫn là một request mới:

~~~http
GET /products/43 HTTP/1.1
Host: shop.example.com
Accept: application/json
~~~

HTTP không tự mang một biến như currentUser hoặc cart từ request đầu sang request sau. Nếu ứng dụng cần biết hai request thuộc cùng một người dùng, ứng dụng phải nhận diện người dùng qua thông tin được gửi lại, chẳng hạn cookie chứa session ID hoặc token trong Authorization header.

Cần phân biệt ba khái niệm:

- **Stateless của HTTP**: giao thức không yêu cầu server nhớ trạng thái xử lý của request trước để hiểu request sau.
- **Stateful của ứng dụng**: ứng dụng lưu dữ liệu giữa các request, ví dụ session đăng nhập hoặc giỏ hàng.
- **Persistent connection**: kết nối TCP/TLS hoặc HTTP được giữ mở để tái sử dụng. Keep-alive và multiplexing không làm cho HTTP tự trở thành giao thức lưu trạng thái nghiệp vụ.

Một ứng dụng có thể dùng HTTP stateless nhưng vẫn lưu trạng thái nghiệp vụ trong database, cache hoặc session store. Stateless cũng không có nghĩa là máy chủ không có bộ nhớ hay không lưu dữ liệu.

## 2. Cookie là gì và hoạt động ra sao?

**Cookie** là một cặp tên/giá trị nhỏ do máy chủ gửi cho trình duyệt thông qua header Set-Cookie. Trình duyệt có thể lưu cookie và tự động gửi lại trong các request tiếp theo khi request khớp phạm vi và chính sách của cookie.

Luồng cơ bản:

1. Trình duyệt gửi request đến máy chủ.
2. Máy chủ trả response có header Set-Cookie.
3. Trình duyệt kiểm tra thuộc tính và lưu cookie nếu chính sách cho phép.
4. Khi gửi request tiếp theo phù hợp, trình duyệt đính kèm cookie trong header Cookie.
5. Máy chủ đọc giá trị cookie để nhận diện hoặc áp dụng tùy chọn tương ứng.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: theme=dark; Path=/; Max-Age=2592000; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

Request tiếp theo đến phạm vi phù hợp có thể chứa:

~~~http
GET /account HTTP/1.1
Host: shop.example.com
Cookie: theme=dark
~~~

Header Set-Cookie được máy chủ gửi trong response; header Cookie do trình duyệt gửi trong request. Trình duyệt không gửi lại toàn bộ thuộc tính như Path, Secure hay SameSite trong header Cookie. Các thuộc tính đó được trình duyệt dùng để quyết định có gửi cookie hay không.

Một response có thể thiết lập nhiều cookie bằng nhiều header Set-Cookie riêng biệt. Không nên gộp nhiều cookie vào một header Set-Cookie duy nhất bằng dấu phẩy vì thuộc tính Expires cũng có thể chứa dấu phẩy. Trong Java/Spring, dùng addHeader cho từng Set-Cookie khi cần gửi nhiều cookie.

## 3. Các thuộc tính quan trọng của cookie

| Thuộc tính | Tác dụng | Cách dùng thường gặp |
|---|---|---|
| **Name=Value** | Tên và giá trị cookie | Giữ giá trị nhỏ, tránh lưu dữ liệu bí mật |
| **Expires** | Thời điểm cookie hết hạn | Dùng khi muốn cookie tồn tại đến một thời điểm cụ thể |
| **Max-Age** | Thời gian tồn tại tính bằng giây | Thường dễ kiểm soát thời lượng hơn Expires |
| **Domain** | Phạm vi host được phép nhận cookie | Bỏ qua nếu chỉ cần host hiện tại; khai báo sẽ mở rộng sang các subdomain phù hợp |
| **Path** | Phạm vi đường dẫn gửi cookie | Dùng Path=/ nếu cookie cần cho toàn bộ ứng dụng |
| **Secure** | Chỉ gửi cookie qua kết nối an toàn HTTPS | Bật trong môi trường production dùng HTTPS |
| **HttpOnly** | Không cho JavaScript đọc cookie qua document.cookie | Bật cho cookie chứa session ID hoặc thông tin xác thực |
| **SameSite** | Kiểm soát việc gửi cookie trong một số ngữ cảnh cross-site | Chọn Lax, Strict hoặc None theo luồng điều hướng và tích hợp |

### 3.1. Expires và Max-Age

Nếu không có Expires hoặc Max-Age, cookie thường được xem là session cookie và được trình duyệt quản lý theo phiên duyệt. Khái niệm phiên trình duyệt không phải lúc nào cũng đồng nghĩa với việc đóng cửa sổ là cookie chắc chắn biến mất; một số trình duyệt có thể khôi phục phiên sau khi khởi động lại.

Max-Age chỉ định số giây cookie được giữ. Ví dụ Max-Age=3600 yêu cầu cookie tồn tại trong một giờ. Expires chỉ định ngày giờ hết hạn. Nếu cả hai cùng có mặt, Max-Age được ưu tiên theo quy tắc cookie hiện hành.

Cookie hết hạn ở trình duyệt và session hết hạn trên máy chủ là hai việc riêng biệt. Xóa cookie phía trình duyệt không tự động xóa session trên server; ngược lại, session server hết hạn không có nghĩa cookie ID đã biến mất khỏi trình duyệt.

### 3.2. Domain và Path

Nếu không khai báo Domain, cookie là host-only cookie: chỉ host đã tạo cookie nhận lại cookie đó. Nếu khai báo Domain, cookie có thể được gửi đến domain được chỉ định và các subdomain phù hợp. Chỉ mở rộng Domain khi thật sự cần chia sẻ cookie giữa nhiều host.

Path giới hạn đường dẫn request được gửi cookie. Ví dụ Path=/admin làm cookie phù hợp với các đường dẫn trong /admin. Path không phải cơ chế phân quyền bảo mật; máy chủ vẫn phải kiểm tra quyền truy cập ở từng endpoint.

### 3.3. Secure và HttpOnly

Secure yêu cầu trình duyệt chỉ gửi cookie qua kết nối an toàn. Thuộc tính này không tự mã hóa giá trị cookie; TLS bảo vệ dữ liệu trên đường truyền.

HttpOnly ngăn JavaScript đọc cookie bằng document.cookie. Điều này làm giảm khả năng mã độc lấy trực tiếp session ID từ cookie khi xảy ra XSS. Tuy nhiên, script độc hại vẫn có thể gửi request từ trang bị xâm nhập và trình duyệt vẫn có thể đính kèm cookie. HttpOnly không thay thế việc ngăn XSS bằng output encoding, kiểm tra input và Content Security Policy phù hợp.

### 3.4. SameSite

SameSite điều khiển việc trình duyệt gửi cookie trong một số request cross-site:

- **Strict**: giới hạn chặt việc gửi cookie trong ngữ cảnh cross-site. Có thể ảnh hưởng trải nghiệm khi người dùng đi vào ứng dụng từ một liên kết bên ngoài.
- **Lax**: cho phép cookie trong một số điều hướng top-level an toàn, đồng thời hạn chế nhiều request cross-site khác. Đây thường là lựa chọn cân bằng cho cookie phiên thông thường.
- **None**: cho phép cookie được gửi trong ngữ cảnh cross-site theo các điều kiện khác của trình duyệt; cookie SameSite=None phải có Secure.

SameSite hữu ích để giảm rủi ro CSRF nhưng không nên được xem là lớp bảo vệ duy nhất. Các luồng đăng nhập qua nhà cung cấp danh tính, iframe hoặc thanh toán bên thứ ba có thể cần chính sách khác nhau; phải kiểm thử trong trình duyệt thực tế.

### 3.5. Prefix cookie

Một số trình duyệt hỗ trợ các prefix giúp áp dụng quy tắc nghiêm ngặt hơn:

- Cookie có prefix __Secure- phải được tạo với thuộc tính Secure.
- Cookie có prefix __Host- phải có Secure, Path=/ và không được khai báo Domain.

Ví dụ tên __Host-session giúp hạn chế cookie bị đặt ở phạm vi subdomain hoặc path khác. Khả năng hỗ trợ và quy tắc cụ thể phụ thuộc trình duyệt; vẫn phải cấu hình thuộc tính đầy đủ.

## 4. Session là gì?

**Session** là cơ chế lưu trạng thái phía máy chủ cho một người dùng hoặc một luồng tương tác trong một khoảng thời gian. Máy chủ tạo một session và cấp cho client một mã định danh ngẫu nhiên, thường gọi là session ID. Trình duyệt lưu mã này trong cookie rồi gửi lại trong request phù hợp.

Mô hình phổ biến:

- Server tạo session và lưu dữ liệu như user ID, giỏ hàng hoặc trạng thái quy trình.
- Server gửi session ID về trình duyệt qua cookie.
- Trình duyệt gửi session ID trong các request sau.
- Server dùng ID để tìm session tương ứng trong session store.
- Khi session hết hạn hoặc bị hủy, ID cũ không còn truy cập được trạng thái đó.

Trong Servlet container, session cookie mặc định thường có tên JSESSIONID. Tên cookie và cơ chế lưu session có thể được cấu hình. Không nên coi JSESSIONID là một định dạng bắt buộc của HTTP; đó là quy ước phổ biến của Servlet container.

Cookie và session không phải hai khái niệm thay thế nhau:

- Cookie là cơ chế lưu và gửi dữ liệu ở phía client.
- Session là trạng thái được quản lý ở phía server.
- Cookie có thể chứa session ID để server tìm đúng session.
- Một cookie tùy chọn giao diện có thể không liên quan đến session.
- Một ứng dụng có thể dùng session mà không lưu nhiều dữ liệu trong cookie; cookie chỉ giữ mã định danh.

## 5. Vòng đời của một HTTP session

Một vòng đời session thường gồm các giai đoạn sau:

1. **Tạo session**: ứng dụng hoặc framework yêu cầu tạo session khi cần lưu trạng thái.
2. **Phát hành ID**: server tạo ID khó đoán và gửi về client, thường bằng Set-Cookie.
3. **Sử dụng session**: trình duyệt gửi lại ID; server tra cứu dữ liệu session và xử lý request.
4. **Gia hạn hoặc hết hạn**: hoạt động có thể làm mới thời gian timeout không hoạt động; nếu quá thời hạn, session bị loại bỏ.
5. **Đăng xuất hoặc hủy**: server invalidate session và xóa dữ liệu tương ứng; cookie ID ở trình duyệt cũng nên được hết hạn nếu cần.

Session timeout thường là thời gian không hoạt động (idle timeout). Nếu yêu cầu bảo mật cần giới hạn tổng thời gian đăng nhập, ứng dụng phải có thêm chính sách absolute timeout; chỉ dựa vào idle timeout có thể cho phép session tồn tại lâu nếu người dùng liên tục hoạt động.

Khi người dùng đăng nhập thành công, cần thay đổi session ID để chống session fixation. Kẻ tấn công có thể tìm cách khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết; nếu ID vẫn giữ nguyên sau đăng nhập, kẻ tấn công có thể lợi dụng session đã được nâng quyền. Spring Security có cơ chế bảo vệ session fixation trong luồng xác thực thông thường, nhưng cần kiểm tra lại nếu ứng dụng tùy chỉnh authentication hoặc session management.

Không nên lưu mật khẩu, access token dài hạn, thông tin thanh toán nhạy cảm hoặc toàn bộ đối tượng lớn trong session. Chỉ lưu dữ liệu tối thiểu cần thiết, kiểm soát thời hạn và giới hạn quyền truy cập.

## 6. Cookie, session và token: phân biệt cách lưu trạng thái

| Cơ chế | Dữ liệu nằm ở đâu? | Request mang gì? | Máy chủ cần tra cứu trạng thái? |
|---|---|---|---|
| Cookie tùy chọn | Trình duyệt | Cookie name/value | Không nhất thiết |
| Cookie chứa session ID | Session store phía server; cookie giữ ID | Session ID trong Cookie | Có |
| Server-side session | Database, cache hoặc bộ nhớ server | ID tham chiếu session | Có |
| Bearer token opaque | Client giữ token; server hoặc authorization service quản lý token | Token trong Authorization header | Thường có tra cứu hoặc introspection |
| JWT access token | Client giữ token; claims nằm trong token đã ký | JWT trong Authorization header hoặc cookie | Có thể xác minh chữ ký mà không cần tra cứu mỗi request |

JWT thường được mã hóa dạng Base64URL và ký để bảo vệ tính toàn vẹn; phần payload không tự động được mã hóa bí mật. Người có token thường có thể đọc claims. Không đưa mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm vào payload JWT thông thường.

Dùng token không tự động làm hệ thống an toàn hơn session. Cần cân nhắc thời gian sống, thu hồi token, xoay khóa, lưu trữ phía client và rủi ro XSS/CSRF. Token lưu trong cookie vẫn có thể được trình duyệt tự động gửi và vì vậy vẫn cần đánh giá CSRF. Token trong Authorization header thường không tự động được gửi theo điều hướng trình duyệt thông thường, nhưng nếu bị lộ qua XSS thì vẫn có thể bị đánh cắp.

## 7. Stateful và stateless trong thiết kế ứng dụng

### 7.1. Stateful session

Ứng dụng lưu session phía server và client chỉ gửi session ID. Ưu điểm là có thể thu hồi session ngay lập tức bằng cách invalidate hoặc xóa dữ liệu session; client không cần gửi toàn bộ trạng thái trong mỗi request.

Đổi lại, server phải quản lý kho session, timeout, đồng bộ giữa các node và tình huống mất session store. Khi triển khai nhiều instance, session chỉ nằm trong bộ nhớ một node sẽ gây lỗi nếu request tiếp theo được định tuyến sang node khác.

Các lựa chọn triển khai phổ biến:

- **Sticky session**: load balancer cố định request của một client vào cùng node. Cách này giảm việc chia sẻ session nhưng vẫn cần xử lý khi node hỏng hoặc thay đổi topology.
- **Session replication**: các node đồng bộ dữ liệu session; cần cân nhắc chi phí đồng bộ và độ trễ.
- **Shared session store**: lưu session trong Redis hoặc JDBC để nhiều instance cùng đọc/ghi. Spring Session hỗ trợ tích hợp các kho lưu trữ như Redis và JDBC.

Nếu dùng shared store, cần xác định TTL, serialization, giới hạn kích thước, khả năng tương thích khi deploy phiên bản mới và cách xử lý khi store tạm thời không truy cập được.

### 7.2. Stateless authentication

Với thiết kế stateless, server không giữ session đăng nhập riêng cho từng client. Mỗi request mang thông tin xác thực đủ để server xác minh, chẳng hạn bearer token có chữ ký. Server vẫn có thể truy vấn database để đọc quyền hoặc dữ liệu nghiệp vụ; stateless ở đây nói về việc không phụ thuộc vào session đăng nhập được giữ giữa các request.

Ưu điểm là các instance dễ xử lý request độc lập và không cần chia sẻ session đăng nhập. Đổi lại, thu hồi token trước thời điểm hết hạn có thể phức tạp; cần thiết kế access token ngắn hạn, refresh token, denylist hoặc introspection nếu yêu cầu bảo mật đòi hỏi.

### 7.3. Chọn theo nhu cầu

- Ứng dụng web truyền thống dùng đăng nhập và server-side rendering thường phù hợp với session cookie.
- API cho mobile hoặc service-to-service thường dùng bearer token trong Authorization header.
- Ứng dụng có nhiều node và cần thu hồi phiên tức thì có thể dùng Spring Session với Redis/JDBC.
- Một hệ thống có thể kết hợp session cho giao diện web và token cho API bên ngoài, miễn là ranh giới xác thực rõ ràng.

Không nên chọn stateless chỉ vì muốn scale ngang. Session có shared store cũng có thể mở rộng; token stateless vẫn cần quản lý khóa, thu hồi và quyền truy cập.

## 8. Cấu hình session cookie trong Spring Boot

Với ứng dụng Servlet dùng Spring Boot, các thuộc tính phổ biến được đặt trong application.properties hoặc application.yml.

Ví dụ application.properties:

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.name=JSESSIONID
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Ý nghĩa:

- server.servlet.session.timeout đặt thời gian session không hoạt động.
- server.servlet.session.cookie.name đặt tên cookie session.
- http-only hạn chế JavaScript đọc cookie session.
- secure yêu cầu cookie chỉ gửi qua HTTPS.
- same-site=lax giúp giảm việc gửi cookie trong nhiều ngữ cảnh cross-site.

Khi chạy local bằng HTTP, cookie có Secure có thể không được gửi trong các request HTTP thông thường. Đây là điều cần tính đến khi kiểm thử. Môi trường production nên dùng HTTPS xuyên suốt, kể cả khi TLS được kết thúc ở reverse proxy; cấu hình proxy và forwarded headers phải chính xác để ứng dụng hiểu đúng scheme bên ngoài.

Tên property và khả năng cấu hình có thể thay đổi theo phiên bản Spring Boot. Hãy đối chiếu với metadata/documentation của phiên bản dự án đang dùng, đặc biệt khi làm việc với phiên bản cũ.

## 9. Tạo cookie tùy chỉnh bằng Spring MVC

Khi cần lưu tùy chọn không nhạy cảm như theme, có thể tạo cookie riêng. Ví dụ sau dùng Spring Boot 3.x, Java 17+ và Spring MVC.

~~~java
package com.example.web;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/preferences")
public class PreferenceController {

    @GetMapping("/theme")
    public Map<String, String> getTheme(
            @CookieValue(name = "theme", required = false) String theme) {
        return Map.of("theme", theme == null ? "light" : theme);
    }

    @PostMapping("/theme")
    public ResponseEntity<Void> saveTheme(@RequestParam String theme) {
        if (!theme.equals("light") && !theme.equals("dark")) {
            return ResponseEntity.badRequest().build();
        }

        ResponseCookie cookie = ResponseCookie.from("theme", theme)
                .path("/")
                .maxAge(Duration.ofDays(30))
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .build();
    }

    @DeleteMapping("/theme")
    public ResponseEntity<Void> clearTheme() {
        ResponseCookie cookie = ResponseCookie.from("theme", "")
                .path("/")
                .maxAge(Duration.ZERO)
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax")
                .build();

        return ResponseEntity.noContent()
                .header(HttpHeaders.SET_COOKIE, cookie.toString())
                .build();
    }
}
~~~

Các điểm cần hiểu:

- @CookieValue đọc giá trị cookie trong request.
- ResponseCookie xây dựng header Set-Cookie với các thuộc tính đã chọn.
- Max-Age=0 yêu cầu trình duyệt xóa cookie.
- Cookie muốn xóa phải khớp tên, Domain và Path với cookie đã tạo. Nếu cookie ban đầu được đặt với Domain hoặc Path khác, cần dùng lại đúng phạm vi khi xóa.
- Ví dụ bật Secure nên cần gọi qua HTTPS trong môi trường trình duyệt thực tế.
- Cookie theme chỉ lưu lựa chọn hiển thị, không được dùng làm bằng chứng xác thực hay phân quyền.

Nếu response cần nhiều cookie, gọi addHeader(HttpHeaders.SET_COOKIE, ...) cho từng cookie. Tránh dùng một header đã nối nhiều giá trị bằng dấu phẩy.

## 10. Lưu và đọc dữ liệu trong HttpSession

Spring MVC có thể nhận HttpSession làm tham số của controller. Ví dụ minh họa bộ đếm số mặt hàng trong giỏ:

~~~java
package com.example.web;

import java.util.Map;

import jakarta.servlet.http.HttpSession;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/cart")
public class CartController {

    @GetMapping
    public Map<String, Integer> getCart(HttpSession session) {
        Integer count = (Integer) session.getAttribute("itemCount");
        return Map.of("itemCount", count == null ? 0 : count);
    }

    @PostMapping("/items")
    public Map<String, Integer> addItem(HttpSession session) {
        Integer count = (Integer) session.getAttribute("itemCount");
        int updatedCount = (count == null ? 0 : count) + 1;
        session.setAttribute("itemCount", updatedCount);
        return Map.of("itemCount", updatedCount);
    }
}
~~~

Khi request đầu tiên gọi endpoint cần session, Servlet container tạo session nếu chưa có và gửi session ID về client. Những request tiếp theo mang cookie session ID để server khôi phục dữ liệu.

Ví dụ kiểm tra bằng curl:

~~~bash
curl -i -c cookies.txt http://localhost:8080/api/cart
curl -i -b cookies.txt -c cookies.txt -X POST http://localhost:8080/api/cart/items
curl -i -b cookies.txt http://localhost:8080/api/cart
~~~

Tùy chọn -c ghi cookie nhận được vào file; -b gửi cookie từ file trong request. Lần POST làm số mặt hàng tăng lên, request GET sau đó đọc lại giá trị đã lưu trong session. Khi dùng cookie Secure, hãy thử qua HTTPS thay vì HTTP.

Ví dụ chỉ minh họa cách giữ dữ liệu giữa các request. Giỏ hàng thực tế thường cần lưu dữ liệu nghiệp vụ trong database hoặc cart service để tránh mất dữ liệu khi session hết hạn, node bị thay thế hoặc người dùng đổi thiết bị.

## 11. Bảo mật cookie, session và request

### 11.1. CSRF

Trình duyệt tự động gửi cookie phù hợp khi truy cập một website. Vì vậy, nếu cookie đại diện cho đăng nhập, một trang độc hại có thể tìm cách khiến trình duyệt gửi request đến website thật kèm cookie của nạn nhân. Đây là nền tảng của Cross-Site Request Forgery (CSRF).

Các biện pháp cần kết hợp:

- Bật cơ chế CSRF protection phù hợp với ứng dụng, đặc biệt khi xác thực dựa trên cookie.
- Dùng SameSite phù hợp như một lớp phòng vệ bổ sung.
- Với thao tác thay đổi trạng thái, dùng method và kiểm tra request origin theo chính sách.
- Không coi CORS là cơ chế chống CSRF; CORS chủ yếu kiểm soát việc JavaScript đọc response cross-origin, không ngăn mọi request được gửi đi.
- Kiểm thử các luồng form, AJAX, đăng nhập và tích hợp bên thứ ba.

Spring Security có CSRF protection cho ứng dụng Servlet theo cấu hình mặc định phổ biến. Nếu ứng dụng tắt hoặc tùy chỉnh CSRF, phải xác định rõ loại client, cách gửi credential và biện pháp thay thế. Không nên tắt CSRF chỉ để xử lý lỗi 403 mà chưa hiểu nguyên nhân.

### 11.2. Session fixation và session hijacking

Session fixation xảy ra khi kẻ tấn công khiến người dùng sử dụng một session ID đã biết trước. Session hijacking xảy ra khi session ID hợp lệ bị đánh cắp và được sử dụng bởi người khác.

Giảm rủi ro bằng cách:

- Chỉ truyền session cookie qua HTTPS và bật Secure.
- Bật HttpOnly để hạn chế đọc cookie bằng JavaScript.
- Dùng SameSite phù hợp và bảo vệ CSRF.
- Tạo session ID đủ ngẫu nhiên, không tự sinh ID từ username, timestamp hoặc dữ liệu dễ đoán.
- Đổi session ID sau khi xác thực hoặc thay đổi mức quyền.
- Invalidate session khi đăng xuất và áp dụng timeout hợp lý.
- Không ghi session ID hoặc token đầy đủ vào log, URL hay thông báo lỗi.

### 11.3. XSS và dữ liệu trong cookie

HttpOnly giảm khả năng JavaScript đọc cookie nhưng không ngăn XSS thực thi hành động dưới danh nghĩa người dùng. Cần mã hóa output theo ngữ cảnh, tránh chèn HTML không an toàn, kiểm tra input và dùng CSP phù hợp.

Không lưu dữ liệu bí mật trong cookie chỉ vì cookie được đặt Secure hoặc HttpOnly. Secure bảo vệ đường truyền; HttpOnly giới hạn truy cập từ JavaScript. Hai thuộc tính này không làm cookie trở thành nơi lưu trữ bí mật được mã hóa.

### 11.4. Cookie và CSRF trong API

Nếu API nhận bearer token qua Authorization header do ứng dụng chủ động gắn vào, trình duyệt không tự động đính kèm header đó trong mọi điều hướng cross-site. Rủi ro CSRF thường thấp hơn so với credential được gửi tự động bằng cookie, nhưng XSS và rò rỉ token vẫn là mối đe dọa.

Nếu bearer token được đặt trong cookie, trình duyệt lại tự động gửi cookie theo chính sách của nó; cần bảo vệ CSRF như với cơ chế xác thực cookie khác. Không quyết định bật/tắt CSRF chỉ dựa trên việc token có phải JWT hay không.

## 12. Đăng xuất và xóa session

Đăng xuất cần vô hiệu hóa trạng thái xác thực phía server. Với Servlet session, có thể gọi invalidate trên session hiện tại:

~~~java
session.invalidate();
~~~

Trong ứng dụng dùng Spring Security, nên dùng logout flow của Spring Security để xóa SecurityContext, xử lý session và các cookie liên quan theo cấu hình. Nếu tự viết endpoint logout, phải bảo đảm không bỏ sót các bước dọn dẹp bảo mật.

Việc xóa cookie phía trình duyệt là thao tác riêng. Server gửi lại Set-Cookie với cùng tên và phạm vi Domain/Path, đặt Max-Age=0 hoặc Expires trong quá khứ. Nếu xóa không đúng Path hoặc Domain, cookie cũ có thể vẫn tồn tại.

Không đưa session ID vào query string để thực hiện URL rewriting nếu không có lý do tương thích đặc biệt. URL có thể bị lưu trong browser history, access log, analytics, proxy log hoặc Referer header, làm lộ mã định danh phiên.

## 13. Kiểm thử cookie và session

Một bộ kiểm thử nên bao gồm:

- **Cookie được phát hành**: response có Set-Cookie và chứa các thuộc tính mong muốn.
- **Cookie được đọc lại**: request tiếp theo gửi cookie và ứng dụng xử lý đúng giá trị.
- **Cookie bị xóa**: response xóa cookie với đúng tên và phạm vi.
- **Session được duy trì**: nhiều request có cùng session ID thấy cùng dữ liệu session.
- **Session hết hạn**: dữ liệu session không còn truy cập được sau timeout theo cấu hình.
- **Đăng xuất**: session bị invalidate và request sau không còn quyền dựa trên session cũ.
- **CSRF**: request thay đổi trạng thái thiếu token hoặc origin hợp lệ bị từ chối theo chính sách.
- **Triển khai nhiều node**: session hoạt động đúng khi request chuyển giữa các instance nếu kiến trúc yêu cầu.

Có thể dùng MockMvc để kiểm tra cookie và session trong integration test. Ví dụ:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CartControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void keepsCartCountInSession() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mockMvc.perform(post("/api/cart/items").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(1));

        mockMvc.perform(get("/api/cart").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.itemCount").value(1));
    }
}
~~~

Test cần các static import tương ứng từ Spring Test, MockMvc, JUnit và JSONPath. MockHttpSession mô phỏng session trong test; nó không thay thế kiểm thử trên Servlet container thật hoặc kiểm thử hành vi cookie của trình duyệt.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Đăng nhập xong request sau bị mất trạng thái | Cookie session không được lưu hoặc không được gửi lại | Kiểm tra Set-Cookie, Cookie, Domain, Path, Secure và SameSite |
| Cookie Secure không hoạt động khi chạy local | Request đang dùng HTTP | Kiểm thử HTTPS hoặc cấu hình profile local riêng |
| Xóa cookie nhưng trình duyệt vẫn gửi cookie cũ | Path hoặc Domain khi xóa không khớp cookie gốc | Gửi Set-Cookie xóa với đúng tên và phạm vi |
| Session mất khi request sang node khác | Session chỉ nằm trong bộ nhớ node trước | Dùng sticky session hoặc shared store như Spring Session |
| Người dùng vẫn còn đăng nhập sau khi đóng trình duyệt | Browser khôi phục session hoặc server session chưa hết hạn | Dùng timeout và chính sách logout/absolute timeout rõ ràng |
| Request POST bị 403 | CSRF token thiếu hoặc không hợp lệ | Kiểm tra cấu hình Spring Security và cách client gửi CSRF token |
| Cookie có HttpOnly nhưng vẫn có hành vi lạ khi XSS | Script độc hại vẫn có thể gửi request từ trang bị xâm nhập | Sửa lỗ hổng XSS; HttpOnly chỉ ngăn đọc cookie trực tiếp |
| Có nhiều cookie trùng tên | Cookie được tạo với các Path hoặc Domain khác nhau | Kiểm tra toàn bộ Set-Cookie và xóa đúng từng phạm vi |
| Session ID xuất hiện trong log hoặc URL | Ứng dụng ghi log credential hoặc dùng URL rewriting | Loại bỏ ID khỏi URL/log, thay đổi session ID nếu có nguy cơ lộ |
| JWT bị coi là dữ liệu bí mật | Payload chỉ được Base64URL encode và ký | Không đặt secret trong claims; mã hóa riêng nếu thực sự cần bảo mật nội dung |

## 15. Quy trình chọn cơ chế lưu trạng thái

Khi thiết kế một tính năng, có thể đi theo trình tự:

1. Xác định dữ liệu nào cần tồn tại giữa các request và thời gian cần giữ.
2. Nếu chỉ là tùy chọn nhỏ, không nhạy cảm, cân nhắc cookie.
3. Nếu cần thu hồi phiên và lưu trạng thái phía server, dùng session với cookie chứa ID.
4. Nếu API cần credential do client chủ động gửi, cân nhắc bearer token và chính sách hết hạn/thu hồi.
5. Nếu triển khai nhiều instance, chọn cách chia sẻ hoặc định tuyến session phù hợp.
6. Đánh giá CSRF, XSS, HTTPS, timeout, logout và quyền truy cập.
7. Viết kiểm thử cho cả request đầu tiên, request tiếp theo và tình huống hết hạn.

Không nên lưu dữ liệu nghiệp vụ quan trọng duy nhất trong cookie hoặc session tạm thời. Đơn hàng, thanh toán, quyền sở hữu và dữ liệu cần kiểm toán phải được lưu trong kho dữ liệu có độ bền phù hợp; cookie/session chỉ nên giữ thông tin tham chiếu hoặc trạng thái ngắn hạn.

## 16. Ghi nhớ

HTTP không tự duy trì trạng thái nghiệp vụ giữa các request. Cookie cho phép trình duyệt lưu một lượng nhỏ dữ liệu và tự động gửi lại khi phù hợp. Session lưu trạng thái ở phía server và thường dùng cookie chứa session ID để nối các request. Stateless authentication yêu cầu client gửi credential trong mỗi request và vẫn cần quản lý vòng đời token.

Khi dùng Spring Boot, hãy cấu hình cookie session với Secure, HttpOnly và SameSite phù hợp; đặt timeout có chủ đích; thay session ID sau xác thực; invalidate khi đăng xuất; và dùng shared session store khi cần nhiều instance. Việc chọn cookie, session hay token phải dựa trên nơi lưu dữ liệu, cách gửi credential, yêu cầu thu hồi và mô hình triển khai của ứng dụng.
