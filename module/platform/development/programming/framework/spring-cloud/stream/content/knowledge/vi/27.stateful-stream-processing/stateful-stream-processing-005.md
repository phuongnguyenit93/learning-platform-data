# Phân biệt event time, processing time và cấu hình TimestampExtractor

Trong xử lý luồng sự kiện, một bản ghi có thể được tạo ở một thời điểm, được Kafka nhận ở thời điểm khác và chỉ được ứng dụng xử lý sau đó. Ba mốc này không đồng nghĩa. Nếu dùng sai loại thời gian, cửa sổ thống kê, phép join theo thời gian và báo cáo độ trễ có thể cho kết quả sai, đặc biệt khi dữ liệu đến trễ hoặc được phát lại.

Kafka Streams gán một timestamp cho từng record trước khi chạy các phép toán phụ thuộc thời gian. Thành phần quyết định timestamp đó là **TimestampExtractor**. Spring Cloud Stream Kafka Streams Binder cho phép đăng ký extractor thành Spring bean và chọn bean theo từng input binding. Vì vậy, ứng dụng có thể dùng thời điểm nghiệp vụ trong payload làm event time, dùng timestamp metadata do broker gán làm ingestion time hoặc dùng đồng hồ hệ thống khi thật sự cần processing-time semantics.

## 1. Ba mốc thời gian trong một luồng sự kiện

Giả sử cảm biến ghi nhận nhiệt độ lúc 10:00:00, thiết bị gửi bản ghi lúc 10:00:03, Kafka broker ghi record vào topic lúc 10:00:04 và ứng dụng chỉ xử lý lúc 10:00:12. Một sự kiện có ít nhất ba mốc đáng quan tâm:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Thời điểm sự kiện thực sự xảy ra tại nguồn | Cảm biến đo nhiệt độ lúc 10:00:00 |
| Ingestion time | Thời điểm broker ghi record vào partition của topic | Kafka append record lúc 10:00:04 |
| Processing time | Thời điểm ứng dụng stream thực sự xử lý record | Kafka Streams xử lý lúc 10:00:12 |

Event time trả lời câu hỏi “điều gì đã xảy ra khi nào?”. Ingestion time trả lời “Kafka đã nhận và lưu sự kiện khi nào?”. Processing time trả lời “ứng dụng đã xử lý sự kiện khi nào?”.

Độ trễ có thể được tính theo các cặp mốc:

- Độ trễ gửi: ingestion time trừ event time.
- Độ trễ xử lý: processing time trừ ingestion time.
- Độ trễ đầu-cuối: processing time trừ event time.

Các phép tính này chỉ đáng tin khi đồng hồ của producer, broker và ứng dụng được đồng bộ ở mức phù hợp. Nếu thiết bị nguồn lệch đồng hồ vài phút, event time vẫn phản ánh timestamp thiết bị gửi nhưng không nhất thiết là thời điểm thực tế chính xác.

## 2. Event time và processing time khác nhau ở đâu?

**Event time** gắn với nội dung nghiệp vụ của sự kiện. Ví dụ, một đơn hàng được thanh toán lúc 09:58 nhưng do mạng chập chờn chỉ tới Kafka lúc 10:04. Nếu hệ thống tính doanh thu theo phút, khoản thanh toán vẫn thuộc phút 09:58.

**Processing time** gắn với thời điểm ứng dụng xử lý record. Trong ví dụ trên, ứng dụng xử lý lúc 10:04. Nếu tính theo processing time, doanh thu được ghi nhận vào phút 10:04.

Khác biệt này thể hiện rõ khi dữ liệu đến trễ hoặc không theo thứ tự thời gian:

- Event-time windowing nhóm sự kiện theo lúc chúng xảy ra, kể cả khi chúng đến muộn.
- Processing-time windowing nhóm sự kiện theo lúc ứng dụng nhận và xử lý.
- Khi phát lại topic từ offset cũ, processing time sẽ thay đổi theo lần chạy; event time được lưu trong dữ liệu có thể giữ nguyên.
- Khi cần phân tích nghiệp vụ lịch sử, event time thường là mốc phù hợp hơn.
- Khi cần đo tải thực tế, thời gian chờ trong hệ thống hoặc phản ứng vận hành, processing time có thể hữu ích hơn.

Không có một loại thời gian đúng cho mọi use case. Hãy chọn theo ý nghĩa của phép tính, sau đó bảo đảm producer và consumer thống nhất cách diễn giải timestamp.

## 3. Kafka còn có timestamp do broker ghi nhận

Kafka lưu timestamp trong metadata của record. Timestamp này có thể là thời gian do producer cung cấp hoặc thời gian broker append record, tùy cấu hình topic/broker.

Kafka hỗ trợ hai kiểu chính:

| Kafka timestamp type | Timestamp được lưu | Ý nghĩa khi Kafka Streams đọc |
|---|---|---|
| CreateTime | Timestamp trong ProducerRecord do producer gửi | Có thể đại diện event time nếu producer đặt nó bằng thời điểm sự kiện |
| LogAppendTime | Timestamp broker gán khi append vào partition | Đại diện ingestion time |

Thuộc tính topic là **message.timestamp.type**; giá trị broker mặc định thường được điều khiển bằng **log.message.timestamp.type**. Giá trị phổ biến là **CreateTime**. Với CreateTime, Kafka giữ timestamp producer gửi lên, trong giới hạn kiểm tra timestamp do broker cấu hình. Với LogAppendTime, broker ghi đè timestamp bằng thời điểm append.

Điểm quan trọng: CreateTime không tự động bảo đảm timestamp là thời điểm nghiệp vụ. Nếu producer không đặt timestamp theo thời điểm sự kiện, client Kafka thường dùng thời gian hiện tại khi tạo record. Khi đó CreateTime gần với thời gian producer gửi hơn là thời gian event thực sự xảy ra.

Ví dụ, producer cần đặt timestamp từ trường **occurredAt** của sự kiện nếu muốn Kafka metadata mang event time:

~~~java
Instant occurredAt = event.occurredAt();

ProducerRecord<String, OrderEvent> record =
    new ProducerRecord<>(
        "orders.created",
        null,
        occurredAt.toEpochMilli(),
        event.customerId(),
        event
    );

kafkaProducer.send(record);
~~~

Ví dụ này dùng Kafka producer trực tiếp để minh họa trường timestamp của ProducerRecord. Khi dùng Spring Cloud Stream Kafka Streams Binder, producer binding và cấu hình serialization có thể được quản lý riêng; đừng giả định payload có trường occurredAt thì Kafka record metadata cũng tự động nhận giá trị đó.

Nếu producer không thể đặt metadata theo event time, Kafka Streams có thể đọc trường timestamp trong payload bằng custom TimestampExtractor. Cách này tách ý nghĩa nghiệp vụ khỏi timestamp mặc định do producer hoặc broker gán.

## 4. Kafka Streams sử dụng timestamp như thế nào?

Kafka Streams gọi TimestampExtractor để lấy timestamp cho mỗi record đầu vào. Timestamp được dùng trong các phép toán phụ thuộc thời gian như:

- Tumbling, hopping và sliding windows.
- Session windows.
- Stream-stream joins có giới hạn thời gian.
- Tính toán stream-time và xử lý record đến sai thứ tự.
- Punctuation theo stream-time.

TimestampExtractor tạo timestamp cho record, nhưng không sắp xếp lại thứ tự Kafka log. Trong một partition, record vẫn được đọc theo offset. Event time có thể tăng, giảm hoặc đến không theo thứ tự. Kafka Streams dùng timestamp và semantics của toán tử để quyết định cửa sổ hoặc phép join, không biến topic thành một log đã được sắp xếp theo event time.

Ví dụ, cùng một partition có thể chứa:

~~~text
Offset 100: eventTime = 10:00:10
Offset 101: eventTime = 10:00:35
Offset 102: eventTime = 10:00:20
~~~

Record ở offset 102 đến sau nhưng có event time sớm hơn offset 101. Đây là out-of-order event. Nếu ứng dụng dùng event time, nó có thể vẫn cập nhật cửa sổ 10:00:00–10:01:00 nếu cửa sổ chưa hết grace period.

## 5. Stream-time là thời gian tiến triển theo dữ liệu

Kafka Streams có khái niệm **stream-time** để theo dõi tiến triển thời gian của một task. Stream-time được cập nhật dựa trên timestamp của các record được xử lý; về cơ bản nó là timestamp lớn nhất mà task đã quan sát. Đây là thời gian do dữ liệu thúc đẩy, không phải đồng hồ treo tường.

Ví dụ, task xử lý record có timestamp 10:00:10, sau đó 10:00:35, rồi nhận một record cũ hơn có timestamp 10:00:20. Stream-time vẫn là 10:00:35. Record cũ không làm thời gian của task quay ngược.

Stream-time có một đặc điểm vận hành quan trọng: nếu không có record mới, stream-time không tự tiến lên chỉ vì đồng hồ hệ thống chạy. Vì vậy, một cửa sổ event-time có thể chưa được xem là hết grace nếu luồng dữ liệu ngừng đến, dù thời gian thực đã trôi qua nhiều phút.

Processing-time dựa trên đồng hồ hệ thống có hành vi khác. Kafka Streams cũng hỗ trợ punctuation theo wall-clock-time, có thể chạy theo lịch ngay cả khi không có record mới. Hai loại thời gian này phục vụ mục đích khác nhau:

| Cơ chế | Thời gian dùng | Tiến triển khi không có record mới? |
|---|---|---|
| Event-time / stream-time | Timestamp được trích từ record | Không |
| Processing-time / wall-clock-time | Đồng hồ hệ thống | Có, với tác vụ được lập lịch theo wall-clock |

## 6. TimestampExtractor là gì?

**TimestampExtractor** là interface của Kafka Streams dùng để lấy timestamp từ một ConsumerRecord. Phương thức chính có dạng:

~~~java
long extract(ConsumerRecord<Object, Object> record, long partitionTime);
~~~

Hai tham số:

- **record**: Kafka record hiện tại, gồm topic, partition, offset, key, value, headers và timestamp metadata.
- **partitionTime**: timestamp hợp lệ cao nhất đã được trích từ một record trước đó trong cùng topic partition; giá trị có thể là **-1** nếu chưa có timestamp để tham chiếu.

Giá trị trả về phải là số mili giây tính từ Unix epoch (00:00:00 UTC ngày 01-01-1970). Kafka Streams yêu cầu timestamp dương; timestamp bằng 0 hoặc âm không được xem là hợp lệ trong API hiện hành. Một extractor cần stateless: không lưu trạng thái riêng trong field để suy luận timestamp giữa các record. Nếu cần dùng timestamp trước đó, Kafka Streams cung cấp partitionTime.

Không dùng LocalDateTime không có múi giờ làm timestamp. Chuyển thời điểm có múi giờ rõ ràng như Instant sang epoch milliseconds:

~~~java
long timestamp = event.occurredAt().toEpochMilli();
~~~

Không trả về số giây trong khi Kafka Streams mong đợi milliseconds. Ví dụ, timestamp 1.700.000.000 là mili giây thuộc năm 1970, trong khi cùng con số nếu hiểu là giây thuộc khoảng năm 2023. Sai đơn vị có thể khiến record bị đặt vào cửa sổ hoàn toàn sai.

## 7. Extractor mặc định và các extractor có sẵn

Kafka Streams mặc định dùng **FailOnInvalidTimestamp**. Extractor này đọc timestamp metadata của Kafka record. Nếu timestamp không hợp lệ (âm), nó ném exception thay vì âm thầm bỏ qua record.

Một số implementation có sẵn:

| Extractor | Cách xử lý | Trường hợp sử dụng |
|---|---|---|
| FailOnInvalidTimestamp | Đọc timestamp metadata; lỗi nếu timestamp âm | Mặc định khi muốn phát hiện dữ liệu thiếu timestamp |
| LogAndSkipOnInvalidTimestamp | Ghi cảnh báo rồi trả timestamp không hợp lệ để record bị bỏ qua | Chỉ khi chính sách chấp nhận bỏ record lỗi |
| UsePartitionTimeOnInvalidTimestamp | Dùng timestamp metadata hợp lệ; nếu không hợp lệ thì ước lượng bằng partitionTime trước đó, lỗi nếu không có giá trị trước | Dữ liệu cũ thiếu timestamp nhưng có thể chấp nhận ước lượng theo partition |
| WallclockTimestampExtractor | Trả về thời gian hiện tại của máy xử lý | Khi muốn processing-time semantics |

Cần thận trọng với **LogAndSkipOnInvalidTimestamp**. Record có timestamp âm sẽ không được xử lý; việc log warning không có nghĩa record đã được đưa vào DLQ. Nếu dữ liệu không được phép mất, hãy chọn cách xử lý có chủ đích, chẳng hạn ném lỗi để dừng pipeline và điều tra hoặc đưa record lỗi sang luồng quarantine riêng.

**UsePartitionTimeOnInvalidTimestamp** không khôi phục event time gốc. Nó chỉ dùng timestamp hợp lệ gần nhất đã quan sát trong cùng partition để ước lượng thời gian cho record thiếu timestamp. Nếu partition chưa có timestamp hợp lệ, extractor không thể ước lượng.

**WallclockTimestampExtractor** không đọc timestamp của payload hoặc metadata. Nó trả về thời gian hệ thống khi record được xử lý. Khi replay cùng một record vào ngày khác, timestamp sẽ khác và kết quả windowing theo processing time có thể thay đổi.

## 8. Viết TimestampExtractor lấy thời điểm nghiệp vụ từ payload

Giả sử sự kiện đơn hàng có cấu trúc:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderEvent(
    String eventId,
    String customerId,
    Instant occurredAt,
    BigDecimal amount
) {}
~~~

Ứng dụng cần tính số đơn hàng theo khách hàng và theo cửa sổ năm phút. Trường **occurredAt** là thời điểm nghiệp vụ cần dùng làm event time.

