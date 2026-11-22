# DELETE và ngữ nghĩa loại bỏ liên kết của tài nguyên đích

## 1. Mục tiêu bài học

Trong module **INTEGRATION_API_REST**, người học thiết kế REST API theo tài nguyên (resource), URI, phương thức, mã trạng thái HTTP và hợp đồng dữ liệu rõ ràng. Bài học thuộc chương **Phương thức HTTP** này tập trung vào **DELETE**, phương thức yêu cầu máy chủ **loại bỏ sự liên kết giữa tài nguyên đích và chức năng hiện tại của nó**.

Sau bài học, bạn có thể:

- Giải thích đúng ngữ nghĩa DELETE theo HTTP, phân biệt việc bỏ liên kết URI với xóa vật lý dữ liệu.
- Chọn URI và phương thức phù hợp cho xóa tài nguyên, gỡ quan hệ hoặc hủy một quy trình nghiệp vụ.
- Giải thích vì sao DELETE **idempotent** nhưng **không safe**, kể cả khi các lần gọi trả mã trạng thái khác nhau.
- Chọn phản hồi **200, 202, 204** và các lỗi **404, 409, 412, 428** theo hợp đồng API.
- Sử dụng **ETag** và **If-Match** để bảo vệ dữ liệu khỏi thao tác xóa dựa trên phiên bản cũ.
- Xử lý cache, xóa mềm, xóa bất đồng bộ, quan hệ phụ thuộc, bảo mật và retry.
- Viết hợp đồng OpenAPI và kiểm thử DELETE bằng HTTP hoặc Java/Spring.

**Tình huống xuyên suốt:** một API quản lý tài liệu cho doanh nghiệp. Người dùng có thể yêu cầu xóa tài liệu, trong khi người khác đang sửa tài liệu đó, file gốc được lưu trong object storage và bản sao phục vụ tìm kiếm được cập nhật bất đồng bộ.

## 2. Ngữ nghĩa của DELETE theo HTTP

Theo **RFC 9110, mục 9.3.5**, DELETE yêu cầu origin server **remove the association between the target resource and its current functionality**: loại bỏ mối liên hệ giữa tài nguyên tại URI đích với chức năng hiện thời của nó. Có thể hiểu tương tự việc gỡ một ánh xạ URI đang được máy chủ cung cấp.

Ví dụ:

~~~http
DELETE /api/v1/documents/8fa7 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Đối tượng của DELETE là tài nguyên được định danh bởi URI **/api/v1/documents/8fa7**. Sau khi xóa theo hợp đồng, yêu cầu GET tới URI đó thường không còn nhận biểu diễn đang hoạt động của tài liệu.

**Điểm quan trọng:** DELETE không bắt buộc máy chủ lập tức xóa toàn bộ các byte dữ liệu. Server có thể:

- Xóa bản ghi khỏi cơ sở dữ liệu.
- Đánh dấu **deleted_at** rồi ẩn tài liệu khỏi truy vấn thông thường (soft delete).
- Ngắt một liên kết, chẳng hạn gỡ user khỏi nhóm.
- Vô hiệu hóa URI truy cập ngay và lên lịch dọn object storage/search index về sau.
- Giữ bản sao lưu hoặc lịch sử theo chính sách retention, legal hold và nghĩa vụ tuân thủ.

Ngược lại, DELETE không mang nghĩa **URI đó sẽ vĩnh viễn không thể được sử dụng lại**. Chính sách tái sử dụng ID hoặc URI do API quyết định. Các nghiệp vụ cần hạn chế tái xuất hiện có thể dùng tombstone hoặc định danh/generation không tái sử dụng.

### 2.1. Xóa tài nguyên khác với gỡ quan hệ

Hai endpoint sau có ngữ nghĩa khác nhau:

~~~http
DELETE /api/v1/users/u-42 HTTP/1.1
DELETE /api/v1/projects/p-3/members/u-42 HTTP/1.1
~~~

Yêu cầu đầu hướng vào tài nguyên **user u-42**. Yêu cầu thứ hai hướng vào **quan hệ thành viên giữa project p-3 và user u-42**, nên chỉ cần gỡ thành viên, không yêu cầu xóa tài khoản user. URI cần thể hiện đúng thực thể hoặc mối quan hệ mà client muốn tác động.

Tương tự, **DELETE /carts/c-1/items/i-7** nhằm loại bỏ dòng hàng khỏi giỏ, không có nghĩa xóa sản phẩm khỏi catalog.

### 2.2. Xóa không mặc nhiên là hủy nghiệp vụ

Một đơn hàng đã thanh toán có thể không được phép xóa lịch sử giao dịch, nhưng có thể **hủy** theo quy trình hoàn tiền. Khi đó mô hình hóa một tài nguyên cancellation thường diễn đạt đúng hơn:

~~~http
POST /api/v1/orders/o-17/cancellations HTTP/1.1
Content-Type: application/json

{"reason":"Customer requested cancellation"}
~~~

Việc dùng POST cho tài nguyên cancellation cho phép xử lý quy trình có trạng thái và lịch sử. Lựa chọn này phụ thuộc nghiệp vụ; không thể quyết định phương thức chỉ từ nhãn nút giao diện “Xóa”.

## 3. DELETE khác gì GET, PUT, POST và PATCH?

