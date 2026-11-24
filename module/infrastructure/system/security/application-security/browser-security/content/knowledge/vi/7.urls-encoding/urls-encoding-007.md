# Query parameter: cấu trúc, encoding và bảo mật

## 1. Query parameter là gì?

**Query parameter** là cặp tên/giá trị hoặc dữ liệu được đặt trong phần query của URL, bắt đầu sau dấu `?`. Ví dụ:

~~~text
https://shop.example.test/products?category=books&page=2&sort=price
~~~

Trong URL này:

- Scheme: `https`
- Host: `shop.example.test`
- Path: `/products`
- Query: `category=books&page=2&sort=price`
- Fragment: không có

Query thường dùng để truyền bộ lọc, tìm kiếm, phân trang, thứ tự sắp xếp, tùy chọn hiển thị hoặc tham số nghiệp vụ. Khi trình duyệt gửi HTTP request tới tài nguyên đó, query thường xuất hiện trong request-target:

~~~http
GET /products?category=books&page=2&sort=price HTTP/1.1
Host: shop.example.test
~~~

Khác với **fragment** bắt đầu bằng `#`, query thường được gửi tới server. Vì vậy nó có thể xuất hiện trong access log, proxy log, hệ thống giám sát, lịch sử trình duyệt, cache key và một số header điều hướng như `Referer` tùy chính sách.

Bài học này thuộc chương **URL và encoding** của module `SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY`. Mục tiêu là hiểu cách đọc, tạo, mã hóa và kiểm tra query parameter để tránh sai lệch giữa trình duyệt, proxy, framework và backend; đồng thời phòng vệ những lỗi như XSS, SQL injection, open redirect, SSRF, parameter pollution và rò rỉ dữ liệu nhạy cảm.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân tích query trong URL và phân biệt query với path, fragment, origin.
2. Dùng `URL` và `URLSearchParams` để tạo, đọc, sửa và mã hóa query đúng cách.
3. Hiểu percent-encoding, dấu `+`, Unicode, giá trị rỗng, tham số lặp và thứ tự tham số.
4. Nhận diện khác biệt parser/canonicalization có thể tạo parameter pollution hoặc bypass validation.
5. Kiểm tra query parameter ở server theo schema, kiểu dữ liệu, allowlist, giới hạn độ dài và quyền nghiệp vụ.
6. Nhận diện query có thể dẫn đến XSS, SQL injection, open redirect, SSRF, cache poisoning hoặc rò rỉ bí mật.
7. Kiểm chứng hành vi bằng DevTools, Network, URL parser và một endpoint thử nghiệm.

## 2. Cấu trúc query trong URL

Ví dụ:

~~~text
https://api.example.test/v1/products?category=books&page=2&tag=security#results
                                               └────────────────────────┘
                                                         query
~~~

Một URL tổng quát có thể gồm:

~~~text
scheme://host[:port]/path?query#fragment
~~~

| Thành phần | Ví dụ | Có được gửi trong request-target HTTP thông thường? | Vai trò |
| --- | --- | --- | --- |
| Scheme | `https` | Không phải phần request-target | Chọn giao thức. |
| Host | `api.example.test` | Thường truyền qua Host/:authority | Đích máy chủ. |
| Path | `/v1/products` | Có | Chọn resource/route. |
| Query | `category=books&page=2` | Có | Tham số của resource hoặc ứng dụng. |
| Fragment | `results` | **Không** | Điều hướng/trạng thái phía client. |

Query bắt đầu ở dấu `?` đầu tiên trước fragment. Dấu `#` kết thúc phần query trong cú pháp URL và mở đầu fragment. Nếu query chứa ký tự `#` như dữ liệu, ký tự đó cần được percent-encode thành `%23`.

Ví dụ:

~~~text
/search?q=red%23blue
~~~

Ở đây `%23` là dữ liệu bên trong giá trị `q`, không phải fragment delimiter.

### 2.1. Query không có một cấu trúc duy nhất bắt buộc cho mọi ứng dụng

Nhiều ứng dụng sử dụng định dạng phổ biến:

~~~text
?name=value&name2=value2
~~~

Đây là cách biểu diễn thường gặp của `application/x-www-form-urlencoded` và `URLSearchParams`. Tuy nhiên, server và framework có thể hỗ trợ các quy ước khác nhau:

~~~text
?tag=security&tag=browser
?tag[]=security&tag[]=browser
?filter[status]=active
?sort=price,desc
?ids=12,15,18
~~~

Không được giả định mọi server đều hiểu các dạng trên như nhau. Dữ liệu lặp có thể được parse thành mảng, lấy giá trị đầu tiên, lấy giá trị cuối cùng hoặc bị từ chối. Cần xác định hợp đồng API cụ thể và kiểm tra parser thực tế.

## 3. Query parameter và URL encoding

URL có một tập ký tự được phép xuất hiện trực tiếp và các ký tự có ý nghĩa phân cách cấu trúc. Khi một giá trị chứa ký tự đặc biệt, nó thường được biểu diễn bằng **percent-encoding**: dấu `%` theo sau bởi hai chữ số hexadecimal biểu diễn byte.

Ví dụ:

| Ký tự dữ liệu | Biểu diễn percent-encoded thường gặp |
| --- | --- |
| Dấu cách | `%20` hoặc `+` trong form encoding |
| `&` | `%26` |
| `=` | `%3D` |
| `?` | `%3F` |
| `#` | `%23` |
| `+` | `%2B` |
| `%` | `%25` |
| `/` | `%2F` khi cần encode trong component |

