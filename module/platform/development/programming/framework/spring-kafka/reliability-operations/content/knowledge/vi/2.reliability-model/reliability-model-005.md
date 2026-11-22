# Mất message, duplicate và retry

Trong một hệ thống Spring Kafka, ba hiện tượng **mất message**, **message bị xử lý lặp** và **retry** có liên hệ chặt chẽ nhưng xảy ra ở những thời điểm khác nhau trong vòng đời sự kiện. Muốn vận hành tin cậy, cần xác định rõ message đã được producer gửi tới đâu, broker đã xác nhận điều gì, consumer đã hoàn tất tác vụ nào và offset đã được commit hay chưa.

Kafka lưu trữ message theo partition và offset. Producer gửi record tới partition leader; broker sao chép dữ liệu tới các replica thuộc ISR (in-sync replicas); consumer đọc record rồi xử lý; cuối cùng consumer group lưu offset để ghi nhận vị trí đã xử lý. Mỗi bước có thể gặp lỗi riêng. Vì vậy, cấu hình retry ở một bước không tự động giải quyết lỗi ở các bước còn lại.

## 1. Phân biệt mất message, duplicate và retry

- **Mất message (message loss):** một sự kiện mà hệ thống cần xử lý không còn khả năng được xử lý. Có thể message chưa được broker lưu bền vững, hoặc consumer đã dịch chuyển offset qua message trước khi tác vụ nghiệp vụ hoàn tất.
- **Duplicate:** cùng một sự kiện được gửi hoặc xử lý nhiều lần. Duplicate có thể xuất hiện dù Kafka lưu mỗi record ở một offset riêng và không hề có lỗi dữ liệu trong broker.
- **Retry:** một lần thử xử lý lại sau khi lần trước thất bại. Retry là cơ chế phục hồi; nếu không kiểm soát, nó có thể tạo duplicate, làm đảo thứ tự sự kiện hoặc gây tải tăng đột biến.

Luồng xử lý cơ bản:

    Producer
       |
       v
    Partition leader ----> ISR replicas
       |
       v
    Consumer poll
       |
       v
    Business processing
       |
       v
    Commit consumer offset

Một message chỉ được xem là xử lý hoàn tất khi tác vụ nghiệp vụ đã đạt trạng thái bền vững và offset được ghi nhận theo đúng chính sách. “Producer gửi thành công”, “broker trả ACK” và “consumer xử lý xong” là ba mốc khác nhau.

| Thời điểm xảy ra lỗi | Rủi ro chính | Hướng kiểm soát |
|---|---|---|
| Producer gửi nhưng không chờ xác nhận | Broker có thể chưa lưu message | acks, retry và idempotent producer |
| Leader lỗi trước khi bản sao đủ an toàn | Message đã ACK có thể không còn trên replica được bầu | Replication factor, ISR và leader election |
| Consumer commit offset trước khi xử lý xong | Message có thể bị bỏ qua sau khi restart | Tắt auto commit; commit sau xử lý |
| Consumer xử lý xong nhưng chưa commit offset | Message có thể được giao lại | Idempotent business handler |
| Xử lý tạm thời thất bại | Message cần được thử lại | Backoff, error handler hoặc retry topic |
| Message không thể xử lý sau nhiều lần thử | Một record lỗi có thể chặn luồng | Dead-letter topic (DLT) và quy trình phục hồi |

## 2. Ngăn mất message ở phía producer và broker

### 2.1. Chọn mức xác nhận phù hợp

Producer dùng thuộc tính acks để quyết định mức xác nhận cần chờ:

- acks=0: producer không chờ broker xác nhận. Ứng dụng có thể không phát hiện message chưa tới broker.
- acks=1: leader xác nhận sau khi ghi record vào log cục bộ. Nếu leader lỗi trước khi replica khác nhận được record, message có thể mất khi một replica cũ được bầu làm leader.
- acks=all (tương đương -1): leader chỉ xác nhận sau khi các replica hiện thuộc ISR đã ghi nhận record. Đây là lựa chọn phù hợp cho luồng cần độ bền cao.

acks=all cần đi cùng cấu hình replication phù hợp. Ví dụ, topic có replication factor 3 và min.insync.replicas=2. Khi đó, producer dùng acks=all sẽ cần ít nhất hai replica trong ISR để chấp nhận ghi. Nếu ISR giảm xuống dưới mức tối thiểu, broker từ chối ghi thay vì xác nhận một bản ghi không đạt mức an toàn yêu cầu. Ứng dụng phải xử lý lỗi gửi và có thể thử lại khi cụm phục hồi.

