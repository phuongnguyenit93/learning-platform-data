# Chính sách referrer

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích `Referer` header và `document.referrer` tiết lộ thông tin điều hướng như thế nào.
- Phân biệt URL đầy đủ, origin và trường hợp trình duyệt không gửi referrer.
- Đọc và lựa chọn các directive của `Referrer-Policy` theo mức độ nhạy cảm của trang.
- Cấu hình chính sách ở HTTP response header, thẻ meta, phần tử HTML và Fetch API.
- Nhận diện rủi ro khi path hoặc query string chứa token, mã định danh, thông tin tìm kiếm hay dữ liệu cá nhân.
- Kiểm thử referrer trong Network panel và đánh giá các kênh rò rỉ URL mà chính sách này không kiểm soát.

## 1. Referrer là gì?

Khi người dùng mở một trang từ liên kết, hoặc một trang tải tài nguyên từ origin khác, trình duyệt có thể gửi thông tin về URL của trang khởi tạo request. Thông tin này thường nằm trong HTTP request header có tên `Referer` (tên header giữ cách viết lịch sử thiếu chữ “r”). Chính sách quyết định gửi bao nhiêu thông tin được gọi là `Referrer-Policy`.

Ví dụ người dùng đang ở trang:

```text
https://shop.example/account/orders?filter=recent
```

Trang đó có một liên kết đến:

```text
https://partner.example/offer
```

Khi người dùng bấm liên kết, trình duyệt có thể gửi header:

```http
Referer: https://shop.example/
```

hoặc một giá trị đầy đủ hơn, tùy chính sách referrer. Nếu chỉ gửi origin, website nhận được biết người dùng đến từ `https://shop.example` nhưng không biết path hay query cụ thể. Nếu gửi URL đầy đủ, path và query có thể tiết lộ trang người dùng đã xem, từ khóa tìm kiếm, mã hồ sơ hoặc thông tin nằm trong query string.

`Referer` không phải credential và không phải bằng chứng xác thực. Server không được dùng nó làm căn cứ duy nhất để xác định danh tính, quyền truy cập hoặc tính hợp lệ của một request. Đây là metadata điều hướng có thể bị thiếu, bị giới hạn bởi browser hoặc được client ngoài trình duyệt tự tạo.

## 2. Phân biệt Referer header và Referrer-Policy

Hai tên gần giống nhau nhưng có vai trò khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `Referer` request header | Giá trị referrer mà browser gửi trong một request cụ thể, nếu policy cho phép. |
| `Referrer-Policy` response header | Chính sách mà tài liệu hoặc response áp dụng để quyết định lượng referrer gửi trong các request tiếp theo. |
| `<meta name="referrer">` | Cách khai báo policy trong HTML khi không cấu hình bằng response header. |
| `referrerpolicy` attribute | Ghi đè hoặc tinh chỉnh policy cho một phần tử tạo request, như liên kết hoặc ảnh, nếu phần tử hỗ trợ thuộc tính này. |
| `RequestInit.referrerPolicy` | Chọn policy cho một request được tạo bằng Fetch API. |

Ví dụ server trả response cho trang:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8
Referrer-Policy: strict-origin-when-cross-origin
```

Browser áp dụng policy của tài liệu cho các request phát sinh từ tài liệu đó, bao gồm điều hướng và tải tài nguyên. Có thể đặt policy riêng cho một phần tử hoặc request khi cần hạn chế chặt hơn. Nên cấu hình bằng HTTP response header vì header được áp dụng sớm, trước khi browser phân tích nội dung HTML và bắt đầu tải tài nguyên.

## 3. Phần nào của URL có thể bị gửi?

Một URL có thể chứa nhiều thành phần:

```text
https://user:password@app.example.com:8443/account/123?email=a%40example.com#settings
\___/   \____________/ \_______________/ \_________/ \________/ \____________/ \_______/
scheme      userinfo          host:port       path       query      fragment
```

Trong `Referer`, browser không gửi username/password trong userinfo và không gửi fragment (`#...`). Tuy nhiên, path và query có thể được gửi tùy directive. Đây là lý do không nên đặt bí mật trong path hoặc query với giả định rằng fragment sẽ được xử lý giống query.

