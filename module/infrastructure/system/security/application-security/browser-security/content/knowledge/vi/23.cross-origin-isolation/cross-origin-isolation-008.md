# Kiểm tra isolation: xác minh trạng thái cross-origin isolated của trang

Cross-origin isolation là trạng thái bảo mật của một browsing context, trong đó trình duyệt áp dụng các giới hạn chặt hơn đối với quan hệ giữa cửa sổ và tài nguyên cross-origin. Khi được cấu hình đúng, ứng dụng có thể sử dụng một số khả năng nhạy cảm với timing hoặc bộ nhớ chia sẻ, điển hình là **SharedArrayBuffer** và các phép đo hiệu năng có độ chính xác cao hơn. Trạng thái này không được xác định chỉ bằng một header đơn lẻ: cần kiểm tra điều kiện bảo mật, chính sách của tài liệu, tài nguyên con, iframe, worker và hành vi thực tế của trình duyệt.

Điểm kiểm tra trực tiếp nhất trong JavaScript là **window.crossOriginIsolated**. Giá trị **true** cho biết môi trường hiện tại đang ở trạng thái cross-origin isolated theo trình duyệt. Giá trị **false** cho biết điều kiện chưa được đáp ứng hoặc môi trường không hỗ trợ. Đọc giá trị này là bước xác nhận cuối, nhưng để tìm nguyên nhân cần kiểm tra các response header như COOP, COEP, CORP và CORS trong Network/Console.

Bài học thuộc chương **Cross-origin isolation**, trong phạm vi **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**: phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web; hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Kiểm tra trạng thái isolation bằng **crossOriginIsolated**.
2. Giải thích vai trò của COOP và COEP trong việc tạo cross-origin isolated browsing context.
3. Phân biệt **Cross-Origin-Resource-Policy** với CORS và hiểu khi nào mỗi cơ chế được dùng.
4. Xác định resource, iframe hoặc worker làm hỏng điều kiện isolation.
5. Kiểm tra điều kiện sử dụng **SharedArrayBuffer** và **Atomics**.
6. Dùng DevTools để tìm response header thiếu hoặc không tương thích.
7. Triển khai COOP/COEP theo từng giai đoạn và kiểm thử tác động tới popup, embed và dependency bên thứ ba.
8. Phân biệt trạng thái isolation với authentication, authorization và Same-Origin Policy.

## 2. Cross-origin isolation là gì?

Trình duyệt có nhiều cơ chế bảo vệ ranh giới giữa các origin. Cross-origin isolation bổ sung một mức cách ly cho browsing context, giúp trình duyệt biết rằng tài liệu đã chủ động áp dụng các chính sách cần thiết để hạn chế tương tác với tài nguyên và cửa sổ cross-origin.

Ở cấp ứng dụng, trạng thái này thường được quan tâm khi cần:

- Dùng **SharedArrayBuffer** để chia sẻ vùng nhớ giữa main thread và worker.
- Dùng **Atomics** để đồng bộ truy cập shared memory.
- Sử dụng các phép đo thời gian có độ phân giải cao hơn trong những trình duyệt hỗ trợ.
- Chạy workload tính toán hiệu năng cao, ví dụ xử lý media, mô phỏng hoặc thư viện WebAssembly đa luồng.

Cross-origin isolation **không** có nghĩa là:

- Trang được phép đọc DOM của mọi origin khác.
- CORS được tự động bật cho API.
- Tất cả tài nguyên cross-origin đều trở nên đáng tin.
- Người dùng đã đăng nhập hoặc có quyền thực hiện một thao tác.
- Ứng dụng được miễn kiểm tra XSS, CSRF hoặc clickjacking.

SOP và CORS vẫn hoạt động theo quy tắc riêng. Isolation là một điều kiện bổ sung về cách trình duyệt tổ chức browsing context và chấp nhận tài nguyên nhúng.

## 3. Kiểm tra trạng thái bằng crossOriginIsolated

Trong Console của trang hoặc trong JavaScript:

```js
console.log(window.crossOriginIsolated);
```

Trong worker có thể kiểm tra:

```js
console.log(self.crossOriginIsolated);
```

Giá trị là boolean:

| Giá trị | Ý nghĩa |
| --- | --- |
| true | Context hiện tại được trình duyệt xác nhận là cross-origin isolated. |
| false | Context chưa đáp ứng điều kiện hoặc trình duyệt/môi trường hiện tại không cung cấp trạng thái này. |

Đây là tín hiệu runtime đáng tin cậy hơn việc chỉ nhìn thấy header trong cấu hình server. Một header có thể bị reverse proxy loại bỏ, bị ghi đè, chỉ áp dụng cho một số route hoặc không đáp ứng do resource con.

### Kiểm tra thêm các API phụ thuộc isolation

Ví dụ:

```js
const isolationReport = {
  crossOriginIsolated: window.crossOriginIsolated,
  sharedArrayBufferAvailable:
    typeof SharedArrayBuffer !== 'undefined',
  atomicsAvailable:
    typeof Atomics !== 'undefined'
};

console.table(isolationReport);
```

SharedArrayBuffer có thể không khả dụng dù một số API khác tồn tại, tùy trình duyệt và môi trường. Vì vậy hãy kiểm tra cả trạng thái isolation lẫn API thực sự mà tính năng cần.

Không dùng riêng typeof SharedArrayBuffer làm kết luận cho toàn bộ cấu hình. Một số môi trường có thể ẩn constructor hoặc hạn chế API vì lý do tương thích và chính sách nền tảng.

## 4. Những điều kiện thường cần để có cross-origin isolation

Trong các trình duyệt hiện đại hỗ trợ cơ chế này, một trang web thông thường cần được phục vụ trong secure context và có chính sách:

- **Cross-Origin-Opener-Policy: same-origin**
- **Cross-Origin-Embedder-Policy: require-corp** hoặc **credentialless**

Ví dụ:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Sau khi cấu hình, phải xác nhận bằng crossOriginIsolated. Việc có hai header trong một file cấu hình chưa chứng minh response thực tế hoặc toàn bộ dependency đáp ứng yêu cầu.

### Secure context

Ứng dụng production nên dùng HTTPS. localhost thường được xem là potentially trustworthy để phục vụ phát triển local, nhưng các host và môi trường webview khác có thể có quy tắc riêng. Hãy kiểm tra isSecureContext:

```js
console.log(window.isSecureContext);
```

Nếu trang không ở secure context, các khả năng liên quan có thể không được cung cấp ngay cả khi header có mặt.

### COOP và COEP giải quyết hai phần khác nhau

| Header | Vai trò |
| --- | --- |
| COOP | Kiểm soát việc tài liệu chia sẻ browsing context group và quan hệ window.opener với cửa sổ cross-origin. |
| COEP | Yêu cầu tài liệu chỉ sử dụng tài nguyên nhúng cross-origin khi tài nguyên đó đáp ứng điều kiện CORS/CORP hoặc cơ chế được phép. |
| CORP | Do response của resource khai báo ai được phép nhúng/tải resource trong các request no-CORS phù hợp. |
| CORS | Cho phép một origin khác thực hiện request và đọc response theo chính sách của server. |

COOP và COEP thường phải phối hợp. Chỉ đặt COOP không tự làm mọi tài nguyên con tương thích; chỉ đặt COEP cũng không thay thế điều kiện COOP cho trạng thái isolation thông thường.

## 5. COOP: Cross-Origin-Opener-Policy

COOP kiểm soát quan hệ giữa một document và các browsing context được mở từ nó hoặc mở nó. Chính sách này có thể đặt các trang vào browsing context group khác nhau, hạn chế khả năng tương tác qua window.opener giữa các nhóm.

### same-origin

```http
Cross-Origin-Opener-Policy: same-origin
```

Đây là lựa chọn thường dùng để đạt cross-origin isolation. Document chỉ giữ quan hệ opener trong điều kiện same-origin theo quy tắc COOP. Khi mở hoặc được mở bởi trang cross-origin, trình duyệt có thể tách browsing context group và làm mất quan hệ opener mà ứng dụng cũ đang dựa vào.

### same-origin-allow-popups

```http
Cross-Origin-Opener-Policy: same-origin-allow-popups
```

Chính sách này giữ một số quan hệ với popup có COOP mặc định/không tách nhóm theo cách same-origin thực hiện. Nó có thể hữu ích với luồng OAuth hoặc thanh toán dùng popup, nhưng **không phải lựa chọn thay thế tương đương để đạt cross-origin isolation** trong cấu hình phổ biến.

