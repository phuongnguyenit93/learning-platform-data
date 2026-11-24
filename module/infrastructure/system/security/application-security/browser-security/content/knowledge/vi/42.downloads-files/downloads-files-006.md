# File origin

## 1. File origin là gì?

**File origin** là cách browser xác định ranh giới bảo mật cho nội dung được mở từ một file URL, thường có dạng `file:///...`. Chủ đề này cũng liên quan đến origin của nội dung được tạo từ file download, `blob:` URL, `data:` URL và tài liệu được nhúng trong iframe.

Với trang web HTTP(S), origin thường là bộ ba **scheme + host + port**. Ví dụ `https://app.example.com:443`. Browser dùng origin để áp dụng Same-Origin Policy (SOP), kiểm soát JavaScript đọc tài nguyên, truy cập DOM giữa frame và một số quyền đối với storage.

File trên đĩa không tự có origin HTTP của trang đã tải nó xuống. Khi người dùng mở file HTML đã download, browser xử lý nó theo scheme `file:` và chính sách local-file của browser. Các browser không có cùng một hành vi tương thích cho `file:` origin; không nên dựa vào việc hai file cùng thư mục được xem là same-origin.

Điểm cần nhớ là **đường dẫn file không phải một origin đáng tin**. Không dùng `file://` để chia sẻ dữ liệu giữa các trang, không mở rộng CORS cho `Origin: null` một cách rộng rãi, và không xem file đã download là dữ liệu thụ động chỉ vì nó nằm trên máy người dùng. HTML, SVG, XML hoặc file có nội dung chủ động có thể chạy code khi được mở hoặc preview.

Bài học này giải thích origin của file, mối quan hệ giữa file download và browser origin, các scheme đặc biệt, CORS với opaque origin, MIME/download headers, Blob URL, preview file và kiểm thử an toàn.

### Kết quả học tập

Sau bài này, người học có thể:

1. Giải thích tuple origin của HTTP(S) và sự khác biệt giữa origin với site.
2. Mô tả giới hạn và tính khác biệt giữa các browser đối với `file:` origin.
3. Phân biệt origin của trang download với origin của file khi được mở.
4. Giải thích vì sao `Origin: null` không đại diện cho một origin đáng tin duy nhất.
5. Phân biệt origin của `blob:`, `data:`, `about:blank` và sandboxed iframe.
6. Cấu hình Content-Disposition, Content-Type và X-Content-Type-Options phù hợp.
7. Tránh thực thi HTML/SVG không tin cậy trong origin ứng dụng.
8. Tạo và thu hồi Blob URL đúng vòng đời.
9. Xử lý file upload bằng File API mà không giả định được quyền đọc filesystem tùy ý.
10. Kiểm thử file origin và download flow trong browser mục tiêu.

## 2. Origin của web và file

### 2.1. Tuple origin

Với các URL web thông thường, origin được xác định bởi scheme, host và port:

| URL | Origin |
| --- | --- |
| `https://app.example.com/profile` | `https://app.example.com` |
| `https://app.example.com:8443/a` | `https://app.example.com:8443` |
| `http://app.example.com` | `http://app.example.com` |
| `https://app.example.com:443` | `https://app.example.com` |

Path, query và fragment không thuộc tuple origin. Hai trang có path khác nhau nhưng cùng scheme/host/port vẫn same-origin.

### 2.2. Origin khác site

Origin và site là hai khái niệm riêng. Origin xét scheme, host và port. Site trong các chính sách như SameSite cookie thường dựa trên scheme và registrable domain (cùng một số quy tắc của public suffix). Ví dụ `https://app.example.com` và `https://api.example.com` khác origin nhưng thường cùng schemeful site.

Không dùng khái niệm same-site để suy ra JavaScript có thể đọc response hoặc DOM. SOP vẫn áp dụng theo origin.

### 2.3. File URL không phải tuple web thông thường

Một file URL thường trông như:

```text
file:///Users/alice/Downloads/report.html
file:///C:/Users/Alice/Downloads/report.html
file://server/share/report.html
```

Không có host/port web thông thường tương đương cho mọi file URL. Thuật toán origin của scheme `file:` có những phần implementation-defined; các browser có thể áp dụng chính sách riêng để hạn chế truy cập file local.

Nhiều browser hiện đại xử lý file document như opaque origin trong nhiều ngữ cảnh. Một số hành vi tương thích cũ có thể cho phép tương tác giữa file trong cùng thư mục hoặc cùng vùng theo cách riêng. Hành vi này có thể thay đổi theo browser, phiên bản, cấu hình và platform.

Vì vậy:

- Không giả định hai file cùng thư mục là same-origin.
- Không giả định hai file khác thư mục chắc chắn bị cô lập giống nhau trên mọi browser.
- Không dùng local file làm cơ chế xác thực hoặc phân quyền.
- Không dựa vào kết quả thử nghiệm trên một browser để thiết kế quyền truy cập file cho mọi browser.
- Khi cần trao đổi dữ liệu giữa trang và tài nguyên, dùng HTTP(S) origin được kiểm soát hoặc cơ chế file picker có sự đồng ý của người dùng.

### 2.4. Opaque origin

Opaque origin là origin duy nhất, không được biểu diễn bằng tuple scheme/host/port thông thường. Khi serialize trong một số API/header, opaque origin thường được biểu diễn là chuỗi `null`. Chuỗi này không phải tên miền hoặc một origin có thể allowlist như `https://app.example.com`.

Opaque origin được dùng trong một số ngữ cảnh cần cô lập tài liệu, ví dụ `data:` URL và sandboxed document không có `allow-same-origin`. Không nên suy luận hai opaque origin có cùng chuỗi serialize `null` thì chúng là same-origin; mỗi opaque origin là một định danh riêng.

## 3. Browser xử lý file:// như thế nào?

### 3.1. Mở file local

Khi người dùng mở file HTML bằng browser, URL thường bắt đầu bằng `file:///`. Browser hiển thị nội dung theo chính sách local-file của nó. Trang đó không trở thành `https://app.example.com` chỉ vì file từng được tải từ website đó.

Ví dụ, người dùng tải `report.html` từ ứng dụng rồi mở bằng double-click. Browser mở một file URL local. Các cookie của `app.example.com` không tự động trở thành cookie của `file:`; JavaScript trong file cũng không được cấp quyền đọc tùy ý cookie hoặc storage của website đã tải nó.

### 3.2. Local file access bị giới hạn

Browser thường hạn chế một file HTML đọc file khác hoặc truy cập filesystem tùy ý. Các giới hạn cụ thể khác nhau theo browser và API. Trang `file:` không có quyền tổng quát để đọc mọi file trong Downloads, Documents hoặc ổ đĩa.

Một số API cho phép người dùng chủ động chọn file hoặc thư mục, ví dụ `<input type="file">` hoặc File System Access API ở browser hỗ trợ. Đây là quyền theo thao tác/permission của người dùng và cần xử lý an toàn; nó không đồng nghĩa trang có quyền đọc toàn bộ filesystem.

### 3.3. Không chạy ứng dụng web bằng cách mở index.html từ đĩa

Nếu ứng dụng cần fetch API, module JavaScript, worker, CORS hoặc service worker, mở trực tiếp `index.html` từ `file:` có thể gây lỗi do local-file origin và browser policy. Chạy development server trên `http://localhost` hoặc HTTPS local phù hợp. Không tắt browser security flags để làm lab hoạt động.

## 4. Origin của file đã download

### 4.1. Download không kế thừa origin của trang gọi

Giả sử người dùng ở `https://app.example.com` nhấn Download và nhận `invoice.pdf`. Response tải xuống được server trả qua HTTP(S), nhưng khi file được lưu xuống đĩa và mở sau đó, nó được xử lý theo loại file và môi trường mở file. Nó không giữ nguyên origin `https://app.example.com` như một document đang chạy trong trang.

Download là một hành động nhận bytes. Origin của request/response trong lúc tải, vị trí file trên filesystem và origin của document khi file được mở là ba khái niệm cần phân biệt.

### 4.2. Content-Disposition attachment

Server có thể yêu cầu browser tải file thay vì hiển thị inline:

```http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
X-Content-Type-Options: nosniff
Cache-Control: private, no-store
```

`Content-Disposition: attachment` hướng browser xử lý response như một download. Nó không bảo đảm file vô hại, không ép hệ điều hành mở file bằng một ứng dụng an toàn và không ngăn người dùng tự mở file sau khi tải.

Thuộc tính `download` trên thẻ anchor là gợi ý cho browser, không phải ranh giới bảo mật; hành vi có thể khác với URL cross-origin. Với download từ server, hãy cấu hình `Content-Disposition: attachment` ở response. Nếu muốn browser hiển thị inline, server dùng `inline` hoặc không đặt attachment tùy loại response. Với file người dùng tải lên hoặc nội dung không tin cậy, tránh inline active content trên origin chính của ứng dụng.

### 4.3. Tên file và header injection

Tên file do người dùng cung cấp không được chèn thẳng vào header. Cần loại bỏ CR/LF, ký tự điều khiển, path separator và chuỗi có thể phá cấu trúc header. Dùng thư viện/framework hỗ trợ Content-Disposition và mã hóa filename/filename* theo chuẩn.

Ví dụ minh họa tên file đã được server chuẩn hóa:

```http
Content-Disposition: attachment; filename="report-2026.pdf"; filename*=UTF-8''report-2026.pdf
```

