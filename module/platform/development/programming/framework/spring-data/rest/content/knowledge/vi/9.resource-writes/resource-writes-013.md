# Tính lũy đẳng của HTTP method và rủi ro gửi lại yêu cầu ghi

Trong Spring Data REST, các repository thường được công khai thành những resource HTTP. Client có thể đọc collection, tạo entity mới, cập nhật một entity hoặc xóa resource thông qua các method như GET, POST, PUT, PATCH và DELETE. Khi mạng chập chờn, client có thể gửi lại một request sau timeout. Nếu không hiểu tính lũy đẳng của method và hợp đồng của endpoint, thao tác gửi lại có thể tạo dữ liệu trùng, phát sinh thanh toán hoặc gửi thông báo nhiều lần.

Tính lũy đẳng giúp xác định request nào có thể được gửi lại an toàn ở cấp độ hiệu ứng được yêu cầu. Nó không tự bảo đảm mọi side effect trong ứng dụng chỉ xảy ra một lần.

## 1. Tính lũy đẳng là gì?

Một thao tác là **lũy đẳng (idempotent)** khi thực hiện một lần hoặc lặp lại nhiều lần cùng một request thì hiệu ứng dự kiến lên trạng thái của server vẫn như nhau.

Ví dụ, đặt trạng thái đơn hàng thành PAID là thao tác có thể được thiết kế lũy đẳng:

- Request đầu tiên đổi trạng thái từ PENDING sang PAID.
- Request thứ hai tiếp tục yêu cầu trạng thái PAID.
- Sau cả hai request, trạng thái đơn hàng vẫn là PAID.

Ngược lại, thao tác cộng thêm 100 điểm vào tài khoản không lũy đẳng:

- Lần đầu số điểm tăng 100.
- Lần thứ hai số điểm tăng thêm 100.
- Gửi lại request làm thay đổi kết quả nghiệp vụ.

Cần phân biệt ba khía cạnh:

1. **Trạng thái tài nguyên:** dữ liệu nghiệp vụ cuối cùng mà request muốn thiết lập.
2. **Response HTTP:** status code, header và body server trả về cho từng lần gọi.
3. **Side effect phụ:** ghi log, phát event, gửi email, gọi dịch vụ thanh toán hoặc cập nhật hệ thống khác.

Hai lần gọi một method lũy đẳng không bắt buộc trả về response giống hệt nhau. Chẳng hạn, DELETE lần đầu có thể trả về 204, lần sau có thể trả về 404 vì resource đã không còn. Điều quan trọng là hiệu ứng dự kiến lên trạng thái tài nguyên vẫn tương đương: resource tiếp tục ở trạng thái không tồn tại.

Đặc tính lũy đẳng của HTTP cũng không có nghĩa mọi side effect phụ tự động được khử trùng lặp. Nếu mỗi lần PUT đều kích hoạt một email hoặc một lần thu tiền, ứng dụng vẫn có thể gửi email hoặc thu tiền nhiều lần dù trạng thái resource sau các request không đổi.

## 2. Phân biệt safe method và idempotent method

Hai khái niệm này có liên quan nhưng không đồng nghĩa.

- **Safe method:** method được định nghĩa để client yêu cầu đọc hoặc quan sát dữ liệu; client không yêu cầu server thay đổi trạng thái nghiệp vụ.
- **Idempotent method:** method có hiệu ứng dự kiến giống nhau khi request được thực hiện một lần hoặc nhiều lần.

| HTTP method | Safe | Idempotent | Ý nghĩa chính |
|---|---|---|---|
| GET | Có | Có | Lấy representation của resource |
| HEAD | Có | Có | Lấy metadata/header tương tự GET, không trả body |
| OPTIONS | Có | Có | Hỏi các tùy chọn hoặc khả năng giao tiếp |
| TRACE | Có | Có | Phản hồi thông tin request theo semantics của TRACE; thường bị tắt vì lý do bảo mật |
| PUT | Không | Có | Tạo hoặc thay thế trạng thái resource tại URI đích |
| DELETE | Không | Có | Yêu cầu resource đích không còn tồn tại |
| POST | Không | Không mặc định | Gửi dữ liệu để resource xử lý, thường dùng để tạo resource hoặc thực hiện hành động |
| PATCH | Không | Không được bảo đảm | Áp dụng một phần thay đổi lên resource |
| CONNECT | Không | Không | Thiết lập tunnel tới đích |

Các method safe cũng là idempotent. PUT và DELETE là idempotent nhưng không safe vì chúng có thể làm thay đổi trạng thái server. POST và PATCH cần xem xét hợp đồng cụ thể của endpoint.

