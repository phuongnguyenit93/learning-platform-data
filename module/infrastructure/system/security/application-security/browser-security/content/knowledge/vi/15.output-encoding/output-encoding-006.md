# URL encoding: mã hóa dữ liệu đúng ngữ cảnh để bảo vệ ứng dụng web

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích percent-encoding và phân biệt URL đầy đủ, path segment, query parameter, fragment và dữ liệu form.
2. Chọn đúng API JavaScript: `encodeURIComponent()`, `encodeURI()`, `URLSearchParams` và `URL`.
3. Hiểu UTF-8, reserved characters, cách biểu diễn dấu cách và rủi ro double encoding.
4. Phân biệt URL encoding với HTML attribute encoding, JavaScript string encoding và CSS encoding.
5. Ngăn DOM XSS, open redirect và URL injection bằng cách parse, validate, allowlist rồi mới render hoặc điều hướng.
6. Kiểm chứng hành vi bằng Chrome DevTools và xây dựng URL an toàn ở frontend/backend.

> **Bối cảnh:** Module Browser Security phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web, đồng thời thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng thực tế. URL encoding là một phần của output encoding: dữ liệu phải được biểu diễn đúng theo thành phần URL đang nhận nó, sau đó vẫn cần validate URL và encode theo ngữ cảnh HTML/JavaScript/CSS nếu URL được nhúng vào các ngữ cảnh đó.

## 1. URL encoding là gì?

URL encoding thường chỉ **percent-encoding**: biểu diễn một byte bằng dấu phần trăm và hai chữ số thập lục phân. Ví dụ dấu cách trong một thành phần URL có thể được biểu diễn là `%20`; ký tự UTF-8 có thể cần nhiều chuỗi `%HH`.

```text
Original text:  hello world
Encoded value:  hello%20world

Original text:  café
UTF-8 bytes:    63 61 66 C3 A9
Encoded value:  caf%C3%A9
```

URL encoding giúp dữ liệu được truyền trong cấu trúc URL mà không vô tình trở thành delimiter của thành phần URL. Nó **không phải mã hóa bí mật**, không phải encryption và không tự làm một URL trở nên đáng tin cậy.

### Một URL có nhiều thành phần

```text
https://shop.example.test:8443/products/search?q=red%20shoes&sort=price#results
└───── scheme ─────┘ └──────── host ────────┘ └port┘ └path┘ └──── query ────┘ └fragment┘
```

| Thành phần | Ví dụ | Dữ liệu cần xử lý |
| --- | --- | --- |
| Scheme | `https:` | Giao thức; phải kiểm tra theo policy |
| Authority/host | `shop.example.test:8443` | Host/port; không tạo từ chuỗi không tin cậy |
| Path segment | `red%20shoes` | Mã hóa dữ liệu cho từng segment |
| Query parameter | `q=red%20shoes` | Mã hóa tên/giá trị từng parameter |
| Fragment | `#results` | Mã hóa giá trị fragment nếu có dữ liệu động |

**Quy tắc quan trọng:** không encode cả URL một cách mù quáng. Nếu encode nguyên URL, các delimiter như `://`, `/`, `?`, `=` và `#` cũng có thể bị biến thành dữ liệu, làm hỏng cấu trúc. Hãy xây dựng URL bằng API hiểu cấu trúc, rồi encode đúng từng thành phần.

## 2. Reserved characters và query injection

URL có các ký tự phân cách cấu trúc, thường gọi là **reserved characters**, ví dụ:

```text
: / ? # [ ] @
! $ & ' ( ) * + , ; =
```

Ý nghĩa của ký tự phụ thuộc vị trí:

- `/` phân tách path segment.
- `?` bắt đầu query.
- `&` phân tách query parameter.
- `=` phân tách tên và giá trị parameter.
- `#` bắt đầu fragment.
- `@` có vai trò trong authority/userinfo.

Nếu dữ liệu người dùng chứa `&` mà được nối trực tiếp vào query, nó có thể tạo thêm parameter ngoài dự kiến.

