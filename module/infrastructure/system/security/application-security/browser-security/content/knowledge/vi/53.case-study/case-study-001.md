# CORS mở quá rộng

## Bối cảnh case study

Một ứng dụng quản lý tài khoản có API tại https://api.example.test. Frontend chính chạy tại https://app.example.test; người dùng đăng nhập bằng cookie phiên. Một nhóm tích hợp muốn cho phép nhiều frontend gọi API nên middleware CORS được viết theo hướng phản chiếu giá trị Origin trong request vào Access-Control-Allow-Origin. Middleware đồng thời bật Access-Control-Allow-Credentials: true.

Sau khi triển khai, một trang do bên ngoài kiểm soát có thể gửi request đến API bằng thông tin xác thực của nạn nhân và đọc response trong trình duyệt, nếu cookie được gửi theo chính sách SameSite và các điều kiện CORS khác được đáp ứng. API vốn yêu cầu đăng nhập, nhưng response lại được chia sẻ cho origin không đáng tin cậy.

Case study này phân tích một cấu hình CORS mở quá rộng, cách xác minh tác động, nguyên nhân, phương án khắc phục và tiêu chí đóng sự cố. Các domain .example.test là tên minh họa dành cho môi trường thử nghiệm.

## 1. Mục tiêu học tập

Sau case study, bạn có thể:

- Giải thích CORS kiểm soát quyền đọc response của JavaScript từ origin khác như thế nào.
- Phân biệt CORS với xác thực, phân quyền và phòng chống CSRF.
- Nhận diện lỗi phản chiếu Origin, wildcard, allowlist theo hậu tố và cho phép origin null.
- Đánh giá ảnh hưởng của Access-Control-Allow-Credentials, cookie SameSite và cache.
- Tái hiện lỗi an toàn trong staging, thu thập bằng chứng và đề xuất sửa lỗi.
- Xây dựng test hồi quy để ngăn cấu hình CORS mở rộng trở lại.

## 2. CORS kiểm soát điều gì?

Origin được xác định bởi bộ ba **scheme, host và port**. Ví dụ, ba địa chỉ sau là ba origin khác nhau:

| URL | Origin |
|---|---|
| https://app.example.test | https://app.example.test |
| http://app.example.test | http://app.example.test với scheme HTTP |
| https://app.example.test:8443 | https://app.example.test:8443 |

CORS (Cross-Origin Resource Sharing) là cơ chế mà máy chủ dùng response header để cho phép JavaScript ở origin khác đọc response. Trình duyệt thực thi cơ chế này. CORS không phải cơ chế xác thực người dùng và không tự quyết định người gọi có quyền thực hiện thao tác nghiệp vụ hay không.

Khi một trang ở origin khác gọi API:

1. Trình duyệt xác định request có thuộc trường hợp cần CORS hay không.
2. Với request đơn giản, trình duyệt có thể gửi request trước rồi kiểm tra response header để quyết định JavaScript có được đọc response.
3. Với request cần preflight, trình duyệt gửi request OPTIONS để hỏi máy chủ về method và header được phép. Nếu preflight không đạt, trình duyệt không gửi request thực tế.
4. Nếu response đáp ứng chính sách CORS, JavaScript có thể đọc response theo các giới hạn được công bố. Nếu không, JavaScript không được đọc response; request đơn giản vẫn có thể đã được máy chủ xử lý.

Điểm cuối rất quan trọng: CORS thường ngăn một origin trái phép **đọc** response. Nó không đảm bảo request không được gửi. Vì vậy, một endpoint thay đổi trạng thái vẫn cần phòng chống CSRF và kiểm tra quyền ở máy chủ.

### 2.1. Các header chính

