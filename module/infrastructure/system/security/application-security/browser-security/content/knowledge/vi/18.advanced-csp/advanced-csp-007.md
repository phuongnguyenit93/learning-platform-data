# Unsafe-inline: vì sao cho phép mã inline làm suy yếu CSP?

> **Chương:** CSP nâng cao  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Trong Content Security Policy (CSP), source expression `'unsafe-inline'` cho phép browser thực thi hoặc áp dụng một số nội dung inline nằm ngay trong tài liệu HTML, thay vì chỉ chấp nhận tài nguyên được cấp quyền bằng nonce, hash hoặc nguồn đã khai báo. Với `script-src`, nó có thể mở quyền cho inline `<script>`, event handler như `onclick` và URL dạng `javascript:`. Với `style-src`, nó cho phép inline CSS như phần tử `<style>` và thuộc tính `style`.

Tên gọi “unsafe” phản ánh đúng rủi ro: khi ứng dụng cho phép inline script rộng rãi, một lỗi chèn HTML có thể dễ dàng trở thành lỗi thực thi JavaScript. CSP khi đó mất đi một trong những lớp bảo vệ quan trọng nhất trước XSS. Với inline style, tác động khác: nó không trực tiếp bật thực thi JavaScript, nhưng có thể cho phép CSS không tin cậy thay đổi giao diện, che nút, tạo lớp phủ hoặc làm sai lệch nội dung người dùng nhìn thấy.

Bài này phân tích chính xác `'unsafe-inline'` tác động tới script và style, cách nonce/hash tương tác với nó trong CSP2/CSP3, cách thay inline handler/style bằng API an toàn và cách loại bỏ ngoại lệ trong một ứng dụng đang chạy.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `'unsafe-inline'` cho phép những dạng nội dung inline nào trong `script-src` và `style-src`.
2. Phân biệt inline script element, event handler attribute, `javascript:` URL, style element và style attribute.
3. Phân biệt `'unsafe-inline'` với `'unsafe-eval'` và hiểu vì sao hai directive giải quyết hai nhóm rủi ro khác nhau.
4. Hiểu nonce/hash có thể khiến `'unsafe-inline'` bị bỏ qua trong browser hỗ trợ CSP2+, nhưng không dựa vào điều đó để giữ policy khó hiểu.
5. Dùng `script-src-elem`, `script-src-attr`, `style-src-elem` và `style-src-attr` để kiểm soát từng loại inline.
6. Thay inline event handler bằng `addEventListener()` và thay inline style bằng class/CSS có kiểm soát.
7. Dùng `'unsafe-hashes'` trong trường hợp legacy rất hẹp và đánh giá giới hạn của nó.
8. Lập kế hoạch migration từ policy đang có `'unsafe-inline'` sang nonce/hash hoặc external resource.
9. Kiểm chứng enforcement, Report-Only và hành vi nonce bằng Node.js cùng DevTools.

## 1. Inline content là gì?

### 1.1 Inline script element

Một script inline được viết trực tiếp trong tài liệu:

~~~html
<script>
  document.querySelector('#status').textContent = 'Ready';
</script>
~~~

Nội dung JavaScript nằm trong HTML response. Nếu CSP không cấp quyền cho inline script bằng nonce, hash hoặc source expression phù hợp, browser sẽ chặn thực thi.

Với `script-src 'unsafe-inline'`, browser cho phép loại inline script này mà không cần nonce/hash. Khi ứng dụng có XSS khiến attacker chèn được một script element, policy rộng này có thể cho phép script chạy.

### 1.2 Inline event handler attribute

Event handler được viết trực tiếp trong HTML attribute:

~~~html
<button onclick="saveProfile()">Lưu</button>
<img src="/avatar" onerror="showFallback()">
~~~

Đây cũng là inline JavaScript. `'unsafe-inline'` trong script policy có thể cho phép những handler này chạy.

Cách viết này gắn logic với markup, làm khó việc kiểm soát nguồn code và khiến việc loại bỏ inline script phức tạp hơn. Hãy dùng event listener:

~~~html
<button id="save-profile" type="button">Lưu</button>
~~~

~~~js
document
  .querySelector('#save-profile')
  .addEventListener('click', saveProfile);
~~~

Khi đó markup không chứa JavaScript và có thể chạy dưới một CSP không cho phép inline handler.

### 1.3 URL dạng javascript:

Ví dụ:

~~~html
<a href="javascript:showHelp()">Trợ giúp</a>
~~~

URL scheme `javascript:` có thể thực thi code khi điều hướng/kích hoạt trong những ngữ cảnh browser hỗ trợ. Đây là một dạng inline script cần tránh.

Thay bằng link điều hướng thực sự hoặc button:

~~~html
<button id="help" type="button">Trợ giúp</button>
~~~

~~~js
document.querySelector('#help').addEventListener('click', showHelp);
~~~

