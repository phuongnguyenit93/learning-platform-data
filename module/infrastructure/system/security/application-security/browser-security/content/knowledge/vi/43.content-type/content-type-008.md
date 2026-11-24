# Type confusion: khi dữ liệu bị hiểu thành một kiểu khác với kiểu đã được kiểm tra

> **Chương:** Content type  
> **Học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy, CORS và các cơ chế cách ly; thực hành phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

**Type confusion** trong ứng dụng web xảy ra khi một thành phần kiểm tra hoặc giả định dữ liệu thuộc một kiểu, nhưng thành phần tiếp theo lại diễn giải dữ liệu đó theo một kiểu khác. Một chuỗi được xem như văn bản có thể bị đưa vào HTML parser; một URL được kiểm tra như đường dẫn có thể mang scheme thực thi; một trường JSON có giá trị chuỗi có thể bị coi là boolean; một file được xem là ảnh theo phần mở rộng có thể thực tế chứa HTML hoặc nội dung chủ động.

Lỗi thường xuất hiện ở ranh giới giữa các tầng: browser, HTTP, JavaScript, DOM, API, thư viện và server. Mỗi tầng có quy tắc diễn giải riêng. Nếu ứng dụng chỉ xác thực biểu diễn ban đầu mà không kiểm tra kiểu và ngữ cảnh ở nơi sử dụng, attacker có thể khiến cùng một dữ liệu vượt qua kiểm tra rồi được xử lý theo cách nguy hiểm.

Bài này xây dựng cách nhận diện type confusion trong trình duyệt và ứng dụng web. Trọng tâm gồm ép kiểu JavaScript, JSON và schema validation, HTML/URL sinks, MIME và file upload, postMessage, Trusted Types, cùng một lab Node.js hai origin để quan sát sai lệch kiểu và cách phòng vệ.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa type confusion và xác định ranh giới nơi dữ liệu bị diễn giải lại.
2. Phân biệt kiểu JavaScript, kiểu dữ liệu trên wire, MIME type và trusted type.
3. Nhận diện rủi ro từ truthiness, implicit coercion, loose equality và kiểm tra typeof chưa đầy đủ.
4. Xác thực cấu trúc và kiểu runtime sau JSON.parse().
5. Phân biệt plain text với HTML và chọn DOM sink phù hợp.
6. Parse URL bằng URL API, kiểm tra scheme và origin bằng allowlist.
7. Hiểu MIME/content-type confusion, browser sniffing và phạm vi của nosniff.
8. Xác thực file upload bằng nhiều lớp thay vì tin filename hoặc Content-Type do client gửi.
9. Kiểm tra origin, source và schema của message nhận qua postMessage.
10. Dùng Trusted Types và CSP như lớp bảo vệ bổ sung cho DOM injection sinks.
11. Thiết kế API contract và test để phát hiện type confusion trước khi release.
12. Thực hành bằng lab Node.js với JSON type mismatch, script MIME mismatch và message cross-origin.

## 1. Type confusion là gì?

### 1.1 Kiểu dữ liệu và cách diễn giải

Một giá trị có thể đi qua nhiều tầng trước khi tạo ra hành vi:

~~~text
Input không tin cậy
       |
       v
HTTP bytes / JSON / form / file
       |
       v
Parser tạo ra giá trị
       |
       v
Validation kiểm tra giả định về kiểu
       |
       v
Chuyển đổi / serialize / template
       |
       v
Browser hoặc thư viện diễn giải theo ngữ cảnh mới
       |
       v
DOM / URL / script / file parser / quyền nghiệp vụ
~~~

Type confusion xuất hiện khi giả định ở một bước không còn đúng ở bước sau. Ví dụ:

- Server kiểm tra chuỗi có vẻ là ảnh, nhưng browser lại xử lý response như HTML.
- Code kiểm tra trường isAdmin bằng truthiness, nhưng JSON cung cấp chuỗi "false".
- Ứng dụng kiểm tra URL bắt đầu bằng https, nhưng giá trị thực được parse thành một URL khác hoặc chứa thông tin đánh lừa.
- Parent nhận message và giả định event.data luôn là object có trường height là number.
- Một chuỗi được xác thực như plain text nhưng lại được gán vào innerHTML.

### 1.2 Type confusion khác với lỗi định dạng thông thường

Một dữ liệu sai định dạng thường khiến parser từ chối hoặc ứng dụng báo lỗi. Type confusion nguy hiểm hơn khi dữ liệu vẫn được chấp nhận nhưng được hiểu theo cách khác với ý định bảo mật.

Ví dụ:

~~~js
const isAdmin = Boolean(payload.isAdmin);
~~~

Nếu payload là:

~~~json
{"isAdmin":"false"}
~~~

Kết quả Boolean("false") là true vì mọi chuỗi không rỗng đều truthy. Ứng dụng có thể cấp quyền admin dù API gửi chuỗi biểu diễn false.

Cách sửa là kiểm tra kiểu thực tế:

~~~js
if (typeof payload.isAdmin !== 'boolean') {
  throw new TypeError('isAdmin phải là boolean');
}

const isAdmin = payload.isAdmin;
~~~

Không tự chuyển đổi dữ liệu đầu vào thành kiểu mong muốn nếu chưa xác định quy tắc chuyển đổi an toàn.

### 1.3 Các ranh giới thường gây nhầm kiểu

| Ranh giới | Giả định sai thường gặp | Hậu quả có thể xảy ra |
|---|---|---|
| HTTP → browser | Content-Type luôn đúng | Browser diễn giải nội dung theo MIME khác |
| JSON → JavaScript | JSON.parse() đã xác thực schema | Sai kiểu, sai cấu trúc hoặc thiếu trường |
| String → DOM | Mọi chuỗi chỉ là văn bản | DOM XSS qua HTML sink |
| String → URL | Chuỗi URL đã được kiểm tra bằng regex | javascript:, origin lạ hoặc URL đánh lừa |
| Message → ứng dụng | event.data có đúng cấu trúc | Gọi nhầm chức năng hoặc thay đổi state ngoài ý muốn |
| File → parser | Extension hoặc MIME do client khai báo là thật | Upload file độc hại hoặc polyglot |
| TypeScript → runtime | Type annotation bảo đảm dữ liệu bên ngoài | Runtime vẫn nhận sai kiểu |

### 1.4 Type confusion không đồng nghĩa với confused deputy

Type confusion là lỗi diễn giải hoặc kiểm tra kiểu dữ liệu. Confused deputy là tình huống một thành phần có quyền bị lợi dụng để thực hiện hành động thay cho bên không có quyền. Hai khái niệm có thể kết hợp, ví dụ một API nhầm chuỗi "false" thành true rồi sử dụng quyền của server để truy cập dữ liệu, nhưng chúng không phải cùng một loại lỗi.

## 2. Type confusion trong JavaScript

