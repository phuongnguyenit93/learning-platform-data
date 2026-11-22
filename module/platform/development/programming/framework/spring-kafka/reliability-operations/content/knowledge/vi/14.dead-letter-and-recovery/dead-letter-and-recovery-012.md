# Replay từ DLT về topic gốc

Trong Spring Kafka, Dead Letter Topic (DLT) là nơi lưu những record mà luồng xử lý chính không thể hoàn tất sau retry hoặc được phân loại là không nên retry. Đưa record vào DLT giúp consumer chính tiếp tục hoạt động, nhưng **không có nghĩa vấn đề nghiệp vụ đã được giải quyết**. Sau khi tìm và sửa nguyên nhân lỗi, đội vận hành có thể cần **replay từ DLT về topic gốc** để xử lý lại các record đã bị cách ly.

Replay là một quy trình có kiểm soát: chọn đúng record, xác nhận đủ điều kiện, publish record trở lại topic nguồn, theo dõi kết quả xử lý và bảo đảm có thể truy vết. Nó khác với việc chỉ thay đổi offset của consumer group hoặc khởi động lại listener. Đặc biệt, publish thành công vào topic gốc **không chứng minh** listener nghiệp vụ đã xử lý thành công.

## 1. DLT nằm ở đâu trong vòng đời xử lý?

Một topology phổ biến dùng `DefaultErrorHandler` và `DeadLetterPublishingRecoverer` để chuyển record thất bại từ topic nguồn sang DLT. Với `@RetryableTopic`, record có thể đi qua một hoặc nhiều retry topic trước khi đến DLT. Tên topic DLT phụ thuộc cấu hình: chẳng hạn `orders.DLT` khi dùng một resolver như `record.topic() + ".DLT"`, hoặc tên có hậu tố khác trong retry-topic infrastructure. Không nên mặc định mọi ứng dụng đều dùng cùng quy ước tên.

```text
Producer
   |
   v
orders (topic gốc)
   |
   v
Spring Kafka listener
   |
   +---- xử lý thành công ----------------> kết thúc
   |
   +---- lỗi ----> retry / error handler
                           |
                      retry hết / fatal
                           |
                           v
                     orders.DLT
                           |
                     sửa nguyên nhân
                           |
                     phê duyệt replay
                           |
                           v
                    replay publisher
                           |
                           v
                     orders (topic gốc)
                           |
                           v
                    listener xử lý lại
```

Ở nhánh thông thường, DLT là một Kafka topic độc lập với partition và offset riêng. Khi record được publish vào DLT, nó nhận một offset mới **trong DLT**, không giữ nguyên offset vật lý ở topic nguồn. Sau khi replay về `orders`, broker cấp tiếp một offset mới tại topic `orders`. Hai lần xuất hiện này được liên kết bằng metadata nghiệp vụ và header provenance, không phải bằng việc tái sử dụng offset cũ.

## 2. Replay khác retry, reprocessing và reset offset

| Cơ chế | Nguồn record | Mục đích | Lưu ý |
|---|---|---|---|
| Blocking retry | Record đang được error handler xử lý | Thử lại lỗi có khả năng phục hồi | Có thể giữ partition và tăng lag |
| Non-blocking retry | Retry topic của Spring Kafka | Hoãn xử lý mà không chặn topic chính | Có thể thay đổi thứ tự xử lý |
| DLT replay | Một record đã nằm trong DLT | Đưa record đã cách ly trở lại luồng nghiệp vụ | Cần phê duyệt, giới hạn và idempotency |
| Consumer offset reset | Log của topic được consumer group đọc | Cho group đọc lại từ một offset khác | Ảnh hưởng toàn bộ dải record, không riêng record trong DLT |
| Tạo event bù trừ | Event mới theo hợp đồng nghiệp vụ | Sửa trạng thái bằng hành động có chủ đích | Không nhất thiết giống payload gốc |

Ví dụ, `orders` đã tiến từ offset 500 tới 2.000, trong khi record lỗi tại offset 530 đã được đưa vào `orders.DLT`. Đặt lại group offset về 530 sẽ khiến listener đọc lại **cả hàng nghìn record khác**, có thể gây side effect trùng. Replay chọn riêng record tương ứng trong DLT sẽ hạn chế phạm vi tác động, dù vẫn phải kiểm soát duplicate và thứ tự nghiệp vụ.

Không dùng reset offset như một thay thế mặc định cho DLT replay. Nếu cần phát lại toàn bộ một khoảng dữ liệu, đó là bài toán backfill/reprocessing với kế hoạch riêng.

## 3. Các điều kiện bắt buộc trước khi replay

Replay phải bắt đầu từ **nguyên nhân lỗi**. Nếu payload sai định dạng hoặc event version không được consumer hỗ trợ, publish nguyên byte dữ liệu cũ trở lại topic gốc thường chỉ tạo thêm một bản ghi lỗi rồi quay lại DLT.