Không tạo `javascript:` URL từ dữ liệu người dùng và không coi việc HTML-encode attribute là biện pháp thay thế kiểm soát scheme.

### 1.4 Inline style element

CSS có thể được viết ngay trong tài liệu:

~~~html
<style>
  .notice { color: darkblue; }
</style>
~~~

`'unsafe-inline'` trong style policy cho phép inline stylesheet này. Nếu không có quyền tương ứng, browser có thể chặn style element không có nonce/hash phù hợp.

### 1.5 Style attribute

CSS cũng có thể nằm trực tiếp trong attribute:

~~~html
<p style="color: darkblue; margin: 1rem">Thông báo</p>
~~~

`style-src 'unsafe-inline'` có thể cho phép style attribute. Đây là một phạm vi riêng với script inline: nó cho phép CSS, không cho phép JavaScript.

CSS injection không đồng nghĩa với script execution, nhưng có thể gây tác động bảo mật hoặc giao diện tùy dữ liệu và DOM. Ví dụ CSS không tin cậy có thể che cảnh báo, làm nổi bật nút giả, thay đổi thứ tự/khả năng nhìn thấy nội dung hoặc khai thác các side channel trong những ứng dụng đặc thù. Không nên xem inline style là vô hại chỉ vì CSS không phải JavaScript.

## 2. unsafe-inline trong script-src

### 2.1 Những gì được cho phép?

Khi policy có:

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-inline'
~~~

browser cho phép script từ nguồn cùng origin và các dạng inline script thuộc phạm vi directive, bao gồm:

- Inline `<script>` không có nonce/hash.
- Inline event handler attributes như `onclick`, `onload`, `onerror`.
- URL dạng `javascript:` trong các ngữ cảnh thực thi được hỗ trợ.

Phạm vi cụ thể chịu ảnh hưởng của CSP version và directive chuyên biệt. CSP3 cho phép tách phần tử script và event handler thành `script-src-elem` và `script-src-attr`. Nếu không khai báo directive chuyên biệt, browser dùng fallback tương ứng.

### 2.2 Vì sao rủi ro XSS tăng mạnh?

Giả sử ứng dụng có một lỗi reflected XSS và attacker có thể đưa markup vào trang. Nếu policy chặn inline script, một payload dạng script element hoặc event handler có thể bị browser chặn. Nếu policy cho `'unsafe-inline'`, browser có thể thực thi inline code được chèn.

Điều đó không có nghĩa mọi XSS đều bị ngăn khi bỏ `'unsafe-inline'`: attacker có thể khai thác script gadget, nguồn script được allowlist, DOM sink hoặc các đường thực thi khác. Nhưng loại bỏ quyền inline rộng là một bước quan trọng để strict CSP có ý nghĩa.

### 2.3 unsafe-inline không tương đương unsafe-eval

Hai keyword thường bị nhầm:

| Keyword | Cho phép | Ví dụ rủi ro |
|---|---|---|
| `'unsafe-inline'` | Inline script và event handler theo directive script; hoặc inline CSS theo directive style | Markup injection có thể tạo script/handler inline |
| `'unsafe-eval'` | Các API đánh giá code từ chuỗi như `eval()`, `new Function()` và một số dạng dynamic compilation | Dữ liệu đi vào chuỗi code có thể bị thực thi |
| Cả hai | Hai nhóm hành vi khác nhau | Bật cả hai làm policy yếu hơn đáng kể |

Bỏ `'unsafe-inline'` không tự động cho phép `eval()`. Thêm `'unsafe-eval'` cũng không phải cách thay thế cho inline script. Chỉ bật đúng ngoại lệ nếu có bằng chứng kỹ thuật và đánh giá rủi ro.

### 2.4 unsafe-inline không cho phép mọi script

Policy `script-src 'unsafe-inline'` vẫn chịu các giới hạn CSP khác. Ví dụ, nó không tự động cho phép script tải từ một CDN không được cho phép, cũng không cấp quyền cho mọi loại worker/resource. Các directive như `connect-src`, `worker-src` và `object-src` có nhiệm vụ riêng.

Tuy nhiên, nếu XSS có thể chèn inline script, attacker không cần tải một file script từ host ngoài. Đây là lý do keyword này nguy hiểm.

## 3. unsafe-inline trong style-src

### 3.1 Phạm vi của inline CSS

Policy:

~~~http
Content-Security-Policy: style-src 'self' 'unsafe-inline'
~~~

cho phép stylesheet cùng origin và inline style trong phạm vi style directive. Tùy browser/CSP version, inline style có thể gồm:

- Phần tử `<style>`.
- Thuộc tính `style="..."`.
- Một số thao tác tạo/chèn style qua DOM/CSSOM chịu kiểm soát của CSP.

Để biết chính xác một API CSSOM có bị policy chặn hay không, kiểm tra browser mục tiêu và CSP violation thực tế. Không suy ra rằng mọi phép gán qua JavaScript đều có cùng semantics với markup style attribute.