### 2.1 Truthiness không phải validation

JavaScript chuyển giá trị thành boolean trong điều kiện if, toán tử !, &&, || và một số ngữ cảnh khác.

| Giá trị | Boolean(value) |
|---|---:|
| false | false |
| 0 | false |
| -0 | false |
| "" | false |
| null | false |
| undefined | false |
| NaN | false |
| "false" | true |
| "0" | true |
| " " | true |
| [] | true |
| {} | true |

Không dùng truthiness để xác thực trường có kiểu boolean:

~~~js
// Sai: chuỗi "false" vẫn được coi là true.
if (payload.enabled) {
  enableFeature();
}
~~~

~~~js
// Đúng: yêu cầu đúng kiểu boolean.
if (typeof payload.enabled !== 'boolean') {
  throw new TypeError('enabled phải là boolean');
}

if (payload.enabled === true) {
  enableFeature();
}
~~~

Nếu API cố ý gửi chuỗi "true"/"false", hãy parse bằng một hàm rõ ràng chỉ chấp nhận hai giá trị đã định nghĩa. Không dùng Boolean(value) cho mục đích này.

### 2.2 typeof có các trường hợp đặc biệt

typeof không phải schema validator:

~~~js
typeof null;       // "object"
typeof [];         // "object"
typeof {};         // "object"
typeof NaN;        // "number"
typeof 1n;         // "bigint"
typeof undefined;  // "undefined"
~~~

Nếu cần một plain object, không chỉ kiểm tra typeof value === 'object'. Cần loại null và array, sau đó xác định cấu trúc được chấp nhận.

~~~js
function isRecord(value) {
  return value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value);
}
~~~

Nếu nghiệp vụ yêu cầu object không có prototype hoặc chỉ có thuộc tính riêng, cần kiểm tra thêm. Không giả định mọi object đều là record JSON hợp lệ.

### 2.3 Loose equality có thể làm sai quyết định

Toán tử == thực hiện coercion trước khi so sánh:

~~~js
"0" == 0;       // true
"" == 0;        // true
false == 0;     // true
null == undefined; // true
[] == false;    // true
~~~

Với kiểm tra quyền, trạng thái, giá tiền hoặc identifier, ưu tiên strict equality:

~~~js
if (account.role === 'admin') {
  showAdminControls();
}
~~~

Strict equality vẫn không thay thế schema validation. Cần xác nhận role là chuỗi thuộc tập giá trị hợp lệ.

### 2.4 Chuyển đổi số có thể nhận đầu vào ngoài dự kiến

Các hàm chuyển đổi có semantics khác nhau:

~~~js
Number('12');       // 12
Number('12px');     // NaN
parseInt('12px', 10); // 12
Number('');         // 0
Number('   ');      // 0
~~~

Nếu API nhận số lượng, giới hạn hoặc tiền tệ, đừng dùng parseInt() rồi bỏ qua phần còn lại của chuỗi. Kiểm tra định dạng, miền giá trị và tính hữu hạn:

~~~js
function parseQuantity(value) {
  if (typeof value !== 'number' ||
      !Number.isSafeInteger(value) ||
      value < 0 ||
      value > 10000) {
    throw new TypeError('quantity không hợp lệ');
  }

  return value;
}
~~~

Nếu dữ liệu đến từ input HTML, giá trị thường là string. Hãy parse theo một grammar đã định nghĩa, rồi kiểm tra miền giá trị sau khi parse.

### 2.5 Không dùng String(value) để che dữ liệu sai kiểu

String() chuyển nhiều kiểu khác nhau thành chuỗi:

~~~js
String(null);       // "null"
String(undefined);  // "undefined"
String({});         // "[object Object]"
String([1, 2]);     // "1,2"
~~~

Điều này hữu ích cho hiển thị debug, nhưng không phải cách xác thực dữ liệu. Một object bất ngờ được ép thành chuỗi có thể che lỗi API contract hoặc làm hỏng URL, log, cache key và nội dung hiển thị.

### 2.6 Kiểm tra own property và object không tin cậy

Không giả định trường tồn tại chỉ vì truy cập không ném lỗi:

~~~js
const role = payload.role;
~~~

Nếu cần trường bắt buộc, kiểm tra nó có thực sự là own property:

~~~js
if (!Object.prototype.hasOwnProperty.call(payload, 'role')) {
  throw new TypeError('Thiếu trường role');
}
~~~

Với object lồng nhau, kiểm tra từng cấp trước khi truy cập. Tránh deep merge dữ liệu không tin cậy vào object cấu hình có quyền hoặc prototype đặc biệt. Dùng schema allowlist và chỉ copy các trường được phép.

## 3. JSON là dữ liệu, không phải schema

### 3.1 JSON.parse() chỉ parse cú pháp

JSON.parse() xác nhận chuỗi có cú pháp JSON hợp lệ và tạo ra JavaScript value. Nó không đảm bảo:

- Giá trị gốc là object thay vì array, string, number, boolean hoặc null.
- Trường bắt buộc tồn tại.
- Kiểu của từng trường đúng với contract.
- Giá trị nằm trong miền nghiệp vụ.
- Người gửi có quyền thực hiện hành động.
- Nội dung string an toàn khi đưa vào HTML, URL hoặc SQL.

Ví dụ JSON hợp lệ nhưng không phải object:

~~~js
JSON.parse('null');
JSON.parse('"admin"');
JSON.parse('false');
JSON.parse('[1, 2, 3]');
~~~

Vì vậy, luôn validate runtime shape sau parse.

### 3.2 Xác thực schema bằng allowlist

~~~js
function parseAccountPayload(value) {
  if (!isRecord(value)) {
    throw new TypeError('Payload phải là object');
  }

  const allowedRoles = new Set(['user', 'admin', 'support']);

  if (typeof value.id !== 'string' || value.id.length < 1) {
    throw new TypeError('id không hợp lệ');
  }

  if (typeof value.role !== 'string' ||
      !allowedRoles.has(value.role)) {
    throw new TypeError('role không hợp lệ');
  }

  if (typeof value.enabled !== 'boolean') {
    throw new TypeError('enabled phải là boolean');
  }

  return {
    id: value.id,
    role: value.role,
    enabled: value.enabled
  };
}
~~~

Đoạn code tạo object mới chỉ chứa trường được phép. Cách này giúp giảm nguy cơ dữ liệu thừa hoặc trường không mong muốn lọt vào phần logic nhạy cảm.

### 3.3 Không tin kiểu từ TypeScript ở ranh giới runtime

TypeScript interface và type annotation được loại bỏ khi compile. Chúng giúp phát hiện lỗi trong code đã được type-check, nhưng không xác thực JSON từ network, localStorage, postMessage, file hoặc JavaScript bên thứ ba.

~~~ts
type Account = {
  id: string;
  role: 'user' | 'admin';
  enabled: boolean;
};

