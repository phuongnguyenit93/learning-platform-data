# Quy tắc phản hồi khi cùng thao tác được gọi lại

## 1. Vấn đề: client gửi lại một thao tác thì API phải trả gì?

Trong thực tế, client không phải lúc nào cũng nhận được phản hồi của request đã gửi. Kết nối có thể bị ngắt sau khi server ghi dữ liệu, gateway có thể timeout, ứng dụng di động có thể gửi lại khi mạng hồi phục hoặc một hệ thống hàng đợi có thể phân phối cùng thông điệp nhiều lần. Khi đó câu hỏi quan trọng là: **nếu cùng một thao tác được gọi lại, trạng thái tài nguyên có thay đổi thêm lần nữa không và HTTP response cần biểu diễn kết quả như thế nào?**

Ví dụ người dùng nhấn **Tạo đơn hàng**. Lần POST đầu đã ghi thành công nhưng response bị mất. Nếu client tự động gửi lại một POST tương tự, server có thể tạo hai đơn hàng. Ngược lại, nếu client lặp lại lệnh **DELETE /orders/123**, API có thể bảo đảm cuối cùng đơn hàng không còn tồn tại, dù mã phản hồi ở các lần gọi có thể khác.

Bài học thuộc chương **Thao tác tài nguyên** của module **INTEGRATION_API_REST**. Người học sẽ kết hợp resource, URI, HTTP method, status code, hợp đồng dữ liệu, idempotency, xác thực/phân quyền, OpenAPI và kiểm thử Java/Spring để thiết kế quy tắc phản hồi nhất quán.

Mục tiêu:

1. Phân biệt **gọi lặp lại**, **retry**, **idempotent** và **phản hồi giống nhau**.
2. Nêu quy tắc cho GET, HEAD, PUT, DELETE, POST và PATCH khi cùng thao tác được gửi lại.
3. Chọn mã **200, 201, 202, 204, 304, 404, 409, 410, 412, 428, 429, 503** theo trạng thái thực tế và hợp đồng.
4. Dùng **Idempotency-Key**, điều kiện **If-Match/If-None-Match**, ETag và khóa duy nhất để xử lý retry, ghi đồng thời.
5. Viết test chứng minh không nhân đôi tác dụng nghiệp vụ, ngay cả khi phản hồi đầu tiên bị thất lạc.
6. Thiết kế hợp đồng API có thể triển khai và kiểm chứng với Spring MVC, database và OpenAPI.

## 2. Idempotency mô tả hiệu ứng, không yêu cầu response phải giống hệt

Theo ngữ nghĩa HTTP, một phương thức **idempotent** khi hiệu ứng dự kiến đối với server của nhiều request **giống hệt nhau** tương đương với hiệu ứng của một request duy nhất. Điều đó **không** có nghĩa status code, thời gian phản hồi hoặc body phải giữ nguyên ở mọi lần gọi.

Xét thao tác xóa:

~~~http
DELETE /api/v1/orders/123 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Lần đầu xóa thành công:

~~~http
HTTP/1.1 204 No Content
~~~

Nếu client gửi lại cùng DELETE và đơn đã không còn, một API có thể tiếp tục trả **204 No Content** theo hợp đồng “đảm bảo tài nguyên không còn”; API khác có thể trả **404 Not Found** để thông báo trạng thái hiện tại. **Cả hai cách đều có thể bảo toàn tính idempotent** của hiệu ứng xóa.

Phân biệt ba khái niệm:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Safe method** | Mục đích request có chỉ là lấy thông tin, không yêu cầu thay đổi trạng thái? | GET, HEAD và OPTIONS là safe theo HTTP; việc ghi log truy cập không làm GET thành thao tác ghi nghiệp vụ. |
| **Idempotent method** | Gửi cùng request nhiều lần có cùng hiệu ứng mong muốn như gửi một lần? | GET, HEAD, PUT, DELETE và các phương thức safe vốn idempotent theo ngữ nghĩa HTTP. |
| **Response replay** | API có chủ động trả lại đúng kết quả đã lưu cho lần request trước không? | POST kèm Idempotency-Key có thể trả lại 201, Location và body của lần tạo đơn đầu. |

Đối với GET, representation có thể thay đổi theo thời gian do người dùng khác sửa tài nguyên; GET vẫn là idempotent vì chính request GET không nhằm thay đổi tài nguyên. Với DELETE, response đầu 204 và response sau 404 không làm mất tính idempotent.

### Gọi lại “giống hệt” nghĩa là gì?

Đánh giá idempotency phải dựa vào **cùng method, URI, nội dung và điều kiện có liên quan trong cùng ngữ cảnh quyền**. Hai request PUT với body khác nhau không phải cùng một thao tác. Hai POST có nội dung giống nhau nhưng không có khóa chống trùng có thể là hai yêu cầu tạo hai tài nguyên độc lập.

Các cơ chế ở tầng nghiệp vụ như gửi email, trừ tiền hoặc phát sự kiện có thể **không idempotent**, ngay cả khi thao tác thay đổi database có vẻ idempotent. Vì vậy cần tách **trạng thái tài nguyên** và **tác dụng phụ bên ngoài** để kiểm chứng.

## 3. Ma trận phương thức HTTP khi gọi lặp lại

| Method | Ngữ nghĩa chính | Idempotent mặc định? | Quy tắc phản hồi thường gặp |
| --- | --- | --- | --- |
| **GET** | Lấy representation | Có, đồng thời safe | **200 OK** nếu trả nội dung, **304 Not Modified** khi request có điều kiện và representation không đổi, **404** nếu không có hoặc không cho biết sự tồn tại. |
| **HEAD** | Lấy metadata tương ứng GET, không có body | Có, đồng thời safe | **200**, **304** khi có điều kiện phù hợp, **404**...; HEAD không có message body. |
| **PUT** | Tạo hoặc thay thế trạng thái tại URI đã biết | Có | Lần đầu tạo: **201 Created**; lần sau thay thế: **200 OK** (có body) hoặc **204 No Content**. |
| **DELETE** | Yêu cầu loại bỏ liên kết hiện tại giữa URI và tài nguyên | Có | Thường **204** khi đã xóa; lần sau có thể **204**, **404** hoặc **410** tùy hợp đồng; **202** nếu việc xóa được chấp nhận nhưng chưa hoàn tất. |
| **POST** | Gửi nội dung để resource đích xử lý theo ngữ nghĩa riêng | Không | Mỗi lần có thể tạo mới (**201**), hoặc dùng cơ chế idempotency theo nghiệp vụ để trả về cùng kết quả tài nguyên. |
| **PATCH** | Sửa một phần theo tập lệnh thay đổi | Không mặc định | Có thể thiết kế idempotent; thường **200** hoặc **204**; dùng điều kiện phiên bản để tránh ghi đè xung đột. |

