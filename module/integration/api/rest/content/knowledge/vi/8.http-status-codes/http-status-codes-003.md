# Location khi tạo tài nguyên và theo dõi xử lý bất đồng bộ

> **Phạm vi:** Bài học thuộc **INTEGRATION_API_REST**, chương **Mã trạng thái**. Trọng tâm là thiết kế REST API theo resource, URI, phương thức và mã trạng thái HTTP: sử dụng header `Location` để công bố tài nguyên vừa tạo, phân biệt yêu cầu đã hoàn thành với yêu cầu mới được tiếp nhận, và thiết kế tài nguyên theo dõi một công việc bất đồng bộ. Bài có ví dụ HTTP/JSON, Java/Spring MVC, OpenAPI, xử lý lỗi và kiểm thử API.

## 1. Vì sao cùng một POST có thể trả hai mã khác nhau?

Một cửa hàng có hai endpoint:

1. `POST /v1/orders` tạo một đơn hàng. Server đã kiểm tra dữ liệu, ghi đơn và có thể trả lại đơn theo ID ngay.
2. `POST /v1/reports` yêu cầu tạo báo cáo tháng. Tác vụ cần tổng hợp nhiều bảng, truy vấn kho dữ liệu và tạo tệp CSV; thời gian hoàn tất có thể từ vài giây đến nhiều phút.

Cả hai đều dùng POST nhưng kết quả ở thời điểm gửi phản hồi **khác nhau**. Nếu đơn đã được tạo, server cần báo rằng tài nguyên đã tồn tại và cung cấp URI của nó. Nếu báo cáo chưa có, server nên xác nhận công việc đã được chấp nhận và chỉ cho client cách theo dõi, thay vì ngầm hứa đã hoàn tất.

Hai câu hỏi luôn phải trả lời trước khi chọn status:

- **Điều gì đã hoàn thành trước khi phản hồi HTTP được gửi?** Tài nguyên chính đã được tạo, hay chỉ mới có yêu cầu đang chờ xử lý?
- **Client cần làm gì tiếp theo?** Đọc tài nguyên vừa tạo, theo dõi tiến độ, xử lý lỗi hay tải tài nguyên kết quả?

Chỉ trả `200 OK` với `{"success":true}` cho mọi trường hợp sẽ che mờ các câu trả lời này, khiến client phải dự đoán hành vi bằng các giá trị JSON riêng.

### 1.1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt chính xác `201 Created`, `202 Accepted`, `200 OK`, `204 No Content` và `303 See Other` trong việc tạo resource và xử lý nền.
- Xác định `Location` phải trỏ tới URI tài nguyên nào; phân biệt với `Content-Location`.
- Thiết kế monitor resource như `/operations/{id}`, có trạng thái, kết quả, lỗi, thời gian lưu giữ và quy ước polling.
- Kết hợp idempotency, lưu công việc bền vững, phân quyền và giới hạn số lần polling để hệ thống hoạt động đáng tin cậy.
- Mô tả hợp đồng HTTP/OpenAPI và kiểm thử một số đường đi thành công, thất bại, retry, hết hạn và tác vụ trùng lặp.

## 2. Bảng quyết định HTTP status code

| Status | Ý nghĩa | Ví dụ phù hợp | Dễ nhầm với |
|---|---|---|---|
| **200 OK** | Yêu cầu hiện tại đã xử lý thành công, có thể có representation | GET đơn hoặc GET trạng thái operation | Không có nghĩa tác vụ nền đã thành công |
| **201 Created** | Yêu cầu thành công và đã tạo một hay nhiều resource | POST tạo đơn đã được lưu | Không nên dùng khi tài nguyên nghiệp vụ còn chưa được tạo theo hợp đồng |
| **202 Accepted** | Yêu cầu được tiếp nhận nhưng xử lý chưa hoàn tất; kết quả cuối có thể thất bại | POST khởi động xuất báo cáo nền | Không phải lời hứa công việc chắc chắn thành công |
| **204 No Content** | Yêu cầu đã thành công và không có response content | PUT/PATCH thành công không trả body | Không mang ý nghĩa công việc còn đang chạy |
| **303 See Other** | Client có thể truy xuất kết quả tại URI khác bằng GET | GET operation khi thành công dẫn tới GET report | Không đồng nghĩa POST ban đầu đã tạo xong resource |
| **400 Bad Request** | Request không thể được xử lý vì đầu vào sai ở cấp HTTP/cú pháp | JSON lỗi hoặc tham số cấu trúc không hợp lệ | Không phải lỗi worker sau khi đã nhận job |
| **401 Unauthorized** | Cần thông tin xác thực hợp lệ | Không có access token hợp lệ | Khác 403 |
| **403 Forbidden** | Bị từ chối do không đủ quyền | User A đọc job của user B | Có thể dùng 404 để che sự tồn tại theo policy |
| **404 Not Found** | Resource không tồn tại hoặc không được phép công bố | ID operation không tìm thấy | Chưa chắc là job đã thất bại |
| **409 Conflict** | Request xung đột trạng thái resource | Idempotency key trùng nhưng payload khác | Không dùng cho mọi validation error |
| **410 Gone** | Resource không còn và server biết tình trạng này có tính lâu dài | Operation hết thời gian lưu, còn dấu vết để xác nhận | Không bắt buộc khi đã xóa mọi dấu vết |
| **422 Unprocessable Content** | Nội dung cú pháp hợp lệ nhưng không thể xử lý theo ngữ nghĩa | Khoảng ngày xuất báo cáo không được chấp nhận | Phân biệt với job FAILED sau khi đã 202 |
| **429 Too Many Requests** | Gửi quá nhiều request | Client poll quá nhanh | Không biểu đạt tiến độ tác vụ |
| **503 Service Unavailable** | Server tạm không đáp ứng | Hệ thống tiếp nhận job đang quá tải | Không nên trả 202 khi chưa tiếp nhận bền vững |

Điểm quan trọng: status HTTP nói về **lần trao đổi HTTP hiện tại**. Một job được nhận lúc 09:00 với phản hồi `202` có thể thất bại lúc 09:03, nhưng server không thể quay lại sửa status của phản hồi trước đó. Client phải biết địa chỉ để kiểm tra trạng thái sau này.

~~~mermaid
flowchart TD
    A["POST tới API"] --> B{"Dữ liệu hợp lệ và có quyền?"}
    B -- "Không" --> X["4xx phù hợp"]
    B -- "Có" --> C{"Công việc nghiệp vụ đã hoàn thành?"}
    C -- "Đã tạo resource chính" --> D["201 Created + Location resource"]
    C -- "Đã xử lý, không tạo resource" --> E["200 OK hoặc 204 No Content"]
    C -- "Chưa, nhưng đã tiếp nhận bền vững" --> F["202 Accepted + URI monitor"]
    C -- "Chưa và không thể tiếp nhận" --> G["4xx / 5xx phù hợp"]
