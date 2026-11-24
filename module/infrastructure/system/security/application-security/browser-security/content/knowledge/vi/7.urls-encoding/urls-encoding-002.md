# URL normalization: phân tích và chuẩn hóa URL an toàn

## 1. Vì sao URL normalization quan trọng với bảo mật trình duyệt?

URL là đầu vào xuất hiện ở nhiều vị trí trong ứng dụng web: thanh địa chỉ, liên kết, biểu mẫu, redirect sau đăng nhập, tham số truy vấn, cấu hình API, iframe, hình ảnh và các request do JavaScript tạo ra. Một URL có thể được viết theo nhiều cách nhưng sau khi trình duyệt phân tích, nó lại trỏ tới cùng một địa chỉ. Ngược lại, hai chuỗi trông gần giống nhau có thể trỏ tới hai host hoặc hai đường dẫn hoàn toàn khác nhau.

Ví dụ, các URL sau có cách viết khác nhau:

```text
HTTPS://Example.COM:443/a/../profile
https://example.com/profile
```

Trình phân tích URL của trình duyệt chuẩn hóa scheme, hostname, port mặc định và các thành phần đường dẫn theo quy tắc URL. Kết quả có thể là cùng một URL được tuần tự hóa. Nếu ứng dụng kiểm tra chuỗi đầu vào trước khi phân tích, nhưng sau đó lại để browser hoặc server diễn giải theo cách khác, kẻ tấn công có thể lợi dụng sự khác biệt đó.

Trong module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`, URL normalization liên quan trực tiếp đến ranh giới **origin**, chính sách truy cập, điều hướng, cookie và các cơ chế chống XSS/CSRF. Một lỗi kiểm tra URL có thể dẫn đến:

- **Open redirect:** ứng dụng chuyển người dùng tới host do kẻ tấn công kiểm soát.
- **URL injection / XSS:** dữ liệu không tin cậy được đưa vào thuộc tính URL hoặc các vị trí có thể kích hoạt giao thức nguy hiểm.
- **Sai lệch kiểm tra origin/host:** allowlist kiểm tra chuỗi nhưng browser diễn giải hostname khác.
- **Path traversal hoặc bypass kiểm soát route:** các lớp proxy, server và ứng dụng chuẩn hóa dấu chấm hoặc percent-encoding không nhất quán.
- **Sai lệch cache/chữ ký:** hai thành phần dùng quy tắc chuẩn hóa khác nhau khi tạo cache key hoặc xác minh chữ ký URL.

### Kết quả học tập

Sau bài học, người học có thể:

1. Phân tích cấu trúc URL và giải thích cách browser parse, resolve và serialize URL.
2. Phân biệt URL parsing, normalization, percent-encoding và canonicalization theo ngữ nghĩa ứng dụng.
3. Dùng `URL` và `URLSearchParams` để xử lý URL theo từng thành phần.
4. Xây dựng allowlist cho origin, protocol và redirect mà không dựa vào so khớp chuỗi thiếu an toàn.
5. Nhận diện lỗi double decoding, encoded separator, dot segment, Unicode hostname và khác biệt parser giữa browser/proxy/server.
6. Viết bài kiểm thử chứng minh URL hợp lệ được chấp nhận và URL không hợp lệ bị từ chối.

## 2. Cấu trúc URL: phải biết mình đang kiểm tra phần nào

Một URL HTTP(S) có thể được phân tích thành các thành phần:

```text
https://alice:secret@app.example.com:8443/reports/2026?format=pdf&lang=vi#summary
└─┬─┘   └──────┬─────┘ └──────┬──────┘ └─┬─┘ └──────┬──────┘ └──────┬───────┘ └──┬──┘
scheme       credentials       hostname    port       path             query      fragment
```

| Thành phần | Ý nghĩa | Câu hỏi bảo mật |
| --- | --- | --- |
| Scheme | Giao thức như `https:`, `http:`, `mailto:`, `javascript:` | Có chỉ cho phép giao thức mà tính năng cần không? |
| Username/password | Thông tin xác thực nhúng trong authority | Có cần từ chối URL chứa credentials để tránh gây nhầm lẫn không? |
| Hostname | Tên máy chủ hoặc địa chỉ IP | Có khớp chính xác allowlist không? |
| Port | Cổng kết nối | Có phải cổng được phép không? |
| Path | Đường dẫn tài nguyên | Có bị dot segment, encoded separator hoặc traversal không? |
| Query | Các tham số sau dấu `?` | Tham số trùng, thứ tự và cách decode có được xử lý nhất quán không? |
| Fragment | Phần sau dấu `#` | Có được dùng làm route phía client hoặc vô tình chứa dữ liệu nhạy cảm không? |

