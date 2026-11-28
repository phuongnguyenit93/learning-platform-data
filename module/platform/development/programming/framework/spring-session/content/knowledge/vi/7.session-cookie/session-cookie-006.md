# SameSite, yêu cầu khác site và yêu cầu dùng SameSite=None

Cookie session thường mang session ID để trình duyệt gửi lại trong các request tiếp theo. Khi ứng dụng được mở từ một website khác, được nhúng trong iframe hoặc gọi API qua một domain khác, trình duyệt có thể không gửi cookie session dù cookie vẫn còn hạn. Thuộc tính `SameSite` điều khiển việc cookie có được gửi trong ngữ cảnh same-site hay cross-site, qua đó ảnh hưởng trực tiếp đến đăng nhập, SSO, tích hợp iframe và các request API.

Spring Session cho phép cấu hình thuộc tính này thông qua `CookieSerializer`. Bài học này giải thích cách phân biệt site và origin, ý nghĩa của `Strict`, `Lax` và `None`, điều kiện bảo mật của `SameSite=None`, cách cấu hình trong Spring Session và cách kiểm tra trên trình duyệt. Nội dung cũng làm rõ quan hệ giữa SameSite, CORS và CSRF để tránh dùng `None` rộng hơn mức cần thiết.

## 1. Site và origin là hai khái niệm khác nhau

Để hiểu SameSite, trước tiên cần phân biệt *site* với *origin*.

- **Origin** gồm scheme, hostname và port. Ví dụ `https://app.example.com:8443` và `https://api.example.com` là hai origin khác nhau vì hostname và port khác nhau.
- **Site** trong cách trình duyệt đánh giá SameSite thường dựa trên scheme và registrable domain (eTLD+1), không tính port. Vì vậy `https://app.example.com` và `https://api.example.com` thường là same-site, nhưng vẫn là cross-origin.

Ví dụ:

| URL thứ nhất | URL thứ hai | Quan hệ site | Quan hệ origin |
| --- | --- | --- | --- |
| `https://app.example.com` | `https://api.example.com` | Same-site | Cross-origin |
| `https://app.example.com` | `https://app.example.com:8443` | Same-site | Cross-origin do port khác |
| `https://shop.example.com` | `https://other-company.net` | Cross-site | Cross-origin |
| `https://example.com` | `http://example.com` | Cross-site theo schemeful same-site | Cross-origin |

Trình duyệt hiện đại áp dụng khái niệm schemeful same-site: khác scheme HTTP/HTTPS có thể làm hai URL trở thành cross-site dù hostname thuộc cùng domain đăng ký. Không nên chỉ nhìn phần domain để quyết định cookie sẽ được gửi.

Một điểm dễ nhầm: request đến API ở subdomain khác có thể là cross-origin nhưng vẫn same-site. SameSite không thay thế chính sách CORS. CORS quyết định JavaScript ở origin nào được phép đọc response; SameSite quyết định cookie có được gửi theo ngữ cảnh site hay không.

## 2. Ba giá trị SameSite

Thuộc tính `SameSite` thường có ba giá trị chính:

| Giá trị | Cách trình duyệt gửi cookie | Trường hợp thường dùng |
| --- | --- | --- |
| `Strict` | Chỉ gửi trong ngữ cảnh same-site; cookie thường không có trong request đầu tiên được khởi tạo từ website khác | Ứng dụng ưu tiên hạn chế tối đa việc gửi cookie qua điều hướng cross-site |
| `Lax` | Gửi trong same-site và thường cho phép điều hướng top-level từ site khác bằng phương thức an toàn, phổ biến là GET; không gửi trong phần lớn request cross-site dạng subresource, iframe hoặc POST | Lựa chọn mặc định phù hợp với nhiều ứng dụng web truyền thống |
| `None` | Cho phép cookie được gửi trong ngữ cảnh cross-site nếu các điều kiện cookie khác được đáp ứng | Tích hợp iframe, request cross-site hoặc callback cần cookie trong POST |

### 2.1. `SameSite=Strict`

`Strict` hạn chế cookie được gửi khi người dùng đi từ một website khác vào ứng dụng. Ví dụ, người dùng đang ở `news.example.net`, nhấp liên kết đến `https://bank.example.com`; request điều hướng đầu tiên có thể không mang cookie session `Strict`. Sau khi người dùng đã ở trên site ngân hàng, các request same-site tiếp theo có thể gửi cookie bình thường.

