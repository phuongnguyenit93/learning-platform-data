# Xử lý lỗi trong callback mà không chặn luồng gửi

KafkaProducer gửi record bất đồng bộ. Khi broker trả kết quả, producer gọi callback để thông báo gửi thành công hoặc thất bại. Callback thường được thực thi trên I/O thread của producer; nếu callback làm việc lâu, chờ database, gọi HTTP, retry bằng vòng lặp hoặc ngủ chờ, nó có thể làm chậm việc hoàn tất các request khác và giảm throughput của producer.

Cách thiết kế phù hợp là giữ callback thật ngắn: lấy kết quả, chuyển một thông tin nhỏ sang bộ xử lý riêng và trả quyền điều khiển ngay cho producer. Phần xử lý lỗi, ghi database, retry và cập nhật trạng thái chạy trên executor hoặc worker riêng có giới hạn tài nguyên.

## 1. Callback nằm ở đâu trong luồng gửi?

Khi ứng dụng gọi send(), KafkaProducer serialize record, chọn partition, đưa record vào bộ đệm và gửi request bằng thread nền. Sau khi broker phản hồi hoặc producer kết thúc quá trình retry, callback được gọi với metadata hoặc exception.

~~~mermaid
sequenceDiagram
    participant App as Application thread
    participant Producer as KafkaProducer
    participant Sender as Producer I/O thread
    participant Broker as Kafka broker
    participant Pool as Result executor

    App->>Producer: send(record, callback)
    Producer-->>App: Future<RecordMetadata>
    Producer->>Sender: Queue record batch
    Sender->>Broker: Produce request
    Broker-->>Sender: Produce response
    Sender->>Pool: Submit compact send result
    Pool-->>Sender: Return immediately
    Pool->>Pool: Persist outcome / retry policy
~~~

Callback không phải một thread riêng được tạo cho từng message. Trong trường hợp thông thường, callback chạy trên thread I/O của producer. Vì vậy, một callback chậm có thể giữ thread đó lâu hơn dự kiến và ảnh hưởng đến các request gửi khác. Một số lỗi phát sinh ngay khi gọi send() có thể được ném trực tiếp trên thread ứng dụng trước khi record được đưa vào luồng gửi.

Hai nguyên tắc cần nhớ:

- Callback chỉ làm thao tác nhanh, không chờ tài nguyên bên ngoài.
- Công việc có thể blocking hoặc tốn CPU phải được chuyển sang executor/worker riêng.

## 2. Phân biệt lỗi đồng bộ và lỗi bất đồng bộ

Không phải mọi lỗi đều xuất hiện trong callback.

| Thời điểm | Ví dụ | Cách nhận biết |
|---|---|---|
| Ngay khi gọi send() | Serializer lỗi, record không hợp lệ, không lấy được metadata trong thời gian cho phép, buffer chờ quá hạn | Exception có thể được ném trên thread gọi; dùng try/catch |
| Sau khi record được tiếp nhận | Broker từ chối, timeout khi giao, authorization lỗi, không đủ ISR sau khi retry | Callback nhận exception hoặc Future hoàn tất bất thường |
| Ứng dụng xử lý kết quả | Executor đầy, database lỗi, retry store không khả dụng | Lỗi thuộc tầng ứng dụng; cần metric, log và cơ chế phục hồi riêng |

Ví dụ xử lý cả hai đường lỗi:

~~~java
try {
    producer.send(record, (metadata, exception) -> {
        // Callback xử lý kết quả bất đồng bộ.
        dispatchResult(record, metadata, exception);
    });
} catch (KafkaException exception) {
    // Lỗi đồng bộ: send() chưa chấp nhận record vào luồng gửi.
    handleImmediateFailure(record, exception);
}
~~~

Không nên giả định callback luôn được gọi nếu send() đã ném lỗi ngay trong lúc serialize hoặc kiểm tra record. Ngược lại, không nên chỉ bắt exception quanh send() rồi cho rằng đã xử lý hết lỗi gửi; lỗi cuối cùng từ broker cần được kiểm tra trong callback hoặc Future.