**Lưu ý:** PUT và DELETE idempotent theo **hiệu ứng mong muốn**. Khi ứng dụng gắn các tác dụng phụ không được kiểm soát vào mỗi lần gọi (ví dụ mỗi lần DELETE đều phát hóa đơn phí), cách triển khai có thể vi phạm hợp đồng idempotent dù đã dùng đúng method.

Một API có thể dùng một phương thức an toàn hoặc idempotent nhưng trả **401/403/429/5xx** vì xác thực, phân quyền, giới hạn tốc độ hoặc hạ tầng. Mã trạng thái phải phản ánh kết quả của **lần HTTP request cụ thể**, còn quy tắc dữ liệu phải được kiểm tra độc lập.

## 4. GET/HEAD: gọi lại không được tạo thay đổi nghiệp vụ

Giả sử client đọc:

~~~http
GET /api/v1/orders/123 HTTP/1.1
Accept: application/json
~~~

Server trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-123-v4"

{"id":"123","status":"PENDING","version":4}
~~~

Lần GET sau có thể vẫn 200 với dữ liệu cũ, hoặc 200 với representation mới nếu người khác đã cập nhật. Điều này không trái idempotency. **Server không được biến GET thành thao tác xác nhận thanh toán, xóa đơn hoặc chuyển trạng thái đơn** chỉ vì endpoint dễ gọi từ trình duyệt.

### Dùng điều kiện GET để tránh truyền lại nội dung không đổi

Client gửi:

~~~http
GET /api/v1/orders/123 HTTP/1.1
If-None-Match: "order-123-v4"
~~~

Nếu representation hiện tại có ETag tương ứng và điều kiện không thay đổi được thỏa, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "order-123-v4"
~~~

**304 không phải một representation JSON rỗng theo kiểu 200**. Client có thể sử dụng dữ liệu đã lưu theo các quy tắc cache/validation áp dụng. Không dùng 304 đơn thuần vì “đây là lần GET thứ hai”; cần có request có điều kiện và đánh giá validator đúng.

**HEAD** có thể dùng để kiểm tra metadata/status mà không nhận response body. Với 404 hoặc 403 cũng phải tuân theo quy tắc quyền và chính sách che giấu tài nguyên.

## 5. PUT: trạng thái cuối idempotent nhưng status có thể đổi

PUT thường nhắm đến **URI tài nguyên xác định trước** và yêu cầu tạo mới hoặc thay thế representation theo hợp đồng.

~~~http
PUT /api/v1/settings/users/u-42 HTTP/1.1
Content-Type: application/json

{"theme":"dark","language":"vi"}
~~~

Nếu URI chưa có resource, lần gọi đầu có thể tạo và trả:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/settings/users/u-42
~~~

Gọi lại cùng PUT khi resource đã tồn tại:

~~~http
HTTP/1.1 204 No Content
~~~

Hai response khác mã nhưng sau cả hai request, cấu hình vẫn là **theme=dark, language=vi**. Đây là ví dụ chính về idempotency **không đòi response giống nhau**.

Nếu server trả representation sau khi thay thế, mã **200 OK** cũng phù hợp. Khi PUT lần đầu tạo mới thành công, HTTP yêu cầu phản hồi **201 Created**; khi thay thế một representation đã tồn tại, server dùng **200** hoặc **204** cho thành công.

### PUT không phải cập nhật từng trường tùy ý

Nếu contract định nghĩa PUT là **thay thế toàn bộ representation**, gửi body thiếu trường có thể đồng nghĩa loại bỏ/đặt lại trường. Dùng PATCH cho cập nhật một phần khi hợp đồng hỗ trợ. Đừng triển khai PUT như PATCH ngầm theo endpoint này nhưng thay thế toàn bộ ở endpoint khác mà không ghi rõ.

Tính idempotent của PUT cũng không loại bỏ **lost update**. Ví dụ:

1. Client A GET version 4.
2. Client B sửa bản ghi thành version 5.
3. Client A PUT lại representation cũ, ghi đè thay đổi của B.

Muốn tránh, cần kiểm soát đồng thời bằng điều kiện như **If-Match** hoặc version nghiệp vụ; xem phần 9.

## 6. DELETE: chọn quy tắc rõ ràng khi tài nguyên đã không còn

Với **DELETE /api/v1/orders/123**, có hai cách thiết kế phổ biến:

| Chính sách | Lần đầu xóa thành công | Gọi lại sau khi đã xóa | Đặc điểm |
| --- | --- | --- | --- |
| **“Đảm bảo không còn”** | 204 No Content | 204 No Content | Client không cần phân biệt vừa xóa và đã xóa; dễ retry. |
| **“Phân biệt không tồn tại”** | 204 No Content | 404 Not Found | Client biết URI hiện không có tài nguyên; vẫn idempotent về hiệu ứng. |

**410 Gone** có thể phù hợp khi server biết tài nguyên trước đó tồn tại nhưng hiện đã không còn và tình trạng đó có tính lâu dài. Không nhất thiết phải dùng 410 cho mọi tài nguyên đã xóa; nhiều hệ thống không giữ tombstone hoặc không muốn tiết lộ thông tin lịch sử tồn tại.

### Không phải lúc nào DELETE cũng hoàn tất ngay

Nếu một thao tác xóa lớn cần chạy bất đồng bộ, server có thể trả **202 Accepted**, kèm URI trạng thái tác vụ và hướng dẫn theo dõi. **202** không xác nhận việc xóa đã hoàn tất, nên client phải kiểm tra trạng thái thực tế.

Nếu xóa bị cấm do nghiệp vụ (ví dụ đơn đã quyết toán), API có thể trả **409 Conflict** thay vì giả vờ đã xóa. Nếu caller không có quyền, dùng **403 Forbidden** hoặc **404 Not Found** theo chính sách bảo vệ sự tồn tại. Không trả 204 vô điều kiện khi chưa kiểm tra ràng buộc.

### Tác dụng phụ và sự kiện phải gắn với chuyển trạng thái thật

Ví dụ có endpoint xóa bản nháp:

~~~text
DELETE lần 1:
  Đang tồn tại -> Không tồn tại
  Ghi một sự kiện DraftDeleted -> 204

DELETE lần 2:
  Đã không tồn tại -> Vẫn không tồn tại
  Không ghi lại sự kiện nghiệp vụ -> 204 hoặc 404
~~~

Lưu ý phân biệt **audit log HTTP** có thể ghi mỗi lần request với **business event** chỉ nên phát khi có chuyển trạng thái thực. Nếu mỗi lần retry lại gửi email “đơn đã xóa” hay phát cùng side effect không được dedupe, trạng thái resource có thể đúng nhưng hệ thống tích hợp vẫn sai.

## 7. POST: hai request giống nhau có thể là hai lệnh tạo mới

Theo HTTP, **POST không idempotent mặc định**. Gửi cùng payload hai lần đến collection có thể tạo hai tài nguyên:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json

{"sku":"BOOK-42","quantity":1}
~~~

Phản hồi thứ nhất:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ord-1001
~~~

Nếu client gửi lại mà server không có chính sách chống trùng, phản hồi thứ hai có thể là:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ord-1002
~~~

Đây có thể là hành vi đúng với ứng dụng cho phép mua cùng sản phẩm nhiều lần, nhưng **không phù hợp** khi lần thứ hai chỉ là retry sau timeout của cùng một ý định tạo đơn. API phải phân biệt hai trường hợp đó bằng một hợp đồng rõ ràng.

### Idempotency-Key cho POST

Một cách triển khai phổ biến là client sinh **Idempotency-Key** mới cho mỗi **ý định nghiệp vụ duy nhất** và **tái sử dụng đúng key đó khi retry**:

~~~http
POST /api/v1/orders HTTP/1.1
Content-Type: application/json
Idempotency-Key: 7b9b9326-5cb8-4c43-8ee6-f955f6595367

{"sku":"BOOK-42","quantity":1}
~~~

Server lần đầu tạo **ord-1001**:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/ord-1001
Content-Type: application/json

{"id":"ord-1001","sku":"BOOK-42","quantity":1,"status":"PENDING"}
~~~

Khi nhận lại **cùng key và cùng nội dung yêu cầu trong cùng phạm vi quyền**, server có thể **replay phản hồi đã lưu**, bao gồm 201, Location và body của ord-1001. Việc trả lại cùng response trong ví dụ là **quy ước của API**, không phải tính năng tự có của POST.

Một hợp đồng khác có thể trả **200 OK** với tài nguyên đã tồn tại. Cả hai cách có thể hợp lý, nhưng phải được tài liệu hóa để client biết kết quả của retry. Nếu chọn replay response 201, cần bảo đảm không tạo thêm tài nguyên mới.

**Không nên** biến hai lần người dùng chủ động mua cùng sản phẩm thành một đơn chỉ vì body JSON giống nhau. Mỗi ý định mới phải có key mới; key chỉ dùng để nhận diện retry của cùng ý định.

## 8. Hợp đồng Idempotency-Key phải định nghĩa những gì?

Tên header **Idempotency-Key** được nhiều API sử dụng, nhưng server và client vẫn cần thống nhất đầy đủ quy tắc: một header tự nó không bảo đảm chống trùng.

| Khía cạnh | Quy tắc cần công bố | Lỗi có thể xảy ra nếu bỏ qua |
| --- | --- | --- |
| **Phạm vi key** | Ràng buộc với tenant/principal, endpoint hoặc loại thao tác theo chính sách | User khác có thể nhận dữ liệu/response đã lưu của người khác |
| **Một ý định duy nhất** | Một key cho một lần tạo hợp lệ; retry giữ nguyên key | Dùng lại key cho lệnh mới sẽ làm mất thao tác |
| **Fingerprint** | So sánh method, đích, các tham số nghiệp vụ và body đã chuẩn hóa | Cùng key nhưng khác payload lại bị coi là retry hợp lệ |
| **Concurrency** | Chỉ một request được thực thi nghiệp vụ; request trùng đang chạy phải chờ, nhận trạng thái pending hoặc lỗi được định nghĩa | Hai node xử lý cùng key và tạo trùng |
| **Kết quả cuối** | Lưu tài nguyên đã tạo, status, Location/body hoặc đủ thông tin tái tạo response | Retry không biết đơn hàng đã tạo ở đâu |
| **Thời hạn lưu** | TTL/retention đủ cho cửa sổ retry dự kiến | Key hết hạn làm request cũ có thể tạo lại |
| **Lỗi và tái thử** | Lỗi nào được lưu/replay, lỗi nào cho phép retry; xử lý trạng thái chưa rõ | Replayed lỗi 500 không đúng, hoặc retry nhân đôi side effect |
| **Bảo vệ dữ liệu** | Không đặt token/PII vào key và không lộ response liên tenant | Rò rỉ thông tin qua cơ chế idempotency |

Một quy ước mẫu:

- Key **không có** trên endpoint yêu cầu key: trả lỗi được hợp đồng định nghĩa, ví dụ **400 Bad Request** kèm mô tả.
- Key mới, request hợp lệ: thực hiện đúng một lần, trả kết quả tạo mới.
- Cùng key và **cùng fingerprint**, đã hoàn tất: trả lại kết quả đã lưu.
- Cùng key nhưng **fingerprint khác**: trả **409 Conflict** và không thực hiện lệnh mới.
- Cùng key đang được xử lý bởi request khác: trả **409 Conflict** với thông tin “in progress”, hoặc **202 Accepted** kèm operation resource nếu API thiết kế mô hình bất đồng bộ; cũng có thể chờ ngắn và replay khi hoàn tất. Phải chọn và công bố một chính sách.

**Không coi 409 là một tín hiệu luôn được tự động retry.** Client chỉ retry sau khi biết nguyên nhân là request cùng key đang xử lý và đã tuân thủ backoff/quy định hợp đồng. Nếu 409 vì payload khác hoặc xung đột trạng thái, phải sửa request hoặc xử lý xung đột trước.

### Về cách tạo fingerprint

Không nên so sánh body JSON bằng chuỗi nguyên văn nếu hợp đồng coi thứ tự thuộc tính hoặc khoảng trắng là không quan trọng. Có thể tạo fingerprint từ representation đã chuẩn hóa và các tham số có tác động đến kết quả. Ngược lại, không được bỏ qua các trường thay đổi ý nghĩa nghiệp vụ (ví dụ currency, amount, resource owner).

### Retention không phải vô hạn