Giá trị này giảm bề mặt tấn công CSRF qua điều hướng cross-site, nhưng có thể làm trải nghiệm đăng nhập hoặc điều hướng từ email, liên kết ngoài và dịch vụ định danh bị gián đoạn. Cần kiểm thử luồng truy cập thực tế trước khi chọn.

### 2.2. `SameSite=Lax`

`Lax` là lựa chọn cân bằng thường phù hợp cho cookie session của ứng dụng web. Cookie được gửi trong request same-site và trong một số điều hướng top-level từ site khác bằng phương thức an toàn. Một liên kết GET từ website ngoài đến trang ứng dụng thường vẫn có thể mang cookie.

Ngược lại, cookie `Lax` thường không được gửi trong iframe cross-site, ảnh/script nhúng từ site khác hoặc request POST cross-site. Vì vậy một luồng đăng nhập liên kết ngoài dùng callback POST có thể thất bại nếu cần cookie session cũ.

Khi không khai báo `SameSite`, các trình duyệt hiện đại thường áp dụng chính sách mặc định tương tự `Lax`. Hành vi mặc định và một số ngoại lệ tương thích có thể khác giữa phiên bản trình duyệt; không nên dựa vào việc bỏ thuộc tính để có hành vi cross-site.

### 2.3. `SameSite=None`

`None` cho phép trình duyệt gửi cookie trong các ngữ cảnh cross-site, ví dụ request từ một website khác, iframe cross-site hoặc một số luồng xác thực liên miền. Cookie phải có thuộc tính `Secure` trong các trình duyệt hiện đại:

```http
Set-Cookie: SESSION=...; Path=/; HttpOnly; Secure; SameSite=None
```

`Secure` yêu cầu trình duyệt chỉ gửi cookie qua kết nối HTTPS. Nếu phát hành `SameSite=None` mà thiếu `Secure`, nhiều trình duyệt sẽ từ chối cookie hoặc không lưu cookie đó. Vì vậy, cấu hình `None` cần được triển khai cùng HTTPS đầu cuối hoặc cấu hình reverse proxy đáng tin cậy để ứng dụng nhận biết đúng request HTTPS.

`SameSite=None` chỉ cho phép cookie tham gia request cross-site theo quy tắc SameSite. Nó không bảo đảm cookie chắc chắn được gửi: chính sách chặn third-party cookies, chế độ riêng tư, cài đặt người dùng, tiện ích bảo mật và chính sách của trình duyệt vẫn có thể chặn cookie.

## 3. Khi nào thực sự cần `SameSite=None`?

Không phải cứ frontend và backend có hostname khác nhau là phải dùng `None`. Hãy xác định quan hệ site, loại request và nơi cookie được sử dụng.

| Tình huống | SameSite thường phù hợp | Giải thích |
| --- | --- | --- |
| Trang và API là cùng site, chỉ khác subdomain | `Lax` thường đủ | Cross-origin nhưng vẫn same-site; cần xử lý CORS/credentials riêng nếu JavaScript gọi API |
| Người dùng nhấp liên kết GET từ website ngoài vào ứng dụng | `Lax` thường đủ | Điều hướng top-level bằng phương thức an toàn thường được cho phép |
| Ứng dụng được nhúng trong iframe trên một site khác và cần cookie session | Có thể cần `None; Secure` | Request trong iframe là ngữ cảnh cross-site |
| JavaScript gọi API thuộc site khác và cần cookie của API | Có thể cần `None; Secure` | Cookie cross-site có thể cần `None`, đồng thời Fetch phải gửi credentials và server phải cho phép CORS có credentials |
| Nhà cung cấp định danh POST callback về ứng dụng (`form_post`) và callback cần session cookie | Có thể cần `None; Secure` | POST cross-site thường không gửi cookie `Lax` |
| Nhà cung cấp định danh điều hướng top-level bằng GET về callback | `Lax` thường hoạt động | Điều hướng top-level an toàn thường được Lax cho phép; phải kiểm thử đúng response mode |

Ví dụ, frontend tại `https://portal.customer.com` nhúng ứng dụng quản trị ở `https://admin.vendor.net` trong iframe. Cookie của `admin.vendor.net` được sử dụng trong ngữ cảnh cross-site. Nếu cookie có `SameSite=Lax`, trình duyệt thường không gửi nó trong các request của iframe; ứng dụng có thể liên tục tạo session mới hoặc yêu cầu đăng nhập lặp lại. `SameSite=None; Secure` có thể cần thiết, nhưng vẫn phải kiểm tra chính sách third-party cookies của trình duyệt.

