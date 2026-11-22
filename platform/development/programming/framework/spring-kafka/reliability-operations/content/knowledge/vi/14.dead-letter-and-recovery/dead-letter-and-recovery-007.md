# Failure headers tích lũy

Trong hệ thống Spring Kafka, một record xử lý thất bại có thể trải qua nhiều chặng: listener chính, retry topic, dead-letter topic (DLT), rồi một luồng recovery hoặc parking topic. Mỗi lần chuyển tiếp, ứng dụng có thể gắn thêm **failure headers** mô tả lỗi và nguồn gốc của record. Vì Kafka cho phép nhiều header có **cùng tên**, metadata lỗi có thể tích lũy qua các lần publish.

Việc tích lũy mang lại lịch sử chẩn đoán hữu ích, nhưng cũng có mặt trái: header lặp, stack trace lớn, khó xác định lỗi mới nhất, và nguy cơ record vượt giới hạn kích thước khi chuyển tiếp nhiều lần. Spring Kafka cung cấp cơ chế để quyết định giữ hay loại bỏ những header exception trước đó. Đây là một phần quan trọng của thiết kế **Dead letter và recovery**, đặc biệt khi record có thể bị replay hoặc di chuyển qua nhiều DLT.

## 1. Failure headers xuất hiện trong luồng nào?

Xét dịch vụ nhận sự kiện thanh toán từ `payments.requested`. Listener gọi một dịch vụ phụ thuộc, gặp timeout và retry. Sau khi hết số lần thử, error handler dùng `DeadLetterPublishingRecoverer` phát record sang DLT:

```text
payments.requested
    |
    | listener lỗi; retry theo backoff
    v
DefaultErrorHandler
    |
    | hết retry -> DeadLetterPublishingRecoverer
    v
payments.requested.DLT
    |
    | bộ phận recovery đọc, sửa hoặc xử lý lại
    v
payments.requested.parking   (nếu tổ chức có luồng parking)
```

Khi chuyển sang DLT, Spring Kafka có thể đính kèm các Kafka headers chứa thông tin **exception**, topic/partition/offset nguồn và những metadata liên quan đến record gốc. Nếu consumer DLT lại thất bại rồi được publish tới một DLT hoặc parking topic khác, hệ thống có thể thêm bộ thông tin mới.

Không phải mọi loại retry đều sinh thêm bộ failure headers như nhau. **Blocking retry** có thể xử lý lại trên cùng topic trước khi publish DLT; **non-blocking retry** chuyển record qua retry topic và có các header điều phối riêng. Cách xử lý header phụ thuộc vào framework, cấu hình recoverer và phiên bản Spring Kafka.

## 2. Kafka headers có thể chứa nhiều giá trị cùng tên

Kafka headers là một tập các cặp `key -> byte[]`, không phải một `Map<String, String>` có khóa duy nhất. Mỗi header có tên và giá trị byte; nhiều phần tử có thể cùng tên.

Ví dụ một record đã đi qua hai bước recovery có thể mang các header với tên giống nhau:

```text
X-Correlation-Id         = 8fa2...        (do producer gốc cung cấp)
kafka_dlt-original-topic = payments.requested
kafka_dlt-exception-fqcn  = java.net.SocketTimeoutException
kafka_dlt-exception-fqcn  = java.lang.IllegalStateException
```

Các tên ở ví dụ thể hiện ý tưởng. Trong code Java, nên dùng các hằng `KafkaHeaders.DLT_*` của phiên bản Spring Kafka đang chạy thay vì hard-code chuỗi header nội bộ.

Kafka API cung cấp hai cách truy cập khác nhau:

```java
Header latest = record.headers().lastHeader(headerName);

Iterable<Header> all = record.headers().headers(headerName);
```

- `lastHeader(name)` lấy phần tử cuối cùng có tên tương ứng trong danh sách headers. Nó không suy luận đâu là lỗi quan trọng nhất về mặt nghiệp vụ.
- `headers(name)` cho phép duyệt tất cả các phần tử cùng tên theo thứ tự chúng xuất hiện.
- `remove(name)` xóa các header có tên đó trong một tập `Headers` có thể chỉnh sửa; việc xóa trên record đã deserialize không tự làm thay đổi record đang lưu trong Kafka.

