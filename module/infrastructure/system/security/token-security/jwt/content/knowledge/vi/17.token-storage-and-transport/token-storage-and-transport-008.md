# CORS và sự khác biệt với cơ chế xác thực token

## 1. CORS giải quyết vấn đề gì?

Một ứng dụng web thường được tải từ một origin, sau đó gửi yêu cầu đến API nằm ở origin khác. Ví dụ:

- Giao diện: `https://app.example.org`
- API: `https://api.example.org`

Hai địa chỉ có hostname khác nhau nên là hai origin khác nhau. Theo **Same-Origin Policy (SOP)**, trình duyệt giới hạn cách tài liệu hoặc mã chạy trong một origin tương tác và đọc dữ liệu từ origin khác. CORS (Cross-Origin Resource Sharing) là cơ chế cho phép máy chủ khai báo những origin nào được phép đọc phản hồi cross-origin trong trình duyệt.

Điểm quan trọng: **CORS không phải cơ chế đăng nhập, không xác minh JWT và không quyết định người dùng có quyền đọc hoặc sửa tài nguyên hay không.** CORS điều khiển việc trình duyệt có cho mã phía trang web truy cập phản hồi cross-origin hay không. API vẫn phải xác thực credential và ủy quyền cho từng yêu cầu.

Phân biệt nhanh:

- **CORS:** trình duyệt có cho trang web ở origin này đọc phản hồi từ origin kia không?
- **Authentication (xác thực):** request đang được gửi bởi chủ thể/client nào và credential có hợp lệ không?
- **Authorization (ủy quyền):** chủ thể/client đó được phép thực hiện hành động nào trên tài nguyên nào?
- **CSRF protection:** làm sao ngăn trình duyệt bị lợi dụng để gửi yêu cầu thay người dùng đang có phiên đăng nhập?

Bài viết thuộc phạm vi **Security - JSON Web Token (JWT)** tổng quát, tập trung vào cách CORS tương tác với việc truyền access token/JWT trong trình duyệt, không phụ thuộc ngôn ngữ lập trình hay framework.

## 2. Origin và Same-Origin Policy

### 2.1. Origin gồm những thành phần nào?

Origin được xác định bởi bộ ba:

```text
scheme + host + port
```

Ví dụ:

| URL | Origin | Có cùng origin với `https://app.example.org`? |
| --- | --- | --- |
| `https://app.example.org/home` | `https://app.example.org` | Có |
| `https://app.example.org:443/api` | `https://app.example.org` (HTTPS mặc định cổng 443) | Có |
| `http://app.example.org` | `http://app.example.org` | Không — khác scheme |
| `https://api.example.org` | `https://api.example.org` | Không — khác host |
| `https://app.example.org:8443` | `https://app.example.org:8443` | Không — khác port |

Đường dẫn không tham gia xác định origin. Hai URL cùng scheme, host và port nhưng khác path vẫn cùng origin.

### 2.2. Same-Origin Policy làm gì?

SOP là một ranh giới bảo mật của trình duyệt. Nó hạn chế một trang web đọc dữ liệu hoặc tương tác tùy ý với tài nguyên thuộc origin khác. Nếu không có cơ chế kiểm soát, một trang độc hại có thể cố đọc dữ liệu từ một ứng dụng mà người dùng đang đăng nhập ở tab khác.

CORS là cơ chế để server cho phép có chọn lọc một số truy cập đọc phản hồi cross-origin. CORS không làm hai origin trở thành cùng origin và không thay thế SOP; nó bổ sung quy tắc chia sẻ cho những trường hợp được server cho phép.

### 2.3. CORS áp dụng ở đâu?

CORS chủ yếu là cơ chế mà **user agent/trình duyệt** thực thi đối với các yêu cầu cross-origin được thực hiện bởi trang web. Nó không phải lớp bảo vệ mạng chung:

- Một chương trình gọi API từ máy chủ khác không bị CORS của trình duyệt áp dụng.
- Các công cụ HTTP như command-line client hoặc công cụ kiểm thử API không tự động bị CORS chặn.
- CORS không ngăn attacker gửi request trực tiếp đến API.
- CORS không thay thế authentication, authorization, rate limiting hoặc kiểm soát đầu vào.

Vì vậy, không được xem việc cấu hình CORS là đủ để bảo vệ endpoint khỏi truy cập trái phép.

## 3. CORS hoạt động bằng response headers

Trong CORS, trình duyệt gửi header `Origin` để cho server biết origin của trang khởi tạo request. Server trả về các header `Access-Control-Allow-*` để khai báo chính sách.

### 3.1. Các header quan trọng

| Header | Hướng truyền | Ý nghĩa |
| --- | --- | --- |
| `Origin` | Request | Origin của trang khởi tạo yêu cầu |
| `Access-Control-Allow-Origin` | Response | Origin được phép đọc phản hồi, hoặc `*` trong trường hợp không dùng credential mode include |
| `Access-Control-Allow-Methods` | Response preflight | Các HTTP method được phép |
| `Access-Control-Allow-Headers` | Response preflight | Các request header được phép gửi |
| `Access-Control-Allow-Credentials` | Response | Cho phép trình duyệt chia sẻ phản hồi trong yêu cầu có credentials mode `include` khi giá trị là `true` |
| `Access-Control-Expose-Headers` | Response | Các response header bổ sung mà mã phía trang được phép đọc |
| `Access-Control-Max-Age` | Response preflight | Thời gian trình duyệt có thể cache kết quả preflight |
| `Access-Control-Request-Method` | Request preflight | HTTP method mà request thật dự định sử dụng |
| `Access-Control-Request-Headers` | Request preflight | Các header không safelisted mà request thật dự định gửi |
| `Vary: Origin` | Response | Báo cache rằng phản hồi có thể thay đổi theo Origin |

### 3.2. Ví dụ phản hồi cho một origin cụ thể

Trang `https://app.example.org` gọi API `https://api.example.org`. API có thể trả:

```http
Access-Control-Allow-Origin: https://app.example.org
Vary: Origin
```

Trình duyệt có thể cho trang ở origin được phép đọc phản hồi. Nếu request đến từ origin khác không nằm trong allowlist, server không trả header cho phép tương ứng và trình duyệt không cho trang đó đọc phản hồi.

Server phải so khớp origin với allowlist được quản lý. Không nên phản chiếu bất kỳ giá trị `Origin` nào mà client gửi đến rồi trả lại nguyên giá trị trong `Access-Control-Allow-Origin`.

## 4. Simple request và preflight request

Không phải mọi yêu cầu CORS đều có cùng trình tự. Trình duyệt có thể gửi một số yêu cầu đơn giản trực tiếp; với các yêu cầu không thuộc nhóm safelisted, trình duyệt thường gửi **preflight** trước.

### 4.1. Simple request

Một request chỉ có thể đi theo cách đơn giản nếu đáp ứng các điều kiện của Fetch Standard, bao gồm method và các request header/content type được safelist. Các method thường gặp trong nhóm này là:

- `GET`
- `HEAD`
- `POST`

Các request header và giá trị của chúng cũng phải đáp ứng quy tắc safelist. Với `Content-Type`, những MIME type thường được safelist là:

- `application/x-www-form-urlencoded`
- `multipart/form-data`
- `text/plain`

Đây là các điều kiện kỹ thuật cụ thể; chỉ dùng method GET/POST không tự động có nghĩa request là simple.

Với simple request, trình duyệt có thể gửi request thật ngay. Sau đó, nó kiểm tra CORS headers trong response để quyết định có cho trang đọc phản hồi hay không.

### 4.2. Preflight request

Nếu request dùng method, header hoặc content type không thuộc nhóm safelisted, trình duyệt gửi một request kiểm tra trước bằng method `OPTIONS`. Request này gọi là **preflight**.

