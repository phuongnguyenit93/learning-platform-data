# Blob URL: tạo và quản lý URL tạm cho dữ liệu trong browser

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích Blob, File và Blob URL khác nhau như thế nào.
2. Tạo URL tạm bằng URL.createObjectURL() và thu hồi bằng URL.revokeObjectURL().
3. Mô tả mối liên hệ giữa Blob URL, origin tạo URL và storage partitioning của browser.
4. Dùng Blob URL để preview ảnh, audio/video, tạo file tải xuống và khởi chạy Worker.
5. Quản lý vòng đời URL để tránh memory leak và lỗi race khi thay đổi giao diện.
6. Phân biệt Blob URL với data URL, URL HTTP và FileReader.
7. Hiểu vì sao Blob URL không phải cơ chế làm sạch nội dung hoặc ranh giới sandbox.
8. Phòng DOM XSS khi Blob chứa HTML/SVG và cấu hình CSP theo loại tài nguyên.
9. Xử lý CORS đúng khi tạo Blob từ response cross-origin.
10. Chọn Blob hay streaming phù hợp với kích thước dữ liệu.
11. Kiểm tra Blob URL bằng DevTools và xây dựng ma trận kiểm thử.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Blob URL giúp browser tham chiếu dữ liệu cục bộ trong một trang mà không cần upload dữ liệu lên server. Tuy nhiên, URL này vẫn có vòng đời, origin và rủi ro bảo mật cần được quản lý.

## 1. Blob là gì?

Blob (Binary Large Object) là đối tượng biểu diễn dữ liệu thô bất biến, có thể chứa văn bản, ảnh, PDF, audio, video hoặc bytes bất kỳ. Browser cung cấp Blob để ứng dụng thao tác với dữ liệu mà không cần biến nó thành một URL HTTP trên server.

Tạo Blob từ văn bản:

    const report = new Blob(
      ["Monthly report\nRevenue: 1200"],
      { type: "text/plain;charset=utf-8" }
    );

Tạo Blob từ nhiều phần:

    const csv = new Blob(
      [
        "name,amount\n",
        "Notebook,120\n",
        "Pen,20\n"
      ],
      { type: "text/csv;charset=utf-8" }
    );

Các thuộc tính và phương thức thường dùng:

| API | Ý nghĩa |
| --- | --- |
| blob.size | Kích thước dữ liệu tính bằng byte |
| blob.type | MIME type được gắn cho Blob |
| blob.slice(start, end, type) | Tạo Blob con từ một khoảng bytes |
| blob.text() | Đọc dữ liệu thành string |
| blob.arrayBuffer() | Đọc dữ liệu thành ArrayBuffer |
| blob.stream() | Tạo ReadableStream để đọc dữ liệu theo luồng |

Blob bất biến sau khi được tạo. Nếu cần nội dung mới, tạo Blob khác hoặc ghép các phần thành Blob mới.

### Blob và File

File kế thừa Blob và bổ sung metadata của tệp do người dùng chọn hoặc tệp được tạo trong browser.

    const file = fileInput.files[0];

    console.log(file.name);
    console.log(file.size);
    console.log(file.type);
    console.log(file.lastModified);

File có thể dùng ở nơi API chấp nhận Blob. Tuy nhiên, name và type là metadata do nguồn dữ liệu cung cấp; không được coi chúng là bằng chứng nội dung thực sự an toàn hoặc đúng định dạng.

### Blob.type không xác minh nội dung

Khi tạo Blob, ứng dụng có thể tự khai báo:

    const blob = new Blob(
      ["<script>example()</script>"],
      { type: "text/plain" }
    );

Giá trị type chỉ là metadata MIME type. Nó không quét bytes, không encode HTML và không loại bỏ script. Nếu cùng bytes được xử lý như HTML ở một ngữ cảnh khác, nội dung vẫn có thể mang hành vi chủ động.

## 2. Blob URL là gì?

Blob URL là URL tạm do browser tạo để một browsing context hoặc worker tham chiếu tới Blob hoặc MediaSource. API tạo URL:

    const objectUrl = URL.createObjectURL(blob);

Giá trị trả về có dạng tổng quát:

    blob:https://app.example.test/550e8400-e29b-41d4-a716-446655440000

Phần sau blob: chứa thông tin origin của môi trường tạo URL và một định danh nội bộ. Đây không phải endpoint HTTP được gửi tới web server.

Browser giữ một mapping giữa Blob URL và object được tham chiếu. Khi một API như img.src, video.src, anchor.href hoặc fetch sử dụng URL đó, browser tra mapping và cung cấp dữ liệu.

### Blob URL không upload dữ liệu

Ví dụ:

    const blob = new Blob(["Hello"], {
      type: "text/plain"
    });
    const url = URL.createObjectURL(blob);

Việc tạo URL không gửi bytes lên server. Dữ liệu vẫn nằm trong phạm vi browser/runtime quản lý. Nếu ứng dụng gọi fetch tới server hoặc gửi Blob qua FormData, lúc đó mới có request mạng mang dữ liệu.

### Mỗi lần tạo có thể cho URL khác

Gọi createObjectURL() nhiều lần với cùng một Blob vẫn tạo các URL riêng:

    const blob = new Blob(["same data"]);

    const firstUrl = URL.createObjectURL(blob);
    const secondUrl = URL.createObjectURL(blob);

    console.log(firstUrl === secondUrl); // false

