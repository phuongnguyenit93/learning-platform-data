# Gom nhóm, đếm và tổng hợp theo khóa

Trong xử lý luồng sự kiện, nhiều câu hỏi nghiệp vụ yêu cầu ghi nhớ kết quả tích lũy theo một khóa: mỗi khách hàng đã tạo bao nhiêu đơn hàng, mỗi tài khoản có tổng số tiền giao dịch là bao nhiêu, hoặc mỗi sản phẩm được đặt bao nhiêu lần trong một khoảng thời gian. Nếu chỉ dùng các phép biến đổi không trạng thái như `map` và `filter`, ứng dụng không thể tự nhớ tổng đã tính từ những message trước.

Kafka Streams cung cấp các phép `groupByKey`, `groupBy`, `count`, `reduce` và `aggregate` để gom các record theo khóa rồi cập nhật trạng thái tích lũy. Spring Cloud Stream Kafka Streams binder kết nối các phép này với mô hình hàm `Function`/`Consumer`, input/output binding và cấu hình ứng dụng Spring Boot. Bài học này tập trung vào cách chọn khóa đúng, hiểu kết quả `KTable`, xây dựng phép đếm/tổng hợp, lưu state store và vận hành topology có trạng thái.

Các ví dụ dùng Kafka Streams binder (`spring-cloud-stream-binder-kafka-streams`). Đây là tích hợp dành riêng cho Kafka Streams; RabbitMQ binder và Pulsar binder không cung cấp trực tiếp các kiểu `KStream`/`KTable` của Kafka Streams. Nếu dùng RabbitMQ hoặc Pulsar làm broker, cần chọn cơ chế xử lý trạng thái phù hợp với binder và nền tảng tương ứng.

## 1. Bài toán: tổng hợp sự kiện theo khóa

Giả sử hệ thống thương mại điện tử phát các sự kiện `OrderCreated` vào topic `orders.created`. Mỗi sự kiện chứa mã đơn hàng, khách hàng và giá trị đơn hàng:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalCents
) {}
```

Một số sự kiện mẫu:

| Key hiện tại | eventId | orderId | customerId | totalCents |
| --- | --- | --- | --- | ---: |
| `ORD-101` | `EVT-1` | `ORD-101` | `CUS-A` | 125000 |
| `ORD-102` | `EVT-2` | `ORD-102` | `CUS-B` | 80000 |
| `ORD-103` | `EVT-3` | `ORD-103` | `CUS-A` | 45000 |
| `ORD-104` | `EVT-4` | `ORD-104` | `CUS-A` | 30000 |

Nếu cần đếm số đơn hàng theo khách hàng, khóa tổng hợp phải là `customerId`, không phải `orderId`. Kết quả sau bốn sự kiện là:

| customerId | orderCount |
| --- | ---: |
| `CUS-A` | 3 |
| `CUS-B` | 1 |

Nếu cần tính tổng giá trị đơn hàng, kết quả là:

| customerId | orderCount | totalCents |
| --- | ---: | ---: |
| `CUS-A` | 3 | 250000 |
| `CUS-B` | 1 | 80000 |

Điểm cốt lõi là mọi record có cùng khóa tổng hợp được đưa tới cùng một phép tính trạng thái. Kafka Streams giữ kết quả hiện tại cho từng khóa và cập nhật nó khi record mới đến.

## 2. KStream, KTable và ý nghĩa của dữ liệu

Trước khi gom nhóm, cần phân biệt hai mô hình dữ liệu quan trọng:

| Kiểu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `KStream<K, V>` | Luồng các sự kiện độc lập; mỗi record là một sự kiện đã xảy ra | `OrderCreated`, `PaymentReceived`, `InventoryReserved` |
| `KTable<K, V>` | Bảng trạng thái hiện tại theo khóa; record mới cập nhật giá trị của khóa đó | Bảng `customerId -> customerProfile` |

Với `KStream`, hai record cùng key là hai sự kiện riêng biệt. Với `KTable`, hai record cùng key thường biểu diễn hai phiên bản của cùng một hàng; giá trị mới thay thế giá trị trước đó. Trong KTable, record có value `null` là tombstone, nghĩa là xóa khóa khỏi bảng.

Khi tổng hợp một luồng sự kiện, đầu vào thường là `KStream`. Khi tổng hợp một bảng thay đổi, đầu vào có thể là `KTable` và các phép tính phải xét cả việc giá trị cũ bị thay thế hoặc khóa bị xóa.

Spring Cloud Stream Kafka Streams binder hỗ trợ binding đầu vào kiểu `KStream`, `KTable` và `GlobalKTable`. Với bài toán đếm số sự kiện phát sinh, dùng `KStream` là lựa chọn tự nhiên. Với bài toán tính lại số lượng dựa trên trạng thái bảng hiện tại, cần hiểu semantics của `KTable` trước khi chọn phép tổng hợp.

## 3. Khóa quyết định cách gom nhóm

Trong Kafka, key của record ảnh hưởng tới partition mà record được ghi. Các record cùng key thường được gửi tới cùng partition theo partitioner đang sử dụng. Kafka Streams dựa vào key để phân phối các record của cùng nhóm tới cùng task và cập nhật trạng thái tương ứng.

Với ví dụ đơn hàng, nếu producer đã ghi `customerId` làm key, stream có thể gom theo key hiện tại. Nếu producer ghi `orderId` làm key nhưng ứng dụng muốn gom theo `customerId`, ứng dụng phải trích xuất khóa mới từ payload.

Hai trường hợp tương ứng với hai phép toán:

- `groupByKey()`: gom theo key hiện tại của record.
- `groupBy(...)`: tính một key mới từ key/value hiện tại rồi gom theo key mới.

Chọn đúng khóa ngay từ producer có thể giảm chi phí đổi khóa và repartition ở downstream. Tuy nhiên, producer chỉ nên chọn một key phù hợp với yêu cầu phân phối của luồng đó; một topic không thể tối ưu đồng thời cho mọi kiểu tổng hợp khác nhau nếu các phép tính cần các khóa khác nhau.

## 4. groupByKey: giữ nguyên key hiện tại

Nếu record trong `orders.by-customer` đã có key là `customerId`, có thể dùng `groupByKey`:

```java
KGroupedStream<String, OrderCreated> ordersByCustomer =
        orders.groupByKey(
                Grouped.with(Serdes.String(), orderCreatedSerde));