## 3. Vì sao callback không nên thực hiện công việc nặng?

Một callback có thể được gọi rất nhiều lần khi producer đang gửi tải lớn. Nếu mỗi callback chờ một thao tác bên ngoài, thời gian hoàn tất của các callback sẽ tích lũy và tạo nghẽn.

Các việc nên tránh trong callback:

- Gọi REST/gRPC đến một dịch vụ khác và chờ phản hồi.
- Ghi database đồng bộ hoặc chờ transaction.
- Gọi Future.get(), join() hoặc chờ một latch.
- Thread.sleep() để retry.
- Parse hoặc biến đổi payload lớn không cần thiết.
- Thực hiện retry liên tục bằng vòng lặp.
- Gọi flush() cho từng record.
- Ghi log đồng bộ với payload rất lớn.

Ví dụ không nên dùng:

~~~java
producer.send(record, (metadata, exception) -> {
    if (exception != null) {
        // Không nên: callback giữ I/O thread trong lúc ngủ.
        try {
            Thread.sleep(5000);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }

        // Không nên: retry ngay trong callback.
        producer.send(record);
    }

    // Không nên: chờ database hoặc HTTP tại đây.
    updateDatabaseSynchronously(record, metadata, exception);
});
~~~

Cách này có thể gây tắc nghẽn I/O thread, tạo vòng retry khó kiểm soát và làm record mới chậm được gửi. Nếu nhiều callback cùng lỗi, các thao tác chờ có thể làm producer suy giảm mạnh đúng lúc cluster đang gặp sự cố.

## 4. Chuyển kết quả sang executor riêng

Callback nên tạo một đối tượng kết quả nhỏ, sau đó gửi công việc sang executor. Worker của executor xử lý database, logging, retry hoặc cập nhật trạng thái.

Một kết quả gửi có thể gồm:

- Event ID để liên kết với nghiệp vụ.
- Topic, partition và offset nếu gửi thành công.
- Exception nếu gửi thất bại.
- Thời điểm gửi hoặc correlation ID nếu cần theo dõi.

Ví dụ dùng Java record:

~~~java
public record SendOutcome(
    String eventId,
    String topic,
    Integer partition,
    Long offset,
    Exception error
) {}
~~~

Tạo executor có số thread và hàng đợi giới hạn:

~~~java
ThreadPoolExecutor resultExecutor = new ThreadPoolExecutor(
    2,
    4,
    30,
    TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(500),
    Executors.defaultThreadFactory(),
    new ThreadPoolExecutor.AbortPolicy()
);
~~~

Hàng đợi có giới hạn giúp ứng dụng không tăng bộ nhớ vô hạn khi tốc độ callback cao hơn tốc độ xử lý kết quả. Chính sách AbortPolicy làm cho việc quá tải được phát hiện bằng RejectedExecutionException.

Callback chỉ chuyển kết quả:

~~~java
producer.send(record, (metadata, exception) -> {
    SendOutcome outcome = new SendOutcome(
        eventId,
        metadata == null ? null : metadata.topic(),
        metadata == null ? null : metadata.partition(),
        metadata == null ? null : metadata.offset(),
        exception
    );

    try {
        resultExecutor.execute(() -> processOutcome(outcome));
    } catch (RejectedExecutionException rejected) {
        callbackQueueRejected.increment();
        applicationOverloaded.set(true);
    }
});
~~~

Trong ví dụ, callback không thực hiện database, retry hay HTTP. Nó chỉ tạo kết quả nhỏ và submit công việc. Các thao tác đó chạy trong thread của resultExecutor.

Nếu executor đầy, không được âm thầm bỏ qua lỗi. Cần có metric cho số lần reject, cảnh báo, trạng thái overload và cơ chế dừng nhận thêm công việc khi cần. Với pipeline quan trọng, trạng thái gửi nên được lưu trong transactional outbox hoặc một kho bền vững để tiến trình phục hồi có thể đối soát và gửi lại. Nếu kết quả thành công bị mất khi callback không submit được, outbox có thể còn ở trạng thái pending và gửi lại; consumer cần idempotent để xử lý duplicate an toàn.

