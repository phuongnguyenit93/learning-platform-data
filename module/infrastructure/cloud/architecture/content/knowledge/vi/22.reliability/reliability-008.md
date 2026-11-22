# Đường dự phòng, chế độ suy giảm và phụ thuộc không trọng yếu

Một hệ thống cloud đáng tin cậy không chỉ cần tránh sự cố. Nó còn phải duy trì những chức năng quan trọng khi một phần hạ tầng hoặc dịch vụ phụ thuộc gặp lỗi. Một trang đặt lịch vẫn có thể hiển thị lịch hẹn đã xác nhận dù dịch vụ gợi ý bị lỗi; người dùng vẫn có thể xem thông tin thiết yếu khi hệ thống đề xuất cá nhân hóa tạm ngừng; một giao dịch có thể được tiếp nhận vào hàng đợi bền vững khi hệ thống xử lý phía sau đang quá tải. Những lựa chọn này cần được thiết kế trước khi sự cố xảy ra.

**Đường dự phòng (fallback path)** là cách xử lý thay thế được kích hoạt khi đường xử lý ưu tiên không thể đáp ứng. **Graceful degradation** là cách hệ thống giảm một phần chất lượng hoặc tính năng nhưng vẫn duy trì chức năng cốt lõi. **Phụ thuộc không trọng yếu (non-critical dependency)** là dịch vụ mà sự cố không nên làm dừng toàn bộ nghiệp vụ chính. Phân loại phụ thuộc phải dựa vào tác động thực tế lên từng use case; cùng một dịch vụ có thể trọng yếu với thao tác này nhưng không trọng yếu với thao tác khác.

Một fallback tốt cần có giới hạn, điều kiện kích hoạt, timeout, dữ liệu thay thế, khả năng quan sát và cách khôi phục. Fallback vô hạn hoặc không rõ semantics có thể tạo dữ liệu sai, che giấu sự cố, làm quá tải hệ thống dự phòng hoặc biến lỗi cục bộ thành sự cố dây chuyền.

Bài học thuộc phần **Độ tin cậy** trong học phần kiến trúc cloud. Trọng tâm là thiết kế đường dự phòng, chế độ suy giảm và ranh giới phụ thuộc để cân bằng độ tin cậy, hiệu năng, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân loại phụ thuộc theo mức độ quan trọng và tác động nghiệp vụ.
- Thiết kế fallback cho cache, dịch vụ bên ngoài, tìm kiếm, gợi ý và tác vụ bất đồng bộ.
- Áp dụng graceful degradation, timeout, retry, circuit breaker, bulkhead và load shedding.
- Xác định khi nào dùng dữ liệu stale, default response, queue hoặc read replica.
- Thiết kế fallback an toàn cho thao tác ghi và tránh xác nhận thành công giả.
- Kiểm thử failure path, recovery path và khả năng không tạo cascading failure.
- Đo SLO, fallback rate, dependency health và đánh giá rủi ro vận hành.

## 1. Vì sao cần đường dự phòng?

Một request có thể đi qua nhiều thành phần: API gateway, authentication, database, cache, search, recommendation, payment provider và notification. Nếu tất cả thành phần đều được gọi tuần tự và một thành phần lỗi khiến request thất bại, độ tin cậy tổng thể của luồng có thể thấp hơn độ tin cậy của từng thành phần.

Ví dụ trang chi tiết lịch hẹn cần Booking Service để lấy lịch, Customer Service để lấy tên hiển thị, Recommendation Service để gợi ý dịch vụ khác và Analytics Service để ghi sự kiện xem trang. Booking và quyền truy cập có thể là phần cốt lõi. Recommendation và analytics thường có thể chạy sau hoặc tạm ngừng. Nếu trang không hiển thị chỉ vì analytics timeout, kiến trúc đã để một phụ thuộc phụ quyết định khả năng phục vụ nghiệp vụ chính.

~~~mermaid
flowchart TD
    U["Client request"] --> API["Application API"]
    API --> CORE["Core booking data"]
    API --> REC["Recommendation"]
    API --> ANA["Analytics event"]
    CORE --> R["Response"]
    REC --> R
    ANA --> R
    R --> U
~~~

Nếu API chờ cả ba nhánh trước khi phản hồi, độ trễ và lỗi của nhánh phụ có thể ảnh hưởng toàn bộ request. Cần xác định nhánh nào đồng bộ bắt buộc, nhánh nào chạy bất đồng bộ và nhánh nào có phương án thay thế.

### Reliability không có nghĩa mọi feature luôn hoạt động

Người dùng thường quan tâm kết quả nghiệp vụ: có xem được lịch hẹn, có đặt được slot, có biết thanh toán đã thành công hay không. Họ có thể chấp nhận tạm thời không có gợi ý, ảnh đại diện hoặc dashboard phụ nếu chức năng chính tiếp tục đúng.

Mục tiêu của graceful degradation là bảo vệ giá trị chính trong sự cố, không phải giữ nguyên mọi tính năng bằng mọi giá. Một chế độ suy giảm phải được định nghĩa rõ để người dùng không hiểu nhầm dữ liệu hoặc trạng thái.

