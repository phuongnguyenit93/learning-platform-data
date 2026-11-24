# Safe DOM API

**Safe DOM API** là cách xây dựng và cập nhật giao diện bằng các API DOM coi dữ liệu không tin cậy là dữ liệu, không phải markup hay mã thực thi. Khi chỉ cần hiển thị văn bản, dùng **textContent**, **createTextNode**, **createElement**, **append** và **replaceChildren** thay vì đưa chuỗi đầu vào HTML parser qua **innerHTML** hoặc các sink tương tự.

Không có API DOM nào tự động làm mọi dữ liệu trở nên an toàn trong mọi ngữ cảnh. Ví dụ, gán một chuỗi vào **textContent** phù hợp để hiển thị văn bản, nhưng gán chuỗi không tin cậy vào **href**, **src**, **style**, **srcdoc** hoặc thuộc tính sự kiện vẫn có thể tạo hành vi nguy hiểm. Cần chọn API theo mục đích, kiểm tra URL/giá trị thuộc tính theo chính sách và chỉ dùng HTML sanitizer khi sản phẩm thực sự cần hiển thị HTML do người dùng cung cấp.

Bài học thuộc chương **DOM security** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích ranh giới giữa browser, origin, cookie và ứng dụng web; tập trung vào cách thao tác DOM an toàn để phòng XSS, kết hợp CSP, Trusted Types và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt DOM API hiển thị văn bản với API phân tích chuỗi thành HTML.
2. Dùng **textContent**, **createTextNode**, **createElement**, **append** và **replaceChildren** để xây dựng DOM an toàn.
3. Nhận diện các HTML/DOM sink nguy hiểm như **innerHTML**, **outerHTML**, **insertAdjacentHTML**, **document.write**, **srcdoc** và event-handler attributes.
4. Hiểu vì sao **setAttribute** và DOM property không mặc nhiên an toàn cho mọi thuộc tính.
5. Kiểm tra URL trước khi gán vào **href**, **src**, **formAction** hoặc gọi **window.open**.
6. Dùng event listener thay cho inline event handler và tránh DOM clobbering.
7. Dùng HTML sanitizer và Trusted Types khi cần hiển thị rich text.
8. Kết hợp Safe DOM API với CSP, xử lý XSS và kiểm thử trong browser DevTools.

## 2. DOM API và ranh giới giữa dữ liệu với mã

DOM (Document Object Model) biểu diễn tài liệu HTML thành cây node mà JavaScript có thể đọc và thay đổi. Khi nhận một chuỗi từ query string, API, form hoặc người dùng, ứng dụng có hai lựa chọn rất khác nhau:

- **Xem chuỗi là dữ liệu:** tạo text node hoặc gán vào thuộc tính chỉ chứa văn bản.
- **Diễn giải chuỗi thành markup:** đưa chuỗi qua HTML parser để browser tạo element, attribute và có thể kích hoạt hành vi.

Ví dụ người dùng nhập:

~~~text
Xin chào <img src=x onerror=alert(1)>
~~~

Nếu ứng dụng gán chuỗi này vào **textContent**, browser hiển thị nguyên văn ký tự. Nếu ứng dụng gán vào **innerHTML**, browser phân tích chuỗi thành phần tử img và thuộc tính onerror; khi điều kiện phù hợp xảy ra, handler có thể chạy.

### Luồng dữ liệu và DOM sink

~~~mermaid
flowchart TD
    A["Dữ liệu không tin cậy<br/>URL, API, form, storage, postMessage"] --> B{"Mục đích hiển thị"}
    B -->|Văn bản| C["textContent / createTextNode"]
    C --> D["DOM hiển thị literal text"]
    B -->|Giao diện có cấu trúc| E["createElement + append"]
    E --> F["Gán text vào text node<br/>kiểm tra URL/attribute riêng"]
    F --> G["DOM được tạo có kiểm soát"]
    B -->|Rich HTML thật sự cần| H["HTML sanitizer theo allowlist"]
    H --> I["Trusted Types khi hỗ trợ<br/>+ CSP enforcement"]
    I --> J["HTML đã sanitize được chèn"]
~~~

**Safe DOM API không đồng nghĩa “không bao giờ có XSS”.** An toàn phụ thuộc cả nguồn dữ liệu, API được gọi, loại thuộc tính, URL scheme, cách sanitizer được cấu hình và các đoạn code xử lý tiếp theo.

## 3. Những API nên ưu tiên khi chỉ cần hiển thị dữ liệu

### 3.1. textContent

`textContent` đọc hoặc thay thế nội dung văn bản của node. Khi gán chuỗi, browser tạo/đặt text node và không diễn giải chuỗi thành HTML:

~~~js
const message = new URLSearchParams(location.search).get('message') ?? '';
const output = document.querySelector('#message');

