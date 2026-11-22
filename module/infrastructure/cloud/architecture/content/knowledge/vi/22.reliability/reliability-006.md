# Timeout nhiều tầng và kiểm soát retry storm

Một request trong hệ thống cloud thường đi qua nhiều thành phần: client, API gateway, service xử lý nghiệp vụ, cache, database, dịch vụ bên ngoài và đôi khi cả message broker. Mỗi thành phần có thể đặt timeout riêng. Nếu các timeout không được thiết kế thành một ngân sách thống nhất, request có thể bị chờ lâu hơn mức người dùng chấp nhận, retry ở nhiều tầng có thể nhân số lần gọi lên theo cấp số nhân, và một dependency đang chậm có thể kéo cả hệ thống xuống.

**Retry storm** là tình trạng nhiều client hoặc service đồng loạt gửi lại request khi dependency lỗi/chậm, làm lượng tải tăng đúng lúc hệ thống ít khả năng xử lý nhất. Retry vốn giúp vượt qua lỗi tạm thời, nhưng khi thiếu giới hạn, backoff, jitter, deadline và idempotency, nó biến lỗi cục bộ thành sự cố diện rộng.

Trong module **CLOUD_ARCHITECTURE**, bài học này đặt timeout và retry trong bối cảnh thiết kế độ tin cậy, khả năng mở rộng, vận hành và chi phí. Ta sẽ xây dựng timeout theo tầng, phân bổ deadline end-to-end, kiểm soát retry amplification, bảo vệ dependency bằng bulkhead/circuit breaker/load shedding và đo lường để phát hiện sớm retry storm.

## 1. Vì sao timeout nhiều tầng là một vấn đề kiến trúc?

Xét luồng đặt chỗ đơn giản:

~~~mermaid
flowchart LR
    C["Client"] --> G["API Gateway"]
    G --> B["Booking API"]
    B --> I["Inventory"]
    B --> P["Payment"]
    B --> D["Database"]
~~~

Client đợi tối đa 2 giây. Gateway có timeout 3 giây. Booking API chờ Inventory 2 giây, Payment 4 giây và Database 3 giây. Các dependency có thể được gọi tuần tự hoặc song song; retry có thể xuất hiện ở client, gateway, service mesh, SDK và service code.

Nếu mỗi tầng tự đặt một timeout mà không nhìn deadline chung, sẽ có những tình huống:

- Client đã bỏ cuộc nhưng server vẫn giữ thread, connection và tiếp tục gọi downstream.
- Gateway trả 504 nhưng service tiếp tục xử lý và commit side effect sau đó.
- Service A retry, service B cũng retry, SDK bên dưới lại retry; một request logic tạo ra hàng chục request vật lý.
- Retry dồn vào cùng thời điểm do mọi instance dùng cùng backoff cố định.
- Request chậm giữ connection pool, thread pool và queue slot; request mới càng khó được xử lý.

Timeout nhiều tầng không phải tập hợp các con số độc lập. Chúng phải tạo thành **một hợp đồng thời gian xuyên suốt** từ điểm bắt đầu tới điểm kết thúc của hành trình.

## 2. Phân biệt timeout, deadline và execution limit

| Khái niệm | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| Connect timeout | Thiết lập TCP/TLS hoặc kết nối tới dependency | Giới hạn thời gian thiết lập kết nối |
| Pool-acquisition timeout | Chờ connection từ pool | Tránh chờ vô hạn khi pool cạn |
| Request/response timeout | Một lần gọi HTTP/RPC | Giới hạn thời gian chờ phản hồi |
| Read/idle timeout | Chờ dữ liệu tiếp theo trên stream | Phát hiện kết nối không tiến triển |
| Query/statement timeout | Một truy vấn database | Giới hạn thời gian DB thực thi/chờ |
| Transaction timeout | Một transaction | Giới hạn khoảng thời gian transaction được phép mở |
| Deadline | Toàn bộ request/job | Thời điểm cuối cùng kết quả còn giá trị |
| Execution limit | Process, function hoặc job runtime | Giới hạn thời gian thực thi tối đa ở nền tảng |

Timeout thường giới hạn một thao tác tại một tầng. Deadline là giới hạn end-to-end. Một request có thể gọi ba dependency với timeout mỗi lần 1 giây và retry hai lần, nên tổng thời gian vượt xa deadline 2 giây nếu không tính ngân sách còn lại.

### Timeout không tự hủy side effect

Caller ngừng chờ không chứng minh server đã dừng. Database có thể đã commit; payment provider có thể đã thu tiền nhưng response bị mất; message có thể đã được publish. Vì vậy cần phân biệt:

- Không gửi request vì deadline đã hết.
- Request đã gửi nhưng chưa biết server có nhận hay không.
- Server đang xử lý và có thể được cancellation.
- Side effect đã commit và cần đối soát thay vì rollback giả định.

Với thao tác ghi, timeout sau khi gửi thường tạo kết quả **chưa xác định**. Idempotency key và operation status cần được thiết kế cùng timeout.

## 3. Phân cấp timeout theo tầng

Một kiến trúc có thể đặt giới hạn ở các lớp sau:

| Tầng | Timeout/giới hạn | Mục tiêu |
| --- | --- | --- |
| Client | User-visible request deadline | Giới hạn trải nghiệm chờ và hành trình |
| Edge/API gateway | Upstream request timeout | Không giữ kết nối edge vô hạn |
| Application server | Request deadline/concurrency timeout | Bảo vệ worker và thread |
| Service-to-service client | Connect + call timeout | Bảo vệ từng dependency call |
| Connection pool | Acquire timeout | Phát hiện cạn pool thay vì xếp hàng vô hạn |
| Database | Statement, lock, transaction timeout | Bảo vệ DB khỏi query/lock kéo dài |
| Queue consumer | Processing deadline/lease/visibility timeout | Kiểm soát job và retry delivery |
| Platform runtime | Graceful shutdown/execution limit | Đảm bảo process không bị giữ mãi |

Timeout ở các tầng cần nhất quán về thứ tự. Ví dụ, query timeout thường phải nhỏ hơn phần ngân sách còn lại của application request. Gateway timeout nên phối hợp với deadline của backend để tránh gateway trả lỗi trong khi backend vẫn tiếp tục làm việc không cần thiết.

Không có một thứ tự số học cố định áp dụng cho mọi hệ thống. Điều quan trọng là request phía trong biết thời gian còn lại và các lớp ngoài dành đủ thời gian cho cleanup, serialize và trả response.

