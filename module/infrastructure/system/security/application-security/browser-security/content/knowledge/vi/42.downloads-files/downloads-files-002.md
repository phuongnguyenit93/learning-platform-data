# Content-Disposition: điều khiển cách trình duyệt xử lý file tải về

`Content-Disposition` là HTTP response header cho biết nội dung được trình duyệt xử lý theo kiểu hiển thị trực tiếp hay tải xuống như một tệp đính kèm. Header này cũng có thể đề xuất tên file cho thao tác lưu.

Một response tải file thường kết hợp `Content-Disposition`, `Content-Type` và các header cache/security phù hợp. `Content-Disposition: attachment` không tự xác thực người dùng, không làm sạch file, không bảo đảm nội dung an toàn và không thay thế kiểm soát quyền truy cập ở server.

Bài học tập trung vào cách chọn `inline` hoặc `attachment`, truyền tên file tương thích Unicode bằng `filename` và `filename*`, xử lý tên file không tin cậy, ngăn header injection, xác định MIME type và phục vụ file an toàn qua ứng dụng web.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của `Content-Disposition` trong HTTP response.
- Phân biệt `inline` và `attachment`.
- Hiểu `filename` và `filename*` theo RFC 6266 và RFC 8187.
- Tạo tên file Unicode có fallback ASCII tương thích browser cũ.
- Hiểu vì sao filename chỉ là gợi ý, không phải đường dẫn lưu file đáng tin cậy.
- Làm sạch tên file, phần mở rộng và dữ liệu do người dùng cung cấp.
- Ngăn CRLF/header injection và parameter ambiguity.
- Kết hợp Content-Disposition với Content-Type và X-Content-Type-Options.
- Bảo vệ file tải về bằng authentication, authorization, cache policy và signed URL.
- Xử lý Range request, streaming, download lớn và lỗi truyền tải.
- Phân biệt Content-Disposition của response với multipart/form-data request.
- Kiểm thử download trên nhiều browser và tình huống bảo mật.

## 1. Content-Disposition nằm ở đâu?

Khi browser gửi request tải file, server trả HTTP response. Header `Content-Disposition` mô tả cách trình duyệt nên trình bày nội dung.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Content-Length: 48291
X-Content-Type-Options: nosniff
Cache-Control: private, no-store

%PDF-1.7...
~~~

Trong ví dụ:

- `Content-Type` mô tả kiểu media của response.
- `Content-Disposition: attachment` yêu cầu browser xử lý nội dung như file tải về.
- `filename="report.pdf"` là tên file được đề xuất.
- `Content-Length` cho biết kích thước response nếu server biết trước.
- `X-Content-Type-Options: nosniff` giúp ngăn một số kiểu MIME sniffing.
- `Cache-Control: private, no-store` hạn chế lưu response nhạy cảm vào cache.

Header này thuộc response. Nó không phải một lệnh JavaScript và cũng không cấp quyền tải file. Server vẫn phải xác thực và kiểm tra quyền trước khi trả nội dung.

### 1.1 Hai disposition type thường gặp

| Giá trị | Hành vi dự kiến | Ví dụ |
|---|---|---|
| `inline` | Browser có thể hiển thị nội dung nếu hỗ trợ MIME type | PDF hoặc ảnh |
| `attachment` | Browser đề nghị tải nội dung thành file | PDF, CSV, ZIP |

Ví dụ hiển thị PDF:

~~~http
Content-Type: application/pdf
Content-Disposition: inline
~~~

Ví dụ tải PDF:

~~~http
Content-Type: application/pdf
Content-Disposition: attachment
~~~

Nếu bỏ `Content-Disposition`, browser quyết định cách xử lý theo MIME type, cấu hình người dùng và chính sách của trình duyệt. Đặt `inline` cũng không buộc browser phải hiển thị nếu browser không hỗ trợ loại nội dung đó hoặc người dùng đã cấu hình tải xuống.

### 1.2 attachment không phải một sandbox

`attachment` là hướng dẫn trình bày response. Nó không biến nội dung độc hại thành an toàn.

Một file HTML, SVG hoặc tài liệu có nội dung active vẫn có thể nguy hiểm khi người dùng mở bằng ứng dụng phù hợp. Nếu phục vụ file do người dùng tải lên, hãy cân nhắc lưu trữ và tải xuống từ một origin riêng biệt, không dùng chung cookie xác thực với ứng dụng chính.

## 2. Cấu trúc Content-Disposition

RFC 6266 định nghĩa `Content-Disposition` cho HTTP response. Cấu trúc khái quát:

~~~http
Content-Disposition: disposition-type; parameter=value
~~~

Các phần thường dùng:

- Disposition type: `inline`, `attachment` hoặc một token mở rộng.
- `filename`: tên file dạng quoted-string hoặc token theo cú pháp HTTP.
- `filename*`: tên file mở rộng có charset và percent-encoded octets.