## 2. Phân loại phụ thuộc theo use case

Không nên gắn nhãn một service là critical hoặc non-critical cho toàn hệ thống. Hãy đánh giá từng dependency trong một đường xử lý cụ thể.

| Mức độ | Ý nghĩa | Ví dụ trong ứng dụng đặt lịch | Hướng xử lý khi lỗi |
| --- | --- | --- | --- |
| **Bắt buộc cho tính đúng đắn** | Không thể hoàn tất nghiệp vụ an toàn nếu thiếu kết quả | Xác thực quyền, kiểm tra và giữ slot, trạng thái payment khi xác nhận booking | Fail closed, retry có giới hạn hoặc chuyển trạng thái chờ |
| **Bắt buộc theo policy** | Phải đáp ứng yêu cầu bảo mật/quy định trước khi tiếp tục | Kiểm tra quyền truy cập hồ sơ nhạy cảm, xác minh giới hạn giao dịch | Từ chối hoặc chờ; không bỏ qua policy để tăng availability |
| **Quan trọng nhưng có phương án dự phòng** | Có thể tiếp tục với dữ liệu hoặc phương thức thay thế trong giới hạn | Cache/read replica, nhà cung cấp xác thực dự phòng đã được phê duyệt | Fallback có điều kiện, ghi rõ mức freshness |
| **Không trọng yếu với request hiện tại** | Lỗi không được chặn nghiệp vụ chính | Gợi ý, tracking analytics, gửi email sau khi booking đã lưu | Bỏ qua tạm thời, queue hoặc xử lý nền |

### Câu hỏi để phân loại

1. Nếu dependency không phản hồi, có thể tạo kết quả sai hoặc vi phạm quy tắc nghiệp vụ không?
2. Có phương án thay thế được kiểm chứng hay chỉ là một phỏng đoán?
3. Dữ liệu thay thế cũ bao lâu thì không còn an toàn?
4. Có yêu cầu pháp lý, bảo mật hoặc authorization buộc phải kiểm tra không?
5. Chức năng có thể trì hoãn mà không ảnh hưởng nghiệp vụ không?
6. Khi fallback được dùng, ai biết và theo dõi được điều đó?

### Phân biệt dependency kỹ thuật và dependency nghiệp vụ

Một ứng dụng có thể phụ thuộc kỹ thuật vào DNS, secret manager, database, identity provider và message broker. Một dependency nghiệp vụ là nguồn quyết định hoặc cung cấp khả năng của domain khác, ví dụ payment provider hoặc dịch vụ định giá.

Không phải mọi lỗi kỹ thuật đều có thể fallback ở application. Nếu không thể xác thực danh tính, ứng dụng không nên tự coi caller là hợp lệ. Nếu không truy cập được secret cần cho kết nối database, không nên hardcode credential dự phòng. Fallback phải giữ nguyên security boundary.

## 3. Xác định chức năng cốt lõi và mức suy giảm cho phép

Trước khi thiết kế fallback, hãy mô tả trải nghiệm tối thiểu mà hệ thống phải giữ trong từng sự cố.

| Use case | Bình thường | Khi phụ thuộc phụ lỗi | Không được đánh đổi |
| --- | --- | --- | --- |
| Xem lịch hẹn | Thông tin lịch, hồ sơ và gợi ý | Ẩn gợi ý, dùng tên tối thiểu từ dữ liệu đã lưu | Không lộ lịch của người khác |
| Tìm bác sĩ | Kết quả mới và xếp hạng | Dùng danh mục/cache gần nhất hoặc tìm kiếm cơ bản | Không hiển thị slot đã biết là hết |
| Tạo booking | Revalidate slot và lưu transaction | Có thể tiếp nhận yêu cầu chờ xử lý nếu contract cho phép | Không xác nhận booking khi chưa giữ được slot |
| Gửi email xác nhận | Gửi sau khi booking commit | Queue và thử lại sau | Không mất trạng thái booking; không gửi thông báo thành công giả |
| Dashboard phân tích | Số liệu mới | Hiển thị thời điểm cập nhật gần nhất | Không trình bày dữ liệu stale như trạng thái tức thời |

### Service degradation budget

Có thể định nghĩa ngân sách suy giảm: feature nào được phép tắt, trong thời gian tối đa bao lâu, tỷ lệ request nào chịu ảnh hưởng và dữ liệu stale tối đa. Ví dụ gợi ý có thể tắt 30 phút; trạng thái booking không được stale quá ngưỡng nghiệp vụ; analytics có thể chậm 15 phút.

Đây là mục tiêu giả định cần được owner nghiệp vụ xác nhận. Không lấy cùng một ngưỡng cho mọi dữ liệu hoặc mọi khách hàng.

## 4. Các chiến lược fallback phổ biến

