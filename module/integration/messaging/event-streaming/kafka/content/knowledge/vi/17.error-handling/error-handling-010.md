# Quy trình sửa dữ liệu và đưa bản ghi lỗi trở lại luồng

Trong hệ thống event streaming, không phải record nào xử lý thất bại cũng cần bỏ đi hoặc gửi lại ngay. Có lỗi chỉ tồn tại trong vài giây như timeout hoặc dịch vụ downstream tạm ngừng; có lỗi do dữ liệu không hợp lệ; có lỗi do code hoặc schema chưa tương thích. Mỗi nhóm cần một cách phục hồi khác nhau.

Quy trình xử lý tốt phải giữ được dấu vết của record gốc, giới hạn retry, tránh lặp vô hạn, sửa đúng nguyên nhân và kiểm soát việc đưa record trở lại luồng. Nếu chỉ chuyển record sang Dead Letter Topic (DLT) rồi tự động phát lại, hệ thống có thể lặp lại cùng lỗi, tạo side effect trùng hoặc làm sai thứ tự event.

Bài học này xây dựng quy trình từ lúc phát hiện lỗi đến khi sửa dữ liệu, redrive record và xác nhận kết quả trong production.

## 1. Phân biệt retry, repair và redrive

Ba thao tác thường đi cùng nhau nhưng có mục đích khác nhau:

- **Retry:** thử xử lý lại cùng một record sau khi một lỗi tạm thời có thể đã hết.
- **Repair:** sửa nguyên nhân khiến record không thể xử lý, có thể là code, cấu hình, dữ liệu tham chiếu hoặc nội dung event.
- **Redrive:** đưa record đã được cách ly hoặc sửa trở lại một luồng xử lý để thực hiện lại.

Ví dụ consumer nhận event OrderCreated nhưng database đang tạm thời không kết nối được:

1. Consumer retry vài lần với backoff.
2. Nếu database phục hồi, record được xử lý và offset được xác nhận.
3. Nếu hết retry, record được chuyển sang DLT.
4. Đội vận hành xác nhận database đã ổn định.
5. Record được redrive để consumer xử lý lại.

Trường hợp khác: record chứa currency=VNDX, trong khi hệ thống chỉ hỗ trợ VND, USD, EUR. Retry không sửa được dữ liệu. Cần xác minh nguồn phát, sửa payload hoặc phát event điều chỉnh, rồi mới redrive.

| Thao tác | Câu hỏi cần trả lời | Mục tiêu |
|---|---|---|
| Retry | Lỗi có thể tự hết sau một khoảng thời gian không? | Xử lý lại cùng record |
| Repair | Nguyên nhân gốc là gì và cần sửa ở đâu? | Loại bỏ điều kiện gây lỗi |
| Redrive | Record sẽ quay lại luồng nào và được nhận diện ra sao? | Phục hồi có kiểm soát |

## 2. Phân loại lỗi trước khi retry

Không nên áp dụng cùng một retry policy cho mọi exception. Bước đầu tiên là phân loại lỗi theo khả năng phục hồi.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Network timeout, connection reset, HTTP 503 | Retry có giới hạn và backoff |
| Quá tải hoặc throttling | HTTP 429, database connection pool exhausted | Backoff, giới hạn concurrency, tôn trọng Retry-After nếu có |
| Lỗi dữ liệu | Thiếu field bắt buộc, enum không hợp lệ, sai định dạng | Không retry mù; cách ly và repair dữ liệu |
| Lỗi tương thích | Consumer chưa hỗ trợ schema version mới | Nâng cấp code/schema rồi replay |
| Lỗi cấu hình | Sai endpoint, credential hết hạn, ACL thiếu quyền | Sửa cấu hình/quyền; chỉ retry sau khi xác nhận nguyên nhân đã hết |
| Lỗi nghiệp vụ | Đơn hàng đã đóng, trạng thái chuyển không hợp lệ | Xác minh quy tắc; có thể cần event bù hoặc xử lý thủ công |
| Record gây lỗi lặp | Poison pill, payload luôn làm consumer crash | Cách ly vào DLT và điều tra riêng |

### 2.1. Phân biệt lỗi transient và permanent

Lỗi transient có khả năng hết nếu thử lại sau một khoảng thời gian. Ví dụ database failover trong vài giây hoặc downstream trả HTTP 503 khi deploy.

Lỗi permanent không tự biến mất khi thử lại. Ví dụ JSON sai cú pháp, thiếu orderId, giá trị tiền tệ không được hỗ trợ hoặc event vi phạm invariant nghiệp vụ.

Một số lỗi nằm giữa hai nhóm. HTTP 401 có thể là credential sai hoặc token tạm hết hạn; lỗi schema registry có thể do network hoặc do schema không tồn tại. Cần dựa vào exception cụ thể và trạng thái hệ thống thay vì chỉ nhìn class exception chung.

### 2.2. Poison pill

