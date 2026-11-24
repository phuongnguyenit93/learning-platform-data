# Percent encoding trong URL

> **Chương:** URL và encoding  
> **Chủ đề:** Percent encoding  
> **Module:** `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY` — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích percent encoding biểu diễn octet trong URL như thế nào và vì sao Unicode thường được mã hóa qua UTF-8.
2. Phân biệt ký tự dành riêng làm dấu phân cách với dữ liệu cần đặt trong một URL component.
3. Chọn đúng `encodeURI`, `encodeURIComponent`, `URL` và `URLSearchParams` trong JavaScript.
4. Phân biệt dấu cách `%20` với quy ước dấu cộng `+` của `application/x-www-form-urlencoded`.
5. Nhận diện lỗi decode nhiều lần, giải mã sai thứ tự và các rủi ro canonicalization như path traversal, parameter confusion và XSS.
6. Kiểm chứng giá trị thô trên HTTP request và giá trị sau parse/decode bằng một server Node.js cục bộ.

## 1. Percent encoding là gì?

**Percent encoding** (mã hóa phần trăm) là cách biểu diễn một octet trong URI/URL bằng ba ký tự ASCII:

`%HH`

Trong đó `%` mở đầu, còn `HH` là hai chữ số hệ thập lục phân biểu diễn giá trị octet từ `00` đến `FF`. Ví dụ:

| Ký tự dữ liệu | Biểu diễn percent-encoded | Ý nghĩa |
|---|---|---|
| Dấu cách | `%20` | Octet `0x20` |
| Dấu `%` | `%25` | Octet `0x25` |
| Dấu `&` | `%26` | Octet `0x26` |
| Dấu `/` | `%2F` | Octet `0x2F` |
| Chữ `é` trong UTF-8 | `%C3%A9` | Hai octet `C3 A9` |

Percent encoding giúp biểu diễn dữ liệu có ký tự không phù hợp với cú pháp URL hoặc có ý nghĩa đặc biệt trong một thành phần URL. Nó **không phải mã hóa bí mật, không phải encryption và không phải sanitization**. Ai cũng có thể decode một chuỗi percent-encoded.

### 1.1. Mã hóa Unicode qua UTF-8

Khi cần đưa văn bản Unicode vào URL, quy trình thông thường là:

1. Mã hóa chuỗi Unicode thành các byte theo UTF-8.
2. Với mỗi byte cần escape, viết `%` theo sau bởi hai chữ số hex.

Ví dụ từ `Đăng nhập`:

```text
Văn bản:             Đăng nhập
UTF-8 bytes:         C4 90  C4 83 6E 67 20 6E 68 E1 BA AD 70
Percent-encoded:     %C4%90%C4%83ng%20nh%E1%BA%ADp
```

Một ký tự Unicode có thể được biểu diễn bởi nhiều byte UTF-8, vì vậy không phải mỗi ký tự Unicode tương ứng với đúng một `%HH`. Khi decode, các byte phải tạo thành chuỗi hợp lệ theo encoding được quy định; với URL web hiện đại, UTF-8 là lựa chọn chuẩn.

## 2. URL có cấu trúc: phải encode đúng thành phần

Một URL thường có dạng:

```text
https://user:pass@shop.example.test:8443/products/item?id=10&lang=vi#reviews
└─┬─┘   └──────┬──────┘ └────────┬────────┘ └─┬─┘ └────────┬────────┘ └──┬──┘
scheme       authority         host/port    path          query       fragment
```

Các thành phần có cú pháp và dấu phân cách riêng:

| Thành phần | Ví dụ | Ký tự có ý nghĩa cấu trúc |
|---|---|---|
| Scheme | `https:` | `:` |
| Authority | `user@host:port` | `@`, `:` |
| Path | `/products/item` | `/` phân tách segment |
| Query | `id=10&lang=vi` | `?` mở query, `&` phân tách cặp, `=` phân tách tên/giá trị |
| Fragment | `#reviews` | `#` mở fragment |

Các ký tự như `/`, `?`, `#`, `&` có thể là **delimiter**. Nếu chúng là dữ liệu của một giá trị, phải encode trong đúng component. Ví dụ giá trị tìm kiếm `red & blue` không được nối thẳng vào query theo cách làm dấu `&` trở thành dấu phân tách tham số.

