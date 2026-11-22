# Điều chỉnh bộ nhớ, CPU và timeout dựa trên số đo

Trong chương **Tối ưu hiệu năng**, điều chỉnh memory, CPU và timeout là quá trình tìm cấu hình phù hợp với tải thực tế, yêu cầu độ trễ và ngân sách. Tăng memory có thể giúp function chạy nhanh hơn nếu nền tảng cấp thêm CPU theo memory; tăng timeout chỉ cho function thêm thời gian hoàn tất, nhưng không tự làm code nhanh hơn. Nếu chọn cấu hình bằng cảm tính, hệ thống có thể tốn chi phí hơn, giữ concurrency lâu hơn hoặc vẫn timeout ở nhóm request chậm.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng theo mô hình serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Tối ưu hiệu năng cần đo cả thời gian xử lý, mức dùng bộ nhớ, CPU, cold start, retry và throughput trong bối cảnh trigger thật.

## 1. Vì sao phải điều chỉnh dựa trên số đo?

Một function chạy chậm không nhất thiết thiếu CPU hoặc memory. Nguyên nhân có thể là:

- Thuật toán có độ phức tạp cao hoặc xử lý dữ liệu thừa.
- Chờ database, HTTP API, DNS hoặc message broker.
- Connection pool cạn hoặc thread bị block.
- Garbage collection diễn ra thường xuyên.
- JVM phải khởi tạo class, JIT compile hoặc mở kết nối trong cold start.
- Function bị throttling do concurrency hoặc quota.
- Timeout của dependency, function và caller không tương thích.
- Retry làm một workload được thực hiện nhiều lần.

Vì vậy, không nên bắt đầu bằng cách tăng timeout hoặc tăng memory đồng loạt. Trước tiên cần xác định bottleneck và đo baseline. Một thay đổi chỉ được xem là cải thiện khi metric mục tiêu tốt hơn mà không làm xấu chi phí, tỷ lệ lỗi hoặc các chỉ số bảo vệ khác.

## 2. Memory, CPU và timeout có quan hệ thế nào?

Ba cấu hình này ảnh hưởng lẫn nhau nhưng có ý nghĩa khác nhau.

| Tham số | Ý nghĩa | Tác động chính |
|---|---|---|
| Memory | Giới hạn bộ nhớ cấp cho execution environment | Heap, native memory, buffer và khả năng xử lý dữ liệu |
| CPU | Năng lực xử lý được nền tảng cấp | Tốc độ tính toán, nén, mã hóa, parse và một phần thời gian khởi tạo |
| Timeout | Thời gian tối đa cho một invocation | Giới hạn thời gian xử lý trước khi nền tảng kết thúc invocation |

Trên AWS Lambda, CPU được phân bổ tỷ lệ thuận với cấu hình memory. Tăng memory có thể đồng thời tăng CPU và một số năng lực tài nguyên khác của execution environment. Trên các nền tảng khác, CPU và memory có thể được cấu hình độc lập hoặc theo các mức tài nguyên định trước; cần đọc đúng mô hình của runtime đang dùng.

Timeout chỉ là giới hạn trên. Nếu function cần 2 giây để xử lý nhưng được đặt timeout 60 giây, function không tự chạy nhanh hơn. Timeout dài hơn có thể giữ concurrency lâu hơn khi dependency bị treo, làm tăng queue age và khiến caller phải chờ.

Mục tiêu là chọn memory/CPU đủ để xử lý tải dự kiến với latency và cost phù hợp, rồi đặt timeout vừa đủ cho thời gian xử lý hợp lệ và các biến động đã đo được.

## 3. Đo baseline trước khi thay đổi

Một baseline tốt cần phản ánh tải thực tế, không chỉ một lần gọi thủ công.

Nên thu thập:

- Invocation count và request rate.
- Duration p50, p95 và p99.
- Error rate, timeout và throttling.
- Max Memory Used và memory allocation.
- Init Duration hoặc cold start duration.
- Concurrent executions.
- Queue age, iterator age và retry count nếu có event trigger.
- Throughput: số request hoặc message xử lý thành công mỗi giây.
- Cost trên mỗi invocation và mỗi đơn vị công việc hoàn tất.

Đo trong các tình huống:

1. Cold start sau khi tạo execution environment mới.
2. Warm invocation khi environment được tái sử dụng.
3. Payload nhỏ, trung bình và lớn.
4. Tải bình thường và tải đỉnh.
5. Dependency phản hồi nhanh và tình huống dependency chậm có kiểm soát.
6. Batch size, architecture và concurrency giống production.

