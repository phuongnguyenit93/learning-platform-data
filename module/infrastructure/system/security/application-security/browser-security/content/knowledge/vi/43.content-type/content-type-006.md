# JSON MIME: khai báo và xử lý dữ liệu JSON an toàn qua HTTP

JSON là định dạng trao đổi dữ liệu phổ biến giữa browser, frontend và API. Trong HTTP, media type chuẩn cho JSON thông thường là `application/json`. Header `Content-Type` cho biết body đang mang kiểu dữ liệu nào; `Accept` cho biết client muốn nhận kiểu dữ liệu nào.

Khai báo đúng JSON MIME giúp các thành phần hiểu body nhất quán, hỗ trợ content negotiation và giảm một số rủi ro do browser đoán sai nội dung. Tuy nhiên, `application/json` không tự xác thực dữ liệu, không ngăn XSS/CSRF, không thay thế CORS hoặc authorization và cũng không làm JSON an toàn khi được ghép vào HTML.

Bài học này giải thích cách dùng JSON MIME trong request/response, xử lý UTF-8, phân biệt JSON với JavaScript/JSONP, cấu hình `X-Content-Type-Options: nosniff`, bảo vệ endpoint JSON, parse và validate dữ liệu không tin cậy, tránh JSON hijacking/XSSI và kiểm thử hành vi thực tế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích ý nghĩa của `application/json` và header `Content-Type`.
- Phân biệt `Content-Type`, `Accept` và `Content-Encoding`.
- Hiểu quy tắc UTF-8 và việc không cần thêm `charset` vào JSON MIME.
- Nhận diện các media type có hậu tố `+json`.
- Phân biệt JSON data với JavaScript source và JSONP.
- Hiểu giới hạn của MIME sniffing và `nosniff`.
- Xây dựng API JSON có content negotiation và status code phù hợp.
- Kết hợp JSON MIME với CORS, CSRF và cookie authentication.
- Phòng tránh JSON hijacking/XSSI trong các môi trường cần hỗ trợ.
- Parse JSON an toàn và validate schema, kiểu dữ liệu, kích thước và độ sâu.
- Tránh prototype pollution, duplicate-key ambiguity và mất chính xác số.
- Nhúng JSON vào HTML mà không tạo cơ hội phá vỡ cấu trúc document.
- Kiểm thử response headers, malformed JSON, CORS và cache behavior.

## 1. JSON MIME trong HTTP là gì?

Media type mô tả định dạng của representation được gửi trong HTTP message. Với JSON thông thường, media type chuẩn là:

~~~http
Content-Type: application/json
~~~

Ví dụ response API:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{
  "id": "user-42",
  "displayName": "Lan",
  "active": true
}
~~~

Browser hoặc client HTTP có thể dùng `Content-Type` để hiểu cách xử lý body. Framework cũng có thể dùng header này để chọn parser hoặc serializer phù hợp.

`application/json` mô tả cú pháp dữ liệu JSON. Nó không nói dữ liệu có đáng tin hay người gọi có quyền truy cập hay không.

### 1.1 Vì sao không nên dùng text/plain hoặc text/html cho JSON?

Nếu body là JSON nhưng server khai báo:

~~~http
Content-Type: text/html
~~~

browser và middleware có thể xử lý nó như HTML, dẫn đến parsing không nhất quán hoặc rủi ro khi nội dung bị render. Nếu khai báo:

~~~http
Content-Type: text/plain
~~~

client có thể coi body là văn bản thông thường và một số thư viện sẽ không chọn JSON parser tự động.

Hãy khai báo media type phản ánh đúng representation. Không dựa vào browser hoặc proxy tự đoán định dạng.

### 1.2 JSON MIME không phải JavaScript MIME

JSON là dữ liệu. JavaScript là mã có thể thực thi.

| Media type | Mục đích |
|---|---|
| `application/json` | Dữ liệu JSON |
| `text/javascript` | JavaScript source |
| `application/javascript` | JavaScript source theo cách khai báo cũ, vẫn gặp trong hệ thống |
| `text/plain` | Văn bản thuần |
| `text/html` | HTML document |

Không trả JSON API dưới dạng `text/javascript` chỉ để có thể nhúng response bằng thẻ `script`. Cách đó làm mờ ranh giới giữa dữ liệu và mã thực thi.

## 2. Content-Type, Accept và Content-Encoding

Ba header này trả lời ba câu hỏi khác nhau.

| Header | Ý nghĩa | Ví dụ |
|---|---|---|
| `Content-Type` | Body hiện tại được biểu diễn theo định dạng nào? | `application/json` |
| `Accept` | Client có thể nhận những media type nào? | `application/json, application/problem+json` |
| `Content-Encoding` | Representation được nén theo cách nào? | `gzip` hoặc `br` |

Ví dụ request:

~~~http
POST /api/users HTTP/1.1
Host: api.example.test
Content-Type: application/json
Accept: application/json
Content-Encoding: gzip

{"displayName":"Lan"}
~~~

Trong ví dụ thực tế, body sau khi giải nén phải là JSON hợp lệ. `Content-Encoding` không thay thế `Content-Type`: gzip cho biết cách giải nén, còn application/json cho biết định dạng dữ liệu sau giải nén.

### 2.1 Content-Type của request

Client gửi JSON trong body nên khai báo:

~~~http
Content-Type: application/json
~~~

Server có thể từ chối media type không được hỗ trợ bằng:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/problem+json
~~~

Không cố parse mọi request body như JSON bất kể Content-Type. Việc đó làm endpoint có hành vi mơ hồ và có thể tạo đường vòng cho validation hoặc CSRF controls.

### 2.2 Accept của request

Client có thể yêu cầu response JSON:

~~~http
Accept: application/json
~~~

Nếu API chỉ hỗ trợ representation khác với những loại client chấp nhận, server có thể trả `406 Not Acceptable`. Nhiều API đơn giản luôn trả JSON và bỏ qua Accept; nếu làm vậy, hãy mô tả rõ contract.

### 2.3 Vary khi response phụ thuộc Accept

Nếu server trả HTML hoặc JSON tùy theo `Accept`, response cache cần biết representation phụ thuộc header nào:

~~~http
Vary: Accept
~~~

Thiếu `Vary: Accept` có thể khiến shared cache phục vụ nhầm representation được tạo cho request khác.

Nếu response còn phụ thuộc `Origin` trong CORS, cần cấu hình `Vary: Origin` khi header CORS được tạo theo origin request.

## 3. application/json và UTF-8

RFC 8259 đăng ký media type `application/json`. JSON trao đổi giữa các hệ thống phải dùng UTF-8 để đạt khả năng tương tác.

Ví dụ:

~~~http
Content-Type: application/json
~~~

JSON MIME không định nghĩa parameter `charset`. Một số hệ thống vẫn gửi `application/json; charset=utf-8` vì thói quen hoặc tương thích; parser có thể chấp nhận, nhưng ứng dụng không nên phụ thuộc vào parameter đó để xác định encoding.

### 3.1 UTF-8 và Unicode

JSON có thể chứa ký tự Unicode trực tiếp:

~~~json
{
  "message": "Xin chào, thế giới",
  "city": "Thành phố Hồ Chí Minh"
}
~~~

Hoặc biểu diễn ký tự bằng escape:

~~~json
{
  "message": "Xin ch\u00e0o"
}
~~~

Hai dạng có thể biểu diễn cùng giá trị sau khi parse.

### 3.2 BOM

JSON generator không được thêm UTF-8 BOM vào đầu JSON text. Parser có thể bỏ qua BOM để hỗ trợ interoperability, nhưng không nên tạo file JSON mới có BOM.

Nếu API nhận JSON từ hệ thống ngoài và parser báo lỗi ngay ký tự đầu tiên, hãy kiểm tra encoding/BOM thay vì xóa tùy tiện các byte đầu mà không hiểu nguồn dữ liệu.

### 3.3 Không tự đoán encoding

Không dựa vào nội dung để đoán charset. Hãy thống nhất UTF-8 trong API contract và kiểm tra client/server có giải mã cùng cách hay không.

## 4. Các media type có hậu tố +json

Một số media type có hậu tố cấu trúc `+json` để cho biết representation dùng cú pháp JSON nhưng có semantics riêng.

Ví dụ:

| Media type | Mục đích |
|---|---|
| `application/json` | JSON thông thường |
| `application/problem+json` | Chi tiết lỗi HTTP theo Problem Details |
| `application/ld+json` | JSON-LD |
| `application/hal+json` | Hypertext Application Language dạng JSON |
| `application/vnd.example.resource+json` | Representation JSON theo vendor media type |

Hậu tố `+json` cho phép công cụ nhận diện cú pháp JSON tổng quát, nhưng không làm các media type này có semantics giống nhau.

### 4.1 application/problem+json

RFC 9457 định nghĩa Problem Details cho HTTP APIs. Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/invalid-input",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Trường email không đúng định dạng",
  "instance": "/requests/req-123"
}
~~~

Client có thể parse representation này như JSON nhưng cần hiểu các field theo Problem Details contract. Không đưa stack trace, SQL query, secret hoặc thông tin nội bộ vào `detail`.

### 4.2 Vendor media type và versioning

API có thể dùng vendor media type như:

~~~http
Content-Type: application/vnd.example.orders+json
Accept: application/vnd.example.orders+json; version=2
~~~

Nếu version nằm trong media type parameter, server cần xử lý negotiation và `Vary` tương ứng. Đừng tạo versioning scheme phức tạp nếu version trong URL hoặc header riêng đã đủ rõ.
## 5. JSON không phải JavaScript

JSON có cú pháp nghiêm ngặt hơn JavaScript object literal.

Ví dụ JSON hợp lệ:

~~~json
{
  "name": "Lan",
  "enabled": true,
  "count": 3,
  "items": null
}
~~~

Ví dụ JavaScript object literal nhưng không phải JSON hợp lệ:

~~~js
const objectLiteral = {
  name: 'Lan',
  enabled: true,
  count: 3,
  callback: () => {}
};
~~~

Một số khác biệt:

- JSON yêu cầu tên property đặt trong dấu nháy kép.
- JSON string dùng dấu nháy kép, không dùng nháy đơn.
- JSON không hỗ trợ comment.
- JSON không có `undefined`, function, symbol hoặc BigInt.
- JSON không cho phép `NaN` và `Infinity`.
- JSON không cho phép trailing comma.

### 5.1 Không dùng eval để parse JSON

Không làm:

~~~js
const data = eval("(" + responseText + ")");
~~~