Ví dụ giá trị tìm kiếm là `C++ & web security?`. Nếu tự ghép chuỗi không encode, các ký tự `+`, `&` và `?` có thể bị hiểu sai theo cú pháp URL.

Không nên tự viết hàm mã hóa bằng cách thay vài ký tự. Cách an toàn hơn là để API URL chuẩn xử lý component:

~~~js
const url = new URL("https://shop.example.test/search");
url.searchParams.set("q", "C++ & web security?");

console.log(url.href);
// https://shop.example.test/search?q=C%2B%2B+%26+web+security%3F
~~~

Trong ví dụ trên, `URLSearchParams` dùng quy tắc form URL encoding: dấu cách được biểu diễn bằng `+`, dấu cộng dữ liệu được mã hóa thành `%2B`.

### 3.1. Dấu cộng có thể có hai ý nghĩa

Đây là nguồn lỗi phổ biến:

- Trong `application/x-www-form-urlencoded`, dấu `+` biểu diễn dấu cách khi parse.
- Nếu muốn truyền ký tự cộng thật, nó phải được encode thành `%2B`.
- Trong một số ngữ cảnh URL khác, dấu `+` có thể là ký tự literal; không được áp dụng quy tắc form encoding một cách tùy tiện cho mọi phần URL.

Ví dụ:

~~~js
const params = new URLSearchParams("q=C++");
console.log(params.get("q")); // "C  "
~~~

Hai dấu cộng được parse thành hai dấu cách theo quy tắc `URLSearchParams`. Nếu muốn giá trị `C++`:

~~~js
const params = new URLSearchParams();
params.set("q", "C++");
console.log(params.toString()); // "q=C%2B%2B"
~~~

### 3.2. Unicode và percent-encoding

Giá trị tiếng Việt hoặc ký tự ngoài ASCII được encode qua byte UTF-8 rồi biểu diễn bằng percent-encoding:

~~~js
const params = new URLSearchParams();
params.set("q", "bảo mật trình duyệt");

console.log(params.toString());
// q=b%E1%BA%A3o+m%E1%BA%ADt+tr%C3%ACnh+duy%E1%BB%87t
~~~

Khi parse bằng `URLSearchParams`, dữ liệu sẽ được giải mã về chuỗi Unicode:

~~~js
const parsed = new URLSearchParams(
  "q=b%E1%BA%A3o+m%E1%BA%ADt"
);
console.log(parsed.get("q")); // "bảo mật"
~~~

Đừng decode nhiều lần chỉ vì thấy dữ liệu còn `%xx`. Nếu một giá trị hợp lệ có chứa chuỗi literal `%2F`, decode lặp có thể biến nó thành dấu `/` và làm thay đổi ý nghĩa.

### 3.3. Encode component, không encode toàn bộ URL

`encodeURIComponent` phù hợp để encode một giá trị riêng lẻ khi cần xây URL thủ công:

~~~js
const query = "C++ & web security?";
const url = "/search?q=" + encodeURIComponent(query);

console.log(url);
// /search?q=C%2B%2B%20%26%20web%20security%3F
~~~

Nhưng với query gồm nhiều tham số, `URLSearchParams` dễ đọc và ít lỗi hơn:

~~~js
const url = new URL("/search", location.origin);
url.searchParams.set("q", query);
url.searchParams.set("page", "1");
~~~

Không dùng `encodeURIComponent` trên **toàn bộ URL** sau khi đã ghép scheme, host, path và dấu phân cách. Làm vậy sẽ mã hóa cả `:`, `/`, `?`, `&` và khiến URL không còn giữ cấu trúc mong muốn.

## 4. Đọc và tạo query bằng Web API chuẩn

### 4.1. `URL` và `URLSearchParams`

~~~js
const url = new URL(
  "https://shop.example.test/products?category=books&page=2"
);

console.log(url.origin);   // "https://shop.example.test"
console.log(url.pathname); // "/products"
console.log(url.search);   // "?category=books&page=2"

console.log(url.searchParams.get("category")); // "books"
console.log(url.searchParams.get("page"));     // "2"
~~~

Dùng `URL` để parse và giữ các phần URL riêng biệt; dùng `URLSearchParams` để thao tác query.

Tạo URL mới:

~~~js
const endpoint = new URL(
  "/v1/products",
  "https://api.example.test"
);

endpoint.searchParams.set("category", "books");
endpoint.searchParams.set("page", "2");
endpoint.searchParams.set("sort", "price");

console.log(endpoint.href);
// https://api.example.test/v1/products?category=books&page=2&sort=price
~~~

Cách này tránh nhầm lẫn khi giá trị chứa dấu phân cách hoặc Unicode.

### 4.2. Các phương thức quan trọng

| API | Hành vi | Ví dụ |
| --- | --- | --- |
| `get(name)` | Lấy giá trị đầu tiên có tên đó, hoặc `null` nếu không có | `params.get("page")` |
| `getAll(name)` | Lấy tất cả giá trị cùng tên theo thứ tự | `params.getAll("tag")` |
| `has(name)` | Kiểm tra có key hay không | `params.has("sort")` |
| `set(name, value)` | Đặt giá trị; xóa các giá trị trùng tên còn lại | `params.set("page", "2")` |
| `append(name, value)` | Thêm một cặp mới, kể cả khi key đã tồn tại | `params.append("tag", "browser")` |
| `delete(name)` | Xóa mọi cặp có key đó | `params.delete("debug")` |
| `toString()` | Serialize query, không có dấu `?` ở đầu | `params.toString()` |
| `sort()` | Sắp xếp cặp theo tên key theo thứ tự UTF-16 | `params.sort()` |