Không so sánh hai cấu hình nếu dữ liệu đầu vào, vùng triển khai, downstream load hoặc concurrency khác nhau đáng kể. Ghi lại commit, runtime version, memory, timeout, environment và thời gian chạy benchmark để có thể lặp lại phép đo.

## 4. Các metric quan trọng

### 4.1. Duration và percentile

Duration đo thời gian thực thi handler theo định nghĩa của nền tảng. Average hữu ích để xem xu hướng tổng thể, nhưng có thể che khuất một nhóm invocation rất chậm.

- p50 cho biết trải nghiệm của invocation ở giữa phân bố.
- p95 cho biết 95% invocation hoàn thành không quá thời gian này.
- p99 giúp nhìn thấy tail latency và các request hiếm nhưng rất chậm.
- Maximum có thể bị ảnh hưởng bởi outlier hoặc sự cố downstream.

Đặt SLO theo percentile phù hợp với trải nghiệm. API tương tác thường quan tâm p95/p99; batch xử lý nền có thể quan tâm throughput và thời gian hoàn tất toàn batch.

Duration của function không phải lúc nào cũng là end-to-end latency. Với HTTP, còn có thời gian gateway, authorizer, network và client. Với queue, còn có thời gian chờ trước khi message được xử lý và thời gian retry.

### 4.2. Memory metrics

Trên AWS Lambda, dòng REPORT trong CloudWatch Logs có thể cung cấp Memory Size và Max Memory Used cho invocation. Đây là tín hiệu quan trọng để phát hiện function đang tiến sát giới hạn.

Ví dụ một dòng báo cáo có dạng:

~~~text
REPORT RequestId: ... Duration: 840.12 ms
Billed Duration: 841 ms Memory Size: 1024 MB
Max Memory Used: 612 MB Init Duration: 420.00 ms
~~~

Các con số trên chỉ minh họa cách đọc trường dữ liệu, không phải benchmark hay cam kết thời gian. Max Memory Used là mức sử dụng cao nhất được nền tảng ghi nhận cho invocation; nó không nói riêng heap Java đang dùng bao nhiêu.

Nếu Max Memory Used gần Memory Size, cần kiểm tra heap, native memory, thread stack, direct buffer, class metadata và các thư viện native. Không nên chỉ nhìn heap dump rồi kết luận toàn bộ process còn nhiều memory.

### 4.3. Cold start và Init Duration

Cold start có thể gồm khởi tạo runtime, tải class, chạy static initializer, tạo client và thiết lập kết nối. Với Java, class loading, framework bootstrap và JIT warm-up có thể làm phần khởi tạo đáng kể.

Trong AWS Lambda, Init Duration được thể hiện riêng trong REPORT log cho những invocation có giai đoạn init tương ứng. Duration của handler và Init Duration cần được phân tích riêng để tránh quy toàn bộ latency cho code xử lý request.

Một cấu hình memory cao hơn có thể rút ngắn một phần init nếu function được cấp thêm CPU, nhưng không thay thế việc giảm dependency nặng hoặc tránh khởi tạo không cần thiết.

### 4.4. Metric theo trigger

| Trigger | Metric cần theo dõi |
|---|---|
| HTTP | Integration latency, response code, request rate, throttles |
| SQS | ApproximateAgeOfOldestMessage, messages visible, DLQ depth, retry |
| Kinesis/DynamoDB Streams | IteratorAge, batch failure, checkpoint lag |
| Async invocation | Event age, retry, dropped event |
| Scheduled | Lateness, duration, missed/overlapping run |

Không chỉ tối ưu Duration của function. Một function có Duration thấp nhưng queue age tăng liên tục vẫn không đáp ứng yêu cầu xử lý.

## 5. Hiểu memory của Java runtime

Memory allocation của function thường là giới hạn cho toàn bộ execution environment hoặc container, không chỉ heap Java.

Một JVM process có thể sử dụng:

- **Java heap:** object, array và phần lớn dữ liệu ứng dụng.
- **Metaspace:** metadata của class.
- **Code cache:** mã máy được JIT compiler tạo ra.
- **Thread stack:** vùng nhớ cho từng thread.
- **Direct buffer:** buffer ngoài heap, ví dụ NIO.
- **Native memory:** thư viện native, TLS, compression và runtime.
- **Các vùng nhớ của agent/extension:** nếu nền tảng triển khai thêm process hoặc extension có tính vào giới hạn tương ứng.