Ví dụ URL nhạy cảm:

```text
https://app.example/reset-password?token=secret-reset-token
https://app.example/patient/record/12345
https://app.example/search?q=internal+acquisition+plan
```

Nếu trang trên tải ảnh, script, font hoặc analytics từ bên thứ ba bằng policy cho phép gửi URL đầy đủ, nhà cung cấp tài nguyên có thể nhận được path/query qua `Referer`. Nếu người dùng bấm liên kết ngoài, website đích cũng có thể nhận được thông tin đó.

Không nên coi fragment là nơi lưu bí mật an toàn tuyệt đối. Fragment thường không được gửi trong HTTP request hoặc `Referer`, nhưng vẫn có thể được đọc bởi JavaScript trên trang, xuất hiện trong lịch sử browser, được ghi vào telemetry hoặc bị lộ qua thao tác sao chép/chia sẻ URL.

## 4. Các directive của Referrer-Policy

`Referrer-Policy` hỗ trợ các giá trị sau. Bảng giả định tài liệu nguồn là HTTPS và so sánh request cùng origin, cross-origin vẫn HTTPS, hoặc downgrade từ HTTPS sang HTTP.

| Directive | Cùng origin | Cross-origin cùng mức bảo mật | Downgrade HTTPS → HTTP |
| --- | --- | --- | --- |
| `no-referrer` | Không gửi | Không gửi | Không gửi |
| `no-referrer-when-downgrade` | URL đầy đủ | URL đầy đủ | Không gửi |
| `origin` | Chỉ origin | Chỉ origin | Chỉ origin |
| `origin-when-cross-origin` | URL đầy đủ | Chỉ origin | Chỉ origin |
| `same-origin` | URL đầy đủ | Không gửi | Không gửi |
| `strict-origin` | Chỉ origin | Chỉ origin | Không gửi |
| `strict-origin-when-cross-origin` | URL đầy đủ | Chỉ origin | Không gửi |
| `unsafe-url` | URL đầy đủ | URL đầy đủ | URL đầy đủ |

“URL đầy đủ” trong bảng không bao gồm userinfo và fragment. Với `origin`, browser chỉ gửi scheme, host và port phù hợp, ví dụ `https://app.example.com/`.

### 4.1. `no-referrer`

Không gửi `Referer` trong request phát sinh từ tài liệu có policy này. Đây là lựa chọn mạnh khi trang xử lý thông tin nhạy cảm và không có nhu cầu chia sẻ nguồn điều hướng.

```http
Referrer-Policy: no-referrer
```

Ưu điểm là giảm đáng kể thông tin URL bị tiết lộ qua header. Hạn chế là hệ thống phân tích, liên kết đối tác hoặc luồng cần biết nguồn truy cập sẽ không nhận được referrer. Không dùng referrer để đo lường nếu dữ liệu đó không thực sự cần thiết.

### 4.2. `same-origin`

Chỉ gửi URL referrer khi request cùng origin. Khi request đến origin khác, không gửi header.

```http
Referrer-Policy: same-origin
```

Policy này phù hợp khi ứng dụng muốn giữ thông tin điều hướng nội bộ nhưng không muốn tiết lộ cả origin cho bên ngoài. Cần lưu ý subdomain khác nhau là cross-origin, dù chúng có thể cùng site.

### 4.3. `origin`

Chỉ gửi origin, không gửi path hoặc query. Ví dụ:

```http
Referrer-Policy: origin
```

Policy này vẫn gửi origin khi điều hướng từ HTTPS xuống HTTP. Nếu cần chặn việc tiết lộ ngay cả origin trong trường hợp downgrade, dùng `strict-origin` hoặc `strict-origin-when-cross-origin`.

### 4.4. `strict-origin`

Gửi origin khi request có mức bảo mật bằng hoặc cao hơn tài liệu nguồn; không gửi referrer khi downgrade từ HTTPS xuống HTTP.

```http
Referrer-Policy: strict-origin
```