| Phương thức | Ý nghĩa chính | Safe? | Idempotent? |
| --- | --- | --- | --- |
| **GET** | Yêu cầu biểu diễn của tài nguyên | Có | Có |
| **HEAD** | Nhận metadata tương tự GET nhưng không có response content | Có | Có |
| **POST** | Yêu cầu tài nguyên đích xử lý biểu diễn theo ngữ nghĩa của tài nguyên | Không | Không mặc định |
| **PUT** | Tạo hoặc thay thế trạng thái của tài nguyên đích | Không | Có |
| **PATCH** | Áp dụng thay đổi một phần theo định dạng patch | Không | Không mặc định |
| **DELETE** | Gỡ sự liên kết hiện tại của tài nguyên đích | **Không** | **Có** |
| **OPTIONS** | Hỏi khả năng giao tiếp được hỗ trợ | Có | Có |

**Safe**: client không yêu cầu thay đổi trạng thái. Server vẫn có thể ghi access log khi xử lý GET, nhưng log là tác dụng phụ chứ không phải yêu cầu chính của client.

**Idempotent**: tác dụng dự kiến của nhiều yêu cầu giống hệt nhau lên trạng thái của tài nguyên tương đương tác dụng của một yêu cầu. DELETE idempotent vì sau khi gỡ thành công, lặp lại yêu cầu gỡ cùng liên kết không cần làm tài nguyên “bị xóa thêm lần nữa”.

## 4. DELETE idempotent: điều gì xảy ra khi retry?

Giả sử server xóa tài liệu thành công, nhưng phản hồi bị mất do lỗi mạng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant D as Data store
    C->>A: DELETE /documents/8fa7
    A->>D: Gỡ liên kết của tài liệu
    D-->>A: Commit thành công
    A--xC: Phản hồi 204 bị mất
    Note over C: Client chưa biết yêu cầu đã hoàn tất
    C->>A: Retry DELETE /documents/8fa7
    A->>D: Kiểm tra tài liệu còn hoạt động?
    D-->>A: Không
    A-->>C: 404 theo hợp đồng ví dụ
~~~

Lần đầu có thể trả **204 No Content**, lần sau **404 Not Found**, nhưng trạng thái cuối vẫn là **tài liệu không còn khả dụng**. Vì thế DELETE vẫn idempotent.

Hai chính sách phản hồi có thể hợp lý:

| Tình huống | Chính sách trả trạng thái thực | Chính sách đảm bảo vắng mặt |
| --- | --- | --- |
| Tài liệu tồn tại, DELETE thành công | 204 | 204 |
| DELETE lặp lại sau khi tài liệu đã bị xóa | 404 hoặc 410 | 204 |
| Ý nghĩa | Cho client biết URI đã không còn | Cho client biết mục tiêu “không còn” đã đạt |

**Cả hai chính sách đều có thể giữ idempotency.** Phương thức idempotent không đòi hỏi tất cả phản hồi phải có cùng status code hoặc body.

Việc DELETE lặp lại có thể tạo thêm access log. Tuy vậy, nếu mỗi lần retry gây hoàn tiền, gửi email nghiệp vụ hay tính phí khác nhau thì thiết kế cần cơ chế nhận dạng yêu cầu và ngăn tác dụng lặp ngoài ý muốn. Không nên lấy tên phương thức DELETE làm bảo đảm rằng toàn bộ workflow bên dưới đã idempotent.

Khi gặp timeout, client có thể retry với backoff và giới hạn số lần. Để xác nhận kết quả cuối, client có thể dùng GET/HEAD tới URI đích hoặc đọc resource trạng thái công việc nếu API xóa bất đồng bộ.

## 5. Thiết kế URI cho DELETE

URI thường chỉ ra chính resource cần loại bỏ:

~~~http
DELETE /api/v1/documents/8fa7
DELETE /api/v1/carts/c-10/items/i-7
DELETE /api/v1/projects/p-3/members/u-42
DELETE /api/v1/users/u-42/sessions/s-11
~~~

| URI | Tác dụng mong đợi |
| --- | --- |
| /documents/8fa7 | Gỡ tài nguyên tài liệu 8fa7 |
| /carts/c-10/items/i-7 | Bỏ dòng hàng i-7 trong giỏ c-10 |
| /projects/p-3/members/u-42 | Gỡ user u-42 khỏi dự án p-3 |
| /users/u-42/sessions/s-11 | Thu hồi phiên đăng nhập s-11 |

Không thiết kế **GET /documents/8fa7/delete** để thực hiện xóa: GET có ngữ nghĩa safe, crawler, prefetch hoặc trình xem trước liên kết có thể gọi GET ngoài ý định của người dùng.

URI kiểu **DELETE /deleteDocument?id=8fa7** không tận dụng rõ ngữ nghĩa resource khi đã có URI tài liệu ổn định.

### 5.1. Có nên DELETE trên collection?

HTTP không cấm DELETE trên URI collection, nhưng **DELETE /documents** thường dễ bị hiểu là xóa cả tập hợp. Nếu nghiệp vụ cần xóa nhiều tài liệu, có thể:

1. Gửi DELETE cho từng tài nguyên để nhận kết quả và lỗi riêng biệt.
2. Tạo resource xử lý xóa hàng loạt qua POST, rồi theo dõi trạng thái công việc.
3. Chỉ hỗ trợ DELETE collection nếu hợp đồng thực sự định nghĩa rõ phạm vi, phân quyền và điều kiện an toàn.

