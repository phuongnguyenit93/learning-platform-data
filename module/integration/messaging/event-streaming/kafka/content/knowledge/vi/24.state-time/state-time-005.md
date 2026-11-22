# TimestampExtractor và dữ liệu có timestamp không hợp lệ

Trong module **KAFKA**, người học xây dựng hệ thống event streaming với Apache Kafka, hiểu topic, partition, offset, producer, consumer group, replication và KRaft; triển khai luồng sự kiện Java/Spring Kafka, xử lý retry, ordering và giao dịch; tích hợp Kafka Connect/Streams rồi giám sát, tối ưu và phục hồi cụm. Bài học này giải thích cách Kafka Streams chọn timestamp cho record bằng **TimestampExtractor**, cách xử lý timestamp thiếu hoặc sai, và ảnh hưởng của quyết định đó đến event-time processing, window, join và stateful aggregation.

Kafka Streams dùng timestamp của record để xác định thời gian xử lý trong topology. Nếu timestamp không hợp lệ, ứng dụng có thể dừng, bỏ qua record hoặc áp dụng fallback. Quyết định này ảnh hưởng trực tiếp đến kết quả nghiệp vụ: timestamp sai đơn vị có thể làm event rơi vào window sai, còn timestamp tương lai có thể đẩy stream-time tiến quá xa và khiến event đến muộn bị xem là quá hạn.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt event time, ingestion time và processing time.
- Giải thích timestamp có sẵn trong Kafka record và cách broker gán timestamp.
- Mô tả vai trò và chữ ký của TimestampExtractor.
- Hiểu ý nghĩa tham số partitionTime.
- Chọn extractor mặc định hoặc extractor tùy chỉnh.
- Phân loại timestamp thiếu, âm, sai định dạng, sai đơn vị và nằm ngoài miền hợp lệ.
- Chọn chính sách fail, skip hoặc fallback có kiểm soát.
- Viết custom TimestampExtractor đọc eventTime từ payload.
- Cấu hình extractor ở cấp Kafka Streams application hoặc từng source.
- Giải thích timestamp ảnh hưởng đến stream-time, window, grace period và late event.
- Kiểm thử timestamp hợp lệ, không hợp lệ và out-of-order bằng TopologyTestDriver.
- Giám sát tỷ lệ record bị bỏ qua, timestamp skew và lỗi xử lý thời gian.

## 2. Timestamp trong Kafka record

Mỗi Kafka record có thể chứa timestamp bên cạnh key, value, headers, topic, partition và offset. Producer có thể cung cấp timestamp khi tạo record; broker cũng có thể ghi đè timestamp theo cấu hình timestamp type.

Hai loại timestamp phổ biến:

- **CreateTime:** thời điểm do producer cung cấp hoặc client gán khi tạo record.
- **LogAppendTime:** thời điểm broker ghi record vào log.

Cấu hình message.timestamp.type ở topic hoặc log.message.timestamp.type ở broker, tùy cách cấu hình và phiên bản, quyết định timestamp được lưu theo CreateTime hay LogAppendTime.

### 2.1. CreateTime

Với CreateTime, timestamp thường phản ánh thời điểm event xảy ra hoặc thời điểm producer tạo record.

~~~text
Event xảy ra tại 10:00:00.000
Producer xử lý event tại 10:00:00.150
Producer gửi record đến Kafka
Record timestamp = 10:00:00.000 nếu producer đặt event time
~~~

CreateTime phù hợp khi hệ thống cần phân tích theo thời điểm nghiệp vụ thực sự xảy ra. Tuy nhiên, đồng hồ máy producer có thể lệch, dữ liệu có thể được replay hoặc event có thể đến trễ.

### 2.2. LogAppendTime

Với LogAppendTime, broker gán timestamp khi append record vào log.

~~~text
Event xảy ra tại 10:00:00.000
Producer gửi record tại 10:00:02.000
Broker append record tại 10:00:02.030
Record timestamp = 10:00:02.030
~~~

LogAppendTime hữu ích khi cần thời điểm Kafka tiếp nhận record. Nó không đại diện chính xác cho thời điểm event xảy ra trong hệ thống nguồn.

### 2.3. Timestamp không phải offset

Offset là vị trí record trong một partition. Timestamp là thông tin thời gian gắn với record.

- Offset tăng theo thứ tự append trong một partition.
- Timestamp có thể tăng, đứng yên hoặc giảm giữa các record.
- Hai record ở hai partition khác nhau không có một thứ tự offset chung.
- Timestamp không bảo đảm thứ tự toàn cục giữa các partition.

Ví dụ:

| Partition | Offset | Timestamp |
|---|---:|---|
| orders-0 | 100 | 10:00:05 |
| orders-0 | 101 | 10:00:03 |
| orders-1 | 50 | 10:00:04 |

Offset 101 đến sau offset 100 trong log, nhưng timestamp của nó lại sớm hơn. Đây có thể là event đến muộn hoặc đồng hồ nguồn lệch.

## 3. Event time, ingestion time và processing time

Trong hệ thống streaming, cần phân biệt ba khái niệm thời gian:

| Loại thời gian | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Thời điểm nghiệp vụ hoặc sự kiện thực sự xảy ra | Người dùng thanh toán lúc 10:00 |
| Ingestion time | Thời điểm record được tiếp nhận vào Kafka hoặc hệ thống streaming | Broker append lúc 10:00:02 |
| Processing time | Thời điểm ứng dụng thực hiện xử lý record | Kafka Streams xử lý lúc 10:00:03 |

Không có một loại timestamp đúng cho mọi bài toán.

- Báo cáo doanh thu theo thời điểm thanh toán thường cần event time.
- Đo độ trễ từ producer đến Kafka thường cần ingestion time.
- Đo thời gian CPU hoặc latency xử lý trong ứng dụng cần processing time.

Nếu dùng ingestion time để tính doanh thu theo giờ nghiệp vụ, event gửi trễ có thể bị tính vào sai giờ. Nếu dùng event time để đo latency hệ thống, đồng hồ nguồn lệch có thể làm số liệu sai.