Trong OAuth/OIDC, lựa chọn phụ thuộc vào cách nhà cung cấp trả callback. Redirect top-level GET thường tương thích với `Lax`. Luồng `response_mode=form_post` gửi POST cross-site có thể cần cookie `None`. Dù dùng cách nào, vẫn phải xác minh `state`, `nonce`, PKCE và các biện pháp bảo vệ callback phù hợp; SameSite không thay thế các kiểm tra của giao thức xác thực.

## 4. Cấu hình SameSite trong Spring Session

Spring Session dùng `CookieSerializer` để tạo và đọc cookie session. Với `DefaultCookieSerializer`, có thể đặt tên cookie, path, `HttpOnly`, `Secure` và `SameSite` bằng Java configuration.

Ví dụ cấu hình cookie cho một luồng cần gửi cookie cross-site:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("None");
        return serializer;
    }
}
```

Với cấu hình này, response tạo cookie session sẽ có các thuộc tính tương ứng, trong đó `SameSite=None` đi cùng `Secure`. Chỉ dùng `None` nếu luồng cross-site thực sự cần cookie; nếu không, giữ `Lax` thường an toàn và đơn giản hơn.

Nếu ứng dụng dùng Spring Session, cookie được phát hành bởi `CookieSerializer`, nên cần kiểm tra cấu hình serializer thực tế. Cấu hình cookie của servlet container như `server.servlet.session.cookie.same-site` có thể áp dụng cho session mặc định của container; không nên giả định nó tự động thay thế bean `CookieSerializer` của Spring Session ở mọi phiên bản Spring Boot. Sau khi cấu hình, hãy xem header `Set-Cookie` thực tế để xác nhận.

### 4.1. Giữ cookie an toàn khi dùng `None`

Khi dùng `SameSite=None`, nên đồng thời:

- Bật `Secure` để cookie chỉ đi qua HTTPS.
- Giữ `HttpOnly` nếu JavaScript không cần đọc cookie; session ID không nên truy cập trực tiếp từ script.
- Chọn `Path` và `Domain` hẹp nhất đáp ứng kiến trúc ứng dụng.
- Không ghi session ID hoặc giá trị cookie vào log.
- Xác minh reverse proxy gửi forwarded headers đáng tin cậy và ứng dụng nhận biết request HTTPS đúng cách.
- Giữ CSRF protection cho các thao tác thay đổi dữ liệu.

Không đặt `Domain=.example.com` chỉ để tiện chia sẻ cookie giữa mọi subdomain nếu không cần. Cookie domain rộng làm tăng phạm vi host có thể ảnh hưởng đến cookie. Với ứng dụng chỉ cần cookie cho `api.example.com`, host-only cookie thường là lựa chọn hẹp hơn.

## 5. SameSite không phải là CORS

Một request có thể cross-origin nhưng same-site. Ví dụ trang `https://app.example.com` gọi API `https://api.example.com`. Đây là cross-origin nhưng same-site. Cookie `Lax` có thể được phép theo quy tắc SameSite, nhưng Fetch API mặc định chỉ gửi credentials cho same-origin request. Muốn gửi cookie trong fetch cross-origin, client thường cần `credentials: "include"`:

```javascript
fetch("https://api.example.com/account", {
  method: "GET",
  credentials: "include"
});
```

Server cần trả CORS headers tương ứng, ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Khi dùng credentials, `Access-Control-Allow-Origin` phải chỉ rõ origin được phép; không thể dùng wildcard `*` cùng `Access-Control-Allow-Credentials: true`. Cần cấu hình cả preflight OPTIONS nếu request có header hoặc method cần preflight.

Hai cơ chế này độc lập:

- `credentials: "include"` và CORS cho phép request cross-origin sử dụng credentials và cho JavaScript đọc response theo chính sách CORS.
- `SameSite` vẫn quyết định cookie có được gửi trong ngữ cảnh site hiện tại hay không.

Do đó, thêm CORS headers không làm cookie `Lax` được gửi trong iframe cross-site. Tương tự, đổi sang `SameSite=None` không tự giải quyết lỗi CORS.

## 6. SameSite không thay thế CSRF protection

SameSite là một lớp giảm rủi ro CSRF, nhưng không nên dùng nó làm biện pháp duy nhất. Một số lý do:

1. `Lax` vẫn cho phép cookie trong điều hướng top-level bằng phương thức an toàn. Endpoint GET mà thay đổi dữ liệu có thể bị kích hoạt qua liên kết ngoài.
2. Các subdomain thuộc cùng site có thể được xem là same-site. Nếu một subdomain bị chiếm quyền hoặc có ứng dụng không đáng tin cậy, cookie `Lax`/`Strict` không nhất thiết ngăn request từ subdomain đó.
3. Một số luồng cần `SameSite=None`, khiến cookie được gửi trong ngữ cảnh cross-site.
4. Hành vi trình duyệt, embedded context và chính sách third-party cookie có thể thay đổi.

Với ứng dụng dùng cookie session để xác thực, cần giữ CSRF protection của Spring Security cho các request thay đổi trạng thái. Không dùng GET để thực hiện chuyển tiền, xóa dữ liệu, cập nhật quyền hoặc thao tác nhạy cảm. Dùng CSRF token trong form hoặc header cho request unsafe, và cân nhắc kiểm tra `Origin`/`Referer` theo kiến trúc ứng dụng.

Ví dụ cấu hình Spring Security nên giữ CSRF protection mặc định hoặc cấu hình repository/handler token phù hợp với kiểu frontend:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );
    // Giữ CSRF protection; cấu hình token phù hợp nếu frontend dùng JavaScript.
    return http.build();
}
```

Không thêm `csrf(csrf -> csrf.disable())` chỉ để khắc phục lỗi cookie cross-site. Nếu dùng `SameSite=None`, hãy đánh giá lại CSRF threat model và xác minh mọi endpoint thay đổi trạng thái có cơ chế chống giả mạo request phù hợp.

## 7. Third-party cookie restrictions vẫn có thể chặn `SameSite=None`

Trình duyệt có thể chặn third-party cookies theo chính sách quyền riêng tư, cài đặt người dùng hoặc chế độ duyệt riêng tư. Khi đó, cookie có `SameSite=None; Secure` vẫn có thể không được gửi trong iframe hoặc request bên thứ ba. SameSite là thuộc tính cookie; nó không thể ghi đè chính sách chặn cookie của trình duyệt.

Khi ứng dụng nhúng bị mất session dù cookie đã đặt `None`, kiểm tra:

- DevTools có báo cookie bị chặn do third-party cookie policy không?
- Cookie có `Secure` và được phát qua HTTPS không?
- Domain, path, thời gian hết hạn và tên cookie có đúng không?
- Request có thực sự gửi cookie trong header hay không?
- Trình duyệt có đang chặn cookie bên thứ ba hoặc yêu cầu quyền truy cập storage không?

Nếu sản phẩm phụ thuộc vào trải nghiệm nhúng, cân nhắc kiến trúc không phụ thuộc third-party cookie, chẳng hạn mở luồng đăng nhập ở top-level navigation, dùng backend-for-frontend cùng site hoặc thiết kế cơ chế cấp quyền/storage phù hợp với nền tảng. Cookie phân vùng (`Partitioned`, CHIPS) có thể phù hợp với một số use case nhúng, nhưng cần kiểm tra hỗ trợ trình duyệt, cấu hình cookie và khả năng của framework trước khi áp dụng; nó không phải thay thế phổ quát cho cookie cross-site.

## 8. Kiểm tra SameSite trong trình duyệt

`curl` hữu ích để xem header `Set-Cookie`, nhưng không mô phỏng đầy đủ chính sách SameSite và third-party cookie của trình duyệt. Cần kiểm thử trong browser thật.

Quy trình kiểm tra:

1. Mở DevTools, vào Network và thực hiện luồng tạo session.
2. Chọn response tạo cookie, kiểm tra header `Set-Cookie` có đúng `SameSite`, `Secure`, `HttpOnly`, `Path` và `Domain` hay không.
3. Mở Application/Storage, xem cookie có được lưu hay bị trình duyệt từ chối. Không sao chép giá trị cookie vào báo cáo.
4. Thực hiện request cross-site hoặc mở iframe cần kiểm thử; chọn request trong Network và xem cookie có được gửi hay không.
5. Nếu cookie bị chặn, xem lý do chi tiết trong DevTools, đặc biệt thông báo thiếu `Secure`, SameSite không phù hợp hoặc third-party cookie bị chặn.
6. Lặp lại với `Strict`, `Lax` và `None; Secure` trên các trình duyệt mục tiêu và các luồng điều hướng/POST/iframe thực tế.

Nên tạo ma trận kiểm thử:

| Ngữ cảnh | Kết quả cần xác nhận |
| --- | --- |
| Request same-site | Cookie được gửi khi còn hạn và path/domain phù hợp |
| Điều hướng top-level GET từ site khác | Cookie `Lax` được gửi theo chính sách trình duyệt |
| POST cross-site | Cookie `Lax` không được giả định sẽ có; xác minh callback dùng `None` nếu thật sự cần |
| Iframe cross-site | Cookie `None; Secure` được thử, đồng thời kiểm tra third-party cookie restrictions |
| Fetch cross-origin | Client dùng `credentials: "include"`, CORS cho phép credentials và SameSite không chặn cookie |
| Logout | Server hủy session và response xóa cookie với đúng tên, domain, path |

Khi kiểm tra logout, nhớ rằng xóa cookie ở trình duyệt và invalidate session ở server là hai thao tác khác nhau. Cookie bị xóa nhưng session chưa bị invalidate có thể vẫn tồn tại cho đến TTL; session bị invalidate nhưng cookie còn trong trình duyệt thì request tiếp theo vẫn gửi ID cũ nhưng server phải từ chối phiên đó.

## 9. Những lỗi thường gặp

- **Đổi `SameSite=None` nhưng quên `Secure`:** trình duyệt hiện đại có thể từ chối cookie. Bật HTTPS và cấu hình secure cookie.
- **Nghĩ cross-origin đồng nghĩa cross-site:** hai subdomain khác nhau thường vẫn same-site; kiểm tra scheme và registrable domain.
- **Nghĩ `None` bảo đảm cookie luôn được gửi:** third-party cookie restrictions vẫn có thể chặn cookie.
- **Chỉ cấu hình CORS:** CORS không ghi đè quy tắc SameSite và không tự gửi credentials từ Fetch API.
- **Tắt CSRF để xử lý request cross-site:** điều này mở rộng rủi ro giả mạo request; hãy cấu hình token và luồng xác thực đúng.
- **Dùng `Strict` mà không thử liên kết ngoài/SSO:** request điều hướng đầu tiên có thể không mang cookie.
- **Cho rằng Spring Session luôn dùng cookie container:** kiểm tra `CookieSerializer` runtime và header `Set-Cookie` thực tế.
- **Chỉ kiểm tra bằng curl:** curl không áp dụng đầy đủ quy tắc cookie như trình duyệt; dùng DevTools và browser mục tiêu.

## 10. Checklist chọn và triển khai SameSite

Trước khi phát hành, xác nhận:

- [ ] Đã xác định frontend/API là same-site hay cross-site theo schemeful site.
- [ ] Đã phân biệt cross-origin với cross-site và cấu hình CORS độc lập.
- [ ] Đã chọn `Strict`, `Lax` hoặc `None` dựa trên request thực tế.
- [ ] Nếu dùng `None`, cookie có `Secure` và ứng dụng chạy HTTPS.
- [ ] `HttpOnly`, domain và path được cấu hình theo nguyên tắc tối thiểu.
- [ ] Các luồng iframe, OAuth callback GET/POST và fetch credentials đã được kiểm thử.
- [ ] CSRF protection vẫn được giữ cho các thao tác thay đổi trạng thái.
- [ ] Đã kiểm tra chính sách third-party cookies trên các trình duyệt mục tiêu.
- [ ] Đã xác minh header `Set-Cookie` và request `Cookie` bằng DevTools.
- [ ] Logout invalidate session ở server và xóa cookie đúng thuộc tính.

## 11. Tự kiểm tra kiến thức

Bạn đã nắm được bài học nếu có thể trả lời:

- Site khác origin ở những điểm nào? Vì sao hai subdomain có thể cross-origin nhưng same-site?
- `Strict`, `Lax` và `None` xử lý điều hướng top-level, POST cross-site và iframe ra sao?
- Vì sao `SameSite=None` phải đi cùng `Secure` trên trình duyệt hiện đại?
- Vì sao `None` vẫn có thể không gửi cookie khi trình duyệt chặn third-party cookies?
- Khi nào một ứng dụng Spring Session cần cấu hình `DefaultCookieSerializer`?
- CORS, Fetch credentials và SameSite kiểm soát những phần khác nhau nào?
- Vì sao SameSite chỉ là một lớp phòng vệ CSRF và không thay thế CSRF token?

Chọn SameSite đúng bắt đầu từ việc hiểu request đến từ site nào và cookie được dùng trong ngữ cảnh nào. `Lax` thường phù hợp với ứng dụng web thông thường; `None; Secure` dành cho những luồng thực sự cần cookie cross-site và phải được kiểm thử cùng HTTPS, CORS, CSRF và chính sách third-party cookie của trình duyệt. Trong Spring Session, xác nhận cuối cùng luôn là header cookie được phát ra và hành vi cookie thực tế trong browser mục tiêu.