| Header | Vai trò | Lưu ý bảo mật |
|---|---|---|
| Origin (request) | Cho biết origin khởi tạo request trong các trường hợp trình duyệt gửi header này | Máy chủ không được xem header do client gửi là bằng chứng xác thực; client ngoài trình duyệt có thể tự đặt header |
| Access-Control-Allow-Origin | Khai báo origin được phép đọc response | Dùng * cho tài nguyên công khai không dùng credentials; với credentials phải trả origin cụ thể |
| Access-Control-Allow-Credentials | Cho phép response được chia sẻ trong request có credentials | Giá trị hợp lệ là true; không được kết hợp với Access-Control-Allow-Origin: * cho request credentials mode include |
| Access-Control-Allow-Methods | Khai báo method được phép cho request cross-origin, đặc biệt trong preflight | Chỉ liệt kê method cần thiết |
| Access-Control-Allow-Headers | Khai báo request header không thuộc nhóm safelisted được phép | Chỉ cho phép header mà API thực sự cần; giá trị * không hoạt động như wildcard với request có credentials |
| Access-Control-Expose-Headers | Cho phép JavaScript đọc thêm response header | Không expose header chứa bí mật |
| Access-Control-Max-Age | Cho phép trình duyệt cache kết quả preflight trong một khoảng thời gian | Thời gian dài có thể làm thay đổi thời gian áp dụng cấu hình mới ở client |
| Vary: Origin | Báo cho cache rằng response thay đổi theo request header Origin | Cần khi response động phản chiếu một origin hợp lệ; không thay thế chính sách cache riêng tư |

### 2.2. Request đơn giản và preflight

Một request thường không cần preflight khi đáp ứng các điều kiện của CORS safelisted request, chẳng hạn method GET, HEAD hoặc POST và các request header/content type nằm trong danh sách an toàn. Một request dùng method PUT, DELETE hoặc header tùy chỉnh như X-CSRF-Token thường cần preflight.

Ví dụ request có preflight:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Một response preflight phù hợp với ví dụ này có thể là:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: PATCH
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Trình duyệt không gửi cookie hoặc credentials của request thực tế trong preflight. Sau khi preflight thành công, request thực tế mới được gửi theo credentials mode của nó. Máy chủ vẫn cần kiểm tra xác thực, CSRF và phân quyền trên request thực tế.

Với request có credentials, giá trị * trong Access-Control-Allow-Headers được xem như tên header literal thay vì cho phép mọi header. Hãy liệt kê chính xác các header cần dùng, chẳng hạn Content-Type và X-CSRF-Token.

### 2.3. Credentials và wildcard

Nếu JavaScript gọi fetch() với credentials: "include", trình duyệt có thể gửi cookie hoặc credentials phù hợp theo chính sách cookie và trình duyệt. Để JavaScript đọc response có credentials, máy chủ cần trả origin cụ thể và:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
~~~

Cấu hình sau không cho phép JavaScript đọc response credentialed trong trình duyệt tuân theo CORS:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Khi credentials mode là include, wildcard * không hợp lệ cho việc chia sẻ response credentialed. Tuy nhiên, không nên kết luận rằng cấu hình này loại bỏ mọi rủi ro: một request đơn giản vẫn có thể được gửi và gây tác động nếu endpoint thiếu CSRF protection. Hãy kiểm tra cả khả năng đọc response lẫn khả năng thực hiện thao tác.

Cookie còn chịu các thuộc tính SameSite, Secure, HttpOnly, domain và path. Origin và site là hai khái niệm khác nhau: hai subdomain HTTPS có thể là cross-origin nhưng vẫn same-site. Do đó, cookie SameSite=Lax hoặc Strict không phải lúc nào cũng ngăn request giữa các subdomain cùng site. Đánh giá đúng schemeful site và ngữ cảnh điều hướng/request thực tế.

## 3. Diễn biến sự cố

### 3.1. Bối cảnh hệ thống

Ứng dụng minh họa có các thành phần:

- Frontend chính: https://app.example.test.
- API tài khoản: https://api.example.test.
- Một số frontend đối tác chạy trên origin riêng.
- Người dùng đăng nhập bằng cookie phiên có Secure, HttpOnly; cấu hình SameSite được thiết lập theo nhu cầu sản phẩm.
- API trả dữ liệu hồ sơ và thông tin tài khoản sau khi xác thực phiên.

