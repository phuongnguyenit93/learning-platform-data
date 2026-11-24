# Network panel trong DevTools

Network panel là nơi quan sát các yêu cầu mà trình duyệt thực hiện khi tải trang và khi người dùng tương tác với ứng dụng. Với mỗi yêu cầu, công cụ cho biết tài nguyên nào được tải, thành phần nào khởi tạo yêu cầu, dữ liệu nào được gửi đi, máy chủ trả về gì và quá trình đó mất bao lâu.

Trong bảo mật ứng dụng web, những thông tin này giúp kiểm chứng hành vi thực tế của trình duyệt: cookie có được gửi hay không, request có phát sinh preflight CORS không, response có chứa security header không, tài nguyên có bị chặn bởi chính sách trình duyệt không, và dữ liệu nhạy cảm có vô tình xuất hiện trong URL hoặc response không. Network panel là công cụ quan sát ở phía trình duyệt; kết quả cần được đối chiếu với cấu hình máy chủ, mã ứng dụng và thông báo trong Console khi cần.

Sau bài học, bạn có thể:

- Thu thập và lọc các request phát sinh trong một phiên tải trang.
- Đọc URL, method, status, request headers, response headers, payload, cookies và timing.
- Lần theo initiator để tìm đoạn mã hoặc tài nguyên khởi tạo request.
- Nhận diện các dấu hiệu liên quan đến CORS, CSRF, XSS, CSP, clickjacking, cache và xác thực.
- Lưu và chia sẻ dữ liệu chẩn đoán mà không làm lộ thông tin đăng nhập hoặc dữ liệu cá nhân.

## 1. Network panel quan sát điều gì?

Khi trình duyệt tải một trang, nó có thể yêu cầu tài liệu HTML, stylesheet, script, hình ảnh, font, API, media và nhiều tài nguyên khác. Các thao tác trong trang cũng có thể tạo thêm request thông qua `fetch`, `XMLHttpRequest`, form submission, điều hướng hoặc kết nối WebSocket.

Network panel ghi lại hoạt động mạng mà trình duyệt quan sát được trong tab hiện tại. Một dòng thường tương ứng với một request hoặc một tài nguyên. Khi chọn dòng đó, bạn có thể xem chi tiết request và response.

Hãy nhớ ba giới hạn khi diễn giải dữ liệu:

1. Network panel không phải công cụ bắt toàn bộ gói tin trên máy. Nó tập trung vào hoạt động tải tài nguyên của trình duyệt trong tab đang kiểm tra.
2. Một tài nguyên có thể được phục vụ từ memory cache, disk cache hoặc Service Worker. Vì vậy, không thấy một kết nối mới tới máy chủ không có nghĩa là trang không sử dụng tài nguyên đó.
3. Network panel cho thấy dữ liệu tại ranh giới trình duyệt xử lý request và response. Nó không tự chứng minh logic phân quyền, tính đúng đắn của truy vấn cơ sở dữ liệu hay trạng thái bên trong máy chủ.

Network panel thường hiển thị nội dung HTTP sau khi trình duyệt xử lý lớp TLS. Đây là góc nhìn hữu ích để kiểm tra header và payload ứng dụng, nhưng không thay thế công cụ phân tích mạng chuyên dụng khi cần điều tra ở tầng kết nối.

## 2. Chuẩn bị một phiên ghi nhận

Mở DevTools trước khi thực hiện thao tác cần kiểm tra, sau đó chọn tab **Network**. Nếu mở Network panel sau khi trang đã tải xong, các request trước đó có thể không xuất hiện.

Một số tùy chọn thường dùng:

| Tùy chọn | Tác dụng | Khi nên dùng |
|---|---|---|
| **Preserve log** | Giữ các dòng request qua những lần điều hướng hoặc tải lại trang | Kiểm tra redirect, luồng đăng nhập và chuyển trang |
| **Disable cache** | Bỏ qua HTTP cache khi DevTools đang mở | So sánh response mới từ máy chủ với dữ liệu đã cache |
| **Throttling** | Mô phỏng kết nối chậm hoặc giới hạn băng thông | Tìm lỗi timeout, tải tài nguyên chậm và race condition |
| **Clear** | Xóa danh sách request đang ghi nhận | Bắt đầu một lần kiểm tra có phạm vi rõ ràng |