Mỗi URL cần được quản lý và revoke riêng. Không gọi createObjectURL() lặp lại trong render hoặc vòng lặp mà không lưu reference và cleanup.

## 3. Origin và storage partitioning của Blob URL

Blob URL được gắn với origin của môi trường tạo URL. Ví dụ trang:

    https://app.example.test

tạo URL:

    blob:https://app.example.test/<identifier>

Blob URL này không tự trở thành một origin độc lập chỉ vì có scheme blob:. Nội dung được nạp từ Blob URL thường mang origin của creator, theo các quy tắc của browser.

Điều này rất quan trọng khi Blob chứa HTML hoặc JavaScript: tạo Blob URL không tự cô lập nội dung đó khỏi origin ứng dụng.

### Blob URL không phải URL public

Không thể coi Blob URL như một URL server để chia sẻ bền vững:

- URL gắn với mapping trong browser/runtime tạo nó.
- URL có thể không dùng được trong context khác.
- Browser áp dụng giới hạn same-origin và storage partitioning.
- URL bị revoke hoặc môi trường kết thúc thì mapping không còn khả dụng.
- URL không thể thay thế API upload, object storage hoặc signed URL.

### Storage partitioning

Browser hiện đại có thể phân vùng quyền truy cập Blob URL theo storage key, bao gồm origin và một số ngữ cảnh top-level site. Vì vậy, việc một URL được tạo trong một context không bảo đảm context khác, dù có URL string, sẽ đọc được dữ liệu.

Quy tắc cụ thể khác nhau theo browser và loại thao tác. Navigation top-level tới Blob URL có thể có cách xử lý khác với fetch hoặc việc nhúng tài nguyên. Không dùng Blob URL như cơ chế chia sẻ cross-site.

### Blob URL từ opaque origin

Nếu môi trường tạo có opaque origin, phần origin trong chuỗi Blob URL có thể được biểu diễn là null. Không suy luận rằng blob:null là một origin chung có thể truy cập tùy ý. Browser vẫn áp dụng quy tắc truy cập và partitioning.

### Blob URL không phải access control

URL có định danh khó đoán không có nghĩa là cơ chế phân quyền. Không dùng Blob URL làm secret token, session ID hoặc đường dẫn truy cập tài nguyên server. Nếu URL bị lộ, người khác có thể thử sử dụng trong phạm vi browser context mà policy cho phép.

## 4. Tạo và thu hồi Blob URL

### Tạo URL

    const blob = new Blob(
      ["Hello from browser"],
      { type: "text/plain" }
    );

    const objectUrl = URL.createObjectURL(blob);

### Thu hồi URL

    URL.revokeObjectURL(objectUrl);

Sau khi revoke, những lần dereference tiếp theo của URL sẽ thất bại. Hãy revoke khi ứng dụng chắc chắn không còn cần URL.

Không revoke quá sớm. Nếu image, video, download hoặc worker chưa kịp đọc URL, thao tác revoke có thể làm việc tải dữ liệu thất bại.

### Khi nào nên revoke?

| Use case | Thời điểm cleanup |
| --- | --- |
| Image preview | Khi ảnh được thay thế, component bị unmount hoặc preview không còn cần |
| Audio/video preview | Khi đổi nguồn hoặc kết thúc playback/capture |
| Download | Sau khi browser đã có thời gian tiếp nhận URL; không có event hoàn tất download phổ quát cho anchor click |
| Worker | Sau khi Worker đã được khởi tạo thành công, nếu không cần URL để tạo Worker lần nữa |
| Document preview | Khi đóng preview hoặc thay tài liệu |
| File tạm trong SPA | Khi state sở hữu URL bị xóa hoặc component kết thúc vòng đời |

### Không có download-complete event chung cho anchor

Browser không cung cấp một sự kiện chuẩn, phổ quát cho biết download do anchor click đã hoàn tất ghi file. Revoke ngay lập tức có thể gây race. Có thể giữ URL trong thời gian đủ dài rồi revoke theo cleanup policy, hoặc giữ tới khi trang/component kết thúc vòng đời.

Một timeout là heuristic, không phải bằng chứng download đã hoàn tất. Chọn thời gian phù hợp với ứng dụng và tránh giữ hàng nghìn URL không cần thiết.

### Quản lý nhiều URL

Nếu tạo nhiều preview, lưu URL theo từng item và revoke khi item bị xóa:

    const previewUrls = new Map();

    function addPreview(id, blob) {
      const url = URL.createObjectURL(blob);
      previewUrls.set(id, url);
      return url;
    }

    function removePreview(id) {
      const url = previewUrls.get(id);
      if (url) {
        URL.revokeObjectURL(url);
        previewUrls.delete(id);
      }
    }

Khi đóng trang hoặc hủy toàn bộ danh sách, duyệt các URL còn lại và revoke từng URL.

## 5. Preview ảnh bằng Blob URL

Một use case phổ biến là hiển thị ảnh người dùng vừa chọn trước khi upload.

HTML:

    <input id="image-file" type="file" accept="image/*">
    <img id="image-preview" alt="Ảnh xem trước">

JavaScript:

    const input = document.querySelector("#image-file");
    const preview = document.querySelector("#image-preview");
    let currentObjectUrl = null;

    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file) return;

      if (currentObjectUrl) {
        URL.revokeObjectURL(currentObjectUrl);
      }

      currentObjectUrl = URL.createObjectURL(file);
      preview.src = currentObjectUrl;
    });

