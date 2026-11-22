# Tài nguyên tính toán, báo cáo và kết quả truy vấn

## Mục tiêu bài học

Trong chương **Mô hình tài nguyên** của module **INTEGRATION_API_REST**, bài học này giải thích cách thiết kế REST API cho những thứ không tương ứng trực tiếp với một hàng dữ liệu: một phép tính, một lần chạy báo cáo, một truy vấn đã lưu hoặc tập kết quả được tạo ra từ dữ liệu khác.

Sau bài học, bạn có thể:

- Phân biệt định nghĩa phép tính, yêu cầu thực thi, lần thực thi và kết quả.
- Chọn giữa xử lý đồng bộ, tài nguyên tác vụ và tập kết quả có danh tính riêng.
- Thiết kế URI, phương thức HTTP và phản hồi cho một báo cáo chạy bất đồng bộ.
- Xác định hợp đồng về thời điểm dữ liệu, phân trang, cache, quyền truy cập và thời hạn lưu giữ.
- Ánh xạ hợp đồng đó sang các lớp giao tiếp Java/Spring và những tình huống cần kiểm thử.

Các ví dụ dùng hệ thống bán hàng: người dùng yêu cầu tổng hợp doanh thu theo ngày cho một khoảng thời gian. Tên URI, mã lỗi nghiệp vụ và chính sách lưu giữ dưới đây là lựa chọn thiết kế của hệ thống minh họa.

## 1. Tài nguyên không bắt buộc phải là bản ghi trong cơ sở dữ liệu

Một tài nguyên REST là một khái niệm có thể được định danh và tương tác qua một giao diện thống nhất. Nó có thể là đơn hàng đã lưu, nhưng cũng có thể là báo cáo doanh thu, kết quả định giá, dự toán vận chuyển hoặc tập kết quả tìm kiếm.

Ví dụ:

~~~http
GET /shipping-quotes?origin=SGN&destination=HAN&weightGrams=1200
~~~

Server có thể tính giá từ nhiều bảng và một dịch vụ vận chuyển bên ngoài. Việc không có bảng tên `shipping_quotes` không làm cho báo giá mất tư cách tài nguyên. Điều cần xác định là client đang đọc biểu diễn nào, kết quả có được giữ ổn định hay không và khi gọi lại thì điều gì có thể thay đổi.

Ngược lại, chuyển một động từ thành danh từ không tự làm API trở nên rõ ràng:

~~~http
POST /calculations
~~~

Nếu request chỉ chứa một trường `operation` với hàng chục ý nghĩa không liên quan, còn response luôn là một đối tượng không có schema cụ thể, client vẫn khó hiểu và khó kiểm thử. Tài nguyên cần có ý nghĩa nghiệp vụ, đầu vào, vòng đời và biểu diễn rõ ràng.

### Bốn lớp khái niệm thường bị gộp chung

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| Định nghĩa | Tính cái gì, theo quy tắc nào? | Báo cáo tổng doanh thu đã thanh toán, phiên bản 3 |
| Yêu cầu thực thi | Người dùng muốn áp dụng bộ tham số nào? | Doanh thu tháng 10, múi giờ Asia/Ho_Chi_Minh |
| Lần thực thi | Công việc đã chạy đến đâu? | Lần chạy `rpt_7f3a` đang xử lý |
| Kết quả | Đã tạo ra dữ liệu hoặc tệp nào? | Các dòng tổng hợp và một tệp CSV |

Không phải API nào cũng cần tạo URI riêng cho cả bốn lớp. Với phép tính rất nhỏ, request và response đồng bộ là đủ. Việc tách lớp trở nên hữu ích khi cần theo dõi tiến trình, chạy lại, chia sẻ, tải tệp, phân trang hoặc kiểm toán.

Một định nghĩa có thể tạo ra nhiều lần chạy. Hai lần chạy dùng cùng tham số cũng chưa chắc cho cùng kết quả, vì dữ liệu nguồn hoặc phiên bản quy tắc có thể đã thay đổi.

## 2. Chọn mô hình theo hành vi cần cung cấp

| Tình huống | Mô hình phù hợp | Đặc điểm hợp đồng |
|---|---|---|
| Phép tổng hợp nhanh trên dữ liệu hiện tại | `GET /sales-summary?...` | Đọc một biểu diễn tính toán; có thể thay đổi khi dữ liệu đổi |
| Phép tính cần đầu vào có cấu trúc lớn | `POST /shipping-quotes` | Body có schema rõ; trả kết quả ngay hoặc tạo báo giá có ID |
| Báo cáo chạy lâu, cần theo dõi | `POST /report-runs` | Tạo lần chạy; trả URI để theo dõi |
| Bộ lọc cần lưu và dùng lại | `POST /saved-queries` | Lưu định nghĩa truy vấn, chưa nhất thiết thực thi |
| Tập kết quả cần ổn định qua nhiều lần đọc | `POST /query-runs` rồi đọc kết quả | Tách thời điểm chạy khỏi thời điểm đọc từng trang |

### GET phù hợp khi client chỉ yêu cầu đọc

Một phép tổng hợp nhỏ có thể được cung cấp như sau:

~~~http
GET /sales-summary?from=2026-10-01&to=2026-11-01&currency=VND
Accept: application/json
~~~

Phản hồi thành công có thể là `200 OK` với tổng doanh thu và thời điểm tính.

GET cần giữ ngữ nghĩa an toàn: client không yêu cầu thay đổi trạng thái nghiệp vụ. Server vẫn có thể ghi log, tạo cache nội bộ hoặc thu thập số liệu vận hành. Những hoạt động phụ đó khác với việc GET ngầm đặt một công việc nghiệp vụ vào hàng đợi, phát sinh phí hoặc gửi báo cáo cho người khác.

Phép tính bằng GET cũng có thể tốn tài nguyên. Cần giới hạn khoảng thời gian, số nhóm và chi phí truy vấn; ngữ nghĩa an toàn không đồng nghĩa với chi phí xử lý bằng không.