output.textContent = message;
~~~

Nếu `message` là `<img src=x onerror=alert(1)>`, người dùng nhìn thấy đúng chuỗi đó; browser không tạo img và không thực thi handler.

Ưu điểm:

- Phù hợp khi cần hiển thị văn bản thuần.
- Không gọi HTML parser với chuỗi đầu vào.
- Không cần tự escape dấu nháy, dấu ngoặc nhọn hoặc ký tự HTML.
- Có thể thay thế nội dung con của node bằng một text node.

Lưu ý: gán `textContent` cho một node cha sẽ thay thế toàn bộ node con hiện có. Nếu cần giữ cấu trúc giao diện, chỉ gán vào phần tử dành riêng cho text hoặc dùng `append` để thêm node.

Phạm vi an toàn ở đây là **node hiển thị văn bản thông thường**. Không dùng `textContent` hoặc `createTextNode` để đưa dữ liệu không tin cậy vào nội dung của phần tử `script` hay `style`: nội dung của các phần tử này được browser diễn giải lần lượt như JavaScript hoặc CSS khi chúng hoạt động.

### 3.2. createTextNode

Khi muốn tạo một text node riêng:

~~~js
const label = document.createTextNode(userSuppliedLabel);
document.querySelector('#labels').append(label);
~~~

`createTextNode` không phân tích chuỗi thành markup. Nó hữu ích khi xây DOM theo từng bước hoặc khi muốn phân biệt rõ node chứa text với node element.

### 3.3. createElement và append

Tạo element bằng tên thẻ cố định do ứng dụng quyết định, sau đó gán dữ liệu vào text node:

~~~js
function renderComment(comment, list) {
  const item = document.createElement('li');
  item.className = 'comment';

  const author = document.createElement('strong');
  author.textContent = String(comment.author ?? 'Ẩn danh');

  const body = document.createElement('p');
  body.textContent = String(comment.body ?? '');

  item.append(author, body);
  list.append(item);
}
~~~

Trong ví dụ:

- Tên tag `li`, `strong`, `p` là hằng số do code tin cậy kiểm soát.
- Dữ liệu `author` và `body` được đưa vào text node.
- Không tạo HTML bằng cách nối chuỗi.

Không lấy tên thẻ tùy ý từ người dùng rồi gọi `document.createElement(userTag)`. Element như `script`, `iframe`, `object` hoặc `style` có ngữ nghĩa và khả năng tải/thực thi riêng. Nếu cần cho phép một tập loại element, dùng allowlist rõ ràng và xử lý từng loại thuộc tính.

### 3.4. replaceChildren

Để thay toàn bộ nội dung của một container bằng các node đã xây dựng:

~~~js
function renderMessages(container, messages) {
  const fragment = document.createDocumentFragment();

  for (const message of messages) {
    const item = document.createElement('li');
    item.textContent = String(message);
    fragment.append(item);
  }

  container.replaceChildren(fragment);
}
~~~

`DocumentFragment` giúp nhóm các node trước khi gắn vào DOM. `replaceChildren` nhận node hoặc chuỗi; khi truyền chuỗi, chuỗi được chuyển thành text node chứ không được phân tích như HTML. Tuy vậy, dùng node tường minh giúp code dễ review và mở rộng hơn.

### 3.5. insertAdjacentText

Nếu cần chèn văn bản vào vị trí cụ thể:

~~~js
const log = document.querySelector('#log');
log.insertAdjacentText('beforeend', userMessage);
~~~

Dùng **insertAdjacentText**, không dùng **insertAdjacentHTML** với dữ liệu không tin cậy. Hai API có tên gần nhau nhưng ngữ nghĩa khác hẳn: một API chèn text node, API còn lại phân tích HTML.

## 4. Bảng chọn API theo mục đích

| Mục đích | API nên ưu tiên | API cần tránh với dữ liệu không tin cậy |
| --- | --- | --- |
| Hiển thị văn bản | `textContent`, `createTextNode`, `insertAdjacentText` | `innerHTML`, `outerHTML` |
| Tạo cấu trúc giao diện | `createElement`, `append`, `prepend`, `replaceChildren` | Nối chuỗi HTML rồi chèn |
| Thay nội dung container | Xây node rồi `replaceChildren` | `container.innerHTML = input` |
| Xử lý click/submit | `addEventListener` với callback tin cậy | Thuộc tính `onclick` nhận chuỗi |
| Gán URL link | Parse/validate bằng `URL`, sau đó gán `anchor.href` | Gán URL tùy ý hoặc chỉ escape HTML |
| Gán ảnh | Allowlist URL/resource origin rồi gán `img.src` | Cho phép dữ liệu tùy ý thành URL ảnh |
| Hiển thị rich HTML | Sanitizer được duy trì, policy rõ ràng, Trusted Types nếu hỗ trợ | `innerHTML` trực tiếp với HTML thô |
| Tạo CSS | Gán thuộc tính CSS cụ thể với giá trị đã validate | Nối dữ liệu tùy ý vào `style.cssText` hoặc stylesheet |