## 4. Xây dựng deadline end-to-end

Bắt đầu từ SLO của hành trình, sau đó phân bổ ngân sách cho từng giai đoạn. Ví dụ API tìm kiếm có mục tiêu p99 dưới 1.500 ms:

| Thành phần | Budget minh họa |
| --- | ---: |
| DNS/connect/TLS và gateway | 120 ms |
| Authentication và routing | 80 ms |
| Xử lý application | 150 ms |
| Search dependency | 650 ms |
| Metadata/database | 220 ms |
| Serialize, network response và headroom | 280 ms |
| **Tổng** | **1.500 ms** |

Đây là budget khởi điểm, cần điều chỉnh theo đo đạc thực tế. Các thành phần tuần tự cộng thời gian; các lời gọi song song hoàn thành theo nhánh chậm nhất nhưng đồng thời dùng nhiều connection và concurrency hơn.

Với các dependency gọi tuần tự:

\[
T_{\text{total}}\approx T_1+T_2+\dots+T_n+T_{\text{overhead}}.
\]

Với các dependency độc lập được gọi song song:

\[
T_{\text{total}}\approx\max(T_1,T_2,\dots,T_n)+T_{\text{overhead}}.
\]

### Remaining budget

Khi tới một tầng mới, không cấp lại toàn bộ timeout ban đầu. Tầng đó phải tính phần thời gian còn lại tới deadline, trừ phần cần cho xử lý và trả kết quả.

Ví dụ deadline còn 400 ms, cần dự trù 80 ms cho cleanup/serialize/response. Dependency chỉ nên dùng tối đa khoảng 320 ms, và có thể ít hơn nếu còn một nhánh khác phải hoàn tất.

Nếu deadline đã hết, reject sớm và không bắt đầu thêm dependency call hoặc retry.

### Đừng nhầm p99 với timeout

p99 là thống kê độ trễ, timeout là chính sách giới hạn. Timeout đặt quá thấp có thể loại bỏ request hợp lệ trong tail; đặt quá cao có thể giữ tài nguyên quá lâu. Hãy xem p95/p99, error budget, deadline người dùng, thời gian cleanup và hành vi khi dependency overload. Không lấy một percentile rồi áp giống nhau cho mọi call.

## 5. Truyền deadline xuyên service

Các tầng cần một cách diễn đạt thời hạn thống nhất:

- Absolute deadline: thời điểm hết hạn.
- Remaining timeout: thời lượng còn lại.
- Protocol-native deadline: cơ chế sẵn có của RPC/framework.

Absolute deadline dễ giữ cùng mốc thời gian nhưng phụ thuộc đồng hồ được đồng bộ đủ tốt. Remaining timeout giảm phụ thuộc đồng hồ nhưng mỗi hop phải trừ thời gian đã tiêu thụ và overhead. Với gRPC, nên dùng deadline/context API của giao thức; với HTTP, cần một contract nội bộ rõ ràng nếu truyền remaining budget bằng header.

### Quy tắc propagation

1. Edge hoặc service đầu tiên xác định deadline theo policy server-side.
2. Validate và giới hạn maximum duration; không tin client có thể yêu cầu timeout vô hạn.
3. Truyền deadline/remaining budget xuống mọi dependency call.
4. Mỗi tầng chọn timeout nhỏ hơn hoặc bằng ngân sách còn lại.
5. Không retry khi backoff cộng thời gian call không còn fit deadline.
6. Khi hết hạn, phát cancellation tới tác vụ có thể dừng và giải phóng tài nguyên.
7. Ghi lại remaining budget tại các hop để điều tra nơi tiêu hết thời gian.

### Header nội bộ không phải chuẩn HTTP phổ quát

Một tổ chức có thể định nghĩa header như X-Request-Timeout-Ms. Nếu làm vậy phải thống nhất đơn vị, semantics, maximum, cách trừ ở từng hop, xử lý giá trị sai và cách gateway ghi đè header từ Internet. Chỉ tin header đó từ caller đã xác thực trong trusted boundary; không để client công khai tự chọn budget backend.

## 6. Vì sao retry storm xảy ra?

Giả sử một service nhận 1.000 request/giây. Mỗi request gọi một dependency. Dependency bắt đầu lỗi và client retry 3 lần. Nếu chỉ một tầng retry, dependency có thể nhận tối đa khoảng 4.000 lần gọi/giây trong giai đoạn retry (lần đầu cộng ba lần thử lại), chưa tính các request mới.

Nếu ba tầng độc lập cùng retry 3 lần mỗi tầng, số request có thể nhân theo tích số lần thử:

\[
N_{\text{downstream}}=N_{\text{initial}}\times A_1\times A_2\times\dots\times A_k
\]

Trong đó \(A_i\) là số lần thử tối đa tại tầng i, tính cả lần đầu. Nếu ba tầng mỗi tầng thử tối đa 4 lần, một request logic có thể tạo tới \(4^3=64\) lần gọi ở tầng cuối trong trường hợp xấu nhất.

Đây là retry amplification. Trên thực tế số request có thể thấp hơn do deadline/circuit breaker, hoặc cao hơn nếu có retry từ SDK, proxy, service mesh, queue redelivery và client cùng lúc.

### Vòng lặp khuếch đại sự cố

~~~mermaid
flowchart TD
    SLOW["Dependency chậm hoặc lỗi"]
    TIMEOUT["Caller timeout"]
    RETRY["Nhiều caller retry"]
    LOAD["Downstream nhận tải tăng"]
    QUEUE["Queue / connection pool tích tụ"]
    SLOW --> TIMEOUT
    TIMEOUT --> RETRY
    RETRY --> LOAD
    LOAD --> QUEUE
    QUEUE --> SLOW
~~~

Khi dependency chậm, request giữ tài nguyên lâu hơn. Timeout phát sinh, caller retry làm tải tăng; tải tăng khiến dependency chậm hơn. Queue và connection pool tích tụ, tạo vòng lặp dương có thể tiếp tục dù lỗi ban đầu đã giảm.

### Retry đồng bộ gây burst

Nếu nhiều instance cùng timeout tại mốc 1 giây và đều retry sau đúng 200 ms, retry tập trung tại cùng thời điểm. Jitter phân tán lịch retry, giảm đợt tải đồng loạt.

