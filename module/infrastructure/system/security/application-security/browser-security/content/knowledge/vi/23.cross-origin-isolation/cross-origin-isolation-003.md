# COEP: kiểm soát tài nguyên cross-origin được nhúng vào tài liệu

> **Chương:** Cross-origin isolation  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Cross-Origin-Embedder-Policy (COEP)** là HTTP response header cho phép một tài liệu kiểm soát việc nhúng các tài nguyên cross-origin được tải ở chế độ **no-cors**. Với policy **require-corp**, tài nguyên cross-origin phải thể hiện rõ sự cho phép qua Cross-Origin-Resource-Policy (CORP), hoặc được tải ở chế độ CORS và vượt qua kiểm tra CORS. Với **credentialless**, browser có thể tải tài nguyên cross-origin ở chế độ no-cors mà không cần CORP, nhưng request bị loại bỏ credential và cookie của response bị bỏ qua.

COEP thường được triển khai cùng **Cross-Origin-Opener-Policy (COOP)** để bật cross-origin isolation. Cặp header này giúp browser giảm khả năng một tài liệu độc hại quan sát hoặc suy luận dữ liệu từ tài nguyên khác origin thông qua side-channel. Một số API như SharedArrayBuffer, timer độ phân giải cao hơn và một số API đo bộ nhớ chỉ hoạt động với ít hạn chế hơn khi document thật sự cross-origin isolated.

COEP có thể làm hỏng ảnh, script, font, worker, iframe hoặc SDK bên thứ ba nếu các tài nguyên đó chưa opt-in đúng cách. Vì vậy, cần hiểu rõ vai trò của COEP, CORP và CORS, kiểm kê toàn bộ dependency, chạy Report-Only trước và kiểm thử luồng thực tế trước khi bật enforcement.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích COEP là policy của tài liệu nhúng tài nguyên và chủ yếu kiểm soát request cross-origin ở chế độ no-cors.
2. Phân biệt ba giá trị unsafe-none, require-corp và credentialless.
3. Giải thích CORP là header do server cung cấp tài nguyên đặt, còn COEP là header do trang embedder đặt.
4. Phân biệt CORP với CORS và chọn đúng cách opt-in cho ảnh, script, font, fetch và iframe.
5. Hiểu vì sao credentialless bỏ cookie/credential trong request cross-origin no-cors và bỏ qua cookie trong response.
6. Kết hợp COEP với COOP để bật cross-origin isolation và kiểm tra crossOriginIsolated.
7. Nhận diện tác động đến iframe, worker, CDN, analytics, OAuth popup và các tích hợp bên thứ ba.
8. Triển khai COEP Report-Only, đọc violation report và xử lý lỗi tải tài nguyên.
9. Thực hành require-corp và credentialless bằng hai origin localhost.

## 1. COEP giải quyết vấn đề gì?

### 1.1 Tài liệu có thể nhúng tài nguyên cross-origin

Một trang có thể tải tài nguyên từ nhiều origin:

~~~html
<img src="https://images.example.net/banner.png" alt="Banner">
<script src="https://cdn.example.net/app.js"></script>
<link rel="stylesheet" href="https://fonts.example.net/site.css">
<iframe src="https://widget.example.net/embed"></iframe>
~~~

Browser thường cho phép nhiều loại tài nguyên cross-origin được nhúng dù JavaScript của trang không được phép đọc nội dung response do Same-Origin Policy. Ví dụ, trang có thể hiển thị ảnh từ domain khác nhưng không được đọc pixel ảnh nếu ảnh không được cấp CORS phù hợp.

Việc một trang có thể nhúng tài nguyên không đồng nghĩa tài nguyên đó đã đồng ý cho phép được nhúng. Trong một số tình huống, attacker có thể lợi dụng browser tải tài nguyên cross-origin để suy luận trạng thái hoặc dữ liệu thông qua side-channel, timing hay hành vi hiển thị.

### 1.2 Embedder phải yêu cầu tài nguyên opt-in

COEP đặt yêu cầu lên tài liệu đang nhúng: tài nguyên cross-origin được tải theo chế độ no-cors cần có sự cho phép rõ từ phía server tài nguyên nếu policy là require-corp.

Ví dụ trang https://app.example.com tải ảnh https://images.example.net/banner.png. Nếu request ảnh là no-cors và trang app dùng:

~~~http
Cross-Origin-Embedder-Policy: require-corp
~~~

server ảnh phải trả header CORP cho phép app nhúng ảnh, hoặc ứng dụng phải chuyển request sang CORS mode và server ảnh cho phép CORS.

COEP vì vậy tạo ra một hợp đồng giữa hai bên:

- **Embedder:** trang đặt COEP để yêu cầu tài nguyên cross-origin opt-in.
- **Resource provider:** server tài nguyên dùng CORP hoặc CORS để cho phép việc tải/nhúng theo cách phù hợp.

### 1.3 COEP không phải CORS và không cấp quyền đọc response

COEP không cấp quyền cho JavaScript đọc response cross-origin. CORS mới là cơ chế quyết định request CORS có được phép chia sẻ response với script hay không.