const account = await response.json() as Account;
~~~

Ép kiểu bằng as Account không kiểm tra dữ liệu. Hãy dùng runtime validator hoặc tự viết parser có kiểm tra. Sau khi parser trả về kiểu đã xác nhận, phần còn lại của ứng dụng mới nên sử dụng kiểu TypeScript đó.

### 3.4 Phân biệt parse, validate và authorize

Ba bước này có mục đích khác nhau:

1. **Parse:** chuyển bytes/string thành cấu trúc dữ liệu.
2. **Validate:** kiểm tra kiểu, trường, định dạng và miền giá trị.
3. **Authorize:** xác định principal hiện tại có quyền thực hiện hành động trên tài nguyên hay không.

Một payload hợp lệ với role "admin" không chứng minh người gửi là admin. Server phải lấy danh tính từ session/token đã xác minh và tự kiểm tra quyền ở phía server.

## 4. String và HTML: type confusion tại DOM sink

### 4.1 Plain text và markup là hai ngữ cảnh khác nhau

Một chuỗi có thể chứa ký tự HTML:

~~~js
const comment = '<img src=x onerror=alert(1)>';
~~~

Nếu mục đích là hiển thị nguyên văn, dữ liệu phải được xử lý như text:

~~~js
commentElement.textContent = comment;
~~~

Không đưa chuỗi không tin cậy vào HTML parser:

~~~js
// Nguy hiểm với dữ liệu không tin cậy.
commentElement.innerHTML = comment;
~~~

innerHTML diễn giải chuỗi như markup. Nếu attacker kiểm soát chuỗi, họ có thể chèn element, attribute hoặc URL nguy hiểm và tạo DOM XSS.

### 4.2 Chọn sink theo kiểu nội dung

| Ý định | API phù hợp | Lưu ý |
|---|---|---|
| Hiển thị văn bản | textContent, createTextNode | Không parse HTML |
| Cập nhật giá trị input | value | Vẫn validate nghiệp vụ |
| Thêm text vào vị trí | insertAdjacentText | Xử lý như text |
| Tạo element cố định | createElement với tên tag hằng/allowlist | Không lấy tên tag tùy ý từ input |
| Gán HTML rich text | Sanitizer chuyên dụng rồi mới tạo DOM | Không chỉ escape bằng regex |
| Gán URL | URL parser và allowlist scheme/origin | Kiểm tra trước khi gán href/src |
| Gán event handler | addEventListener với function cố định | Không gán chuỗi vào onclick |

Không có một phép encode duy nhất phù hợp với mọi context. HTML text, HTML attribute, JavaScript string, CSS và URL có grammar khác nhau.

### 4.3 DOMParser không phải sanitizer

DOMParser.parseFromString() có thể tạo một document từ HTML string, nhưng việc parse không biến nội dung thành đáng tin. Khi node được đưa vào document đang hoạt động, event handler, URL và các phần tử có khả năng tải tài nguyên vẫn cần được kiểm soát.

Nếu chỉ cần hiển thị nội dung, dùng textContent. Nếu cần rich HTML, sanitize bằng thư viện được duy trì, cấu hình allowlist và tiếp tục kiểm soát URL/attribute trước khi chèn.

### 4.4 Trusted Types giúp giữ ranh giới kiểu ở DOM sink

Trusted Types cho phép browser phân biệt chuỗi thông thường với giá trị đã qua một policy được ứng dụng định nghĩa đối với các injection sink được hỗ trợ.

Có thể bật enforcement bằng CSP:

~~~http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-html
~~~

Ví dụ tạo policy sau khi sanitize:

~~~js
const htmlPolicy = trustedTypes.createPolicy('app-html', {
  createHTML(input) {
    return DOMPurify.sanitize(input, {
      USE_PROFILES: { html: true }
    });
  }
});

target.innerHTML = htmlPolicy.createHTML(untrustedHtml);
~~~

Trusted Types không tự sanitize dữ liệu. Policy quá rộng hoặc trả nguyên input sẽ làm mất ý nghĩa bảo vệ. Chỉ tạo policy tại module được kiểm soát, dùng sanitizer phù hợp và giới hạn tên policy bằng directive trusted-types.

Hỗ trợ Trusted Types khác nhau theo browser. Với browser không có enforcement native, vẫn phải dùng safe sink, sanitizer và test tương thích.

## 5. String và URL: kiểm tra theo cấu trúc, không theo tiền tố

### 5.1 Vì sao kiểm tra chuỗi bằng startsWith() không đủ?

Ví dụ sau có thể bị vượt qua bởi nhiều dạng URL:

~~~js
if (input.startsWith('https://trusted.example')) {
  location.href = input;
}
~~~

Chuỗi có thể chứa hostname đánh lừa, userinfo, port, ký tự mã hóa hoặc scheme khác. URL cần được parse bằng parser của browser rồi kiểm tra từng thành phần.

### 5.2 Dùng URL API và allowlist

~~~js
function parseAllowedNavigation(raw) {
  if (typeof raw !== 'string') {
    throw new TypeError('URL phải là chuỗi');
  }

  const url = new URL(raw, window.location.origin);

  const allowedOrigins = new Set([
    window.location.origin,
    'https://docs.example.net'
  ]);

  if (url.protocol !== 'https:') {
    throw new TypeError('Chỉ cho phép HTTPS');
  }

  if (!allowedOrigins.has(url.origin)) {
    throw new TypeError('Origin không nằm trong allowlist');
  }

  if (url.username || url.password) {
    throw new TypeError('Không chấp nhận URL chứa userinfo');
  }

  return url;
}
~~~

URL constructor chuẩn hóa URL và cung cấp protocol, hostname, port, origin, username và password. Sau khi parse, kiểm tra chính xác scheme và origin cần cho nghiệp vụ.

Nếu cho phép relative URL, truyền base URL rõ ràng. Nếu ứng dụng chỉ chấp nhận một hostname, kiểm tra url.hostname bằng allowlist thay vì so sánh substring.

### 5.3 Scheme phải được cho phép theo mục đích

Không cho phép mọi scheme. Các scheme có ý nghĩa khác nhau:

- https: thường phù hợp cho navigation và resource từ web.
- http: có thể tạo mixed content hoặc điều hướng không an toàn.
- javascript: có thể thực thi code trong một số navigation context.
- data: có thể nhúng nội dung trực tiếp và có quy tắc origin riêng.
- blob: tham chiếu dữ liệu được tạo trong browser và có lifetime riêng.
- file: truy cập tài nguyên cục bộ theo quy tắc browser/OS.

Nếu tính năng chỉ cần liên kết web, allowlist https:. Nếu cần mailto:, xử lý như một loại riêng. Không tự động chấp nhận data:, javascript: hoặc file: vì URL đã parse thành công.

### 5.4 Kiểm tra URL không thay thế authorization

