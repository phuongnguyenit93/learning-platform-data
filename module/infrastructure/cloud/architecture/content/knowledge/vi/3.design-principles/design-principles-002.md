# Thiết kế cho lỗi, thay đổi và nhu cầu tăng trưởng

> **Chương:** Nguyên lý thiết kế  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai; cân nhắc độ tin cậy, bảo mật, khả năng mở rộng, chi phí, vận hành và đánh giá theo nguyên tắc Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **lỗi, thay đổi và tăng trưởng** phải được xem là trạng thái bình thường trong vòng đời hệ thống đám mây.
2. Phân tích miền lỗi, điểm lỗi đơn, chuỗi phụ thuộc và giới hạn chịu lỗi của một kiến trúc.
3. Chọn biện pháp phù hợp: dự phòng, cách ly lỗi, timeout, retry có kiểm soát, idempotency, hàng đợi, giảm cấp dịch vụ, sao lưu và khôi phục.
4. Thiết kế thay đổi an toàn bằng ranh giới module, hợp đồng tương thích, Infrastructure as Code, triển khai tăng dần, di chuyển dữ liệu và khả năng quay lui.
5. Ước tính năng lực, chọn phương thức mở rộng compute/dữ liệu và kiểm chứng khả năng ứng phó tải tăng đột ngột.
6. Giải thích đánh đổi giữa độ tin cậy, tốc độ thay đổi, độ phức tạp và chi phí; đánh giá theo tư duy Well-Architected.

## 1. Ba điều chắc chắn của hệ thống đang hoạt động

Một ứng dụng có thể chạy tốt lúc trình diễn nhưng chưa đủ điều kiện vận hành thật. Máy chủ bị thay thế; mạng mất gói hoặc tăng độ trễ; database quá tải; nhà cung cấp thanh toán tạm ngừng; nhóm phát triển phát hành phiên bản mới; lượng người dùng tăng nhanh hơn dự kiến. Kiến trúc cần tính đến những tình huống đó trước khi chúng trở thành sự cố nghiêm trọng.

| Hướng thiết kế | Câu hỏi cần trả lời | Kết quả mong đợi |
|---|---|---|
| **Cho lỗi** (*design for failure*) | Nếu một thành phần, kết nối hoặc miền hạ tầng lỗi, hệ thống còn làm được gì? | Giới hạn phạm vi ảnh hưởng, giữ dữ liệu đúng, phát hiện và phục hồi |
| **Cho thay đổi** (*design for change*) | Nếu sửa nghiệp vụ, API, schema hay hạ tầng, làm sao phát hành có kiểm soát? | Thành phần ít phụ thuộc, tương thích, kiểm thử và có đường quay lui |
| **Cho tăng trưởng** (*design for scale*) | Nếu người dùng, yêu cầu, dữ liệu và tác vụ nền tăng, điểm nghẽn nằm ở đâu? | Mở rộng theo nhu cầu trong giới hạn hiệu năng, vận hành và chi phí |

Ba hướng tác động lẫn nhau. Tăng số instance để mở rộng có thể làm cạn kết nối database; triển khai đồng loạt phiên bản lỗi có thể đánh sập mọi instance; retry không kiểm soát biến lỗi nhỏ thành sự cố toàn hệ thống. Vì vậy không thể chỉ bật autoscaling hoặc dự phòng hai máy rồi xem kiến trúc đã bền vững.

### 1.1. Bắt đầu từ tác động nghiệp vụ

Giả sử một **nền tảng đặt lịch khám** gồm các luồng tra cứu lịch, giữ chỗ, xác nhận đặt lịch và gửi thông báo:

- **Đặt lịch:** không được ghi trùng bác sĩ/khung giờ; phải an toàn khi người dùng gửi lại yêu cầu.
- **Tra cứu:** cần phản hồi nhanh, nhưng có thể chấp nhận dữ liệu hơi cũ trong giới hạn nghiệp vụ đồng ý.
- **Email/SMS:** có thể gửi trễ mà không làm mất giao dịch đặt lịch đã hoàn tất.
- **Báo cáo quản trị:** có thể tạm ngừng khi quá tải để dành năng lực cho giao dịch chính.

Những khác biệt này quyết định việc nào phải đồng bộ, việc nào có thể xử lý sau, dữ liệu nào là nguồn sự thật và khi nào chấp nhận giảm cấp dịch vụ.

### 1.2. Đặt mục tiêu đo được

| Khía cạnh | Mục tiêu minh họa | Phải làm rõ trước khi cam kết |
|---|---|---|
| Khả dụng | 99,9% request đặt lịch hợp lệ thành công trong 30 ngày | Đo từ đâu, lỗi nào thuộc phạm vi và timeout có tính thất bại không? |
| Độ trễ | p95 API tra cứu dưới 400 ms tại tải mục tiêu | Từ khu vực client nào, dữ liệu và cơ cấu endpoint nào? |
| Tải đỉnh | 600 request/giây | Tỷ lệ đọc/ghi, độ đồng thời và thời gian duy trì đỉnh? |
| Khôi phục | RTO 60 phút, RPO 15 phút khi mất database chính | Có bao gồm mất cả region hay xóa nhầm dữ liệu không? |
| Thay đổi | Phát hành API không cần dừng toàn hệ thống | Có chạy song song phiên bản cũ/mới và rollback được không? |
| Chi phí | Ngân sách tháng và ngưỡng cảnh báo | Có tính dự phòng, log, backup, egress và chi phí giờ cao điểm không? |

Các giá trị trên **chỉ là giả định phục vụ bài học**, không phải tiêu chuẩn cho mọi hệ thống.

- **SLI (Service Level Indicator):** chỉ số đo thực tế, như tỷ lệ request thành công.
- **SLO (Service Level Objective):** mục tiêu cho SLI trên cửa sổ đo cụ thể.
- **RTO (Recovery Time Objective):** thời gian tối đa mục tiêu để khôi phục sau một loại sự cố xác định.
- **RPO (Recovery Point Objective):** mức mất dữ liệu mới nhất tối đa chấp nhận, biểu diễn bằng thời gian, theo loại sự cố xác định.
- **Error budget:** phần sai lệch cho phép so với SLO, có thể dùng để cân bằng tốc độ thay đổi và đầu tư độ tin cậy.

