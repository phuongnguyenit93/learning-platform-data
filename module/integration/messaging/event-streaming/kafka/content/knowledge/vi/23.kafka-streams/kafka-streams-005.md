# filter, map, mapValues, flatMap và selectKey

Kafka Streams DSL cung cấp các toán tử để lọc record, biến đổi key/value và mở rộng một record thành nhiều record. Năm toán tử **filter**, **map**, **mapValues**, **flatMap** và **selectKey** thường xuất hiện trong hầu hết topology xử lý dữ liệu.

Điểm cần hiểu rõ là mỗi toán tử tác động lên phần nào của record. filter quyết định giữ hay loại record; map có thể thay cả key và value; mapValues chỉ thay value; flatMap có thể tạo không, một hoặc nhiều record; selectKey chỉ tính lại key. Sự khác biệt này ảnh hưởng đến partitioning, ordering, SerDes và cách Kafka Streams tối ưu topology.

## 1. Record trong Kafka Streams

Một record trong KStream có thể được nhìn như cặp:

\[
(key,\ value)
\]

Ví dụ topic orders.raw chứa:

| Key | Value |
|---|---|
| order-101 | 101\|customer-7\|PAID\|250000 |
| order-102 | 102\|customer-8\|NEW\|180000 |
| order-103 | 103\|customer-7\|PAID\|320000 |

KStream biểu diễn một luồng record bất biến theo thời gian. Mỗi toán tử DSL tạo một KStream mới về mặt logic; record đầu vào không bị sửa tại chỗ.

~~~mermaid
flowchart LR
    A["orders.raw<br/>(key, value)"] --> B["filter"]
    B --> C["map"]
    C --> D["mapValues"]
    D --> E["flatMap"]
    E --> F["selectKey"]
    F --> G["orders.customer-events"]
~~~

Các toán tử trong bài là những phép biến đổi stateless: chúng không cần lưu state qua nhiều record. Chúng thường chạy trong processor task của Kafka Streams và có thể được kết hợp thành một topology.

Các ví dụ dùng Java 17 và một số domain record minh họa:

~~~java
import java.util.List;

record OrderEvent(
    String orderId,
    String customerId,
    String status,
    long totalAmount,
    List<OrderItem> items
) {}

record OrderItem(String productId, int quantity) {}
record OrderSummary(String orderId, String customerId, long totalAmount) {}
record OrderView(String orderId, String status, long totalAmount) {}
record OrderLine(String orderId, String productId, int quantity) {}
~~~

Các SerDe cho domain record cần được cung cấp theo schema/serializer của ứng dụng; ví dụ có thể dùng JSON, Avro hoặc Protobuf.

Tóm tắt callback và kiểu đầu ra của các operator:

| Operator | Callback nhận | Callback trả về | Key đầu ra |
|---|---|---|---|
| filter | key, value | boolean | Giữ key cũ |
| map | key, value | một KeyValue | Có thể đổi |
| mapValues | value hoặc key + value | value mới | Giữ key cũ |
| flatMap | key, value | Iterable<KeyValue> | Có thể đổi |
| flatMapValues | value hoặc key + value | Iterable<value> | Giữ key cũ |
| selectKey | key, value | key mới | Thay key, giữ value |

Các callback tương ứng trong API là Predicate, KeyValueMapper, ValueMapper và ValueMapperWithKey. Kiểu generic thực tế cho phép đổi K/V đầu vào sang KR/VR đầu ra.

## 2. filter: chỉ giữ record thỏa điều kiện

filter nhận một predicate gồm key và value. Nếu predicate trả về true, record được chuyển tiếp; nếu trả về false, record bị loại khỏi nhánh stream đó.

~~~java
KStream<String, OrderEvent> paidOrders =
    orders.filter((key, event) ->
        event != null && "PAID".equals(event.status())
    );
~~~

Trong ví dụ, chỉ đơn hàng có trạng thái PAID được chuyển tiếp. Key và value của record được giữ nguyên.

### filterNot

