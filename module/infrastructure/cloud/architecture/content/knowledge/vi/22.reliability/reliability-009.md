# Phân tích độ sẵn sàng đầu cuối theo chuỗi phụ thuộc

> **Chương:** Độ tin cậy  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào cách đánh giá độ sẵn sàng của một hành trình nghiệp vụ xuyên qua nhiều thành phần và nhà cung cấp, nhận diện điểm lỗi chung, định lượng tác động của phụ thuộc và kiểm chứng các mục tiêu SLO, RTO, RPO theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt availability của một thành phần, một dịch vụ và một hành trình nghiệp vụ đầu cuối.
2. Mô hình hóa dependency graph để xác định thành phần bắt buộc, tùy chọn, nối tiếp, song song, dự phòng và có điểm lỗi chung.
3. Ước tính availability của chuỗi phụ thuộc bằng mô hình xác suất phù hợp và nhận biết giới hạn của các giả định độc lập.
4. Đánh giá ảnh hưởng của timeout, retry, queue, cache, fallback, circuit breaker và graceful degradation tới availability thực tế.
5. Xác định SLI/SLO theo hành trình người dùng; phân biệt availability, latency, correctness, freshness, RTO và RPO.
6. Thiết kế kiểm thử lỗi, diễn tập phục hồi và bằng chứng vận hành để xác nhận cam kết độ sẵn sàng đầu cuối.

## 1. Availability đầu cuối là gì?

Một dịch vụ có thể có nhiều replica, database multi-AZ và load balancer dự phòng nhưng người dùng vẫn không thể hoàn thành giao dịch. Lý do là hành trình nghiệp vụ thường đi qua nhiều thành phần: DNS, CDN/WAF, gateway, compute, identity provider, database, broker, payment provider và các hệ thống bên ngoài.

**Availability đầu cuối (end-to-end availability)** mô tả khả năng người dùng hoàn thành một hành động nghiệp vụ trong điều kiện đã định nghĩa, trong một khoảng thời gian đo. Nó bao gồm mọi dependency cần thiết để hành động đó thành công, cùng với cách hệ thống xử lý lỗi và suy giảm.

Ví dụ, với hành trình đặt chỗ:

1. Người dùng mở ứng dụng và xác thực.
2. Tìm dịch vụ và xem lịch còn chỗ.
3. Tạo booking và giữ chỗ trong inventory.
4. Thanh toán qua nhà cung cấp bên ngoài.
5. Nhận xác nhận và thông báo.

Nếu notification provider ngừng hoạt động nhưng booking đã được ghi nhận chính xác và người dùng có thể xem trạng thái trong ứng dụng, hành trình đặt chỗ có thể vẫn được coi là thành công. Ngược lại, nếu payment provider không thể xác định giao dịch đã thu tiền hay chưa, hệ thống không nên tuyên bố booking hoàn tất chỉ để tránh hiển thị lỗi.

Vì vậy phải định nghĩa **thành công nghiệp vụ** trước khi tính availability. Một trang trả HTTP 200 chưa chắc đã tạo ra booking đúng; một API khỏe chưa chắc cả hành trình hoàn tất.

## 2. Xây dependency graph theo hành trình nghiệp vụ

### 2.1. Bắt đầu từ hành động người dùng

Hãy chọn một hành động có ý nghĩa đo được, chẳng hạn:

- Đăng nhập thành công.
- Tra cứu sản phẩm trong thời gian mục tiêu.
- Hoàn tất checkout và có trạng thái giao dịch xác định.
- Gửi báo cáo theo lịch đúng hạn.
- Khôi phục khả năng đọc/ghi dữ liệu sau sự cố.

Sau đó vẽ những thành phần thực sự cần để hành động thành công. Tách rõ:

- **Hard dependency:** thiếu nó thì hành động không thể thành công đúng nghĩa.
- **Soft/optional dependency:** thiếu nó thì chức năng phụ trợ có thể tạm suy giảm mà không phá hỏng mục tiêu cốt lõi.
- **Alternative dependency:** có một hoặc nhiều đường thay thế hợp lệ.
- **Shared dependency:** phục vụ nhiều luồng và có thể tạo blast radius rộng.
- **Hidden dependency:** DNS, certificate, secret manager, identity, control plane, quota hoặc hệ thống vận hành thường bị bỏ quên.

### 2.2. Ví dụ dependency graph

~~~mermaid
flowchart TD
    U["Người dùng"] --> DNS["DNS / edge / WAF"]
    DNS --> GW["API gateway"]
    GW --> AUTH["Identity provider"]
    GW --> BOOK["Booking service"]
    BOOK --> INV["Inventory service"]
    BOOK --> DB[("Booking DB")]
    BOOK --> PAY["Payment provider"]
    BOOK --> OUT["Transactional outbox"]
    OUT --> BR["Message broker"]
    BR --> NOTI["Notification service"]
    NOTI --> EMAIL["Email/SMS provider"]
    BOOK --> OBS["Logs / metrics / tracing"]
    AUTH --> OBS
    PAY --> OBS
