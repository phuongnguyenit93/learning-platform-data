# Site isolation: cách trình duyệt cách ly các site ở mức tiến trình

## 1. Vì sao Same-Origin Policy vẫn cần thêm Site Isolation?

Hãy hình dung một trang quản trị nội bộ mở một khung quảng cáo từ website khác. **Same-Origin Policy (SOP)** ngăn JavaScript trong khung quảng cáo đọc trực tiếp DOM và dữ liệu lưu trữ của trang quản trị. Tuy nhiên, nếu mã xử lý hai trang cùng chạy trong một tiến trình của trình duyệt, chúng có thể cùng hiện diện trong không gian bộ nhớ của tiến trình đó.

Những lớp tấn công như **Spectre** cho thấy đôi khi kẻ tấn công có thể lợi dụng hành vi thực thi suy đoán và kênh phụ để suy ra thông tin trong bộ nhớ, vượt ra ngoài mô hình “JavaScript chỉ được dùng những API được phép”. SOP chủ yếu kiểm soát **quyền truy cập qua API**; để giảm lượng dữ liệu nhạy cảm xuất hiện trong cùng không gian bộ nhớ với nội dung không tin cậy, trình duyệt cần một lớp cách ly thấp hơn.

**Site isolation** là kiến trúc bảo mật mà trong đó trình duyệt cố gắng đặt nội dung từ các **site khác nhau** vào những tiến trình kết xuất (*renderer process*) riêng, với ranh giới hệ điều hành và cơ chế kiểm soát giao tiếp giữa tiến trình. Một ví dụ nổi bật là **Site Isolation** trong Chromium; Firefox có kiến trúc cách ly site mang tên **Fission**. Chính sách triển khai cụ thể còn phụ thuộc trình duyệt, phiên bản, nền tảng và tài nguyên hệ thống.

Đây là một mắt xích quan trọng trong mô hình bảo mật ứng dụng web:

- **Origin** xác định danh tính để SOP giới hạn quyền đọc DOM và nhiều API.
- **Site** thường là đơn vị được dùng để nhóm hoặc tách tiến trình khi triển khai site isolation.
- **Cookie và SameSite** có các quy tắc riêng, phục vụ quản lý trạng thái đăng nhập và giảm nguy cơ CSRF.
- **CORS, CSP, Trusted Types, sandbox, security headers** bảo vệ những đường dữ liệu, điểm thực thi và quan hệ nhúng mà site isolation không tự xử lý.

Sau bài học, bạn sẽ phân biệt được các ranh giới đó, đọc sơ đồ tiến trình của một trang có iframe, và kiểm chứng hành vi trên trình duyệt thực tế.

## 2. Phân biệt site, origin và tiến trình

### 2.1 Origin: đơn vị của SOP

Với URL HTTP(S) thông thường:

```text
origin = (scheme, host, port)

https://app.example.com:443/dashboard
  scheme: https
  host:   app.example.com
  port:   443 (mặc định của HTTPS)
```

Hai URL cùng origin khi **cả ba thành phần** tương ứng bằng nhau. Đường dẫn, query và fragment không làm đổi origin. Ví dụ `https://app.example.com/dashboard` và `https://app.example.com/settings` cùng origin, nhưng `https://api.example.com` khác origin.

### 2.2 Site: đơn vị rộng hơn origin

Trong mô hình **schemeful site** thường dùng trên web hiện đại, site được xác định bởi **scheme** và **registrable domain** (miền có thể đăng ký, xác định theo Public Suffix List). Với host là IP hoặc một tên máy đặc biệt, quy tắc xác định site sử dụng host tương ứng thay vì tự suy ra “hai host cùng máy”.

Ví dụ khi xuất phát từ `https://app.example.com`:

| URL đích | Same-origin? | Same-site? | Giải thích |
| --- | --- | --- | --- |
| `https://app.example.com/a` | Có | Có | Cùng scheme, host, port. |
| `https://api.example.com/v1` | Không | Có | Khác subdomain, cùng site `https://example.com`. |
| `https://app.example.com:8443/` | Không | Có | Port khác làm đổi origin, thường không làm đổi site. |
| `http://app.example.com/` | Không | Không | Scheme khác trong mô hình schemeful same-site. |
| `https://other.example.net/` | Không | Không | Registrable domain khác. |

