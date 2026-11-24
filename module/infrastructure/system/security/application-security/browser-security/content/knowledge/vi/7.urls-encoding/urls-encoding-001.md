# URL parsing: cách trình duyệt phân tích và chuẩn hóa địa chỉ web

## 1. URL parsing là gì?

**URL parsing** là quá trình phân tích một chuỗi địa chỉ thành các thành phần có ý nghĩa: scheme, username/password, host, port, path, query và fragment. Trình duyệt dùng kết quả này để xác định tài nguyên cần tải, nơi gửi request, cách giải quyết URL tương đối và nhiều quyết định liên quan đến bảo mật.

Một URL không chỉ là một chuỗi để cắt bằng dấu gạch chéo hoặc dấu hai chấm. URL có cú pháp, quy tắc chuẩn hóa và các trường hợp đặc biệt. Hai chuỗi trông khác nhau có thể được parser chuẩn hóa thành cùng một URL; ngược lại, hai URL có hostname giống nhau nhưng khác scheme hoặc port có thể thuộc hai origin khác nhau.

Bài viết thuộc chương **URL và encoding** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Việc hiểu URL parsing giúp phân tích ranh giới giữa trình duyệt, origin, cookie và ứng dụng web; đặc biệt khi triển khai Same-Origin Policy (SOP), CORS, redirect, xác thực nguồn request và phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types cùng security headers.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện các thành phần URL và hiểu thành phần nào tham gia tạo origin.
- Dùng chuẩn **WHATWG URL** và API **URL/URLSearchParams** để parse, resolve và chuẩn hóa URL.
- Hiểu scheme đặc biệt, host, port mặc định, path, query, fragment và percent-encoding.
- Phân biệt parse URL với xác thực URL có được phép dùng trong một nghiệp vụ hay không.
- Nhận diện lỗi bảo mật do kiểm tra URL bằng chuỗi, parser khác nhau, redirect và encoding nhiều lần.
- Thiết kế kiểm tra URL an toàn cho redirect, liên kết, CORS và những chức năng server nhận URL từ người dùng.

## 2. Cấu trúc của một URL

Một URL HTTP(S) thông thường có dạng:

```text
https://alice:secret@shop.example.com:8443/products/item?id=42&sort=asc#reviews
└─┬─┘   └──────┬─────┘ └──────────┬─────────┘ └──┬───┘ └──────┬──────┘ └──┬──┘
scheme        userinfo            host + port    path         query     fragment
```

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| **Scheme / protocol** | https: | Cách diễn giải và truy cập tài nguyên |
| **Username** | alice | Thông tin userinfo trong authority; hiếm khi cần trong ứng dụng hiện đại |
| **Password** | secret | Thông tin userinfo; không nên nhúng bí mật vào URL |
| **Host** | shop.example.com | Tên máy chủ hoặc địa chỉ IP |
| **Port** | 8443 | Cổng kết nối; có thể bị lược bỏ nếu là port mặc định |
| **Path** | /products/item | Đường dẫn tài nguyên phía server |
| **Query** | id=42&sort=asc | Tham số truy vấn |
| **Fragment** | reviews | Vị trí hoặc trạng thái phía client; không gửi trong HTTP request thông thường |

Dấu @ phân tách userinfo và host; dấu hai chấm trong authority có thể phân tách username/password hoặc host/port tùy vị trí. Vì vậy, không thể lấy phần trước dấu gạch chéo rồi tách bằng dấu hai chấm để xác định host.

### 2.1. URL không phải lúc nào cũng có authority

Cú pháp URL phụ thuộc scheme. Ví dụ:

```text
https://example.com/a?x=1#top
mailto:help@example.com
tel:+84123456789
data:text/plain,hello
blob:https://example.com/550e8400-e29b-41d4-a716-446655440000
file:///C:/docs/readme.txt
```

HTTPS thường có authority gồm host và có thể có port. Mailto và tel không có host theo cách của HTTP(S). Data chứa dữ liệu trong phần path; blob chứa một URL nội bộ đại diện tài nguyên blob. File có quy tắc riêng theo nền tảng và trình duyệt.

Do đó, đừng giả định mọi URL đều có hostname, pathname hoặc origin dạng scheme://host.

### 2.2. Fragment không được gửi lên server

Với URL:

```text
https://docs.example.com/guide?page=2#authentication
```

Trình duyệt gửi request đến tài nguyên /guide?page=2; phần #authentication được xử lý ở phía client và **không nằm trong request target HTTP thông thường**. Fragment có thể được dùng để cuộn đến phần tử, định tuyến ứng dụng SPA hoặc lưu trạng thái phía client.

Không đặt access token hoặc dữ liệu bí mật trong fragment với giả định nó được bảo vệ: fragment vẫn có thể lộ qua lịch sử trình duyệt, ảnh chụp màn hình, script cùng trang, extension hoặc thao tác sao chép URL.

## 3. WHATWG URL parser và quá trình chuẩn hóa

