# MIME type

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích MIME type (media type) mô tả định dạng của một representation HTTP như thế nào.
- Đọc cấu trúc `type/subtype` và các tham số như `charset` hoặc `boundary`.
- Phân biệt `Content-Type`, `Accept`, `Content-Encoding` và phần mở rộng file.
- Hiểu vì sao browser có thể MIME sniffing và cách `X-Content-Type-Options: nosniff` giới hạn một số hành vi đó.
- Nhận diện rủi ro MIME confusion, file polyglot, HTML/SVG chủ động và upload có Content-Type giả mạo.
- Phục vụ JSON, HTML, script, ảnh và file tải xuống với MIME type cùng security header phù hợp.
- Kiểm thử MIME type thực tế bằng DevTools và kiểm tra cả header lẫn nội dung byte.

## 1. MIME type là gì?

MIME type, tên chuẩn hiện nay thường gọi là media type, mô tả định dạng dữ liệu của một representation. Trong HTTP, server thường gửi media type qua response header `Content-Type` để cho client biết nội dung body là HTML, JSON, ảnh, JavaScript, PDF hay một loại dữ liệu khác.

Ví dụ:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=utf-8

<!doctype html>
<html lang="vi">
  <title>Trang chủ</title>
</html>
```

Browser dùng media type cùng ngữ cảnh sử dụng để chọn cách xử lý representation: parse HTML, giải mã ảnh, thực thi script, hiển thị PDF hoặc tải dữ liệu dạng nhị phân. MIME type vì vậy là một phần của ranh giới bảo mật giữa dữ liệu và nội dung có thể được browser diễn giải hoặc thực thi.

Nếu server gửi sai loại nội dung, browser có thể hiển thị dữ liệu theo cách không mong muốn hoặc, trong một số ngữ cảnh, nhận diện nội dung bằng cách kiểm tra byte (MIME sniffing). Kẻ tấn công có thể lợi dụng sự không thống nhất giữa phần mở rộng, header và nội dung thực để biến file được coi là dữ liệu thụ động thành nội dung chủ động như HTML hoặc script.

## 2. Cấu trúc media type

Media type có cấu trúc cơ bản:

```text
type/subtype; parameter=value
```

Trong đó:

- `type` là nhóm tổng quát, ví dụ `text`, `image`, `audio`, `video`, `application` hoặc `font`.
- `subtype` xác định định dạng cụ thể, ví dụ `html`, `plain`, `jpeg`, `png`, `json`, `pdf` hoặc `zip`.
- `parameter` bổ sung thông tin về representation, ví dụ `charset=utf-8` hoặc `boundary=...`.

Ví dụ:

```http
Content-Type: text/plain; charset=utf-8
Content-Type: application/json
Content-Type: multipart/form-data; boundary=----browser-form-boundary
Content-Type: image/svg+xml
```

Tên type, subtype và tên parameter không phân biệt chữ hoa/chữ thường theo quy tắc media type. Cách diễn giải giá trị parameter phụ thuộc từng parameter; không nên mặc định mọi giá trị đều không phân biệt hoa/thường. Trong thực tế, nên dùng cách viết lowercase nhất quán cho type, subtype và tên parameter. Giá trị parameter có thể cần đặt trong dấu nháy nếu chứa ký tự đặc biệt hoặc khoảng trắng theo cú pháp HTTP.

### 2.1. Một số MIME type thường gặp

| Nội dung | Media type thường dùng | Lưu ý bảo mật |
| --- | --- | --- |
| HTML | `text/html` | Browser parse thành document; không phục vụ nội dung không tin cậy dưới origin ứng dụng. |
| Văn bản thuần | `text/plain` | Thích hợp cho log hoặc nội dung text; vẫn phải encode khi đưa vào HTML của ứng dụng. |
| CSS | `text/css` | Dùng đúng type cho stylesheet; `nosniff` có ý nghĩa với request đích style. |
| JavaScript | `text/javascript` | Chỉ cho phép nguồn script đáng tin cậy; MIME đúng không chứng minh script an toàn. |
| JSON | `application/json` | Dùng cho API JSON; không trả JSON cá nhân dưới `text/html`. |
| XML | `application/xml` | Parser XML cần cấu hình an toàn, tránh external entity nếu thư viện cho phép. |
| JPEG | `image/jpeg` | Header không chứng minh byte là ảnh JPEG hợp lệ. |
| PNG | `image/png` | Kiểm tra nội dung ảnh ở server khi nhận file không tin cậy. |
| SVG | `image/svg+xml` | SVG là định dạng XML có khả năng chứa nội dung chủ động; cần xử lý như nội dung có rủi ro. |
| PDF | `application/pdf` | Có thể chứa hành vi chủ động/interactive; cân nhắc attachment hoặc viewer cô lập. |
| ZIP | `application/zip` | Giải nén phải giới hạn kích thước, entry, độ sâu và đường dẫn. |
| Binary chung | `application/octet-stream` | Báo dữ liệu nhị phân; không bảo đảm file an toàn hoặc browser không thể mở. |
| WebAssembly | `application/wasm` | Dùng đúng type khi tải module WebAssembly. |

Danh sách này không đầy đủ. Khi chọn type cho định dạng cụ thể, tham khảo media type registry và tài liệu của định dạng. Không tự đặt subtype tùy ý nếu đã có type được đăng ký và hỗ trợ rộng rãi.

### 2.2. Charset

Một số media type dạng text có thể chỉ định bộ mã ký tự:

```http
Content-Type: text/html; charset=utf-8
Content-Type: text/css; charset=utf-8
Content-Type: text/plain; charset=utf-8
```

UTF-8 là lựa chọn phù hợp cho hầu hết nội dung web hiện đại. Với HTML, khai báo charset ở HTTP header giúp browser biết cách giải mã sớm; thẻ `<meta charset="utf-8">` có thể bổ sung trong tài liệu.

JSON trong trao đổi giữa các hệ thống hiện đại được mã hóa UTF-8. `application/json` thường không cần tham số `charset`; không nên dùng một charset khác để tạo kỳ vọng browser sẽ giải mã JSON theo cách riêng.

Charset không phải cơ chế mã hóa bí mật. Nó chỉ xác định cách diễn giải byte thành ký tự. Chọn sai charset có thể gây lỗi hiển thị, lỗi parser hoặc khác biệt trong quá trình kiểm tra nội dung.

### 2.3. Structured syntax suffix

Một số subtype dùng hậu tố như `+json` hoặc `+xml` để chỉ định cú pháp nền. Ví dụ:

```http
Content-Type: application/problem+json
Content-Type: application/ld+json
Content-Type: image/svg+xml
```

`application/problem+json` là một định dạng JSON có cấu trúc riêng; `application/ld+json` thường dùng cho JSON-LD. Hậu tố giúp client nhận biết cú pháp nền nhưng không có nghĩa mọi subtype có cùng ngữ nghĩa nghiệp vụ hoặc cùng mức độ tin cậy.

## 3. Phân biệt Content-Type, Accept và Content-Encoding

Ba header này liên quan đến biểu diễn dữ liệu nhưng làm nhiệm vụ khác nhau:

| Header | Hướng thường gặp | Ý nghĩa |
| --- | --- | --- |
| `Content-Type` | Request hoặc response | Media type của body đang được gửi. |
| `Accept` | Request | Các media type client có thể xử lý hoặc ưu tiên nhận. |
| `Content-Encoding` | Request hoặc response | Phép mã hóa nội dung được áp dụng lên representation, ví dụ `gzip` hoặc `br`. |

Ví dụ browser gửi request:

```http
GET /api/profile HTTP/1.1
Host: app.example.com
Accept: application/json
Accept-Encoding: gzip, br
```

Server trả:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: br
Vary: Accept-Encoding

{"displayName":"Lan"}
```