```

`groupByKey` không đổi key. Nó tạo `KGroupedStream`, là kiểu dữ liệu đầu vào cho các phép đếm và tổng hợp. Khi stream đã được phân vùng đúng theo key và không có thao tác trước đó đánh dấu cần repartition, đây thường là cách hiệu quả hơn.

Nếu trước đó ứng dụng đã gọi `selectKey` để thay đổi key, Kafka Streams đánh dấu stream cần repartition. Khi một phép group theo key được thực hiện, topology sẽ dùng repartition để bảo đảm record có cùng key đi tới cùng partition trước khi cập nhật state store.

Không dùng `groupByKey` nếu key hiện tại vẫn là `orderId` trong khi mục tiêu là gom theo `customerId`. Khi đó, các đơn hàng của cùng khách hàng có thể đang nằm ở nhiều partition khác nhau và phép tính sẽ không tạo được tổng theo khách hàng như mong muốn.

## 5. groupBy: tạo khóa tổng hợp mới

Nếu key hiện tại là `orderId`, nhưng muốn tổng hợp theo `customerId`, dùng `groupBy` để trích xuất khóa từ payload:

```java
KGroupedStream<String, OrderCreated> ordersByCustomer = orders
        .filter((orderId, event) ->
                event != null && event.customerId() != null)
        .groupBy(
                (orderId, event) -> event.customerId(),
                Grouped.with(Serdes.String(), orderCreatedSerde));
```

Trong ví dụ:

- Hàm đầu tiên nhận key hiện tại `orderId` và payload `OrderCreated`.
- Hàm trả về `customerId`, là key mới của phép tổng hợp.
- `Grouped.with` khai báo Serde cho key mới và value `OrderCreated`.
- Kafka Streams có thể tạo repartition topic nội bộ để phân phối lại record theo key mới.

`groupBy` luôn có thể yêu cầu repartition vì key được tính lại. Repartition có chi phí ghi/đọc topic nội bộ, serialization và network. Nếu luồng đã được partition theo đúng khóa tổng hợp từ đầu, `groupByKey` có thể tránh được một bước repartition không cần thiết.

### Không để khóa null đi vào phép tổng hợp

Record có key `null` không thể được phân phối theo khóa như mong đợi. Kafka Streams bỏ qua record có null key trong các phép grouping/aggregation theo key. Do đó, hãy kiểm tra khóa trước khi group:

```java
KStream<String, OrderCreated> validOrders = orders
        .filter((orderId, event) ->
                event != null
                        && event.customerId() != null
                        && !event.customerId().isBlank());
```

Không âm thầm thay mọi khóa null thành cùng một chuỗi như `UNKNOWN` nếu điều đó khiến toàn bộ record lỗi dồn vào một nhóm nóng. Nếu nghiệp vụ cho phép nhóm riêng dữ liệu thiếu khóa, hãy dùng một giá trị phân loại có chủ đích và theo dõi số lượng record được đưa vào nhóm đó.

## 6. Serde phải phù hợp với khóa và giá trị sau khi group

Kafka lưu byte, vì vậy Kafka Streams cần `Serde` (serializer/deserializer) cho key và value ở các ranh giới topic, repartition topic và state store.

Một số Serde tích hợp sẵn thường dùng:

| Kiểu Java | Serde |
| --- | --- |
| `String` | `Serdes.String()` |
| `Long` | `Serdes.Long()` |
| `Integer` | `Serdes.Integer()` |
| `UUID` | `Serdes.UUID()` |
| DTO/record nghiệp vụ | `JsonSerde`, Avro Serde hoặc Serde tùy chỉnh |

Khi `groupBy` thay đổi kiểu key, cần cung cấp Serde cho key mới. Khi giá trị là DTO, hãy bảo đảm Serde đọc/ghi đúng schema và tương thích với các producer khác.

Ví dụ khai báo JSON Serde cho sự kiện:

```java
import org.apache.kafka.common.serialization.Serde;
import org.springframework.kafka.support.serializer.JsonSerde;

