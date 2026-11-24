# URL context

**URL context** là vị trí trong ứng dụng mà dữ liệu không đáng tin cậy được dùng để tạo hoặc thay đổi một URL, ví dụ thuộc tính **href**, **src**, **action**, lời gọi **window.open()** hoặc điều hướng qua **location**. Đây là một ngữ cảnh quan trọng của **Cross-Site Scripting (XSS)** vì một URL có thể chứa scheme nguy hiểm như **javascript:**, trỏ tới website giả mạo hoặc làm trình duyệt tải nội dung không mong muốn.

Một chuỗi URL hợp lệ về cú pháp chưa chắc an toàn về ý nghĩa. Escape ký tự HTML giúp bảo vệ cú pháp thuộc tính, nhưng **không tự ngăn một URL dùng scheme nguy hiểm**. Ứng dụng cần parse URL bằng API chuẩn, kiểm tra scheme/host/port theo chính sách và encode đúng từng thành phần URL trước khi đưa dữ liệu vào sink.

Bài học thuộc chương **XSS và DOM** trong module **Browser Security** (SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY). Nội dung phân tích cách dữ liệu đi qua URL parser, HTML attribute và DOM sink; liên hệ với origin, SOP, CORS, CSP, Trusted Types và kiểm chứng hành vi thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện các URL sink như href, src, action, formAction, location và window.open().
2. Phân biệt URL context với HTML attribute context, JavaScript context và CSS context.
3. Giải thích vì sao HTML escaping hoặc percent-encoding đơn thuần không đủ để xác thực một URL.
4. Parse và canonicalize URL bằng new URL(), kiểm tra scheme, origin, hostname, port và userinfo.
5. Dùng URLSearchParams và encode từng path segment thay vì encode toàn bộ URL.
6. Phòng DOM-based XSS, open redirect và điều hướng tới URL không tin cậy.
7. Hiểu vai trò và giới hạn của CSP, Trusted Types, template auto-escaping và DOMPurify.
8. Thực hành kiểm tra URL an toàn bằng Node.js và browser DevTools.

## 2. URL context nằm ở đâu trong luồng dữ liệu?

Một URL thường có nhiều thành phần:

~~~text
https://shop.example.com:443/products?id=42#reviews
scheme / hostname / port / path / query / fragment
~~~

Khi ứng dụng nhận dữ liệu từ người dùng, dữ liệu có thể đi vào:

- Link điều hướng: thẻ a với thuộc tính href.
- Tài nguyên được tải: img src, script src, iframe src.
- Form: form action, button.formAction.
- Điều hướng JavaScript: location.href, window.location, window.open().
- Fetch/XHR: fetch(url), XMLHttpRequest.open().
- CSS URL: url(...) trong style hoặc stylesheet.

Các sink này không có cùng chính sách. Ví dụ, một URL có thể hợp lệ để mở bằng liên kết HTTPS nhưng không hợp lệ để dùng làm nguồn script. Vì thế, đừng xây một hàm “sanitize URL” chung chung rồi dùng cho mọi ngữ cảnh mà không định nghĩa chính sách cụ thể.

### Luồng xử lý và điểm cần kiểm soát

~~~mermaid
flowchart TD
    A["Nguồn dữ liệu không tin cậy<br/>query, hash, form, API, postMessage"] --> B["Parse bằng URL API"]
    B --> C["Canonicalize hostname và URL"]
    C --> D{"Chính sách URL"}
    D -->|Scheme/host/port không hợp lệ| E["Từ chối hoặc dùng URL an toàn mặc định"]
    D -->|Hợp lệ| F["Dùng trong đúng URL sink"]
    F --> G["HTML template: attribute escaping<br/>DOM: property API"]
    G --> H["Browser áp dụng CSP, SOP,<br/>cookie và navigation policy"]
~~~

Kiểm tra URL và encoding là hai công việc khác nhau. **Validation** quyết định URL có được phép dùng không; **encoding** bảo toàn cấu trúc của thành phần khi đưa dữ liệu vào URL hoặc HTML.