### Retry không phân biệt lỗi tạm thời và lỗi vĩnh viễn

Retry authentication failure, validation error, thiếu permission hoặc request malformed thường không giúp thành công. Nó chỉ tốn tài nguyên và có thể làm log/alert nhiễu hơn. Chỉ retry lỗi có khả năng hồi phục và được xác định rõ trong contract.

## 7. Chính sách retry: số lần, điều kiện và trách nhiệm

Một policy retry cần định nghĩa tối thiểu:

| Thành phần | Câu hỏi |
| --- | --- |
| Retryable errors | Lỗi nào có thể tạm thời? |
| Max attempts | Bao nhiêu lần thử tối đa, tính cả lần đầu? |
| Retry owner | Tầng nào chịu trách nhiệm retry? |
| Backoff | Chờ bao lâu giữa các lần thử? |
| Jitter | Có random hóa thời điểm retry không? |
| Deadline | Còn đủ thời gian cho lần thử tiếp theo không? |
| Idempotency | Lặp lại có gây side effect hai lần không? |
| Retry budget | Tổng lượng retry được phép trên toàn service là bao nhiêu? |
| Fallback | Khi không retry nữa, trả trạng thái gì hoặc chuyển luồng nào? |

### Một tầng nên sở hữu retry

Nếu client, gateway, service code và SDK đều retry mà không phối hợp, khó tính tổng số attempt. Thông thường nên đặt retry ở một tầng có đủ ngữ cảnh về idempotency và deadline; các tầng khác dùng timeout và trả lỗi có phân loại. Nếu bắt buộc có retry nhiều tầng, phải tính tổng số attempt và deadline theo toàn chuỗi.

### Retry chỉ với lỗi có khả năng hồi phục

Có thể cân nhắc retry có giới hạn cho connect reset, một số timeout, 429/503 theo contract hoặc lỗi tạm thời của broker. Không nên tự động retry:

- Validation error hoặc lỗi dữ liệu không hợp lệ.
- Authentication/authorization failure.
- Not found không có semantics eventual.
- Business conflict cần người dùng xử lý.
- Payment/booking write có kết quả chưa xác định nếu không có idempotency.

### Retry-After và server guidance

Nếu downstream trả Retry-After hoặc một retry hint có hợp đồng, caller nên tôn trọng nó nhưng vẫn phải kiểm tra deadline và retry budget. Không retry sớm hơn thời điểm server yêu cầu nếu điều đó tạo thêm tải.

## 8. Exponential backoff và jitter

Exponential backoff tăng thời gian chờ sau mỗi lần lỗi:

\[
delay_n=\min(cap,\ base\times 2^{n-1})
\]

Trong đó base là thời gian chờ ban đầu, cap là mức tối đa và n là số thứ tự retry. Có thể thêm jitter để phân tán thời điểm gửi lại.

### Full jitter

Một biến thể phổ biến:

\[
delay_n=random(0,\ \min(cap,\ base\times 2^{n-1}))
\]

Ví dụ base 100 ms, cap 2.000 ms:

| Lần retry | Backoff upper bound | Full jitter |
| --- | ---: | --- |
| 1 | 100 ms | 0–100 ms |
| 2 | 200 ms | 0–200 ms |
| 3 | 400 ms | 0–400 ms |
| 4 | 800 ms | 0–800 ms |
| 5 | 1.600 ms | 0–1.600 ms |

Các con số minh họa; chọn base/cap theo latency và deadline của workload. Backoff không được làm request vượt deadline. Full jitter có thể khiến một số retry diễn ra sớm; có thể dùng equal jitter/decorrelated jitter tùy workload và thư viện.

### Equal jitter

Một biến thể giữ lại một nửa backoff và random hóa nửa còn lại:

\[
delay_n=\frac{upper_n}{2}+random(0,\frac{upper_n}{2})
\]

Nó tránh các retry gần như ngay lập tức khi random ra gần 0, đồng thời phân tán lịch.

### Đừng chỉ dùng exponential mà thiếu cap

Nếu delay tăng mãi, job hoặc request có thể chờ lâu hơn thời hạn nghiệp vụ. Cap phải gắn với deadline/job expiry, không phải con số tùy ý. Với queue consumer, delay/retry schedule cần phối hợp visibility timeout, lease và DLQ.

## 9. Retry budget và giới hạn tổng lượng retry

Max attempts mỗi request không đủ khi request rate tăng lớn. Retry budget giới hạn lượng retry trong một khoảng thời gian, thường dựa trên số request gốc hoặc tỷ lệ retry cho phép.

Ví dụ một service có thể đặt retry budget là tối đa 10 retry trên mỗi 100 request gốc trong cửa sổ đo. Khi budget cạn, service fail fast hoặc trả lỗi downstream thay vì tiếp tục thử lại.

### Ví dụ budget theo tỷ lệ

Giả sử service nhận 20.000 request gốc/phút và policy cho phép retry tối đa 5%. Budget tương ứng 1.000 retry/phút. Khi đã dùng hết budget, các request mới không được retry tự động trong cửa sổ hiện tại.

Con số 5% chỉ là ví dụ. Cần xác định:

- Tính retry theo request, attempt hay dependency call.
- Budget global, theo dependency, endpoint, tenant hay region.
- Cách chia budget giữa instance để tránh mỗi instance tự tiêu toàn bộ quota.
- Reset/decay theo cửa sổ trượt hay token bucket.
- Hành vi khi budget cạn và cách expose metric.

### Token bucket cho retry

Một token bucket có thể tích lũy token retry theo tốc độ cho phép và giới hạn burst. Mỗi retry tiêu một token. Khi hết token, request không retry. Trong cluster nhiều instance, cần cơ chế phân bổ quota để tránh mỗi process có một bucket đầy độc lập làm tổng retry vượt dự kiến.

### Retry budget theo dependency

Dependency A đang khỏe không nên bị cắt retry chỉ vì dependency B đang lỗi. Budget theo dependency giúp khoanh vùng; budget toàn service vẫn cần để giữ tổng tải. Có thể thêm budget theo endpoint/tenant với giới hạn cardinality hợp lý.

## 10. Idempotency và retry thao tác ghi

Retry thao tác đọc thường ít rủi ro side effect hơn; retry POST/command ghi có thể tạo bản ghi, thu tiền hoặc gửi thông báo hai lần. HTTP method được gọi là idempotent theo semantics không có nghĩa implementation của ứng dụng luôn idempotent.