Custom extractor:

~~~java
import java.time.Instant;

import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.streams.errors.StreamsException;
import org.apache.kafka.streams.processor.TimestampExtractor;

public final class OrderEventTimestampExtractor
        implements TimestampExtractor {

    @Override
    public long extract(
            ConsumerRecord<Object, Object> record,
            long partitionTime) {

        Object value = record.value();

        if (!(value instanceof OrderEvent event)) {
            throw new StreamsException(
                "Expected OrderEvent in topic " + record.topic()
            );
        }

        Instant occurredAt = event.occurredAt();

        if (occurredAt == null) {
            throw new StreamsException(
                "Missing occurredAt for event " + event.eventId()
            );
        }

        long timestamp = occurredAt.toEpochMilli();

        if (timestamp <= 0) {
            throw new StreamsException(
                "Invalid event timestamp for event " + event.eventId()
            );
        }

        return timestamp;
    }
}
~~~

Extractor này có các đặc điểm:

- Lấy timestamp từ trường nghiệp vụ occurredAt, không phụ thuộc timestamp producer hoặc broker.
- Chuyển Instant thành epoch milliseconds.
- Không dùng trạng thái mutable và không phụ thuộc thứ tự gọi.
- Không tự thay timestamp lỗi bằng thời gian hiện tại.
- Ném StreamsException nếu payload hoặc thời điểm nghiệp vụ không hợp lệ để lỗi được phát hiện và xử lý theo chính sách của ứng dụng.

Trong production, cần xác định rõ chiến lược cho record không có occurredAt: fail để sửa nguồn dữ liệu, chuyển sang topic quarantine bằng cơ chế xử lý lỗi phù hợp, hoặc dùng một timestamp ước lượng nếu nghiệp vụ cho phép. Không nên âm thầm thay bằng processing time vì điều đó trộn hai semantics trong cùng một luồng.

## 9. Đăng ký extractor trong Spring Cloud Stream Kafka Streams Binder

Kafka Streams Binder cho phép đăng ký TimestampExtractor dưới dạng Spring bean. Sau đó, chọn bean bằng tên trên từng consumer input binding.

Ví dụ bean:

~~~java
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class StreamTimeConfiguration {

    @Bean
    TimestampExtractor orderEventTimestampExtractor() {
        return new OrderEventTimestampExtractor();
    }
}
~~~

Ví dụ function xử lý sự kiện:

~~~java
import java.time.Duration;
import java.util.function.Function;

import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, OrderEvent>,
        KTable<Windowed<String>, Long>> countOrders() {

    return orders -> orders
        .filter((customerId, event) -> customerId != null && event != null)
        .groupByKey()
        .windowedBy(
            TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)
            )
        )
        .count(
            Materialized
                .<String, Long, org.apache.kafka.streams.state.WindowStore<Bytes, byte[]>>
                    as("orders-by-customer-window")
        );
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: countOrders
    stream:
      bindings:
        countOrders-in-0:
          destination: orders.created
      kafka:
        streams:
          bindings:
            countOrders-in-0:
              consumer:
                timestampExtractorBeanName: orderEventTimestampExtractor
~~~

Tên input binding được tạo từ function name là **countOrders-in-0**. Thuộc tính **timestampExtractorBeanName** trỏ tới tên Spring bean. Nếu một function có nhiều input, có thể chỉ định extractor khác nhau cho từng input binding. Input không khai báo custom extractor sẽ dùng cấu hình mặc định của Kafka Streams.

Ví dụ DSL trên dùng event time từ occurredAt để nhóm sự kiện theo cửa sổ năm phút, với grace period một phút. Phần Serde cho key/value và kiểu Materialized cần được cấu hình phù hợp với dependency và phiên bản Kafka Streams của dự án. Đoạn code tập trung minh họa việc extractor cung cấp timestamp cho các phép toán windowing.

## 10. Event-time window và late-arriving event

Một sự kiện có thể đến sau khi cửa sổ event-time mà nó thuộc về đã bắt đầu hoặc thậm chí gần kết thúc. Kafka Streams dùng stream-time và grace period để quyết định còn chấp nhận record trễ hay không.

Giả sử cửa sổ năm phút bắt đầu lúc 10:00 và kết thúc lúc 10:05, grace period là một phút:

- Event có occurredAt 10:02 đến ứng dụng lúc 10:03: record được xử lý trong cửa sổ 10:00–10:05.
- Event có occurredAt 10:01 nhưng tới lúc 10:05:20: vẫn có thể được chấp nhận nếu stream-time chưa vượt qua 10:06.
- Khi stream-time đã vượt qua 10:06, record thuộc cửa sổ này được xem là quá trễ và bị loại khỏi phép tính của cửa sổ.

