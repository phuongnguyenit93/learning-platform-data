# Xử lý downstream throttling và phân bổ retry budget

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện downstream throttling và phân biệt nó với lỗi mạng, lỗi ứng dụng hoặc rate limit ở đầu vào.
- Giải thích vì sao autoscaling và retry có thể khuếch đại tải lên database, API hoặc queue.
- Phân loại lỗi có thể retry và lỗi cần dừng ngay.
- Thiết kế retry budget theo deadline của request và theo capacity của dịch vụ.
- Áp dụng exponential backoff, jitter, `Retry-After`, circuit breaker, bulkhead và rate limiter.
- Điều chỉnh concurrency, batch size và tốc độ tiêu thụ queue để bảo vệ downstream.
- Viết Java client có timeout, retry có giới hạn và idempotency.
- Quan sát retry ratio, throttling, queue age và saturation để điều chỉnh chính sách.

## 1. Downstream throttling là gì?

Downstream là dịch vụ mà function gọi đến để hoàn thành công việc: database, cache, HTTP API, object storage, message broker hoặc một service nội bộ khác. Downstream throttling xảy ra khi dịch vụ đó giới hạn hoặc từ chối một phần request vì đã chạm ngưỡng quota, concurrency, connection, throughput hoặc capacity.

Ví dụ, một Java function xử lý đơn hàng có thể gọi database để đọc tồn kho, gọi API thanh toán và publish message. Khi traffic tăng đột ngột, function scale out nhanh hơn khả năng xử lý của database. Database bắt đầu từ chối connection hoặc trả lỗi quá tải; API thanh toán có thể trả `429 Too Many Requests`; message broker có thể áp dụng quota publish.

Throttling có thể là cơ chế bảo vệ có chủ đích. Nó báo cho caller rằng tốc độ hiện tại vượt quá giới hạn mà dịch vụ chấp nhận. Nếu caller tiếp tục gửi request ở cùng tốc độ, số lỗi sẽ tăng và downstream càng khó phục hồi.

### 1.1. Những dấu hiệu thường gặp

| Dấu hiệu | Ý nghĩa có thể có |
|---|---|
| HTTP `429` | Caller vượt rate limit hoặc quota |
| HTTP `503` | Dịch vụ tạm thời quá tải hoặc không sẵn sàng |
| HTTP `Retry-After` | Server gợi ý thời điểm thử lại |
| Database connection timeout | Hết connection, pool cạn hoặc DB không nhận thêm kết nối |
| `Too many connections` | Chạm giới hạn kết nối database |
| gRPC `RESOURCE_EXHAUSTED` | Hết quota, capacity hoặc resource |
| Queue backlog tăng | Consumer không theo kịp tốc độ producer |
| Latency p95/p99 tăng cùng error rate | Downstream đang bão hòa hoặc chờ tài nguyên |
| Throttling chỉ xuất hiện khi scale out | Tốc độ tăng của function vượt khả năng downstream |

Không phải mọi `429` hay `503` đều có cùng nguyên nhân. Hãy đọc response body, error code, provider metric và log của dịch vụ đích. Ví dụ, một API có thể dùng `429` cho quota theo project, theo user hoặc theo endpoint; cách khôi phục có thể khác nhau.

### 1.2. Throttling khác với lỗi ứng dụng

- **Lỗi input hoặc validation:** request không hợp lệ; gửi lại cùng dữ liệu thường vẫn lỗi.
- **Lỗi authorization:** thiếu quyền hoặc token không hợp lệ; retry liên tục không tự cấp quyền.
- **Throttling:** request có thể hợp lệ nhưng tốc độ hoặc mức đồng thời vượt giới hạn.
- **Lỗi mạng:** có thể là lỗi tạm thời, nhưng cũng có thể do DNS, route hoặc firewall cấu hình sai.
- **Lỗi server:** `5xx` có thể tạm thời hoặc kéo dài; cần phân loại theo mã lỗi và hợp đồng của API.

Retry chỉ có ích khi lỗi có khả năng tự hết trong khoảng thời gian hợp lý. Retry lỗi cấu hình, dữ liệu sai hoặc quyền bị từ chối chỉ tiêu tốn tài nguyên và làm log nhiễu.

### 1.3. Mô hình request qua nhiều tầng

~~~mermaid
flowchart LR
    A[Client] --> B[HTTP Java function]
    B --> C[Order service]
    C --> D[Inventory database]
    C --> E[Payment API]
    C --> F[Message broker]
    D --> G[Throttling / quota]
    E --> G
    F --> G
~~~

Function có thể nhận request thành công nhưng vẫn thất bại ở một dependency. Cần đo từng downstream riêng; một metric tổng `function errors` không đủ để biết dependency nào gây nghẽn.

## 2. Vì sao serverless có thể khuếch đại tải?

Serverless có thể tạo thêm instance khi request tăng. Khả năng scale này giúp xử lý burst, nhưng downstream thường có giới hạn cố định hoặc tăng chậm hơn. Nếu mỗi invocation mở nhiều kết nối, tải lên dependency có thể tăng nhanh hơn số request đầu vào.

### 2.1. Fan-out làm tăng số request

Giả sử mỗi invocation gọi 3 downstream, và mỗi downstream nhận 2 request. Với 100 invocation đồng thời, tổng số lời gọi dependency có thể là:

\[
100 \times 3 \times 2 = 600
\]

Nếu một dependency chỉ chịu được 150 request đồng thời, function có thể đẩy nó vào trạng thái throttling dù mỗi invocation riêng lẻ có vẻ nhẹ.

### 2.2. Retry làm tăng tải thêm lần nữa

Giả sử có 1.000 request ban đầu và 20% request thất bại tạm thời. Nếu tất cả request lỗi đều được retry 3 lần, số lần gọi bổ sung tối đa là:

\[
1.000 \times 20\% \times 3 = 600
\]

Downstream phải nhận tới 1.600 lần gọi thay vì 1.000. Nếu các lần retry tiếp tục thất bại, tải tăng trong lúc dịch vụ đang yếu nhất.

Đây là *retry amplification*. Khi nhiều function instance cùng retry theo một lịch cố định, chúng có thể tạo thành retry storm: một đợt request mới đồng loạt đổ vào downstream sau mỗi khoảng chờ.

