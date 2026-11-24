# Browser download: tải tệp an toàn trong trình duyệt

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt tải tệp bằng liên kết, thuộc tính download, Content-Disposition, Fetch/Blob và object URL.
2. Giải thích vai trò của browser, server, origin và CORS trong một luồng download.
3. Bảo vệ endpoint tải tệp bằng authentication, authorization và kiểm tra quyền trên từng tài nguyên.
4. Thiết kế Content-Type, Content-Disposition và X-Content-Type-Options phù hợp.
5. Tạo filename an toàn, tránh path traversal, header injection và giả mạo phần mở rộng.
6. Xử lý file HTML, SVG, PDF và các định dạng có nội dung chủ động.
7. Quản lý Blob URL, bộ nhớ và tải tệp lớn.
8. Hiểu giới hạn của download attribute, user activation và automatic download.
9. Bảo vệ signed URL, cache, referrer, redirect và log.
10. Kiểm thử luồng download bằng Chrome DevTools và ma trận kiểm thử.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Browser download là điểm giao giữa ứng dụng, server, browser và hệ điều hành. Cần xác thực quyền tải, phân phối đúng loại nội dung, kiểm soát tên file và tránh để dữ liệu nhạy cảm rò rỉ qua URL hoặc cache.

## 1. Browser download là gì?

Browser download là quá trình browser nhận dữ liệu từ URL hoặc từ một object trong trang rồi lưu thành tệp theo lựa chọn và chính sách của browser. Tùy response header, loại nội dung, thao tác người dùng và cài đặt, browser có thể:

- Hiển thị nội dung trực tiếp trong tab.
- Tải tệp về thiết bị.
- Hỏi người dùng nơi lưu hoặc cách mở tệp.
- Chặn download do policy, sandbox, mixed content hoặc cơ chế bảo vệ.
- Hiển thị cảnh báo bảo mật với tệp hoặc nguồn đáng ngờ.

Một luồng download có nhiều thành phần:

    User action
        |
        v
    Browser tạo navigation hoặc Fetch request
        |
        v
    Server xác thực và kiểm tra quyền
        |
        v
    Server trả bytes và response headers
        |
        v
    Browser quyết định render, download hoặc block
        |
        v
    Người dùng lưu hoặc mở file bằng ứng dụng phù hợp

Download thành công không chứng minh file an toàn. Browser nhận được bytes không có nghĩa nội dung đã được kiểm tra malware, cấu trúc file hoặc hành vi khi mở.

### Ba câu hỏi bảo mật

Với mọi chức năng download, cần trả lời:

1. **Ai được tải?** Server xác thực người dùng và authorization trên tài nguyên cụ thể.
2. **Browser nhận nội dung gì?** Server gửi đúng Content-Type, Content-Disposition và policy liên quan.
3. **File sẽ được xử lý thế nào?** Không giả định file an toàn chỉ vì browser đã tải xong; định dạng có nội dung chủ động cần được cô lập và kiểm soát.

## 2. Các cách tải file trong browser

### Liên kết điều hướng trực tiếp

Cách đơn giản nhất là liên kết tới endpoint:

    <a href="/downloads/reports/monthly.pdf">
      Tải báo cáo
    </a>

Server trả response phù hợp, thường có Content-Disposition: attachment. Browser tự xử lý luồng download.

Ưu điểm:

- Không cần giữ toàn bộ file trong JavaScript memory.
- Phù hợp với file lớn.
- Browser quản lý tiến độ, resume hoặc giao diện download theo khả năng.
- Dùng được với cookie session same-origin mà không phải đưa token vào URL.

Đây thường là lựa chọn tốt cho file do server cung cấp.

### Thuộc tính download của anchor

Thuộc tính download gợi ý browser tải URL thay vì điều hướng hiển thị:

    <a
      href="/downloads/report.pdf"
      download="monthly-report.pdf">
      Tải báo cáo
    </a>

Tên trong download là tên gợi ý. Browser có quyền điều chỉnh hoặc bỏ qua theo policy, loại URL và cài đặt người dùng.

Thuộc tính này chủ yếu áp dụng cho same-origin URL, blob URL và data URL. Với URL cross-origin, browser thường không cho trang ép tải chỉ bằng thuộc tính download; server đích có thể cần trả Content-Disposition: attachment.

Không dựa vào download attribute để bảo vệ file. Server vẫn phải xác thực, kiểm tra quyền và trả response an toàn.

### Content-Disposition

Server có thể yêu cầu browser tải tệp bằng header:

    Content-Disposition: attachment; filename="report.pdf"

Hoặc yêu cầu hiển thị inline nếu browser hỗ trợ loại nội dung:

    Content-Disposition: inline

attachment thường khiến browser tải thay vì render trực tiếp. inline cho phép browser xử lý nội dung theo Content-Type. Với nội dung không tin cậy, việc render inline có thể tạo rủi ro script hoặc nội dung chủ động.

Content-Disposition là chỉ dẫn cho browser, không phải cơ chế authorization hay antivirus. Người dùng vẫn có thể mở file đã tải bằng ứng dụng khác.

### Fetch rồi tạo Blob