`Content-Type` mô tả dữ liệu sau khi giải mã content encoding; `Content-Encoding` cho biết cách giải mã representation. Không đặt `Content-Type: gzip` chỉ vì body được nén bằng gzip. Media type vẫn có thể là `application/json` trong khi `Content-Encoding: gzip`.

Nếu response thay đổi theo `Accept`, server có thể cần `Vary: Accept` để cache phân biệt representation. Nếu response thay đổi theo `Accept-Encoding`, cần `Vary: Accept-Encoding`. Cache key phải phản ánh các header thực sự ảnh hưởng đến nội dung.

## 4. Content-Type trong request

### 4.1. JSON request

Khi gửi JSON bằng Fetch, khai báo `Content-Type: application/json`:

```js
const response = await fetch("/api/profile", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  body: JSON.stringify({ displayName: "Lan" })
});
```

Server cần kiểm tra media type trước khi parse body và giới hạn kích thước body. Không chỉ kiểm tra header: client có thể khai báo JSON nhưng gửi byte không phải JSON. Parser phải xử lý lỗi cú pháp và schema validation phải kiểm tra cấu trúc, kiểu dữ liệu, trường được phép cùng giới hạn độ dài.

### 4.2. Form URL encoded

Form truyền thống có thể gửi dữ liệu theo `application/x-www-form-urlencoded`:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=lan&password=example
```

Server cần bảo vệ endpoint đăng nhập bằng HTTPS, rate limit và các kiểm soát xác thực phù hợp. `Content-Type` chỉ mô tả cách mã hóa form body; nó không chứng minh request đến từ giao diện hợp lệ hoặc người dùng có quyền.

### 4.3. Multipart form data

Upload file qua HTML form hoặc Fetch thường dùng `multipart/form-data` với boundary phân tách các part:

```http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----form-boundary

