# If-Match để ngăn ghi đè trạng thái đã thay đổi

## 1. Mục tiêu và bối cảnh

Trong module **INTEGRATION_API_REST**, người học thiết kế REST API theo tài nguyên, URI, phương thức HTTP, mã trạng thái, hợp đồng dữ liệu rõ ràng; đồng thời thực hành cache, idempotency, phân quyền, OpenAPI và kiểm thử với Java/Spring hoặc công nghệ tương đương. Chương **Điều kiện và đồng thời** tập trung vào tình huống nhiều client cùng đọc rồi chỉnh sửa một resource.

**If-Match** là một **HTTP conditional request header**. Nó yêu cầu server chỉ thực hiện phương thức được gửi khi biểu diễn hiện tại của tài nguyên đích thỏa điều kiện entity tag (ETag) mà client cung cấp. Trong trường hợp phổ biến nhất, client đưa **strong ETag** vừa nhận từ GET vào If-Match khi PUT, PATCH hoặc DELETE để tránh sửa/xóa một phiên bản đã bị người khác thay đổi.

Sau bài học, bạn sẽ có thể:

- Mô tả **lost update** và lý do đọc rồi ghi không có điều kiện gây mất thay đổi.
- Hiểu ETag là validator của **biểu diễn tài nguyên**, không phải mật khẩu hay quyền truy cập.
- Dùng đúng **If-Match**, strong comparison, danh sách entity tag và giá trị đặc biệt **\***.
- Chọn mã **412 Precondition Failed**, **428 Precondition Required**, **409 Conflict** và các mã 2xx phù hợp.
- Phối hợp kiểm tra HTTP precondition với **optimistic concurrency control** và thao tác nguyên tử trong CSDL.
- Tách vấn đề cạnh tranh phiên bản khỏi xác thực, phân quyền, idempotency và các xung đột nghiệp vụ.
- Viết API Java/Spring có ETag, xử lý If-Match, mô tả OpenAPI 3.1 và kiểm thử tình huống hai client cùng sửa.

**Tình huống xuyên suốt:** nhân viên Lan và Minh cùng chỉnh sửa bản nháp tài liệu trong một hệ thống quản lý hợp đồng. Lan mở bản v7. Minh lưu bản v8. Nếu Lan lưu lại toàn bộ nội dung cũ mà API không kiểm tra phiên bản, nội dung mới của Minh có thể bị ghi đè mà không được cảnh báo.

## 2. Lost update: lỗi xảy ra dù mỗi request đều hợp lệ

Hãy xem luồng chỉ dùng GET và PUT thông thường:

~~~mermaid
sequenceDiagram
    participant L as Lan (Client A)
    participant S as REST API
    participant DB as Database
    participant M as Minh (Client B)
    L->>S: GET /documents/d-101
    S->>DB: Read document
    DB-->>S: version 7, title A
    S-->>L: 200 body v7
    M->>S: GET /documents/d-101
    S-->>M: 200 body v7
    M->>S: PUT title B
    S->>DB: Ghi phiên bản 8
    S-->>M: 200 OK
    L->>S: PUT title C từ bản v7
    S->>DB: Ghi đè thành title C
    S-->>L: 200 OK
    Note over DB: Sửa đổi của Minh bị mất
~~~

Vấn đề không nằm ở việc client gửi JSON sai. Cả Lan và Minh có thể được xác thực, có quyền chỉnh sửa và gửi dữ liệu hợp lệ. Lỗi xuất hiện vì server không kiểm tra **Lan đang dựa vào trạng thái nào** khi yêu cầu thay đổi.

**Lost update** là tình huống một cập nhật muộn ghi đè một cập nhật trước đó mà client không nhận biết hoặc chấp nhận rõ ràng. Đây là vấn đề đặc biệt nguy hiểm khi:

- Dùng **PUT** thay thế cả biểu diễn tài nguyên.
- Dùng **PATCH** cập nhật những trường mà người khác cũng có thể chỉnh sửa.
- Dùng **DELETE** để xóa resource vừa được cập nhật hoặc thay đổi trạng thái.
- Nhiều dịch vụ, background job hoặc trình duyệt chạy song song.
- Một request bị timeout và client gửi lại khi trạng thái đã thay đổi.

Nếu client có thể gửi lại phiên bản đã đọc, server có thể phát hiện rằng **bản client đang dựa vào đã lỗi thời** thay vì âm thầm ghi đè.

## 3. ETag là gì và được phát hành ở đâu?

**ETag** là response header chứa một **entity tag** do server tạo để xác định phiên bản/biến thể của biểu diễn. Về mặt cú pháp HTTP, entity tag đặt trong dấu ngoặc kép:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "document-d101-v7"
Cache-Control: private, no-cache

{
  "id": "d-101",
  "title": "Hợp đồng dịch vụ",
  "status": "DRAFT",
  "version": 7
}
~~~

**ETag không nhất thiết bằng cột version trong DB.** Nó có thể dựa trên version nội bộ, hash của biểu diễn, generation ID hoặc cơ chế riêng của origin server. Vấn đề quan trọng là ETag phản ánh **đúng sự thay đổi có ý nghĩa đối với biểu diễn** mà nó xác định.

| Khái niệm | Dùng để làm gì? | Điều không được suy ra |
| --- | --- | --- |
| DB version | Hỗ trợ optimistic concurrency trong persistence | Không tự tạo ETag chuẩn HTTP |
| ETag | Validator cho biểu diễn HTTP | Không phải token xác thực |
| **If-Match** | Chỉ thực hiện yêu cầu nếu validator hiện tại thỏa điều kiện | Không tự bảo đảm phân quyền hay transaction nguyên tử |
| If-None-Match | Điều kiện dựa trên biểu diễn **không** khớp; phổ biến cho GET cache validation | Không thay thế If-Match khi muốn bảo vệ phiên bản cũ |
| Last-Modified | Thời điểm biến đổi gần nhất được công bố | Không phải lúc nào cũng đủ độ phân giải để tránh lost update |

### 3.1. Strong và weak ETag

Ví dụ hai dạng hợp lệ:

~~~http
ETag: "document-d101-v7"
ETag: W/"document-d101-v7"
~~~

- **Strong ETag** không có tiền tố W/. Nó phù hợp cho **strong comparison**, dùng trong If-Match.
- **Weak ETag** có tiền tố W/. Nó cho phép đánh giá tương đương biểu diễn yếu hơn, hữu ích với revalidation bằng If-None-Match trong những trường hợp phù hợp.
- If-Match áp dụng **strong comparison**; hai giá trị giống nhau về chuỗi nhưng một bên có W/ **không khớp theo strong comparison**.

Đừng bỏ tiền tố W/ hoặc dấu ngoặc kép để so bằng chuỗi “v7” tùy tiện. Server cần phân tích đúng cú pháp HTTP entity tag hoặc dùng thư viện hỗ trợ.

### 3.2. ETag gắn với representation, không chỉ bản ghi

Giả sử một tài liệu có hai representation:

~~~http
GET /documents/d-101
Accept: application/json
~~~

~~~http
GET /documents/d-101
Accept-Language: vi
~~~

Nếu body khác nhau theo media type/ngôn ngữ/encoding hoặc projection, chính sách ETag và **Vary** phải tương thích với các biến thể. Một DB version có thể là tín hiệu tốt, nhưng không được trả cùng một **strong ETag** cho hai representation có bytes khác nhau nếu chúng không đáp ứng điều kiện strong validator.