### POST phù hợp khi cần gửi lệnh xử lý hoặc tạo tài nguyên

Khi đầu vào phức tạp, POST có thể mang một biểu thức hoặc đối tượng tham số trong body. Không nên phụ thuộc vào body của GET để truyền đầu vào vì nhiều thành phần trung gian không hỗ trợ nó theo cách client mong đợi.

POST không bắt buộc phải ghi một hàng dữ liệu mới. Nó có thể yêu cầu server xử lý nội dung request. Tuy nhiên, nếu kết quả cần được đọc lại hoặc tham chiếu từ nơi khác, tạo một tài nguyên có URI thường giúp hợp đồng dễ sử dụng hơn.

Với báo cáo chạy lâu, thay vì giữ một kết nối mở trong nhiều phút, client tạo một lần chạy và theo dõi trạng thái bằng GET.

## 3. Mô hình báo cáo doanh thu xuyên suốt

Giả sử hệ thống cần:

- Tổng hợp doanh thu đã thanh toán theo ngày.
- Chạy trên khoảng thời gian có giới hạn.
- Cho phép người dùng đóng trang rồi quay lại xem kết quả.
- Cho phép đọc từng trang và tải CSV.
- Giữ kết quả trong bảy ngày.

Một mô hình tài nguyên có thể là:

| Tài nguyên | URI minh họa | Trách nhiệm |
|---|---|---|
| Định nghĩa báo cáo | `/report-definitions/revenue-summary` | Mô tả tham số, cột dữ liệu và quy tắc tổng hợp |
| Tập lần chạy | `/report-runs` | Nhận yêu cầu tạo và liệt kê những lần chạy được phép xem |
| Một lần chạy | `/report-runs/rpt_7f3a` | Cung cấp trạng thái, thời điểm, phiên bản định nghĩa và liên kết |
| Kết quả một lần chạy | `/report-runs/rpt_7f3a/result` | Cung cấp metadata và các dòng kết quả |
| Một tệp kết quả | `/report-runs/rpt_7f3a/artifacts/art_csv1` | Cung cấp nội dung tệp CSV đã tạo |

URI của result nằm dưới một lần chạy để thể hiện quan hệ sở hữu. Không cần đưa toàn bộ điều kiện lọc vào đường dẫn hoặc tạo URI sâu theo từng bảng nguồn.

Trong thiết kế này, mỗi lần chạy có tối đa một kết quả JSON logic và có thể có nhiều tệp xuất. Nếu nghiệp vụ cho phép nhiều tập kết quả trong một lần chạy, mô hình có thể đổi thành collection `/results` với ID riêng cho từng tập.

### Luồng tổng quát

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant W as Worker
    C->>A: POST /report-runs
    A-->>C: 202 Accepted + Location
    A->>W: Giao công việc đã tiếp nhận
    C->>A: GET /report-runs/rpt_7f3a
    A-->>C: 200, status=RUNNING
    W->>A: Công bố kết quả và trạng thái SUCCEEDED
    C->>A: GET /report-runs/rpt_7f3a
    A-->>C: 200, liên kết result
    C->>A: GET /report-runs/rpt_7f3a/result
    A-->>C: 200, metadata và các dòng
~~~

Hình chỉ mô tả hợp đồng bên ngoài và vai trò xử lý nền. Nó không yêu cầu worker gọi HTTP ngược vào API; triển khai thực tế có thể dùng cơ sở dữ liệu, hàng đợi hoặc một kho trạng thái chung.

## 4. Tạo lần chạy và diễn đạt việc tiếp nhận

~~~http
POST /report-runs HTTP/1.1
Content-Type: application/json
Accept: application/json
Idempotency-Key: revenue-oct-2026-request-01

{
  "reportDefinitionId": "revenue-summary",
  "parameters": {
    "fromInclusive": "2026-09-30T17:00:00Z",
    "toExclusive": "2026-10-31T17:00:00Z",
    "timeZone": "Asia/Ho_Chi_Minh",
    "currency": "VND",
    "groupBy": "DAY"
  }
}
~~~

Khoảng thời gian trên tương ứng từ đầu ngày 01/10 đến đầu ngày 01/11/2026 theo múi giờ đã chọn. Quy ước đầu vào là `[fromInclusive, toExclusive)`: lấy mốc đầu, bỏ mốc cuối. Hai kỳ liên tiếp vì thế không cùng tính một giao dịch ở ranh giới.

Quy tắc tổng hợp của định nghĩa báo cáo cũng phải nêu rõ: lấy thời điểm thanh toán hay thời điểm tạo đơn, xử lý hoàn tiền thế nào, loại trạng thái nào và làm tròn ở bước nào. Chỉ một cặp ngày không đủ diễn đạt ý nghĩa của con số doanh thu.

Ví dụ phản hồi tiếp nhận:

~~~http
HTTP/1.1 202 Accepted
Location: /report-runs/rpt_7f3a
Content-Type: application/json
Cache-Control: no-store

{
  "id": "rpt_7f3a",
  "status": "QUEUED",
  "definitionVersion": 3,
  "submittedAt": "2026-11-02T02:00:00Z",
  "pollAfterSeconds": 3,
  "links": {
    "self": "/report-runs/rpt_7f3a"
  }
}
~~~

`202 Accepted` chỉ xác nhận yêu cầu đã được chấp nhận để xử lý; nó không bảo đảm báo cáo sẽ thành công. `Location` trong hợp đồng này trỏ đến tài nguyên theo dõi. `pollAfterSeconds` là gợi ý riêng của API để client tránh hỏi quá dày.

### Phân biệt 200, 201 và 202

| Mã | Khi phù hợp |
|---|---|
| `200 OK` | Phép tính đồng bộ đã hoàn tất và body chứa kết quả |
| `201 Created` | Request đã hoàn tất việc tạo tài nguyên mới; `Location` chỉ tài nguyên được tạo |
| `202 Accepted` | Request đã được nhận nhưng phần xử lý được yêu cầu chưa hoàn tất |