filterNot là phép ngược của filter: giữ record khi predicate trả về false.

~~~java
KStream<String, OrderEvent> nonPaidOrders =
    orders.filterNot((key, event) ->
        event != null && "PAID".equals(event.status())
    );
~~~

### Khi nào dùng filter?

- Loại event không thuộc phạm vi xử lý.
- Chỉ giữ đơn hàng đã thanh toán.
- Bỏ record không đạt điều kiện chất lượng dữ liệu.
- Chọn một nhóm event trước khi đưa sang nhánh xử lý khác.

filter không thay đổi key, value, partition hay thứ tự tương đối của những record được giữ trong cùng một partition. Nó cũng không tự ghi record bị loại sang topic khác. Nếu cần lưu record không hợp lệ, hãy tạo nhánh riêng hoặc dùng cơ chế xử lý lỗi phù hợp.

### Cẩn thận với value null

Kafka record có thể có key nhưng value null, ví dụ tombstone. Predicate có thể nhận value null; vì vậy cần kiểm tra null trước khi truy cập field:

~~~java
KStream<String, OrderEvent> validOrders =
    orders.filter((key, event) ->
        key != null
            && event != null
            && event.orderId() != null
    );
~~~

Nếu nghiệp vụ cần xử lý tombstone, không lọc bỏ chúng một cách vô thức. Hãy xác định tombstone có nghĩa xóa key khỏi state hay chỉ cần bỏ qua trong nhánh event hiện tại.

## 3. map: biến đổi cả key và value

map nhận key và value hiện tại rồi trả về một KeyValue mới. Nó cho phép thay cả key lẫn value, đồng thời có thể đổi kiểu dữ liệu.

~~~java
KStream<String, OrderSummary> summaries =
    orders.map((oldKey, event) -> KeyValue.pair(
        event.orderId(),
        new OrderSummary(
            event.orderId(),
            event.customerId(),
            event.totalAmount()
        )
    ));
~~~

Ở đây:

- Key cũ có thể là một định danh khác.
- Key mới là event.orderId().
- Value mới là OrderSummary.
- Kiểu value đã đổi từ OrderEvent sang OrderSummary.

map hữu ích khi cần chuẩn hóa key, đổi schema dữ liệu, kết hợp field hoặc chuyển record sang một kiểu biểu diễn mới.

### Ví dụ thay đổi key và value

~~~java
KStream<String, String> normalized =
    rawOrders.map((oldKey, rawValue) -> {
        String[] fields = rawValue.split("\\|", -1);
        String orderId = fields[0].trim();
        String customerId = fields[1].trim();
        String status = fields[2].trim().toUpperCase(Locale.ROOT);

        String newValue = customerId + "|" + status;
        return KeyValue.pair(orderId, newValue);
    });
~~~

Ví dụ input có key source-row-9 và value 101|customer-7|paid|250000, output có key 101 và value customer-7|PAID.

### map có thể làm thay đổi partitioning

Key mới có thể khác key cũ. Nếu record sau đó đi vào thao tác phụ thuộc key như groupByKey, join hoặc aggregation, Kafka Streams có thể cần repartition để đưa các record cùng key về đúng partition.

Không nên dùng map chỉ để thay value khi key phải được giữ nguyên. Trong trường hợp đó mapValues thể hiện ý định rõ hơn và cho phép Kafka Streams giữ nguyên partitioning metadata.

## 4. mapValues: chỉ biến đổi value

mapValues thay value và giữ nguyên key. Đây là lựa chọn phù hợp khi nghiệp vụ chỉ cần tính toán hoặc chuyển đổi payload.

~~~java
KStream<String, OrderView> views =
    orders.mapValues(event ->
        new OrderView(
            event.orderId(),
            event.status(),
            event.totalAmount()
        )
    );
~~~

Key vẫn là order-101; chỉ value được chuyển từ OrderEvent sang OrderView.

### mapValues có truy cập được key không?

Có overload nhận cả key và value qua ValueMapperWithKey:

~~~java
KStream<String, String> descriptions =
    orders.mapValues((key, event) ->
        "Order " + key + " has status " + event.status()
    );
~~~

Overload này vẫn giữ nguyên key. Nó chỉ cho mapper đọc key để tính value mới.

### Vì sao mapValues thường hiệu quả hơn map?

Kafka Streams biết mapValues không thay đổi key, nên có thể giữ thông tin partitioning và tránh một lần repartition không cần thiết ở các thao tác key-based tiếp theo. Đây là lý do nên ưu tiên mapValues khi không có nhu cầu đổi key.

Điều này chỉ có nghĩa mapValues không tự tạo thêm yêu cầu repartition. Nếu upstream đã dùng map, flatMap hoặc selectKey để đổi key, mapValues không xóa yêu cầu repartition mà toán tử trước đó đã tạo ra.

| Tiêu chí | map | mapValues |
|---|---|---|
| Đọc key đầu vào | Có | Có ở overload ValueMapperWithKey |
| Thay key | Có | Không |
| Thay value | Có | Có |
| Đổi kiểu value | Có | Có |
| Bảo toàn key/partitioning metadata | Không bảo đảm | Có |
| Dùng khi | Cần tính lại key và/hoặc value | Chỉ cần tính lại value |

## 5. flatMap: một record tạo ra nhiều record

flatMap nhận một record và trả về một Iterable<KeyValue<KR, VR>>. Từ một record đầu vào, mapper có thể tạo:

- Không record nào: loại record khỏi nhánh.
- Một record: tương tự map.
- Nhiều record: fan-out một event thành nhiều event.

Ví dụ một đơn hàng có nhiều sản phẩm; tạo một record cho mỗi sản phẩm:

~~~java
KStream<String, OrderLine> orderLines =
    orders.flatMap((orderKey, event) -> {
        if (event == null || event.items() == null) {
            return List.of();
        }

        return event.items().stream()
            .map(item -> KeyValue.pair(
                event.orderId(),
                new OrderLine(
                    event.orderId(),
                    item.productId(),
                    item.quantity()
                )
            ))
            .toList();
    });
~~~

Một order có ba item sẽ tạo ba record OrderLine. Nếu danh sách item rỗng, mapper trả về danh sách rỗng và không có record nào được phát ra.

### flatMap khác map như thế nào?

| Input | map | flatMap |
|---|---|---|
| Một record | Một KeyValue output | Iterable có thể chứa 0, 1 hoặc nhiều KeyValue |
| Đổi key | Có | Có |
| Fan-out | Không trực tiếp | Có |
| Loại record bằng output rỗng | Không | Có |

flatMap phù hợp khi tách một event tổng hợp thành nhiều event nhỏ, bung danh sách, tách nội dung hoặc phát nhiều loại record từ một input.

### Thứ tự khi fan-out

Các output do một lần gọi mapper tạo ra được chuyển tiếp theo thứ tự iterable trả về trong cùng processor invocation. Tuy nhiên, khi có nhiều task/partition hoặc xử lý song song downstream, không có thứ tự toàn cục giữa các partition. Nếu thứ tự của cùng entity quan trọng, giữ key ổn định và thiết kế partitioning phù hợp.

## 6. flatMapValues: mở rộng value nhưng giữ key

Nếu cần tạo nhiều value từ một record nhưng tất cả output vẫn dùng cùng key, flatMapValues đơn giản hơn flatMap.

~~~java
KStream<String, String> productIds =
    orders.flatMapValues(event ->
        event == null || event.items() == null
            ? List.of()
            : event.items().stream()
                .map(OrderItem::productId)
                .toList()
    );
~~~

Một order có ba sản phẩm tạo ba record, cả ba đều giữ key của order ban đầu.

| Toán tử | Có đổi key? | Có thể tạo nhiều record? |
|---|---:|---:|
| flatMap | Có | Có |
| flatMapValues | Không | Có |

