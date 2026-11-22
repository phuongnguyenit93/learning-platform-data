# Số lần giao, bản ghi không xử lý được và chiến lược xử lý lỗi

Share Groups thay đổi cách Kafka phân phối công việc cho consumer. Trong consumer group truyền thống, một partition tại một thời điểm được gán cho một consumer member; offset biểu diễn tiến độ đã commit của partition. Với Share Groups, nhiều consumer có thể cùng nhận các record từ một partition và xác nhận kết quả cho từng record. Broker theo dõi trạng thái giao nhận, record đang được consumer giữ xử lý và số lần record đã được giao.

Vì vậy, xử lý lỗi trong Share Groups cần nhìn ở cấp record: record đã được acquire bao nhiêu lần, consumer nên xác nhận thành công, trả record để giao lại hay từ chối vĩnh viễn, và khi nào record vượt giới hạn giao nhận. Một record độc hại hoặc dữ liệu không hợp lệ không nên khiến consumer lặp vô hạn; đồng thời một lỗi database tạm thời không nên làm record bị loại bỏ vĩnh viễn.

## 1. Share Group xử lý công việc khác consumer group truyền thống

Consumer group truyền thống gán partition cho một member trong group. Consumer xử lý record theo thứ tự partition và commit offset để biểu diễn vị trí tiếp theo cần đọc. Nếu một record lỗi, ứng dụng thường retry tại consumer, pause partition, hoặc chuyển sang retry/DLT topic rồi mới commit offset.

Share Group sử dụng cơ chế record acquisition và acknowledgment. Nhiều consumer trong cùng share group có thể cùng xử lý các record thuộc một partition; broker theo dõi trạng thái từng record. Consumer xác nhận record cụ thể sau khi xử lý, thay vì chỉ commit một offset liên tục cho cả partition theo mô hình truyền thống.

| Đặc điểm | Consumer group truyền thống | Share Group |
|---|---|---|
| Đơn vị phân phối chính | Partition được assign cho member | Record được acquire bởi consumer |
| Nhiều consumer cùng partition | Không trong cùng group tại một thời điểm | Có thể |
| Tiến độ | Committed offset theo partition | Trạng thái acknowledgment theo record và delivery state |
| Xử lý lỗi | Retry/seek/pause/DLT thường do ứng dụng điều phối theo partition | ACCEPT, RELEASE, REJECT và delivery count theo record |
| Ordering | Consumer đọc theo thứ tự partition; xử lý tuần tự thường dễ kiểm soát hơn | Nhiều consumer có thể xử lý song song; thứ tự hoàn tất không được bảo đảm toàn cục |
| Use case | Event processing cần ordering theo partition | Work sharing, xử lý độc lập từng record và tăng mức song song |

Share Group không tự động làm mọi ứng dụng consumer group nhanh hơn. Nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt theo aggregate hoặc cần một record lỗi chặn các record sau, phải đánh giá kỹ semantics trước khi chuyển.

## 2. Vòng đời giao nhận của một record

Ở mức khái niệm, record trong Share Group trải qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Available
    Available --> Acquired: consumer nhận record
    Acquired --> Acknowledged: ACCEPT
    Acquired --> Available: RELEASE hoặc lock hết hạn
    Acquired --> Archived: REJECT
    Available --> Archived: vượt giới hạn delivery count
    Acknowledged --> [*]
    Archived --> [*]
~~~

- **Available:** record có thể được giao cho một consumer trong share group.
- **Acquired:** một consumer đã nhận record và đang có quyền xử lý trong thời gian lock/lease.
- **Acknowledged:** consumer xác nhận xử lý thành công; broker ghi nhận record đã hoàn tất trong group.
- **Released:** consumer trả record về trạng thái có thể được acquire lại.
- **Archived:** record không còn được giao lại bình thường cho share group đó, ví dụ do consumer từ chối hoặc record đã vượt giới hạn giao nhận.

Tên trạng thái nội bộ và cách broker biểu diễn có thể khác giữa các phiên bản Kafka. Điều cần nắm là acquisition tạo quyền xử lý tạm thời, acknowledgment quyết định kết quả, còn record không được xác nhận có thể được giao lại khi được release hoặc lock hết hạn.

~~~mermaid
sequenceDiagram
    participant B as Share Group broker
    participant C1 as Consumer A
    participant C2 as Consumer B
    B->>C1: Acquire record R
    C1->>C1: Xử lý R
    C1-->>B: RELEASE (lỗi tạm thời)
    B->>C2: Acquire lại record R
    C2->>C2: Xử lý thành công
    C2-->>B: ACCEPT
    Note over B: R hoàn tất trong share group
~~~

Ví dụ trên cho thấy record có thể được giao cho consumer khác sau khi được release. Ứng dụng không nên dựa vào việc cùng một instance luôn nhận lại record lỗi.

