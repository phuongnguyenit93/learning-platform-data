# Clipboard API: đọc, ghi và bảo vệ dữ liệu trong system clipboard

> **Chương:** Permissions  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Clipboard là vùng dữ liệu tạm thời do hệ điều hành quản lý, cho phép người dùng chuyển văn bản, hình ảnh hoặc nội dung có định dạng giữa các ứng dụng. Website có thể tham gia vào luồng này bằng hai nhóm API: **Clipboard Event API** xử lý thao tác copy/cut/paste do người dùng khởi tạo; **Async Clipboard API** cho phép JavaScript đọc hoặc ghi clipboard thông qua các Promise.

Clipboard chứa dữ liệu có thể rất nhạy cảm như mật khẩu, mã xác thực, địa chỉ, token, đoạn lệnh hoặc thông tin khách hàng. Vì vậy, browser áp dụng secure context, user activation, permission hoặc prompt tùy trường hợp. Một trang không nên tự đọc clipboard khi vừa tải hoặc âm thầm thay nội dung người dùng đang copy.

Bài này giải thích hai nhóm API, cách đọc/ghi text và dữ liệu đa định dạng, khác biệt permission giữa các browser, cách xử lý nội dung paste an toàn, chính sách cho iframe và cách kiểm chứng bằng một ứng dụng Node.js chạy trên localhost.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt Clipboard Event API với Async Clipboard API.
2. Dùng navigator.clipboard.readText() và writeText() cho dữ liệu text.
3. Dùng ClipboardItem, read() và write() cho HTML, text và ảnh khi browser hỗ trợ.
4. Xử lý copy, cut và paste bằng ClipboardEvent.clipboardData.
5. Giải thích yêu cầu secure context, focus, user activation và permission.
6. Hiểu vì sao Permissions API không cung cấp cùng một mô hình clipboard permission trên mọi browser.
7. Delegate clipboard-read và clipboard-write cho iframe khi cần và khi browser hỗ trợ.
8. Xử lý HTML paste như dữ liệu không tin cậy, tránh DOM XSS.
9. Nhận diện clipboard poisoning, pastejacking và nguy cơ rò rỉ dữ liệu.
10. Kiểm tra hỗ trợ API, xử lý lỗi và thiết kế fallback hợp lý.

## 1. Clipboard và hai nhóm API

### 1.1 System clipboard là gì?

System clipboard là vùng dữ liệu tạm do hệ điều hành cung cấp. Người dùng có thể copy từ một ứng dụng, chuyển sang ứng dụng khác rồi paste. Một clipboard item có thể có nhiều representation của cùng nội dung, ví dụ:

- text/plain: nội dung văn bản thuần.
- text/html: nội dung HTML có định dạng.
- image/png: dữ liệu ảnh PNG.
- Một số MIME type hoặc custom format khác tùy browser và hệ điều hành.

Một bảng trong trình soạn thảo có thể được copy đồng thời thành HTML table và văn bản tab-separated. Ứng dụng nhận dữ liệu có thể chọn representation mà nó hiểu.

### 1.2 Clipboard Event API

Các event chính:

- copy: người dùng thực hiện thao tác sao chép.
- cut: người dùng cắt nội dung được chọn.
- paste: người dùng dán dữ liệu vào trang.
- clipboardchange: thông báo clipboard thay đổi trong các browser hỗ trợ.

Trong event handler, thuộc tính clipboardData cung cấp DataTransfer để đọc hoặc ghi representation phù hợp. Ví dụ, copy event có thể đặt text/plain hoặc text/html rồi gọi preventDefault() để thay hành vi mặc định.

Clipboard Event API gắn với thao tác người dùng. Nó không phải một API để trang tự do đọc clipboard vào bất kỳ thời điểm nào.

### 1.3 Async Clipboard API

Async Clipboard API truy cập clipboard qua navigator.clipboard:

~~~js
await navigator.clipboard.writeText('Nội dung được sao chép');
const text = await navigator.clipboard.readText();
~~~

Các method thường dùng:

| Method | Mục đích |
|---|---|
| navigator.clipboard.writeText(text) | Ghi văn bản thuần |
| navigator.clipboard.readText() | Đọc representation văn bản |
| navigator.clipboard.write(items) | Ghi một hoặc nhiều ClipboardItem |
| navigator.clipboard.read() | Đọc các ClipboardItem và representation |

Các method trả Promise vì thao tác với system clipboard là bất đồng bộ và có thể cần kiểm tra quyền hoặc chờ browser/OS.

### 1.4 Không dùng execCommand cho code mới

document.execCommand('copy') và document.execCommand('paste') là các cơ chế cũ, đã deprecated. Chúng có hành vi khác nhau giữa browser và không phải lựa chọn chính cho ứng dụng mới.

Ưu tiên Async Clipboard API cho thao tác bất đồng bộ. Dùng Clipboard Event API khi cần tùy biến dữ liệu gắn với hành động copy/cut/paste thực sự của người dùng.

Async Clipboard API được expose trên Navigator của document, không được expose qua WorkerNavigator. Worker không thể gọi navigator.clipboard trực tiếp; nếu ứng dụng cần clipboard, hãy xử lý ở window context sau thao tác người dùng.

## 2. Điều kiện bảo mật khi truy cập clipboard

### 2.1 Secure context

