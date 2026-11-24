# Content-Type: kiểm soát cách browser diễn giải và tải tệp

## 1. Vì sao Content-Type quan trọng?

Khi browser nhận một HTTP response, nó cần biết nội dung bên trong là HTML, CSS, JavaScript, JSON, ảnh, PDF hay một định dạng khác. Header `Content-Type` cung cấp media type để mô tả representation mà server gửi. Browser và các thành phần trung gian có thể dùng thông tin này để chọn parser, renderer, cách xử lý charset và hành vi tải tệp.

Nếu server khai báo sai hoặc bỏ trống Content-Type, browser có thể phải suy đoán loại nội dung. Cơ chế MIME sniffing giúp tương thích với website cũ, nhưng có thể khiến dữ liệu tưởng là văn bản hoặc tệp tải xuống bị diễn giải như nội dung chủ động. Một file do người dùng upload có thể chứa HTML hoặc SVG; nếu server trả file đó với loại nội dung không phù hợp và cho browser hiển thị inline, nội dung có thể chạy trong một origin có quyền truy cập dữ liệu của ứng dụng.

Content-Type vì vậy là một phần của ranh giới bảo mật giữa dữ liệu và mã có thể được browser thực thi. Nó cần đi cùng kiểm tra file upload, header `X-Content-Type-Options: nosniff`, `Content-Disposition` và chiến lược lưu trữ/phân phối tệp.

Sau bài học, bạn có thể:

- Giải thích media type và các thành phần của header Content-Type.
- Phân biệt Content-Type của request và response.
- Mô tả MIME sniffing và giới hạn của `nosniff`.
- Chọn Content-Type phù hợp cho file download.
- Phân biệt `Content-Type` với `Content-Disposition`.
- Xử lý filename an toàn trong response tải xuống.
- Kiểm tra file upload bằng nhiều tín hiệu thay vì tin MIME do client khai báo.
- Phòng ngừa việc HTML, SVG hoặc nội dung chủ động được phục vụ từ origin nhạy cảm.
- Cấu hình server, reverse proxy và object storage để trả metadata nhất quán.
- Kiểm thử hành vi thực tế trong DevTools.

## 2. Media type và cấu trúc Content-Type

Media type có dạng tổng quát:

```http
Content-Type: type/subtype; parameter=value
```

Ví dụ:

```http
Content-Type: text/html; charset=utf-8
Content-Type: application/json
Content-Type: image/png
Content-Type: application/pdf
Content-Type: application/octet-stream
```

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Type | Nhóm media type cấp cao. | `text`, `image`, `application`, `audio`. |
| Subtype | Định dạng cụ thể trong nhóm. | `html`, `png`, `json`, `pdf`. |
| Parameter | Thông tin bổ sung cho representation. | `charset=utf-8`, `boundary=...`. |

Media type được đăng ký và chuẩn hóa trong hệ sinh thái MIME/IANA. Tên type/subtype không phân biệt chữ hoa chữ thường theo quy tắc media type, nhưng nên dùng cách viết chữ thường nhất quán để dễ đọc và so sánh.

### 2.1 Một số media type thường gặp

| Nội dung | Media type thường dùng |
| --- | --- |
| HTML | `text/html` |
| CSS | `text/css` |
| JavaScript | `text/javascript` |
| JSON | `application/json` |
| XML | `application/xml` hoặc media type chuyên biệt |
| Plain text | `text/plain` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| SVG | `image/svg+xml` |
| PDF | `application/pdf` |
| ZIP | `application/zip` |
| Binary không xác định | `application/octet-stream` |

Danh sách này không phải bảng thay thế cho việc nhận diện file. Cùng một phần mở rộng có thể được dùng sai cho nội dung khác; một định dạng cũng có thể có nhiều biến thể.

### 2.2 Structured syntax suffix

Một số media type dùng suffix để mô tả cú pháp chung:

- `application/problem+json` là định dạng JSON theo cấu trúc Problem Details.
- `application/ld+json` là JSON-LD.
- `image/svg+xml` dùng cú pháp XML.

Suffix giúp phần mềm nhận biết cú pháp hoặc họ định dạng, nhưng không tự động chứng minh dữ liệu an toàn. JSON vẫn có thể chứa dữ liệu không tin cậy; SVG có thể chứa tính năng chủ động và cần được xem xét như nội dung web.

## 3. Content-Type của request và response

`Content-Type` mô tả representation trong message body hiện tại. Nó không nói client được phép gửi gì, cũng không xác nhận nội dung có hợp lệ hay không.

### 3.1 Request Content-Type