## 5. Các DOM sink có thể phân tích hoặc thực thi dữ liệu

Một **sink** là điểm mà dữ liệu đi vào một API hoặc thuộc tính có thể tạo ra hành vi trong browser. Khi review XSS, cần lần theo source → transform → sink.

### 5.1. HTML parsing sinks

Các API sau có thể đưa chuỗi qua HTML parser:

| Sink | Rủi ro |
| --- | --- |
| `element.innerHTML` | Phân tích chuỗi thành HTML con |
| `element.outerHTML` | Thay thế element bằng HTML được phân tích |
| `element.insertAdjacentHTML()` | Chèn HTML tại vị trí chỉ định |
| `document.write()` / `document.writeln()` | Ghi chuỗi vào parser của tài liệu |
| `Range.createContextualFragment()` | Phân tích chuỗi thành DocumentFragment |
| `iframe.srcdoc` | Nạp nội dung HTML inline vào iframe |
| `DOMParser.parseFromString(..., 'text/html')` | Parse HTML thành document; không nên coi document inert là đã sanitize |

Ví dụ nguy hiểm:

~~~js
const comment = new URLSearchParams(location.search).get('comment') ?? '';
document.querySelector('#comments').innerHTML = comment;
~~~

Thay bằng:

~~~js
const comment = new URLSearchParams(location.search).get('comment') ?? '';
const paragraph = document.createElement('p');
paragraph.textContent = comment;
document.querySelector('#comments').append(paragraph);
~~~

### 5.2. Vì sao DOMParser không phải sanitizer?

Một số người cho rằng có thể parse HTML trong document tạm rồi lấy node ra vì script không chạy ngay trong document được parse. Đây là giả định nguy hiểm:

- Document tạm không đồng nghĩa nội dung đã được loại bỏ event handler, URL nguy hiểm hoặc node không mong muốn.
- Khi node được đưa vào document đang hoạt động, một số hành vi có thể trở nên hoạt động.
- Nội dung vẫn có thể chứa iframe, URL tải tài nguyên, thuộc tính sự kiện hoặc cấu trúc gây DOM clobbering.

Nếu cần hiển thị HTML do người dùng cung cấp, dùng sanitizer HTML chuyên dụng với allowlist tag/attribute/protocol; không tự viết bộ lọc bằng regex hoặc dựa vào DOMParser đơn thuần.

### 5.3. JavaScript execution sinks

Tránh chuyển dữ liệu không tin cậy thành mã:

~~~js
// Không an toàn:
eval(userInput);
new Function(userInput)();
setTimeout(userInput, 1000);
setInterval(userInput, 1000);
~~~

`setTimeout` và `setInterval` nên nhận callback function tin cậy:

~~~js
setTimeout(() => {
  refreshStatus();
}, 1000);
~~~

Không đưa chuỗi do người dùng kiểm soát vào `eval`, `Function` hoặc API thực thi chuỗi tương tự. Nếu cần tính toán biểu thức, thiết kế parser/grammar giới hạn hoặc dùng dữ liệu có cấu trúc, không thực thi JavaScript tùy ý.

## 6. setAttribute và DOM property không mặc nhiên an toàn

Một hiểu lầm phổ biến là mọi API DOM đều an toàn vì không nối HTML. Thực tế, thuộc tính được gán có thể tự tạo ngữ nghĩa đặc biệt.

### 6.1. Thuộc tính văn bản thường dùng được

Các thuộc tính như `title`, `aria-label` hoặc `data-*` thường phù hợp để chứa text:

~~~js
button.setAttribute('aria-label', userLabel);
element.dataset.description = userDescription;
~~~

Nhưng dữ liệu ở đây vẫn phải được xử lý đúng khi đọc lại. Nếu code sau đó lấy `dataset.description` rồi đưa vào `innerHTML`, rủi ro XSS xuất hiện ở sink tiếp theo.

### 6.2. Thuộc tính nguy hiểm cần chính sách riêng

Không gán chuỗi không tin cậy vào các nhóm thuộc tính sau mà chưa kiểm tra:

| Nhóm | Ví dụ | Lý do |
| --- | --- | --- |
| Event handler | `onclick`, `onerror`, `onload` | Có thể được browser biên dịch/chạy như mã |
| URL | `href`, `src`, `action`, `formaction`, `xlink:href` | Có thể điều hướng, tải tài nguyên hoặc kích hoạt scheme nguy hiểm |
| HTML inline | `srcdoc` | Nội dung được parse thành tài liệu HTML |
| CSS | `style`, `style.cssText` | Giá trị được diễn giải theo cú pháp CSS, có thể chứa URL hoặc thay đổi giao diện |
| Script | `script.text`, `script.src` | Có thể tạo hoặc tải mã thực thi |
| Tên/ID DOM | `id`, `name` | Có thể gây DOM clobbering hoặc ghi đè named properties |