Không suy ra rằng query **?filter=...** trên endpoint đọc cũng tự động áp dụng cho việc xóa hàng loạt.

## 6. Ba mã thành công của DELETE

| Mã | Nghĩa HTTP | Cách dùng điển hình |
| --- | --- | --- |
| **204 No Content** | Yêu cầu đã được thực thi, không cung cấp response content | Xóa đồng bộ hoàn thành |
| **200 OK** | Yêu cầu đã được thực thi, response có biểu diễn mô tả trạng thái | Muốn trả biên bản hoặc kết quả xóa |
| **202 Accepted** | Đã chấp nhận để xử lý nhưng tác vụ **chưa hoàn tất** | Xóa bất đồng bộ hoặc phải dọn nhiều hệ thống |

### 6.1. Phản hồi 204

~~~http
HTTP/1.1 204 No Content
Date: Wed, 18 Nov 2026 09:00:00 GMT
~~~

**Không gửi response content cùng status 204**, kể cả JSON có trường success. Nếu cần nội dung mô tả, dùng 200.

### 6.2. Phản hồi 200

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "documentId": "8fa7",
  "state": "removed",
  "removedAt": "2026-11-18T09:00:00Z"
}
~~~

Có thể dùng khi client cần biên bản xóa hoặc thông tin trạng thái, với điều kiện đây là hành động đã được thực hiện.

### 6.3. Phản hồi 202

~~~http
HTTP/1.1 202 Accepted
Location: /api/v1/operations/op-712
Retry-After: 3
Content-Type: application/json

{
  "operationId": "op-712",
  "state": "queued"
}
~~~

**202 không cam kết chắc chắn tác vụ sẽ hoàn thành thành công.** Location trong ví dụ trỏ đến resource theo dõi job; đây là lựa chọn thiết kế hữu ích, không phải header bắt buộc với mọi 202. Retry-After là gợi ý thời gian giữa các lần kiểm tra, không thay cho trạng thái công việc.

## 7. Mã lỗi quan trọng và cách chọn

| Mã | Khi sử dụng với DELETE |
| --- | --- |
| **400 Bad Request** | Cú pháp request hoặc ID sai định dạng |
| **401 Unauthorized** | Chưa xác thực hợp lệ |
| **403 Forbidden** | Đã xác thực nhưng không có quyền xóa |
| **404 Not Found** | Không có tài nguyên được phép truy cập tại URI, kể cả sau khi xóa |
| **405 Method Not Allowed** | URI tồn tại nhưng không hỗ trợ DELETE; phải kèm header **Allow** |
| **409 Conflict** | Xung đột với trạng thái nghiệp vụ: tài liệu bị khóa, còn quan hệ bắt buộc |
| **410 Gone** | Server chủ ý xác nhận resource trước đây đã có và nay không còn |
| **412 Precondition Failed** | If-Match không thỏa điều kiện phiên bản |
| **428 Precondition Required** | API bắt buộc gửi điều kiện If-Match nhưng client không gửi |
| **429 Too Many Requests** | Người gọi vượt giới hạn |
| **503 Service Unavailable** | Dịch vụ tạm không xử lý được, có thể kèm Retry-After |

**409 khác 412:** nếu tài liệu bị khóa bởi quy trình phê duyệt, đây là xung đột nghiệp vụ, thường dùng 409. Nếu client gửi ETag cũ, đây là lỗi điều kiện HTTP, dùng 412.

**404 khác 410:** 410 thể hiện tài nguyên được biết là không còn và tình trạng có vẻ lâu dài, trong khi 404 không khẳng định điều đó. Vì lý do bảo mật, API có thể trả 404 khi không muốn tiết lộ tài nguyên có tồn tại hay không.

Phản hồi lỗi có thể dùng **application/problem+json** theo RFC 9457:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/document-locked",
  "title": "Document cannot be deleted",
  "status": 409,
  "detail": "Tài liệu đang bị khóa bởi quy trình phê duyệt.",
  "instance": "/api/v1/documents/8fa7"
}
~~~

Không đưa SQL, stack trace, token hoặc thông tin nhạy cảm của tenant khác vào nội dung lỗi. Có thể mở rộng problem details với mã lỗi ứng dụng và correlation ID.

## 8. DELETE có request body không?

Theo HTTP, request content trong DELETE **không có ngữ nghĩa chung được định nghĩa**. Vì vậy, thiết kế REST API thông thường nên xác định tài nguyên bằng URI và điều kiện bằng header.

Một ví dụ dễ gây vấn đề:

~~~http
DELETE /api/v1/documents HTTP/1.1
Content-Type: application/json

{"ids": ["8fa7", "9ba8"]}
~~~

Các proxy, framework và thành phần trung gian có thể không xử lý DELETE với body nhất quán. Nội dung DELETE cũng có thể làm tăng nguy cơ lỗi phân tích thông điệp, bao gồm tình huống request smuggling do các thành phần hiểu khác nhau.

Nếu cần xóa theo lô, có thể mô hình hóa một tài nguyên job:

~~~http
POST /api/v1/document-deletion-jobs HTTP/1.1
Content-Type: application/json
Idempotency-Key: batch-2026-11-18-01

{
  "documentIds": ["8fa7", "9ba8"]
}
~~~