Một URL thuộc allowlist chỉ nói rằng đích đến phù hợp với chính sách navigation. Server tại đích vẫn phải kiểm tra quyền truy cập. Đừng dùng việc URL cùng origin làm bằng chứng rằng người dùng được phép đọc hoặc sửa tài nguyên.

## 6. MIME và Content-Type confusion

### 6.1 Content-Type là metadata, không phải bằng chứng nội dung

HTTP Content-Type mô tả MIME type mà server khai báo cho representation. Browser và các parser sử dụng thông tin này cùng request context để quyết định cách xử lý response.

Một file có thể bị khai báo sai:

~~~http
Content-Type: text/plain
~~~

nhưng body lại chứa HTML hoặc JavaScript. Tùy context và thuật toán sniffing, browser có thể nhận diện nội dung khác với MIME server khai báo. Hành vi sniffing phụ thuộc loại request; không phải mọi response đều được xử lý theo cùng một thuật toán.

### 6.2 Browser có thể diễn giải cùng bytes theo destination

Một response được tải như navigation, script, stylesheet, image hoặc download có các quy tắc xử lý khác nhau. Ví dụ, nội dung có vẻ là HTML được nhúng vào context script không nhất thiết được xử lý như một trang HTML. Cần kiểm tra MIME theo destination thay vì chỉ nhìn tên file.

### 6.3 X-Content-Type-Options: nosniff

Header:

~~~http
X-Content-Type-Options: nosniff
~~~

Trong các kiểm tra MIME quan trọng của browser, nosniff ngăn tải script nếu MIME không phải JavaScript MIME hợp lệ và ngăn áp dụng stylesheet nếu MIME không phải text/css. Không mô tả nosniff như một nút tắt toàn bộ MIME sniffing cho mọi destination.

Hãy gửi Content-Type chính xác cho từng resource và thêm nosniff như lớp phòng vệ. Header không làm một file độc hại trở nên an toàn và không thay thế cô lập nội dung upload.

### 6.4 Content-Type không giống kiểu dữ liệu trong JavaScript

Một response có:

~~~http
Content-Type: application/json
~~~

vẫn có thể chứa JSON với kiểu trường sai:

~~~json
{"enabled":"false","quota":"100"}
~~~

MIME type đúng không chứng minh schema đúng. Browser parse JSON thành JavaScript value; ứng dụng phải kiểm tra kiểu runtime như đã trình bày ở phần JSON.

Ngược lại, JSON có schema đúng nhưng server gửi Content-Type sai có thể làm client, proxy hoặc browser xử lý không đúng. Cần kiểm tra cả representation và schema.

### 6.5 Đừng dùng client MIME làm response MIME

Khi người dùng upload file, request Content-Type và File.type do client cung cấp đều có thể bị giả mạo. Server phải xác định loại file theo allowlist nghiệp vụ, kiểm tra extension sau khi chuẩn hóa tên, kiểm tra signature và dùng parser phù hợp.

Khi phục vụ file người dùng, ưu tiên host/origin riêng cho nội dung upload, đặt Content-Type chính xác, X-Content-Type-Options: nosniff và Content-Disposition: attachment nếu không cần hiển thị inline. Với file cần preview, dùng quy trình chuyển đổi/scan và môi trường hiển thị cô lập.

## 7. File upload và parser confusion

### 7.1 Ba loại metadata không thể tin riêng lẻ

| Thành phần | Nguồn | Vì sao không đủ |
|---|---|---|
| Phần mở rộng filename | Người dùng hoặc client | Có thể đổi tên, double extension, ký tự Unicode hoặc encoding |
| File.type / Content-Type request | Client | Có thể khai báo tùy ý |
| Magic bytes/signature | Nội dung file | Có thể bị giả mạo hoặc file polyglot chứa nhiều cách diễn giải |

Dùng nhiều lớp xác minh, nhưng không coi một lớp là bằng chứng tuyệt đối.

### 7.2 Allowlist theo nghiệp vụ

Nếu chức năng chỉ nhận ảnh avatar, chỉ cho phép định dạng thực sự cần như JPEG, PNG hoặc WebP. Giới hạn kích thước, kích thước pixel, số frame và metadata. Giải mã rồi encode lại bằng thư viện ảnh cập nhật có thể giảm nội dung phụ, nhưng bản thân image parser cũng phải được cập nhật và giới hạn tài nguyên.

### 7.3 Tránh phục vụ file upload từ origin ứng dụng

Nội dung do người dùng upload nên được phục vụ từ một site riêng, tốt nhất là một registrable domain khác, không có cookie phiên của ứng dụng. Nếu phải dùng subdomain, dùng cookie host-only hoặc prefix __Host- cho session cookie và không đặt Domain ở parent domain để chia sẻ session với host upload.

Nếu cần xem trước, dùng response có MIME chính xác, sandbox/iframe phù hợp và Content-Disposition theo mục đích. Với file không cần render inline, dùng attachment. Đừng đưa file HTML/SVG không tin cậy vào DOM của origin ứng dụng.

### 7.4 Polyglot file

Polyglot là file có thể được diễn giải theo nhiều định dạng hoặc parser. Một file có header giống ảnh vẫn có thể chứa nội dung phụ mà parser khác nhận diện. Vì vậy, kiểm tra signature đơn lẻ không đủ; cần parse bằng thư viện chuyên dụng, kiểm tra cấu trúc, giới hạn tài nguyên và chuyển đổi sang định dạng được phép khi phù hợp.

## 8. postMessage và structured clone: message vẫn là input không tin cậy

### 8.1 event.data không có schema bảo đảm

postMessage truyền dữ liệu giữa browsing contexts. Structured clone hỗ trợ nhiều kiểu dữ liệu như object, array, string, number, ArrayBuffer, Map và một số đối tượng khác. Việc browser clone được dữ liệu không có nghĩa dữ liệu đó đúng với contract của ứng dụng.

Không giả định event.data luôn là object, luôn có trường type hoặc các trường số thực sự là number.

### 8.2 Kiểm tra origin, source và schema

~~~js
const expectedOrigin = 'https://widget.example.net';
const frame = document.querySelector('#widget');

window.addEventListener('message', event => {
  if (event.origin !== expectedOrigin) return;
  if (event.source !== frame.contentWindow) return;

  const data = event.data;

  if (
    data === null ||
    typeof data !== 'object' ||
    Array.isArray(data)
  ) {
    return;
  }

  if (data.type !== 'resize') return;

  if (
    typeof data.height !== 'number' ||
    !Number.isInteger(data.height) ||
    data.height < 0 ||
    data.height > 2000
  ) {
    return;
  }

  frame.style.height = data.height + 'px';
});
~~~

Origin xác minh nguồn gửi theo scheme/host/port. Source giúp phân biệt cửa sổ cụ thể khi có nhiều frame cùng origin. Schema validation xác minh nội dung message. Ba bước bổ sung cho nhau.