Không dùng CallerRunsPolicy cho executor này. Khi hàng đợi đầy, CallerRunsPolicy có thể chạy tác vụ ngay trên thread gọi execute(), tức có thể chính là producer I/O thread đang chạy callback. Điều đó làm mất mục tiêu không chặn luồng gửi.

## 5. Xử lý kết quả thành công và thất bại ở worker

Worker nhận SendOutcome và quyết định hành động:

~~~java
void processOutcome(SendOutcome outcome) {
    if (outcome.error() == null) {
        markOutboxDelivered(
            outcome.eventId(),
            outcome.topic(),
            outcome.partition(),
            outcome.offset()
        );
        return;
    }

    if (isRetryableAfterProducerExhausted(outcome.error())) {
        scheduleRetry(outcome.eventId(), outcome.error());
        return;
    }

    markAsPermanentFailure(outcome.eventId(), outcome.error());
}
~~~

Các hàm trong ví dụ đại diện cho logic ứng dụng:

- markOutboxDelivered cập nhật trạng thái nghiệp vụ sau khi broker xác nhận.
- scheduleRetry ghi nhận lần thử tiếp theo, không ngủ chờ trong worker.
- markAsPermanentFailure chuyển event sang trạng thái cần can thiệp hoặc quy trình xử lý lỗi riêng.

Executor tách việc xử lý kết quả khỏi I/O thread, nhưng bản thân executor vẫn cần giới hạn số thread, hàng đợi, thời gian xử lý và khả năng phục hồi. Nếu database chậm kéo dài, worker pool có thể đầy; hãy theo dõi queue depth và thiết kế backpressure.

## 6. Phân loại lỗi trước khi retry

Kafka producer đã có cơ chế retry nội bộ cho các lỗi tạm thời. Callback thường nhận kết quả cuối cùng sau khi producer đã thử lại theo cấu hình và hết điều kiện giao record, chẳng hạn delivery timeout.

Không nên retry mọi exception theo cùng một cách.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Broker mất kết nối ngắn, leader đang chuyển, request timeout | Xem xét retry ở tầng ứng dụng theo backoff và giới hạn |
| Lỗi cấu hình/quyền | Topic hoặc cluster không cho phép principal ghi | Sửa cấu hình hoặc quyền; retry liên tục không giải quyết được |
| Lỗi dữ liệu | Serialization lỗi, schema không hợp lệ, record quá lớn | Sửa dữ liệu hoặc schema; đưa vào luồng xử lý lỗi phù hợp |
| Lỗi vòng đời producer | Producer đã đóng, transactional producer bị fencing | Khôi phục hoặc tạo lại producer theo đúng lifecycle/transaction |
| Kết quả không chắc chắn | Timeout hoặc mất kết nối sau khi broker có thể đã append record | Dùng event ID/idempotency để tránh xử lý trùng khi gửi lại |

Tên exception cụ thể và khả năng retry phụ thuộc phiên bản client và trạng thái request. Nên phân loại theo exception type, mã lỗi Kafka và ngữ cảnh nghiệp vụ thay vì chỉ kiểm tra chuỗi message.

### 6.1. Retry nội bộ và retry nghiệp vụ

Hai tầng retry có trách nhiệm khác nhau:

- **Retry nội bộ của KafkaProducer:** client tự xử lý lỗi tạm thời trong giới hạn cấu hình, sequence và producer session.
- **Retry nghiệp vụ của ứng dụng:** được thực hiện sau khi producer trả kết quả thất bại cuối cùng hoặc khi hệ thống phục hồi từ outbox.

Không nên lặp lại ngay record trong callback khi producer vừa hết delivery timeout. Nếu retry nghiệp vụ không có giới hạn, hệ thống có thể tạo tải lớn hơn khi broker đang quá tải.