Trên web hiện đại, trình duyệt dùng mô hình parser được mô tả trong **WHATWG URL Standard**. JavaScript cung cấp giao diện tương ứng qua URL và URLSearchParams.

Parser thực hiện nhiều bước, có thể bao gồm loại bỏ một số ký tự điều khiển/space ở đầu cuối, nhận diện scheme, phân tích authority, chuẩn hóa host, xử lý port, path và encoding. Chi tiết phụ thuộc loại scheme.

Sơ đồ khái niệm:

```mermaid
flowchart TD
    A["Chuỗi URL đầu vào"] --> B["Xác định scheme và loại URL"]
    B --> C{"URL có authority?"}
    C -- "Có" --> D["Parse userinfo, host và port"]
    C -- "Không" --> E["Parse phần path theo scheme"]
    D --> F["Chuẩn hóa host, port"]
    E --> G["Chuẩn hóa path/query/fragment"]
    F --> G
    G --> H["URL record / các thuộc tính URL"]
    H --> I["Serialize URL hoặc lấy origin"]
```

**Điểm quan trọng:** Parse thành công chỉ cho biết chuỗi có thể được diễn giải thành URL. Nó không có nghĩa URL đó an toàn, thuộc domain được tin cậy, trỏ đến IP công khai hoặc được phép dùng cho nghiệp vụ hiện tại.

### 3.1. Dùng URL thay cho cắt chuỗi thủ công

```js
const input =
  "https://alice:secret@SHOP.example.com:443/products?id=42#reviews";

const url = new URL(input);

console.log(url.protocol); // "https:"
console.log(url.username); // "alice"
console.log(url.password); // "secret"
console.log(url.hostname); // "shop.example.com"
console.log(url.port);     // ""
console.log(url.pathname); // "/products"
console.log(url.search);   // "?id=42"
console.log(url.hash);     // "#reviews"
console.log(url.origin);   // "https://shop.example.com"
console.log(url.href);     // URL đã chuẩn hóa
```

Ở ví dụ này, host được chuyển về chữ thường và port HTTPS mặc định 443 được chuẩn hóa thành chuỗi rỗng trong thuộc tính port. Origin không chứa username, password, path, query hoặc fragment.

new URL(input) yêu cầu URL tuyệt đối. Nếu đầu vào không parse được, constructor ném TypeError. Với URL tương đối, phải cung cấp base URL rõ ràng.

### 3.2. URL tuyệt đối và URL tương đối

URL tương đối được giải quyết dựa trên một **base URL**:

```js
const base = new URL("https://shop.example.com/catalog/list.html");

const inputs = [
  "/account",          // root-relative
  "item/42",           // path-relative
  "../images/logo.svg",
  "?page=2",            // query-relative
  "#reviews",           // fragment-relative
  "//cdn.example.net/app.js", // scheme-relative
];

for (const input of inputs) {
  console.log(input, "=>", new URL(input, base).href);
}
```

| URL tương đối | Kết quả minh họa | Ý nghĩa |
|---|---|---|
| /account | https://shop.example.com/account | Thay path từ root |
| item/42 | https://shop.example.com/catalog/item/42 | Ghép vào thư mục hiện tại |
| ../images/logo.svg | https://shop.example.com/images/logo.svg | Lùi một cấp path |
| ?page=2 | https://shop.example.com/catalog/list.html?page=2 | Thay query |
| #reviews | https://shop.example.com/catalog/list.html#reviews | Thay fragment |
| //cdn.example.net/app.js | https://cdn.example.net/app.js | Giữ scheme của base, đổi authority |

Một URL bắt đầu bằng // không phải đường dẫn cùng host: nó thay host, vì thế có thể làm thay đổi origin.

### 3.3. Base URL trong tài liệu HTML

Trong trang HTML, URL tương đối thường được resolve theo document.baseURI. Phần tử base href có thể thay đổi base dùng cho các liên kết và tài nguyên tương đối:

```html
<base href="https://cdn.example.net/assets/">
<a href="account">Tài khoản</a>
<img src="logo.svg" alt="Logo">
```

Khi đó liên kết account được resolve thành https://cdn.example.net/assets/account. Nếu kẻ tấn công có thể chèn một base độc hại, nhiều URL tương đối trên trang có thể bị chuyển hướng đến host khác.

Để kiểm soát nguồn base trong ứng dụng, có thể dùng CSP:

```http
Content-Security-Policy: base-uri 'self'
```

Hoặc base-uri 'none' nếu ứng dụng không cần thẻ base. Directive này hạn chế URL được dùng trong base; nó không thay thế việc xác thực mọi URL do ứng dụng tạo ra.

## 4. Scheme, host và port

### 4.1. Scheme được chuẩn hóa

Scheme không phân biệt chữ hoa/chữ thường trong cú pháp URL; parser chuẩn hóa về chữ thường:

```js
new URL("HTTPS://EXAMPLE.COM/a").href;
// "https://example.com/a"
```

Nhưng http: và https: là hai scheme khác nhau và thường tạo origin khác nhau. Một ứng dụng yêu cầu HTTPS nên kiểm tra url.protocol === "https:", không chỉ kiểm tra hostname.