Với custom HTTP method hoặc API có semantics riêng, cần đọc hợp đồng API thay vì suy luận chỉ từ tên method.

## 3. Ý nghĩa của từng method khi làm việc với Spring Data REST

Spring Data REST thường ánh xạ repository thành collection resource và item resource. Ví dụ, giả sử repository quản lý Order và API công khai:

- Collection: /orders
- Item: /orders/42

Tên đường dẫn thực tế phụ thuộc cấu hình repository, base path và resource mapping của ứng dụng.

### 3.1. POST: tạo mới và nguy cơ tạo bản ghi trùng

POST lên collection thường được dùng để tạo entity mới.

~~~http
POST /orders
Content-Type: application/json

{
  "customerId": 17,
  "total": 250000
}
~~~

Nếu server đã tạo Order nhưng response bị mất trên đường truyền, client chỉ nhìn thấy timeout. Khi client gửi lại POST, server có thể tạo thêm một Order khác. Hai request có cùng body vẫn có thể tạo hai resource vì mỗi lần POST có thể được hiểu là một yêu cầu tạo mới.

POST không lũy đẳng theo mặc định. Không nên tự động retry POST chỉ vì client không nhận được response.

Các biện pháp thường dùng để chống tạo trùng gồm:

- Idempotency key được server hỗ trợ.
- Mã yêu cầu nghiệp vụ duy nhất, có unique constraint ở database.
- Một operation resource có ID ổn định để client truy vấn kết quả.
- Cơ chế deduplication ở tầng nghiệp vụ.

### 3.2. PUT: đặt trạng thái resource tại URI xác định

PUT thường được dùng để tạo hoặc thay thế representation của resource tại URI đã biết.

~~~http
PUT /orders/42
Content-Type: application/json

{
  "customerId": 17,
  "total": 250000,
  "status": "PENDING"
}
~~~

Nếu hai request PUT giống nhau cùng nhắm tới /orders/42 và có cùng nội dung, trạng thái resource mà client yêu cầu thiết lập vẫn là cùng một trạng thái. Vì vậy PUT được định nghĩa là idempotent.

Response của hai lần gọi vẫn có thể khác nhau. Lần đầu có thể tạo resource và trả 201 Created; lần sau có thể cập nhật resource hiện có và trả 200 OK hoặc 204 No Content.

Không nên dùng PUT như một lệnh cộng dồn hoặc tạo side effect mới ở mỗi lần gọi. Nếu logic xử lý PUT gửi email, phát event không có khóa khử trùng lặp hoặc gọi dịch vụ thu tiền mỗi lần request được xử lý, các side effect đó vẫn có thể lặp lại.

### 3.3. PATCH: phụ thuộc vào nội dung bản vá

PATCH dùng để áp dụng một phần thay đổi lên resource. Bản thân PATCH không được bảo đảm là idempotent; tính chất này phụ thuộc nội dung patch và cách API xử lý.

Một patch đặt giá trị cụ thể có thể lũy đẳng:

~~~http
PATCH /orders/42
Content-Type: application/merge-patch+json

{
  "status": "PAID"
}
~~~

Lặp lại yêu cầu đặt status thành PAID vẫn hướng tới cùng trạng thái.

Một patch mang ý nghĩa cộng dồn lại không lũy đẳng:

~~~http
PATCH /accounts/17
Content-Type: application/json

{
  "balanceDelta": 100
}
~~~

Nếu API hiểu balanceDelta là cộng thêm 100, mỗi lần retry sẽ tiếp tục tăng số dư. Tên field và semantics thực tế do ứng dụng định nghĩa; ví dụ này minh họa một API patch tùy chỉnh.

Vì vậy, trước khi retry PATCH, cần biết patch document biểu diễn thao tác đặt giá trị hay thao tác biến đổi trạng thái.

### 3.4. DELETE: xóa resource

DELETE lên item resource yêu cầu resource đích không còn tồn tại.

~~~http
DELETE /orders/42
~~~

Lần đầu có thể trả về 204 No Content. Nếu gửi lại sau khi resource đã bị xóa, server có thể trả về 404 Not Found. Hai response khác nhau nhưng trạng thái đích vẫn là resource không tồn tại, nên DELETE có semantics idempotent.

Tính lũy đẳng của DELETE không đồng nghĩa mọi hành động liên quan đến xóa chỉ được chạy một lần. Ví dụ, listener hoặc event handler gửi email thông báo sau mỗi request xóa được chấp nhận vẫn cần cơ chế kiểm soát side effect.

## 4. Vì sao retry request ghi có thể gây lỗi?

