# Status code nhất quán với kết quả bảo mật

HTTP status code là một phần của hợp đồng API. Nó cho client biết request đã thành công, cần xác thực, bị từ chối, không hợp lệ, xung đột với trạng thái hiện tại hay tạm thời không thể xử lý. Trong thiết kế `SECURITY_API_SECURITY`, status code còn ảnh hưởng trực tiếp đến cách client retry, cách hệ thống ghi nhận sự cố và lượng thông tin mà API tiết lộ về tài nguyên.

Một API được bảo vệ tốt cần thiết kế bảo mật theo từng endpoint, đối tượng dữ liệu và luồng nghiệp vụ. Vì vậy, kết quả HTTP phải phản ánh đúng quyết định xác thực, phân quyền, validation và kiểm soát lạm dụng tài nguyên. Trả `200 OK` cho một thao tác bị từ chối, dùng lẫn lộn `401` với `403`, hoặc tiết lộ tài nguyên qua thông báo `404` không nhất quán đều làm suy yếu hợp đồng và có thể tạo thêm rủi ro.

## 1. Status code là một phần của ranh giới bảo mật

Client thường dựa vào status code để quyết định bước tiếp theo:

- Gặp `401`, client có thể yêu cầu người dùng đăng nhập hoặc làm mới thông tin xác thực.
- Gặp `403`, client hiểu rằng danh tính hiện tại không được phép thực hiện hành động.
- Gặp `404`, client có thể dừng truy cập tài nguyên hoặc hiển thị trạng thái không tìm thấy.
- Gặp `409`, client có thể tải lại trạng thái mới và yêu cầu người dùng giải quyết xung đột.
- Gặp `429` hoặc `503`, client có thể chờ trước khi thử lại.
- Gặp `5xx`, hệ thống vận hành cần điều tra lỗi phía server hoặc dịch vụ phụ thuộc.

Nếu API trả sai mã, client có thể retry một thao tác không được phép, bỏ qua lỗi xác thực, hiển thị dữ liệu không chính xác hoặc tạo ra nhiều side effect. Status code không thay thế authorization, validation hay rate limit; nó phải là kết quả trung thực của các kiểm soát đó.

Một quyết định cho request nên đi theo thứ tự có chủ đích:

1. Xác định route và method có tồn tại, được hỗ trợ không.
2. Xác thực danh tính và kiểm tra tính hợp lệ của credential.
3. Xác định phạm vi tenant, actor và tài nguyên được tham chiếu.
4. Kiểm tra quyền trên object, action và field.
5. Kiểm tra cấu trúc, dữ liệu đầu vào và điều kiện workflow.
6. Thực hiện thao tác, rồi trả status code phù hợp với kết quả thực tế.

Thứ tự thực thi cụ thể có thể khác tùy framework và chính sách che giấu thông tin. Ví dụ, API có thể chủ động trả `404` cho tài nguyên ngoài phạm vi để không tiết lộ tài nguyên tồn tại. Điều quan trọng là các endpoint cùng loại phải áp dụng một quy ước nhất quán.

## 2. Phân biệt 401, 403 và 404

Ba mã này thường bị nhầm lẫn nhất trong API có xác thực và phân quyền.

| Status | Ý nghĩa | Tình huống thường gặp |
|---|---|---|
| `401 Unauthorized` | Request thiếu credential hợp lệ hoặc credential không được chấp nhận | Không gửi token, token hết hạn, chữ ký token sai |
| `403 Forbidden` | Server hiểu danh tính request nhưng từ chối hành động theo chính sách | User đã đăng nhập nhưng không có quyền duyệt hóa đơn |
| `404 Not Found` | Không tìm thấy tài nguyên hoặc chủ động che giấu tài nguyên ngoài phạm vi | ID không tồn tại hoặc object không được phép biết đến |

Tên `Unauthorized` của `401` dễ gây hiểu nhầm. Trong ngữ nghĩa HTTP, đây là phản hồi liên quan đến việc xác thực: client cần cung cấp thông tin xác thực hợp lệ. `403 Forbidden` thường phù hợp khi server đã nhận diện được actor nhưng actor không được phép thực hiện hành động.

### 2.1. Khi nào trả 401

