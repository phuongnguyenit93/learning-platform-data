# Chính sách cách ly cross-origin

> **Chương:** Cross-origin isolation  
> **Học phần:** Application Security — Browser Security (`SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`)

Một trang web có thể tải script, ảnh, font, iframe và worker từ nhiều origin. Browser dùng Same-Origin Policy (SOP), CORS và các cơ chế khác để giới hạn việc đọc dữ liệu giữa những origin đó. Tuy nhiên, một số tính năng mạnh như `SharedArrayBuffer` và bộ định thời có độ phân giải cao có thể làm tăng khả năng khai thác side channel nếu một trang bị xâm nhập.

**Cross-origin isolation** là trạng thái bảo mật mà browser chỉ cấp khi tài liệu đáp ứng các chính sách cách ly liên quan. Mô hình triển khai phổ biến kết hợp `Cross-Origin-Opener-Policy` (COOP) với `Cross-Origin-Embedder-Policy` (COEP), đồng thời yêu cầu môi trường an toàn và các điều kiện quyền phù hợp. Khi được bật thành công, JavaScript có thể kiểm tra `crossOriginIsolated`; một số API như `SharedArrayBuffer` chỉ khả dụng trong điều kiện này trên các browser hiện đại.

Cross-origin isolation không làm SOP biến mất và không cho phép trang đọc dữ liệu cross-origin tùy ý. Nó thay đổi cách browser cô lập browsing context và kiểm soát tài nguyên cross-origin được nhúng. Để triển khai đúng, cần hiểu vai trò riêng của COOP, COEP, Cross-Origin Resource Policy (CORP) và CORS.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích cross-origin isolation và các rủi ro mà nó giúp giảm thiểu.
2. Phân biệt SOP, site isolation và cross-origin isolation.
3. Mô tả vai trò của COOP và tác động tới `window.opener`/popup.
4. Mô tả vai trò của COEP `require-corp` và `credentialless`.
5. Phân biệt CORP với CORS và xác định khi nào tài nguyên cần opt-in.
6. Cấu hình response header để bật cross-origin isolation.
7. Kiểm tra `crossOriginIsolated` và khả năng dùng `SharedArrayBuffer`.
8. Xử lý tài nguyên CDN, font, ảnh, iframe và worker khi bật COEP.
9. Triển khai Report-Only, chẩn đoán violation và rollout theo giai đoạn.

## 2. Cross-origin isolation giải quyết vấn đề gì?

Browser phải cho phép trang tải tài nguyên từ nơi khác để web hoạt động: CDN, font provider, API, video, widget và thư viện bên thứ ba. Đồng thời, browser cần ngăn một origin đọc dữ liệu riêng của origin khác. SOP và CORS giải quyết một phần ranh giới này.

Một số cuộc tấn công side channel có thể suy luận dữ liệu thông qua thời gian, trạng thái cache, hành vi CPU hoặc các API chia sẻ bộ nhớ, ngay cả khi attacker không đọc trực tiếp DOM cross-origin. Những kỹ thuật như Spectre cho thấy việc chia sẻ process hoặc tài nguyên phần cứng có thể làm suy yếu giả định cô lập ở tầng JavaScript.

Cross-origin isolation yêu cầu browser thiết lập ranh giới chặt hơn giữa tài liệu top-level và các context liên quan, đồng thời yêu cầu tài nguyên cross-origin được nhúng phải thể hiện ý định cho phép. Điều này giúp browser cấp một số khả năng nhạy cảm với side channel trong môi trường có mức cô lập cao hơn.

Cross-origin isolation là biện pháp giảm thiểu. Nó không loại bỏ mọi side channel, không bảo vệ khỏi XSS trong chính origin, không thay thế phân quyền server-side và không bảo đảm mọi dữ liệu cross-origin đều không thể bị suy luận.

## 3. Phân biệt các khái niệm gần nhau

| Cơ chế | Ranh giới/chức năng chính | Điều nó không làm |
| --- | --- | --- |
| Same-Origin Policy (SOP) | Giới hạn script truy cập DOM và dữ liệu giữa các origin | Không ngăn mọi request hoặc mọi tài nguyên cross-origin được tải |
| CORS | Cho phép server công bố origin nào được đọc response cross-origin | Không phải cơ chế cô lập process hay chống clickjacking |
| Site isolation | Cách browser triển khai process isolation giữa các site | Không phải trạng thái web platform mà ứng dụng tự bật bằng một header duy nhất |
| COOP | Cô lập top-level browsing context khỏi một số context cross-origin và opener relationship | Không kiểm soát việc tải ảnh/font/script cross-origin |
| COEP | Yêu cầu tài nguyên cross-origin được nhúng opt-in theo CORP/CORS hoặc chính sách credentialless | Không tự cho JavaScript quyền đọc response cross-origin |
| CORP | Resource server khai báo ai được tải tài nguyên trong một số ngữ cảnh no-CORS | Không cấp quyền đọc response như CORS |
| Cross-origin isolation | Trạng thái kết hợp các chính sách để cấp một số API/capability nhạy cảm | Không thay thế SOP, CORS hoặc authorization |

