# Retry budget, circuit breaker và bulkhead

Trong hệ thống phân tán, một lời gọi API có thể đi qua load balancer, service mesh, ứng dụng, database, queue và một dịch vụ bên ngoài. Chỉ một dependency chậm cũng có thể làm request giữ connection, thread và bộ nhớ lâu hơn bình thường. Nếu mọi tầng cùng retry, số request có thể tăng theo cấp số nhân; nếu một dịch vụ dùng chung bị nghẽn, nhiều chức năng không liên quan cũng có thể ngừng hoạt động.

Ba cơ chế thường được kết hợp để hạn chế sự cố lan truyền:

- **Retry budget** giới hạn lượng công việc được phép thử lại, tránh để retry tạo thêm tải khi hệ thống đang suy giảm.
- **Circuit breaker** ngừng gọi một dependency đang lỗi trong một khoảng thời gian, cho hệ thống thời gian phục hồi và cho request thất bại nhanh hoặc dùng phương án dự phòng.
- **Bulkhead** chia tài nguyên thành các vùng độc lập để lỗi hoặc quá tải ở một nhóm request không chiếm hết capacity của nhóm khác.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, các cơ chế này có thể áp dụng cho ứng dụng chạy trên EC2, ECS, EKS và Lambda; cho lời gọi tới RDS, DynamoDB, S3, API Gateway hoặc dịch vụ bên ngoài; và cho xử lý bất đồng bộ qua SQS, EventBridge hay Step Functions. Mục tiêu của module là giúp người học thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí. Vì vậy, cần thiết kế retry, timeout, circuit breaker và bulkhead như một chính sách nhất quán xuyên suốt các tầng, thay vì bật retry riêng lẻ ở từng thư viện.

## 1. Vì sao cần giới hạn lỗi lan truyền?

Giả sử một API Orders nhận 500 request mỗi giây. Mỗi request cần gọi Inventory và Payment. Database Inventory bắt đầu phản hồi chậm. Request của Orders phải chờ lâu hơn, thread và connection pool bị giữ lại, số request đang xử lý tăng. Khi timeout xảy ra, ứng dụng retry ngay lập tức. Các retry tiếp tục tới Inventory, làm tải tăng đúng lúc dependency đang yếu nhất.

Nếu API Gateway, service Orders, SDK và service Inventory đều có retry, số request ban đầu có thể nhân lên qua từng tầng. Ví dụ ba tầng, mỗi tầng cho phép ba lần thử tổng cộng, có thể tạo ra tới 27 lần gọi ở tầng sâu nhất trong trường hợp xấu. Đây là lý do retry phải được giới hạn và phối hợp theo toàn bộ đường đi của request.

Ba mẫu thiết kế giải quyết ba vấn đề khác nhau:

| Cơ chế | Câu hỏi nó trả lời | Mục tiêu |
|---|---|---|
| Retry budget | Hệ thống được phép tạo thêm bao nhiêu lần thử? | Giới hạn tải phát sinh do retry |
| Circuit breaker | Khi dependency đang lỗi, có nên tiếp tục gọi không? | Ngăn request tiếp tục dồn vào dependency suy giảm |
| Bulkhead | Một nhóm request có được phép chiếm hết tài nguyên chung không? | Cô lập lỗi và giữ capacity cho phần còn lại |

Các cơ chế này không thay thế timeout, idempotency, rate limiting, load shedding hoặc autoscaling. Chúng cần phối hợp với các biện pháp đó để bảo vệ cả caller và dependency.

## 2. Bắt đầu từ timeout và deadline

Retry chỉ có ý nghĩa khi mỗi lần gọi có giới hạn thời gian. Nếu không đặt timeout, request có thể chờ vô thời hạn, giữ connection và thread, làm cạn tài nguyên ngay cả khi không có retry.

Hai khái niệm cần phân biệt:

- **Timeout:** giới hạn thời gian cho một thao tác cụ thể, chẳng hạn kết nối TCP hoặc một HTTP request.
- **Deadline:** thời điểm cuối cùng mà toàn bộ công việc phải hoàn thành, bao gồm các lần thử, backoff và xử lý kết quả.

Ví dụ, một API có deadline 2 giây. Nó gọi một dependency với timeout 400 ms và cho phép tối đa hai lần retry. Nếu hai khoảng backoff tối đa lần lượt là 100 ms và 200 ms, tổng ngân sách lý thuyết là:

\[
3 \times 400\text{ ms} + 100\text{ ms} + 200\text{ ms} = 1.5\text{ s}
\]

Phần còn lại dành cho serialization, network overhead, kiểm tra breaker và trả response. Nếu timeout của mỗi lần gọi là 1 giây, ba lần thử đã vượt deadline trước cả khi tính backoff. Khi đó retry policy không thể đáp ứng mục tiêu latency.

### Thiết kế timeout theo tầng

Một nguyên tắc hữu ích là timeout của dependency phải ngắn hơn deadline còn lại của caller. Ví dụ:

| Tầng | Giới hạn ví dụ |
|---|---:|
| Deadline API từ client | 2.000 ms |
| Xử lý tổng thể của Orders | 1.800 ms |
| Một lần gọi Inventory | 400 ms |
| Kết nối TCP/TLS | 100 ms |
| Tổng thời gian backoff | Tối đa 300 ms |

Các con số chỉ là ví dụ thiết kế. Cần đo latency p95/p99, thời gian kết nối và yêu cầu nghiệp vụ để chọn giá trị phù hợp. Không nên đặt timeout chỉ dựa trên latency trung bình.

Khi deadline đã gần hết, client không nên bắt đầu một lần retry mới nếu không còn đủ thời gian hoàn thành. Truyền deadline hoặc remaining time xuyên các service giúp tầng dưới biết request còn bao nhiêu ngân sách.

## 3. Retry: thử lại khi nào?

Retry là việc gửi lại một thao tác sau khi lần thực hiện trước thất bại. Retry có ích với lỗi tạm thời như:

- Kết nối bị reset hoặc lỗi mạng ngắn hạn.
- Timeout do một đợt tải đột biến.
- HTTP 5xx từ dependency.
- Throttling hoặc giới hạn tốc độ, nếu phản hồi cho phép thử lại sau một khoảng thời gian.
- Một số lỗi dịch vụ tạm thời được AWS SDK nhận diện.

Không nên retry mọi lỗi. Những lỗi sau thường cần xử lý trực tiếp:

- Dữ liệu đầu vào không hợp lệ.
- Không có quyền truy cập hoặc credential sai.
- Tài nguyên không tồn tại và không có khả năng xuất hiện do eventual consistency.
- Vi phạm quy tắc nghiệp vụ.
- Request vượt giới hạn cố định mà không có cơ chế chờ hoặc điều chỉnh.

Retry một lỗi không thể tự hết sẽ chỉ tiêu tốn thời gian và capacity. Cần phân loại lỗi theo mã HTTP, exception, error code và ngữ cảnh của dịch vụ, không chỉ dựa vào việc “có exception”.

### Retry chỉ an toàn khi thao tác có tính idempotent

Một thao tác idempotent có thể được thực hiện nhiều lần mà kết quả cuối không thay đổi ngoài kết quả của lần đầu. GET thường có tính chất này; PUT có thể idempotent nếu được thiết kế đúng; POST tạo đơn hàng hoặc trừ tiền thường không tự động idempotent.

Tình huống nguy hiểm: server đã tạo đơn hàng và commit database, nhưng response bị mất trên đường về. Client thấy timeout và gửi lại POST. Nếu server không nhận diện request trùng, đơn hàng có thể được tạo hai lần.

Cách bảo vệ:

1. Client tạo một idempotency key duy nhất cho ý định nghiệp vụ.
2. Server lưu key cùng kết quả hoặc trạng thái xử lý trong một kho dữ liệu có tính nhất quán phù hợp.
3. Request lặp lại với cùng key trả về kết quả đã ghi nhận hoặc trạng thái đang xử lý.
4. Cùng key nhưng payload khác phải bị từ chối hoặc đưa vào điều tra.
5. Có thời hạn lưu key đủ dài so với thời gian retry, queue redelivery và cửa sổ đối soát.

Với SQS, message có thể được giao lại. Consumer cần idempotent hoặc có cơ chế deduplication/conditional write để không thực hiện giao dịch hai lần.

## 4. Exponential backoff và jitter

Nếu nhiều client cùng retry ngay sau một lỗi, chúng tạo ra một đợt tải đồng bộ gọi là retry storm hoặc thundering herd. Exponential backoff tăng dần khoảng chờ giữa các lần thử; jitter thêm độ ngẫu nhiên để client không cùng thức dậy ở một thời điểm.

Một công thức full jitter phổ biến:

\[
d_n = U\left(0,\ \min(d_{\max}, d_0 \times 2^n)\right)
\]

Trong đó:

- \(d_n\) là thời gian chờ trước lần thử tiếp theo.
- \(d_0\) là khoảng chờ ban đầu.
- \(d_{\max}\) là giới hạn backoff.
- \(n\) là số thứ tự lần retry.
- \(U(0,x)\) là giá trị ngẫu nhiên phân bố đều từ 0 tới \(x\).

Ví dụ với \(d_0=100\) ms và \(d_{\max}=2\) giây:

| Lần retry | Khoảng backoff tối đa trước jitter | Thời gian thực tế |
|---|---:|---|
| 1 | 100 ms | Ngẫu nhiên 0–100 ms |
| 2 | 200 ms | Ngẫu nhiên 0–200 ms |
| 3 | 400 ms | Ngẫu nhiên 0–400 ms |
| 4 | 800 ms | Ngẫu nhiên 0–800 ms |
| 5 | 1.600 ms | Ngẫu nhiên 0–1.600 ms |

Sau đó giá trị tối đa không vượt \(d_{\max}\). Cần kết hợp backoff với deadline và retry budget; tăng thời gian chờ vô hạn không phải là chiến lược phục hồi.

### Respect Retry-After

