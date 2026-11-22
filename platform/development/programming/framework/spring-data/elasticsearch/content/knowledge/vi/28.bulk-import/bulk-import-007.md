# Backoff, jitter và giới hạn số yêu cầu đồng thời

Khi nhập dữ liệu hàng loạt vào Elasticsearch, ứng dụng có thể gửi nhiều bulk request cùng lúc để tăng throughput. Nếu tốc độ gửi vượt khả năng xử lý của cluster, hàng đợi write có thể đầy và Elasticsearch từ chối một phần hoặc toàn bộ request. Client tiếp tục retry ngay lập tức sẽ tạo thêm tải, khiến cluster càng khó phục hồi.

Ba cơ chế cần phối hợp để điều khiển luồng nhập liệu:

- **Backoff**: tăng thời gian chờ giữa các lần retry để giảm áp lực lên cluster.
- **Jitter**: thêm độ ngẫu nhiên vào thời gian chờ để nhiều client không retry đồng loạt.
- **Concurrency limit**: giới hạn số bulk request đang chạy cùng lúc để kiểm soát lượng công việc được đưa vào hệ thống.

Chỉ dùng backoff mà không giới hạn concurrency vẫn có thể tạo quá nhiều request đang chờ. Chỉ giới hạn concurrency mà retry ngay lập tức vẫn có thể tạo vòng lặp lỗi liên tục. Một pipeline ổn định cần có cả retry policy, giới hạn tải, batch size, timeout và cơ chế xử lý lỗi từng item.

## 1. Vì sao bulk ingestion cần điều khiển tải?

### 1.1. Bulk request giảm overhead nhưng có thể tạo burst lớn

Bulk API cho phép gửi nhiều thao tác index, create, update hoặc delete trong một request. So với gửi từng document riêng lẻ, bulk giúp giảm số lần round-trip và tận dụng hiệu quả hơn kết nối mạng.

Ví dụ:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"index":{"_index":"products","_id":"P1001"}}
{"name":"Wireless Keyboard","price":49.9}
{"index":{"_index":"products","_id":"P1002"}}
{"name":"USB Hub","price":19.9}
~~~

Tuy nhiên, bulk không làm chi phí indexing biến mất. Elasticsearch vẫn phải phân tích document, cập nhật Lucene segments, ghi translog, xử lý replica và thực hiện các hoạt động liên quan đến shard.

Một request chứa quá nhiều document hoặc nhiều bulk request chạy đồng thời có thể làm tăng:

- CPU và disk I/O.
- Heap usage và áp lực garbage collection.
- Write thread pool queue.
- Merge activity và segment count.
- Network traffic giữa coordinating node, primary shard và replica.
- Thời gian phản hồi và tỷ lệ request bị từ chối.

### 1.2. Khi cluster quá tải

Khi thread pool hoặc hàng đợi liên quan đến write không còn chỗ, Elasticsearch có thể trả lỗi rejection. Với bulk request, có thể nhận HTTP status thành công ở cấp request nhưng một số item bên trong bị lỗi. Cũng có trường hợp toàn request bị từ chối.

Các dấu hiệu thường gặp:

- HTTP 429.
- `es_rejected_execution_exception`.
- Bulk response có `errors: true`.
- Một số item có status 429 trong khi item khác đã thành công.
- Request timeout hoặc gateway timeout khi cluster chịu tải cao.

Không nên coi mọi lỗi trong bulk response là lỗi tạm thời. Lỗi mapping, sai kiểu dữ liệu hoặc document không hợp lệ sẽ không tự hết khi retry.

### 1.3. Retry ngay lập tức tạo retry storm

Giả sử 20 worker cùng gửi bulk request. Cluster bắt đầu trả 429. Nếu cả 20 worker retry ngay, chúng lại gửi một đợt request gần như cùng thời điểm.

~~~mermaid
sequenceDiagram
    participant C as Bulk clients
    participant E as Elasticsearch
    C->>E: Burst of concurrent bulk requests
    E-->>C: 429 / rejected
    C->>E: Immediate retries
    E-->>C: More rejections
    C->>E: Repeated retries
    E-->>C: Queue remains overloaded
~~~

Retry storm làm tăng request rate đúng vào lúc cluster đang thiếu khả năng xử lý. Backoff và jitter giúp giãn thời điểm retry; concurrency limit ngăn ứng dụng đưa quá nhiều request mới vào cluster.

## 2. Backoff là gì?

### 2.1. Chờ trước khi thử lại

Backoff là chính sách tăng thời gian chờ sau mỗi lần thất bại tạm thời. Thay vì gửi lại ngay, client đợi một khoảng thời gian rồi thử lại.

Ví dụ lịch chờ cố định:

| Lần retry | Thời gian chờ |
|---:|---:|
| 1 | 1 giây |
| 2 | 1 giây |
| 3 | 1 giây |
| 4 | 1 giây |

Fixed backoff đơn giản nhưng không tăng khoảng cách khi lỗi kéo dài. Với hệ thống đang quá tải, retry mỗi giây vẫn có thể gây áp lực liên tục.

### 2.2. Exponential backoff

Exponential backoff tăng thời gian chờ theo cấp số nhân:

\[
d_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

Trong đó:

- \(d_0\): thời gian chờ ban đầu.
- \(n\): số thứ tự lần retry, bắt đầu từ 1.
- \(d_{max}\): giới hạn thời gian chờ tối đa.
- \(d_n\): thời gian chờ trước lần retry thứ \(n\).

Ví dụ với initial delay 200 ms và maximum delay 5 giây:

| Lần retry | Delay trước khi áp dụng cap |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |
| 6 | 6.400 ms |
| 7 | 12.800 ms |

Sau khi áp dụng cap 5 giây, các lần tiếp theo không chờ quá 5 giây.

Exponential backoff giúp giảm tần suất retry khi lỗi kéo dài. Tuy nhiên, nếu mọi client đều bắt đầu cùng lúc và dùng cùng công thức, chúng vẫn có thể thức dậy và retry gần như đồng thời.

### 2.3. Giới hạn số lần retry

Không nên retry vô hạn. Mỗi operation cần một giới hạn rõ ràng, ví dụ tối đa 5 lần retry sau lần gửi đầu tiên.

Phân biệt:

- `attempt`: tổng số lần gửi, gồm lần đầu.
- `retry`: số lần gửi lại sau thất bại.

Nếu cấu hình `maxRetries = 5`, cần nói rõ đây là 5 lần retry hay 5 lần thử tổng cộng. Nhầm hai khái niệm có thể làm thời gian xử lý dài hơn dự kiến.

### 2.4. Giới hạn thời gian tổng thể

Số lần retry không phải giới hạn duy nhất. Một operation cũng nên có deadline hoặc maximum elapsed time.

Ví dụ:

- Timeout cho một HTTP request: 10 giây.
- Tối đa 5 lần retry.
- Tổng thời gian operation: không quá 45 giây.

Nếu deadline đã hết, không tiếp tục retry dù còn attempt. Điều này tránh một batch cũ tiếp tục chiếm worker khi pipeline cần chuyển sang dữ liệu mới.

## 3. Jitter: phân tán thời điểm retry

### 3.1. Vì sao chỉ exponential backoff chưa đủ?

Giả sử 100 client cùng gặp 429 tại thời điểm t = 0. Tất cả đều chờ 1, 2, 4 rồi 8 giây. Nếu thời điểm bắt đầu và delay giống nhau, các client có thể tạo thành những đợt request lớn tại cùng mốc thời gian.

Đây là hiện tượng synchronized retries. Jitter thêm yếu tố ngẫu nhiên vào delay để các client phân tán thời điểm gửi lại.

### 3.2. Full jitter

Full jitter chọn delay ngẫu nhiên trong khoảng từ 0 đến exponential cap:

\[
d_n \sim Uniform(0, \min(d_{max}, d_0 \times 2^{n-1}))
\]

Ví dụ cap ở lần retry thứ ba là 800 ms, delay thực tế có thể là bất kỳ giá trị nào từ 0 đến 800 ms.

Ưu điểm:

- Giảm khả năng nhiều client retry đúng cùng thời điểm.
- Giảm tải trung bình trong một cửa sổ retry.
- Công thức đơn giản, dễ triển khai.

Nhược điểm là có thể chọn delay rất ngắn, kể cả gần 0. Nếu muốn bảo đảm khoảng nghỉ tối thiểu, hãy cân nhắc equal jitter hoặc đặt floor riêng.

### 3.3. Equal jitter

Equal jitter giữ một nửa exponential cap làm phần chờ cơ sở và ngẫu nhiên hóa nửa còn lại:

\[
base_n = \min(d_{max}, d_0 \times 2^{n-1})
\]

\[
d_n = \frac{base_n}{2} + Uniform(0, \frac{base_n}{2})
\]

Với cap 800 ms, delay nằm trong khoảng 400–800 ms.

Equal jitter tránh delay quá gần 0 nhưng vẫn phân tán client.

### 3.4. Decorrelated jitter

Một cách khác là decorrelated jitter, trong đó delay mới phụ thuộc delay trước đó:

\[
d_n = \min(d_{max}, Uniform(d_0, 3 \times d_{n-1}))
\]

Cách này tạo chuỗi delay có độ phân tán tốt và không nhất thiết tăng đều theo từng lần retry. Cần lưu delay trước đó cho mỗi operation hoặc retry sequence.

### 3.5. So sánh các chiến lược

| Chiến lược | Công thức ý tưởng | Đặc điểm |
|---|---|---|
| Fixed | Luôn bằng một khoảng | Đơn giản, có thể đồng bộ client |
| Exponential | Tăng gấp đôi theo lần retry | Giãn dần nhưng vẫn đồng bộ nếu cùng bắt đầu |
| Full jitter | Ngẫu nhiên từ 0 đến exponential cap | Phân tán mạnh, có thể có delay rất ngắn |
| Equal jitter | Nửa cap cộng phần ngẫu nhiên | Có khoảng chờ tối thiểu tự nhiên |
| Decorrelated jitter | Dựa trên delay trước | Phân tán tốt, trạng thái phức tạp hơn |

Không có một chiến lược phù hợp cho mọi hệ thống. Full jitter thường là lựa chọn mặc định dễ triển khai cho retry phân tán; equal jitter hữu ích khi muốn hạn chế delay quá ngắn.

### 3.6. Dùng Retry-After khi server cung cấp

Một số tầng proxy hoặc dịch vụ có thể gửi header `Retry-After`. Nếu có, client nên xem đây là tín hiệu điều khiển thời điểm retry.

Cần phân biệt:

- `Retry-After` dạng số giây.
- `Retry-After` dạng HTTP-date.
- Header có thể đến từ gateway/proxy thay vì Elasticsearch trực tiếp.

Không được retry sớm hơn thời điểm server yêu cầu. Có thể thêm jitter nhỏ sau thời điểm đó để nhiều client không cùng gửi lại đúng một mốc, nhưng không được làm mất ý nghĩa minimum delay.

Nếu server yêu cầu chờ lâu hơn operation deadline, đưa batch vào hàng đợi bền vững hoặc đánh dấu retry sau; không giữ thread chờ vô thời hạn.

## 4. Phân loại lỗi trước khi retry

### 4.1. Retry chỉ dành cho lỗi có khả năng tạm thời

Một retry policy tốt cần phân biệt lỗi tạm thời và lỗi cố định.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Quá tải/từ chối tạm thời | 429, `es_rejected_execution_exception` | Backoff + jitter, giảm concurrency |
| Lỗi hạ tầng tạm thời | Một số 502, 503, 504, connection reset | Retry có giới hạn nếu operation còn deadline |
| Timeout | Request timeout hoặc response không đến | Chỉ retry khi semantics và idempotency cho phép |
| Mapping/validation | 400, mapper/parsing exception | Không retry; sửa dữ liệu hoặc mapping |
| Authorization | 401, 403 | Không retry tự động; xử lý credentials/permission |
| Version conflict | 409 hoặc version conflict item | Xử lý theo chính sách optimistic concurrency |
| Index không tồn tại | 404 hoặc resource error | Sửa cấu hình/index lifecycle; không retry mù |

HTTP status chỉ là tín hiệu ban đầu. Với bulk API, phải đọc error type và status của từng item. Một HTTP response 200 không có nghĩa tất cả thao tác trong bulk đều thành công.

### 4.2. Phân biệt lỗi request-level và item-level

Bulk response có trường `errors` và danh sách `items`. Mỗi item chứa kết quả của thao tác tương ứng.

Ví dụ khái niệm:

~~~json
{
  "errors": true,
  "items": [
    {
      "index": {
        "_id": "P1001",
        "status": 201
      }
    },
    {
      "index": {
        "_id": "P1002",
        "status": 429,
        "error": {
          "type": "es_rejected_execution_exception",
          "reason": "rejected execution"
        }
      }
    },
    {
      "index": {
        "_id": "P1003",
        "status": 400,
        "error": {
          "type": "mapper_parsing_exception",
          "reason": "failed to parse field"
        }
      }
    }
  ]
}
~~~

Trong ví dụ:

- P1001 đã thành công.
- P1002 bị từ chối tạm thời, có thể retry.
- P1003 lỗi mapping, cần sửa dữ liệu hoặc mapping.

Không gửi lại cả bulk request như thể chưa có item nào thành công. Chỉ đưa item được xác định là retryable vào batch retry. Nếu gửi lại toàn bộ, các item đã thành công sẽ bị ghi lại, tốn tài nguyên và có thể gây tác dụng phụ với update/create semantics.

### 4.3. Không retry mọi lỗi 4xx hoặc 5xx giống nhau

Một số lỗi 5xx là tạm thời, nhưng không phải tất cả. Một số lỗi 4xx như 429 lại có thể retry. Vì vậy policy phải dựa trên status, error type và ngữ cảnh operation.

Ví dụ:

- 429 do write queue rejection: thường retry được.
- 400 do mapper_parsing_exception: retry không giải quyết được.
- 409 version conflict: có thể cần đọc lại và tính lại update, không chỉ gửi lại cùng payload.
- 403 do index block hoặc permission: cần xác định nguyên nhân; không nên tạo retry loop.

### 4.4. Dead-letter queue cho lỗi không thể tự phục hồi

Các item không retryable hoặc đã hết retry budget nên được ghi lại trong dead-letter queue (DLQ) hoặc một kho lỗi có thể xử lý lại.

Một record DLQ hữu ích nên chứa:

- Document ID và index/alias đích.
- Operation type.
- Payload hoặc tham chiếu an toàn tới payload.
- Error type, status và reason.
- Attempt count.
- Timestamp và correlation/batch ID.
- Phiên bản schema hoặc pipeline nếu có.

Không log dữ liệu nhạy cảm đầy đủ nếu payload chứa thông tin cá nhân. Có thể lưu reference đến nơi lưu trữ được kiểm soát quyền.

## 5. Idempotency và an toàn khi retry

### 5.1. Vì sao retry có thể ghi trùng?

Một request có thể đã được Elasticsearch xử lý nhưng response bị mất trên đường về. Client nhìn thấy timeout và không biết thao tác đã thành công hay chưa.

Nếu retry một thao tác không idempotent, kết quả có thể bị lặp hoặc sai.

Ví dụ:

- `index` với `_id` ổn định thường ghi đè cùng document ID, nên retry cùng payload có tính idempotent ở mức trạng thái cuối.
- `create` với cùng `_id` lần thứ hai có thể trả conflict vì document đã được tạo.
- `update` có script tăng counter có thể tăng hai lần nếu lần đầu đã thành công nhưng response bị mất.
- `delete` cùng ID thường có trạng thái cuối đã xóa, nhưng response/semantics có thể khác giữa lần đầu và retry.

### 5.2. Dùng deterministic document ID

Nếu nguồn dữ liệu có khóa ổn định, dùng khóa đó làm `_id`. Ví dụ product ID hoặc event ID được tạo từ nguồn.

Điều này giúp retry thao tác index cùng document không tạo ra nhiều document mới.

Không dùng random ID mới cho mỗi lần retry nếu mục tiêu là cập nhật cùng một entity. Mỗi lần retry với ID khác nhau sẽ tạo document trùng.

### 5.3. Update script và external side effects

Các update script như increment, append hoặc phát sinh event cần được thiết kế cẩn thận khi retry. Có thể cần:

- Event ID duy nhất để deduplicate.
- Version hoặc sequence number.
- Optimistic concurrency control.
- Ghi trạng thái xử lý ở nguồn bền vững.
- Thiết kế thao tác có thể chạy lặp mà không đổi kết quả lần thứ hai.

Retry policy không thể tự biến một thao tác không idempotent thành an toàn.

### 5.4. Xử lý version conflict

Với optimistic concurrency, version conflict có thể cho biết document đã thay đổi sau khi client đọc. Gửi lại nguyên update cũ có thể tiếp tục conflict hoặc ghi đè thay đổi mới.

Một flow đúng có thể cần:

1. Đọc trạng thái mới nhất.
2. Tính lại thay đổi.
3. Gửi update với version/sequence mới.
4. Giới hạn số lần conflict retry.
5. Đưa vào xử lý thủ công nếu conflict kéo dài.

## 6. Giới hạn số yêu cầu đồng thời

### 6.1. Concurrency limit là gì?

Concurrency limit giới hạn số request đang được xử lý hoặc đang chờ phản hồi tại một thời điểm.

Ví dụ giới hạn 4 nghĩa là pipeline chỉ cho tối đa 4 bulk request in-flight. Khi một request hoàn tất, một request tiếp theo mới được gửi.

Điều này khác với rate limit:

- **Concurrency limit**: giới hạn số công việc đồng thời.
- **Rate limit**: giới hạn số request hoặc operation trong một đơn vị thời gian.

Một hệ thống có thể giữ 4 request đồng thời nhưng mỗi request mất 100 ms, tương ứng throughput cao. Khi latency tăng lên 10 giây, concurrency không đổi nhưng throughput giảm. Ngược lại, rate limit có thể chặn request mới ngay cả khi chưa đạt concurrency tối đa.

### 6.2. Vì sao concurrency cần giới hạn?

Không giới hạn request in-flight có thể khiến client đẩy nhiều công việc hơn khả năng cluster xử lý. Khi request latency tăng, số request đang chờ có thể tăng theo, giữ kết nối, buffer và memory ở ứng dụng.

Concurrency limit giúp:

- Hạn chế số request cùng lúc tới Elasticsearch.
- Giữ queue phía client trong phạm vi kiểm soát.
- Giảm áp lực lên thread pool và connection pool.
- Tạo điểm điều tiết rõ ràng khi cluster chậm.
- Dễ áp dụng backpressure cho producer.

### 6.3. Bulk size và concurrency là hai nút điều khiển khác nhau

Một bulk request chứa 100 document với 4 request đồng thời có thể đưa tối đa khoảng 400 document vào các request đang in-flight, chưa tính queue và retry.

Nếu tăng bulk size gấp đôi và concurrency gấp đôi, lượng công việc in-flight có thể tăng khoảng bốn lần.

Hãy điều chỉnh từng tham số có đo lường:

- Bulk size: số document và số byte trong mỗi request.
- Concurrency: số bulk request in-flight.
- Queue capacity: số batch chờ gửi.
- Retry budget: số lần và tổng thời gian retry.
- Producer rate: tốc độ dữ liệu đầu vào.

Không tăng tất cả cùng lúc vì sẽ khó xác định yếu tố nào làm cluster quá tải.

### 6.4. Ước lượng throughput bằng Little's Law

Một quan hệ hữu ích:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số request trung bình đang in-flight.
- \(\lambda\): throughput trung bình, request/giây.
- \(W\): thời gian xử lý trung bình của một request, giây.

Suy ra:

\[
\lambda \approx \frac{L}{W}
\]

Nếu concurrency là 4 và thời gian hoàn tất trung bình là 0,5 giây, throughput lý thuyết khoảng 8 request/giây. Đây chỉ là ước lượng; nó không cho biết Elasticsearch có đủ CPU, disk hoặc write capacity để duy trì mức đó.

Khi latency tăng, throughput thực tế với concurrency cố định sẽ giảm. Không nên tăng concurrency vô hạn để cố giữ throughput, vì điều đó có thể làm latency và rejection tệ hơn.

## 7. Điều chỉnh concurrency thích ứng

### 7.1. AIMD: tăng chậm, giảm nhanh

Một chiến lược phổ biến là Additive Increase, Multiplicative Decrease (AIMD):

- Khi hệ thống ổn định trong một khoảng thời gian, tăng concurrency thêm một lượng nhỏ.
- Khi có dấu hiệu quá tải như 429 hoặc latency vượt ngưỡng, giảm concurrency theo tỷ lệ.
- Giữ concurrency trong min/max đã cấu hình.

Ví dụ:

~~~text
maxInFlight = 4

healthy windows:
  4 -> 5 -> 6 -> 7

overload:
  7 -> floor(7 * 0.5) = 3
~~~

Cách này thăm dò dần năng lực cluster nhưng phản ứng nhanh khi có rejection.

### 7.2. Không tăng concurrency chỉ vì không có 429

Không có rejection không đồng nghĩa cluster đang rảnh. CPU, disk I/O, merge pressure, heap và write latency vẫn có thể ở mức cao.

Adaptive controller nên xem nhiều tín hiệu:

- Tỷ lệ 429/rejected.
- Bulk request latency p50/p95.
- Throughput thành công.
- Write thread pool active/queue/rejected.
- Node CPU và disk utilization.
- Heap pressure và GC.
- Ingest lag ở producer.

Chỉ điều chỉnh theo những metric có thể đo tin cậy. Không tăng tải khi metric bị thiếu hoặc đang stale.

### 7.3. Hysteresis và thời gian ổn định

Nếu controller tăng/giảm concurrency mỗi vài millisecond, hệ thống có thể dao động liên tục. Dùng cửa sổ đo, cooldown và ngưỡng khác nhau cho tăng/giảm.

Ví dụ:

- Chỉ tăng sau 3 cửa sổ liên tiếp không có rejection và latency trong ngưỡng.
- Giảm ngay khi có rejection lặp lại hoặc p95 vượt ngưỡng.
- Sau khi giảm, đợi cooldown trước khi tăng lại.
- Đặt min concurrency và max concurrency.

Các con số phải được benchmark theo cluster và workload, không dùng làm mặc định production cho mọi hệ thống.

### 7.4. Global limit và per-index/per-tenant limit

Một giới hạn toàn ứng dụng có thể không đủ nếu nhiều index hoặc tenant có mức độ ưu tiên khác nhau.

Có thể dùng:

- Global semaphore để bảo vệ cluster.
- Per-index limit để tránh một index chiếm toàn bộ capacity.
- Per-tenant quota để cô lập workload.
- Priority queue cho dữ liệu quan trọng.
- Fair scheduling để tránh tenant lớn làm đói tenant nhỏ.

Nếu nhiều instance ứng dụng cùng gửi bulk, semaphore trong một JVM chỉ giới hạn từng instance. Muốn giới hạn toàn hệ thống cần coordinator hoặc phân bổ quota theo instance.

## 8. Kết hợp backoff với concurrency limit

### 8.1. Mô hình điều tiết

Một pipeline có thể tổ chức như sau:

~~~mermaid
flowchart TD
    A[Producer] --> B[Bounded batch queue]
    B --> C[Concurrency limiter]
    C --> D[Bulk request]
    D --> E[Elasticsearch]
    E --> F{Bulk response}
    F -->|All success| G[Acknowledge batch]
    F -->|Retryable items| H[Retry scheduler with backoff and jitter]
    F -->|Permanent failures| I[Dead-letter queue]
    H --> C
    G --> B
    I --> B
~~~

Queue cần có capacity hữu hạn. Khi queue đầy, producer phải chờ, giảm tốc độ hoặc ghi vào một log bền vững. Không thay queue hữu hạn bằng một danh sách in-memory không giới hạn.

### 8.2. Retry không nên giữ semaphore trong lúc ngủ

Một lỗi thiết kế thường gặp là giữ permit concurrency trong toàn bộ thời gian backoff. Nếu nhiều request bị 429, tất cả permit có thể bị giữ bởi các task đang ngủ, khiến pipeline không thể xử lý batch khác dù cluster đã hồi phục.

Một flow tốt hơn:

1. Gửi request khi đã lấy permit.
2. Nhận response.
3. Giải phóng permit.
4. Phân loại item lỗi.
5. Lên lịch retry với delay.
6. Đến thời điểm retry, lấy permit mới trước khi gửi.

Như vậy, thời gian ngủ không chiếm slot request in-flight.

### 8.3. Giới hạn retry queue

Retry queue cũng phải bounded. Nếu cluster lỗi lâu và producer tiếp tục tạo dữ liệu, retry queue có thể phình ra vô hạn.

Có thể:

- Giới hạn số batch retry đang chờ.
- Lưu batch vào durable queue.
- Dùng exponential backoff có cap.
- Đưa item hết retry budget sang DLQ.
- Áp dụng backpressure cho producer.
- Có chính sách ưu tiên hoặc loại bỏ dữ liệu theo nghiệp vụ nếu được cho phép.

### 8.4. Tránh retry lồng nhiều tầng

Nếu HTTP client, Spring service, message consumer và scheduler đều có retry độc lập, một operation có thể bị nhân số lần thử. Ví dụ ba tầng, mỗi tầng retry 3 lần, có thể tạo tối đa nhiều request hơn dự kiến.

Chỉ định một tầng sở hữu retry policy cho bulk operation hoặc tính toán tổng retry budget giữa các tầng. Ghi rõ retry attempt trong log và metric.

## 9. Thiết kế bulk size và flush strategy

### 9.1. Chọn bulk size theo byte và document count

Bulk size thường được đặt theo số document, nhưng kích thước document có thể khác nhau rất nhiều. 1.000 document nhỏ và 1.000 document lớn tạo tải rất khác.

Theo dõi cả:

- Số document mỗi bulk.
- Tổng request bytes.
- Kích thước trung bình và p95 document.
- Thời gian xử lý bulk.
- Tỷ lệ rejection.

Không nên tạo bulk quá lớn chỉ để giảm số HTTP request. Bulk quá lớn có thể tăng memory pressure và làm retry một request tốn kém hơn.

### 9.2. Flush theo kích thước hoặc thời gian

Một batcher có thể flush khi:

- Đạt số document tối đa.
- Đạt giới hạn byte.
- Hết thời gian chờ kể từ document đầu tiên.
- Có tín hiệu shutdown hoặc checkpoint.

Ví dụ:

~~~text
flush when:
  documentCount >= 500
  OR estimatedBytes >= 5 MiB
  OR oldestDocumentAge >= 1 second
~~~

Đây chỉ là giá trị minh họa. Hãy benchmark theo kích thước document và cluster thực tế.

### 9.3. Đừng nhầm flush interval với retry backoff

Flush interval điều khiển khi batch đang gom được gửi đi. Retry backoff điều khiển khi một batch hoặc item lỗi được thử lại.

Nếu flush interval quá ngắn, ứng dụng tạo nhiều bulk nhỏ. Nếu retry delay quá ngắn, ứng dụng gây áp lực lên cluster đang lỗi. Hai tham số cần được cấu hình và quan sát riêng.

## 10. Ví dụ triển khai retry policy bằng Java

### 10.1. Tính exponential backoff với full jitter

Ví dụ Java thuần:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryDelayPolicy {

    private final Duration initialDelay;
    private final Duration maxDelay;

    public RetryDelayPolicy(
            Duration initialDelay,
            Duration maxDelay) {
        this.initialDelay = initialDelay;
        this.maxDelay = maxDelay;
    }

    public Duration fullJitterDelay(int retryNumber) {
        if (retryNumber < 1) {
            throw new IllegalArgumentException(
                "retryNumber must be >= 1"
            );
        }

        long initial = initialDelay.toMillis();
        long cap = maxDelay.toMillis();

        long exponentialCap = initial;

        for (int i = 1; i < retryNumber; i++) {
            if (exponentialCap > cap / 2) {
                exponentialCap = cap;
                break;
            }
            exponentialCap *= 2;
        }

        exponentialCap = Math.min(exponentialCap, cap);

        long delay = ThreadLocalRandom.current()
            .nextLong(exponentialCap + 1);

        return Duration.ofMillis(delay);
    }
}
~~~

Đoạn code minh họa cách tạo delay có cap. Production code cần validate initialDelay lớn hơn 0, maxDelay không nhỏ hơn initialDelay, tránh overflow khi chuyển duration và quyết định rõ đơn vị/độ chính xác. Nếu maxDelay có thể gần giới hạn long, cần tránh phép cộng exponentialCap + 1 bị overflow.

### 10.2. Kiểm tra retry budget

~~~java
public boolean canRetry(
        int retriesAlreadyUsed,
        int maxRetries,
        Instant deadline,
        Clock clock) {

    return retriesAlreadyUsed < maxRetries
        && clock.instant().isBefore(deadline);
}
~~~

Dùng Clock giúp test deadline có thể kiểm soát. Không chỉ dựa vào Thread.sleep và số attempt; operation phải dừng khi deadline hết.

### 10.3. Không sleep trên callback thread

Nếu dùng asynchronous HTTP client hoặc bulk listener, không gọi Thread.sleep trong callback hoàn tất request. Điều này giữ thread xử lý response bị chặn và có thể làm giảm throughput toàn client.

Dùng scheduler hoặc delayed queue để lên lịch retry:

~~~java
scheduler.schedule(
    () -> retryQueue.offer(failedItems),
    delay.toMillis(),
    TimeUnit.MILLISECONDS
);
~~~

Ví dụ trên chỉ minh họa ý tưởng. retryQueue cần bounded và thao tác offer phải có cách xử lý khi queue đầy. Task retry vẫn phải lấy concurrency permit trước khi gửi request.

## 11. Giới hạn concurrency bằng Semaphore

### 11.1. Ví dụ semaphore đồng bộ

~~~java
public final class BulkConcurrencyLimiter {

    private final Semaphore permits;

    public BulkConcurrencyLimiter(int maxInFlight) {
        if (maxInFlight < 1) {
            throw new IllegalArgumentException(
                "maxInFlight must be positive"
            );
        }
        this.permits = new Semaphore(maxInFlight);
    }

    public void execute(Runnable request) throws InterruptedException {
        permits.acquire();
        try {
            request.run();
        } finally {
            permits.release();
        }
    }
}
~~~

Đây là ví dụ đồng bộ đơn giản. Với HTTP request bất đồng bộ, không được release permit ngay sau khi method trả về nếu request vẫn đang chạy. Permit phải được release khi future hoàn tất, kể cả exceptional completion hoặc cancellation.

### 11.2. Semaphore cho CompletableFuture

Mẫu khái niệm:

~~~java
public <T> CompletableFuture<T> executeAsync(
        Supplier<CompletableFuture<T>> requestSupplier) {

    permits.acquireUninterruptibly();

    try {
        CompletableFuture<T> future = requestSupplier.get();

        return future.whenComplete((result, error) ->
            permits.release()
        );
    } catch (Throwable error) {
        permits.release();
        throw error;
    }
}
~~~

Trong code production, cân nhắc dùng acquire có thể interrupt hoặc tryAcquire(timeout) để không chặn vô hạn. Cần xử lý trường hợp supplier ném exception đồng bộ và future bị cancel. Permit chỉ được release đúng một lần.

### 11.3. Không tạo quá nhiều future trước limiter

Nếu producer tạo hàng trăm nghìn CompletableFuture rồi mới chờ semaphore, số task và object vẫn có thể phình trong heap.

Limiter nên nằm trước bước tạo hoặc gửi request, kết hợp bounded queue và backpressure. Chỉ có số lượng task chờ hữu hạn.

### 11.4. Timeout khi chờ permit

Nếu không lấy được permit trong thời gian cho phép, operation có thể:

- Được đưa trở lại queue.
- Bị từ chối với trạng thái overload.
- Ghi vào durable queue.
- Hết deadline và chuyển sang lỗi có thể quan sát.

Không nên để thread chờ permit vô thời hạn trong một executor có số thread cố định, vì có thể làm cạn worker.

## 12. Tích hợp với Spring Data Elasticsearch

### 12.1. BulkOperations

Spring Data Elasticsearch có abstraction `BulkOperations` để gom nhiều thao tác ghi:

~~~java
BulkOperations bulk = operations.bulkOps(
    BulkOperations.BulkMode.BULK,
    ProductDocument.class
);

bulk.insert(products);
bulk.execute();
~~~

Cú pháp và overload phụ thuộc phiên bản Spring Data Elasticsearch. BulkOperations giúp biểu diễn bulk write, nhưng retry/backoff/concurrency policy tổng thể vẫn cần được thiết kế ở tầng ingestion hoặc component quản lý bulk.

Không giả định một lần gọi execute tự cung cấp mọi retry policy mong muốn cho từng item.

### 12.2. Phân loại lỗi sau execute

Tùy phiên bản, bulk execution có thể trả kết quả hoặc ném exception khi request lỗi. Cần xác định API đang dùng có expose từng item response hay chỉ expose request-level failure.

Nếu cần retry chính xác từng item:

1. Giữ danh sách thao tác gốc theo thứ tự.
2. Đọc từng item response tương ứng.
3. Phân loại status và error type.
4. Tạo danh sách thao tác chỉ gồm item retryable.
5. Đưa lỗi cố định vào DLQ.
6. Không retry item đã thành công.

Nếu abstraction cấp cao không expose đủ metadata item, có thể cần dùng Elasticsearch Java API Client hoặc bulk response API thấp hơn cho ingestion component.

### 12.3. Dùng Elasticsearch Java API Client

Elasticsearch Java API Client cung cấp Bulk API và response item để ứng dụng kiểm tra từng thao tác. Mẫu khái niệm:

~~~java
BulkResponse response = esClient.bulk(b -> b
    .operations(operations)
);

List<BulkOperation> retryable = new ArrayList<>();

for (int i = 0; i < response.items().size(); i++) {
    BulkResponseItem item = response.items().get(i);

    if (isRetryable(item)) {
        retryable.add(originalOperations.get(i));
    } else if (item.error() != null) {
        deadLetter(item, originalOperations.get(i));
    }
}
~~~

Đoạn code minh họa cách ghép response item với operation gốc theo thứ tự. Kiểu class, accessor và cách tạo BulkOperation phụ thuộc phiên bản Java API Client. Cần bảo đảm thứ tự mapping không bị thay đổi khi chia batch hoặc lọc retry items.

### 12.4. BulkProcessor và giới hạn concurrent requests

Một số phiên bản Elasticsearch Java API Client hoặc thư viện client có `BulkIngester`/`BulkProcessor` để gom request và quản lý số bulk request đồng thời. API cụ thể thay đổi theo client version.

Khi sử dụng, hãy kiểm tra các cấu hình tương ứng:

- Maximum operations per bulk.
- Maximum bytes per bulk.
- Flush interval.
- Maximum concurrent bulk requests.
- Listener xử lý bulk response và lỗi.
- Chính sách retry/rejection nếu component cung cấp.

Không dựa vào tên BulkProcessor từ một thư viện cũ để suy ra cấu hình của client hiện tại. Spring Data Elasticsearch version và Elasticsearch Java API Client version cần tương thích.

### 12.5. Tránh nhiều lớp retry trùng nhau

Spring retry, HTTP client retry, message broker redelivery và bulk listener có thể cùng hoạt động. Nếu không có một retry budget chung, số lần gửi thực tế có thể lớn hơn cấu hình ở từng lớp.

Chọn một nơi chịu trách nhiệm chính cho item-level retry và ghi attempt count xuyên suốt operation. Các tầng khác nên truyền lỗi hoặc áp dụng retry cho loại lỗi riêng đã được xác định.

## 13. Circuit breaker và backpressure

### 13.1. Circuit breaker

Nếu cluster liên tục thất bại, circuit breaker có thể tạm ngừng gửi request mới:

- Closed: request được phép đi qua.
- Open: từ chối hoặc xếp hàng trong thời gian cooldown.
- Half-open: cho một số request thử để kiểm tra cluster đã hồi phục chưa.

Circuit breaker khác backoff. Backoff điều khiển thời điểm retry của operation; circuit breaker điều khiển có gửi request mới vào dependency hay không.

### 13.2. Backpressure về producer

Nếu ingestion consumer đọc nhanh hơn Elasticsearch ghi được, queue phía ứng dụng sẽ tăng. Bounded queue giúp phát hiện sớm tình trạng này.

Các lựa chọn:

- Pause/resume message consumption.
- Giảm số consumer.
- Điều chỉnh fetch batch size.
- Chờ queue có capacity.
- Persist dữ liệu vào log hoặc broker.
- Phát tín hiệu overload về upstream.

Không bỏ dữ liệu âm thầm khi queue đầy. Nếu phải drop, cần chính sách nghiệp vụ và metric ghi nhận rõ.

### 13.3. Phân biệt cluster overload với nguồn dữ liệu burst

Nếu producer đẩy dữ liệu theo burst, có thể cần rate smoothing hoặc batch scheduling trước khi gửi. Nếu cluster luôn quá tải ở tốc độ trung bình, backoff chỉ giảm burst tạm thời; cần tăng capacity, giảm chi phí indexing hoặc giảm ingest rate.

Backoff không thay thế capacity planning.

## 14. Timeout, cancellation và shutdown

### 14.1. Timeout request và deadline operation

Mỗi bulk request nên có request timeout. Toàn bộ batch/retry sequence nên có deadline riêng.

Nếu request timeout, client có thể không biết server đã thực hiện một phần hay toàn bộ operation. Đây là lý do idempotency và deterministic IDs rất quan trọng.

### 14.2. Cancellation

Khi job bị hủy hoặc application shutdown:

- Ngừng nhận batch mới.
- Ngừng lên lịch retry mới.
- Chờ request in-flight hoàn tất trong grace period.
- Persist batch chưa xử lý nếu cần.
- Đưa lỗi cuối cùng vào DLQ hoặc durable retry queue.
- Giải phóng semaphore permit đúng một lần.

Không xóa retry queue in-memory khi shutdown nếu dữ liệu chưa được ghi nhận ở nơi bền vững.

### 14.3. Graceful shutdown

Một trình tự shutdown có thể là:

1. Đánh dấu ingestion service đang dừng.
2. Tạm dừng producer hoặc consumer.
3. Flush batch đang gom nếu còn deadline.
4. Chờ request in-flight trong một khoảng grace period.
5. Persist các batch chưa gửi hoặc retry đang chờ.
6. Đóng bulk client và scheduler.
7. Xuất metric về số item thành công, lỗi và còn pending.

Nếu cluster đang lỗi, không kéo dài shutdown vô hạn để retry. Hãy bảo đảm dữ liệu pending được lưu bền vững và có thể tiếp tục ở lần khởi động sau.

## 15. Theo dõi retry và concurrency trong production

### 15.1. Metric nên có

Theo dõi:

- Bulk requests gửi mỗi giây.
- Số document và byte mỗi bulk.
- Bulk latency p50/p95/p99.
- Số request in-flight.
- Concurrency limit hiện tại.
- Số request bị chờ permit.
- Số item thành công/thất bại.
- Retry count theo status/error type.
- Delay thực tế của retry.
- Retry queue depth và oldest age.
- DLQ item count.
- 429 và `es_rejected_execution_exception`.
- Write thread pool active, queue và rejected.
- CPU, heap, GC, disk I/O và merge pressure.

Metric nên gắn nhãn có giới hạn cardinality. Không dùng document ID hoặc tenant ID tùy ý làm label Prometheus vì có thể tạo số lượng time series rất lớn. Có thể dùng log hoặc trace cho định danh cụ thể.

### 15.2. Log có correlation

Mỗi batch nên có batch ID hoặc correlation ID. Log các trường:

- Batch ID.
- Attempt number.
- Item count và byte size.
- Request duration.
- Error type/status.
- Retry delay.
- Concurrency limit tại thời điểm gửi.
- Số item retryable, permanent và successful.

Không log payload đầy đủ nếu có dữ liệu nhạy cảm.

### 15.3. Cảnh báo theo xu hướng

Cảnh báo có thể dựa trên:

- 429 tăng kéo dài.
- Retry queue tăng liên tục.
- Oldest retry age vượt SLA.
- p95 bulk latency tăng mạnh.
- Concurrency bị giảm liên tục.
- DLQ tăng bất thường.
- Producer lag tăng.

Một vài 429 ngắn có thể xảy ra trong workload burst. Điều quan trọng là tỷ lệ, thời gian kéo dài và ảnh hưởng tới ingest lag.

## 16. Benchmark và điều chỉnh cấu hình

### 16.1. Bắt đầu bằng cấu hình bảo thủ

Một lần thử ban đầu có thể dùng:

- Bulk size vừa phải theo byte và document count.
- Concurrency nhỏ.
- Exponential backoff có cap.
- Full jitter.
- Retry budget hữu hạn.
- Queue bounded.
- Request timeout và operation deadline.
- Retry chỉ cho item lỗi tạm thời.

Đây là điểm khởi đầu để đo, không phải bộ thông số production dùng chung.

### 16.2. Thử tải theo từng bước

Một quy trình benchmark:

1. Gửi một bulk nhỏ và đo latency.
2. Tăng bulk size trong khi giữ concurrency cố định.
3. Ghi throughput, latency và rejection.
4. Giữ bulk size hợp lý rồi tăng concurrency từng bước.
5. Xác định vùng throughput ổn định trước khi rejection tăng.
6. Thử burst và lỗi 429 có chủ đích trong môi trường test.
7. Xác minh jitter phân tán retry và concurrency không vượt giới hạn.
8. Thử cluster chậm, timeout và shutdown.
9. Chọn operating point có headroom thay vì chạy sát giới hạn.

### 16.3. Không tối ưu theo throughput đơn lẻ

Một cấu hình đạt throughput cao nhưng có p99 latency rất lớn, retry queue tăng hoặc nhiều rejection chưa phải cấu hình tốt.

Đánh giá đồng thời:

- Successful documents/second.
- End-to-end ingest lag.
- Bulk latency.
- Rejection rate.
- Retry volume.
- Heap/CPU/disk.
- Tỷ lệ lỗi vĩnh viễn.
- Khả năng phục hồi sau burst.

### 16.4. Kiểm thử với nhiều client

Jitter chỉ có giá trị khi nhiều client không đồng bộ retry. Hãy mô phỏng nhiều worker hoặc nhiều application instance cùng nhận 429, rồi quan sát thời điểm retry.

Một test chỉ có một client không thể chứng minh hệ thống tránh được synchronized retry storm.

## 17. Ví dụ cấu hình tham khảo

Bộ thông số sau chỉ để minh họa một pipeline có giới hạn:

| Tham số | Giá trị ví dụ | Mục đích |
|---|---:|---|
| Bulk documents | 500 | Giới hạn số thao tác mỗi batch |
| Bulk bytes | 5 MiB | Tránh request quá lớn |
| Max in-flight | 4 | Giới hạn bulk request đồng thời |
| Initial backoff | 200 ms | Delay khởi đầu |
| Max backoff | 10 giây | Cap exponential delay |
| Jitter | Full jitter | Phân tán thời điểm retry |
| Max retries | 5 | Giới hạn lần thử lại |
| Request timeout | 10 giây | Giới hạn một HTTP request |
| Operation deadline | 45 giây | Giới hạn toàn bộ retry sequence |
| Retry queue | 100 batches | Giới hạn backlog trong memory |

Không sao chép nguyên bảng này vào production. Cần điều chỉnh theo document size, shard count, node capacity, network, workload và SLA.

## 18. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| 429 tăng sau mỗi lần retry | Retry ngay hoặc delay quá ngắn | Exponential backoff và jitter |
| Nhiều client retry cùng thời điểm | Cùng dùng exponential delay không jitter | Full/equal/decorrelated jitter |
| Cluster vẫn quá tải dù có backoff | Quá nhiều request in-flight hoặc producer rate quá cao | Giới hạn concurrency, bounded queue và backpressure |
| Một bulk có item thành công vẫn bị gửi lại toàn bộ | Không xử lý partial failure | Retry riêng item lỗi có thể retry |
| Mapping error lặp mãi | Retry lỗi dữ liệu cố định | Phân loại error và đưa vào DLQ |
| Document bị ghi trùng | Retry với ID mới hoặc operation không idempotent | Deterministic ID và deduplication |
| Counter tăng hai lần | Update script không idempotent và response timeout | Event ID/version hoặc thiết kế update an toàn khi chạy lặp |
| Semaphore không giải phóng | Chỉ release ở success path | Release trong completion/finally, kể cả lỗi và cancel |
| Pipeline đứng dù cluster đã hồi phục | Giữ permit trong lúc task backoff | Release permit trước khi schedule retry |
| Heap tăng dù concurrency nhỏ | Tạo quá nhiều future hoặc queue không giới hạn | Bounded queue và limiter trước khi tạo request |
| Shutdown làm mất batch | Retry queue chỉ nằm trong memory | Persist pending batch và graceful shutdown |
| Throughput giảm khi tăng concurrency | Cluster bão hòa, queue/latency tăng | Giảm concurrency và tìm operating point ổn định |
| Retry nhiều tầng làm request tăng đột biến | HTTP, service và broker đều retry | Một retry budget thống nhất |
| Dashboard metric quá nhiều series | Dùng ID/tenant tùy ý làm label | Dùng label có giới hạn và log/trace cho chi tiết |

## 19. Quy trình triển khai thực tế

Khi xây pipeline bulk ingestion, hãy thực hiện theo trình tự:

1. Xác định bulk operation nào có thể retry an toàn.
2. Dùng document ID ổn định hoặc cơ chế deduplication phù hợp.
3. Chọn batch size theo cả document count và byte size.
4. Đặt concurrency limit cho request in-flight.
5. Dùng bounded queue và backpressure cho producer.
6. Phân loại request-level và item-level errors.
7. Chỉ retry các lỗi tạm thời đã xác định.
8. Dùng exponential backoff có cap và jitter.
9. Giải phóng concurrency permit trong lúc chờ retry.
10. Giới hạn max retries và operation deadline.
11. Đưa lỗi cố định hoặc hết retry budget vào DLQ.
12. Theo dõi retry, queue depth, 429, latency và cluster resource.
13. Benchmark bulk size/concurrency theo từng bước.
14. Kiểm thử burst, nhiều client, partial success, timeout và shutdown.
15. Rollout với headroom và khả năng giảm tải khi cluster có dấu hiệu quá tải.

## 20. Những điểm cần ghi nhớ

- Backoff làm giãn các lần retry; exponential backoff tăng delay theo số lần thất bại.
- Jitter thêm ngẫu nhiên để nhiều client không retry đồng loạt.
- Full jitter chọn delay trong khoảng từ 0 đến exponential cap; equal jitter giữ một phần delay cơ sở.
- Dùng cap, max retries và operation deadline để retry có giới hạn.
- Ưu tiên Retry-After khi server/proxy cung cấp, đồng thời giữ jitter mà không retry sớm hơn thời điểm yêu cầu.
- Phân loại lỗi theo status và error type; 429 thường có thể retry, còn mapping/validation errors cần sửa dữ liệu.
- Bulk API có partial failure: HTTP 200 không đồng nghĩa mọi item thành công.
- Chỉ retry item lỗi tạm thời, không gửi lại cả bulk chứa item đã thành công.
- Deterministic document ID và idempotent operation giúp retry an toàn khi response bị mất.
- Concurrency limit giới hạn request in-flight; rate limit giới hạn tốc độ gửi.
- Kết hợp concurrency limiter, bounded queue và backpressure để tránh backlog không giới hạn.
- Không giữ semaphore permit trong lúc task chờ backoff.
- Kiểm soát retry lồng nhiều tầng để tránh nhân số lần request.
- Theo dõi bulk latency, 429, retry queue, DLQ, concurrency, heap và write thread pool.
- Chọn bulk size, concurrency và retry policy bằng benchmark trên workload gần production.

Backoff, jitter và concurrency limit bổ trợ cho nhau. Backoff cho cluster thời gian hồi phục, jitter phân tán các lần thử lại, còn concurrency limit giữ lượng request đang chạy trong phạm vi có thể kiểm soát. Khi kết hợp với retry theo từng item, idempotency, bounded queue và backpressure, pipeline bulk ingestion có thể phục hồi sau quá tải mà không tạo thêm một đợt tải mới làm tình trạng tệ hơn.
