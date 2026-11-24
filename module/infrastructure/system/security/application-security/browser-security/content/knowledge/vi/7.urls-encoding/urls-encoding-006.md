# URL confusion: khi parser và encoding tạo ra lỗi bảo mật

> **Chương:** URL và encoding  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

URL là đầu vào quan trọng của điều hướng, tải tài nguyên, gọi API, redirect, xác thực và kiểm tra origin. Một URL có thể được trình duyệt, reverse proxy, web server, framework và ứng dụng phân tích bằng những thư viện hoặc quy tắc khác nhau. Nếu các thành phần **không thống nhất URL nào đang được yêu cầu**, kẻ tấn công có thể lợi dụng sự khác biệt để vượt allowlist, tạo open redirect, truy cập sai route, gây lỗi phân quyền hoặc đưa dữ liệu vào sai ngữ cảnh.

Hiện tượng này thường được gọi là **URL confusion**: hệ thống nhìn cùng một chuỗi theo những cách khác nhau, hoặc kiểm tra một dạng URL rồi sử dụng một dạng đã bị giải mã/chuẩn hóa khác. Phòng vệ cần một quy trình nhất quán: **parse bằng parser chuẩn, chuẩn hóa một lần, kiểm tra thành phần có cấu trúc và dùng chính kết quả đã kiểm tra**.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân tích các thành phần URL: scheme, authority, userinfo, hostname, port, path, query và fragment.
2. Nhận diện các lỗi kiểm tra URL bằng substring, prefix, regex đơn giản hoặc tách chuỗi thủ công.
3. Giải thích percent-encoding, double decoding, dấu phân cách được mã hóa và khác biệt giữa URL encoding với HTML encoding.
4. Dự đoán tác động của URL normalization, dot segments, backslash, IDN và default port đến origin/route.
5. Phát hiện query parameter pollution và open redirect trong luồng đăng nhập/điều hướng.
6. Viết kiểm tra allowlist dựa trên URL parser, tránh tin cậy Origin: null và hạn chế scheme nguy hiểm.
7. Dùng Node.js URL API và DevTools để kiểm chứng cách parser diễn giải URL.

## 1. URL có cấu trúc, không phải một chuỗi tùy ý

### 1.1 Các thành phần của URL

Một URL dạng phổ biến:

~~~text
https://user:password@shop.example.com:8443/orders/item?id=42&view=full#details
|---|   |--------------| |-----------------| |--| |-------------------| |------|
scheme      userinfo          hostname       port        path/query     fragment
~~~

| Thành phần | Ví dụ | Ý nghĩa bảo mật |
|---|---|---|
| Scheme | **https** | Quyết định giao thức; không nên chấp nhận mọi scheme khi cần URL web |
| Userinfo | **user:password@** | Không phải hostname; dễ bị lợi dụng để đánh lừa người đọc URL |
| Hostname | **shop.example.com** | Tham gia xác định origin và đích kết nối |
| Port | **8443** | Tham gia xác định origin; port mặc định được chuẩn hóa |
| Path | **/orders/item** | Được router xử lý; cần nhất quán trong decode và chuẩn hóa |
| Query | **?id=42&view=full** | Tham số ứng dụng; có thể lặp key và có quy tắc decode riêng |
| Fragment | **#details** | Thông thường chỉ được xử lý phía client, không gửi trong HTTP request |

Một URL đầy đủ có thể có dạng:

~~~text
scheme://[userinfo@]host[:port]/path?query#fragment
~~~

Không phải mọi scheme đều có authority hoặc đủ các thành phần trên. URL tương đối như /orders, ../login hay //accounts.example.net cần được phân giải dựa trên **base URL**.

### 1.2 Origin được xác định từ URL như thế nào?

Với URL HTTP(S), origin thông thường là bộ ba:

\[
\text{origin}=(\text{scheme},\ \text{hostname},\ \text{port})
\]

| URL | Origin sau chuẩn hóa |
|---|---|
| https://shop.example.com/orders | https://shop.example.com |
| https://shop.example.com:443/orders | https://shop.example.com |
| https://shop.example.com:8443/orders | https://shop.example.com:8443 |
| http://shop.example.com/orders | http://shop.example.com |
| https://api.example.com/orders | https://api.example.com |

Port mặc định của HTTPS là 443 và của HTTP là 80; parser URL chuẩn hóa port mặc định tương ứng. Đường dẫn, query và fragment không thuộc origin.

**Hệ quả:** kiểm tra hostname đơn thuần là chưa đủ. HTTP và HTTPS trên cùng hostname là hai origin khác nhau; port không mặc định cũng tạo origin khác.

### 1.3 Authority có userinfo dễ đánh lừa mắt người

Xét:

~~~text
https://trusted.example@attacker.test/login
~~~

Hostname thực là **attacker.test**; **trusted.example** là userinfo. Vì vậy đoạn kiểm tra chuỗi như:

~~~js
raw.startsWith('https://trusted.example')
~~~

có thể bị đánh lừa. Người đọc nhìn thấy tên miền đáng tin trước dấu @, nhưng browser kết nối tới host sau dấu @.

