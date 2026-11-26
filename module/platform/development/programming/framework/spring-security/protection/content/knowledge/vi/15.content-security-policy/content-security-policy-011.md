# Giới hạn của allowlist rộng cùng unsafe-inline, unsafe-eval

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Vì sao một CSP “có header” vẫn có thể bảo vệ rất yếu?

**Content Security Policy (CSP)** là lớp phòng vệ do trình duyệt thực thi để hạn chế những nguồn tài nguyên và kiểu thực thi mã mà một tài liệu được phép sử dụng. Trong Spring Security, ứng dụng cung cấp chuỗi policy rồi gửi nó qua header `Content-Security-Policy`; Spring không tự suy ra domain nào đáng tin hoặc loại mã nào nên được phép.

Xét chính sách:

~~~http
Content-Security-Policy: default-src * https: data: blob:; script-src * https: 'unsafe-inline' 'unsafe-eval'; style-src * 'unsafe-inline'
~~~

Mặc dù response **có** header CSP, chính sách trên mở rất nhiều đường tải tài nguyên và thực thi JavaScript. Hai vấn đề lớn:

1. **Allowlist quá rộng:** `*`, `https:` hoặc những tập host khó kiểm soát cho phép nhiều nguồn ngoài mong đợi.
2. **Nới quyền thực thi:** `'unsafe-inline'` và `'unsafe-eval'` loại bỏ những hạn chế quan trọng của CSP đối với mã JavaScript.

Một chính sách yếu không có nghĩa CSP vô dụng: vẫn có thể còn một số giới hạn tùy directive, trình duyệt và nguồn cụ thể. Nhưng việc chỉ thấy header trong DevTools **không chứng minh** ứng dụng đã được bảo vệ hiệu quả trước XSS hoặc truyền dữ liệu ngoài ý muốn.

### Mục tiêu bài học

Sau bài này, bạn có thể:

- Đánh giá sự khác biệt giữa allowlist cụ thể và nguồn rộng như `*`, `https:`, wildcard subdomain.
- Giải thích chính xác `'unsafe-inline'`, `'unsafe-eval'` và tác động của chúng lên script, handler, `eval` và style.
- Nhận ra giới hạn của allowlist host dù nguồn nằm trong `'self'` hoặc một CDN đã phê duyệt.
- Chọn hướng cải thiện bằng file script đáng tin, nonce/hash, `'strict-dynamic'` có cân nhắc và các lớp phòng vệ hỗ trợ.
- Viết, thử và triển khai CSP trong Spring Security Servlet/WebFlux, phân biệt lỗi CSP với CORS/CSRF và lỗi browser khác.

## 2. Đặt CSP trong mô hình đe dọa thực tế

Một trang có thể bị tấn công khi dữ liệu người dùng bị render thành HTML không an toàn, khi JavaScript đáng tin xử lý chuỗi không an toàn hoặc khi một nguồn script được cấp phép bị thay đổi.

~~~mermaid
flowchart TD
    A[Trang nhận nội dung hoặc code từ nhiều nguồn] --> B{Nguồn gây rủi ro}
    B --> C[HTML injection]
    B --> D[DOM XSS trong script được phép]
    B --> E[Script từ CDN hoặc cùng origin bị kiểm soát sai]
    C --> F[Script inline, handler hoặc tài nguyên ngoài]
    D --> G[Code chạy trong ngữ cảnh ứng dụng]
    E --> G
    F --> H[CSP có thể chặn một phần đường thực thi]
    G --> I[CSP không tự xác nhận ý định của code đã được phép]
    H --> J[Escape, sanitize, quyền hạn, CSP chặt, kiểm soát nguồn]
    I --> J
~~~

**CSP là phòng vệ bổ sung, không phải trình lọc HTML hoặc bộ đánh giá độ tin cậy của mã.** Nó đặc biệt hữu ích khi một lỗi injection chỉ cho kẻ tấn công chèn markup hoặc một script không được cấp phép. Tuy nhiên, nếu ứng dụng đã cho một script độc hại chạy từ nguồn hợp lệ, CSP không thể biến script ấy thành an toàn.

Đối với bài học này, xem xét ba câu hỏi độc lập:

| Câu hỏi | Cơ chế CSP liên quan | Vấn đề khi cấu hình yếu |
|---|---|---|
| Script/tài nguyên được tải **từ đâu**? | `script-src`, `style-src`, `img-src`, `connect-src`... | Allowlist rộng cho quá nhiều nguồn |
| Mã **nội tuyến** có được thực thi không? | `script-src`, `script-src-elem`, `script-src-attr`; các directive style tương ứng | `'unsafe-inline'` mở nhiều đường thực thi |
| JavaScript có được **biên dịch chuỗi thành code** không? | Quy tắc về `'unsafe-eval'` trong `script-src` hoặc fallback | `'unsafe-eval'` mở lại các API đánh giá chuỗi |

Không nên sửa lỗi thuộc nhóm này bằng cách nới rộng nhóm khác. Ví dụ, thêm nguồn ảnh vào `img-src` không cho phép `eval`; bật `'unsafe-eval'` không tự cấp phép tải JavaScript ngoài từ host bất kỳ.

## 3. Allowlist: chính xác đến đâu thì có ý nghĩa?

Source list là tập biểu thức nguồn được phép. Có thể gặp:

~~~http
script-src 'self'
script-src https://static.example.net
script-src https:
script-src *
script-src https://*.example.net
~~~

Các dòng trên minh họa **năm giá trị directive khác nhau**, không phải năm policy cần gắn cùng lúc.

| Source expression | Ý nghĩa khái quát | Rủi ro hoặc hạn chế |
|---|---|---|
| `'none'` | Không cho nguồn nào ở directive đó | Chặt, nhưng có thể làm hỏng tính năng nếu chưa kiểm kê |
| `'self'` | Cùng origin với tài liệu | Vẫn tin mọi đường phục vụ script phù hợp trên origin ấy |
| `https://static.example.net` | Nguồn HTTPS cụ thể | Phụ thuộc việc host đó được kiểm soát an toàn |
| `https:` | Nhiều nguồn HTTPS | Quá rộng nếu chỉ cần 1–2 CDN |
| `*` | Nhiều host theo quy tắc matching CSP | Quá rộng; không mặc nhiên bao gồm mọi scheme như `data:` hay `blob:` |
| `https://*.example.net` | Nhiều subdomain của domain chỉ định | Subdomain mới hoặc bị chiếm quyền có thể trở thành nguồn được phép |