## 4. Hai trụ cột: COOP và COEP

Mô hình thường dùng để bật cross-origin isolation cho trang top-level là:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Hai header giải quyết hai hướng khác nhau:

- **COOP** kiểm soát mối quan hệ giữa tài liệu top-level với các browsing context khác, đặc biệt là cửa sổ được mở bằng `window.open` và `window.opener`.
- **COEP** kiểm soát tài nguyên cross-origin mà tài liệu nhúng, yêu cầu tài nguyên opt-in qua CORP hoặc CORS tùy request mode; một lựa chọn khác là `credentialless`.

Chỉ có một trong hai header thường chưa đủ để đạt trạng thái cross-origin isolated. Header phải được gửi trên response thực tế của tài liệu; khai báo trong HTML meta tag không thay thế được response header cho các cơ chế này.

## 5. COOP — Cross-Origin-Opener-Policy

COOP kiểm soát việc một tài liệu top-level có chia sẻ browsing context group với cửa sổ khác origin hay không. Browsing context group là nhóm các cửa sổ có thể có quan hệ opener và một số tương tác giữa chúng.

Các giá trị thường gặp:

| Giá trị | Hành vi khái quát | Khi cân nhắc |
| --- | --- | --- |
| `unsafe-none` | Hành vi mặc định, cho phép một số quan hệ opener cross-origin | Tương thích ứng dụng cũ; không cung cấp mức cô lập COOP cần cho cross-origin isolation |
| `same-origin` | Tách tài liệu khỏi browsing context group không cùng origin theo quy tắc COOP | Lựa chọn phổ biến để bật cross-origin isolation |
| `same-origin-allow-popups` | Giữ một số quan hệ với popup có COOP tương thích | Có thể cần cho OAuth/payment popup, nhưng không thay thế cấu hình COOP cần thiết cho cross-origin isolation |
| `noopener-allow-popups` | Tách quan hệ opener theo chính sách được định nghĩa cho giá trị này | Chỉ dùng khi đã hiểu tương thích popup và browser mục tiêu |

Khi COOP `same-origin` tạo browsing context group mới, quan hệ `window.opener` giữa các tài liệu cross-origin có thể bị sever. Điều này giảm một số rủi ro như cross-window attacks và XS-Leaks dựa trên việc quan sát cửa sổ mở nhau.

Ví dụ response:

```http
Cross-Origin-Opener-Policy: same-origin
```

### 5.1 Tác động tới popup và luồng đăng nhập

Một ứng dụng có thể dùng popup cho OAuth, đăng nhập bên thứ ba, thanh toán hoặc hỗ trợ. COOP `same-origin` có thể làm mất mối quan hệ opener mà luồng cũ dựa vào, khiến callback không thể gọi `window.opener.postMessage(...)` như trước hoặc các kiểm tra trạng thái cửa sổ thay đổi.

Trước khi bật COOP, hãy kiểm kê:

- `window.open` và `window.opener`.
- Luồng OAuth/OIDC, SSO, thanh toán và xác minh danh tính.
- Popup callback và cơ chế đóng popup.
- Các SDK bên thứ ba cần giao tiếp với opener.
- Luồng điều hướng giữa các subdomain hoặc origin khác nhau.

Thiết kế lại callback bằng redirect hoặc một kênh giao tiếp được kiểm soát. Không hạ COOP toàn bộ ứng dụng chỉ để sửa một popup chưa được phân tích. Nếu một trang bắt buộc cần chính sách popup khác, có thể tách route hoặc ứng dụng con với threat model riêng; cần đánh giá tác động tới cross-origin isolation của từng context.

## 6. COEP — Cross-Origin-Embedder-Policy

COEP kiểm soát những tài nguyên cross-origin mà tài liệu hoặc worker nhúng. Giá trị thường gặp:

| Giá trị | Ý nghĩa |
| --- | --- |
| `unsafe-none` | Giá trị mặc định; không yêu cầu tài nguyên cross-origin opt-in theo COEP |
| `require-corp` | Tài nguyên cross-origin được tải ở chế độ no-CORS phải opt-in qua CORP; tài nguyên ở chế độ CORS phải vượt qua CORS check |
| `credentialless` | Cho phép một số request cross-origin no-CORS không có credential mà không cần CORP opt-in; request CORS vẫn phải đáp ứng CORS |