### 8.3 Gửi message với targetOrigin cụ thể

~~~js
frame.contentWindow.postMessage(
  { type: 'resize', height: 480 },
  'https://widget.example.net'
);
~~~

Không dùng dấu * khi biết chính xác origin đích. Nếu gửi message tới opaque origin và buộc phải dùng *, dữ liệu gửi phải được xem xét như công khai và không chứa secret. Phía nhận vẫn cần kiểm tra origin/source theo thiết kế.

### 8.4 Kiểm tra kiểu trước khi thay đổi state

Đừng chuyển một chuỗi thành số chỉ vì Number() có thể parse được. Nếu contract quy định height là number, hãy từ chối chuỗi "480". Nếu contract cho phép chuỗi số, định nghĩa grammar và giới hạn chuyển đổi rõ ràng.

## 9. API contract, serialization và các lớp bảo vệ

### 9.1 Định nghĩa contract ở cả client và server

Mỗi API nên mô tả:

- Kiểu của từng field.
- Field bắt buộc và tùy chọn.
- Miền giá trị, độ dài và precision.
- Enum/allowlist.
- Hành vi với null, missing và empty string.
- Quy tắc versioning.
- Cách xử lý field không nhận diện.

Server là nơi thực thi validation và authorization cuối cùng. Client validation cải thiện UX và giảm lỗi, nhưng không phải ranh giới bảo mật.

### 9.2 Không trộn null, missing và empty

Các giá trị sau không tương đương:

~~~js
const a = {};
const b = { name: undefined };
const c = { name: null };
const d = { name: '' };

Object.hasOwn(a, 'name'); // false
Object.hasOwn(b, 'name'); // true
Object.hasOwn(c, 'name'); // true
Object.hasOwn(d, 'name'); // true
~~~

API phải quy định rõ trường hợp nào có nghĩa là không thay đổi, xóa giá trị hoặc đặt chuỗi rỗng. Với PATCH, nhầm lẫn giữa missing và null có thể khiến ứng dụng vô tình xóa hoặc giữ lại dữ liệu.

### 9.3 Tránh mass assignment

Không đưa toàn bộ payload vào model nhạy cảm:

~~~js
// Nguy hiểm nếu payload chứa role, ownerId hoặc isVerified.
Object.assign(userRecord, payload);
~~~

Chọn các trường cho phép:

~~~js
const update = {
  displayName: validated.displayName,
  locale: validated.locale
};

Object.assign(userRecord, update);
~~~

Các trường quyền như role, ownerId, balance, isAdmin hoặc isVerified cần luồng nghiệp vụ và authorization riêng.

### 9.4 Serialization có thể thay đổi kiểu hoặc làm mất thông tin

JSON không biểu diễn trực tiếp undefined, BigInt, function, symbol hoặc object graph có vòng lặp. JSON.stringify() có thể bỏ trường undefined trong object, biến undefined trong array thành null hoặc ném lỗi với BigInt/circular reference.

Không dựa vào round-trip JSON để giữ nguyên mọi kiểu. Nếu cần biểu diễn date, bytes, tiền tệ hoặc identifier lớn, định nghĩa format rõ ràng, ví dụ ISO 8601 cho thời gian, chuỗi thập phân cho số nguyên lớn và schema version cho payload.

### 9.5 CSP và Trusted Types là lớp bổ sung

CSP có thể giới hạn nguồn script và Trusted Types có thể chặn string đi vào một số DOM injection sinks. Chúng không thay thế:

- Runtime schema validation.
- URL allowlist.
- MIME chính xác.
- File upload validation.
- postMessage origin/source checks.
- Server-side authorization.

Defense in depth hoạt động khi mỗi lớp bảo vệ một ranh giới khác nhau.

## 10. Quy trình tìm và sửa Type confusion

### 10.1 Theo dấu dữ liệu từ source tới sink

Với mỗi input, ghi lại:

1. Nguồn: URL, form, JSON, cookie, storage, postMessage, file hoặc API.
2. Parser: URL, JSON, multipart, image/document parser.
3. Kiểu runtime sau parse.
4. Validation: type, schema, allowlist và miền giá trị.
5. Chuyển đổi: String(), Number(), Boolean(), serialization hoặc template.
6. Sink: DOM, URL, script, CSS, file system hoặc logic quyền.
7. Hành vi khi dữ liệu sai: reject, fallback hay tiếp tục.

Nếu có bước chuyển đổi sau validation, kiểm tra xem conversion có làm mất giả định bảo mật không.

### 10.2 Tìm các mẫu code rủi ro

Tìm trong source:

~~~bash
rg -n "innerHTML|outerHTML|insertAdjacentHTML|document.write|eval|new Function" src
rg -n "postMessage|addEventListener\\(['\"]message" src
rg -n "Boolean\\(|parseInt\\(|Number\\(|==[^=]" src
rg -n "Content-Type|file\\.type|filename|upload" src
~~~

Kết quả tìm kiếm chỉ là điểm bắt đầu. Một API như innerHTML có thể an toàn nếu input đã được sanitize đúng; một hàm Number() có thể hợp lệ nếu grammar đầu vào được xác định. Review data flow và sink thay vì chỉ đếm số lần xuất hiện.

### 10.3 Kiểm thử giá trị biên và kiểu bất thường

Với mỗi field, thử:

- Thiếu field.
- null.
- Boolean thay cho string hoặc number.
- String thay cho boolean hoặc number.
- Empty string và whitespace.
- Array thay cho object.
- Object thay cho primitive.
- Số âm, số quá lớn, NaN hoặc Infinity ở runtime.
- Chuỗi dài, Unicode và ký tự điều khiển.
- URL có scheme, userinfo, port hoặc origin ngoài allowlist.
- MIME không khớp body.
- Message từ origin/source không mong đợi.

Mục tiêu là xác nhận hệ thống từ chối dữ liệu sai kiểu tại đúng ranh giới và không âm thầm chuyển nó thành giá trị có quyền cao hơn.

## 11. Thực hành: Type confusion lab với Node.js và hai origin

Lab có:

- Ứng dụng tại localhost:3000.
- Widget cross-origin tại localhost:3001.
- API trả JSON với boolean được cố ý gửi dưới dạng string.
- Script có body JavaScript nhưng Content-Type sai và nosniff.
- postMessage gửi một message sai kiểu trước khi gửi message hợp lệ.

Lab chỉ dùng dữ liệu demo, không cấp quyền thật và không nhận file upload.

### 11.1 Cấu trúc thư mục

~~~text
type-confusion-lab/
  server.mjs
  public/
    index.html
    app.js
~~~

### 11.2 Tạo server.mjs

~~~js
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const appOrigin = 'http://localhost:3000';
const publicRoot = new URL('./public/', import.meta.url);