Vì vậy, khi một record mang nhiều failure headers, người đọc phải quyết định mình cần **lỗi gần nhất**, **lỗi gốc** hay **toàn bộ lịch sử**. Dùng một hàm chuyển headers thành `Map<String, String>` có thể làm mất các giá trị trùng tên mà không hề báo lỗi.

## 3. Các nhóm header thường gặp khi publish DLT

`DeadLetterPublishingRecoverer` có thể gắn các header tiêu chuẩn của Spring Kafka để ghi nhận lỗi và xuất xứ. Các tên hằng thường gặp bao gồm:

| Nhóm | Hằng Spring Kafka | Ý nghĩa |
|---|---|---|
| Exception | `KafkaHeaders.DLT_EXCEPTION_FQCN` | Tên đầy đủ của lớp exception. |
| Exception | `KafkaHeaders.DLT_EXCEPTION_CAUSE_FQCN` | Tên lớp nguyên nhân lỗi, khi có. |
| Exception | `KafkaHeaders.DLT_EXCEPTION_MESSAGE` | Thông điệp exception. |
| Exception | `KafkaHeaders.DLT_EXCEPTION_STACKTRACE` | Stack trace hỗ trợ điều tra. |
| Nguồn record | `KafkaHeaders.DLT_ORIGINAL_TOPIC` | Topic nguồn được recoverer ghi nhận. |
| Nguồn record | `KafkaHeaders.DLT_ORIGINAL_PARTITION` | Partition nguồn. |
| Nguồn record | `KafkaHeaders.DLT_ORIGINAL_OFFSET` | Offset nguồn. |
| Nguồn record | `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP` | Timestamp nguồn. |
| Nguồn record | `KafkaHeaders.DLT_ORIGINAL_TIMESTAMP_TYPE` | Loại timestamp của record nguồn. |

Tùy phiên bản và tình huống lỗi, cũng có thể có các header riêng cho lỗi deserialize **key** hoặc **value**, cùng những header phục vụ retry-topic. Không phải mọi header trong bảng đều luôn xuất hiện: ví dụ exception không có cause thì cause metadata có thể không được tạo.

Lưu ý **kiểu dữ liệu**: các header text như exception class hoặc message thường được biểu diễn bằng byte UTF-8, còn một số header số như partition/offset được mã hóa dạng nhị phân. Không giải mã mọi header bằng `new String(bytes, UTF_8)` rồi giả định kết quả đúng.

## 4. Vì sao failure headers tích lũy?

Một lần chuyển tiếp sang DLT thường bắt đầu từ record nguồn đã chứa headers. Recoverer tạo producer record mới, mang theo metadata phù hợp và thêm các header ghi nhận sự cố hiện tại.

Khi record DLT tiếp tục đi qua một recovery pipeline và lại được publish bằng recoverer, có hai dạng tích lũy cần phân biệt:

1. **Thông tin nguồn gốc**: record có thể chứa metadata nguồn ở nhiều chặng, giúp truy ngược từ DLT/parking tới topic đầu tiên và topic gần nhất.
2. **Thông tin exception**: mỗi chặng có thể phát sinh exception khác nhau; nếu giữ tất cả, các header exception lặp lại dưới cùng tên và payload header tăng dần.

Ví dụ một chuỗi thất bại:

```text
Chặng 1: payments.requested
    lỗi: Timeout gọi payment gateway
    -> payments.requested.DLT

Chặng 2: consumer của payments.requested.DLT
    lỗi: Không thể xác thực payload để replay
    -> payments.requested.parking

Record ở parking có thể còn thông tin của cả hai chặng
nếu cấu hình giữ các header trước đó.
```

Header đầu tiên không nhất thiết mô tả sự cố hiện tại. Ngược lại, header cuối cùng có thể chỉ nói về sự cố ở recovery listener, trong khi nguyên nhân gốc nằm ở lần xử lý trước. Cần thiết kế rõ ý nghĩa của từng trường và chính sách lưu lịch sử.

## 5. Hai tùy chọn quan trọng của DeadLetterPublishingRecoverer