Một số API trả header Retry-After hoặc thông tin tương đương khi throttling. Nếu hợp đồng API yêu cầu client tôn trọng thời gian này, hãy chờ theo chỉ dẫn nhưng vẫn kiểm tra deadline và giới hạn tối đa của ứng dụng. Không retry sớm hơn chỉ vì backoff nội bộ ngắn hơn.

## 5. Retry budget là gì?

Retry budget giới hạn tổng lượng retry được phép phát sinh trong một phạm vi và một khoảng thời gian. Thay vì chỉ đặt “mỗi request tối đa ba lần thử”, budget còn kiểm soát tổng số lần thử lại của toàn service hoặc dependency.

Có thể định nghĩa budget theo:

- Tỷ lệ retry trên số request gốc.
- Số retry tối đa trong một phút.
- Token bucket được bổ sung theo tốc độ request thành công hoặc theo cấu hình.
- Budget riêng cho từng dependency, tenant hoặc nhóm endpoint.

Ví dụ, một service có 1.000 request gốc mỗi phút và chính sách retry budget 5% có thể cho phép tối đa khoảng 50 retry attempt trong cửa sổ đó. Nếu số retry vượt budget, client ngừng thử lại, trả lỗi nhanh hoặc chuyển sang fallback đã được thiết kế.

Con số 5% chỉ là ví dụ nội bộ, không phải mặc định AWS. Tổ chức cần đặt budget từ tải nền, khả năng dependency, SLO và mức độ lỗi có thể chấp nhận.

### Retry budget khác max attempts

| Giới hạn | Phạm vi |
|---|---|
| Max attempts | Số lần một request có thể được thực hiện, tính cả lần đầu hoặc theo quy ước thư viện |
| Retry budget | Tổng retry attempt được phép trong một cửa sổ hoặc phạm vi |
| Deadline | Tổng thời gian request được phép tiêu tốn |
| Rate limit | Tổng request mới được phép đi vào hệ thống |

Một request có thể còn retry attempt theo max attempts nhưng không còn retry budget của service. Ngược lại, service có budget nhưng request đã hết deadline thì cũng không được retry.

### Token bucket cho retry budget

Một cách triển khai là dùng token bucket:

1. Bucket bắt đầu với một số token giới hạn.
2. Mỗi retry tiêu thụ một token.
3. Token được bổ sung theo tốc độ đã cấu hình hoặc theo tỷ lệ request thành công.
4. Khi bucket hết token, request không được retry.

Token bucket cho phép một lượng burst nhỏ nhưng giới hạn tổng tải kéo dài. Có thể triển khai ở client process, thư viện nội bộ hoặc tầng điều phối. Nếu budget cần dùng chung toàn fleet, phải cân nhắc chi phí và độ trễ của bộ đếm phân tán; một bộ đếm cục bộ trên mỗi instance có thể khiến tổng budget toàn hệ thống lớn hơn dự kiến.

## 6. Circuit breaker là gì?

Circuit breaker theo dõi kết quả gọi dependency và tạm ngừng gửi request khi tỷ lệ hoặc số lượng lỗi vượt ngưỡng. Mục tiêu là ngăn caller tiếp tục tiêu thụ tài nguyên chờ một dependency đang không khỏe.

Circuit breaker thường có ba trạng thái:

| Trạng thái | Hành vi |
|---|---|
| **Closed** | Request được phép đi qua; breaker ghi nhận thành công/thất bại |
| **Open** | Request bị từ chối nhanh hoặc chuyển fallback; không gọi dependency |
| **Half-open** | Cho phép một số probe giới hạn để kiểm tra dependency đã phục hồi chưa |

Luồng trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Closed
    Closed --> Open: Lỗi vượt ngưỡng
    Open --> HalfOpen: Hết thời gian chờ
    HalfOpen --> Closed: Probe thành công
    HalfOpen --> Open: Probe thất bại
~~~

### Closed

Ở trạng thái Closed, breaker cho phép request tới dependency. Nó theo dõi lỗi theo số lần liên tiếp, tỷ lệ lỗi trong cửa sổ thời gian hoặc kết hợp nhiều điều kiện. Chỉ tính những lỗi phản ánh sức khỏe dependency, ví dụ timeout, connection failure hoặc 5xx.

Không nên tính mọi lỗi nghiệp vụ là lỗi breaker. HTTP 400 do dữ liệu đầu vào sai hoặc 403 do caller thiếu quyền thường không chứng minh dependency đang quá tải.

### Open

Khi vượt ngưỡng, breaker chuyển sang Open trong một khoảng thời gian. Request mới bị fail fast để giải phóng thread và connection. Ứng dụng có thể trả lỗi có kiểm soát, dùng cache cũ còn an toàn hoặc đưa công việc vào queue nếu nghiệp vụ cho phép.

Không nên dùng fallback giả thành công nếu điều đó làm sai dữ liệu nghiệp vụ. Ví dụ, không thể trả “đã thanh toán” khi Payment service đang lỗi mà chưa xác nhận giao dịch.

### Half-open

