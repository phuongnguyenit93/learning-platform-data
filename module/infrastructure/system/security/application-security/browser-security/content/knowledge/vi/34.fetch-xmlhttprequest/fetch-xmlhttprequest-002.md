# XMLHttpRequest: gửi request bất đồng bộ và kiểm soát ranh giới bảo mật

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của XMLHttpRequest (XHR) trong việc gửi HTTP request từ JavaScript.
2. Mô tả vòng đời request qua readyState và các event load, error, timeout, abort, progress.
3. Dùng open, setRequestHeader, responseType, timeout và send đúng thứ tự.
4. Phân biệt lỗi HTTP với lỗi mạng/CORS và xử lý status chính xác.
5. Cấu hình withCredentials và hiểu cookie, Same-Origin Policy, CORS và preflight.
6. Upload file bằng FormData, theo dõi tiến độ và xử lý hủy request.
7. Phòng XSS, CSRF, lộ dữ liệu và lỗi xử lý response không an toàn.
8. Kiểm thử XHR bằng Chrome DevTools và so sánh XHR với Fetch API.

> **Bối cảnh:** Module Browser Security phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types và security headers. Bài này tập trung vào XMLHttpRequest, cách browser thực hiện request, đọc response và áp dụng các chính sách bảo mật.

## 1. XMLHttpRequest là gì?

XMLHttpRequest (XHR) là API của browser cho phép JavaScript gửi HTTP request và nhận response mà không cần điều hướng toàn bộ trang. Tên API có chữ XML từ lịch sử phát triển, nhưng XHR có thể xử lý JSON, text, Blob, ArrayBuffer, document và nhiều kiểu response khác.

XHR thường được dùng để:

- Đọc dữ liệu JSON từ backend.
- Gửi dữ liệu biểu mẫu.
- Upload file và theo dõi tiến độ.
- Tải file nhị phân.
- Hủy request hoặc đặt timeout.
- Gửi request cross-origin khi server cho phép qua CORS.

Ví dụ GET JSON:

    const xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/products", true);
    xhr.responseType = "json";

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        console.log(xhr.response);
      } else {
        console.error("HTTP status:", xhr.status);
      }
    };

    xhr.onerror = () => {
      console.error("Network error or request blocked");
    };

    xhr.send();

Tham số true trong open() yêu cầu request bất đồng bộ. Đây là chế độ nên dùng cho ứng dụng web.

### XHR không bỏ qua chính sách bảo mật của browser

XHR vẫn chịu:

- Same-Origin Policy.
- CORS đối với request cross-origin.
- Cookie policy, SameSite, Secure và các giới hạn credential.
- CSP connect-src.
- Mixed content rules.
- Secure context và các điều kiện mạng của browser.

Việc dùng XHR thay Fetch không tạo quyền đọc dữ liệu từ origin khác. Server vẫn phải xác thực và authorization cho mọi endpoint.

## 2. Tạo và gửi request: open(), setRequestHeader(), send()

Một request XHR cơ bản có ba bước:

1. Tạo object XMLHttpRequest.
2. Gọi open() để thiết lập method và URL.
3. Cấu hình header, responseType, timeout, event listener rồi gọi send().