### 2.3. Little's Law và số request đang chạy

Một quan hệ hữu ích để hiểu concurrency là Little's Law:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống.
- \(\lambda\): tốc độ request hoàn tất hoặc đi vào hệ thống (request/giây).
- \(W\): thời gian trung bình một request ở trong hệ thống (giây).

Nếu downstream chậm hơn, \(W\) tăng. Với cùng tốc độ đầu vào, số request đang chờ và giữ connection tăng theo. Nếu function tiếp tục scale hoặc mở thêm connection, downstream có thể bị bão hòa nhanh hơn.

Ví dụ, 200 request/giây với thời gian xử lý trung bình 0,1 giây tương ứng khoảng 20 request đang chạy. Nếu latency tăng lên 2 giây, số request đang chạy có thể lên khoảng 400. Đây là lý do cần kiểm soát concurrency, timeout và queue depth cùng lúc.

### 2.4. Connection pool có thể khuếch đại tải

Giả sử mỗi instance Java mở pool 20 database connection. Nếu function scale lên 30 instance, tổng pool có thể cho phép tới 600 connection. Database có thể chỉ hỗ trợ 250 connection cho ứng dụng đó.

Một pool lớn không làm database nhanh hơn. Hãy tính:

\[
\text{Potential connections}
= \text{max instances} \times \text{pool size per instance}
\]

Cộng thêm connection của các service khác, migration, admin tool và worker. Cấu hình pool phải phù hợp với giới hạn thực tế của database.

## 3. Phân loại lỗi trước khi retry

Retry policy cần dựa trên semantics của lỗi và thao tác. Không nên viết một vòng lặp bắt mọi exception rồi thử lại.

### 3.1. Lỗi thường có thể retry

Tùy API contract, các trường hợp sau có thể là transient:

- HTTP `429` hoặc mã quota tương ứng.
- HTTP `500`, `502`, `503`, `504` khi dịch vụ xác nhận đây là lỗi tạm thời.
- gRPC `UNAVAILABLE` hoặc `RESOURCE_EXHAUSTED` khi quota/capacity có thể hồi phục.
- Kết nối bị reset hoặc timeout trong lúc gọi dependency.
- Database deadlock hoặc lỗi transaction tạm thời.
- Lỗi broker tạm thời khi publish/consume.

Với throttling, hãy ưu tiên `Retry-After` nếu server gửi header này. Không tự giả định mọi mã `5xx` đều retry được; ví dụ lỗi do request không được hỗ trợ có thể không thay đổi sau khi thử lại.

### 3.2. Lỗi không nên retry mù quáng

- HTTP `400` do payload sai.
- HTTP `401` khi credential/token không hợp lệ.
- HTTP `403` khi principal không có quyền.
- HTTP `404` khi resource không tồn tại và không có lý do cho thấy nó sẽ xuất hiện ngay.
- Lỗi parse/schema hoặc lỗi nghiệp vụ vĩnh viễn.
- Certificate hostname mismatch hoặc TLS trust failure do cấu hình.
- DNS/route/firewall sai kéo dài.
- Request vượt giới hạn kích thước cố định.

Một số lỗi có thể cần hành động sửa chữa rồi mới thử lại. Ví dụ, `401` có thể được retry một lần sau khi refresh token nếu API client có cơ chế refresh hợp lệ. Đó là một chính sách riêng, không phải retry tổng quát cho mọi `401`.

### 3.3. Ma trận quyết định

| Tình huống | Hành động gợi ý |
|---|---|
| `429` kèm `Retry-After` | Chờ theo header, giới hạn bởi deadline và retry budget |
| `429` không có header | Exponential backoff + jitter, số lần giới hạn |
| `503` tạm thời | Retry có giới hạn nếu thao tác an toàn |
| Timeout trước khi biết server đã nhận request chưa | Chỉ retry nếu thao tác idempotent hoặc có idempotency key |
| `400` validation | Dừng retry, trả lỗi input |
| `401`/`403` | Sửa credential hoặc permission; không retry liên tục |
| `404` | Theo semantics API; mặc định không retry |
| Database deadlock | Retry transaction có giới hạn nếu toàn transaction có thể chạy lại |
| Downstream mất kết nối kéo dài | Mở circuit, giảm tải hoặc đưa việc vào queue |

## 4. Retry budget là gì?

Retry budget là giới hạn lượng công việc bổ sung mà hệ thống cho phép dùng để thử lại các thao tác thất bại. Nó ngăn retry tiêu thụ toàn bộ capacity trong lúc downstream đang gặp sự cố.

Có thể quản lý budget ở nhiều phạm vi:

1. **Per request:** mỗi request chỉ được retry một số lần và phải hoàn tất trong deadline.
2. **Per dependency:** tổng số retry đến một downstream bị giới hạn theo tỷ lệ hoặc token bucket.
3. **Per service/worker:** giới hạn tổng retry của toàn bộ instance hoặc consumer group.
4. **System-wide:** phối hợp giới hạn giữa nhiều service để tránh mỗi tầng tự retry làm khuếch đại tải.

Một giới hạn `maxAttempts=3` chỉ là per-request cap. Nếu một triệu request đồng thời đều được retry ba lần, downstream vẫn có thể nhận thêm hai triệu lời gọi. Vì vậy, production thường cần cả giới hạn từng request lẫn budget ở cấp dịch vụ.

### 4.1. Budget theo request và deadline

Mỗi request nên có:

- Deadline end-to-end do caller đặt hoặc service xác định.
- Số attempt tối đa.
- Thời gian tối đa cho một lần gọi dependency.
- Khoảng thời gian dự trữ để xử lý kết quả, ghi log và trả response.

Ví dụ, caller có deadline 3 giây. Function đã dùng 1 giây để validate và đọc dữ liệu; dependency có timeout 1 giây. Khi lần gọi đầu timeout sau 1 giây, chỉ còn khoảng 1 giây. Nếu backoff 2 giây rồi retry, request chắc chắn vượt deadline.

Không bắt đầu attempt mới nếu thời gian còn lại không đủ cho backoff, connect timeout và thời gian xử lý tối thiểu.

### 4.2. Budget theo dependency

Một chính sách có thể giới hạn retry ratio:

\[
\text{Retry ratio}
= \frac{\text{Số lần gọi retry}}{\text{Số lần gọi ban đầu}}
\]

Ví dụ, tổ chức đặt mục tiêu retry ratio tối đa 10% trong một cửa sổ thời gian. Nếu có 10.000 lời gọi ban đầu, chỉ cho phép tối đa khoảng 1.000 lời gọi retry trong cửa sổ đó. Đây là ví dụ để minh họa cách định nghĩa budget; ngưỡng thật cần dựa trên capacity và SLA của downstream.

Khi budget hết:

- Không tiếp tục retry ngay.
- Trả lỗi có kiểm soát cho caller hoặc đưa message vào queue/DLQ theo semantics.
- Có thể mở circuit breaker để ngăn lời gọi mới trong một khoảng thời gian.
- Ghi metric về budget exhaustion để đội vận hành biết downstream đang chịu áp lực.

### 4.3. Token bucket cho retry budget

Một cách triển khai là token bucket:

- Bucket có capacity giới hạn.
- Token được bổ sung theo tốc độ định trước hoặc khi có request gốc thành công.
- Mỗi retry tiêu thụ một token.
- Nếu không còn token, dừng retry và áp dụng fallback.

Ví dụ, mỗi 10 request gốc thành công bổ sung một token retry, bucket tối đa 20 token. Điều này giới hạn tốc độ retry tương đối với lượng traffic thành công và cho phép một burst retry nhỏ. Quy tắc bổ sung token phải được thiết kế cẩn thận; nếu chỉ bổ sung theo success, khi downstream phục hồi sẽ dần khôi phục budget mà không tạo burst quá lớn.

Token bucket có thể nằm trong process cho một instance, nhưng khi có nhiều instance thì mỗi instance có bucket riêng và tổng budget có thể nhân lên theo số instance. Nếu cần giới hạn toàn hệ thống, dùng rate limiter phân tán hoặc quota ở gateway/downstream, hoặc chia budget rõ ràng cho từng instance.

### 4.4. Phân bổ budget qua nhiều tầng

Một request có thể đi qua API gateway, function, application service và SDK. Nếu mỗi tầng tự retry 3 lần, số lời gọi cuối có thể nhân lên theo cấp số nhân:

\[
3 \times 3 \times 3 = 27
\]

Hãy chọn một tầng chịu trách nhiệm retry chính cho từng dependency. Các tầng còn lại nên truyền deadline và lỗi lên trên, hoặc chỉ retry các lỗi riêng mà tầng đó hiểu rõ. Kiểm tra retry mặc định trong SDK, database driver, HTTP client và service mesh; tránh vô tình bật nhiều lớp retry chồng nhau.

~~~mermaid
flowchart TD
    A[Caller deadline] --> B[Function request budget]
    B --> C[Dependency attempt timeout]
    C --> D[Retry budget token]
    D -->|Token available| E[Backoff and retry]
    D -->|Budget exhausted| F[Fail fast / queue / fallback]
~~~

## 5. Exponential backoff và jitter

Exponential backoff tăng dần khoảng chờ giữa các lần thử lại. Jitter thêm độ ngẫu nhiên để các client không retry đồng loạt.

### 5.1. Công thức backoff

Một dạng full jitter phổ biến:

\[
d_n \sim U(0,\min(d_{\max},d_0 \times 2^{n-1}))
\]

Trong đó:

- \(d_n\): thời gian chờ trước lần retry thứ \(n\).
- \(d_0\): khoảng chờ ban đầu.
- \(d_{\max}\): giới hạn tối đa.
- \(U(0,x)\): chọn ngẫu nhiên đều trong khoảng từ 0 đến \(x\).

Ví dụ, base delay 200 ms, cap 5 giây:

| Lần retry | Cửa sổ chờ tối đa | Full jitter chọn |
|---:|---:|---|
| 1 | 200 ms | Ngẫu nhiên 0–200 ms |
| 2 | 400 ms | Ngẫu nhiên 0–400 ms |
| 3 | 800 ms | Ngẫu nhiên 0–800 ms |
| 4 | 1.600 ms | Ngẫu nhiên 0–1.600 ms |
| 5 | 3.200 ms | Ngẫu nhiên 0–3.200 ms |
| 6 trở đi | 5.000 ms | Ngẫu nhiên 0–5.000 ms |

Jitter làm phân tán thời điểm retry giữa các instance. Không dùng một khoảng cố định như 1 giây cho mọi client; sau một đợt lỗi, tất cả có thể gửi lại đúng cùng thời điểm.

### 5.2. Tôn trọng Retry-After

Nếu HTTP response có header `Retry-After`, server có thể cung cấp số giây hoặc ngày giờ HTTP để client thử lại. Client nên:

1. Parse header theo định dạng được hỗ trợ.
2. Không retry trước thời điểm server yêu cầu.
3. Kiểm tra thời gian còn lại trong deadline.
4. Giới hạn thời gian chờ theo chính sách của ứng dụng.
5. Nếu thời gian chờ vượt deadline, trả lỗi hoặc đưa công việc sang xử lý bất đồng bộ.

Không cộng một khoảng jitter âm khiến client retry sớm hơn `Retry-After`. Có thể thêm jitter dương nhỏ sau thời điểm đó để tránh nhiều client cùng thức dậy một lúc, miễn vẫn còn trong deadline và budget.

### 5.3. Đặt giới hạn cho backoff

Backoff cần có:

- Base delay đủ nhỏ để không lãng phí deadline.
- Cap để thời gian chờ không tăng vô hạn.
- Số lần retry tối đa.
- Deadline tổng cho toàn bộ operation.
- Jitter để tránh đồng bộ hóa.
- Quy tắc riêng cho server gửi `Retry-After`.

Backoff không làm downstream tăng capacity. Nó chỉ giảm tốc độ retry và cho dịch vụ thời gian phục hồi. Nếu lỗi kéo dài, circuit breaker, queue hoặc fail-fast phù hợp hơn.

## 6. Deadline, timeout và retry phải được tính cùng nhau

Timeout của một lần gọi dependency khác với deadline của toàn bộ request. Deadline là thời điểm muộn nhất mà caller còn chấp nhận kết quả. Từng attempt, backoff và xử lý sau cùng đều phải nằm trong ngân sách đó.

