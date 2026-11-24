# Tổng hợp dữ liệu thiết bị theo cửa sổ bằng Kafka Streams Binder

Một hệ thống IoT có thể nhận hàng nghìn phép đo nhiệt độ và độ ẩm mỗi giây từ nhiều thiết bị. Nếu chỉ lưu từng message, ứng dụng phân tích phải tự nhóm dữ liệu, tính trung bình và xác định khoảng thời gian. Kafka Streams có thể thực hiện công việc này ngay trên luồng sự kiện: định tuyến record theo thiết bị, gom record vào cửa sổ thời gian, duy trì trạng thái tổng hợp và phát kết quả sang một topic khác.

Bài thực hành xây dựng pipeline Spring Cloud Stream sử dụng Kafka Streams Binder. Mỗi event có device ID, thời điểm đo, nhiệt độ và độ ẩm. Ứng dụng nhóm theo device ID, tổng hợp trong cửa sổ tumbling một phút, chấp nhận event đến trễ trong 15 giây và xuất summary cho từng thiết bị/cửa sổ.

Nội dung kết hợp mô hình hàm Supplier/Function/Consumer, binder, Kafka Streams DSL, event-time, Serde, state store, kiểm thử và vận hành. Ví dụ hướng tới Java 17+ và phiên bản Kafka Streams có API TimeWindows.ofSizeAndGrace; cần dùng Spring Boot, Spring Cloud release train và Kafka Streams Binder tương thích theo BOM của dự án.

## 1. Kết quả mong đợi và kiến trúc

Nguồn dữ liệu phát các record như sau:

| deviceId | eventTime | temperatureC | humidityPercent |
|---|---|---:|---:|
| sensor-101 | 10:00:05 | 26.2 | 61.0 |
| sensor-101 | 10:00:18 | 26.8 | 60.5 |
| sensor-205 | 10:00:21 | 24.1 | 55.0 |
| sensor-101 | 10:00:54 | 27.0 | 60.0 |
| sensor-205 | 10:01:02 | 24.4 | 54.5 |

Với cửa sổ một phút bắt đầu lúc 10:00:00, kết quả của sensor-101 có thể gồm số lượng mẫu, nhiệt độ trung bình, thấp nhất, cao nhất và độ ẩm trung bình. sensor-205 có summary riêng. Các cửa sổ tiếp theo không ghi đè kết quả cửa sổ trước vì output key chứa cả device ID và thời điểm bắt đầu cửa sổ.

Kiến trúc tổng quát:

    IoT devices
        |
        v
    telemetry producer
        |
        v
    Kafka topic: device-readings
        |
        v
    Kafka Streams Binder
        |
        v
    Function<KStream, KStream>
        |
        +--> validate event
        +--> key by deviceId
        +--> repartition if required
        +--> group by key
        +--> event-time window
        +--> aggregate into state store
        |
        v
    Kafka topic: device-window-summaries
        |
        v
    dashboard / alerting / downstream consumers

Binder quản lý kết nối input/output binding của Spring Cloud Stream với Kafka Streams runtime. Kafka Streams DSL thực hiện grouping, windowing, aggregation và state management. Phần business transformation vẫn nằm trong function bean.

## 2. Chuẩn bị project và dependency

Ứng dụng cần Kafka Streams Binder. Dùng dependency do Spring Cloud BOM quản lý version:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Nếu ứng dụng còn có các function dùng Kafka MessageChannel Binder, chỉ thêm Kafka Binder thường khi thật sự cần. Kafka Streams Binder là integration dành cho Kafka Streams API và có cấu hình, lifecycle, topology riêng.

Các dependency thường đã được quản lý bởi Spring Boot/Spring Cloud BOM:
- Spring Boot starter và Spring Cloud Stream.
- Kafka Streams API tương thích với binder.
- Spring Kafka để dùng JsonSerde.
- Jackson Java Time module nếu ứng dụng cần deserialize java.time.Instant trong JSON.

Không pin tùy tiện các phiên bản Spring Cloud Stream, Kafka Streams và Spring Kafka riêng lẻ. Dùng release train/BOM tương thích, sau đó kiểm tra dependency tree nếu xuất hiện lỗi class hoặc method không tương thích.

## 3. Thiết kế event và output contract

Event đầu vào biểu diễn một lần đo:

~~~java
import java.time.Instant;

public record DeviceReading(
        String deviceId,
        Instant eventTime,
        double temperatureC,
        double humidityPercent) {
}
~~~

Output là kết quả tổng hợp của một thiết bị trong một cửa sổ:

~~~java
public record DeviceWindowSummary(
        String deviceId,
        long windowStartEpochMs,
        long windowEndEpochMs,
        long readingCount,
        double averageTemperatureC,
        double minTemperatureC,
        double maxTemperatureC,
        double averageHumidityPercent) {
}
~~~