Nếu hợp đồng của POST chỉ là “tạo một tài nguyên lần chạy”, `201` vẫn có thể phù hợp dù tài nguyên đó đang ở trạng thái chờ. Ví dụ xuyên suốt chọn `202` vì request được diễn đạt như yêu cầu tạo và thực thi báo cáo chưa hoàn tất. Hãy thống nhất lựa chọn và tài liệu hóa; không suy rằng mọi phản hồi có ID đều phải dùng `201`.

Trước khi trả `202`, hệ thống cần ghi nhận yêu cầu theo cơ chế đủ bền để phục hồi khi tiến trình lỗi. Nếu ghi dữ liệu và gửi hàng đợi ở hai hệ thống khác nhau, cần xử lý khoảng hở giữa hai thao tác, chẳng hạn bằng transactional outbox. Một ID chỉ nằm trong bộ nhớ của một tiến trình không đủ làm lời hứa theo dõi đáng tin cậy.

## 5. Trạng thái của lần chạy và trạng thái HTTP

Vòng đời cơ bản:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> RUNNING
    QUEUED --> FAILED
    RUNNING --> SUCCEEDED
    RUNNING --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

`FAILED` từ hàng đợi có thể xảy ra khi hệ thống xác định công việc không thể bắt đầu sau chính sách thử lại. Nếu hỗ trợ hủy, có thể bổ sung các trạng thái như `CANCEL_REQUESTED` và `CANCELLED`, nhưng phải định nghĩa rõ việc chấp nhận yêu cầu hủy khác với việc công việc đã dừng.

Một lần chạy thành công:

~~~json
{
  "id": "rpt_7f3a",
  "status": "SUCCEEDED",
  "definitionVersion": 3,
  "submittedAt": "2026-11-02T02:00:00Z",
  "startedAt": "2026-11-02T02:00:01Z",
  "completedAt": "2026-11-02T02:00:08Z",
  "snapshotId": "snap_86",
  "dataAsOf": "2026-11-02T01:59:00Z",
  "resultExpiresAt": "2026-11-09T02:00:08Z",
  "links": {
    "self": "/report-runs/rpt_7f3a",
    "result": "/report-runs/rpt_7f3a/result",
    "csv": "/report-runs/rpt_7f3a/artifacts/art_csv1"
  }
}
~~~

Chỉ công bố `SUCCEEDED` sau khi kết quả cần thiết đã sẵn sàng để đọc. Nếu CSV được tạo sau kết quả JSON, hãy mô hình hóa việc xuất CSV bằng một tài nguyên riêng hoặc công bố trạng thái riêng của tệp; đừng coi một liên kết chưa hoạt động là tệp đã có.

Không bắt buộc phải có phần trăm tiến độ. Nếu không biết tổng khối lượng, một giai đoạn như `READING_SOURCE` hoặc `AGGREGATING` trung thực hơn con số tăng giả. Nếu cung cấp tiến độ, phải nêu nó đo công việc nào và có thể thay đổi ra sao.

### Công việc thất bại không có nghĩa GET phải trả 500

~~~http
GET /report-runs/rpt_failed1 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id": "rpt_failed1",
  "status": "FAILED",
  "completedAt": "2026-11-02T02:00:06Z",
  "error": {
    "code": "SOURCE_TIMEOUT",
    "message": "Không đọc được nguồn dữ liệu trong thời gian cho phép.",
    "retryable": true
  },
  "links": {
    "self": "/report-runs/rpt_failed1"
  }
}
~~~

HTTP `200` ở đây nói rằng thao tác đọc tài nguyên lần chạy thành công. Trường `status` nói rằng công việc nghiệp vụ bên trong đã thất bại. `500` chỉ phù hợp khi chính thao tác HTTP gặp lỗi server tương ứng, không dùng để thay cho mọi trạng thái `FAILED`.

Nếu cho phép chạy lại, client tạo một lần chạy mới. Có thể thêm `retryOf` để liên kết lịch sử; không nên xóa dấu vết thất bại bằng cách âm thầm biến cùng một ID thành một lần chạy khác.

## 6. Kết quả cần có hợp đồng dữ liệu riêng

Kết quả báo cáo không nên chỉ là một mảng số thiếu ngữ cảnh. Client cần biết đơn vị, khoảng thời gian, cách chia nhóm và thời điểm dữ liệu được chốt.

~~~http
GET /report-runs/rpt_7f3a/result?limit=2 HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, max-age=60
ETag: "rpt_7f3a-result-page1-v1"

{
  "runId": "rpt_7f3a",
  "snapshotId": "snap_86",
  "definitionVersion": 3,
  "dataAsOf": "2026-11-02T01:59:00Z",
  "period": {
    "fromInclusive": "2026-09-30T17:00:00Z",
    "toExclusive": "2026-10-31T17:00:00Z",
    "timeZone": "Asia/Ho_Chi_Minh"
  },
  "currency": "VND",
  "groupBy": "DAY",
  "totals": {
    "paidOrderCount": 142,
    "revenue": "125000000"
  },
  "rows": [
    {
      "date": "2026-10-01",
      "paidOrderCount": 8,
      "revenue": "6000000"
    },
    {
      "date": "2026-10-02",
      "paidOrderCount": 10,
      "revenue": "8500000"
    }
  ],
  "page": {
    "limit": 2,
    "nextCursor": "opaque-page-token-2"
  },
  "links": {
    "next": "/report-runs/rpt_7f3a/result?limit=2&cursor=opaque-page-token-2"
  }
}
~~~

Trong ví dụ này:

- `totals` là tổng của toàn bộ kết quả, không phải tổng hai dòng trên trang hiện tại.
- `revenue` là chuỗi thập phân theo đơn vị tiền tệ khai báo. Đây là quyết định của hợp đồng nhằm tránh client tự chuyển sang số dấu phẩy động rồi mất độ chính xác.
- `date` là ngày lịch trong `timeZone`; nó không phải một thời điểm UTC bị lược bỏ phần giờ.
- Kết quả có một dòng cho mỗi ngày trong kỳ, kể cả ngày không phát sinh doanh thu. Một hệ thống chọn bỏ ngày rỗng phải nói rõ điều đó.
- Báo cáo này chỉ cộng các khoản cùng `currency`. Nếu có chuyển đổi tiền tệ, phải thêm quy tắc và thời điểm tỷ giá, không cộng trực tiếp các số tiền khác đơn vị.

Phía Java nên dùng `BigDecimal` cho phép tính tiền, với quy tắc làm tròn được xác định trong định nghĩa báo cáo. Việc serialize thành chuỗi hay JSON number cần được thống nhất với client; đổi kiểu giữa các response là phá vỡ hợp đồng.

### Ba loại thời điểm không thể thay thế cho nhau

| Thông tin | Ý nghĩa |
|---|---|
| Khoảng `fromInclusive` đến `toExclusive` | Chọn các sự kiện nghiệp vụ thuộc kỳ nào |
| `dataAsOf` | Dữ liệu nguồn được nhìn nhận hoặc chốt đến thời điểm nào |
| `completedAt` | Hệ thống hoàn tất xử lý vào lúc nào |

Ví dụ, một khoản hoàn tiền nhập muộn vào ngày 03/11 có thể làm thay đổi báo cáo tháng 10 khi chạy lại ngày 04/11. Hai báo cáo vẫn cùng kỳ nghiệp vụ nhưng khác thời điểm dữ liệu.

`dataAsOf` phải phản ánh đúng cơ chế nguồn. Trong kho dữ liệu có độ trễ, nó có thể là watermark đã đồng bộ. Chỉ ghi thời điểm bắt đầu chạy vào trường này không tự tạo ra tính nhất quán snapshot.

Nếu cần khả năng tái lập, lưu phiên bản định nghĩa, bộ tham số đã chuẩn hóa và danh tính snapshot hoặc phiên bản dữ liệu nguồn. Chỉ lưu SQL và thời gian chạy chưa chắc đủ để dựng lại kết quả sau khi nguồn đã thay đổi.

## 7. Kết quả truy vấn hiện tại và tập kết quả cố định

### Đọc truy vấn hiện tại

~~~http
GET /orders?status=PAID&sort=paidAt,id&limit=50
~~~

Đây thường là một collection được lọc tại thời điểm request. Trang sau có thể được đọc khi dữ liệu đã đổi. API phải xác định mức nhất quán mà client có thể trông đợi.

### Lưu định nghĩa truy vấn

~~~http
POST /saved-queries
Content-Type: application/json

{
  "name": "Đơn đã thanh toán",
  "entity": "orders",
  "filters": [
    {
      "field": "status",
      "operator": "EQ",
      "value": "PAID"
    }
  ],
  "sort": [
    { "field": "paidAt", "direction": "ASC" },
    { "field": "id", "direction": "ASC" }
  ]
}
~~~

Tài nguyên này lưu ý định truy vấn. Nó chưa phải bản sao dữ liệu. Chạy lại saved query có thể nhận các đơn hàng khác nếu nguồn đã thay đổi.

Một DSL truy vấn cần giới hạn trường, toán tử và độ phức tạp. Không nhận tùy ý tên bảng, tên cột hay đoạn SQL rồi ghép chuỗi để thực thi.

### Tạo một lần chạy truy vấn

~~~http
POST /query-runs
Content-Type: application/json

{
  "savedQueryId": "sq_paid_orders",
  "savedQueryVersion": 4
}
~~~

Nếu API hứa kết quả ổn định, lần chạy phải gắn với một snapshot hoặc một tập kết quả đã được vật hóa. Sau đó, các trang thuộc cùng lần chạy sẽ đọc cùng dữ liệu logic.

Saved query và query run có thể có vòng đời khác nhau. Sửa saved query sang phiên bản 5 không được âm thầm thay điều kiện của lần chạy đã chốt ở phiên bản 4.

### Phân trang cần giữ cùng ý nghĩa truy vấn

Trong báo cáo doanh thu, thứ tự dòng là ngày tăng dần. Với kết quả có thể trùng khóa sắp xếp, cần thêm khóa phân định ổn định, chẳng hạn `paidAt, id`.

Một cursor nên ràng buộc với:

- Lần chạy hoặc snapshot đang đọc.
- Vị trí đọc tiếp theo và thứ tự sắp xếp.
- Bộ lọc và các lựa chọn biểu diễn có ảnh hưởng đến kết quả.
- Thời hạn sử dụng, nếu hợp đồng có đặt hạn.

Cursor có thể được ký hoặc trỏ đến trạng thái phía server để tránh sửa tùy ý. Không đưa thông tin nhạy cảm vào token có thể giải mã công khai rồi coi mã hóa base64 là bảo mật.

Cursor chỉ xác định vị trí, không tự làm nguồn dữ liệu bất biến. Nếu các dòng nguồn bị cập nhật giữa hai request, keyset pagination vẫn có thể không cung cấp snapshot mà nghiệp vụ mong đợi.

Với `limit=50`, trang đầu không có dòng nào nên trả `200` với `rows: []` và không có liên kết trang sau. Đây là truy vấn thành công cho tập rỗng. `404` dành cho trường hợp tài nguyên được yêu cầu không tồn tại hoặc được xử lý như không tồn tại theo chính sách quyền truy cập.

## 8. Retry và idempotency khi tạo công việc

Tình huống điển hình:

1. Client gửi POST tạo báo cáo.
2. Server đã ghi nhận `rpt_7f3a`.
3. Kết nối bị ngắt trước khi client nhận response.
4. Client gửi lại cùng ý định.

