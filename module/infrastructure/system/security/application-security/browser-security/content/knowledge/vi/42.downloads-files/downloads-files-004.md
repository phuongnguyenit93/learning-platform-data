# Filename handling: xử lý tên file an toàn khi upload và download

## 1. Filename handling là gì?

**Filename handling** là quá trình tiếp nhận, kiểm tra, lưu trữ, hiển thị và gửi tên file khi ứng dụng cho phép người dùng upload hoặc download tài liệu. Tên file thường do người dùng, browser, hệ điều hành hoặc một hệ thống bên ngoài cung cấp. Vì vậy, ứng dụng phải xem filename là dữ liệu không tin cậy.

Một tên file có thể chứa path traversal, ký tự điều khiển, dấu phân cách của hệ điều hành khác, Unicode gây nhầm lẫn, phần mở rộng giả mạo hoặc chuỗi được thiết kế để phá vỡ HTTP header. Nếu dùng trực tiếp filename làm đường dẫn lưu file, ứng dụng có thể ghi đè file ngoài thư mục upload. Nếu đưa filename vào header mà không encode đúng, ứng dụng có thể gặp header injection. Nếu chỉ tin phần mở rộng, file thực thi có thể được ngụy trang thành ảnh hoặc tài liệu.

Ví dụ các filename cần được kiểm tra:

```text
report.pdf
../../config/secrets.txt
..\..\Windows\win.ini
invoice.pdf.exe
CON.txt
report
X-Injected: yes.pdf
résumé-2026.pdf
```

Tên file hợp lệ về mặt hiển thị không nhất thiết hợp lệ làm đường dẫn lưu trữ. Ngược lại, một file có thể được lưu dưới ID ngẫu nhiên an toàn trong khi vẫn giữ tên gốc đã làm sạch để hiển thị hoặc tải xuống.

**Nguyên tắc:** tách biệt tên hiển thị, tên lưu trữ và đường dẫn vật lý. Không dùng filename do client cung cấp làm storage path hoặc định danh quyền truy cập. Xác thực nội dung file độc lập với phần mở rộng, rồi tạo đường dẫn lưu trữ từ ID do server sinh.

Bài viết thuộc chương **Download và file** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung kết nối filename handling với upload/download, path traversal, canonicalization, Unicode, HTTP Content-Disposition, MIME validation, archive extraction và ranh giới bảo mật của browser/server.

Sau bài học, bạn có thể:

- Phân biệt filename gốc, filename hiển thị, storage key và đường dẫn vật lý.
- Nhận diện path traversal trên POSIX và Windows.
- Hiểu canonicalization, URL decoding và vì sao decode nhiều lần nguy hiểm.
- Xử lý Unicode normalization, ký tự điều khiển, bidi control và tên dành riêng của Windows.
- Kiểm tra extension, MIME type và file signature theo nhiều lớp.
- Lưu file bằng ID ngẫu nhiên, tránh overwrite và kiểm soát collision.
- Tạo Content-Disposition an toàn với filename UTF-8.
- Cấu hình response download với Content-Type và security headers phù hợp.
- Phòng ZIP Slip và các lỗi filename khi giải nén archive.
- Kiểm tra filename ở browser mà không tin đường dẫn client gửi.
- Thực hành kiểm tra filename bằng lab Node.js local.

## 2. Tách tên hiển thị, storage key và physical path

Một thiết kế an toàn cần phân biệt ba giá trị:

| Giá trị | Mục đích | Ví dụ |
|---|---|---|
| Original filename | Giá trị nhận từ client hoặc metadata của archive | ../../report.pdf |
| Display filename | Tên đã chuẩn hóa và làm sạch để hiển thị/tải xuống | report.pdf |
| Storage key | ID nội bộ do server sinh | UUID ngẫu nhiên |

Đường dẫn vật lý được tạo từ storage root và storage key:

```text
Storage root:  /srv/app/private-uploads
Storage key:   8b5f2c4a-7a01-4f23-9c30-1d7f...
Physical path: /srv/app/private-uploads/8b5f2c4a-7a01-4f23-9c30-1d7f...
Display name:  báo-cáo-quý-3.pdf
```

Filename chỉ là metadata mô tả file. Storage key mới là định danh nội bộ để tìm nội dung file, và việc truy cập vẫn phải qua authorization của ứng dụng.

### 2.1. Original filename không phải đường dẫn

Browser thường không cung cấp đường dẫn máy local thật qua file input. Thuộc tính File.name chỉ là tên file; các browser thường loại bỏ phần đường dẫn trước khi cung cấp cho page.

Dù vậy, server vẫn không được tin giá trị filename từ multipart request. Client có thể tự tạo HTTP request và gửi filename tùy ý. File được upload từ script, mobile app hoặc công cụ HTTP cũng không nhất thiết tuân theo hành vi file picker của browser.

### 2.2. Display filename không phải storage key

Hai người dùng có thể upload file cùng tên report.pdf. Điều đó không có nghĩa file thứ hai được ghi đè file thứ nhất. Storage key phải duy nhất hoặc được quản lý theo namespace có kiểm soát.

Không dùng tên file để quyết định quyền đọc. Một người dùng đoán được salary.pdf hoặc report.pdf không được phép tải file nếu không có quyền đối với file record tương ứng.

### 2.3. Physical path là chi tiết server

Đường dẫn lưu trữ phải được server tạo từ thư mục gốc cố định và ID đã kiểm tra. Không nối trực tiếp uploadRoot + filename hoặc path.join(uploadRoot, clientFilename) rồi cho rằng đã an toàn.

Tốt nhất, nội dung upload nằm ngoài web root và không được browser truy cập trực tiếp bằng cách đoán URL. Server cung cấp download handler có authorization và response headers phù hợp.

## 3. Nguồn filename và ranh giới tin cậy

Filename có thể đến từ nhiều nguồn:

- Multipart upload: tham số filename trong Content-Disposition.
- Browser File API: File.name.
- API client hoặc mobile app: JSON field hoặc multipart metadata.
- Archive: tên entry bên trong ZIP/TAR.
- Cloud storage: object key hoặc metadata do người dùng đặt.
- Import từ hệ thống khác: tên file trong database hoặc message queue.
- Download response: filename được server gửi trong Content-Disposition.