Một idempotency key có thể được lưu 24 giờ, 72 giờ hay thời gian khác do nghiệp vụ chọn. Sau khi hết hạn, server **có thể** không còn nhận ra retry cũ; phải nói rõ hành vi này. Với tác vụ tài chính hoặc đơn có khóa nghiệp vụ, cơ chế chống trùng có thể cần thêm **unique business constraint** hoặc reconciliation, không phụ thuộc duy nhất vào cache key có TTL.

## 9. Conditional requests: tránh ghi đè hoặc xóa sai phiên bản

Idempotency không đủ để kiểm soát **hai người cùng sửa tài nguyên**. HTTP cung cấp các precondition headers, trong đó **If-Match** và **If-None-Match** thường hữu ích.

### 9.1. If-Match để cập nhật đúng phiên bản

Giả sử GET trả ETag:

~~~http
HTTP/1.1 200 OK
ETag: "task-42-v7"
Content-Type: application/json

{"id":"42","title":"Bản nháp","version":7}
~~~

Client sửa tiêu đề:

~~~http
PATCH /api/v1/tasks/42 HTTP/1.1
If-Match: "task-42-v7"
Content-Type: application/merge-patch+json

{"title":"Hoàn thành"}
~~~

Nếu ETag hiện tại vẫn là **"task-42-v7"**, server áp dụng thay đổi và có thể trả 200 kèm representation mới, hoặc 204 không body. Nếu tài nguyên đã đổi thành version 8 trước đó, precondition thất bại; response thường là:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Precondition Failed",
  "status": 412,
  "detail": "Phiên bản tài nguyên không còn khớp"
}
~~~

Client có thể GET phiên bản mới, cho người dùng xem xung đột rồi thực hiện lệnh cập nhật mới với ETag đúng. **Không retry vô hạn cùng If-Match cũ**.

Khi server yêu cầu client luôn cung cấp precondition cho cập nhật có nguy cơ lost update nhưng client bỏ qua header, có thể dùng **428 Precondition Required**. 428 khác 412: một mã nói **thiếu điều kiện bắt buộc**, mã kia nói **điều kiện được gửi nhưng không đúng**.

### 9.2. If-None-Match: * để tạo nếu chưa tồn tại

Client có URI cụ thể và muốn tạo mới **chỉ nếu resource chưa có**:

~~~http
PUT /api/v1/settings/users/u-42 HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"theme":"dark"}
~~~

- Lần đầu URI chưa có: server tạo tài nguyên và trả **201 Created**.
- Lần sau resource đã tồn tại: điều kiện **If-None-Match: \*** không thỏa; trả **412 Precondition Failed**.

Kết quả dữ liệu vẫn idempotent. Client đã cố ý yêu cầu **create-only**, nên phản hồi lần lặp khác và không ghi đè.

### 9.3. Tránh kiểm tra rồi ghi trong hai bước không nguyên tử

Không đủ nếu code thực hiện “GET version, nếu khớp thì UPDATE” mà hai thao tác không có bảo vệ đồng thời. Hai request có thể cùng đọc version 7, sau đó cả hai cùng ghi.

Cần dùng **conditional UPDATE**, optimistic locking với cột version, transaction hoặc cơ chế tương đương; điều kiện phải được kiểm tra tại điểm ghi có thẩm quyền. Dùng ETag mạnh khi cần so khớp chính xác representation; cách tính ETag và cách ánh xạ sang version database phải thống nhất.

## 10. PATCH: thao tác cập nhật một phần có thể idempotent hoặc không

PATCH gửi một tập thay đổi thay vì thay thế toàn bộ tài nguyên. Tính idempotent phụ thuộc **ngữ nghĩa payload**:

| Loại PATCH | Ví dụ | Gửi hai lần sẽ thế nào? |
| --- | --- | --- |
| Đặt giá trị cụ thể | JSON Merge Patch **{"status":"DONE"}** | Thường cùng trạng thái cuối, nếu không có điều kiện khác |
| Thay thế tại một đường dẫn cụ thể | JSON Patch **replace** giá trị | Có thể idempotent nếu được áp dụng trên trạng thái phù hợp |
| Tăng số đếm | Lệnh nghiệp vụ “increment counter by 1” | Tăng hai lần nếu không có khóa chống trùng |
| Thêm phần tử vào danh sách | JSON Patch **add** vào vị trí mảng | Có thể chèn hai lần hoặc thay đổi thứ tự/kết quả |
| Cập nhật có If-Match | PATCH cùng ETag cũ | Lần đầu có thể thành công, lần sau có thể nhận 412 khi version đã đổi |

Ngay cả một phép “set status=DONE” cũng cần cân nhắc tác dụng phụ. Nếu mỗi lần gọi phát **OrderCompleted** và gửi thông báo một lần, triển khai chưa bảo đảm hiệu ứng nghiệp vụ idempotent. Nên chỉ phát event khi thực sự chuyển trạng thái và dùng idempotency/deduplication ở consumer.

Vì PATCH không được HTTP bảo đảm idempotent mặc định, client **không nên tự động retry mù quáng** mọi PATCH sau timeout. Hợp đồng phải ghi rõ phép cập nhật nào an toàn khi lặp lại, hoặc yêu cầu precondition/idempotency key.

## 11. Mã trạng thái và hướng xử lý sau lần gọi lại

| Mã | Ý nghĩa trong tình huống gọi lặp | Client nên làm gì? |
| --- | --- | --- |
| **200 OK** | Thao tác hoàn tất và trả representation/kết quả; có thể là lần cập nhật/replay | Dùng dữ liệu theo schema; không mặc định có tài nguyên mới |
| **201 Created** | Tạo tài nguyên theo hợp đồng đã hoàn tất; với replay idempotent có thể dùng lại response ban đầu | Lấy URI tài nguyên từ Location và body được công bố |
| **202 Accepted** | Request được nhận nhưng xử lý chưa hoàn tất | Theo dõi operation/status endpoint; không mặc định tài nguyên cuối đã sẵn sàng |
| **204 No Content** | Thao tác thành công, không trả message body | Không parse JSON body; dùng URI và contract đã biết |
| **304 Not Modified** | GET/HEAD có điều kiện không cần truyền representation mới | Dùng bản lưu hợp lệ theo quy tắc cache |
| **400 Bad Request** | Request sai hợp đồng hoặc thiếu idempotency key bắt buộc | Sửa request, không retry giống hệt |
| **404 Not Found** | URI không có tài nguyên hiển thị cho caller; có thể là DELETE lần sau | Áp dụng chính sách client: kết thúc xóa hoặc xử lý lỗi tùy endpoint |
| **409 Conflict** | Xung đột phiên bản/trạng thái/khóa nghiệp vụ hoặc duplicate key khác nội dung | Phân loại nguyên nhân; chỉ retry khi contract cho phép |
| **410 Gone** | Tài nguyên được biết là đã không còn và tình trạng được công bố | Không tự động gửi lại cùng request để “khôi phục” |
| **412 Precondition Failed** | If-Match/If-None-Match không thỏa | GET lại và ra quyết định; không retry mù với điều kiện cũ |
| **428 Precondition Required** | Thiếu điều kiện mà server bắt buộc với request đó | Bổ sung If-Match/điều kiện phù hợp rồi gửi lại |
| **429 Too Many Requests** | Bị giới hạn tốc độ | Tôn trọng Retry-After nếu có, backoff và hạn chế số lần retry |
| **503 Service Unavailable** | Dịch vụ tạm thời không phục vụ | Retry có kiểm soát nếu thao tác an toàn/idempotent hoặc đã có khóa chống trùng |