Các field có ý nghĩa rõ ràng:
- deviceId xác định thiết bị và là khóa nhóm.
- eventTime là thời điểm sự kiện xảy ra ở thiết bị, không nhất thiết là lúc Kafka nhận record.
- readingCount cho biết số mẫu hợp lệ được tính vào summary.
- windowStartEpochMs và windowEndEpochMs xác định cửa sổ.
- Các giá trị average/min/max được tính từ mẫu hợp lệ.

Nên thống nhất timezone và đơn vị. Ví dụ nhiệt độ dùng độ C, độ ẩm là phần trăm từ 0 đến 100, timestamp dùng UTC epoch milliseconds khi trao đổi giữa hệ thống. Nếu producer gửi timestamp không rõ timezone hoặc dùng giây thay vì milliseconds, cửa sổ sẽ phân loại sai.

## 4. Phân biệt record key và device ID trong payload

Kafka Streams groupByKey nhóm theo Kafka record key. Nó không tự đọc deviceId trong JSON payload để suy ra khóa.

Nếu producer đã ghi key bằng deviceId, có thể gọi groupByKey trực tiếp. Nếu producer ghi key rỗng hoặc dùng một khóa khác, cần chọn lại key từ payload:

~~~java
.selectKey((oldKey, reading) -> reading.deviceId())
.groupByKey(Grouped.with(Serdes.String(), readingSerde))
~~~

selectKey thay đổi record key. Khi thao tác tiếp theo yêu cầu partitioning theo key, Kafka Streams có thể tạo repartition topic nội bộ để chuyển record tới partition tương ứng. Repartition giúp tất cả record cùng deviceId đi tới cùng task/partition, nhưng có chi phí network, serialization, disk và latency.

Nếu producer có thể tạo key đúng ngay từ đầu, thường nên làm ở producer để giảm một lần repartition. Tuy nhiên, topology vẫn phải bảo đảm key semantics; không chỉ tin vào tên topic.

## 5. Chọn cửa sổ thời gian

Kafka Streams cung cấp nhiều kiểu cửa sổ:

| Loại | Cách hoạt động | Ví dụ sử dụng |
|---|---|---|
| Tumbling | Các cửa sổ cố định, không chồng lấn | Trung bình mỗi phút hoặc mỗi giờ |
| Hopping | Cửa sổ cố định nhưng bước tiến nhỏ hơn kích thước, có chồng lấn | Trung bình 5 phút cập nhật mỗi 1 phút |
| Sliding | Cửa sổ dựa trên khoảng cách thời gian giữa các record | Phân tích các event gần nhau |
| Session | Cửa sổ mở rộng theo hoạt động, đóng sau một khoảng idle | Phiên hoạt động của thiết bị/người dùng |

Bài này chọn tumbling window một phút. Các khoảng thời gian là nửa mở: thời điểm bắt đầu được tính vào cửa sổ, thời điểm đúng bằng mốc kết thúc thuộc cửa sổ kế tiếp. Ví dụ cửa sổ từ 10:00:00 đến 10:01:00 chứa event có timestamp từ 10:00:00 đến trước 10:01:00.

Kích thước cửa sổ và grace period là hai khái niệm khác nhau:
- Window size xác định phạm vi thời gian được tổng hợp.
- Grace period cho phép event đến muộn được cập nhật cửa sổ sau thời điểm kết thúc.
- Event đến sau khi stream time vượt quá window end cộng grace sẽ bị xem là quá trễ và không được đưa vào phép tổng hợp của cửa sổ đó.

Với window size một phút và grace 15 giây, event thuộc cửa sổ 10:00 có thể được chấp nhận trong thời gian grace sau 10:01, tùy stream time của partition/task. Không nên hiểu grace là một bộ hẹn giờ độc lập chính xác theo đồng hồ máy chủ; Kafka Streams sử dụng stream time dựa trên timestamp của record được xử lý.

## 6. Event time và processing time

Đây là quyết định quan trọng nhất của bài thực hành.

- Event time: thời điểm thiết bị thực hiện phép đo.
- Ingestion time: thời điểm broker nhận record.
- Processing time: thời điểm ứng dụng xử lý record.

Window aggregation mặc định sử dụng timestamp mà Kafka Streams lấy từ record theo TimestampExtractor. Nếu producer đặt Kafka record timestamp theo thời điểm tạo event, mặc định có thể phù hợp. Nhưng nếu eventTime chỉ nằm trong JSON payload còn Kafka record timestamp là thời điểm publish, window sẽ theo ingestion timestamp chứ không tự động dùng field eventTime.

Với dữ liệu IoT, thiết bị có thể mất mạng rồi gửi bù dữ liệu. Khi đó event-time thường phù hợp hơn processing-time. Cần cấu hình TimestampExtractor để đọc eventTime từ payload hoặc đưa timestamp vào record metadata ngay tại producer.