### Idempotency key

Client tạo một key ổn định cho một ý định nghiệp vụ và gửi lại cùng key khi retry. Server lưu key, scope tenant/principal, payload hash, trạng thái và kết quả. Cùng key/cùng payload trả lại kết quả đã có; cùng key/khác payload bị từ chối theo contract.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Booking API
    participant DB as Database
    C->>API: Create booking + idempotency key K
    API->>DB: Lookup K
    alt K chưa tồn tại
        API->>DB: Create operation and booking
        DB-->>API: Commit result
        API-->>C: Success + operation ID
    else K đã tồn tại
        DB-->>API: Existing status/result
        API-->>C: Return same logical result
    end
~~~

### Trạng thái chưa xác định

Nếu connection bị timeout sau khi server đã gửi command, caller không biết commit đã xảy ra hay chưa. API nên hỗ trợ tra cứu operation theo idempotency key hoặc operation ID. Không chuyển thành trạng thái failed chỉ vì client không nhận response.

### Scope và retention của idempotency key

Key thường phải được scope theo tenant/client/operation type để tránh xung đột giữa các caller. Retention của key phải dài hơn cửa sổ retry/replay có thể xảy ra. Với queue, dedupe cần theo event ID/operation ID và được lưu bền vững đủ lâu.

Không chỉ lưu key trong cache volatile nếu mất cache có thể khiến retry tạo side effect trùng. Với giao dịch quan trọng, lưu idempotency record trong cùng transaction với business state hoặc cơ chế tương đương.

## 11. Circuit breaker: ngừng gọi dependency đang không khỏe

Circuit breaker theo dõi kết quả gọi dependency và tạm ngăn request mới khi lỗi vượt ngưỡng. Mục tiêu là tránh tiếp tục gửi tải tới một dependency đang suy giảm và cho nó thời gian phục hồi.

Các trạng thái phổ biến:

- **Closed:** request được phép đi qua; breaker theo dõi lỗi/latency.
- **Open:** request bị chặn nhanh, trả lỗi/fallback mà không gọi dependency.
- **Half-open:** cho một số probe giới hạn đi qua để kiểm tra dependency đã phục hồi chưa.

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Error/slow-call threshold exceeded
    Open --> HalfOpen: Open duration elapsed
    HalfOpen --> Closed: Probe succeeds
    HalfOpen --> Open: Probe fails
~~~

### Cấu hình cần định nghĩa

| Tham số | Ý nghĩa |
| --- | --- |
| Failure threshold | Tỉ lệ/số lỗi cần đạt để mở breaker |
| Slow-call threshold | Tỉ lệ call chậm vượt ngưỡng |
| Minimum volume | Số request tối thiểu trước khi đánh giá |
| Sliding window | Khoảng mẫu dùng tính failure rate |
| Open duration | Thời gian breaker ở trạng thái Open |
| Half-open permits | Số probe được phép khi thử phục hồi |
| Exception classifier | Loại lỗi nào được tính là dependency failure |

Không tính lỗi validation, caller cancellation hoặc business conflict như lỗi sức khỏe dependency nếu chúng không phản ánh trạng thái dependency. Nếu threshold quá thấp, breaker có thể mở vì burst nhỏ; quá cao thì mở muộn. Cần quan sát và tuning theo từng dependency.

### Circuit breaker không thay timeout

Breaker có thể chặn request mới sau khi phát hiện lỗi, nhưng request đang bay vẫn cần timeout. Nó cũng không tự retry; retry policy vẫn phải có deadline/budget. Một breaker được đặt trước một client không kiểm soát request ở các đường gọi khác.

### Fallback phải có semantics

Fallback có thể là:

- Trả stale cache khi dữ liệu được phép cũ.
- Bỏ một tính năng phụ như recommendation.
- Trả trạng thái pending để client tra cứu sau.
- Từ chối nhanh với lỗi có thể retry sau.

Không fallback bằng dữ liệu giả cho giao dịch tài chính, authorization hoặc availability nếu có thể làm sai quyết định nghiệp vụ.

## 12. Bulkhead: cô lập tài nguyên giữa dependency

Bulkhead chia tài nguyên thành các pool/partition riêng để một dependency chậm không chiếm toàn bộ thread, connection hoặc queue của service.

~~~mermaid
flowchart TB
    API["Booking API"]
    API --> BI["Inventory bulkhead\nlimited concurrency"]
    API --> BP["Payment bulkhead\nlimited concurrency"]
    BI --> INV["Inventory service"]
    BP --> PAY["Payment service"]
~~~

Nếu Payment chậm, request chờ Payment chỉ chiếm pool/concurrency dành cho Payment; Inventory vẫn có thể được phục vụ theo capacity riêng.

### Các dạng bulkhead

- Thread pool riêng theo dependency.
- Semaphore giới hạn số call đồng thời.
- Connection pool riêng.
- Queue riêng theo workload/tenant tier.
- Worker pool riêng cho tác vụ nặng hoặc không tin cậy.
- CPU/memory limit và autoscaling theo workload.

### Chọn giới hạn

Concurrency limit cần tính theo capacity downstream, latency và số instance. Nếu mỗi instance có 100 permit và có 20 instance, tổng concurrency tối đa có thể là 2.000, chưa kể caller khác. Vì vậy giới hạn per-process phải phối hợp với global quota/downstream capacity.

Khi bulkhead đầy, đừng để request chờ vô hạn; dùng queue bounded hoặc reject fast với lỗi quá tải phù hợp. Đo queue wait và rejected count để biết giới hạn quá thấp hay downstream đang nghẽn.

## 13. Load shedding và admission control

Load shedding chủ động từ chối một phần request khi hệ thống không còn capacity an toàn. Admission control quyết định request nào được phép vào hệ thống dựa trên concurrency, queue depth, deadline hoặc priority.

### Khi nào nên shed load?

- Queue vượt ngưỡng và latency tiếp tục tăng.
- Thread/connection pool gần cạn.
- CPU, memory hoặc I/O tiến tới vùng nguy hiểm.
- Dependency đã mở circuit breaker.
- Request không còn đủ deadline để hoàn thành.
- Retry traffic chiếm tỉ lệ quá lớn so với request gốc.

### Ưu tiên và giảm cấp chức năng