Trước khi cho phép một record replay, cần xác nhận:

1. **Nguyên nhân đã được hiểu:** lỗi schema, dữ liệu, dependency, bug ứng dụng hay cấu hình bảo mật.
2. **Cách khắc phục đã sẵn sàng:** consumer đã được sửa, dependency đã phục hồi, hoặc payload được chuyển đổi theo quy trình được phê duyệt.
3. **Tác động nghiệp vụ được đánh giá:** record có thể đã tạo một phần side effect; replay không được phát sinh giao dịch/hóa đơn/thông báo trùng.
4. **Đúng topic và owner:** xác minh DLT, topic gốc, môi trường, cluster, group và dịch vụ chịu trách nhiệm.
5. **Có phạm vi cụ thể:** danh sách event ID hoặc tọa độ `DLT topic + partition + offset`, thời gian, số lượng, điều kiện lọc.
6. **Có kế hoạch rollback hoặc xử lý lại:** nếu replay tiếp tục lỗi, phải biết record sẽ đi đâu và ai xử lý.
7. **Có giới hạn tốc độ:** tránh đưa hàng trăm nghìn record cũ vào topic chính trong lúc dịch vụ đang chạy tải cao.

Một record đã lỗi vì phiên bản schema mới có thể hợp lệ sau khi consumer được nâng cấp. Ngược lại, một record bị từ chối theo business rule bất biến có thể phải được kết thúc như một kết quả nghiệp vụ chứ không nên replay.

## 4. Tìm record gốc từ DLT metadata

`DeadLetterPublishingRecoverer` thường bổ sung header chứa thông tin nguồn và exception, ví dụ topic, partition, offset, timestamp gốc và các thuộc tính lỗi. Trong Spring Kafka, nhóm hằng số `KafkaHeaders.DLT_*` cung cấp tên header tương ứng, chẳng hạn `KafkaHeaders.DLT_ORIGINAL_TOPIC`, `KafkaHeaders.DLT_ORIGINAL_PARTITION` và `KafkaHeaders.DLT_ORIGINAL_OFFSET`. Header cụ thể và số lần lưu giữ metadata có thể khác nhau giữa các phiên bản và cấu hình recoverer.

Một record DLT có thể được mô tả như sau:

```text
DLT record:
  topic:     orders.DLT
  partition: 2
  offset:    730
  key:       order-12345

Original metadata (headers):
  original topic:     orders
  original partition: 2
  original offset:    530
  exception class:    ...InvalidOrderPayloadException

Business metadata:
  event-id:           evt-9b62
  correlation-id:     request-2187
```

Trong ví dụ, `orders.DLT` partition 2 offset 730 là vị trí của **bản ghi trong DLT**, còn `orders` partition 2 offset 530 là nơi lỗi bắt nguồn. Để chọn đúng record replay, dùng tọa độ DLT hoặc business event ID đã kiểm chứng. Không dùng offset nguồn như thể đó cũng là offset trong DLT.

Nếu recoverer tùy chỉnh không tạo các header nguồn, ứng dụng phải có cơ chế provenance riêng. Không tự suy diễn topic gốc chỉ từ một tên DLT bất kỳ rồi publish mà không kiểm tra whitelist; một job replay cần bảo vệ khỏi việc ghi nhầm topic, cluster hoặc môi trường.

## 5. Chọn chiến lược replay

Ba cách thường gặp:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Replay một record / một danh sách đã duyệt | Job đọc tọa độ DLT cụ thể, kiểm tra rồi publish lại | Sự cố nhỏ, cần kiểm soát chặt từng event |
| Replay một khoảng DLT | Job đọc một dải offset, áp dụng bộ lọc và giới hạn tốc độ | Backlog lớn, đã xác định điều kiện an toàn |
| Replay consumer chuyên dụng | Listener trên DLT được khởi động theo yêu cầu và có chính sách phê duyệt | Vận hành lặp lại thường xuyên, có owner riêng |

Không nên tạo một `@KafkaListener(topics = "orders.DLT")` chạy liên tục rồi tự động publish **mọi record** về `orders`. Khi lỗi gốc chưa được sửa, record sẽ luân chuyển từ topic chính tới DLT rồi quay lại topic chính, hình thành **vòng lặp poison message**.

Với công việc có yêu cầu kiểm soát và audit, một job chạy theo danh sách DLT partition/offset đã duyệt thường dễ kiểm tra hơn một consumer luôn tự động replay mọi record.

## 6. Ví dụ Spring Kafka: replay đúng một record đã chọn

Ví dụ dưới đây minh họa một `DltReplayService` đọc một tọa độ DLT được cấp từ quy trình vận hành, xác nhận original topic là `orders`, giới hạn số lần replay và publish lại **raw payload bytes**. Việc đọc raw bytes giúp tránh phải deserialize một payload đã từng gây lỗi; tuy nhiên nó chỉ an toàn nếu DLT chứa bytes tương ứng với định dạng mà consumer topic gốc cần nhận.