@Bean
public Serde<OrderCreated> orderCreatedSerde() {
    return new JsonSerde<>(OrderCreated.class);
}
```

Kafka Streams binder có thể suy luận Serde dựa trên kiểu tham số của `Function` hoặc `Consumer`, các bean `Serde` có trong ứng dụng và các kiểu được Kafka Streams hỗ trợ sẵn. Nếu không thể suy luận chính xác, hãy cấu hình Serde tường minh ở binding hoặc trong topology. Đặc biệt, Serde của phép `Grouped` và `Materialized` vẫn là trách nhiệm của code xử lý khi DSL yêu cầu.

Ví dụ binding-level Serde cho một input binding có thể được cấu hình dưới `spring.cloud.stream.kafka.streams.bindings.<binding>.consumer.keySerde` và `valueSerde`. Với output binding, các thuộc tính tương ứng nằm dưới `producer.keySerde` và `producer.valueSerde`. Hãy dùng tên lớp Serde phù hợp với phiên bản và định dạng dữ liệu của dự án.

## 7. Count: đếm số record theo khóa

`count()` phù hợp khi cần đếm số record của từng khóa. Nó nhận một `KGroupedStream` và trả về `KTable<K, Long>` chứa số đếm hiện tại của mỗi khóa.

```java
KTable<String, Long> orderCounts = ordersByCustomer
        .count(Materialized.as("customer-order-counts"));
```

Với ba sự kiện của `CUS-A`, giá trị hiện tại của khóa đó là `3`. Mỗi khi có thêm một record hợp lệ cho `CUS-A`, trạng thái được tăng lên một và KTable phát ra bản cập nhật mới.

`count()` đếm record, không đếm giá trị số trong payload. Nếu mỗi record chứa `quantity = 5`, `count()` vẫn chỉ tăng một. Muốn cộng số lượng hoặc số tiền, dùng `reduce()` hoặc `aggregate()`.

### Đưa KTable thành KStream để xuất kết quả

Kafka Streams trả kết quả `count()` dưới dạng `KTable`, bởi vì nó biểu diễn giá trị hiện tại theo khóa. Nếu muốn binder gửi các lần cập nhật ra output topic, chuyển bảng thành luồng bằng `toStream()`:

```java
KStream<String, Long> countUpdates = orderCounts.toStream();
```

Mỗi record đầu ra biểu diễn một lần cập nhật của giá trị hiện tại. Ví dụ, `CUS-A` có thể phát lần lượt `1`, `2`, rồi `3`. Topic output khi đó chứa lịch sử cập nhật, không chỉ một bản ghi duy nhất cho mỗi khách hàng.

Nếu downstream cần bảng trạng thái mới nhất, có thể đọc topic như changelog/KTable hoặc cấu hình topic output có compaction theo key. Không giả định `toStream()` tự xóa các giá trị cũ khỏi topic.

## 8. Ví dụ hoàn chỉnh: đếm đơn hàng theo khách hàng

Đây là một Kafka Streams processor theo mô hình hàm của Spring Cloud Stream:

```java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.KeyValue;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.support.serializer.JsonSerde;

public record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        long totalCents
) {}

public record CustomerOrderCount(String customerId, long orderCount) {}

@Configuration
public class CustomerOrderCounter {

    @Bean
    public Serde<OrderCreated> orderCreatedSerde() {
        return new JsonSerde<>(OrderCreated.class);
    }

    @Bean
    public Function<KStream<String, OrderCreated>,
            KStream<String, CustomerOrderCount>> countOrdersByCustomer(
                    Serde<OrderCreated> orderCreatedSerde) {

        return orders -> orders
                .filter((orderId, event) ->
                        event != null
                                && event.customerId() != null
                                && !event.customerId().isBlank())
                .groupBy(
                        (orderId, event) -> event.customerId(),
                        Grouped.with(Serdes.String(), orderCreatedSerde))
                .count(Materialized
                        .<String, Long, KeyValueStore<Bytes, byte[]>>as(
                                "customer-order-counts")
                        .withKeySerde(Serdes.String())
                        .withValueSerde(Serdes.Long()))
                .toStream()
                .map((customerId, count) -> KeyValue.pair(
                        customerId,
                        new CustomerOrderCount(customerId, count)));
    }
}
```

Trong ví dụ này:

1. Input binding là `countOrdersByCustomer-in-0`.
2. `groupBy` lấy `customerId` từ payload để tạo key tổng hợp.
3. `Grouped.with` cung cấp Serde cho key `String` và value `OrderCreated`.
4. `count` cập nhật số record theo từng khách hàng.
5. `Materialized.as` đặt tên state store là `customer-order-counts`.
6. `toStream` chuyển các lần cập nhật KTable thành record output.
7. `map` tạo payload `CustomerOrderCount` để downstream dễ sử dụng.

Các record Java có thể được đặt trong file riêng theo quy ước của dự án. Cần bảo đảm JSON Serde có thể serialize/deserialize các record đó và schema được các producer/consumer thống nhất.

## 9. Cấu hình binding và application ID

Hàm trên có một input và một output. Kafka Streams binder tự tạo tên binding theo tên bean:

- `countOrdersByCustomer-in-0`
- `countOrdersByCustomer-out-0`

Ví dụ cấu hình:

```yaml
spring:
  application:
    name: customer-order-counter
  cloud:
    function:
      definition: countOrdersByCustomer
    stream:
      bindings:
        countOrdersByCustomer-in-0:
          destination: orders.created
        countOrdersByCustomer-out-0:
          destination: customers.order-counts
      kafka:
        streams:
          binder:
            applicationId: customer-order-counter
            brokers: localhost:9092