Ví dụ:

```http
Cross-Origin-Embedder-Policy: require-corp
```

Khi bật `require-corp`, tài nguyên cross-origin có thể bị chặn nếu server nguồn không công bố chính sách cho phép nhúng phù hợp. Điều này thường làm lộ các dependency trước đây tải được mà không có CORS/CORP.

`credentialless` có thể giảm công việc thay đổi ở một số tài nguyên công khai, nhưng request no-CORS cross-origin sẽ không mang credential. Nếu tài nguyên cần cookie hoặc xác thực, nó có thể không hoạt động như mong muốn. Không coi `credentialless` là cách tắt kiểm tra bảo mật hoặc là lựa chọn phù hợp cho mọi ứng dụng.

## 7. CORP — Cross-Origin-Resource-Policy

CORP là response header do **server sở hữu tài nguyên** gửi để khai báo những site/origin nào được phép nhúng tài nguyên trong một số request no-CORS.

Các giá trị:

| Giá trị | Ý nghĩa khái quát | Ví dụ sử dụng |
| --- | --- | --- |
| `same-origin` | Chỉ cho phép tài nguyên được nhúng từ cùng origin | API response hoặc tài nguyên riêng chỉ dành cho ứng dụng cùng origin |
| `same-site` | Cho phép cùng site theo quy tắc site của browser | Asset dùng giữa các subdomain cùng site đã được tin cậy |
| `cross-origin` | Cho phép nhúng từ origin khác | Ảnh/font/tài nguyên công khai chủ động cho phép dùng cross-origin |

Ví dụ response cho ảnh công khai:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Ví dụ response cho tài nguyên chỉ dùng nội bộ origin:

```http
Cross-Origin-Resource-Policy: same-origin
```

CORP là tín hiệu opt-in cho việc nhúng tài nguyên; nó không cấp cho JavaScript origin khác quyền đọc response. Nếu cần JavaScript đọc response cross-origin, server vẫn phải cấu hình CORS phù hợp.

Không đặt `Cross-Origin-Resource-Policy: cross-origin` trên dữ liệu riêng tư hoặc response chứa thông tin tài khoản chỉ để tránh lỗi COEP. Hãy phân loại tài nguyên và chọn giá trị theo mức độ công khai.

## 8. CORS và CORP khác nhau thế nào?

Hai cơ chế thường bị nhầm vì đều xuất hiện khi tải tài nguyên cross-origin:

| Tiêu chí | CORS | CORP |
| --- | --- | --- |
| Header chính | `Access-Control-Allow-Origin` | `Cross-Origin-Resource-Policy` |
| Ai cấu hình | Server trả response | Server trả tài nguyên |
| Mục đích | Cho phép origin khác đọc response trong CORS mode | Cho phép/chặn nhúng tài nguyên trong một số no-CORS context |
| Có làm SOP biến mất? | Không; chỉ mở quyền đọc theo policy | Không |
| Có thay thế nhau? | Không | Không |

Ví dụ CORS cho frontend cụ thể:

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Nếu request dùng credentials, server cần cấu hình origin cụ thể và `Access-Control-Allow-Credentials: true`; không thể kết hợp wildcard `*` với credentialed CORS response. CORS là hợp đồng giữa request mode và response header, còn CORP là tuyên bố về khả năng nhúng no-CORS.

## 9. COEP xử lý request theo mode như thế nào?

Để chẩn đoán lỗi, cần biết request được gửi ở mode nào:

| Cách tải tài nguyên | Request mode thường gặp | Điều cần đáp ứng khi COEP `require-corp` |
| --- | --- | --- |
| `<img src="...">` không có `crossorigin` | `no-cors` | Tài nguyên cross-origin cần CORP cho phép |
| `<img crossorigin="anonymous">` | `cors` | Response cần CORS header cho phép origin |
| `<script src="...">` classic không có `crossorigin` | Thường `no-cors` | Tài nguyên cross-origin cần CORP phù hợp |
| `<script type="module">` | CORS mode | Module và dependency cần CORS phù hợp |
| `fetch()` | Mặc định `cors` khi gọi URL cross-origin | Response cần CORS phù hợp |
| Font qua `@font-face` | CORS mode theo cơ chế tải font | Font server cần CORS phù hợp |
| Stylesheet `<link>` không có `crossorigin` | Có thể là `no-cors` | Tài nguyên cần CORP phù hợp |

Chi tiết request mode còn phụ thuộc thuộc tính `crossorigin`, loại tài nguyên và API. Khi một resource bị chặn, hãy kiểm tra Network để xem request mode, response header và redirect cuối cùng thay vì chỉ thêm host vào một danh sách chung.