Khi browser gửi JSON:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"itemId":"item-123","quantity":2}
```

Server có thể dùng header để chọn parser JSON. Nhưng client tự khai báo header; attacker có thể gửi body không phải JSON hoặc cố tình làm parser xử lý dữ liệu độc hại. Server phải parse an toàn, giới hạn kích thước và validate schema.

Khi upload file bằng multipart:

```http
POST /upload HTTP/1.1
Content-Type: multipart/form-data; boundary=----form-boundary
```

Mỗi part có thể có Content-Type riêng do client gửi. Header đó là metadata không đáng tin cậy.

### 3.2 Response Content-Type

Server trả JSON:

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff

{"ok":true}
```

Browser hoặc client HTTP dùng media type để chọn cách xử lý response. Nếu server trả JSON nhưng khai báo `text/html`, browser có thể diễn giải response theo cách không mong muốn trong một số ngữ cảnh.

### 3.3 Không dùng Content-Type thay validation

Header không chứng minh body có đúng định dạng. Ví dụ:

- Request khai báo `image/png` nhưng body là HTML.
- File có tên `report.pdf` nhưng nội dung là ZIP hoặc JavaScript.
- Response khai báo `application/json` nhưng body bị lỗi hoặc chứa dữ liệu không đúng schema.

Server cần kiểm tra nội dung bằng parser/decoder phù hợp, validate cấu trúc và xử lý lỗi. Không quyết định quyền upload chỉ dựa trên MIME type do browser gửi.

## 4. MIME sniffing là gì?

MIME sniffing là quá trình browser suy luận loại nội dung từ bytes của response, header và ngữ cảnh tải. Cơ chế này xuất hiện để hỗ trợ các server cũ gửi thiếu hoặc khai báo sai Content-Type.

Ví dụ server trả nội dung có dấu hiệu HTML nhưng khai báo `text/plain` hoặc không gửi Content-Type. Tùy ngữ cảnh và thuật toán của browser, browser có thể nhận diện nội dung theo bytes thay vì chỉ tin header.

MIME sniffing có ích cho tương thích, nhưng gây rủi ro nếu dữ liệu do người dùng kiểm soát bị browser diễn giải thành HTML hoặc nội dung chủ động.

### 4.1 Vì sao sniffing tạo rủi ro?

Giả sử ứng dụng cho người dùng upload file văn bản và lưu tại:

```text
https://app.example.com/uploads/user-file
```

Attacker upload nội dung HTML nhưng khai báo tên file là `notes.txt`. Nếu server phục vụ file từ origin ứng dụng và browser diễn giải nội dung như HTML, script trong file có thể chạy cùng origin với ứng dụng. Khi đó, hậu quả có thể gồm đọc dữ liệu mà trang có quyền truy cập hoặc thực hiện request thay người dùng.

Rủi ro không chỉ đến từ extension. Nội dung thực tế, Content-Type response, cách browser mở file và origin phục vụ đều ảnh hưởng.

### 4.2 Sniffing phụ thuộc ngữ cảnh

Browser không áp dụng một thuật toán suy đoán duy nhất cho mọi request. Cách xử lý có thể khác giữa:

- Navigation tới một URL.
- Tải tài nguyên bằng `script`.
- Tải stylesheet.
- `fetch` hoặc XHR.
- Hiển thị ảnh, audio hoặc video.
- Tải file với Content-Disposition attachment.

Không suy luận hành vi của navigation chỉ từ quy tắc strict MIME checking cho script/style. Kiểm thử đúng browser, request destination và header thực tế của ứng dụng.

## 5. X-Content-Type-Options: nosniff

Header:

```http
X-Content-Type-Options: nosniff
```

yêu cầu browser không tự suy đoán MIME trong những ngữ cảnh mà chuẩn/browser áp dụng kiểm tra MIME nghiêm ngặt. Đặc biệt, browser hiện đại chặn việc dùng response có MIME type không phù hợp làm script hoặc stylesheet trong các request tương ứng.

### 5.1 nosniff giúp gì?

- Giảm nguy cơ response văn bản bị diễn giải thành script/style khi được tải như tài nguyên đó.
- Làm server phải khai báo Content-Type chính xác cho script và stylesheet.
- Giảm một số lớp tấn công dựa trên MIME confusion.

### 5.2 nosniff không làm gì?

- Không xác thực bytes của file upload.
- Không biến HTML hoặc SVG độc hại thành file an toàn.
- Không thay thế Content-Disposition attachment.
- Không thay thế CSP, output encoding hoặc authorization.
- Không bảo đảm mọi kiểu navigation đều bị ép thành download.
- Không ngăn XSS đã chạy trong trang.