### 6.1. Ngân sách thời gian

Ví dụ một HTTP request có deadline 5 giây:

| Công đoạn | Ngân sách |
|---|---:|
| Validate và chuẩn bị | 300 ms |
| Attempt 1 | 1.000 ms |
| Backoff 1 | 200 ms |
| Attempt 2 | 1.000 ms |
| Backoff 2 | 400 ms |
| Attempt 3 | 1.000 ms |
| Serialize và trả response | 300 ms |
| Dự phòng | 800 ms |

Tổng thời gian phải nhỏ hơn hoặc bằng deadline. Nếu attempt đầu đã dùng hết phần lớn ngân sách, không nên cố thực hiện mọi retry đã cấu hình sẵn.

### 6.2. Truyền deadline xuống dependency

Khi một service gọi service khác, truyền deadline hoặc timeout còn lại thay vì mỗi tầng tự đặt một timeout dài độc lập. Với HTTP, có thể truyền deadline qua context/header theo contract nội bộ. Với gRPC, dùng deadline của RPC. Không tin một deadline do client gửi nếu nó không được validate và giới hạn theo SLA của service.

### 6.3. Tránh timeout chồng lấn

Một request có thể có timeout ở load balancer, API Gateway, function runtime, HTTP client, database driver và query. Hãy sắp xếp chúng:

- Timeout của dependency nhỏ hơn thời gian còn lại của function.
- Timeout của function nhỏ hơn hoặc bằng deadline của caller theo thiết kế.
- Timeout của database query nằm trong ngân sách dành cho database.
- Retry phải kết thúc trước khi function hết thời gian.
- Dành thời gian cho commit transaction, log và response.

Nếu caller timeout trước nhưng function vẫn tiếp tục retry và commit side effect, caller có thể gửi lại request vì không nhận được response. Idempotency là cần thiết để bảo vệ tác động nghiệp vụ trong tình huống này.

## 7. Các cơ chế bảo vệ downstream

Retry chỉ là một phần của kiểm soát tải. Cần kết hợp với cơ chế giới hạn tốc độ, concurrency và cách xử lý khi dependency không khỏe.

### 7.1. Rate limiter

Rate limiter giới hạn số request theo thời gian. Token bucket cho phép burst nhỏ nhưng giữ tốc độ trung bình trong giới hạn. Có thể áp dụng ở API Gateway, service, worker hoặc client.

Ví dụ, một API thanh toán chấp nhận 100 request/giây. Function có thể dùng limiter để phát tối đa 80 request/giây, giữ phần headroom cho traffic khác và dao động. Con số thật phải dựa trên quota và phân bổ giữa các caller.

Nếu có nhiều function instance, limiter local trên mỗi instance không giới hạn được tổng tốc độ. Ví dụ 10 instance, mỗi instance 80 request/giây có thể tạo ra 800 request/giây. Dùng limiter phân tán, quota ở gateway, queue hoặc phân bổ quota theo instance.

### 7.2. Concurrency limiter và bulkhead

Concurrency limiter giới hạn số lời gọi đang chạy đồng thời đến một dependency. Bulkhead chia tài nguyên theo dependency để một hệ thống chậm không chiếm hết thread, connection hoặc worker của toàn function.

Ví dụ:

- Payment API: tối đa 20 request đồng thời.
- Inventory database: tối đa 40 query đồng thời.
- Email provider: tối đa 10 request đồng thời.

Các giới hạn này phải tính trên tổng instance. Nếu mỗi instance cho phép 20 request và có 15 instance, downstream có thể nhận 300 request đồng thời. Cần phối hợp với max instances hoặc limiter tập trung.

### 7.3. Circuit breaker

Circuit breaker theo dõi lỗi/timeout của dependency:

- **Closed:** request được phép đi qua.
- **Open:** tạm dừng gọi dependency khi lỗi vượt ngưỡng.
- **Half-open:** cho một số probe request đi qua để kiểm tra phục hồi.

Circuit breaker giúp fail-fast và ngăn tạo thêm request vào dịch vụ đang quá tải. Nó không thay thế retry budget: khi circuit mở, retry cũng phải dừng. Cần tránh cấu hình mọi instance cùng probe dồn dập; jitter hoặc probe quota giúp giảm tải khi circuit chuyển sang half-open.

### 7.4. Load shedding và fallback

Khi hệ thống gần bão hòa, có thể từ chối sớm một phần request ít quan trọng thay vì để tất cả request timeout. Trả HTTP 429 hoặc 503 có hướng dẫn retry phù hợp; nếu có Retry-After, cung cấp thời điểm thử lại.

Fallback có thể là cache, dữ liệu gần nhất, kết quả một phần hoặc đưa công việc vào queue. Không dùng fallback nếu nó làm sai nghiệp vụ, ví dụ xác nhận thanh toán thành công khi payment provider chưa xác nhận.

### 7.5. Queue để hấp thụ burst

Queue tách tốc độ nhận việc khỏi tốc độ xử lý:

~~~mermaid
flowchart LR
    A[HTTP request] --> B[Validate and enqueue]
    B --> C[Queue]
    C --> D[Worker function]
    D --> E[Downstream API / database]
    D -->|Transient failure| C
    D -->|Permanent failure| F[DLQ / quarantine]
~~~

Queue cho phép worker xử lý theo concurrency và tốc độ phù hợp với downstream. Đổi lại, ứng dụng phải chấp nhận xử lý bất đồng bộ, theo dõi queue age, thiết kế idempotency và cung cấp trạng thái job cho caller.

### 7.6. Batch và cache

Batch có thể giảm số request đến downstream nếu dịch vụ hỗ trợ bulk API. Tuy nhiên, batch quá lớn làm tăng latency, memory và phạm vi retry. Nếu một item lỗi, cần biết có thể retry toàn batch hay chỉ item lỗi.

Cache giảm số lần đọc lặp. Cần xác định TTL, invalidation và tính nhất quán. Cache không giải quyết được mọi throttling, đặc biệt với thao tác ghi hoặc dữ liệu cần tính chính xác ngay lập tức.

## 8. Retry an toàn với side effect và idempotency

Retry một thao tác đọc thường an toàn hơn retry một thao tác ghi. Nếu server đã xử lý request nhưng response bị mất, client không biết thao tác đã thành công hay chưa.