**Lưu ý về Public Suffix List:** không thể chỉ cắt lấy hai nhãn cuối của hostname. Chẳng hạn `a.github.io` và `b.github.io` được xem là hai site khác nhau theo danh sách hậu tố công khai, dù cùng kết thúc bằng `github.io`.

### 2.3 Tiến trình là đơn vị cách ly của hệ điều hành

Một **renderer process** là tiến trình thực hiện nhiều công việc kết xuất nội dung, xử lý DOM và chạy JavaScript. Một site có thể dùng nhiều renderer process; cũng có những trường hợp trình duyệt tái sử dụng tiến trình theo chính sách quản lý tài nguyên. Vì vậy:

> “Same-site” không có nghĩa chắc chắn cùng tiến trình, và “cross-origin” không có nghĩa chắc chắn khác tiến trình.

Mấu chốt của site isolation là **trình duyệt có thể tách nội dung của những site khác nhau thành các tiến trình riêng**, rồi dùng cơ chế IPC (inter-process communication) để phối hợp kết xuất và tương tác.

## 3. Site isolation hoạt động như thế nào?

Trình duyệt đa tiến trình có những thành phần lớn:

| Thành phần | Trách nhiệm khái quát | Liên hệ bảo mật |
| --- | --- | --- |
| **Browser process** | Điều phối tab, điều hướng, quyền truy cập và nhiều dịch vụ của trình duyệt. | Kiểm soát các quyết định vượt ra ngoài một renderer; kiểm tra quyền đối với thao tác nhạy cảm. |
| **Renderer process** | Xử lý tài liệu web, DOM, CSS và JavaScript. | Được sandbox ở mức hệ điều hành theo kiến trúc trình duyệt; site isolation giảm phạm vi dữ liệu cùng nằm trong tiến trình. |
| **Frame / document** | Đơn vị nội dung hiển thị trong trang, kể cả iframe lồng nhau. | Mỗi document có origin và chính sách bảo mật riêng. |
| **IPC** | Kênh trao đổi thông tin giữa các tiến trình. | Cho phép ghép một trang có nhiều renderer mà không phải mở quyền đọc DOM chéo site. |

**Sơ đồ ý tưởng với iframe khác site:**

```text
Browser process
│
├── Renderer A: https://shop.example.com
│   ├── Document của tab chính
│   └── iframe cùng site: https://help.example.com
│        (có thể được xử lý ở cùng hoặc tiến trình khác,
│         tùy chính sách trình duyệt)
│
└── Renderer B: https://payments.example.net
    └── iframe thanh toán khác site

     Browser quản lý cây frame và phối hợp qua IPC.
     SOP vẫn kiểm tra quyền truy cập DOM giữa các origin.
```

Trong Chromium, một iframe khác site có thể trở thành **out-of-process iframe (OOPIF)**: giao diện cho người dùng trông như một trang liền mạch, trong khi phần iframe được kết xuất bởi renderer khác. Trình duyệt vẫn phải phối hợp vị trí, kích thước, focus, nhập liệu và các sự kiện cho các frame.

Lưu ý: sơ đồ mô tả cơ chế, **không bảo đảm mỗi frame hay site luôn có đúng một tiến trình**. Chiến lược phân bổ phụ thuộc cả thiết lập cách ly và tài nguyên; khi bộ nhớ hạn chế, trình duyệt có thể có các ngoại lệ hoặc tối ưu hóa tiến trình. Các tên kiến trúc như OOPIF và SiteInstance là đặc trưng triển khai của Chromium, không phải API web tiêu chuẩn mà ứng dụng được quyền giả định.

### 3.1 Một iframe khác site vẫn nằm trong cùng trang giao diện

```html
<main>
  <h1>Đơn hàng</h1>
  <iframe
    title="Thanh toán"
    src="https://payments.example.net/checkout">
  </iframe>
</main>
```