### 3.1. Event time trong Kafka Streams

Kafka Streams sử dụng timestamp được cung cấp bởi TimestampExtractor làm timestamp của record trong topology. Timestamp này được dùng bởi các phép toán dựa trên thời gian như windowed aggregation, stream-stream join và một số xử lý stateful.

TimestampExtractor không tự sắp xếp lại record theo event time. Nó chỉ xác định timestamp mà record mang vào topology. Record vẫn được đọc theo thứ tự log của partition.

### 3.2. Processing time

Nếu nghiệp vụ cần xử lý theo đồng hồ hiện tại của ứng dụng, có thể dùng WallclockTimestampExtractor hoặc chủ động lấy system clock trong processor. Đây là lựa chọn khác với event time.

Không thay event time bằng processing time chỉ để tránh timestamp lỗi nếu kết quả nghiệp vụ cần phản ánh thời điểm event xảy ra. Việc đổi time semantics có thể làm thay đổi window, join và aggregation.

## 4. TimestampExtractor là gì?

TimestampExtractor là interface của Kafka Streams dùng để lấy timestamp cho mỗi record đầu vào.

Chữ ký phương thức:

~~~java
long extract(
    ConsumerRecord<Object, Object> record,
    long partitionTime
);
~~~

Hai tham số:

- record: Kafka record sau khi được consumer đọc và deserialize theo cấu hình source.
- partitionTime: mốc thời gian Kafka Streams đang duy trì cho partition hiện tại; có thể là giá trị âm nếu chưa có record hợp lệ được xử lý.

Giá trị trả về là timestamp theo milliseconds kể từ Unix epoch.

### 4.1. TimestampExtractor quyết định điều gì?

Extractor có thể:

1. Dùng timestamp có sẵn trong Kafka record.
2. Lấy event time từ payload.
3. Đọc timestamp từ header nếu ứng dụng tự quy ước.
4. Dùng partitionTime khi timestamp record không hợp lệ.
5. Trả về giá trị âm để bỏ qua record.
6. Ném exception nếu record vi phạm chính sách dữ liệu.

Extractor không:

- Sắp xếp record theo timestamp.
- Sửa timestamp đã lưu trong Kafka log.
- Tự đưa record lỗi sang dead-letter topic.
- Đồng bộ đồng hồ giữa producer và broker.
- Bảo đảm event time hợp lệ về mặt nghiệp vụ nếu dữ liệu nguồn đã sai.

### 4.2. partitionTime có ý nghĩa gì?

partitionTime là mốc thời gian đã quan sát mà Kafka Streams duy trì cho cùng partition. Extractor có thể dùng nó để:

- Fallback khi timestamp hiện tại bị thiếu.
- Phát hiện timestamp giảm bất thường.
- Kiểm tra timestamp có vượt giới hạn lateness của nghiệp vụ hay không.
- Giữ một quy tắc thời gian không giảm trong partition nếu nghiệp vụ yêu cầu.

Không được hiểu partitionTime là timestamp lớn nhất của toàn bộ topic hoặc toàn bộ application. Nó không tạo ra một đồng hồ toàn cục giữa các partition. Tùy phiên bản và cách triển khai, đây là partition time/high-watermark đã quan sát, không nên dùng như một cam kết rằng timestamp của record ngay trước đó luôn bằng giá trị này.

## 5. Extractor mặc định và các chính sách có sẵn

Nếu không cấu hình extractor khác, Kafka Streams dùng FailOnInvalidTimestamp làm timestamp extractor mặc định trong các phiên bản phổ biến.

Extractor mặc định sử dụng timestamp của Kafka record. Nếu timestamp âm hoặc không hợp lệ theo điều kiện của extractor, nó ném StreamsException.

Một số extractor có sẵn trong Kafka Streams:

| Extractor | Hành vi |
|---|---|
| FailOnInvalidTimestamp | Dừng xử lý bằng exception khi record có timestamp không hợp lệ. |
| LogAndSkipOnInvalidTimestamp | Ghi log và bỏ qua record có timestamp không hợp lệ. |
| UsePartitionTimeOnInvalidTimestamp | Dùng partitionTime làm timestamp thay thế khi timestamp record không hợp lệ. |
| WallclockTimestampExtractor | Dùng thời gian đồng hồ của máy xử lý thay cho timestamp trong record. |

Kiểm tra API của phiên bản Kafka Streams đang dùng để xác nhận class và hành vi chi tiết, đặc biệt trường hợp partitionTime chưa có giá trị ở record đầu tiên.

### 5.1. FailOnInvalidTimestamp

Phù hợp khi timestamp là dữ liệu bắt buộc và không được phép suy đoán.

Ưu điểm:

- Phát hiện dữ liệu sai sớm.
- Không âm thầm làm thay đổi time semantics.
- Phù hợp với pipeline có hợp đồng dữ liệu chặt chẽ.

Hạn chế:

- Một record lỗi có thể làm stream thread gặp exception.
- Nếu không có chính sách xử lý lỗi phù hợp, ứng dụng có thể dừng hoặc liên tục phục hồi rồi gặp lại record lỗi.
- Cần có quy trình sửa dữ liệu hoặc xử lý record lỗi trước khi replay.

### 5.2. LogAndSkipOnInvalidTimestamp

Phù hợp khi record timestamp lỗi có thể bị loại bỏ và hệ thống chấp nhận mất record đó khỏi kết quả topology.

Ưu điểm:

- Record lỗi không chặn các record tiếp theo.
- Có log để điều tra.
- Dễ bảo vệ topology khỏi dữ liệu timestamp âm.

Hạn chế:

- Record bị bỏ qua không tự động xuất hiện trong DLT.
- Nếu không có metric hoặc alert, tỷ lệ mất record có thể bị bỏ sót.
- Không phù hợp nếu mọi event đều phải được kiểm toán hoặc xử lý.