Mã lỗi **5xx** sau POST **không chứng minh giao dịch chưa được ghi**. Có thể database đã commit nhưng lỗi xảy ra khi serialize response hoặc gateway mất kết nối. Đây là lý do cần idempotency key và/hoặc API truy vấn trạng thái theo business ID khi retry.

### Retry-After có phải bảo đảm thành công?

Không. **Retry-After** là gợi ý thời điểm nên thử lại trong ngữ cảnh tương ứng; client vẫn cần thời hạn tổng, backoff, jitter và giới hạn số lần. Với POST có tác dụng phụ, Retry-After cũng không thay thế idempotency key.

## 12. Thiết kế cơ chế chống trùng vững khi nhiều instance chạy song song

Một cache cục bộ theo instance không đủ: request đầu đến instance A, retry đến instance B, hai instance có thể cùng tạo tài nguyên. Cơ chế chống trùng cần được lưu và kiểm tra tại một **điểm có thẩm quyền**, thường bằng unique constraint và transaction trên database hoặc cơ chế atomic tương đương.

### 12.1. Lược đồ lưu idempotency minh họa

~~~sql
CREATE TABLE idempotency_records (
    tenant_id        VARCHAR(64)  NOT NULL,
    operation_name   VARCHAR(100) NOT NULL,
    idempotency_key  VARCHAR(200) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    state            VARCHAR(20)  NOT NULL,
    response_status  INTEGER,
    response_location TEXT,
    response_body    TEXT,
    created_at       TIMESTAMP NOT NULL,
    expires_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_name, idempotency_key)
);
~~~

Đây là mô hình **minh họa**, không phải SQL áp dụng nguyên xi cho mọi engine. Thực tế cần điều chỉnh kiểu dữ liệu, phân vùng tenant, bảo vệ PII trong response lưu lại, quy tắc xóa hạn và tối ưu index.

### 12.2. Luồng xử lý với database transaction

~~~mermaid
flowchart TD
  R[POST + Idempotency-Key] --> V{Key và request hợp lệ?}
  V -->|Không| E[400 / lỗi validation]
  V -->|Có| C[Tra/claim key atomically]
  C --> D{Key đã tồn tại?}
  D -->|Có, hash khác| X[409 Conflict]
  D -->|Có, đã hoàn tất| P[Replay response đã lưu]
  D -->|Có, đang xử lý| I[Chờ / 409 / 202 theo hợp đồng]
  D -->|Chưa| T[Transaction: tạo resource + lưu kết quả]
  T --> S{Commit thành công?}
  S -->|Có| O[201 + Location + body]
  S -->|Không| F[Rollback / lỗi phù hợp; cho phép xử lý lại an toàn]
~~~

Với tạo resource và lưu idempotency trong **cùng một cơ sở dữ liệu**, có thể thiết kế transaction sao cho **cả resource và kết quả idempotency cùng commit hoặc cùng rollback**. Nếu hai request tranh key, unique constraint/row lock quyết định một bên thực hiện, bên còn lại chờ hoặc đọc kết quả. Đừng dùng đoạn **if key absent rồi insert** không khóa, vì cả hai request có thể vượt qua kiểm tra.

Nếu nghiệp vụ còn gọi **cổng thanh toán hoặc gửi webhook ngoài transaction DB**, một transaction DB không thể hoàn tác tác dụng phụ ở bên ngoài. Cần cơ chế idempotency với đối tác, **outbox**, workflow/saga, trạng thái trung gian và đối soát để bảo đảm toàn bộ luồng nghiệp vụ.

### 12.3. Xử lý lỗi giữa commit và response

Kịch bản khó:

1. Server tạo đơn **ord-1001** và commit.
2. Kết nối HTTP bị ngắt trước khi client nhận 201.
3. Client không biết request đầu đã thành công.
4. Client gửi lại với cùng idempotency key.
5. Server đọc kết quả bền vững và trả lại **Location /orders/ord-1001**, không tạo thêm đơn.

Nếu response được lưu trong key store **không nguyên tử** với tạo đơn, bước 1 thành công nhưng bước lưu response có thể thất bại, gây trạng thái không xác định khi retry. Hãy thiết kế điểm commit rõ ràng, giữ mapping đến resource và có quy trình reconcile các trạng thái lỗi.

## 13. Tạo và cập nhật có điều kiện trong Spring MVC

Ví dụ sử dụng Spring MVC và Java 17+ để mô tả **ngữ nghĩa HTTP**. Business service và persistence cần triển khai giao dịch, khóa/optimistic locking, kiểm tra quyền và xử lý lỗi thực tế.

### 13.1. DELETE nhất quán theo chính sách “đảm bảo không còn”

~~~java
@RestController
@RequestMapping("/api/v1/drafts")
public class DraftController {

    private final DraftService drafts;

    public DraftController(DraftService drafts) {
        this.drafts = drafts;
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(
            @PathVariable UUID id,
            Authentication authentication) {

        // Service kiểm tra quyền và chỉ phát event
        // khi bản nháp thực sự chuyển trạng thái sang đã xóa.
        drafts.deleteIfExistsAuthorized(id, authentication);

        return ResponseEntity.noContent().build();
    }
}
~~~

Theo contract này, **204** được trả khi thao tác “đảm bảo không còn bản nháp mà caller được phép xóa” hoàn thành. Service phải xử lý **403/404 hoặc chính sách che giấu sự tồn tại** đúng trước khi controller trả 204; không dùng 204 để che mọi lỗi database hoặc quyền.

### 13.2. PUT tạo mới và thay thế

~~~java
@RestController
@RequestMapping("/api/v1/preferences")
public class PreferenceController {

