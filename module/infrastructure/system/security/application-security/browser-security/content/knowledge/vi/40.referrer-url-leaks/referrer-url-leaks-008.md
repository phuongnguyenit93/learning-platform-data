# Giảm dữ liệu trong URL: hạn chế rò rỉ qua history, referrer và log

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Nhận diện các thành phần URL và dữ liệu có thể bị lộ qua path, query và redirect.
2. Giải thích vì sao URL thường xuất hiện trong browser history, bookmark, Referer, server log, proxy, CDN và analytics.
3. Phân loại dữ liệu không nên đặt trong URL, gồm credential, token, mã xác thực và thông tin cá nhân.
4. Chọn GET, POST hoặc server-side state theo mục đích và mức độ nhạy cảm của dữ liệu.
5. Cấu hình Referrer-Policy phù hợp và hiểu khác biệt giữa các directive.
6. Thiết kế OAuth/OIDC callback và reset link để giảm thời gian tồn tại của secret trong URL.
7. Làm sạch URL ở browser đúng cách mà không nhầm việc đó với xóa log hoặc lịch sử đã ghi.
8. Redact query/path nhạy cảm tại reverse proxy, CDN, WAF, APM và analytics.
9. Phòng open redirect, URL injection, cache leakage và lỗi hiển thị URL đầy đủ.
10. Kiểm thử referrer và URL leak bằng DevTools, log test và ma trận kiểm thử.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. URL là dữ liệu đi qua nhiều lớp browser và hạ tầng. Giảm thông tin nhạy cảm trong URL giúp hạn chế rò rỉ qua history, referrer, log, analytics và các hệ thống quan sát.

## 1. Vì sao dữ liệu trong URL dễ bị lộ?

URL được thiết kế để định vị tài nguyên và có thể được lưu, chia sẻ, ghi log hoặc gửi kèm theo request. Nó không phải một kho bí mật.

Ví dụ:

    https://shop.example.test/orders?customer=alice&token=secret-value

Trong ví dụ này, token nằm trong query string. Dù trang dùng HTTPS, token vẫn có thể xuất hiện ở:

- Browser history và danh sách gợi ý địa chỉ.
- Bookmark hoặc URL người dùng sao chép để chia sẻ.
- HTTP access log tại web server, reverse proxy, CDN hoặc WAF.
- APM, distributed tracing và hệ thống error reporting.
- Analytics SDK hoặc script bên thứ ba đọc location.href.
- Referer header khi trang điều hướng hoặc tải tài nguyên khác.
- Screenshot, screen recording, clipboard và nội dung hỗ trợ khách hàng.
- Log do ứng dụng tự ghi khi có exception hoặc debug.

HTTPS mã hóa dữ liệu trên đường truyền giữa các điểm TLS tương ứng. HTTPS không ngăn browser, server, proxy kết thúc TLS hoặc script đang chạy trong trang ghi lại URL.

### URL có nhiều thành phần

Một URL có cấu trúc tổng quát:

    https://user:password@example.test:8443/orders/123?tab=history#details

| Thành phần | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Scheme | https | Xác định giao thức |
| User information | user:password | Thông tin đăng nhập nhúng trong URL; tránh sử dụng |
| Host | example.test | Máy chủ hoặc tên miền |
| Port | 8443 | Cổng kết nối |
| Path | /orders/123 | Đường dẫn tài nguyên; thường được gửi tới server |
| Query | ?tab=history | Tham số request; thường được gửi tới server |
| Fragment | #details | Phần định vị phía client; không được gửi trong HTTP request thông thường |

Path và query thường xuất hiện trong request target và log hạ tầng. Fragment không được gửi trong HTTP request tới server, nhưng vẫn có thể được browser lưu trong history và JavaScript cùng trang đọc qua location.hash hoặc location.href.

Không chuyển token từ query sang fragment rồi coi vấn đề đã được giải quyết. Fragment tránh một số log server và Referer, nhưng vẫn có thể bị script, extension, history, screenshot hoặc code client đọc.

### User information trong URL

Không nhúng username/password vào URL:

    https://alice:password@example.test/

Cách này có thể làm credential xuất hiện trong history, log, công cụ giám sát hoặc giao diện. Browser và thư viện URL hiện đại cũng có các quy tắc xử lý riêng với user information. Dùng cơ chế xác thực được thiết kế cho HTTP/application thay vì nhúng credential vào URL.

## 2. Dữ liệu nào không nên đặt trong URL?

Tránh đưa các dữ liệu sau vào path hoặc query:

- Password, PIN và câu trả lời bảo mật.
- Access token, refresh token, session ID và API key.
- Mã OTP hoặc mã khôi phục có thể dùng để xác thực.
- Reset-password token hoặc invitation token có quyền sử dụng.
- Thông tin thanh toán, số tài khoản và dữ liệu định danh nhạy cảm.
- Email, số điện thoại, địa chỉ hoặc dữ liệu cá nhân nếu không cần công khai.
- Dữ liệu nội bộ, tên khách hàng hoặc thông tin đơn hàng không cần xuất hiện ở URL.
- Nội dung tìm kiếm có thể chứa thông tin sức khỏe, tài chính hoặc bí mật công việc.

Ngay cả khi giá trị đã được mã hóa hoặc hash, URL vẫn có thể chứa một định danh ổn định có khả năng liên kết hoạt động. Hash không tự biến dữ liệu thành anonymous.

### Phân biệt dữ liệu định tuyến và dữ liệu bí mật

