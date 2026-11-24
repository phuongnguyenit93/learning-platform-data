# Browser fingerprinting: nhận diện trình duyệt qua các tín hiệu kỹ thuật

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích browser fingerprinting và phân biệt nó với cookie, session và đăng nhập.
2. Phân biệt fingerprinting thụ động với fingerprinting chủ động.
3. Nhận diện các nhóm tín hiệu như HTTP headers, user agent, màn hình, ngôn ngữ, font, canvas, WebGL, audio và đặc điểm thiết bị.
4. Giải thích entropy, uniqueness, stability và linkability của một fingerprint.
5. Hiểu vì sao fingerprint thường mang tính xác suất và có thể thay đổi theo thời gian.
6. Đánh giá rủi ro theo dõi xuyên site, ghép nối dữ liệu và phân loại nhầm người dùng.
7. Hiểu giới hạn của private browsing, xóa cookie, VPN và đổi IP.
8. Áp dụng các biện pháp giảm fingerprinting ở browser và trong thiết kế ứng dụng.
9. Cân bằng mục tiêu chống gian lận với quyền riêng tư, tính minh bạch và giảm thu thập dữ liệu.
10. Kiểm tra các bề mặt fingerprinting bằng DevTools và quy trình audit có kiểm soát.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Fingerprinting liên quan đến quyền riêng tư vì một website có thể kết hợp nhiều tín hiệu từ browser, thiết bị và mạng để nhận diện hoặc liên kết hoạt động của một trình duyệt, kể cả khi cookie bị xóa.

## 1. Browser fingerprinting là gì?

Browser fingerprinting là kỹ thuật thu thập và kết hợp các đặc điểm mà browser hoặc thiết bị để lộ để tạo ra một tập tín hiệu nhận diện. Tập tín hiệu đó có thể giúp một website hoặc hệ thống phân tích suy đoán một trình duyệt có giống lần truy cập trước hay không.

Các tín hiệu có thể gồm:

- User-Agent hoặc User-Agent Client Hints.
- Ngôn ngữ, locale và timezone.
- Kích thước màn hình, viewport, độ sâu màu và pixel ratio.
- Hệ điều hành, kiến trúc CPU và số logical processors mà browser công khai.
- Khả năng hỗ trợ API, codec và feature của browser.
- Font, canvas rendering và WebGL behavior.
- Audio processing và một số khác biệt trong rendering.
- Đặc điểm mạng hoặc IP mà server quan sát được.

Không có một trường đơn lẻ nào nhất thiết xác định duy nhất một người. Giá trị fingerprint đến từ việc kết hợp nhiều tín hiệu, so sánh chúng với dữ liệu đã quan sát và đánh giá khả năng hai lần truy cập thuộc cùng một browser.

### Fingerprint không phải cookie

Cookie là dữ liệu browser lưu và gửi theo domain, path, expiry, SameSite và các quy tắc cookie. Fingerprint được suy ra từ các tín hiệu browser/device/network; nó có thể được tính lại mà không cần một cookie định danh.

| Cơ chế | Cách nhận diện | Có thể mất khi xóa cookie? |
| --- | --- | --- |
| Session cookie | Giá trị session do server cấp | Thường có thể mất nếu cookie đó bị xóa hoặc hết hạn |
| Persistent cookie | Identifier được lưu trong browser | Có thể mất khi xóa cookie/site data |
| Local storage identifier | Giá trị do ứng dụng lưu theo origin | Có thể mất khi xóa site data |
| Browser fingerprint | Kết hợp tín hiệu browser, thiết bị và mạng | Không nhất thiết; tín hiệu có thể vẫn còn |

Xóa cookie có thể loại bỏ một số identifier trực tiếp nhưng không bảo đảm browser trở nên không thể liên kết.

### Fingerprint không phải xác thực

Fingerprint không phải password, session token hoặc bằng chứng mật mã về danh tính. Nhiều người có thể có fingerprint tương tự; cùng một người cũng có thể tạo ra fingerprint khác khi đổi browser, thiết bị, màn hình, mạng hoặc cài đặt privacy.

Không dùng fingerprint làm yếu tố xác thực duy nhất, không dùng nó để thay MFA và không coi fingerprint match là bằng chứng chắc chắn người dùng là chủ tài khoản.

## 2. Fingerprinting thụ động và chủ động

### Passive fingerprinting

Passive fingerprinting sử dụng thông tin server nhận được trong quá trình kết nối bình thường, không cần trang chạy thêm nhiều API để dò thiết bị.

Ví dụ:

- IP address và thông tin mạng do server quan sát.
- HTTP request headers như Accept-Language.
- User-Agent hoặc Client Hints nếu browser gửi.
- TLS handshake characteristics ở tầng hạ tầng.
- Một số metadata của request hoặc giao thức.

Passive fingerprinting có thể diễn ra ở reverse proxy, CDN, load balancer hoặc server trước khi JavaScript của trang chạy.

### Active fingerprinting