Ví dụ cấu hình broker/topic thường dùng cho dữ liệu quan trọng:

    # Cấu hình broker hoặc cấu hình topic tương ứng
    default.replication.factor=3
    min.insync.replicas=2
    unclean.leader.election.enable=false

Hãy tạo topic production với replication factor rõ ràng; default.replication.factor chủ yếu áp dụng khi broker tự tạo topic. Tắt unclean leader election giúp tránh bầu một replica ngoài ISR có thể thiếu dữ liệu, đổi lại partition có thể tạm ngừng ghi/đọc khi không còn replica đủ điều kiện. Đây là quyết định giữa tính sẵn sàng và nguy cơ mất dữ liệu.

Replication không thay thế backup. Nó bảo vệ trước một số lỗi broker và ổ đĩa, nhưng không bảo vệ đầy đủ trước thao tác xóa nhầm, lỗi ứng dụng ghi dữ liệu sai, retention hết hạn hoặc sự cố ảnh hưởng đồng thời toàn bộ replica.

### 2.2. Bật idempotent producer và xử lý lỗi gửi

Khi producer gửi một batch nhưng ACK bị mất trên đường truyền, producer có thể gửi lại. Nếu không có cơ chế chống lặp ở giao thức producer, broker có thể ghi cùng một lần gửi thành nhiều record.

Bật idempotent producer để Kafka nhận diện các lần gửi lại thuộc cùng producer session và tránh ghi trùng do retry ở tầng giao thức:

    spring:
      kafka:
        producer:
          acks: all
          properties:
            enable.idempotence: true
            delivery.timeout.ms: 120000
            request.timeout.ms: 30000

Các giá trị timeout trên chỉ là ví dụ để minh họa; hãy điều chỉnh theo độ trễ mạng, SLA và thời gian phục hồi dự kiến. delivery.timeout.ms giới hạn tổng thời gian producer chờ gửi thành công hoặc báo lỗi. Khi hết thời hạn, ứng dụng phải ghi nhận lỗi và quyết định xử lý tiếp theo.

Idempotent producer bảo vệ các lần retry gửi record trong phạm vi producer session theo cơ chế của Kafka. Nó không ngăn ứng dụng chủ động gọi send() hai lần cho cùng một sự kiện nghiệp vụ, không tự khử trùng lặp giữa hai producer độc lập và không thay thế idempotency ở consumer. Nếu ứng dụng khởi động lại rồi phát lại cùng một sự kiện, hệ thống vẫn cần một eventId ổn định để nhận diện sự kiện đó.

Không cấu hình các giá trị acks, retries hoặc max.in.flight.requests.per.connection xung đột với yêu cầu của idempotence. Kafka client có các ràng buộc tương thích và có thể từ chối cấu hình không hợp lệ. Hãy kiểm tra cấu hình producer thực tế sau khi ứng dụng khởi động.

### 2.3. Phân biệt lỗi gửi với lỗi xử lý

Producer cần quan sát kết quả của thao tác gửi. Với API bất đồng bộ, việc gọi send() không đồng nghĩa message đã được broker xác nhận. Ứng dụng nên theo dõi callback hoặc future của thao tác gửi, ghi nhận lỗi cuối cùng và không âm thầm bỏ qua exception.

Nếu ứng dụng ghi dữ liệu vào database rồi phát một event Kafka, có một khoảng lỗi giữa hai thao tác: database commit thành công nhưng ứng dụng dừng trước khi gửi event. Producer retry đơn thuần không giải quyết được khoảng trống này. Có thể dùng **Transactional Outbox**: ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database, sau đó một tiến trình relay gửi outbox sang Kafka. Relay có thể gửi lặp, vì vậy consumer vẫn cần idempotency.

## 3. Ngăn mất message ở phía consumer

### 3.1. Commit offset sau khi xử lý thành công

Consumer group lưu offset để biết vị trí tiếp theo cần đọc. Nếu offset được commit trước khi tác vụ nghiệp vụ hoàn tất, consumer có thể bỏ qua record khi tiến trình lỗi.

Ví dụ tình huống nguy hiểm:

1. Consumer nhận record ở offset 120.
2. Consumer commit offset tiếp theo là 121.
3. Ứng dụng gọi database nhưng tiến trình bị dừng trước khi transaction hoàn tất.
4. Consumer khởi động lại và tiếp tục từ offset 121.
5. Record 120 không được giao lại cho consumer group đó.

Với xử lý cần tránh mất message, tắt auto commit và để Spring Kafka container quản lý commit sau khi listener hoàn thành thành công:

    spring:
      kafka:
        consumer:
          enable-auto-commit: false
        listener:
          ack-mode: record

Với AckMode.RECORD, container commit offset của record sau khi listener xử lý thành công. Với AckMode.BATCH, offset được commit sau khi các record trong poll batch được xử lý thành công. Chọn chế độ phù hợp với listener và mức độ chấp nhận phát lại.

Nếu listener dùng manual acknowledgment, chỉ gọi acknowledge() sau khi tác vụ bền vững đã hoàn tất. Không ACK ngay khi vừa nhận record hoặc trước khi database transaction commit. Việc commit offset có thể thất bại hoặc consumer có thể bị rebalance; do đó, xử lý xong nhưng chưa commit vẫn có thể dẫn tới giao lại. Đây là nguồn duplicate phổ biến và cần được giải quyết bằng idempotency.

### 3.2. Hiểu ranh giới transaction

Khi listener ghi database, thứ tự thao tác thường là:

    Nhận record
        |
        v
    Bắt đầu database transaction
        |
        v
    Thực hiện thay đổi nghiệp vụ
        |
        v
    Database commit
        |
        v
    Commit Kafka offset

Nếu tiến trình dừng sau database commit nhưng trước offset commit, Kafka giao lại record. Nếu đảo thứ tự và commit offset trước database, lỗi database có thể làm mất tác vụ. Với một database và Kafka độc lập, không thể tạo một transaction nguyên tử bao trùm cả hai chỉ bằng cách thay đổi thứ tự hai lệnh.

Vì vậy, consumer ghi database nên thiết kế thao tác có thể chạy lặp an toàn, ví dụ dùng unique constraint trên eventId, upsert có điều kiện hoặc bảng inbox. Nếu cần phối hợp nhiều hệ thống, hãy xác định rõ transaction boundary và dùng outbox/inbox hoặc một cơ chế điều phối phù hợp.

### 3.3. Chú ý retention và offset không còn hợp lệ

Kafka chỉ giữ record theo chính sách retention của topic. Consumer bị dừng lâu hơn thời gian retention có thể không còn đọc được dữ liệu cũ. Với topic compacted, Kafka có thể loại bỏ các phiên bản cũ của cùng key theo chính sách compaction; compacted topic không phải bản lưu trữ mọi thay đổi lịch sử.

Theo dõi consumer lag, thời gian consumer ngừng hoạt động và tuổi của record chưa xử lý. Đặt retention dựa trên thời gian gián đoạn tối đa cần phục hồi, dung lượng lưu trữ và yêu cầu nghiệp vụ. Cấu hình auto.offset.reset cũng cần được chọn có chủ đích: earliest có thể đọc lại dữ liệu còn lưu khi group chưa có offset hợp lệ; latest có thể bỏ qua phần dữ liệu cũ hơn vị trí bắt đầu mới. Cả hai không thể khôi phục record đã hết retention.

## 4. Hiểu và kiểm soát duplicate

### 4.1. Duplicate xuất hiện ở đâu?

Một sự kiện có thể xuất hiện nhiều lần trong các trường hợp sau:

- Producer không nhận được ACK và gửi lại; idempotent producer xử lý loại duplicate ở tầng giao thức này.
- Logic ứng dụng phát cùng một event nhiều lần, chẳng hạn người dùng gửi lại yêu cầu hoặc outbox relay khởi động lại.
- Consumer đã ghi database thành công nhưng chưa commit offset rồi bị dừng hoặc rebalance.
- Error handler, retry topic hoặc quy trình DLT re-drive giao lại cùng sự kiện.
- Hai luồng độc lập cùng phát biểu diễn của một thay đổi nghiệp vụ.

Do đó, “Kafka có offset duy nhất” không có nghĩa “một sự kiện nghiệp vụ chỉ được xử lý một lần”. Offset nhận diện một record trong một partition; nó không tự nhận diện các bản sao logic được gửi ở offset khác hoặc topic khác.

### 4.2. Dùng event ID ổn định

