# CSRF negative test: kiểm chứng yêu cầu giả mạo bị từ chối

**Chương:** CSRF  
**Mô-đun:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**CSRF negative test** là nhóm kiểm thử xác nhận server **từ chối** các request có thể được trình duyệt của nạn nhân gửi đi ngoài ý muốn, khi request thiếu bằng chứng hợp lệ cho thao tác được bảo vệ. Một bài test tốt không chỉ xác nhận HTTP trả `403`; nó còn chứng minh dữ liệu không thay đổi, không phát sinh giao dịch, không gửi email và không đẩy công việc nền.

CSRF (Cross-Site Request Forgery) khai thác việc trình duyệt tự đính kèm thông tin xác thực — thường là cookie phiên — vào request. Kẻ tấn công có thể dụ người dùng đã đăng nhập mở một trang khác, rồi trang đó gửi form hoặc request tới ứng dụng đích. SOP và CORS giới hạn khả năng đọc phản hồi cross-origin, nhưng **không tự ngăn mọi request được gửi**. Vì vậy kiểm thử âm tính phải xác minh chính sách ở phía server.

Bài này tập trung vào cách thiết kế test âm tính có thể lặp lại trong CI và cách kiểm chứng bằng browser thật. Mục tiêu là chứng minh những request không hợp lệ bị chặn mà luồng hợp lệ vẫn hoạt động.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích một CSRF negative test cần chứng minh điều gì ngoài status code.
2. Xây dựng test matrix cho token thiếu/sai/hết hạn, session không khớp, Origin/Referer không hợp lệ và Fetch Metadata.
3. Phân biệt CSRF với CORS, SOP, XSS và xác thực/phân quyền.
4. Kiểm tra request được gửi qua form HTML, Fetch và các content type đơn giản.
5. Xác minh server không tạo side effect khi từ chối request.
6. Tổ chức kiểm thử đơn vị, integration, browser và regression trong CI.
7. Tránh những test giả an toàn, chẳng hạn chỉ kiểm tra preflight hoặc chỉ kiểm tra giao diện không có nút thao tác.

## 2. Mô hình đe dọa và tiêu chí kiểm thử

Giả sử người dùng đăng nhập vào `https://bank.example.test`. Trình duyệt lưu cookie phiên. Người dùng sau đó mở `https://attacker.example.test`. Trang tấn công không đọc được DOM của ngân hàng, nhưng có thể thử gửi một form đến endpoint đổi email hoặc chuyển tiền:

```html
<form action="https://bank.example.test/account/email" method="POST">
  <input name="email" value="attacker@example.test">
  <button>Continue</button>
</form>
```

Nếu browser gửi cookie phiên phù hợp và server không xác minh request, thao tác có thể xảy ra dù người dùng không chủ động thực hiện trong ứng dụng ngân hàng.

Một negative test phải kiểm tra đồng thời:

- **Request bị từ chối:** server trả response phù hợp với chính sách (thường `403 Forbidden` hoặc `400 Bad Request` tùy hợp đồng API).
- **Không có side effect:** email, số dư, quyền, đơn hàng, trạng thái phiên, queue và các bản ghi nghiệp vụ giữ nguyên.
- **Không rò rỉ bí mật:** response không tiết lộ CSRF token hợp lệ, session ID, dữ liệu cá nhân hay thông tin nội bộ.
- **Luồng hợp lệ vẫn chạy:** request có session, token và nguồn hợp lệ vẫn thành công.
- **Kết quả lặp lại:** test chạy được nhiều lần, không phụ thuộc trạng thái từ test trước.

Không dùng một status code duy nhất làm tiêu chí. Một endpoint có thể trả `200` với trang lỗi được render, hoặc trả `302` về trang đăng nhập; điều quan trọng là hợp đồng response đã định nghĩa và **trạng thái nghiệp vụ không đổi**. Với API, nên có response lỗi rõ ràng, không chuyển hướng âm thầm sang HTML login nếu client mong đợi JSON.

## 3. CSRF khác CORS và SOP như thế nào?

Ba cơ chế này có nhiệm vụ khác nhau:

| Cơ chế | Bảo vệ điều gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| Same-Origin Policy (SOP) | Giới hạn script đọc dữ liệu/DOM giữa các origin | Không chặn mọi form, navigation hoặc request cross-origin |
| CORS | Cho phép hoặc từ chối JavaScript đọc response cross-origin theo header server | Không phải cơ chế tổng quát ngăn request được gửi; không thay thế CSRF token |
| CSRF defense | Kiểm tra request có xuất phát từ luồng được ứng dụng cho phép hay không | Không ngăn XSS chạy ngay trong origin ứng dụng |
| Authentication | Xác định người dùng/phiên nào đang gửi request | Không chứng minh người dùng chủ động xác nhận hành động |
| Authorization | Xác định phiên/người dùng có quyền thực hiện thao tác | Không tự phân biệt request hợp lệ với request CSRF |