    private final PreferenceService preferences;

    public PreferenceController(PreferenceService preferences) {
        this.preferences = preferences;
    }

    @PutMapping("/{userId}")
    public ResponseEntity<PreferenceResponse> put(
            @PathVariable String userId,
            @Valid @RequestBody PreferenceRequest body,
            Authentication authentication) {

        // upsert phải thực hiện atomically và kiểm tra
        // caller có quyền thao tác trên userId.
        PreferenceWriteResult result =
                preferences.upsertAuthorized(userId, body, authentication);

        if (result.created()) {
            URI location = URI.create("/api/v1/preferences/" + userId);
            return ResponseEntity.created(location).body(result.value());
        }

        return ResponseEntity.ok(result.value());
    }
}
~~~

Trong ví dụ, **PreferenceRequest**, **PreferenceResponse**, **PreferenceWriteResult** và service là những kiểu nghiệp vụ người học cần tự định nghĩa. Code chỉ tập trung vào HTTP contract; đường dẫn chứa userId phải được mã hóa/kiểm soát theo chính sách URI và quyền.

**Lần PUT đầu tạo mới trả 201; lần sau thay thế trả 200.** Dù status khác, nếu cùng body và không có tác dụng phụ khác, trạng thái đích vẫn giống nhau. Không tự xác định created bằng một phép kiểm tra tồn tại tách biệt rồi insert không khóa; phải xử lý race condition trong persistence.

### 13.3. Xử lý precondition đúng chỗ

Controller có thể nhận **If-Match** và đưa đến service. Nhưng phép so sánh version cần thực hiện **tại điểm ghi có thẩm quyền**, không chỉ so ETag rồi mới gửi một UPDATE không ràng buộc.

Pseudocode:

~~~text
PATCH /tasks/42 with If-Match "v7"
   -> authorize caller
   -> conditional UPDATE tasks
        SET title = ..., version = 8
        WHERE id = 42 AND version = 7
   -> affected rows = 1: 200/204, ETag mới nếu có
   -> affected rows = 0:
        phân biệt không tồn tại, không có quyền hoặc
        version đã đổi theo chính sách API
        -> 404/403 hoặc 412 phù hợp
~~~

Với ETag do server cấp, cần bảo đảm phiên bản và representation liên kết chính xác. Khi có thay đổi mà không phản ánh trong version, validator có thể đánh giá sai.

## 14. OpenAPI: tài liệu hóa response cho từng lần gọi

OpenAPI nên mô tả **ngữ nghĩa lặp lại và xung đột** ngay trong description, không chỉ liệt kê mã status. Ví dụ rút gọn cho DELETE và PUT:

~~~yaml
openapi: 3.1.0
info:
  title: Preferences and Drafts API
  version: 1.0.0
paths:
  /api/v1/preferences/{userId}:
    put:
      summary: Tạo hoặc thay thế cấu hình người dùng
      description: >
        PUT có hiệu ứng idempotent. Nếu URI chưa có cấu hình thì tạo
        và trả 201; nếu đã có thì thay thế và trả 200.
        Việc cập nhật đồng thời cần tuân thủ chính sách version của API.
      parameters:
        - in: path
          name: userId
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [theme, language]
              properties:
                theme: { type: string }
                language: { type: string }
      responses:
        '201':
          description: Cấu hình mới được tạo
          headers:
            Location:
              description: URI của resource mới
              schema: { type: string, format: uri-reference }
        '200':
          description: Cấu hình đã tồn tại được thay thế
        '412':
          description: Precondition không thỏa nếu API hỗ trợ yêu cầu có điều kiện
  /api/v1/drafts/{id}:
    delete:
      summary: Đảm bảo bản nháp không còn
      description: >
        Sau khi kiểm tra quyền và điều kiện nghiệp vụ, API trả 204
        cả khi resource vừa bị xóa lẫn khi trước đó đã không còn.
      parameters:
        - in: path
          name: id
          required: true
          schema: { type: string, format: uuid }
      responses:
        '204':
          description: Không còn bản nháp được phép xóa
        '403':
          description: Không có quyền
        '409':
          description: Không thể xóa do trạng thái nghiệp vụ
~~~

Đối với POST, nên thêm mô tả của **Idempotency-Key**: yêu cầu key hay không, phạm vi, TTL, tình huống replay, key khác payload, request in-progress và khả năng trả 201/200/202/409 theo hợp đồng. Nếu một response có body JSON, OpenAPI cần khai báo schema, còn **204** tuyệt đối không kèm body.

### Ví dụ mô tả header cho POST tạo đơn

~~~yaml
parameters:
  - in: header
    name: Idempotency-Key
    required: true
    description: >
      Key duy nhất cho một ý định tạo đơn; giữ nguyên khi retry.
      Cùng key nhưng payload khác bị từ chối.
    schema:
      type: string
      minLength: 1
      maxLength: 200
~~~

Đoạn trên là một phần của **operation object**, cần đặt đúng dưới POST trong OpenAPI hoàn chỉnh. Không nhầm đây là quy tắc idempotency mặc định được HTTP thực thi.

## 15. Retry tại client: khi nào an toàn?

Không xây một middleware **retry mọi request lỗi**. Cần dựa vào phương thức, hợp đồng idempotency, loại lỗi và tổng thời gian.

| Tình huống | Hành vi client gợi ý |
| --- | --- |
| GET timeout/lỗi mạng tạm thời | Có thể retry có giới hạn, backoff và jitter; lưu ý cache/ETag |
| HEAD timeout | Có thể retry có giới hạn |
| PUT cùng URI/body, không có side effect nguy hiểm | Có thể retry vì hiệu ứng mong muốn idempotent; xem lại precondition |
| DELETE timeout | Có thể retry; hiểu chính sách 204/404/410 và quyền |
| POST tạo đơn không có idempotency key | Không tự động retry mù; kiểm tra trạng thái theo business identifier hoặc dùng cơ chế chống trùng |
| POST với idempotency key bền vững | Retry **cùng key và payload** trong thời hạn hợp đồng; kiểm tra response replay |
| PATCH tăng counter hoặc thêm phần tử | Không retry mù; cần key hoặc thiết kế phép ghi có điều kiện |
| 401/403 | Sửa xác thực/quyền theo quy trình, không retry vô hạn |
| 409 do payload khác key | Dừng và sửa request hoặc dùng key mới cho ý định mới |
| 412/428 | GET lại/reconcile hoặc bổ sung precondition trước khi gửi lại |
| 429/503 có Retry-After | Tôn trọng thời điểm, giới hạn số lần, tránh tạo retry storm |

### Backoff và giới hạn tổng

Ví dụ thuật toán ở mức ý tưởng:

~~~text
attempt = 0
while attempt < maxAttempts and totalDeadlineNotExceeded:
    send request with SAME idempotency key if this is a retry
    if successful: return result

