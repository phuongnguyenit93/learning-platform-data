# default-src và chính sách theo từng nhóm tài nguyên

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Tại sao CSP cần phân loại tài nguyên?

Một trang web hiếm khi chỉ có HTML. Trình duyệt còn tải JavaScript, CSS, ảnh, font, video, kết nối API, WebSocket, Web Worker và đôi khi cả iframe. Các nguồn tài nguyên đó có nhu cầu truy cập khác nhau: ảnh sản phẩm có thể nằm trên CDN, nhưng JavaScript không nhất thiết phải được thực thi từ CDN ấy; API có thể đặt ở một origin riêng, trong khi form đăng nhập chỉ nên gửi về chính ứng dụng.

**Content Security Policy (CSP)** cho phép ứng dụng đặt quy tắc theo từng loại tài nguyên. CSP là lớp bảo vệ do trình duyệt thực thi khi nhận header HTTP `Content-Security-Policy` từ server. Trong bộ directive của CSP, **`default-src` cung cấp nguồn dự phòng cho nhiều loại tài nguyên khi ứng dụng chưa khai báo directive chuyên biệt**.

Ví dụ khởi đầu:

~~~http
Content-Security-Policy: default-src 'self'
~~~

Chính sách này yêu cầu nhiều nhóm tài nguyên mặc định chỉ được tải từ **cùng origin** với trang. Tuy nhiên, nó không bảo đảm mọi hành vi đều bị giới hạn: chẳng hạn `form-action`, `base-uri` và `frame-ancestors` **không kế thừa** `default-src`. Một chính sách hoàn chỉnh cần khai báo thêm các directive phù hợp với chức năng và rủi ro thực tế.

Sau bài học, bạn sẽ:

1. Nêu được ý nghĩa của `default-src` và cách một directive chuyên biệt thay thế fallback.
2. Phân biệt nguồn cho script, style, ảnh, font, media, API, worker và iframe.
3. Dự đoán kết quả cho phép hoặc chặn với những ví dụ CSP cụ thể.
4. Viết chính sách cho ứng dụng Spring Security Servlet và WebFlux.
5. Kiểm thử trong trình duyệt, giải thích thông báo vi phạm và tránh cấu hình mở quá rộng.

## 2. Đọc một CSP header

Giả sử server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.net; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Đây là **một chuỗi chính sách** gồm nhiều directive ngăn cách bởi dấu chấm phẩy `;`. Với mỗi lần tải tài nguyên hoặc thực thi hành vi thuộc phạm vi CSP, trình duyệt tìm directive thích hợp để quyết định nguồn có được phép hay không.

| Thành phần | Cách hiểu |
|---|---|
| `default-src 'none'` | Mặc định không cho các nhóm tài nguyên có fallback sử dụng nguồn nào, trừ khi directive chuyên biệt cho phép |
| `script-src 'self'` | Cho phép tải script cùng origin; không tự cấp quyền chạy inline script hoặc event handler |
| `style-src 'self'` | Cho phép stylesheet cùng origin; không mặc nhiên cho inline style |
| `img-src 'self' https://images.example.net` | Cho ảnh từ cùng origin và đúng origin ảnh đã khai báo |
| `connect-src 'self' https://api.example.net` | Cho kết nối JavaScript tới các origin liệt kê |
| `object-src 'none'` | Không cho nội dung dạng `object`/`embed` |
| `base-uri 'self'` | Giới hạn URL của thẻ `<base>` |
| `form-action 'self'` | Chỉ cho form gửi đến cùng origin |
| `frame-ancestors 'none'` | Không cho các trang khác nhúng trang hiện tại vào frame |

Trong một source list:

- `'self'` chỉ **cùng origin** (scheme, hostname và port theo quy tắc của trình duyệt), không tự động gồm mọi subdomain.
- `'none'` nghĩa là không cấp phép nguồn nào. Hãy dùng riêng `'none'` cho source list đó, không trộn với những nguồn như `'self'` rồi kỳ vọng chúng cộng thêm quyền.
- `https://images.example.net` cho một nguồn cụ thể; nó khác `https:` vốn rộng hơn nhiều.
- `*` là wildcard rộng, thường không phù hợp cho script. Những giá trị đặc biệt như `'unsafe-inline'`, `'unsafe-eval'` cần hiểu tác động trước khi sử dụng.
- Các từ khóa CSP như `'self'` và `'none'` phải có dấu nháy đơn; tên directive và host không cần nháy.

**Điểm mấu chốt:** CSP không đọc `default-src` như một quy tắc luôn cộng dồn với mọi directive riêng. Khi một directive chuyên biệt được khai báo, nó được dùng theo quy tắc fallback của CSP cho hành vi tương ứng.

## 3. Cơ chế fallback của default-src