Để hỗ trợ tích hợp nhanh, middleware CORS ban đầu phản chiếu bất kỳ Origin nào được gửi lên. Khi request có header Origin, response đặt Access-Control-Allow-Origin bằng chính giá trị đó và bật Access-Control-Allow-Credentials: true. Không có allowlist tin cậy.

### 3.2. Cấu hình gây lỗi

Ví dụ pseudocode của middleware có lỗi:

~~~javascript
function permissiveCors(req, res, next) {
  const origin = req.headers.origin;

  if (origin) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");
    res.setHeader("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE");
    res.setHeader("Access-Control-Allow-Headers", "*");
  }

  next();
}
~~~

Đoạn mã này chỉ để minh họa lỗi. Nó tin mọi giá trị Origin, cấp quyền đọc response cho origin đó và cho phép credentials. Danh sách method rộng làm tăng bề mặt tích hợp; giá trị * trong Access-Control-Allow-Headers không trở thành wildcard hữu ích với request có credentials và có thể khiến người bảo trì hiểu sai policy.

Lỗi cốt lõi không nằm ở việc API có nhiều frontend hợp lệ. Lỗi nằm ở chỗ máy chủ không phân biệt origin nào được tin cậy trước khi cấp quyền chia sẻ response.

### 3.3. Luồng khai thác có điều kiện

Giả sử nạn nhân đang đăng nhập và truy cập một trang bên ngoài do kẻ tấn công kiểm soát. Trang đó gửi request đến API bằng credentials của trình duyệt. Nếu cookie được gửi trong ngữ cảnh request, API trả dữ liệu tài khoản và response phản chiếu origin của trang bên ngoài. Khi response cũng có Access-Control-Allow-Credentials: true, trình duyệt có thể cho JavaScript của trang đó đọc response.

Ví dụ minh họa trong một lab được phép kiểm thử:

~~~javascript
fetch("https://api.example.test/api/profile", {
  method: "GET",
  credentials: "include",
})
  .then((response) => {
    if (!response.ok) throw new Error("Request was rejected");
    return response.json();
  })
  .then((profile) => {
    // Trong lab, xác nhận response có thể đọc được.
    console.log("Profile response was readable", Object.keys(profile));
  })
  .catch(() => {
    console.log("Response could not be read");
  });
~~~

Đoạn mã chỉ minh họa việc kiểm tra khả năng đọc response trong môi trường thử nghiệm; không gửi dữ liệu ra ngoài hoặc thu thập thông tin tài khoản thật.

Điều kiện để đọc được response bao gồm:

1. Nạn nhân có phiên hợp lệ và request thực tế được gửi kèm credentials.
2. Cookie được gửi theo thuộc tính SameSite, Secure, domain/path và chính sách trình duyệt.
3. API chấp nhận request và trả dữ liệu theo phiên của nạn nhân.
4. Response CORS cho phép chính origin của trang gọi đọc response và cho phép credentials.
5. Không có lớp kiểm soát khác chặn request hoặc loại bỏ dữ liệu.

Nếu cookie cross-site bị chặn bởi SameSite hoặc chính sách cookie bên thứ ba, kịch bản có thể không đọc được dữ liệu theo cách này. Nhưng không nên dựa vào hành vi cookie đó làm biện pháp duy nhất: subdomain cùng site, trình duyệt khác nhau, cấu hình cookie khác hoặc credential khác có thể tạo điều kiện khác.

### 3.4. Điều gì xảy ra nếu chỉ dùng wildcard?

Một cấu hình Access-Control-Allow-Origin: * không cho phép JavaScript đọc response khi request dùng credentials mode include. Trình duyệt từ chối chia sẻ response credentialed. Dù vậy:

- Request đơn giản có thể đã đến API trước khi trình duyệt từ chối response.
- Nếu endpoint thay đổi trạng thái và thiếu CSRF protection, hành động vẫn có thể được thực hiện.
- Nếu API không yêu cầu credentials hoặc dữ liệu thực sự công khai, wildcard có thể hợp lệ.
- Nếu response dùng credentials nhưng wildcard, lỗi cấu hình vẫn cần sửa để tránh nhầm lẫn và tránh thay đổi sau này tạo điều kiện đọc dữ liệu.