Sau thời gian chờ, breaker cho phép một số request thử nghiệm. Nếu probe thành công đủ điều kiện, breaker trở lại Closed. Nếu probe tiếp tục thất bại, breaker trở lại Open.

Giới hạn số probe để tránh hàng nghìn client cùng kiểm tra dependency tại một thời điểm. Có thể dùng jitter cho thời điểm thử lại breaker hoặc phối hợp qua rate limit.

## 7. Cấu hình circuit breaker hợp lý

Một breaker cần các tham số:

- Cửa sổ quan sát: theo số request gần nhất hoặc khoảng thời gian.
- Ngưỡng tối thiểu: chỉ đánh giá tỷ lệ lỗi khi có đủ mẫu.
- Ngưỡng mở: tỷ lệ lỗi, số lỗi liên tiếp hoặc số timeout.
- Open duration: thời gian giữ trạng thái Open.
- Half-open permits: số probe đồng thời được phép.
- Success threshold: số hoặc tỷ lệ probe thành công để đóng lại.
- Exception/response classification: loại lỗi nào được tính.

Ví dụ minh họa: trong cửa sổ 30 giây, nếu có ít nhất 20 request và hơn 50% request kết thúc bằng timeout hoặc 5xx, mở breaker trong 10 giây. Sau đó chỉ cho phép hai probe đồng thời. Nếu cả hai thành công, đóng breaker; nếu có probe thất bại, mở lại.

Đây là chính sách minh họa, không phải giá trị khuyến nghị cho mọi ứng dụng. Cần cân nhắc traffic thấp, thời gian phục hồi dependency, SLO và khả năng xử lý fallback.

### Breaker theo dependency

Không dùng một breaker toàn cục cho mọi downstream. Inventory, Payment và Notification có đặc tính latency, mức độ quan trọng và fallback khác nhau. Tách breaker theo dependency hoặc endpoint quan trọng giúp lỗi Payment không ngăn ứng dụng gọi Inventory.

Với multi-tenant service, có thể cần phân tách theo tenant hoặc pool nếu một tenant gây quá tải. Tuy nhiên, tạo breaker cho từng tenant với cardinality quá lớn có thể tiêu tốn bộ nhớ và gây khó giám sát; chọn ranh giới theo rủi ro thực tế.

## 8. Bulkhead là gì?

Bulkhead lấy ý tưởng từ các vách ngăn trên tàu: nếu một khoang bị ngập, các khoang khác vẫn có thể nổi. Trong phần mềm, bulkhead chia tài nguyên hoặc luồng công việc thành các vùng độc lập để một dependency hoặc nhóm request không chiếm hết capacity chung.

Các tài nguyên có thể được cô lập:

- Thread pool hoặc executor.
- Semaphore và giới hạn concurrency.
- Connection pool tới từng database/service.
- Queue và consumer group.
- Process/container/task hoặc nhóm instance.
- Capacity theo tenant, API hoặc loại công việc.

Ví dụ, service Orders gọi Payment và Recommendation. Nếu hai dependency dùng chung một thread pool, Recommendation chậm có thể chiếm hết thread và làm request thanh toán không xử lý được. Tách pool và giới hạn concurrency cho mỗi dependency giúp bảo vệ luồng thanh toán.

### Bulkhead bằng thread pool và semaphore

Thread-pool bulkhead cấp một pool riêng cho từng dependency. Khi pool đầy, request mới bị từ chối hoặc đưa vào queue có giới hạn. Semaphore bulkhead giới hạn số thao tác đồng thời nhưng có thể dùng chung executor.

| Cách làm | Ưu điểm | Rủi ro/cần chú ý |
|---|---|---|
| Thread pool riêng | Cô lập thread và queue theo dependency | Tốn thread, cần tránh queue không giới hạn |
| Semaphore | Nhẹ, giới hạn concurrency rõ | Không tự cô lập thread nếu tác vụ blocking |
| Connection pool riêng | Giới hạn kết nối và tránh một DB chiếm hết pool | Cần sizing và timeout phù hợp |
| Queue riêng | Tách tải và retry theo loại công việc | Cần xử lý backlog, ordering và DLQ |
| Compute/service riêng | Cô lập CPU/memory và scaling | Tăng chi phí và vận hành |

Queue hoặc pool không giới hạn không phải bulkhead an toàn. Nếu request tiếp tục xếp hàng trong khi dependency không phục hồi, latency và memory sẽ tăng cho tới khi hệ thống cạn tài nguyên. Luôn đặt capacity, queue length, timeout và hành vi khi đầy.

## 9. Kết hợp retry budget, circuit breaker và bulkhead

Ba cơ chế cần hoạt động theo một thứ tự rõ ràng:

1. Kiểm tra deadline và quyền sử dụng capacity.
2. Kiểm tra circuit breaker; nếu Open thì fail fast hoặc fallback.
3. Lấy slot từ bulkhead; nếu hết slot thì từ chối nhanh hoặc queue trong giới hạn.
4. Thực hiện request với timeout.
5. Nếu lỗi thuộc nhóm retryable, kiểm tra deadline, max attempts và retry budget.
6. Chờ backoff có jitter rồi thử lại nếu breaker/bulkhead vẫn cho phép.
7. Ghi metric và trả kết quả cuối cùng.