Poison pill là record luôn làm consumer thất bại khi đọc hoặc xử lý. Ví dụ:

- Payload quá lớn hoặc không thể deserialize.
- Field có kiểu dữ liệu không tương thích.
- Một giá trị làm code ném exception ở mọi lần xử lý.
- Event phá vỡ invariant khiến database constraint liên tục từ chối.

Nếu consumer retry vô hạn tại cùng record, partition có thể không tiến lên và các record sau bị chặn. Cần giới hạn retry, chuyển record lỗi sang DLT hoặc tạm dừng partition để sửa nguyên nhân.

## 3. Thiết kế retry có giới hạn

Retry giúp chịu lỗi tạm thời, nhưng mỗi lần thử lại đều tiêu tốn tài nguyên. Retry vô hạn có thể khuếch đại sự cố: database đang quá tải thì nhiều consumer càng gửi thêm request, khiến database càng chậm và retry càng nhiều.

Một retry policy nên xác định:

- Số lần thử tối đa.
- Khoảng chờ giữa các lần thử.
- Backoff tăng theo cấp số nhân hay cố định.
- Jitter để phân tán request đồng thời.
- Exception nào được retry.
- Thời gian xử lý tối đa của một record.
- Hành động khi hết retry.

### 3.1. Fixed backoff

Fixed backoff chờ cùng một khoảng thời gian giữa các lần retry.

Ví dụ:

| Lần thử | Thời điểm tương đối |
|---:|---:|
| Lần đầu | 0 giây |
| Retry 1 | Sau 1 giây |
| Retry 2 | Sau 1 giây tiếp theo |
| Retry 3 | Sau 1 giây tiếp theo |
| Hết retry | Chuyển DLT hoặc dừng xử lý theo policy |

Fixed backoff dễ hiểu và phù hợp với lỗi ngắn, có thời gian phục hồi tương đối ổn định.

### 3.2. Exponential backoff và jitter

Exponential backoff tăng thời gian chờ theo từng lần thử:

\[
d_n = \min(d_{\max}, d_0 \times m^{n-1})
\]

Trong đó:

- \(d_0\): thời gian chờ ban đầu.
- \(m\): hệ số nhân, thường lớn hơn 1.
- \(d_{\max}\): thời gian chờ tối đa.
- \(n\): số thứ tự lần retry.

Ví dụ với \(d_0=1s\), \(m=2\), \(d_{\max}=30s\):

| Lần retry | Thời gian chờ |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| 4 | 8 giây |
| 5 | 16 giây |
| 6 | 30 giây |

Jitter thêm một độ lệch ngẫu nhiên vào thời gian chờ. Nếu hàng nghìn consumer cùng retry đúng 30 giây sau một sự cố, chúng có thể đồng loạt đánh vào downstream khi dịch vụ vừa phục hồi. Jitter giúp phân tán tải.

### 3.3. Retry budget

Đừng chỉ giới hạn số lần thử; hãy giới hạn cả tổng thời gian retry. Ví dụ record có thể được retry tối đa 5 lần trong tối đa 2 phút. Sau thời hạn này, chuyển sang DLT hoặc quy trình can thiệp.

Retry budget giúp đáp ứng SLA và tránh giữ một record quá lâu trong luồng chính.

## 4. Blocking retry và retry topic

Kafka consumer có hai hướng triển khai retry phổ biến.

### 4.1. Blocking retry tại consumer

Consumer giữ record hiện tại và thử lại trong cùng luồng xử lý. Trong thời gian retry, partition có thể không tiến đến record sau.

~~~mermaid
flowchart TD
    A["Consumer nhận record"] --> B["Xử lý nghiệp vụ"]
    B --> C{"Thành công?"}
    C -->|Có| D["Commit next offset"]
    C -->|Không| E{"Còn retry budget?"}
    E -->|Có| F["Backoff"]
    F --> B
    E -->|Không| G["Publish DLT hoặc dừng"]
    G --> H["Chỉ tiến offset khi recovery hợp lệ"]
~~~

Ưu điểm:

- Giữ thứ tự xử lý trong partition dễ hơn.
- Không cần thêm retry topic.
- Logic và quan sát tương đối đơn giản.
- Phù hợp với lỗi ngắn và yêu cầu ordering nghiêm ngặt.

Đánh đổi:

- Record lỗi có thể chặn các record sau trong cùng partition.
- Consumer thread bị chiếm trong thời gian backoff.
- Nếu xử lý lâu, có thể vượt max.poll.interval.ms và gây rebalance.
- Không phù hợp với retry delay dài nhiều phút hoặc nhiều giờ.

### 4.2. Retry topic

Với retry topic, record lỗi được publish sang một topic trung gian có thời gian chờ. Consumer chính có thể tiếp tục xử lý các record sau, trong khi retry consumer nhận record khi đến hạn.

Ví dụ:

~~~text
orders
   |
   | xử lý thất bại
   v
orders-retry-1s
   |
   | vẫn thất bại
   v