```

`applicationId` là định danh của Kafka Streams application. Các replica của cùng một ứng dụng phải dùng cùng application ID để chia sẻ task và state theo cơ chế Kafka Streams. Những ứng dụng độc lập cần application ID khác nhau để không dùng chung consumer group và state.

Trong production, hãy cấu hình application ID tường minh và ổn định. Không tạo ID ngẫu nhiên cho từng replica, vì mỗi replica khi đó có thể trở thành một Kafka Streams application độc lập, đọc lại toàn bộ dữ liệu và tạo state store riêng.

Kafka Streams binder dùng `KStream` cho input/output trong ví dụ. `KTable` và `GlobalKTable` được hỗ trợ ở input. Nếu ứng dụng dùng nhiều processor/function trong cùng một Spring Boot context, phải chọn rõ các hàm cần kích hoạt bằng `spring.cloud.function.definition` và cấu hình application ID phù hợp cho từng processor.

## 10. Reduce: gộp các giá trị cùng kiểu

`reduce()` phù hợp khi kết quả tổng hợp có cùng kiểu với value đầu vào. Ví dụ, nếu input sau khi group là `KGroupedStream<String, Long>`, có thể cộng các giá trị:

```java
KTable<String, Long> totalByCustomer = amountsByCustomer
        .reduce(Long::sum, Materialized.as("customer-total-cents"));
```

Nếu một khách hàng có các giá trị `100`, `250`, `50`, kết quả tích lũy là `400`. `reduce` không cần giá trị khởi tạo vì giá trị đầu tiên của nhóm trở thành giá trị ban đầu.

`reduce` thường dùng khi phép gộp có dạng kết hợp hai giá trị cùng kiểu, ví dụ:

- Cộng số tiền.
- Tìm giá trị lớn nhất hoặc nhỏ nhất.
- Ghép các chuỗi hoặc cấu trúc cùng kiểu theo quy tắc nghiệp vụ.

Hàm reduce nên có tính kết hợp (associative) để kết quả không phụ thuộc cách Kafka Streams phân nhóm hoặc khôi phục state. Tránh phép toán phụ thuộc thứ tự xử lý nếu topology có thể xử lý song song.

## 11. Aggregate: tạo cấu trúc kết quả khác kiểu đầu vào

`aggregate()` tổng quát hơn `reduce()`. Nó cho phép tạo giá trị tích lũy có kiểu khác với value đầu vào và yêu cầu:

1. `Initializer`: tạo giá trị ban đầu cho một khóa.
2. `Aggregator`: nhận key, value mới và aggregate hiện tại, rồi trả aggregate mới.

Ví dụ muốn tính cả số đơn và tổng số tiền theo khách hàng. Dùng `CustomerStats` làm cấu trúc kết quả:

```java
public record CustomerStats(long orderCount, long totalCents) {

    public static CustomerStats empty() {
        return new CustomerStats(0, 0);
    }

    public CustomerStats add(OrderCreated event) {
        return new CustomerStats(
                orderCount + 1,
                totalCents + event.totalCents());
    }
}
```

Phép aggregate:

```java
KTable<String, CustomerStats> customerStats = ordersByCustomer
        .aggregate(
                CustomerStats::empty,
                (customerId, event, current) -> current.add(event),
                Materialized
                        .<String, CustomerStats,
                                KeyValueStore<Bytes, byte[]>>as(
                                        "customer-order-stats")
                        .withKeySerde(Serdes.String())
                        .withValueSerde(customerStatsSerde));
