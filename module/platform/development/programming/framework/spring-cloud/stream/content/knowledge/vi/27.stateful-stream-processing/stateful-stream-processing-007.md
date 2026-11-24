# Grace period, dữ liệu đến muộn và kết quả cửa sổ

Trong xử lý stream, event không phải lúc nào cũng đến Kafka theo đúng thứ tự thời gian nghiệp vụ. Một giao dịch xảy ra lúc 10:02 có thể đến sau một giao dịch lúc 10:04 vì mạng chậm, thiết bị offline, retry hoặc producer gửi từ nhiều nguồn. Nếu hệ thống chốt kết quả cửa sổ ngay khi thấy thời gian kết thúc, những event đến trễ có thể bị bỏ qua hoặc làm sai số liệu.

Kafka Streams giải quyết bài toán này bằng **event time**, **stream time**, cửa sổ (window) và **grace period**. Window xác định event nào thuộc cùng một nhóm thời gian; grace period giới hạn khoảng thời gian sau khi cửa sổ kết thúc mà hệ thống vẫn chấp nhận record đến không đúng thứ tự. Kết quả cửa sổ có thể được phát liên tục khi state thay đổi hoặc chỉ phát một lần sau khi cửa sổ đóng.

Trong Spring Cloud Stream Kafka Streams binder, các khái niệm này được dùng trực tiếp qua Kafka Streams DSL trong function bean. Bài học tập trung vào việc chọn timestamp, cấu hình grace, phân biệt late event với event bị loại, quản lý state retention và kiểm thử kết quả cuối cùng.

## 1. Vì sao event đến muộn?

Giả sử một cửa hàng tổng hợp số đơn hàng theo khách trong các cửa sổ 5 phút. Thời gian nghiệp vụ của đơn hàng được ghi lúc phát sinh, nhưng producer có thể gửi record trễ vài phút.

~~~text
Thời gian nghiệp vụ (event time)       Thời gian record tới Kafka
10:01:00  order A --------------------> 10:01:02
10:02:00  order B -------------------------------> 10:05:30
10:04:00  order C --------------------> 10:04:03
10:03:00  order D --------------------------------------> 10:08:00
~~~

Nếu chỉ dựa vào thời điểm record đến, hệ thống có thể xếp order B và order D vào cửa sổ sai. Nếu dùng event time, chúng được đặt vào cửa sổ theo thời điểm xảy ra, nhưng phải quyết định hệ thống còn chờ record đến muộn trong bao lâu.

Các nguyên nhân thường gặp:

- Thiết bị di động hoặc IoT mất kết nối rồi gửi bù dữ liệu.
- Producer retry hoặc batch nhiều event trước khi gửi.
- Nhiều producer có độ trễ mạng khác nhau.
- Consumer hoặc broker tạm thời bị nghẽn.
- Event được tạo ở hệ thống nguồn nhưng qua nhiều service mới đến topic.
- Đồng hồ của máy nguồn bị lệch hoặc timestamp được tạo sai.
- Replay/backfill đưa record cũ vào topic sau khi cửa sổ đã được xử lý.

Event time là thời điểm nghiệp vụ mà event đại diện. Processing time là thời điểm ứng dụng thực hiện xử lý record. Kafka Streams còn sử dụng stream time để quyết định tiến độ thời gian của một task. Ba mốc này có thể khác nhau.

## 2. Event time, processing time và stream time

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Event time | Thời điểm sự kiện thực sự xảy ra theo dữ liệu nguồn | Đơn hàng được tạo lúc 10:02 |
| Processing time | Thời điểm ứng dụng đang xử lý record | Consumer xử lý lúc 10:06 |
| Stream time | Mốc thời gian tiến triển theo timestamp của record mà task đã quan sát | Task đã nhận record có timestamp tới 10:08 |

Kafka record có timestamp metadata. Mặc định Kafka Streams sử dụng timestamp trong ConsumerRecord. Timestamp này có thể phản ánh CreateTime do producer gửi hoặc LogAppendTime do broker gán, tùy cấu hình topic/broker.

Nếu cần dùng trường `occurredAt` trong payload làm event time, phải cung cấp `TimestampExtractor`. Không nên mặc định timestamp Kafka luôn là thời điểm nghiệp vụ.

Stream time được Kafka Streams theo dõi theo task và tiến lên khi task xử lý record có timestamp lớn hơn mốc hiện tại. Record out-of-order có timestamp nhỏ hơn không làm stream time lùi lại. Nó không phải đồng hồ hệ thống chạy liên tục. Khi không có record mới, stream time có thể đứng yên dù đồng hồ thực tế đã đi qua nhiều phút.

Điểm này rất quan trọng: grace period và việc đóng cửa sổ dựa trên stream time. Không có record mới để đẩy stream time đi tiếp thì một cửa sổ có thể chưa đóng và kết quả cuối cùng chưa được phát, dù wall clock đã vượt qua mốc window end + grace.

~~~text
Event time của record       10:01  10:02  10:04  10:08
                                |     |     |     |
Stream time của task        10:01 -> 10:02 -> 10:04 -> 10:08

Wall clock vẫn chạy kể cả khi không có record.
Stream time chỉ tiến theo timestamp của dữ liệu được xử lý.
~~~

Không nhầm stream time với watermark toàn cục của một hệ thống stream processing khác. Kafka Streams dùng stream-time semantics trong task để quản lý window, grace và suppression.

## 3. Window xác định phạm vi gom nhóm theo thời gian

Windowing chia các record cùng key thành nhóm theo thời gian để thực hiện count, reduce, aggregate hoặc join.

Kafka Streams hỗ trợ các dạng cửa sổ chính:

| Loại cửa sổ | Đặc điểm | Ví dụ sử dụng |
|---|---|---|
| Tumbling time window | Cố định, không chồng lấn, không có khoảng trống | Tổng đơn hàng mỗi 5 phút |
| Hopping time window | Cố định, có thể chồng lấn; có size và advance interval | Tổng đơn trong 5 phút, cập nhật mỗi phút |
| Sliding window | Cửa sổ trượt liên tục theo chênh lệch timestamp giữa record | Phát hiện hai hành vi gần nhau trong 10 phút |
| Session window | Kích thước động, ngăn cách bởi khoảng không hoạt động | Gom chuỗi thao tác của một người dùng |

### Tumbling window

Cửa sổ 5 phút không chồng lấn có ranh giới:

~~~text
[10:00, 10:05) [10:05, 10:10) [10:10, 10:15)
     5 phút          5 phút          5 phút
~~~

Khoảng thời gian có đầu trái inclusive và đầu phải exclusive. Record có timestamp đúng 10:05 thuộc cửa sổ bắt đầu 10:05, không thuộc cửa sổ kết thúc 10:05.

TimeWindows của Kafka Streams được căn theo epoch. Với tumbling window 5 phút, các ranh giới được xác định theo bội số của 5 phút kể từ epoch, không tự căn theo thời điểm ứng dụng khởi động.

### Hopping window

Cửa sổ có size 5 phút và advance 1 phút:

~~~text
[10:00, 10:05)
   [10:01, 10:06)
      [10:02, 10:07)
         [10:03, 10:08)
~~~

Một event có thể thuộc nhiều cửa sổ. Hopping phù hợp với dashboard cần tính tổng theo khoảng nhìn lùi nhưng cập nhật thường xuyên. Chi phí state và số kết quả thường cao hơn tumbling.

### Sliding window

Sliding window khác hopping window. Nó tạo snapshot theo chênh lệch timestamp giữa các record; ranh giới không đơn giản là các bước nhảy cố định theo epoch. Kafka Streams có `SlidingWindows` cho windowed aggregation và `JoinWindows` cho stream-stream join. Không gọi mọi cửa sổ chồng lấn là cùng một loại window.

### Session window

Session window gom các record theo key khi khoảng cách giữa các event không vượt quá inactivity gap. Khi có event mới nối hai session, Kafka Streams có thể hợp nhất các session và cập nhật kết quả. Session window phù hợp với phiên sử dụng, hành trình tương tác hoặc chuỗi thao tác mà thời lượng phụ thuộc hoạt động thực tế.

## 4. Grace period là gì?

Grace period là khoảng thời gian sau khi window end mà Kafka Streams vẫn chấp nhận record đến không đúng thứ tự cho cửa sổ đó.

Ví dụ cửa sổ [10:00, 10:05) có grace 2 phút:

~~~text
Window end:       10:05
Grace period:     10:05 ---------------- 10:07
                  |<------ 2 phút ----->|

Stream time chưa vượt mốc đóng cửa sổ:
  record event-time 10:04 đến muộn vẫn có thể cập nhật cửa sổ.

Stream time đã đi qua mốc 10:07:
  cửa sổ đã đóng; record đến sau mà thuộc cửa sổ này bị loại.
~~~

Grace không thay đổi event timestamp của record. Nó cũng không tự dịch record sang cửa sổ tiếp theo. Grace chỉ xác định cửa sổ còn mở để nhận dữ liệu out-of-order tới khi nào.

Một số điểm cần nhớ:

- Grace được tính từ window end, không tính từ lúc record đầu tiên đến.
- Record được phân loại theo event timestamp, còn việc cửa sổ đã đóng hay chưa phụ thuộc stream time của task.
- Record đến sau khi cửa sổ đóng sẽ bị loại khỏi phép tính cửa sổ tương ứng.
- Grace lớn hơn cho phép nhận dữ liệu trễ hơn nhưng kéo dài thời gian chốt kết quả và giữ state lâu hơn.
- Grace bằng 0 có nghĩa không có khoảng chờ cho record out-of-order sau khi cửa sổ kết thúc.
- Grace không phải retry delay của consumer và không phải Kafka topic retention.

Kafka Streams hiện đại yêu cầu chọn grace tường minh bằng các factory method như `ofSizeAndGrace` hoặc `ofSizeWithNoGrace`. Các API cũ từng có mặc định grace dài 24 giờ; Kafka đã loại bỏ mặc định đó để tránh vô tình giữ kết quả chưa chốt trong thời gian dài. Vì vậy không nên dựa vào constructor window cũ hoặc giả định mọi phiên bản có cùng default.

## 5. Ví dụ timeline: record được chấp nhận hay bị loại?

Giả sử tumbling window [10:00, 10:05), grace 2 phút. Mốc đóng là 10:07 theo stream time.

| Thứ tự nhận | Event timestamp | Stream time trước khi nhận | Kết quả |
|---|---:|---:|---|
| 1 | 10:01 | 10:00 | Chấp nhận, cập nhật cửa sổ |
| 2 | 10:04 | 10:01 | Chấp nhận, cập nhật cửa sổ |
| 3 | 10:02 | 10:04 | Chấp nhận; record out-of-order nhưng cửa sổ còn grace |
| 4 | 10:08 | 10:04 | Stream time tiến lên 10:08; cửa sổ 10:00 đã đóng |
| 5 | 10:03 | 10:08 | Bị loại khỏi cửa sổ [10:00, 10:05) vì đã quá grace |

Điểm dễ nhầm: record thứ 3 có timestamp nhỏ hơn stream time hiện tại, nhưng vẫn được chấp nhận vì window chưa đóng. Record thứ 5 có event timestamp thuộc cửa sổ cũ nhưng đến sau khi stream time đã vượt end + grace, nên không thể sửa kết quả cửa sổ đó.