Quy trình ghi nhận cơ bản:

1. Mở trang cần kiểm tra và mở Network panel.
2. Bật **Preserve log** nếu luồng kiểm tra có điều hướng hoặc redirect.
3. Bật **Disable cache** khi cần loại trừ ảnh hưởng của HTTP cache. Tắt tùy chọn này sau khi hoàn tất phép đo bình thường.
4. Xóa danh sách request cũ.
5. Tải lại trang hoặc thực hiện đúng thao tác gây ra vấn đề.
6. Lọc request liên quan và mở từng request để đọc chi tiết.

Chỉ dùng tài khoản thử nghiệm và dữ liệu giả khi có thể. Không tắt cơ chế bảo vệ của trình duyệt để làm cho request chạy thành công; việc đó có thể che khuất chính lỗi bảo mật đang cần tìm.

## 3. Đọc danh sách request

Danh sách request cung cấp cái nhìn tổng quan trước khi đi sâu vào từng dòng. Các cột phổ biến gồm:

| Cột | Ý nghĩa |
|---|---|
| **Name** | Tên tài nguyên hoặc phần cuối của URL |
| **Status** | Mã trạng thái HTTP hoặc thông tin lỗi do trình duyệt hiển thị |
| **Type** | Loại tài nguyên, chẳng hạn `document`, `script`, `stylesheet`, `fetch` hoặc `xhr` |
| **Initiator** | Thành phần hoặc chuỗi lời gọi khởi tạo request |
| **Size** | Kích thước response và thông tin nguồn cache nếu có |
| **Time** | Thời gian hoàn tất request theo cách DevTools đo |
| **Waterfall** | Trình tự và thời lượng các giai đoạn tải request trên dòng thời gian |

Bạn có thể chọn các bộ lọc như **All**, **Fetch/XHR**, **Doc**, **JS**, **CSS**, **Img**, **Media**, **Font** hoặc **WS**. Bộ lọc **Fetch/XHR** đặc biệt hữu ích khi điều tra API. Ô Filter cho phép lọc theo chuỗi URL, domain, method, status hoặc một số thuộc tính khác tùy phiên bản trình duyệt.

Khi cần tìm một request cụ thể, hãy bắt đầu bằng loại tài nguyên hoặc domain, sau đó thu hẹp bằng URL hay method. Đừng chỉ nhìn vào status: một request `200` vẫn có thể trả về dữ liệu sai, lộ thông tin hoặc chứa cấu hình bảo mật yếu.

## 4. Đọc chi tiết một request

Chọn một dòng trong danh sách để mở bảng chi tiết. Tên và cách sắp xếp tab có thể khác đôi chút giữa các phiên bản Chromium, nhưng những nhóm thông tin chính thường giống nhau.

### 4.1. Headers

Tab **Headers** thường chia thành các nhóm:

- **General**: Request URL, Request Method, Status Code và thông tin kết nối liên quan.
- **Response Headers**: header máy chủ hoặc lớp trung gian trả về.
- **Request Headers**: header trình duyệt gửi lên máy chủ.

Ví dụ một request API:

```http
POST /api/profile HTTP/1.1
Host: app.example.test
Content-Type: application/json
Accept: application/json
Origin: https://app.example.test
Cookie: session=<redacted>
```