Đối với API cập nhật bằng PUT, server cần chọn rõ **ETag của biểu diễn đích nào**. Client không được lấy ETag của collection, của một projection khác hoặc của user khác rồi coi đó là validator đương nhiên cho resource đang cập nhật.

## 4. Giao thức GET → If-Match → PUT

Luồng chuẩn cho API chỉnh sửa một tài liệu:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant D as Database
    C->>A: GET /documents/d-101
    A->>D: Đọc bản hiện tại
    D-->>A: version 7
    A-->>C: 200 OK + ETag "document-d101-v7"
    Note over C: Người dùng chỉnh sửa trên v7
    C->>A: PUT /documents/d-101 + If-Match v7
    A->>A: Xác thực + quyền + điều kiện
    A->>D: UPDATE ... WHERE version = 7
    D-->>A: affected = 1; version 8
    A-->>C: 200 OK + ETag "document-d101-v8"
~~~

### 4.1. Đọc trạng thái

~~~http
GET /api/v1/documents/d-101 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "document-d101-v7"
Cache-Control: private, no-cache

{
  "id": "d-101",
  "title": "Hợp đồng dịch vụ",
  "status": "DRAFT",
  "version": 7
}
~~~

### 4.2. Gửi cập nhật có điều kiện

~~~http
PUT /api/v1/documents/d-101 HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>
If-Match: "document-d101-v7"

{
  "title": "Hợp đồng dịch vụ – bản rà soát",
  "status": "DRAFT"
}
~~~

Giá trị If-Match là **ETag của resource đích mà client đã nhận**, không phải header do client tự sáng tạo một version tùy ý.

### 4.3. Khi điều kiện khớp

Sau khi xác thực quyền và kiểm tra điều kiện, server ghi thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "document-d101-v8"
Cache-Control: private, no-store

{
  "id": "d-101",
  "title": "Hợp đồng dịch vụ – bản rà soát",
  "status": "DRAFT",
  "version": 8
}
~~~

**200** phù hợp khi server trả biểu diễn đã cập nhật. **204 No Content** cũng có thể phù hợp nếu cập nhật thành công và API không trả content. Khi dùng PUT, quy tắc HTTP có giới hạn đối với việc gửi validator trong response nếu biểu diễn đã được biến đổi trước lúc lưu; thiết kế ví dụ cần bảo đảm ETag thực sự gắn với representation hiện tại mà server đã lưu. Không tự khẳng định đã có ETag mới nếu không xác định được biểu diễn tương ứng.

## 5. Khi bản ghi đã thay đổi: 412 Precondition Failed

Giả sử Minh đã ghi version 8 trước khi Lan gửi PUT với If-Match version 7.

~~~mermaid
sequenceDiagram
    participant L as Lan
    participant S as API
    participant M as Minh
    L->>S: GET document
    S-->>L: ETag "v7"
    M->>S: PUT + If-Match "v7"
    S-->>M: 200, ETag "v8"
    L->>S: PUT + If-Match "v7"
    S->>S: Strong ETag v7 không khớp v8
    S-->>L: 412 Precondition Failed
    Note over L: Giữ thay đổi local, đọc lại và giải quyết xung đột
~~~

Một phản hồi lỗi có cấu trúc **Problem Details (RFC 9457)**:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-Id: req-7f2a

{
  "type": "https://api.example.test/problems/stale-resource",
  "title": "Resource changed",
  "status": 412,
  "detail": "Tài liệu đã được thay đổi kể từ lần đọc trước. Hãy tải phiên bản mới trước khi lưu.",
  "instance": "/api/v1/documents/d-101",
  "code": "ETAG_MISMATCH",
  "traceId": "req-7f2a"
}
~~~

Client nên:

1. **Không** gửi lại y nguyên PUT có If-Match cũ theo vòng lặp vô hạn.
2. Giữ bản chỉnh sửa cục bộ để người dùng không mất công.
3. GET lại tài nguyên và ETag mới nếu vẫn có quyền.
4. Hiển thị khác biệt hoặc áp dụng cơ chế merge theo nghiệp vụ.
5. Khi người dùng xác nhận, tạo một request mới với **ETag của trạng thái mới**.

**412 là một kết quả bảo vệ dữ liệu**, không nhất thiết là lỗi dịch vụ. Nếu theo dõi metric, tỷ lệ 412 tăng có thể cho thấy tranh chấp khi nhiều người chỉnh sửa hoặc UI không cập nhật đủ thường xuyên.

## 6. Nếu API yêu cầu điều kiện mà client không gửi: 428

Một API có thể quyết định: **mọi PUT/PATCH/DELETE sửa tài liệu đều phải có If-Match**. Nếu request thiếu header, dùng **428 Precondition Required** để nói rằng request phải được gửi có điều kiện.

~~~http
PUT /api/v1/documents/d-101 HTTP/1.1
Content-Type: application/json

{"title":"Bản mới"}
~~~

~~~http
HTTP/1.1 428 Precondition Required
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/precondition-required",
  "title": "Precondition required",
  "status": 428,
  "detail": "Hãy GET tài liệu rồi gửi lại If-Match với ETag hiện tại.",
  "code": "IF_MATCH_REQUIRED"
}
~~~

**Phân biệt:**

| Trường hợp | Mã hợp lý | Nguyên nhân |
| --- | --- | --- |
| Thiếu If-Match theo chính sách bắt buộc | **428** | Chưa cung cấp precondition |
| Có If-Match nhưng không khớp | **412** | Precondition được đánh giá là false |
| Tài liệu bị khóa dù ETag khớp | **409** | Xung đột nghiệp vụ |
| Không xác thực | **401** | Không có credential hợp lệ |
| Không đủ quyền | **403** hoặc 404 theo chính sách | Authorization thất bại |
| Resource không hiện diện/không được phép nhìn thấy | **404** trong tình huống tương ứng | Không có representation được phép |

**428 không bắt buộc với mọi REST API**. Server có thể cho phép cập nhật không điều kiện khi mô hình nghiệp vụ cho phép; khi đó cần công bố rủi ro. Nhưng một API muốn thực sự chống lost update nên thiết lập chính sách rõ thay vì hy vọng client nhớ tự gửi If-Match.

Theo RFC 6585, response **428 không được lưu bởi cache**.

## 7. If-Match chi tiết: danh sách tag, wildcard và thứ tự đánh giá

Cú pháp khái niệm:

~~~http
If-Match: "v7"
If-Match: "v6", "v7"
If-Match: *
~~~

### 7.1. Một strong entity tag

~~~http
If-Match: "document-d101-v7"
~~~

Điều kiện thành công nếu origin xác định representation hiện tại có strong ETag tương ứng với tag được gửi. Với resource đã đổi ETag, điều kiện thất bại.

### 7.2. Nhiều entity tag

~~~http
If-Match: "document-d101-v6", "document-d101-v7"
~~~

Theo ngữ nghĩa If-Match, phép so sánh thỏa nếu **bất kỳ** tag nào trong danh sách khớp mạnh với validator hiện tại. Đây là điều kiện OR trên các entity tag, không phải yêu cầu cả hai phải khớp.