Policy này không tiết lộ path/query ngay cả với request cùng origin. Nó phù hợp khi cần chia sẻ nguồn gốc ở mức site/origin nhưng không muốn tiết lộ trang cụ thể.

### 4.5. `strict-origin-when-cross-origin`

Đây là lựa chọn mặc định phổ biến ở các browser hiện đại khi website không đặt policy khác:

- Request cùng origin: gửi URL đầy đủ.
- Request cross-origin nhưng không downgrade: chỉ gửi origin.
- Request downgrade HTTPS sang HTTP: không gửi referrer.

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Policy này cân bằng giữa khả năng chẩn đoán điều hướng nội bộ và hạn chế lộ URL cho website ngoài. Tuy nhiên, path/query vẫn có thể xuất hiện trong request cùng origin. Nếu URL nội bộ chứa token hoặc dữ liệu nhạy cảm, policy mặc định không đủ để bảo vệ chúng khỏi log và script cùng origin.

### 4.6. `origin-when-cross-origin`

Gửi URL đầy đủ cho request cùng origin và chỉ gửi origin cho request cross-origin. Khác với `strict-origin-when-cross-origin`, policy này không chặn referrer chỉ vì request là downgrade.

```http
Referrer-Policy: origin-when-cross-origin
```

Vì vẫn có thể gửi origin khi downgrade, hãy cân nhắc kỹ khi trang HTTPS tạo request đến endpoint HTTP. Trong ứng dụng production, nên tránh mixed content và ưu tiên policy có kiểm soát downgrade.

### 4.7. `no-referrer-when-downgrade`

Gửi URL đầy đủ trừ khi request đi từ mức bảo mật cao xuống mức thấp hơn, chẳng hạn HTTPS sang HTTP. Đây từng là giá trị mặc định ở nhiều browser cũ, nhưng có thể tiết lộ path/query cho origin bên ngoài khi cả hai đều HTTPS.

```http
Referrer-Policy: no-referrer-when-downgrade
```

Không nên chọn policy này cho ứng dụng mới nếu không có yêu cầu tương thích cụ thể. `strict-origin-when-cross-origin` thường giới hạn thông tin tốt hơn.

### 4.8. `unsafe-url`

Gửi URL đầy đủ cho request cùng origin, cross-origin và cả downgrade. Đây là policy dễ làm lộ path/query nhất.

```http
Referrer-Policy: unsafe-url
```

Không dùng cho trang có thông tin nhạy cảm. Chỉ cân nhắc trong hệ thống kiểm soát chặt, có lý do nghiệp vụ rõ và đã đánh giá rằng URL không chứa dữ liệu nhạy cảm. Ngay cả khi dùng `unsafe-url`, browser vẫn không gửi userinfo hoặc fragment trong `Referer`.

## 5. Chọn policy cho từng loại ứng dụng

Không có một policy duy nhất tối ưu cho mọi trang. Hãy xem dữ liệu có trong URL, nhu cầu điều hướng và các bên thứ ba được tải trên trang.

| Loại trang | Policy khởi đầu nên cân nhắc | Lý do |
| --- | --- | --- |
| Trang công khai, nội dung thông thường | `strict-origin-when-cross-origin` | Giữ URL đầy đủ cho điều hướng nội bộ, chỉ gửi origin ra ngoài và chặn downgrade. |
| Trang tài khoản, dashboard nội bộ | `strict-origin` hoặc `same-origin` | Tránh gửi path/query ra ngoài; chọn `same-origin` nếu không muốn tiết lộ cả origin cho bên ngoài. |
| Trang xử lý dữ liệu sức khỏe, tài chính hoặc hồ sơ nhạy cảm | `no-referrer` | Không chia sẻ URL nguồn qua request phát sinh từ trang. |
| Trang callback OAuth/OIDC hoặc reset password | `no-referrer` kết hợp URL sạch và không tải third-party resource không cần thiết | Giảm khả năng code/token trong URL bị gửi đến tài nguyên khác. |
| Trang có liên kết đối tác cần đo lường nguồn truy cập | `strict-origin-when-cross-origin` hoặc policy riêng trên liên kết | Chỉ chia sẻ mức thông tin cần thiết; không gửi path/query nếu không cần. |