Thông tin phù hợp với URL thường là dữ liệu định tuyến hoặc trạng thái giao diện không nhạy cảm:

    /products/keyboard
    /catalog?category=office&page=2
    /help/shipping

Thông tin không phù hợp:

    /reset?token=long-lived-secret
    /account?access_token=...
    /invoice?card_number=...
    /search?q=medical-diagnosis-and-personal-details

Một ID tài nguyên trong path không nhất thiết là bí mật, nhưng backend vẫn phải kiểm tra authorization. URL khó đoán không thay thế quyền truy cập.

### Không coi URL khó đoán là access control

UUID hoặc chuỗi ngẫu nhiên có thể giảm khả năng đoán URL, nhưng nếu ai có URL cũng đọc được dữ liệu thì đó vẫn là bearer capability. Với URL cấp quyền truy cập, cần TTL, scope, revoke, audit và cơ chế chia sẻ có chủ đích. Đối với tài nguyên tài khoản, vẫn xác thực và kiểm tra quyền ở server.

## 3. Những nơi URL có thể xuất hiện

### Browser history và đồng bộ

Browser thường lưu URL đã truy cập trong history. Người dùng có thể:

- Mở lại URL từ lịch sử.
- Tìm URL qua thanh địa chỉ.
- Đồng bộ history giữa các thiết bị.
- Sao chép URL vào clipboard.
- Chia sẻ URL qua chat, email hoặc ticket hỗ trợ.

Private browsing thường giới hạn việc lưu history lâu dài sau khi đóng phiên, nhưng không ngăn mọi script hoặc hệ thống hạ tầng quan sát URL trong lúc sử dụng.

### Referer header

Khi browser tải tài nguyên hoặc điều hướng từ trang này sang trang khác, nó có thể gửi header HTTP Referer chứa thông tin về trang nguồn. Tên header trong HTTP được viết là Referer, dù thuộc tính JavaScript là referrer.

Tùy Referrer-Policy, giá trị có thể chứa:

- Origin.
- Origin cùng path.
- Origin cùng path và query.
- Không có referrer.

Fragment và user information không được đưa vào Referer theo quy tắc xử lý referrer, nhưng query/path nhạy cảm vẫn có thể bị gửi nếu policy cho phép.

### Server, proxy và CDN

Request target thường chứa path và query. Nhiều access log mặc định ghi URL hoặc request URI. Reverse proxy, CDN, WAF và load balancer cũng có thể ghi request metadata.

Ngay cả khi ứng dụng không log query, URL vẫn có thể nằm trong log của hạ tầng phía trước.

### Analytics, APM và error reporting

SDK có thể tự thu thập page URL, route, query parameter hoặc navigation event. Error report thường đính kèm location.href để giúp tái hiện lỗi.

Nếu URL có token hoặc PII, việc gửi telemetry có thể làm dữ liệu lan sang nhà cung cấp bên thứ ba và hệ thống lưu trữ khác.

### Redirect và hệ thống hỗ trợ

URL có thể được chuyển qua nhiều redirect. Mỗi hop có thể tạo log hoặc truyền referrer theo policy áp dụng. Người dùng cũng có thể chụp màn hình, gửi link hoặc dán URL vào ticket.

Không chỉ kiểm tra trang cuối cùng. Hãy kiểm tra toàn bộ callback, redirect, proxy và telemetry trong luồng.

## 4. GET và POST: chọn đúng vị trí cho dữ liệu

### GET dành cho truy vấn và điều hướng

GET phù hợp để đọc tài nguyên và biểu diễn trạng thái có thể bookmark/chia sẻ:

    GET /api/products?category=books&page=2

Không đặt secret trong query chỉ vì endpoint là API. Query string vẫn có thể được ghi log hoặc gửi qua Referer.

### POST có thể giảm lộ dữ liệu qua URL

POST thường gửi dữ liệu trong request body:

    POST /api/session
    Content-Type: application/json

    {
      "email": "user@example.test",
      "password": "..."
    }

Body không xuất hiện trong URL, browser history hoặc Referer. Tuy nhiên, POST không tự làm dữ liệu an toàn:

- TLS vẫn cần để bảo vệ dữ liệu trên đường truyền.
- Server, WAF, proxy hoặc APM có thể ghi request body nếu cấu hình capture.
- Browser DevTools có thể hiển thị payload trong phiên debug.
- XSS có thể đọc dữ liệu trước khi gửi.
- CSRF vẫn cần được xử lý nếu request dùng cookie session.
- Cache và retry phải được thiết kế đúng.

Không chuyển secret từ query sang body rồi bỏ qua log redaction, access control và transport security.

### GET không dùng cho thao tác thay đổi trạng thái

Không thực hiện hành động như đổi email, xóa tài khoản, thanh toán hoặc reset password qua GET. GET có thể bị prefetch, crawler, link scanner hoặc browser mở lại.

Dùng method có semantics phù hợp, thường là POST/PATCH/DELETE, kèm xác thực, authorization và CSRF defense nếu dùng cookie.

### Pattern Post/Redirect/Get

Sau khi xử lý POST thành công, server có thể trả redirect để browser điều hướng tới URL sạch:

    POST /checkout/confirm
          |
          v
    Server xử lý và lưu kết quả
          |
          v
    303 See Other
    Location: /orders/123/confirmation
          |
          v
    GET /orders/123/confirmation

Redirect giúp tránh gửi lại form khi reload và giữ dữ liệu POST ngoài URL. Không dùng query trong Location để đưa token hoặc dữ liệu cá nhân vào trang đích.