Mỗi nguồn có encoding và quy tắc riêng. Không giả định filename đã được chuẩn hóa chỉ vì nó đến từ browser hoặc thư viện multipart.

### 3.1. Multipart filename

Một request upload có thể chứa:

```http
Content-Disposition: form-data; name="file"; filename="../../private/report.pdf"
Content-Type: application/pdf
```

Giá trị filename do client gửi. Nó không chứng minh file thực sự là PDF và không được dùng làm path. Parser multipart có thể xử lý quoted string, encoding hoặc dấu phân cách khác nhau; dùng thư viện parser được duy trì thay vì tự parse multipart bằng chuỗi.

### 3.2. Browser File API

Ví dụ:

```js
const input = document.querySelector('input[type="file"]');

input.addEventListener("change", () => {
  const file = input.files?.[0];
  if (!file) return;

  console.log({
    name: file.name,
    size: file.size,
    type: file.type
  });
});
```

file.name, file.size và file.type đều là metadata do client cung cấp. file.type có thể rỗng hoặc không chính xác. Server phải kiểm tra lại filename, kích thước và nội dung.

### 3.3. Archive entry

Tên entry trong ZIP/TAR có thể chứa đường dẫn tương đối, đường dẫn tuyệt đối, ký tự phân cách của nền tảng khác hoặc thành phần .. Khi giải nén, mỗi entry là input không tin cậy giống như filename từ upload.

Không tin rằng archive được tạo bởi một ứng dụng phổ biến thì sẽ an toàn. Archive có thể được attacker tạo thủ công hoặc được sửa sau khi tạo.

## 4. Path traversal và canonicalization

### 4.1. Path traversal là gì?

Path traversal xảy ra khi dữ liệu do người dùng kiểm soát làm đường dẫn thoát khỏi thư mục mà ứng dụng dự định sử dụng. Thành phần .. có nghĩa là đi lên thư mục cha trong nhiều hệ thống file.

Ví dụ nguy hiểm:

```js
const destination = path.join(uploadRoot, clientFilename);
await fs.writeFile(destination, fileBuffer);
```

Nếu filename là ../../config/app.env, đường dẫn kết quả có thể nằm ngoài upload root. Tùy quyền của tiến trình, lỗi này có thể ghi đè file cấu hình, mã nguồn hoặc dữ liệu khác.

### 4.2. Các dạng path cần nhận diện

| Dạng | Ví dụ | Rủi ro |
|---|---|---|
| POSIX traversal | ../../etc/passwd | Đi lên thư mục cha |
| Windows separator | ..\..\Windows\win.ini | Dấu gạch chéo ngược là separator trên Windows |
| Absolute path | /var/app/config.yml | Bỏ qua thư mục gốc khi resolve |
| Drive path | C:\data\secret.txt | Chỉ định ổ đĩa |
| UNC path | \\server\share\file.txt | Tham chiếu network share |
| Mixed separator | ..\../secret.txt | Bypass bộ lọc chỉ kiểm tra một dấu |
| Encoded traversal | %2e%2e%2fsecret | Dạng đã URL-encode |
| Double encoded | %252e%252e%252fsecret | Có thể thành traversal nếu decode nhiều lần |

Một bộ lọc chỉ tìm chuỗi ../ sẽ bỏ sót dấu gạch chéo ngược, absolute path, mixed separator hoặc dạng đã encode.

### 4.3. Canonicalization và kiểm tra containment

Canonicalization là quá trình đưa đường dẫn về dạng chuẩn để so sánh. Khi thật sự cần xử lý path, phải kiểm tra đường dẫn sau khi resolve có còn nằm trong storage root hay không.

Ví dụ kiểm tra containment bằng Node.js:

```js
import path from "node:path";

function isInsideRoot(root, candidate) {
  const relative = path.relative(root, candidate);

  return (
    relative === "" ||
    (
      relative !== ".." &&
      !relative.startsWith(".." + path.sep) &&
      !path.isAbsolute(relative)
    )
  );
}

const root = path.resolve("/srv/app/uploads");
const candidate = path.resolve(root, "generated-file-id");

if (!isInsideRoot(root, candidate)) {
  throw new Error("Path nằm ngoài storage root");
}
```

Đây là lớp kiểm tra bổ sung. Với upload thông thường, hãy dùng ID do server sinh làm tên file và không đưa filename gốc vào phép resolve. Nếu có symlink hoặc thư mục do attacker kiểm soát, chỉ kiểm tra chuỗi path chưa đủ để ngăn mọi race condition.

### 4.4. Không chỉ dùng basename

Một cách thường gặp là gọi path.basename(clientFilename). basename có thể hữu ích để lấy thành phần cuối theo quy tắc của platform hiện tại, nhưng không phải giải pháp đầy đủ:

- Server chạy POSIX có thể không coi dấu gạch chéo ngược là separator giống Windows.
- Filename có thể chứa ký tự điều khiển hoặc Unicode gây nhầm lẫn.
- Tên dành riêng và alternate data stream trên Windows vẫn cần xử lý.
- Filename vẫn có thể gây header injection hoặc hiển thị sai.
- Nó không xác thực loại file hoặc quyền truy cập.

Dùng parser/path library phù hợp, reject path-like input ở biên tiếp nhận và lưu file bằng storage key độc lập.

### 4.5. Decode đúng một lần

Nếu giao thức yêu cầu percent-decoding, thực hiện tại đúng boundary theo parser chuẩn rồi validate giá trị đã decode. Không decode lặp lại qua nhiều tầng.

Ví dụ %252e%252e%252f sau một lần decode trở thành %2e%2e%2f; sau lần thứ hai mới thành ../. Nếu gateway decode một lần và ứng dụng decode lần nữa, hai tầng có thể hiểu cùng một input khác nhau.

Quy tắc:

1. Xác định parser nào chịu trách nhiệm decode.
2. Decode đúng một lần theo giao thức.
3. Validate dạng đã decode.
4. Không chuyển tiếp một giá trị còn encoded cho tầng khác rồi decode lần nữa.
5. Không tự decode filename multipart nếu thư viện parser đã xử lý encoding.

## 5. Khác biệt giữa hệ điều hành

Tên file được diễn giải theo quy tắc filesystem. Một chuỗi có thể hợp lệ trên Linux nhưng không hợp lệ hoặc có ý nghĩa đặc biệt trên Windows.