const appServer = createServer(async (req, res) => {
  const url = new URL(req.url || '/', appOrigin);

  if (url.pathname === '/api/mismatch') {
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff'
    });

    return res.end(JSON.stringify({
      enabled: 'false',
      quota: '10',
      role: 'user'
    }));
  }

  if (url.pathname === '/api/typed') {
    res.writeHead(200, {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff'
    });

    return res.end(JSON.stringify({
      enabled: false,
      quota: 10,
      role: 'user'
    }));
  }

  if (url.pathname === '/wrong-script') {
    res.writeHead(200, {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store'
    });

    return res.end(
      'window.typeConfusionScriptRan = true;'
    );
  }

  if (url.pathname === '/right-script') {
    res.writeHead(200, {
      'Content-Type': 'text/javascript; charset=utf-8',
      'X-Content-Type-Options': 'nosniff',
      'Cache-Control': 'no-store'
    });

    return res.end(
      'window.typeConfusionScriptRan = true;'
    );
  }

  if (url.pathname === '/app.js') {
    try {
      const body = await readFile(new URL('app.js', publicRoot));
      res.writeHead(200, {
        'Content-Type': 'text/javascript; charset=utf-8',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store'
      });
      return res.end(body);
    } catch {
      res.writeHead(500);
      return res.end('Cannot read app.js');
    }
  }

  if (url.pathname === '/') {
    try {
      const body = await readFile(new URL('index.html', publicRoot));
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store'
      });
      return res.end(body);
    } catch {
      res.writeHead(500);
      return res.end('Cannot read index.html');
    }
  }

  res.writeHead(404, {
    'Content-Type': 'text/plain; charset=utf-8',
    'X-Content-Type-Options': 'nosniff'
  });
  res.end('Not found');
});

const widgetServer = createServer((req, res) => {
  if (req.url !== '/widget') {
    res.writeHead(404);
    return res.end('Not found');
  }

  const html = [
    '<!doctype html>',
    '<html lang="vi">',
    '<head><meta charset="utf-8"><title>Widget origin</title></head>',
    '<body>',
    '<p>Widget origin localhost:3001</p>',
    '<script>',
    'const target = "http://localhost:3000";',
    'setTimeout(() => {',
    '  parent.postMessage({ type: "resize", height: "480" }, target);',
    '}, 150);',
    'setTimeout(() => {',
    '  parent.postMessage({ type: "resize", height: 320 }, target);',
    '}, 450);',
    '</script>',
    '</body></html>'
  ].join('\n');

  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  });
  res.end(html);
});

appServer.listen(3000, 'localhost', () => {
  console.log('App:    http://localhost:3000');
});

widgetServer.listen(3001, 'localhost', () => {
  console.log('Widget: http://localhost:3001/widget');
});
~~~

### 11.3 Tạo public/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Type confusion lab</title>
  <script src="/app.js" defer></script>
</head>
<body>
  <main>
    <h1>Type confusion lab</h1>

    <section>
      <h2>JSON runtime types</h2>
      <button id="load-mismatch" type="button">Đọc JSON sai kiểu</button>
      <button id="load-typed" type="button">Đọc JSON đúng kiểu</button>
      <pre id="json-result">Chưa có dữ liệu.</pre>
    </section>

    <section>
      <h2>DOM sink</h2>
      <p>Chuỗi demo được hiển thị như văn bản:</p>
      <pre id="text-output"></pre>
    </section>

    <section>
      <h2>MIME mismatch</h2>
      <button id="wrong-script" type="button">Tải script MIME sai</button>
      <button id="right-script" type="button">Tải script MIME đúng</button>
      <p id="script-result">Chưa tải script.</p>
    </section>

    <section>
      <h2>postMessage schema</h2>
      <p id="message-result">Đang chờ widget.</p>
      <iframe
        id="widget"
        data-src="http://localhost:3001/widget"
        title="Widget type confusion demo"></iframe>
    </section>

    <section>
      <h2>URL validation</h2>
      <button id="url-test" type="button">Thử URL hợp lệ và không hợp lệ</button>
      <pre id="url-result"></pre>
    </section>
  </main>
</body>
</html>
~~~

### 11.4 Tạo public/app.js

~~~js
const jsonResult = document.querySelector('#json-result');
const textOutput = document.querySelector('#text-output');
const scriptResult = document.querySelector('#script-result');
const messageResult = document.querySelector('#message-result');
const frame = document.querySelector('#widget');

function isRecord(value) {
  return value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value);
}

function validateFeaturePayload(value) {
  if (!isRecord(value)) {
    throw new TypeError('Payload phải là object');
  }

  if (typeof value.enabled !== 'boolean') {
    throw new TypeError('enabled phải là boolean');
  }

  if (
    typeof value.quota !== 'number' ||
    !Number.isSafeInteger(value.quota) ||
    value.quota < 0
  ) {
    throw new TypeError('quota phải là số nguyên không âm');
  }

  if (!['user', 'admin'].includes(value.role)) {
    throw new TypeError('role không hợp lệ');
  }

  return {
    enabled: value.enabled,
    quota: value.quota,
    role: value.role
  };
}

async function loadPayload(path) {
  const response = await fetch(path);

  if (!response.ok) {
    throw new Error('HTTP ' + response.status);
  }

  const raw = await response.json();

  // Minh họa lỗi: chuỗi "false" là truthy.
  const unsafeEnabled = Boolean(raw.enabled);

  try {
    const safe = validateFeaturePayload(raw);

    jsonResult.textContent = JSON.stringify({
      raw,
      unsafeEnabled,
      validated: safe,
      result: 'PASS'
    }, null, 2);
  } catch (error) {
    jsonResult.textContent = JSON.stringify({
      raw,
      unsafeEnabled,
      validation: 'REJECTED',
      reason: error.message
    }, null, 2);
  }
}

document.querySelector('#load-mismatch').addEventListener('click', () => {
  loadPayload('/api/mismatch');
});

document.querySelector('#load-typed').addEventListener('click', () => {
  loadPayload('/api/typed');
});

const untrustedText = '<img src=x onerror=alert(1)>';

textOutput.textContent = untrustedText;

function loadScript(path) {
  window.typeConfusionScriptRan = false;

  const script = document.createElement('script');
  script.src = path;

  script.onload = () => {
    scriptResult.textContent = window.typeConfusionScriptRan
      ? 'Script đã được browser thực thi.'
      : 'Script tải xong nhưng không đặt cờ demo.';
  };

  script.onerror = () => {
    scriptResult.textContent =
      'Browser từ chối script. Kiểm tra Content-Type và nosniff trong Console.';
  };

  document.head.append(script);
}

document.querySelector('#wrong-script').addEventListener('click', () => {
  loadScript('/wrong-script');
});

document.querySelector('#right-script').addEventListener('click', () => {
  loadScript('/right-script');
});