------form-boundary
Content-Disposition: form-data; name="description"

Ảnh đại diện
------form-boundary
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

...file bytes...
------form-boundary--
```

Khi dùng `FormData` với Fetch, không tự đặt header `Content-Type` vì browser phải tự tạo boundary và thêm đúng giá trị vào header:

```js
const form = new FormData();
form.append("description", "Ảnh đại diện");
form.append("file", fileInput.files[0]);

await fetch("/api/upload", {
  method: "POST",
  body: form,
  credentials: "same-origin"
});
```

Media type ở từng part, tên file và phần mở rộng do client gửi đều là dữ liệu không tin cậy. Server không được coi `Content-Type: image/png` trong multipart là bằng chứng file thực sự là PNG.

## 5. Browser MIME sniffing

MIME sniffing là quá trình browser phân tích một phần byte của response để suy đoán định dạng khi header thiếu, không rõ ràng hoặc trong những ngữ cảnh mà thuật toán sniffing được áp dụng. Hành vi này có lịch sử nhằm tương thích với website cũ, nơi server thường gửi MIME type không chính xác.

Vấn đề bảo mật xuất hiện khi server nghĩ nội dung là text hoặc ảnh nhưng browser nhận diện nó là HTML hoặc một định dạng có thể thực thi. Ví dụ, người dùng upload một file có nội dung HTML nhưng server lưu nó dưới phần mở rộng `.txt` và trả header không chính xác. Nếu browser sniff hoặc xử lý theo ngữ cảnh khác, nội dung có thể được diễn giải theo cách nguy hiểm.

MIME sniffing không giống việc browser chỉ nhìn phần mở rộng file. Browser có thể xét header, byte đầu, destination của request và các quy tắc riêng theo loại tài nguyên. Thuật toán khác nhau giữa document navigation, script, stylesheet, ảnh và các ngữ cảnh khác.

### 5.1. MIME confusion

MIME confusion xảy ra khi các thành phần không thống nhất về định dạng thực:

```text
Tên file:       avatar.png
Upload header:  Content-Type: image/png
Byte thực tế:   nội dung HTML
Server header:  Content-Type: text/plain
Browser:        có thể xử lý khác theo context và sniffing rules
```

Kẻ tấn công có thể lợi dụng sự khác biệt này để đưa nội dung chủ động vào nơi ứng dụng nghĩ là dữ liệu thụ động. Nguy cơ tăng nếu file được phục vụ từ origin có cookie hoặc quyền truy cập API của ứng dụng.

### 5.2. File polyglot

File polyglot là file có thể được diễn giải hợp lệ theo nhiều định dạng hoặc parser khác nhau. Ví dụ một tập byte có thể thỏa một số quy tắc cấu trúc của ảnh đồng thời chứa nội dung mà parser khác nhận diện theo cách khác. Chỉ kiểm tra magic bytes đầu file không đủ để chứng minh toàn bộ file an toàn.

Với file upload, cần kiểm tra nhiều lớp: loại file được phép theo nghiệp vụ, signature/format thực, khả năng parse đầy đủ bằng thư viện phù hợp, kích thước, cấu trúc và nội dung. Nếu có thể, decode rồi encode lại ảnh sang định dạng chuẩn để loại bỏ metadata hoặc cấu trúc bất thường; tuy nhiên thao tác này cũng cần thư viện cập nhật và giới hạn tài nguyên.

## 6. X-Content-Type-Options: nosniff

Server có thể gửi:

```http
X-Content-Type-Options: nosniff
```

Header này yêu cầu browser hạn chế MIME sniffing trong những ngữ cảnh được chuẩn hóa. Đặc biệt, Fetch yêu cầu chặn một số request đích `script` hoặc `style` nếu response MIME type không phù hợp. Điều này giúp ngăn response text/HTML bị dùng như script hoặc stylesheet chỉ nhờ sniffing.

`nosniff` là lớp phòng vệ hữu ích, nhưng không có nghĩa browser không bao giờ kiểm tra nội dung hoặc mọi document navigation đều bị chặn nếu type không đúng. Hành vi cụ thể phụ thuộc destination và browser. Vì vậy:

- Trả `Content-Type` đúng cho mọi response.
- Gửi `X-Content-Type-Options: nosniff` như header mặc định cho nội dung web.
- Không dựa vào `nosniff` để biến HTML/SVG độc hại thành file vô hại.
- Không phục vụ file không tin cậy dưới origin chính chỉ vì đã thêm `nosniff`.
- Kết hợp CSP, sandbox, `Content-Disposition: attachment` và origin riêng khi phù hợp.

Ví dụ response cho JavaScript:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=utf-8
X-Content-Type-Options: nosniff

console.log("Ứng dụng đã tải.");
```