### 5.1. Windows reserved names

Windows có các tên thiết bị dành riêng, ví dụ:

```text
CON
PRN
AUX
NUL
COM1 ... COM9
LPT1 ... LPT9
```

Các tên này vẫn có thể bị coi là reserved khi có phần mở rộng, ví dụ CON.txt. Ứng dụng tạo file để tải xuống cho Windows users nên xử lý các tên này.

### 5.2. Dấu và ký tự đặc biệt

Windows không cho phép một số ký tự trong filename, gồm:

```text
< > : " / \ | ? *
```

Dấu hai chấm còn có ý nghĩa đặc biệt trong một số ngữ cảnh như alternate data stream. Không để client quyết định tên path trên Windows.

### 5.3. Dấu chấm và khoảng trắng ở cuối

Một số API/filesystem trên Windows có thể chuẩn hóa hoặc loại bỏ dấu chấm và khoảng trắng ở cuối tên. Hai chuỗi mà ứng dụng tưởng khác nhau có thể trỏ tới cùng tên thực tế.

Chuẩn hóa trước khi kiểm tra collision, và không dựa vào so sánh chuỗi đơn giản để bảo đảm tên duy nhất trên mọi platform.

### 5.4. Case sensitivity

Một số filesystem phân biệt chữ hoa/chữ thường, một số không. Report.pdf và report.pdf có thể là hai file khác nhau trên hệ thống này nhưng trùng tên trên hệ thống khác.

Storage key ngẫu nhiên tránh phụ thuộc vào case sensitivity của display filename. Nếu cần collision check cho tên hiển thị, phải dùng quy tắc tương thích với storage backend thực tế.

## 6. Unicode và ký tự gây nhầm lẫn

### 6.1. Unicode normalization

Một ký tự hiển thị có thể được biểu diễn bằng nhiều chuỗi code point. Ví dụ chữ có dấu có thể là một code point dựng sẵn hoặc chữ cái kết hợp dấu.

Unicode normalization như NFC giúp đưa các chuỗi tương đương về một dạng chuẩn phổ biến:

```js
const normalized = filename.normalize("NFC");
```

NFC hữu ích để giảm một số trường hợp tên trông giống nhau nhưng byte khác nhau. Tuy nhiên, normalization không loại bỏ mọi ký tự nguy hiểm và không tạo ra tên duy nhất.

### 6.2. NFKC cần được cân nhắc

NFKC có thể biến một số ký tự compatibility thành dạng chuẩn tương thích. Nó có thể hữu ích trong một số identifier, nhưng cũng có thể thay đổi cách viết mà người dùng mong đợi.

Không áp dụng NFKC một cách mù quáng cho mọi filename. Xác định chính sách rõ ràng, giữ metadata gốc nếu cần audit và dùng storage key độc lập.

### 6.3. Homoglyph và confusable characters

Một số ký tự từ bảng chữ cái khác nhau có hình dáng gần giống nhau. Ví dụ chữ Latin a và một số ký tự Cyrillic có thể khó phân biệt khi nhìn nhanh.

Điều này có thể bị lợi dụng để tạo file giả mạo như tên tài liệu chính thức hoặc file có phần mở rộng trông giống .pdf. Không dùng mắt người làm lớp kiểm tra duy nhất; hiển thị loại file đã xác minh, nguồn tải và cảnh báo khi cần.

### 6.4. Bidirectional controls

Ký tự điều khiển hướng văn bản có thể khiến thứ tự hiển thị khác với thứ tự ký tự thực. Một filename có thể trông như kết thúc bằng .pdf trong khi phần mở rộng thực tế là loại khác.

Đặc biệt lưu ý các nhóm bidi control như:

```text
U+202A ... U+202E
U+2066 ... U+2069
```

Có thể từ chối hoặc loại bỏ các ký tự này trong filename dùng cho UI/download. Nếu cần hỗ trợ ngôn ngữ có hướng văn bản phức tạp, dùng UI có thể hiển thị rõ tên đã kiểm tra và phần mở rộng thực tế.

### 6.5. Control characters và null byte

Reject hoặc loại bỏ ký tự điều khiển như CR, LF, NUL và DEL trước khi dùng filename trong log, header hoặc UI. Không dựa vào hành vi của một thư viện cũ có thể cắt chuỗi tại null byte.

Không đưa filename thô vào log line hoặc HTTP header. Dùng structured logging và escaping phù hợp.

## 7. Quy tắc tạo display filename

Display filename là giá trị đã làm sạch để hiển thị hoặc gợi ý khi tải xuống. Chính sách nên rõ ràng, nhất quán và có giới hạn độ dài.

Một quy trình thường dùng:

1. Kiểm tra input là chuỗi hợp lệ.
2. Áp dụng Unicode normalization đã chọn, thường là NFC.
3. Reject dấu phân cách path / và \.
4. Reject control characters và bidi control không được phép.
5. Thay ký tự không hợp lệ trên platform mục tiêu bằng dấu gạch dưới hoặc từ chối.
6. Loại bỏ dấu chấm/khoảng trắng nguy hiểm ở đầu/cuối theo chính sách.
7. Xử lý reserved device name.
8. Giới hạn số code point và số byte UTF-8.
9. Kiểm tra extension theo allowlist.
10. Encode đúng khi hiển thị HTML hoặc đưa vào Content-Disposition.

### 7.1. Sanitization không phải validation nội dung

Tên invoice.pdf chỉ nói người gửi muốn gọi file như vậy. Nó không chứng minh nội dung là PDF.

Tên photo.jpg không bảo đảm byte là ảnh JPEG. File có thể là HTML, executable, script hoặc polyglot được đặt tên khác.

Tách riêng các bước:

- Sanitize display filename.
- Validate extension theo policy.
- Detect MIME/content type từ nội dung.
- Parse file bằng thư viện phù hợp.
- Quét malware hoặc xử lý bổ sung theo threat model.
- Lưu vào storage key do server sinh.

### 7.2. Không cố giữ mọi ký tự bằng mọi giá

Nếu filename chứa ký tự không hỗ trợ trên platform mục tiêu, thay thế hoặc từ chối theo policy. Mục tiêu là tạo tên dễ hiểu, không gây lỗi và không mang ý nghĩa path/header ngoài ý muốn.

