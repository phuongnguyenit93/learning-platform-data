# Opaque origin: danh tính origin đặc biệt trong trình duyệt

> **Chương:** Origin  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi.

Một trang web thông thường có origin được xác định từ **scheme, hostname và port**. Tuy nhiên, trình duyệt còn có thể cấp cho tài liệu một **opaque origin**: danh tính origin nội bộ không được biểu diễn bằng bộ ba scheme–host–port. Cơ chế này đặc biệt quan trọng khi nhúng nội dung không đáng tin trong iframe, tải tài liệu `data:` hoặc thực thi các chính sách `sandbox`.

Điểm cốt lõi: nhiều opaque origin có thể được biểu diễn thành cùng một chuỗi **`"null"`** khi đưa ra ngoài, nhưng chúng **không phải cùng một origin**. Chuỗi hiển thị không thay thế cho danh tính bảo mật nội bộ của trình duyệt.

## Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt **tuple origin** và **opaque origin**, giải thích vì sao hai opaque origin cùng biểu diễn `"null"` vẫn khác nhau.
2. Dự đoán origin của tài liệu `data:`, `about:blank`, `about:srcdoc`, `blob:`, `file:` và iframe có/không có sandbox.
3. Phân tích tác động lên **Same-Origin Policy (SOP)**, quyền đọc DOM, storage, cookie, Fetch, CORS và `postMessage`.
4. Cấu hình iframe sandbox để tách nội dung không đáng tin khỏi trang chính mà vẫn hỗ trợ giao tiếp cần thiết.
5. Thực hành quan sát giá trị `MessageEvent.origin` và lỗi `SecurityError` bằng DevTools.
6. Nhận diện các lỗi cấu hình nguy hiểm, đặc biệt là việc xem `Origin: null` như danh tính đáng tin ở máy chủ.

## 1. Origin thông thường và opaque origin

### 1.1 Tuple origin

Trong mô hình web, origin của một URL HTTP(S) thường là bộ ba:

\[
\text{origin}=(\text{scheme},\ \text{host},\ \text{port})
\]

Ví dụ:

| URL | Origin | So với `https://app.example.com` |
|---|---|---|
| `https://app.example.com/profile` | `https://app.example.com` | Same-origin |
| `https://app.example.com:8443/api` | `https://app.example.com:8443` | Cross-origin do khác cổng |
| `https://api.example.com/data` | `https://api.example.com` | Cross-origin do khác host |
| `http://app.example.com` | `http://app.example.com` | Cross-origin do khác scheme |
| `https://app.example.com/a?q=1` | `https://app.example.com` | Same-origin; path/query không quyết định origin |

Các origin thuộc dạng bộ ba như vậy được gọi là **tuple origin**. Trình duyệt dùng so sánh origin để quyết định liệu JavaScript trong tài liệu này có thể đọc nội dung hoặc thao tác trực tiếp trên tài liệu khác hay không.

### 1.2 Định nghĩa opaque origin

**Opaque origin** là một origin được trình duyệt nhận diện bằng một giá trị nội bộ riêng, không có scheme, host, port theo kiểu tuple origin. Về trực giác, ta có thể minh họa hai opaque origin mới được cấp phát là hai danh tính khác nhau:

~~~text
A = (https, app.example.com, 443)  → serializes as "https://app.example.com"
B = opaque-id-01                    → serializes as "null"
C = opaque-id-02                    → serializes as "null"

sameOrigin(A, B) = false
sameOrigin(B, C) = false
~~~

**`"null"` ở đây là chuỗi literal**, khác giá trị JavaScript `null` hoặc việc không có header HTTP `Origin`. Việc hai origin cùng *serialize* thành `"null"` không biến chúng thành same-origin.

Các bối cảnh thường thấy chuỗi này:

- Header `Origin: null` trong một số cross-origin request xuất phát từ opaque origin.
- Giá trị `event.origin === "null"` trong sự kiện `message` gửi từ tài liệu có opaque origin.
- Một số URL và công cụ chẩn đoán có cách thể hiện nguồn là `null`; giá trị cụ thể còn tùy API.

**Không được dùng chuỗi `"null"` như định danh đáng tin** cho một ứng dụng, một iframe hay một tài khoản cụ thể.

### 1.3 Vì sao cần opaque origin?