Khi thay file, revoke URL cũ để giải phóng mapping và tài nguyên mà browser không còn cần.

### Chờ ảnh load trước khi thay đổi UI

Có thể theo dõi load/error:

    preview.addEventListener("load", () => {
      showPreviewReady();
    });

    preview.addEventListener("error", () => {
      showPreviewError();
    });

Không nhất thiết revoke ngay khi load nếu người dùng còn cần mở ảnh, lưu ảnh hoặc tương tác với preview. Hãy revoke khi preview bị thay thế hoặc đóng.

### Giới hạn file preview

Thuộc tính accept chỉ là gợi ý cho file picker. Server và ứng dụng vẫn phải kiểm tra:

- Kích thước file.
- Định dạng được phép.
- Signature bytes hoặc nội dung thực tế nếu cần.
- Quyền upload và quyền xem.
- Nội dung có active behavior hay không.

Không tin file.type hoặc extension do người dùng cung cấp.

### SVG và ảnh không tin cậy

SVG là định dạng XML có khả năng chứa nội dung chủ động trong một số ngữ cảnh. Cách browser xử lý SVG qua img, object, iframe hoặc navigation có thể khác nhau. Không coi việc preview qua Blob URL là sanitizer.

Nếu không cần vector interaction, cân nhắc rasterize ảnh ở server hoặc dùng định dạng raster được kiểm tra. Tránh mở SVG không tin cậy như document cùng origin ứng dụng.

## 6. Tạo file download từ Blob

Blob URL có thể được gắn vào anchor để tải dữ liệu do browser tạo:

    function downloadText(text, filename) {
      const blob = new Blob([text], {
        type: "text/plain;charset=utf-8"
      });

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = filename;
      link.click();

      // Cleanup phải đủ muộn để browser tiếp nhận URL.
      setTimeout(() => {
        URL.revokeObjectURL(url);
      }, 60000);
    }

Thời gian trong ví dụ chỉ là một heuristic. Tùy browser và loại download, ứng dụng có thể chọn giữ URL tới khi người dùng đóng view hoặc khi component cleanup. Không có API anchor download phổ quát báo hoàn tất.

### Tên file cũng cần an toàn

Không đưa dữ liệu không tin cậy trực tiếp vào filename:

    link.download = userSuppliedName;

Filename có thể chứa ký tự điều khiển, path separator, tên gây nhầm lẫn hoặc phần mở rộng giả. Dùng tên do ứng dụng tạo hoặc sanitize theo quy tắc hệ điều hành và định dạng mục tiêu.

### CSV formula injection

Nếu Blob chứa CSV được mở bằng spreadsheet, cell bắt đầu bằng các ký tự như =, +, - hoặc @ có thể được một số ứng dụng hiểu là công thức. Khi export dữ liệu do người dùng kiểm soát, cần escape hoặc prefix theo chính sách tương thích spreadsheet để giảm nguy cơ formula injection.

### User activation

Download nên bắt đầu từ thao tác người dùng rõ ràng. Browser có thể chặn nhiều download hoặc download tự động khi không có user activation. Nếu Blob được tạo sau một thao tác bất đồng bộ và click tổng hợp bị chặn, hãy hiển thị nút tải để người dùng click sau khi file đã sẵn sàng.

## 7. Blob URL cho audio và video

Blob URL có thể làm nguồn cho audio/video element:

    const video = document.querySelector("video");
    const videoUrl = URL.createObjectURL(videoFile);

    video.src = videoUrl;
    video.load();

Khi đổi file hoặc kết thúc preview:

    video.pause();
    video.removeAttribute("src");
    video.load();
    URL.revokeObjectURL(videoUrl);

Với file media lớn, Blob URL vẫn tham chiếu tới Blob đã có sẵn. Nếu dữ liệu phải được tải toàn bộ vào Blob trước, ứng dụng có thể tốn bộ nhớ hoặc storage tạm. Streaming media qua URL HTTP hoặc MediaSource có thể phù hợp hơn tùy use case.

### Blob URL và MediaSource

URL.createObjectURL() cũng từng được dùng để tạo URL cho MediaSource. Các API media hiện đại có những cách gắn MediaSource trực tiếp hơn; hãy theo hướng dẫn tương thích của browser mục tiêu. Không mặc định Blob URL là lựa chọn tối ưu cho mọi luồng streaming.

### Không để URL sống sau khi kết thúc media

Khi người dùng đóng player, đổi nguồn hoặc rời trang:

- Pause media.
- Gỡ src hoặc srcObject phù hợp.
- Dừng track nếu nguồn là MediaStream.
- Revoke Blob URL khi không còn consumer.
- Xóa reference giữ Blob nếu không còn cần.

Gỡ URL khỏi element và revoke mapping là hai bước quản lý khác nhau.

## 8. Blob URL và Web Worker

Một ứng dụng có thể tạo Worker từ JavaScript Blob:

    const workerCode = [
      "self.onmessage = (event) => {",
      "  const result = event.data * 2;",
      "  self.postMessage(result);",
      "};"
    ].join("\n");

    const workerBlob = new Blob(
      [workerCode],
      { type: "text/javascript" }
    );

    const workerUrl = URL.createObjectURL(workerBlob);
    const worker = new Worker(workerUrl);

    URL.revokeObjectURL(workerUrl);

Sau khi Worker đã được khởi tạo, browser đã tiếp nhận script nguồn; có thể revoke URL để không giữ mapping lâu hơn cần thiết. Nếu Worker chưa tạo thành công, cần xử lý lỗi và cleanup phù hợp.