Giả sử ứng dụng chỉ gửi:

~~~http
Content-Security-Policy: default-src 'self'
~~~

Trình duyệt có thể dùng `default-src 'self'` làm nguồn dự phòng cho script, style, ảnh, font, media, kết nối và nhiều nhóm fetch khác nếu không có directive cụ thể hơn. Nhưng khi ứng dụng bổ sung:

~~~http
Content-Security-Policy: default-src 'self'; img-src https://images.example.net
~~~

quy tắc cho **ảnh** bây giờ là `img-src https://images.example.net`. Danh sách `'self'` trong `default-src` **không tự được cộng thêm** vào `img-src`: ảnh cùng origin có thể bị chặn nếu chúng không khớp danh sách nguồn của `img-src`.

Nếu ứng dụng muốn cho phép cả hai nguồn, phải viết tường minh:

~~~http
Content-Security-Policy: default-src 'self'; img-src 'self' https://images.example.net
~~~

Tương tự:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'
~~~

Ở đây, JavaScript từ cùng origin được phép tải theo `script-src`, còn các nhóm fetch chưa có directive tương ứng vẫn rơi về `default-src 'none'` và bị từ chối.

### Cây quyết định đơn giản

~~~mermaid
flowchart TD
    A[Trình duyệt cần xử lý một tài nguyên] --> B[Xác định loại tài nguyên và directive tương ứng]
    B --> C{Có directive chuyên biệt phù hợp?}
    C -- Có --> D[Đánh giá theo directive chuyên biệt]
    C -- Không --> E{Loại directive có hỗ trợ fallback?}
    E -- Có --> F[Áp dụng directive fallback theo quy tắc CSP]
    E -- Không --> G[Không suy ra giới hạn từ default-src]
    D --> H{Nguồn hoặc hành vi được phép?}
    F --> H
    H -- Có --> I[Tiếp tục các kiểm tra thông thường]
    H -- Không --> J[Chặn nếu policy đang thực thi]
~~~

Không nên diễn giải sơ đồ này thành “mọi loại tài nguyên đều fallback thẳng về `default-src`”. Một số loại có **chuỗi fallback nhiều cấp**, chẳng hạn script element, style attribute, worker và iframe. Phần tiếp theo sẽ phân biệt cụ thể.

## 4. Những nhóm tài nguyên và chuỗi fallback

Trong CSP, một số directive điều khiển các **fetch request**, một số điều khiển hành vi khác như nơi submit form hoặc quyền bị nhúng. Bảng dưới đây tập trung vào các nguồn thường gặp khi phát triển ứng dụng Spring.

| Nhóm | Directive ưu tiên | Nguồn dự phòng khi không khai báo |
|---|---|---|
| Thẻ `<script src=...>` | `script-src-elem` | `script-src` → `default-src` |
| Inline handler `onclick`/`onerror` | `script-src-attr` | `script-src` → `default-src` |
| Các quy tắc JavaScript khác trong phạm vi script | `script-src` | `default-src` |
| Thẻ `<link rel="stylesheet">` hoặc `<style>` | `style-src-elem` | `style-src` → `default-src` |
| Thuộc tính `style="..."` | `style-src-attr` | `style-src` → `default-src` |
| CSS nói chung | `style-src` | `default-src` |
| Ảnh | `img-src` | `default-src` |
| Font | `font-src` | `default-src` |
| API/fetch/XHR/WebSocket | `connect-src` | `default-src` |
| Âm thanh/video | `media-src` | `default-src` |
| Plugin/nhúng đối tượng | `object-src` | `default-src` |
| Web Worker | `worker-src` | `child-src` → `script-src` → `default-src` |
| Nội dung iframe do trang tải | `frame-src` | `child-src` → `default-src` |
| Web app manifest | `manifest-src` | `default-src` |

Các nhánh `script-src-elem`, `script-src-attr`, `style-src-elem` và `style-src-attr` là những directive chi tiết của CSP Level 3; hãy kiểm thử trên các trình duyệt được sản phẩm hỗ trợ. `child-src` vẫn có vai trò fallback ở một số nhóm, đặc biệt với worker/frame, nhưng khi cần quy tắc rõ ràng cho ứng dụng mới nên khai báo `worker-src` hoặc `frame-src`.

### Những directive **không** kế thừa default-src