Nếu heap còn trống nhưng process vẫn vượt giới hạn memory, cần xem native memory, thread count, direct buffer và extension. Ngược lại, nếu heap thường xuyên gần max heap, GC có thể chạy dày hơn và làm tăng tail latency.

### 5.1. Quan sát heap và non-heap trong Java

Có thể đọc các chỉ số JVM cơ bản:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;

public final class JvmMemorySnapshot {
    private JvmMemorySnapshot() {
    }

    public static void logSnapshot() {
        var memoryBean = ManagementFactory.getMemoryMXBean();

        MemoryUsage heap = memoryBean.getHeapMemoryUsage();
        MemoryUsage nonHeap = memoryBean.getNonHeapMemoryUsage();

        long maxHeap = Runtime.getRuntime().maxMemory();
        long freeHeap = Runtime.getRuntime().freeMemory();

        System.out.printf(
                "heapUsed=%d heapCommitted=%d heapMax=%d " +
                "nonHeapUsed=%d runtimeMaxHeap=%d freeHeap=%d%n",
                heap.getUsed(),
                heap.getCommitted(),
                heap.getMax(),
                nonHeap.getUsed(),
                maxHeap,
                freeHeap);
    }
}
~~~

Các giá trị này giúp phân tích JVM, nhưng không thay thế Max Memory Used của nền tảng. Runtime.maxMemory phản ánh giới hạn heap mà JVM nhận biết, không phải toàn bộ memory quota của function.

Không nên log snapshot ở mọi invocation nếu điều đó tạo quá nhiều log và chi phí. Có thể lấy mẫu, ghi ở benchmark hoặc phát custom metric với cardinality thấp.

### 5.2. Chú ý thread và direct buffer

Một thread pool quá lớn có thể tiêu thụ thread stack và tạo nhiều request đồng thời tới dependency. Direct buffer có thể dùng native memory ngoài heap. Connection pool quá lớn có thể làm tăng socket, thread và memory dù heap vẫn ổn.

Đặt giới hạn cho executor, HTTP connection pool, database connection pool và buffer theo concurrency thực tế. Không tạo một thread pool mới cho mỗi invocation nếu có thể tái sử dụng một client/thread pool an toàn trong execution environment.

## 6. Xác định bottleneck CPU-bound, memory-bound hay I/O-bound

Trước khi tăng memory, phân loại workload.

| Dấu hiệu | Bottleneck có thể có | Hướng xử lý |
|---|---|---|
| CPU gần bão hòa, wall time cao | CPU-bound | Tăng CPU nếu có thể, tối ưu thuật toán |
| Memory gần giới hạn, GC nhiều | Memory-bound | Tăng memory, giảm allocation/working set |
| CPU thấp, thời gian chờ cao | I/O-bound | Tối ưu network, connection pool, timeout |
| p99 cao nhưng p50 tốt | Tail latency | Tìm outlier, lock, GC, cold start, retry |
| Thời gian init cao | Cold start/bootstrap | Giảm classpath/init, tái sử dụng client, cân nhắc provisioned capacity |
| Throttles tăng | Concurrency/quota | Điều chỉnh concurrency, tải và downstream capacity |

CPU time và wall-clock time khác nhau. Một function có thể chạy 100 ms CPU nhưng mất 2 giây vì chờ database. Tăng CPU có thể ít cải thiện nếu phần lớn thời gian nằm ở network wait.

Dùng profiler hoặc trace để xác định đoạn code tốn thời gian. Với Java, Java Flight Recorder (JFR), async-profiler hoặc profiler phù hợp với runtime có thể giúp tìm hot method, allocation pressure, lock contention và GC pause. Profiling production cần được bật có kiểm soát vì có thể tạo overhead.

## 7. Điều chỉnh memory để đổi lấy CPU

Trên AWS Lambda, tăng memory đồng thời tăng lượng CPU được cấp. Vì vậy, một function CPU-bound đôi khi chạy nhanh hơn đáng kể khi tăng memory, dù bản thân dữ liệu không cần thêm heap.

Các workload thường hưởng lợi:

- Nén/giải nén file.
- Mã hóa, giải mã hoặc ký dữ liệu.
- Parse JSON/XML lớn.
- Chuyển đổi ảnh hoặc tài liệu.
- Tính toán và xử lý batch.
- Khởi tạo framework Java nặng.