window.addEventListener('message', event => {
  if (event.origin !== 'http://localhost:3001') return;
  if (event.source !== frame.contentWindow) return;

  const data = event.data;

  if (!isRecord(data) || data.type !== 'resize') {
    messageResult.textContent = 'Message bị từ chối: schema không hợp lệ.';
    return;
  }

  if (
    typeof data.height !== 'number' ||
    !Number.isInteger(data.height) ||
    data.height < 0 ||
    data.height > 1000
  ) {
    messageResult.textContent =
      'Message bị từ chối: height phải là số nguyên từ 0 đến 1000.';
    return;
  }

  frame.style.height = data.height + 'px';
  messageResult.textContent = 'Đã nhận height hợp lệ: ' + data.height;
});

// Cài listener trước khi tải iframe để không bỏ lỡ message đầu tiên.
frame.src = frame.dataset.src;

function parseAllowedUrl(raw) {
  if (typeof raw !== 'string') {
    throw new TypeError('URL phải là chuỗi');
  }

  const url = new URL(raw, window.location.origin);

  const allowedOrigins = new Set([
    window.location.origin,
    'https://docs.example.net'
  ]);

  if (url.protocol !== 'https:' && url.origin !== window.location.origin) {
    throw new TypeError('Scheme không được phép');
  }

  if (!allowedOrigins.has(url.origin)) {
    throw new TypeError('Origin không nằm trong allowlist');
  }

  if (url.username || url.password) {
    throw new TypeError('URL không được chứa userinfo');
  }

  return url.href;
}

document.querySelector('#url-test').addEventListener('click', () => {
  const values = [
    '/account',
    'https://docs.example.net/guide',
    'javascript:alert(1)',
    'https://docs.example.net.attacker.invalid/'
  ];

  const results = values.map(value => {
    try {
      return { input: value, accepted: parseAllowedUrl(value) };
    } catch (error) {
      return { input: value, rejected: error.message };
    }
  });

  document.querySelector('#url-result').textContent =
    JSON.stringify(results, null, 2);
});
~~~

### 11.5 Chạy lab

Từ thư mục type-confusion-lab:

~~~bash
node server.mjs
~~~

Mở:

~~~text
http://localhost:3000
~~~

Không cần package ngoài. Hai port tạo hai origin khác nhau; localhost được browser coi là potentially trustworthy cho mục đích phát triển.

### 11.6 Thử JSON type mismatch

Bấm “Đọc JSON sai kiểu”.

Quan sát:

- API trả enabled là chuỗi "false".
- Boolean(raw.enabled) cho kết quả true.
- Runtime validator từ chối vì enabled không phải boolean và quota không phải number.

Bấm “Đọc JSON đúng kiểu”. Validator chấp nhận boolean false và number 10. Lab cho thấy parse JSON thành công không đồng nghĩa payload đúng schema.

### 11.7 Thử DOM sink

Phần DOM sink hiển thị chuỗi chứa markup bằng textContent. Browser hiển thị nguyên văn chuỗi và không tạo img element. Đối chiếu với ví dụ innerHTML ở phần 4; không chạy payload vào trang chính.

### 11.8 Thử MIME mismatch

Bấm “Tải script MIME sai”. Endpoint trả body JavaScript nhưng khai báo text/plain và X-Content-Type-Options: nosniff. Browser hiện đại phải từ chối script trong script destination do MIME không phải JavaScript MIME hợp lệ.

Bấm “Tải script MIME đúng”. Endpoint trả JavaScript MIME hợp lệ và script có thể chạy. Mở DevTools → Network để so sánh Content-Type và Console.

### 11.9 Thử postMessage type confusion

Widget ở port 3001 gửi trước message có height là chuỗi "480". Parent xác minh origin và source nhưng vẫn từ chối vì schema sai. Sau đó widget gửi height là number 320; parent chấp nhận và cập nhật chiều cao iframe.

Điều này cho thấy kiểm tra origin không thay thế validation event.data. Một origin đáng tin vẫn có thể gửi dữ liệu lỗi do bug hoặc phiên bản API không tương thích.

### 11.10 Dừng lab

Dừng Node server bằng Ctrl+C. Không có dữ liệu cá nhân hoặc quyền thật được sử dụng.

## 12. Chẩn đoán Type confusion

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Trạng thái "false" lại được coi là bật | Boolean() trên chuỗi không rỗng | Yêu cầu boolean runtime hoặc parse enum rõ ràng |
| API trả JSON hợp lệ nhưng UI lỗi | JSON.parse không kiểm tra schema | Runtime validate type, shape và range |
| Array lọt qua kiểm tra object | typeof [] là object | Dùng Array.isArray và kiểm tra record |
| null lọt vào nhánh object | typeof null là object | Loại null rõ ràng |
| URL kiểm tra prefix nhưng vẫn điều hướng sai | Regex/startsWith không parse URL | Dùng URL API và allowlist origin/scheme |
| Chuỗi hiển thị thành HTML | Dùng innerHTML cho plain text | Dùng textContent hoặc sanitizer cho rich HTML |
| Script bị browser chặn | MIME không phải JavaScript hoặc nosniff | Sửa Content-Type tại server |
| File ảnh upload chạy như nội dung chủ động | Tin extension/MIME do client gửi hoặc phục vụ cùng origin | Validate nhiều lớp, chuyển đổi file và dùng origin riêng |
| postMessage từ đúng origin vẫn gây lỗi | Không kiểm tra source hoặc schema | Kiểm tra origin, source và từng field |
| TypeScript không phát hiện payload sai | Type assertion không chạy ở runtime | Dùng runtime schema validation |
| PATCH vô tình xóa dữ liệu | Nhầm missing, undefined, null và empty string | Định nghĩa semantics và validate từng trường |
| Object config bị thay đổi ngoài ý muốn | Merge toàn bộ input không tin cậy | Allowlist field, tránh deep merge tùy tiện |

## 13. Ma trận kiểm thử Type confusion