Ví dụ, SLO 99,9% trong khoảng 30 ngày tương ứng khoảng **43,2 phút** ngân sách không khả dụng theo cách tính thời gian lý tưởng; kết quả thực tế còn phụ thuộc định nghĩa SLI và cách đo. RTO/RPO phải gắn với kịch bản cụ thể: mất một instance, mất một zone, xóa nhầm dữ liệu và mất toàn region cần phương án khác nhau.

## 2. Thiết kế cho lỗi: không giả định phụ thuộc luôn hoạt động

### 2.1. Lập bản đồ miền lỗi và chuỗi phụ thuộc

**Miền lỗi (failure domain)** là tập thành phần có thể cùng hỏng vì một nguyên nhân: một process, VM, node, tuyến mạng, availability zone, region hoặc hệ thống quản trị dùng chung. Hai app instance trên cùng VM không giúp chịu lỗi VM; hai app ở hai zone vẫn có điểm lỗi đơn nếu cùng phụ thuộc database chỉ chạy trong một zone.

~~~mermaid
flowchart LR
    C[Người dùng] --> E[DNS / Edge / HTTPS Load Balancer]
    E --> A[Booking API]
    A --> DB[(Database)]
    A --> IDP[Identity provider]
    A --> Q[(Queue)]
    Q --> W[Notification worker]
    W --> S[Email / SMS provider]
    A --> OBJ[(Object storage)]
~~~

Với từng mũi tên trong sơ đồ, đặt năm câu hỏi: nếu đích không trả lời thì phía gọi chờ bao lâu; nếu mất response sau khi giao dịch thành công thì nhận biết thế nào; nếu gửi lại có tạo hiệu ứng lặp không; nhiều request lỗi có chiếm hết tài nguyên chung không; ai nhận cảnh báo và khôi phục ra sao?

| Sự cố | Hậu quả điển hình | Cơ chế cần cân nhắc |
|---|---|---|
| Một process/VM chết | Mất request đang xử lý | Replica, health check, thay thế instance, idempotency |
| Một zone mất kết nối | Mất một phần compute/dữ liệu | Multi-AZ cho cả đường đi thiết yếu, thử failover |
| Database chậm hoặc cạn kết nối | API giữ connection, request tồn đọng | Connection pool giới hạn, timeout, giảm tải và cảnh báo |
| Provider email ngừng | API chậm nếu gửi đồng bộ | Queue, retry giới hạn, DLQ và cảnh báo |
| Xóa nhầm dữ liệu | Replica có thể sao chép cả thao tác xóa | Backup độc lập, point-in-time recovery nếu có, thử restore |
| Phiên bản/cấu hình lỗi | Nhiều instance cùng suy giảm | Canary/rolling deployment, metric và rollback |
| Tải tăng đột ngột | Hết CPU, worker, quota, DB capacity | Admission control, autoscaling, backpressure |

**Dự phòng không đồng nghĩa độc lập:** replica có thể dùng chung DNS, IAM, khóa, quota, cấu hình, pipeline hoặc database. Phải xét lỗi tương quan, không chỉ đếm số instance.

### 2.2. Dự phòng và phục hồi phải đúng phạm vi

- **Replicas + load balancing:** phân phối yêu cầu và tránh phụ thuộc một instance; app nên stateless đối với session quan trọng, hoặc lưu trạng thái ở hệ thống dùng chung thích hợp.
- **Multi-AZ:** giảm ảnh hưởng của lỗi một zone nếu mọi phụ thuộc cốt lõi thực sự có cấu hình tương ứng.
- **Managed service HA:** giảm công việc quản trị và có thể hỗ trợ failover; cần hiểu thời gian chuyển đổi, ngắt kết nối, độ trễ replication và giới hạn dịch vụ.
- **Backup/restore:** phục hồi dữ liệu sau lỗi logic hoặc sự cố lớn; cần bảo vệ bản sao lưu khỏi thao tác xóa/ghi đè và thử khôi phục.
- **Multi-region DR:** cân nhắc nếu phải chịu lỗi toàn region hoặc đáp ứng yêu cầu địa lý; đánh đổi dữ liệu, định tuyến, độ phức tạp và chi phí.

Phân biệt **high availability** (tiếp tục phục vụ trong miền lỗi thiết kế), **disaster recovery** (khôi phục sau sự cố vượt khả năng chịu lỗi thông thường) và **data correctness** (không ghi sai, mất hoặc trùng trạng thái nghiệp vụ). Một hệ thống luôn trả HTTP 200 nhưng đặt trùng lịch vẫn không đáng tin cậy.

### 2.3. Ngăn lỗi lan truyền

Nếu mọi request đều chờ không giới hạn một dependency chậm, thread/connection pool sẽ cạn, rồi những chức năng khác cũng hỏng.

| Cơ chế | Tác dụng | Rủi ro khi dùng sai |
|---|---|---|
| **Timeout/deadline** | Chặn việc giữ tài nguyên vô hạn, giới hạn thời gian toàn luồng | Timeout từng tầng cộng dồn vượt deadline client |
| **Retry giới hạn** | Vượt lỗi tạm thời nếu thao tác an toàn khi thử lại | Retry vô hạn ở nhiều tầng, tăng tải khi dependency đang quá tải |
| **Exponential backoff + jitter** | Giãn các lần thử, giảm tình trạng thử lại đồng loạt | Không giới hạn backoff/deadline |
| **Circuit breaker** | Tạm ngừng gọi dependency đang lỗi liên tục, thử phục hồi có kiểm soát | Không có cảnh báo, fallback hoặc phục hồi |
| **Bulkhead** | Cách ly pool tài nguyên để một chức năng không làm nghẽn toàn hệ thống | Dùng chung pool không giới hạn cho mọi chức năng |
| **Rate limit/load shedding** | Từ chối sớm lượng tải quá sức xử lý | Nhận hết request rồi hàng loạt timeout tại DB |
| **Backpressure** | Buộc upstream giảm tốc khi downstream bão hòa | Queue phình vô hạn, độ trễ tăng không kiểm soát |

Ví dụ cách phân ngân sách thời gian, **không phải cấu hình bắt buộc**:

~~~text
Deadline toàn request phía client: 3 giây.
Database query: có timeout và connection pool giới hạn.
Lời gọi dịch vụ ngoài: timeout ngắn, retry tối đa 1-2 lần khi an toàn.
Retry: dùng backoff + jitter, không vượt deadline còn lại.
Dependency không thiết yếu lỗi: hoãn/bỏ chức năng phụ có thông báo phù hợp.
Dependency thiết yếu lỗi: trả lỗi rõ ràng, đo được, không báo thành công giả.
~~~

Phải đo độ trễ thật và xem hành vi của từng dependency. Một request gốc có 3 lần retry tạo tối đa **4 lần gọi** tới dependency; retry ở nhiều tầng có thể khuếch đại tải mạnh hơn. Cần hạn chế retry ở tầng phù hợp và ưu tiên các thao tác idempotent.

**Lỗi response không chứng minh thao tác thất bại.** Ví dụ hệ thống thanh toán đã thu tiền nhưng response bị mất; gọi lại không có khóa idempotency có thể thu tiền lần hai. Với mọi thao tác có hiệu ứng nghiệp vụ, thiết kế cách nhận biết giao dịch đã thực hiện hoặc tra cứu trạng thái trước khi gửi lại.

### 2.4. Giảm cấp dịch vụ có chủ đích

Khi quá tải, nền tảng đặt lịch có thể ngừng xếp hạng/gợi ý, dùng cache cho dữ liệu đọc cho phép cũ trong khoảng ngắn, hoãn gửi thông báo và hạn chế request báo cáo. API phải giữ được ưu tiên dành cho **ghi booking đúng và xác thực an toàn**. Nếu không thể commit giao dịch, phải trả lỗi hoặc trạng thái chưa xác nhận; không được báo đặt lịch thành công. Không bỏ qua phân quyền để tăng thông lượng.

Đáp ứng quá tải còn có thể là trả HTTP 429 cho request vượt hạn mức và hướng dẫn thử lại theo chính sách. Trả lỗi nhanh, rõ ràng và có đo lường thường tốt hơn chờ vô hạn rồi làm cạn toàn bộ tài nguyên.

### 2.5. Bảo vệ dữ liệu khi request và thông điệp bị lặp

Để ngăn hai khách đặt cùng khung giờ, phải bảo vệ bất biến tại chỗ ghi dữ liệu: transaction, unique constraint theo mô hình slot rời rạc hoặc một cơ chế kiểm soát đồng thời phù hợp. Hai request cùng “đọc thấy còn chỗ” rồi ghi riêng không đủ chống race condition.

Một cách triển khai **idempotency** cho tạo booking:

1. Client gửi một khóa idempotency cho đúng một ý định đặt lịch; scope khóa theo người dùng và thao tác.
2. API kiểm tra xác thực, nội dung và trạng thái xử lý của khóa trên kho bền vững.
3. Trong transaction, ghi booking, gắn khóa với kết quả và kiểm tra ràng buộc chỗ để chống trùng.
4. Request lặp cùng khóa và nội dung nhận lại kết quả cũ hoặc trạng thái đang xử lý; cùng khóa nhưng nội dung khác phải bị từ chối.
5. Quy định thời hạn lưu khóa và thời gian retry theo vòng đời giao dịch.

Với xử lý bất đồng bộ, queue có thể giao lại thông điệp. Consumer phải có idempotency/deduplication, retry giới hạn và **dead-letter queue (DLQ)** cho thông điệp xử lý lỗi kéo dài. Nếu muốn commit booking và bảo đảm có sự kiện được phát về sau, dùng **transactional outbox**: ghi sự kiện trong cùng transaction dữ liệu, sau commit dispatcher đọc outbox và đẩy queue. Dispatcher có thể phát trùng nên consumer vẫn phải chống xử lý lặp.

~~~mermaid
sequenceDiagram
    actor U as Người đặt lịch
    participant API as Booking API
    participant DB as Database
    participant O as Outbox dispatcher
    participant Q as Queue
    participant W as Worker
    U->>API: Tạo booking + idempotency key
    API->>DB: Transaction: booking + key + outbox
    alt Slot còn trống
        DB-->>API: Commit thành công
        API-->>U: Booking ID
        O->>DB: Đọc outbox đã commit
        O->>Q: Phát booking.created
        Q->>W: Giao message, có thể lặp
        W->>W: Kiểm tra idempotency
        W-->>U: Gửi thông báo qua provider
    else Xung đột hoặc không hợp lệ
        DB-->>API: Conflict / rollback
        API-->>U: Không tạo booking
    end
~~~

Gửi tới dịch vụ bên ngoài có thể vẫn rơi vào trạng thái bất định giữa “đã gửi” và “đã ghi nhận hoàn thành”. Nếu provider hỗ trợ khóa idempotency hãy dùng; nếu không, quản lý nguy cơ gửi trùng theo chính sách thay vì hứa toàn luồng “exactly once”.

### 2.6. Khôi phục phải được diễn tập

Runbook recovery cần nêu **kịch bản lỗi, người phụ trách, điều kiện kích hoạt, từng thao tác, kiểm tra tính đúng đắn và tiêu chí hoàn thành**. Không đủ nếu chỉ ghi “đã bật backup”.

1. Lỗi một instance: load balancer ngừng gửi traffic sau bao lâu, request dở dang xử lý thế nào?
2. Lỗi một zone: app, DB, queue, network và các phụ thuộc có tiếp tục hoạt động không?
3. Xóa nhầm/corrupt dữ liệu: có backup độc lập hoặc khôi phục đến thời điểm cụ thể không?
4. Lỗi cả region: có phương án DR hay đây là rủi ro được chấp nhận?
5. Lỗi cấu hình/phân quyền: còn cách khôi phục quyền quản trị, điều chỉnh cấu hình, rollback an toàn?

Thử restore phải xác nhận **dữ liệu thực sự đọc/ghi đúng và ứng dụng hoạt động**, không chỉ nhận thông báo job backup thành công. Ghi lại RTO/RPO thực đo, phạm vi dữ liệu đã mất và điều kiện thử. Replica có thể sao chép cả lệnh xóa nhầm, nên replica không thay thế backup.

## 3. Thiết kế cho thay đổi: cập nhật hệ thống mà vẫn tương thích

### 3.1. Ranh giới thành phần quyết định chi phí thay đổi