`eval` thực thi JavaScript. Nếu input bị kiểm soát bởi attacker, nó có thể chạy mã trong context của ứng dụng.

Dùng:

~~~js
const data = JSON.parse(responseText);
~~~

`JSON.parse` parse cú pháp JSON và không thực thi function hoặc expression JavaScript. Nhưng parse thành công không có nghĩa dữ liệu hợp lệ về nghiệp vụ hoặc đáng tin.

### 5.2 JSONP là một kỹ thuật legacy

JSONP bọc dữ liệu trong lời gọi callback:

~~~js
handleData({
  "name": "Lan"
});
~~~

Browser tải JSONP bằng thẻ script, nên response là JavaScript có thể thực thi chứ không phải JSON thuần. Nếu callback name hoặc payload không được kiểm soát đúng, JSONP có thể tạo injection hoặc data exposure.

Không dùng JSONP cho API mới. Dùng Fetch/XHR với CORS được cấu hình rõ ràng. Nếu phải duy trì JSONP cũ, hãy giới hạn callback syntax, không cho callback tùy ý và lập kế hoạch loại bỏ.

## 6. MIME sniffing và X-Content-Type-Options

Browser có thể dùng heuristic để đoán kiểu nội dung trong một số tình huống. Nếu server khai báo sai MIME, browser hoặc thành phần trung gian có thể diễn giải nội dung khác với dự kiến.

Ví dụ JSON response:

~~~http
Content-Type: application/json
X-Content-Type-Options: nosniff
~~~

`X-Content-Type-Options: nosniff` yêu cầu browser không thực hiện một số hành vi MIME sniffing. Đặc biệt, nó có ý nghĩa với việc tải script và stylesheet khi MIME không đúng.

### 6.1 nosniff không phải bộ lọc JSON

`nosniff` không:

- Xác thực JSON.
- Xác minh schema.
- Chặn mọi cách browser hiển thị JSON khi điều hướng trực tiếp.
- Thay thế CSP.
- Thay thế CORS hoặc CSRF protection.
- Ngăn XSS trong frontend khi ứng dụng đưa dữ liệu JSON vào HTML không an toàn.

Hãy dùng MIME đúng, `nosniff` và các biện pháp bảo vệ theo từng threat model.

### 6.2 Không phục vụ JSON dưới MIME sai

Một endpoint trả JSON không nên khai báo `text/html` hoặc `text/javascript` chỉ để tránh một lỗi client. Sửa client parser hoặc API contract thay vì làm sai media type.

## 7. Fetch API và xử lý JSON response

`response.json()` đọc body và parse thành JavaScript value. Method này không tự bảo đảm server đã khai báo đúng `Content-Type`.

Ví dụ:

~~~js
async function loadProfile() {
  const response = await fetch("/api/profile", {
    headers: {
      Accept: "application/json"
    },
    credentials: "same-origin"
  });

  if (!response.ok) {
    throw new Error("API request failed: " + response.status);
  }

  const contentType = response.headers.get("content-type") || "";
  const mediaType = contentType.split(";")[0].trim().toLowerCase();

  if (
    mediaType !== "application/json" &&
    !mediaType.endsWith("+json")
  ) {
    throw new Error("Unexpected response media type");
  }

  return response.json();
}
~~~

Ví dụ chấp nhận `application/json` và các media type kết thúc bằng `+json`. Ứng dụng có thể dùng allowlist hẹp hơn nếu API chỉ được phép trả một representation cụ thể.

### 7.1 Kiểm tra status trước khi parse

Không giả định mọi response đều có JSON body. `204 No Content`, `304 Not Modified` hoặc response lỗi từ proxy có thể không chứa JSON như client mong đợi.

Xác định API contract cho từng status và xử lý body tương ứng. Nếu parse thất bại, phân biệt lỗi mạng, lỗi HTTP và lỗi JSON syntax.

### 7.2 Parse error không phải validation error

`JSON.parse` có thể thành công nhưng schema vẫn sai:

~~~json
{
  "age": "không phải số",
  "role": "admin",
  "unexpected": true
}
~~~

Nếu API mong `age` là integer trong khoảng nhất định và role do server quyết định, cần schema validation và authorization riêng. Không tin client gửi role, tenant ID hoặc permission.

### 7.3 Giới hạn response size

Không đọc vô hạn response JSON từ endpoint không tin cậy. Hãy giới hạn payload phía server, dùng pagination/streaming cho dữ liệu lớn và đặt timeout phù hợp. `response.json()` thường cần materialize body để parse, nên payload rất lớn có thể tiêu tốn nhiều memory.

## 8. JSON MIME, CORS và CSRF

JSON MIME có liên quan đến CORS preflight nhưng không phải cơ chế chống CSRF hoàn chỉnh.

### 8.1 application/json có thể kích hoạt preflight

Một cross-origin Fetch request với:

~~~http
Content-Type: application/json
~~~

không thuộc nhóm CORS-safelisted Content-Type. Browser thường gửi preflight OPTIONS trước request thực:

~~~http
OPTIONS /api/update HTTP/1.1
Origin: https://client.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

Server có thể phản hồi:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://client.example.test
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Content-Type
Vary: Origin
~~~

Browser chỉ gửi request thực nếu preflight được chấp nhận theo CORS protocol.

### 8.2 CORS không thay thế CSRF protection

