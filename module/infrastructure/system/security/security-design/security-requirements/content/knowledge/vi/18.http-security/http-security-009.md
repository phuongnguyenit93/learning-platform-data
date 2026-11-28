# CORS policy

## 1. CORS là quyết định chia sẻ dữ liệu với một origin

Một nền tảng học tập có giao diện tại `https://portal.learning.example` và API tại `https://api.learning.example`. JavaScript của giao diện cần đọc hồ sơ, tiến độ và danh sách đăng ký từ API. Hai địa chỉ thuộc các origin khác nhau, nên trình duyệt cần một quyết định chia sẻ phản hồi phù hợp.

Cross-Origin Resource Sharing, gọi tắt là CORS, là cơ chế để server khai báo khi nào mã chạy trong trình duyệt từ một origin được phép truy cập phản hồi cross-origin. Với một số dạng request, trình duyệt còn hỏi trước bằng preflight trước khi gửi request thực tế.

Trong thiết kế yêu cầu bảo mật, CORS cần trả lời: dữ liệu nào được chia sẻ với ứng dụng web nào, trong chế độ credential nào, qua những phương thức và header nào? Câu trả lời phải gắn với endpoint, mô hình phiên và chủ sở hữu origin, không phải một cấu hình wildcard để giao diện hết báo lỗi.

Sau bài này, người học có thể:

- Phân biệt origin, site, danh tính người dùng và quyền nghiệp vụ.
- Giải thích request trực tiếp, preflight và việc trình duyệt cho phép đọc phản hồi.
- Đặc tả allowlist origin, credentials, method, header và chính sách cache.
- Nhận diện phản chiếu Origin tùy ý, wildcard không phù hợp và trust sai subdomain.
- Viết tiêu chí nghiệm thu bằng cả kiểm tra HTTP và trình duyệt thực.

## 2. Origin không phải tên miền chung, đường dẫn hoặc vai trò

### 2.1. Bộ ba scheme, host và port

Với các URL HTTP thông thường, origin được xác định bởi scheme, host và port hiệu lực. Hai URL có thể cùng site theo mô hình cookie nhưng vẫn khác origin.

Lấy `https://portal.learning.example` làm mốc:

| URL | Quan hệ origin với mốc | Lý do |
| --- | --- | --- |
| `https://portal.learning.example/courses` | Cùng origin | Chỉ khác đường dẫn |
| `https://portal.learning.example:443/profile` | Cùng origin | Port HTTPS mặc định tương đương |
| `http://portal.learning.example` | Khác origin | Khác scheme |
| `https://portal.learning.example:8443` | Khác origin | Khác port |
| `https://admin.learning.example` | Khác origin | Khác host |
| `https://api.learning.example` | Khác origin | Khác host |

Allowlist CORS chứa origin, không phải URL đầy đủ có đường dẫn. Nếu cho phép `https://portal.learning.example`, chính sách không có nghĩa chỉ script từ `/courses` mới được đọc API. Mã chạy trong cùng origin thuộc cùng ranh giới chia sẻ của quyết định này.

### 2.2. Origin không xác thực người dùng

Một origin được cho phép có thể phục vụ nhiều người dùng với các vai trò khác nhau. Server vẫn phải kiểm tra phiên hoặc token, tenant, quyền chức năng và quyền trên dữ liệu.

Giá trị Origin cũng không phải credential của server-to-server client. Một chương trình ngoài trình duyệt có thể tạo request và header theo cách riêng; không được coi việc nó khai một origin trong allowlist là bằng chứng danh tính.

### 2.3. Site và origin cần được mô hình hóa riêng

Chính sách cookie và SameSite không dùng cùng ranh giới với CORS. Những subdomain khác origin có thể vẫn nằm trong một site. Vì vậy, “cookie được gửi” không chứng minh script được đọc phản hồi, và “CORS đã cho phép” không bảo đảm cookie chắc chắn được gửi.

Yêu cầu cần xét cả hai lớp theo môi trường trình duyệt thực tế, bao gồm các hạn chế cookie liên quan. Không suy ra một lớp từ kết quả của lớp kia.

## 3. CORS kiểm soát điều gì?

### 3.1. Quyền đọc phản hồi và việc gửi request không luôn đi cùng nhau