Không tin extension hoặc MIME type do client upload khai báo. Server cần tạo tên file lưu trữ nội bộ và áp dụng policy download riêng.

## 5. Các scheme đặc biệt và origin của chúng

### 5.1. blob: URL

`blob:` URL được tạo từ Blob hoặc MediaSource, thường qua `URL.createObjectURL()`. Origin của blob URL thông thường gắn với origin của môi trường tạo ra nó. Ví dụ trang `https://app.example.com` tạo blob URL thì blob document thường mang origin của ứng dụng đó.

Nếu Blob URL được tạo trong một opaque-origin context, URL có thể được serialize với phần origin là `null`. Điều đó vẫn không biến mọi URL `blob:null` thành cùng một origin; nguồn tạo và định danh opaque origin vẫn quan trọng.

Điều này rất quan trọng: Blob URL không phải sandbox tự động. Nếu ứng dụng tạo Blob có MIME `text/html` từ nội dung không tin cậy rồi điều hướng browser tới blob URL, script trong HTML có thể chạy với origin của trang tạo Blob.

### 5.2. data: URL

`data:` URL nhúng nội dung trực tiếp trong URL. Document được nạp từ `data:` thường có opaque origin. Không dùng `data:` như cơ chế chia sẻ same-origin hoặc để né CORS.

### 5.3. about:blank

Một initial `about:blank` document được tạo từ một browsing context có thể kế thừa origin của creator/opener theo quy tắc HTML. Vì vậy, `about:blank` không mặc nhiên là opaque origin trong mọi tình huống.

Nếu mở cửa sổ mới bằng `window.open()` và ghi nội dung vào document, hãy xem xét quan hệ opener, `noopener` và việc dữ liệu có không tin cậy hay không. Không coi `about:blank` là nơi cô lập nội dung.

### 5.4. iframe srcdoc và sandbox

`srcdoc` thường tạo document kế thừa origin của parent. Khi iframe có `sandbox` mà không có `allow-same-origin`, document bị gán opaque origin.

```html
<iframe
  sandbox
  referrerpolicy="no-referrer"
  srcdoc="<p>Văn bản xem trước không tin cậy</p>">
</iframe>
```

Không thêm `allow-scripts` nếu preview không cần chạy script. Đặc biệt tránh kết hợp `allow-scripts` và `allow-same-origin` cho nội dung cùng origin, vì nội dung đó có thể có cách gỡ bỏ sandbox trong một số cấu hình.

## 6. Origin null và CORS

### 6.1. Vì sao Origin có thể là null?

Một số request có thể mang `Origin: null` khi được tạo từ opaque-origin context, chẳng hạn một số `file:` document, `data:` document hoặc sandboxed iframe. Hành vi header chính xác phụ thuộc loại request và browser.

`null` là serialization của opaque origin, không phải origin của một domain tên “null”. Nhiều trang không liên quan có thể cùng serialize thành `null`.

### 6.2. Không allowlist Origin: null một cách rộng rãi

Cấu hình nguy hiểm:

```http
Access-Control-Allow-Origin: null
Access-Control-Allow-Credentials: true
```

Nếu server trả các header này cho mọi request `Origin: null`, nhiều opaque-origin document không tin cậy có thể được phép đọc response có credentials theo các điều kiện browser. Không dùng `null` như wildcard thay thế cho origin cụ thể.

Chỉ hỗ trợ opaque origin nếu có use case được đánh giá rõ, kiểm soát được context tạo request và hiểu giới hạn của credentials/cookie. Trong phần lớn ứng dụng web, không cần cho `file:` page đọc API authenticated.

### 6.3. CORS không cấp quyền filesystem

Thêm `Access-Control-Allow-Origin` không biến một website thành ứng dụng có quyền đọc file local. CORS điều khiển việc JavaScript đọc response cross-origin; nó không cấp quyền đọc đường dẫn trên ổ đĩa, không vượt qua file picker và không thay thế browser permission model.

### 6.4. Không dùng fetch file:// để đọc local file

Một trang web không thể tùy ý gọi:

```js
fetch("file:///C:/Users/Alice/Documents/private.txt");
```

và kỳ vọng đọc nội dung file. Browser hạn chế các request này theo local-file security policy. Nếu người dùng cần chọn file, dùng file input hoặc picker API được browser hỗ trợ và chỉ xử lý các file đã được người dùng cấp quyền.

## 7. MIME type, sniffing và cách browser xử lý file

### 7.1. Content-Type phải phản ánh bytes

`Content-Type` cho browser biết media type của response. Ví dụ:

| Nội dung | MIME type thường dùng |
| --- | --- |
| PDF | `application/pdf` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| Plain text | `text/plain; charset=utf-8` |
| HTML | `text/html; charset=utf-8` |
| SVG | `image/svg+xml` |
| JSON | `application/json` |
| Generic binary download | `application/octet-stream` |