Active fingerprinting chủ động gọi API hoặc thực hiện thao tác rendering để quan sát khác biệt:

- Đọc navigator.language, navigator.languages hoặc screen dimensions.
- Kiểm tra sự tồn tại và hành vi của browser APIs.
- Vẽ canvas rồi quan sát pixel output.
- Khởi tạo WebGL và truy vấn khả năng rendering.
- Dùng Web Audio API để quan sát khác biệt xử lý âm thanh.
- Kiểm tra font hoặc cách browser render text.
- Đọc các đặc điểm thiết bị mà browser cho phép truy cập.

Một trang có thể kết hợp nhiều phép đo nhỏ thành một vector đặc trưng. API được gọi và giá trị trả về phụ thuộc browser, phiên bản, quyền, policy và chế độ privacy.

### Kết hợp passive và active

Server có thể kết hợp IP/header với dữ liệu JavaScript gửi lên. Nếu nhiều bên cùng thu thập hoặc chia sẻ dữ liệu, khả năng liên kết hoạt động giữa các website có thể tăng lên.

Không nên giả định fingerprinting chỉ xảy ra ở JavaScript. Một số tín hiệu xuất hiện ở tầng HTTP/TLS hoặc được thu thập từ SDK và script bên thứ ba.

## 3. Các tín hiệu browser thường bị kết hợp

### User-Agent và Client Hints

User-Agent từng cung cấp nhiều chi tiết về browser, engine, hệ điều hành và thiết bị. Các browser hiện đại có thể giảm độ chi tiết hoặc chuẩn hóa một số thành phần để hạn chế passive fingerprinting.

User-Agent Client Hints cung cấp một số thông tin theo cơ chế có kiểm soát hơn, có thể gồm browser brand, platform hoặc thông tin thiết bị bổ sung khi được yêu cầu và browser cho phép.

Ứng dụng nên:

- Chỉ yêu cầu Client Hints thật sự cần cho chức năng.
- Không thu thập thông tin model/version chi tiết để nhận diện nếu không có mục đích hợp lệ.
- Không dựa vào User-Agent để quyết định quyền truy cập hoặc xác thực.
- Dùng feature detection thay cho suy luận browser identity khi kiểm tra khả năng API.

### Ngôn ngữ, locale và timezone

Các giá trị như navigator.language, navigator.languages, Intl locale và timezone có thể góp phần phân biệt môi trường.

Một giá trị riêng lẻ thường không duy nhất. Nhưng kết hợp nhiều ngôn ngữ, timezone và định dạng có thể làm tập tín hiệu hẹp hơn.

Ứng dụng chỉ nên dùng locale/timezone cho mục đích chức năng như định dạng ngày giờ hoặc ngôn ngữ giao diện. Không thu thập danh sách locale dài để tạo identifier.

### Screen và viewport

Các thuộc tính như screen.width, screen.height, devicePixelRatio, innerWidth, innerHeight và colorDepth có thể phản ánh cấu hình màn hình.

Các giá trị thay đổi khi:

- Người dùng đổi màn hình.
- Browser thay đổi zoom hoặc cửa sổ.
- Thiết bị chuyển giữa chế độ portrait và landscape.
- Hệ điều hành thay đổi scaling.

Một số browser có thể làm tròn hoặc giảm độ chính xác để hạn chế fingerprinting. Vì vậy, các giá trị này không ổn định tuyệt đối.

### Hardware hints

Các thuộc tính như navigator.hardwareConcurrency hoặc navigator.deviceMemory có thể cung cấp gợi ý về tài nguyên thiết bị. Browser có thể giảm độ chính xác, giới hạn hoặc không hỗ trợ các thuộc tính này.

Không dùng chúng để suy ra chính xác model máy, hiệu năng thật hoặc danh tính người dùng. Nếu cần tối ưu hiệu năng, đo khả năng thực tế của tác vụ và cho phép người dùng điều chỉnh.

### Font và rendering

Font được cài trên hệ điều hành và cách browser rasterize chữ có thể tạo ra khác biệt. Tuy nhiên, browser có thể giới hạn font enumeration hoặc chuẩn hóa rendering.

Không cần quét danh sách font cài đặt của người dùng cho một website thông thường. Hãy dùng web font hoặc font stack phù hợp với giao diện.

## 4. Canvas, WebGL và Audio fingerprinting

### Canvas fingerprinting

Canvas fingerprinting thường vẽ một nội dung gồm text, shape, gradient hoặc hình ảnh rồi đọc pixel output. Kết quả có thể khác nhau theo:

- Browser và rendering engine.
- Hệ điều hành.
- GPU và driver.
- Font và cách rasterize.
- Color management và scaling.

Một phép đo canvas không phải định danh ổn định tuyệt đối. Cập nhật driver, browser hoặc font có thể làm output thay đổi.

Website không cần đọc pixel canvas chỉ để hiển thị hình ảnh hoặc biểu đồ. Chỉ dùng readback khi chức năng thật sự cần, chẳng hạn xử lý ảnh trong editor.