`'self'` là **cùng origin**, không có nghĩa mọi subdomain; scheme, host và port cũng quan trọng. Wildcard subdomain như `*.example.net` không nên được hiểu mặc nhiên gồm chính domain gốc `example.net`. Khi cần cả host gốc và subdomain, phải hiểu cú pháp khớp nguồn và khai báo đúng theo yêu cầu.

### Ví dụ: hai allowlist có vẻ giống nhưng khác rủi ro

Giả sử ứng dụng chỉ cần một script từ CDN:

~~~html
<script src="https://static.example.net/app-v2.js" defer></script>
~~~

Chính sách hẹp:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' https://static.example.net; object-src 'none'; base-uri 'self'
~~~

Chính sách rộng:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' https:; object-src 'none'; base-uri 'self'
~~~

Ở chính sách thứ hai, nhiều host HTTPS khác có thể trở thành nơi tải script hợp lệ. **HTTPS chỉ bảo vệ đường truyền đến host, không xác nhận tất cả host HTTPS đều đáng tin.**

Nếu nội dung bị chèn tạo thẻ script với URL HTTPS do bên ngoài quản lý, CSP thứ hai có thể không ngăn việc tải script ấy. Chính sách hẹp giảm bề mặt đó, dù vẫn phụ thuộc nguồn `static.example.net` và script cùng origin có an toàn không.

### Không nên sử dụng default-src rộng như đường tắt

~~~http
Content-Security-Policy: default-src https:
~~~

Khi một fetch directive cụ thể vắng mặt, nó có thể fallback về `default-src`. Vì thế một `default-src` quá rộng có thể vô tình ảnh hưởng nhiều loại tài nguyên: script, style, ảnh, font, kết nối và các nhóm có fallback phù hợp.

Đổi lại:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.net; font-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self'
~~~

Policy mới bắt đầu từ mặc định đóng, rồi mở đúng nhóm. Đây là ví dụ khởi đầu, **chưa phù hợp mọi ứng dụng**: những trang dùng iframe, worker, video, CDN khác hoặc inline code hợp lệ phải được đánh giá và cấu hình tiếp.

## 4. Vì sao allowlist chỉ gồm host được tin vẫn có thể bị vượt qua?

Một host có trong `script-src` là một **nguồn được CSP cho phép**; điều đó không đồng nghĩa mọi JavaScript mà host có thể trả về đều đáng tin.

### 4.1. Script từ cùng origin

~~~http
Content-Security-Policy: script-src 'self'
~~~

Nếu ứng dụng cho người dùng tải tệp lên và tệp có thể được phục vụ dưới cùng origin ở dạng có thể thực thi như JavaScript, CSP `'self'` có thể vẫn cho phép browser tải tệp ấy qua thẻ script. Tương tự, một endpoint cũ có thể trả JavaScript được hình thành từ dữ liệu không được kiểm soát tốt.

Hướng bảo vệ:

- Tách nội dung người dùng upload sang một origin độc lập, không chia sẻ quyền chạy script với trang ứng dụng chính.
- Kiểm soát content type, `Content-Disposition`, header chống sniffing phù hợp và quy tắc phục vụ file.
- Không cho endpoint nội dung không đáng tin trả JavaScript có thể được nhúng cùng origin.
- Escape/sanitize dữ liệu đúng ngữ cảnh, tránh DOM XSS ngay trong mã của ứng dụng.

### 4.2. CDN và dịch vụ bên thứ ba

~~~http
Content-Security-Policy: script-src 'self' https://cdn.example.net
~~~

Chính sách này cấp quyền cho script từ CDN. Nếu CDN bị chiếm quyền, đường deploy CDN bị thao túng hoặc một nội dung không đáng tin trên host ấy có thể trả JavaScript, chính sách nguồn không tự phân biệt code tốt với code xấu.

Đối với script ngoài, có thể xem xét **Subresource Integrity (SRI)** khi nội dung được ghim phiên bản và cơ chế tải hỗ trợ:

~~~html
<script
  src="https://cdn.example.net/vendor-v3.js"
  integrity="sha384-BASE64_DIGEST_OF_APPROVED_FILE"
  crossorigin="anonymous"
  defer></script>
~~~

`BASE64_DIGEST_OF_APPROVED_FILE` là placeholder; phải tính digest thật trước khi dùng. SRI kiểm tra nội dung tệp tải về đúng digest đã khai báo, nhưng không sửa lỗi trong code đã được chấp thuận hoặc giải quyết mọi vấn đề supply chain. CSP allowlist vẫn có nhiệm vụ kiểm soát nguồn, và CORS còn ảnh hưởng đến cách kiểm tra SRI của tài nguyên cross-origin.

### 4.3. Wildcard subdomain và domain phức tạp

Nếu ứng dụng cho `https://*.example.net` nhưng một số subdomain thuộc môi trường thử nghiệm, tenant tùy ý, bucket upload hoặc dịch vụ bên thứ ba, toàn bộ tập nguồn có thể khó quản lý.

Không thể kết luận chỉ từ wildcard rằng hệ thống chắc chắn khai thác được. Vấn đề là **mô hình sở hữu và cách phục vụ nội dung trên từng subdomain** phải được đánh giá. Allowlist theo tên miền chỉ hữu ích khi nguồn thực tế bị giới hạn theo đúng ý đồ bảo mật.

## 5. unsafe-inline: mở lại những đường thực thi từ HTML

Mã inline bao gồm:

~~~html
<!-- A. Script element nội tuyến -->
<script>
  window.pageReady = true;
</script>

<!-- B. Event handler nội tuyến -->
<button onclick="refreshData()">Làm mới</button>

<!-- C. Handler trong một phần tử khác -->
<img src="/missing.png" onerror="console.log('error')">

<!-- D. JavaScript URL -->
<a href="javascript:console.log('clicked')">Chạy</a>
~~~

Với chính sách:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'
~~~

browser có thể tải script ngoài cùng origin nhưng từ chối A, B, C và D nếu chúng không có cơ chế cấp phép inline hợp lệ.

Nếu đổi thành:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' 'unsafe-inline'
~~~

thì nhiều dạng JavaScript inline vốn bị chặn có thể được thực thi. Điều này đặc biệt nguy hiểm khi ứng dụng có lỗi HTML injection: một payload có thể chạy mà không cần tải file script ngoài.

### Vì sao unsafe-inline không nên là cách sửa lỗi template?

Một developer có thể thấy trang hỏng sau khi bật CSP:

~~~html
<button onclick="saveDraft()">Lưu</button>
~~~

Thay vì bật `'unsafe-inline'`, hãy chuyển handler sang script được quản lý:

~~~html
<button id="saveDraftButton" type="button">Lưu</button>
<script src="/js/draft.js" defer></script>
~~~

~~~javascript
// /js/draft.js — file được ứng dụng phục vụ và review.
document.getElementById("saveDraftButton")
  .addEventListener("click", () => saveDraft());
~~~

Với `script-src 'self'`, script ngoài cùng origin có thể được tải. Event handler inline không còn cần thiết.

### unsafe-inline không giống với CSP nonce/hash

Ví dụ policy có nonce:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-RANDOM_PER_RESPONSE'
~~~

Một thẻ script tin cậy có nonce khớp có thể chạy; một thẻ inline bị chèn **không có nonce** vẫn bị chặn. Với hash, browser so khớp **nội dung chính xác** của khối mã với digest trong policy.

Đây là cấp phép **có điều kiện và hẹp hơn** việc mở `'unsafe-inline'` cho mọi mã inline. Nhưng nonce/hash cũng không sửa lỗi nếu bạn gắn nonce hoặc hash cho chính code không đáng tin.

## 6. unsafe-eval: cho phép biến chuỗi thành code JavaScript

`'unsafe-eval'` là một từ khóa khác, không đồng nghĩa với `'unsafe-inline'`.

Ví dụ một file JavaScript ngoài cùng origin:

~~~javascript
// /js/app.js
console.log("Ứng dụng đang chạy");

// Các API nhận source code dưới dạng chuỗi:
const calculate = new Function("return 6 * 7");
const answer = calculate();
console.log(answer);

eval("console.log('evaluated string')");
~~~

Với:

~~~http
Content-Security-Policy: script-src 'self'
~~~

file `/js/app.js` có thể được tải, nhưng những cơ chế như `eval(...)` hoặc `new Function(...)` có thể bị chặn khi thực thi vì policy không cho `'unsafe-eval'`. Một số API nhận chuỗi code để thực thi, ví dụ dạng `setTimeout("doSomething()", 100)`, cũng thuộc loại hành vi cần kiểm tra.

Nếu đổi thành:

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-eval'
~~~

browser có thể cho những thao tác đánh giá JavaScript từ chuỗi được thực thi. Chính sách này **không tự cho phép** khối `<script>...</script>` inline hoặc event handler nếu không có cấp phép inline khác.

### Vì sao unsafe-eval làm tăng rủi ro?

Khi code hợp lệ có thể biên dịch một chuỗi do dữ liệu không đáng tin ảnh hưởng thành chương trình JavaScript, lỗ hổng xử lý dữ liệu có thể biến thành thực thi code. Chặn các cơ chế đánh giá chuỗi sẽ giảm một số đường tấn công; bật lại `'unsafe-eval'` làm mất hạn chế đó.

Nếu một thư viện yêu cầu eval vì development build, template compiler hoặc cấu hình bundler, nên:

1. Kiểm tra có bản production build không dùng eval hay không.
2. Thay API đánh giá chuỗi bằng xử lý dữ liệu: `JSON.parse(...)`, bộ định tuyến bằng hàm, map các hành động được khai báo.
3. Không nối dữ liệu người dùng vào biểu thức code.
4. Chỉ cân nhắc bật `'unsafe-eval'` sau khi đánh giá cụ thể và hiểu rủi ro còn lại.

Ví dụ tránh eval:

~~~javascript
// Không diễn giải biểu thức tùy ý thành JavaScript.
const approvedActions = {
  refresh: () => refreshDashboard(),
  save: () => saveDraft()
};

function runApprovedAction(name) {
  const action = approvedActions[name];
  if (!action) {
    throw new Error("Unsupported action");
  }
  action();
}
~~~

Điểm quan trọng là **tách dữ liệu khỏi mã có quyền thực thi**, không phải thay `eval(...)` bằng một cách biên dịch chuỗi khác.

### WebAssembly và wasm-unsafe-eval

Một số trình duyệt triển khai `'wasm-unsafe-eval'` để cho phép việc biên dịch/thực thi WebAssembly khi quy tắc script phù hợp đang giới hạn hành vi này, mà không mở rộng toàn bộ các API eval JavaScript.

Ví dụ minh họa:

~~~http
Content-Security-Policy: script-src 'self' 'wasm-unsafe-eval'
~~~

Đừng nhầm `'wasm-unsafe-eval'` với `'unsafe-eval'`: hỗ trợ trình duyệt và phạm vi kiểm soát không hoàn toàn giống nhau; `'unsafe-eval'` còn có tác động rộng hơn. Chỉ thêm một trong các từ khóa này nếu ứng dụng thật sự cần khả năng tương ứng và đã kiểm tra browser mục tiêu.

## 7. Hai từ khóa unsafe có thể gây hiểu nhầm khi dùng chung nonce/hash

Policy sau thường xuất hiện trong một số phương án tương thích với trình duyệt cũ:

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-inline' 'nonce-EXAMPLE_PER_RESPONSE'
~~~

Với những trình duyệt hỗ trợ nonce/hash theo các phiên bản CSP phù hợp, sự có mặt của nonce hoặc hash trong `script-src` làm `'unsafe-inline'` **bị bỏ qua đối với kiểm tra inline liên quan**. Nhờ đó, mã inline không được cấp nonce/hash không tự được phép chỉ vì chuỗi policy còn chứa `'unsafe-inline'`.

Tuy nhiên, một trình duyệt CSP đời cũ **không hỗ trợ nonce/hash** có thể diễn giải `'unsafe-inline'` theo cách cho phép inline rộng. Điều này có thể là quyết định tương thích có chủ đích, nhưng cần biết mức bảo vệ trên từng browser, không xem đây là công thức bảo mật giống nhau ở mọi nơi.

### unsafe-inline trong script-src khác style-src

~~~http
Content-Security-Policy: script-src 'self'; style-src 'self' 'unsafe-inline'
~~~

Policy trên không tự cho JavaScript inline chạy chỉ vì `style-src` có `'unsafe-inline'`; nó mở rộng các hình thức CSS inline thuộc phạm vi style. CSS injection có rủi ro riêng như thay đổi giao diện, che nội dung hoặc hỗ trợ lừa người dùng. Vì thế, cũng cần hạn chế việc nới style một cách không có căn cứ.

Khi muốn tách style element và style attribute trên CSP Level 3, có thể dùng:

~~~http
Content-Security-Policy: style-src 'self'; style-src-elem 'self'; style-src-attr 'none'
~~~