### CSP worker-src

Nếu CSP chặn Worker từ Blob URL, Console có thể báo vi phạm worker-src. Chỉ cho phép blob: trong directive cần thiết:

    Content-Security-Policy: default-src 'self'; worker-src 'self' blob:

Không thêm blob: vào script-src một cách rộng rãi chỉ để làm Worker hoạt động. worker-src là directive dành riêng cho nguồn Worker; cấu hình tối thiểu theo ứng dụng.

### Service Worker không hỗ trợ createObjectURL()

URL.createObjectURL() và revokeObjectURL() không khả dụng trong Service Worker global scope do nguy cơ giữ tài nguyên và leak. Nếu cần tạo file hoặc phản hồi trong Service Worker, hãy thiết kế bằng Response/Blob, Cache API hoặc streaming phù hợp thay vì dựa vào Blob URL.

Dedicated Worker và Shared Worker có thể hỗ trợ object URL theo browser; luôn kiểm tra API trong môi trường triển khai.

## 9. Blob URL và data URL khác nhau thế nào?

| Đặc điểm | Blob URL | Data URL |
| --- | --- | --- |
| Dữ liệu | Tham chiếu tới Blob/MediaSource trong browser | Dữ liệu được nhúng trực tiếp trong chuỗi URL |
| Kích thước URL | Thường ngắn | Có thể rất dài |
| Tạo | URL.createObjectURL() | Nối prefix data: với dữ liệu đã encode |
| Bộ nhớ | Browser quản lý mapping và dữ liệu Blob | Chuỗi URL chứa nội dung, thường cần encode |
| Cleanup | Cần revoke object URL | Không có revoke API tương đương |
| Use case | Preview file, download, worker source | Icon nhỏ hoặc dữ liệu nhúng nhỏ, có kiểm soát |

### FileReader khác Blob URL thế nào?

FileReader đọc bytes của Blob/File vào JavaScript, ví dụ thành Data URL, text hoặc ArrayBuffer. Blob URL tạo một reference để element hoặc API khác đọc Blob mà không cần chuyển toàn bộ dữ liệu thành một chuỗi JavaScript.

Ví dụ FileReader:

    const reader = new FileReader();
    reader.onload = () => {
      image.src = reader.result;
    };
    reader.readAsDataURL(file);

Với preview ảnh, Blob URL thường tránh bước mã hóa toàn bộ file thành Base64 và không tạo chuỗi Data URL lớn. FileReader phù hợp khi ứng dụng thực sự cần bytes hoặc text trong JavaScript để phân tích, biến đổi hay gửi qua một protocol khác.

### Data URL có thể làm URL phình lớn

Ví dụ:

    const dataUrl = "data:text/plain;base64,SGVsbG8=";

Base64 làm dữ liệu lớn hơn so với bytes gốc và toàn bộ nội dung nằm trong chuỗi URL. Không dùng data URL cho file lớn.

### Blob URL không phải cách mã hóa dữ liệu

Blob URL chỉ là reference do browser cấp. Nó không mã hóa nội dung, không ẩn dữ liệu khỏi JavaScript cùng quyền và không cung cấp authorization.

## 10. Blob URL và Fetch/CORS

### Fetch Blob từ same-origin

Ví dụ:

    const response = await fetch("/api/export");
    if (!response.ok) {
      throw new Error("Request failed");
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);

Server vẫn phải xác thực và authorization. Blob URL chỉ được tạo sau khi JavaScript đã đọc được response.

### Fetch Blob từ cross-origin

Nếu gọi:

    const response = await fetch(
      "https://files.example.test/report.pdf"
    );

browser áp dụng CORS. JavaScript chỉ đọc được response nếu server cho phép origin theo CORS policy. Không thể dùng createObjectURL() để vượt CORS hoặc đọc response bị browser chặn.

Luồng đúng:

1. Browser gửi Fetch request.
2. Server trả CORS headers phù hợp.
3. Fetch resolve với response mà script được phép đọc.
4. Ứng dụng chuyển response thành Blob.
5. Ứng dụng tạo Blob URL.

Nếu bước CORS thất bại, ứng dụng không có Blob chứa response bị chặn để tạo URL.

### Blob URL không phải proxy cross-origin

Tạo Blob URL từ dữ liệu đã được đọc hợp lệ không thay đổi nguồn gốc hoặc quyền truy cập của request ban đầu. Không dùng Blob URL để biến một URL cross-origin thành tài nguyên same-origin có thể đọc tùy ý.

### Credential và CORS

Nếu Fetch cross-origin cần cookie:

    fetch("https://files.example.test/report.pdf", {
      credentials: "include"
    });

Server phải cấu hình CORS credential phù hợp, gồm origin cụ thể và Access-Control-Allow-Credentials: true. Cookie vẫn chịu SameSite, Secure và third-party cookie policy. CORS không thay authorization.

## 11. Blob chứa HTML/SVG: ranh giới XSS

Đây là phần bảo mật quan trọng nhất của Blob URL.

Tạo HTML từ dữ liệu không tin cậy:

    const html = [
      "<h1>", userSuppliedTitle, "</h1>",
      "<p>", userSuppliedMessage, "</p>"
    ].join("");

    const blob = new Blob([html], {
      type: "text/html"
    });

    const url = URL.createObjectURL(blob);

    window.open(url);