### 2.1. Reserved và unreserved characters

RFC 3986 chia một số ký tự thành các nhóm:

- **Unreserved:** chữ cái ASCII, chữ số, `-`, `.`, `_`, `~`. Những ký tự này có thể xuất hiện trực tiếp trong nhiều component.
- **Gen-delimiters:** `: / ? # [ ] @`.
- **Sub-delimiters:** `! $ & ' ( ) * + , ; =`.

Reserved characters có thể mang ý nghĩa cấu trúc tùy component. Encode một reserved character có thể biến delimiter thành dữ liệu; decode sớm có thể biến dữ liệu thành delimiter. Vì vậy, **không encode hoặc decode toàn bộ URL bằng một thao tác chung**.

Ví dụ, dấu `/` trong path thường phân tách segment:

```text
Path:        /files/a/b
Hai segment: "a" và "b"

Path:        /files/a%2Fb
Một segment được biểu diễn: "a/b"
```

Tuy nhiên, một số proxy, web server hoặc framework decode `%2F` trước khi định tuyến, khiến nó trở thành `/`. Hành vi này phụ thuộc stack triển khai. Không dùng `%2F` như một ranh giới bảo mật đáng tin cậy nếu các tầng xử lý URL không thống nhất.

### 2.2. Percent encoding không thay đổi origin

Origin của URL HTTP(S) được xác định từ **scheme, host và port**. Thay đổi percent encoding trong path, query hoặc fragment không làm origin thay đổi:

- `https://app.example.test/a%2Fb`
- `https://app.example.test/a/b`
- `https://app.example.test/search?q=%26`

Các URL trên cùng scheme/host/port nên cùng origin, dù path/query được parse hoặc diễn giải khác nhau. Khi phân tích SOP/CORS, **percent encoding không phải cách vượt qua ranh giới origin**.

Fragment được browser xử lý phía client và **không được gửi trong HTTP request target**. Ví dụ `https://example.test/page#section` gửi request cho `/page`, không gửi `#section` tới server.

## 3. Mã hóa từng component trong JavaScript

### 3.1. `encodeURI()`: mã hóa một URI đã có cấu trúc

`encodeURI()` được dùng khi đã có một URI hoàn chỉnh và muốn escape những ký tự không phù hợp, đồng thời giữ lại các delimiter có ý nghĩa trong URI như `:`, `/`, `?`, `&`, `=` và `#`.

```js
const uri = 'https://example.test/search?q=red blue&sort=recent';
console.log(encodeURI(uri));
// https://example.test/search?q=red%20blue&sort=recent
```

Không dùng `encodeURI()` cho một giá trị query chưa được gắn vào URL. Nếu giá trị có `&` hoặc `#`, chúng vẫn được giữ như delimiter và có thể làm thay đổi cấu trúc URL.

### 3.2. `encodeURIComponent()`: mã hóa một giá trị component

`encodeURIComponent()` phù hợp hơn khi cần encode một giá trị query, một path segment hoặc dữ liệu nằm trong một component riêng:

```js
const searchTerm = 'red & blue / Đà Nẵng';
const encoded = encodeURIComponent(searchTerm);

console.log(encoded);
// red%20%26%20blue%20%2F%20%C4%90%C3%A0%20N%E1%BA%B5ng
```

Hàm này encode các ký tự có thể đóng vai trò delimiter như `&`, `/`, `?`, `#`, `=`. Tuy nhiên, nó vẫn để nguyên một số ký tự như `!`, `'`, `(`, `)`, `*`; nếu một giao thức yêu cầu cách escape nghiêm ngặt theo RFC 3986, có thể chuẩn hóa thêm:

```js
function encodeRFC3986Component(value) {
  return encodeURIComponent(value).replace(/[!'()*]/g, (char) => {
    return '%' + char.charCodeAt(0).toString(16).toUpperCase();
  });
}
```

Không nên tự viết hàm percent encoder bằng cách thay vài ký tự phổ biến. Unicode, byte UTF-8, dấu `%` và các reserved characters dễ khiến hàm tự chế không tương thích với parser.

### 3.3. So sánh nhanh