| Directive | Điều khiển | Hậu quả nếu quên |
|---|---|---|
| `form-action` | Đích gửi biểu mẫu | `default-src 'none'` không tự giới hạn nơi form được submit |
| `frame-ancestors` | Những origin được phép nhúng **trang hiện tại** | `default-src` hoặc `frame-src` không thay thế việc khai báo này |
| `base-uri` | URL của thẻ `<base>` | Không được khóa bởi `default-src` |
| `sandbox` | Áp dụng các hạn chế sandbox cho tài liệu khi có trong CSP header | Không có fallback từ `default-src` |
| `upgrade-insecure-requests` | Yêu cầu nâng cấp các URL tải không an toàn có thể nâng cấp | Là directive không nhận source list và không kế thừa `default-src` |
| `report-to`/`report-uri` | Endpoint nhận báo cáo vi phạm theo cơ chế được hỗ trợ | Không quyết định nơi script, ảnh hay API được phép tải |

**Cặp tên dễ nhầm:** `frame-src` hạn chế iframe mà **trang của bạn tải vào**, còn `frame-ancestors` hạn chế website **được phép nhúng trang của bạn**. Một directive không thay thế directive còn lại.

## 5. Script: nhóm tài nguyên cần được kiểm soát chặt

JavaScript có quyền thao tác DOM, gọi API được phép và tương tác với trạng thái phía trình duyệt. Vì vậy, `script-src` là một trong những directive quan trọng nhất để giảm tác động của nội dung bị chèn.

Giả sử trang có:

~~~html
<script src="/js/app.js"></script>
<script src="https://cdn.example.net/widgets.js"></script>
<script>alert("inline")</script>
<button onclick="alert('clicked')">Bấm</button>
~~~

Với:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'
~~~

thì:

| Đoạn script | Kết quả theo CSP | Vì sao |
|---|---|---|
| `/js/app.js` | Được phép tải | Nguồn script cùng origin |
| `https://cdn.example.net/widgets.js` | Bị chặn | CDN không có trong `script-src` |
| `<script>alert(...)</script>` | Bị chặn | `'self'` không cho phép inline script |
| `onclick="..."` | Bị chặn | Event handler nội tuyến không được cấp phép |

**Phân biệt:** nếu website tự cung cấp tệp JavaScript chứa mã độc trên cùng origin, `script-src 'self'` có thể vẫn cho phép tệp đó. CSP không thể thay thế việc kiểm soát file upload, xử lý dữ liệu an toàn, escape/sanitize hoặc kiểm tra nguồn script.

### script-src-elem và script-src-attr

Khi muốn tách chính sách cho thẻ script và thuộc tính thực thi, có thể dùng:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-attr 'none'; object-src 'none'
~~~

`script-src-attr 'none'` yêu cầu chặn các thuộc tính handler như `onclick`/`onerror`; `script-src 'self'` vẫn kiểm soát các hành vi script còn lại. Nếu dùng `script-src-elem`, phải hiểu nó có quyền ưu tiên cho **script element** theo trình duyệt hỗ trợ:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-elem https://assets.example.net; script-src-attr 'none'
~~~

Theo cơ chế fallback của các directive này, thẻ `<script src="/js/app.js">` có thể **không được phép** vì `script-src-elem` đã chọn riêng `https://assets.example.net`, không tự cộng thêm `'self'` từ `script-src`. Nếu thật sự muốn cả hai nguồn, dùng `script-src-elem 'self' https://assets.example.net`.

Khi có inline script hợp lệ, nên chuyển sang file script ngoài, hoặc cân nhắc **nonce/hash** theo chính sách bảo vệ script. Nonce phải được tạo ngẫu nhiên, khó đoán và mới theo **từng HTTP response**, rồi được gắn khớp vào CSP header và script đáng tin cậy. Không dùng nonce hard-code. Tránh thêm `'unsafe-inline'` vào `script-src` để sửa nhanh một chức năng vì nó làm giảm hiệu quả chống nhiều dạng XSS.

## 6. Style, ảnh và font: phục vụ giao diện mà không mở quá rộng

### 6.1. style-src, style-src-elem và style-src-attr

Ví dụ:

~~~html
<link rel="stylesheet" href="/css/app.css">
<link rel="stylesheet" href="https://cdn.example.net/theme.css">
<style>.banner { display: block }</style>
<div style="color: red">Thông báo</div>
~~~

Với:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'
~~~

trình duyệt có thể tải `/css/app.css`, từ chối CSS từ CDN ngoài, đồng thời chặn `<style>` và thuộc tính `style` nội tuyến nếu không có cơ chế cho phép inline phù hợp. Với trình duyệt hỗ trợ CSP Level 3, `style-src-elem` và `style-src-attr` có thể đặt quy tắc riêng cho stylesheet/style element và thuộc tính style.

Điều này dễ gây lỗi với một số framework UI và thư viện CSS-in-JS tạo thẻ `<style>` hoặc cập nhật thuộc tính `style`. Khi xảy ra xung đột, hãy xác định thư viện dùng cơ chế nào rồi chọn cách phục vụ stylesheet, nonce/hash hoặc điều chỉnh thiết kế phù hợp; không tự động cho phép toàn bộ inline style.