Dùng `401` khi request không có credential cần thiết hoặc credential không hợp lệ, chẳng hạn:

- Không có access token trong endpoint yêu cầu đăng nhập.
- Token hết hạn, sai chữ ký, sai issuer/audience hoặc bị thu hồi.
- API key không hợp lệ hoặc thông tin xác thực không được chấp nhận.
- Credential không đáp ứng cơ chế xác thực mà endpoint yêu cầu.

Với HTTP authentication, phản hồi `401` cần có header `WWW-Authenticate` chỉ ra cơ chế xác thực phù hợp. Ví dụ API dùng Bearer token có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="api"
Content-Type: application/problem+json
Cache-Control: no-store
```

Không đưa token nhận được, khóa bí mật, chi tiết chữ ký hoặc nguyên nhân nội bộ nhạy cảm vào response. Một thông báo như `Authentication required` hoặc `The access token is invalid or expired` thường đủ cho client. Nếu API dùng OAuth 2.0 Bearer Token, cần tuân theo quy ước lỗi của giao thức; ví dụ token không hợp lệ thường dẫn đến `401`, còn token hợp lệ nhưng thiếu scope có thể dẫn đến `403` kèm thông tin challenge phù hợp.

### 2.2. Khi nào trả 403

Dùng `403` khi danh tính đã được xác thực nhưng chính sách không cho phép hành động. Ví dụ:

- Người dùng thường gọi endpoint quản trị.
- Nhân viên có quyền đọc hóa đơn nhưng không có quyền hoàn tiền.
- Actor không được sửa field `role`, `balance` hoặc `verifiedAt`.
- Người phê duyệt không được duyệt giao dịch do chính mình tạo, theo nguyên tắc tách nhiệm vụ.
- Service identity hợp lệ nhưng không có quyền gọi chức năng của service đích.

Ví dụ:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store
```

Response có thể nói `You are not allowed to perform this action`. Không nên trả tên role nội bộ, policy expression, danh sách quyền của người khác hoặc chi tiết cấu hình IAM nếu client không cần biết.

Không trả `401` chỉ vì actor thiếu quyền. Nếu client hiểu `401` là cần đăng nhập lại, nó có thể lặp lại quy trình đăng nhập dù credential hoàn toàn hợp lệ. Điều này gây trải nghiệm sai và tạo tải không cần thiết cho hệ thống xác thực.

### 2.3. Khi nào dùng 404 để che giấu object

Trong lỗi Broken Object Level Authorization (BOLA), client có thể thay ID để dò tài nguyên của người khác. Nếu API trả `403` cho ID tồn tại nhưng trả `404` cho ID không tồn tại, kẻ tấn công có thể phân biệt hai trường hợp và thu thập thông tin về dữ liệu trong hệ thống.

Một chính sách thường dùng là trả cùng `404 Not Found` cho cả hai trường hợp:

- Object không tồn tại.
- Object tồn tại nhưng actor không được phép biết hoặc truy cập object đó.

Ví dụ:

```http
GET /api/invoices/8b1f...

HTTP/1.1 404 Not Found
Content-Type: application/problem+json
```

Chính sách che giấu này phù hợp với tài nguyên riêng tư như hóa đơn, hồ sơ cá nhân, đơn hàng hoặc tệp nội bộ. Tuy nhiên, không phải endpoint nào cũng cần che giấu. Với chức năng quản trị hoặc tài nguyên mà sự tồn tại vốn được công khai, `403` có thể rõ ràng và phù hợp hơn.

Khi chọn `404` để che giấu, cần nhất quán giữa object không tồn tại và object ngoài phạm vi ở các khía cạnh:

- Status code và cấu trúc response.
- Thông báo lỗi và các header có thể tiết lộ thông tin.
- Luồng xử lý, truy vấn và các side effect.
- Thời gian phản hồi ở mức hợp lý, tránh khác biệt lớn dễ bị dùng làm tín hiệu dò tìm.

Không thể bảo đảm thời gian của hai nhánh hoàn toàn giống nhau trong mọi hệ thống. Hãy tránh các khác biệt rõ rệt, không thực hiện truy vấn hoặc thao tác phụ không cần thiết, và kiểm thử khả năng dò tìm trên endpoint có dữ liệu nhạy cảm.