Ví dụ:

- Một ảnh có Cross-Origin-Resource-Policy: cross-origin có thể được nhúng ở chế độ no-cors dưới COEP require-corp, nhưng JavaScript vẫn không tự động đọc được pixel qua canvas.
- Một ảnh được tải bằng crossorigin="anonymous" dùng CORS mode; server cần Access-Control-Allow-Origin phù hợp.
- Một request fetch() dùng mode: "cors" vẫn phải vượt qua CORS; COEP không bỏ qua kiểm tra CORS.

## 2. Ba giá trị của Cross-Origin-Embedder-Policy

### 2.1 unsafe-none: hành vi mặc định

~~~http
Cross-Origin-Embedder-Policy: unsafe-none
~~~

unsafe-none là mặc định nếu response không có COEP. Tài liệu có thể tải tài nguyên cross-origin ở chế độ no-cors mà không cần tài nguyên gửi CORP opt-in.

Giá trị này thuận tiện cho tương thích, nhưng không đáp ứng điều kiện COEP cần thiết để document đạt cross-origin isolation. Nếu mục tiêu là dùng SharedArrayBuffer theo chế độ cross-origin isolated, cần require-corp hoặc credentialless cùng COOP phù hợp.

### 2.2 require-corp: yêu cầu resource opt-in

~~~http
Cross-Origin-Embedder-Policy: require-corp
~~~

Với require-corp:

- Tài nguyên same-origin có thể được tải theo quy tắc thông thường.
- Tài nguyên cross-origin được request ở chế độ no-cors cần response CORP cho phép embedder.
- Tài nguyên được request ở chế độ cors có thể tải nếu server cho phép qua CORS.
- Nếu tài nguyên cross-origin không có CORP phù hợp và request không dùng CORS thành công, browser chặn tài nguyên.

Ví dụ resource server cho phép mọi origin nhúng ở chế độ no-cors:

~~~http
Cross-Origin-Resource-Policy: cross-origin
~~~

Đây là lựa chọn rộng. Chỉ dùng cho tài nguyên công khai mà chủ sở hữu thật sự muốn cho phép nhúng cross-origin.

Nếu tài nguyên chỉ nên được nhúng từ cùng site:

~~~http
Cross-Origin-Resource-Policy: same-site
~~~

Nếu chỉ được nhúng bởi document cùng origin:

~~~http
Cross-Origin-Resource-Policy: same-origin
~~~

### 2.3 credentialless: cho phép no-cors cross-origin không có credential

~~~http
Cross-Origin-Embedder-Policy: credentialless
~~~

Với credentialless, browser có thể tải tài nguyên cross-origin ở chế độ no-cors mà không cần response CORP opt-in. Đổi lại:

- Cookie bị loại khỏi request.
- Các credential khác của request cũng không được gửi theo chế độ này.
- Cookie được đặt trong response bị browser bỏ qua.
- Request CORS vẫn phải đáp ứng CORS như bình thường.

Giá trị này hữu ích khi cần cross-origin isolation nhưng còn phụ thuộc một số tài nguyên công khai từ nhà cung cấp chưa cấu hình CORP. Nó không phải cách vượt qua CORS cho API cần đọc response và không phù hợp nếu tài nguyên cần cookie để cá nhân hóa hoặc xác thực.

### 2.4 So sánh nhanh

| COEP | Cross-origin no-cors | Credential | CORS request |
|---|---|---|---|
| unsafe-none | Có thể tải mà không cần CORP opt-in | Theo request bình thường | Vẫn phải qua CORS nếu cần chia sẻ response |
| require-corp | Cần CORP cho phép | Theo request bình thường, nhưng resource phải opt-in | Phải qua CORS |
| credentialless | Có thể tải mà không cần CORP opt-in | Cookie/credential bị loại khỏi request; cookie response bị bỏ qua | Phải qua CORS |

Chọn policy theo mô hình dữ liệu và tích hợp thực tế. credentialless giảm yêu cầu opt-in của resource provider cho no-cors nhưng làm thay đổi ngữ nghĩa request có credential. require-corp yêu cầu resource provider thể hiện sự cho phép rõ ràng.

### 2.5 COEP không ghi đè CORP của resource

COEP là yêu cầu từ phía embedder; CORP vẫn là quyết định của server cung cấp tài nguyên. Nếu resource trả CORP same-origin, một trang khác origin không thể nhúng resource đó chỉ bằng cách chuyển COEP sang credentialless. Tương tự, credentialless không biến một response bị CORP hạn chế thành tài nguyên công khai. Hãy phân biệt việc bỏ credential khỏi request với việc resource provider cho phép embedder.

Một response HTML chỉ nên có một giá trị COEP hợp lệ. Không gửi nhiều token hoặc lặp header COEP qua cả ứng dụng và reverse proxy; cấu hình trùng/lỗi có thể khiến browser không áp dụng policy như dự kiến.

## 3. Phân biệt COEP, CORP và CORS

### 3.1 COEP là policy của embedder

COEP được gửi trong response của document đang nhúng tài nguyên:

~~~http
Cross-Origin-Embedder-Policy: require-corp
~~~

Nó nói với browser: “Tài liệu này yêu cầu tài nguyên cross-origin no-cors phải opt-in theo CORP, hoặc được tải qua CORS hợp lệ.”

### 3.2 CORP là policy của resource provider

CORP được gửi trong response của chính tài nguyên:

~~~http
Cross-Origin-Resource-Policy: same-origin
~~~

Ba giá trị thường gặp:

| CORP | Cho phép |
|---|---|
| same-origin | Chỉ request từ cùng origin |
| same-site | Request từ cùng site theo quy tắc site của browser |
| cross-origin | Request từ origin khác cũng có thể nhúng tài nguyên |

Origin bao gồm scheme, host và port. Site dựa trên khái niệm registrable domain và schemeful site của browser; do đó hai subdomain có thể same-site nhưng khác-origin. CORP same-site rộng hơn same-origin.

CORP là opt-in của resource provider cho các request no-cors. Nó không cho script quyền đọc response và không phải một CORS response header.

### 3.3 CORS là cơ chế chia sẻ response

Server có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
~~~

Nếu request CORS được gửi từ origin đã nêu, browser có thể cho script đọc response theo quy tắc CORS.

Với credentialed CORS request, server cần origin cụ thể và:

~~~http
Access-Control-Allow-Credentials: true
~~~

Không dùng wildcard Access-Control-Allow-Origin: * cùng credentials. Request mode và credentials mode phải phù hợp với API.

### 3.4 Bảng phân biệt

| Câu hỏi | Cơ chế |
|---|---|
| Trang embedder có yêu cầu resource no-cors opt-in không? | COEP |
| Resource provider cho phép tài nguyên được nhúng bởi same-origin/same-site/cross-origin nào? | CORP |
| JavaScript có được đọc response cross-origin không? | CORS |
| Trang top-level và cửa sổ mở bằng popup có bị tách browsing context group không? | COOP |
| Document đã đạt điều kiện cross-origin isolation chưa? | crossOriginIsolated và các điều kiện COOP/COEP/Permissions Policy |

Đừng dùng CORP để thay CORS cho API mà JavaScript cần đọc dữ liệu. Đừng dùng CORS để thay CORP cho resource được tải no-cors dưới COEP require-corp.

## 4. Request mode quyết định cách xử lý

### 4.1 no-cors resource

Nhiều thẻ HTML tải tài nguyên ở chế độ no-cors khi không có thuộc tính crossorigin phù hợp. Ví dụ ảnh:

~~~html
<img src="https://images.example.net/banner.png" alt="Banner">
~~~

Nếu trang embedder dùng COEP require-corp, response ảnh cross-origin cần CORP cho phép. Nếu không có, browser chặn ảnh và ghi nhận COEP violation.

### 4.2 Chuyển ảnh sang CORS mode

Nếu resource provider hỗ trợ CORS, có thể dùng:

~~~html
<img
  src="https://images.example.net/banner.png"
  crossorigin="anonymous"
  alt="Banner">
~~~

Thuộc tính crossorigin="anonymous" khiến browser gửi request ở chế độ CORS với credentials mode phù hợp cho anonymous. Server ảnh cần trả ACAO cho phép origin của trang hoặc wildcard trong trường hợp không dùng credentials.

Nếu cần credentials:

~~~html
<img
  src="https://images.example.net/private-banner.png"
  crossorigin="use-credentials"
  alt="Banner riêng">
~~~

Server phải cho phép origin cụ thể và credentials; cookie còn phụ thuộc SameSite, third-party cookie policy và các điều kiện browser khác.

### 4.3 Fetch API

Request CORS:

~~~js
const response = await fetch('https://api.example.net/data', {
  mode: 'cors',
  credentials: 'omit'
});

if (!response.ok) {
  throw new Error('Request failed: ' + response.status);
}

const data = await response.json();
~~~

Request mode cors vẫn cần server trả CORS header đúng. COEP không bỏ qua CORS.

Request mode no-cors thường trả về opaque response mà JavaScript không thể đọc nội dung. Dưới COEP require-corp, tài nguyên cross-origin no-cors vẫn cần CORP phù hợp. Chuyển sang no-cors không phải cách khắc phục để đọc API.

### 4.4 Script, stylesheet và font

Script có thể chuyển sang CORS mode bằng crossorigin:

~~~html
<script
  src="https://cdn.example.net/library.js"
  crossorigin="anonymous"></script>
~~~

Server CDN cần ACAO tương ứng. Nếu không dùng crossorigin, script có thể được request no-cors và khi đó COEP require-corp cần CORP.

Font web thường được tải theo CORS rules; kiểm tra response font và cấu hình CDN. Stylesheet và các tài nguyên con được CSS tham chiếu cũng cần được kiểm kê. Không chỉ kiểm tra file CSS chính rồi kết luận toàn bộ dependency đã opt-in.

## 5. Bật cross-origin isolation với COOP và COEP

### 5.1 Hai header phối hợp