~~~

Sơ đồ chỉ là điểm bắt đầu. Nếu người dùng đã có session hợp lệ, identity provider có thể không cần được gọi ở mọi request. Nếu notification bất đồng bộ, email/SMS không nằm trên đường găng của thao tác checkout. Phân loại dependency theo **đường đi thực tế và trạng thái hệ thống**, không chỉ theo kết nối tồn tại trong sơ đồ.

### 2.3. Ma trận dependency

| Thành phần | Vai trò trong hành trình | Bắt buộc để ghi nhận booking? | Phương án khi lỗi |
| --- | --- | --- | --- |
| DNS/edge/gateway | Tiếp nhận request | Có | Health routing/failover nếu đã cấu hình |
| Identity provider | Xác thực hoặc cấp token | Tùy trạng thái phiên và policy | Cache token/phiên trong giới hạn hợp lệ; không bỏ xác thực |
| Booking service | Áp dụng quy tắc booking | Có | Replica/zone khác, rollback an toàn |
| Inventory | Giữ chỗ, chống oversell | Có trong mô hình này | Reservation policy hoặc từ chối có kiểm soát |
| Booking database | Lưu trạng thái và bất biến giao dịch | Có | HA/restore theo RTO/RPO |
| Payment provider | Xác nhận thanh toán theo hợp đồng | Có đối với booking yêu cầu trả trước | Pending/unknown và reconciliation; không giả định thất bại |
| Broker/outbox relay | Phát thông báo sự kiện sau commit | Không nhất thiết cho HTTP response ban đầu | Outbox giữ sự kiện, retry và DLQ |
| Email/SMS provider | Gửi thông báo | Không | Hiển thị booking trong app, gửi lại sau |
| Observability | Chẩn đoán, cảnh báo | Không phải dependency runtime của mọi request | Buffer/alternate telemetry; không để mất trace gây dừng nghiệp vụ |

Bảng này phụ thuộc chính sách nghiệp vụ. Nếu pháp lý/hợp đồng bắt buộc gửi OTP qua SMS trước khi xác nhận, SMS provider trở thành hard dependency của bước xác thực đó.

## 3. Chuỗi nối tiếp và thành phần song song

### 3.1. Chuỗi nối tiếp (series)

Trong một đường đi mà tất cả thành phần đều phải hoạt động, nếu giả sử các lỗi độc lập và availability từng thành phần là \(A_i\), availability của cả chuỗi là:

\[
A_{\text{series}}=\prod_{i=1}^{n} A_i
\]

Giả sử một request phải qua bốn thành phần nối tiếp, mỗi thành phần có availability 99,9% trong cùng kỳ và cùng phạm vi đo:

\[
A_{\text{series}}=0.999^4 \approx 0.996006
\]

Tức xấp xỉ 99,60%. Mỗi thành phần riêng lẻ có vẻ rất sẵn sàng, nhưng chuỗi có thể thấp hơn đáng kể.

Đây là **ước lượng mô hình**, không phải cam kết thực tế. Công thức giả định các sự kiện lỗi độc lập, các availability cùng định nghĩa thời gian và không có hành vi phục hồi/timeout làm thay đổi kết quả. Trong thực tế, shared network, region, identity, quota hoặc cấu hình sai có thể làm nhiều thành phần cùng lỗi.

### 3.2. Thành phần dự phòng song song (parallel redundancy)

Nếu có hai instance độc lập, cùng đủ năng lực và có load balancer chuyển request sang instance còn hoạt động, availability của lớp có thể được ước tính:

\[
A_{\text{parallel}}=1-(1-A_1)(1-A_2)
\]

Nếu mỗi instance có availability 99%:

\[
A_{\text{parallel}}=1-(0.01 \times 0.01)=0.9999
\]

Kết quả lý thuyết là 99,99%, nhưng chỉ đúng nếu lỗi instance độc lập và cơ chế phát hiện/chuyển traffic hoạt động đủ nhanh. Nếu hai instance cùng zone, cùng image lỗi hoặc cùng phụ thuộc một database chết, dự phòng không giải quyết được lỗi chung.

### 3.3. Nhiều lớp dự phòng không tự động cộng dồn

Ví dụ hai API replica cùng dựa vào một database primary không có failover. Availability API có thể cao trong khi database là giới hạn của toàn hành trình. Đặt hai load balancer cũng không tăng availability nếu cả hai dùng chung DNS zone sai cấu hình hoặc certificate hết hạn.

Phải vẽ cả:
- Các thành phần dự phòng.
- Shared dependency và common-cause failure.
- Control plane cần để khởi tạo/điều phối failover.
- Đường dữ liệu và trạng thái được duy trì khi chuyển vùng.
- Thời gian phát hiện, quyết định và thực hiện phục hồi.

## 4. Common-cause failure và blast radius

**Common-cause failure** xảy ra khi một nguyên nhân chung làm nhiều thành phần dự phòng cùng ngừng hoạt động hoặc suy giảm. Đây là lý do phép nhân availability độc lập thường lạc quan.