Vì vậy, đánh giá phải kiểm tra request, response, cookie và kết quả nghiệp vụ, không chỉ nhìn một header.

## 4. Phát hiện và xác minh

### 4.1. Dấu hiệu ban đầu

Các tín hiệu có thể dẫn đến phát hiện:

- API trả Access-Control-Allow-Origin bằng các origin không nằm trong danh sách frontend được phê duyệt.
- Response có Access-Control-Allow-Credentials: true trên nhiều origin khác nhau.
- Middleware ghi nhận mọi origin nhưng không có sự kiện allow/deny hoặc danh sách policy.
- Báo cáo bảo mật cho thấy một origin bên ngoài có thể đọc endpoint tài khoản.
- Endpoint hồ sơ có request từ origin lạ và trả response thành công.

Một request có Origin lạ không tự chứng minh đã khai thác. Cần xác minh origin đó có đọc được response trong trình duyệt với phiên thử nghiệm và dữ liệu giả hay không.

### 4.2. Kiểm tra header bằng curl

Dùng dữ liệu giả và endpoint staging:

~~~bash
curl -i \
  -H 'Origin: https://untrusted.example.test' \
  https://api.example.test/api/profile
~~~

Kiểm tra:

- Access-Control-Allow-Origin có phản chiếu origin không tin cậy không.
- Access-Control-Allow-Credentials có xuất hiện không.
- Vary: Origin có được đặt khi response thay đổi theo Origin không.
- Có header cho phép method hoặc request header vượt quá nhu cầu không.

Lưu ý: curl không thực thi CORS. Nó chỉ hiển thị response của máy chủ. Kết quả có Access-Control-Allow-Origin không chứng minh trình duyệt cho phép JavaScript đọc response; cần kiểm thử bằng browser thật.

### 4.3. Kiểm tra preflight

Gửi request OPTIONS trong staging:

~~~bash
curl -i -X OPTIONS \
  -H 'Origin: https://untrusted.example.test' \
  -H 'Access-Control-Request-Method: PATCH' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token' \
  https://api.example.test/api/profile
~~~

Response cần được đánh giá theo origin, method và header được yêu cầu. Với origin không tin cậy, server không được trả bộ header CORS cho phép request đó. Với origin hợp lệ, chỉ trả method và header cần thiết.

Không dùng curl để kết luận browser có gửi request thực tế sau preflight hay không. Dùng DevTools Network để quan sát cả OPTIONS và request tiếp theo.

### 4.4. Kiểm thử bằng trình duyệt

Trong staging, tạo hai origin kiểm thử:

- Origin được phép: https://app.example.test.
- Origin không được phép: https://untrusted.example.test.

Dùng tài khoản thử nghiệm có dữ liệu giả. Từ mỗi origin, gọi endpoint với credentials: "include". Quan sát:

1. Request có được gửi không?
2. Cookie có được đính kèm không? DevTools có thể che hoặc giới hạn hiển thị một số chi tiết; không chụp lại giá trị cookie.
3. Có preflight không? Nếu có, response OPTIONS có cho phép origin, method và header không?
4. Request thực tế có được gửi và API trả status nào?
5. JavaScript có đọc được response body và header không?
6. API có thực hiện thay đổi trạng thái không?

Kết quả mong đợi: origin hợp lệ có thể đọc response theo hợp đồng tích hợp; origin không hợp lệ không thể đọc response. Endpoint thay đổi trạng thái vẫn từ chối request thiếu CSRF token hoặc không đáp ứng kiểm tra Origin/Referer theo thiết kế.

### 4.5. Kiểm tra các biến thể Origin nguy hiểm

Thử các trường hợp sau trong staging để xác nhận allowlist không bị vượt qua:

| Giá trị Origin | Lỗi cần tìm |
|---|---|
| https://untrusted.example.test | Origin bất kỳ bị phản chiếu |
| https://app.example.test.attacker.test | Kiểm tra hậu tố chuỗi thiếu ranh giới hostname |
| https://evil-app.example.test | Subdomain không được quản lý hoặc không đáng tin được cho phép nhầm |
| http://app.example.test | Cho phép nhầm scheme HTTP |
| https://app.example.test:8443 | Cho phép nhầm port |
| null | Cho phép opaque origin như sandboxed document ngoài dự kiến |
| Không có Origin | Middleware xử lý sai request không phải CORS hoặc client ngoài trình duyệt |

Allowlist phải so sánh origin đã chuẩn hóa theo scheme, hostname và port. Không dùng kiểm tra chuỗi kiểu endsWith("example.test") nếu không có ranh giới hostname rõ ràng; ngay cả khi kiểm tra đúng hậu tố, mọi subdomain được chấp nhận phải thuộc cùng mức tin cậy. Không cho phép null trừ khi có một trường hợp sử dụng cụ thể đã được phân tích và giới hạn.

## 5. Đánh giá tác động

Tác động phụ thuộc dữ liệu API, cách xác thực và cookie thực tế. Phân loại bằng chứng thành:

| Mức bằng chứng | Ví dụ | Cách kết luận |
|---|---|---|
| Cấu hình có nguy cơ | Origin bất kỳ được phản chiếu cùng credentials | Xác nhận lỗi cấu hình và khả năng mở quyền chia sẻ response |
| Có thể đọc trong lab | Origin không tin cậy đọc được dữ liệu giả bằng phiên thử nghiệm | Xác nhận đường khai thác có thể thực hiện trong điều kiện lab |
| Có request production | Log ghi nhận request từ origin lạ đến endpoint | Chỉ xác nhận request đã xảy ra; chưa đủ chứng minh response bị đọc |
| Có dấu hiệu truy cập dữ liệu | Log/API audit cho thấy response chứa dữ liệu hoặc endpoint trả thành công | Xác định loại dữ liệu và phạm vi; browser log phía server không chứng minh JavaScript đã đọc response |
| Có bằng chứng lạm dụng | Kết hợp nhiều nguồn cho thấy dữ liệu hoặc hành động bị truy cập trái phép | Xác nhận phạm vi đã chứng minh, đồng thời ghi rõ phần chưa xác định |

Cần trả lời:

- Endpoint nào trả dữ liệu cá nhân hoặc dữ liệu có quyền truy cập?
- API có cho phép origin không tin cậy đọc response với credentials không?
- Cookie nào được gửi trong ngữ cảnh cross-origin/cross-site? SameSite và browser policy có thay đổi theo trình duyệt không?
- Có endpoint thay đổi trạng thái nào bị ảnh hưởng bởi CSRF không?
- Có token nào được lưu trong response body hoặc header có thể đọc bởi JavaScript không?
- CDN hoặc reverse proxy có cache response theo Origin sai cách không?
- Có bao nhiêu origin và nhóm người dùng có khả năng bị ảnh hưởng?
- Log hiện có có đủ để xác định dữ liệu đã bị đọc hay không?

CORS thường không để lại bằng chứng phía máy chủ cho biết JavaScript của origin gọi đã đọc response. Máy chủ nhìn thấy request và response được gửi đi, nhưng quyết định cho phép JavaScript đọc là do trình duyệt thực thi. Vì vậy, nếu không có telemetry đáng tin cậy từ phía client, có thể chỉ xác định được mức phơi nhiễm tiềm năng chứ không thể khẳng định chính xác response đã bị đọc.

## 6. Nguyên nhân gốc và yếu tố góp phần

Ví dụ phân tích:

| Lớp | Phát hiện |
|---|---|
| Nguyên nhân trực tiếp | Middleware phản chiếu mọi giá trị Origin vào Access-Control-Allow-Origin |
| Quyền credentials | Middleware bật Access-Control-Allow-Credentials: true cho mọi origin được phản chiếu |
| Thiếu kiểm soát | Không có allowlist origin được phê duyệt và không có kiểm tra scheme/host/port |
| Thiếu kiểm thử | Browser integration test chỉ chạy từ frontend chính |
| Yếu tố góp phần | Tài liệu tích hợp mô tả CORS như cơ chế “cho phép frontend gọi API” nhưng không giải thích ranh giới đọc response và credentials |
| Khoảng trống giám sát | Không có dashboard về origin được cấp quyền hoặc cảnh báo khi origin lạ xuất hiện |
| Rủi ro cache | Response động theo Origin không có Vary: Origin ở một số đường phân phối |