Spring Kafka cung cấp các tùy chọn nhằm kiểm soát việc giữ lại metadata khi một record đã có DLT headers tiếp tục được recover:

- `setAppendOriginalHeaders(boolean)`: điều chỉnh việc bổ sung tiếp các header thể hiện thông tin nguồn gốc vào record chuyển tiếp.
- `setStripPreviousExceptionHeaders(boolean)`: điều chỉnh việc loại bỏ các exception headers từ lần recover trước trước khi thêm thông tin exception mới.

Tên phương thức và giá trị mặc định cần được kiểm tra theo phiên bản Spring Kafka đang sử dụng; các bản phát hành có thể khác nhau về defaults và cách xử lý một số loại header. Hai lựa chọn trên đặc biệt có ý nghĩa khi **DLT được publish lại** hoặc một record trải qua nhiều recovery stage.

Ví dụ cấu hình recoverer để tránh cộng dồn thông tin exception cũ:

```java
@Bean
DefaultErrorHandler deadLetterErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    recoverer.setAppendOriginalHeaders(false);
    recoverer.setStripPreviousExceptionHeaders(true);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L));
}
```

Đây là một cấu hình minh họa cho **listener không chạy trong container transaction**. Với transactional listener, cần chọn cơ chế xử lý exception/rollback tương thích, chẳng hạn after-rollback processor được cấu hình phù hợp; không tự chuyển nguyên cấu hình non-transactional sang container có transaction.

Trong một pipeline đơn giản chỉ có **main -> DLT**, khác biệt giữa giữ và strip exception cũ có thể chưa rõ. Nó nổi bật khi record đã qua DLT một lần rồi tiếp tục được publish sang DLT khác hoặc parking topic.

### 5.1. appendOriginalHeaders

Khi bổ sung các `DLT_ORIGINAL_*` headers ở mỗi chặng, record có thể mang nhiều dấu mốc nguồn. Điều này giúp truy ngược đường đi, nhưng cũng yêu cầu người đọc phân biệt nguồn ban đầu với nguồn của lần recover gần nhất.

Nếu tắt việc append thêm original headers, metadata nguồn có thể gọn hơn. Tuy nhiên, phải xác định cách bảo tồn nguồn ban đầu khi hệ thống còn cần nó cho replay và audit. Đừng tự giả định rằng mọi dấu vết nguồn vẫn được giữ khi một consumer khác tạo producer record mới và chỉ chọn một phần headers để chuyển tiếp.

### 5.2. stripPreviousExceptionHeaders

Khi strip các exception headers cũ, record chuyển tiếp tập trung vào exception vừa xảy ra. Đây là lựa chọn hữu ích nếu mục tiêu là tránh các stack trace dài bị nhân lên qua nhiều lần recovery.

Nếu muốn giữ lịch sử lỗi đầy đủ, có thể chọn không strip exception headers, nhưng cần kiểm soát lượng dữ liệu và cách đọc. Đặc biệt, đừng coi mọi bản sao `DLT_EXCEPTION_MESSAGE` đều là cùng một lỗi; chúng có thể tới từ các chặng khác nhau.

### 5.3. So sánh hai hướng lưu metadata

| Chính sách | Lợi ích | Điều cần lưu ý |
|---|---|---|
| Giữ exception history | Có dấu vết nhiều lần thất bại ngay trong record | Header lớn, khó phân biệt lỗi gốc/lỗi cuối, có thể lộ dữ liệu trong stack trace. |
| Chỉ giữ exception mới nhất | Record gọn và dễ chẩn đoán trạng thái hiện tại | Có thể mất lịch sử lỗi nếu không ghi lại ở log/trace hoặc kho audit. |
| Giữ original provenance có kiểm soát | Replay dễ truy ngược nguồn | Cần quy định rõ trường nào là nguồn gốc ban đầu, trường nào là chặng hiện tại. |
| Chỉ dùng custom summary headers | Dễ truy vấn theo các nhãn lỗi ngắn | Cần tự quản lý versioning, format và tính nhất quán của metadata. |

## 6. Đọc đầy đủ các failure headers trong DLT listener

Khi debug, nên bắt đầu bằng cách kiểm tra **số lượng giá trị của cùng một header**, rồi mới quyết định nên hiển thị giá trị nào. Ví dụ sau đọc các exception class đã được lưu trong record:

```java
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.common.header.Header;
import org.apache.kafka.common.header.Headers;
import org.springframework.kafka.support.KafkaHeaders;

public final class FailureHeaderReader {

    private FailureHeaderReader() {
    }

    public static List<String> exceptionClasses(Headers headers) {
        List<String> result = new ArrayList<>();

        for (Header header :
                headers.headers(KafkaHeaders.DLT_EXCEPTION_FQCN)) {
            byte[] value = header.value();
            if (value != null) {
                result.add(new String(value, StandardCharsets.UTF_8));
            }
        }

        return result;
    }

    public static String latestExceptionClass(Headers headers) {
        Header latest =
                headers.lastHeader(KafkaHeaders.DLT_EXCEPTION_FQCN);

        return latest == null || latest.value() == null
                ? null
                : new String(latest.value(), StandardCharsets.UTF_8);
    }
}
```

Listener DLT có thể gọi hai hàm này để ghi nhận số entry và exception gần nhất:

```java
@KafkaListener(topics = "payments.requested.DLT")
public void onDeadLetter(ConsumerRecord<String, PaymentEvent> record) {
    List<String> classes =
            FailureHeaderReader.exceptionClasses(record.headers());

    String latest =
            FailureHeaderReader.latestExceptionClass(record.headers());

    log.warn("DLT record topic={} partition={} offset={} "
                    + "exceptionHeaderCount={} latestException={}",
            record.topic(), record.partition(), record.offset(),
            classes.size(), latest);

    recoveryService.handle(record);
}
```

Trong production, tránh log toàn bộ exception message, stack trace hoặc payload cho mọi record nếu chúng có thể chứa thông tin nhạy cảm. Nếu cần dữ liệu điều tra chi tiết, hãy dùng lưu trữ và phân quyền phù hợp.

## 7. Hiểu header gốc và header hiện tại

Sau nhiều lần chuyển tiếp, một record có ít nhất ba khái niệm cần được tách bạch:

| Khái niệm | Ví dụ | Mục đích |
|---|---|---|
| Nguồn ban đầu | `payments.requested`, partition 2, offset 105 | Truy xuất record nghiệp vụ gốc. |
| Chặng hiện tại | `payments.requested.DLT`, partition 2, offset 41 | Biết consumer hiện tại đọc từ đâu. |
| Lỗi gần nhất | `IllegalStateException` tại recovery listener | Chẩn đoán vì sao chặng hiện tại thất bại. |

Các trường `ConsumerRecord.topic()`, `partition()` và `offset()` luôn nói về **record hiện đang được đọc**, không phải record ban đầu. Muốn tìm nguồn ban đầu phải đọc provenance headers hoặc một định danh sự kiện ổn định đi cùng payload.

Khi dùng `DLT_ORIGINAL_PARTITION` hoặc `DLT_ORIGINAL_OFFSET`, nhớ rằng các giá trị số được mã hóa dạng byte. Nếu cần giải mã, dùng API/serializer tương thích với định dạng mà Spring Kafka ghi. Không nối chuỗi trực tiếp từ byte thô rồi diễn giải thành partition hoặc offset.

Một kiến trúc có nhiều hop nên định nghĩa riêng **business event ID** hoặc **correlation ID** từ producer gốc. Các trường này giúp liên kết record ở nhiều topic dù Kafka offset và partition thay đổi qua mỗi lần publish.

## 8. Deserialization failure và raw payload

Không phải mọi lỗi bắt đầu trong phương thức listener. Một record có thể không được deserialize thành Java object vì JSON sai định dạng, schema không tương thích hoặc serializer thay đổi.

Khi cấu hình `ErrorHandlingDeserializer`, Spring Kafka có thể chuyển thông tin lỗi deserialization vào headers để error handler và recoverer xử lý. Đối với lỗi này, cần đặc biệt cẩn thận:

- Payload object có thể chưa được tạo thành công; listener có thể không được gọi.
- Raw bytes của key/value có thể cần được đưa tới DLT để điều tra hoặc replay.
- Header lỗi deserialization có thể chứa thông tin exception được serialize theo định dạng nội bộ.
- Cấu hình producer gửi DLT phải hỗ trợ dữ liệu thực tế được recoverer phát, có thể là raw bytes thay vì object Java thông thường.

