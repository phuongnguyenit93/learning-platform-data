# Kiểm thử topology bằng TopologyTestDriver

Kafka Streams xử lý record bằng một topology gồm source, processor, state store và sink. Khi thay đổi logic lọc, đổi key, aggregate, join hoặc cửa sổ thời gian, cần kiểm tra kết quả của toàn bộ chuỗi xử lý. TopologyTestDriver cung cấp môi trường kiểm thử topology ngay trong JVM: test đưa record vào input topic, topology xử lý đồng bộ, sau đó test đọc output và truy vấn state store.

TopologyTestDriver rất phù hợp để kiểm tra logic xử lý và trạng thái một cách nhanh, lặp lại được. Nó không khởi chạy Kafka broker thật, không mô phỏng consumer group assignment hay replication. Vì vậy, nên dùng nó để kiểm tra hành vi topology, rồi bổ sung integration test với Kafka khi cần xác minh cấu hình binder và hành vi broker.

## 1. TopologyTestDriver giải quyết bài toán gì?

Một Kafka Streams application có thể được viết bằng Streams DSL hoặc Processor API. Dù dùng cách nào, ứng dụng cuối cùng đều tạo ra một Topology. TopologyTestDriver nhận topology đó và mô phỏng việc đọc record từ source, chạy processor, cập nhật state store và ghi record ra sink.

Một test điển hình thực hiện các bước:

1. Tạo topology giống logic đang chạy trong ứng dụng.
2. Tạo TopologyTestDriver với cấu hình Streams cần thiết.
3. Tạo TestInputTopic cho từng topic đầu vào cùng serializer tương ứng.
4. Đưa record vào bằng pipeInput hoặc pipeRecordList.
5. Tạo TestOutputTopic cho topic đầu ra cùng deserializer tương ứng.
6. Đọc record đầu ra và so sánh key, value, timestamp hoặc header.
7. Truy vấn state store để xác minh trạng thái sau xử lý.
8. Đóng driver để giải phóng tài nguyên.

~~~mermaid
flowchart LR
    A["TestInputTopic<br/>pipeInput"] --> B["TopologyTestDriver"]
    B --> C["Source"]
    C --> D["Processor / DSL"]
    D --> E["State store"]
    D --> F["Sink"]
    F --> G["TestOutputTopic<br/>assert output"]
    E --> H["Query state store"]
~~~

Driver xử lý input đồng bộ. Khi test gọi pipeInput, record được đưa qua các processor liên quan trước khi lời gọi trả về. Test không cần chờ một consumer thread hoặc polling loop như khi chạy broker thật.

## 2. Thêm dependency kiểm thử

Kafka cung cấp artifact kafka-streams-test-utils. Chỉ cần dependency ở phạm vi test:

~~~xml
<dependency>
    <groupId>org.apache.kafka</groupId>
    <artifactId>kafka-streams-test-utils</artifactId>
    <version>${kafka.version}</version>
    <scope>test</scope>
</dependency>
~~~

Giá trị kafka.version phải trùng với phiên bản kafka-streams mà ứng dụng đang sử dụng. Nếu dự án đã dùng Spring Boot hoặc dependency management để quản lý phiên bản Kafka, hãy dùng cùng phiên bản được quản lý thay vì kéo thêm một phiên bản test-utils khác.

Với dự án dùng JUnit 5 và Spring Boot, test có thể dùng spring-boot-starter-test để có JUnit Jupiter và thư viện assertion. TopologyTestDriver không yêu cầu Spring ApplicationContext hoặc Kafka broker.

## 3. Tách logic topology để dùng lại trong ứng dụng và test

Trong Spring Cloud Stream Kafka Streams Binder, ứng dụng thường khai báo Function nhận KStream và trả về KStream. Binder kết nối input/output binding với Kafka topic. Để kiểm thử logic, nên đặt phần biến đổi Streams DSL vào một phương thức Java thuần; Function trong ứng dụng và topology dùng trong test cùng gọi phương thức đó.

Ví dụ đếm số lần xuất hiện của từng từ:

~~~java
import java.util.Arrays;
import java.util.Locale;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.kstream.Produced;
import org.apache.kafka.streams.state.KeyValueStore;

public final class WordCountTopology {

    private WordCountTopology() {
    }

    public static KStream<String, Long> countWords(
            KStream<String, String> input) {

        return input
            .flatMapValues(text ->
                Arrays.asList(
                    text.toLowerCase(Locale.ROOT).split("\\W+")
                )
            )
            .groupBy(
                (originalKey, word) -> word,
                Grouped.with(Serdes.String(), Serdes.String())
            )
            .count(
                Materialized
                    .<String, Long, KeyValueStore<Bytes, byte[]>>as("word-counts")
                    .withKeySerde(Serdes.String())
                    .withValueSerde(Serdes.Long())
            )
            .toStream();
    }

    public static Topology buildForTest() {
        StreamsBuilder builder = new StreamsBuilder();

        KStream<String, String> input = builder.stream(
            "input-topic",
            Consumed.with(Serdes.String(), Serdes.String())
        );

        countWords(input).to(
            "output-topic",
            Produced.with(Serdes.String(), Serdes.Long())
        );

        return builder.build();
    }
}
~~~

Trong ứng dụng Spring Cloud Stream, Function dùng lại cùng phép biến đổi:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WordCountConfiguration {

    @Bean
    Function<KStream<String, String>, KStream<String, Long>> wordCount() {
        return WordCountTopology::countWords;
    }
}
~~~

Trong ứng dụng, binder lấy record từ binding wordCount-in-0 và gửi kết quả trả về qua wordCount-out-0. Trong test, buildForTest gắn cùng phép biến đổi vào topic input-topic và output-topic để TopologyTestDriver có thể đưa dữ liệu vào và đọc kết quả.

Tách phép biến đổi như trên giúp test tập trung vào logic thật của ứng dụng. Nếu viết lại một phiên bản DSL riêng chỉ dành cho test, test có thể vẫn xanh dù Function production đã bị thay đổi hoặc cấu hình sai.

## 4. Viết test đầu tiên với input và output topic

Một test dùng JUnit 5 có thể tạo driver trực tiếp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.state.KeyValueStore;
import org.junit.jupiter.api.Test;

class WordCountTopologyTest {

    @Test
    void shouldCountWordsAndUpdateStateStore() {
        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "word-count-test");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

        try (TopologyTestDriver driver =
                new TopologyTestDriver(
                    WordCountTopology.buildForTest(),
                    props
                )) {

            TestInputTopic<String, String> input = driver.createInputTopic(
                "input-topic",
                Serdes.String().serializer(),
                Serdes.String().serializer()
            );

            TestOutputTopic<String, Long> output = driver.createOutputTopic(
                "output-topic",
                Serdes.String().deserializer(),
                Serdes.Long().deserializer()
            );

            input.pipeInput("order-1", "spring cloud spring");

            Map<String, Long> latestCounts = output.readKeyValuesToMap();
            assertEquals(2L, latestCounts.get("spring"));
            assertEquals(1L, latestCounts.get("cloud"));
            assertEquals(2, latestCounts.size());
            assertTrue(output.isEmpty());

            KeyValueStore<String, Long> store =
                driver.getKeyValueStore("word-counts");
            assertEquals(2L, store.get("spring"));
            assertEquals(1L, store.get("cloud"));
        }
    }
}
~~~

Ở ví dụ này, input topic nhận một record có key order-1 và payload là chuỗi từ. flatMapValues tách chuỗi thành từng từ, groupBy đổi key thành từ, count cập nhật số lần xuất hiện. Output là các lần cập nhật của KTable được chuyển thành KStream.

readKeyValuesToMap trả về giá trị mới nhất cho từng key, phù hợp khi chỉ cần xác minh trạng thái cuối của một bảng. Nếu muốn kiểm tra từng lần cập nhật, dùng readKeyValuesToList hoặc readRecordsToList; cùng một key có thể xuất hiện nhiều lần trong danh sách.