## 3. Status code cho validation và định dạng request

Lỗi đầu vào cần được phân loại để client biết nên sửa nội dung request hay thay đổi cách gửi.

| Status | Khi nào dùng | Ví dụ |
|---|---|---|
| `400 Bad Request` | Request sai cú pháp hoặc không thể phân tích | JSON hỏng, query parameter sai định dạng |
| `413 Content Too Large` | Body vượt giới hạn cho phép | Upload request quá lớn |
| `415 Unsupported Media Type` | Content-Type không được endpoint hỗ trợ | Gửi XML đến endpoint chỉ nhận JSON |
| `422 Unprocessable Content` | Cú pháp hợp lệ nhưng dữ liệu không đáp ứng quy tắc xử lý | Email sai định dạng, ngày kết thúc trước ngày bắt đầu |

Một API có thể chọn `400` cho nhiều loại validation error theo hợp đồng đã công bố. Nếu tách `400` cho lỗi cú pháp và `422` cho lỗi ngữ nghĩa, cần áp dụng quy ước đó nhất quán trên toàn API. Không nên để cùng một lỗi lúc trả `400`, lúc trả `422` chỉ vì đi qua controller khác nhau.

Ví dụ request có JSON hợp lệ nhưng giá trị không thỏa quy tắc:

```http
POST /api/reservations
Content-Type: application/json

{
  "startDate": "2026-12-20",
  "endDate": "2026-12-10"
}
```

Response có thể là `422 Unprocessable Content` với thông tin field `endDate` cần điều chỉnh. Không phản hồi lại toàn bộ payload nếu payload có thông tin cá nhân, token, ghi chú riêng tư hoặc dữ liệu nhạy cảm.

### 3.1. Validation không được thay thế phân quyền

Một request có cấu trúc hợp lệ vẫn có thể không được phép. Ví dụ `tenantId` là UUID hợp lệ nhưng actor không được chọn tenant đó; `ownerId` tồn tại nhưng không thuộc phạm vi người gọi; `role` có giá trị hợp lệ trong enum nhưng user không được thay đổi role.

Phân biệt:

- Dữ liệu sai định dạng hoặc sai quy tắc chung: thường là `400` hoặc `422` theo hợp đồng.
- Dữ liệu tham chiếu đến object ngoài phạm vi: áp dụng chính sách `403` hoặc `404` để bảo vệ object.
- Field hợp lệ về kiểu nhưng actor không có quyền ghi: `403`, hoặc từ chối toàn bộ request theo chính sách field-level.
- Trạng thái hiện tại không cho phép thao tác: thường là `409`.

Đừng dùng `422` để che mọi lỗi bảo mật. Nếu actor gửi `role: ADMIN` và hệ thống trả lỗi validation `role is not editable`, response có thể vô tình tiết lộ field đặc quyền hoặc cho phép dò schema. Cần định nghĩa rõ API có bỏ qua field không được phép, từ chối toàn bộ request hay trả lỗi quyền; lựa chọn đó phải nhất quán và không làm lộ thông tin nội bộ.

## 4. Status code cho xung đột trạng thái và điều kiện cập nhật

### 4.1. 409 Conflict

`409 Conflict` phù hợp khi request hợp lệ nhưng không thể hoàn tất vì xung đột với trạng thái hiện tại của tài nguyên hoặc quy tắc nghiệp vụ.

Ví dụ:

- Duyệt hóa đơn đã bị hủy.
- Thanh toán đơn hàng đã thanh toán.
- Tạo username hoặc mã nghiệp vụ đang được sử dụng, nếu hợp đồng biểu diễn đây là xung đột tài nguyên.
- Dùng cùng idempotency key nhưng gửi payload khác với request ban đầu.
- Hai thao tác đồng thời cùng cố chuyển một tài nguyên sang trạng thái không tương thích.