### WebGL fingerprinting

WebGL cung cấp khả năng render đồ họa tăng tốc. Khác biệt về GPU, driver, shader compiler và browser implementation có thể tạo ra kết quả rendering khác nhau.

Một số thông tin renderer có thể bị browser ẩn, chuẩn hóa hoặc giới hạn. Việc truy vấn renderer details không được hỗ trợ giống nhau trên mọi browser.

Nếu ứng dụng cần WebGL để render, chỉ dùng capability cần thiết cho đồ họa. Không thu thập renderer string hoặc kết quả benchmark để tạo identifier nếu không có lý do rõ ràng.

### Audio fingerprinting

Web Audio API có thể tạo hoặc xử lý tín hiệu âm thanh. Khác biệt trong floating-point processing, audio pipeline và thiết bị có thể làm kết quả đo khác nhau.

Không khởi tạo audio graph chỉ để nhận diện browser. Nếu ứng dụng xử lý âm thanh, giới hạn việc đo và chỉ dùng dữ liệu phục vụ tính năng mà người dùng yêu cầu.

### Fingerprinting không đồng nghĩa với quyền camera/microphone

Fingerprinting có thể dùng thông tin khả năng API hoặc metadata mà browser công khai; nó không mặc nhiên được quyền thu âm hoặc bật camera. getUserMedia vẫn chịu secure context, Permissions Policy và quyền người dùng.

Tuy nhiên, việc liệt kê thiết bị, đọc device labels hoặc truy cập media khi được cấp quyền có thể làm tăng lượng thông tin lộ ra. Chỉ yêu cầu permission khi chức năng cần.

## 5. Entropy, uniqueness và độ ổn định

### Entropy là gì?

Entropy mô tả mức độ bất định của một biến. Với một tập tín hiệu, entropy có thể dùng để ước lượng lượng thông tin mà tập đó cung cấp về môi trường browser.

Công thức Shannon:

    H(X) = -Σ p(x) log2 p(x)

Nếu một tín hiệu có nhiều giá trị phổ biến gần như nhau, entropy có thể cao hơn một tín hiệu mà gần như mọi browser đều có cùng giá trị.

Ví dụ minh họa:

- Một giá trị phổ biến như ngôn ngữ English có thể phân biệt ít browser trong một tập lớn.
- Một tổ hợp hiếm gồm browser version, timezone, viewport và khả năng đồ họa có thể hẹp tập ứng viên hơn.

Không cộng entropy từng thuộc tính một cách máy móc. Các tín hiệu thường tương quan: browser version liên quan engine, hệ điều hành liên quan font, viewport liên quan độ phân giải và scaling.

### Uniqueness không đồng nghĩa stability

Một fingerprint có thể hiếm ở thời điểm hiện tại nhưng thay đổi ngay sau khi người dùng:

- Cập nhật browser.
- Cập nhật hệ điều hành hoặc driver.
- Cắm màn hình khác.
- Thay đổi font hoặc cài đặt ngôn ngữ.
- Chuyển sang browser profile khác.
- Bật tính năng chống fingerprinting.

Một tín hiệu ổn định trong thời gian dài có thể hữu ích cho liên kết, nhưng nếu quá phổ biến thì không phân biệt được nhiều người.

### Linkability

Linkability là khả năng liên kết hai phiên hoặc hai hoạt động được quan sát ở các thời điểm/ngữ cảnh khác nhau.

Ví dụ, nếu một tổ hợp tín hiệu đủ ổn định xuất hiện trên hai website, một bên có thể suy đoán hai lần truy cập đến từ cùng môi trường browser dù cookie khác nhau.

Linkability không chứng minh chắc chắn đó là cùng một người. Thiết bị dùng chung, NAT, máy ảo hoặc cấu hình phổ biến có thể tạo false match.

### Fingerprint là xác suất, không phải định danh tuyệt đối

Hệ thống có thể tính điểm tương đồng giữa fingerprint mới và fingerprint cũ. Ngưỡng quyết định càng chặt có thể giảm false match nhưng tăng false reject; ngưỡng rộng có thể tăng khả năng liên kết nhưng dễ ghép nhầm.

Không chuyển điểm tương đồng thành kết luận danh tính chắc chắn. Nếu dùng cho chống gian lận, cần thêm tín hiệu độc lập và cơ chế review phù hợp.

## 6. Theo dõi xuyên site và ghép nối dữ liệu

Fingerprinting trở nên nhạy cảm khi được dùng để liên kết hoạt động giữa các website hoặc dịch vụ.

Một luồng thường gặp:

1. Website A tải SDK phân tích bên thứ ba.
2. SDK đọc các tín hiệu browser mà policy cho phép.
3. SDK gửi dữ liệu về một dịch vụ tập trung.
4. Cùng SDK xuất hiện trên website B.
5. Dịch vụ so sánh tín hiệu và suy đoán hai phiên có thể thuộc cùng browser.
6. Dữ liệu được ghép với tài khoản, quảng cáo hoặc hồ sơ đã có.