Ví dụ, một form cross-origin dùng `application/x-www-form-urlencoded` thường có thể được gửi mà không cần CORS preflight. Browser có thể gửi request, nhưng script bên ngoài không được đọc response nếu CORS không cho phép. Nếu server thực hiện chuyển tiền trước khi response bị chặn đọc, CORS không cứu được giao dịch.

**Negative test bắt buộc phải thử request thực sự được gửi**, đặc biệt là form POST và các content type mà HTML form có thể tạo ra. Đừng chỉ test rằng JavaScript attacker không đọc được response.

## 4. Những lớp phòng vệ cần được kiểm thử

### 4.1. Synchronizer token

Với mô hình session phía server, server tạo CSRF token khó đoán, gắn token với phiên, rồi đưa token vào form hoặc một header được ứng dụng kiểm soát. Server xác minh token ở mọi request thay đổi trạng thái.

Negative cases điển hình:

- thiếu token;
- token sai hoặc đã bị sửa;
- token thuộc một session khác;
- token hết hạn nếu thiết kế có thời hạn;
- token sai định dạng hoặc rỗng.

Không mặc định mọi CSRF token phải dùng một lần. Nhiều triển khai synchronizer token cho phép tái sử dụng token trong thời gian session hợp lệ. Chỉ test token replay là bất hợp lệ khi thiết kế của ứng dụng thực sự dùng nonce dùng một lần.

Token không nên nằm trong URL, log, analytics hoặc nơi có thể bị lộ qua `Referer`. Trang chứa token cần cache policy phù hợp, thường là `Cache-Control: no-store` cho nội dung nhạy cảm.

### 4.2. Double-submit cookie

Mô hình double-submit đặt một giá trị trong cookie và yêu cầu client gửi lại giá trị tương ứng trong một field hoặc header khác. Server so sánh hai giá trị.

Một triển khai **naive** có thể yếu trước cookie injection/tossing từ subdomain nếu attacker có thể ghi cookie domain rộng. Với cookie phiên hoặc token nhạy cảm, cân nhắc cookie host-only có prefix `__Host-` và triển khai **signed double-submit** ràng buộc token với session. Không coi việc hai chuỗi bằng nhau là bằng chứng đầy đủ nếu attacker có thể tự đặt cả hai.

Negative tests cần bao gồm:

- cookie token không tồn tại;
- request field/header không tồn tại;
- hai giá trị không khớp;
- token không có chữ ký hợp lệ hoặc không ràng buộc đúng session (với signed design);
- cookie token được tạo từ nguồn không đáng tin không thể thay thế token hợp lệ.

### 4.3. Kiểm tra Origin và Referer

Đối với request thay đổi trạng thái, server có thể xác minh `Origin` khớp chính xác origin của ứng dụng được phép, gồm scheme, hostname và port. Nếu `Origin` không có, có thể dùng `Referer` theo chính sách đã định. Một số request có thể mang `Origin: null`; không coi `null` là origin đáng tin.

Không dùng so khớp chuỗi hậu tố như `endsWith("example.com")`. Cách đó có thể chấp nhận hostname đánh lừa hoặc subdomain không thuộc allowlist. Dùng parser URL và allowlist origin chính xác.

Negative cases cần kiểm tra:

- Origin của website tấn công;
- Origin khác scheme hoặc port;
- Origin không có;
- Origin `null`;
- Referer thuộc website ngoài;
- Referer thiếu khi chính sách yêu cầu fallback;
- Origin và Referer mâu thuẫn (nếu ứng dụng kiểm tra cả hai).

Một số hệ thống qua reverse proxy cần xác định đúng public origin. Không tin header do client tự đặt như `X-Forwarded-Host` trừ khi nó được proxy tin cậy ghi đè và cấu hình rõ ràng.

### 4.4. Fetch Metadata

Browser hiện đại có thể gửi các header `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` để mô tả ngữ cảnh request. `Sec-Fetch-Site` thường có các giá trị `same-origin`, `same-site`, `cross-site` và `none`.

Server có thể từ chối request cross-site tới endpoint thay đổi trạng thái theo chính sách. Tuy nhiên:

- `same-site` không có nghĩa là origin tin cậy; subdomain do tenant hoặc bên thứ ba quản lý vẫn có thể cùng site.
- `none` có thể xuất hiện ở một số điều hướng do người dùng khởi tạo; cần chính sách riêng.
- Client không phải browser có thể không gửi Fetch Metadata.
- Header này là tín hiệu bổ sung, không thay thế token và kiểm tra nguồn.
- Không nên chặn mọi request thiếu Fetch Metadata nếu API phải hỗ trợ client hợp lệ không phải browser; xác định rõ nhóm client.

