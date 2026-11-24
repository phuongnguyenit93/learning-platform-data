# Timeout, retry, backoff và xử lý sự kiện trùng lặp

## 1. Vì sao serverless cần quản lý timeout và retry?

Ứng dụng serverless thường được kích hoạt bởi HTTP request, message trong queue, sự kiện object storage, lịch chạy hoặc lời gọi từ dịch vụ khác. Nền tảng có thể tự tạo execution environment, gọi function và thu hồi tài nguyên sau khi xử lý. Mô hình này giảm việc quản lý máy chủ, nhưng không loại bỏ lỗi mạng, dependency chậm, giới hạn thời gian chạy hoặc việc một sự kiện được giao nhiều lần.

Một function có thể xử lý xong nghiệp vụ nhưng mất kết nối trước khi gửi kết quả xác nhận. Hệ thống phát sự kiện không biết function đã hoàn tất hay chưa và có thể gửi lại. Function có thể nhận cùng một message hai lần do cơ chế giao nhận ít nhất một lần, timeout, visibility timeout hết hạn hoặc retry ở tầng caller. Nếu lần chạy thứ hai tạo đơn hàng hoặc trừ tiền lần nữa, người dùng chịu tác động trùng lặp dù từng lần thực thi đều không báo lỗi.

Vì vậy, vận hành serverless cần phối hợp bốn cơ chế:

- **Timeout và deadline:** giới hạn thời gian của function, request và lời gọi dependency.
- **Retry:** quyết định lỗi nào được thử lại, thử ở đâu và tối đa bao nhiêu lần.
- **Backoff và jitter:** giãn cách lần thử để tránh dồn tải lên dependency đang lỗi.
- **Idempotency và deduplication:** bảo đảm cùng một sự kiện được xử lý lại không tạo thêm tác động nghiệp vụ.

Các cơ chế này phải được thiết kế cùng queue, event source, database, API bên ngoài và SLO. Chỉ tăng timeout hoặc bật retry không tự làm hệ thống đáng tin cậy hơn; cấu hình sai có thể kéo dài request treo, tạo retry storm hoặc nhân đôi giao dịch.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, chủ đề này gắn với vận hành và tối ưu serverless: function cần xử lý sự kiện trong giới hạn compute, kết nối dependency hiệu quả, chịu được tải biến động và kiểm soát chi phí khi lỗi xảy ra.

Sau bài học, người học có thể:

- Phân biệt timeout của function, request, queue visibility và dependency.
- Thiết lập deadline tổng thể và chia timeout budget cho từng bước.
- Phân biệt retry do caller, nền tảng invocation và event source.
- Chọn exponential backoff, cap, jitter, retry budget và giới hạn số lần thử.
- Giải thích vì sao event có thể được giao nhiều lần và vì sao cần idempotency.
- Thiết kế idempotency key, deduplication store và xử lý atomic với thay đổi nghiệp vụ.
- Dùng DLQ, redrive và replay an toàn.
- Theo dõi retry, timeout, duplicate, age of message và chi phí.
- Kiểm thử các tình huống lỗi, race condition và sự kiện đến sai thứ tự.

## 2. Timeout, deadline và thời gian xử lý

### 2.1. Timeout là giới hạn cho một thao tác

Timeout xác định thời gian tối đa một thao tác được phép chờ. Khi hết thời gian, caller hoặc runtime dừng chờ và trả lỗi hoặc hủy thao tác theo khả năng của giao thức.

Một luồng serverless có thể có nhiều timeout độc lập:

- Timeout ở client hoặc API gateway.
- Timeout của lời gọi function đồng bộ.
- Maximum execution duration của function.
- Timeout khi kết nối database, cache hoặc HTTP API.
- Timeout của thao tác đọc/ghi storage.
- Visibility timeout hoặc thời hạn lease của message.
- Deadline nghiệp vụ, ví dụ đơn hàng phải được xác nhận trong 30 giây.

Các timeout không tự động đồng nhất. Client có thể bỏ cuộc trước khi function kết thúc; function có thể bị runtime kết thúc trước khi database hoàn tất; message có thể được giao lại khi worker vẫn đang xử lý nếu visibility timeout quá ngắn.

### 2.2. Deadline tổng thể

Deadline là thời điểm cuối cùng mà toàn bộ công việc còn có giá trị hoặc được phép hoàn tất. Khác với timeout riêng lẻ, deadline bao trùm cả chuỗi bước, gồm thời gian xếp hàng, khởi động, xử lý, gọi dependency và retry.

Ví dụ, API cần trả kết quả trong 8 giây. Nếu gateway timeout ở 8 giây và function timeout ở 30 giây, function có thể tiếp tục chạy sau khi client đã bỏ cuộc. Nếu function tiếp tục ghi dữ liệu hoặc gọi dịch vụ thanh toán, caller có thể retry và tạo tác động trùng.

Thiết kế tốt cần truyền deadline hoặc thời gian còn lại qua các lớp. Mỗi dependency nhận timeout nhỏ hơn phần ngân sách còn lại, để function còn thời gian xử lý lỗi và trả kết quả trước deadline.

### 2.3. Timeout budget

Giả sử deadline tổng thể là \(T_{total}\), thời gian khởi tạo/điều phối là \(T_{overhead}\), và có các bước xử lý với ngân sách \(T_1, T_2, \ldots, T_n\). Cần thỏa:

\[
T_{overhead} + \sum_{i=1}^{n} T_i \leq T_{total}
\]

Nếu dành toàn bộ deadline cho từng dependency riêng lẻ, tổng thời gian có thể vượt giới hạn. Ví dụ function có deadline 10 giây và gọi tuần tự database, payment API, email API. Đặt timeout 8 giây cho từng lời gọi có thể khiến function không thể hoàn thành trong 10 giây.

Một cách chia ngân sách minh họa:

| Giai đoạn | Budget |
|---|---:|
| Parse/validate và overhead | 0,5 giây |
| Database read/write | 2 giây |
| External API | 3 giây |
| Commit trạng thái và response | 1 giây |
| Dự phòng lỗi/serialization | 1 giây |
| Tổng | 7,5 giây |

Phần còn lại so với deadline là headroom cho biến động. Các con số cần lấy từ latency percentile và yêu cầu nghiệp vụ thực tế.

### 2.4. Đặt timeout theo latency đo được

