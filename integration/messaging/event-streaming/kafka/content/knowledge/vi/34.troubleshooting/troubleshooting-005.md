# Timeout gửi, buffer cạn và kết quả ghi không xác định

Producer Kafka nhận record từ ứng dụng, gom chúng vào buffer, gửi theo batch đến broker và chờ phản hồi theo cấu hình giao nhận. Khi broker chậm, mạng chập chờn hoặc lưu lượng tăng đột ngột, ứng dụng có thể gặp timeout, buffer đầy hoặc không biết chắc record đã được ghi hay chưa. Đây là nhóm sự cố nguy hiểm vì một lần gửi thất bại ở phía ứng dụng không phải lúc nào cũng đồng nghĩa record chưa xuất hiện trong Kafka.

Bài học này thuộc chương **Chẩn đoán sự cố** của module **KAFKA**. Mục tiêu là phân biệt đúng các loại timeout, tìm nguyên nhân khiến producer không giải phóng được buffer, xử lý kết quả ghi không xác định và cấu hình Java/Spring Kafka để hệ thống chịu được tải cũng như lỗi mạng.

## 1. Phân biệt ba loại timeout

Trước khi thay đổi cấu hình, cần xác định timeout xảy ra ở giai đoạn nào. Kafka producer có nhiều giới hạn thời gian với ý nghĩa khác nhau.

| Dấu hiệu | Thời điểm xảy ra | Ý nghĩa |
|---|---|---|
| send() ném TimeoutException trước khi trả về future | Producer chờ metadata hoặc chờ cấp phát buffer quá thời gian max.block.ms | Lời gọi chưa đưa record vào luồng gửi thành công; kiểm tra metadata và áp lực buffer |
| Future gửi record hoàn tất với TimeoutException | Record đã được tiếp nhận vào accumulator nhưng không hoàn tất giao nhận trong delivery.timeout.ms | Ứng dụng không nhận được xác nhận thành công; kết quả ghi có thể không xác định |
| Future.get(timeout) ném TimeoutException | Luồng ứng dụng chờ future quá thời gian tự đặt | Chỉ thời gian chờ của luồng gọi đã hết; producer vẫn có thể tiếp tục gửi và future vẫn có thể hoàn tất sau đó |

Ba tình huống trên không thể xử lý bằng cùng một cách. Đặc biệt, không tự động gửi lại record chỉ vì luồng gọi bị timeout khi chờ future.

### max.block.ms

send() là API bất đồng bộ sau khi record được chấp nhận, nhưng bản thân lời gọi send() vẫn có thể chặn trong một số tình huống. Producer cần metadata để xác định partition và cần vùng nhớ trong buffer để lưu record. Nếu metadata chưa sẵn sàng hoặc buffer không còn chỗ trống, producer chờ tối đa theo max.block.ms.

Nếu thời gian chờ này hết trước khi send() trả về, ứng dụng nhận exception ngay tại lời gọi. Đây là lỗi ở giai đoạn tiếp nhận record vào producer. Cần kiểm tra kết nối metadata, topic/partition và tình trạng buffer; không nhầm nó với timeout khi chờ broker xác nhận một record đã gửi.

### request.timeout.ms

Đây là thời gian producer chờ phản hồi cho một request gửi đến broker. Request có thể thất bại do broker xử lý chậm, mạng mất gói, broker quá tải hoặc thời gian chờ phản hồi vượt giới hạn. Producer có thể thử lại theo chính sách retry nếu record vẫn còn trong thời hạn giao nhận.

request.timeout.ms không phải tổng thời gian tối đa của toàn bộ record. Một record có thể trải qua nhiều request/retry trước khi kết quả cuối cùng được báo cho ứng dụng.

### delivery.timeout.ms

Đây là giới hạn tổng thời gian để producer báo kết quả thành công hoặc thất bại cho một record sau khi send() đã tiếp nhận record. Khoảng thời gian này bao gồm chờ batch, thời gian request và các lần retry. Khi hết thời hạn, producer hoàn tất future với lỗi.

Nếu broker đã ghi record nhưng phản hồi ACK bị mất hoặc đến muộn, producer có thể không biết chắc kết quả. Vì vậy, delivery timeout là một giới hạn giao nhận ở phía client, không phải bằng chứng tuyệt đối rằng broker chưa lưu record.

### Timeout khi chờ future ở ứng dụng