Một record có timestamp tương lai bất thường có thể đẩy stream time tiến quá xa, làm nhiều cửa sổ cũ đóng sớm. Vì vậy cần kiểm tra timestamp tương lai, clock skew và dữ liệu replay trước khi đưa vào topology.

## 6. Cấu hình tumbling window với grace trong Kafka Streams DSL

Ví dụ đếm số đơn hàng theo customer ID, mỗi cửa sổ 5 phút và chấp nhận record đến muộn trong 2 phút:

~~~java
import java.time.Duration;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.apache.kafka.streams.state.WindowStore;

KTable<Windowed<String>, Long> counts = orders
    .groupByKey(Grouped.with(
        Serdes.String(),
        Serdes.String()
    ))
    .windowedBy(
        TimeWindows.ofSizeAndGrace(
            Duration.ofMinutes(5),
            Duration.ofMinutes(2)
        )
    )
    .count(
        Materialized
            .<String, Long, WindowStore<Bytes, byte[]>>as(
                "orders-per-customer-5m"
            )
            .withKeySerde(Serdes.String())
            .withValueSerde(Serdes.Long())
            .withRetention(Duration.ofHours(1))
    );
~~~

Giải thích:

- `groupByKey` nhóm record theo Kafka key; ví dụ key là customer ID.
- `TimeWindows.ofSizeAndGrace` tạo cửa sổ cố định 5 phút và grace 2 phút.
- `count` duy trì số lượng record theo key và window.
- `Materialized.as` đặt tên state store để theo dõi và phục hồi.
- `withRetention` giữ window state ít nhất đủ lâu cho window và grace; ví dụ 1 giờ lớn hơn 7 phút cần thiết.

Nếu đổi key trước khi group, dùng `groupBy` với `Grouped.with` để cung cấp Serde cho key mới và value. Kafka Streams có thể tạo repartition topic để đưa cùng key về cùng partition.

Đầu ra là KTable có key kiểu `Windowed<String>`, không phải String đơn thuần. Key bao gồm customer ID và thông tin cửa sổ để phân biệt cùng khách hàng ở nhiều window.

## 7. Kết quả cửa sổ thay đổi liên tục

Sau khi aggregate, KTable phát các bản cập nhật khi có record mới hoặc record đến muộn được chấp nhận.

Ví dụ cửa sổ [10:00, 10:05):

~~~text
Event A đến: count = 1
Event B đến: count = 2
Event C đến muộn nhưng còn grace: count = 3
~~~

Nếu chuyển KTable thành KStream ngay, downstream có thể nhận ba bản cập nhật: 1, 2 và 3. Đây là các giá trị mới nhất của cùng một windowed key, không phải ba số độc lập để cộng lại.

Consumer downstream phải hiểu semantics cập nhật:

- Nếu ghi vào bảng trạng thái, upsert theo customer + window.
- Nếu gửi tới hệ thống chỉ nhận kết quả cuối, không gửi các cập nhật tạm thời.
- Nếu tính tổng từ các bản cập nhật, phải xử lý changelog semantics thay vì cộng mọi giá trị.
- Nếu dùng compacted topic, cần key duy nhất cho từng customer/window và serializer cho windowed key.

### Chuyển KTable thành KStream

~~~java
KStream<Windowed<String>, Long> updates = counts.toStream();
~~~

KStream này chứa các lần cập nhật. Nó không tự biến các lần cập nhật thành một event nghiệp vụ duy nhất. Nếu output topic dùng windowed key, cấu hình `TimeWindowedSerde` tương ứng với key và kích thước window. Nếu không muốn windowed key ở tầng Kafka, có thể map thành key String và đưa window start/end vào value.

Ví dụ định dạng output dễ đọc:

~~~java
KStream<String, String> summaries = counts.toStream()
    .map((windowedKey, count) -> {
        String customerId = windowedKey.key();
        long start = windowedKey.window().start();
        long end = windowedKey.window().end();

        String value = start + "|" + end + "|" + count;
        return KeyValue.pair(customerId, value);
    });
~~~

Trong ví dụ này key đầu ra là customer ID; value chứa window start, end và count. Nếu cùng customer có nhiều window, key String đơn giản này sẽ bị trùng và record mới có thể ghi đè record trước trong compacted topic. Khi cần lưu nhiều cửa sổ, hãy dùng windowed key hoặc tạo key ghép như customerId + windowStart.

## 8. Chỉ phát kết quả cuối bằng Suppressed.untilWindowCloses

Một số nghiệp vụ cần chờ hết grace mới gửi kết quả, ví dụ:

- Chốt doanh thu theo từng 5 phút.
- Phát cảnh báo khi số giao dịch trong một giờ thấp hơn ngưỡng.
- Gửi báo cáo cuối kỳ tới hệ thống không hỗ trợ cập nhật.
- Tạo hóa đơn hoặc snapshot sau khi cửa sổ được đóng.

Kafka Streams cung cấp `Suppressed.untilWindowCloses` để giữ các bản cập nhật trung gian và chỉ phát giá trị cuối khi window đóng.

~~~java
import static org.apache.kafka.streams.kstream.Suppressed.BufferConfig.unbounded;

import org.apache.kafka.streams.kstream.Suppressed;

KTable<Windowed<String>, Long> finalCounts = counts.suppress(
    Suppressed.untilWindowCloses(unbounded())
);
~~~

Với cửa sổ 10:00–10:05 và grace 2 phút, kết quả cuối chỉ được phát khi stream time của task đi qua mốc đóng 10:07. Nếu có 10 event hợp lệ trong cửa sổ, downstream nhận một kết quả cuối có count 10, thay vì các bản cập nhật 1, 2, 3...10.

Grace và suppression có vai trò khác nhau:

| Thành phần | Quyết định |
|---|---|
| Window size | Event thuộc nhóm thời gian nào |
| Grace period | Cửa sổ chấp nhận record out-of-order đến khi nào |
| Suppressed.untilWindowCloses | Khi nào phát kết quả cuối thay vì phát mọi cập nhật |
| State retention | State được giữ lại trong store bao lâu |

Nếu không dùng suppression, kết quả vẫn được cập nhật liên tục. Grace vẫn quyết định record muộn có được chấp nhận hay không.

### Bộ đệm suppression

`unbounded()` dễ minh họa nhưng không có giới hạn bộ nhớ. Trong production, phải giới hạn buffer theo byte hoặc số record và chọn chính sách khi buffer đầy.

- `emitEarlyWhenFull()` giải phóng bộ nhớ bằng cách phát một số kết quả trước khi window đóng; điều này có thể phá yêu cầu “chỉ phát kết quả cuối”.
- `shutDownWhenFull()` giữ semantics không phát sớm nhưng có thể làm processor dừng khi buffer chạm giới hạn.
- Chọn giới hạn dựa trên số window đang mở, số key hoạt động, grace, tốc độ event và bộ nhớ cấp cho ứng dụng.

Không dùng buffer vô hạn trong production mà không ước lượng số window/key đồng thời. Grace càng dài và lưu lượng càng lớn, số kết quả phải giữ chờ càng nhiều.

## 9. Chọn grace period dựa trên độ trễ thực tế

Grace quá ngắn làm mất event đến trễ. Grace quá dài kéo dài thời gian chốt kết quả, tăng state retention và suppression buffer.

Nên đo phân phối độ trễ:

`event arrival delay = record arrival timestamp - event time`

Ví dụ, nếu 99.5% event đến trong vòng 45 giây và yêu cầu nghiệp vụ cho phép bỏ một tỷ lệ rất nhỏ dữ liệu trễ hơn, grace 1 phút có thể là điểm bắt đầu để thử nghiệm. Nếu nguồn có thể offline 20 phút và gửi bù, grace 1 phút sẽ không đáp ứng yêu cầu.

Quy trình chọn grace:

1. Thu thập timestamp nghiệp vụ và timestamp nhận record.
2. Tính độ trễ theo p50, p95, p99 và các trường hợp cực đại.
3. Phân loại nguồn có độ trễ khác nhau; không chỉ lấy trung bình toàn hệ thống.
4. Xác định SLA thời gian chốt kết quả.
5. Chọn grace đủ bao phủ phần lớn độ trễ được chấp nhận.
6. Đánh giá dung lượng state store và suppression buffer.
7. Chạy replay dữ liệu thực để đo tỷ lệ late record bị loại.
8. Theo dõi metric sau triển khai và điều chỉnh khi pattern thay đổi.

Không chọn grace bằng cách cộng một con số tùy ý. Cần cân bằng tính đầy đủ dữ liệu, độ trễ đầu ra và chi phí lưu state.

## 10. Grace period không phải retention của state store

Hai cấu hình này thường bị nhầm:

- Grace xác định thời gian chấp nhận record đến muộn cho một window.
- Retention xác định state store giữ dữ liệu cửa sổ trong bao lâu trước khi dọn.

Ví dụ window size 5 phút, grace 2 phút. State store phải giữ window đủ lâu để xử lý đến hết grace; retention không thể nhỏ hơn window size + grace. Có thể giữ lâu hơn nếu cần query hoặc vận hành có lý do.

~~~java
.count(
    Materialized
        .as("orders-per-customer-5m")
        .withKeySerde(Serdes.String())
        .withValueSerde(Serdes.Long())
        .withRetention(Duration.ofHours(1))
);
~~~

Một số lưu ý:

- Retention dài hơn không tự mở rộng grace. Record đến sau khi window đóng vẫn bị loại.
- Grace dài hơn không tự bảo đảm state được giữ đủ lâu nếu retention bị cấu hình sai.
- Retention quá ngắn có thể làm state của window bị dọn trước khi hết thời gian cần thiết.
- Retention quá dài làm tăng dung lượng disk, changelog và thời gian restore.
- Kafka Streams có retention mặc định cho window store; production nên đặt rõ khi yêu cầu nghiệp vụ cần kiểm soát.

Với session window, retention phải đáp ứng inactivity gap và grace tương ứng. Với join, cần kiểm tra retention của cả hai phía state store và cấu hình window/grace của join.

## 11. TimestampExtractor: chọn timestamp đúng

Mặc định Kafka Streams lấy timestamp metadata từ Kafka ConsumerRecord. Nếu producer đã gán timestamp đúng event time, cách này có thể đủ.

Nếu timestamp nghiệp vụ nằm trong payload, tạo một bean `TimestampExtractor`:

DTO `Purchase` được khai báo một lần trong package dùng chung để producer, Serde, extractor và function cùng sử dụng:

~~~java
import java.time.Instant;

public record Purchase(
    String customerId,
    long amount,
    Instant occurredAt
) {}
~~~

Đặt record này trong file `Purchase.java` ở package dùng chung của ứng dụng. Các ví dụ extractor và topology phía dưới cùng sử dụng DTO này.

~~~java
import java.time.Instant;

import org.apache.kafka.streams.errors.StreamsException;
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class EventTimestampConfiguration {

    @Bean
    TimestampExtractor purchaseTimestampExtractor() {
        return (record, partitionTime) -> {
            Object value = record.value();

            if (!(value instanceof Purchase purchase)
                    || purchase.occurredAt() == null) {
                throw new StreamsException(
                    "Purchase event is missing occurredAt"
                );
            }

            Instant occurredAt = purchase.occurredAt();
            long timestamp = occurredAt.toEpochMilli();

            if (timestamp < 0) {
                throw new StreamsException(
                    "Purchase event has an invalid timestamp"
                );
            }

            return timestamp;
        };
    }

}
~~~