## 5. Thay dữ liệu nhạy cảm bằng server-side state

Thay vì mang toàn bộ trạng thái hoặc credential trong URL, lưu trạng thái nhạy cảm phía server và dùng session identifier phù hợp.

Ví dụ:

1. Browser gửi dữ liệu qua POST tới server.
2. Server xác thực, kiểm tra quyền và lưu trạng thái.
3. Server gắn trạng thái với session hoặc một reference ngẫu nhiên có giới hạn.
4. Browser được redirect tới URL sạch.
5. Trang đích đọc dữ liệu từ server sau khi xác thực.

### Session cookie

Với ứng dụng web dùng session, cookie nên được cấu hình theo nhu cầu:

    Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax

Ví dụ này cần được điều chỉnh theo domain, kiến trúc và luồng xác thực thực tế. Cookie __Host- phải dùng Secure, Path=/ và không có Domain attribute.

Session ID nên là giá trị opaque ngẫu nhiên, không chứa thông tin người dùng hoặc quyền ở dạng đọc được. Server giữ trạng thái và có khả năng revoke/rotate.

### Opaque reference

Nếu cần URL để mở một tài nguyên tạm thời, có thể dùng reference ngẫu nhiên:

    /share/7a4c...opaque-reference

Nhưng reference này có thể hoạt động như bearer capability. Cần:

- Entropy đủ cao.
- Phạm vi quyền hẹp.
- TTL phù hợp.
- Khả năng revoke.
- Giới hạn số lần sử dụng nếu cần.
- Không cho phép truy cập tài nguyên khác qua IDOR.
- Không ghi raw reference vào log nếu nó cấp quyền.

Nếu URL bị lộ, người khác có thể sử dụng reference trong thời gian còn hiệu lực. Opaque không đồng nghĩa với vô hại.

## 6. Referrer-Policy kiểm soát dữ liệu được gửi đi

Referrer-Policy quy định lượng thông tin browser gửi trong header Referer khi tải tài nguyên hoặc điều hướng. Nó là một biện pháp quan trọng để giảm URL leakage.

Header HTTP:

    Referrer-Policy: strict-origin-when-cross-origin

Đây là policy mặc định phổ biến của các browser hiện đại, nhưng ứng dụng nên khai báo rõ để chính sách không phụ thuộc giả định về mặc định.

### Các directive thường gặp

| Directive | Cùng origin | Cross-origin | HTTPS xuống HTTP |
| --- | --- | --- | --- |
| no-referrer | Không gửi | Không gửi | Không gửi |
| same-origin | Gửi full URL | Không gửi | Không gửi |
| origin | Chỉ gửi origin | Chỉ gửi origin | Chỉ gửi origin |
| strict-origin | Chỉ gửi origin | Chỉ gửi origin | Không gửi |
| origin-when-cross-origin | Full URL | Chỉ origin | Chỉ origin |
| strict-origin-when-cross-origin | Full URL | Chỉ origin | Không gửi |
| no-referrer-when-downgrade | Full URL | Full URL | Không gửi |
| unsafe-url | Full URL | Full URL | Full URL |

Full URL trong bảng có thể chứa path và query nhưng không bao gồm fragment hoặc user information.

### no-referrer

Không gửi Referer:

    Referrer-Policy: no-referrer

Phù hợp với trang chứa dữ liệu nhạy cảm, trang callback hoặc luồng reset token khi không cần referrer. Cần kiểm tra yêu cầu nghiệp vụ và analytics trước khi áp dụng.

### same-origin

Chỉ gửi referrer khi request cùng origin. Cross-origin request không nhận Referer.

Policy này hữu ích khi muốn giữ referrer nội bộ nhưng không tiết lộ URL nội bộ cho website khác.

### strict-origin-when-cross-origin

Với request cùng origin, browser có thể gửi full URL. Với cross-origin, chỉ gửi origin. Khi downgrade từ HTTPS xuống HTTP, không gửi referrer.

Policy này giảm rò rỉ path/query sang origin khác nhưng không bảo vệ query nhạy cảm trong request cùng origin. Nếu trang hiện tại có secret trong URL, request same-origin vẫn có thể làm full URL xuất hiện trong Referer.

### unsafe-url

unsafe-url có thể gửi full URL kể cả khi điều hướng từ HTTPS xuống HTTP. Không dùng cho trang có dữ liệu nhạy cảm. Nó có thể tiết lộ path và query cho origin đích.

## 7. Đặt Referrer-Policy ở đâu?

### HTTP response header

Khuyến nghị cấu hình ở server:

    Referrer-Policy: strict-origin-when-cross-origin

Hoặc policy chặt hơn cho trang nhạy cảm:

    Referrer-Policy: no-referrer

Header áp dụng cho document và các request do document khởi tạo theo quy tắc của browser. Có thể cấu hình policy tổng thể ở server và policy chặt hơn ở các route nhạy cảm.

### Meta element

Có thể khai báo trong head:

    <meta name="referrer" content="no-referrer">

Meta hữu ích khi không thể chỉnh header ngay, nhưng HTTP response header là vị trí quản trị rõ ràng hơn. Đặt meta sớm trong head, trước các resource hoặc navigation có thể phát sinh.

### Thuộc tính referrerpolicy

Một số element hỗ trợ thuộc tính referrerpolicy:

    <a
      href="https://external.example.test/"
      referrerpolicy="no-referrer">
      Mở trang bên ngoài
    </a>