Mỗi sự kiện nghiệp vụ nên có một định danh ổn định, ví dụ eventId, được tạo khi sự kiện hình thành và giữ nguyên qua các lần gửi lại, retry topic và DLT. Không tạo event ID mới mỗi lần retry, vì như vậy hệ thống không thể nhận ra các lần thử thuộc cùng sự kiện.

Ví dụ payload:

    {
      "eventId": "evt-8f21a6",
      "eventType": "OrderPaid",
      "aggregateId": "order-1042",
      "occurredAt": "2026-11-15T10:30:00Z",
      "payload": {
        "orderId": "order-1042",
        "amount": 125000
      }
    }

Ở consumer ghi database, có thể tạo bảng inbox hoặc bảng processed_event với event_id là khóa duy nhất. Việc đánh dấu đã xử lý và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng database transaction:

    BEGIN;

    INSERT INTO processed_event (event_id, processed_at)
    VALUES (:event_id, CURRENT_TIMESTAMP)
    ON CONFLICT (event_id) DO NOTHING;

    -- Chỉ thực hiện thay đổi nghiệp vụ nếu INSERT thực sự thêm một hàng.
    -- Nếu event_id đã tồn tại, bỏ qua tác vụ đã hoàn tất trước đó.

    COMMIT;

Ứng dụng cần kiểm tra số hàng được insert để quyết định có thực hiện thay đổi nghiệp vụ hay không. Nếu thao tác nghiệp vụ lỗi, transaction phải rollback cả dấu mốc inbox để lần giao lại có thể thử lại. Không commit dấu mốc đã xử lý trong một transaction riêng trước khi cập nhật dữ liệu nghiệp vụ, vì điều đó có thể khiến record bị bỏ qua dù tác vụ chưa hoàn tất.

Với một consumer chỉ xử lý một topic, cặp topic + partition + offset có thể nhận diện một lần xuất hiện cụ thể. Tuy nhiên, eventId thường phù hợp hơn cho idempotency nghiệp vụ vì có thể giữ nguyên khi cùng sự kiện được phát lại sang topic khác hoặc được tạo lại từ outbox.

### 4.3. Thiết kế thao tác nghiệp vụ idempotent

Một thao tác idempotent cho kết quả nghiệp vụ tương đương khi được thực hiện nhiều lần với cùng một định danh hoặc cùng một trạng thái đích. Ví dụ:

- Đặt trạng thái đơn hàng thành PAID có điều kiện, thay vì cộng số lần thanh toán.
- Dùng mã giao dịch duy nhất để tránh ghi nhận một khoản thanh toán hai lần.
- Tạo bản ghi với unique key và xử lý xung đột có chủ đích.
- Dùng version của aggregate để từ chối cập nhật cũ hoặc lặp.

Không phải mọi thao tác đều có thể biến thành phép gán trạng thái. Với thao tác cộng/trừ số dư, gửi thông báo hoặc gọi API tính phí, cần khóa idempotency mà hệ thống đích hiểu và lưu bền vững. Nếu API bên ngoài hỗ trợ idempotency key, hãy truyền cùng key qua tất cả lần thử.

## 5. Chọn delivery semantics

Ba cách diễn đạt phổ biến mô tả sự đánh đổi giữa mất message và duplicate:

| Semantics | Thời điểm ghi nhận offset | Đặc điểm |
|---|---|---|
| At-most-once | Trước khi xử lý | Tránh giao lại trong một số tình huống nhưng có thể mất tác vụ |
| At-least-once | Sau khi xử lý thành công | Tránh bỏ qua record chưa xử lý nhưng có thể xử lý lặp |
| Exactly-once | Kết hợp dữ liệu và offset trong transaction được hỗ trợ | Có thể đạt trong phạm vi Kafka transaction; không tự bao trùm side effect ở hệ thống ngoài |

Với nhiều hệ thống nghiệp vụ, **at-least-once kết hợp idempotent consumer** là lựa chọn thực tế: record có thể được giao lại, nhưng hiệu ứng nghiệp vụ chỉ được áp dụng một lần theo eventId.

Kafka transaction hỗ trợ luồng consume-process-produce trong Kafka: record đầu vào, record đầu ra và offset của consumer có thể được commit nguyên tử trong cùng transaction. Consumer đọc kết quả transaction nên dùng isolation.level=read_committed để không nhìn thấy record thuộc transaction chưa commit hoặc đã abort.