**Fragment không được gửi trong HTTP request tới server.** Tuy nhiên, JavaScript phía client có thể đọc `location.hash` và dùng nó để điều hướng hoặc render nội dung. Do đó fragment vẫn cần được xử lý như dữ liệu không tin cậy khi đưa vào DOM.

Origin của URL HTTP(S) chỉ được xác định từ **scheme + host + port**. Path, query và fragment không thuộc origin. Hai URL có path khác nhau vẫn có thể cùng origin; hai URL có cùng hostname nhưng scheme hoặc port khác thì khác origin.

## 3. Parsing, normalization và canonicalization khác nhau ra sao?

Ba khái niệm này liên quan nhưng không đồng nghĩa.

| Khái niệm | Việc thực hiện | Ví dụ |
| --- | --- | --- |
| **Parsing** | Đọc chuỗi và tách thành các thành phần URL theo một bộ quy tắc | Nhận diện scheme, host, port, path, query |
| **Normalization** | Chuyển biểu diễn URL về dạng tuần tự hóa theo quy tắc parser | Viết thường scheme/host, loại port mặc định, xử lý dot segment |
| **Canonicalization** | Chọn một biểu diễn chuẩn theo ngữ nghĩa của một ứng dụng cụ thể để so sánh, ký hoặc lưu | Quy định cách xử lý query trùng, thứ tự tham số, dấu gạch chéo cuối |

Browser sử dụng **WHATWG URL Standard** để parse và serialize URL trong các API web hiện đại. Server, reverse proxy, CDN, framework router và thư viện khác có thể sử dụng parser hoặc quy tắc riêng. Vì thế không nên cho rằng một chuỗi sau khi browser serialize chắc chắn sẽ được mọi lớp backend diễn giải giống hệt.

**Normalization không phải là xác thực.** Một URL sau khi parse thành công vẫn có thể trỏ tới host không tin cậy, dùng protocol nguy hiểm, chứa credentials hoặc trỏ tới route không được phép.

### 3.1. Những phép chuẩn hóa phổ biến với URL HTTP(S)

| Thành phần | Hành vi thường thấy khi browser parse/serialize |
| --- | --- |
| Scheme | Được chuẩn hóa về chữ thường, ví dụ `HTTPS:` thành `https:` |
| Hostname | Được chuẩn hóa theo quy tắc host, bao gồm chuyển chữ hoa thành chữ thường và xử lý IDNA |
| Port mặc định | Port mặc định của scheme thường được loại khỏi dạng serialize, ví dụ `:443` của HTTPS |
| Path dot segment | Các đoạn `.` và `..` được xử lý để giải quyết đường dẫn; một số dạng percent-encoded của dot segment cũng được nhận diện |
| Space và ký tự cần encode | Được percent-encode theo quy tắc của từng thành phần |
| Backslash với special scheme | Với các scheme đặc biệt như HTTP/HTTPS, dấu `\` có thể được xử lý như dấu `/` ở một số vị trí parse |
| Query và fragment | Được giữ như các thành phần riêng; browser không tự quyết định rằng hai query khác thứ tự luôn có cùng ý nghĩa |

Ví dụ trong JavaScript:

```js
const url = new URL("HTTPS://Example.COM:443/a/../profile?view=full#top");

console.log(url.href);
// "https://example.com/profile?view=full#top"

console.log(url.origin);
// "https://example.com"

console.log(url.pathname);
// "/profile"
```

Kết quả minh họa cách serialize theo URL parser của browser. Nếu ứng dụng ký URL, xác minh chữ ký hoặc tạo cache key, cần xác định chính xác thành phần nào tham gia thuật toán và dùng cùng quy tắc ở mọi phía.

### 3.2. URL tương đối cần một base URL

Chuỗi `/account`, `../images/logo.svg` hoặc `//cdn.example.com/app.js` chưa phải lúc nào cũng là một URL tuyệt đối. Browser cần một **base URL** để resolve:

```js
const base = "https://app.example.com/users/42/";

console.log(new URL("settings", base).href);
// https://app.example.com/users/42/settings

console.log(new URL("../help", base).href);
// https://app.example.com/users/help

console.log(new URL("/login", base).href);
// https://app.example.com/login

console.log(new URL("//cdn.example.net/app.js", base).href);
// https://cdn.example.net/app.js
```

Đặc biệt, **URL bắt đầu bằng `//` có thể thay host**. Nếu ứng dụng cho phép người dùng cung cấp đường dẫn redirect tương đối, phải kiểm tra URL sau khi resolve, không chỉ nhìn chuỗi đầu vào.

## 4. Percent-encoding: mã hóa đúng thành phần

Percent-encoding biểu diễn một byte bằng dấu `%` theo sau hai chữ số hex. Ví dụ:

| Ký tự | Biểu diễn thường gặp |
| --- | --- |
| Space | `%20` hoặc `+` trong ngữ cảnh form-urlencoded |
| `/` | `%2F` khi cần biểu diễn trong một thành phần |
| `?` | `%3F` khi nằm trong giá trị, thay vì làm dấu bắt đầu query |
| `#` | `%23` khi nằm trong giá trị, thay vì bắt đầu fragment |
| `&` | `%26` trong giá trị query để không bị hiểu là dấu phân cách tham số |
| `%` | `%25` khi chính dấu phần trăm là dữ liệu |

Không phải mọi ký tự đều phải encode trong mọi thành phần. Một ký tự có ý nghĩa phân cách trong cấu trúc URL có thể là dữ liệu bình thường bên trong một giá trị đã encode.

### 4.1. Dùng đúng API theo thành phần

**`encodeURIComponent()`** phù hợp khi mã hóa một giá trị thành phần, ví dụ một segment hoặc một giá trị cần chèn vào query. **`encodeURI()`** giữ lại nhiều ký tự phân cách cấu trúc URL nên không phù hợp để encode một giá trị tùy ý.

```js
const fileName = "báo cáo tháng 11.pdf";
const segment = encodeURIComponent(fileName);

const url = new URL("https://files.example.com/download");
url.pathname += "/" + segment;

console.log(url.href);
```

Với query string, ưu tiên `URLSearchParams`:

```js
const params = new URLSearchParams();
params.set("q", "browser security & URL");
params.set("page", "2");

const url = new URL("https://search.example.com/");
url.search = params.toString();

console.log(url.href);
// Query được encode theo quy tắc application/x-www-form-urlencoded.
```

Không tự ghép chuỗi query bằng cách nối dữ liệu chưa encode:

```js
// Không an toàn: giá trị có thể làm thay đổi cấu trúc query.
const unsafe = "/search?q=" + userInput;

// An toàn hơn: API xử lý riêng giá trị và dấu phân cách.
const safe = new URL("/search", location.origin);
safe.searchParams.set("q", userInput);
```

### 4.2. Dấu cộng trong query không phải lúc nào cũng là dấu cộng

`URLSearchParams` dùng quy tắc form-urlencoded: khi parse query, dấu `+` được hiểu là space. Nếu dữ liệu thực sự chứa dấu cộng, nó cần được encode thành `%2B`.

```js
const a = new URLSearchParams("q=C++");
console.log(a.get("q")); // "C  "

const b = new URLSearchParams("q=C%2B%2B");
console.log(b.get("q")); // "C++"

const c = new URLSearchParams();
c.set("q", "C++");
console.log(c.toString()); // q=C%2B%2B
```

Khi xử lý dữ liệu query, cần thống nhất cách parse giữa browser và backend. Một framework có thể xử lý `+`, `%20`, tham số trùng hoặc dấu phân cách khác với thư viện phía client.

### 4.3. Không decode toàn bộ URL

Một URL có các dấu phân cách cấu trúc như `/`, `?`, `&`, `=`, `#`. Nếu gọi `decodeURIComponent()` trên cả URL, các ký tự vốn được encode như dữ liệu có thể biến thành dấu phân cách, làm thay đổi cấu trúc mà ứng dụng định kiểm tra.

```js
const input = "https://app.example.com/search?q=a%26role%3Dadmin";

// Không làm thế này với toàn bộ URL:
// decodeURIComponent(input)

// Parse trước, sau đó đọc đúng thành phần cần xử lý:
const parsed = new URL(input);
const query = parsed.searchParams.get("q");

console.log(query); // "a&role=admin" là một giá trị q duy nhất
```

Chỉ decode tại **đúng ranh giới dữ liệu**, theo đúng số lần mà giao thức của ứng dụng quy định. Decode hai lần có thể biến `%252e%252e` thành `%2e%2e`, rồi thành `..`; điều đó tạo cơ hội cho path traversal nếu các lớp xử lý không nhất quán.

## 5. Những phép chuẩn hóa cần đặc biệt chú ý

### 5.1. Scheme, hostname và port

Browser thường chuẩn hóa scheme và hostname về chữ thường. Port mặc định của scheme cũng được loại khỏi serialization:

```js
const a = new URL("HTTPS://EXAMPLE.COM:443/a");
const b = new URL("https://example.com/b");

console.log(a.origin); // https://example.com
console.log(b.origin); // https://example.com
console.log(a.origin === b.origin); // true
```

Vì vậy, khi so sánh origin, hãy dùng thuộc tính `URL.origin` sau khi parse. Không tự viết biểu thức regex để so sánh chuỗi URL thô.

