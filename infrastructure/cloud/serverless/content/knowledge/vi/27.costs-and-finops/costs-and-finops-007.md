# Tối ưu batch, thời gian thực thi và dung lượng được cấp

Chi phí serverless không chỉ phụ thuộc vào số lần gọi function. Với workload xử lý message hoặc stream, cách gom record thành batch, thời gian chờ gom batch, thời gian xử lý, memory/CPU và capacity dành sẵn có thể làm thay đổi đáng kể cả chi phí lẫn độ trễ. Một cấu hình batch lớn có thể giảm số invocation nhưng làm tăng thời gian chờ, kích thước payload và lượng công việc phải retry khi có lỗi. Một cấu hình capacity lớn có thể giữ latency ổn định nhưng tạo chi phí ngay cả khi traffic thấp.

Bài học này dùng AWS Lambda, Amazon SQS và Java làm ví dụ chính, đồng thời đối chiếu với Always Ready của Azure Functions và minimum instances của Google Cloud Run. Mục tiêu là chọn batch size, batching window, memory, concurrency và provisioned capacity dựa trên workload đo được, sau đó đánh giá chi phí trên mỗi đơn vị nghiệp vụ thành công.

## 1. Nhìn chi phí theo toàn bộ luồng xử lý

Một pipeline serverless xử lý message thường có các thành phần:

~~~mermaid
flowchart LR
    P["Producer"] --> Q["Queue / stream"]
    Q --> E["Event source mapping / poller"]
    E --> B["Batch payload"]
    B --> F["Java function"]
    F --> D[("Database / API / storage")]
    F --> R["Success / partial failure"]
    R --> Q
    F --> DLQ["DLQ / quarantine"]
~~~

Mỗi thành phần có thể tạo chi phí hoặc ảnh hưởng tới thời gian hoàn tất:

- Queue hoặc stream có phí request, lưu trữ, throughput hoặc partition.
- Event source mapping có thể dùng polling tự động hoặc provisioned pollers.
- Mỗi invocation có phí request và compute duration theo memory được cấp.
- Provisioned Concurrency có phí capacity trong khoảng thời gian được cấu hình.
- Log, metric, tracing, data transfer, NAT, database connection và API đối tác cũng có chi phí.
- Retry và duplicate làm tăng số lần xử lý cho cùng một message.
- DLQ và replay tạo thêm lưu trữ, request và compute.

Không tối ưu một dòng chi phí riêng lẻ nếu nó làm tăng chi phí ở phần khác. Ví dụ, tăng batch size giảm invocation count nhưng có thể kéo dài duration, làm queue age tăng và tạo nhiều công việc phải chạy lại khi batch lỗi.

## 2. Các loại capacity thường bị nhầm lẫn

Trong AWS Lambda, có ba loại cấu hình cần phân biệt:

| Cấu hình | Cấp tài nguyên nào? | Giải quyết vấn đề gì? | Tạo phí capacity riêng? |
|---|---|---|---|
| Batch size / batching window | Số record và thời gian gom record | Giảm overhead invocation, cân bằng latency và throughput | Không có phí capacity riêng |
| Reserved Concurrency | Giới hạn và dành phần concurrency cho function | Bảo vệ function/dependency, tránh function khác chiếm hết account concurrency | Không tính phí riêng cho cấu hình |
| Provisioned Concurrency | Execution environment đã khởi tạo sẵn cho version/alias | Giảm cold start của invocation dùng capacity này | Có |
| Provisioned Pollers | Polling resources riêng cho event source mapping | Tăng tốc độ đọc queue/stream và kiểm soát throughput đầu vào | Có, theo EPU-hours |

Provisioned Concurrency chuẩn bị sẵn môi trường thực thi function. Provisioned Pollers chuẩn bị sẵn tài nguyên đọc sự kiện từ SQS hoặc Kafka. Chúng giải quyết hai nút thắt khác nhau.

Reserved Concurrency không phải số instance luôn nóng. Nó giới hạn tổng concurrency của function và dành phần quota tương ứng trong account. Nếu function cần environment mới, vẫn có thể gặp cold start.

## 3. Mô hình tính chi phí Lambda

Với Lambda Event Functions, chi phí cơ bản thường gồm request và compute duration. Compute được tính theo GB-seconds:

\[
GB\text{-}seconds = Memory_{GB} \times BilledDuration_{seconds}
\]

Với workload không dùng capacity dành sẵn, có thể ước lượng:

\[
C_{function} =
N_{invocations} \times Price_{request}
+
GB\text{-}seconds \times Price_{compute}
\]

Tổng chi phí workload cần cộng thêm queue, event poller, log, data transfer, database, cache, NAT và các dependency khác.

Với batch processing, số invocation không bằng số message. Nếu có một triệu message và batch thực tế trung bình chứa 100 message, số invocation lý thuyết gần 10.000 thay vì một triệu. Tuy nhiên, batch thực tế có thể nhỏ hơn cấu hình do batching window hết hạn, payload chạm giới hạn hoặc traffic thấp.

Một công thức FinOps hữu ích là:

\[
CostPerSuccess =
\frac{TotalWorkloadCost}{SuccessfulBusinessOperations}
\]

Mẫu số phải là số nghiệp vụ hoàn tất hợp lệ, không chỉ số invocation thành công. Nếu một message được xử lý ba lần hoặc bị đưa vào DLQ, chi phí của nó vẫn đã phát sinh.

## 4. Batch size và batching window

Với event source mapping, Lambda gom record thành batch trước khi invoke function. Hai cấu hình quan trọng:

- **Batch size:** số record tối đa trong một batch.
- **Batching window:** thời gian tối đa chờ để gom thêm record.

Lambda invoke function khi một trong các điều kiện xảy ra: batching window hết hạn, batch đạt batch size hoặc payload đạt giới hạn 6 MB. Giới hạn payload tính cả metadata do nguồn sự kiện và Lambda thêm vào; vì vậy số record thực tế có thể ít hơn batch size cấu hình.

Đối với Amazon SQS:

| Thuộc tính | Standard queue | FIFO queue |
|---|---:|---:|
| Batch size mặc định | 10 | 10 |
| Batch size tối đa | 10.000 | 10 |
| Batching window | 0–300 giây | Không hỗ trợ |
| Giới hạn payload invocation | 6 MB | 6 MB |
| Partial batch response | Có | Có, cần giữ thứ tự |

Khi batch size lớn hơn 10, phải đặt batching window tối thiểu 1 giây. Với SQS standard, nếu traffic thấp, Lambda có thể chờ tới khoảng 20 giây trước khi invoke ngay cả khi batching window được đặt thấp hơn mức đó. Điều này cần được tính vào latency budget.

Các event source khác có giới hạn batch size và window riêng. Không sao chép giá trị SQS sang Kinesis, DynamoDB Streams, Kafka, Amazon MQ hoặc DocumentDB mà chưa kiểm tra tài liệu của nguồn tương ứng.

## 5. Chọn batch size theo latency và throughput

Batch lớn có thể giảm số lần invoke và tăng số record xử lý trên mỗi invocation. Tuy nhiên, batch lớn không phải lúc nào cũng nhanh hơn.

| Batch size | Lợi ích | Rủi ro |
|---|---|---|
| Nhỏ | Latency thấp, lỗi cô lập, ít record phải xử lý lại | Nhiều invocation và polling overhead |
| Trung bình | Cân bằng throughput và latency | Cần benchmark theo payload/duration |
| Lớn | Giảm invocation count, tận dụng tốt overhead cố định | Batch duration dài, memory cao, payload lớn và retry tốn kém |

Ví dụ: nếu mỗi record cần 5 ms xử lý tuần tự, batch 10 record có thể cần khoảng 50 ms cộng overhead. Batch 100 record có thể cần khoảng 500 ms cộng overhead. Số invocation giảm 10 lần nhưng thời gian xử lý một invocation tăng tương ứng.

Nếu xử lý song song, duration có thể giảm nhưng CPU, thread, database connection và API concurrency tăng. Batch size phải được chọn cùng với mức parallelism và giới hạn dependency.

Một cách thử nghiệm thực tế là benchmark batch size 10, 25, 50, 100 và 250, sau đó đo:

- Throughput record/giây.
- p50/p95/p99 từ lúc message được gửi tới lúc xử lý xong.
- Duration của invocation.
- Memory peak.
- Retry và duplicate.
- Queue age.
- Chi phí trên mỗi nghìn record thành công.

Không chọn batch size chỉ theo số invocation thấp nhất. Hãy chọn cấu hình đạt SLO với chi phí tổng thấp nhất.

## 6. Đặt batching window theo độ trễ nghiệp vụ

Batching window tạo thêm thời gian chờ để thu thập record. Window lớn thường giúp batch đầy hơn khi traffic thưa, nhưng làm message mới phải chờ lâu hơn trước khi được xử lý.

Ví dụ:

- API event cần phản hồi trong vài giây: window bằng 0 hoặc rất nhỏ.
- Xử lý telemetry có thể chờ 5–10 giây: có thể dùng window lớn hơn để tăng batch fullness.
- Job tổng hợp theo phút: batching window dài hơn có thể phù hợp.
- FIFO queue cần thứ tự và không hỗ trợ batching window trong event source mapping SQS: tối ưu batch size trong giới hạn của FIFO.

Đừng dùng batching window để che một consumer không đủ throughput. Nếu queue age liên tục tăng, cần tăng khả năng xử lý, giảm duration hoặc điều chỉnh producer rate.

## 7. Payload size và giới hạn 6 MB

Giới hạn payload có thể khiến batch kết thúc trước khi đạt số record đã cấu hình. Một record có body lớn, message attributes nhiều hoặc metadata dài sẽ làm giảm số record trong batch.

Cần đo phân phối payload, không chỉ lấy giá trị trung bình. Nếu phần lớn message nhỏ nhưng một số message rất lớn, batch có thể dao động mạnh.

Các biện pháp:

- Chỉ gửi metadata và object reference trong message; lưu payload lớn ở object storage.
- Giới hạn message size theo contract.
- Dùng compression nếu consumer và producer có thể xử lý an toàn.
- Tránh lặp lại metadata không cần thiết trong từng record.
- Kiểm tra payload thực tế sau khi Lambda thêm metadata.
- Tách loại message lớn sang queue hoặc consumer riêng nếu chúng có profile xử lý khác.

Không nén dữ liệu chỉ để giảm payload nếu chi phí CPU và duration lớn hơn phần tiết kiệm. Hãy đo cả kích thước truyền và compute dùng để nén/giải nén.

## 8. Partial batch response giảm chi phí retry

Mặc định, nếu function xử lý batch có lỗi, toàn bộ batch có thể được gửi lại. Những record đã xử lý thành công có thể bị chạy lại, làm tăng compute, request tới dependency và nguy cơ side effect trùng.