| Hàm | Đầu vào phù hợp | Hành vi |
|---|---|---|
| `encodeURI(uri)` | Một URI đã có cấu trúc | Giữ lại các delimiter URI |
| `encodeURIComponent(value)` | Một component/giá trị riêng | Encode cả nhiều delimiter |
| `decodeURI(uri)` | URI đã encode | Decode một số escape, giữ escape của reserved characters |
| `decodeURIComponent(value)` | Một component đã encode | Decode percent escapes trong component |

Ví dụ nguy hiểm:

```js
const value = 'admin&role=owner';

// Sai: encodeURI giữ nguyên dấu &, tạo thêm một query parameter.
const bad = 'https://app.example.test/search?q=' + encodeURI(value);

// Đúng hơn: encode giá trị riêng, dấu & trở thành dữ liệu.
const good = 'https://app.example.test/search?q=' +
  encodeURIComponent(value);
```

Kết quả mong muốn là một tham số `q` có giá trị `admin&role=owner`, không phải hai tham số `q=admin` và `role=owner`.

## 4. Dùng URL và URLSearchParams thay cho nối chuỗi

Với ứng dụng web, API `URL` và `URLSearchParams` giúp tạo URL theo cấu trúc:

```js
const url = new URL('/search', 'https://app.example.test');
url.searchParams.set('q', 'red & blue / Đà Nẵng');
url.searchParams.set('page', '2');

console.log(url.href);
console.log(url.searchParams.get('q'));
console.log(url.origin);
```

`URLSearchParams` xử lý encode/decode tên và giá trị query theo quy ước form URL encoded. Dùng `.set()` để đặt giá trị, `.append()` khi thật sự cần tham số lặp, `.get()` để lấy giá trị đầu tiên và `.getAll()` để lấy tất cả giá trị cùng tên.

Đối với path, encode từng **segment**, không encode toàn bộ URL:

```js
const fileId = 'report 2026/phase 1';
const url = new URL('/files/' + encodeURIComponent(fileId),
  'https://files.example.test');

console.log(url.pathname);
// /files/report%202026%2Fphase%201
```

Ở ví dụ này, dấu `/` trong `fileId` được biểu diễn như dữ liệu của segment. Nhưng trước khi dùng cách này trong hệ thống thật, cần xác nhận reverse proxy và framework giữ nguyên `%2F` tới tầng route. Nếu chúng tự decode, hãy thiết kế route và validation sao cho không phụ thuộc vào hành vi không nhất quán.

### 4.1. Dấu cách `%20` và dấu cộng `+`

Một nhầm lẫn phổ biến là cho rằng `+` luôn có nghĩa dấu cách trong mọi URL. Thực tế:

- Trong URI thông thường, dấu cách thường được percent-encode thành `%20`.
- Trong định dạng `application/x-www-form-urlencoded` (được dùng bởi HTML form và `URLSearchParams`), dấu cách được serialize thành `+`.
- Một dấu cộng thực sự trong dữ liệu form phải được encode thành `%2B`.

Ví dụ:

```js
const params = new URLSearchParams();
params.set('q', 'C++ tutorial');

console.log(params.toString());
// q=C%2B%2B+tutorial

const parsed = new URLSearchParams('q=C%2B%2B+tutorial');
console.log(parsed.get('q'));
// C++ tutorial
```

`decodeURIComponent('C++')` trả về `C++`, không đổi dấu cộng thành dấu cách. Ngược lại, `new URLSearchParams('q=C++').get('q')` trả về `C  ` vì parser form URL encoded hiểu `+` là dấu cách. Hãy chọn parser đúng với định dạng dữ liệu.

### 4.2. Query có tham số lặp

URL có thể có nhiều tham số cùng tên:

```text
/search?role=user&role=admin
```

Các framework có thể chọn giá trị đầu, giá trị cuối, danh sách hoặc từ chối. Nếu lớp proxy, middleware và ứng dụng chọn quy tắc khác nhau, có thể xuất hiện **HTTP parameter pollution** hoặc bypass kiểm tra. Với tham số ảnh hưởng quyền, định danh hoặc định tuyến, hãy quy định rõ chỉ được có một giá trị và từ chối trường hợp lặp ngoài dự kiến.