Một biến thể khác:

~~~text
https://trusted.example.attacker.test/
~~~

Hostname là **trusted.example.attacker.test**, không phải **trusted.example**. Kiểm tra includes hoặc endsWith sai vị trí cũng có thể cấp quyền nhầm.

### 1.4 URL tương đối phụ thuộc base URL

Các chuỗi sau không mang cùng ý nghĩa:

| Đầu vào | Phân giải với base https://app.example/a/b |
|---|---|
| /login | https://app.example/login |
| login | https://app.example/a/login |
| ../login | https://app.example/login |
| //evil.example/x | https://evil.example/x |
| https://evil.example/x | Giữ nguyên URL tuyệt đối |
| ?next=/home | Giữ path hiện tại, thay query |
| #section | Giữ tài liệu hiện tại, thay fragment |

Không kiểm tra một URL tương đối mà không biết base URL thực tế. Giá trị bắt đầu bằng hai dấu slash là **scheme-relative URL**: scheme được lấy từ base, còn host được thay đổi.

## 2. Parser differential: cùng một chuỗi, nhiều cách hiểu

### 2.1 Browser và server có thể không dùng cùng parser

Trình duyệt hiện đại dùng mô hình URL theo WHATWG URL Standard. Server, proxy, framework và thư viện khác có thể dùng parser theo RFC, parser riêng hoặc logic tự viết. Các khác biệt thường xuất hiện ở:

- Backslash và slash trong URL có scheme đặc biệt như HTTP/HTTPS.
- Ký tự điều khiển, khoảng trắng đầu/cuối và cách percent-decode.
- Hostname Unicode/IDN và chuyển đổi punycode.
- Dot segment như dấu chấm và hai dấu chấm, kể cả dạng percent-encoded.
- Dấu phân cách path/query được mã hóa như %2F, %3F, %23.
- URL tương đối và base URL.
- Port mặc định, chữ hoa/thường, dấu chấm cuối hostname.
- Dữ liệu userinfo trước dấu @.

Một tầng có thể kiểm tra chuỗi thô, tầng khác parse URL rồi chuẩn hóa; một tầng decode %2F thành dấu slash trước khi định tuyến, tầng khác giữ nguyên. Nếu kiểm soát quyền ở một dạng và định tuyến ở dạng khác, chính sách có thể bị vượt qua.

### 2.2 Dùng parser của nền tảng thay vì tách chuỗi

Trong JavaScript, URL là API chuẩn để parse và resolve URL:

~~~js
const target = new URL(
  '/account',
  'https://app.example.com/shop/'
);

console.log(target.href);
// https://app.example.com/account

console.log(target.origin);
// https://app.example.com

console.log(target.hostname);
// app.example.com

console.log(target.pathname);
// /account
~~~

Các thuộc tính quan trọng:

- **protocol:** scheme có dấu hai chấm, ví dụ https:.
- **username, password:** userinfo đã parse.
- **hostname:** hostname đã chuẩn hóa theo URL parser.
- **port:** port không mặc định; thường là chuỗi rỗng nếu dùng port mặc định.
- **host:** hostname cộng port nếu có.
- **pathname:** path sau xử lý chuẩn hóa của parser.
- **search:** query bao gồm dấu hỏi.
- **hash:** fragment bao gồm dấu thăng.
- **origin:** origin serialize; với một số scheme không có tuple origin, kết quả là chuỗi null.

Không nên viết parser riêng bằng split, regex tự chế hoặc cắt chuỗi để xác định host/origin. Hãy parse URL một lần, kiểm tra các trường có cấu trúc, sau đó dùng chính đối tượng URL đã kiểm tra.

## 3. Percent-encoding và lỗi giải mã nhiều lần

### 3.1 Percent-encoding là gì?

Percent-encoding biểu diễn một byte bằng dấu phần trăm theo sau là hai chữ số hex.

| Ký tự | Mã thường gặp |
|---|---|
| Dấu cách | %20 |
| Slash | %2F |
| Dấu hỏi | %3F |
| Dấu thăng | %23 |
| @ | %40 |
| Phần trăm | %25 |
| Dấu chấm | %2E |

Ví dụ:

~~~text
https://app.example/search?q=web%20security
~~~

Trong query, %20 có thể được giải mã thành dấu cách khi ứng dụng đọc giá trị. Encoding cho phép dữ liệu chứa ký tự đặc biệt mà không làm thay đổi cấu trúc URL tại vị trí tương ứng.

**Percent-encoding không phải mã hóa bí mật.** Nó không bảo vệ dữ liệu nhạy cảm và không thay thế xác thực, kiểm tra đầu vào hay encoding theo ngữ cảnh HTML/JavaScript.

### 3.2 Encode đúng thành phần

Không có một hàm “encode URL” duy nhất phù hợp cho mọi ngữ cảnh. Phải biết dữ liệu được chèn vào **path segment**, **query value**, hay toàn bộ URL.

~~~js
const value = 'a/b?c=d & e';

// Encode một giá trị query.
const query = new URLSearchParams({ q: value });
console.log(query.toString());