Nếu API tutorial chỉ triển khai **một tag**, phải nói rõ đây là giới hạn ví dụ; không nên trình bày việc so chuỗi thủ công với một tag như một HTTP parser đầy đủ.

### 7.3. If-Match: *

~~~http
If-Match: *
~~~

Giá trị **\*** yêu cầu origin có **biểu diễn hiện tại** của tài nguyên đích. Nó **không chứng minh** client đã đọc phiên bản đang hiện hữu. Vì vậy:

- Có thể hữu ích cho thao tác có điều kiện **resource phải tồn tại**.
- **Không phù hợp để chống lost update** nếu mục tiêu là “chỉ ghi khi dữ liệu chưa đổi kể từ lần đọc”.
- Khi áp dụng chính sách cần **ETag cụ thể**, API nên công bố rằng wildcard không đáp ứng yêu cầu bảo vệ phiên bản, thay vì bí mật coi **\*** như một ETag version.

### 7.4. Weak tag không thỏa If-Match

~~~http
If-Match: W/"document-d101-v7"
~~~

If-Match dùng **strong comparison**, nên weak tag không khớp dù phần opaque tag tương tự. Không bỏ tiền tố W/ để biến weak tag thành strong.

### 7.5. Đánh giá precondition ở đúng thời điểm

Theo ngữ nghĩa HTTP, precondition được xem xét trong ngữ cảnh server sẽ phản hồi như thế nào khi **không có điều kiện**. Xác thực, phân quyền, tính hợp lệ cơ bản và trạng thái resource vẫn có vai trò; không buộc mọi request thất bại authentication phải trả 412 chỉ vì If-Match sai.

Khi có nhiều conditional headers, HTTP có thứ tự đánh giá preconditions. Ví dụ If-Match được ưu tiên so với If-Unmodified-Since theo các điều kiện áp dụng. Trong ứng dụng, tránh tự viết một thứ tự tùy tiện hoặc ghép các điều kiện không đúng semantics.

## 8. If-Match và If-None-Match: cùng ETag, mục tiêu khác

Hai header dễ bị nhầm vì cùng nói tới ETag:

| Header | Phép so sánh | Mục tiêu phổ biến | Phản hồi khi không thỏa |
| --- | --- | --- | --- |
| **If-Match** | Strong comparison | Chống ghi đè khi PUT/PATCH/DELETE | **412** trong trường hợp thông thường |
| **If-None-Match** | Weak comparison | GET cache validation, tránh tải body không đổi | **304** với GET/HEAD khi điều kiện false |
| **If-None-Match: \*** | Điều kiện không có representation hiện tại | Create-if-absent cho PUT | **412** nếu resource đã có |
| **If-Unmodified-Since** | Dựa trên thời điểm sửa | Tránh thay đổi kể từ thời điểm đã biết | **412**, nhưng kém chính xác hơn ETag |
| **If-Modified-Since** | Dựa trên thời điểm sửa | GET revalidation | Có thể **304** với GET/HEAD |

**Ví dụ tạo resource chỉ khi chưa tồn tại:**

~~~http
PUT /api/v1/documents/d-new HTTP/1.1
If-None-Match: *
Content-Type: application/json

{"title":"Tài liệu mới"}
~~~

Nếu URI chưa có representation hiện tại và các điều kiện khác thỏa, server có thể tạo resource. Nếu URI đã có representation, precondition thất bại, thường trả **412**. Đây không phải phép thay thế cho If-Match khi cập nhật một version đã đọc.

**304 Not Modified** chủ yếu liên quan conditional GET/HEAD để tiết kiệm truyền tải. Một PUT có If-Match cũ **không nên trả 304**; thông thường đó là **412**.

## 9. PUT, PATCH, DELETE và POST có thể dùng If-Match như thế nào?

### 9.1. PUT thay thế representation

~~~http
PUT /api/v1/documents/d-101
If-Match: "v7"
Content-Type: application/json

{"title":"Bản rà soát","status":"DRAFT"}
~~~

PUT có ngữ nghĩa tạo/thay thế trạng thái tài nguyên đích bằng biểu diễn gửi lên. Nếu server cho phép cập nhật, If-Match giúp chống việc một bản chỉnh sửa cũ thay thế bản mới.

### 9.2. PATCH thay đổi một phần

~~~http
PATCH /api/v1/documents/d-101
If-Match: "v7"
Content-Type: application/merge-patch+json

{"title":"Bản rà soát"}
~~~

PATCH không mặc định idempotent và định dạng patch có ngữ nghĩa riêng. Dù chỉ sửa một trường, client vẫn có thể cần If-Match nếu quy tắc nghiệp vụ yêu cầu cập nhật trên một phiên bản nhất định, nhất là khi patch phụ thuộc trạng thái hiện tại.

**Lưu ý:** trường không trùng nhau có thể cập nhật song song trong một số mô hình nghiệp vụ, nhưng tự động merge cần được thiết kế và kiểm thử; không dùng PATCH làm lý do bỏ qua concurrency control.

### 9.3. DELETE tránh xóa bản mới

~~~http
DELETE /api/v1/documents/d-101
If-Match: "v7"
~~~

Nếu người khác vừa sửa tài liệu thành v8, server có thể từ chối bằng **412**, tránh xóa một tài liệu mới mà client chưa xem. Xóa mềm cũng cần điều kiện version nguyên tử và ràng buộc quyền.

### 9.4. POST trên resource có thể cần precondition

If-Match là điều kiện HTTP áp vào **tài nguyên đích của request**, không bị giới hạn tuyệt đối ở PUT. Nếu POST tác động một resource có representation cần kiểm tra, server có thể hỗ trợ If-Match theo hợp đồng.

Tuy nhiên, với POST tạo resource con mới, **target URI** có thể là collection, không phải bản ghi con. Đặt If-Match vào collection chỉ có ý nghĩa nếu API định nghĩa rõ ETag của collection có liên quan tới operation; không được tự động hiểu nó là version của một resource con.

## 10. Optimistic concurrency: kiểm tra HTTP chưa đủ nếu DB không nguyên tử

**Đây là điểm trọng tâm khi chuyển từ hợp đồng API sang triển khai.** Nếu application xử lý như sau:

~~~text
1. SELECT version FROM documents WHERE id = X  -> 7
2. So với If-Match "v7"                         -> khớp
3. Một request khác UPDATE thành version 8
4. UPDATE documents SET title = ..., version=9 WHERE id=X
~~~

Nếu bước 4 không có điều kiện version, thay đổi của request kia vẫn có thể bị ghi đè. If-Match ở tầng controller chỉ giảm rủi ro, **không đảm bảo loại bỏ race**.

### 10.1. Mẫu SQL cập nhật có điều kiện

~~~sql
UPDATE documents
SET title = :new_title,
    status = :new_status,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :document_id
  AND tenant_id = :verified_tenant_id
  AND version = :expected_version
  AND deleted_at IS NULL;
~~~

Trong đây:

- **:document_id** là ID từ path, đã parse/validate.
- **:verified_tenant_id** do server xác nhận qua authentication/membership.
- **:expected_version** là version mà server đã ánh xạ từ validator được phép dùng.
- **version = version + 1** thực hiện cùng câu UPDATE.
- **deleted_at IS NULL** ngăn cập nhật tài liệu đã xóa mềm.