Nếu function chủ yếu chờ HTTP hoặc database, tăng memory có thể không làm latency giảm tương ứng. Cần benchmark nhiều mức memory và so sánh cả duration lẫn GB-seconds.

### 7.1. Đừng suy luận chỉ từ phần trăm heap

Heap sử dụng 30% không chứng minh function đang được cấp thừa memory. Có thể function bị giới hạn CPU và cần memory cao hơn để nhận thêm CPU. Ngược lại, heap sử dụng 90% chưa chắc cần tăng memory nếu có thể giảm object allocation hoặc sửa memory leak.

Hãy so sánh:

- Max Memory Used ở cấp nền tảng.
- Heap used/max và GC behavior.
- CPU profile hoặc CPU utilization nếu nền tảng cung cấp.
- Duration p50/p95/p99.
- Cost trên mỗi công việc thành công.

## 8. Chọn memory bằng benchmark có kiểm soát

Một cách thực tế là thử nhiều mức memory trên cùng một workload. Không thay đổi code, payload, concurrency hoặc downstream cùng lúc.

Quy trình:

1. Chọn memory hiện tại làm baseline.
2. Chọn một số mức thấp/cao hơn trong giới hạn nền tảng.
3. Chạy cùng tập payload đại diện.
4. Lặp lại đủ nhiều lần để có phân bố.
5. Tách cold start và warm invocation.
6. Ghi Duration, p95/p99, Max Memory Used, error và cost.
7. Chọn cấu hình đáp ứng SLO với chi phí phù hợp.
8. Chạy lại ở concurrency gần production để xác nhận.

Với AWS Lambda, AWS Lambda Power Tuning là một công cụ mã nguồn mở dùng Step Functions để chạy function ở nhiều mức memory rồi so sánh thời gian và chi phí ước tính. Công cụ giúp tự động hóa phép thử, nhưng kết quả vẫn phụ thuộc payload, downstream, concurrency và cách tạo dữ liệu thử. Chạy trong account/môi trường kiểm thử, kiểm soát số invocation và không dùng dữ liệu production nhạy cảm.

Ví dụ bảng dưới đây là số liệu giả định nhằm minh họa cách tính, không phải kết quả đo từ một ứng dụng thật:

| Memory | Mean duration | p95 | Max memory used | Memory × mean duration |
|---:|---:|---:|---:|---:|
| 512 MB | 2,40 s | 3,80 s | 455 MB | 1,20 GB-s |
| 1024 MB | 1,30 s | 2,00 s | 470 MB | 1,30 GB-s |
| 1536 MB | 0,82 s | 1,20 s | 490 MB | 1,23 GB-s |
| 2048 MB | 0,55 s | 0,82 s | 500 MB | 1,10 GB-s |

Trong ví dụ, 2048 MB cho p95 tốt nhất và GB-seconds thấp nhất trong bốn lựa chọn. Mức 1024 MB nhanh hơn baseline nhưng có GB-seconds cao hơn. Điều này cho thấy memory cao hơn không nhất thiết đắt hơn trên mỗi invocation nếu duration giảm đủ nhiều.

Công thức GB-seconds ở bảng là memory tính bằng GB nhân mean duration tính bằng giây. Billing thực tế còn phụ thuộc cách nền tảng làm tròn thời gian, loại invocation, kiến trúc, tính năng bật thêm và bảng giá hiện hành. Hãy dùng dữ liệu billing/usage thật để quyết định.

## 9. Đo chi phí trên mỗi công việc thành công

Chi phí không chỉ là memory nhân duration. Một mô hình khái quát:

\[
Cost \approx RequestCost + GBSeconds \times UnitPrice + OtherCharges
\]

Trong đó:

- RequestCost phụ thuộc số invocation.
- GBSeconds phụ thuộc memory được cấu hình và thời gian tính phí.
- OtherCharges có thể gồm provisioned concurrency, data transfer, log ingestion, storage, extension hoặc dịch vụ downstream.

Nên tính thêm retry. Nếu một message cần ba invocation mới xử lý thành công, cost trên mỗi message hoàn tất cao hơn một invocation. Một timeout có thể làm function bị retry, tạo thêm chi phí database, queue và network.

Metric nên theo dõi:

- Cost trên 1.000 request thành công.
- Cost trên một message hoặc batch hoàn tất.
- Tỷ lệ retry và DLQ.
- Chi phí log và trace.
- Chi phí provisioned concurrency nếu sử dụng.
- Chi phí downstream do function tạo ra.