### Third-party script mở rộng trust boundary

Script bên thứ ba chạy trong trang thường có quyền JavaScript của origin nhúng, trừ khi được cô lập bằng kiến trúc khác. Nó có thể đọc nhiều thông tin mà trang có quyền đọc, gửi dữ liệu ra ngoài và tương tác với DOM.

Biện pháp:

- Kiểm kê script bên thứ ba và mục đích thu thập.
- Chỉ tải SDK cần thiết.
- Giới hạn quyền script qua CSP và kiểm soát dependency.
- Dùng sandboxed iframe hoặc kiến trúc cô lập phù hợp khi có thể.
- Tránh đưa dữ liệu định danh vào URL hoặc referrer.
- Kiểm tra network request của SDK và chính sách retention.

### Partitioning giảm linkability nhưng không xóa fingerprint

Browser có thể phân vùng một số storage hoặc network state theo top-level site để hạn chế một bên thứ ba dùng chung identifier giữa các website.

Partitioning giúp giảm một số hình thức tracking dựa trên storage, nhưng không tự loại bỏ tín hiệu browser/device mà trang vẫn có thể quan sát. Fingerprinting có thể tiếp tục dựa trên các tín hiệu đó.

Không coi partitioned storage là bằng chứng browser không thể bị liên kết xuyên site.

## 7. Fingerprinting và các ranh giới Browser Security

### Same-Origin Policy

Same-Origin Policy kiểm soát việc document/script truy cập tài nguyên của origin khác theo các quy tắc browser. Nó không bảo đảm website không thể quan sát bất kỳ đặc điểm nào của browser hoặc thiết bị.

Một số API trả về thông tin môi trường ngay trong origin hiện tại. Website có thể kết hợp chúng mà không cần đọc DOM của origin khác.

### CORS

CORS kiểm soát việc JavaScript đọc response cross-origin qua các API mạng như Fetch/XHR. CORS không phải cơ chế chống fingerprinting tổng quát và không ngăn server quan sát IP hoặc request headers mà browser gửi tới server đó.

### Permissions Policy

Permissions Policy có thể hạn chế các feature nhạy cảm như camera, microphone, geolocation trong document/iframe. Nó không ẩn mọi thuộc tính navigator, screen hoặc mọi khác biệt rendering.

### CSP

CSP có thể hạn chế script và endpoint mà trang được phép kết nối. Điều này giúp giảm khả năng SDK không mong muốn chạy hoặc gửi dữ liệu ra ngoài, nhưng CSP không làm browser trở nên đồng nhất và không tự loại bỏ fingerprinting từ code được phép chạy.

### Cookie và Web Storage

Cookie, localStorage và sessionStorage là các kho lưu trữ có quy tắc riêng. Xóa chúng không xóa mọi tín hiệu browser/device mà một website có thể đọc lại.

## 8. Các biện pháp giảm fingerprinting ở browser

### Giảm độ chi tiết tín hiệu

Browser có thể chuẩn hóa hoặc giảm độ chính xác của một số thuộc tính:

- Giảm chi tiết User-Agent.
- Giới hạn Client Hints.
- Làm tròn kích thước màn hình hoặc viewport.
- Giới hạn font enumeration.
- Ẩn hoặc chuẩn hóa thông tin GPU.
- Giới hạn số liệu hardware.
- Giới hạn quyền truy cập API nhạy cảm.

Hành vi cụ thể phụ thuộc browser, phiên bản và cài đặt privacy.

### Tăng tính đồng nhất giữa người dùng

Một chiến lược là làm nhiều browser trông giống nhau hơn ở các bề mặt phổ biến. Nếu nhiều người dùng có cùng bộ giá trị mặc định, hệ thống khó phân biệt họ hơn.

Một số browser tập trung vào anti-fingerprinting có thể chuẩn hóa nhiều tín hiệu cùng lúc. Điều này có thể làm giảm compatibility của một số website hoặc thay đổi hành vi đồ họa.

### Randomization có thể có trade-off

Một số cơ chế có thể thêm noise hoặc thay đổi kết quả một cách có kiểm soát. Nhưng randomization không tự động tốt trong mọi trường hợp:

- Nếu mỗi lần truy cập tạo ra giá trị ngẫu nhiên độc nhất, giá trị đó có thể trở thành một fingerprint mới.
- Nếu noise không nhất quán giữa các API, tổ hợp tín hiệu có thể lại khác thường.
- Nếu thay đổi quá mạnh, ứng dụng hợp lệ có thể gặp lỗi rendering hoặc xác thực thiết bị.

Vì vậy, biện pháp anti-fingerprinting thường cần phối hợp nhiều API và được thiết kế ở cấp browser, thay vì ứng dụng tự randomize một vài thuộc tính.

### Partitioning và ephemeral state

Browser có thể phân vùng storage/network state hoặc xóa một số state khi kết thúc phiên. Điều này làm giảm khả năng bên thứ ba dùng lại identifier lưu trữ.