Không giả định rằng mọi failure header đều là UTF-8 hoặc có thể công khai qua log. Với dữ liệu deserialize lỗi, hãy dùng handler/recoverer được Spring Kafka hỗ trợ và quy trình cách ly phù hợp thay vì tự giải mã tất cả các byte trong header.

## 9. Custom headers và việc thay thế giá trị cũ

Ngoài header tiêu chuẩn, ứng dụng thường muốn lưu metadata ngắn, dễ tìm kiếm:

```text
x-correlation-id = c8d7c5...
x-first-failed-at = 2026-11-15T12:00:00Z
x-last-failure-stage = inventory-lookup
x-failure-category = TRANSIENT_DEPENDENCY
x-recovery-owner = order-platform
```

Các header dạng `x-*` trên là quy ước ứng dụng, không phải các header Kafka/Spring Kafka tự cung cấp. Có thể bổ sung chúng qua `headersFunction` của recoverer hoặc qua publisher riêng của pipeline, tùy thiết kế.

Khi thêm header tên đã tồn tại, Kafka thường lưu thêm một entry cùng tên. Nếu mục tiêu là lưu **một giá trị mới nhất**, hãy dùng cách ghi header có chủ đích: loại bỏ giá trị trước đó ở producer record đang tạo, hoặc dùng cơ chế single-value/replacement header mà phiên bản Spring Kafka hỗ trợ. Không chỉ gọi `headers.add("x-last-failure-stage", value)` rồi nghĩ rằng giá trị cũ đã bị ghi đè.

Một thiết kế nhất quán có thể chia custom headers thành hai nhóm:

- **Immutable**: `x-event-id`, `x-correlation-id`, `x-first-failed-at`; đặt một lần rồi chuyển tiếp nguyên vẹn.
- **Mutable/current state**: `x-last-failure-stage`, `x-last-error-code`, `x-recovery-attempt`; thay thế theo chính sách rõ ràng mỗi chặng.

Nếu cần giữ toàn bộ history nhiều chặng, cân nhắc một audit store riêng. Không nhất thiết phải nhét mọi stack trace hoặc trạng thái xử lý vào Kafka headers.

## 10. Kích thước header và giới hạn message

Kafka headers nằm trong record được lưu trữ và truyền qua broker. Mỗi lần thêm exception stack trace hoặc nhiều bản metadata nguồn, record có thể tăng kích thước đáng kể.

Ví dụ minh họa, nếu mỗi lần recover gắn thêm 8 KB stack trace và record đi qua 20 chặng mà không strip metadata cũ, riêng phần stack trace có thể chiếm khoảng 160 KB, chưa kể key/value, các headers khác và overhead mã hóa.

Hậu quả có thể gồm:

- Record vượt giới hạn kích thước request/message ở producer, broker hoặc topic, khiến thao tác publish retry/DLT thất bại.
- Tăng network traffic và dung lượng lưu trữ, nhất là khi lượng record lỗi lớn.
- Tăng chi phí ghi log và vận hành nếu hệ thống xuất tất cả headers thành trace/log.
- Dữ liệu exception chứa thông tin nội bộ hoặc dữ liệu cá nhân được sao chép qua nhiều topic.

Không nên chữa bằng cách tăng mọi giới hạn message size. Hãy giải quyết nguyên nhân tích lũy, rút gọn metadata và giới hạn số lần chuyển tiếp. Nếu cần full stack trace, lưu một lần trong log hoặc hệ thống quan sát với correlation ID để truy xuất khi điều tra.

## 11. Hành vi khác nhau giữa blocking retry và retry topic

**Blocking retry** qua `DefaultErrorHandler` thường thử xử lý lại record trước khi recovery. Exception headers DLT thường được thêm khi recoverer thực sự phát record sang topic đích, chứ không nhất thiết thêm cho mỗi lần listener thất bại trong cùng một poll.