Hãy triển khai nosniff như một lớp bảo vệ mặc định, đồng thời vẫn đặt đúng Content-Type và quyết định rõ file nào được hiển thị inline.

## 6. Content-Type và Content-Disposition

Hai header này giải quyết hai câu hỏi khác nhau:

| Header | Câu hỏi |
| --- | --- |
| Content-Type | Nội dung là định dạng gì? |
| Content-Disposition | Browser nên hiển thị nội dung inline hay đề nghị tải xuống? |

Ví dụ:

```http
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
X-Content-Type-Options: nosniff
```

`Content-Type` mô tả PDF. `Content-Disposition: attachment` yêu cầu browser xử lý response như tệp đính kèm để tải xuống trong các browser hỗ trợ.

### 6.1 inline và attachment

- `inline` cho phép browser hiển thị nội dung nếu browser hỗ trợ media type đó.
- `attachment` yêu cầu browser tải nội dung xuống thay vì hiển thị inline.

Không coi `application/octet-stream` là cách duy nhất để buộc download. Dùng Content-Disposition để thể hiện rõ disposition.

### 6.2 application/octet-stream

`application/octet-stream` là media type chung cho dữ liệu nhị phân không có định dạng cụ thể hoặc không muốn khai báo định dạng chi tiết. Browser thường có xu hướng tải loại nội dung này, nhưng hành vi chính xác còn phụ thuộc Content-Disposition và browser.

Không đổi mọi response thành octet-stream một cách máy móc. Làm vậy có thể phá chức năng preview hợp lệ, gây khó cho client và không giải quyết việc server lưu file độc hại. Hãy chọn type dựa trên nội dung đã xác minh và policy hiển thị.

## 7. Chọn Content-Type cho download

Khi cung cấp file download, server nên xác định media type từ metadata đáng tin cậy được tạo sau quá trình upload/validation. Không chỉ lấy extension từ filename người dùng gửi lên.

Ví dụ:

| File đã xác minh | Content-Type | Disposition gợi ý |
| --- | --- | --- |
| PDF | `application/pdf` | `attachment` nếu không cần preview |
| PNG | `image/png` | `attachment` khi tải; inline chỉ khi đã quyết định an toàn |
| CSV | `text/csv; charset=utf-8` | Thường là `attachment` |
| Plain text | `text/plain; charset=utf-8` | `attachment` nếu là tài liệu do người dùng tải lên |
| ZIP | `application/zip` | `attachment` |
| Định dạng không xác định | `application/octet-stream` | `attachment` |
| HTML do người dùng upload | Không phục vụ inline từ origin ứng dụng | Tải xuống hoặc phân phối từ origin tách biệt theo policy |

### 7.1 Đừng để extension quyết định một mình

Nếu file tên `photo.png` nhưng bytes không phải PNG, server không nên trả `image/png` chỉ vì phần mở rộng. Nếu server đã xác minh nội dung là PNG, metadata tin cậy mới có thể dùng để tạo response header.

### 7.2 File không rõ định dạng

Nếu không nhận diện được định dạng, có thể trả `application/octet-stream` cùng `Content-Disposition: attachment`. Tuy nhiên, ứng dụng vẫn cần policy về kích thước, lưu trữ, malware scanning và quyền tải. Không xác định được MIME không đồng nghĩa file vô hại.

## 8. Filename trong Content-Disposition

Ví dụ đơn giản:

```http
Content-Disposition: attachment; filename="report.pdf"
```

Filename được browser dùng làm gợi ý tên file. Giá trị này không được xem là đường dẫn mà server có thể tin cậy.

### 8.1 filename và filename*

RFC 6266 định nghĩa tham số filename và filename*. `filename` tương thích rộng với tên ASCII; `filename*` hỗ trợ encoding theo RFC 5987, thường hữu ích cho tên UTF-8:

```http
Content-Disposition: attachment;
 filename="report.pdf";
 filename*=UTF-8''b%C3%A1o-c%C3%A1o-th%C3%A1ng-11.pdf
```

Khi gửi cả hai, browser hỗ trợ filename* thường ưu tiên giá trị đó. Dùng thư viện chuẩn của framework để sinh Content-Disposition thay vì tự nối chuỗi.

### 8.2 Không tin filename do người dùng gửi

Filename có thể chứa:

- Dấu phân cách thư mục như `/` hoặc `\`.
- Ký tự điều khiển hoặc CR/LF.
- Tên gây nhầm lẫn với extension khác.
- Tên rất dài hoặc Unicode khó hiển thị.
- Ký tự bidi làm đảo hướng hiển thị.

Tạo một download name an toàn ở server: loại bỏ path component, control character và dấu phân cách; giới hạn độ dài; chọn extension từ định dạng đã xác minh; encode header theo thư viện tin cậy.

### 8.3 Filename không phải nơi lưu trữ

Không dùng filename từ request làm filesystem path. Tạo storage key ngẫu nhiên hoặc ID nội bộ, lưu original filename như metadata đã làm sạch. Khi tải, kiểm tra authorization và tạo Content-Disposition từ tên hiển thị an toàn.

## 9. File upload: Content-Type do client khai báo không đáng tin

Trong multipart upload, browser thường gửi tên file và Content-Type của từng part:

```http
Content-Disposition: form-data; name="file"; filename="avatar.png"
Content-Type: image/png

...file bytes...
```

Attacker có thể tự tạo request và khai báo bất kỳ MIME type nào. Vì vậy:

- Không tin `Content-Type` trong multipart.
- Không tin extension.
- Không tin filename.
- Không tin `accept` attribute ở input file; nó chỉ hỗ trợ giao diện chọn file.
- Không tin `Content-Length` do client gửi như giới hạn tài nguyên duy nhất.

Server phải kiểm tra bytes và xử lý file trong một pipeline riêng.

## 10. Quy trình xác minh file upload

Một pipeline upload an toàn thường gồm:

1. Xác thực người dùng và kiểm tra quyền upload vào đúng resource.
2. Giới hạn kích thước, số file, tốc độ và tổng quota.
3. Lưu tạm vào vùng cách ly, không public trực tiếp.
4. Kiểm tra tên file và loại bỏ path/control character.
5. Nhận diện định dạng bằng magic bytes và parser/decoder phù hợp.
6. Parse toàn bộ cấu trúc theo định dạng; từ chối file lỗi hoặc vượt giới hạn.
7. Quét malware hoặc áp dụng Content Disarm and Reconstruction (CDR) khi phù hợp.
8. Re-encode ảnh/media sang định dạng chuẩn nếu use case cho phép.
9. Lưu metadata đã xác minh và storage key nội bộ.
10. Chỉ publish sau khi pipeline hoàn tất; phục vụ qua download handler có authorization.

### 10.1 Magic bytes chỉ là một tín hiệu

Magic bytes là một số byte đầu hoặc cấu trúc đặc trưng giúp nhận diện định dạng. Ví dụ PNG có signature cố định; PDF thường bắt đầu bằng `%PDF-`.

Nhưng kiểm tra vài byte đầu không đủ chứng minh file hợp lệ hoặc an toàn. File có thể bị polyglot, dữ liệu có thể chứa payload ở phần khác, hoặc parser có lỗ hổng. Kết hợp signature với parser thực sự, giới hạn tài nguyên và kiểm tra cấu trúc.

### 10.2 Extension allowlist và MIME allowlist

Allowlist extension/MIME giúp thu hẹp loại file được chấp nhận, nhưng phải kiểm tra cả nội dung. Ví dụ ứng dụng avatar có thể chỉ nhận PNG/JPEG/WebP đã decode thành công; không nhận SVG nếu không có nhu cầu và pipeline xử lý an toàn.

### 10.3 Giới hạn parser và archive

File nén có thể giải nén thành dữ liệu lớn hơn nhiều lần kích thước upload. PDF, ảnh và media có thể khai thác bug parser hoặc gây tiêu thụ CPU/memory.

Đặt giới hạn:

- Kích thước upload và kích thước sau giải nén.
- Số lượng entry trong archive.
- Độ sâu thư mục và compression ratio.
- Thời gian parse, số pixel và dimension ảnh.
- Bộ nhớ và CPU của worker xử lý.
- Loại file lồng nhau được chấp nhận.

Không giải nén archive trực tiếp vào thư mục public hoặc theo path entry chưa được chuẩn hóa.

## 11. Phục vụ file do người dùng upload

Tách nơi lưu trữ file khỏi web root hoặc static asset directory của ứng dụng. Dùng storage key ngẫu nhiên và route download kiểm tra quyền.

Với file không tin cậy:

- Ưu tiên `Content-Disposition: attachment`.
- Đặt Content-Type đã xác minh; nếu không xác định, dùng `application/octet-stream`.
- Thêm `X-Content-Type-Options: nosniff`.
- Tránh phục vụ HTML/SVG do người dùng upload inline từ origin chứa session của ứng dụng.
- Cân nhắc phục vụ nội dung không tin cậy từ một registrable domain/site riêng biệt, không chia sẻ cookie với ứng dụng.
- Dùng CSP/sandbox phù hợp nếu sản phẩm có tính năng preview.

### 11.1 Origin riêng cho nội dung không tin cậy

Nếu sản phẩm cần preview HTML hoặc SVG, nên xem xét một origin riêng không có cookie/session của ứng dụng chính. Không chỉ dùng subdomain rồi chia sẻ cookie Domain rộng; cookie host-only và site boundary cần được thiết kế rõ ràng.

Một origin riêng giảm quyền mà nội dung upload có thể tiếp cận, nhưng vẫn cần sandbox, CSP, authorization và chính sách tải xuống. Nội dung active không trở nên an toàn chỉ vì nằm trên subdomain khác nếu cookie hoặc trust relationship được chia sẻ.

### 11.2 Preview ảnh

Với ảnh raster, server có thể decode rồi re-encode để loại metadata hoặc cấu trúc bất thường, sau đó phục vụ định dạng được hỗ trợ. SVG là XML có khả năng chứa nội dung active; không xử lý như PNG/JPEG. Nếu không cần SVG, loại bỏ khỏi allowlist hoặc rasterize bằng pipeline chuyên biệt.

## 12. Ví dụ download an toàn với Express

Ví dụ minh họa dùng metadata do pipeline upload đã xác minh. Thư viện `content-disposition` xử lý encoding và quoting của filename:

```javascript
import contentDisposition from "content-disposition";

