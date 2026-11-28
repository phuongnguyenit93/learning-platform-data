# Reverse proxy, thông tin HTTPS và nguồn header được tin cậy

Trong môi trường production, ứng dụng Spring thường không trực tiếp kết thúc kết nối HTTPS từ trình duyệt. Một reverse proxy hoặc load balancer nhận kết nối TLS, sau đó chuyển request tới ứng dụng qua mạng nội bộ. Vì vậy, ứng dụng có thể nhận một kết nối HTTP dù người dùng bên ngoài đang truy cập bằng HTTPS. Nếu Spring không biết request ban đầu là HTTPS, ứng dụng có thể tạo redirect sai scheme hoặc phát cookie session thiếu thuộc tính `Secure`.

Reverse proxy thường truyền thông tin kết nối ban đầu qua các header như `Forwarded` hoặc `X-Forwarded-Proto`. Spring Boot có thể xử lý các header này bằng cơ chế của Servlet container hoặc filter của framework. Tuy nhiên, các header forwarded chỉ đáng tin khi chúng đến từ proxy mà hệ thống kiểm soát. Nếu ứng dụng tin trực tiếp header do client tùy ý gửi, kẻ tấn công có thể giả mạo scheme, host hoặc địa chỉ nguồn và làm sai lệch quyết định bảo mật.

## 1. Vì sao ứng dụng cần biết request gốc là HTTPS?

Một request có thể đi qua nhiều chặng:

1. Trình duyệt mở kết nối HTTPS tới cổng công khai của reverse proxy.
2. Proxy giải mã TLS và chuyển request tới ứng dụng Spring qua HTTP trong mạng riêng.
3. Ứng dụng nhận kết nối HTTP và nếu không có thông tin bổ sung sẽ thấy `request.isSecure()` là `false`, scheme là `http` và cổng có thể là cổng nội bộ.

Ở tầng ứng dụng, các giá trị request có thể được dùng để quyết định nhiều hành vi:

- Cookie session có được phát với thuộc tính `Secure` hay không.
- Redirect tuyệt đối được tạo bằng `https://` hay `http://`.
- URL callback, liên kết xác minh email hoặc URL được sinh trong response dùng host và port nào.
- Một số cơ chế bảo mật có xem request là kết nối an toàn hay không.
- Log, audit và telemetry ghi nhận scheme, host hoặc địa chỉ client nào.

Nếu ứng dụng chỉ nhìn thấy HTTP nội bộ, nó có thể phát cookie session không có `Secure`, khiến trình duyệt có thể gửi cookie trên kết nối HTTP nếu có đường truy cập phù hợp. Ứng dụng cũng có thể tạo redirect về HTTP, gây lỗi vòng lặp với proxy hoặc làm giảm bảo vệ khi người dùng đi theo liên kết đó.

`Secure` trên cookie yêu cầu trình duyệt chỉ gửi cookie qua kết nối an toàn theo quy tắc của trình duyệt. Thuộc tính này bảo vệ đường truyền cookie ở phía client; nó không thay thế TLS, không mã hóa session data trong Redis/JDBC và không xác thực proxy. Ứng dụng vẫn cần cấu hình TLS cho kết nối bên ngoài và bảo vệ mạng nội bộ giữa proxy với backend theo mô hình triển khai.

## 2. Header forwarded thường gặp

Có hai họ header phổ biến để mô tả request ban đầu.

| Header | Thông tin thường mang theo | Ví dụ |
| --- | --- | --- |
| `Forwarded` | Chuẩn hóa theo RFC 7239; có thể mang `for`, `by`, `host`, `proto` | `Forwarded: for=203.0.113.8;proto=https;host=portal.example.com` |
| `X-Forwarded-Proto` | Scheme của kết nối bên ngoài | `https` |
| `X-Forwarded-Host` | Host mà client dùng khi gọi proxy | `portal.example.com` |
| `X-Forwarded-Port` | Cổng công khai | `443` |
| `X-Forwarded-For` | Địa chỉ client và có thể cả các proxy trong chuỗi | `203.0.113.8` |
| `X-Forwarded-Prefix` | Prefix public được proxy thêm hoặc loại bỏ | `/portal` |