### 3.2 Rủi ro giao diện và CSS injection

Inline CSS không tự bật JavaScript, nhưng CSS do attacker kiểm soát có thể:

- Ẩn thông báo bảo mật hoặc trạng thái giao dịch.
- Che phủ control thật và làm người dùng bấm nhầm.
- Tạo giao diện giả hoặc thay đổi thứ tự hiển thị.
- Làm lộ một số trạng thái thông qua selector/side channel trong những cấu trúc đặc thù.
- Làm sai lệch nội dung hoặc khả năng truy cập.

CSP style policy là một lớp giảm rủi ro. Ứng dụng vẫn phải tránh đưa dữ liệu không tin cậy vào CSS parser, validate giá trị động và dùng class được định nghĩa sẵn.

### 3.3 Phân biệt style element và style attribute

CSP3 có các directive chuyên biệt:

- `style-src-elem` kiểm soát stylesheet element như `<style>` và `<link rel="stylesheet">`.
- `style-src-attr` kiểm soát inline style attribute.

Nếu không có directive chuyên biệt, browser fallback về `style-src` rồi `default-src`. Nhờ vậy, ứng dụng có thể cho phép stylesheet element bằng nonce/hash nhưng vẫn chặn mọi style attribute.

## 4. Nonce/hash và quy tắc bỏ qua unsafe-inline

### 4.1 Nonce hoặc hash có thể làm unsafe-inline bị bỏ qua

Trong browser hỗ trợ CSP2 trở lên, nếu source list của một directive có nonce-source hoặc hash-source hợp lệ, `'unsafe-inline'` trong cùng source list bị bỏ qua theo quy tắc CSP. Điều này cho phép một số policy chuyển tiếp có cả keyword cũ và nonce/hash mới, nhưng cần hiểu rõ mức hỗ trợ của browser.

Ví dụ:

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-inline' 'nonce-RANDOM_VALUE'
~~~

Trong browser hỗ trợ nonce CSP, inline script cần nonce khớp; keyword `'unsafe-inline'` không còn mở toàn bộ inline script như trước. Browser cũ không hiểu nonce có thể bỏ qua nonce source và vẫn áp dụng `'unsafe-inline'`.

Đây có thể là chiến lược tương thích trong giai đoạn chuyển đổi, nhưng **không phải strict CSP cho mọi browser**. Nếu mục tiêu là chặn inline script trên mọi browser được hỗ trợ, cần loại bỏ keyword và xác định rõ browser support policy.

### 4.2 Nonce chỉ áp dụng cho script/style element

Ví dụ:

~~~http
Content-Security-Policy: script-src 'nonce-ABC123'; script-src-attr 'none'
~~~

~~~html
<script nonce="ABC123">
  initializeApp();
</script>
<button onclick="initializeApp()">Run</button>
~~~

Script element có nonce hợp lệ được phép. Event handler attribute không được cấp quyền bởi nonce của script element; `script-src-attr 'none'` chặn handler.

Nonce là thuộc tính trên phần tử `<script>` hoặc `<style>`. Không có cơ chế gắn nonce cho attribute `onclick` hoặc `style` để cấp quyền tương đương.

### 4.3 Hash cho inline script cố định

Có thể cho phép một script element inline cố định bằng hash:

~~~http
Content-Security-Policy: script-src 'sha256-BASE64_HASH'; script-src-attr 'none'
~~~

Hash phải khớp chính xác nội dung script theo thuật toán CSP. Thay một ký tự hoặc khoảng trắng có thể làm hash không còn khớp.

Hash của script element không tự động cho phép inline event handler. Với handler legacy, cần xử lý riêng; ưu tiên chuyển sang event listener.

### 4.4 unsafe-hashes là ngoại lệ hẹp cho handler legacy

CSP có source expression `'unsafe-hashes'` cho phép hash khớp với một số inline event handler hoặc style attribute khi kết hợp hash source tương ứng.

Ví dụ minh họa:

~~~http
Content-Security-Policy: script-src 'unsafe-hashes' 'sha256-HASH_OF_HANDLER'; script-src-attr 'unsafe-hashes' 'sha256-HASH_OF_HANDLER'
~~~

Cách này chỉ cho phép đoạn handler có nội dung khớp hash; nó không mở toàn bộ inline handler như `'unsafe-inline'`. Nhưng handler vẫn nằm trong markup và có thể khó bảo trì. Chỉ dùng như biện pháp chuyển tiếp khi chưa thể sửa code, sau đó thay bằng `addEventListener()`.

Không sao chép hash giả trong ví dụ. Hash production phải được tính từ đúng bytes/chuỗi handler theo quy tắc CSP và kiểm tra trên browser mục tiêu.

### 4.5 Directive chuyên biệt có thể mở lại inline

Một policy có thể chặn inline script element nhưng vô tình cho phép event handler:

~~~http
Content-Security-Policy: script-src-elem 'nonce-ABC123'; script-src-attr 'unsafe-inline'
~~~

Script element cần nonce, nhưng event handler attribute vẫn được cho phép do directive riêng. Khi rà soát CSP3, kiểm tra cả:

- `script-src`
- `script-src-elem`
- `script-src-attr`
- `style-src`
- `style-src-elem`
- `style-src-attr`

Không kết luận policy an toàn chỉ vì `script-src` không chứa `'unsafe-inline'`. Một directive chuyên biệt có thể mở quyền riêng cho loại inline khác.

## 5. Loại bỏ inline JavaScript

### 5.1 Chuyển event handler sang addEventListener

Trước:

~~~html
<button onclick="submitOrder()">Đặt hàng</button>
~~~

Sau:

~~~html
<button id="submit-order" type="button">Đặt hàng</button>
<script src="/assets/order.js" defer></script>
~~~

File `/assets/order.js`:

~~~js
document
  .querySelector('#submit-order')
  .addEventListener('click', submitOrder);
~~~

Logic nằm trong file script được quản lý, review và cấp quyền bởi CSP. Không đưa dữ liệu người dùng vào source code handler.

### 5.2 Gắn listener cho phần tử được tạo động

Nếu UI tạo button động, vẫn có thể dùng event delegation:

~~~js
document.querySelector('#orders').addEventListener('click', event => {
  const button = event.target.closest('[data-action="cancel"]');
  if (!button) return;

  cancelOrder(button.dataset.orderId);
});
~~~

Markup chỉ mang data attribute; logic được giữ trong JavaScript tin cậy. Giá trị data attribute vẫn phải được kiểm tra theo nghiệp vụ và authorization phía server.

### 5.3 Thay javascript: URL

Trước:

~~~html
<a href="javascript:openDialog()">Mở hộp thoại</a>
~~~

Sau:

~~~html
<button id="open-dialog" type="button">Mở hộp thoại</button>
~~~

~~~js
document
  .querySelector('#open-dialog')
  .addEventListener('click', openDialog);
~~~

Nếu control thực sự điều hướng, dùng URL HTTPS đã được kiểm tra thay vì javascript URL.

### 5.4 Inline script khởi tạo dữ liệu

Ứng dụng server-rendered đôi khi nhúng biến trực tiếp:

~~~html
<script>
  window.currentUser = 'USER_INPUT';
</script>
~~~

Không nối dữ liệu không tin cậy vào JavaScript string. Các lựa chọn tốt hơn:

- Tải JSON từ endpoint same-origin sau khi trang khởi tạo.
- Đặt dữ liệu vào các thuộc tính/data node với encoding đúng context rồi đọc bằng DOM API.
- Nếu buộc phải nhúng JSON, dùng serializer an toàn cho HTML script context, escape ký tự `<` thành `\u003c` để ngăn chuỗi `</script>` kết thúc script element, và cấp nonce/hash phù hợp.

Nonce cho phép script element được thực thi; nó không làm dữ liệu nhúng trong script trở nên an toàn.

## 6. Loại bỏ inline CSS

### 6.1 Chuyển style attribute sang class

Trước:

~~~html
<p style="color: red; font-weight: bold">Thanh toán thất bại</p>
~~~

Sau:

~~~html
<p class="payment-error">Thanh toán thất bại</p>
~~~

CSS:

~~~css
.payment-error {
  color: red;
  font-weight: bold;
}
~~~

Class CSS được định nghĩa trong stylesheet cùng origin hoặc nguồn được CSP cho phép. Dữ liệu người dùng không còn được parse như CSS.

### 6.2 Chuyển style element sang stylesheet

Trước:

~~~html
<style>
  .card { border-radius: 8px; }
</style>
~~~

Sau:

~~~html
<link rel="stylesheet" href="/assets/app.css">
~~~

Nếu ứng dụng server-rendered cần style block động, có thể dùng nonce cho style element; không bật `'unsafe-inline'` chỉ để tránh cấp nonce.

### 6.3 Giá trị CSS động có kiểm soát

Một số giao diện cần giá trị động như chiều rộng thanh tiến trình hoặc màu theo trạng thái. Ưu tiên ánh xạ giá trị sang class có sẵn:

~~~js
const stateClass = {
  success: 'status-success',
  warning: 'status-warning',
  error: 'status-error'
};

const className = stateClass[status] || 'status-neutral';
statusElement.className = className;
~~~

Nếu thực sự cần giá trị số động, kiểm tra kiểu, khoảng và đơn vị trước khi gán qua CSS property. Không lấy chuỗi CSS tùy ý từ người dùng rồi đưa vào style attribute.

## 7. Cách viết policy không cần unsafe-inline

### 7.1 Tách script element và event handler

Một policy CSP3 có thể tách rõ hai loại:

~~~http
Content-Security-Policy: default-src 'none'; script-src-elem 'self' 'nonce-RANDOM_VALUE'; script-src-attr 'none'; object-src 'none'; base-uri 'none'; connect-src 'self'; img-src 'self'; style-src-elem 'self' 'nonce-RANDOM_VALUE'; style-src-attr 'none'; form-action 'self'; frame-ancestors 'none'
~~~

Ý nghĩa:

- Script element được tải từ cùng origin hoặc inline script có nonce hợp lệ.
- Inline event handler bị chặn.
- Stylesheet element được tải từ cùng origin hoặc style element có nonce.
- Style attribute bị chặn.
- Các nguồn khác bị giới hạn rõ ràng.

Nếu cần hỗ trợ browser cũ không hiểu directive chuyên biệt, hãy khai báo fallback `script-src`/`style-src` phù hợp và kiểm tra behavior theo từng CSP version. Đừng đưa `unsafe-inline` vào fallback mà không hiểu browser cũ sẽ thực thi nó.

### 7.2 Dùng nonce-based strict policy

Ví dụ policy gọn hơn:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'nonce-RANDOM_VALUE' 'strict-dynamic'; style-src 'self' 'nonce-RANDOM_VALUE'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'
~~~

Policy này không cho phép inline event handler. Script element tin cậy phải có nonce; `strict-dynamic` có thể truyền trust tới script được script có nonce tải động trong browser hỗ trợ CSP3.

Không tự động thêm `unsafe-inline` để sửa lỗi tương thích. Kiểm kê browser và script loader trước khi quyết định fallback.

### 7.3 Hash-based policy

Nếu ứng dụng có inline script nhỏ và cố định:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'sha256-BASE64_HASH'; script-src-attr 'none'; style-src 'self'; object-src 'none'; base-uri 'none'
~~~

Build pipeline cần tính hash và cập nhật header cùng lúc với HTML. Không dùng hash cố định cho nội dung có dữ liệu thay đổi theo request.

### 7.4 Chỉ cho phép style inline trong trường hợp cần thiết

Nếu chưa thể loại bỏ toàn bộ inline style, có thể đánh giá nonce cho style element hoặc hash/`'unsafe-hashes'` cho một số style attribute cố định theo CSP support. Tránh mở `style-src 'unsafe-inline'` trên toàn ứng dụng nếu chỉ một component legacy cần ngoại lệ.

Một phương án tốt hơn là tách component legacy ra route/ứng dụng riêng với policy giới hạn và kế hoạch loại bỏ rõ ràng. Không để ngoại lệ của một trang làm yếu policy của mọi trang nhạy cảm.

## 8. Report-Only và migration khỏi unsafe-inline

### 8.1 Đo trước khi chặn

Bắt đầu bằng policy Report-Only không có `'unsafe-inline'`:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-RANDOM_VALUE'; script-src-attr 'none'; style-src 'self' 'nonce-RANDOM_VALUE'; style-src-attr 'none'; object-src 'none'; base-uri 'none'
~~~

Browser sẽ ghi nhận các inline script/style bị policy thử nghiệm vi phạm mà không chặn chỉ vì Report-Only. Quan sát Console hoặc report endpoint để biết thành phần nào còn phụ thuộc inline.

Report-Only không chứng minh policy enforcement sẽ hoạt động hoàn hảo; nó chỉ cung cấp dữ liệu về những hành vi bị policy thử nghiệm coi là vi phạm trong các luồng đã chạy.

### 8.2 Phân loại từng violation

Với mỗi violation, xác định:

- Inline script element do ứng dụng viết hay do bên thứ ba chèn?
- Event handler có thể chuyển sang listener không?
- Script block cố định có thể dùng hash không?
- Script thay đổi theo response có thể dùng nonce không?
- Style attribute có thể thay bằng class không?
- Thư viện cũ có cần cập nhật hoặc thay thế không?
- Violation có đến từ browser extension hoặc công cụ kiểm thử không?

Không tự động thêm nguồn hoặc `unsafe-inline` dựa trên report. Mỗi ngoại lệ cần có lý do, owner và thời hạn loại bỏ.

### 8.3 Chuyển theo từng nhóm route

Một lộ trình migration:

1. Kiểm kê tất cả `onclick`, `onload`, `onerror`, `javascript:` URL, `<script>` inline, `<style>` và `style=`.
2. Chuyển event handler sang `addEventListener`.
3. Chuyển CSS sang file/class; thay dynamic string bằng giá trị được validate.
4. Chọn nonce cho script động theo response hoặc hash cho script cố định.
5. Gửi policy Report-Only và chạy các luồng login, thanh toán, upload, SSO, dashboard.
6. Sửa violation hợp lệ, không allowlist theo thói quen.
7. Bật enforcement cho một nhóm route hoặc staging.
8. Theo dõi lỗi và rollback có kiểm soát nếu chức năng quan trọng bị chặn.
9. Loại bỏ `unsafe-inline` khỏi mọi directive và subdirective.
10. Kiểm tra lại response header cuối cùng ở browser thật.

