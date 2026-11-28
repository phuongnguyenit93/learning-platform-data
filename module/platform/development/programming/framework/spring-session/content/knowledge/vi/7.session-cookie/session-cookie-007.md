# Cookie tồn tại theo phiên trình duyệt và cookie có Max-Age

Spring Session thường nhận diện phiên của người dùng thông qua một cookie chứa session ID. Cookie này được gửi lại trong các request tiếp theo để `SessionRepositoryFilter` tìm dữ liệu phiên trong Redis, JDBC hoặc repository khác. Cách trình duyệt lưu cookie ảnh hưởng việc cookie còn được gửi sau khi đóng cửa sổ hoặc khởi động lại trình duyệt, nhưng không thay thế thời hạn hiệu lực của session ở phía máy chủ.

Hai dạng cookie thường gặp là **session cookie** (cookie không có `Max-Age` hoặc `Expires`) và **persistent cookie** (cookie có thời hạn, thường được thiết lập bằng `Max-Age`). Cần hiểu rõ sự khác biệt giữa vòng đời cookie ở trình duyệt và idle timeout/TTL của session trong repository để tránh cấu hình bảo mật sai.

## 1. Session cookie là gì?

Session cookie là cookie không khai báo thời điểm hết hạn `Expires` và cũng không khai báo thời lượng `Max-Age`. Theo mô hình cookie HTTP, user agent giữ cookie này trong phiên trình duyệt hiện tại và thường loại bỏ khi phiên trình duyệt kết thúc.

Ví dụ một response có thể gửi:

```http
Set-Cookie: SESSION=abc123; Path=/; HttpOnly; Secure; SameSite=Lax
```

Trong ví dụ này, cookie `SESSION` không có `Max-Age` hoặc `Expires`, nên nó là session cookie. Trình duyệt thường giữ cookie cho đến khi phiên trình duyệt kết thúc. Tuy nhiên, hành vi “kết thúc phiên trình duyệt” do trình duyệt định nghĩa. Một số trình duyệt có chức năng khôi phục phiên hoặc khôi phục tab có thể khôi phục cả session cookie sau khi mở lại. Vì vậy, không nên coi việc người dùng đóng cửa sổ trình duyệt là cơ chế bảo đảm xóa credential.

Session cookie phù hợp khi ứng dụng muốn trình duyệt không lưu cookie như một cookie bền vững qua nhiều phiên sử dụng. Nó không tự động làm session phía máy chủ hết hạn ngay khi trình duyệt đóng. Nếu cookie bị mất, dữ liệu session trong repository có thể vẫn còn cho đến khi idle timeout hoặc quy trình cleanup loại bỏ nó.

## 2. Persistent cookie và thuộc tính Max-Age

Persistent cookie là cookie có thời hạn lưu ở phía trình duyệt. Thuộc tính `Max-Age` quy định số giây cookie được phép tồn tại kể từ thời điểm user agent nhận cookie.

Ví dụ:

```http
Set-Cookie: SESSION=abc123; Max-Age=3600; Path=/; HttpOnly; Secure; SameSite=Lax
```

`Max-Age=3600` yêu cầu trình duyệt giữ cookie trong khoảng một giờ. Khi thời hạn này kết thúc, trình duyệt không nên gửi cookie trong các request tiếp theo. Cookie cũng có thể dùng thuộc tính `Expires` để chỉ ra ngày giờ hết hạn tuyệt đối. Nếu response có cả `Max-Age` và `Expires`, `Max-Age` được ưu tiên bởi các user agent hiện đại.

Các giá trị cần phân biệt:

| Cấu hình | Ý nghĩa ở phía trình duyệt |
|---|---|
| Không có `Max-Age` và `Expires` | Session cookie; được giữ theo phiên trình duyệt |
| `Max-Age` là số dương | Persistent cookie; hết hạn sau số giây đã chỉ định |
| `Max-Age=0` | Xóa cookie ngay lập tức |
| `Expires` là thời điểm trong quá khứ | Cookie đã hết hạn và được yêu cầu xóa |