## 3. URL context không chỉ là HTML attribute context

Ví dụ một liên kết:

~~~html
<a href="https://example.com/search?q=security">Tìm kiếm</a>
~~~

Giá trị href là một URL nằm bên trong một HTML attribute được đặt trong dấu ngoặc kép. Khi server render HTML, có ít nhất hai lớp cần xử lý:

1. URL phải hợp lệ và được cho phép theo chính sách ứng dụng.
2. Giá trị phải được escape đúng quy tắc HTML attribute để không phá cú pháp markup.

**HTML escaping không thay URL validation.** Nếu chuỗi đã được escape thành một attribute hợp lệ nhưng URL vẫn bắt đầu bằng javascript:, trình duyệt có thể xử lý nó như một URL JavaScript trong ngữ cảnh cho phép.

### Các ngữ cảnh cần phân biệt

| Ngữ cảnh | Ví dụ sink | Phòng vệ chính |
| --- | --- | --- |
| URL trong HTML attribute | a href | Validate scheme/host theo mục đích + HTML attribute escaping |
| URL trong DOM property | anchor.href = value | Parse/validate URL trước khi gán; property API không tự lọc scheme nguy hiểm |
| URL trong JavaScript | location.href = value | Validate URL và allowlist đích; tránh inline script sinh từ dữ liệu |
| URL trong CSS | background-image: url(...) | Không nối dữ liệu tùy ý vào CSS; dùng giá trị đã kiểm tra theo chính sách tài nguyên |
| URL nguồn script | script.src = value | Allowlist nguồn script cố định, CSP và Trusted Types khi phù hợp |
| URL form đích | form.action = value | Chỉ cho phép đích nghiệp vụ dự kiến; CSP form-action là lớp bổ sung |

### Ví dụ HTML escaping chưa đủ

~~~html
<!-- Dù value được escape để giữ đúng attribute syntax,
     scheme nguy hiểm vẫn cần bị từ chối. -->
<a href="javascript:...">Mở liên kết</a>
~~~

Trong HTML, entity có thể được parser giải mã trước khi browser xử lý URL. Vì vậy lọc chuỗi theo một vài mẫu văn bản hoặc chỉ escape dấu nháy không đủ để xác định URL có an toàn hay không.

## 4. Scheme: thành phần đầu tiên cần kiểm tra

Scheme cho biết browser sẽ xử lý URL theo loại giao thức nào. Các scheme phổ biến gồm:

| Scheme | Mục đích | Chính sách thường gặp |
| --- | --- | --- |
| https: | Tài nguyên qua HTTPS | Thường được cho phép, nhưng vẫn kiểm tra host/port |
| http: | Tài nguyên HTTP không mã hóa | Thường từ chối trong ứng dụng HTTPS hoặc chỉ cho phép trong môi trường phát triển |
| javascript: | Thực thi JavaScript trong một số navigation/script URL context | Từ chối với dữ liệu không tin cậy |
| data: | URL chứa dữ liệu inline | Từ chối cho navigation/script; chỉ cho phép MIME cụ thể nếu sản phẩm thật sự cần |
| blob: | URL trỏ tới Blob được tạo trong browser | Chỉ tin URL do ứng dụng tạo và quản lý; không nhận tùy ý từ user |
| file: | Tài nguyên cục bộ | Từ chối trong ứng dụng web thông thường |
| mailto: | Mở trình xử lý email | Chỉ cho phép ở link nếu chức năng cần |
| tel: | Mở trình xử lý gọi điện | Chỉ cho phép ở link nếu chức năng cần |

Không nên chỉ tìm chuỗi javascript: bằng startsWith() trên input thô. URL parser có thể chuẩn hóa scheme, bỏ khoảng trắng ASCII ở vị trí nhất định và diễn giải URL tương đối theo base URL. Hãy parse trước, rồi kiểm tra url.protocol sau khi parse.

### 4.1. Ví dụ URL scheme nguy hiểm

Trong ngữ cảnh link, các giá trị dạng sau cần bị từ chối nếu ứng dụng chỉ cho phép điều hướng tới website HTTPS:

~~~text
javascript:...
data:text/html,...
~~~

Không cần và không nên thực thi các giá trị này để kiểm tra; có thể kiểm tra kết quả parse bằng URL API.

### 4.2. Scheme hợp lệ vẫn có thể trỏ sai nơi

https://attacker.example dùng HTTPS nhưng vẫn có thể là website phishing. Vì vậy:

- Allowlist scheme chỉ xác nhận giao thức.
- Allowlist host/origin xác định đích được phép.
- Authorization phía server quyết định người dùng được truy cập tài nguyên nào.

Không coi HTTPS là bằng chứng website thuộc thương hiệu hoặc đối tác mong muốn.

## 5. Parse URL bằng API chuẩn

Không nên xử lý URL bằng cách nối chuỗi hoặc tách theo dấu /, ?, # bằng regex. Dùng URL:

~~~js
const url = new URL('/products?id=42', 'https://shop.example.com');

console.log(url.protocol); // https:
console.log(url.hostname); // shop.example.com
console.log(url.port);     // chuỗi rỗng vì port mặc định
console.log(url.pathname); // /products
console.log(url.search);   // ?id=42
console.log(url.origin);   // https://shop.example.com
~~~

Constructor new URL(input, base) xử lý URL tương đối dựa trên base:

~~~js
new URL('/account', 'https://app.example.com');
// https://app.example.com/account
new URL('https://other.example/path', 'https://app.example.com');
// https://other.example/path
new URL('//other.example/path', 'https://app.example.com');
// https://other.example/path
~~~

Do đó, chỉ kiểm tra chuỗi có bắt đầu bằng / không là chưa đủ để xác nhận cùng origin. URL bắt đầu bằng // là protocol-relative URL và có thể trỏ sang host khác.

### 5.1. Kiểm tra same-origin

Nếu ứng dụng chỉ cho phép URL cùng origin:

~~~js
function parseSameOriginUrl(input, baseUrl) {
  try {
    const base = new URL(baseUrl);
    const target = new URL(input, base);

    if (target.protocol !== 'https:') return null;
    if (target.origin !== base.origin) return null;
    if (target.username || target.password) return null;

    return target;
  } catch {
    return null;
  }
}

const safe = parseSameOriginUrl(
  '/account?tab=security',
  'https://app.example.com',
);
if (safe) {
  window.location.assign(safe.href);
}
~~~

Trong môi trường production, base URL nên được lấy từ cấu hình tin cậy của ứng dụng hoặc từ origin đã được xác định bởi framework/server; không dùng một giá trị base tùy ý do người dùng cung cấp.

### 5.2. Allowlist host cụ thể

Nếu cần điều hướng tới một số website đối tác, kiểm tra hostname chính xác:

~~~js
const allowedHosts = new Set([
  'docs.example.com',
  'support.example.net',
]);

function parseAllowedHttpsUrl(input) {
  try {
    const url = new URL(input);
    if (url.protocol !== 'https:') return null;
    if (url.username || url.password) return null;
    if (url.port && url.port !== '443') return null;
    if (!allowedHosts.has(url.hostname)) return null;
    return url;
  } catch {
    return null;
  }
}
~~~

URL parser chuẩn hóa hostname, gồm xử lý chữ hoa/thường và IDN theo quy tắc URL. So sánh chính xác hostname giúp tránh lỗi như:

~~~text
docs.example.com.attacker.net
attacker-docs.example.com
docs.example.com@attacker.net
~~~

Không dùng hostname.endsWith('example.com') nếu không kiểm tra ranh giới nhãn; attacker-example.com cũng có suffix là example.com. Nếu chủ đích cho phép subdomain, so sánh hostname === domain || hostname.endsWith('.' + domain) sau canonicalization và chỉ khi mọi subdomain đều thuộc phạm vi tin cậy.

### 5.3. Userinfo có thể đánh lừa người đọc

URL có thể chứa userinfo trước dấu @:

~~~text
https://trusted.example@attacker.example/path
~~~