### 8.4 Tìm inline code trong repository

Có thể tìm dấu hiệu trong source/template:

~~~bash
rg -n -i 'on(click|load|error|change|submit)\s*=|javascript:|style\s*=' src templates public
rg -n '<script|<style' src templates
~~~

Các kết quả cần được review thủ công. Regex không thể xác định đầy đủ HTML parsing context hoặc loại bỏ mọi inline code; template có thể tạo attribute qua helper hoặc framework.

## 9. Tương tác với các lớp bảo vệ khác

### 9.1 Output encoding vẫn bắt buộc

Bỏ `'unsafe-inline'` giúp browser chặn nhiều dạng inline script, nhưng không thay thế output encoding. Dữ liệu không tin cậy vẫn phải được encode theo HTML text/attribute context, validate URL và sanitize nếu cho phép rich HTML.

Không dựa vào CSP để làm sạch dữ liệu trước khi lưu hoặc gửi sang hệ thống khác.

### 9.2 Trusted Types kiểm soát DOM sink

Trusted Types có thể yêu cầu các DOM XSS sink nhận giá trị được tạo qua policy đáng tin cậy:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Cơ chế này giảm việc đưa string tùy ý vào sink như `innerHTML`. Nó không loại bỏ inline handler trong markup bằng cách tự động chuyển chúng thành listener, và không thay việc bỏ `unsafe-inline`.

### 9.3 CSP không chống mọi XSS

Ngay cả policy không có `'unsafe-inline'` vẫn có thể bị khai thác qua script gadget, script nguồn được allowlist nhưng không an toàn, nonce bị lộ/gắn nhầm, hoặc logic tải script động không kiểm soát.

Hãy coi CSP là một lớp giảm khả năng thực thi. Sửa root cause XSS, dùng safe DOM API và review các script có quyền.

### 9.4 Không nhầm CSP nonce với CSRF token

CSP nonce cấp quyền cho script element trong một tài liệu. CSRF token bảo vệ request thay đổi trạng thái. Hai giá trị có mục đích, vòng đời và nơi kiểm tra khác nhau; không tái sử dụng cùng token.

## 10. Thực hành: so sánh unsafe-inline, nonce và strict mode

Bài lab dùng Node.js tích hợp, không cần package ngoài. Nó chạy trên localhost, dùng script/style demo và không gửi request tới website bên ngoài.

### 10.1 Tạo file `unsafe-inline-lab.mjs`

~~~js
import { createServer } from 'node:http';
import { randomBytes } from 'node:crypto';

const mode = process.env.CSP_MODE || 'strict';
const nonce = randomBytes(16).toString('base64');

if (!['strict', 'unsafe', 'nonce', 'report'].includes(mode)) {
  throw new Error('CSP_MODE must be strict, unsafe, nonce or report');
}

const scriptSources = mode === 'unsafe'
  ? "'self' 'unsafe-inline'"
  : mode === 'nonce'
    ? "'self' 'nonce-" + nonce + "' 'unsafe-inline'"
    : "'self'";

const styleSources = mode === 'unsafe'
  ? "'self' 'unsafe-inline'"
  : mode === 'nonce'
    ? "'self' 'nonce-" + nonce + "' 'unsafe-inline'"
    : "'self'";

const scriptAttr = mode === 'unsafe' ? "'unsafe-inline'" : "'none'";
const styleAttr = mode === 'unsafe' ? "'unsafe-inline'" : "'none'";

const policy = [
  "default-src 'none'",
  'script-src ' + scriptSources,
  'script-src-attr ' + scriptAttr,
  'style-src ' + styleSources,
  'style-src-attr ' + styleAttr,
  "img-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
  "frame-ancestors 'none'"
].join('; ');

const nonceAttr = mode === 'nonce' ? ' nonce="' + nonce + '"' : '';

const html = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head>',
  '<meta charset="utf-8">',
  '<title>unsafe-inline CSP lab</title>',
  '<style' + nonceAttr + '>',
  'body { font-family: sans-serif; padding: 2rem; }',
  '.notice { color: green; }',
  '</style>',
  '</head>',
  '<body>',
  '<h1>unsafe-inline lab</h1>',
  '<p id="status" class="notice">Inline script chưa chạy.</p>',
  '<p style="color: purple">Đoạn này dùng style attribute.</p>',
  '<button id="demo" type="button" onclick="document.getElementById(\'status\').textContent=\'Handler chạy\'">',
  'Inline event handler',
  '</button>',
  '<script' + nonceAttr + '>',
  'document.getElementById("status").textContent = "Inline script element chạy.";',
  '</script>',
  '<p>Mode: ' + mode + '</p>',
  '</body>',
  '</html>'
].join('\n');