## 3. Delivery count là gì?

Delivery count là số lần broker đã giao/acquire record cho consumer thuộc share group. Nó giúp ứng dụng và broker nhận biết record đã bị thử xử lý nhiều lần hay chưa.

Một cách đọc đơn giản:

| Lần giao | Kết quả xử lý | Hệ quả |
|---:|---|---|
| 1 | Consumer acquire record | Delivery count bắt đầu tăng |
| 1 | Consumer RELEASE | Record có thể được giao lại |
| 2 | Consumer khác acquire record | Delivery count tăng thêm |
| 2 | Consumer RELEASE | Record có thể tiếp tục được giao |
| 3 | Consumer xử lý thành công và ACCEPT | Record được xác nhận hoàn tất |

Delivery count gắn với record trong share group, không phải số lần consumer process khởi động lại và cũng không phải consumer lag. Một record có delivery count cao là dấu hiệu nó đã nhiều lần được giao nhưng chưa được xác nhận thành công.

### Delivery count dùng để làm gì?

- Phân biệt lỗi thoáng qua với record liên tục thất bại.
- Áp dụng giới hạn retry theo record.
- Chọn thời điểm chuyển record sang DLT/quarantine.
- Tạo metric về poison record và chất lượng dữ liệu.
- Điều tra record nào đang tiêu tốn nhiều lần giao nhận.

Không nên chỉ dựa vào delivery count để kết luận lỗi là vĩnh viễn. Một database outage kéo dài có thể làm nhiều record có delivery count cao dù payload hoàn toàn hợp lệ. Cần kết hợp exception class, thời gian lỗi, downstream health và chính sách retry.

### Đọc delivery count từ client

Share Consumer API của Kafka có thể cung cấp delivery count cùng thông tin record tùy phiên bản client. Trong các phiên bản có accessor trên ConsumerRecord, có thể đọc delivery count từ record metadata. Hãy kiểm tra Javadoc của đúng phiên bản kafka-clients đang triển khai; không tự suy ra số lần giao từ số lần gọi poll.

Ví dụ minh họa:

~~~java
for (ConsumerRecord<String, String> record : records) {
    var deliveryCount = record.deliveryCount();
    log.info(
        "topic={}, partition={}, offset={}, deliveryCount={}",
        record.topic(),
        record.partition(),
        record.offset(),
        deliveryCount
    );
}
~~~

Nếu phiên bản client chưa expose accessor này, không nên tự tạo delivery count bằng biến local vì biến đó mất khi consumer restart và không phản ánh lần giao ở broker. Hãy dùng API/metadata được phiên bản hỗ trợ hoặc metric broker phù hợp.

## 4. Giới hạn số lần giao nhận

Broker có cấu hình giới hạn số lần một record được giao cho share group. Trong các phiên bản hỗ trợ Share Groups, cấu hình broker thường được gọi là share.group.max.delivery.count. Giá trị mặc định và khả năng thay đổi động phụ thuộc phiên bản Kafka; cần kiểm tra cấu hình thực tế của cluster.

Ví dụ minh họa:

~~~properties
share.group.max.delivery.count=5
~~~

Giới hạn này bảo vệ share group khỏi việc một record liên tục được giao lại vô hạn. Khi record chạm/vượt ngưỡng theo semantics của phiên bản broker, broker có thể archive record để nó không tiếp tục được giao bình thường cho group.

### Giới hạn delivery count không phải Dead Letter Topic

Đây là khác biệt rất quan trọng:

| Giới hạn delivery count | Dead Letter Topic |
|---|---|
| Broker theo dõi số lần giao và ngăn retry vô hạn | Ứng dụng hoặc pipeline recovery ghi bản sao record sang topic riêng |
| Record có thể bị archive khỏi luồng giao bình thường | DLT lưu payload và metadata để điều tra/replay |
| Không tự tạo bản sao payload vào topic khác | Có thể lưu raw payload, exception và nguồn gốc record |
| Là cơ chế bảo vệ ở tầng Share Group | Là chiến lược xử lý dữ liệu lỗi ở tầng ứng dụng |

Không giả định broker tự chuyển record vượt ngưỡng sang DLT. Nếu cần giữ payload lỗi để điều tra hoặc sửa dữ liệu rồi replay, ứng dụng phải triển khai quarantine/DLT trước khi record bị archive.

### Chọn giới hạn bao nhiêu?

Không có một con số phù hợp cho mọi workload. Cần xem xét:

- Số lần lỗi transient thường cần để downstream phục hồi.
- Mức độ tốn kém của mỗi lần xử lý.
- Thời gian lock/acquisition và độ trễ retry.
- Tốc độ record mới được đưa vào share group.
- Khả năng quan sát và vận hành DLT.
- Rủi ro một record độc hại chiếm nhiều tài nguyên.