Khả năng thay đổi không bắt đầu ở công cụ CI/CD; nó bắt đầu từ cách phân chia trách nhiệm:

- Tách **lõi nghiệp vụ** (quy tắc đặt lịch, trạng thái thanh toán) khỏi lớp HTTP và tích hợp với nhà cung cấp.
- Có giao diện/hợp đồng rõ ràng giữa các module; tránh để mọi module tùy ý sửa bảng dữ liệu của nhau.
- Giữ phụ thuộc có hướng và kiểm thử được; không đặt secret hoặc cấu hình môi trường trực tiếp trong mã nguồn.
- Tách microservice khi có lý do cụ thể về ranh giới nghiệp vụ, triển khai/mở rộng độc lập hoặc cô lập lỗi và đội ngũ có khả năng vận hành.

Một **modular monolith** với ranh giới module rõ thường đáp ứng tốt nhu cầu thay đổi ban đầu. Microservice có thể làm tăng số API, phiên bản, network call, observability và transaction phân tán; việc “chia nhỏ” không tự làm kiến trúc linh hoạt.

### 3.2. Duy trì tương thích khi chạy đồng thời nhiều phiên bản

Rolling/canary deployment có giai đoạn **phiên bản cũ và mới cùng hoạt động**. Vì thế API, event và schema phải hỗ trợ giai đoạn chuyển tiếp.

| Loại thay đổi | Cách an toàn thường dùng | Cách dễ gây sự cố |
|---|---|---|
| API | Thêm field tùy chọn, giữ ngữ nghĩa cũ, version cho thay đổi phá vỡ hợp đồng | Xóa/đổi field bắt buộc khi còn client cũ |
| Message/event | Consumer chấp nhận field mới chưa biết, có quy ước version | Thay định dạng bất ngờ làm worker phiên bản cũ lỗi |
| Database | **Expand → migrate/backfill → switch → contract** | Xóa cột cũ cùng lần deploy mã mới |
| Cấu hình | Version hóa, validation, thử ở phạm vi nhỏ | Sửa tay không theo dõi rồi gây drift giữa các môi trường |
| Khóa/bí mật | Xoay khóa với giai đoạn chồng lấp khi giao thức cho phép | Thu hồi khóa cũ trước khi mọi consumer chuyển đổi |

Ví dụ đổi tên cột dữ liệu số điện thoại từ **phone** sang **contact_phone**:

1. **Expand:** tạo contact_phone ở trạng thái có thể bỏ trống, vẫn giữ phone; mã mới cần xử lý dữ liệu ở cả hai dạng.
2. **Migrate:** backfill từng lô để tránh giữ lock lớn; đồng bộ cách ghi trong giai đoạn chuyển tiếp, đo số bản ghi còn thiếu.
3. **Switch:** chuyển việc đọc sang contact_phone sau khi đã kiểm tra dữ liệu và mọi consumer liên quan.
4. **Contract:** chỉ bỏ phone khi không còn phiên bản cũ phụ thuộc và đã hết cửa sổ rollback.

Với schema thực tế, cần đánh giá lock, kích thước dữ liệu, replication, chỉ mục và loại database trước khi chạy migration. **Rollback code không đồng nghĩa rollback dữ liệu**. Một thao tác đã xóa cột hoặc chuyển đổi không đảo ngược cần kế hoạch khôi phục riêng và có thể yêu cầu tạm ngừng một luồng ghi trong cửa sổ kiểm soát.

### 3.3. Triển khai từng phần và có điều kiện dừng

~~~mermaid
flowchart LR
    A[Commit mã / cấu hình] --> B[Build + test + kiểm tra bảo mật]
    B --> C[Triển khai môi trường thử]
    C --> D[Kiểm tra hợp đồng và migration]
    D --> E[Canary tới nhóm nhỏ]
    E --> F{SLI, error rate, latency đạt?}
    F -- Có --> G[Tăng dần traffic]
    G --> H[Hoàn tất phát hành]
    F -- Không --> I[Dừng rollout, rollback hoặc giảm tác động]
~~~

Các chiến lược thường gặp:

- **Rolling deployment:** thay lần lượt nhóm instance; tương đối tiết kiệm capacity nhưng cần xử lý phiên bản cũ/mới cùng hoạt động.
- **Blue-green deployment:** chuẩn bị hai môi trường, sau đó chuyển traffic; chuyển nhanh nhưng tăng chi phí tài nguyên tạm thời và vẫn phải giải quyết tính tương thích của dữ liệu chung.
- **Canary deployment:** phân một phần traffic sang phiên bản mới, đo SLI trước khi tăng tỷ lệ; cần cơ chế routing và metric đại diện.
- **Feature flag:** bật/tắt tính năng theo nhóm hoặc điều kiện; phải quản lý quyền thay đổi, fallback, vòng đời và việc dọn flag cũ.

Một quy trình phát hành an toàn cần xác nhận **thay đổi nào có thể đảo ngược**, trạng thái schema/data sau khi rollback, kế hoạch quan sát, điều kiện tạm dừng và người chịu trách nhiệm. Theo dõi metric nghiệp vụ như booking thành công/trùng/lỗi, cùng error rate, latency và saturation; trạng thái “container Running” chưa đủ để kết luận phát hành thành công.

### 3.4. Infrastructure as Code và kiểm soát thay đổi hạ tầng

Hạ tầng cũng là một phần phiên bản của ứng dụng. **Infrastructure as Code (IaC)** giúp định nghĩa network, compute, IAM, database và observability thành cấu hình được review; CI/CD giúp lặp lại môi trường và kiểm tra tác động trước khi áp dụng.

Quy trình nên bao gồm: kiểm tra cú pháp/chính sách, hiển thị kế hoạch thay đổi, review quyền và dữ liệu, áp dụng từng phạm vi, giám sát kết quả và phát hiện **configuration drift**. IaC không tự bảo đảm an toàn: một thay đổi đúng cú pháp vẫn có thể xóa tài nguyên, mở quyền truy cập hoặc tạo chi phí ngoài dự kiến.

Với thay đổi không thể đảo ngược, hãy dùng chiến lược di chuyển từng bước hoặc thử trên môi trường tách biệt. Đặc biệt thận trọng với thay đổi IAM, route, database và khóa mã hóa vì có thể ảnh hưởng nhiều workload cùng lúc.