Không an toàn:

```js
const search = "red&admin=true";
const url = "/search?q=" + search;
console.log(url);
// /search?q=red&admin=true
```

Server có thể hiểu thành hai parameter: `q=red` và `admin=true`. Hãy dùng URL API:

```js
const url = new URL("/search", window.location.origin);
url.searchParams.set("q", "red&admin=true");
console.log(url.href);
// https://current-host.example/search?q=red%26admin%3Dtrue
```

`URLSearchParams` mã hóa giá trị parameter theo quy tắc form URL encoding khi serialize, giữ `&` và `=` bên trong dữ liệu thay vì biến chúng thành delimiter mới.

## 3. Chọn API JavaScript đúng mục đích

### `encodeURIComponent()`: một thành phần dữ liệu

Dùng cho một giá trị độc lập như query value, path segment hoặc fragment component:

```js
const value = "red shoes & bags";
const encoded = encodeURIComponent(value);
console.log(encoded);
// red%20shoes%20%26%20bags
```

API này encode các ký tự có thể làm thay đổi cấu trúc thành phần. Nó vẫn để nguyên một số ký tự như `! ' ( ) * - _ . ~`; nếu cần chuẩn hóa chặt theo RFC 3986 cho ứng dụng cụ thể, phải định nghĩa policy và kiểm thử encoder tương ứng.

### `encodeURI()`: URL đã có cấu trúc

`encodeURI()` dành cho một URI đã có cấu trúc, giữ lại nhiều delimiter cần thiết:

```js
const uri = "https://shop.example.test/search?q=red shoes&sort=price";
console.log(encodeURI(uri));
// https://shop.example.test/search?q=red%20shoes&sort=price
```

`encodeURI()` **không** encode các delimiter như `?`, `&` hoặc `=`. Nếu dữ liệu không tin cậy được nối vào URL trước khi gọi API này, dữ liệu vẫn có thể thay đổi cấu trúc URL. Vì vậy, API này không thay thế việc xây dựng URL theo từng thành phần.

### `URL` và `URLSearchParams`: ưu tiên cho URL động

```js
const url = new URL("https://api.example.test/search");
url.searchParams.set("q", "café & tea");
url.searchParams.set("page", "2");
url.searchParams.set("sort", "newest");
console.log(url.href);
// https://api.example.test/search?q=caf%C3%A9+%26+tea&page=2&sort=newest
```

`URLSearchParams` sử dụng quy tắc `application/x-www-form-urlencoded` khi serialize query: dấu cách thường thành `+`, còn dấu cộng literal được encode thành `%2B`. Browser/server parse query tương ứng sẽ khôi phục đúng giá trị.

| API | Dùng khi | Tránh dùng khi |
| --- | --- | --- |
| `encodeURIComponent(value)` | Encode một component độc lập | Encode nguyên URL đầy đủ |
| `encodeURI(uri)` | Encode một URI đã được cấu trúc trước đó | Bảo vệ dữ liệu không tin cậy được nối vào delimiter |
| `URLSearchParams` | Tạo/serialize query parameters | Xây dựng authority hoặc path segment phức tạp |
| `new URL(input, base)` | Parse và xây URL có cấu trúc | Thay thế kiểm tra scheme/host/redirect policy |

### Encode path segment riêng biệt

Nếu một ID được đặt trong một path segment, encode chính segment đó:

```js
const productId = "sku/42 blue";
const path = "/products/" + encodeURIComponent(productId);
console.log(path);
// /products/sku%2F42%20blue
```

Không encode cả path sau khi đã ghép các segment, vì dấu slash dùng để phân tách route cũng có thể bị encode. Kiểm tra cách reverse proxy, web server và framework route xử lý encoded slash; một số hệ thống từ chối hoặc decode nó ở các giai đoạn khác nhau.

## 4. Dấu cách, dấu cộng và UTF-8

Có hai biểu diễn thường gặp của dấu cách:

| Ngữ cảnh | Dấu cách thường serialize thành |
| --- | --- |
| Percent-encoding của URI component | `%20` |
| Query theo `application/x-www-form-urlencoded` | `+` |

Đừng tự thay mọi dấu `+` thành dấu cách nếu chưa biết parser đang xử lý loại dữ liệu nào. Trong form encoding, dấu cộng literal phải được biểu diễn thành `%2B`.

```js
const params = new URLSearchParams();
params.set("q", "C++ tutorial");
console.log(params.toString());
// q=C%2B%2B+tutorial
console.log(new URLSearchParams("q=C%2B%2B+tutorial").get("q"));
// C++ tutorial
```

Percent-encoding biểu diễn **byte**, không trực tiếp biểu diễn ký tự Unicode. Web URL APIs dùng UTF-8 để chuyển chuỗi Unicode thành byte trước khi percent-encode. Ví dụ `é` có byte UTF-8 `C3 A9`, nên được biểu diễn `%C3%A9`.

Khi xử lý URL ở frontend và backend:

- Thống nhất UTF-8.
- Chỉ decode đúng số lần theo giao thức; không decode lặp tùy tiện.
- Không so sánh chuỗi đã encode với chuỗi đã decode mà không chuẩn hóa cùng một cách.
- Kiểm thử Unicode normalization nếu ứng dụng dùng tên người dùng, slug hoặc ID chứa ký tự Unicode.

## 5. Double encoding và canonicalization

**Double encoding** xảy ra khi một giá trị đã được percent-encode lại bị encode lần nữa:

```js
const once = encodeURIComponent("a/b");
console.log(once); // a%2Fb
const twice = encodeURIComponent(once);
console.log(twice); // a%252Fb
```

`%25` là cách biểu diễn dấu phần trăm. Khi một tầng decode một lần, kết quả có thể vẫn còn `%2F`; tầng tiếp theo decode nữa sẽ tạo dấu slash. Nếu proxy, framework và ứng dụng decode số lần khác nhau, cùng một đầu vào có thể được diễn giải thành các route khác nhau.

Các biến thể như:

```text
../admin
%2e%2e%2fadmin
%252e%252e%252fadmin
```

có thể bị các tầng khác nhau chuẩn hóa hoặc decode khác nhau. Không dùng URL encoding như biện pháp chống path traversal. Server phải parse request nhất quán, chuẩn hóa theo framework, xác thực quyền truy cập tài nguyên và tránh decode lần thứ hai một giá trị đã được framework decode.

**Canonicalization** là việc đưa dữ liệu về một dạng chuẩn trước khi so sánh/chính sách. Phải xác định rõ thành phần nào được normalize, decode ở đâu và bao nhiêu lần. Đừng tự viết nhiều lớp replace/decode để “làm sạch” URL.

## 6. URL encoding không thay thế validation

Percent-encoding chỉ thay đổi cách biểu diễn dữ liệu. Nó không quyết định URL có an toàn để điều hướng, fetch, nhúng hoặc chuyển hướng hay không.

| Scheme | Ví dụ | Đánh giá |
| --- | --- | --- |
| `https:` | `https://docs.example.test` | Thường phù hợp cho liên kết web nếu host được phép |
| `http:` | `http://docs.example.test` | Có thể gây downgrade/mixed content; thường không nên cho trong liên kết nhạy cảm |
| `javascript:` | `javascript:alert(1)` | Có thể thực thi script trong ngữ cảnh hỗ trợ; không chấp nhận từ dữ liệu không tin cậy |
| `data:` | `data:text/html,...` | Có thể chứa nội dung chủ động; không cho phép tùy tiện |
| `blob:` | `blob:https://app.example.test/...` | URL tạm do môi trường tạo; chỉ dùng nếu luồng ứng dụng kiểm soát nguồn |
| `mailto:`/`tel:` | `mailto:support@example.test` | Có thể cho phép có chủ đích cho liên kết tương ứng |