Hostname thực là attacker.example; trusted.example là phần userinfo. Với các luồng xác nhận thanh toán, đăng nhập hoặc liên kết đối tác, nên từ chối URL có username hoặc password để tránh gây nhầm lẫn.

## 6. Encode đúng thành phần URL

URL encoding bảo toàn cấu trúc của URL khi dữ liệu được đưa vào một thành phần. Không encode cả URL như một chuỗi duy nhất.

### 6.1. Query string: dùng URLSearchParams

~~~js
const url = new URL('https://shop.example.com/search');
url.searchParams.set('q', 'áo sơ mi & phụ kiện');
url.searchParams.set('page', '2');

console.log(url.href);
// Query được serialize đúng theo quy tắc URL.
~~~

URLSearchParams xử lý dấu cách, dấu &, = và Unicode trong giá trị query. Tránh tự nối:

~~~js
// Sai: giá trị có & hoặc = có thể làm thay đổi cấu trúc query.
const url = '/search?q=' + userInput;
~~~

### 6.2. Path segment: encode từng segment

Nếu thật sự cần đưa một giá trị thành một path segment:

~~~js
const productId = 'model A/blue';
const url = '/products/' + encodeURIComponent(productId);
~~~

encodeURIComponent() mã hóa các ký tự phân cách như dấu / trong giá trị. Tuy nhiên, cần kiểm tra dữ liệu nghiệp vụ và quy tắc route trước khi sử dụng. Các segment đặc biệt như . hoặc .. có ý nghĩa điều hướng path; encode không tự thay thế kiểm tra path traversal.

### 6.3. Không encode toàn bộ URL

~~~js
// Sai: làm mất cấu trúc phân tách scheme, host, path, query.
encodeURIComponent('https://example.com/search?q=hello world');
~~~

Hãy parse URL, set pathname hoặc searchParams phù hợp, rồi serialize qua url.href.

### 6.4. Không decode lặp

Một chuỗi có thể chứa percent-encoding nhiều lớp. Nếu proxy decode một lần, ứng dụng decode thêm lần nữa, hai lớp có thể hiểu dữ liệu khác nhau. Không chạy decodeURIComponent() lặp cho đến khi chuỗi “trông sạch”; parse và decode đúng một lần tại đúng ranh giới giao thức.

## 7. Các URL sink thường gặp và cách dùng an toàn

| Sink | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| a.href | Phishing, javascript:, điều hướng ngoài allowlist | Parse URL, allowlist scheme/host; đặt bằng property |
| img.src | Tải tracker hoặc tài nguyên ngoài không mong muốn; data URL không phù hợp | Allowlist HTTPS host hoặc URL do ứng dụng tạo |
| script.src | Thực thi mã bên thứ ba trong origin ứng dụng | Chỉ dùng nguồn script tin cậy, CSP, SRI/Trusted Types khi phù hợp |
| iframe.src | Nhúng trang độc hại, clickjacking hoặc nội dung không tin cậy | Allowlist origin, sandbox iframe, CSP frame-src và frame-ancestors |
| form.action | Gửi dữ liệu form tới website attacker | Chỉ cho phép endpoint dự kiến; CSP form-action |
| button.formAction | Ghi đè đích form ngoài ý muốn | Validate đích và kiểm tra DOM logic |
| location.href / assign() | Open redirect/phishing | Chỉ cho phép route hoặc origin tin cậy |
| window.open() | Điều hướng tới URL attacker; tabnabbing | Validate URL, dùng noopener và noreferrer khi phù hợp |
| fetch() / XHR | Gửi dữ liệu tới origin không tin cậy, rò rỉ token | Kiểm tra URL, CORS allowlist ở server, không gửi credential tùy tiện |
| CSS url(...) | Tải tài nguyên ngoài, khai thác parser/context | Tránh nội suy chuỗi tùy ý vào CSS; dùng nguồn đã kiểm tra |

### 7.1. Gán DOM property không tự validate URL

Đoạn này tránh HTML string parsing nhưng vẫn có thể nguy hiểm nếu userUrl không được kiểm tra:

~~~js
link.href = userUrl;
~~~

Property assignment giúp tránh một số lỗi HTML injection do nối markup, nhưng browser vẫn parse URL và có thể chấp nhận scheme không mong muốn. Hãy validate trước:

~~~js
const parsed = parseAllowedHttpsUrl(userUrl);
if (parsed) {
  link.href = parsed.href;
  link.textContent = 'Mở trang đối tác';
} else {
  link.removeAttribute('href');
  link.textContent = 'Liên kết không hợp lệ';
}
~~~

### 7.2. window.open và tabnabbing

Khi mở tab mới:

~~~js
const url = parseAllowedHttpsUrl(userProvidedUrl);
if (url) {
  window.open(url.href, '_blank', 'noopener,noreferrer');
}
~~~

noopener ngăn trang mới truy cập window.opener của trang mở; noreferrer hạn chế gửi Referer và cũng hàm ý noopener trong các browser hiện đại. Nếu không cần giữ thông tin referrer, đây là lựa chọn tốt cho liên kết mở tab mới. Quan trọng nhất vẫn là kiểm tra đích URL trước khi mở.

### 7.3. Form action

Không cho dữ liệu người dùng quyết định tùy ý nơi browser gửi form chứa thông tin nhạy cảm. Dùng endpoint do ứng dụng kiểm soát và cấu hình CSP:

~~~http
Content-Security-Policy: form-action 'self'
~~~

form-action giới hạn đích gửi form của tài liệu. Đây là lớp phòng vệ bổ sung; server vẫn phải xác minh Origin/CSRF token và quyền nghiệp vụ.

## 8. DOM-based XSS qua URL

URL thường là source của dữ liệu không đáng tin cậy:

- location.search: query string.
- location.hash: fragment.
- location.pathname: path.
- document.referrer: URL trang điều hướng tới.
- postMessage: dữ liệu từ cửa sổ/iframe khác.

Nếu đưa trực tiếp các giá trị này vào sink nguy hiểm, có thể tạo DOM-based XSS hoặc open redirect.

### 8.1. Ví dụ DOM XSS

~~~js
const message = new URLSearchParams(location.search).get('message') || '';

// Không an toàn: chuỗi từ URL đi vào HTML parser.
document.querySelector('#message').innerHTML = message;

// Phù hợp nếu chỉ hiển thị văn bản.
document.querySelector('#message').textContent = message;
~~~

Đây là ví dụ HTML context, nhưng URL là nguồn dữ liệu. Việc query string đã percent-encoded không làm nội dung trở nên an toàn; URLSearchParams giải mã giá trị query trước khi trả về.

### 8.2. Ví dụ open redirect

~~~js
const next = new URLSearchParams(location.search).get('next');
if (next) {
  // Không an toàn: người dùng có thể bị chuyển tới website giả.
  location.assign(next);
}
~~~

Sửa bằng allowlist route nội bộ:

~~~js
const allowedRoutes = new Set([
  '/account',
  '/orders',
  '/settings/security',
]);

const requested = new URLSearchParams(location.search).get('next');
const safePath = allowedRoutes.has(requested) ? requested : '/';
location.assign(safePath);
~~~

Nếu cần hỗ trợ URL tương đối phức tạp, parse bằng new URL(requested, location.origin) rồi kiểm tra target.origin === location.origin, scheme và route. Không dùng regex đơn giản để loại bỏ chuỗi http hoặc //.

### 8.3. Referrer không phải dữ liệu tin cậy

document.referrer có thể rỗng hoặc bị cắt theo Referrer-Policy. Không dùng nó làm bằng chứng xác thực, quyền truy cập hoặc nguồn gốc duy nhất của thao tác. Nếu cần xác minh request, server nên kiểm tra session, token và các header phù hợp theo threat model.

## 9. CSP và Trusted Types bảo vệ URL context như thế nào?

### 9.1. Content Security Policy

CSP cho phép server đặt chính sách tài nguyên và hành vi mà browser thực thi. Ví dụ:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-YWJjMTIz'; img-src 'self' https://images.example.com; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-src 'self' https://player.example.net; frame-ancestors 'none'
~~~