Không chọn timeout chỉ theo cảm giác. Đo p50, p95, p99 và tail latency của dependency trong tải bình thường, tải cao và tình huống suy giảm. Timeout quá ngắn làm tăng lỗi giả và retry; timeout quá dài giữ execution environment, connection và concurrency trong thời gian không hữu ích.

Một số hướng dẫn:

- Timeout kết nối thường ngắn hơn timeout của toàn bộ request.
- Timeout đọc/ghi phải phù hợp với kích thước dữ liệu và throughput.
- Timeout của dependency nên nhỏ hơn thời gian còn lại của function.
- Function timeout phải đủ cho công việc hợp lệ nhưng không vượt deadline nghiệp vụ.
- Queue visibility timeout hoặc lease phải bao phủ thời gian xử lý dự kiến và cơ chế gia hạn nếu có.

### 2.5. Timeout không có nghĩa thao tác đã bị hủy

Khi client timeout, server hoặc dependency có thể vẫn đang thực hiện thao tác. Ví dụ, function gửi yêu cầu tạo giao dịch đến payment API nhưng kết nối bị ngắt trước khi nhận response. Không biết giao dịch đã được tạo hay chưa.

Đây là trạng thái kết quả không xác định. Không nên lập tức gửi lại lệnh tạo giao dịch bằng request mới. Hãy dùng idempotency key ổn định để truy vấn hoặc lặp lại an toàn cùng một thao tác. Với database, cần xác định transaction đã commit hay rollback bằng cách đọc trạng thái theo business key.

## 3. Timeout trong các kiểu invocation serverless

### 3.1. Synchronous invocation

Với lời gọi đồng bộ, caller chờ kết quả của function. Timeout có thể xuất hiện ở client, gateway, SDK và runtime. Giới hạn nhỏ nhất trong chuỗi quyết định caller còn chờ được bao lâu.

Nếu client timeout nhưng function tiếp tục chạy, caller có thể gửi lại request. Vì vậy, API tạo dữ liệu hoặc thực hiện thanh toán phải hỗ trợ idempotency kể cả khi caller không nhận được response.

### 3.2. Asynchronous invocation

Với lời gọi bất đồng bộ, caller gửi sự kiện rồi không chờ function trả kết quả trực tiếp. Nền tảng có thể lưu sự kiện, thử thực thi lại theo retry policy và gửi sự kiện thất bại đến destination hoặc DLQ nếu được cấu hình.

Retry policy và số lần thử khác nhau theo nền tảng, loại sự kiện và cấu hình. Cần xác định rõ ai chịu trách nhiệm retry: dịch vụ gọi function, nền tảng serverless hay event source. Không giả định mọi asynchronous invocation có cùng số lần retry hoặc cùng thời gian giữ sự kiện.

### 3.3. Queue/event source mapping

Với queue, event source mapping thường poll message rồi gọi function theo batch. Nếu function xử lý thất bại, message có thể trở lại queue sau visibility timeout hoặc theo cơ chế tương ứng. Có thể cần cấu hình partial batch response để chỉ retry message lỗi thay vì cả batch.

Đối với queue standard, thứ tự không nhất thiết được bảo đảm và message có thể được giao nhiều lần. Với queue FIFO, thứ tự trong message group và deduplication có các quy tắc riêng; vẫn cần idempotency trong ứng dụng vì retry hoặc timeout có thể tạo trạng thái không chắc chắn ở các hệ thống bên ngoài.

### 3.4. Event từ object storage, lịch và stream

Object storage event, scheduler và stream có thể phát lại sự kiện khi consumer lỗi hoặc checkpoint chưa được commit. Event có thể chứa object key, version, sequence hoặc event ID. Dùng các trường này làm input cho idempotency/deduplication khi semantics phù hợp.

Không giả định event luôn đến đúng một lần hoặc đúng thứ tự. Nếu nghiệp vụ phụ thuộc thứ tự, cần sequence/version, state machine hoặc cơ chế ordering riêng.

### 3.5. Bảng so sánh

| Kiểu kích hoạt | Caller chờ response? | Nguồn retry thường gặp | Điều cần thiết kế |
|---|---|---|---|
| HTTP/API đồng bộ | Có | Client, SDK, gateway hoặc caller | Deadline, response không xác định, idempotency key |
| Invocation bất đồng bộ | Không chờ kết quả cuối | Nền tảng invocation hoặc destination | Retry policy, event age, failure destination/DLQ |
| Queue polling | Không chờ client ban đầu | Queue visibility/redelivery và event source mapping | Visibility timeout, batch failure, ack/delete, DLQ |
| Stream | Consumer xử lý theo shard/partition | Replay từ checkpoint hoặc offset | Checkpoint, ordering, batch retry và poison record |
| Scheduled event | Không chờ người dùng | Scheduler/event delivery policy | Event ID, missed schedule, duplicate run và idempotency |

Đây là phân loại khái quát. Phải kiểm tra semantics thực tế của nhà cung cấp và event source.

## 4. Retry: khi nào nên thử lại?

### 4.1. Retry không phải giải pháp cho mọi lỗi

Retry hữu ích với lỗi tạm thời như timeout mạng ngắn, connection reset, throttling có thời hạn hoặc dịch vụ phụ thuộc đang khởi động lại. Retry không giúp sửa lỗi dữ liệu, lỗi validation, quyền truy cập sai hoặc bug xác định.

Phân loại lỗi trước khi retry:

| Nhóm lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| Transient | Connection reset, DNS timeout ngắn | Retry có backoff và giới hạn |
| Throttling | HTTP 429, quota tạm thời | Tôn trọng Retry-After, giảm tốc độ |
| Dependency unavailable | HTTP 503, database failover | Backoff, circuit breaker, retry budget |
| Timeout không rõ kết quả | Gửi payment nhưng mất response | Tra cứu bằng idempotency key trước khi quyết định |
| Permanent/business error | Invalid input, account closed | Không retry; trả lỗi hoặc đưa vào xử lý nghiệp vụ |
| Authorization/configuration | AccessDenied, sai endpoint | Không retry liên tục; sửa cấu hình/quyền |
| Poison event | Payload không parse được | Cách ly, DLQ và điều tra |

### 4.2. Retry ở đúng tầng

Một request có thể bị retry ở nhiều lớp: client, API gateway, SDK, function wrapper, event source và downstream service. Nếu mỗi lớp tự retry nhiều lần, tổng số lần gọi có thể nhân lên nhanh chóng.