Response minh họa:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
Cache-Control: no-store
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
```

Các giá trị trên chỉ là ví dụ. Khi kiểm tra ứng dụng thật, hãy đối chiếu URL, method, origin và header với yêu cầu nghiệp vụ. Ví dụ, endpoint thay đổi trạng thái không nên bị biến thành thao tác GET chỉ vì cách gọi đó tiện cho việc kiểm tra.

### 4.2. Query String Parameters và Payload

**Query String Parameters** hiển thị các tham số trong URL, còn **Payload** hiển thị dữ liệu gửi trong request body khi có. Tùy loại request, payload có thể là form data, JSON, dữ liệu văn bản hoặc nội dung nhị phân.

Ví dụ:

```http
GET /api/orders?status=pending&page=2
```

Hoặc body JSON:

```json
{
  "displayName": "Demo User",
  "timezone": "Asia/Ho_Chi_Minh"
}
```

URL có thể xuất hiện trong browser history, access log, hệ thống analytics, header `Referer` hoặc các báo cáo chẩn đoán. Vì vậy, không đưa mật khẩu, session ID, access token hay dữ liệu cá nhân nhạy cảm vào query string. Với dữ liệu cần gửi trong body, ứng dụng vẫn phải dùng HTTPS và kiểm soát quyền truy cập ở máy chủ.

### 4.3. Response và Preview

Tab **Response** cho biết nội dung response mà DevTools nhận được; **Preview** cố gắng trình bày dữ liệu theo định dạng dễ đọc hơn, chẳng hạn JSON hoặc hình ảnh.

Khi kiểm tra API, hãy xác nhận:

- Response có đúng kiểu nội dung dự kiến không?
- Dữ liệu trả về có vượt quá quyền của tài khoản thử nghiệm không?
- Lỗi có vô tình chứa stack trace, câu truy vấn, đường dẫn nội bộ hoặc bí mật không?
- Response có trả dữ liệu cá nhân hoặc thông tin xác thực không cần thiết không?
- Header cache có phù hợp với độ nhạy của dữ liệu không?

Một status thành công không chứng minh response an toàn. Ví dụ, endpoint có thể trả `200 OK` nhưng vẫn để lộ hồ sơ của người dùng khác do lỗi kiểm tra quyền ở máy chủ.

### 4.4. Cookies

Cookie có thể được gửi trong request thông qua header `Cookie` và được máy chủ thiết lập bằng header `Set-Cookie`. Tab **Cookies** của request giúp xem cookie được gửi, cookie bị loại trừ và lý do trình duyệt chặn cookie trong những trường hợp được DevTools hỗ trợ hiển thị.

Ví dụ cookie phiên:

```http
Set-Cookie: session=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=Lax
```

Các thuộc tính quan trọng:

| Thuộc tính | Vai trò bảo mật |
|---|---|
| `Secure` | Chỉ gửi cookie qua kết nối an toàn HTTPS, ngoại trừ một số hành vi đặc biệt trên môi trường phát triển được trình duyệt quy định |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua API như `document.cookie`; trình duyệt vẫn có thể gửi cookie theo quy tắc phù hợp |
| `SameSite` | Kiểm soát việc gửi cookie trong ngữ cảnh same-site và cross-site, hỗ trợ giảm nguy cơ CSRF |
| `Domain` | Xác định phạm vi domain nhận cookie; bỏ thuộc tính này thường tạo host-only cookie |
| `Path` | Giới hạn các đường dẫn mà cookie được gửi tới; không phải ranh giới bảo mật đủ mạnh để phân quyền |
| `Max-Age` / `Expires` | Xác định thời hạn tồn tại của cookie |
| `Partitioned` | Đánh dấu cookie phân vùng theo cơ chế partitioning được trình duyệt hỗ trợ |

Nếu cookie không xuất hiện trong request, hãy kiểm tra domain, path, thời hạn, `Secure`, `SameSite`, ngữ cảnh điều hướng và việc request có bật credentials phù hợp không. Với cookie phiên, ưu tiên `Secure`, `HttpOnly` và chính sách `SameSite` phù hợp với luồng sản phẩm. `SameSite` không thay thế token chống CSRF trong mọi kiến trúc.

`HttpOnly` chỉ ngăn mã JavaScript của trang đọc cookie. Người có quyền mở DevTools vẫn có thể nhìn thấy thông tin cookie trong giao diện kiểm tra. Vì vậy, hãy che giá trị cookie khi chụp màn hình, sao chép request hoặc chia sẻ HAR.

### 4.5. Initiator và Timing

**Initiator** giúp lần theo nguyên nhân tạo request. Tùy loại request, nguồn khởi tạo có thể là tài liệu HTML, một dòng trong script, chuỗi gọi hàm hoặc Service Worker. Mở ngăn xếp lời gọi nếu có để tìm vị trí trong mã ứng dụng.

**Timing** chia thời gian request thành các giai đoạn, chẳng hạn hàng đợi, kết nối, gửi request, chờ byte đầu tiên và nhận response. Tên giai đoạn có thể thay đổi theo giao thức và phiên bản trình duyệt.

Nếu request chậm, hãy xem nó bị chờ trước khi gửi, mất nhiều thời gian kết nối, hay máy chủ phản hồi chậm. Nếu request phát sinh ngoài dự kiến, hãy lần theo Initiator để tìm script, event handler hoặc Service Worker liên quan.

## 5. Hiểu status, redirect, cache và preflight

### 5.1. Status code

Một số mã trạng thái thường gặp:

| Nhóm / mã | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `200`, `201`, `204` | Request thành công; `204` không có response body | Kiểm tra nội dung, quyền truy cập và side effect thực tế |
| `301`, `302`, `307`, `308` | Redirect | Bật Preserve log và xem từng bước chuyển hướng, method cùng header có được giữ hay không |
| `304` | Có thể dùng bản cache đã lưu theo điều kiện validator | Kiểm tra `ETag`, `Last-Modified`, `Cache-Control` và response được dùng |
| `400`, `422` | Request không hợp lệ hoặc dữ liệu không qua kiểm tra | Đọc payload và response lỗi; không gửi dữ liệu nhạy cảm vào log |
| `401` | Chưa xác thực hoặc thông tin xác thực không được chấp nhận | Kiểm tra cookie/token, thời hạn và luồng đăng nhập |
| `403` | Máy chủ từ chối thao tác | Kiểm tra quyền và chính sách ở máy chủ; không suy ra rằng người dùng đã được xác thực chỉ từ mã này |
| `404` | Không tìm thấy tài nguyên hoặc máy chủ chủ động che giấu tài nguyên | Kiểm tra URL, route và quyền truy cập |
| `429` | Bị giới hạn tần suất | Kiểm tra `Retry-After` và chính sách rate limit |
| `5xx` | Lỗi phía máy chủ hoặc gateway | Đối chiếu request ID, log máy chủ và thời điểm phát sinh |

Một số lỗi hiển thị dưới dạng `(failed)`, `blocked` hoặc thông báo do trình duyệt tạo ra thay vì status HTTP. Khi đó có thể request chưa tới máy chủ, bị chặn bởi chính sách trình duyệt, hoặc response không được phép cung cấp cho JavaScript. Hãy đọc chi tiết lỗi và Console để xác định nguyên nhân.

### 5.2. Redirect

Một lần điều hướng có thể gồm nhiều response `3xx`. Khi kiểm tra luồng đăng nhập, hãy bật **Preserve log** rồi lần theo chuỗi URL, status và header `Location`.

Quan sát xem:

- Redirect có chuyển sang domain hoặc origin khác không?
- Dữ liệu nhạy cảm có bị đưa vào URL đích không?
- Cookie có được gửi ở bước tiếp theo theo đúng domain, path và SameSite không?
- Method và body có thay đổi theo loại redirect không?

`301` và `302` có thể khiến client chuyển POST thành GET theo hành vi tương thích phổ biến; `307` và `308` giữ method và body. Ứng dụng cần chọn loại redirect phù hợp với thao tác đang thực hiện.

### 5.3. Cache và Service Worker

Các header như `Cache-Control`, `ETag`, `Last-Modified`, `Age` và `Vary` giúp giải thích cách response được cache và tái sử dụng. Ví dụ, `Cache-Control: no-store` yêu cầu cache không lưu response; `no-cache` cho phép lưu nhưng yêu cầu xác thực lại trước khi sử dụng theo ngữ nghĩa HTTP.

Network panel có thể đánh dấu tài nguyên đến từ memory cache, disk cache hoặc Service Worker. Nếu bật **Disable cache**, bạn đang thay đổi điều kiện thử nghiệm; kết quả khi đó không đại diện cho hành vi cache bình thường của người dùng.

Khi kiểm tra dữ liệu cá nhân hoặc response chứa thông tin tài khoản, xem xét chính sách cache tại cả trình duyệt và proxy/CDN. Không nên để response nhạy cảm có thể được chia sẻ giữa các người dùng qua cache công cộng.

### 5.4. CORS preflight

Khi JavaScript gửi một số request cross-origin không thuộc nhóm CORS-safelisted, trình duyệt gửi request `OPTIONS` trước để hỏi máy chủ xem method và header dự kiến có được phép hay không. Đây là **preflight**.

Ví dụ, request JSON cross-origin:

```javascript
await fetch("https://api.example.test/profile", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ displayName: "Demo User" })
});
```

Trong Network panel, bạn có thể thấy request `OPTIONS` với các header như:

```http
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
```

Response preflight hợp lệ có thể chứa:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type
Vary: Origin
```