Nếu một trang thương mại điện tử cho phép người dùng gửi nội dung HTML rồi hiển thị preview, nội dung đó có thể chứa script độc hại. Nếu iframe preview được xem là cùng origin với trang chính, script có nguy cơ truy cập DOM, Web Storage hoặc những giao diện nhạy cảm của trang.

Opaque origin giúp **ép tài liệu bị cách ly** khỏi origin của trang chính. Điều này đặc biệt hữu ích khi dùng iframe `sandbox` thiếu quyền `allow-same-origin`.

~~~mermaid
flowchart TD
    A["Trang chính<br/>https://app.example.com"] --> B["iframe srcdoc<br/>không sandbox"]
    A --> C["iframe srcdoc<br/>sandbox=allow-scripts"]
    B --> D["Kế thừa origin trang cha"]
    C --> E["Opaque origin riêng"]
    D --> F["Có thể same-origin với trang cha"]
    E --> G["Không đọc trực tiếp DOM cha theo SOP"]
~~~

Opaque origin **không phải cơ chế ẩn danh trên mạng**: tài liệu vẫn có thể tải tài nguyên và gửi request nếu chính sách cho phép; máy chủ vẫn có thể nhận các kết nối đó.

## 2. Khi nào tài liệu có opaque origin?

| Trường hợp | Origin thường có | Điều cần nhớ |
|---|---|---|
| Trang HTTP(S) thông thường | Tuple origin | Xác định từ scheme + host + port |
| Tài liệu `data:text/html,...` | **Opaque origin mới** | Hai tài liệu `data:` riêng biệt không vì có cùng chuỗi URL mà same-origin |
| Iframe có `sandbox` và **không có** `allow-same-origin` | **Opaque origin** | Kể cả khi nội dung đến từ URL cùng host với trang cha |
| Iframe `srcdoc` không sandbox | Thường kế thừa origin trang cha | `about:srcdoc` không mặc nhiên là opaque |
| Trang `about:blank` do một trang khác tạo/nhúng | Thường kế thừa origin của trang tạo | Có ngoại lệ tùy cách tạo và sandbox |
| `blob:` URL tạo trong tài liệu có tuple origin | Thường mang origin của môi trường tạo | Không mặc nhiên opaque vì dùng scheme `blob:` |
| `blob:` URL tạo từ môi trường có opaque origin | Gắn với opaque origin của môi trường tạo | Có thể thấy dạng URL `blob:null/...` |
| `file:` URL | Tùy browser/triển khai; thường bị hạn chế như opaque | Không giả định hai file cục bộ cùng thư mục là same-origin |
| Iframe sandbox **có** `allow-same-origin` | Không bị sandbox ép sang opaque | Không đồng nghĩa nó cùng origin với trang cha nếu URL thực sự khác origin |

### 2.1 Tài liệu `data:`

Một `data:` URL chứa dữ liệu ngay trong URL:

~~~html
<iframe src="data:text/html,%3Ch1%3EHello%3C%2Fh1%3E"></iframe>
~~~

Tài liệu ở đây thường nhận một **opaque origin mới**. Trang cha tạo iframe không làm nội dung `data:` mặc nhiên được dùng origin của trang cha. Nếu tạo thêm iframe khác từ cùng URL `data:`, cũng không nên coi hai iframe đó same-origin.

Trình duyệt hiện đại còn có những giới hạn riêng với điều hướng top-level đến `data:`. Ví dụ trên minh họa ngữ nghĩa origin của tài liệu nhúng, không khẳng định mọi trình duyệt hoặc CSP sẽ cho phép mọi kiểu điều hướng `data:`.

### 2.2 `about:blank` và `srcdoc` thường kế thừa origin

Ví dụ:

~~~html
<iframe srcdoc="<p>Nội dung do trang cha tạo</p>"></iframe>
~~~

Không có sandbox, `srcdoc` thông thường nhận origin của trang cha. Tài liệu `about:blank` được tạo từ trang khác cũng thường kế thừa origin của ngữ cảnh tạo/nhúng.

Nhưng với cấu hình:

~~~html
<iframe
  sandbox="allow-scripts"
  srcdoc="<p>Preview có script, nhưng bị cách ly origin</p>">
</iframe>
~~~

thuộc tính sandbox **không có** `allow-same-origin` khiến tài liệu nhận **opaque origin**. Dù nội dung HTML do chính trang cha cung cấp, iframe vẫn không được đọc trực tiếp DOM của cha theo SOP.