Không kết luận rằng thiếu Vary: Origin là nguyên nhân duy nhất của việc lộ dữ liệu. Việc phản chiếu origin không kiểm soát và cho phép credentials mới là lỗi cấp quyền CORS trực tiếp. Thiếu Vary có thể khiến cache phân phối nhầm header/response giữa các origin, tùy cache key và cấu hình.

## 7. Phương án khắc phục

### 7.1. Xây dựng allowlist chính xác

Chỉ cho phép các origin cần thiết, được phê duyệt và có chủ sở hữu. Ví dụ:

- https://app.example.test
- https://partner-portal.example.test

Mỗi origin cần xác định môi trường, mục đích tích hợp, nhóm sở hữu và ngày rà soát. Không tự động tin tất cả subdomain hoặc origin chỉ vì chúng cùng domain gốc.

Không phản chiếu giá trị Origin nếu chưa kiểm tra allowlist. Không tạo wildcard credentials. Không chấp nhận origin null theo mặc định.

### 7.2. Cấu hình response theo origin hợp lệ

Pseudocode minh họa:

~~~javascript
const allowedOrigins = new Set([
  "https://app.example.test",
  "https://partner-portal.example.test",
]);

function corsForTrustedOrigins(req, res, next) {
  const origin = req.headers.origin;

  if (origin && allowedOrigins.has(origin)) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Access-Control-Allow-Credentials", "true");

    // Framework nên merge Vary thay vì ghi đè giá trị hiện có.
    res.vary("Origin");

    res.setHeader("Access-Control-Allow-Methods", "GET, POST");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token");
    res.setHeader("Access-Control-Expose-Headers", "X-Request-Id");
  }

  next();
}
~~~

Đây là ví dụ minh họa cho Express-style response API; cần điều chỉnh theo framework thực tế. Với request từ origin không được phép, không trả các header CORS cho phép. Việc không có header CORS không thay thế xác thực và phân quyền của endpoint.

### 7.3. Xử lý preflight có kiểm tra

Với OPTIONS, máy chủ phải kiểm tra origin, method và request header được yêu cầu trước khi trả response cho phép. Ví dụ luồng xử lý:

~~~javascript
function handlePreflight(req, res) {
  const origin = req.headers.origin;
  const requestedMethod = req.headers["access-control-request-method"];
  const requestedHeaders = (req.headers["access-control-request-headers"] || "")
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean);

  const allowedMethods = new Set(["GET", "POST", "PATCH"]);
  const allowedHeaders = new Set(["content-type", "x-csrf-token"]);

  if (!origin || !allowedOrigins.has(origin)) {
    return res.sendStatus(403);
  }

  if (!allowedMethods.has(requestedMethod)) {
    return res.sendStatus(403);
  }

  if (requestedHeaders.some((header) => !allowedHeaders.has(header))) {
    return res.sendStatus(403);
  }

  res.setHeader("Access-Control-Allow-Origin", origin);
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Methods", requestedMethod);
  res.setHeader("Access-Control-Allow-Headers", requestedHeaders.join(", "));
  res.vary("Origin");
  res.vary("Access-Control-Request-Method");
  res.vary("Access-Control-Request-Headers");

  return res.sendStatus(204);
}
~~~

Đây là pseudocode; hàm res.vary() và sendStatus() phụ thuộc framework. Cần kiểm tra method/header rỗng, định dạng sai, header trùng lặp và quy tắc xử lý OPTIONS trong framework. Không trả Access-Control-Allow-Methods: * hoặc Access-Control-Allow-Headers: * chỉ để tránh phải quản lý danh sách.

### 7.4. Giới hạn dữ liệu và credentials

