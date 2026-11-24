# Response type: phân biệt mức truy cập response của Fetch và kiểu dữ liệu của XMLHttpRequest

> **Chương:** Fetch và XMLHttpRequest  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Khi nhận response từ server, JavaScript cần biết hai điều khác nhau: browser cho phép script nhìn thấy những phần nào của response, và ứng dụng muốn đọc phần body dưới dạng dữ liệu gì. Fetch biểu diễn câu hỏi thứ nhất bằng thuộc tính **Response.type**. XMLHttpRequest biểu diễn câu hỏi thứ hai chủ yếu bằng **XMLHttpRequest.responseType**.

Hai thuộc tính có tên gần giống nhau nhưng không thể thay thế cho nhau. Response.type phản ánh cách Fetch lọc response theo ranh giới same-origin, CORS và redirect. XMLHttpRequest.responseType yêu cầu browser chuyển body thành text, JSON object, Document, Blob hoặc ArrayBuffer. Việc chọn JSON hay Blob không cấp quyền đọc dữ liệu cross-origin; CORS vẫn quyết định quyền đó.

Bài này phân tích sáu giá trị Response.type, header nào được JavaScript nhìn thấy, opaque response và manual redirect, cách phân biệt HTTP error với network/CORS error, cách đọc body an toàn và cách đối chiếu với responseType của XHR. Lab hai origin localhost giúp quan sát từng trường hợp bằng DevTools.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích Response.type mô tả response filtering, không phải MIME type hoặc định dạng body.
2. Phân biệt basic, cors, default, error, opaque và opaqueredirect.
3. Giải thích vì sao opaque response có status 0, headers rỗng và body null.
4. Phân biệt network/CORS failure làm Fetch reject với HTTP 4xx/5xx trả về một Response bình thường.
5. Hiểu CORS-safelisted response headers, Access-Control-Expose-Headers và header bị cấm như Set-Cookie.
6. Dự đoán response type theo request mode và redirect mode.
7. Dùng Response body methods và xử lý body stream chỉ đọc một lần.
8. Phân biệt Response.type của Fetch với XMLHttpRequest.responseType.
9. Chọn responseType phù hợp cho text, JSON, document, Blob và ArrayBuffer.
10. Chẩn đoán lỗi bằng Network, Console và lab hai origin.

## 1. Hai khái niệm cùng tên “type” nhưng khác nhiệm vụ

### 1.1 Response.type của Fetch là phân loại bảo mật

Fetch trả về một đối tượng Response. Thuộc tính type cho biết browser đã cung cấp response cho JavaScript qua lớp lọc nào.

Ví dụ:

~~~js
const response = await fetch('/api/profile');

console.log(response.type); // "basic" nếu response same-origin
console.log(response.status);
console.log(response.headers.get('content-type'));
~~~

Nếu request thành công tới một origin khác bằng CORS, type thường là cors. Nếu request cross-origin dùng no-cors, type có thể là opaque. Những giá trị này nói về mức độ response được expose cho script, không nói body là JSON hay ảnh.

### 1.2 XMLHttpRequest.responseType chọn cách biểu diễn body

Với XHR:

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/api/profile');
xhr.responseType = 'json';

xhr.onload = () => {
  console.log(xhr.responseType); // "json"
  console.log(xhr.response);     // JavaScript object nếu parse thành công
};

xhr.send();
~~~

responseType là lựa chọn của ứng dụng về cách browser diễn giải response body. Nó không cho biết request là same-origin hay CORS, và không thay đổi allowlist header mà JavaScript được phép đọc.

### 1.3 Content-Type là khái niệm thứ ba

HTTP response có header Content-Type, ví dụ:

~~~http
Content-Type: application/json; charset=utf-8
~~~

Content-Type mô tả media type của representation. Response.type mô tả cách browser expose response. XHR.responseType mô tả kiểu JavaScript muốn nhận.

| Thuộc tính | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Response.type | Browser đã lọc response theo ranh giới nào? | basic, cors, opaque |
| XMLHttpRequest.responseType | Body được chuyển thành kiểu dữ liệu nào? | json, blob, arraybuffer |
| HTTP Content-Type | Server nói body thuộc media type nào? | application/json, image/png |

Không suy luận Response.type từ Content-Type. Một response JSON có thể là basic, cors hoặc opaque tùy request và chính sách browser.

## 2. Sáu giá trị Response.type

Fetch Standard định nghĩa sáu giá trị: basic, cors, default, error, opaque và opaqueredirect.

### 2.1 basic: response được expose trong same-origin context

Một request same-origin thông thường nhận response type basic:

~~~js
const response = await fetch('/api/status');

console.log(response.type); // "basic"
console.log(response.status); // Ví dụ 200
console.log(response.ok); // true nếu status trong khoảng 200–299
console.log(await response.json());
~~~

Với basic response, JavaScript nhìn thấy phần lớn response headers, ngoại trừ các forbidden response-header names. Set-Cookie và Set-Cookie2 không được expose cho script, kể cả khi response cùng origin.

Basic không có nghĩa mọi dữ liệu server trả về đều an toàn. Ứng dụng vẫn cần kiểm tra status, Content-Type, schema, quyền truy cập và dữ liệu đầu vào trước khi sử dụng.

### 2.2 cors: response cross-origin đã vượt qua CORS

Một request tới origin khác có thể trả response type cors khi server cho phép request theo CORS:

~~~js
const response = await fetch('https://api.example.net/public-data');

console.log(response.type); // "cors" nếu CORS thành công
console.log(response.status);
console.log(response.headers.get('content-type'));
~~~

CORS response chỉ expose các CORS-safelisted response headers và các header được server công khai bằng Access-Control-Expose-Headers.

Các response headers được safelist mặc định gồm:

- Cache-Control.
- Content-Language.
- Content-Length.
- Content-Type.
- Expires.
- Last-Modified.
- Pragma.

Nếu server muốn JavaScript đọc thêm header tùy chỉnh, server có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id, X-RateLimit-Remaining
~~~

Sau đó script có thể đọc:

~~~js
console.log(response.headers.get('x-request-id'));
console.log(response.headers.get('x-ratelimit-remaining'));
~~~