Ví dụ:

    const xhr = new XMLHttpRequest();

    xhr.open("POST", "/api/preferences", true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Accept", "application/json");

    xhr.responseType = "json";
    xhr.timeout = 8000;

    xhr.send(JSON.stringify({
      theme: "dark"
    }));

### open(method, url, async, username, password)

- method: HTTP method như GET, POST, PUT, PATCH hoặc DELETE.
- url: URL request; thường dùng URL tương đối cùng origin cho API nội bộ.
- async: true để bất đồng bộ; nếu bỏ qua, mặc định là true.
- username/password: tham số xác thực HTTP cũ; tránh nhúng credential vào code hoặc URL.

open() chuẩn bị request và chuyển readyState sang OPENED. Gọi open() lại trên một XHR đang dùng sẽ reset trạng thái request trước đó.

Không nối chuỗi URL từ dữ liệu không tin cậy mà không kiểm tra. Với query parameter, dùng URL và URLSearchParams:

    const url = new URL("/api/search", location.origin);
    url.searchParams.set("q", userSearchText);

    const xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.send();

Không đặt password, bearer token hoặc session secret trong query string; URL có thể xuất hiện trong history, log và telemetry.

### setRequestHeader()

Gọi setRequestHeader() sau open() và trước send():

    xhr.open("POST", "/api/orders", true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.send(JSON.stringify(order));

Gọi setRequestHeader() trước open() hoặc sau send() sẽ gây InvalidStateError.

Một số header bị browser cấm JavaScript tự đặt, ví dụ Host, Cookie, Origin, Content-Length, Connection và các header có prefix Sec- hoặc Proxy-. Browser tự quản lý những header này để bảo vệ protocol và ranh giới bảo mật.

Không cố đặt Cookie bằng setRequestHeader(). Cookie được gửi theo cookie jar và chính sách credential của browser.

### send(body)

GET/HEAD thường gọi send() không có body:

    xhr.open("GET", "/api/profile", true);
    xhr.send();

POST/PUT/PATCH có thể gửi string, FormData, Blob, ArrayBuffer, URLSearchParams hoặc các kiểu body được hỗ trợ.

Nếu gửi JSON, tự serialize và đặt Content-Type phù hợp. Nếu gửi FormData, không tự đặt multipart Content-Type; browser phải tạo boundary:

    const form = new FormData();
    form.append("title", "Báo cáo");
    form.append("attachment", fileInput.files[0]);

    xhr.open("POST", "/api/upload", true);
    xhr.send(form);

## 3. Vòng đời request: readyState

XHR có thuộc tính readyState với năm trạng thái:

| Giá trị | Tên | Ý nghĩa |
| --- | --- | --- |
| 0 | UNSENT | Object đã tạo nhưng chưa gọi open() |
| 1 | OPENED | Đã gọi open(); request có thể được cấu hình và gửi |
| 2 | HEADERS_RECEIVED | Response header đã được nhận |
| 3 | LOADING | Response body đang được nhận |
| 4 | DONE | Request đã hoàn tất hoặc kết thúc do lỗi/abort/timeout |

Theo dõi thay đổi:

    xhr.onreadystatechange = () => {
      console.log("readyState:", xhr.readyState);

      if (xhr.readyState === XMLHttpRequest.DONE) {
        console.log("status:", xhr.status);
      }
    };

readystatechange có thể chạy nhiều lần. Chỉ xử lý response cuối khi readyState là DONE và phải kiểm tra status.

### readyState không phải kết quả thành công

DONE chỉ có nghĩa request đã kết thúc. Nó không có nghĩa HTTP response thành công.

Ví dụ:

- HTTP 200: request hoàn tất và server trả thành công.
- HTTP 404: request hoàn tất nhưng resource không tồn tại.
- HTTP 500: request hoàn tất nhưng server gặp lỗi.
- Network/CORS failure: request có thể kết thúc với status 0 và event error.
- abort hoặc timeout: request kết thúc nhưng không có response hoàn chỉnh để xử lý như thành công.

Không dùng điều kiện readyState === 4 làm điều kiện duy nhất để render dữ liệu.

## 4. Các event của XMLHttpRequest

XHR cung cấp event để theo dõi request:

| Event | Ý nghĩa |
| --- | --- |
| loadstart | Bắt đầu tải |
| progress | Có tiến độ truyền dữ liệu |
| readystatechange | readyState thay đổi |
| load | Hoàn tất trao đổi HTTP ở mức request, kể cả status 4xx/5xx |
| error | Lỗi mạng hoặc request bị browser chặn, ví dụ CORS |
| timeout | Quá thời gian timeout |
| abort | Request bị hủy |
| loadend | Kết thúc sau load, error, timeout hoặc abort |

Ví dụ:

    xhr.addEventListener("loadstart", () => {
      console.log("Request started");
    });

    xhr.addEventListener("load", () => {
      console.log("HTTP exchange completed:", xhr.status);
    });

    xhr.addEventListener("error", () => {
      console.log("Network/CORS failure");
    });

    xhr.addEventListener("timeout", () => {
      console.log("Request timed out");
    });

    xhr.addEventListener("abort", () => {
      console.log("Request aborted");
    });

    xhr.addEventListener("loadend", () => {
      console.log("Request finished");
    });

### load không có nghĩa status 2xx

XHR phát load khi nhận được HTTP response, kể cả response 404 hoặc 500. Trong handler load, phải kiểm tra status:

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        handleSuccess(xhr.response);
      } else {
        handleHttpError(xhr.status);
      }
    });

Event error dành cho lỗi ở tầng mạng hoặc chính sách browser. Do CORS cố ý che response cross-origin không được phép, JavaScript thường không nhận được chi tiết server để phân biệt chính xác nguyên nhân.

## 5. Đọc status và response

### status và statusText

status là mã HTTP:

    if (xhr.status === 204) {
      // No Content
    }

    if (xhr.status >= 200 && xhr.status < 300) {
      // Success
    }

statusText là mô tả dạng text do browser cung cấp; không dùng nó làm logic phân nhánh vì có thể rỗng hoặc khác nhau.