Ví dụ, client thử 3 lần, function SDK thử 4 lần và event source giao lại 5 lần có thể tạo tới 60 lần thực hiện downstream trong trường hợp xấu, tùy cách các lớp lồng nhau. Hãy chọn một tầng chịu trách nhiệm chính cho retry và đặt giới hạn tổng thể cho toàn luồng.

### 4.3. Retry chỉ với thao tác an toàn

Trước khi retry, xác định thao tác có idempotent hay không. Đọc dữ liệu thường có thể retry; ghi dữ liệu hoặc gọi API tạo giao dịch cần idempotency key hoặc transaction semantics. Nếu timeout làm kết quả không rõ, kiểm tra trạng thái trước khi gửi lại.

### 4.4. Retry budget

Retry budget giới hạn số lượng hoặc tỷ lệ request được phép retry trong một khoảng thời gian. Khi lỗi tăng, budget cạn sẽ ngăn hệ thống tiếp tục khuếch đại tải. Có thể giới hạn theo service, dependency, tenant hoặc operation.

Một chính sách có thể giới hạn tối đa 2 lần retry cho mỗi request và tổng retry không vượt 5% số request trong một cửa sổ. Các ngưỡng phải phù hợp với SLO, không phải giá trị mặc định cho mọi hệ thống.

### 4.5. Không retry lỗi permanent

Lỗi validation, dữ liệu sai schema, tài nguyên không tồn tại theo nghiệp vụ hoặc quyền bị từ chối thường cần sửa dữ liệu/cấu hình. Retry chỉ làm tăng chi phí invocation và log. Phân loại mã lỗi và response body một cách có kiểm soát, tránh retry mọi HTTP 4xx hoặc mọi exception chung.

## 5. Exponential backoff và jitter

### 5.1. Exponential backoff

Exponential backoff tăng thời gian chờ giữa các lần retry. Một mô hình cơ bản:

\[
d_n = \min(d_{max}, d_0 \times 2^n)
\]

Trong đó:

- \(d_0\): thời gian chờ ban đầu.
- \(n\): số lần retry đã thực hiện, bắt đầu từ 0.
- \(d_{max}\): giới hạn tối đa của thời gian chờ.
- \(d_n\): thời gian chờ trước lần retry tiếp theo.

Ví dụ, với base delay 0,5 giây và cap 8 giây, chuỗi delay không jitter là 0,5; 1; 2; 4; 8; 8 giây. Cap ngăn thời gian chờ tăng vô hạn.

### 5.2. Vì sao cần jitter?

Nếu hàng nghìn function gặp cùng một lỗi và cùng retry sau 1, 2, 4 giây, chúng có thể gửi request lại gần như đồng thời. Hiện tượng này tạo thundering herd, làm dependency vừa phục hồi lại bị quá tải.

Jitter thêm yếu tố ngẫu nhiên vào thời gian chờ để phân tán lần thử. Một dạng full jitter:

\[
d_n = U(0, \min(d_{max}, d_0 \times 2^n))
\]

Trong đó \(U(0,x)\) là giá trị ngẫu nhiên đều trong khoảng từ 0 đến \(x\). Có nhiều biến thể jitter; chọn theo thư viện hoặc chuẩn của hệ thống và kiểm tra cách triển khai thực tế.

### 5.3. Tôn trọng Retry-After

Nếu downstream trả `Retry-After`, nên xem đó là gợi ý thời gian chờ hoặc giới hạn tối thiểu theo semantics của API. Kết hợp với jitter để nhiều caller không thức dậy cùng lúc. Nếu thời gian được yêu cầu vượt deadline nghiệp vụ, dừng retry và chuyển sang trạng thái chờ hoặc thất bại có kiểm soát.

### 5.4. Giới hạn số lần thử và thời gian tổng

Retry cần có cả `maxAttempts` và deadline tổng. Chỉ giới hạn số lần thử là chưa đủ nếu mỗi lần chờ dài; chỉ giới hạn thời gian tổng là chưa đủ nếu retry dồn dập. Cần theo dõi cả số lần thử, tổng thời gian và chi phí.

### 5.5. Ví dụ hàm tính delay

```python
import random

def retry_delay(attempt, base_seconds=0.5, cap_seconds=20.0):
    upper = min(cap_seconds, base_seconds * (2 ** attempt))
    return random.uniform(0.0, upper)
```

Hàm trên minh họa full jitter. Trong production cần giới hạn attempt, xử lý tràn số nếu attempt rất lớn, tôn trọng deadline và `Retry-After`, đồng thời dùng retry budget. Không để vòng lặp retry chạy vượt thời gian thực thi tối đa của function.

## 6. Timeout budget khi retry

### 6.1. Tổng thời gian của một chuỗi retry

Giả sử mỗi lần thử có timeout \(t_i\), giữa các lần thử có delay \(d_i\), và có \(A\) lần thử. Tổng thời gian gần đúng:

\[
T_{retry} = \sum_{i=1}^{A} t_i + \sum_{i=1}^{A-1} d_i
\]

Phải bảo đảm:

\[
T_{retry} + T_{cleanup} + T_{response} \leq T_{remaining}
\]

Nếu không còn đủ thời gian, không bắt đầu lần retry mới. Hãy lưu trạng thái cần thiết và để event source hoặc scheduler thử lại sau, hoặc trả kết quả có thể retry cho caller.

### 6.2. Ví dụ deadline

Function có thời gian còn lại 6 giây. Một dependency call có timeout 1,5 giây; policy cho phép tối đa 3 attempts, với delay 0,5 và 1 giây. Thời gian tối đa gần đúng là:

\[
3 \times 1.5 + 0.5 + 1 = 6 \text{ giây}
\]

Chưa tính parsing, cleanup và ghi log. Vì vậy policy này không phù hợp nếu function cần trả response trong 6 giây. Cần giảm số lần thử, giảm timeout mỗi lần, chuyển xử lý sang bất đồng bộ hoặc để caller/event source thực hiện retry ở một thời điểm khác.

### 6.3. Truyền deadline thay vì timeout cố định

Khi function gọi nhiều service, truyền deadline tuyệt đối hoặc thời gian còn lại thay vì đặt timeout cố định độc lập cho mỗi service. Mỗi client tính thời gian còn lại trước khi gửi request. Nếu ngân sách gần hết, bỏ qua bước không thiết yếu hoặc trả lỗi có kiểm soát.