Access-Control-Expose-Headers không thể làm Set-Cookie trở nên đọc được. Set-Cookie là forbidden response-header name và luôn bị ẩn khỏi JavaScript.

### 2.3 default: response được tạo bằng JavaScript

Một Response được tạo trực tiếp bằng constructor có type default:

~~~js
const response = new Response(
  JSON.stringify({ ok: true }),
  {
    status: 200,
    headers: { 'Content-Type': 'application/json' }
  }
);

console.log(response.type); // "default"
console.log(response.status); // 200
console.log(await response.json());
~~~

default thường xuất hiện với Response do ứng dụng hoặc Service Worker tạo ra. Nó không phải nhãn cho một HTTP response cross-origin đã vượt CORS. Đừng dùng default để kết luận request đến server có cùng origin.

Response.json(), Response.redirect() và các API tạo Response cũng cần được hiểu theo ngữ cảnh đối tượng được tạo; type của Response được tạo bằng JavaScript thường là default trừ khi thuật toán quy định một loại khác.

### 2.4 error: Response lỗi được tạo tường minh

Có thể tạo error response bằng:

~~~js
const response = Response.error();

console.log(response.type); // "error"
console.log(response.status); // 0
console.log(response.body); // null
~~~

Đây là một Response object có type error. Tuy nhiên, khi một request fetch thật gặp network error, lỗi CORS hoặc bị abort, Promise fetch thường reject thay vì resolve thành Response.error().

Ví dụ:

~~~js
try {
  const response = await fetch('https://unavailable.example.net/data');
  console.log('Fetch resolved:', response.type);
} catch (error) {
  console.log('Fetch rejected:', error.name);
}
~~~

Vì vậy, không chờ fetch trả về response.type === 'error' để xử lý lỗi mạng. Dùng try/catch để bắt Promise rejection.

### 2.5 opaque: response cross-origin ở mode no-cors

Khi request cross-origin dùng mode no-cors, browser có thể trả một opaque filtered response:

~~~js
const response = await fetch('https://cdn.example.net/public-file', {
  mode: 'no-cors'
});

console.log(response.type); // "opaque"
console.log(response.status); // 0
console.log(response.ok); // false
console.log(response.headers); // Headers rỗng
console.log(response.body); // null
~~~

Opaque response che giấu status, headers và body. JavaScript không thể đọc nội dung qua text(), json(), blob() hoặc arrayBuffer() vì body được expose là null.

Opaque không có nghĩa server thật sự trả HTTP status 0. Server có thể đã trả 200, 404 hoặc response khác; browser cố ý không tiết lộ thông tin đó cho script.

Không dùng no-cors để “sửa” lỗi CORS nếu ứng dụng cần đọc dữ liệu. no-cors chỉ giới hạn request vào một tập method/header được phép và làm response opaque. Nó không cấp quyền đọc response.

### 2.6 opaqueredirect: redirect ở chế độ manual

Khi request đặt redirect: 'manual' và server trả redirect, Fetch expose một opaqueredirect response:

~~~js
const response = await fetch('https://api.example.net/redirect', {
  redirect: 'manual'
});

console.log(response.type); // "opaqueredirect" khi nhận redirect
console.log(response.status); // 0
console.log(response.headers); // Headers rỗng
console.log(response.body); // null
~~~

JavaScript không thể đọc status 302 hoặc header Location từ response này. Đây là giới hạn có chủ đích để giữ quy tắc redirect và origin boundary.

Nếu cần nhận response cuối cùng, để redirect mặc định là follow:

~~~js
const response = await fetch('https://api.example.net/redirect');

console.log(response.redirected);
console.log(response.url); // URL cuối cùng nếu request hoàn tất
~~~

Nếu cần tự điều khiển redirect cross-origin ở tầng ứng dụng, thiết kế endpoint/API phía server để trả một URL hoặc dữ liệu điều hướng có thể đọc qua CORS. Không cố đọc Location từ opaqueredirect.

### 2.7 Bảng tổng hợp

| Response.type | Trường hợp thường gặp | status / ok | Headers và body |
|---|---|---|---|
| basic | Request same-origin | Status HTTP thật; ok theo 2xx | Headers được expose trừ forbidden response headers; body đọc được |
| cors | Cross-origin request vượt CORS | Status HTTP thật; ok theo 2xx | Safelist và header được expose; body đọc được |
| default | Response được tạo bằng JavaScript | Theo ResponseInit | Theo Response object được tạo |
| error | Response.error() | status 0; ok false | Headers rỗng, body null |
| opaque | Cross-origin no-cors | status 0; ok false | Headers rỗng, body null |
| opaqueredirect | Redirect với redirect: manual | status 0; ok false | Headers rỗng, body null |

Đừng chỉ nhìn response.ok để kết luận request thất bại. Opaque response có ok false vì status bị lọc thành 0, trong khi request có thể đã tải resource thành công ở tầng browser. Hãy xem response.type và mục đích của request.

## 3. Request mode quyết định mức response exposure

### 3.1 cors

cors là mode thường dùng cho Fetch cross-origin. Browser gửi request theo quy tắc CORS; server cần trả Access-Control-Allow-Origin phù hợp.

~~~js
const response = await fetch('https://api.example.net/items', {
  mode: 'cors'
});
~~~

Nếu request là simple request, browser có thể gửi trực tiếp rồi kiểm tra CORS headers trên response. Nếu request cần preflight, browser gửi OPTIONS trước để kiểm tra method/header được phép.

Nếu CORS thất bại, JavaScript thường chỉ nhận Promise rejection dạng TypeError; script không được đọc response lỗi của server.

### 3.2 same-origin

same-origin yêu cầu URL phải cùng origin. Nếu URL cross-origin, Fetch thất bại:

~~~js
await fetch('https://api.example.net/items', {
  mode: 'same-origin'
});
~~~

Mode này hữu ích khi ứng dụng chỉ chấp nhận endpoint cùng origin. Nó không phải cách yêu cầu server cấp CORS.

### 3.3 no-cors

no-cors giới hạn method và request headers vào các giá trị safelisted. Với request cross-origin thành công, response được expose dưới dạng opaque:

~~~js
const response = await fetch('https://cdn.example.net/image.png', {
  mode: 'no-cors'
});
~~~