Ví dụ `Max-Age=86400` tạo cookie có thời hạn một ngày. Thời hạn này chỉ điều khiển việc trình duyệt lưu và gửi cookie; nó không tự đặt TTL của bản ghi session trong Redis hoặc JDBC.

## 3. Phân biệt thời hạn cookie với thời hạn session phía máy chủ

Cookie chứa session ID là phương tiện để trình duyệt gửi định danh phiên. Dữ liệu phiên thực tế được lưu ở phía máy chủ. Vì vậy, có hai đồng hồ độc lập:

1. **Cookie lifetime:** thời gian trình duyệt giữ cookie và có thể gửi session ID.
2. **Session lifetime:** thời gian repository chấp nhận dữ liệu session, thường được kiểm soát bằng idle timeout và TTL/expiry của backend.

Ví dụ, cookie có `Max-Age=7 ngày` nhưng session trong Spring Session có idle timeout 30 phút. Nếu người dùng không gửi request trong 30 phút, repository có thể xem session đã hết hạn. Trình duyệt vẫn có thể giữ cookie trong bảy ngày, nhưng khi gửi ID cũ, server không tìm thấy session hợp lệ và ứng dụng sẽ yêu cầu tạo phiên mới hoặc xác thực lại.

Ngược lại, nếu cookie là session cookie nhưng server session có idle timeout bảy ngày, việc đóng trình duyệt thường làm mất cookie ở client, nhưng dữ liệu session có thể còn trên server cho đến khi hết hạn hoặc được dọn dẹp. Không nên dựa vào việc cookie biến mất để thu hồi dữ liệu session tức thời.

| Cookie ở trình duyệt | Session ở repository | Kết quả thường thấy |
|---|---|---|
| Hết hạn trước | Còn hợp lệ | Trình duyệt không gửi ID; người dùng có thể phải đăng nhập lại dù session server còn tồn tại |
| Còn hạn | Hết hạn | Trình duyệt gửi ID cũ nhưng repository không trả session hợp lệ |
| Còn hạn | Còn hợp lệ | Filter có thể nạp lại session bình thường |
| Bị xóa | Còn dữ liệu | Cookie không còn được gửi từ trình duyệt đó; dữ liệu server chờ timeout/cleanup |

Cookie `Max-Age` không phải một cơ chế bảo mật thay thế idle timeout hoặc absolute timeout. Server phải kiểm tra session và chính sách xác thực trên mỗi request. Nếu cần giới hạn tổng thời gian đăng nhập, ứng dụng cần absolute timeout riêng.

## 4. Cấu hình cookie trong Spring Session

Spring Session dùng `HttpSessionIdResolver` để đọc và ghi session ID. Với cookie, serializer thường dùng là `DefaultCookieSerializer`. Có thể cung cấp bean `CookieSerializer` để tùy chỉnh tên cookie, đường dẫn, thuộc tính bảo mật và thời hạn.