### 6.4. Hủy thao tác và cancellation

Một số runtime/client hỗ trợ cancellation token hoặc abort signal. Khi function sắp hết deadline, hủy lời gọi downstream còn có thể hủy được để tránh tiếp tục tiêu thụ tài nguyên. Tuy nhiên, cancellation không bảo đảm thao tác từ xa đã rollback. Với write operation, vẫn cần idempotency và kiểm tra trạng thái.

## 7. Vì sao sự kiện bị giao trùng?

### 7.1. At-least-once delivery

Nhiều hệ thống queue/event hướng tới giao ít nhất một lần: event được giữ cho đến khi consumer xác nhận hoặc checkpoint. Nếu consumer xử lý xong nhưng ACK bị mất, event source có thể giao lại. Điều này ưu tiên không mất sự kiện nhưng có thể tạo bản giao trùng.

“At least once” không có nghĩa event chắc chắn được xử lý thành công; nó có nghĩa hệ thống có thể giao lại theo chính sách cho đến khi đạt điều kiện hoặc hết retention/retry. Các semantics khác nhau theo nguồn sự kiện.

### 7.2. Các nguyên nhân phổ biến

- Function hoàn tất nghiệp vụ nhưng timeout trước khi ACK/response được ghi nhận.
- Runtime hoặc worker bị terminate sau khi đã ghi một phần dữ liệu.
- Visibility timeout hết trước khi function hoàn tất.
- Batch có một record lỗi khiến cả batch được giao lại.
- Event source retry sau lỗi tạm thời.
- Caller gửi lại request vì không nhận được response.
- Scheduler phát cùng một lịch do retry hoặc xử lý bù.
- Người vận hành redrive message từ DLQ nhiều lần.
- Stream consumer replay từ checkpoint cũ.
- Event producer phát lại do transaction/outbox chưa được đánh dấu hoàn tất.

### 7.3. Duplicate không nhất thiết có cùng thời điểm

Hai bản event có thể đến gần nhau hoặc cách nhau nhiều giờ/ngày. Deduplication cần giữ key đủ lâu so với thời gian retry, retention, redrive và replay. TTL quá ngắn khiến một event cũ được xử lý lại sau khi key hết hạn.

### 7.4. Duplicate và out-of-order là hai vấn đề khác nhau

Idempotency ngăn tác động lặp của cùng một event. Nó không tự giải quyết event đến sai thứ tự. Ví dụ `OrderPaid` có thể đến trước `OrderCreated` do hai luồng xử lý khác nhau. Cần sequence/version, state transition hợp lệ hoặc buffer sự kiện theo aggregate khi thứ tự có ý nghĩa.

## 8. Idempotency và deduplication

### 8.1. Idempotent operation

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng định danh/đầu vào mà trạng thái nghiệp vụ cuối cùng tương đương với thực hiện một lần.

Ví dụ:

- Đặt trạng thái đơn hàng thành `PAID` theo cùng payment ID.
- Ghi kết quả của một partition theo khóa ổn định.
- Tạo tài nguyên với client-supplied idempotency key và trả lại kết quả đã có.
- Upsert một record theo business key với quy tắc cập nhật xác định.

Một thao tác tăng số dư thêm 100 mỗi lần gọi không idempotent. Thay đổi thành “ghi nhận giao dịch có ID X nếu chưa tồn tại, rồi tính số dư từ ledger” có thể làm thao tác retry an toàn hơn nếu được thực hiện trong transaction.

### 8.2. Idempotency key

Idempotency key là định danh ổn định cho một yêu cầu nghiệp vụ. Có thể lấy từ:

- Event ID do producer cấp.
- Message ID nếu semantics của event source bảo đảm ổn định khi redelivery.
- Business transaction ID hoặc order ID kết hợp operation type.
- Client-generated request ID được giữ nguyên qua retry.
- Object key + version ID + event type đối với object event.

Không tạo UUID mới mỗi lần retry cùng một thao tác; như vậy mỗi lần thử sẽ bị xem là yêu cầu mới. Cũng không dùng payload hash một cách mù quáng nếu hai sự kiện hợp lệ có payload giống nhau nhưng là hai nghiệp vụ riêng.

### 8.3. Dedupe store

Dedupe store lưu key đã xử lý hoặc đang xử lý, kèm trạng thái và kết quả. Có thể dùng database, conditional write, unique constraint hoặc dịch vụ key-value có thao tác atomic.

Một record có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| `idempotency_key` | Khóa duy nhất của thao tác |
| `status` | `IN_PROGRESS`, `COMPLETED` hoặc trạng thái lỗi có thể retry |
| `request_hash` | Phát hiện cùng key nhưng payload khác |
| `result_ref` | Tham chiếu kết quả đã tạo |
| `created_at` | Thời điểm bắt đầu |
| `expires_at` | Thời điểm hết retention của key |
| `owner/lease` | Worker hoặc lease đang xử lý nếu cần |

### 8.4. Kiểm tra và ghi key phải atomic

Mẫu không an toàn:

1. Đọc dedupe store, thấy key chưa tồn tại.
2. Tạo đơn hàng.
3. Ghi key đã xử lý.

Nếu function chết sau bước 2 nhưng trước bước 3, event được giao lại và đơn hàng được tạo lần nữa.

Mẫu an toàn hơn dùng unique constraint/conditional insert để chỉ một worker chiếm được key, sau đó thay đổi nghiệp vụ và trạng thái idempotency trong cùng transaction khi chúng nằm trong cùng database. Nếu side effect ở hệ thống ngoài không tham gia transaction, dùng outbox/inbox, idempotency API của downstream hoặc state machine có khả năng đối soát.

### 8.5. Xử lý cùng key nhưng payload khác

Nếu cùng idempotency key nhưng request hash khác, không nên trả lại kết quả cũ một cách âm thầm. Đây có thể là bug caller hoặc key collision. Từ chối với lỗi rõ ràng, ghi log có correlation ID và điều tra.

### 8.6. TTL và thời gian lưu key

TTL phải dài hơn khoảng thời gian event có thể được retry, redrive hoặc replay. Cân nhắc queue retention, DLQ retention, lịch retry, thời gian người vận hành có thể redrive và quy định nghiệp vụ.

