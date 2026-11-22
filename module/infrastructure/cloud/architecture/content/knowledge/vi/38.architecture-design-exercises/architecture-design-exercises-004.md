# Bổ sung xử lý bất đồng bộ và kiểm soát tải đột biến

## 1. Mục tiêu bài thực hành

Một ứng dụng đám mây có thể chạy tốt vào ngày thường nhưng suy giảm nghiêm trọng khi có khuyến mãi, sự kiện truyền thông hoặc hàng loạt khách hàng cùng gửi yêu cầu. Một nguyên nhân phổ biến là **mọi thao tác đều được thực hiện đồng bộ trong luồng HTTP**, kể cả những việc khách hàng không cần chờ ngay như gửi email, lập báo cáo, tạo PDF hay đồng bộ hệ thống bên ngoài. Khi tải tăng, các lời gọi chậm tạo thành hàng đợi ngầm ở thread, connection pool và database; timeout và retry có thể khiến hệ thống quá tải thêm.

Bài **“Bổ sung xử lý bất đồng bộ và kiểm soát tải đột biến”** thuộc chương **Thực hành thiết kế** của module **CLOUD_ARCHITECTURE**. Người học sẽ thực hành biến yêu cầu nghiệp vụ thành quyết định về **mạng, compute, dữ liệu và mô hình triển khai**, đồng thời giải thích đánh đổi theo **Well-Architected**: độ tin cậy, bảo mật, hiệu năng, chi phí, vận hành và tính bền vững.

Sau bài này, bạn có thể:

1. Nhận ra việc nào nên giữ **đồng bộ** và việc nào có thể chuyển sang **bất đồng bộ**.
2. Thiết kế luồng **API → lưu yêu cầu bền vững → queue → worker → hệ thống đích**.
3. Chọn **rate limiting, admission control, backpressure, autoscaling** và giới hạn concurrency để bảo vệ tài nguyên khi burst.
4. Tính gần đúng **throughput, backlog, thời gian chờ và công suất worker** từ một kịch bản tải cụ thể.
5. Xử lý **retry, duplicate, idempotency, poison message, dead-letter queue (DLQ), thứ tự sự kiện** và tình huống sự cố.
6. Đưa ra sơ đồ kiến trúc, tiêu chí nghiệm thu, runbook và phân tích đánh đổi có thể bảo vệ trước hội đồng thiết kế.

**Nguyên tắc xuyên suốt:** Bất đồng bộ giúp **tách thời điểm chấp nhận công việc khỏi thời điểm thực hiện công việc**; bản thân queue **không tạo thêm công suất**. Nếu tốc độ công việc đến luôn lớn hơn tốc độ xử lý, backlog cuối cùng vẫn tăng đến mức không thể chấp nhận.

## 2. Đề bài: hệ thống bán hàng gặp đỉnh tải

### Bối cảnh giả định

Một doanh nghiệp thương mại điện tử có API phục vụ trang web và ứng dụng di động. Sau khi đơn hàng được xác nhận, hệ thống cần tạo hóa đơn PDF, gửi email thông báo, cộng điểm khách hàng và đồng bộ dữ liệu sang hệ thống phân tích. Hiện tại, các tác vụ này chạy trực tiếp trong lời gọi xác nhận đơn hàng.

**Tất cả số liệu dưới đây là giả định cho bài học**, không phải năng lực mặc định của một dịch vụ cloud:

| Thông số | Giá trị giả định |
|---|---:|
| Lưu lượng request toàn ứng dụng ngày thường | 400 request/giây |
| Lưu lượng đỉnh khi khuyến mãi | 4.000 request/giây trong 5 phút |
| Tỷ lệ request dẫn tới một đơn hàng đã xác nhận | 5% |
| Số sự kiện xử lý nền phát sinh | Khoảng 20 sự kiện/giây ngày thường; 200 sự kiện/giây lúc đỉnh |
| Throughput của một worker qua benchmark ban đầu | 5 sự kiện/giây |
| Giới hạn worker dự kiến trong đợt đầu | 24 worker |
| Kỳ vọng nghiệp vụ đối với thông báo/hóa đơn | Hoàn thành phần lớn trong 10 phút sau xác nhận đơn |

Khách hàng phải **biết trạng thái đơn và thanh toán một cách chính xác**. Việc gửi email hoặc tạo PDF chậm không được khiến một đơn đã thanh toán hợp lệ biến thành đơn “thất bại” hoặc khiến hệ thống thu tiền hai lần. Ngược lại, cũng không được trả lời “thanh toán thành công” chỉ vì đã đẩy một yêu cầu vào queue.

### Hiện trạng: phụ thuộc đồng bộ kéo dài đường đi

~~~mermaid
flowchart LR
    U["Khách hàng"] --> L["Load balancer"]
    L --> A["Order API"]
    A --> DB[("Order database")]
    A --> PDF["Tạo hóa đơn PDF"]
    A --> MAIL["Nhà cung cấp email"]
    A --> CRM["Đồng bộ loyalty / analytics"]
    PDF --> A
    MAIL --> A
    CRM --> A
    A --> U
~~~

Giả sử email provider đột ngột tăng latency từ vài trăm mili giây lên hàng chục giây. HTTP connection/thread bị giữ lâu; retry từ client và gateway có thể làm lượng công việc thực tế vượt lưu lượng ban đầu. Thêm instance API mà không giới hạn kết nối tới downstream có thể **đẩy nút thắt** sang email provider hoặc database.

**Bài toán cần giải:** giảm phụ thuộc của luồng quan trọng vào các tác vụ nền, tiếp nhận tải đột biến có giới hạn, cho phép xử lý dần mà vẫn bảo toàn tính đúng đơn hàng và kiểm soát lỗi, chi phí, vận hành.

## 3. Bước một: phân loại nghiệp vụ đồng bộ và bất đồng bộ

Trước khi vẽ queue, xác định điều gì phải đúng **ngay tại thời điểm phản hồi HTTP**.

| Hoạt động | Định hướng | Lý do |
|---|---|---|
| Xác thực và kiểm tra quyền đặt hàng | **Đồng bộ** | Không được chấp nhận yêu cầu trái quyền |
| Kiểm tra định dạng, khóa idempotency và quy tắc đầu vào cơ bản | **Đồng bộ** | Tránh lưu yêu cầu không hợp lệ rõ ràng |
| Ghi nhận yêu cầu đặt hàng một cách bền vững | **Đồng bộ tại ranh giới chấp nhận** | Không được báo đã nhận nếu mọi thông tin chỉ nằm trong RAM |
| Xử lý/kết luận thanh toán | **Tùy hợp đồng nghiệp vụ** | Nếu cần kết quả ngay, giữ đường xác nhận đúng; nếu xử lý sau, phải trả trạng thái đang xử lý |
| Tạo file PDF hóa đơn | **Thường bất đồng bộ** | File có thể sẵn sàng sau một khoảng thời gian được công bố |
| Gửi email/SMS thông báo | **Thường bất đồng bộ** | Có thể retry khi nhà cung cấp chậm, tránh giữ HTTP request |
| Tích điểm, đồng bộ CRM, ghi số liệu phân tích | **Có thể bất đồng bộ** | Cần xác định SLA cập nhật và quy tắc đối soát |
| Giữ chỗ hàng tồn hoặc bảo đảm không bán quá số lượng | **Phải bảo toàn tính đúng** | Có thể thiết kế bất đồng bộ nhưng cần trạng thái, reservation/compensation và cam kết rõ |