Một payload `javascript:...` không trở nên an toàn chỉ vì một số ký tự đã percent-encode. Browser có thể parse, chuẩn hóa hoặc decode URL ở các bước khác nhau; hãy kiểm tra scheme sau khi parse bằng URL API và áp dụng allowlist.

### Validate URL trước khi dùng

Ví dụ chỉ cho phép HTTPS và hai host tài liệu tin cậy:

```js
const allowedHosts = new Set([
  "docs.example.test",
  "support.example.test"
]);

function getTrustedExternalUrl(input) {
  let url;
  try {
    url = new URL(input);
  } catch {
    return null;
  }

  if (url.protocol !== "https:") return null;
  if (!allowedHosts.has(url.hostname)) return null;
  if (url.username || url.password) return null;

  return url;
}

const safeUrl = getTrustedExternalUrl(userSuppliedUrl);
if (safeUrl) {
  link.href = safeUrl.href;
} else {
  // Không render link; hiển thị lỗi hoặc dùng đích nội bộ mặc định.
}
```

Nếu policy cho phép port tùy chỉnh, phải kiểm tra `url.port` rõ ràng. Ví dụ trên chỉ allowlist hostname và HTTPS; nếu ứng dụng chỉ cho port mặc định, cần thêm điều kiện port phù hợp. URL parser chuẩn hóa hostname; allowlist phải chứa giá trị đã chuẩn hóa theo policy xác định.

**Đừng dùng `hostname.endsWith("example.test")`** để kiểm tra host; tốt nhất là exact set. `evil-example.test` hoặc `example.test.attacker.test` không phải host được phép.

## 7. Chống open redirect

Open redirect xảy ra khi ứng dụng chuyển hướng người dùng tới URL do bên ngoài kiểm soát:

```js
// SAI: URL đích lấy trực tiếp từ query string
const next = new URLSearchParams(location.search).get("next");
if (next) {
  window.location.assign(next);
}
```

Kẻ tấn công có thể gửi link tới domain thật của ứng dụng với tham số `next=https://evil.test/login`; người dùng nhìn thấy domain đáng tin ban đầu nhưng sau đó bị chuyển sang trang giả mạo.

### Cách an toàn: chỉ cho phép đường dẫn nội bộ cụ thể

```js
const allowedPaths = new Set([
  "/account",
  "/orders",
  "/checkout/complete"
]);

function getSafeInternalPath(value) {
  if (typeof value !== "string") return null;
  if (!value.startsWith("/") || value.startsWith("//")) return null;

  let url;
  try {
    url = new URL(value, window.location.origin);
  } catch {
    return null;
  }

  if (url.origin !== window.location.origin) return null;
  if (!allowedPaths.has(url.pathname)) return null;
  return url.pathname + url.search + url.hash;
}

const destination = getSafeInternalPath(
  new URLSearchParams(location.search).get("next")
);

if (destination) {
  window.location.assign(destination);
}
```

Với ứng dụng thực, allowlist path cần tính đến route động và query được phép. Cũng cần xác minh ở **server redirect endpoint**; kiểm tra chỉ ở JavaScript không bảo vệ endpoint chuyển hướng phía backend. Kiểm tra thêm các biến thể URL đã chuẩn hóa, encoded separator và quy tắc xử lý dấu gạch chéo của proxy/framework.

Nếu sản phẩm phải redirect tới nhiều domain đối tác, cấu hình exact origin allowlist phía server, giới hạn scheme HTTPS và kiểm tra URL cuối cùng theo policy. Không dùng wildcard hoặc substring.

## 8. Output encoding theo ngữ cảnh: URL nằm trong HTML, JavaScript hay CSS?

URL encoding là một lớp trong chuỗi xử lý. Khi URL được đưa vào HTML, JavaScript hoặc CSS, còn phải xử lý **ngữ cảnh output bên ngoài**.

### URL trong HTML attribute

```html
<a href="https://docs.example.test/search?q=red%20shoes">
  Tìm tài liệu
</a>
```