## 10. `COEP: credentialless` và credential

`credentialless` là một lựa chọn COEP cho tài liệu muốn tải một số tài nguyên cross-origin no-CORS mà không yêu cầu resource server gửi CORP. Browser gửi request no-CORS cross-origin mà không kèm credential như cookie hoặc HTTP authentication theo hành vi credentialless được định nghĩa.

Điều này có nghĩa:

- Tài nguyên công khai có thể tải mà không cần thay đổi response server để thêm CORP trong một số trường hợp.
- Tài nguyên phụ thuộc session/cookie có thể trả về nội dung khác hoặc bị từ chối.
- Request ở CORS mode vẫn cần response CORS hợp lệ.
- `credentialless` không cho JavaScript quyền đọc dữ liệu cross-origin.
- Hỗ trợ browser và hành vi chi tiết cần được kiểm thử theo môi trường triển khai.

Không chọn `credentialless` chỉ vì `require-corp` đang chặn một tài nguyên nhạy cảm. Trước hết phải xác định tài nguyên có thực sự nên được nhúng hay không và liệu có cần credential hay không.

## 11. Bật cross-origin isolation

Với trang top-level, cấu hình khởi đầu phổ biến:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Hoặc, khi đã đánh giá trade-off của credentialless:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: credentialless
```

Các điều kiện khác cần lưu ý:

- Trang phải chạy trong secure context. Production nên dùng HTTPS; `localhost` được browser xem là môi trường đáng tin trong nhiều tình huống phát triển.
- Header phải nằm trên response của document top-level; COOP và COEP không được bật tương đương bằng meta tag.
- Tất cả tài nguyên cross-origin được nhúng phải đáp ứng chính sách COEP tương ứng.
- Worker và tài nguyên mà worker import cũng cần được kiểm tra theo policy áp dụng.
- Permissions Policy có thể giới hạn việc sử dụng capability cross-origin-isolated trong một số ngữ cảnh iframe.
- Browser phải hỗ trợ cơ chế và không có điều kiện khác làm mất trạng thái isolated.

COOP `same-origin` và COEP `require-corp`/`credentialless` là cấu hình thường gặp, nhưng không phải công thức copy-paste cho mọi ứng dụng. Hãy kiểm tra response thực tế và browser matrix.

## 12. Kiểm tra trạng thái bằng `crossOriginIsolated`

Sau khi triển khai, kiểm tra trong Console của trang:

```js
console.log(window.crossOriginIsolated);
```

Trong worker, có thể kiểm tra trên global scope tương ứng nếu browser hỗ trợ:

```js
console.log(self.crossOriginIsolated);
```

Giá trị `true` cho biết context hiện tại đạt trạng thái cross-origin isolated theo browser. Nếu là `false`, không nên suy đoán từ một header riêng lẻ; hãy kiểm tra COOP, COEP, secure context, Permissions Policy, redirect và tài nguyên bị chặn.

Kiểm tra API:

```js
const canUseSharedMemory =
  self.crossOriginIsolated === true &&
  typeof SharedArrayBuffer === "function";