Với link không cần gửi referrer, có thể dùng:

    <a
      href="https://external.example.test/"
      rel="noreferrer">
      Mở trang bên ngoài
    </a>

rel="noreferrer" ngăn gửi referrer và có hành vi tương đương noopener đối với liên kết đó. Nó hữu ích khi mở nội dung bên ngoài trong tab mới.

### Fetch API

Có thể chỉ định referrerPolicy cho một request:

    fetch("/api/status", {
      method: "GET",
      referrerPolicy: "no-referrer"
    });

Không phải mọi API hoặc mọi request đều cho phép ứng dụng tùy ý đặt Referer header. Browser kiểm soát header này; dùng Referrer-Policy thay vì cố tự set Referer.

### document.referrer

Trang đích có thể đọc document.referrer, nhưng giá trị phụ thuộc policy và ngữ cảnh navigation. Nó có thể là full URL, chỉ origin hoặc chuỗi rỗng.

Không dùng document.referrer làm bằng chứng xác thực hoặc nguồn dữ liệu bắt buộc. Người dùng có thể truy cập trực tiếp, policy có thể ẩn referrer và browser có thể thay đổi hành vi.

## 8. Referrer-Policy không xóa URL ở mọi nơi

Referrer-Policy chỉ kiểm soát referrer browser gửi theo request/navigation. Nó không:

- Xóa URL khỏi browser history.
- Xóa query khỏi access log đã ghi.
- Ngăn server nhận path/query của request trực tiếp.
- Ngăn script cùng trang đọc location.href.
- Ngăn extension hoặc công cụ endpoint ghi nhận URL.
- Tự redaction analytics hoặc APM.
- Xóa URL khỏi clipboard, screenshot hoặc ticket hỗ trợ.
- Ngăn ứng dụng chủ động gửi URL qua fetch/beacon.

Vì vậy, hãy loại bỏ secret khỏi URL trước khi cần dựa vào Referrer-Policy. Policy là lớp giảm lan truyền, không phải cách làm sạch nguồn dữ liệu.

### Redirect không tự xóa dữ liệu đã lộ

Nếu URL đầu tiên chứa token rồi server redirect sang URL sạch, token vẫn có thể đã xuất hiện trong:

- Request log của URL đầu tiên.
- Browser history hoặc telemetry.
- Referrer theo policy của request tiếp theo.
- Error report hoặc trace.

Redirect chỉ thay URL hiện tại hoặc tạo request tiếp theo. Nó không thu hồi bản sao đã được ghi nhận.

## 9. OAuth và OIDC callback: ngoại lệ cần xử lý cẩn thận

OAuth Authorization Code Flow thường trả authorization code và state về redirect URI qua query string, tùy response mode. Đây là một ngoại lệ có chủ đích của protocol, không có nghĩa có thể đặt access token hoặc refresh token trong URL.

Ví dụ callback:

    https://app.example.test/oauth/callback?code=SHORT_LIVED_CODE&state=RANDOM_STATE

### Bảo vệ authorization code

- Dùng Authorization Code Flow.
- Với public client như SPA, dùng PKCE.
- Dùng state chống CSRF và liên kết với giao dịch đăng nhập đã khởi tạo.
- Dùng redirect URI khớp chính xác với URI đã đăng ký.
- Code phải ngắn hạn, dùng một lần và gắn với client/redirect URI theo protocol.
- Xác minh state trước khi hoàn tất luồng.
- Không ghi code hoặc state thô vào log/analytics.
- Không tải third-party script không cần thiết trên callback page.
- Đổi code lấy token qua kênh phù hợp rồi điều hướng tới URL sạch.

### Không đặt access token trong query

Không dùng implicit-style URL như:

    https://app.example.test/callback?access_token=LONG_LIVED_TOKEN

Bearer token trong URL có thể bị lộ qua history, log và referrer. Dùng flow hiện đại phù hợp với OAuth security best practice.

### Làm sạch callback URL

Sau khi đã lưu state cần thiết và xử lý callback an toàn, ứng dụng có thể thay URL hiện tại bằng route sạch:

    history.replaceState(
      null,
      "",
      "/dashboard"
    );

Trong SPA, chỉ gọi sau khi đã đọc và xử lý callback cần thiết. Việc này giảm việc token/code còn hiển thị trong thanh địa chỉ và history entry hiện tại.

replaceState không xóa request đã tới server, log, APM, screenshot hoặc telemetry đã thu thập trước đó. Server callback vẫn phải redaction query ngay tại lớp log.

### Callback page nên tối giản

Trang callback nên:

- Trả Referrer-Policy: no-referrer.
- Không tải analytics, quảng cáo hoặc script bên thứ ba.
- Không hiển thị code/state ra DOM.
- Không đưa query vào error message.
- Không redirect tới URL do query parameter tùy ý chỉ định.
- Xử lý lỗi bằng mã lỗi chung và correlation ID.

Nếu dùng BFF, server có thể nhận callback, đổi code ở backend, tạo session cookie rồi redirect browser tới URL sạch. Cách này giảm việc access token đi qua JavaScript browser.

## 10. Reset-password và invitation link

Một số luồng email cần link có token để chứng minh người nhận sở hữu email hoặc cho phép đặt lại mật khẩu. Token trong URL là một capability nhạy cảm nên phải giới hạn rủi ro.

Ví dụ:

    https://app.example.test/reset-password?token=ONE_TIME_SECRET

Nếu thiết kế buộc phải dùng token trong link:

- Token có entropy cao và chỉ dùng một lần.
- TTL ngắn, giới hạn đúng mục đích.
- Lưu hash token phía server nếu phù hợp.
- Ràng buộc token với user và hành động.
- Có thể revoke token khi tạo token mới hoặc đổi mật khẩu.
- Không ghi query vào access log, APM hoặc analytics.
- Trang reset trả Referrer-Policy: no-referrer.
- Không tải ảnh, script, font hoặc widget bên thứ ba không cần thiết.
- Không đưa token vào URL redirect tiếp theo.

### Không tiêu thụ token chỉ bằng GET

Email security scanner, link preview hoặc gateway có thể tự động truy cập URL trước khi người dùng bấm. Nếu GET ngay lập tức tiêu thụ token, link có thể bị vô hiệu hóa trước khi người dùng thật mở.

Một thiết kế thường dùng:

1. GET mở trang xác nhận và kiểm tra sơ bộ token nhưng chưa thực hiện thay đổi mật khẩu.
2. Trang hiển thị form yêu cầu người dùng chủ động nhập mật khẩu mới.
3. POST gửi token cùng dữ liệu thay đổi.
4. Server xác minh token, session/CSRF theo thiết kế và tiêu thụ token một lần trong transaction.
5. Server revoke các session phù hợp và redirect tới URL sạch.

Không dùng GET để thay đổi mật khẩu, xác nhận thanh toán hoặc thực hiện hành động nhạy cảm.

### Giảm thời gian token nằm trên trang

Trang reset nên dùng policy no-referrer và không có third-party script. Có thể thay URL hiện tại bằng route sạch sau khi đã giữ token trong luồng xử lý cần thiết, nhưng phải bảo đảm form POST vẫn có thể gửi token an toàn.

Không để token trong localStorage hoặc analytics. Không đưa token vào DOM text hoặc error report.

## 11. URL parameter và open redirect

Một endpoint thường nhận URL đích từ query:

    /redirect?next=https://external.example.test/

Nếu server điều hướng tới URL tùy ý, attacker có thể tạo open redirect. Redirect này có thể được dùng để lừa người dùng, làm rò rỉ code/token qua callback sai hoặc tạo chuỗi chuyển hướng khó kiểm soát.

### Dùng allowlist route

Ưu tiên map một key nội bộ sang route:

    const destinations = {
      dashboard: "/dashboard",
      orders: "/orders"
    };

    const key = new URL(location.href).searchParams.get("next");
    const destination = destinations[key] ?? "/dashboard";

Nếu cần chấp nhận URL, parse bằng URL API và kiểm tra origin chính xác:

    const target = new URL(candidate, location.origin);

    if (target.origin !== location.origin) {
      throw new Error("External redirect is not allowed");
    }

Không dùng kiểm tra chuỗi như startsWith("/") một cách đơn giản mà không xử lý backslash, encoding và URL parser behavior. Tốt nhất dùng identifier route nội bộ thay vì nhận URL tùy ý.

### Không đưa token vào redirect target

Không nối query chứa access token, session ID hoặc reset token vào Location header. Nếu cần truyền state qua bước điều hướng, lưu server-side hoặc dùng reference ngắn hạn có kiểm soát.

## 12. Làm sạch URL ở browser đúng cách

### URLSearchParams

Khi cần tạo query cho dữ liệu không nhạy cảm, dùng URLSearchParams:

    const url = new URL("/catalog", location.origin);
    url.searchParams.set("category", "books");
    url.searchParams.set("page", "2");

    location.assign(url);

URLSearchParams giúp encode parameter đúng cách và tránh nối chuỗi thủ công. Nó không làm dữ liệu trở nên bí mật.

### history.replaceState()

Sau khi xử lý một query tạm thời, có thể thay URL hiện tại:

    const url = new URL(location.href);
    url.searchParams.delete("campaign");
    url.searchParams.delete("temporary_code");

    history.replaceState(
      history.state,
      "",
      url.pathname + url.search + url.hash
    );

Chỉ giữ lại các parameter cần thiết. Nếu route có state mà ứng dụng cần, lưu state an toàn trước khi thay URL.

### replaceState có giới hạn

replaceState:

- Thay URL của history entry hiện tại.
- Không tạo navigation request mới.
- Không xóa server log hoặc proxy log đã ghi.
- Không thu hồi URL đã sao chép hoặc gửi trong Referer.
- Không xóa dữ liệu mà script khác đã đọc.
- Không bảo đảm xóa bản sao đã đồng bộ hoặc ghi vào telemetry.

Vì vậy, làm sạch URL là biện pháp giảm phơi bày về sau. Thiết kế ban đầu vẫn phải tránh đặt secret vào URL.

### Không dùng location.hash như kho bí mật

Fragment không được gửi trong HTTP request thông thường, nhưng script cùng origin đọc được và browser lưu nó trong history. Một số SDK có thể đọc toàn bộ location.href. Không đặt token dài hạn hoặc dữ liệu cá nhân trong fragment.

## 13. Redaction tại server, proxy và observability

Ứng dụng cần biết những lớp nào đang ghi URL:

    Browser
      |
      v
    CDN / WAF
      |
      v
    Reverse proxy / Load balancer
      |
      v
    Web server
      |
      v
    Application
      |
      +--> APM / tracing
      +--> Analytics
      +--> Error reporting

Mỗi lớp có thể lưu request URL hoặc query parameter.

### Access log

Không log raw query cho mọi endpoint nếu query có thể chứa dữ liệu nhạy cảm. Chọn format log chỉ gồm:

- Method.
- Route template hoặc normalized path.
- Status code.
- Duration.
- Correlation ID.
- User/tenant pseudonymous identifier khi cần.

Ví dụ thay vì log:

    GET /reset-password?token=ONE_TIME_SECRET

hãy log:

    GET /reset-password [query_redacted]

Hoặc dùng route template và ghi nhận rằng request có query mà không lưu giá trị.

### Redaction theo allowlist

Ưu tiên chỉ log những query parameter được phép, ví dụ page hoặc category. Các parameter khác bị loại bỏ hoặc redact mặc định.

Không chỉ dựa vào denylist tên như token, password hoặc secret vì attacker/developer có thể dùng tên khác như key, code, auth, session, credential hoặc dữ liệu nhạy cảm trong path.

### Path cũng có thể nhạy cảm

Ví dụ:

    /users/alice@example.test/invoices/123

Email trong path có thể xuất hiện trong log và referrer. Dùng route template:

    /users/:userId/invoices/:invoiceId

Log ID đã pseudonymize hoặc route template nếu không cần giá trị thật.

### APM và distributed tracing

Kiểm tra các thuộc tính như http.url, url.full, url.query, request.target và span name. Tên field thay đổi theo agent và chuẩn telemetry.

Redact ở collector hoặc instrumentation trước khi dữ liệu được gửi tới vendor. Chỉ redact ở dashboard là quá muộn nếu raw URL đã được ingest và lưu trữ.

### Analytics và error reporting

Không gửi location.href nguyên vẹn nếu query có thể chứa secret hoặc PII. Tạo page identifier từ route template:

    /orders/:orderId

thay vì:

    /orders/123?customerEmail=alice@example.test

Với SPA, kiểm tra cả page_view, route_change, exception context, breadcrumbs và replay tool.

### Kiểm soát retention và truy cập

Khi URL nhạy cảm đã được log:

- Giới hạn người có thể truy cập log.
- Rút ngắn retention nếu phù hợp.
- Xóa hoặc redact bản sao theo quy trình quản trị dữ liệu.
- Kiểm tra bản sao ở CDN, backup, archive và vendor.
- Revoke credential nếu URL chứa secret có thể sử dụng.

## 14. Cache và URL nhạy cảm

Query string thường là một phần của cache key. Nếu URL chứa dữ liệu riêng tư, cache có thể lưu response theo key đó hoặc chia sẻ sai giữa người dùng nếu cấu hình cache key không đúng.

Với response nhạy cảm:

    Cache-Control: no-store

no-store yêu cầu cache HTTP không lưu response theo quy tắc HTTP caching. Nó không xóa request URL khỏi access log, history hoặc APM.

Không dựa vào query token để phân tách cache. Nếu response phụ thuộc session hoặc Authorization, hãy thiết kế cache policy và cache key rõ ràng; tránh shared cache cho response cá nhân hóa khi chưa có bảo đảm phân tách.

### Redirect response

Redirect chứa Location có thể mang dữ liệu nhạy cảm nếu ứng dụng nối query vào URL đích. Kiểm tra cả response 301, 302, 303, 307 và 308 trong Network; đừng chỉ kiểm tra URL cuối.

## 15. Các header và cơ chế hỗ trợ

### Referrer-Policy

Giảm thông tin trang nguồn được gửi sang request tiếp theo:

    Referrer-Policy: strict-origin-when-cross-origin

Với trang callback hoặc trang xử lý secret:

    Referrer-Policy: no-referrer

### Cache-Control

Với response chứa dữ liệu nhạy cảm:

    Cache-Control: no-store

### Content Security Policy

Giới hạn script và endpoint để giảm nguy cơ SDK không mong muốn đọc URL rồi gửi ra ngoài:

    Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self'

Policy thực tế phải phù hợp tài nguyên cần dùng; ví dụ chỉ minh họa một cấu hình chặt.

CSP không ngăn browser history hoặc server access log lưu URL. Nó giúp giới hạn một số đường script exfiltration.

### X-Content-Type-Options và security headers khác

Các header bảo mật khác vẫn quan trọng cho ứng dụng, nhưng không trực tiếp xóa URL khỏi log/referrer. Hãy xác định rõ mục tiêu từng header, tránh kỳ vọng một header xử lý mọi loại leakage.

## 16. Kiểm thử URL leak bằng DevTools

Thực hiện trên local/staging với dữ liệu giả. Không đưa token production vào URL để kiểm tra.

### Bước 1 — Kiểm tra URL và Network

1. Mở DevTools → Network.
2. Thực hiện luồng đăng nhập, tìm kiếm, reset hoặc callback test.
3. Kiểm tra Request URL, query string và redirect chain.
4. Kiểm tra request body riêng biệt.
5. Xác nhận không có access token, refresh token, session ID hoặc PII không cần thiết trong URL.

### Bước 2 — Kiểm tra Referer

1. Tạo trang test có path/query giả, không chứa secret thật.
2. Từ trang đó tải một tài nguyên same-origin và một tài nguyên cross-origin do bạn kiểm soát.
3. Quan sát Request Headers → Referer.
4. Thử các policy strict-origin-when-cross-origin, same-origin và no-referrer.
5. Kiểm tra document.referrer ở trang đích.

Kết quả cần đối chiếu theo scheme, origin và downgrade. Đừng chỉ nhìn một trường hợp cùng origin rồi kết luận cross-origin cũng được bảo vệ.

### Bước 3 — Kiểm tra history và replaceState