Async Clipboard API chỉ được cung cấp trong secure context. Trong production, hãy dùng HTTPS với chứng chỉ hợp lệ.

Các origin localhost/loopback thường được browser xem là potentially trustworthy để phục vụ phát triển. Vì vậy, lab trên localhost có thể sử dụng Clipboard API dù không cấu hình chứng chỉ TLS. Không suy rộng ngoại lệ này sang hostname nội bộ hoặc địa chỉ LAN chạy HTTP.

Kiểm tra:

~~~js
if (!window.isSecureContext) {
  console.warn('Trang không ở secure context.');
}

if (!navigator.clipboard) {
  console.warn('Async Clipboard API không khả dụng.');
}
~~~

Secure context là điều kiện cần, không đồng nghĩa browser đã cho phép thao tác.

### 2.2 User activation

Browser thường yêu cầu thao tác trực tiếp của người dùng, đặc biệt với clipboard read. Ví dụ phù hợp là gọi readText() bên trong handler của nút Paste mà người dùng vừa bấm.

~~~js
pasteButton.addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    output.textContent = text;
  } catch (error) {
    output.textContent = 'Không thể đọc clipboard: ' + error.name;
  }
});
~~~

Không trì hoãn thao tác clipboard qua nhiều bước bất đồng bộ trước khi gọi API. Transient user activation có thời hạn ngắn và có thể mất trước khi browser kiểm tra quyền.

Đối với ghi clipboard, nhiều browser cũng yêu cầu user activation. Chromium có thể cho phép ghi sau khi permission đã được cấp; Firefox và Safari thường yêu cầu thao tác người dùng cho mỗi lần ghi.

### 2.3 Focus và trạng thái document

Async Clipboard API thường yêu cầu document đang được focus. Một tab chạy nền không nên được xem là có quyền đọc clipboard tùy ý.

Nếu thao tác bị từ chối, kiểm tra:

- Trang có đang ở secure context không?
- Tab/document có đang focus không?
- API có được gọi trực tiếp từ thao tác người dùng không?
- Browser có yêu cầu prompt hoặc permission riêng không?
- Iframe có được delegate clipboard feature không?
- Người dùng đã từ chối quyền hoặc browser policy có chặn không?

### 2.4 Permissions API không đồng nhất giữa browser

Không giả định mọi browser đều hỗ trợ cùng tên permission hoặc cùng luồng prompt:

| Browser family | Clipboard read | Clipboard write |
|---|---|---|
| Chromium | Có thể dùng permission clipboard-read và prompt khi cần; thường cần document focus | Có thể dựa vào clipboard-write permission hoặc transient activation |
| Firefox | Thường dựa vào transient activation và prompt paste tạm thời của browser | Thường cần transient activation |
| Safari | Thường dựa vào transient activation và prompt paste tạm thời của browser | Thường cần transient activation |

Các chi tiết có thể thay đổi theo phiên bản, cấu hình và nền tảng. Firefox/Safari không triển khai các descriptor clipboard-read và clipboard-write theo mô hình Chromium được MDN mô tả. Bản Working Draft W3C hiện tại cũng đang điều chỉnh mô hình permission; không coi tên permission của một browser là hợp đồng tương thích chung.

Có thể thử query permission trên browser hỗ trợ:

~~~js
async function inspectClipboardPermission(name) {
  if (!navigator.permissions?.query) {
    return 'Permissions API không khả dụng';
  }

  try {
    const result = await navigator.permissions.query({ name });
    return result.state;
  } catch {
    return 'Browser không hỗ trợ query permission này';
  }
}

const readState = await inspectClipboardPermission('clipboard-read');
const writeState = await inspectClipboardPermission('clipboard-write');

console.log({ readState, writeState });
~~~

Query có thể bị từ chối vì browser không nhận diện descriptor. Hãy xử lý bằng try/catch và thực hiện thao tác trong user gesture; đừng khóa chức năng chỉ vì query permission không thành công.

### 2.5 Clipboard permissions và iframe

Trong Chromium, iframe truy cập clipboard có thể cần Permissions Policy cho clipboard-read và clipboard-write. Header của trang cha có thể giới hạn origin được delegate:

~~~http
Permissions-Policy: clipboard-read=(self "https://editor.example"), clipboard-write=(self "https://editor.example")
~~~

Iframe có thể khai báo:

~~~html
<iframe
  src="https://editor.example/embed"
  title="Trình soạn thảo"
  allow="clipboard-read; clipboard-write">
</iframe>
~~~

Trong HTML allow attribute, tên feature không có allowlist tường minh thường dùng origin của src. Header phía trên vẫn là giới hạn tối đa; iframe không thể tự bật feature mà ancestor đã chặn.

Permissions Policy và cú pháp iframe allow có mức hỗ trợ khác nhau giữa browser. Hãy kiểm thử trên browser mục tiêu. Cấu hình này cũng không thay thế secure context, user activation hoặc permission prompt.

## 3. Ghi văn bản với writeText()

### 3.1 Ví dụ cơ bản

~~~html
<button id="copy" type="button">Copy mã tham chiếu</button>
<p id="status" aria-live="polite"></p>
~~~

~~~js
const copyButton = document.querySelector('#copy');
const status = document.querySelector('#status');