Ví dụ:

~~~js
const params = new URLSearchParams();
params.append("tag", "security");
params.append("tag", "browser");

console.log(params.get("tag"));    // "security"
console.log(params.getAll("tag")); // ["security", "browser"]

params.set("tag", "web");
console.log(params.getAll("tag")); // ["web"]
~~~

`set` thay thế toàn bộ các cặp có cùng tên bằng một giá trị; `append` thêm một cặp mới. Chọn sai phương thức có thể làm mất dữ liệu hoặc vô tình tạo tham số lặp.

### 4.3. Đọc query hiện tại

~~~js
const params = new URLSearchParams(window.location.search);

const searchTerm = params.get("q") ?? "";
const pageText = params.get("page") ?? "1";
~~~

`location.search` có dấu `?` ở đầu nếu có query. `URLSearchParams` có thể nhận trực tiếp chuỗi đó.

Không nên parse bằng:

~~~js
// Không nên: dễ sai với encoding, dấu &, dấu =, Unicode và giá trị rỗng.
const pairs = location.search.slice(1).split("&");
~~~

Tự tách chuỗi thường bỏ qua percent-encoding, key lặp, dấu bằng nằm trong giá trị, dấu cộng và các trường hợp biên. Dùng API chuẩn và validate kết quả.

## 5. Các trạng thái query phải được phân biệt

Những URL dưới đây không nhất thiết có cùng ý nghĩa:

~~~text
/search
/search?q
/search?q=
/search?q=books
/search?q=books&q=security
/search?Q=books
~~~

| Dạng | Cách đọc phổ biến bằng `URLSearchParams` | Điểm cần lưu ý |
| --- | --- | --- |
| Không có key `q` | `get("q") === null` | Không được gửi tham số. |
| `?q` | `get("q") === ""` | Key có mặt, giá trị rỗng. |
| `?q=` | `get("q") === ""` | Giá trị rỗng được viết tường minh. |
| `?q=books` | `get("q") === "books"` | Một giá trị. |
| `?q=books&q=security` | `get("q") === "books"`; `getAll` trả cả hai | Parser backend có thể khác. |
| `?Q=books` | `get("q") === null` | Tên key phân biệt hoa/thường theo API. |

Nếu API cần đúng một giá trị cho `page` hoặc `sort`, đừng dùng `get` rồi bỏ qua giá trị lặp. Hãy xác định rõ chính sách: từ chối duplicate, nhận duy nhất một giá trị, hoặc định nghĩa mảng có chủ đích.

### 5.1. Query parameter lặp và HTTP Parameter Pollution

**HTTP Parameter Pollution (HPP)** xảy ra khi cùng một tên tham số xuất hiện nhiều lần nhưng các thành phần trong hệ thống hiểu khác nhau.

Ví dụ:

~~~text
/transfer?amount=10&amount=1000
~~~

Một reverse proxy có thể lấy giá trị đầu, framework lấy giá trị cuối, một lớp validation chỉ kiểm tra giá trị đầu nhưng code nghiệp vụ lại dùng giá trị cuối. Khi đó kẻ tấn công có thể tạo **parser differential**: các tầng cùng nhìn một URL nhưng không cùng hiểu một yêu cầu.

Các dạng khác:

~~~text
?role=user&role=admin
?redirect=/safe&redirect=https://outside.test
?filter[status]=active&filter[status]=all
~~~

Không có một cách xử lý duplicate universal. Tùy hợp đồng API, server có thể:

- Từ chối key đơn trị nếu xuất hiện nhiều lần.
- Khai báo rõ key đa trị và parse thành danh sách.
- Chuẩn hóa đúng một lần ở ranh giới đầu vào rồi chuyển cấu trúc đã validate xuống tầng sau.
- Bảo đảm validation, authorization và xử lý nghiệp vụ dùng **cùng một giá trị đã chuẩn hóa**.

Không dựa vào thứ tự tham số hoặc giả định framework luôn lấy first/last nếu chưa kiểm chứng phiên bản và cấu hình thực tế.

## 6. Validate query ở phía server

Query parameter là dữ liệu do client kiểm soát. Kể cả frontend tạo URL bằng form hoặc code của chính ứng dụng, người dùng có thể sửa request bằng address bar, DevTools, proxy hoặc HTTP client khác.

Một quy trình validation nên gồm:

1. Xác định danh sách key được phép cho endpoint.
2. Xác định key nào đơn trị, key nào đa trị; từ chối duplicate ngoài hợp đồng.
3. Kiểm tra kiểu dữ liệu, cú pháp, miền giá trị và giới hạn độ dài.
4. Chuẩn hóa một cách nhất quán; tránh decode nhiều lần hoặc thay đổi ý nghĩa giữa các tầng.
5. Kiểm tra quyền của user đối với tài nguyên được tham chiếu.
6. Dùng query parameter như **đầu vào**, không dùng nó làm bằng chứng quyền hoặc danh tính.
7. Áp dụng giới hạn tần suất, pagination và chi phí truy vấn để tránh lạm dụng tài nguyên.