Với SQS, cấu hình event source mapping để bật **ReportBatchItemFailures**. Function trả danh sách message ID thất bại; Lambda chỉ làm những message đó xuất hiện lại để retry. AWS Lambda Powertools for Java có Batch Processing utility để thực hiện partial batch response cho SQS, Kinesis và DynamoDB Streams.

Partial batch response không thay thế idempotency. Event source mapping vẫn có at-least-once delivery và duplicate vẫn có thể xảy ra. Với FIFO, cần dừng xử lý sau lỗi đầu tiên trong message group hoặc áp dụng quy tắc bảo toàn thứ tự tương ứng; không xử lý tiếp các record sau theo cách phá thứ tự nghiệp vụ.

## 9. Ví dụ Java xử lý SQS batch với partial failures

Ví dụ dưới đây xử lý từng record và trả về những message cần retry. Lỗi permanent được ghi vào quarantine bền vững trước khi coi record đã xử lý; lỗi transient được trả về để SQS retry.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public final class OrderBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    private final OrderService orderService = OrderService.create();
    private final QuarantineStore quarantine = QuarantineStore.create();

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event,
            Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                orderService.processIdempotently(message);

            } catch (PermanentRecordException error) {
                // Chỉ coi là đã xử lý khi quarantine đã ghi bền vững.
                quarantine.store(message, error.getCode());

            } catch (TransientDependencyException error) {
                failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                                message.getMessageId()
                        )
                );

            } catch (RuntimeException error) {
                // Lỗi chưa phân loại: retry có giới hạn theo redrive policy.
                failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                                message.getMessageId()
                        )
                );
            }
        }

        return new SQSBatchResponse(failures);
    }
}
~~~

Ví dụ dùng AWS Lambda Java Events và các lớp OrderService/QuarantineStore minh họa. Trong dự án thực tế, cần bổ sung constructor injection, timeout, logging, metrics và xử lý exception của quarantine store. Nếu ghi quarantine thất bại, record phải được báo là failed để không bị mất.

Event source mapping cần bật ReportBatchItemFailures. Nếu function ném exception ra ngoài handler, toàn batch có thể bị xem là thất bại; vì vậy hãy phân loại lỗi theo từng record và chỉ trả partial response khi tất cả record đã được xử lý hoặc đã được ghi quarantine an toàn.

## 10. Cấu hình SQS event source mapping

Ví dụ cập nhật batch size và batching window:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --batch-size 100 \
  --maximum-batching-window-in-seconds 2
~~~

Bật partial batch response:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --function-response-types ReportBatchItemFailures
~~~

Kiểm tra cấu hình hiện tại:

~~~bash
aws lambda get-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID
~~~

Các lệnh cần được chạy với quyền quản trị event source mapping phù hợp. Thay UUID bằng mapping thật và kiểm tra trạng thái sau khi cập nhật.

## 11. Visibility timeout và thời gian xử lý batch

SQS giữ message ở trạng thái invisible trong thời gian visibility timeout khi Lambda đang xử lý batch. Nếu function chưa hoàn tất trước khi timeout, message có thể xuất hiện lại và bị xử lý đồng thời hoặc lặp.

AWS khuyến nghị visibility timeout của queue ít nhất bằng sáu lần timeout của function. Nếu có batching window, cộng thêm thời gian batching window vào phép tính:

\[
VisibilityTimeout \geq 6 \times FunctionTimeout + BatchingWindow
\]

Đây là khuyến nghị cấu hình của AWS cho SQS event source mapping; vẫn cần kiểm thử duration thực tế, retry và throttling. Function timeout phải nhỏ hơn hoặc bằng visibility timeout của queue.

Ví dụ: function timeout 30 giây và batching window 5 giây thì mức visibility timeout khuyến nghị tối thiểu là 185 giây. Có thể chọn giá trị cao hơn nếu workload có tail latency hoặc downstream chậm.

Đặt visibility timeout quá ngắn có thể tạo duplicate processing. Đặt quá dài làm message lỗi phải chờ lâu mới được retry. Cần cân bằng với retry policy và yêu cầu phục hồi.

## 12. Retry, DLQ và chi phí của message lỗi

Một message lỗi có thể tiêu thụ chi phí nhiều lần: invocation retry, dependency call, log, trace và thời gian chờ. Nếu lỗi permanent nhưng bị retry như lỗi transient, chi phí sẽ tiếp tục tăng mà không tạo thêm giá trị.

Phân loại lỗi:

| Loại lỗi | Cách xử lý |
|---|---|
| Lỗi transient: timeout, 429, 503 | Retry có giới hạn với backoff và jitter |
| Lỗi permanent: schema sai, dữ liệu không hợp lệ | Quarantine hoặc DLQ |
| Lỗi authorization | Cảnh báo và sửa quyền; tránh retry vô hạn |
| Lỗi dependency diện rộng | Giảm concurrency/backpressure, mở circuit breaker |
| Lỗi không rõ | Retry giới hạn, log có correlation ID và chuyển DLQ |

Cấu hình redrive policy cho SQS với maxReceiveCount phù hợp. AWS khuyến nghị giá trị ít nhất 5 như điểm khởi đầu cho nhiều trường hợp, nhưng cần điều chỉnh theo loại lỗi và thời gian phục hồi dự kiến.

DLQ không phải nơi để quên message. Cần dashboard, cảnh báo, quy trình phân loại, sửa dữ liệu và replay theo batch nhỏ. Replay phải idempotent để không tạo side effect trùng.

## 13. Idempotency là điều kiện để batch lớn an toàn