**Lưu ý:** `location.href` hoặc `location.origin` phản ánh URL và ngữ cảnh của Location API; với các tình huống sandbox, không nên suy ra *effective security origin* chỉ từ chuỗi URL hiển thị. Hãy quan sát chính sách sandbox, hành vi truy cập DOM và origin của thông điệp `postMessage`.

### 2.3 `blob:` không mặc nhiên tạo opaque origin

Ví dụ:

~~~js
const blob = new Blob(
  ['<h1>Generated document</h1>'],
  { type: 'text/html' }
);
const blobUrl = URL.createObjectURL(blob);
~~~

Nếu code chạy trong trang `https://app.example.com`, blob URL thông thường gắn với origin của môi trường tạo nó. Khi code chạy từ một môi trường vốn có opaque origin, blob URL có thể gắn với opaque origin đó.

Đừng suy ra origin dựa duy nhất vào tiền tố URL. Cách origin được xác lập phụ thuộc **kiểu URL, ngữ cảnh tạo tài liệu và chính sách sandbox**.

### 2.4 `file:` phụ thuộc trình duyệt

Chính sách đối với file cục bộ có khác biệt giữa trình duyệt và phiên bản; nhiều trình duyệt dùng chính sách cô lập mạnh cho `file:`. Vì thế khi xây dựng bài thực hành, hãy phục vụ trang qua `http://localhost` thay vì mở thẳng bằng `file://`. Một ví dụ chạy được trên một trình duyệt từ ổ đĩa không chứng minh quy tắc origin áp dụng cho production.

## 3. Same-Origin Policy với opaque origin

### 3.1 Bị tách khỏi quyền đọc DOM của trang cha

Giả sử trang `https://app.example.com` tạo iframe:

~~~html
<iframe
  id="preview"
  sandbox="allow-scripts"
  srcdoc="<script>console.log('iframe chạy script')</script>">
</iframe>
~~~

Script trong iframe được phép chạy vì có `allow-scripts`. Nhưng vì không có `allow-same-origin`, iframe nhận opaque origin. Quyền chạy script **khác** quyền đọc DOM ở origin khác.

Trong iframe, những truy cập như sau có thể bị SOP ngăn và ném `SecurityError`:

~~~js
try {
  console.log(parent.document.body.innerText);
} catch (error) {
  console.log(error.name); // Thường là "SecurityError"
}
~~~

Chiều ngược lại cũng vậy: JavaScript của trang cha không thể tùy ý đọc DOM của iframe có opaque origin, dù chính trang cha tạo ra nội dung `srcdoc`.

### 3.2 Hai iframe đều báo `null` vẫn khác origin

Nếu tạo hai iframe sandbox A và B, mỗi iframe có một opaque origin:

~~~text
iframe A  ── security origin ──> opaque-A ── serialize ──> "null"
iframe B  ── security origin ──> opaque-B ── serialize ──> "null"

opaque-A !== opaque-B
~~~

Việc thấy `event.origin` của cả hai đều bằng `"null"` **không chứng minh chúng được phép truy cập tài liệu của nhau**.

### 3.3 SOP không cấm mọi giao tiếp

SOP kiểm soát nhiều kiểu truy cập trực tiếp tới dữ liệu/DOM nhưng không có nghĩa mọi giao tiếp giữa origin khác nhau bị cấm. Ví dụ, trang khác origin có thể trao đổi dữ liệu được đóng gói có chủ đích qua `window.postMessage`.

~~~js
parent.postMessage(
  { type: 'widget-ready', version: 1 },
  '*'
);
~~~

Ở ví dụ này, chỉ gửi trạng thái công khai. Dùng đích `"*"` mà không kiểm soát có thể làm lộ dữ liệu nhạy cảm khi frame điều hướng; thiết kế giao tiếp thực tế cần kiểm tra nguồn, dữ liệu và vòng đời của frame.

## 4. Storage, cookie và network request

### 4.1 Web Storage không dùng được như origin thông thường

`localStorage`, `IndexedDB` và nhiều khả năng lưu trữ được ràng buộc với origin và các chính sách truy cập của browser. Tài liệu có opaque origin thường **không được dùng storage gắn với origin như trang HTTP(S) thông thường**.

Dùng `try/catch` để phát hiện:

~~~js
try {
  localStorage.setItem('demo', 'value');
  console.log('localStorage available');
} catch (error) {
  console.log('Storage blocked:', error.name);
}
~~~