Browser hỗ trợ CSP Level 3 sẽ ưu tiên `style-src-elem` cho stylesheet/style element và `style-src-attr` cho thuộc tính `style="..."`. Tương tự, script có `script-src-elem` và `script-src-attr`. Khi directive chi tiết đã được khai báo, nó không tự cộng thêm những source expression ở directive chung; cần hiểu fallback trước khi thiết kế chính sách.

## 8. Nonce, hash và strict-dynamic: các hướng thay thế có điều kiện

Khi host allowlist không đủ mạnh và inline code cần được hỗ trợ, có thể chuyển từ tư duy “tin mọi script trên một danh sách host” sang “cấp phép những script khởi tạo đáng tin”.

### 8.1. Nonce riêng cho từng response

Một template có script inline hợp lệ:

~~~html
<script nonce="RANDOM_VALUE_FOR_THIS_RESPONSE">
  initializeDashboard();
</script>
~~~

Header của **cùng response**:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-RANDOM_VALUE_FOR_THIS_RESPONSE'
~~~

`RANDOM_VALUE_FOR_THIS_RESPONSE` là placeholder. Trong triển khai thật, server cần tạo nonce bằng ngẫu nhiên mật mã học, khó đoán, **mới cho từng response HTML**, rồi gắn khớp vào header và thẻ script tin cậy.

Không dùng nonce tĩnh lưu trong application config hoặc session. Cũng không tự động gắn nonce cho markup do người dùng kiểm soát; làm vậy chính là cấp quyền cho đoạn mã đó.

### 8.2. Hash cho code inline thực sự cố định

~~~http
Content-Security-Policy: script-src 'self' 'sha256-ACTUAL_BASE64_DIGEST'
~~~

`ACTUAL_BASE64_DIGEST` là placeholder: cần tính SHA-256 digest và mã hóa Base64 từ **chính xác nội dung** giữa thẻ `<script>...</script>`. Hash không bao gồm thẻ mở/đóng và có thể thay đổi khi whitespace/code thay đổi.

Đối với script/style inline cố định, hash giúp tránh phải tạo nonce từng response. Đối với code inline thay đổi theo request, nonce và cách render dữ liệu an toàn thường thuận tiện hơn. Không tự động tính hash của mọi chuỗi HTML người dùng cung cấp để cấp phép nó: đó là biến nội dung không đáng tin thành nội dung được cho phép.

### 8.3. strict-dynamic: tin một script khởi tạo, không phải toàn bộ CDN

Ví dụ:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'nonce-RANDOM_PER_RESPONSE' 'strict-dynamic'; object-src 'none'; base-uri 'none'
~~~

Ở trình duyệt hỗ trợ CSP Level 3, `'strict-dynamic'` cho phép một số script được cấp quyền thông qua nonce/hash truyền sự tin cậy sang script được chúng tải **động theo cơ chế phù hợp**. Đồng thời, các biểu thức host/scheme allowlist trong `script-src` có thể bị bỏ qua đối với việc khớp script trong chính sách đó.

Điều này **không đồng nghĩa mọi script xuất hiện trong DOM được phép chạy**. Script được parser nạp mà không có nonce/hash, hoặc đường nạp không thuộc cơ chế truyền tin cậy, vẫn có thể bị chặn. Hành vi phụ thuộc cách frontend tải script và hỗ trợ CSP của browser.

Đặc biệt, một script đã được cấp nonce/hash nhưng bị lợi dụng để tải URL do kẻ tấn công điều khiển có thể kéo theo code không mong muốn. `'strict-dynamic'` không thay thế việc kiểm soát URL động và tính an toàn của script khởi tạo.

### Bảng quyết định

| Nhu cầu | Giải pháp thường ưu tiên | Điều cần kiểm tra |
|---|---|---|
| JavaScript tĩnh do ứng dụng kiểm soát | File ngoài cùng origin, source list chặt | Origin có nội dung upload không đáng tin không? |
| Một vài script inline bất biến | CSP hash | Digest khớp HTML sau build/render |
| Script inline hợp lệ của server-rendered page | Nonce per response | Header, template và cache đồng bộ |
| Ứng dụng nạp script động theo bootstrap tin cậy | Nonce/hash + xem xét `'strict-dynamic'` | Loader, URL động, browser hỗ trợ |
| Legacy event handler `onclick` | Chuyển sang `addEventListener` | Không thêm `'unsafe-inline'` chỉ để giữ cú pháp cũ |
| Code dùng eval trong development | Production build không dùng eval | Tránh bật `'unsafe-eval'` toàn ứng dụng |
| WebAssembly hợp lệ bị chặn | Kiểm tra `'wasm-unsafe-eval'` theo browser | Không tự mở JavaScript `'unsafe-eval'` |

## 9. CSP Level 3: điều kiện ưu tiên và những bẫy cấu hình

CSP Level 3 chia script và style thành directive chi tiết:

| Nội dung | Directive ưu tiên | Fallback nếu vắng mặt |
|---|---|---|
| `<script src="...">` hoặc `<script>...</script>` | `script-src-elem` | `script-src` → `default-src` |
| `onclick="..."`, `onerror="..."` | `script-src-attr` | `script-src` → `default-src` |
| Stylesheet hoặc `<style>...</style>` | `style-src-elem` | `style-src` → `default-src` |
| `style="..."` | `style-src-attr` | `style-src` → `default-src` |

Ví dụ:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' 'nonce-RANDOM'; script-src-elem https://static.example.net; script-src-attr 'none'
~~~

Ở browser hỗ trợ `script-src-elem`, thẻ `<script>` chịu directive riêng `script-src-elem`. Một script inline chỉ có nonce trong `script-src` có thể **vẫn bị chặn**, vì nonce không tự được sao chép sang directive `script-src-elem`. Nếu dùng nonce cho script element, hãy khai báo nó trong directive thực sự điều khiển phần tử ấy và xác minh kết quả browser.

### unsafe-hashes không phải giải pháp mặc định

Một số trường hợp legacy yêu cầu inline handler hoặc style attribute. CSP Level 3 có cơ chế `'unsafe-hashes'` kết hợp hash của nội dung attribute trong directive phù hợp:

~~~http
Content-Security-Policy: script-src 'self'; script-src-attr 'unsafe-hashes' 'sha256-BASE64_DIGEST_OF_HANDLER'
~~~

`BASE64_DIGEST_OF_HANDLER` chỉ là placeholder. Đây là **cấp phép nội dung handler khớp hash**, không phải cấp phép riêng một nút trong DOM. Cùng chuỗi handler có thể xuất hiện ở nơi khác; mức hỗ trợ cũng thay đổi theo browser. **Ưu tiên loại bỏ handler nội tuyến**, không biến `'unsafe-hashes'` thành phương pháp sửa lỗi chung.