Không tối ưu cost bằng cách giảm memory đến mức làm tăng timeout hoặc retry. Cấu hình rẻ nhất trên mỗi invocation có thể không phải cấu hình rẻ nhất trên mỗi công việc thành công.

## 10. Tối ưu CPU cho Java

Nếu workload CPU-bound, cần kết hợp cấu hình tài nguyên và tối ưu code.

Các bước hữu ích:

- Profile hot method trước khi thay thuật toán.
- Tránh parse cùng payload nhiều lần.
- Giảm object allocation trong vòng lặp nóng.
- Dùng streaming parser cho dữ liệu lớn nếu phù hợp.
- Tránh serialize/deserialize không cần thiết.
- Chọn thuật toán và cấu trúc dữ liệu phù hợp.
- Giới hạn parallelism theo CPU được cấp.
- Tránh tạo quá nhiều thread và context switch.
- Tái sử dụng client thread-safe thay vì khởi tạo lại.

Không dùng parallel stream hoặc thread pool lớn với giả định function có nhiều CPU. Trên FaaS, số CPU có thể thay đổi theo memory tier hoặc cấu hình runtime. Parallelism quá cao có thể làm tăng contention và memory mà không tăng throughput.

### 10.1. Đo thời gian đoạn code

Dùng System.nanoTime cho khoảng thời gian trong cùng process:

~~~java
long startedAt = System.nanoTime();

OrderResult result = orderService.process(command);

long elapsedNanos = System.nanoTime() - startedAt;
double elapsedMillis = elapsedNanos / 1_000_000.0;

// Gửi metric có tên và dimension giới hạn.
// Tránh log từng invocation nếu volume lớn.
metrics.recordDuration("order.process", elapsedMillis);
~~~

Không dùng System.currentTimeMillis để đo duration ngắn vì đồng hồ wall-clock có thể bị điều chỉnh. Không ghi customer ID, request ID hoặc giá trị không giới hạn vào metric dimension vì cardinality cao.

## 11. Tối ưu memory và garbage collection

Allocation rate cao có thể khiến GC chạy thường xuyên, làm tăng latency và CPU. Một số hướng xử lý:

- Tránh tạo object tạm trong vòng lặp lớn.
- Không giữ collection hoặc cache không giới hạn.
- Dùng streaming thay vì tải toàn bộ file vào heap.
- Giới hạn batch size và payload.
- Đặt TTL/size bound cho cache.
- Tránh giữ reference tới request data sau invocation.
- Chọn GC và JVM option phù hợp với runtime, sau khi đo.

Không nên thay GC collector hoặc JVM flags chỉ vì một bài viết khuyên dùng. Ghi GC log hoặc JFR trong benchmark, quan sát pause time, allocation rate và heap occupancy rồi mới thay đổi.

Với Java Lambda, một cache static có thể tồn tại qua nhiều invocation trong cùng execution environment. Cache đó cần giới hạn kích thước và vòng đời; nếu không, memory có thể tăng dần khi environment được tái sử dụng. Không dùng static field làm nơi lưu trạng thái nghiệp vụ cần tồn tại bền vững.

## 12. Đặt timeout theo deadline và SLO

Timeout phải đủ cho một request hợp lệ trong điều kiện tải dự kiến, nhưng không quá dài đến mức giữ tài nguyên khi dependency đã treo. Khi function chạm timeout, nền tảng kết thúc invocation; không dựa vào finally block, shutdown hook hoặc thao tác cleanup để hoàn tất sau thời điểm đó. Những thay đổi cần được ghi bền vững trước deadline và phải có thể phục hồi khi invocation bị dừng.

Một cách đặt timeout:

1. Xác định SLO latency hoặc thời gian tối đa cho công việc.
2. Đo p95/p99 ở tải production-like.
3. Phân bổ ngân sách cho từng bước: xác thực, database, HTTP dependency, xử lý và ghi kết quả.
4. Đặt timeout cho từng dependency thấp hơn deadline còn lại.
5. Đặt function timeout đủ để xử lý hợp lệ và cleanup cần thiết.
6. Đảm bảo caller hoặc gateway có deadline tương thích.
7. Kiểm tra retry và visibility timeout của trigger.

Không đặt timeout chỉ bằng p99 cộng một con số tùy ý. Cần xét SLO, độ biến động, giới hạn caller và tác động của request bị treo. Nếu p99 cao do một dependency bất ổn, tăng timeout có thể làm hệ thống giữ request lâu hơn mà không sửa nguyên nhân.