Nếu dữ liệu được ghép vào HTML mà không encode/sanitize, nội dung có thể tạo XSS. Blob URL không tự sanitize và document được mở có thể mang origin của môi trường tạo Blob URL.

### Vì sao có thể nguy hiểm?

- Blob URL không tạo một origin sandbox mới theo mặc định.
- HTML có thể chứa script hoặc event handler.
- Script có thể chạy với quyền của document theo origin được gắn với Blob URL.
- Nội dung có thể truy cập tài nguyên same-origin mà origin đó được phép.
- XSS có thể đọc dữ liệu trong trang hoặc thực hiện request bằng quyền hiện có.

Không dùng Blob URL như cách an toàn để mở HTML do người dùng cung cấp.

### Dùng textContent khi chỉ cần hiển thị text

Nếu dữ liệu chỉ là văn bản:

    const output = document.createElement("pre");
    output.textContent = userSuppliedMessage;
    document.body.append(output);

Không cần tạo HTML Blob hoặc gán innerHTML cho use case hiển thị text.

### Nếu cần preview HTML

Ưu tiên một trong các thiết kế:

- Render nội dung đã được sanitize bằng sanitizer đáng tin cậy và allowlist chặt.
- Phục vụ preview từ một site/origin riêng biệt không chia sẻ cookie với ứng dụng.
- Dùng iframe sandbox với quyền tối thiểu và không cấp allow-same-origin/allow-scripts cùng lúc cho nội dung không tin cậy.
- Không để preview truy cập API nội bộ hoặc session của ứng dụng chính.

Nếu cần script trong preview, phải thiết kế sandbox và origin isolation riêng; không nới sandbox cho nội dung cùng origin chính một cách máy móc.

### SVG cũng cần được xem là nội dung chủ động

SVG có thể chứa event handler, liên kết và các khả năng tương tác khác tùy ngữ cảnh. SVG hiển thị qua img thường bị hạn chế hơn so với SVG được mở như document hoặc nhúng qua object/iframe. Không suy rộng một hành vi của img sang mọi cách sử dụng SVG.

Với SVG không tin cậy:

- Không mở trực tiếp như document cùng origin ứng dụng.
- Không nhúng qua object/embed tùy tiện.
- Cân nhắc rasterize hoặc sanitize bằng thư viện phù hợp.
- Dùng attachment hoặc origin cô lập nếu chỉ cần phân phối file.

## 12. CSP và Blob URL

Content Security Policy kiểm soát nguồn được phép cho từng loại tài nguyên. Nếu ứng dụng cần Blob URL, chỉ cho phép trong directive tương ứng.

Ví dụ preview ảnh:

    Content-Security-Policy: default-src 'self'; img-src 'self' blob:; object-src 'none'

Ví dụ audio/video:

    Content-Security-Policy: default-src 'self'; media-src 'self' blob:; object-src 'none'

Ví dụ Worker:

    Content-Security-Policy: default-src 'self'; worker-src 'self' blob:

Ví dụ iframe preview Blob:

    Content-Security-Policy: default-src 'self'; frame-src 'self' blob:; object-src 'none'

Đây là các ví dụ rời theo use case, không phải một policy tổng hợp áp dụng nguyên trạng cho mọi ứng dụng.

### Chỉ mở blob: ở directive cần thiết

Không thêm blob: vào default-src hoặc nhiều directive cùng lúc nếu không cần. Hãy xác định tài nguyên nào dùng Blob URL:

- img-src cho ảnh.
- media-src cho audio/video.
- worker-src cho Worker.
- frame-src cho iframe/document.
- object-src cho object/embed nếu sản phẩm còn dùng các element đó.

Giữ object-src 'none' nếu không cần plugin/object embedding. Việc cho phép blob: ở một directive không đồng nghĩa nên cho phép script Blob trong script-src.

### CSP không phải sanitizer

CSP có thể chặn một số hành vi script hoặc nguồn tải, nhưng không biến dữ liệu HTML không tin cậy thành dữ liệu an toàn. Vẫn cần output encoding, sanitization và origin isolation đúng.

## 13. Blob URL và memory management

Blob có thể chứa lượng dữ liệu lớn. Object URL tạo thêm mapping mà browser phải quản lý. Nếu ứng dụng quên revoke, dữ liệu và tài nguyên có thể được giữ lâu hơn cần thiết.

### Dấu hiệu leak

- Mỗi lần chọn ảnh lại tạo URL mới nhưng không revoke URL cũ.
- Component render tạo URL mới ở mỗi lần cập nhật.
- Người dùng đóng modal nhưng preview URL vẫn được giữ trong state/global map.
- Tạo URL trong vòng lặp để export nhiều file và không cleanup.
- Worker đã kết thúc nhưng Blob URL vẫn còn.

### Nguyên tắc quản lý

1. Tạo URL khi thực sự cần.
2. Lưu URL cùng owner/lifecycle rõ ràng.
3. Revoke URL cũ khi thay nội dung.
4. Revoke khi component hoặc view kết thúc.
5. Không revoke trước khi consumer đã đọc URL.
6. Xóa reference Blob nếu không còn cần.
7. Đo memory trong DevTools khi xử lý file lớn hoặc nhiều preview.

### Blob.slice() và xử lý từng phần

Blob có thể tạo phần dữ liệu nhỏ:

    const firstChunk = largeBlob.slice(0, 1024 * 1024);