Ví dụ giả định value đã được deserialize thành Purchase trước khi timestamp extractor đọc record. Nếu dữ liệu là JSON bytes hoặc String, extractor cần parse theo định dạng thực tế và phải xử lý lỗi parse có chủ đích.

Đăng ký extractor cho đúng input binding:

~~~yaml
spring:
  cloud:
    function:
      definition: purchaseWindowCounts

    stream:
      kafka:
        streams:
          bindings:
            purchaseWindowCounts-in-0:
              consumer:
                timestampExtractorBeanName: purchaseTimestampExtractor
~~~

Spring Cloud Stream Kafka Streams binder cho phép gắn bean TimestampExtractor theo từng consumer binding. Với function nhiều input, mỗi binding có thể cần timestamp extractor khác nhau nếu nguồn có quy ước timestamp khác nhau.

Không gán WallclockTimestampExtractor nếu mục tiêu là event-time window. Wall-clock extractor dùng thời điểm hiện tại khi record được xử lý, làm mất khả năng sắp xếp record theo thời điểm nghiệp vụ gốc.

## 12. Kiểm tra timestamp và clock skew

Timestamp là đầu vào quan trọng nhất của windowing. Một giá trị sai có thể làm sai kết quả của nhiều window.

Cần kiểm tra:

- Múi giờ và định dạng thời gian; lưu thời điểm tuyệt đối theo UTC.
- Timestamp có nằm trong giới hạn quá khứ/tương lai hợp lý không.
- Producer có đồng bộ đồng hồ bằng NTP hoặc cơ chế tương đương không.
- Có dùng timestamp từ client không đáng tin cậy không.
- Event replay có giữ nguyên event time ban đầu không.
- Broker đang dùng CreateTime hay LogAppendTime.
- TimestampExtractor có trả timestamp nhất quán cho mọi record cùng nguồn không.

Một record có timestamp tương lai xa có thể đẩy stream time tiến nhanh, đóng các cửa sổ cũ và khiến event đến sau bị xem là quá muộn. Có thể từ chối, cách ly hoặc chuẩn hóa timestamp bất thường trước khi đưa vào topology.

Nếu timestamp không hợp lệ, không âm thầm thay bằng thời gian hiện tại trừ khi đó là chính sách nghiệp vụ được định nghĩa. Việc thay timestamp có thể khiến event rơi vào window sai mà không còn cách truy nguyên.

## 13. Hopping window với grace

Hopping window có size và advance interval. Ví dụ tổng giao dịch trong 5 phút, cập nhật mỗi phút, grace 90 giây:

~~~java
import java.time.Duration;

import org.apache.kafka.streams.kstream.TimeWindows;

TimeWindows windows = TimeWindows
    .ofSizeAndGrace(
        Duration.ofMinutes(5),
        Duration.ofSeconds(90)
    )
    .advanceBy(Duration.ofMinutes(1));
~~~

Một event có thể cập nhật nhiều cửa sổ đang mở. Khi dùng suppression, mỗi window chỉ phát kết quả cuối khi stream time vượt end + grace của chính window đó.

Cần tính chi phí:

- Một event có thể thuộc nhiều window.
- Số state entry tăng theo mức chồng lấn.
- Suppression buffer phải giữ kết quả của nhiều window.
- Grace áp dụng cho từng window, nên thời điểm phát kết quả cuối khác nhau.
- Downstream cần nhận dạng cả key lẫn window boundaries.

Hopping phù hợp với dashboard rolling metrics nhưng có thể tốn state hơn tumbling. Đừng đặt advance quá nhỏ so với size nếu không cần cập nhật dày.

## 14. Session window với grace

Session window được xác định bởi inactivity gap. Các event cùng key được gom vào một session nếu khoảng cách giữa chúng nằm trong gap. Một event đến muộn có thể nối hoặc hợp nhất các session, làm thay đổi start/end và aggregate.

Ví dụ gap 5 phút:

~~~text
Event A 10:00
Event B 10:03      -> cùng session
Event C 10:11      -> session mới

Event D 10:07 đến muộn
Nếu session vẫn trong grace và D nối hai vùng hoạt động,
Kafka Streams có thể hợp nhất session theo timestamp.
~~~

Cấu hình:

~~~java
SessionWindows sessions = SessionWindows
    .ofInactivityGapAndGrace(
        Duration.ofMinutes(5),
        Duration.ofMinutes(2)
    );
~~~

Với session window, ranh giới có thể thay đổi khi event đến muộn được chấp nhận. Downstream không nên giả định một session key/window đã phát intermediate result sẽ luôn giữ nguyên. Nếu cần kết quả cuối, dùng suppression cho session window và thiết kế key/state store phù hợp.

Session window hữu ích cho phiên đăng nhập, phiên nghe nhạc, chuỗi tương tác hoặc thiết bị hoạt động liên tục. Hãy chọn inactivity gap theo ý nghĩa domain, không chỉ theo độ trễ mạng.

## 15. Grace trong stream-stream join

Grace cũng quan trọng với stream-stream join. Hai event cùng key có thể đến không đồng thời. Join window xác định độ lệch timestamp cho phép ghép cặp; grace cho phép record out-of-order tiếp tục tham gia trong khoảng sau khi cửa sổ join kết thúc.

Ví dụ ghép OrderPlaced và PaymentReceived nếu hai timestamp cách nhau tối đa 10 phút, grace 2 phút:

~~~java
import java.time.Duration;

import org.apache.kafka.streams.kstream.JoinWindows;