### 12.1. Timeout theo tầng

Ví dụ một HTTP-triggered function gọi service và database:

~~~text
Client deadline:            8.0 s
API gateway integration:    7.0 s
Function timeout:           6.0 s
External API timeout:       2.0 s
Database statement timeout: 1.5 s
Cleanup / response budget:  phần thời gian còn lại
~~~

Các con số chỉ minh họa thứ tự deadline. Trong thực tế cần tính cả thời gian gateway, DNS, TLS, retry, connection acquisition và serialization. Timeout ở tầng trong nên ngắn hơn deadline còn lại của tầng ngoài để ứng dụng có thể trả lỗi có kiểm soát.

Nếu gateway timeout trước function, client có thể nhận lỗi trong khi function vẫn tiếp tục xử lý. Client retry có thể tạo một invocation thứ hai. Vì vậy, timeout phải được thiết kế cùng idempotency.

### 12.2. Timeout dependency và retry

Đặt connect timeout, read timeout và overall request timeout riêng khi thư viện hỗ trợ. Không retry một request đã hết deadline. Dùng exponential backoff với jitter cho lỗi tạm thời và giới hạn tổng thời gian retry.

Không retry lỗi không thể khắc phục như validation failure hoặc AccessDenied. Retry cần dựa trên loại lỗi và semantics của thao tác.

## 13. Timeout trong Lambda và trigger

Mỗi trigger có giới hạn riêng:

- HTTP client/gateway có timeout chờ response.
- Lambda function có timeout invocation.
- SQS có visibility timeout.
- Stream có checkpoint, batch window và cơ chế retry.
- Async invocation có retry policy và event age.
- Scheduler có thể kích hoạt chồng lấn nếu lần chạy trước chưa kết thúc.

Với AWS Lambda, timeout function có giới hạn tối đa 15 phút. Nếu một tác vụ cần lâu hơn, nên chia thành các bước, đưa vào queue hoặc dùng workflow orchestration thay vì cố kéo dài một invocation.

Với SQS event source mapping, visibility timeout cần đủ dài để function xử lý và để nền tảng retry an toàn. AWS khuyến nghị visibility timeout ít nhất gấp sáu lần function timeout, cộng thêm maximum batching window nếu dùng batching. Kiểm tra đúng hướng dẫn của trigger và cấu hình thực tế trước khi triển khai.

Không giả định HTTP, SQS, Kinesis và asynchronous invocation có cùng retry semantics. Mỗi nguồn cần được cấu hình và kiểm thử riêng.

## 14. Dùng remaining time để dừng công việc có kiểm soát

AWS Lambda Java handler có thể đọc thời gian còn lại từ Context. Ứng dụng có thể tránh bắt đầu một thao tác mới khi không còn đủ ngân sách.

~~~java
import com.amazonaws.services.lambda.runtime.Context;

public final class DeadlineGuard {
    private static final long SAFETY_MARGIN_MS = 300;

    private DeadlineGuard() {
    }

    public static boolean canStart(Context context, long requiredMs) {
        long remaining = context.getRemainingTimeInMillis();
        return remaining > requiredMs + SAFETY_MARGIN_MS;
    }
}
~~~

Đây là guard đơn giản, không thay thế timeout của HTTP client hoặc database. Nếu không còn đủ thời gian, application cần chọn hành vi an toàn: trả lỗi để nguồn retry, lưu checkpoint, hoặc chuyển công việc còn lại sang queue. Không ACK message trước khi kết quả được lưu bền vững.

Với các nền tảng khác, dùng API deadline/cancellation tương ứng của runtime. Không giả định Context của AWS có mặt trong mọi Java FaaS.

## 15. Concurrency, throughput và timeout

Concurrency là số invocation đang chạy cùng thời điểm. Một quy tắc ước lượng cho workload ổn định:

\[
Concurrency \approx ArrivalRate \times AverageDuration
\]

Nếu hệ thống nhận 100 request mỗi giây và mỗi request mất trung bình 0,5 giây, concurrency trung bình xấp xỉ 50. Nếu duration tăng lên 2 giây, concurrency trung bình có thể tăng lên khoảng 200 với cùng arrival rate.

Timeout dài không trực tiếp làm tăng concurrency khi request luôn hoàn tất nhanh, nhưng khi dependency bị treo, invocation tồn tại lâu hơn và chiếm slot lâu hơn. Điều đó có thể gây throttling hoặc làm queue backlog tăng.