Ví dụ cấu hình cookie session không có `Max-Age`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        // Không đặt cookieMaxAge: cookie là session cookie.
        return serializer;
    }
}
```

Ví dụ trên bật `Secure`, vì vậy trình duyệt chỉ gửi cookie qua HTTPS. Trong production, đây thường là lựa chọn phù hợp. Nếu chạy local HTTP, hãy dùng cấu hình riêng cho môi trường phát triển thay vì hạ cấu hình bảo mật của production. Khi ứng dụng chạy sau reverse proxy, cần cấu hình forwarded headers và proxy tin cậy đúng cách để ứng dụng nhận biết request HTTPS.

Để tạo persistent cookie một giờ, cấu hình `cookieMaxAge` theo giây:

```java
@Bean
CookieSerializer persistentCookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    serializer.setCookieMaxAge(60 * 60); // 1 giờ, đơn vị giây
    return serializer;
}
```

Trong một ứng dụng, chỉ khai báo một bean serializer phù hợp. Hai ví dụ trên là hai lựa chọn cấu hình thay thế nhau, không phải hai bean cần đăng ký đồng thời. `DefaultCookieSerializer` cũng hỗ trợ cấu hình domain hoặc domain pattern khi cần chia sẻ cookie giữa các subdomain. Chỉ đặt domain khi kiến trúc thực sự cần; cookie host-only thường giới hạn phạm vi gửi cookie tốt hơn.

Nếu ứng dụng dùng Spring Boot, hãy kiểm tra phiên bản và cơ chế auto-configuration của Spring Session. Thuộc tính cookie của Servlet container không nhất thiết điều khiển cookie do Spring Session tự ghi; khi dùng `DefaultCookieSerializer`, cấu hình serializer là nơi trực tiếp quyết định thuộc tính cookie.

## 5. Các thuộc tính cookie quan trọng khác

Thời hạn chỉ là một phần của cấu hình cookie. Những thuộc tính sau cũng ảnh hưởng bảo mật và phạm vi gửi cookie:

| Thuộc tính | Vai trò | Khuyến nghị chung |
|---|---|---|
| `HttpOnly` | Ngăn JavaScript phía trình duyệt đọc cookie qua API như `document.cookie` | Bật cho cookie session để giảm khả năng đánh cắp cookie qua XSS; không ngăn mọi tác động của XSS |
| `Secure` | Chỉ gửi cookie qua kết nối HTTPS | Bật trong production dùng HTTPS |
| `SameSite` | Hạn chế cookie được gửi trong request cross-site | Chọn `Lax`, `Strict` hoặc `None` theo luồng đăng nhập và tích hợp; `None` cần `Secure` trên trình duyệt hiện đại |
| `Path` | Giới hạn đường dẫn request gửi cookie | Chọn phạm vi nhỏ nhất vẫn đáp ứng ứng dụng; thường là `/` khi cookie dùng toàn ứng dụng |
| `Domain` | Xác định host/domain được phép nhận cookie | Ưu tiên host-only; chỉ mở rộng domain khi cần chia sẻ giữa subdomain |
| `Max-Age` | Thời gian cookie tồn tại ở client | Chọn theo chính sách lưu cookie; không dùng thay session timeout phía server |

`SameSite` có thể ảnh hưởng luồng đăng nhập qua nhà cung cấp danh tính bên ngoài, callback cross-site hoặc ứng dụng nhúng. Hãy kiểm thử luồng xác thực thực tế trước khi chọn `Strict`. Nếu bắt buộc cookie được gửi trong ngữ cảnh cross-site, `SameSite=None; Secure` có thể cần thiết, đồng thời phải có biện pháp chống CSRF phù hợp.

## 6. Đăng xuất và xóa cookie

Đăng xuất cần kết thúc session ở phía server và yêu cầu trình duyệt xóa cookie. Chỉ xóa cookie ở trình duyệt mà không xóa session trong repository có thể để lại session còn hiệu lực nếu session ID đã bị sao chép ở nơi khác. Ngược lại, chỉ xóa session trong repository mà không hết hạn cookie có thể khiến trình duyệt tiếp tục gửi ID cũ trong các request tiếp theo.

Với Servlet API, có thể kết thúc phiên hiện tại bằng:

```java
HttpSession session = request.getSession(false);
if (session != null) {
    session.invalidate();
}
```

Khi đi qua `SessionRepositoryFilter`, `invalidate()` yêu cầu Spring Session xóa session thông qua repository. Resolver sẽ xử lý việc xóa session ID khỏi cookie/header theo cơ chế của nó. Với Spring Security, nên dùng logout flow chuẩn để dọn `SecurityContext`, session và cookie theo cấu hình bảo mật.

Nếu tự gửi header xóa cookie, thuộc tính `Path` và `Domain` phải khớp với cookie đã tạo. Ví dụ cookie được tạo với `Path=/app` thì một cookie xóa có `Path=/` có thể không xóa đúng cookie cũ. Tương tự, cookie host-only và cookie có `Domain` là hai phạm vi khác nhau.

Ví dụ HTTP để xóa cookie:

```http
Set-Cookie: SESSION=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax
```

Việc hết hạn cookie không thay thế việc invalidate session ở repository. Hãy để Spring Session/Spring Security thực hiện cả hai bước theo cùng cấu hình cookie.

## 7. Cookie persistent có đồng nghĩa với “Remember Me” không?

Không. Persistent session cookie chỉ khiến trình duyệt lưu session ID lâu hơn. Nếu session server hết hạn sau 30 phút không hoạt động, cookie tồn tại bảy ngày cũng không làm session sống lại. Ngược lại, tính năng “Remember Me” thường dùng một credential riêng để khôi phục xác thực hoặc tạo session mới sau khi session hiện tại hết hạn.

Vì vậy, cần phân biệt:

- **Persistent session cookie:** lưu session ID ở trình duyệt qua nhiều phiên trình duyệt cho đến thời hạn cookie.
- **Remember-me credential:** credential riêng có thể cho phép tái xác thực hoặc khôi phục đăng nhập theo chính sách riêng.
- **Idle timeout:** giới hạn thời gian session không hoạt động ở phía server.
- **Absolute timeout:** giới hạn tuổi tối đa của phiên đăng nhập, không được kéo dài chỉ vì có request mới.

Nếu ứng dụng triển khai remember-me, hãy đặt thời hạn, khả năng thu hồi, vòng đời token và cơ chế bảo vệ riêng. Không dùng `Max-Age` của cookie session để mô phỏng một hệ thống remember-me an toàn.

## 8. Cookie và kiến trúc nhiều instance

Trong môi trường có load balancer, cookie session ID thường được gửi đến bất kỳ instance nào xử lý request. Vì vậy, các instance phải thống nhất:

- Tên cookie, path, domain, SameSite và cách resolver đọc/ghi ID.
- Cấu hình serializer và cách mã hóa session ID nếu có.
- Repository dùng chung, Redis namespace hoặc JDBC schema.
- Chính sách idle timeout và absolute timeout.
- Cấu hình HTTPS/reverse proxy để thuộc tính `Secure` được phát hành đúng.

Nếu instance A phát hành cookie tên `SESSION` nhưng instance B lại tìm cookie tên khác, request chuyển sang B có thể bị xem như không có session. Nếu domain hoặc path không phù hợp, trình duyệt có thể không gửi cookie tới một số URL. Nếu các instance dùng repository khác nhau, cùng một session ID có thể không được tìm thấy.

Sticky session ở load balancer không thay thế repository dùng chung. Nó chỉ cố gắng đưa request về cùng instance; khi instance khởi động lại hoặc load balancer chuyển hướng, session cục bộ vẫn có thể mất. Spring Session cùng Redis/JDBC giúp các instance truy cập dữ liệu session chung.

## 9. Kiểm thử session cookie và Max-Age

Kiểm thử cần xem cả header `Set-Cookie`, hành vi client và trạng thái repository.

1. **Session cookie:** phát hành session ID và xác nhận header không có `Max-Age` hoặc `Expires`.
2. **Persistent cookie:** cấu hình `cookieMaxAge` dương và xác nhận `Set-Cookie` chứa `Max-Age` tương ứng.
3. **Xóa cookie:** logout và xác nhận response phát hành cookie hết hạn với đúng path/domain.
4. **Server timeout trước cookie:** đặt cookie Max-Age dài nhưng idle timeout ngắn; xác nhận server từ chối session sau idle timeout dù client còn cookie.
5. **Cookie hết hạn trước session:** đặt Max-Age ngắn hơn server timeout; xác nhận trình duyệt ngừng gửi cookie, trong khi dữ liệu session có thể còn trong repository cho đến cleanup.
6. **Bảo mật cookie:** xác nhận `HttpOnly`, `Secure`, `SameSite`, `Path` và `Domain` đúng theo môi trường.
7. **Nhiều instance:** nhận cookie từ instance A và gửi request tới instance B; xác nhận resolver và repository nhận diện cùng session.
8. **Trình duyệt:** kiểm tra cookie trong developer tools và thử luồng khởi động lại/khôi phục phiên trên các trình duyệt mục tiêu nếu hành vi đó quan trọng với sản phẩm.

Trong kiểm thử backend, có thể dùng `MockMvc` để kiểm tra header `Set-Cookie`, nhưng kiểm thử trình duyệt thật hoặc công cụ HTTP client có cookie jar mới thể hiện chính xác cách client lưu và gửi cookie. Không dựa vào `Thread.sleep()` dài để kiểm tra thời hạn; có thể kiểm tra header `Max-Age` trực tiếp và dùng clock/test repository để kiểm tra session expiry.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Cookie biến mất khi đóng trình duyệt | Cookie không có `Max-Age`/`Expires` và trình duyệt kết thúc phiên | Xác nhận đây có phải session cookie theo thiết kế hay không; xem xét hành vi khôi phục phiên của browser |
| Cookie còn nhưng người dùng bị đăng xuất | Session phía server đã hết idle timeout hoặc bị invalidate | Kiểm tra repository, timeout hiệu lực và log sự kiện session |
| Người dùng vẫn đăng nhập sau khi đóng rồi mở browser | Browser khôi phục session cookie hoặc cookie có Max-Age dài | Không dựa vào đóng browser để thu hồi; áp dụng timeout server và logout đúng cách |
| Cookie không được gửi tới subdomain | Domain/host-only hoặc Path không phù hợp | Kiểm tra thuộc tính cookie và host/path của request |
| Cookie Secure không xuất hiện trên HTTP local | Trình duyệt không gửi cookie Secure qua HTTP | Dùng HTTPS trong môi trường kiểm thử tương ứng hoặc cấu hình phát triển riêng |
| Logout xong cookie cũ vẫn còn | Cookie xóa sai Path/Domain hoặc logout chưa đi qua resolver | Kiểm tra header `Set-Cookie` khi logout và dùng cùng phạm vi cookie |
| Cookie persistent nhưng session mất sớm | Max-Age dài hơn TTL/idle timeout server | Điều chỉnh hai thời hạn theo chính sách và giải thích rõ cho người dùng |
| Session tồn tại server nhưng browser không còn ID | Cookie đã hết hạn hoặc bị xóa | Để repository cleanup theo TTL; không coi dữ liệu còn lại là phiên client có thể sử dụng |

Khi điều tra, có thể ghi log tên instance, mã tương quan request, tên cookie và kết quả tìm session. Không ghi giá trị session ID hoặc toàn bộ header Cookie. Nếu cần đối chiếu phiên, dùng fingerprint đã băm và giới hạn quyền truy cập log.

## 11. Nguyên tắc cấu hình

- Session cookie không khai báo `Max-Age` hoặc `Expires`; persistent cookie có thời hạn lưu ở trình duyệt.
- `Max-Age` tính bằng giây; `Max-Age=0` yêu cầu xóa cookie.
- Cookie lifetime và server session lifetime là hai cơ chế độc lập.
- Dùng `DefaultCookieSerializer` để cấu hình cookie Spring Session; xác nhận đúng bean serializer được ứng dụng sử dụng.
- Bật `HttpOnly` và `Secure` trong production HTTPS; chọn `SameSite`, `Path`, `Domain` theo luồng ứng dụng.
- Logout phải invalidate session phía server và hết hạn cookie theo đúng path/domain.
- Persistent session cookie không phải tính năng Remember Me và không thay thế idle/absolute timeout.
- Đồng bộ cấu hình cookie và repository giữa các instance; kiểm thử header thực tế và luồng request qua nhiều node.