Có hai việc riêng:

1. Xây URL và encode đúng query/path component.
2. HTML-attribute-encode giá trị URL khi render vào `href` (framework template hiện đại thường tự escape attribute).

Nếu giá trị URL có ký tự quote, ampersand hoặc dấu ngoặc nhọn và được ghép thẳng vào HTML string, có thể tạo HTML injection dù query component đã được encode một phần. Không tự tắt auto-escaping của template.

Ưu tiên DOM API:

```js
const link = document.createElement("a");
const url = new URL("/search", window.location.origin);
url.searchParams.set("q", userQuery);
link.href = url.href;
link.textContent = "Kết quả tìm kiếm";
document.querySelector("#results").append(link);
```

DOM API tránh việc tự ghép HTML; vẫn cần validate URL nếu URL đích đến từ input không tin cậy.

### URL trong JavaScript

Không chèn trực tiếp chuỗi không tin cậy vào mã JavaScript inline:

```html
<!-- SAI: dữ liệu có thể phá vỡ string/script context -->
<script>
  const next = 'USER_INPUT';
</script>
```

Ưu tiên tải dữ liệu qua JSON/API hoặc gắn giá trị vào DOM bằng API an toàn. Nếu phải serialize dữ liệu vào script, dùng serializer JSON phù hợp với template engine và bảo đảm escape các ký tự có thể kết thúc thẻ script trong HTML parser; chỉ dùng JSON.stringify không tự động bảo vệ mọi ngữ cảnh HTML template.

### URL trong CSS

Không ghép input không tin cậy trực tiếp vào CSS:

```css
/* Không tạo CSS bằng cách nối chuỗi input */
.preview {
  background-image: url("USER_INPUT");
}
```

CSS có parser và quy tắc escape riêng. Nếu cần hiển thị ảnh do người dùng chọn, validate scheme/host/type theo policy rồi gán qua DOM/CSS API phù hợp; không coi URL encoding là CSS escaping.

### Bảng chọn output encoding

| Nơi dữ liệu được đặt | Biện pháp |
| --- | --- |
| Query parameter | URLSearchParams hoặc encodeURIComponent cho value |
| Một path segment | encodeURIComponent cho segment; kiểm tra quy tắc encoded slash |
| URL đầy đủ | URL parser/builder; validate scheme, host, port và redirect policy |
| HTML href/src attribute | Xây URL trước, sau đó HTML attribute encoding hoặc DOM property |
| JavaScript string/script | Serialize dữ liệu đúng ngữ cảnh; ưu tiên tránh inline script động |
| CSS value/url() | CSS-specific handling; tránh ghép CSS từ input không tin cậy |

## 9. Ví dụ backend Java

### Dùng URI builder thay vì nối chuỗi

Với Spring, có thể dùng `UriComponentsBuilder` để xây URL:

```java
import org.springframework.web.util.UriComponentsBuilder;

String url = UriComponentsBuilder
    .fromUriString("https://api.example.test/search")
    .queryParam("q", userQuery)
    .queryParam("page", page)
    .build()
    .encode()
    .toUriString();
```

Builder xử lý cấu trúc URL và encode các component theo API; vẫn cần kiểm tra host/scheme nếu base URL hoặc đích redirect đến từ dữ liệu không tin cậy. Base URL nên là cấu hình server, không lấy tùy tiện từ request.

### Java URLEncoder không phải generic URL encoder

`URLEncoder` trong Java encode theo quy tắc **application/x-www-form-urlencoded**, phù hợp cho form/query parameter value trong ngữ cảnh tương ứng. Nó không phải công cụ để encode nguyên URL hoặc path segment:

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