### 5.3. UsePartitionTimeOnInvalidTimestamp

Phù hợp khi ứng dụng chấp nhận dùng thời gian record trước đó trong cùng partition làm fallback.

Ví dụ:

~~~text
Partition orders-0:
  record 100 timestamp = 10:00:00
  record 101 timestamp = -1
  partitionTime = 10:00:00

Fallback:
  record 101 timestamp = 10:00:00
~~~

Cách này giữ được record trong topology nhưng timestamp thay thế không còn là event time thật. Nó có thể làm thay đổi window assignment và thứ tự thời gian tương đối.

Nếu partitionTime chưa có giá trị hợp lệ, hãy xác định rõ fallback tiếp theo là fail hay skip. Không tự giả định một timestamp 0 hoặc thời gian hiện tại nếu chưa có quyết định nghiệp vụ.

### 5.4. WallclockTimestampExtractor

Extractor này dùng đồng hồ hệ thống tại thời điểm xử lý. Nó có thể hữu ích cho bài toán processing-time, nhưng không phù hợp nếu cần event-time semantics.

Ví dụ một event xảy ra lúc 09:00 nhưng chỉ đến Kafka lúc 09:10. Với wall-clock extractor, event sẽ được gán thời điểm khoảng 09:10 khi xử lý, không còn đại diện thời điểm nghiệp vụ 09:00.

## 6. Những dạng timestamp không hợp lệ

Timestamp lỗi không chỉ là timestamp âm. Trong hệ thống thực tế, cần phân loại nhiều tình huống.

| Dạng lỗi | Ví dụ | Rủi ro |
|---|---|---|
| Thiếu timestamp | JSON không có eventTime | Extractor không có event time để dùng. |
| Null | eventTime là null | Không thể chuyển thành thời điểm. |
| Timestamp âm | -1 | Kafka Streams xem là timestamp không hợp lệ. |
| Sai định dạng | eventTime là yesterday | Không parse được thời gian. |
| Sai đơn vị | Epoch seconds bị hiểu là milliseconds | Event rơi vào thời điểm năm 1970. |
| Sai timezone | Thời gian local bị hiểu như UTC | Event lệch nhiều giờ. |
| Timestamp tương lai | Thời điểm lớn hơn hiện tại nhiều ngày | Stream-time có thể nhảy xa và làm event khác bị xem là quá muộn. |
| Timestamp quá cũ | Event hợp lệ từ đợt replay lịch sử | Có thể nằm ngoài retention hoặc grace của window. |
| Tràn số | Chuyển đổi epoch sang milliseconds vượt long | Có thể gây exception hoặc thời gian sai. |
| Đồng hồ producer lệch | Producer nhanh/chậm vài phút | Window và join cho kết quả không nhất quán. |

Không phải mọi timestamp cũ đều là lỗi. Dữ liệu lịch sử được replay có thể có event time cách xa hiện tại nhưng vẫn hoàn toàn hợp lệ. Cần phân biệt timestamp không hợp lệ về cấu trúc với timestamp đến trễ theo chính sách nghiệp vụ.

## 7. Chọn chính sách xử lý timestamp lỗi

Trước khi viết extractor, hãy xác định ứng dụng sẽ làm gì khi timestamp không hợp lệ.

| Chính sách | Khi nào dùng | Hệ quả |
|---|---|---|
| Fail fast | Timestamp là bắt buộc, sai timestamp là lỗi dữ liệu nghiêm trọng | Dừng xử lý để tránh kết quả sai |
| Skip | Record lỗi có thể loại bỏ theo nghiệp vụ | Mất record khỏi topology, cần metric/audit |
| Fallback broker timestamp | Event time lỗi nhưng ingestion time có thể thay thế | Đổi semantics từ event time sang ingestion time cho record đó |
| Fallback partitionTime | Chấp nhận thời gian của record trước cùng partition | Giữ record nhưng thời điểm không còn chính xác |
| Quarantine/DLT | Cần giữ record lỗi để điều tra và sửa | Phải có luồng riêng trước hoặc ngoài extractor |
| Normalize at ingestion | Có thể sửa timestamp ngay khi nhận dữ liệu | Giảm lỗi cho các consumer phía sau |

### 7.1. Không fallback âm thầm

Nếu event time sai và extractor tự chuyển sang record timestamp, cần:

- Ghi log có rate limit.
- Tăng metric records_timestamp_fallback_total.
- Ghi rõ fallback policy trong tài liệu vận hành.
- Giữ event ID để có thể truy vết.
- Theo dõi tỷ lệ fallback theo source và producer version.

Không trộn event time và ingestion time mà không đánh dấu. Một dashboard có thể trông vẫn hợp lý nhưng kết quả window đã thay đổi.

### 7.2. Khi nào nên đưa record vào DLT?

TimestampExtractor chỉ trả timestamp hoặc báo lỗi; nó không có API để phát record sang topic khác. Nếu cần giữ record lỗi trong DLT, nên xử lý trước khi Kafka Streams nhận dữ liệu:

1. Validate timestamp ở producer hoặc ingestion service.
2. Nếu hợp lệ, ghi vào topic chuẩn.
3. Nếu không hợp lệ, ghi vào quarantine topic kèm error code và payload gốc.
4. Kafka Streams chỉ đọc topic đã được kiểm tra hoặc có extractor phù hợp.

Một lựa chọn khác là xây dựng topology/processor chuyên xử lý dữ liệu thô trước các phép toán event-time, nhưng cần lưu ý extractor vẫn được gọi ở đầu vào. Không thể trông chờ một processor phía sau bắt record mà extractor đã làm skip.

## 8. Viết custom TimestampExtractor

Giả sử event order có payload JSON:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "eventTime": "2026-11-20T10:15:30Z",
  "amount": 125000
}
~~~

Ứng dụng muốn dùng eventTime làm event time. Nếu field thiếu hoặc không parse được, ví dụ này fallback sang Kafka record timestamp khi timestamp đó hợp lệ. Nếu cả hai đều không hợp lệ, extractor trả về -1 để Kafka Streams bỏ qua record.