Nếu **affected rows = 1**, một bản ghi thỏa điều kiện đã được cập nhật. Nếu **affected rows = 0**, ứng dụng phải kiểm tra nguyên nhân theo chính sách: resource mất/ẩn, ETag cũ, bị xóa hay trạng thái nghiệp vụ không còn cho phép.

**Không luôn trả 412 cho mọi affected=0** mà không phân biệt 404/403/409 và trường hợp concurrency. Tuy nhiên, nếu trước đó đã xác minh resource tồn tại và có quyền, thay đổi version giữa hai bước thường dẫn tới 412.

### 10.2. Cơ chế của DB bảo vệ phép cập nhật thế nào?

Với CSDL quan hệ hỗ trợ cập nhật có điều kiện và giao dịch thích hợp, câu UPDATE sẽ kiểm tra điều kiện trên bản ghi phù hợp khi nó được thực thi, không phải dựa vào kết quả SELECT cũ mà ứng dụng giữ trong bộ nhớ. Hai request cùng kỳ vọng version 7 không thể đều cập nhật tuần tự thành công trên bản ghi có version tăng theo đúng câu UPDATE.

Ví dụ hai request đồng thời:

| Thời điểm | Request A | Request B | Version trong DB |
| --- | --- | --- | --- |
| T0 | Đọc v7 | Đọc v7 | 7 |
| T1 | UPDATE WHERE version=7 → 1 row | Chờ/đua tranh | 8 |
| T2 | Commit | UPDATE WHERE version=7 → 0 row | 8 |
| T3 | 200/204 | 412 sau khi xác định conflict | 8 |

Kết quả chi tiết phụ thuộc transaction isolation, lock và DB engine, nhưng **mục tiêu bất biến** là chỉ một cập nhật dựa trên cùng version cũ được commit trong trường hợp thay đổi đó tăng version đúng cách.

### 10.3. Dùng @Version với JPA

JPA cung cấp **optimistic locking** qua **@Version**. Ví dụ entity có:

~~~java
@Entity
public class Document {
    @Id
    private UUID id;

    private UUID tenantId;
    private String title;
    private String status;

    @Version
    private long version;

    // Constructors, getters, setters...
}
~~~

Khi entity được quản lý và cập nhật bằng JPA, provider có thể kiểm tra version khi flush/commit và ném lỗi optimistic locking nếu có thay đổi đồng thời.

**Cần hiểu:** @Version bảo vệ **giao dịch của persistence**, còn If-Match bảo vệ **ý định mà client gửi qua HTTP**. Hai cơ chế bổ sung cho nhau. Nếu ứng dụng bỏ If-Match, một request vẫn có thể GET một phiên bản rất cũ, rồi server đọc phiên bản mới và ghi theo @Version mà không nhận biết client đang dựa vào dữ liệu cũ.

Ngoài ra, JPQL bulk UPDATE có thể bỏ qua cơ chế version tự động; nếu dùng bulk update, phải ràng buộc và tăng version rõ ràng, rồi đồng bộ persistence context cho đúng.

## 11. Thiết kế ETag cho resource và vòng đời phiên bản

Một validator tốt cần đáp ứng:

1. **Server kiểm soát** nguồn tạo ETag và tính nhất quán.
2. Thay đổi được khi representation có ý nghĩa đối với conditional write thay đổi.
3. Không trộn ETag giữa các resource, tenant hoặc các biến thể không tương thích.
4. Có thể tái tạo sau restart mà không phải tạo ngẫu nhiên mỗi lần đọc.
5. Không tiết lộ dữ liệu nhạy cảm qua một validator dễ đoán nếu threat model yêu cầu che giấu.
6. Không cho client dùng ETag để bỏ qua authorization.

Có hai hướng phổ biến:

**Version-based ETag:**

~~~text
"document-d101-v7"
"document-d101-v8"
~~~

Ưu điểm: đơn giản, gắn với cột version DB; dễ dùng optimistic concurrency. Rủi ro: mọi thay đổi representation phải cập nhật version đúng cách. Nếu một dịch vụ khác sửa dữ liệu mà không tăng version, client có thể nhận ETag cũ không còn đại diện trạng thái mới.

**Content hash ETag:**

~~~text
"sha256-digest-of-representation"
~~~

Ưu điểm: phản ánh representation thực tế nếu hash được tính đúng. Rủi ro: cần thống nhất serialization, encoding, projection, chi phí tính hash và chiến lược mapping validator sang điều kiện ghi nguyên tử.

**Chọn một chuẩn cho từng tài nguyên**, tài liệu hóa và kiểm tra trong hệ đa instance. Không sinh ETag dựa trên timestamp JVM hiện tại ở mỗi GET; điều đó sẽ khiến biểu diễn không đổi cũng có ETag mới, làm revalidation và concurrency kém hiệu quả.

## 12. Java/Spring Boot: minh họa API có If-Match

Ví dụ tập trung vào **GET biểu diễn tài liệu và PUT thay thế trạng thái có điều kiện**. Mô hình giả định dùng Java 17+, Spring Boot 3/Spring Web và **NamedParameterJdbcTemplate** để làm rõ UPDATE nguyên tử. Các lớp xác thực, connection, DTO mapping và error handler được rút gọn cho mục tiêu học tập.

### 12.1. DTO và ngữ cảnh quyền

~~~java
public record DocumentView(
        UUID id,
        String title,
        String status,
        long version) {}

public record ReplaceDocumentRequest(
        @NotBlank String title,
        @NotBlank String status) {}

public record AuthorizedScope(
        UUID tenantId,
        UUID userId) {}

public interface DocumentAuthorization {
    // Lấy từ authenticated principal và policy đã xác minh.
    AuthorizedScope requireDocumentWriteScope(UUID documentId);

    AuthorizedScope requireDocumentReadScope(UUID documentId);
}
~~~

**Không** nhận tenantId do client gửi và dùng trực tiếp như quyền. Trong SaaS, tenant và quyền đối với documentId phải được kiểm tra theo principal/role/ACL.

### 12.2. GET trả biểu diễn cùng strong ETag

~~~java
@RestController
@RequestMapping("/api/v1/documents")
public class DocumentController {

    private final DocumentService service;
    private final DocumentAuthorization authorization;

    public DocumentController(
            DocumentService service,
            DocumentAuthorization authorization) {
        this.service = service;
        this.authorization = authorization;
    }

    @GetMapping("/{id}")
    public ResponseEntity<DocumentView> get(@PathVariable UUID id) {
        AuthorizedScope scope = authorization.requireDocumentReadScope(id);
        DocumentView view = service.get(scope.tenantId(), id);

        return ResponseEntity.ok()
                .eTag(etag(id, view.version()))
                .header(HttpHeaders.CACHE_CONTROL, "private, no-cache")
                .body(view);
    }

    private static String etag(UUID id, long version) {
        return "\"document-" + id + "-v" + version + "\"";
    }
}
~~~

**Lưu ý:** ví dụ trả strong ETag dựa trên version/ID, hợp lệ về mặt ý tưởng nếu **mọi thay đổi của biểu diễn được version hóa** và có một biểu diễn JSON thống nhất. Nếu serialization khác theo ngôn ngữ, encoding hoặc quyền, cách đặt ETag phải được điều chỉnh cho đúng representation.

### 12.3. PUT bắt buộc If-Match