Đây là điểm bắt đầu, không phải thay thế threat model. Nếu trang chứa token trong query string, cần loại bỏ token khỏi URL càng sớm càng tốt; đổi policy không giải quyết việc token đã xuất hiện trong browser history, server log hoặc analytics.

## 6. Cấu hình policy ở HTTP response header

Nên cấu hình `Referrer-Policy` trên response của HTML document từ web server, reverse proxy hoặc CDN:

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Đối với khu vực nhạy cảm, có thể áp dụng policy nghiêm ngặt hơn ở route tương ứng:

```http
Referrer-Policy: no-referrer
Cache-Control: no-store
```

Ví dụ cấu hình Nginx cho website thông thường:

```nginx
location / {
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}

location /account/ {
    add_header Referrer-Policy "no-referrer" always;
    add_header Cache-Control "no-store" always;
}
```

Đây là ví dụ cấu hình; cần kiểm tra cách server kế thừa `add_header`, response lỗi, redirect và các location lồng nhau. Nếu CDN hoặc reverse proxy cũng thêm header, tránh phát nhiều policy mâu thuẫn. Kiểm tra response cuối cùng mà browser thực sự nhận được.

Response header có lợi thế được gửi trước khi browser parse HTML. Với trang được render qua nhiều tầng proxy, hãy xác minh header ở production/staging bằng Network panel hoặc lệnh HTTP phù hợp.

## 7. Cấu hình bằng meta element

Có thể khai báo policy trong phần `<head>`:

```html
<head>
  <meta name="referrer" content="strict-origin-when-cross-origin">
</head>
```

Với trang nhạy cảm:

```html
<head>
  <meta name="referrer" content="no-referrer">
</head>
```

Meta policy chỉ có hiệu lực sau khi browser đọc được thẻ. Nếu tài liệu đã tải tài nguyên hoặc điều hướng trước đó, những request đã phát sinh không thể được bảo vệ hồi tố. Vì vậy, response header là lựa chọn đáng tin cậy hơn; meta hữu ích khi không thể cấu hình server hoặc như lớp khai báo trong tài liệu.

Không đặt nhiều meta referrer khác nhau với kỳ vọng chúng sẽ được kết hợp thành policy an toàn. Hãy chọn một policy rõ ràng và kiểm tra response header cùng HTML cuối cùng.

## 8. Cấu hình riêng cho liên kết và tài nguyên

### 8.1. Liên kết HTML

Thuộc tính `referrerpolicy` cho phép giảm thông tin referrer của một liên kết cụ thể:

```html
<a
  href="https://partner.example/offer"
  referrerpolicy="no-referrer"
>
  Mở đối tác
</a>
```

Nếu không muốn gửi referrer và cũng muốn ngăn trang đích truy cập `window.opener`, có thể dùng:

```html
<a href="https://partner.example/offer" rel="noreferrer">
  Mở trang ngoài
</a>
```

`rel="noreferrer"` ngăn gửi referrer; trên các browser hiện đại, nó cũng ngụ ý hành vi `noopener`, giúp trang mới không điều khiển được cửa sổ mở nó qua `window.opener`. Nếu chỉ cần kiểm soát referrer, dùng `referrerpolicy` để thể hiện mục đích rõ ràng.

### 8.2. Ảnh, script, iframe và tài nguyên khác

Nhiều phần tử HTML hỗ trợ thuộc tính `referrerpolicy`:

```html
<img
  src="https://images.cdn.example/banner.webp"
  alt="Banner"
  referrerpolicy="no-referrer"
>

<iframe
  src="https://embed.vendor.example/widget"
  title="Widget"
  referrerpolicy="strict-origin"
></iframe>

<script
  src="https://cdn.example/library.js"
  referrerpolicy="no-referrer"
></script>
```

Hãy kiểm tra thuộc tính được hỗ trợ trên loại phần tử và browser mục tiêu. Nếu một tài nguyên bên thứ ba không cần biết trang nào đã tải nó, `no-referrer` có thể giảm thông tin gửi đến nhà cung cấp. Việc ẩn referrer không thay thế kiểm soát nguồn script, Subresource Integrity hoặc CSP.