Partitioning và xóa state là lớp bổ sung. Chúng không thay thế việc giảm tín hiệu và kiểm soát script.

## 9. Người dùng có thể làm gì để giảm theo dõi?

Các lựa chọn sau có thể giảm một số dạng tracking, nhưng không bảo đảm ẩn danh tuyệt đối:

- Dùng browser có tính năng chống fingerprinting và cập nhật phiên bản.
- Giữ cấu hình browser phổ biến, tránh cài quá nhiều extension làm môi trường khác thường.
- Hạn chế third-party cookies và cross-site tracking theo cài đặt browser.
- Chặn hoặc giới hạn script bên thứ ba khi phù hợp.
- Dùng profile riêng cho các hoạt động cần tách biệt.
- Kiểm soát quyền camera, microphone, location và notification.
- Không cài extension không rõ nguồn gốc.
- Dùng VPN nếu mục tiêu là thay đổi IP công khai, nhưng hiểu rằng VPN không ẩn các tín hiệu browser khác.

### Private browsing không xóa fingerprint

Private/Incognito mode thường tạo phiên storage tạm thời và xóa một số dữ liệu khi đóng cửa sổ riêng tư. Nó không nhất thiết làm browser/device signals biến mất.

Website vẫn có thể quan sát một số thuộc tính browser, request headers, rendering behavior và IP của kết nối. Các browser có thể áp dụng anti-tracking bổ sung trong private mode, nhưng không nên xem đó là bảo đảm ẩn danh.

### Xóa cookie/site data có giới hạn

Xóa cookie có thể xóa identifier trực tiếp. Tuy nhiên, website có thể tính lại một tập tín hiệu từ môi trường hiện tại. Nếu người dùng đăng nhập lại cùng tài khoản, tài khoản đó cũng có thể liên kết các phiên theo cách khác.

### VPN chỉ thay đổi một phần tín hiệu

VPN thường thay đổi IP mà server nhìn thấy và có thể thay đổi tuyến mạng/độ trễ. Nó không nhất thiết thay đổi browser version, font, screen, WebGL, audio hoặc locale.

VPN không phải công cụ chống fingerprinting toàn diện.

## 10. Thiết kế ứng dụng tôn trọng quyền riêng tư

Nhà phát triển nên giảm việc tạo và lưu fingerprint nếu không có mục đích rõ ràng.

### Data minimization

Trước khi thu thập tín hiệu, hãy trả lời:

1. Tính năng nào thực sự cần dữ liệu này?
2. Có thể dùng feature detection hoặc dữ liệu tổng hợp ít nhạy cảm hơn không?
3. Có cần lưu qua nhiều phiên không?
4. Có cần chia sẻ với bên thứ ba không?
5. Thời hạn retention là bao lâu?
6. Người dùng có được thông báo và có lựa chọn phù hợp không?

Không thu thập toàn bộ navigator, screen, hardware và rendering signals chỉ vì có thể truy cập được.

### Dùng feature detection thay fingerprint

Nếu mục tiêu là xác định browser có hỗ trợ một tính năng, kiểm tra trực tiếp feature:

    const supportsWebRTC =
      typeof window.RTCPeerConnection === "function";

    const supportsMediaCapture =
      Boolean(navigator.mediaDevices?.getUserMedia);

Không cần xây dựng một identifier từ danh sách hàng chục thuộc tính để quyết định có hiển thị nút gọi video hay không.

### Tránh lưu fingerprint lâu dài

Nếu có use case chống gian lận cần một số tín hiệu:

- Chỉ thu thập các tín hiệu liên quan.
- Ưu tiên đánh giá rủi ro ngắn hạn thay vì định danh dài hạn.
- Không lưu raw high-entropy values nếu không cần.
- Giới hạn retention và quyền truy cập.
- Không chia sẻ với mục đích quảng cáo hoặc profiling ngoài mục đích đã thông báo.
- Cho phép quy trình khiếu nại khi hệ thống đánh giá nhầm.

### Không dùng fingerprint làm khóa tài khoản

Không tự động khóa tài khoản chỉ vì fingerprint thay đổi. Browser update, thiết bị mới, màn hình khác, privacy mode hoặc extension có thể làm fingerprint thay đổi.

Không tự động từ chối người dùng chỉ vì fingerprint giống người khác. Thiết bị dùng chung, máy ở thư viện, máy công ty và NAT có thể tạo tín hiệu trùng.

Nếu dùng risk scoring, kết hợp nhiều tín hiệu độc lập và yêu cầu xác minh bổ sung theo mức rủi ro. Tránh quyết định bất lợi chỉ dựa vào một điểm fingerprint.

## 11. Chống fingerprinting trong ứng dụng và hạ tầng

### Kiểm soát JavaScript và SDK

- Kiểm kê script bên thứ ba.
- Dùng CSP script-src với nonce/hash hoặc allowlist hẹp.
- Dùng Subresource Integrity cho tài nguyên bên thứ ba hỗ trợ SRI.
- Loại bỏ SDK không còn mục đích.
- Kiểm tra code thực tế trước khi nâng version.
- Cô lập script không đáng tin bằng iframe sandbox hoặc kiến trúc riêng khi phù hợp.