### object-src, base-uri và form-action không được quên

Ngay cả khi script policy chặt:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'nonce-RANDOM'
~~~

thì `form-action` và `base-uri` **không tự kế thừa** `default-src`. Nếu ứng dụng muốn hạn chế đích submit và thẻ `<base>`, nên khai báo thêm chính xác:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'nonce-RANDOM'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

`object-src 'none'` hạn chế object/embed; `frame-ancestors 'none'` hạn chế website khác nhúng tài liệu hiện tại. Các directive có nhiệm vụ khác nhau, không thể chỉ dựa vào `script-src` để ngăn mọi cách tải tài nguyên hoặc tương tác của trang.

## 10. Hai tình huống đánh giá chính sách yếu

### Tình huống A: HTML injection và unsafe-inline

Một ứng dụng hiển thị nội dung do người dùng nhập:

~~~html
<div class="review">
  <!-- Dữ liệu người dùng lẽ ra phải được escape trước khi render -->
  <img src="/not-found" onerror="console.log('inline handler executed')">
</div>
~~~

Đây là demo không có hành vi gửi dữ liệu, nhưng cho thấy đường thực thi: khi ảnh lỗi, handler inline có thể chạy nếu policy cấp quyền.

| Policy | Dự đoán trong browser hỗ trợ |
|---|---|
| `script-src 'self'` | Handler inline bị chặn |
| `script-src 'self' 'unsafe-inline'` | Handler inline có thể chạy |
| `script-src 'self'; script-src-attr 'none'` | Handler bị chặn rõ ràng bởi directive chi tiết |
| Policy nonce hợp lệ nhưng handler không được cấp cách cho phép riêng | Handler vẫn bị chặn |

**Không nên kết luận CSP thay thế escape:** nếu hình thức injection cho phép hiển thị form giả mạo, link sai hoặc ảnh bên ngoài, người dùng vẫn có thể bị tác động. CSP chỉ chặn những hành vi cụ thể theo chính sách.

### Tình huống B: Script hợp lệ dùng eval với dữ liệu không an toàn

Giả sử một thư viện nội bộ chạy trong file `/js/expression-engine.js`. Nó có code:

~~~javascript
// Minh họa API nguy hiểm cần loại khỏi code production.
function interpretExpression(expression) {
  return new Function("return (" + expression + ")")();
}

console.log(interpretExpression("21 * 2"));
~~~

Nếu `script-src 'self'` không có `'unsafe-eval'`, thao tác biên dịch chuỗi có thể bị chặn. Nếu developer thêm `'unsafe-eval'` để thư viện chạy, ứng dụng lại cho phép thao tác chuyển chuỗi thành code. Khi `expression` bị ảnh hưởng bởi dữ liệu không đáng tin, rủi ro cao hơn nhiều so với việc chỉ tính một biểu thức được kiểm soát.

Giải pháp tốt hơn là thay thư viện đánh giá chuỗi bằng parser tính toán giới hạn, lựa chọn hành động từ danh sách có kiểm soát hoặc xử lý dữ liệu theo cấu trúc. Chỉ sử dụng nguồn đầu vào đáng tin và validation không đủ để hợp thức hóa một API eval tùy ý.

## 11. Thiết kế policy bảo vệ nhiều lớp cho ứng dụng Spring

Một ứng dụng server-rendered giả định:

- HTML, JavaScript và CSS từ cùng origin `https://app.example.com`.
- Một API REST tại `https://api.example.net`.
- Ảnh sản phẩm tại `https://images.example.net`.
- Font cùng origin.
- Không có iframe/object/plugin hay nhu cầu eval.
- Có form submit cùng origin.
- Một script inline thực sự cần thiết, được gắn nonce ngẫu nhiên theo response.

Policy định hướng:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' 'nonce-NONCE_PER_RESPONSE'; script-src-attr 'none'; style-src 'self'; style-src-attr 'none'; img-src 'self' https://images.example.net; font-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

`NONCE_PER_RESPONSE` là placeholder và phải được thay bằng nonce mới của response. **Không dùng chuỗi cố định này trên production.**

Những quyết định có chủ đích:

| Quyết định | Lợi ích | Cần đánh giá |
|---|---|---|
| `default-src 'none'` | Không mở các nhóm chưa khai báo | Kiểm kê đủ các tài nguyên phụ |
| `script-src 'self'` | Cho script từ ứng dụng | Origin có upload hay endpoint trả JS không an toàn? |
| Nonce động | Cho thẻ script tin cậy inline | Cần đồng bộ header và template/cache |
| Không có `'unsafe-inline'` | Chặn nhiều đường XSS inline | Tách handler cũ và script inline không cần thiết |
| Không có `'unsafe-eval'` | Giới hạn đánh giá chuỗi thành code | Tương thích thư viện/build |
| Host cụ thể cho `img-src`/`connect-src` | Hạn chế nguồn ngoài cần thiết | CDN đổi host, API đổi origin, WSS nếu có |
| `object-src 'none'`, `base-uri 'none'` | Thu hẹp object và base URL injection | Không dùng object/base tag hợp lệ |
| `form-action 'self'` | Hạn chế đích submit form | SSO/payment form ngoài origin |

### Hướng tối giản nếu không còn inline script

Khi đã chuyển script/style vào file cùng origin, có thể bỏ nonce và dùng chính sách tĩnh dễ vận hành:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.net; font-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

Chính sách này vẫn không loại trừ hoàn toàn XSS, vì code chạy từ chính origin có thể chứa lỗi DOM XSS. Nhưng nó tránh hai nới lỏng lớn `'unsafe-inline'`/`'unsafe-eval'` và có allowlist rõ ràng hơn.

## 12. Cấu hình Spring Security Servlet

Ví dụ Spring MVC/Servlet dùng policy tĩnh, sau khi frontend đã chuyển script và style inline ra file tin cậy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    private static final String CSP_POLICY =
        "default-src 'none'; " +
        "script-src 'self'; " +
        "script-src-attr 'none'; " +
        "style-src 'self'; " +
        "style-src-attr 'none'; " +
        "img-src 'self' https://images.example.net; " +
        "font-src 'self'; " +
        "connect-src 'self' https://api.example.net; " +
        "object-src 'none'; " +
        "base-uri 'none'; " +
        "form-action 'self'; " +
        "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );

        // Authentication, authorization, CSRF, CORS, session... là các
        // phần bảo vệ độc lập và cần cấu hình theo yêu cầu ứng dụng.
        return http.build();
    }
}
~~~