Nếu server trả JavaScript dưới `text/plain`, browser có thể chặn khi tải bằng script destination với `nosniff`. Sửa đúng MIME type là cách xử lý đúng; không bỏ `nosniff` chỉ để che lỗi cấu hình.

## 7. MIME type và rủi ro XSS

MIME type không tự tạo ra XSS, nhưng cấu hình sai có thể làm nội dung không tin cậy được browser diễn giải như HTML hoặc script. Một số trường hợp cần đặc biệt chú ý:

- Server trả nội dung do người dùng kiểm soát dưới `text/html`.
- File HTML/SVG upload được mở inline trong origin có session ứng dụng.
- API trả JSON nhưng khai báo `text/html`, khiến browser hoặc hệ thống downstream xử lý sai ngữ cảnh.
- Endpoint phản chiếu dữ liệu người dùng trong response với MIME type có thể thực thi.
- CDN hoặc proxy thay đổi `Content-Type` so với origin.

### 7.1. JSON API

API trả JSON nên dùng:

```http
Content-Type: application/json
X-Content-Type-Options: nosniff
Cache-Control: no-store
```

Không trả JSON dưới `text/html` chỉ vì muốn browser hiển thị đẹp. Nếu cần xem JSON trong browser, dùng viewer hoặc trang developer riêng có encode output đúng cách.

Khi JavaScript đọc JSON bằng Fetch, parse bằng `response.json()` sau khi kiểm tra status và xử lý lỗi. Không nối trực tiếp chuỗi JSON vào `innerHTML`. JSON hợp lệ vẫn có thể chứa chuỗi HTML hoặc nội dung độc hại nếu ứng dụng render sai ngữ cảnh.

### 7.2. HTML và SVG do người dùng tải lên

HTML và SVG có thể chứa script, event handler, liên kết ngoài hoặc nội dung active tùy cách browser hiển thị. Nếu cần cho tải về, dùng `Content-Disposition: attachment` và cân nhắc origin riêng. Nếu cần preview, dùng sandbox hoặc renderer cô lập, CSP phù hợp và quy trình sanitization theo loại định dạng.

Không dựa vào phần mở rộng `.txt`, `.png` hoặc header `image/png` do client gửi để kết luận file không thể thực thi. Browser có thể xử lý file theo response header, nội dung thực và ngữ cảnh mở.

## 8. Upload validation: không tin MIME type từ client

Trong multipart upload, browser thường gửi `Content-Type` của file dựa trên hệ điều hành, phần mở rộng hoặc thông tin có sẵn. Người dùng có thể sửa request bằng DevTools hoặc công cụ HTTP. Vì vậy, giá trị này chỉ là gợi ý.

Một pipeline upload nên có các bước:

1. Xác thực người gửi và authorize hành động upload vào đúng resource/tenant.
2. Giới hạn request bytes, file count, kích thước từng file và tổng dung lượng.
3. Allowlist loại file mà nghiệp vụ thực sự cần; từ chối loại không hỗ trợ.
4. Kiểm tra phần mở rộng đã chuẩn hóa, nhưng không dùng nó làm căn cứ duy nhất.
5. Kiểm tra magic bytes/file signature và parse nội dung bằng thư viện phù hợp.
6. Với ảnh, decode rồi encode lại khi phù hợp; loại bỏ metadata không cần thiết.
7. Quét malware hoặc dùng content disarm/reconstruction cho loại file cần thiết.
8. Lưu vào quarantine/storage key do server tạo; không dùng filename làm path.
9. Chỉ publish sau khi kiểm tra hoàn tất; phục vụ từ origin riêng hoặc dưới dạng attachment.
10. Ghi metadata đã xác minh và MIME type do server quyết định.

### 8.1. Vì sao kiểm tra magic bytes vẫn chưa đủ?

Magic bytes có thể giúp nhận diện định dạng, nhưng không xác minh toàn bộ cấu trúc file, không bảo đảm parser an toàn và không phát hiện mọi file polyglot. Một số định dạng có nhiều biến thể hoặc không có signature cố định. Vì vậy, hãy kết hợp signature với parser chuyên dụng, giới hạn tài nguyên và kiểm tra nội dung.

Không tự viết parser định dạng phức tạp chỉ để xác định MIME. Dùng thư viện được duy trì, cập nhật bảo mật và chạy trong worker cô lập với giới hạn CPU, RAM, thời gian cùng dung lượng.

### 8.2. Tên file không quyết định media type

Phần mở rộng có ích cho UX và gợi ý ứng dụng mở file, nhưng không phải bằng chứng định dạng. `report.pdf` có thể chứa byte HTML; `avatar.jpg` có thể không phải JPEG. Server nên lưu storage key ngẫu nhiên và metadata MIME type đã xác minh riêng. Tên download có thể được chuẩn hóa độc lập với storage key.

## 9. Phục vụ download với MIME type an toàn

Khi phục vụ file, server cần quyết định browser nên hiển thị inline hay tải xuống. Ví dụ file nhị phân không tin cậy:

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="upload.bin"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

`application/octet-stream` là type tổng quát cho dữ liệu nhị phân và thường được dùng cùng `attachment`. Tuy nhiên, nó không bảo đảm browser hoặc hệ điều hành không mở file sau khi người dùng chủ động chọn. `nosniff` cũng không thay thế scan, sandbox hoặc tách origin.

Với file đã xác minh và cần hiển thị inline, dùng media type đúng, ví dụ `image/png` cho PNG. Với HTML/SVG không tin cậy, tránh inline trong origin chính. Nếu sản phẩm cần preview, dùng origin riêng không chia sẻ cookie, sandbox iframe và CSP chặt.

### 9.1. Ví dụ Express

Ví dụ phục vụ JSON API:

```js
app.get("/api/profile", authenticateSession, (req, res) => {
  res.set({
    "Content-Type": "application/json; charset=utf-8",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store"
  });

  res.json({ displayName: req.user.displayName });
});
```

Ví dụ download file không tin cậy:

```js
app.get("/files/:id/download", authenticateSession, async (req, res) => {
  const file = await fileRepository.findAuthorized(req.user, req.params.id);
  if (!file) return res.sendStatus(404);

  res.set({
    "Content-Type": "application/octet-stream",
    "Content-Disposition": makeSafeAttachmentHeader(file.downloadName),
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-store"
  });

  objectStorage.createReadStream(file.storageKey).pipe(res);
});
```

Đây là ví dụ minh họa; `authenticateSession`, `findAuthorized`, `makeSafeAttachmentHeader` và `objectStorage` cần được triển khai an toàn. Phải xử lý stream error, client abort, file size limit và quyền trên tenant/resource. Không nối trực tiếp tên file chưa kiểm tra vào `Content-Disposition`.

## 10. Blob, File và Data URL trong browser

JavaScript có thể tạo Blob với một `type`:

```js
const blob = new Blob(["hello"], {
  type: "text/plain"
});
```