Cần theo dõi:

- ConcurrentExecutions và Throttles.
- Reserved concurrency và account quota.
- Queue age hoặc iterator age.
- Duration theo percentile.
- Downstream connection count và latency.
- Số request đang chờ trong client pool.

Không tăng concurrency mà không kiểm tra capacity của database hoặc API downstream. Function có thể scale nhanh hơn hệ thống mà nó gọi, tạo connection storm và làm sự cố lan rộng.

## 16. Tối ưu theo loại workload

| Loại workload | Dấu hiệu chính | Hướng tối ưu |
|---|---|---|
| CPU-bound | CPU cao, xử lý tính toán chiếm phần lớn thời gian | Thử memory tier cao hơn, profile thuật toán |
| Memory-bound | Max Memory Used sát giới hạn, GC/OOM | Tăng memory, giảm working set và allocation |
| I/O-bound | CPU thấp, nhiều thời gian chờ | Tối ưu network, connection pool và downstream timeout |
| Batch | Throughput thấp, payload lớn | Điều chỉnh batch size, memory và parallelism |
| Latency-sensitive HTTP | p95/p99 cao, cold start rõ | Giảm init, tối ưu dependency, cân nhắc provisioned capacity |
| Event-driven queue | Queue age và retry tăng | Điều chỉnh concurrency, batch, visibility timeout và idempotency |

Không có một cấu hình tối ưu cho mọi loại workload. Một function xử lý ảnh và một function gọi database có thể cần memory/CPU/timeout rất khác nhau dù cùng runtime Java.

## 17. Ví dụ cấu hình Lambda bằng SAM

Một function có thể khai báo memory và timeout trong template:

~~~yaml
Resources:
  ResizeImageFunction:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java17
      Handler: com.example.ResizeImageHandler::handleRequest
      CodeUri: target/function.zip
      MemorySize: 2048
      Timeout: 20
~~~

Các giá trị 2048 MB và 20 giây chỉ là ví dụ minh họa. Không sao chép vào production nếu chưa đo. Runtime Java được chọn phải còn được nền tảng hỗ trợ tại thời điểm triển khai; template cần pin các cấu hình khác như architecture, role, environment, tracing và trigger theo nhu cầu thực tế.

Khi đổi MemorySize hoặc Timeout, tạo một phiên bản cấu hình có thể truy vết, chạy benchmark và so sánh trước/sau. Tránh thay nhiều tham số cùng lúc vì sẽ khó biết thay đổi nào tạo ra kết quả.

## 18. Java-specific: giảm thời gian khởi tạo và chi phí mỗi invocation

Một số việc có thể giúp Java function:

- Tạo AWS SDK client và HTTP client một lần trong execution environment.
- Tránh quét classpath hoặc reflection không cần thiết khi khởi tạo.
- Giảm số dependency và framework auto-configuration.
- Chỉ tải cấu hình cần dùng.
- Dùng connection pool có giới hạn và tái sử dụng an toàn.
- Đo cold start riêng với warm invocation.
- Kiểm tra GC và JIT behavior với workload thực.
- Cân nhắc SnapStart hoặc provisioned concurrency nếu nền tảng hỗ trợ và latency yêu cầu.

Tái sử dụng client không có nghĩa giữ dữ liệu request hoặc security context của user trong static field. Các object chia sẻ phải thread-safe và không chứa trạng thái invocation có thể rò rỉ sang request tiếp theo.

SnapStart, provisioned concurrency và native image có thể thay đổi startup behavior nhưng có trade-off về snapshot, tương thích thư viện, memory và chi phí. Đánh giá chúng sau khi có baseline; không bật chỉ vì muốn giảm cold start mà chưa đo tỷ lệ cold invocation.

## 19. Quy trình tối ưu lặp lại

Một vòng tối ưu có thể thực hiện theo thứ tự:

1. **Đặt mục tiêu:** ví dụ p95 dưới 700 ms, error rate dưới ngưỡng và cost mỗi đơn thành công không vượt ngân sách.
2. **Đo baseline:** dùng payload và concurrency đại diện, tách cold/warm.
3. **Xác định bottleneck:** CPU, heap/native memory, I/O, lock, GC hay downstream.
4. **Thay đổi một yếu tố:** memory, CPU, code, connection pool hoặc timeout.
5. **Chạy benchmark lặp lại:** lấy phân bố và kiểm tra độ ổn định.
6. **So sánh cost và latency:** dùng GB-seconds, billed duration và cost per success.
7. **Kiểm thử tải và lỗi:** timeout, retry, duplicate event, downstream chậm.
8. **Canary cấu hình mới:** theo dõi production metrics và rollback nếu guardrail xấu đi.
9. **Ghi lại quyết định:** cấu hình, commit, dữ liệu đo, lý do chọn và ngày đánh giá lại.