Spring Security ghi header `Content-Security-Policy` trên những response thuộc chain phù hợp. Nó không tự kiểm tra HTML hoặc tự loại `unsafe-inline`/`unsafe-eval` nếu ứng dụng đã yêu cầu hai giá trị đó.

### Khi cần nonce động trong Servlet

`policyDirectives(CSP_POLICY)` với chuỗi `static final` chỉ dùng cho policy **tĩnh**. Nếu trang thực sự cần nonce theo response, hệ thống phải tạo nonce ngẫu nhiên trong luồng xử lý request, truyền cho template, đồng thời xuất header có nonce tương ứng trước khi response commit.

Không viết:

~~~java
// Sai: nonce cố định ở cấp cấu hình, dùng lại giữa các response.
String policy = "script-src 'self' 'nonce-fixed-value'";
~~~

Một thiết kế đúng có một nguồn sinh nonce theo request và một chủ thể chịu trách nhiệm ghi CSP header cuối cùng. Khi dùng filter/header writer tùy biến, tránh đồng thời để DSL tĩnh xuất thêm policy gây xung đột.

### Có nhiều SecurityFilterChain hoặc CDN frontend

Nếu ứng dụng có một chain cho `/api/**` và một chain cho HTML, hãy kiểm tra **response HTML thực sự** nhận CSP mong muốn. Chỉ đặt header lên JSON API không áp chính sách đó cho trang frontend được phục vụ từ CDN/origin khác.

## 13. Cấu hình Spring Security Reactive/WebFlux

Với Reactive/WebFlux, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        String policy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "script-src-attr 'none'; " +
            "style-src 'self'; " +
            "style-src-attr 'none'; " +
            "img-src 'self' https://images.example.net; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.net; " +
            "object-src 'none'; " +
            "base-uri 'none'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

Ý nghĩa của `script-src`, `'unsafe-inline'` và `'unsafe-eval'` **không thay đổi** giữa Servlet và WebFlux, vì browser thực thi CSP. Khác biệt là API server dùng để cấu hình HTTP security chain.

Nếu WebFlux render HTML có nonce, có thể tạo nonce qua một WebFilter theo request/exchange, truyền vào model rồi xuất header đồng bộ. Không dựa vào biến singleton hoặc `ThreadLocal` khi xử lý reactive. Một request API JSON không cần nonce riêng chỉ để trả dữ liệu cho HTML ở origin khác.

## 14. Report-Only và lộ trình siết policy

Chuyển đột ngột từ một policy rộng sang policy hẹp có thể làm hỏng thư viện UI, inline event handler, đoạn script bootstrap hoặc build code dùng eval. Ứng dụng đang vận hành nên thử một **candidate policy** bằng:

~~~http
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self'; script-src-attr 'none'; style-src 'self'; img-src 'self' https://images.example.net; connect-src 'self' https://api.example.net; object-src 'none'; report-uri /_csp/report
~~~

Report-Only ghi nhận vi phạm của policy thử nghiệm nhưng **không chặn chỉ vì policy thử nghiệm đó**. Nếu response đồng thời có một CSP thực thi, CSP thực thi vẫn có thể chặn tài nguyên.

**Các bước triển khai:**

1. **Kiểm kê hiện trạng:** source list, script từ CDN, inline script/handler, CSS-in-JS, thư viện dùng eval, nguồn ảnh/API/font/worker.
2. **Phân loại rủi ro:** host nào thật sự do ứng dụng kiểm soát, nguồn nào được người dùng upload, đường nào đang dùng `'unsafe-inline'` hoặc `'unsafe-eval'`.
3. **Giảm phụ thuộc:** chuyển handler sang `addEventListener`, thay eval, đưa inline script ra file hoặc dùng nonce/hash đúng cách.
4. **Thử Report-Only:** quan sát Console/báo cáo trên các trang và browser mục tiêu; xác minh từng vi phạm trước khi mở nguồn.
5. **Bật thực thi có kiểm soát:** chuyển candidate thành `Content-Security-Policy`, test luồng chính và các nhánh ít dùng.
6. **Theo dõi hồi quy:** nếu có CDN/proxy, xem CSP header trên HTML cuối cùng; tránh nhiều policy chồng chéo ngoài ý muốn.

Không biến mọi CSP violation thành một source expression được thêm tự động. Vi phạm có thể xuất phát từ extension, nội dung không đáng tin hoặc một endpoint bị thay đổi. Quan trọng là các tính năng **hợp lệ** hoạt động và nguồn được cấp phép đều có lý do.

### Multiple policies: mở ở một header không nhất thiết có hiệu lực

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-inline'
Content-Security-Policy: script-src 'self'
~~~

Khi browser nhận nhiều CSP **thực thi**, tất cả được áp dụng. Inline script có thể vẫn bị chặn bởi policy thứ hai dù policy thứ nhất chứa `'unsafe-inline'`. Điều này cũng xảy ra khi Spring Security và proxy/CDN mỗi nơi thêm một header. Đừng kết luận chính sách cuối cùng “ghi đè” toàn bộ chính sách trước đó.

## 15. Kiểm thử phía server bằng MockMvc và WebTestClient

### 15.1. Servlet: xác nhận chuỗi policy đã bỏ hai từ khóa unsafe

Giả sử ứng dụng có route HTML `/dashboard` đi qua Spring Security filter chain và được cấu hình test phù hợp:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        not(containsString("'unsafe-inline'"))
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        not(containsString("'unsafe-eval'"))
    ));
~~~

Test này kiểm tra **chuỗi header trên response server**. Nó chưa mô phỏng browser thực thi mã inline hoặc eval. Nếu route cần xác thực, chuẩn bị mock authentication phù hợp để kiểm tra đúng response HTML.

Một quy tắc kiểm thử bổ sung hữu ích là parse policy và kiểm tra `script-src` không chứa `*`, scheme-only `https:` hoặc những host không được phê duyệt. Việc dùng `containsString` đơn giản có thể không đủ cho những bộ quy tắc phức tạp hoặc nhiều CSP header.

### 15.2. Reactive: kiểm tra header trên route HTML

~~~java
// Trong lớp test đã có WebTestClient, route HTML /dashboard.
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*script-src 'self'.*"
    );
~~~

Với WebFlux, có thể đọc header và assert rằng không chứa `'unsafe-inline'`/`'unsafe-eval'`. Nếu frontend HTML do hệ thống khác trả, các test này cần được chạy ở nơi phát HTML thực tế để có ý nghĩa bảo vệ.

## 16. Thử nghiệm browser có kiểm soát

### Trang demo và các phép thử