Nếu cần chống duplicate vĩnh viễn cho giao dịch tài chính, không dựa vào TTL ngắn; dùng business transaction ID/ledger có unique constraint hoặc chính sách lưu lâu dài. Dedupe cache có thể tối ưu hiệu năng nhưng không nên là nguồn sự thật duy nhất nếu việc mất cache dẫn đến giao dịch lặp.

## 9. Ví dụ xử lý idempotent

### 9.1. Mẫu SQL với unique constraint

Giả sử ứng dụng nhận sự kiện thanh toán có `payment_event_id`. Có thể tạo bảng inbox:

```sql
CREATE TABLE processed_events (
    event_id        VARCHAR(200) PRIMARY KEY,
    request_hash    VARCHAR(128) NOT NULL,
    processed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Trong transaction:

```sql
BEGIN;

INSERT INTO processed_events (event_id, request_hash)
VALUES (:event_id, :request_hash)
ON CONFLICT (event_id) DO NOTHING;

-- Ứng dụng kiểm tra số dòng được insert.
-- Chỉ worker thắng quyền insert mới thực hiện thay đổi nghiệp vụ.
UPDATE orders
SET payment_status = 'PAID'
WHERE order_id = :order_id
  AND payment_status <> 'PAID';

COMMIT;
```

Đây là phác thảo; logic phải kiểm tra kết quả insert và payload hash trước khi update. Nếu event đã tồn tại với cùng hash, trả kết quả đã xử lý. Nếu cùng key nhưng hash khác, đưa vào nhánh conflict. Inbox insert và thay đổi order phải nằm trong cùng transaction để tránh cửa sổ lỗi giữa hai thao tác.

### 9.2. State machine cho tác vụ nhiều bước

Với nghiệp vụ có nhiều side effect, lưu trạng thái rõ ràng:

```text
RECEIVED -> VALIDATED -> PAYMENT_REQUESTED -> PAYMENT_CONFIRMED -> COMPLETED
                  |              |
                  v              v
               REJECTED       UNKNOWN
```

`UNKNOWN` biểu thị timeout khi gọi payment API mà chưa biết giao dịch đã thành công chưa. Worker cần truy vấn downstream bằng idempotency key hoặc payment reference trước khi gửi lệnh mới.

State machine cần định nghĩa transition hợp lệ, retryable state, terminal state và cách đối soát khi một bước không thể xác định kết quả.

### 9.3. Idempotency key cho HTTP API

Client gửi header `Idempotency-Key` ổn định cho một thao tác tạo đơn. Server lưu key cùng request hash và kết quả. Nếu client retry do timeout, server trả kết quả đã lưu thay vì tạo đơn mới.

```http
POST /orders
Idempotency-Key: order-create-7f3a...
Content-Type: application/json
```

Key cần được giữ nguyên cho tất cả retry của cùng một thao tác. Server cần xác định scope của key, ví dụ theo tenant/account và operation, để tránh va chạm giữa người dùng.

### 9.4. Idempotency không thay thế authorization

Khi trả lại kết quả đã lưu, vẫn phải xác minh caller hiện tại có quyền xem tài nguyên đó. Không để idempotency key trở thành cách truy cập kết quả của tenant khác. Dedupe key cần được scope theo tenant hoặc principal phù hợp.

## 10. Xử lý batch và message queue

### 10.1. Vì sao batch làm duplicate khó hơn?

Function có thể nhận nhiều message trong một batch. Nếu xử lý 9 message thành công nhưng message thứ 10 lỗi, một số event source có thể giao lại cả batch. Chín message đầu có thể chạy lại dù đã hoàn tất.

Idempotency cần được thực hiện ở cấp từng message, không chỉ cấp batch. Nếu event source hỗ trợ partial batch response, trả về chính xác các record cần retry để giảm xử lý lặp.

### 10.2. Partial batch failure

Với queue/event source mapping hỗ trợ partial batch response, function có thể báo danh sách message ID lỗi. Event source chỉ giao lại những record đó theo semantics được hỗ trợ.

Ví dụ logic:

```python
def handler(records):
    failures = []
    for record in records:
        try:
            process_idempotently(record)
        except RetryableError:
            failures.append({"itemIdentifier": record["messageId"]})
        except PermanentError:
            send_to_failure_store(record)
    return {"batchItemFailures": failures}