~~~

Có một sắc thái cần nhớ: nếu endpoint có mục đích **tạo chính resource operation** và resource này đã được tạo ngay, `201` cho operation có thể phù hợp dù việc nền chưa kết thúc. Với endpoint `POST /reports` có ý nghĩa **yêu cầu tạo báo cáo**, `202` và monitor resource thường truyền đạt rõ hơn ý nghĩa chưa hoàn tất. Thiết kế cần xác định chính xác **resource chính** là gì.

## 3. `201 Created` và `Location` khi tạo tài nguyên

### 3.1. Ví dụ HTTP

Client tạo đơn:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "customerId": "cus_82",
  "items": [{"sku": "SKU-101", "quantity": 2}]
}
~~~

Server đã lưu tài nguyên đơn hàng:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/orders/ord_916
Content-Type: application/json

{
  "id": "ord_916",
  "status": "PENDING_PAYMENT",
  "items": [{"sku": "SKU-101", "quantity": 2}],
  "links": {"self": "/v1/orders/ord_916"}
}
~~~

`Location` ở đây định danh **tài nguyên chính mới tạo**. Nếu client `GET` URI đó và có đủ quyền, API nên phục vụ representation tương ứng theo hợp đồng. Trạng thái `PENDING_PAYMENT` là **trạng thái nghiệp vụ của một đơn đã tồn tại**, không có nghĩa thao tác tạo đơn còn đang chờ. Việc thu tiền hoặc gửi email có thể thực hiện sau này mà thao tác **tạo đơn** vẫn hoàn tất.

Theo ngữ nghĩa HTTP, `201` báo một hoặc nhiều tài nguyên mới được tạo; tài nguyên chính được nhận diện bởi `Location` nếu có, nếu không thì dựa vào URI đích theo quy định của giao thức. Khi POST vào collection như `/orders`, **nên** trả Location rõ ràng để client không phải tự ghép URI từ ID hay đoán resource nào đã tạo.

### 3.2. Location nên chứa URI nào?

- **URI ổn định của resource**, ví dụ `/v1/orders/ord_916`, không phải địa chỉ vật lý của một pod, node hay máy chủ xử lý.
- URI có thể là dạng tuyệt đối hoặc tham chiếu tương đối theo ngữ nghĩa HTTP; cung cấp URL tuyệt đối thường tiện cho các client, nhưng cần lấy từ **public base URL đáng tin cậy**.
- Khi sau reverse proxy/API Gateway, không tạo Location dựa mù quáng vào header `Host` hoặc `Forwarded` do client tùy ý đưa vào. Dùng cấu hình gateway/proxy được tin cậy để tránh trả URL giả hoặc địa chỉ nội bộ.
- Không đặt bearer token, mật khẩu, email hay dữ liệu nhạy cảm trong URL. ID khó đoán giúp giảm dò tìm nhưng **không thay thế kiểm tra quyền**.
- Nếu tài nguyên vừa tạo nằm trên bản sao đọc có độ trễ, phải xác định kỳ vọng đọc ngay sau ghi. Một phản hồi `201` theo sau bởi `404` lặp đi lặp lại có thể gây khó hiểu nếu không có hợp đồng về eventual consistency.

### 3.3. Body có bắt buộc không?

`201` không yêu cầu body JSON. Có thể trả `201` cùng `Location` và không có body, hoặc trả representation mới tạo để giảm lượt GET đầu tiên. Nếu có body, mô tả rõ nó là representation, bản tóm tắt hay metadata kết quả.

`204 No Content` lại mang ý nghĩa yêu cầu đã thành công nhưng **không có response content**. Không gửi JSON cùng `204` và không coi nó tương đương `202`; `204` không biểu thị xử lý chưa hoàn tất.

### 3.4. Phân biệt `Location` và `Content-Location`

| Header | Chức năng | Trong API này |
|---|---|---|
| `Location` | Xác định URI liên quan tới kết quả: với 201 là resource chính đã tạo, với redirect là URI đích | `Location: /v1/orders/ord_916` |
| `Content-Location` | Xác định URI tương ứng với representation trong nội dung phản hồi theo ngữ nghĩa HTTP | Có thể có khi body đúng representation của URI đó, nhưng không phải header chỉ đích tạo mới |

Không dùng `Content-Location` thay cho `Location` để chỉ nơi client cần GET tài nguyên mới hoặc monitor job. Nhiều API đơn giản không cần `Content-Location`.

## 4. `202 Accepted`: nhận công việc chưa hoàn tất

Một số công việc nên chạy nền: xuất báo cáo lớn, nhập file hàng trăm nghìn dòng, xử lý video, đồng bộ dữ liệu, gửi thông báo hàng loạt hoặc gọi nhiều dịch vụ ngoài có thời gian không thể dự đoán. Giữ kết nối HTTP chờ đến khi xong làm tăng timeout, rủi ro client retry và chi phí tài nguyên.

`202 Accepted` nói rằng server đã nhận yêu cầu **để xử lý**, nhưng quá trình chưa hoàn tất; kết quả vẫn có thể bị từ chối hoặc thất bại ở giai đoạn sau. Điều này khác với `201` khi tài nguyên chính đã được tạo.

### 4.1. Ví dụ yêu cầu tạo báo cáo

~~~http
POST /v1/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 04f38e72-d37a-4a22-bc82-6e82187de9c2
Content-Type: application/json
Prefer: respond-async

{
  "type": "monthly-orders",
  "from": "2026-10-01",
  "to": "2026-10-31",
  "format": "csv"
}
~~~

Server đã nhận yêu cầu một cách bền vững nhưng chưa có báo cáo:

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v1/operations/op_a71c
Retry-After: 3
Cache-Control: no-store
Content-Type: application/json

{
  "id": "op_a71c",
  "type": "report-export",
  "status": "QUEUED",
  "submittedAt": "2026-11-18T09:00:00Z",
  "links": {
    "self": "/v1/operations/op_a71c"
  }
}
~~~

Ở ví dụ này:

- `202` xác nhận công việc **đã được nhận**, không phải CSV đã xuất xong.
- `Location` trỏ tới **operation monitor**, là tài nguyên có thể đọc để theo dõi tiến độ.
- `Retry-After: 3` là **gợi ý thời gian polling theo hợp đồng của API này**. Chuẩn HTTP không bắt mọi client diễn giải `Retry-After` trên `202` theo cách đó; vì thế cần mô tả trong tài liệu.
- `Prefer: respond-async` là cách client biểu thị ưu tiên xử lý không đồng bộ nếu dịch vụ hỗ trợ. Nó không tự bắt server phải xử lý theo một kiểu; server cần xác định chính sách và hành vi phản hồi.
- `Idempotency-Key` là khóa theo hợp đồng API nhằm tránh tạo nhiều tác vụ khi phải gửi lại cùng request. Framework không tự bảo đảm hành vi này chỉ vì client gửi header.

**Quan trọng:** Đối với `201`, `Location` có ngữ nghĩa xác định resource vừa tạo. Đối với `202`, HTTP **không bắt buộc** phải có `Location` trỏ tới operation; đây là **mẫu thiết kế hữu ích**, cần được mô tả rõ trong API contract. Thân phản hồi `202` cũng nên giải thích trạng thái hiện tại và cung cấp đường dẫn monitor.

Nếu server chưa thể lưu bền vững yêu cầu, chưa bảo đảm nó sẽ được tìm lại sau crash hoặc chưa chấp nhận do quota, đừng trả `202` trước rồi hy vọng worker sẽ nhận được. Dùng lỗi `4xx`/`5xx` phù hợp tại thời điểm tiếp nhận.

## 5. Theo dõi một operation resource

### 5.1. Phân biệt operation và resource kết quả

Mỗi loại tài nguyên có trách nhiệm riêng:

| Resource | URI mẫu | Nó đại diện cho điều gì? |
|---|---|---|
| Operation | `/v1/operations/op_a71c` | Một lần thực thi: người yêu cầu, thời điểm, trạng thái, tiến độ, lỗi và liên kết kết quả |
| Report | `/v1/reports/r_45` | Báo cáo đã được tạo, nội dung, định dạng, quyền xem và thời hạn lưu |

Một operation **thất bại** có thể không tạo ra report. Nhiều operation có thể tạo các phiên bản báo cáo khác nhau. Không nên đặt `Location` của response `202` thành URI của một tệp báo cáo chưa tồn tại, khiến client GET thấy `404` mà không biết phải đợi hay đã lỗi.

### 5.2. State machine

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED: API tiếp nhận bền vững
    QUEUED --> RUNNING: Worker bắt đầu
    QUEUED --> CANCELLED: Hủy khi chưa chạy
    RUNNING --> SUCCEEDED: Hoàn tất, lưu kết quả
    RUNNING --> FAILED: Lỗi kết thúc
    RUNNING --> CANCELLING: Có yêu cầu hủy
    CANCELLING --> CANCELLED: Đã dừng
    CANCELLING --> SUCCEEDED: Hoàn tất trước khi dừng
    CANCELLING --> FAILED: Thất bại khi dừng hoặc xử lý
    SUCCEEDED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
~~~

Các từ `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLING` và `CANCELLED` là **trạng thái của tác vụ**, không phải HTTP status. Có thể bổ sung `EXPIRED` cho logic lưu giữ, nhưng khi xóa operation hẳn khỏi kho, API phải lựa chọn rõ `404` hoặc `410` theo khả năng biết lịch sử.

Nếu hỗ trợ hủy, cần ghi rõ: hủy chỉ là yêu cầu hay đã chắc chắn dừng; tác động nghiệp vụ đã xảy ra có thể khôi phục không; và trường hợp kết thúc cùng lúc với lệnh hủy xử lý thế nào.

### 5.3. GET monitor khi chưa xong

~~~http
GET /v1/operations/op_a71c HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{
  "id": "op_a71c",
  "status": "RUNNING",
  "submittedAt": "2026-11-18T09:00:00Z",
  "startedAt": "2026-11-18T09:00:03Z",
  "updatedAt": "2026-11-18T09:00:36Z",
  "progress": {
    "completed": 45,
    "total": 100,
    "unit": "percent"
  },
  "links": {"self": "/v1/operations/op_a71c"}
}
~~~

**Vì sao response là 200 khi job vẫn chạy?** Bởi request GET hiện tại đã **đọc thành công resource monitor**; kết quả nghiệp vụ của job được biểu diễn bằng `status: RUNNING`. Có API thiết kế GET monitor trả `202` nếu chưa xong, nhưng muốn vậy phải công bố rõ contract; `200` kèm representation là mô hình đơn giản và dễ xây SDK.

Chỉ trả phần trăm tiến độ nếu có thể đo tin cậy; khi không biết tổng số bước, dùng progress theo giai đoạn hoặc bỏ trường này. Tránh để 99% kéo dài vô hạn mà không có heartbeat, deadline hoặc cảnh báo.

### 5.4. Khi thành công: 200 kèm liên kết hoặc 303

**Phương án A – trạng thái thành công ngay trong monitor:**

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "op_a71c",
  "status": "SUCCEEDED",
  "finishedAt": "2026-11-18T09:01:10Z",
  "result": {
    "reportId": "r_45",
    "href": "/v1/reports/r_45"
  }
}
~~~

Client đọc `result.href` và GET resource kết quả. Mẫu này giữ schema operation nhất quán qua các trạng thái, phù hợp UI hiển thị lịch sử, lỗi và dữ liệu bổ sung.

**Phương án B – điều hướng tới kết quả với `303 See Other`:**

~~~http
HTTP/1.1 303 See Other
Location: https://api.example.test/v1/reports/r_45
Cache-Control: no-store
~~~

Client theo `Location` bằng `GET` tới báo cáo. `303` diễn đạt rõ kết quả có thể được truy xuất tại URI khác. Một số thư viện HTTP tự động theo redirect, có thể che đi response `303` trung gian; client cần biết cấu hình để quan sát hoặc xử lý đúng.

**Chọn một phương án chính, đừng thay đổi tùy thời điểm.** Nếu dùng phương án B, GET operation đang chạy trả `200` và khi hoàn tất trả `303`. Nếu dùng phương án A, GET luôn trả `200` và client đọc `status`, sau đó GET `result.href`.

### 5.5. Khi job FAILED

Giả sử worker không thể lấy đủ dữ liệu để xuất CSV:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "op_a71c",
  "status": "FAILED",
  "finishedAt": "2026-11-18T09:01:10Z",
  "error": {
    "code": "REPORT_SOURCE_NOT_READY",
    "message": "Dữ liệu nguồn chưa sẵn sàng cho kỳ báo cáo.",
    "retryable": true
  }
}
~~~

`200` ở đây **không khẳng định job thành công**. Nó khẳng định GET monitor xử lý thành công; body cho biết job thất bại. Nếu chính việc đọc operation store bị lỗi, server có thể trả `5xx` cho request GET đó. Không trả `500` một cách máy móc chỉ vì operation có trạng thái `FAILED`.