### 6.1. Ví dụ validate phân trang

Không dùng trực tiếp giá trị query làm số hoặc đưa thẳng vào database:

~~~js
const params = new URLSearchParams(location.search);
const rawPage = params.get("page");

function parsePage(value) {
  if (value === null) return 1;
  if (!/^[1-9][0-9]{0,3}$/.test(value)) return null;

  const page = Number(value);
  if (!Number.isSafeInteger(page) || page > 1000) return null;
  return page;
}

const page = parsePage(rawPage);

if (page === null) {
  throw new Error("Tham số page không hợp lệ");
}
~~~

Ví dụ này đặt giới hạn trang tối đa để tránh request truy xuất quá nhiều dữ liệu. API thực tế cần xác định giá trị mặc định, phản hồi lỗi nhất quán và giới hạn kích thước page size riêng.

### 6.2. Allowlist cho sort/filter

~~~js
const allowedSorts = new Set([
  "name",
  "price",
  "createdAt"
]);

const requestedSort = params.get("sort") ?? "createdAt";
const sort = allowedSorts.has(requestedSort)
  ? requestedSort
  : "createdAt";
~~~

Nếu query được dùng để chọn tên cột hoặc biểu thức SQL, **không** đưa chuỗi do người dùng gửi trực tiếp vào câu SQL. Parameterized query thường bind được **giá trị**, nhưng tên cột/order direction thường phải được map từ allowlist sang identifier cố định do server kiểm soát.

### 6.3. Validation không thay thế authorization

Ví dụ:

~~~text
GET /api/invoices?id=INV-1002
~~~

Kiểm tra `id` đúng định dạng chỉ chứng minh chuỗi có hình thức hợp lệ. Backend còn phải xác minh user hiện tại có quyền đọc hóa đơn `INV-1002` hay không. Nếu API chỉ kiểm tra ID mà không kiểm tra ownership, có thể xảy ra **Insecure Direct Object Reference (IDOR)** hoặc broken access control.

## 7. Query parameter và XSS

Query có thể chứa dữ liệu phản chiếu lên trang. Nếu ứng dụng chèn trực tiếp giá trị vào HTML mà không encode/sanitize theo ngữ cảnh, có thể phát sinh **reflected XSS** hoặc DOM XSS.

Ví dụ đầu vào:

~~~text
/search?q=browser
~~~

Code dễ lỗi:

~~~js
const q = new URLSearchParams(location.search).get("q") ?? "";
document.querySelector("#result").innerHTML = "Bạn tìm: " + q;
~~~

`URLSearchParams` giải mã query, nhưng **không sanitize HTML**. Giá trị nhận được vẫn là input không tin cậy.

Nếu chỉ hiển thị văn bản:

~~~js
const q = new URLSearchParams(location.search).get("q") ?? "";
document.querySelector("#result").textContent = "Bạn tìm: " + q;
~~~

Các nguyên tắc:

- Dùng `textContent` khi muốn hiển thị chữ.
- Nếu render HTML, encode đúng context hoặc dùng HTML sanitizer đáng tin cậy.
- Tránh `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `eval` và tạo script từ chuỗi đầu vào.
- CSP `script-src` giúp giới hạn nguồn thực thi; không thay thế sửa sink.
- Trusted Types có thể kiểm soát một số DOM injection sinks trên trình duyệt hỗ trợ; policy phải sanitize thật, không chỉ gắn nhãn chuỗi.

Ví dụ CSP minh họa:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{RANDOM_PER_RESPONSE}'; object-src 'none'; base-uri 'none'
~~~

Nonce phải được tạo an toàn cho từng response HTML và chỉ cấp cho script hợp lệ. Cần kiểm tra chính sách với tài nguyên thực tế.

## 8. Query parameter và SQL injection

Query thường mang dữ liệu tìm kiếm, lọc và sắp xếp. Nếu server ghép chuỗi query trực tiếp vào câu SQL, dữ liệu có thể thay đổi cấu trúc câu lệnh.

**Mẫu nguy hiểm:**

~~~js
// Minh họa anti-pattern: ghép trực tiếp dữ liệu client vào SQL.
const sql =
  "SELECT * FROM products WHERE category = '" +
  request.query.category +
  "'";
~~~

Cách tiếp cận an toàn là **parameterized query**:

~~~js
// API giả định theo phong cách prepared statement.
const rows = await db.query(
  "SELECT * FROM products WHERE category = ?",
  [category]
);
~~~

Placeholder và cú pháp cụ thể phụ thuộc database driver. Với tên cột hoặc chiều sắp xếp, dùng map allowlist:

~~~js
const sortColumns = {
  name: "product_name",
  price: "price",
  createdAt: "created_at"
};

const column = sortColumns[requestedSort] ?? "created_at";
const sql = "SELECT * FROM products ORDER BY " + column;
~~~

Giá trị được bind qua parameter; identifier chỉ lấy từ tập hằng do server kiểm soát. Không tin rằng URL encoding có thể ngăn SQL injection: encoding chỉ biểu diễn dữ liệu trong URL, **không thay thế parameterized query**.

## 9. Query parameter và open redirect

Ứng dụng đôi khi nhận URL đích trong query:

~~~text
/login?next=/account
~~~

Đây có thể là chức năng hợp lệ sau khi đăng nhập. Nhưng nếu server hoặc frontend chấp nhận tùy ý:

~~~text
/login?next=https://outside.test/fake-login
~~~

kẻ tấn công có thể gửi liên kết dùng domain tin cậy để chuyển người dùng sang trang giả mạo. Đây là **open redirect**.

Không kiểm tra URL đích bằng substring:

~~~js
// Không an toàn: host độc hại có thể chứa chuỗi này ở một phần khác.
if (next.includes("shop.example.test")) {
  location.assign(next);
}
~~~

Thiết kế an toàn hơn nếu chỉ cần điều hướng nội bộ: dùng route key hoặc allowlist path:

~~~js
const destinations = new Map([
  ["home", "/"],
  ["account", "/account"],
  ["orders", "/orders"]
]);

const key = new URLSearchParams(location.search).get("next");
const target = destinations.get(key) ?? "/";

location.assign(target);
~~~

Nếu yêu cầu hỗ trợ URL tuyệt đối, parse bằng `new URL(value, base)`, kiểm tra scheme, host, port/origin chính xác theo allowlist, loại bỏ các scheme không được phép và xử lý đường dẫn tương đối rõ ràng. Redirect nhạy cảm cần thiết kế luồng xác nhận phù hợp; không chỉ dựa vào kiểm tra phía client.

## 10. Query parameter và SSRF

Một API có thể nhận URL để tải ảnh, import feed hoặc tạo preview:

~~~text
GET /preview?url=https%3A%2F%2Fcdn.example.test%2Fimage.png
~~~

Nếu server lấy tham số `url` rồi tự kết nối tới địa chỉ đó, chức năng có thể tạo **Server-Side Request Forgery (SSRF)**. Kẻ tấn công có thể tìm cách khiến backend truy cập dịch vụ nội bộ, loopback, metadata endpoint hoặc mạng không được phép.

Query parameter được percent-encode không làm URL đích đáng tin. Phòng vệ cần ở server:

- Ưu tiên nhận **ID/tên tài nguyên** rồi ánh xạ sang URL cố định, thay vì nhận URL tùy ý.
- Nếu nghiệp vụ cần URL, chỉ cho phép scheme phù hợp (thường `https`), host/port nằm trong allowlist và kiểm tra sau khi parse.
- Kiểm tra DNS và địa chỉ IP đã resolve; chặn loopback, private, link-local, địa chỉ đặc biệt và các dải không được phép theo chính sách.
- Chống DNS rebinding và redirect chain: kiểm tra lại từng đích sau redirect, giới hạn số redirect.
- Áp dụng egress firewall, timeout, giới hạn dung lượng và giao thức; không gửi cookie hoặc credentials nội bộ tới đích.
- Không chỉ dựa vào validation frontend hoặc regex trên URL thô.

Nếu URL được backend fetch, cần xem đây là một **quyền mạng của server** chứ không chỉ là tham số tìm kiếm.

## 11. Query parameter và cache poisoning / cache confusion

Cache có thể dùng URL (bao gồm query hoặc một phần query) làm cache key. Nếu cache và origin server hiểu query khác nhau, hoặc cache bỏ qua tham số có ảnh hưởng nội dung, có thể xảy ra **cache poisoning** hay **cache confusion**.

Ví dụ mô hình:

- Backend dùng `?role=...` để quyết định nội dung.
- CDN cấu hình bỏ qua key `role` khi tạo cache key.
- Một response được tạo theo giá trị của một request có thể bị phục vụ cho request khác nếu các điều kiện cache phù hợp.

Không phải mọi tham số lạ đều tạo cache poisoning. Cần hiểu chính xác cache key, quy tắc normalize, header `Vary`, trạng thái cacheability và logic backend.

Biện pháp:

1. Xác định rõ query key nào ảnh hưởng representation.
2. Đảm bảo cache key bao gồm mọi tham số có ảnh hưởng nội dung hoặc không cache response nhạy cảm.
3. Không dùng query do người dùng kiểm soát để thay đổi quyền hoặc nội dung riêng tư mà không phân tách cache phù hợp.
4. Cấu hình cache theo endpoint; dùng `Cache-Control: private` hoặc `no-store` cho dữ liệu nhạy cảm khi phù hợp.
5. Kiểm thử qua đúng CDN/proxy đang triển khai, không chỉ gọi trực tiếp origin server.

## 12. Query parameter và chữ ký URL

Một số hệ thống dùng **signed URL** để cấp quyền truy cập tạm thời vào tài nguyên:

~~~text
/download/report.pdf?expires=...&signature=...
~~~

Chữ ký có thể phụ thuộc path, query, expiry, HTTP method, host hoặc các thành phần khác theo giao thức riêng. Nếu bên ký và bên xác minh chuẩn hóa khác nhau, có thể phát sinh lỗi xác thực hoặc bypass.

Các điểm cần thống nhất:

- Quy tắc encode/decode, Unicode normalization và thứ tự tham số.
- Xử lý tham số trùng tên: từ chối hay ký toàn bộ danh sách theo thứ tự.
- Tham số nào nằm trong canonical request và tham số nào bị loại.
- Quy tắc percent-encoding chữ hoa/thường, dấu cộng, dấu cách và ký tự reserved.
- Hạn dùng, audience/resource, method, scope và chống replay nếu cần.

Không tự ý gọi `URLSearchParams.sort()` trước khi xác minh chữ ký nếu thuật toán ký yêu cầu một dạng canonicalization khác. Tương tự, không decode rồi encode lại query đã ký theo quy tắc khác với phía phát hành.

**Nguyên tắc:** Cả bên tạo chữ ký và bên kiểm tra phải dùng cùng một đặc tả canonicalization đã được kiểm thử. Không tự thiết kế thuật toán chữ ký URL từ việc nối chuỗi rồi hash; dùng thư viện/giao thức đã được xem xét bảo mật.

## 13. Query parameter và dữ liệu nhạy cảm

Query thường bị lưu ở nhiều nơi hơn người phát triển dự kiến:

- Thanh địa chỉ và browser history.
- Access log của web server, reverse proxy, CDN, WAF và APM.
- Công cụ analytics, error reporting hoặc session replay nếu thu thập URL.
- Liên kết được copy, gửi qua chat/email hoặc lưu bookmark.
- Cache key và hệ thống giám sát.
- `Referer` trong một số điều kiện điều hướng/request, tùy `Referrer-Policy` và quan hệ origin.

Do đó, **không đặt mật khẩu, access token, session identifier, API key, dữ liệu thanh toán hoặc thông tin cá nhân nhạy cảm trong query** nếu có phương án phù hợp hơn.

Dùng HTTPS để bảo vệ dữ liệu trên đường truyền nhưng HTTPS **không ngăn URL xuất hiện trong log ở hai đầu, browser history hoặc hệ thống analytics**.

Ví dụ header giảm thông tin referrer:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

Chính sách này là mặc định phổ biến trên các trình duyệt hiện đại, nhưng ứng dụng có thể chọn chính sách khác. Khi chuyển cross-origin, thường chỉ gửi origin thay vì full path/query; cùng-origin có thể gửi URL đầy đủ hơn. Nếu URL có dữ liệu nhạy cảm, cách tốt nhất vẫn là **không đưa dữ liệu đó vào URL**.

### 13.1. Vì sao fragment và query có rủi ro khác nhau?

| Thuộc tính | Query | Fragment |
| --- | --- | --- |
| Bắt đầu bằng | `?` | `#` |
| Có trong request-target HTTP thông thường? | **Có** | **Không** |
| Server nhận trực tiếp trong navigation request? | Thường có | Không |
| JavaScript trên trang đọc được? | Có | Có |
| Có thể vào browser history/URL được chia sẻ? | Có | Có |
| Có thể bị ghi vào server/proxy access log qua URL? | Có | Không trực tiếp qua request-target |
| Có thể bị code client gửi tiếp sang server? | Có | Có |