Negative test cần xác minh các request cross-site bị chặn, đồng thời test các luồng same-origin và những client được hỗ trợ.

### 4.5. SameSite cookie

`SameSite` kiểm soát khi nào browser gửi cookie trong ngữ cảnh cross-site:

- `Strict` hạn chế cookie trong các request cross-site.
- `Lax` cho phép một số điều hướng top-level an toàn (thường là GET), nhưng hạn chế nhiều subresource và POST cross-site.
- `None` cho phép ngữ cảnh cross-site theo quy tắc cookie và yêu cầu `Secure`.

SameSite là lớp phòng vệ hữu ích, nhưng không thay thế CSRF token. Request từ subdomain khác nhưng cùng site có thể vẫn được xem là same-site. Một số luồng đăng nhập, thanh toán hoặc liên kết từ website ngoài cũng có thể bị ảnh hưởng nếu chọn `Strict`.

Negative test nên kiểm tra browser gửi cookie trong những ngữ cảnh thực tế, thay vì chỉ đọc giá trị cấu hình `Set-Cookie`. Kết quả phụ thuộc scheme, site, loại navigation, method, browser và chính sách cookie bên thứ ba.
## 5. Ma trận CSRF negative test

Một test suite nên có **positive control** để chứng minh endpoint hoạt động với request hợp lệ, rồi mới chạy các trường hợp âm tính. Nếu mọi request đều bị từ chối do ứng dụng đang lỗi hoặc session hết hạn, một loạt negative test xanh không chứng minh được CSRF defense.

### 5.1. Ma trận request

Giả sử endpoint `POST /account/email` yêu cầu session đăng nhập, CSRF token hợp lệ và origin `https://app.example.test`. Quy định status code là ví dụ; dùng response contract của hệ thống thực tế.

| ID | Trường hợp | Kết quả mong đợi | Điều cần xác minh |
| --- | --- | --- | --- |
| POS-01 | Session hợp lệ, token đúng, Origin đúng | Thành công (2xx hoặc redirect đã định nghĩa) | Email thay đổi đúng một lần |
| NEG-01 | Thiếu CSRF token | Từ chối | Email và side effect không đổi |
| NEG-02 | Token ngẫu nhiên/sai | Từ chối | Không chấp nhận chỉ vì token có định dạng hợp lệ |
| NEG-03 | Token rỗng hoặc sai định dạng | Từ chối | Không phát sinh lỗi 500 |
| NEG-04 | Token được lấy từ session A nhưng gửi cùng session B | Từ chối | Token phải gắn với đúng session |
| NEG-05 | Token hết hạn hoặc session đã rotate | Từ chối nếu chính sách có expiry/rotation | Token cũ không còn hợp lệ |
| NEG-06 | Origin là website ngoài | Từ chối | Không đổi email |
| NEG-07 | Origin khác scheme, host hoặc port | Từ chối | So sánh origin đầy đủ, không chỉ hostname |
| NEG-08 | Origin là `null` | Từ chối với endpoint yêu cầu origin tin cậy | Không coi `null` là allowlist |
| NEG-09 | Origin thiếu và Referer cũng thiếu | Từ chối nếu chính sách yêu cầu ít nhất một nguồn hợp lệ | Không fallback sang allow-all |
| NEG-10 | Referer thuộc website ngoài | Từ chối | Không chấp nhận vì session cookie vẫn hợp lệ |
| NEG-11 | Origin và Referer mâu thuẫn | Từ chối theo chính sách nghiêm ngặt | Không chọn header thuận tiện hơn để cho qua |
| NEG-12 | `Sec-Fetch-Site: cross-site` | Từ chối request thay đổi trạng thái theo policy | Không tạo side effect |
| NEG-13 | `Sec-Fetch-Site: same-site` từ subdomain không tin cậy | Từ chối nếu origin/token không hợp lệ | Same-site không được đồng nhất với trusted origin |
| NEG-14 | Form POST không có token | Từ chối dù browser có gửi cookie | Kiểm chứng request thực sự tới server |
| NEG-15 | Form dùng `multipart/form-data` hoặc `text/plain` không có token | Từ chối nếu endpoint không hỗ trợ/không xác minh token | Không phụ thuộc riêng CORS preflight |
| NEG-16 | Request dùng method không được hỗ trợ | `405 Method Not Allowed` | Không thực hiện thao tác |
| NEG-17 | GET tới endpoint thay đổi trạng thái | Không được thay đổi trạng thái; tốt nhất không có thao tác state-changing qua GET | Bảo đảm GET an toàn, idempotent theo thiết kế |
| NEG-18 | Session không đăng nhập | `401` hoặc response auth đã định nghĩa | Phân biệt lỗi auth với lỗi CSRF |
| NEG-19 | User đăng nhập nhưng không có quyền | `403` theo policy authorization | CSRF token hợp lệ không cấp thêm quyền |
| NEG-20 | Token replay | Theo thiết kế token | Chỉ phải từ chối nếu token/nonce được quy định dùng một lần |