Lỗi trả cho client cần mã ổn định, thông điệp an toàn, không lộ SQL, token, đường dẫn nội bộ hoặc dữ liệu của người khác. Trường `retryable` phải đi kèm hướng dẫn cụ thể: tạo job mới, thử lại operation cũ, sửa dữ liệu đầu vào hay liên hệ người quản trị.

### 5.6. Khi monitor hết hạn

Server phải tài liệu hóa thời gian giữ operation và report. Nếu giữ operation bảy ngày:

- Có thể trả `410 Gone` khi server còn biết operation từng tồn tại và hiện đã bị xóa/hết hiệu lực.
- Có thể trả `404 Not Found` nếu đã xóa mọi dấu vết, không còn phân biệt được với ID chưa từng có, hoặc chính sách bảo mật yêu cầu che thông tin.

Không bắt buộc `410` cho mọi ID không tìm thấy. Kết quả báo cáo có thể có thời hạn lưu khác trạng thái operation; client cần biết để tải đúng hạn.

## 6. Toàn bộ vòng đời client-server

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant A as REST API
    participant S as Operation Store
    participant Q as Queue
    participant W as Worker
    C->>A: POST /v1/reports
    A->>S: Lưu operation và yêu cầu bền vững
    A-->>C: 202 + Location /v1/operations/op_a71c
    C->>A: GET /v1/operations/op_a71c
    A->>S: Đọc operation được phân quyền
    A-->>C: 200 + QUEUED / RUNNING
    Q-->>W: Giao việc
    W->>S: Ghi tiến độ và trạng thái cuối
    C->>A: GET /v1/operations/op_a71c
    A-->>C: 303 + Location /v1/reports/r_45
    C->>A: GET /v1/reports/r_45
    A-->>C: 200 + báo cáo
~~~

Trong sơ đồ, operation store và queue có thể cập nhật qua **outbox hoặc cơ chế tiếp nhận bền vững**; thứ tự xử lý thực tế cần chống khe hở giữa ghi DB và publish message. Worker và HTTP server có thể chạy trên nhiều instance; không thể chỉ lưu trạng thái trong bộ nhớ một JVM. Đường thất bại sẽ ghi `FAILED` vào operation, không nhất thiết có resource kết quả.

### 6.1. Ma trận endpoint

| URI | Method | Chức năng | Status chuẩn của tình huống |
|---|---|---|---|
| `/v1/orders` | POST | Tạo đơn đồng bộ | `201` + Location đơn |
| `/v1/orders/{id}` | GET | Đọc đơn | `200`; `401/403/404` nếu không được phép/không có |
| `/v1/reports` | POST | Khởi tạo xuất báo cáo | `202` + Location operation |
| `/v1/operations/{id}` | GET | Trạng thái báo cáo | `200` + body; hoặc `303` khi thành công theo contract |
| `/v1/reports/{id}` | GET | Đọc/tải báo cáo đã tạo | `200` và nội dung thích hợp |
| `/v1/operations/{id}/cancel` | POST (tùy chọn) | Yêu cầu hủy operation | Status/body theo mức hoàn thành và tính chất hủy |

Nếu dùng `DELETE /operations/{id}` để hủy, cần mô tả rõ xóa resource monitor, yêu cầu ngừng xử lý hay đảo ngược tác động nghiệp vụ có ý nghĩa gì. Không mặc định xóa URI đồng nghĩa undo một giao dịch đã xảy ra.

## 7. Idempotency khi client retry

Hãy xét trường hợp server đã nhận `POST /reports`, đã lưu operation, nhưng kết nối mất **trước khi client nhận response 202**. Client không biết job đã được tạo hay chưa và rất dễ gửi POST lần nữa. Nếu server không chống trùng, hai job có thể xuất cùng báo cáo, cùng ghi dữ liệu hoặc phát sinh chi phí gấp đôi.

### 7.1. Khóa chống trùng

Ví dụ:

~~~http
POST /v1/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 04f38e72-d37a-4a22-bc82-6e82187de9c2
Content-Type: application/json

{"type":"monthly-orders","from":"2026-10-01","to":"2026-10-31"}
~~~

Hợp đồng cần quy định:

1. **Phạm vi khóa:** gắn với user/tenant được xác thực, endpoint và loại thao tác. Không lấy kết quả job của tenant khác chỉ vì vô tình trùng key.
2. **Dấu vân tay payload:** cùng khóa và cùng nội dung phải tham chiếu cùng operation; cùng khóa nhưng payload khác trả lỗi, ví dụ `409 Conflict`.
3. **Thao tác nguyên tử:** lưu khóa và tiếp nhận công việc phải chống race khi hai request đồng thời gửi một khóa.
4. **Khi retry:** cùng khóa và payload trả lại URI operation ban đầu, không tạo job mới. API có thể giữ response gốc hoặc trả phản hồi tương đương theo hợp đồng.
5. **Hạn dùng khóa:** có retention rõ. Khi hết hạn, việc gửi lại key có thể tạo job mới; client cần được thông báo về rủi ro.

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v1/operations/op_a71c
Content-Type: application/json

{"id":"op_a71c","status":"RUNNING"}
~~~

Nếu nội dung khác với cùng khóa:

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/idempotency-key-conflict",
  "title": "Idempotency key conflict",
  "status": 409,
  "detail": "Khóa đã được sử dụng cho nội dung yêu cầu khác."
}
~~~

Mẫu lỗi có dạng **Problem Details**. URI trong `type` chỉ là ví dụ; khi công bố thật, hãy cung cấp tài liệu loại lỗi ổn định. Header `Idempotency-Key` phải được tài liệu hóa, không giả định mọi ứng dụng HTTP hoặc Spring tự hiểu và xử lý khóa.

### 7.2. Chống trùng ở tầng worker

Idempotency ở endpoint POST và idempotency của **tác động nghiệp vụ** là hai bài toán. Hàng đợi có thể giao lại message sau timeout, hoặc worker có thể không nhận xác nhận từ đối tác dù đối tác đã xử lý xong.

Ví dụ worker nhập dữ liệu theo SKU cần ràng buộc duy nhất hoặc logic upsert an toàn. Worker thanh toán cần kiểm soát tác động lặp qua mã giao dịch và cơ chế idempotency của nhà cung cấp. Không khẳng định “exactly once” chỉ vì HTTP có key hoặc broker có cơ chế ack; phải đo được tính duy nhất ở kết quả nghiệp vụ.

## 8. Bền vững khi chấp nhận job: tránh trả 202 quá sớm

Luồng dễ lỗi:

~~~text
API nhận POST
  -> trả 202
  -> sau đó mới ghi message vào queue
  -> API crash trước khi ghi