Không cần làm sạch filename bằng một regex duy nhất áp dụng cho mọi OS. Quy tắc display và storage nên độc lập với filesystem.

## 8. Extension, MIME type và nội dung file

### 8.1. Extension là tín hiệu yếu

Extension là phần sau dấu chấm cuối cùng, nhưng có thể bị giả mạo:

```text
invoice.pdf.exe
photo.jpg.html
report.pdf.
archive.tar.gz
.env
```

Nếu chỉ kiểm tra chuỗi có chứa .pdf, file invoice.pdf.exe có thể vượt qua bộ lọc sai. Lấy extension cuối theo quy tắc đã định nghĩa và so sánh với allowlist.

### 8.2. MIME type từ client không đáng tin

Multipart request có thể gửi:

```http
Content-Disposition: form-data; name="file"; filename="photo.jpg"
Content-Type: image/jpeg
```

Client có thể tự khai Content-Type. Browser cũng có thể gửi loại chung như application/octet-stream hoặc giá trị rỗng.

Không dựa riêng vào file.type trong browser hoặc multipart Content-Type để quyết định file có an toàn hay không.

### 8.3. File signature và content inspection

Một số loại file có magic bytes hoặc cấu trúc định dạng đặc trưng. Server có thể dùng thư viện nhận dạng file dựa trên nội dung để đối chiếu với loại được phép.

Ví dụ kiểm tra theo nhiều lớp:

| Lớp | Ví dụ | Vai trò |
|---|---|---|
| Filename extension | .pdf, .png | Hạn chế loại mà sản phẩm chấp nhận |
| Declared MIME | application/pdf | Tín hiệu từ client, chỉ dùng tham khảo |
| Detected MIME | Loại suy ra từ bytes | Đối chiếu với allowlist |
| Parser validation | Parse PDF/image/document | Kiểm tra cấu trúc định dạng |
| Malware scan/CDR | Antivirus, content disarm and reconstruction | Giảm rủi ro theo loại file và threat model |

Magic bytes không chứng minh file hoàn toàn an toàn. Một file có thể có header hợp lệ nhưng chứa exploit trong parser hoặc nội dung chủ động. Dùng parser cập nhật, giới hạn tài nguyên và sandbox khi xử lý file rủi ro cao.

### 8.4. Double extension và file active content

Ví dụ invoice.pdf.exe có thể đánh lừa người dùng khi UI ẩn extension cuối. Một file HTML hoặc SVG cũng có thể chứa nội dung chủ động khi được browser mở inline.

Biện pháp:

- Hiển thị extension cuối cùng và loại nội dung đã xác minh.
- Không cho upload các định dạng active content nếu không cần.
- Không phục vụ file không tin cậy cùng origin với ứng dụng nhạy cảm.
- Ưu tiên attachment download cho nội dung cần tải về.
- Dùng sandbox hoặc isolated origin nếu cần preview.
- Không tin Content-Type do người upload khai báo.

### 8.5. Giới hạn kích thước và parser

File có thể gây tiêu thụ CPU, RAM hoặc disk quá mức dù extension/MIME hợp lệ. Cần giới hạn:

- Kích thước request và từng file.
- Số file trong một request.
- Số entry trong archive.
- Kích thước sau giải nén.
- Độ sâu thư mục.
- Thời gian parse/scan.
- Tài nguyên CPU/memory của worker xử lý file.

## 9. Storage an toàn cho upload

### 9.1. Tạo storage key ngẫu nhiên

Ví dụ:

```js
import { randomUUID } from "node:crypto";

const storageKey = randomUUID();
```

Storage key không chứa filename, user input hoặc path. Database có thể lưu metadata:

| Field | Ví dụ |
|---|---|
| file_id | UUID do server sinh |
| owner_id | ID user đã xác thực |
| storage_key | UUID hoặc object key nội bộ |
| display_name | báo-cáo-quý-3.pdf |
| detected_mime | application/pdf |
| size_bytes | 245760 |
| sha256 | Hash nội dung để kiểm tra integrity |
| created_at | Timestamp |

Quyền truy cập được kiểm tra qua file_id và owner/ACL trong database. Không coi UUID khó đoán là authorization thay thế.

### 9.2. Lưu ngoài web root

Đặt file upload trong private storage hoặc bucket không public mặc định. Khi download, backend:

1. Xác thực người dùng.
2. Kiểm tra quyền với file record.
3. Tra storage key trong database.
4. Mở object/file theo key đã kiểm soát.
5. Tạo Content-Disposition từ display filename đã làm sạch.
6. Trả Content-Type đã xác minh và security headers phù hợp.

Không ghép request parameter trực tiếp thành filesystem path.

### 9.3. Tránh overwrite và race condition

Dùng storage key duy nhất và thao tác tạo mới theo chế độ không ghi đè. Với filesystem, tạo file theo cơ chế exclusive-create phù hợp và thư mục chỉ tiến trình tin cậy mới có quyền ghi.

Nếu hai request đồng thời upload cùng display filename, chúng vẫn phải có storage key riêng. Nếu sản phẩm cần thay thế file, thực hiện qua một thao tác có authorization và versioning rõ ràng.

### 9.4. Symlink và thư mục không tin cậy

Nếu attacker có thể tạo symlink trong storage root, path containment theo chuỗi có thể không ngăn việc ghi qua symlink tới vị trí khác. Giữ storage directory không cho user tạo file tùy ý, dùng API filesystem an toàn, exclusive creation và kiểm soát symlink theo platform.

Không chạy xử lý upload dưới tài khoản có quyền ghi rộng vào hệ thống file. Tách quyền của upload processor khỏi application configuration và source code.

## 10. Content-Disposition khi download

### 10.1. Header quyết định cách browser xử lý response

HTTP Content-Disposition có thể gợi ý browser hiển thị inline hoặc tải file:

```http
Content-Disposition: attachment; filename="report.pdf"
```

attachment thường yêu cầu browser tải file xuống. inline cho phép browser hiển thị nội dung nếu hỗ trợ loại file.

Với file không tin cậy, attachment thường là lựa chọn phù hợp hơn preview trực tiếp. Tuy nhiên, header này không thay thế MIME validation hoặc authorization.