Với request có credentials, `Access-Control-Allow-Origin` phải chỉ rõ origin được phép; không thể dùng `*` cùng `Access-Control-Allow-Credentials: true`. Nếu máy chủ phản hồi preflight không phù hợp, trình duyệt có thể không gửi request thực tế. Nếu preflight thành công nhưng response của request thực tế thiếu header CORS phù hợp, JavaScript vẫn có thể không đọc được response.

CORS là cơ chế trình duyệt kiểm soát việc JavaScript đọc response cross-origin. Nó không thay thế xác thực, phân quyền hoặc biện pháp chống CSRF ở máy chủ. Không kết luận endpoint an toàn chỉ vì một request bị CORS chặn trong trình duyệt.

## 6. Dùng Network panel để kiểm tra các cơ chế bảo mật

### 6.1. Kiểm tra CORS

Khi ứng dụng báo lỗi CORS:

1. Lọc **Fetch/XHR** và tìm request lỗi.
2. Xác định URL đích, method và header do ứng dụng gửi.
3. Tìm request `OPTIONS` nếu có preflight.
4. Đọc `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` và các header `Access-Control-Allow-*` trong response.
5. Kiểm tra response thực tế, vì preflight thành công không đảm bảo response cuối cùng có cấu hình CORS đúng.