### unsafe-none

```http
Cross-Origin-Opener-Policy: unsafe-none
```

Đây là hành vi mặc định trong nhiều tình huống nếu không có chính sách COOP mạnh hơn. Nó cho phép quan hệ browsing context rộng hơn. Không dùng unsafe-none khi mục tiêu là isolation.

### Tác động tới popup và OAuth

Khi COOP tách browsing context group, ứng dụng có thể quan sát:

- window.opener ở popup hoặc trang mở có thể trở thành null.
- Các phép kiểm tra popup.closed và giao tiếp dựa trên opener có thể thay đổi theo cách browser triển khai.
- Callback OAuth/payment dựa vào popup và opener có thể cần chuyển sang redirect hoặc postMessage với origin cụ thể.
- Các luồng thanh toán, đăng nhập liên kết và tích hợp bên thứ ba cần kiểm thử end-to-end.

Không hạ COOP chỉ để sửa một popup mà chưa đánh giá rủi ro. Hãy điều chỉnh luồng tích hợp và chọn policy phù hợp với yêu cầu bảo mật.

## 6. COEP: Cross-Origin-Embedder-Policy

COEP kiểm soát việc tài liệu tải hoặc nhúng tài nguyên cross-origin. Với require-corp, tài nguyên cross-origin được tải theo kiểu no-CORS cần có CORP phù hợp; nếu tài nguyên được yêu cầu theo CORS, server phải trả CORS header hợp lệ.

### require-corp

```http
Cross-Origin-Embedder-Policy: require-corp
```

Đây là chế độ chặt chẽ. Một resource cross-origin được nhúng bằng request no-CORS cần chủ động cho phép thông qua Cross-Origin-Resource-Policy phù hợp. Với tài nguyên cần đọc bằng CORS, server phải cấp Access-Control-Allow-Origin và các header cần thiết theo request.

Nếu một ảnh, font, script, stylesheet, media hoặc iframe bên thứ ba không đáp ứng chính sách, trình duyệt có thể chặn nó. Vì vậy COEP cần được kiểm thử trên toàn bộ tài nguyên của ứng dụng.

### credentialless

```http
Cross-Origin-Embedder-Policy: credentialless
```

Chế độ này cho phép một số request cross-origin no-CORS được tải mà không gửi credential, đồng thời không yêu cầu response phải có CORP trong trường hợp đó theo mô hình credentialless. Nó có thể giúp tương thích với một số tài nguyên công khai không thiết lập CORP.

Credentialless không có nghĩa là mọi request đều bỏ cookie hoặc mọi resource được phép. Request CORS, tài nguyên có credential và các loại nhúng khác vẫn chịu các quy tắc tương ứng. Cần kiểm thử hành vi thực tế với tài nguyên của sản phẩm và browser mục tiêu.

### COEP không phải CORS

COEP không tự cấp quyền cho JavaScript đọc response cross-origin. Nếu JavaScript dùng fetch() tới API khác origin, server API vẫn cần cấu hình CORS phù hợp. Ngược lại, CORS hợp lệ không tự đảm bảo một tài nguyên no-CORS có thể được nhúng dưới COEP require-corp.

## 7. CORP: Cross-Origin-Resource-Policy

CORP là response header do **server cung cấp tài nguyên** gửi để khai báo những site/origin nào có thể nhúng tài nguyên đó trong các request no-CORS được áp dụng.

Ví dụ:

```http
Cross-Origin-Resource-Policy: same-origin
```

Các giá trị thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| same-origin | Chỉ cho phép request từ cùng origin theo quy tắc CORP. |
| same-site | Cho phép từ cùng site, dù có thể khác origin. |
| cross-origin | Cho phép các origin khác sử dụng resource trong những ngữ cảnh CORP áp dụng. |

### Chọn CORP theo mục đích resource

- Ảnh nội bộ chỉ dùng trong cùng origin có thể đặt same-origin.
- Ảnh công khai được dùng trên nhiều subdomain cùng site có thể cần same-site.
- Font, ảnh hoặc script công khai được nhúng từ nhiều site có thể cần cross-origin, hoặc dùng CORS nếu loại request yêu cầu.