Event source mapping xử lý ít nhất một lần, nên duplicate có thể xuất hiện khi function timeout, mất acknowledgment hoặc message được retry. Batch lớn làm tăng số record có thể được xử lý lại nếu không có partial batch response.

Mỗi nghiệp vụ cần một idempotency key ổn định, ví dụ event ID hoặc business operation ID. Dùng conditional write hoặc transaction để đảm bảo một key chỉ tạo side effect một lần.

Không dùng static map hoặc HashSet trong JVM làm kho idempotency. Execution environment có thể bị tái tạo và nhiều instance chạy song song. Trạng thái phải nằm trong database hoặc store bền vững có atomic operation.

Khi replay DLQ, giữ nguyên idempotency key gốc. Nếu tạo key mới cho mỗi lần replay, hệ thống có thể xử lý lại cùng một nghiệp vụ như một thao tác mới.

## 14. Tối ưu thời gian thực thi của Java function

Duration ảnh hưởng trực tiếp đến compute cost và throughput. Với Java, một số nguồn overhead thường gặp:

- Khởi tạo framework hoặc client trong mỗi invocation.
- Parse/serialize JSON lặp lại.
- Tạo connection mới cho từng record.
- Truy vấn database theo từng record thay vì bulk operation.
- Gọi API tuần tự dù dependency hỗ trợ batch.
- Logging payload lớn hoặc tạo trace quá chi tiết.
- Quét classpath hoặc reflection không cần thiết.
- Dùng thread pool lớn hơn số CPU hoặc khả năng downstream.

Khởi tạo client thread-safe ở ngoài handler để tái sử dụng giữa các invocation. Không lưu dữ liệu người dùng hoặc trạng thái nghiệp vụ mutable vào static field. Tối ưu serializer, query và API call trước khi tăng memory.

Nếu dependency hỗ trợ bulk write, gom các thao tác có thể gộp trong cùng batch. Tuy nhiên, bulk operation phải có semantics rõ ràng khi một phần record lỗi; nếu không, việc retry cả batch có thể gây duplicate.

## 15. Memory và CPU ảnh hưởng duration như thế nào?

Trong AWS Lambda, memory được cấu hình từ 128 MB tới 10.240 MB. CPU được cấp tỷ lệ với memory; ở khoảng 1.769 MB, function có lượng CPU tương đương một vCPU theo mô tả của AWS.

Tăng memory có thể giảm duration cho workload CPU-bound hoặc một số workload network-bound. Dù mức giá trên mỗi giây tăng, tổng GB-seconds có thể giữ nguyên hoặc giảm nếu function chạy nhanh hơn đủ nhiều.

Ví dụ minh họa:

| Memory | Duration | Compute tương đối |
|---:|---:|---:|
| 512 MB | 1,2 giây | 0,6 GB-s |
| 1.024 MB | 0,7 giây | 0,7 GB-s |
| 2.048 MB | 0,3 giây | 0,6 GB-s |

Bảng trên chỉ là số liệu giả định để minh họa trade-off, không phải benchmark thực tế. Cấu hình 2 GB có thể hoàn thành nhanh nhất và có compute tương đương cấu hình 512 MB. Nếu SLO quan trọng, lựa chọn nhanh hơn có thể đáng giá; nếu chỉ tối ưu cost, cần tính cả request, concurrency và downstream.

Không tăng memory theo cảm tính. Chạy benchmark ở nhiều mức memory, giữ nguyên code, payload, architecture và traffic pattern rồi so sánh duration, GB-seconds, error rate và cost per success.

## 16. Chọn architecture và runtime theo benchmark

AWS Lambda hỗ trợ x86_64 và arm64. Graviton/Arm có thể cải thiện price-performance cho một số workload, nhưng dependency native, JNI, library và container image phải tương thích.

Quy trình đánh giá:

1. Build artifact cho cả hai architecture nếu dependency cho phép.
2. Dùng cùng input, batch size, memory và concurrency.
3. Chạy đủ warm/cold samples.
4. Đo duration, memory, error rate và CPU-bound time.
5. So sánh giá theo Region và architecture.
6. Kiểm tra thư viện native, JDBC driver và observability extension.
7. Chọn cấu hình có cost per success và latency đạt mục tiêu.

Không chọn Arm chỉ vì đơn giá thấp hơn. Nếu dependency không tương thích hoặc duration tăng đủ lớn, tổng chi phí có thể cao hơn.

## 17. Parallel processing trong Java

Batch có thể xử lý tuần tự hoặc song song.

**Tuần tự** dễ giữ thứ tự, dễ kiểm soát transaction và ít tạo áp lực lên downstream. Nó phù hợp với FIFO, nghiệp vụ phụ thuộc thứ tự hoặc database có giới hạn connection thấp.

**Song song** có thể tăng throughput cho record độc lập, đặc biệt khi mỗi record chờ I/O. Tuy nhiên, thread count và concurrency cần bị giới hạn theo CPU, connection pool và rate limit của dependency.

Với CPU-bound task, số worker nên gần số CPU khả dụng. Với I/O-bound task, có thể dùng nhiều worker hơn nhưng phải giới hạn số request đồng thời tới database hoặc partner API.

Java 21 virtual threads giúp giảm chi phí tạo thread cho I/O blocking, nhưng không làm CPU xử lý nhanh hơn và không tăng giới hạn của database. Dùng semaphore hoặc bulkhead để giới hạn dependency concurrency.

AWS Lambda Powertools for Java Batch Processing hỗ trợ xử lý song song cho SQS standard, Kinesis và DynamoDB Streams; không dùng chế độ parallel cho SQS FIFO. Hãy benchmark vì parallelism không phải lúc nào cũng tốt hơn.