Để một document đạt cross-origin isolation trong cấu hình thông dụng, response HTML cần:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Hoặc dùng COEP credentialless:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: credentialless
~~~

Ngoài ra, Permissions Policy không được chặn feature cross-origin-isolated. Default allowlist của directive này là self, nhưng cấu hình tùy chỉnh có thể vô tình tắt quyền.

Nếu ứng dụng chủ động cấu hình Permissions Policy, có thể khai báo rõ quyền cho document cùng origin:

~~~http
Permissions-Policy: cross-origin-isolated=(self)
~~~

Đừng đặt allowlist rỗng cho feature này trên document cần SharedArrayBuffer. Với iframe, chỉ delegate khi kiến trúc thực sự yêu cầu và browser hỗ trợ luồng đó.

COOP tách browsing context group với các cửa sổ cross-origin không tương thích, giúp bảo vệ quan hệ opener. COEP yêu cầu tài nguyên được nhúng phải opt-in. Cả hai giải quyết hai mặt khác nhau của quá trình cách ly.

### 5.2 Kiểm tra crossOriginIsolated

Trong JavaScript:

~~~js
console.log('crossOriginIsolated:', window.crossOriginIsolated);
~~~

Trong worker:

~~~js
console.log('worker isolated:', self.crossOriginIsolated);
~~~

Giá trị true cho biết document hoặc worker đang ở trạng thái cross-origin isolated. Nếu là false, kiểm tra:

- COOP response header có đúng same-origin không?
- COEP có phải require-corp hoặc credentialless không?
- Permissions Policy có chặn cross-origin-isolated không?
- Header có bị proxy/CDN ghi đè, xóa hoặc gửi trùng không?
- Tài liệu đang kiểm tra có thật sự nhận response header đó không?

### 5.3 SharedArrayBuffer

Khi cross-origin isolated và browser hỗ trợ:

~~~js
if (window.crossOriginIsolated &&
    typeof SharedArrayBuffer !== 'undefined') {
  const shared = new SharedArrayBuffer(1024);
  const view = new Int32Array(shared);

  Atomics.store(view, 0, 42);
  console.log(Atomics.load(view, 0));
} else {
  console.log('SharedArrayBuffer không khả dụng trong context này.');
}
~~~

SharedArrayBuffer cho phép nhiều agent như window và worker chia sẻ vùng nhớ. Điều này hữu ích cho xử lý song song và một số ứng dụng hiệu năng cao. Nó cũng tạo điều kiện cho timing side-channel tinh vi hơn, vì vậy browser yêu cầu môi trường cross-origin isolated trước khi cung cấp đầy đủ tính năng.

### 5.4 Những API khác

Cross-origin isolation còn liên quan đến:

- Độ phân giải cao hơn của Performance.now() trong những browser áp dụng hạn chế timer.
- Một số API đo bộ nhớ như performance.measureUserAgentSpecificMemory() theo hỗ trợ browser.
- Một số tính năng dùng SharedArrayBuffer trong thư viện WebAssembly hoặc xử lý media.

Không giả định mọi API đều có cùng browser support. Kiểm tra feature detection và cung cấp fallback khi document chưa isolated.

### 5.5 COOP có thể thay đổi hành vi popup

Cross-Origin-Opener-Policy: same-origin có thể tách trang khỏi cửa sổ cross-origin được mở bằng window.open(). Quan hệ window.opener có thể bị cắt và các luồng popup cũ có thể thay đổi.

Kiểm thử kỹ:

- OAuth/OIDC login popup.
- Payment provider popup.
- Cửa sổ hỗ trợ hoặc dashboard mở từ ứng dụng.
- Luồng dùng postMessage giữa opener và popup.
- Callback cần truy cập opener sau điều hướng.

Có thể cần thiết kế lại luồng popup bằng redirect, server callback hoặc cơ chế trao đổi message có xác thực. Không nới COOP chỉ để sửa một luồng mà chưa đánh giá ảnh hưởng đến cross-origin isolation.

## 6. Ảnh hưởng đến iframe, worker và dependency

### 6.1 Iframe cross-origin

COEP áp dụng cho tài nguyên được nhúng, bao gồm iframe và nested frame. Khi bật require-corp, iframe cross-origin có thể bị chặn nếu response/luồng tải không opt-in phù hợp. Một số tích hợp yêu cầu document con có policy riêng và cần kiểm tra cả chuỗi frame.

Kiểm kê:

- Origin iframe ban đầu.
- Redirect sang origin khác.
- Header COEP/CORP của document con.
- Các tài nguyên con mà iframe tự tải.
- Sandbox, Permissions Policy và CSP liên quan.
- Cookie/SSO cần thiết cho iframe.

Không thể chỉ thêm allow attribute hoặc CORS header vào trang cha để giải quyết mọi lỗi iframe. Mỗi lớp policy có trách nhiệm riêng.

### 6.2 Worker và Service Worker

Worker script là một dependency cần được kiểm tra cùng các header và origin của ứng dụng. Worker cùng origin thường dễ tương thích hơn; worker hoặc import script từ nguồn khác cần đáp ứng quy tắc fetch/CORS và policy tương ứng.