Ví dụ:
- Hai replica ở hai AZ nhưng dùng chung một IAM policy bị thu hồi.
- Nhiều service cùng phụ thuộc DNS resolver hoặc identity provider.
- Hai database node cùng chịu lỗi một storage/control plane.
- Một pipeline deploy đẩy cấu hình sai đồng loạt tới tất cả region.
- Một cloud account hết quota hoặc bị khóa quyền.
- Certificate, secret hoặc KMS key dùng chung hết hạn/không thể truy cập.

### 4.1. Các lớp lỗi chung cần rà soát

| Phạm vi | Ví dụ common cause | Kiểm soát |
| --- | --- | --- |
| Region/AZ | Mất điện, network fabric hoặc dịch vụ vùng | Phân bố failure domain, DR được thử |
| Identity/IAM | Policy chung sai, IdP/KMS unavailable | Break-glass có kiểm soát, policy test, rotation plan |
| DNS/certificate | Zone sai, registrar/issuer, expiry | DNS monitoring, renewal automation, alternate access |
| Deployment | Lỗi image/config rollout toàn bộ replica | Canary, staged rollout, rollback |
| Data | Corrupt schema, migration lỗi, replication sai | Backup immutable, PITR, migration safety |
| Control plane | Cluster/API/quota hoặc orchestrator không hoạt động | Runbook thủ công hợp lệ, control plane recovery |
| Dependency ngoài | Payment, email, SaaS hoặc cloud API gặp outage | Timeout, degraded mode, provider alternatives khi có thể |
| Con người/quy trình | Thao tác xóa nhầm, quyền quá rộng | Approval theo rủi ro, audit, separation of duties |

### 4.2. Failure domain và blast radius

Một failure domain là phạm vi tài nguyên có thể bị ảnh hưởng bởi cùng một lỗi. Có thể phân tách theo process, node, rack, AZ, region, account/subscription, control plane hoặc nhà cung cấp.

Không phải lúc nào cũng nên tách mọi thứ. Mỗi ranh giới mới có chi phí về replication, network, consistency, IAM, observability và vận hành. Mục tiêu là cô lập những lỗi có hậu quả không thể chấp nhận, đồng thời giữ kiến trúc có thể vận hành.

## 5. Availability phải gắn với định nghĩa SLI/SLO

### 5.1. SLI, SLO và SLA

- **SLI (Service Level Indicator):** phép đo thực tế, ví dụ tỷ lệ checkout hợp lệ hoàn thành trong 2 giây.
- **SLO (Service Level Objective):** mục tiêu cho SLI trong một kỳ đo, ví dụ 99,9% booking hợp lệ hoàn tất trong cửa sổ một tháng.
- **SLA (Service Level Agreement):** cam kết trong hợp đồng, kèm định nghĩa, điều kiện loại trừ và biện pháp khi vi phạm.

Một SLO không rõ mẫu số sẽ dẫn tới tranh cãi. Cần xác định:
- Request nào thuộc phạm vi: mọi request, request hợp lệ, user journey hay giao dịch đã qua kiểm tra?
- Lỗi client 4xx do đầu vào không hợp lệ có tính vào SLI không?
- Timeout phía người dùng nhưng server đã commit booking được tính ra sao?
- Retry của cùng một giao dịch là một hay nhiều sự kiện đo?
- Cửa sổ đo là rolling 30 ngày hay tháng lịch?
- Hệ thống bảo trì định kỳ có bị loại trừ không và ai phê duyệt?

### 5.2. SLI đầu cuối cho checkout

Có thể định nghĩa một giao dịch hợp lệ thành công khi:
1. Booking được ghi một lần với trạng thái nghiệp vụ hợp lệ.
2. Inventory được giữ đúng theo quy tắc.
3. Payment ở trạng thái đã xác nhận hoặc một trạng thái pending được hợp đồng cho phép.
4. Người dùng nhận được kết quả có thể tra cứu.
5. Các bất biến dữ liệu không bị vi phạm.

Một metric HTTP 2xx đơn lẻ không đủ đại diện cho kết quả này.

Ví dụ SLI:
\[
SLI_{\text{checkout}}=
\frac{\text{số giao dịch hợp lệ hoàn thành đúng semantics trong thời hạn}}
{\text{tổng giao dịch hợp lệ được thử}}
\]

Mục tiêu và thời hạn phải được Product, SRE và chủ sở hữu nghiệp vụ thống nhất dựa trên trải nghiệm cần thiết.

### 5.3. Error budget

Với SLO availability 99,9% trong một kỳ 30 ngày (giả sử 30 ngày liên tục):

\[
30 \times 24 \times 60 \times (1-0.999)
=43.2 \text{ phút}
\]

Đây là thời gian lỗi tương đương nếu SLI được định nghĩa theo thời gian. Nếu SLI dựa trên tỷ lệ request thành công, error budget là tỷ lệ request lỗi cho phép, không thể quy đổi trực tiếp thành số phút nếu lưu lượng biến động.