| Chiến lược | Cách hoạt động | Hợp với | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| Static/default response | Trả cấu hình hoặc nội dung mặc định đã được phê duyệt | Banner, gợi ý, nội dung không quyết định giao dịch | Default sai, lỗi thời hoặc không phù hợp tenant |
| Cached/stale response | Trả bản cache còn trong stale bound | Catalog, profile, dashboard | Dữ liệu cũ, quyền đã bị thu hồi, cache poisoning |
| Alternate provider/path | Gọi nhà cung cấp hoặc route dự phòng | DNS, identity/payment capability khi đã hỗ trợ chính thức | Hai provider có semantics khác nhau, split-brain |
| Read replica/read model | Đọc bản sao hoặc projection | Truy vấn chỉ đọc chấp nhận lag | Stale read, failover hoặc lag không rõ |
| Queue/defer | Lưu công việc bền vững để xử lý sau | Notification, analytics, export, tác vụ lâu | Backlog, retention, duplicate, queue full |
| Reduced feature set | Tắt phần phụ, giữ phần cốt lõi | Recommendation, personalization, preview | Người dùng cần biết tính năng tạm thời không sẵn sàng |
| Load shedding | Từ chối sớm hoặc giảm tải có kiểm soát | Quá tải, bảo vệ core dependency | Công bằng giữa tenant và retry storm |
| Fail fast | Dừng request khi không thể xử lý đúng | Authorization, giao dịch cần strong consistency | UX cần trạng thái lỗi rõ và khả năng retry an toàn |

Một hệ thống có thể dùng nhiều chiến lược. Ví dụ cache-aside cho catalog, queue cho email, tắt recommendation khi lỗi và fail fast khi payment state chưa xác định.

## 5. Default response và cached/stale data

Fallback đơn giản là trả một kết quả thay thế. Nhưng không phải dữ liệu nào cũng có thể thay bằng giá trị mặc định.

### Default response

Default cần được domain owner phê duyệt, không chứa dữ liệu cá nhân hoặc dữ liệu suy đoán, có semantics rõ và không làm người dùng hiểu rằng thao tác đã hoàn thành. Giá trị mặc định cần có thể được thay đổi qua configuration an toàn.

Ví dụ khi recommendation lỗi, trả danh sách rỗng kèm trạng thái recommendations unavailable có thể hợp lý. Trả một danh sách slot giả định cho thao tác đặt lịch thì không.

### Stale-while-revalidate

Ứng dụng có thể trả dữ liệu cache đang stale nhưng vẫn nằm trong giới hạn cho phép, đồng thời làm mới ở nền. Cần phân biệt:

- **Fresh TTL:** dữ liệu được xem là mới.
- **Stale window:** dữ liệu cũ có thể phục vụ tạm.
- **Hard expiry:** vượt ngưỡng này thì không được dùng.

~~~text
if age <= fresh_ttl:
    return cached_value
elif age <= hard_expiry:
    return cached_value_with_stale_flag
    trigger_refresh_in_background()
else:
    load_from_source_or_return_unavailable()
~~~

Stale bound phải được quyết định theo nghiệp vụ. Danh mục dịch vụ có thể chấp nhận vài phút; quyền truy cập, số dư hoặc trạng thái đặt chỗ không nên dựa vào cache cũ khi commit.

### Read replica làm fallback

Read replica có thể được dùng khi writer đang bận hoặc một query đọc không cần read-after-write. Nhưng cần kiểm tra replication lag và xác định query nào chấp nhận stale. Không chuyển query cần dữ liệu mới nhất sang replica mà không có consistency contract.

### Fallback không được vượt authorization

Nếu primary auth service không hoạt động, dùng cached authorization decision chỉ khi policy cho phép, thời hạn ngắn và dữ liệu đủ mới. Khi quyền bị thu hồi, cache cũ có thể gây truy cập trái phép. Một số thao tác nhạy cảm phải fail closed dù điều đó làm giảm availability.

## 6. Timeout, retry và giới hạn thời gian fallback

Fallback chỉ hữu ích nếu hệ thống phát hiện dependency chậm đủ sớm. Không đặt timeout bằng toàn bộ deadline request rồi mới thử đường khác.

### Timeout budget

Giả sử API có deadline 2 giây:

~~~text
Total request budget: 2000 ms
  Authentication:          150 ms
  Core database:            700 ms
  Optional recommendation:  250 ms
  Response/serialization:   150 ms
  Safety margin:            250 ms
  Unallocated reserve:      500 ms
~~~

Các con số chỉ minh họa. Nên cấp timeout cho dependency theo SLO và thời gian còn lại. Nếu recommendation không phản hồi trong 250 ms, API có thể bỏ nhánh đó và trả kết quả cốt lõi. Không tiếp tục chờ 2 giây rồi mới degrade.

### Retry có chọn lọc

Retry chỉ nên áp dụng với lỗi có khả năng phục hồi và thao tác idempotent. Thử lại request ghi có kết quả không rõ có thể tạo side effect trùng. Dùng exponential backoff, jitter, số lần tối đa và deadline tổng.

Không retry lỗi authentication/authorization rõ ràng, lỗi validation/business rule không thể tự khỏi, request không idempotent khi thiếu cơ chế bảo vệ, hoặc dependency đã vượt deadline request.

### Retry budget

Giới hạn tỷ lệ request được retry trong một khoảng thời gian hoặc số retry theo request. Khi dependency đang outage, giảm retry giúp bảo vệ tài nguyên và tránh tạo bão request.