```

`aggregate` khởi tạo mỗi khách hàng bằng `CustomerStats.empty()`. Mỗi record mới tạo ra một đối tượng `CustomerStats` mới với số đơn tăng một và tổng tiền tăng theo `totalCents` của sự kiện.

Trong ví dụ production, cần khai báo `Serde<CustomerStats>` tương ứng, ví dụ JSON Serde hoặc Avro Serde. Khi dùng tiền tệ, ưu tiên số nguyên theo đơn vị nhỏ nhất như cent hoặc kiểu decimal có quy tắc làm tròn rõ ràng; không dùng `double` cho phép tính tiền cần độ chính xác.

Ví dụ JSON Serde cho aggregate:

```java
@Bean
public Serde<CustomerStats> customerStatsSerde() {
    return new JsonSerde<>(CustomerStats.class);
}
```

### Tránh thay đổi object aggregate tại chỗ

Nên trả về một aggregate mới như ví dụ trên thay vì sửa object mutable đã nhận. Cách dùng object bất biến giúp logic dễ kiểm thử và tránh lỗi do chia sẻ tham chiếu hoặc cập nhật trạng thái không rõ ràng.

## 12. So sánh count, reduce và aggregate

| Phép toán | Đầu vào | Giá trị khởi tạo | Kết quả | Ví dụ |
| --- | --- | --- | --- | --- |
| `count()` | Các record đã group | Tự khởi tạo 0 | `Long` | Số đơn theo khách hàng |
| `reduce()` | Các value cùng kiểu | Không cần; dùng value đầu tiên | Cùng kiểu với value đầu vào | Tổng các khoản tiền `Long` |
| `aggregate()` | Các value đã group | Bắt buộc có initializer | Có thể khác kiểu đầu vào | Số đơn, tổng tiền và thời điểm gần nhất trong một DTO |

Hãy chọn phép toán theo ý nghĩa dữ liệu. `count()` không cộng trường số lượng trong payload. `reduce()` không thuận tiện khi cần đổi kiểu kết quả. `aggregate()` linh hoạt hơn nhưng cần định nghĩa initializer, aggregator và Serde cho state store.

## 13. KGroupedStream và KGroupedTable không giống nhau

Phép group có thể tạo `KGroupedStream` từ `KStream` hoặc `KGroupedTable` từ `KTable`. Cách diễn giải cập nhật khác nhau:

- Với `KGroupedStream`, mỗi record là một sự kiện mới. `count` tăng theo mỗi record; `aggregate` nhận thêm một giá trị vào trạng thái.
- Với `KGroupedTable`, một key có thể được cập nhật bằng giá trị mới hoặc xóa bằng tombstone. Khi một hàng đổi nhóm, phép tổng hợp phải phản ánh việc rút giá trị cũ khỏi nhóm cũ rồi thêm giá trị mới vào nhóm mới.

Vì vậy, các phép `aggregate` trên grouped table có thể yêu cầu cả aggregator cộng thêm và subtractor để đảo tác động của giá trị cũ. Không áp dụng logic đếm event của KStream cho một bảng changelog mà không xét update và delete.

Ví dụ, nếu bảng `ordersById` có key `ORD-1` với customer `CUS-A`, sau đó cập nhật cùng key thành customer `CUS-B`, đây là một hàng được thay đổi. Nếu đếm số đơn theo khách hàng từ KTable, kết quả của `CUS-A` phải giảm và `CUS-B` phải tăng. Nếu coi update đó là một sự kiện tạo đơn mới, số đếm sẽ sai.

## 14. Materialized state store là gì?

Các phép `count`, `reduce` và `aggregate` cần giữ trạng thái giữa các record. Kafka Streams materialize kết quả vào state store. Khi dùng high-level DSL, state store được tạo tự động nếu topology có phép toán yêu cầu state.

Đặt tên store bằng `Materialized.as("customer-order-counts")` giúp:

- Đặt tên ổn định để quan sát và truy vấn state.
- Cấu hình Serde cho key/value của store.
- Cấu hình retention cho windowed store khi phù hợp.
- Kết nối store với API Interactive Queries nếu ứng dụng cần đọc trạng thái hiện tại.

Với state store persistent, dữ liệu thường được lưu cục bộ trên instance (ví dụ RocksDB) và được sao lưu bằng changelog topic của Kafka. Khi instance gặp sự cố hoặc task được chuyển sang instance khác, Kafka Streams có thể khôi phục state bằng cách đọc changelog. Đây là lý do state store có thể duy trì kết quả tích lũy qua restart mà không cần ứng dụng tự nạp lại toàn bộ trạng thái từ một database bên ngoài.

Không nên tắt changelog logging cho state store quan trọng nếu chưa hiểu hệ quả: store không còn khả năng phục hồi đầy đủ từ changelog và không thể có standby replica theo cơ chế tương ứng.

### Tên state store phải ổn định và duy nhất

Không dùng cùng một tên store cho các phép tổng hợp độc lập trong cùng topology. Tên store cũng trở thành một phần của hạ tầng vận hành; đổi tên có thể khiến Kafka Streams tạo store/changelog mới và phải dựng lại state từ input topic. Hãy quản lý việc đổi tên như một thay đổi migration, nhất là với topic có retention hữu hạn.

## 15. Materialized state store trong Kafka Streams binder

Với phép DSL như `count(Materialized.as(...))`, store được tạo theo topology. Nếu input binding là `KTable` và muốn materialize dữ liệu đầu vào thành một store có tên cụ thể, Kafka Streams binder hỗ trợ thuộc tính `materializedAs` ở consumer binding:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            process-in-1:
              consumer:
                materializedAs: incoming-customer-table
```