if (canUseSharedMemory) {
  const buffer = new SharedArrayBuffer(1024);
  console.log("Shared memory available", buffer.byteLength);
} else {
  console.log("Use a non-shared-memory fallback");
}
```

Kiểm tra cả trạng thái isolation lẫn API thực tế. Không giả định `crossOriginIsolated === true` bảo đảm mọi browser/version đều triển khai cùng một tập API.

## 13. `SharedArrayBuffer`, Atomics và worker

`SharedArrayBuffer` cho phép nhiều agent như main thread và worker cùng truy cập một vùng nhớ. `Atomics` cung cấp thao tác đồng bộ trên shared memory. Các khả năng này hữu ích cho:

- Tính toán song song trong Web Worker.
- Xử lý dữ liệu lớn với ít bước sao chép hơn.
- Engine game, audio/video, mô phỏng và thư viện WebAssembly đa luồng.
- Một số ứng dụng khoa học hoặc xử lý ảnh cần hiệu năng cao.

Ví dụ tạo shared buffer và chuyển cho worker:

```js
if (crossOriginIsolated && typeof SharedArrayBuffer !== "undefined") {
  const sharedBuffer = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
  const sharedValue = new Int32Array(sharedBuffer);

  const worker = new Worker("/workers/counter.js", { type: "module" });
  worker.postMessage({ buffer: sharedBuffer });
}
```

Worker có thể nhận reference tới shared memory theo structured clone và dùng `Atomics` để đọc/ghi có đồng bộ. `SharedArrayBuffer` không phải cơ chế truyền dữ liệu bí mật an toàn; code trong cùng agent cluster được cấp reference có thể truy cập vùng nhớ đó. Chỉ chia sẻ vùng nhớ với worker mà ứng dụng kiểm soát.

Không gọi `Atomics.wait()` trên main thread trong ứng dụng UI; thao tác chờ đồng bộ có thể bị cấm hoặc làm treo giao diện. Thiết kế worker và đồng bộ hóa theo API phù hợp.

## 14. Worker và tài nguyên được import

Khi bật COEP, không chỉ document chính cần được kiểm tra. Dedicated worker, shared worker, module worker và các script/resource mà chúng tải có thể chịu yêu cầu policy liên quan. Một worker entrypoint hoặc dependency cross-origin không tương thích có thể làm worker khởi tạo thất bại hoặc không đạt trạng thái mong muốn.

Checklist worker:

- Worker script được phục vụ từ origin phù hợp và response có header cần thiết.
- Module import, WASM, script phụ và các tài nguyên fetch được kiểm tra CORS/CORP.
- Không giả định worker kế thừa mọi quyền từ document mà không cần kiểm tra.
- Worker chỉ nhận shared memory từ code tin cậy và validate message như mọi kênh khác.
- Có fallback khi browser không hỗ trợ shared memory hoặc isolation.

Service Worker có lifecycle và phạm vi riêng; đừng suy luận rằng mọi quy tắc của Dedicated Worker áp dụng nguyên xi cho Service Worker. Hãy kiểm thử loại worker mà ứng dụng thật sự dùng.

## 15. Iframe và Permissions Policy

Một trang cross-origin isolated có thể nhúng iframe, nhưng việc iframe có được sử dụng capability liên quan tới cross-origin isolation hay không còn phụ thuộc chính sách của ancestor, Permissions Policy và hỗ trợ browser.

Feature policy liên quan có thể được giới hạn bằng Permissions Policy `cross-origin-isolated`; khi cần delegate cho iframe, phải cấu hình allowlist phù hợp và kiểm tra `allow` trên iframe. Ví dụ định hướng:

```http
Permissions-Policy: cross-origin-isolated=(self "https://worker-ui.example.net")
```

```html
<iframe
  src="https://worker-ui.example.net/tool"
  allow="cross-origin-isolated"
  title="Công cụ xử lý dữ liệu"></iframe>