MIME type cần được xác định từ loại nội dung đã kiểm tra ở server, không chỉ dựa vào extension hoặc `Content-Type` do browser upload gửi lên.

### 7.2. X-Content-Type-Options: nosniff

```http
X-Content-Type-Options: nosniff
```

`nosniff` yêu cầu browser không sniff MIME trong các ngữ cảnh được định nghĩa, đặc biệt khi tải script/style. Nó giúp ngăn một số trường hợp browser diễn giải nội dung theo kiểu nguy hiểm khác với MIME server khai báo.

`nosniff` không phải antivirus, không xác thực file, không ngăn người dùng tự mở file bằng ứng dụng desktop và không thay thế `Content-Disposition: attachment`.

### 7.3. HTML và SVG là active content

HTML và SVG có thể chứa script, event handler, external resource hoặc navigation. SVG cũng có thể được hiển thị trong browser và có ngữ cảnh hoạt động tùy cách nhúng. Không coi `.html` hoặc `.svg` là hình ảnh/tài liệu thụ động.

Nếu file do người dùng cung cấp, tránh phục vụ nội dung active trên origin chứa session cookie hoặc API cùng origin. Dùng download attachment hoặc host trên origin/site riêng không có credential của ứng dụng.

### 7.4. Extension không chứng minh định dạng

File có tên `invoice.pdf` có thể chứa HTML hoặc bytes khác. File có đuôi .txt cũng không bảo đảm nội dung không có markup nếu server phục vụ nó với MIME active. Kiểm tra file signature/content, giới hạn kích thước, dùng parser an toàn và quyết định MIME/extension ở server.

## 8. Phục vụ file download an toàn

### 8.1. Tách download endpoint khỏi quyền truy cập file

Client nên yêu cầu một resource ID hoặc opaque download token có thời hạn ngắn. Server xác thực session, kiểm tra quyền sở hữu file và ánh xạ ID sang đường dẫn lưu trữ nội bộ. Không nhận filesystem path tùy ý từ query như `?path=../../private/...`.

### 8.2. Ví dụ Express trả file riêng tư

```js
app.get("/downloads/:fileId", requireSession, async (req, res, next) => {
  try {
    const file = await findFileById(req.params.fileId);

    if (!file || file.ownerId !== req.user.id) {
      return res.sendStatus(404);
    }

    res.set({
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff"
    });

    res.download(file.storagePath, file.safeDownloadName, error => {
      if (error && !res.headersSent) next(error);
    });
  } catch (error) {
    next(error);
  }
});
```

`requireSession` xác thực user; `findFileById` chỉ tra cứu metadata; `ownerId` được kiểm tra trước khi đọc file. `storagePath` và `safeDownloadName` phải do server quản lý, không lấy trực tiếp từ path hoặc filename chưa kiểm tra của request.

### 8.3. Download URL có chữ ký

Signed URL có thể cho phép tải file mà không cần cookie session trong một thời gian ngắn. URL đó là bearer credential: ai có URL đều có thể dùng trong phạm vi và thời hạn được cấp. Vì vậy:

- Dùng HTTPS và expiry ngắn.
- Gắn URL với file, method và phạm vi cần thiết.
- Không đưa signed URL vào analytics hoặc log không redacted.
- Không dùng URL có thời hạn dài cho file nhạy cảm.
- Có cơ chế revoke/rotate nếu nền tảng hỗ trợ.
- Không coi URL đã ký là bí mật nếu nó được gửi qua chat/email không an toàn.

### 8.4. Filename và path traversal

Không ghép filename do người dùng gửi vào filesystem path. Lưu file bằng ID ngẫu nhiên hoặc key do server sinh, giữ tên gốc như metadata đã sanitize. Khi trả download, tạo filename hiển thị riêng và loại bỏ path separator, control characters, CR/LF và extension không được phép.
## 9. Blob URL: origin của nội dung được tạo trong browser

### 9.1. Tạo Blob URL cho file download

Blob URL hữu ích khi ứng dụng tạo file từ dữ liệu đã có trong memory, ví dụ export CSV hoặc báo cáo. URL được tạo bởi `URL.createObjectURL()` và cần được thu hồi khi không còn sử dụng.

```js
function downloadTextFile(text, filename) {
  const blob = new Blob([text], {
    type: "text/plain;charset=utf-8"
  });

  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = objectUrl;
  link.download = filename;
  link.hidden = true;

  document.body.append(link);
  link.click();
  link.remove();

  // Giữ URL đủ lâu cho browser bắt đầu download, sau đó thu hồi.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
```

Tên file cần được ứng dụng chuẩn hóa trước khi đưa vào `download`. Không đưa nội dung nhạy cảm vào Blob nếu không cần; Blob URL tồn tại trong browser context và có thể được sử dụng bởi code có quyền truy cập URL đó.