~~~mermaid
flowchart TD
    A[Request đến] --> B{Còn deadline?}
    B -->|Không| X[Timeout / fail fast]
    B -->|Có| C{Circuit breaker cho phép?}
    C -->|Open| F[Fallback hoặc lỗi có kiểm soát]
    C -->|Có| D{Còn bulkhead capacity?}
    D -->|Không| F
    D -->|Có| E[Gọi dependency với timeout]
    E --> G{Thành công?}
    G -->|Có| H[Trả kết quả]
    G -->|Không| I{Lỗi retryable?}
    I -->|Không| X
    I -->|Có| J{Còn retry budget và deadline?}
    J -->|Không| X
    J -->|Có| K[Backoff + jitter]
    K --> C
~~~

Thứ tự chi tiết có thể khác tùy thư viện. Điều quan trọng là retry không được bỏ qua breaker, bulkhead hoặc deadline. Mỗi lần retry phải đi qua cùng chính sách bảo vệ như lần đầu.

## 10. Áp dụng với AWS SDK

AWS SDK có retry strategy cho một số lỗi tạm thời và throttling. Nên hiểu rõ chế độ retry, số lần thử, backoff và giới hạn retry của SDK thay vì bọc thêm một vòng retry không giới hạn bên ngoài.

Các chế độ thường gặp:

- **Standard retry mode:** áp dụng backoff và retry quota để giới hạn retry. Retry quota là cơ chế token/quota nội bộ của SDK, giúp ngừng retry khi chi phí retry vượt giới hạn; nó không phải retry budget toàn service do doanh nghiệp định nghĩa.
- **Adaptive retry mode:** ngoài retry behavior còn điều chỉnh tốc độ request dựa trên phản hồi throttling. Chế độ này phù hợp với một số workload tương tác với một resource hoặc endpoint cụ thể; nếu dùng chung client cho nhiều resource không liên quan, việc điều tiết có thể ảnh hưởng lẫn nhau.
- **Legacy retry mode:** hành vi cũ, có thể tồn tại để tương thích; nên xem xét dùng standard cho ứng dụng mới theo hướng dẫn SDK hiện hành.

Không nên cộng nhiều lớp retry mà không tính tổng số lần gọi. Ví dụ SDK tự retry ba lần, service wrapper retry thêm ba lần, rồi API Gateway/client retry tiếp; tổng tải có thể lớn hơn dự kiến.

### Quy tắc thực tế

1. Chọn một lớp chịu trách nhiệm chính về retry cho từng dependency.
2. Đặt max attempts và timeout trong SDK phù hợp deadline.
3. Đọc mã lỗi và throttling behavior của dịch vụ.
4. Không retry lỗi xác thực, phân quyền hoặc validation.
5. Đối với thao tác ghi, dùng idempotency hoặc conditional operation.
6. Theo dõi SDK retry count, throttling và latency để điều chỉnh.

AWS SDK retry quota chỉ giới hạn retry ở client instance. Nó không thay thế circuit breaker hoặc bulkhead, và không ngăn một số lượng lớn client khác nhau cùng tạo tải tới dependency.

## 11. SQS và xử lý bất đồng bộ

SQS giúp tách producer khỏi consumer, hấp thụ burst và cho phép worker xử lý theo tốc độ phù hợp. Đây là một dạng bulkhead ở cấp kiến trúc khi các workload dùng queue và consumer riêng.

Các cơ chế cần phối hợp:

- **Visibility timeout:** khoảng thời gian message bị ẩn sau khi consumer nhận. Nếu xử lý chưa xong và message không được xóa, nó có thể được giao lại.
- **Redrive policy:** chuyển message sang dead-letter queue sau số lần receive tối đa.
- **MaxReceiveCount:** giới hạn số lần message được nhận trước khi chuyển DLQ.
- **Batch size/concurrency:** giới hạn tốc độ và số message xử lý đồng thời.
- **Idempotent consumer:** bảo đảm message lặp không gây giao dịch lặp.

Không tăng MaxReceiveCount quá cao chỉ để tránh DLQ. Poison message có thể được xử lý đi xử lý lại, chiếm worker và làm chậm message tốt. DLQ cần có alarm, owner và quy trình replay sau khi sửa nguyên nhân.

### Visibility timeout và retry

Visibility timeout nên đủ dài cho thời gian xử lý dự kiến, có xét tới heartbeat/visibility extension nếu tác vụ dài. Nếu timeout quá ngắn, message có thể được giao cho consumer khác trong khi consumer đầu vẫn đang xử lý, gây xử lý trùng. Nếu quá dài, message lỗi phải chờ lâu mới được retry.

Với Lambda event source mapping cho SQS, cân nhắc partial batch response để chỉ retry các message thất bại thay vì toàn bộ batch. Dù dùng cơ chế nào, consumer vẫn cần idempotency vì SQS standard queue có semantics at-least-once.