Không thể dùng no-cors để đọc JSON, custom header, status hoặc body. Nếu cần đọc response, hãy cấu hình CORS tại server đích và dùng mode cors.

### 3.4 navigate

navigate là mode đặc biệt được browser dùng cho điều hướng document. JavaScript không thể tùy ý đặt Request.mode thành navigate để lấy quyền đọc response của navigation. Việc điều hướng do browser quản lý và chịu các quy tắc navigation riêng.

### 3.5 Mode không quyết định body parser

Mode cors không đồng nghĩa body là JSON. Mode no-cors không đồng nghĩa body là ảnh. Sau khi response được expose, ứng dụng vẫn chọn cách đọc body theo định dạng thực tế:

~~~js
const response = await fetch('/api/items');

if (!response.ok) {
  throw new Error('HTTP ' + response.status);
}

const contentType = response.headers.get('content-type') || '';

if (contentType.includes('application/json')) {
  const data = await response.json();
  console.log(data);
} else {
  const text = await response.text();
  console.log(text);
}
~~~

Content-Type là tín hiệu để chọn parser; không dùng Response.type thay cho Content-Type.

## 4. CORS response filtering và response headers

### 4.1 Basic response cũng có header bị ẩn

Một basic response expose headers ngoại trừ các forbidden response-header names. Ví dụ:

~~~js
const response = await fetch('/session');

console.log(response.headers.get('content-type'));
console.log(response.headers.get('set-cookie')); // null
~~~

Server có thể gửi Set-Cookie để browser xử lý cookie theo quy tắc cookie, nhưng JavaScript không được đọc giá trị Set-Cookie từ response.

### 4.2 CORS response chỉ expose danh sách cho phép

Server trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id
X-Request-Id: req-2026-001
X-Internal-Trace: node-17
~~~

Script có thể đọc X-Request-Id nhưng không đọc X-Internal-Trace vì header đó chưa được expose:

~~~js
console.log(response.headers.get('x-request-id')); // req-2026-001
console.log(response.headers.get('x-internal-trace')); // null
~~~

Việc header có xuất hiện trong DevTools Network không đồng nghĩa JavaScript có quyền đọc header đó. DevTools hiển thị dữ liệu ở góc độ developer; Fetch API áp dụng response filtering trước khi expose cho script.

### 4.3 Wildcard trong Access-Control-Expose-Headers

Server có thể dùng:

~~~http
Access-Control-Expose-Headers: *
~~~

Trong trường hợp request không dùng credentials, wildcard có thể có nghĩa expose tất cả response headers không bị cấm. Với credentialed request, dấu * không hoạt động như wildcard tổng quát; nó được hiểu như tên header cụ thể. Hãy liệt kê rõ header cần expose khi request có credentials.

Set-Cookie và Set-Cookie2 vẫn không được expose dù có wildcard.

### 4.4 Credential không quyết định Response.type

Request có credentials vẫn có thể tạo basic hoặc cors response. Response.type phụ thuộc cách request được thực hiện và response được lọc, không phải chỉ dựa vào việc có cookie.

Với credentialed CORS request:

~~~js
const response = await fetch('https://api.example.net/account', {
  mode: 'cors',
  credentials: 'include'
});
~~~

Server cần origin cụ thể, không dùng wildcard:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Cookie còn chịu SameSite, Secure, third-party cookie policy và các điều kiện browser khác. CORS cho phép script đọc response; nó không tự cấp cookie hoặc đăng nhập.

## 5. Redirect và Response.type

### 5.1 follow là hành vi mặc định

Fetch mặc định follow redirect. Khi request chuyển từ URL A sang URL B và hoàn tất, Response thường mô tả response cuối cùng:

~~~js
const response = await fetch('/legacy-endpoint');

console.log(response.redirected); // true nếu đã follow redirect
console.log(response.url); // URL cuối cùng
console.log(response.type);
~~~

Với redirect cross-origin, CORS phải hợp lệ trong chuỗi redirect theo quy tắc Fetch. Một endpoint đầu tiên có CORS nhưng endpoint đích không cho phép origin vẫn có thể khiến request thất bại.

### 5.2 manual che response redirect

~~~js
const response = await fetch('/redirect', {
  redirect: 'manual'
});

console.log(response.type);
~~~

Khi nhận redirect, script có thể thấy opaqueredirect thay vì status và Location. Đây là hành vi thiết kế, không phải lỗi server.

### 5.3 error từ redirect: 'error'

~~~js
try {
  await fetch('/redirect', {
    redirect: 'error'
  });
} catch (error) {
  console.log('Redirect bị từ chối:', error.name);
}
~~~

Nếu request gặp redirect và policy yêu cầu error, Fetch reject. Ứng dụng không nhận một Response 3xx để tự xử lý.

### 5.4 Redirect không đồng nghĩa HTTP error

Redirect 301, 302, 303, 307 và 308 là các status HTTP hợp lệ. Với redirect mặc định, browser có thể follow rồi trả response cuối cùng. Với manual, browser có thể trả opaqueredirect. Với error, Promise reject.

## 6. Đọc body của Fetch Response

### 6.1 Response type và body parser độc lập

Sau khi response được expose, chọn method theo representation:

| Method | Kết quả |
|---|---|
| response.text() | Promise trả string |
| response.json() | Promise parse JSON thành JavaScript value |
| response.blob() | Promise trả Blob |
| response.arrayBuffer() | Promise trả ArrayBuffer |
| response.formData() | Promise trả FormData khi body phù hợp |
| response.bytes() | Promise trả Uint8Array trên browser hỗ trợ |

Các method đọc body bất đồng bộ. Nếu body không phải định dạng mong đợi, parser có thể reject. Ví dụ response.json() reject nếu body không parse được JSON.

### 6.2 Body chỉ đọc được một lần

Body của Response là stream. Sau khi đọc bằng json(), text() hoặc blob(), bodyUsed trở thành true và không thể đọc lại body gốc:

~~~js
const response = await fetch('/api/data');

const data = await response.json();
console.log(data);

// Gọi response.text() sau đó sẽ thất bại vì body đã được tiêu thụ.
~~~

Nếu cần hai cách đọc, clone response trước khi tiêu thụ:

~~~js
const response = await fetch('/api/data');