`Forwarded` là header chuẩn hóa; các header `X-Forwarded-*` là quy ước được sử dụng rộng rãi. Hệ thống nên thống nhất proxy phát ra dạng nào và ứng dụng xử lý dạng nào. Không nên để nhiều tầng proxy phát các giá trị mâu thuẫn mà không xác định rõ quy tắc chọn phần tử đáng tin cậy.

Ví dụ, proxy có thể gửi:

```http
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.com
X-Forwarded-Port: 443
X-Forwarded-For: 203.0.113.8
```

Sau khi các header được xử lý đúng, ứng dụng có thể nhìn thấy request như được gửi trực tiếp tới `https://portal.example.com`, dù kết nối TCP giữa proxy và ứng dụng là HTTP. Các API Servlet như `getScheme()`, `isSecure()`, `getServerName()` và `getServerPort()` có thể phản ánh thông tin public đã được proxy xác nhận.

Không dùng `X-Forwarded-For` làm danh tính người dùng. Nó chỉ mô tả địa chỉ mạng theo chuỗi proxy và có thể bị giả mạo nếu trust boundary không được thiết lập đúng. Xác thực người dùng vẫn phải dựa trên cơ chế authentication của ứng dụng.

## 3. Thiết lập ranh giới tin cậy tại reverse proxy

Ứng dụng chỉ nên tin header forwarded được ghi hoặc xác nhận bởi proxy nằm trong vùng tin cậy. Có hai yêu cầu nền tảng:

1. Client bên ngoài không được tự quyết định giá trị forwarded mà backend sẽ tin.
2. Backend chỉ nhận request từ proxy được phép, hoặc có cơ chế xác thực kết nối proxy/backend phù hợp.

Với mô hình một proxy ở biên, proxy nên xóa các header forwarded do client gửi tới rồi tự ghi lại giá trị mà nó quan sát được. Ví dụ cấu hình Nginx minh họa:

```nginx
location / {
    proxy_pass http://spring_app;

    # Ghi lại thông tin mà proxy thực sự quan sát được.
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Host   $host;
    proxy_set_header X-Forwarded-Proto  $scheme;
    proxy_set_header X-Forwarded-Port   $server_port;
    proxy_set_header X-Forwarded-For    $remote_addr;
}
```

Đây là ví dụ cho một proxy tin cậy ở biên. Nếu có CDN, ingress controller hoặc nhiều reverse proxy nối tiếp, cần thiết kế quy tắc nối/ghi đè chuỗi `X-Forwarded-For` và `Forwarded` phù hợp. Không sao chép nguyên cấu hình một proxy đơn lẻ vào kiến trúc nhiều hop mà không xác định proxy nào được phép cung cấp từng phần thông tin.

Ở mạng triển khai, hạn chế truy cập trực tiếp tới cổng backend. Nếu người dùng có thể gọi thẳng ứng dụng mà không qua proxy, họ có thể gửi header forwarded giả. Có thể dùng security group, firewall, network policy, private subnet hoặc mutual TLS để chỉ proxy hợp lệ kết nối được tới backend. Việc ẩn cổng backend khỏi DNS công khai chưa đủ nếu cổng đó vẫn truy cập được từ các mạng không tin cậy.

Nếu proxy ở biên chuyển tiếp giá trị từ proxy phía trước, chỉ chấp nhận các hop đã được quản trị và xác định rõ số lượng hoặc danh sách proxy tin cậy. Một header chứa nhiều địa chỉ không tự chứng minh rằng phần tử đầu tiên là client thật. Khi điều tra, đối chiếu cấu hình proxy, đường đi mạng và log của từng hop.