## 12. Retry trong AWS Step Functions và EventBridge

Step Functions cho phép khai báo retry và catch trong state machine. Đây là cách quản lý retry rõ ràng cho workflow nhiều bước thay vì viết vòng lặp không kiểm soát trong Lambda.

Ví dụ state task có backoff, giới hạn số lần thử và jitter:

~~~json
{
  "CallInventory": {
    "Type": "Task",
    "Resource": "arn:aws:states:::lambda:invoke",
    "Parameters": {
      "FunctionName": "CheckInventory",
      "Payload.$": "$"
    },
    "Retry": [
      {
        "ErrorEquals": ["TransientDependencyError", "States.Timeout"],
        "IntervalSeconds": 2,
        "BackoffRate": 2.0,
        "MaxAttempts": 3,
        "MaxDelaySeconds": 20,
        "JitterStrategy": "FULL"
      }
    ],
    "Catch": [
      {
        "ErrorEquals": ["States.ALL"],
        "Next": "HandleFailure"
      }
    ],
    "End": true
  }
}
~~~

Đây là đoạn minh họa cấu trúc Amazon States Language. Cần kiểm tra error name mà Lambda thực tế trả về và chọn retryable error chính xác. Không retry States.ALL một cách mặc định vì lỗi dữ liệu hoặc quyền có thể không tự hết.

EventBridge có retry policy và dead-letter queue cho target delivery. Đây là retry của quá trình giao event tới target, khác với retry bên trong Lambda hoặc service xử lý event. Khi thiết kế, tính tổng các lớp retry và deduplication để một event không gây nhiều side effect.

## 13. Bulkhead với các dịch vụ compute AWS

### Lambda

Reserved concurrency giới hạn concurrency tối đa của một function và dành riêng capacity cho function đó trong account/Region. Nó có thể giúp cô lập function quan trọng khỏi các function khác và bảo vệ downstream khỏi lượng request quá lớn.

Reserved concurrency không tự động chia thread pool hoặc connection pool bên trong function. Cần kết hợp timeout, giới hạn concurrency, SQS event source scaling, idempotency và circuit breaker trong code. Provisioned concurrency chủ yếu giữ execution environment sẵn sàng để giảm cold start; không phải cơ chế bulkhead thay thế reserved concurrency.

### ECS

Có thể tách workload thành ECS service riêng theo dependency hoặc mức độ quan trọng. Mỗi service có desired count, autoscaling, CPU/memory và task role riêng. Giới hạn số task hoặc concurrency ở consumer giúp bảo vệ database. Một service recommendation bị nghẽn không nên làm cạn capacity của service checkout.

### EKS

Dùng namespace, resource requests/limits, ResourceQuota, LimitRange, node group hoặc workload pool riêng để giảm tranh chấp CPU/memory. NetworkPolicy và service account tách quyền truy cập. HPA có thể scale theo metric nhưng cần đặt max replicas và capacity của downstream; autoscaling quá nhanh có thể tạo thêm tải lên database.

### EC2

Tách Auto Scaling group hoặc process pool theo workload; dùng connection pool riêng cho từng dependency. Giới hạn số worker và queue length để tránh một loại request chiếm toàn bộ instance.

## 14. Circuit breaker và fallback

Khi breaker Open, hệ thống cần quyết định trả lỗi, dùng dữ liệu cũ hay chuyển công việc sang queue. Fallback phải phù hợp với ngữ nghĩa nghiệp vụ.

| Dependency | Fallback có thể cân nhắc | Điều cần tránh |
|---|---|---|
| Recommendation | Trả danh sách mặc định hoặc bỏ qua phần gợi ý | Chặn toàn bộ checkout chỉ vì recommendation lỗi |
| Product catalog cache | Trả dữ liệu cache còn trong thời hạn an toàn | Dùng dữ liệu giá hoặc tồn kho cũ khi nghiệp vụ yêu cầu chính xác |
| Notification | Ghi yêu cầu vào queue để gửi sau | Báo đã gửi thành công khi chưa lưu được yêu cầu |
| Payment | Trả trạng thái pending hoặc yêu cầu thử lại có kiểm soát | Khẳng định thanh toán thành công khi chưa xác nhận |
| Inventory | Từ chối hoặc chuyển trạng thái chờ xác nhận | Bán vượt tồn kho vì dùng fallback không đáng tin |

Fallback có thể tạo thêm tải lên cache, queue hoặc dịch vụ khác. Cần bảo vệ fallback bằng timeout, bulkhead và capacity riêng. Nếu fallback phụ thuộc cùng một database đang lỗi, nó không phải đường phục hồi độc lập.

## 15. Quan sát và cảnh báo

Không thể điều chỉnh retry/breaker/bulkhead chỉ bằng cảm giác. Cần đo cả request gốc, retry và trạng thái tài nguyên.