Ứng dụng có thể dùng Fetch để lấy dữ liệu, kiểm tra response rồi tạo Blob URL:

    async function downloadReport() {
      const response = await fetch("/api/reports/monthly", {
        credentials: "same-origin"
      });

      if (!response.ok) {
        throw new Error("Download failed");
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "monthly-report.pdf";
      link.click();

      setTimeout(() => {
        URL.revokeObjectURL(objectUrl);
      }, 1000);
    }

Luồng này hữu ích khi ứng dụng cần thêm Authorization header, kiểm tra status hoặc xử lý response trước khi tải. Tuy nhiên, response.blob() thường phải giữ toàn bộ nội dung trong bộ nhớ; không phù hợp với file rất lớn.

Lưu ý về user activation: một số browser giới hạn download được kích hoạt bằng script nếu thao tác click ban đầu đã quá lâu hoặc activation hết hạn trong lúc chờ mạng. Nếu download tự động sau await bị chặn, hãy hiển thị nút hoặc liên kết tải khi Blob đã sẵn sàng để người dùng click lần nữa. Không tạo click ẩn hoặc lặp lại click để né giới hạn của browser.

### Blob URL

URL.createObjectURL(blob) tạo URL tạm để browser truy cập Blob:

    const blob = new Blob(["Report content"], {
      type: "text/plain"
    });

    const objectUrl = URL.createObjectURL(blob);

    downloadLink.href = objectUrl;
    downloadLink.download = "report.txt";

Blob URL không phải URL public trên server. Nó gắn với môi trường tạo và có vòng đời cần được quản lý. Khi không còn cần, gọi URL.revokeObjectURL().

Không tạo hàng loạt Blob URL rồi bỏ quên. Object URL còn sống có thể giữ tài nguyên và dữ liệu trong memory.

## 3. download attribute và user activation

Browser giới hạn download tự động để giảm drive-by download và hành vi ép người dùng tải file.

### Gắn download vào thao tác người dùng

Ví dụ:

    downloadButton.addEventListener("click", async () => {
      const response = await fetch("/api/export");
      if (!response.ok) return;

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = objectUrl;
      link.download = "export.csv";
      link.click();

      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    });

Nên khởi tạo luồng từ hành động rõ ràng của người dùng. Một số browser có thể giới hạn click tổng hợp, nhiều download liên tiếp hoặc download không có user activation.

### Không tìm cách vượt cơ chế bảo vệ download

Không tự động mở hàng loạt download, tạo chuỗi click ẩn hoặc dùng redirect để ép tải nhiều file. Nếu chức năng cần tải nhiều tệp, hãy hiển thị danh sách và yêu cầu người dùng xác nhận hoặc tạo archive rõ ràng.

### Browser quyết định vị trí lưu

Trang web không được tùy ý ghi file vào đường dẫn bất kỳ trên máy người dùng bằng anchor download. Browser quản lý vị trí lưu, prompt và quyền truy cập file system.

Tên file do trang gợi ý không cho phép trang chọn thư mục tùy ý hoặc ghi đè file của người dùng mà không qua cơ chế browser.

## 4. Content-Disposition và filename an toàn

### filename và filename*

Header Content-Disposition có thể mang filename:

    Content-Disposition: attachment; filename="report.pdf"

Với tên Unicode, có thể cung cấp filename* theo RFC 6266 và encoding UTF-8:

    Content-Disposition: attachment; filename="report.pdf"; filename*=UTF-8''b%C3%A1o-c%C3%A1o.pdf

Client/browser có thể ưu tiên filename* khi hỗ trợ. Server nên dùng thư viện/framework xử lý header thay vì tự nối chuỗi tùy ý.

### Filename là input không tin cậy

Nếu filename xuất phát từ người dùng hoặc metadata file, phải xử lý trước khi đưa vào header.

Rủi ro:

- Path separator như slash hoặc backslash.
- Ký tự điều khiển và CR/LF gây header injection.
- Tên file quá dài.
- Tên đặc biệt hoặc reserved name của hệ điều hành.
- Dấu chấm hoặc dấu cách ở cuối tên.
- Unicode normalization khác nhau.
- Ký tự bidi điều khiển hướng chữ làm giả phần mở rộng hiển thị.
- Tên nhiều phần mở rộng như invoice.pdf.exe.
- Ký tự gây nhầm lẫn giữa extension và MIME type.

### Quy tắc tạo filename

- Chỉ cho phép một tập ký tự hợp lý theo nghiệp vụ.
- Loại bỏ slash, backslash, control characters và CR/LF.
- Không cho phép path từ client quyết định vị trí lưu.
- Giới hạn độ dài.
- Chuẩn hóa Unicode theo quy tắc của hệ thống.
- Chặn hoặc thay thế tên reserved theo hệ điều hành mục tiêu nếu cần.
- Tạo extension từ loại nội dung đã xác minh ở server.
- Có thể tạo tên file mới phía server thay vì giữ nguyên tên upload.

Ví dụ pseudo-code:

    function safeDownloadName(inputName, extension) {
      const base = removePathAndControlCharacters(inputName);
      const normalized = normalizeUnicode(base);
      const safeBase = keepAllowedCharacters(normalized)
        .slice(0, 80);

      return ensureSafeExtension(
        safeBase || "download",
        extension
      );
    }

Các hàm minh họa cần được triển khai bằng thư viện đã kiểm thử cho nền tảng server. Không tự viết một regex đơn giản rồi coi filename đã an toàn trên mọi hệ điều hành.

### Không tin extension do client gửi

Tên file .pdf không chứng minh nội dung là PDF. Người dùng có thể đổi tên file executable thành .pdf hoặc gửi nội dung không đúng định dạng.

Server cần xác định loại nội dung bằng quy trình phù hợp: allowlist định dạng, kiểm tra signature/magic bytes, parser chuyên dụng và scan nếu threat model yêu cầu. Extension chỉ là một phần của tên hiển thị.

## 5. Content-Type và MIME sniffing

Content-Type mô tả loại media của response:

    Content-Type: application/pdf

Ví dụ khác:

| Loại dữ liệu | MIME type thường gặp |
| --- | --- |
| PDF | application/pdf |
| CSV | text/csv |
| JSON | application/json |
| ZIP | application/zip |
| PNG | image/png |
| JPEG | image/jpeg |
| Plain text | text/plain |
| Dữ liệu không xác định | application/octet-stream |

Server phải gửi Content-Type phù hợp với nội dung thực tế và cách browser dự kiến xử lý.

### X-Content-Type-Options: nosniff

Có thể gửi:

    X-Content-Type-Options: nosniff

Header này yêu cầu browser không tự suy đoán MIME type trong một số ngữ cảnh được đặc tả, đặc biệt với script/style. Nó giúp giảm một số kiểu MIME confusion, nhưng không phải bộ quét malware và không bảo đảm mọi loại file sẽ không bị xử lý chủ động.

Kết hợp:

    Content-Type: application/octet-stream
    Content-Disposition: attachment; filename="download.bin"
    X-Content-Type-Options: nosniff

cho file không tin cậy hoặc không có MIME type đáng tin cậy, tùy thiết kế sản phẩm. Với file có định dạng rõ, gửi đúng Content-Type và quyết định inline/attachment theo rủi ro.

### Không dùng nosniff thay kiểm tra nội dung

Nếu server khai báo application/pdf nhưng bytes thực tế là HTML hoặc file executable, header không biến nội dung thành PDF an toàn. Phải xác minh nội dung trước khi phân phối.

### HTML, SVG và các định dạng có nội dung chủ động

Một số định dạng có thể chứa script, liên kết, form hoặc nội dung tương tác:

- HTML.
- SVG.
- XML có thể tham chiếu tài nguyên ngoài tùy parser.
- PDF có thể có action hoặc nội dung tương tác theo viewer.
- Một số định dạng office có macro hoặc external link.

Nếu file không tin cậy, tránh render inline trên origin chính chứa session cookie và dữ liệu ứng dụng.

## 6. Tách origin khi phân phối file không tin cậy

Phục vụ HTML/SVG do người dùng tải lên từ cùng origin với ứng dụng có thể tạo nguy cơ nếu file được mở inline hoặc browser xử lý theo origin đó.

Ví dụ:

    https://app.example.test
    https://files.example.test

Subdomain riêng có thể giảm một số rủi ro, nhưng cần kiểm tra cookie Domain. Nếu cookie session đặt Domain=.example.test, subdomain files có thể vẫn nhận cookie đó theo quy tắc cookie.

Với nội dung chủ động không tin cậy, cân nhắc dùng một site/domain riêng biệt không chia sẻ cookie với ứng dụng chính, cùng response header và sandbox phù hợp. Không dựa vào subdomain tách biệt nếu cookie hoặc trust boundary vẫn được chia sẻ.

### Download attachment thay vì inline

Với file không cần preview:

    Content-Disposition: attachment

Điều này yêu cầu browser tải file thay vì render trực tiếp trong tab ở các trường hợp hỗ trợ. Khi người dùng mở file đã tải, ứng dụng bên ngoài vẫn có thể xử lý nội dung chủ động. Attachment không phải sanitizer.

### Preview trong sandbox

Nếu sản phẩm cần preview HTML hoặc tài liệu không tin cậy, dùng origin cô lập và sandbox chặt. Ví dụ iframe sandbox có thể hạn chế script, form, navigation và download; chỉ cấp token sandbox cần thiết.

Không thêm allow-scripts, allow-same-origin hoặc allow-downloads chỉ để làm preview hoạt động nếu chưa đánh giá tác động. Với nội dung không tin cậy, ưu tiên không cấp script và không chia sẻ origin/cookie với ứng dụng chính.

## 7. Bảo vệ endpoint download

Ẩn URL hoặc dùng tên file khó đoán không phải authorization. Mọi request tải file phải được server xác thực và kiểm tra quyền.

### Kiểm tra quyền trên từng tài nguyên

Ví dụ endpoint:

    GET /api/documents/123/download

Server phải:

1. Xác thực session hoặc access token.
2. Tìm document 123.
3. Kiểm tra user có quyền đọc/tải document đó.
4. Kiểm tra tenant, trạng thái, retention và policy nghiệp vụ.
5. Ghi audit event phù hợp.
6. Trả file với header đúng.

Không chỉ kiểm tra user có role "member". Cần kiểm tra user có quyền với đúng document, tenant hoặc project.

### IDOR trong download

Nếu người dùng thay:

    /documents/123/download

thành:

    /documents/124/download

server phải kiểm tra quyền với document 124. UUID hoặc ID dài không thay thế authorization.

### Download URL không được thay đổi trạng thái

GET download nên chỉ đọc dữ liệu. Không thực hiện xóa, thanh toán, xác nhận hoặc chuyển quyền chỉ vì người dùng mở một download URL.

Nếu có hành động nghiệp vụ trước khi tải, thực hiện bằng request có method phù hợp, CSRF defense khi dùng cookie và xác nhận người dùng. Sau đó mới trả URL/file.

### Không để lộ file qua static public path

Nếu file riêng tư được đặt trong thư mục public mà không có authorization, attacker có thể truy cập trực tiếp bỏ qua API. Dùng storage private và endpoint kiểm tra quyền hoặc signed URL có giới hạn.

## 8. Signed URL và bearer capability

Object storage hoặc CDN có thể cấp signed URL để tải trực tiếp mà không phải proxy toàn bộ bytes qua ứng dụng.

Ví dụ minh họa:

    https://storage.example.test/object/report.pdf?signature=...&expires=...

Signed URL thường hoạt động như bearer capability: ai có URL trong thời hạn hợp lệ có thể thực hiện hành động được ký.

### Giới hạn signed URL

- TTL ngắn theo nhu cầu.
- Chỉ cho phép một object hoặc prefix rất hẹp.
- Ràng buộc method GET nếu chỉ cho download.
- Không cho phép ghi/xóa qua URL tải.
- Có thể giới hạn content disposition hoặc response override.
- Hỗ trợ revoke/rotate signing key hoặc thu hồi quyền qua policy khi cần.
- Không log query chứa signature.
- Không gửi URL qua analytics hoặc error reporting.
- Không đặt URL vào Referer của trang bên ngoài.

### Signed URL có thể bị chia sẻ

Người nhận có thể sao chép URL và gửi cho người khác. Kiểm tra authorization ở thời điểm phát hành URL không tự bảo đảm người tải cuối cùng vẫn là người được cấp quyền.

Nếu dữ liệu rất nhạy cảm, cân nhắc proxy download qua backend, thời hạn rất ngắn, kiểm soát session ở mỗi request hoặc cơ chế cấp quyền theo người dùng.

### Referrer-Policy cho signed URL

Nếu trang điều hướng tới signed URL, cấu hình referrer policy chặt cho trang hoặc link:

    Referrer-Policy: no-referrer

Hoặc:

    <a href="SIGNED_URL" referrerpolicy="no-referrer">
      Tải file
    </a>

Không đưa signed URL vào trang có third-party script không cần thiết. Referrer-Policy giảm một đường rò rỉ; nó không ngăn browser history, proxy log hoặc người dùng sao chép URL.

## 9. Download bằng Fetch, CORS và credential

### Same-origin Fetch

Ví dụ:

    const response = await fetch("/api/files/123/download", {
      credentials: "same-origin"
    });

    if (!response.ok) {
      throw new Error("Download failed");
    }

    const blob = await response.blob();

Cookie same-origin được gửi theo policy của browser. Server vẫn phải xác thực session và kiểm tra quyền file.

### Cross-origin Fetch

Nếu JavaScript dùng Fetch để đọc file từ origin khác, browser áp dụng CORS. Server cần trả CORS policy phù hợp.

Với credentialed cross-origin Fetch:

- Client dùng credentials: "include".
- Server trả Access-Control-Allow-Origin là origin cụ thể.
- Server trả Access-Control-Allow-Credentials: true.
- Cookie vẫn chịu SameSite, Secure và third-party cookie policy.
- Không dùng Access-Control-Allow-Origin: * cùng credential.

Ví dụ:

    fetch("https://files.example.test/download/123", {
      credentials: "include"
    });

### Navigation download khác Fetch

Một liên kết điều hướng tới file cross-origin không phải cùng cơ chế với JavaScript Fetch đọc response. CORS chủ yếu kiểm soát việc script đọc response qua Fetch/XHR; nó không phải authorization và không thay thế server policy.

Với cross-origin anchor, download attribute có thể bị browser bỏ qua. Server đích nên trả Content-Disposition: attachment nếu muốn browser xử lý như download.

### Authorization header

Fetch có thể đặt Authorization header:

    fetch("/api/files/123/download", {
      headers: {
        Authorization: "Bearer " + accessToken
      }
    });

Anchor thông thường không cho JavaScript tùy ý gắn Authorization header. Nếu cần tải bằng bearer token, có thể dùng Fetch rồi Blob cho file vừa phải, hoặc thiết kế BFF/session/signed URL ngắn hạn cho file lớn.

Không đưa bearer token dài hạn vào query string chỉ để làm anchor download hoạt động.

### Expose Content-Disposition

Nếu Fetch cross-origin cần đọc tên file từ Content-Disposition, server phải expose header:

    Access-Control-Expose-Headers: Content-Disposition

Nếu không expose, JavaScript có thể không đọc được header đó dù browser đã nhận response. Cần xử lý CORS cho request thực tế và preflight nếu có custom header.

## 10. Tải file lớn, Range request và bộ nhớ

### Tránh Blob cho file rất lớn nếu không cần xử lý ở JavaScript

response.blob() thường tạo Blob từ toàn bộ response. Với file lớn, browser có thể phải giữ lượng dữ liệu đáng kể trong memory hoặc storage tạm.

Ưu tiên native navigation/download endpoint khi:

- File lớn.
- Không cần biến đổi nội dung ở client.
- Server có thể xác thực qua cookie/session hoặc signed URL.
- Muốn browser quản lý download UI và khả năng tiếp tục theo hỗ trợ.

### Range request

Browser hoặc download manager có thể gửi Range request để lấy từng phần:

    Range: bytes=0-1048575

Server có thể trả:

    HTTP/1.1 206 Partial Content
    Accept-Ranges: bytes
    Content-Range: bytes 0-1048575/5000000

Nếu endpoint yêu cầu authentication, mọi request Range phải áp dụng cùng authentication và authorization. Không để request phần tiếp theo bỏ qua quyền chỉ vì request đầu đã được xác thực.

### Kiểm soát cache và validator

ETag, Last-Modified và If-Range hỗ trợ cache/partial download. Với file riêng tư:

    Cache-Control: private, no-store

Chính sách thực tế cần cân nhắc khả năng resume, hiệu năng và độ nhạy cảm. Không để shared cache trả file của user A cho user B do cache key thiếu session/authorization context.

### Content-Length và giới hạn

Content-Length có thể giúp hiển thị kích thước dự kiến nhưng không phải lúc nào cũng có hoặc đáng tin cậy trong mọi luồng. Server phải giới hạn kích thước file theo policy và không chỉ dựa vào client-side check.

## 11. Tên file và loại nội dung từ server

Server nên giữ metadata đã xác minh cho file:

- Storage key nội bộ.
- MIME type đã xác định.
- Extension được phép.
- Kích thước.
- Hash hoặc checksum nếu cần.
- Chủ sở hữu/tenant.
- Trạng thái scan.
- Quyền truy cập và retention.

Không dùng filename từ request làm storage path. Tên hiển thị và storage key nên tách biệt.

### MIME detection

Quy trình xác định file có thể gồm:

1. Kiểm tra extension theo allowlist.
2. Kiểm tra magic bytes/file signature.
3. Parse bằng thư viện phù hợp nếu định dạng phức tạp.
4. Kiểm tra kích thước và cấu trúc.
5. Quét malware hoặc sandbox nếu cần.
6. Lưu metadata đã xác minh.

Magic bytes cũng không đủ để chứng minh file hoàn toàn an toàn; một số định dạng có thể chứa payload chủ động hoặc khai thác parser.

### File nén

Archive ZIP/TAR có thể chứa:

- Path traversal khi giải nén.
- File rất lớn sau giải nén.
- Nhiều entry nhỏ gây cạn tài nguyên.
- Nested archive.
- Symlink hoặc metadata đặc biệt.

Browser download không tự giải quyết rủi ro khi người dùng hoặc ứng dụng giải nén. Nếu backend xử lý archive, giới hạn số entry, tổng kích thước sau giải nén, độ sâu lồng nhau và path sau canonicalization.

## 12. HTML, SVG, PDF và nội dung chủ động

### HTML và SVG

HTML/SVG có thể chứa script, event handler, external resource và navigation. Nếu phục vụ file không tin cậy inline trên origin ứng dụng, nội dung đó có thể tương tác với browser theo quyền của origin tùy cách phân phối.

Biện pháp:

- Dùng Content-Disposition: attachment nếu chỉ cần tải.
- Không inline HTML/SVG không tin cậy trên origin chứa session cookie.
- Nếu cần preview, dùng origin/site cô lập và sandbox.
- Đặt Content-Type chính xác.
- Dùng CSP phù hợp cho preview origin.
- Không chèn nội dung file vào DOM của ứng dụng chính bằng innerHTML.

### PDF

PDF viewer của browser có sandbox và hành vi riêng theo browser. Không giả định mọi PDF đều vô hại; PDF có thể chứa link, form, action hoặc khai thác parser/viewer.

Với PDF không tin cậy:

- Kiểm tra nguồn và quyền tải.
- Cân nhắc scan.
- Không tự động render inline nếu threat model không cho phép.
- Cập nhật browser/viewer.
- Không dựa vào extension .pdf.

### Office và executable

Macro-enabled office document, script file, installer và executable có rủi ro cao hơn. Không tự động tải hoặc mở chúng chỉ vì server trả status 200.

Hiển thị loại file và nguồn rõ ràng. Tôn trọng cảnh báo của browser và hệ điều hành. Không cố vượt SmartScreen/Safe Browsing hoặc policy quản trị thiết bị.

## 13. Download trong iframe và sandbox

Iframe sandbox có thể giới hạn việc download được khởi tạo từ frame. Ví dụ:

    <iframe
      src="https://preview.example.test/"
      sandbox="allow-scripts"
      title="File preview">
    </iframe>

Không có allow-downloads thì download từ sandboxed frame có thể bị chặn theo sandbox flags. Chỉ thêm allow-downloads nếu frame thực sự cần tải file và nội dung/nguồn đã được đánh giá.

Không cấp allow-scripts và allow-same-origin cùng lúc một cách máy móc cho nội dung không tin cậy. Tổ hợp đó có thể làm suy yếu đáng kể sandbox khi frame cùng origin với parent.

### CSP sandbox

CSP sandbox có thể áp dụng sandbox restrictions cho document. Nếu cần cho phép download, phải cân nhắc token allow-downloads theo policy và browser hỗ trợ. Không dùng sandbox như một lớp thay authorization hoặc malware scanning.

## 14. Automatic download và drive-by download

Drive-by download là tình huống trang cố tải file ngoài mong đợi hoặc gây áp lực để người dùng mở file.

Browser hiện đại có thể:

- Yêu cầu user activation.
- Giới hạn nhiều download tự động.
- Hiển thị prompt hoặc cảnh báo.
- Chặn download từ iframe sandbox.
- Cảnh báo nguồn hoặc file đáng ngờ.
- Áp dụng chính sách riêng do doanh nghiệp quản lý.

Ứng dụng nên:

- Chỉ bắt đầu download sau thao tác người dùng rõ ràng.
- Hiển thị tên và loại file trước khi tải nếu cần.
- Không tự tải hàng loạt file khi page load.
- Không dùng popup/redirect để né cảnh báo.
- Không ép người dùng mở file.
- Cung cấp cách hủy hoặc quay lại.

Không dựa vào browser warning làm lớp bảo vệ duy nhất. Server vẫn phải kiểm tra quyền và file.

## 15. Redirect, Referrer và URL leakage trong download

Download URL có thể chứa signed token hoặc mã tạm. URL này có thể xuất hiện trong log, history và referrer.

### Redirect chain

Ví dụ:

    /download/123
         |
         v
    302 Location: https://storage.example.test/file?signature=...
         |
         v
    File response

Kiểm tra:

- Redirect chỉ tới host đã cấu hình.
- Không nhận URL đích tùy ý từ query.
- Không chuyển Authorization header hoặc token sang origin không tin cậy.
- Signed URL có TTL ngắn và scope hẹp.
- Query chứa signature được redact khỏi log.
- Referrer-Policy ngăn gửi URL nhạy cảm sang tài nguyên khác.

### Referrer-Policy

Với trang tải file có signed URL:

    Referrer-Policy: no-referrer

Policy này giảm việc browser gửi URL trang nguồn trong Referer. Nó không xóa URL khỏi history, access log, proxy hoặc clipboard.

### Không dùng open redirect

Không cho phép parameter next/url/redirect tùy ý điều khiển Location tới domain bất kỳ. Dùng route key hoặc allowlist origin chính xác. Điều này đặc biệt quan trọng nếu URL download chứa capability.

## 16. Cache và dữ liệu riêng tư

File cá nhân, báo cáo tài chính hoặc dữ liệu hồ sơ cần cache policy rõ ràng.

Ví dụ response riêng tư:

    Cache-Control: private, no-store
    Pragma: no-cache

no-store yêu cầu cache HTTP không lưu response theo semantics HTTP caching. Nó không xóa file đã tải khỏi thiết bị người dùng và không xóa log.

Nếu cho phép cache private để hỗ trợ resume hoặc hiệu năng, xác định rõ:

- Ai có thể dùng lại cache.
- Cache key có phụ thuộc identity/authorization không.
- File có chứa dữ liệu nhạy cảm không.
- Khi quyền bị revoke, cache cũ có thể tiếp tục truy cập không.
- Browser và intermediary có tuân thủ policy mong muốn không.

Không dùng public shared cache cho file cá nhân hóa nếu chưa bảo đảm phân tách user và tenant.

## 17. Bộ header tham khảo cho download

Ví dụ file PDF đã xác minh, cần tải về:

    Content-Type: application/pdf
    Content-Disposition: attachment; filename="report.pdf"
    X-Content-Type-Options: nosniff
    Cache-Control: private, no-store
    Referrer-Policy: no-referrer

Ví dụ file không rõ MIME hoặc không tin cậy:

    Content-Type: application/octet-stream
    Content-Disposition: attachment; filename="download.bin"
    X-Content-Type-Options: nosniff
    Cache-Control: private, no-store
    Referrer-Policy: no-referrer

Đây là mẫu tham khảo. Chọn Content-Type đúng với file đã xác minh; application/octet-stream không thay thế scan hoặc validation.

Nếu endpoint cross-origin cần JavaScript đọc Content-Disposition:

    Access-Control-Expose-Headers: Content-Disposition

Nếu endpoint cần credentialed CORS, cấu hình origin cụ thể và Access-Control-Allow-Credentials phù hợp. CORS không thay authorization.

## 18. Kiểm thử Browser download bằng DevTools

Thực hiện trên local/staging với file giả và tài khoản test. Không tải executable hoặc tài liệu độc hại lên thiết bị làm việc.

### Bước 1 — Kiểm tra response

1. Mở DevTools → Network.
2. Bấm nút tải file.
3. Chọn request download.
4. Kiểm tra URL, method, status và redirect chain.
5. Kiểm tra Content-Type, Content-Disposition, Content-Length và Cache-Control.
6. Xác nhận không có token hoặc PII trong URL ngoài thiết kế có kiểm soát.

### Bước 2 — Kiểm tra authorization

1. Tải file bằng user A có quyền.
2. Thử cùng URL bằng user B không có quyền.
3. Thử đổi document ID.
4. Thử request không có session/token.
5. Xác nhận server từ chối các trường hợp không hợp lệ.

### Bước 3 — Kiểm tra filename

Dùng tên file test chứa:

- Slash/backslash.
- CR/LF hoặc control characters.
- Unicode và ký tự bidi.
- Tên rất dài.
- Nhiều extension.
- Tên reserved của hệ điều hành.

Xác nhận server tạo filename an toàn và không cho phép header injection hoặc path traversal.

### Bước 4 — Kiểm tra Fetch và Blob URL

1. Tải file nhỏ qua Fetch.
2. Kiểm tra response.ok trước khi đọc Blob.
3. Tạo object URL và trigger download từ thao tác người dùng.
4. Kiểm tra Blob URL được revoke sau khi browser bắt đầu xử lý.
5. Chạy lặp lại và quan sát memory để phát hiện object URL bị bỏ quên.

### Bước 5 — Kiểm tra CORS

1. Gọi download bằng Fetch từ origin khác trong staging.
2. Kiểm tra preflight nếu có Authorization/custom header.
3. Xác nhận ACAO khớp origin được phép.
4. Kiểm tra credentials nếu dùng cookie.
5. Xác nhận Content-Disposition được expose nếu JavaScript cần đọc.
6. Thử native link navigation riêng để phân biệt với Fetch.

### Bước 6 — Kiểm tra sandbox và active content

1. Nhúng preview test trong iframe sandbox.
2. Thử download khi không có allow-downloads.
3. Chỉ bật allow-downloads trong test nếu use case yêu cầu.
4. Xác nhận file HTML/SVG không tin cậy không chạy trong origin ứng dụng chính.
5. Kiểm tra browser xử lý attachment và inline khác nhau ra sao.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Same-origin link | Endpoint trả attachment | Browser tải theo policy |
| Download attribute | Same-origin URL | Browser có thể dùng filename gợi ý |
| Cross-origin link | Server không có attachment | download attribute có thể bị bỏ qua |
| Cross-origin attachment | Server trả Content-Disposition attachment | Browser xử lý theo header |
| Unauthorized | Không có session/token | Server từ chối |
| IDOR | Đổi document ID sang file user khác | Server từ chối |
| Filename traversal | Tên có ../ hoặc slash | Filename được sanitize, storage path không đổi |
| Header injection | Filename chứa CR/LF | Server/framework từ chối hoặc loại ký tự |
| MIME mismatch | Extension và bytes không khớp | Server phát hiện hoặc xử lý theo policy |
| nosniff | Response có header | Browser áp dụng các quy tắc nosniff được hỗ trợ |
| HTML/SVG không tin cậy | Yêu cầu preview | Không render trên origin chứa session |
| Blob URL | Tải Blob test | Object URL được revoke sau khi dùng |
| File lớn | Download qua native navigation | Không cần giữ toàn bộ file trong JS memory |
| Range request | Tải từng byte range | Mỗi request vẫn được authorization |
| Signed URL hết hạn | Dùng URL sau TTL | Storage/CDN từ chối |
| Signed URL sai object | Thay object key | Chữ ký không hợp lệ |
| Referrer | Tải từ trang có no-referrer | Không gửi Referer |
| Private cache | File user-specific | Không được lưu vào shared cache |
| Sandbox download | Frame không có allow-downloads | Browser chặn theo sandbox policy |
| Automatic download | Trigger khi page load | Browser có thể chặn; app yêu cầu user action |

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ download attribute luôn được tuân thủ | Browser có thể bỏ qua theo origin/policy | Dùng Content-Disposition ở server |
| Nghĩ attachment làm file an toàn | File có thể nguy hiểm khi người dùng mở | Validate, scan và cô lập active content |
| Tin extension do client gửi | File giả dạng loại khác | Kiểm tra bytes và parse theo allowlist |
| Dùng filename trực tiếp trong header | Header injection hoặc tên gây nhầm lẫn | Sanitize và dùng API header an toàn |
| Chỉ kiểm tra quyền ở trang hiển thị nút | Endpoint có thể bị gọi trực tiếp | Authorization ở mọi download request |
| Dùng UUID thay authorization | IDOR vẫn tồn tại | Kiểm tra quyền trên object |
| Đưa bearer token vào query cho anchor | Token rò rỉ qua log/history/referrer | Session/BFF hoặc signed URL ngắn hạn |
| Dùng Blob cho file nhiều GB | Tốn bộ nhớ và có thể crash tab | Native download endpoint |
| Không revoke Blob URL | Giữ tài nguyên không cần thiết | Gọi URL.revokeObjectURL() |
| Coi CORS là authorization | Client ngoài browser vẫn có thể gọi API | Xác thực và kiểm tra quyền ở server |
| Dùng wildcard credentialed CORS | Browser từ chối response và policy quá rộng | Origin cụ thể và ACAC đúng |
| Phục vụ HTML upload inline cùng origin | XSS hoặc truy cập dữ liệu ứng dụng | Attachment hoặc origin/site cô lập |
| Dựa vào nosniff để quét malware | File độc hại vẫn có thể tải/mở | Scan và validation riêng |
| Chỉ xác thực request đầu của Range | Request tiếp theo có thể lộ bytes | Authorization mọi request/range |
| Log signed URL | URL capability bị lộ | Redact query tại CDN/proxy/APM |
| Cho iframe tải tự do | Nội dung nhúng có thể ép download | Sandbox và chỉ cấp allow-downloads khi cần |
| Tự động tải nhiều file khi mở trang | Drive-by download và bị browser chặn | User action và xác nhận rõ |

## 20. Câu hỏi củng cố

**Câu 1.** Content-Disposition: attachment có tác dụng gì?

**Giải đáp:** Yêu cầu browser xử lý response như tệp đính kèm để tải xuống thay vì hiển thị inline khi phù hợp. Nó không xác thực quyền và không làm sạch file.

**Câu 2.** download attribute có hoạt động với mọi URL cross-origin không?

**Giải đáp:** Không. Browser giới hạn thuộc tính này; với cross-origin, server thường cần trả Content-Disposition: attachment.

**Câu 3.** Vì sao không tin filename do người dùng cung cấp?

**Giải đáp:** Filename có thể chứa path separator, CR/LF, ký tự điều khiển, Unicode bidi hoặc extension giả. Server phải tạo tên an toàn.

**Câu 4.** X-Content-Type-Options: nosniff có thay antivirus không?

**Giải đáp:** Không. Nó giảm một số hành vi MIME sniffing, không quét nội dung và không bảo đảm file an toàn.

**Câu 5.** Khi nào nên dùng Fetch rồi Blob?

**Giải đáp:** Khi cần custom Authorization header hoặc xử lý response ở client và file có kích thước phù hợp. Với file lớn, native download thường tiết kiệm memory hơn.

**Câu 6.** Vì sao signed URL cần TTL ngắn?

**Giải đáp:** URL hoạt động như bearer capability; ai có URL có thể dùng trong phạm vi và thời gian được ký. TTL ngắn giảm thời gian lạm dụng nếu URL bị lộ.

**Câu 7.** CORS có bảo vệ endpoint download không?

**Giải đáp:** Không. CORS kiểm soát việc JavaScript đọc response cross-origin; endpoint vẫn phải xác thực và authorization.

**Câu 8.** Tại sao phải authorization mỗi Range request?

**Giải đáp:** Mỗi Range là một request có thể lấy bytes. Không được để request sau bỏ qua quyền chỉ vì request đầu đã được xác thực.

**Câu 9.** Attachment có bảo vệ file HTML khỏi XSS không?

**Giải đáp:** Nó yêu cầu download thay vì inline, nhưng file có thể được mở sau đó. Với active content không tin cậy, cần cô lập origin và kiểm soát nội dung.

**Câu 10.** Blob URL cần được xử lý thế nào?

**Giải đáp:** Tạo khi cần, dùng cho download và revoke sau khi browser bắt đầu xử lý để giải phóng tài nguyên.

## 21. Tổng kết

Browser download có thể bắt đầu từ anchor, Content-Disposition, Fetch/Blob hoặc object URL. Với phần lớn file do server cung cấp, native download endpoint thường đơn giản và tiết kiệm bộ nhớ. download attribute chỉ là gợi ý, đặc biệt bị giới hạn với cross-origin; Content-Disposition là chỉ dẫn phía server để browser xử lý attachment hoặc inline.

Server phải xác thực và authorization cho từng file, không dựa vào URL khó đoán. Filename, extension và MIME type đều cần được kiểm tra; dùng Content-Disposition an toàn, Content-Type chính xác và X-Content-Type-Options: nosniff như một lớp hỗ trợ. HTML, SVG và các định dạng chủ động không tin cậy cần được tải dưới dạng attachment hoặc phục vụ từ origin/site cô lập.

Với Fetch/Blob, kiểm tra response.ok, xử lý CORS và credential đúng, rồi revoke Blob URL. Với file lớn, ưu tiên native download và bảo vệ mọi Range request. Signed URL là bearer capability nên cần TTL ngắn, scope hẹp và redaction. Kết hợp Referrer-Policy, Cache-Control, sandbox, giới hạn automatic download và kiểm thử authorization để bảo vệ toàn bộ luồng.

## Tài liệu tham khảo

1. [WHATWG — HTML Standard: Links and downloads](https://html.spec.whatwg.org/multipage/links.html): download attribute và thuật toán download.
2. [RFC 6266 — Content-Disposition in HTTP](https://www.rfc-editor.org/rfc/rfc6266): attachment, inline, filename và filename*.
3. [MDN — Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Disposition): cách browser xử lý response disposition.
4. [MDN — HTMLAnchorElement.download](https://developer.mozilla.org/en-US/docs/Web/API/HTMLAnchorElement/download): giới hạn và hành vi download attribute.
5. [MDN — URL.createObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL_static): tạo object URL từ Blob.
6. [MDN — URL.revokeObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/revokeObjectURL_static): giải phóng object URL.
7. [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): giảm MIME sniffing trong các ngữ cảnh được hỗ trợ.
8. [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): kiểm tra loại file, lưu trữ và xử lý nội dung không tin cậy.