### 6.2. img-src

Với:

~~~http
Content-Security-Policy: default-src 'none'; img-src 'self' https://images.example.net
~~~

ảnh `/images/logo.png` và `https://images.example.net/product.png` được phép theo CSP, còn ảnh từ origin ngoài danh sách bị chặn.

Một số hệ thống hiển thị ảnh ngay trong HTML theo `data:` URL, nhưng `img-src 'self'` không tự cho phép `data:`. Chỉ cân nhắc `img-src 'self' data:` nếu ứng dụng có nhu cầu hợp lệ, đã hiểu cách ảnh được tạo và kiểm soát bề mặt dữ liệu tương ứng. Không suy từ nhu cầu ảnh `data:` sang việc cho phép `data:` trong `script-src`.

### 6.3. font-src

Với CSS dùng `@font-face`, trình duyệt còn tải tệp font. Nếu CSS ở cùng origin nhưng font từ `https://fonts.example.net` thì `style-src 'self'` **không tự cấp quyền cho font**. Cần khai báo đúng nguồn ở `font-src`, chẳng hạn:

~~~http
Content-Security-Policy: default-src 'none'; style-src 'self'; font-src 'self' https://fonts.example.net
~~~

Một lỗi frontend có thể do **nhiều directive phối hợp**: stylesheet phải được phép tải theo `style-src`, sau đó font bên trong stylesheet phải được phép theo `font-src`. Từng request bị kiểm tra theo nhóm của nó.

## 7. Kết nối API và WebSocket: connect-src khác CORS

Một SPA ở `https://app.example.com` gọi API ở `https://api.example.com` và nhận sự kiện qua `wss://events.example.com`. Cấu hình:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; connect-src 'self' https://api.example.com wss://events.example.com
~~~

cho phép các kết nối thuộc danh sách của `connect-src` theo quy tắc CSP. Điều này áp dụng cho các cơ chế như `fetch`, XHR và WebSocket.

~~~javascript
// JS hợp lệ được nạp từ chính origin của trang
const response = await fetch("https://api.example.com/profile");
const socket = new WebSocket("wss://events.example.com/feed");
~~~

Các yêu cầu trên vẫn phụ thuộc vào điều kiện khác của trình duyệt và server. Ví dụ, khi JavaScript đọc response API **khác origin**, server API còn phải cấp quyền **CORS** phù hợp. `connect-src` và CORS xử lý hai mặt khác nhau:

| Cơ chế | Câu hỏi chính |
|---|---|
| CSP `connect-src` | Tài liệu hiện tại có được tạo kết nối đến nguồn này không? |
| CORS | JavaScript ở origin hiện tại có được đọc response cross-origin theo yêu cầu của server đích không? |
| CSRF protection | Server có bảo vệ thao tác thay đổi trạng thái trước yêu cầu giả mạo không? |

Nếu Console báo `Refused to connect ... because it violates ... connect-src`, hãy sửa **CSP của trang**. Nếu request đã đi qua bước CSP nhưng Console báo thiếu `Access-Control-Allow-Origin`, hãy kiểm tra **cấu hình CORS của API**. Việc chỉ mở `connect-src` không tự giải quyết lỗi CORS.

**WebSocket:** đừng mặc định giả định `'self'` luôn khớp chính xác `ws:`/`wss:` trên mọi browser. Khi ứng dụng dùng WebSocket, hãy khai báo rõ endpoint/protocol cần thiết trong `connect-src` và thử trên trình duyệt mục tiêu.

## 8. Media, object, iframe và worker: các nguồn thường bị bỏ sót

### media-src: audio và video

Nếu trang tải video tại `https://media.example.net/training.mp4`:

~~~html
<video controls src="https://media.example.net/training.mp4"></video>
~~~

thì chính sách `default-src 'none'` sẽ chặn nếu không có `media-src` phù hợp. Cấu hình ví dụ:

~~~http
Content-Security-Policy: default-src 'none'; media-src 'self' https://media.example.net
~~~

Lưu ý rằng video được nhúng qua iframe của một nền tảng ngoài là **tình huống khác** với video tải bằng `<video>`: iframe chịu `frame-src` của trang, còn các tài nguyên bên trong iframe chịu chính sách và origin của tài liệu iframe.

### object-src: thu hẹp nội dung nhúng cũ

`object-src` điều khiển `<object>`/`<embed>` và một số dạng nội dung plugin. Khi không có yêu cầu đặc biệt, cấu hình:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'
~~~

giúp giảm bề mặt nhúng không cần thiết. Dù `default-src 'none'` đã làm nguồn fallback bị từ chối khi chưa có `object-src`, khai báo `object-src 'none'` rõ ràng giúp chính sách dễ kiểm tra và tránh lỗi khi `default-src` được thay đổi sau này.