Một số trường hợp không nên gộp: token sai và user không có quyền là hai lý do từ chối khác nhau. Nếu middleware auth chạy trước CSRF middleware, response có thể là `401` thay vì `403`; điều đó không có nghĩa test CSRF thất bại nếu hợp đồng xử lý đã định nghĩa rõ và request không gây side effect.

### 5.2. Kiểm tra side effect sau mỗi lần từ chối

Với endpoint đổi email, kiểm tra ít nhất:

- email trong database vẫn là giá trị ban đầu;
- session vẫn còn hiệu lực nếu policy không chủ ý thu hồi;
- không gửi email xác nhận hoặc thông báo;
- không tạo audit event thành công;
- không enqueue job đổi email;
- không phát webhook hoặc gọi dịch vụ bên ngoài;
- không ghi token hoặc cookie vào log.

Với endpoint chuyển tiền, cần kiểm tra số dư cả hai tài khoản, ledger, giao dịch, queue, thông báo và idempotency record. Đừng chỉ kiểm tra một trường hiển thị trên UI.

Mẫu assertion tổng quát:

```javascript
const before = await readAccountState(accountId);
const queueBefore = await countPendingJobs("change-email");

const response = await sendRequest({
  method: "POST",
  path: "/account/email",
  cookie: sessionCookie,
  body: { email: "attacker@example.test" },
  csrfToken: undefined
});

const after = await readAccountState(accountId);
const queueAfter = await countPendingJobs("change-email");

assert.equal(response.status, 403);
assert.deepEqual(after, before);
assert.equal(queueAfter, queueBefore);
```

Các hàm `readAccountState`, `countPendingJobs` và `sendRequest` là helper của test suite, không phải API chuẩn của Node.js. Trong hệ thống thật, đọc state từ database/test fixture hoặc domain service, và chờ queue/eventual consistency hoàn tất trước khi kết luận không có side effect.

### 5.3. Kiểm tra lỗi không làm lộ thông tin

Negative response không nên chứa token đúng, session ID, stack trace, SQL, đường dẫn file hay bí mật cấu hình. Log phía server nên ghi lý do từ chối ở mức phân loại (ví dụ `csrf_token_missing` hoặc `origin_mismatch`), request ID và endpoint; không ghi giá trị token/cookie.

Test cũng cần xác minh không phản chiếu dữ liệu attacker vào HTML chưa encode. Trang lỗi có thể hiển thị thông báo ngắn, chung và có mã correlation để tra log nội bộ.

## 6. Thiết kế test theo nhiều tầng

### 6.1. Unit test middleware

Unit test kiểm tra từng nhánh của hàm xác minh token, origin hoặc Fetch Metadata với input đã kiểm soát. Các trường hợp nên có:

- token đúng/sai/thiếu và session binding;
- origin chính xác, khác scheme/host/port, `null` và thiếu;
- Fetch Metadata cross-site/same-site/thiếu;
- method an toàn so với method thay đổi trạng thái;
- token đã hết hạn nếu có expiry.

Unit test nhanh và dễ tái lập, nhưng không chứng minh browser thật gửi cookie, Origin hay Fetch Metadata như dự kiến.

### 6.2. Integration test với HTTP server và database thử nghiệm

Integration test gửi request HTTP tới ứng dụng đã khởi động cùng test database. Nó kiểm tra middleware được gắn đúng route, session được đọc đúng, token được so khớp, transaction bị rollback/không bắt đầu và side effect không phát sinh.

Nên tạo fixture riêng cho từng test, reset dữ liệu, dùng session mới và token mới. Đảm bảo negative test không vô tình đi qua nhánh 401 vì thiếu session khi mục tiêu là kiểm tra CSRF token.

### 6.3. Browser test với hai origin

Dùng browser automation hoặc thao tác DevTools để kiểm chứng:

- app origin và attacker origin thực sự khác nhau;
- browser gửi form POST;
- cookie có được đính kèm theo SameSite/context không;
- request có Origin và Fetch Metadata như mong đợi;
- server từ chối và state không đổi;
- response bị CORS giới hạn đọc vẫn không ngăn request đã gửi.

Đừng chỉ dùng một tab cùng origin để mô phỏng attacker. Cũng không được xem hai port khác nhau là hai site khác nhau: `http://localhost:3000` và `http://localhost:4000` là hai origin nhưng thường cùng site. Cặp này hữu ích để kiểm tra **cross-origin same-site**; muốn kiểm tra cross-site cần hai site khác nhau và môi trường DNS/HTTPS phù hợp.