Ví dụ:

~~~js
// Không an toàn: browser hiểu giá trị như event handler.
button.setAttribute('onclick', userSuppliedCode);

// Không an toàn nếu URL chưa được kiểm tra.
link.setAttribute('href', userSuppliedUrl);

// Không an toàn: nội dung được parse thành document trong iframe.
frame.srcdoc = userSuppliedHtml;
~~~

Đối với sự kiện, đăng ký callback tin cậy:

~~~js
button.addEventListener('click', () => {
  submitForm();
});
~~~

Đối với URL, parse và allowlist theo mục đích trước khi gán. Đối với rich HTML, sanitize trước khi chèn.

### 6.3. Không để người dùng quyết định tên thuộc tính

Không tạo attribute name trực tiếp từ dữ liệu người dùng:

~~~js
// Không an toàn về thiết kế:
element.setAttribute(userProvidedAttributeName, userProvidedValue);
~~~

Ngay cả khi value đã được escape, tên thuộc tính có thể là `onclick`, `srcdoc` hoặc `style`. Nếu phải hỗ trợ cấu hình linh hoạt, định nghĩa map allowlist tên thuộc tính và validate giá trị riêng theo từng loại.

## 7. Xử lý URL an toàn trước khi gán DOM property

Các property như `anchor.href`, `image.src` và `form.action` vẫn là URL sink. Gán bằng property API giúp tránh HTML string parsing nhưng **không tự chặn javascript:, data: hoặc host không tin cậy**.

### 7.1. Chỉ cho phép URL cùng origin

~~~js
function parseInternalUrl(input) {
  try {
    const target = new URL(input, window.location.origin);
    if (target.origin !== window.location.origin) return null;
    if (target.protocol !== window.location.protocol) return null;
    if (target.username || target.password) return null;
    return target;
  } catch {
    return null;
  }
}

function setInternalLink(anchor, input, label) {
  const target = parseInternalUrl(input);
  if (!target) {
    anchor.removeAttribute('href');
    anchor.textContent = label;
    return;
  }
  anchor.href = target.href;
  anchor.textContent = label;
}
~~~

Base URL lấy từ `window.location.origin`, không lấy từ dữ liệu người dùng. So sánh `origin` bao gồm scheme, host và port; URL tương đối được resolve trước khi kiểm tra.

### 7.2. Allowlist nguồn ảnh

Nếu ảnh có thể đến từ một số CDN cụ thể:

~~~js
const imageHosts = new Set([
  'images.example.com',
  'cdn.example.net',
]);

function parseImageUrl(input) {
  try {
    const url = new URL(input, window.location.origin);
    if (url.protocol !== 'https:') return null;
    if (!imageHosts.has(url.hostname)) return null;
    if (url.username || url.password) return null;
    if (url.port && url.port !== '443') return null;
    return url;
  } catch {
    return null;
  }
}
~~~

Sau đó gán:

~~~js
const imageUrl = parseImageUrl(apiImageUrl);
if (imageUrl) {
  image.src = imageUrl.href;
  image.alt = 'Ảnh sản phẩm';
} else {
  image.removeAttribute('src');
  image.alt = 'Không có ảnh hợp lệ';
}
~~~

Allowlist host chỉ phù hợp khi danh sách host được kiểm soát và mọi đường dẫn trên host đó đều phù hợp mục đích. Với ảnh do người dùng tải lên, ưu tiên phục vụ từ origin riêng cho nội dung không tin cậy hoặc qua pipeline kiểm tra file.

### 7.3. URL không chỉ có scheme và host

Tùy mục đích, có thể cần kiểm tra:

- Scheme: chỉ HTTPS hay cho phép mailto/tel?
- Host/origin: chỉ domain nội bộ hay một allowlist đối tác?
- Port: chỉ port mặc định hay một port dịch vụ cụ thể?
- Userinfo: có từ chối username/password để tránh gây nhầm?
- Redirect: đích ban đầu có chuyển hướng sang host ngoài allowlist không?
- URL path: có được phép truy cập route hoặc file cụ thể?

Nếu server fetch URL do client cung cấp, còn phải phòng SSRF, DNS rebinding, redirect abuse và truy cập IP nội bộ. Validation ở browser không thay kiểm tra URL ở backend.

## 8. CSS và style cũng cần API phù hợp

Không nối dữ liệu tùy ý vào chuỗi CSS:

~~~js
// Không an toàn về thiết kế:
element.style.cssText = userStyle;
~~~

Nếu cần thay đổi một thuộc tính CSS, gán property cụ thể và kiểm tra giá trị:

~~~js
const allowedColors = new Set(['red', 'blue', 'green', 'gray']);
const color = allowedColors.has(userColor) ? userColor : 'gray';
element.style.color = color;
~~~

Đối với kích thước, số liệu và vị trí, parse thành số rồi áp dụng giới hạn min/max thay vì đưa chuỗi tùy ý vào CSS. Không để người dùng điều khiển trực tiếp `backgroundImage` hoặc CSS `url(...)` nếu không có URL policy.

CSS injection không phải lúc nào cũng thực thi JavaScript trong browser hiện đại, nhưng vẫn có thể làm giả giao diện, che nội dung, tải tài nguyên ngoài hoặc tạo kênh rò rỉ tùy ngữ cảnh. Đừng xem style là vùng dữ liệu vô hại.

## 9. DOM clobbering và tên thuộc tính

**DOM clobbering** xảy ra khi element có `id` hoặc `name` được đưa vào tài liệu và làm thay đổi cách truy cập các named properties trên `window`, `document` hoặc form. Mã ứng dụng dựa vào global name có thể vô tình tham chiếu tới element do attacker kiểm soát.

Ví dụ code dễ mắc lỗi:

~~~js
// Không nên dựa vào named global do id/name tạo ra.
if (window.redirectUrl) {
  location.href = window.redirectUrl;
}
~~~

Nếu tài liệu có element với tên phù hợp, named property có thể gây xung đột với biến mà ứng dụng kỳ vọng.

Phòng vệ:

- Dùng `const`/`let` và truy vấn DOM rõ ràng qua `querySelector` hoặc `getElementById`.
- Không để dữ liệu không tin cậy quyết định `id` hoặc `name` của element nhạy cảm.
- Dùng tên thuộc tính ổn định do ứng dụng quản lý.
- Nếu cho phép rich HTML, cấu hình sanitizer để xử lý/đổi tên các thuộc tính định danh nguy hiểm; DOMPurify có tùy chọn `SANITIZE_NAMED_PROPS`.
- Không dựa vào `window.someName` hoặc `document.someName` như một biến ứng dụng.

DOM clobbering có thể kết hợp với XSS hoặc lỗi logic URL, nên cần kiểm tra cả HTML do người dùng cung cấp và code tiêu thụ các named properties.

## 10. Khi thật sự cần rich HTML: sanitize trước khi chèn

Một số sản phẩm cần hiển thị nội dung rich text như bình luận có định dạng, bài viết hoặc mô tả sản phẩm. Trong trường hợp này, `textContent` không đáp ứng yêu cầu vì nó hiển thị markup thành văn bản. Cần dùng một **HTML sanitizer được duy trì**, cấu hình allowlist rõ ràng và kiểm thử theo browser mục tiêu.

### 10.1. Ví dụ với DOMPurify

~~~js
const dirtyHtml = apiResponse.richText;
const cleanHtml = DOMPurify.sanitize(dirtyHtml, {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['style', 'iframe', 'object', 'embed'],
  FORBID_ATTR: ['style'],
});

document.querySelector('#article').innerHTML = cleanHtml;
~~~

Đây là ví dụ minh họa cấu hình; chính sách thực tế phải xác định tag, attribute, URL protocol và nhu cầu sản phẩm. Nếu ứng dụng không cần link, ảnh hoặc một số tag, hãy loại bỏ chúng. Không tự thêm lại event handler hoặc thuộc tính nguy hiểm sau khi sanitize.

### 10.2. Không sửa chuỗi sau sanitize theo cách làm mất bảo vệ

Một anti-pattern:

1. Sanitize HTML.
2. Nối thêm chuỗi không tin cậy vào kết quả.
3. Gán toàn bộ vào `innerHTML`.

Khi sửa nội dung sau sanitizer, đầu ra có thể trở lại không an toàn. Nếu cần thêm thông tin, hãy tạo DOM node bằng Safe DOM API rồi append vào cấu trúc đã sanitize.

### 10.3. Sanitizer không thay validation nghiệp vụ

Sanitizer quyết định markup/attribute nào được giữ lại. Nó không xác minh rằng:

- URL là website đối tác mà doanh nghiệp muốn cho phép.
- Người dùng có quyền xem tài nguyên được liên kết.
- Nội dung không chứa thông tin nhạy cảm.
- Ảnh hoặc file được tải lên là loại file hợp lệ.

Vẫn cần URL policy, authorization và kiểm tra nội dung theo nghiệp vụ.

## 11. Trusted Types: siết các DOM sink nguy hiểm