### frame-src và frame-ancestors: hai chiều iframe

Giả sử website chứa:

~~~html
<iframe src="https://docs.example.net/help"></iframe>
~~~

Để **trang hiện tại nạp iframe**, cần cho phép đích ở `frame-src`:

~~~http
Content-Security-Policy: default-src 'none'; frame-src https://docs.example.net
~~~

Để **trang khác được nhúng website của bạn**, quy tắc nằm ở `frame-ancestors`. Chẳng hạn `frame-ancestors 'none'` không cho trang nào nhúng tài liệu hiện tại. `frame-ancestors` không hỗ trợ fallback về `default-src` và cần được gửi qua HTTP header, không thể áp dụng chỉ bằng thẻ `<meta http-equiv="Content-Security-Policy">`.

### worker-src: Web Worker và Service Worker

Một SPA có thể tạo worker xử lý dữ liệu nền:

~~~javascript
const worker = new Worker("/js/worker.js");
~~~

Để giới hạn nguồn worker:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; worker-src 'self'
~~~

Khi **`worker-src` không được khai báo**, trình duyệt áp dụng chuỗi fallback phù hợp: `child-src`, sau đó `script-src`, cuối cùng `default-src`. Vì quy tắc có thể khó đọc khi cấu hình nhiều directive, khai báo `worker-src` tường minh nếu ứng dụng thực sự sử dụng worker. **Lưu ý:** CSP của tài liệu tạo worker và CSP điều khiển các tài nguyên bên trong worker không hoàn toàn là một; riêng worker có thể cần được phục vụ với policy phù hợp.

## 9. Bài toán thực tế: xây CSP theo kiến trúc ứng dụng

Giả sử dashboard triển khai như sau:

| Thành phần | Nguồn |
|---|---|
| HTML, JavaScript và CSS ứng dụng | `https://app.example.com` |
| Ảnh sản phẩm | `https://images.example.net` và ảnh cùng origin |
| Font | Cùng origin |
| API | `https://api.example.net` |
| WebSocket | `wss://events.example.net` |
| Video đào tạo | `https://media.example.net` |
| Iframe trợ giúp | `https://docs.example.net` |
| Đích gửi form | Cùng origin |
| Website được nhúng dashboard | Không website nào |

Một policy có chủ đích:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.net; font-src 'self'; connect-src 'self' https://api.example.net wss://events.example.net; media-src 'self' https://media.example.net; frame-src https://docs.example.net; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Chính sách này dùng `default-src 'none'` làm **mặc định đóng**, rồi mở có chủ đích theo từng nhóm. Nó giả định frontend không cần JavaScript và CSS nội tuyến, không dùng manifest ngoài và không dùng blob URL cho worker; nếu ứng dụng có các nhu cầu đó, phải xét từng trường hợp.

### Thử thay đổi một yêu cầu

Sau một đợt phát hành, dashboard muốn lấy ảnh từ một CDN mới `https://new-images.example.net`. Cách cập nhật đúng là sửa **`img-src`**:

~~~http
img-src 'self' https://images.example.net https://new-images.example.net
~~~

Không cần nới `script-src` hoặc `default-src` cho CDN ảnh. Nếu muốn ngừng dùng CDN cũ, nên loại bỏ nguồn cũ sau khi xác nhận ảnh không còn dùng nó.

Nếu frontend muốn chạy script từ CDN mới, đó là một quyết định rủi ro **khác**: cần xem xét tin cậy nguồn script, khả năng tự phục vụ, kiểm soát tính toàn vẹn tài nguyên và chính sách CSP phù hợp. Đừng suy rằng CDN đã được cho phép trong `img-src` thì được phép chạy JavaScript.

### Vì sao default-src không thể thay cho danh sách chi tiết?

Ví dụ sau quá rộng đối với một ứng dụng chỉ cần API ở một origin và script nội bộ:

~~~http
Content-Security-Policy: default-src https:; script-src https:
~~~

Nguồn `https:` cho phép rất nhiều host HTTPS. Nếu dữ liệu bị chèn khiến trang tạo script từ một host HTTPS bất kỳ, chính sách có thể không ngăn tải script đó. Khai báo host chính xác theo từng nhóm thường giúp chính sách dễ kiểm soát và kiểm thử hơn.

## 10. Cấu hình trong Spring Security Servlet

Trong ứng dụng Spring MVC/Servlet, sử dụng `SecurityFilterChain` và CSP header DSL. Ví dụ dưới đây áp dụng policy của dashboard ở mục 9:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    static final String CSP_POLICY =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self' https://images.example.net; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.net " +
                "wss://events.example.net; " +
            "media-src 'self' https://media.example.net; " +
            "frame-src https://docs.example.net; " +
            "worker-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );
        return http.build();
    }
}
~~~