Idempotency-Key là một **quy ước ứng dụng** nếu server hỗ trợ và lưu khóa theo hợp đồng; chỉ thêm header không tự động bảo đảm POST sẽ idempotent. Cần định nghĩa key scope, TTL, xử lý payload khác nhau với cùng key và truy xuất kết quả trước đó.

## 9. Xóa đồng bộ và xóa bất đồng bộ

### 9.1. Đồng bộ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant D as Database
    C->>A: DELETE /documents/8fa7
    A->>A: Xác thực, phân quyền, kiểm tra điều kiện
    A->>D: Xóa hoặc đánh dấu deleted
    D-->>A: Commit thành công
    A-->>C: 204 No Content
~~~

Nếu hợp đồng chỉ hứa **tài liệu không còn truy cập qua API** ngay sau commit, server có thể trả 204 sau khi đã gỡ quyền truy cập, đồng thời dọn file vật lý về sau. Nếu hợp đồng hứa **purge toàn bộ dữ liệu trước phản hồi**, chỉ được trả thành công tương ứng khi điều đó thật sự hoàn thành.

### 9.2. Bất đồng bộ

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant Q as Job Queue
    participant W as Worker
    C->>A: DELETE /documents/8fa7
    A->>A: Xác thực, phân quyền, điều kiện
    A->>Q: Lưu job xóa bền vững
    A-->>C: 202 + Location: /operations/op-712
    C->>A: GET /operations/op-712
    A-->>C: 200 state=running
    Q->>W: Xử lý job
    W->>W: Xóa / thu hồi theo chính sách
    C->>A: GET /operations/op-712
    A-->>C: 200 state=succeeded
~~~

Một response từ operation resource:

~~~json
{
  "operationId": "op-712",
  "target": "/api/v1/documents/8fa7",
  "state": "succeeded",
  "startedAt": "2026-11-18T09:00:00Z",
  "completedAt": "2026-11-18T09:00:12Z"
}
~~~

Cần quy định các trạng thái **queued, running, succeeded, failed** và nếu hỗ trợ **cancelled**, cùng quy tắc retry, giám sát và phân quyền đọc job.

Để tránh worker trễ xóa nhầm tài nguyên vừa được tạo lại cùng ID, job nên chứa **resource generation/version** hoặc tombstone xác nhận đúng đối tượng. Nếu một bước dọn dẹp lỗi, job phải có trạng thái có thể quan sát và chạy lại an toàn.


## 10. Xóa có điều kiện với ETag và If-Match

Một rủi ro của DELETE là **xóa tài liệu đã thay đổi sau khi người dùng đọc**. Lan đọc tài liệu v7, Minh chỉnh sửa thành v8, rồi Lan gửi yêu cầu xóa dựa trên giao diện cũ. Nếu server xóa vô điều kiện, thay đổi của Minh có thể mất mà Lan không biết.

~~~mermaid
sequenceDiagram
    participant L as Lan
    participant S as REST API
    participant M as Minh
    L->>S: GET /documents/8fa7
    S-->>L: 200 ETag v7
    M->>S: PATCH /documents/8fa7
    S-->>M: 200 ETag v8
    L->>S: DELETE /documents/8fa7, If-Match v7
    S-->>L: 412 Precondition Failed
~~~

HTTP có cơ chế **conditional request**. Client lấy ETag từ GET:

~~~http
HTTP/1.1 200 OK
ETag: "v7"
Content-Type: application/json

{"id":"8fa7","title":"Quy trình onboarding","version":7}
~~~

Sau đó gửi:

~~~http
DELETE /api/v1/documents/8fa7 HTTP/1.1
If-Match: "v7"
Authorization: Bearer <access-token>
~~~

Nếu strong ETag hiện tại vẫn là **"v7"**, server có thể xóa. Nếu đã sang **"v8"**, điều kiện sai và server trả **412 Precondition Failed**; tài liệu phải được giữ nguyên.

- **If-Match** dùng so sánh strong ETag. Weak ETag dạng **W/"v7"** không thỏa so sánh này.
- **If-Match: \*** yêu cầu tài nguyên phải có biểu diễn hiện tại; không chống xóa tài liệu vừa thay đổi so với lần đọc trước.
- **428 Precondition Required** phù hợp nếu API bắt buộc có If-Match mà client không gửi.
- Khi tài nguyên không còn, server có thể trả 404 theo hợp đồng. Retry sau khi xóa thành công có thể trả 404 hoặc 412 tùy tình huống, vì client không thể suy ra chắc từ việc mất phản hồi.

**Quan trọng:** kiểm tra ETag tại ứng dụng rồi xóa vô điều kiện trong bước tiếp theo **không an toàn trước race**. So sánh phiên bản và thay đổi dữ liệu phải được bảo vệ nguyên tử bằng optimistic locking hoặc câu lệnh DB có điều kiện.

## 11. Xóa mềm, xóa vật lý và quan hệ phụ thuộc

| Cách xóa | Ý tưởng | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Hard delete** | Xóa bản ghi/file thật | Gọn dữ liệu | Khó khôi phục, phụ thuộc backup và FK |
| **Soft delete** | Đặt deleted_at/status=deleted | Phục hồi, audit dễ hơn | Mọi đường đọc cần lọc đúng |
| **Tombstone** | Giữ dấu ID/generation đã xóa | Tránh tái xuất hiện bởi retry/event cũ | Cần chính sách lưu và loại bỏ tombstone |
| **Asynchronous purge** | Worker dọn bản sao sau khi gỡ truy cập | Giảm latency của DELETE | Cần retry, đối soát, giám sát |
| **Retention/legal hold** | Giữ dữ liệu trong thời hạn bắt buộc | Hỗ trợ tuân thủ | Không được hứa xóa vật lý tức thì |