Error budget giúp thảo luận giữa tốc độ phát hành và độ ổn định. Nó không phải quyền tự động bỏ qua kiểm soát bảo mật, tuân thủ hoặc tính đúng đắn dữ liệu.

## 6. Dependency không đồng nghĩa tất cả phải nằm trên đường găng

Một kiến trúc tốt phân loại tác vụ theo mức cần thiết cho kết quả nghiệp vụ. Các công việc phụ trợ có thể rời khỏi request đồng bộ bằng queue hoặc outbox.

Ví dụ:
- Ghi booking và trạng thái payment là bước cốt lõi.
- Gửi email, cập nhật analytics và phát thông báo cho CRM có thể chạy bất đồng bộ.
- Recommendation có thể bị tắt khi quá tải.
- Dashboard có thể chậm vài phút nhưng không làm checkout thất bại.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking service
    participant D as Booking DB
    participant P as Payment provider
    participant O as Outbox
    participant Q as Broker
    participant N as Notification
    C->>B: Tạo booking
    B->>D: Ghi PENDING / reservation
    B->>P: Xác nhận thanh toán
    P-->>B: Kết quả giao dịch
    B->>D: Commit trạng thái hợp lệ
    B->>O: Ghi event cùng transaction
    B-->>C: Kết quả có thể tra cứu
    O->>Q: Relay event
    Q->>N: Consume event
    Note over Q,N: Lỗi notification không đảo ngược booking đã commit
~~~

Đây là mẫu khái niệm. Nếu payment provider timeout sau khi nhận charge request, trạng thái có thể là **UNKNOWN/PENDING_RECONCILIATION**, không được xem như thất bại chắc chắn. Cần idempotency key và tra cứu giao dịch trước khi retry hoặc giải phóng inventory.

## 7. Timeout, retry và thời gian hoàn thành đầu cuối

### 7.1. Timeout theo ngân sách end-to-end

Giả sử request có deadline 2 giây. Nếu gateway chờ backend 2 giây, backend chờ database 2 giây và payment client chờ 2 giây, request thực tế có thể kéo dài vượt xa mục tiêu.

Cần truyền deadline/budget qua các hop:
- Gateway reserve thời gian cho serialization và trả kết quả.
- Application phân bổ phần còn lại cho dependency.
- Database statement timeout nhỏ hơn timeout ứng dụng thích hợp.
- External call có connect timeout và response timeout riêng.
- Worker/queue có visibility timeout, job timeout và retry policy.

Timeout không nhất thiết dừng hoạt động ở hệ thống đích. Client có thể timeout trong khi payment vẫn được xử lý. Vì vậy timeout tạo trạng thái không chắc chắn; cần reconciliation, không thể suy diễn rằng lệnh chưa xảy ra.

### 7.2. Retry có thể tăng availability hoặc làm outage tệ hơn

Retry hữu ích với lỗi transient, nhưng retry đồng loạt có thể tạo **retry storm**. Quy tắc:
- Exponential backoff và jitter.
- Giới hạn số lần thử, retry budget và tổng deadline.
- Chỉ retry thao tác idempotent hoặc có idempotency key.
- Phân loại lỗi permanent/transient, 4xx/5xx, rate limit và timeout.
- Dừng hoặc giảm retry khi circuit breaker mở.
- Không retry ngay ở mọi tầng cùng lúc; retry amplification có thể nhân request theo cấp số nhân.

Nếu ba tầng đều retry ba lần, một request gốc có thể tạo nhiều lần gọi xuống dependency. Cần quyết định tầng nào sở hữu retry và theo dõi attempt count.

### 7.3. Circuit breaker và bulkhead

- **Circuit breaker:** ngừng gọi tạm thời dependency có dấu hiệu lỗi liên tục, cho thời gian phục hồi và thử lại hạn chế ở half-open.
- **Bulkhead:** tách connection pool, thread pool, queue hoặc concurrency để sự cố một dependency không làm cạn toàn bộ ứng dụng.
- **Load shedding:** từ chối chức năng ít ưu tiên khi tải vượt capacity.
- **Graceful degradation:** giữ nghiệp vụ cốt lõi, tắt hoặc giảm tính năng phụ trợ.

Các cơ chế này cần được kiểm thử với threshold, timeout và recovery behavior thực tế. Circuit breaker cấu hình quá nhạy có thể làm dịch vụ dao động; cấu hình quá lỏng thì không bảo vệ được tài nguyên.

## 8. Cache, queue và fallback ảnh hưởng availability như thế nào?

### 8.1. Cache

Cache có thể phục vụ dữ liệu đọc khi origin tạm thời lỗi, nhưng chỉ khi stale data được nghiệp vụ chấp nhận. Có thể dùng stale-while-revalidate cho catalog công khai; không được dùng dữ liệu tồn kho hoặc trạng thái thanh toán cũ nếu có thể dẫn tới giao dịch sai.