Trong iframe opaque, thao tác có thể ném `SecurityError`. Đừng thiết kế một widget bị sandbox dựa trên khả năng đọc token từ `localStorage` hoặc cookie của trang chính.

### 4.2 Cookie theo cơ chế khác SOP

Cookie có quy tắc **Domain, Path, Secure, HttpOnly, SameSite**, cùng bối cảnh site và chính sách cookie của trình duyệt. Đây là hệ thống khác với danh tính tuple/opaque origin.

Khi tài liệu bị sandbox ép opaque origin:

- Script thường không có quyền sử dụng `document.cookie` như tài liệu cùng origin thông thường.
- Không thể suy ra mọi request đi ra ngoài đều không mang cookie. Điều đó còn phụ thuộc URL đích, lựa chọn `credentials` của Fetch, thuộc tính cookie, site context, hạn chế cookie bên thứ ba và chính sách browser.
- Cookie `HttpOnly` không đọc được trực tiếp bằng JavaScript, nhưng một request hợp lệ vẫn có thể được trình duyệt đính kèm cookie nếu các điều kiện gửi thỏa mãn.
- `SameSite` xét ranh giới **site**, còn CORS/SOP xét **origin**; cross-origin không nhất thiết là cross-site.

Vì thế khi phân tích rủi ro, cần kiểm tra riêng **quyền truy cập DOM/storage**, **cookie có được gửi**, và **server có chấp nhận request hay không**.

### 4.3 Fetch từ opaque origin

Giả sử một iframe opaque gửi:

~~~js
const response = await fetch('https://api.example.com/public', {
  mode: 'cors',
  credentials: 'omit'
});
const data = await response.json();
~~~

API có tuple origin `https://api.example.com`, còn iframe có opaque origin. Đây là **cross-origin request**. Với một yêu cầu chịu CORS và có header `Origin`, trình duyệt có thể gửi:

~~~http
GET /public HTTP/1.1
Host: api.example.com
Origin: null
Accept: */*
~~~

Không phải mọi request đều có header `Origin`; cần kiểm tra method, mode, loại tài nguyên và hành vi browser.

Nếu endpoint thực sự công khai, không cần credentials, API có thể dùng:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: *
Content-Type: application/json
~~~

Khi các điều kiện Fetch/CORS khác phù hợp, script có thể đọc response. Opaque origin **không phải lệnh cấm network tuyệt đối**.

### 4.4 Rủi ro khi CORS cho phép `Origin: null`

Ví dụ cấu hình máy chủ:

~~~http
Access-Control-Allow-Origin: null
Access-Control-Allow-Credentials: true
~~~

Đây là cấu hình **cần tránh nếu mục tiêu là chỉ tin một iframe nhất định**. Nhiều ngữ cảnh không đáng tin có thể tạo request mà origin được serialize thành `null`. Máy chủ không thể phân biệt các opaque origin riêng chỉ bằng chuỗi header này.

Nếu credentials thực sự được gửi và các điều kiện CORS khác đều thỏa mãn, cấu hình trên có thể cho phép mã từ nhiều ngữ cảnh opaque đọc response nhạy cảm. Việc chặn cookie bên thứ ba có thể hạn chế một số trường hợp, nhưng không biến `null` thành định danh đáng tin.

| Cấu hình response | Credentials mode | Kết quả CORS cho iframe opaque |
|---|---|---|
| Không có `Access-Control-Allow-Origin` | `omit` | Không đọc được response chịu CORS |
| `Access-Control-Allow-Origin: *` | `omit` | Có thể đọc nếu các điều kiện khác hợp lệ |
| `Access-Control-Allow-Origin: *` | `include` | Không được chia sẻ response vì wildcard không hợp lệ với mode `include` |
| `Access-Control-Allow-Origin: null` và `Access-Control-Allow-Credentials: true` | `include` | Có thể đọc nếu các điều kiện khác hợp lệ; **không an toàn nếu mặc định tin mọi opaque origin** |
| `Access-Control-Allow-Origin: https://app.example.com` | `omit` | Không khớp origin opaque được serialize thành `null` |

Phòng vệ đúng: định nghĩa allowlist origin chính xác cho các frontend có tuple origin khi cần CORS, đồng thời bắt buộc **authentication, authorization, CSRF protection, validation** ở server. **CORS không thay thế xác thực hoặc CSRF**; form và các request khác có thể đến server ngay cả khi script không đọc được response.

### 4.5 Đừng nhầm opaque origin với opaque response

Có hai khái niệm khác nhau:

- **Opaque origin:** danh tính bảo mật của tài liệu/ngữ cảnh.
- **Opaque response:** loại response của Fetch (ví dụ từ `mode: 'no-cors'` trong nhiều trường hợp cross-origin), khiến JavaScript không đọc trực tiếp body, status thực và headers.

~~~js
const response = await fetch('https://cdn.example.net/pixel.png', {
  mode: 'no-cors'
});
console.log(response.type); // Thường là "opaque"
~~~

`no-cors` không “sửa lỗi CORS” để đọc JSON. Một tài liệu có tuple origin vẫn có thể nhận opaque response, và một tài liệu có opaque origin vẫn có thể đọc response CORS hợp lệ.

## 5. Iframe sandbox: cách sử dụng đúng

Thuộc tính `sandbox` đặt những hạn chế như cấm script, form, popup, điều hướng top-level và **ép opaque origin**. Thiếu `allow-same-origin` thì tài liệu bị ép opaque; thêm `allow-same-origin` chỉ bỏ giới hạn này, **không tự tạo quan hệ same-origin với một URL vốn khác origin**.

### 5.1 Bảng quyền với iframe `srcdoc`

Giả sử trang cha có origin `https://app.example.com`:

| Cấu hình | Script trong iframe | Origin thường gặp | Hệ quả |
|---|---|---|---|
| Không có `sandbox` | Có thể chạy theo chính sách bình thường | Kế thừa origin cha | Có thể đọc DOM cha theo SOP |
| `sandbox=""` | Bị sandbox chặn | Opaque | Mức cách ly mạnh, nhiều chức năng bị chặn |
| `sandbox="allow-scripts"` | Được chạy | **Opaque** | Chạy được script nhưng không đọc trực tiếp DOM cha |
| `sandbox="allow-same-origin"` | Vẫn bị sandbox chặn | Kế thừa origin cha | Không tự cấp quyền script |
| `sandbox="allow-scripts allow-same-origin"` | Được chạy | Kế thừa origin cha | Nguy hiểm với nội dung không đáng tin cùng origin |

Nếu iframe tải từ URL có origin khác với cha, `allow-same-origin` chỉ bỏ việc ép opaque; SOP giữa hai origin thực vẫn tồn tại.

**Tránh kết hợp `allow-scripts` và `allow-same-origin` cho nội dung không đáng tin được phục vụ từ cùng origin với trang cha.** Script same-origin có thể tác động tới phần tử iframe và tạo đường làm suy yếu sandbox sau khi điều hướng/tải lại. Nên phục vụ preview nội dung người dùng từ **origin riêng** và chỉ cấp quyền tối thiểu.

### 5.2 Ví dụ nhúng preview

~~~html
<iframe
  title="Preview nội dung người dùng"
  src="https://preview.example.net/widget"
  sandbox="allow-scripts"
  referrerpolicy="no-referrer">
</iframe>
~~~

Cấu hình này cho phép script trong widget nhưng ép tài liệu dùng opaque origin. Nếu preview không cần script, có thể giữ `sandbox=""` để hạn chế mạnh hơn. Nếu cần form/popup/download, cân nhắc từng quyền trước khi thêm flag tương ứng.

### 5.3 CSP và các security headers hỗ trợ

Ví dụ trang cha có thể trả:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; frame-src https://preview.example.net; object-src 'none'; base-uri 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
~~~

- **CSP `frame-src`:** giới hạn những iframe mà trang cha được tải.
- **CSP `frame-ancestors`** và **X-Frame-Options:** quy định ai được nhúng trang, góp phần chống clickjacking; không trực tiếp làm tài liệu thành opaque origin.
- **CSP `sandbox`:** khi gửi từ response header có thể áp đặt sandbox; nếu không có `allow-same-origin`, tài liệu có thể bị ép opaque.
- **CSP `connect-src`:** giới hạn đích fetch/XHR/WebSocket; khác với CORS là chính sách ai được đọc response cross-origin.
- **Trusted Types:** giúp kiểm soát một số DOM sink nguy hiểm nhằm giảm DOM XSS ở trình duyệt hỗ trợ; không thay thế sandbox và không tự tạo opaque origin.

Các chính sách hỗ trợ nhau nhưng có phạm vi riêng. Nội dung người dùng còn cần encode/sanitize theo ngữ cảnh, kiểm tra input và phân quyền phía server.

## 6. `postMessage` với nguồn có origin `"null"`

### 6.1 Vì sao không nên tin chỉ dựa vào `event.origin`

Mã sau không đủ để xác minh một iframe cụ thể:

~~~js
window.addEventListener('message', (event) => {
  if (event.origin === 'null') {
    // KHÔNG mặc nhiên coi đây là widget nội bộ đáng tin.
  }
});
~~~

Một tài liệu sandbox hoặc `data:` khác cũng có thể gửi thông điệp với giá trị origin đó. Xác minh danh tính bằng đúng chuỗi `"null"` là sai về mặt mô hình bảo mật.

### 6.2 Bộ lọc message cơ bản

Trang cha có thể nhận thông báo trạng thái **không nhạy cảm** từ iframe đã biết:

~~~js
const widget = document.querySelector('#widget');

window.addEventListener('message', (event) => {
  if (event.source !== widget.contentWindow) return;
  if (!event.data || event.data.type !== 'widget-ready') return;
  if (event.data.version !== 1) return;

  console.log('Widget đã báo sẵn sàng:', event.origin);
});
~~~

Các điểm cần chú ý:

1. **`event.source`** liên kết với browsing context được mong đợi, nhưng iframe có thể điều hướng nên phải kiểm soát vòng đời.
2. **`event.data`** cần được xác thực kiểu, schema, giới hạn dữ liệu và ý nghĩa nghiệp vụ. Không đưa HTML nhận được vào các DOM sink nguy hiểm.
3. Nếu cần tác vụ nhạy cảm, nên dùng **nonce/capability gắn với phiên** và giao thức bắt tay; đừng coi thông điệp `ready` là xác thực.
4. **MessageChannel/MessagePort** có thể cung cấp kênh giao tiếp có kiểm soát sau khi thiết lập, nhưng vẫn phải bảo đảm port được cấp đúng đối tượng.
5. **`postMessage(..., "*")`** có thể cần khi đích là opaque origin không thể biểu diễn bằng tuple origin chính xác; không truyền bí mật nếu chưa xác minh đối tượng nhận và ngăn rủi ro frame điều hướng.

Cần nhớ `event.source` và dữ liệu message là lớp lọc, **không thay thế xác thực server** khi thực hiện thao tác quan trọng.

## 7. Thực hành: quan sát origin thật của iframe

Bài thực hành này so sánh hai iframe có **cùng nội dung `srcdoc`** nhưng khác cấu hình sandbox.

### 7.1 Lưu tệp `opaque-origin-lab.html`

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Opaque origin lab</title>
</head>
<body>
  <h1>Opaque origin lab</h1>
  <p>Iframe A không sandbox; iframe B có sandbox="allow-scripts".</p>

  <iframe id="regular" title="Iframe A"></iframe>
  <iframe id="isolated" title="Iframe B"
          sandbox="allow-scripts"></iframe>
  <pre id="log" aria-live="polite"></pre>

  <script>
    const regular = document.querySelector('#regular');
    const isolated = document.querySelector('#isolated');
    const log = document.querySelector('#log');

    // Tách tên thẻ đóng để parser không kết thúc script cha sớm.
    const childDocument = [
      '<!doctype html><html lang="vi">',
      '<meta charset="utf-8"><h2>Child document</h2>',
      '<script>',
      'let storage;',
      'try {',
      '  localStorage.setItem("opaque-origin-lab", "ok");',
      '  storage = "available";',
      '} catch (error) {',
      '  storage = error.name;',
      '}',
      'parent.postMessage({type:"lab-result", storage}, "*");',
      '</scr' + 'ipt>',
      '</html>'
    ].join('\n');

    window.addEventListener('message', (event) => {
      if (!event.data || event.data.type !== 'lab-result') return;

      let frameName;
      if (event.source === regular.contentWindow) {
        frameName = 'A: regular';
      } else if (event.source === isolated.contentWindow) {
        frameName = 'B: sandbox';
      } else {
        return;
      }

      log.textContent +=
        frameName +
        '\n  event.origin = ' + JSON.stringify(event.origin) +
        '\n  localStorage = ' + event.data.storage +
        '\n\n';
    });

    regular.srcdoc = childDocument;
    isolated.srcdoc = childDocument;
  </script>
</body>
</html>
~~~

Trong demo, thông điệp chỉ chứa dữ liệu quan sát công khai. Cờ `allow-scripts` ở iframe B cần thiết để JavaScript trong tài liệu con gửi kết quả.

### 7.2 Chạy qua localhost

Đặt tệp HTML trong một thư mục riêng và phục vụ qua HTTP. Ví dụ dùng Node.js có sẵn, không cần package bên ngoài:

~~~bash
node -e "const h=require('node:http'),f=require('node:fs');h.createServer((q,r)=>{r.setHeader('Content-Type','text/html; charset=utf-8');f.createReadStream('opaque-origin-lab.html').on('error',()=>{r.statusCode=404;r.end('Not found')}).pipe(r)}).listen(8080)"
~~~

Sau đó mở **http://localhost:8080**. Không dùng `file://` cho lab này vì chính sách file cục bộ có thể khác nhau giữa trình duyệt.

### 7.3 Dự đoán và kiểm chứng

| Quan sát | Iframe A: không sandbox | Iframe B: `sandbox="allow-scripts"` |
|---|---|---|
| Nội dung | `srcdoc` | Cùng `srcdoc` |
| Script chạy | Có nếu không bị policy khác chặn | Có do `allow-scripts` |
| `event.origin` ở trang cha | Thường là `"http://localhost:8080"` | **`"null"`** |
| `localStorage` | Thường hoạt động | Thường ném **SecurityError** |
| Đọc DOM cha theo SOP | Có thể do origin kế thừa | Bị chặn |

Dùng DevTools ở ngữ cảnh trang cha, thử:

~~~js
document.querySelector('#regular').contentWindow.document.body
document.querySelector('#isolated').contentWindow.document.body
~~~

Lệnh thứ nhất thường trả về DOM của iframe A; lệnh thứ hai thường bị từ chối do khác origin. Tên lỗi hoặc thông báo cụ thể có thể khác nhau giữa các browser.

**Bài thử mở rộng:** tạo iframe C cùng `sandbox="allow-scripts"` và cùng `srcdoc`. C và B có thể cùng gửi `"null"` nhưng không được đọc DOM của nhau vì nhận opaque origin riêng.

### 7.4 Quan sát CORS nếu có API thử nghiệm

Nếu iframe opaque gọi API `http://localhost:4000/public` bằng Fetch ở mode `cors`, hãy kiểm tra Network:

- Header `Origin` của request chịu CORS từ iframe opaque có thể là `null`, còn từ iframe A sẽ là `http://localhost:8080`.
- Nếu response thiếu header CORS cần thiết, JavaScript không đọc được dữ liệu dù máy chủ đã nhận GET.
- Nếu response là dữ liệu công khai và `Access-Control-Allow-Origin: *`, script có thể đọc response khi không dùng credentials và các điều kiện khác hợp lệ.
- Nếu `connect-src` của CSP chặn đích, request có thể không được gửi; đây là lỗi khác với CORS.
- Đừng thử với tài khoản thật hay hệ thống không thuộc quyền kiểm thử của mình.

## 8. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| “Hai origin cùng serialize thành `null` là cùng origin” | Opaque origin có danh tính nội bộ riêng; chuỗi serialize không phải phép so sánh same-origin |
| “`srcdoc` luôn opaque” | Không sandbox, `srcdoc` thường kế thừa origin của trang nhúng |
| “`blob:` luôn opaque” | Blob URL thông thường gắn origin của môi trường tạo |
| “`allow-scripts` cấp quyền đọc DOM cha” | Quyền chạy script và SOP là hai kiểm tra khác nhau |
| “`allow-same-origin` làm URL khác origin trở thành cùng origin với cha” | Nó bỏ ép opaque của sandbox; origin thực của URL vẫn được giữ |
| “CORS `Origin: null` tin được một iframe cụ thể” | Nhiều nguồn không đáng tin có thể cùng serialize thành `null` |
| “Opaque origin không được gửi HTTP request” | Request vẫn có thể gửi nếu policy cho phép, nhưng bị xét là cross-origin khi thích hợp |
| “`no-cors` biến opaque response thành dữ liệu đọc được” | Opaque response là một loại Fetch response không đọc được body, khác với opaque origin |
| “`event.origin === 'null'` là xác thực” | Cần kiểm tra source, dữ liệu, phiên và cơ chế xác thực phù hợp |
| “Bật Trusted Types là đủ cô lập iframe” | Trusted Types phòng DOM XSS ở sink phù hợp, không thay thế sandbox/SOP |

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Hai iframe cùng chứa `data:text/html,...` và đều gửi `event.origin === "null"`. Chúng có được coi là same-origin không?

**Đáp án:** Không. Các tài liệu `data:` riêng được gán opaque origin khác nhau. Giá trị `"null"` chỉ là serialization.

**Câu 2.** Trang `https://app.example.com` nhúng iframe `srcdoc` với `sandbox="allow-scripts"`. Script trong iframe có thể đọc `parent.document.cookie` không?

**Đáp án:** Không theo quyền same-origin. Iframe có opaque origin khác cha; SOP ngăn quyền đọc DOM/cookie của cha dù script vẫn được phép chạy.

**Câu 3.** Mọi URL `blob:` có opaque origin không?

**Đáp án:** Không. Blob URL thường gắn với origin của môi trường tạo. Nếu tạo trong tuple origin, nó thường gắn với tuple origin đó; nếu tạo trong opaque origin, nó có thể gắn với origin opaque đó.

**Câu 4.** API trả `Access-Control-Allow-Origin: null` có chắc chỉ cho phép iframe sandbox của ứng dụng mình không?

**Đáp án:** Không. Nhiều ngữ cảnh khác cũng có origin serialize thành `null`. Không coi giá trị này là định danh đáng tin; phải dùng authentication, authorization và các kiểm soát server tương ứng.

**Câu 5.** Vì sao `sandbox="allow-scripts allow-same-origin"` rủi ro với HTML không đáng tin được phục vụ cùng origin với trang cha?

**Đáp án:** Script được chạy và không còn bị ép opaque. Nếu thực tế cùng origin với cha, nó có thể có khả năng thay đổi phần tử iframe và làm suy yếu sandbox khi tải lại. Cần cách ly bằng origin riêng và quyền tối thiểu.

**Câu 6.** Iframe opaque không dùng được `localStorage`. Điều đó chứng minh mọi request từ nó đều không có cookie?

**Đáp án:** Không. Quyền lưu trữ và quy tắc gửi cookie là hai cơ chế riêng. Cần kiểm tra Fetch credentials, SameSite, Secure, phạm vi cookie và chính sách trình duyệt.

**Câu 7.** Trang cha muốn trao đổi thông tin không nhạy cảm với iframe opaque mà vẫn giữ SOP thì dùng cơ chế nào?

**Đáp án:** `postMessage` hoặc kênh MessageChannel được thiết kế có kiểm soát source, schema và vòng đời. Không dùng `event.origin === "null"` làm bằng chứng danh tính duy nhất.

## 10. Checklist ứng dụng

Trước khi quyết định tin hoặc cấp quyền cho một tài liệu có opaque origin, hãy hỏi:

1. **Vì sao origin opaque được tạo?** Do `data:`, sandbox thiếu `allow-same-origin`, môi trường opaque trước đó hay đặc thù browser?
2. **Script có được chạy không?** Quyền này khác với quyền đọc DOM, cookie hoặc storage.
3. **Nó có thể đọc origin nào?** Không dùng chuỗi `"null"` để suy đoán quan hệ same-origin.
4. **Nó gọi API nào?** Kiểm tra CSP, Fetch mode, CORS và kiểm soát server.
5. **Credentials có thể đi cùng request không?** Đánh giá cookie flags, SameSite và chính sách trình duyệt.
6. **Ai gửi thông điệp `postMessage`?** Kiểm tra nguồn và tính hợp lệ của nội dung; dùng capability/nonce nếu có tác vụ nhạy cảm.
7. **CSP, sandbox, Trusted Types và frame headers có vai trò nào?** Dùng đúng lớp phòng vệ cho XSS, CSRF, clickjacking và cách ly.

**Kết luận kiến thức:** Opaque origin là một danh tính bảo mật nội bộ giúp tách tài liệu khỏi quyền same-origin thông thường. Nhiều opaque origin serialize thành **`"null"`** nhưng **không cùng origin**. Phòng vệ ứng dụng vẫn cần kết hợp sandbox tối thiểu, SOP, CORS đúng phạm vi, bảo vệ cookie/CSRF, CSP, Trusted Types và kiểm soát nhúng.

## Tài liệu tham khảo

- [WHATWG HTML Standard — Origins](https://html.spec.whatwg.org/multipage/browsers.html#concept-origin)
- [MDN — Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
- [MDN — Data URLs](https://developer.mozilla.org/en-US/docs/Web/URI/Reference/Schemes/data)
- [MDN — Iframe và thuộc tính sandbox](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Window.postMessage()](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage)