Đây là một trang có hai document. Nếu trình duyệt dùng OOPIF cho iframe thanh toán, DOM của document chính và DOM iframe được quản lý bởi các tiến trình khác nhau. Dù tiến trình được phân bổ ra sao, JavaScript ở trang chính **không có quyền tự do đọc** `iframe.contentWindow.document` vì iframe mang origin khác.

### 3.2 Trình duyệt duy trì quan hệ cửa sổ bằng tham chiếu hạn chế

Trang cha vẫn có thể gọi `iframe.contentWindow.postMessage(...)` thông qua tham chiếu cửa sổ. Trình duyệt thực hiện trao đổi thông điệp bằng cơ chế tương thích với những ranh giới tiến trình, nhưng không cấp quyền đọc dữ liệu chéo origin.

```javascript
const frame = document.querySelector("iframe");
const paymentOrigin = "https://payments.example.net";

frame.addEventListener("load", () => {
  frame.contentWindow.postMessage(
    { type: "REQUEST_STATUS" },
    paymentOrigin
  );
});

window.addEventListener("message", (event) => {
  if (event.origin !== paymentOrigin) return;
  if (event.source !== frame.contentWindow) return;
  if (event.data?.type !== "PAYMENT_STATUS") return;
  if (typeof event.data.ok !== "boolean") return;
  // Đối chiếu trạng thái thật với backend trước khi ghi nhận thanh toán.
  console.log("Thông điệp từ iframe:", event.data.ok);
});
```

**Bên nhận phải kiểm tra `event.origin`, `event.source` và cấu trúc dữ liệu**. Không dùng `targetOrigin: "*"` để gửi bí mật và không xem thông điệp từ iframe là chứng cứ thanh toán thành công. Kết quả nghiệp vụ phải được xác minh tại backend.

## 4. Site isolation bảo vệ trước loại rủi ro nào?

### 4.1 Giảm rủi ro rò rỉ dữ liệu bộ nhớ qua Spectre

SOP là ranh giới ở cấp API: mã trong `https://evil.example.net` không được trực tiếp đọc DOM của `https://bank.example.com`. Nhưng các cuộc tấn công kênh phụ từ thực thi suy đoán có thể cố suy ra thông tin mà CPU đã xử lý. Khi hai site khác nhau nằm trong những renderer riêng, renderer do attacker điều khiển không còn dễ có dữ liệu bí mật của site kia trong **cùng không gian địa chỉ tiến trình**.

Site isolation vì vậy làm giảm một lớp khả năng khai thác vượt ranh giới do **đặt dữ liệu nhạy cảm ngoài phạm vi bộ nhớ của renderer không tin cậy**. Đây không phải bảo đảm loại bỏ mọi kênh phụ phần cứng, và không thay thế cập nhật trình duyệt, hệ điều hành hay các bản vá vi xử lý.

### 4.2 Hạn chế phạm vi tác động khi renderer bị xâm phạm

Nếu mã độc khai thác một lỗi trong renderer của trang không tin cậy, việc các site khác được cách ly ở tiến trình riêng có thể giảm dữ liệu mà attacker truy cập trực tiếp trong tiến trình đó. Sandbox của renderer và các kiểm tra quyền ở browser process còn giúp giới hạn hành vi vượt ra ngoài tiến trình.

Tuy nhiên, nếu attacker đồng thời vượt sandbox hoặc khai thác lỗi ở browser process thì rủi ro vẫn tồn tại. Không nên trình bày site isolation như một cơ chế bảo vệ tuyệt đối khỏi mọi dạng chiếm quyền trình duyệt.

### 4.3 Những thứ Site Isolation *không* tự giải quyết