Ví dụ:

~~~http
Content-Disposition: attachment; filename="report.pdf"
~~~

Có thể có các parameter mở rộng khác theo ứng dụng, nhưng không nên tự tạo parameter trùng tên hoặc dựa vào cách browser xử lý header mơ hồ.

### 2.1 filename là tên gợi ý

`filename` không phải đường dẫn file trên server. Nó chỉ là tên gợi ý để browser hiển thị trong hộp thoại tải xuống hoặc dùng làm tên mặc định.

Không gửi đường dẫn tuyệt đối như:

~~~http
Content-Disposition: attachment; filename="/var/private/reports/secret.pdf"
~~~

Không gửi path traversal như:

~~~http
Content-Disposition: attachment; filename="../../../../etc/passwd"
~~~

Browser hiện đại thường loại bỏ thành phần path khi diễn giải filename, nhưng server vẫn phải tự làm sạch tên. Không dựa vào browser để ngăn path traversal trong ứng dụng hoặc hệ thống lưu trữ.

### 2.2 filename và filename* khác nhau

`filename` là dạng tương thích rộng, thường dùng ASCII để giảm khác biệt giữa các browser cũ.

`filename*` hỗ trợ encoding theo extended parameter syntax, cho phép tên Unicode. RFC 6266 sử dụng cơ chế được định nghĩa trong RFC 5987; RFC 8187 cập nhật cơ chế extended HTTP parameter encoding.

Ví dụ:

~~~http
Content-Disposition: attachment; filename="bao-cao.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o.pdf
~~~

Browser hiểu `filename*` thường ưu tiên giá trị đó khi cả hai cùng xuất hiện. `filename` là fallback cho client không hiểu extended parameter.

### 2.3 Quy tắc gửi cả hai

Khi tên file có Unicode, nên gửi:

1. `filename` với fallback ASCII an toàn.
2. `filename*` với UTF-8 percent-encoded.

Ví dụ:

~~~http
Content-Disposition: attachment; filename="bao-cao-2026.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o-2026.pdf
~~~

Không đặt cùng một parameter nhiều lần:

~~~http
Content-Disposition: attachment; filename="a.pdf"; filename="b.pdf"
~~~

RFC 6266 yêu cầu sender không tạo nhiều instance cùng tên parameter trong một field value. Duplicate parameters làm kết quả parsing không nhất quán và có thể tạo khác biệt giữa proxy, library và browser.

## 3. filename* và Unicode

Extended parameter có dạng:

~~~text
charset'language'percent-encoded-value
~~~

Ví dụ:

~~~text
UTF-8''b%C3%A1o-c%C3%A1o.pdf
~~~

- `UTF-8` là charset.
- Phần giữa hai dấu nháy đơn là language tag; có thể để trống.
- Phần cuối là octet UTF-8 được percent-encode.

### 3.1 Percent-encode theo byte UTF-8

Không encode từng ký tự Unicode theo code point rồi ghép tùy tiện. Hãy chuyển chuỗi thành byte UTF-8, sau đó percent-encode các byte theo extended parameter syntax.

Dấu cộng `+` không phải cách biểu diễn space tương đương trong mọi ngữ cảnh. Dùng percent-encoding đúng chuẩn cho `filename*`.

### 3.2 Fallback ASCII

Tên tiếng Việt:

~~~text
báo cáo quý 4.pdf
~~~

Có thể gửi fallback:

~~~http
filename="bao-cao-quy-4.pdf"
~~~

và tên Unicode:

~~~http
filename*=UTF-8''b%C3%A1o%20c%C3%A1o%20qu%C3%BD%204.pdf
~~~

Fallback không cần giữ nguyên toàn bộ dấu tiếng Việt. Nó cần an toàn, dễ hiểu và có phần mở rộng phù hợp.

### 3.3 Không double-encode

Nếu tên Unicode đã được percent-encode, không encode dấu `%` thêm lần nữa. Double encoding có thể khiến browser hiện `%C3%A1` trong tên file thay vì ký tự Unicode mong muốn.

Dùng thư viện HTTP header đã được kiểm thử thay vì tự xây chuỗi extended parameter.

## 4. Tên file không tin cậy và sanitization

Tên file có thể đến từ:

- Người dùng upload.
- Tên object trong storage.
- Tên báo cáo do người dùng đặt.
- Metadata từ hệ thống bên ngoài.
- Tên file trong database cũ.

Không đưa trực tiếp giá trị này vào response header.

### 4.1 Path separator và traversal

Loại bỏ hoặc thay thế:

- `/` và `\`.
- Các segment `.` hoặc `..`.
- Ký tự điều khiển.
- Null byte và ký tự không hợp lệ theo nền tảng.
- Tên rỗng hoặc chỉ chứa dấu chấm/khoảng trắng.

Ví dụ tên upload nguy hiểm:

~~~text
../../../../startup.sh
..\..\private\credentials.txt
~~~

Tên tải về nên là basename đã chuẩn hóa, ví dụ:

~~~text
startup-report.txt
credentials-export.txt
~~~

Không dùng filename hiển thị làm đường dẫn để mở file trên server. Hãy lấy object bằng ID đã xác thực hoặc key storage do server quản lý.

### 4.2 CRLF và header injection

HTTP header được phân tách bằng CRLF. Nếu filename chứa carriage return hoặc line feed và server ghép chuỗi header không an toàn, attacker có thể cố tạo header mới hoặc làm hỏng response.

Dữ liệu nguy hiểm:

~~~text
report.pdf\r\nSet-Cookie: attacker=value
~~~

Không tự nối filename vào chuỗi header. Dùng API response header của framework hoặc thư viện Content-Disposition đã xử lý quoting/encoding.

Server phải từ chối CR (`\r`), LF (`\n`), NUL và control characters trong filename trước khi tạo header. Framework hiện đại thường từ chối CR/LF, nhưng không được dựa hoàn toàn vào hành vi ngầm của framework.

### 4.3 Unicode bidi và tên gây nhầm lẫn

Một số Unicode control characters có thể đảo thứ tự hiển thị, khiến phần mở rộng trông khác với phần mở rộng thực.

Ví dụ, tên file có thể hiển thị giống `invoice.pdf` nhưng phần mở rộng thực bị che bởi bidi control. Hãy cân nhắc loại bỏ control characters không cần thiết, chuẩn hóa Unicode và hiển thị extension rõ ràng.

Không tự động bỏ mọi ký tự Unicode hợp lệ. Hãy có policy cho tên hiển thị và fallback ASCII.

### 4.4 Phần mở rộng phải khớp nội dung

Không tin extension do người dùng cung cấp. Nếu nội dung là PDF, không đặt tên thành `.html` hoặc `.exe` để gây nhầm lẫn.

- Kiểm tra MIME và định dạng bằng server-side validation.
- Dùng allowlist extension theo loại file.
- Tạo extension từ loại nội dung đã xác minh.
- Không cho phép tên kép gây đánh lừa như `report.pdf.exe`.
- Không dùng extension để thay thế malware scanning hoặc content validation.

### 4.5 Tên file không phải object identifier

Một thiết kế an toàn tách:

- Object ID/storage key: do server tạo, dùng để truy xuất file.
- Display filename: tên đã làm sạch, chỉ dùng hiển thị cho người tải.

Không ghép display filename vào filesystem path hoặc SQL query.

## 5. Content-Disposition kết hợp Content-Type

Hai header có vai trò khác nhau:

| Header | Câu hỏi được trả lời |
|---|---|
| `Content-Type` | Nội dung thuộc kiểu media nào? |
| `Content-Disposition` | Browser nên hiển thị hay tải về, tên file gợi ý là gì? |
| `X-Content-Type-Options` | Có cho phép một số hành vi MIME sniffing hay không? |

Ví dụ PDF tải xuống:

~~~http
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
X-Content-Type-Options: nosniff
~~~

Ví dụ CSV:

~~~http
Content-Type: text/csv; charset=utf-8
Content-Disposition: attachment; filename="users.csv"
X-Content-Type-Options: nosniff
~~~

### 5.1 MIME type phải phản ánh nội dung

Không tin `Content-Type` do browser upload gửi lên. Client có thể khai báo file bất kỳ là `image/png` hoặc `application/pdf`.

Server nên xác minh loại file bằng signature/magic bytes và parser phù hợp, kết hợp allowlist theo use case. Một số định dạng phức tạp cần scan hoặc chuyển đổi trước khi phục vụ.

### 5.2 application/octet-stream

Với file nhị phân không xác định hoặc nội dung không muốn browser cố hiển thị, server có thể dùng:

~~~http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="download.bin"
X-Content-Type-Options: nosniff
~~~

Không dùng `application/octet-stream` cho mọi file nếu sản phẩm cần MIME chính xác, preview hoặc xử lý theo định dạng. Chọn type dựa trên nội dung đã xác minh và chính sách phục vụ.

### 5.3 nosniff không thay thế kiểm tra file

`X-Content-Type-Options: nosniff` giúp browser không tự đoán MIME trong các ngữ cảnh mà chuẩn áp dụng, đặc biệt là script và stylesheet. Nó không phải malware scanner và không bảo đảm mọi loại file đều an toàn khi người dùng mở.

Nếu file HTML/SVG do người dùng upload, hãy phục vụ từ origin tách biệt và cân nhắc CSP sandbox cùng chính sách tải xuống phù hợp.

## 6. inline, attachment và nội dung active

`inline` phù hợp khi ứng dụng chủ động muốn browser render một định dạng hỗ trợ, chẳng hạn PDF hoặc ảnh. Chỉ dùng cho nội dung đã được xác minh và được phép hiển thị trong origin hiện tại.

`attachment` phù hợp khi người dùng cần lưu file. Nhưng nếu browser hoặc hệ điều hành mở file sau khi tải, nội dung vẫn có thể thực thi theo loại file và ứng dụng liên quan.

### 6.1 File do người dùng upload

Các file như HTML, SVG, XML hoặc một số định dạng tài liệu có thể chứa nội dung active hoặc tham chiếu tài nguyên bên ngoài.

Với file không tin cậy:

- Không render trực tiếp trong origin ứng dụng có session cookie.
- Dùng origin riêng cho nội dung upload/download.
- Không chia sẻ cookie domain với ứng dụng chính.
- Áp dụng `Content-Disposition: attachment` khi phù hợp.
- Đặt MIME type chính xác hoặc `application/octet-stream` cho file không xác định.
- Dùng `X-Content-Type-Options: nosniff`.
- Cân nhắc CSP sandbox cho nội dung được render trong môi trường cách ly.
- Scan, validate hoặc chuyển đổi file theo loại nội dung.

### 6.2 Origin riêng cho file

Một subdomain riêng chỉ thực sự cách ly tốt nếu cookie của ứng dụng không được đặt với Domain rộng như `.example.test`. Nếu cookie domain dùng chung, subdomain file có thể nhận cookie đó.

Với file không tin cậy, cân nhắc một registrable domain khác, không có credential ứng dụng, không có quyền CORS credential và không tải script từ ứng dụng chính.

### 6.3 CSP sandbox

Nếu phải render nội dung không tin cậy trong browser, một response có thể dùng CSP sandbox theo threat model, ví dụ:

~~~http
Content-Security-Policy: sandbox; default-src 'none'
~~~

CSP sandbox áp dụng hạn chế cho document được trả về. Cần kiểm thử các tính năng sản phẩm cần thiết và tránh thêm ngoại lệ sandbox tùy tiện.

## 7. Header Content-Disposition trong server

Dùng API của framework hoặc thư viện có hỗ trợ RFC 6266/8187. Không tự nối tên file do người dùng cung cấp vào header.

### 7.1 Node.js với thư viện content-disposition

Ví dụ dùng package `content-disposition` để tạo header:

~~~js
import contentDisposition from "content-disposition";

async function downloadReport(req, res) {
  const report = await loadReportById(req.params.id);

  if (!report || !canDownload(req.user, report)) {
    res.sendStatus(404);
    return;
  }

  const displayName = makeSafeDisplayName(report.displayName, "report.pdf");

  res.setHeader("Content-Type", "application/pdf");
  res.setHeader(
    "Content-Disposition",
    contentDisposition(displayName, { type: "attachment" })
  );
  res.setHeader("X-Content-Type-Options", "nosniff");
  res.setHeader("Cache-Control", "private, no-store");

  report.stream.pipe(res);
}
~~~

Ví dụ giả định `loadReportById` trả về file đã được xác định từ storage và `canDownload` kiểm tra quyền ở server. `makeSafeDisplayName` phải chuẩn hóa tên hiển thị và không dùng tên đó để truy cập storage.

Package cần được thêm và cập nhật theo dependency policy của dự án. API của thư viện giúp xử lý quoting và extended filename; vẫn phải validate dữ liệu nghiệp vụ và test header được sinh ra.

### 7.2 Dùng helper có sẵn của framework

Một số framework có helper như `res.download(path, filename)` hoặc API tương tự. Helper thường xử lý Content-Disposition và stream file.

Trước khi dùng, kiểm tra:

- Helper có hỗ trợ Unicode `filename*` không.
- Tên file có được quote/escape đúng không.
- CRLF/control characters có bị từ chối không.
- Có thể đặt Content-Type và cache/security headers không.
- Quyền truy cập được kiểm tra trước khi stream không.
- Lỗi xảy ra sau khi response bắt đầu được xử lý thế nào.

Không giả định helper tự xác thực user hoặc tự ngăn path traversal.

### 7.3 Không dùng filename làm filesystem path

Mẫu không an toàn:

~~~js
const path = "/uploads/" + req.query.filename;
res.download(path);
~~~

Attacker có thể thử path traversal hoặc truy cập file không thuộc quyền của họ.

Mẫu an toàn hơn:

~~~js
async function openAuthorizedDownload(req, res) {
  const fileRecord = await repository.findById(req.params.fileId);

  if (!fileRecord || !canDownload(req.user, fileRecord)) {
    return res.sendStatus(404);
  }

  const stream = await storage.openReadStream(fileRecord.storageKey);
  return stream.pipe(res);
}
~~~

`storageKey` phải do server quản lý, không phải đường dẫn do client gửi.

## 8. Authentication và authorization trước khi tải

Content-Disposition không phải access control. Bất kỳ ai biết URL tải xuống cũng không nên mặc định có quyền lấy file.

Trước khi stream:

1. Xác thực session hoặc credential.
2. Tìm file theo ID/key đã kiểm soát.
3. Kiểm tra user có quyền đọc file trong tenant/project tương ứng.
4. Kiểm tra trạng thái file, retention và policy tải.
5. Ghi audit event tối thiểu nếu nghiệp vụ yêu cầu.
6. Chỉ sau đó mới mở stream.

### 8.1 Tránh IDOR

Không cho phép người dùng tải file của người khác chỉ bằng cách đổi `fileId` trong URL.

Quyền cần được kiểm tra cho từng object, không chỉ kiểm tra user đã đăng nhập.

### 8.2 Không để response lỗi tiết lộ file

Khi file không tồn tại hoặc user không có quyền, cân nhắc response thống nhất để tránh enumeration. Không trả storage path, tên nội bộ hoặc metadata nhạy cảm trong error response.

### 8.3 Signed download URL

Signed URL có thể hữu ích cho CDN/object storage, nhưng bản thân URL thường là bearer capability: ai có URL đều có thể tải trong thời hạn và phạm vi đã ký.

Nếu dùng:

- Lifetime ngắn và chỉ áp dụng cho một object.
- Ràng buộc method và response headers nếu provider hỗ trợ.
- Không ký quyền rộng hơn cần thiết.
- Không ghi full signed URL vào log hoặc analytics.
- Dùng Referrer-Policy chặt chẽ cho trang tạo link.
- Không đặt link trong public page hoặc third-party telemetry.
- Có cơ chế revoke/rotate nếu provider hỗ trợ.

Không xem signed URL là dữ liệu công khai chỉ vì nó không chứa access token theo tên gọi.

## 9. Cache và dữ liệu nhạy cảm

File có thể chứa báo cáo tài chính, hồ sơ người dùng hoặc dữ liệu nội bộ. Chọn cache policy theo độ nhạy.

### 9.1 private, no-store

Với file nhạy cảm:

~~~http
Cache-Control: private, no-store
~~~

- `private` ngăn shared cache lưu response theo ngữ nghĩa cache.
- `no-store` yêu cầu cache không lưu response.

Không ghi credential hoặc nội dung nhạy cảm vào CDN cache chỉ vì URL có vẻ khó đoán.

### 9.2 File công khai có thể cache

Với file public, versioned và không chứa dữ liệu người dùng:

~~~http
Cache-Control: public, max-age=31536000, immutable
ETag: "sha256-content-version"
~~~

Chỉ dùng cache dài hạn khi nội dung thực sự public và URL thay đổi khi nội dung thay đổi. Không áp dụng policy này cho file riêng tư hoặc URL có signed token mà chưa đánh giá cache key và CDN behavior.

### 9.3 Content-Disposition và cache key

`Content-Disposition` có thể thay đổi filename mà không thay đổi bytes. Nếu CDN cache response theo URL, cần hiểu cache có lưu header nào và có thể phục vụ filename sai giữa người dùng hay không.

Không cache chung response riêng tư chỉ vì nội dung giống nhau. Cấu hình cache key và authorization phải bảo đảm không rò rỉ dữ liệu giữa user/tenant.

## 10. Range request và file lớn

Browser hoặc download manager có thể gửi Range request để tiếp tục tải hoặc lấy một phần nội dung.

Ví dụ:

~~~http
GET /files/123 HTTP/1.1
Range: bytes=0-999
~~~

Server có thể trả:

~~~http
HTTP/1.1 206 Partial Content
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Accept-Ranges: bytes
Content-Range: bytes 0-999/48291
Content-Length: 1000
~~~

### 10.1 Range và authorization

Mỗi request Range vẫn phải qua authentication/authorization. Không giả định request đầu tiên đã xác thực thì mọi request tiếp theo đều được phép.

Nếu dùng signed URL, thời hạn phải đủ cho việc tải theo thiết kế nhưng vẫn giới hạn rủi ro. Không tạo signed URL vô thời hạn chỉ để hỗ trợ resume.

### 10.2 Content-Length và streaming

Nếu server biết kích thước, có thể gửi Content-Length chính xác. Với streaming hoặc nội dung được nén/chuyển đổi động, không tự đặt length sai.

Khi stream lỗi sau khi header đã gửi, server không thể đổi response thành JSON 500 một cách đáng tin cậy. Hãy log lỗi an toàn, đóng stream và cho client biết tải chưa hoàn tất qua kết quả kết nối.

### 10.3 Range không phải một cách bypass

Không cho phép Range request bỏ qua quyền hoặc trả byte ngoài phạm vi file. Kiểm tra parser Range, giới hạn số range nếu cần và trả 416 khi range không hợp lệ theo protocol.

## 11. Cross-origin download và HTML download attribute

HTML có thuộc tính `download`:

~~~html
<a href="/files/123" download="report.pdf">Tải báo cáo</a>
~~~

Thuộc tính này là gợi ý phía browser. Hành vi phụ thuộc origin, browser và response header. Với cross-origin URL, browser có thể không tôn trọng thuộc tính download như mong đợi; response server với `Content-Disposition: attachment` là cơ chế quan trọng hơn.

### 11.1 CORS không phải quyền tải file

Điều hướng người dùng đến URL tải xuống và JavaScript dùng `fetch()` để đọc response là hai trường hợp khác nhau.

- Navigation/download không nhất thiết cần CORS để browser tải file.
- JavaScript đọc response cross-origin bằng Fetch/XHR cần CORS phù hợp.
- CORS không thay thế authentication/authorization.
- `Access-Control-Expose-Headers: Content-Disposition` có thể cần nếu JavaScript cần đọc header này từ response cross-origin đã được CORS cho phép.

Không mở CORS credentials cho mọi origin chỉ để JavaScript tải file.

### 11.2 Fetch rồi tạo Blob URL

Ứng dụng có thể fetch file, đọc blob rồi tạo object URL:

~~~js
const response = await fetch("/api/files/123", {
  credentials: "same-origin"
});

if (!response.ok) {
  throw new Error("Download failed");
}

const blob = await response.blob();
const objectUrl = URL.createObjectURL(blob);

const link = document.createElement("a");
link.href = objectUrl;
link.download = "report.pdf";
document.body.append(link);
link.click();
link.remove();

window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
~~~

Ví dụ trì hoãn revoke để browser có thời gian bắt đầu tải; thời gian cụ thể cần được kiểm thử trên browser mục tiêu và có thể được quản lý theo vòng đời UI. `download` ở đây đặt tên phía client, nhưng server vẫn cần gửi Content-Type chính xác và kiểm soát quyền.

Đối với file lớn, `response.blob()` có thể giữ toàn bộ nội dung trong memory. Ưu tiên navigation trực tiếp hoặc streaming phù hợp khi dung lượng lớn.

## 12. Content-Disposition trong multipart/form-data

Không nhầm response header tải file với `Content-Disposition` trong body `multipart/form-data` của upload request.

Ví dụ multipart:

~~~http
Content-Disposition: form-data; name="file"; filename="photo.png"
Content-Type: image/png
~~~

Ở đây:

- `form-data` xác định một form part.
- `name` là tên field.
- `filename` là tên do client khai báo cho file upload.

Filename trong multipart là dữ liệu không tin cậy. Không dùng nó làm storage path và không tin MIME type do client khai báo.

Response tải file thường có dạng:

~~~http
Content-Disposition: attachment; filename="photo.png"
~~~

Hai trường hợp dùng cùng header name nhưng nằm ở vị trí và mục đích khác nhau.

## 13. Kiểm thử Content-Disposition

Dùng file lab do bạn kiểm soát. Không thử download file nhạy cảm của người khác.

### 13.1 Kiểm tra response headers

Dùng curl:

~~~bash
curl -sS -D - -o /dev/null https://app.example.test/files/123
~~~

Kiểm tra:

- Status code.
- Content-Type.
- Content-Disposition.
- X-Content-Type-Options.
- Cache-Control.
- Content-Length hoặc Content-Range.

Không đưa bearer token thật vào command line hoặc shell history. Dùng môi trường test và credential tạm thời.

### 13.2 Kiểm tra tên Unicode

Tạo file có tên:

~~~text
báo cáo quý 4.pdf
~~~

Xác nhận response có fallback ASCII và `filename*` UTF-8. Thử Chrome, Firefox, Safari và các browser mục tiêu để kiểm tra tên lưu thực tế.

### 13.3 Kiểm tra filename độc hại

Thử các input lab:

- `../../secret.txt`
- `..\..\secret.txt`
- Tên có CR/LF.
- Tên có NUL/control character.
- Tên có dấu nháy và dấu chấm phẩy.
- Tên có Unicode bidi control.
- Tên rỗng hoặc chỉ có khoảng trắng.

Server phải từ chối hoặc chuyển thành display name an toàn; không để input tạo thêm response header hoặc ảnh hưởng storage path.

### 13.4 Kiểm tra inline và attachment

Với cùng một file PDF lab:

1. Trả `Content-Disposition: inline`.
2. Trả `Content-Disposition: attachment`.
3. Quan sát hành vi browser.
4. Thử browser có PDF viewer bật/tắt.
5. Xác nhận MIME type không thay đổi ngoài ý muốn.

### 13.5 Kiểm tra file active

Upload một file HTML/SVG vô hại trong lab. Xác nhận file được phục vụ từ origin riêng, không nhận cookie ứng dụng chính, và policy tải xuống phù hợp.

Không mở payload thực thi trên máy thật. Mục tiêu là kiểm tra origin, header và cách ly.

### 13.6 Kiểm tra authorization và Range

- Tải file bằng user có quyền.
- Thử cùng file bằng user không có quyền.
- Thử đổi file ID.
- Gửi Range request.
- Xác nhận mỗi request đều được authorization.
- Kiểm tra CDN không cache response riêng tư cho user khác.

## 14. Lỗi triển khai thường gặp

### 14.1 Dùng attachment như biện pháp bảo mật duy nhất

Attachment chỉ gợi ý tải xuống. Nó không xác thực, phân quyền hoặc scan nội dung.

### 14.2 Nối filename trực tiếp vào header

Input chứa CR/LF hoặc ký tự đặc biệt có thể gây header injection hoặc header không hợp lệ. Dùng thư viện/framework và validate.

### 14.3 Chỉ gửi filename, bỏ filename*

Tên Unicode có thể bị lỗi hoặc biến thành ký tự không mong muốn trên một số client. Gửi ASCII fallback và UTF-8 `filename*`.

### 14.4 Gửi nhiều filename parameter

Duplicate parameter gây parsing ambiguity. Chỉ gửi một `filename` và một `filename*` theo pattern chuẩn.

### 14.5 Tin extension hoặc Content-Type từ upload

Attacker có thể đổi tên file hoặc MIME declaration. Xác minh nội dung và dùng policy extension/MIME phía server.

### 14.6 Dùng filename làm path

Tên file có thể chứa path traversal. Truy xuất file bằng object ID/storage key do server quản lý.

### 14.7 Cho file HTML/SVG chạy trên origin ứng dụng

Nội dung active có thể chạy trong context có cookie/session. Cách ly file trên origin riêng và áp dụng policy phù hợp.

### 14.8 Dùng no-store thay authorization

Cache-Control không kiểm tra user. Mỗi request tải file vẫn phải xác thực và phân quyền.

### 14.9 CORS wildcard để tải file

CORS không phải access control và không nên mở credentials cho mọi origin. Chỉ expose header cho origin được phép nếu ứng dụng thực sự cần.

### 14.10 Không xử lý Range và stream failure

File lớn có thể bị tải dở hoặc resume sai. Kiểm tra Range, Content-Length và lifecycle stream.

### 14.11 Tin download attribute luôn hoạt động cross-origin

Browser có thể giới hạn download attribute cho URL khác origin. Hãy cấu hình response Content-Disposition ở server.

## 15. Quy trình triển khai Content-Disposition

Trước khi đưa endpoint tải file vào production:

1. Xác thực người dùng và kiểm tra quyền với từng file.
2. Lấy file qua object ID/storage key do server quản lý.
3. Xác minh loại nội dung và chọn Content-Type phù hợp.
4. Chọn `attachment` hoặc `inline` theo use case.
5. Sinh display filename an toàn; loại path separator và control characters.
6. Dùng thư viện hỗ trợ RFC 6266/8187 để tạo `filename` và `filename*`.
7. Đặt X-Content-Type-Options: nosniff.
8. Chọn Cache-Control theo độ nhạy và phạm vi chia sẻ.
9. Cách ly file active hoặc file do người dùng upload khỏi origin ứng dụng.
10. Hỗ trợ Range/streaming nếu cần và authorization cho từng request.
11. Redact filename/path/secret khỏi log nếu chứa dữ liệu cá nhân.
12. Kiểm thử browser, Unicode, CRLF, path traversal, MIME, CORS và cache.

## 16. Checklist review Content-Disposition

- [ ] Chọn đúng `inline` hoặc `attachment`.
- [ ] Content-Disposition được đặt trên response cần thiết.
- [ ] Có `filename` fallback ASCII khi cần tương thích.
- [ ] Có `filename*` UTF-8 percent-encoded cho Unicode.
- [ ] Không tạo duplicate parameter.
- [ ] Không tự nối filename vào header.
- [ ] CR/LF, NUL và control characters bị từ chối hoặc loại bỏ.
- [ ] Path separator và `..` không đi vào tên lưu trữ.
- [ ] Filename không được dùng làm filesystem path/storage key.
- [ ] Unicode bidi/control characters được xử lý theo policy.
- [ ] Extension khớp nội dung đã xác minh.
- [ ] Content-Type được xác định phía server.
- [ ] Có X-Content-Type-Options: nosniff.
- [ ] File HTML/SVG không tin cậy được cách ly khỏi origin ứng dụng.
- [ ] Authentication và object-level authorization chạy trước khi stream.
- [ ] Signed URL có scope và lifetime giới hạn.
- [ ] Cache-Control phù hợp với dữ liệu riêng tư/công khai.
- [ ] Range request vẫn được authorization.
- [ ] Stream failure được xử lý và log an toàn.
- [ ] CORS chỉ mở cho origin cần thiết.
- [ ] Đã kiểm tra cross-origin download và browser behavior.
- [ ] Đã kiểm thử Unicode, path traversal, CRLF và MIME mismatch.

## 17. Bài thực hành

Thực hiện trên endpoint và file lab do bạn kiểm soát.

### Bài 1: Inline và attachment

Tạo endpoint trả cùng một PDF với hai disposition type. Quan sát browser render PDF hay tải file.

### Bài 2: Filename Unicode

Tạo response có fallback ASCII và `filename*` UTF-8. Kiểm tra tên file tải về trên các browser mục tiêu.

### Bài 3: Sanitization

Gửi filename có path traversal, CRLF, quote, semicolon và bidi control. Xác nhận header hợp lệ, tên hiển thị an toàn và storage path không đổi.

### Bài 4: MIME và nosniff

Upload file lab có MIME declaration không khớp nội dung. Xác nhận server dùng MIME đã kiểm tra và trả nosniff.

### Bài 5: File HTML/SVG

Phục vụ file active vô hại từ origin cách ly. Kiểm tra cookie, CSP sandbox, Content-Disposition và khả năng truy cập ứng dụng chính.

### Bài 6: Authorization và IDOR

Thử tải file bằng hai user khác nhau và thay file ID. Xác nhận server kiểm tra quyền cho từng object.

### Bài 7: Range và resume

Tạo file lớn, gửi Range request và xác nhận 206/Content-Range đúng. Thử request bằng user không có quyền.

### Bài 8: Cache và CDN

Tải file riêng tư qua CDN lab. Xác nhận response không bị cache dùng chung và không phục vụ nhầm giữa hai user.

## 18. Câu hỏi tự kiểm tra

**1. Content-Disposition có vai trò gì?**

Cho browser biết nội dung nên hiển thị hay tải xuống và cung cấp tên file gợi ý.

**2. inline và attachment khác nhau thế nào?**

Inline cho phép browser hiển thị nếu hỗ trợ; attachment yêu cầu browser xử lý như file tải về.

**3. filename và filename* khác nhau thế nào?**

`filename` là tham số tên file tương thích rộng; `filename*` hỗ trợ extended encoding như UTF-8 theo RFC 8187.

**4. Vì sao nên gửi cả filename và filename*?**

Để browser hỗ trợ extended parameter dùng tên Unicode, còn client cũ có fallback ASCII.

**5. Filename có phải đường dẫn server không?**

Không. Đây chỉ là tên gợi ý cho browser. Storage key và filesystem path phải do server quản lý.

**6. CRLF trong filename gây rủi ro gì?**

Có thể tạo header injection hoặc response header sai nếu server ghép chuỗi không an toàn.

**7. attachment có làm file an toàn không?**

Không. Nội dung vẫn có thể nguy hiểm khi người dùng mở. Cần xác minh, scan và cách ly file không tin cậy.

**8. Content-Type khác Content-Disposition thế nào?**

Content-Type mô tả định dạng media; Content-Disposition điều khiển cách trình bày và tên file gợi ý.

**9. CORS có cần cho mọi download không?**

Không. Navigation download khác với JavaScript Fetch đọc response cross-origin. CORS chỉ cần cho trường hợp script đọc response theo policy.

**10. Content-Disposition có thay authorization không?**

Không. Server phải xác thực và kiểm tra quyền trên từng file trước khi trả response.

## Ghi nhớ

Content-Disposition điều khiển cách browser trình bày response và tên file gợi ý. Hãy chọn inline/attachment có chủ đích, gửi filename fallback cùng filename* UTF-8, làm sạch tên và ngăn CRLF injection. Kết hợp header với MIME type chính xác, nosniff, origin cách ly cho file không tin cậy, authorization từng object, cache policy và kiểm thử Range/download trên browser mục tiêu.

## Tài liệu tham khảo

- [RFC 6266: Use of the Content-Disposition Header Field in the Hypertext Transfer Protocol (HTTP)](https://www.rfc-editor.org/rfc/rfc6266.html)
- [RFC 8187: Indicating Character Encoding and Language for HTTP Header Field Parameters](https://www.rfc-editor.org/rfc/rfc8187.html)
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
- [MDN: Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Disposition)
- [MDN: X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options)
- [MDN: HTML anchor download](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/a#download)
- [OWASP: File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP: HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