Một timeout không cho biết chắc chắn server chưa thực hiện request. Có ít nhất ba tình huống:

1. Request chưa đến server hoặc bị từ chối trước khi xử lý. Thao tác nghiệp vụ chưa xảy ra.
2. Server đã xử lý và commit transaction, nhưng response bị mất trên đường truyền. Thao tác nghiệp vụ đã xảy ra.
3. Server vẫn đang xử lý khi client hết thời gian chờ. Client chưa biết kết quả cuối cùng.

Tình huống thứ hai đặc biệt nguy hiểm với POST hoặc thao tác không lũy đẳng.

Ví dụ một client tạo đơn hàng:

~~~text
Client                         Server
  |                              |
  | POST /orders                 |
  |----------------------------->|
  |                              | Tạo Order #101
  |                              | Commit transaction
  |         response 201         |
  |<--------- X -----------------| Response bị mất
  |                              |
  | Timeout                      |
  |                              |
  | POST /orders (retry)         |
  |----------------------------->|
  |                              | Tạo Order #102
  |<-----------------------------|
  |         response 201         |
~~~

Client chỉ định tạo một đơn hàng nhưng database có thể chứa hai đơn hàng. Nếu cùng quy trình còn phát sinh thanh toán hoặc gửi thông báo, hậu quả có thể nghiêm trọng hơn dữ liệu trùng.

Không thể kết luận request thất bại chỉ vì client không nhận được response. Client cần một cách xác định kết quả đã commit hay chưa trước khi quyết định gửi lại.

## 5. Quy tắc retry theo method

| Method | Hướng xử lý khi timeout |
|---|---|
| GET, HEAD, OPTIONS | Thường có thể retry vì semantics safe và idempotent; vẫn cần giới hạn retry và xử lý lỗi hạ tầng |
| PUT | Có thể retry cùng URI, cùng nội dung và cùng điều kiện ghi nếu endpoint giữ đúng semantics idempotent |
| DELETE | Có thể retry khi mục tiêu vẫn là resource không tồn tại; xử lý response 404 theo hợp đồng API |
| PATCH | Chỉ retry khi patch operation được thiết kế lũy đẳng hoặc có cơ chế deduplication |
| POST | Không retry mù; cần idempotency key, mã nghiệp vụ duy nhất hoặc truy vấn trạng thái operation |

Một số nguyên tắc áp dụng cho mọi method:

- Retry phải giữ nguyên định danh của một thao tác nghiệp vụ. Không tạo idempotency key mới cho mỗi lần thử.
- Giữ nguyên method, URI, payload và precondition của lần gửi ban đầu khi semantics yêu cầu như vậy.
- Chỉ retry lỗi có khả năng tạm thời, ví dụ timeout kết nối, 408, 429, 502, 503 hoặc 504; tuân thủ Retry-After khi server gửi header này.
- Không retry liên tục lỗi xác thực, phân quyền, validation hoặc lỗi nghiệp vụ mà không thay đổi nguyên nhân.
- Dùng số lần retry hữu hạn, exponential backoff và jitter để tránh nhiều client đồng loạt gửi lại.
- Với kết quả không rõ ràng, ưu tiên truy vấn trạng thái resource hoặc operation trước khi phát sinh một thao tác ghi mới.

Đặc tính idempotent của method chỉ giúp bảo vệ hiệu ứng được định nghĩa ở cấp HTTP. Nó không thay thế việc kiểm tra side effect và invariant nghiệp vụ của endpoint.

## 6. Idempotency key cho POST và thao tác ghi không lũy đẳng

Khi một API cần cho phép client retry POST, có thể bổ sung cơ chế idempotency key ở tầng ứng dụng. Đây là quy ước hợp đồng giữa client và server; HTTP hoặc Spring Data REST không tự động bảo đảm xử lý header này nếu ứng dụng chưa triển khai.

Ví dụ request:

~~~http
POST /orders
Content-Type: application/json
Idempotency-Key: 9f3c2b7e-8c1d-4f10-a8a1-7d2e8b9c0012

{
  "customerId": 17,
  "total": 250000
}
~~~

Client tạo key một lần cho một hành động nghiệp vụ. Nếu timeout, client gửi lại cùng key và cùng payload.

Server có thể triển khai luồng xử lý như sau:

1. Nhận key cùng thông tin định danh người dùng/tenant, method, URI và payload.
2. Tạo fingerprint của request để xác định nội dung request có giống lần đầu hay không.
3. Ghi nhận key với ràng buộc unique để hai request đồng thời không cùng thực hiện side effect.
4. Thực hiện thay đổi nghiệp vụ và lưu kết quả xử lý trong cùng transaction hoặc một cơ chế có bảo đảm nhất quán tương đương.
5. Khi nhận lại key với cùng fingerprint, trả lại kết quả đã lưu hoặc trạng thái operation đang xử lý.
6. Khi cùng key nhưng payload khác, từ chối request theo hợp đồng API, thường bằng lỗi conflict.
7. Quy định thời hạn lưu key, phạm vi key và cách xử lý khi operation chưa hoàn tất.

Bảng lưu idempotency key thường cần có tối thiểu:

| Trường | Mục đích |
|---|---|
| key | Định danh duy nhất của thao tác |
| scope | Người dùng, tenant hoặc phạm vi nghiệp vụ |
| request fingerprint | Phát hiện việc tái sử dụng key với payload khác |
| status | IN_PROGRESS, SUCCEEDED hoặc FAILED theo mô hình xử lý |
| response/result reference | Kết quả có thể trả lại cho lần retry |
| created_at / expires_at | Quản lý vòng đời key |

Không nên chỉ lưu key trong cache rồi thực hiện ghi database ở một bước độc lập mà không xử lý lỗi giữa hai bước. Nếu key đã được đánh dấu hoàn tất nhưng transaction nghiệp vụ thất bại, hoặc transaction đã commit nhưng key chưa được lưu, hệ thống có thể trả kết quả sai hoặc tạo dữ liệu trùng.

Với side effect ngoài database như gửi email, gọi payment gateway hoặc publish message, cần thiết kế thêm outbox, idempotency key của nhà cung cấp hoặc deduplication ở consumer. Một transaction database đơn lẻ không thể tự bảo đảm side effect bên ngoài chỉ xảy ra một lần.

**Correlation ID không thay thế idempotency key.** Correlation ID dùng để liên kết log và trace của nhiều thành phần. Idempotency key dùng để nhận diện cùng một thao tác nghiệp vụ qua các lần retry.

## 7. Kết hợp conditional request và optimistic locking

Tính lũy đẳng giải quyết việc lặp lại cùng một thao tác. Nó không tự giải quyết xung đột khi nhiều client cùng sửa một resource.

Giả sử hai client cùng đọc Order #42 ở phiên bản có ETag "v7". Client A cập nhật thành công và resource chuyển sang phiên bản mới. Client B vẫn gửi dữ liệu dựa trên phiên bản cũ. Nếu API hỗ trợ conditional request, B có thể gửi:

~~~http
PUT /orders/42
If-Match: "v7"
Content-Type: application/json

{
  "status": "PAID"
}
~~~

Server chỉ chấp nhận cập nhật nếu ETag hiện tại vẫn khớp. Nếu resource đã thay đổi, server có thể trả 412 Precondition Failed để ngăn ghi đè dữ liệu mới hơn.

Conditional request và idempotency có mục đích khác nhau:

- **If-Match / ETag:** ngăn cập nhật dựa trên phiên bản đã lỗi thời.
- **Idempotency key:** nhận diện cùng một thao tác qua nhiều lần gửi và ngăn thực hiện side effect trùng.
- **Unique constraint:** bảo vệ một invariant dữ liệu ở database, ví dụ mã đơn hàng không được trùng.

Nếu lần PUT đầu tiên đã thành công nhưng response bị mất, retry với If-Match cũ có thể nhận 412 vì phiên bản đã đổi. Điều đó chưa chứng minh lần đầu thất bại. Client cần GET lại resource hoặc truy vấn operation để đối chiếu kết quả. Nếu endpoint cần trả lại đúng response của lần đầu, nên kết hợp cơ chế idempotency key phù hợp.

Spring Data REST có thể tham gia vào cơ chế optimistic locking khi resource và ứng dụng được cấu hình hỗ trợ version/ETag. Hãy kiểm tra hợp đồng thực tế của endpoint và cách client gửi precondition; không giả định mọi repository resource đều đã bật cơ chế này.

## 8. Những điểm cần kiểm soát trong ứng dụng Spring Data REST

Khi thiết kế endpoint ghi, hãy kiểm tra cả repository operation và logic chạy xung quanh nó.