- Chỉ bật Access-Control-Allow-Credentials: true khi frontend thực sự cần cookie hoặc credentials.
- Nếu dữ liệu công khai, cân nhắc Access-Control-Allow-Origin: * nhưng không dùng credentials.
- Với API cá nhân, vẫn phải xác thực và phân quyền cho từng request.
- Cân nhắc Cache-Control: private, no-store cho response nhạy cảm.
- Nếu response CORS thay đổi theo Origin, thêm Vary: Origin; với preflight thay đổi theo method/header yêu cầu, thêm các trường tương ứng vào Vary.
- Không expose Set-Cookie, token hoặc header nội bộ cho JavaScript. JavaScript không thể đọc Set-Cookie qua CORS; không thiết kế dựa vào việc expose header này.

### 7.5. Duy trì CSRF protection

CORS không thay thế CSRF protection. Với endpoint thay đổi trạng thái:

- Dùng CSRF token gắn với phiên và xác minh ở máy chủ.
- Kiểm tra Origin hoặc Referer theo chính sách endpoint khi phù hợp.
- Chọn SameSite cho cookie dựa trên luồng nghiệp vụ; dùng Secure và HttpOnly cho cookie phiên.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Yêu cầu xác nhận hoặc xác thực lại với thao tác nhạy cảm.
- Kiểm thử request đơn giản có thể được gửi cross-origin ngay cả khi response không đọc được.

## 8. Kế hoạch kiểm thử sau sửa

### 8.1. Ma trận origin

| Origin gửi request | Kết quả mong đợi |
|---|---|
| https://app.example.test | Được phép theo hợp đồng API |
| https://partner-portal.example.test | Được phép nếu còn trong danh sách tích hợp |
| https://untrusted.example.test | Không có ACAO/ACAC cho phép; JavaScript không đọc được response |
| https://app.example.test.attacker.test | Bị từ chối |
| http://app.example.test | Bị từ chối nếu chỉ cho phép HTTPS |
| https://app.example.test:8443 | Bị từ chối nếu port không được phê duyệt |
| null | Bị từ chối trừ trường hợp đặc biệt đã được thiết kế và phê duyệt |
| Không có Origin | Xử lý theo luồng API bình thường; vẫn yêu cầu xác thực và phân quyền |

### 8.2. Ma trận credentials và request

| Trường hợp | Kết quả mong đợi |
|---|---|
| Request GET từ origin hợp lệ, credentials include | Response có ACAO chính xác và ACAC true; dữ liệu trả về theo quyền của phiên |
| Request GET từ origin không hợp lệ, credentials include | JavaScript không đọc được response; API không bỏ qua xác thực |
| Request POST đơn giản từ origin lạ | Có thể đến server; CSRF protection phải từ chối thay đổi trạng thái trái phép |
| Request PATCH từ origin lạ | Preflight bị từ chối; browser không gửi request PATCH thực tế |
| Request dùng header không nằm trong allowlist | Preflight bị từ chối |
| Request không có credentials | Chỉ được chia sẻ dữ liệu theo chính sách công khai hoặc origin đã cho phép |
| Response thay đổi theo Origin | Cache nhận đúng biến thể nhờ Vary và cache policy |
| Session đã hết hạn | API trả kết quả xác thực phù hợp; CORS không biến lỗi thành quyền truy cập |

### 8.3. Kiểm tra cache

Nếu response được tạo động theo Origin:

1. Gửi request từ origin hợp lệ A.
2. Gửi tiếp request từ origin hợp lệ B đến cùng URL.
3. Kiểm tra ACAO trong từng response có khớp đúng origin hay không.
4. Kiểm tra CDN có HIT response của A cho B hay không.
5. Kiểm tra Vary: Origin và cache key thực tế.
6. Với dữ liệu cá nhân, kiểm tra response không bị lưu ở shared cache và không bị tái sử dụng giữa các phiên.

Vary: Origin phân biệt các biến thể theo Origin; nó không phân biệt hai người dùng cùng một origin. Vì vậy, response cá nhân cần chính sách cache riêng như private hoặc no-store và kiểm soát ở CDN.