## 7. Circuit breaker, bulkhead và load shedding

Ba mẫu này bảo vệ hệ thống trước lỗi dependency nhưng giải quyết các vấn đề khác nhau.

### Circuit breaker

Circuit breaker theo dõi lỗi hoặc latency của dependency. Khi vượt ngưỡng, nó **open** và từ chối gọi dependency trong một khoảng thời gian; sau đó chuyển **half-open** để thử một số request; nếu ổn thì **closed** trở lại.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Error/latency threshold exceeded
    OPEN --> HALF_OPEN: Cooldown elapsed
    HALF_OPEN --> CLOSED: Probe succeeds
    HALF_OPEN --> OPEN: Probe fails
~~~

Khi breaker open, caller phải có hành vi rõ: dùng cache, bỏ feature phụ, enqueue nếu phù hợp hoặc trả lỗi. Circuit breaker không tự chọn fallback và cũng không sửa dependency.

Với nhiều application instance, breaker local có thể mở ở instance này nhưng chưa mở ở instance khác. Điều đó có thể hợp lý để tránh state store toàn cục, nhưng cần hiểu phạm vi và tổng lượng probe. Không giả định local breaker đồng bộ toàn cluster.

### Bulkhead

Bulkhead tách tài nguyên để lỗi một dependency không chiếm hết thread, connection hoặc worker của hệ thống. Ví dụ recommendation có pool 20 concurrency riêng; database core có pool riêng. Recommendation bị treo sẽ không giữ hết connection phục vụ booking.

### Load shedding

Khi hệ thống gần quá tải, từ chối sớm một số request hoặc feature không ưu tiên để bảo vệ năng lực còn lại. Có thể ưu tiên core transaction, giới hạn tenant, tạm tắt export hoặc giảm recommendation.

Load shedding cần thứ tự ưu tiên theo tác động nghiệp vụ, quota và rate limit theo tenant/operation, response có retry guidance, và metric cho số request bị shed. Không để client retry lập tức tạo thêm tải.

## 8. Phụ thuộc không trọng yếu và xử lý bất đồng bộ

Một cách hiệu quả để giảm coupling là đưa công việc không cần kết quả ngay ra khỏi critical path.

Ví dụ khi booking được xác nhận:

1. Booking Service commit booking state và một outbox event trong cùng transaction.
2. Relay phát BookingConfirmed lên broker.
3. Notification worker nhận event và gửi email.
4. Analytics consumer cập nhật số liệu.
5. Nếu email provider lỗi, worker retry theo policy và có thể chuyển DLQ.

~~~mermaid
flowchart TD
    API["Create booking request"] --> CORE["Core booking transaction"]
    CORE --> DB[("Booking DB")]
    CORE --> OUT[("Transactional outbox")]
    OUT --> RELAY["Outbox relay"]
    RELAY --> Q[("Durable event queue")]
    Q --> N["Notification worker"]
    Q --> A["Analytics consumer"]
    N --> EP["Email/SMS provider"]
    N --> DLQ[("Dead-letter queue")]
~~~

Booking đã được lưu thì email có thể chậm mà không làm mất booking. Tuy nhiên, client response phải nói đúng trạng thái: booking confirmed, notification pending hoặc chưa gửi; không khẳng định email đã được giao khi chỉ mới enqueue.

### Queue không phải nơi đẩy lỗi vô hạn

Queue có retention, storage và throughput giới hạn. Khi consumer không theo kịp, cần theo dõi depth và oldest message age, giới hạn producer hoặc áp backpressure, điều chỉnh consumer concurrency theo capacity downstream, định nghĩa retry count và DLQ, có runbook poison message/replay. Nếu queue đầy hoặc không thể lưu bền vững, trả lỗi tiếp nhận thay vì giả vờ đã nhận.

### Phân biệt accepted với completed

HTTP 202 có thể biểu thị request đã được tiếp nhận để xử lý bất đồng bộ, nhưng API cần cung cấp operation ID/status endpoint hoặc callback. 202 không có nghĩa tác vụ đã hoàn thành. Với giao dịch tài chính, booking hay tác vụ có side effect, semantics này phải được ghi rõ.

## 9. Fallback cho ghi dữ liệu và giao dịch

Read fallback thường dễ hơn write fallback. Khi đọc catalog, có thể trả bản cache cũ. Khi ghi booking hoặc thanh toán, một kết quả mơ hồ có thể gây trùng giao dịch hoặc vi phạm dữ liệu.

Nguyên tắc với write path:

- Chỉ xác nhận thành công khi source of truth đã commit hoặc một durable acceptance mechanism được hợp đồng định nghĩa.
- Dùng idempotency key cho retry cùng ý định.
- Lưu operation state và correlation ID để tra cứu kết quả không rõ.
- Với workflow dài, trả trạng thái pending và cung cấp cách kiểm tra.
- Không đổi sang provider/route khác rồi thực hiện lại thao tác ghi nếu chưa xác minh provider cũ không xử lý.

### Ví dụ payment timeout

Payment provider timeout sau khi nhận charge request. Hệ thống không biết provider đã charge hay chưa. Fallback an toàn:

1. Đánh dấu payment UNKNOWN hoặc PENDING_RECONCILIATION.
2. Giữ cùng provider idempotency key và operation reference.
3. Tra cứu trạng thái giao dịch theo reference.
4. Nếu đã capture, lưu kết quả và tiếp tục booking.
5. Nếu chắc chắn chưa capture, retry theo provider contract.
6. Nếu không thể xác định, chuyển reconciliation/manual review.

Không gọi provider thứ hai với key mới chỉ vì provider đầu chậm. Điều này có thể charge khách hàng hai lần.

### Fallback sang replica hoặc region

Nếu writer chính không khả dụng, chỉ failover ghi khi có cơ chế fencing để bảo đảm một writer active, xác định được trạng thái commit và chấp nhận RPO. Nếu điều đó chưa được đảm bảo, có thể tạm dừng write hoặc tiếp nhận yêu cầu dưới trạng thái pending trong một durable queue, nhưng không giả vờ transaction đã hoàn tất.

## 10. Dependency graph và cascading failure

Một request có thể phụ thuộc gián tiếp qua nhiều tầng. API gọi service A; A gọi B và C; C gọi D. Nếu D chậm, connection và worker của C bị giữ; C chậm khiến A giữ tài nguyên; cuối cùng API timeout và tạo retry mới. Lỗi ban đầu nhỏ có thể lan rộng.

~~~mermaid
flowchart TD
    CLIENT["Clients / retries"] --> API["API service"]
    API --> A["Core service"]
    API --> OPT["Optional service"]
    A --> DB["Database"]
    A --> C["Internal dependency"]
    C --> D["External provider"]
    D -. "Latency / failure" .-> C
    C -. "Resource exhaustion" .-> A
    A -. "Queue/thread saturation" .-> API
    API -. "Retry amplification" .-> CLIENT
~~~

Các lớp bảo vệ gồm timeout ở mọi network boundary, retry budget và backoff/jitter, circuit breaker, bulkhead tách pool/thread/queue, concurrency/rate limit, load shedding theo ưu tiên nghiệp vụ, cache/default response cho read path được phép stale, queue/outbox cho side effect không cần đồng bộ và capacity headroom có giới hạn.

Autoscaling không phải fallback vô hạn. Nếu mọi instance mới lại mở thêm connection tới database đang quá tải, scale ứng dụng có thể làm sự cố nặng hơn.

## 11. Multi-provider và đường dự phòng độc lập

Một số năng lực có thể dùng provider dự phòng: DNS, email/SMS, object storage, identity, payment hoặc region. Nhưng hai nhà cung cấp không mặc nhiên thay thế được nhau.

Trước khi dùng alternate provider, phải xác minh API/status/error mapping tương thích, credential/quota/billing sẵn sàng, residency/compliance cho phép, idempotency hoạt động xuyên chuyển đổi, routing/failback không làm hai provider cùng xử lý một ý định, health check phản ánh nghiệp vụ và quy trình failback đã được thử.

### Active-passive và active-active

- **Active-passive:** provider chính xử lý, provider phụ chỉ nhận traffic khi failover. Dễ xác định ownership hơn nhưng cần đảm bảo provider phụ sẵn sàng và quota đủ.
- **Active-active:** cả hai provider xử lý đồng thời hoặc chia traffic. Tăng capacity và resilience nhưng cần conflict handling, idempotency và reconciliation.

Đối với payment hoặc identity, active-active có thể phức tạp do mỗi provider có state, fraud policy và transaction reference riêng. Không triển khai chỉ để tăng uptime trên giấy.

## 12. Health check và quyết định kích hoạt fallback

Health check cần phản ánh khả năng thực hiện operation cần thiết. Một HTTP 200 từ root endpoint không chứng minh database query, permission hoặc downstream workflow đang hoạt động.

- **Liveness:** process còn sống và có thể tiếp tục chạy.
- **Readiness:** instance có thể nhận loại traffic hiện tại.
- **Dependency health:** trạng thái database, broker, provider hoặc feature cụ thể.

Không nhất thiết đưa mọi optional dependency vào readiness của toàn service. Nếu recommendation lỗi và booking vẫn hoạt động, đánh dấu toàn API not-ready sẽ làm giảm availability không cần thiết.

Fallback có thể kích hoạt từ timeout/error rate/latency vượt threshold, circuit breaker open, provider quota exhausted, operator kill switch, maintenance window hoặc health policy phát hiện response sai. Threshold cần cửa sổ và hysteresis để tránh bật/tắt liên tục. Cần cooldown, probe giới hạn và gradual recovery.

### Kill switch và feature flag

Feature flag có thể tắt một phần không trọng yếu nhanh chóng. Quyền thay đổi cần được kiểm soát và audit; config phải có default an toàn; phân biệt flag vận hành với flag sản phẩm; flag khẩn cấp cần owner và ngày hết hạn. Không dùng flag để bỏ qua security hoặc business invariant.

## 13. Observability cho graceful degradation