| Rủi ro | Vì sao cần cơ chế khác? | Phòng vệ phù hợp |
| --- | --- | --- |
| **XSS trong ứng dụng** | Script tấn công chạy ngay trong origin hợp lệ, có thể dùng quyền của document đó. | Output encoding đúng ngữ cảnh, `textContent`, CSP, Trusted Types. |
| **CSRF** | Trình duyệt vẫn có thể gửi request và cookie theo quy tắc cookie, dù trang gửi thuộc tiến trình khác. | CSRF token, `SameSite`, kiểm tra Origin/Referer và xác thực quyền. |
| **Clickjacking** | Trang khác vẫn có thể nhúng một số document trong iframe nếu không bị cấm. | CSP `frame-ancestors`, `X-Frame-Options` khi cần. |
| **CORS sai cấu hình** | Site isolation không quyết định script có được đọc phản hồi `fetch` cross-origin hay không. | Allowlist CORS chính xác, kiểm tra credentials, xác thực/phân quyền ở API. |
| **Thông điệp iframe giả mạo** | `postMessage` vẫn cho phép trao đổi dữ liệu giữa các cửa sổ. | Kiểm tra `event.origin`, `event.source`, schema, trạng thái request. |
| **Rò rỉ qua hành vi quan sát được** | Một số side channel hoặc XS-Leak còn có thể dựa vào thời gian, điều hướng hoặc trạng thái quan sát được. | Thiết kế luồng nhạy cảm, chính sách cách ly, kiểm tra quyền, giảm tín hiệu quan sát được. |

## 5. Vì sao Site Isolation không giống SOP?

Hai cơ chế bảo vệ ở **hai tầng khác nhau**:

```text
Ứng dụng: authentication, authorization, CSRF protection
       ↓
Web APIs: SOP, CORS, CSP, iframe sandbox, postMessage
       ↓
Kiến trúc trình duyệt: site/process isolation, renderer sandbox, IPC
       ↓
Hệ điều hành: tiến trình, không gian bộ nhớ, sandbox/quyền
```

- **SOP:** quyết định JavaScript có thể đọc/sửa một số dữ liệu của document khác origin thông qua API hay không.
- **Site isolation:** quyết định cách trình duyệt phân bố công việc và dữ liệu của các site giữa các tiến trình nhằm tăng cách ly bộ nhớ.
- **CORS:** cho phép server mở quyền đọc phản hồi mạng cross-origin một cách có kiểm soát.

Xét hai iframe:

1. `https://a.example.com` nhúng `https://b.example.com`: **khác origin nhưng cùng site**. SOP vẫn chặn đọc DOM; tùy cách tổ chức tiến trình, hai tài liệu có thể cùng renderer.
2. `https://a.example.com` nhúng `https://other.example.net`: **khác origin và khác site**. SOP vẫn chặn đọc DOM; một trình duyệt triển khai site isolation đầy đủ thường đặt iframe khác site vào renderer riêng.

Vì thế, **không suy luận quyền DOM từ số lượng tiến trình** và không suy luận một cơ chế cách ly tiến trình chỉ từ việc `contentDocument` trả về `null`.

## 6. Site isolation và những cơ chế cách ly khác

Các tên dễ gây nhầm gồm *site isolation*, *origin isolation*, *cross-origin isolation* và *agent cluster*. Chúng liên quan nhưng không đồng nhất.

### 6.1 Origin-Agent-Cluster (OAC)

Một server có thể gửi:

```http
Origin-Agent-Cluster: ?1
```

Header này yêu cầu trình duyệt (nếu hỗ trợ) tổ chức **agent cluster theo origin**, thay vì gộp các origin có liên hệ tương thích trong cùng cụm thực thi. Nó giúp tăng tính tách biệt giữa các origin và hạn chế một số kiểu chia sẻ tài nguyên/khả năng nới origin cũ.

Có thể quan sát giá trị:

```javascript
console.log(window.originAgentCluster);
```

Giá trị được hỗ trợ và ý nghĩa triển khai phụ thuộc trình duyệt. **OAC không phải cam kết rằng mỗi origin được cấp một tiến trình hệ điều hành riêng**. API `document.domain` từng dùng để nới SOP giữa subdomain nay đã lỗi thời; ứng dụng mới nên dùng `postMessage` và API rõ ràng thay cho cơ chế đó.

### 6.2 COOP: tách quan hệ giữa các cửa sổ cấp cao nhất

**Cross-Origin-Opener-Policy (COOP)** điều khiển việc document cấp cao nhất có thể cùng *browsing context group* với các cửa sổ khác hay không:

```http
Cross-Origin-Opener-Policy: same-origin
```

Khi chính sách này được áp dụng, trình duyệt có thể cắt quan hệ `window.opener` với popup khác origin hoặc làm cho tham chiếu trả về từ `window.open` không còn dùng được như trước. Đây là thay đổi về **quan hệ cửa sổ**, không phải một cú pháp bật/tắt site isolation cho iframe.

Ứng dụng thanh toán/đăng nhập bằng popup cần kiểm tra kỹ luồng callback khi thêm COOP.

### 6.3 COEP, CORP và trạng thái cross-origin isolated

**Cross-Origin-Embedder-Policy (COEP)** có thể yêu cầu tài liệu chỉ nhúng những tài nguyên cross-origin có cơ chế cấp phép phù hợp. Ví dụ:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Khi đáp ứng các yêu cầu bổ sung về secure context và chính sách trình duyệt, sự kết hợp phù hợp của COOP và COEP cho phép document đạt trạng thái **cross-origin isolated**, hữu ích cho một số API nhạy cảm.

```javascript
console.log(window.crossOriginIsolated);
```

Điều cần phân biệt: `crossOriginIsolated === true` là trạng thái chính sách web có những điều kiện riêng; nó **không phải một công tắc hay phép đo trực tiếp xác nhận mọi iframe đang ở tiến trình khác nhau**.

**Cross-Origin-Resource-Policy (CORP)** là response header do tài nguyên cung cấp để kiểm soát một số kiểu tải tài nguyên *no-CORS*. Ví dụ với tài nguyên chỉ dành cho cùng site:

```http
Cross-Origin-Resource-Policy: same-site
```

Nếu tài nguyên cần được nhúng từ bất cứ origin nào, bên cung cấp có thể cân nhắc `Cross-Origin-Resource-Policy: cross-origin` theo tính công khai của tài nguyên. CORP không đồng nghĩa với cơ chế cấp quyền đọc phản hồi bằng CORS. COEP `require-corp` cũng có thể làm hỏng ảnh, script hoặc tài nguyên nhúng chưa được cấu hình phù hợp; phải thử nghiệm thực tế.

### 6.4 CSP, sandbox và chính sách khung

Để **ngăn trang khác nhúng một trang nhạy cảm**, server của trang nhạy cảm có thể trả:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

`frame-ancestors` được áp dụng qua **HTTP response header** (không hỗ trợ qua `meta`) và giúp chống clickjacking. Nếu nghiệp vụ phải cho một cổng thông tin nhúng trang, nên dùng allowlist origin cụ thể.

Để **hạn chế quyền nội dung nhúng**, trang chủ động nhúng có thể dùng:

```html
<iframe
  title="Bản xem trước không tin cậy"
  sandbox=""
  srcdoc="<p>Nội dung xem trước</p>">
</iframe>
```

`sandbox=""` khóa nhiều quyền, bao gồm script, và làm cho nội dung nhận opaque origin. Nếu cần cho phép script nhưng vẫn tách origin, có thể dùng `sandbox="allow-scripts"` và đánh giá các khả năng cần thiết. Tránh kết hợp `allow-scripts` và `allow-same-origin` cho nội dung cùng origin không tin cậy, vì có thể phá vỡ mục tiêu cách ly.

Các cơ chế này điều chỉnh **quyền web và khả năng nhúng**, trong khi site isolation xử lý **kiến trúc tiến trình**.

## 7. Mối liên hệ với cookie và chính sách SameSite

Site isolation sử dụng khái niệm site nhưng **không phải** là cơ chế quản lý cookie. Cookie tuân theo domain/host, path, `Secure`, `HttpOnly`, `SameSite` và chính sách cookie/partitioning của từng trình duyệt.