Ví dụ TimestampExtractor:

~~~java
import org.apache.kafka.clients.consumer.ConsumerRecord;
import org.apache.kafka.streams.processor.TimestampExtractor;

public class DeviceEventTimestampExtractor implements TimestampExtractor {

    @Override
    public long extract(ConsumerRecord<Object, Object> record,
                        long partitionTime) {
        Object value = record.value();

        if (value instanceof DeviceReading reading
                && reading.eventTime() != null) {
            return reading.eventTime().toEpochMilli();
        }

        // Fallback chỉ nên dùng nếu hợp đồng dữ liệu cho phép.
        return record.timestamp();
    }
}
~~~

Nếu eventTime thiếu hoặc sai định dạng, không nên âm thầm gán thời gian hiện tại vì sẽ đưa event lỗi vào cửa sổ sai. Có thể từ chối record, phát cảnh báo hoặc chuyển payload lỗi sang luồng cách ly. Fallback sang record.timestamp chỉ phù hợp khi đó là chính sách được thống nhất.

## 7. Cấu hình TimestampExtractor cho input binding

Khai báo extractor thành Spring bean với tên ổn định:

~~~java
import org.apache.kafka.streams.processor.TimestampExtractor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DeviceStreamConfiguration {

    @Bean
    TimestampExtractor deviceEventTimestampExtractor() {
        return new DeviceEventTimestampExtractor();
    }
}
~~~

Với Kafka Streams Binder, binding consumer có thuộc tính timestampExtractorBeanName để tham chiếu bean. Tên property và cách cấu hình cần khớp release binder đang dùng.

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            aggregateDeviceWindows-in-0:
              consumer:
                timestampExtractorBeanName: deviceEventTimestampExtractor
~~~

Nếu không cấu hình extractor, hãy chắc chắn producer đặt Kafka record timestamp theo event-time mà topology mong đợi. Viết test với event đến trễ và timestamp lệch nhau để chứng minh extractor được sử dụng đúng.

## 8. Tạo Serde cho payload và state

Kafka lưu byte array; Kafka Streams cần Serializer/Deserializer (Serde) để chuyển đổi key và value. Trong ví dụ:
- Key là String.
- Input value là DeviceReading.
- State store value là DeviceAggregate.
- Output value là DeviceWindowSummary.

Spring Kafka có JsonSerde để dùng JSON. Có thể tạo các lớp Serde cụ thể với public no-argument constructor để binder cấu hình bằng class name:

~~~java
import org.springframework.kafka.support.serializer.JsonSerde;

public class DeviceReadingSerde extends JsonSerde<DeviceReading> {
    public DeviceReadingSerde() {
        super(DeviceReading.class);
    }
}

public class DeviceAggregateSerde extends JsonSerde<DeviceAggregate> {
    public DeviceAggregateSerde() {
        super(DeviceAggregate.class);
    }
}

public class DeviceWindowSummarySerde extends JsonSerde<DeviceWindowSummary> {
    public DeviceWindowSummarySerde() {
        super(DeviceWindowSummary.class);
    }
}
~~~

Đặt mỗi lớp public trong file Java riêng, với package tương ứng trong cấu hình binder. Các lớp Serde phải có public no-argument constructor để binder có thể khởi tạo theo class name.

Với Java record chứa Instant, kiểm tra Jackson Java Time module và cấu hình ObjectMapper mà JsonSerde sử dụng. Không coi JSON là schema registry: nếu cần quản lý schema version, compatibility và schema ID, dùng serializer/Serde tương ứng với registry đã chọn.

## 9. Xây dựng đối tượng state aggregate

Aggregate giữ các giá trị đủ để cập nhật kết quả mà không phải lưu toàn bộ danh sách phép đo:

~~~java
public record DeviceAggregate(
        long count,
        double temperatureSum,
        double humiditySum,
        double minTemperatureC,
        double maxTemperatureC) {

    public static DeviceAggregate empty() {
        return new DeviceAggregate(
                0,
                0,
                0,
                0,
                0);
    }

    public DeviceAggregate add(DeviceReading reading) {
        double min = count == 0
                ? reading.temperatureC()
                : Math.min(minTemperatureC, reading.temperatureC());

        double max = count == 0
                ? reading.temperatureC()
                : Math.max(maxTemperatureC, reading.temperatureC());

        return new DeviceAggregate(
                count + 1,
                temperatureSum + reading.temperatureC(),
                humiditySum + reading.humidityPercent(),
                min,
                max);
    }

    public double averageTemperatureC() {
        return count == 0 ? 0 : temperatureSum / count;
    }

    public double averageHumidityPercent() {
        return count == 0 ? 0 : humiditySum / count;
    }
}
~~~