### 9.2. Thu hồi object URL

Mỗi lần gọi `URL.createObjectURL()` tạo một URL reference mới. Khi file không còn cần preview hoặc download, gọi `URL.revokeObjectURL(url)`. Không revoke ngay trước khi browser bắt đầu đọc file, nhưng cũng không giữ URL vô thời hạn trong ứng dụng.

Nếu URL đang được dùng trong `<img>`, `<iframe>` hoặc media element, chỉ revoke sau khi element không còn cần resource. Revoke URL không xóa file gốc trên đĩa; Blob URL chỉ là handle tới dữ liệu trong browser.

### 9.3. Blob URL không phải origin cách ly

Ví dụ anti-pattern:

```js
const untrustedHtml = getUserSuppliedHtml();
const blob = new Blob([untrustedHtml], {
  type: "text/html"
});

const url = URL.createObjectURL(blob);
window.open(url, "_blank");
```

Nếu trang ứng dụng tạo Blob HTML rồi mở Blob URL, document thường gắn với origin của creator. Script trong nội dung không tin cậy có thể được thực thi trong security context của ứng dụng. Việc URL bắt đầu bằng `blob:` không làm nó trở thành sandbox.

Không dùng Blob URL do ứng dụng tạo để chạy HTML/SVG không tin cậy. Nếu chỉ cần tải file, đặt MIME phù hợp và dùng download flow. Nếu cần preview, dùng text rendering hoặc sandbox/origin riêng.

## 10. Preview file không tin cậy

### 10.1. Hiển thị nội dung dưới dạng text

Nếu mục tiêu là cho người dùng xem source hoặc nội dung text, render bằng `textContent` hoặc `<pre>` thay vì gán chuỗi không tin cậy vào `innerHTML`.

```js
function showTextPreview(container, fileText) {
  const pre = document.createElement("pre");
  pre.textContent = fileText;
  container.replaceChildren(pre);
}
```

`textContent` coi dữ liệu là text. Nếu dùng `innerHTML`, nội dung như `<img onerror=...>` hoặc `<script>` có thể trở thành markup hoạt động tùy context.

### 10.2. Sandbox iframe cho preview HTML

Khi cần hiển thị HTML không tin cậy, dùng iframe sandbox với quyền tối thiểu. Nếu chỉ cần xem markup như tài liệu tĩnh, không cấp script hoặc same-origin:

```html
<iframe
  sandbox
  referrerpolicy="no-referrer"
  title="Xem trước tài liệu không tin cậy">
</iframe>
```

Ví dụ gán nội dung đã escape dưới dạng text trong `srcdoc`:

```js
function escapeHtml(value) {
  return value.replace(/[&<>"']/g, character => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function renderUntrustedTextInFrame(frame, value) {
  frame.setAttribute("sandbox", "");
  frame.referrerPolicy = "no-referrer";
  frame.srcdoc = "<!doctype html><meta charset='utf-8'><pre>" +
    escapeHtml(value) +
    "</pre>";
}
```

Sandbox không có `allow-same-origin` khiến frame có opaque origin; không cấp `allow-scripts` nếu không cần. Nếu cần preview HTML có tương tác, phải đánh giá riêng threat model và quyền sandbox. Không kết hợp `allow-scripts` với `allow-same-origin` cho nội dung cùng origin.

### 10.3. Origin riêng cho nội dung do người dùng tải lên

Nếu sản phẩm phải phục vụ HTML/SVG hoặc tài liệu active do người dùng upload, host chúng trên origin riêng không chứa session cookie và không có quyền truy cập API nội bộ. Ví dụ ứng dụng ở `app.example.com`, file không tin cậy ở một site/domain riêng được kiểm soát như `usercontent-example.net`.

Dùng một registrable domain riêng sẽ tạo ranh giới mạnh hơn subdomain cùng site trong một số mô hình cookie/SameSite. Không đặt cookie phiên của ứng dụng trên domain cha dùng chung với host nội dung không tin cậy. Cấu hình CORS không cho host nội dung truy cập API private.

### 10.4. CSP là lớp bổ sung

CSP có thể hạn chế script, network, frame và navigation trong response được server phục vụ. Ví dụ một viewer cô lập có thể dùng policy nghiêm ngặt phù hợp với chức năng:

```http
Content-Security-Policy: default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; sandbox
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
```

Đây chỉ là ví dụ cần tinh chỉnh theo viewer. Đặc biệt, HTTP response header CSP của lần download không nhất thiết được lưu thành metadata và áp dụng lại khi người dùng mở file local sau đó. Không dựa vào CSP header của response download để bảo vệ file khi nó được mở từ đĩa; cần cô lập origin/ứng dụng xem file ngay từ đầu.