```http
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Ví dụ:

- `https://app.example.com` và `https://api.example.com` thường **same-site** nhưng **cross-origin**.
- Cookie đặt `Domain=example.com` có thể áp dụng cho các subdomain phù hợp; cookie không phân vùng theo port như origin.
- Thuộc tính `SameSite` đánh giá **ngữ cảnh gửi cookie**, không cấp quyền truy cập DOM.
- Một subdomain cùng site bị chiếm quyền có thể tạo các request same-site; do đó không thể chỉ dựa vào `SameSite` để xử lý mọi biến thể CSRF.

**Hệ quả:** đừng coi “iframe đã chạy ở tiến trình khác” là bằng chứng cookie không được gửi, và đừng coi “cookie là same-site” là bằng chứng trang nhúng được đọc DOM. Backend vẫn phải xác thực, phân quyền và chống CSRF cho hành động thay đổi trạng thái.

## 8. Thực hành: quan sát sự khác nhau giữa site và origin

Để quan sát hai loại ranh giới, hãy phục vụ hai tệp HTML mẫu bằng HTTP server cục bộ. Dùng các địa chỉ sau (nên để server phía iframe lắng nghe trên loopback để truy cập được cả `localhost` và `127.0.0.1`):

| Vai trò | URL | Quan hệ với trang cha |
| --- | --- | --- |
| Trang cha | `http://localhost:3000/index.html` | Origin gốc. |
| Iframe thử nghiệm 1 | `http://localhost:4000/child.html` | **Cross-origin, same-site** (khác port). |
| Iframe thử nghiệm 2 | `http://127.0.0.1:4000/child.html` | **Cross-origin, cross-site** (khác host/site). |

Hai tên `localhost` và `127.0.0.1` đều trỏ về máy cục bộ trong ngữ cảnh thường gặp, nhưng **không vì thế trở thành cùng site**. Kết quả phân bổ tiến trình có thể khác theo browser và cấu hình bảo mật.

### 8.1 Trang cha: index.html

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Kiểm chứng site isolation</title></head>
<body>
  <h1>Trang cha: localhost:3000</h1>
  <label for="target">Chọn URL iframe:</label>
  <select id="target">
    <option value="http://localhost:4000/child.html">
      Cross-origin, same-site
    </option>
    <option value="http://127.0.0.1:4000/child.html">
      Cross-origin, cross-site
    </option>
  </select>
  <iframe id="child" title="Tài liệu con" width="500" height="170"></iframe>
  <pre id="result">Đang tải...</pre>
  <script>
    const frame = document.querySelector("#child");
    const target = document.querySelector("#target");
    const output = document.querySelector("#result");

    function loadFrame() {
      output.textContent = "Đang tải iframe...";
      frame.src = target.value;
    }

    target.addEventListener("change", loadFrame);
    frame.addEventListener("load", () => {
      const expectedOrigin = new URL(target.value).origin;
      output.textContent =
        "Trang cha: " + location.origin + "\n" +
        "Iframe: " + expectedOrigin + "\n" +
        "contentDocument === null: " + (frame.contentDocument === null);

      frame.contentWindow.postMessage(
        { type: "PING", requestId: "lab-1" },
        expectedOrigin
      );
    });

    window.addEventListener("message", (event) => {
      const expectedOrigin = new URL(target.value).origin;
      if (event.origin !== expectedOrigin) return;
      if (event.source !== frame.contentWindow) return;
      if (event.data?.type !== "PONG") return;
      if (event.data.requestId !== "lab-1") return;
      if (typeof event.data.message !== "string") return;
      output.textContent += "\n" + event.data.message;
    });

    loadFrame();
  </script>
</body>
</html>
```

Đoạn code trên chỉ trình diễn kiểm tra origin cho thông điệp đơn giản. Ứng dụng thật nên dùng request ID không đoán được, gắn với mỗi yêu cầu đang chờ và có giới hạn vòng đời, đặc biệt khi trao đổi dữ liệu nhạy cảm.

### 8.2 Trang con: child.html

```html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Iframe thí nghiệm</title></head>
<body>
  <h2>Iframe ở cổng 4000</h2>
  <p id="origin"></p>
  <script>
    document.querySelector("#origin").textContent = location.origin;
    const allowedParentOrigin = "http://localhost:3000";

    window.addEventListener("message", (event) => {
      if (event.origin !== allowedParentOrigin) return;
      if (event.source !== window.parent) return;
      if (event.data?.type !== "PING") return;
      if (event.data.requestId !== "lab-1") return;
      event.source.postMessage(
        {
          type: "PONG",
          requestId: "lab-1",
          message: "PONG từ " + location.origin
        },
        allowedParentOrigin
      );
    });
  </script>