Cần xác định:
- Source of truth.
- TTL và freshness objective.
- Invalidation/refresh.
- Hành vi khi cache miss trong lúc origin lỗi.
- Cache poisoning và tenant isolation.
- Cold-cache capacity.

### 8.2. Queue

Queue làm phẳng burst và tách producer/consumer. Khi consumer lỗi, producer có thể tiếp tục trong giới hạn buffer/retention; tuy nhiên queue không đảm bảo kết quả được xử lý đúng hạn nếu backlog tăng vô hạn.

Theo dõi:
- Oldest message age.
- Consumer lag và throughput.
- Retention còn lại.
- DLQ growth, retry và poison message.
- Sink saturation và thời gian drain backlog.

### 8.3. Fallback

Fallback chỉ cải thiện availability khi trả về **kết quả nghiệp vụ hợp lệ**. Ví dụ:
- Recommendation service lỗi: trả trang không có gợi ý.
- Email provider lỗi: vẫn hiển thị booking trong app và retry gửi email sau.
- Search index lỗi: có thể chuyển sang truy vấn nguồn khác nếu capacity và tính đúng đắn cho phép.
- Payment provider lỗi: trả trạng thái chưa xác định và cung cấp phương thức tra cứu, không tự đánh dấu đã thanh toán.

Một fallback gây stale hoặc sai dữ liệu có thể biến lỗi availability thành lỗi correctness nghiêm trọng hơn.

## 9. Định lượng availability với redundancy và giới hạn thực tế

### 9.1. Ví dụ chuỗi có dự phòng

Một hành trình cần:
- Gateway availability 99,99%.
- API layer có hai replica song song, mỗi replica 99,9% (giả định độc lập).
- Database HA availability 99,95%.
- Payment provider availability 99,9%.

Availability ước lượng của API layer:

\[
A_{\text{API}}=1-(1-0.999)^2=0.999999
\]

Availability chuỗi:

\[
A_{\text{journey}}=
0.9999 \times 0.999999 \times 0.9995 \times 0.999
\approx 0.998401
\]

Tức khoảng 99,84% theo mô hình độc lập. Payment provider và database có ảnh hưởng đáng kể dù API layer có redundancy rất cao.

### 9.2. Thêm lỗi chung

Giả sử xác suất một lỗi chung làm cả hai API replica không dùng được trong kỳ là \(q\). Khi đó phần availability của API layer không thể chỉ dùng công thức độc lập. Một mô hình đơn giản có thể là:

\[
A_{\text{API}} \approx (1-q)\left[1-(1-a)^2\right]
\]

Trong đó \(a\) là availability riêng của mỗi replica khi không có lỗi chung. Nếu \(q\) đáng kể, lợi ích redundancy giảm. Mô hình này vẫn giản lược vì lỗi chung và lỗi riêng có thể tương quan.

### 9.3. Availability theo thời gian khác availability theo request

- **Time-based availability:** tỷ lệ thời gian dịch vụ sẵn sàng trong kỳ.
- **Request-based availability:** tỷ lệ request hợp lệ hoàn thành đúng điều kiện.
- **Journey-based availability:** tỷ lệ người dùng hoàn tất hành trình nghiệp vụ.
- **Data freshness/quality:** dữ liệu có mới và đúng để phục vụ hành động không.

Một dịch vụ có thể hoạt động 99,99% thời gian nhưng có 1% request lỗi do overload trong các giờ cao điểm. Ngược lại, một khoảng downtime ngắn vào ban đêm có thể ảnh hưởng ít request. Phải chọn SLI phản ánh giá trị người dùng.

Không cộng hoặc nhân các loại availability khác định nghĩa/kỳ đo với nhau.

## 10. RTO, RPO và kế hoạch khôi phục

- **RTO (Recovery Time Objective):** thời gian mục tiêu tối đa để khôi phục dịch vụ sau sự cố theo phạm vi đã xác định.
- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa theo thời gian có thể chấp nhận.
- **MTTR:** thời gian trung bình sửa chữa/khôi phục; là metric vận hành, không thay thế RTO.
- **Failover:** chuyển hoạt động sang thành phần/vùng dự phòng.
- **Failback:** chuyển trở lại môi trường chính sau khi đã xử lý sự cố và xác minh trạng thái.

Mỗi hành trình có thể có RTO/RPO khác nhau. API catalog có thể chấp nhận khôi phục chậm hơn checkout; log analytics có thể có RPO khác database booking.

### 10.1. Các chiến lược DR

| Chiến lược | Mô tả | Đánh đổi |
| --- | --- | --- |
| Backup and restore | Khôi phục từ backup sau sự cố | Chi phí standby thấp hơn, RTO thường dài hơn |
| Pilot light | Một số thành phần cốt lõi chạy sẵn ở vùng phụ | Cần mở rộng và cấu hình khi failover |
| Warm standby | Môi trường dự phòng chạy ở capacity giảm | RTO nhanh hơn, có chi phí duy trì |
| Active-active | Nhiều vùng đồng thời phục vụ | Có thể giảm downtime, nhưng phức tạp về routing, consistency và conflict |