JoinWindows joinWindows = JoinWindows
    .ofTimeDifferenceAndGrace(
        Duration.ofMinutes(10),
        Duration.ofMinutes(2)
    );
~~~

Grace không làm rộng time difference của join. Time difference xác định hai record có đủ gần nhau để ghép không; grace xác định hệ thống còn chấp nhận record out-of-order cho join tới khi nào.

Cần xác định rõ:

- Hai stream có cùng key và partitioning không.
- Timestamp extractor của hai nguồn có cùng semantics không.
- Time difference là đối xứng hay cần before/after cụ thể.
- Record đến trễ sau grace bị loại như thế nào.
- State store retention có đủ cho cửa sổ join và grace không.
- Một record có thể ghép với nhiều record phía còn lại hay không.

Nếu một phía đến trễ lâu hơn grace, kết quả join có thể thiếu. Hãy đo độ trễ của từng nguồn riêng biệt; không chọn grace theo nguồn nhanh hơn.

## 16. Xử lý record bị loại sau grace

Kafka Streams không tự chuyển mọi late record sang DLQ. Khi record đã quá grace đối với window operation, nó bị bỏ qua cho phép tính cửa sổ tương ứng. Đây là hành vi khác với exception khi deserialize hoặc exception do business processor ném ra.

Để không mất khả năng điều tra:

1. Theo dõi metric record bị drop và độ trễ event.
2. Ghi log có chọn lọc key, topic, partition, offset, timestamp và window liên quan.
3. Giữ raw topic đủ lâu để có thể replay/backfill.
4. Tách luồng dữ liệu quá muộn sang topic quarantine nếu nghiệp vụ cần xử lý riêng.
5. Có quy trình tính bù hoặc sửa kết quả nếu event đến sau grace.
6. Phân biệt late record bị drop khỏi window với record bị lỗi deserialize hoặc processing exception.

Một chiến lược là tạo nhánh kiểm tra độ trễ trước window aggregation bằng custom Processor API hoặc logic timestamp-aware. Nhánh đó có thể gửi metadata của record quá cũ sang topic riêng. Tuy nhiên, việc phân loại phải dùng cùng quy tắc window và stream time như topology chính; không chỉ so timestamp với System.currentTimeMillis.

Nếu không có nhánh quarantine, raw input topic và khả năng replay vẫn là lớp bảo vệ để điều tra. Nhưng replay bằng cùng application ID có thể tiếp tục dùng committed offsets và state hiện tại; cần quy trình reset hoặc một application ID riêng cho backfill, đồng thời cô lập output để tránh ghi trùng.

## 17. Ví dụ đầy đủ với Spring Cloud Stream Kafka Streams binder

Function nhận Purchase, nhóm theo customer ID, đếm số đơn trong window 5 phút, chấp nhận late record 2 phút và chỉ phát kết quả cuối.

Bean `Serde<Purchase>` có kiểu generic khớp với input function nên Kafka Streams binder có thể suy luận Serde cho value đầu vào. Binder cũng suy luận String Serde cho key và output String; nếu ứng dụng dùng Serde riêng hoặc suy luận không phù hợp, khai báo `keySerde`/`valueSerde` theo từng binding.

~~~java
import java.time.Duration;

import java.util.function.Function;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Suppressed;
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.state.WindowStore;
import org.springframework.kafka.support.serializer.JsonSerde;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class PurchaseWindowTopology {

    @Bean
    Serde<Purchase> purchaseSerde() {
        return new JsonSerde<>(Purchase.class);
    }

    @Bean
    Function<KStream<String, Purchase>, KStream<String, String>>
            purchaseWindowCounts(Serde<Purchase> purchaseSerde) {

        return purchases -> purchases
            .filter((key, purchase) ->
                purchase != null && purchase.customerId() != null
            )
            .groupBy(
                (key, purchase) -> purchase.customerId(),
                Grouped.with(Serdes.String(), purchaseSerde)
            )
            .windowedBy(
                TimeWindows.ofSizeAndGrace(
                    Duration.ofMinutes(5),
                    Duration.ofMinutes(2)
                )
            )
            .count(
                Materialized
                    .<String, Long, WindowStore<Bytes, byte[]>>as(
                        "purchase-count-by-customer-5m"
                    )
                    .withKeySerde(Serdes.String())
                    .withValueSerde(Serdes.Long())
                    .withRetention(Duration.ofHours(1))
            )
            .suppress(
                Suppressed.untilWindowCloses(
                    Suppressed.BufferConfig.unbounded()
                )
            )
            .toStream()
            .map((windowedKey, count) -> {
                String customerId = windowedKey.key();
                long start = windowedKey.window().start();
                long end = windowedKey.window().end();

                String summary = start + "|" + end + "|" + count;
                return KeyValue.pair(customerId, summary);
            });
    }

}
~~~

Trong production, thay `unbounded()` bằng buffer có giới hạn và chính sách đầy phù hợp. Nếu output topic compacted và có nhiều window cho cùng customer, key đầu ra phải chứa window start để mỗi cửa sổ có một key riêng; ví dụ `customerId + "|" + start`.

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: purchaseWindowCounts

    stream:
      bindings:
        purchaseWindowCounts-in-0:
          destination: purchases.events

        purchaseWindowCounts-out-0:
          destination: purchases.window-counts

      kafka:
        streams:
          binder:
            applicationId: purchase-window-counter-v1
~~~

Nếu timestamp event nằm trong payload, đăng ký `TimestampExtractor` bean và cấu hình bean name cho input binding như phần trước. Nếu Kafka record timestamp đã là event time, có thể dùng extractor mặc định.

## 18. Kiểm thử window và late event với TopologyTestDriver

TopologyTestDriver cho phép tạo input record với timestamp cụ thể, kiểm tra window boundary và xác nhận event muộn được chấp nhận hay loại.