Kết quả: client có URI operation nhưng job không được tiếp nhận thật.
~~~

Một thiết kế đáng tin là **ghi bền vững operation và yêu cầu xử lý** trước khi trả `202`. Nếu database và queue là hai hệ riêng, không thể mặc nhiên giả định transaction xuyên cả hai. Có thể dùng transactional outbox hoặc cơ chế tương đương:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant DB as Operation DB + Outbox
    participant P as Outbox Publisher
    participant Q as Queue
    participant W as Worker
    C->>A: POST + Idempotency-Key
    A->>DB: Transaction: insert operation + outbox
    DB-->>A: Commit thành công
    A-->>C: 202 + Location
    P->>DB: Đọc outbox chưa phát
    P->>Q: Publish job
    Q-->>P: Ack
    P->>DB: Đánh dấu đã publish
    Q-->>W: Giao job, có thể giao lại
    W->>DB: Ghi RUNNING và kết quả cuối
~~~

Outbox khắc phục khoảng trống giữa commit DB và publish, nhưng cần vận hành publisher, giám sát lag, retry và dọn bản ghi. Do message có thể bị publish trùng hoặc giao lại, worker vẫn phải idempotent. Một giải pháp khác cũng chấp nhận được nếu chứng minh được không mất yêu cầu đã nhận và có cơ chế phục hồi.

### 8.1. Operation store nên lưu gì?

- ID ổn định; owner/tenant, loại tác vụ, metadata cần thiết và mã tham chiếu yêu cầu.
- `QUEUED`, `RUNNING`, terminal status, thời điểm nhận, bắt đầu, cập nhật cuối, kết thúc.
- Vị trí kết quả hoặc mã lỗi an toàn để trả client; không lưu bí mật không cần thiết.
- Heartbeat/lease hoặc cơ chế phát hiện tác vụ kẹt; quy tắc chuyển trạng thái không cho `SUCCEEDED` quay thành `RUNNING` vì retry muộn.
- Retention, người có quyền xem/cancel, số lần retry và thông tin audit cần thiết.

Một biến map trạng thái trong bộ nhớ API không đủ khi server có nhiều instance, scale ngang hoặc restart. Dùng kho trạng thái chung cùng quy tắc đồng bộ và xử lý tranh chấp hợp lý.

## 9. Thiết kế client polling an toàn

Poll liên tục có thể gây tải rất lớn: 5.000 client, mỗi client gọi mười lần mỗi giây, tạo **50.000 GET/giây** chỉ để hỏi trạng thái. Polling cần giới hạn và có tín hiệu điều chỉnh.

Quy trình client:

1. POST và kiểm tra status; nếu `201`, xử lý resource mới; nếu `202`, lấy monitor URI theo hợp đồng.
2. Chờ khoảng ban đầu hoặc gợi ý của server; gọi GET monitor với token được phép.
3. Với `200`, đọc `status`: chờ khi `QUEUED/RUNNING`; xử lý lỗi khi `FAILED/CANCELLED`; lấy kết quả khi `SUCCEEDED`.
4. Với `303`, GET Location đích một cách an toàn. Chú ý thư viện HTTP có thể tự theo redirect.
5. Với `429` hoặc `503`, tuân thủ `Retry-After` nếu có và hợp lệ, hoặc backoff có giới hạn và jitter.
6. Với `401/403/404/410`, xử lý quyền hoặc vòng đời resource; không tiếp tục hỏi vô hạn.
7. Có deadline và số lần thử tối đa. Khi người dùng rời ứng dụng, có thể lưu ID operation và tiếp tục sau, thay vì tạo job mới.

Mã giả:

~~~text
response = POST("/v1/reports", body, idempotencyKey)
if response.status == 201:
    handleCreatedResource(response.Location)
    stop
if response.status != 202:
    handleRequestError(response)
    stop

monitorUri = validateAndResolveLocation(response)
delay = initialDelayFromContract()
deadline = now() + maximumWait

while now() < deadline:
    wait(delayWithJitter(delay))
    poll = GET(monitorUri, authorization)

    if poll.status == 303:
        safeResultUri = validateRedirectTarget(poll.Location)
        GET(safeResultUri)
        stop

    if poll.status == 200:
        op = parseOperation(poll.body)
        if op.status == "SUCCEEDED":
            GET(op.result.href)
            stop
        if op.status in ["FAILED", "CANCELLED"]:
            showTerminalState(op)
            stop
        if op.status in ["QUEUED", "RUNNING", "CANCELLING"]:
            delay = cappedBackoff(delay, serverPollingHint)
            continue

    if poll.status in [429, 503]:
        delay = retryAfterOrBackoff(poll)
        continue

    if poll.status in [401, 403, 404, 410]:
        handleAccessOrLifetimeError(poll)
        stop

    handleOtherHttpOrNetworkError(poll)

persistMonitorUriIfPending(monitorUri)
~~~

Lưu ý `Retry-After` theo ngữ nghĩa HTTP có thể là số giây hoặc HTTP-date. `Retry-After` trên `202` trong ví dụ là **quy ước polling của API**, không nên cho rằng mọi client HTTP đều tự động hỗ trợ. Có thể dùng trường `nextPollAfterSeconds` trong body nếu muốn client xử lý độc lập với header, nhưng phải định nghĩa một nguồn ưu tiên để tránh mâu thuẫn.

Nếu dùng ETag/`If-None-Match` cho operation status có thể cache phù hợp, response `304 Not Modified` có thể giảm payload nhưng không giảm số request. Với status nhạy cảm, ưu tiên chính sách cache đúng yêu cầu bảo mật. Webhook/SSE/WebSocket có thể thay thế hoặc bổ sung polling khi cần, nhưng phải xử lý auth, retry, sự kiện bị mất và vẫn có nguồn trạng thái để đối soát.

## 10. Triển khai Java/Spring MVC

Các đoạn code sau tập trung vào **response status và Location**. Những interface nghiệp vụ chỉ mô tả contract; khi chạy thực cần hiện thực persistence, validation, authn/authz, transaction/outbox, queue, xử lý lỗi và cấu hình public base URL.

### 10.1. Tạo đồng bộ với 201

~~~java
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @RequestBody CreateOrderRequest request) {
        // create() kết thúc sau khi đơn được lưu bền vững.
        OrderView created = orderService.create(request);
        URI location = URI.create(
            "https://api.example.test/v1/orders/" + created.id());
        return ResponseEntity.created(location).body(created);
    }
}

record CreateOrderRequest(String customerId) {}
record OrderView(String id, String status) {}

interface OrderService {
    OrderView create(CreateOrderRequest request);
}
~~~