## 18. Ví dụ xử lý song song có giới hạn

Một mô hình I/O-bound có thể dùng executor với số worker được cấu hình:

~~~java
int workers = Integer.parseInt(
        System.getenv().getOrDefault("BATCH_WORKERS", "8")
);

ExecutorService executor =
        Executors.newFixedThreadPool(workers);

Semaphore downstreamLimit = new Semaphore(12);

void processRecord(OrderEvent event) throws Exception {
    downstreamLimit.acquire();
    try {
        partnerClient.send(event);
    } finally {
        downstreamLimit.release();
    }
}
~~~

Ví dụ minh họa giới hạn số thao tác đồng thời tới dependency. Trong Lambda, executor nên được tái sử dụng phù hợp với lifecycle của execution environment và phải được quản lý cẩn thận. Không tạo thread pool mới ở mỗi record hoặc mỗi invocation nếu không cần.

Số worker cần dựa trên memory/CPU và connection limit. Nếu có 10 Lambda execution environment, mỗi environment tạo 20 worker thì dependency có thể nhận tới 200 request đồng thời. Hãy tính concurrency ở cấp toàn hệ thống, không chỉ trong một JVM.

## 19. Throughput và concurrency

Với batch, throughput gần đúng:

\[
RecordsPerSecond \approx
ConcurrentInvocations \times
\frac{EffectiveBatchSize}{AverageBatchDuration}
\]

Ví dụ: 20 invocation đồng thời, mỗi batch 100 record và duration trung bình 0,5 giây:

\[
20 \times \frac{100}{0.5} = 4.000 \text{ records/second}
\]

Đây là ước lượng lý tưởng. Payload limit, poller capacity, downstream, retry, memory và thời gian batching có thể làm throughput thấp hơn.

Tăng concurrency chỉ giúp nếu dependency chịu được tải. Nếu database chỉ cho phép 100 connection mà mỗi Lambda environment mở 10 connection, chỉ 10 environment có thể chiếm hết connection pool. Cần sizing cả function concurrency và connection pool.

## 20. Reserved Concurrency để bảo vệ dependency

Reserved Concurrency đặt giới hạn tối đa và dành một phần concurrency cho function. Nó không làm nóng environment và không có khoản phí cấu hình riêng, nhưng phần quota được dành sẽ không khả dụng cho các function khác trong account.

Dùng Reserved Concurrency khi:

- Database có giới hạn connection.
- Partner API có rate limit.
- Function không được phép scale quá nhanh.
- Cần bảo vệ capacity cho workload quan trọng.
- Muốn giới hạn blast radius khi có message burst.

Ví dụ đặt concurrency tối đa:

~~~bash
aws lambda put-function-concurrency \
  --function-name orders-consumer \
  --reserved-concurrent-executions 40
~~~

Giá trị 40 chỉ là ví dụ. Nếu batch xử lý 100 record và có 40 invocation đồng thời, function có thể xử lý tối đa khoảng 4.000 record trong một đợt, nhưng phải kiểm tra duration và downstream capacity.

Nếu Reserved Concurrency quá thấp, SQS mapping có thể bị throttle và message age tăng. Nếu không đặt giới hạn, burst có thể làm downstream quá tải. Hãy load test để tìm điểm cân bằng.

## 21. Provisioned Concurrency cho function execution

Provisioned Concurrency cấp trước execution environment đã khởi tạo cho một published version hoặc alias. Nó hữu ích khi invocation cần latency rất thấp và cold start ảnh hưởng SLO.

PC không làm tăng batch size và không tăng tốc độ polling queue. Với SQS consumer, nó chỉ giúp execution environment sẵn sàng khi event source mapping invoke function. Nếu bottleneck là poller hoặc batch fill, PC không giải quyết đúng vấn đề.

Chi phí PC phụ thuộc memory, concurrency và thời gian bật. Ngoài phí capacity, invocation vẫn có phí request và duration. Khi traffic vượt PC, phần vượt có thể chạy bằng standard concurrency và gặp cold start. Chi phí PC được tính từ lúc bật tới lúc tắt, làm tròn lên khoảng 5 phút; initialization code được chạy khi allocate/recycle cũng có thể được tính vào duration.

Ví dụ capacity usage:

\[
PC\ GB\text{-}seconds =
ProvisionedConcurrency \times Memory_{GB} \times EnabledSeconds
\]

Nếu cấu hình 20 PC ở memory 2 GB trong 8 giờ:

\[
20 \times 2 \times 28.800 = 1.152.000\ GB\text{-}seconds
\]

Đây là lượng capacity tính phí trước khi cộng request và execution duration. So sánh với bật PC cả ngày hoặc cả tháng để thấy chi phí idle.

## 22. Provisioned Pollers cho SQS và Kafka

Provisioned Mode của Lambda event source mapping cấp tài nguyên polling chuyên dụng để đọc message. Đây là lựa chọn cho queue/stream có yêu cầu throughput và latency nghiêm ngặt.

Đối với SQS, một event poller có thể xử lý tối đa khoảng:

- 1 MB/giây throughput.
- 10 invocation đồng thời.
- 10 SQS polling API calls mỗi giây.

Provisioned Mode cho phép đặt minimum và maximum pollers, sau đó tự scale trong phạm vi đó. AWS mô tả chế độ này có tốc độ scale nhanh hơn standard mode và hỗ trợ concurrency cao hơn cho SQS. Số poller tối thiểu của SQS là 2; giới hạn tối đa cần xác minh theo API và quota hiện hành của Region.