createServer((req, res) => {
  const headerName = mode === 'report'
    ? 'Content-Security-Policy-Report-Only'
    : 'Content-Security-Policy';

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    [headerName]: policy
  });
  res.end(html);
}).listen(3000, 'localhost', () => {
  console.log('Open http://localhost:3000');
  console.log('CSP mode:', mode);
});
~~~

### 10.2 Chạy strict mode

~~~bash
node unsafe-inline-lab.mjs
~~~

Mặc định mode là `strict`:

- Inline script element không nonce bị chặn.
- Inline event handler bị chặn.
- Style element không nonce và style attribute bị chặn.
- Console hiển thị các CSP violation tương ứng.

### 10.3 Chạy unsafe mode

Dừng server rồi chạy:

~~~bash
CSP_MODE=unsafe node unsafe-inline-lab.mjs
~~~

Trên PowerShell:

~~~powershell
$env:CSP_MODE = "unsafe"
node unsafe-inline-lab.mjs
~~~

Trong mode này, policy có `unsafe-inline` cho script và style. Quan sát script element, event handler và style attribute hoạt động. Các directive khác như `object-src`, `base-uri` và `frame-ancestors` vẫn có hiệu lực.

### 10.4 Chạy nonce mode

~~~bash
CSP_MODE=nonce node unsafe-inline-lab.mjs
~~~

Trên PowerShell:

~~~powershell
$env:CSP_MODE = "nonce"
node unsafe-inline-lab.mjs
~~~

Trong browser hỗ trợ CSP2+, inline script/style element có nonce khớp được phép; event handler và style attribute vẫn bị chặn do directive `*-src-attr 'none'`. `unsafe-inline` trong source list có nonce/hash bị bỏ qua theo quy tắc CSP2+; đây là minh họa cho khả năng tương thích, không phải policy khuyến nghị để giữ lâu dài.

### 10.5 Chạy Report-Only mode

~~~bash
CSP_MODE=report node unsafe-inline-lab.mjs
~~~

Trên PowerShell:

~~~powershell
$env:CSP_MODE = "report"
node unsafe-inline-lab.mjs
~~~

Browser ghi nhận violation nhưng không chặn chỉ vì policy Report-Only. Vì mode này không cấp nonce cho inline script, inline script có thể chạy trong khi console vẫn ghi nhận vi phạm.

Sau lab, dừng server và đóng trang localhost.

## 11. Chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Inline script vẫn chạy dù có CSP | Policy chứa `unsafe-inline`, hoặc browser không áp dụng policy dự kiến | Kiểm tra response header và các CSP policy khác |
| Inline handler chạy dù script element bị chặn | `script-src-attr` mở `unsafe-inline` hoặc policy fallback cho phép | Đặt `script-src-attr 'none'`, thay handler bằng listener |
| Style attribute vẫn được áp dụng | `style-src-attr` hoặc fallback cho phép inline style | Chuyển sang class hoặc đặt `style-src-attr 'none'` |
| Nonce script bị chặn | Nonce không khớp header/body hoặc response cache sai | Tạo nonce per-response và gắn đồng bộ |
| Nonce script chạy nhưng onclick bị chặn | Hành vi mong đợi: nonce không cấp quyền cho event handler | Dùng `addEventListener` |
| `unsafe-inline` vẫn có trong header nhưng inline bị chặn | Nonce/hash trong cùng directive khiến keyword bị bỏ qua ở browser CSP2+ | Kiểm tra browser support và directive chuyên biệt |
| Browser cũ cho inline script chạy | Browser không hiểu nonce/hash và áp dụng unsafe-inline fallback | Đánh giá support policy; bỏ fallback nếu cần bảo vệ browser đó |
| Thêm nonce nhưng CSS attribute vẫn chạy | Style attribute được mở bởi directive riêng hoặc fallback | Kiểm tra `style-src-attr` và `style-src` |
| Xóa unsafe-inline nhưng framework lỗi | Framework tạo inline handler/style hoặc script block | Cập nhật cấu hình/build, chuyển sang external resource hoặc nonce |
| Report-Only vẫn cho inline code chạy | Đây là hành vi mong đợi | Sửa violation rồi chuyển policy sang enforcement |
| CSP không ngăn được XSS | Script gadget/allowlisted source/nonce misuse hoặc sink khác | Sửa root cause, thu hẹp source và dùng safe DOM API |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `script-src 'unsafe-inline'` cho phép những dạng nội dung nào?

**Đáp án:** Nó cho phép inline script element, inline event handler và URL `javascript:` trong những ngữ cảnh browser hỗ trợ; nguồn script bên ngoài vẫn phải thỏa các nguồn được phép khác.

**Câu 2.** `style-src 'unsafe-inline'` có cho phép JavaScript chạy không?

**Đáp án:** Không. Nó cho phép inline CSS như style element/attribute theo policy, không phải quyền thực thi JavaScript. Tuy nhiên CSS injection vẫn có thể làm sai lệch giao diện hoặc trạng thái người dùng nhìn thấy.