Aggregate chỉ lưu count, sum, min và max. Khi có event mới, cập nhật các trường này trong thời gian hằng số. Không giữ một List chứa tất cả record trong cửa sổ vì memory tăng theo số event và cửa sổ tải cao có thể làm state store phình lớn.

Với nghiệp vụ cần percentile hoặc median, sum/count không đủ. Có thể dùng thuật toán streaming như t-digest hoặc histogram, nhưng phải chọn cấu trúc state có kích thước kiểm soát và Serde tương ứng.

## 10. Viết Function tổng hợp theo cửa sổ

Function nhận KStream có key String và value DeviceReading, rồi trả KStream có key String và value DeviceWindowSummary.

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
import org.apache.kafka.streams.kstream.TimeWindows;
import org.apache.kafka.streams.kstream.Windowed;
import org.apache.kafka.streams.state.WindowStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class DeviceWindowFunctions {

    @Bean
    Function<KStream<String, DeviceReading>,
             KStream<String, DeviceWindowSummary>> aggregateDeviceWindows() {

        Serde<String> stringSerde = Serdes.String();
        Serde<DeviceReading> readingSerde = new DeviceReadingSerde();
        Serde<DeviceAggregate> aggregateSerde = new DeviceAggregateSerde();

        return input -> input
                .filter((key, reading) -> isValid(reading))
                .selectKey((oldKey, reading) -> reading.deviceId())
                .groupByKey(Grouped.with(stringSerde, readingSerde))
                .windowedBy(TimeWindows.ofSizeAndGrace(
                        Duration.ofMinutes(1),
                        Duration.ofSeconds(15)))
                .aggregate(
                        DeviceAggregate::empty,
                        (deviceId, reading, aggregate) ->
                                aggregate.add(reading),
                        Materialized
                                .<String, DeviceAggregate,
                                        WindowStore<Bytes, byte[]>>as(
                                                "device-window-aggregate")
                                .withKeySerde(stringSerde)
                                .withValueSerde(aggregateSerde))
                .toStream()
                .map((windowedKey, aggregate) -> toSummary(
                        windowedKey,
                        aggregate));
    }

    private static boolean isValid(DeviceReading reading) {
        return reading != null
                && reading.deviceId() != null
                && !reading.deviceId().isBlank()
                && reading.eventTime() != null
                && Double.isFinite(reading.temperatureC())
                && Double.isFinite(reading.humidityPercent())
                && reading.humidityPercent() >= 0
                && reading.humidityPercent() <= 100;
    }

    private static KeyValue<String, DeviceWindowSummary> toSummary(
            Windowed<String> windowedKey,
            DeviceAggregate aggregate) {

        long start = windowedKey.window().start();
        long end = windowedKey.window().end();

        String outputKey = windowedKey.key() + "|" + start;

        DeviceWindowSummary summary = new DeviceWindowSummary(
                windowedKey.key(),
                start,
                end,
                aggregate.count(),
                aggregate.averageTemperatureC(),
                aggregate.minTemperatureC(),
                aggregate.maxTemperatureC(),
                aggregate.averageHumidityPercent());

        return KeyValue.pair(outputKey, summary);
    }
}
~~~

Các bước trong topology:

1. filter loại bỏ record không đáp ứng hợp đồng dữ liệu cơ bản.
2. selectKey lấy deviceId làm Kafka record key.
3. groupByKey nhóm các record có cùng thiết bị.
4. windowedBy chia record theo cửa sổ thời gian.
5. aggregate cập nhật state cho từng cặp thiết bị/cửa sổ.
6. toStream chuyển KTable kết quả thành luồng cập nhật.
7. map tạo output key duy nhất cho từng thiết bị và window start.

Ví dụ chỉ lọc event sai để làm rõ topology. Trong production, không nên drop im lặng: hãy đếm metric invalid, log có giới hạn và định tuyến payload lỗi tới DLQ/quarantine theo yêu cầu nghiệp vụ.

## 11. Vì sao output key phải chứa window start?

Nếu output key chỉ là deviceId, mỗi cửa sổ mới sẽ ghi cùng một key. Khi downstream dùng KTable hoặc output topic có log compaction, summary mới có thể thay thế summary cũ của thiết bị đó.

Trong bài này output key là:

    deviceId|windowStartEpochMs

Ví dụ:

    sensor-101|1795514400000
    sensor-101|1795514460000

Nhờ vậy mỗi cửa sổ có định danh riêng. Nếu downstream cần update cùng một cửa sổ khi event đến muộn trong grace period, output key giữ nguyên cho cửa sổ đó; record mới cập nhật summary của cùng key.

Một phương án khác là dùng composite key có schema rõ ràng thay vì nối chuỗi. Nếu downstream cần partition theo deviceId, có thể dùng deviceId làm Kafka key và đưa windowStart vào value, nhưng khi đó topic chỉ giữ latest update theo key nếu compacted. Hãy chọn key theo contract của consumer downstream.