### 10.2. Filename UTF-8

Để hỗ trợ filename có dấu và Unicode, Content-Disposition có thể gửi cả filename fallback ASCII và filename* theo RFC 5987/6266:

```http
Content-Disposition: attachment; filename="bao-cao.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o.pdf
```

Browser hiện đại thường ưu tiên filename* khi hỗ trợ. Fallback filename giúp tương thích với client cũ hơn.

Không nối raw filename vào header. CR/LF hoặc dấu quote có thể làm hỏng cấu trúc header hoặc tạo header injection nếu framework không từ chối.

### 10.3. Tạo header bằng thư viện

Ưu tiên thư viện Content-Disposition được duy trì và tuân thủ RFC thay vì tự viết encoder. Nếu phải tự tạo, cần:

- Reject CR, LF và control characters.
- Sanitize display filename trước.
- Escape quote và backslash trong fallback.
- Percent-encode UTF-8 cho filename* theo đúng quy tắc.
- Giới hạn độ dài.
- Không dùng raw path hoặc storage key làm filename hiển thị.

### 10.4. Không dùng URL query làm filename path

Download endpoint nên nhận file ID:

```text
GET /files/8b5f2c4a-7a01-4f23-9c30-1d7f
```

Backend tra metadata và storage key sau khi kiểm tra quyền. Không nhận query path hoặc dùng query filename để quyết định file vật lý cần đọc.

## 11. Security headers cho download

Một response download thường cần các header phù hợp với loại nội dung và threat model:

```http
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

Ý nghĩa:

- Content-Type: loại nội dung đã được server xác minh.
- Content-Disposition: attachment: đề nghị browser tải file.
- X-Content-Type-Options: nosniff: yêu cầu browser không tự suy đoán MIME type theo một số cơ chế sniffing.
- Cache-Control: private, no-store: hạn chế lưu response riêng tư vào cache theo policy phù hợp.

Không dùng một Content-Type cố định cho mọi file. Không trả text/html cho file chỉ vì client gửi MIME như vậy. Với file không tin cậy cần preview, cân nhắc isolated origin, sandbox và CSP chặt.

### 11.1. Isolated origin cho user uploads

Nếu ứng dụng cho phép người dùng tải nội dung HTML/SVG hoặc file có khả năng active content, phục vụ chúng từ origin riêng không có cookie đăng nhập của ứng dụng. Cách này giảm khả năng nội dung upload tương tác với session và DOM của ứng dụng chính.

Không dùng subdomain cùng cookie Domain rộng nếu mục tiêu là tách credential. Thiết kế cookie host-only, không chia sẻ credential sang upload origin và kiểm soát CORS rõ ràng.

### 11.2. Cache và dữ liệu riêng tư

File riêng tư không nên được cache public bởi CDN/shared proxy. Dùng policy phù hợp với authorization và cache key. no-store hữu ích cho response nhạy cảm, nhưng không thay thế quyền truy cập và xóa file.

## 12. Browser download APIs

### 12.1. File input

```html
<input type="file" id="upload" accept=".pdf,.png,.jpg">
```

Thuộc tính accept chỉ là gợi ý cho file picker, không phải validation bảo mật. Người dùng hoặc script có thể gửi loại file khác. Server vẫn cần kiểm tra.

### 12.2. File.name

Browser cung cấp tên file qua File.name, nhưng không cung cấp đường dẫn máy local đầy đủ cho page. Không dựa vào File.name để lấy vị trí file hoặc xác minh nơi file đến.

```js
const file = document.querySelector("#upload").files[0];

if (file) {
  console.log(file.name);
  console.log(file.size);
  console.log(file.type);
}
```

Ba thuộc tính này hỗ trợ UX; server vẫn cần validation độc lập.

### 12.3. Download attribute

Ví dụ:

```html
<a href="/files/8b5f2c4a-7a01-4f23-9c30-1d7f"
   download="bao-cao.pdf">
  Tải báo cáo
</a>
```

Thuộc tính download là gợi ý cho browser về tên file tải xuống. Browser có thể bỏ qua hoặc xử lý khác tùy origin, response header, sandbox và policy. Content-Disposition từ server thường là cơ chế đáng tin cậy hơn để cung cấp filename cho response.

Không coi tên trong download attribute là validation cho server hoặc bằng chứng file an toàn.

### 12.4. Blob URL

Ứng dụng có thể tạo Blob URL cho dữ liệu do client tạo:

```js
const blob = new Blob(["example"], {
  type: "text/plain"
});

const objectUrl = URL.createObjectURL(blob);

const link = document.createElement("a");
link.href = objectUrl;
link.download = "example.txt";
link.click();