Ví dụ cập nhật trạng thái có điều kiện:

~~~sql
UPDATE documents
SET deleted_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND deleted_at IS NULL
  AND version = :expected_version;
~~~

Các tham số bắt đầu bằng dấu hai chấm là placeholder được driver bind. Tenant ID phải đến từ ngữ cảnh đã xác thực và phân quyền.

Nếu cập nhật **một dòng**, server đã chuyển trạng thái. Nếu cập nhật **không dòng nào**, cần xác định lý do: không tồn tại, đã xóa, khác tenant hoặc khác version. Không được luôn suy ra kết quả 404 mà không xét hợp đồng và chính sách bảo mật.

Một tài liệu có thể liên quan bình luận, quyền chia sẻ, search index, object storage và lịch sử kiểm toán. **ON DELETE CASCADE** chỉ thực hiện ràng buộc đã khai báo trong DB; nó không tự xóa file trên object storage hay dữ liệu trong hệ tìm kiếm. Khi cần thao tác phân tán, **transactional outbox** hoặc cơ chế bền vững tương đương giúp ghi nhận sự kiện cleanup cùng giao dịch thay đổi trạng thái.

Đối với yêu cầu xóa dữ liệu cá nhân, phản hồi HTTP thành công **không tự chứng minh** rằng backup, log hoặc dữ liệu ở bên thứ ba đã được tiêu hủy. Cần quy trình quản lý retention, xóa theo chính sách và kiểm chứng riêng.

## 12. Cache sau DELETE

Phản hồi DELETE không cacheable theo HTTP. Một DELETE thành công đi qua cache HTTP phù hợp kích hoạt cơ chế invalidation URI đích theo quy tắc caching. Hệ thống thực tế còn có CDN, cache ứng dụng, client và search index có thể không thấy request DELETE.

Ví dụ:

~~~text
GET    /documents/8fa7 -> 200 từ cache
DELETE /documents/8fa7 -> 204 từ origin
GET    /documents/8fa7 -> phải phản ánh trạng thái mới theo hợp đồng
~~~

Nếu CDN hoặc cache riêng không nhận thông báo, nó có thể tiếp tục trả tài liệu cũ. Thiết kế cần:

- Invalidate tài liệu đích và nội dung liên quan như danh sách, kết quả tìm kiếm, thống kê.
- Công bố mức nhất quán: ngay sau commit hay eventual consistency có khoảng trễ.
- Thu hồi truy cập tại origin và đường phát file để không tiếp tục lộ tài liệu nhạy cảm.
- Theo dõi lỗi và thời gian trễ của job cập nhật index/cache.
- Bảo vệ dữ liệu không bị đưa trở lại cache bởi một thao tác đến muộn.

Không nhầm việc cache đã bị invalidation với việc dữ liệu trong backup đã được purge.

## 13. Bảo mật: kiểm tra quyền xóa đúng resource

DELETE thay đổi trạng thái nên cần kiểm soát nhiều lớp:

1. **Authentication:** token hoặc session phải hợp lệ theo chính sách.
2. **Authorization:** người gọi được phép xóa **đúng tài nguyên ID** này, trong đúng tenant.
3. **Chính sách nghiệp vụ:** nếu tài liệu locked hoặc có legal hold thì từ chối theo lỗi rõ ràng.
4. **Tenant isolation:** truy vấn DB dùng tenant đã xác thực, không tin ID/tenant do người dùng tự điền.
5. **Audit:** lưu actor, resource, thời điểm, kết quả, correlation ID và thông tin phù hợp mà không lộ nội dung nhạy cảm.
6. **Rate limiting:** hạn chế abuse và xóa diện rộng bất thường.
7. **CSRF:** nếu xác thực bằng cookie trong trình duyệt, bảo vệ CSRF cho yêu cầu thay đổi; CORS không thay CSRF.
8. **Background workers:** chỉ cho phép job đúng quyền, đúng tenant và đúng generation tài nguyên.

Với request JavaScript cross-origin, DELETE thường kích hoạt **CORS preflight OPTIONS**, vì DELETE không thuộc nhóm phương thức CORS-safelisted. Cho phép DELETE ở CORS không có nghĩa đã phân quyền người dùng.

Khi không muốn tiết lộ tài nguyên của tenant khác tồn tại, API có thể chọn 404 thay vì 403. Quy tắc này phải được áp dụng nhất quán và kiểm thử trên toàn bộ endpoint.


## 14. Java/Spring Boot: DELETE có điều kiện

Ví dụ sau minh họa một API xóa tài liệu **đồng bộ**, bắt buộc **If-Match**, có tenant context và điều kiện version ở thao tác DB. Code tập trung vào hợp đồng HTTP và race condition; các import, entity, cấu hình security và exception handler cần được hoàn thiện trong dự án thật.

### 14.1. Controller

~~~java
@RestController
@RequestMapping("/api/v1/documents")
public class DocumentController {
    private final DocumentService service;
    private final TenantContext tenantContext;

    public DocumentController(DocumentService service,
                              TenantContext tenantContext) {
        this.service = service;
        this.tenantContext = tenantContext;
    }