## 12. Cấu hình Kafka Streams Binder

Chọn function bean và khai báo input/output binding:

~~~yaml
spring:
  cloud:
    function:
      definition: aggregateDeviceWindows
    stream:
      bindings:
        aggregateDeviceWindows-in-0:
          destination: device-readings
        aggregateDeviceWindows-out-0:
          destination: device-window-summaries
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: device-window-aggregator-local
          bindings:
            aggregateDeviceWindows-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.telemetry.DeviceReadingSerde
                timestampExtractorBeanName: deviceEventTimestampExtractor
            aggregateDeviceWindows-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.telemetry.DeviceWindowSummarySerde
~~~

Thay broker endpoint, package class Serde và applicationId theo project. Các property Kafka Streams Binder thuộc prefix kafka.streams, khác cấu hình Kafka MessageChannel Binder. Đừng sao chép property dưới spring.cloud.stream.kafka.bindings sang kafka.streams.bindings vì hai binder có extension properties khác nhau.

applicationId xác định Kafka Streams application identity và consumer group nội bộ. Các instance cùng một ứng dụng cần dùng cùng applicationId để chia task và state; dev, staging và production phải dùng applicationId riêng để không chia consumer group hoặc state ngoài ý muốn.

Input/output destination nên được provision trước ở môi trường production. Topic input cần partition count phù hợp với parallelism. Output topic và internal repartition/changelog topics cần đủ quyền và dung lượng.

### 12.1. Serde trong binding và trong topology

Cấu hình keySerde/valueSerde của input binding giúp binder deserialize record đầu vào. Trong topology, Grouped.with xác định Serde dùng cho thao tác group/repartition; Materialized.with xác định Serde cho state store. Output binding producer Serde xác định cách serialize summary.

Các lớp Serde phải có thể được khởi tạo theo cơ chế binder hỗ trợ. Nếu dùng class tùy chỉnh, cần public constructor và dependency có trong runtime classpath. Không chỉ khai báo Serde cho input rồi giả định output/state store tự dùng cùng một kiểu.

## 13. Chạy local end-to-end

Một quy trình thực hành:

1. Khởi chạy Kafka local hoặc môi trường test riêng.
2. Tạo topic device-readings với partition count phù hợp.
3. Tạo topic device-window-summaries.
4. Khởi chạy ứng dụng với profile local và applicationId riêng.
5. Gửi các event có deviceId, eventTime và giá trị đo.
6. Đọc output topic và kiểm tra summary theo device/window.
7. Gửi một event đến muộn nhưng còn trong grace.
8. Gửi một event quá grace và xác nhận không cập nhật cửa sổ cũ.
9. Dừng/restart ứng dụng và kiểm tra state restore.
10. Xem consumer lag, processing rate, state/changelog topic và log.

Ví dụ JSON input:

~~~json
{
  "deviceId": "sensor-101",
  "eventTime": "2026-11-24T10:00:05Z",
  "temperatureC": 26.2,
  "humidityPercent": 61.0
}
~~~

Ví dụ summary output:

~~~json
{
  "deviceId": "sensor-101",
  "windowStartEpochMs": 1795514400000,
  "windowEndEpochMs": 1795514460000,
  "readingCount": 3,
  "averageTemperatureC": 26.6667,
  "minTemperatureC": 26.2,
  "maxTemperatureC": 27.0,
  "averageHumidityPercent": 60.5
}
~~~

Các số output minh họa cho ba mẫu trong cùng cửa sổ; timestamp epoch cần được tính từ event time thực tế trong test. Không hard-code timestamp minh họa vào code xử lý.

## 14. Kết quả aggregate được phát khi nào?

Kết quả aggregate trong topology trên được biểu diễn bằng KTable. Mỗi khi một event hợp lệ làm thay đổi state của một cửa sổ, KTable có thể phát một bản cập nhật qua toStream. Vì vậy downstream có thể nhận nhiều summary cho cùng output key trong thời gian cửa sổ còn mở hoặc còn trong grace period.

Điều này hữu ích cho dashboard gần realtime: giá trị trung bình được cập nhật sau từng mẫu. Nhưng nếu downstream chỉ muốn một kết quả cuối cùng sau khi cửa sổ đóng, có thể dùng Suppressed.untilWindowCloses trong topology.

~~~java
.suppress(Suppressed.untilWindowCloses(
        Suppressed.BufferConfig
                .maxBytes(50_000_000L)
                .shutDownWhenFull()))
.toStream()
~~~