Ví dụ cấu hình consumer khi đọc dữ liệu transactional:

    spring:
      kafka:
        consumer:
          properties:
            isolation.level: read_committed

Trong Spring Boot, có thể bật transaction cho producer bằng spring.kafka.producer.transaction-id-prefix với prefix duy nhất cho từng instance ứng dụng. Cách cấu hình transaction và listener container cần khớp với phiên bản Spring Kafka đang dùng. Kafka EOS bảo vệ chuỗi thao tác trong phạm vi Kafka; nếu listener còn ghi database, gọi HTTP hoặc gửi email, các side effect đó vẫn cần transaction/idempotency riêng.

## 6. Retry khi xử lý thất bại

### 6.1. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng có thể khắc phục bằng cách thử lại.

| Nhóm lỗi | Ví dụ | Hành động phù hợp |
|---|---|---|
| Tạm thời (transient) | Database timeout, dịch vụ phụ thuộc tạm mất kết nối, lỗi mạng | Retry có backoff và giới hạn |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai định dạng, vi phạm quy tắc cố định | Không retry vô hạn; chuyển DLT hoặc luồng xử lý lỗi |
| Lỗi cấu hình/quyền | Sai credential, thiếu quyền truy cập, topic không tồn tại | Cảnh báo và khắc phục cấu hình; retry liên tục thường không giúp |
| Lỗi cạnh tranh/trạng thái | Version xung đột, tài nguyên chưa sẵn sàng | Đánh giá khả năng retry, tính idempotent và giới hạn |

Retry chỉ hữu ích khi nguyên nhân có khả năng biến mất theo thời gian. Một record sai schema sẽ tiếp tục thất bại dù được thử hàng nghìn lần. Với lỗi tạm thời, nên dùng số lần thử hữu hạn, khoảng nghỉ tăng dần và jitter để nhiều consumer không đồng loạt gọi lại dịch vụ đang quá tải.

Ví dụ backoff tăng dần:

    Lần thử 1: thất bại
       |
       +-- chờ 1 giây
    Lần thử 2: thất bại
       |
       +-- chờ 2 giây
    Lần thử 3: thất bại
       |
       +-- chờ 4 giây
    Hết giới hạn -> DLT / quy trình phục hồi

Tránh retry vô hạn và tránh nhân chồng nhiều tầng retry mà không tính tổng thời gian. Ví dụ HTTP client retry 3 lần bên trong listener, trong khi Kafka listener cũng retry 5 lần, có thể tạo ra nhiều lần gọi dịch vụ hơn dự kiến. Hãy xác định tổng ngân sách retry, timeout và thời hạn xử lý của sự kiện.

### 6.2. Blocking retry với DefaultErrorHandler

Spring Kafka cung cấp DefaultErrorHandler để container thử lại record trên luồng xử lý hiện tại. Cách này phù hợp khi cần giữ thứ tự trong partition và thời gian retry ngắn. Trong thời gian chờ, partition/consumer có thể bị ảnh hưởng bởi việc xử lý record đang lỗi; không nên dùng backoff rất dài mà không đánh giá tác động đến poll interval, throughput và rebalance.

Ví dụ cấu hình với ba lần retry sau lần xử lý đầu tiên, mỗi lần cách nhau một giây, sau đó chuyển record sang DLT:

    @Bean
    DefaultErrorHandler kafkaErrorHandler(
            KafkaTemplate<Object, Object> kafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(kafkaTemplate);

        DefaultErrorHandler handler =
                new DefaultErrorHandler(recoverer, new FixedBackOff(1_000L, 3L));

        // Lỗi dữ liệu không thể khắc phục bằng retry sẽ đi thẳng tới recoverer.
        handler.addNotRetryableExceptions(IllegalArgumentException.class);

        return handler;
    }

Ví dụ giả định ứng dụng đã cấu hình serializer/deserializer phù hợp và topic DLT có thể nhận record. Recoverer mặc định thường định tuyến tới topic có hậu tố .DLT và giữ partition tương ứng; cần bảo đảm DLT tồn tại và có đủ partition cho cách định tuyến đang dùng. Có thể tùy chỉnh destination resolver để định tuyến theo loại lỗi hoặc loại topic.