copyButton.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText('ORDER-2026-0042');
    status.textContent = 'Đã sao chép mã tham chiếu.';
  } catch (error) {
    status.textContent = 'Sao chép thất bại: ' + error.name;
  }
});
~~~

Promise hoàn tất khi browser đã cập nhật clipboard. Chỉ hiển thị thông báo thành công sau khi await hoàn tất.

### 3.2 Không báo thành công trước khi API hoàn tất

Tránh:

~~~js
navigator.clipboard.writeText(value);
status.textContent = 'Đã sao chép';
~~~

Promise có thể reject vì NotAllowedError, document không focus, browser policy hoặc lỗi hệ điều hành. Cách đúng là await và xử lý lỗi.

### 3.3 Fallback khi API không khả dụng

Nếu Async Clipboard API không có, ứng dụng có thể cung cấp nút chọn nội dung để người dùng copy bằng phím tắt hoặc menu browser. Không cần gọi execCommand chỉ để cố tự động hóa mọi browser.

~~~js
if (!navigator.clipboard?.writeText) {
  status.textContent = 'Hãy chọn nội dung và dùng Ctrl+C hoặc Cmd+C.';
}
~~~

Fallback nên giữ người dùng chủ động và không âm thầm thay đổi clipboard.

## 4. Đọc văn bản với readText()

### 4.1 Chỉ đọc khi người dùng yêu cầu

~~~html
<button id="paste" type="button">Dán nội dung clipboard</button>
<textarea id="destination" rows="4"></textarea>
<p id="paste-status" aria-live="polite"></p>
~~~

~~~js
const pasteButton = document.querySelector('#paste');
const destination = document.querySelector('#destination');
const pasteStatus = document.querySelector('#paste-status');

pasteButton.addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    destination.value = text;
    pasteStatus.textContent = text
      ? 'Đã đọc nội dung văn bản.'
      : 'Clipboard không có văn bản.';
  } catch (error) {
    pasteStatus.textContent = 'Không thể đọc clipboard: ' + error.name;
  }
});
~~~

Đây là hành động nhạy cảm vì clipboard có thể chứa mật khẩu, token hoặc dữ liệu cá nhân. Nút cần mô tả rõ chức năng và chỉ đọc khi người dùng yêu cầu.

### 4.2 Kết quả rỗng không nhất thiết là lỗi

readText() có thể trả chuỗi rỗng khi clipboard trống hoặc không có representation text mà browser có thể trả về. Hãy phân biệt chuỗi rỗng với Promise reject.

### 4.3 NotAllowedError

NotAllowedError thường có nghĩa browser không cho phép thao tác tại thời điểm đó. Nguyên nhân có thể gồm:

- Người dùng từ chối prompt.
- Thiếu user activation.
- Document không focus.
- Browser không cho phép clipboard read trong context hiện tại.
- Iframe chưa được delegate feature.
- Quyền bị chặn bởi policy của browser hoặc hệ điều hành.

Không thử lặp readText() liên tục để ép prompt. Hiển thị hướng dẫn rõ ràng và cho người dùng dùng paste mặc định của browser nếu phù hợp.

## 5. Đọc và ghi nhiều định dạng với ClipboardItem

### 5.1 Một item có thể có nhiều representation

ClipboardItem có thể chứa nhiều định dạng của cùng nội dung. Ví dụ, một ứng dụng có thể ghi HTML có định dạng cùng plain text fallback:

~~~js
const html = '<strong>Thông báo</strong><p>Đơn hàng đã được xác nhận.</p>';
const plain = 'Thông báo\nĐơn hàng đã được xác nhận.';

const item = new ClipboardItem({
  'text/html': new Blob([html], { type: 'text/html' }),
  'text/plain': new Blob([plain], { type: 'text/plain' })
});

await navigator.clipboard.write([item]);
~~~

Ứng dụng nhận có thể chọn HTML để giữ định dạng hoặc plain text nếu không hỗ trợ HTML.

HTML ghi vào clipboard cần được tạo từ nội dung đáng tin cậy hoặc sanitize trước. Không nối trực tiếp dữ liệu người dùng vào HTML string rồi đưa lên clipboard.

### 5.2 Đọc các representation

~~~js
const items = await navigator.clipboard.read();

for (const item of items) {
  console.log('Các định dạng:', item.types);

  if (item.types.includes('text/plain')) {
    const blob = await item.getType('text/plain');
    const text = await blob.text();
    console.log('Plain text:', text);
  }

  if (item.types.includes('text/html')) {
    const blob = await item.getType('text/html');
    const html = await blob.text();

    // Chỉ xem như dữ liệu không tin cậy.
    console.log('HTML từ clipboard:', html);
  }
}
~~~

Không đưa HTML lấy từ clipboard thẳng vào innerHTML. Dùng textContent nếu chỉ cần hiển thị text; nếu cần rich HTML, sanitize bằng thư viện chuyên dụng và áp dụng allowlist phần tử/attribute.

### 5.3 Kiểm tra hỗ trợ format

Các định dạng phổ biến được browser hỗ trợ gồm text/plain, text/html và image/png. Một số format khác như SVG hoặc custom format có hỗ trợ khác nhau.

Có thể kiểm tra trước:

~~~js
if (typeof ClipboardItem !== 'undefined' &&
    ClipboardItem.supports?.('image/png')) {
  console.log('Browser hỗ trợ image/png trong ClipboardItem.');
}
~~~