Đầu tiên, tạo `ConsumerFactory<String, byte[]>` dành riêng cho job đọc DLT. Consumer này không auto commit; ví dụ dùng bootstrap và cấu hình kết nối do Spring Boot cung cấp trong thực tế:

```java
@Bean("dltReplayConsumerFactory")
ConsumerFactory<String, byte[]> dltReplayConsumerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> props =
            new HashMap<>(kafkaProperties.buildConsumerProperties());

    props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-dlt-replay-admin");
    props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
    props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
            StringDeserializer.class);
    props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
            ByteArrayDeserializer.class);

    return new DefaultKafkaConsumerFactory<>(props);
}
```

Trong Spring Boot các phiên bản khác nhau, API xây dựng consumer properties từ `KafkaProperties` có thể nhận thêm cấu hình SSL bundles; hãy dùng overload phù hợp với phiên bản đang triển khai. `KafkaTemplate<String, byte[]>` dùng để replay phải có `StringSerializer` cho key, `ByteArraySerializer` cho value, bootstrap/ACL đúng cluster và độ bền producer phù hợp.

Một service đọc bằng `assign()` và `seek()` để chọn tọa độ **trong DLT**, không sử dụng consumer group assignment thông thường. Mã dưới đây giả định các định danh DLT đã được operator duyệt qua một luồng phê duyệt bên ngoài:

```java
@Service
public class DltReplayService {

    private static final String DLT = "orders.DLT";
    private static final String ORIGINAL = "orders";
    private static final int MAX_REPLAY_COUNT = 2;

    private final ConsumerFactory<String, byte[]> consumerFactory;
    private final KafkaTemplate<String, byte[]> kafkaTemplate;

    public DltReplayService(
            @Qualifier("dltReplayConsumerFactory")
            ConsumerFactory<String, byte[]> consumerFactory,
            KafkaTemplate<String, byte[]> kafkaTemplate) {
        this.consumerFactory = consumerFactory;
        this.kafkaTemplate = kafkaTemplate;
    }

    public void replayApproved(int dltPartition, long dltOffset)
            throws Exception {

        // Caller phải xác nhận quyền, change ticket và tọa độ đã duyệt.
        if (dltPartition < 0 || dltOffset < 0) {
            throw new IllegalArgumentException("Invalid DLT position");
        }

        TopicPartition source = new TopicPartition(DLT, dltPartition);

        try (Consumer<String, byte[]> consumer =
                     consumerFactory.createConsumer()) {

            consumer.assign(List.of(source));
            consumer.seek(source, dltOffset);

            ConsumerRecord<String, byte[]> selected = null;

            // Poll có giới hạn; nếu record bị retention/compaction loại bỏ,
            // không được tự chọn một offset khác thay thế.
            for (int pollIndex = 0;
                    pollIndex < 5 && selected == null;
                    pollIndex++) {

                ConsumerRecords<String, byte[]> records =
                        consumer.poll(Duration.ofSeconds(2));

                for (ConsumerRecord<String, byte[]> record :
                        records.records(source)) {
                    if (record.offset() == dltOffset) {
                        selected = record;
                        break;
                    }
                }
            }

            if (selected == null) {
                throw new IllegalStateException("DLT record unavailable");
            }

            Header originalTopicHeader = selected.headers().lastHeader(
                    KafkaHeaders.DLT_ORIGINAL_TOPIC);

            if (originalTopicHeader == null) {
                throw new IllegalStateException("Missing origin header");
            }

            String originalTopic = new String(
                    originalTopicHeader.value(), StandardCharsets.UTF_8);

            if (!ORIGINAL.equals(originalTopic)) {
                throw new IllegalStateException("Unexpected original topic");
            }

            int previousReplayCount = replayCount(selected.headers());
            if (previousReplayCount >= MAX_REPLAY_COUNT) {
                throw new IllegalStateException("Replay limit reached");
            }

            Headers replayHeaders = new RecordHeaders();
            // Chỉ sao chép header nghiệp vụ nằm trong allowlist.
            for (Header header : selected.headers()) {
                if (header.key().equals("event-id")
                        || header.key().equals("x-correlation-id")
                        || header.key().equals("content-type")) {
                    replayHeaders.add(header.key(), header.value());
                }
            }

            replayHeaders.add("x-replay-count", Integer.toString(
                    previousReplayCount + 1).getBytes(StandardCharsets.UTF_8));
            replayHeaders.add("x-replay-source", (
                    DLT + ":" + dltPartition + ":" + dltOffset)
                    .getBytes(StandardCharsets.UTF_8));

            ProducerRecord<String, byte[]> outgoing = new ProducerRecord<>(
                    ORIGINAL, null, selected.key(), selected.value(),
                    replayHeaders);

            // Chỉ coi thao tác republish thành công sau khi broker xác nhận.
            kafkaTemplate.send(outgoing).get(30, TimeUnit.SECONDS);

            // Ghi audit result vào hệ thống vận hành bên ngoài ví dụ này.
            // Không có commit offset DLT: job đọc theo tọa độ đã chọn.
        }
    }

    private int replayCount(Headers headers) {
        Header value = headers.lastHeader("x-replay-count");
        if (value == null) {
            return 0;
        }
        try {
            int count = Integer.parseInt(
                    new String(value.value(), StandardCharsets.UTF_8));
            if (count < 0) {
                throw new IllegalArgumentException("Negative replay count");
            }
            return count;
        }
        catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid replay count", ex);
        }
    }
}
```