Ở đây `policyDirectives(CSP_POLICY)` là **giá trị CSP do ứng dụng tự chọn**. Spring Security xuất header theo cấu hình; trình duyệt mới phân tích và thực thi các directive. Không có cơ chế tự động dò frontend để biết API hoặc CDN nào đang được dùng.

Trong Servlet stack, cũng có thể dùng `ContentSecurityPolicyHeaderWriter` và đăng ký qua `addHeaderWriter(...)` nếu dự án đã quản lý header writers trực tiếp. Với một policy tĩnh, DSL trên thường đủ rõ ràng.

**Nhiều security chain:** nếu dự án có một chain cho `/api/**` và một chain cho các trang HTML, hãy bảo đảm CSP được gắn vào **response HTML thực tế**. Chỉ đặt CSP trên JSON response của API không bảo vệ được trang HTML do một CDN/origin khác phục vụ.

## 11. Cấu hình trong Spring Security Reactive/WebFlux

Trong WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Chuỗi directive giữ nguyên vì CSP là một chuẩn phía trình duyệt:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String policy =
                "default-src 'none'; " +
                "script-src 'self'; " +
                "style-src 'self'; " +
                "img-src 'self' https://images.example.net; " +
                "font-src 'self'; " +
                "connect-src 'self' https://api.example.net " +
                    "wss://events.example.net; " +
                "media-src 'self' https://media.example.net; " +
                "frame-src https://docs.example.net; " +
                "worker-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "form-action 'self'; " +
                "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );

        return http.build();
    }
}
~~~

Servlet và Reactive khác nhau về API server, không khác nhau về ý nghĩa của `default-src`, `script-src`, `img-src` hay `connect-src`. Một trang WebFlux cũng cần kiểm tra header trả về trên **response HTML cuối cùng** chứ không chỉ trên route API.

### Phòng vệ nhiều lớp

CSP làm giảm cơ hội thực thi mã và tải nguồn trái phép khi có nội dung bị chèn, nhưng không làm sạch dữ liệu đã render vào HTML. Ứng dụng vẫn cần mã hóa đầu ra đúng ngữ cảnh, giới hạn HTML người dùng được phép nhập, kiểm soát file upload và sử dụng bảo vệ CSRF, cookie session, HSTS, CORS, HTTP firewall theo chức năng riêng của từng cơ chế trong `SPRING_SECURITY_HTTP_PROTECTION`.

## 12. Kiểm thử fallback và từng nhóm tài nguyên

### 12.1. Test phía server: header có được xuất đúng không?

Với Spring MVC/Servlet có `MockMvc` và route `/dashboard` đã được cấu hình trong môi trường test:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("default-src 'none'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("img-src 'self' https://images.example.net")
    ));
~~~

Với WebFlux, có thể xác nhận qua `WebTestClient`:

~~~java
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*default-src 'none'.*"
    );
~~~

Các test này xác nhận server xuất header; chúng **không chứng minh** browser đã chặn ảnh, script hoặc API cụ thể. Muốn kiểm chứng hiệu lực CSP cần thử bằng trình duyệt.

### 12.2. Ma trận kiểm thử browser

Trong môi trường demo có quyền kiểm soát, phục vụ trang với policy ở mục 9 và thử:

| Thao tác | Kỳ vọng theo CSP | Directive cần quan sát |
|---|---|---|
| Tải `/js/app.js` | Được phép về mặt CSP | `script-src 'self'` |
| Chèn `<script src="https://other.example.net/x.js">` | Bị chặn | `script-src` |
| Chèn `<img src="https://images.example.net/a.png">` | Được phép về mặt CSP | `img-src` |
| Chèn `<img src="https://other.example.net/a.png">` | Bị chặn | `img-src` |
| Tải `/css/app.css` | Được phép | `style-src 'self'` |
| Dùng `<div style="color:red">` | Bị chặn nếu không có cấp phép inline phù hợp | `style-src` hoặc `style-src-attr` |
| `fetch("https://api.example.net/data")` | Được phép ở bước CSP; vẫn cần CORS khi đọc cross-origin | `connect-src` |
| Kết nối WebSocket ngoài danh sách | Bị chặn | `connect-src` |
| Tải `https://media.example.net/demo.mp4` qua `<video>` | Được phép về mặt CSP | `media-src` |
| Nhúng iframe từ `https://other.example.net` | Bị chặn | `frame-src` |
| Trang bên ngoài cố nhúng dashboard | Bị chặn | `frame-ancestors 'none'` |
| Gửi form đến origin ngoài | Bị chặn | `form-action 'self'` |