### Giới hạn endpoint thu thập

Server nên kiểm kê các endpoint nhận telemetry, analytics và device signals. Kiểm tra:

- Field nào được nhận.
- Dữ liệu có định danh trực tiếp hay gián tiếp.
- Dữ liệu có bị ghép với account ID/IP không.
- Ai có quyền truy cập.
- Dữ liệu được giữ bao lâu.
- Có được chuyển cho vendor khác không.

### IP và log

IP address có thể là dữ liệu cá nhân hoặc dữ liệu có thể liên kết tùy bối cảnh và quy định áp dụng. Không lưu IP thô vô thời hạn chỉ để debug nếu có thể dùng retention ngắn hoặc dữ liệu tổng hợp.

Nếu cần bảo vệ dịch vụ khỏi abuse, dùng rate limit, account security, device attestation phù hợp và tín hiệu hành vi có kiểm soát thay vì phụ thuộc duy nhất vào fingerprint.

### Referrer và URL

Không đưa identifier hoặc thông tin nhạy cảm vào query string. Dùng Referrer-Policy phù hợp để hạn chế URL bị gửi sang origin khác:

    Referrer-Policy: strict-origin-when-cross-origin

Chính sách này kiểm soát referrer được gửi theo navigation/request; nó không loại bỏ fingerprinting nói chung.

## 12. Fingerprinting và chống gian lận

Fingerprinting có thể được dùng để phát hiện:

- Tự động hóa hoặc bot.
- Tài khoản tạo hàng loạt.
- Lạm dụng khuyến mại.
- Credential stuffing.
- Hành vi đăng nhập bất thường.

Một số use case có thể hợp pháp và có ích cho bảo mật, nhưng cách triển khai cần cân bằng với quyền riêng tư.

### Không nhầm bot detection với danh tính

Browser automation, accessibility tools, privacy extensions và môi trường doanh nghiệp có thể tạo tín hiệu khác browser thông thường. Tín hiệu lạ không tự chứng minh hành vi gian lận.

### Kết hợp risk signals

Một hệ thống risk scoring có thể xem xét:

- Tốc độ và tần suất request.
- Lịch sử đăng nhập và challenge.
- Tính nhất quán của session.
- Dấu hiệu tự động hóa.
- Tín hiệu thiết bị ở mức tối thiểu cần thiết.
- Kết quả xác minh bổ sung.

Fingerprint chỉ nên là một tín hiệu hỗ trợ. Đặt ngưỡng, retention, kiểm tra false positive và quy trình review.

### Công bằng và khả năng giải trình

Fingerprint có thể phân biệt người dùng dựa trên thiết bị cũ, cấu hình hiếm, hệ điều hành đặc thù hoặc công nghệ hỗ trợ. Nếu hệ thống từ chối họ mà không có cách khắc phục, có thể tạo tác động không công bằng.

Nên:

- Có thông báo lỗi đủ hữu ích nhưng không tiết lộ rule chống abuse.
- Có cách xác minh thay thế.
- Cho phép người dùng liên hệ hoặc khiếu nại.
- Theo dõi tỷ lệ false positive giữa nhóm thiết bị/browser.
- Định kỳ đánh giá lại tín hiệu và ngưỡng.

## 13. Kiểm tra fingerprinting bằng Chrome DevTools

Mục tiêu của bài lab là kiểm kê bề mặt thu thập trên ứng dụng của chính mình. Không tạo hoặc gửi một fingerprint định danh người khác.

### Bước 1 — Kiểm tra request headers

1. Mở DevTools → Network.
2. Tải lại trang trong môi trường test.
3. Chọn document request.
4. Xem Request Headers.
5. Ghi nhận User-Agent, Accept-Language và các Client Hints thực sự được gửi.
6. Kiểm tra request có gửi dữ liệu nhận diện riêng qua query/header hay không.

Không sao chép token, cookie hoặc thông tin tài khoản vào báo cáo lab.

### Bước 2 — Kiểm tra script bên thứ ba

1. Mở Network và lọc JS.
2. Ghi nhận domain của script.
3. Kiểm tra Initiator để biết script nào tải SDK.
4. Tìm các request telemetry do SDK gửi.
5. Đối chiếu field gửi đi với mục đích của tính năng.

### Bước 3 — Audit API surface trong source

Tìm trong code của ứng dụng các API có thể tiết lộ tín hiệu:

- navigator.userAgent và userAgentData.
- navigator.language và navigator.languages.
- screen và devicePixelRatio.
- navigator.hardwareConcurrency và deviceMemory.
- Canvas getImageData hoặc toDataURL.
- WebGL renderer/debug extensions.
- AudioContext hoặc OfflineAudioContext.
- enumerateDevices và deviceId.