Thuộc tính `blob.type` là metadata mà code cung cấp; browser không nhất thiết kiểm tra byte có đúng là text/plain hay không. Tương tự, `File.type` có thể rỗng hoặc được suy đoán từ phần mở rộng ở một số môi trường. Không dùng các thuộc tính này làm bằng chứng file upload an toàn.

Data URL có thể nhúng media type trực tiếp:

```text
data:text/plain;charset=utf-8,Hello
data:image/png;base64,iVBORw0KGgo...
```

Data URL do ứng dụng tạo từ nội dung không tin cậy cần được đánh giá theo loại media type và ngữ cảnh. Không đưa HTML hoặc SVG không tin cậy vào `iframe`, `object`, `embed` hoặc navigation chỉ vì URL bắt đầu bằng `data:`. CSP có thể hạn chế một số scheme trong các directive tương ứng; hãy cấu hình theo nhu cầu thay vì cho phép `data:` rộng rãi trong `script-src` hoặc `object-src`.

Khi tạo Object URL từ Blob, revoke URL khi không còn cần thiết để giải phóng tài nguyên. Revoke không làm thay đổi hoặc xác minh nội dung Blob.

## 11. MIME type, CORS và các chính sách cross-origin

CORS không phải cơ chế xác minh MIME type. CORS quyết định JavaScript từ origin nào được phép đọc response cross-origin. MIME type mô tả dữ liệu và có thể ảnh hưởng cách browser xử lý response theo destination.

Ví dụ một Fetch cross-origin:

```js
const response = await fetch("https://api.example.net/data", {
  mode: "cors",
  headers: { Accept: "application/json" }
});

const data = await response.json();
```

API cần trả CORS header phù hợp và `Content-Type: application/json`. Nếu API trả HTML lỗi nhưng client cố parse JSON, `response.json()` sẽ báo lỗi; client không nên đoán hoặc render HTML đó như nội dung tin cậy.

Với `mode: "no-cors"`, JavaScript nhận opaque response và không thể đọc status, header hoặc body theo cách thông thường. Không dùng `no-cors` như cách vượt CORS hoặc kiểm tra MIME type. Nếu browser tải script/style cross-origin, các quy tắc MIME và `nosniff` vẫn có thể ảnh hưởng việc sử dụng response theo destination.

Một response có `Access-Control-Allow-Origin: *` không trở nên an toàn chỉ vì có MIME type đúng. Ngược lại, `Content-Type: application/json` không tự cấp quyền đọc cross-origin. Hãy cấu hình CORS, MIME type, CSP và authorization như các lớp độc lập.

## 12. Kiểm thử MIME type bằng DevTools

Tạo các endpoint lab trả về nội dung giả, không chứa mã độc hoặc dữ liệu nhạy cảm. Dùng các trường hợp header đúng, sai và thiếu.

| Kịch bản | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| HTML đúng type | Trả HTML với `Content-Type: text/html; charset=utf-8`. | Browser parse thành document theo dự kiến. |
| JSON đúng type | Trả JSON với `application/json`. | Fetch `response.json()` parse thành công. |
| JSON sai type | Trả cùng body JSON dưới `text/html`. | Client không nên dựa vào type sai; parser và browser có thể xử lý khác theo context. |
| Script sai MIME với nosniff | Trả script body dưới `text/plain` và có `X-Content-Type-Options: nosniff`. | Browser chặn sử dụng response trong script destination theo quy tắc nosniff. |
| Stylesheet sai MIME với nosniff | Trả CSS dưới type không phù hợp. | Browser chặn stylesheet theo quy tắc nosniff áp dụng. |
| Upload Content-Type giả | Gửi file text với part header `image/png`. | Server phát hiện mismatch qua kiểm tra nội dung/parser và không tin header client. |
| Extension không khớp byte | Đặt tên file `.jpg` nhưng nội dung là text fixture. | Server xác định loại từ nội dung/validation và lưu metadata đã xác minh. |
| SVG upload | Upload SVG fixture chứa nội dung không tin cậy. | File không được inline trong origin ứng dụng; preview dùng sandbox/origin riêng. |
| Multipart boundary | Upload bằng FormData không tự đặt Content-Type. | Browser tự sinh boundary đúng; server parse được các part. |
| CDN sửa header | So sánh response từ origin và response qua CDN. | `Content-Type` và `nosniff` nhất quán; không có rule edge ghi đè ngoài dự kiến. |