1. Mở route test có query không nhạy cảm.
2. Xử lý query bằng ứng dụng.
3. Gọi history.replaceState() để xóa parameter tạm.
4. Kiểm tra thanh địa chỉ và history entry hiện tại.
5. Xác nhận thao tác không xóa request/log đã được tạo trước đó.

### Bước 4 — Kiểm tra log và telemetry

1. Gửi request test có query marker giả như test_marker=URL_LEAK_CHECK.
2. Kiểm tra CDN/WAF/proxy/web server log.
3. Kiểm tra APM span và analytics event.
4. Xác nhận marker được redact hoặc chỉ route template được lưu.
5. Kiểm tra error report không chứa full URL.

### Bước 5 — Kiểm tra OAuth/reset callback

1. Dùng authorization code và reset token giả trong staging.
2. Xác nhận callback page không tải third-party script.
3. Kiểm tra Referrer-Policy.
4. Kiểm tra query không được ghi vào log.
5. Xác nhận token/code không bị tiêu thụ chỉ bởi GET preview.
6. Sau xử lý, xác nhận redirect tới URL sạch.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Query không nhạy cảm | page=2, category=books | URL có thể giữ để bookmark |
| Secret trong query | Token giả trong query | Bị loại bỏ khỏi thiết kế hoặc bị từ chối |
| Secret trong path | Email/user identifier trong path | Route/log được chuẩn hóa hoặc pseudonymize |
| HTTPS same-origin referrer | Policy strict-origin-when-cross-origin | Có thể gửi full URL cùng origin |
| HTTPS cross-origin referrer | Policy strict-origin-when-cross-origin | Chỉ gửi origin |
| HTTPS xuống HTTP | Policy strict-origin-when-cross-origin | Không gửi referrer |
| no-referrer | Navigation/request từ trang nhạy cảm | Không có Referer |
| unsafe-url | Môi trường test riêng | Quan sát nguy cơ gửi full URL; không dùng production |
| Fragment | Giá trị sau dấu # | Không gửi trong HTTP request thông thường, nhưng script đọc được |
| replaceState | Xóa query sau callback | Thanh địa chỉ sạch; log trước đó vẫn tồn tại |
| OAuth callback | Code/state giả | Code ngắn hạn, một lần; log redacted; URL sạch sau xử lý |
| Reset link scanner | GET preview | Không tiêu thụ token hoặc thay đổi mật khẩu |
| POST body | Dữ liệu test trong body | Không xuất hiện trong URL; body log vẫn được kiểm soát |
| Access log | Query marker test | Giá trị nhạy cảm bị redact |
| APM/analytics | Route có query marker | Không ingest raw query nếu không cần |
| Sensitive response cache | Response riêng tư | Cache-Control no-store |
| Open redirect | next trỏ tới origin ngoài allowlist | Server từ chối hoặc dùng route key nội bộ |

## 17. Xử lý sự cố khi URL đã chứa secret

Nếu phát hiện token, password-reset code hoặc session identifier trong URL:

1. Xác định URL, loại dữ liệu, thời gian tồn tại và nơi đã xuất hiện.
2. Revoke session/token hoặc vô hiệu hóa one-time link nếu credential còn sử dụng được.
3. Kiểm tra access log, proxy, CDN, WAF, APM, analytics, error report và backup.
4. Giới hạn quyền truy cập log và kích hoạt quy trình xóa/redact bản sao theo chính sách.
5. Sửa endpoint để không phát hành secret trong URL hoặc giảm TTL/phạm vi nếu protocol yêu cầu.
6. Đặt Referrer-Policy phù hợp và loại third-party script khỏi trang nhạy cảm.
7. Cập nhật log redaction ở mọi lớp trước khi dữ liệu tiếp tục được ingest.
8. Kiểm tra redirect chain, cache key và response cache policy.
9. Thêm regression test cho URL, Referer và log.
10. Đánh giá liệu credential đã bị sử dụng trái phép hay dữ liệu cá nhân đã được chia sẻ ngoài phạm vi.

Không chỉ xóa query trên browser rồi kết luận sự cố đã được xử lý. Bản sao trong log, history sync, telemetry hoặc hệ thống vendor có thể vẫn tồn tại.

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ HTTPS làm URL bí mật | URL vẫn xuất hiện ở browser và endpoint kết thúc TLS | Không đặt secret trong URL |
| Chỉ tránh query nhưng để secret trong path | Path vẫn có thể được log và gửi trong Referer | Loại secret khỏi cả path và query |
| Chuyển token sang fragment rồi coi là an toàn | Script/history vẫn có thể đọc fragment | Không dùng URL làm kho token |
| Nghĩ POST body không thể bị log | Proxy/APM có thể capture body | Redact body và bảo vệ telemetry |
| Dùng GET để thay đổi trạng thái | Prefetch/crawler có thể kích hoạt hành động | Dùng POST/PATCH/DELETE và CSRF defense |
| Chỉ cấu hình Referrer-Policy ở trang đích | Request đã rời trang nguồn theo policy khác | Cấu hình policy trên document nguồn |
| Dùng strict-origin-when-cross-origin rồi giữ secret trong query | Same-origin request có thể gửi full URL trong Referer | Loại secret khỏi URL hoặc dùng no-referrer |
| Dùng unsafe-url | Tiết lộ full URL kể cả khi downgrade | Dùng policy chặt hơn |
| Nghĩ no-referrer xóa history và log | Chỉ header Referer bị kiểm soát | Redact log và tránh URL secret ngay từ đầu |
| Gọi replaceState rồi nghĩ secret đã biến mất | Log/telemetry trước đó vẫn có thể lưu | Redact ở server và rút ngắn thời gian phơi bày |
| Chỉ redact ở dashboard | Raw URL đã được ingest vào APM | Redact trước khi gửi/ingest |
| Chỉ dùng denylist tên parameter | Secret có thể nằm dưới tên khác hoặc path | Allowlist field log và route template |
| Dùng reset link GET để đổi password | Scanner có thể tiêu thụ link | GET chỉ hiển thị; POST xác nhận hành động |
| Tin UUID là access control | Người có URL vẫn có thể truy cập | Xác thực, authorization, TTL và revoke |
| Redirect tới URL do query quyết định | Open redirect và rò rỉ code/token | Allowlist route hoặc exact origin |
| Không kiểm tra URL của analytics SDK | Query/PII có thể gửi sang bên thứ ba | Audit page_view, breadcrumbs và error context |