Provisioned Mode hiện được hỗ trợ cho SQS, Amazon MSK và self-managed Kafka. Khả năng mỗi poller và cấu hình của Kafka khác SQS; không dùng công thức SQS cho Kafka.

Provisioned Pollers có chi phí riêng theo Event Poller Unit-hours (EPU-hours). Với SQS, một EPU hỗ trợ một event poller và mỗi SQS mapping cần tối thiểu hai poller. Chi phí được tính theo số EPU và thời gian dùng; thời gian tính theo giây với mức tối thiểu một phút.

Provisioned Mode không thể dùng cùng cấu hình maximum concurrency của SQS event source mapping. Khi bật provisioned mode, dùng maximum pollers để điều khiển mức polling/concurrency đầu vào. Reserved Concurrency ở cấp function vẫn là giới hạn khác cần tính đến.

## 23. Tính poller capacity theo workload

Để ước lượng poller, cần đo:

- Peak message/record per second.
- Average message size.
- Batch size thực tế.
- Average batch duration.
- Latency target.
- Số invocation đồng thời và concurrency quota.

Một ước lượng throughput của consumer:

\[
EPS \approx
\frac{PollerCount \times EffectiveBatchSize \times ConcurrentBatchesPerPoller}
{AverageBatchDuration}
\]

Sau đó đối chiếu giới hạn throughput và polling API của mỗi poller. Công thức chỉ là điểm xuất phát; phải benchmark vì payload, batching window và downstream có thể giới hạn throughput trước poller.

Ví dụ, nếu mỗi poller thực tế xử lý được 100 event/giây và peak yêu cầu 1.000 event/giây, cần khoảng 10 poller trước khi cộng buffer. Hãy đo bằng workload thực tế; không coi đây là giá trị mặc định của dịch vụ.

## 24. Cấu hình Provisioned Pollers bằng CLI

Ví dụ cập nhật một event source mapping SQS:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --provisioned-poller-config '{"MinimumPollers": 5, "MaximumPollers": 100}'
~~~

Tắt provisioned mode và trở về polling mặc định:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --provisioned-poller-config '{}'
~~~

Kiểm tra metric ProvisionedPollers và trạng thái event source mapping sau khi thay đổi. Cần kiểm tra thêm function concurrency, queue age và throughput để xác nhận capacity thực sự được sử dụng.

## 25. Phân biệt bottleneck: batch, poller hay function?

| Triệu chứng | Nút thắt có thể nằm ở | Hướng tối ưu |
|---|---|---|
| Batch thường nhỏ, invocation nhiều | Traffic thấp hoặc batching window quá ngắn | Điều chỉnh batch window nếu latency cho phép |
| Batch đầy nhưng queue age tăng | Function duration hoặc concurrency thấp | Tối ưu Java, memory, batch processing hoặc concurrency |
| Function concurrency thấp dù queue lớn | Polling/scaling event source mapping | Kiểm tra poller mode, source limits và mapping |
| Spillover/throttle hoặc invocation bị throttle | Function/account concurrency | Điều chỉnh reserved concurrency và poller capacity |
| Function nhanh nhưng message vẫn chờ | Event source poller hoặc batch window | Đo poller throughput và batching delay |
| Function duration tăng theo batch size | Batch quá lớn hoặc xử lý tuần tự | Giảm batch hoặc dùng parallelism có giới hạn |
| DB connection saturation | Concurrency/worker quá cao | Giới hạn connection, worker và function concurrency |
| Cost tăng do retries | Partial failure/idempotency chưa tốt | Bật partial batch response và sửa lỗi record |
| Cost cao khi không có message | Provisioned pollers hoặc PC baseline quá lớn | Giảm minimum hoặc dùng schedule nếu phù hợp |

Trước khi tăng capacity, hãy xác định chính xác thành phần đang giới hạn throughput. Thêm poller không giúp nếu function đã bị throttle; thêm PC không giúp nếu poller không đọc message đủ nhanh; tăng batch không giúp nếu database là bottleneck.

## 26. So sánh Provisioned Concurrency và Provisioned Pollers

| Tiêu chí | Provisioned Concurrency | Provisioned Pollers |
|---|---|---|
| Được gắn với | Lambda version/alias | Event source mapping |
| Tài nguyên được chuẩn bị | Execution environment đã khởi tạo | Polling resources đọc queue/stream |
| Tác động chính | Giảm cold start của function | Tăng tốc độ và năng lực polling |
| Đơn vị capacity | Concurrency × memory × thời gian | EPU × thời gian |
| Workload phù hợp | HTTP/API hoặc function cần startup latency thấp | SQS/Kafka có yêu cầu throughput/latency nghiêm ngặt |
| Giải quyết batch fill? | Không | Có thể cải thiện polling, nhưng batch/window vẫn cần tuning |
| Có phí khi idle? | Có | Có, theo minimum poller/EPU được cấp |

Hai cơ chế có thể giải quyết các phần khác nhau của một pipeline nhưng cần tính tổng chi phí và concurrency. Đừng bật cả hai chỉ vì muốn hệ thống nhanh hơn; đo xem latency đến từ polling hay initialization.

## 27. Chi phí Provisioned Concurrency

PC được tính theo lượng concurrency cấu hình, memory và thời gian bật. Khi function được invoke, request và duration vẫn được tính. Phần invocation vượt PC được tính theo on-demand rate. Lambda có thể recycle execution environment và chạy lại initialization code, do đó initialization cũng cần được tính vào chi phí duration.