Một số hệ điều hành/browser chỉ cho ghi một ClipboardItem trong một lần write(). Không giả định mọi nền tảng đều giữ nhiều item hoặc custom format giống nhau.

### 5.4 Ghi ảnh PNG

Nếu đã có Blob ảnh PNG:

~~~js
async function copyPng(blob) {
  if (!ClipboardItem.supports('image/png')) {
    throw new Error('Browser không hỗ trợ ghi image/png.');
  }

  const item = new ClipboardItem({
    'image/png': blob
  });

  await navigator.clipboard.write([item]);
}
~~~

Blob phải có MIME type đúng. Không đọc file hoặc URL không tin cậy rồi ghi vào clipboard mà không kiểm tra nguồn, kích thước và nội dung.

### 5.5 Custom format

ClipboardItem hỗ trợ custom web format trong một số browser, thường dùng tên MIME có tiền tố web. Đây là tính năng nâng cao, hỗ trợ chưa đồng đều và có thể không được ứng dụng desktop khác hiểu.

Luôn cung cấp representation tiêu chuẩn như text/plain hoặc text/html làm fallback. Không dùng custom format làm định dạng duy nhất nếu người dùng cần copy sang ứng dụng khác.

## 6. Clipboard Event API: copy, cut và paste

### 6.1 Đọc dữ liệu trong paste event

ClipboardEvent.clipboardData là DataTransfer có sẵn trong handler:

~~~js
document.querySelector('#editor').addEventListener('paste', event => {
  const text = event.clipboardData.getData('text/plain');
  console.log('Người dùng đang paste:', text);
});
~~~

Sự kiện được phát sinh khi người dùng thực hiện thao tác paste. Không giữ reference clipboardData để dùng sau handler; dữ liệu và quyền truy cập gắn với event context.

Synthetic event do JavaScript tự tạo không cung cấp quyền đọc system clipboard thật.

### 6.2 Tùy biến nội dung copy

~~~js
document.querySelector('#editor').addEventListener('copy', event => {
  const editor = event.currentTarget;
  const start = editor.selectionStart;
  const end = editor.selectionEnd;
  const selected = editor.value.slice(start, end);

  if (!selected) return;

  event.clipboardData.setData('text/plain', selected);
  event.preventDefault();
});
~~~

Khi gọi preventDefault(), handler hủy hành vi copy mặc định và dữ liệu do handler đặt sẽ được dùng. Nếu không hủy event, browser tiếp tục copy selection mặc định.

Không âm thầm thay link hoặc text người dùng đang copy bằng nội dung khác. Nếu ứng dụng bổ sung nguồn trích dẫn hoặc metadata, hãy thông báo điều đó rõ ràng.

### 6.3 Tùy biến paste vào textarea

~~~js
const editor = document.querySelector('#editor');

editor.addEventListener('paste', event => {
  const text = event.clipboardData.getData('text/plain');

  if (text === '') return;

  event.preventDefault();

  const start = editor.selectionStart;
  const end = editor.selectionEnd;

  editor.setRangeText(text, start, end, 'end');
});
~~~

Ví dụ này chỉ chèn plain text vào textarea. setRangeText() giữ dữ liệu ở dạng text, tránh parse nội dung clipboard như HTML.

Nếu không cần tùy biến, hãy để browser xử lý paste mặc định vào input/textarea. Không chặn event chỉ để đọc dữ liệu nếu ứng dụng không có mục tiêu rõ ràng.

### 6.4 Cut event

cut event cho phép tùy biến dữ liệu được ghi vào clipboard. Nếu handler gọi preventDefault(), browser sẽ không tự xóa selection khỏi document; ứng dụng phải tự cập nhật nội dung nếu muốn giữ semantics của thao tác cut.

Đây là khác biệt quan trọng giữa copy và cut: cut vừa cập nhật clipboard vừa thay đổi tài liệu đang chỉnh sửa.

### 6.5 clipboardchange

Một số browser hỗ trợ event clipboardchange trên navigator.clipboard để thông báo clipboard đã thay đổi. Event này có thể chịu điều kiện activation/permission và không được hỗ trợ đồng đều.

Không dùng clipboardchange để theo dõi clipboard người dùng liên tục hoặc đồng bộ dữ liệu ra server khi chưa có yêu cầu rõ ràng. Đây là vùng dữ liệu nhạy cảm và cần sự chủ động của người dùng.

## 7. Bảo vệ ứng dụng khi paste dữ liệu

### 7.1 Clipboard là input không tin cậy

Dữ liệu clipboard có thể đến từ website khác, ứng dụng desktop, tài liệu tải về hoặc một chương trình độc hại. Không giả định dữ liệu đã được browser làm sạch hoàn toàn.

Clipboard có thể chứa:

- HTML với link hoặc attribute nguy hiểm.
- Text ẩn hoặc comment chứa dữ liệu không mong muốn.
- URL có scheme không an toàn.
- Lệnh shell hoặc đoạn script người dùng có thể vô tình chạy.
- Hình ảnh hoặc file có kích thước lớn.
- Nội dung chứa token hoặc dữ liệu cá nhân.

### 7.2 Không gán clipboard text vào innerHTML

Sai:

~~~js
const text = await navigator.clipboard.readText();
container.innerHTML = text;
~~~

Đúng nếu chỉ hiển thị văn bản:

~~~js
const text = await navigator.clipboard.readText();
container.textContent = text;
~~~

textContent tạo text node và không diễn giải nội dung như HTML. Nếu ứng dụng cần rich text, dùng sanitizer đáng tin cậy như DOMPurify, giới hạn element/attribute được phép rồi mới tạo DOM.

### 7.3 Sanitize HTML paste theo allowlist

Một trình soạn thảo rich text có thể cho phép một tập nhỏ:

- p, br, strong, em.
- ul, ol, li.
- a với href đã validate.
- Các heading được hỗ trợ.
- Một số bảng và cấu trúc cần thiết.

Loại bỏ script, event handler attributes, javascript: URL, iframe, object, embed và style không được kiểm soát. Kiểm tra URL sau khi parse và chỉ cho phép scheme phù hợp như https: hoặc mailto: theo nghiệp vụ.

Sanitizer cần được cập nhật và cấu hình đúng. Regex tự viết không phải HTML sanitizer an toàn.

### 7.4 HTML clipboard có thể được browser sanitize

Browser có thể sanitize HTML khi đọc clipboard, ví dụ loại bỏ script hoặc nội dung nguy hiểm. Tuy nhiên, mức sanitize khác nhau giữa browser. Không dựa vào việc browser đã sanitize để bỏ qua xử lý đầu vào ở ứng dụng.

Một số API có tùy chọn yêu cầu đọc representation unsanitized ở browser hỗ trợ. Không dùng tùy chọn đó trừ khi có lý do kỹ thuật rõ ràng; nếu dùng, dữ liệu cần được xử lý như input nguy hiểm.

### 7.5 Kiểm tra URL và dữ liệu có cấu trúc

Khi paste URL:

~~~js
function isAllowedLink(value) {
  try {
    const url = new URL(value);
    return ['https:', 'mailto:'].includes(url.protocol);
  } catch {
    return false;
  }
}
~~~

Không chỉ kiểm tra chuỗi bắt đầu bằng https vì URL có thể chứa ký tự điều khiển, username/password hoặc cách viết đánh lừa. Parse bằng URL rồi kiểm tra protocol và hostname theo yêu cầu ứng dụng.

Khi paste CSV/JSON, kiểm tra kích thước, cấu trúc và kiểu dữ liệu trước khi lưu hoặc thực thi thao tác nghiệp vụ.

## 8. Các rủi ro clipboard thường gặp

### 8.1 Clipboard poisoning

Clipboard poisoning xảy ra khi website hoặc script thay nội dung mà người dùng nghĩ họ đã copy. Ví dụ, người dùng chọn địa chỉ ví hoặc lệnh an toàn nhưng trang thay bằng địa chỉ khác.

Biện pháp:

- Không thay nội dung copy âm thầm.
- Chỉ bổ sung metadata khi có thông báo.
- Với thông tin thanh toán, hiển thị lại giá trị cuối cùng trước khi xác nhận.
- Không coi clipboard là kênh xác thực địa chỉ hoặc lệnh.

### 8.2 Pastejacking

Pastejacking là kỹ thuật khiến người dùng copy nội dung nhìn thấy nhưng clipboard thực tế chứa lệnh khác, có thể gồm ký tự xuống dòng hoặc phần bổ sung bị ẩn. Khi người dùng paste vào terminal, shell hoặc công cụ quản trị, lệnh có thể được thực thi ngoài ý muốn.

Ứng dụng nên tránh thay đổi clipboard theo cách khó nhận biết. Người dùng cũng cần kiểm tra nội dung lệnh sau khi paste trước khi thực thi.

### 8.3 Clipboard data exfiltration

Nếu trang đọc clipboard tự động rồi gửi lên server, nó có thể làm rò rỉ mật khẩu, token, mã OTP hoặc dữ liệu khách hàng.

Thiết kế an toàn:

- Chỉ đọc khi người dùng nhấn nút hoặc chọn Paste.
- Hiển thị mục đích đọc dữ liệu.
- Không ghi clipboard content vào log hoặc analytics.
- Không gửi nội dung lên server trừ khi chức năng yêu cầu rõ và người dùng xác nhận.
- Xóa dữ liệu nhạy cảm khỏi state/UI khi không còn cần.
- Không giữ clipboard content lâu hơn thời gian xử lý.

### 8.4 Clipboard không phải storage an toàn

Clipboard là vùng chia sẻ giữa nhiều ứng dụng. Bất kỳ ứng dụng nào có quyền phù hợp trên hệ điều hành có thể thay đổi nội dung. Không lưu secret dài hạn, session token hoặc thông tin xác thực vào clipboard nếu không cần thiết.

Nếu phải copy secret cho người dùng, thông báo rõ rằng nội dung đã được đưa vào clipboard và có thể vẫn tồn tại sau khi người dùng rời trang.

### 8.5 Giới hạn kích thước và định dạng

Không ghi dữ liệu không giới hạn vào clipboard. Nội dung quá lớn có thể gây treo browser hoặc ứng dụng nhận. Giới hạn kích thước, kiểm tra MIME type và xử lý lỗi khi browser/OS không hỗ trợ định dạng.

## 9. Permissions Policy, iframe và ranh giới origin