Ví dụ, ứng dụng gọi future.get(2, TimeUnit.SECONDS) trong khi delivery.timeout.ms được đặt là 120 giây. Nếu hai giây trôi qua, Future.get() ném TimeoutException cho luồng đang chờ. Điều đó không tự hủy request của Kafka producer và không chứng minh record thất bại.

Hãy phân biệt rõ timeout do Kafka client báo với timeout do mã ứng dụng tự đặt khi chờ kết quả. Nếu dùng CompletableFuture.orTimeout() làm giới hạn ở tầng ứng dụng, cần nhớ thao tác này làm future hoàn tất ngoại lệ theo bộ đếm thời gian của ứng dụng; nó không phải lệnh hủy việc gửi ở Kafka broker.

## 2. Theo dõi vòng đời của một record

Luồng gửi đơn giản có thể hình dung như sau:

~~~mermaid
flowchart TD
    A[Ứng dụng gọi send] --> B[Serialize và xác định partition]
    B --> C{Có metadata và buffer?}
    C -- Không --> D[Chờ tối đa max.block.ms]
    D --> E{Được cấp tài nguyên?}
    E -- Không --> F[send ném exception đồng bộ]
    E -- Có --> G[Đưa record vào accumulator]
    C -- Có --> G
    G --> H[Sender gom batch và gửi request]
    H --> I{Broker phản hồi ACK?}
    I -- Có --> J[Future thành công]
    I -- Chưa có hoặc lỗi tạm thời --> K{Còn thời hạn giao nhận?}
    K -- Có --> H
    K -- Không --> L[Hết delivery.timeout.ms]
    L --> M[Future thất bại; kết quả ghi có thể chưa xác định]
~~~

Trong thực tế, serializer, partitioner, interceptor, nhiều partition và nhiều request có thể làm luồng phức tạp hơn. Sơ đồ nhấn mạnh điểm quan trọng: lỗi trước khi record được đưa vào accumulator khác với lỗi sau khi producer đã bắt đầu giao nhận.

Khi điều tra, ghi nhận loại exception, stack trace, thời điểm gọi send(), thời điểm future hoàn tất, topic, key, event ID và nếu có thì partition/offset. Đừng chỉ ghi một dòng “Kafka timeout” vì thông tin đó không đủ để xác định record đã được tiếp nhận hay chưa.

## 3. Vì sao producer bị cạn buffer?

Kafka producer dùng buffer.memory để giữ các record đang chờ được gửi. Record thường được gom theo partition thành batch. Sender nền lấy batch, gửi đến broker và giải phóng vùng nhớ khi batch được xử lý xong.

Buffer có thể cạn khi tốc độ ứng dụng tạo record cao hơn tốc độ producer gửi và broker xác nhận. Một số nguyên nhân thường gặp:

- Broker chậm hoặc mất kết nối, khiến batch tồn tại lâu trong accumulator.
- Replication bị chậm, ISR thay đổi hoặc broker phải throttle producer.
- Mạng có độ trễ cao, mất gói hoặc thường xuyên tái kết nối.
- Lưu lượng tăng đột biến, nhiều partition đồng thời có batch đang chờ.
- Batch quá nhỏ hoặc linger.ms quá thấp khiến số request tăng và giảm hiệu quả gửi theo lô.
- Serialization hoặc nén tiêu tốn CPU, làm tốc độ tạo/gửi batch giảm.
- Callback của producer thực hiện công việc nặng hoặc chặn luồng gửi.
- Có quá nhiều producer instance cùng tồn tại, mỗi instance giữ một vùng buffer riêng.

Một dấu hiệu điển hình là buffer-available-bytes giảm dần, waiting-threads tăng và record-queue-time tăng. Khi buffer hết chỗ, các lời gọi send() mới có thể phải đợi cấp phát bộ nhớ; nếu quá max.block.ms, chúng thất bại ngay tại lời gọi.

Không nên kết luận rằng chỉ cần tăng buffer.memory là hết sự cố. Nếu broker chỉ xử lý được 10 MB/s trong khi ứng dụng liên tục tạo 50 MB/s, buffer lớn hơn chỉ kéo dài thời gian trước khi áp lực quay trở lại và có thể làm tăng mức sử dụng heap.

## 4. Đọc các metric của producer

Ưu tiên đọc metric theo chuỗi từ buffer đến broker:

| Metric | Điều cần quan sát | Gợi ý chẩn đoán |
|---|---|---|
| buffer-available-bytes | Dung lượng buffer còn trống | Giảm liên tục cho thấy producer không giải phóng buffer kịp |
| buffer-total-bytes | Tổng dung lượng buffer | Giúp đặt buffer còn trống trong bối cảnh tổng dung lượng |
| waiting-threads | Số luồng đang đợi buffer | Tăng cùng lúc buffer trống giảm là dấu hiệu áp lực cấp phát |
| record-queue-time-avg / max | Thời gian record nằm trong queue trước khi gửi | Tăng cho thấy backlog ở phía producer |
| request-latency-avg / max | Độ trễ phản hồi request | Tăng cho thấy broker hoặc đường mạng phản hồi chậm |
| record-retry-rate | Tần suất record/request phải retry | Tăng cho thấy lỗi tạm thời, timeout hoặc broker/network không ổn định |
| record-error-rate | Tần suất gửi thất bại | Đối chiếu với exception và delivery timeout |
| batch-size-avg | Kích thước batch trung bình | Quá thấp có thể làm giảm hiệu quả gửi theo lô |
| records-per-request-avg | Số record trung bình trong mỗi request | Giúp đánh giá hiệu quả batching |

Tên metric cụ thể và cách xuất chúng phụ thuộc phiên bản Kafka client, JMX, Micrometer và cấu hình quan sát. Hãy xác nhận metric có được xuất từ đúng producer instance. Không so sánh số liệu trung bình của toàn dịch vụ với một producer đơn lẻ đang bị nghẽn.

Đối chiếu metric producer với broker:

- Produce request latency và request queue time của broker.
- Tỷ lệ request bị throttle do quota.
- ISR thay đổi, partition under-replicated và thời gian xử lý replication.
- CPU, disk latency, network throughput và số kết nối của broker.
- Lỗi xác thực, phân quyền hoặc metadata khi topic/partition không truy cập được.

Nếu request latency tăng cùng lúc ISR co lại, cần điều tra replication và broker trước khi tăng buffer. Nếu broker ổn định nhưng waiting-threads tăng trong các đợt tải cao, tập trung vào tốc độ đầu vào, batching và dung lượng buffer.

## 5. Chọn cấu hình timeout và batching

Các tham số chính có quan hệ với nhau:

| Tham số | Vai trò | Khi điều chỉnh |
|---|---|---|
| max.block.ms | Thời gian send() chờ metadata hoặc buffer | Tăng khi hệ thống cần chịu khoảng chờ dài hơn và luồng gọi có thể chặn tương ứng |
| request.timeout.ms | Thời gian chờ phản hồi một request | Điều chỉnh theo độ trễ mạng/broker và chính sách retry |
| delivery.timeout.ms | Tổng thời hạn giao nhận record | Phải đủ cho batching, request và retry dự kiến |
| buffer.memory | Dung lượng buffer cho record đang chờ gửi | Tăng khi có burst ngắn và heap còn ngân sách |
| batch.size | Kích thước batch mục tiêu cho mỗi partition | Tăng nếu cần batch lớn hơn và mức trễ cho phép |
| linger.ms | Thời gian chờ thêm record để gom batch | Tăng nhẹ khi throughput quan trọng hơn độ trễ tức thời |
| compression.type | Thuật toán nén batch | Chọn theo cân bằng CPU, băng thông và kích thước payload |
| max.in.flight.requests.per.connection | Số request chưa được xác nhận trên một kết nối | Cân bằng throughput và bảo toàn thứ tự theo cấu hình idempotence |

delivery.timeout.ms nên lớn hơn hoặc bằng request.timeout.ms cộng linger.ms để có đủ khoảng thời gian cho request và batching. Cần kiểm tra tài liệu của phiên bản Kafka client đang dùng khi đặt các giá trị liên quan; một cấu hình không hợp lệ có thể khiến producer không khởi tạo được.

Một cấu hình khởi đầu cho ứng dụng Spring Boot có thể như sau:

~~~properties
spring.kafka.producer.acks=all
spring.kafka.producer.properties.enable.idempotence=true
spring.kafka.producer.properties.max.in.flight.requests.per.connection=5

spring.kafka.producer.properties.max.block.ms=60000
spring.kafka.producer.properties.request.timeout.ms=30000
spring.kafka.producer.properties.delivery.timeout.ms=120000

spring.kafka.producer.properties.buffer.memory=67108864
spring.kafka.producer.properties.batch.size=32768
spring.kafka.producer.properties.linger.ms=5
spring.kafka.producer.properties.compression.type=zstd
~~~