Khi fallback hoạt động, hệ thống có thể tiếp tục trả response 200 nhưng chất lượng đã suy giảm. Nếu chỉ theo dõi HTTP availability, đội vận hành có thể không biết một feature đang tắt nhiều giờ.

| Metric | Mục đích |
| --- | --- |
| Fallback invocation count/rate | Biết fallback được sử dụng bao nhiêu |
| Fallback reason | Timeout, breaker open, quota, cache miss hay operator switch |
| Stale response age | Đo tuổi dữ liệu trả về |
| Optional feature availability | Theo dõi từng tính năng không trọng yếu |
| Dependency latency/error | Phát hiện lỗi trước khi fallback tăng |
| Queue depth/oldest age | Theo dõi tác vụ bị trì hoãn |
| Retry/circuit state | Phát hiện retry storm hoặc breaker flapping |
| Shed/throttle count | Đo mức tải bị từ chối |
| Recovery time | Đo thời gian trở lại chế độ bình thường |
| Business outcome | Booking/payment thành công, hủy hoặc pending |

Gắn trường degraded_mode, fallback_reason, dependency name, correlation ID và operation ID vào log/trace. Không ghi payload nhạy cảm hoặc credential. Trace cần cho thấy nhánh nào bị bỏ qua, nhánh nào chạy thay thế và thời gian tiết kiệm được.

### Alert theo trải nghiệm

Cảnh báo khi tỷ lệ fallback vượt ngưỡng hoặc kéo dài, stale age vượt bound, queue backlog/oldest age vượt SLO, core transaction fail, dependency phục hồi nhưng circuit vẫn open, hoặc fallback provider có success rate thấp hơn mức yêu cầu.

Không chỉ cảnh báo service down; hãy cảnh báo tác động tới người dùng và nghiệp vụ.

## 14. Kiểm thử failure path và recovery path

Fallback cần được kiểm thử như đường xử lý chính. Chỉ có unit test cho nhánh default là chưa đủ.

Các nhóm kiểm thử:

1. **Dependency timeout:** mô phỏng dependency không trả lời; API có degrade trong deadline không?
2. **Dependency 5xx/429:** retry/backoff và breaker hoạt động đúng không?
3. **Cache unavailable:** nguồn dữ liệu có chịu được fallback QPS không?
4. **Stale data:** quá stale bound có bị từ chối không; dữ liệu nhạy cảm có bị phục vụ sai không?
5. **Queue full/backlog:** producer có báo accepted sai hoặc giữ queue vô hạn không?
6. **Provider failover:** route dự phòng có credential, quota và semantics đúng không?
7. **Partial response:** client hiểu feature nào không sẵn sàng và dữ liệu nào là stale không?
8. **Concurrent requests:** nhiều request cùng kích hoạt fallback có tạo stampede hoặc duplicate không?
9. **Recovery:** dependency phục hồi có gradual traffic, probe và đóng breaker đúng không?
10. **Kill switch:** operator có thể tắt feature an toàn và có audit không?

### Fault injection và chaos engineering

Trong môi trường thử nghiệm, chủ động gây latency, packet loss, connection reset, HTTP 500, quota exhaustion hoặc broker slowdown. Đo cả hệ thống bình thường lẫn degraded mode. Giữ phạm vi thử nghiệm giới hạn để không gây ảnh hưởng production ngoài kế hoạch được phê duyệt.

Chaos experiment kiểm tra một giả thuyết có thể đo, ví dụ “Recommendation Service lỗi không làm Booking API vượt p95 500 ms”. Mỗi thử nghiệm cần giả thuyết, blast radius, điều kiện dừng an toàn, metric quan sát, owner, kết quả mong đợi và recovery procedure.

## 15. Ví dụ thiết kế: trang đặt lịch hoạt động khi recommendation và notification lỗi

**Bối cảnh giả định:** Một ứng dụng đặt lịch dùng Booking Service, Customer Profile, Recommendation, Email Provider và Analytics. Booking được lưu trong relational database. Recommendation có thể timeout trong giờ cao điểm; email provider có đợt lỗi; analytics không có yêu cầu real-time. SLO của trang lịch hẹn là p95 dưới 500 ms và availability 99,9%. Đây là mục tiêu luyện tập.

### Phân loại phụ thuộc

| Dependency | Vai trò | Criticality với trang lịch hẹn |
| --- | --- | --- |
| Authentication/authorization | Xác minh user và quyền xem lịch | Bắt buộc |
| Booking database/service | Đọc booking chính xác | Bắt buộc |
| Customer profile | Tên hiển thị, tùy field | Có thể dùng snapshot tối thiểu nếu policy cho phép |
| Recommendation | Gợi ý dịch vụ | Không trọng yếu |
| Email provider | Gửi thông báo sau commit | Không trọng yếu với response booking; cần xử lý nền |
| Analytics | Ghi event xem trang | Không trọng yếu |

### Đường xử lý

1. Xác thực user và kiểm tra quyền.
2. Đọc booking từ source of truth hoặc read model có consistency phù hợp.
3. Gọi profile trong timeout nhỏ; nếu không có, dùng field display name đã lưu nếu còn hợp lệ.
4. Gọi recommendation với deadline ngắn; khi lỗi, trả phần gợi ý rỗng kèm degraded flag.
5. Ghi analytics event bất đồng bộ; nếu broker/queue không nhận được, áp policy log/buffer hoặc bỏ event tùy mức quan trọng.
6. Email được phát sau booking commit qua outbox; worker retry và DLQ.