## 5. Decode đúng cách và đúng số lần

### 5.1. Decode là chuyển biểu diễn trở lại dữ liệu

```js
const encoded = '%C4%90%C4%83ng%20nh%E1%BA%ADp';
console.log(decodeURIComponent(encoded));
// Đăng nhập
```

Decode không có nghĩa là chuỗi đã an toàn để dùng trong HTML, SQL, shell, đường dẫn filesystem hoặc JavaScript. Nó chỉ chuyển percent escapes về ký tự/byte tương ứng.

### 5.2. Không decode nhiều lần

Ví dụ một giá trị đã được encode hai lớp:

```text
Giá trị ban đầu:          ../private
Encode một lần:           ..%2Fprivate
Encode hai lần:           ..%252Fprivate
Decode một lần:           ..%2Fprivate
Decode hai lần:           ../private
```

Nếu gateway decode một lần nhưng backend decode lần nữa, ký tự `%2F` có thể biến thành `/` ở tầng sau. Kẻ tấn công có thể lợi dụng sự khác biệt giữa tầng lọc và tầng sử dụng để thay đổi ranh giới path hoặc tham số.

**Nguyên tắc:** parse theo một quy ước rõ ràng, decode đúng một lần ở tầng sở hữu component đó, và dùng cùng một biểu diễn canonical cho validation, authorization và thao tác dữ liệu. Không decode “cho chắc” ở mỗi middleware.

### 5.3. Xử lý dữ liệu malformed

Percent escape hợp lệ phải có đúng hai chữ số hex sau `%`. Các chuỗi `%`, `%2`, `%GG` không hợp lệ. `decodeURIComponent()` có thể ném `URIError` nếu escape không hợp lệ hoặc byte UTF-8 không tạo thành chuỗi hợp lệ:

```js
try {
  const value = decodeURIComponent('%E0%A4%A');
  console.log(value);
} catch (error) {
  if (error instanceof URIError) {
    console.error('Percent encoding không hợp lệ');
  }
}
```

Đừng bỏ qua lỗi rồi dùng chuỗi gốc trong một nhánh xử lý khác. Hãy từ chối request có encoding sai theo một quy tắc nhất quán và ghi log an toàn, không đưa dữ liệu không tin cậy vào log theo cách gây log injection.

Lưu ý, không phải parser URL nào cũng báo lỗi cho mọi đầu vào sai. Các API theo WHATWG như `URL`/`URLSearchParams` có cách xử lý tolerant đối với một số percent escape hoặc chuỗi UTF-8 không hợp lệ; `decodeURIComponent()` lại ném lỗi trong những trường hợp tương ứng. Nếu ứng dụng cần chính sách **reject malformed input**, phải xác định rõ tầng kiểm tra raw request target, dùng cùng một quy tắc parse/decode ở mọi tầng và không để một parser tolerant đi trước một parser strict hoặc ngược lại.

## 6. Canonicalization và các rủi ro bảo mật

**Canonicalization** là quá trình chuyển các biểu diễn khác nhau của cùng dữ liệu về một dạng chuẩn để so sánh, kiểm tra và sử dụng nhất quán. URL có thể chứa nhiều biểu diễn:

- `%2f` và `%2F` biểu diễn cùng một octet; chữ hex không phân biệt hoa thường.
- Một số unreserved characters có thể xuất hiện trực tiếp hoặc percent-encoded, ví dụ `~` và `%7E`.
- Dấu phân cách có thể được biểu diễn trực tiếp hoặc encoded, ví dụ `/` và `%2F`, nhưng hai dạng không phải lúc nào cũng được mọi tầng xử lý tương đương.
- Dữ liệu Unicode có thể có nhiều dạng chuẩn hóa Unicode (ví dụ ký tự dựng sẵn và ký tự kết hợp); percent encoding tự nó không quyết định chính sách Unicode normalization.

Khi các thành phần trong hệ thống chuẩn hóa khác nhau, một lớp có thể kiểm tra một chuỗi trong khi lớp sau sử dụng chuỗi khác.

### 6.1. Path traversal qua encoded separator

Giả sử ứng dụng nhận tên file từ URL:

```text
/download?file=report.pdf
```