Không đặt same-origin một cách máy móc cho mọi resource của CDN nếu nhiều ứng dụng hợp lệ cần nhúng chúng. Ngược lại, không đặt cross-origin cho tài nguyên riêng tư chỉ để làm COEP hết lỗi.

CORP không thay thế authentication. Một resource được cho phép nhúng cross-origin vẫn có thể cần xác thực ở tầng ứng dụng nếu chứa dữ liệu riêng tư.

## 8. CORS và CORP khác nhau thế nào?

Hai cơ chế thường xuất hiện cùng lúc nhưng giải quyết các vấn đề khác nhau:

| Đặc điểm | CORS | CORP |
| --- | --- | --- |
| Nơi khai báo | Response của server resource | Response của server resource |
| Mục đích | Cho phép JavaScript ở origin khác đọc response theo CORS | Kiểm soát việc nhúng/tải resource trong các request no-CORS phù hợp |
| Header điển hình | Access-Control-Allow-Origin | Cross-Origin-Resource-Policy |
| Phạm vi | Fetch/XHR và các request CORS khác | Resource embedding theo CORP, đặc biệt no-CORS |
| Kết quả | Response có thể được expose cho script nếu các điều kiện CORS hợp lệ | Browser cho phép hoặc chặn việc sử dụng resource theo chính sách CORP |

Ví dụ API trả:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

để cho phép origin cụ thể đọc response qua CORS. Một ảnh công khai trả:

```http
Cross-Origin-Resource-Policy: cross-origin
```

có thể cho phép nhúng trong một số request no-CORS từ site khác. Không thay một header bằng header còn lại.

### CORS credentialed request

Nếu fetch dùng credentials, server thường cần trả origin cụ thể thay vì wildcard và cho phép credentials:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

COEP không tự sửa cấu hình CORS sai. Nếu response thiếu header hoặc origin không khớp, JavaScript vẫn không đọc được response.

## 9. Tài nguyên con có thể làm isolation thất bại

Một trang có thể trả đúng COOP/COEP nhưng vẫn không đạt trạng thái isolation vì một dependency hoặc response con không tương thích.

Những vị trí cần kiểm tra:

- Ảnh, font, script, stylesheet và media từ CDN.
- fetch()/XHR tới API khác origin.
- iframe, video player, widget, bản đồ và cổng thanh toán.
- Worker script, module worker và các tài nguyên worker import.
- Popup hoặc cửa sổ đăng nhập OAuth.
- Service worker và các route được phục vụ từ cache.
- Redirect qua nhiều host hoặc proxy làm thay đổi header.

### Iframe cross-origin

COEP của trang cha có thể làm iframe cross-origin không được tải nếu tài liệu/response con không đáp ứng yêu cầu embedding. Iframe cũng có thể cần chính sách COEP riêng nếu nó phải hoạt động như một context cross-origin isolated. Không giả định việc cha đã isolated thì mọi iframe con tự động isolated.

Với iframe bên thứ ba, hãy kiểm tra nhà cung cấp có hỗ trợ COEP/CORP và cách tích hợp được khuyến nghị hay không. Nếu không thể thay đổi header phía nhà cung cấp, cân nhắc bỏ iframe đó khỏi trang cần isolation, dùng một trang tích hợp riêng hoặc chọn kiến trúc khác.

### Worker

Worker script phải được tải từ nguồn hợp lệ theo quy tắc worker và CSP. Nếu dùng worker để chia sẻ SharedArrayBuffer, kiểm tra trạng thái crossOriginIsolated trong worker và document. Các worker module có thể tải thêm module/resource; kiểm tra toàn bộ dependency chứ không chỉ file entry.

## 10. Kiểm tra thực tế bằng DevTools

Khi crossOriginIsolated trả về false, kiểm tra theo thứ tự:

1. **Security context:** trang có HTTPS hoặc môi trường local đáng tin cậy không?
2. **Main document response:** COOP và COEP có thực sự xuất hiện trong Network response không?
3. **Redirect:** các response/đích redirect có làm mất hoặc thay đổi header không?
4. **Subresources:** có resource cross-origin no-CORS bị chặn bởi COEP không?
5. **Iframe:** có iframe nào không đáp ứng yêu cầu embedding hoặc làm thay đổi cấu trúc context không?
6. **Worker:** worker có tải thành công và nhận đúng môi trường/policy không?
7. **Runtime:** window.crossOriginIsolated và self.crossOriginIsolated có trả về true ở context cần dùng không?