Grace period không phải thời gian chờ cố định tính từ lúc broker nhận record. Nó được đánh giá theo stream-time của task. Nếu không có record mới, stream-time không tự tăng theo đồng hồ hệ thống.

Sơ đồ minh họa:

~~~text
Event time:
10:00                 10:05          10:06
  |--------------------|--------------|
  <--- window 5 phút --> < grace 1 phút >

Record đến trễ có event time 10:02:
  - Trước khi stream-time vượt 10:06: có thể được chấp nhận
  - Sau khi stream-time vượt 10:06: quá trễ cho cửa sổ này
~~~

Grace period càng lớn thì hệ thống chấp nhận dữ liệu đến trễ càng lâu, nhưng state của cửa sổ phải được giữ lâu hơn và kết quả cuối cùng bị trì hoãn. Grace quá nhỏ có thể loại record hợp lệ do mạng hoặc thiết bị nguồn chậm. Hãy chọn dựa trên phân bố độ trễ thực tế của producer.

## 11. Processing time với WallclockTimestampExtractor

Khi mục tiêu là xử lý theo thời điểm ứng dụng thực sự nhận record, có thể dùng **WallclockTimestampExtractor**:

~~~java
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.apache.kafka.streams.processor.WallclockTimestampExtractor;

@Bean
TimestampExtractor processingTimeExtractor() {
    return new WallclockTimestampExtractor();
}
~~~

Cấu hình trên input binding:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            liveMetrics-in-0:
              consumer:
                timestampExtractorBeanName: processingTimeExtractor
~~~

Mỗi record nhận timestamp theo đồng hồ hệ thống khi extractor chạy. Cách này hữu ích cho một số phép đo vận hành, ví dụ gom các record theo thời điểm consumer xử lý chúng.

Tuy nhiên, có các đánh đổi:

- Cùng một record được replay vào thời điểm khác sẽ có timestamp khác.
- Windowing có thể cho kết quả khác nhau giữa lần chạy đầu và lần replay.
- Hai instance có đồng hồ lệch nhau có thể tạo timestamp không đồng nhất.
- Khi ứng dụng bị dừng và không có record mới, stream-time vẫn không tiến triển; extractor chỉ được gọi khi record được xử lý.
- WallclockTimestampExtractor không thay thế bộ lập lịch tác vụ theo wall-clock.

Nếu mục tiêu là chạy tác vụ định kỳ kể cả khi không có message, hãy dùng cơ chế scheduler hoặc Processor API punctuation theo **WALL_CLOCK_TIME**. Nếu mục tiêu là chạy khi stream-time tiến triển, dùng punctuation theo **STREAM_TIME**. Hai cơ chế này khác nhau:

~~~java
context.schedule(
    Duration.ofSeconds(30),
    PunctuationType.STREAM_TIME,
    timestamp -> {
        // Chạy khi stream-time tiến triển đủ tới mốc kế tiếp.
    }
);

context.schedule(
    Duration.ofSeconds(30),
    PunctuationType.WALL_CLOCK_TIME,
    timestamp -> {
        // Chạy theo đồng hồ hệ thống, kể cả khi stream không có record mới.
    }
);
~~~

Ví dụ punctuation thuộc Processor API; API cụ thể và cách tạo ProcessorContext phụ thuộc phiên bản Kafka Streams. Không dùng wall-clock punctuation để giả lập event-time windowing.

## 12. Xử lý timestamp không hợp lệ

Timestamp không hợp lệ (bằng 0 hoặc âm theo yêu cầu của API hiện hành) có thể xuất hiện khi:

- Producer cũ không ghi timestamp metadata.
- Producer gửi giá trị âm hoặc sai đơn vị.
- Payload thiếu occurredAt.
- Dữ liệu nguồn dùng múi giờ không rõ ràng.
- Timestamp bị lỗi khi chuyển đổi schema hoặc kiểu dữ liệu.
- Đồng hồ thiết bị nguồn bị lệch nghiêm trọng.

Các lựa chọn cần được quyết định theo nghiệp vụ:

| Chính sách | Hành vi | Rủi ro |
|---|---|---|
| Fail fast | Ném exception và dừng/để task xử lý lỗi | Có thể làm pipeline ngừng tiến triển nhưng tránh âm thầm sai số liệu |
| Log and skip | Bỏ record timestamp lỗi và ghi warning | Mất dữ liệu khỏi phép tính |
| Use partition time | Ước lượng bằng timestamp hợp lệ gần nhất trong partition | Không còn event time chính xác |
| Quarantine | Chuyển record lỗi sang luồng điều tra riêng | Cần thêm topology, quyền và quy trình xử lý |
| Wall-clock fallback | Dùng thời điểm consumer xử lý | Trộn event time và processing time; replay không xác định |