Ví dụ response:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "State conflict",
  "status": 409,
  "detail": "The invoice cannot be approved in its current state."
}
```

Chỉ cung cấp trạng thái hiện tại nếu actor được phép biết thông tin đó. Nếu tài nguyên đang bị che giấu theo chính sách BOLA, không dùng `409` để tiết lộ rằng object tồn tại.

### 4.2. 412 Precondition Failed và 428 Precondition Required

Khi API hỗ trợ cập nhật có điều kiện, `ETag` và `If-Match` giúp tránh ghi đè thay đổi mới hơn:

```http
GET /api/invoices/4812
```

```http
HTTP/1.1 200 OK
ETag: "invoice-v7"
```

Client gửi version đã đọc khi cập nhật:

```http
PATCH /api/invoices/4812
If-Match: "invoice-v7"
Content-Type: application/json

{
  "memo": "Updated note"
}
```

Nếu tài nguyên đã thay đổi thành version khác, server trả `412 Precondition Failed`. Nếu API yêu cầu client gửi điều kiện nhưng client không gửi, có thể trả `428 Precondition Required`. Hai mã này giúp client phân biệt xung đột dữ liệu với request thiếu điều kiện cập nhật.

ETag không thay thế authorization. Server vẫn phải kiểm tra actor có quyền trên object và field trước khi ghi. Với tài nguyên nhạy cảm, cần bảo đảm ETag không trở thành kênh tiết lộ thông tin hoặc cho phép cache không phù hợp.

## 5. Status code cho method, nội dung và tài nguyên

Một số mã giúp client nhận biết cách gọi API không phù hợp:

- `404 Not Found`: route hoặc tài nguyên không được tìm thấy, hoặc object được che giấu theo chính sách.
- `405 Method Not Allowed`: route tồn tại nhưng không hỗ trợ HTTP method được gửi. Response nên có header `Allow` liệt kê method được hỗ trợ.
- `406 Not Acceptable`: server không thể tạo representation phù hợp với các định dạng trong `Accept`, nếu API có thương lượng nội dung.
- `415 Unsupported Media Type`: định dạng body không được hỗ trợ.
- `413 Content Too Large`: kích thước request vượt giới hạn.

Các giới hạn kích thước là một phần của bảo vệ tài nguyên. Ví dụ, API upload nên giới hạn kích thước file, tổng kích thước request, số phần tử trong batch và độ sâu JSON. Trả `413` cho request vượt giới hạn giúp client nhận biết cần giảm kích thước. Đừng đọc toàn bộ body vào bộ nhớ rồi mới kiểm tra giới hạn; giới hạn cần được áp dụng sớm ở gateway, web server và tầng ứng dụng phù hợp.

Không trả `405` chỉ vì actor thiếu quyền. Method được hỗ trợ nhưng actor không được thực hiện hành động thường là `403` hoặc `404` theo chính sách che giấu. `405` mô tả khả năng của endpoint, không mô tả quyền của người gọi.

## 6. Status code cho rate limit và sự cố dịch vụ

### 6.1. 429 Too Many Requests

Dùng `429` khi client hoặc actor vượt giới hạn tần suất/số lượng được áp dụng. Ví dụ:

- Gửi quá nhiều lần thử đăng nhập hoặc OTP.
- Gọi API tìm kiếm quá nhanh.
- Tạo quá nhiều tài nguyên trong một khoảng thời gian.
- Vượt quota export hoặc upload.
- Thực hiện quá nhiều lần thử một thao tác nhạy cảm.

Response có thể cung cấp `Retry-After` để chỉ thời điểm hoặc khoảng thời gian client nên chờ trước khi gửi lại:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json
Cache-Control: no-store
```

Không tiết lộ ngưỡng chống lạm dụng chi tiết nếu thông tin đó giúp kẻ tấn công tối ưu hành vi né tránh. Client hợp lệ chỉ cần biết request bị giới hạn và khi nào có thể thử lại. Với login hoặc OTP, tránh response khác nhau tiết lộ tài khoản có tồn tại hay không.

Rate limit có thể được áp dụng theo IP, API key, user, tenant, route hoặc loại hành động. Không dựa duy nhất vào IP vì nhiều người dùng hợp lệ có thể chia sẻ NAT, còn kẻ tấn công có thể phân tán nguồn gửi. Với hành động nhạy cảm, kết hợp quota, giới hạn đồng thời, cooldown và kiểm soát nghiệp vụ.

### 6.2. Phân biệt 429 và 503