## 5. TestInputTopic và TestOutputTopic

TestInputTopic mô phỏng source topic của topology. Các cách đưa dữ liệu thường dùng:

| Phương thức | Công dụng |
|---|---|
| pipeInput(value) | Gửi record không chỉ định key |
| pipeInput(key, value) | Gửi key và value |
| pipeInput(key, value, timestamp) | Gửi record với timestamp sự kiện xác định |
| pipeRecordList(records) | Gửi danh sách TestRecord, có thể kèm timestamp và header |
| pipeKeyValueList(records) | Gửi danh sách KeyValue |
| advanceTime(duration) | Tăng đồng hồ event time nội bộ của input topic |

TestOutputTopic cung cấp các cách đọc khác nhau:

| Phương thức | Khi nên dùng |
|---|---|
| readValue | Chỉ cần value của một record |
| readKeyValue | Cần key và value của một record |
| readRecord | Cần cả key, value, timestamp và header |
| readValuesToList | Đọc tất cả value |
| readKeyValuesToList | Đọc tất cả cặp key/value |
| readRecordsToList | Đọc tất cả record cùng metadata |
| readKeyValuesToMap | Lấy giá trị cuối cùng theo key khi kiểm tra bảng |
| isEmpty | Xác minh không còn output chưa đọc |

Chọn cách đọc phù hợp với ngữ nghĩa của output. KStream thường cần kiểm tra toàn bộ chuỗi sự kiện. KTable chuyển thành KStream phát các bản cập nhật; nếu chỉ quan tâm trạng thái cuối, map theo key sẽ dễ đọc hơn.

## 6. Kiểm tra key, value, timestamp và header

Nếu chỉ dùng readKeyValue, test không nhìn thấy timestamp và headers. Với logic phụ thuộc metadata, hãy dùng readRecord hoặc readRecordsToList.

Ví dụ gửi record có header và timestamp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.time.Instant;

import org.apache.kafka.common.header.internals.RecordHeaders;
import org.apache.kafka.streams.test.TestRecord;

RecordHeaders headers = new RecordHeaders();
headers.add(
    "event_type",
    "order-created".getBytes(StandardCharsets.UTF_8)
);

TestRecord<String, String> record = new TestRecord<>(
    "order-1001",
    "{\"amount\":120}",
    headers,
    Instant.parse("2026-03-10T10:15:00Z")
);

inputTopic.pipeInput(record);

TestRecord<String, Long> outputRecord = outputTopic.readRecord();
assertEquals("order-1001", outputRecord.key());
assertEquals(
    Instant.parse("2026-03-10T10:15:00Z").toEpochMilli(),
    outputRecord.timestamp()
);
~~~

Đoạn code giả định topology chỉ forward record và giữ nguyên timestamp. Nếu topology đổi key hoặc gán timestamp khác, hãy assert theo hành vi dự kiến của chính topology đó.

TestRecord có thể mang headers và timestamp như một record Kafka. Đây là cách kiểm thử processor đọc header event type, correlation ID hoặc metadata thời gian mà không cần gửi message qua broker.

## 7. Kiểm thử state store

Topology có state store thường không chỉ tạo output. Aggregate có thể cập nhật KTable, Processor API có thể lưu dữ liệu vào KeyValueStore, WindowStore hoặc SessionStore, và các processor phía sau có thể đọc trạng thái đó.

TopologyTestDriver cho phép truy vấn state store sau khi đưa dữ liệu vào:

~~~java
KeyValueStore<String, Long> counts =
    driver.getKeyValueStore("word-counts");

assertEquals(2L, counts.get("spring"));
assertEquals(1L, counts.get("cloud"));
~~~

Có thể truy vấn store trước khi gửi input để kiểm tra hành vi khi đã có trạng thái ban đầu. Tuy nhiên, với store có changelog hoặc logging, không nên tự ghi trạng thái ban đầu một cách tùy tiện. Hãy ưu tiên tạo state qua input records như khi chạy thật. Chỉ pre-populate store trực tiếp khi test thực sự cần một trạng thái nền và đã cấu hình store phù hợp cho thao tác đó.