Đối chiếu chính xác scheme, host và port của origin. Nếu máy chủ phản hồi origin theo danh sách cho phép động, kiểm tra `Vary: Origin` để cache không dùng nhầm response của origin khác.

### 6.2. Kiểm tra CSRF và cookie phiên

CSRF xảy ra khi trình duyệt của nạn nhân gửi một request có tác dụng thay đổi trạng thái tới ứng dụng mà người dùng đang đăng nhập, trong khi ứng dụng không xác minh đầy đủ ý định của người dùng.

Khi kiểm tra một thao tác thay đổi trạng thái trong môi trường được phép, hãy quan sát:

- Request dùng method nào và có tạo thay đổi trạng thái không?
- Cookie phiên có được trình duyệt gửi kèm không?
- `SameSite` và ngữ cảnh điều hướng có ảnh hưởng đến việc gửi cookie không?
- Ứng dụng có gửi token chống CSRF hoặc cơ chế xác minh tương đương không?
- Máy chủ có kiểm tra `Origin` hoặc `Referer` phù hợp với kiến trúc không?
- Response có cho biết request bị từ chối khi thiếu token hoặc sai origin không?

Network panel giúp xác minh request thực tế nhưng không tự chứng minh khả năng khai thác CSRF. Cần kiểm tra cả logic máy chủ, token, chính sách cookie và các luồng nghiệp vụ. Chỉ thực hiện thử nghiệm trên tài khoản và hệ thống bạn được phép kiểm tra.