## 11. File API và quyền đọc file do người dùng chọn

### 11.1. File object không đổi origin của trang

Khi người dùng chọn file qua `<input type="file">`, browser cung cấp `File` object cho trang. File object là dữ liệu mà người dùng đã chọn; document vẫn giữ origin của ứng dụng. Việc đọc File object không biến file thành một document same-origin hoặc cấp quyền đọc các file khác trong cùng thư mục.

```html
<label>
  Chọn tài liệu
  <input id="file-input" type="file" accept=".txt,.csv,application/pdf">
</label>
<pre id="file-info"></pre>
```

```js
const input = document.querySelector("#file-input");
const output = document.querySelector("#file-info");

input.addEventListener("change", () => {
  const file = input.files?.[0];
  if (!file) return;

  output.textContent = JSON.stringify({
    name: file.name,
    size: file.size,
    type: file.type,
    lastModified: file.lastModified
  }, null, 2);
});
```

Không hiển thị đường dẫn local tuyệt đối. Giá trị `file.name`, `file.type` và metadata do browser/client cung cấp đều là input không tin cậy.

### 11.2. Đọc file do user chọn

```js
async function readSelectedTextFile(file) {
  if (file.size > 2 * 1024 * 1024) {
    throw new Error("File vượt quá giới hạn 2 MB.");
  }

  return file.text();
}

input.addEventListener("change", async () => {
  const file = input.files?.[0];
  if (!file) return;

  try {
    const text = await readSelectedTextFile(file);
    showTextPreview(output, text);
  } catch {
    output.textContent = "Không thể đọc file đã chọn.";
  }
});
```

Kiểm tra size trước khi đọc toàn bộ file vào memory. Với file lớn, dùng stream hoặc xử lý theo chunk nếu API và định dạng cho phép. Không dùng `accept` như cơ chế xác thực; đây chỉ là gợi ý cho file picker.

### 11.3. Upload file

```js
async function uploadSelectedFile(file) {
  const formData = new FormData();
  formData.append("document", file, file.name);

  const response = await fetch("/api/documents", {
    method: "POST",
    credentials: "same-origin",
    body: formData
  });

  if (!response.ok) {
    throw new Error("Upload thất bại.");
  }

  return response.json();
}
```

Server phải xác thực user, kiểm tra quyền upload, giới hạn kích thước, kiểm tra nội dung thực tế, đổi tên lưu trữ và quét file theo yêu cầu sản phẩm. Không tin `file.type`, extension hoặc filename từ client. Nếu endpoint dùng cookie session, bảo vệ CSRF như các mutation khác.

### 11.4. File System Access API

Một số browser hỗ trợ File System Access API cho phép người dùng chọn file hoặc thư mục và cấp handle để đọc/ghi theo permission. API này không phải quyền filesystem tổng quát; cần secure context và user activation/permission theo browser. Không giả định mọi browser đều hỗ trợ và không yêu cầu quyền rộng nếu chỉ cần một file.

## 12. Browser security cho file download và upload

### 12.1. Download file từ server

Với file private, server cần xác thực và authorize từng download. Opaque file ID không tự chứng minh người dùng có quyền. Không dựa vào việc URL khó đoán làm biện pháp authorization duy nhất.

### 12.2. Upload và lưu trữ

File upload có thể chứa malware, polyglot content hoặc active HTML/SVG. Cần giới hạn kích thước, số lượng, loại file và parser. Lưu file ngoài web root hoặc trong object storage riêng; không cho upload trực tiếp trở thành executable path của web server.

### 12.3. File preview và antivirus

Quét malware có thể giảm rủi ro nhưng không bảo đảm file vô hại. Parser vẫn có thể có lỗi, file có thể chứa macro/active content, và file có thể khai thác ứng dụng desktop khi mở. Không tự động mở file vừa upload hoặc tải xuống.

### 12.4. Content Security Policy không thay thế origin separation

CSP giúp giảm khả năng thực thi script trong một document, nhưng origin riêng vẫn là biện pháp cô lập mạnh hơn cho nội dung do người dùng kiểm soát. Nếu host file không tin cậy trên cùng origin với ứng dụng, cookie, storage và API có thể cùng nằm trong một trust boundary. Hãy tách origin trước, sau đó áp dụng CSP và MIME policy phù hợp.