Điều này hữu ích khi parser hoặc protocol chỉ cần một đoạn bytes. Tuy nhiên, tạo slice không tự biến toàn bộ pipeline thành streaming; cần xem các API tiếp theo có đọc toàn bộ dữ liệu hay không.

### Dùng Blob.stream() khi phù hợp

    const reader = blob.stream().getReader();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      processChunk(value);
    }

Đọc stream giúp xử lý từng chunk mà không cần gọi arrayBuffer() hoặc text() cho toàn bộ Blob trước. Nhưng nếu Blob đã được tạo từ response toàn bộ trong memory, lợi ích memory có thể khác so với đọc trực tiếp response.body.

### Với file lớn, cân nhắc stream từ nguồn

Nếu nguồn dữ liệu là HTTP response lớn, cân nhắc đọc response.body stream hoặc dùng native download/navigation để browser quản lý dữ liệu. Tránh tải toàn bộ file vào JavaScript rồi mới tạo Blob URL nếu không cần biến đổi nội dung.

## 14. Blob URL trong SPA và component lifecycle

Trong SPA, component có thể mount/unmount nhiều lần. Blob URL cần được cleanup cùng component sở hữu nó.

Ví dụ framework-neutral:

    let previewUrl = null;

    function setPreview(file, imageElement) {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }

      if (!file) {
        imageElement.removeAttribute("src");
        return;
      }

      previewUrl = URL.createObjectURL(file);
      imageElement.src = previewUrl;
    }

    function disposePreview(imageElement) {
      imageElement.removeAttribute("src");

      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }
    }

### React-style effect

    useEffect(() => {
      if (!file) return;

      const url = URL.createObjectURL(file);
      setPreviewUrl(url);

      return () => {
        URL.revokeObjectURL(url);
      };
    }, [file]);

Đây là ví dụ minh họa pattern cleanup. Trong code thực, state cập nhật có thể khiến effect chạy lại; dependency phải ổn định và không tạo URL trong render body.

### Race khi người dùng thay file liên tục

Một số tác vụ bất đồng bộ như decode ảnh hoặc đọc metadata có thể hoàn thành sau khi người dùng đã chọn file mới. Cần gắn generation ID hoặc so sánh URL hiện tại trước khi cập nhật UI:

    let generation = 0;

    async function loadPreview(file) {
      const currentGeneration = ++generation;
      const url = URL.createObjectURL(file);

      try {
        const image = new Image();
        image.src = url;
        await image.decode();

        if (currentGeneration !== generation) {
          URL.revokeObjectURL(url);
          return;
        }

        showImage(image);
      } catch (error) {
        URL.revokeObjectURL(url);
        throw error;
      }
    }

Nếu URL cũ đã được gắn vào UI, cleanup phải gỡ reference cũ đúng thời điểm và không revoke URL đang được consumer hiện tại sử dụng.

## 15. Blob URL, privacy và logging

Blob URL không được gửi tới server chỉ vì được tạo. Tuy nhiên, nó vẫn có thể xuất hiện trong:

- Thanh địa chỉ nếu document điều hướng tới Blob URL.
- Browser history trong một số luồng navigation.
- Console, error report hoặc debug log.
- Analytics nếu code gửi location.href.
- Screenshot hoặc clipboard.
- Message giữa các browsing context.

Không đưa Blob URL vào telemetry nếu không cần. Không coi UUID trong Blob URL là secret có thể thay thế authorization.

### URL blob không phải server URL

Khi browser đọc Blob URL, nó truy cập mapping nội bộ. Web server không nhận HTTP request thông thường cho chính Blob URL đó. Nhưng nếu ứng dụng gửi Blob lên server hoặc gửi chuỗi Blob URL qua API, server chỉ nhận dữ liệu mà client chủ động gửi.

### Không dùng Blob URL lâu dài

Blob URL không phù hợp cho:

- Lưu vào database để người dùng mở sau nhiều ngày.
- Gửi qua email hoặc chat như liên kết tải public.
- Làm URL canonical của file.
- Thay thế object storage.
- Thay thế signed URL hoặc endpoint authorization.

Nếu cần chia sẻ file, upload lên storage/server và cấp URL có authorization, TTL và audit phù hợp.

## 16. Các lỗi và tình huống cần xử lý

| Tình huống | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| URL không tải được | URL đã revoke hoặc context không còn quyền truy cập | Kiểm tra lifecycle và storage partition |
| Preview ảnh lỗi | Blob không phải ảnh hợp lệ hoặc type/nội dung không khớp | Validate file và xử lý error event |
| Worker không khởi tạo | CSP worker-src chặn blob: hoặc script lỗi | Kiểm tra Console, CSP và code Worker |
| Download bị chặn | Thiếu user activation hoặc browser giới hạn automatic download | Yêu cầu click rõ ràng sau khi file sẵn sàng |
| Memory tăng dần | Tạo object URL nhưng không revoke | Gắn cleanup với lifecycle |
| HTML Blob chạy script | Blob URL không phải sandbox | Không mở HTML không tin cậy; sanitize và cô lập origin |
| Cross-origin Fetch thất bại | CORS không cho script đọc response | Sửa CORS server theo origin được phép |
| Blob URL không dùng được ở context khác | Khác origin/storage key hoặc URL đã revoke | Tạo URL trong context sử dụng và truyền dữ liệu theo API phù hợp |
| Service Worker thiếu createObjectURL | API không được hỗ trợ trong Service Worker | Dùng Response/Blob/stream phù hợp |