Đây là ví dụ về **bước đọc và publish**, không phải một hệ thống phê duyệt hoàn chỉnh. Endpoint hoặc job gọi `replayApproved()` phải có xác thực, quyền hạn, approval record, giới hạn tổng số record và audit trail. Không cung cấp method này trực tiếp qua một API công khai không được bảo vệ. Không dùng cùng một `KafkaConsumer` giữa nhiều thread; mỗi job hoặc worker phải sở hữu consumer riêng.

Ví dụ không chỉ định partition đích khi tạo `ProducerRecord`. Kafka producer có thể chọn partition theo key và partitioner đang cấu hình. Điều này **không đảm bảo** record được replay vào cùng partition ban đầu. Nếu cần giữ partition gốc, phải đọc header partition nguồn, xác minh partition đích còn hợp lệ và quyết định rõ tác động lên thứ tự xử lý. Dù dùng partition nào, offset được cấp ở topic gốc khi replay vẫn là **offset mới**.

Các import class cần dùng bao gồm Kafka client (`Consumer`, `ConsumerRecord`, `ConsumerRecords`, `ProducerRecord`, `TopicPartition`, `Header`, `Headers`, `RecordHeaders`, `ConsumerConfig`, deserializers), Spring Kafka (`ConsumerFactory`, `DefaultKafkaConsumerFactory`, `KafkaTemplate`, `KafkaHeaders`), Java (`Duration`, `TimeUnit`, `StandardCharsets`, collections) và annotation Spring. Nếu ứng dụng dùng schema registry hoặc serializer đặc biệt, cần thay đổi cấu hình đọc/ghi tương ứng thay vì mặc định payload luôn là JSON thuần.

## 7. Nếu replay cả một batch hoặc backlog lớn

Job replay một record là nền tảng cho replay một danh sách đã duyệt. Với backlog lớn, không nên mỗi record lại mở consumer mới; dùng consumer chuyên dụng đọc tuần tự các khoảng đã phê duyệt, có checkpoint và khả năng resume.

Thiết kế batch replay cần xử lý:

- **Scope:** topic DLT, partition, khoảng offset hoặc tập event ID; điều kiện về exception class/schema.
- **Checkpoint:** tiến độ job riêng, không đánh đồng với committed offset của consumer group nghiệp vụ.
- **Pacing:** tốc độ record/giây, số request đang chờ, giới hạn theo partition và downstream.
- **Selection:** record không đủ điều kiện phải được ghi nhận là skipped với lý do, không âm thầm bỏ qua.
- **Failure:** nếu publish thất bại, dừng hoặc retry có backoff; không đánh dấu thành công trước broker ack.
- **Resume:** chạy lại sau crash từ checkpoint an toàn; chấp nhận khả năng duplicate và dùng idempotency.
- **Audit:** người phê duyệt, change ID, số lượng được duyệt, thành công/thất bại/bỏ qua, timestamp và mapping offset mới.

Một checkpoint đáng tin cậy nên gắn với tọa độ DLT đã thực sự publish thành công. Nếu checkpoint được lưu sau broker ack, crash giữa hai thao tác có thể khiến record được publish lần nữa khi resume. Nếu checkpoint được lưu trước broker ack, có nguy cơ đánh dấu xong dù broker chưa nhận record. Với hai hệ thống lưu trữ khác nhau, không có atomicity mặc định; cần thiết kế cho at-least-once và deduplication.

## 8. Mẫu listener replay có điều khiển

Nếu tổ chức thường xuyên có backlog lớn, có thể tạo một listener chuyên dụng đọc DLT nhưng **không tự khởi động**. Cần triển khai approval/filter/checkpoint trước khi bật, vì listener sẽ thấy record theo tiến độ consumer group của chính nó, không tự biết những record nào đã được phê duyệt.