Không trả về timestamp âm để biểu diễn “không biết”. Kafka Streams có thể bỏ record mà không xử lý. Nếu không thể xác định timestamp và không chấp nhận mất dữ liệu, hãy ném lỗi hoặc đưa record vào quarantine theo thiết kế rõ ràng.

Nếu dùng partitionTime làm fallback, cần ghi nhận metric số lần fallback. Không coi giá trị ước lượng là timestamp nghiệp vụ chính xác. Nếu partition chưa từng có timestamp hợp lệ, partitionTime có thể là -1 và không thể dùng làm mốc thay thế.

## 13. Đồng hồ, múi giờ và độ lệch timestamp

TimestampExtractor trả về epoch milliseconds, tức thời điểm tính từ Unix epoch theo UTC. Trong payload, nên dùng kiểu biểu diễn có múi giờ rõ ràng như ISO-8601 có offset hoặc UTC:

~~~json
{
  "eventId": "evt-9001",
  "customerId": "customer-42",
  "occurredAt": "2026-11-24T03:15:30Z",
  "amount": 125000
}
~~~

Nếu nguồn gửi local time mà không có timezone, ứng dụng không thể biết chắc đó là UTC hay múi giờ địa phương. Hãy thống nhất schema và quy ước timezone giữa các producer.

Cần đồng bộ đồng hồ bằng NTP hoặc cơ chế tương đương. Nếu producer dùng CreateTime, Kafka broker có thể áp dụng giới hạn chênh lệch timestamp so với giờ broker và từ chối record quá xa. Nếu dùng LogAppendTime, broker thay timestamp bằng giờ append nên không còn phản ánh event time trong metadata.

Nên kiểm tra các điều kiện:

- Timestamp không ở tương lai quá xa.
- Timestamp không cũ hơn mức nghiệp vụ chấp nhận.
- Đơn vị luôn là milliseconds khi đi vào Kafka Streams.
- Không dùng LocalDateTime thiếu timezone cho dữ liệu xuyên hệ thống.
- Lưu timestamp gốc của nguồn nếu cần audit.
- Ghi nhận clock skew và tỷ lệ record bị fallback/quarantine.

## 14. Timestamp truyền qua các phép toán Kafka Streams

Timestamp không chỉ ảnh hưởng source record. Kafka Streams còn xác định timestamp cho output record dựa trên phép toán:

- Stateless transformation thường giữ timestamp của input record.
- Các phép toán tạo nhiều record từ một input thường truyền timestamp tương ứng từ input.
- Kết quả aggregation có thể mang timestamp lớn nhất của các record đóng góp vào kết quả.
- Kết quả stream-stream hoặc table-table join thường dùng timestamp lớn hơn giữa hai record đầu vào.
- Output được tạo từ punctuation có thể dùng thời gian nội bộ của task tại thời điểm punctuation.

Điều này quan trọng khi nối nhiều topology hoặc nhiều topic. Nếu một phép toán thay đổi timestamp, downstream windowing sẽ dùng timestamp mới. Khi cần giữ thời điểm nghiệp vụ ban đầu, hãy xác minh semantics của operator và có thể giữ thêm trường occurredAt trong payload để audit.

Không đồng nhất timestamp metadata của output record với mọi timestamp trong payload. Một event có thể chứa nhiều mốc: occurredAt, receivedAt, processedAt. Metadata Kafka chỉ mang một timestamp cho record; payload có thể giữ các mốc còn lại để đo độ trễ và điều tra.

## 15. TimestampExtractor và nhiều input binding

Một function Kafka Streams có thể có nhiều input binding, ví dụ:

- **process-in-0** nhận OrderEvent từ topic đơn hàng.
- **process-in-1** nhận PaymentEvent từ topic thanh toán.
- **process-in-2** nhận CustomerSnapshot từ topic khách hàng.

Mỗi input có thể cần timestamp semantics khác nhau. OrderEvent có thể dùng occurredAt, PaymentEvent dùng settledAt, còn CustomerSnapshot có thể dùng timestamp metadata của Kafka.

Spring Cloud Stream Kafka Streams Binder cho phép chọn TimestampExtractor theo từng binding. Prefix đầy đủ là **spring.cloud.stream.kafka.streams.bindings.<binding-name>.consumer**:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-0:
              consumer:
                timestampExtractorBeanName: orderTimestampExtractor
            process-in-1:
              consumer:
                timestampExtractorBeanName: paymentTimestampExtractor
~~~

Hai bean cần được khai báo trong Spring context. Nếu bỏ qua một binding, binder sử dụng timestamp extractor mặc định cho binding đó.