Các scheme đặc biệt của WHATWG URL gồm ftp, file, http, https, ws và wss. Nhóm scheme này có quy tắc parser đặc biệt; ví dụ dấu backslash trong một số vị trí được xử lý giống dấu slash. Đây là một lý do nữa để không tự parse URL bằng regex.

### 4.2. Host: domain, IPv4, IPv6 và IDN

Host có thể là:

- Tên miền ASCII như shop.example.com.
- Tên miền quốc tế (IDN), có thể được chuẩn hóa sang dạng ASCII/Punycode.
- IPv4 như 192.0.2.10.
- IPv6 đặt trong ngoặc vuông như [2001:db8::10].

```js
const urls = [
  "https://SHOP.EXAMPLE.COM",
  "https://münich.example",
  "https://192.0.2.10",
  "https://[2001:db8::10]:8443",
];

for (const value of urls) {
  const u = new URL(value);
  console.log({
    input: value,
    hostname: u.hostname,
    origin: u.origin,
  });
}
```

Tên miền quốc tế có thể có các ký tự nhìn giống chữ Latin nhưng thuộc bảng chữ cái khác. Punycode giúp chuẩn hóa cách biểu diễn host cho giao thức; nó **không loại bỏ hoàn toàn nguy cơ tên miền giả mạo bằng ký tự tương tự (homograph)**. Khi hiển thị domain cho người dùng, cần dựa vào chính sách hiển thị an toàn của trình duyệt và không tự biến chuỗi host thành nội dung đáng tin.

WHATWG host parser cũng nhận diện một số dạng IPv4 không quen thuộc, ví dụ dạng số rút gọn hoặc biểu diễn hex. Đừng dùng regex chỉ chấp nhận bốn nhóm số thập phân rồi cho rằng mọi URL còn lại không phải địa chỉ loopback/private. Khi kiểm soát đích mạng, hãy parse bằng thư viện chuẩn rồi kiểm tra địa chỉ IP sau phân giải DNS và tại thời điểm kết nối.

### 4.3. Port mặc định

Các port mặc định thường được chuẩn hóa:

| Scheme | Port mặc định |
|---|---:|
| http: | 80 |
| https: | 443 |
| ws: | 80 |
| wss: | 443 |
| ftp: | 21 |

Ví dụ:

```js
new URL("https://example.com:443/a").href;
// "https://example.com/a"

new URL("https://example.com:8443/a").href;
// "https://example.com:8443/a"
```

URL.port trả chuỗi rỗng nếu không có port tường minh hoặc port mặc định đã được chuẩn hóa. Port vẫn là thành phần của origin khi khác mặc định. Do đó, https://example.com và https://example.com:8443 là hai origin khác nhau.

### 4.4. Userinfo và lỗi nhầm host

Một URL có thể chứa username/password trước dấu @:

```text
https://trusted.example@evil.test/login
        └──────┬─────┘ └───┬────┘
             userinfo      host
```

Host thực tế của URL trên là evil.test, không phải trusted.example. Kiểm tra chuỗi kiểu input.includes("trusted.example") sẽ bị đánh lừa.

Một số ứng dụng không có lý do hợp lệ để nhận userinfo trong URL. Hãy từ chối url.username hoặc url.password khi kiểm tra URL điều hướng/đích tin cậy để tránh nhầm lẫn cho người dùng và các thành phần xử lý sau.

## 5. Path: phân đoạn và chuẩn hóa

Path của URL thường gồm các segment phân tách bằng /:

```text
https://example.com/users/42/orders/7
                     └──┬──┘└┬┘└──┬─┘└┬┘
                      users  42 orders 7
```

Đường dẫn có thể chứa các ký tự percent-encoded. Parser cũng xử lý segment dấu chấm (.) và dấu chấm kép (..) theo quy tắc chuẩn hóa đường dẫn. Một số dạng percent-encoded của dot segment cũng được nhận diện trong URL đặc biệt, ví dụ %2e và %2e%2e (không phân biệt chữ hoa/chữ thường của hex).

```js
const u = new URL(
  "https://example.com/a/b/../c/./item"
);

console.log(u.pathname); // "/a/c/item"
```

**Không đồng nghĩa với bảo vệ path traversal:** server, reverse proxy, framework và filesystem có thể giải mã hoặc chuẩn hóa path ở các giai đoạn khác nhau. Nếu một tầng kiểm tra /safe/%2e%2e/admin trước giải mã nhưng tầng sau giải mã rồi truy cập /safe/../admin, có thể phát sinh parser/normalization differential.

### 5.1. Percent-encoded slash và backslash

%2F là dạng percent-encoded của /, còn %5C là dạng của \. URL parser và các server/framework có thể xử lý chúng khác nhau theo scheme, cấu hình và tầng xử lý. Không tự giả định %2F luôn là ký tự bình thường hoặc luôn được giải mã thành dấu phân tách.

Khi bảo vệ route hoặc file:

- Xác định tầng nào parse URL, tầng nào decode path và tầng nào ánh xạ path vào tài nguyên.
- Tránh decode toàn bộ URL trước khi parse.
- Không decode một giá trị nhiều lần qua các middleware mà không có quy ước rõ.
- Chuẩn hóa và kiểm tra path theo cùng một quy tắc với tầng thực thi cuối cùng.
- Dùng API filesystem an toàn, kiểm soát root directory và tránh nối chuỗi path tùy tiện.

### 5.2. Không decode URL toàn cục trước khi parse

Ví dụ chuỗi:

```text
https://example.com/search?q=a%26role%3Dadmin
```

Nếu decode toàn bộ URL trước khi parse, phần query q có thể biến thành a&role=admin, khiến ký tự & vốn là dữ liệu trở thành dấu phân tách tham số. Điều này làm thay đổi cấu trúc URL.

Hãy parse URL trước, sau đó lấy và decode đúng thành phần bằng API tương ứng. Không thực hiện percent-decode lặp lại nếu dữ liệu đã được giải mã ở tầng trước.

## 6. Query string và URLSearchParams

Query bắt đầu bằng ?, thường chứa các cặp key/value:

```text
/search?q=browser+security&page=2&tag=web&tag=privacy
        └───────┬────────┘ └─┬─┘       └───────┬────────┘
                 q           page          tag (lặp)
```

Dùng URLSearchParams để đọc và ghi query thay vì tự tách bằng & và =:

```js
const url = new URL(
  "https://example.com/search?q=browser+security&page=2&tag=web&tag=privacy"
);

const params = url.searchParams;

console.log(params.get("q"));       // "browser security"
console.log(params.get("page"));    // "2"
console.log(params.getAll("tag"));  // ["web", "privacy"]

params.set("page", "3");
params.append("tag", "cookies");

console.log(url.href);
```

get() trả giá trị đầu tiên khi key lặp; getAll() trả tất cả. Nếu nhiều thành phần trong hệ thống diễn giải key trùng lặp theo quy tắc khác nhau (đầu tiên, cuối cùng hoặc ghép mảng), có thể xuất hiện **HTTP parameter pollution**. Với tham số ảnh hưởng quyền hoặc định tuyến, hãy quy định rõ có chấp nhận key lặp hay không và từ chối trường hợp mơ hồ.

### 6.1. Dấu cộng và percent-encoding trong query

URLSearchParams dùng quy tắc application/x-www-form-urlencoded: khoảng trắng được serialize thành +, và dấu + trong dữ liệu được encode thành %2B.

```js
const params = new URLSearchParams();
params.set("q", "C++ security & URL");
console.log(params.toString());
// q=C%2B%2B+security+%26+URL

const parsed = new URLSearchParams("q=C%2B%2B+security");
console.log(parsed.get("q"));
// "C++ security"
```

Không đồng nhất mọi quy tắc query với quy tắc path hoặc với encodeURIComponent. Trong URL, các thành phần có bộ ký tự cần percent-encode khác nhau.

### 6.2. encodeURI, encodeURIComponent và URLSearchParams

| API | Mục đích | Lưu ý |
|---|---|---|
| encodeURI(value) | Encode một URI/URL tương đối hoàn chỉnh | Giữ lại nhiều ký tự phân tách như ?, &, #, /; không phù hợp để encode dữ liệu tùy ý đặt vào một tham số |
| encodeURIComponent(value) | Encode một thành phần dữ liệu | Encode các dấu phân tách như &, =, ?, / |
| URLSearchParams | Xây dựng/đọc query theo form-url-encoded | Xử lý key lặp và quy tắc dấu + |

Ví dụ:

```js
const term = "admin&role=owner";

const unsafe = "/search?q=" + term;
// /search?q=admin&role=owner
// Dữ liệu bị diễn giải thành hai tham số.

const safe = new URL("https://example.com/search");
safe.searchParams.set("q", term);

console.log(safe.href);
// https://example.com/search?q=admin%26role%3Downer
```

Không dùng encoding như một biện pháp xác thực hay làm sạch HTML. Percent-encoding chỉ biểu diễn dữ liệu trong URL; khi đưa dữ liệu sang HTML, JavaScript, CSS hoặc SQL, phải áp dụng quy tắc bảo vệ riêng cho ngữ cảnh đích.

## 7. Origin được xác định từ URL như thế nào?

Với URL HTTP(S) thông thường, origin được xác định bởi:

```text
scheme + host + port
```

Ví dụ:

| URL | Serialized origin |
|---|---|
| https://shop.example.com/a | https://shop.example.com |
| https://shop.example.com:443/b | https://shop.example.com |
| https://shop.example.com:8443/b | https://shop.example.com:8443 |
| http://shop.example.com/a | http://shop.example.com |
| https://api.example.com/a | https://api.example.com |

Path, query, fragment và userinfo không tham gia serialized origin. Vì vậy, khi so sánh origin để kiểm soát quyền, dùng url.origin hoặc cơ chế chuẩn hóa tương ứng, không so sánh href hay hostname đơn lẻ.

### 7.1. URL.origin không phải lúc nào cũng là danh tính của Document