| Mức | Ví dụ | Hành vi khi overload |
| --- | --- | --- |
| Critical | Xác nhận booking/payment state | Giữ capacity dự phòng, không dùng dữ liệu sai |
| Core | Đọc booking detail | Phục vụ trong budget còn lại |
| Optional | Recommendation, analytics enrichment | Bỏ qua hoặc trả stale/fallback |
| Background | Export lớn, batch recompute | Giãn lịch, giảm concurrency, retry sau |

Không nên luôn ưu tiên request trả tiền cao nhất mà bỏ qua fairness, SLA hoặc yêu cầu công bằng theo tenant. Policy cần minh bạch và được kiểm thử.

### Reject sớm tốt hơn queue vô hạn

Queue dài làm latency tăng và giữ tài nguyên. Nếu deadline request chỉ còn 100 ms nhưng queue wait dự kiến 2 giây, nên từ chối sớm thay vì xếp hàng chắc chắn hết hạn. Với background job, có thể nhận job nếu queue có capacity và job deadline phù hợp; trả operation ID cùng thời gian ước lượng theo contract.

## 14. Queue retry, visibility timeout và dead-letter queue

Message broker có cơ chế retry/redelivery riêng. Cần phân biệt:

- Retry của producer khi publish.
- Redelivery của broker khi consumer không ack.
- Retry do consumer tự gọi dependency.
- Scheduled retry với delay.
- Dead-letter queue (DLQ) sau số lần xử lý lỗi tối đa.

Nếu consumer xử lý chậm hơn visibility timeout/lease, broker có thể giao cùng message cho consumer khác trong khi worker đầu vẫn chạy. Điều này có thể tạo xử lý đồng thời và duplicate side effect.

### Quy tắc consumer

1. Xác thực message và schema.
2. Kiểm tra message/job deadline trước side effect.
3. Dùng idempotency key/event ID để chống duplicate.
4. Cấu hình visibility timeout/lease phù hợp processing time hoặc gia hạn lease theo khả năng broker.
5. Phân loại lỗi retryable và permanent.
6. Backoff với jitter; giới hạn attempt và thời gian sống message.
7. Đưa poison message vào DLQ/quarantine.
8. Cung cấp công cụ replay có kiểm soát và audit.

### Tránh retry chồng lớp

Nếu broker redelivery 5 lần và consumer HTTP client retry 4 lần mỗi lần nhận, một message có thể tạo tới 20 call tới dependency (hoặc nhiều hơn nếu có thêm layer). Nên phân chia rõ:

- Broker quản lý redelivery của message.
- Consumer có thể retry dependency một số lần rất hạn chế trong deadline của attempt.
- Job state lưu attempts, last error và next retry time.
- Tổng retry budget/job age có giới hạn.

### DLQ không phải nơi bỏ quên lỗi

DLQ cần alert theo tuổi và số lượng. Có runbook phân loại poison message, dữ liệu sai schema, dependency outage hoặc permission error. Replay phải idempotent và không bỏ qua deadline nghiệp vụ.

## 15. Hedged request và speculative retry

Hedged request gửi thêm một request song song tới replica khác khi request đầu chậm hơn một ngưỡng, rồi dùng kết quả hợp lệ đầu tiên. Kỹ thuật này có thể giảm tail latency cho các thao tác đọc idempotent khi có replica dư capacity.

Nhưng hedging cũng tăng load:

- Mỗi request chậm có thể tạo thêm request.
- Nếu ngưỡng quá thấp, hệ thống liên tục nhân tải ngay cả khi bình thường.
- Nếu replica cùng chia sẻ bottleneck, hedge không cải thiện gì.
- Với thao tác ghi, hai request song song có thể tạo duplicate side effect.

Chỉ cân nhắc hedging khi:

- Workload đọc, idempotent và có thể hủy request thua.
- Có nhiều replica độc lập và capacity dự phòng rõ.
- Chỉ hedge phần nhỏ request vượt percentile threshold.
- Có hedge budget, deadline và cancellation.
- Đã test tải tăng thêm và consistency của các replica.

Hedging không phải cách chữa dependency đang quá tải; thường cần bulkhead, backpressure hoặc load shedding trước.

## 16. Client disconnect và cancellation propagation

Khi client hủy request hoặc deadline hết, server nên dừng công việc còn có thể dừng:

- Hủy lời gọi HTTP/RPC đang chờ nếu client library hỗ trợ.
- Hủy query/statement đang chạy theo cơ chế database.
- Rút request khỏi queue nếu chưa được xử lý.
- Dừng nhánh parallel không còn cần thiết.
- Giải phóng connection, semaphore permit và temporary resource.

Cancellation thường là cooperative; task phải quan sát tín hiệu. Future.cancel(true) trong Java thường gửi interrupt, không đảm bảo cưỡng bức dừng thread hoặc rollback transaction. Cần đo cancellation lag và xác minh dependency thực sự ngừng xử lý.

Không hủy job nền đã được chấp nhận chỉ vì browser đóng kết nối. Job cần deadline, cancellation policy và lifecycle riêng. Với side effect đã commit, tra cứu/đối soát thay vì giả vờ rollback.

## 17. Observability: phân biệt request gốc và retry

Nếu chỉ đo tổng request rate, đội vận hành khó biết traffic tăng do người dùng hay do retry. Cần phân tách request gốc, retry attempt, queue redelivery và hedged request.

### Metrics nên có

| Metric | Ý nghĩa |
| --- | --- |
| Original requests/sec | Lượng request logic từ caller |
| Attempts per logical request | Số lần gọi vật lý cho mỗi request logic |
| Retry rate | Tỉ lệ attempt là retry |
| Retry budget remaining/exhausted | Mức ngân sách retry còn lại và số lần bị chặn |
| Timeout rate by phase | Timeout ở connect, pool wait, response, query hoặc transaction |
| Deadline exceeded rate | Request hết deadline end-to-end |
| In-flight requests | Request đang giữ tài nguyên |
| Queue depth/age | Backlog và tuổi request/job |
| Pool wait/rejection | Chờ hoặc bị từ chối khi lấy resource |
| Circuit breaker state | Closed/Open/Half-open theo dependency |
| Bulkhead rejected | Request bị từ chối do concurrency limit |
| Cancellation lag | Thời gian từ yêu cầu hủy đến lúc tác vụ dừng |
| Late completion | Kết quả hoàn tất sau deadline/caller disconnect |
| Dependency latency/error | p50/p95/p99 và lỗi theo dependency |