Không có chiến lược nào tự đạt RTO/RPO nếu chưa thử. Replication không thay thế backup: lỗi logic hoặc xóa nhầm có thể được replicate sang vùng dự phòng.

### 10.2. Mô tả recovery phải đủ chi tiết

Runbook cần chỉ rõ:
- Trigger và quyền ra quyết định failover.
- Thành phần nào chuyển trước, thứ tự phụ thuộc.
- DNS/traffic routing, certificate, IAM, secrets và network.
- Database replication lag, transaction consistency, write fencing và chống split-brain.
- Queue offset, outbox/inbox và message replay.
- Đối soát payment/inventory/booking.
- Điều kiện mở traffic và kiểm tra health theo hành trình.
- Kế hoạch failback, thông báo khách hàng và audit.

## 11. Thiết kế SLO theo dependency và degraded mode

Một số thành phần không cần cùng SLO với hành trình chính. Cần đặt SLO theo mức quan trọng:

| Hành trình/thành phần | SLI gợi ý | Degraded mode chấp nhận được |
| --- | --- | --- |
| Login | Tỷ lệ xác thực hợp lệ, latency | Chỉ dùng phiên/token đã cấp trong giới hạn policy |
| Search | Tỷ lệ truy vấn trả kết quả hợp lệ, p95 | Cache kết quả public còn fresh trong giới hạn |
| Checkout | Tỷ lệ giao dịch hoàn tất đúng semantics | Không xác nhận nếu payment unknown; cho phép tra cứu |
| Booking confirmation | Tỷ lệ trạng thái có thể tra cứu | Trạng thái pending rõ ràng khi bước ngoài chưa xác định |
| Notification | Tỷ lệ gửi đúng hạn | Queue và retry; không làm rollback booking |
| Reporting | Tỷ lệ báo cáo hoàn thành đúng lịch | Chậm có cảnh báo, không ảnh hưởng checkout |

Một dependency optional vẫn có thể cần SLO riêng. Ví dụ notification có thể chậm tối đa 10 phút nhưng không làm checkout fail. Định nghĩa degraded mode và thời hạn phục hồi giúp tránh tranh cãi khi sự cố xảy ra.

### 11.1. Dependency SLO không cộng đơn giản

Nếu API phụ thuộc payment provider, SLO của API có thể chịu ảnh hưởng từ SLO provider nhưng không nhất thiết bằng tích hai con số. Hành vi retry, timeout, async workflow, fallback và cách đếm transaction quyết định kết quả quan sát.

Cần đo trực tiếp end-to-end, sau đó dùng dependency metrics để phân tích nguyên nhân. Đừng chỉ lấy SLA của từng nhà cung cấp rồi nhân lại và công bố đó là SLO thực tế.

## 12. Chaos engineering và failure testing

Mô hình tính toán chỉ tạo giả thuyết. Muốn biết hệ thống thực sự hoạt động ra sao phải kiểm chứng trong môi trường có kiểm soát.

### 12.1. Các thử nghiệm theo failure domain

| Thử nghiệm | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Kill một API instance | Load balancer có phát hiện và chuyển traffic? | Error rate, recovery time, remaining capacity |
| Mất một AZ | Có đủ capacity và dữ liệu ở AZ còn lại? | SLO, replica placement, DB failover |
| DB failover | Request đang chạy, connection pool và transaction ra sao? | Error duration, data integrity, RTO |
| Payment timeout | Có charge trùng hoặc booking sai trạng thái? | Idempotency, reconciliation, pending state |
| Broker unavailable | Outbox/backlog có giữ được event? | Queue age, event loss/duplicate, recovery |
| DNS/certificate lỗi | Client và service-to-service có còn truy cập? | Resolution, TLS errors, fallback path |
| Secret/KMS unavailable | Workload đã chạy và workload restart bị ảnh hưởng thế nào? | Secret fetch, cache/rotation behavior |
| Regional outage | DR có khởi động và phục vụ được end-to-end? | RTO/RPO, data consistency, user journey |

### 12.2. Nguyên tắc thử nghiệm an toàn

- Xác định giả thuyết, phạm vi, blast radius, điều kiện dừng và người chịu trách nhiệm.
- Bắt đầu ở môi trường test/staging đủ tương đồng, sau đó thử production có kiểm soát nếu được phê duyệt.
- Không giả lập lỗi phá hủy dữ liệu khách hàng hoặc tạo giao dịch thật ngoài quy trình.
- Đo baseline trước và sau thử nghiệm.
- Có rollback/abort và kênh liên lạc incident.
- Ghi lại kết quả, bất ngờ và công việc khắc phục.
- Thử cả lỗi phục hồi: dependency đã hồi phục nhưng backlog còn lớn, cache lạnh hoặc replica đang đồng bộ lại.

Chaos engineering không phải tạo lỗi ngẫu nhiên tùy tiện. Mục tiêu là kiểm tra giả thuyết về khả năng phục hồi.

## 13. Quan sát và cảnh báo theo hành trình