Lưu ý: `origin` không chứa username/password. Một URL như `https://trusted.example@attacker.test/` có hostname thực là `attacker.test`; phần `trusted.example` chỉ là username. Đây là một lý do phải kiểm tra `url.hostname`, `url.origin` và từ chối credentials khi không cần thiết.

### 5.2. Dot segment và path traversal

Đường dẫn có thể chứa `.` và `..`:

```js
const url = new URL("https://app.example.com/public/../admin");
console.log(url.pathname); // /admin
```

URL parser của browser còn nhận diện một số dạng dot segment được percent-encode. Tuy nhiên, **không được dựa vào một phép parse phía browser để bảo vệ filesystem hoặc router phía server**. Reverse proxy, web server và framework có thể decode hoặc normalize ở những thời điểm khác nhau.

Một số biểu diễn cần đưa vào bộ kiểm thử:

| Đầu vào path | Vấn đề cần kiểm tra |
| --- | --- |
| `/public/../admin` | Dot segment thông thường |
| `/public/%2e%2e/admin` | Dot segment có percent-encoding |
| `/public/%252e%252e/admin` | Có thể trở thành dot segment sau hai lần decode |
| `/public/%2Fadmin` | Encoded slash có thể được giữ như dữ liệu hoặc được lớp backend giải mã thành dấu phân cách |
| `/public/%5Cadmin` | Encoded backslash; cách xử lý phụ thuộc parser và hệ điều hành/router |
| `/public//admin` | Nhiều dấu slash; một số thành phần có thể gộp, thành phần khác giữ nguyên |

**Nguyên tắc phòng vệ:**

1. Parse URL bằng parser chuẩn, không kiểm tra chuỗi thô rồi mới parse bằng một bộ quy tắc khác.
2. Xác định chính xác thành phần nào được phép và chỉ decode dữ liệu đúng một lần ở ranh giới đã chọn.
3. Thống nhất canonicalization giữa CDN, reverse proxy, web server và application router.
4. Nếu route hoặc tài nguyên không cho phép encoded slash/backslash, từ chối chúng theo một chính sách rõ ràng ở lớp có thẩm quyền.
5. Kiểm tra quyền truy cập trên tài nguyên thực tế sau khi router đã xác định đích; không dùng kiểm tra prefix chuỗi thay cho authorization.

### 5.3. Encoded separator và sự khác biệt giữa các lớp

Giả sử CDN kiểm tra path trước khi decode, còn application server decode `%2F` thành `/`. Một URL được CDN xem là:

```text
/users/alice%2F..%2Fadmin
```

nhưng ứng dụng có thể diễn giải thành:

```text
/users/alice/../admin
```

Nếu hai lớp không thống nhất, quy tắc kiểm soát truy cập có thể bị bypass. Đây là **parser differential**: cùng một chuỗi nhưng các thành phần diễn giải khác nhau.

Không có một quy tắc chung rằng mọi server đều giữ hoặc giải mã `%2F`. Hãy xác minh bằng đúng proxy, server và framework đang vận hành. Với dữ liệu nhạy cảm, ưu tiên route có cấu trúc rõ, tham số định danh được xác thực và kiểm tra quyền tại backend.

### 5.4. Unicode hostname và IDN homograph

Tên miền quốc tế hóa (Internationalized Domain Name – IDN) cho phép hostname chứa ký tự Unicode. Browser xử lý hostname theo quy tắc IDNA và có thể chuyển sang dạng ASCII tương ứng gọi là **Punycode**.

Một số ký tự Unicode nhìn gần giống chữ Latin nhưng là ký tự khác. Kẻ tấn công có thể tạo hostname trông giống thương hiệu thật để lừa người dùng. Do đó:

- Không xác minh host bằng cách nhìn chuỗi hiển thị trên giao diện.
- Khi kiểm tra quyền, dùng hostname đã được URL parser chuẩn hóa và so sánh chính xác với allowlist.
- Với UI hiển thị link bên ngoài, cân nhắc hiển thị hostname rõ ràng và cảnh báo khi có tên miền quốc tế hóa gây nhầm lẫn.
- Không dùng so khớp chuỗi kiểu `includes("example.com")` hoặc `endsWith("example.com")` mà không kiểm tra ranh giới domain.

Ví dụ kiểm tra sai:

```js
// Sai: attacker-example.com hoặc example.com.attacker.test
// có thể làm kiểm tra chuỗi này cho kết quả ngoài ý muốn.
if (input.includes("example.com")) {
  // Cho phép?
}
```

Thay vào đó:

```js
const url = new URL(input);
const allowedHosts = new Set([
  "app.example.com",
  "docs.example.com"
]);

if (!allowedHosts.has(url.hostname)) {
  throw new Error("Host không được phép");
}
```