| Metric | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Request rate | Lưu lượng request gốc | Tải có tăng bất thường không? |
| Retry attempts / retry ratio | Số retry và tỷ lệ so với request gốc | Retry có đang làm tăng tải không? |
| Retry budget remaining/exhausted | Mức budget còn lại hoặc số lần cạn | Chính sách có quá chặt hoặc quá lỏng? |
| Timeout rate | Tỷ lệ request hết thời gian | Timeout có xảy ra ở dependency nào? |
| Circuit state / open count | Trạng thái breaker và số lần mở | Dependency có đang suy giảm? |
| Half-open probe result | Kết quả probe phục hồi | Dependency đã khỏe đủ để nhận tải chưa? |
| Bulkhead rejection / saturation | Số request bị từ chối do hết slot | Capacity có thiếu hoặc dependency quá chậm? |
| Pool utilization | Mức dùng thread/connection | Có cạn tài nguyên cục bộ không? |
| Queue age / DLQ depth | Tuổi message và backlog | Consumer có theo kịp producer không? |
| Downstream latency p95/p99 | Latency tail của dependency | Timeout có phù hợp với phân bố latency? |

Dùng Amazon CloudWatch metrics, logs và alarms để theo dõi. AWS X-Ray hoặc OpenTelemetry/ADOT có thể giúp xác định span nào chậm trong chuỗi gọi. Gắn trace ID, request ID và idempotency key vào log theo cách không làm lộ dữ liệu nhạy cảm.

Alarm nên dựa trên xu hướng và tác động: retry ratio tăng kéo dài, breaker mở liên tục, bulkhead rejection tăng, queue age vượt SLO hoặc DLQ tăng. Không chỉ cảnh báo mỗi lần breaker mở vì một lần mở ngắn có thể là hành vi bảo vệ đúng.

## 16. Ví dụ thiết kế: Orders gọi Payment và Recommendation

Giả sử API Orders có deadline 1,5 giây. Nó gọi hai dependency:

- Payment là dependency thiết yếu; không được xác nhận đơn hàng đã thanh toán nếu chưa có kết quả chắc chắn.
- Recommendation là chức năng phụ; có thể bỏ qua nếu chậm hoặc lỗi.

Thiết kế:

1. Đặt timeout cho Payment thấp hơn deadline còn lại; retry chỉ cho lỗi mạng/5xx có thể phục hồi và có idempotency key.
2. Circuit breaker riêng cho Payment; khi Open, trả trạng thái pending hoặc lỗi có kiểm soát, đồng thời đối soát qua webhook/status API.
3. Bulkhead riêng cho Payment và Recommendation để recommendation không chiếm thread/connection của payment.
4. Recommendation có breaker và fallback danh sách mặc định hoặc bỏ qua.
5. Retry budget riêng cho từng dependency, với giới hạn tổng tải.
6. Ghi metric retry, timeout, breaker state và bulkhead saturation.
7. Với công việc bất đồng bộ như gửi email, đẩy message vào SQS riêng và dùng DLQ.

~~~mermaid
flowchart LR
    A[Client] --> B[Orders API]
    B --> C[Payment Bulkhead]
    C --> D[Payment Circuit Breaker]
    D --> E[Payment Service]
    B --> F[Recommendation Bulkhead]
    F --> G[Recommendation Circuit Breaker]
    G --> H[Recommendation Service]
    B --> I[Notification SQS]
    I --> J[Notification Worker]
    B --> K[Retry Budget + Deadline]
~~~

Nếu Recommendation chậm, request vẫn có thể hoàn tất mà không chờ nó. Nếu Payment lỗi, hệ thống không được giả vờ thành công; nó cần trả trạng thái phù hợp và có cơ chế kiểm tra kết quả giao dịch. Đây là ví dụ về degraded mode có chủ đích.

## 17. Tính toán ngân sách retry cho một dependency

Giả sử service Orders có 2.000 request gốc mỗi phút tới Inventory. Mục tiêu retry budget là 3% request gốc trong cửa sổ một phút:

\[
2.000 \times 0.03 = 60\ \text{retry attempts/phút}
\]

Nếu tỷ lệ lỗi tăng và 500 request cần retry, hệ thống chỉ cho phép 60 retry trong cửa sổ; phần còn lại fail fast hoặc chuyển sang fallback. Điều này làm một số request thất bại sớm hơn, nhưng tránh tạo thêm 440 request vào dependency đang suy giảm.

Trong triển khai phân tán, budget cục bộ trên mỗi instance cần được tính theo số instance tối đa. Nếu có 10 instance và mỗi instance được 60 retry/phút, tổng budget có thể lên tới 600 retry/phút. Có thể phân bổ budget theo capacity của từng instance hoặc dùng bộ điều phối chung nếu cần giới hạn toàn fleet. Bộ đếm chung cũng là một dependency cần thiết kế HA và timeout; đừng để retry budget store trở thành điểm lỗi mới.

## 18. Những sai lầm thường gặp

### Retry ở mọi tầng

SDK, service wrapper, API Gateway và caller cùng retry làm tăng số request. Chọn một tầng chính, tính tổng attempts và ghi rõ trách nhiệm retry trong hợp đồng API.