### Phân biệt lỗi của caller và lỗi của dependency

Một request có thể bị hủy vì client disconnect; không nên tính cancellation đó là dependency failure mặc định. Timeout khi chờ connection pool khác timeout khi server dependency xử lý. Phân loại đúng giúp circuit breaker không mở sai và retry budget phản ánh đúng tình trạng.

### Distributed tracing

Mỗi logical request cần trace/correlation ID xuyên qua gateway, service và dependency. Span cho từng attempt nên thể hiện:

- Dependency/endpoint được gọi.
- Attempt number, retry reason và backoff.
- Deadline/remaining budget khi bắt đầu.
- Connect time, pool wait, server processing và response time nếu đo được.
- Cancellation/error category và kết quả cuối.

Không dùng request ID hoặc raw user ID làm metric label vì cardinality rất lớn. Dùng trace/log có kiểm soát truy cập để xem chi tiết; metric nên nhóm theo service, dependency, operation và error category.

### Cảnh báo retry storm

- Retry rate tăng nhanh trong khi original request rate ổn định.
- Attempts per logical request vượt baseline.
- Dependency p99 và error rate cùng tăng.
- Queue depth/age tăng, pool wait và rejection tăng.
- Circuit breaker mở hoặc bulkhead rejection tăng.
- Database/third-party request rate tăng dù traffic đầu vào không tăng tương ứng.

Alert nên dựa trên tác động SLO/error budget và xu hướng, không chỉ một spike ngắn chưa ảnh hưởng người dùng.

## 18. Case study: API đặt chỗ có ba tầng dependency

Một API tạo booking cần phản hồi đồng bộ trong 2 giây. Luồng gồm:

- Gateway: xác thực, routing, 100 ms.
- Booking service: validation và điều phối, 150 ms.
- Inventory: xác nhận slot, tối đa 300 ms.
- Payment provider: có độ trễ biến động, tối đa 700 ms cho lần gọi đồng bộ.
- Database commit và response: 300 ms.
- Headroom: 450 ms.

Tổng budget minh họa:

\[
100+150+300+700+300+450=2.000\text{ ms}.
\]

### Timeout policy

| Thành phần | Timeout minh họa | Lưu ý |
| --- | ---: | --- |
| Gateway | 1.900 ms | Chừa một khoảng nhỏ cho response/edge overhead |
| Booking application deadline | 1.800 ms | Không nhận thêm công việc sau deadline |
| Inventory call | Tối đa 300 ms hoặc remaining budget | Không retry nếu không còn đủ thời gian |
| Payment call | Tối đa 700 ms hoặc remaining budget | Một attempt; kết quả timeout có thể chưa xác định |
| DB pool acquire | 50 ms | Phát hiện pool pressure sớm |
| DB transaction/query | Theo budget còn lại, ví dụ tối đa 250 ms | Rollback nếu chưa commit và transaction còn mở |

Các giá trị phải được điều chỉnh bằng benchmark. Timeout gateway có thể cần lớn hơn backend deadline đủ cho serialization/network, nhưng không nên dài đến mức backend tiếp tục giữ tài nguyên lâu sau khi gateway đã bỏ cuộc.

### Retry policy

- Inventory read/availability check có thể retry tối đa một lần cho một số lỗi connect tạm thời, chỉ khi deadline còn đủ và thao tác không tạo hold.
- Payment charge không retry mù. Gửi idempotency key bền vững; nếu timeout sau khi gửi, đánh dấu operation pending/unknown và query trạng thái theo key.
- Database transaction chỉ retry khi lỗi serialization/deadlock được xác định, transaction có thể thực thi lại an toàn và còn deadline.
- Client retry create booking phải dùng cùng idempotency key.

### Bảo vệ dependency

- Bulkhead riêng cho Inventory và Payment, concurrency tính theo quota provider.
- Circuit breaker theo dependency, phân loại lỗi và slow call.
- Khi Payment breaker mở, API có thể trả trạng thái pending/retry-later theo nghiệp vụ; không xác nhận booking như đã thanh toán.
- Load shedding cho endpoint phụ như recommendation/analytics.
- Retry budget giới hạn tổng retry tới từng dependency.

### Khi Payment chậm hàng loạt

1. Timeout và slow-call metric của Payment tăng.
2. Circuit breaker mở, ngăn request mới dồn vào provider.
3. Booking API không tiếp tục giữ thread chờ dài; operation có thể được chuyển sang pending/reconciliation theo contract.
4. Client nhận operation ID và có thể truy vấn trạng thái.
5. Worker xử lý xác minh với retry schedule có backoff/jitter và job deadline.
6. Dashboard theo dõi pending age, reconciliation queue, duplicate charge và provider health.

### Tiêu chí chấp nhận

- Request đồng bộ dừng trong deadline end-to-end.
- Một ý định booking không tạo giao dịch/payment trùng khi response bị mất.
- Retry rate có cap/budget, không tăng không giới hạn theo số tầng.
- Payment outage không làm cạn worker/connection của Inventory.
- Khi breaker mở, hành vi API phản ánh đúng trạng thái nghiệp vụ.
- Pending operation được đối soát và không bị bỏ quên.

## 19. Case study: queue worker và dịch vụ bên ngoài suy giảm

Một worker tiêu thụ 5.000 message/phút và gọi dịch vụ gửi thông báo. Provider chậm và bắt đầu trả 503. Consumer hiện có 5 lần retry tức thì; broker redelivery sau visibility timeout 30 giây.

### Vấn đề

- Nhiều worker cùng retry ngay, tạo burst tới provider.
- Nếu xử lý vượt 30 giây, broker có thể giao lại message khi worker cũ vẫn chạy.
- Một message có thể gửi notification nhiều lần.
- Queue depth tăng, message age vượt SLA.

### Thiết kế lại

1. Provider call timeout ngắn, ví dụ 2 giây, và có max concurrency theo quota.
2. Một retry nội bộ có exponential backoff+jitter nếu deadline của attempt cho phép.
3. Nếu còn lỗi, lưu nextAttemptAt hoặc nack theo delay policy; không spin-loop.
4. Broker redelivery và application retry có tổng attempt budget chung hoặc phối hợp rõ.
5. Notification dùng message/event ID để dedupe nếu provider hỗ trợ idempotency.
6. Visibility timeout/lease lớn hơn processing budget hợp lý hoặc được gia hạn; consumer heartbeat theo tính năng broker.
7. Quá max attempts hoặc quá job age thì chuyển DLQ, kèm error classification.
8. Alert theo oldest message age và DLQ growth.