Nếu mỗi POST đều tạo công việc mới, người dùng có hai báo cáo và server có thể tiêu tốn tài nguyên gấp đôi.

Hệ thống minh họa hỗ trợ header `Idempotency-Key` như một phần hợp đồng riêng. Server lưu khóa trong phạm vi tenant/người gọi và loại thao tác, kèm dấu vân tay của request đã chuẩn hóa:

| Trường hợp | Hành vi cần quy định |
|---|---|
| Khóa mới và request hợp lệ | Ghi nhận một lần chạy và ánh xạ khóa đến lần chạy đó |
| Cùng khóa, cùng nội dung, còn trong thời hạn | Trả lại cùng danh tính lần chạy theo chính sách replay đã công bố |
| Cùng khóa nhưng khác nội dung | Từ chối, ví dụ `409 Conflict` với mã `IDEMPOTENCY_KEY_REUSED` |
| Khóa đã hết hạn | Có thể được xem là request mới; client phải biết giới hạn này |

Hai request đồng thời dùng cùng khóa cũng chỉ được tạo một lần chạy. Điều này cần được đảm bảo bằng cơ chế lưu trữ nguyên tử hoặc ràng buộc duy nhất, không chỉ bằng phép kiểm tra “đã có chưa” trong bộ nhớ.

Hãy nêu rõ thời hạn lưu khóa và phạm vi của khóa trong tài liệu API. Header này không phải cam kết mặc định mà mọi endpoint POST hay proxy đều hiểu.

Cùng tham số chưa chắc là cùng ý định. Người dùng có thể cố ý chạy lại báo cáo sau khi dữ liệu được cập nhật; khi đó họ cần một khóa mới và một lần chạy mới.

Ngoài ra, chống trùng request HTTP khác với chống trùng thực thi nội bộ. Hàng đợi có thể phát lại một message. Worker cần kiểm tra quyền xử lý, quản lý chuyển trạng thái và công bố kết quả theo cách không tạo tác dụng phụ lặp. Nếu công việc còn gửi email hoặc gọi dịch vụ tính phí, các tác dụng đó cũng cần cơ chế chống trùng tương ứng.

## 9. Cache, tệp kết quả và thời hạn lưu giữ

### Tách chính sách cache cho trạng thái và kết quả

Tài nguyên trạng thái thay đổi nhanh từ `QUEUED` sang `RUNNING` rồi kết thúc. Ví dụ chọn `Cache-Control: no-store` để giảm nguy cơ client nhìn trạng thái cũ. Một API khác có thể dùng cache ngắn hoặc revalidation nếu hợp đồng cho phép.

Kết quả đã hoàn tất và được giữ bất biến có thể dùng `ETag`:

~~~http
GET /report-runs/rpt_7f3a/result?limit=2 HTTP/1.1
If-None-Match: "rpt_7f3a-result-page1-v1"
~~~

Nếu biểu diễn còn hợp lệ và không đổi, server có thể trả `304 Not Modified` để client dùng lại body đã lưu. Việc xác thực và kiểm tra quyền vẫn phải diễn ra theo chính sách của tài nguyên.

ETag phải ứng với biểu diễn được chọn, có xét đến trang, tham số và biến thể liên quan. Không dùng cùng một strong ETag cho những body khác nhau chỉ vì chúng thuộc cùng một lần chạy.

`private` cho phép cache riêng của client, không cho shared cache lưu theo chỉ thị đó. `no-store` phù hợp hơn khi dữ liệu nhạy cảm cần hạn chế lưu ở cache. ID ngẫu nhiên hoặc URI khó đoán không thay thế được chính sách cache và phân quyền.

### Tệp xuất là tài nguyên có metadata rõ ràng

Một artifact CSV có thể được đọc trực tiếp:

~~~http
GET /report-runs/rpt_7f3a/artifacts/art_csv1 HTTP/1.1
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: text/csv; charset=UTF-8
Content-Disposition: attachment; filename="revenue-2026-10.csv"
Cache-Control: private, max-age=60
ETag: "art_csv1-v1"

date,paidOrderCount,revenue,currency
2026-10-01,8,6000000,VND
2026-10-02,10,8500000,VND
~~~

Body trên chỉ trích hai dòng đầu để minh họa. Hợp đồng tải tệp phải nêu rõ tệp chứa toàn bộ kết quả hay chỉ một phần; ví dụ này chọn toàn bộ kết quả.

Nếu dữ liệu xuất có chuỗi do người dùng nhập và sẽ được mở bằng bảng tính, cần có chính sách xử lý ô có thể bị diễn giải thành công thức. Quy tắc escape CSV về dấu phẩy và dấu nháy không tự giải quyết rủi ro công thức.

Khi tệp nằm ở object storage, API có thể kiểm tra quyền rồi trả `303 See Other` đến URL tải có thời hạn. URL ký sẵn phải được đối xử như thông tin cấp quyền; tránh ghi nó vào log công khai và không coi nó là URI chuẩn tồn tại lâu dài của artifact.

### Hết hạn kết quả không nhất thiết xóa lịch sử lần chạy

Trong ví dụ, `resultExpiresAt` đánh dấu thời điểm hệ thống ngừng phục vụ kết quả. Metadata lần chạy có thể còn tồn tại để kiểm toán:

- `GET /report-runs/rpt_7f3a` vẫn trả trạng thái `SUCCEEDED`, kèm thông tin kết quả đã hết hạn.
- `GET /report-runs/rpt_7f3a/result` có thể trả `410 Gone` khi server còn biết kết quả đã bị loại bỏ có chủ đích.
- Nếu không giữ dấu vết hoặc chính sách che giấu sự tồn tại yêu cầu như vậy, `404` có thể là lựa chọn phù hợp hơn.

Không trả tập rỗng thay cho kết quả đã bị xóa; client sẽ hiểu nhầm rằng báo cáo thực sự không có dữ liệu.