status có thể bằng 0 khi request chưa có response HTTP hợp lệ, bị abort, timeout hoặc bị browser chặn. Không coi status 0 là một mã HTTP server trả về.

### responseType

Đặt responseType trước send():

| Giá trị | Kiểu dữ liệu |
| --- | --- |
| "" hoặc "text" | String |
| "json" | Object/array hoặc null nếu không parse được |
| "blob" | Blob |
| "arraybuffer" | ArrayBuffer |
| "document" | Document trong môi trường được hỗ trợ |

Ví dụ JSON:

    xhr.responseType = "json";

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const data = xhr.response;
      }
    };

Với responseType là json, browser parse JSON cho ứng dụng. Nếu body rỗng hoặc JSON không hợp lệ, response có thể là null. Vẫn cần kiểm tra schema và kiểu dữ liệu trước khi sử dụng.

### responseText

responseText chỉ hợp lệ khi responseType là "" hoặc "text". Đọc responseText khi responseType là json, blob hoặc arraybuffer có thể gây InvalidStateError.

    xhr.responseType = "text";
    xhr.onload = () => {
      const text = xhr.responseText;
    };

### Đọc response header

XHR có:

- getResponseHeader(name): đọc một response header.
- getAllResponseHeaders(): đọc danh sách header mà browser cho phép JavaScript nhìn thấy.

Ví dụ:

    const contentType = xhr.getResponseHeader("Content-Type");
    const etag = xhr.getResponseHeader("ETag");

Với response cross-origin, JavaScript chỉ đọc được các response header safelisted và header server công khai qua Access-Control-Expose-Headers. Set-Cookie là forbidden response-header name; không thể mở nó cho JavaScript bằng Access-Control-Expose-Headers.

## 6. Timeout, abort và quản lý request

### timeout

timeout tính bằng milliseconds:

    xhr.timeout = 10000;

Khi hết thời gian, browser kết thúc request và phát timeout, sau đó loadend. Giá trị mặc định 0 nghĩa là không đặt timeout ở cấp XHR.

Đặt timeout trước send(). Với synchronous XHR trên main thread, các thuộc tính timeout và responseType có giới hạn và có thể gây InvalidAccessError; đây là một lý do nữa để không dùng synchronous XHR.

### abort()

Hủy request:

    const xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/search?q=browser", true);
    xhr.send();

    cancelButton.addEventListener("click", () => {
      xhr.abort();
    });

abort() kết thúc request và phát event abort/loadend. Handler cần phân biệt abort do người dùng với lỗi server để tránh hiển thị thông báo sai.

### Tránh request cũ ghi đè kết quả mới

Khi người dùng gõ tìm kiếm liên tục, request trước có thể trả về sau request mới. Hủy request cũ:

    let activeRequest = null;

    function searchProducts(query) {
      if (activeRequest) {
        activeRequest.abort();
      }

      const url = new URL("/api/search", location.origin);
      url.searchParams.set("q", query);

      const xhr = new XMLHttpRequest();
      activeRequest = xhr;
      xhr.open("GET", url, true);
      xhr.responseType = "json";

      xhr.onload = () => {
        if (activeRequest !== xhr) return;
        if (xhr.status >= 200 && xhr.status < 300) {
          renderResults(xhr.response);
        }
      };

      xhr.send();
    }

Việc so sánh activeRequest với xhr ngăn handler của request cũ cập nhật UI nếu một request khác đã thay thế nó.

## 7. Progress event và upload file

XHR có hai event target liên quan tới tiến độ:

- xhr: tiến độ nhận response.
- xhr.upload: tiến độ gửi request body, hữu ích khi upload file.

Ví dụ:

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;

      const percent = Math.round(
        (event.loaded / event.total) * 100
      );
      progressBar.value = percent;
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        showUploadComplete();
      } else {
        showUploadError(xhr.status);
      }
    });

    xhr.open("POST", "/api/files", true);
    xhr.send(formData);

### FormData và multipart boundary

Khi gửi FormData, không tự set Content-Type:

    const formData = new FormData();
    formData.append("description", descriptionInput.value);
    formData.append("file", fileInput.files[0]);

    xhr.open("POST", "/api/files", true);
    xhr.send(formData);

Browser tự thêm multipart/form-data cùng boundary phù hợp. Nếu tự đặt Content-Type mà thiếu boundary đúng, server có thể không parse được body.

### Kiểm tra file ở server

Client-side validation giúp trải nghiệm tốt hơn nhưng không phải ranh giới bảo mật. Server phải:

- Xác thực người dùng và authorization cho endpoint upload.
- Chống CSRF nếu request dùng cookie session.
- Giới hạn kích thước và số lượng file.
- Kiểm tra nội dung thực tế, không chỉ tin extension hoặc MIME type do client gửi.
- Dùng allowlist loại file nếu nghiệp vụ cho phép.
- Quét malware hoặc xử lý file theo threat model.
- Lưu file ngoài webroot hoặc trong object storage có quyền truy cập kiểm soát.
- Tạo tên file phía server, tránh path traversal.
- Không render filename hoặc metadata như HTML không tin cậy.

### Upload cross-origin

Upload cross-origin có thể kích hoạt CORS preflight, đặc biệt khi dùng custom header hoặc gắn listener vào xhr.upload. Server cần cho phép origin, method và request header phù hợp. Không mở wildcard credential chỉ để làm upload hoạt động.

## 8. Same-Origin Policy và CORS với XHR

XHR cùng origin có thể đọc response theo quyền của document. Với origin khác, browser áp dụng CORS để quyết định JavaScript có được phép đọc response hay không.

Ví dụ trang:

    https://app.example.test

gọi API:

    https://api.example.test

Đây là cross-origin vì hostname khác nhau, dù cùng domain gốc.

### Request đơn giản và preflight

Một số request cross-origin đáp ứng điều kiện CORS safelisted có thể được gửi mà không cần preflight. Ví dụ phổ biến là GET hoặc POST với tập header và Content-Type được safelist.

Request có thể cần preflight OPTIONS khi:

- Dùng method ngoài GET, HEAD, POST.
- Có request header không safelisted, ví dụ X-CSRF-Token hoặc X-Client-Version.
- Dùng Content-Type không safelisted như application/json.
- Có các điều kiện khác theo CORS protocol.

Browser gửi OPTIONS để hỏi server có cho phép origin, method và request header hay không. Chỉ khi preflight thành công, browser mới tiếp tục request thực tế.

Preflight request không mang credential như cookie hoặc HTTP authentication, kể cả khi XHR được cấu hình withCredentials=true. Tuy vậy, nếu request thực tế là credentialed, response preflight vẫn phải đáp ứng các quy tắc CORS cho credential, gồm origin cụ thể và Access-Control-Allow-Credentials: true. Request thực tế sau preflight mới được gửi credential nếu cookie policy và các điều kiện khác cho phép.

Ngoài ra, một số điều kiện khác cũng làm request cần preflight. Ví dụ, gắn event listener vào đối tượng xhr.upload cho request cross-origin có thể khiến browser thực hiện preflight. Khi debug, hãy xem OPTIONS trong Network thay vì chỉ suy luận từ method POST.

### Ví dụ preflight

Trang gọi:

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "https://api.example.test/orders", true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("X-Request-ID", "demo-123");
    xhr.send(JSON.stringify({ productId: 42 }));

Browser có thể gửi OPTIONS trước:

    OPTIONS /orders HTTP/1.1
    Origin: https://app.example.test
    Access-Control-Request-Method: POST
    Access-Control-Request-Headers: content-type,x-request-id

Server trả response cho preflight:

    HTTP/1.1 204 No Content
    Access-Control-Allow-Origin: https://app.example.test
    Access-Control-Allow-Methods: POST
    Access-Control-Allow-Headers: Content-Type, X-Request-ID
    Access-Control-Max-Age: 600

Sau đó browser mới gửi POST thực tế. Server vẫn phải xác thực và authorization cho POST; preflight thành công không chứng minh người gọi được phép tạo đơn.

### CORS không phải authorization

CORS kiểm soát browser có cung cấp response cross-origin cho JavaScript hay không. Nó không thay thế xác thực hoặc kiểm tra quyền trên server.

Một client ngoài browser như curl hoặc backend service không bị CORS của browser áp dụng theo cùng cách. Vì vậy, endpoint không được dựa vào CORS để bảo vệ dữ liệu hoặc ngăn người dùng trái phép.

## 9. Cookie và withCredentials

XHR có thuộc tính withCredentials để kiểm soát credential trong request cross-origin:

    xhr.withCredentials = true;

Đặt trước send(). Mặc định là false đối với request cross-origin.

### Cùng origin

Với request same-origin, browser gửi cookie phù hợp theo cookie jar và policy của browser. withCredentials không cần bật để gửi cookie same-origin.

### Cross-origin

Với request cross-origin:

- Mặc định withCredentials là false; credential cross-origin không được gửi theo chế độ này.
- Nếu cần cookie/credential, đặt withCredentials = true trước send().
- Server phải trả Access-Control-Allow-Credentials: true.
- Access-Control-Allow-Origin phải là origin cụ thể, không được là * khi credential được cho phép.
- Cookie vẫn chịu Secure, SameSite, domain/path, third-party cookie restrictions và các chính sách privacy của browser.

Ví dụ response:

    Access-Control-Allow-Origin: https://app.example.test
    Access-Control-Allow-Credentials: true
    Vary: Origin

Không dùng kết hợp:

    Access-Control-Allow-Origin: *
    Access-Control-Allow-Credentials: true

cho credentialed CORS request; browser sẽ không chấp nhận kết hợp wildcard này.

### withCredentials không có nghĩa là gửi mọi cookie

Cookie chỉ được gửi nếu domain, path, Secure, SameSite và chính sách browser cho phép. Bật withCredentials không vượt qua third-party cookie blocking hoặc SameSite restrictions.

### Không thể đọc Set-Cookie từ JavaScript

Set-Cookie là forbidden response header. Dù server gửi Set-Cookie, XHR không thể đọc nó qua getResponseHeader() hoặc Access-Control-Expose-Headers. Browser tự xử lý cookie theo chính sách.

## 10. CORS không tự bảo vệ khỏi CSRF

Đây là điểm quan trọng khi sử dụng XHR với cookie session.

Một website độc hại có thể gửi một số request cross-origin đơn giản bằng form hoặc các cơ chế browser khác. CORS thường ngăn JavaScript đọc response, nhưng không nhất thiết ngăn request được gửi hoặc server xử lý.

Vì vậy, endpoint thay đổi trạng thái như chuyển tiền, đổi email, tạo đơn hoặc cập nhật mật khẩu phải có CSRF defense:

- Cookie session dùng SameSite phù hợp.
- CSRF token gắn với session và được server xác minh.
- Kiểm tra Origin và/hoặc Referer theo chính sách phù hợp.
- Chỉ chấp nhận method và content type phù hợp với thiết kế.
- Không thực hiện thay đổi trạng thái qua GET.
- Với API same-origin, có thể yêu cầu custom header và từ chối request không có header đó; vẫn cần kiểm tra CORS và các đường truy cập khác.

### XHR và custom CSRF header

Ví dụ:

    xhr.open("POST", "/api/profile/email", true);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("X-CSRF-Token", csrfToken);
    xhr.send(JSON.stringify({ email: newEmail }));

Server phải xác minh token, session và quyền thay đổi email. Chỉ gửi header từ frontend mà không kiểm tra ở backend không tạo ra bảo vệ.

Đối với cross-origin, custom header thường kích hoạt preflight. Preflight có thể giúp browser ngăn request không được CORS cho phép, nhưng không thay thế CSRF token và kiểm tra server.

## 11. XSS và xử lý response an toàn

XHR không tự làm sạch nội dung response. Nếu server trả dữ liệu do người dùng kiểm soát, ứng dụng phải xử lý theo đúng context khi render.

Ví dụ không an toàn:

    xhr.onload = () => {
      resultContainer.innerHTML = xhr.responseText;
    };

Nếu response chứa HTML độc hại hoặc dữ liệu phản chiếu chưa encode, việc gán innerHTML có thể tạo DOM XSS.

Ưu tiên textContent khi chỉ cần hiển thị văn bản:

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resultContainer.textContent = xhr.responseText;
      }
    };

Nếu response là JSON:

    xhr.responseType = "json";
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) return;

      const data = xhr.response;
      if (!data || typeof data.message !== "string") return;

      resultContainer.textContent = data.message;
    };

Không dùng dữ liệu response trong eval, Function, setTimeout với string, URL nguy hiểm hoặc HTML sink mà không có kiểm soát. JSON parse thành công không đồng nghĩa dữ liệu đã an toàn để render.

### XHR và CSP connect-src

Content Security Policy directive connect-src kiểm soát các đích kết nối mà XHR, Fetch, WebSocket và một số API mạng có thể truy cập.

Ví dụ:

    Content-Security-Policy: default-src 'self'; connect-src 'self' https://api.example.test

Nếu XHR bị CSP chặn, Console có thể hiển thị vi phạm connect-src. Đây là lỗi policy ở browser, khác với HTTP 403 hoặc CORS response.

## 12. Upload, download và response nhị phân

### Download Blob

Đặt responseType là blob:

    const xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/reports/monthly", true);
    xhr.responseType = "blob";

    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) return;

      const objectUrl = URL.createObjectURL(xhr.response);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "monthly-report.pdf";
      link.click();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    };

    xhr.send();