### Không đặt timeout

Request có thể giữ thread và connection vô thời hạn. Đặt timeout cho connect/read/request và deadline tổng thể.

### Dùng backoff cố định không có jitter

Nhiều client retry cùng lúc. Dùng exponential backoff với jitter và cap.

### Retry thao tác ghi không idempotent

Có thể tạo đơn hàng hoặc trừ tiền hai lần. Dùng idempotency key, conditional write và deduplication.

### Circuit breaker quá nhạy

Một vài lỗi đơn lẻ làm breaker mở dù dependency vẫn khỏe. Dùng minimum request threshold, cửa sổ phù hợp và phân loại lỗi chính xác.

### Circuit breaker không có half-open giới hạn

Khi hết thời gian Open, mọi client cùng probe. Giới hạn probe concurrency và thêm jitter.

### Bulkhead chỉ giới hạn thread nhưng queue vô hạn

Request tiếp tục tích tụ và tiêu tốn memory. Giới hạn queue, thời gian chờ và hành vi khi đầy.

### Chia sẻ connection pool giữa các dependency

Một dependency chậm chiếm hết connection. Tách pool và đặt max connection, acquisition timeout.

### Fallback không an toàn

Trả thành công giả hoặc dùng dữ liệu cũ cho giao dịch cần chính xác có thể làm sai nghiệp vụ. Xác định rõ phần nào được degrade.

### Chỉ nhìn tỷ lệ lỗi mà không nhìn tải

Retry ratio có thể thấp nhưng request volume rất lớn; một dependency có thể bị quá tải. Theo dõi cả absolute retry count, concurrency, latency và saturation.

## 19. Checklist thiết kế resilience

- [ ] Có deadline tổng thể cho request và timeout cho từng dependency.
- [ ] Timeout của tầng dưới phù hợp với thời gian còn lại của caller.
- [ ] Chỉ retry lỗi tạm thời và có điều kiện.
- [ ] Retry dùng exponential backoff, jitter và giới hạn tối đa.
- [ ] Max attempts, retry budget và deadline được tính riêng và phối hợp.
- [ ] Thao tác ghi có idempotency key hoặc cơ chế deduplication phù hợp.
- [ ] Không có nhiều tầng retry cộng dồn ngoài dự kiến.
- [ ] Circuit breaker phân biệt lỗi dependency với lỗi nghiệp vụ/client.
- [ ] Breaker có closed/open/half-open, probe giới hạn và fallback an toàn.
- [ ] Bulkhead tách pool/concurrency/queue theo dependency hoặc workload quan trọng.
- [ ] Queue và pool có giới hạn; hành vi khi đầy được xác định.
- [ ] SQS consumer idempotent, có visibility timeout, redrive policy và DLQ.
- [ ] Step Functions/EventBridge retry được tính trong tổng retry path.
- [ ] AWS SDK retry mode được chọn rõ ràng và không bị bọc retry vô hạn.
- [ ] CloudWatch/X-Ray/ADOT đo retry, timeout, breaker, bulkhead và queue age.
- [ ] Có load test, fault injection và game day để kiểm chứng khi dependency suy giảm.
- [ ] Có tài liệu về degraded mode và hành động vận hành khi budget cạn.

## 20. Ghi nhớ

Retry budget giới hạn lượng retry để tránh tạo thêm tải trong lúc dependency đang suy giảm. Circuit breaker ngăn request tiếp tục gọi dependency lỗi và cho phép thử phục hồi có kiểm soát. Bulkhead chia tài nguyên để một nhóm request không chiếm hết capacity của hệ thống.

Ba cơ chế phải đi cùng timeout, deadline, exponential backoff có jitter và idempotency. Với AWS, có thể tận dụng retry strategy của SDK, SQS/DLQ, Step Functions retry, Lambda reserved concurrency, ECS/EKS resource isolation và CloudWatch/X-Ray để triển khai và quan sát. Các tính năng dịch vụ không thay thế chính sách ở cấp ứng dụng.

Một kiến trúc bền vững không cố gắng retry mọi lỗi cho tới khi thành công. Nó giới hạn công việc, fail fast khi cần, giữ capacity cho chức năng quan trọng và chỉ dùng fallback khi ngữ nghĩa nghiệp vụ cho phép. Hãy đo retry ratio, latency, saturation và kết quả diễn tập để điều chỉnh các ngưỡng theo tải thực tế.

## Tài liệu tham khảo

- [AWS Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
- [AWS SDKs and Tools: Retry behavior](https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html)
- [AWS Well-Architected: Control and Limit Retry Calls](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_limit_retries.html)
- [AWS Well-Architected: Use Timeouts to Control Demand](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_timeouts.html)
- [AWS Step Functions: Retrying after an error](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html)
- [Amazon SQS: Using dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS: Visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [AWS Lambda: Configuring reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [AWS Lambda: Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Amazon EventBridge: Retry policy and dead-letter queue](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-retry-policy.html)
- [Amazon CloudWatch: Alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html)
- [AWS X-Ray: Concepts](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html)