Khi join hai stream, timestamp semantics cần được thống nhất hoặc ít nhất phải hiểu rõ. Nếu một stream dùng event time còn stream kia dùng ingestion time, record có thể không khớp cửa sổ như kỳ vọng. Trước khi join, hãy xác định timestamp nào đại diện cho cùng một khái niệm nghiệp vụ.

## 16. Kiểm thử timestamp và windowing

Không nên chỉ unit test rằng extractor trả về một số dương. Cần kiểm tra cả hành vi của topology khi có record đến sai thứ tự và record trễ.

Có thể dùng Kafka Streams **TopologyTestDriver** để kiểm tra logic topology mà không cần broker thật. Ví dụ tạo input topic và gửi record với timestamp xác định:

~~~java
inputTopic.pipeInput(
    "customer-42",
    new OrderEvent(
        "evt-1001",
        "customer-42",
        Instant.parse("2026-11-24T03:00:10Z"),
        new BigDecimal("100000")
    ),
    Instant.parse("2026-11-24T03:00:10Z")
);
~~~

Nếu topology dùng custom extractor đọc occurredAt trong payload, timestamp truyền qua TestInputTopic không thay thế giá trị occurredAt mà extractor chọn. Test nên xác minh rõ timestamp thực sự được dùng cho windowing.

Các trường hợp nên kiểm thử:

1. Event time hợp lệ, timestamp đúng epoch milliseconds.
2. Timestamp trước Unix epoch hoặc trường occurredAt null.
3. Payload sai kiểu hoặc schema version không được hỗ trợ.
4. Hai record cùng partition đến theo thứ tự event time tăng dần.
5. Record có event time cũ đến sau record mới.
6. Record đến trong grace period được cập nhật vào cửa sổ.
7. Record đến sau khi stream-time vượt end + grace bị loại khỏi cửa sổ.
8. WallclockTimestampExtractor tạo timestamp theo thời điểm test thực thi.
9. Replay cùng dữ liệu với event time cho kết quả ổn định.
10. Nhiều input binding dùng extractor riêng và join theo cùng semantics.

TopologyTestDriver phù hợp để kiểm tra logic thời gian và cửa sổ. Integration test với Kafka broker thật vẫn cần thiết nếu muốn xác minh topic timestamp type là CreateTime hay LogAppendTime, producer có đặt metadata đúng và cấu hình binder thực sự chọn đúng extractor bean.

## 17. Quan sát độ trễ và chất lượng timestamp

Một pipeline production nên theo dõi cả độ trễ và chất lượng timestamp:

| Metric | Ý nghĩa |
|---|---|
| Event-to-ingestion delay | Khoảng cách giữa event time và ingestion time |
| Ingestion-to-processing delay | Thời gian record chờ trước khi được xử lý |
| Event-to-processing delay | Độ trễ đầu-cuối theo nghiệp vụ |
| Invalid timestamp count | Số record không có timestamp hợp lệ |
| Timestamp fallback count | Số lần dùng partitionTime hoặc fallback khác |
| Late record count | Số record bị loại vì vượt grace period |
| Stream-time lag | Chênh lệch giữa thời gian thực và stream-time đang quan sát |
| Window update latency | Thời gian từ event đến khi aggregate được cập nhật |

Khi log record lỗi, nên có topic, partition, offset, eventId, timestamp metadata và timestamp payload nếu có. Không log toàn bộ payload nhạy cảm.

Cần phân biệt late record với record đến chậm do processing backlog. Event time cũ có thể là dữ liệu hợp lệ đến trễ; processing-time lag lớn có thể do consumer không theo kịp. Hai vấn đề cần cách xử lý khác nhau.

## 18. Lựa chọn semantics theo use case

| Use case | Timestamp nên chọn | Lý do |
|---|---|---|
| Tính doanh thu theo lúc thanh toán | Event time từ settledAt | Giao dịch đến trễ vẫn thuộc đúng khoảng nghiệp vụ |
| Đếm sensor reading theo thời điểm đo | Event time từ sensor timestamp | Giữ ý nghĩa thời điểm đo ở thiết bị |
| Đo thời gian message nằm trong broker | Ingestion time và processing time | Đo backlog và độ trễ tiêu thụ |
| Dashboard tốc độ xử lý hiện tại | Processing time | Phản ánh hoạt động thực tế của consumer |
| Phát lại lịch sử để tái tính toán | Event time ổn định trong payload | Kết quả windowing có thể tái lập |
| Hệ thống nhận record từ producer không kiểm soát timestamp | LogAppendTime hoặc timestamp do gateway chuẩn hóa | Giảm phụ thuộc đồng hồ nguồn |