Thời hạn cache cần phù hợp với thời hạn phục vụ kết quả. Tuy nhiên, một response đã được tải xuống hoặc cache không thể được thu hồi chắc chắn chỉ bằng việc xóa file ở server. Nghiệp vụ cần phân biệt thời hạn phục vụ, thời hạn lưu trữ nội bộ và chính sách sử dụng bản sao phía client.

## 10. Xác thực, phân quyền và giới hạn công việc

Một lần chạy phải gắn với tenant và chủ thể yêu cầu từ ngữ cảnh đã xác thực. Không tin trường `tenantId` do client gửi như căn cứ cấp quyền.

Kiểm tra quyền ở nhiều điểm có mục đích khác nhau:

| Điểm kiểm tra | Câu hỏi cần trả lời |
|---|---|
| Tạo lần chạy | Người gọi được dùng định nghĩa và phạm vi dữ liệu này không? |
| Worker đọc nguồn | Công việc chỉ đọc đúng tenant, bộ lọc và phạm vi được giao không? |
| Đọc trạng thái | Người gọi hiện tại có quyền biết công việc này tồn tại không? |
| Đọc kết quả, tải tệp | Người gọi hiện tại còn quyền truy cập dữ liệu đã tổng hợp không? |

Quyền xem metadata không nhất thiết đồng nghĩa với quyền tải dữ liệu chi tiết. Chính sách phải được áp dụng đồng nhất trên mọi đường đọc, kể cả artifact và URL tải tạm thời.

Nếu quyền của người dùng thay đổi trong lúc công việc đang chạy, hệ thống cần quy định công việc có tiếp tục hay không và khi tải kết quả sẽ xét quyền hiện tại thế nào. Không nên để một lần kiểm tra ở POST trở thành quyền đọc vô thời hạn.

Báo cáo tổng hợp vẫn có thể tiết lộ dữ liệu nhạy cảm. Ví dụ, một nhóm chỉ có một khách hàng có thể làm lộ thông tin dù response không chứa tên. Tùy nghiệp vụ, cần giới hạn chiều phân tích, cột được xuất hoặc mức độ chi tiết.

Để tránh một request báo cáo trở thành công việc vô hạn, hợp đồng cần giới hạn khoảng ngày, số chiều nhóm, số dòng, kích thước tệp và số công việc đồng thời. Khi người gọi vượt hạn mức request/công việc có thể trả `429 Too Many Requests` theo chính sách; khi toàn hệ thống tạm thời không thể tiếp nhận có thể trả `503 Service Unavailable`. Chỉ trả `202` khi thực sự có khả năng ghi nhận và theo dõi công việc.

## 11. Ánh xạ sang Java/Spring

Đoạn mã sau minh họa lớp HTTP cho việc tạo và đọc lần chạy. Đây là khung giao tiếp, chưa phải ứng dụng chạy độc lập: cần có cấu hình xác thực, implementation của service, kho lưu trạng thái, worker và bộ ánh xạ lỗi.

Ví dụ giả định dự án Java hỗ trợ record, có Spring Web và Jakarta Bean Validation. Các DTO dưới đây được đặt trong các file Java riêng theo cấu trúc dự án; trong bài học chúng được ghép cùng để dễ theo dõi.

~~~java
public record CreateRunRequest(
    @jakarta.validation.constraints.NotBlank
    String reportDefinitionId,

    @jakarta.validation.Valid
    @jakarta.validation.constraints.NotNull
    ReportParameters parameters
) {}

public record ReportParameters(
    @jakarta.validation.constraints.NotNull
    java.time.Instant fromInclusive,

    @jakarta.validation.constraints.NotNull
    java.time.Instant toExclusive,

    @jakarta.validation.constraints.NotBlank
    String timeZone,

    @jakarta.validation.constraints.NotBlank
    @jakarta.validation.constraints.Pattern(regexp = "[A-Z]{3}")
    String currency,

    @jakarta.validation.constraints.NotBlank
    @jakarta.validation.constraints.Pattern(regexp = "DAY")
    String groupBy
) {}

public enum RunStatus {
    QUEUED, RUNNING, SUCCEEDED, FAILED
}

public record RunError(
    String code,
    String message,
    boolean retryable
) {}

public record RunView(
    String id,
    RunStatus status,
    int definitionVersion,
    java.time.Instant submittedAt,
    java.time.Instant startedAt,
    java.time.Instant completedAt,
    String snapshotId,
    java.time.Instant dataAsOf,
    java.time.Instant resultExpiresAt,
    Integer pollAfterSeconds,
    RunError error,
    java.util.Map<String, String> links
) {}

public interface ReportRunService {
    RunView submit(
        String subject,
        String idempotencyKey,
        CreateRunRequest request
    );

    RunView findVisible(String subject, String runId);
}
~~~

`@Pattern` chỉ kiểm tra hình thức. Ví dụ, ba chữ cái in hoa không chứng minh đó là đơn vị tiền tệ được hệ thống hỗ trợ. Service còn cần kiểm tra khoảng thời gian, độ dài kỳ, múi giờ, định nghĩa báo cáo, quyền truy cập và các giá trị nghiệp vụ được cho phép.

~~~java
import java.net.URI;
import java.security.Principal;

import jakarta.validation.Valid;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/report-runs")
public class ReportRunController {

    private final ReportRunService service;