orders-retry-10s
   |
   | vẫn thất bại
   v
orders-retry-1m
   |
   | hết retry
   v
orders.DLT
~~~

Ưu điểm:

- Không phải giữ consumer chính chờ lâu.
- Có thể biểu diễn các khoảng retry dài.
- Dễ quan sát backlog theo từng mức retry.
- Cho phép phân bổ tài nguyên riêng cho retry workload.

Đánh đổi:

- Tăng số topic, partition, consumer và chi phí vận hành.
- Thứ tự giữa record ban đầu và record retry có thể thay đổi.
- Cần giữ metadata để truy nguyên record gốc.
- Cần kiểm soát việc publish retry và commit offset nguồn.
- Record có thể bị retry topic chuyển qua lại nếu policy sai.

### 4.3. Retry topic có thể làm thay đổi ordering

Giả sử cùng partition có event:

| Offset nguồn | Event | Kết quả |
|---:|---|---|
| 10 | OrderCreated | Thất bại, chuyển retry topic |
| 11 | OrderPaid | Thành công ở topic chính |

Consumer xử lý event offset 11 trước khi event offset 10 quay lại từ retry topic. Nếu nghiệp vụ yêu cầu OrderCreated phải hoàn tất trước OrderPaid, trạng thái có thể bị đảo.

Vì vậy:

- Dùng blocking retry khi phải giữ thứ tự tuyệt đối trong partition.
- Dùng retry topic khi chấp nhận record sau tiếp tục và nghiệp vụ có thể xử lý out-of-order.
- Với ordering theo entity, thêm sequence/version của entity và kiểm tra trước khi áp dụng event.
- Có thể giữ riêng các event của cùng entity cho đến khi event trước được phục hồi.

Retry topic không tự bảo đảm thứ tự chỉ vì record giữ nguyên Kafka key.

## 5. Dead Letter Topic dùng để làm gì?

Dead Letter Topic (DLT) chứa record đã hết retry hoặc được xác định không thể xử lý tự động. DLT là vùng cách ly để điều tra và phục hồi.

Ví dụ tên:

- Topic nguồn: orders
- DLT: orders.DLT
- Retry topic: orders-retry-1m

Một record trong DLT nên giữ:

- Payload gốc hoặc payload lỗi có thể đọc được.
- Key và các header nghiệp vụ cần thiết.
- Topic, partition và offset gốc.
- Timestamp gốc nếu có.
- Exception class, message và stack trace phù hợp.
- Số lần thử, thời điểm retry cuối.
- Consumer group và service đã xử lý.
- Correlation ID, event ID và trace ID.

Không chỉ lưu exception message trong log rồi bỏ payload. Khi cần sửa, đội vận hành phải truy được chính xác record gây lỗi.

### 5.1. Partition của DLT

Với DeadLetterPublishingRecoverer, resolver mặc định thường định tuyến record đến topic có suffix .DLT và giữ partition nguồn. Nếu dùng cách định tuyến này, DLT cần có partition tương ứng với partition nguồn.

Nếu topic nguồn có 12 partition mà DLT chỉ có 3 partition, việc publish vào partition số 8 không thể thành công nếu resolver cố giữ partition đó. Hãy tạo DLT có số partition phù hợp hoặc cấu hình resolver để chọn partition đích hợp lệ.

### 5.2. DLT không phải nơi lưu vô thời hạn

Đặt retention theo quy trình xử lý sự cố và yêu cầu audit. Cần có:

- Chủ sở hữu DLT và người chịu trách nhiệm triage.
- SLA xử lý DLT.
- Cảnh báo khi DLT tăng nhanh hoặc record quá tuổi.
- Quy định retention và backup nếu cần.
- ACL hạn chế quyền đọc/ghi.
- Mã hóa và chính sách che dữ liệu nhạy cảm.

DLT có thể chứa payload lỗi, thông tin cá nhân hoặc dữ liệu nhạy cảm. Cần áp dụng cùng hoặc chặt hơn chính sách bảo vệ dữ liệu của topic nguồn.

## 6. Spring Kafka: DefaultErrorHandler và DLT

Spring Kafka cung cấp DefaultErrorHandler để retry record và gọi recoverer khi hết retry. DeadLetterPublishingRecoverer là một recoverer phổ biến để publish record sang DLT.

Ví dụ cấu hình:

~~~java
@Bean
DefaultErrorHandler kafkaErrorHandler(
        DeadLetterPublishingRecoverer recoverer) {

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
    );

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class
    );

    return handler;
}
~~~

Trong ví dụ, handler chờ 1 giây giữa các lần retry và cho phép 3 lần retry sau lần xử lý ban đầu. Khi hết retry, recoverer publish record sang DLT theo resolver đã cấu hình.

Các điểm cần kiểm tra:

- Exception nào được retry và exception nào không.
- DLT có tồn tại và có partition phù hợp.
- Producer dùng để publish DLT có serializer xử lý được cả payload bình thường lẫn payload lỗi.
- Lỗi khi publish DLT có được báo lại để record nguồn không bị coi là recovered giả.
- Offset chỉ được tiến qua record khi recovery đã thành công theo policy.
- Metric và log ghi rõ lần retry, DLT publish success/failure.

### 6.1. Lỗi deserialize trước khi listener được gọi

Nếu JSON hoặc schema không thể deserialize, listener chưa được gọi. Dùng ErrorHandlingDeserializer để đưa lỗi deserialize vào cơ chế xử lý lỗi của Spring Kafka.

Ví dụ cấu hình consumer:

~~~java
props.put(
    ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
    ErrorHandlingDeserializer.class
);

props.put(
    ErrorHandlingDeserializer.VALUE_DESERIALIZER_CLASS,
    JsonDeserializer.class.getName()
);
~~~

Cấu hình delegate JsonDeserializer thêm trusted package/type mapping theo ứng dụng. Không mở trusted packages rộng tùy tiện nếu payload đến từ nguồn không tin cậy.

Nếu DLT chứa record mà value không thể deserialize thành object, publisher phải có serializer phù hợp với dạng byte[]/raw payload. Kiểm thử riêng trường hợp deserialization failure; không giả định DLT publisher có thể serialize mọi loại value chỉ với một JSON serializer.

## 7. Spring Kafka: RetryableTopic và DltHandler

Với retry delay dài hoặc muốn tách retry khỏi consumer chính, Spring Kafka hỗ trợ non-blocking retry topics qua @RetryableTopic.

Ví dụ:

~~~java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 30_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "orders",
    groupId = "orders-service"
)
public void consume(OrderEvent event) {
    orderService.process(event);
}

@DltHandler
public void handleDlt(
        OrderEvent event,
        @Header(KafkaHeaders.RECEIVED_TOPIC) String topic) {

    log.error("Order event moved to DLT topic={}", topic);
    dltAuditService.record(event);
}
~~~

Trong ví dụ, attempts="4" là tổng số lần delivery tính cả lần đầu; backoff tăng dần đến tối đa 30 giây. DLT handler nên lưu trạng thái và phát cảnh báo, không tự động redrive vô hạn.

Non-blocking retry hữu ích khi cần chờ lâu mà không giữ partition consumer chính. Tuy nhiên, nó có thể làm thay đổi thứ tự record. Kiểm tra giới hạn tương thích của phiên bản Spring Kafka đang dùng, đặc biệt với batch listener và transaction.

## 8. Quy trình sửa dữ liệu trước khi redrive

Khi record đã vào DLT, đừng lập tức gửi lại toàn bộ. Trước hết cần hiểu lỗi và quyết định loại sửa phù hợp.

Một quy trình vận hành:

~~~mermaid
flowchart TD
    A["Phát hiện DLT record"] --> B["Triage và phân loại lỗi"]
    B --> C{"Nguyên nhân đã rõ?"}
    C -->|Chưa| D["Giữ cách ly, thu thập log/trace"]
    D --> B
    C -->|Rồi| E{"Cần sửa gì?"}
    E -->|Code hoặc config| F["Sửa và triển khai bản đã kiểm thử"]
    E -->|Payload hoặc reference data| G["Tạo bản sửa có audit"]
    E -->|Side effect đã sai| H["Tạo compensating event"]
    F --> I["Validate trên bản sao/một record"]
    G --> I
    H --> I
    I --> J{"Kết quả đúng?"}
    J -->|Không| D
    J -->|Có| K["Canary redrive"]
    K --> L{"Metric và nghiệp vụ đạt?"}
    L -->|Không| M["Dừng redrive và điều tra"]
    L -->|Có| N["Redrive phần còn lại có giới hạn"]
    N --> O["Đối soát và đóng incident"]
~~~

### 8.1. Sửa code hoặc cấu hình

Nếu payload đúng nhưng consumer có bug, sửa code rồi triển khai phiên bản mới. Sau khi kiểm thử, redrive record gốc không cần sửa nội dung.

Ví dụ: consumer cũ giả định discount luôn có giá trị, trong khi schema cho phép null. Sau khi code xử lý nullable đúng, record cũ có thể được xử lý lại nguyên trạng.

### 8.2. Sửa payload

Nếu payload thực sự sai, không sửa trực tiếp record đã ghi trong Kafka log. Kafka log là append-only; hãy tạo một record mới có thông tin liên kết với bản gốc.

Một event sửa nên có:

- eventId hoặc correctionId theo quy ước mới.
- originalEventId để truy vết event gốc.
- correlationId và causationId.
- Phiên bản schema.
- Lý do sửa và incident/ticket tham chiếu.
- Người hoặc service thực hiện correction.
- Thời điểm tạo correction.

Cần quyết định rõ event ID:

- Nếu đây là lần thử lại cùng một logical event và side effect trước chưa hoàn tất, có thể giữ event ID gốc để idempotency nhận diện cùng event.
- Nếu đây là một event correction mới, tạo event ID mới và liên kết originalEventId.
- Nếu database đã đánh dấu event gốc là processed nhưng cần thực hiện lại một thao tác có chủ đích, không xóa dấu deduplication một cách tùy tiện. Dùng correction ID hoặc processing generation theo chính sách nghiệp vụ đã phê duyệt.

### 8.3. Sửa trạng thái bằng compensating event

Nếu event gốc đã được áp dụng nhưng tạo ra kết quả sai, redrive event cũ có thể làm sai trạng thái nặng hơn.

Ví dụ:

- Event gốc trừ tồn kho 5 sản phẩm.
- Sau đó phát hiện đơn hàng chỉ có 3 sản phẩm.
- Gửi lại event cũ có thể trừ thêm 5 lần nữa.
- Cách đúng có thể là phát event bù cộng lại 2 sản phẩm hoặc một inventory adjustment theo nghiệp vụ.

Compensating event mô tả thay đổi mới để đưa trạng thái về đúng. Không xóa lịch sử event đã xảy ra.

## 9. Redrive record từ DLT

Redrive là thao tác publish một record DLT trở lại luồng xử lý. Trước khi thực hiện, cần xác định đích và cách giữ metadata.

Các lựa chọn:

| Cách redrive | Khi phù hợp | Lưu ý |
|---|---|---|
| DLT → topic nguồn | Đã sửa nguyên nhân, payload gốc vẫn đúng | Record có offset mới; cần idempotency |
| DLT → repair topic → consumer chính | Cần kiểm tra/transform trước khi quay lại luồng | Thêm một bước xử lý và topic trung gian |
| DLT → topic replay riêng | Muốn chạy lại bằng consumer group riêng | Không ảnh hưởng offset của group production |
| Sửa payload → topic nguồn | Dữ liệu gốc sai và đã tạo bản correction hợp lệ | Lưu originalEventId và correction audit |
| Phát compensating event | Side effect gốc đã được áp dụng nhưng kết quả sai | Cần logic nghiệp vụ cho event bù |

### 9.1. Giữ dấu vết record gốc

Khi redrive, nên giữ các thông tin:

- originalTopic
- originalPartition
- originalOffset
- originalTimestamp
- originalEventId
- redriveId
- redriveAttempt
- incidentId
- repairReason
- redrivenAt

Không chỉ dựa vào offset mới vì record sau redrive là một lần append mới và có offset mới. Dấu vết gốc giúp nối chuỗi sự kiện khi điều tra.

Nếu sử dụng Spring Kafka, DeadLetterPublishingRecoverer đã bổ sung các DLT headers cho vị trí và exception gốc. Khi redrive, hãy quyết định header nào được giữ, header lỗi nào được xóa hoặc chuyển thành audit metadata. Tránh để exception header cũ khiến record mới bị hiểu nhầm là vẫn đang ở trạng thái lỗi.

### 9.2. Java redrive cơ bản

Ví dụ service publish một record đã được kiểm tra từ DLT về topic nguồn:

~~~java
public void redrive(
        ConsumerRecord<String, OrderEvent> failed,
        OrderEvent repaired,
        String incidentId) throws Exception {

    Headers headers = new RecordHeaders();

    headers.add(
        "original-topic",
        failed.topic().getBytes(StandardCharsets.UTF_8)
    );
    headers.add(
        "original-partition",
        Integer.toString(failed.partition()).getBytes(StandardCharsets.UTF_8)
    );
    headers.add(
        "original-offset",
        Long.toString(failed.offset()).getBytes(StandardCharsets.UTF_8)
    );
    headers.add(
        "incident-id",
        incidentId.getBytes(StandardCharsets.UTF_8)
    );
    headers.add(
        "redrive-id",
        UUID.randomUUID().toString().getBytes(StandardCharsets.UTF_8)
    );

    ProducerRecord<String, OrderEvent> replay =
            new ProducerRecord<>(
                "orders",
                failed.partition(),
                null,
                failed.key(),
                repaired,
                headers
            );

    kafkaTemplate.send(replay).get(10, TimeUnit.SECONDS);
}
~~~

Đây là ví dụ minh họa. Trong ứng dụng thực tế:

- Dùng serializer đúng với topic đích.
- Xác minh partition đích tồn tại; nếu số partition thay đổi, không gửi vào partition không hợp lệ.
- Giữ các header nghiệp vụ cần thiết nhưng loại bỏ header lỗi cũ không còn đúng.
- Không dùng null timestamp một cách mặc định nếu yêu cầu bảo toàn thời gian nghiệp vụ; có thể lưu timestamp gốc ở header và dùng timestamp redrive mới.
- Ghi audit record trước/sau theo quy trình có thể đối soát.
- Xác nhận Future hoàn tất thành công trước khi đánh dấu thao tác redrive đã gửi.

### 9.3. Không xóa DLT ngay sau khi publish lại