Tạo một trang test chỉ chứa script ngoài cùng origin và CSP:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'
~~~

Đưa các phép thử dưới đây vào **môi trường do bạn kiểm soát**. Dùng dữ liệu minh họa, không gửi dữ liệu thật sang domain bên ngoài.

| Phép thử | Với policy chặt | Khi nới `'unsafe-inline'` hoặc `'unsafe-eval'` |
|---|---|---|
| `<script src="/js/app.js">` | Cho phép nếu file cùng origin | Vẫn được cho phép |
| `<script>console.log('inline')</script>` | Bị chặn nếu không nonce/hash | Có thể chạy khi bật `'unsafe-inline'` cho script |
| `onclick="console.log('click')"` | Bị chặn | Có thể chạy khi bật `'unsafe-inline'`, nếu không có directive chi tiết chặt hơn |
| Script ngoài gọi `eval("2 + 2")` | Bị chặn khi không cho eval | Có thể chạy khi bật `'unsafe-eval'` |
| Script ngoài gọi `new Function("return 42")` | Bị chặn khi không cho eval | Có thể chạy khi bật `'unsafe-eval'` |
| Thẻ script tải từ host HTTPS không có trong allowlist | Bị chặn | Hai từ khóa unsafe không tự cấp quyền URL ngoài |
| Thẻ script từ host HTTPS ngoài danh sách dưới `script-src https:` | Có thể được phép theo policy rộng | Không cần unsafe-inline để tải script ngoài |

**Chú ý:** nếu bạn đã khai báo `script-src-elem`/`script-src-attr`, kết quả có thể bị điều khiển bởi directive chi tiết thay vì `script-src`. Hãy đọc chính sách thực nhận, không chỉ nhìn một source expression.

### Các bước quan sát

1. Mở DevTools → Network, chọn request **document HTML**, xem toàn bộ header `Content-Security-Policy` và `Content-Security-Policy-Report-Only`.
2. Kiểm tra Console/Issues để tìm `Refused to execute inline script`, `Refused to evaluate a string as JavaScript` hoặc thông báo về nguồn script bị từ chối.
3. So sánh yêu cầu của ứng dụng với policy đang thử; phân biệt hành vi *được CSP cho phép* và hành vi thành công do các điều kiện khác.
4. Thay policy một biến mỗi lần trong môi trường test: mở `'unsafe-inline'`, sau đó trả lại; mở `'unsafe-eval'`, rồi trả lại. Ghi rõ đường thực thi nào thay đổi.
5. Kiểm tra browser mục tiêu, nhất là khi dùng nonce/hash, `'strict-dynamic'` hoặc directive `-elem`/`-attr`.
6. Xác nhận sau khi sửa, script/style hợp lệ vẫn hoạt động trong khi payload không được cấp phép vẫn bị chặn.

Mã nhập trực tiếp trong **DevTools Console** có thể được browser xử lý khác với code đi qua HTML hoặc script ứng dụng. Để đo hiệu lực CSP, hãy thử qua chính trang test và luồng tải mã của tài liệu, không chỉ dựa vào Console.

## 17. Chẩn đoán xung đột khi bỏ allowlist rộng và unsafe

| Triệu chứng | Khả năng nguyên nhân | Hướng xử lý |
|---|---|---|
| Bật CSP rồi nút không hoạt động | `onclick` nội tuyến bị chặn | Chuyển handler sang file JS đáng tin |
| Bootstrap script inline không chạy | Thiếu nonce/hash, không còn `'unsafe-inline'` | Chuyển ra file hoặc dùng nonce/hash đúng cách |
| Framework báo lỗi eval sau khi siết CSP | Build/thư viện dùng `eval`/`new Function` | Dùng production build hoặc thay thư viện |
| Script CDN bị chặn | Host không có trong `script-src` | Đánh giá host và mở chính xác nếu cần |
| Script từ `'self'` vẫn bị chặn | `script-src-elem` chuyên biệt hoặc CSP khác | Kiểm tra directive ưu tiên và nhiều header |
| Script có nonce vẫn bị chặn | Nonce lệch header/HTML, sai directive, hoặc policy khác | Kiểm tra response HTML và toàn bộ CSP |
| CSP có `'strict-dynamic'` nhưng host allowlist không hoạt động như cũ | Browser có thể bỏ qua host source khi dùng strict-dynamic | Xem mô hình bootstrap/loader và support |
| Script vẫn chạy dù bạn thấy report | Có thể là Report-Only không chặn | Kiểm tra tên header và policy thực thi |
| Local hoạt động, production hỏng | CDN/proxy thay header, asset host khác, build khác | Xem HTML production, network và source list |
| Ảnh/API không tải sau khi siết `default-src` | `img-src`/`connect-src` chưa khai báo | Chỉ mở directive cần thiết |
| API fetch bị chặn dù backend cho CORS | CSP `connect-src` của trang hạn chế đích | Kiểm tra CSP ở frontend HTML |
| POST bị server trả 403 | CSRF/authorization hoặc nghiệp vụ | Kiểm tra phía server, không nới CSP |
| Thêm `'unsafe-eval'` nhưng inline handler vẫn bị chặn | Eval khác với inline | Chuyển handler hoặc dùng cấp phép inline đúng cơ chế |
| Thêm `'unsafe-inline'` nhưng `eval` vẫn bị chặn | Inline khác với eval | Loại bỏ eval; không bật thêm unsafe-eval vội |

### Nguyên tắc xử lý có hệ thống

Khi gặp lỗi, lần lượt xác định:

1. **Response nào** chứa CSP? Có phải HTML thực sự mà browser đang render không?
2. **Directive nào** đang quyết định hành vi? `script-src`, `script-src-elem`, `script-src-attr`, `connect-src` hay một policy khác?
3. **Đường thực thi nào** đang bị chặn: file ngoài, inline block, event handler, `eval`, WebAssembly hay request đến API?
4. **Nguồn hoặc code có thực sự đáng tin** không? Chỉ mở đường đã xác minh.
5. **Có thể thay đổi code để bỏ nhu cầu unsafe** hay không? Đây thường là giải pháp bền vững nhất.
6. **Các lớp khác** như CORS, CSRF, HSTS, HTTP firewall, cookie/session và xử lý dữ liệu có còn đúng không?

## 18. Trusted Types và phòng vệ bổ sung cho DOM XSS

CSP có thể giúp hạn chế những đường thực thi từ markup bị chèn, nhưng ứng dụng vẫn có nguy cơ **DOM XSS** khi một script hợp lệ đưa dữ liệu không đáng tin vào những API DOM có khả năng phân tích HTML hoặc code.