app.get("/files/:fileId/download", requireUser, async (req, res, next) => {
  try {
    const file = await findFileById(req.params.fileId);

    if (!file || !canReadFile(req.user, file)) {
      return res.sendStatus(404);
    }

    const allowedTypes = new Set([
      "application/pdf",
      "image/png",
      "image/jpeg",
      "text/csv; charset=utf-8",
      "application/zip"
    ]);

    const mediaType = allowedTypes.has(file.verifiedContentType)
      ? file.verifiedContentType
      : "application/octet-stream";

    res.setHeader("Content-Type", mediaType);
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader(
      "Content-Disposition",
      contentDisposition(file.safeDownloadName, { type: "attachment" })
    );
    res.setHeader("Cache-Control", "private, no-store");

    const stream = await openPrivateStorageStream(file.storageKey);
    stream.on("error", next);
    stream.pipe(res);
  } catch (error) {
    next(error);
  }
});
```

Các hàm `findFileById`, `canReadFile` và `openPrivateStorageStream` đại diện cho tầng dữ liệu của ứng dụng. Chúng phải dùng ID nội bộ, kiểm tra quyền server-side và không ghép path từ input người dùng.

### 12.1 Không để người dùng chọn Content-Type response

Không nhận query như `?contentType=text/html` rồi phản chiếu trực tiếp vào response. Content-Type phải đến từ metadata đã xác minh và policy của server.

### 12.2 Xử lý stream lỗi

Nếu storage stream lỗi sau khi response đã gửi headers/body, không thể đổi status code thành một response JSON bình thường. Log lỗi bằng request ID, không ghi URL có secret hoặc storage credential; đóng stream đúng cách và để middleware xử lý theo trạng thái response.

## 13. Cấu hình Nginx và reverse proxy

Có thể thêm `nosniff` mặc định ở lớp web server:

```nginx
add_header X-Content-Type-Options "nosniff" always;
```

`always` giúp header được thêm cả với nhiều response lỗi. Kiểm tra cấu hình inheritance và các location block để chắc header không bị bỏ ở một route cụ thể.

### 13.1 default_type không thay thế metadata chính xác

Nginx có `default_type` cho response mà nó không xác định được type từ mapping. Giá trị mặc định thường là `application/octet-stream`. Điều này hữu ích như fallback nhưng không thay thế việc đặt type đúng cho HTML, CSS, JavaScript, JSON và các file download đã xác minh.

### 13.2 Kiểm tra MIME mapping

Static server thường suy ra media type từ extension thông qua file mapping. Nếu file có extension sai hoặc người dùng có thể kiểm soát extension, mapping có thể tạo response Content-Type không phù hợp với bytes. Với file upload, nên dùng download handler có metadata đã xác minh thay vì public static mapping.

### 13.3 Tránh header bị ghi đè

Kiểm tra response cuối sau CDN/proxy. Upstream có thể trả một Content-Type, proxy có thể thay hoặc xóa nó, và CDN có thể lưu metadata cũ. Kiểm thử response mà browser thực sự nhận, không chỉ cấu hình ở một lớp.

## 14. Object storage và CDN

Object storage thường lưu metadata Content-Type và Content-Disposition cùng object. Khi upload, metadata có thể được lấy từ request của client nếu backend không kiểm soát. Khi download, CDN có thể phát lại metadata này.

Quy trình an toàn:

- Backend nhận file và xác minh định dạng.
- Backend đặt metadata Content-Type dựa trên kết quả xác minh.
- Đặt Content-Disposition attachment cho file không tin cậy.
- Đặt nosniff ở response layer hỗ trợ.
- Giới hạn quyền đọc/ghi object và thời hạn signed URL.
- Kiểm tra cache key và response header override ở CDN.

### 14.1 Metadata upload không được tin mặc định

Một object có thể được upload với metadata `text/html` dù bytes là một file khác, hoặc ngược lại. Nếu bucket public/static phục vụ trực tiếp, browser có thể nhận metadata đó mà không qua download handler của ứng dụng.

Không cho client tự chọn Content-Type metadata khi upload vào public bucket. Backend cần xác minh, ghi metadata mới và chỉ publish object sau khi xử lý.

### 14.2 Cache và thay đổi metadata

Khi sửa Content-Type hoặc Content-Disposition của object, cache CDN cũ có thể tiếp tục trả header trước đó. Invalidate cache hoặc version object phù hợp, và xác nhận response mới ở edge.

## 15. Charset và text content

Với text, charset mô tả cách giải mã bytes thành ký tự. Ví dụ:

```http
Content-Type: text/html; charset=utf-8
Content-Type: text/plain; charset=utf-8
Content-Type: text/csv; charset=utf-8
```

UTF-8 là lựa chọn phổ biến cho nội dung web mới. Server cần bảo đảm bytes thực sự được encode theo charset đã khai báo. Khai báo UTF-8 nhưng gửi bytes theo encoding khác có thể gây lỗi hiển thị hoặc parser disagreement.

### 15.1 Không gắn charset tùy tiện cho binary

PNG, JPEG, PDF và ZIP là định dạng binary; không thêm `charset=utf-8` vào media type của chúng. Charset có ý nghĩa với các loại representation dạng text.

### 15.2 CSV và spreadsheet formula

Content-Type `text/csv` chỉ mô tả định dạng trao đổi. Nó không ngăn spreadsheet diễn giải cell bắt đầu bằng `=`, `+`, `-` hoặc `@` thành công thức khi người dùng mở file. Nếu export dữ liệu không tin cậy cho spreadsheet, cần xử lý CSV/formula injection riêng; Content-Type không giải quyết vấn đề này.

## 16. JSON API và MIME type chính xác

JSON response nên dùng:

```http
Content-Type: application/json; charset=utf-8
X-Content-Type-Options: nosniff
```

Không trả JSON dưới `text/html` để tận dụng browser rendering. Không phục vụ dữ liệu JSON nhạy cảm dưới dạng HTML hoặc JSONP chỉ để hỗ trợ client cũ.

### 16.1 JSON không phải HTML

Một API trả JSON nên được tiêu thụ qua `fetch`/HTTP client và parse JSON. Nếu nội dung JSON chứa chuỗi do người dùng kiểm soát, frontend vẫn phải encode khi render vào HTML/DOM. Media type đúng không ngăn DOM XSS do client chèn chuỗi không an toàn.

### 16.2 Không dùng Content-Type như CORS hoặc authorization

Khai báo `application/json` không cho phép hay cấm origin khác đọc response. CORS và authorization là các lớp riêng. API phải kiểm tra credential và quyền; browser áp dụng CORS cho việc chia sẻ response giữa origin.

## 17. Các file cần thận trọng khi preview inline

| Định dạng | Đặc điểm | Khuyến nghị |
| --- | --- | --- |
| HTML | Nội dung active, script và form. | Không inline từ origin chính nếu do người dùng upload. |
| SVG | XML có khả năng chứa script/links và nội dung active tùy ngữ cảnh. | Không coi như ảnh raster; sanitize/rasterize hoặc tách origin. |
| XML | Có parser và tính năng phụ thuộc implementation; có thể có external entity trong parser server. | Dùng parser an toàn, disable external entity khi không cần. |
| PDF | Browser có built-in viewer và active feature tùy trình xem. | Dùng attachment hoặc preview trong sandbox/origin phù hợp. |
| JavaScript | Có thể được browser thực thi như script. | Không phục vụ file upload dưới script MIME từ origin ứng dụng. |
| CSS | Có thể tải tài nguyên và ảnh hưởng trang nếu được dùng như stylesheet. | Không cho upload CSS rồi dùng trong trang tin cậy. |
| Archive | Có thể chứa path traversal hoặc archive bomb khi giải nén. | Kiểm tra entry, kích thước, path và quota trước giải nén. |
| HTML disguised as image | Header/extension không khớp bytes. | Verify bytes và không phục vụ inline theo extension. |

## 18. Kiểm thử Content-Type trong DevTools

Mở DevTools → Network và chọn request download/upload:

1. Xác nhận URL và status của response.
2. Kiểm tra Response Headers: Content-Type, Content-Disposition và X-Content-Type-Options.
3. Kiểm tra Content-Type của multipart request và nhớ rằng giá trị đó do client khai báo.
4. Xem Preview/Response để biết browser đang nhận bytes gì.
5. Kiểm tra response sau CDN/proxy có giữ đúng header hay không.
6. Thử file hợp lệ, file sai extension và file không nhận diện.
7. Mở trực tiếp URL file và so sánh navigation với download attachment.
8. Thử browser mục tiêu để xác nhận hành vi tải/preview thực tế.

### 18.1 Ma trận kiểm thử

| Ca | Bytes | Header response | Disposition | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| T1 | PDF hợp lệ | `application/pdf` + nosniff | attachment | Browser tải PDF. |
| T2 | PNG hợp lệ | `image/png` + nosniff | attachment | Browser tải PNG. |
| T3 | HTML upload | `application/octet-stream` + nosniff | attachment | Browser tải file, không render HTML từ origin ứng dụng. |
| T4 | HTML upload | `text/html` | inline | Không dùng cấu hình này cho nội dung không tin cậy; xác nhận nguy cơ trong lab cô lập. |
| T5 | Bytes không phải PNG | Metadata `image/png` | inline | Pipeline phải từ chối hoặc sửa metadata trước publish. |
| T6 | File không xác định | `application/octet-stream` + nosniff | attachment | Tải xuống như binary. |
| T7 | File HTML khai báo `text/plain` | `text/plain` + nosniff | inline | Không suy ra an toàn; kiểm tra navigation/sniffing trên browser mục tiêu. |
| T8 | Script bytes | `text/plain` | script request | Browser hiện đại phải áp dụng strict MIME checking cho script và chặn mismatch. |

### 18.2 Quan sát Console

Khi script hoặc stylesheet có MIME type không phù hợp, browser có thể phát thông báo strict MIME type checking. Ghi lại browser/version, request destination và response headers. Đừng kết luận chỉ từ một thông báo console rằng mọi navigation/file download đều được bảo vệ tương tự.

## 19. Lab: Content-Type và nosniff

Lab chạy local với nội dung giả. Không dùng website production hoặc file người dùng thật.

### 19.1 Tạo server HTTP thử nghiệm

Tạo file `server.mjs`:

```javascript
import http from "node:http";