    @DeleteMapping("/{documentId}")
    public ResponseEntity<Void> delete(
            @PathVariable UUID documentId,
            @RequestHeader(value = "If-Match", required = false) String ifMatch) {

        if (ifMatch == null || ifMatch.isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_REQUIRED,
                    "If-Match header is required");
        }

        UUID tenantId = tenantContext.requireAuthorizedTenant();
        service.deleteIfVersionMatches(tenantId, documentId, ifMatch);
        return ResponseEntity.noContent().build();
    }
}
~~~

**TenantContext** là một thành phần minh họa lấy tenant được phép truy cập từ security context đã xác thực. Không lấy tenant ID trực tiếp từ header chưa xác minh. Ngoài quyền tenant, service còn phải kiểm tra quyền xóa theo resource ID khi nghiệp vụ yêu cầu.

### 14.2. Service

~~~java
@Service
public class DocumentService {
    private final DocumentRepository repository;

    public DocumentService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void deleteIfVersionMatches(UUID tenantId, UUID id, String ifMatch) {
        Document document = repository.findByTenantIdAndId(tenantId, id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));

        // Chỉ minh họa một strong ETag dạng "vN".
        String currentEtag = "\"v" + document.getVersion() + "\"";
        if (!currentEtag.equals(ifMatch)) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "Document has changed");
        }

        // Ràng buộc version trực tiếp trong thao tác DELETE.
        int deleted = repository.deleteByTenantAndIdAndVersion(
                tenantId, id, document.getVersion());

        if (deleted != 1) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "Document changed during delete");
        }
    }
}
~~~

### 14.3. Repository

~~~java
public interface DocumentRepository extends JpaRepository<Document, UUID> {
    Optional<Document> findByTenantIdAndId(UUID tenantId, UUID id);

    @Modifying
    @Query("""
           DELETE FROM Document d
           WHERE d.tenantId = :tenantId
             AND d.id = :id
             AND d.version = :version
           """)
    int deleteByTenantAndIdAndVersion(
            @Param("tenantId") UUID tenantId,
            @Param("id") UUID id,
            @Param("version") long version);
}
~~~

**Các giới hạn cần nêu trước khi dùng production:**

- Service chỉ hỗ trợ một giá trị strong ETag dạng **"vN"**. HTTP hỗ trợ cú pháp danh sách entity tag và **If-Match: \***; production cần parser đầy đủ hoặc định nghĩa rõ phần cú pháp mà API chấp nhận.
- Ví dụ dùng hard delete cho một bản ghi đơn giản. JPQL bulk delete có thể bỏ qua callback/cascade của ORM; phải xem xét ràng buộc DB, soft delete và workflow dọn dẹp trong ứng dụng thực.
- Câu lệnh DB có điều kiện version giúp tránh race sau khi đọc; không được chỉ kiểm tra version bằng SELECT rồi xóa vô điều kiện.
- Mapping lỗi 404/409/412/428 có thể được tập trung bằng exception handler và phản hồi **application/problem+json**.
- Không được giả định việc tìm thấy document theo tenant tự động chứng minh quyền xóa. Cần áp dụng chính sách quyền theo tài liệu, vai trò và trạng thái.
- Nếu tài liệu có file, search index hoặc hệ thống phụ, cần outbox/job để xử lý hậu quả nhất quán.

### 14.4. Khi nào nên trả 202 từ Spring?

Nếu việc dọn dẹp phải chạy lâu và hợp đồng yêu cầu chờ kết quả, controller có thể ghi job bền vững rồi trả **ResponseEntity.accepted()** với Location đến operation resource. Không trả 204 chỉ vì đã đưa job vào hàng đợi khi hành động xóa theo hợp đồng **vẫn chưa được thực thi**.

## 15. Hợp đồng OpenAPI cho DELETE

Đây là ví dụ **OpenAPI 3.1** với xóa có điều kiện và phản hồi 204 không chứa body:

~~~yaml
openapi: 3.1.0
info:
  title: Document API
  version: 1.0.0
paths:
  /api/v1/documents/{documentId}:
    delete:
      operationId: deleteDocument
      summary: Gỡ tài liệu khỏi API
      description: >
        Yêu cầu xóa theo strong ETag. URI đã không tồn tại được báo 404.
        Phiên bản không khớp được báo 412.
      parameters:
        - in: path
          name: documentId
          required: true
          schema:
            type: string
            format: uuid
        - in: header
          name: If-Match
          required: true
          description: Strong ETag từ GET trước đó, ví dụ "v7".
          schema:
            type: string
      responses:
        '204':
          description: Đã gỡ tài liệu; không có response content
        '400':
          description: Request hoặc ID sai định dạng
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền xóa
        '404':
          description: Không tìm thấy tài liệu trong phạm vi được phép
        '409':
          description: Trạng thái nghiệp vụ không cho phép xóa
        '412':
          description: If-Match không còn đúng
        '428':
          description: Thiếu If-Match bắt buộc
      security:
        - bearerAuth: []
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Bản production nên định nghĩa schema **Problem Details** dùng chung cho phản hồi lỗi và các ví dụ rõ ràng. Nếu API xóa bất đồng bộ, bổ sung 202 và resource theo dõi trạng thái công việc.

OpenAPI mô tả hợp đồng, không tự thực thi xác thực, phân quyền hoặc idempotency.