Thuộc tính này dành cho việc materialize một incoming `KTable` binding. Nó không thay thế `Materialized.as(...)` trên phép `count`, `reduce` hoặc `aggregate` trong DSL. Hãy phân biệt state store của bảng đầu vào với state store do phép tổng hợp tạo ra.

Với Processor API cấp thấp, ứng dụng có thể cần đăng ký `StoreBuilder` bean thủ công. Với high-level DSL, các phép stateful thường tự tạo store cần thiết; hãy chỉ khai báo thủ công khi topology hoặc API yêu cầu.

## 16. Windowed aggregation: tổng hợp theo khóa và cửa sổ

Tổng hợp không cửa sổ giữ một giá trị tích lũy cho mỗi khóa trong toàn bộ thời gian lưu trạng thái. Nếu câu hỏi nghiệp vụ là “mỗi khách hàng đặt bao nhiêu đơn trong 5 phút gần nhất” hoặc “mỗi sản phẩm bán được bao nhiêu trong từng giờ”, cần kết hợp group với window.

Các loại cửa sổ phổ biến:

| Loại | Hành vi | Ví dụ |
| --- | --- | --- |
| Tumbling | Cửa sổ cố định, không chồng lấp | Đếm đơn theo từng khoảng 5 phút |
| Hopping | Cửa sổ cố định, có thể chồng lấp, có bước dịch chuyển | Đếm đơn trong 10 phút, cập nhật mỗi phút |
| Sliding | Cửa sổ dựa trên khoảng cách timestamp giữa record; dùng cho các phép tính/join tương ứng | So sánh hai sự kiện xảy ra trong khoảng 30 giây |
| Session | Cửa sổ theo hoạt động, mở rộng khi có sự kiện mới và kết thúc sau khoảng im lặng | Gom chuỗi hoạt động của một khách hàng |

Ví dụ đếm số đơn theo khách hàng trong các cửa sổ 5 phút, cho phép sự kiện đến muộn trong 1 phút:

```java
import java.time.Duration;

import org.apache.kafka.streams.kstream.TimeWindows;

KTable<Windowed<String>, Long> fiveMinuteCounts = ordersByCustomer
        .windowedBy(TimeWindows.ofSizeAndGrace(
                Duration.ofMinutes(5),
                Duration.ofMinutes(1)))
        .count(Materialized.as("customer-order-counts-5m"));
```

Khóa của kết quả là `Windowed<String>`, gồm customer ID và thông tin cửa sổ. Không bỏ phần window start/end nếu downstream cần phân biệt hai cửa sổ khác nhau của cùng khách hàng.

### Event time, grace period và late events

Kafka Streams dùng timestamp của record theo `TimestampExtractor` để xác định cửa sổ. Nếu record tới trễ nhưng timestamp thuộc một cửa sổ chưa đóng, grace period cho phép nó vẫn được tính. Khi stream time đã vượt quá thời điểm kết thúc cửa sổ cộng grace, record quá muộn sẽ không được đưa vào phép tính của cửa sổ đó.

Grace period không phải thời gian chờ cố định trước khi phát mọi kết quả. Nó xác định mức độ trễ được chấp nhận cho window. Hãy chọn dựa trên phân bố độ trễ thực tế và yêu cầu nghiệp vụ.

### Phát kết quả liên tục hay chỉ phát kết quả cuối?

KTable windowed aggregation có thể phát các bản cập nhật khi số đếm thay đổi. Nếu downstream chỉ cần kết quả cuối cùng khi cửa sổ đóng, có thể dùng suppression (`untilWindowCloses`) để giữ và phát kết quả cuối. Buffer của suppression cần giới hạn dung lượng và có chính sách khi đầy; không dùng buffer không giới hạn cho lưu lượng production nếu chưa tính toán bộ nhớ.

## 17. Repartition, partition count và khóa nóng

Khi `groupBy` thay đổi key, Kafka Streams có thể tạo repartition topic nội bộ. Số partition của repartition topic ảnh hưởng khả năng xử lý song song. Việc chọn khóa cũng quyết định tải phân phối:

- Nếu hầu hết record thuộc một customer ID, một partition có thể trở thành hot partition.
- Nếu key có cardinality quá thấp, số task hữu ích bị giới hạn.
- Nếu key là giá trị ngẫu nhiên, cùng một thực thể có thể không được gom vào cùng state.
- Nếu các producer dùng cách serialize hoặc partitioner khác nhau, record cùng key về mặt nghiệp vụ có thể không được phân phối nhất quán.

Để scale, cần xem xét số partition nguồn, repartition topic, số instance và số stream thread. Tăng số instance không tự tạo thêm partition hoặc chia nhỏ một key nóng. Một key cụ thể vẫn cần được xử lý tuần tự trong task sở hữu partition đó.