### Backpressure

Nếu queue backlog đã cao và provider đang outage, giảm consumer concurrency hoặc tạm ngừng nhận message. Tăng worker chỉ làm tăng call tới provider và có thể tạo nhiều retry hơn. Khi provider phục hồi, ramp-up có kiểm soát thay vì giải phóng toàn bộ backlog đồng thời.

## 20. Xử lý sự cố retry storm: runbook

1. **Xác nhận amplification:** so sánh original request rate với attempt rate theo dependency.
2. **Xác định nguồn retry:** client, gateway, service mesh, SDK, application code hay broker redelivery.
3. **Khoanh vùng dependency:** latency, error rate, pool wait, queue depth, circuit breaker và resource utilization.
4. **Dừng retry không cần thiết:** giảm max attempts, tạm tắt retry ở tầng chồng lặp hoặc hạ retry budget theo change process.
5. **Giới hạn tải:** bulkhead, rate limit, admission control, load shedding hoặc giảm consumer concurrency.
6. **Bảo vệ side effect:** xác nhận idempotency và operation status trước khi replay command ghi.
7. **Phục hồi dần:** mở circuit theo probe, ramp traffic, theo dõi backlog và dependency.
8. **Đối soát:** tìm late completion, unknown payment/booking và duplicate event.
9. **Rút kinh nghiệm:** xác định cấu hình retry nào gây amplification và thêm test/alert.

Không tăng timeout và max attempts hàng loạt trong lúc sự cố nếu chưa hiểu capacity. Các thay đổi đó có thể giữ tài nguyên lâu hơn và nhân tải thêm.

## 21. Kiểm thử timeout và retry dưới lỗi

| Bài thử | Mô phỏng | Kỳ vọng |
| --- | --- | --- |
| Connect timeout | DNS/TCP/TLS không kết nối | Dừng trong connect budget, không giữ pool vô hạn |
| Slow dependency | Phản hồi chậm hơn call timeout | Timeout/cancellation đúng, request tổng không vượt deadline |
| Multi-layer retry | Bật retry ở nhiều tầng trong test | Đo được amplification và xác nhận tổng attempt cap |
| Synchronized failures | Nhiều instance lỗi cùng lúc | Jitter phân tán retry, không tạo burst lớn |
| Retry budget exhaustion | Giả lập dependency fail kéo dài | Retry bị chặn khi budget cạn |
| Non-retryable error | 400/401/403/validation | Không retry vô ích |
| Timeout after commit | Server commit rồi response bị drop | Cùng idempotency key trả cùng logical result |
| Circuit breaker | Tăng lỗi/slow calls | Open, half-open và recovery theo policy |
| Bulkhead saturation | Một dependency treo | Pool khác vẫn phục vụ, excess bị reject có kiểm soát |
| Queue redelivery | Consumer quá visibility timeout | Dedupe ngăn side effect lặp |
| Client cancellation | Hủy request giữa chừng | Tác vụ con dừng nếu có thể; resource được giải phóng |
| Shutdown | Pod nhận SIGTERM khi có request | Ngừng nhận mới, drain/cancel theo grace period |

### Fault injection

Có thể mô phỏng packet loss, latency injection, DNS failure, 429/503, DB lock, pool exhaustion, broker backlog hoặc provider outage. Bắt đầu ở môi trường kiểm thử và có ngưỡng dừng. Sau thử nghiệm phải kiểm tra:

- End-to-end latency/deadline.
- Original request rate và retry attempts.
- Resource in-flight, queue và pool.
- Duplicate/late side effect.
- Circuit breaker/bulkhead/load shedding.
- Recovery time và backlog drain rate.

### Kiểm thử deadline bằng clock giả lập

Unit test nên dùng clock abstraction để kiểm tra deadline hết, retry không còn budget, backoff vượt deadline và cancellation race mà không phải chờ thời gian thực. Integration test vẫn cần xác minh HTTP client, RPC, database driver và broker có semantics timeout/cancel như dự kiến.

## 22. Những sai lầm thường gặp

1. **Mỗi tầng tự đặt timeout mà không có deadline chung:** request bị kéo dài qua nhiều hop.
2. **Timeout gateway ngắn hơn backend nhưng backend không nhận cancellation:** server tiếp tục làm việc sau khi caller đã bỏ cuộc.
3. **Retry ở mọi tầng:** số attempt nhân lên theo tích số lần thử.
4. **Retry tức thì hoặc backoff cố định:** nhiều instance tạo burst đồng thời.
5. **Exponential backoff không có cap:** request/job chờ quá lâu hoặc vượt thời hạn nghiệp vụ.
6. **Max attempts không gắn deadline:** bắt đầu lần thử chắc chắn không thể hoàn thành.
7. **Retry cả lỗi vĩnh viễn:** tốn tài nguyên và tạo noise.
8. **Retry thao tác ghi không idempotent:** tạo booking, payment hoặc notification trùng.
9. **Timeout sau commit bị coi là thất bại:** client gửi lại command mới dù giao dịch đã thành công.
10. **Không có retry budget:** tổng retry tăng theo traffic và có thể áp đảo request gốc.
11. **Circuit breaker dùng chung cho nhiều dependency:** một dependency lỗi làm chặn cả service.
12. **Circuit breaker thay cho timeout:** request đang bay vẫn giữ tài nguyên.
13. **Bulkhead chỉ giới hạn per instance:** tổng concurrency toàn cluster vẫn vượt quota downstream.
14. **Queue visibility timeout quá ngắn:** broker redelivery trong khi worker cũ còn chạy.
15. **Tăng worker khi dependency outage:** tạo thêm tải và retry tới dependency đang yếu.
16. **Không phân biệt cancellation với dependency failure:** breaker mở sai hoặc retry request đã bị hủy.
17. **Hedged request không có budget:** giảm tail latency một số request nhưng làm quá tải toàn hệ thống.
18. **Không đo original request và retry riêng:** không nhận diện được amplification sớm.
19. **Không có runbook phục hồi:** khi dependency khỏe lại, backlog và retry tiếp tục tạo đợt quá tải mới.

## 23. Bài tập thực hành và đáp án định hướng