### 9.1 Iframe cần được delegate

Một iframe có thể cần đọc hoặc ghi clipboard để cung cấp editor, bảng tính hoặc widget copy/paste. Trong browser hỗ trợ, trang cha có thể giới hạn bằng Permissions-Policy header và allow attribute.

Ví dụ:

~~~http
Permissions-Policy: clipboard-read=(self "https://editor.example"), clipboard-write=(self "https://editor.example")
~~~

~~~html
<iframe
  src="https://editor.example/embed"
  allow="clipboard-read; clipboard-write"
  title="Editor">
</iframe>
~~~

Header đặt giới hạn ở cấp document; allow attribute delegate feature cho iframe. Nếu ancestor đã tắt feature, iframe không thể tự bật lại.

### 9.2 Cross-origin không có nghĩa được đọc clipboard tự do

SOP vẫn kiểm soát truy cập DOM giữa các origin. Clipboard permission là một cơ chế riêng: trang được phép dùng Clipboard API vẫn không tự động được đọc DOM của trang khác.

Một iframe cross-origin có thể nhận clipboard feature nếu browser, Permissions Policy và user permission cho phép. Nó vẫn không được quyền đọc mọi dữ liệu của parent document.

### 9.3 Không nhầm Clipboard API với postMessage

postMessage trao đổi dữ liệu giữa browsing context. Clipboard API đọc/ghi system clipboard. Nếu parent và child chỉ cần trao đổi dữ liệu ứng dụng, ưu tiên postMessage với targetOrigin cụ thể và kiểm tra event.origin thay vì dùng clipboard làm kênh trung gian.

## 10. Xử lý lỗi và thiết kế UX

### 10.1 Các lỗi thường gặp

| Lỗi | Ý nghĩa có thể | Cách xử lý |
|---|---|---|
| NotAllowedError | Browser không cho phép đọc/ghi tại thời điểm gọi | Kiểm tra user activation, permission, focus và iframe policy |
| NotFoundError | Không có representation được yêu cầu | Kiểm tra item.types trước khi getType |
| navigator.clipboard undefined | Không phải secure context hoặc API không được hỗ trợ | Dùng HTTPS/localhost và feature detection |
| ClipboardItem undefined | Browser không hỗ trợ rich clipboard API | Dùng readText/writeText hoặc fallback thủ công |
| readText trả chuỗi rỗng | Clipboard trống hoặc không có text representation | Hiển thị trạng thái không có văn bản |
| write() thất bại với nhiều item | Nền tảng chỉ hỗ trợ một ClipboardItem | Gộp các representation vào một item |
| Permission query reject | Browser không hỗ trợ descriptor đó | Không coi query là điều kiện bắt buộc; gọi API trong user gesture |
| Iframe bị từ chối | Permissions Policy chưa delegate hoặc ancestor đã chặn | Kiểm tra header và allow attribute |

### 10.2 Thông báo rõ ràng

Thông báo nên nói hành động nào thất bại và người dùng có thể làm gì tiếp theo:

- “Không thể đọc clipboard. Hãy dùng Ctrl+V hoặc Cmd+V trong ô nhập.”
- “Browser đã từ chối quyền truy cập clipboard.”
- “Định dạng ảnh này chưa được browser hỗ trợ.”
- “Đã sao chép văn bản.”

Tránh thông báo mơ hồ như “Lỗi hệ thống” khi có thể hiển thị nguyên nhân phù hợp.

### 10.3 Không xin quyền quá sớm

Không hỏi quyền clipboard ngay khi người dùng mở trang nếu chức năng chỉ cần copy sau một thao tác. Hãy gọi API khi người dùng nhấn nút tương ứng. Quyền được yêu cầu đúng thời điểm giúp người dùng hiểu lý do browser hiển thị prompt.

## 11. Thực hành: xây dựng Clipboard API lab với Node.js

Lab tạo một trang local có nút copy, paste, ghi HTML/text đa định dạng và đọc danh sách MIME type. Dùng localhost để đáp ứng secure-context requirement trong môi trường phát triển. Clipboard thật của hệ điều hành sẽ bị thay đổi khi bấm Copy; hãy chỉ dùng dữ liệu demo.

### 11.1 Tạo cấu trúc

~~~text
clipboard-lab/
  server.mjs
~~~

### 11.2 Tạo file server.mjs

~~~js
import { createServer } from 'node:http';