Dashboard nên kết hợp:
- **Business SLI:** checkout success, booking state correctness, payment reconciliation.
- **User experience:** p95/p99 journey latency, error rate, region/device breakdown.
- **Dependency health:** latency, availability, quota/throttle, circuit breaker state.
- **Resource saturation:** CPU, memory, connection pool, DB locks/IO, network.
- **Queueing:** oldest message age, backlog, retry/DLQ.
- **Recovery:** replication lag, backup validation, last successful DR test.
- **Change correlation:** deploy/config/feature flag thay đổi trước incident.

Distributed tracing cần correlation ID xuyên API, queue và worker. Với bất đồng bộ, propagate trace context hoặc business correlation/causation ID; không log token hoặc PII nhạy cảm chỉ để thuận tiện điều tra.

Cảnh báo nên phản ánh **triệu chứng người dùng** và mức nghiêm trọng. Cảnh báo CPU 80% có thể là tín hiệu hữu ích, nhưng p95 checkout hoặc success rate vi phạm SLO mới thể hiện tác động nghiệp vụ trực tiếp.

## 14. Tình huống thực tế: checkout có nhiều dependency

### 14.1. Bối cảnh

Một nền tảng đặt chỗ có các thành phần:
- Edge/gateway và authentication.
- Booking API và Inventory service.
- Booking database.
- Payment provider bên ngoài.
- Broker và notification worker.
- Email/SMS provider.

Mục tiêu giả định:
- 99,9% giao dịch checkout hợp lệ đạt trạng thái xác định trong kỳ 30 ngày.
- p95 checkout dưới 2 giây trong tải đã thống nhất.
- RTO database booking dưới 60 phút; RPO dưới 5 phút.
- Notification được gửi trong 10 phút ở điều kiện bình thường, nhưng không được chặn booking.

Các ngưỡng là giả định bài học, phải được Product/SRE/pháp chế xác nhận trước khi dùng làm cam kết.

### 14.2. Phân loại đường găng

| Thành phần | Hard/soft trong checkout | Hành vi khi lỗi |
| --- | --- | --- |
| Gateway/API | Hard | Chuyển sang replica/zone khỏe |
| Auth | Hard ở bước cần xác thực | Không bypass policy; có thể dùng session/token hợp lệ |
| Inventory | Hard | Từ chối hoặc pending theo reservation rule, không oversell |
| Booking DB | Hard | HA/failover, commit và đối soát |
| Payment | Hard cho booking trả trước | Unknown/pending + tra cứu idempotent |
| Broker | Soft cho phản hồi đồng bộ nếu outbox bền vững | Outbox relay retry sau |
| Email/SMS | Soft | Queue và gửi lại, trạng thái vẫn tra cứu trong app |

### 14.3. Các lỗi thường gặp nếu thiết kế sai

- Email provider lỗi khiến checkout trả 500 dù payment đã thành công.
- Payment timeout bị coi là thất bại, client retry tạo giao dịch charge thứ hai.
- Booking DB chuyển primary nhưng ứng dụng vẫn dùng connection cũ và tiếp tục ghi sai endpoint.
- Broker hết storage, outbox relay không tiến triển nhưng không có cảnh báo.
- Hai AZ có API replica nhưng cùng dùng một dependency identity không sẵn sàng.
- Failover region được kích hoạt nhưng chưa có dữ liệu/secret/certificate phù hợp.

### 14.4. Kế hoạch kiểm chứng

1. Tắt email provider trong staging; chứng minh booking vẫn hoàn tất và event được gửi lại sau.
2. Làm payment request timeout sau khi provider đã nhận; chứng minh không charge trùng và trạng thái được reconciliation.
3. Kill API instance; đo thời gian chuyển traffic và p95.
4. Diễn tập DB failover; xác minh transaction, connection pool và data integrity.
5. Dừng broker một khoảng thời gian; đo outbox growth, alert và drain time.
6. Mô phỏng mất region theo kế hoạch DR; đo RTO/RPO và hành trình checkout sau khôi phục.
7. Đối chiếu cost và capacity khi dự phòng được kích hoạt.

## 15. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng uptime của API làm availability của sản phẩm | Bỏ sót DB, auth, payment và dependency ngoài | Đo SLI theo hành trình nghiệp vụ |
| Nhân availability của mọi thành phần như độc lập | Đánh giá quá lạc quan khi có lỗi chung | Phân tích common cause và failure domain |
| Coi notification là hard dependency | Một provider phụ làm checkout thất bại | Tách outbox/queue và degraded mode |
| Coi payment timeout là thất bại | Có thể thu tiền trùng | Idempotency, status query và reconciliation |
| Retry ở mọi tầng không giới hạn | Retry storm, outage kéo dài | Retry budget, backoff, jitter và một tầng sở hữu retry |
| Có replica nhưng cùng AZ/credential/config | Dự phòng không chống common-cause failure | Tách failure domain và kiểm thử |
| Có backup nhưng chưa restore | RTO/RPO không có bằng chứng | Diễn tập restore và đo kết quả |
| Chỉ dùng SLA nhà cung cấp làm SLO sản phẩm | Không phản ánh request/journey thực tế | Định nghĩa và đo end-to-end SLI |
| Fallback trả dữ liệu stale cho giao dịch | Tạo lỗi correctness | Freshness policy và source-of-truth |
| Coi queue là capacity vô hạn | Backlog tăng và dữ liệu hết hạn | Retention, bounded admission, age alerts |
| Cảnh báo chỉ theo CPU | Không phát hiện lỗi hành trình người dùng | Business SLI, trace, dependency và saturation |
| Chaos test không có điều kiện dừng | Tạo sự cố ngoài kiểm soát | Hypothesis, scope, abort/rollback và owner |