### 8.3. Fetch API

Fetch API cho phép đặt `referrerPolicy` cho từng request:

```js
const response = await fetch("https://metrics.example/collect", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ event: "page-view" }),
  referrerPolicy: "no-referrer"
});
```

`referrerPolicy` chỉ điều khiển thông tin referrer của request; nó không xóa URL khỏi body, query, header tùy chỉnh hoặc dữ liệu analytics mà ứng dụng tự gửi. Không đưa thông tin nhạy cảm vào payload chỉ vì request đã dùng `no-referrer`.

## 9. `document.referrer` ở trang đích

Trang nhận điều hướng có thể đọc `document.referrer` để biết referrer mà browser đã gửi cho lần điều hướng đó:

```js
if (document.referrer) {
  console.log("Trang nguồn:", document.referrer);
} else {
  console.log("Không có referrer được cung cấp.");
}
```

Giá trị có thể rỗng nếu người dùng mở URL trực tiếp, đi từ bookmark, browser không gửi referrer hoặc policy của trang nguồn đã chặn nó. Nếu policy chỉ gửi origin, `document.referrer` ở trang đích cũng chỉ chứa origin. Không dùng `document.referrer` làm bằng chứng đăng nhập, CSRF token hoặc căn cứ authorization.

`document.referrer` mô tả nguồn điều hướng của document hiện tại, không phải danh sách mọi trang người dùng đã truy cập. Nó cũng không cho biết chắc chắn người dùng đã click một liên kết; điều hướng có thể được tạo bởi script, form, redirect hoặc browser.

## 10. Referrer và các luồng URL nhạy cảm

### 10.1. Password reset và magic link

Một liên kết đặt lại password thường có token dùng một lần trong URL. Nếu trang reset tải script, ảnh hoặc analytics từ bên thứ ba trước khi xử lý token, URL có thể bị tiết lộ qua referrer nếu policy cho phép gửi path/query.

Biện pháp nên áp dụng:

- Dùng `Referrer-Policy: no-referrer` cho route reset/magic link.
- Không tải analytics, quảng cáo, widget hoặc tài nguyên bên thứ ba không cần thiết trên trang xử lý token.
- Dùng token ngẫu nhiên, thời hạn ngắn, ràng buộc với đúng user và chỉ sử dụng một lần.
- Sau khi xác minh token, tạo session hoặc trạng thái giao dịch phía server rồi chuyển sang URL sạch bằng redirect hoặc `history.replaceState()` phù hợp.
- Không ghi URL chứa token vào access log, APM, error tracking hoặc analytics.
- Không coi referrer policy là biện pháp thay thế cho token one-time và server-side validation.

### 10.2. OAuth/OIDC callback

Authorization code có thể xuất hiện trong query string ở callback. Code cần được bảo vệ bằng PKCE, `state`, thời hạn ngắn và quy tắc dùng một lần. Trang callback nên tránh tải tài nguyên bên thứ ba trước khi xử lý code, dùng policy hạn chế referrer và không gửi URL callback nguyên vẹn đến analytics.

Sau khi xử lý callback thành công, ứng dụng nên chuyển đến URL nội bộ sạch. Không ghi code, state hoặc token thô vào log. `Referrer-Policy` giúp giảm một đường rò rỉ khi callback điều hướng/tải tài nguyên, nhưng không xóa code khỏi request callback đã đến server hoặc browser history.

### 10.3. Tìm kiếm và dữ liệu cá nhân trong query

Query string có thể chứa email, số hồ sơ, từ khóa tìm kiếm hoặc bộ lọc nội bộ. Nếu các giá trị này nhạy cảm, cân nhắc POST hoặc lưu trạng thái ở server thay vì đưa vào URL. Nếu cần URL có thể chia sẻ, chỉ chứa dữ liệu không nhạy cảm và đã được phép công khai.

## 11. Referrer-Policy không ngăn mọi URL leak

Chính sách referrer chỉ kiểm soát phần thông tin referrer mà browser gửi trong request. Nó không giải quyết các kênh rò rỉ khác:

| Kênh | Ví dụ | Biện pháp bổ sung |
| --- | --- | --- |
| Browser history | Token trong query vẫn có thể nằm trong lịch sử điều hướng. | Không đặt bí mật trong URL; dùng token ngắn hạn và làm sạch URL sau khi xử lý. |
| Server/proxy logs | Request đến endpoint chứa token trong path/query được ghi vào access log. | Redact query/path nhạy cảm, hạn chế quyền truy cập log và đặt retention. |
| Analytics/error tracking | Script ghi `location.href`, query hoặc route vào event. | Allowlist trường cần thu thập, loại bỏ query nhạy cảm và kiểm soát SDK. |
| Redirect chain | URL nhạy cảm đi qua nhiều endpoint hoặc hệ thống tracking. | Tránh redirect không cần thiết, kiểm soát đích và không truyền secret trong URL. |
| JavaScript cùng origin | Script đọc `location.href`, query string hoặc fragment. | Phòng chống XSS, giảm script bên thứ ba và không đặt secret trong URL. |
| Người dùng/chia sẻ thủ công | URL được copy, chụp màn hình hoặc gửi qua chat. | Thiết kế URL không chứa bí mật và cung cấp cơ chế chia sẻ an toàn. |
| Browser extension hoặc phần mềm trên thiết bị | Extension có quyền đọc trang/lịch sử. | Giảm dữ liệu nhạy cảm trên client; áp dụng quản trị thiết bị theo threat model. |

Một URL nhạy cảm có thể bị ghi log ở server nhận request ngay cả khi `Referrer-Policy: no-referrer` được đặt đúng, vì chính URL đó là request target. Chính sách không xóa dữ liệu đã được gửi trong request URL.

## 12. Redirect và referrer

Redirect có thể làm URL đi qua nhiều hệ thống. Ví dụ trang A chuyển sang tracker B rồi mới đến trang C. Mỗi hop là một request/response riêng và browser tính referrer theo policy đang áp dụng, URL trước đó và các quy tắc redirect. Không nên dựa vào việc redirect sẽ tự xóa mọi query nhạy cảm.

Nếu một URL chứa token được redirect sang URL khác, token có thể xuất hiện trong log của endpoint trung gian hoặc được chuyển tiếp qua `Location`. Hãy thiết kế redirect để không mang theo credential, xác thực token ở endpoint cần thiết rồi tạo URL đích sạch. Kiểm tra cả redirect server-side và điều hướng do JavaScript thực hiện.

Đối với liên kết ngoài, dùng `rel="noreferrer"` hoặc `referrerpolicy` phù hợp nếu không muốn trang đích nhận nguồn điều hướng. Với trang nhận dữ liệu nhạy cảm, đặt policy ở response của chính trang đó để hạn chế các request tiếp theo.

## 13. Quy trình kiểm thử bằng DevTools

Tạo hai origin thử nghiệm, ví dụ `https://app.test` và `https://partner.test`. Trên trang app, tạo URL có marker giả trong path/query; không dùng token thật hoặc dữ liệu cá nhân.

1. Cấu hình `Referrer-Policy: strict-origin-when-cross-origin` trên response của app.
2. Tải tài liệu và kiểm tra response header trong Network.
3. Bấm liên kết đến partner; chọn request điều hướng và kiểm tra request header `Referer`.
4. Thử tải ảnh/script cross-origin để quan sát referrer của subresource request.
5. Đổi policy lần lượt thành `no-referrer`, `origin`, `same-origin`, `strict-origin` và `unsafe-url`; so sánh header thực tế.
6. Thêm `referrerpolicy="no-referrer"` cho một liên kết và xác nhận chỉ request đó bị giới hạn theo thuộc tính.
7. Thực hiện `fetch()` với `referrerPolicy: "no-referrer"` và kiểm tra request.
8. Ở trang partner, đọc `document.referrer` và so sánh với header mà DevTools hiển thị.
9. Thử điều hướng từ HTTPS đến HTTP trong lab nếu môi trường cho phép; xác nhận các policy strict không gửi referrer khi downgrade.
10. Kiểm tra redirect chain, URL cuối cùng, server log và analytics để xác định các đường rò rỉ ngoài `Referer`.