const server = http.createServer((req, res) => {
  if (req.url === "/wrong-type") {
    res.writeHead(200, {
      "Content-Type": "text/plain"
    });
    res.end("<h1>HTML bytes with a text/plain label</h1>");
    return;
  }

  if (req.url === "/download") {
    res.writeHead(200, {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": "attachment; filename=\"demo.txt\"",
      "X-Content-Type-Options": "nosniff"
    });
    res.end("Demo download content");
    return;
  }

  if (req.url === "/json") {
    res.writeHead(200, {
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff"
    });
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  res.writeHead(404, {
    "Content-Type": "text/plain; charset=utf-8",
    "X-Content-Type-Options": "nosniff"
  });
  res.end("Not found");
});

server.listen(8080, "127.0.0.1", () => {
  console.log("Open http://127.0.0.1:8080");
});
```

Chạy:

```bash
node server.mjs
```

### 19.2 Quan sát response

Mở:

- `http://127.0.0.1:8080/wrong-type`
- `http://127.0.0.1:8080/download`
- `http://127.0.0.1:8080/json`

So sánh Content-Type, Content-Disposition và hành vi browser. Kết quả của `wrong-type` có thể phụ thuộc MIME sniffing và ngữ cảnh navigation; không dùng nó làm cơ chế bảo vệ.

### 19.3 Thử strict MIME checking cho script

Trong một trang HTML lab riêng, tạo một script request trỏ tới endpoint trả JavaScript bytes nhưng khai báo `text/plain` cùng `nosniff`. Quan sát browser chặn script do MIME mismatch. Sau đó đổi response sang `text/javascript` và so sánh.

Không cần đưa payload độc hại vào lab; một dòng JavaScript vô hại là đủ để thấy strict MIME checking.

## 20. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tin Content-Type do client upload gửi | File bytes có thể không đúng loại khai báo. | Detect bằng signature và parse/validate nội dung. |
| Chỉ kiểm tra extension | File HTML có thể mang tên `.png` hoặc `.txt`. | Kết hợp extension allowlist, signature và parser. |
| Phục vụ upload từ origin chính | Nội dung active có thể chạy với quyền của ứng dụng. | Attachment hoặc origin riêng cho untrusted content. |
| Bỏ nosniff | Tăng khả năng browser sniff MIME trong một số ngữ cảnh. | Thêm `X-Content-Type-Options: nosniff`. |
| Nghĩ nosniff ép mọi file thành download | Navigation không được chuyển thành attachment chỉ nhờ header này. | Dùng Content-Disposition attachment. |
| Dùng octet-stream cho mọi response | Client mất MIME metadata đúng và hành vi có thể khó đoán. | Dùng verified media type, fallback khi không xác định. |
| Ghép filename trực tiếp vào header | CR/LF, path và encoding có thể gây lỗi/header injection. | Dùng thư viện Content-Disposition và safe filename. |
| Cho client đặt metadata object storage | CDN có thể phát sai Content-Type. | Backend xác minh và đặt metadata trước publish. |
| Preview SVG như ảnh raster | SVG có thể chứa nội dung active. | Sanitize/rasterize hoặc cô lập origin. |
| Chỉ kiểm thử local upstream | CDN/proxy có thể ghi đè header. | Kiểm tra response cuối browser nhận. |

## 21. Checklist bảo mật Content-Type

- [ ] Response có Content-Type chính xác theo bytes/metadata đã xác minh.
- [ ] Text response có charset phù hợp, thường là UTF-8.
- [ ] Binary không bị gắn charset text không phù hợp.
- [ ] Response có `X-Content-Type-Options: nosniff`.
- [ ] File không tin cậy dùng `Content-Disposition: attachment` theo policy.
- [ ] Filename được làm sạch và encode bằng thư viện chuẩn.
- [ ] Content-Type trong multipart upload được xem là input không tin cậy.
- [ ] Extension, magic bytes và parser validation được kết hợp.
- [ ] Upload được lưu cách ly trước khi scan/validate hoàn tất.
- [ ] Archive, image và document parser có giới hạn tài nguyên.
- [ ] HTML/SVG do người dùng upload không được inline từ origin ứng dụng chính.
- [ ] Object storage metadata và CDN response header đã được kiểm tra.
- [ ] Authorization được kiểm tra trước khi download.
- [ ] Cache policy phù hợp với file nhạy cảm.
- [ ] DevTools đã xác nhận header ở response cuối.
- [ ] Đã kiểm thử MIME mismatch, nosniff và attachment trên browser mục tiêu.

## 22. Câu hỏi tự kiểm tra

1. Content-Type mô tả điều gì trong HTTP message?
2. Request Content-Type do browser gửi có thể được tin cậy không?
3. MIME sniffing tồn tại vì lý do gì và tạo ra rủi ro nào?
4. `X-Content-Type-Options: nosniff` bảo vệ những ngữ cảnh nào?
5. Vì sao nosniff không thay thế Content-Disposition attachment?
6. Content-Type khác Content-Disposition ở điểm nào?
7. Vì sao `application/octet-stream` không tự xác minh file an toàn?
8. Vì sao extension và magic bytes riêng lẻ chưa đủ để xác thực file?
9. Tại sao HTML/SVG upload không nên được phục vụ inline từ origin ứng dụng?
10. `filename*` hỗ trợ mục đích gì?
11. Nginx `$uri`/MIME mapping có thể gây vấn đề gì với file upload?
12. Những header nào cần kiểm tra trong DevTools khi điều tra lỗi download?

## 23. Tổng kết

Content-Type mô tả media type của representation để browser và client chọn cách diễn giải nội dung. Khi server bỏ trống hoặc khai báo sai, MIME sniffing có thể tạo ra hành vi khác với ý định của ứng dụng. `X-Content-Type-Options: nosniff` giúp browser áp dụng MIME checking nghiêm ngặt trong các ngữ cảnh như script và stylesheet, nhưng không xác minh file upload và không tự ép mọi navigation thành download.

Khi tải file, dùng Content-Type dựa trên định dạng đã xác minh, `Content-Disposition: attachment` cho nội dung không tin cậy và filename được tạo an toàn. Khi upload, không tin MIME type, extension hoặc filename do client gửi; cần kiểm tra signature, parse cấu trúc, giới hạn tài nguyên, quét và lưu cách ly trước khi publish. HTML/SVG và các nội dung active cần được cô lập khỏi origin ứng dụng hoặc chỉ preview qua pipeline an toàn.

Kiểm tra response cuối cùng tại browser vì proxy, CDN và object storage có thể thay đổi metadata. Content-Type, nosniff, Content-Disposition, validation upload, authorization và origin isolation phối hợp với nhau để giữ ranh giới giữa dữ liệu tải xuống và nội dung browser có thể thực thi.