“Được phép” trong bảng chỉ có nghĩa là **CSP cụ thể này không chặn**. Request vẫn có thể thất bại vì nguồn không tồn tại, CORS, chính sách khác, lỗi mạng hoặc các kiểm tra bảo mật của trình duyệt.

### 12.3. Thử thay đổi fallback để thấy sự khác biệt

**Thử nghiệm A:**

~~~http
Content-Security-Policy: default-src 'self'
~~~

Ảnh từ cùng origin có thể được phép nhờ fallback. 

**Thử nghiệm B:**

~~~http
Content-Security-Policy: default-src 'self'; img-src https://images.example.net
~~~

Ảnh cùng origin có thể bị chặn vì `img-src` đã thay thế fallback của `default-src` cho ảnh.

**Thử nghiệm C:**

~~~http
Content-Security-Policy: default-src 'self'; img-src 'self' https://images.example.net
~~~

Ảnh cùng origin lại được phép; ứng dụng đã khai báo `'self'` **trực tiếp** trong `img-src`.

Nếu cần thử trên sản phẩm đang vận hành mà chưa muốn chặn tài nguyên, dùng `Content-Security-Policy-Report-Only` để quan sát cảnh báo trước. Chế độ đó **không chặn chỉ vì policy đang thử**; khi chuyển sang `Content-Security-Policy`, browser mới thực thi quy tắc chặn tương ứng. Nếu response có nhiều CSP thực thi, tất cả đều có hiệu lực, nên hãy kiểm tra đầy đủ các header.

### 12.4. Dùng DevTools để giải thích lỗi

1. Mở Network, chọn request **tài liệu HTML** và kiểm tra header `Content-Security-Policy` có đúng chuỗi cấu hình hay không.
2. Mở Console/Issues để đọc thông báo vi phạm, gồm nguồn bị chặn và directive có hiệu lực. Một số browser còn nói rõ directive nào đã được dùng làm fallback.
3. Đối chiếu tài nguyên đang tải với danh sách nguồn của directive chuyên biệt; nếu không có, xem chuỗi fallback tương ứng.
4. Xác nhận lỗi có thuộc CSP không: phân biệt với CORS, lỗi TLS, HTTP 404/500, blocked mixed content hoặc lỗi mã JavaScript.
5. Khi sửa, chỉ mở đúng directive và origin cần thiết. Tải lại trang, kiểm tra cả tính năng hợp lệ và thử một nguồn không được phép.

Trên môi trường có reverse proxy/CDN, hãy kiểm tra response tới browser vì các tầng trung gian có thể thêm, thay đổi hoặc gửi thêm header. Với nhiều CSP thực thi, một tài nguyên phải thỏa **mọi chính sách liên quan**, không được phép chỉ vì một header trong số đó cho phép.

## 13. Các lỗi suy luận thường gặp và cách xử lý

| Nhận định sai hoặc triệu chứng | Giải thích đúng | Cách sửa |
|---|---|---|
| “`default-src 'self'` cho phép mọi hành vi trên trang” | Chỉ fallback cho các nhóm fetch liên quan; `form-action`, `base-uri`, `frame-ancestors` không kế thừa | Thêm directive riêng cho hành vi cần bảo vệ |
| “`default-src 'self'; img-src https://cdn.example` vẫn cho ảnh cùng origin” | `img-src` thay thế fallback `default-src` của ảnh | Viết `img-src 'self' https://cdn.example` nếu cần cả hai |
| “Có `script-src 'self'` thì inline handler chạy được” | `'self'` nói về nguồn, không cho phép inline script/handler | Chuyển handler sang JS tĩnh hoặc dùng nonce/hash phù hợp |
| “Mở `img-src` cho CDN thì script CDN cũng chạy” | Mỗi nhóm có directive riêng | Chỉ mở đúng directive ứng với nhu cầu |
| “Trang được phép iframe người khác nghĩa là người khác được iframe trang” | `frame-src` và `frame-ancestors` điều khiển hai hướng khác nhau | Khai báo cả hai theo nhu cầu |
| “CSP cho API là đủ, CORS không cần” | `connect-src` và CORS kiểm soát các bước khác nhau | Cấu hình từng cơ chế đúng vai trò |
| “Worker sẽ được cho phép theo `default-src` dù `script-src 'none'`” | `worker-src` có chuỗi fallback có thể đi qua `script-src` trước `default-src` | Khai báo `worker-src` rõ ràng nếu có worker |
| “Chỉ một CSP header được trình duyệt dùng” | Các CSP thực thi đồng thời đều có hiệu lực | Xem toàn bộ response, tránh policy chồng chéo ngoài ý muốn |
| “Tắt CSP hoặc thêm `*` sẽ hết lỗi” | Cách đó làm mất nhiều lớp hạn chế quan trọng | Khoanh đúng nguồn, directive và tính năng gây lỗi |