Giá trị nonce trong ví dụ chỉ minh họa cú pháp; production phải sinh nonce ngẫu nhiên mới cho mỗi response và gắn đúng cùng giá trị đó vào các script hợp lệ của response. Chính sách mẫu cần được điều chỉnh theo ứng dụng, kiểm thử ở chế độ Content-Security-Policy-Report-Only trước khi áp dụng chặn.

Một số chỉ thị:

| Chỉ thị | Liên hệ với URL context |
| --- | --- |
| script-src | Giới hạn nguồn script và ngăn nhiều dạng inline/script URL không được cho phép |
| img-src | Giới hạn nơi ảnh được tải |
| connect-src | Giới hạn endpoint cho fetch, XHR, WebSocket và một số API kết nối |
| frame-src | Giới hạn nguồn iframe mà trang được nhúng |
| form-action | Giới hạn đích gửi form |
| base-uri | Giới hạn URL base của tài liệu, giúp giảm nguy cơ thẻ base độc hại làm đổi đích URL tương đối |
| object-src | Hạn chế nội dung plugin/object cũ |
| frame-ancestors | Kiểm soát website nào được nhúng chính tài liệu này |

CSP là defense-in-depth. Nó không xác minh URL theo nghiệp vụ, không thay allowlist hostname và không thay authorization/CSRF. Ví dụ connect-src 'self' https://api.example.com giới hạn nơi browser được kết nối, nhưng server API vẫn phải xác thực và phân quyền.

### 9.2. Trusted Types

Trusted Types giúp hạn chế chuỗi tùy ý đi vào một số DOM sink nguy hiểm, chẳng hạn innerHTML và một số sink URL/script cụ thể ở browser hỗ trợ. Có thể bật enforcement bằng CSP:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html app-script-url
~~~

Trusted Types **không phải bộ kiểm tra mọi URL**. Một anchor href hoặc navigation URL vẫn cần chính sách scheme/host/origin phù hợp. Với script.src hoặc sink yêu cầu TrustedScriptURL, policy phải được thiết kế chặt, không tạo policy kiểu “tin mọi chuỗi”.

### 9.3. HTML sanitizer không thay URL policy

Nếu cho phép rich HTML, dùng sanitizer được duy trì như DOMPurify với cấu hình phù hợp để loại bỏ script và thuộc tính nguy hiểm. Tuy nhiên, vẫn cần hiểu danh sách protocol được phép, URL trong thuộc tính và cấu hình ứng dụng. Sanitizer HTML không thay cho kiểm tra URL của một redirect hoặc API fetch.

## 10. Bài thực hành: kiểm tra URL bằng Node.js

Bài thực hành dùng **Node.js 18 trở lên**, không cần package ngoài. Mục tiêu là parse nhiều URL, kiểm tra scheme/origin/host và phát hiện trường hợp URL nhìn có vẻ tin cậy nhưng thực tế trỏ sang host khác.

### 10.1. Tạo file url-context-demo.mjs

~~~js
const base = 'https://app.example.com';
const allowedHosts = new Set([
  'app.example.com',
  'docs.example.com',
]);

const samples = [
  '/account',
  'https://app.example.com/settings',
  '//attacker.example/path',
  'javascript:alert(1)',
  'data:text/html,example',
  'https://app.example.com.attacker.net/',
  'https://app.example.com@attacker.net/',
  'https://docs.example.com/guide',
  'http://app.example.com/insecure',
];

function inspectUrl(input) {
  try {
    const url = new URL(input, base);
    const allowed =
      url.protocol === 'https:' &&
      !url.username &&
      !url.password &&
      (!url.port || url.port === '443') &&
      allowedHosts.has(url.hostname);

    return {
      input,
      protocol: url.protocol,
      hostname: url.hostname,
      origin: url.origin,
      pathname: url.pathname,
      allowed,
    };
  } catch {
    return { input, allowed: false, error: 'Invalid URL' };
  }
}

console.table(samples.map(inspectUrl));
~~~