URL.revokeObjectURL(objectUrl);
```

Tên download vẫn là dữ liệu do ứng dụng cung cấp và cần được tạo từ giá trị an toàn. Thu hồi object URL sau khi dùng để giải phóng tài nguyên khi phù hợp.

## 13. Archive extraction và ZIP Slip

### 13.1. ZIP Slip là gì?

ZIP Slip là dạng path traversal xảy ra khi ứng dụng giải nén archive bằng cách ghép thư mục đích với tên entry không tin cậy.

Ví dụ entry có tên:

```text
../../webroot/config.js
..\..\app\settings.json
/var/app/secrets.txt
C:\Windows\Temp\payload.txt
```

Nếu extractor ghi entry mà không kiểm tra containment, file có thể được ghi ra ngoài thư mục giải nén.

### 13.2. Kiểm tra từng entry

Với mỗi entry:

1. Parse tên entry theo format archive, thường chuẩn hóa separator về / để phân tích.
2. Reject absolute path, drive prefix, UNC path và segment ...
3. Resolve đường dẫn đích bên trong extraction root.
4. Kiểm tra đường dẫn sau resolve nằm trong root.
5. Kiểm soát symlink/hardlink và không cho entry tạo symlink thoát root.
6. Không overwrite file hiện có nếu policy không cho phép.
7. Giới hạn số entry, độ sâu, kích thước sau giải nén và compression ratio.

Không chỉ kiểm tra chuỗi có chứa ..; cần kiểm tra từng path segment và kết quả resolve.

### 13.3. Symlink trong archive

Một entry có thể tạo symlink trỏ ra ngoài extraction root, rồi entry tiếp theo ghi qua symlink đó. Vì vậy, kiểm tra containment của chuỗi đích đơn lẻ chưa đủ nếu extractor cho phép symlink.

Nếu không cần symlink, từ chối chúng. Nếu cần, dùng thư viện có cơ chế an toàn đã được kiểm tra và đảm bảo không thể theo symlink ra ngoài root.

### 13.4. Decompression bomb

Archive nhỏ có thể giải nén thành dữ liệu rất lớn hoặc chứa hàng triệu entry. Giới hạn compressed size không đủ; cần giới hạn tổng uncompressed bytes, số entry, độ sâu và thời gian xử lý.

Xử lý archive trong worker/process có giới hạn tài nguyên. Không giải nén file không tin cậy vào thư mục chứa source code hoặc cấu hình production.

## 14. Logging và hiển thị filename

### 14.1. Log injection

Filename có thể chứa CR/LF, tab hoặc control characters. Nếu ghi raw filename vào log dạng dòng, attacker có thể tạo log giả hoặc làm sai cấu trúc parser.

Dùng structured logging, encode/escape giá trị và giới hạn độ dài. Giữ original filename chỉ khi cần cho audit; phân biệt nó với display filename đã làm sạch.

### 14.2. HTML injection

Không chèn filename trực tiếp vào HTML:

```js
// Không an toàn nếu filename chứa markup.
container.innerHTML = "<span>" + filename + "</span>";
```

Dùng text content:

```js
container.textContent = filename;
```

Nếu template engine được dùng, bật auto-escaping và không đánh dấu filename là HTML an toàn.

### 14.3. Bidi và tên gây nhầm lẫn trong UI

Hiển thị filename cùng loại file đã xác minh, dung lượng và nguồn upload. Có thể dùng layout tách phần mở rộng hoặc thông tin loại nội dung để người dùng không chỉ dựa vào chuỗi tên.

Không hiển thị filename đã sanitize như thể đó là tên gốc chưa chỉnh sửa nếu việc audit cần phân biệt. Có thể lưu original name riêng với quyền truy cập hạn chế và display name đã làm sạch.

### 14.4. Tránh đưa PII vào filename

Filename có thể xuất hiện trong download history, log, email notification, support ticket và audit record. Tránh tự tạo filename từ email, số tài khoản, số hồ sơ hoặc dữ liệu cá nhân nếu không cần.

Dùng tên chung như statement.pdf và metadata riêng được bảo vệ nếu sản phẩm cần giữ liên kết với tài khoản.

## 15. Ví dụ Node.js: làm sạch tên hiển thị và tạo storage path

Đoạn code sau minh họa một policy nhỏ cho filename hiển thị. Nó reject path separator và control character, chuẩn hóa NFC, xử lý reserved name, giới hạn độ dài và kiểm tra extension allowlist.

Đây không phải bộ kiểm tra nội dung file. Production vẫn cần kiểm tra MIME/content signature, parser, kích thước, malware và authorization.

```js
import path from "node:path";
import { randomUUID } from "node:crypto";

const ALLOWED_EXTENSIONS = new Set([
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".txt"
]);

const RESERVED_WINDOWS_NAMES =
  /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$/i;

function truncateUtf8(value, maxBytes) {
  let result = "";

  for (const character of value) {
    const next = result + character;
    if (Buffer.byteLength(next, "utf8") > maxBytes) break;
    result = next;
  }

  return result;
}