```java
@KafkaListener(
        id = "ordersDltReplayListener",
        topics = "orders.DLT",
        groupId = "orders-dlt-replay-operator",
        containerFactory = "dltReplayListenerContainerFactory",
        autoStartup = "false")
public void replayDltRecord(
        ConsumerRecord<String, byte[]> record,
        Acknowledgment acknowledgment) throws Exception {

    // Kiểm tra approval/eligibility và replay count trước khi publish.
    // Republish xong phải chờ broker ack rồi mới acknowledge DLT.
    // Trường hợp không được duyệt: không được tự ack để bỏ qua im lặng.
}
```

Đây là **khung listener, không phải một implementation có thể bật chạy ngay**. Factory cần ack mode phù hợp, chẳng hạn `MANUAL_IMMEDIATE`, và việc publish phải có kiểm tra kết quả. Khi bật listener, cần giới hạn partition hoặc dải offset nếu muốn replay có chọn lọc. `autoStartup=false` chỉ ngăn container tự start lúc application startup; nó không tự tạo approval workflow, pause/resume, offset boundary hay replay cap.

Với `KafkaListenerEndpointRegistry`, ứng dụng có thể lấy container theo listener ID để `start()` hoặc `stop()` qua một thao tác quản trị có xác thực. Dừng container không hoàn tác những record đã publish. Khi dùng consumer group replay chuyên dụng, committed offset DLT của group đó chỉ biểu thị tiến độ đọc DLT, không chứng minh record được consumer nghiệp vụ xử lý thành công sau replay.

## 9. Không tạo vòng lặp replay vô hạn

Một record có thể đi từ DLT về topic gốc rồi thất bại lần nữa. Nếu tự động replay DLT không giới hạn, record có thể luân chuyển vô hạn:

```text
orders -> orders.DLT -> orders -> orders.DLT -> ...
```

Vòng lặp này gây tăng số record trên broker, consumer lag, phí lưu trữ, log và DLT backlog. Dù producer idempotent, các lần publish với record mới vẫn có thể được Kafka chấp nhận là **những bản ghi mới hợp lệ**; idempotent producer không ngăn business replay loop.

Cần áp dụng nhiều lớp bảo vệ:

1. **Chỉ replay khi nguyên nhân lỗi đã được khắc phục**, có bằng chứng từ kiểm thử một tập nhỏ.
2. **Giới hạn số lần replay:** dùng header hoặc metadata bền vững như `x-replay-count`; tránh reset count khi record quay lại DLT.
3. **Dùng khóa idempotency nghiệp vụ:** event ID ổn định, unique constraint hoặc inbox table để không tạo side effect trùng.
4. **Có quarantine cuối cùng:** record vượt ngưỡng replay phải dừng ở vùng xử lý thủ công thay vì lại được gửi vào topic gốc.
5. **Có rate limit và circuit breaker:** tạm dừng job nếu tỷ lệ lỗi ở topic gốc/DLT tăng trở lại.
6. **Theo dõi provenance:** lưu tọa độ DLT và lần replay để phân biệt record gốc với bản ghi phát lại.

Header `x-replay-count` trong ví dụ chỉ hữu ích nếu pipeline giữ header đó khi record bị gửi lại vào DLT. Nếu serializer, mapper hoặc recoverer làm mất header, số lần replay có thể bị đếm lại từ 0. Với workflow quan trọng, có thể lưu replay history trong một datastore quản trị theo stable event ID để có giới hạn bền vững qua nhiều lần publish.

## 10. Idempotency: replay không đồng nghĩa đúng một lần xử lý

Ví dụ record `PaymentCaptured` đã ghi vào database nhưng listener bị crash trước khi commit offset. Sau đó record bị retry rồi đưa vào DLT do lỗi ở một bước downstream. Nếu replay vô điều kiện, cập nhật số dư hoặc tạo hóa đơn có thể thực hiện thêm lần nữa.

Thiết kế consumer cần xử lý trùng dựa trên ID nghiệp vụ:

```text
event-id: evt-9b62
       |
       v
BEGIN DB TRANSACTION
       |
       v
INSERT INTO inbox(event_id)
       |
       +-- unique constraint conflict --> đã xử lý, kết thúc an toàn
       |
       v
Thực hiện cập nhật nghiệp vụ
       |
       v
COMMIT DB TRANSACTION
```

Việc ghi event ID vào inbox phải nằm trong **cùng transaction database** với side effect được bảo vệ. Chỉ ghi vào một cache không bền vững có thể không đủ. Nếu một sự kiện có nhiều side effect ở những hệ thống ngoài database, cần thiết kế idempotency riêng cho từng hệ thống hoặc orchestration phù hợp.

Ngay cả job replay cũng phải tránh phát lại ngoài ý muốn. Dùng replay job ID và bộ khóa `(DLT topic, partition, offset)` trong audit/checkpoint để xác định record đã được yêu cầu replay. Tuy nhiên, nếu publish Kafka và ghi audit nằm ở hai transaction độc lập, vẫn tồn tại khoảng crash. Vì vậy, người vận hành cần hiểu rằng **at-least-once republish** là cách giả định an toàn nếu không thiết kế thêm giao dịch/outbox cụ thể.