const html = [
  '<!doctype html>',
  '<html lang="vi">',
  '<head>',
  '<meta charset="utf-8">',
  '<meta name="viewport" content="width=device-width, initial-scale=1">',
  '<title>Clipboard API lab</title>',
  '<style>',
  'body { font: 16px sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }',
  'textarea { width: 100%; min-height: 100px; }',
  'button { margin: .3rem; padding: .5rem .8rem; }',
  'pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f2f2f2; padding: 1rem; }',
  '</style>',
  '</head>',
  '<body>',
  '<h1>Clipboard API lab</h1>',
  '<p>Lab chỉ dùng dữ liệu demo. Bấm từng nút để kiểm tra quyền và hành vi browser.</p>',
  '<label for="source">Văn bản nguồn</label>',
  '<textarea id="source">Mã demo CLIPBOARD-2026-001</textarea>',
  '<div>',
  '<button id="write-text" type="button">Ghi text vào clipboard</button>',
  '<button id="read-text" type="button">Đọc text từ clipboard</button>',
  '<button id="write-rich" type="button">Ghi HTML + text</button>',
  '<button id="read-types" type="button">Đọc MIME types</button>',
  '</div>',
  '<label for="destination">Kết quả text</label>',
  '<textarea id="destination" placeholder="Dữ liệu đọc được sẽ hiện ở đây"></textarea>',
  '<p id="status" role="status" aria-live="polite">Sẵn sàng.</p>',
  '<pre id="details">Chưa có thao tác.</pre>',
  '<script>',
  'const source = document.querySelector("#source");',
  'const destination = document.querySelector("#destination");',
  'const status = document.querySelector("#status");',
  'const details = document.querySelector("#details");',
  '',
  'function showError(label, error) {',
  '  status.textContent = label + ": " + error.name;',
  '  details.textContent = error.message;',
  '}',
  '',
  'document.querySelector("#write-text").addEventListener("click", async () => {',
  '  try {',
  '    await navigator.clipboard.writeText(source.value);',
  '    status.textContent = "Đã ghi text vào clipboard.";',
  '    details.textContent = "writeText() hoàn tất.";',
  '  } catch (error) {',
  '    showError("Ghi clipboard thất bại", error);',
  '  }',
  '});',
  '',
  'document.querySelector("#read-text").addEventListener("click", async () => {',
  '  try {',
  '    const text = await navigator.clipboard.readText();',
  '    destination.value = text;',
  '    status.textContent = text ? "Đã đọc text." : "Clipboard không có text.";',
  '    details.textContent = "readText() trả về " + text.length + " ký tự.";',
  '  } catch (error) {',
  '    showError("Đọc clipboard thất bại", error);',
  '  }',
  '});',
  '',
  'document.querySelector("#write-rich").addEventListener("click", async () => {',
  '  try {',
  '    const plain = source.value;',
  '    const htmlValue = "<strong>" + plain.replace(/[&<>]/g, char => ({',
  '      "&": "&amp;",',
  '      "<": "&lt;",',
  '      ">": "&gt;",',
  '    })[char]) + "</strong>";',
  '    const item = new ClipboardItem({',
  '      "text/plain": new Blob([plain], { type: "text/plain" }),',
  '      "text/html": new Blob([htmlValue], { type: "text/html" })',
  '    });',
  '    await navigator.clipboard.write([item]);',
  '    status.textContent = "Đã ghi HTML và text representations.";',
  '    details.textContent = "Một ClipboardItem có text/plain và text/html.";',
  '  } catch (error) {',
  '    showError("Ghi rich clipboard thất bại", error);',
  '  }',
  '});',
  '',
  'document.querySelector("#read-types").addEventListener("click", async () => {',
  '  try {',
  '    const items = await navigator.clipboard.read();',
  '    const result = [];',
  '    for (const item of items) {',
  '      result.push("Item types: " + item.types.join(", "));',
  '      if (item.types.includes("text/plain")) {',
  '        const blob = await item.getType("text/plain");',
  '        result.push("Plain text length: " + (await blob.text()).length);',
  '      }',
  '    }',
  '    details.textContent = result.join("\\n") || "Clipboard không có item.";',
  '    status.textContent = "Đã đọc metadata clipboard.";',
  '  } catch (error) {',
  '    showError("Không thể đọc clipboard items", error);',
  '  }',
  '});',
  '',
  'if (!window.isSecureContext || !navigator.clipboard) {',
  '  status.textContent = "Async Clipboard API không khả dụng trong context này.";',
  '}',
  '</script>',
  '</body>',
  '</html>'
].join('\n');

createServer((req, res) => {
  if (req.url !== '/') {
    res.writeHead(404);
    return res.end('Not found');
  }

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store'
  });

  res.end(html);
}).listen(3000, 'localhost', () => {
  console.log('Clipboard lab: http://localhost:3000');
});
~~~

### 11.3 Chạy lab

~~~bash
node server.mjs
~~~

Mở http://localhost:3000. Kiểm tra:

1. Bấm “Ghi text vào clipboard”; browser có thể yêu cầu quyền hoặc yêu cầu thao tác người dùng.
2. Chuyển sang ứng dụng khác và paste để xác minh nội dung.
3. Copy nội dung khác từ bên ngoài, quay lại trang và bấm “Đọc text từ clipboard”.
4. Bấm “Ghi HTML + text”, paste vào trình soạn thảo hỗ trợ rich text để xem định dạng.
5. Bấm “Đọc MIME types” để quan sát các representation browser trả về.
6. Từ chối permission hoặc bỏ user activation trong một lần thử riêng để quan sát NotAllowedError.
7. Thử browser khác để so sánh prompt và permission behavior.

Không dùng dữ liệu mật khẩu hoặc token thật trong lab. Sau khi thử, dừng server và có thể copy một nội dung vô hại khác để thay clipboard demo.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Clipboard Event API và Async Clipboard API khác nhau thế nào?

**Đáp án:** Clipboard Event API xử lý các thao tác copy/cut/paste do người dùng khởi tạo; Async Clipboard API cho phép JavaScript đọc/ghi trực tiếp qua Promise và chịu các kiểm soát quyền chặt hơn.

**Câu 2.** Vì sao Async Clipboard API cần secure context?