## 13. Những lỗi bảo mật thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Giả định file cùng thư mục là same-origin | Quyền truy cập thay đổi theo browser | Không dùng file origin để chia sẻ dữ liệu |
| Allow CORS cho `Origin: null` rộng rãi | Opaque-origin document không tin cậy có thể đọc response | Chỉ allow origin cụ thể |
| Cho rằng file download giữ origin của trang tải | Đánh giá sai ranh giới khi file được mở | Phân biệt download response và file document local |
| Mở HTML upload trên app origin | Script có thể chạy với quyền origin ứng dụng | Attachment hoặc origin riêng |
| Mở Blob HTML không tin cậy trong tab mới | Blob có thể mang origin của creator | Text preview hoặc sandbox |
| Tin `Content-Type`/extension từ client | MIME confusion và active content | Kiểm tra file ở server |
| Dùng `nosniff` như antivirus | File độc hại vẫn có thể được mở | Validation, scanning và isolation |
| Dùng `download` attribute như kiểm soát bảo mật | Browser có thể bỏ qua ở cross-origin; file vẫn mở được | Server Content-Disposition và policy |
| Ghi filename trực tiếp vào header/path | Header injection hoặc path traversal | Sanitize, server-generated storage key |
| Coi CSP header của download còn áp dụng khi mở local | File local không nhất thiết giữ HTTP headers | Bảo vệ viewer và origin riêng |
| Dùng `file://` để chạy app thay cho dev server | Khác biệt origin, fetch/module/worker bị chặn | Dùng localhost/HTTPS |
| Cho phép file preview có script và same-origin | Nội dung không tin cậy có thể truy cập app context | Sandbox, opaque origin hoặc site riêng |

## 14. Thực hành: kiểm tra file origin trong browser

Lab nên chạy trên tài khoản thử nghiệm và browser mục tiêu. Không mở file lạ hoặc nội dung không tin cậy từ nguồn bên ngoài.

### 14.1. Kiểm tra origin của trang HTTP

Mở DevTools Console trên một trang thử nghiệm HTTP(S):

```js
console.log({
  href: location.href,
  origin: location.origin,
  protocol: location.protocol
});
```

Ghi lại origin. Thử mở một trang cùng origin và một trang khác host/port để thấy tuple origin thay đổi.

### 14.2. Kiểm tra file URL

Tạo một file HTML tĩnh chỉ hiển thị thông tin:

```html
<!doctype html>
<meta charset="utf-8">
<title>File origin lab</title>
<pre id="result"></pre>
<script>
  document.querySelector("#result").textContent = JSON.stringify({
    href: location.href,
    origin: location.origin,
    protocol: location.protocol
  }, null, 2);
</script>
```

Mở file bằng browser và quan sát `location.protocol` cùng `location.origin`. Giá trị serialize và quyền tương tác có thể khác theo browser; không suy ra policy production từ một kết quả đơn lẻ.

### 14.3. Kiểm tra Blob và data URL

Trên một trang HTTP(S) thử nghiệm, chạy:

```js
const blob = new Blob(
  ["<!doctype html><p>Blob document</p>"],
  { type: "text/html" }
);

const blobUrl = URL.createObjectURL(blob);
console.log("Blob URL:", blobUrl);

const dataUrl = "data:text/html,<p>Data document</p>";
console.log("Data URL:", dataUrl);
```

Mở từng URL trong môi trường thử nghiệm và quan sát `location.origin`. Blob document thông thường gắn với origin creator; data document có opaque origin. Thu hồi Blob URL sau khi hoàn tất kiểm tra:

```js
URL.revokeObjectURL(blobUrl);
```

Không dùng nội dung HTML không tin cậy trong bài kiểm tra origin này.

### 14.4. Kiểm tra sandbox

Tạo iframe sandbox không cấp quyền:

```html
<iframe id="preview" sandbox srcdoc="<p>Sandboxed</p>"></iframe>
```

So sánh với iframe `srcdoc` không sandbox trong trang thử nghiệm. Quan sát việc truy cập DOM, origin và message. Không thêm token sandbox cho tới khi hiểu quyền cụ thể cần cấp.

### 14.5. Kiểm tra download response

Dùng một endpoint staging có file test:

- Mở Network và chọn response download.
- Kiểm tra `Content-Type`, `Content-Disposition`, `X-Content-Type-Options` và `Cache-Control`.
- Xác minh response private có authorization check.
- Tải file về và mở bằng browser/ứng dụng phù hợp.
- Xác nhận file được xử lý như file local, không mang session của app.
- Nếu file là HTML/SVG không tin cậy, chỉ kiểm tra trong môi trường cô lập, không mở trên profile đang đăng nhập tài khoản thật.

## 15. Ma trận kiểm thử File origin