Nếu thay đổi partition count, hãy đánh giá lại phân phối key, state store và thứ tự xử lý. Một số key có thể được ánh xạ sang partition mới; state được di chuyển và khôi phục theo cơ chế Kafka Streams, nhưng thứ tự nghiệp vụ qua thời điểm migration vẫn cần được thiết kế cẩn thận.

## 18. Duplicate và tính đúng của phép đếm

`count()` tăng một cho mỗi record mà topology xử lý. Nếu cùng một sự kiện được phát hai lần với cùng `eventId`, phép đếm thông thường vẫn tăng hai. Kafka Streams không thể tự suy ra hai record đó là cùng một sự kiện nghiệp vụ chỉ vì payload giống nhau.

Nếu nguồn có thể phát duplicate, hãy cân nhắc:

- Dùng `eventId` duy nhất và deduplicate trước khi group.
- Duy trì state store ghi nhận các event ID đã xử lý trong một khoảng retention phù hợp.
- Đặt giới hạn thời gian deduplication để tránh state tăng vô hạn.
- Thiết kế producer idempotent và transaction phù hợp khi phát sự kiện.
- Kiểm thử restart/replay để xác minh số đếm không tăng ngoài ý muốn.

Kafka Streams có cơ chế processing guarantee để phối hợp offset, state store và output topic trong phạm vi Kafka. Chế độ exactly-once có thể giảm tác động duplicate do retry nội bộ của Kafka Streams, nhưng không tự loại bỏ hai event nghiệp vụ trùng có `eventId` khác nhau và không làm cho database bên ngoài cùng commit nguyên tử.

## 19. Interactive Queries: đọc trạng thái tổng hợp hiện tại

Khi state store đã được materialize với tên ổn định, ứng dụng có thể truy vấn giá trị hiện tại mà không cần đọc lại toàn bộ output topic. Kafka Streams hỗ trợ Interactive Queries; Spring Cloud Stream Kafka Streams binder cung cấp `InteractiveQueryService` để lấy state store.

Ví dụ khái niệm:

```java
ReadOnlyKeyValueStore<String, Long> store =
        interactiveQueryService.getQueryableStoreType(
                "customer-order-counts",
                QueryableStoreTypes.keyValueStore());

Long count = store.get("CUS-A");
```

API cụ thể cần được dùng trong bean có dependency `InteractiveQueryService` và kiểu store tương ứng. Khi ứng dụng chạy nhiều instance, mỗi instance chỉ giữ một phần state theo partition/task. Muốn truy vấn một key bất kỳ, cần xác định instance đang sở hữu key đó và định tuyến request tới đúng host. Cấu hình `application.server` và cơ chế discovery/route phù hợp là cần thiết cho truy vấn phân tán.

Interactive Queries là API đọc state. Không sửa state store trực tiếp qua query API để thay đổi kết quả tổng hợp; mọi cập nhật nên đi qua topology để changelog và kết quả được nhất quán.

## 20. Kiểm thử phép group và aggregate

Nên kiểm tra topology ở nhiều cấp:

### Unit test logic ánh xạ khóa

Kiểm tra event có `customerId` hợp lệ được group đúng; event null hoặc thiếu khóa được lọc hoặc xử lý theo chính sách. Kiểm tra các record có cùng customer ID tạo cùng nhóm.

### TopologyTestDriver

Kafka Streams cung cấp `TopologyTestDriver` để kiểm thử topology mà không cần Kafka broker thật. Test có thể tạo input topic, gửi các record theo key/timestamp, đọc output topic và kiểm tra kết quả count/aggregate.

Các tình huống nên có:

- Hai event cùng key làm count tăng từ 1 lên 2.
- Hai key khác nhau giữ state độc lập.
- `groupBy` đổi từ order ID sang customer ID.
- Serde của input, output và state store hoạt động đúng.
- Record có key null hoặc payload không hợp lệ được xử lý theo chính sách.
- Window boundary, grace period và event đến muộn.
- Duplicate event ID không làm tăng kết quả nếu topology có deduplication.

### Integration test với Kafka

Test với broker thật hoặc Testcontainers để xác minh repartition topic, changelog topic, ACL, application ID, recovery sau restart và behavior khi scale. `TopologyTestDriver` không mô phỏng đầy đủ network, broker rebalance, topic provisioning hoặc khôi phục state từ changelog.

## 21. Quan sát và vận hành stateful aggregation

Các chỉ số quan trọng gồm:

- Throughput input và output theo processor.
- Consumer lag và processing latency.
- Số lần rebalance, số task/partition được gán.
- Thời gian khôi phục state store sau restart hoặc chuyển task.
- Kích thước local state store và dung lượng đĩa.
- Tốc độ ghi changelog và kích thước internal repartition topic.
- Số key, phân bố record theo key và dấu hiệu hot partition.
- Số record bị loại do key null, schema lỗi hoặc quá muộn so với window grace.
- Tỷ lệ duplicate nếu ứng dụng có deduplication.