## 17. Kiểm thử Blob URL bằng Chrome DevTools

Thực hiện trong local/staging với file test. Không dùng nội dung HTML độc hại hoặc dữ liệu nhạy cảm.

### Bước 1 — Tạo và xem Blob URL

1. Mở DevTools → Console.
2. Tạo Blob text nhỏ.
3. Gọi URL.createObjectURL().
4. In URL ra Console.
5. Dùng URL làm href hoặc src trong trang test.
6. Xác nhận dữ liệu được browser đọc mà không có request tới server cho Blob URL.

### Bước 2 — Kiểm tra revoke

1. Tạo Blob URL.
2. Đọc nội dung qua consumer test.
3. Gọi URL.revokeObjectURL().
4. Thử dereference lại URL.
5. Xác nhận thao tác đọc mới thất bại.
6. Kiểm tra consumer đã load trước đó có hành vi riêng theo loại tài nguyên.

### Bước 3 — Kiểm tra preview lifecycle

1. Chọn ảnh test.
2. Tạo preview.
3. Chọn ảnh khác.
4. Xác nhận URL cũ được revoke.
5. Đóng component/modal.
6. Xác nhận URL hiện tại được revoke và reference được xóa.

### Bước 4 — Kiểm tra CSP

1. Chạy preview ảnh khi img-src không cho blob:.
2. Quan sát Console.
3. Thêm blob: chỉ vào img-src.
4. Thử Worker với worker-src không cho blob: rồi cho phép trong staging.
5. Xác nhận policy không mở blob: vào script-src nếu không cần.

### Bước 5 — Kiểm tra active content an toàn

Trong một origin lab riêng:

1. Tạo HTML Blob chỉ chứa nội dung vô hại.
2. Quan sát origin khi mở Blob URL.
3. Xác nhận không dùng dữ liệu người dùng để nối vào HTML.
4. Thử preview trong iframe sandbox với quyền tối thiểu.
5. Xác nhận ứng dụng chính không chia sẻ session cookie với preview origin.

Không thử payload đánh cắp cookie hoặc dữ liệu thật. Mục tiêu là kiểm tra origin và sandbox boundary.

### Bước 6 — Kiểm tra memory và Worker

1. Tạo nhiều preview có kích thước nhỏ trong test.
2. Thay và xóa preview.
3. Quan sát Memory/Performance nếu cần.
4. Xác nhận URL được revoke.
5. Tạo Worker từ Blob URL và terminate Worker.
6. Xác nhận URL cleanup theo lifecycle.
7. Kiểm tra Service Worker context không dựa vào createObjectURL().

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Tạo Blob URL | Blob text hợp lệ | URL có scheme blob: được tạo |
| Tạo nhiều URL | Cùng một Blob, gọi hai lần | Hai URL có thể khác nhau; quản lý từng URL |
| Đọc trước revoke | URL còn sống | Consumer đọc được dữ liệu |
| Đọc sau revoke | URL đã revoke | Dereference mới thất bại |
| Image preview | File ảnh hợp lệ | Ảnh hiển thị |
| File giả MIME | type là image nhưng bytes không phải ảnh | Preview lỗi hoặc bị từ chối theo validation |
| Replace preview | Chọn file mới | URL cũ được revoke sau khi không còn dùng |
| Component unmount | View kết thúc | URL do component sở hữu được cleanup |
| Download | User click nút tải | Browser bắt đầu download theo policy |
| Async download | Blob sẵn sàng sau await | Nếu activation hết hạn, UI yêu cầu click lần nữa |
| CSP img-src | Không cho blob: | Browser chặn image Blob URL |
| CSP worker-src | Không cho blob: | Browser chặn Worker Blob URL |
| HTML Blob | Mở document Blob | Không giả định có sandbox; origin cần được đánh giá |
| Cross-origin Fetch | Server không cho CORS | Script không đọc được response để tạo Blob |
| Worker | Tạo Worker từ Blob URL | Worker chạy nếu policy/API cho phép |
| Service Worker | Gọi createObjectURL | API không khả dụng trong Service Worker |
| Large Blob | File lớn được giữ toàn bộ | Đánh giá memory; cân nhắc streaming/native download |
| URL cleanup | Revoke mọi URL khi đóng view | Không còn mapping do view sở hữu |

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ Blob URL là URL server | Thiết kế chia sẻ hoặc lưu trữ sai | Dùng object storage hoặc endpoint server cho chia sẻ lâu dài |
| Không revoke URL | Mapping và tài nguyên bị giữ lâu | Cleanup theo lifecycle |
| Revoke ngay sau khi tạo | Consumer chưa đọc được dữ liệu | Revoke sau khi consumer đã tiếp nhận |
| Tạo URL trong mỗi lần render | Tăng URL và memory leak | Tạo trong effect/event và lưu reference |
| Nghĩ Blob type xác minh bytes | File giả MIME vẫn được gắn type mong muốn | Validate nội dung riêng |
| Nghĩ Blob URL tạo origin sandbox | HTML Blob có thể chạy trong origin creator | Dùng sandbox và origin cô lập |
| Dùng Blob URL để mở HTML không tin cậy | DOM XSS hoặc truy cập cùng origin | textContent, sanitizer và sandbox |
| Cho blob: vào mọi CSP directive | Mở rộng nguồn tài nguyên không cần | Chỉ thêm vào directive cần dùng |
| Dùng Blob URL để vượt CORS | Browser vẫn chặn đọc response cross-origin | Cấu hình CORS server đúng |
| Dùng Blob cho file rất lớn | Tốn memory/storage tạm | Native download hoặc streaming |
| Revoke download URL ngay lập tức | Browser có thể chưa nhận URL | Cleanup có trì hoãn hoặc theo lifecycle |
| Nghĩ download có event hoàn tất chuẩn | Revoke theo event không tồn tại | Dùng cleanup heuristic có giới hạn |
| Chia sẻ Blob URL qua email | URL không bền và context khác có thể không truy cập | Upload file và cấp URL có quyền |
| Dùng createObjectURL trong Service Worker | API không hỗ trợ trong context này | Dùng Response/stream |
| Tin accept attribute của file input | Người dùng có thể chọn file khác hoặc giả MIME | Validate ở client và server |