Một lần gửi redrive thành công chỉ chứng minh broker nhận record mới theo producer ACK. Nó chưa chứng minh consumer đã xử lý nghiệp vụ thành công.

Giữ record DLT cho đến khi:

- Record redrive được consumer nhận.
- Business processing hoàn tất.
- Offset/checkpoint được xác nhận.
- Kết quả nghiệp vụ được đối soát.
- Incident được đóng theo quy trình.

Có thể đánh dấu DLT record đã redrive bằng một audit store hoặc topic audit riêng. Không cần xóa record gốc khỏi Kafka log; retention sẽ xử lý theo policy.

## 10. Giữ idempotency khi redrive

Redrive thường tạo một lần publish mới. Idempotent producer không tự ngăn duplicate nghiệp vụ do operator chủ động gửi lại record.

Dùng event ID ổn định và inbox/deduplication ở consumer. Ví dụ bảng processed event có unique key theo logical event ID:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL,
    result_code VARCHAR(50) NOT NULL
);
~~~

Khi nhận event, consumer ghi event ID và business update trong cùng transaction database. Nếu event đã tồn tại, consumer nhận ra đây là lần giao lại và không lặp side effect.

Nếu correction là một sự kiện nghiệp vụ mới, dùng correction ID riêng và lưu liên kết với event gốc. Đừng tái sử dụng event ID theo cách khiến deduplication loại bỏ một correction hợp lệ.

## 11. Kiểm soát ordering khi redrive

Redrive một record cũ về topic nguồn thường đưa nó đến cuối log, tức có offset mới lớn hơn các record đã tồn tại. Kafka không chèn record trở lại vị trí offset cũ.

Ví dụ:

| Thứ tự | Event | Trạng thái |
|---:|---|---|
| Offset 100 | OrderCreated | Đã vào DLT |
| Offset 101 | OrderPaid | Đã xử lý |
| Offset 102 | OrderShipped | Đã xử lý |
| Offset 150 | OrderCreated redrive | Được publish lại sau repair |

Nếu business logic giả định event luôn được áp dụng đúng thứ tự, event offset 150 có thể đến sau khi entity đã chuyển sang trạng thái shipped.

Các cách kiểm soát:

- Dùng sequence/version tăng dần trên từng entity.
- Consumer từ chối hoặc giữ event nếu version đến sau chưa có version trước.
- Tạm dừng partition liên quan trong khi repair nếu cần strict ordering.
- Redrive theo thứ tự gốc và kiểm tra trạng thái hiện tại trước khi áp dụng.
- Với event đã bị event sau supersede, dùng correction/compensation thay vì replay mù.

Không thể khôi phục ordering lịch sử chỉ bằng cách gửi record cũ trở lại topic nguồn.

## 12. Redrive theo lô và kiểm soát tốc độ

Không redrive hàng trăm nghìn record cùng lúc nếu downstream chưa được kiểm chứng. Một đợt replay lớn có thể làm database quá tải hoặc khiến consumer lag tăng đột biến.

Quy trình an toàn:

1. Đếm số record theo exception type, source topic, partition và thời gian.
2. Chọn một nhóm nhỏ đại diện cho từng loại lỗi.
3. Redrive canary với giới hạn tốc độ.
4. Theo dõi error rate, retry rate, DLT rate và downstream latency.
5. Tăng batch size từng bước khi hệ thống ổn định.
6. Dừng ngay nếu xuất hiện duplicate, ordering violation hoặc lỗi mới.
7. Đối soát số record đã redrive với số record business success.

Các giới hạn nên cấu hình:

- Maximum records per batch.
- Maximum records per second.
- Maximum concurrent redrive workers.
- Maximum retry/redrive generations.
- Pause/resume switch.
- Time window và partition filter.
- Allowlist event type hoặc incident ID.

## 13. Replaying bằng consumer offset reset

Một cách khác để đọc lại dữ liệu là reset offset của consumer group:

~~~bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --group orders-service \
  --topic orders \
  --reset-offsets \
  --to-earliest \
  --dry-run
~~~

Sau khi xem kết quả, có thể dùng --execute để áp dụng. Các lựa chọn khác gồm --to-offset, --shift-by, --to-datetime và --to-latest tùy phiên bản CLI.

Cần rất cẩn thận:

- Offset reset ảnh hưởng tiến độ của consumer group được chỉ định.
- Reset theo partition có thể làm nhiều record đã xử lý bị đọc lại.
- Không phải công cụ chọn lọc một record duy nhất để replay.
- Không reset group production đang chạy mà chưa dừng consumer và có kế hoạch rõ ràng.
- Tốt hơn nên dùng group replay riêng khi cần kiểm thử hoặc tái dựng dữ liệu.
- Nếu reset offset, side effect vẫn có thể chạy lại; idempotency vẫn cần thiết.

Dùng DLT redrive khi cần phục hồi chọn lọc một số record. Dùng offset reset khi cần replay một phạm vi partition/time/offset và đã chấp nhận tác động đến toàn bộ record trong phạm vi đó.