Query thường được server và proxy tiếp nhận trực tiếp nên cần quan tâm log, cache, analytics và server-side validation. Fragment thường nằm phía client nên cần chú ý DOM XSS, hash routing và script có quyền đọc URL. **Cả hai đều không phải nơi an toàn để cất bí mật.**

## 14. Giới hạn kích thước, hiệu năng và từ chối dịch vụ

Không có một giới hạn độ dài URL duy nhất áp dụng cho mọi browser, proxy và server. Request line, header, CDN, framework và application server có các giới hạn cấu hình riêng. Query quá dài có thể bị từ chối, bị cắt hoặc làm tăng chi phí parse/log/cache.

Các biện pháp:

- Đặt giới hạn độ dài URL và từng giá trị query ở edge và backend.
- Giới hạn số lượng tham số, số giá trị lặp và độ sâu cấu trúc nếu framework hỗ trợ nested query.
- Giới hạn page size, số filter và độ phức tạp của biểu thức tìm kiếm.
- Dùng POST/body cho payload lớn hoặc dữ liệu có cấu trúc khi hợp đồng API phù hợp; body vẫn phải validate và bảo vệ.
- Giới hạn chi phí truy vấn database và áp dụng rate limit.
- Trả lỗi rõ ràng khi query vượt giới hạn, không âm thầm diễn giải theo cách khác nhau ở từng tầng.

Không coi chuyển dữ liệu từ query sang body là giải pháp bảo mật tự động: dữ liệu trong body cũng là input không tin cậy và vẫn có thể được log nếu hệ thống cấu hình như vậy.

## 15. Ví dụ thiết kế endpoint tìm kiếm an toàn

Giả sử API hỗ trợ:

~~~text
GET /v1/products?q=keyboard&category=computer&page=2&sort=price
~~~

Một hợp đồng hợp lý có thể định nghĩa:

| Key | Kiểu | Quy tắc |
| --- | --- | --- |
| `q` | String tùy chọn | Tối đa 100 ký tự; không dùng làm HTML; chuẩn hóa theo quy tắc tìm kiếm. |
| `category` | Enum tùy chọn | Chỉ nhận các category server hỗ trợ. |
| `page` | Integer | Mặc định 1; từ 1 đến giới hạn đã định. |
| `sort` | Enum | `name`, `price` hoặc `createdAt`. |
| `tag` | Multi-value | Cho phép lặp có chủ đích; giới hạn số tag và validate từng giá trị. |

Ví dụ kiểm tra ở frontend để cải thiện UX:

~~~js
const url = new URL("/v1/products", "https://api.example.test");

url.searchParams.set("q", "mechanical keyboard");
url.searchParams.set("category", "computer");
url.searchParams.set("page", "2");
url.searchParams.set("sort", "price");
url.searchParams.append("tag", "wireless");
url.searchParams.append("tag", "compact");

console.log(url.href);
~~~

Nhưng frontend validation chỉ cải thiện trải nghiệm. Backend phải parse request, từ chối key/giá trị sai, áp dụng query parameterized, kiểm tra quyền nếu dữ liệu cá nhân, giới hạn page size và đảm bảo response cache đúng.