## 19. Câu hỏi củng cố

**Câu 1.** Blob và Blob URL khác nhau thế nào?

**Giải đáp:** Blob là object chứa bytes; Blob URL là reference tạm do browser tạo để consumer truy cập Blob.

**Câu 2.** API nào tạo và thu hồi Blob URL?

**Giải đáp:** URL.createObjectURL() tạo URL; URL.revokeObjectURL() thu hồi mapping.

**Câu 3.** Blob URL có phải URL HTTP trên server không?

**Giải đáp:** Không. Browser tra mapping nội bộ; việc tạo URL không upload bytes.

**Câu 4.** Có nên revoke URL ngay sau khi gắn vào img.src không?

**Giải đáp:** Không nên revoke trước khi consumer đã đọc URL. Giữ URL trong thời gian preview còn được sử dụng rồi cleanup khi thay ảnh hoặc đóng view.

**Câu 5.** Blob URL có tự sandbox HTML không?

**Giải đáp:** Không. Nội dung HTML có thể mang origin của creator. Cần tránh HTML không tin cậy hoặc dùng sanitizer, sandbox và origin cô lập.

**Câu 6.** Có thể dùng Blob URL để vượt CORS không?

**Giải đáp:** Không. JavaScript phải đọc được response cross-origin theo CORS trước khi tạo Blob từ dữ liệu đó.

**Câu 7.** Vì sao không nên dùng Blob URL cho file rất lớn?

**Giải đáp:** Nếu phải giữ toàn bộ dữ liệu trong Blob, ứng dụng có thể tiêu tốn nhiều memory/storage tạm. Native download hoặc streaming có thể phù hợp hơn.

**Câu 8.** Blob URL có hoạt động trong Service Worker không?

**Giải đáp:** URL.createObjectURL() không khả dụng trong Service Worker do rủi ro giữ tài nguyên và leak.

**Câu 9.** CSP cần directive nào cho Blob URL ảnh?

**Giải đáp:** img-src. Chỉ thêm blob: vào directive cần thiết, không mở rộng default-src hoặc script-src một cách tùy tiện.

**Câu 10.** Có thể chia sẻ Blob URL qua email để người nhận tải file không?

**Giải đáp:** Không nên. Blob URL gắn với browser context và lifecycle; hãy upload file lên server/storage rồi cấp URL có authorization phù hợp.

## 20. Tổng kết

Blob là object chứa dữ liệu thô; Blob URL là reference tạm do browser tạo bằng URL.createObjectURL(). URL này cho phép preview, phát media, tải file hoặc tạo Worker mà không cần upload dữ liệu lên server. Nó gắn với origin và storage context của môi trường tạo, không phải URL public hoặc cơ chế phân quyền.

Ứng dụng phải quản lý vòng đời bằng URL.revokeObjectURL() khi consumer không còn cần URL. Không revoke quá sớm, nhưng cũng không giữ URL vô thời hạn. Với file lớn, cân nhắc streaming hoặc native download để tránh giữ toàn bộ dữ liệu trong JavaScript memory.

Blob URL không sanitize HTML/SVG và không tạo sandbox tự động. HTML Blob có thể chạy trong origin creator, vì vậy không ghép dữ liệu không tin cậy vào HTML rồi mở Blob URL. Dùng textContent, sanitizer, iframe sandbox và origin cô lập theo nhu cầu. Cấu hình CSP chỉ cho phép blob: ở directive cần thiết; CORS vẫn phải được đáp ứng trước khi JavaScript có thể đọc response cross-origin để tạo Blob.

## Tài liệu tham khảo

1. [File API — W3C](https://www.w3.org/TR/FileAPI/): Blob, File, object URL, createObjectURL và revokeObjectURL.
2. [MDN — URL.createObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/createObjectURL_static): tạo URL cho Blob hoặc MediaSource.
3. [MDN — URL.revokeObjectURL()](https://developer.mozilla.org/en-US/docs/Web/API/URL/revokeObjectURL_static): thu hồi object URL.
4. [MDN — Blob](https://developer.mozilla.org/en-US/docs/Web/API/Blob): dữ liệu Blob và các phương thức đọc.
5. [MDN — Using object URLs](https://developer.mozilla.org/en-US/docs/Web/API/File_API/Using_files_from_web_applications#using_object_urls): sử dụng object URL trong ứng dụng web.
6. [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): giới hạn nguồn tài nguyên và Worker.
7. [MDN — Web Workers API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Workers_API): Worker, script và môi trường thực thi.
8. [OWASP — DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html): xử lý dữ liệu không tin cậy trong DOM.