// Encode một path segment.
const segment = encodeURIComponent(value);
console.log(segment);
~~~

- **encodeURIComponent()** phù hợp để encode một thành phần như query value hoặc path segment; nó encode các ký tự phân cách như slash, dấu hỏi, dấu & và dấu =.
- **encodeURI()** giữ lại nhiều ký tự có ý nghĩa cấu trúc của URL; không dùng nó để encode dữ liệu cần đặt trong một query value.
- **URLSearchParams** xử lý serialization query theo quy tắc application/x-www-form-urlencoded, trong đó dấu cách thường serialize thành dấu cộng.
- Khi tạo URL, ưu tiên URL và URLSearchParams thay vì ghép chuỗi thủ công.

Ví dụ sai:

~~~js
const url = '/search?q=' + userInput;
~~~

Nếu userInput chứa **&admin=true**, chuỗi query có thể bị tách thành tham số ngoài ý muốn. Cách tốt hơn:

~~~js
const url = new URL('/search', location.origin);
url.searchParams.set('q', userInput);
~~~

### 3.3 Double encoding và double decoding

Một ký tự phần trăm có thể được encode thành %25. Ví dụ:

~~~text
../admin       → %2E%2E%2Fadmin
%2E%2E%2Fadmin → %252E%252E%252Fadmin
~~~

Nếu một tầng decode một lần, %252E%252E%252Fadmin trở thành %2E%2E%2Fadmin. Nếu tầng tiếp theo decode lần thứ hai, nó trở thành ../admin.

Đây là nguồn của nhiều lỗi **double decoding**. Ví dụ, proxy kiểm tra path sau một lần decode nhưng ứng dụng decode thêm lần nữa trước khi truy cập file hoặc route; hai tầng không còn kiểm tra cùng một tài nguyên.

Quy tắc phòng vệ:

1. Xác định rõ tầng nào chịu trách nhiệm parse/decode.
2. Decode đúng một lần theo giao thức và framework đã chọn.
3. Không gọi decodeURIComponent lặp lại trên dữ liệu đã decode.
4. Dùng cùng biểu diễn canonical cho kiểm tra quyền và định tuyến.
5. Nếu đầu vào chứa encoding sai hoặc không hợp lệ, từ chối có kiểm soát thay vì cố sửa theo nhiều cách khác nhau.

### 3.4 Encoded slash, backslash và dot segment

Các dạng sau có thể gây parser differential:

~~~text
/a/b
/a%2Fb
/a%252Fb
/a/../admin
/a/%2e%2e/admin
/a%5Cb
/a%255Cb
~~~

Ý nghĩa chính xác phụ thuộc URL parser và tầng server:

- %2F là slash được percent-encode; một số router giữ nó trong một segment, tầng khác decode thành dấu slash.
- %5C là backslash; một số nền tảng hoặc backend Windows có thể coi backslash như dấu phân cách đường dẫn.
- %252F sau một lần decode thành %2F; decode thêm lần nữa mới thành slash.
- Dot segment có thể được chuẩn hóa khi parse URL; một số dạng percent-encoded của dot segment cũng được URL parser xử lý theo quy tắc của nó.

Không nên tự giả định server giữ nguyên path giống trình duyệt. Cần kiểm tra đường đi thực tế qua CDN, reverse proxy, web server, router và filesystem.

## 4. URL normalization: canonicalization và ranh giới bảo mật

### 4.1 Normalization làm thay đổi biểu diễn nhưng không nhất thiết đổi tài nguyên

Một số khác biệt được URL parser chuẩn hóa:

| Đầu vào | Biểu diễn sau parse thường gặp | Lưu ý |
|---|---|---|
| HTTPS://EXAMPLE.COM:443/a | https://example.com/a | Scheme/host chữ thường, port mặc định bỏ |
| https://example.com/a/../b | https://example.com/b | Dot segment được loại |
| https://example.com/%2e%2e/b | Có thể thành https://example.com/b | Dot segment encoded được xử lý theo quy tắc WHATWG |
| https://example.com/a%2Fb | Path vẫn có thể giữ %2F | Backend có thể decode khác |
| https://example.com./ | Host có dấu chấm cuối | DNS thường xem tương đương hostname có/không dấu chấm cuối, nhưng allowlist string có thể khác |
| https://example.com:443/ | https://example.com/ | Default port được chuẩn hóa |

Canonicalization là quá trình đưa đầu vào về biểu diễn thống nhất. Nó giúp giảm nhập nhằng, nhưng phải thống nhất với các tầng sử dụng URL sau đó.

### 4.2 Không kiểm tra quyền trên chuỗi khác với chuỗi được sử dụng

Mô hình nguy hiểm:

~~~text
raw input
   ↓
kiểm tra chuỗi bằng regex/prefix
   ↓
proxy decode và chuẩn hóa
   ↓
framework parse lại
   ↓
route/filesystem dùng giá trị khác
~~~

Mô hình tốt hơn:

~~~text
raw input
   ↓
parse bằng parser chuẩn
   ↓
chuẩn hóa/canonicalize theo một chính sách
   ↓
kiểm tra scheme + origin + path + query
   ↓