**Non-blocking retry** qua `@RetryableTopic` tạo các retry destination và thông tin cần thiết để điều phối số lần thử, độ trễ, routing. Một record có thể được publish nhiều lần qua các retry topic trước khi vào DLT. Framework có thể cập nhật những header liên quan đến retry attempt và timestamp; cách dùng header exception và DLT có thể khác so với cấu hình recoverer thủ công.

Vì vậy, không dựa vào số lượng `DLT_EXCEPTION_FQCN` để tính chính xác **số lần retry**. Một retry trong cùng container có thể không tạo header mới, trong khi một lần re-publish DLT lại có thể thêm nhiều header ở cùng bước. Muốn theo dõi số lần thử, hãy sử dụng API delivery-attempt hoặc retry metadata mà cơ chế retry cụ thể cung cấp, và đo thực tế trên topology đang chạy.

## 12. Chọn chính sách giữ lịch sử theo yêu cầu recovery

Không có một chính sách header phù hợp cho mọi pipeline. Hãy phân loại yêu cầu trước:

| Yêu cầu | Chính sách gợi ý |
|---|---|
| Consumer DLT chỉ cần biết lỗi hiện tại | Strip exception cũ và giữ một bộ lỗi mới nhất. |
| Muốn truy ra record ở topic nghiệp vụ gốc | Giữ event ID và provenance ổn định; xác định cách bảo tồn original headers. |
| Cần audit qua nhiều lần retry/recovery | Lưu lịch sử ngắn hoặc ghi sự kiện audit riêng, có giới hạn kích thước. |
| Record có nguy cơ chứa payload nhạy cảm | Không nhân bản stack trace/header chứa dữ liệu nhạy cảm qua nhiều topic. |
| DLT được tự động replay nhiều vòng | Có giới hạn replay, marker và chính sách thay thế failure headers. |
| Nhiều service cùng xử lý một record lỗi | Dùng correlation ID chung và trường owner/stage rõ ràng. |

Nếu dùng nhiều pipeline recovery, hãy ghi lại hợp đồng headers cho từng chặng. Ví dụ, `x-event-id` không đổi; `x-last-failure-stage` luôn biểu diễn chặng mới nhất; các header gốc được lưu một lần; exception tiêu chuẩn được giữ theo cấu hình strip/append đã thống nhất.

## 13. Quy trình quan sát failure headers trong production

Khi một DLT bắt đầu tăng nhanh hoặc xuất hiện record publish thất bại do kích thước, điều tra theo thứ tự:

1. Xác định topic hiện tại, partition và offset của record lỗi.
2. Đọc các headers theo **danh sách entry**, tránh chuyển ngay sang map làm mất header trùng tên.
3. Đếm số `DLT_EXCEPTION_*` và `DLT_ORIGINAL_*` entries, xác định những tên lặp lại.
4. Phân biệt lỗi đầu tiên, lỗi gần nhất và lỗi của recovery listener.
5. Kiểm tra cấu hình `DeadLetterPublishingRecoverer`, gồm chính sách append original và strip previous exception.
6. Đối chiếu luồng chuyển tiếp của record: main, retry topic, DLT, parking hoặc replay.
7. Đo kích thước record và mức độ đóng góp của stack trace/header lớn.
8. Xác định record còn có thể tiếp tục được replay hay cần cách ly để điều tra thủ công.

Metrics hữu ích gồm số record vào từng DLT, số lần publish thất bại, retry attempt, số record replay, kích thước record tại các topic recovery và lỗi vượt giới hạn message size. Các metric cần được gắn theo topic/service và phân loại lỗi ở mức có cardinality kiểm soát.

Khi điều tra ở production, giữ quyền truy cập DLT và log phù hợp. Stack trace có thể chứa tên class nội bộ, URL phụ thuộc hoặc thông tin nhạy cảm trong message; tránh sao chép toàn bộ header sang hệ thống dashboard công khai.

## 14. Kiểm thử hành vi tích lũy headers

Kiểm thử tích hợp với Embedded Kafka hoặc Kafka Testcontainers giúp xác nhận cách phiên bản Spring Kafka đang dùng thực sự thêm và loại bỏ headers. Đây là cách đáng tin cậy hơn việc giả định kết quả từ một mô tả chung.

Các kịch bản nên có:

1. Gửi record hợp lệ nhưng làm listener ném exception; xác nhận record đi tới DLT và có các failure headers cần thiết.
2. Đọc record DLT rồi publish lại bằng recoverer; xác nhận số header cùng tên khi cấu hình giữ exception cũ.
3. Lặp lại với `setStripPreviousExceptionHeaders(true)`; xác nhận metadata lỗi cũ không tiếp tục cộng dồn như trước.
4. Kiểm tra `setAppendOriginalHeaders(false)` khi record qua nhiều hop; xác nhận provenance cần cho replay được bảo tồn theo thiết kế.
5. Gắn hai custom headers có cùng tên; kiểm tra khác biệt giữa `headers(name)` và `lastHeader(name)`.
6. Gây lỗi deserialization; xác nhận dữ liệu lỗi và raw key/value vẫn được xử lý an toàn tại DLT.
7. Tạo record có stack trace lớn hoặc nhiều lần replay; quan sát cách hệ thống phản ứng khi vượt giới hạn message size.
8. Tạo exception trong recovery listener; xác nhận lỗi hiện tại không bị nhầm thành lỗi nghiệp vụ ban đầu.

Đặt assertion dựa trên **giá trị thật** của header, số lần xuất hiện và record đích. Không dựa vào thứ tự trường được in khi chuyển headers sang JSON, vì quá trình chuyển đổi có thể làm mất thông tin trùng tên.

## 15. Những sai lầm dễ gặp

- **Coi headers là map có một giá trị cho mỗi tên:** lịch sử lỗi có thể bị mất khi deserialize metadata.
- **Dùng `lastHeader()` như lịch sử lỗi đầy đủ:** chỉ nhận được giá trị cuối, không cho biết các lần thất bại trước.
- **Cho rằng mọi lần retry đều tạo một bộ DLT exception headers:** hành vi tùy retry mechanism và thời điểm publish.
- **Luôn giữ mọi stack trace:** header ngày càng lớn qua các lần recovery, dẫn tới publish failure và tăng chi phí.
- **Xóa toàn bộ headers khi muốn gọn:** có thể mất correlation ID, event ID và provenance thiết yếu cho replay.
- **Nhầm original topic với current topic:** `ConsumerRecord.topic()` là topic đang đọc, có thể là DLT chứ không phải nguồn đầu tiên.
- **Đọc partition/offset như chuỗi UTF-8:** dữ liệu số có thể được mã hóa nhị phân.
- **Retry vô hạn record lỗi trong DLT:** dễ tạo vòng lặp re-publish và header tích lũy không kiểm soát.
- **Không kiểm tra phiên bản Spring Kafka:** default append/strip và tập header của framework có thể thay đổi.
- **Ghi nguyên header lỗi vào log không kiểm soát:** có thể lộ payload nhạy cảm và làm hệ thống logging quá tải.

## 16. Nguyên tắc thiết kế recovery có thể vận hành lâu dài

Một luồng dead-letter tốt cần giữ đủ thông tin để xác định **record gốc, lỗi gần nhất, người sở hữu recovery và trạng thái replay**. Bắt đầu từ một định danh sự kiện ổn định, xác định rõ chính sách giữ original headers, đặt giới hạn cho exception history, và chỉ mang những metadata thực sự cần cho bước tiếp theo.

Khi cần điều tra nhiều lần thất bại, hãy lưu lịch sử có cấu trúc trong audit log hoặc kho dữ liệu phù hợp thay vì bắt Kafka headers mang toàn bộ lịch sử không giới hạn. Khi publish lại record, hãy chọn rõ trường nào được giữ, trường nào được thay thế và trường nào được bổ sung. Đặc biệt, một record đã vào DLT cần có chính sách replay hữu hạn để tránh vòng lặp không kết thúc.

**Failure headers tích lũy** là hệ quả tự nhiên của việc Kafka cho phép nhiều header cùng tên và của các pipeline có nhiều bước recovery. Nắm rõ quy tắc append, strip và cách đọc nhiều giá trị giúp hệ thống Spring Kafka giữ được dấu vết lỗi cần thiết mà vẫn kiểm soát được kích thước message, dữ liệu nhạy cảm và hành vi retry/replay.