Ví dụ minh họa dùng Jackson để parse JSON:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.streams.errors.StreamsException;
import org.apache.kafka.streams.processor.TimestampExtractor;

import java.time.Instant;

public class OrderEventTimestampExtractor
        implements TimestampExtractor {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Override
    public long extract(
            ConsumerRecord<Object, Object> record,
            long partitionTime) {

        long eventTime = readEventTime(record.value());

        if (isValid(eventTime)) {
            return eventTime;
        }

        long kafkaTimestamp = record.timestamp();

        if (isValid(kafkaTimestamp)) {
            // Fallback này đổi semantics sang ingestion/record time.
            return kafkaTimestamp;
        }

        // Timestamp âm khiến record bị bỏ qua trong Kafka Streams.
        return -1L;
    }

    private long readEventTime(Object value) {
        if (!(value instanceof String json)) {
            return -1L;
        }

        try {
            JsonNode root = MAPPER.readTree(json);
            JsonNode field = root.get("eventTime");

            if (field == null || field.isNull()) {
                return -1L;
            }

            if (field.isIntegralNumber()) {
                return field.longValue();
            }

            if (field.isTextual()) {
                return Instant.parse(field.asText()).toEpochMilli();
            }

        } catch (Exception exception) {
            // Production nên ghi metric/log có rate limit tại đây.
            return -1L;
        }

        return -1L;
    }

    private boolean isValid(long timestamp) {
        return timestamp >= 0;
    }
}
~~~

Ví dụ này chấp nhận eventTime dạng epoch milliseconds hoặc chuỗi ISO-8601 UTC như 2026-11-20T10:15:30Z. Nếu hệ thống dùng định dạng khác, hãy định nghĩa parser rõ ràng thay vì đoán theo giá trị.

### 8.1. Kiểm tra timestamp tương lai

Có thể bổ sung giới hạn timestamp tương lai:

~~~java
private static final long MAX_FUTURE_SKEW_MS =
    5 * 60 * 1000L;

private boolean isValid(long timestamp) {
    if (timestamp < 0) {
        return false;
    }

    long latestAllowed =
        System.currentTimeMillis() + MAX_FUTURE_SKEW_MS;

    return timestamp <= latestAllowed;
}
~~~

Giới hạn này chỉ là ví dụ. Chọn skew theo đồng bộ NTP, độ trễ mạng, thời gian xử lý upstream và yêu cầu replay.

Không áp dụng giới hạn không được cũ hơn hiện tại X phút nếu ứng dụng cần replay dữ liệu lịch sử. Timestamp cũ có thể hợp lệ; late-event policy nên được xử lý ở tầng window/grace thay vì đánh đồng với timestamp sai.

### 8.2. Không dùng fallback nếu event time là bắt buộc

Nếu nghiệp vụ yêu cầu mọi record phải có event time chuẩn, hãy bỏ fallback sang record timestamp:

~~~java
@Override
public long extract(
        ConsumerRecord<Object, Object> record,
        long partitionTime) {

    long eventTime = readEventTime(record.value());

    if (eventTime < 0) {
        throw new StreamsException(
            "Missing or invalid eventTime for topic="
            + record.topic()
            + ", partition="
            + record.partition()
            + ", offset="
            + record.offset()
        );
    }

    return eventTime;
}
~~~

Cách fail-fast cần đi cùng exception handling, alert và quy trình quarantine/replay. Nếu không, một record lỗi có thể khiến ứng dụng phục hồi rồi gặp lại cùng record và lặp lỗi.

## 9. Cấu hình TimestampExtractor

Có hai cách phổ biến để cấu hình extractor.

### 9.1. Cấu hình mặc định cho toàn application

~~~java
Properties properties = new Properties();

properties.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "orders-event-time-v1"
);
properties.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "localhost:9092"
);
properties.put(
    StreamsConfig.DEFAULT_TIMESTAMP_EXTRACTOR_CLASS_CONFIG,
    OrderEventTimestampExtractor.class
);
~~~

Cấu hình này áp dụng extractor mặc định cho source nodes không chỉ định extractor riêng.

### 9.2. Cấu hình riêng cho một source

~~~java
Consumed<String, String> consumed =
    Consumed.with(Serdes.String(), Serdes.String())
        .withTimestampExtractor(
            new OrderEventTimestampExtractor()
        );

KStream<String, String> orders =
    builder.stream("orders", consumed);
~~~

Cách này hữu ích khi cùng topology đọc nhiều topic có định dạng timestamp khác nhau.

Ví dụ:

- orders dùng eventTime trong JSON.
- audit dùng timestamp Kafka record.
- metrics dùng epoch milliseconds trong value.

Không nên dùng một extractor giả định cùng cấu trúc payload cho mọi source nếu dữ liệu không có cùng hợp đồng.

## 10. Chuẩn hóa đơn vị và timezone

Đây là nguồn lỗi rất phổ biến khi tích hợp nhiều producer.

### 10.1. Epoch seconds và epoch milliseconds

Unix epoch seconds có giá trị khoảng 10 chữ số ở thời điểm hiện tại. Epoch milliseconds có khoảng 13 chữ số.

Ví dụ:

~~~text
Epoch seconds:      1795169730
Epoch milliseconds: 1795169730000
~~~

Nếu giá trị seconds bị hiểu là milliseconds, timestamp sẽ nằm gần năm 1970. Ngược lại, nếu milliseconds bị nhân thêm 1000, giá trị có thể vượt phạm vi hợp lệ.

Hãy quy định rõ:

- Tên field có đơn vị, ví dụ eventTimeMs.
- Schema quy định kiểu và đơn vị.
- Producer và consumer dùng cùng chuẩn.
- Validation từ chối giá trị không đúng phạm vi.

Không tự động suy luận đơn vị chỉ từ số chữ số trong production. Có thể tồn tại dữ liệu lịch sử, timestamp nhỏ hoặc format khác làm quy tắc suy luận sai.