Nếu cần cho phép cả subdomain, hãy thiết kế điều kiện theo ranh giới nhãn DNS, ví dụ host bằng chính xác `example.com` hoặc kết thúc bằng `.example.com`; vẫn cần xác định rõ subdomain nào được tin cậy. Không coi mọi subdomain cùng site là đáng tin cậy.

## 6. Xác thực URL an toàn trong ứng dụng

Một quy trình an toàn thường có các bước:

1. **Chọn base URL rõ ràng** nếu chấp nhận URL tương đối.
2. **Parse bằng `new URL()`** và xử lý lỗi parse.
3. **Kiểm tra protocol** theo yêu cầu tính năng.
4. **Từ chối credentials** nếu không có trường hợp sử dụng hợp lệ.
5. **So sánh origin/hostname/port** với allowlist sau khi parse.
6. **Kiểm tra path, query và fragment** theo quy tắc nghiệp vụ riêng.
7. Dùng URL đã kiểm tra để điều hướng hoặc tạo request; không quay lại dùng chuỗi đầu vào thô.

### 6.1. Hàm kiểm tra URL HTTPS theo allowlist

```js
const ALLOWED_ORIGINS = new Set([
  "https://app.example.com",
  "https://docs.example.com"
]);

function parseAllowedHttpsUrl(input, base = "https://app.example.com/") {
  let url;

  try {
    url = new URL(input, base);
  } catch {
    return null;
  }

  if (url.protocol !== "https:") return null;
  if (url.username !== "" || url.password !== "") return null;
  if (!ALLOWED_ORIGINS.has(url.origin)) return null;

  return url;
}

const accepted = parseAllowedHttpsUrl("/account");
const rejected = parseAllowedHttpsUrl("https://attacker.test/");

console.log(accepted?.href); // https://app.example.com/account
console.log(rejected);       // null
```

Hàm trên kiểm tra URL sau khi browser parser resolve và normalize. Danh sách allowlist là **origin tuyệt đối**; không dùng wildcard hoặc so sánh prefix. Nếu ứng dụng cần HTTP ở môi trường local, hãy dùng cấu hình môi trường riêng và giới hạn nó cho môi trường phát triển.

### 6.2. Redirect an toàn

Open redirect thường xuất hiện khi ứng dụng nhận tham số như `?returnUrl=...` rồi chuyển hướng tới giá trị đó mà không xác thực. Một URL tương đối cũng có thể dùng dạng `//attacker.test/path` để đổi host.

Nếu tính năng chỉ cho phép redirect trong cùng origin:

```js
function safeReturnPath(input) {
  const trustedOrigin = "https://app.example.com";
  let target;

  try {
    target = new URL(input, trustedOrigin);
  } catch {
    return "/home";
  }

  if (target.protocol !== "https:") return "/home";
  if (target.origin !== trustedOrigin) return "/home";
  if (target.username || target.password) return "/home";

  return target.pathname + target.search + target.hash;
}
```

Nếu nghiệp vụ cần redirect tới nhiều host, dùng allowlist origin cụ thể và kiểm tra từng origin sau parse. Không cho phép mọi host chỉ vì URL dùng HTTPS.

### 6.3. Kiểm tra path theo segment

Kiểm tra prefix thô dễ mắc lỗi:

```js
// Sai: /reports-evil cũng bắt đầu bằng /reports
if (url.pathname.startsWith("/reports")) {
  allow();
}
```

Nếu chỉ cho phép route báo cáo và các route con:

```js
function isReportsRoute(pathname) {
  return pathname === "/reports" || pathname.startsWith("/reports/");
}
```

Đây chỉ là kiểm tra định tuyến ở client. **Quyền xem báo cáo phải được xác minh trên server** sau khi route được phân giải; không dùng URL path làm bằng chứng người dùng có quyền truy cập.

Với route có tham số động, ưu tiên router định nghĩa rõ segment và validate từng tham số. Nếu backend giải mã separator hoặc chuẩn hóa path khác browser, cần kiểm tra bằng test tích hợp thay vì giả định hàm JavaScript đã xử lý hết.

## 7. URL trong DOM: tránh URL injection và XSS

URL không chỉ là địa chỉ điều hướng. Khi đưa vào DOM, nó có thể trở thành một **navigation sink** hoặc resource-loading sink. Một giá trị như `javascript:...` có thể nguy hiểm nếu được đặt vào một thuộc tính URL có thể kích hoạt mã.

Không đưa dữ liệu không tin cậy vào HTML bằng cách nối chuỗi:

```js
// Không an toàn: vừa tạo HTML từ dữ liệu không tin cậy,
// vừa không kiểm soát protocol của href.
container.innerHTML = '<a href="' + userUrl + '">' + userLabel + '</a>';
```