    public ReportRunController(ReportRunService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<RunView> create(
            @Valid @RequestBody CreateRunRequest request,
            @RequestHeader(
                value = "Idempotency-Key",
                required = false
            ) String idempotencyKey,
            Principal principal) {

        RunView run = service.submit(
            principal.getName(),
            idempotencyKey,
            request
        );

        return ResponseEntity.accepted()
            .location(URI.create("/report-runs/" + run.id()))
            .cacheControl(CacheControl.noStore())
            .body(run);
    }

    @GetMapping("/{runId}")
    public ResponseEntity<RunView> get(
            @PathVariable("runId") String runId,
            Principal principal) {

        RunView run = service.findVisible(
            principal.getName(),
            runId
        );

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(run);
    }
}
~~~

Các endpoint này phải được cấu hình yêu cầu xác thực, để `Principal` có sẵn khi controller được gọi. Trong hệ thống nhiều tenant, service cần lấy và kiểm tra tenant từ ngữ cảnh tin cậy cùng với subject; chỉ tên người dùng chưa phải mô hình phân quyền đầy đủ.

Service `submit` chịu trách nhiệm kiểm tra, chuẩn hóa request, xử lý idempotency và ghi nhận công việc bền vững trước khi trả về. Controller này chọn chính sách replay vẫn trả `202` và cùng ID cho yêu cầu lặp còn trong thời hạn; trạng thái trong body có thể đã tiến triển. Nếu API chọn chính sách replay khác, lớp HTTP cần thể hiện đúng lựa chọn đó.

Service `findVisible` phải kiểm tra quyền trên chính lần chạy được yêu cầu. Không triển khai nó bằng cách tìm ID trước rồi trả thẳng entity chứa toàn bộ trường nội bộ.

Worker được gọi bởi hạ tầng xử lý nền, không phải bằng cách để client giữ kết nối với controller. Sau khi tổng hợp bằng kiểu dữ liệu phù hợp, worker lưu kết quả hoàn chỉnh rồi công bố trạng thái kết thúc. Các lần chạy bị kẹt cần có cơ chế phát hiện và phục hồi, chẳng hạn lease có thời hạn và giới hạn số lần thử lại.

Đối với endpoint result, lớp giao tiếp còn cần:

1. Kiểm tra quyền và tình trạng lưu giữ kết quả.
2. Phân biệt chưa sẵn sàng, đã thất bại và đã hết hạn.
3. Giải mã và kiểm tra cursor theo đúng lần chạy.
4. Trả DTO kết quả đã công bố, không chạy lại truy vấn nguồn cho từng trang.
5. Áp dụng cache và conditional request theo đúng biểu diễn.

DTO công khai nên chỉ chứa trạng thái, tham số và liên kết mà client được phép thấy. Không trả entity ORM, câu SQL, đường dẫn file vật lý, thông tin hàng đợi hoặc stack trace.

## 12. Thiết kế lỗi và mô tả hợp đồng API

Hệ thống cần một định dạng lỗi thống nhất, có mã máy đọc được và thông điệp có ích cho người dùng. Ví dụ dưới đây dùng `application/problem+json`, với `code` là trường mở rộng do API định nghĩa:

~~~http
GET /report-runs/rpt_7f3a/result HTTP/1.1
Accept: application/json
~~~

~~~http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Lần chạy chưa hoàn tất; hãy đọc trạng thái tại URI theo dõi.",
  "instance": "/report-runs/rpt_7f3a/result",
  "code": "RESULT_NOT_READY"
}
~~~

`409` cho kết quả chưa sẵn sàng là lựa chọn của API minh họa. Không có một mã lỗi duy nhất bắt buộc cho mọi thiết kế xử lý nền. Điều cần giữ là client phân biệt được trạng thái công việc với lỗi request và biết bước tiếp theo.

Bảng hợp đồng tham khảo:

| Tình huống | Phản hồi trong thiết kế này |
|---|---|
| JSON hỏng, kiểu dữ liệu không đọc được | `400 Bad Request` |
| Request đúng cấu trúc nhưng kỳ báo cáo không hợp lệ | `422 Unprocessable Content` |
| Thiếu hoặc không hợp lệ thông tin xác thực | `401 Unauthorized` theo cơ chế xác thực của API |
| Có danh tính nhưng không được thực hiện thao tác | `403 Forbidden`, hoặc `404` khi chính sách yêu cầu che giấu tài nguyên |
| ID không tồn tại | `404 Not Found` |
| Đọc được lần chạy, kể cả lần chạy đã thất bại | `200 OK` với trạng thái tương ứng |
| Đọc result khi đang chờ hoặc đang chạy | `409`, mã `RESULT_NOT_READY` |
| Đọc result của lần chạy thất bại | `409`, mã `RUN_FAILED` và liên kết theo dõi nếu được phép |
| Result đã bị loại bỏ, còn dấu vết có chủ đích | `410 Gone` |
| Vượt hạn mức của người gọi | `429 Too Many Requests` |
| Hệ thống tạm thời không thể nhận công việc | `503 Service Unavailable` |

Không cần trả chi tiết lỗi nguồn dữ liệu cho client. Chẳng hạn, lỗi timeout có thể đi kèm mã theo dõi để vận hành tra cứu; không kèm chuỗi kết nối hay thông tin nội bộ.

Khi mô tả bằng OpenAPI, cần ghi đủ:

- Schema request và response, kiểu dữ liệu, enum trạng thái, định dạng thời gian.
- Trường bắt buộc, trường có thể null và trường chỉ xuất hiện ở một số trạng thái.
- `Location`, `ETag`, `Cache-Control`, định dạng cursor và chính sách idempotency.
- Các mã phản hồi đã chọn và schema lỗi.
- Cách lấy result, tải artifact và thời hạn phục vụ.

Ví dụ `result` chỉ xuất hiện sau khi công bố kết quả; `completedAt` chưa có khi công việc đang chạy. Với DTO Java ở trên, phải cấu hình và mô tả thống nhất việc bỏ trường null hay trả null. Không để ví dụ JSON và schema đưa ra hai hợp đồng khác nhau.

Tài liệu cũng cần chỉ rõ thứ tự sắp xếp mặc định, giới hạn kích thước trang, quy tắc tính tổng và ý nghĩa của thời điểm dữ liệu. Những quy tắc này khó suy ra chỉ từ kiểu `string` hay `integer` trong schema.

## 13. Những tình huống cần kiểm thử

Các tình huống sau giúp đánh giá hợp đồng của một implementation; chúng không yêu cầu phải dùng một framework kiểm thử cụ thể.