### 10.2. ISO-8601 và UTC

Nên truyền timestamp dạng ISO-8601 có timezone rõ ràng:

~~~text
2026-11-20T10:15:30Z
2026-11-20T17:15:30+07:00
~~~

Hai chuỗi trên biểu diễn cùng thời điểm nếu offset tương ứng.

Tránh chuỗi local không có timezone:

~~~text
2026-11-20 10:15:30
~~~

Không thể xác định duy nhất instant nếu không biết timezone của nguồn.

Trong Java:

~~~java
long timestamp = Instant.parse(
    "2026-11-20T10:15:30Z"
).toEpochMilli();
~~~

Nếu nguồn gửi LocalDateTime, cần biết ZoneId đã được thống nhất trước khi chuyển thành Instant. Không mặc định timezone của JVM là timezone nghiệp vụ.

## 11. Timestamp lỗi và event đến muộn

TimestampExtractor chọn timestamp, còn Kafka Streams dùng timestamp đó trong các phép toán event-time. Một record có timestamp hợp lệ vẫn có thể đến muộn.

Phân biệt:

- **Invalid timestamp:** không thể diễn giải hoặc vi phạm hợp đồng timestamp.
- **Out-of-order event:** timestamp nhỏ hơn event đã xử lý trước đó nhưng vẫn hợp lệ.
- **Late event:** event đến sau khi stream-time đã tiến xa; với windowed operation, nó có thể đến sau thời điểm window được chấp nhận.
- **Future event:** timestamp hợp lệ về cấu trúc nhưng nằm quá xa trong tương lai theo chính sách nguồn.

Không nên skip mọi record có timestamp nhỏ hơn partitionTime. Điều đó sẽ loại bỏ event đến muộn hợp lệ.

### 11.1. Out-of-order không đồng nghĩa invalid

Ví dụ cùng partition:

~~~text
offset 100: eventTime 10:00:05
offset 101: eventTime 10:00:02
offset 102: eventTime 10:00:07
~~~

Record offset 101 có timestamp thấp hơn offset 100. Nó vẫn có thể là event hợp lệ được gửi trễ.

Nếu extractor ép timestamp không giảm bằng cách luôn thay timestamp nhỏ hơn partitionTime, ứng dụng sẽ làm thay đổi event time thật. Chỉ làm điều này nếu nghiệp vụ định nghĩa timestamp phải đơn điệu theo partition.

### 11.2. Stream-time và window

Kafka Streams dùng timestamp của record để tiến triển stream-time trong task. Với windowed aggregation, stream-time giúp xác định window nào còn nhận record và window nào đã đóng theo grace period.

Ví dụ window 5 phút, grace 1 phút:

~~~text
Window: 10:00 - 10:05
Grace:  1 phút

Event trong window:
  eventTime = 10:04:50 -> thuộc window

Event đến sau khi stream-time vượt end + grace:
  eventTime = 10:04:50 -> có thể bị drop vì window đã đóng
~~~

Grace period cho phép dữ liệu đến trễ trong một khoảng thời gian. Nó không sửa timestamp và cũng không bảo đảm mọi event đến muộn đều được chấp nhận.

Ví dụ API hiện đại:

~~~java
TimeWindows windows =
    TimeWindows.ofSizeAndGrace(
        Duration.ofMinutes(5),
        Duration.ofMinutes(1)
    );
~~~

Tên API có thể khác ở các phiên bản cũ. Chọn grace theo phân bố lateness thực tế, không chỉ theo cảm tính.

### 11.3. Timestamp tương lai có thể đẩy stream-time đi quá xa

Giả sử một record lỗi mang timestamp 2099 trong khi các event còn lại thuộc năm 2026. Record tương lai có thể làm stream-time tăng mạnh. Khi đó, window cũ có thể đóng sớm và event hợp lệ đến sau bị xem là quá muộn.

Vì vậy, cần kiểm tra timestamp tương lai ngay tại ingestion hoặc extractor nếu nguồn có thể phát timestamp sai. Giới hạn tương lai nên dựa trên clock synchronization và hợp đồng dữ liệu.

## 12. TimestampExtractor và join

Timestamp cũng ảnh hưởng đến join, đặc biệt là KStream-KStream join dùng time window.

Với stream-stream join:

- Hai record phải có key phù hợp.
- Timestamp xác định quan hệ thời gian giữa hai record.
- Join window quy định khoảng cách thời gian cho phép.
- Grace period cho phép record đến trễ trong giới hạn.
- Timestamp sai có thể khiến cặp record đáng lẽ match không còn nằm trong cửa sổ.

KStream-KTable join và KStream-GlobalKTable join không dùng time window theo cách stream-stream join, nhưng timestamp vẫn có thể ảnh hưởng đến các phép toán downstream hoặc logic event-time khác trong topology.

Nếu join không tạo output, cần kiểm tra cả key, partitioning, timestamp, window size, grace và tiến độ cập nhật state.

## 13. Kiểm thử TimestampExtractor

Không nên chỉ test record timestamp hợp lệ. Hãy kiểm thử các trường hợp biên:

| Trường hợp | Input | Kết quả mong đợi |
|---|---|---|
| ISO-8601 hợp lệ | 2026-11-20T10:15:30Z | Chuyển thành epoch milliseconds đúng |
| Epoch milliseconds | 1795169730000 | Giữ nguyên nếu nằm trong miền hợp lệ |
| Thiếu eventTime | Không có field | Fallback hoặc skip/fail theo policy |
| Null | eventTime null | Xử lý theo policy |
| Chuỗi sai định dạng | eventTime tomorrow | Skip hoặc fail; không crash ngoài kiểm soát |
| Timestamp âm | -1 | Invalid |
| Sai đơn vị | Epoch seconds đưa vào field milliseconds | Bị validation phát hiện |
| Timestamp tương lai | Năm 2099 | Từ chối nếu vượt future-skew policy |
| Event đến muộn | Timestamp thấp hơn partitionTime | Chấp nhận nếu event time hợp lệ |
| Partition chưa có record trước | partitionTime âm | Dùng chính sách first-record rõ ràng |