- **Repository event handler:** các handler như HandleAfterCreate, HandleAfterSave hoặc HandleAfterDelete có thể phát sinh side effect. Đảm bảo handler không gửi thông báo hoặc tạo tác vụ trùng khi request được retry.
- **Entity listener và domain event:** một lần lưu entity có thể kích hoạt logic bổ sung. Xác định event đại diện cho thay đổi trạng thái hay đại diện cho mỗi lần request.
- **Ràng buộc database:** dùng unique constraint cho khóa nghiệp vụ cần duy nhất. Kiểm tra constraint ở database giúp bảo vệ dữ liệu kể cả khi nhiều request đến đồng thời.
- **Transaction boundary:** thao tác ghi resource và bản ghi idempotency cần có quan hệ transaction rõ ràng. Với message hoặc dịch vụ ngoài, cân nhắc transactional outbox và consumer deduplication.
- **Optimistic locking:** dùng version/ETag và precondition khi cần ngăn ghi đè cập nhật của client khác.
- **Hợp đồng response:** quy định rõ trường hợp retry trả lại response cũ, trả trạng thái hiện tại, hoặc trả lỗi conflict/precondition.
- **Quyền truy cập và phạm vi key:** không dùng chung key giữa các tenant hoặc người dùng nếu điều đó có thể làm lộ kết quả của thao tác khác.

Không nên dựa vào việc frontend vô tình không gửi hai lần để bảo vệ dữ liệu. Client có thể retry do timeout, người dùng có thể nhấn nút nhiều lần, proxy có thể retry theo cấu hình và nhiều request có thể đến đồng thời.

## 9. Ví dụ lựa chọn thiết kế

| Nhu cầu | Thiết kế phù hợp | Điều cần tránh |
|---|---|---|
| Đọc thông tin đơn hàng | GET /orders/42 | Thực hiện ghi nghiệp vụ trong GET |
| Đặt trạng thái đơn hàng thành PAID | PUT hoặc PATCH với semantics đặt giá trị; có thể thêm If-Match | Biến request thành thao tác cộng dồn hoặc thu tiền mỗi lần gọi |
| Tạo đơn hàng mới | POST kèm idempotency key hoặc mã yêu cầu duy nhất | Retry POST mù sau timeout |
| Xóa đơn hàng | DELETE với xử lý response khi resource đã vắng mặt | Gửi email/xử lý hoàn tiền lặp lại không có deduplication |
| Cộng tiền vào tài khoản | Lệnh nghiệp vụ có operation ID/idempotency key và transaction phù hợp | Giả định PATCH tự động idempotent |
| Cập nhật resource khi có nhiều client | Version/ETag, If-Match và xử lý conflict | Ghi đè dữ liệu mới bằng bản đọc cũ |

## 10. Kiểm tra thiết kế trước khi bật retry

Với mỗi endpoint ghi, hãy trả lời các câu hỏi sau:

1. Method và URI biểu diễn thao tác nào? Request có đặt trạng thái hay tạo một hành động mới?
2. Nếu gửi lại đúng method, URI, payload và precondition, trạng thái nghiệp vụ cuối cùng có thay đổi thêm không?
3. Những side effect nào chạy khi request được xử lý: event, email, payment, message hay lời gọi dịch vụ khác?
4. Nếu server commit nhưng response bị mất, client có thể xác định kết quả bằng GET hoặc operation ID không?
5. POST/PATCH không lũy đẳng có idempotency key, unique constraint hoặc cơ chế deduplication nào?
6. Hai request cùng key đến đồng thời có thể tạo hai thao tác nghiệp vụ không?
7. Cùng một key nhưng payload khác được xử lý ra sao?
8. Retry có giữ nguyên key và có giới hạn số lần, backoff, jitter và xử lý Retry-After không?
9. Nếu dùng ETag/If-Match, client xử lý 412 và đối chiếu kết quả sau timeout như thế nào?
10. Có kiểm soát deduplication cho message hoặc side effect ngoài transaction database không?

Nên kiểm tra cả trường hợp request được xử lý thành công nhưng response bị làm mất, hai request cùng idempotency key đến đồng thời, cùng key nhưng payload khác, retry sau khi resource đã bị xóa và retry với ETag cũ. Những tình huống này giúp phát hiện lỗi mà một bài kiểm tra chỉ gửi request một lần thường bỏ sót.

## Kết luận

Safe mô tả việc client không yêu cầu thay đổi trạng thái nghiệp vụ; idempotent mô tả hiệu ứng dự kiến không đổi khi lặp lại cùng request. GET, HEAD, OPTIONS, TRACE, PUT và DELETE có semantics idempotent; POST không idempotent theo mặc định và PATCH phụ thuộc cách định nghĩa thao tác.

Khi xây dựng API với Spring Data REST, cần đánh giá cả trạng thái resource, response và side effect. PUT/DELETE có thể retry theo đúng hợp đồng; POST/PATCH cần cơ chế idempotency hoặc deduplication khi thao tác không lũy đẳng. Timeout chỉ cho biết client chưa nhận được kết quả, không chứng minh server chưa commit.