```

Đây là cấu hình cần xác minh theo browser và kiến trúc cụ thể; không phải mọi iframe đều có thể trở thành cross-origin isolated chỉ bằng cách thêm `allow`. COOP áp dụng chủ yếu cho top-level browsing context, trong khi iframe có các điều kiện ancestor/policy riêng.

Nếu widget không cần SharedArrayBuffer hoặc API nhạy cảm, đừng delegate capability này. Giữ quyền tối thiểu và tránh đưa dữ liệu nhạy cảm vào frame không được kiểm soát.

## 16. Ảnh hưởng tới popup, OAuth và thanh toán

COOP `same-origin` có thể làm thay đổi quan hệ opener giữa trang và popup. Những luồng cũ dựa vào `window.opener` có thể lỗi dù CORS/COEP của tài nguyên đã được cấu hình đúng.

Trước khi phát hành, thử các luồng:

- OAuth/OIDC redirect và popup callback.
- SSO giữa các origin.
- Payment provider mở cửa sổ riêng.
- Widget hỗ trợ dùng `window.opener` hoặc `postMessage`.
- Luồng đóng popup và cập nhật trạng thái parent.

Ưu tiên giao thức redirect có state/nonce được xác minh server-side hoặc callback trên origin được kiểm soát. Nếu cần `postMessage`, dùng exact origin, kiểm tra source và schema; không gửi access token hoặc refresh token qua message chỉ để khắc phục COOP.

Một trang con có thể được tách thành route/app riêng với COOP phù hợp cho popup. Tuy nhiên, route đó có thể không còn cross-origin isolated; không giả định toàn bộ site giữ cùng trạng thái sau khi đổi COOP.

## 17. Các header liên quan và vai trò riêng

| Header | Nơi thường cấu hình | Mục đích |
| --- | --- | --- |
| `Cross-Origin-Opener-Policy` | Response document top-level | Cô lập browsing context/opener relationship |
| `Cross-Origin-Embedder-Policy` | Response document và context worker phù hợp | Yêu cầu tài nguyên cross-origin opt-in |
| `Cross-Origin-Resource-Policy` | Response tài nguyên được tải | Cho phép/chặn nhúng no-CORS theo origin/site |
| `Access-Control-Allow-Origin` | Response API/resource CORS | Cho phép origin cụ thể đọc response |
| `Permissions-Policy` | Response document | Giới hạn/delegate một số browser capability |
| `Origin-Agent-Cluster` | Response document | Yêu cầu agent cluster theo origin trong các browser hỗ trợ; không thay COOP/COEP |

`Origin-Agent-Cluster: ?1` có thể tăng mức cô lập agent cluster theo origin, nhưng không tự bật cross-origin isolation và không thay thế cặp COOP/COEP. Site isolation cũng là một khái niệm triển khai ở browser, không phải tên khác của header này.

## 18. Reporting và chế độ Report-Only

Trước khi enforcement, có thể dùng các header Report-Only tương ứng để quan sát tác động:

```http
Cross-Origin-Opener-Policy-Report-Only: same-origin; report-to coop-endpoint
Cross-Origin-Embedder-Policy-Report-Only: require-corp; report-to coep-endpoint
Reporting-Endpoints: coop-endpoint="https://reports.example.com/coop", coep-endpoint="https://reports.example.com/coep"
```

Report-Only giúp phát hiện một số quan hệ opener hoặc tài nguyên cross-origin không đáp ứng policy mà chưa cưỡng chế chặn. Nó không làm `crossOriginIsolated` trở thành `true`; cần header enforcement thực sự và các điều kiện còn lại.

Endpoint reporting phải:

- Giới hạn kích thước và tần suất request.
- Không coi URL hoặc field trong report là dữ liệu đáng tin.
- Không lưu cookie, token hoặc thông tin cá nhân không cần thiết.
- Giới hạn quyền truy cập, thời gian lưu và khả năng tra cứu.
- Phân biệt violation từ ứng dụng, browser extension, redirect và dependency bên thứ ba.

Report-Only không thay thế test trên browser thật. Một số hành vi có thể khác giữa browser/version; hãy kiểm tra response header và Network log.

## 19. Lộ trình triển khai

Không nên bật COOP/COEP ở production mà chưa kiểm kê tài nguyên và luồng popup. Một lộ trình thực tế:

1. **Inventory:** liệt kê script, stylesheet, ảnh, font, media, iframe, worker, WASM và API cross-origin.
2. **Phân loại request:** xác định request mode (`cors` hay `no-cors`), credential và chủ sở hữu server tài nguyên.
3. **Kiểm tra popup:** tìm `window.open`, `window.opener`, OAuth, payment và callback.
4. **Chọn policy:** quyết định COEP `require-corp` hay `credentialless` dựa trên nhu cầu credential và khả năng opt-in của tài nguyên.
5. **Cấu hình resource server:** thêm CORP cho tài nguyên no-CORS được phép nhúng; cấu hình CORS cho resource/API cần CORS mode.
6. **Report-Only:** triển khai COOP/COEP Report-Only và thu thập violation trong staging.
7. **Sửa dependency:** self-host, thay CDN, thêm header đúng ở resource owner hoặc bỏ tài nguyên không cần.
8. **Enforcement:** bật COOP `same-origin` và COEP đã chọn trên response phù hợp.
9. **Verify:** kiểm tra `crossOriginIsolated`, SharedArrayBuffer, worker, iframe, popup và toàn bộ luồng chính.
10. **Monitor:** theo dõi report, lỗi tải tài nguyên và thay đổi từ dependency/CDN sau release.

Không thêm CORP `cross-origin` cho mọi tài nguyên để làm sạch violation. Hãy xác định tài nguyên có thực sự công khai và cần được nhúng cross-origin hay không.

## 20. Chẩn đoán lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `crossOriginIsolated` là `false` | Thiếu COOP/COEP enforcement, không phải secure context hoặc policy bị giới hạn | Kiểm tra response document, secure context và Permissions Policy |
| Ảnh/script/stylesheet bị chặn | COEP `require-corp`, resource no-CORS thiếu CORP hoặc CORS mode thiếu ACAO | Xác định request mode rồi cấu hình CORP/CORS đúng ở resource server |
| Font không tải | Font request cần CORS nhưng server không cho phép origin | Cấu hình `Access-Control-Allow-Origin` phù hợp |
| API fetch lỗi CORS | API thiếu CORS response header hoặc credentials config sai | Sửa CORS; không thêm CORP để thay thế |
| Widget cross-origin không hiển thị | COEP/iframe opt-in hoặc frame policy không phù hợp | Kiểm tra response iframe, CORP/CORS và policy ancestor |
| Popup OAuth không cập nhật parent | COOP làm sever opener relationship | Thiết kế lại callback/redirect hoặc đánh giá policy route riêng |
| Worker không khởi tạo | Worker entrypoint/import không tương thích policy hoặc URL | Kiểm tra worker response, import và COEP/CORS/CORP |
| `SharedArrayBuffer` không có | Browser support hoặc cross-origin isolation chưa đạt | Kiểm tra API, `crossOriginIsolated`, secure context và fallback |
| Tài nguyên chỉ tải khi có cookie | COEP `credentialless` bỏ credential khỏi no-CORS request | Chọn `require-corp`/CORS phù hợp hoặc thiết kế resource công khai |
| Report-Only có violation nhưng trang vẫn tải | Report-Only chỉ quan sát | Sửa resource rồi chuyển policy sang enforcement |

Khi debug, ghi lại URL document, COOP, COEP, response resource, request mode, CORP/CORS header, redirect chain, browser/version và trạng thái `crossOriginIsolated`. Đừng sửa bằng cách mở wildcard hoặc cho phép mọi cross-origin resource.

## 21. Ví dụ cấu hình response

### 21.1 Trang ứng dụng và asset cùng origin

```http
HTTP/1.1 200 OK
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
```

Các asset cùng origin thường tương thích với policy. Tài nguyên cross-origin vẫn cần opt-in.

### 21.2 Ảnh công khai trên CDN

Response ảnh từ CDN có thể gửi:

```http
Cross-Origin-Resource-Policy: cross-origin
```

Nếu ứng dụng chuyển ảnh sang CORS mode bằng `crossorigin="anonymous"`, CDN cần trả CORS header phù hợp. Chọn một cơ chế theo request mode thực tế.

### 21.3 API cho frontend cụ thể

```http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
```

Nếu dùng credentials, cấu hình credentialed CORS với origin cụ thể và `Access-Control-Allow-Credentials: true`; không dùng wildcard `*` cho response credentialed.

Các ví dụ chỉ là phần header liên quan cross-origin isolation. Ứng dụng thực tế còn cần các CSP directive, cache policy, cookie attribute, authentication và authorization theo threat model.

## 22. Thực hành kiểm chứng trong môi trường lab

Chỉ dùng domain local/test và tài nguyên do bạn quản lý. Không thay header của website bên ngoài hoặc thử nghiệm trên tài khoản thật.

### Bài thử A — Quan sát trạng thái isolation

1. Chạy trang HTTPS local hoặc `localhost`.
2. Mở Console và đọc `window.crossOriginIsolated`.
3. Thêm COOP `same-origin` và COEP `require-corp` vào response document.
4. Tải lại và kiểm tra lại trạng thái.

**Kỳ vọng:** Khi browser hỗ trợ, response có đủ header enforcement và các điều kiện cần thiết, trạng thái có thể chuyển thành `true`. Chỉ thêm một header thường chưa đủ.

### Bài thử B — Thử `SharedArrayBuffer`

Chạy:

```js
console.log({
  isolated: crossOriginIsolated,
  sharedArrayBuffer: typeof SharedArrayBuffer,
});
```

Nếu API khả dụng, tạo buffer nhỏ và chuyển cho worker lab. Nếu không, ghi nhận browser/version, header và Console violation; không thay policy bằng wildcard để ép chạy.

### Bài thử C — COEP `require-corp` với ảnh cross-origin

Tạo một ảnh public trên origin thứ hai do bạn quản lý. Tải ảnh bằng `<img>` không có `crossorigin`, trước tiên không gửi CORP, sau đó thêm `Cross-Origin-Resource-Policy: cross-origin` ở response ảnh. Thử thêm biến thể `<img crossorigin="anonymous">` cùng CORS header.

**Kỳ vọng:** Request no-CORS cần CORP opt-in khi `require-corp`; biến thể CORS cần response CORS hợp lệ. CORP không cấp quyền đọc pixel/response qua JavaScript như CORS.

### Bài thử D — COEP `credentialless`

Tạo resource no-CORS lab trả nội dung công khai và ghi log server xem request có mang cookie lab hay không. Chạy trang với COEP `credentialless`, so sánh với chế độ không credentialless.

**Kỳ vọng:** Request cross-origin no-CORS theo credentialless không gửi credential; resource cần session có thể trả nội dung khác hoặc không hoạt động. Không dùng cookie thật trong lab.

### Bài thử E — COOP và popup

Tạo trang top-level lab mở một popup ở origin khác. Quan sát `window.opener` ở popup và khả năng parent nhận callback trước/sau khi áp dụng COOP `same-origin`.

**Kỳ vọng:** COOP có thể sever opener relationship khi browsing context group bị tách. Thiết kế callback không nên phụ thuộc vào quan hệ opener cross-origin không được bảo đảm.

## 23. Những hiểu nhầm thường gặp

| Nhận định sai | Hiểu đúng |
| --- | --- |
| “COOP một mình bật cross-origin isolation.” | Cần các điều kiện COEP và môi trường phù hợp; kiểm tra `crossOriginIsolated`. |
| “COEP cho phép đọc mọi response cross-origin.” | COEP kiểm soát tài nguyên được nhúng; CORS vẫn quyết định quyền đọc response. |
| “CORP và CORS là cùng một header khác tên.” | CORP opt-in cho một số no-CORS embedding; CORS cấp quyền đọc trong CORS mode. |
| “Thêm CORP cross-origin cho mọi tài nguyên là an toàn.” | Chỉ dùng với tài nguyên thực sự công khai và cần được nhúng rộng rãi. |
| “Credentialless tương đương bỏ qua COEP.” | Nó thay đổi cách gửi credential cho một số no-CORS request; không bỏ CORS check. |
| “Cross-origin isolated có thể đọc DOM cross-origin.” | SOP vẫn áp dụng; isolation không cấp quyền DOM cross-origin. |
| “Site isolation và cross-origin isolation là một.” | Một bên là triển khai process của browser, bên kia là trạng thái web platform/policy. |
| “Origin-Agent-Cluster thay thế COOP/COEP.” | Nó là cơ chế khác, không tự bật cross-origin isolation. |
| “Bật COOP không ảnh hưởng popup.” | Opener relationship và luồng OAuth/payment có thể thay đổi. |
| “Report-Only đã bật isolation.” | Report-Only chỉ báo cáo; cần enforcement để đạt trạng thái isolated. |

## 24. Checklist review cross-origin isolation

- [ ] Có lý do sản phẩm rõ ràng để cần SharedArrayBuffer hoặc capability yêu cầu cross-origin isolation.
- [ ] Trang chạy trong secure context và browser mục tiêu hỗ trợ.
- [ ] COOP `same-origin` được gửi trên response top-level phù hợp.
- [ ] COEP `require-corp` hoặc `credentialless` được chọn sau khi đánh giá credential/resource.
- [ ] Đã kiểm kê script, style, ảnh, font, media, iframe, worker, WASM và API cross-origin.
- [ ] Mỗi tài nguyên no-CORS có CORP phù hợp hoặc được xử lý theo credentialless.
- [ ] Mỗi tài nguyên CORS mode có ACAO/CORS response đúng.
- [ ] Không dùng CORP `cross-origin` cho dữ liệu riêng tư.
- [ ] Đã kiểm thử worker và dependency được import.
- [ ] Đã kiểm thử iframe và Permissions Policy nếu cần delegate capability.
- [ ] Đã kiểm thử popup, OAuth, SSO và payment sau COOP.
- [ ] `crossOriginIsolated` được kiểm tra runtime; có fallback khi false/API không khả dụng.
- [ ] Report-Only được dùng để phát hiện vấn đề trước enforcement.
- [ ] HTML, header và CDN/proxy behavior được kiểm tra trên response cuối.
- [ ] Có browser matrix, regression test và giám sát sau phát hành.

## 25. Câu hỏi tự kiểm tra

1. Cross-origin isolation là trạng thái gì và giúp giảm loại rủi ro nào?
2. COOP kiểm soát browsing context và `window.opener` như thế nào?
3. COEP `require-corp` xử lý tài nguyên no-CORS và CORS mode ra sao?
4. `credentialless` thay đổi credential của request nào và giới hạn của nó là gì?
5. CORP khác CORS ở mục đích và quyền đọc response như thế nào?
6. Vì sao `Cross-Origin-Resource-Policy: cross-origin` không nên được thêm đại trà?
7. Cần những điều kiện nào để `crossOriginIsolated` có thể là `true`?
8. Vì sao COOP có thể làm hỏng luồng popup OAuth hoặc thanh toán?
9. Worker và iframe cần được kiểm tra ra sao khi bật COEP?
10. Vì sao site isolation và `Origin-Agent-Cluster` không thay thế COOP/COEP?

## 26. Ghi nhớ

Cross-origin isolation kết hợp chính sách cô lập opener và kiểm soát tài nguyên nhúng. COOP `same-origin` tách browsing context top-level khỏi một số quan hệ cross-origin; COEP `require-corp` yêu cầu tài nguyên no-CORS opt-in bằng CORP, còn tài nguyên CORS mode phải đáp ứng CORS. `credentialless` là lựa chọn khác cho một số request no-CORS bằng cách không gửi credential, nhưng không bỏ qua CORS.

Hãy kiểm kê tài nguyên, worker, iframe và popup trước khi triển khai; cấu hình CORP/CORS ở đúng resource server; dùng Report-Only để quan sát; sau đó bật enforcement và xác minh `crossOriginIsolated` cùng API cần thiết. **Cross-origin isolation tăng mức cô lập của browser và mở khóa một số capability nhạy cảm; SOP, CORS, authorization và phòng vệ XSS vẫn giữ nguyên vai trò riêng.**