Một số request không cần preflight. Chúng có thể tới server trước khi trình duyệt quyết định có chia sẻ phản hồi với script hay không. Trình duyệt chặn script đọc không có nghĩa server chưa nhận request hoặc chưa thực hiện tác dụng phụ. [MDN về các request CORS không cần preflight](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS#simple_requests).

Đây là lý do một lỗi CORS trong console không đủ để kết luận thao tác nghiệp vụ đã bị ngăn.

### 3.2. Không thay xác thực, phân quyền và chống CSRF

| Kiểm soát | Câu hỏi chính | CORS có thay thế không? |
| --- | --- | --- |
| Xác thực | Ai đang gọi? | Không |
| Phân quyền | Chủ thể được làm gì trên dữ liệu nào? | Không |
| Chống CSRF | Request có phù hợp với ý định và mô hình phiên của người dùng không? | Không |
| Giới hạn tốc độ | Bao nhiêu tài nguyên được phép tiêu thụ? | Không |
| CORS | Script từ origin nào được chia sẻ phản hồi theo giao thức trình duyệt? | Là phạm vi của cơ chế này |

Với API dùng cookie, request từ một trang khác có thể tận dụng credential tự động theo điều kiện cookie. Những thao tác đổi trạng thái cần biện pháp chống CSRF phù hợp; chỉ bỏ header cho phép đọc không tự ngăn mọi request đó. [MDN về mô hình và phòng vệ CSRF](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF).

### 3.3. Không phải firewall cho mọi client

CORS được trình duyệt thực thi. Một service backend, công cụ dòng lệnh hoặc ứng dụng khác không tự chịu cùng cơ chế hạn chế đọc như JavaScript trong trang web.

API không được bỏ phân quyền vì “chỉ portal có CORS”. Mọi đường gọi vẫn phải thực hiện chính sách server-side ngay cả khi request không có Origin hoặc đến từ client không phải trình duyệt.

### 3.4. Không bảo vệ origin đã được tin nhưng bị chiếm quyền

Nếu origin trong allowlist bị chiếm quyền hoặc có XSS, mã chạy tại origin đó có thể hưởng khả năng đọc mà CORS đã cấp trong điều kiện tương ứng. Allowlist là một quyết định tin cậy đối với ứng dụng web và chủ sở hữu của nó.

Do đó, thêm một origin cần xét ai triển khai nội dung ở đó, có nội dung do tenant hoặc người dùng tùy ý điều khiển không và ai chịu trách nhiệm khi ngừng sử dụng.

## 4. Hai luồng cần phân biệt

### 4.1. Request không cần preflight

Ví dụ portal gọi hồ sơ bằng cookie:

```javascript
const response = await fetch("https://api.learning.example/v1/me", {
  mode: "cors",
  credentials: "include",
  headers: {
    "Accept": "application/json"
  }
});

if (!response.ok) {
  throw new Error("Không đọc được hồ sơ");
}

const profile = await response.json();
```

Với dạng GET và các điều kiện header thông thường trong ví dụ, request không cần preflight chỉ vì nó dùng credentials. Khả năng gửi cookie còn tùy chính sách cookie và trình duyệt.

Một phản hồi phù hợp với profile minh họa có thể là:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://portal.learning.example
Access-Control-Allow-Credentials: true
Vary: Origin
Cache-Control: no-store

{"displayName":"Học viên A"}
```

`no-store` ở đây là lựa chọn minh họa cho dữ liệu hồ sơ; không phải mọi phản hồi CORS đều phải có cùng chính sách cache.

### 4.2. Preflight cho một request không thuộc tập được miễn

Giả sử portal gửi JSON và header chống CSRF cho thao tác cập nhật thiết lập:

```http
OPTIONS /v1/preferences HTTP/1.1
Host: api.learning.example
Origin: https://portal.learning.example
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type, x-csrf-token
```

Server đánh giá origin, method và tên header theo profile của route. Nếu được phép:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://portal.learning.example
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: PATCH
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Max-Age: 300
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
```

Giá trị cache 300 giây là ví dụ để minh họa cấu hình, không phải mức mặc định bắt buộc. Những giá trị Vary liên quan tới preflight phải phù hợp cách server và hạ tầng tạo hoặc cache phản hồi.

Sau đó mới là request nghiệp vụ:

```http
PATCH /v1/preferences HTTP/1.1
Host: api.learning.example
Origin: https://portal.learning.example
Content-Type: application/json
X-CSRF-Token: <token-theo-co-che-cua-ung-dung>
Cookie: <cookie-phien-neu-trinh-duyet-duoc-phep-gui>

{"emailNotifications":false}
```

Server vẫn xác thực, phân quyền, kiểm tra CSRF và dữ liệu. Phản hồi thực tế cũng cần các header CORS phù hợp để portal đọc được kết quả; một preflight thành công không thay thế bước kiểm tra phản hồi sau đó.

### 4.3. Preflight không phải phiên đăng nhập

Theo mô hình CORS, preflight cross-origin không mang credential như request nghiệp vụ. Nếu toàn bộ OPTIONS bị middleware yêu cầu cookie phiên, luồng hợp lệ có thể thất bại trước khi tới thao tác thực. Giá trị hợp lệ của `Access-Control-Allow-Credentials` là `true`; khi không cần thì bỏ header, không dùng `false`. [MDN về Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials).

Thiết kế cần cho phép đánh giá preflight theo chính sách route mà không thực hiện nghiệp vụ và không bỏ bảo vệ request thực tế. Không diễn giải điều này thành “bỏ xác thực cho mọi request OPTIONS”, vì ứng dụng có thể có các hành vi khác cần quản lý riêng.

### 4.4. Khi preflight bị từ chối

Nếu origin, method hoặc header không được phép, server không phát hành một phản hồi cấp quyền cho tổ hợp đó. Profile có thể trả lỗi thích hợp hoặc phản hồi không thỏa kiểm tra CORS, nhưng hành vi phải rõ và không tạo tác dụng phụ nghiệp vụ.

Không được tự thêm `*` khi không tìm thấy policy để “tránh lỗi frontend”. Thiếu policy của một route mới phải có hành vi mặc định đã được xác định.

## 5. Các header có vai trò khác nhau

| Header | Vai trò trong chính sách | Điều cần đặc tả |
| --- | --- | --- |
| `Access-Control-Allow-Origin` | Origin được chia sẻ phản hồi | Giá trị chính xác hoặc wildcard chỉ cho profile phù hợp |
| `Access-Control-Allow-Credentials` | Cho phép chia sẻ trong chế độ credential tương ứng | Có cần `true` hay không |
| `Access-Control-Allow-Methods` | Phương thức được chấp thuận trong preflight | Danh sách tối thiểu theo route hoặc profile |
| `Access-Control-Allow-Headers` | Tên request header được chấp thuận trong preflight | Các header client cần gửi |
| `Access-Control-Expose-Headers` | Response header bổ sung mà script được đọc | Danh sách cần thiết cho giao diện |
| `Access-Control-Max-Age` | Thời gian cho phép cache kết quả preflight | Giá trị phù hợp và kế hoạch thay đổi |
| `Vary` | Các chiều làm phản hồi khác nhau đối với cache HTTP | Giữ đúng biến thể qua origin và các chiều liên quan |

### 5.1. Allow-Origin không nhận một danh sách origin tùy ý

Header này không phải một chuỗi phân tách bằng dấu phẩy của mọi origin được phép. Cũng không có cú pháp giá trị kiểu `https://*.learning.example` để trình duyệt tự hiểu như allowlist subdomain. Server chọn một giá trị hợp lệ theo request và policy; `null` không nên được mở mặc định cho các ngữ cảnh không rõ danh tính. [MDN về cú pháp Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin#syntax).

### 5.2. Wildcard và credential mode

Với request có credential mode `include`, `Access-Control-Allow-Origin: *` không cho phép chia sẻ phản hồi. Điều kiện này dựa trên mode của request, không chỉ việc nhìn thấy một cookie thực tế trong lần truyền đó. Với profile có credentials, server cần origin cụ thể đã được chấp thuận và điều kiện credential tương ứng. [Fetch Standard, CORS và credentials](https://fetch.spec.whatwg.org/#cors-protocol-and-credentials).

Một cấu hình `*` cùng `Allow-Credentials: true` không phải cách “cho mọi origin đọc dữ liệu có phiên”. Nó tạo cấu hình không đáp ứng quy tắc chia sẻ của trình duyệt. Tuy nhiên, cũng không nên coi cấu hình sai đó là bằng chứng mọi tác dụng phụ đã bị ngăn.

### 5.3. Allow-Headers và Expose-Headers là hai hướng khác nhau

`Access-Control-Allow-Headers` liên quan tới request được gửi. Nếu ứng dụng dùng `Authorization`, phải chấp thuận tên đó một cách rõ ràng; wildcard không thay cho nó. Không cần đưa mọi header vận hành vào danh sách chỉ vì một client đang báo lỗi. [MDN về Access-Control-Allow-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Headers).

`Access-Control-Expose-Headers` liên quan tới response mà script đọc được. Ví dụ, nếu giao diện cần đọc `X-Request-Id` hoặc `Content-Disposition`, profile có thể expose đúng các tên đó. Việc expose không cho phép đọc mọi bí mật; nó cũng không biến `Set-Cookie` thành header script được đọc. [MDN về Access-Control-Expose-Headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Expose-Headers).

### 5.4. Allow-Methods không thay routing hoặc quyền chức năng

Danh sách này tham gia quyết định preflight. Nó không thay thế giới hạn method của router hoặc phân quyền server. Một request không cần preflight có thể không đi qua cùng phép hỏi trước.

Nếu profile không cho phép một method trên một route, server phải đánh giá đúng hành vi thực tế và chính sách cấp quyền đọc, đồng thời giữ nguyên kiểm soát nghiệp vụ. Không chỉ viết một danh sách method trong header rồi mặc định mọi đường khác không thể gọi server.

## 6. Thiết kế policy theo dữ liệu và ứng dụng tiêu thụ

### 6.1. Không dùng một profile mở cho toàn bộ API

Một nền tảng có thể cần các profile khác nhau:

| Nhóm API | Ứng dụng được chia sẻ phản hồi | Credentials | Điều kiện nghiệp vụ riêng |
| --- | --- | --- | --- |
| Danh mục công khai, không cá nhân hóa | Có thể cho mọi origin nếu đúng mục tiêu công khai | Không yêu cầu chế độ include | Không trả dữ liệu riêng khi có cookie ngoài dự kiến |
| Hồ sơ và tiến độ | `https://portal.learning.example` | Theo mô hình phiên đã chọn | Xác thực và giới hạn dữ liệu của người dùng |
| Quản trị tenant | `https://admin.learning.example` | Theo mô hình quản trị | Quyền chức năng và phạm vi tenant |
| Tích hợp trình duyệt của đối tác | Các origin đối tác được phê duyệt | Theo hợp đồng token hoặc phiên | Scope, đối tượng và phạm vi dữ liệu của đối tác |
| API chỉ dùng server-to-server | Không nhất thiết cần quyền đọc CORS | Theo cơ chế server-to-server | Xác thực và phân quyền vẫn bắt buộc |

Không thêm portal vào profile quản trị chỉ vì cả hai cùng thuộc tổ chức. Nếu portal không cần đọc phản hồi quản trị, mở thêm origin làm tăng phạm vi tin cậy mà không đáp ứng một nhu cầu chức năng cụ thể.

Với API công khai, cần bảo đảm kết quả thật sự không nhạy cảm và không chuyển sang cá nhân hóa trong một số điều kiện. “Chấp nhận wildcard” là quyết định về dữ liệu, không phải nhãn mặc định của phương thức GET.

### 6.2. Hồ sơ một policy

```text
POLICY: learner-profile-browser-access
ROUTES: các route hồ sơ và tiến độ đã kiểm kê
ALLOWED ORIGINS: https://portal.learning.example
CREDENTIAL MODEL: phiên người dùng theo cấu hình cookie của sản phẩm
METHODS: chỉ các phương thức từng route thực sự hỗ trợ
REQUEST HEADERS: Content-Type và header chức năng cần thiết đã liệt kê
EXPOSED RESPONSE HEADERS: X-Request-Id nếu giao diện cần đọc
PREFLIGHT CACHE: giá trị được chọn theo nhu cầu và khả năng thu hồi
ACTUAL RESPONSE CACHE: chính sách dữ liệu riêng của từng route
OWNER: nhóm API hồ sơ và nhóm ứng dụng portal
```

Một profile có thể dùng chung cho nhiều route nếu quyền chia sẻ dữ liệu thật sự giống nhau. Danh sách route và ngoại lệ cần rõ để một API mới không tự thừa hưởng policy rộng hơn mục đích.

### 6.3. Môi trường phát triển không tự trở thành origin production

Origin localhost, port phát triển hoặc tên preview có thể cần trong môi trường thử nghiệm. Chúng phải có phạm vi môi trường và vòng đời riêng.

Không mang toàn bộ danh sách preview vào production chỉ vì nhóm giao diện từng dùng chúng. Với origin preview do nhiều người hoặc pipeline tạo, cần xác định ai có thể triển khai mã ở đó và dữ liệu production nào có thể bị đọc.

## 7. So khớp origin và tránh phản chiếu tùy ý

### 7.1. Allowlist chính xác là điểm bắt đầu dễ kiểm chứng

Nguồn cấu hình nên chứa các origin đã được phân tích, kiểm tra và biểu diễn theo quy tắc thống nhất. Profile trình duyệt có thể yêu cầu một giá trị Origin hợp lệ, không mơ hồ; từ chối cấp quyền khi đầu vào không đáp ứng quy tắc đó.

Không dùng kiểm tra chuỗi kiểu:

```text
origin chứa "learning.example"
origin kết thúc bằng "learning.example"
```

Các kiểm tra thiếu ranh giới hoặc không phân tích đúng có thể chấp nhận một host ngoài chủ đích. Tên có đường dẫn, userinfo hoặc cách biểu diễn bất thường cũng không được tự coi là origin hợp lệ chỉ vì một parser URL chung chấp nhận được chuỗi đó.

Nếu dùng wildcard trong cấu hình server để quản lý một tập origin, đó là cơ chế so khớp nội bộ của framework, không phải cú pháp wildcard gửi trong Allow-Origin. Quy tắc đó cần được kiểm thử riêng và không được bao phủ vùng có nội dung người dùng hoặc tenant tùy ý kiểm soát.

### 7.2. Phản chiếu chỉ sau quyết định cho phép

Mẫu nguy hiểm là lấy bất kỳ Origin nào trong request rồi trả lại cùng `Allow-Credentials: true`. Khi cookie và điều kiện trình duyệt tương ứng cho phép, cách đó có thể chia sẻ dữ liệu phiên với một trang ngoài chủ đích.

Mẫu khái niệm phù hợp hơn:

```text
policy = findPolicyForResolvedRoute(request.route)
origin = parseSingleOriginAccordingToProfile(request)

if policy does not exist:
    do not grant cross-origin sharing
else if origin is not explicitly allowed by policy:
    do not grant cross-origin sharing
else if actual method is not allowed for this route and policy:
    do not grant cross-origin sharing
else:
    grant sharing only for the matched origin and profile
```

Đoạn này chỉ mô tả quyết định chia sẻ CORS. Nó không phải toàn bộ pipeline xử lý request. Xác thực, phân quyền, CSRF, routing và kiểm tra dữ liệu vẫn phải thực thi theo hợp đồng của API.

Với preflight, bổ sung kiểm tra phương thức dự kiến và tập tên header được yêu cầu. Không cần biết giá trị token chống CSRF hoặc nội dung nghiệp vụ ở bước này; chúng được kiểm tra trên request thực tế.

### 7.3. Không tin mọi subdomain

Một tên dưới cùng miền có thể thuộc dịch vụ cũ, nhà cung cấp, tenant hoặc vùng tải nội dung của người dùng. Việc cho mọi subdomain đọc API có phiên có thể mở rộng quyền tới các bên không chịu cùng kiểm soát triển khai.

Một yêu cầu hữu ích là mỗi origin có chủ sở hữu, mục đích, phạm vi dữ liệu, thời điểm phê duyệt và điều kiện gỡ bỏ. Khi một hostname không còn dùng, xóa nó khỏi allowlist cũng là một phần của quy trình ngừng dịch vụ.

### 7.4. Xử lý null và thiếu Origin

Các ngữ cảnh trình duyệt có opaque origin có thể gửi giá trị `null`. Một profile dữ liệu riêng không nên tự cho phép literal này chỉ để sửa một trường hợp iframe hoặc chạy tệp cục bộ.

Thiếu Origin cũng không chứng minh request đến từ backend tin cậy. API cần xử lý theo mô hình client được hỗ trợ và cơ chế xác thực của nó. Nếu một biện pháp chống CSRF dùng thông tin nguồn request, yêu cầu xử lý thiếu hoặc không xác minh được phải được định nghĩa ở chính lớp đó.

## 8. Đặt policy nhất quán trong chuỗi xử lý

### 8.1. Một chủ sở hữu cho kết quả cuối cùng

Nếu gateway, CDN, reverse proxy và ứng dụng đều tự thêm CORS, response có thể xuất hiện nhiều giá trị Allow-Origin hoặc một tầng mở rộng quyền mà tầng khác định hạn chế.

Kiến trúc cần chỉ rõ ai tạo header cuối cùng, ai có quyền thay đổi và các tầng còn lại phải giữ, loại bỏ hay chuyển tiếp thế nào. Header nhìn thấy ở client mới là kết quả cần kiểm chứng.

Không chỉ đọc cấu hình một service rồi kết luận CORS production đúng. Các tuyến lỗi, redirect hoặc response do edge tạo cũng phải thuộc phạm vi đánh giá.

### 8.2. Preflight và request nghiệp vụ đi qua các lớp khác nhau

Middleware cần nhận diện preflight đúng và đánh giá nó trước những bước yêu cầu credential của request nghiệp vụ, theo thiết kế framework. Việc cho phép trả lời preflight không được tạo một nhánh thực thi nghiệp vụ thiếu xác thực.

Không cho phép mọi OPTIONS rồi phản chiếu toàn bộ method và header được yêu cầu. Server phải có policy trước; request không được tự tạo policy bằng các trường Access-Control-Request-*.

### 8.3. Phản hồi lỗi cho origin được phép

Giao diện hợp lệ có thể cần đọc phản hồi hết phiên, không đủ quyền, giới hạn tốc độ hoặc lỗi kiểm tra dữ liệu. Nếu các phản hồi này thiếu CORS phù hợp, client có thể chỉ thấy lỗi truy cập phản hồi thay vì mã nghiệp vụ cần xử lý.

Yêu cầu nên bao phủ các trạng thái liên quan cho origin và route đã được cho phép, đồng thời giữ thông báo lỗi không có dữ liệu thừa. Điều này không cho phép thêm header chia sẻ với origin không hợp lệ chỉ để mọi client đều đọc được lỗi.

### 8.4. Redirect không thay thế hợp đồng API

Preflight hoặc request API bị đẩy sang một trang đăng nhập hoặc authority khác có thể tạo hành vi không phù hợp với client. Cần đặc tả cách API báo thiếu xác thực và các redirect được hỗ trợ theo môi trường trình duyệt mục tiêu.

Không coi mọi lỗi trong console có chữ CORS là lỗi allowlist. TLS, DNS, proxy, redirect và cookie đều có thể làm luồng không đạt trước khi đọc được dữ liệu như mong đợi.

## 9. Cache và việc thay đổi policy

### 9.1. Phản hồi thay đổi theo Origin

Nếu response được chọn theo Origin và phát Allow-Origin cụ thể, cần biểu diễn đúng biến thể với `Vary: Origin`. Phải giữ các giá trị Vary khác đang cần thiết, không ghi đè chúng khi thêm CORS. [MDN về CORS và cache](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin#cors_and_caching).

Thiết kế nên xét cả request không có Origin và origin không được cấp quyền, để cache không tái sử dụng sai một biến thể cho luồng khác. Nếu CDN không xử lý Vary như kỳ vọng, cần cấu hình key hoặc chính sách cache tương ứng thay vì chỉ thêm header ở ứng dụng.

Vary không thay thế phân vùng dữ liệu theo người dùng. Một body hồ sơ cá nhân bị cache dùng chung vẫn là lỗi bảo mật dù header CORS được chọn đúng origin.

### 9.2. Cache của preflight là một lớp riêng

`Access-Control-Max-Age` điều khiển thời gian lưu kết quả preflight trong giới hạn hành vi của trình duyệt. Cần chọn giá trị phù hợp với tần suất gọi và nhu cầu thay đổi; không giả định mọi trình duyệt giữ nguyên thời gian yêu cầu. [MDN về Access-Control-Max-Age](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Max-Age).

Nếu hạ tầng HTTP cũng cache OPTIONS, các chiều Origin, phương thức dự kiến và tên header có thể ảnh hưởng tới kết quả. Phải thiết kế rõ key, TTL và hành vi vô hiệu hóa cho lớp cache đó.

### 9.3. Thu hồi origin không thu hồi quyền nghiệp vụ bằng phép màu

Sau khi gỡ một origin, browser có thể vẫn có kết quả preflight đã cache và gửi request thực tế trong một số trường hợp. Server vẫn phải đánh giá việc chia sẻ trên response thực tế theo policy hiện hành.

Nếu mục tiêu là ngăn hành động nghiệp vụ, cần kiểm soát server-side tương ứng như thu hồi quyền, phiên hoặc thay đổi biện pháp CSRF. CORS không nên là ràng buộc duy nhất quyết định một request có được thay đổi dữ liệu.

Khi thay policy, cũng cần xử lý response cũ tại CDN hoặc cache được quản lý. Không thể thu hồi dữ liệu mà script đã đọc trước đó bằng cách chỉ thay header.

### 9.4. Giới hạn thời gian hiệu lực phải có cơ chế thực hiện

Yêu cầu “gỡ origin có hiệu lực trong khoảng T” phải định nghĩa T áp dụng cho điều gì: header ở instance mới, response từ CDN, cache preflight hay quyền nghiệp vụ.

Cần chọn giá trị T và cách đo theo kiến trúc thực tế. Một thay đổi cấu hình đã merge chưa chứng minh mọi edge và instance đã thực hiện cùng policy.

## 10. Chuyển thành yêu cầu bảo mật có thể kiểm chứng

### 10.1. Viết đúng mục tiêu chia sẻ dữ liệu

Yêu cầu yếu:

> Bật CORS cho frontend.

Câu này không xác định frontend nào, dữ liệu nào, cookie có được dùng không hoặc những response lỗi nào giao diện cần đọc.

Yêu cầu rõ hơn:

> Các API hồ sơ trong danh mục chỉ chia sẻ phản hồi có phiên với `https://portal.learning.example`, theo profile credential của sản phẩm. Origin ngoài allowlist không được cấp quyền đọc CORS. Request thực tế vẫn phải xác thực, phân quyền và thực thi biện pháp chống CSRF phù hợp; preflight không được tạo tác dụng phụ nghiệp vụ.

Yêu cầu cần đi kèm route, method, request header, response header được expose và chính sách cache. Không dùng câu chung để thay một hợp đồng có phạm vi.

### 10.2. Bộ yêu cầu minh họa

| Mã | Yêu cầu | Bằng chứng dự kiến |
| --- | --- | --- |
| CORS-01 | Mỗi profile có danh mục route, loại dữ liệu và ứng dụng web được chia sẻ | Bản đồ consumer và cấu hình profile |
| CORS-02 | Origin được so khớp theo quy tắc chính xác đã định nghĩa; không phản chiếu tùy ý | Ca đúng origin, sai scheme, port, host và chuỗi giả dạng |
| CORS-03 | Origin không được phép, không hợp lệ hoặc route thiếu policy không được cấp quyền đọc ngoài chủ đích | Ca mặc định từ chối chia sẻ |
| CORS-04 | Profile có credentials phải dùng giá trị origin và điều kiện credential hợp lệ; không dùng wildcard thay origin cụ thể | Kiểm thử browser theo credential mode |
| CORS-05 | Method và request header được chấp thuận phải tối thiểu theo chức năng | Danh mục nhu cầu và ca preflight vượt phạm vi |
| CORS-06 | Preflight không yêu cầu credential của request nghiệp vụ để đánh giá policy và không thực hiện nghiệp vụ | Bằng chứng OPTIONS và tác dụng phụ bằng không |
| CORS-07 | CORS không làm bỏ xác thực, phân quyền hoặc CSRF ở request thực tế | Ca API trực tiếp và ca có phiên nhưng không đủ quyền |
| CORS-08 | Response lỗi thuộc luồng hợp lệ phải tuân thủ profile mà không tiết lộ dữ liệu thừa | Ca hết phiên, không đủ quyền, lỗi dữ liệu và giới hạn tốc độ |
| CORS-09 | Response biến thiên theo origin phải được cache với biến thể đúng; dữ liệu cá nhân không bị chia sẻ qua cache | Thử nghiệm qua CDN và nhiều phiên |
| CORS-10 | Header CORS cuối cùng phải nhất quán qua edge, proxy và ứng dụng, không có cấu hình cấp quyền xung đột | Bằng chứng response tại đường truy cập thực |
| CORS-11 | Thay allowlist phải có owner, vòng đời và giới hạn hiệu lực đã công bố | Hồ sơ thay đổi, gỡ origin và kiểm tra hội tụ |
| CORS-12 | Chỉ expose response header thực sự cần; không dùng danh sách rộng ngoài mục đích | Kiểm thử JavaScript đọc header theo profile |
| CORS-13 | Origin phát triển hoặc preview phải tách phạm vi với dữ liệu production theo chính sách | Kiểm tra cấu hình từng môi trường |
| CORS-14 | API không được coi Origin hợp lệ hoặc thiếu Origin là bằng chứng danh tính của client | Ca server-to-server và ca header tự khai |

Các mã là ví dụ tổ chức đặc tả. Điều kiện, mức bao phủ và giới hạn thời gian phải được lựa chọn cho hệ thống thực tế.

### 10.3. Truy vết rủi ro tới bằng chứng

```text
Tài sản: hồ sơ và tiến độ người học
    ↓
Mối đe dọa: trang ngoài chủ đích đọc dữ liệu bằng phiên hiện có
    ↓
Yêu cầu: origin chính xác, credential profile và không phản chiếu tùy ý
    ↓
Thiết kế: policy theo route, được áp dụng nhất quán ở response cuối
    ↓
Bằng chứng: portal hợp lệ đọc được dữ liệu trong điều kiện có quyền;
origin ngoài allowlist không được script đọc phản hồi
```

Một mối đe dọa khác là request trái ý định làm thay đổi dữ liệu. Mối đó phải có yêu cầu CSRF và phân quyền riêng, không coi bằng chứng chặn đọc CORS là đủ.

## 11. Tiêu chí nghiệm thu

Phần này mô tả kiểm thử nên thực hiện khi triển khai, không có nghĩa các kiểm thử đã được chạy cho một hệ thống cụ thể.

### 11.1. Tách kiểm tra HTTP và kiểm tra trình duyệt

Kiểm tra HTTP xác nhận server trả những header nào, qua route nào và với trạng thái nào. Kiểm tra trình duyệt xác nhận script thực sự được hoặc không được đọc phản hồi theo cơ chế CORS.

Một công cụ gọi HTTP ngoài trình duyệt có thể đọc body dù response không có Allow-Origin. Điều đó không tự chứng minh CORS bị lỗi; công cụ không thực thi ranh giới đọc của trình duyệt.

Ngược lại, chỉ thấy CORS error trong trình duyệt chưa cho biết request đã được gửi, cookie có mặt hay backend đã thay đổi dữ liệu. Cần quan sát cả client và server.

### 11.2. Ma trận trường hợp

| Trường hợp | Thiết lập | Kết quả cần chứng minh |
| --- | --- | --- |
| Origin hợp lệ | Portal, route được phép và danh tính đúng quyền | Script đọc được kết quả theo profile |
| Origin ngoài allowlist | Một origin thử nghiệm không được cấp quyền | Không được chia sẻ body với script |
| Scheme hoặc port khác | HTTP thay HTTPS hoặc port ngoài cấu hình | Không vô tình khớp origin hợp lệ |
| Tên giả dạng | Host chứa tên tin cậy nhưng nằm ngoài allowlist | Không được cấp quyền do phép so khớp chuỗi sai |
| Literal null | Ngữ cảnh thử tạo Origin null | Tuân thủ chính sách rõ ràng, không được mở mặc định cho dữ liệu riêng |
| Origin không hợp lệ | Header có đường dẫn hoặc biểu diễn ngoài profile, qua công cụ HTTP | Không phản chiếu như một giá trị được tin |
| Credential mode include | Origin hợp lệ, cookie theo môi trường thử | Chia sẻ chỉ khi đủ điều kiện profile; không dùng Allow-Origin wildcard |
| Không có phiên | Origin hợp lệ nhưng không có danh tính | API vẫn từ chối theo xác thực; không trả dữ liệu riêng |
| Không đủ quyền | Origin hợp lệ, người dùng sai vai trò hoặc tenant | Phân quyền server vẫn có hiệu lực |
| Preflight hợp lệ | Method và header đúng profile | Cho phép hỏi trước, không tạo tác dụng phụ |
| Preflight vượt phạm vi | Method hoặc header không được chấp thuận | Không cấp quyền cho tổ hợp đó |
| Request không cần preflight | Luồng có thể tới server trực tiếp | Xác thực và CSRF vẫn ngăn hành động trái chính sách |
| Lỗi nghiệp vụ | Origin hợp lệ, payload không hợp lệ | Giao diện đọc được lỗi đã được phép, không lộ chi tiết thừa |
| Header được expose | Response có header cần cho client | Script đọc đúng các header được hợp đồng cho phép |
| Qua cache và proxy | Gọi xen kẽ các origin và phiên khác nhau | Không tái sử dụng sai header hoặc body |
| Gỡ origin | Cache và instance có trạng thái khác nhau | Hiệu lực thay đổi phù hợp phạm vi và thời gian cam kết |

Chuỗi host giả dạng cần là dữ liệu thử trong môi trường kiểm soát, chẳng hạn `https://portal.learning.example.attacker.example`. Mục tiêu là kiểm tra logic so khớp, không truy cập hệ thống của bên khác.

### 11.3. Kiểm soát điều kiện cookie để tránh kết luận sai

Một ca negative có thể không đọc được dữ liệu đơn giản vì cookie đã bị trình duyệt chặn hoặc phiên hết hạn. Khi đó, chưa chứng minh allowlist CORS ngăn chia sẻ dữ liệu trong điều kiện có credential.

Môi trường test cần biết chính xác request nào mang phiên, response nghiệp vụ nào được tạo và script thấy gì. Dùng dữ liệu thử và tài khoản thử phù hợp, không ghi hoặc phát tán cookie thật.

Tương tự, ca positive thất bại do TLS hoặc DNS không xác nhận CORS sai. Cần tách những điều kiện nền này khỏi thuộc tính CORS đang kiểm chứng.

### 11.4. Kiểm tra tác dụng phụ độc lập với khả năng đọc

Với thao tác thay đổi thiết lập, quan sát trạng thái trước và sau request, audit và kết quả server-side. Nếu script không đọc được response nhưng thiết lập vẫn thay đổi trái chính sách, phần chống CSRF hoặc phân quyền chưa đáp ứng yêu cầu liên quan.

Đối với preflight, xác nhận không có cập nhật nghiệp vụ, không tạo job thực hiện thao tác và không thực thi handler dự kiến của request thật. Sự kiện log phục vụ vận hành là hoạt động riêng đã được thiết kế.

### 11.5. Những bằng chứng chưa đủ

- Có header Allow-Origin không chứng minh origin và credentials đúng.
- Có preflight thành công không chứng minh request nghiệp vụ đã được phân quyền.
- Thấy lỗi CORS không chứng minh backend không thực hiện hành động.
- Một origin được phép hoạt động không chứng minh origin lạ bị từ chối.
- Kiểm tra trực tiếp service không chứng minh response đi qua CDN giống như vậy.
- Dữ liệu không đọc được vì thiếu cookie không chứng minh policy credential đã an toàn.
- Test chỉ trạng thái thành công không chứng minh các response lỗi có cùng policy đúng.

Bằng chứng nên ghi browser, origin, route, method, credential mode, tình trạng phiên, header cuối cùng và cấu hình cache liên quan. Với dữ liệu nhạy cảm, dùng định danh thử và chính sách log phù hợp.

## 12. Các sai lầm thiết kế thường gặp

### 12.1. Bật wildcard để sửa mọi lỗi frontend

Cách này bỏ qua việc dữ liệu thuộc loại công khai hay có phiên. Nó cũng không sửa được những tổ hợp credentials không hợp lệ theo giao thức. Cần tìm nguyên nhân và áp dụng profile cho đúng route.

### 12.2. Phản chiếu Origin không qua allowlist

Nếu mọi origin đều được trả lại như đã chấp thuận, hệ thống đã biến một trường đầu vào thành quyết định tin cậy. Phải kiểm tra trước khi phát hành quyền chia sẻ.

### 12.3. Tin cả miền và mọi subdomain

Chính sách quá rộng có thể bao gồm preview, dịch vụ bỏ hoang hoặc vùng nội dung của người dùng. Origin cần được xét theo quyền kiểm soát mã và loại dữ liệu được chia sẻ.

### 12.4. Coi preflight là cơ chế xác thực

Preflight chỉ hỏi điều kiện giao tiếp cross-origin theo policy. Nó không thay phiên, token hoặc phân quyền của request thực. Không lấy việc OPTIONS đã qua làm lý do bỏ kiểm tra tiếp.

### 12.5. Chỉ thêm CORS cho response thành công

Giao diện có thể không đọc được lỗi hết phiên hoặc giới hạn tốc độ và xử lý sai trạng thái. Cần bao phủ response hợp lệ theo origin và route, giữ dữ liệu lỗi tối thiểu.

### 12.6. Để proxy và ứng dụng cấp quyền riêng rẽ

Nhiều nguồn cấu hình có thể làm header trùng, không hợp lệ hoặc rộng ngoài ý định. Cần một hợp đồng trách nhiệm và kiểm chứng response cuối tại đường truy cập thật.

### 12.7. Dùng mode no-cors để đọc API riêng

Chuyển Fetch sang `no-cors` không cấp thêm quyền đọc body cross-origin. Nó không phải giải pháp cho một API cần chia sẻ dữ liệu với giao diện; cần sửa hợp đồng server và client phù hợp với nhu cầu được phép.

### 12.8. Dùng CORS để chặn server-to-server client

Một chương trình ngoài trình duyệt không chịu ràng buộc đọc của CORS. Cần cơ chế xác thực, phân quyền và bảo vệ tài nguyên thực sự cho mọi client.

## 13. Vận hành và vòng đời allowlist

### 13.1. Mỗi origin là một quyết định tin cậy có owner

Hồ sơ thay đổi nên ghi origin, mục đích, route được đọc, mô hình credentials, nhóm triển khai ứng dụng web và người chịu trách nhiệm gỡ bỏ. Với đối tác hoặc preview, có thể cần thời hạn hoặc điều kiện kiểm tra lại.

Khi origin đổi chủ, ngừng dịch vụ hoặc chuyển chức năng, cần đánh giá lại quyền chia sẻ. Không giữ origin vĩnh viễn chỉ vì nó từng được thêm để xử lý một ticket.

### 13.2. Quan sát lỗi nhưng không log dữ liệu phiên

Có thể theo dõi số preflight được chấp thuận, bị từ chối, origin ngoài allowlist, policy version và response thiếu hoặc trùng header. Dữ liệu đầu vào không tin cậy như Origin cần được log bằng cơ chế tránh phá cấu trúc và có giới hạn kích thước.

Không ghi cookie, token hay toàn bộ phản hồi hồ sơ chỉ để chẩn đoán CORS. Dashboard quan sát cũng phải có quyền truy cập phù hợp.

### 13.3. Thu hẹp policy khi có sự cố

Nếu một origin được tin bị ảnh hưởng, đội vận hành cần biết cách gỡ quyền chia sẻ ở mọi lớp, xử lý cache được quản lý và cập nhật instance. Với rủi ro thực hiện hành động bằng phiên, đánh giá đồng thời cơ chế phiên, CSRF và phân quyền.

Rollback không được tự mở wildcard để khôi phục giao diện. Nên có cấu hình phiên bản và phương án quay về một policy đã biết đúng.

### 13.4. Điều tra dựa trên toàn bộ luồng

Một quy trình chẩn đoán có thể kiểm tra lần lượt: origin thực tế, route và profile, request có cần preflight không, kết quả OPTIONS, request thật có được gửi không, tình trạng credential, phản hồi cuối và các cache trung gian.

Mục tiêu là tìm đúng lớp không đáp ứng hợp đồng. Không chuyển một lỗi cookie, xác thực hoặc redirect thành một thay đổi allowlist rộng hơn ngoài nhu cầu.

## 14. Mẫu đặc tả ngắn

```text
ID: SEC-HTTP-LEARNER-API-CORS

Tài sản:
Hồ sơ và tiến độ người học được API cung cấp cho ứng dụng web.

Phạm vi:
Các route trong profile learner-profile-browser-access đã được kiểm kê.

Origin được chia sẻ:
https://portal.learning.example, đối chiếu đúng scheme, host và port.
Không phản chiếu tùy ý, không cấp mặc định cho origin lạ hoặc null.

Mô hình credential:
Theo cơ chế phiên và cookie của sản phẩm. Khi request dùng include,
Allow-Origin phải là origin cụ thể được phép và điều kiện credential
phải hợp lệ. Không dùng wildcard để thay giá trị đó.

Method và header:
Chỉ chấp thuận những method và request header chức năng đã liệt kê.
Chỉ expose response header mà ứng dụng web thực sự cần đọc.

Preflight:
Đánh giá bằng policy của route, không yêu cầu credential của request
nghiệp vụ và không tạo tác dụng phụ. Không tự mở policy từ dữ liệu hỏi.

Request thực:
Vẫn xác thực, phân quyền, kiểm tra CSRF và dữ liệu theo hợp đồng.
CORS không được coi là bằng chứng danh tính hoặc quyền nghiệp vụ.

Response và cache:
Cấp header đúng trên các trạng thái thuộc luồng được phép.
Giữ đúng Vary và biến thể cache; bảo vệ body theo chính sách dữ liệu.
Có giới hạn hiệu lực thay đổi cho instance, edge và cache liên quan.

Bằng chứng:
HTTP và browser test cho origin đúng/sai, credentials, preflight,
response lỗi, header expose, proxy/cache và hành vi sau khi gỡ origin.
Quan sát tác dụng phụ riêng với khả năng script đọc response.

Chủ sở hữu:
Nhóm API và ứng dụng web xác định nhu cầu; nhóm nền tảng bảo đảm header
cuối nhất quán; nhóm vận hành quản lý vòng đời, thay đổi và sự cố.
```

CORS policy là hợp đồng chia sẻ dữ liệu giữa API và các ứng dụng web được lựa chọn. Đặc tả rõ origin, credentials, route và cache giúp bảo vệ hợp đồng đó; xác thực, phân quyền và chống CSRF tiếp tục chịu trách nhiệm cho danh tính và hành động nghiệp vụ của mỗi request.