Có thể bổ sung phương thức này vào cùng controller:

~~~java
@PutMapping("/{id}")
public ResponseEntity<DocumentView> replace(
        @PathVariable UUID id,
        @Valid @RequestBody ReplaceDocumentRequest body,
        @RequestHeader(value = "If-Match", required = false) String ifMatch) {

    AuthorizedScope scope = authorization.requireDocumentWriteScope(id);

    if (ifMatch == null || ifMatch.isBlank()) {
        throw new ResponseStatusException(
                HttpStatus.PRECONDITION_REQUIRED,
                "If-Match is required");
    }

    DocumentView changed = service.replaceIfMatches(
            scope.tenantId(), id, body, ifMatch);

    return ResponseEntity.ok()
            .eTag(etag(id, changed.version()))
            .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
            .body(changed);
}
~~~

Phương thức **etag** được định nghĩa ở GET ví dụ, không phải một method mới cần sao chép nhiều lần. DTO **ReplaceDocumentRequest** không chứa version do client tự chỉnh mà dựa trên If-Match đã nhận trước đó.

**Cảnh báo về ví dụ:** trình xử lý bên dưới sử dụng một strong tag cụ thể theo format do ứng dụng phát hành. HTTP cho phép danh sách entity tag và wildcard; bản production muốn hỗ trợ đầy đủ phải dùng parser và đánh giá semantics phù hợp, không chỉ so một chuỗi.

### 12.4. Service phối hợp HTTP validator và UPDATE nguyên tử

~~~java
@Service
public class DocumentService {

    private final DocumentDao dao;

    public DocumentService(DocumentDao dao) {
        this.dao = dao;
    }

    @Transactional(readOnly = true)
    public DocumentView get(UUID tenantId, UUID id) {
        return dao.findActive(tenantId, id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));
    }

    @Transactional
    public DocumentView replaceIfMatches(
            UUID tenantId,
            UUID id,
            ReplaceDocumentRequest request,
            String ifMatch) {

        DocumentView current = dao.findActive(tenantId, id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Document not found"));

        String expectedTag =
                "\"document-" + id + "-v" + current.version() + "\"";

        // Chỉ xử lý một strong entity tag đúng định dạng trong ví dụ.
        if (!expectedTag.equals(ifMatch)) {
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "The resource has changed");
        }

        // Kiểm tra nghiệp vụ, ví dụ trạng thái LOCKED không thể sửa.
        if ("LOCKED".equals(current.status())) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, "Document is locked");
        }

        int affected = dao.updateIfVersionMatches(
                tenantId, id, current.version(),
                request.title(), request.status());

        if (affected != 1) {
            // Một request khác có thể đã sửa/xóa sau khi đọc.
            throw new ResponseStatusException(
                    HttpStatus.PRECONDITION_FAILED,
                    "The resource changed during update");
        }

        return dao.findActive(tenantId, id)
                .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Could not load updated resource"));
    }
}
~~~

Ví dụ đảm bảo **If-Match được kiểm tra ở server** và thao tác cuối có **version predicate**, nhằm chống race giữa bước đọc và ghi.

### 12.5. Data access có điều kiện

~~~java
@Repository
public class DocumentDao {
    private final NamedParameterJdbcTemplate jdbc;