Trong ứng dụng thực, kiểm tra Content-Type, kích thước, status và quyền tải file. Không tin tên file từ response nếu chưa validate.

### Download ArrayBuffer

    xhr.responseType = "arraybuffer";

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const bytes = new Uint8Array(xhr.response);
        processBinaryData(bytes);
      }
    };

Không cấp phát buffer không giới hạn từ response lớn. Dùng giới hạn ở server và kiểm soát kích thước dữ liệu.

## 13. Đồng bộ XHR và vì sao không nên dùng

XHR có thể được mở ở chế độ đồng bộ bằng:

    xhr.open("GET", "/api/data", false);

Trong document main thread, request đồng bộ sẽ chặn JavaScript cho tới khi request hoàn tất. UI có thể đứng, animation dừng và browser không xử lý tương tác bình thường.

Synchronous XHR trên main thread đã bị deprecated và bị hạn chế trong nhiều tình huống. Một số thuộc tính như timeout và responseType không thể dùng theo cách thông thường với synchronous XHR trên Window.

Trong Worker, một số trường hợp synchronous XHR vẫn được hỗ trợ, nhưng vẫn cần đánh giá độ trễ và khả năng hủy. Với giao diện web, ưu tiên async XHR hoặc Fetch.

Không dùng synchronous XHR trong beforeunload/unload để cố gửi dữ liệu cuối phiên. Nếu cần gửi telemetry khi trang rời đi, cân nhắc navigator.sendBeacon() hoặc fetch với keepalive theo đúng giới hạn và yêu cầu dữ liệu.

## 14. Xây dựng helper XHR có xử lý lỗi

Ví dụ helper GET JSON:

    function getJson(url, options = {}) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("GET", url, true);
        xhr.responseType = "json";
        xhr.timeout = options.timeout ?? 10000;

        xhr.setRequestHeader("Accept", "application/json");

        xhr.addEventListener("load", () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(xhr.response);
            return;
          }

          reject(new Error("HTTP " + xhr.status));
        });

        xhr.addEventListener("error", () => {
          reject(new Error("Network or browser policy error"));
        });

        xhr.addEventListener("timeout", () => {
          reject(new Error("Request timed out"));
        });

        xhr.addEventListener("abort", () => {
          reject(new DOMException("Request aborted", "AbortError"));
        });

        xhr.send();
      });
    }

Sử dụng:

    try {
      const products = await getJson("/api/products");
      renderProducts(products);
    } catch (error) {
      showSafeErrorMessage(error.message);
    }

Trong helper production:

- Validate URL để chỉ gọi endpoint mong muốn.
- Xử lý status 204 hoặc response null nếu API có thể trả body rỗng.
- Validate schema của JSON.
- Không hiển thị raw server error chứa stack trace hoặc dữ liệu nhạy cảm.
- Nếu cần hủy từ UI, trả về hoặc giữ reference XHR để gọi abort().
- Tránh retry tự động với request thay đổi trạng thái nếu không có idempotency key.

### Retry và idempotency

Không retry POST tạo đơn hoặc thanh toán chỉ vì client không nhận được response. Server có thể đã xử lý request trước khi kết nối bị đứt.

Với thao tác cần retry:

- Thiết kế idempotency key ở server.
- Xác định rõ method và semantics.
- Giới hạn số lần retry và dùng backoff.
- Không retry lỗi 4xx như validation/authorization theo cách mù quáng.
- Với timeout, xác minh trạng thái nghiệp vụ trước khi gửi lại thao tác.

## 15. So sánh XMLHttpRequest với Fetch API

| Khía cạnh | XMLHttpRequest | Fetch |
| --- | --- | --- |
| API | Event/callback và readyState | Promise |
| Đọc response | response, responseText | Response.json(), text(), blob() |
| Upload progress | Có xhr.upload progress event | Fetch chuẩn không có upload progress event tương đương phổ biến |
| Download progress | Có progress event | Có thể đọc stream body |
| Hủy request | xhr.abort() | AbortController |
| Timeout | Thuộc tính timeout | Thường dùng AbortController/AbortSignal.timeout |
| CORS/credentials | withCredentials | credentials |
| HTTP 404/500 | Phát load; phải kiểm tra status | Promise vẫn resolve; phải kiểm tra response.ok/status |
| Synchronous mode | Có API cũ nhưng không nên dùng trên main thread | Không có synchronous Fetch |
| Response headers | getResponseHeader() | Headers API |

Fetch là lựa chọn phù hợp cho phần lớn request mới vì Promise API dễ kết hợp với async/await. XHR vẫn hữu ích khi cần upload progress hoặc đang tích hợp codebase cũ.