Các loại store có thể truy cập:

| Store | Dữ liệu lưu | Ví dụ kiểm tra |
|---|---|---|
| KeyValueStore | Một giá trị hiện tại cho mỗi key | Tổng đơn hàng theo customerId |
| WindowStore | Giá trị theo key và khoảng thời gian | Tổng số sự kiện trong cửa sổ 5 phút |
| SessionStore | Phiên hoạt động theo key và khoảng thời gian | Phiên truy cập của người dùng |
| ReadOnlyKeyValueStore | Truy vấn chỉ đọc với một số topology/query API | Kiểm tra kết quả truy vấn |

Tên store phải trùng tên được khai báo trong Materialized hoặc Processor API. Nếu tên sai, driver không tìm thấy store và test thất bại; đây là lỗi hữu ích giúp phát hiện thay đổi tên store ngoài ý muốn.

## 8. Kiểm thử event time và wall-clock time

Kafka Streams có hai loại thời gian thường gặp trong processor:

- Event time: thời điểm gắn với record, thường được lấy từ timestamp của Kafka record hoặc TimestampExtractor.
- Wall-clock time: thời gian đồng hồ thực tế của tiến trình.

TopologyTestDriver kiểm soát cả hai loại thời gian. Khi đưa record có timestamp vào, event-time punctuation có thể được kích hoạt theo stream time. Wall-clock punctuation phải được kích hoạt bằng cách tiến đồng hồ mô phỏng:

~~~java
import java.time.Duration;
import java.time.Instant;

inputTopic.pipeInput(
    "customer-42",
    "order-created",
    Instant.parse("2026-03-10T10:00:00Z")
);

driver.advanceWallClockTime(Duration.ofSeconds(30));
~~~

Không nhầm advanceTime của TestInputTopic với advanceWallClockTime của driver:

| Thao tác | Đồng hồ được tác động | Tác động đến stream time |
|---|---|---|
| pipeInput với timestamp mới | Event time của record | Có thể tăng stream time khi record được xử lý |
| TestInputTopic.advanceTime | Thời gian tạo timestamp tự động của input topic | Không tự tăng stream time nếu chưa gửi record mới |
| TopologyTestDriver.advanceWallClockTime | Wall-clock time mô phỏng | Kích hoạt wall-clock punctuation khi đến lịch |

Ví dụ test cửa sổ:

1. Gửi record đầu tiên ở thời điểm 10:00:00.
2. Gửi record tiếp theo ở 10:00:30.
3. Gửi record có timestamp mới hơn để đẩy stream time qua ranh giới cửa sổ.
4. Xác minh output được phát hoặc state store được cập nhật đúng.
5. Gửi record đến muộn trong phạm vi grace period và xác minh hành vi.
6. Gửi record quá muộn và xác minh chính sách bỏ qua hoặc xử lý riêng.

Event-time punctuation được kích hoạt theo timestamp record được xử lý. Chỉ tăng đồng hồ input mà không gửi record mới không đồng nghĩa stream time đã tiến lên. Với wall-clock punctuation, dùng advanceWallClockTime để tránh test phụ thuộc vào thời gian chạy thật.

## 9. Kiểm thử nhiều input topic và join

Topology có thể đọc nhiều source topic, ví dụ orders và customers. Tạo một TestInputTopic cho từng source:

Giả sử ứng dụng khai báo các kiểu dữ liệu và Serde tương ứng:

~~~java
public record Order(
    String orderId,
    String customerId,
    int amount
) {}

public record Customer(
    String customerId,
    String displayName
) {}
~~~

~~~java
TestInputTopic<String, Order> orders = driver.createInputTopic(
    "orders",
    Serdes.String().serializer(),
    orderSerde.serializer()
);

TestInputTopic<String, Customer> customers = driver.createInputTopic(
    "customers",
    Serdes.String().serializer(),
    customerSerde.serializer()
);