HTML form có thể gửi một số request đơn giản cross-origin với content type như:

- `application/x-www-form-urlencoded`
- `multipart/form-data`
- `text/plain`

CORS chủ yếu kiểm soát việc script đọc response và quy trình preflight cho request không đơn giản. Nó không ngăn mọi request cross-site được gửi đến server.

Nếu endpoint dùng cookie tự động gửi và thay đổi trạng thái, vẫn cần CSRF protection phù hợp: token anti-CSRF, kiểm tra Origin/Referer, SameSite cookie và contract method/content-type rõ ràng.

### 8.3 Không nhận JSON qua text/plain chỉ để tiện

Một số endpoint chấp nhận `text/plain` rồi parse body thành JSON. Cách này có thể mở đường cho form request đơn giản và làm yếu giả định preflight.

Nếu API yêu cầu JSON, hãy yêu cầu đúng `Content-Type: application/json` và từ chối media type khác. Vẫn triển khai CSRF controls khi authentication dựa trên cookie.

### 8.4 CORS credentials

Nếu cross-origin API cần cookie:

~~~http
Access-Control-Allow-Origin: https://client.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không thể kết hợp credentialed CORS với wildcard `Access-Control-Allow-Origin: *`. Chỉ allowlist origin cụ thể, kiểm tra Origin server-side và không coi CORS là authorization.
## 9. JSON hijacking và XSSI

JSON hijacking/XSSI là nhóm rủi ro liên quan đến việc một trang khác tìm cách khiến browser tải hoặc quan sát dữ liệu từ endpoint JSON trong context không mong đợi.

### 9.1 JSON hijacking là gì?

Trong các browser cũ, có những kỹ thuật khai thác việc một JSON response được tải bằng thẻ script, đặc biệt với top-level array và endpoint dựa vào cookie. Một số kỹ thuật lịch sử lợi dụng JavaScript execution behavior hoặc side effect để đọc dữ liệu.

Browser hiện đại đã có nhiều biện pháp giảm thiểu, nhưng ứng dụng vẫn cần bảo vệ dữ liệu và không nên dựa vào giả định rằng JSON response không thể bị nhúng ở nơi khác.

### 9.2 Biện pháp phòng vệ

- Không cung cấp dữ liệu nhạy cảm qua endpoint GET mà không có authorization phù hợp.
- Không trả JSONP.
- Dùng `Content-Type: application/json` và `X-Content-Type-Options: nosniff`.
- Cấu hình CORS allowlist.
- Bảo vệ endpoint cookie-authenticated khỏi CSRF.
- Tránh để response nhạy cảm được tải như script.
- Cân nhắc anti-XSSI prefix cho hệ thống legacy nếu threat model yêu cầu.

### 9.3 Anti-XSSI prefix

Một số hệ thống thêm prefix như:

~~~text
)]}',
{"account":"private"}
~~~

Prefix khiến response không còn là JSON thuần để parser JavaScript cũ hoặc script element xử lý trực tiếp như một expression. Client biết giao thức có thể bỏ prefix trước khi parse.

Đây là quy ước ứng dụng, không phải JSON chuẩn. Không thêm prefix tùy tiện vào API JSON công khai vì client chuẩn sẽ báo lỗi parse. Nếu dùng, phải thống nhất contract và kiểm thử tất cả client.

### 9.4 Không dùng prefix thay authorization

Anti-XSSI prefix không thay thế kiểm tra quyền. Nếu attacker gọi endpoint hợp lệ bằng credential của chính họ, prefix không ngăn họ đọc response. Server vẫn phải xác thực user, kiểm tra quyền và giới hạn dữ liệu trả về.

## 10. Parse và validate JSON an toàn

JSON body đến từ browser, mobile client, integration hoặc hệ thống ngoài đều là input không tin cậy.

Quy trình nên có:

1. Giới hạn kích thước body.
2. Kiểm tra Content-Type.
3. Parse bằng parser chuẩn.
4. Validate schema và kiểu dữ liệu.
5. Kiểm tra authorization cho từng trường/tài nguyên.
6. Chuẩn hóa dữ liệu theo domain.
7. Xử lý lỗi mà không tiết lộ nội bộ.

### 10.1 JSON.parse không thực thi JavaScript

`JSON.parse` an toàn hơn `eval` vì nó chỉ parse grammar JSON. Nhưng object được tạo ra vẫn chứa dữ liệu do người gửi kiểm soát.

Không render string từ JSON bằng `innerHTML`. Dùng `textContent` hoặc framework binding có output encoding.

### 10.2 Prototype pollution

JSON có thể chứa key đặc biệt như:

~~~json
{
  "__proto__": {
    "isAdmin": true
  },
  "name": "Lan"
}
~~~

`JSON.parse` không tự động thay đổi prototype của object chỉ vì key `__proto__` xuất hiện. Rủi ro thường phát sinh khi ứng dụng merge object không tin cậy vào object khác bằng cách đệ quy hoặc dùng thư viện merge không an toàn.

Phòng vệ:

- Dùng schema allowlist.
- Loại bỏ key `__proto__`, `prototype` và `constructor` trong các cấu trúc không cần chúng.
- Tránh recursive merge tùy tiện với object không tin cậy.
- Dùng `Object.create(null)` cho dictionary khi phù hợp.
- Cập nhật thư viện merge và kiểm tra prototype pollution advisory.