new URL("about:blank").origin thường serialize thành "null" khi parse chuỗi URL độc lập. Nhưng một tài liệu about:blank được tạo bởi trang cha có thể **kế thừa origin của creator**. Tương tự, sandbox iframe có thể tạo opaque origin ngay cả khi URL của nó có vẻ giống host của trang cha.

Vì thế:

- new URL(input).origin cho biết origin được tính từ URL đã parse.
- location.origin biểu diễn origin của URL hiện tại theo API Location; với about:blank, srcdoc hoặc sandbox, chuỗi này không tự cho biết đầy đủ quyền truy cập của Document.
- Origin thực tế của Document còn chịu ảnh hưởng cách tài liệu được tạo, sandbox và quy tắc kế thừa.
- Chuỗi "null" không phải danh tính duy nhất của một opaque origin.

Khi bảo vệ postMessage, CORS hoặc iframe, hãy xét ngữ cảnh tài liệu và kiểm tra event.origin/event.source đúng cách; không chỉ phân tích URL ban đầu.

### 7.2. CORS và header Origin

Trình duyệt có thể gửi HTTP request với header:

```http
GET /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
```

Origin chỉ biểu diễn origin của ngữ cảnh gửi, không có path. Server cần so sánh với allowlist origin chính xác. Không lấy URL tùy ý từ người dùng rồi phản chiếu vào Access-Control-Allow-Origin.

Ví dụ kiểm tra:

```js
const allowedOrigins = new Set([
  "https://app.example.com",
  "https://admin.example.com",
]);

function isAllowedOriginHeader(value) {
  return typeof value === "string" && allowedOrigins.has(value);
}
```

Đây là kiểm tra ở server cho giá trị header đã nhận; nó không thay xác thực hoặc phân quyền. CORS chủ yếu kiểm soát khả năng script đọc response. Request cross-site vẫn có thể được gửi trong một số tình huống, vì vậy CSRF cần token và kiểm tra nguồn riêng.

## 8. URL parsing và các lỗi bảo mật thường gặp

### 8.1. Kiểm tra hostname bằng substring

Sai:

```js
if (input.includes("trusted.example")) {
  allow();
}
```

Chuỗi như https://trusted.example.attacker.test/ hoặc https://trusted.example@attacker.test/ có thể vượt qua phép kiểm tra chuỗi đơn giản.

Đúng hơn: parse bằng URL parser, sau đó so sánh origin với allowlist chính xác.

### 8.2. Kiểm tra bằng tiền tố hoặc hậu tố thiếu ranh giới

Sai:

```js
url.hostname.endsWith("example.com");
```

Cách này có thể chấp nhận notexample.com. Nếu nghiệp vụ thật sự cần chấp nhận toàn bộ subdomain, điều kiện tối thiểu phải xét ranh giới nhãn DNS:

```js
const host = url.hostname.toLowerCase();
const isExampleDomain =
  host === "example.com" || host.endsWith(".example.com");
```

Tuy nhiên, điều kiện này vẫn chấp nhận **mọi** subdomain, bao gồm subdomain do người dùng kiểm soát hoặc đã bị takeover. Với luồng nhạy cảm, ưu tiên allowlist các hostname/origin cụ thể và đánh giá quyền sở hữu từng subdomain.

### 8.3. Nhầm userinfo với host

Sai lầm: nhìn thấy trusted.example trong https://trusted.example@evil.test/ rồi kết luận host đáng tin.

Cách xử lý: dùng new URL(), kiểm tra hostname, origin, username và password; từ chối userinfo nếu không có nhu cầu rõ ràng.

### 8.4. Chấp nhận mọi scheme

Một URL có thể dùng scheme không phải HTTP(S):

```text
javascript:alert(document.domain)
data:text/html,<script>alert(1)</script>
blob:https://app.example.com/...
https://app.example.com/
```

Nếu ứng dụng cho người dùng nhập URL để tạo liên kết điều hướng hoặc đặt vào href, đừng mặc định mọi URL parse thành công đều an toàn. Hãy xác định scheme được phép, thường chỉ https: (và có thể http: trong môi trường phát triển được giới hạn). Các scheme như javascript: có thể tạo nguy cơ thực thi mã khi được dùng trong ngữ cảnh điều hướng phù hợp.

Ví dụ:

```js
function parseExternalLink(input) {
  const url = new URL(input);

  if (!["https:", "http:"].includes(url.protocol)) {
    throw new TypeError("Scheme không được phép");
  }

  if (url.username || url.password) {
    throw new TypeError("Không chấp nhận userinfo");
  }

  return url;
}
```

Việc cho phép http: chỉ phù hợp nếu sản phẩm thực sự cần. Với liên kết ra ngoài trong sản phẩm production, thường nên yêu cầu HTTPS.

### 8.5. Open redirect

Một endpoint nhận tham số returnTo có thể chuyển người dùng sang domain độc hại nếu chỉ kiểm tra URL có tồn tại:

```text
/login?returnTo=https://attacker.test/phishing
```