Giới hạn quá thấp có thể archive record trong một outage ngắn. Giới hạn quá cao có thể làm poison record tiêu tốn nhiều CPU, I/O và log. Đặt giới hạn cùng với retry/backoff và DLT policy.

## 5. Ba kiểu acknowledgment quan trọng

Share Consumer sử dụng acknowledgment để báo kết quả xử lý record. Ba kiểu thường gặp:

| Acknowledge type | Ý nghĩa | Khi dùng |
|---|---|---|
| ACCEPT | Record đã được xử lý thành công | Side effect cần thiết đã hoàn tất và ứng dụng sẵn sàng xác nhận |
| RELEASE | Không hoàn tất record; trả record để có thể được giao lại | Lỗi transient hoặc cần thử lại ở consumer khác |
| REJECT | Từ chối record, không muốn nó tiếp tục được giao theo luồng bình thường | Payload độc hại hoặc lỗi vĩnh viễn đã được xử lý/quarantine |

### ACCEPT

Chỉ ACCEPT sau khi xử lý nghiệp vụ thành công. Nếu listener cập nhật database, phải bảo đảm transaction database đã commit trước khi gửi acknowledgment. Nếu ACCEPT trước khi side effect hoàn tất, crash có thể khiến record không được giao lại dù nghiệp vụ chưa được ghi.

### RELEASE

RELEASE trả record về trạng thái có thể được consumer khác acquire. Đây là lựa chọn thường dùng cho lỗi tạm thời như database timeout, HTTP 503 hoặc dependency đang quá tải.

RELEASE không có nghĩa broker sẽ chờ một khoảng backoff do ứng dụng yêu cầu trong mọi phiên bản. Nếu record trở nên available ngay, nó có thể được giao lại rất nhanh. Không tạo vòng lặp nóng bằng cách RELEASE liên tục mà không có delay/backoff.

### REJECT

REJECT biểu thị ứng dụng không muốn record được giao lại bình thường. Chỉ dùng sau khi đã quyết định record là không thể xử lý theo luồng hiện tại và payload đã được lưu vào nơi phục hồi nếu cần.

Không REJECT chỉ vì một lần gọi database bị timeout. REJECT sai có thể khiến record bị archive và không còn được giao lại trong share group.

## 6. Phân loại lỗi trước khi chọn hành động

Chính sách xử lý nên dựa trên nguyên nhân:

| Nhóm lỗi | Ví dụ | Hành động thường phù hợp |
|---|---|---|
| Lỗi transient | DB timeout, HTTP 503, network reset | RELEASE với backoff có giới hạn |
| Rate limit | HTTP 429, quota tạm thời | Backoff theo Retry-After nếu có, sau đó RELEASE |
| Payload sai định dạng | JSON hỏng, bytes không parse được | Ghi DLT/quarantine rồi REJECT |
| Schema không tương thích | Enum mới, field đổi kiểu, schema ID không tồn tại | Quarantine hoặc DLT; sửa contract rồi replay có kiểm soát |
| Vi phạm nghiệp vụ vĩnh viễn | Amount âm, account không tồn tại theo quy tắc | Reject/quarantine hoặc business exception flow |
| Lỗi lập trình | Null pointer, mapping sai, bug code | Alert, có thể RELEASE hạn chế trong thời gian rollout; không retry vô hạn |
| Lỗi credential/quyền | SASL auth failure, topic authorization | Dừng/giảm retry, sửa cấu hình và cảnh báo vận hành |

Lỗi transient thường có khả năng tự phục hồi. Lỗi permanent thường không thay đổi nếu cùng payload được xử lý lại. Tuy nhiên, một số lỗi có thể chuyển từ permanent sang recoverable sau khi cập nhật consumer/schema; DLT giúp giữ lại dữ liệu để replay sau khi sửa.

## 7. Chiến lược retry có backoff

Retry ngay lập tức có thể làm tình trạng downstream xấu hơn. Nếu database đang quá tải, hàng nghìn record RELEASE và acquire lại liên tục sẽ tạo thêm request, log và lock churn.

Một chiến lược retry nên có:

- Giới hạn số lần thử.
- Exponential backoff để tăng khoảng nghỉ giữa các lần thử.
- Jitter để nhiều consumer không retry đồng loạt.
- Timeout tổng cho một record hoặc một nhóm công việc.
- Circuit breaker/health signal khi downstream lỗi diện rộng.
- Quyết định rõ khi nào RELEASE, khi nào DLT/REJECT.

Ví dụ lịch backoff:

| Lần thử | Khoảng chờ minh họa |
|---:|---:|
| 1 | 500 ms |
| 2 | 1 s |
| 3 | 2 s |
| 4 | 4 s |
| 5 | Chuyển sang retry topic/DLT theo policy |