String value = "red shoes & bags";
String encoded = URLEncoder.encode(value, StandardCharsets.UTF_8);
// red+shoes+%26+bags
```

Nếu dùng cho query parameter, hãy để URI builder quản lý delimiter và value thay vì tự ghép toàn bộ URL. Không dùng kết quả form encoding làm path segment nếu chưa xác định rõ quy tắc mong muốn.

## 10. Kiểm chứng bằng Chrome DevTools

Thực hiện trong ứng dụng thử nghiệm hoặc trang local do bạn kiểm soát.

### Bài A — Query parameter có ký tự delimiter

Trong Console:

```js
const input = "red&admin=true + café";
const url = new URL("/search", window.location.origin);
url.searchParams.set("q", input);
console.log(url.href);
console.log(url.searchParams.get("q"));
```

Kiểm tra:

1. Tab Network: request URL chứa một parameter `q` với value đã encode.
2. Server nhận `q` đúng bằng chuỗi đầu vào.
3. Không xuất hiện parameter `admin` ngoài dự kiến.

### Bài B — So sánh encoder

```js
const value = "a/b?c=d&e=f + café";
console.table({
  component: encodeURIComponent(value),
  uri: encodeURI(value),
  form: new URLSearchParams({ q: value }).toString()
});
```

Quan sát delimiter nào được giữ lại và delimiter nào trở thành dữ liệu. Giải thích vì sao `encodeURI` không thích hợp để encode một query value độc lập.

### Bài C — Thử URL scheme không được phép

Với hàm validate ở mục 6, thử:

```js
[
  "https://docs.example.test/guide",
  "http://docs.example.test/guide",
  "javascript:alert(1)",
  "data:text/html,example",
  "https://docs.example.test.attacker.test/",
  "https://user@docs.example.test/"
].map(value => ({
  value,
  accepted: Boolean(getTrustedExternalUrl(value))
}));
```

Chỉ URL HTTPS có host chính xác trong allowlist và không có userinfo mới được chấp nhận theo policy mẫu.

### Bài D — Kiểm tra open redirect

Thử các giá trị `next` bằng một mảng trong Console:

```js
[
  "/account",
  "//evil.test/",
  "https://evil.test/",
  "/%2f%2fevil.test/",
  "/orders"
].map(value => ({
  value,
  accepted: Boolean(getSafeInternalPath(value))
}));
```

Ghi lại giá trị nào được hàm allowlist path chấp nhận. Kiểm tra thêm ở server vì URL parser và proxy/framework có thể chuẩn hóa encoded separator theo quy tắc riêng.

### Ma trận kiểm thử

| Ca kiểm thử | Input | Kết quả mong đợi |
| --- | --- | --- |
| Query có ampersand | `red&admin=true` | Một value `q`, không tạo parameter `admin` |
| Query có dấu cộng literal | `C++` | Decode phía server vẫn là `C++` |
| Query có Unicode | `café` | Round-trip UTF-8 chính xác |
| Path segment có slash | `sku/42` | Slash được encode trong segment; kiểm tra server routing |
| URL scheme nguy hiểm | `javascript:` | Bị từ chối bởi scheme allowlist |
| Host giả | `docs.example.test.attacker.test` | Bị từ chối bởi exact host allowlist |
| URL redirect ngoài | `https://evil.test/` | Bị từ chối bởi same-origin/path policy |
| Double encoding | `%252e%252e%252f` | Không decode lặp; kiểm tra canonicalization ở server |
| HTML attribute injection | Dữ liệu chứa quote/ampersand | Template/DOM API không tạo attribute ngoài ý muốn |

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng encodeURI cho query value | `&` và `=` có thể vẫn là delimiter | Dùng URLSearchParams hoặc encodeURIComponent |
| Encode nguyên URL bằng encodeURIComponent | URL bị biến thành một chuỗi dữ liệu, mất cấu trúc | Xây URL bằng URL API |
| Nối input vào query/path trước khi encode | Query injection hoặc route thay đổi | Encode từng component trước khi thêm vào URL |
| Dùng URL encoding để ngăn XSS trong HTML | Không bảo vệ HTML/JS/CSS context | Encode đúng context output hoặc dùng DOM API |
| Chỉ encode nhưng không validate scheme | javascript: hoặc scheme không mong muốn vẫn có thể được dùng | Parse URL và allowlist protocol |
| Kiểm tra host bằng substring | Chấp nhận host giả | So sánh hostname/origin chính xác |
| Decode nhiều lần | Tạo delimiter hoặc path traversal sau một tầng decode khác | Chuẩn hóa một lần theo giao thức, tránh decode lại |
| Dùng URLEncoder cho cả URL/path | Dấu cách và delimiter bị xử lý theo form semantics | Dùng URI builder hoặc encoder đúng component |
| Tin URL đã percent-encode là an toàn | Encoding không xác minh đích hoặc quyền truy cập | Validate URL, authorize phía server |
| Chỉ kiểm tra redirect ở frontend | Endpoint redirect server vẫn có thể bị lạm dụng | Validate redirect đích ở server |