Không coi một lần chạy nhanh hơn là bằng chứng. Kết quả có thể bị ảnh hưởng bởi cache, JIT, noisy neighbor, network hoặc downstream load. Chạy nhiều lần, dùng cùng điều kiện và xem cả percentile.

## 20. Những lỗi thường gặp

**Tăng timeout để che giấu bottleneck:** Request vẫn chậm và giữ concurrency lâu hơn. Profile và sửa nguyên nhân trước.

**Tăng memory mà không benchmark:** Có thể làm chi phí tăng mà duration không giảm. Thử nhiều mức và so sánh GB-seconds.

**Chỉ xem average duration:** Tail latency vẫn có thể rất cao. Theo dõi p95/p99.

**Chỉ xem heap:** Native memory, thread stack và direct buffer cũng dùng quota. Đối chiếu JVM metrics với Max Memory Used.

**Đặt timeout function lớn hơn mọi timeout bên ngoài:** Caller có thể bỏ cuộc trong khi function vẫn chạy. Thiết kế deadline theo tầng và idempotency.

**Không tính retry vào cost:** Một công việc lỗi có thể tạo nhiều invocation và downstream calls. Tính cost trên mỗi kết quả thành công.

**Tăng concurrency không kiểm tra downstream:** Database hoặc API có thể quá tải. Đặt giới hạn và đo connection/latency.

**Đặt connection pool quá lớn:** Mỗi environment tạo nhiều connection, gây connection storm. Tính tổng connection theo concurrency và số environment.

**Benchmark chỉ warm invocation:** Bỏ qua cold start và init overhead. Đo riêng cold/warm.

**Dùng một payload nhỏ cho mọi phép thử:** Không phát hiện memory pressure với payload lớn. Dùng phân bố input thực tế.

**Tối ưu một function làm xấu cả workflow:** Duration giảm nhưng queue retry hoặc database load tăng. Theo dõi metric end-to-end.

## 21. Checklist trước khi phát hành cấu hình hiệu năng

- [ ] Có baseline và SLO latency/throughput rõ ràng.
- [ ] Đã đo p50, p95, p99 và error rate.
- [ ] Đã tách cold start khỏi warm execution.
- [ ] Đã đọc Max Memory Used và JVM heap/non-heap metrics.
- [ ] Đã phân loại workload CPU-bound, memory-bound hay I/O-bound.
- [ ] Memory tier được chọn qua benchmark cùng payload và concurrency.
- [ ] Cost được so sánh bằng billing duration/GB-seconds thực tế.
- [ ] Timeout function phù hợp với deadline của caller và trigger.
- [ ] Timeout của HTTP/database client ngắn hơn deadline còn lại.
- [ ] Retry, visibility timeout, DLQ và idempotency đã được kiểm thử.
- [ ] Concurrency phù hợp với quota và capacity downstream.
- [ ] Connection pool, thread pool và batch size có giới hạn.
- [ ] Có guardrail cho p95/p99, error, throttles, queue age và cost.
- [ ] Đã canary cấu hình mới và có phương án rollback.
- [ ] Cấu hình và kết quả benchmark được lưu cùng release record.

## Kết luận

Điều chỉnh memory, CPU và timeout là một bài toán đo lường. Trên AWS Lambda, memory còn quyết định lượng CPU được cấp, nên tăng memory có thể giảm duration của workload CPU-bound và đôi khi giảm cả cost trên mỗi invocation. Với workload I/O-bound, cần tập trung vào network, connection pool và dependency latency. Java cần được quan sát ở cả heap lẫn non-heap vì quota của function bao gồm nhiều loại memory ngoài heap.

Timeout phải phản ánh SLO, deadline của caller, giới hạn trigger và retry behavior. Timeout quá ngắn làm công việc thất bại; timeout quá dài có thể giữ concurrency và làm tăng backlog khi dependency gặp sự cố. Benchmark với payload và concurrency đại diện, theo dõi percentile, Max Memory Used, GB-seconds và cost trên mỗi công việc thành công sẽ giúp chọn cấu hình có cơ sở và kiểm chứng được.