Ví dụ dùng URL cố định để dễ nhìn. Trong hệ thống thật, base URL được cấu hình theo môi trường hoặc suy từ proxy đã được tin cậy; thành phần path phải được encode bằng URI builder phù hợp và ID do server kiểm soát. Đừng nối URL tùy ý do client gửi vào `Location`.

### 10.2. Tạo tác vụ nền với 202

~~~java
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/reports")
public class ReportCommandController {
    private final ReportService reportService;

    public ReportCommandController(ReportService reportService) {
        this.reportService = reportService;
    }

    @PostMapping
    public ResponseEntity<OperationView> start(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody ReportRequest request) {
        // acceptDurably() đảm bảo đã ghi yêu cầu/operation trước
        // khi trả về, và chống trùng key theo hợp đồng.
        OperationView operation = reportService.acceptDurably(key, request);
        URI monitor = URI.create(
            "https://api.example.test/v1/operations/" + operation.id());
        return ResponseEntity.accepted()
            .location(monitor)
            .header(HttpHeaders.RETRY_AFTER, "3")
            .cacheControl(CacheControl.noStore())
            .body(operation);
    }
}

record ReportRequest(String type, String from, String to) {}
record OperationView(String id, String status, String resultHref) {}

interface ReportService {
    OperationView acceptDurably(String key, ReportRequest request);
    OperationView findAuthorized(String id);
}
~~~

Không có transaction phân tán tự động giữa DB và broker khi chỉ gọi `acceptDurably()`. Đây là tên hàm mô tả điều service **phải bảo đảm** bằng một cơ chế như transactional outbox và unique constraint cho khóa idempotency.

### 10.3. GET monitor: đang chạy trả 200, thành công trả 303

~~~java
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/operations")
public class OperationController {
    private final ReportService reportService;

    public OperationController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> get(@PathVariable String id) {
        // Service phải kiểm tra quyền đọc operation này.
        OperationView operation = reportService.findAuthorized(id);

        if ("SUCCEEDED".equals(operation.status())) {
            URI result = URI.create(
                "https://api.example.test" + operation.resultHref());
            return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(result)
                .cacheControl(CacheControl.noStore())
                .build();
        }
        // QUEUED, RUNNING, FAILED, CANCELLED đều là representation
        // hợp lệ của operation: GET thành công => HTTP 200.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(operation);
    }
}
~~~

Đoạn mã chọn **phương án B**: redirect khi SUCCEEDED. `resultHref` phải được server tạo từ dữ liệu đáng tin cậy, không cho phép client nhúng URL tùy ý để tránh open redirect. Nếu chọn phương án A, trả `ResponseEntity.ok().body(operation)` ngay cả khi `SUCCEEDED`. Production code còn phải xử lý operation không tồn tại, không đủ quyền, hết hạn, lỗi service và việc result không còn tồn tại.

### 10.4. Kiểm tra HTTP bằng MockMvc

Minh họa các assertion sau khi mock service phù hợp:

~~~java
// Cần cấu hình mockMvc, orderService, reportService và các
// đối tượng trả về trong một bộ test Spring MVC thực tế.
mockMvc.perform(post("/v1/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"customerId\":\"cus_82\"}"))
    .andExpect(status().isCreated())
    .andExpect(header().string(HttpHeaders.LOCATION,
        "https://api.example.test/v1/orders/ord_916"));

mockMvc.perform(post("/v1/reports")
        .header("Idempotency-Key", "key-1")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"type\":\"monthly-orders\",\"from\":\"2026-10-01\",\"to\":\"2026-10-31\"}"))
    .andExpect(status().isAccepted())
    .andExpect(header().string(HttpHeaders.LOCATION,
        "https://api.example.test/v1/operations/op_a71c"));
~~~

Kiểm tra controller chỉ xác nhận contract HTTP. Test tích hợp còn phải chứng minh nhận công việc bền vững, idempotency khi retry đồng thời, quyền truy cập và tính nhất quán của kết quả worker.

## 11. Mô tả bằng OpenAPI

OpenAPI giúp công bố header, status và schema thay vì chỉ mô tả response `200` chung. Ví dụ rút gọn theo OpenAPI 3.1 cho mô hình `202` + monitor:

~~~yaml
openapi: 3.1.0
info:
  title: Report Export API
  version: 1.0.0
paths:
  /v1/reports:
    post:
      summary: Tiếp nhận yêu cầu xuất báo cáo
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema: {type: string}
          description: Khóa chống trùng theo user và payload
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [type, from, to]
              properties:
                type: {type: string}
                from: {type: string, format: date}
                to: {type: string, format: date}
      responses:
        '202':
          description: Công việc đã được nhận, còn chờ xử lý
          headers:
            Location:
              required: true
              description: URI operation monitor của API này
              schema: {type: string, format: uri}
            Retry-After:
              description: Gợi ý số giây chờ trước khi poll
              schema: {type: string}
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '409':
          description: Khóa chống trùng xung đột với nội dung khác
        '422':
          description: Dữ liệu đầu vào không thể xử lý
        '429':
          description: Quá giới hạn yêu cầu
  /v1/operations/{id}:
    get:
      summary: Đọc tiến độ và trạng thái tác vụ
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Operation đang chạy hoặc kết thúc thất bại/hủy
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '303':
          description: Operation thành công, GET URI kết quả
          headers:
            Location:
              required: true
              description: URI báo cáo đã tạo
              schema: {type: string, format: uri}
        '404':
          description: Không tìm thấy hoặc không công bố operation
        '410':
          description: Operation đã hết thời gian theo dõi
components:
  schemas:
    Operation:
      type: object
      required: [id, status]
      properties:
        id: {type: string}
        status:
          type: string
          enum: [QUEUED, RUNNING, CANCELLING, SUCCEEDED, FAILED, CANCELLED]
        submittedAt: {type: string, format: date-time}
        finishedAt: {type: string, format: date-time}
        resultHref: {type: string}
        error:
          type: object
          properties:
            code: {type: string}
            message: {type: string}
~~~

Ví dụ chọn **phương án redirect `303`** khi SUCCEEDED. Nếu chọn `200` và body `SUCCEEDED`, thay response description và xử lý client tương ứng. Trong OpenAPI thực tế cần khai báo `securitySchemes`, authentication, các response lỗi theo Problem Details, retention, idempotency và cách polling. OpenAPI mô tả hợp đồng nhưng không tự triển khai queue, giao dịch hay retry.

## 12. Bảo mật và quyền truy cập

Biết được operation ID **không đồng nghĩa** được phép xem operation đó. URI monitor có thể xuất hiện trong lịch sử trình duyệt, log, ticket hoặc hệ thống tracing; operation có thể lộ nội dung yêu cầu và dữ liệu nhạy cảm.