### 10.3 Duplicate JSON keys

Ví dụ:

~~~json
{
  "role": "user",
  "role": "admin"
}
~~~

Tên member trong object JSON nên là duy nhất. Khi key bị lặp, parser có thể giữ giá trị đầu, giá trị cuối hoặc xử lý khác nhau. Điều này tạo ambiguity giữa các thành phần.

Với dữ liệu nhạy cảm hoặc chữ ký số, hãy dùng parser có thể phát hiện duplicate keys và từ chối payload mơ hồ. Không giả định `JSON.parse` tiêu chuẩn sẽ báo lỗi cho duplicate key.

### 10.4 Numeric precision

JavaScript dùng Number cho JSON number. Số nguyên lớn hơn giới hạn an toàn `Number.MAX_SAFE_INTEGER` có thể mất chính xác.

Ví dụ ID dạng số 64-bit hoặc tiền tệ có thể bị làm tròn khi parse. Dùng string cho identifier lớn hoặc decimal có yêu cầu chính xác; chuyển đổi bằng thư viện decimal/bigint phù hợp sau khi validate.

Không truyền BigInt trực tiếp qua `JSON.stringify` vì JSON không có kiểu BigInt chuẩn.

### 10.5 Giới hạn độ sâu và complexity

Payload JSON quá lớn hoặc lồng nhau quá sâu có thể tiêu tốn CPU/memory hoặc làm parser/validator quá tải.

Đặt:

- Body size limit.
- Maximum nesting depth theo parser/schema nếu hỗ trợ.
- Maximum array length và object property count.
- Request timeout.
- Rate limit.
- Giới hạn số lượng lỗi validation trả về.

Không chỉ giới hạn số byte; một payload nhỏ nhưng có cấu trúc phức tạp cũng có thể gây tốn tài nguyên trong bước xử lý sau parse.
## 11. JSON trong HTML và ranh giới script

Một số ứng dụng nhúng dữ liệu JSON vào HTML để bootstrap frontend:

~~~html
<script id="bootstrap-data" type="application/json">
{"displayName":"Lan"}
</script>
~~~

`type="application/json"` làm script element trở thành data block thay vì JavaScript executable theo cách sử dụng phổ biến. Tuy nhiên, HTML parser vẫn xử lý thẻ script theo quy tắc raw-text; chuỗi `</script>` trong dữ liệu có thể kết thúc element ngay cả khi nằm trong JSON string.

### 11.1 Serialize an toàn cho HTML context

Không chèn raw user data vào HTML template. Dùng serializer chuyên dụng hoặc escape các ký tự có thể phá vỡ script element, đặc biệt ký tự nhỏ hơn `<`. Một cách phổ biến là chuyển nó thành chuỗi escape JSON `\u003c` trước khi đặt JSON vào script element.

Ví dụ minh họa:

~~~js
function serializeJsonForScriptElement(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}
~~~

Ví dụ này minh họa việc ngăn chuỗi mở thẻ HTML xuất hiện nguyên dạng trong script data block. Trong production, dùng helper/template engine đã được kiểm thử và xử lý thêm các ký tự theo đúng HTML context. Không dùng cùng một encoder cho mọi HTML context.

### 11.2 Đọc data block

Frontend có thể đọc:

~~~js
const element = document.getElementById("bootstrap-data");
const data = JSON.parse(element.textContent);
~~~

`textContent` đọc text của data block. Không dùng `innerHTML` để lấy hoặc đưa dữ liệu vào DOM khi không cần.

### 11.3 CSP vẫn có vai trò

CSP có thể hạn chế nguồn script và giảm tác động của một số XSS. Nhưng CSP không làm JSON serialization tự động an toàn. Phải encode đúng HTML context trước, sau đó mới dựa vào CSP như một lớp phòng vệ bổ sung.
## 12. Xây dựng JSON API ở server

Server cần xác định media type, status code, giới hạn body, validation và quyền truy cập.

### 12.1 Express JSON parser

Ví dụ Node.js/Express:

~~~js
import express from "express";

const app = express();

app.use(express.json({
  type: "application/json",
  limit: "1mb"
}));

function requireJsonContentType(req, res, next) {
  if (!req.is("application/json")) {
    return res.status(415).type("application/problem+json").send(JSON.stringify({
      type: "https://api.example.test/problems/unsupported-media-type",
      title: "Media type không được hỗ trợ",
      status: 415
    }));
  }
  next();
}

app.post("/api/profile", authenticate, requireJsonContentType, async (req, res) => {
  const result = validateProfileInput(req.body);

  if (!result.ok) {
    return res.status(422).type("application/problem+json").send(JSON.stringify({
      type: "https://api.example.test/problems/validation",
      title: "Dữ liệu không hợp lệ",
      status: 422
    }));
  }

  const profile = await updateProfile(req.user.id, result.value);

  res
    .status(200)
    .type("application/json")
    .set("X-Content-Type-Options", "nosniff")
    .send(JSON.stringify(profile));
});
~~~

Ví dụ giả định `authenticate` xác thực session/token và `validateProfileInput` kiểm tra schema cùng quyền trường dữ liệu. Body parser không thay validation và authorization.

Trong ứng dụng thực tế, đặt middleware kiểm tra media type trước parser hoặc cấu hình error handler để mọi request sai media type đều nhận response nhất quán.