### 6.4. Regression và CI

Trong CI, nên chia suite:

| Nhóm | Mục tiêu | Nhịp chạy |
| --- | --- | --- |
| Unit | Logic token/origin/Fetch Metadata | Mỗi commit |
| Integration | Middleware, database, side effect | Mỗi commit hoặc pull request |
| Browser | Form, cookie, SameSite, header browser thật | Pull request và lịch định kỳ |
| Regression security | Các payload/case từng gây lỗi | Mỗi thay đổi liên quan auth/session/API |

Khi test fail, lưu request ID, status, lý do từ chối, snapshot trạng thái trước/sau và browser version. Không lưu cookie phiên hoặc token thật vào artifact CI. Dùng secret test ngắn hạn và xóa dữ liệu fixture sau run.

## 7. Lab: kiểm chứng request giả mạo bằng hai origin local

Lab dùng Node.js built-in, không cần package bên ngoài. App chạy tại `http://localhost:3000`; trang attacker chạy tại `http://localhost:4000`. Hai URL là **khác origin vì port khác**, nhưng thông thường vẫn cùng site vì scheme/host giống nhau và site không tính port.

Đây là tình huống hữu ích để kiểm tra một subdomain/ứng dụng khác origin nhưng same-site về mặt cookie. Nó không mô phỏng đầy đủ cross-site. Mục tiêu là chứng minh form POST có thể gửi request và cookie phiên vẫn có thể được gửi; server phải xác minh token và origin.

Cookie lab dùng tên `lab_session` và không đặt `Secure` để chạy HTTP localhost đơn giản. **Không sao chép cấu hình này vào production.** Ứng dụng thật nên dùng HTTPS, cookie host-only như `__Host-session` với `Secure; HttpOnly; SameSite=Lax; Path=/` và quản lý session phía server.
### 7.1. Tạo server ứng dụng

Tạo file `csrf-lab.mjs`:

```javascript
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const APP_ORIGIN = "http://localhost:3000";
const sessions = new Map();

let balance = 1000;
const transfers = [];

function send(res, status, contentType, body, extraHeaders = {}) {
  res.writeHead(status, {
    "Content-Type": contentType,
    "Cache-Control": "no-store",
    ...extraHeaders
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", chunk => {
      data += chunk;
      if (data.length > 16384) {
        reject(new Error("Request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

function getCookie(req, name) {
  const raw = req.headers.cookie || "";
  for (const part of raw.split(";")) {
    const item = part.trim();
    const separator = item.indexOf("=");
    if (separator < 0) continue;
    if (item.slice(0, separator) === name) {
      return item.slice(separator + 1);
    }
  }
  return "";
}
const appPage = `<!doctype html>
<html lang="vi">
<meta charset="utf-8">
<title>CSRF negative test - App</title>
<h1>Ứng dụng ngân hàng thử nghiệm</h1>
<p>Session cookie được server thiết lập khi mở trang.</p>
<form action="/transfer" method="POST">
  <input type="hidden" name="csrf" value="__CSRF_TOKEN__">
  <label>Số tiền:
    <input name="amount" type="number" value="10" min="1">
  </label>
  <label>Người nhận:
    <input name="recipient" value="friend">
  </label>
  <button type="submit">Chuyển tiền hợp lệ</button>
</form>
<p><button id="refresh" type="button">Kiểm tra số dư</button></p>
<pre id="state"></pre>
<script>
  async function loadState() {
    const response = await fetch("/state", { cache: "no-store" });
    document.querySelector("#state").textContent = await response.text();
  }
  document.querySelector("#refresh").addEventListener("click", loadState);
  loadState();