Với cross-origin isolated document, worker có thể kiểm tra self.crossOriginIsolated và sử dụng SharedArrayBuffer khi được phép. Nếu worker được tạo từ blob URL hoặc module import, hãy kiểm tra CSP worker-src, nguồn script và browser support riêng. COEP không thay thế CSP.

### 6.3 CDN và third-party SDK

Những nguồn dễ gây lỗi khi bật COEP:

- Ảnh và video CDN không có CORP.
- Font CDN không có CORS header đúng.
- Script analytics hoặc tag manager tải ở no-cors.
- SDK tải script phụ từ domain khác.
- Captcha, chat widget, payment iframe.
- Media/worker được host bởi nhà cung cấp khác.
- Tài nguyên public redirect qua một origin không được dự kiến.

Yêu cầu nhà cung cấp hỗ trợ CORP/CORS hoặc thay cách tải phù hợp. Nếu tài nguyên chỉ là public no-cors và không cần cookie, credentialless có thể là lựa chọn, nhưng phải xác nhận ngữ nghĩa và quyền riêng tư.

## 7. Triển khai CORP ở resource server

### 7.1 Chỉ same-origin

Đối với response chứa dữ liệu riêng tư, có thể đặt:

~~~http
Cross-Origin-Resource-Policy: same-origin
~~~

Browser sẽ không cho phép resource đó được nhúng bởi document khác origin trong no-cors mode. Header này hữu ích với tài nguyên chỉ nên được sử dụng trong origin sở hữu nó.

### 7.2 Same-site

~~~http
Cross-Origin-Resource-Policy: same-site
~~~

Cho phép nhúng từ cùng site theo quy tắc site của browser. Hai subdomain có thể khác origin nhưng cùng site. Chọn same-site khi các subdomain thuộc cùng ranh giới tin cậy và cần chia sẻ resource; không dùng chỉ vì chúng có chung chuỗi domain.

### 7.3 Public cross-origin resource

~~~http
Cross-Origin-Resource-Policy: cross-origin
~~~

Cho phép resource được nhúng cross-origin trong các request phù hợp. Chỉ đặt cho nội dung mà chủ sở hữu thực sự muốn công khai cho việc nhúng, ví dụ asset public từ CDN.

CORP cross-origin không phải quyền CORS để đọc response bằng JavaScript. Nếu script cần đọc nội dung, server vẫn phải cấu hình CORS.

### 7.4 Chọn giá trị tối thiểu

| Resource | Policy có thể phù hợp |
|---|---|
| Avatar riêng của người dùng, chỉ dùng trong app | same-origin |
| Asset chia sẻ giữa các subdomain cùng site | same-site |
| Logo/ảnh public trên CDN cho mọi website nhúng | cross-origin |
| API JSON cần JavaScript đọc | CORS theo origin được phép; không dựa vào CORP |

Không đặt cross-origin toàn bộ response của domain chỉ để sửa một trang embedder. Hãy phân loại endpoint và dữ liệu.

## 8. Report-Only và giám sát COEP violation

### 8.1 COEP Report-Only

Trước khi chặn thật, có thể gửi:

~~~http
Reporting-Endpoints: coep-endpoint="https://reports.example.net/coep"
Cross-Origin-Embedder-Policy-Report-Only: require-corp; report-to="coep-endpoint"
~~~

Report-Only cho browser đánh giá policy và ghi nhận vi phạm mà không chặn tài nguyên chỉ vì policy thử nghiệm. Nó hữu ích để tìm các ảnh, script, font hoặc iframe chưa opt-in.

Không nhầm COEP Report-Only với enforcement header Cross-Origin-Embedder-Policy. Khi đã sẵn sàng, chuyển policy sang header enforcement và tiếp tục theo dõi.

### 8.2 Dữ liệu report

COEP violation report có thể cung cấp:

- URL tài liệu phát sinh violation.
- URL tài nguyên bị chặn hoặc bị đánh giá.
- Destination/resource type như image, script hoặc iframe.
- Loại violation, ví dụ CORP.
- Disposition là reporting hay enforce theo định dạng report.

Các trường có thể thiếu hoặc bị rút gọn tùy browser. Report endpoint phải giới hạn kích thước, tần suất và không render dữ liệu thô bằng HTML sink.

### 8.3 ReportingObserver

Có thể quan sát một số report trong trang:

~~~js
if ('ReportingObserver' in window) {
  const observer = new ReportingObserver((reports) => {
    for (const report of reports) {
      console.log('Report type:', report.type);
      console.log('Report body:', report.body);
    }
  }, {
    types: ['coep'],
    buffered: true
  });

  observer.observe();
}
~~~

Đây là công cụ chẩn đoán. Không coi report là bằng chứng duy nhất của tấn công hoặc là danh sách đầy đủ mọi resource bị ảnh hưởng. Hãy kết hợp DevTools Network, Console, response header và kiểm thử luồng ứng dụng.

### 8.4 Không tự động allowlist tất cả violation