Trong Network panel, header `Referer` là bằng chứng trực tiếp về dữ liệu browser đã gửi trong request đó. `document.referrer` là góc nhìn của document nhận. Hai nơi có thể thể hiện cùng thông tin điều hướng nhưng không phải API để xác định danh tính hoặc quyền.

Khi kiểm thử, nhớ xóa cache hoặc dùng profile test mới nếu cần để tránh nhầm response cũ. Kiểm tra response HTML thực tế sau CDN/proxy; việc source code có cấu hình header không đảm bảo header đã đến browser.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `unsafe-url` trên toàn site | Path và query có thể bị gửi đến origin bên ngoài, kể cả khi downgrade. | Dùng `strict-origin-when-cross-origin` hoặc policy chặt hơn. |
| Nghĩ `strict-origin-when-cross-origin` che path/query ở mọi nơi | Request cùng origin vẫn có thể nhận URL đầy đủ. | Dùng `same-origin`, `strict-origin` hoặc `no-referrer` cho route nhạy cảm. |
| Chỉ đặt meta referrer sau các script/ảnh | Request phát sinh trước khi browser đọc meta có thể đã gửi referrer theo policy trước đó. | Đặt HTTP response header; nếu dùng meta, đặt sớm trong head. |
| Đưa reset token vào query và chỉ dựa vào no-referrer | Token vẫn có thể vào history, server log, analytics hoặc URL được chia sẻ. | Thiết kế token one-time, redact log, không tải bên thứ ba và làm sạch URL. |
| Dùng `document.referrer` để xác thực request | Referrer có thể rỗng, bị rút gọn hoặc giả mạo bởi non-browser client. | Dùng session, CSRF token, xác thực và authorization phía server. |
| Cho rằng CORS kiểm soát referrer | CORS điều khiển quyền đọc response; Referrer-Policy điều khiển metadata referrer. | Cấu hình riêng từng cơ chế theo mục đích. |
| Quên liên kết hoặc iframe bên thứ ba | Nhà cung cấp có thể nhận URL nguồn nhiều hơn mức cần thiết. | Đặt `referrerpolicy` trên phần tử hoặc policy nghiêm ngặt ở trang. |
| Không kiểm tra response production | CDN/proxy có thể ghi đè hoặc bỏ header. | Kiểm tra header thực tế trong Network trên môi trường triển khai. |

## 15. Bài thực hành

Xây dựng một trang thử nghiệm có dashboard, trang reset password giả lập và một liên kết đến origin bên ngoài. Chỉ dùng marker không nhạy cảm.

1. Thiết lập response header `Referrer-Policy: strict-origin-when-cross-origin` cho trang công khai.
2. Tạo route `/account/demo-record?marker=private-demo` và quan sát referrer khi tải tài nguyên cùng origin và cross-origin.
3. Áp dụng `no-referrer` cho route reset giả lập; xác nhận ảnh, script và điều hướng ngoài không nhận `Referer`.
4. Thêm một liên kết `referrerpolicy="origin"` và một liên kết `rel="noreferrer"`; so sánh header và `window.opener` ở trang đích.
5. Gọi Fetch API với `referrerPolicy` khác nhau và kiểm tra Network.
6. Tạo callback OAuth giả lập có query marker, xử lý marker rồi dùng `history.replaceState()` để làm sạch URL; kiểm tra server log và analytics test.
7. Thử `strict-origin`, `same-origin`, `origin-when-cross-origin` và `unsafe-url` trong lab để quan sát khác biệt.
8. Viết policy đề xuất cho trang công khai, dashboard, callback đăng nhập và trang xử lý dữ liệu nhạy cảm; giải thích lý do.

Hoàn thành bài thực hành khi bạn dự đoán đúng phần URL sẽ xuất hiện trong `Referer`, biết cách đặt policy ở response/element/request, và chỉ ra được những kênh rò rỉ URL còn tồn tại dù browser không gửi referrer.