orders.pipeInput(
    "customer-42",
    new Order("order-1001", "customer-42", 120)
);

customers.pipeInput(
    "customer-42",
    new Customer("customer-42", "Lan")
);
~~~

Với KStream-KStream join, test phải cấp timestamp hợp lý cho cả hai phía và xác minh record nằm trong cửa sổ join. Với KStream-KTable join, cần đưa dữ liệu table vào trước hoặc sau theo kịch bản nghiệp vụ để kiểm tra việc tra cứu trạng thái tại thời điểm xử lý.

TopologyTestDriver xử lý input đồng bộ, nên test có thể chủ động sắp thứ tự record để tái hiện trường hợp record bên trái đến trước, record bên phải đến sau, record đến ngoài cửa sổ hoặc tombstone xóa key.

Driver mô phỏng input topic dưới dạng một partition. Nó phù hợp kiểm tra logic join theo key và thời gian, nhưng không chứng minh rằng các topic thật được co-partition hoặc mọi partition của cluster đều được gán đúng cho task.

## 10. Kiểm thử repartition và internal topics

Khi topology đổi key rồi groupBy hoặc join, Kafka Streams có thể tạo internal repartition topic. TopologyTestDriver có thể chạy topology có internal repartition, cho phép kiểm tra kết quả logic sau bước phân phối lại.

Có thể kiểm tra các topic mà topology đã ghi:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;

Set<String> producedTopics = driver.producedTopicNames();
assertTrue(producedTopics.contains("output-topic"));
~~~

Danh sách topic được ghi có thể chứa topic nghiệp vụ và internal topic như repartition hoặc changelog. Tên internal topic phụ thuộc application.id và tên processor/repartition được tạo trong topology.

Test driver không mô phỏng nhiều partition thực tế. Do đó, kiểm tra repartition bằng driver chỉ xác nhận dữ liệu qua topology và kết quả phép toán. Để xác minh partition count, partitioner, ACL, replication factor hoặc việc broker tạo internal topic, cần integration test với Kafka broker.

## 11. Kiểm thử Processor API và punctuator

TopologyTestDriver hỗ trợ topology tạo bằng Processor API, gồm source, processor, state store và sink. Test có thể kiểm tra record được forward, trạng thái store sau xử lý và tác động của punctuation.

Với một processor tùy chỉnh:

1. Tạo topology có source và processor.
2. Đăng ký state store với processor.
3. Dùng TopologyTestDriver để gửi record.
4. Đọc output từ sink.
5. Truy vấn store để xác minh cập nhật.
6. Dùng timestamp input hoặc advanceWallClockTime để kích hoạt lịch phù hợp.

Nếu chỉ kiểm thử một Processor API component tách rời, MockProcessorContext có thể phù hợp hơn. MockProcessorContext cho phép kiểm tra record được forward và lịch punctuation đã đăng ký, nhưng không tự động chạy topology hoặc tự động kích hoạt punctuator. Khi muốn kiểm tra punctuation được thực thi trong topology, dùng TopologyTestDriver.

## 12. Cấu hình Serde trong test

TopologyTestDriver mô phỏng producer và consumer làm việc với byte[]; TestInputTopic dùng serializer để chuyển Java object thành byte và TestOutputTopic dùng deserializer để đọc byte trở lại object. Vì vậy, test cần dùng đúng Serde như ứng dụng.

Nếu topology sử dụng kiểu custom:

~~~java
TestInputTopic<String, Order> input = driver.createInputTopic(
    "orders",
    Serdes.String().serializer(),
    orderSerde.serializer()
);

TestOutputTopic<String, OrderSummary> output = driver.createOutputTopic(
    "order-summaries",
    Serdes.String().deserializer(),
    orderSummarySerde.deserializer()
);
~~~

Một số lỗi thường gặp:

- Serializer và deserializer không cùng schema hoặc version.
- Key Serde khác với key type sau selectKey.
- Value Serde dùng sai cho output của aggregate.
- JSON/Avro mapper không đăng ký module cần thiết.
- Serde test tự tạo khác cấu hình Serde trong ứng dụng.