| Nhóm | Tình huống và kết quả mong đợi |
|---|---|
| Tiếp nhận | POST hợp lệ trả `202`, `Location` đọc được và ID được lưu bền vững |
| Ngày giờ | Giao dịch đúng mốc đầu được tính; đúng mốc cuối bị loại; chia ngày theo múi giờ đã chọn |
| Tiền tệ | Tổng đúng theo quy tắc làm tròn; không gộp nhầm tiền khác đơn vị |
| Trạng thái | Lần chạy chuyển hợp lệ; chưa công bố `SUCCEEDED` khi result chưa đọc được |
| Thất bại | GET lần chạy thất bại trả `200` với `FAILED`; không lộ lỗi nội bộ |
| Retry HTTP | Hai request cùng khóa và cùng body trả cùng ID; thử cả gửi đồng thời |
| Xung đột khóa | Cùng khóa nhưng body khác bị từ chối theo hợp đồng |
| Phát lại message | Worker xử lý lại không tạo kết quả hoặc tác dụng phụ trùng |
| Phân trang | Đọc hết các trang trên cùng snapshot không thiếu/trùng; cursor của lần chạy khác bị từ chối |
| Tập rỗng | Result hợp lệ trả `200` với danh sách rỗng hoặc các nhóm có giá trị 0 theo đúng quy tắc đã công bố |
| Quyền truy cập | Tenant khác không xem trạng thái, result hoặc tải artifact được |
| Thay đổi quyền | Quyền bị thu hồi trước lúc tải được xử lý đúng chính sách |
| Cache | ETag đúng theo từng biểu diễn; conditional GET không vượt qua kiểm tra quyền |
| Hết hạn | Result hết hạn không biến thành “báo cáo không có dữ liệu” |
| Khôi phục | API/worker bị dừng sau khi tiếp nhận vẫn theo dõi hoặc phục hồi công việc được |

Để kiểm tra snapshot, có thể đọc trang đầu, thay đổi dữ liệu nguồn rồi đọc trang sau. Nếu hợp đồng hứa tập kết quả cố định, thay đổi đó không được làm các trang còn lại chuyển sang dữ liệu mới.

Để kiểm tra độ bền, mô phỏng lỗi ở ranh giới giữa ghi nhận công việc và chuyển việc cho worker. Kiểm tra chỉ với luồng thành công không phát hiện được một yêu cầu đã trả `202` nhưng không bao giờ được xử lý.

## 14. Các sai lầm thường gặp

| Cách làm | Vấn đề | Hướng điều chỉnh |
|---|---|---|
| GET ngầm tạo một báo cáo tính phí mới | Client, cache hoặc cơ chế tải trước có thể vô tình phát sinh công việc | Dùng POST cho ý định tạo/chạy; GET dùng để theo dõi và đọc |
| Chỉ đổi `/generateReport` thành `/reports` | Tên gọi chưa giải quyết đầu vào và vòng đời mơ hồ | Xác định rõ định nghĩa, lần chạy và kết quả |
| Tài nguyên trạng thái không có ID bền vững | Client không thể quay lại theo dõi sau lỗi kết nối | Ghi nhận công việc và cấp URI ổn định |
| Trả `202` rồi chỉ lưu việc trong bộ nhớ | Khởi động lại có thể làm mất yêu cầu đã tiếp nhận | Dùng cơ chế lưu trữ và chuyển giao có thể phục hồi |
| GET mỗi trang tự chạy lại truy vấn nguồn | Trang và tổng có thể thuộc các thời điểm khác nhau | Chốt snapshot hoặc công bố mức nhất quán thực tế |
| Ghi một timestamp rồi gọi đó là snapshot | Timestamp không tự cố định được tập dữ liệu | Dùng cơ chế snapshot/vật hóa phù hợp với nguồn |
| Trả `500` khi công việc đã thất bại | Client không phân biệt lỗi đọc tài nguyên với thất bại công việc | Trả biểu diễn lần chạy cùng trạng thái nghiệp vụ |
| Dùng ID khó đoán làm bảo vệ dữ liệu | Người có ID vẫn có thể truy cập chéo tenant nếu thiếu kiểm tra | Phân quyền trên từng tài nguyên và đường tải |
| Xóa result rồi trả mảng rỗng | Làm sai ý nghĩa báo cáo | Dùng phản hồi hết hạn hoặc không tồn tại theo chính sách |
| Sửa định nghĩa rồi thay cả kết quả cũ | Làm mất khả năng giải thích lịch sử | Gắn lần chạy với phiên bản và giữ kết quả đã công bố |

## 15. Tự thực hành

Thiết kế API “báo cáo công nợ theo khách hàng” với ba yêu cầu: chạy có thể mất vài phút, tải kết quả sau khi đóng trình duyệt và kết quả phải ổn định trong bảy ngày.

Hãy viết hợp đồng cho ba thao tác:

1. Tạo lần chạy với ngày chốt công nợ và đồng tiền.
2. Đọc trạng thái của một lần chạy.
3. Đọc từng trang kết quả và tải tệp xuất.

Với từng thao tác, xác định URI, phương thức, request, response, mã HTTP và điều kiện phân quyền. Sau đó trả lời:

- Nếu cùng request được gửi hai lần vì timeout, có tạo hai lần chạy không?
- Nếu dữ liệu thanh toán được cập nhật sau khi đọc trang đầu, trang sau dựa trên dữ liệu nào?
- Nếu công việc thất bại, client nhìn thấy thông tin ở đâu?
- Nếu result đã hết hạn nhưng lịch sử lần chạy còn tồn tại, hai URI trả gì?
- Nếu người tạo báo cáo bị thu hồi quyền, ai còn được tải tệp?

Một thiết kế đạt yêu cầu khi client có thể theo dõi công việc bằng URI ổn định, hiểu chính xác ý nghĩa của dữ liệu và xử lý retry, lỗi, hết hạn mà không phải đoán hành vi của server.