const copy = response.clone();

const data = await response.json();
const rawText = await copy.text();

console.log(data, rawText);
~~~

Không clone response quá nhiều lần nếu body lớn. Các nhánh stream có thể làm tăng buffering và bộ nhớ.

### 6.3 Kiểm tra status trước khi parse

Fetch không reject chỉ vì server trả 404 hoặc 500:

~~~js
const response = await fetch('/api/missing');

console.log(response.type); // basic
console.log(response.status); // 404
console.log(response.ok); // false
~~~

Promise vẫn resolve với Response. Ứng dụng phải kiểm tra response.ok hoặc status trước khi xử lý như dữ liệu thành công.

Ngược lại, lỗi DNS, TLS, CORS, network hoặc abort có thể làm Promise reject và không có Response để kiểm tra.

### 6.4 Không đọc body opaque

Opaque response có body null. Không gọi json() hoặc text() rồi kỳ vọng lấy nội dung. Nếu cần dữ liệu, thay endpoint để hỗ trợ CORS hoặc chuyển việc tải sang một backend cùng origin có quyền phù hợp.

### 6.5 Không đưa response HTML thẳng vào DOM

Ngay cả khi response.type là basic hoặc cors, body vẫn có thể chứa HTML không tin cậy. Đừng đưa response text vào innerHTML nếu chưa sanitize. Dùng textContent khi cần hiển thị văn bản; nếu cần rich HTML, dùng sanitizer chuyên dụng và allowlist.

## 7. XMLHttpRequest.responseType chi tiết

### 7.1 Giá trị mặc định

XHR có responseType mặc định là chuỗi rỗng. Chuỗi rỗng có nghĩa hành vi text:

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/api/message');
console.log(xhr.responseType); // ""
~~~

Khi response hoàn tất, xhr.response thường là string. Có thể dùng xhr.responseText để đọc văn bản.

### 7.2 text

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/api/message');
xhr.responseType = 'text';

xhr.onload = () => {
  console.log(xhr.response); // string
  console.log(xhr.responseText);
};

xhr.send();
~~~

responseText chỉ dùng được khi responseType là chuỗi rỗng hoặc text. Nếu responseType là json, blob, arraybuffer hoặc document, truy cập responseText có thể ném InvalidStateError.

### 7.3 json

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/api/data');
xhr.responseType = 'json';

xhr.onload = () => {
  if (xhr.status >= 200 && xhr.status < 300) {
    console.log(xhr.response); // Object, Array hoặc primitive JSON
  } else {
    console.error('HTTP', xhr.status);
  }
};

xhr.send();
~~~

Browser parse JSON thành JavaScript value. Nếu response không phải JSON hợp lệ hoặc không thể parse, xhr.response thường là null. Kiểm tra status và response trước khi dùng như object.

### 7.4 blob

Blob phù hợp với file hoặc binary data cần lưu, hiển thị hoặc chuyển thành object URL:

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/assets/photo.png');
xhr.responseType = 'blob';

xhr.onload = () => {
  if (xhr.status >= 200 && xhr.status < 300 && xhr.response) {
    const objectUrl = URL.createObjectURL(xhr.response);
    document.querySelector('img').src = objectUrl;
  }
};

xhr.send();
~~~

Khi không còn sử dụng object URL, gọi URL.revokeObjectURL() để giải phóng tài nguyên.

### 7.5 arraybuffer

ArrayBuffer phù hợp khi ứng dụng cần thao tác byte:

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/assets/data.bin');
xhr.responseType = 'arraybuffer';

xhr.onload = () => {
  if (xhr.status >= 200 && xhr.status < 300 && xhr.response) {
    const bytes = new Uint8Array(xhr.response);
    console.log('Byte count:', bytes.length);
  }
};

xhr.send();
~~~

ArrayBuffer không tự giải mã ảnh, audio hoặc text. Nó chỉ chứa bytes; ứng dụng cần decoder hoặc API phù hợp.

### 7.6 document

responseType document yêu cầu browser parse response thành HTML Document hoặc XMLDocument tùy MIME type và môi trường:

~~~js
const xhr = new XMLHttpRequest();

xhr.open('GET', '/documents/help.html');
xhr.responseType = 'document';

xhr.onload = () => {
  const doc = xhr.response;
  console.log(doc?.title);
};

xhr.send();
~~~

Giá trị này chủ yếu dùng trong Window context; không phải lựa chọn cho mọi worker context. Nội dung document tải về vẫn phải được coi là dữ liệu không tin cậy nếu được đưa vào trang hiện tại. Việc parse thành Document không tự làm sạch HTML hoặc loại bỏ mọi rủi ro XSS.

### 7.7 Thiết lập responseType đúng thời điểm

Đặt responseType sau open() và trước send():

~~~js
xhr.open('GET', '/api/data', true);
xhr.responseType = 'json';
xhr.send();
~~~

Không đợi request chuyển sang LOADING hoặc DONE rồi mới đổi responseType. Việc thay đổi trong trạng thái không phù hợp có thể ném InvalidStateError.

Synchronous XHR trong Window context có giới hạn nghiêm ngặt; cố thay đổi responseType cho synchronous request có thể ném InvalidAccessError. Không dùng synchronous XHR trong code giao diện mới. XHR không được hỗ trợ trong Service Worker.

### 7.8 responseText và response khác nhau

- xhr.response là giá trị theo responseType.
- xhr.responseText chỉ hợp lệ khi responseType là "" hoặc text.
- xhr.responseXML là giao diện cũ để truy cập XML document trong các trường hợp tương thích.
- xhr.responseURL cho biết URL cuối cùng sau redirect khi có.

Không đọc responseText khi đã chọn json hoặc blob. Dùng xhr.response theo kiểu đã khai báo.

## 8. Fetch Response.type và XHR responseType: đối chiếu