Chạy:

~~~bash
node url-context-demo.mjs
~~~

Quan sát:

- /account được resolve về origin base.
- //attacker.example/path dùng scheme HTTPS của base nhưng host khác.
- javascript: và data: bị từ chối vì không phải HTTPS.
- app.example.com.attacker.net và URL có userinfo trỏ sang host khác bị từ chối.
- Chỉ hostname nằm trong allowlist và thỏa scheme/port mới được chấp nhận.

### 10.2. Xây dựng query an toàn

~~~js
const searchUrl = new URL('/search', base);
searchUrl.searchParams.set('q', 'XSS & URL context');
searchUrl.searchParams.set('page', '1');
console.log(searchUrl.href);
~~~

Không tự nối query bằng chuỗi khi giá trị có thể chứa &, =, # hoặc Unicode. Quan sát searchUrl.search và thử đọc lại bằng searchParams.get('q').

### 10.3. Kiểm tra DOM sink trong browser

Tạo một trang HTML thử nghiệm riêng, không dùng trên website thật:

~~~html
<label>URL thử nghiệm <input id="candidate" value="/account"></label>
<button id="check">Kiểm tra</button>
<a id="result">Liên kết kết quả</a>
<pre id="status"></pre>
<script type="module">
  const candidate = document.querySelector('#candidate');
  const result = document.querySelector('#result');
  const status = document.querySelector('#status');

  document.querySelector('#check').addEventListener('click', () => {
    const parsed = parseSameOriginUrl(candidate.value, location.origin);
    if (!parsed) {
      result.removeAttribute('href');
      result.textContent = 'URL bị từ chối';
      status.textContent = 'Chỉ cho phép HTTPS cùng origin.';
      return;
    }
    result.href = parsed.href;
    result.textContent = parsed.pathname + parsed.search;
    status.textContent = 'URL hợp lệ: ' + parsed.origin;
  });

  function parseSameOriginUrl(input, baseUrl) {
    try {
      const base = new URL(baseUrl);
      const target = new URL(input, base);
      if (target.protocol !== 'https:' ||
          target.origin !== base.origin ||
          target.username ||
          target.password) return null;
      return target;
    } catch {
      return null;
    }
  }
</script>
~~~

Thử nhập /account, //attacker.example, javascript:... và https://app.example.com.attacker.net. Kiểm tra rằng liên kết chỉ được gán khi URL cùng origin và HTTPS. Ví dụ này kiểm tra URL navigation; nó không thay thế CSP hoặc kiểm soát quyền truy cập route ở server.

## 11. Checklist review URL context trong code

Khi review một thay đổi có dữ liệu đi vào URL:

1. **Xác định source:** query, hash, form, API response, local storage, postMessage hay dữ liệu server?
2. **Xác định sink:** href, src, action, formAction, script.src, iframe.src, location, window.open, fetch hay CSS url?
3. **Parse đúng:** dùng URL API và base tin cậy; không nối/tách URL bằng regex.
4. **Allowlist scheme:** thường chỉ HTTPS cho website; cho phép mailto/tel hoặc data/blob chỉ khi ngữ cảnh và nhu cầu rõ ràng.
5. **Allowlist host/origin/port:** so sánh canonical hostname/origin; tránh suffix check sai và userinfo gây nhầm.
6. **Encode đúng thành phần:** URLSearchParams cho query, encodeURIComponent cho một path segment; không encode cả URL.
7. **Escape HTML attribute:** nếu server render URL vào markup, dùng template auto-escaping hoặc encoder đúng ngữ cảnh sau khi validate URL.
8. **Không dùng sink nguy hiểm:** tránh innerHTML và nội suy URL vào JavaScript/CSS; dùng DOM property sau validation.
9. **Chặn open redirect:** dùng route nội bộ allowlist hoặc kiểm tra origin sau URL parse.
10. **Thêm CSP:** form-action, base-uri, script-src, img-src, connect-src, frame-src theo kiến trúc.
11. **Xem xét Trusted Types:** bật enforcement cho sink hỗ trợ; không coi đây là URL validator tổng quát.
12. **Kiểm thử canonicalization:** protocol-relative URL, IDN, userinfo, port, dấu chấm, backslash, percent-encoding và URL tương đối.