`429` nói rằng request bị giới hạn theo chính sách của client/actor hoặc quota. `503 Service Unavailable` nói rằng dịch vụ tạm thời không thể xử lý request do quá tải, bảo trì hoặc phụ thuộc không sẵn sàng.

| Tình huống | Status phù hợp |
|---|---|
| Một user vượt giới hạn gọi API | `429` |
| Tenant hết quota theo hợp đồng | `429` hoặc lỗi nghiệp vụ được quy định rõ; cần một quy ước thống nhất |
| API đang bảo trì hoặc quá tải toàn hệ thống | `503` |
| Dịch vụ phụ thuộc không phản hồi và API không thể hoàn tất | Thường là `503`, tùy vai trò của dependency |
| Gateway nhận phản hồi không hợp lệ từ upstream | `502 Bad Gateway` |
| Gateway chờ upstream quá thời hạn | `504 Gateway Timeout` |

Có thể gửi `Retry-After` với `503` nếu server biết khi nào nên thử lại. Client không nên retry vô hạn hoặc đồng loạt ngay lập tức; cần exponential backoff, jitter và giới hạn số lần thử. Với thao tác có side effect, chỉ retry khi có idempotency hoặc cơ chế bảo đảm không tạo tác động lặp.

## 7. Dùng 2xx đúng với kết quả thực tế

Nhóm `2xx` biểu thị request đã được xử lý thành công theo ngữ nghĩa của method:

| Status | Ý nghĩa thường dùng | Ví dụ |
|---|---|---|
| `200 OK` | Request thành công và có representation hoặc kết quả | Đọc tài nguyên, cập nhật có trả body |
| `201 Created` | Đã tạo tài nguyên | Tạo hóa đơn mới; thường kèm `Location` |
| `202 Accepted` | Đã nhận request để xử lý, nhưng công việc chưa hoàn tất | Bắt đầu export bất đồng bộ |
| `204 No Content` | Thành công nhưng không có response body | Xóa thành công hoặc cập nhật không trả dữ liệu |

Không trả `200 OK` với body kiểu `{ "success": false }` cho lỗi xác thực, phân quyền hoặc validation. Cách làm này phá vỡ hợp đồng HTTP, khiến client và monitoring hiểu nhầm request thành công. Hãy dùng status code đúng và một schema lỗi ổn định.

Với `202 Accepted`, cần nói rõ đây là chấp nhận xử lý chứ chưa phải hoàn tất. Có thể trả URL của operation resource trong `Location` hoặc body. Khi client truy vấn operation resource, endpoint đó vẫn phải kiểm tra quyền trên job, dữ liệu đầu ra và tenant tương ứng. Không để ID job trở thành bearer secret thay thế authorization.

`204 No Content` không được có response body. Nếu thao tác bị từ chối hoặc chưa thực hiện do trạng thái không hợp lệ, không trả `204` chỉ để tránh giải thích lỗi.

## 8. Chuẩn hóa cấu trúc lỗi