## 11. Kafka transaction có giải quyết hết không?

Kafka transaction có thể giúp ghi nhiều record và commit offset của một consumer group một cách nguyên tử **trong phạm vi Kafka**, khi producer, consumer và transaction manager được cấu hình phù hợp. Một replay consumer sử dụng transaction có thể publish record về topic gốc và commit offset DLT của replay group trong cùng Kafka transaction.

Tuy vậy, transaction này không tự bao gồm kết quả xử lý của listener nghiệp vụ trên topic gốc, database, HTTP API hay một hệ thống lưu audit bên ngoài. Consumer downstream vẫn cần idempotency và chính sách failure handling.

Với job đọc tọa độ DLT thủ công bằng `assign()` như ví dụ trên, không có group offset commit gắn với job; muốn dùng Kafka transaction phải thiết kế riêng một luồng consume-transform-produce có group assignment, offset được chuyển vào transaction và producer transactional phù hợp. Không thêm `@Transactional` rồi giả định mọi thao tác Kafka và database tự động nguyên tử.

## 12. Header, schema, key và partition khi replay

Khi đưa dữ liệu từ DLT trở lại topic gốc, cần quyết định **giữ nguyên cái gì** và **loại bỏ cái gì**:

| Thành phần | Hướng xử lý thường phù hợp |
|---|---|
| Business event ID | Giữ nguyên để consumer deduplicate |
| Kafka record key | Giữ nếu cần cùng partition routing theo key |
| Payload | Giữ raw bytes nếu dữ liệu hợp lệ sau khi sửa consumer; nếu cần chuyển đổi, phải version/audit rõ |
| Correlation ID | Giữ để liên kết trace gốc và replay |
| Exception stack trace trong DLT header | Không tự động copy lại topic chính nếu không cần |
| Original topic/partition/offset | Lưu trong audit hoặc provenance header có kiểm soát |
| Replay attempt/count | Tăng theo chính sách và giữ qua các lần recovery |
| Timestamp Kafka | Replay có timestamp ghi mới; không giả định timestamp gốc được bảo toàn |
| Partition gốc | Chỉ tái sử dụng khi phù hợp với partition count, key distribution và yêu cầu ordering |

Mã minh họa dùng allowlist header nghiệp vụ thay vì sao chép toàn bộ header DLT. Việc giữ nhiều header lỗi từ các vòng retry/replay có thể làm header phình to và rò rỉ stack trace hoặc thông tin nhạy cảm sang topic chính.

**Cẩn trọng với deserialization failure:** một record DLT sinh ra từ `ErrorHandlingDeserializer` có thể chứa raw bytes chưa deserialize thành công, trong khi DLT sinh ra từ exception ở listener có thể chứa value đã được serializer mã hóa lại theo cấu hình `KafkaTemplate`. Khi replay cần kiểm tra payload hiện có thực sự tương thích với consumer topic gốc. Không chỉ nhìn Java type của object DLT mà suy ra bytes an toàn để publish.

Nếu payload cần chỉnh sửa, ưu tiên tạo một event mới với contract/schema hợp lệ và lưu mapping từ event mới về record DLT cũ. Không âm thầm sửa nội dung đã phát hành mà không lưu dấu vết, đặc biệt với sự kiện tài chính hoặc kiểm toán.

## 13. Ordering và tác động lên luồng nghiệp vụ

Replay từ DLT về topic gốc luôn thêm **một record mới vào cuối log của partition đích**. Nó không chèn record trở lại vị trí lịch sử trước các record đã được xử lý.

Ví dụ:

```text
orders partition 2:
  offset 530: OrderCreated  ---> lỗi, sang DLT
  offset 531: OrderPaid     ---> xử lý ở topic chính
  offset 532: OrderShipped  ---> xử lý ở topic chính
  ...
  offset 940: replay OrderCreated
```

Nếu `OrderPaid` hoặc `OrderShipped` yêu cầu `OrderCreated` được áp dụng trước, replay cuối log không khôi phục được thứ tự nghiệp vụ ban đầu. Hệ thống cần chọn một phương án rõ ràng: xử lý event theo state machine có version kiểm tra, giữ bản ghi chờ phụ thuộc, thực hiện bù trừ, hoặc dùng một workflow reprocessing riêng có bảo đảm ordering cần thiết.

Giữ Kafka record key giúp các sự kiện cùng key có thể được partitioner đưa vào cùng partition, nhưng **không làm cho replay lấy lại offset cũ** và không loại bỏ vấn đề event cũ đến sau event mới. Với producer configuration khác nhau hoặc partition count thay đổi, cùng key thậm chí có thể rơi vào partition khác. Cần xác minh trên môi trường thực tế.