Một report về tài nguyên bên thứ ba không có nghĩa nên mở quyền cho domain đó. Với từng resource, hỏi:

1. Có còn được ứng dụng sử dụng không?
2. Resource có cần cookie/credential không?
3. Có thể chuyển sang CORS mode không?
4. Nhà cung cấp có thể thêm CORP không?
5. Có thể host asset tại origin của mình không?
6. Có dữ liệu riêng tư trong response không?
7. Có redirect hoặc script phụ tải từ origin khác không?

Loại bỏ dependency không cần trước khi thêm ngoại lệ.

## 9. Quy trình rollout COEP

### 9.1 Kiểm kê request trước khi bật

Thu thập request từ browser thật ở các luồng:

- Đăng nhập, logout và MFA.
- Dashboard và trang nội dung.
- Ảnh, avatar, video, font.
- Analytics, tag manager và SDK.
- Worker, service worker và WebAssembly.
- Iframe thanh toán, captcha, chat và SSO.
- Popup OAuth/OIDC hoặc payment.
- Download/upload và các route legacy.

Phân loại từng request theo origin, destination, mode (cors, no-cors, navigate), credentials và header opt-in.

### 9.2 Chọn require-corp hay credentialless

Chọn require-corp khi resource provider có thể cấu hình CORP hoặc CORS và muốn việc opt-in được thể hiện rõ.

Chọn credentialless khi cần tải một số tài nguyên cross-origin no-cors không có CORP, đồng thời các tài nguyên đó không cần cookie hoặc credential. Kiểm tra kỹ response Set-Cookie bị bỏ qua và các request có phụ thuộc trạng thái đăng nhập hay không.

Đừng chọn credentialless chỉ vì nó làm hết lỗi tải resource. Một widget cần cookie có thể ngừng hoạt động hoặc mất phiên.

### 9.3 Bật Report-Only

Đặt COEP Report-Only trên staging hoặc nhóm người dùng thử nghiệm. Theo dõi report trong các browser mục tiêu và chạy đầy đủ luồng nghiệp vụ. Phân loại từng violation và làm việc với resource provider để sửa header.

### 9.4 Bật COOP và COEP enforcement

Triển khai:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

Hoặc thay require-corp bằng credentialless theo lựa chọn đã đánh giá. Kiểm tra window.crossOriginIsolated trên mọi route HTML quan trọng.

COOP có thể ảnh hưởng popup, vì vậy triển khai và kiểm thử cùng lúc với các luồng đăng nhập/đối tác.

### 9.5 Theo dõi sau phát hành

Theo dõi:

- Ảnh, font, script và iframe bị chặn.
- Console error và COEP violation.
- crossOriginIsolated có phải true không.
- SharedArrayBuffer/worker path có hoạt động không.
- Login popup, payment, SSO và third-party widget.
- Tỷ lệ lỗi theo browser và phiên bản.
- Các dependency mới được thêm sau khi policy đã bật.

Giữ rollback plan cho header và biết rõ route nào đã phụ thuộc vào cross-origin isolation trước khi thay đổi.

## 10. Thực hành: kiểm tra require-corp và credentialless bằng Node.js

Lab dùng hai origin khác nhau theo port: trang embedder chạy ở localhost:3000, resource server chạy ở localhost:3001. Hai origin cùng host nhưng khác port nên khác-origin. Lab tạo ảnh demo, không dùng cookie hay tài khoản thật.

### 10.1 Tạo file coep-lab.mjs

~~~js
import { createServer } from 'node:http';

const mode = process.env.COEP_MODE || 'require-corp';
if (!['require-corp', 'credentialless'].includes(mode)) {
  throw new Error('COEP_MODE must be require-corp or credentialless');
}

const png = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jXioAAAAASUVORK5CYII=',
  'base64'
);

const page = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head><meta charset="utf-8"><title>COEP lab</title></head>',
  '<body>',
  '<h1>COEP mode: ' + mode + '</h1>',
  '<p id="isolation"></p>',
  '<h2>no-cors image không có CORP</h2>',
  '<img src="http://localhost:3001/no-corp.png" alt="No CORP">',
  '<h2>no-cors image có CORP cross-origin</h2>',
  '<img src="http://localhost:3001/corp.png" alt="CORP opt-in">',
  '<h2>CORS image có ACAO</h2>',
  '<img src="http://localhost:3001/cors.png" crossorigin="anonymous" alt="CORS opt-in">',
  '<script>',
  'document.querySelector("#isolation").textContent =',
  '  "crossOriginIsolated: " + window.crossOriginIsolated;',
  'if (window.crossOriginIsolated && typeof SharedArrayBuffer !== "undefined") {',
  '  const shared = new SharedArrayBuffer(16);',
  '  const view = new Int32Array(shared);',
  '  Atomics.store(view, 0, 42);',
  '  document.querySelector("#isolation").textContent +=',
  '    " | SharedArrayBuffer OK: " + Atomics.load(view, 0);',
  '}',
  '</script>',
  '</body></html>'
].join('\n');