## 16. Kiểm thử DELETE bằng HTTP và Java

Có thể dùng curl, Postman, Rest Assured, Spring MockMvc hoặc integration test. Ví dụ lệnh cho **môi trường thử nghiệm**, thay token, ETag, ID và URI theo dữ liệu kiểm thử:

~~~bash
# Lấy biểu diễn và ETag
curl -i \
  -H "Authorization: Bearer YOUR_TEST_TOKEN" \
  https://api.example.test/api/v1/documents/8fa7

# Xóa với ETag vừa nhận
curl -i -X DELETE \
  -H "Authorization: Bearer YOUR_TEST_TOKEN" \
  -H 'If-Match: "v7"' \
  https://api.example.test/api/v1/documents/8fa7

# Đọc lại để xác nhận URI
curl -i \
  -H "Authorization: Bearer YOUR_TEST_TOKEN" \
  https://api.example.test/api/v1/documents/8fa7
~~~

Không chạy DELETE trên dữ liệu production khi chưa xác nhận phạm vi và quyền thực hiện. Việc dùng ví dụ ID **8fa7** chỉ nhằm diễn giải, không phải UUID hợp lệ cho endpoint Spring mẫu; khi chạy ví dụ Java UUID cần thay bằng định danh UUID đúng định dạng.

### 16.1. Ma trận kiểm thử

| Trường hợp | Chuẩn bị / hành động | Kết quả mong đợi |
| --- | --- | --- |
| Xóa thành công | Tài liệu tồn tại, ETag và quyền hợp lệ | 204 không body; GET không còn biểu diễn hoạt động |
| Retry sau thành công | Gửi lại cùng DELETE | 404 theo hợp đồng mẫu; dữ liệu vẫn đã xóa |
| Thiếu token | Không gửi thông tin xác thực | 401 hoặc phản hồi xác thực tương ứng |
| Thiếu quyền | Caller không có quyền trên tài liệu | 403 hoặc 404 theo chính sách che giấu |
| Chéo tenant | User A cố xóa ID tenant B | Không xóa được, không lộ thông tin B |
| Thiếu If-Match | Gửi DELETE thiếu header | 428; tài liệu không đổi |
| ETag cũ | GET v7, update v8, DELETE v7 | 412; tài liệu v8 vẫn còn |
| Race update/delete | Hai thao tác đồng thời | Không có xóa nhầm phiên bản mới |
| Trạng thái locked | Xóa tài liệu bị khóa | 409; không đổi |
| Không tồn tại | URI không có tài liệu | 404 theo hợp đồng |
| Cache | GET được cache trước khi xóa | Không trả dữ liệu cũ quá mức nhất quán được cam kết |
| Cascade | Tài liệu có bình luận, file, search record | Xử lý theo retention và ràng buộc được thiết kế |
| Timeout sau commit | Commit xong nhưng phản hồi mất, rồi retry | Trạng thái cuối đúng, không có nghiệp vụ lặp |
| Job bất đồng bộ | Trả 202 và Location job | Có thể kiểm tra trạng thái, quyền và lỗi |
| Worker retry | Cùng sự kiện cleanup chạy hai lần | Không xóa nhầm version/generation khác |
| DELETE không được phép | URI chỉ hỗ trợ GET | 405 và header Allow phù hợp |
| Giới hạn tốc độ | Gửi nhiều request | 429 theo chính sách, không quá tải |

### 16.2. Ca thử có giá trị hơn việc DELETE hai lần

Mô phỏng **commit thành công nhưng client bị ngắt trước khi nhận phản hồi**:

1. Gửi DELETE hợp lệ.
2. Sau khi DB commit, giả lập lỗi kết nối.
3. Client gửi lại cùng yêu cầu.
4. Đọc lại tài nguyên hoặc operation status.
5. Đối soát số event, file, job, audit và hành động nghiệp vụ liên quan.

Kết quả cần chứng minh tính idempotent của tác dụng mong muốn, không chỉ là hai lần gọi API không crash.

## 17. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Hiểu DELETE phải xóa mọi byte vật lý tức thì | Cam kết sai với người dùng | Tách rõ URI removal, soft delete và purge |
| Dùng GET cho thao tác xóa | Crawler/prefetch có thể vô tình kích hoạt | Dùng DELETE hoặc resource nghiệp vụ phù hợp |
| Hủy quy trình nghiệp vụ phức tạp bằng DELETE không rõ nghĩa | Mất audit, workflow và dữ liệu liên quan | Mô hình cancellation hoặc transition riêng |
| Cho rằng idempotent nghĩa là luôn trả 204 | Client không xử lý retry chính xác | Tài liệu hóa 204/404/410 sau lần đầu |
| Chỉ so ETag rồi xóa vô điều kiện | Race và lost update | Ràng buộc version vào câu lệnh DB |
| Trả 204 cùng JSON body | Sai hợp đồng HTTP | 204 không body, hoặc 200 có nội dung |
| Trả 202 mà không có trạng thái job | Client không biết tác vụ thành công không | Operation resource + giám sát lỗi |
| Bỏ quên cache, file và search | Tiếp tục thấy dữ liệu đã xóa | Invalidation, outbox và cleanup |
| Kiểm tra quyền chung mà thiếu resource/tenant | Xóa nhầm tài liệu người khác | Authorization theo ID và tenant |
| Dùng body DELETE cho batch không có hợp đồng | Tương thích proxy kém | POST tạo bulk-deletion job |
| Không kiểm thử timeout/retry | Side effect bị lặp | Test lỗi mạng và worker idempotency |
| Ghi nội dung nhạy cảm vào audit | Rò rỉ dữ liệu qua log | Log metadata tối thiểu và giới hạn quyền xem |