Các endpoint nên dùng một định dạng lỗi nhất quán để client xử lý mà không phải phân tích nhiều schema khác nhau. Một lựa chọn phổ biến là Problem Details for HTTP APIs (`application/problem+json`). Ví dụ:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store
```

```json
{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/api/reservations",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "endDate",
      "code": "DATE_ORDER_INVALID",
      "message": "End date must be after start date."
    }
  ],
  "traceId": "01J..."
}
```

Các thuộc tính chuẩn thường gồm `type`, `title`, `status`, `detail` và `instance`. API có thể bổ sung `code`, `errors` hoặc `traceId` để client và đội vận hành xử lý thuận tiện. Các extension phải có ý nghĩa ổn định và được tài liệu hóa.

### 8.1. Nguyên tắc an toàn cho error body

- `status` trong body phải khớp với HTTP status trên response.
- `title` và `code` nên ổn định để client có thể xử lý bằng mã, không phụ thuộc câu chữ.
- `detail` chỉ cung cấp thông tin mà người gọi được phép biết.
- Validation error chỉ nêu field và quy tắc cần sửa; không echo dữ liệu bí mật mà client gửi lên.
- Không trả stack trace, SQL, tên bảng/cột nội bộ, đường dẫn filesystem, secret, token hoặc nội dung exception nguyên bản.
- `instance` không nên chứa query string hoặc dữ liệu nhạy cảm được client truyền vào.
- `traceId` là mã tra cứu log, không phải credential và không được dùng để cấp quyền.
- Response lỗi có chứa thông tin cá nhân hoặc dữ liệu riêng tư nên có chính sách cache phù hợp, thường là `Cache-Control: no-store`.

Không nên để framework hoặc reverse proxy trả HTML error page trong khi API còn lại trả JSON. Các lỗi phát sinh trước khi request vào application, như body quá lớn hoặc route không tồn tại, cũng cần được cấu hình để có format và header phù hợp với hợp đồng API.

## 9. Thiết kế một bảng ánh xạ lỗi thống nhất

Trước khi triển khai, hãy thống nhất một bảng ánh xạ giữa loại kết quả nội bộ và HTTP status. Ví dụ:

| Kết quả trong hệ thống | HTTP status gợi ý | Ghi chú bảo mật |
|---|---|---|
| Thiếu hoặc credential không hợp lệ | `401` | Có `WWW-Authenticate` phù hợp; không tiết lộ chi tiết token |
| Actor đã xác thực nhưng thiếu quyền action/field | `403` | Chỉ dùng khi việc tiết lộ object là chấp nhận được |
| Object không tồn tại hoặc cần che giấu | `404` | Không phân biệt object vắng mặt và object ngoài phạm vi |
| Request sai cú pháp | `400` | Không echo payload nhạy cảm |
| Dữ liệu hợp lệ về cú pháp nhưng sai quy tắc | `422` | Field-level message an toàn |
| Workflow hoặc tài nguyên xung đột trạng thái | `409` | Chỉ tiết lộ trạng thái nếu actor được phép biết |
| Điều kiện `If-Match` không còn đúng | `412` | Hỗ trợ xử lý cập nhật đồng thời |
| Thiếu precondition bắt buộc | `428` | Nêu điều kiện client cần gửi |
| Method không được hỗ trợ | `405` | Có `Allow` |
| Content-Type không hỗ trợ | `415` | Không phân tích body theo định dạng khác |
| Body quá lớn | `413` | Giới hạn sớm để bảo vệ tài nguyên |
| Vượt rate limit/quota | `429` | Có thể kèm `Retry-After` |
| Dịch vụ tạm thời không khả dụng | `503` | Có thể kèm `Retry-After`; tránh retry storm |
| Lỗi không dự kiến trong server | `500` | Thông báo chung, chi tiết chỉ ở log nội bộ |

Bảng trên là quy ước khởi đầu, không phải phép ánh xạ máy móc cho mọi sản phẩm. Chủ sở hữu API cần quyết định rõ cách xử lý lỗi đặc thù, sau đó áp dụng đồng nhất trong controller, service, gateway và tài liệu API.

## 10. Triển khai trong ứng dụng API

### 10.1. Tách lỗi nghiệp vụ khỏi HTTP response

Service nên biểu diễn kết quả hoặc lỗi theo ngữ nghĩa nghiệp vụ. Tầng HTTP chịu trách nhiệm ánh xạ sang status code và schema response. Cách này tránh việc mỗi service tự trả mã khác nhau cho cùng một lỗi.

Ví dụ minh họa:

```java
public class InvoiceService {
    public Invoice getInvoice(UUID id, CurrentUser actor) {
        Invoice invoice = repository
            .findByIdAndTenantId(id, actor.tenantId())
            .orElseThrow(InvoiceNotFoundException::new);

        authorization.requireCanRead(actor, invoice);
        return invoice;
    }
}
```

Nếu chính sách yêu cầu che giấu object ngoài phạm vi, `InvoiceNotFoundException` có thể được dùng cho cả object không tồn tại và object không được actor phép biết đến. Nếu sản phẩm chọn `403`, service/policy cần phát sinh lỗi quyền riêng. Không nên để controller tự kiểm tra ID theo cách khác với service.

Ở tầng HTTP, exception handler tập trung có thể ánh xạ lỗi:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(InvoiceNotFoundException.class)
    ResponseEntity<ProblemDetail> handleNotFound() {
        ProblemDetail body = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        body.setTitle("Resource not found");
        body.setDetail("The requested resource was not found.");
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .cacheControl(CacheControl.noStore())
            .body(body);
    }

    @ExceptionHandler(InvalidInvoiceStateException.class)
    ResponseEntity<ProblemDetail> handleConflict() {
        ProblemDetail body = ProblemDetail.forStatus(HttpStatus.CONFLICT);
        body.setTitle("State conflict");
        body.setDetail("The operation is not valid in the current state.");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
```