### 6.2. Backoff và jitter

Retry ở tầng ứng dụng nên có khoảng chờ tăng dần, giới hạn số lần thử và thêm jitter để nhiều producer không cùng retry tại một thời điểm.

Ví dụ chính sách minh họa:

| Lần thử | Khoảng chờ cơ sở |
|---:|---:|
| 1 | 500 ms |
| 2 | 1 giây |
| 3 | 2 giây |
| 4 | 4 giây |
| Sau giới hạn | Chuyển sang trạng thái cần xử lý hoặc chờ lịch retry dài hơn |

Jitter thêm một độ lệch ngẫu nhiên trong khoảng đã chọn. Không dùng Thread.sleep() trong callback. Hãy dùng scheduler, hàng đợi retry hoặc cột next_attempt_at trong outbox để lên lịch.

### 6.3. Chống trùng khi gửi lại

Khi ứng dụng retry sau timeout, broker có thể đã ghi record nhưng acknowledgement bị mất trên đường về. Vì vậy, lần gửi lại có thể tạo một record trùng về mặt nghiệp vụ.

Tạo event ID ổn định trước lần gửi đầu tiên và giữ nguyên ID qua mọi lần retry. Consumer có thể lưu event ID đã xử lý với unique constraint hoặc cơ chế idempotency phù hợp.

Producer idempotence bảo vệ retry nội bộ trong producer session; nó không tự khử duplicate do ứng dụng khởi động lại và gửi lại một event như một thao tác mới. Với nghiệp vụ cần độ tin cậy cao, transactional outbox giúp lưu event cùng transaction nghiệp vụ và hỗ trợ khôi phục sau crash.

## 7. Giữ thứ tự khi xử lý lỗi bất đồng bộ

Việc chuyển callback sang executor có thể làm thay đổi thứ tự hoàn tất công việc xử lý kết quả. Ví dụ, event A được gửi trước event B nhưng worker xử lý kết quả B xong trước A vì tác vụ A chờ database lâu hơn.

Kafka bảo đảm thứ tự record trong một partition theo thứ tự append. Nó không tự bảo đảm các tác vụ hậu xử lý callback trong ứng dụng hoàn tất theo đúng thứ tự đó.

Nếu nghiệp vụ cần thứ tự theo key:

- Gửi các event cùng aggregate key vào cùng partition.
- Dùng sequence number hoặc version của aggregate để phát hiện thứ tự.
- Có thể phân luồng worker theo key hoặc shard để các event cùng key được xử lý tuần tự.
- Nếu event trước chưa gửi thành công, quyết định rõ có cho event sau vượt qua hay phải chờ.
- Retry event cũ phải giữ nguyên key và event ID.

Không nên dùng một executor song song không giới hạn rồi giả định thứ tự callback và thứ tự cập nhật database luôn giống nhau. Nếu thứ tự không quan trọng, xử lý song song giúp tăng throughput; nếu quan trọng, phải đưa thứ tự vào thiết kế worker.

## 8. Backpressure khi callback nhanh hơn worker

Một executor có giới hạn sẽ bảo vệ bộ nhớ, nhưng khi queue đầy, ứng dụng phải có chính sách phản ứng. Không được để callback bị chặn vô thời hạn hoặc bỏ mất kết quả mà không có dấu vết.

Một số cơ chế:

| Cơ chế | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Bounded queue | Giới hạn số kết quả chờ xử lý | Mọi hệ thống có tải biến động |
| Admission control | Tạm dừng nhận request mới khi quá tải | Producer phục vụ API hoặc luồng có thể điều tiết |
| Circuit breaker | Đánh dấu downstream đang lỗi và ngừng gửi công việc mới theo chính sách | Database/API lỗi kéo dài |
| Durable outbox | Lưu event và trạng thái gửi trong database để worker phục hồi | Luồng nghiệp vụ không được mất event |
| Retry scheduler | Đưa event cần thử lại vào lịch có backoff | Lỗi tạm thời và có thể thử lại sau |