| Khía cạnh | Fetch | XMLHttpRequest |
|---|---|---|
| Thuộc tính type | response.type phân loại response filtering | Không có thuộc tính tương đương |
| Chọn kiểu body | Gọi json(), text(), blob(), arrayBuffer()... | Đặt xhr.responseType trước send() |
| CORS | mode cors và CORS response filtering | CORS được áp dụng tự động cho request cross-origin |
| no-cors opaque | Có thể nhận opaque response với status 0/body null | Không có tùy chọn no-cors tương đương cho ứng dụng |
| CORS failure | Promise fetch reject | Thường phát error event; status thường là 0 |
| HTTP 404/500 | Promise resolve; kiểm tra response.status/ok | load event vẫn có thể xảy ra; kiểm tra xhr.status |
| Body đọc lại | Stream một lần; clone trước nếu cần nhiều nhánh | response đã được browser tạo theo responseType |
| Redirect manual | Có thể nhận opaqueredirect | XHR tự xử lý redirect; không expose manual redirect response theo cách này |
| Hủy request | AbortController | xhr.abort() |
| Tiến trình tải | Stream/API và các cơ chế progress phù hợp | progress event có sẵn |

Điểm cốt lõi: Fetch Response.type là ranh giới bảo mật của response; XHR responseType là lựa chọn representation. Đặt xhr.responseType = 'json' không làm request cross-origin vượt CORS. Đặt fetch mode = 'cors' cũng không tự parse JSON; ứng dụng vẫn gọi response.json().

## 9. CORS failure, HTTP error và status 0

### 9.1 Ba tình huống khác nhau

| Tình huống | Fetch | XHR |
|---|---|---|
| Server trả HTTP 404 | Resolve Response, status 404, ok false | load event có thể chạy, status 404 |
| CORS check thất bại | Reject Promise, thường TypeError | error event; status thường 0 |
| Network/TLS/DNS failure | Reject Promise | error event; status thường 0 |

Status 0 trong Fetch thường xuất hiện trên opaque, opaqueredirect hoặc error response object. Status 0 trong XHR còn có thể xuất hiện trước khi request hoàn tất hoặc khi request thất bại. Không diễn giải status 0 là một HTTP status do server gửi.

### 9.2 Fetch error handling

~~~js
async function loadJson(url) {
  let response;

  try {
    response = await fetch(url);
  } catch (error) {
    throw new Error('Network/CORS/abort failure: ' + error.name);
  }

  if (response.type === 'opaque' || response.type === 'opaqueredirect') {
    throw new Error('Browser không expose response để ứng dụng đọc.');
  }

  if (!response.ok) {
    throw new Error('HTTP error: ' + response.status);
  }

  return response.json();
}
~~~

Trong ứng dụng thực tế, không nên gộp tất cả lỗi vào một thông báo nếu người dùng cần biết cách khắc phục. Ghi log phân loại an toàn, không ghi token hoặc dữ liệu cá nhân.

### 9.3 XHR error handling

~~~js
function loadJsonWithXhr(url) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.open('GET', url, true);
    xhr.responseType = 'json';
    xhr.timeout = 10000;

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300 && xhr.response !== null) {
        resolve(xhr.response);
      } else {
        reject(new Error('HTTP/parse failure: ' + xhr.status));
      }
    };

    xhr.onerror = () => reject(new Error('Network/CORS failure'));
    xhr.ontimeout = () => reject(new Error('Request timed out'));
    xhr.onabort = () => reject(new Error('Request aborted'));

    xhr.send();
  });
}
~~~

XHR không cho script biết nguyên nhân CORS chi tiết qua response body; browser cố ý che response không được phép đọc. Hãy xem Console và Network để chẩn đoán cấu hình server.

## 10. Cách kiểm tra response type trong DevTools

### 10.1 Network panel

Chọn request và kiểm tra:

- Request URL và origin.
- Request mode hoặc thông tin CORS liên quan nếu DevTools hiển thị.
- Status code và redirect chain.
- Response headers trên Network.
- Initiator và loại tài nguyên.
- Lỗi CORS trong Console.
- Response body mà DevTools có thể hiển thị.

DevTools có thể hiển thị header mà JavaScript không được phép đọc. Đây không phải mâu thuẫn: DevTools có quyền quan sát ở tầng developer tools, còn Fetch API trả filtered response cho trang.

### 10.2 Log Response metadata

~~~js
function inspectResponse(response) {
  console.table({
    type: response.type,
    status: response.status,
    ok: response.ok,
    statusText: response.statusText,
    url: response.url,
    redirected: response.redirected,
    bodyUsed: response.bodyUsed,
    hasBody: response.body !== null
  });

  console.log([...response.headers.entries()]);
}
~~~

Với opaque hoặc opaqueredirect, nhiều trường sẽ rỗng hoặc bằng 0. Không dùng những trường đó để suy luận server đã trả response gì.

### 10.3 Log XHR metadata

~~~js
function inspectXhr(xhr) {
  console.table({
    readyState: xhr.readyState,
    status: xhr.status,
    statusText: xhr.statusText,
    responseType: xhr.responseType,
    responseURL: xhr.responseURL
  });
}
~~~

Chỉ đọc response sau khi trạng thái phù hợp, thường trong load hoặc loadend. getAllResponseHeaders() và getResponseHeader() cũng chịu quy tắc CORS; header không được expose sẽ không xuất hiện trong kết quả.

## 11. Thực hành: quan sát Response.type và XHR.responseType bằng Node.js

Lab tạo hai origin khác nhau theo port:

- Trang ứng dụng: localhost:3000.
- API/resource server: localhost:3001.

Hai port khác nhau nên là hai origin khác nhau. Server API có các endpoint CORS thành công, CORS nhưng không expose header tùy chỉnh, endpoint không có CORS và redirect. Lab chỉ dùng dữ liệu giả.

### 11.1 Cấu trúc thư mục

~~~text
response-type-lab/
  server.mjs
  public/
    index.html
    app.js
~~~

### 11.2 Tạo file server.mjs

~~~js
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const appOrigin = 'http://localhost:3000';
const publicRoot = new URL('./public/', import.meta.url);

function sendJson(res, data, headers = {}) {
  res.writeHead(200, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    ...headers
  });
  res.end(JSON.stringify(data));
}