### Network

Mở DevTools → Network, bật Preserve log nếu có redirect, tải lại trang và chọn request loại **document**. Kiểm tra Response Headers:

- Cross-Origin-Opener-Policy
- Cross-Origin-Embedder-Policy

Sau đó lọc theo Img, JS, CSS, Font, Media, Fetch/XHR và Doc. Với resource bị chặn, xem request URL, initiator, status và Console message. Chọn response của resource để kiểm tra Cross-Origin-Resource-Policy hoặc Access-Control-Allow-Origin.

### Console

Console thường ghi lý do tài nguyên không được phép nhúng dưới COEP hoặc lý do CORS thất bại. Đọc đúng thông báo và URL; đừng thêm crossorigin attribute hoặc mở rộng CORS một cách đoán mò.

### Application/Issues

Tùy phiên bản DevTools, tab Issues hoặc Application có thể hiển thị cảnh báo liên quan tới COEP/COOP, cookie và resource. Đây là tín hiệu bổ sung; response header và hành vi runtime vẫn là bằng chứng chính.

## 11. Thực hành: dựng và kiểm tra isolation trên localhost

Thực hành trên server local do người học kiểm soát. Dùng tài nguyên giả và không thay đổi header của website bên ngoài.

### 11.1. Tạo trang kiểm tra

Tạo một trang /isolation-check.html:

```html
<!doctype html>
<html lang="vi">
<meta charset="utf-8">
<title>Cross-origin isolation check</title>
<h1>Isolation check</h1>
<pre id="result"></pre>
<script src="/isolation-check.js"></script>
</html>
```

Trong /isolation-check.js:

```js
const report = {
  secureContext: window.isSecureContext,
  crossOriginIsolated: window.crossOriginIsolated,
  sharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
  atomics: typeof Atomics !== 'undefined'
};

document.querySelector('#result').textContent =
  JSON.stringify(report, null, 2);
console.table(report);
```

### 11.2. Phục vụ response header

Trên response của trang HTML, cấu hình:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Tải lại trang và quan sát crossOriginIsolated. Nếu vẫn là false, kiểm tra Network và Console trước khi thay đổi policy.

### 11.3. Thử một resource cross-origin no-CORS

Dùng một ảnh thử nghiệm từ origin local thứ hai do mình quản lý. Với COEP require-corp, response ảnh có thể cần:

```http
Cross-Origin-Resource-Policy: cross-origin
```

hoặc được tải theo CORS với response CORS hợp lệ và cách khai báo request tương ứng. Tải lại trang và quan sát ảnh có hiển thị hay bị chặn.

### 11.4. Thử CORS cho fetch

Từ trang chính, gọi API ở origin local thứ hai:

```js
fetch('http://localhost:5174/api/demo', {
  mode: 'cors'
})
  .then((response) => response.json())
  .then((data) => console.log(data))
  .catch((error) => console.error(error));
```

Trên API server, trả Access-Control-Allow-Origin phù hợp với origin của trang. Nếu CORS chưa đúng, request có thể xuất hiện trong Network nhưng JavaScript không được đọc response. CORP cross-origin không thay thế header CORS cho trường hợp fetch CORS này.

### 11.5. Thử iframe bên thứ ba

Nhúng một iframe thử nghiệm từ origin khác do mình quản lý. Quan sát với COEP require-corp, sau đó điều chỉnh response của iframe theo chính sách cần thiết. Kiểm tra response document của iframe và các tài nguyên con của chính iframe; việc chỉ sửa header ở trang cha không đảm bảo iframe hoạt động.

### 11.6. Kiểm tra SharedArrayBuffer

Khi crossOriginIsolated là true và browser hỗ trợ:

```js
const buffer = new SharedArrayBuffer(16);
const view = new Int32Array(buffer);

Atomics.store(view, 0, 42);
console.log(Atomics.load(view, 0)); // 42
```

Nếu constructor không khả dụng, quay lại kiểm tra secure context, COOP, COEP, browser support và response thực tế. Không dùng kết quả trên một browser làm cam kết cho mọi webview.