## 19. Câu hỏi củng cố

**Câu 1.** Vì sao không nên đặt access token trong query string?

**Giải đáp:** Query có thể xuất hiện trong history, Referer, access log, proxy, APM, analytics và các bản sao người dùng chia sẻ. Token có thể bị sử dụng nếu còn hiệu lực.

**Câu 2.** Fragment có được gửi trong HTTP request không?

**Giải đáp:** Fragment thông thường không được gửi tới server, nhưng JavaScript cùng trang và browser history vẫn có thể đọc/lưu nó. Không dùng fragment làm kho bí mật.

**Câu 3.** Referrer-Policy no-referrer làm gì?

**Giải đáp:** Ngăn browser gửi Referer cho request/navigation chịu policy đó. Nó không xóa history, log hoặc dữ liệu script đã thu thập.

**Câu 4.** strict-origin-when-cross-origin có gửi full URL không?

**Giải đáp:** Có thể gửi full URL cho request cùng origin; chỉ gửi origin cho cross-origin và không gửi khi downgrade HTTPS xuống HTTP.

**Câu 5.** POST có bảo đảm request body không bị log không?

**Giải đáp:** Không. Proxy, WAF, server hoặc APM có thể capture body nếu cấu hình. Cần redaction và TLS.

**Câu 6.** history.replaceState() có xóa token khỏi access log không?

**Giải đáp:** Không. Nó chỉ thay URL của history entry hiện tại ở browser, không xóa request hoặc bản sao đã ghi.

**Câu 7.** Vì sao reset-password link không nên tiêu thụ token ngay ở GET?

**Giải đáp:** Email scanner hoặc link preview có thể tự truy cập URL. Dùng GET để hiển thị trang và POST có chủ ý để tiêu thụ token/thay đổi trạng thái.

**Câu 8.** OAuth callback có thể chứa authorization code trong query không?

**Giải đáp:** Có thể theo Authorization Code Flow, nhưng code phải ngắn hạn, dùng một lần, bảo vệ bằng state/PKCE và được đổi lấy token an toàn; không đưa access token dài hạn vào URL.

**Câu 9.** Vì sao phải redact ở CDN/proxy/APM?

**Giải đáp:** Những lớp này có thể ghi URL trước khi request tới ứng dụng. Redact chỉ ở dashboard là quá muộn nếu raw data đã được ingest.

**Câu 10.** UUID khó đoán có thay thế authorization không?

**Giải đáp:** Không. Nếu ai có UUID cũng truy cập được thì nó vẫn là capability. Server phải xác thực và kiểm tra quyền.

## 20. Tổng kết

URL thường được lưu và truyền qua browser history, Referer, server log, proxy, CDN, APM, analytics và các hệ thống hỗ trợ. Path và query thường được gửi tới server; fragment không được gửi trong HTTP request thông thường nhưng vẫn có thể bị JavaScript và browser history đọc. Không đặt password, access/refresh token, session ID, OTP hoặc dữ liệu cá nhân nhạy cảm trong URL.

Hãy dùng GET cho truy vấn không nhạy cảm, POST cho dữ liệu cần gửi trong body và server-side state cho trạng thái nhạy cảm. POST không tự bảo vệ body khỏi log hoặc XSS. Dùng Referrer-Policy phù hợp, thường là strict-origin-when-cross-origin cho ứng dụng thông thường và no-referrer cho callback/reset page nhạy cảm. Policy này giảm Referer nhưng không xóa history hoặc log.

Với OAuth/OIDC callback và reset link, giới hạn TTL, dùng một lần, xác minh state/PKCE, tránh third-party script, redaction query và redirect tới URL sạch sau khi xử lý. Cấu hình redaction tại CDN, proxy, server, APM và analytics; kiểm tra cả path, query, redirect chain và request body. history.replaceState() chỉ làm sạch URL hiển thị ở browser, không thu hồi bản sao đã ghi trước đó.

## Tài liệu tham khảo

1. [W3C — Referrer Policy](https://www.w3.org/TR/referrer-policy/): thuật toán và các policy kiểm soát Referer.
2. [MDN — Referrer-Policy HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): directive, ví dụ và cách triển khai.
3. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics của method, request target, Referer và response.
4. [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): authorization code flow, redirect URI và token endpoint.
5. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành OAuth security hiện hành và giảm token leakage.
6. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): state, nonce, ID token và callback flow.
7. [OWASP — Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url): rủi ro lộ thông tin qua query string.
8. [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): thiết kế reset link và token đặt lại mật khẩu.