const parent = createServer((req, res) => {
  if (req.url !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Cross-Origin-Opener-Policy': 'same-origin',
    'Cross-Origin-Embedder-Policy': mode
  });
  res.end(page);
});

const resources = createServer((req, res) => {
  if (!req.url?.endsWith('.png')) {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.setHeader('Content-Type', 'image/png');
  res.setHeader('Cache-Control', 'no-store');

  if (req.url === '/corp.png') {
    res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  }

  if (req.url === '/cors.png') {
    res.setHeader('Access-Control-Allow-Origin', '*');
  }

  res.writeHead(200);
  res.end(png);
});

parent.listen(3000, 'localhost', () => {
  console.log('Embedder: http://localhost:3000');
  console.log('COEP mode:', mode);
});

resources.listen(3001, 'localhost', () => {
  console.log('Resources: http://localhost:3001');
});
~~~

### 10.2 Chạy với require-corp

~~~bash
node coep-lab.mjs
~~~

Mở http://localhost:3000 và xem DevTools Console/Network:

- Ảnh /no-corp.png được request ở no-cors và không có CORP nên bị COEP chặn.
- Ảnh /corp.png có Cross-Origin-Resource-Policy: cross-origin nên được phép nhúng.
- Ảnh /cors.png dùng crossorigin="anonymous" và server trả Access-Control-Allow-Origin: *, nên request CORS hợp lệ.
- Trang hiển thị crossOriginIsolated: true trong browser hỗ trợ và nếu không có policy khác chặn.

### 10.3 Chạy với credentialless

Dừng server, sau đó chạy:

~~~bash
COEP_MODE=credentialless node coep-lab.mjs
~~~

Trên PowerShell:

~~~powershell
$env:COEP_MODE = "credentialless"
node coep-lab.mjs
~~~

Khi dùng credentialless:

- Ảnh /no-corp.png có thể được tải dù không có CORP vì request no-cors không gửi credential.
- Ảnh /corp.png vẫn được phép nhờ CORP.
- Ảnh /cors.png vẫn cần CORS hợp lệ.
- crossOriginIsolated có thể là true khi COOP/COEP và các điều kiện khác đáp ứng.

### 10.4 Quan sát header và thử nghiệm

Trong Network, chọn response document ở port 3000 và xác minh:

~~~http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
~~~

hoặc:

~~~http
Cross-Origin-Embedder-Policy: credentialless
~~~

Chọn từng ảnh ở port 3001 để kiểm tra response header. Dùng Console để quan sát COEP violation của ảnh không có CORP trong chế độ require-corp.

Lab không kiểm tra cookie stripping bằng dữ liệu người dùng. Hành vi credentialless được minh họa qua việc cho phép no-cors resource không có CORP; trong ứng dụng thật, hãy xác minh request không gửi cookie và cookie trong response bị bỏ qua theo browser.

Sau lab, dừng cả hai server.

## 11. Chẩn đoán lỗi COEP

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ảnh cross-origin biến mất sau khi bật require-corp | Request no-cors và response thiếu CORP | Yêu cầu resource provider thêm CORP hoặc dùng CORS nếu hỗ trợ |
| Script CDN bị chặn | Script no-cors không có CORP phù hợp | Dùng crossorigin với CORS hợp lệ hoặc yêu cầu CDN cấu hình CORP |
| Font không tải | Font server thiếu CORS header hoặc request mode không phù hợp | Kiểm tra font response và ACAO |
| Fetch CORS thất bại | Server không cho phép origin hoặc credentials mode | Sửa CORS; COEP không thay thế CORS |
| Credentialless làm widget mất đăng nhập | Request no-cors không gửi cookie và cookie response bị bỏ qua | Chọn require-corp/CORS hoặc thiết kế resource không phụ thuộc credential |
| Iframe bên thứ ba không hiển thị | Document/redirect hoặc resource con không đáp ứng policy | Kiểm tra cả chuỗi frame và header của từng response |
| crossOriginIsolated là false | Thiếu COOP/COEP, policy bị xóa hoặc Permissions Policy chặn | Kiểm tra response document và cross-origin-isolated |
| SharedArrayBuffer không tồn tại/không dùng được | Document chưa isolated hoặc browser không hỗ trợ | Kiểm tra crossOriginIsolated, feature detection và browser |
| Popup OAuth bị tách khỏi opener | COOP same-origin thay đổi browsing context group | Thiết kế lại callback/message flow và kiểm thử SSO |
| Resource có CORP nhưng vẫn bị chặn | CORP value không cho phép embedder hoặc request khác origin dự kiến | So sánh origin/site thực tế và giá trị CORP |
| Report-Only có violation nhưng trang vẫn tải | Đây là hành vi mong đợi của Report-Only | Sửa dependency rồi chuyển sang enforcement |
| Một số route isolated, route khác không | Header không được áp dụng nhất quán hoặc route nhận response khác | Kiểm tra mọi response HTML và cấu hình proxy/CDN |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** COEP kiểm soát loại request cross-origin nào?

**Đáp án:** COEP chủ yếu kiểm soát tài nguyên cross-origin được tải ở chế độ no-cors. Request cors vẫn phải vượt qua CORS.

**Câu 2.** require-corp yêu cầu gì từ resource cross-origin no-cors?

**Đáp án:** Response phải có CORP cho phép embedder, ví dụ same-site hoặc cross-origin tùy quan hệ và nhu cầu; nếu không, browser chặn resource.

**Câu 3.** credentialless thay đổi điều gì?

**Đáp án:** Cho phép cross-origin no-cors resource không có CORP nhưng loại cookie/credential khỏi request và bỏ qua cookie trong response.

**Câu 4.** CORP khác CORS thế nào?

**Đáp án:** CORP là opt-in của resource provider cho việc nhúng trong no-cors; CORS kiểm soát việc JavaScript có được đọc response cross-origin hay không.

**Câu 5.** Cross-Origin-Resource-Policy: same-site có đồng nghĩa same-origin không?

**Đáp án:** Không. Các subdomain có thể khác origin nhưng cùng site; same-site rộng hơn same-origin.

**Câu 6.** COEP require-corp có chặn một request CORS hợp lệ không?

**Đáp án:** Không. Request CORS được đánh giá theo CORS; server vẫn phải cho phép origin và credentials mode nếu cần.

**Câu 7.** Những header nào thường cần để bật cross-origin isolation?

**Đáp án:** Cross-Origin-Opener-Policy: same-origin và Cross-Origin-Embedder-Policy: require-corp hoặc credentialless; Permissions Policy cũng không được chặn cross-origin-isolated.

**Câu 8.** Làm sao kiểm tra document đã isolated?

**Đáp án:** Kiểm tra window.crossOriginIsolated trong document hoặc self.crossOriginIsolated trong worker.

**Câu 9.** Vì sao COOP có thể làm hỏng popup OAuth?

**Đáp án:** COOP same-origin có thể tách browsing context group và cắt quan hệ opener với popup cross-origin; cần kiểm thử lại luồng callback và postMessage.

**Câu 10.** Có nên dùng credentialless cho API cần cookie đăng nhập không?

**Đáp án:** Không nên nếu request là cross-origin no-cors và phụ thuộc cookie. Credentialless bỏ cookie; hãy thiết kế CORS/credential flow phù hợp hoặc dùng resource không cần credential.

## 13. Checklist triển khai COEP

Trước khi bật enforcement, hãy kiểm tra:

1. **Resource inventory:** đã kiểm kê image, script, stylesheet, font, media, worker, iframe và SDK chưa?
2. **Request mode:** xác định resource nào no-cors, resource nào CORS và resource nào navigate.
3. **CORP:** resource provider đã trả same-origin, same-site hoặc cross-origin đúng phạm vi chưa?
4. **CORS:** API/script/font/image cần CORS đã có ACAO và credentials policy phù hợp chưa?
5. **Policy choice:** chọn require-corp khi cần opt-in rõ; chọn credentialless chỉ khi no-cors resource không cần cookie/credential.
6. **COOP:** đánh giá same-origin và tác động lên popup, OAuth, payment, opener và postMessage.
7. **Permissions Policy:** không chặn cross-origin-isolated ở document cần tính năng.
8. **Iframe:** kiểm tra origin, redirect, nested frame, sandbox và policy của document con.
9. **Worker:** kiểm tra worker script, import, blob URL và CSP worker-src.
10. **Report-Only:** thu thập violation trên luồng thực tế trước enforcement.
11. **Cross-origin isolation:** xác minh crossOriginIsolated ở document và worker; feature-detect SharedArrayBuffer.
12. **Deployment:** kiểm tra response header trên mọi route HTML và qua CDN/reverse proxy.
13. **Fallback:** chuẩn bị đường chạy không SharedArrayBuffer hoặc API có hạn chế hơn khi browser không isolated.
14. **Maintenance:** rà soát dependency mới, CORP/CORS và popup flow sau mỗi lần tích hợp.

**Ghi nhớ:** COEP quyết định tài liệu có chấp nhận tài nguyên cross-origin no-cors hay không. require-corp yêu cầu resource opt-in bằng CORP; credentialless cho phép no-cors resource không có CORP nhưng bỏ credential. Request CORS vẫn cần CORS. Khi kết hợp COEP với COOP same-origin, kiểm tra crossOriginIsolated để xác nhận document thực sự đạt cross-origin isolation.

## Tài liệu tham khảo

- [MDN — Cross-Origin-Embedder-Policy (COEP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy)
- [MDN — Cross-Origin-Resource-Policy (CORP)](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/CORP)
- [MDN — Cross-Origin-Opener-Policy (COOP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy)
- [MDN — Window.crossOriginIsolated](https://developer.mozilla.org/en-US/docs/Web/API/Window/crossOriginIsolated)
- [MDN — COEP Report-Only](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy-Report-Only)
- [W3C — Cross-Origin-Embedder-Policy](https://html.spec.whatwg.org/multipage/origin.html#cross-origin-embedder-policy)
- [WHATWG HTML — Cross-origin isolation](https://html.spec.whatwg.org/multipage/webappapis.html#cross-origin-isolated-capability)