const appServer = createServer(async (req, res) => {
  const url = new URL(req.url || '/', appOrigin);

  if (url.pathname === '/same-origin') {
    return sendJson(res, {
      source: 'same-origin',
      message: 'Response type basic'
    }, {
      'X-Internal-Trace': 'same-origin-trace'
    });
  }

  if (url.pathname === '/') {
    try {
      const html = await readFile(new URL('index.html', publicRoot));
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-store'
      });
      return res.end(html);
    } catch {
      res.writeHead(500);
      return res.end('Cannot read index.html');
    }
  }

  if (url.pathname === '/app.js') {
    try {
      const js = await readFile(new URL('app.js', publicRoot));
      res.writeHead(200, {
        'Content-Type': 'text/javascript; charset=utf-8',
        'Cache-Control': 'no-store',
        'X-Content-Type-Options': 'nosniff'
      });
      return res.end(js);
    } catch {
      res.writeHead(500);
      return res.end('Cannot read app.js');
    }
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('Not found');
});

const apiServer = createServer((req, res) => {
  const url = new URL(req.url || '/', 'http://localhost:3001');

  if (url.pathname === '/cors') {
    return sendJson(res, {
      source: 'cross-origin-cors',
      message: 'CORS response is readable'
    }, {
      'Access-Control-Allow-Origin': appOrigin,
      'Access-Control-Expose-Headers': 'X-Debug-Id',
      'Vary': 'Origin',
      'X-Debug-Id': 'cors-debug-001',
      'X-Internal-Trace': 'hidden-unless-exposed'
    });
  }

  if (url.pathname === '/cors-limited') {
    return sendJson(res, {
      source: 'cross-origin-cors',
      message: 'Only safelisted response headers are exposed'
    }, {
      'Access-Control-Allow-Origin': appOrigin,
      'Vary': 'Origin',
      'X-Debug-Id': 'not-exposed'
    });
  }

  if (url.pathname === '/opaque') {
    res.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store'
    });
    return res.end('This body is hidden from no-cors fetch().');
  }

  if (url.pathname === '/redirect') {
    res.writeHead(302, {
      'Location': '/cors-final',
      'Access-Control-Allow-Origin': appOrigin,
      'Cache-Control': 'no-store',
      'Vary': 'Origin'
    });
    return res.end();
  }

  if (url.pathname === '/cors-final') {
    return sendJson(res, {
      source: 'redirect-final-response',
      message: 'Default redirect handling followed this endpoint'
    }, {
      'Access-Control-Allow-Origin': appOrigin,
      'Vary': 'Origin'
    });
  }

  if (url.pathname === '/no-cors-header') {
    return sendJson(res, {
      source: 'cors-failure',
      message: 'This response deliberately omits ACAO'
    });
  }

  res.writeHead(404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Access-Control-Allow-Origin': appOrigin
  });
  res.end('Not found');
});

appServer.listen(3000, 'localhost', () => {
  console.log('App: http://localhost:3000');
});

apiServer.listen(3001, 'localhost', () => {
  console.log('API: http://localhost:3001');
});
~~~

### 11.3 Tạo file public/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Response type lab</title>
  <script src="/app.js" defer></script>
</head>
<body>
  <main>
    <h1>Fetch Response.type và XHR responseType</h1>
    <p>Trang chạy tại localhost:3000; API chạy tại localhost:3001.</p>

    <section>
      <h2>Fetch</h2>
      <button id="basic">Same-origin basic</button>
      <button id="cors">CORS response</button>
      <button id="cors-limited">CORS headers bị giới hạn</button>
      <button id="opaque">no-cors opaque</button>
      <button id="redirect-follow">Redirect follow</button>
      <button id="redirect-manual">Redirect manual</button>
      <button id="constructed">Constructed/default và error</button>
    </section>

    <section>
      <h2>XMLHttpRequest</h2>
      <button id="xhr-json">XHR responseType=json</button>
      <button id="xhr-cors-fail">XHR CORS failure</button>
    </section>

    <section>
      <h2>Kết quả</h2>
      <pre id="output">Chưa có thao tác.</pre>
    </section>
  </main>
</body>
</html>
~~~

### 11.4 Tạo file public/app.js

~~~js
const output = document.querySelector('#output');

function show(value) {
  output.textContent = typeof value === 'string'
    ? value
    : JSON.stringify(value, null, 2);
}

function summarize(response) {
  return {
    type: response.type,
    status: response.status,
    ok: response.ok,
    statusText: response.statusText,
    url: response.url,
    redirected: response.redirected,
    bodyIsNull: response.body === null,
    bodyUsed: response.bodyUsed,
    contentType: response.headers.get('content-type'),
    debugId: response.headers.get('x-debug-id'),
    internalTrace: response.headers.get('x-internal-trace')
  };
}

async function runFetch(label, url, options = {}, readBody = true) {
  try {
    const response = await fetch(url, options);
    const result = {
      label,
      metadata: summarize(response)
    };

    if (readBody && response.body !== null) {
      result.body = await response.text();
    }

    show(result);
  } catch (error) {
    show({
      label,
      rejected: true,
      errorName: error.name,
      message: error.message
    });
  }
}

document.querySelector('#basic').addEventListener('click', () => {
  runFetch('basic', '/same-origin');
});

document.querySelector('#cors').addEventListener('click', () => {
  runFetch('cors', 'http://localhost:3001/cors');
});

document.querySelector('#cors-limited').addEventListener('click', () => {
  runFetch('cors-limited', 'http://localhost:3001/cors-limited');
});

document.querySelector('#opaque').addEventListener('click', () => {
  runFetch(
    'opaque',
    'http://localhost:3001/opaque',
    { mode: 'no-cors' },
    false
  );
});

document.querySelector('#redirect-follow').addEventListener('click', () => {
  runFetch('redirect-follow', 'http://localhost:3001/redirect');
});

document.querySelector('#redirect-manual').addEventListener('click', () => {
  runFetch(
    'redirect-manual',
    'http://localhost:3001/redirect',
    { redirect: 'manual' },
    false
  );
});

document.querySelector('#constructed').addEventListener('click', () => {
  const normal = new Response('Generated locally', {
    status: 200,
    headers: { 'Content-Type': 'text/plain' }
  });

  const error = Response.error();

  show({
    constructed: {
      type: normal.type,
      status: normal.status,
      bodyIsNull: normal.body === null
    },
    error: {
      type: error.type,
      status: error.status,
      ok: error.ok,
      bodyIsNull: error.body === null
    }
  });
});