**Không được tùy tiện chuyển thanh toán, giữ chỗ hoặc thao tác có hệ quả pháp lý sang queue rồi trả thành công trước khi điều kiện nghiệp vụ được thỏa.** Nếu chấp nhận xử lý sau, API nên nói chính xác “đã nhận yêu cầu, đang xử lý” và cung cấp cách tra cứu kết quả cuối.

### Phân biệt ba thời điểm

1. **Accepted:** yêu cầu được kiểm tra cơ bản và lưu bền vững theo hợp đồng API.
2. **Business completed:** tác vụ nghiệp vụ chính hoàn thành, ví dụ đơn được xác nhận thanh toán.
3. **Side effects completed:** hóa đơn, email, loyalty hoặc phân tích được xử lý xong.

Một hệ thống có thể ở trạng thái accepted nhưng chưa business completed; hoặc đơn đã xác nhận nhưng thông báo còn chờ. Không nên dùng một cờ boolean \`success=true\` cho cả ba trạng thái.

## 4. Bước hai: thiết kế luồng bất đồng bộ có thể tin cậy

### Kiến trúc đích tham khảo

~~~mermaid
flowchart TB
    U["Web / Mobile"] --> EDGE["CDN / WAF / API Gateway<br/>auth, rate limit, admission"]
    EDGE --> API["Order API<br/>idempotency + trạng thái nghiệp vụ"]
    API <--> DB[("Order DB<br/>Orders + Outbox")]
    DB --> RELAY["Outbox relay<br/>publish với retry"]
    RELAY --> Q["Durable queue / topic<br/>backlog có giới hạn"]
    Q --> W["Worker pool<br/>concurrency có giới hạn"]
    W --> PDF["Dịch vụ tạo PDF / storage"]
    W --> MSG["Email / loyalty / analytics"]
    W --> DLQ["Dead-letter queue"]
    API --> STATUS["API tra cứu trạng thái"]
    STATUS --> U
    OBS["Metrics / logs / traces / alerts"] -.-> API
    OBS -.-> RELAY
    OBS -.-> Q
    OBS -.-> W
    OBS -.-> DLQ
~~~

Sơ đồ là **kiến trúc logic**. Queue có thể là dịch vụ quản lý hoặc broker tự vận hành; worker có thể chạy trên serverless, container jobs, Kubernetes hoặc VM. Không cần thêm tất cả thành phần trong mọi dự án; giữ những khối thực sự giải quyết yêu cầu và có nhóm sở hữu vận hành.

### Vai trò các thành phần

**Edge/API Gateway:** xác thực, giới hạn yêu cầu theo người dùng/tenant và bảo vệ API khỏi cơn bão request. WAF giúp lọc một số loại lưu lượng độc hại nhưng không thay thế admission control ở tầng ứng dụng.

**Order API:** xử lý quy tắc đồng bộ, quyết định chấp nhận/từ chối, tạo hoặc đọc bản ghi idempotency và trả trạng thái đúng sự thật. Trên luồng xác nhận đơn, API hoặc consumer xử lý kết quả thanh toán sẽ ghi thay đổi nghiệp vụ và event cần phát một cách nhất quán.

**Transactional outbox:** bảng event trong **cùng giao dịch database** với cập nhật trạng thái nghiệp vụ, giúp tránh tình huống “DB commit thành công nhưng tiến trình chết trước khi publish event”. Relay đọc event chưa gửi, publish rồi đánh dấu đã gửi. Nếu relay mất kết nối sau khi broker nhận nhưng trước khi cập nhật outbox, sự kiện có thể được gửi **lặp**.

**Durable queue:** giữ công việc đã publish, tách nhịp tiếp nhận khỏi nhịp xử lý, hỗ trợ retry/visibility timeout hoặc cơ chế tương đương. Queue phải có quota, thời hạn lưu và chiến lược khi đầy; không nên xem là kho lưu trữ vô hạn.

**Worker:** thực hiện tác vụ độc lập, giới hạn concurrency và kết nối downstream, ghi tiến độ/kết quả. Consumer phải chịu được message lặp và xử lý lỗi có phân loại.

**DLQ:** nhận message vượt chính sách retry hoặc lỗi không thể xử lý ngay, để điều tra và phát lại có kiểm soát. DLQ có cảnh báo, owner, retention; không phải “thùng rác để quên”.

**Observability:** đo cả HTTP, outbox, queue và downstream; liên kết sự kiện bằng \`order_id\`, \`event_id\`, \`correlation_id\` và \`trace_id\` phù hợp chính sách bảo mật.

### Luồng sau khi đơn được xác nhận

~~~mermaid
sequenceDiagram
    participant C as Khách hàng
    participant A as Order API
    participant D as Order DB
    participant R as Outbox relay
    participant Q as Queue
    participant W as Worker
    participant E as Email/PDF
    C->>A: Xác nhận/tra cứu đơn
    A->>D: Giao dịch: trạng thái CONFIRMED + outbox event
    D-->>A: COMMIT thành công
    A-->>C: Phản hồi trạng thái đơn chính xác
    R->>D: Đọc event chưa publish
    R->>Q: Publish OrderConfirmed
    Q-->>R: Broker ACK
    R->>D: Đánh dấu outbox đã gửi
    Q->>W: Giao event (có thể giao lại)
    W->>W: Kiểm tra event_id / tính idempotent
    W->>E: Tạo PDF/gửi thông báo
    E-->>W: Kết quả
    W->>Q: ACK sau xử lý thành công
~~~

Đây không phải một transaction nguyên tử trải dài từ database tới email provider. Nếu worker mất kết nối ngay sau khi email đã gửi, event có thể được giao lại; cần idempotency ở hệ thống đích, bằng chứng giao dịch hoặc quy trình đối soát.

## 5. Bước ba: xác định hợp đồng API và trạng thái

Với lệnh xử lý bất đồng bộ, hợp đồng phải nói rõ **khi nào dữ liệu đã được ghi bền vững** và cách khách hàng biết kết quả.

### Ví dụ API nhận yêu cầu xử lý sau

~~~http
POST /orders
Idempotency-Key: 74d29db0-94e7-4c1e-9667-2a2189a3d82d
Content-Type: application/json

{"cart_id":"cart-715","delivery_address_id":"addr-20"}
~~~

Nếu chỉ **tiếp nhận để xử lý tiếp** và chưa xác nhận thanh toán/đơn:

~~~http
HTTP/1.1 202 Accepted
Location: /orders/ord-913
Retry-After: 2
Content-Type: application/json

{"order_id":"ord-913","status":"PENDING","message":"Yêu cầu đã được ghi nhận"}
~~~

~~~http
GET /orders/ord-913
~~~

~~~json
{"order_id":"ord-913","status":"CONFIRMED","invoice_status":"PROCESSING","notification_status":"PENDING"}
~~~

Các trạng thái minh họa có thể gồm \`PENDING\`, \`PROCESSING\`, \`CONFIRMED\`, \`REJECTED\`, \`CANCELLED\`; những trạng thái cuối và phép chuyển trạng thái cần được định nghĩa theo miền nghiệp vụ. Nếu API đã xác nhận đơn hoàn tất tại thời điểm trả lời thì có thể dùng \`201 Created\` hoặc \`200 OK\` tùy giao ước, không bắt buộc phải trả \`202\` cho mọi hệ thống có queue.

**Idempotency-Key** nên được ràng buộc với người gọi, loại thao tác và dấu vết payload (hoặc dữ liệu tương đương) để tránh một khóa bị dùng lại cho yêu cầu khác. Cần quy định thời gian giữ khóa và kết quả trả về khi client retry. Khi cùng một khóa và payload được gửi lại, API nên trả lại kết quả đã được ghi nhận thay vì tạo đơn mới. Kiểm soát này **không tự thay thế idempotency của thanh toán** ở hệ thống đối tác.

### Khi không thể tiếp nhận thêm

- **429 Too Many Requests**: người gọi vượt giới hạn đã công bố hoặc giới hạn để bảo vệ tài nguyên; có thể kèm \`Retry-After\` nếu ước lượng hợp lý.
- **503 Service Unavailable**: hệ thống tạm không thể tiếp nhận an toàn do thiếu công suất hoặc phụ thuộc trọng yếu không sẵn sàng; cân nhắc \`Retry-After\` và client backoff.
- **Không trả \`202\` hoặc \`2xx\` nếu yêu cầu chưa được ghi bền vững** và không có cơ chế bảo đảm xử lý tiếp.

API phải phân biệt **chấp nhận yêu cầu** với **hoàn tất công việc** để tránh khiến frontend hiển thị sai trạng thái nghiệp vụ.

## 6. Bước bốn: kiểm soát tải đột biến ở nhiều lớp

Thêm queue giải quyết một phần công việc nền, nhưng lớp nhận request vẫn có database, connection pool, CPU và giới hạn đối tác. Một thiết kế đủ an toàn thường kết hợp nhiều cơ chế sau:

| Cơ chế | Đặt tại đâu | Vai trò | Giới hạn cần lưu ý |
|---|---|---|---|
| **Rate limiting** | Edge/API theo user, API key, tenant, endpoint | Giới hạn tốc độ gửi yêu cầu | Không giải quyết nhiệm vụ đã vào backlog |
| **Burst allowance (token bucket)** | Gateway hoặc API | Cho phép burst ngắn trong phạm vi ngân sách | Burst quá lớn vẫn làm quá tải thành phần phía sau |
| **Admission control** | API trước điểm commit | Từ chối/giãn nhận khi DB, outbox, queue hoặc ngân sách gần giới hạn | Phải dùng tín hiệu trạng thái và ngưỡng rõ ràng |
| **Bounded concurrency** | API, relay và worker | Không vượt connection pool, quota hoặc công suất downstream | Concurrency quá thấp gây trễ SLA |
| **Backpressure** | Worker, queue, producer | Truyền tín hiệu quá tải ngược dòng; giảm tốc hoặc tạm nhận | Phải quyết định công việc nào ưu tiên, công việc nào từ chối |
| **Autoscaling** | API và worker | Tăng/giảm compute theo nhu cầu đo được | Có độ trễ khởi tạo, quota, chi phí và bottleneck khác |
| **Timeout + circuit breaker** | Caller tới downstream | Không giữ tài nguyên chờ vô hạn khi đối tác lỗi | Ngưỡng quá nhạy có thể từ chối cả yêu cầu tốt |
| **Load shedding / degrade** | API và ứng dụng | Tạm bỏ tính năng không thiết yếu để bảo vệ giao dịch chính | Phải xác định rõ chức năng được phép giảm cấp |

### Token bucket minh họa

Một bucket có **dung lượng 200 token**, bổ sung **80 token/giây** và mỗi request tốn một token. Tại thời điểm bucket đầy, có thể cho phép tối đa 200 request dồn dập, sau đó tốc độ chấp nhận dài hạn quanh 80 request/giây (chưa xét giới hạn khác).

Đây chỉ là **ví dụ một bucket cho một lớp/đối tượng được chọn**; không thể lấy ngưỡng 80 request/giây áp trực tiếp cho toàn ứng dụng đang xử lý hàng trăm request/giây. Cần thiết kế riêng **per-client**, **per-tenant**, **per-endpoint** và **global safety limit** theo ngân sách công suất, bảo đảm công bằng và tránh một tenant chiếm hết tài nguyên.

### Sơ đồ bảo vệ có thứ tự

~~~mermaid
flowchart TD
    R["Request tới API"] --> AUTH{"Xác thực / quyền hợp lệ?"}
    AUTH -- "Không" --> D1["401/403 hoặc lỗi tương ứng"]
    AUTH -- "Có" --> RATE{"Rate limit đạt?"}
    RATE -- "Không" --> D2["429 + hướng dẫn retry"]
    RATE -- "Có" --> CAP{"Còn khả năng tiếp nhận bền vững?"}
    CAP -- "Không" --> D3["503 / 429 theo lý do, không nhận giả"]
    CAP -- "Có" --> COMMIT["Ghi state + idempotency/outbox"]
    COMMIT --> OK["Trả trạng thái chính xác"]
~~~

Không có con số giới hạn đúng cho mọi hệ thống. Ngưỡng được xác định qua load test, sức chịu tải database, quota downstream, SLO và chính sách phân bổ tài nguyên.

### Ngăn “retry storm”

Khi dịch vụ chậm, client, gateway, service và worker **có thể cùng retry một thao tác**, khiến mỗi request ban đầu sinh nhiều request mới. Chính sách retry nên có:

- Timeout rõ ràng theo từng tầng và ngân sách thời gian end-to-end.
- Số lần retry **hữu hạn**, chỉ retry lỗi có tính tạm thời.
- Exponential backoff với **jitter** để tránh tất cả cùng gửi lại một lúc.
- Tôn trọng \`Retry-After\` và quota của downstream khi được cung cấp.
- Idempotency đối với thao tác có side effect.
- Không retry ngay lập tức tại mọi lớp; xác định tầng **chịu trách nhiệm retry** cho một thao tác.

**Circuit breaker** có thể giảm số lời gọi tới downstream đang hỏng, nhưng cần đo để mở lại từng phần an toàn; nó không giải quyết backlog đã tồn tại.

## 7. Bước năm: tính công suất, backlog và thời gian phục hồi

Để quyết định bao nhiêu worker là đủ, mô hình hóa tốc độ:

- \(\lambda(t)\): số công việc mới được nhận vào hàng đợi mỗi giây.
- \(\mu(t)\): số công việc hoàn tất mỗi giây của toàn worker pool.
- \(B(t)\): số công việc còn tồn chưa hoàn tất, theo cách định nghĩa nhất quán với chỉ số queue.

Gần đúng theo khoảng thời gian \(\Delta t\), khi không có giới hạn khác:

\[
B(t+\Delta t)\approx\max\left(0,\, B(t)+[\lambda(t)-\mu(t)]\Delta t\right).
\]

**Giả định bài toán:** một sự kiện = một công việc, mỗi worker xử lý trung bình **5 công việc/giây**, công suất giữ ở 24 worker ngay khi đỉnh bắt đầu, queue đủ dung lượng, không bị nghẽn downstream, mỗi công việc có chi phí xử lý gần tương đương.

Khi đó:

| Giai đoạn | Tốc độ đến \(\lambda\) | Công suất \(\mu\) | Biến động backlog |
|---|---:|---:|---:|
| Bình thường | 20 job/s | 24 × 5 = 120 job/s (nếu đủ worker đang chạy) | Hàng đợi nhanh chóng rỗng |
| Đỉnh trong 300 giây | 200 job/s | 120 job/s | Tăng \(80 \times 300 = 24.000\) job |
| Sau đỉnh | 20 job/s | 120 job/s | Giảm ròng 100 job/s |

Từ đó ước tính thời gian **xả backlog sau đỉnh**:

\[
t_{\text{xả}}=\frac{24.000}{120-20}=240\text{ giây}=4\text{ phút}.
\]

Nếu FIFO và throughput giữ ổn định, một công việc đến ở cuối đỉnh có thể phải đợi gần **\(24.000/120=200\) giây** trước khi được xử lý, chưa kể thời gian bản thân task thực hiện. Tổng thời gian từ lúc bắt đầu đỉnh tới khi backlog trở lại gần 0 là khoảng **9 phút** trong mô hình lý tưởng.

**Cần phân biệt:** 4 phút là thời gian xả sau đỉnh; 9 phút là thời gian từ đầu đỉnh đến khi xả xong, không phải thời gian chờ của mọi công việc. Các giá trị này là **ước tính**, chưa tính delay autoscaling, task thất bại, retry, queue delivery, nhà cung cấp email/PDF hay hiệu ứng phân bố thời gian xử lý.

### Công thức sizing thực dụng

Nếu mỗi worker có thông lượng bền vững đã đo là \(r\) job/s, mục tiêu công suất là \(\mu_{\text{target}}\) job/s thì:

\[
N_{\text{worker}}=\left\lceil\frac{\mu_{\text{target}}}{r}\right\rceil.
\]

Ví dụ muốn **xử lý ngang bằng đỉnh 200 job/s** với 5 job/s/worker và không dựa vào buffer:

\[
N=\left\lceil\frac{200}{5}\right\rceil=40\text{ worker}.
\]

Nếu vẫn chỉ dùng 24 worker vì ngân sách hoặc quota, phải chấp nhận backlog có giới hạn và **chứng minh thời gian chờ vẫn trong SLO**. Nếu downstream chỉ nhận 60 job/s, cả 40 worker cũng không giúp vượt giới hạn đó; cần throttling có kiểm soát hoặc tăng quota downstream.

### Thực tế không thể chỉ dựa vào một con số trung bình

Cần benchmark **p50/p95 thời gian mỗi job**, tỷ lệ lỗi, hệ số retry, thời gian cold start, tác vụ chậm, API quota, disk/network throughput và độ lệch kích thước công việc. Nếu mỗi job mất 1 giây CPU nhưng đồng thời gọi API tốn 5 giây chờ, cách chọn concurrency và sizing CPU sẽ khác. Workers chạy quá nhiều tác vụ đồng thời có thể gây OOM hoặc cạn connection pool.

Ngoài **queue depth**, phải quan sát **age of oldest unprocessed message** và **end-to-end completion latency**; hai queue cùng có 10.000 message có thể khác nhau rất lớn về mức độ vi phạm SLO.

## 8. Bước sáu: bảo đảm tính đúng khi queue giao lại message

### At-least-once không đồng nghĩa exactly-once

Hầu hết thiết kế thực tế cần sẵn sàng cho tình huống một message được giao **hơn một lần**. Ví dụ:

1. Worker nhận \`OrderConfirmed\`.
2. Worker tạo PDF và gọi dịch vụ email thành công.
3. Worker bị dừng trước khi gửi ACK tới broker.
4. Sau visibility timeout, broker giao lại message cho worker khác.

Nếu consumer không có cơ chế kiểm soát, khách có thể nhận hai email, bị cộng điểm hai lần hoặc sinh hai hóa đơn khác nhau. Queue có cơ chế FIFO hoặc deduplication **không tự bảo đảm hiệu ứng đúng một lần trên mọi hệ thống bên ngoài**.

### Thiết kế event và khóa idempotency

Một event mẫu nên có phiên bản schema và định danh ổn định:

~~~json
{
  "event_id": "order-913-confirmed-v1",
  "event_type": "OrderConfirmed",
  "schema_version": 1,
  "order_id": "ord-913",
  "occurred_at": "2026-01-01T10:00:00Z",
  "correlation_id": "trace-7f3b",
  "payload_ref": "orders/ord-913"
}
~~~

Ví dụ trên dùng timestamp minh họa; dữ liệu sản xuất phải được tạo từ thời điểm sự kiện thực. \`event_id\` không được thay đổi khi relay publish lại cùng một event. Giữ payload nhỏ và ưu tiên **tham chiếu** tới dữ liệu nguồn khi phù hợp, hạn chế đưa PII vào queue.

Một **consumer idempotency key** có thể là \`(consumer_name, event_id)\`; khi cùng một event cần chạy lại vì bản sửa dữ liệu hay thay đổi thuật toán, tạo **version xử lý riêng** được quản lý. Với hành động “cộng 100 điểm”, key cần được áp dụng tại sổ cái/transaction ghi điểm để ngăn cộng trùng, không chỉ kiểm tra một biến trong RAM.

### Transactional outbox: giải quyết khoảng trống DB–broker

~~~sql
-- Giả mã SQL, tên cột và cú pháp phụ thuộc hệ quản trị dữ liệu.
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'PENDING';

-- Chỉ phát event khi transition nghiệp vụ thành công.
INSERT INTO outbox(event_id, aggregate_id, event_type, payload, status)
VALUES (:stable_event_id, :order_id, 'OrderConfirmed', :payload, 'NEW')
ON CONFLICT (event_id) DO NOTHING;

COMMIT;
~~~

Đoạn trên là **phác thảo**. Khi triển khai phải xác minh số dòng được cập nhật, cách xử lý đơn đã được xác nhận, transaction isolation và logic nhận kết quả thanh toán. **Một cập nhật đơn thành công và event tương ứng** phải nằm trong cùng transaction. Giao dịch này không thể tự bao trùm lời gọi đến cổng thanh toán bên ngoài.

Relay **chỉ đánh dấu outbox đã publish sau khi broker xác nhận đã nhận**. Nếu relay crash giữa ACK của broker và việc đánh dấu DB, event có thể xuất hiện lại. Đó là lý do consumer vẫn phải idempotent.

### Consumer xử lý an toàn

~~~text
on_message(event):
    validate_schema_and_authorization(event)
    if already_completed(consumer_name, event.event_id):
        ack_message()
        return

    order = fetch_order(event.order_id)
    verify_expected_business_state(order)
    result = perform_side_effect_with_idempotency_key(
        key = consumer_name + ":" + event.event_id
    )
    persist_completion_or_reconcile(result, event.event_id)
    ack_message_only_after_safe_completion()
~~~

Giả mã không tuyên bố có transaction xuyên **database + broker + email provider**. Nếu bên cung cấp email không hỗ trợ idempotency key, phải chấp nhận có khả năng gửi trùng trong các trường hợp khó xác định hoặc bổ sung tra cứu/đối soát; không nên gắn nhãn “exactly once” khi chưa chứng minh.

### Thứ tự event và nhiều worker

Queue xử lý song song thường **không bảo đảm thứ tự toàn cục**. Với các thay đổi \`OrderCreated\`, \`OrderPaid\`, \`OrderCancelled\`, hệ thống cần quyết định có phải giữ thứ tự **theo order_id** không, và nếu có thì dùng partition key/ordering key, kiểm tra version hoặc cơ chế serialization theo aggregate.

Một cách phòng vệ là ghi **version trạng thái** và chỉ xử lý event khi thỏa điều kiện chuyển trạng thái. Không áp dụng sự kiện \`OrderCreated\` đến muộn để ghi đè đơn đã \`CONFIRMED\`.

## 9. Bước bảy: retry, timeout và dead-letter queue

### Phân loại lỗi trước khi thử lại

| Nhóm lỗi | Ví dụ | Hành động |
|---|---|---|
| **Tạm thời** | 429 từ provider, timeout mạng, dịch vụ đích tạm gián đoạn | Retry có giới hạn, backoff + jitter, tuân thủ quota |
| **Thường trực theo dữ liệu** | Thiếu trường bắt buộc, schema không tương thích, địa chỉ email lỗi định dạng | Không retry vô hạn; đánh dấu lỗi nghiệp vụ/quarantine |
| **Lỗi code hoặc cấu hình** | Mọi message bị exception vì deploy lỗi | Dừng hoặc giảm consumer, rollback, sửa và replay có kiểm soát |
| **Thiếu tài nguyên** | OOM, hết kết nối, worker bị thu hồi | Điều chỉnh concurrency/sizing; xử lý lại sau khi đủ tài nguyên |
| **Không rõ side effect đã xảy ra** | Provider đã gửi email nhưng client không nhận phản hồi | Tra cứu bằng idempotency/transaction key hoặc reconciliation trước khi chạy lại |

Một chính sách tham khảo: **tối đa 5 lần thử**, thời gian chờ tăng dần có jitter, và chuyển DLQ khi hết cơ hội phục hồi. Con số này chỉ là ví dụ; chính sách thực phải tính **tổng thời gian retry**, retention, SLO và tốc độ hồi phục của downstream.

### Visibility timeout, lease và ACK

Với broker sử dụng cơ chế visibility timeout, nếu thời gian xử lý có thể lên tới 120 giây mà visibility timeout chỉ 30 giây, message có thể được giao cho worker khác **trước khi worker đầu hoàn thành**. Chọn timeout dựa trên thời gian xử lý quan sát được hoặc dùng **heartbeat/lease extension** nếu nền tảng hỗ trợ. Dù vậy, consumer vẫn phải idempotent vì duplicate có thể xảy ra theo nguyên nhân khác.

Sau một lỗi tạm thời, **không ACK như đã thành công**. Nhưng cũng không để message retry nóng liên tục không backoff. Khi poison message vào DLQ, hệ thống phải có người theo dõi và một trạng thái nghiệp vụ đủ rõ để xử lý trường hợp bỏ sót thông báo.

### Quy trình xử lý DLQ

1. Cảnh báo khi DLQ tăng, có message già hoặc tỷ lệ lỗi vượt ngưỡng; gắn owner.
2. Điều tra theo \`event_id\`, nguyên nhân lỗi, schema version, consumer version và tác động người dùng.
3. Sửa nguyên nhân: dữ liệu, code, cấu hình, quyền, quota hoặc provider.
4. Phát lại một **mẫu nhỏ** sau sửa, đối soát để chắc chắn không nhân đôi side effect.
5. Replay theo lô có giới hạn tốc độ, theo dõi queue lag và downstream.
6. Ghi lại số event thành công, chưa xử lý, bị loại có lý do và tác động đến SLO.

DLQ không nên chứa secret hoặc thông tin nhạy cảm quá mức cần thiết. Thời hạn retention phải phù hợp quy định dữ liệu và thời gian cho phép phục hồi.

## 10. Bước tám: autoscaling có giới hạn và ưu tiên công việc

### Chọn tín hiệu scale

Chỉ scale worker theo CPU không đủ cho hệ thống chủ yếu chờ I/O. Tín hiệu hữu ích có thể là:

- **Queue backlog trên mỗi worker** và tốc độ nhập/xử lý thực tế.
- **Age of oldest message** so với SLO chờ.
- **Throughput mỗi worker**, p95 thời gian xử lý và số lần retry.
- **Quota/429 của downstream**, độ đầy connection pool, database/CPU/memory.
- **Chi phí**, quota max instance, số worker được phép triển khai.

Một công thức bắt đầu để suy ra worker từ backlog và thời gian xả mục tiêu:

\[
N_{\text{ước tính}}=
\left\lceil
\frac{\lambda_{\text{dự kiến}}+B/T_{\text{xả mục tiêu}}}
{r_{\text{worker hiệu dụng}}}
\right\rceil.
\]

Ví dụ backlog 24.000 job, muốn xả trong 240 giây, tốc độ đến vẫn 20 job/s, mỗi worker xử lý hiệu dụng 5 job/s:

\[
N=\left\lceil\frac{20+24.000/240}{5}\right\rceil
=\lceil24\rceil=24.
\]

**Điều kiện áp dụng:** throughput phải được đo thực tế và chưa nghẽn hệ thống đích. Đặt **min/max worker**, cooldown, giới hạn tăng/giảm và theo dõi độ trễ cấp tài nguyên. Nếu provider trả 429 vì giới hạn 60 job/s thì mở rộng lên 100 worker chỉ gây thêm lỗi và phí.

### Phân luồng ưu tiên

Khi một queue chứa nhiều loại việc, công việc quan trọng có thể bị chặn bởi hàng nghìn tác vụ ít khẩn cấp. Có thể dùng:

- **Queue riêng** cho sự kiện ảnh hưởng quyền lợi khách hàng và queue khác cho analytics/backfill.
- **Worker pool/concurrency riêng** theo mức ưu tiên, bảo đảm tài nguyên tối thiểu cho nhiệm vụ quan trọng.
- **Weighted fair scheduling** khi cần công bằng giữa nhiều tenant hoặc loại việc.
- **Rate limit riêng** theo provider để không vượt quota email, CRM hay PDF.

Không nên để queue ưu tiên cao chiếm toàn bộ compute vô hạn khiến queue thấp không bao giờ được xử lý; định nghĩa SLO và giới hạn cho mỗi loại công việc.

### Khi nào cần giảm mức phục vụ?

Ví dụ hệ thống đang có 24.000 job chờ và provider email chậm: có thể tạm dừng email marketing, giảm tần suất đồng bộ analytics, nhưng vẫn giữ công việc bắt buộc theo quy định và tính đúng của đơn hàng. Nếu backlog ảnh hưởng năng lực chấp nhận giao dịch mới, dùng admission control và thông báo đúng tình trạng. **Từ chối sớm có kiểm soát** có thể tốt hơn nhận mọi thứ rồi mất dữ liệu hoặc trễ nhiều giờ không ai biết.

## 11. Bước chín: lựa chọn hạ tầng và ranh giới vận hành

### Compute, queue và dữ liệu

| Thành phần | Lựa chọn thường cân nhắc | Câu hỏi quyết định |
|---|---|---|
| API | Managed containers, PaaS, VM hoặc serverless | Có stateless không? Số kết nối DB? Scale cold start? |
| Durable queue | Managed queue, broker có retention/ACK hoặc dịch vụ event | Cần fan-out, ordering, độ trễ, DLQ, replay và retention thế nào? |
| Outbox/metadata | Bảng trong relational DB đang quản lý order | Giao dịch với dữ liệu nghiệp vụ có đồng nhất không? Relay quét/CDC tác động tải thế nào? |
| Worker | Serverless function, container worker, batch job, VM | Job chạy bao lâu, bao nhiêu RAM, cần kết nối dài, giới hạn concurrency? |
| File kết quả | Object storage hoặc dịch vụ tài liệu phù hợp | Cách xuất bản, quyền truy cập, thời hạn lưu, checksum? |
| Quan sát | Managed metrics/logs/tracing và alert | Theo dõi được end-to-end, queue age, DLQ và cost/run không? |

**Queue hay stream?** Một queue công việc đơn giản phù hợp khi muốn giao mỗi task cho một consumer xử lý. Pub/sub hoặc event streaming phù hợp hơn khi cần nhiều nhóm tiêu thụ độc lập, khả năng replay lịch sử, consumer group hoặc thông lượng sự kiện lớn. Chọn dựa trên ngữ nghĩa delivery, retention, ordering và chi phí vận hành; không thêm event streaming chỉ vì “sẽ có thể dùng sau”.

### Mạng, quyền truy cập và bảo mật

- Đặt worker và database trong mạng/vùng truy cập phù hợp, hạn chế inbound công khai. Cho phép egress đến bên thứ ba qua đường có kiểm soát, quan sát được lỗi mạng/NAT.
- Dùng **service identity/IAM** riêng: API có quyền ghi nghiệp vụ/outbox; relay có quyền đọc outbox và publish queue; worker có quyền đọc queue và đúng storage/API cần thiết; consumer không mặc định có quyền chỉnh sửa mọi đơn.
- Mã hóa dữ liệu khi truyền và khi lưu; quản lý key và secret, xoay khóa, kiểm tra quyền truy cập.
- Hạn chế payload queue chứa dữ liệu cá nhân; dùng \`order_id\` hoặc tham chiếu với quyền truy xuất thích hợp. Log nên loại hoặc che PII.
- Đặt retention cho queue, DLQ, file PDF, log và bản ghi idempotency theo chính sách nghiệp vụ/pháp lý.
- Xác định owner cho API, queue, worker, outbox, DR, dashboard và hóa đơn cloud; dịch vụ quản lý không thay thế trách nhiệm cấu hình và vận hành ứng dụng.

### Không để phát sinh thêm một điểm lỗi trọng yếu

Nếu queue tạm thời không nhận message nhưng order DB còn hoạt động, **outbox giữ event** để relay gửi lại khi queue hồi phục, trong giới hạn dung lượng và thời hạn của hệ thống. Phải quan sát **outbox age/backlog**; nếu backlog có nguy cơ làm database đầy, admission control cần phản ứng. Nếu dùng mô hình producer publish trực tiếp lên queue, không có outbox, phải xác định rõ hợp đồng khi DB commit thành công nhưng queue publish thất bại.

Nếu một queue cần tính sẵn sàng theo nhiều availability zone, phải kiểm tra tính năng thực tế của dịch vụ, ranh giới lỗi, retention và khả năng khôi phục; không suy luận rằng mọi dịch vụ “managed” tự bảo đảm mọi RTO/RPO ứng dụng.

## 12. Bước mười: quan sát và quy trình vận hành

### Các chỉ số cốt lõi

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| **API** | RPS, accepted/rejected, 429/503, p50/p95/p99 latency, inflight requests | Hệ thống có nhận đúng mức và phản hồi đúng trạng thái không? |
| **Outbox** | Event chưa gửi, tuổi event cũ nhất, publish error/latency | Có nguy cơ mất khả năng phát event đúng hạn? |
| **Queue** | Incoming rate, processed rate, depth, oldest age, redelivery count | Có backlog tăng, vi phạm SLO hay retry loop? |
| **Worker** | Active/concurrency, job latency p95, success/failure, CPU/RAM, timeout | Công suất xử lý thực tế và giới hạn nằm ở đâu? |
| **Downstream** | 429, timeout, circuit breaker open, connection pool, quota | Có đang đẩy quá tải sang hệ thống khác? |
| **DLQ** | Số message, tuổi message, nguyên nhân lỗi, tốc độ xử lý lại | Có công việc chưa hoàn thành bị bỏ quên? |
| **Nghiệp vụ** | Số đơn được xác nhận, hóa đơn chưa tạo, thông báo trễ, điểm cộng lỗi | Khách hàng thực sự chịu ảnh hưởng gì? |
| **Chi phí** | Worker-hours, queue requests/storage, egress, log, cost per 1.000 jobs | Chi phí có phù hợp ngân sách và giá trị không? |

Một alert “queue depth > 10.000” có thể hữu ích nhưng không đủ. Nếu throughput rất lớn và xử lý trong một phút thì backlog này có thể bình thường; nếu backlog nhỏ nhưng message cũ trên 30 phút thì đó lại là sự cố. Ưu tiên cảnh báo **tuổi message, độ trễ nghiệp vụ, tốc độ tăng backlog, tỷ lệ lỗi và khả năng xả trước deadline**.

### Runbook xử lý tăng backlog

1. **Xác minh tác động:** đơn hàng còn được ghi nhận không, tỷ lệ 429/503 bao nhiêu, thông báo/hóa đơn trễ đến mức nào?
2. **Đọc tín hiệu:** so sánh tốc độ đến \(\lambda\), tốc độ xử lý \(\mu\), queue age, retries, DLQ, outbox age và quota downstream.
3. **Khoanh vùng:** worker thiếu compute, lỗi deploy, provider chậm, database cạn kết nối, queue limit hay bị hot partition?
4. **Giảm tác động an toàn:** hạ concurrency khi provider bị throttling; tăng worker khi có headroom; tạm dừng công việc ít ưu tiên; bật backpressure/giới hạn đầu vào theo chính sách.
5. **Chặn nhân đôi tác động:** không replay DLQ hàng loạt khi chưa xác minh idempotency, không purge queue để giảm dashboard, không nới giới hạn vô hạn.
6. **Xác nhận phục hồi:** backlog giảm theo dự báo, oldest age trở lại SLO, số sự kiện thiếu/duplicate được đối soát, chi phí về mức bình thường.
7. **Cải tiến:** lưu timeline, nguyên nhân gốc, ngưỡng cảnh báo và action owner; điều chỉnh benchmark hoặc capacity plan.

### SLO nên được diễn đạt từ góc nhìn người dùng

Ví dụ một bộ SLO cần thống nhất:

- **API tiếp nhận:** p95 latency dưới 300 ms **trong dải tải được cam kết** và sau khi đã xác định chính xác endpoint/SLI; việc thanh toán có SLA riêng.
- **Thông báo/hóa đơn:** 95% event đủ điều kiện hoàn tất trong 10 phút kể từ khi đơn xác nhận.
- **Tính đúng:** các giao dịch tài chính và điểm thưởng có cơ chế đối soát, idempotency và sửa sai; không khẳng định “không bao giờ có duplicate” nếu hệ thống đích chưa bảo đảm.
- **Khôi phục:** thất bại một worker không làm mất event đã lưu bền vững, có thể thử lại; đối với sự cố diện rộng, xác định RTO/RPO và diễn tập.

Không được coi retry thành công sau 20 phút là “đạt SLO 10 phút” chỉ vì cuối cùng đã gửi được email.

## 13. Đánh đổi theo Well-Architected

| Trụ cột | Cách kiến trúc hỗ trợ | Đánh đổi cần thẩm định |
|---|---|---|
| **Operational Excellence** | Tách API/worker, có dashboard, runbook, CI/CD và on-call | Tăng số thành phần cần owner, schema, logging, cách phát lại |
| **Security** | IAM riêng từng vai trò, queue private, encryption, payload tối thiểu | Nhiều identity và luồng dữ liệu phải cấu hình/kiểm toán |
| **Reliability** | Durable queue + outbox + retry + DLQ, cô lập lỗi nhà cung cấp | At-least-once tạo duplicate; backlog quá lớn vẫn có thể vi phạm deadline |
| **Performance Efficiency** | API không chờ side effect, worker scale theo queue, bounded concurrency | Cold start và latency bất đồng bộ; database và downstream vẫn có thể nghẽn |
| **Cost Optimization** | Worker scale-to-zero khi rảnh, xử lý theo nhu cầu | Queue, lưu trữ, log, retry, egress và headroom tăng chi phí |
| **Sustainability** | Tắt compute nền khi không có việc, tránh overprovision kéo dài | Retry storm, dữ liệu nhân bản và worker dư gây lãng phí tài nguyên |

**Cân nhắc quan trọng:** độ tin cậy và hiệu năng end-to-end không tự cải thiện khi thêm queue. Bất đồng bộ đổi cách biểu hiện của vấn đề: từ HTTP timeout có thể thành **queue latency hoặc công việc chưa hoàn tất**. Thiết kế cần làm các trạng thái này **quan sát được và có người chịu trách nhiệm**.

### Bài toán chi phí ngắn

Giả định giá compute hiệu dụng của một worker là **0,20 đơn vị tiền/giờ**, có **24 worker chạy trong 15 phút** để xử lý burst và backlog:

\[
C_{\text{compute}} = 24\times 0{,}25\times0{,}20=1{,}20
\]

đơn vị tiền. Đây chỉ là minh họa cho phần compute của đợt tải, **chưa phải tổng chi phí**. Muốn so sánh với chạy cố định 24 worker cả ngày cần cộng queue/broker, retention, database I/O, file storage, log/tracing, egress, hỗ trợ, nhân lực và chi phí do job retry. Đặt min worker và autoscaling theo nhu cầu thực tế, không mặc định 24 worker luôn bật cả ngày.

## 14. Kế hoạch triển khai theo từng giai đoạn

Thay đổi từ đồng bộ sang bất đồng bộ tác động hành vi API và dữ liệu. Tránh chuyển toàn bộ hệ thống trong một lần.

| Giai đoạn | Thay đổi | Kiểm chứng trước khi tiếp tục |
|---|---|---|
| **1. Đo baseline** | Thu thập p95 API, RPS, thời gian provider, connection pool, lỗi và chi phí | Biết rõ nút thắt và dải tải |
| **2. Tách một side effect ít rủi ro** | Ví dụ gửi email đơn hàng qua outbox + queue + worker | Event bền vững, retry không mất, duplicate được xử lý |
| **3. Thêm bảo vệ tải** | Rate limit theo tenant, admission control, bounded concurrency | Đạt giới hạn cam kết và không làm sập DB/provider |
| **4. Mở rộng các side effect khác** | PDF, loyalty, analytics theo mức ưu tiên và ownership | SLO riêng, dữ liệu đối soát, DLQ có người xử lý |
| **5. Autoscale và quan sát** | Scale theo queue age/backlog, alert và ngân sách | Tải đỉnh không vi phạm SLO khi diễn tập |
| **6. Go-live có kiểm soát** | Canary/feature flag, rollout từng nhóm, runbook | So sánh baseline, theo dõi lỗi và hành vi người dùng |

### Khả năng quay lại

Rollback code không đơn giản nếu event đã được phát. Trước khi bật luồng mới, xác định:

- Queue có thể còn event chưa xử lý sau khi tắt feature flag.
- Chạy lại handler đồng bộ cùng lúc với worker có thể gây **hai side effect**.
- Phiên bản schema sự kiện cũ và mới có tương thích không?
- Có thể cho worker **drain** số message còn lại, dừng producer, và khôi phục từ điểm nào?
- Khi cần sửa sai nghiệp vụ, có cần job đối soát hoặc bút toán bù (compensation)?

Một phương án giảm rủi ro là triển khai **consumer ở chế độ shadow/dry-run** hoặc theo tỷ lệ nhỏ khi loại side effect cho phép, sau đó mở rộng khi kết quả đối soát đúng. Với dữ liệu thanh toán hoặc khách hàng, shadow không được phép phát sinh side effect thật ngoài kiểm soát.

## 15. Kế hoạch load test và failure injection

Bài thiết kế chỉ được xem là hoàn chỉnh khi có bằng chứng từ kiểm thử:

| Kịch bản | Cách chạy | Tiêu chí nghiệm thu |
|---|---|---|
| **Tải thường** | Giữ mức RPS ngày thường đủ lâu | API, queue, DB và downstream ổn định; không rò backlog |
| **Burst 10 lần** | Tăng từ 400 lên 4.000 RPS trong 5 phút | Admission/429/503 theo chính sách; tác vụ bền vững; thời gian xử lý trong SLO đã duyệt |
| **Provider email lỗi** | Trả 429/5xx hoặc timeout trong một khoảng | Worker backoff, không retry storm; queue/DLQ có cảnh báo |
| **Worker chết sau side effect** | Giết worker sau khi gửi email/PDF, trước ACK | Replay không làm side effect sai hoặc có đối soát rõ |
| **Relay chết sau publish** | Giả lập broker ACK rồi relay crash trước cập nhật DB | Duplicate event được consumer xử lý an toàn |
| **Database chậm/đầy kết nối** | Giới hạn connection pool hoặc tăng latency DB | Admission không báo nhận giả; không làm mất giao dịch |
| **Queue tạm không nhận** | Chặn publish trong thời gian có kiểm soát | Outbox lưu event, cảnh báo age, phát lại sau phục hồi |
| **Message sai schema** | Chèn event không hợp lệ đã kiểm soát | Quarantine/DLQ đúng, không retry vô hạn |
| **Đơn bị cập nhật lệch thứ tự** | Giao event version cũ sau version mới | Không ghi đè trạng thái mới bằng trạng thái cũ |
| **DLQ replay** | Sửa lỗi rồi replay một tập nhỏ | Không nhân đôi điểm thưởng/email ngoài hợp đồng; audit đầy đủ |
| **Quota compute/downstream** | Hạ max worker hoặc quota đối tác | Có tín hiệu backpressure và thời gian phục hồi tính được |

**Go/no-go:** Chỉ cho phép rollout rộng khi bản ghi outbox/queue không bị mất, cơ chế duplicate đã được thử, các chức năng thiết yếu đúng nghiệp vụ, có người trực nhận cảnh báo và SLO đạt trong dải tải đã cam kết. Nếu không, ghi rõ giới hạn an toàn và phạm vi rollout nhỏ hơn để tiếp tục cải thiện.

## 16. Bài tập thiết kế độc lập

Giả sử một nền tảng đặt vé có các yêu cầu sau:

- Trung bình **30 giao dịch/giây**, tăng lên **300 giao dịch/giây** trong 8 phút khi mở bán.
- Giữ chỗ và kết quả thanh toán phải đúng; khách không được bị giữ tiền hai lần vì client retry.
- Sinh vé PDF, gửi email và ghi thống kê có thể hoàn tất trong **15 phút**.
- Worker xử lý tạo vé được benchmark ở **3 job/giây**, giới hạn tối đa **36 worker**; hệ thống gửi email có quota **80 yêu cầu/giây**.
- Đội vận hành có tối đa 3 người trực luân phiên; muốn giảm chi phí hạ tầng khi không có đợt bán vé.

Hãy trình bày một bản thiết kế gồm:

1. **Ranh giới nghiệp vụ:** bước nào đồng bộ, bước nào bất đồng bộ? Những trạng thái nào được trả qua API khi thanh toán chưa kết luận?
2. **Sơ đồ kiến trúc:** edge/admission, xử lý giữ chỗ/thanh toán, database, outbox, queue, worker, DLQ, status endpoint, metrics/alerts.
3. **Sizing:** với giả định một giao dịch tạo một job PDF, hãy tính tốc độ đến và công suất 36 worker; ước lượng backlog tăng trong 8 phút nếu worker có mặt ngay và không có retry, rồi ước lượng thời gian xả khi tải về mức trung bình.
4. **Kiểm soát rủi ro:** khóa idempotency ở API và worker, chính sách retry, cách tránh cộng/trừ hoặc giữ chỗ trùng, xử lý message out of order, giới hạn quota email.
5. **Vận hành:** tối thiểu 6 metric, 3 alert, owner của từng thành phần, runbook khi queue age vượt 15 phút.
6. **Well-Architected:** chọn ít nhất 3 trụ cột, giải thích đánh đổi giữa độ tin cậy, hiệu năng, chi phí và công sức quản trị.

### Gợi ý lời giải và kiểm tra phép tính

Nếu mỗi giao dịch phát sinh **một job PDF** và không có thất bại:

\[
\lambda_{\text{đỉnh}}=300\text{ job/s},\qquad
\mu=36\times3=108\text{ job/s}.
\]

Với đỉnh kéo dài \(8\times60=480\) giây:

\[
B_{\text{tăng}}=(300-108)\times480=92.160\text{ job}.
\]

Khi về 30 job/s, công suất xả ròng là \(108-30=78\) job/s:

\[
t_{\text{xả}}=\frac{92.160}{78}\approx1.181{,}5\text{ giây}
\approx19{,}7\text{ phút}.
\]

Kết quả này cho thấy **36 worker không thể xả hết backlog trong 15 phút sau khi đỉnh kết thúc** với giả định đang dùng. Nhưng nó **chưa đủ để kết luận tỷ lệ job vi phạm SLO 15 phút**, vì SLO đo từ lúc mỗi vé được xác nhận và phụ thuộc thời điểm phát sinh, thứ tự queue, độ trễ thực tế và khả năng mở rộng. Cần mô phỏng hoặc đo **end-to-end latency theo từng job**. Để có biên an toàn, đội có thể tối ưu tốc độ tạo vé, nâng giới hạn worker nếu được phép, giảm công việc trên critical path, dùng cơ chế ưu tiên có kiểm soát hoặc thương lượng lại mục tiêu với nghiệp vụ.

Quota email **80 request/s** là một nút thắt riêng: dù tạo PDF đạt 108 job/s, vẫn phải giới hạn worker gửi email hoặc tách queue/worker pool riêng, tránh 429 và retry storm. Nếu gộp hai tác vụ vào một worker tuần tự, throughput thực tế có thể thấp hơn mô hình đơn giản. Không nên chạy giữ chỗ/thanh toán trên cùng cơ chế bất đồng bộ mà chưa chứng minh tính đúng và khả năng bồi hoàn.

### Rubric tự đánh giá (100 điểm)

| Thành phần | Điểm tối đa | Dấu hiệu đạt |
|---|---:|---|
| Đúng hợp đồng nghiệp vụ và trạng thái API | 20 | Không nhận giả; thanh toán/giữ chỗ đúng; status rõ |
| Kiến trúc bền vững và kiểm soát duplicate | 20 | Outbox/queue/worker, idempotency, ACK và DLQ hợp lý |
| Sizing và bảo vệ burst | 20 | Công thức đúng; nêu bottleneck và quota downstream |
| Quan sát, runbook và ownership | 20 | Metrics/alerts có tác dụng và người chịu trách nhiệm |
| Bảo mật, chi phí, Well-Architected | 20 | Có đánh đổi thực tế, không tối ưu một chiều |

## 17. Checklist khi trình bày phương án trước hội đồng thiết kế

- [ ] Đã phân định **accepted / business completed / side effects completed**; response HTTP không gây hiểu nhầm.
- [ ] Chức năng bắt buộc đồng bộ vẫn bảo toàn nghiệp vụ, đặc biệt giao dịch thanh toán và dữ liệu tồn kho.
- [ ] Điểm chấp nhận yêu cầu có cơ chế **ghi bền vững**, không chỉ đặt vào bộ nhớ tiến trình.
- [ ] Có quyết định rõ về outbox hoặc cách nhất quán giữa DB và queue; hiểu rằng event có thể bị giao lại.
- [ ] Consumer idempotent hoặc có quy trình đối soát side effect; không tuyên bố exactly-once không có bằng chứng.
- [ ] Rate limit, admission control, backpressure và giới hạn concurrency phù hợp quota DB/downstream.
- [ ] Đã tính throughput, backlog, thời gian xả và **độ trễ end-to-end**, kể cả autoscaling lag, retry và lỗi.
- [ ] Có retry hữu hạn, backoff/jitter, timeout, DLQ và phương án replay an toàn.
- [ ] Có kế hoạch xử lý thứ tự sự kiện, schema version, poison message và dữ liệu đến muộn nếu cần.
- [ ] IAM, secret, encryption, mạng, logging dữ liệu nhạy cảm và retention được xác định.
- [ ] Có metrics API–outbox–queue–worker–downstream, dashboard, alert, runbook và owner cụ thể.
- [ ] Đã thử peak load, worker crash, queue outage, provider 429, duplicate và rollback.
- [ ] Có so sánh chi phí managed queue/worker, storage, egress, retries và công vận hành.
- [ ] Các lựa chọn được giải thích theo **Well-Architected** và SLO đã xác nhận với nghiệp vụ.

**Điểm cần nhớ:** Xử lý bất đồng bộ là một công cụ kiến trúc để **cô lập thời gian xử lý và hấp thụ burst trong giới hạn có thể kiểm soát**. Một phương án tốt luôn đi cùng hợp đồng trạng thái chính xác, công việc được lưu bền vững, xử lý lặp an toàn, backpressure, số liệu capacity và trách nhiệm vận hành rõ ràng.