## 14. Publish retry/DLT và commit offset nguồn

Có một failure window quan trọng khi consumer publish record sang retry topic hoặc DLT rồi commit offset nguồn.

Hai thao tác này là hai ghi riêng nếu không dùng transaction:

- Publish retry/DLT thành công nhưng commit offset nguồn thất bại: record có thể được gửi sang retry/DLT lần nữa sau khi consumer restart.
- Commit offset nguồn trước nhưng publish retry/DLT thất bại: record nguồn có thể bị bỏ qua trong khi bản retry không tồn tại.

Với thiết kế at-least-once, chấp nhận khả năng duplicate và dùng event ID để deduplicate ở retry/DLT consumer. Nếu cần atomicity giữa output retry/DLT và input offset, dùng Kafka transaction với producer transactional và gửi source offset vào transaction phù hợp; Spring Kafka có transaction-capable listener container và cơ chế rollback/recovery tương ứng.

Không giả định một lần gọi KafkaTemplate.send() rồi commit consumer offset riêng là một thao tác nguyên tử.

## 15. Runbook xử lý một DLT incident

Một runbook tối thiểu có thể tổ chức theo các bước:

### Bước 1: Triage

- Xác định topic DLT, consumer group và service.
- Đếm số record lỗi, độ tuổi và phân bố partition.
- Phân loại exception và kiểm tra log/trace.
- Xác định lỗi đang tiếp diễn hay đã hết.
- Kiểm tra có side effect nào đã thực hiện trước khi lỗi hay chưa.

### Bước 2: Khoanh vùng

- Tạm dừng redrive tự động nếu nguyên nhân chưa rõ.
- Giữ nguyên DLT và audit metadata.
- Xác định các record cùng event type, schema version hoặc source.
- Xác định phạm vi entity bị ảnh hưởng.

### Bước 3: Sửa nguyên nhân

- Sửa code/config/reference data hoặc tạo corrected event.
- Nếu side effect sai đã xảy ra, thiết kế compensating event.
- Thử trên môi trường staging hoặc một bản sao dữ liệu.
- Kiểm tra idempotency và ordering.

### Bước 4: Canary redrive

- Chọn một vài record đại diện.
- Ghi incident ID và redrive ID.
- Publish với tốc độ thấp.
- Xác nhận producer ACK, consumer processing success và offset commit.
- Kiểm tra trạng thái database/business.

### Bước 5: Redrive có kiểm soát

- Mở rộng theo batch.
- Giới hạn throughput và concurrency.
- Theo dõi retry/DLT mới phát sinh.
- Dừng nếu error rate hoặc downstream latency vượt ngưỡng.

### Bước 6: Đối soát và đóng incident

- So sánh số record DLT ban đầu, số record đã redrive và số business success.
- Xác định duplicate được deduplicate đúng.
- Xác nhận không có entity bị sai ordering/state.
- Lưu báo cáo repair và nguyên nhân gốc.
- Đặt retention/cleanup theo policy.

## 16. Metrics và audit cho retry, DLT và redrive

Theo dõi các chỉ số:

| Metric | Ý nghĩa |
|---|---|
| retry_attempt_total | Tổng số lần retry |
| retry_exhausted_total | Số record hết retry budget |
| dlt_publish_total | Số record được gửi vào DLT |
| dlt_publish_failure_total | Số lần publish DLT thất bại |
| dlt_records_current | Số record đang tồn trong DLT theo công cụ/exporter |
| dlt_oldest_record_age | Tuổi record cũ nhất trong DLT |
| redrive_attempt_total | Tổng số lần operator/service redrive |
| redrive_success_total | Số lần redrive được publish và xác nhận |
| redrive_business_success_total | Số record redrive đã hoàn tất nghiệp vụ |
| duplicate_event_total | Số lần deduplication phát hiện event trùng |
| retry_topic_lag | Backlog của retry consumer |

Audit log nên lưu:

- Incident/ticket ID.
- Event ID và original topic-partition-offset.
- Exception ban đầu và nguyên nhân đã xác định.
- Repair version hoặc correction ID.
- Người/service thực hiện redrive.
- Thời điểm, số lần và topic đích.
- Producer send result.
- Business processing result.
- Kết quả đối soát.