Đây là lịch do ứng dụng quản lý, không phải cam kết broker tự delay từng record. Nếu Share Consumer không hỗ trợ delayed redelivery theo yêu cầu, có thể publish sang retry topic có thời gian chờ hoặc dùng scheduler bên ngoài. Khi dùng retry topic, phải giữ event ID, key và metadata nguồn.

### Không giữ record acquired trong lúc sleep quá lâu

Nếu consumer acquire record rồi sleep nhiều phút trước khi RELEASE, record vẫn có thể ở trạng thái acquired và không sẵn sàng cho consumer khác. Lock/lease có thể hết hạn trong lúc consumer còn xử lý; khi đó record có thể được giao lại và tạo xử lý đồng thời.

Thay vì giữ acquisition trong lúc chờ dài:

1. Ghi nhận lỗi và quyết định retry delay.
2. Nếu cần delayed retry dài, chuyển record sang retry topic hoặc scheduler có persistence.
3. Xác nhận việc chuyển giao retry thành công.
4. Sau đó mới xác nhận/reject record nguồn theo thiết kế.

## 8. Poison record là gì?

Poison record là record luôn thất bại khi xử lý do payload hoặc điều kiện không thể tự phục hồi. Ví dụ:

- JSON không hợp lệ hoặc thiếu cấu trúc bắt buộc.
- Schema không được consumer hỗ trợ.
- Giá trị enum không được mapping.
- Record vượt giới hạn kích thước nghiệp vụ.
- Một field có giá trị làm code ném exception ở mọi lần thử.
- Dữ liệu vi phạm invariant mà consumer không thể sửa.

Trong consumer group truyền thống, poison record có thể chặn tiến độ partition nếu consumer cứ retry tại cùng offset. Share Group giảm nguy cơ chặn toàn partition vì record được theo dõi riêng và có thể được release, reject hoặc archive theo delivery policy. Tuy nhiên, poison record vẫn có thể gây lặp giao, chiếm tài nguyên và làm mất dữ liệu nếu bị archive mà không được lưu DLT.

### Dấu hiệu nhận biết

- Delivery count tăng liên tục cho cùng record.
- Cùng topic/partition/offset xuất hiện lặp trong log.
- Cùng exception class và stack trace lặp lại.
- Một số record có thời gian xử lý bất thường.
- DLT/quarantine rate tăng.
- Số record archived do delivery limit tăng.

## 9. Dead Letter Topic cho Share Group

DLT là nơi lưu record không thể xử lý trong luồng chính. Một bản ghi DLT hữu ích nên có:

| Trường | Mục đích |
|---|---|
| Original topic | Topic nguồn |
| Original partition/offset | Vị trí record nguồn |
| Original key/value hoặc raw bytes | Dữ liệu để điều tra và replay |
| Event ID/correlation ID | Liên kết với nghiệp vụ |
| Delivery count | Số lần record đã được giao |
| Exception class/message | Nguyên nhân lỗi |
| First/last failure time | Theo dõi tuổi lỗi |
| Consumer group | Share group xử lý record |
| Consumer instance | Instance cuối cùng xử lý |
| Schema/version | Hỗ trợ sửa contract và replay |

Không chỉ ghi exception message vào log rồi REJECT. Nếu cần phục hồi dữ liệu, phải lưu payload và metadata trong một nơi bền vững, có ACL và retention phù hợp.

### Trình tự DLT an toàn

1. Xác định lỗi permanent hoặc record đã hết retry budget.
2. Serialize payload gốc và metadata vào DLT/quarantine topic.
3. Chờ xác nhận publish thành công.
4. Sau đó mới REJECT record nguồn.
5. Nếu publish DLT thất bại, không REJECT; RELEASE hoặc retry theo chính sách.

~~~mermaid
flowchart TD
    A[Acquire record] --> B[Process]
    B -->|Success| C[ACCEPT]
    B -->|Transient error| D[Backoff]
    D --> E[RELEASE]
    B -->|Permanent error / retry budget exhausted| F[Publish to DLT]
    F -->|Publish confirmed| G[REJECT source record]
    F -->|Publish failed| H[Do not reject]
    H --> I[RELEASE / retry DLT publish]
~~~

Publish DLT và acknowledgment source record thường là hai thao tác khác nhau. Nếu DLT publish thành công nhưng consumer crash trước khi REJECT, record nguồn có thể được giao lại và DLT có thể nhận bản sao. Dùng event ID/source coordinate làm idempotency key ở DLT consumer hoặc storage để deduplicate.

Không giả định Kafka transaction hiện tại tự động tạo atomic transaction giữa share acknowledgment và produce DLT trong mọi phiên bản/API. Kiểm tra chính xác khả năng transaction của ShareConsumer và release đang dùng; nếu không có transaction boundary được hỗ trợ, thiết kế để chịu duplicate.