### 15.1. Pseudocode backend minh họa

~~~js
async function listProducts(request, currentUser) {
  const params = request.query;

  // Hợp đồng đơn trị: từ chối nếu parser cung cấp nhiều giá trị.
  const pageValues = getAllQueryValues(request, "page");
  if (pageValues.length > 1) {
    throw badRequest("page chỉ được xuất hiện một lần");
  }

  const page = parseBoundedInteger(pageValues[0] ?? "1", {
    min: 1,
    max: 1000
  });

  const sortInput = getSingleQueryValue(request, "sort", "createdAt");
  const sortColumn = SORT_ALLOWLIST[sortInput];
  if (!sortColumn) throw badRequest("sort không hợp lệ");

  const category = validateCategory(
    getSingleQueryValue(request, "category", "")
  );

  // Query values được bind; identifier được map từ allowlist.
  return database.query(
    "SELECT id, name, price FROM products WHERE category = ? ORDER BY " +
      sortColumn +
      " LIMIT ? OFFSET ?",
    [category, 20, (page - 1) * 20]
  );
}
~~~

Đây là pseudocode minh họa, các hàm parse và driver cần được triển khai theo framework/database cụ thể. Điểm quan trọng là **không dùng raw query string làm logic quyền**, và không ghép giá trị client vào SQL.

## 16. Thực hành A — Quan sát query trong Network

Dùng trang local/staging bạn kiểm soát. Mở DevTools → **Network**, bật Preserve log nếu cần và truy cập:

~~~text
http://localhost:3000/search?q=browser&page=2#results
~~~

Quan sát request document:

~~~http
GET /search?q=browser&page=2 HTTP/1.1
Host: localhost:3000
~~~

Ghi lại:

1. Query xuất hiện trong request URL.
2. Fragment `#results` không nằm trong request-target.
3. Nếu thay `q` hoặc `page`, request URL và cache key có thể thay đổi.
4. Nếu chỉ đổi fragment trên cùng tài liệu, browser thường không gửi lại request document.

**Kết luận:** Query và fragment có vai trò khác nhau trong navigation và request.

## 17. Thực hành B — Percent-encoding và dấu cộng

Mở Console:

~~~js
const params = new URLSearchParams();
params.set("q", "C++ & bảo mật?");
params.set("note", "a b+c");

console.log(params.toString());

const parsed = new URLSearchParams(params.toString());
console.log(parsed.get("q"));
console.log(parsed.get("note"));
~~~

Đối chiếu với:

~~~js
new URLSearchParams("q=C++").get("q");   // "C  "
new URLSearchParams("q=C%2B%2B").get("q"); // "C++"
~~~

Thử nhập các giá trị có `&`, `=`, `#`, dấu cách, dấu `+` và chữ Việt. Kiểm tra serialize/parse trả lại đúng chuỗi gốc. Không tự decode thêm nếu API đã parse.

## 18. Thực hành C — Duplicate parameter và parser differential

Tạo request thử nghiệm:

~~~text
http://localhost:3000/demo?role=user&role=admin
~~~

Trong Console:

~~~js
const params = new URLSearchParams(location.search);

console.log(params.get("role"));
console.log(params.getAll("role"));
~~~

Sau đó gửi cùng URL tới một endpoint local có log kết quả parse theo framework đang dùng. So sánh:

- Framework có trả string hay array?
- Nó lấy giá trị đầu, cuối hay tất cả?
- Middleware validation và handler nghiệp vụ có nhận cùng cách parse không?
- Reverse proxy hoặc cache có normalize/loại bỏ duplicate không?

Không thử trên hệ thống không được phép. **Kết luận:** API phải định nghĩa duplicate key một cách rõ ràng và mọi tầng phải dùng cùng một cách diễn giải.

## 19. Thực hành D — DOM XSS source/sink từ query

Tạo một trang test có:

~~~html
<div id="unsafe"></div>
<div id="safe"></div>
~~~

Mở trang với query chứa markup vô hại đã encode:

~~~text
http://localhost:3000/demo?q=%3Cb%3Ehello%3C%2Fb%3E
~~~

Trong Console:

~~~js
const q = new URLSearchParams(location.search).get("q") ?? "";

document.querySelector("#unsafe").innerHTML = q;
document.querySelector("#safe").textContent = q;
~~~

Quan sát tab Elements:

- Vùng `unsafe` tạo node `<b>`.
- Vùng `safe` giữ chuỗi như text, không tạo element từ input.

Đây là phép thử minh họa ranh giới **data → HTML parser**, không cần chạy payload script. Trong code production, không đưa input không tin cậy vào `innerHTML`.

## 20. Thực hành E — Open redirect và allowlist

Tạo một trang demo có query `next`. Đầu tiên chỉ hiển thị giá trị bằng `textContent`:

~~~js
const next = new URLSearchParams(location.search).get("next") ?? "";
document.querySelector("#next-value").textContent = next;
~~~

Thử các giá trị:

~~~text
?next=account
?next=orders
?next=https%3A%2F%2Foutside.test
?next=%2F%2Foutside.test
~~~

Sau đó triển khai route-key allowlist:

~~~js
const allowed = {
  account: "/account",
  orders: "/orders"
};

const key = new URLSearchParams(location.search).get("next");
const target = allowed[key] ?? "/";