Đây là ví dụ rút gọn. Lỗi xác thực thường được xử lý ở security filter chain bằng `AuthenticationEntryPoint`; lỗi phân quyền có thể đi qua `AccessDeniedHandler`. Cần cấu hình các thành phần này cùng schema Problem Details, để request bị chặn trước controller vẫn có response nhất quán. `@RestControllerAdvice` đơn lẻ không xử lý được mọi lỗi phát sinh ở filter, gateway hoặc web server.

### 10.2. Không dùng status code để thay thế audit log

Status code cho client biết kết quả ở mức giao thức. Log bảo mật cần giữ thêm ngữ cảnh để điều tra:

- Actor hoặc service identity và tenant đã xác định.
- Route, method, action và loại tài nguyên.
- Kết quả policy: allow, deny hoặc không đủ dữ liệu để quyết định.
- Mã lỗi nội bộ, correlation ID/trace ID và thời điểm.
- Nguồn giới hạn bị vượt, nếu có, ở mức không làm lộ cấu hình chống lạm dụng.

Không ghi access token, mật khẩu, API key, dữ liệu thanh toán hoặc toàn bộ request body nhạy cảm. Log cũng cần được kiểm soát quyền đọc, thời hạn lưu và khả năng chống sửa đổi. `404` hoặc `403` trên response không cho biết đầy đủ lý do nội bộ; log mới là nơi lưu chi tiết phục vụ vận hành.

## 11. Những lỗi thiết kế thường gặp

| Cách làm sai | Hệ quả | Cách sửa |
|---|---|---|
| Trả `200` cho mọi response và đặt `success=false` trong body | Client, proxy và monitoring hiểu sai kết quả | Dùng status code HTTP đúng |
| Dùng `401` cho cả lỗi thiếu quyền | Client yêu cầu đăng nhập lại dù token hợp lệ | Phân biệt `401` và `403` |
| Trả `403` cho mọi object ID không truy cập được | Có thể tiết lộ object tồn tại | Áp dụng chính sách `404` che giấu khi phù hợp |
| Trả `404` cho cả route sai và method sai | Client khó phân biệt endpoint không tồn tại với method không hỗ trợ | Dùng `405` cho route tồn tại nhưng method không hợp lệ |
| Trả `500` cho validation error | Che mất lỗi hợp đồng, gây cảnh báo vận hành giả | Dùng `400`/`422` phù hợp |
| Trả `400` cho lỗi nghiệp vụ trạng thái | Client không biết cần xử lý xung đột | Dùng `409` khi phù hợp |
| Dùng `429` cho lỗi hệ thống quá tải | Client có thể xử lý retry sai chính sách | Phân biệt giới hạn client với sự cố dịch vụ `503` |
| Trả stack trace hoặc exception message | Rò rỉ cấu trúc và thông tin nội bộ | Response an toàn, chi tiết ở log được bảo vệ |
| Mỗi controller tự định nghĩa error schema | Client phải xử lý nhiều biến thể | Chuẩn hóa handler và contract |

Một lỗi khác là kiểm tra quyền sau khi đã tạo side effect. Ví dụ server ghi thay đổi vào database, gửi email hoặc gọi cổng thanh toán rồi mới phát hiện actor không có quyền. Khi đó response `403` không thể hoàn tác tác động đã xảy ra. Authorization phải được kiểm tra trước hành động nhạy cảm và trong transaction hoặc workflow bảo đảm tính nhất quán phù hợp.

## 12. Kiểm thử tính nhất quán và rò rỉ thông tin

Kiểm thử status code cần bao gồm cả kết quả hợp lệ, từ chối quyền và các điều kiện lỗi. Với mỗi endpoint, tạo ma trận theo actor, object, action, field và trạng thái.