Ví dụ logic cần kiểm thử. Đoạn code dưới đây giả định `testDriver`, các serializer/deserializer và topology tương ứng đã được khởi tạo ở phần setup của test:

- Window [10:00, 10:05), grace 2 phút.
- Event timestamp 10:01 và 10:04 được tính.
- Event timestamp 10:03 đến sau nhưng trước khi stream time đi qua 10:07 vẫn được tính.
- Một record timestamp 10:08 đẩy stream time qua grace.
- Event timestamp 10:04 đến sau đó bị loại khỏi window cũ.
- Suppression chỉ phát kết quả cuối khi window đóng.

~~~java
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;

// Tạo input/output topic từ TopologyTestDriver với Serde đúng.
TestInputTopic<String, Purchase> input = testDriver.createInputTopic(
    "purchases.events",
    stringSerializer,
    purchaseSerializer
);
TestOutputTopic<String, String> output = testDriver.createOutputTopic(
    "purchases.window-counts",
    stringDeserializer,
    stringDeserializer
);

input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 100, Instant.parse("2026-11-24T10:01:00Z")),
    Instant.parse("2026-11-24T10:01:00Z")
);

input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 200, Instant.parse("2026-11-24T10:04:00Z")),
    Instant.parse("2026-11-24T10:04:00Z")
);

// Record out-of-order nhưng cửa sổ vẫn còn grace.
input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 150, Instant.parse("2026-11-24T10:03:00Z")),
    Instant.parse("2026-11-24T10:03:00Z")
);

// Gửi record có timestamp sau 10:07 để đẩy stream time và đóng window cũ.
input.pipeInput(
    "customer-99",
    new Purchase("customer-99", 50, Instant.parse("2026-11-24T10:08:00Z")),
    Instant.parse("2026-11-24T10:08:00Z")
);

// Record thuộc window cũ nhưng đến sau khi window đã đóng.
input.pipeInput(
    "customer-42",
    new Purchase("customer-42", 75, Instant.parse("2026-11-24T10:04:30Z")),
    Instant.parse("2026-11-24T10:04:30Z")
);

List<KeyValue<String, String>> finalResults = output.readKeyValuesToList();
assertEquals(1, finalResults.size());
assertEquals("customer-42", finalResults.get(0).key);
assertTrue(finalResults.get(0).value.endsWith("|3"));
~~~

Test cần đọc output theo key/window đã thiết kế và xác nhận count cuối của customer-42 là 3, không phải 4. Nếu dùng suppression, output cửa sổ cũ chỉ xuất hiện sau record timestamp 10:08 đẩy stream time vượt mốc đóng.

Lưu ý:

- `advanceWallClockTime` không thay thế việc đẩy stream time bằng record timestamp.
- Để kiểm tra late record, phải điều khiển timestamp của input record.
- Test record đúng ranh giới window, ví dụ timestamp 10:05 thuộc window tiếp theo.
- Test event timestamp tương lai bất thường.
- Test không có record mới để xác nhận suppression chưa phát chỉ vì wall clock trôi qua.
- Test hopping/session windows riêng vì semantics window khác tumbling.

## 19. Integration test với Kafka thật

Unit test xác minh logic DSL, còn integration test cần xác minh binder, timestamp extractor, Serde và broker.

Dùng Testcontainers Kafka hoặc môi trường Kafka thử nghiệm để kiểm tra:

1. Function bean được kích hoạt và input/output binding trỏ đúng topic.
2. Kafka record timestamp hoặc custom TimestampExtractor được sử dụng đúng.
3. Payload có event time khác timestamp Kafka được đặt vào window đúng.
4. Event out-of-order trong grace cập nhật aggregate.
5. Event sau grace không thay đổi aggregate cuối.
6. Suppression phát một kết quả cuối khi stream time vượt end + grace.
7. Restart ứng dụng phục hồi state store và không làm mất aggregate.
8. Output key giữ đủ customer ID và window identity.
9. Window retention và changelog hoạt động với cấu hình production.
10. Metric/log cho record bị drop có thể được quan sát.

Không chỉ dùng sleep để đợi 2 phút trong test. Hãy điều khiển timestamp record để đẩy stream time. Test sẽ nhanh, ổn định và không phụ thuộc đồng hồ máy chạy CI.

## 20. Quan sát và vận hành trong production

Một topology windowed cần quan sát cả độ trễ dữ liệu lẫn tiến độ xử lý.

Nên theo dõi:

- Processing lag của input partition.
- Độ trễ event arrival so với event time.
- Stream time của task và khoảng cách với event time mới nhất.
- Số record bị drop do quá grace hoặc lỗi timestamp.
- Số window đang mở và lượng dữ liệu trong state store.
- Dung lượng suppression buffer và số lần buffer chạm ngưỡng.
- Restore time của state store sau restart.
- Rebalance, task migration và consumer errors.
- Tỷ lệ event timestamp bất thường hoặc lệch clock.
- Số lần replay/backfill và số record được xử lý lại.

Metric cụ thể phụ thuộc phiên bản Kafka Streams, binder và exporter. Hãy xác định metric có sẵn trong runtime thực tế thay vì hard-code tên metric từ một phiên bản khác. Log điều tra nên kèm topic, partition, offset, key, record timestamp, window start/end và application ID.

Nếu grace được tăng trong production, kiểm tra tác động tới suppression buffer và thời gian phát output. Nếu grace giảm, xác định liệu dữ liệu cũ có thể bị loại nhiều hơn và cần backfill không.