Hãy parse và kiểm tra URL trước, sau đó tạo node bằng DOM API:

```js
function appendExternalLink(container, rawUrl, label) {
  let url;
  try {
    url = new URL(rawUrl);
  } catch {
    return false;
  }

  if (!["https:", "http:"].includes(url.protocol)) return false;
  if (url.username || url.password) return false;

  const link = document.createElement("a");
  link.href = url.href;
  link.textContent = label;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  container.append(link);
  return true;
}
```

Chỉ cho phép HTTP nếu tính năng thực sự cần liên kết HTTP; với ứng dụng nhạy cảm nên yêu cầu HTTPS. `textContent` đặt nhãn dưới dạng text, tránh diễn giải nhãn thành HTML. `noopener` ngăn trang mới điều khiển `window.opener`; `noreferrer` còn giới hạn gửi referrer trong hành vi tương ứng.

**Kiểm tra protocol phải diễn ra sau parsing.** Đừng chỉ tìm chuỗi `https` ở đầu input, vì input có thể là URL tương đối, URL có credentials, URL protocol-relative hoặc chứa ký tự/encoding làm thay đổi cách diễn giải.

## 8. Query parameter: giá trị trùng và thứ tự

Query string không phải lúc nào cũng có một biểu diễn duy nhất. Hai URL:

```text
https://app.example.com/search?a=1&b=2
https://app.example.com/search?b=2&a=1
```

có thể có cùng ý nghĩa với một ứng dụng, nhưng không nhất thiết tương đương đối với mọi hệ thống ký, cache hoặc backend. Tương tự, tham số trùng có thể được hiểu theo nhiều cách:

```text
?role=user&role=admin
```

Một thư viện có thể lấy giá trị đầu, thư viện khác lấy giá trị cuối, một thư viện khác trả về danh sách. Nếu lớp kiểm soát truy cập và lớp xử lý nghiệp vụ chọn giá trị khác nhau, có thể phát sinh parameter pollution.

Với `URLSearchParams`:

```js
const url = new URL(
  "https://app.example.com/action?role=user&role=admin"
);

console.log(url.searchParams.get("role"));    // Giá trị đầu tiên
console.log(url.searchParams.getAll("role")); // ["user", "admin"]
```

**Chính sách cần chọn rõ ràng:**

- Với tham số đơn trị quan trọng như `redirect`, `role`, `accountId`, có thể từ chối nếu xuất hiện nhiều lần.
- Với tham số đa trị có chủ đích, xử lý thành danh sách và validate từng giá trị.
- Backend phải dùng một quy tắc duy nhất xuyên suốt validation, authorization và business logic.
- Nếu URL được ký, phải thống nhất quy tắc canonicalization của query (thứ tự, encoding, duplicate, empty value) giữa bên ký và bên xác minh.

Ví dụ từ chối tham số redirect trùng:

```js
const url = new URL(location.href);
const redirects = url.searchParams.getAll("returnUrl");

if (redirects.length !== 1) {
  throw new Error("returnUrl phải xuất hiện đúng một lần");
}

const target = parseAllowedHttpsUrl(redirects[0]);
if (!target) throw new Error("URL chuyển hướng không hợp lệ");
```

## 9. URL normalization và các ranh giới bảo mật liên quan

| Ranh giới/cơ chế | URL normalization ảnh hưởng thế nào? | Điều cần kiểm tra |
| --- | --- | --- |
| Origin và SOP | Scheme, host và port sau parse quyết định origin | So sánh `URL.origin`, không so chuỗi raw |
| CORS | Request `Origin` là origin của document, còn URL đích quyết định nơi gửi request | Không dùng URL đích để thay thế allowlist origin gửi |
| Cookie | URL đích và ngữ cảnh request ảnh hưởng cookie domain/path/SameSite/Secure | Xác định URL thực tế sau redirect và scheme |
| CSRF | URL điều hướng/action có thể trỏ tới endpoint thay đổi trạng thái | Xác minh nguồn, CSRF token và authorization tại server |
| CSP | `connect-src`, `img-src`, `frame-src` có thể giới hạn đích tải/kết nối | Kiểm tra URL cuối sau resolve/redirect |
| XSS | URL đưa vào thuộc tính DOM có thể kích hoạt protocol hoặc navigation nguy hiểm | Parse, allowlist scheme/host và dùng DOM API |
| Redirect | URL tương đối, protocol-relative và credentials có thể đổi đích | Resolve với base tin cậy, kiểm tra origin |
| Cache/signature | Cách encode, thứ tự query và path có thể tạo key khác nhau | Dùng một thuật toán canonicalization nhất quán |

