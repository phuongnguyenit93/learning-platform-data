# Path, Domain, host-only và phạm vi trình duyệt gửi cookie

Spring Session nhận diện phiên bằng session ID thường được gửi qua cookie. Trình duyệt không gửi mọi cookie trong mọi request: nó kiểm tra host, đường dẫn, giao thức, thời hạn và các chính sách cookie trước khi thêm cookie vào header Cookie. Vì vậy, cấu hình Path và Domain quyết định request nào có thể mang session ID đến ứng dụng.

Phạm vi cookie ảnh hưởng trực tiếp đến việc ứng dụng có tìm lại được session hay không. Cookie quá hẹp có thể không được gửi đến endpoint cần phiên. Cookie quá rộng có thể làm session ID được gửi đến những ứng dụng hoặc subdomain không cần truy cập nó. Với Spring Session, cần chọn phạm vi phù hợp với hostname và context path mà trình duyệt thực sự sử dụng.

## 1. Trình duyệt quyết định gửi cookie như thế nào?

Khi server tạo cookie, response thường có header Set-Cookie. Trình duyệt lưu cookie cùng các thuộc tính như tên, giá trị, host/domain, path, thời hạn, Secure, HttpOnly và SameSite. Ở request sau, trình duyệt chọn các cookie phù hợp rồi gửi chúng trong header Cookie.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=abc123; Path=/shop; Secure; HttpOnly; SameSite=Lax
~~~

Khi trình duyệt gửi request đến https://shop.example.com/shop/cart, cookie SESSION có thể được gửi vì host và path phù hợp, kết nối dùng HTTPS, và chính sách SameSite cho phép request đó. Request đến https://shop.example.com/api/orders không khớp Path=/shop, nên trình duyệt không gửi cookie này.

Các điều kiện chính gồm:

1. Host của request phải khớp phạm vi host/domain của cookie.
2. Request path phải khớp Path của cookie.
3. Cookie có Secure chỉ được gửi qua kết nối bảo mật, thông thường là HTTPS.
4. Cookie phải còn hạn và chưa bị xóa.
5. Chính sách SameSite và các quy tắc riêng của trình duyệt phải cho phép gửi cookie trong ngữ cảnh request đó.

HttpOnly kiểm soát việc JavaScript truy cập cookie; thuộc tính này không ngăn trình duyệt gửi cookie trong HTTP request. Secure kiểm soát giao thức truyền. SameSite kiểm soát một phần việc gửi cookie trong ngữ cảnh cross-site. Các thuộc tính này có vai trò khác với Path và Domain.

## 2. Host-only cookie là gì?

Cookie là host-only khi server tạo cookie mà không có thuộc tính Domain. Trình duyệt chỉ gửi cookie đó đến đúng host đã đặt cookie. Cookie được tạo bởi shop.example.com sẽ được gửi đến shop.example.com, nhưng không tự động được gửi đến api.example.com, admin.example.com hoặc example.com.

Ví dụ:

~~~http
Set-Cookie: SESSION=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Header trên không có Domain, vì vậy cookie là host-only. Đây thường là lựa chọn phù hợp khi một ứng dụng chạy trên một hostname riêng và không có nhu cầu chia sẻ cookie phiên với subdomain khác.

Host-only giúp giới hạn nơi session ID được gửi. Nếu một ứng dụng chỉ chạy tại shop.example.com, việc không khai báo Domain sẽ tránh gửi cookie đó đến các subdomain như blog.example.com hoặc support.example.com.

Lưu ý: host-only không có nghĩa cookie chỉ dùng được trong một port. Cookie không được phân tách theo port. Các dịch vụ HTTP chạy trên shop.example.com:443 và shop.example.com:8443 có thể cùng thuộc phạm vi host của cookie; các thuộc tính khác như Secure, Path và chính sách trình duyệt vẫn được áp dụng.

## 3. Domain cookie và domain matching

Nếu server khai báo thuộc tính Domain, trình duyệt có thể gửi cookie đến host đã đặt cookie và các subdomain phù hợp với domain đó. Ví dụ, ứng dụng tại shop.example.com phát hành:

~~~http
Set-Cookie: SESSION=abc123; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie có thể được gửi đến:

- example.com
- shop.example.com
- api.example.com
- admin.example.com
- a.b.example.com

Cookie không được gửi đến other-example.com hoặc example.net, vì các host đó không khớp domain example.com.

Trình duyệt kiểm tra domain theo quy tắc domain-match: host phải bằng domain cookie hoặc kết thúc bằng domain cookie với ranh giới dấu chấm phù hợp. Vì vậy badexample.com không khớp example.com, trong khi api.example.com có thể khớp.

Một số điểm cần nhớ:

- Domain=example.com mở rộng phạm vi đến các subdomain phù hợp.
- Dấu chấm ở đầu như .example.com bị trình duyệt hiện đại bỏ qua; nó không tạo ra một chế độ domain khác.
- Server không thể đặt cookie cho một domain không phải domain hiện tại hoặc domain cha hợp lệ của nó.
- Trình duyệt từ chối những Domain không hợp lệ, chẳng hạn public suffix như com hoặc co.uk.
- Thuộc tính Domain không bao gồm port.

Chỉ cấu hình Domain khi có nhu cầu chia sẻ cookie giữa nhiều host. Cookie Domain rộng có thể khiến session ID được gửi đến subdomain do nhóm khác vận hành hoặc subdomain có cấu hình bảo mật yếu. Nếu một subdomain bị chiếm quyền hoặc có ứng dụng không đáng tin cậy, phạm vi cookie rộng làm tăng hậu quả của sự cố.

## 4. So sánh host-only và Domain cookie

Giả sử ứng dụng tạo cookie từ shop.example.com:

| Request host | Không có Domain (host-only) | Domain=example.com |
| --- | --- | --- |
| example.com | Không gửi | Gửi |
| shop.example.com | Gửi | Gửi |
| api.example.com | Không gửi | Gửi |
| admin.example.com | Không gửi | Gửi |
| example.net | Không gửi | Không gửi |
| badexample.com | Không gửi | Không gửi |

Với ứng dụng Spring Session, host-only thường là điểm bắt đầu an toàn khi một ứng dụng phục vụ trên một hostname. Chỉ chuyển sang Domain cookie khi kiến trúc thực sự cần các subdomain cùng nhận session ID và các subdomain đó thuộc cùng ranh giới tin cậy.

Chia sẻ cookie giữa subdomain không tự động chia sẻ dữ liệu session. Các ứng dụng nhận cùng cookie vẫn phải có cấu hình tương thích và cùng truy cập một repository nếu chúng cần dùng cùng session. Ngược lại, hai ứng dụng dùng chung Redis nhưng có cookie host-only khác host vẫn có thể không nhận được cùng session ID từ trình duyệt.

## 5. Path cookie và path matching

Thuộc tính Path giới hạn các đường dẫn request mà trình duyệt sẽ gửi cookie. Ví dụ:

~~~http
Set-Cookie: SESSION=abc123; Path=/shop; Secure; HttpOnly; SameSite=Lax
~~~

Cookie này được gửi đến /shop, /shop/, /shop/cart và /shop/orders/123. Nó không được gửi đến /api, /admin hoặc /shopping.

Quy tắc path-match có thể hiểu như sau:

- Request path bằng cookie path thì khớp.
- Request path bắt đầu bằng cookie path và ký tự tiếp theo là dấu / thì khớp.
- Nếu cookie path không kết thúc bằng /, một tiền tố chỉ giống một phần tên thư mục sẽ không đủ để khớp.

| Cookie Path | Request path | Có khớp? |
| --- | --- | --- |
| / | /shop/cart | Có |
| /shop | /shop | Có |
| /shop | /shop/cart | Có |
| /shop | /shopping | Không |
| /shop/ | /shop/cart | Có |
| /shop/ | /shop | Không |
| /api | /api/orders | Có |
| /api | /shop/cart | Không |

Nếu không khai báo Path, trình duyệt tính default-path dựa trên đường dẫn của request đã tạo cookie. Ví dụ cookie được tạo từ request /shop/cart/add có thể nhận default-path /shop/cart. Default path phụ thuộc URL request tại thời điểm phát hành, nên không nên dựa vào nó khi ứng dụng có cấu trúc endpoint rõ ràng. Đặt Path tường minh giúp hành vi dễ dự đoán hơn.