## 16. Bài tập thực hành

Một nền tảng đặt chỗ cloud chạy trên hai availability zone. Người dùng báo thỉnh thoảng không hoàn thành checkout dù dashboard cho thấy API uptime 99,99%. Hệ thống còn phụ thuộc database booking, identity provider, payment gateway, broker, email provider và DNS. Mục tiêu Product đề xuất là 99,9% checkout hợp lệ hoàn tất trong 30 ngày; RTO database 45 phút, RPO 5 phút.

Hãy thực hiện:

1. Vẽ dependency graph cho hành trình checkout; phân loại hard, soft, alternative và shared dependency.
2. Định nghĩa một end-to-end SLI có mẫu số, điều kiện hợp lệ, semantics thành công và thời gian hoàn thành.
3. Tính availability ước lượng cho chuỗi nối tiếp với các giả định rõ; thêm mô hình hai replica và common-cause failure.
4. Chỉ ra ít nhất năm lỗi chung có thể làm cả hai AZ cùng mất khả năng phục vụ.
5. Thiết kế degraded mode cho email, broker, payment, identity và database; xác định chức năng nào được suy giảm.
6. Phân bổ timeout/deadline qua gateway, API, database và payment; nêu cách xử lý kết quả payment không xác định.
7. Đề xuất SLO cho checkout, notification freshness và reporting; tính error budget nếu thích hợp.
8. Viết runbook failover database và regional DR, gồm data consistency, queue/outbox và reconciliation.
9. Xây dựng kế hoạch chaos/failure test với giả thuyết, blast radius, điều kiện dừng và tiêu chí đạt.
10. Viết ADR nêu quyết định, đánh đổi, residual risks, owner và trigger xem xét lại.

**Tiêu chí tự đánh giá:** giải pháp tốt phải đo độ sẵn sàng của kết quả nghiệp vụ, nhận diện dependency ẩn và lỗi chung, có fallback đúng semantics, kiểm chứng được RTO/RPO và nêu được rủi ro còn tồn tại.

## 17. Checklist trước khi cam kết availability

- [ ] Hành trình nghiệp vụ và điều kiện thành công được định nghĩa rõ.
- [ ] Dependency graph gồm thành phần ngoài, control plane, identity, DNS, secrets và data.
- [ ] Thành phần được phân loại hard, soft, alternative, shared và hidden dependency.
- [ ] Có phân tích series, parallel redundancy và common-cause failure với giả định công khai.
- [ ] Failure domain và blast radius được thể hiện trên sơ đồ.
- [ ] SLI/SLO/SLA có mẫu số, thời hạn, phạm vi request và điều kiện loại trừ.
- [ ] Error budget được tính theo đúng loại SLI.
- [ ] Timeout/deadline xuyên hop có ngân sách; retry có idempotency và giới hạn.
- [ ] Circuit breaker, bulkhead, backpressure và degraded mode được thử.
- [ ] Cache/fallback không vi phạm freshness, authorization hoặc correctness.
- [ ] Queue/outbox, replay, DLQ và side effect có semantics rõ.
- [ ] RTO/RPO được xác định theo dữ liệu/hành trình và có diễn tập restore/failover.
- [ ] Common-cause failures như DNS, IAM, KMS, deploy, quota và region đã được xem xét.
- [ ] Dashboard/cảnh báo đo business SLI, dependency health và saturation.
- [ ] Chaos/failure test có giả thuyết, điều kiện dừng, rollback và owner.
- [ ] ADR ghi bằng chứng, đánh đổi, residual risk và điều kiện đánh giá lại.

## Ghi nhớ

Độ sẵn sàng của một hệ thống không bằng uptime của một API hay số lượng replica. Nó phụ thuộc vào **hành trình nghiệp vụ thực tế**, các dependency bắt buộc, cách chúng nối tiếp/song song, những lỗi chung và cách hệ thống suy giảm hoặc phục hồi.

Hãy thiết kế từ chuỗi **hành động người dùng → dependency graph → SLI/SLO → failure domain → timeout/retry/fallback → RTO/RPO → kiểm thử lỗi và đo lường production**. Chỉ cam kết độ sẵn sàng khi có định nghĩa, bằng chứng và quy trình vận hành chứng minh được kết quả đầu cuối.