## 10. Java ShareConsumer: xử lý và acknowledge

Share Consumer API được cung cấp trong các phiên bản Kafka có hỗ trợ Share Groups. API và trạng thái preview/maturity thay đổi theo release; cần dùng kafka-clients đúng phiên bản broker và kiểm tra Javadoc tương ứng.

Ví dụ cấu hình cơ bản:

~~~java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG,
          "kafka-1:9092,kafka-2:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG,
          "order-share-workers");
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
          StringDeserializer.class.getName());

ShareConsumer<String, String> consumer =
    new ShareConsumer<>(props);
~~~

Consumer subscribe topic và poll record:

~~~java
consumer.subscribe(List.of("orders.events"));

while (!Thread.currentThread().isInterrupted()) {
    ConsumerRecords<String, String> records =
        consumer.poll(Duration.ofMillis(500));

    for (ConsumerRecord<String, String> record : records) {
        try {
            orderService.handle(record.value());
            consumer.acknowledge(record, AcknowledgeType.ACCEPT);
        }
        catch (TransientProcessingException ex) {
            consumer.acknowledge(record, AcknowledgeType.RELEASE);
        }
        catch (PermanentProcessingException ex) {
            deadLetterPublisher.publishAndConfirm(record, ex);
            consumer.acknowledge(record, AcknowledgeType.REJECT);
        }
    }
}
~~~

Đây là skeleton để thể hiện luồng xử lý; tên constructor, overload acknowledge, exception và cách xác nhận kết quả publish cần đối chiếu phiên bản Kafka client cụ thể. Trong production, không bắt mọi RuntimeException rồi REJECT. Phải phân loại lỗi, có timeout, backoff, xử lý lỗi DLT và đóng consumer đúng lifecycle.

### Xử lý delivery count trong policy

Ví dụ pseudocode:

~~~java
int deliveryCount = readDeliveryCount(record);

if (deliveryCount <= 2 && isTransientFailure(error)) {
    backoffFor(deliveryCount);
    release(record);
}
else if (isPermanentFailure(error) || deliveryCount >= retryLimit) {
    publishDltAndConfirm(record, error);
    reject(record);
}
else {
    backoffFor(deliveryCount);
    release(record);
}
~~~

readDeliveryCount(), release(), reject() và publishDltAndConfirm() là helper minh họa do ứng dụng định nghĩa; API lấy delivery count/acknowledge cụ thể phụ thuộc kafka-clients version. Không dùng biến local làm nguồn delivery count có thẩm quyền.

## 11. Xử lý khi consumer crash hoặc lock hết hạn

Share Group sử dụng cơ chế lock/lease để tránh nhiều consumer cùng acquire một record tại cùng thời điểm theo semantics của broker. Nếu consumer không acknowledge, crash hoặc mất kết nối, lock có thể hết hạn và record trở lại trạng thái có thể giao.

Một tình huống quan trọng:

1. Consumer A acquire record R.
2. A cập nhật database thành công.
3. A crash trước khi gửi ACCEPT.
4. Lock hết hạn.
5. Consumer B acquire lại R và xử lý lần nữa.

Đây là cửa sổ duplicate. A đã tạo side effect nhưng broker chưa nhận acknowledgment. Vì vậy, consumer phải idempotent:

- Dùng event ID duy nhất và bảng inbox có unique constraint.
- Dùng upsert theo aggregate ID/version.
- Ghi ledger có business transaction ID.
- Kiểm tra trạng thái trước khi áp dụng side effect.
- Không dựa vào delivery count để chống duplicate nghiệp vụ.

Nếu consumer A vẫn tiếp tục xử lý sau khi lock hết hạn, B có thể đã bắt đầu xử lý cùng record. Cần timeout nghiệp vụ ngắn hơn lock budget và idempotency ở hệ thống đích để bảo vệ khỏi hai lần xử lý đồng thời.

### Inbox để chống side effect trùng

Nếu consumer cập nhật database, event ID nên có unique constraint trong cùng database transaction với thay đổi nghiệp vụ. Cách làm phổ biến là insert inbox marker trước; chỉ khi insert thành công mới thực hiện side effect.

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Ví dụ với PostgreSQL:

~~~sql
INSERT INTO processed_events(event_id, processed_at)
VALUES (:event_id, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;
~~~

Ứng dụng kiểm tra số row được insert. Nếu không có row mới, event đã được xử lý và có thể xác nhận mà không áp dụng side effect lần nữa. Nếu insert thành công, thực hiện cập nhật nghiệp vụ trong cùng transaction; nếu transaction rollback, cả inbox marker và side effect đều rollback.

Không tách insert inbox và cập nhật nghiệp vụ thành hai transaction độc lập, vì crash giữa hai bước có thể tạo trạng thái marker đã ghi nhưng nghiệp vụ chưa hoàn tất.

## 12. Ordering khi retry trong Share Group

Share Group tăng mức song song bằng cách cho nhiều consumer cùng nhận record trong một partition. Do đó, thứ tự xử lý hoàn tất có thể khác thứ tự record trong log.

Ví dụ:

| Record | Consumer | Thời gian xử lý | Kết quả |
|---|---|---:|---|
| R1 | A | 8 giây | RELEASE do DB timeout |
| R2 | B | 1 giây | ACCEPT |
| R3 | C | 2 giây | ACCEPT |
| R1 | D | 1 giây | ACCEPT sau khi được giao lại |

R2 và R3 có thể hoàn tất trước R1. Nếu R1 là OrderCreated còn R2 là OrderPaid của cùng một order, việc áp dụng R2 trước R1 có thể làm sai trạng thái nghiệp vụ.

Giải pháp khi ordering quan trọng:

- Đưa các event cùng aggregate vào một luồng/partitioning strategy có thể serialize xử lý.
- Dùng aggregate version hoặc sequence number và từ chối/đợi version chưa đủ.
- Thiết kế state transition idempotent, cho phép nhận event out-of-order có kiểm soát.
- Chọn consumer group truyền thống nếu yêu cầu thứ tự partition nghiêm ngặt quan trọng hơn work sharing.
- Không dùng Share Group cho luồng cần total ordering mà không có cơ chế ordering ở tầng nghiệp vụ.

## 13. Retry topic và delayed retry

RELEASE thường làm record trở lại trạng thái có thể được acquire; nó không phải một scheduler cho retry sau 5 phút. Nếu cần delay dài hoặc lịch retry khác nhau theo exception, có thể dùng retry topics:

~~~mermaid
flowchart LR
    A[orders.events share group] --> B{Process}
    B -->|Success| C[ACCEPT]
    B -->|Retryable| D[orders.retry.1m]
    D --> E[Retry consumer / scheduler]
    E --> F[orders.retry.ready]
    F --> G[Share group hoặc processor chính]
    B -->|Permanent / exhausted| H[orders.DLT]
~~~

Retry topic cần giữ:

- Original event ID.
- Original topic/partition/offset.
- Attempt number.
- Next eligible time hoặc retry tier.
- Exception category gần nhất.
- Aggregate key và sequence/version.

Retry topic tạo một luồng record mới, vì vậy nó không giữ nguyên delivery state của record nguồn. Ứng dụng phải quản lý retry count riêng trong metadata nếu cần. Consumer cần deduplicate vì retry publish và source acknowledgment có thể bị lặp.

Không đưa retry vô hạn qua nhiều topic. Đặt maximum attempts, maximum age và DLT cuối cùng.

## 14. Chọn chiến lược theo loại lỗi

| Tình huống | Chính sách đề xuất | Vì sao |
|---|---|---|
| DB tạm thời không kết nối | Backoff, RELEASE | Có thể tự phục hồi |
| Downstream trả 429 | Tôn trọng Retry-After, delay/retry topic | Tránh làm tăng rate limit |
| Payload JSON sai cú pháp | DLT rồi REJECT | Cùng payload sẽ tiếp tục lỗi |
| Schema chưa được consumer hỗ trợ | Quarantine/DLT; sửa schema rồi replay | Retry ngay không giúp consumer cũ hiểu schema mới |
| Bug vừa được deploy | Alert, rollback/fix; retry giới hạn | Tránh retry loop trên mọi record |
| Một record làm CPU/memory tăng bất thường | Giới hạn kích thước, timeout, DLT/quarantine | Bảo vệ worker và các record khác |
| Credential hết hạn | Alert và dừng retry nóng; sửa credential | Lỗi ảnh hưởng diện rộng, không phải lỗi riêng record |
| Record đã vượt retry budget | DLT rồi REJECT | Ngăn poison record tiếp tục chiếm tài nguyên |

Nếu lỗi ảnh hưởng toàn bộ downstream, có thể tạm dừng việc lấy thêm công việc hoặc điều tiết số consumer. Tuy nhiên, đừng giữ record acquired quá lâu; xem xét release hoặc retry topic theo chính sách.

## 15. Quan sát delivery count và record lỗi

Nên theo dõi các metric ở cấp group, consumer và record:

| Metric/log | Mục đích |
|---|---|
| Records acquired | Throughput giao nhận |
| Delivery count distribution | Phát hiện record bị giao nhiều lần |
| ACCEPT/RELEASE/REJECT count | Hiểu kết quả xử lý |
| Archived record count | Phát hiện record vượt delivery limit hoặc bị từ chối |
| Acquisition/lock expiry | Consumer có giữ record quá lâu không |
| Processing latency | Record có vượt timeout nghiệp vụ không |
| DLT publish success/failure | Dữ liệu lỗi có được lưu bền vững không |
| Retry topic depth/age | Retry backlog có tăng không |
| Duplicate event ID | Side effect hoặc publish có bị lặp không |
| Consumer count and throughput | Mức song song và phân phối tải |
| Per-partition completion skew | Một partition/key có bị nghẽn không |

Log nên có group ID, consumer ID, topic, partition, offset, key/event ID, delivery count, acknowledgment type và exception class. Tránh log raw payload không giới hạn vì có thể chứa dữ liệu cá nhân hoặc secret.

### Cảnh báo nên có

- Delivery count vượt ngưỡng cảnh báo.
- Archived records tăng khác thường.
- RELEASE rate tăng cao kéo dài.
- DLT publish thất bại.
- Acquisition lock hết hạn tăng.
- Một event ID được xử lý lặp nhiều lần.
- Retry topic có record quá tuổi SLO.
- Tỷ lệ ACCEPT giảm trong khi input throughput không giảm.

## 16. Bảo mật và quyền vận hành

Share Group có resource và quyền ACL riêng theo phiên bản Kafka. Ứng dụng cần quyền consume/share trên topic và share group theo cơ chế authorizer của cluster; công cụ vận hành cần quyền xem trạng thái và quản lý resource tương ứng.

Các nguyên tắc:

- Dùng principal riêng cho mỗi service/share group.
- Chỉ cấp quyền trên topic và share group cần thiết.
- Không dùng super user cho consumer runtime.
- DLT/retry topics cần ACL ghi/đọc riêng.
- Bảo vệ thông tin event và payload lỗi theo cùng phân loại dữ liệu của topic nguồn.
- Audit các thao tác thay đổi cấu hình delivery limit và quyền share group.

Tên operation/resource ACL và hỗ trợ của Share Group thay đổi theo phiên bản Kafka. Hãy đối chiếu tài liệu broker/client đang triển khai và kiểm tra authorization error thực tế trước khi cấp quyền rộng.

## 17. Kiểm thử chiến lược lỗi

Kiểm thử cần bao phủ cả xử lý thành công, retry, DLT và crash window:

1. Gửi một record hợp lệ và xác minh consumer ACCEPT.
2. Gây lỗi database transient, RELEASE và xác minh record có thể được acquire lại.
3. Gửi payload không hợp lệ, publish DLT thành công rồi REJECT.
4. Làm DLT broker/topic không khả dụng và xác minh consumer không REJECT record nguồn.
5. Dừng consumer sau side effect nhưng trước ACCEPT; xác minh record được giao lại và inbox/idempotency ngăn side effect trùng.
6. Để acquisition lock hết hạn trong lab; xác minh record có thể được consumer khác nhận.
7. Tạo poison record và quan sát delivery count/maximum delivery count.
8. Xác minh record vượt giới hạn được xử lý theo archive policy và dữ liệu không bị mất khỏi quy trình điều tra.
9. Gửi record cùng aggregate với thời gian xử lý khác nhau; kiểm tra ordering và version guard.
10. Kiểm thử retry topic, DLT replay và deduplication.

Không cố ý làm cạn disk, purge log hoặc thay đổi delivery limit trên cluster production để thử nghiệm.

## 18. Runbook xử lý poison record

Khi phát hiện một record có delivery count tăng liên tục:

1. Ghi nhận share group, topic, partition, offset, event ID và delivery count.
2. Xác định consumer nào đã acquire và exception gần nhất.
3. Phân loại lỗi transient, permanent hay lỗi diện rộng.
4. Nếu transient, kiểm tra downstream health và áp dụng backoff trước RELEASE.
5. Nếu permanent hoặc hết retry budget, publish raw payload cùng metadata vào DLT.
6. Chỉ REJECT sau khi xác nhận DLT publish thành công.
7. Nếu DLT publish thất bại, giữ record trong luồng retry/release; không bỏ qua.
8. Theo dõi archived count và xác minh record không bị mất khỏi recovery process.
9. Sửa dữ liệu/schema/code hoặc dependency.
10. Replay từ DLT/retry topic có kiểm soát, giữ event ID và kiểm tra aggregate version.
11. Theo dõi duplicate, ordering và DLT backlog sau replay.

Nếu record đã bị broker archive do delivery limit trước khi ứng dụng kịp ghi DLT, cần dùng cơ chế recovery được hỗ trợ ở phiên bản Kafka hoặc tái tạo/replay từ nguồn lưu trữ/topic gốc theo runbook. Không giả định record archived tự động xuất hiện trong DLT.

## 19. Bài thực hành: Share Group retry và DLT

Tạo môi trường lab với Kafka hỗ trợ Share Groups, topic orders.events, topic orders.DLT và hai ShareConsumer instance cùng share group.

1. Cấu hình broker share group và maximum delivery count theo phiên bản lab.
2. Gửi record hợp lệ, quan sát delivery count lần đầu và ACCEPT.
3. Tạo consumer cố ý RELEASE một record; quan sát lần acquire tiếp theo và delivery count.
4. Chạy hai consumer song song, xác minh record có thể được consumer khác nhận sau RELEASE.
5. Tạo lỗi transient, áp dụng backoff và RELEASE.
6. Tạo lỗi permanent, publish DLT kèm source coordinate, event ID, delivery count và exception.
7. Xác nhận DLT publish rồi REJECT record nguồn.
8. Làm DLT publish thất bại và xác minh record nguồn không bị REJECT.
9. Mô phỏng crash sau side effect trước ACCEPT; kiểm tra inbox/unique constraint.
10. Thử delivery limit và quan sát archive behavior.
11. Replay DLT sau khi sửa lỗi và xác minh không tạo duplicate.
12. Gửi nhiều event cùng aggregate để kiểm tra out-of-order completion và sequence guard.

Chỉ chạy các tình huống lỗi có chủ ý trong môi trường lab. Trước production, xác nhận chính xác broker/client version, trạng thái hỗ trợ Share Groups và hành vi delivery limit của release đang dùng.

## 20. Checklist production

- Xác nhận Kafka broker và kafka-clients hỗ trợ Share Groups ở mức maturity phù hợp.
- Xác định rõ group ID, topic scope và quyền ACL.
- Định nghĩa xử lý thành công, transient failure và permanent failure.
- Dùng ACCEPT chỉ sau khi side effect hoàn tất.
- Dùng RELEASE cho retry có giới hạn và backoff.
- Dùng REJECT sau khi đã quarantine/DLT hoặc xác định rõ không cần retry.
- Đặt maximum delivery count theo outage budget và retry policy.
- Theo dõi delivery count, archived records, lock expiry và DLT.
- Giữ event ID/source coordinate để deduplicate.
- Thiết kế consumer idempotent trước crash window.
- Không giả định Share Group bảo đảm ordering như consumer group truyền thống.
- Dùng sequence/version nếu nghiệp vụ cần ordering theo aggregate.
- Không giữ record acquired trong lúc chờ backoff dài.
- Bảo đảm DLT publish thành công trước khi REJECT.
- Có quy trình replay cho record DLT và record đã archived.
- Bảo vệ raw payload và secret trong log/DLT.
- Kiểm thử lỗi DLT, crash, lock expiry, delivery limit và duplicate trước production.

## 21. Những nhầm lẫn thường gặp

- **Delivery count là consumer restart count:** delivery count đo số lần record được giao/acquire, không phải số lần process khởi động.
- **RELEASE đồng nghĩa retry sau một khoảng delay:** RELEASE làm record có thể được giao lại; delayed retry cần backoff hoặc retry topic phù hợp.
- **REJECT giống RELEASE:** REJECT loại record khỏi luồng giao bình thường; RELEASE cho phép giao lại.
- **Maximum delivery count tự tạo DLT:** giới hạn broker bảo vệ khỏi retry vô hạn; DLT phải được ứng dụng/pipeline tạo riêng.
- **Broker archive record nghĩa là payload đã được lưu để điều tra:** archive state không thay thế bản sao DLT.
- **ACCEPT trước rồi mới cập nhật DB:** có thể làm mất xử lý nếu DB thất bại sau acknowledgment.
- **REJECT ngay khi DB timeout:** timeout có thể transient; reject sai làm record không được giao lại.
- **RELEASE liên tục không cần backoff:** có thể tạo hot loop và tăng tải.
- **Một record luôn được consumer cũ nhận lại:** sau release hoặc lock expiry, consumer khác có thể acquire record.
- **Share Group giữ thứ tự hoàn tất theo partition:** nhiều consumer có thể xử lý song song và hoàn tất out of order.
- **Không cần idempotency vì broker theo dõi acknowledgment:** crash giữa side effect và ACCEPT vẫn có thể tạo duplicate.
- **DLT publish và REJECT luôn atomic:** cần kiểm tra transaction support; nếu không atomic, phải deduplicate.

Delivery count, acknowledgment và maximum delivery count là các cơ chế cốt lõi để Share Groups xử lý record lỗi mà không buộc cả partition dừng lại. Dùng ACCEPT sau xử lý thành công, RELEASE cho lỗi có thể phục hồi và REJECT cho record đã được quarantine hoặc không cần giao lại. Kết hợp retry có backoff, DLT bền vững, idempotency, ordering theo aggregate và monitoring delivery/archival sẽ giúp hệ thống tận dụng work sharing mà vẫn kiểm soát được poison record và rủi ro mất dữ liệu.