### 3.5. Dùng dữ liệu để đánh giá khả năng thay đổi

Những chỉ số hữu ích:

- **Deployment frequency:** tần suất phát hành thành công theo cách đội ngũ định nghĩa.
- **Lead time for changes:** thời gian từ thay đổi mã đến khi chạy trên môi trường mục tiêu.
- **Change failure rate:** tỷ lệ thay đổi dẫn đến suy giảm dịch vụ hoặc cần can thiệp.
- **Failed deployment recovery time:** thời gian khôi phục sau một lần phát hành thất bại.
- **Rollback success:** tỷ lệ diễn tập hoặc tình huống thực tế phục hồi đúng với kế hoạch.

Không chạy theo số lần deploy. Mục tiêu là **thay đổi nhỏ, kiểm chứng được, phản hồi nhanh và phục hồi có kiểm soát**.

## 4. Thiết kế cho tăng trưởng: mở rộng ở đúng nút thắt

### 4.1. Phân biệt scale dọc, scale ngang và elasticity

- **Vertical scaling (scale up):** tăng CPU/RAM/IOPS cho một instance; đơn giản nhưng có giới hạn phần cứng và đôi khi phải dừng/khởi động lại.
- **Horizontal scaling (scale out):** tăng số instance hoặc worker; phù hợp tác vụ phân tán được, cần load balancing và quản lý trạng thái.
- **Elasticity:** điều chỉnh tài nguyên theo nhu cầu; chịu giới hạn bởi thời gian khởi động, metric quan sát, quota và chi phí.

Không phải mọi lớp scale giống nhau. Stateless API thường nhân bản dễ; database có transaction và trạng thái cần xem xét tối ưu query, read replica, partition, nâng tài nguyên hoặc sharding khi thật cần.

### 4.2. Ước lượng capacity theo đơn vị công việc

Một công thức khởi đầu cho số lượng compute instance:

~~~text
Số instance cần thiết
  = ceil(lưu lượng đỉnh / thông lượng bền vững mỗi instance ở mức sử dụng mục tiêu)
~~~

Giả sử kiểm thử tải cho thấy **mỗi instance xử lý được 100 request/giây tại giới hạn hiệu năng**, nhưng đội ngũ chỉ muốn chạy ở **80% năng lực đã đo** để chừa khoảng dự phòng. Khi đó mỗi instance được tính khoảng 80 request/giây. Với tải đỉnh 600 request/giây và cơ cấu request tương tự:

~~~text
ceil(600 / 80) = 8 instance
8 instance × 80 = 640 request/giây tại mức sử dụng mục tiêu
~~~

**Tám instance mới đáp ứng tải bình thường**, chưa chứng minh khả năng chịu lỗi zone. Nếu chia 4 instance ở mỗi trong hai zone và mất một zone, phía còn lại chỉ giữ được 4 × 80 = 320 request/giây ở mức mục tiêu. Muốn **ngay lập tức** chịu 600 request/giây sau sự cố mất một zone, có thể phải giữ đủ 8 instance ở mỗi zone (16 instance khi phân bố cân bằng hai zone), hoặc chấp nhận giảm cấp/rate limit và khoảng trễ scale-up. Quyết định cần xét chi phí, số zone thực sự khả dụng, năng lực database và giới hạn các dịch vụ khác.

Ví dụ chứng minh hai khái niệm khác nhau: **đủ capacity giờ cao điểm** và **đủ capacity khi hỏng một miền lỗi**. Thông lượng thực tế mỗi instance còn tùy tỷ lệ đọc/ghi, truy vấn database, cache hit, payload, latency, GC, network và chính sách connection pooling; phải đo lại trong điều kiện đại diện.

### 4.3. Database và cache có giới hạn riêng

Mở rộng số API instance dễ chuyển nút thắt sang database. Các lựa chọn cần đánh giá theo số liệu:

1. **Quan sát query:** xác định query chậm, N+1, scan toàn bảng, transaction kéo dài, lock contention và cạn connection.
2. **Tối ưu mô hình/chỉ mục:** thêm chỉ mục phục vụ truy vấn quan trọng, nhưng tính cả chi phí ghi và dung lượng.
3. **Cache có chiến lược:** chọn dữ liệu có thể cũ, đặt TTL/invalidation, kiểm soát cache stampede và xử lý cache failure.
4. **Read replica:** phân tải đọc phù hợp, lưu ý độ trễ replication; không dùng replica trễ làm căn cứ duy nhất để xác nhận chỗ còn trống.
5. **Tăng tài nguyên hoặc capacity dịch vụ database:** kiểm tra giới hạn, thời gian bảo trì, dự báo chi phí.
6. **Partition/shard khi có lý do:** giúp chia tải nhưng tăng độ phức tạp transaction, join, query, rebalancing và phục hồi.

Một dịch vụ database quản lý hoặc tự co giãn vẫn có giới hạn connection, I/O, transaction, throughput và quota. Không coi autoscaling API là bằng chứng toàn hệ thống có thể scale vô hạn.

### 4.4. Queue hấp thụ đỉnh tải, không xóa bỏ công việc

Queue cho phép producer và consumer hoạt động với tốc độ khác nhau, nhưng **backlog tăng khi tốc độ đến vượt tốc độ xử lý**.

Giả sử chiến dịch kéo dài 10 phút tạo **400 thông báo/giây**, trong khi worker chỉ xử lý **250 thông báo/giây**, bỏ qua retry và chênh lệch thời gian từng job:

~~~text
Tốc độ tích tụ = 400 - 250 = 150 thông báo/giây
Backlog sau 10 phút = 150 × 600 = 90.000 thông báo

Sau chiến dịch, tốc độ đến trở về 100 thông báo/giây:
Năng lực xử lý backlog còn dư = 250 - 100 = 150 thông báo/giây
Thời gian xả backlog xấp xỉ = 90.000 / 150 = 600 giây (10 phút)
~~~

Nếu nghiệp vụ yêu cầu gửi thông báo trong **2 phút**, cấu hình này không đạt trong đợt cao tải. Cần tăng worker, chia ưu tiên hoặc thống nhất lại SLO. Metric nên có **oldest message age, queue depth, throughput, retry count, DLQ count**; queue depth riêng lẻ có thể che giấu thông điệp cũ tồn tại quá lâu.