URL normalization không thay thế các cơ chế trên. Nó là bước giúp mọi thành phần hiểu **địa chỉ thực sự mà ứng dụng đang xử lý** trước khi áp dụng chính sách tương ứng.

## 10. Thực hành: quan sát browser parse và normalize URL

Mở DevTools → Console trên một trang bất kỳ và chạy đoạn mã:

```js
const samples = [
  "HTTPS://Example.COM:443/a/../profile",
  "https://example.com/%2e%2e/admin",
  "https://example.com/a%2Fb",
  "https://user:pass@example.com/account",
  "https://example.com.attacker.test/",
  "//cdn.example.net/app.js",
  "/login?next=%2Fadmin#form"
];

for (const input of samples) {
  try {
    const url = new URL(input, "https://app.example.com/current/page");
    console.log({
      input,
      href: url.href,
      origin: url.origin,
      hostname: url.hostname,
      username: url.username,
      pathname: url.pathname,
      search: url.search,
      hash: url.hash
    });
  } catch (error) {
    console.log({ input, error: error.message });
  }
}
```

### Bảng dự đoán

| Input | Điều cần xác nhận |
| --- | --- |
| `HTTPS://Example.COM:443/a/../profile` | Scheme/host được chuẩn hóa; port mặc định và dot segment được xử lý |
| `https://example.com/%2e%2e/admin` | Browser nhận diện dạng encoded dot segment theo URL parser |
| `https://example.com/a%2Fb` | Quan sát encoded slash trong `pathname`; không giả định mọi server giữ nguyên |
| `https://user:pass@example.com/account` | Host là `example.com`; username/password là thành phần riêng |
| `https://example.com.attacker.test/` | Host không phải `example.com` |
| `//cdn.example.net/app.js` | Base URL quyết định scheme, nhưng host chuyển sang `cdn.example.net` |
| `/login?next=%2Fadmin#form` | Đường dẫn tương đối được resolve theo base; query và fragment là hai thành phần riêng |

**Câu hỏi sau khi chạy:**

1. Vì sao hai URL đầu tiên có thể serialize về path giống nhau?
2. Vì sao `url.origin` không thể hiện username/password?
3. Vì sao `//cdn.example.net/app.js` không phải đường dẫn cùng host với base URL?
4. Vì sao `pathname` giữ thông tin percent-encoding không có nghĩa backend sẽ xử lý giống browser?
5. Khi một URL parse thành công, còn những điều kiện nào phải kiểm tra trước khi điều hướng?

## 11. Bộ kiểm thử bảo mật cho URL normalization

Đối với tính năng nhận URL từ người dùng, hãy tạo test case theo từng thành phần thay vì chỉ thử một vài chuỗi thông thường.

| Nhóm | Ví dụ đầu vào | Kết quả chính sách mong muốn |
| --- | --- | --- |
| Scheme không được phép | `javascript:alert(1)`, `data:text/html,...` | Từ chối nếu tính năng chỉ cho HTTP(S) |
| Host giả mạo | `https://example.com.attacker.test/` | Không khớp allowlist |
| Credentials | `https://trusted.example@attacker.test/` | Từ chối credentials; xác định hostname thật là attacker.test |
| Protocol-relative | `//attacker.test/path` | Resolve rồi kiểm tra origin; từ chối nếu host không được phép |
| Default port | `https://example.com:443/` | So sánh origin đã normalize với HTTPS mặc định |
| Port ngoài allowlist | `https://example.com:8443/` | Từ chối nếu port không nằm trong origin được phép |
| Dot segment | `/public/../admin` | Route được phân tích theo canonical path và kiểm tra quyền |
| Encoded dot segment | `/public/%2e%2e/admin` | Kết quả không được bypass kiểm soát route |
| Double encoding | `/public/%252e%252e/admin` | Không decode lặp ngoài quy định |
| Encoded separator | `/users/a%2Fadmin` | Proxy/server/router thống nhất cách xử lý; áp dụng chính sách rõ |
| Query trùng | `?role=user&role=admin` | Từ chối hoặc xử lý đa trị thống nhất |
| Query có dấu cộng | `?q=C%2B%2B` và `?q=C++` | Kiểm tra quy tắc decode và giá trị thực |
| Unicode hostname | Domain có ký tự tương tự chữ Latin | Parse IDNA và so sánh hostname chuẩn hóa; tránh nhầm lẫn hiển thị |
| URL tương đối | `../account`, `/login` | Resolve bằng base được chỉ định và kiểm tra đích |

### Cách đánh giá kết quả

Với mỗi test, ghi lại:

1. Chuỗi đầu vào nguyên bản.
2. Giá trị URL sau khi browser parse/serialize.
3. `origin`, `hostname`, `port`, `pathname`, `searchParams` và fragment.
4. URL mà request thực tế sử dụng trong Network, gồm cả redirect nếu có.
5. Cách reverse proxy và backend route/decode giá trị.
6. Quyết định allow/deny và lý do.

Không kết luận một test an toàn chỉ vì browser từ chối điều hướng. Cần xác minh **request có được gửi không**, **server nhận path nào**, và **server có thực hiện hành động nhạy cảm không**.

## 12. Tình huống tổng hợp: redirect sau đăng nhập

**Bối cảnh:** ứng dụng `https://app.example.com` nhận tham số `returnUrl` để đưa người dùng về trang ban đầu sau khi đăng nhập. Đoạn code cũ:

```js
const target = new URLSearchParams(location.search).get("returnUrl");
location.href = target || "/home";
```

Đoạn code này cho phép nhiều loại URL tương đối và tuyệt đối, kể cả host bên ngoài hoặc scheme không mong muốn. Hãy gia cố theo yêu cầu:

- Chỉ redirect trong origin `https://app.example.com`.
- Từ chối tham số `returnUrl` xuất hiện nhiều lần.
- Từ chối credentials và protocol không phải HTTPS.
- Dùng URL đã parse, không dùng lại raw input.
- Nếu không hợp lệ, chuyển về `/home`.

Một cách triển khai:

```js
function resolveLoginReturnUrl(search) {
  const params = new URLSearchParams(search);
  const values = params.getAll("returnUrl");
  if (values.length > 1) return "/home";
  if (values.length === 0 || values[0] === "") return "/home";

  let target;
  try {
    target = new URL(values[0], "https://app.example.com/");
  } catch {
    return "/home";
  }

  if (target.protocol !== "https:") return "/home";
  if (target.origin !== "https://app.example.com") return "/home";
  if (target.username || target.password) return "/home";

  return target.pathname + target.search + target.hash;
}

location.assign(resolveLoginReturnUrl(location.search));
```

**Lưu ý:** kiểm tra ở frontend giúp tránh điều hướng sai trong giao diện, nhưng server vẫn phải kiểm tra redirect nếu endpoint đăng nhập thực hiện redirect bằng HTTP `Location`. Nếu URL được lưu vào session hoặc gửi qua nhiều thành phần, mỗi ranh giới tin cậy cần áp dụng cùng chính sách. Không để một lớp frontend đã validate trở thành lý do bỏ qua kiểm tra server.

### Tiêu chí hoàn thành

Bài tập đạt khi:

- URL hợp lệ trong origin được phép vẫn chuyển hướng đúng.
- URL ngoài host, khác scheme, khác port, protocol-relative trỏ ra ngoài hoặc có credentials đều bị từ chối.
- Query parameter trùng được xử lý theo chính sách đã nêu.
- Kết quả browser parse và kết quả server redirect không mâu thuẫn.
- Có bằng chứng test từ Console, Network và log server.

## 13. Checklist khi xử lý URL trong ứng dụng web

- [ ] Parse bằng API URL chuẩn thay vì regex tự tách chuỗi.
- [ ] Resolve URL tương đối với base URL tin cậy.
- [ ] Kiểm tra protocol, hostname, port và origin sau khi parse.
- [ ] Từ chối username/password nếu tính năng không cần URL credentials.
- [ ] Dùng allowlist chính xác; không dùng `includes()` hoặc prefix hostname.
- [ ] Encode theo từng thành phần; dùng `URLSearchParams` cho query.
- [ ] Không decode toàn bộ URL và không decode lặp.
- [ ] Quy định rõ cách xử lý dot segment, encoded slash/backslash và query trùng.
- [ ] Đồng bộ normalization giữa browser, CDN, reverse proxy và backend.
- [ ] Kiểm tra quyền trên tài nguyên cuối cùng tại server.
- [ ] Khi đưa URL vào DOM, parse/validate trước và dùng DOM API an toàn.
- [ ] Kiểm thử redirect, fragment, URL Unicode và các trường hợp parser differential.

### Ghi nhớ

**URL normalization giúp xác định địa chỉ mà browser thực sự hiểu, nhưng không tự chứng minh địa chỉ đó đáng tin cậy.** Hãy parse trước, kiểm tra từng thành phần sau parse, encode/decode đúng ngữ cảnh và giữ cách diễn giải nhất quán giữa browser với backend. Đặc biệt, origin phải được so sánh từ URL đã parse; redirect và URL sink cần allowlist protocol/host; path, query và percent-encoding cần được kiểm tra theo đúng quy tắc router. Mọi quyền truy cập và hành động nhạy cảm vẫn phải được xác minh ở phía server.