dùng chính đối tượng/giá trị đã kiểm tra
   ↓
router hoặc navigation
~~~

Nếu reverse proxy và ứng dụng buộc phải xử lý path theo cách khác nhau, cần định nghĩa hợp đồng encoding rõ ràng và kiểm thử xuyên suốt các tầng. Đặc biệt với đường dẫn tài nguyên, không được để tầng xác thực kiểm tra một path còn tầng truy cập filesystem sử dụng path đã decode/normalize khác.

### 4.3 Unicode, IDN và hostname giả mạo trực quan

Tên miền quốc tế hóa (IDN) cho phép hostname có ký tự ngoài ASCII. URL parser có thể chuyển hostname Unicode sang dạng ASCII tương thích DNS, thường được gọi là **punycode**.

Hai hostname có thể trông gần giống nhau trên màn hình nhưng chứa ký tự Unicode khác nhau (homograph attack). Ví dụ, một ký tự Cyrillic có thể giống ký tự Latin về hình dạng.

Phòng vệ:

- Parse hostname bằng URL parser chuẩn và dùng giá trị hostname đã canonicalize.
- Với allowlist bảo mật, so sánh chính xác hostname ASCII đã chuẩn hóa; không dựa vào hình thức hiển thị.
- Không dùng includes hoặc kiểm tra suffix thiếu dấu chấm ranh giới.
- Khi hiển thị URL cho người dùng, cân nhắc hiển thị punycode hoặc cảnh báo hostname có ký tự gây nhầm lẫn theo chính sách sản phẩm.
- Không tự áp dụng Unicode normalization tùy tiện cho hostname/path; dùng quy tắc IDNA và URL parser của nền tảng.

### 4.4 Backslash trong URL đặc biệt

Đối với các scheme đặc biệt như HTTP và HTTPS, WHATWG URL parser có thể xử lý backslash như dấu slash trong các vị trí nhất định. Vì thế một chuỗi có backslash có thể được parse thành host/path khác với cách một bộ lọc đơn giản dự đoán.

Ví dụ cần kiểm thử trong parser đang dùng:

~~~js
const base = 'https://app.example/';
const inputs = [
  '//evil.example/path',
  '\\\\evil.example/path',
  '/\\\\evil.example/path'
];

for (const input of inputs) {
  const url = new URL(input, base);
  console.log(input, '=>', url.href, url.origin);
}
~~~

Đừng dựa vào quy tắc “chỉ URL bắt đầu bằng slash là đường dẫn nội bộ” nếu chưa parse. Hãy kiểm tra url.origin sau khi resolve với base tin cậy.

## 5. Query parameter pollution và cách diễn giải tham số

### 5.1 Một key có thể xuất hiện nhiều lần

Ví dụ:

~~~text
https://app.example/search?role=user&role=admin
~~~

Các thư viện có thể xử lý tham số lặp theo những cách khác nhau:

- Lấy giá trị đầu tiên.
- Lấy giá trị cuối cùng.
- Trả về mảng nhiều giá trị.
- Ghép chuỗi.
- Từ chối tham số trùng.

Nếu middleware kiểm tra role=user nhưng phần nghiệp vụ lấy giá trị cuối role=admin, có thể xảy ra **HTTP Parameter Pollution (HPP)** hoặc sai lệch logic bảo mật.

Với URLSearchParams:

~~~js
const params = new URLSearchParams(
  'role=user&role=admin'
);

console.log(params.get('role'));    // Giá trị đầu tiên
console.log(params.getAll('role')); // Tất cả giá trị
~~~

### 5.2 Quy định rõ cardinality của từng tham số

Đối với tham số ảnh hưởng đến bảo mật như next, returnUrl, role, tenant, redirect_uri, state:

1. Xác định tham số được phép xuất hiện một lần hay nhiều lần.
2. Nếu chỉ cho phép một lần, từ chối khi getAll(name).length khác 1 hoặc khi parser backend phát hiện duplicate.
3. Kiểm tra kiểu, độ dài, định dạng và phạm vi giá trị.
4. Đảm bảo gateway, middleware và controller dùng cùng quy tắc lấy giá trị.
5. Không dùng tham số do client gửi để tự quyết định quyền truy cập; quyền phải lấy từ danh tính/phiên đã xác thực ở server.

Ví dụ helper phía client/server JavaScript:

~~~js
function getSingleParam(params, name) {
  const values = params.getAll(name);
  if (values.length !== 1) {
    throw new Error('Invalid parameter cardinality: ' + name);
  }
  return values[0];
}

const params = new URLSearchParams(location.search);
const returnTo = getSingleParam(params, 'returnTo');
~~~

Đây chỉ là bước kiểm tra cấu trúc; returnTo vẫn cần parse URL và kiểm tra đích trước khi điều hướng.

### 5.3 Dấu cộng trong query không phải lúc nào cũng là dấu cộng

Trong định dạng application/x-www-form-urlencoded, dấu cộng biểu diễn dấu cách. Để biểu diễn dấu cộng thực sự trong query value, nó thường được encode thành %2B.

Ví dụ:

~~~js
const params = new URLSearchParams('q=C%2B%2B+security');
console.log(params.get('q')); // "C++ security"
~~~

Nếu một tầng coi dấu cộng là dấu cộng còn tầng khác coi là dấu cách, kiểm tra chữ ký, canonicalization hoặc so khớp giá trị có thể lệch nhau. Cần thống nhất cách serialize/parse query trên toàn hệ thống.

## 6. URL confusion trong redirect và allowlist

### 6.1 Vì sao prefix check nguy hiểm?

Mã sai:

~~~js
function isTrusted(raw) {
  return raw.startsWith('https://trusted.example');
}
~~~

Các đầu vào có thể vượt qua kiểm tra nhưng không có origin mong muốn:

~~~text
https://trusted.example.attacker.test/
https://trusted.example@attacker.test/
https://trusted.example:443@attacker.test/
~~~

Vấn đề là so sánh chuỗi không hiểu cấu trúc URL. Tên miền, userinfo, port và scheme cần được parse thành trường riêng.

### 6.2 Kiểm tra origin bằng URL parser

Ví dụ allowlist URL tuyệt đối:

~~~js
const allowedOrigins = new Set([
  'https://trusted.example',
  'https://accounts.example'
]);

function parseAllowedHttpsUrl(raw, base) {
  const url = new URL(raw, base);

  if (url.protocol !== 'https:') {
    throw new Error('Only HTTPS URLs are allowed');
  }

  if (url.username !== '' || url.password !== '') {
    throw new Error('URL userinfo is not allowed');
  }

  if (!allowedOrigins.has(url.origin)) {
    throw new Error('Destination origin is not allowed');
  }

  return url;
}

const target = parseAllowedHttpsUrl(
  '/profile',
  'https://trusted.example'
);

console.log(target.href);
~~~

Điểm quan trọng:

- new URL(raw, base) xử lý cả URL tuyệt đối lẫn tương đối.
- protocol giới hạn scheme; không mặc định chấp nhận javascript:, data:, file:, blob: hoặc scheme khác khi mục tiêu là web HTTPS.
- origin bao gồm scheme, hostname và port đã chuẩn hóa.
- Userinfo bị từ chối để tránh URL gây nhầm lẫn cho người dùng hoặc hệ thống log.
- Dùng **chính đối tượng URL đã kiểm tra** cho hành động tiếp theo.

Nếu cần cho phép nhiều path trên cùng origin, kiểm tra pathname bằng quy tắc route rõ ràng sau khi parse. Đừng chuyển thành kiểm tra prefix hostname.

### 6.3 Chỉ cho phép đường dẫn nội bộ

Nếu nghiệp vụ chỉ cần redirect về một route nội bộ, hãy yêu cầu URL phân giải vẫn cùng origin với ứng dụng:

~~~js
function safeInternalDestination(raw) {
  const base = new URL('https://app.example.com/');
  const target = new URL(raw, base);

  if (target.origin !== base.origin) {
    throw new Error('Only same-origin destinations are allowed');
  }

  if (target.username || target.password) {
    throw new Error('Userinfo is not allowed');
  }

  return target.pathname + target.search + target.hash;
}

const returnPath = safeInternalDestination('/orders?view=recent');
~~~

Cách này từ chối các dạng //evil.example, URL tuyệt đối khác origin và các biến thể backslash sau khi parser xử lý. Với hệ thống có base path hoặc tenant path, cần bổ sung allowlist route cụ thể; cùng origin chưa có nghĩa mọi route đều an toàn.

### 6.4 Scheme nguy hiểm và URL trong HTML

Nếu ứng dụng nhận một URL để đặt vào thuộc tính href, chỉ kiểm tra origin là chưa đủ. Cần quyết định scheme được phép. Đặc biệt, javascript: có thể thực thi script trong một số ngữ cảnh điều hướng; data: có thể tạo tài liệu nhúng; file: có thể truy cập ngữ cảnh cục bộ theo quyền browser.

Ví dụ:

~~~js
function safeWebLink(raw) {
  const url = new URL(raw, location.origin);

  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('Unsupported URL scheme');
  }

  return url.href;
}

linkElement.href = safeWebLink(userSuppliedUrl);
~~~

Đoạn mã trên giới hạn scheme nhưng **không tự quyết định domain nào đáng tin**. Nếu chỉ cho phép một số website, thêm allowlist origin. Khi đưa giá trị vào HTML string hoặc attribute qua template, còn phải dùng cơ chế encode/sanitize theo đúng ngữ cảnh; URL validation không thay thế HTML escaping.

## 7. URL và các cơ chế bảo mật trình duyệt

### 7.1 CORS: so sánh origin đã parse, không so sánh chuỗi tùy tiện

CORS dùng origin serialize gồm scheme, hostname và port. Server không nên kiểm tra:

~~~js
if (origin.includes('trusted.example')) {
  // Sai: có thể khớp hostname giả hoặc origin không mong muốn.
}
~~~

Thay vào đó:

- Parse và chuẩn hóa Origin theo định dạng hợp lệ; so sánh chính xác với allowlist origin.
- Không phản chiếu tùy tiện giá trị Origin nhận được vào Access-Control-Allow-Origin.
- Không coi Origin: null là một ứng dụng tin cậy; nhiều ngữ cảnh opaque có thể serialize thành null.
- Nếu response có credentials, không dùng wildcard Access-Control-Allow-Origin: *; trả đúng một origin được phép và Access-Control-Allow-Credentials: true khi thật sự cần.
- Gửi Vary: Origin nếu response thay đổi theo request Origin và có thể qua cache.

CORS chỉ quyết định quyền đọc response ở browser; API vẫn cần authentication, authorization và CSRF protection.

### 7.2 CSP và thẻ base có thể ảnh hưởng cách resolve URL

Thẻ HTML base thay đổi base URL dùng để resolve các URL tương đối trong tài liệu:

~~~html
<base href="https://cdn.example.net/assets/">
<a href="login">Đăng nhập</a>
~~~

Link trên được resolve thành https://cdn.example.net/assets/login, không phải route tương đối của origin hiện tại. Nếu attacker có thể chèn hoặc thay đổi base element, nhiều link/resource tương đối có thể bị đổi đích.

Có thể giới hạn base bằng response header:

~~~http
Content-Security-Policy: base-uri 'self'; object-src 'none'; frame-ancestors 'none'
~~~

base-uri kiểm soát URL được phép dùng trong thẻ base. Nó không thay thế kiểm tra URL ở server và không thay thế output encoding. Với ứng dụng không cần base tùy chỉnh, cân nhắc base-uri 'none'.

Các chỉ thị CSP khác có vai trò riêng: form-action giới hạn đích gửi form; connect-src giới hạn fetch/XHR/WebSocket; frame-src giới hạn iframe mà trang tải; frame-ancestors giới hạn trang nào được nhúng tài liệu hiện tại.

### 7.3 URL trong CSRF và navigation

URL có thể kích hoạt hành động khi người dùng hoặc browser điều hướng tới nó. Nếu GET endpoint làm thay đổi trạng thái, một trang ngoài có thể dụ người dùng mở liên kết đó. Cookie SameSite=Lax vẫn có thể đi kèm top-level cross-site GET trong nhiều trường hợp.

- GET/HEAD phải an toàn theo ngữ nghĩa ứng dụng, không chuyển tiền, đổi email hoặc xóa dữ liệu.
- Thay đổi trạng thái cần method phù hợp, CSRF token hoặc cơ chế chống CSRF tương đương.
- Kiểm tra Origin/Referer và Fetch Metadata có thể bổ sung lớp phòng vệ.
- Không dựa vào việc CORS chặn JavaScript đọc response để kết luận request không thể tới server.

### 7.4 XSS: URL validation không phải output encoding

Một URL hợp lệ vẫn có thể trở thành nguy hiểm nếu được chèn vào sai ngữ cảnh. Ví dụ, query value chứa ký tự HTML/JavaScript không nên được nối thẳng vào HTML:

~~~js
// Không an toàn: tạo HTML từ dữ liệu không tin cậy.
container.innerHTML = '<a href="' + userInput + '">Open</a>';
~~~

Hướng an toàn hơn là tạo phần tử DOM và đặt thuộc tính sau khi validate scheme/origin theo nghiệp vụ:

~~~js
const anchor = document.createElement('a');
anchor.textContent = 'Open';
anchor.href = safeWebLink(userInput);
container.replaceChildren(anchor);
~~~

Nếu ứng dụng thực sự cần render HTML động, cần sanitizer đáng tin cậy và chính sách CSP/Trusted Types phù hợp. **URL parsing, HTML escaping, JavaScript string escaping và CSS escaping là những công việc khác nhau**; không dùng một hàm encode cho mọi context.

## 8. Checklist xử lý URL an toàn

Khi URL đến từ người dùng, query parameter, API hoặc cấu hình, áp dụng quy trình:

1. **Xác định loại URL:** absolute, relative, scheme-relative hay URL theo scheme riêng?
2. **Chọn base URL đáng tin:** không resolve relative URL dựa trên base do người dùng kiểm soát.
3. **Parse bằng chuẩn của nền tảng:** dùng WHATWG URL trong browser/Node.js hoặc parser phù hợp trong backend.
4. **Kiểm tra scheme:** chỉ cho phép các scheme thực sự cần; với link web thông thường, ưu tiên HTTPS.
5. **Kiểm tra origin/host chính xác:** gồm scheme, hostname và port; không dùng prefix/substring.
6. **Kiểm tra userinfo:** từ chối username/password trong URL nếu nghiệp vụ không cần.
7. **Chuẩn hóa nhất quán:** xử lý dot segment, percent-encoding, slash/backslash và Unicode theo một quy tắc xuyên suốt.
8. **Kiểm tra path/query:** route và cardinality của tham số phải rõ; không cho gateway và ứng dụng hiểu khác nhau.
9. **Dùng kết quả đã kiểm tra:** không parse/decode lại bằng một thư viện khác trước khi sử dụng.
10. **Encode theo đúng output context:** query value, path segment, HTML attribute, JavaScript string là các ngữ cảnh khác nhau.
11. **Kiểm soát redirect và base URL:** allowlist đích; hạn chế thẻ base bằng CSP khi phù hợp.
12. **Kiểm thử toàn tuyến:** browser → CDN/proxy → server → framework → router; log giá trị canonical an toàn, không log bí mật trong URL.