Các điểm cần lưu ý:

- PC được tính từ lúc enable đến lúc disable, làm tròn lên 5 phút.
- Giá phụ thuộc Region, architecture và memory.
- Lambda Free Tier không áp dụng cho function bật Provisioned Concurrency theo bảng giá hiện hành.
- Invocation và duration vẫn được tính khi function chạy.
- PC không được dùng trên $LATEST; cần version/alias đã publish.
- Capacity không được dùng hết vẫn có chi phí.

Nếu chỉ cần latency thấp trong giờ cao điểm, cân nhắc scheduled scaling để tăng PC trước giờ cao điểm và giảm sau đó. Với traffic bất ngờ, target tracking có thể tăng capacity nhưng cần thời gian scale; nó không thay thế baseline capacity nếu SLO yêu cầu ngay lập tức.

## 28. Chi phí Provisioned Pollers

Provisioned Mode cho event source mapping có phí theo EPU-hours. AWS tính phí dựa trên minimum poller đã cấp và poller bổ sung trong quá trình autoscaling. EPU pricing khác theo event source và Region.

Công thức khái quát:

\[
EPUHours = \sum (AllocatedEPUs \times DurationHours)
\]

\[
PollerCost = EPUHours \times RegionalEPUPrice
\]

Ví dụ, nếu một SQS mapping cần 2 poller trong 10 giờ và một EPU tương ứng một poller, lượng dùng là 20 EPU-hours. Phí thực tế cần tra theo Region và thời điểm trên trang AWS Lambda Pricing.

Không dùng giá EPU ở US East để lập ngân sách cho Region khác. Hãy dùng AWS Pricing Calculator, Cost Explorer và billing data của account.

## 29. Batch có thể giảm chi phí bao nhiêu?

Ví dụ giả định để minh họa:

- Một triệu message cần xử lý.
- Nếu xử lý từng message, mỗi invocation mất 80 ms ở memory 1 GB.
- Nếu batch 100 message, mỗi invocation mất 400 ms ở memory 1 GB.
- Không tính retry, request price, queue price và downstream.

Xử lý từng message:

\[
1.000.000 \times 0,08s \times 1GB = 80.000\ GB\text{-}s
\]

Xử lý batch 100:

\[
10.000 \times 0,4s \times 1GB = 4.000\ GB\text{-}s
\]

Trong ví dụ này, compute giảm 20 lần và số invocation giảm 100 lần. Đây không phải mức tiết kiệm bảo đảm; nếu batch 100 khiến duration tăng lên 8 giây, tăng memory hoặc retry toàn batch khi một record lỗi, lợi ích có thể nhỏ hơn nhiều.

Phải benchmark với payload và lỗi thực tế. Tính cả partial batch response, idempotency và DLQ trước khi đưa batch lớn vào production.

## 30. Cross-cloud: Always Ready và minimum instances

Các cloud provider có cơ chế tương tự để giữ capacity sẵn sàng, nhưng cách tính phí và scale khác nhau:

| Nền tảng | Cơ chế | Chi phí cần theo dõi |
|---|---|---|
| AWS Lambda | Provisioned Concurrency | Memory × concurrency × thời gian bật, cộng request và duration |
| AWS Lambda SQS/Kafka | Provisioned Pollers / Provisioned Mode | EPU-hours, cộng function compute và queue/stream |
| Azure Functions Flex Consumption | Always Ready instances | Baseline memory khi idle, execution time và executions |
| Google Cloud Run | Minimum instances | CPU/memory idle billing theo cấu hình và request/active time |

Azure Flex Consumption cho phép cấu hình Always Ready theo function hoặc trigger group; baseline idle có chi phí riêng. Google Cloud Run có thể tính phí minimum instances trong thời gian idle theo billing mode. Các cơ chế này không hoàn toàn tương đương AWS PC; cần đọc pricing model của đúng plan và Region.

## 31. FinOps: đo cost per successful message

Một dashboard tốt không chỉ hiển thị tổng Lambda cost. Cần kết hợp cost, throughput và chất lượng nghiệp vụ.

Các chỉ số nên theo dõi:

| Nhóm | Metric |
|---|---|
| Batch | Average batch size, batch fullness, batching delay, payload size |
| Compute | Invocations, duration, memory used, GB-seconds |
| Capacity | ConcurrentExecutions, ReservedConcurrentExecutions, ProvisionedConcurrentExecutions |
| Poller | ProvisionedPollers, poller utilization, EPU-hours |
| Queue | ApproximateAgeOfOldestMessage, visible/in-flight count, DLQ count |
| Reliability | Retry count, partial batch failures, duplicate count |
| Performance | Records/second, p95/p99 processing latency |
| Business | Successful orders/payments/jobs |
| Cost | Cost per 1.000 successful messages, cost per transaction |

Công thức quan trọng:

\[
CostPer1000Success =
\frac{TotalCost}{SuccessfulMessages} \times 1000
\]

Nếu throughput tăng nhưng success rate giảm hoặc DLQ tăng, cost per success có thể xấu đi. Không tối ưu bằng cách bỏ qua lỗi hoặc coi message vào DLQ là đã xử lý thành công.

## 32. Tagging và phân bổ chi phí

Gắn cost allocation tags nhất quán cho function, queue, event source mapping và các tài nguyên liên quan. Một bộ tag có thể gồm:

- Application
- Service
- Environment
- Team
- CostCenter
- Owner
- BusinessCapability