Hai API đều chịu Same-Origin Policy, CORS, CSP connect-src, cookie policy và các kiểm soát server. Chuyển từ XHR sang Fetch không tự sửa lỗi authorization, CSRF hoặc XSS.

## 16. Kiểm thử XHR bằng Chrome DevTools

Thực hiện trên local/staging với tài khoản và dữ liệu giả.

### Bước 1 — Quan sát request

1. Mở DevTools → Network.
2. Chọn bộ lọc Fetch/XHR.
3. Thực hiện thao tác trong ứng dụng.
4. Chọn request và kiểm tra URL, method, status, request headers và response.
5. Kiểm tra Initiator để tìm đoạn code tạo XHR.

### Bước 2 — Phân biệt HTTP error và network/CORS error

Tạo hai trường hợp trong môi trường test:

- Endpoint trả HTTP 404: XHR vẫn phát load và status là 404.
- Endpoint cross-origin không có CORS phù hợp: browser chặn JavaScript đọc response và XHR có thể phát error với status 0.

Quan sát Console và Network. Không kết luận server không nhận request chỉ vì JavaScript báo CORS; request đơn giản có thể đã tới server.

### Bước 3 — Kiểm tra preflight

Gửi request cross-origin với Content-Type application/json hoặc custom header. Quan sát OPTIONS trong Network:

- Origin.
- Access-Control-Request-Method.
- Access-Control-Request-Headers.
- Access-Control-Allow-Origin.
- Access-Control-Allow-Methods.
- Access-Control-Allow-Headers.

Nếu preflight thất bại, browser không gửi request thực tế theo luồng đó.

### Bước 4 — Kiểm tra credentials

Trong staging:

1. Gọi API cross-origin khi withCredentials=false.
2. Thử với withCredentials=true.
3. Kiểm tra ACAO là origin cụ thể và ACAC=true.
4. Kiểm tra cookie có được gửi theo SameSite/Secure và third-party cookie policy hay không.
5. Không dùng cookie production hoặc tài khoản thật cho bài lab.

### Bước 5 — Kiểm tra upload

1. Upload một file test nhỏ bằng FormData.
2. Quan sát xhr.upload progress.
3. Hủy request giữa chừng.
4. Kiểm tra event abort/loadend.
5. Thử file vượt giới hạn và xác nhận server từ chối.

### Bước 6 — Kiểm tra CSP

Trong staging, tạm loại API host khỏi connect-src. Xác nhận XHR bị browser chặn và Console chỉ ra directive vi phạm. Khôi phục policy sau test.

### Ma trận kiểm thử

| Ca kiểm thử | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Same-origin GET | Endpoint trả JSON 200 | load, status 200, response JSON |
| HTTP 404 | Server trả 404 | load vẫn chạy; ứng dụng xử lý status |
| HTTP 500 | Server trả 500 | load chạy; không coi là thành công |
| CORS bị chặn | Cross-origin thiếu ACAO phù hợp | error/status 0, response không đọc được |
| Preflight thành công | OPTIONS cho phép method/header | Browser gửi request thực tế |
| Preflight thất bại | Server từ chối method/header | Request thực tế bị browser chặn |
| Credentialed CORS | withCredentials true, ACAO cụ thể, ACAC true | Cookie chỉ gửi nếu cookie policy cho phép |
| Wildcard với credentials | ACAO * và ACAC true | Browser không chấp nhận response |
| Timeout | Server chậm hơn xhr.timeout | timeout rồi loadend |
| Abort | Gọi xhr.abort() | abort rồi loadend |
| Upload progress | FormData file đủ lớn | xhr.upload phát progress khi có thể |
| CSP connect-src | API host bị loại khỏi policy | Browser chặn request theo CSP |
| Response XSS | Response chứa chuỗi HTML test | textContent hiển thị literal, không thực thi |
| Retry POST | Mạng mất response sau khi server xử lý | Không gửi lại mù; dùng idempotency/status check |

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ readyState DONE là HTTP thành công | Có thể render response 404/500 | Kiểm tra status và schema |
| Nghĩ event load chỉ chạy với 2xx | Bỏ sót xử lý HTTP error | Phân biệt load với status |
| Coi CORS error là server chắc chắn chưa nhận request | Request đơn giản có thể đã được gửi | Kiểm tra server log và Network |
| Đặt header sau send() | InvalidStateError hoặc header không áp dụng | Đặt sau open và trước send |
| Tự set Cookie/Origin | Browser cấm một số forbidden header | Để browser quản lý cookie và Origin |
| Gửi FormData nhưng tự đặt multipart Content-Type | Boundary sai, server parse lỗi | Để browser tự đặt Content-Type |
| Dùng withCredentials như cách vượt SameSite | Cookie vẫn có thể bị browser chặn | Kiểm tra cookie attributes và third-party policy |
| Nghĩ CORS ngăn CSRF | Request đơn giản vẫn có thể được gửi | CSRF token, SameSite và kiểm tra Origin |
| Gán responseText vào innerHTML | DOM XSS | Dùng textContent hoặc sanitizer đúng cách |
| Dùng synchronous XHR | Đóng băng UI và hành vi lỗi thời | Dùng async XHR hoặc Fetch |
| Retry POST sau timeout | Tạo giao dịch trùng | Idempotency key và xác minh trạng thái |
| Bỏ qua abort/timeout event | UI kẹt trạng thái loading | Xử lý loadend và trạng thái request |
| Đọc Set-Cookie qua getResponseHeader | Không thể truy cập forbidden response header | Để browser xử lý cookie; kiểm tra cookie qua DevTools |