### 4.5. Chống quá tải khi chưa kịp scale

Kiến trúc cho tăng trưởng cần xử lý cả tải **ngoài kế hoạch**:

- **Rate limit/quota:** tránh một khách hàng hoặc tenant chiếm hết tài nguyên chung.
- **Admission control:** chỉ tiếp nhận lượng việc có thể hoàn thành trong giới hạn mong muốn.
- **Backpressure:** yêu cầu upstream giảm tốc khi downstream bão hòa.
- **Bảo vệ pool:** giới hạn DB connections, worker, bộ nhớ, queue và số lời gọi đồng thời.
- **Ưu tiên nghiệp vụ:** dành năng lực cho đặt lịch hơn báo cáo hoặc gợi ý.
- **Warm capacity:** giữ phần năng lực dự phòng khi autoscaling cần thời gian khởi tạo.
- **Guardrail chi phí:** ngân sách, cảnh báo, chính sách ngăn scale bất thường và review tăng trưởng.

Autoscaling là một vòng điều khiển có độ trễ. Dùng riêng CPU làm metric khi nghẽn thực ở DB, đặt cooldown sai hoặc chạm quota có thể khiến nhiều instance được tạo nhưng SLO vẫn thất bại. Cần đo **độ bão hòa và thời gian phục hồi từng thành phần**, không chỉ số instance.

## 5. Ví dụ kiến trúc kết hợp cả ba nguyên lý

Với nền tảng đặt lịch, một phương án v1 có thể triển khai như sau:

~~~mermaid
flowchart TB
    U[Web / Mobile] --> EDGE[DNS / CDN / WAF]
    EDGE --> LB[HTTPS Load Balancer]
    subgraph R[Cloud Region]
        subgraph Z1[Availability Zone A]
            A1[Stateless Booking API A]
            W1[Notification Worker A]
        end
        subgraph Z2[Availability Zone B]
            A2[Stateless Booking API B]
            W2[Notification Worker B]
        end
        LB --> A1
        LB --> A2
        A1 --> D[(Managed Relational DB / HA)]
        A2 --> D
        A1 --> O[(Transactional Outbox)]
        A2 --> O
        O --> Q[(Managed Queue + DLQ)]
        Q --> W1
        Q --> W2
    end
    W1 --> P[Email / SMS provider]
    W2 --> P
    D -.-> B[(Backup / PITR)]
    OBS[Metrics / Logs / Traces] -.-> A1
    OBS -.-> A2
    OBS -.-> D
~~~

**Lưu ý khi đọc sơ đồ:**

- Đây là **mô hình logic**, chưa thể hiện subnet, route, IAM, secret, private endpoint, mã hóa, DNS failover và quyền của từng thành phần.
- Outbox thường là bản ghi/bảng thuộc database giao dịch; một dispatcher chạy sau commit đọc bản ghi và gửi tới queue. Mũi tên đi qua outbox biểu diễn quá trình này, không có nghĩa API ghi trực tiếp queue trong cùng giao dịch database.
- Nhãn **HA** và **Backup/PITR** chỉ thể hiện yêu cầu chọn/cấu hình khả năng phù hợp; phải kiểm tra hỗ trợ thực tế của dịch vụ cloud. Dự phòng qua hai zone chưa bảo vệ khỏi mất toàn region hoặc mất dữ liệu do thao tác logic.
- API/worker nên ở mạng riêng hoặc giới hạn đường vào phù hợp; các endpoint công khai cần TLS và xác thực/phân quyền. Bản sao lưu cũng cần chính sách bảo vệ và quyền truy cập riêng.

### 5.1. Ứng xử mong muốn theo từng sự kiện

| Sự kiện | Hành vi nghiệp vụ mong muốn | Cơ chế hỗ trợ | Kiểm chứng |
|---|---|---|---|
| Một API instance chết | Request mới tới instance khỏe; request dở dang có thể gửi lại an toàn | Stateless, health check, idempotency | Dừng instance; đo 5xx, latency, booking trùng |
| Một zone không khả dụng | Các luồng thiết yếu duy trì hoặc phục hồi trong SLO | Multi-AZ, capacity dự phòng, DB/queue HA | Mô phỏng lỗi zone và đo failover |
| Email provider lỗi 20 phút | Booking vẫn được commit, thông báo có thể trễ | Queue, retry/backoff, DLQ | Ngắt provider, đo queue age, retry và gửi trùng |
| Phát hành API mới tăng 5xx | Dừng rollout, giới hạn người dùng bị ảnh hưởng | Canary, metric gate, rollback | Phát hành lỗi có kiểm soát, đo thời gian phát hiện/phục hồi |
| Thêm field dữ liệu booking | Phiên bản cũ và mới cùng hoạt động trong giai đoạn chuyển tiếp | Expand-contract migration | Chạy hai phiên bản song song và thử rollback |
| Lưu lượng tăng gấp 3 | Tăng compute/worker, bảo vệ database và các quota | Autoscale, giới hạn kết nối, admission control | Load/spike test, ghi saturation và chi phí |
| Xóa nhầm booking | Khôi phục và đối soát theo chính sách chấp nhận mất dữ liệu | Backup/PITR, audit, runbook | Restore tách biệt, đo RTO/RPO thực tế |

### 5.2. Đánh đổi phải được ghi rõ

Thiết kế multi-zone thường tăng chi phí dự phòng nhưng giảm rủi ro khi hỏng một zone. Đưa email vào queue giảm phụ thuộc đồng bộ nhưng đòi hỏi quản lý backlog và nguy cơ xử lý lặp. Canary giảm phạm vi ảnh hưởng của phiên bản lỗi nhưng cần phân phối lưu lượng và metric tốt. Read replica tăng năng lực đọc nhưng không bảo đảm dữ liệu vừa ghi được nhìn thấy ngay ở replica. Mỗi quyết định phải có **mục tiêu, phương án khác, chi phí, rủi ro còn lại và bằng chứng**.

Một **Architecture Decision Record (ADR)** minh họa:

~~~text
ADR-012: Tách gửi thông báo khỏi request tạo booking

Bối cảnh:
- API tạo booking phải phản hồi trong SLO đã thống nhất.
- Email provider có thể chậm hoặc tạm ngừng.