~~~mermaid
flowchart TD
    U["User"] --> API["Booking page API"]
    API --> AUTH["Auth / authorization"]
    API --> BOOK["Booking source of truth"]
    API --> PROF["Profile with short timeout"]
    API --> REC["Recommendation with circuit breaker"]
    PROF --> RESP["Compose response"]
    REC --> RESP
    REC -. "Failure: omit suggestions" .-> RESP
    RESP --> U
    BOOK --> OUT["Outbox"]
    OUT --> Q[("Queue")]
    Q --> EMAIL["Email worker"]
    Q --> ANA["Analytics consumer"]
~~~

### Hành vi khi dependency lỗi

- Nếu Booking Service không truy cập được và không có read replica đủ mới, không hiển thị lịch đoán; trả unavailable hoặc trạng thái retry rõ.
- Nếu Recommendation lỗi, không chặn trang; tắt gợi ý.
- Nếu Email lỗi sau commit, booking vẫn có trạng thái chính xác; notification pending được theo dõi và retry.
- Nếu Analytics lỗi, không làm tăng latency trang; có thể chấp nhận mất event không trọng yếu theo policy hoặc dùng durable queue nếu event cần lưu.
- Nếu authorization lỗi, fail closed cho dữ liệu riêng tư.

### Acceptance criteria

- Recommendation timeout không làm p95 trang vượt deadline mục tiêu.
- Booking vẫn đọc đúng và không lộ chéo user khi profile lỗi.
- Email retry không gửi duplicate không kiểm soát; operation có ID và idempotency.
- Degraded response có metric và trace rõ.
- Queue backlog và DLQ có cảnh báo.
- Khi dependency phục hồi, hệ thống mở lại traffic có kiểm soát.

## 16. Bài thực hành: thiết kế degraded mode cho nền tảng thương mại điện tử

**Tình huống:** Một nền tảng bán hàng có Catalog, Inventory, Pricing, Recommendation, Payment, Notification và Analytics. Catalog và Inventory có cache; Pricing cần quy tắc khuyến mại; Payment gọi provider bên ngoài. Người dùng phải xem sản phẩm, thêm giỏ, đặt hàng và thanh toán. Các tính năng gợi ý, review tổng hợp và analytics có thể chậm hơn. Đây là kịch bản mô phỏng.

### Nhiệm vụ

1. **Lập dependency graph:** xác định đồng bộ/bất đồng bộ, criticality theo từng use case và failure impact.
2. **Định nghĩa degraded mode:** với mỗi dependency lỗi, xác định fallback, stale bound, default response, fail-fast hoặc queue.
3. **Phân bổ timeout budget:** đặt deadline cho API, dependency và safety margin; quy định retry budget.
4. **Thiết kế bảo vệ:** circuit breaker, bulkhead, concurrency limit, load shedding và kill switch.
5. **Thiết kế write path:** xử lý payment timeout, inventory uncertainty, queue full và kết quả mơ hồ bằng idempotency/reconciliation.
6. **Thiết kế observability:** fallback rate, stale age, queue backlog, breaker state, shed count và business outcome.
7. **Thiết kế recovery:** probe, gradual ramp-up, replay, DLQ và quy trình tắt degraded mode.

### Ma trận tình huống

| Dependency lỗi | Phương án cần đánh giá | Điều không được làm |
| --- | --- | --- |
| Recommendation | Ẩn gợi ý/default list | Chặn trang sản phẩm |
| Review aggregation | Dùng rating snapshot có timestamp hoặc ẩn rating | Hiển thị số liệu cũ như dữ liệu mới |
| Catalog cache | Fallback nguồn có giới hạn hoặc cached stale trong bound | Đẩy toàn bộ request không giới hạn về DB |
| Inventory source | Trả trạng thái unavailable/pending hoặc revalidate sau | Xác nhận hàng còn khi không biết |
| Pricing | Dùng rule snapshot đã version nếu policy cho phép; nếu không fail closed | Tự đoán giá/khuyến mại |
| Payment provider | Unknown state, query/reconcile cùng idempotency key | Charge qua provider khác bằng key mới |
| Notification | Outbox/queue retry và DLQ | Rollback đơn chỉ vì email lỗi |
| Analytics | Async event hoặc drop theo policy có audit | Giữ request checkout chờ analytics |

### Kiểm thử

- Gây timeout từng dependency và đo p95/p99 của use case.
- Mô phỏng cache outage để kiểm tra database không bị stampede.
- Làm chậm queue consumer và quan sát backlog/backpressure.
- Payment provider timeout sau khi đã nhận charge; kiểm tra không charge trùng.
- Pricing service lỗi; kiểm tra giá không bị áp dụng sai.
- Bật/tắt circuit breaker và kill switch, xác minh audit.
- Phục hồi dependency, tăng traffic dần và kiểm tra fallback không còn bật quá lâu.