    public DocumentDao(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<DocumentView> findActive(UUID tenantId, UUID id) {
        String sql = """
                SELECT id, title, status, version
                FROM documents
                WHERE tenant_id = :tenantId
                  AND id = :id
                  AND deleted_at IS NULL
                """;

        var params = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("id", id);

        List<DocumentView> list = jdbc.query(
                sql, params, (rs, rowNum) -> new DocumentView(
                        rs.getObject("id", UUID.class),
                        rs.getString("title"),
                        rs.getString("status"),
                        rs.getLong("version")));

        return list.stream().findFirst();
    }

    public int updateIfVersionMatches(
            UUID tenantId, UUID id, long version,
            String title, String status) {

        String sql = """
                UPDATE documents
                SET title = :title,
                    status = :status,
                    version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = :tenantId
                  AND id = :id
                  AND version = :version
                  AND deleted_at IS NULL
                """;

        var params = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("id", id)
                .addValue("version", version)
                .addValue("title", title)
                .addValue("status", status);

        return jdbc.update(sql, params);
    }
}
~~~

Ví dụ dùng placeholder bind thay vì nối trực tiếp dữ liệu client vào SQL; điều kiện tenant và version được kiểm tra ngay tại CSDL.

**Giới hạn quan trọng trước khi chạy production:**

- Tên lớp Java, import, DB schema, error mapper và security configuration phải được hoàn thiện; các đoạn code là khối minh họa, không phải ứng dụng độc lập.
- Cần bảo đảm **DocumentAuthorization** kiểm tra chính xác quyền trên resource và tenant, đồng thời cân nhắc việc quyền bị thay đổi giữa kiểm tra và commit trong nghiệp vụ nhạy cảm.
- Các giá trị **status** phải được validate/allowlist theo nghiệp vụ; không để client tự đưa trạng thái bất hợp lệ.
- Nếu trạng thái **LOCKED** có thể đổi song song mà không tăng version, phần kiểm tra trước UPDATE chưa đủ. Mọi thay đổi trạng thái liên quan phải tăng version hoặc kiểm tra điều kiện status trong UPDATE.
- Nếu DB hỗ trợ nhiều biểu diễn, ETag cần phản ánh đúng representation mà client nhận.
- Việc service đọc lại sau UPDATE trong một transaction phù hợp với loại DB và isolation đã chọn; phải kiểm thử concurrency thực tế.
- Nếu response có ETag sau **PUT**, bảo đảm biểu diễn trả về phù hợp quy tắc validator của HTTP, không phát hành validator sai khi lưu có biến đổi representation.
- Các lỗi do transaction timeout hoặc DB outage cần được mapping riêng; không biến mọi lỗi hệ thống thành 412.

## 13. Phân quyền, bảo mật và cache với If-Match

If-Match **không phải authorization token**. Client biết ETag của tài liệu không có nghĩa được sửa tài liệu đó.

Các kiểm tra phải độc lập:

1. **Authentication:** caller có credential hợp lệ.
2. **Authorization:** caller được đọc/sửa/xóa tài nguyên đang nhắm tới, trong tenant phù hợp.
3. **Policy nghiệp vụ:** resource còn được phép thay đổi không?
4. **HTTP precondition:** If-Match có thỏa validator hiện tại?
5. **Atomic mutation:** DB update/delete thực sự ràng buộc version.
6. **Audit:** lưu ai sửa, resource nào, version cũ/mới, kết quả và request ID khi phù hợp.

Nếu user A có ETag của resource tenant B, A vẫn phải bị chặn. API có thể dùng 404 thay 403 để không tiết lộ sự tồn tại theo chính sách; cần tránh trả **412** với thông tin ETag mới của tài nguyên trái quyền.

### 13.1. Cache và ETag

ETag cũng phục vụ caching, nhưng mục tiêu khác:

- **If-None-Match** khi GET thường hỏi “body tôi có còn mới không?” để nhận **304** khi phù hợp.
- **If-Match** khi PUT/PATCH/DELETE hỏi “resource có còn đúng phiên bản tôi dựa vào không?” để quyết định có thể ghi.

Đối với tài liệu riêng, dùng chính sách cache phù hợp như **private, no-cache** khi chấp nhận private cache giữ body nhưng muốn revalidate trước reuse, hoặc **no-store** khi không muốn HTTP cache lưu. Không để CDN hoặc shared cache tái sử dụng body/ETag của một tenant sang tenant khác.

### 13.2. ETag không được làm lộ dữ liệu

- Không dùng ETag như một bí mật để cấp quyền.
- Không đặt token, API key hoặc email của người dùng vào ETag.
- Không đưa raw payload nhạy cảm vào ETag.
- Nếu response lỗi không được tiết lộ resource, không đưa ETag hiện tại/chi tiết phiên bản vào lỗi một cách vô điều kiện.
- Ghi log validator nếu cần truy vết nhưng không biến toàn bộ URL hoặc request body chứa PII thành metric label.

## 14. Idempotency, retry và lần PUT thứ hai

PUT là phương thức **idempotent theo ngữ nghĩa HTTP**, nhưng điều đó không có nghĩa phản hồi của hai lần gọi giống nhau khi dùng If-Match.

Giả sử client gửi:

~~~http
PUT /documents/d-101
If-Match: "v7"
Content-Type: application/json

{"title":"Bản mới"}
~~~

Lần đầu update v7 → v8 thành công, nhưng response mất do lỗi mạng. Client retry **cùng If-Match v7**; server thấy resource hiện tại là v8, nên có thể trả **412**.

Tình huống này **không chứng minh lần đầu thất bại**, cũng không làm PUT mất idempotency về tác dụng yêu cầu trong cách hiểu thông thường. Nếu tác dụng mong muốn đã được thực hiện, server không nhất thiết thực hiện nó lần hai.

### 14.1. Server có được trả 2xx khi điều kiện false?

RFC 9110 cho phép một ngoại lệ hẹp: origin có thể trả 2xx nếu xác minh được **thay đổi trạng thái mà client yêu cầu đã được phản ánh** trong trạng thái hiện tại. Điều này hỗ trợ một số trường hợp retry sau khi response trước bị mất. Tuy vậy, việc xác định trùng tác vụ phải đáng tin; không được chỉ so body rồi cho rằng mọi kết quả hiện tại đều do request trước tạo ra.

Khi không thể xác minh an toàn, trả **412** là hướng mặc định.

Nếu cần bảo đảm client phân biệt được kết quả retry:

- Dùng **request/operation ID** và lưu kết quả trong tầng ứng dụng, khi hợp đồng hỗ trợ.
- Với POST hoặc workflow có side effect, dùng **Idempotency-Key** được server triển khai và lưu trạng thái đủ lâu.
- Cho client GET lại tài nguyên và đối chiếu dữ liệu hiện tại.
- Tách thao tác “ghi phiên bản mới” khỏi tác vụ gửi email, thanh toán hoặc publish event có thể bị lặp.

**If-Match bảo vệ không ghi đè phiên bản cũ; Idempotency-Key giải quyết việc nhận dạng một ý định lặp lại.** Hai cơ chế không thay thế nhau.

## 15. Quyết định của client khi gặp 412

Một UI chỉnh sửa có thể áp dụng:

~~~mermaid
flowchart TD
    A[GET resource + ETag] --> B[Người dùng chỉnh sửa]
    B --> C[PUT/PATCH + If-Match]
    C --> D{HTTP status?}
    D -- 2xx --> E[Lưu thành công, cập nhật ETag/UI]
    D -- 412 --> F[Giữ local changes, GET lại resource]
    F --> G[Hiển thị thay đổi khác nhau]
    G --> H{Người dùng chọn?}
    H -- Merge/Apply lại --> I[Tạo request mới với ETag mới]
    I --> C
    H -- Hủy --> J[Giữ hoặc bỏ local draft theo lựa chọn]
    D -- 428 --> K[Đọc hướng dẫn, lấy ETag trước khi ghi]
    D -- 401/403/404 --> L[Giải quyết xác thực/quyền/tồn tại]
    D -- 409 --> M[Giải quyết xung đột nghiệp vụ]
~~~

**Không nên tự động overwrite** khi thấy 412. Với dữ liệu dễ ghép (ví dụ mỗi user sửa một trường độc lập), ứng dụng có thể hỗ trợ merge, nhưng cần kiểm tra conflict thực tế và chính sách nghiệp vụ. Với dữ liệu quan trọng như hợp đồng đã ký hoặc số dư, cần quy trình chấp thuận hoặc thao tác domain riêng thay vì tự ghép.

### 15.1. Xử lý mất kết nối và bản nháp cục bộ

Một UI tốt lưu bản chỉnh sửa trong client state khi request thất bại. Nếu cần lưu dài hạn, áp dụng cơ chế an toàn với dữ liệu nhạy cảm. Khi nhận 412, hiển thị các thay đổi mới từ server và phần client đang chuẩn bị ghi; đừng reset form về bản mới mà mất nội dung người dùng đã nhập.

## 16. OpenAPI 3.1 cho GET và PUT có điều kiện

Ví dụ hợp đồng tài liệu có đường **GET** phát ETag và **PUT** bắt buộc If-Match. Định nghĩa response lỗi bằng Problem Details.

~~~yaml
openapi: 3.1.0
info:
  title: Document Concurrency API
  version: 1.0.0
paths:
  /api/v1/documents/{documentId}:
    parameters:
      - name: documentId
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      operationId: getDocument
      summary: Lấy tài liệu cùng ETag
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Biểu diễn tài liệu hiện tại
          headers:
            ETag:
              description: Strong validator của biểu diễn
              required: true
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Document'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '404':
          $ref: '#/components/responses/NotFound'
    put:
      operationId: replaceDocument
      summary: Thay thế tài liệu nếu trạng thái chưa đổi
      description: >
        Client GET trước để nhận ETag. Khi PUT phải gửi If-Match
        với strong ETag. Nếu phiên bản đã thay đổi trả 412.
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: If-Match
          required: true
          description: Strong ETag từ GET cùng resource, ví dụ "document-...-v7".
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ReplaceDocument'
      responses:
        '200':
          description: Cập nhật thành công, trả biểu diễn mới
          headers:
            ETag:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Document'
        '400':
          $ref: '#/components/responses/BadRequest'
        '401':
          $ref: '#/components/responses/Unauthorized'
        '403':
          $ref: '#/components/responses/Forbidden'
        '404':
          $ref: '#/components/responses/NotFound'
        '409':
          $ref: '#/components/responses/Conflict'
        '412':
          $ref: '#/components/responses/PreconditionFailed'
        '428':
          $ref: '#/components/responses/PreconditionRequired'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Document:
      type: object
      required: [id, title, status, version]
      properties:
        id:
          type: string
          format: uuid
        title:
          type: string
        status:
          type: string
        version:
          type: integer
          minimum: 0
    ReplaceDocument:
      type: object
      required: [title, status]
      properties:
        title:
          type: string
          minLength: 1
        status:
          type: string
          enum: [DRAFT, REVIEWED]
    ApiProblem:
      type: object
      required: [type, title, status]
      properties:
        type:
          type: string
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
        code:
          type: string
  responses:
    BadRequest:
      description: Request sai cú pháp hoặc không hợp lệ
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Unauthorized:
      description: Chưa xác thực hợp lệ
      headers:
        WWW-Authenticate:
          schema:
            type: string
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Forbidden:
      description: Không có quyền
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    NotFound:
      description: Resource không tồn tại hoặc không thể công bố
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    Conflict:
      description: Xung đột trạng thái nghiệp vụ
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    PreconditionFailed:
      description: If-Match không khớp
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
    PreconditionRequired:
      description: API yêu cầu If-Match
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ApiProblem'
~~~

**Giải thích:** OpenAPI mô tả header và response, nhưng không tự buộc server kiểm tra strong ETag hoặc transaction. Cần kiểm thử đúng hành vi qua mạng. Bản production có thể bổ sung PATCH/DELETE, error code cụ thể, nhiều representation và ví dụ response lỗi.

## 17. Kiểm thử bằng curl và HTTP

Làm trên **môi trường thử nghiệm** với tài liệu UUID hợp lệ, ví dụ **11111111-1111-4111-8111-111111111111**. URL và token dưới đây là giá trị minh họa.

~~~bash
# 1. GET biểu diễn hiện tại; ghi lại ETag từ response.
curl -i \
  -H "Authorization: Bearer YOUR_TEST_TOKEN" \
  https://api.example.test/api/v1/documents/11111111-1111-4111-8111-111111111111

# 2. PUT với strong ETag thực nhận được từ GET.
curl -i -X PUT \
  -H "Authorization: Bearer YOUR_TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -H 'If-Match: "document-11111111-1111-4111-8111-111111111111-v7"' \
  --data '{"title":"Hợp đồng cập nhật","status":"DRAFT"}' \
  https://api.example.test/api/v1/documents/11111111-1111-4111-8111-111111111111

# 3. Retry với ETag cũ để quan sát hành vi precondition.
# Mã thường gặp sau khi request đầu đã thành công là 412.
~~~

**Không đoán ETag** dựa vào số version trong ví dụ khi chạy test thực; phải lấy giá trị được server phát hành. Không thực hiện PUT/DELETE lên dữ liệu production khi chưa được cho phép.

### 17.1. Ma trận kiểm thử bắt buộc

| Mã | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| P01 | GET tài liệu hợp lệ | 200 và strong ETag phù hợp biểu diễn |
| P02 | PUT với If-Match đúng | 200/204, dữ liệu đổi, version tăng |
| P03 | GET lại sau PUT | ETag đổi khi biểu diễn đổi |
| P04 | PUT thiếu If-Match | 428; dữ liệu không đổi |
| P05 | PUT với ETag cũ | 412; dữ liệu hiện tại không bị ghi đè |
| P06 | If-Match weak tag W/ | Không được coi là strong match |
| P07 | If-Match danh sách tag | Kiểm tra OR semantics nếu API hỗ trợ chuẩn đầy đủ |
| P08 | If-Match: * | Kiểm tra ngữ nghĩa resource tồn tại và chính sách API |
| P09 | If-None-Match: * khi PUT tạo mới | Tạo nếu chưa tồn tại; 412 nếu đã có |
| P10 | PUT tài liệu bị khóa với ETag hiện tại | 409 nếu policy cấm sửa |
| P11 | Hai client cùng đọc v7, cùng PUT | Chỉ một cập nhật được commit trên version v7 |
| P12 | Race giữa SELECT và UPDATE | Câu UPDATE có điều kiện không ghi đè phiên bản mới |
| P13 | PATCH có If-Match | Không áp patch vào version cũ |
| P14 | DELETE có If-Match | Không xóa tài liệu vừa được thay đổi |
| P15 | User A cố sửa document tenant B | 403/404 theo policy; không lộ ETag B |
| P16 | Không có token | 401; không đánh giá precondition để tiết lộ dữ liệu |
| P17 | Retry PUT sau commit nhưng mất response | Không tạo side effect trùng; xử lý kết quả không rõ |
| P18 | If-None-Match conditional GET | 304 nếu chưa đổi; phân biệt rõ với 412 của PUT |
| P19 | Cache/Authorization | 304/ETag không bỏ qua quyền và không trộn biểu diễn |
| P20 | Content negotiation/variant | ETag phù hợp representation, không nhầm phiên bản |
| P21 | Resource đã xóa | 404 hoặc 412 theo tình huống và hợp đồng |
| P22 | Lỗi hệ thống/DB timeout | Không biến lỗi hạ tầng thành 412 |
| P23 | Concurrent update từ background job | Job cũng tăng version hoặc phối hợp điều kiện |
| P24 | DTO có field không hợp lệ | 400/422 theo policy, không mutate resource |

### 17.2. Kiểm thử cạnh tranh đồng thời

Một kiểm thử có giá trị hơn việc gọi API tuần tự hai lần:

1. Tạo tài liệu version 7.
2. Cho hai client GET và nhận cùng ETag v7.
3. Dùng barrier để hai request PUT cùng gửi gần đồng thời.
4. Chờ hoàn tất và ghi hai status.
5. Xác minh **chỉ một thay đổi dựa trên v7 được commit**; request còn lại bị từ chối theo điều kiện/concurrency policy.
6. Đọc lại DB và API: version mới, body và audit/event đúng.
7. Lặp nhiều lần, thử trên nhiều instance/connection pool.

Các trạng thái cụ thể có thể bị ảnh hưởng bởi transaction isolation/deadlock retry và error mapping của ứng dụng; bài test cần assert **bất biến dữ liệu**, không chỉ một timing ngẫu nhiên.

### 17.3. Kiểm thử optimistic locking trong JPA

Nếu dùng @Version, bổ sung integration test trong đó hai transaction đọc cùng một phiên bản rồi cập nhật. Khi flush/commit, một transaction phải phát hiện conflict, hoặc được DB/transaction manager buộc retry theo chính sách. Đừng để test chỉ xác nhận exception ở controller mà không kiểm tra **dữ liệu cuối** và **không có side effect trùng**.

## 18. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng GET rồi PUT không kèm version | Lost update | Phát ETag và yêu cầu If-Match |
| Chỉ kiểm tra ETag bằng SELECT trước khi UPDATE | Race giữa kiểm tra và commit | UPDATE/DELETE có điều kiện nguyên tử hoặc optimistic lock |
| Dùng weak ETag cho If-Match | Không thỏa strong comparison | Dùng strong ETag đúng representation |
| Coi If-Match: * là chống lost update | Chỉ kiểm tra tồn tại, bỏ qua version | Yêu cầu tag cụ thể nếu cần bảo vệ bản đã đọc |
| Nhầm If-None-Match với If-Match | 304/412 hoặc create/update sai | Phân biệt mục tiêu các preconditions |
| Trả 409 cho mọi ETag mismatch | Client khó phân loại HTTP precondition | Dùng 412 cho If-Match false |
| Trả 412 khi thiếu header | Không rõ chính sách yêu cầu có điều kiện | Dùng 428 nếu API bắt buộc If-Match |
| Trả 412 trước khi kiểm tra quyền | Có thể lộ tài nguyên hoặc version | Authn/authz và policy an toàn |
| Chỉ dựa @Version, không truyền version client | Client ghi dựa trên bản rất cũ mà không biết | Kết hợp @Version với If-Match |
| Không tăng version khi background job sửa | ETag còn khớp dù dữ liệu đổi | Version mọi đường ghi cần nhất quán |
| Tự tạo ETag từ đồng hồ hiện tại | Validator đổi ngay cả khi body không đổi | Validator ổn định từ version/representation |
| Tái dùng ETag cho representation khác | Cache/precondition sai | Quản lý variant/representation và Vary |
| Retry PUT với tag cũ cho tới khi 2xx | Vòng lặp hoặc xóa nội dung local | Xử lý 412 bằng read/merge |
| Cho rằng 412 chứng minh request trước chưa commit | Kết quả có thể không rõ sau timeout | Dùng operation tracking/idempotency nếu cần |
| Cho client truyền tenantId như quyền | Ghi đè dữ liệu tenant khác | Trusted principal/ACL ở backend |
| Kiểm tra version nhưng bỏ qua trạng thái LOCKED | Thay đổi đúng version nhưng trái nghiệp vụ | Kiểm tra cả policy trạng thái |
| Mọi update đều yêu cầu merge tự động | Có thể áp sai thay đổi nghiệp vụ | Cần UI/flow giải quyết xung đột |

## 19. Bài thực hành: chỉnh sửa hồ sơ nhiều người dùng

**Bối cảnh:** hệ thống quản lý hồ sơ khách hàng có endpoint:

- GET **/api/v1/customers/{id}** trả hồ sơ với ETag;
- PUT **/api/v1/customers/{id}** thay thế thông tin hồ sơ;
- PATCH **/api/v1/customers/{id}** cập nhật một số trường;
- DELETE **/api/v1/customers/{id}** chỉ được phép khi hồ sơ chưa có giao dịch gắn kết.

Nhân viên A và B cùng GET khách hàng version 12. B thay đổi số điện thoại và lưu thành version 13; A vẫn giữ biểu diễn cũ với địa chỉ mới. Đồng thời, hệ thống có background job chuẩn hóa tên khách hàng.

### Nhiệm vụ A – Thiết kế hợp đồng HTTP

1. Viết request/response GET với strong ETag.
2. Viết PUT với If-Match của version 12; xác định status nếu version hiện tại đã là 13.
3. Viết response Problem Details cho 412 và 428.
4. Giải thích khi nào dùng 409 nếu hồ sơ bị khóa nghiệp vụ.
5. Xác định hành vi If-Match: * khác gì ETag v12.

### Nhiệm vụ B – Thiết kế dữ liệu

1. Đề xuất version column và câu SQL UPDATE có điều kiện **customer_id, tenant_id, version**.
2. Giải thích vì sao phải tăng version khi background job chỉnh sửa.
3. So sánh việc dùng JPA @Version với SQL UPDATE điều kiện.
4. Xử lý tình huống affected rows = 0 mà không lộ thông tin khách hàng ngoài quyền.

### Nhiệm vụ C – UX và retry

1. Thiết kế luồng UI khi A nhận 412, giữ thay đổi local và so sánh với version 13.
2. Nêu cách ứng dụng xử lý POST/PUT mất phản hồi sau commit mà không tạo side effect trùng.
3. Chỉ ra vì sao “retry PUT với If-Match cũ” không phải chiến lược giải quyết 412.

### Nhiệm vụ D – Kiểm thử

Viết ít nhất tám test bao phủ: thiếu If-Match, mismatch, concurrent PUT, DELETE có điều kiện, cross-tenant authorization, weak ETag, background job tăng version, cache/304 và retry sau timeout.

### 19.1. Hướng giải tham khảo

| Trường hợp | Kết quả gợi ý | Lý do |
| --- | --- | --- |
| GET hồ sơ v12 | 200 + ETag "customer-v12" | Trả validator server kiểm soát |
| PUT đúng tag và còn quyền | 200/204 + phiên bản mới | Ghi có điều kiện thành công |
| PUT v12 khi DB đã v13 | 412 | Precondition thất bại |
| PUT thiếu If-Match theo policy | 428 | Chưa gửi điều kiện bắt buộc |
| PATCH v12 khi DB v13 | 412 | Không áp patch vào bản cũ |
| DELETE v12 khi DB đã v13 | 412 | Không xóa bản mới |
| Hồ sơ LOCKED | 409 | Xung đột nghiệp vụ |
| User tenant A sửa hồ sơ tenant B | 403/404 theo policy | Ngăn truy cập chéo tenant |
| GET với If-None-Match trùng | 304 nếu đủ điều kiện | Conditional GET/cache validation |

Một lời giải tốt sẽ làm rõ **source of truth của version**, **atomic predicate tại DB**, **security scope**, **error contract** và **UX khi conflict**, chứ không chỉ trả đúng status trên một request tuần tự.

## 20. Checklist trước khi phát hành

- [ ] GET trả ETag gắn với representation đúng.
- [ ] PUT/PATCH/DELETE có If-Match khi cần bảo vệ version đã đọc.
- [ ] Tôi biết If-Match dùng **strong comparison**.
- [ ] Tôi phân biệt If-Match tag cụ thể, danh sách tag và wildcard.
- [ ] Tôi không coi If-Match: * là phép bảo vệ version.
- [ ] Tôi biết khi nào phản hồi 412 và 428.
- [ ] Tôi phân biệt xung đột version với 409 nghiệp vụ.
- [ ] Tôi kiểm tra authn/authz/tenant trước khi tiết lộ tình trạng resource.
- [ ] Tôi ràng buộc version ngay trong UPDATE/DELETE nguyên tử.
- [ ] Tôi hiểu @Version JPA hỗ trợ DB concurrency nhưng không thay If-Match.
- [ ] Mọi đường ghi, kể cả job, đều cập nhật version đúng.
- [ ] Tôi không trộn validator của các representation khác nhau.
- [ ] Client giữ local changes, GET lại và giải quyết xung đột khi nhận 412.
- [ ] Tôi không dùng 304 cho PUT bị từ chối bởi If-Match.
- [ ] Tôi phân biệt retry sau timeout với việc xử lý lost update.
- [ ] OpenAPI có If-Match, ETag, 412, 428 và Problem Details.
- [ ] Có integration test hai request đồng thời, permission và side effect.

**Ghi nhớ:** **If-Match nối ý định của client với phiên bản tài nguyên mà client đã đọc**. Nhưng để thật sự tránh lost update, server phải đi xa hơn việc so header: kiểm tra **strong ETag**, **phân quyền**, **quy tắc nghiệp vụ** và thực hiện **ghi có điều kiện nguyên tử** tại tầng dữ liệu. **412** là tín hiệu bảo vệ thay đổi của người khác, không phải lời mời retry vô điều kiện.

### Tài liệu chuẩn để tra cứu

- **RFC 9110 – HTTP Semantics:** mục If-Match, ETag, precondition evaluation và 412 Precondition Failed.
- **RFC 6585 – Additional HTTP Status Codes:** 428 Precondition Required.
- **RFC 9111 – HTTP Caching:** validators, conditional requests và cache revalidation.
- **RFC 5789 – PATCH Method for HTTP:** PATCH và tương tác với conditional requests.
- **RFC 9457 – Problem Details for HTTP APIs:** phản hồi lỗi application/problem+json.
- **OpenAPI Specification 3.1:** headers, responses, schemas và security.
- **Spring Framework / Spring Data JPA:** ResponseEntity, ETag, optimistic locking với @Version, JdbcTemplate và transactions.