Ví dụ trang web muốn gửi:

```http
POST /api/orders HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Authorization: Bearer <access-token>
Content-Type: application/json
```

Do `Authorization` không phải CORS-safelisted request header và `application/json` không phải safelisted Content-Type, trình duyệt thường thực hiện preflight trước khi gửi request POST thật.

Preflight request minh họa:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

Lưu ý: preflight không gửi access token trong header `Authorization`. Nó chỉ nêu tên header mà request thật dự định gửi.

### 4.3. Server trả lời preflight

Nếu origin, method và các header được phép, server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.org
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin
```

Trình duyệt kiểm tra phản hồi preflight. Nếu các điều kiện không đạt, nó không gửi request POST thật theo luồng CORS đó. Nếu đạt, trình duyệt tiếp tục gửi request thật; server vẫn phải xác thực access token và kiểm tra quyền.

### 4.4. Preflight không phải bước xác thực

Preflight là một câu hỏi về chính sách cross-origin: origin này có được gửi method/header dự định không? Nó không chứng minh người dùng đã đăng nhập và không chứng minh access token hợp lệ.

Trình duyệt không gửi credentials trong CORS-preflight request. Vì vậy, một API thường cần xử lý `OPTIONS` preflight trước middleware xác thực access token hoặc có quy tắc riêng để cho phép preflight đi qua. Request thật sau đó vẫn phải được xác thực đầy đủ.

Không nên mở rộng quyền truy cập tài nguyên chỉ vì preflight được cho phép. Cho phép trình duyệt gửi request khác hoàn toàn với cho phép request thực hiện nghiệp vụ.

## 5. CORS và JWT Bearer Access Token

### 5.1. Header Authorization làm phát sinh preflight

Một cách phổ biến để gửi JWT access token là:

```http
Authorization: Bearer <jwt-access-token>
```

`Authorization` không phải CORS-safelisted request header. Khi trang web gửi header này đến origin khác, trình duyệt thường thực hiện preflight và hỏi API có cho phép header `Authorization` hay không.

Server cần cho phép header này trong phản hồi preflight, ví dụ:

```http
Access-Control-Allow-Headers: Authorization, Content-Type
```

Nếu server chỉ cho phép `Content-Type` mà không cho phép `Authorization`, trình duyệt có thể chặn request thật trước khi gửi. Đây là lỗi cấu hình CORS, không phải bằng chứng JWT sai chữ ký hoặc hết hạn.

### 5.2. Request thật vẫn phải xác minh JWT

Sau khi preflight thành công, trình duyệt gửi request thật kèm access token:

```http
GET /api/orders HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Authorization: Bearer <jwt-access-token>
```

API phải thực hiện quy trình xác minh độc lập:

1. Kiểm tra cấu trúc và loại access token được hỗ trợ.
2. Xác minh chữ ký bằng khóa tin cậy nếu token là JWT.
3. Kiểm tra issuer, audience và thời gian.
4. Kiểm tra scope/permission.
5. Kiểm tra quyền trên tài nguyên và thao tác cụ thể.
6. Trả kết quả nghiệp vụ cùng CORS response headers phù hợp để trang được phép đọc phản hồi.

CORS không đọc hoặc xác minh claims `iss`, `sub`, `aud`, `exp`, `scope`. Những việc đó thuộc trách nhiệm của API/resource server.

### 5.3. CORS không làm JWT an toàn hơn

CORS không:

- Ký JWT hoặc xác minh chữ ký.
- Mã hóa payload JWT.
- Ngăn token bị đánh cắp từ nơi lưu trữ.
- Giới hạn audience hoặc scope của token.
- Thu hồi access token.
- Ngăn request trực tiếp từ công cụ hoặc máy chủ khác.
- Thay thế HTTPS/TLS.

Một API cấu hình CORS chặt nhưng chấp nhận JWT giả vẫn không an toàn. Một API xác minh JWT rất chặt nhưng cấu hình CORS sai có thể khiến giao diện hợp lệ không đọc được response. Đây là hai lớp cấu hình độc lập.

## 6. CORS và cookie/session credentials

JWT có thể được truyền bằng header Authorization hoặc được lưu trong cookie theo một kiến trúc cụ thể. Hai cách này có hành vi trình duyệt khác nhau.

### 6.1. Gửi cookie cross-origin

Đối với yêu cầu cross-origin, trình duyệt mặc định không gửi cookie theo credentials mode mặc định `same-origin`. Nếu ứng dụng cần gửi cookie đến origin khác, nó phải dùng credentials mode `include` trong request.

Với request có credentials mode `include`, server phải trả:

```http
Access-Control-Allow-Origin: https://app.example.org
Access-Control-Allow-Credentials: true
Vary: Origin
```

Các quy tắc quan trọng:

- `Access-Control-Allow-Origin: *` không hợp lệ cho response được chia sẻ với credentials mode `include`.
- `Access-Control-Allow-Credentials` phải có giá trị `true` chính xác để cho phép chia sẻ response trong trường hợp này.
- Server phải chỉ định origin cụ thể được phép; nếu phản chiếu origin từ request, phải kiểm tra allowlist trước.
- Cookie vẫn phải đáp ứng thuộc tính `SameSite`, `Secure`, domain/path và chính sách cookie của trình duyệt.

### 6.2. Bearer Authorization header không đồng nghĩa cookie credentials

Một JWT được đặt thủ công trong header `Authorization` thường làm phát sinh preflight vì header này không safelisted. Điều đó không tự động có nghĩa request cần `Access-Control-Allow-Credentials: true`.

Phải phân biệt:

- Header `Authorization: Bearer ...` được trang chủ động thêm vào request và phải được cho phép qua `Access-Control-Allow-Headers`.
- Cookie, HTTP authentication entries và các credential trình duyệt khác chịu ảnh hưởng của credentials mode; khi dùng cross-origin credentials mode `include`, response cần `Access-Control-Allow-Credentials: true` và origin cụ thể.

Không thêm `Access-Control-Allow-Credentials: true` một cách máy móc cho mọi API chỉ vì API dùng JWT Bearer. Hãy xác định request thực sự có dùng cookie/credential mode include hay không.

### 6.3. Cookie flags vẫn quan trọng

Nếu cookie chứa session identifier hoặc credential, cần đánh giá:

| Thuộc tính | Vai trò |
| --- | --- |
| `Secure` | Chỉ gửi cookie qua kết nối bảo mật theo quy tắc cookie |
| `HttpOnly` | Ngăn script phía trang đọc trực tiếp cookie |
| `SameSite` | Kiểm soát một phần việc gửi cookie trong ngữ cảnh site khác |
| `Domain`, `Path` | Giới hạn phạm vi host/path gửi cookie |
| `Max-Age`, `Expires` | Giới hạn thời gian lưu cookie phía trình duyệt |

Các flags này không thay thế kiểm tra phiên phía máy chủ, bảo vệ CSRF hoặc xác minh quyền. `HttpOnly` giúp giảm khả năng đánh cắp cookie bằng cách đọc từ script, nhưng mã độc chạy trong origin vẫn có thể thực hiện hành động thay người dùng.

## 7. CORS không phải CSRF protection

Đây là một phân biệt đặc biệt quan trọng khi API sử dụng cookie.

### 7.1. Vì sao CORS không ngăn được mọi CSRF?

CSRF xảy ra khi trình duyệt của người dùng bị lợi dụng để gửi một yêu cầu đến ứng dụng mà người dùng đang có phiên đăng nhập. Với cookie, trình duyệt có thể tự động đính kèm cookie theo quy tắc cookie và ngữ cảnh request.

Một số request đơn giản có thể được gửi đến server dù trang khởi tạo không được phép đọc response theo CORS. CORS chủ yếu kiểm soát việc chia sẻ response với trang gọi; nó không bảo đảm request không gây tác động ở server.

Ví dụ: một trang độc hại gửi một form POST đơn giản đến một endpoint thay đổi trạng thái. Dù trang đó không đọc được response, server vẫn có thể nhận và xử lý request nếu không có biện pháp chống CSRF phù hợp.

### 7.2. Các biện pháp chống CSRF

Tùy kiến trúc, có thể kết hợp:

- **CSRF token:** yêu cầu một giá trị khó đoán gắn với phiên và kiểm tra ở server.
- **SameSite cookie:** giảm việc cookie được gửi trong một số ngữ cảnh cross-site; cần chọn giá trị phù hợp và hiểu các ngoại lệ.
- **Origin/Referer validation:** kiểm tra nguồn khởi tạo đối với các yêu cầu thay đổi trạng thái.
- **Custom request header:** có thể buộc request đi qua preflight trong mô hình trình duyệt, nhưng không thay thế kiểm tra server-side.
- **Không dùng GET cho thao tác thay đổi trạng thái:** giữ ngữ nghĩa an toàn của method.
- **Xác minh quyền và trạng thái phiên ở server:** không dựa vào CORS để quyết định nghiệp vụ.

Không phải ứng dụng nào cũng cần mọi biện pháp, nhưng phải có threat model và chọn cơ chế phù hợp với cách credential được gửi.

### 7.3. Bearer token trong Authorization header và CSRF

Nếu ứng dụng lưu access token ở nơi mà trang chủ động đọc được rồi tự thêm header `Authorization`, trình duyệt thường không tự đính kèm header đó vào request cross-site do một trang khác khởi tạo. Điều này có thể giảm một số rủi ro CSRF kiểu cookie tự động gửi.

Tuy nhiên:

- Nếu token bị lộ qua XSS, attacker có thể đọc token và gửi request từ môi trường khác.
- Nếu ứng dụng lưu token trong cookie, cookie có thể được tự động gửi và rủi ro CSRF cần được xử lý.
- CORS sai cấu hình có thể cho origin không tin cậy đọc response hoặc thực hiện request với credential.
- API vẫn phải xác minh token và quyền ở mọi request.

Không nên kết luận “dùng JWT là không cần CSRF protection”. Hãy xét cách token được lưu, cách trình duyệt gửi credential và loại request có thể gây tác động.

## 8. Cấu hình CORS an toàn

### 8.1. Dùng allowlist origin rõ ràng

Server nên xác định trước những origin hợp lệ, ví dụ:

```text
https://app.example.org
https://admin.example.org
```

Khi nhận header `Origin`, server so khớp với allowlist rồi mới trả `Access-Control-Allow-Origin`. Tránh:

- Cho phép mọi origin trong khi dùng cookie credentials.
- Phản chiếu nguyên văn mọi origin mà không xác thực.
- Dùng kiểm tra chuỗi lỏng như chỉ kiểm tra hostname có chứa `example.org`.
- Cho phép origin không tin cậy vì nó có cùng hậu tố hoặc tên gần giống.
- Cho phép `null` một cách tùy tiện.

Origin là một tuple scheme/host/port; nên so sánh theo giá trị origin đã phân tích và danh sách cấu hình đáng tin cậy.

### 8.2. Chỉ cho phép method và header cần thiết

Ví dụ API chỉ cần:

```http
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, X-Request-ID
```

Không cần mở mọi method hoặc mọi header nếu ứng dụng không sử dụng. Lưu ý `Authorization` là request header cần được nêu rõ trong allowlist; không dựa vào wildcard để thay thế.

### 8.3. Chỉ expose response headers cần thiết

Theo mặc định, script phía trang chỉ đọc được một tập response headers safelisted. Nếu client cần đọc header bổ sung như `X-Request-ID` hoặc `Content-Disposition`, server cần khai báo:

```http
Access-Control-Expose-Headers: X-Request-ID, Content-Disposition
```

Không expose toàn bộ headers một cách không cần thiết. Không expose header bí mật hoặc metadata nội bộ cho origin không đáng tin.

### 8.4. Dùng Vary khi phản hồi phụ thuộc Origin

Nếu server trả `Access-Control-Allow-Origin` động dựa trên allowlist, response nên có:

```http
Vary: Origin
```

Điều này giúp cache phân biệt response theo origin. Nếu thiếu `Vary: Origin`, một cache dùng chung có thể phục vụ response có CORS header của origin này cho origin khác, gây lỗi hoặc tạo lỗ hổng tùy cấu hình cache.

### 8.5. Giới hạn preflight cache

`Access-Control-Max-Age` cho phép trình duyệt cache kết quả preflight trong một khoảng thời gian. Thời gian dài có thể giảm số OPTIONS request, nhưng thay đổi chính sách có thể không có hiệu lực ngay trên các trình duyệt đang giữ cache. Chọn giá trị theo yêu cầu vận hành và khả năng cập nhật cấu hình.

Preflight cache là cache dành cho CORS; nó không phải cache access token hoặc kết quả xác thực JWT.

## 9. Xử lý OPTIONS và middleware xác thực

### 9.1. Vì sao preflight thường không mang access token?

Trình duyệt gửi preflight để hỏi server xem request thật có được phép dùng origin, method và header dự định hay không. Preflight request không gửi credentials. Nếu API bắt buộc mọi request, kể cả OPTIONS preflight, phải có JWT hợp lệ, trình duyệt có thể nhận lỗi trước khi gửi request thật.

Một cách tổ chức thường dùng:

1. Xử lý OPTIONS preflight theo chính sách CORS đã cấu hình.
2. Chỉ trả phép cho origin/method/header nằm trong allowlist.
3. Không thực hiện nghiệp vụ hoặc trả dữ liệu nhạy cảm chỉ vì OPTIONS được phép.
4. Với request thật, xác minh access token và ủy quyền như bình thường.

Cho phép preflight không đồng nghĩa cho phép truy cập endpoint. Request thật vẫn phải có credential hợp lệ nếu API yêu cầu.

### 9.2. CORS headers cần có trên response lỗi

Nếu origin hợp lệ gửi request thật nhưng token hết hạn, API có thể trả lỗi 401 cùng CORS headers thích hợp. Nhờ vậy, trang được phép đọc response và xử lý việc đăng nhập/làm mới token.

Nếu response lỗi không có CORS headers, trình duyệt có thể chỉ hiển thị lỗi CORS cho trang; client không đọc được body/status thật để biết API đã trả 401 hay 403.

Do đó, CORS policy cần được áp dụng nhất quán cho response thành công và response lỗi từ origin được phép, đồng thời không làm lộ dữ liệu cho origin không được phép.

## 10. Phân biệt lỗi CORS, lỗi xác thực và lỗi ủy quyền

| Hiện tượng | Lớp có vấn đề | Ví dụ | Cách điều tra |
| --- | --- | --- | --- |
| Preflight bị từ chối | CORS | Thiếu `Authorization` trong Allow-Headers | Kiểm tra OPTIONS và CORS response headers |
| Trình duyệt không cho trang đọc response | CORS | Thiếu hoặc sai `Access-Control-Allow-Origin` | Kiểm tra Origin và response headers |
| API trả 401 | Authentication | JWT thiếu, sai chữ ký, hết hạn hoặc sai audience | Kiểm tra response API và quy trình xác minh token |
| API trả 403 | Authorization | Token hợp lệ nhưng thiếu scope hoặc không có quyền trên tài nguyên | Kiểm tra policy, scope và quyền tài nguyên |
| API nhận request nhưng thay đổi trái phép do cookie tự gửi | CSRF | Thiếu CSRF protection trên endpoint thay đổi trạng thái | Kiểm tra cookie, SameSite, CSRF token và Origin |
| Công cụ HTTP gọi API thành công nhưng trình duyệt thất bại | CORS/browser policy | API hoạt động nhưng không cho origin giao diện đọc response | Kiểm tra preflight và CORS headers |

Một lỗi CORS không chứng minh token hợp lệ hay không hợp lệ. Một lỗi 401 không nhất thiết là lỗi CORS. Hãy xem Network panel của trình duyệt để phân biệt OPTIONS preflight, request thật và response headers.

## 11. Ví dụ cấu hình luồng JWT cross-origin hoàn chỉnh

Giả sử:

- Giao diện: `https://app.example.org`.
- API: `https://api.example.org`.
- Client gửi JWT access token qua `Authorization: Bearer`.
- API chỉ cho phép origin giao diện đã đăng ký.