Sự xuất hiện của API chưa chứng minh có fingerprinting. Kiểm tra dữ liệu có được kết hợp, gửi đi, lưu lại hoặc dùng để phân loại user không.

### Bước 4 — So sánh profile test

Trong môi trường local, so sánh:

1. Browser profile thường.
2. Private browsing profile.
3. Browser sau khi cập nhật.
4. Viewport hoặc màn hình khác.
5. Cấu hình privacy/anti-tracking khác.

Quan sát tín hiệu nào thay đổi. Không kết luận hai profile thuộc cùng hoặc khác người chỉ từ một vài giá trị.

### Bước 5 — Kiểm tra storage partitioning

1. Mở Application → Storage.
2. Kiểm tra cookie và storage của origin test.
3. Mở cùng third-party content từ hai top-level site trong môi trường lab.
4. Quan sát browser có phân vùng storage hay không theo browser/version.
5. Ghi rõ giới hạn của phép thử; kết quả storage partitioning không chứng minh fingerprinting đã bị loại bỏ.

### Ví dụ feature detection không tạo fingerprint

Đoạn code sau chỉ kiểm tra hai tính năng để bật/tắt UI. Nó không tạo identifier, không đọc renderer string và không gửi dữ liệu đi:

    const capabilities = {
      webRTC: typeof window.RTCPeerConnection === "function",
      mediaCapture: Boolean(
        navigator.mediaDevices?.getUserMedia
      )
    };

    enableCallButton(
      capabilities.webRTC && capabilities.mediaCapture
    );

### Ma trận kiểm thử

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Passive signals | Quan sát request headers | Chỉ ghi nhận các header browser thực sự gửi |
| Third-party SDK | Kiểm tra JS và telemetry | Xác định SDK, endpoint và field được gửi |
| Canvas API | Audit code readback | Có mục đích chức năng rõ; không thu thập chỉ để nhận diện |
| WebGL API | Audit renderer/debug query | Không thu thập thông tin renderer không cần thiết |
| Audio API | Audit AudioContext usage | Chỉ dùng cho tính năng audio |
| Device enumeration | Kiểm tra enumerateDevices | Chỉ gọi khi cần; không gửi device list vô cớ |
| Private profile | So sánh với profile thường | Một số storage thay đổi; không kết luận fingerprint biến mất |
| VPN | Thay IP test | IP thay đổi nhưng các tín hiệu browser khác có thể còn |
| Cookie deletion | Xóa site data | Identifier lưu trữ có thể mất; tín hiệu browser vẫn có thể quan sát |
| Storage partitioning | Dùng cùng third-party ở hai site | State có thể bị tách; không đồng nghĩa không còn fingerprinting |
| Feature detection | Chạy ví dụ capability | UI hoạt động mà không tạo identifier dài hạn |

## 14. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ fingerprint là cookie | Bỏ sót tracking không dựa vào storage | Audit cả API, headers, SDK và server signals |
| Nghĩ fingerprint xác định duy nhất một người | Ghép nhầm người dùng | Xem là tín hiệu xác suất, đo false positive |
| Nghĩ xóa cookie sẽ xóa fingerprint | Tín hiệu browser/device vẫn có thể được đo lại | Kết hợp privacy controls và giảm signal collection |
| Nghĩ Incognito ẩn mọi đặc điểm browser | Website vẫn quan sát được nhiều tín hiệu | Hiểu private mode chủ yếu cô lập/giới hạn state |
| Nghĩ VPN chống fingerprinting hoàn toàn | IP đổi nhưng rendering và browser signals còn | Kết hợp anti-tracking và giảm API exposure |
| Thu thập mọi thuộc tính navigator | Tăng entropy và dữ liệu nhạy cảm không cần thiết | Data minimization và feature detection |
| Hash fingerprint rồi coi là anonymous | Hash vẫn có thể liên kết cùng input | Không coi pseudonymous identifier là dữ liệu vô danh |
| Randomize mỗi thuộc tính độc lập | Tạo tổ hợp khác thường, dễ phân biệt | Ưu tiên biện pháp anti-fingerprinting phối hợp ở browser |
| Dùng fingerprint làm MFA | Kẻ tấn công có thể giả lập hoặc có tín hiệu tương tự | Dùng yếu tố xác thực mật mã và MFA |
| Dùng fingerprint làm điều kiện khóa tài khoản duy nhất | False positive và tác động không công bằng | Dùng risk scoring, challenge và review |
| Nghĩ storage partitioning xóa fingerprint | Passive/active signals vẫn có thể được thu thập | Xem partitioning là một lớp giảm linkability |
| Nghĩ CORS chặn fingerprinting | CORS không kiểm soát mọi tín hiệu browser/network | Giới hạn script và data collection |
| Bỏ qua SDK bên thứ ba | Dữ liệu có thể được gửi ra ngoài origin | Inventory, CSP, SRI và kiểm tra telemetry |
| Log IP và device signals vô thời hạn | Tăng rủi ro riêng tư và breach impact | Giới hạn retention, access và mục đích |

## 15. Câu hỏi củng cố