Buffer suppression giữ kết quả cho tới khi cửa sổ đóng theo stream time và grace. Buffer cần giới hạn dung lượng; khi đầy, chính sách ở ví dụ sẽ làm Kafka Streams task/application dừng thay vì âm thầm bỏ cam kết final-only. Cần chọn dung lượng, giám sát và phương án phục hồi phù hợp. Nếu chấp nhận phát sớm khi buffer đầy, có thể chọn policy khác nhưng phải hiểu rằng output có thể không còn chỉ là final result.

Không dùng suppression chỉ vì muốn giảm số message mà không tính memory. Số thiết bị, số cửa sổ đang mở, grace period và tốc độ event quyết định kích thước buffer.

## 15. State store và changelog topic

Windowed aggregation cần lưu trạng thái trung gian. Kafka Streams tạo state store với tên device-window-aggregate; local state thường được lưu trên máy instance và được phục hồi từ changelog topic khi task chuyển sang instance khác hoặc process restart.

Cần hiểu ba thành phần:

- Local state store: dữ liệu state đang được task sử dụng trên instance.
- Changelog topic: log Kafka hỗ trợ khôi phục state store.
- Repartition topic: có thể được tạo khi topology thay đổi key và cần phân phối lại record.

State store không phải cache tạm có thể xóa tùy ý. Xóa local state có thể làm tăng thời gian restore; xóa changelog/internal topic có thể làm mất khả năng phục hồi state. Không tự xóa internal topic khi ứng dụng đang vận hành.

Đặt applicationId và store name ổn định. Nếu đổi applicationId, Kafka Streams coi đó là ứng dụng mới với consumer group/state identity mới; nó có thể đọc lại input theo offset policy và xây state từ đầu. Nếu đổi topology/store name, cần kế hoạch migration state và internal topics.

## 16. Partition, task và khả năng mở rộng

Kafka Streams tạo task dựa trên partition của input topic và topology. Trong một applicationId, các instance phối hợp chia task. Số instance hoạt động hữu ích bị giới hạn bởi số task có thể chạy song song; tăng pod vượt quá mức này có thể không tăng throughput.

Các điểm cần kiểm tra:
- Input topic có đủ partition cho parallelism mong muốn không?
- Key distribution có đều không hay một thiết bị quá nóng?
- Repartition topic có số partition và throughput phù hợp không?
- Broker có đủ disk/network và replication capacity không?
- State store restore có làm rebalance kéo dài không?
- Downstream output có chịu được tốc độ publish không?

Với topology nhóm theo deviceId, cùng device phải đi cùng partition để aggregation đúng. Nếu key phân bố lệch, một task có thể xử lý nhiều hơn hẳn các task khác. Tăng partition không tự chia một key nóng thành nhiều partition vì cùng key vẫn cần cùng partition để giữ thứ tự và state của aggregate.

## 17. Chọn processing guarantee

Kafka Streams có các processing guarantee khác nhau. At-least-once có thể xử lý lại record sau một số failure window; downstream nên thiết kế idempotent theo output key. Exactly-once v2 có thể cung cấp giao dịch đọc/ghi Kafka phù hợp khi broker và cấu hình đáp ứng yêu cầu.

Exactly-once trong Kafka Streams không tự bao phủ side effect tới database, HTTP API, email hoặc broker khác. Nếu function ghi database bên ngoài Kafka, cần outbox/inbox hoặc cơ chế idempotency/transaction riêng.

Khi bật exactly_once_v2, kiểm tra:
- Kafka broker version và transaction support.
- Transactional ID/producer permissions và transaction coordinator availability.
- Replication/min ISR của các topic liên quan.
- Transaction timeout và commit behavior.
- Cách binder truyền processing guarantee xuống Kafka Streams config trong phiên bản đang dùng.

Không tuyên bố end-to-end exactly-once chỉ vì cấu hình processing.guarantee là exactly_once_v2.

## 18. Kiểm thử logic aggregation

Tách phần tính toán aggregate khỏi topology giúp unit test dễ hiểu. Kiểm tra:
- Aggregate rỗng nhận event đầu tiên.
- Count tăng đúng.
- Sum và average đúng.
- Min/max cập nhật đúng.
- Nhiều device không trộn dữ liệu.
- Invalid reading không được đưa vào kết quả.
- Output key phân biệt các window.

Ví dụ unit test cho aggregate:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;

class DeviceAggregateTest {

    @Test
    void calculatesCountAverageAndRange() {
        DeviceAggregate aggregate = DeviceAggregate.empty();

        aggregate = aggregate.add(new DeviceReading(
                "sensor-101",
                Instant.parse("2026-11-24T10:00:05Z"),
                26.0,
                60.0));

        aggregate = aggregate.add(new DeviceReading(
                "sensor-101",
                Instant.parse("2026-11-24T10:00:20Z"),
                28.0,
                64.0));

        assertThat(aggregate.count()).isEqualTo(2);
        assertThat(aggregate.averageTemperatureC()).isEqualTo(27.0);
        assertThat(aggregate.minTemperatureC()).isEqualTo(26.0);
        assertThat(aggregate.maxTemperatureC()).isEqualTo(28.0);
        assertThat(aggregate.averageHumidityPercent()).isEqualTo(62.0);
    }
}
~~~