Nếu nghiệp vụ yêu cầu phân tích lịch sử và chấp nhận late event, event time thường là lựa chọn chính. Nếu hệ thống cần thống kê vận hành theo thời điểm nhận hoặc xử lý, ingestion/processing time phù hợp hơn. Có thể lưu đồng thời cả ba mốc trong payload hoặc telemetry để phục vụ audit và phân tích.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Window có dữ liệu lệch nhiều phút/giờ | Timestamp dùng sai timezone hoặc đơn vị giây thay vì milliseconds | Chuẩn hóa Instant/UTC và kiểm tra epoch milliseconds |
| Event đến trễ bị loại | Stream-time đã vượt end + grace | Điều chỉnh grace theo phân bố late arrival và kiểm tra timestamp extractor |
| Replay cho kết quả khác lần đầu | Dùng processing-time extractor hoặc timestamp phụ thuộc đồng hồ | Dùng event time ổn định nếu cần tái lập |
| Record bị bỏ mà không có kết quả | Extractor trả timestamp âm hoặc dùng LogAndSkipOnInvalidTimestamp | Chọn chính sách fail/quarantine và giám sát invalid timestamp |
| Join không khớp cửa sổ | Hai input dùng timestamp semantics khác nhau | Đồng bộ event-time contract cho các input |
| Timestamp mặc định không phải event time | Producer để Kafka tự gán CreateTime từ đồng hồ gửi | Đặt ProducerRecord timestamp hoặc dùng custom extractor |
| Stream-time không tiến triển khi topic im lặng | Stream-time chỉ tiến khi có record mới | Dùng wall-clock punctuation cho tác vụ theo đồng hồ |
| Event time nằm trong tương lai | Clock nguồn lệch hoặc dữ liệu sai | Kiểm tra clock skew, giới hạn timestamp và quarantine |
| Một binding dùng sai extractor | Sai tên bean hoặc sai binding name | Kiểm tra function definition và timestampExtractorBeanName |

## 20. Checklist triển khai production

- Xác định rõ timestamp nghiệp vụ cần dùng là event time, ingestion time hay processing time.
- Quy định timestamp trong schema bằng UTC/Instant hoặc epoch milliseconds.
- Nếu dùng CreateTime, bảo đảm producer đặt timestamp theo đúng ý nghĩa mong muốn.
- Nếu dùng LogAppendTime, hiểu rằng Kafka broker thay timestamp bằng thời điểm append.
- Dùng TimestampExtractor stateless và trả epoch milliseconds hợp lệ.
- Chọn chính sách timestamp lỗi: fail, skip, estimate hoặc quarantine.
- Không âm thầm trộn event time với processing time.
- Đăng ký extractor bean và gán đúng từng input binding.
- Đồng bộ timestamp semantics trước khi join nhiều stream.
- Chọn grace period theo độ trễ đến muộn thực tế.
- Theo dõi stream-time, late records, timestamp fallback và độ trễ đầu-cuối.
- Kiểm thử replay, out-of-order, invalid timestamp và window close.
- Dùng integration test để xác minh topic timestamp type và metadata thực tế của Kafka.
- Đồng bộ clock của producer, broker và consumer; bảo vệ timestamp khỏi dữ liệu tương lai hoặc quá cũ.

## 21. Tài liệu tham khảo

- [Spring Cloud Stream — Timestamp Extractor](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/timestamp-extractor.html), cách đăng ký TimestampExtractor bean và cấu hình theo input binding.
- [Spring Cloud Stream Kafka Streams Binder — Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html), thuộc tính consumer của Kafka Streams Binder.
- [Apache Kafka Streams — Core Concepts](https://kafka.apache.org/44/streams/core-concepts/), event time, processing time, ingestion time, stream-time và windowing.
- [Apache Kafka Streams — Configuring a Streams Application](https://kafka.apache.org/44/streams/developer-guide/config-streams/), default.timestamp.extractor và các extractor có sẵn.
- [Apache Kafka — TimestampExtractor API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/processor/TimestampExtractor.html), chữ ký extract, partitionTime và yêu cầu timestamp.
- [Apache Kafka — Topic Configs](https://kafka.apache.org/44/configuration/topic-configs/), message.timestamp.type và các giới hạn timestamp.

Event time mô tả thời điểm nghiệp vụ xảy ra, ingestion time mô tả lúc broker lưu record và processing time mô tả lúc ứng dụng xử lý. Kafka Streams dùng TimestampExtractor để đưa một trong các semantics đó vào stream-time và các phép toán phụ thuộc thời gian. Khi timestamp được chuẩn hóa, extractor được cấu hình đúng cho từng input binding, grace period phản ánh độ trễ thực tế và chính sách timestamp lỗi được xác định rõ, các cửa sổ và phép join sẽ cho kết quả nhất quán hơn khi dữ liệu đến trễ, sai thứ tự hoặc được phát lại.