**Câu 1.** Browser fingerprinting là gì?

**Giải đáp:** Kỹ thuật kết hợp tín hiệu browser, thiết bị và mạng để suy đoán hoặc liên kết một môi trường browser giữa các lần truy cập.

**Câu 2.** Fingerprint khác cookie như thế nào?

**Giải đáp:** Cookie là identifier được lưu và gửi theo quy tắc cookie; fingerprint được suy ra từ các tín hiệu môi trường và có thể được tính lại sau khi xóa cookie.

**Câu 3.** Passive fingerprinting khác active fingerprinting thế nào?

**Giải đáp:** Passive dùng dữ liệu sẵn có trong request/handshake; active chủ động gọi API hoặc render nội dung để đo khác biệt.

**Câu 4.** Entropy cao có đồng nghĩa fingerprint ổn định không?

**Giải đáp:** Không. Entropy liên quan mức độ phân biệt trong một tập; stability liên quan khả năng tín hiệu giữ nguyên theo thời gian.

**Câu 5.** Vì sao fingerprint là xác suất?

**Giải đáp:** Nhiều browser có thể chia sẻ tín hiệu giống nhau, còn một browser có thể thay đổi tín hiệu sau update hoặc đổi cấu hình. Do đó luôn có khả năng false match và false reject.

**Câu 6.** Private browsing có loại bỏ fingerprint không?

**Giải đáp:** Không. Nó thường cô lập storage tạm thời nhưng nhiều tín hiệu browser/device vẫn có thể quan sát.

**Câu 7.** VPN có chống fingerprinting đầy đủ không?

**Giải đáp:** Không. VPN thay đổi IP hoặc tuyến mạng nhưng không nhất thiết thay browser version, font, screen, WebGL hoặc locale.

**Câu 8.** Storage partitioning có loại bỏ tracking xuyên site không?

**Giải đáp:** Nó giảm một số liên kết dựa trên storage/network state dùng chung, nhưng không tự loại bỏ passive/active fingerprinting.

**Câu 9.** Có nên dùng fingerprint làm yếu tố xác thực?

**Giải đáp:** Không. Fingerprint không phải bằng chứng mật mã về danh tính. Nó chỉ có thể là tín hiệu rủi ro bổ sung.

**Câu 10.** Nhà phát triển nên làm gì trước khi thu thập fingerprint?

**Giải đáp:** Xác định mục đích, giảm dữ liệu, ưu tiên feature detection, giới hạn retention/chia sẻ, thông báo minh bạch và đánh giá false positive.

## 16. Tổng kết

Browser fingerprinting kết hợp các tín hiệu browser, thiết bị và mạng để nhận diện hoặc liên kết một môi trường theo xác suất. Nó khác cookie và storage identifier vì có thể được tính lại từ các đặc điểm môi trường sau khi dữ liệu lưu trữ bị xóa. Fingerprint có thể mang tính passive hoặc active, có entropy và uniqueness khác nhau, nhưng không nhất thiết ổn định hoặc duy nhất.

Các bề mặt thường gặp gồm User-Agent/Client Hints, locale, timezone, screen, hardware hints, font, canvas, WebGL, audio và thông tin mạng. Same-Origin Policy, CORS, Permissions Policy, CSP và storage partitioning xử lý các ranh giới khác nhau; không cơ chế nào tự loại bỏ mọi fingerprinting.

Người dùng có thể giảm một số hình thức theo dõi bằng anti-fingerprinting, hạn chế third-party scripts và quản lý quyền, nhưng private browsing, xóa cookie hoặc VPN không bảo đảm ẩn danh. Nhà phát triển nên ưu tiên data minimization và feature detection, không dùng fingerprint làm xác thực duy nhất hoặc tự động khóa tài khoản. Nếu dùng cho chống gian lận, cần giới hạn retention, đo false positive, minh bạch và có quy trình review.

## Tài liệu tham khảo

1. [W3C — Fingerprinting Guidance](https://www.w3.org/TR/fingerprinting-guidance/): hướng dẫn giảm bề mặt fingerprinting cho browser và web platform.
2. [W3C — Privacy Principles](https://www.w3.org/TR/privacy-principles/): các nguyên tắc quyền riêng tư cho nền tảng web.
3. [MDN — Browser fingerprinting](https://developer.mozilla.org/en-US/docs/Glossary/Fingerprinting): khái niệm và các tín hiệu fingerprinting.
4. [EFF — Cover Your Tracks](https://coveryourtracks.eff.org/): công cụ minh họa mức độ browser có thể bị nhận diện qua các tín hiệu.
5. [Tor Browser — Anti-fingerprinting](https://support.torproject.org/anti-fingerprinting/): cách giảm tính phân biệt của browser fingerprint.
6. [MDN — User-Agent Client Hints API](https://developer.mozilla.org/en-US/docs/Web/API/User-Agent_Client_Hints_API): cơ chế Client Hints và quyền riêng tư.
7. [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy): giới hạn truy cập các browser features.