flatMapValues là lựa chọn phù hợp khi key đã đúng và chỉ cần bung danh sách value. Vì key được giữ nguyên, Kafka Streams cũng giữ được thông tin partitioning theo key đầu vào.

## 7. selectKey: tính lại key, giữ nguyên value

selectKey nhận key/value hiện tại và trả về key mới. Value được giữ nguyên:

~~~java
KStream<String, OrderEvent> ordersByCustomer =
    orders.selectKey((orderKey, event) ->
        event == null ? null : event.customerId()
    );
~~~

Ví dụ record ban đầu có key order-101; sau selectKey, key trở thành customer-7, còn value vẫn là OrderEvent.

Các trường hợp thường dùng:

- Đổi từ order ID sang customer ID để xử lý theo khách hàng.
- Đổi key sang account ID trước khi aggregate số dư.
- Chuẩn hóa key từ field trong payload.
- Đưa record về cùng key logic trước khi join/group.

### selectKey không tự repartition ngay

selectKey cập nhật key của record trong topology, nhưng không ngay lập tức ghi lại toàn bộ stream vào topic repartition. Nếu tiếp theo là thao tác phụ thuộc key như groupByKey, Kafka Streams có thể tự chèn repartition node/topic nội bộ khi cần. Nếu muốn chủ động điểm phân phối lại, có thể gọi repartition():

map và flatMap cũng có thể làm thay đổi key; nếu topology tiếp tục group/join/aggregate theo key mới, hãy kiểm tra topology description để xác nhận có repartition node tại đúng vị trí.

~~~java
KStream<String, OrderEvent> byCustomer =
    orders.selectKey((orderKey, event) -> event.customerId())
        .repartition(
            Repartitioned.with(
                Serdes.String(),
                orderEventSerde
            )
        );
~~~

Repartition tạo luồng trung gian được phân phối lại theo key mới. Việc này có chi phí serialize, ghi/đọc topic nội bộ và network. Chỉ dùng khi cần bảo đảm record được phân vùng theo key mới trước thao tác downstream hoặc khi muốn chủ động topology.

Nếu chỉ gọi to() để ghi ra topic khác, sink producer sẽ dùng key mới và partitioner của topic đích để chọn partition theo cấu hình. Điều đó không đồng nghĩa các bước xử lý trước to() đã được repartition theo key mới.

## 8. Kết hợp các toán tử trong một topology

Giả sử topic orders.raw có value theo định dạng:

~~~text
orderId|customerId|status|amount
~~~

Ví dụ:

~~~text
key=source-1 value=101|customer-7|PAID|250000
key=source-2 value=102|customer-8|NEW|180000
key=source-3 value=103|customer-7|PAID|320000
~~~

Topology dưới đây thực hiện:

1. filter: chỉ giữ đơn hàng PAID hợp lệ.
2. map: đổi key từ source key sang order ID và rút gọn value.
3. mapValues: chuẩn hóa payload mà không đổi order ID.
4. flatMap: phát hai event từ một order.
5. selectKey: đổi key sang customer ID.
6. to: ghi các event vào topic đầu ra.

~~~java
import java.util.List;
import java.util.Locale;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KeyValue;
import org.apache.kafka.streams.kstream.Produced;

public class OrderTopology {

    public static void build(StreamsBuilder builder) {
        KStream<String, String> raw =
            builder.stream(
                "orders.raw",
                Consumed.with(Serdes.String(), Serdes.String())
            );

        KStream<String, String> paidEvents = raw
            .filter((sourceKey, value) -> isValidPaidOrder(value))
            .map((sourceKey, value) -> {
                String[] fields = value.split("\\|", -1);
                String orderId = fields[0].trim();
                String customerId = fields[1].trim();
                String status = fields[2].trim();
                String amount = fields[3].trim();

                return KeyValue.pair(
                    orderId,
                    customerId + "|" + status + "|" + amount
                );
            })
            .mapValues((orderId, payload) -> {
                String[] fields = payload.split("\\|", -1);
                return fields[0] + "|"
                    + fields[1].toUpperCase(Locale.ROOT) + "|"
                    + fields[2];
            })
            .flatMap((orderId, payload) -> {
                String[] fields = payload.split("\\|", -1);
                String customerId = fields[0];
                String amount = fields[2];

                return List.of(
                    KeyValue.pair(
                        orderId,
                        "ORDER_PAID|" + customerId + "|" + orderId
                    ),
                    KeyValue.pair(
                        orderId,
                        "AMOUNT_PAID|" + customerId + "|" + amount
                    )
                );
            })
            .selectKey((orderId, event) ->
                event.split("\\|", -1)[1]
            );

        paidEvents.to(
            "orders.customer-events",
            Produced.with(Serdes.String(), Serdes.String())
        );
    }