Path=/ có nghĩa cookie được gửi đến mọi đường dẫn trên host phù hợp. Path=/shop giới hạn cookie vào khu vực /shop của host đó. Nếu cùng một host phục vụ nhiều ứng dụng ở các context path khác nhau, Path hẹp có thể tránh gửi session cookie của ứng dụng này đến endpoint của ứng dụng khác.

### Path không phải ranh giới bảo mật

Không dùng Path để cách ly các ứng dụng như thể chúng ở các origin độc lập. Các ứng dụng cùng host vẫn có thể có rủi ro tương tác qua JavaScript cùng origin, cấu hình server, redirect hoặc lỗi ứng dụng. Path chủ yếu điều khiển việc trình duyệt tự động gửi cookie theo URL; nó không thay thế xác thực, phân quyền, HttpOnly, Secure hay việc tách ứng dụng sang hostname riêng khi cần ranh giới bảo mật.

Nếu hai ứng dụng cùng host dùng cùng tên cookie nhưng Path khác nhau, trình duyệt có thể lưu cả hai cookie và gửi nhiều cặp cùng tên trong một request phù hợp với cả hai path. Server có thể xử lý không như mong đợi nếu có nhiều cookie trùng tên. Nên dùng tên cookie riêng hoặc thiết kế Path nhất quán, tránh phụ thuộc vào thứ tự cookie trùng tên.

## 6. Kết hợp Domain và Path

Domain và Path được xét đồng thời. Domain xác định host nào được nhận cookie; Path xác định đường dẫn nào trên host đó được nhận cookie.

Ví dụ:

~~~http
Set-Cookie: SESSION=abc123; Domain=example.com; Path=/shop; Secure; HttpOnly; SameSite=Lax
~~~

Cookie có thể được gửi đến /shop trên example.com, shop.example.com hoặc api.example.com, miễn là request thỏa các điều kiện còn lại. Nó không được gửi đến /admin trên các host đó, và cũng không được gửi đến other.example.net.

Ví dụ ma trận:

| URL request | Domain khớp? | Path khớp? | Cookie được gửi? |
| --- | --- | --- | --- |
| https://shop.example.com/shop/cart | Có | Có | Có |
| https://api.example.com/shop/items | Có | Có | Có |
| https://admin.example.com/admin | Có | Không | Không |
| https://example.com/shop | Có | Có | Có |
| https://other.example.net/shop | Không | Có | Không |

Nếu cookie host-only được tạo tại shop.example.com với Path=/shop, chỉ URL có host chính xác shop.example.com và path phù hợp mới nhận cookie.

## 7. Cấu hình Path và Domain trong Spring Session

Với ứng dụng Servlet dùng Spring Session, có thể cấu hình cookie bằng bean CookieSerializer. DefaultCookieSerializer cho phép đặt tên cookie, Path, Domain và các thuộc tính liên quan.

### Trường hợp host-only

Nếu ứng dụng chỉ chạy tại shop.example.com và đặt dưới context path /shop, có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SHOPSESSION");
        serializer.setCookiePath("/shop");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        // Không gọi setDomainName(): cookie là host-only.
        return serializer;
    }
}
~~~

Vì không đặt Domain, cookie được giới hạn ở host phát hành. Path=/shop giới hạn cookie vào các request có path phù hợp. Nếu ứng dụng chạy ở root context, chọn Path phù hợp như /. Nếu ứng dụng nằm sau reverse proxy và URL bên ngoài khác context path nội bộ, phải cấu hình theo URL mà trình duyệt nhìn thấy và kiểm thử qua proxy.

### Trường hợp cần chia sẻ cookie giữa subdomain

Chỉ khi nhiều subdomain có nhu cầu dùng cùng session ID và cùng thuộc ranh giới tin cậy, mới đặt Domain:

~~~java
@Bean
CookieSerializer sharedSessionCookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SHAREDSESSION");
    serializer.setCookiePath("/");
    serializer.setDomainName("example.com");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
~~~