- Bắt buộc xác thực ở endpoint tạo công việc, theo dõi và tải resource kết quả.
- Kiểm tra phân quyền theo **owner/tenant và loại dữ liệu** khi GET monitor và GET result; quyền lúc tạo job không tự động cấp quyền xem mãi mãi.
- Sử dụng ID không chứa PII và khó đoán; vẫn cần authorization, không chỉ dựa vào tính bí mật của ID.
- Che token, SQL, stack trace, thông tin hệ thống nội bộ và dữ liệu người dùng khác khỏi body lỗi và log.
- Xem xét `Cache-Control: no-store` cho monitor nhạy cảm; không đặt dữ liệu tenant vào shared cache công khai.
- Giới hạn quota tạo job, dung lượng input, số job song song, tần suất polling và thời gian xử lý để tránh lạm dụng tài nguyên.
- Chỉ redirect tới result URI từ danh mục tin cậy; không chuyển token sang domain khác một cách tùy tiện.
- Công bố thời hạn lưu operation, log và tệp kết quả, phù hợp loại dữ liệu và yêu cầu nghiệp vụ.

Một số API có thể trả `404` thay vì `403` để không tiết lộ một ID thuộc người khác. Đây là lựa chọn hợp đồng/phân quyền, cần nhất quán ở cả monitor và result.

### 12.1. Quan sát và vận hành

| Metric | Mục đích |
|---|---|
| Tỷ lệ tiếp nhận `202` và lỗi nhận việc | Biết hệ thống có thực sự tiếp nhận yêu cầu bền vững không |
| Queue depth và tuổi message cũ nhất | Phát hiện tắc nghẽn worker |
| Thời gian từ QUEUED đến RUNNING | Đánh giá thời gian chờ |
| Thời gian từ RUNNING đến terminal status | Đánh giá năng lực xử lý |
| Tỷ lệ SUCCEEDED/FAILED/CANCELLED | Đánh giá kết quả nghiệp vụ, không chỉ HTTP status |
| Số operation không cập nhật quá ngưỡng | Phát hiện worker bị kẹt hoặc mất heartbeat |
| Số GET monitor và tỷ lệ 429 | Phát hiện polling quá dày |

Gắn correlation ID giữa request, operation, queue, worker và report. Có cảnh báo theo thời gian chờ quá mục tiêu, kết quả thất bại tăng và outbox không được xử lý; tránh cảnh báo chỉ dựa trên CPU mà bỏ lỡ job bị kẹt.

## 13. Kiểm thử hợp đồng và tình huống lỗi

| Kịch bản | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Tạo đơn thành công | POST hợp lệ | `201`, Location hợp lệ, GET resource đúng theo hợp đồng |
| Tạo báo cáo nền | POST hợp lệ | `202`, operation được lưu và Location trỏ đúng monitor |
| Đang chờ/chạy | GET operation | `200` với QUEUED/RUNNING, chưa có kết quả giả |
| Thành công | Worker xong | `200` + result link hoặc `303` + Location tùy contract |
| Thất bại sau 202 | Worker gặp lỗi | `200` + FAILED/error an toàn khi GET monitor |
| Request sai | JSON lỗi/ngữ nghĩa không được chấp nhận | `400`/`422` phù hợp, không tạo job |
| Retry cùng key và payload | Client mất response rồi POST lại | Cùng operation, không tạo job mới |
| Key trùng nhưng payload khác | POST với key đã dùng | `409` hoặc lỗi hợp đồng phù hợp |
| Hai POST cùng key đồng thời | Race condition | Chỉ một job logic, có unique constraint/transaction |
| Worker nhận message lặp | Queue redelivery | Không nhân đôi tác động nghiệp vụ |
| API crash sau commit | Response 202 bị mất | Client retry có thể tìm lại operation cũ |
| Publish queue thất bại | DB đã lưu operation | Outbox/recovery phát lại, không mất công việc |
| Worker chết giữa chừng | Không có heartbeat | Có timeout, retry hoặc xử lý job kẹt |
| User khác xem monitor | Không đủ quyền | `403` hoặc `404` theo chính sách, không lộ dữ liệu |
| Operation hết hạn | GET sau retention | `410` nếu có tombstone, hoặc `404` theo hợp đồng |
| Poll quá nhanh | Vượt quota | `429`, client backoff |
| Result đã xóa | Monitor còn lịch sử | Thông báo rõ kết quả không còn và hướng xử lý |

### 13.1. Thử với curl

Tạo đơn:

~~~bash
curl -i -X POST "https://api.example.test/v1/orders" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"customerId":"cus_82","items":[{"sku":"SKU-101","quantity":2}]}'
~~~

Tạo report bất đồng bộ:

~~~bash
curl -i -X POST "https://api.example.test/v1/reports" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Idempotency-Key: demo-report-001" \
  -H "Content-Type: application/json" \
  -d '{"type":"monthly-orders","from":"2026-10-01","to":"2026-10-31"}'
~~~

GET operation sau khi nhận Location:

~~~bash
curl -i "https://api.example.test/v1/operations/op_a71c" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
~~~

Không dùng `curl -L` ở bước đầu nếu muốn quan sát `303` và `Location` trung gian; khi có ý định theo redirect, kiểm tra URI đích, quyền và cách client xử lý Authorization khi khác origin. Domain, token và ID chỉ mang tính minh họa.

## 14. Phản mẫu thường gặp

| Phản mẫu | Vì sao sai | Cách sửa |
|---|---|---|
| Tạo xong đơn nhưng trả `200 {"success":true}` không có URI | Client thiếu đường dẫn tài nguyên mới | Trả `201` + Location |
| Trả `201` khi công việc chính vẫn chưa hoàn tất | Client tưởng kết quả đã có | Dùng `202` + monitor khi phù hợp |
| Trả `202` mà không có cách theo dõi | Client không biết tác vụ thành công hay thất bại | Công bố operation resource và contract |
| Location của `202` trỏ tới file còn chưa tồn tại | GET có thể 404 không rõ nghĩa | Location trỏ monitor; kết quả xuất hiện sau |
| GET monitor trả `500` chỉ vì worker thất bại | Trộn lỗi HTTP với lỗi nghiệp vụ nền | `200` + FAILED nếu GET monitor vẫn thành công |
| Trả `202` trước khi lưu bền vững | Công việc có thể mất khi API crash | Ghi transaction/outbox trước khi đáp |
| Poll mỗi 100 ms vô hạn | Tăng tải và chi phí | Backoff, jitter, quota, deadline |
| Idempotency chỉ ở POST, không ở worker | Message lặp vẫn gây tác động đôi | Ràng buộc idempotent trong xử lý nền |
| Monitor chỉ lưu trong memory API | Restart/load balance làm mất trạng thái | Dùng operation store bền vững |
| URI monitor cho phép truy cập vô danh | Lộ tiến độ, input, result và lỗi | Authn/authz theo tenant trên mọi endpoint |
| Dùng Content-Location thay Location | Sai ngữ nghĩa liên kết | Dùng Location đúng chức năng |
| Redirect theo URL do client gửi | Rủi ro open redirect hoặc lộ credential | Chỉ tạo Location từ nguồn tin cậy |