### 11.7. Thử COEP credentialless

Trong môi trường thử nghiệm riêng, đổi:

```http
Cross-Origin-Embedder-Policy: require-corp
```

thành:

```http
Cross-Origin-Embedder-Policy: credentialless
```

So sánh resource cross-origin no-CORS công khai có thể tải trong hai chế độ. Quan sát cookie/credential của request trong Network và xác nhận hành vi trên browser mục tiêu. Không suy ra credentialless loại bỏ credential cho tất cả loại request.

### 11.8. Bằng chứng cần lưu

| Bằng chứng | Điều cần xác nhận |
| --- | --- |
| Main document response | COOP và COEP được server gửi đúng. |
| Runtime report | isSecureContext và crossOriginIsolated có giá trị mong đợi. |
| Subresource response | CORP hoặc CORS phù hợp với kiểu request. |
| Console/Network | Resource bị chặn có nguyên nhân và initiator xác định được. |
| Iframe/worker | Context con tải được và có trạng thái isolation đúng yêu cầu. |
| SharedArrayBuffer | API hoạt động ở context cần dùng khi browser hỗ trợ. |
| Popup flow | Luồng OAuth/thanh toán vẫn hoạt động sau khi COOP được bật. |

## 12. Rollout trong ứng dụng thực tế

Không nên bật COEP require-corp trên toàn bộ production mà chưa kiểm kê dependency. Một tài nguyên ảnh, font hoặc iframe không có header tương thích có thể biến mất sau deploy.

Quy trình triển khai gợi ý:

1. Lập danh sách subresource, iframe, worker, popup và API cross-origin.
2. Xác định tài nguyên nào cần CORS, tài nguyên nào có thể dùng CORP, tài nguyên nào không nên nhúng.
3. Kiểm tra nhà cung cấp CDN/widget có hỗ trợ các header cần thiết.
4. Dùng chế độ report-only nếu browser và hạ tầng hỗ trợ để quan sát vi phạm trước khi enforce.
5. Triển khai trên staging và kiểm tra luồng đăng nhập, thanh toán, popup, media và worker.
6. Bật COOP/COEP trên nhóm route cần isolation, không nhất thiết toàn bộ site.
7. Xác nhận crossOriginIsolated tại runtime trên browser mục tiêu.
8. Theo dõi lỗi sau deploy và có phương án rollback header rõ ràng.

### Report-Only

Có thể sử dụng các header báo cáo COOP/COEP phù hợp với browser và hạ tầng để thu thập vi phạm trước khi enforcement. Ví dụ tên header gồm Cross-Origin-Opener-Policy-Report-Only và Cross-Origin-Embedder-Policy-Report-Only. Khả năng hỗ trợ và cơ chế Reporting API thay đổi theo browser; kiểm tra tài liệu triển khai hiện hành trước khi dựa vào chúng.

Report-Only giúp quan sát, nhưng không tạo cross-origin isolated context. Phải bật policy enforcement thực tế rồi xác minh crossOriginIsolated.

### Chọn route và host riêng khi cần

Nếu chỉ một công cụ tính toán cần SharedArrayBuffer, cân nhắc triển khai nó trên một route hoặc subdomain riêng với COOP/COEP. Điều này có thể giảm ảnh hưởng tới luồng popup, tích hợp thanh toán và nội dung bên thứ ba của phần còn lại.

Tuy nhiên, tách subdomain tạo ranh giới origin mới. Cần thiết kế lại cookie, xác thực, CORS, postMessage và quyền truy cập dữ liệu giữa ứng dụng chính với công cụ đó.

## 13. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| crossOriginIsolated là false | Thiếu COOP/COEP, không secure context hoặc browser không hỗ trợ | Kiểm tra runtime và main document response. |
| Header có trong config nhưng không có trong Network | Reverse proxy/CDN/redirect loại bỏ hoặc ghi đè header | Kiểm tra response cuối cùng tới browser. |
| Ảnh/font cross-origin bị chặn | COEP require-corp nhưng resource thiếu CORP/CORS phù hợp | Xem request mode, response header và Console. |
| fetch API không đọc được response | CORS không cho origin hiện tại đọc response | Kiểm tra ACAO, credentials và preflight. |
| Iframe biến mất sau deploy | Tài liệu hoặc resource con không đáp ứng COEP | Kiểm tra response của iframe và dependency bên trong. |
| Popup OAuth không hoạt động | COOP thay đổi browsing context group/opener relationship | Kiểm thử luồng popup và thiết kế callback khác. |
| SharedArrayBuffer không khả dụng | Isolation chưa đạt, browser không hỗ trợ hoặc API bị giới hạn | Kiểm tra crossOriginIsolated, secure context và runtime API. |
| Chỉ một worker không isolated | Worker hoặc cách tạo worker/resource không đáp ứng yêu cầu | Kiểm tra worker script, response và self.crossOriginIsolated. |