## 4. Cấu hình forwarded headers trong Spring Boot

Spring Boot cung cấp thuộc tính `server.forward-headers-strategy` để chọn cách xử lý thông tin forwarded cho ứng dụng Servlet. Các lựa chọn chính:

| Giá trị | Cách hoạt động | Khi sử dụng |
| --- | --- | --- |
| `NONE` | Không áp dụng xử lý forwarded headers của Boot | Backend không đứng sau proxy hoặc không tin header forwarded |
| `NATIVE` | Dùng hỗ trợ của Servlet container | Container có cơ chế native phù hợp, ví dụ Tomcat `RemoteIpValve` |
| `FRAMEWORK` | Dùng cơ chế của Spring Framework, thường thông qua `ForwardedHeaderFilter` | Muốn xử lý forwarded headers ở tầng framework |

Ví dụ cấu hình:

```properties
# Chọn một cơ chế xử lý forwarded headers
server.forward-headers-strategy=framework
```

Với `FRAMEWORK`, `ForwardedHeaderFilter` bọc request để các thành phần phía sau nhìn thấy scheme, host, port và thông tin liên quan đã được chuyển tiếp. Filter cần chạy đủ sớm để các thành phần phụ thuộc vào `request.isSecure()` hoặc URL public nhận được giá trị đúng.

Với `NATIVE`, Servlet container xử lý thông tin forwarded. Tomcat có thể sử dụng `RemoteIpValve` để cập nhật địa chỉ remote, scheme, cổng và trạng thái secure dựa trên header đã cấu hình. Jetty và Undertow có cơ chế riêng tương ứng với phiên bản. Hãy kiểm tra tài liệu container đang chạy và xác nhận proxy tin cậy được khai báo đúng.

Chọn một cơ chế làm chủ việc xử lý forwarded headers. Không bật đồng thời xử lý native và framework một cách tùy tiện, vì hai tầng có thể cùng diễn giải header hoặc biến đổi request nhiều lần. Nếu môi trường triển khai có cấu hình mặc định theo platform, hãy kiểm tra giá trị thực tế thay vì giả định mọi môi trường đều dùng `NONE`.

Trong Spring Framework, `ForwardedHeaderFilter` xử lý cả header chuẩn `Forwarded` và các header `X-Forwarded-*` được hỗ trợ. Filter này không tự tạo ra ranh giới tin cậy cho mạng. Nếu ứng dụng nhận request từ nguồn không đáng tin, header có thể bị giả mạo trước khi filter xử lý. Vì vậy, cấu hình proxy và network restriction vẫn là điều kiện bắt buộc.

## 5. Quan hệ giữa request.isSecure() và cookie session

Spring Session dùng `HttpSessionIdResolver` để xác định cách nhận session ID từ request và cách gửi ID trong response. Với cookie resolver mặc định, session ID được trao đổi qua cookie. `DefaultCookieSerializer` điều khiển thuộc tính cookie như tên, path, domain, `HttpOnly`, `Secure`, `SameSite` và thời hạn.

Trong `DefaultCookieSerializer`, nếu không đặt cứng lựa chọn `useSecureCookie`, serializer có thể dựa vào trạng thái secure của request để quyết định có thêm thuộc tính `Secure` hay không. Vì thế, khi TLS kết thúc tại proxy, forwarded headers phải được xử lý đúng trước khi Spring Session ghi cookie. Nếu ứng dụng nhìn request nội bộ là HTTP, cookie có thể thiếu `Secure` dù trình duyệt bên ngoài dùng HTTPS.

Có thể cấu hình cookie luôn dùng `Secure` trong môi trường production:

```properties
server.servlet.session.cookie.name=SESSION
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
```

`server.servlet.session.cookie.secure=true` buộc cookie Servlet session được đánh dấu `Secure`. Nếu cấu hình `DefaultCookieSerializer` trực tiếp, có thể đặt `setUseSecureCookie(true)` theo API của phiên bản đang dùng. Cần tránh để cấu hình cookie Servlet và Spring Session mâu thuẫn; xác định rõ serializer nào đang thực sự phát cookie.