### Những nguyên tắc thiết kế dễ duy trì

- Chọn `default-src 'none'` nếu có thể liệt kê rõ các nhóm tài nguyên mà ứng dụng dùng. Với ứng dụng đang vận hành, bắt đầu bằng kiểm kê và Report-Only để tránh gây lỗi hàng loạt.
- Giữ nguồn script chặt hơn nguồn ảnh; tránh wildcard và scheme rộng trong `script-src`.
- Khai báo `object-src 'none'`, `base-uri`, `form-action` và `frame-ancestors` có chủ đích.
- Đánh giá thư viện mới theo **loại tài nguyên**: một CDN có thể cấp CSS, font, JavaScript và kết nối API ở các origin khác nhau.
- Lưu policy cùng code/cấu hình được review; tránh ghép trực tiếp giá trị do người dùng kiểm soát vào CSP header.
- Kiểm tra trang HTML được phục vụ thực sự ở đâu. Nếu frontend và backend Spring Security tách origin, CSP cần xuất từ hệ thống trả trang HTML.

## 14. Bài thực hành tổng hợp

**Bối cảnh:** một dashboard dùng JavaScript và CSS cùng origin, ảnh từ CDN, API và WebSocket bên ngoài, thêm tài liệu trợ giúp bằng iframe. Đội phát triển muốn hạn chế việc nội dung chèn tải script độc hại, nhưng không làm hỏng tính năng.

**Nhiệm vụ:**

1. Viết chính sách bắt đầu bằng `default-src 'none'`. Thêm `script-src`, `style-src`, `img-src`, `font-src`, `connect-src`, `frame-src`, `object-src`, `base-uri`, `form-action` và `frame-ancestors` đúng kiến trúc ở mục 9.
2. Cấu hình chính sách trong Spring Security Servlet bằng `HttpSecurity.headers(...).contentSecurityPolicy(...)`; đọc header trên request HTML.
3. Tạo một phiên bản WebFlux dùng `ServerHttpSecurity` và so sánh header CSP nhận được.
4. Dùng DevTools thử một ảnh CDN hợp lệ, một ảnh ngoài danh sách, một script ngoài danh sách và một request `fetch` đến API. Ghi rõ directive quyết định hành vi cho từng tình huống.
5. Bỏ `img-src` để quan sát ảnh quay về `default-src 'none'`; sau đó thêm `img-src https://images.example.net` và kiểm tra ảnh cùng origin có bị từ chối không.
6. Thử `<iframe>` được phép tải nội dung ở `docs.example.net` và một trang ngoài cố nhúng dashboard; giải thích sự khác biệt giữa `frame-src` và `frame-ancestors`.
7. Với một vi phạm gây hỏng tính năng hợp lệ, sửa **directive chính xác**, tránh chuyển cả policy sang `default-src *`.

**Câu hỏi tự đánh giá:**

1. Khi đã có `img-src`, giá trị trong `default-src` còn tự động được cộng vào danh sách ảnh không?
2. Vì sao `script-src 'self'` có thể chặn JavaScript nội tuyến?
3. Một SPA có `connect-src 'self' https://api.example.com` có chắc chắn đọc được mọi response từ API cross-origin không?
4. Nếu `worker-src` không có, chuỗi fallback là gì?
5. Vì sao `form-action`, `base-uri` và `frame-ancestors` phải được xem xét riêng dù đã có `default-src 'none'`?
6. Làm thế nào phân biệt lỗi `style-src`, `font-src` và `img-src` khi giao diện mất CSS hoặc icon?
7. Khi một response chứa hai CSP thực thi, việc một policy cho phép CDN có bảo đảm CDN đó được nạp không?

## 15. Ghi nhớ

`default-src` là **nguồn dự phòng** cho nhiều nhóm tải tài nguyên trong CSP, **không phải quy tắc tự cộng thêm** vào directive chuyên biệt. Để thiết kế chính sách theo nhu cầu thật, hãy xác định loại request hoặc hành vi, dùng đúng directive (`script-src`, `style-src`, `img-src`, `font-src`, `connect-src`, `media-src`, `worker-src`, `frame-src`...) và hiểu chuỗi fallback nếu directive đó vắng mặt.

Các chỉ thị như `form-action`, `base-uri` và `frame-ancestors` không kế thừa `default-src`. Một chính sách hiệu quả cần kết hợp mặc định chặt, nguồn được mở có chủ đích, cấu hình ở response HTML, kiểm thử browser và các lớp bảo vệ khác như escape dữ liệu, CSRF, CORS, HSTS và bảo vệ session. Trong Spring Security, cách khai báo Servlet hoặc WebFlux khác nhau về API, nhưng ý nghĩa và cách trình duyệt thực thi các directive CSP là giống nhau.