    private static boolean isValidPaidOrder(String value) {
        if (value == null) {
            return false;
        }

        String[] fields = value.split("\\|", -1);
        return fields.length == 4
            && !fields[0].isBlank()
            && !fields[1].isBlank()
            && "PAID".equalsIgnoreCase(fields[2]);
    }
}
~~~

Với input order 101 và 103, topology tạo các event có key customer-7. Order 102 bị filter vì trạng thái NEW. mapValues chỉ chuẩn hóa status thành chữ hoa và giữ nguyên customer ID. Value đầu ra có hai loại event: ORDER_PAID và AMOUNT_PAID.

Ví dụ dùng String để tập trung vào semantics của DSL. Trong ứng dụng thực tế, nên dùng schema/POJO và SerDe tương ứng thay vì ghép chuỗi; kiểm tra dữ liệu đầu vào trước khi parse và định nghĩa cách xử lý record lỗi.

## 9. SerDes khi thay đổi kiểu dữ liệu

SerDe (Serializer/Deserializer) quy định cách chuyển key/value giữa object Java và byte array Kafka. Source stream khai báo SerDes đầu vào; sink hoặc stateful operator có thể cần SerDes cho kiểu dữ liệu mới.

| Toán tử | Ảnh hưởng kiểu dữ liệu | Điều cần kiểm tra |
|---|---|---|
| filter | Không đổi key/value type | SerDes giữ nguyên |
| map | Có thể đổi key và value type | SerDes cho key/value mới ở sink hoặc repartition |
| mapValues | Có thể đổi value type | SerDe value mới ở sink/state store |
| flatMap | Có thể đổi key/value type | SerDes cho output mới |
| selectKey | Có thể đổi key type | Key SerDe mới khi repartition hoặc ghi topic |

Ví dụ khi key được đổi từ String sang Long, các bước downstream cần dùng Long SerDe. Nếu cấu hình Produced.with(Serdes.String(), ...) trong khi key thực tế là Long, serialization sẽ thất bại.

Kafka Streams có thể cần serialize dữ liệu khi ghi repartition topic hoặc state store. Vì vậy, lỗi SerDe có thể xuất hiện ở giữa topology chứ không chỉ tại source/sink.

## 10. Key, partition và ordering sau selectKey/map

Kafka bảo đảm thứ tự trong một partition. Các record cùng key thường được partitioner mặc định đưa về cùng partition của một topic. Tuy nhiên, sau khi đổi key trong topology, record vẫn đang được xử lý theo partition nguồn cho đến khi có bước repartition hoặc sink.

Ví dụ:

~~~text
Source topic:
partition 0: order-101 -> customer-7
partition 1: order-103 -> customer-7
~~~

Sau selectKey(customerId), hai record đều có key customer-7 nhưng có thể vẫn đang chạy trên hai task/partition nguồn khác nhau. Nếu tiếp tục aggregate theo customer, Kafka Streams cần repartition để đưa các record cùng customer về cùng partition của repartition topic.

Không giả định selectKey tự bảo đảm thứ tự toàn cục của customer. Nếu cần thứ tự theo entity, hãy:

- Dùng cùng một key ổn định cho mọi event của entity.
- Repartition trước thao tác stateful theo key mới.
- Không xử lý bất đồng bộ bên ngoài làm đảo thứ tự hoàn tất.
- Kiểm tra ảnh hưởng khi thay đổi số partition hoặc partitioner.

## 11. Null và tombstone qua các toán tử

Trong Kafka, record có value null thường được dùng làm tombstone. KStream có thể nhận record như vậy; mapper cần có chủ đích khi xử lý.

| Toán tử | Lưu ý với value null |
|---|---|
| filter | Predicate có thể nhận null; kiểm tra null trước khi đọc field |
| map | Mapper nhận null; cần quyết định bỏ qua, biến đổi hoặc phát record phù hợp |
| mapValues | Mapper nhận null; giá trị trả về null vẫn là record có value null |
| flatMap | Mapper nhận null; có thể trả iterable rỗng để loại record |
| selectKey | Mapper nhận null; có thể trả key null, nhưng key null không phù hợp cho các thao tác cần partition theo key |

Một record output có value null vẫn có thể mang semantics tombstone ở sink. Đừng vô tình biến lỗi parse thành null value nếu downstream sẽ hiểu đó là xóa key.

Nếu topology dùng KTable, tombstone có ý nghĩa xóa row khỏi table state. Với KStream, record null là một event trong stream; cách downstream diễn giải phụ thuộc toán tử và việc chuyển sang KTable/changelog.

## 12. Stateless mapper và xử lý lỗi

Các mapper nên là hàm xác định (deterministic) và tránh side effect:

- Không gọi API thanh toán hoặc gửi email trực tiếp trong mapValues.
- Không ghi database ngoài trong flatMap.
- Không tạo kết quả phụ thuộc trạng thái mutable dùng chung giữa task.
- Không giả định mapper chỉ chạy đúng một lần; task có thể khôi phục và xử lý lại record.

Nếu cần gọi dịch vụ ngoài, cân nhắc tách thành consumer/service chuyên trách với retry, idempotency và quan sát lỗi rõ ràng.

Lỗi parse hoặc exception trong mapper có thể làm stream task thất bại tùy exception handler và cấu hình ứng dụng. Hãy xác định chiến lược:

- Kiểm tra schema/field trước khi biến đổi.
- Gửi record lỗi sang nhánh quarantine/DLQ nếu thiết kế topology hỗ trợ.
- Ghi log kèm topic, partition, offset và correlation ID; tránh log payload nhạy cảm.
- Cấu hình production exception handler phù hợp với mức độ nghiêm trọng.

Không dùng filter để âm thầm loại dữ liệu lỗi nếu cần kiểm toán hoặc khắc phục sau này.

## 13. Kiểm thử topology

Kafka Streams cung cấp TopologyTestDriver để kiểm thử DSL mà không cần chạy broker thật. Có thể tạo input topic, pipe record và đọc output topic trong bộ nhớ.

Ví dụ khung kiểm thử:

~~~java
import java.util.List;
import java.util.Properties;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.TopologyTestDriver;
import org.apache.kafka.streams.TestInputTopic;
import org.apache.kafka.streams.TestOutputTopic;
import org.apache.kafka.streams.StreamsBuilder;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderTopologyTest {

    @Test
    void filtersAndExpandsPaidOrders() {
        StreamsBuilder builder = new StreamsBuilder();
        OrderTopology.build(builder);

        Properties props = new Properties();
        props.put(StreamsConfig.APPLICATION_ID_CONFIG, "orders-test");
        props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, "dummy:9092");

        try (TopologyTestDriver driver =
                new TopologyTestDriver(builder.build(), props)) {

            TestInputTopic<String, String> input =
                driver.createInputTopic(
                    "orders.raw",
                    Serdes.String().serializer(),
                    Serdes.String().serializer()
                );

            TestOutputTopic<String, String> output =
                driver.createOutputTopic(
                    "orders.customer-events",
                    Serdes.String().deserializer(),
                    Serdes.String().deserializer()
                );

            input.pipeInput(
                "source-1",
                "101|customer-7|PAID|250000"
            );
            input.pipeInput(
                "source-2",
                "102|customer-8|NEW|180000"
            );

            List<KeyValue<String, String>> records =
                output.readKeyValuesToList();

            // Kỳ vọng hai output cho order 101; order 102 bị filter.
            assertEquals(2, records.size());
        }
    }
}
~~~