## 18. Câu hỏi củng cố

**Câu 1.** XHR có thể đọc response cross-origin chỉ vì server trả HTTP 200 không?

**Giải đáp:** Không. Browser vẫn cần CORS hợp lệ để JavaScript đọc response cross-origin.

**Câu 2.** readyState DONE có nghĩa request thành công không?

**Giải đáp:** Không. Request có thể kết thúc với HTTP 404/500, network error, timeout hoặc abort. Cần kiểm tra event và status.

**Câu 3.** withCredentials mặc định là gì đối với cross-origin XHR?

**Giải đáp:** Mặc định false. Nếu cần credential cross-origin, đặt true trước send và server phải cấu hình ACAO cụ thể cùng ACAC true; cookie vẫn chịu SameSite và browser privacy policy.

**Câu 4.** CORS có ngăn CSRF không?

**Giải đáp:** Không. CORS chủ yếu kiểm soát JavaScript đọc response. Request đơn giản vẫn có thể được gửi; endpoint thay đổi trạng thái cần CSRF defense.

**Câu 5.** Vì sao không tự đặt Content-Type khi gửi FormData?

**Giải đáp:** Browser cần tạo multipart boundary và gắn boundary vào Content-Type. Tự đặt header thường làm thiếu boundary đúng.

**Câu 6.** XHR upload progress được nghe ở đâu?

**Giải đáp:** Qua xhr.upload, còn progress trên xhr theo dõi quá trình nhận response.

**Câu 7.** Có nên dùng synchronous XHR trong main thread không?

**Giải đáp:** Không. Nó chặn UI, đã deprecated và bị giới hạn trong nhiều trường hợp. Dùng async XHR hoặc Fetch.

**Câu 8.** Vì sao không đưa responseText vào innerHTML?

**Giải đáp:** Response có thể chứa HTML hoặc input chưa tin cậy; innerHTML có thể tạo DOM XSS. Dùng textContent hoặc sanitizer đã được đánh giá.

## 19. Tổng kết

XMLHttpRequest là API gửi HTTP request từ JavaScript với vòng đời bất đồng bộ, trạng thái readyState và các event để theo dõi tải, lỗi, timeout, abort và progress. Cấu hình request theo thứ tự open, set header/responseType/timeout rồi send; khi xử lý kết quả phải phân biệt HTTP status với lỗi mạng hoặc CORS.

XHR vẫn tuân theo Same-Origin Policy, CORS, cookie policy và CSP connect-src. withCredentials chỉ cho phép browser tham gia gửi/nhận credential cross-origin khi server và cookie policy cho phép; nó không vượt SameSite hoặc third-party cookie restrictions. CORS không phải authorization và không thay CSRF defense.

Với response, validate dữ liệu và schema trước khi sử dụng; dùng textContent thay innerHTML cho text không tin cậy. Upload file phải được kiểm tra ở server. Tránh synchronous XHR, retry POST mù quáng và lưu credential trong URL. Dùng DevTools để kiểm tra preflight, request header, cookie behavior, CSP, progress và lỗi thực tế.

## Tài liệu tham khảo

1. [WHATWG — XMLHttpRequest Standard](https://xhr.spec.whatwg.org/): đặc tả XHR, lifecycle, event, request và response.
2. [MDN — XMLHttpRequest](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest): hướng dẫn API và ví dụ sử dụng.
3. [MDN — Using XMLHttpRequest](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest_API/Using_XMLHttpRequest): request, response, upload và progress.
4. [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, credential và response header.
5. [MDN — CSP connect-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/connect-src): kiểm soát XHR, Fetch và các kết nối script.
6. [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF token, cookie và kiểm tra request.