Với cấu hình này, cookie được phát hành với Domain example.com và có thể được gửi đến các subdomain phù hợp. Tất cả host cần sử dụng cùng session phải kết nối đến repository dùng chung, dùng namespace tương thích và có cách xử lý xác thực thống nhất. Nếu chỉ muốn cookie dùng cho một host, bỏ lời gọi setDomainName().

Không nên đặt Domain là domain cha chỉ vì các ứng dụng có cùng tổ chức hoặc cùng DNS zone. Mỗi subdomain có thể có đội vận hành, vòng đời và mức độ tin cậy khác nhau. Mở rộng cookie domain có thể làm session ID bị gửi đến nhiều hệ thống hơn dự định.

## 8. Cookie theo context path và nhiều ứng dụng trên cùng host

Giả sử một máy chủ phục vụ hai ứng dụng:

- Ứng dụng bán hàng tại https://example.com/shop
- Ứng dụng quản trị tại https://example.com/admin

Nếu cả hai cùng dùng cookie tên SESSION và Path /, trình duyệt có thể gửi cookie đó đến cả hai ứng dụng. Nếu mỗi ứng dụng có repository riêng, ứng dụng còn lại có thể không tìm thấy session hoặc có thể ghi đè cookie khi phát hành session mới.

Có thể xử lý bằng cách:

1. Dùng tên cookie riêng, ví dụ SHOPSESSION và ADMINSESSION.
2. Chọn Path tương ứng như /shop và /admin nếu kiến trúc cho phép.
3. Tách host thành shop.example.com và admin.example.com khi cần ranh giới host rõ hơn.
4. Chỉ dùng chung Domain và session repository nếu hai ứng dụng được thiết kế để chia sẻ cùng danh tính và trạng thái phiên.

Không giả định Path thay thế hoàn toàn việc tách hostname. Path hữu ích để giới hạn request nhận cookie, nhưng cùng host vẫn là cùng origin đối với nhiều cơ chế bảo mật của trình duyệt.

## 9. Xóa hoặc thay đổi cookie khi đổi phạm vi

Trình duyệt nhận diện cookie bằng tên, domain và path. Khi xóa cookie, response cần phát hành cookie cùng tên với thời hạn đã hết và phạm vi phù hợp với cookie cũ. Nếu cookie cũ được tạo với Domain=example.com; Path=/shop, việc chỉ xóa một cookie host-only hoặc dùng Path=/ có thể không xóa đúng bản ghi cũ.

Ví dụ xóa cookie với phạm vi phù hợp:

~~~http
Set-Cookie: SESSION=; Domain=example.com; Path=/shop; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Khi đổi từ host-only sang Domain cookie hoặc đổi Path, trình duyệt có thể giữ cookie cũ song song với cookie mới. Trong quá trình chuyển đổi:

- Phát hành cookie mới với phạm vi đã chọn.
- Xóa cookie cũ bằng đúng tên và phạm vi cũ.
- Kiểm tra request header Cookie để phát hiện trường hợp có nhiều cookie cùng tên.
- Cân nhắc buộc đăng nhập lại nếu không thể chuyển đổi session ID một cách an toàn.

Khi dùng Spring Session, cần đảm bảo cấu hình xóa cookie trong logout flow tương thích với CookieSerializer đang dùng. Nếu đã thay đổi tên, Path hoặc Domain, phải kiểm tra response đăng xuất và xác nhận cookie cũ thực sự biến mất khỏi cookie jar của trình duyệt.

## 10. Kiểm thử phạm vi cookie

Nên kiểm thử bằng trình duyệt thật hoặc công cụ HTTP có quản lý cookie. Trong Developer Tools, mở tab Application/Storage để xem cookie đã lưu, các cột Domain, Path, Secure, HttpOnly và SameSite. Trong tab Network, xem Set-Cookie ở response và Cookie ở request kế tiếp.

Với curl, có thể lưu cookie vào cookie jar rồi gửi lại:

~~~bash
curl -i -c cookies.txt https://shop.example.com/shop
curl -i -b cookies.txt https://shop.example.com/shop/cart
curl -i -b cookies.txt https://shop.example.com/api
curl -i -b cookies.txt https://api.example.com/shop
~~~