### 13.1. Unit test cho extractor

Ví dụ kiểm thử logic parse timestamp nên tách thành hàm thuần để dễ test:

~~~java
@Test
void parsesIso8601EventTime() {
    long actual = parser.parse(
        "2026-11-20T10:15:30Z"
    );

    long expected = Instant.parse(
        "2026-11-20T10:15:30Z"
    ).toEpochMilli();

    assertEquals(expected, actual);
}

@Test
void rejectsInvalidTimestamp() {
    assertEquals(-1L, parser.parse("tomorrow"));
}

@Test
void rejectsNegativeEpoch() {
    assertEquals(-1L, parser.parse("-100"));
}
~~~

Nếu custom extractor phụ thuộc system clock để kiểm tra future skew, hãy inject Clock để test ổn định thay vì gọi System.currentTimeMillis() trực tiếp trong mọi nhánh.

### 13.2. TopologyTestDriver

TopologyTestDriver cho phép kiểm thử cách timestamp ảnh hưởng đến topology mà không cần broker thật cho các test logic cơ bản.

~~~java
Properties properties = new Properties();
properties.put(
    StreamsConfig.APPLICATION_ID_CONFIG,
    "timestamp-test"
);
properties.put(
    StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
    "dummy:9092"
);

try (TopologyTestDriver driver =
         new TopologyTestDriver(topology, properties)) {

    TestInputTopic<String, String> input =
        driver.createInputTopic(
            "orders",
            Serdes.String().serializer(),
            Serdes.String().serializer()
        );

    input.pipeInput(
        "order-1",
        "{\"eventTime\":\"2026-11-20T10:15:30Z\"}",
        Instant.parse("2026-11-20T10:15:31Z")
    );
}
~~~

TestInputTopic có thể cung cấp timestamp riêng cho record. Cần kiểm tra output, window assignment và state sau khi đưa record theo thứ tự thời gian mong muốn.

TopologyTestDriver không mô phỏng đầy đủ broker timestamp policy, clock skew của nhiều host, network delay hoặc rebalance production. Những trường hợp đó cần integration test với Kafka cluster.

## 14. Monitoring timestamp quality

Theo dõi timestamp quality như một phần của data quality.

Các metric nên có:

| Metric | Ý nghĩa |
|---|---|
| records_timestamp_invalid_total | Số record có timestamp không hợp lệ |
| records_timestamp_fallback_total | Số record dùng fallback timestamp |
| records_timestamp_skipped_total | Số record bị skip |
| records_timestamp_future_total | Số record có timestamp vượt ngưỡng tương lai |
| records_timestamp_past_total | Số record quá cũ theo policy nếu có |
| event_time_lag_ms | Chênh lệch giữa processing/ingestion time và event time |
| partition_timestamp_regression_total | Số lần timestamp giảm trong cùng partition |
| window_late_record_drop_total | Số record bị loại khỏi window vì đến quá muộn |

Không phải metric nào cũng có sẵn tự động trong Kafka Streams. Có thể cần instrument extractor, processor hoặc ingestion layer để ghi nhận.

### 14.1. Log đủ thông tin để điều tra

Khi timestamp lỗi, log nên có:

- Topic.
- Partition.
- Offset.
- Event ID nếu có.
- Producer/source identifier.
- Timestamp raw.
- Timestamp Kafka record.
- Loại lỗi hoặc policy được áp dụng.
- Connector/producer version nếu có.

Không log toàn bộ payload nếu dữ liệu có thông tin cá nhân hoặc bí mật. Dùng event ID và metadata đủ để truy vết.

### 14.2. Alert theo tỷ lệ, không chỉ số lượng

Một topic có hàng tỷ record có thể có vài timestamp lỗi mỗi phút mà tỷ lệ rất nhỏ. Một topic nhỏ có 100 timestamp lỗi trong một phút có thể là sự cố nghiêm trọng.

Theo dõi cả:

- Số lượng lỗi.
- Tỷ lệ lỗi trên tổng record.
- Tốc độ tăng lỗi.
- Phân bố lỗi theo producer/source.
- Số record bị fallback hoặc skip.
- Event-time lag p95/p99.

## 15. Vận hành và phục hồi khi gặp timestamp lỗi

Nếu ứng dụng dừng hoặc bỏ qua record vì timestamp không hợp lệ, cần quy trình xử lý có thể lặp lại.

1. Xác định topic, partition, offset và event ID.
2. Xác định producer/source đã tạo record.
3. Kiểm tra raw payload và Kafka record timestamp.
4. Phân loại lỗi: thiếu field, sai format, sai đơn vị, clock skew hay timestamp tương lai.
5. Xác định record đã bị fail, skip hay fallback.
6. Sửa hợp đồng dữ liệu hoặc extractor.
7. Nếu cần replay, xác định offset và phạm vi dữ liệu.
8. Tránh tạo duplicate side effect khi replay.
9. Kiểm tra lại window/aggregation sau khi dữ liệu được phát lại.
10. Ghi nhận metric và nguyên nhân gốc.

Nếu record đã bị skip, việc đổi extractor không tự động đưa record đó trở lại topology. Cần replay từ nguồn hoặc từ một topic quarantine đã lưu record gốc.

Nếu record được fallback sang broker timestamp, dữ liệu output đã có thể mang semantics khác. Replay sau khi sửa extractor có thể tạo kết quả khác; cần quyết định có rebuild state hay phát correction event.

## 16. Ví dụ topology event-time

Ví dụ đơn giản đọc order event, dùng custom extractor và aggregate số event theo cửa sổ 5 phút.

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.kstream.WindowedSerdes;
import org.apache.kafka.streams.Topology;

import java.time.Duration;
import java.util.Properties;

public class OrderEventTimeApplication {