**Trusted Types** là cơ chế browser giúp ứng dụng hạn chế việc đưa chuỗi tùy ý vào một số DOM XSS sink. Khi bật enforcement, các sink yêu cầu Trusted Types sẽ từ chối chuỗi thông thường và chỉ chấp nhận giá trị được tạo qua policy đã đăng ký.

Ví dụ CSP:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html dompurify
~~~

Chỉ thị `require-trusted-types-for 'script'` yêu cầu các sink được hỗ trợ phải nhận kiểu tin cậy. `trusted-types` giới hạn tên policy được phép tạo. Nếu dùng phiên bản DOMPurify có policy nội bộ tên `dompurify`, cấu hình CSP cần cho phép policy đó; kiểm tra tài liệu phiên bản thư viện thực tế.

### 11.1. Tạo policy gắn với sanitizer

~~~js
const htmlPolicy = trustedTypes.createPolicy('app-html', {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true },
      RETURN_TRUSTED_TYPE: false,
    });
  },
});

const trustedHtml = htmlPolicy.createHTML(untrustedRichText);
document.querySelector('#article').innerHTML = trustedHtml;
~~~

Trong callback `createHTML`, DOMPurify trả về chuỗi đã sanitize để Trusted Types policy bọc thành TrustedHTML. Không tạo policy kiểu:

~~~js
// Không an toàn: policy tin mọi chuỗi.
trustedTypes.createPolicy('app-html', {
  createHTML: input => input,
});
~~~

Policy là ranh giới tin cậy trong code ứng dụng. Nếu policy chỉ trả lại input, enforcement mất ý nghĩa.

### 11.2. Trusted Types không thay Safe DOM API

Trusted Types:

- Có hỗ trợ theo browser; cần kiểm tra compatibility.
- Chỉ bảo vệ những sink được triển khai trong cơ chế Trusted Types.
- Không tự xác thực URL cho mọi thuộc tính như anchor href hoặc mọi navigation.
- Không thay authorization, CSRF, CSP hoặc việc xử lý dữ liệu đúng.
- Không làm một policy yếu trở nên an toàn.

Ưu tiên Safe DOM API cho văn bản và cấu trúc thông thường; dùng sanitizer + Trusted Types cho trường hợp cần HTML.

## 12. CSP hỗ trợ bảo vệ DOM như thế nào?

CSP là response header để browser áp dụng chính sách tài nguyên và một số hành vi của tài liệu. Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-YWJjMTIz'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types app-html dompurify
~~~

Nonce trong ví dụ chỉ minh họa cú pháp; production phải sinh nonce ngẫu nhiên mới cho mỗi response và gắn đúng vào script hợp lệ. Các chỉ thị có vai trò khác nhau:

| Chỉ thị | Tác dụng |
| --- | --- |
| `script-src` | Giới hạn nguồn script, inline script và một số dạng thực thi |
| `object-src 'none'` | Chặn nội dung object/plugin cũ |
| `base-uri 'self'` | Giới hạn URL base của tài liệu |
| `form-action 'self'` | Giới hạn đích form gửi tới |
| `frame-ancestors 'none'` | Ngăn website khác nhúng trang, giúp phòng clickjacking |
| `require-trusted-types-for 'script'` | Bật enforcement Trusted Types cho các sink hỗ trợ |
| `trusted-types ...` | Allowlist tên Trusted Types policy |

CSP không thay việc sửa sink nguy hiểm. Nếu ứng dụng có XSS, CSP có thể giảm một số cách khai thác, nhưng cần cấu hình nghiêm ngặt, kiểm thử và theo dõi vi phạm. Bắt đầu bằng `Content-Security-Policy-Report-Only` nếu cần đánh giá tác động trước khi chặn.

## 13. Thực hành: dựng DOM an toàn trong browser

Bài thực hành dùng browser hiện đại, không cần thư viện ngoài. Mục tiêu là so sánh cách hiển thị dữ liệu không tin cậy bằng text node với việc phân tích HTML; đồng thời kiểm tra URL và event handler qua các API DOM.

### 13.1. Tạo trang thử nghiệm