Khi record được gửi sang DLT, hãy bảo đảm việc publish DLT thành công trước khi xem record gốc là đã phục hồi. Nếu gửi DLT thất bại, hệ thống cần giữ khả năng thử lại và phát cảnh báo; không được âm thầm bỏ qua record gốc.

### 6.3. Non-blocking retry với @RetryableTopic

Với lỗi cần chờ lâu hơn hoặc không muốn giữ partition chính trong thời gian backoff, Spring Kafka hỗ trợ retry topic qua @RetryableTopic. Record thất bại được chuyển qua các topic retry theo lịch backoff; khi hết số lần thử, record đi tới DLT.

    @RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 1_000, multiplier = 2.0),
        dltTopicSuffix = ".DLT"
    )
    @KafkaListener(topics = "orders", groupId = "order-processor")
    public void consume(OrderCreated event) {
        orderService.process(event);
    }

Đây là ví dụ minh họa; cần cấu hình topic retry/DLT, serializer và listener phù hợp với phiên bản Spring Kafka của dự án. attempts biểu diễn số lần giao/thử theo cấu hình annotation; hãy xác nhận cách đếm và số topic được tạo theo phiên bản thư viện đang chạy.

Retry topic giải phóng luồng chính trong lúc chờ, nhưng có thể làm thay đổi thứ tự xử lý. Ví dụ record A của một order bị lỗi và chuyển sang retry topic, trong khi record B của cùng order được xử lý ngay trên topic chính. Khi A quay lại sau, B có thể đã được áp dụng trước A. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo key, hãy cân nhắc blocking retry ngắn, thiết kế version/sequence ở aggregate hoặc một cơ chế điều phối theo key.

Không cấu hình đồng thời nhiều cơ chế retry cho cùng một lỗi mà không có chủ đích. Chọn một chiến lược chính, xác định số lần thử tổng cộng và nơi lưu record sau khi hết retry.

### 6.4. Dead-letter topic và phục hồi

DLT lưu record không thể xử lý sau chính sách retry. DLT giúp tách một record lỗi khỏi luồng chính, nhưng không tự sửa dữ liệu hoặc bảo đảm record sẽ được xử lý lại.

Một quy trình DLT nên lưu đủ thông tin để điều tra:

- Payload và key gốc, cùng topic, partition và offset nguồn.
- eventId, timestamp và correlation ID nếu có.
- Exception cuối cùng, nguyên nhân và số lần thử.
- Thông tin retry/DLT headers do Spring Kafka bổ sung.
- Thời điểm record được chuyển sang DLT.

Quy trình vận hành thường gồm: cảnh báo khi DLT tăng, phân loại lỗi, xác định nguyên nhân, sửa dữ liệu hoặc code, rồi re-drive có kiểm soát. Khi phát lại, giữ nguyên eventId để consumer idempotent nhận diện bản sao. Tránh phát lại toàn bộ DLT cùng lúc nếu hệ thống phụ thuộc vẫn đang quá tải.

## 7. Cấu hình Spring Kafka tham khảo

Một cấu hình nền tảng cho luồng cần ưu tiên độ bền và xử lý at-least-once có thể bắt đầu như sau:

    spring:
      kafka:
        producer:
          acks: all
          properties:
            enable.idempotence: true
        consumer:
          enable-auto-commit: false
        listener:
          ack-mode: record

Ý nghĩa của các lựa chọn:

- Producer chờ xác nhận từ ISR và dùng idempotence để tránh duplicate do retry giao thức.
- Consumer không tự commit offset theo lịch độc lập với listener.
- Container commit offset sau khi listener xử lý record thành công.
- Nếu listener thất bại, error handler quyết định retry, recover hoặc chuyển DLT.
- Consumer handler vẫn phải idempotent vì lỗi có thể xảy ra sau khi side effect đã hoàn tất nhưng trước khi offset commit.

Đây là điểm khởi đầu, không phải cấu hình đầy đủ cho mọi hệ thống. Cần điều chỉnh replication factor, min.insync.replicas, retention, timeout, concurrency, poll settings và chính sách retry theo tải, kích thước record, SLA cũng như phiên bản Kafka/Spring Kafka. Các cấu hình broker và topic phải được triển khai ở đúng lớp; đặt một thuộc tính trong Spring Boot không tự thay đổi cấu hình cluster.

## 8. Theo dõi độ tin cậy khi vận hành

Để phát hiện sớm mất message, duplicate và retry bất thường, cần theo dõi cả producer, broker, consumer và DLT.