## 15. Bài thực hành: nhập sản phẩm hàng loạt

**Bối cảnh:** Endpoint quản trị `POST /v1/imports` nhận một tệp CSV gồm 100.000 sản phẩm. Việc nhập có thể kéo dài mười lăm phút. Một số dòng không hợp lệ; người dùng có thể mất kết nối và muốn theo dõi tiến độ. API và worker có nhiều instance.

**Yêu cầu làm bài:**

1. Thiết kế resource map: endpoint POST nhập file, URI monitor và URI báo cáo kết quả.
2. Viết response `202` gồm `Location`, operation ID, trạng thái đầu tiên, policy polling và thời hạn theo dõi.
3. Định nghĩa state machine gồm QUEUED, RUNNING, SUCCEEDED, FAILED và trạng thái phục vụ hủy. Nêu điều kiện chuyển giữa các trạng thái.
4. Quyết định cách biểu diễn **thành công một phần** khi 1.000/100.000 dòng lỗi. Có thể chọn all-or-nothing hoặc partial success nhưng phải ghi rõ hợp đồng nghiệp vụ.
5. Đề xuất idempotency cho lần POST và cho mỗi dòng/SKU khi worker retry.
6. Nêu chính sách lưu giữ CSV, log, DLQ và báo cáo lỗi; thiết kế phân quyền khi xem operation/result.
7. Viết ít nhất tám phép kiểm trong ma trận mục 13, bao phủ status, Location, retry, quyền và lỗi worker.

**Một phương án mẫu:**

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v1/operations/op_import_123
Content-Type: application/json

{"id":"op_import_123","status":"QUEUED"}
~~~

Sau khi xử lý theo chính sách cho phép lưu các dòng hợp lệ:

~~~json
{
  "id": "op_import_123",
  "status": "SUCCEEDED",
  "outcome": "PARTIAL_SUCCESS",
  "totalRows": 100000,
  "createdRows": 99000,
  "failedRows": 1000,
  "result": {"href": "/v1/import-results/ir_123"}
}
~~~

`outcome` là **kết quả nghiệp vụ**, không phải HTTP status. Có hệ thống dùng terminal state PARTIALLY_SUCCEEDED thay vì SUCCEEDED + outcome; cả hai có thể hợp lý nếu contract và client thống nhất. Trước khi chọn, phải hỏi doanh nghiệp: được phép nhập một phần không, thế nào là dòng trùng SKU, làm sao hoàn tác, có cần duyệt từng đợt nhập và giữ báo cáo lỗi bao lâu?

### 15.1. Câu hỏi phản biện

- Nếu người dùng bấm tải file CSV xong nhưng API không trả response, retry POST có tạo hai operation không? Phải kiểm tra khóa chống trùng ở đâu?
- Nếu worker chết ở dòng 70.000, có thể chạy lại phần còn lại và không nhập trùng 69.999 dòng đầu không?
- Nếu operation trả SUCCEEDED nhưng result file đã hết hạn, client xử lý thế nào?
- Nếu người dùng bị thu hồi quyền quản trị khi job đang RUNNING, họ có được tải kết quả không? Đầu ra có chứa dữ liệu nhạy cảm không?
- Nếu quá nhiều client poll, API có rate limit mà không ảnh hưởng các lệnh tạo tác vụ quan trọng không?

## 16. Checklist trước khi công bố API

### Tạo tài nguyên

- [ ] Resource chính, điều kiện hoàn tất và URI chuẩn đã được xác định.
- [ ] `201 Created` chỉ được dùng theo đúng ý nghĩa tạo resource; Location chỉ URI chính.
- [ ] URI đọc được theo hợp đồng, không chứa bí mật; có chính sách nhất quán sau ghi.
- [ ] Body, nếu có, được mô tả đúng schema và không mâu thuẫn Location.

### Xử lý nền

- [ ] `202 Accepted` chỉ trả sau khi job được tiếp nhận bền vững.
- [ ] URI monitor và cách lấy URI được tài liệu hóa; Location của 202 được định nghĩa rõ là quy ước API.
- [ ] Operation có trạng thái terminal thành công/thất bại/hủy và liên kết kết quả hoặc mã lỗi.
- [ ] Chọn và mô tả rõ phương án `200` + result link hoặc `303` + Location khi xong.
- [ ] Idempotency khi POST, retry worker, đồng thời và sau mất kết nối đã được xử lý.
- [ ] Retention, `404/410`, hủy tác vụ và điều kiện tác vụ kẹt có hợp đồng rõ ràng.

### Client, bảo mật và vận hành

- [ ] OpenAPI định nghĩa status, Location header, schema operation, lỗi và quy tắc polling.
- [ ] Client có backoff, jitter, giới hạn thời gian, handling `429/503` và `Retry-After` phù hợp.
- [ ] Cả operation và result có xác thực, phân quyền, chính sách cache và retention.
- [ ] Log/metric theo dõi được tỷ lệ job hoàn tất, thất bại, đọng queue và polling quá mức.
- [ ] Test đủ cả trường hợp POST trùng, queue lỗi, worker crash, quyền bị từ chối và result hết hạn.

## 17. Ghi nhớ

**`201 Created`** xác nhận tài nguyên chính đã được tạo; `Location` thường chỉ URI tài nguyên đó. **`202 Accepted`** xác nhận yêu cầu được tiếp nhận nhưng kết quả xử lý vẫn chưa chắc chắn; một API REST thường dùng `Location` trỏ tới URI **operation monitor** để client có nơi theo dõi. Đây là **quy ước thiết kế cần ghi rõ**, không phải nghĩa bắt buộc riêng của mã `202`.

Khi công việc hoàn tất, server có thể trả **`200 OK` với liên kết tới kết quả** hoặc **`303 See Other` với `Location` trỏ tới resource kết quả**. Những mã trạng thái chỉ là một phần hợp đồng; API đáng tin cậy còn cần lưu việc bền vững, idempotency, trạng thái có thể quan sát, lỗi ổn định, giới hạn polling và phân quyền nhất quán.