Đây chỉ là bộ giá trị minh họa để bắt đầu đo đạc, không phải cấu hình tối ưu cho mọi workload. Cần kiểm tra phiên bản Kafka client có hỗ trợ thuật toán nén đã chọn hay không, đồng thời đo CPU, độ trễ và throughput dưới tải thực tế. Dung lượng buffer 64 MiB cũng cần được tính vào tổng heap của mỗi producer instance.

Không dùng max.block.ms như cách chữa broker chậm. Tăng tham số này chỉ cho phép lời gọi send() chờ lâu hơn khi thiếu metadata hoặc buffer; nó không tăng tốc độ broker và có thể làm nhiều luồng ứng dụng bị giữ lại lâu hơn. Tương tự, tăng delivery.timeout.ms có thể kéo dài thời gian record nằm trong buffer, nên phải cân nhắc dung lượng và yêu cầu độ trễ đầu cuối.

### Bảo đảm giao nhận

Với dữ liệu nghiệp vụ quan trọng, cấu hình thường dùng:

- acks=all để producer chờ xác nhận từ các replica đang nằm trong ISR.
- min.insync.replicas ở broker/topic để đặt ngưỡng replica tối thiểu cho ghi với acks=all.
- enable.idempotence=true để Kafka deduplicate các lần retry nội bộ của producer trong phạm vi session/producer identity.
- retries đủ để client thử lại lỗi tạm thời, trong giới hạn delivery.timeout.ms.

Idempotence yêu cầu các cấu hình liên quan phù hợp. Với Kafka client hiện đại, bật idempotence sẽ áp dụng hoặc xác thực một số ràng buộc như acks=all, retries lớn hơn 0 và max.in.flight.requests.per.connection không vượt quá 5. Không nên tắt idempotence chỉ để né lỗi cấu hình khi chưa hiểu tác động đến duplicate và ordering.

acks=all không có nghĩa là mọi replica được cấu hình cho partition đều phải xác nhận. Broker chờ các replica hiện thuộc ISR; min.insync.replicas xác định ngưỡng tối thiểu để chấp nhận ghi. Khi ISR thấp hơn ngưỡng, producer có thể nhận lỗi thay vì ghi với mức độ bền vững thấp hơn.

## 6. Gửi bất đồng bộ trong Java và Spring Kafka

Trong ứng dụng web hoặc service xử lý nhiều request, tránh chặn thread nghiệp vụ bằng cách gọi future.get() ngay sau send(). Hãy đăng ký callback để xử lý kết quả khi producer hoàn tất:

~~~java
CompletableFuture<SendResult<String, OrderCreated>> sendFuture =
    kafkaTemplate.send("orders.created", event.orderId(), event);

sendFuture.whenComplete((result, error) -> {
    if (error != null) {
        log.error(
            "Cannot confirm Kafka delivery: eventId={}, orderId={}",
            event.eventId(),
            event.orderId(),
            error
        );
        return;
    }

    RecordMetadata metadata = result.getRecordMetadata();
    log.info(
        "Kafka record acknowledged: eventId={}, topic={}, partition={}, offset={}",
        event.eventId(),
        metadata.topic(),
        metadata.partition(),
        metadata.offset()
    );
});
~~~

Ví dụ dùng API CompletableFuture của Spring Kafka hiện đại. Các phiên bản Spring Kafka cũ có thể trả về ListenableFuture; cần dùng API tương ứng với phiên bản dự án. Callback nên ngắn gọn: ghi log có cấu trúc, cập nhật trạng thái nhẹ hoặc đẩy công việc tiếp theo sang executor phù hợp. Không gọi HTTP chậm, chờ database hoặc thực hiện tác vụ blocking trong callback của producer.

Nếu một luồng đặc biệt cần chờ kết quả đồng bộ, hãy đặt giới hạn chờ riêng và xử lý đúng trường hợp kết quả chưa xác định:

~~~java
try {
    SendResult<String, OrderCreated> result =
        sendFuture.get(5, TimeUnit.SECONDS);

    log.info(
        "Delivered to {}-{} at offset {}",
        result.getRecordMetadata().topic(),
        result.getRecordMetadata().partition(),
        result.getRecordMetadata().offset()
    );
} catch (TimeoutException e) {
    // Luồng này đã hết thời gian chờ; producer vẫn có thể hoàn tất việc gửi.
    log.warn("Timed out waiting for Kafka result; outcome is not confirmed", e);
} catch (ExecutionException e) {
    // Xem exception gốc để phân loại lỗi gửi.
    log.error("Kafka send failed", e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    log.warn("Interrupted while waiting for Kafka send", e);
}
~~~

Nếu đã gắn whenComplete trước đó, callback vẫn là nơi quan sát kết quả cuối cùng của future. Khi Future.get() hết thời gian chờ, không gọi cancel() hoặc gửi lại ngay theo phản xạ. Hãy để kết quả gửi tiếp tục được theo dõi và chuyển trạng thái nghiệp vụ sang “đang xác minh” nếu chưa thể kết luận.

## 7. Kết quả ghi không xác định và nguy cơ gửi trùng

Giả sử producer gửi event OrderCreated:

1. Broker nhận request và ghi record vào partition.
2. Broker gửi ACK về producer.
3. Mạng bị đứt trước khi ACK đến client.
4. Producer hết thời gian chờ và báo lỗi.
5. Ứng dụng thấy lỗi nhưng không biết record đã được ghi hay chưa.

Đây là kết quả ghi không xác định. Nếu ứng dụng tạo một lần send() mới với cùng nội dung, Kafka có thể lưu cả record cũ và record mới. Khi idempotence bị tắt, retry nội bộ sau khi ACK thất lạc cũng có thể tạo duplicate. Idempotent producer xử lý retry nội bộ của cùng một producer sequence; nó không tự nhận biết rằng hai lời gọi send() độc lập từ ứng dụng là cùng một sự kiện nghiệp vụ.

Phân biệt hai loại retry:

- **Retry nội bộ của producer:** client gửi lại request/batch theo protocol. Idempotence giúp broker nhận diện sequence và tránh ghi trùng do retry trong phạm vi được bảo vệ.
- **Retry ở tầng ứng dụng:** mã nghiệp vụ gọi kafkaTemplate.send() lần nữa sau timeout. Lời gọi mới có thể được xem là record mới và gây duplicate.

Vì vậy, mỗi sự kiện nghiệp vụ nên có eventId ổn định. Consumer cần có cơ chế idempotency, ví dụ lưu eventId đã xử lý cùng với thay đổi nghiệp vụ trong một transaction ở hệ thống đích. Nếu nhận lại eventId, consumer nhận biết và không thực hiện tác động lần hai.

Với luồng phát sự kiện từ database, Transactional Outbox giúp lưu thay đổi nghiệp vụ và bản ghi cần phát trong cùng transaction database. Một relay đọc outbox và gửi sang Kafka; nếu relay gặp timeout và phát lại, eventId ổn định cùng consumer idempotency giúp xử lý duplicate. Outbox không tự làm cho Kafka và database trở thành một transaction phân tán duy nhất, nhưng giúp tránh mất sự kiện giữa commit database và thao tác publish.

Khi kết quả chưa xác định, quy trình xử lý nên là:

1. Giữ eventId và thông tin nghiệp vụ của lần gửi.
2. Theo dõi callback/future gốc nếu producer vẫn còn hoạt động.
3. Nếu cần xác minh sau khi ứng dụng khởi động lại, đối chiếu trạng thái nghiệp vụ hoặc hệ thống downstream bằng eventId/correlation ID.
4. Nếu chính sách yêu cầu phát lại, dùng cùng eventId và bảo đảm consumer idempotent.
5. Ghi nhận trạng thái cuối cùng để vận hành có thể phân biệt đã xác nhận, thất bại chắc chắn và chưa xác định.

Không thể chỉ dựa vào offset hiện tại của một consumer group để kết luận một event cụ thể đã được ghi hay chưa nếu không biết partition, key và offset tương ứng. Kafka cũng không cung cấp một API chung để hỏi broker “eventId này đã được lưu chưa” khi eventId chỉ là trường payload tùy ý. Thiết kế quy trình xác minh ngay từ contract sẽ giúp giảm việc dò tìm thủ công.

## 8. Xử lý riêng các lỗi do broker và replication

Khi producer dùng acks=all, thời gian xác nhận phụ thuộc tình trạng ISR và khả năng replication. Nếu follower replica chậm, broker quá tải hoặc ISR liên tục thay đổi, request có thể tăng latency hoặc thất bại.

Kiểm tra:

- Partition nào đang under-replicated và broker nào đang mất kết nối.
- ISR có giảm xuống dưới min.insync.replicas hay không.
- Broker có log lỗi disk, network, quota hoặc request queue hay không.
- Producer có nhận lỗi NotEnoughReplicas hoặc NotEnoughReplicasAfterAppend hay không.
- Topic có cấu hình replication factor và min.insync.replicas phù hợp yêu cầu độ bền vững không.

NotEnoughReplicasAfterAppend cần được xem xét cẩn thận: tên lỗi cho biết tình trạng replica sau khi append, nên không thể suy ra đơn giản rằng record chắc chắn chưa được ghi. Lưu exception gốc, timestamp, partition và kiểm tra theo cơ chế vận hành của cụm trước khi quyết định phát lại.

Nếu chỉ một số partition gặp sự cố, xem key distribution và broker leader của các partition đó. Một key nóng có thể dồn lượng lớn record vào một partition, tạo nghẽn cục bộ dù throughput trung bình toàn cụm vẫn thấp. Tăng số producer thread không giải quyết được partition nóng nếu tất cả record vẫn có cùng key.

## 9. Trình tự xử lý sự cố trong môi trường thực tế

Khi cảnh báo timeout hoặc buffer cạn xuất hiện, xử lý theo thứ tự sau:

**Bước 1 — Xác định vị trí timeout.** Kiểm tra exception được ném đồng bộ từ send(), lỗi hoàn tất future hay TimeoutException từ Future.get() do ứng dụng tự đặt. Đối chiếu timestamp với max.block.ms, request.timeout.ms và delivery.timeout.ms.

**Bước 2 — Đo áp lực buffer.** Quan sát buffer-available-bytes, waiting-threads, record-queue-time và batch-size. Nếu buffer cạn, kiểm tra tốc độ đầu vào so với tốc độ gửi và thời gian broker phản hồi.

**Bước 3 — Kiểm tra broker và mạng.** Đối chiếu request latency, throttle, ISR, under-replicated partitions, CPU, disk và network. Kiểm tra log kết nối, DNS, TLS, authentication và ACL nếu producer không lấy được metadata hoặc không gửi được.

**Bước 4 — Bảo toàn kết quả chưa xác định.** Không retry mù. Lưu eventId, topic, key, exception và trạng thái future. Nếu producer còn sống, tiếp tục quan sát kết quả cuối cùng; nếu phải phát lại, dùng eventId ổn định và consumer idempotency.

**Bước 5 — Khôi phục lưu lượng có kiểm soát.** Nếu đầu vào vượt năng lực xử lý, áp dụng backpressure hoặc giới hạn tốc độ phát. Khi broker hồi phục, tăng tải dần và theo dõi queue time, buffer và request latency. Tránh khởi động đồng loạt nhiều producer có backlog lớn nếu điều đó tạo thêm burst.

**Bước 6 — Chỉ điều chỉnh tham số sau khi có số liệu.** Tăng buffer khi burst ngắn và heap còn đủ; điều chỉnh batch/linger/compression để cải thiện hiệu quả; thay đổi timeout theo SLA và độ trễ thực tế. Sau thay đổi, kiểm tra cả p95/p99 latency, throughput, lỗi và mức sử dụng bộ nhớ.

## 10. Checklist phòng ngừa

- [ ] Phân biệt max.block.ms, request.timeout.ms, delivery.timeout.ms và timeout do Future.get().
- [ ] Có metric buffer, waiting threads, queue time, request latency, retry và error rate.
- [ ] Theo dõi ISR, under-replicated partitions, quota và tình trạng broker.
- [ ] Dùng idempotent producer cho luồng cần bảo vệ khỏi retry nội bộ gây duplicate.
- [ ] Mỗi event có eventId ổn định; consumer xử lý idempotent.
- [ ] Không tự động gửi lại một event mới chỉ vì luồng gọi hết thời gian chờ.
- [ ] Callback producer không thực hiện tác vụ blocking hoặc xử lý nặng.
- [ ] Buffer memory được tính vào ngân sách heap của từng producer instance.
- [ ] delivery.timeout.ms đủ cho request timeout và batching theo phiên bản client.
- [ ] acks, min.insync.replicas và replication factor phù hợp yêu cầu dữ liệu.
- [ ] Có backpressure khi tốc độ tạo record vượt năng lực gửi.
- [ ] Có cách đối soát hoặc phát lại sự kiện chưa xác định, dựa trên eventId.

Timeout và buffer cạn thường là biểu hiện của sự mất cân bằng giữa tốc độ tạo record, năng lực producer và khả năng xác nhận của broker. Chẩn đoán đúng giai đoạn lỗi giúp tránh tăng timeout một cách mù quáng. Quan trọng hơn, eventId ổn định, idempotent producer, consumer idempotency và quy trình xử lý kết quả chưa xác định giúp hệ thống phục hồi mà không làm mất hoặc nhân đôi tác động nghiệp vụ.