Tạo file `safe-dom-demo.html` trong thư mục thực hành riêng:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Safe DOM API lab</title>
</head>
<body>
  <h1>Safe DOM API</h1>
  <label>
    Nội dung thử nghiệm
    <textarea id="input" rows="4"><img src=x onerror=alert(1)> Xin chào</textarea>
  </label>
  <button id="render">Hiển thị an toàn</button>
  <section>
    <h2>Kết quả</h2>
    <ul id="output"></ul>
  </section>
  <label>
    URL thử nghiệm
    <input id="url" value="/account">
  </label>
  <button id="check-url">Kiểm tra URL</button>
  <p id="url-result"></p>
  <script>
    const input = document.querySelector('#input');
    const output = document.querySelector('#output');
    const urlInput = document.querySelector('#url');
    const urlResult = document.querySelector('#url-result');

    document.querySelector('#render').addEventListener('click', () => {
      const item = document.createElement('li');
      const text = document.createElement('span');
      text.textContent = input.value;
      item.append(text);
      output.append(item);
    });

    function parseInternalUrl(value) {
      try {
        const target = new URL(value, location.origin);
        if (target.origin !== location.origin) return null;
        if (target.protocol !== location.protocol) return null;
        if (target.username || target.password) return null;
        return target;
      } catch {
        return null;
      }
    }

    document.querySelector('#check-url').addEventListener('click', () => {
      const target = parseInternalUrl(urlInput.value);
      urlResult.textContent = target
        ? 'Được phép: ' + target.pathname + target.search
        : 'URL bị từ chối';
    });
  </script>
</body>
</html>
~~~

Phục vụ file qua local development server rồi mở URL HTTP của server. Nội dung textarea chỉ là chuỗi kiểm thử; không đưa nó vào `innerHTML`.

### 13.2. Kiểm tra textContent

1. Giữ nội dung mặc định có chuỗi `<img ... onerror=...>`.
2. Nhấn **Hiển thị an toàn**.
3. Quan sát rằng browser hiển thị nguyên văn chuỗi trong danh sách.
4. Mở DevTools → Elements; node con là text, không có element img được tạo từ input.
5. Console không có alert hoặc event handler chạy.

### 13.3. Kiểm tra URL policy

Thử lần lượt:

| Input | Kết quả dự kiến |
| --- | --- |
| `/account` | Cho phép |
| `/orders?id=42` | Cho phép |
| `https://app.example.com/settings` (nếu origin thực là app.example.com) | Cho phép |
| `//attacker.example/path` | Từ chối vì khác origin |
| `javascript:alert(1)` | Từ chối vì protocol khác |
| `https://app.example.com.attacker.net/` | Từ chối vì origin khác |
| `https://user@app.example.com/` | Từ chối vì có userinfo |

Trong trang local mở bằng `file://`, origin có thể là `null` và quy tắc khác với website HTTPS. Nên phục vụ trang qua local HTTP server để kiểm thử hành vi origin rõ ràng; trong production sử dụng HTTPS.

### 13.4. Kiểm tra event listener

Mở Console và kiểm tra:

~~~js
document.querySelector('#render').onclick
~~~

Handler được đăng ký qua `addEventListener`, nên property `onclick` không phải chuỗi mã lấy từ người dùng. Không dùng `setAttribute('onclick', ...)` hoặc nội suy dữ liệu vào inline event handler.

## 14. Thực hành mở rộng: rich HTML có sanitizer

Nếu sản phẩm bắt buộc hiển thị rich text, thêm DOMPurify từ nguồn dependency được quản lý và khóa phiên bản. Không tải sanitizer từ URL do người dùng điều khiển. Ví dụ:

~~~js
const dirty = '<p>Hello <strong>world</strong></p><img src=x onerror=alert(1)>';
const clean = DOMPurify.sanitize(dirty, {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['style', 'iframe', 'object', 'embed'],
  FORBID_ATTR: ['style'],
});
document.querySelector('#rich-preview').innerHTML = clean;
~~~

Kết quả dự kiến giữ markup định dạng được phép và loại bỏ event handler nguy hiểm. Hãy kiểm tra HTML sau sanitize trong DevTools và kiểm thử các URL protocol, SVG, MathML, custom element và thuộc tính đặc biệt theo cấu hình thực tế.

Nếu browser hỗ trợ Trusted Types, bật enforcement trong môi trường thử nghiệm rồi tích hợp policy chỉ trả về HTML đã sanitize. Nếu chưa hỗ trợ, sanitizer vẫn có giá trị nhưng cần CSP và kiểm thử tương thích khác.

## 15. Checklist review Safe DOM API

Khi review code thay đổi DOM:

1. **Xác định nguồn:** URL, API, form, local storage, postMessage, dữ liệu server hay nội dung người dùng?
2. **Xác định sink:** text node, HTML parser, URL property, event handler, CSS, script hay iframe?
3. **Văn bản thuần:** dùng textContent/createTextNode/insertAdjacentText.
4. **Cấu trúc DOM:** dùng createElement với tag cố định, append/prepend/replaceChildren.
5. **Event:** dùng addEventListener với callback tin cậy; không tạo inline handler từ chuỗi.
6. **URL:** parse bằng URL API, kiểm tra scheme/host/origin/port/userinfo theo mục đích trước khi gán.
7. **Attributes:** không nhận attribute name tùy ý; phân loại text, URL, event, style, srcdoc và script.
8. **HTML:** tránh innerHTML/outerHTML/insertAdjacentHTML/document.write; nếu cần rich HTML, sanitize bằng thư viện được duy trì.
9. **CSS:** gán property cụ thể với giá trị đã kiểm tra; không nội suy chuỗi style tùy ý.
10. **DOM clobbering:** không dùng named globals; kiểm soát id/name trong nội dung không tin cậy.
11. **Defense-in-depth:** CSP, Trusted Types, HttpOnly cookie và kiểm soát quyền server.
12. **Kiểm thử:** kiểm tra payload dạng text, URL scheme, event attributes, iframe/srcdoc và các luồng nhiều lần biến đổi dữ liệu.