Ví dụ cấu hình serializer bằng Java khi ứng dụng dùng Spring Session cookie:

```java
@Bean
DefaultCookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    return serializer;
}
```

API và cách Boot tự cấu hình serializer có thể khác theo phiên bản và loại repository. Nếu dùng bean tùy chỉnh, kiểm tra bean đó thực sự được Spring Session sử dụng. Không kết luận cookie đã an toàn chỉ vì có một bean `DefaultCookieSerializer` trong context.

`SameSite` và `Secure` giải quyết các khía cạnh khác nhau. `SameSite=Lax` thường phù hợp cho điều hướng web thông thường. Nếu luồng xác thực liên miền cần `SameSite=None`, cookie phải có `Secure` theo quy tắc trình duyệt hiện đại; đồng thời phải rà soát CSRF, CORS và luồng callback. `HttpOnly` ngăn JavaScript đọc cookie nhưng không ngăn mã độc trong trình duyệt thực hiện request cùng origin.

## 6. Host, redirect và cookie path khi có proxy

Ngoài scheme, host và prefix public cũng có thể khác thông tin mà backend nhìn thấy. Ví dụ proxy nhận `/portal/orders` rồi chuyển tới backend dưới `/orders`. Nếu ứng dụng không nhận được prefix public, redirect hoặc URL tạo ra có thể bỏ mất `/portal`.

`X-Forwarded-Host`, `X-Forwarded-Port` và `X-Forwarded-Prefix` có thể giúp framework hoặc container tái dựng địa chỉ public. Chỉ sử dụng chúng nếu proxy có trách nhiệm ghi các giá trị đó và ứng dụng đã tin đúng proxy. Với cookie, `Path` và `Domain` phải phù hợp với URL mà trình duyệt truy cập. Cookie có path quá hẹp hoặc domain sai có thể không được gửi tới request tiếp theo, khiến ứng dụng tạo phiên mới liên tục.

Không nên dùng host do client tự gửi để tạo liên kết tuyệt đối nhạy cảm như URL reset mật khẩu, URL callback hoặc liên kết xác minh email. Nếu forwarded host không được bảo vệ, kẻ tấn công có thể tạo liên kết chứa domain của họ và lừa người nhận. Với các URL quan trọng, dùng public base URL được cấu hình rõ ràng hoặc kiểm tra host theo allowlist.

Nếu proxy chuyển tiếp `X-Forwarded-Prefix`, xác nhận framework/container có xử lý prefix đúng và cookie path mong muốn vẫn được phát. Không tự nối prefix vào path ở nhiều tầng cùng lúc vì có thể tạo đường dẫn lặp như `/portal/portal/...`.

## 7. HSTS, TLS giữa các chặng và bảo vệ session ID

HTTPS ở chặng trình duyệt tới proxy bảo vệ cookie trên mạng công cộng. Kết nối proxy tới backend cũng cần được bảo vệ theo mức độ nhạy cảm của môi trường. Trong mạng nội bộ dùng chung hoặc có nguy cơ bị truy cập, cân nhắc TLS nội bộ hoặc mutual TLS để ngăn bên thứ ba nghe lén hoặc giả làm proxy.

HTTP Strict Transport Security (HSTS) là header do ứng dụng hoặc proxy phát để trình duyệt ưu tiên HTTPS cho domain trong thời hạn được khai báo. Nếu TLS kết thúc tại proxy, cần xác định tầng nào phát HSTS và bảo đảm header chỉ được phát trên kết nối HTTPS phù hợp. HSTS không thay thế thuộc tính `Secure` của cookie và cũng không làm cho forwarded headers trở nên đáng tin.

Session ID là bearer credential: người nắm giữ ID hợp lệ có thể được xem như chủ phiên. Vì vậy:

- Chỉ truyền cookie session qua HTTPS ở môi trường production.
- Đặt `HttpOnly`, `Secure` và `SameSite` theo luồng ứng dụng.
- Không đưa session ID vào URL, query string hoặc log.
- Không cho client tự quyết định scheme/host mà backend tin qua forwarded headers.
- Hạn chế truy cập trực tiếp tới backend và dùng proxy được kiểm soát.
- Đổi session ID sau xác thực và vô hiệu hóa phiên khi đăng xuất hoặc khi cần thu hồi.

## 8. Ví dụ cấu hình triển khai end-to-end

Giả sử trình duyệt truy cập `https://portal.example.com`, Nginx kết thúc TLS rồi proxy request tới Spring Boot trên mạng riêng. Một cấu hình điển hình cần thống nhất ba phần:

**Tại proxy:** ghi đè forwarded headers bằng thông tin mà proxy quan sát được, không chuyển tiếp nguyên vẹn giá trị do client tự gửi. Hạn chế cổng backend để chỉ proxy được phép kết nối.

**Tại Spring Boot:** chọn một chiến lược xử lý forwarded headers phù hợp với container:

```properties
server.forward-headers-strategy=framework

server.servlet.session.cookie.name=SESSION
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
```

**Tại Spring Session:** xác nhận cookie serializer đang dùng và repository session là Redis hoặc JDBC theo cấu hình ứng dụng. Không tạo thêm serializer hoặc filter nếu Boot đã cấu hình đúng. Kiểm tra response thực tế để xác nhận cookie có `Secure`, `HttpOnly`, `SameSite` và path/domain như dự kiến.

Sau khi triển khai, request đến ứng dụng cần cho thấy `request.getScheme()` là `https`, `request.isSecure()` là `true`, host/port phản ánh địa chỉ public nếu các thành phần phía sau cần chúng. Các giá trị này chỉ đáng tin khi ứng dụng nhận request từ proxy đã xác thực và proxy ghi lại header chính xác.

## 9. Kiểm thử và chẩn đoán

Không chỉ kiểm tra bằng cách gọi trực tiếp endpoint backend. Hãy kiểm thử qua đúng đường đi của production: trình duyệt hoặc HTTP client → proxy → ứng dụng. Một số kịch bản quan trọng:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Truy cập HTTPS qua proxy | Backend nhận request secure sau khi forwarded headers được xử lý |
| Proxy chuyển tiếp HTTPS tới backend HTTP | Cookie session vẫn có `Secure` |
| Gửi request với header `X-Forwarded-Proto: http` giả từ client | Proxy biên ghi đè hoặc loại bỏ; backend không tin giá trị giả |
| Gửi `Forwarded` và `X-Forwarded-*` mâu thuẫn | Cấu hình xử lý thống nhất, không có diễn giải bất ngờ |
| Redirect sau đăng nhập | Scheme, host, port và prefix đúng địa chỉ public |
| Cookie path/domain | Trình duyệt gửi cookie cho request tiếp theo |
| Gọi thẳng backend từ mạng không tin cậy | Kết nối bị chặn hoặc không thể giả mạo proxy tin cậy |
| Nhiều proxy nối tiếp | Chỉ các hop được cho phép mới ảnh hưởng thông tin request |

Có thể kiểm tra response bằng công cụ HTTP hoặc tab Network của trình duyệt. Quan sát `Set-Cookie` và xác nhận các thuộc tính, không chỉ nhìn tên cookie. Kiểm tra request kế tiếp có gửi cookie đó và ứng dụng khôi phục đúng phiên hay không.