Backend nối tên file vào thư mục dữ liệu mà không kiểm tra đường dẫn cuối cùng. Kẻ tấn công có thể thử biến thể chứa dấu chấm hoặc dấu phân tách đã encode:

```text
%2e%2e%2f
%2e%2e%5c
%252e%252e%252f
```

Những chuỗi này có thể trở thành `../` hoặc biến thể tương đương nếu một hoặc nhiều tầng decode. Cách phòng vệ:

1. Ưu tiên **identifier/allowlist** thay vì nhận đường dẫn tùy ý từ client.
2. Parse và decode theo một quy ước duy nhất; từ chối encoding malformed hoặc dạng không được hỗ trợ.
3. Chuẩn hóa đường dẫn ở backend rồi xác nhận đường dẫn cuối cùng vẫn nằm bên trong thư mục gốc được phép. Khi làm việc với filesystem, kiểm tra canonical/real path và xử lý cả symlink theo yêu cầu hệ điều hành.
4. Không dựa vào kiểm tra chuỗi như `includes('..')` hoặc chặn riêng `../`; separator, encoding và hệ điều hành có nhiều biến thể.
5. Đồng bộ hành vi decode/routing giữa CDN, reverse proxy, web server, framework và ứng dụng.

Ví dụ Node.js minh họa kiểm tra thư mục đích ở mức ứng dụng:

```js
const path = require('node:path');

function resolveInside(rootDirectory, requestedName) {
  const root = path.resolve(rootDirectory);
  const candidate = path.resolve(root, requestedName);
  const relative = path.relative(root, candidate);

  if (
    relative === '..' ||
    relative.startsWith('..' + path.sep) ||
    path.isAbsolute(relative)
  ) {
    throw new Error('Đường dẫn nằm ngoài thư mục cho phép');
  }
  return candidate;
}
```

Đây là một lớp kiểm tra đường dẫn sau khi giá trị đã được parse/decode theo quy ước ứng dụng. Trong môi trường có symlink hoặc file có thể bị thay đổi đồng thời, cần kiểm soát thêm filesystem operation; không coi đoạn code ngắn này là thay thế hoàn chỉnh cho thiết kế lưu trữ an toàn.

### 6.2. Query parameter confusion

Nếu ứng dụng nối giá trị chưa encode vào query:

```js
const role = 'user&admin=true';
const url = '/profile?role=' + role;
```

URL trở thành `/profile?role=user&admin=true`, tạo thêm tham số `admin`. Dùng `URLSearchParams.set()` để giá trị được encode theo component:

```js
const url = new URL('/profile', 'https://app.example.test');
url.searchParams.set('role', 'user&admin=true');
```

Server nhận một tham số `role` chứa dấu `&` như dữ liệu. Tuy nhiên, backend vẫn phải xác thực và phân quyền; không dùng query parameter do client cung cấp làm bằng chứng quyền quản trị.

### 6.3. Percent encoding không ngăn XSS

Giá trị `<img src=x onerror=alert(1)>` có thể được percent-encode khi truyền trong query. Khi ứng dụng đọc tham số, decode rồi đưa chuỗi vào `innerHTML`, nguy cơ XSS vẫn xuất hiện. Percent encoding chỉ bảo vệ cú pháp vận chuyển URL, không làm dữ liệu trở nên đáng tin.

Nếu hiển thị nội dung như văn bản, dùng:

```js
const params = new URLSearchParams(location.search);
const message = params.get('message') || '';
document.querySelector('#message').textContent = message;
```

Nếu cần cho phép HTML, phải dùng sanitizer phù hợp và allowlist; đồng thời triển khai CSP và Trusted Types khi phù hợp. Không đưa URL hoặc query value trực tiếp vào HTML, JavaScript, CSS hay thuộc tính nhạy cảm mà không xử lý theo **đúng ngữ cảnh đầu ra**.

### 6.4. Scheme nguy hiểm trong URL

Percent encoding không biến một URL nguy hiểm thành URL an toàn. Trước khi dùng dữ liệu không tin cậy làm đích liên kết hoặc điều hướng, parse URL rồi kiểm tra scheme và đích:

```js
function safeExternalUrl(input) {
  const url = new URL(input, location.origin);
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('Scheme không được phép');
  }
  return url.href;
}
```