Hãy kiểm tra cả round-trip serialization và kết quả nghiệp vụ. Nếu test chỉ gọi hàm chuyển đổi Java trực tiếp, nó không phát hiện lỗi serializer/deserializer.

## 13. Test lỗi và dữ liệu biên

TopologyTestDriver có thể kiểm tra các nhánh xử lý lỗi thuộc logic topology, chẳng hạn:

- Record có key null hoặc value null.
- Payload sai định dạng sau khi đã deserialize thành công.
- Header bắt buộc bị thiếu.
- Timestamp âm hoặc ngoài khoảng hợp lệ theo nghiệp vụ.
- Record trùng event ID.
- Tombstone xóa key khỏi KTable.
- Record đến muộn ngoài grace period.
- Giá trị aggregate vượt giới hạn hoặc không hợp lệ.

Tuy nhiên, lỗi deserialization xảy ra trước khi record được đưa vào topology. Driver dùng serializer/deserializer do test cung cấp và không mô phỏng đầy đủ Kafka consumer exception handler, retry listener hoặc DLQ của binder. Hãy kiểm thử deserialization failure, producer failure và broker authorization bằng integration test tương ứng.

## 14. Giới hạn cần hiểu trước khi dựa vào test

TopologyTestDriver rất nhanh vì không chạy broker. Đổi lại, nó không xác minh các thuộc tính thuộc về cluster hoặc runtime phân tán.

| Có thể kiểm tra tốt bằng TopologyTestDriver | Cần Kafka broker hoặc môi trường tích hợp |
|---|---|
| Lọc, map, selectKey, aggregate | Consumer group và rebalance |
| Join và cửa sổ với timestamp được kiểm soát | Co-partitioning trên nhiều partition thật |
| Output key/value/header/timestamp | Replication factor và leader election |
| State store và tombstone | ACL, SASL, TLS và authorization |
| Event-time và wall-clock punctuation | Broker transaction và coordinator failure |
| Internal topology và logic repartition | Broker tạo internal topic, quota và topic config |
| Serde của record được test | Kết nối mạng, timeout và broker compatibility |
| Logic Processor API | Multi-instance assignment và state restoration từ changelog |

Theo API Kafka, test driver mô phỏng input topic như một partition. Nó cũng xử lý record đồng bộ; commit.interval.ms và cache.max.bytes.buffering không có tác động như khi chạy runtime thật, vì hành vi được mô phỏng như thể commit/flush sau mỗi input record.

Không dùng kết quả TopologyTestDriver để kết luận ứng dụng đã sẵn sàng triển khai. Nó xác nhận topology xử lý đúng các tình huống đã đưa vào test.

## 15. Khi nào cần integration test với Kafka?

Hãy bổ sung integration test khi cần xác minh:

- Spring Cloud Stream Kafka Streams Binder tạo đúng binding và topic.
- Function definition và tên binding được ánh xạ chính xác.
- Kafka Streams application.id và consumer configuration.
- Key/value Serde thực tế, schema registry hoặc native encoding.
- Internal repartition/changelog topic được broker tạo với cấu hình phù hợp.
- Partition count, partitioner và co-partitioning.
- Transaction, offset, exactly-once và lỗi coordinator.
- Security, ACL, TLS, SASL và quyền truy cập topic.
- Rebalance, state restoration, standby replica và multi-instance.
- Retry, deserialization exception handler và DLQ.

Có thể chạy Kafka bằng Testcontainers hoặc EmbeddedKafka của Spring Kafka. Với ứng dụng dùng Spring Cloud Stream, khởi chạy ApplicationContext với Kafka broker test và xác minh binding thực sự publish/consume trên topic. Đây là lớp test khác với TopologyTestDriver: integration test kiểm tra framework, binder và broker cùng hoạt động.

## 16. Mẫu phân lớp test cho dự án Spring Cloud Stream

Một dự án xử lý sự kiện có thể chia test thành ba lớp:

| Lớp | Công cụ | Mục tiêu |
|---|---|---|
| Unit test logic nghiệp vụ | JUnit, AssertJ, Mockito | Kiểm tra hàm tính toán hoặc validation thuần Java |
| Topology test | TopologyTestDriver | Kiểm tra pipeline, state store, timestamp, join và output |
| Integration test | Kafka Testcontainers hoặc EmbeddedKafka, Spring Boot Test | Kiểm tra binder, serialization, broker, partition, transaction và cấu hình triển khai |

Ví dụ tổ chức package:

~~~text
src/
  main/
    java/
      com/example/orders/
        OrderFunctions.java
        OrderTopology.java
  test/
    java/
      com/example/orders/
        OrderFunctionsTest.java
        OrderTopologyTest.java
        OrderBinderIntegrationTest.java
~~~

OrderFunctionsTest kiểm tra logic thuần Java. OrderTopologyTest tạo TopologyTestDriver và đưa record qua pipeline. OrderBinderIntegrationTest chạy Spring context cùng Kafka broker test để xác minh binding và cấu hình thực tế.

## 17. Checklist viết một TopologyTestDriver test tốt

- [ ] Topology trong test dùng cùng phép biến đổi DSL với Function production.
- [ ] application.id riêng cho test, không trùng ứng dụng đang chạy.
- [ ] Cấu hình key/value Serde đúng với record thực tế.
- [ ] Mỗi source topic có một TestInputTopic.
- [ ] Mỗi output topic cần xác minh có một TestOutputTopic.
- [ ] Dùng timestamp tường minh cho test window, join hoặc punctuation.
- [ ] Kiểm tra cả output và state store khi topology có trạng thái.
- [ ] Kiểm tra trường hợp không phát output bằng isEmpty.
- [ ] Đọc TestRecord nếu cần kiểm tra timestamp hoặc headers.
- [ ] Đóng TopologyTestDriver sau mỗi test.
- [ ] Không giả định driver kiểm tra được nhiều partition hoặc broker behavior.
- [ ] Có integration test cho binder và Kafka khi các yếu tố đó ảnh hưởng tính đúng đắn.

## 18. Quy trình thực hiện

1. Xác định hành vi cần kiểm tra: output, state store, thời gian, join hay lỗi dữ liệu.
2. Tách phép biến đổi topology thành phương thức dùng chung với Function production.
3. Xây topology test với input topic và sink topic có tên rõ ràng.
4. Tạo dependency kafka-streams-test-utils đúng phiên bản.
5. Khởi tạo Properties với application.id riêng và cấu hình Serde phù hợp.
6. Tạo TopologyTestDriver trong try-with-resources.
7. Tạo TestInputTopic và TestOutputTopic cho các source/sink.
8. Đưa các record đại diện và record biên vào topology.
9. Assert output theo ngữ nghĩa KStream hoặc KTable.
10. Truy vấn state store và kiểm tra giá trị cuối.
11. Điều khiển event time hoặc wall-clock time khi topology có punctuation/window.
12. Bổ sung integration test cho các hành vi phụ thuộc Kafka broker và Spring binder.

## Tài liệu tham khảo chính thức

- [Apache Kafka 4.4 - Testing a Streams Application](https://kafka.apache.org/44/streams/developer-guide/testing/): dependency test-utils, TestInputTopic, TestOutputTopic, state store, punctuation và giới hạn test.
- [Apache Kafka 4.4 - TopologyTestDriver API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TopologyTestDriver.html): tạo driver, cấu hình, input/output topic, state store và thời gian.
- [Apache Kafka 4.4 - TestInputTopic API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TestInputTopic.html): pipeInput, timestamp và danh sách record.
- [Apache Kafka 4.4 - TestOutputTopic API](https://kafka.apache.org/44/javadoc/org/apache/kafka/streams/TestOutputTopic.html): đọc KeyValue, TestRecord, map kết quả cuối và kiểm tra output queue.
- [Spring Cloud Stream Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html): functional programming model, KStream binding, Serde và cấu hình binder.