Một API báo cáo có deadline 1.500 ms. Gateway tiêu thụ 100 ms, application logic cần 150 ms, Search API cần 400 ms, Billing API cần 500 ms, serialize/response cần 100 ms. Search và Billing được gọi song song. Mỗi dependency client đang cấu hình 3 attempts (tính cả lần đầu), backoff cố định 200 ms. Gateway cũng retry hai lần khi nhận 502/504.

### Câu 1 — Thời gian đường đi bình thường có fit deadline không?

**Đáp án:** Nhánh chậm nhất là 500 ms. Tổng ước lượng 100 + 150 + 500 + 100 = 850 ms, còn khoảng 650 ms headroom. Cần kiểm tra pool wait, connect, network và tail latency thực tế.

### Câu 2 — Ba attempts ở mỗi dependency có luôn phù hợp không?

**Đáp án:** Không. Cần kiểm tra retryable error, remaining deadline và retry budget. Nếu một lần gọi dùng 500 ms, ba attempts cộng backoff có thể vượt ngân sách. Với hai dependency song song, retry nhánh lỗi có thể kéo dài toàn request; không retry nếu không còn đủ thời gian.

### Câu 3 — Gateway retry hai lần và mỗi client dependency có ba attempts, số lần gọi tối đa ở một dependency có thể là bao nhiêu?

**Đáp án:** Nếu gateway tạo tối đa ba lần gửi tới application (lần đầu + hai retry), và mỗi lần application lại thực hiện tối đa ba attempts cho dependency, có thể tạo tới 9 call cho một dependency cho mỗi request logic trong trường hợp xấu nhất. Đây là lý do phải tránh retry chồng lớp hoặc tính tổng amplification.

### Câu 4 — Nên đặt retry ở đâu?

**Đáp án định hướng:** Chọn một tầng sở hữu retry có ngữ cảnh về deadline/idempotency; gateway không nên retry mù khi application đã có retry. Có thể giữ một retry connect-level rất hạn chế nếu thư viện cần, nhưng phải tính vào tổng attempts và telemetry.

### Câu 5 — Khi Billing trả timeout sau khi đã ghi nhận hóa đơn, client nên làm gì?

**Đáp án:** Dùng cùng idempotency key để truy vấn/kết thúc cùng operation. Không tạo command mới với key khác. Nếu trạng thái chưa rõ, trả pending/unknown và đối soát.

### Câu 6 — Billing lỗi kéo dài, biện pháp nào giúp Search vẫn hoạt động?

**Đáp án:** Bulkhead/connection pool/concurrency riêng; circuit breaker riêng cho Billing; load shedding hoặc bỏ enrichment Billing nếu nghiệp vụ cho phép. Không dùng một breaker chung cho cả hai dependency.

### Câu 7 — Retry rate tăng gấp 5 lần nhưng original request rate không đổi. Cần xem gì?

**Đáp án:** Attempt rate theo dependency, retry reason, tầng phát retry, latency/error của dependency, queue, pool wait, backoff distribution và budget exhaustion. Dừng retry chồng lớp và giới hạn tải trước khi tăng capacity.

### Câu 8 — Consumer xử lý message lâu hơn visibility timeout. Rủi ro và cách khắc phục?

**Đáp án:** Broker có thể redeliver khi worker cũ chưa dừng, gây xử lý đồng thời/duplicate. Điều chỉnh visibility/lease hoặc heartbeat, dùng idempotency, lưu job state và kiểm soát attempt/deadline.

## 24. Checklist review timeout và retry

- Mỗi hành trình có deadline end-to-end gắn với SLO chưa?
- Client, gateway, service, pool, database và queue timeout có được phân cấp rõ?
- Các tầng có dùng remaining budget thay vì cấp lại timeout đầy đủ không?
- Maximum request/job duration có được enforce server-side không?
- Retry chỉ áp dụng cho lỗi được phân loại retryable?
- Có một tầng retry owner rõ ràng; tổng attempts qua mọi layer đã tính chưa?
- Exponential backoff có jitter và cap phù hợp?
- Retry budget có giới hạn theo service/dependency và có hành vi khi hết budget?
- Retry có dừng khi không đủ deadline không?
- Side effect có idempotency key/dedupe và operation status?
- Timeout sau commit có trạng thái unknown/pending và reconciliation?
- Circuit breaker có threshold, window, half-open probe và exception classifier?
- Bulkhead/concurrency được sizing theo tổng số instance và downstream quota?
- Queue lease/visibility timeout, retry schedule, DLQ và replay có phối hợp?
- Load shedding/admission control có bảo vệ critical path và fairness tenant?
- Client cancellation có lan xuống dependency và giải phóng tài nguyên?
- Metrics phân biệt original request, retry, hedge và broker redelivery?
- Có tracing attempt, backoff, deadline còn lại và dependency phase?
- Có test slow dependency, partition, timeout-after-commit và retry storm dưới tải?
- Có runbook để dừng retry, giảm tải và phục hồi backlog?

## 25. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Dependency suy giảm có gây retry storm hoặc domino failure không? | Deadline, retry budget, breaker, bulkhead, fault injection |
| **Bảo mật** | Retry/replay có thể lặp side effect, vượt tenant scope hoặc làm lộ token không? | Idempotency, authorization, secret redaction, audit |
| **Hiệu năng** | Tail latency và concurrency được kiểm soát ra sao? | p95/p99, pool wait, queue age, deadline budget |
| **Tối ưu chi phí** | Retry, hedging và work sau deadline tiêu tốn bao nhiêu tài nguyên? | Attempts/request, late work, cost per operation |
| **Vận hành xuất sắc** | Đội trực có thấy nguồn retry, dependency lỗi và trạng thái breaker không? | Dashboard, trace, alert, runbook, ownership |
| **Tính bền vững** | Hệ thống có tránh lặp công việc vô ích và sử dụng capacity hiệu quả không? | Cancellation, admission control, bounded queue, right-sizing |

Một kiến trúc timeout/retry tốt bảo đảm request kết thúc trong ngân sách, dependency được bảo vệ khi suy giảm và thao tác nghiệp vụ không bị nhân đôi. **Timeout giới hạn thời gian, deadline thống nhất toàn hành trình, retry budget giới hạn tải thêm, còn circuit breaker/bulkhead/load shedding ngăn sự cố lan rộng.** Các cơ chế cần được quan sát và kiểm thử cùng nhau; chỉ cấu hình số lần retry hoặc timeout riêng lẻ không đủ để chứng minh độ tin cậy.