</body>
</html>
```

### 8.3 Quy trình quan sát

1. Mở `http://localhost:3000/index.html`. Chọn iframe `localhost:4000`. Xác nhận hai origin khác nhau do port, nhưng cùng site. Giá trị `frame.contentDocument === null` dự kiến là `true`.
2. Chuyển sang `127.0.0.1:4000`. Hai document giờ vừa khác origin vừa khác site, nhưng kết quả kiểm tra DOM vẫn tương tự. Cả hai trường hợp đều có thể nhận `PONG` qua `postMessage` khi kiểm tra nguồn và payload phù hợp.
3. Với **Chromium/Chrome trên desktop**, mở trình quản lý tác vụ của trình duyệt (thường bằng `Shift+Esc`). Nếu có, bật cột **Process ID** và quan sát những tác vụ tab/subframe. Iframe cross-site thường có thể xuất hiện với tiến trình khác. Việc hiển thị và phân bổ phụ thuộc phiên bản, cờ bảo mật và tài nguyên; không dùng số PID như một chứng minh chắc chắn của SOP.
4. Trong DevTools, kiểm tra cây iframe và Console. Thử đọc `frame.contentWindow.document.body` từ trang cha; với cả hai URL iframe, thao tác này thường ném `SecurityError`. Điều đó minh họa SOP, **không tự chứng minh site isolation**.
5. Tắt phần xử lý `message` hoặc đổi `targetOrigin` thành origin không khớp; quan sát thông điệp không được chấp nhận/giao như dự kiến. Khôi phục cấu hình đúng và kiểm tra lại.
6. Thử thêm `sandbox="allow-scripts"` vào iframe. Document con lúc này có opaque origin (do thiếu `allow-same-origin`), nên bộ kiểm tra `event.origin` hiện tại của trang cha không chấp nhận phản hồi `PONG`. Đừng nới kiểm tra sang mọi origin để che lỗi thiết kế.

**Điểm cần rút ra:** sự khác nhau về **site** có thể ảnh hưởng đến phân bổ renderer; sự khác nhau về **origin** quyết định quyền DOM theo SOP; còn `postMessage` vẫn hoạt động nếu giao thức và các chính sách khác cho phép.

## 9. Ứng dụng thực tế: lựa chọn biện pháp phòng vệ

Giả sử một hệ thống thương mại điện tử có:

```text
https://shop.example.com       Ứng dụng chính
https://admin.example.com      Trang quản trị (same-site, cross-origin)
https://payments.example.net   Đối tác thanh toán (cross-site)
https://cdn.example.net        Máy chủ tài nguyên bên thứ ba (cross-site)
```

Một số quyết định thiết kế hợp lý:

1. **Admin:** xác thực mạnh và phân quyền backend độc lập; không tin rằng cùng site đồng nghĩa cùng quyền. Khi có thể, phân tách nội dung không tin cậy khỏi origin admin và áp dụng CSP/Trusted Types.
2. **Thanh toán:** nhúng hoặc mở popup theo hợp đồng kỹ thuật của đối tác; giới hạn origin trong `postMessage` và xác nhận kết quả giao dịch bằng backend. Kiểm tra tác động của COOP trước khi dùng popup.
3. **CDN:** chỉ cho tải tài nguyên cần thiết, xác định rõ chính sách CSP/CORS/CORP; không xem script từ CDN là “chạy ở origin của CDN” sau khi được nhúng bằng thẻ `script`.
4. **Cookie:** dùng `Secure`, `HttpOnly`, `SameSite` theo luồng nghiệp vụ; hạn chế phạm vi `Domain` và `Path`; triển khai chống CSRF khi cần.
5. **Chống clickjacking:** trả `Content-Security-Policy: frame-ancestors ...` phù hợp ở trang chứa thao tác nhạy cảm.
6. **Kiểm chứng:** thử cả same-origin, cross-origin same-site và cross-site; không suy luận từ một trường hợp localhost duy nhất.