| Tình huống kiểm thử | Kết quả mong đợi |
|---|---|
| Không gửi token đến endpoint cần xác thực | `401` và challenge phù hợp |
| Token hết hạn hoặc sai chữ ký | `401`; không tiết lộ chi tiết xác minh token |
| User đã đăng nhập gọi chức năng ngoài quyền | `403` hoặc `404` theo chính sách object |
| ID không tồn tại và ID thuộc user khác | Response không phân biệt được nếu endpoint dùng chính sách che giấu |
| JSON sai cú pháp | `400` |
| JSON hợp lệ nhưng vi phạm quy tắc field | `422` hoặc quy ước validation đã công bố |
| Cập nhật trạng thái không hợp lệ | `409` |
| ETag cũ trong `If-Match` | `412` |
| Gửi method không được hỗ trợ | `405` kèm `Allow` |
| Gửi Content-Type không được hỗ trợ | `415` |
| Body vượt giới hạn | `413` |
| Vượt giới hạn request | `429`, có hướng dẫn retry phù hợp |
| Dịch vụ tạm thời không khả dụng | `503`, không lộ thông tin dependency nhạy cảm |
| Lỗi ngoài dự kiến | `500` với thông báo chung và trace ID |

Ngoài mã trạng thái, hãy xác minh:

- Body có schema thống nhất và `status` khớp với HTTP status.
- Header `WWW-Authenticate`, `Allow`, `Retry-After`, `Content-Type` và cache control xuất hiện đúng trường hợp.
- Response không chứa stack trace, token, SQL, dữ liệu field bị cấm hoặc tên tài nguyên ngoài phạm vi.
- Nhánh bị từ chối không tạo database write, gửi message, gửi email hoặc gọi dịch vụ thanh toán.
- Client không thể dùng khác biệt lớn về body, header hoặc thời gian để dò object nhạy cảm.
- Retry sau `429`, `503` hoặc timeout không tạo side effect lặp; thao tác nhạy cảm có idempotency phù hợp.
- Các endpoint cùng loại và các phiên bản API áp dụng cùng quy ước.

Nên có contract test cho error response, integration test qua security filter và controller, cùng kiểm thử end-to-end ở gateway. Unit test cho mapper không đủ để chứng minh request bị chặn ở tầng xác thực hoặc reverse proxy cũng có response đúng.

## 13. Checklist review status code cho API

- [ ] `401` chỉ dùng cho lỗi xác thực/credential; có challenge phù hợp.
- [ ] `403` biểu thị actor đã được xác thực nhưng không có quyền thực hiện hành động.
- [ ] Chính sách `404` che giấu object được áp dụng nhất quán và không làm lộ tài nguyên qua body/header/thời gian rõ rệt.
- [ ] Lỗi cú pháp và validation được phân biệt theo một quy ước `400`/`422` thống nhất.
- [ ] Xung đột workflow và cập nhật đồng thời dùng `409`/`412` phù hợp.
- [ ] `405`, `413`, `415` phản ánh đúng method, kích thước và media type.
- [ ] `429` dành cho giới hạn client/quota; `503` dành cho dịch vụ tạm thời không khả dụng.
- [ ] `200`, `201`, `202` và `204` phản ánh đúng mức độ hoàn tất của thao tác.
- [ ] Error body có schema ổn định, không lộ stack trace, secret hoặc dữ liệu ngoài quyền.
- [ ] Header xác thực, retry, method và cache được thiết lập phù hợp.
- [ ] Lỗi bảo mật được log đủ để điều tra mà không ghi dữ liệu nhạy cảm.
- [ ] Test chứng minh từ chối quyền không tạo side effect và các endpoint cùng loại trả kết quả nhất quán.

Status code tốt giúp client và hệ thống vận hành hiểu chính xác điều gì đã xảy ra. Khi `401`, `403`, `404`, `409`, `422`, `429` và các mã khác được dùng đúng ngữ nghĩa, có chính sách che giấu thông tin rõ ràng và được kiểm thử trên mọi tầng xử lý, API vừa dễ tích hợp hơn vừa giảm nguy cơ rò rỉ dữ liệu, retry sai và xử lý nghiệp vụ trái phép.