| Mã | Tình huống | Kết quả mong muốn |
| --- | --- | --- |
| FILE-OR-01 | Hai trang HTTPS cùng scheme/host/port | Same-origin |
| FILE-OR-02 | Hai trang khác port | Cross-origin |
| FILE-OR-03 | HTTP và HTTPS cùng host | Cross-origin |
| FILE-OR-04 | Mở file HTML bằng file URL | Browser áp dụng local-file origin policy |
| FILE-OR-05 | Hai file trong cùng thư mục | Không dựa vào giả định same-origin |
| FILE-OR-06 | File HTML fetch một file local khác | Browser hạn chế theo local-file policy |
| FILE-OR-07 | File local gọi API authenticated | Không mở rộng CORS cho null để làm request thành công |
| FILE-OR-08 | Opaque origin serialize thành null | Không coi null là một domain đáng tin |
| FILE-OR-09 | data URL document | Opaque origin theo browser model hiện đại |
| FILE-OR-10 | Blob URL từ app origin | Blob document gắn origin creator trong trường hợp thông thường |
| FILE-OR-11 | Blob HTML không tin cậy | Không mở trực tiếp như document cùng origin |
| FILE-OR-12 | about:blank initial document | Xác minh quan hệ kế thừa origin từ creator |
| FILE-OR-13 | iframe srcdoc không sandbox | Kế thừa origin parent theo quy tắc |
| FILE-OR-14 | iframe sandbox không allow-same-origin | Opaque origin |
| FILE-OR-15 | iframe sandbox không allow-scripts | Script trong preview không chạy |
| FILE-OR-16 | CORS allow Origin null | Không bật rộng; kiểm thử opaque-origin threat |
| FILE-OR-17 | Download private file | Server xác thực và authorize file ID |
| FILE-OR-18 | Content-Disposition attachment | Browser xử lý response như download |
| FILE-OR-19 | Response thiếu nosniff | Kiểm tra MIME handling và cấu hình header |
| FILE-OR-20 | HTML/SVG do user upload | Không phục vụ inline trên app origin |
| FILE-OR-21 | Filename có CR/LF/path separator | Server sanitize hoặc từ chối |
| FILE-OR-22 | Extension không khớp file signature | Server không tin extension/MIME client |
| FILE-OR-23 | Signed URL hết hạn | Download bị từ chối |
| FILE-OR-24 | Blob URL không còn dùng | URL được revoke đúng vòng đời |
| FILE-OR-25 | File picker chọn file | Chỉ file do người dùng chọn được cung cấp |
| FILE-OR-26 | Upload file có MIME giả | Server xác minh nội dung thực tế |
| FILE-OR-27 | Back/preview file sau logout | Không lộ session hoặc dữ liệu app |
| FILE-OR-28 | CSP header trên response download | Không giả định policy còn áp dụng khi mở local |
| FILE-OR-29 | Host file trên origin riêng | Không chia sẻ cookie/session với app |
| FILE-OR-30 | Browser khác nhau xử lý file origin | Không phụ thuộc một implementation cụ thể |

## 16. Checklist triển khai

- [ ] Dùng tuple origin scheme/host/port để phân tích web origin.
- [ ] Phân biệt origin với site và SameSite cookie.
- [ ] Không dựa vào hành vi file origin giống nhau giữa các browser.
- [ ] Không dùng file URL làm cơ chế chia sẻ hoặc xác thực.
- [ ] Không allowlist Origin: null rộng rãi.
- [ ] Không xem file download là document kế thừa origin của trang tải.
- [ ] Dùng Content-Disposition attachment cho file cần download.
- [ ] Trả Content-Type chính xác và X-Content-Type-Options: nosniff.
- [ ] Đặt Cache-Control phù hợp cho file private.
- [ ] Xác thực và authorize mỗi lần download.
- [ ] Dùng server-generated storage key; chống path traversal và header injection.
- [ ] Không phục vụ HTML/SVG upload trên app origin.
- [ ] Host nội dung active không tin cậy trên origin/site riêng.
- [ ] Dùng textContent cho text preview.
- [ ] Dùng iframe sandbox với quyền tối thiểu cho HTML preview.
- [ ] Không kết hợp allow-scripts và allow-same-origin cho nội dung cùng origin.
- [ ] Hiểu Blob URL kế thừa origin creator; không dùng để sandbox HTML.
- [ ] Revoke Blob URL khi không còn sử dụng.
- [ ] Dùng File API chỉ với file người dùng đã chọn.
- [ ] Xác minh MIME, signature, size và nội dung file ở server.
- [ ] Không dựa vào CSP header của response download khi file được mở local.
- [ ] Kiểm thử trên các browser mục tiêu và qua đường đi CDN/proxy thật.

### Ghi nhớ

**File download không mang origin web của trang đã tải nó.** Khi mở file local, browser áp dụng chính sách `file:` riêng và hành vi có thể khác giữa các browser. Opaque origin thường serialize thành `null`, vì vậy không allowlist `Origin: null` rộng rãi. Blob URL thường gắn với origin creator và không phải sandbox; HTML/SVG không tin cậy cần được hiển thị bằng text, sandbox hoặc origin riêng. Server cần xác thực download, đặt MIME/Content-Disposition/nosniff phù hợp và kiểm tra file upload theo nội dung thực tế.