Khi cần debug, log tạm `scheme`, `isSecure`, host, port và địa chỉ remote sau khi xử lý forwarded headers. Không log giá trị cookie session. So sánh log tại proxy với log tại backend để xác định header bị mất, bị ghi đè hoặc bị tin quá mức ở tầng nào. Nếu dùng Tomcat native processing, kiểm tra cấu hình `RemoteIpValve` và danh sách internal/trusted proxies; nếu dùng `FRAMEWORK`, kiểm tra filter có được đăng ký và chạy trước các thành phần tạo redirect/cookie.

## 10. Lỗi thường gặp

**Cookie session không có `Secure` dù trình duyệt truy cập HTTPS.** Backend có thể đang nhìn request là HTTP. Kiểm tra proxy có gửi `X-Forwarded-Proto: https` hoặc `Forwarded: proto=https` không, chiến lược forwarded headers của Boot, thứ tự filter và cấu hình serializer. Trong production, có thể buộc `secure=true` để bảo vệ cookie kể cả khi phát hiện scheme gặp lỗi; vẫn cần sửa forwarded processing để redirect và các API request khác phản ánh đúng HTTPS.

**Redirect quay về HTTP hoặc tạo vòng lặp.** Ứng dụng chưa nhận đúng scheme public hoặc proxy có cấu hình chuyển hướng không nhất quán. Kiểm tra `request.isSecure()`, scheme sau khi xử lý forwarded headers và logic redirect ở proxy. Không khắc phục bằng cách tin mọi header do client gửi.

**Host hoặc URL callback có domain lạ.** Kiểm tra `Host` và `X-Forwarded-Host` có bị client kiểm soát không. Đặt allowlist host hoặc public base URL cố định cho các liên kết nhạy cảm; cấu hình proxy ghi lại forwarded host.

**Ứng dụng hoạt động khi qua load balancer nhưng lỗi khi gọi trực tiếp.** Có thể backend đang tin forwarded headers mà chỉ proxy mới được phép cung cấp. Chặn truy cập trực tiếp tới backend; nếu cần môi trường phát triển gọi trực tiếp, dùng cấu hình riêng với trust policy rõ ràng.

**Cookie bị gửi sai path hoặc domain.** Kiểm tra `X-Forwarded-Prefix`, context path, `CookieSerializer`, `Path` và `Domain`. Đảm bảo proxy không thêm prefix nhiều lần và cookie khớp URL public.

**Địa chỉ client trong log sai hoặc dễ giả mạo.** Xem lại chuỗi proxy và cách xử lý `X-Forwarded-For`. Chỉ tin địa chỉ được thêm bởi proxy trong danh sách tin cậy; không dùng giá trị header đầu vào làm bằng chứng danh tính.

## 11. Checklist trước khi đưa lên production

- Xác định rõ TLS kết thúc ở proxy nào và request từ proxy tới backend đi qua mạng nào.
- Chỉ cho proxy tin cậy kết nối tới backend; xóa hoặc ghi đè forwarded headers do client cung cấp.
- Chọn đúng một cơ chế xử lý forwarded headers: `NONE`, `NATIVE` hoặc `FRAMEWORK`.
- Xác nhận `request.isSecure()`, scheme, host và port phản ánh địa chỉ public sau xử lý.
- Buộc cookie session có `Secure` và `HttpOnly`; chọn `SameSite`, `Path` và `Domain` phù hợp.
- Kiểm thử `Set-Cookie`, redirect, callback URL, cookie path và request tiếp theo qua proxy.
- Kiểm tra trường hợp header giả mạo, header mâu thuẫn và request gọi trực tiếp backend.
- Không ghi session ID hoặc cookie đầy đủ vào log; bảo vệ cả chặng proxy/backend theo yêu cầu môi trường.

Khi proxy, trust boundary và Spring Boot được cấu hình nhất quán, ứng dụng có thể nhận biết đúng request ban đầu dùng HTTPS và phát cookie session an toàn. Điều đó giúp Spring Session tiếp tục quản lý phiên tập trung qua Redis hoặc JDBC mà không phụ thuộc vào việc TLS được kết thúc tại ứng dụng hay tại reverse proxy.