Ví dụ cần dependency kafka-streams-test-utils cùng phiên bản với kafka-streams và JUnit 5. Các import ở trên minh họa những lớp được dùng; trong dự án thực tế, tạo builder từ đúng topology được kiểm thử và thêm assertion cho key/value cụ thể. Source và sink trong topology cần khai báo SerDes tường minh như ví dụ ở phần kết hợp toán tử.

Các ca kiểm thử nên có:

1. Record PAID hợp lệ được giữ.
2. Record NEW bị filter.
3. map đổi key đúng order ID.
4. mapValues giữ key nhưng chuẩn hóa value.
5. flatMap tạo đúng số output.
6. selectKey đổi key sang customer ID.
7. Input value null không gây NullPointerException.
8. SerDe đầu ra khớp kiểu key/value sau biến đổi.
9. Repartition trước groupByKey đưa cùng key về cùng phân vùng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Key output không như mong muốn | Dùng mapValues trong khi cần đổi key | Dùng map hoặc selectKey |
| Mapper không compile | Trả về value thay vì KeyValue trong map/flatMap | Kiểm tra generic type và kiểu trả về |
| Chỉ nhận một output khi cần nhiều | Dùng map thay cho flatMap | Dùng flatMap hoặc flatMapValues |
| Record cùng entity bị aggregate sai | Key mới chưa được repartition trước thao tác key-based | Dùng groupBy/groupByKey đúng cách hoặc repartition() |
| SerializationException | SerDe không khớp kiểu key/value sau operator | Cấu hình SerDe mới ở source, repartition hoặc sink |
| NullPointerException | Mapper truy cập field khi value null | Kiểm tra null trước khi xử lý |
| Tombstone bị mất ý nghĩa | Filter hoặc mapper loại record null ngoài ý muốn | Thiết kế riêng semantics delete |
| Topology chậm sau map/flatMap | Mapper parse nặng hoặc fan-out quá lớn | Tối ưu phép biến đổi, giới hạn fan-out và theo dõi throughput |

## 15. Bài tập tự kiểm tra

1. filter khác map ở đầu ra như thế nào?
2. Vì sao mapValues có thể giúp tránh repartition không cần thiết?
3. Khi nào chọn map thay vì selectKey?
4. flatMap có thể tạo bao nhiêu output cho một input?
5. flatMapValues khác flatMap ở cách giữ key ra sao?
6. selectKey có tự ghi record vào repartition topic ngay không?
7. Vì sao đổi key trước groupByKey có thể cần repartition?
8. Nếu mapValues trả về null, downstream có thể nhận semantics gì?
9. Vì sao không nên gọi API ngoài có side effect trong mapper?
10. Cần kiểm thử những trường hợp nào với tombstone và SerDe?

## Kết luận

Năm toán tử DSL có trách nhiệm khác nhau: filter chọn record; map biến đổi cả key/value; mapValues chỉ biến đổi value và giữ key; flatMap mở rộng một record thành nhiều cặp key/value; selectKey tính lại key và giữ value. flatMapValues là lựa chọn bổ sung khi muốn bung nhiều value nhưng giữ nguyên key.

Khi kết hợp chúng, cần theo dõi kiểu dữ liệu và SerDes sau mỗi phép biến đổi, xử lý null/tombstone có chủ đích, và hiểu rằng đổi key chưa đồng nghĩa đã repartition. Nếu downstream group, join hoặc aggregate theo key mới, hãy bảo đảm repartition phù hợp. Mapper nên deterministic, không chứa side effect và cần được kiểm thử với record hợp lệ, dữ liệu lỗi và tombstone.