document.querySelector('#xhr-json').addEventListener('click', () => {
  const xhr = new XMLHttpRequest();

  xhr.open('GET', 'http://localhost:3001/cors', true);
  xhr.responseType = 'json';

  xhr.onload = () => {
    show({
      kind: 'XMLHttpRequest',
      responseType: xhr.responseType,
      status: xhr.status,
      responseURL: xhr.responseURL,
      response: xhr.response,
      debugId: xhr.getResponseHeader('X-Debug-Id'),
      internalTrace: xhr.getResponseHeader('X-Internal-Trace')
    });
  };

  xhr.onerror = () => {
    show({
      kind: 'XMLHttpRequest',
      event: 'error',
      status: xhr.status
    });
  };

  xhr.send();
});

document.querySelector('#xhr-cors-fail').addEventListener('click', () => {
  const xhr = new XMLHttpRequest();

  xhr.open('GET', 'http://localhost:3001/no-cors-header', true);
  xhr.responseType = 'json';

  xhr.onload = () => {
    show({
      kind: 'XMLHttpRequest',
      event: 'load',
      status: xhr.status,
      response: xhr.response
    });
  };

  xhr.onerror = () => {
    show({
      kind: 'XMLHttpRequest',
      event: 'error',
      status: xhr.status,
      note: 'CORS failure: JavaScript cannot inspect the server response.'
    });
  };

  xhr.send();
});
~~~

### 11.5 Chạy lab

Từ thư mục response-type-lab:

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000
~~~

Không cần cài package ngoài; lab dùng Node.js built-in HTTP server. Hai port tạo hai origin để browser áp dụng CORS.

### 11.6 Thử basic response

Bấm Same-origin basic.

Kết quả mong đợi:

- type là basic.
- status là 200 và ok là true.
- X-Internal-Trace có thể đọc được vì đây là same-origin response và header không thuộc nhóm bị cấm.
- Body chứa JSON từ endpoint cùng origin.

### 11.7 Thử CORS response

Bấm CORS response.

Kết quả mong đợi:

- type là cors.
- status là 200.
- X-Debug-Id đọc được vì server có Access-Control-Expose-Headers.
- X-Internal-Trace là null vì server không expose header đó.
- Body đọc được vì CORS thành công.

Bấm CORS headers bị giới hạn. Response vẫn có type cors và body đọc được, nhưng X-Debug-Id không được expose nên script nhận null.

### 11.8 Thử opaque response

Bấm no-cors opaque.

Kết quả mong đợi:

- type là opaque.
- status là 0 và ok là false.
- headers không có giá trị để script đọc.
- bodyIsNull là true.

Server có thể đã trả 200, nhưng browser không expose status hoặc body. Đây không phải cách tải JSON cross-origin.

### 11.9 Thử redirect

Bấm Redirect follow. Browser follow 302 đến /cors-final; response cuối có type cors và body đọc được.

Bấm Redirect manual. Kết quả mong đợi là opaqueredirect, status 0, headers rỗng và body null. Script không đọc được Location từ response này.

### 11.10 Thử Response tạo bằng JavaScript

Bấm Constructed/default và error.

- new Response(...) tạo response type default.
- Response.error() tạo response type error, status 0 và body null.

Đối chiếu với lỗi mạng thật: Fetch reject Promise thay vì resolve thành Response.error().

### 11.11 Thử XHR responseType

Bấm XHR responseType=json.

- xhr.responseType là json.
- xhr.response là JavaScript object sau khi parse.
- X-Debug-Id đọc được do server expose header.
- X-Internal-Trace không đọc được vì chưa expose.

Bấm XHR CORS failure. XHR phát error event và status thường là 0. JavaScript không đọc được response body hoặc status HTTP thật của endpoint.

### 11.12 Dừng lab

Sau khi thử nghiệm, dừng Node server bằng Ctrl+C trong terminal. Lab chỉ dùng dữ liệu demo, không có tài khoản hoặc thông tin cá nhân.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Response.type là opaque | Request cross-origin dùng no-cors | Cấu hình CORS và dùng cors nếu cần đọc body |
| status bằng 0 và body null | Opaque, opaqueredirect hoặc error response | Kiểm tra response.type; phân biệt Promise reject |
| CORS response có status 200 nhưng header tùy chỉnh là null | Header chưa nằm trong Access-Control-Expose-Headers | Thêm header cần expose ở server |
| DevTools thấy Set-Cookie nhưng script nhận null | Set-Cookie là forbidden response-header name | Xử lý cookie qua browser cookie mechanism, không đọc bằng JavaScript |
| Fetch reject nhưng server có log 200 | CORS check thất bại hoặc lỗi ở redirect chain | Kiểm tra ACAO, credentials và redirect từng bước |
| Fetch 404 không vào catch | HTTP error là Response hợp lệ | Kiểm tra response.ok hoặc status |
| redirect manual không đọc được Location | Response type là opaqueredirect | Dùng follow hoặc thiết kế API trả URL có thể đọc |
| response.json() reject | Body không phải JSON hợp lệ hoặc stream lỗi | Kiểm tra Content-Type và nội dung thực tế |
| response.text() chạy lần hai thất bại | Body đã được tiêu thụ | Clone trước khi đọc nhiều lần |
| XHR response là null với responseType=json | JSON không parse được hoặc request chưa hoàn tất/thất bại | Kiểm tra status, readyState và response body server |
| Đọc responseText ném InvalidStateError | responseType không phải text hoặc chuỗi rỗng | Dùng xhr.response theo responseType |
| XHR status bằng 0 | Request chưa hoàn tất, CORS/network failure hoặc abort | Kiểm tra load/error/abort/timeout và readyState |
| XHR CORS response không có custom header | Server chưa expose header | Thêm Access-Control-Expose-Headers |
| XHR document response null | MIME type hoặc context không phù hợp | Kiểm tra Content-Type và môi trường Window |
| responseType đổi quá muộn | Request đã vào trạng thái không cho đổi | Đặt sau open() và trước send() |

## 13. Ma trận kiểm thử Response type