## 12. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Escape HTML là URL đã an toàn.” | HTML escaping bảo vệ cú pháp markup; scheme/host vẫn phải được validate. |
| “Chỉ cần chặn chuỗi javascript.” | URL parser có thể chuẩn hóa input; cần parse và allowlist scheme sau parse. |
| “URL bắt đầu bằng / luôn cùng origin.” | //host/path là protocol-relative và có thể đổi host. |
| “HTTPS nghĩa là website đáng tin.” | HTTPS bảo vệ kết nối tới hostname; không xác minh thương hiệu hay ý định nghiệp vụ. |
| “encodeURIComponent toàn bộ URL là an toàn.” | Nó phá cấu trúc URL; chỉ encode giá trị query hoặc path segment phù hợp. |
| “Gán element.href tự động sanitize.” | DOM property tránh HTML string parsing nhưng vẫn chấp nhận URL scheme theo parser. |
| “CSP thay allowlist URL.” | CSP giới hạn tải/kết nối; ứng dụng vẫn cần kiểm tra đích theo nghiệp vụ. |
| “Trusted Types kiểm tra mọi URL.” | Trusted Types bảo vệ một số DOM sink; không thay URL validation tổng quát. |
| “URL fragment không quan trọng vì không gửi lên server.” | Fragment vẫn có thể là source cho DOM-based XSS hoặc redirect phía client. |
| “Cùng origin nghĩa là mọi URL đều được phép.” | Cùng origin không thay authorization, route policy hay kiểm tra dữ liệu. |

## 13. Câu hỏi tự đánh giá

**Câu 1.** Vì sao HTML attribute escaping không đủ để bảo vệ a href?

**Gợi ý trả lời:** Nó giữ đúng cú pháp attribute nhưng không quyết định scheme/host có được phép hay không. URL scheme nguy hiểm vẫn cần bị từ chối sau khi parse.

**Câu 2.** //attacker.example/path được parse với base HTTPS có protocol nào và origin nào?

**Gợi ý trả lời:** Nó kế thừa scheme HTTPS của base nhưng dùng host attacker.example, nên origin khác.

**Câu 3.** Vì sao không dùng hostname.endsWith('example.com') để allowlist?

**Gợi ý trả lời:** Hostname như attacker-example.com cũng có suffix đó. Cần so sánh chính xác hoặc suffix có ranh giới nhãn sau canonicalization.

**Câu 4.** URLSearchParams giúp tránh lỗi nào?

**Gợi ý trả lời:** Nó serialize giá trị query đúng quy tắc, tránh dữ liệu chứa & hoặc = làm thay đổi cấu trúc query.

**Câu 5.** CSP form-action 'self' có thay thế CSRF token không?

**Gợi ý trả lời:** Không. CSP giới hạn đích form do browser thực thi; server vẫn cần xác minh ý định request, session và quyền.

**Câu 6.** Trusted Types có tự chặn open redirect không?

**Gợi ý trả lời:** Không. Open redirect cần URL parsing, allowlist origin/route và validation theo mục đích; Trusted Types chỉ bảo vệ một số DOM sink.

**Câu 7.** Vì sao URL fragment vẫn cần được xem là dữ liệu không tin cậy?

**Gợi ý trả lời:** Fragment không gửi trong HTTP request nhưng JavaScript có thể đọc location.hash và đưa vào DOM hoặc navigation sink, tạo DOM XSS/open redirect.

## Tài liệu tham khảo

- OWASP — [Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html), [DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html).
- OWASP — [Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html).
- WHATWG — [URL Standard](https://url.spec.whatwg.org/).
- MDN — [URL API](https://developer.mozilla.org/en-US/docs/Web/API/URL), [URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams), [CSP](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP).
- MDN — [Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API), [Window.open()](https://developer.mozilla.org/en-US/docs/Web/API/Window/open).