Trong ứng dụng thật, còn cần allowlist hostname nếu chỉ cho phép liên kết tới một số domain. Không dựa vào kiểm tra prefix chuỗi như `startsWith('https://trusted.example')`, vì URL có thể chứa userinfo hoặc hostname gây nhầm lẫn.

## 7. Các quy tắc thực hành an toàn

| Tình huống | Cách làm khuyến nghị |
|---|---|
| Tạo query string | Dùng `URL` và `URLSearchParams` |
| Đưa dữ liệu vào một query value | Dùng `URLSearchParams.set()` hoặc `encodeURIComponent()` |
| Đưa dữ liệu vào một path segment | Encode segment riêng; xác nhận stack giữ nguyên ranh giới segment |
| Encode một URI đã có cấu trúc | Dùng `encodeURI()` khi đúng mục đích; không dùng cho từng value |
| Parse query | Dùng parser tương ứng định dạng; quy định rõ cách xử lý tham số trùng |
| Decode | Decode đúng một lần, đúng tầng và đúng component |
| Gặp malformed percent escape | Từ chối theo chính sách thống nhất |
| Kiểm tra file/path | Dùng identifier allowlist, canonical path và kiểm tra nằm trong root |
| Hiển thị dữ liệu URL | Dùng `textContent` hoặc sanitizer theo ngữ cảnh |
| Dùng URL làm đích điều hướng | Parse bằng `URL`, giới hạn scheme và hostname |

Các điều cần nhớ:

- `%2F` không phải lúc nào cũng tương đương `/` ở mọi tầng.
- `+` không phải dấu cách trong mọi loại URL; nó là dấu cách trong form URL encoded.
- `decodeURIComponent()` không thay `+` bằng dấu cách.
- Percent encoding không mã hóa bí mật, không xác thực dữ liệu và không ngăn XSS.
- Cùng origin vẫn được xác định bởi scheme/host/port; thay đổi path/query encoding không thay đổi origin.
- Không để proxy, framework và ứng dụng decode cùng một giá trị theo các quy tắc khác nhau.

## 8. Thực hành: quan sát raw URL và giá trị đã parse

Bài lab sử dụng Node.js, không cần thư viện bên ngoài. Mục tiêu là nhập chuỗi có dấu cách, `&`, `+`, `/` và tiếng Việt, sau đó quan sát:

1. Browser serialize query value bằng `URLSearchParams`.
2. HTTP server nhận request target ở dạng percent-encoded.
3. `URL` parser trả lại giá trị query đã decode.

### Bước 1 — Tạo file `percent-encoding-lab.cjs`

```js
const http = require('node:http');

const page = `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Percent encoding lab</title>
</head>
<body>
  <h1>Percent encoding</h1>
  <label for="value">Giá trị query:</label>
  <input id="value" value="A&B + C/Đà Nẵng" size="40">
  <button id="send">Gửi tới server</button>
  <pre id="output"></pre>
  <script>
    document.querySelector('#send').addEventListener('click', async () => {
      const value = document.querySelector('#value').value;
      const url = new URL('/echo', location.origin);
      url.searchParams.set('q', value);

      const output = document.querySelector('#output');
      output.textContent = 'Request URL: ' + url.href + '\nĐang gửi...';

      try {
        const response = await fetch(url);
        const result = await response.json();
        output.textContent =
          'Browser tạo URL:\n' + url.href +
          '\n\nServer nhận raw request target:\n' + result.rawTarget +
          '\n\nServer parse giá trị q:\n' + result.decodedValue;
      } catch (error) {
        output.textContent = 'Lỗi: ' + error.message;
      }
    });
  </script>
</body>
</html>`;

http.createServer((req, res) => {
  if (req.url === '/') {
    res.writeHead(200, {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    return res.end(page);
  }

  if (req.url.startsWith('/echo?')) {
    // URL parser giải mã query theo quy ước URLSearchParams.
    const parsed = new URL(req.url, 'http://localhost:3000');
    const decodedValue = parsed.searchParams.get('q');

    console.log('Raw request target:', req.url);
    console.log('Decoded q:', decodedValue);

    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    });
    return res.end(JSON.stringify({
      rawTarget: req.url,
      decodedValue,
    }));
  }

  res.writeHead(404);
  res.end('Not found');
}).listen(3000, () => {
  console.log('Mở http://localhost:3000');
});
```