Dùng AWS Cost Explorer hoặc Cost and Usage Report để phân bổ theo account, Region, service, function và tag. Nếu nhiều workload dùng chung queue, database hoặc log group, cần có cách phân bổ theo volume hoặc metric nghiệp vụ.

Không quy toàn bộ chi phí queue cho function consumer nếu queue còn được dùng bởi nhiều ứng dụng. Ghi rõ phương pháp phân bổ để so sánh tháng này với tháng trước có ý nghĩa.

## 33. FinOps guardrails

Một số guardrail có thể tự động hóa:

- Cảnh báo khi batch size hoặc batching window thay đổi vượt ngưỡng.
- Cảnh báo khi PC hoặc minimum pollers duy trì ngoài giờ dự kiến.
- Giới hạn maximum concurrency theo downstream capacity.
- Cảnh báo queue age và DLQ tăng.
- Báo cáo cost per successful message theo service/team.
- Cảnh báo duration hoặc memory peak tăng sau release.
- Yêu cầu owner và lý do khi bật provisioned capacity.
- Review capacity tối thiểu hàng tháng.
- Tự động giảm capacity theo lịch nếu workload có lịch ổn định và quy trình cho phép.

Không tự động giảm PC hoặc pollers chỉ dựa trên utilization thấp trong một khoảng ngắn. Cần xem traffic seasonality, sự kiện kinh doanh, SLO và thời gian scale-up.

## 34. Quy trình tối ưu có kiểm soát

Một vòng tối ưu nên thực hiện theo thứ tự:

1. Xác định business unit cần tối ưu: message, order, payment hoặc job.
2. Đo baseline: cost, throughput, latency, retry, DLQ và success rate.
3. Xác định bottleneck: batch, function duration, memory, poller, concurrency hay downstream.
4. Chọn một thay đổi nhỏ: batch size, window, memory, worker count hoặc capacity.
5. Benchmark với cùng payload và traffic.
6. Kiểm tra lỗi, duplicate, ordering và queue visibility.
7. Tính cost per successful operation.
8. Deploy canary hoặc staging trước.
9. Theo dõi sau phát hành.
10. Giữ hoặc rollback dựa trên SLO và unit cost.

Không thay đổi batch size, memory, concurrency và poller cùng lúc. Nếu cost giảm hoặc latency tăng, nhóm sẽ khó xác định yếu tố nào tạo ra kết quả.

## 35. Checklist production

**Batch và latency**

1. Batch size phù hợp với payload và source type?
2. Batching window đáp ứng latency budget?
3. Đã tính giới hạn payload 6 MB và metadata?
4. Đã benchmark nhiều batch size?
5. Visibility timeout đủ dài cho function timeout và batching window?
6. FIFO ordering được bảo toàn?

**Java và xử lý lỗi**

7. Handler có thể xử lý duplicate an toàn?
8. Partial batch response được bật và trả đúng message ID?
9. Lỗi transient và permanent được phân loại?
10. DLQ/quarantine có owner và quy trình replay?
11. Thread pool/virtual threads có giới hạn theo downstream?
12. Client, serializer và connection pool được tái sử dụng đúng cách?

**Capacity**

13. Reserved Concurrency bảo vệ downstream?
14. Provisioned Concurrency có thực sự giảm cold start ảnh hưởng SLO?
15. Caller invoke đúng alias/version đã provision?
16. Provisioned Pollers có cải thiện polling latency/throughput?
17. Poller capacity và function concurrency không xung đột?
18. Minimum capacity có được scale down khi traffic thấp?

**FinOps**

19. Cost per successful message được đo?
20. Có tính retry, DLQ, queue, poller, log và downstream?
21. Giá được tính theo Region/architecture thực tế?
22. Có dashboard, alarm, tagging và owner?
23. Có benchmark trước/sau thay đổi?
24. Có rollback plan khi latency, error rate hoặc cost xấu đi?

## Tài liệu tham khảo

- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [How Lambda processes records from stream and queue-based event sources](https://docs.aws.amazon.com/lambda/latest/dg/invocation-eventsourcemapping.html)
- [Lambda parameters for Amazon SQS event source mappings](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-parameters.html)
- [Creating and configuring an Amazon SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Using Lambda with Amazon SQS and provisioned mode](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Configure Lambda function memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html)
- [Powertools for AWS Lambda Java: Batch Processing](https://docs.aws.amazon.com/powertools/java/latest/utilities/batch/)
- [Azure Functions Flex Consumption pricing](https://learn.microsoft.com/azure/azure-functions/pricing)
- [Azure Functions Flex Consumption hosting](https://learn.microsoft.com/azure/azure-functions/flex-consumption-plan)
- [Google Cloud Run pricing](https://cloud.google.com/run/pricing)

## Kết luận

Tối ưu batch giúp giảm invocation overhead và tăng throughput, nhưng batch size và batching window phải phù hợp với latency budget, payload limit, visibility timeout và cách xử lý lỗi. Với Java, cần benchmark xử lý tuần tự/song song, memory, CPU, connection pool và partial batch response. Idempotency và DLQ là điều kiện để batch lớn không làm tăng side effect trùng hoặc chi phí retry.

Provisioned Concurrency chuẩn bị sẵn execution environment; Provisioned Pollers chuẩn bị tài nguyên đọc SQS/Kafka; Reserved Concurrency giới hạn và dành concurrency để bảo vệ workload. Mỗi loại có mục tiêu và cách tính chi phí riêng. Quyết định cuối cùng nên dựa trên throughput, p95/p99, queue age, retry, cost per successful message và tổng chi phí của cả pipeline, không chỉ một metric của Lambda.