### Deliverables

- Dependency graph và criticality matrix.
- Degradation contract cho từng use case.
- Timeout/retry budget và circuit/bulkhead policy.
- Fallback design cho read/write/async path.
- Dashboard, alert, runbook và recovery procedure.
- Fault injection/chaos test report và ADR.

## 17. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi cho fallback và degraded mode |
| --- | --- |
| **Operational Excellence** | Có dependency inventory, runbook, kill switch, owner, degraded dashboard và quy trình khôi phục không? |
| **Security** | Fallback có giữ authorization, tenant isolation, data classification, key và policy không? |
| **Reliability** | Optional failure có bị cô lập? Timeout, retry, circuit, bulkhead, queue và recovery đã được thử? |
| **Performance Efficiency** | Fallback có deadline ngắn, hạn chế fan-out và không tạo thêm bottleneck không? |
| **Cost Optimization** | Có tránh multi-provider/standby/queue dư thừa và autoscaling không kiểm soát? |
| **Sustainability** | Có tránh retry storm, polling liên tục, refresh thừa và giữ tài nguyên degraded vô hạn không? |

## 18. Những sai lầm thường gặp

**Coi mọi dependency là critical.** Một dịch vụ gợi ý hoặc analytics có thể làm giảm availability nếu nằm trên critical path không cần thiết.

**Fallback bằng dữ liệu stale không giới hạn.** Dữ liệu cũ có thể gây quyết định sai; luôn có fresh TTL, stale bound và hard expiry.

**Bỏ qua authorization khi dependency lỗi.** Không được dùng fallback để xem dữ liệu mà policy không cho phép.

**Chờ dependency tới hết request timeout rồi mới fallback.** Đã hết thời gian hữu ích cho response; timeout từng nhánh phải nhỏ hơn deadline tổng.

**Retry vô hạn.** Retry storm có thể làm dependency và hệ thống của mình tiếp tục quá tải.

**Circuit breaker mở nhưng không có hành vi thay thế.** Caller vẫn có thể thất bại hoặc trả lỗi thiếu rõ ràng.

**Dùng local cache làm durable write buffer.** Process/node mất có thể làm mất dữ liệu chưa commit.

**Chuyển payment sang provider khác sau timeout mà không tra cứu.** Có thể tạo giao dịch kép.

**Tắt một feature nhưng không có metric.** Degraded mode có thể kéo dài mà không ai biết.

**Tự động failback ngay khi dependency vừa hồi phục.** Traffic spike có thể làm hệ thống lỗi lại; cần probe và gradual ramp.

**Queue mọi thứ mà không có retention/backpressure.** Backlog có thể tăng vô hạn, làm chi phí và độ trễ vượt kiểm soát.

**Health check optional dependency làm cả service not-ready.** Một feature phụ lỗi không nhất thiết phải rút core service khỏi load balancer.

## 19. Checklist trước khi đưa degraded mode vào production

- [ ] Dependency graph theo từng use case được lập và có owner.
- [ ] Criticality phân biệt correctness/security dependency với optional feature.
- [ ] Degraded behavior và phần tính năng bị giảm được mô tả rõ trong API/UI contract.
- [ ] Mỗi fallback có trigger, timeout, stale bound, hard expiry và điều kiện dừng.
- [ ] Authorization và business invariant vẫn được giữ trong mọi fallback.
- [ ] Read fallback không trình bày dữ liệu stale như trạng thái mới nhất.
- [ ] Write fallback có idempotency, operation state và reconciliation.
- [ ] Optional side effect được đưa khỏi critical path bằng outbox/queue khi phù hợp.
- [ ] Queue có durable acceptance, retention, backpressure, retry và DLQ.
- [ ] Timeout budget, retry budget, circuit breaker, bulkhead và load shedding được cấu hình.
- [ ] Alternate provider có semantics, quota, credential, routing và failback đã được kiểm chứng.
- [ ] Health check không gộp optional dependency vào readiness không cần thiết.
- [ ] Kill switch/feature flag có access control, audit, owner và expiry.
- [ ] Metric/log/trace theo dõi fallback reason, stale age, queue age và business outcome.
- [ ] Có fault injection, concurrency, provider timeout và recovery tests.
- [ ] Đã diễn tập gradual recovery, failback và xử lý trạng thái pending/unknown.
- [ ] Chi phí fallback, standby, queue, cache và headroom có budget.

Đường dự phòng và graceful degradation giúp hệ thống giữ những giá trị nghiệp vụ cốt lõi khi phụ thuộc gặp lỗi. Muốn làm được điều đó, phải phân loại dependency theo từng use case, xác định phần nào bắt buộc cho tính đúng đắn hoặc bảo mật, và chọn fallback có semantics rõ. Cache stale, default response, queue, alternate provider và fail-fast đều có vị trí riêng; chúng cần timeout, giới hạn, idempotency, observability và quy trình phục hồi tương ứng. Hệ thống đáng tin không phải hệ thống che giấu mọi sự cố, mà là hệ thống suy giảm có kiểm soát, không tạo kết quả sai và biết cách trở lại hoạt động bình thường.