    if permanent client error: stop
    if 409/412: apply conflict policy, do not blind retry
    if transient and operation is retry-safe:
        wait respecting Retry-After if present
        otherwise exponential backoff with jitter
        attempt += 1
        continue
    stop

return final error/unknown-outcome status
~~~

Nếu client timeout sau khi request có thể đã commit, trạng thái kết quả là **unknown**, không phải “chắc chắn thất bại”. UI cần diễn đạt phù hợp và hỗ trợ truy vấn theo operation ID/business ID/idempotency key nếu API cung cấp.

## 16. Kiểm thử lặp lại với Java/Spring và trường hợp cạnh tranh

### 16.1. Test HTTP PUT tạo rồi thay thế

Một test MockMvc có thể kiểm tra **status khác nhau nhưng representation cuối thống nhất**:

~~~java
@Test
void repeatedPutDoesNotCreateAnotherPreference() throws Exception {
    String payload = """
        {"theme":"dark","language":"vi"}
        """;

    mockMvc.perform(put("/api/v1/preferences/u-42")
            .contentType(MediaType.APPLICATION_JSON)
            .content(payload))
        .andExpect(status().isCreated());

    mockMvc.perform(put("/api/v1/preferences/u-42")
            .contentType(MediaType.APPLICATION_JSON)
            .content(payload))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.theme").value("dark"));

    mockMvc.perform(get("/api/v1/preferences/u-42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.language").value("vi"));
}
~~~

Test cần môi trường dữ liệu sạch, principal hợp lệ và triển khai PreferenceService thực sự; không được tắt kiểm tra quyền để hợp thức hóa contract. Cần kiểm tra thêm số bản ghi và business event nếu ứng dụng có side effect.

### 16.2. Test DELETE nhiều lần

~~~java
@Test
void deleteIsRetrySafe() throws Exception {
    mockMvc.perform(delete("/api/v1/drafts/42"))
        .andExpect(status().isNoContent());

    mockMvc.perform(delete("/api/v1/drafts/42"))
        .andExpect(status().isNoContent());

    mockMvc.perform(get("/api/v1/drafts/42"))
        .andExpect(status().isNotFound());
}
~~~

Test trên giả định contract chọn **204 cho cả hai lần**. Nếu API chọn 404 ở lần hai, thay kỳ vọng theo hợp đồng nhưng vẫn kiểm tra trạng thái cuối là không còn.

### 16.3. Ma trận test bắt buộc cho POST có idempotency key

| Test | Bằng chứng đạt |
| --- | --- |
| Request lần đầu với key mới | 201, Location, tài nguyên thực sự tồn tại |
| Retry cùng key, cùng payload | Cùng resource ID, không thêm row, phản hồi theo contract |
| Cùng key nhưng payload khác | 409, không có side effect mới |
| Hai request đồng thời cùng key tới hai instance | Chỉ một resource/transaction được commit |
| Timeout sau DB commit trước response | Retry vẫn tìm được kết quả đã commit |
| Request mới với key mới nhưng payload giống | Tạo resource mới nếu nghiệp vụ cho phép |
| Key thuộc tenant khác | Không được đọc/replay response của tenant trước |
| Key quá hạn | Theo đúng TTL/reconciliation/unique business rule đã công bố |
| Lỗi trước commit | Rollback đúng và cho phép retry an toàn |
| Side effect ngoài DB/queue | Outbox/consumer chống lặp khi replay |

Để test concurrency thực sự, dùng integration test với database có unique constraint, chạy hai client/thread độc lập đồng bộ thời điểm bắt đầu, rồi xác minh số bản ghi sau commit. Test mock chỉ đếm method invocation trong một instance **không chứng minh** khả năng chống race ở nhiều instance.

### 16.4. Test optimistic locking

- GET phiên bản **v4**, client A cập nhật với **If-Match: v4** → thành công và sinh version mới.
- Client B tiếp tục gửi lại với **If-Match: v4** → **412** theo chính sách, không ghi đè dữ liệu mới.
- Client thiếu **If-Match** nếu endpoint bắt buộc → **428**.
- Test phân quyền phải bảo đảm một client không xem được ETag hoặc nội dung của tài nguyên tenant khác chỉ vì đoán trúng URI.

## 17. Những sai lầm thiết kế thường gặp

### Sai lầm 1: Đồng nhất idempotency với việc mọi lần đều trả 200

PUT tạo mới lần đầu cần **201**, những lần thay thế sau dùng **200/204**. DELETE có thể trả 204 rồi 404. Tính idempotent nằm ở **hiệu ứng**, không nằm ở việc cố định status code.

### Sai lầm 2: Dùng GET cho thao tác thay đổi trạng thái

Ví dụ **GET /orders/123/confirm** làm thay đổi trạng thái đơn. Các hệ thống cache, crawler, trình duyệt có thể gọi GET lại. Hãy mô hình hóa thao tác ghi bằng method và resource thích hợp, xác định idempotency rõ.

### Sai lầm 3: Chỉ dùng kiểm tra tồn tại trước khi insert

~~~text
if not exists(order for key):
    insert(order)
~~~

Hai request đồng thời có thể cùng nhìn thấy “chưa có” rồi cùng insert. Cần **unique constraint + transaction/atomic claim**, không chỉ dùng synchronized trên một process.

### Sai lầm 4: Mỗi retry có key mới

Client gửi lại POST với key ngẫu nhiên mới sau timeout thì server coi là **ý định mới**. Cần giữ cùng key trong vòng đời thao tác, kể cả sau khi ứng dụng khởi động lại nếu chính sách yêu cầu.

### Sai lầm 5: Chỉ chống trùng trong database

Tạo đơn không trùng nhưng mỗi retry lại gửi hai email hoặc gọi cổng thanh toán hai lần vẫn là lỗi nghiệp vụ. Kết hợp **transactional outbox, event ID, consumer deduplication** và idempotency với đối tác.

### Sai lầm 6: Trả 204 để che mọi lỗi DELETE

Nếu hệ thống không truy cập database được, trả 204 khiến client tin rằng xóa đã hoàn tất. Phải phân biệt lỗi vận hành, lỗi quyền, lỗi ràng buộc nghiệp vụ và trường hợp đã không còn resource.

### Sai lầm 7: Coi If-Match là khóa chỉ cần kiểm tra trong controller

Check version rồi update không nguyên tử vẫn có race condition. Thực hiện conditional write hoặc optimistic locking tại database.

### Sai lầm 8: Trộn lẫn “đã tiếp nhận” và “đã hoàn tất”

Một job bất đồng bộ đang chạy không tương đương resource đã tạo. **202** cần operation resource/trạng thái rõ ràng; **201** dùng khi việc tạo theo hợp đồng đã hoàn tất.

## 18. Bài thực hành: API xác nhận phiếu đăng ký

Một hệ thống quản lý sự kiện có các resource:

- **POST /api/v1/registrations**: tạo đăng ký, server sinh ID.
- **GET /api/v1/registrations/{id}**: đọc đăng ký.
- **PUT /api/v1/registrations/{id}/preferences**: đặt lại tùy chọn.
- **PATCH /api/v1/registrations/{id}**: sửa trạng thái có version.
- **DELETE /api/v1/registrations/{id}**: hủy một bản đăng ký chưa được xác nhận; hệ thống cho phép gọi lại khi đã hủy.

Yêu cầu nghiệp vụ: người dùng có thể gửi lại request khi mạng yếu; mỗi lần đăng ký mới có thể có payload giống nhau nhưng là một ý định mới; không tạo hai đăng ký chỉ vì timeout; email xác nhận chỉ gửi một lần cho cùng registration.

### Nhiệm vụ

1. Thiết kế bảng **method, URI, kết quả lần đầu, kết quả gọi lại, trạng thái resource cuối** cho năm endpoint.
2. Đề xuất chính sách **Idempotency-Key** cho POST: phạm vi key theo user/tenant, fingerprint, TTL, replay, concurrent duplicate, xử lý key khác payload.
3. Vẽ flow từ POST đầu tiên → database commit → mất HTTP response → client retry → trả cùng registration ID.
4. Viết OpenAPI mô tả **201 Created**, Location, các tình huống 409/412/428, status và body thích hợp.
5. Cài đặt PUT preferences sao cho gửi cùng body nhiều lần không phát thêm event nghiệp vụ không cần thiết.
6. Với PATCH, chọn cơ chế **If-Match** để chặn lost update và mô tả phản hồi 412.
7. Chọn một trong hai chính sách DELETE **204→204** hoặc **204→404**, giải thích tại sao vẫn idempotent.
8. Viết integration test cho hai request POST đồng thời cùng key, hai key khác nhau cùng payload và retry sau mất response.
9. Thiết kế outbox/email worker idempotent để không gửi email hai lần khi event được replay.
10. Mô tả backoff, Retry-After, hành vi khi response không rõ và cách UI tra cứu trạng thái.

### Bộ tình huống tự kiểm tra

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Gửi POST hai lần cùng key, cùng payload | Một registration; response lặp lại theo hợp đồng |
| Gửi POST hai lần khác key nhưng payload giống | Có thể tạo hai registration nếu nghiệp vụ cho phép |
| Retry POST cùng key nhưng đổi email liên hệ | 409 hoặc lỗi xung đột key được công bố |
| PUT preferences tạo rồi đặt lại y hệt | 201 rồi 200/204, trạng thái cuối không đổi |
| DELETE một resource rồi DELETE lại | 204 rồi 204/404 theo contract, không phát tác dụng phụ xóa lần hai |
| PATCH status từ v3 trong khi đã lên v4 | 412, không ghi đè v4 |
| Mất database trong lúc xử lý | Không báo thành công giả; retry an toàn theo transaction |
| Queue gửi lại event email | Một tác dụng nghiệp vụ, dù nhiều lần delivery |

## 19. Checklist trước khi công bố quy tắc gọi lặp

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Method có phù hợp với tác động thực tế? | GET/HEAD không làm thay đổi trạng thái nghiệp vụ; PUT/DELETE giữ idempotency |
| Client biết ý nghĩa khi cùng request lặp lại? | Tài liệu mô tả mã lần đầu và lần sau |
| POST nguy cơ tạo trùng đã được xử lý? | Có idempotency contract và unique atomic enforcement |
| Có phân biệt cùng key/cùng payload với cùng key/khác payload? | Lỗi xung đột và fingerprint rõ |
| Có xử lý concurrency giữa nhiều instance? | Integration test kiểm chứng chỉ một commit |
| Có cơ chế lost update? | If-Match/ETag và atomic conditional write khi cần |
| Có bảo đảm side effect idempotent? | Outbox, event ID, consumer deduplication và quy tắc retry |
| Lỗi 4xx/5xx/429/503 được xử lý đúng? | Client retry có giới hạn, phân loại unknown outcome |
| 202/201/204 được dùng đúng? | Không đánh đồng chấp nhận xử lý và hoàn thành |
| OpenAPI và test có phản ánh hợp đồng? | Status, headers, body, concurrency, quyền và retry được kiểm chứng |

## 20. Ghi nhớ

**Quy tắc phản hồi khi cùng thao tác được gọi lại** bắt đầu từ câu hỏi về **hiệu ứng đối với tài nguyên**: sau hai request giống nhau, trạng thái có bị thay đổi thêm lần nữa hay không? Tiếp theo mới quyết định mỗi lần HTTP response nên trả mã gì để mô tả **kết quả hiện tại** và **ngữ nghĩa của hợp đồng**.

GET/HEAD là safe; PUT và DELETE idempotent theo ngữ nghĩa HTTP; POST và PATCH cần đánh giá từng thao tác. **201 rồi 200**, hoặc **204 rồi 404**, vẫn có thể là một API idempotent; **201 rồi 201 với hai URI khác nhau** có thể là dấu hiệu POST bị nhân đôi vì retry.

Trong hệ thống thực, việc trả đúng mã chỉ là một phần. Muốn retry an toàn phải có **điểm ghi nguyên tử, khóa chống trùng, kiểm soát phiên bản, bảo vệ tác dụng phụ và kiểm thử trường hợp response bị thất lạc**.