## 12. Câu hỏi củng cố

**Câu 1.** Vì sao `encodeURIComponent("red&admin=true")` phù hợp hơn `encodeURI()` khi giá trị được đặt trong query parameter `q`?

**Giải đáp:** Query value là một component dữ liệu. `encodeURIComponent` encode `&` và `=` để chúng không tạo parameter mới; `encodeURI` giữ nhiều delimiter của URL.

**Câu 2.** `URLSearchParams` có thể biến dấu cách thành `+`. Đây có phải lỗi không?

**Giải đáp:** Không. Đây là quy tắc serialize của `application/x-www-form-urlencoded`; parser tương ứng giải mã đúng. Dấu cộng literal được encode thành `%2B`.

**Câu 3.** Nếu URL chứa `%252F`, server có nên decode cho đến khi không còn `%` không?

**Giải đáp:** Không. Decode lặp có thể biến dữ liệu thành delimiter sau nhiều tầng và tạo lỗi canonicalization/path traversal. Xác định đúng số lần decode theo framework/protocol.

**Câu 4.** URL `javascript:alert(1)` đã được percent-encode một phần có thể mặc nhiên an toàn để gán vào `href` không?

**Giải đáp:** Không. Encoding không phải validation. Parse URL, kiểm tra protocol/host theo allowlist và chỉ sau đó mới gán vào DOM.

**Câu 5.** URL query value đã được encode có cần HTML attribute encoding khi render vào `href` không?

**Giải đáp:** Có. URL component encoding xử lý cấu trúc URL; HTML attribute encoding bảo vệ ngữ cảnh HTML bên ngoài. Hai bước giải quyết hai parser khác nhau.

## 13. Tổng kết

URL encoding là cách biểu diễn dữ liệu theo **thành phần URL**. Dùng `URL`/`URLSearchParams` để xây URL có cấu trúc, `encodeURIComponent` cho một component độc lập, và chỉ dùng `encodeURI` cho URI đã có cấu trúc. Hiểu UTF-8, dấu cách, reserved characters và tránh double encoding giúp request được diễn giải nhất quán qua browser, proxy và backend.

Encoding không thay validation hay authorization. Trước khi điều hướng hoặc render URL, hãy parse và kiểm tra scheme, host, port, đích redirect; khi đặt URL vào HTML/JavaScript/CSS, tiếp tục xử lý đúng output context. Với ứng dụng bảo mật, kết hợp cách xử lý này với CSP, Trusted Types, kiểm tra phía server và kiểm thử thực tế bằng DevTools.

## Tài liệu tham khảo

1. [WHATWG — URL Standard](https://url.spec.whatwg.org/): cấu trúc URL, parser, percent-encoding và URLSearchParams.
2. [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): reserved characters và percent-encoding.
3. [MDN — encodeURIComponent()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURIComponent): encode một URI component.
4. [MDN — encodeURI()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURI): encode URI đã có cấu trúc.
5. [MDN — URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams): xử lý query parameters và form serialization.
6. [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding theo ngữ cảnh và phòng XSS.
7. [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): kiểm soát đích redirect.