Nếu chức năng chỉ cần redirect nội bộ, parse giá trị theo base cố định rồi kiểm tra origin:

```js
const APP_ORIGIN = "https://app.example.com";

function getSafeReturnUrl(value) {
  const target = new URL(value, APP_ORIGIN);

  if (target.origin !== APP_ORIGIN) {
    throw new TypeError("Chỉ cho phép redirect nội bộ");
  }

  if (target.username || target.password) {
    throw new TypeError("Không chấp nhận userinfo");
  }

  return target;
}
```

Ví dụ này cho phép URL tương đối nội bộ và từ chối URL chuyển sang origin khác. Nếu ứng dụng chỉ cho phép một số path, cần thêm allowlist route; cùng origin không đồng nghĩa mọi endpoint đều hợp lệ.

### 8.6. SSRF: URL hợp lệ vẫn có thể trỏ đến mạng nội bộ

Một server nhận URL rồi tự tải tài nguyên có thể bị lợi dụng để truy cập:

- localhost, loopback hoặc địa chỉ quản trị nội bộ.
- Dải IP private, link-local hoặc metadata service của cloud.
- Host công khai ban đầu nhưng redirect đến địa chỉ nội bộ.
- Host DNS trả về địa chỉ khác giữa bước kiểm tra và bước kết nối.

Dùng new URL() chỉ parse cú pháp. Phòng vệ SSRF còn cần:

1. Chỉ cho phép scheme cần thiết (thường HTTPS).
2. Allowlist hostname khi nghiệp vụ có tập đích xác định.
3. Phân giải DNS và kiểm tra toàn bộ địa chỉ IPv4/IPv6, gồm loopback, private, link-local và các dải đặc biệt.
4. Kết nối đến địa chỉ đã kiểm tra để giảm DNS rebinding/TOCTOU; không để thư viện tự phân giải lại một cách không kiểm soát.
5. Tắt redirect hoặc kiểm tra lại **từng redirect hop** và đích cuối.
6. Áp chính sách egress/network ở tầng hạ tầng như lớp bảo vệ bổ sung.

Không dùng regex hoặc so sánh hostname làm biện pháp duy nhất để chặn SSRF.

### 8.7. Parser differential giữa browser, proxy và backend

Một URL có thể đi qua nhiều parser: trình duyệt, CDN, reverse proxy, framework, router và thư viện HTTP. Nếu các tầng diễn giải encoding, dấu slash/backslash, dot segment, port hoặc host khác nhau, kẻ tấn công có thể khai thác sự khác biệt.

Ví dụ về vùng cần kiểm tra:

- /safe/%2e%2e/admin: encoded dot segment.
- /safe%2Fadmin: encoded slash.
- /safe\..\admin: backslash trong parser của scheme đặc biệt hoặc server cụ thể.
- Host có userinfo hoặc biểu diễn IPv4 không quen thuộc.
- Query chứa key lặp hoặc ký tự +/%2B.

Quy tắc an toàn: **parse một lần theo chuẩn rõ ràng, truyền dữ liệu có cấu trúc giữa các tầng khi có thể, và bảo đảm mọi tầng dùng cùng quy tắc canonicalization trước khi kiểm tra quyền**.

## 9. Mẫu kiểm tra URL theo allowlist

Khi một ứng dụng cần nhận URL tuyệt đối và chỉ cho phép một số origin, hãy dùng allowlist sau khi parse:

```js
const ALLOWED_ORIGINS = new Set([
  "https://docs.example.com",
  "https://support.example.com",
]);

function parseAllowedDestination(input) {
  // Không truyền base: chỉ chấp nhận URL tuyệt đối.
  const url = new URL(input);

  if (url.protocol !== "https:") {
    throw new TypeError("Chỉ chấp nhận HTTPS");
  }

  if (url.username !== "" || url.password !== "") {
    throw new TypeError("Không chấp nhận userinfo");
  }

  if (!ALLOWED_ORIGINS.has(url.origin)) {
    throw new TypeError("Origin không nằm trong allowlist");
  }

  return url;
}
```

Vì url.origin đã được parser chuẩn hóa, phép so sánh chính xác xử lý nhất quán chữ hoa/thường của host và port mặc định. Ví dụ https://DOCS.example.com:443/page có thể được chấp nhận như cùng origin với https://docs.example.com, còn https://docs.example.com.attacker.test/ bị từ chối.

Nếu sản phẩm cho phép một URL tương đối, hãy dùng base URL cố định và kiểm tra origin kết quả. Nếu sản phẩm cho phép cả query hoặc path cụ thể, kiểm tra thêm các thành phần đó theo yêu cầu nghiệp vụ.

**Không phản chiếu URL đầu vào trở lại HTML hoặc header trước khi encode/validate theo ngữ cảnh.** URL hợp lệ về cú pháp vẫn có thể là nội dung độc hại trong một ngữ cảnh khác.

## 10. Thực hành kiểm chứng bằng DevTools

### Bài A — Quan sát URL parser và canonicalization

Mở DevTools → Console trên một trang HTTPS và chạy:

```js
const samples = [
  "HTTPS://SHOP.EXAMPLE.COM:443/a/../b?q=hello+world#top",
  "https://trusted.example@evil.test/path",
  "https://example.com:8443/path",
  "https://münich.example/",
  "https://[2001:db8::10]:8443/a",
  "data:text/plain,hello",
  "blob:https://example.com/550e8400-e29b-41d4-a716-446655440000",
];

console.table(samples.map((input) => {
  try {
    const u = new URL(input);
    return {
      input,
      href: u.href,
      origin: u.origin,
      protocol: u.protocol,
      hostname: u.hostname,
      port: u.port,
      pathname: u.pathname,
      search: u.search,
      hash: u.hash,
    };
  } catch (error) {
    return { input, error: error.name };
  }
}));
```

Hãy giải thích:

- Vì sao port 443 không xuất hiện trong href chuẩn hóa?
- Host thật của URL có userinfo là evil.test hay trusted.example?
- Vì sao data: có origin serialize là "null"?
- Path a/../b được chuẩn hóa như thế nào?

### Bài B — Kiểm tra URL tương đối và base

Chạy:

```js
const base = new URL("https://app.example.com/account/settings");
const tests = [
  "/logout",
  "../admin",
  "//attacker.test/collect",
  "https://attacker.test/collect",
  "?next=%2Fhome",
  "#profile",
];

console.table(tests.map((value) => {
  const result = new URL(value, base);
  return {
    input: value,
    resolved: result.href,
    origin: result.origin,
    sameOrigin: result.origin === base.origin,
  };
}));
```

Tìm những đầu vào làm thay đổi origin. Giải thích tại sao //attacker.test/collect đổi host dù không ghi scheme.

### Bài C — Kiểm tra encoding của query

Chạy:

```js
const u = new URL("https://app.example.com/search");
u.searchParams.set("q", "a&role=admin + C++");

console.log(u.href);
console.log(new URL(u.href).searchParams.get("q"));
console.log(new URLSearchParams("q=a+b").get("q"));
console.log(new URLSearchParams("q=a%2Bb").get("q"));
```

Quan sát sự khác nhau giữa dấu + biểu diễn space trong form-url-encoded và %2B biểu diễn dấu cộng thực.

### Bài D — Thử kiểm tra URL redirect an toàn

Dùng hàm getSafeReturnUrl ở mục 8.5 và thử các giá trị:

```js
const candidates = [
  "/dashboard",
  "https://app.example.com/profile",
  "//attacker.test/phish",
  "https://app.example.com.attacker.test/",
  "https://app.example.com@attacker.test/",
  "javascript:alert(1)",
];

for (const value of candidates) {
  try {
    console.log(value, "=>", getSafeReturnUrl(value).href);
  } catch (error) {
    console.log(value, "=> REJECT:", error.message);
  }
}
```

Kết quả mong đợi: đường dẫn tương đối và URL cùng origin có thể được chấp nhận; URL chuyển sang origin khác hoặc scheme không hợp lệ bị từ chối bởi kiểm tra origin/scheme. Hàm ở mục 8.5 mới kiểm tra origin và userinfo; để loại javascript: và các scheme khác một cách tường minh, hãy bổ sung kiểm tra protocol === "https:" (hoặc scheme nội bộ được cho phép).

## 11. Checklist trước khi dùng URL do người dùng cung cấp

1. **Parse:** Dùng parser chuẩn (URL trong browser/Node.js), không tách URL bằng regex hoặc substring.
2. **Scheme:** Chỉ cho phép scheme phù hợp nghiệp vụ, thường là HTTPS cho URL bên ngoài.
3. **Authority:** Kiểm tra hostname, port, username, password; đừng nhầm userinfo với host.
4. **Allowlist:** So sánh origin/host đã chuẩn hóa với allowlist chính xác; chỉ cho phép subdomain nếu có lý do và kiểm soát được từng subdomain.
5. **Base URL:** Với URL tương đối, dùng base cố định đáng tin cậy và kiểm tra origin sau resolve.
6. **Redirect:** Kiểm tra URL đích và từng redirect hop; không để endpoint returnTo trở thành open redirect.
7. **Encoding:** Parse trước, decode đúng component một lần; không decode toàn URL hoặc decode nhiều lần không có quy ước.
8. **Path:** Kiểm tra canonicalization đồng nhất giữa proxy, framework, router và filesystem; phòng path traversal.
9. **Query:** Xử lý key lặp, dấu cộng, %2B và các tham số ảnh hưởng quyền một cách nhất quán.
10. **SSRF:** Với server fetch URL, kiểm tra DNS/IP, chặn mạng nội bộ và revalidate redirect; dùng egress control.
11. **Ngữ cảnh đầu ra:** Encode URL khi chèn vào HTML/attribute và áp dụng CSP phù hợp; URL parse hợp lệ không tự động an toàn trong mọi sink.
12. **Kiểm thử:** Thử host giả mạo, userinfo, port, IDN, IPv4 lạ, encoded dot/slash, URL tương đối và redirect.