## 21. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Event đến muộn bị tính vào sai window | Dùng processing time thay vì event time | Kiểm tra Kafka timestamp và TimestampExtractor |
| Event out-of-order bị loại quá sớm | Grace quá ngắn hoặc stream time đã tiến xa | Đo độ trễ và chọn grace phù hợp |
| Không thấy kết quả cuối | Stream time chưa đi qua end + grace | Kiểm tra timestamp của record mới và suppression |
| Wall clock đã qua window nhưng output chưa phát | Stream time không tự tiến khi không có record | Hiểu stream-time semantics; không dựa vào sleep |
| Kết quả bị phát nhiều lần | KTable được chuyển thành KStream không suppression | Chấp nhận upsert hoặc dùng untilWindowCloses |
| Downstream cộng sai số | Coi các bản cập nhật KTable như event độc lập | Upsert theo key/window hoặc dùng kết quả cuối |
| State store tăng dung lượng | Window/hopping/grace/retention quá lớn | Đo key cardinality và giảm phạm vi hợp lý |
| Buffer suppression đầy | Nhiều window mở hoặc grace dài | Giới hạn buffer, theo dõi và chọn chính sách đầy |
| Window bị đóng quá sớm | Timestamp tương lai hoặc clock skew | Validate event time và đồng hồ nguồn |
| Join thiếu dữ liệu | Grace của join không đủ hoặc hai nguồn lệch độ trễ | Đo từng nguồn, điều chỉnh time difference và grace |
| Replay không sửa được kết quả | Dữ liệu replay vẫn quá muộn so với stream time/state hiện tại | Dùng quy trình backfill/reset có cô lập output |
| Test chờ mãi không có kết quả | Test chỉ advance wall clock | Gửi record timestamp mới để advance stream time |

## 22. Checklist thiết kế trước khi triển khai

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Event time | Timestamp đến từ producer, broker hay payload? |
| Timestamp extractor | Có cần custom extractor theo input binding không? |
| Clock | Nguồn có đồng bộ UTC và giới hạn timestamp tương lai không? |
| Window type | Tumbling, hopping, sliding hay session phù hợp domain? |
| Window boundaries | Đầu/cuối cửa sổ có đúng semantics mong muốn không? |
| Grace | Độ trễ p99 của nguồn là bao nhiêu? |
| Stream time | Có hiểu stream time chỉ tiến khi task xử lý record không? |
| Late event | Record sau grace bị drop, quarantine hay backfill? |
| Output | Phát intermediate updates hay final-only? |
| Suppression | Buffer có giới hạn và chính sách khi đầy chưa? |
| Retention | State store giữ ít nhất window size + grace chưa? |
| Key | Output key có chứa window identity không? |
| Recovery | Changelog và local state có thể phục hồi sau restart không? |
| Testing | Có test boundary, out-of-order, after-grace và idle stream không? |
| Monitoring | Có metric lateness, dropped records, state size và restore time không? |

## 23. Bài thực hành và tiêu chí hoàn thành

Xây dựng topology đếm số đơn hàng theo customer trong cửa sổ 5 phút:

1. Tạo topic `purchases.events` với key là customer ID.
2. Xác định event time là `occurredAt` trong payload.
3. Viết `TimestampExtractor` và gắn vào input binding.
4. Tạo KStream và group theo customer ID.
5. Dùng tumbling window 5 phút với grace 2 phút.
6. Materialize state store với tên rõ ràng và retention ít nhất 7 phút.
7. Chạy một tập record theo thứ tự thời gian và kiểm tra count.
8. Gửi một event out-of-order trước khi stream time vượt end + grace; xác nhận count tăng.
9. Đẩy stream time vượt end + grace rồi gửi event thuộc window cũ; xác nhận count không đổi.
10. So sánh output liên tục với output dùng `Suppressed.untilWindowCloses`.
11. Kiểm tra record timestamp đúng ranh giới window.
12. Kiểm tra timestamp tương lai bất thường và event replay.
13. Viết TopologyTestDriver test cho late event và suppression.
14. Chạy integration test với Kafka binder và broker thật.
15. Ghi lại lựa chọn grace, retention, output semantics và kế hoạch xử lý record quá muộn.

Hoàn thành bài khi có thể giải thích event time, processing time và stream time; tính được ranh giới window và grace; dự đoán record nào được chấp nhận hoặc bị drop; phân biệt grace với retention; lựa chọn phát intermediate hay final result; và kiểm thử được hành vi của topology khi dữ liệu đến muộn.

## 24. Tài liệu tham khảo chính thức

- [Apache Kafka Streams — Streams DSL: Windowing and Grace](https://kafka.apache.org/41/streams/developer-guide/dsl-api/) — tumbling, hopping, sliding, session windows, grace period, late record và final window results.
- [Apache Kafka Streams — Upgrade Guide](https://kafka.apache.org/41/streams/upgrade-guide/) — thay đổi API grace và việc loại bỏ grace mặc định 24 giờ.
- [Apache Kafka Streams — Configuring a Streams Application](https://kafka.apache.org/41/streams/developer-guide/config-streams/) — timestamp, state store và cấu hình runtime.
- [Apache Kafka Streams — Application Reset Tool](https://kafka.apache.org/41/streams/developer-guide/app-reset-tool/) — quy trình reset/replay khi cần dựng lại state.
- [Spring Cloud Stream — Kafka Streams Binder: Timestamp Extractor](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/timestamp-extractor.html) — khai báo TimestampExtractor bean và gắn bean theo input binding.
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html) — binder configuration và các thuộc tính Kafka Streams.
- [Apache Kafka — TimeWindows API](https://kafka.apache.org/41/javadoc/org/apache/kafka/streams/kstream/TimeWindows.html) — cấu hình size, advance interval và grace.
- [Apache Kafka — Suppressed API](https://kafka.apache.org/41/javadoc/org/apache/kafka/streams/kstream/Suppressed.html) — buffer, untilWindowCloses và chính sách khi đầy.