### Đừng sửa lỗi bằng cách mở toàn bộ tài nguyên

Khi COEP chặn resource, không hạ toàn bộ chính sách hoặc thêm cross-origin cho mọi server một cách tự động. Hãy xác định resource có cần thiết không, ai sở hữu nó và dữ liệu có công khai không. Với tài nguyên riêng tư, chọn cơ chế xác thực và CORS phù hợp; với tài nguyên không cần thiết, bỏ khỏi trang isolation.

## 14. Checklist kiểm tra isolation

| Hạng mục | Câu hỏi rà soát | Kết quả mong đợi |
| --- | --- | --- |
| Secure context | Trang có isSecureContext === true không? | HTTPS hoặc môi trường phát triển đáng tin cậy. |
| COOP | Main document có COOP phù hợp không? | same-origin khi mục tiêu là isolation thông thường. |
| COEP | Main document có COEP phù hợp không? | require-corp hoặc credentialless theo browser và yêu cầu. |
| Runtime | crossOriginIsolated có true ở context cần dùng không? | Xác nhận trực tiếp trong document/worker. |
| CORP | Resource no-CORS cross-origin có CORP phù hợp không? | Chỉ cho phép đúng site/origin cần nhúng. |
| CORS | Fetch/API cross-origin có CORS đúng không? | Origin cụ thể, credentials và preflight phù hợp. |
| Iframe | Tài liệu iframe và tài nguyên con có tương thích COEP không? | Kiểm tra toàn bộ frame tree. |
| Worker | Worker script và module import có tải thành công không? | Xác nhận runtime trong worker. |
| Popup | OAuth/payment có phụ thuộc opener không? | Có luồng thay thế được kiểm thử. |
| Shared memory | Có thật sự cần SharedArrayBuffer không? | Chỉ bật khi có use case và đồng bộ đúng bằng Atomics. |
| Compatibility | Browser/webview mục tiêu có hỗ trợ không? | Có fallback và kiểm thử theo engine. |
| Monitoring | Có theo dõi COOP/COEP violation không? | Có báo cáo, phân loại và owner xử lý. |

## 15. Câu hỏi tự kiểm tra

1. crossOriginIsolated cho biết điều gì và vì sao cần kiểm tra runtime thay vì chỉ xem cấu hình server?
2. COOP và COEP đảm nhiệm hai phần nào trong cross-origin isolation?
3. Vì sao Cross-Origin-Opener-Policy: same-origin-allow-popups không phải lựa chọn tương đương same-origin cho isolation?
4. COEP require-corp yêu cầu gì ở resource cross-origin no-CORS?
5. COEP credentialless khác require-corp như thế nào và vì sao không có nghĩa mọi request đều bỏ credential?
6. CORP và CORS khác nhau ở mục đích và loại request nào?
7. Vì sao CORS hợp lệ cho fetch không tự bảo đảm ảnh no-CORS được nhúng dưới COEP?
8. Những dependency nào thường làm isolation thất bại?
9. Vì sao COOP có thể ảnh hưởng popup OAuth và thanh toán?
10. Làm thế nào dùng Network, Console và crossOriginIsolated để tìm nguyên nhân context chưa isolated?

**Tiêu chí hoàn thành:** người học có thể xác minh trạng thái cross-origin isolation tại runtime, giải thích và kiểm tra COOP/COEP/CORP/CORS, tìm resource hoặc frame/worker gây thất bại, xác nhận khả năng dùng SharedArrayBuffer khi được hỗ trợ, và triển khai chính sách theo từng giai đoạn mà vẫn kiểm soát tác động tới popup và dependency bên thứ ba.