Một số chỉ số nên theo dõi:

- Độ sâu hàng đợi callback result.
- Số lần executor reject.
- Thời gian xử lý outcome.
- Số event pending trong outbox.
- Tỷ lệ send success/failure.
- Số lần retry và tuổi của event lâu nhất.
- Thời gian từ send đến acknowledgement.

Khi queue gần đầy, ứng dụng có thể giảm tốc độ nhận request, tạm dừng nguồn phát hoặc chuyển sang chế độ bảo vệ. Không nên tăng thread hoặc queue vô hạn để che giấu downstream không theo kịp.

## 9. Ví dụ Java: callback ngắn, worker xử lý riêng

Ví dụ sau minh họa cách chuyển kết quả gửi sang executor giới hạn. Các hàm lưu outbox, phân loại lỗi và metric là điểm tích hợp với ứng dụng thực tế.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.LongAdder;

import org.apache.kafka.clients.producer.KafkaProducer;
import org.apache.kafka.clients.producer.ProducerRecord;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.apache.kafka.common.errors.KafkaException;

public class AsyncOrderPublisher implements AutoCloseable {

    private final KafkaProducer<String, String> producer;
    private final ThreadPoolExecutor resultExecutor;

    private final LongAdder callbackRejected = new LongAdder();
    private final AtomicBoolean overloaded = new AtomicBoolean(false);
    private final AtomicBoolean accepting = new AtomicBoolean(true);

    public AsyncOrderPublisher(
            KafkaProducer<String, String> producer) {
        this.producer = producer;

        this.resultExecutor = new ThreadPoolExecutor(
            2,
            4,
            30,
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(500),
            new ThreadPoolExecutor.AbortPolicy()
        );
    }

    public void publish(
            String eventId,
            ProducerRecord<String, String> record) {

        if (!accepting.get() || overloaded.get()) {
            throw new IllegalStateException(
                "Publisher is not accepting new events"
            );
        }

        try {
            producer.send(record, (metadata, exception) -> {
                SendOutcome outcome = new SendOutcome(
                    eventId,
                    metadata == null ? null : metadata.topic(),
                    metadata == null ? null : metadata.partition(),
                    metadata == null ? null : metadata.offset(),
                    exception
                );

                try {
                    resultExecutor.execute(
                        () -> processOutcome(outcome)
                    );
                } catch (RejectedExecutionException rejected) {
                    callbackRejected.increment();
                    overloaded.set(true);
                    // Phát tín hiệu overload; không xử lý blocking tại đây.
                }
            });
        } catch (KafkaException exception) {
            // Lỗi đồng bộ trước khi record được nhận vào luồng gửi.
            handleImmediateFailure(eventId, exception);
        }
    }

    private void processOutcome(SendOutcome outcome) {
        if (outcome.error() == null) {
            markOutboxDelivered(
                outcome.eventId(),
                outcome.topic(),
                outcome.partition(),
                outcome.offset()
            );
            return;
        }

        if (isRetryableAfterProducerExhausted(outcome.error())) {
            scheduleRetry(outcome.eventId(), outcome.error());
        } else {
            markPermanentFailure(outcome.eventId(), outcome.error());
        }
    }