Khi thấy state store phục hồi chậm, hãy kiểm tra kích thước changelog, local state directory, tốc độ broker và partition assignment. Khi một partition có lag lớn hơn hẳn các partition khác, hãy kiểm tra skew của key trước khi chỉ tăng số instance.

## 22. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Count luôn bằng 0 hoặc không tăng | Sai binding, sai function definition hoặc record không có key hợp lệ | Kiểm tra binding, payload và key trước phép group. |
| Mọi khách hàng có cùng một count | Dùng nhầm key chung hoặc `groupByKey` khi key hiện tại không phải customer ID | Dùng `groupBy` trích xuất đúng khóa hoặc sửa producer key. |
| Một key có nhiều state ở các partition | Producer/partitioner không thống nhất hoặc key bị thay đổi trước group | Chuẩn hóa key và bảo đảm repartition trước aggregate. |
| Ứng dụng lỗi Serde khi khởi động hoặc chạy | Key/value/state store dùng Serde không tương thích | Cấu hình Serde tường minh cho binding, Grouped và Materialized. |
| State store bị tạo lại sau mỗi lần deploy | Đổi application ID, tên store hoặc xóa local state/changelog | Giữ application ID và store name ổn định; quản lý migration có kế hoạch. |
| Tổng tiền sai sau khi có duplicate | Count/aggregate xử lý mỗi record như một event mới | Deduplicate theo event ID hoặc bảo đảm producer idempotent. |
| KTable output phát nhiều bản cập nhật | `toStream()` phát changelog updates chứ không chỉ snapshot cuối | Downstream hiểu update semantics hoặc dùng topic compacted cho latest-by-key. |
| Window không nhận record đến muộn | Stream time đã vượt window end + grace | Chọn grace phù hợp và theo dõi late records. |
| Một partition lag rất cao | Key skew/hot key | Đánh giá lại khóa, mô hình phân phối hoặc chia nhỏ nghiệp vụ có chủ đích. |
| Interactive query không tìm thấy key | Key nằm trên instance khác hoặc store chưa sẵn sàng | Dùng host metadata, `application.server` và retry khi store khởi tạo. |

## 23. Quy trình triển khai một phép tổng hợp theo khóa

Trước khi viết topology, hãy trả lời:

1. Đầu vào là `KStream` sự kiện hay `KTable` trạng thái?
2. Khóa nghiệp vụ nào xác định nhóm tổng hợp?
3. Key hiện tại đã đúng chưa, hay phải dùng `groupBy` để tạo key mới?
4. Có cần repartition không và topic nội bộ có đủ partition/ACL không?
5. Serde nào được dùng cho key, value, repartition và state store?
6. Cần `count`, `reduce` hay `aggregate`?
7. Có cần window theo thời gian/sessions hay chỉ rolling total theo key?
8. State store có tên ổn định và changelog phù hợp không?
9. Output là update stream hay cần snapshot/latest value theo key?
10. Duplicate, event đến muộn và thay đổi schema được xử lý thế nào?
11. Application ID, partition count và số replica có phù hợp không?
12. Metrics, alert và integration test nào chứng minh topology phục hồi đúng?

## Tài liệu tham khảo

- [Spring Cloud Stream Kafka Streams Binder — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream Kafka Streams Binder — State Store](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/state-store.html)
- [Spring Cloud Stream Kafka Streams Binder — Serialization and Deserialization](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html)
- [Apache Kafka Streams — DSL API: Grouping, Aggregating and Windowing](https://kafka.apache.org/documentation/streams/developer-guide/dsl-api/)
- [Apache Kafka Streams — Processor API and Fault-tolerant State Stores](https://kafka.apache.org/documentation/streams/developer-guide/processor-api/)
- [Apache Kafka Streams — Interactive Queries](https://kafka.apache.org/documentation/streams/developer-guide/interactive-queries/)

Hãy đối chiếu tài liệu của release train Spring Cloud Stream và phiên bản Kafka Streams mà dự án đang dùng, nhất là API window, Serde inference, cấu hình application ID và state store. Các ví dụ trong bài minh họa mô hình functional binder; tên property hoặc API cụ thể có thể thay đổi theo phiên bản.

## Kết luận

Gom nhóm và tổng hợp theo khóa là nền tảng của xử lý luồng có trạng thái. `groupByKey` dùng key hiện tại; `groupBy` tạo key mới và có thể phát sinh repartition. Sau khi group, `count` đếm record, `reduce` gộp các giá trị cùng kiểu, còn `aggregate` cho phép xây dựng cấu trúc trạng thái khác kiểu đầu vào. Kết quả thường là `KTable` được materialize vào state store và có thể chuyển thành `KStream` để phát các lần cập nhật. Muốn phép tính đúng và phục hồi ổn định, cần chọn key phù hợp, cấu hình Serde, giữ state store/changelog ổn định, kiểm soát duplicate và window, đồng thời kiểm thử cả topology lẫn môi trường Kafka thực tế.