console.log(target);
~~~

Không điều hướng tới URL tùy ý trong bài thử. Ghi nhận rằng route key hợp lệ được ánh xạ thành path cố định; các giá trị khác trở về trang mặc định.

## 21. Checklist review query parameter

- [ ] Dùng `URL` và `URLSearchParams` thay vì tự tách chuỗi.
- [ ] Xác định schema: key cho phép, kiểu, bắt buộc/tùy chọn, giá trị mặc định và độ dài tối đa.
- [ ] Định nghĩa chính sách duplicate key cho từng endpoint; kiểm tra cách parser ở proxy, middleware và handler.
- [ ] Phân biệt key vắng mặt, key rỗng, key lặp và tên key khác chữ hoa/thường.
- [ ] Xử lý percent-encoding, UTF-8 và dấu `+` nhất quán; tránh double-decoding.
- [ ] Validate ở server; frontend validation chỉ hỗ trợ UX.
- [ ] Dùng parameterized query cho giá trị SQL và allowlist cho identifier/sort.
- [ ] Không chèn query vào HTML bằng sink nguy hiểm; dùng text sink, encode/sanitize đúng ngữ cảnh, CSP và Trusted Types khi phù hợp.
- [ ] Với `redirect` hoặc `next`, dùng route allowlist hoặc kiểm tra URL đích chính xác.
- [ ] Với query chứa URL để server fetch, đánh giá SSRF và giới hạn egress/redirect/DNS.
- [ ] Kiểm tra cache key có bao gồm mọi tham số ảnh hưởng response; không cache dữ liệu nhạy cảm sai phạm vi.
- [ ] Không đưa bí mật vào query; rà soát history, logs, analytics, referrer và URL được chia sẻ.
- [ ] Giới hạn tổng độ dài URL, số key, số giá trị lặp, page size và chi phí truy vấn.
- [ ] Với signed URL, thống nhất canonicalization và xử lý duplicate/encoding giữa bên ký và xác minh.
- [ ] Kiểm tra authorization/ownership độc lập với giá trị query.

## 22. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Query parameter không được gửi tới server.” | **Sai** | Query thường có trong HTTP request-target. |
| “Query và fragment giống nhau.” | **Sai** | Query thường gửi tới server; fragment không nằm trong request-target thông thường. |
| “Percent-encoding ngăn XSS hoặc SQL injection.” | **Sai** | Encoding biểu diễn dữ liệu; không thay validation, output encoding hay parameterized query. |
| “`URLSearchParams.get` trả tất cả giá trị.” | **Sai** | Nó trả giá trị đầu tiên; dùng `getAll` để lấy danh sách. |
| “Key lặp luôn lấy giá trị cuối.” | **Sai** | Hành vi phụ thuộc parser/framework; phải kiểm chứng. |
| “Dấu `+` luôn là dấu cộng.” | **Sai** | Trong form URL encoding, `+` thường decode thành dấu cách. |
| “Đã validate ở frontend thì backend có thể tin.” | **Sai** | Client có thể bị sửa hoặc bỏ qua hoàn toàn. |
| “Query ID hợp lệ nghĩa là user được quyền truy cập.” | **Sai** | Cần authorization và kiểm tra ownership. |
| “Dùng query để redirect là vô hại.” | **Sai** | Có thể tạo open redirect và phishing. |
| “HTTPS khiến query không xuất hiện trong log.” | **Sai** | HTTPS bảo vệ trên đường truyền; endpoint/proxy vẫn có thể log URL. |
| “Đưa URL đích vào query rồi encode là chống SSRF.” | **Sai** | Backend vẫn cần allowlist, kiểm tra IP/DNS, redirect và egress. |
| “Sắp xếp query trước khi ký luôn đúng.” | **Sai** | Canonicalization phải theo đúng đặc tả chữ ký. |

## 23. Tổng kết

Query parameter là một phần của URL thường được dùng để chuyển dữ liệu từ client tới server. Vì query thường nằm trong HTTP request-target, nó có thể đi qua nhiều tầng: browser, proxy, CDN, web server, framework, application và database. Mỗi tầng có thể parse, normalize, cache hoặc log theo cách khác nhau.

Hãy giữ ba nguyên tắc:

1. **Dùng parser và encoder chuẩn:** `URL` và `URLSearchParams` xử lý cấu trúc, percent-encoding và duplicate key rõ ràng hơn việc tự ghép chuỗi. Nhưng parse thành công không đồng nghĩa dữ liệu hợp lệ.
2. **Validate và authorize ở server:** xác định schema, giới hạn, duplicate policy, parameterized query, allowlist redirect và SSRF defense. Query không phải bằng chứng danh tính hoặc quyền truy cập.
3. **Đánh giá toàn bộ vòng đời dữ liệu:** query có thể vào DOM, SQL, URL fetch, cache, log, history và referrer. Dùng sink an toàn, không lưu bí mật trong URL và kiểm thử các tầng có cùng cách diễn giải.

Khi review một endpoint, hãy tự hỏi: **query này được ai tạo, được parse ở bao nhiêu tầng, mỗi key có kiểu và miền giá trị nào, nó ảnh hưởng tài nguyên hoặc quyền gì, và có thể bị ghi lại hoặc chuyển tiếp tới đâu?** Trả lời được những câu hỏi này giúp ứng dụng xử lý URL đúng và giảm đáng kể các lỗi bảo mật do encoding và input không tin cậy.