## 12. Những hiểu lầm phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| "URL chỉ là chuỗi, có thể tách bằng / và :." | URL có cú pháp phụ thuộc scheme; dùng parser chuẩn. |
| "Parse thành công nghĩa là URL an toàn." | Parser chỉ xác định cấu trúc; ứng dụng vẫn phải kiểm tra scheme, origin, host và quyền nghiệp vụ. |
| "Hostname chứa chuỗi domain đáng tin là đủ." | Userinfo, suffix giả, IDN và cách biểu diễn IP có thể đánh lừa kiểm tra chuỗi. |
| "Mọi URL đều có host." | data:, mailto:, tel: và nhiều scheme không có authority HTTP-style. |
| "Fragment được gửi lên server." | Fragment được xử lý phía client và không nằm trong HTTP request thông thường. |
| "Port 443 luôn hiện trong URL." | Port mặc định có thể được chuẩn hóa và lược bỏ. |
| "Encode toàn bộ URL trước khi parse sẽ an toàn hơn." | Có thể biến dữ liệu thành dấu phân tách cấu trúc và làm parser hiểu khác. |
| "encodeURI và encodeURIComponent giống nhau." | Chúng giữ lại các tập ký tự khác nhau; chọn API theo component. |
| "Cùng hostname nghĩa là cùng origin." | Scheme và port cũng tham gia origin. |
| "Kiểm tra URL bằng startsWith/endsWith là đủ." | So sánh origin đã parse với allowlist chính xác. |
| "URL hợp lệ không thể gây SSRF." | URL hợp lệ vẫn có thể trỏ đến loopback, private IP hoặc redirect đến mạng nội bộ. |
| "CSP thay thế validate URL." | CSP là một lớp bảo vệ thực thi nội dung; validate URL theo nghiệp vụ vẫn cần thiết. |

## 13. Câu hỏi ôn tập

1. URL gồm những thành phần nào? Thành phần nào được dùng để xác định origin HTTP(S)?
2. Vì sao https://trusted.example@evil.test/ có host là evil.test?
3. Khác biệt giữa new URL("/account", base) và new URL("//evil.test/account", base) là gì?
4. Vì sao fragment không được gửi trong HTTP request thông thường?
5. Khi nào port bị lược bỏ trong URL serialization? Port có còn ảnh hưởng origin không?
6. Vì sao không nên decode toàn bộ URL trước khi parse?
7. URLSearchParams diễn giải + và %2B khác nhau như thế nào?
8. Vì sao kiểm tra hostname.endsWith("example.com") có thể sai?
9. Tại sao new URL() thành công chưa đủ để ngăn SSRF?
10. CSP base-uri giúp phòng vệ tình huống nào?

**Đáp án định hướng:** (1) Scheme, userinfo, host, port, path, query, fragment; origin dùng scheme/host/port. (2) Phần trước @ là userinfo, phần sau là host. (3) URL thứ nhất giữ origin của base; URL thứ hai thay authority/host nhưng giữ scheme. (4) Fragment là trạng thái phía client. (5) Port mặc định được chuẩn hóa thành không tường minh; port khác mặc định vẫn là thành phần origin. (6) Vì ký tự đã encode có thể biến thành dấu phân tách làm thay đổi cấu trúc. (7) Trong form-urlencoded, + là space còn %2B là dấu cộng. (8) Có thể nhận notexample.com; cần ranh giới nhãn hoặc allowlist chính xác. (9) Đích có thể là IP nội bộ, DNS rebinding hoặc redirect đến mạng nội bộ. (10) Hạn chế URL được dùng trong phần tử base, giảm nguy cơ URL tương đối bị chuyển sang host ngoài.

## 14. Tài liệu tham khảo

- [WHATWG URL Standard](https://url.spec.whatwg.org/): Chuẩn parser, URL record, host parsing, path, query và serialization.
- [MDN — URL](https://developer.mozilla.org/en-US/docs/Web/API/URL): API URL, constructor, thuộc tính và cách resolve URL.
- [MDN — URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams): Đọc/ghi query và quy tắc form-url-encoded.
- [MDN — Percent-encoding](https://developer.mozilla.org/en-US/docs/Glossary/Percent-encoding): Cách biểu diễn ký tự bằng %HH.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): Phòng open redirect.
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): Kiểm soát URL và đích mạng để phòng SSRF.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal): Các dạng path traversal và encoding.
- [MDN — CSP base-uri](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/base-uri): Hạn chế URL base của tài liệu.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP): Chính sách nội dung và phòng vệ XSS.

**Kết nối với mô hình bảo mật web:** URL parser xác định cách trình duyệt diễn giải địa chỉ và chuẩn hóa thành phần. Origin từ URL tham gia SOP/CORS; URL tương đối và redirect ảnh hưởng nơi điều hướng; query/path encoding ảnh hưởng cách server định tuyến và xác thực dữ liệu. Bảo mật yêu cầu parse nhất quán, kiểm tra sau canonicalization và áp dụng chính sách theo đúng ngữ cảnh sử dụng URL.