### 6.3. Kiểm tra XSS, CSP và Trusted Types

Để xem chính sách bảo vệ nội dung, chọn request loại **document** và kiểm tra response headers:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; script-src 'self' 'nonce-<per-response-nonce>'
X-Content-Type-Options: nosniff
```

Nếu ứng dụng dùng Trusted Types, có thể thấy directive như:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app
```

Hãy xác định policy có được gửi trên response HTML đúng không, có bị thay thế bởi redirect hoặc response khác không, và tài nguyên script được tải từ đâu. Nếu dùng `Content-Security-Policy-Report-Only`, trình duyệt chỉ báo cáo vi phạm mà không thực thi việc chặn theo policy đó.

Khi một script hoặc tài nguyên bị chặn, xem dòng request, lý do blocked và thông báo tương ứng trong Console. Network panel giúp tìm nguồn script và response liên quan; nó không thể chứng minh ứng dụng không còn điểm XSS. Việc xác minh XSS vẫn cần xem cách dữ liệu đi vào DOM, cách mã hóa đầu ra và việc dùng API DOM an toàn.

### 6.4. Kiểm tra clickjacking

Clickjacking thường lợi dụng việc nhúng trang mục tiêu trong một frame để đánh lừa người dùng tương tác với giao diện bị che phủ. Chọn request **document** và kiểm tra response headers như:

```http
Content-Security-Policy: frame-ancestors 'none'
```

Hoặc chính sách tương thích cũ hơn:

```http
X-Frame-Options: DENY
```

`frame-ancestors` xác định những ancestor nào được phép nhúng trang và cần được gửi bằng HTTP response header; khai báo trong thẻ `meta` không thay thế được directive này. Hãy kiểm tra đúng response HTML được nhúng, bao gồm cả các route và trang đăng nhập liên quan.

### 6.5. Kiểm tra xác thực và phân quyền

Khi một API trả `401` hoặc `403`, kiểm tra request có gửi cookie hoặc `Authorization` header như dự kiến không, thông tin xác thực có bị hết hạn hoặc bị loại trừ không, và response có vô tình tiết lộ chi tiết nội bộ không.

Để kiểm tra phân quyền, dùng hai tài khoản thử nghiệm có vai trò khác nhau và gọi cùng endpoint với dữ liệu thuộc từng tài khoản. So sánh response để xác nhận máy chủ chỉ trả dữ liệu mà từng tài khoản được phép xem. Network panel cung cấp bằng chứng về request và response; quyết định cho phép phải được thực hiện ở phía máy chủ.

### 6.6. Kiểm tra kiểu nội dung và mixed content

Kiểm tra `Content-Type` của response để chắc chắn tài nguyên được phục vụ đúng loại. Với tài nguyên có nguy cơ bị diễn giải sai kiểu, xem xét `X-Content-Type-Options: nosniff` cùng cấu hình MIME chính xác.

Nếu một trang HTTPS tải tài nguyên HTTP, trình duyệt có thể chặn hoặc nâng cấp một số loại mixed content. Network panel có thể hiển thị request bị blocked; đọc thêm thông báo trong Console để xác định URL và loại tài nguyên gây ra vấn đề. Sửa URL và cấu hình máy chủ để phục vụ tài nguyên qua HTTPS.

## 7. Quy trình điều tra một lỗi mạng

Khi một thao tác không hoạt động, làm theo trình tự sau để tránh bỏ sót nguyên nhân:

1. **Tái hiện có kiểm soát:** ghi lại trang, tài khoản thử nghiệm, thao tác và thời điểm lỗi.
2. **Thu thập request:** mở Network trước khi thao tác, xóa log cũ và bật Preserve log nếu cần.
3. **Thu hẹp phạm vi:** dùng Fetch/XHR, domain, URL hoặc status để tìm request liên quan.
4. **Đọc request:** xác nhận method, URL, query, payload, credentials và request headers.
5. **Đọc response:** xác nhận status, response body, response headers và redirect.
6. **Lần theo nguồn gọi:** dùng Initiator để tìm script hoặc thao tác tạo request.
7. **Đọc timing:** phân biệt request bị xếp hàng, kết nối chậm hay máy chủ phản hồi chậm.
8. **Đối chiếu Console và máy chủ:** dùng request ID hoặc timestamp để ghép sự kiện với log phía máy chủ nếu có.
9. **Thử lại một biến:** thay đổi một điều kiện mỗi lần để xác định nguyên nhân, chẳng hạn cache, tài khoản, payload hoặc trạng thái đăng nhập.

Ví dụ, nếu nút “Lưu hồ sơ” không hoạt động, hãy tìm request API được tạo khi nhấn nút. Nếu không có request, lỗi có thể nằm ở event handler hoặc mã phía trình duyệt. Nếu có request nhưng trả `400`, kiểm tra payload và validation. Nếu trả `401`, kiểm tra phiên đăng nhập. Nếu trả `403`, xác minh quyền ở máy chủ. Nếu trả `200` nhưng giao diện không đổi, kiểm tra response body và logic cập nhật giao diện.

## 8. Sao chép request và xuất HAR an toàn

DevTools có thể cho phép **Copy as cURL** hoặc xuất toàn bộ phiên thành tệp HAR. Những chức năng này hữu ích để tái hiện lỗi và chia sẻ bằng chứng kỹ thuật, nhưng dữ liệu có thể chứa:

- Cookie phiên, bearer token và header `Authorization`.
- Query string có mã truy cập, email hoặc dữ liệu cá nhân.
- Payload form/JSON chứa thông tin tài khoản.
- URL ký số, thông tin nội bộ hoặc dữ liệu phản hồi nhạy cảm.

Trước khi gửi request đã sao chép cho người khác hoặc chia sẻ HAR:

1. Xóa hoặc thay thế cookie, token, API key và thông tin xác thực bằng placeholder.
2. Ẩn dữ liệu cá nhân trong URL, payload và response body.
3. Kiểm tra cả header request lẫn response, vì bí mật có thể nằm ở một trong hai phía.
4. Chỉ giữ lại các request cần thiết cho vấn đề đang điều tra.
5. Dùng kênh chia sẻ được tổ chức cho phép và tuân thủ thời hạn lưu trữ dữ liệu.

Một lệnh cURL được sao chép có thể tái sử dụng thông tin xác thực còn hiệu lực. Hãy xem nội dung lệnh trước khi chạy hoặc lưu nó vào ticket, tài liệu hay lịch sử shell.

## 9. Thực hành có hướng dẫn

Thực hiện trên ứng dụng thử nghiệm mà bạn kiểm soát, với tài khoản và dữ liệu giả.

### Bài tập A: Tìm request của một thao tác

1. Mở ứng dụng thử nghiệm và Network panel.
2. Xóa log, chọn **Fetch/XHR** rồi thực hiện thao tác tải danh sách.
3. Tìm request mới xuất hiện, ghi lại URL, method, status và Initiator.
4. Mở Headers, Payload và Response để mô tả dữ liệu đi và về.
5. Xác định request có gửi cookie phiên hay token không; không sao chép giá trị bí mật vào ghi chú.

Kết quả cần đạt: bạn có thể mô tả một thao tác giao diện tương ứng với request nào và response nào làm thay đổi trạng thái giao diện.

### Bài tập B: Quan sát preflight CORS

Trong môi trường thử nghiệm có hai origin riêng, gọi API bằng request JSON cross-origin. Quan sát request `OPTIONS`, các header `Access-Control-Request-*` và response `Access-Control-Allow-*`. Sau đó thay đổi cấu hình cho phép một header thử nghiệm và quan sát sự khác nhau giữa preflight thành công và thất bại.