Chạy:

```sh
node percent-encoding-lab.cjs
```

Mở `http://localhost:3000`, bật Developer Tools → **Network**, sau đó nhấn **Gửi tới server**.

### Bước 2 — Quan sát kết quả

Với giá trị mặc định `A&B + C/Đà Nẵng`, request target thường có dạng tương tự:

```text
/echo?q=A%26B+%2B+C%2F%C4%90%C3%A0+N%E1%BA%B5ng
```

Kết quả chính:

- `&` thành `%26` để không mở thêm query parameter.
- Dấu cách thành `+` vì `URLSearchParams` dùng quy ước form URL encoded.
- Dấu cộng dữ liệu thành `%2B`.
- `/` trong giá trị thành `%2F`.
- Các ký tự tiếng Việt được chuyển thành byte UTF-8 rồi percent-encode.
- Server parse query và nhận lại chuỗi `A&B + C/Đà Nẵng`.

So sánh ba vị trí: URL hiển thị trong trang, **Request URL** trong Network và log terminal. Browser và server có thể hiển thị một dạng đã chuẩn hóa; trường `rawTarget` của thí nghiệm cho thấy request target Node.js nhận được.

### Bước 3 — Thử các trường hợp biên

Thay giá trị input lần lượt bằng:

| Dữ liệu nhập | Điều cần quan sát |
|---|---|
| `100%` | Dấu `%` phải thành `%25` |
| `C++` | Hai dấu cộng dữ liệu phải thành `%2B%2B` |
| `red & blue` | Dấu `&` thành `%26`, không tạo tham số mới |
| `a/b` | Dấu `/` trong giá trị thành `%2F` |
| `Đăng nhập` | Một số ký tự tiếng Việt tạo nhiều byte UTF-8 |
| Chuỗi rỗng | Giá trị query tồn tại nhưng rỗng; phân biệt với thiếu tham số |

Sau đó sửa request thủ công trong một công cụ thử nghiệm để gửi `%`, `%2`, `%GG` hoặc byte UTF-8 không hợp lệ. So sánh cách parser xử lý hoặc từ chối các đầu vào này. Không để ứng dụng production tiếp tục với các nhánh parse khác nhau.

### Bước 4 — Thử decode nhiều lần

Mở Console và chạy:

```js
const once = decodeURIComponent('%252e%252e%252f');
const twice = decodeURIComponent(once);

console.log(once);  // %2e%2e%2f
console.log(twice); // ../
```

Giải thích vì sao một lớp middleware decode trước có thể làm thay đổi ý nghĩa của dữ liệu mà backend nhận được. Trong hệ thống thật, không giải quyết bằng cách decode lặp đến khi không còn `%`; hãy quy định một lần parse/decode ở đúng tầng và xác thực trên dạng canonical.

## 9. Chẩn đoán lỗi percent encoding

Khi server đọc query/path khác với dữ liệu người dùng nhập, kiểm tra theo thứ tự:

1. **Xác định component:** giá trị đang nằm trong path segment, query, fragment, form body hay header? Mỗi nơi có quy tắc khác nhau.
2. **Kiểm tra encoder:** dùng `encodeURIComponent` cho component hay `URLSearchParams` cho query/form? Có vô tình dùng `encodeURI` cho value không?
3. **Kiểm tra định dạng:** dấu cách có được chuyển thành `+` theo form encoding không? Dấu cộng thật đã thành `%2B` chưa?
4. **Kiểm tra số lần decode:** CDN, proxy, web server, framework và ứng dụng có tầng nào decode thêm không?
5. **Kiểm tra canonicalization:** `%2f`/`%2F`, unreserved escapes, Unicode normalization, encoded dot segment và slash/backslash có được xử lý thống nhất không?
6. **Kiểm tra parser:** duplicate parameter được xử lý thế nào? Parser có từ chối malformed `%` và UTF-8 không hợp lệ không?
7. **Kiểm tra nơi sử dụng cuối:** dữ liệu sau decode có được đưa vào filesystem, SQL, HTML, JavaScript hoặc URL điều hướng không? Mỗi sink cần validation/encoding riêng.

### Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Encode cả URL bằng `encodeURIComponent` | Encode luôn `:`, `/`, `?`, `&`, làm hỏng cấu trúc | Dùng URL parser và encode từng component |
| Dùng `encodeURI` cho query value | Dấu `&`, `=` có thể tạo tham số ngoài ý muốn | Dùng `URLSearchParams` hoặc `encodeURIComponent` |
| Tự thay dấu cách bằng `+` cho mọi URL | Có thể sai với URL syntax thông thường hoặc làm sai dấu cộng dữ liệu | Dùng API theo định dạng cụ thể |
| Decode hai lần | Dữ liệu đổi ranh giới path/query sau bước kiểm tra | Decode một lần và xác thực canonical representation |
| Kiểm tra `../` trên chuỗi thô | Bỏ sót dạng percent-encoded hoặc separator khác | Kiểm tra canonical path và giới hạn filesystem root |
| Tin rằng percent-encoded HTML an toàn | XSS vẫn xảy ra sau khi ứng dụng decode và đưa vào HTML sink | Output encoding/sanitization theo ngữ cảnh |
| Chấp nhận nhiều cách diễn giải query | Proxy và backend có thể phân quyền trên các giá trị khác nhau | Quy định parser và từ chối tham số trùng không hợp lệ |

## 10. Câu hỏi tự kiểm tra

**1.** Percent encoding `%C3%A9` biểu diễn gì?  
**Trả lời:** Hai octet UTF-8 `C3 A9`, thường giải mã thành ký tự `é`.

**2.** Vì sao `encodeURIComponent('a&b')` phù hợp hơn `encodeURI('a&b')` khi tạo query value?  
**Trả lời:** Nó encode dấu `&` thành dữ liệu `%26`; `encodeURI` giữ `&` như delimiter và có thể tạo thêm tham số.

**3.** `URLSearchParams` serialize dấu cách và dấu cộng dữ liệu như thế nào?  
**Trả lời:** Dấu cách thành `+`; dấu cộng dữ liệu thành `%2B`. Parser `URLSearchParams` đổi `+` trở lại dấu cách.

**4.** `decodeURIComponent('a+b')` trả về gì?  
**Trả lời:** `a+b`. Hàm này không áp dụng quy tắc dấu cộng của `application/x-www-form-urlencoded`.

**5.** Vì sao không nên decode URL ở nhiều middleware?  
**Trả lời:** Mỗi tầng có thể thay đổi delimiter hoặc path sau khi lớp trước đã kiểm tra, tạo double-decoding và canonicalization mismatch.

**6.** Percent encoding có làm chuỗi HTML độc hại an toàn khi gán vào `innerHTML` không?  
**Trả lời:** Không. Sau decode, chuỗi vẫn có thể tạo HTML/script. Dùng output encoding hoặc sanitizer theo ngữ cảnh và phòng vệ XSS phù hợp.

**7.** Thay `%2F` bằng `/` có luôn giữ nguyên ý nghĩa URL không?  
**Trả lời:** Không. `/` là path delimiter; `%2F` có thể là dữ liệu trong segment. Proxy/server/framework có thể decode ở các thời điểm khác nhau, vì vậy cần kiểm chứng stack.

**8.** Thay percent encoding trong query có làm thay đổi origin không?  
**Trả lời:** Không. Origin HTTP(S) dựa trên scheme, host và port; query/path không nằm trong bộ ba này.

## Tổng kết

Percent encoding biểu diễn octet bằng `%HH`, thường dùng UTF-8 để đưa dữ liệu Unicode vào URL. An toàn phụ thuộc vào việc **encode đúng component, parse theo đúng định dạng và decode đúng một lần**. Dùng `URL`/`URLSearchParams` thay cho nối chuỗi, xử lý rõ `%20` và `+`, đồng bộ canonicalization giữa các tầng và xác thực đường dẫn sau parse. Percent encoding chỉ là biểu diễn dữ liệu: nó không mã hóa bí mật, không cấp quyền, không thay thế kiểm tra server và không ngăn XSS nếu dữ liệu sau decode đi vào sink nguy hiểm.