### 12.1. Quan sát Network panel

Trong DevTools:

1. Chọn request và kiểm tra `Content-Type`, `Content-Encoding`, `Content-Disposition` và `X-Content-Type-Options` ở response headers.
2. Kiểm tra request `Accept` để hiểu client mong đợi representation nào.
3. Xem Preview/Response để đối chiếu nội dung với media type được khai báo.
4. Với upload, kiểm tra request payload và `Content-Type` của từng multipart part.
5. Quan sát Console để tìm lỗi MIME mismatch hoặc thông báo chặn script/style do `nosniff`.
6. So sánh header ở origin và CDN/reverse proxy để phát hiện thay đổi trên đường đi.

DevTools Preview chỉ là cách hiển thị của công cụ, không phải bằng chứng browser sẽ xử lý response giống hệt trong mọi context. Hãy thử đúng destination: document navigation, script, stylesheet, image hoặc download.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng phần mở rộng làm bằng chứng MIME | File có thể mang nội dung khác với tên. | Kiểm tra signature, parse nội dung và lưu MIME type do server xác minh. |
| Tin `Content-Type` do client gửi | Attacker có thể khai báo file nguy hiểm là ảnh hoặc tài liệu. | Xem header upload là dữ liệu không tin cậy; validate nhiều lớp. |
| Không gửi `X-Content-Type-Options: nosniff` | Một số ngữ cảnh có thể sniff và xử lý nội dung khác dự kiến. | Gửi `nosniff` và trả MIME type chính xác. |
| Nghĩ `nosniff` chặn mọi cách thực thi file | Document navigation hoặc ứng dụng mở file vẫn có thể diễn giải nội dung theo ngữ cảnh. | Tách origin, attachment, sandbox, CSP và validation. |
| Phục vụ SVG/HTML upload từ origin chính | Nội dung chủ động có thể chạy trong origin có session/quyền ứng dụng. | Phục vụ từ origin riêng, dùng attachment hoặc sandbox preview. |
| Đặt `Content-Type: gzip` cho JSON nén | Client hiểu sai media type và không giải mã representation đúng. | Dùng `Content-Type: application/json` cùng `Content-Encoding: gzip`. |
| Tự đặt multipart Content-Type khi dùng FormData | Boundary có thể thiếu hoặc không khớp body. | Để browser tự tạo header và boundary. |
| Coi Blob.type hoặc File.type là kết quả kiểm tra file | Metadata có thể do code hoặc hệ thống client suy đoán. | Xác minh byte và parse file ở server. |
| Dùng CORS để xử lý MIME mismatch | CORS không xác minh định dạng hoặc ngăn MIME confusion. | Cấu hình riêng CORS, Content-Type và nosniff. |

## 14. Bài thực hành

Xây dựng một API nhỏ có endpoint JSON, endpoint trả HTML, endpoint upload và endpoint download trong môi trường local/staging.

1. Trả JSON bằng `application/json` và `X-Content-Type-Options: nosniff`; kiểm tra bằng Fetch.
2. Tạo một response script và stylesheet thử nghiệm với MIME type đúng, sau đó cố ý đổi type để quan sát `nosniff`.
3. Upload một file fixture có header multipart `image/png` nhưng nội dung là text; xác nhận server không tin MIME do client khai báo.
4. Kiểm tra một ảnh hợp lệ bằng parser; lưu MIME type server đã xác minh thay vì dùng tên file làm căn cứ.
5. Upload SVG/HTML fixture và xác nhận chúng được phục vụ từ origin riêng hoặc dưới dạng attachment, không inline trong ứng dụng chính.
6. Dùng FormData và để browser tạo multipart boundary; quan sát request headers.
7. Thêm CDN/reverse proxy test hoặc mock để xác nhận `Content-Type` và `nosniff` không bị ghi đè.
8. Kiểm tra CSP, CORS và `Content-Disposition` theo từng endpoint.
9. Ghi lại MIME type mong đợi, MIME type thực tế, loại parser và quyết định accept/reject cho từng fixture.

Hoàn thành bài thực hành khi bạn chứng minh được header MIME type khớp nội dung, browser xử lý đúng theo destination, upload không tin Content-Type từ client và nội dung HTML/SVG không tin cậy không được chạy trong origin ứng dụng.