Kết quả cần đạt: bạn giải thích được vì sao trình duyệt gửi preflight, khi nào request thực tế được gửi và vì sao JavaScript có thể không đọc được response.

### Bài tập C: Kiểm tra header bảo mật

Chọn response document của ứng dụng thử nghiệm. Ghi nhận các header hiện có: `Content-Security-Policy`, `X-Content-Type-Options`, `Strict-Transport-Security`, `Referrer-Policy`, `Permissions-Policy`, `X-Frame-Options` hoặc `frame-ancestors` trong CSP. Xác định header nào có mặt, header nào thiếu và chính sách đó áp dụng cho response nào.

Kết quả cần đạt: bạn phân biệt được header được gửi thật với cấu hình chỉ tồn tại trong mã nguồn hoặc trong một response khác.

### Bài tập D: Kiểm tra cookie phiên

Đăng nhập bằng tài khoản thử nghiệm, tìm response thiết lập cookie và request API tiếp theo. Đối chiếu `Set-Cookie` với cookie được gửi trong request. Thử một luồng điều hướng cùng site và một luồng cross-site được thiết kế an toàn trong môi trường thử nghiệm để quan sát tác động của `SameSite`.

Kết quả cần đạt: bạn giải thích được thuộc tính cookie nào ảnh hưởng đến việc lưu và gửi cookie, đồng thời biết cách che giá trị cookie khi lưu bằng chứng.

## 10. Những nhầm lẫn thường gặp

- **Thấy `200` nghĩa là an toàn:** status chỉ cho biết kết quả giao thức ở mức nhất định; vẫn phải kiểm tra nội dung, quyền và dữ liệu bị lộ.
- **Không thấy request nghĩa là mã không chạy:** tài nguyên có thể đến từ cache hoặc Service Worker; một thao tác cũng có thể lỗi trước khi tạo request.
- **CORS là cơ chế xác thực:** CORS điều khiển việc trình duyệt cho JavaScript đọc response cross-origin; máy chủ vẫn phải xác thực và phân quyền.
- **Cookie không xuất hiện là do server không thiết lập:** cookie có thể bị trình duyệt loại trừ do domain, path, thời hạn, Secure, SameSite hoặc credentials mode.
- **Có CSP là không thể có XSS:** policy có thể quá rộng, không áp dụng cho response đang xem hoặc chỉ ở chế độ Report-Only; cần đánh giá cách ứng dụng xử lý dữ liệu.
- **Copy as cURL chỉ chứa dữ liệu kỹ thuật:** lệnh có thể chứa cookie và token còn hiệu lực.
- **Disable cache phản ánh hành vi người dùng bình thường:** tùy chọn này thay đổi điều kiện tải; cần kiểm tra lại với cache được bật.

## 11. Checklist khi kết thúc kiểm tra

- [ ] Đã ghi nhận đúng thao tác và thời điểm gây ra vấn đề.
- [ ] Đã xác định request liên quan, method, URL, status và initiator.
- [ ] Đã kiểm tra request headers, payload, cookies, response headers và response body.
- [ ] Đã kiểm tra redirect, preflight, cache hoặc Service Worker khi có liên quan.
- [ ] Đã đối chiếu các security header trên đúng response cần bảo vệ.
- [ ] Đã kiểm tra quyền truy cập và dữ liệu trả về bằng tài khoản thử nghiệm phù hợp.
- [ ] Đã che token, cookie, dữ liệu cá nhân và bí mật trước khi chia sẻ bằng chứng.

Network panel phát huy hiệu quả khi bạn đặt một câu hỏi cụ thể cho từng lần quan sát: trình duyệt đã gửi gì, gửi trong điều kiện nào, nhận lại gì và chính sách nào tác động đến kết quả. Cách kiểm tra có hệ thống này giúp biến lỗi giao diện hoặc thông báo bảo mật thành bằng chứng request/response có thể đối chiếu và xử lý.