### Những ngộ nhận thường gặp

| Nhận định | Đánh giá đúng |
| --- | --- |
| “Site isolation ngăn mọi XSS.” | Sai. XSS chạy trong origin của chính ứng dụng; cần xử lý DOM an toàn, CSP và Trusted Types. |
| “Khác origin luôn khác renderer process.” | Sai. Ranh giới origin và site không trùng nhau; việc phân bổ process phụ thuộc browser. |
| “Cùng site được phép đọc DOM của nhau.” | Sai. SOP kiểm tra origin, không phải chỉ registrable domain. |
| “COOP, COEP và site isolation là một.” | Sai. COOP/COEP là chính sách web với tác dụng cụ thể; site isolation là kiến trúc tiến trình của trình duyệt. |
| “Chuyển nội dung sang iframe là đã an toàn.” | Sai. Cần xét origin, sandbox, quyền nhúng, thông điệp và bản chất nội dung. |
| “CORS chặn request CSRF vì khác tiến trình.” | Sai. CORS chủ yếu kiểm soát quyền đọc phản hồi bằng script; CSRF cần phòng vệ phía server. |

## 10. Câu hỏi kiểm tra và bài tập

1. Tại sao `https://a.example.com` và `https://b.example.com` có thể cùng site nhưng không cùng origin? Điều đó ảnh hưởng gì tới DOM và renderer?
2. Một iframe cross-site có thể hiển thị bên trong tab chính dù được kết xuất bởi tiến trình khác không? Trình duyệt dùng cơ chế gì để phối hợp?
3. Site isolation giúp giảm rủi ro từ Spectre theo cách nào? Tại sao nó không loại bỏ mọi kênh phụ?
4. `Origin-Agent-Cluster: ?1` có bảo đảm tạo tiến trình hệ điều hành riêng cho mỗi origin không?
5. `window.crossOriginIsolated === true` có chứng minh mỗi iframe khác origin đang được kết xuất bởi một renderer riêng không?
6. Vì sao một popup đăng nhập có thể bị ảnh hưởng khi bật `Cross-Origin-Opener-Policy: same-origin`?
7. Một site đã dùng OOPIF cho iframe quảng cáo có còn cần `frame-ancestors`, chống XSS và CSRF không? Giải thích theo từng loại tấn công.
8. Dùng công cụ của trình duyệt để so sánh hai iframe: `http://localhost:4000` và `http://127.0.0.1:4000` với cha `http://localhost:3000`. Tách riêng kết luận về origin, site, SOP và tiến trình.

## 11. Tổng kết

**Site isolation** tăng độ an toàn bằng cách đưa nội dung của các site khác nhau vào những tiến trình kết xuất được cách ly trong các trường hợp trình duyệt hỗ trợ. Cơ chế này bổ sung ranh giới bộ nhớ và sandbox cho SOP, đặc biệt hữu ích để giảm rủi ro rò rỉ dữ liệu do khai thác renderer hoặc các kênh phụ như Spectre.

Ba câu hỏi cần được trả lời riêng khi thiết kế và kiểm chứng bảo mật trình duyệt:

- **Origin nào?** Để xác định giới hạn đọc DOM, storage và quyền API theo SOP/CORS.
- **Site nào?** Để hiểu quan hệ same-site của cookie và khả năng phân tách renderer trong kiến trúc site isolation.
- **Chính sách nào?** Để kiểm soát iframe, popup, tài nguyên, DOM và hành động nhạy cảm bằng CSP, Trusted Types, COOP/COEP, CORP, sandbox, security headers, xác thực và chống CSRF.

Thực hành trên các origin/site khác nhau và quan sát DevTools sẽ giúp tách những lớp bảo vệ này một cách rõ ràng, tránh kỳ vọng rằng một cơ chế đơn lẻ có thể thay thế toàn bộ thiết kế bảo mật ứng dụng web.