### 8.1. Vì sao timeout có thể tạo side effect trùng?

Ví dụ, function gửi lệnh tạo thanh toán. Payment provider đã tạo giao dịch, nhưng response bị mất do network timeout. Function retry với request mới và provider tạo giao dịch thứ hai.

Không thể kết luận thao tác thất bại chỉ vì client không nhận được response. Trạng thái có thể là *unknown outcome*.

### 8.2. Idempotency key

Với API hỗ trợ idempotency, tạo key ổn định cho cùng một nghiệp vụ và gửi lại key đó trên mọi attempt. Provider lưu kết quả theo key để request lặp không tạo side effect mới.

Ví dụ:

~~~java
HttpRequest request = HttpRequest.newBuilder(paymentUri)
        .header("Idempotency-Key", orderPaymentId)
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(payload))
        .build();
~~~

Key phải đại diện cho một operation nghiệp vụ, không tạo UUID mới ở mỗi lần retry. Nếu mỗi attempt dùng key khác, server không thể nhận ra đó là cùng một operation.

### 8.3. Idempotency trong database

Nếu không có idempotency API từ downstream, có thể lưu operation key với unique constraint trong database. Việc claim key, thay đổi trạng thái và ghi kết quả cần có transaction hoặc giao thức nhất quán.

Một mẫu trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `NEW` | Chưa xử lý |
| `IN_PROGRESS` | Worker đã claim |
| `SUCCEEDED` | Tác động đã hoàn tất |
| `FAILED_PERMANENT` | Lỗi không thể retry |
| `RETRYABLE` | Có thể thử lại sau |

Cần xử lý lease/timeout cho `IN_PROGRESS` nếu worker chết giữa chừng. Nếu side effect ở hệ thống ngoài, dùng idempotency key tại hệ thống đó, outbox/inbox pattern hoặc đối soát để giải quyết trạng thái không xác định.

### 8.4. Delivery semantics

Event source thường có thể giao lại message nếu consumer không xác nhận thành công. Vì vậy, event-driven function nên được thiết kế theo hướng at-least-once khi dịch vụ cung cấp semantics này. Không giả định exactly-once end-to-end chỉ vì broker có tính năng deduplication; side effect ở database/API ngoài vẫn cần idempotency.

## 9. Áp dụng retry budget cho queue và event function

Queue giúp kiểm soát tốc độ xử lý, nhưng retry sai cách vẫn có thể làm backlog và downstream tăng tải.

### 9.1. AWS Lambda với Amazon SQS

Khi Lambda đọc SQS, event source mapping poll queue và gọi function theo batch. Nếu function lỗi, message có thể được giao lại sau visibility timeout. Cần cấu hình:

- Batch size phù hợp với thời gian xử lý và memory.
- Maximum concurrency hoặc giới hạn concurrency của event source mapping để bảo vệ downstream.
- Visibility timeout đủ dài cho function timeout, batch window và khả năng retry theo khuyến nghị của AWS.
- Redrive policy và DLQ cho message lỗi kéo dài.
- Partial batch response để chỉ trả lại các message thất bại khi batch có xử lý thành công một phần.
- Idempotency cho từng message, không chỉ cho cả batch.

Nếu không dùng partial batch response, một message lỗi có thể khiến cả batch được giao lại, làm những message đã xử lý thành công chạy lặp. Với batch, hãy phân biệt lỗi retryable của từng message và lỗi vĩnh viễn cần quarantine.

### 9.2. Google Cloud Pub/Sub và Eventarc

Với Pub/Sub, subscription quyết định ack deadline, retry policy và dead-letter topic. Consumer cần ack sau khi xử lý bền vững. Nếu ack deadline hết trước khi xử lý xong, message có thể được giao lại khi worker trước vẫn còn chạy.

Có thể giới hạn số message outstanding và concurrency của subscriber để giữ áp lực lên downstream trong mức chịu được. Nếu dùng Cloud Run functions/Eventarc, kiểm tra retry policy, thời gian lưu giữ event và dead-letter support của trigger cụ thể. Không giả định tất cả trigger có cùng semantics.

### 9.3. Phân biệt retry trong handler và retry của broker

Nếu handler tự retry 3 lần rồi ném exception, broker có thể tiếp tục giao lại message và lặp cả 3 lần nữa. Nếu broker cũng retry nhiều lần, tổng attempt có thể tăng mạnh.

Chọn rõ:
- Retry ngắn cho lỗi transient trong một invocation nếu còn deadline.
- Để broker xử lý retry dài hơn bằng cách fail invocation có kiểm soát.
- Dùng DLQ/quarantine cho message lỗi vĩnh viễn hoặc vượt ngưỡng.
- Ghi event ID, message ID và attempt count để truy vết.
- Dùng idempotency để an toàn khi cùng message xuất hiện nhiều lần.

### 9.4. Queue age quan trọng hơn queue depth trong một số workload

Queue depth cho biết số message đang chờ; queue age cho biết message cũ nhất đã đợi bao lâu. Một queue có 10.000 message nhưng worker xử lý nhanh có thể ổn; queue có 100 message nhưng message đã chờ 30 phút có thể vi phạm SLA.

Theo dõi cả:
- Queue depth và age of oldest message.
- Message receive count/attempt count.
- DLQ depth.
- Consumer concurrency và processing duration.
- Downstream throttling và error rate.
- Tốc độ producer so với tốc độ consumer.

## 10. Ví dụ Java: retry có giới hạn và deadline

Một retry helper nên nhận operation, điều kiện retry, số attempt tối đa, deadline và retry budget. Logic này không nên tự retry mọi exception. Ứng dụng phải phân loại lỗi dựa trên contract của dependency.

### 10.1. Tạo full-jitter delay

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class Backoff {

    private Backoff() {}

    public static Duration fullJitter(
            int retryNumber,
            Duration baseDelay,
            Duration maxDelay) {

        if (retryNumber < 1) {
            throw new IllegalArgumentException("retryNumber must be >= 1");
        }

        long base = Math.max(1, baseDelay.toMillis());
        long cap = Math.max(base, maxDelay.toMillis());
        long ceiling = base;

        for (int i = 1; i < retryNumber && ceiling < cap; i++) {
            ceiling = ceiling > cap / 2 ? cap : ceiling * 2;
        }

        long delay = ThreadLocalRandom.current().nextLong(ceiling + 1);
        return Duration.ofMillis(delay);
    }
}
~~~