| ID | Input | Kết quả cần xác nhận |
|---|---|---|
| T01 | enabled là boolean false | Được chấp nhận và giữ false |
| T02 | enabled là chuỗi "false" | Bị từ chối |
| T03 | quota là chuỗi "10" | Bị từ chối nếu contract yêu cầu number |
| T04 | quota âm hoặc vượt giới hạn | Bị từ chối |
| T05 | Payload là null | Bị từ chối trước khi đọc field |
| T06 | Payload là array | Bị từ chối nếu contract yêu cầu record |
| T07 | Payload thiếu role | Bị từ chối |
| T08 | role là giá trị ngoài enum | Bị từ chối |
| T09 | URL dùng javascript: | Bị từ chối |
| T10 | URL có hostname chứa chuỗi allowlist nhưng origin khác | Bị từ chối |
| T11 | HTML string hiển thị qua textContent | Hiển thị nguyên văn, không parse markup |
| T12 | HTML string đưa vào innerHTML | Review xác nhận chỉ dùng sau sanitizer phù hợp |
| T13 | Script JavaScript trả text/plain + nosniff | Browser chặn script load |
| T14 | Script JavaScript trả MIME hợp lệ | Browser có thể thực thi |
| T15 | postMessage từ origin ngoài allowlist | Bị bỏ qua |
| T16 | postMessage từ frame khác cùng origin | Bị từ chối nếu source không khớp |
| T17 | postMessage height là string | Bị từ chối |
| T18 | postMessage height là số âm hoặc quá lớn | Bị từ chối |
| T19 | File upload có MIME khai báo khác signature | Bị từ chối hoặc chuyển sang quy trình kiểm tra |
| T20 | PATCH thiếu field | Giữ nguyên theo semantics đã định nghĩa |
| T21 | PATCH field là null | Xử lý theo contract rõ ràng |
| T22 | JSON chứa trường quyền ngoài allowlist | Không merge vào model nhạy cảm |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Type confusion là gì?

**Đáp án:** Là lỗi khi dữ liệu được kiểm tra hoặc giả định thuộc một kiểu nhưng sau đó bị thành phần khác diễn giải theo kiểu/ngữ cảnh khác, dẫn đến hành vi ngoài dự kiến.

**Câu 2.** Vì sao chuỗi "false" là truthy?

**Đáp án:** Trong JavaScript mọi chuỗi không rỗng đều truthy. Boolean("false") trả true; phải kiểm tra typeof và giá trị boolean thật.

**Câu 3.** JSON.parse() có xác thực schema không?

**Đáp án:** Không. Nó chỉ parse cú pháp JSON và có thể trả object, array, string, number, boolean hoặc null.

**Câu 4.** Vì sao typeof value === 'object' chưa đủ?

**Đáp án:** null và array cũng có typeof là object. Cần loại null, dùng Array.isArray và kiểm tra cấu trúc record.

**Câu 5.** Vì sao innerHTML là sink nguy hiểm với plain string?

**Đáp án:** innerHTML chuyển chuỗi thành markup. Dữ liệu attacker kiểm soát có thể tạo element/attribute nguy hiểm và DOM XSS; dùng textContent nếu cần text.

**Câu 6.** Trusted Types có tự sanitize HTML không?

**Đáp án:** Không. Trusted Types buộc các sink được hỗ trợ nhận giá trị được tạo qua policy; policy phải thực hiện sanitize/validation đúng cách.

**Câu 7.** Vì sao không nên kiểm tra URL bằng startsWith()?

**Đáp án:** Chuỗi URL có thể có userinfo, port, scheme hoặc hostname đánh lừa. Parse bằng URL API rồi kiểm tra protocol và origin chính xác.

**Câu 8.** Content-Type upload do browser gửi có đáng tin không?

**Đáp án:** Không. Client có thể giả mạo MIME type; server cần allowlist, kiểm tra signature và parser phù hợp cùng giới hạn tài nguyên.

**Câu 9.** postMessage cần kiểm tra những gì?

**Đáp án:** event.origin, event.source và schema của event.data. Kiểm tra origin đơn lẻ không xác minh kiểu và nội dung message.

**Câu 10.** TypeScript assertion có xác thực JSON runtime không?

**Đáp án:** Không. Assertion bị loại bỏ khi compile; dữ liệu từ network cần runtime validation trước khi sử dụng.

## 15. Checklist phòng chống Type confusion

### Input và runtime type

- [ ] Xác định nguồn dữ liệu và parser của từng input.
- [ ] Không dùng truthiness làm validation cho boolean.
- [ ] Ưu tiên strict equality thay cho loose equality trong logic bảo mật.
- [ ] Phân biệt null, missing, undefined và empty string.
- [ ] Kiểm tra object, array và primitive rõ ràng.
- [ ] Kiểm tra miền số, độ dài string và enum.
- [ ] Runtime validate JSON, postMessage, storage và file metadata.
- [ ] Không xem TypeScript assertion là kiểm tra runtime.

### DOM, URL và browser

- [ ] Dùng textContent cho plain text.
- [ ] Không đưa dữ liệu không tin cậy vào innerHTML/document.write/eval.
- [ ] Nếu cần rich HTML, dùng sanitizer được duy trì và allowlist.
- [ ] Bật Trusted Types enforcement khi browser mục tiêu hỗ trợ.
- [ ] Parse URL bằng URL API.
- [ ] Allowlist scheme và origin; từ chối userinfo không cần thiết.
- [ ] Kiểm tra origin và source của postMessage.
- [ ] Validate schema của event.data trước khi thay đổi DOM/state.

### MIME, file và server

- [ ] Gửi Content-Type đúng cho từng resource.
- [ ] Bật X-Content-Type-Options: nosniff.
- [ ] Không tin filename, extension hoặc MIME do client gửi.
- [ ] Dùng allowlist định dạng và kiểm tra signature cùng parser.
- [ ] Giới hạn kích thước và tài nguyên khi parse file.
- [ ] Cô lập nội dung upload trên origin/site riêng.
- [ ] Dùng Content-Disposition phù hợp khi phục vụ file.
- [ ] Server validate schema và authorization cho mọi request.

### Kiểm thử và vận hành

- [ ] Test giá trị sai kiểu, null, array, missing và giá trị biên.
- [ ] Test URL scheme/origin và hostname đánh lừa.
- [ ] Test MIME/body mismatch với browser mục tiêu.
- [ ] Test message từ origin và source không mong đợi.
- [ ] Review mọi conversion sau bước validation.
- [ ] Log lỗi theo loại dữ liệu mà không ghi secret.
- [ ] Kiểm tra regression khi thay schema hoặc dependency.

**Ghi nhớ:** Type safety ở compile time không bảo vệ ranh giới dữ liệu runtime. Hãy xác thực đúng kiểu tại nơi dữ liệu đi vào, giữ nguyên ngữ nghĩa qua serialization, rồi chọn parser và sink phù hợp với mục đích sử dụng. Browser có thể áp dụng MIME sniffing, URL handling và DOM parsing theo quy tắc riêng; ứng dụng cần giữ rõ ranh giới giữa data, markup, URL và code.

## Tài liệu tham khảo

- [WHATWG — MIME Sniffing Standard](https://mimesniff.spec.whatwg.org/)
- [WHATWG — HTML Standard: DOM parsing and scripting](https://html.spec.whatwg.org/)
- [WHATWG — URL Standard](https://url.spec.whatwg.org/)
- [MDN — MIME type verification](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/MIME_types)
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [OWASP — DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html)
- [OWASP — HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [MDN — Trusted Types API](https://developer.mozilla.org/en-US/docs/Web/API/Trusted_Types_API)
- [MDN — URL API](https://developer.mozilla.org/en-US/docs/Web/API/URL)