## 14. Replay có kiểm soát theo canary và tốc độ

Với DLT backlog lớn, một đợt replay ồ ạt có thể làm consumer chính và downstream quá tải, tạo thêm exception và đẩy nhiều record quay lại DLT. Nên thực hiện theo giai đoạn:

1. Chọn một số record đại diện theo exception class, schema version và thời điểm lỗi.
2. Replay vào môi trường thử nghiệm hoặc một luồng canary tương thích nếu có thể.
3. Replay một tập nhỏ trên production, theo dõi side effect và DLT re-entry.
4. Tăng tốc dần trong giới hạn throughput của consumer/database/API downstream.
5. Tự động tạm dừng khi error rate, lag, latency hoặc DLT re-entry vượt ngưỡng.
6. Kết thúc đợt replay, đối soát danh sách đã duyệt với số lượng publish thành công và kết quả nghiệp vụ.

Điểm quan trọng là không lấy tốc độ producer gửi thành công làm thước đo duy nhất. Có thể producer gửi 10.000 record/giây nhưng consumer nghiệp vụ chỉ xử lý 1.000 record/giây và DLT tiếp tục tăng. Cần phối hợp rate limit với lag và năng lực thực tế của downstream.

## 15. Quan sát và audit replay

Một dashboard vận hành nên tách ba lớp kết quả:

- **Replay requested/approved:** số record được phê duyệt hoặc đưa vào kế hoạch.
- **Replay published:** số record được broker xác nhận đã ghi về topic gốc.
- **Business reprocessed:** số record thực sự được listener nghiệp vụ hoàn tất sau replay.

Các chỉ số bổ sung gồm lỗi publish, throughput replay, latency từ DLT tới topic gốc, số record replay quay lại DLT, số record vượt replay limit, consumer lag topic gốc và tình trạng downstream. Ghi log/audit của mỗi record với DLT topic/partition/offset, original topic/partition/offset, event ID, replay job ID, operator/change ID, thời điểm publish, result topic/partition/offset mới và kết quả đối soát khi có.

Không dùng event ID hay offset riêng lẻ làm metric label vì cardinality cao. Giữ chúng trong audit log hoặc trace có kiểm soát. Hạn chế hiển thị payload hoặc stack trace nhạy cảm trên dashboard.

Một bảng audit có thể có cấu trúc:

| Trường | Ý nghĩa |
|---|---|
| `job_id` | Đợt replay và người phê duyệt |
| `dlt_topic`, `dlt_partition`, `dlt_offset` | Vị trí DLT được chọn |
| `event_id` | Khóa nghiệp vụ ổn định |
| `target_topic` | Topic được publish lại |
| `replayed_partition`, `replayed_offset` | Tọa độ broker trả về sau republish |
| `status` | Approved, published, failed, skipped, verified |
| `reason` | Lý do replay hoặc lý do từ chối |

Để kết luận record đã được xử lý nghiệp vụ, cần đối soát với transaction/inbox database, event kết quả hoặc metric có ý nghĩa nghiệp vụ, không chỉ với producer acknowledgment.

## 16. Các lỗi vận hành thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Replay xong record lại vào DLT | Nguyên nhân lỗi chưa được sửa hoặc payload vẫn không tương thích | Dừng replay, kiểm tra exception mới và test một record |
| Một event tạo side effect hai lần | Consumer không idempotent hoặc job publish lại nhiều lần sau crash | Giữ event ID, dùng inbox/unique constraint, audit replay requests |
| Job replay nhầm topic | Tin tưởng header không kiểm chứng hoặc nhầm môi trường | Whitelist topic đích, kiểm tra cluster, ACL và approval |
| Không tìm thấy record tại DLT offset | Retention/compaction đã loại record hoặc chọn sai partition/offset | Xác minh tọa độ, không tự lấy record kế tiếp để thay thế |
| Replay phát lại sai định dạng | DLT value đã được serializer khác mã hóa; schema chưa được sửa | Xem raw bytes/schema và cấu hình serializer/deserializer |
| Replay làm sai thứ tự xử lý | Record cũ được append vào cuối topic | Dùng state version, bù trừ hoặc workflow có kiểm soát ordering |
| DLT tăng trong lúc replay | Replay loop, throughput quá cao hoặc consumer vẫn lỗi | Rate limit, circuit breaker, replay cap, dừng đợt |
| Publish được nhưng không thấy kết quả nghiệp vụ | Consumer gốc lag, lỗi tiếp, hoặc business workflow không hoàn tất | Theo dõi consumer group, kết quả nghiệp vụ và DLT re-entry |
| DLT replay listener bỏ qua record không được duyệt | Listener auto ack/commit trước khi filter có trạng thái bền vững | Dùng job chọn theo tọa độ hoặc chính sách checkpoint/skip có audit |
| Job restart gây replay lặp | Checkpoint và Kafka publish không nguyên tử | Thiết kế at-least-once, deduplication và resume có kiểm soát |