Phương án A: Gửi email đồng bộ sau khi đặt lịch.
Phương án B: Commit booking + outbox; queue và worker gửi email sau.

Quyết định: B.
Lợi ích: Booking không phải chờ email; worker có thể scale và retry riêng.
Đánh đổi: Thông báo có thể trễ; phải quản lý backlog, message lặp và DLQ.
Kiểm chứng: Ngắt email provider 20 phút; booking vẫn đúng;
             alert backlog hoạt động; xử lý lặp đúng chính sách.
Xem xét lại khi: SLO gửi thông báo, lưu lượng hoặc chi phí thay đổi.
~~~

## 6. Kiểm tra theo tư duy Well-Architected

**Well-Architected** là phương pháp đặt câu hỏi về chất lượng kiến trúc, xác định rủi ro và cải tiến bằng bằng chứng. Cách nhóm trụ cột khác nhau giữa các nhà cung cấp. Bảng sau dùng **sáu trụ cột quen thuộc của AWS Well-Architected** làm khung tham chiếu, không yêu cầu sử dụng dịch vụ AWS.

| Trụ cột | Câu hỏi đối với lỗi, thay đổi và tăng trưởng | Bằng chứng nên có |
|---|---|---|
| **Operational Excellence** | Có runbook, deployment pipeline, cảnh báo và cải tiến sau sự cố không? | Dashboard, diễn tập, quy trình rollback, postmortem |
| **Security** | Scale/triển khai có làm lộ bí mật, mở rộng quyền hay bỏ kiểm soát không? | IAM least privilege, network policy, mã hóa, quyền CI/CD |
| **Reliability** | Có chịu lỗi trong phạm vi đã cam kết và khôi phục đúng dữ liệu không? | Fault injection, failover/restore test, RTO/RPO, SLO |
| **Performance Efficiency** | Tăng tải làm nghẽn lớp nào, có dự báo và đo được không? | Load test, profiler, capacity model, p95/p99, saturation |
| **Cost Optimization** | Dự phòng và autoscale có đạt mức dịch vụ với tổng chi phí hợp lý? | Budget, allocation tag, chi phí replica/egress/log, owner |
| **Sustainability** | Có hạn chế chạy tài nguyên thừa và dùng tài nguyên hiệu quả không? | Scale-in an toàn, storage lifecycle, dọn workload dư thừa |

Những câu hỏi xuyên trụ cột:

1. Nếu provider bên ngoài lỗi 20 phút, luồng nào được duy trì và người dùng nhìn thấy gì?
2. Nếu tăng gấp ba request, database và quota có theo kịp compute hay không?
3. Nếu bản phát hành mới lỗi, có thể dừng và phục hồi trước khi vượt error budget không?
4. Nếu backup hôm qua thành công, đã có bằng chứng **khôi phục dữ liệu đúng** hay chưa?
5. Nếu phải giữ gấp đôi capacity để chịu lỗi zone, tăng chi phí bao nhiêu và nghiệp vụ có chấp nhận không?

Không đánh giá kiến trúc bằng số lượng công cụ. Bật autoscaling khi DB nghẽn vẫn có thể làm hệ thống sập; có backup nhưng chưa từng thử restore chưa chứng minh đáp ứng RTO/RPO; có canary nhưng không theo dõi metric nghiệp vụ vẫn có thể phát hành lỗi mà không phát hiện.

### 6.1. Ma trận ưu tiên rủi ro

Để quyết định đầu tư trước vào đâu, có thể đánh giá **xác suất xảy ra**, **mức tác động nghiệp vụ**, **khả năng phát hiện** và **thời gian phục hồi**. Không cần áp dụng một con số rủi ro chung cho mọi công ty; nên dùng tiêu chí thống nhất với chủ sản phẩm, an ninh và vận hành.

Ví dụ:

| Rủi ro | Tác động | Độ ưu tiên giả định | Bước xử lý đầu tiên |
|---|---|---|---|
| Booking trùng khi retry | Sai nghiệp vụ cốt lõi, có thể ảnh hưởng khách hàng | Rất cao | Transaction + constraint + idempotency, concurrency test |
| Không restore được backup | Mất dữ liệu hoặc vượt RTO/RPO | Rất cao | Diễn tập restore tách biệt, đối soát dữ liệu |
| Email provider gián đoạn | Thông báo chậm | Trung bình nếu được phép trễ | Queue + retry + DLQ + SLO riêng |
| API thiếu năng lực giờ cao điểm | Mất giao dịch và ảnh hưởng trải nghiệm | Cao | Load test, capacity plan, admission control |
| Rollout không có metric/rollback | Phát hành lỗi ảnh hưởng diện rộng | Cao | Canary gate, runbook rollback, kiểm tra tương thích |

Độ ưu tiên thực tế thay đổi theo mức độ thiệt hại, yêu cầu pháp lý, chi phí và mức độ phụ thuộc. Ma trận là điểm khởi đầu cho thảo luận, không thay thế phân tích rủi ro của từng tổ chức.

## 7. Kế hoạch kiểm chứng kiến trúc bằng thực nghiệm

Đọc sơ đồ và đối chiếu checklist là chưa đủ. Các thử nghiệm nên nối trực tiếp với SLO và rủi ro:

| Phép thử | Cách thử | Chỉ số/bằng chứng |
|---|---|---|
| **Load test** | Tăng tới tải thiết kế với tỷ lệ endpoint và dữ liệu đại diện | p95/p99, error rate, throughput, CPU, DB pool, queue age và chi phí |
| **Spike test** | Tăng tải đột ngột trong thời gian ngắn | Độ trễ autoscale, rate limit, request thành công và hồi phục sau đỉnh |
| **Soak test** | Duy trì tải lâu | Memory/connection leak, tail latency, log/storage tăng trưởng |
| **Instance/zone failure** | Dừng instance hoặc mô phỏng mất zone trong phạm vi kiểm soát | Request lỗi, failover, năng lực còn lại, tính đúng đắn booking |
| **Dependency failure** | Tăng độ trễ hoặc ngắt provider/cache/DB có kiểm soát | Timeout, retry budget, circuit breaker, fallback và cascade |
| **Duplicate/concurrency test** | Gửi cùng yêu cầu/message nhiều lần, tranh chấp một slot | Không booking trùng, xử lý lặp đúng chính sách, có audit |
| **Canary rollback** | Phát hành lỗi có kiểm soát cho một nhóm nhỏ | Phát hiện đúng, rollback/mitigate, dữ liệu/schema vẫn tương thích |
| **Backup restore** | Phục hồi sang môi trường tách biệt và đối soát nghiệp vụ | RTO/RPO thực đo, dữ liệu đúng, quyền và runbook đầy đủ |