    public static void main(String[] args) {
        Properties properties = new Properties();

        properties.put(
            StreamsConfig.APPLICATION_ID_CONFIG,
            "order-event-time"
        );
        properties.put(
            StreamsConfig.BOOTSTRAP_SERVERS_CONFIG,
            "localhost:9092"
        );
        properties.put(
            StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG,
            Serdes.String().getClass()
        );
        properties.put(
            StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG,
            Serdes.String().getClass()
        );

        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, String> orders = builder.stream(
            "orders",
            Consumed.with(Serdes.String(), Serdes.String())
                .withTimestampExtractor(
                    new OrderEventTimestampExtractor()
                )
        );

        KTable<Windowed<String>, Long> eventCounts = orders
            .groupByKey(
                Grouped.with(Serdes.String(), Serdes.String())
            )
            .windowedBy(
                TimeWindows.ofSizeAndGrace(
                    Duration.ofMinutes(5),
                    Duration.ofMinutes(1)
                )
            )
            .count(
                Materialized.as("order-event-counts")
            );

        eventCounts.toStream().to(
            "order-event-counts",
            Produced.with(
                WindowedSerdes.timeWindowedSerdeFrom(String.class),
                Serdes.Long()
            )
        );

        Topology topology = builder.build();
        System.out.println(topology.describe());

        KafkaStreams streams = new KafkaStreams(topology, properties);
        streams.start();

        Runtime.getRuntime().addShutdownHook(
            new Thread(streams::close)
        );
    }
}
~~~

Đây là khung minh họa. Trong project thật, cần import Produced và WindowedSerdes, chọn key aggregation phù hợp với nghiệp vụ, khai báo schema rõ ràng và kiểm tra API theo phiên bản Kafka Streams. Nếu dùng groupBy() để đổi key, topology có thể tạo repartition topic trước khi aggregate.

## 17. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| StreamsException báo invalid timestamp | Extractor mặc định gặp timestamp âm hoặc không hợp lệ | Kiểm tra Kafka record timestamp và chọn fail/skip/fallback policy |
| Record bị skip nhưng không thấy output | Extractor trả timestamp âm hoặc LogAndSkipOnInvalidTimestamp bỏ record | Kiểm tra log/metric và replay nếu record cần được xử lý |
| Event rơi vào năm 1970 | Epoch seconds bị hiểu là milliseconds | Chuẩn hóa đơn vị timestamp ở producer/schema |
| Window đóng quá sớm | Một record có timestamp tương lai làm stream-time nhảy xa | Kiểm tra future timestamp và giới hạn skew |
| Window không nhận event đến trễ | Event đến sau end + grace | Điều chỉnh grace theo lateness distribution hoặc xử lý late data riêng |
| Join không tạo output | Timestamp không nằm trong join window hoặc key không khớp | Kiểm tra timestamp, window, grace, key và partitioning |
| Timestamp tăng/giảm bất thường | Producer clock lệch hoặc event đến không theo thứ tự | Đo clock skew và phân biệt out-of-order hợp lệ |
| Extractor parse JSON lỗi | Payload sai schema hoặc value không phải String | Kiểm tra Serde, schema version và raw payload |
| Replay tạo kết quả khác | Extractor hoặc fallback policy đã thay đổi | Lập kế hoạch rebuild/correction và chống duplicate |
| Nhiều record dùng broker timestamp | EventTime thiếu hoặc không parse được | Theo dõi fallback rate và sửa producer contract |
| Record đầu tiên partition bị skip | Fallback partitionTime chưa có giá trị | Định nghĩa policy riêng cho first record |
| Dữ liệu lịch sử bị loại | Extractor dùng giới hạn tuổi không phù hợp | Phân biệt replay hợp lệ với timestamp lỗi |

## 18. Checklist thiết kế production

Trước khi triển khai TimestampExtractor, hãy xác nhận:

1. Đã xác định nghiệp vụ cần event time, ingestion time hay processing time chưa?
2. Producer có thống nhất timestamp format và timezone không?
3. Đơn vị timestamp là epoch milliseconds hay ISO-8601?
4. Kafka topic đang dùng CreateTime hay LogAppendTime?
5. Extractor mặc định có phù hợp với chất lượng timestamp nguồn không?
6. Chính sách invalid timestamp là fail, skip hay fallback?
7. Fallback có làm trộn event time và ingestion time không?
8. Record bị skip có cần quarantine hoặc replay không?
9. partitionTime được dùng đúng phạm vi partition chưa?
10. Có chấp nhận event timestamp out-of-order không?
11. Future skew có ngưỡng và metric không?
12. Window grace có dựa trên phân bố late-event thực tế không?
13. Có kiểm thử timestamp âm, null, sai format, sai đơn vị và tương lai không?
14. Có kiểm thử event đến muộn và record đầu tiên của partition không?
15. Có metric cho invalid, fallback, skip và event-time lag không?
16. Có quy trình replay hoặc rebuild state khi sửa extractor không?
17. Có tránh log payload nhạy cảm khi điều tra không?

## 19. Bài tập thực hành

### Bài 1: Quan sát Kafka record timestamp

1. Tạo topic orders-time-lab.
2. Gửi record với timestamp do producer cung cấp.
3. Đọc metadata record và in timestamp.
4. Cấu hình topic dùng CreateTime rồi thử lại.
5. Cấu hình môi trường lab dùng LogAppendTime nếu broker cho phép.
6. So sánh timestamp producer và timestamp broker lưu.

### Bài 2: Dùng extractor mặc định

1. Tạo Kafka Streams application đọc topic có timestamp hợp lệ.
2. Không cấu hình custom extractor.
3. Xác nhận topology dùng record timestamp.
4. Tạo record không có timestamp hợp lệ bằng test input.
5. Quan sát FailOnInvalidTimestamp và error behavior.

### Bài 3: So sánh fail và skip