Ví dụ mã cần xem xét:

~~~javascript
// Không an toàn nếu htmlFromUser không được kiểm soát đúng cách:
document.getElementById("content").innerHTML = htmlFromUser;
~~~

Một cách thiết kế đơn giản hơn khi chỉ cần hiển thị văn bản:

~~~javascript
document.getElementById("content").textContent = textFromUser;
~~~

Trong các browser hỗ trợ, **Trusted Types** có thể bổ sung rào cản tại những *DOM injection sink* được hỗ trợ. Cơ chế CSP liên quan có thể bao gồm:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types appPolicy
~~~

Ví dụ chỉ minh họa directive; việc bật Trusted Types cần kiểm kê sink, tạo policy thật sự an toàn và kiểm tra mức hỗ trợ browser. Không coi Trusted Types thay thế escape/sanitize hoặc dùng một policy tự động trả lại nguyên HTML người dùng để “cho qua” kiểm tra. Trong trình duyệt không hỗ trợ, không được dựa hoàn toàn vào cơ chế này.

### Giới hạn tổng thể của CSP

Ngay cả một CSP chặt vẫn không bảo vệ khỏi mọi lỗi:

- Một script được phép có thể xử lý DOM sai hoặc tiết lộ dữ liệu qua API hợp lệ.
- Một endpoint server thiếu authorization vẫn có thể trả dữ liệu không nên được truy cập.
- CSRF được bảo vệ bằng cơ chế server và cookie phù hợp, không phải `script-src`.
- CORS bảo vệ khả năng đọc response cross-origin của JavaScript, không thay thế CSP hay kiểm tra quyền server.
- HSTS, session cookie bảo mật, HTTP firewall và cơ chế bảo vệ request giải quyết những rủi ro khác.

Do đó, mục tiêu không phải chỉ “đạt điểm CSP” hay “không còn Console error”, mà là **tăng chất lượng ranh giới tin cậy từ dữ liệu, HTML, JavaScript đến HTTP server**.

## 19. Bài thực hành tổng hợp

**Tình huống:** Một dashboard Spring Boot có script cùng origin, một thư viện UI tải từ CDN, vài handler `onclick` cũ, đoạn code development dùng `new Function(...)` và API tại `https://api.example.net`. CSP hiện tại có `script-src https: 'unsafe-inline' 'unsafe-eval'`.

1. Ghi lại các nguồn script thực sự được sử dụng. Giải thích vì sao `https:` cho nhiều host hơn yêu cầu hiện tại và thay bằng nguồn cụ thể đã phê duyệt.
2. Tạo một trang test có script ngoài cùng origin, script inline và inline event handler. Thử chính sách `script-src 'self'` rồi `script-src 'self' 'unsafe-inline'`; ghi kết quả.
3. Chuyển handler cũ sang `addEventListener` trong file JS và loại bỏ nhu cầu `'unsafe-inline'`.
4. Thử `eval("2 + 2")` hoặc `new Function("return 42")` từ file JS cùng origin; quan sát sự khác biệt khi có và không có `'unsafe-eval'`. Sau đó sửa code để không cần đánh giá chuỗi.
5. Chọn một script inline hợp lệ, cố định để cấp phép bằng hash; với trường hợp động, thiết kế nonce per response và truyền nonce đồng bộ vào template.
6. Nếu muốn dùng `'strict-dynamic'`, xác định script bootstrap nào được cấp nonce/hash, script nào được tải động và các giới hạn URL bên trong loader.
7. Cấu hình Spring Security Servlet bằng `HttpSecurity.headers(...).contentSecurityPolicy(...)` với policy tĩnh sau khi đã loại bỏ inline và eval.
8. Lặp lại cấu hình trên WebFlux với `ServerHttpSecurity`, kiểm tra header bằng WebTestClient.
9. Bật candidate policy trong Report-Only ở môi trường test; đối chiếu các violation với tính năng hợp lệ rồi chuyển sang enforcement.
10. Dùng browser kiểm tra những hành vi bị chặn và được phép, phân biệt CSP với CORS/CSRF nếu các API hoặc form không hoạt động.

**Câu hỏi tự đánh giá:**

1. Tại sao `script-src https:` yếu hơn `script-src 'self' https://static.example.net` nếu ứng dụng chỉ cần một CDN?
2. `script-src 'self'` có luôn an toàn khi cùng origin phục vụ file người dùng upload không?
3. `'unsafe-inline'` mở thêm những đường thực thi nào và tại sao có thể làm giảm hiệu quả CSP trước HTML injection?
4. `'unsafe-eval'` có tự cho phép `onclick="..."` không? Ngược lại, `'unsafe-inline'` có tự cho phép `eval(...)` không?
5. Khi policy có nonce/hash và `'unsafe-inline'`, hành vi có giống nhau trên mọi phiên bản CSP/browser không?
6. `'strict-dynamic'` có thể làm thay đổi cách host allowlist được áp dụng như thế nào?
7. Vì sao một script tải từ CDN đã được allowlist vẫn có thể gây rủi ro?
8. `script-src-elem` có thể khiến hash/nonce chỉ nằm trong `script-src` không còn áp dụng cho script element như mong đợi không?
9. Vì sao CSP không thay thế escape/sanitize HTML, kiểm soát quyền và CSRF protection?
10. Làm thế nào xác minh rằng policy mới có hiệu lực trên response HTML thực tế khi frontend và API tách origin?

## 20. Ghi nhớ

**Allowlist rộng, `'unsafe-inline'` và `'unsafe-eval'` là ba cách nới CSP theo những chiều khác nhau.** Một host hoặc scheme được cho phép không biến mọi script từ đó thành đáng tin. `'unsafe-inline'` có thể cấp quyền cho mã trực tiếp trong HTML và handler, còn `'unsafe-eval'` mở những đường chuyển chuỗi thành JavaScript thực thi. Hai từ khóa này **không thay thế nhau** và không nên được thêm chỉ để loại bỏ cảnh báo.

Trong ứng dụng Spring Security Servlet/WebFlux, hãy kiểm kê nguồn thực tế, dùng allowlist hẹp, ưu tiên JS/CSS ngoài đáng tin, loại bỏ handler/eval, sử dụng nonce/hash đúng trường hợp, cân nhắc `'strict-dynamic'` khi hiểu rõ loader và triển khai qua Report-Only rồi kiểm thử enforcement. CSP là một lớp phòng vệ của mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, phải phối hợp với mã hóa đầu ra, Trusted Types khi phù hợp, CORS, CSRF, HSTS, HTTP firewall và bảo vệ session.