**Đáp án:** Clipboard là tài nguyên hệ điều hành có thể chứa dữ liệu nhạy cảm. Browser chỉ cung cấp API này trong secure context để giảm nguy cơ bị truy cập hoặc can thiệp qua kết nối không an toàn.

**Câu 3.** writeText() trả về gì?

**Đáp án:** Một Promise được resolve khi nội dung đã được ghi vào system clipboard; Promise có thể reject nếu browser không cho phép.

**Câu 4.** readText() có thể trả chuỗi rỗng trong trường hợp nào?

**Đáp án:** Clipboard trống hoặc không có representation text mà browser có thể trả về.

**Câu 5.** Vì sao không thể dựa vào Permissions API query clipboard-read trên mọi browser?

**Đáp án:** Browser triển khai permission khác nhau. Chromium hỗ trợ các permission clipboard-read/clipboard-write theo mô hình riêng; Firefox và Safari thường dùng user activation và prompt paste thay vì các descriptor đó.

**Câu 6.** ClipboardItem dùng để làm gì?

**Đáp án:** Nó chứa nhiều representation MIME của cùng một nội dung, ví dụ text/plain và text/html, để ứng dụng nhận chọn định dạng phù hợp.

**Câu 7.** Vì sao dữ liệu text/html từ clipboard phải được sanitize?

**Đáp án:** Clipboard có thể chứa markup không tin cậy, event handler, URL nguy hiểm hoặc nội dung ẩn. Đưa thẳng vào innerHTML có thể tạo DOM XSS.

**Câu 8.** Khi paste handler gọi preventDefault(), điều gì xảy ra?

**Đáp án:** Browser hủy hành vi paste mặc định. Nếu ứng dụng vẫn muốn chèn nội dung, handler phải tự xử lý dữ liệu và cập nhật editor.

**Câu 9.** Iframe cần gì để dùng clipboard trong browser hỗ trợ Permissions Policy?

**Đáp án:** Parent policy phải cho phép clipboard-read/clipboard-write và iframe cần được delegate bằng allow attribute. Secure context, activation và permission vẫn áp dụng.

**Câu 10.** Vì sao không nên đọc clipboard ngay khi trang tải?

**Đáp án:** Clipboard có thể chứa password, token, OTP và dữ liệu cá nhân. Chỉ đọc khi người dùng chủ động yêu cầu, giải thích mục đích và tránh gửi dữ liệu ra server ngoài nhu cầu.

## 13. Checklist bảo mật Clipboard API

Trước khi triển khai clipboard feature, hãy kiểm tra:

1. **Purpose:** chức năng copy/paste có mục đích rõ và người dùng hiểu được không?
2. **Secure context:** document chạy trên HTTPS hoặc môi trường localhost được browser tin cậy.
3. **User gesture:** gọi API trực tiếp từ thao tác người dùng khi browser yêu cầu.
4. **Permission:** xử lý prompt, denied state và khác biệt browser; không giả định permission query luôn có.
5. **Focus:** bảo đảm document đang focus khi thực hiện thao tác cần focus.
6. **Least access:** chỉ đọc clipboard khi người dùng yêu cầu; không poll hoặc đọc lúc page load.
7. **Data handling:** không log hoặc gửi clipboard content tới server ngoài nhu cầu đã công bố.
8. **Paste safety:** coi text/html, URL, CSV, JSON và file metadata là input không tin cậy.
9. **DOM safety:** dùng textContent cho text; sanitize HTML bằng thư viện chuyên dụng trước khi tạo DOM.
10. **Copy integrity:** không âm thầm thay nội dung mà người dùng nghĩ họ đang copy.
11. **Iframe:** cấu hình Permissions Policy/allow đúng origin nếu cần delegate.
12. **Compatibility:** feature-detect ClipboardItem, image formats và permission descriptors.
13. **Error handling:** xử lý NotAllowedError, NotFoundError và API không tồn tại.
14. **Size limits:** giới hạn dung lượng, MIME type và số lượng representation.
15. **Secrets:** cảnh báo khi copy secret; không xem clipboard là nơi lưu trữ an toàn.
16. **Regression:** kiểm thử Chromium, Firefox, Safari và các môi trường hệ điều hành mục tiêu.

**Ghi nhớ:** Clipboard là cầu nối giữa website, browser, hệ điều hành và ứng dụng khác. Dùng Async Clipboard API cho thao tác trực tiếp, Clipboard Event API cho copy/cut/paste do người dùng thực hiện, và luôn coi dữ liệu paste là input không tin cậy. Secure context, user activation, permission và Permissions Policy là những lớp kiểm soát cần được kiểm tra cùng nhau.

## Tài liệu tham khảo

- [W3C — Clipboard API and events (Working Draft, 24 June 2026)](https://www.w3.org/TR/clipboard-apis/)
- [MDN — Clipboard API](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard_API)
- [MDN — Clipboard.readText()](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/readText)
- [MDN — Clipboard.writeText()](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/writeText)
- [MDN — Clipboard.read()](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/read)
- [MDN — Clipboard.write()](https://developer.mozilla.org/en-US/docs/Web/API/Clipboard/write)
- [MDN — ClipboardItem](https://developer.mozilla.org/en-US/docs/Web/API/ClipboardItem)
- [MDN — Permissions Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)