Unit test này xác nhận phép tính thuần Java, chưa kiểm tra Kafka Streams window semantics, Serde hoặc binder.

## 19. Kiểm thử topology bằng TopologyTestDriver

TopologyTestDriver cho phép chạy topology Kafka Streams trong JVM mà không cần broker thật. Dùng test input/output topics để kiểm tra key, timestamp, window và aggregate.

Một bộ test nên bao gồm:

| Kịch bản | Dữ liệu | Kết quả mong đợi |
|---|---|---|
| Một thiết bị, một cửa sổ | Nhiều reading cùng deviceId | Một output key, count và average đúng |
| Hai thiết bị | Hai deviceId khác nhau | State độc lập |
| Hai cửa sổ | Event trước và sau mốc phút | Hai summary key khác nhau |
| Event đến muộn trong grace | Timestamp thuộc window cũ, được xử lý trong grace | Aggregate cửa sổ cũ được cập nhật |
| Event quá grace | Timestamp cũ hơn giới hạn grace | Không cập nhật window đã hết grace |
| Timestamp sai | Null hoặc timestamp âm/không hợp lệ | Bị từ chối hoặc xử lý theo policy |
| Key thay đổi | Input key khác deviceId | Repartition/group vẫn tạo đúng nhóm |
| Restart/state restore | Khôi phục từ changelog trong integration test | Aggregate tiếp tục từ state đã commit |

Khi test event-time, điều khiển timestamp của TestInputTopic hoặc dùng record timestamp extractor như production. Nếu test chỉ gửi payload nhưng timestamp record không đúng, kết quả window có thể khác kỳ vọng.

TopologyTestDriver kiểm tra topology logic và state store trong môi trường test. Nó không thay thế integration test về broker rebalance, ACL, TLS, transaction, network partition hoặc state restoration giữa các instance thật.

## 20. Integration test với Kafka thật

Dùng Kafka Testcontainers hoặc môi trường Kafka test tương đương để kiểm tra binder và runtime:

1. Khởi động Kafka container.
2. Tạo input/output topic với partition count xác định.
3. Khởi động Spring context có Kafka Streams Binder.
4. Gửi event qua producer với key và timestamp đúng.
5. Đọc output topic và xác minh summary.
6. Gửi event late trong grace và quá grace.
7. Dừng/restart application hoặc chuyển task để kiểm tra restore.
8. Kiểm tra consumer group, applicationId và internal topics.
9. Xác nhận quyền truy cập và serialization trên artifact thật.

Integration test nên dùng applicationId riêng theo test run để không đụng state/offset của môi trường khác. Dọn topic/container sau test nhưng không xóa internal topics của một ứng dụng đang chạy dùng chung.

## 21. Theo dõi và vận hành

Một pipeline aggregation cần theo dõi cả ứng dụng lẫn Kafka:

| Metric/Signal | Ý nghĩa |
|---|---|
| Input records/sec | Tốc độ reading đi vào topology |
| Output updates/sec | Tốc độ summary được phát |
| Processing latency | Thời gian xử lý record |
| Consumer lag | Mức chậm của Kafka Streams application |
| Rebalance count/time | Mức độ thay đổi assignment |
| State restore duration | Thời gian phục hồi state store |
| RocksDB/local state size | Dung lượng state trên instance |
| Changelog/repartition traffic | Lưu lượng nội bộ của topology |
| Dropped late records | Số record quá grace |
| Invalid reading count | Dữ liệu không đáp ứng schema/domain |
| Broker disk and request latency | Sức khỏe cluster Kafka |

Không dùng output rate đơn lẻ làm dấu hiệu thành công. Với topology cập nhật liên tục, một input có thể tạo nhiều output update; khi dùng suppression, output rate lại gần số cửa sổ hoàn tất hơn. Dashboard phải phản ánh semantics đang triển khai.

Log nên chứa deviceId, event type, applicationId, partition/task và error category ở mức phù hợp. Tránh đưa mọi event ID hoặc device ID cardinality cao vào metric label; dùng structured log/trace cho điều tra từng event.