## 16. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Mọi DOM API đều an toàn hơn innerHTML.” | DOM property như href, src, style và srcdoc vẫn có thể là sink nguy hiểm. |
| “setAttribute luôn an toàn.” | Tùy tên attribute; onclick, srcdoc, href, style và script-related attributes cần chính sách riêng. |
| “textContent có thể hiển thị rich HTML.” | textContent hiển thị markup thành văn bản; rich HTML cần sanitizer. |
| “DOMParser tự loại bỏ XSS.” | Parse trong document tạm không đồng nghĩa sanitize; node có thể nguy hiểm khi đưa vào DOM hoạt động. |
| “addEventListener và onclick giống nhau.” | addEventListener nhận callback; gán chuỗi vào event-handler attribute có thể tạo mã thực thi. |
| “URL property tự chặn javascript:.” | Phải parse và allowlist scheme/host trước khi gán. |
| “Sanitizer xong có thể nối thêm HTML tùy ý.” | Sửa output sau sanitize có thể làm mất bảo vệ; tạo node riêng bằng Safe DOM API. |
| “Trusted Types thay sanitizer.” | Trusted Types kiểm soát kiểu dữ liệu vào sink; policy vẫn phải tạo giá trị an toàn. |
| “HttpOnly ngăn mọi tác động của XSS.” | HttpOnly ngăn đọc cookie trực tiếp nhưng XSS vẫn có thể thao tác trong phiên. |
| “DOM clobbering chỉ là lỗi đặt tên.” | id/name có thể ảnh hưởng named properties và luồng logic của ứng dụng. |

## 17. Câu hỏi tự đánh giá

**Câu 1.** Vì sao textContent an toàn hơn innerHTML khi hiển thị bình luận?

**Gợi ý trả lời:** textContent tạo text node và không phân tích chuỗi thành markup; innerHTML đưa chuỗi qua HTML parser, có thể tạo element và event handler.

**Câu 2.** Gán userSuppliedUrl vào anchor.href có đủ an toàn không?

**Gợi ý trả lời:** Không. Cần parse URL và kiểm tra scheme, origin/host, port và userinfo theo chính sách trước khi gán.

**Câu 3.** Vì sao setAttribute('onclick', userInput) nguy hiểm?

**Gợi ý trả lời:** onclick là event-handler attribute; browser có thể diễn giải giá trị như mã JavaScript.

**Câu 4.** Khi nào nên dùng HTML sanitizer?

**Gợi ý trả lời:** Khi sản phẩm thực sự cần hiển thị rich HTML do nguồn không tin cậy cung cấp. Cấu hình allowlist tag/attribute/protocol, dùng thư viện được duy trì và không sửa output theo cách làm mất bảo vệ.

**Câu 5.** Trusted Types có ngăn open redirect không?

**Gợi ý trả lời:** Không. Open redirect cần URL parsing và allowlist đích; Trusted Types chỉ bảo vệ một số DOM sink.

**Câu 6.** DOMParser.parseFromString tạo document tạm. Vì sao không thể coi nội dung đã an toàn?

**Gợi ý trả lời:** Parser không loại bỏ mọi event handler, URL hoặc node nguy hiểm. Khi node được đưa vào document hoạt động, hành vi có thể được kích hoạt.

**Câu 7.** DOM clobbering có thể xảy ra qua những thuộc tính nào?

**Gợi ý trả lời:** Các thuộc tính id/name có thể tạo named properties và gây xung đột với biến hoặc logic mà ứng dụng mong đợi.

## Tài liệu tham khảo

- OWASP — [DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html), [Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).
- OWASP — [DOM Clobbering Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_Clobbering_Prevention_Cheat_Sheet.html).
- MDN — [Node.textContent](https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent), [Document.createElement()](https://developer.mozilla.org/en-US/docs/Web/API/Document/createElement), [Element.replaceChildren()](https://developer.mozilla.org/en-US/docs/Web/API/Element/replaceChildren).
- MDN — [Element.innerHTML](https://developer.mozilla.org/en-US/docs/Web/API/Element/innerHTML), [Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API), [Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP).
- DOMPurify — [Project documentation](https://github.com/cure53/DOMPurify).