</script>
</html>`;

const appServer = createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/") {
    let sessionId = getCookie(req, "lab_session");
    if (!sessions.has(sessionId)) {
      sessionId = randomBytes(32).toString("hex");
      sessions.set(sessionId, { csrfToken: randomBytes(32).toString("hex") });
    }
    const sessionData = sessions.get(sessionId);
    return send(res, 200, "text/html; charset=utf-8",
      appPage.replace("__CSRF_TOKEN__", sessionData.csrfToken), {
        "Set-Cookie": "lab_session=" + sessionId + "; Path=/; HttpOnly; SameSite=Lax"
      });
  }

  if (req.method === "GET" && req.url === "/state") {
    const session = getCookie(req, "lab_session");
    if (!sessions.has(session)) {
      return send(res, 401, "application/json; charset=utf-8", JSON.stringify({ error: "Session required" }));
    }
    return send(res, 200, "application/json; charset=utf-8",
      JSON.stringify({ balance, transfers }));
  }

  if (req.url === "/transfer" && req.method !== "POST") {
    return send(res, 405, "text/plain; charset=utf-8", "Method not allowed", {
      "Allow": "POST"
    });
  }
  if (req.method === "POST" && req.url === "/transfer") {
    const session = getCookie(req, "lab_session");
    const sessionData = sessions.get(session);
    if (!sessionData) {
      return send(res, 401, "text/plain; charset=utf-8", "Session required");
    }

    const contentType = (req.headers["content-type"] || "").split(";")[0].trim();
    if (contentType !== "application/x-www-form-urlencoded") {
      return send(res, 415, "text/plain; charset=utf-8", "Unsupported content type");
    }

    let rawBody;
    try {
      rawBody = await readBody(req);
    } catch {
      return send(res, 400, "text/plain; charset=utf-8", "Invalid request body");
    }

    const form = new URLSearchParams(rawBody);
    const submittedToken = form.get("csrf") || "";

    // Kiểm tra token trước để quan sát lỗi thiếu/sai token.
    if (submittedToken !== sessionData.csrfToken) {
      return send(res, 403, "text/plain; charset=utf-8", "CSRF token rejected");
    }

    // So khớp origin chính xác, gồm scheme, hostname và port.
    if (req.headers.origin !== APP_ORIGIN) {
      return send(res, 403, "text/plain; charset=utf-8", "Origin rejected");
    }

    // Fetch Metadata là lớp bổ sung. Same-site không thay thế origin/token.
    if (req.headers["sec-fetch-site"] === "cross-site") {
      return send(res, 403, "text/plain; charset=utf-8", "Cross-site request rejected");
    }

    const amount = Number(form.get("amount"));
    const recipient = form.get("recipient") || "";
    if (!Number.isFinite(amount) || amount <= 0 || amount > balance || !recipient) {
      return send(res, 400, "text/plain; charset=utf-8", "Invalid transfer");
    }

    balance -= amount;
    transfers.push({ amount, recipient });

    return send(res, 200, "text/plain; charset=utf-8",
      "Transfer accepted. Remaining balance: " + balance);
  }

  return send(res, 404, "text/plain; charset=utf-8", "Not found");
});
const attackerPage = `<!doctype html>
<html lang="vi">
<meta charset="utf-8">
<title>Attacker origin</title>
<h1>Trang origin khác</h1>
<p>Form này thử gửi POST tới ứng dụng ở localhost:3000.</p>
<form action="http://localhost:3000/transfer" method="POST">
  <input type="hidden" name="amount" value="100">
  <input type="hidden" name="recipient" value="attacker">
  <button type="submit">Thử request không có CSRF token</button>
</form>
</html>`;

const attackerServer = createServer((req, res) => {
  send(res, 200, "text/html; charset=utf-8", attackerPage);
});

appServer.listen(3000, () => console.log("App: http://localhost:3000"));
attackerServer.listen(4000, () => console.log("Attacker: http://localhost:4000"));
```

Chạy:

```bash
node csrf-lab.mjs
```

Mở hai tab: `http://localhost:3000` và `http://localhost:4000`. Đăng nhập giả lập được tạo tự động khi mở app; không có thông tin thật.

### 7.2. Chạy positive control

Ở tab ứng dụng, nhấn **Chuyển tiền hợp lệ**. Form cùng origin gửi cookie session và token hợp lệ. Kết quả mong đợi:

- response báo giao dịch được chấp nhận;
- số dư giảm từ 1000 xuống 990;
- danh sách transfers có một mục.

Nhấn **Kiểm tra số dư** để xem trạng thái server. Positive control xác nhận endpoint thực sự hoạt động trước khi thử request bị từ chối.

### 7.3. Gửi request giả mạo từ origin khác

Ở tab attacker, nhấn **Thử request không có CSRF token**. Form POST được gửi tới port 3000. Trong DevTools → Network, quan sát request:

- URL đích là `http://localhost:3000/transfer`;
- browser có thể đính kèm cookie `lab_session` vì hai URL localhost khác port nhưng cùng site và cookie không được giới hạn theo port;
- `Origin` của request là `http://localhost:4000`;
- request là cross-origin nhưng thường same-site;
- server trả `403` vì thiếu token.

Quay lại tab app, nhấn **Kiểm tra số dư**. Số dư vẫn là 990 và danh sách transfers không tăng. Đây là assertion quan trọng: server không thực hiện giao dịch dù request đã tới endpoint.

### 7.4. Tách riêng kiểm tra token và Origin

Để quan sát riêng lớp Origin, lấy giá trị token ngẫu nhiên hiện tại từ hidden input `csrf` trong DevTools → Elements của tab app (chỉ dùng trong lab). Trong trang attacker thêm một hidden field và dán giá trị vừa lấy:

```html
<input type="hidden" name="csrf" value="COPY_CURRENT_TOKEN_HERE">
```

Token được chép thủ công chỉ để thử nhánh Origin; trong tấn công thật, SOP ngăn attacker đọc DOM của trang app để lấy token. Gửi lại form. Server vượt qua kiểm tra token nhưng từ chối vì `Origin` là port 4000, không phải origin app port 3000.

Sau test, xóa field token vừa thêm. Không sử dụng token của lab ở bất kỳ hệ thống thật nào.
### 7.5. Thử content type và method

- Thử gửi POST với `enctype="text/plain"` hoặc `multipart/form-data`. Endpoint lab chỉ chấp nhận `application/x-www-form-urlencoded` nên trả `415` trước khi xử lý giao dịch.
- Gửi GET tới `/transfer`. Server trả `405` và không thay đổi số dư.
- Thử POST không có cookie session. Server trả `401`; đây là kiểm tra authentication, không phải bằng chứng duy nhất cho CSRF.
- Mở tab Network và xác nhận không có request nào tạo transfer khi response là 4xx.

**Lưu ý về content type:** server cần từ chối content type không được hỗ trợ, nhưng content-type validation không thay thế token/origin validation. Form mặc định dùng `application/x-www-form-urlencoded` vẫn là request có thể gửi cross-origin; chính sách CSRF phải bảo vệ trường hợp đó.

**Giới hạn của lab:** hai port trên localhost tạo cross-origin same-site, vì vậy không kiểm chứng được chính sách SameSite cho cross-site. Muốn kiểm tra cross-site thực sự, cần hai hostname/site khác nhau và HTTPS phù hợp, ví dụ hai tên miền thử nghiệm được ánh xạ trong môi trường local. Không dùng `localhost:3000` và `localhost:4000` để kết luận cookie cross-site sẽ hoạt động như thế nào.

Dừng hai server bằng Ctrl+C. Lab chỉ là ứng dụng demo trong máy local, không có tài khoản thật và không được expose ra mạng.

## 8. Những test dễ tạo cảm giác an toàn giả

### 8.1. Chỉ kiểm tra CORS preflight

Một test chỉ gửi `OPTIONS` và xác nhận server không trả `Access-Control-Allow-Origin` chưa chứng minh CSRF được chặn. HTML form có thể gửi request đơn giản mà không cần preflight; server vẫn phải xác minh token và nguồn request.

### 8.2. Chỉ kiểm tra JavaScript attacker không đọc được response

CORS có thể chặn attacker đọc response, trong khi server đã xử lý POST. Hãy kiểm tra Network/server log và trạng thái dữ liệu sau request, không chỉ xem Promise bị reject.

### 8.3. Chỉ test khi cookie không được gửi

Nếu cookie không được gửi do SameSite hoặc thiếu credentials, server có thể trả 401. Test đó không chứng minh CSRF token hoạt động. Để kiểm tra token, dùng một session hợp lệ và xác nhận request bị từ chối **vì token/Origin**.

### 8.4. Chỉ test cùng origin

Một form nội bộ hợp lệ không mô phỏng trang attacker. Cần browser context hoặc tab khác origin để quan sát cookie, Origin, Fetch Metadata và hành vi form thực tế.

### 8.5. Chỉ kiểm tra status code

Một endpoint có thể trả 403 nhưng vẫn enqueue job trước khi kiểm tra token. Assertion phải kiểm tra transaction, database, event, email, queue và webhook.

### 8.6. Chặn mọi request thiếu Fetch Metadata

API dành cho mobile app, command-line client hoặc browser cũ có thể không gửi Fetch Metadata. Chính sách phải phân loại client và dùng token/origin/auth phù hợp, không tự động coi thiếu header là cross-site trong mọi hệ thống.

### 8.7. Cho rằng same-site đồng nghĩa same-origin

Subdomain không đáng tin có thể cùng site với ứng dụng chính. Cần kiểm tra Origin chính xác và CSRF token; không chỉ dựa vào `Sec-Fetch-Site: same-site` hoặc SameSite cookie.

## 9. Checklist xây dựng CSRF negative test

Trước khi coi endpoint đã được kiểm thử, xác nhận:

1. **Chọn endpoint:** mọi thao tác thay đổi trạng thái dùng method phù hợp; GET/HEAD không tạo side effect.
2. **Positive control:** request có session, token và origin hợp lệ thành công đúng một lần.
3. **Token negative cases:** thiếu, sai, rỗng, sai session, hết hạn hoặc đã rotate đều bị từ chối theo thiết kế.
4. **Origin negative cases:** khác scheme/host/port, origin attacker, `null` và thiếu Origin/Referer được xử lý theo policy rõ ràng.
5. **Fetch Metadata:** cross-site bị chặn theo policy; same-site từ subdomain không tin cậy không tự được cấp quyền.
6. **Form content types:** kiểm thử `application/x-www-form-urlencoded`, `multipart/form-data` và `text/plain` nếu endpoint có thể nhận chúng.
7. **Cookie context:** kiểm tra cookie thực sự được gửi trong các ngữ cảnh same-site/cross-site, với browser mục tiêu.
8. **CORS:** không dựa vào preflight hoặc việc attacker không đọc được response.
9. **Side effects:** database, ledger, queue, email, webhook, audit và cache không đổi khi request bị từ chối.
10. **Authentication/authorization:** tách test CSRF khỏi 401 do thiếu session và 403 do user không có quyền.
11. **Response/logging:** không rò rỉ token/session; log chỉ ghi mã lý do và request ID.
12. **CI regression:** unit, integration và browser test có fixture độc lập; không lưu credential thật trong artifact.

### Gợi ý cấu trúc helper test

Đóng gói việc kiểm tra state trước/sau để mọi negative test đều xác minh side effect:

```javascript
async function expectCsrfRejected({
  request,
  readBusinessState,
  expectedStatus = 403
}) {
  const before = await readBusinessState();
  const response = await request();
  const after = await readBusinessState();

  assert.equal(response.status, expectedStatus);
  assert.deepEqual(after, before);
}
```

Helper này là mẫu minh họa. Với hệ thống có xử lý bất đồng bộ, cần chờ queue/event hoặc kiểm tra transaction boundary trước khi đọc trạng thái sau. Không dùng cùng fixture/session giữa các test song song nếu chúng có thể sửa cùng một bản ghi.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Nếu browser gửi form cross-origin nhưng attacker không đọc được response vì CORS, server có thể đã thực hiện thao tác chưa?  
**Đáp án:** Có. CORS kiểm soát quyền đọc response; server có thể đã xử lý request trước đó.

**Câu 2.** Negative test token thiếu nên kiểm tra điều gì ngoài 403?  
**Đáp án:** Trạng thái nghiệp vụ, database, queue, email, webhook và mọi side effect phải giữ nguyên.

**Câu 3.** Hai URL `http://localhost:3000` và `http://localhost:4000` có phải cross-site không?  
**Đáp án:** Chúng khác origin vì port khác, nhưng thông thường cùng site vì scheme/host giống nhau và site không tính port.

**Câu 4.** `Sec-Fetch-Site: same-site` có chứng minh request đến từ origin tin cậy không?  
**Đáp án:** Không. Subdomain không đáng tin có thể cùng site; cần origin allowlist và CSRF token.

**Câu 5.** Có nên từ chối token replay trong mọi triển khai không?  
**Đáp án:** Không. Chỉ từ chối nếu thiết kế dùng nonce một lần; synchronizer token có thể hợp lệ trong toàn bộ thời gian session.

**Câu 6.** Test trả 401 vì thiếu cookie có chứng minh token CSRF sai bị chặn không?  
**Đáp án:** Không. Cần session hợp lệ để đi tới nhánh kiểm tra CSRF.

**Câu 7.** Một endpoint chỉ chấp nhận JSON có thể bỏ CSRF token không?  
**Đáp án:** Không nên suy luận như vậy. Content type và preflight không phải ranh giới CSRF đầy đủ; cần token/origin hoặc cơ chế tương đương.

## 11. Ghi nhớ cốt lõi

CSRF negative test phải chứng minh request giả mạo **không tạo ra thay đổi**. Một request có thể được browser gửi đi dù SOP/CORS ngăn trang attacker đọc response. Vì vậy test phải bao gồm form POST thực tế, session cookie hợp lệ, token thiếu/sai, origin không được phép và assertion trạng thái trước/sau.

Kết hợp synchronizer token hoặc signed double-submit, kiểm tra Origin/Referer chính xác, Fetch Metadata và SameSite theo chính sách phù hợp. Mỗi lớp có giới hạn riêng; same-site không đồng nghĩa trusted-origin và CORS không thay thế CSRF defense. Luồng hợp lệ cần có positive control để chứng minh test không chỉ xanh vì endpoint đang hỏng.

### Tài liệu tham khảo

- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- [OWASP — CSRF Testing Guide](https://owasp.org/www-project-web-security-testing-guide/).
- [MDN — Cross-Site Request Forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Glossary/CSRF).
- [MDN — Fetch Metadata request headers](https://developer.mozilla.org/en-US/docs/Glossary/Fetch_metadata_request_header).
- [MDN — Set-Cookie: SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#samesitesamesite-value).
- [Fetch Standard (WHATWG)](https://fetch.spec.whatwg.org/).