function sanitizeDisplayFilename(input) {
  if (typeof input !== "string" || input.length === 0) {
    throw new TypeError("Filename phải là chuỗi không rỗng");
  }

  let name = input.normalize("NFC");

  if (/[\/\\]/.test(name)) {
    throw new Error("Filename không được chứa path separator");
  }

  if (/[\u0000-\u001F\u007F]/.test(name)) {
    throw new Error("Filename chứa control character");
  }

  if (/[\u202A-\u202E\u2066-\u2069]/.test(name)) {
    throw new Error("Filename chứa bidi control");
  }

  name = name.replace(/[<>:"|?*]/g, "_");
  name = name.replace(/^[. ]+/, "").replace(/[. ]+$/g, "");

  if (!name) {
    name = "download";
  }

  const firstPart = name.split(".")[0];

  if (RESERVED_WINDOWS_NAMES.test(firstPart)) {
    name = "_" + name;
  }

  const dot = name.lastIndexOf(".");
  const extension = dot > 0 ? name.slice(dot) : "";
  let stem = extension ? name.slice(0, dot) : name;

  stem = truncateUtf8(stem, 140);
  name = (stem || "download") + extension;
  name = truncateUtf8(name, 180);

  if (!name || name === "." || name === "..") {
    throw new Error("Filename sau chuẩn hóa không hợp lệ");
  }

  return name;
}

function getExtension(filename) {
  const dot = filename.lastIndexOf(".");
  return dot > 0 ? filename.slice(dot).toLowerCase() : "";
}

function validateAllowedExtension(filename) {
  const extension = getExtension(filename);

  if (!ALLOWED_EXTENSIONS.has(extension)) {
    throw new Error("File extension không được hỗ trợ");
  }

  return extension;
}

function isInsideRoot(root, candidate) {
  const relative = path.relative(root, candidate);

  return (
    relative !== "" &&
    relative !== ".." &&
    !relative.startsWith(".." + path.sep) &&
    !path.isAbsolute(relative)
  );
}

function createStoragePath(uploadRoot) {
  const root = path.resolve(uploadRoot);
  const storageKey = randomUUID();
  const destination = path.resolve(root, storageKey);

  if (!isInsideRoot(root, destination)) {
    throw new Error("Storage path nằm ngoài root");
  }

  return {
    storageKey,
    destination
  };
}

for (const input of [
  "report.pdf",
  "báo-cáo-quý-3.pdf",
  "invoice.pdf.exe",
  "CON.txt",
  "../../private/secret.txt",
  "report\r\nX-Injected: yes.pdf"
]) {
  try {
    const displayName = sanitizeDisplayFilename(input);
    const extension = validateAllowedExtension(displayName);

    console.log({
      input: JSON.stringify(input),
      displayName,
      extension,
      acceptedByExtensionPolicy: true
    });
  } catch (error) {
    console.log({
      input: JSON.stringify(input),
      rejected: error.message
    });
  }
}

console.log(
  "Generated storage path:",
  createStoragePath("/srv/app/private-uploads")
);
```

### 15.1. Giới hạn của ví dụ

- Allowlist extension chỉ là một lớp policy, không chứng minh nội dung file đúng định dạng.
- path.relative() kiểm tra containment theo path string của platform hiện tại; nó không tự giải quyết symlink race.
- Storage directory phải do server quản lý, không cho người dùng tạo symlink hoặc file tùy ý.
- Cần dùng exclusive-create hoặc object storage API có semantics không overwrite.
- Filename hiển thị phải được encode đúng khi đưa vào HTML hoặc HTTP header.
- Cần kiểm tra dung lượng, MIME, signature, parser và quyền upload/download.

## 16. Lab local: kiểm thử filename

Lab chạy một script Node.js không tạo file trên máy. Nó nhận danh sách filename giả, áp dụng policy và hiển thị kết quả. Mục tiêu là hiểu input nào bị reject và vì sao.

### 16.1. Tạo file filename-lab.mjs

Dùng đoạn code ở mục 15 và lưu thành filename-lab.mjs. Chạy:

```bash
node filename-lab.mjs
```

Quan sát các trường displayName, extension, acceptedByExtensionPolicy hoặc rejected.

### 16.2. Bổ sung test cases

Thêm từng trường hợp sau vào mảng input:

```js
[
  "normal.txt",
  ".hidden",
  "name.",
  " name.pdf ",
  "CON.txt",
  "LPT1.csv",
  "photo.jpg.html",
  "invoice.pdf.exe",
  "folder/file.pdf",
  "folder\\file.pdf",
  "C:\\temp\\file.pdf",
  "\\\\server\\share\\file.pdf",
  "line1\nline2.pdf",
  "name\u202Efdp.exe",
  "résumé.pdf",
  "resume\u0301.pdf"
]
```

Kết quả mong đợi theo policy trong ví dụ:

- Tên bình thường có extension trong allowlist được chấp nhận ở bước extension.
- Dotfile hoặc tên không có extension bị từ chối theo allowlist.
- CON.txt và LPT1.csv được đổi display name để tránh reserved base name; extension vẫn phải được allowlist.
- Double extension có phần mở rộng cuối không được phép sẽ bị từ chối.
- Path separator, absolute path và UNC path bị reject.
- CR/LF và bidi control bị reject.
- Hai dạng Unicode tương đương được chuẩn hóa NFC; điều đó không có nghĩa chúng là hai file có nội dung giống nhau.

### 16.3. Kiểm tra path containment

Thử thay storage key bằng một giá trị cố ý không hợp lệ trong một bản test riêng, ví dụ ../outside. Kiểm tra isInsideRoot() trả về false. Không dùng giá trị đó để ghi file.

Trong production, không nhận storage key từ người dùng nếu chưa xác thực định dạng và kiểm tra quyền truy cập record tương ứng.

### 16.4. Kiểm tra Content-Disposition

Khi triển khai download endpoint, kiểm tra response trong DevTools Network:

- Header Content-Disposition có attachment.
- Filename Unicode hiển thị đúng.
- Không có CR/LF hoặc ký tự quote phá header.
- Header X-Content-Type-Options có nosniff.
- Content-Type khớp loại nội dung server đã xác minh.
- User không có quyền nhận response 403/404 phù hợp.
- File không bị cache public khi chứa dữ liệu riêng tư.

Không thử upload executable hoặc file độc hại lên hệ thống production để kiểm tra. Dùng fixture vô hại trong môi trường local/test.

## 17. Checklist review filename handling

Trước khi phát hành chức năng upload/download:

1. **Trust boundary:** Filename có được coi là input không tin cậy từ mọi client không?
2. **Separation:** Display filename, storage key và physical path có tách biệt không?
3. **Path traversal:** Có reject /, \, absolute path, drive path, UNC và .. không?
4. **Canonicalization:** Có decode đúng một lần và validate sau decode không?
5. **Unicode:** Có policy NFC/NFKC, bidi control, confusable và length limit không?
6. **Platform:** Có xử lý Windows reserved names, ADS, trailing dots/spaces và case collision không?
7. **Extension:** Có allowlist theo nhu cầu sản phẩm và kiểm tra extension cuối không?
8. **MIME:** Có bỏ qua MIME khai báo từ client như một nguồn xác thực duy nhất không?
9. **Content:** Có detect signature, parse, scan hoặc re-encode theo loại file không?
10. **Storage:** Có dùng ID do server sinh và lưu ngoài web root không?
11. **Overwrite:** Có tránh collision/overwrite và kiểm soát race condition không?
12. **Symlink:** Storage root có ngăn user tạo symlink hoặc đường dẫn thoát root không?
13. **Download auth:** Có xác thực và authorization trên từng file record không?
14. **Headers:** Có Content-Disposition an toàn, Content-Type đã xác minh và nosniff không?
15. **Active content:** HTML/SVG hoặc file active có được cách ly origin/sandbox phù hợp không?
16. **Archive:** ZIP/TAR extraction có chống ZIP Slip, symlink và decompression bomb không?
17. **Logging:** Filename có được escape trong log và giới hạn độ dài không?
18. **UI:** Filename có được render bằng text/auto-escaping thay vì innerHTML không?
19. **Privacy:** Filename có chứa email, account ID hoặc dữ liệu nhạy cảm không cần thiết không?
20. **Testing:** Đã thử Unicode, CRLF, path traversal, double extension và platform edge cases chưa?

## 18. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| Browser gửi File.name nên server có thể tin. | Client tự tạo request và gửi filename tùy ý; server phải validate. |
| path.basename() giải quyết mọi path traversal. | Separator và semantics khác nhau theo platform; basename không xử lý Unicode, header hay extension. |
| Chỉ cần bỏ chuỗi ../. | Có backslash, absolute path, drive path, UNC, encoding và mixed separator. |
| Filename đã URL-encode thì an toàn. | Encoding không phải validation hoặc encryption; decode nhiều lần còn tạo bypass. |
| Extension .pdf chứng minh file là PDF. | Extension là metadata do người gửi chọn; phải kiểm tra nội dung. |
| MIME type trong multipart là đáng tin. | Client có thể tự khai MIME type bất kỳ. |
| Tên file duy nhất thì storage an toàn. | Filename có thể collision, overwrite hoặc traversal; dùng storage key do server sinh. |
| UUID thay thế authorization. | ID khó đoán không chứng minh người dùng có quyền tải file. |
| NFC giải quyết mọi vấn đề Unicode. | NFC chỉ chuẩn hóa một số biểu diễn; homoglyph và bidi control vẫn cần xử lý. |
| Đổi dấu / thành _ là đủ. | Còn dấu \, absolute path, reserved names, control chars và header injection. |
| Content-Disposition filename có thể nối chuỗi trực tiếp. | Cần reject control chars và encode filename theo chuẩn; ưu tiên thư viện. |
| attachment làm file an toàn. | Attachment chỉ gợi ý download; nội dung vẫn phải được kiểm tra. |
| nosniff xác minh file. | nosniff hạn chế MIME sniffing; nó không scan hoặc validate nội dung. |
| Giải nén vào thư mục tạm là đủ. | Entry traversal hoặc symlink vẫn có thể thoát khỏi thư mục tạm. |
| Tên hiển thị và tên lưu trữ phải giống nhau. | Display name phục vụ người dùng; storage key phục vụ lưu trữ và nên do server sinh. |

## 19. Câu hỏi ôn tập

1. Filename handling bao gồm những giai đoạn nào?
2. Vì sao original filename không được dùng làm physical path?
3. Display filename khác storage key ở điểm nào?
4. Path traversal có thể xuất hiện dưới những dạng nào trên POSIX và Windows?
5. Vì sao chỉ kiểm tra ../ không đủ?
6. Canonicalization và path containment giải quyết vấn đề gì?
7. Vì sao decode URL nhiều lần có thể tạo bypass?
8. Windows reserved names gồm những ví dụ nào?
9. Unicode NFC giúp ích gì và không giải quyết vấn đề nào?
10. Bidi control có thể làm người dùng hiểu nhầm filename ra sao?
11. Vì sao extension và MIME khai báo từ client không đủ xác minh file?
12. File signature và parser validation khác nhau thế nào?
13. Vì sao server nên tạo storage key ngẫu nhiên?
14. Vì sao UUID không thay thế authorization?
15. Content-Disposition filename và filename* có vai trò gì?
16. X-Content-Type-Options: nosniff bảo vệ điều gì?
17. ZIP Slip xảy ra như thế nào?
18. Symlink trong archive tạo rủi ro gì?
19. Vì sao filename cần được escape khi log và render HTML?
20. Những header nào cần kiểm tra trong download response?

**Đáp án định hướng:** (1) Tiếp nhận, normalize, validate, lưu, hiển thị và download. (2) Nó có thể chứa traversal hoặc absolute path. (3) Display name dành cho người dùng; storage key là ID nội bộ do server sinh. (4) ../, ..\, absolute path, drive path, UNC, encoded traversal. (5) Có separator khác, encoding và path tuyệt đối. (6) Đưa path về dạng so sánh và xác minh nó nằm trong root. (7) Chuỗi double-encoded có thể trở thành traversal sau nhiều tầng decode. (8) CON, PRN, AUX, NUL, COM1-9, LPT1-9. (9) NFC chuẩn hóa một số biểu diễn tương đương, nhưng không giải quyết homoglyph hoặc bidi. (10) Thứ tự hiển thị có thể khác thứ tự ký tự thật. (11) Client kiểm soát metadata; nội dung có thể giả mạo. (12) Signature nhận dạng byte pattern; parser kiểm tra cấu trúc theo định dạng. (13) Tránh path injection và collision từ tên do client kiểm soát. (14) Cần kiểm tra owner/ACL trước khi trả file. (15) filename là fallback; filename* hỗ trợ UTF-8 theo chuẩn. (16) Hạn chế browser MIME sniffing trong các ngữ cảnh áp dụng. (17) Entry archive chứa path thoát extraction root. (18) Entry sau có thể ghi qua symlink ra ngoài root. (19) Tránh log injection và HTML injection. (20) Content-Type, Content-Disposition, X-Content-Type-Options, Cache-Control và các header phù hợp threat model.

## 20. Tài liệu tham khảo

- [RFC 6266 — Content-Disposition in HTTP](https://www.rfc-editor.org/rfc/rfc6266): Quy tắc filename và disposition trong HTTP response.
- [RFC 5987 — Character Set and Language Encoding for HTTP Header Field Parameters](https://www.rfc-editor.org/rfc/rfc5987): Encoding UTF-8 cho tham số header như filename*.
- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578): Multipart form-data và filename parameter.
- [WHATWG — File API](https://www.w3.org/TR/FileAPI/): File object và metadata browser cung cấp.
- [MDN — Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Disposition): Cách browser xử lý inline/attachment và filename.
- [MDN — File.name](https://developer.mozilla.org/en-US/docs/Web/API/File/name): Tên file trong browser File API.
- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options): Hạn chế MIME sniffing.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): Validation, storage và xử lý file upload.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): Các dạng path traversal và biện pháp phòng vệ.
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload): Rủi ro upload file không được kiểm soát.
- [Node.js — Path](https://nodejs.org/api/path.html): Resolve, relative, basename và thao tác path theo platform.
- [Unicode — Normalization Forms](https://unicode.org/reports/tr15/): NFC/NFKC và Unicode normalization.
- [CWE-22 — Improper Limitation of a Pathname to a Restricted Directory](https://cwe.mitre.org/data/definitions/22.html): Path traversal/Zip Slip class.
- [CWE-434 — Unrestricted Upload of File with Dangerous Type](https://cwe.mitre.org/data/definitions/434.html): Upload file có loại nguy hiểm.

**Kết nối với mô hình bảo mật web:** Filename là metadata không tin cậy đi qua browser, HTTP, server và filesystem. Path traversal được ngăn bằng việc tách storage key khỏi display name và kiểm tra containment; extension phải được đối chiếu với MIME/signature và parser; Content-Disposition cần encode đúng để tránh header injection. Khi download hoặc giải nén, tiếp tục kiểm tra authorization, cache, symlink, archive entry và nội dung active. Không dùng tên file làm đường dẫn hay bằng chứng quyền truy cập.