Hàm trên trả về một khoảng chờ ngẫu nhiên từ 0 đến cửa sổ exponential đã bị cap. Nó chỉ tính delay; caller vẫn phải kiểm tra deadline, retry budget và Retry-After.

### 10.2. Retry budget interface

~~~java
public interface RetryBudget {
    // Trả true nếu còn budget và đã giữ một token cho retry này.
    boolean tryAcquire();
}
~~~

Một implementation local có thể dùng token bucket thread-safe. Tuy nhiên, nếu function scale ra nhiều instance, mỗi instance có budget riêng. Muốn giới hạn tổng retry của một dependency trên toàn hệ thống, cần budget phân tán, quota ở gateway hoặc phân bổ quota theo instance.

### 10.3. Vòng lặp retry có deadline

Ví dụ sau minh họa cấu trúc điều khiển. operation phải tự đặt timeout cho một attempt; retryable chỉ chấp nhận lỗi transient đã xác định:

~~~java
import java.time.Duration;
import java.util.concurrent.Callable;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Predicate;

public final class RetryExecutor {

    private RetryExecutor() {}

    public static <T> T execute(
            Callable<T> operation,
            Predicate<Exception> retryable,
            RetryBudget budget,
            int maxAttempts,
            long deadlineNanos,
            Duration baseDelay,
            Duration maxDelay) throws Exception {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }

        Exception lastFailure = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            if (deadlineNanos - System.nanoTime() <= 0) {
                break;
            }

            try {
                return operation.call();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw interrupted;
            } catch (Exception failure) {
                lastFailure = failure;

                boolean canRetry =
                        retryable.test(failure)
                        && attempt < maxAttempts
                        && budget.tryAcquire();

                if (!canRetry) {
                    throw failure;
                }

                long remaining = deadlineNanos - System.nanoTime();
                long delay = Backoff.fullJitter(
                        attempt, baseDelay, maxDelay).toNanos();

                if (delay >= remaining) {
                    throw failure;
                }

                try {
                    TimeUnit.NANOSECONDS.sleep(delay);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw interrupted;
                }
            }
        }

        if (lastFailure != null) {
            throw lastFailure;
        }

        throw new TimeoutException("Request deadline exhausted");
    }
}
~~~

Các điểm cần giữ đúng khi tích hợp:

- `maxAttempts` bao gồm cả lần gọi đầu tiên.
- Mỗi lần gọi dependency phải có connect/read/request timeout nhỏ hơn thời gian còn lại.
- `retryable` không được trả true cho mọi exception.
- `budget.tryAcquire()` chỉ được gọi khi thật sự chuẩn bị retry.
- Delay phải nằm trong deadline; nếu không, dừng và trả lỗi.
- `InterruptedException` không được nuốt; để luồng bị interrupt dừng đúng cách.
- Nếu server gửi `Retry-After`, thay logic delay để không thử lại trước thời điểm server yêu cầu, đồng thời vẫn kiểm tra deadline.
- Không dùng helper này để retry thao tác ghi nếu chưa có idempotency.

### 10.4. Phân loại HTTP response

Một HTTP client nên phân loại response theo contract của API. Ví dụ:

~~~java
static boolean isRetryableStatus(int statusCode) {
    return statusCode == 429
            || statusCode == 500
            || statusCode == 502
            || statusCode == 503
            || statusCode == 504;
}
~~~

Đây chỉ là ví dụ cho một API có contract cho phép retry các status trên. Một số dịch vụ dùng mã lỗi khác hoặc quy định riêng. Hãy kiểm tra response body và header, đặc biệt với 429/503.

### 10.5. Không xếp retry trong retry

Nếu HTTP SDK đã retry nội bộ 3 lần, đừng bọc nó bằng một retry helper khác cũng chạy 3 lần mà không tính tổng số attempt. Tổng số lời gọi có thể lên 9. Cần đọc cấu hình retry của SDK, driver database và service client; chọn một nơi quản lý budget chính.

## 11. Thiết kế retry theo loại operation

Không phải mọi request đều cần cùng chính sách. Cần phân biệt thao tác đọc, ghi, event delivery và công việc dài.

| Loại operation | Retry gợi ý | Điều kiện quan trọng |
|---|---|---|
| HTTP GET đọc dữ liệu | Có thể retry transient | Timeout, deadline, rate limit |
| HTTP POST tạo giao dịch | Chỉ retry khi có idempotency | Key ổn định và provider hỗ trợ |
| Database read | Retry transient có giới hạn | Connection/query timeout |
| Database transaction ghi | Retry toàn transaction khi lỗi phù hợp | Transaction có thể chạy lại, tránh side effect ngoài |
| Publish message | Retry theo SDK/broker | Message ID hoặc idempotency key |
| Consume message | Broker redelivery + DLQ | Ack sau commit, handler idempotent |
| Gửi email | Có thể tạo email trùng nếu timeout không rõ kết quả | Idempotency hoặc trạng thái gửi |
| Gọi API không idempotent | Thường không retry mù quáng | Cần tra cứu trạng thái hoặc idempotency contract |

Nếu thao tác không idempotent và downstream không hỗ trợ idempotency key, một timeout có thể để lại trạng thái không xác định. Thay vì gửi lại ngay, có thể truy vấn trạng thái operation bằng business ID trước khi quyết định tiếp tục.

## 12. Điều chỉnh concurrency và tốc độ tiêu thụ

Khi downstream bị throttling, giảm áp lực đầu vào thường hiệu quả hơn tăng số lần retry.

### 12.1. Giới hạn concurrency của function

Đặt max instances hoặc concurrency phù hợp với capacity của downstream. Ví dụ, nếu database chỉ dành 100 connection cho function và mỗi instance mở pool 10 connection, giới hạn lý thuyết là 10 instance; thực tế cần chừa headroom cho connection khác và burst.

Giới hạn ở platform không thay thế limiter trong ứng dụng. Một instance có thể xử lý nhiều request đồng thời và tất cả cùng gọi một API. Cần tính tổng request đồng thời qua tất cả instance.