### 11.1. Preflight

Request:

```http
OPTIONS /v1/orders HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Response:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.org
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Authorization
Access-Control-Max-Age: 600
Vary: Origin
```

Preflight không có header Bearer token. API chỉ xác nhận rằng origin được phép gửi GET với header Authorization.

### 11.2. Request thật

```http
GET /v1/orders HTTP/1.1
Host: api.example.org
Origin: https://app.example.org
Authorization: Bearer <jwt-access-token>
```

API:

1. Xác minh JWT theo issuer, khóa, thuật toán, audience và thời gian.
2. Kiểm tra scope và quyền trên đơn hàng.
3. Xử lý request.
4. Trả response cùng CORS headers cho origin hợp lệ.

Response thành công minh họa:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.org
Vary: Origin
Content-Type: application/json

{"items":[]}
```

Response lỗi token minh họa:

```http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.org
Vary: Origin
Content-Type: application/json

{"error":"invalid_token"}
```

Origin được phép vẫn có thể đọc lỗi 401 và yêu cầu client xử lý token hết hạn. CORS không biến response 401 thành thành công và cũng không bỏ qua xác minh token.

### 11.3. Nếu dùng cookie thay cho Authorization header

Nếu ứng dụng chuyển sang cookie cross-origin, cần đánh giá lại:

- Request dùng credentials mode `include`.
- Response phải có `Access-Control-Allow-Origin` là origin cụ thể.
- Response phải có `Access-Control-Allow-Credentials: true`.
- Cookie cần thuộc tính `Secure`, `SameSite` và domain/path phù hợp.
- API phải có CSRF protection thích hợp.
- Server vẫn xác minh session hoặc credential trong cookie và kiểm tra quyền.

Không thể chỉ thêm `Access-Control-Allow-Credentials: true` mà bỏ qua CSRF hoặc xác minh session.

## 12. Những lỗi cấu hình CORS phổ biến

1. **Dùng `Access-Control-Allow-Origin: *` cùng credentials mode include:** trình duyệt không chấp nhận chia sẻ response có credential theo cấu hình này.
2. **Quên cho phép `Authorization`:** preflight thất bại dù JWT hợp lệ.
3. **Bắt preflight phải có JWT:** OPTIONS không mang credentials, nên request thật không được gửi.
4. **Phản chiếu mọi Origin:** cho phép website không tin cậy đọc response.
5. **Cho phép origin bằng kiểm tra chuỗi lỏng:** có thể chấp nhận hostname giả mạo có hậu tố giống domain tin cậy.
6. **Không có `Vary: Origin` khi phản hồi động:** cache có thể phục vụ nhầm CORS headers.
7. **Chỉ thêm CORS headers cho response 200:** client không đọc được response lỗi 401/403 để xử lý đúng.
8. **Cho phép mọi method/header:** mở rộng bề mặt request không cần thiết.
9. **Nhầm CORS với authentication:** cho phép origin không có nghĩa token đã hợp lệ.
10. **Nhầm CORS với CSRF protection:** request có thể được gửi và gây tác động dù trang không đọc được response.
11. **Cho rằng API được bảo vệ khỏi curl/Postman nhờ CORS:** CORS là cơ chế trình duyệt, không phải kiểm soát truy cập mạng chung.
12. **Bật credentials cho mọi origin:** có thể làm lộ dữ liệu phiên cho website không đáng tin.

## 13. Checklist thiết kế CORS cho API dùng JWT

### Chính sách origin

- [ ] Có allowlist origin cụ thể theo môi trường.
- [ ] So khớp scheme, host và port; không phản chiếu Origin tùy ý.
- [ ] Chỉ cho phép origin cần thiết.
- [ ] Có `Vary: Origin` khi response thay đổi theo Origin.

### Preflight và headers

- [ ] Xử lý OPTIONS preflight mà không yêu cầu access token trong preflight.
- [ ] Chỉ cho phép method cần thiết.
- [ ] Cho phép rõ `Authorization` nếu client gửi Bearer token.
- [ ] Chỉ cho phép các request headers cần thiết.
- [ ] Expose response headers cần thiết, không expose tràn lan.
- [ ] Chọn `Access-Control-Max-Age` phù hợp.

### Credentials và cookie

- [ ] Xác định request dùng Bearer header hay cookie/session.
- [ ] Chỉ bật credentials mode include khi thực sự cần.
- [ ] Nếu dùng credentials mode include, trả origin cụ thể và `Access-Control-Allow-Credentials: true`.
- [ ] Không dùng wildcard origin với credentialed response.
- [ ] Cookie có Secure/HttpOnly/SameSite và phạm vi phù hợp.
- [ ] Có CSRF protection khi trình duyệt tự động gửi cookie.

### Authentication và authorization

- [ ] API xác minh JWT/session trên request thật, độc lập với CORS.
- [ ] Kiểm tra issuer, chữ ký, audience, thời gian và loại token.
- [ ] Kiểm tra scope/permission và quyền trên tài nguyên.
- [ ] Xử lý 401/403 cùng CORS headers cho origin được phép.
- [ ] Không ghi token hoặc cookie nguyên văn vào log.
- [ ] Có kiểm soát rate limit, input validation và giám sát như các API khác.

## 14. Kết luận

CORS là cơ chế chia sẻ tài nguyên cross-origin do trình duyệt thực thi dựa trên các response headers mà server cung cấp. Nó quyết định trang web ở origin nào được đọc phản hồi, có thể gửi method/header nào và có được chia sẻ response trong trường hợp credentials mode include hay không.

CORS **không xác thực JWT, không kiểm tra issuer/audience/expiry, không cấp scope, không quyết định quyền truy cập tài nguyên và không thay thế CSRF protection**. Khi dùng JWT Bearer, header `Authorization` thường làm phát sinh preflight và phải được cho phép rõ ràng. Sau khi preflight thành công, request thật vẫn phải qua toàn bộ quy trình xác minh token và ủy quyền của API.

Nếu dùng cookie cross-origin, cần cấu hình credentials, cookie flags và CSRF protection đúng cách. Thiết kế an toàn phải giữ các lớp riêng biệt: CORS cho trình duyệt, authentication cho credential, authorization cho quyền tài nguyên và CSRF protection cho request có thể bị trình duyệt gửi thay người dùng.

## Tài liệu tham khảo

- [WHATWG Fetch Standard — CORS protocol](https://fetch.spec.whatwg.org/#http-cors-protocol): thuật toán CORS, preflight, credentials và CORS headers.
- [RFC 6454 — The Web Origin Concept](https://www.rfc-editor.org/rfc/rfc6454): khái niệm origin.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách truyền và bảo vệ bearer access token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): định dạng JWT và claims.
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/docs/Web/HTTP/CORS): hướng dẫn CORS, simple request và preflight.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): phân biệt và giảm thiểu CSRF.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): lưu trữ credential phía trình duyệt và các rủi ro liên quan.