Không dùng metric tổng hợp duy nhất cho DLT. Cần phân nhóm theo topic, exception class, event type, schema version và source service để nhận ra lỗi có hệ thống.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
|---|---|---|
| Retry vô hạn | Partition bị kẹt, downstream bị quá tải | Retry budget, backoff và DLT |
| Retry mọi exception | Tốn tài nguyên với lỗi dữ liệu permanent | Phân loại exception |
| Chuyển DLT rồi commit dù publish thất bại | Mất record khỏi luồng xử lý | Kiểm tra DLT publish result trước recovery/commit |
| Redrive toàn bộ DLT ngay lập tức | Tạo burst tải và lỗi lặp | Canary, rate limit và batch |
| Sửa record cũ trực tiếp | Mất tính bất biến và audit | Append corrected/compensating event |
| Redrive cùng event ID mà không hiểu dedupe | Consumer bỏ qua correction hoặc lặp side effect | Thiết kế logical event ID và correction ID |
| Dùng retry topic khi cần strict ordering | Event sau vượt qua event trước | Blocking retry hoặc sequence/version theo entity |
| Không giữ source coordinates | Không truy nguyên được record gốc | Lưu topic, partition, offset và event ID |
| Dùng offset reset để replay một record | Đọc lại nhiều record ngoài dự kiến | DLT redrive chọn lọc hoặc replay group riêng |
| Xóa DLT sau khi producer ACK redrive | Mất bằng chứng trước khi nghiệp vụ hoàn tất | Giữ audit đến khi business reconciliation xong |

## 18. Lab: đưa record lỗi từ DLT trở lại luồng

Mục tiêu: tạo một record lỗi dữ liệu, đưa vào DLT, sửa payload, redrive và xác nhận consumer xử lý thành công.

### Bước 1: Tạo topic

Tạo các topic thử nghiệm:

~~~bash
bin/kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --partitions 3 \
  --replication-factor 1

bin/kafka-topics.sh --create \
  --bootstrap-server localhost:9092 \
  --topic orders.DLT \
  --partitions 3 \
  --replication-factor 1
~~~

### Bước 2: Tạo record không hợp lệ

Gửi event có currency=VNDX hoặc thiếu orderId. Consumer validate và ném exception không retryable.

### Bước 3: Chuyển record vào DLT

Cấu hình DefaultErrorHandler với DeadLetterPublishingRecoverer. Xác nhận DLT chứa payload và headers chỉ ra topic, partition, offset gốc.

### Bước 4: Điều tra nguyên nhân

Đọc record DLT, kiểm tra event ID, exception, schema version và source coordinates. Quyết định đây là lỗi payload hay lỗi code.

### Bước 5: Tạo corrected event

Sửa currency thành giá trị hợp lệ hoặc tạo correction event có correctionId và originalEventId. Ghi incident ID và lý do sửa.

### Bước 6: Canary redrive

Gửi một record về topic orders hoặc repair topic. Chờ consumer nhận, xử lý database và commit offset. Kiểm tra event ID và trạng thái business.

### Bước 7: Đối soát

So sánh số record DLT ban đầu, số redrive đã publish và số business success. Xác nhận không có duplicate hoặc ordering violation.

### Bước 8: Thử redrive lặp

Gửi lại cùng event một lần nữa để xác nhận inbox/deduplication ngăn side effect bị thực hiện hai lần. Sau đó thử một correction event hợp lệ có ID riêng để kiểm tra quy tắc nhận diện correction.

## 19. Checklist trước production

- [ ] Phân loại transient, permanent và poison pill.
- [ ] Retry có giới hạn số lần và tổng thời gian.
- [ ] Có backoff; cân nhắc jitter khi nhiều consumer retry đồng thời.
- [ ] Exception không retryable được cách ly sớm.
- [ ] Blocking retry hay retry topic được chọn theo yêu cầu ordering.
- [ ] DLT có partition và serializer phù hợp.
- [ ] DLT publish failure không bị coi là recovery thành công.
- [ ] DLT giữ source topic, partition, offset, event ID và exception metadata.
- [ ] Có chính sách retention, ACL và bảo vệ payload nhạy cảm.
- [ ] Có quy trình sửa code, sửa payload và compensating event.
- [ ] Redrive có incident ID, redrive ID và audit trail.
- [ ] Idempotency/deduplication được kiểm thử với record redrive lặp.
- [ ] Có kiểm soát ordering theo partition hoặc entity version.
- [ ] Redrive có canary, rate limit, batch size và pause switch.
- [ ] Không reset offset production nếu chưa đánh giá phạm vi replay.
- [ ] Đối soát business success trước khi đóng incident.
- [ ] Có metric cho retry, DLT, redrive, duplicate và tuổi record lỗi.

## 20. Tài liệu tham khảo

- [Apache Kafka 4.4 – Consumer Configs](https://kafka.apache.org/44/configuration/consumer-configs/)
- [Apache Kafka 4.4 – KafkaConsumer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html)
- [Apache Kafka 4.4 – KafkaProducer Javadoc](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html)
- [Spring Kafka – Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html)
- [Spring Kafka – Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html)

Retry, repair và redrive là một quy trình có kiểm soát. Hãy phân loại lỗi trước khi thử lại, giữ record gốc cùng metadata truy nguyên, sửa nguyên nhân trước khi redrive và xác nhận kết quả nghiệp vụ sau khi producer đã gửi thành công. Khi kết hợp retry budget, DLT, idempotency, ordering và audit, hệ thống có thể phục hồi dữ liệu lỗi mà vẫn giữ được tính đúng đắn của luồng event.