Sau khi thay đổi preflight policy, kiểm thử bằng browser profile mới hoặc chờ hết Access-Control-Max-Age của policy cũ. Trình duyệt có thể đang giữ kết quả preflight đã được cache; một lần thử ngay sau deploy có thể chưa gửi OPTIONS mới. Dù preflight cache còn hiệu lực, API vẫn phải xác thực và phân quyền trên request thực tế.

## 9. Theo dõi sau triển khai

Sau khi sửa, theo dõi trong một khoảng thời gian đủ để bao phủ các luồng tích hợp:

- Số origin được cho phép và bị từ chối theo route.
- Tỷ lệ preflight 2xx/4xx và các method/header thường bị từ chối.
- Tỷ lệ lỗi CORS phía client theo browser family và app version, nếu telemetry thu thập được.
- Request đến API từ origin không nằm trong danh sách.
- Lỗi tích hợp của frontend hợp lệ sau khi thu hẹp allowlist.
- Trạng thái cache và response header ở CDN.
- Các request thay đổi trạng thái bị từ chối bởi CSRF protection.

Không ghi cookie, token, toàn bộ URL có query string hoặc nội dung response vào telemetry. Dữ liệu Origin nên được chuẩn hóa, giới hạn độ dài và phân loại theo allowlist; endpoint log phải chống giả mạo và log injection.

Khi có origin hợp lệ bị từ chối, xác minh quyền sở hữu và nhu cầu nghiệp vụ trước khi thêm vào allowlist. Không mở rộng wildcard chỉ để xử lý nhanh lỗi tích hợp.

## 10. Bài học rút ra

1. **CORS là chính sách chia sẻ response của trình duyệt.** Nó không thay thế xác thực, phân quyền hay CSRF protection.
2. **Không phản chiếu Origin tùy ý.** Với API dùng credentials, chỉ trả origin cụ thể từ allowlist chính xác.
3. **Origin và site khác nhau.** Cookie SameSite không phải biện pháp duy nhất để bảo vệ API khỏi origin không đáng tin.
4. **Request và response là hai vấn đề khác nhau.** Request đơn giản có thể đến máy chủ dù JavaScript không đọc được response.
5. **Cache là một phần của ranh giới CORS.** Response động theo Origin cần Vary phù hợp; dữ liệu riêng tư vẫn cần cache policy riêng.
6. **Kiểm thử phải chạy trong browser.** Curl cho biết server trả header gì, nhưng không mô phỏng quyết định CORS của trình duyệt.
7. **Allowlist cần chủ sở hữu và vòng đời.** Origin đối tác phải có mục đích, môi trường, người chịu trách nhiệm và ngày rà soát.

## 11. Checklist đóng case study

- [ ] Đã xác định endpoint, origin, dữ liệu và credentials liên quan.
- [ ] Đã tái hiện trong staging bằng dữ liệu giả.
- [ ] Đã phân biệt request được gửi với response JavaScript được phép đọc.
- [ ] Đã kiểm tra cookie SameSite, Secure, HttpOnly và ngữ cảnh cross-site.
- [ ] Đã rà soát wildcard, phản chiếu Origin, allowlist theo hậu tố và origin null.
- [ ] Đã kiểm tra preflight, method và request header.
- [ ] Đã xác minh CORS không thay thế CSRF, xác thực và phân quyền.
- [ ] Đã giới hạn allowlist theo scheme, host và port chính xác.
- [ ] Đã thêm Vary phù hợp và cache policy cho response cá nhân.
- [ ] Đã kiểm thử hai origin hợp lệ, một origin không hợp lệ và các biến thể nguy hiểm.
- [ ] Đã kiểm tra CDN/cache không phân phối nhầm response giữa origin hoặc phiên.
- [ ] Đã có test hồi quy, dashboard và owner cho allowlist.

Case study chỉ được đóng khi origin không tin cậy không thể đọc response nhạy cảm qua trình duyệt, request thay đổi trạng thái vẫn được bảo vệ bằng CSRF và phân quyền, cache không làm lẫn response giữa các origin/phiên, và mọi origin được phép đều có lý do nghiệp vụ cùng chủ sở hữu rõ ràng.