**Producer**

- Tỷ lệ gửi lỗi và số lần retry.
- Độ trễ gửi, request timeout và buffer cạn.
- Số record được gửi thành công so với số event ứng dụng dự kiến phát.

**Broker**

- Under-replicated partitions và offline partitions.
- ISR shrink/expand, lỗi request và tình trạng ổ đĩa.
- Replication lag và trạng thái controller/leader election.

**Consumer**

- Consumer lag theo group, topic và partition.
- Tốc độ xử lý, thời gian xử lý mỗi record và số lần rebalance.
- Tỷ lệ exception, retry, commit lỗi và số record đang chờ xử lý.

**Retry và DLT**

- Số record đi vào từng retry topic và DLT.
- Tuổi của record cũ nhất trong DLT.
- Tỷ lệ retry thành công, retry hết hạn và re-drive.
- Số event bị từ chối do lỗi dữ liệu không thể retry.

Log nên chứa eventId, topic, partition, offset, key, consumer group, attempt và correlation ID để nối các lần thử. Tránh ghi payload nhạy cảm vào log. Một chỉ số “consumer lag bằng 0” không đủ chứng minh không mất message: record có thể đã bị commit sớm hoặc đã hết retention. Cần đối chiếu số lượng event đầu vào, kết quả nghiệp vụ, lỗi gửi và DLT.

## 9. Các tình huống cần mô phỏng trong môi trường thử nghiệm

Khi xây dựng quy trình vận hành, hãy mô phỏng các cửa sổ lỗi quan trọng và xác nhận kết quả nghiệp vụ:

1. Producer gửi record rồi mất kết nối trước khi nhận ACK: kiểm tra retry và idempotent producer.
2. Một broker leader dừng ngay sau khi ghi: kiểm tra ISR, replication factor và mức xác nhận.
3. Consumer dừng trước database commit: record phải có thể được giao lại.
4. Consumer dừng sau database commit nhưng trước offset commit: record có thể được giao lại nhưng thay đổi nghiệp vụ không được nhân đôi.
5. Dịch vụ phụ thuộc timeout trong một khoảng ngắn: retry phải phục hồi được mà không tạo tải tăng đột biến.
6. Record sai schema: không retry vô hạn; record phải đến DLT hoặc luồng xử lý lỗi đã định.
7. DLT không khả dụng: record gốc không được đánh dấu phục hồi thành công khi chưa lưu được bản lỗi.
8. Consumer ngừng lâu hơn retention: xác nhận quy trình phát hiện và khôi phục dữ liệu từ nguồn lưu trữ khác nếu yêu cầu nghiệp vụ cần.

Các tình huống này giúp đội vận hành kiểm chứng giả định về offset, transaction và retry trước khi áp dụng vào production.

## 10. Nguyên tắc lựa chọn theo yêu cầu nghiệp vụ

| Yêu cầu | Thiết kế nên cân nhắc |
|---|---|
| Không muốn mất record khi broker gặp lỗi đơn lẻ | acks=all, replication factor phù hợp, min.insync.replicas và leader election an toàn |
| Không muốn mất tác vụ khi consumer restart | Tắt auto commit; commit sau xử lý thành công |
| Chấp nhận giao lại nhưng không muốn áp dụng nghiệp vụ hai lần | At-least-once và consumer idempotent theo eventId |
| Consume rồi produce sang Kafka với tính nguyên tử | Kafka transaction và consumer read_committed |
| Ghi database rồi phát event | Transactional Outbox |
| Consumer nhận event và cập nhật database | Inbox/dedup trong cùng database transaction với thay đổi nghiệp vụ |
| Lỗi phụ thuộc chỉ kéo dài ngắn | Blocking retry với backoff hữu hạn |
| Retry cần chờ lâu và không nên giữ luồng chính | Retry topic, đồng thời đánh giá ảnh hưởng thứ tự |
| Record không thể xử lý tự động | DLT, cảnh báo, điều tra và re-drive có kiểm soát |

Độ tin cậy của Spring Kafka đến từ việc phối hợp đúng các mốc xác nhận, replication, offset commit, idempotency và retry. Hãy chọn semantics dựa trên hậu quả nghiệp vụ của việc mất hoặc lặp sự kiện, sau đó thiết kế consumer và quy trình vận hành để xử lý được các cửa sổ lỗi còn lại.