### 12.2. Giảm batch size khi dependency quá tải

Batch size lớn có thể tăng throughput khi downstream khỏe, nhưng một batch quá lớn cũng tạo burst và làm retry phạm vi rộng. Khi throttling:

- Giảm batch size.
- Giảm maximum concurrency của consumer.
- Tăng khoảng cách poll hoặc áp dụng flow control.
- Tách loại message nặng/nhẹ nếu chúng có capacity khác nhau.
- Chỉ retry item lỗi nếu broker và event source hỗ trợ partial failure.
- Tăng dần concurrency sau khi downstream phục hồi, không bật lại toàn bộ cùng lúc.

### 12.3. Adaptive concurrency

Một hệ thống có thể điều chỉnh concurrency dựa trên latency và error rate của downstream. Khi p95/p99 hoặc throttling tăng, giảm giới hạn đồng thời; khi dịch vụ ổn định, tăng từ từ.

Không tăng concurrency chỉ vì queue depth tăng. Queue có thể tăng vì downstream đang chậm; tăng consumer lúc đó có thể làm sự cố nặng hơn. Dùng queue age, downstream saturation và success throughput để quyết định.

## 13. Quan sát retry budget và downstream health

Retry policy không thể vận hành tốt nếu không đo lường. Cần phân biệt số request gốc, số attempt và số lần retry.

### 13.1. Metrics nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| Original request count | Lượng công việc mới |
| Attempt count | Tổng số lần gọi gồm cả retry |
| Retry count và retry ratio | Mức khuếch đại tải |
| Retry budget exhausted | Số lần budget chặn retry |
| Throttling count theo dependency | Downstream nào từ chối request |
| Latency p50/p95/p99 | Thời gian đáp ứng và mức bão hòa |
| Timeout và connection errors | Vấn đề kết nối hoặc capacity |
| Circuit breaker state | Dependency đang closed/open/half-open |
| Active concurrency | Số lời gọi đang chạy |
| Connection pool utilization | Mức sử dụng pool |
| Queue depth và oldest message age | Khả năng consumer theo kịp |
| DLQ depth | Số công việc cần điều tra |

Định nghĩa retry ratio thống nhất. Có thể đo số retry trên mỗi request gốc hoặc phần trăm tổng attempt là retry; hai công thức khác nhau. Dashboard cần ghi rõ công thức để tránh hiểu sai.

### 13.2. Log có cấu trúc

Mỗi attempt nên có các trường như:

- `requestId` hoặc `traceId`.
- `dependency` và `operation`.
- `attempt` và `maxAttempts`.
- `retryReason` hoặc status/error code.
- `backoffMs` và `remainingDeadlineMs`.
- `retryBudgetAllowed`.
- `durationMs`.
- `idempotencyKey` đã được làm mờ hoặc hash nếu nhạy cảm.

Không log token, password, payload nhạy cảm hoặc toàn bộ header xác thực. Log cả lần retry bị chặn bởi budget để biết chính sách đang hoạt động.

### 13.3. Cảnh báo có ý nghĩa

Cảnh báo nên gắn với tác động nghiệp vụ, không chỉ số lỗi:

- Retry ratio vượt ngưỡng trong một cửa sổ.
- Throttling tăng liên tục ở dependency quan trọng.
- Queue age vượt SLA.
- DLQ xuất hiện message mới hoặc tăng nhanh.
- Circuit breaker mở kéo dài.
- Database connection pool gần cạn.
- Success throughput giảm dù concurrency tăng.

## 14. Quy trình xử lý khi downstream bị throttling

Khi phát hiện throttling tăng, có thể xử lý theo trình tự:

1. Xác định dependency nào bị throttling bằng metric/log riêng.
2. Kiểm tra quota, concurrency, connection pool và capacity của downstream.
3. Kiểm tra retry ratio và xem có nhiều tầng retry chồng nhau không.
4. Giảm concurrency, batch size hoặc producer rate để hạ áp lực.
5. Áp dụng backoff + jitter và tôn trọng `Retry-After`.
6. Dừng retry khi hết request deadline hoặc service retry budget.
7. Mở circuit breaker nếu lỗi kéo dài; dùng fallback hoặc trả lỗi có kiểm soát.
8. Đưa công việc có thể trì hoãn vào queue; chuyển message không thể xử lý sang DLQ theo policy.
9. Kiểm tra idempotency và trạng thái side effect trước khi redrive.
10. Tăng tải trở lại từ từ khi downstream ổn định, theo dõi success throughput và queue age.

Không redrive toàn bộ DLQ cùng lúc khi downstream chưa phục hồi. Hãy replay theo batch nhỏ, có giới hạn tốc độ và quan sát kết quả.

## 15. Kiểm thử retry và throttling

Test retry policy cần xác minh số lần gọi, tổng thời gian và side effect, không chỉ kiểm tra rằng exception cuối cùng được ném ra.

Các kịch bản nên có:

- Downstream trả 429 với `Retry-After`.
- Downstream trả 429 liên tục cho đến khi budget hết.
- 503 tạm thời rồi phục hồi.
- Timeout sau khi server đã commit side effect nhưng response bị mất.
- Lỗi 400 hoặc 403 không bị retry.
- Deadline hết trước khi có thể thực hiện attempt tiếp theo.
- Nhiều instance retry cùng lúc nhưng jitter phân tán thời điểm.
- Circuit breaker mở và chỉ cho phép probe giới hạn khi half-open.
- Queue redelivery cùng message và handler vẫn idempotent.
- Một batch có cả item thành công, retryable và permanent failure.
- Downstream phục hồi nhưng consumer không tạo retry storm.
- Retry budget phân tán vẫn giữ giới hạn khi số instance tăng.

Dùng mock server hoặc test double để điều khiển status, header và latency. Với load test, tăng tải theo từng bậc và quan sát điểm bắt đầu throttling; không chỉ đo peak throughput khi downstream khỏe.

## 16. Những lỗi thiết kế thường gặp