## 9. Thực hành: quan sát cách URL parser chuẩn hóa

Bài lab chỉ phân tích chuỗi cục bộ, **không gửi request mạng**. Dùng Node.js có sẵn.

### 9.1 Tạo file url-confusion-lab.mjs

~~~js
const base = 'https://app.example.com/a/b';

const inputs = [
  '/login',
  '../admin',
  '//evil.example/path',
  'https://trusted.example@attacker.test/login',
  'https://trusted.example.attacker.test/',
  'https://app.example.com:443/account',
  'https://app.example.com:8443/account',
  '/a/%2e%2e/admin',
  '/a%2Fadmin',
  '/a%252Fadmin',
  '\\\\evil.example/path',
  'https://例え.テスト/path'
];

for (const input of inputs) {
  try {
    const url = new URL(input, base);
    console.log({
      input,
      href: url.href,
      origin: url.origin,
      protocol: url.protocol,
      username: url.username,
      hostname: url.hostname,
      port: url.port,
      pathname: url.pathname,
      search: url.search
    });
  } catch (error) {
    console.log({ input, error: error.message });
  }
}
~~~

Chạy:

~~~bash
node url-confusion-lab.mjs
~~~

### 9.2 Những điều cần quan sát

| Đầu vào | Câu hỏi cần trả lời |
|---|---|
| //evil.example/path | Scheme lấy từ đâu? Host có đổi không? |
| https://trusted.example@attacker.test/login | Hostname là gì? trusted.example thuộc phần nào? |
| https://trusted.example.attacker.test/ | Vì sao prefix check có thể sai? |
| https://app.example.com:443/account | Vì sao port mặc định có thể biến mất? |
| https://app.example.com:8443/account | Origin khác ở thành phần nào? |
| /a/%2e%2e/admin | URL parser xử lý dot segment ra sao? |
| /a%2Fadmin | Path có giữ encoded slash không? Backend có thể xử lý khác không? |
| /a%252Fadmin | Cần bao nhiêu lần decode mới thành slash? |
| \\evil.example/path | Backslash được parser HTTP/HTTPS diễn giải thế nào? |
| Hostname Unicode | hostname canonicalize thành dạng nào? |

### 9.3 Kiểm tra query parameter lặp

Chạy đoạn sau trong Node.js:

~~~js
const params = new URLSearchParams(
  'role=user&role=admin&q=C%2B%2B+security'
);

console.log('first role:', params.get('role'));
console.log('all roles:', params.getAll('role'));
console.log('query:', params.get('q'));
~~~

Hãy giải thích vì sao một middleware dùng giá trị đầu tiên và controller dùng giá trị cuối cùng có thể tạo lỗi phân quyền hoặc logic nghiệp vụ.

### 9.4 Tự thử bộ lọc redirect

Dùng các input sau để kiểm tra helper safeInternalDestination() ở phần 6:

~~~text
/orders
../account
//attacker.example/path
https://attacker.example/path
https://app.example.com@attacker.example/
\\attacker.example/path
javascript:alert(1)
data:text/html,hello
~~~

Một helper đúng phải parse URL với base đáng tin và từ chối mọi origin khác origin ứng dụng, đồng thời không chấp nhận scheme không phù hợp. Hãy bổ sung kiểm tra route cụ thể nếu ứng dụng chỉ cho phép một tập đường dẫn.

## 10. Các lỗi thường gặp và cách khắc phục

| Lỗi | Tác động | Cách xử lý |
|---|---|---|
| Kiểm tra URL bằng startsWith/includes | Bỏ sót userinfo, suffix hostname giả, port và scheme | Parse rồi so sánh trường origin/hostname chính xác |
| Dùng URL tương đối nhưng không chỉ định base tin cậy | URL có thể resolve sang host khác | Dùng base lấy từ cấu hình đáng tin, parse và so sánh origin |
| Decode nhiều lần | Bypass path validation, route hoặc kiểm tra file | Decode đúng một lần; thống nhất parser và canonical path |
| Gateway và app decode slash khác nhau | Authorization kiểm tra route A nhưng router xử lý route B | Định nghĩa quy tắc encoding xuyên suốt, kiểm thử end-to-end |
| Chỉ kiểm tra hostname mà bỏ scheme/port | Cho phép HTTP hoặc port ngoài dự kiến | So sánh origin đầy đủ |
| Chấp nhận Origin: null như frontend tin cậy | Mở quyền cho nhiều opaque origin không mong muốn | Không allowlist null cho dữ liệu có credentials |
| Lấy một giá trị query nhưng tầng khác lấy giá trị khác | Parameter pollution, sai quyền/logic | Quy định duplicate key; dùng cùng parser/cardinality |
| Ghép query bằng chuỗi | &, =, + làm thay đổi cấu trúc | Dùng URLSearchParams |
| Tin Unicode hostname theo hình thức hiển thị | Homograph/phishing | Canonicalize hostname, allowlist ASCII chính xác |
| Chấp nhận mọi scheme | Có thể đưa javascript:, data: hoặc scheme không mong muốn vào sink | Allowlist protocol theo nghiệp vụ |
| Tin thẻ base mặc định | URL tương đối bị chuyển sang đích khác | CSP base-uri, kiểm soát markup và URL |
| Nghĩ URL encoding thay thế HTML escaping | DOM XSS trong attribute hoặc HTML context | Encode/sanitize đúng output context; dùng DOM API an toàn |
| Nghĩ CORS ngăn navigation/CSRF | Form/link vẫn có thể gửi request | CSRF token, SameSite, kiểm tra request và phân quyền server |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** URL https://trusted.example@attacker.test/ có hostname là gì?