### 12.2 Từ chối media type không hỗ trợ

Nếu endpoint chỉ nhận JSON, hãy kiểm tra Content-Type và trả 415 khi request không phù hợp. Đừng tự parse text/plain hoặc form body thành JSON nếu API contract không cho phép.

### 12.3 Không trả object nội bộ trực tiếp

Không serialize toàn bộ database model nếu nó chứa:

- Password hash.
- Reset token.
- Internal flags.
- Permission metadata.
- Secret key.
- Internal path hoặc debug field.

Tạo response DTO/allowlist gồm đúng các field client được phép nhận.

### 12.4 Error response

Dùng status code có ý nghĩa:

| Status | Trường hợp |
|---|---|
| 400 | JSON syntax lỗi hoặc request không hợp lệ |
| 401 | Thiếu hoặc credential không hợp lệ |
| 403 | Đã xác thực nhưng không đủ quyền |
| 404 | Tài nguyên không tồn tại hoặc không được phép tiết lộ |
| 406 | Không có representation phù hợp Accept |
| 413 | Body quá lớn |
| 415 | Content-Type không được hỗ trợ |
| 422 | JSON parse được nhưng dữ liệu không đạt validation |
| 429 | Vượt rate limit |
| 5xx | Lỗi nội bộ server |

Không trả stack trace, SQL error hoặc secret trong JSON error body production.
## 13. Cache và JSON chứa dữ liệu nhạy cảm

JSON API có thể trả dữ liệu public, dữ liệu user-specific hoặc secret. Cache policy phải phù hợp với loại dữ liệu.

### 13.1 Response nhạy cảm

Ví dụ:

~~~http
Cache-Control: private, no-store
Content-Type: application/json
X-Content-Type-Options: nosniff
~~~

`private` hạn chế shared cache lưu response; `no-store` yêu cầu cache không lưu response. Dùng cho dữ liệu nhạy cảm theo policy ứng dụng.

### 13.2 Response public có thể cache

Với dữ liệu công khai và ổn định:

~~~http
Cache-Control: public, max-age=300
ETag: "catalog-v42"
Content-Type: application/json
~~~

Cache cần tính đến query, Accept, Origin, Authorization và các input ảnh hưởng representation. Đừng cache response user-specific trong shared cache nếu cache key không tách biệt an toàn.

### 13.3 Service Worker

Service Worker có thể cache Fetch response vào Cache Storage. Không cache token response, dữ liệu riêng tư hoặc JSON chứa credential chỉ vì response có `application/json`.

Cần allowlist route được cache, loại trừ auth endpoints và xác định cách xóa cache khi logout hoặc user đổi tenant.

## 14. JSON upload và download

### 14.1 JSON request body

Khi gửi JSON:

~~~js
await fetch("/api/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json"
  },
  credentials: "same-origin",
  body: JSON.stringify({
    productId: "sku-42",
    quantity: 2
  })
});
~~~

`JSON.stringify` tạo JSON text. Nó không validate schema, không escape HTML context và không làm dữ liệu bí mật an toàn.

### 14.2 JSON file download

Nếu người dùng cần tải JSON như file:

~~~http
Content-Type: application/json
Content-Disposition: attachment; filename="export.json"; filename*=UTF-8''export.json
X-Content-Type-Options: nosniff
~~~

`Content-Disposition` điều khiển cách browser xử lý file tải về. JSON MIME vẫn mô tả nội dung. Với dữ liệu nhạy cảm, thêm authorization và cache policy phù hợp.

### 14.3 Không nhầm JSON với multipart

Một request upload file có thể dùng `multipart/form-data` với các part riêng. Một part có thể chứa JSON metadata, nhưng toàn bộ request vẫn có media type multipart với boundary.

Nếu API nhận raw JSON body, dùng `application/json`. Nếu nhận file và metadata nhiều phần, dùng multipart contract rõ ràng và validate từng part.
## 15. Kiểm thử JSON MIME

Dùng API lab do bạn kiểm soát. Không gửi dữ liệu người dùng hoặc credential thật vào endpoint test công khai.

### 15.1 Kiểm tra response header

Dùng curl:

~~~bash
curl -i -H "Accept: application/json" https://api.example.test/profile
~~~

Xác nhận:

- Status code.
- Content-Type là application/json hoặc media type được API contract cho phép.
- X-Content-Type-Options có giá trị nosniff.
- Cache-Control phù hợp.
- Vary có các request header ảnh hưởng representation.

### 15.2 Kiểm tra request parser

Gửi lần lượt:

~~~bash
curl -i -X POST https://api.example.test/profile \
  -H "Content-Type: application/json" \
  --data '{"displayName":"Lan"}'
~~~

~~~bash
curl -i -X POST https://api.example.test/profile \
  -H "Content-Type: text/plain" \
  --data '{"displayName":"Lan"}'
~~~

Nếu endpoint chỉ nhận JSON, request thứ hai nên bị từ chối theo contract, thường là 415.

### 15.3 Kiểm tra malformed JSON

Thử:

~~~json
{"name":"Lan",
~~~

Server nên trả lỗi client phù hợp, không crash, không trả stack trace và không ghi toàn bộ body nhạy cảm vào log.

### 15.4 Kiểm tra CORS và CSRF

- Gửi cross-origin Fetch với Content-Type application/json và quan sát OPTIONS preflight.
- Gửi form-urlencoded hoặc text/plain từ trang lab khác origin.
- Xác nhận endpoint cookie-authenticated có CSRF protection.
- Kiểm tra origin không được allowlist không thể đọc response.
- Kiểm tra credentialed CORS không dùng wildcard.

### 15.5 Kiểm tra JSON parser limits

Gửi payload vượt body size, array quá lớn, nesting sâu và chuỗi không hợp lệ. Xác nhận server giới hạn tài nguyên, trả status phù hợp và ghi log có kiểm soát.

### 15.6 Kiểm tra JSON trong HTML

Đưa các giá trị lab như `</script><script>...`, dấu `<`, `&`, U+2028/U+2029 vào bootstrap JSON. Xác nhận HTML structure không bị phá vỡ và dữ liệu được parse đúng sau khi serialize an toàn.

## 16. Lỗi triển khai thường gặp

### 16.1 Khai báo JSON là text/html

Browser hoặc middleware có thể xử lý body như HTML. Khai báo đúng `application/json`.

### 16.2 Dùng eval để parse

`eval` thực thi JavaScript. Dùng `JSON.parse` và validate schema.

### 16.3 Nghĩ JSON MIME tự chống XSS

JSON data có thể trở thành XSS nếu frontend ghép vào `innerHTML` hoặc serialize sai khi nhúng vào HTML. Dùng output encoding theo context.

### 16.4 Nghĩ application/json tự chống CSRF

Một số request cross-origin đơn giản vẫn có thể được gửi. Dùng CSRF token/Origin checks/SameSite phù hợp cho cookie-authenticated state changes.

### 16.5 Dùng JSONP cho API mới

JSONP là JavaScript thực thi, không phải JSON thuần. Dùng Fetch/XHR và CORS allowlist.

### 16.6 Chấp nhận text/plain rồi parse như JSON

Điều này có thể làm suy yếu giả định preflight và tạo endpoint behavior không rõ ràng. Yêu cầu media type theo contract.

### 16.7 Không giới hạn JSON body

Payload lớn hoặc cấu trúc phức tạp có thể gây DoS. Đặt size, depth, timeout và rate limits.

### 16.8 Parse thành công rồi tin toàn bộ field

JSON syntax hợp lệ không có nghĩa dữ liệu hợp lệ. Validate schema, domain rules và quyền truy cập từng field.

### 16.9 Merge object không tin cậy

Recursive merge có thể dẫn đến prototype pollution. Dùng allowlist và merge an toàn.

### 16.10 Cache JSON riêng tư

Shared cache có thể trả dữ liệu user này cho user khác nếu cache key không tách biệt. Dùng private/no-store cho dữ liệu nhạy cảm.

### 16.11 Trả lỗi nội bộ trong JSON

Stack trace, query database và secret trong error response làm lộ thông tin. Dùng Problem Details an toàn và log nội bộ đã redact.

## 17. Quy trình review JSON MIME

Trước khi đưa JSON API lên production:

1. Xác định media type cho từng request và response.
2. Dùng application/json cho JSON thông thường.
3. Dùng UTF-8 và không phát BOM.
4. Phân biệt Content-Type, Accept và Content-Encoding.
5. Chọn status code 400/406/413/415/422 theo lỗi.
6. Dùng media type `+json` đúng semantics khi API có representation chuyên biệt.
7. Không dùng JSONP hoặc eval.
8. Đặt X-Content-Type-Options: nosniff.
9. Cấu hình CORS allowlist và Vary chính xác.
10. Bảo vệ cookie-authenticated state changes khỏi CSRF.
11. Giới hạn body size, nesting, array length và processing time.
12. Parse bằng thư viện chuẩn và validate schema/domain.
13. Xử lý duplicate keys, prototype pollution và numeric precision khi liên quan.
14. Escape JSON đúng HTML context khi nhúng vào document.
15. Dùng DTO allowlist, không serialize database model trực tiếp.
16. Đặt cache policy phù hợp và loại trừ token/private response khỏi Service Worker cache.
17. Không trả stack trace hoặc secret trong error JSON.
18. Kiểm thử browser, proxy, CDN, CORS và parser boundary.

## 18. Checklist review JSON MIME

- [ ] JSON response dùng Content-Type application/json hoặc media type +json theo contract.
- [ ] JSON request body khai báo application/json.
- [ ] Content-Type, Accept và Content-Encoding được xử lý riêng.
- [ ] UTF-8 được dùng nhất quán; generator không thêm BOM.
- [ ] Không dựa vào charset parameter không được JSON MIME định nghĩa.
- [ ] Không trả JSON dưới text/html hoặc JavaScript MIME.
- [ ] Không dùng JSONP cho API mới.
- [ ] Không dùng eval hoặc Function để parse JSON.
- [ ] Có X-Content-Type-Options: nosniff.
- [ ] Hiểu nosniff không thay thế validation/CSP/authorization.
- [ ] CORS allowlist và Vary được cấu hình chính xác.
- [ ] Cookie-authenticated endpoint có CSRF protection.
- [ ] Endpoint JSON từ chối media type không hỗ trợ.
- [ ] Có giới hạn body size, nesting, array và timeout.
- [ ] JSON parse được vẫn phải qua schema/domain validation.
- [ ] Có xử lý duplicate key và prototype pollution phù hợp.
- [ ] Số nguyên lớn/decimal không bị mất chính xác.
- [ ] Không ghép JSON vào innerHTML.
- [ ] JSON nhúng trong HTML được serialize an toàn cho script element.
- [ ] Response DTO không chứa secret hoặc field nội bộ.
- [ ] Error response không lộ stack trace.
- [ ] Cache policy không rò rỉ dữ liệu riêng tư.
- [ ] Service Worker không cache token/private response.
- [ ] Đã kiểm thử 400/406/413/415/422 và malformed JSON.
- [ ] Đã kiểm thử CORS preflight và CSRF simple request.

## 19. Bài thực hành

Thực hiện trong API/browser lab do bạn kiểm soát.

### Bài 1: Xác minh JSON MIME

Tạo endpoint trả object JSON. Dùng DevTools và curl kiểm tra Content-Type, nosniff và Cache-Control.

### Bài 2: Content-Type và Accept

Tạo endpoint nhận JSON và trả JSON. Gửi request với Content-Type đúng/sai và Accept khác nhau. Xác nhận 415 và 406 theo contract.

### Bài 3: UTF-8 và BOM

Gửi chuỗi tiếng Việt và ký tự Unicode. Kiểm tra byte encoding và parser. Tạo fixture có BOM để quan sát behavior, nhưng generator của bạn phải phát UTF-8 không BOM.

### Bài 4: JSON vs JavaScript

Tạo một JSON endpoint và một legacy JSONP endpoint trong lab. So sánh media type, cách browser tải và rủi ro khi response được dùng như script. Sau đó loại bỏ JSONP.

### Bài 5: CORS preflight và CSRF

Từ origin lab khác, gửi Fetch application/json và form-urlencoded. Quan sát preflight và xác nhận endpoint cookie-authenticated từ chối request không có CSRF proof.

### Bài 6: Prototype pollution và duplicate keys

Dùng payload kiểm thử có `__proto__`, `constructor` và duplicate key. Xác nhận validator/merge layer xử lý theo policy và không thay đổi prototype ngoài ý muốn.

### Bài 7: HTML bootstrap JSON

Nhúng dữ liệu chứa `</script>`, `<`, `&` và Unicode separator vào data block. Xác nhận serializer không làm vỡ HTML và client parse đúng.

### Bài 8: Cache và error response

Kiểm tra dữ liệu riêng tư dùng no-store, response public có Vary/ETag đúng, malformed JSON không làm lộ stack trace và Service Worker không cache token response.

## 20. Câu hỏi tự kiểm tra

**1. Media type chuẩn cho JSON thông thường là gì?**

`application/json`.

**2. Content-Type và Accept khác nhau thế nào?**

Content-Type mô tả body đang gửi; Accept mô tả media type client muốn nhận.

**3. JSON MIME có cần charset=utf-8 không?**

Không. JSON MIME không định nghĩa charset parameter; JSON trao đổi dùng UTF-8.

**4. JSON khác JavaScript object literal như thế nào?**

JSON có grammar nghiêm ngặt: key và string dùng dấu nháy kép, không có comment, function, undefined hoặc trailing comma.

**5. Vì sao không dùng eval để parse JSON?**

Eval thực thi JavaScript có thể bị attacker kiểm soát; JSON.parse chỉ parse cú pháp JSON.

**6. application/json có tự chống CSRF không?**

Không. Request đơn giản cross-origin vẫn có thể được gửi; endpoint dùng cookie cần CSRF protection.

**7. nosniff có tác dụng gì?**

Hạn chế một số hành vi MIME sniffing của browser, đặc biệt khi tải script/style; nó không validate JSON hay thay CSP.

**8. Vì sao cần schema validation sau JSON.parse?**

Parse chỉ xác nhận cú pháp. Kiểu, phạm vi, field được phép và quyền nghiệp vụ vẫn phải được kiểm tra.

**9. Prototype pollution thường phát sinh ở bước nào?**

Thường ở bước merge/assign object không tin cậy vào object khác hoặc thư viện xử lý key đặc biệt không an toàn; JSON.parse đơn thuần không tự thay prototype chỉ vì key __proto__ xuất hiện.

**10. Khi nào dùng application/problem+json?**

Khi API trả Problem Details theo RFC 9457 để mô tả lỗi HTTP bằng JSON có cấu trúc.

## Ghi nhớ

`application/json` khai báo body là JSON data, còn `Content-Type`, `Accept` và `Content-Encoding` có nhiệm vụ riêng. Dùng UTF-8, parser chuẩn, schema validation và MIME chính xác; kết hợp nosniff với CORS, CSRF, CSP, authorization và cache policy phù hợp. JSON hợp lệ vẫn là input không tin cậy cho đến khi được kiểm tra theo domain và quyền truy cập.

## Tài liệu tham khảo

- [RFC 8259: The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html)
- [RFC 9110: HTTP Semantics — Content-Type and Accept](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 6839: Additional Media Type Structured Syntax Suffixes](https://www.rfc-editor.org/rfc/rfc6839.html)
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [Fetch Standard](https://fetch.spec.whatwg.org/)
- [MDN: Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type)
- [MDN: X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options)
- [OWASP: Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP: DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
- [OWASP: Prototype Pollution Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Prototype_Pollution_Prevention_Cheat_Sheet.html)