| ID | Request/Response | Điều kiện | Kết quả mong đợi |
|---|---|---|---|
| R01 | Fetch same-origin | Endpoint trả 200 | basic |
| R02 | Fetch cross-origin | CORS thành công | cors |
| R03 | Fetch cross-origin | mode no-cors | opaque |
| R04 | Fetch redirect | redirect follow | Response cuối cùng; redirected true |
| R05 | Fetch redirect | redirect manual | opaqueredirect khi nhận redirect |
| R06 | Response constructor | new Response() | default |
| R07 | Response.error() | Tạo response lỗi tường minh | error |
| R08 | Fetch HTTP 404 | Server trả 404 | Promise resolve, ok false |
| R09 | Fetch CORS failure | ACAO không hợp lệ/thiếu | Promise reject |
| R10 | CORS response custom header | Không expose header | headers.get() trả null |
| R11 | CORS response custom header | Expose header | JavaScript đọc được header |
| R12 | Fetch body | Đọc text rồi đọc json | Lần đọc thứ hai thất bại |
| R13 | XHR responseType=json | JSON hợp lệ | xhr.response là object |
| R14 | XHR responseType=json | JSON sai định dạng | xhr.response thường là null |
| R15 | XHR responseType=blob | Binary response | xhr.response là Blob |
| R16 | XHR responseType=arraybuffer | Binary response | xhr.response là ArrayBuffer |
| R17 | XHR CORS failure | Server thiếu ACAO | error event, status thường 0 |
| R18 | XHR responseText | responseType=json | InvalidStateError khi đọc responseText |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Response.type mô tả điều gì?

**Đáp án:** Nó mô tả cách browser expose/ lọc response cho JavaScript theo các quy tắc Fetch và origin, không phải MIME type hoặc kiểu dữ liệu body.

**Câu 2.** basic và cors khác nhau thế nào?

**Đáp án:** basic thường là response same-origin và expose hầu hết header trừ forbidden response headers; cors là response cross-origin vượt CORS và chỉ expose header safelist cùng header được server cho phép.

**Câu 3.** Vì sao opaque response có status 0?

**Đáp án:** Browser cố ý lọc status, headers và body để script không suy luận response cross-origin được tải bằng no-cors.

**Câu 4.** Opaque response có nghĩa server trả HTTP status 0 không?

**Đáp án:** Không. Status 0 là giá trị được expose sau filtering; server có thể đã trả status HTTP bình thường.

**Câu 5.** Fetch network error khác Response.error() thế nào?

**Đáp án:** Response.error() tạo một Response có type error. Network/CORS failure của fetch thường làm Promise reject, không resolve thành Response.

**Câu 6.** Access-Control-Expose-Headers dùng để làm gì?

**Đáp án:** Nó cho phép JavaScript đọc thêm response headers ngoài CORS-safelisted response headers; không thể expose Set-Cookie.

**Câu 7.** Vì sao redirect manual có thể trả opaqueredirect?

**Đáp án:** Browser che status và Location của redirect để giữ ranh giới bảo mật và quy tắc redirect; ứng dụng không thể đọc response 302 như response thông thường.

**Câu 8.** XMLHttpRequest.responseType khác Response.type ở đâu?

**Đáp án:** responseType chọn cách biểu diễn body thành text, JSON, Document, Blob hoặc ArrayBuffer. Response.type phân loại mức response được expose cho script.

**Câu 9.** Vì sao Fetch không tự reject khi server trả 404?

**Đáp án:** 404 là HTTP response hợp lệ. Promise fetch resolve với Response và ứng dụng phải kiểm tra response.ok hoặc response.status.

**Câu 10.** Vì sao XHR status 0 cần được chẩn đoán theo event?

**Đáp án:** Nó có thể xuất hiện khi request chưa hoàn tất hoặc khi network/CORS/abort failure xảy ra; không phải HTTP status do server gửi.

## 15. Checklist triển khai

Trước khi xử lý response trong ứng dụng, hãy kiểm tra:

1. **Response filtering:** xác định basic, cors, opaque, opaqueredirect, default hoặc error.
2. **Request mode:** hiểu cors, same-origin và no-cors; không dùng no-cors để đọc dữ liệu.
3. **CORS:** server trả ACAO đúng origin và ACAC phù hợp nếu có credentials.
4. **Header exposure:** khai báo Access-Control-Expose-Headers cho custom header cần đọc.
5. **Forbidden headers:** không cố đọc Set-Cookie hoặc Set-Cookie2 từ JavaScript.
6. **Status:** phân biệt HTTP 4xx/5xx với network/CORS rejection.
7. **Redirect:** chọn follow/manual/error theo nhu cầu và hiểu opaqueredirect.
8. **Body parser:** chọn json/text/blob/arrayBuffer theo Content-Type và contract API.
9. **Body lifecycle:** clone response trước khi cần đọc nhiều lần.
10. **XHR responseType:** đặt sau open() và trước send(); dùng response thay cho responseText khi không phải text.
11. **XHR errors:** xử lý load, error, abort và timeout riêng.
12. **Data safety:** validate schema và sanitize HTML trước khi đưa vào DOM.
13. **Credentials:** không giả định CORS tự cấp cookie hoặc authentication.
14. **Observability:** dùng DevTools Network/Console và log metadata không chứa secret.
15. **Regression:** kiểm tra same-origin, CORS, no-cors, redirect, HTTP error và network failure trên browser mục tiêu.

**Ghi nhớ:** Response.type của Fetch là thông tin về ranh giới response mà browser cho JavaScript nhìn thấy. XMLHttpRequest.responseType là lựa chọn kiểu dữ liệu của body. Hãy xử lý CORS trước khi đọc response, phân biệt opaque với network error, kiểm tra HTTP status và chỉ parse body theo representation thực tế.

## Tài liệu tham khảo

- [WHATWG — Fetch Standard: Responses and filtered responses](https://fetch.spec.whatwg.org/#responses)
- [MDN — Response.type](https://developer.mozilla.org/en-US/docs/Web/API/Response/type)
- [MDN — Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [MDN — Response](https://developer.mozilla.org/en-US/docs/Web/API/Response)
- [MDN — XMLHttpRequest.responseType](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/responseType)
- [MDN — XMLHttpRequest.response](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/response)
- [MDN — XMLHttpRequest](https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest)
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Forbidden response header name](https://developer.mozilla.org/en-US/docs/Glossary/Forbidden_response_header_name)