Khi điều tra, bắt đầu bằng tọa độ DLT và event ID, dựng lại đường đi của record qua topic gốc, retry topic, DLT và replay. Xác nhận chính xác bản ghi nào được publish sau mỗi đợt thay vì chỉ dựa vào số lượng tổng hợp.

## 17. Kiểm thử luồng replay

Trước khi đưa chức năng replay vào production, nên kiểm thử ít nhất các kịch bản:

1. **Record hợp lệ sau sửa lỗi:** đưa vào DLT, khắc phục consumer, replay và xác nhận xử lý nghiệp vụ thành công.
2. **Lỗi vẫn tồn tại:** replay một record độc hại, xác nhận replay cap/quarantine hoặc circuit breaker ngăn vòng lặp.
3. **Duplicate request:** cùng DLT partition/offset được yêu cầu hai lần; xác nhận audit và nghiệp vụ chống side effect trùng.
4. **Publish failure:** mất quyền ghi hoặc broker timeout; job không ghi trạng thái published thành công trước broker ack.
5. **Crash sau publish:** dừng tiến trình ngay sau broker nhận record nhưng trước khi lưu checkpoint; xác nhận resume không làm sai nghiệp vụ.
6. **Thiếu original topic header:** job từ chối hoặc chuyển xử lý thủ công; không đoán topic đích tùy tiện.
7. **Payload lỗi deserialization:** bảo đảm raw bytes/schema được xử lý đúng hoặc bị chặn an toàn.
8. **Ordering conflict:** replay event cũ sau event mới và xác nhận state version/business rule bảo vệ kết quả.
9. **DLT retention:** offset đã mất không được thay thế âm thầm bằng record kế tiếp.
10. **Backlog lớn:** giới hạn tốc độ, quan sát lag/DLT re-entry và khả năng pause/resume hoạt động.

Các bài kiểm thử nên xác nhận cả thông tin Kafka (key, headers, partition, offset) và trạng thái nghiệp vụ. Với transactional hay outbox replay, cần bổ sung tình huống transaction abort và retry job.

## 18. Runbook replay an toàn

Một quy trình dùng trong ca trực vận hành có thể theo trình tự sau:

1. **Phát hiện:** cảnh báo DLT tăng hoặc sự cố được báo từ downstream.
2. **Phân loại:** nhóm record theo exception, producer version, schema và hệ thống bị ảnh hưởng.
3. **Khắc phục:** sửa code, dữ liệu, dependency, ACL hoặc schema; kiểm chứng bằng một record đại diện.
4. **Phê duyệt:** chốt phạm vi DLT topic/partition/offset hoặc event ID, người chịu trách nhiệm và giới hạn đợt replay.
5. **Chuẩn bị:** kiểm tra topic đích, ACL, serializer, retention, idempotency, ordering và năng lực downstream.
6. **Canary:** replay một số record, theo dõi DLT re-entry và kết quả nghiệp vụ.
7. **Thực thi:** chạy batch với rate limit và checkpoint, không mở rộng phạm vi ngoài danh sách đã duyệt.
8. **Giám sát:** theo dõi published count, business processed count, lag, exception rate và replay loop.
9. **Đối soát:** kết luận bao nhiêu record thành công, bao nhiêu vẫn lỗi hoặc cần xử lý thủ công.
10. **Đóng sự cố:** lưu job ID, mapping offset mới, root cause, timeline và thay đổi phòng ngừa.

Nếu cần dừng giữa chừng, giữ lại trạng thái job và danh sách record đã publish. Không reset offset consumer chính để “làm lại tất cả” trừ khi có một kế hoạch backfill độc lập và được phê duyệt.

## 19. Nguyên tắc cốt lõi khi replay DLT về topic gốc

Replay chỉ nên được thực hiện khi có **một lý do nghiệp vụ rõ ràng** và có bằng chứng rằng record sẽ được xử lý tốt hơn so với lần thất bại trước. Dùng DLT metadata để chọn đúng record, whitelist topic đích, giữ stable event ID và metadata provenance, giới hạn số lần phát lại, theo dõi kết quả đến tận side effect nghiệp vụ.

Về tính nhất quán, hãy mặc định rằng record có thể được publish hoặc xử lý nhiều hơn một lần trong các tình huống crash, retry và rebalance; idempotency là yêu cầu nền tảng. Về vận hành, hãy xem DLT replay như một **quy trình khôi phục dữ liệu có kiểm soát**, không phải listener tự động đẩy mọi record lỗi trở lại topic chính. Khi kết hợp approval, rate limit, audit, kiểm thử và đối soát, Spring Kafka có thể khôi phục event bị cách ly mà vẫn hạn chế duplicate, replay loop và ảnh hưởng tới consumer đang chạy.