**Câu 3.** `unsafe-inline` khác `unsafe-eval` như thế nào?

**Đáp án:** `unsafe-inline` mở quyền inline script/style theo directive; `unsafe-eval` mở các API đánh giá/biên dịch code từ chuỗi như eval hoặc new Function. Chúng là hai ngoại lệ khác nhau.

**Câu 4.** Nếu `script-src` có cả `unsafe-inline` và nonce hợp lệ, browser CSP2+ xử lý ra sao?

**Đáp án:** Nonce/hash source khiến `unsafe-inline` trong cùng source list bị bỏ qua theo quy tắc CSP2+. Browser cũ không hỗ trợ nonce có thể vẫn áp dụng `unsafe-inline`.

**Câu 5.** Nonce trên thẻ `<script>` có cho phép `onclick` không?

**Đáp án:** Không. Nonce cấp quyền cho script element, không cấp quyền cho event handler attribute. Dùng `script-src-attr 'none'` và `addEventListener`.

**Câu 6.** Hash của inline script element có tự cho phép event handler không?

**Đáp án:** Không. Handler là một ngữ cảnh riêng. `unsafe-hashes` có thể cho phép hash khớp handler trong trường hợp legacy hẹp, nhưng nên chuyển handler sang listener.

**Câu 7.** Vì sao nên bỏ `style-src 'unsafe-inline'` dù nó không trực tiếp bật JavaScript?

**Đáp án:** CSS không tin cậy có thể thay đổi giao diện, che nội dung hoặc control, tạo UI redress và làm người dùng hiểu sai trạng thái. Hãy dùng class/stylesheet và kiểm soát CSS động.

**Câu 8.** `script-src-attr 'none'` có vai trò gì?

**Đáp án:** Chặn inline event handler attributes như onclick, kể cả khi script element được cấp quyền riêng bằng nonce/hash.

**Câu 9.** Report-Only có chặn inline script vi phạm không?

**Đáp án:** Không. Nó ghi nhận violation để đánh giá policy; enforcement header mới thực sự chặn.

**Câu 10.** Bỏ `unsafe-inline` có đủ để tuyên bố ứng dụng không còn XSS không?

**Đáp án:** Không. CSP có thể giảm khả năng thực thi nhưng vẫn có script gadget, nguồn được allowlist không an toàn, nonce misuse hoặc DOM sink khác. Cần output encoding, sanitizer, safe DOM API và sửa root cause.

## 13. Checklist loại bỏ unsafe-inline

Trước khi gỡ ngoại lệ khỏi CSP, hãy kiểm tra:

1. **Inventory script:** đã tìm inline `<script>`, event handler `on*` và URL `javascript:` chưa?
2. **Inventory style:** đã tìm `<style>`, `style=` và thư viện sinh inline CSS chưa?
3. **Directive chuyên biệt:** đã kiểm tra `script-src-elem`, `script-src-attr`, `style-src-elem`, `style-src-attr` chưa?
4. **Externalize:** chuyển event handler sang `addEventListener` và stylesheet sang file/class.
5. **Nonce/hash:** chọn nonce cho nội dung theo response, hash cho nội dung cố định.
6. **Legacy:** nếu dùng `unsafe-hashes`, giới hạn hash, ghi rõ lý do và thời hạn loại bỏ.
7. **CSP2/CSP3:** hiểu cách browser hỗ trợ nonce/hash và fallback; không coi policy lai là strict cho mọi browser.
8. **Report-Only:** thu thập violation trên các luồng thực tế trước enforcement.
9. **Enforcement:** bật theo route/staging, theo dõi lỗi và có rollback.
10. **No accidental reopening:** không để directive `*-src-attr` mở lại inline sau khi `script-src` đã được siết.
11. **Other defenses:** vẫn dùng output encoding, URL validation, sanitizer, Trusted Types và CSRF protection.
12. **Review:** xác minh response header cuối cùng trên browser mục tiêu và loại bỏ ngoại lệ không còn cần.

**Ghi nhớ:** `unsafe-inline` làm browser tin mọi inline script/style thuộc directive tương ứng. Với script, điều đó làm yếu trực tiếp khả năng CSP ngăn XSS; với style, nó mở đường cho CSS injection và thao túng giao diện. Hãy thay inline handler bằng listener, thay style attribute bằng class, dùng nonce/hash cho phần tử thực sự cần inline và kiểm tra cả các directive CSP3 chuyên biệt.

## Tài liệu tham khảo

- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
- [W3C — Content Security Policy Level 2](https://www.w3.org/TR/CSP2/)
- [MDN — Content-Security-Policy: script-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src)
- [MDN — Content-Security-Policy: style-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/style-src)
- [MDN — CSP: script-src-attr](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src-attr)
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [Google web.dev — Strict CSP](https://web.dev/articles/strict-csp)