1. Chạy topology với FailOnInvalidTimestamp.
2. Gửi một record hợp lệ và một record lỗi.
3. Quan sát ứng dụng và log.
4. Đổi sang LogAndSkipOnInvalidTimestamp.
5. Gửi lại cùng dữ liệu trong topic lab.
6. So sánh record output và metric cần có.

### Bài 4: Custom event-time extractor

1. Tạo payload có eventTime dạng ISO-8601.
2. Viết OrderEventTimestampExtractor.
3. Gửi record có eventTime hợp lệ, thiếu field và sai định dạng.
4. Thử fallback sang Kafka record timestamp.
5. Kiểm tra event-time lag và fallback counter.
6. Bỏ fallback để thử fail/skip policy.

### Bài 5: Out-of-order và grace period

1. Tạo window 5 phút với grace 1 phút.
2. Gửi event timestamp 10:00:10.
3. Gửi event timestamp 10:00:05 sau đó.
4. Gửi record làm stream-time vượt end + grace.
5. Gửi lại event thuộc window cũ.
6. Quan sát record nào được chấp nhận hoặc bị drop.

### Bài 6: Timestamp tương lai

1. Gửi một record có timestamp cách hiện tại nhiều năm.
2. Quan sát stream-time và window behavior trong môi trường lab.
3. Bổ sung future-skew validation.
4. Gửi lại record và xác nhận policy fail/skip/fallback.
5. Đánh giá ảnh hưởng nếu record tương lai đã được xử lý trước đó.

## 20. Câu hỏi tự kiểm tra

1. Event time khác ingestion time và processing time như thế nào?
2. CreateTime và LogAppendTime khác nhau ở đâu?
3. Offset có thể dùng thay timestamp không?
4. TimestampExtractor có chữ ký phương thức nào?
5. partitionTime biểu diễn thời gian của record nào?
6. FailOnInvalidTimestamp xử lý timestamp âm ra sao?
7. LogAndSkipOnInvalidTimestamp phù hợp khi nào?
8. UsePartitionTimeOnInvalidTimestamp có rủi ro gì?
9. Vì sao WallclockTimestampExtractor không phù hợp cho event-time analytics?
10. Timestamp thiếu và timestamp cũ có luôn là lỗi không?
11. Epoch seconds bị hiểu là milliseconds gây ra hiện tượng gì?
12. Vì sao cần timezone rõ ràng trong payload?
13. TimestampExtractor có thể tự gửi record lỗi sang DLT không?
14. Out-of-order event khác invalid timestamp như thế nào?
15. Stream-time ảnh hưởng window ra sao?
16. Grace period giúp xử lý late event như thế nào?
17. Một record timestamp tương lai có thể ảnh hưởng các record khác ra sao?
18. Vì sao không nên ép timestamp luôn tăng theo partition nếu nghiệp vụ cho phép event đến muộn?
19. Cần metric nào để theo dõi chất lượng timestamp?
20. Khi thay extractor và replay dữ liệu, cần lưu ý điều gì?

## Kết luận

TimestampExtractor quyết định timestamp mà Kafka Streams sử dụng cho record trong topology. Timestamp có thể lấy từ Kafka record, payload, header hoặc đồng hồ xử lý tùy semantics. Event time phù hợp với phân tích theo thời điểm nghiệp vụ; ingestion time phản ánh thời điểm tiếp nhận; processing time phản ánh thời điểm ứng dụng thực hiện xử lý.

Khi timestamp không hợp lệ, cần chọn chính sách rõ ràng: fail để bảo vệ tính đúng đắn, skip khi nghiệp vụ cho phép loại bỏ, hoặc fallback khi chấp nhận thay đổi time semantics. TimestampExtractor không tự đưa record lỗi sang DLT và không sắp xếp record theo event time.

Timestamp hợp lệ vẫn có thể out-of-order hoặc đến muộn. Stream-time, window và grace period quyết định record muộn còn được chấp nhận hay không. Timestamp tương lai có thể làm stream-time nhảy xa, vì vậy cần kiểm tra clock skew, đơn vị, timezone và giới hạn tương lai. Hãy kiểm thử các trường hợp biên, đo tỷ lệ invalid/fallback/skip và chuẩn bị quy trình replay trước khi triển khai production.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Timestamp | Thời điểm gắn với Kafka record, thường tính bằng milliseconds từ Unix epoch. |
| CreateTime | Timestamp do producer/client cung cấp hoặc gán khi tạo record. |
| LogAppendTime | Timestamp do broker gán khi append record vào log. |
| Event time | Thời điểm nghiệp vụ hoặc sự kiện thực sự xảy ra. |
| Ingestion time | Thời điểm dữ liệu được tiếp nhận vào Kafka/hệ thống streaming. |
| Processing time | Thời điểm ứng dụng thực hiện xử lý record. |
| TimestampExtractor | Interface chọn timestamp cho record đầu vào Kafka Streams. |
| partitionTime | Timestamp của record trước đó đã xử lý trong cùng partition. |
| FailOnInvalidTimestamp | Extractor báo lỗi khi Kafka record có timestamp không hợp lệ. |
| LogAndSkipOnInvalidTimestamp | Extractor ghi log và bỏ qua record có timestamp không hợp lệ. |
| UsePartitionTimeOnInvalidTimestamp | Extractor dùng partitionTime khi record timestamp không hợp lệ. |
| WallclockTimestampExtractor | Extractor dùng đồng hồ hệ thống tại thời điểm xử lý. |
| Stream-time | Khái niệm thời gian tiến triển trong Kafka Streams dựa trên timestamp record. |
| Out-of-order event | Event có timestamp không theo thứ tự tăng dần khi được xử lý. |
| Late event | Event đến sau tiến độ thời gian của topology hoặc sau giới hạn window/grace. |
| Grace period | Khoảng thời gian bổ sung cho phép window nhận event đến muộn. |
| Tombstone | Record có key và value null dùng để xóa key trong changelog table. |
| Timestamp skew | Độ lệch timestamp giữa nguồn, broker và hệ thống xử lý. |