Các lệnh trên chỉ cho kết quả có ý nghĩa khi hostname trỏ đến môi trường kiểm thử có thể truy cập và chứng thư TLS hợp lệ. Quan sát header Cookie ở request hoặc dùng chế độ verbose để xác nhận cookie được gửi ở URL nào. Không chia sẻ cookie jar vì nó có thể chứa session ID hợp lệ.

Một bộ kiểm thử nên bao gồm:

| Trường hợp | Kết quả cần xác nhận |
| --- | --- |
| Host-only tại shop.example.com | Cookie được gửi đến đúng host |
| Request đến api.example.com với host-only cookie | Cookie không được gửi |
| Domain cookie example.com | Cookie được gửi đến các subdomain phù hợp |
| Request path /shop/cart với Path /shop | Cookie được gửi |
| Request path /shopping với Path /shop | Cookie không được gửi |
| Path / | Cookie khớp mọi đường dẫn trên host/domain phù hợp |
| HTTP với cookie Secure | Trình duyệt không gửi cookie |
| Logout | Cookie có phạm vi cũ được xóa và session bị vô hiệu hóa |

Kiểm thử thêm qua reverse proxy nếu ứng dụng được công khai dưới hostname hoặc context path khác với cấu hình nội bộ. Đặc biệt kiểm tra cookie Path trong response sau khi proxy rewrite URL. Cấu hình đúng khi truy cập trực tiếp localhost chưa chắc đúng khi truy cập qua domain production.

## 11. Các lỗi thường gặp và cách xử lý

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Đăng nhập thành công nhưng request tiếp theo mất session | Cookie Path không khớp endpoint tiếp theo | Xem Path trong Set-Cookie và URL request |
| Subdomain không nhận cookie | Cookie là host-only hoặc Domain không bao phủ subdomain | Kiểm tra có cần Domain cookie hay không |
| Cookie bị gửi đến ứng dụng không liên quan | Domain quá rộng hoặc Path là / trên cùng host | Thu hẹp Domain/Path, tách tên cookie hoặc hostname |
| Có hai cookie cùng tên | Ứng dụng đổi Path/Domain nhưng chưa xóa cookie cũ | Xem cookie jar và xóa theo phạm vi cũ |
| Cookie không xuất hiện khi chạy HTTP local | Cookie có thuộc tính Secure | Dùng HTTPS hoặc cấu hình riêng cho local |
| Ứng dụng sau proxy không nhận session | Path/host bên ngoài khác cấu hình ứng dụng | Kiểm tra header response và URL công khai qua proxy |

Khi điều tra, không chỉ xem cookie có tồn tại trong trình duyệt hay không. Hãy kiểm tra cả ba điểm: server đã phát Set-Cookie với phạm vi nào, trình duyệt đã lưu cookie nào, và request thực tế đã gửi header Cookie nào. Sau đó xác nhận Spring Session instance nhận được ID đó có thể đọc session từ repository.

## 12. Nguyên tắc chọn phạm vi

- Ưu tiên host-only bằng cách không đặt Domain khi chỉ một hostname cần session.
- Chỉ đặt Domain ở domain cha khi các subdomain cần chia sẻ cookie và cùng thuộc ranh giới tin cậy.
- Chọn Path theo đường dẫn công khai của ứng dụng; dùng / khi cookie thực sự cần cho mọi endpoint trên host.
- Không xem Path là cơ chế phân quyền hoặc ranh giới bảo mật.
- Dùng tên cookie riêng nếu nhiều ứng dụng cùng host có session độc lập.
- Khi đổi Path hoặc Domain, xóa cookie cũ bằng đúng tên và phạm vi cũ.
- Kiểm thử cả hostname, subdomain, context path, HTTPS và luồng đăng xuất qua reverse proxy.

Domain xác định host nào có thể nhận cookie; nếu bỏ thuộc tính này, cookie là host-only và chỉ được gửi đến host phát hành. Path xác định những đường dẫn request trên host phù hợp có thể nhận cookie. Chọn hai thuộc tính theo đúng kiến trúc Spring Session giúp trình duyệt gửi session ID đến đúng ứng dụng, hạn chế phạm vi cookie và tránh lỗi mất phiên khi request đi qua nhiều endpoint hoặc subdomain.