Với thử lỗi có chủ đích, bắt đầu ở môi trường an toàn, đặt phạm vi và điều kiện dừng, ghi baseline rồi mới thực hiện. Thử trên sản xuất chỉ khi có kiểm soát vận hành phù hợp. Sau mỗi lần thử, cập nhật runbook, giám sát, capacity model và ADR nếu giả định ban đầu không còn đúng.

### 7.1. Các dấu hiệu khiến phải xem lại kiến trúc

- p95/p99 tăng nhanh khi request/giây chưa tăng nhiều: có thể nghẽn pool, lock hoặc dependency.
- CPU API thấp nhưng request timeout nhiều: kiểm tra DB connection, DNS/network và thread/async queue.
- Scale ra API liên tục nhưng throughput không tăng: có thể hệ thống đạt giới hạn ở DB, queue, quota hoặc upstream.
- Queue depth giảm nhưng oldest message age còn cao: một nhóm message kẹt hoặc consumer bị lỗi retry.
- Rollback API thành công nhưng dữ liệu không đọc được: schema/data migration chưa tương thích.
- Bản sao lưu luôn thành công nhưng restore kéo dài quá RTO: cần sửa kế hoạch DR và runbook.
- Alert đến nhiều nhưng người trực không biết hành động: cần thay alert theo tác động và gắn runbook.

## 8. Bài thực hành: thiết kế để sống sót qua một đợt tăng trưởng

**Tình huống:** Nền tảng đặt lịch hiện dùng một VM công khai chạy cả API và database. Email được gửi trực tiếp trước khi trả response. Dịch vụ xử lý khoảng 5.000 booking/ngày. Một chiến dịch mới có thể làm lưu lượng tra cứu tăng gấp **5 lần trong 15 phút**. Nhóm muốn phát hành tính năng hủy lịch không cần dừng hệ thống và cần tránh đặt trùng khi request được gửi lại. Hiện chưa đo được p95 và thông lượng trên mỗi instance.

Hãy lập đề xuất kiến trúc v1 có các đầu ra:

1. **Yêu cầu đo được:** đề xuất SLI/SLO cho tra cứu và đặt lịch; định nghĩa RTO/RPO riêng cho ít nhất hai kịch bản sự cố; ghi rõ giả định phải xác minh.
2. **Bản đồ lỗi:** vẽ đường đi request, đánh dấu single point of failure và hành vi dự kiến khi VM, DB, zone hoặc email provider lỗi.
3. **Tính đúng đắn:** mô tả transaction/ràng buộc không đặt trùng, xử lý cùng idempotency key được gửi lại và worker nhận message lặp.
4. **Thay đổi:** chọn rolling/canary để phát hành tính năng hủy; mô tả một thay đổi schema theo expand-contract, giai đoạn chạy song song và điều kiện rollback.
5. **Tăng trưởng:** xác định metric cho autoscale API/worker, nút thắt ở DB, chiến lược bảo vệ request cốt lõi, giới hạn chi phí và chính sách kiểm soát backlog.
6. **Kiểm chứng:** ít nhất một load test, một bài thử lỗi dependency, một canary rollback và một restore test. Mỗi bài thử phải có tiêu chí đạt, thông số cần ghi và rủi ro còn lại.

Không đo được thông lượng mỗi instance thì **không bịa số instance**. Hãy dùng công thức capacity và kế hoạch load test để tìm giá trị đầu vào trước khi chốt.

Bảng quyết định mẫu:

| Quyết định | Yêu cầu | Lựa chọn và đánh đổi | Bằng chứng cần thu thập |
|---|---|---|---|
| Tách DB khỏi VM API | Không mất dữ liệu khi app instance lỗi | Managed DB tăng chi phí nền nhưng giảm việc quản trị | Restore/failover, throughput, chi phí |
| Idempotent booking | Không ghi trùng khi request lặp | Cần lưu khóa và giao dịch/ràng buộc dữ liệu | Test concurrent requests và replay |
| Queue thông báo | Booking không chờ email | Thông báo có thể trễ; cần retry/DLQ | Kiểm tra backlog, provider failure |
| Canary + schema tương thích | Phát hành hủy lịch an toàn | Cần telemetry và giai đoạn chuyển schema | Chạy hai phiên bản, kiểm tra rollback |
| Autoscaling API | Đáp ứng tăng tải | Replica tăng tải DB và chi phí | Load/spike test, saturation và cost |

**Tiêu chí hoàn thành:** Người đọc đề xuất phải có thể chỉ ra (a) hệ thống còn hoạt động thế nào khi từng phụ thuộc lỗi; (b) phiên bản cũ/mới đồng tồn tại lúc phát hành ra sao; (c) nút thắt tăng trưởng tiếp theo nằm ở đâu; (d) bằng chứng nào kiểm chứng từng khẳng định.

## 9. Khung ghi nhớ khi thiết kế

- **Lỗi:** xác định miền lỗi, chặn lan truyền, giữ đúng dữ liệu và thử phục hồi thật.
- **Thay đổi:** ranh giới trách nhiệm rõ, tương thích trong giai đoạn chuyển tiếp, triển khai từng phần, có đường quay lui.
- **Tăng trưởng:** đo tải thực, mở rộng đúng lớp nghẽn, tính năng lực khi sự cố và kiểm soát quota, backlog, chi phí.
- **Đánh đổi:** mọi quyết định phải nối với yêu cầu, phương án thay thế, rủi ro còn lại và phép đo xác nhận.

Một kiến trúc có thể bắt đầu đơn giản rồi tiến hóa. Mức dự phòng, tự động hóa và độ phức tạp hợp lý phụ thuộc tác động nghiệp vụ khi lỗi, tốc độ thay đổi mong muốn, quy mô thực tế và kỹ năng vận hành của đội. Chu trình **đo → thử → học → điều chỉnh** mới biến một sơ đồ cloud thành hệ thống có thể vận hành đáng tin cậy.