## 18. Bài thực hành: thiết kế DELETE cho kho tài liệu

**Bối cảnh:** một SaaS có tenant A và B. Mỗi tài liệu chứa id, tenant_id, version, status, file_key. Tài liệu có thể là **draft**, **published**, **locked** hoặc **deleted**. File lưu trong object storage, search index được worker đồng bộ. Hệ thống cần:

- Mỗi tenant chỉ được xóa tài liệu của mình.
- Tài liệu locked không thể xóa.
- Client được cảnh báo nếu tài liệu bị sửa sau lần đọc trước.
- URI không còn trả nội dung hoạt động sau khi xóa được xác nhận thành công.
- File được dọn theo chính sách nhưng có thể hoàn thành về sau.
- Retry timeout không được xóa nhầm phiên bản hoặc sinh tác dụng bất hợp lý.

**Nhiệm vụ:**

1. Chọn URI, method và ý nghĩa của resource bị xóa.
2. Thiết kế status code cho draft v7 được xóa, locked, client gửi ETag v7 nhưng hiện tại v8, và tài liệu đã mất.
3. Vẽ sơ đồ API → authorization → DB/outbox → worker → object storage/search.
4. Chọn soft/hard delete; giải thích quyền chia sẻ, cache, bình luận và retention.
5. Viết ít nhất sáu test: ETag cũ, xóa chéo tenant, retry sau timeout, worker xử lý lặp, cache sau DELETE và race update/delete.
6. Nêu ba metrics để quan sát: số job lỗi, độ trễ cleanup và độ trễ invalidation.

### 18.1. Hướng giải tham khảo

Một phương án là **DELETE /api/v1/documents/{id}** với **If-Match bắt buộc**, phân quyền theo (tenant_id, document_id), kiểm tra locked, thực hiện **UPDATE có điều kiện version** đặt deleted_at. Trong cùng giao dịch, ghi **outbox event** có operation ID, tenant, document ID và generation.

| Tình huống | Mã phản hồi ví dụ | Trạng thái cuối |
| --- | --- | --- |
| Draft v7, quyền và ETag đúng | 204 | Deleted |
| Tài liệu locked | 409 | Không đổi |
| Client v7 nhưng hiện tại v8 | 412 | Không đổi |
| Gửi lại DELETE khi đã deleted | 404 | Vẫn deleted |
| User A xóa tài liệu B | 404 theo chính sách che giấu | Dữ liệu B không đổi |

Worker xử lý outbox theo event ID/generation để chạy lại an toàn. API phải ngăn GET thông thường trả tài liệu sau khi deleted_at được commit, đồng thời invalidation cache và search index theo cơ chế đã cam kết.

Theo hợp đồng mẫu, **204 chỉ xác nhận tài liệu đã được gỡ khỏi API tại commit**, không ngụ ý file đã bị purge. Nếu yêu cầu nghiệp vụ muốn xóa vật lý hoàn tất trước khi xác nhận, thiết kế luồng và mã phản hồi phải thay đổi.

## 19. Checklist hoàn thành

- [ ] Tôi phân biệt gỡ liên kết URI và xóa vật lý dữ liệu.
- [ ] Tôi chọn đúng resource để DELETE, kể cả quan hệ thành viên.
- [ ] Tôi biết DELETE idempotent nhưng không safe.
- [ ] Tôi giải thích được retry có thể nhận 404 sau 204.
- [ ] Tôi chọn 200/202/204 theo trạng thái hoàn tất và response content.
- [ ] Tôi không gửi JSON body cùng 204.
- [ ] Tôi phân biệt 409, 412 và 428.
- [ ] Tôi biết dùng ETag/If-Match và cập nhật nguyên tử để tránh race.
- [ ] Tôi không dựa vào request body DELETE cho thao tác xóa hàng loạt mặc định.
- [ ] Tôi kiểm soát xác thực, phân quyền resource/tenant và audit.
- [ ] Tôi xử lý cache, file, search, retention và job bất đồng bộ.
- [ ] Tôi có hợp đồng OpenAPI và test lỗi mạng, retry, worker lặp.

**Ghi nhớ:** DELETE yêu cầu origin server loại bỏ **sự liên kết của tài nguyên đích với chức năng hiện tại tại URI đó**. Xóa mềm, purge vật lý, lưu giữ backup và dọn dẹp hệ thống phụ là quyết định của hợp đồng API và kiến trúc thực thi. Người thiết kế cần chứng minh hành vi bằng mã HTTP, điều kiện, quyền truy cập và kiểm thử.

### Tiêu chuẩn để tra cứu

- **RFC 9110 – HTTP Semantics:** DELETE (9.3.5), thuộc tính phương thức, status code, ETag, If-Match.
- **RFC 9111 – HTTP Caching:** vô hiệu hóa cache khi có request thay đổi trạng thái.
- **RFC 9457 – Problem Details for HTTP APIs:** cấu trúc application/problem+json.
- **OpenAPI Specification 3.1:** mô tả endpoint, header, response và security.