```

Đây là pseudocode theo một kiểu response thường gặp; tên trường và cách bật partial batch response phụ thuộc nền tảng/event source. Permanent error cần được ghi nhận hoặc chuyển DLQ theo chính sách, không được âm thầm bỏ message.

### 10.3. Visibility timeout

Với queue có visibility timeout, message sau khi được nhận sẽ tạm ẩn khỏi consumer khác. Nếu function chưa hoàn tất khi visibility timeout hết, message có thể được giao lại trong khi lần xử lý đầu vẫn đang chạy.

Đặt visibility timeout dài hơn thời gian xử lý tối đa dự kiến, cộng headroom cho batch và overhead. Nếu xử lý có thể kéo dài, dùng cơ chế gia hạn visibility/lease khi được hỗ trợ. Không đặt quá dài nếu nó làm chậm phục hồi message khi worker chết.

### 10.4. Batch size và concurrency

Batch lớn có thể giảm overhead invocation nhưng tăng thời gian xử lý và phạm vi retry khi có lỗi. Concurrency cao tăng throughput nhưng cũng tăng số request đồng thời đến dependency và nguy cơ duplicate khi nhiều lease hết hạn.

Chọn batch size, maximum concurrency và timeout cùng nhau. Kiểm tra dependency connection pool, API rate limit và thời gian xử lý p99.

### 10.5. FIFO và ordering

Queue FIFO hoặc message group có thể giữ thứ tự trong phạm vi được định nghĩa, nhưng consumer vẫn cần xử lý duplicate. Một message lỗi có thể chặn message sau trong cùng group tùy semantics. Thiết kế DLQ/redrive phải cân nhắc việc khôi phục thứ tự và không để một poison message chặn vô hạn toàn bộ group.

## 11. Dead-letter queue và redrive

### 11.1. DLQ là gì?

Dead-letter queue (DLQ) hoặc failure destination lưu sự kiện không thể xử lý sau số lần thử hoặc thời hạn nhất định. Nó giúp tách message lỗi khỏi luồng chính để điều tra và xử lý sau.

DLQ không phải nơi lưu message rồi quên. Cần giám sát số lượng, tuổi message, loại lỗi, owner và quy trình khôi phục.

### 11.2. Phân biệt retryable và poison message

Retryable message có thể xử lý được sau khi dependency hồi phục. Poison message luôn thất bại do payload/schema không hợp lệ, dữ liệu không tồn tại hoặc bug xác định. Retry poison message nhiều lần chỉ tăng chi phí và làm chậm message khác.

Có thể dùng max receive count hoặc max retry attempts để đưa message sang DLQ. Ngưỡng cần phù hợp với loại lỗi, thời gian dependency hồi phục và retention.

### 11.3. Redrive an toàn

Trước khi redrive:

1. Xác định nguyên nhân gốc đã được sửa.
2. Kiểm tra payload và schema có còn hợp lệ không.
3. Xác định event ID/idempotency key có được giữ nguyên không.
4. Kiểm tra trạng thái nghiệp vụ để tránh tạo tác động trùng.
5. Giới hạn tốc độ redrive để không làm dependency quá tải.
6. Theo dõi kết quả, số lần retry và message quay lại DLQ.

Không tạo ID mới cho event khi redrive nếu mục tiêu là tiếp tục cùng một thao tác nghiệp vụ. Nếu cần tạo một nghiệp vụ mới, phải có ID mới và audit rõ lý do.

### 11.4. DLQ retention và access control

DLQ có thể chứa dữ liệu nhạy cảm hoặc payload không hợp lệ. Giới hạn quyền đọc, mã hóa, đặt retention và audit truy cập. Không log toàn bộ payload vào log công khai; dùng correlation ID và trường đã được làm sạch.

## 12. Retry storm, circuit breaker và backpressure

### 12.1. Retry storm

Retry storm xảy ra khi nhiều client/function đồng thời thử lại dependency lỗi. Số request có thể tăng nhanh hơn khả năng phục hồi của dịch vụ. Các function giữ concurrency trong lúc chờ khiến queue backlog và chi phí invocation tăng.

Dấu hiệu:

- Retry rate và timeout tăng đồng thời.
- Downstream 429/5xx tăng.
- Latency p95/p99 tăng, throughput thành công giảm.
- Queue age và số message in-flight tăng.
- Function concurrency đạt giới hạn nhưng số việc hoàn tất không tăng.

### 12.2. Circuit breaker

Circuit breaker theo dõi tỷ lệ lỗi/timeout của dependency. Khi vượt ngưỡng, breaker mở và từ chối hoặc trì hoãn lời gọi mới trong một khoảng thời gian. Sau đó breaker chuyển half-open để thử một số request giới hạn; nếu thành công thì đóng lại.

Circuit breaker giảm áp lực lên dependency đang lỗi nhưng không thay thế retry policy, timeout hay idempotency. Cần tránh để mỗi execution environment giữ breaker state độc lập mà không hiểu tổng concurrency; có thể cần gateway hoặc cơ chế chia sẻ trạng thái.

### 12.3. Backpressure

Backpressure giảm tốc độ upstream khi downstream không thể nhận thêm việc. Với serverless, có thể giới hạn event source concurrency, reserved concurrency, queue consumer rate hoặc admission rate. Tùy nền tảng, reserved concurrency có thể giới hạn function tổng thể nhưng không thay thế rate limit theo dependency.

Nếu queue backlog tăng vì downstream throttling, tăng concurrency function thường làm tình trạng tệ hơn. Giữ backlog trong giới hạn retention, giảm consumer rate và phát cảnh báo theo tuổi message.

### 12.4. Load shedding

Khi deadline sắp hết hoặc dependency bão hòa, có thể từ chối sớm request ít ưu tiên, trả lỗi retryable có hướng dẫn, hoặc chuyển công việc sang queue. Không nhận thêm việc nếu hệ thống không thể xử lý trong thời hạn nghiệp vụ.

### 12.5. Retry budget kết hợp circuit breaker

Retry budget giới hạn tổng nỗ lực; circuit breaker ngăn gọi dependency trong lúc lỗi kéo dài. Khi breaker mở, không tiếp tục tiêu thụ retry budget bằng các lần thử vô ích. Khi half-open, chỉ cho phép số request nhỏ để kiểm tra phục hồi.

## 13. Tối ưu timeout và retry cho hiệu năng, chi phí

### 13.1. Chi phí của một invocation

Mỗi lần retry có thể tạo thêm invocation duration, request đến dependency, log, network transfer và storage operation. Một function timeout dài nhưng thường xuyên chờ dependency có thể giữ concurrency lâu và tăng chi phí.

Tối ưu cần xem:

- Duration và billed duration theo runtime.
- Số lần invocation/retry trên mỗi event.
- Cold start và initialization time.
- Memory/CPU allocation và throughput.
- Queue wait, message age và concurrency.
- Dependency request count và throttling.
- DLQ/redrive và storage cost.

### 13.2. Không đặt timeout quá lớn để che lỗi

Timeout dài có thể giúp job hợp lệ chạy xong, nhưng cũng giữ tài nguyên cho request treo và làm message phục hồi chậm. Tách tác vụ dài sang workflow/queue hoặc chia nhỏ job nếu phù hợp. Chọn timeout theo phân bố thời gian thực tế và deadline, không chỉ theo giới hạn tối đa của nền tảng.

### 13.3. Reuse connection và client

Tái sử dụng SDK client và connection pool trong execution environment có thể giảm thời gian thiết lập. Tuy nhiên, môi trường serverless có thể bị freeze hoặc thu hồi; connection có thể hết hạn. Kiểm tra connection trước khi dùng, đặt idle timeout và reconnect an toàn.

Không tạo connection mới cho mọi request nếu có thể reuse; đồng thời không để tổng connection khi scale-out vượt giới hạn database. Dùng proxy/pooler hoặc concurrency limit khi cần.

### 13.4. Giảm payload và batch phù hợp

Payload lớn tăng thời gian serialize, truyền và parse. Với file/object event, truyền reference và version ID thay vì nhúng toàn bộ dữ liệu. Batch có thể giảm invocation overhead nhưng phải cân bằng thời gian xử lý, retry scope và memory.

### 13.5. Tối ưu concurrency có giới hạn

Concurrency cao không luôn tăng throughput. Khi downstream bão hòa, nó chỉ làm tăng wait time, timeout và duplicate. Xác định concurrency an toàn qua load test, sau đó đặt giới hạn theo function và dependency.

## 14. Quan sát timeout, retry và duplicate

### 14.1. Metric cần có

- Invocation count, success/error, timeout và duration p50/p95/p99.
- Retry attempts trên mỗi event và retry rate theo dependency.
- Function concurrency, throttled invocation và execution environment initialization.
- Queue depth, age of oldest message, in-flight count và receive count.
- Duplicate event count và idempotency hit/miss/conflict.
- DLQ depth, DLQ age, redrive success/failure.
- Downstream latency, 429/5xx, connection pool wait và circuit breaker state.
- Chi phí invocation/duration và chi phí dependency trên mỗi event hoàn tất.

### 14.2. Log có correlation ID

Log nên chứa event ID, idempotency key đã được che hoặc hash, request ID, trace ID, attempt number, function version, dependency name và kết quả xử lý. Không log token, password, payment data hoặc toàn bộ payload nhạy cảm.

Correlation ID giúp nối một sự kiện qua nhiều lần invocation và phân biệt retry với event nghiệp vụ mới.

### 14.3. Phân biệt retry với duplicate nghiệp vụ

Retry attempt count cho biết số lần thử của cùng một delivery chain; duplicate business event được nhận diện bằng idempotency key. Hai khái niệm không nhất thiết bằng nhau: một message có thể được giao lại sau khi retry metadata bị mất hoặc qua một luồng replay khác.

### 14.4. Alert theo tác động

Ưu tiên cảnh báo:

- Timeout rate vượt SLO.
- Retry rate tăng mạnh trong khi success rate giảm.
- Age of oldest message vượt deadline.
- DLQ có message mới hoặc tăng nhanh.
- Idempotency conflict xuất hiện.
- Duplicate side effect được phát hiện.
- Dependency circuit breaker mở kéo dài.
- Function concurrency chạm giới hạn và backlog tiếp tục tăng.

Không chỉ cảnh báo theo số invocation tăng; đó có thể là traffic hợp lệ. Cần liên kết với error, latency và công việc hoàn tất.

## 15. Kiểm thử độ tin cậy

### 15.1. Kiểm thử timeout

Thử dependency phản hồi chậm hơn timeout, không phản hồi, đóng kết nối giữa chừng và trả response sau khi caller đã hết deadline. Xác minh function không tiếp tục tạo tác động ngoài ý muốn sau timeout.

### 15.2. Kiểm thử duplicate

Gửi cùng event ID nhiều lần đồng thời và tuần tự. Xác minh chỉ một thay đổi nghiệp vụ được commit, các lần sau trả kết quả ổn định và cùng key với payload khác bị từ chối.

### 15.3. Kiểm thử crash window

Chủ động dừng function ở các điểm:

- Trước khi ghi dedupe key.
- Sau khi claim key nhưng trước nghiệp vụ.
- Sau khi commit nghiệp vụ nhưng trước ACK.
- Sau khi gọi downstream nhưng trước khi lưu kết quả.
- Trong lúc ghi checkpoint hoặc update state.

Kiểm tra lần giao lại có thể phục hồi hoặc đối soát mà không tạo side effect trùng.

### 15.4. Kiểm thử retry storm

Cho dependency trả 429/503 hoặc tăng latency trong một khoảng thời gian. Xác minh backoff+jitter phân tán request, retry budget giới hạn nỗ lực, circuit breaker mở và concurrency không vượt ngưỡng bảo vệ.

### 15.5. Kiểm thử DLQ và redrive

Đưa một poison message vào DLQ, sửa nguyên nhân rồi redrive một phần nhỏ. Xác minh idempotency key được giữ, tốc độ redrive có giới hạn và message không quay lại DLQ vô hạn.

## 16. Ví dụ thực tế

### Ví dụ 1: API tạo đơn bị client retry sau timeout

Client gọi `POST /orders`. Function tạo đơn trong database nhưng response bị mất khi API gateway timeout. Client gửi lại request và function tạo đơn thứ hai.

**Nguyên nhân:** hệ thống không phân biệt retry của cùng thao tác với yêu cầu tạo đơn mới.

**Thiết kế lại:** client gửi `Idempotency-Key` ổn định; server lưu key và request hash với unique constraint. Việc tạo đơn và ghi kết quả idempotency nằm trong cùng transaction. Khi request lặp, server trả kết quả đã lưu; nếu payload khác với cùng key, trả conflict.

**Kiểm tra:** mô phỏng mất response sau commit và gửi lại cùng key nhiều lần; xác minh chỉ một order được tạo.

### Ví dụ 2: Queue worker timeout và message được giao lại

Function xử lý message trong 90 giây nhưng visibility timeout của queue chỉ 60 giây. Message trở nên visible trước khi function đầu tiên kết thúc; worker thứ hai nhận cùng message.

**Nguyên nhân:** lease/visibility timeout ngắn hơn thời gian xử lý, không có gia hạn và business operation không idempotent.

**Thiết kế lại:** điều chỉnh visibility timeout theo p99 duration cộng headroom; dùng heartbeat/extension nếu nền tảng hỗ trợ; lưu idempotency key theo message ID hoặc business ID; chỉ ACK khi trạng thái đã commit.

**Kiểm tra:** kéo dài xử lý, kill worker giữa chừng và xác minh redelivery không tạo side effect trùng.

### Ví dụ 3: Retry storm khi external API trả 429

Một đợt traffic tăng khiến external API trả 429. Mỗi function retry ngay ba lần; hàng nghìn invocation đồng loạt gửi lại và quota tiếp tục bị vượt.

**Nguyên nhân:** không có backoff, jitter, rate limit chung hoặc retry budget.

**Thiết kế lại:** tôn trọng `Retry-After`, dùng exponential backoff với full jitter, giới hạn attempts và tổng retry budget; giảm event source concurrency hoặc đẩy công việc vào queue. Theo dõi quota và age of oldest message.

**Kiểm tra:** giả lập 429 trong vài phút, đo request rate đến dependency và xác minh nó giảm thay vì tăng theo số retry.

### Ví dụ 4: Payment API timeout với kết quả không xác định

Function gửi yêu cầu thanh toán. Payment API đã xử lý nhưng response bị mất. Function retry bằng request mới và khách hàng bị trừ tiền hai lần.

**Nguyên nhân:** timeout được coi như thất bại chắc chắn, trong khi thao tác từ xa có thể đã commit.

**Thiết kế lại:** dùng idempotency key ổn định do business transaction tạo; khi timeout, truy vấn payment API bằng key/reference trước khi gửi lại. Lưu state `UNKNOWN` và chạy reconciliation nếu chưa xác định được kết quả.

**Kiểm tra:** ngắt kết nối sau khi payment API commit nhưng trước response; xác minh retry không tạo charge thứ hai.

### Ví dụ 5: Batch có một record lỗi làm xử lý lặp toàn bộ

Function nhận batch 100 message. 99 message được xử lý thành công, một message lỗi do payload không hợp lệ. Event source giao lại cả batch; 99 message đầu chạy lại.

**Nguyên nhân:** không có per-record idempotency hoặc partial batch response.

**Thiết kế lại:** lưu trạng thái theo message/business ID; bật partial batch failure nếu event source hỗ trợ; chuyển poison record vào DLQ theo policy. Giữ kết quả của 99 record đã commit để lần giao lại không tạo side effect mới.

## 17. Những sai lầm thường gặp

- **Đặt function timeout bằng gateway timeout:** function có thể tiếp tục chạy sau khi caller bỏ cuộc.
- **Đặt timeout lớn cho mọi dependency:** một dependency treo giữ toàn bộ execution lâu hơn cần thiết.
- **Retry mọi exception:** lỗi validation và quyền truy cập không tự biến mất.
- **Retry ở nhiều tầng:** số lần gọi downstream tăng theo cấp số nhân.
- **Retry ngay lập tức:** tạo thundering herd khi dependency vừa phục hồi.
- **Không giới hạn tổng thời gian retry:** function hết deadline giữa chừng mà không lưu trạng thái.
- **Coi timeout là rollback:** thao tác từ xa có thể đã commit dù response bị mất.
- **Dedupe bằng cache dễ mất:** cache flush có thể làm event cũ được xử lý lại.
- **Ghi dedupe sau side effect:** crash window tạo tác động trùng.
- **Tạo idempotency key mới mỗi lần retry:** mỗi lần thử bị coi là nghiệp vụ mới.
- **TTL dedupe quá ngắn:** redrive/replay đến sau khi key hết hạn.
- **Chỉ dedupe cấp batch:** một record lặp có thể làm lặp toàn bộ batch.
- **Visibility timeout quá ngắn:** hai worker cùng xử lý một message.
- **DLQ không có owner:** message lỗi tồn tại nhưng không được xử lý.
- **Redrive toàn bộ cùng lúc:** gây quá tải dependency và tái tạo retry storm.
- **Không phân biệt duplicate với out-of-order:** trạng thái nghiệp vụ có thể bị ghi đè sai thứ tự.

## 18. Checklist vận hành

### Timeout và deadline

- [ ] Đã xác định deadline nghiệp vụ và timeout ở từng lớp.
- [ ] Tổng timeout budget nằm trong deadline, có headroom cleanup/response.
- [ ] Timeout dependency dựa trên latency percentile và tải thực tế.
- [ ] Function không giữ execution quá lâu khi dependency treo.
- [ ] Cancellation không được hiểu nhầm là rollback thao tác từ xa.

### Retry và backoff

- [ ] Đã phân loại transient, throttling, permanent và unknown outcome.
- [ ] Chỉ retry thao tác an toàn hoặc có idempotency.
- [ ] Retry có max attempts, deadline và retry budget.
- [ ] Backoff có cap và jitter.
- [ ] Tôn trọng Retry-After khi phù hợp.
- [ ] Tránh retry đồng thời ở nhiều tầng mà không có giới hạn tổng.

### Duplicate và state

- [ ] Event có ID hoặc idempotency key ổn định.
- [ ] Dedupe store có unique/conditional write atomic.
- [ ] Dedupe và thay đổi nghiệp vụ được commit cùng transaction khi có thể.
- [ ] Side effect ngoài có idempotency key hoặc quy trình đối soát.
- [ ] Cùng key nhưng payload khác được xử lý như conflict.
- [ ] TTL phù hợp với retry, retention, redrive và replay.
- [ ] Có cơ chế xử lý event đến sai thứ tự nếu nghiệp vụ yêu cầu.

### Queue, DLQ và quan sát

- [ ] Visibility timeout/lease đủ cho thời gian xử lý và có gia hạn nếu cần.
- [ ] Batch failure xử lý ở cấp record khi event source hỗ trợ.
- [ ] DLQ có retention, encryption, owner và cảnh báo.
- [ ] Redrive có kiểm soát tốc độ và giữ nguyên idempotency key.
- [ ] Theo dõi timeout, retry, duplicate, queue age, DLQ và dependency throttling.
- [ ] Log có correlation ID nhưng không chứa secret hoặc payload nhạy cảm.

### Kiểm thử

- [ ] Đã test mất response sau khi side effect commit.
- [ ] Đã test duplicate đồng thời và tuần tự.
- [ ] Đã test crash giữa dedupe, commit và ACK.
- [ ] Đã test dependency 429/503 và retry storm.
- [ ] Đã test poison message, DLQ và redrive.
- [ ] Đã xác minh chi phí và SLO khi retry tăng.

## 19. Kết luận

Timeout xác định thời gian tối đa của một thao tác; deadline xác định giới hạn của toàn bộ luồng nghiệp vụ. Hãy chia timeout budget giữa function và dependency, không để từng lớp dùng toàn bộ deadline. Retry chỉ phù hợp với lỗi có khả năng hồi phục và phải có max attempts, backoff, jitter, retry budget cùng giới hạn thời gian.

Trong hệ thống serverless, một sự kiện có thể được giao nhiều lần vì ACK bị mất, timeout, redelivery, batch retry hoặc replay. Idempotency key ổn định, deduplication atomic, transaction, state machine và đối soát giúp ngăn tác động nghiệp vụ trùng lặp. DLQ và redrive cung cấp đường xử lý cho message không thể hoàn tất; observability và failure testing xác nhận các cơ chế này hoạt động trong điều kiện thực tế. Khi timeout, retry và idempotency được thiết kế cùng nhau, serverless workload có thể phục hồi lỗi mà vẫn bảo vệ dữ liệu, SLO và chi phí vận hành.