- **Retry mọi exception:** làm lỗi vĩnh viễn bị lặp và tăng chi phí.
- **Không có deadline:** request có thể retry lâu hơn thời gian caller chấp nhận.
- **Backoff cố định:** nhiều instance đồng bộ retry và tạo retry storm.
- **Không có jitter:** các lần retry tập trung thành burst.
- **Chỉ giới hạn attempt mỗi request:** tổng retry toàn hệ thống vẫn có thể rất lớn.
- **Retry ở mọi tầng:** số attempt nhân lên qua gateway, service và SDK.
- **Không tôn trọng Retry-After:** client tiếp tục gây tải khi server đã yêu cầu chờ.
- **Retry POST không idempotent:** có thể tạo giao dịch hoặc side effect trùng.
- **Limiter chỉ ở từng instance:** tổng tốc độ tăng theo số instance.
- **Tăng concurrency để xử lý queue backlog:** có thể làm downstream quá tải hơn.
- **Ack message trước khi ghi bền vững:** message có thể mất dù nghiệp vụ chưa hoàn tất.
- **Redrive DLQ không giới hạn:** có thể tái tạo sự cố ngay lập tức.
- **Không đo retry ratio:** không biết retry đang chiếm bao nhiêu capacity.
- **Không tính connection pool tổng:** mỗi instance hoạt động đúng nhưng tổng kết nối vượt giới hạn database.

## 17. Checklist production

- [ ] Đã phân loại lỗi transient và permanent theo contract của dependency.
- [ ] Mỗi attempt có timeout riêng và request có deadline end-to-end.
- [ ] Số attempt tối đa bao gồm lần gọi đầu tiên.
- [ ] Exponential backoff có cap và jitter.
- [ ] Tôn trọng `Retry-After` nếu server cung cấp.
- [ ] Có retry budget per request và giới hạn retry theo dependency/service.
- [ ] Không có nhiều tầng retry chồng lấn ngoài dự kiến.
- [ ] Thao tác có side effect được bảo vệ bằng idempotency key hoặc transaction.
- [ ] Có circuit breaker, bulkhead hoặc concurrency limiter khi cần.
- [ ] Rate limiter tính đến tổng số instance.
- [ ] Max instances, batch size và consumer concurrency phù hợp capacity downstream.
- [ ] Queue visibility/ack deadline, retry policy và DLQ được cấu hình đúng.
- [ ] Partial batch failure được xử lý nếu event source hỗ trợ.
- [ ] Có metric original request, attempt, retry ratio và budget exhausted.
- [ ] Có dashboard cho downstream throttling, latency, queue age và DLQ.
- [ ] Đã kiểm thử timeout sau side effect, duplicate delivery và retry storm.
- [ ] DLQ replay có tốc độ giới hạn và quy trình đối soát.

## 18. Tự kiểm tra

**Câu 1.** Vì sao retry có thể làm downstream throttling nghiêm trọng hơn?

**Gợi ý trả lời:** Retry tạo thêm request đúng lúc dependency đang quá tải. Khi nhiều instance retry cùng thời điểm hoặc nhiều tầng retry chồng nhau, tải bổ sung có thể tạo retry storm và làm dịch vụ khó phục hồi.

**Câu 2.** Retry budget khác maxAttempts thế nào?

**Gợi ý trả lời:** maxAttempts giới hạn số lần thử của một request. Retry budget còn giới hạn tổng lượng retry theo dependency, worker hoặc toàn hệ thống để ngăn tổng retry vượt capacity.

**Câu 3.** Vì sao cần jitter khi dùng exponential backoff?

**Gợi ý trả lời:** Jitter phân tán thời điểm retry giữa các client. Nếu mọi client dùng cùng lịch backoff cố định, chúng có thể đồng loạt gửi lại và tạo burst mới.

**Câu 4.** Khi nào không nên retry một POST request?

**Gợi ý trả lời:** Khi không biết server đã thực hiện side effect hay chưa và API không hỗ trợ idempotency. Cần dùng idempotency key hoặc truy vấn trạng thái operation trước khi gửi lại.

**Câu 5.** Vì sao retry budget local trên từng instance không giới hạn được tổng retry?

**Gợi ý trả lời:** Mỗi instance có bucket riêng. Khi số instance tăng, tổng token và tốc độ retry có thể tăng theo. Muốn giới hạn toàn hệ thống cần budget phân tán, quota tập trung hoặc phân bổ quota theo instance.

**Bài tập tình huống:** Một Java function nhận 500 HTTP request/giây. Mỗi invocation gọi API thanh toán và database. API thanh toán giới hạn 100 request/giây và trả 429 kèm Retry-After; database bắt đầu từ chối connection khi tổng connection vượt 200. Function autoscale lên 30 instance, mỗi instance mở pool 10 connection. Hãy thiết kế retry budget, backoff, concurrency limit, connection pool, queue/fallback và metric. Nêu cách xử lý request đã thanh toán nhưng response bị timeout.

**Gợi ý:** Tổng pool tiềm năng là 30 × 10 = 300 connection, vượt giới hạn 200. Cần giảm pool mỗi instance hoặc giới hạn max instances/concurrency sao cho tổng connection có headroom. API thanh toán chỉ nhận 100 request/giây, nên rate limit toàn hệ thống hoặc queue worker phải giữ tốc độ dưới quota, không dựa vào limiter local không đồng bộ. Khi nhận 429, tôn trọng Retry-After, thêm jitter dương nếu còn deadline và chỉ retry khi còn budget. Với thao tác thanh toán, dùng idempotency key ổn định theo payment operation; khi timeout chưa rõ kết quả, tra cứu trạng thái bằng key trước khi tạo request mới. Theo dõi retry ratio, 429 count, payment latency, connection pool utilization, DB errors, queue age và DLQ.

## Kết luận

Downstream throttling là tín hiệu cho thấy tốc độ hoặc concurrency của caller vượt khả năng tiếp nhận của dependency. Retry không giới hạn có thể khuếch đại tải, kéo dài sự cố và tạo side effect trùng. Một chính sách vững chắc kết hợp phân loại lỗi, deadline, timeout mỗi attempt, exponential backoff có jitter, Retry-After, retry budget theo request và theo dependency, cùng concurrency/rate limit. Với event và thao tác ghi, idempotency, ack sau khi commit và DLQ là điều kiện quan trọng. Quan sát retry ratio, throttling, queue age, connection pool và success throughput giúp điều chỉnh tải theo capacity thực tế của downstream.