## 22. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mọi thiết bị bị gộp chung | Không rekey theo deviceId hoặc producer key sai | selectKey rồi groupByKey, xác nhận key serde |
| Summary rơi vào cửa sổ sai | Kafka record timestamp khác eventTime | Cấu hình TimestampExtractor và test timestamp |
| Event late không cập nhật | Grace period đã hết theo stream time | Kiểm tra grace, partition time và clock/source delay |
| Event sai schema không deserialize | Serde hoặc JSON type không khớp | Kiểm tra input valueSerde, JavaTime module và contract |
| State store không restore | Changelog/internal topic hoặc applicationId bị thay đổi | Kiểm tra internal topics, ACL và app identity |
| Repartition topic không được tạo | Thiếu quyền hoặc cấu hình provisioning | Kiểm tra ACL, broker policy và topic provisioning |
| Output không đọc được | Output producer Serde sai | Cấu hình output keySerde/valueSerde |
| Một task quá tải | Key skew/hot device | Phân tích key distribution và thiết kế shard nếu nghiệp vụ cho phép |
| Nhiều pod nhưng throughput không tăng | Input partition/task không đủ | Tăng partition theo capacity plan và kiểm tra task assignment |
| Output có nhiều bản cập nhật | KTable toStream phát mỗi lần aggregate thay đổi | Dùng suppression nếu chỉ cần final result |
| Application dừng khi suppression buffer đầy | Buffer giới hạn và policy shutDownWhenFull | Tăng capacity có kiểm soát, giảm cardinality/window hoặc chọn policy khác |
| Test pass nhưng production fail | Chưa kiểm tra binder, broker security hoặc state restore thật | Bổ sung integration test trên Kafka tương đương |

## 23. Quy trình thực hành từ đầu đến cuối

1. Tạo project với Kafka Streams Binder dependency tương thích BOM.
2. Định nghĩa DeviceReading và DeviceWindowSummary.
3. Chọn event-time và thống nhất timestamp UTC.
4. Tạo TimestampExtractor đọc eventTime từ payload hoặc bảo đảm producer timestamp đúng.
5. Tạo Serde cho input, aggregate state và output.
6. Viết Function nhận KStream và xác thực payload.
7. Đặt key theo deviceId, groupByKey và kiểm tra repartition.
8. Cấu hình tumbling window một phút và grace 15 giây.
9. Viết aggregate count/sum/min/max.
10. Materialize state store với tên ổn định.
11. Chuyển KTable thành KStream và tạo output key theo deviceId/window start.
12. Cấu hình input/output binding, applicationId và Serde trong Kafka Streams Binder.
13. Chạy local, gửi event và kiểm tra summary.
14. Test nhiều thiết bị, nhiều window, late event và invalid payload.
15. Kiểm thử topology bằng TopologyTestDriver.
16. Integration test binder, broker, state restore và security.
17. Theo dõi lag, restore, dropped late event, state size và output rate.
18. Triển khai với topic/partition/ACL đã provision và applicationId riêng cho từng môi trường.

## 24. Checklist production

- [ ] Event có deviceId ổn định và eventTime hợp lệ.
- [ ] Producer key hoặc topology rekey theo deviceId.
- [ ] TimestampExtractor dùng đúng event-time semantics.
- [ ] Window size, grace và chính sách late event được thống nhất.
- [ ] Input, aggregate state và output có Serde tương thích.
- [ ] State store có tên ổn định và changelog được bảo vệ.
- [ ] Output key phân biệt thiết bị và cửa sổ.
- [ ] Đã quyết định phát incremental updates hay chỉ final result.
- [ ] Suppression buffer có giới hạn và alert nếu tiến gần ngưỡng.
- [ ] applicationId riêng giữa local/dev/staging/prod, chung giữa các replica cùng app.
- [ ] Input partitions đủ cho parallelism và key distribution đã được kiểm tra.
- [ ] Broker ACL cho input, output, repartition và changelog topics đầy đủ.
- [ ] Processing guarantee phản ánh đúng phạm vi Kafka transaction.
- [ ] Có unit test, TopologyTestDriver test và Kafka integration test.
- [ ] Có dashboard cho lag, restore, state, late records và throughput.
- [ ] Có runbook cho rebalance kéo dài, state restore chậm, backlog và schema error.

Bài thực hành đã tạo một pipeline hoàn chỉnh: nhận telemetry, dùng deviceId làm key, nhóm theo tumbling event-time window, cập nhật aggregate state và phát summary riêng cho từng thiết bị/cửa sổ. Kafka Streams Binder đảm nhiệm kết nối function với Kafka Streams runtime; Kafka Streams DSL đảm nhiệm windowing và stateful computation. Khi triển khai thật, các quyết định về timestamp, grace, Serde, partition, state store, applicationId và delivery guarantee phải được kiểm thử cùng broker và dữ liệu đại diện.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Streams Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/overview.html)
- [Spring Cloud Stream — Kafka Streams Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Apache Kafka Streams — Developer Guide](https://kafka.apache.org/documentation/streams/)
- [Apache Kafka Streams — Windowing](https://kafka.apache.org/documentation/streams/developer-guide/dsl-api.html#windowing)
- [Spring Kafka — Serialization, Deserialization and Serdes](https://docs.spring.io/spring-kafka/reference/kafka/serdes.html)