**Đáp án:** attacker.test. Phần trusted.example nằm trong userinfo trước dấu @.

**Câu 2.** Vì sao raw.startsWith('https://trusted.example') không phải kiểm tra allowlist an toàn?

**Đáp án:** Có thể khớp https://trusted.example.attacker.test/ hoặc URL chứa userinfo https://trusted.example@attacker.test/. Cần parse URL và so sánh origin chính xác.

**Câu 3.** https://app.example.com:443/ và https://app.example.com/ có cùng origin không?

**Đáp án:** Có trong mô hình URL chuẩn hóa vì 443 là port mặc định của HTTPS. Port không mặc định như 8443 tạo origin khác.

**Câu 4.** Vì sao %252e%252e%252fadmin có thể nguy hiểm khi qua hai tầng decode?

**Đáp án:** Decode một lần thành %2e%2e%2fadmin; decode lần hai thành ../admin. Nếu kiểm tra và sử dụng ở những tầng decode khác nhau, kiểm tra path có thể bị bypass.

**Câu 5.** Fragment #section có được gửi trong HTTP request không?

**Đáp án:** Thông thường không. Fragment được xử lý phía client và không nằm trong request target gửi tới server.

**Câu 6.** encodeURIComponent() có phải hàm sanitizer HTML không?

**Đáp án:** Không. Nó encode một thành phần URL; không thay thế HTML attribute escaping, JavaScript string escaping hoặc sanitizer.

**Câu 7.** Query có role=user&role=admin cần được xử lý ra sao?

**Đáp án:** Xác định cardinality của key. Nếu chỉ cho phép một giá trị, từ chối key lặp; đảm bảo mọi tầng dùng cùng parser và quy tắc. Không lấy role từ query để cấp quyền.

**Câu 8.** CORS allowlist có thể dùng origin.includes('example.com') không?

**Đáp án:** Không. Cần parse/chuẩn hóa và so sánh chính xác origin gồm scheme, host, port. Không phản chiếu origin tùy ý và không tin null cho API nhạy cảm.

**Câu 9.** Một URL //evil.example/path có phải đường dẫn nội bộ không?

**Đáp án:** Không nhất thiết. Đây là scheme-relative URL; khi resolve với base HTTPS, nó trỏ tới https://evil.example/path. Phải parse với base tin cậy rồi kiểm tra origin.

**Câu 10.** Nếu ứng dụng đã kiểm tra URL bằng parser chuẩn, có thể đưa trực tiếp vào innerHTML không?

**Đáp án:** Không. URL validation không phải HTML sanitization. Dùng DOM API và textContent/thuộc tính đã kiểm tra; nếu cần HTML động, dùng sanitizer và CSP/Trusted Types phù hợp.

## 12. Ghi nhớ

URL confusion thường không đến từ một ký tự kỳ lạ đơn lẻ mà từ **sự bất đồng giữa các bước parse, decode, normalize, validate và sử dụng**. Một hệ thống an toàn phải bảo đảm mọi lớp cùng hiểu một đích đến và một route.

Hãy nhớ bốn nguyên tắc:

1. **Parse trước khi tin:** dùng parser URL chuẩn; không tự tách chuỗi để xác định host/origin.
2. **Chuẩn hóa nhất quán:** không double decode; thống nhất slash, dot segment, Unicode và query duplicate giữa proxy và ứng dụng.
3. **Kiểm tra cấu trúc:** scheme, origin, hostname, port, userinfo, path và cardinality của query phải phù hợp chính sách.
4. **Dùng đúng ngữ cảnh:** URL validation, CORS, CSRF protection, HTML escaping, CSP và Trusted Types giải quyết các lớp rủi ro khác nhau.

## Tài liệu tham khảo

- [WHATWG URL Standard](https://url.spec.whatwg.org/)
- [MDN — URL API](https://developer.mozilla.org/en-US/docs/Web/API/URL)
- [MDN — URLSearchParams](https://developer.mozilla.org/en-US/docs/Web/API/URLSearchParams)
- [MDN — encodeURIComponent()](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/encodeURIComponent)
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html)
- [OWASP — HTTP Parameter Pollution](https://owasp.org/www-community/attacks/HTTP_Parameter_Pollution)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP)