    @Override
    public void close() {
        accepting.set(false);

        // Chờ các lần gửi đã nhận được hoàn tất để callback có thể submit.
        producer.flush();
        producer.close();

        // Chỉ shutdown executor sau khi producer đã hoàn tất callback.
        resultExecutor.shutdown();

        try {
            if (!resultExecutor.awaitTermination(30, TimeUnit.SECONDS)) {
                resultExecutor.shutdownNow();
            }
        } catch (InterruptedException interrupted) {
            resultExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    private void handleImmediateFailure(
            String eventId,
            Exception exception) {
        // Chuyển lỗi đồng bộ về tầng gọi hoặc ghi nhận vào outbox.
    }

    private boolean isRetryableAfterProducerExhausted(
            Exception exception) {
        // Phân loại theo exception type, mã lỗi và chính sách nghiệp vụ.
        return false;
    }

    private void scheduleRetry(String eventId, Exception exception) {
        // Lưu nextAttemptAt; không Thread.sleep() trong callback.
    }

    private void markOutboxDelivered(
            String eventId,
            String topic,
            Integer partition,
            Long offset) {
        // Cập nhật trạng thái outbox ở worker thread.
    }

    private void markPermanentFailure(
            String eventId,
            Exception exception) {
        // Ghi trạng thái lỗi cuối cùng hoặc chuyển sang quy trình xử lý.
    }

    public long getCallbackRejectedCount() {
        return callbackRejected.sum();
    }

    public boolean isOverloaded() {
        return overloaded.get();
    }

    public record SendOutcome(
        String eventId,
        String topic,
        Integer partition,
        Long offset,
        Exception error
    ) {}
}
~~~

Ví dụ tập trung vào luồng callback. Trong hệ thống thật, cần hoàn thiện các hàm lưu trạng thái, metric, retry và phục hồi outbox. Khi executor reject, cờ overload ngăn nhận thêm event; hệ thống giám sát cần phát hiện trạng thái này và có quy trình phục hồi rõ ràng.

Nếu producer dùng trong service lâu dài, hãy để dependency injection/container quản lý lifecycle producer. Đóng publisher theo thứ tự: ngừng nhận event mới, flush/close producer để callback hoàn tất, sau đó shutdown executor và chờ worker xử lý kết quả đã được submit.

## 10. Tích hợp với Spring Kafka

Spring Kafka cung cấp KafkaTemplate. Phương thức send() trả về future chứa SendResult. Với các phiên bản Spring Kafka hiện đại, API thường dùng CompletableFuture; phiên bản cũ có thể dùng ListenableFuture.

Có thể chuyển phần xử lý kết quả sang executor riêng:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.RejectedExecutionException;

import org.apache.kafka.clients.producer.RecordMetadata;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

CompletableFuture<SendResult<String, String>> future =
    kafkaTemplate.send("orders", orderId, eventJson);

future.whenComplete((result, exception) -> {
    try {
        resultExecutor.execute(() -> {
            if (exception != null) {
                handleSendFailure(orderId, exception);
                return;
            }

            RecordMetadata metadata =
                result.getRecordMetadata();

            markOutboxDelivered(
                orderId,
                metadata.topic(),
                metadata.partition(),
                metadata.offset()
            );
        });
    } catch (RejectedExecutionException rejected) {
        callbackRejected.increment();
        applicationOverloaded.set(true);
    }
});
~~~

Đoạn code giả định các biến và hàm xử lý đã được khai báo trong service. Khi dùng Spring Kafka, cần xác định phiên bản thực tế để chọn đúng kiểu Future. Quy tắc vẫn như nhau: completion callback có thể chạy trên thread hoàn tất send; không để nó chờ database hoặc HTTP.

Một lựa chọn khác là dùng whenCompleteAsync với executor riêng. Khi đó cần xử lý trường hợp executor từ chối task: future phụ có thể hoàn tất exceptionally với RejectedExecutionException. Dù dùng cách nào, phải quan sát lỗi submit và có đường phục hồi cho kết quả không được xử lý.

Không nên dùng executor mặc định không giới hạn hoặc common ForkJoinPool cho công việc blocking mà không hiểu tác động. Hãy dùng executor có cấu hình thread/queue phù hợp và theo dõi tải.

## 11. Đóng ứng dụng an toàn

Khi ứng dụng shutdown, producer có thể vẫn còn record đang chờ acknowledgement và callback đang được gọi. Nếu shutdown executor trước producer, callback đến sau đó có thể không submit được kết quả.

Thứ tự nên thực hiện:

1. Ngừng nhận công việc mới và không tạo thêm ProducerRecord.
2. Chờ các request nghiệp vụ đang phát event hoàn tất hoặc chuyển trạng thái pending vào outbox.
3. Gọi flush() hoặc close producer với timeout phù hợp để hoàn tất các lần gửi đang chờ.
4. Đợi các task kết quả đã submit vào executor xử lý xong.
5. Đóng executor và các tài nguyên phụ trợ.
6. Khi hết thời gian shutdown, ghi nhận các event còn pending để tiến trình sau phục hồi.

Không gọi shutdownNow() ngay từ đầu nếu vẫn cần callback submit kết quả. Shutdown cưỡng bức có thể làm mất phần xử lý hậu kỳ của những lần gửi đã có kết quả.

## 12. Kiểm thử callback và xử lý quá tải

Một bài kiểm thử nên bao gồm cả đường thành công, lỗi broker và quá tải executor:

| Kịch bản | Cách tạo tình huống | Điều cần xác minh |
|---|---|---|
| Gửi thành công | Gửi record đến topic có sẵn | Callback nhận metadata, worker cập nhật trạng thái |
| Broker tạm thời không sẵn sàng | Dừng broker hoặc chặn kết nối trong môi trường test | Producer retry nội bộ; callback nhận kết quả cuối |
| Không đủ ISR | Giảm số replica trong ISR dưới min.insync.replicas | Callback nhận lỗi cuối; retry policy được áp dụng |
| Serializer lỗi | Dùng serializer ném exception | Lỗi được bắt tại đường gọi send() |
| Executor đầy | Dùng worker chậm và queue nhỏ trong test | Reject được đếm, hệ thống chuyển sang overload |
| Database chậm | Giả lập độ trễ ở hàm xử lý outcome | Callback vẫn trả nhanh, queue depth tăng có kiểm soát |
| Shutdown khi còn request | Gửi nhiều record rồi đóng publisher | Producer hoàn tất callback trước khi executor dừng |
| Timeout không rõ kết quả | Ngắt phản hồi sau khi request có thể đã đến broker | Retry giữ nguyên event ID và consumer xử lý idempotent |

Đo callback duration riêng với worker processing duration. Nếu callback duration tăng cùng lúc producer throughput giảm, có thể callback đang làm quá nhiều việc. Nếu callback nhanh nhưng queue depth và thời gian worker tăng, bottleneck nằm ở tầng xử lý kết quả hoặc downstream.

## 13. Checklist thiết kế callback

- [ ] Callback không gọi database, HTTP hoặc thao tác blocking.
- [ ] Callback không gọi Future.get(), sleep() hoặc retry trong vòng lặp.
- [ ] Callback chỉ tạo kết quả nhỏ và submit sang executor riêng.
- [ ] Executor có giới hạn thread và queue.
- [ ] Không dùng CallerRunsPolicy khiến callback phải chạy tác vụ nặng.
- [ ] Có metric cho callback duration, queue depth và rejected task.
- [ ] Xử lý riêng lỗi đồng bộ khi gọi send() và lỗi bất đồng bộ trong callback/Future.
- [ ] Phân biệt retry nội bộ của KafkaProducer với retry nghiệp vụ.
- [ ] Retry có backoff, jitter, giới hạn và idempotency key.
- [ ] Có cách giữ thứ tự theo key nếu nghiệp vụ yêu cầu.
- [ ] Kết quả quan trọng có đường phục hồi qua outbox hoặc storage bền vững.
- [ ] Shutdown producer trước executor để callback có thể hoàn tất việc submit.

Callback của KafkaProducer là điểm thông báo kết quả gửi, không nên trở thành nơi chạy toàn bộ nghiệp vụ hậu xử lý. Giữ callback ngắn, chuyển kết quả sang worker có giới hạn, kiểm soát backpressure và lưu trạng thái đủ để phục hồi sẽ giúp producer duy trì throughput ngay cả khi database hoặc dịch vụ phía sau chậm. Retry cần có chính sách và idempotency rõ ràng để xử lý lỗi mà không tạo vòng gửi lặp hoặc phá vỡ thứ tự nghiệp vụ.
