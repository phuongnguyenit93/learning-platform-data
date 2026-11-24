# Đổi khóa, repartition và yêu cầu đồng phân vùng

Trong Kafka Streams, record key quyết định dữ liệu được phân phối tới partition nào. Các phép toán có trạng thái như aggregate, join và cập nhật KTable cần những record cùng khóa được xử lý tại cùng một stream task. Vì vậy, khi ứng dụng đổi khóa của record, nó thường phải repartition trước khi thực hiện phép toán trạng thái tiếp theo.

Repartitioning cũng là nền tảng của co-partitioning: các topic tham gia một phép join theo khóa phải có cùng số partition và dùng cùng chiến lược phân phối khóa. Nếu một phía dùng customerId để chọn partition còn phía kia dùng một partitioner khác, hai record có cùng customerId có thể đến hai task khác nhau và phép join không tìm thấy dữ liệu tương ứng.

## 1. Record key quyết định điều gì?

Kafka lưu record trong một topic được chia thành các partition. Record có key thường được partitioner dùng để chọn partition. Các record có cùng key, khi được gửi bằng cùng partitioning strategy và cùng số partition, sẽ đi đến cùng partition. Điều này tạo thứ tự theo key trong một partition và cho phép Kafka Streams xử lý trạng thái cục bộ theo khóa.

Ví dụ topic orders có sáu partition. Nếu key là order-1001, các sự kiện tạo đơn, cập nhật và hủy của đơn đó được gửi theo cùng quy tắc phân vùng sẽ nằm trên cùng partition. Các instance Kafka Streams có thể xử lý các partition độc lập, nhưng mọi sự kiện của cùng key được đưa đến cùng task.

| Thành phần | Ý nghĩa |
|---|---|
| Record key | Định danh dùng để phân nhóm hoặc định tuyến dữ liệu |
| Partition | Phân đoạn log của topic; đơn vị phân phối cho consumer/task |
| Partitioner | Quy tắc chọn partition cho record |
| Key Serde | Chuyển key giữa kiểu Java và byte[] |
| Stream task | Đơn vị xử lý một hoặc nhiều partition input cùng với state tương ứng |
| State store | Nơi lưu trạng thái cục bộ theo key cho aggregate, join hoặc truy vấn |

Key không chỉ là một trường dữ liệu để lọc. Nó xác định nơi record được xử lý và do đó ảnh hưởng trực tiếp đến tính đúng đắn của phép toán trạng thái.

## 2. Khi nào cần đổi key?

Một sự kiện đơn hàng ban đầu có thể được key theo orderId, nhưng một báo cáo doanh thu cần gom dữ liệu theo customerId. Khi đó, ứng dụng cần đổi key từ orderId sang customerId.

Ví dụ:

| Key ban đầu | Payload | Key mới cần dùng |
|---|---|---|
| order-1001 | customerId=c-42, amount=120 | c-42 |
| order-1002 | customerId=c-17, amount=80 | c-17 |
| order-1003 | customerId=c-42, amount=55 | c-42 |

Hai đơn hàng order-1001 và order-1003 thuộc cùng khách hàng c-42. Muốn aggregate tổng doanh thu theo khách hàng, cả hai record phải được chuyển về cùng partition theo key c-42.

### 2.1. Đổi value và đổi key là hai thao tác khác nhau

Kafka Streams DSL có các phép biến đổi phổ biến:

| Phép toán | Thay đổi value | Thay đổi key | Đánh dấu cần repartition |
|---|---:|---:|---:|
| mapValues | Có | Không | Không |
| filter | Không | Không | Không |
| filterNot | Không | Không | Không |
| selectKey | Không | Có thể | Có |
| map | Có thể | Có thể | Có |
| flatMap | Có thể tạo nhiều record | Có thể | Có |
| flatMapValues | Có thể tạo nhiều value | Không | Không |

Nếu chỉ chuẩn hóa tên khách hàng trong payload mà vẫn giữ key orderId, có thể dùng mapValues. Nếu muốn chuyển sang key customerId, dùng selectKey hoặc map.

Ví dụ đổi key:

~~~java
KStream<String, Order> ordersByCustomer = orders
    .selectKey((orderId, order) -> order.customerId());
~~~

Sau selectKey, key logic của mỗi record đã là customerId. Tuy nhiên, record chưa nhất thiết được ghi lại vào partition tương ứng với key mới. selectKey đánh dấu stream cần repartition; một phép grouping hoặc join ở phía sau có thể kích hoạt bước phân phối lại.

Ví dụ chỉ đổi value và giữ key:

~~~java
public record OrderSummary(
    String orderId,
    String customerId,
    BigDecimal amount
) {}

KStream<String, OrderSummary> summaries = orders
    .mapValues(order -> new OrderSummary(
        order.orderId(),
        order.customerId(),
        order.amount()
    ));
~~~

Trong ví dụ này, key vẫn là orderId. Việc tạo thêm trường customerId trong payload không tự thay đổi partition key.

## 3. Vì sao đổi key thường phải repartition?

Giả sử topic đầu vào được chia thành sáu partition theo orderId. Một task đang xử lý partition 2 có thể nhận nhiều order khác nhau. Sau khi đổi key sang customerId, những record cùng customerId có thể đang nằm rải rác trên nhiều partition đầu vào.

Nếu task lập tức aggregate theo customerId mà không chuyển dữ liệu, cùng một khách hàng có thể có nhiều bản trạng thái cục bộ ở các task khác nhau. Kết quả tổng hợp khi đó không đại diện cho toàn bộ sự kiện của khách hàng.

Repartition giải quyết vấn đề bằng cách:

1. Đọc record sau khi key đã được đổi.
2. Ghi record vào một internal repartition topic bằng key mới.
3. Kafka phân phối record vào partition theo key mới.
4. Kafka Streams đọc lại internal topic.
5. Các phép aggregate hoặc join phía sau xử lý record cùng key tại cùng task.

~~~mermaid
flowchart LR
    A["Topic orders<br/>key = orderId"] --> B["selectKey(customerId)"]
    B --> C["Internal repartition topic<br/>key = customerId"]
    C --> D["Partition theo customerId"]
    D --> E["groupByKey / aggregate"]
    E --> F["State store theo customerId"]
~~~

Repartition tạo một ranh giới ghi/đọc qua Kafka. Nó có chi phí serialization, network, disk I/O và độ trễ bổ sung, nhưng bảo đảm phân phối lại dữ liệu theo key hiện tại.

## 4. Tự động repartition sau selectKey, groupBy và join

Kafka Streams DSL theo dõi một số phép toán có thể thay đổi key. Khi stream được đánh dấu cần repartition, các phép toán tiếp theo yêu cầu dữ liệu cùng key nằm cùng partition có thể tạo internal repartition topic tự động.

Các trường hợp thường gặp:

- selectKey(...).groupByKey(...): group theo key mới và repartition nếu cần.
- selectKey(...).join(...): join theo key mới và repartition stream đã đổi key nếu topology có thể làm việc đó.
- groupBy(...): tạo key mới để grouping và luôn thực hiện repartition.
- map(...) hoặc flatMap(...) đổi key rồi mới aggregate/join: cần bảo đảm dữ liệu đã được phân phối theo key mới.

groupByKey() dùng key hiện tại và chỉ repartition nếu stream đã được đánh dấu cần repartition. Nếu key chưa đổi, đây thường là lựa chọn tiết kiệm hơn groupBy() vì không tạo repartition không cần thiết.

Ví dụ:

~~~java
KGroupedStream<String, Order> grouped = orders
    .selectKey((orderId, order) -> order.customerId())
    .groupByKey(
        Grouped.with(Serdes.String(), orderSerde)
    );
~~~

selectKey đánh dấu cần repartition. groupByKey tiếp theo sử dụng key mới và kích hoạt repartition để đưa các record cùng customerId về cùng partition trước khi aggregate.

Không phải mọi processor đều tự động nhận biết key đã bị thay đổi. Khi dùng Processor API hoặc custom processor có thể sửa key, hãy chủ động gọi repartition() trước stateful operation nếu topology không đánh dấu được thay đổi đó.

## 5. Gọi repartition tường minh

Có thể gọi KStream.repartition() khi muốn chủ động kiểm soát số partition, tên internal topic, Serde hoặc partitioner.

Ví dụ:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.Repartitioned;

KStream<String, Order> ordersByCustomer = orders
    .selectKey((orderId, order) -> order.customerId())
    .repartition(
        Repartitioned.<String, Order>with(
                Serdes.String(),
                orderSerde
            )
            .withName("orders-by-customer")
            .withNumberOfPartitions(12)
    );
~~~

Trong ví dụ:

- Serdes.String() tuần tự hóa key customerId.
- orderSerde tuần tự hóa payload Order.
- withName đặt tên ổn định, dễ nhận diện cho repartition processor và internal topic.
- withNumberOfPartitions(12) yêu cầu internal topic có mười hai partition.

Kafka Streams quản lý internal topic được tạo bởi repartition(). Tên thực tế thường có dạng application.id-orders-by-customer-repartition. Có thể dùng Topology.describe() để xem tên các node và internal topic được tạo trong topology.

Repartition tường minh luôn tạo ranh giới repartition, kể cả khi stream chưa được đánh dấu cần repartition. Không gọi nó nhiều lần liên tiếp nếu không có lý do về key hoặc số partition, vì mỗi lần đều có thể thêm một vòng ghi/đọc.

## 6. Aggregate theo key mới

Ví dụ một ứng dụng Spring Cloud Stream Kafka Streams Binder nhận sự kiện đơn hàng và tính tổng doanh thu theo khách hàng. Input topic đang có key orderId, nhưng state store cần key customerId.

Kiểu dữ liệu:

~~~java
import java.math.BigDecimal;

public record Order(
    String orderId,
    String customerId,
    BigDecimal amount
) {}

public record CustomerTotal(
    BigDecimal total
) {
    static CustomerTotal empty() {
        return new CustomerTotal(BigDecimal.ZERO);
    }

    CustomerTotal add(BigDecimal amount) {
        return new CustomerTotal(
            total.add(amount)
        );
    }
}
~~~

Function:

~~~java
import java.util.function.Function;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Bytes;
import org.apache.kafka.streams.kstream.Grouped;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Materialized;
import org.apache.kafka.streams.state.KeyValueStore;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.apache.kafka.common.serialization.Serde;

@Configuration
class CustomerTotalsConfiguration {

    @Bean
    Function<KStream<String, Order>, KStream<String, CustomerTotal>>
    customerTotals(
        Serde<Order> orderSerde,
        Serde<CustomerTotal> totalSerde
    ) {
        return orders -> orders
            .selectKey((orderId, order) -> order.customerId())
            .groupByKey(
                Grouped.with(Serdes.String(), orderSerde)
            )
            .aggregate(
                CustomerTotal::empty,
                (customerId, order, current) ->
                    current.add(order.amount()),
                Materialized
                    .<String, CustomerTotal,
                        KeyValueStore<Bytes, byte[]>>as("customer-totals")
                    .withKeySerde(Serdes.String())
                    .withValueSerde(totalSerde)
            )
            .toStream();
    }
}
~~~

selectKey đổi orderId thành customerId. groupByKey yêu cầu các record cùng customerId được gom về một partition; Kafka Streams tạo repartition nội bộ nếu cần. aggregate cập nhật state store theo customerId rồi phát changelog dưới dạng KTable; toStream() chuyển kết quả thành KStream để binder gửi ra output binding.

Trong ví dụ này, state store giữ tổng doanh thu hiện tại của mỗi khách hàng. Nếu cùng khách hàng có đơn hàng ở nhiều partition nguồn, repartition bảo đảm các cập nhật của khách hàng đó được xử lý cùng task.

## 7. Co-partitioning là gì?

Hai hoặc nhiều topic được gọi là co-partitioned khi chúng thỏa mãn các điều kiện phân phối cần thiết để phép join theo key hoạt động đúng:

1. Các topic đầu vào có cùng số partition.
2. Producer của các topic dùng cùng partitioning strategy.
3. Cùng một key logic được serialize nhất quán và đi đến cùng số partition trên mọi topic.

Ví dụ topic orders.by-customer và customers.by-id đều có 12 partition. Khi record key c-42 ở cả hai topic được phân phối bằng cùng key Serde và partitioner, cả hai record nằm ở partition có cùng chỉ số. Kafka Streams có thể giao chúng cho cùng task để join.

~~~mermaid
flowchart TD
    A["orders.by-customer<br/>12 partitions"] --> C["Task xử lý partition 4"]
    B["customers.by-id<br/>12 partitions"] --> C
    C --> D["Join theo customerId"]
    D --> E["OrderWithCustomer"]
~~~

Co-partitioning không có nghĩa hai topic phải có cùng dữ liệu hoặc cùng số lượng record. Điều kiện là cùng số partition và cùng quy tắc đưa một key vào partition tương ứng.

## 8. Vì sao join cần co-partitioning?

Kafka Streams thực hiện join theo key. Khi join hai stream, task xử lý một partition cần nhìn thấy các record của cả hai phía có cùng key. Nếu record c-42 ở topic A nằm partition 4 nhưng record c-42 ở topic B nằm partition 9, hai task độc lập sẽ không có đủ dữ liệu để join.

Các phép join cần chú ý:

| Phép join | Yêu cầu co-partition |
|---|---|
| KStream-KStream | Có; thường là join theo cửa sổ thời gian |
| KStream-KTable | Có; stream key phải khớp với key của table partition |
| KTable-KTable primary-key join | Có |
| KStream-GlobalKTable | Không cần co-partition; mỗi instance có bản sao GlobalKTable |
| KTable foreign-key join | Kafka Streams xử lý phân phối nội bộ; không áp dụng cùng yêu cầu co-partition như primary-key join |

Kafka Streams kiểm tra số partition của các nguồn join trong quá trình partition assignment. Nếu số partition không bằng nhau, ứng dụng có thể gặp exception tại bước này. Kafka Streams không thể tự xác minh mọi custom partitioner có phân phối cùng một key tới cùng partition hay không; phần đó thuộc trách nhiệm của ứng dụng.

## 9. Ví dụ join hai KStream theo customerId

Giả sử:

- Topic orders.raw có 6 partition và key là orderId.
- Topic customers.raw có 12 partition và key là customerId.
- Ứng dụng muốn join đơn hàng với thông tin khách hàng theo customerId.

Trước join, đổi key đơn hàng sang customerId và repartition cả hai phía về 12 partition. Nếu topic customers đã có key customerId nhưng số partition khác, vẫn cần repartition về cùng số partition trong topology.

Kiểu dữ liệu bổ sung:

~~~java
public record Customer(
    String customerId,
    String displayName
) {}

public record OrderWithCustomer(
    Order order,
    Customer customer
) {}
~~~

~~~java
import java.time.Duration;
import java.util.function.BiFunction;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.JoinWindows;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Repartitioned;
import org.apache.kafka.streams.kstream.StreamJoined;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderEnrichmentConfiguration {

    @Bean
    BiFunction<
        KStream<String, Order>,
        KStream<String, Customer>,
        KStream<String, OrderWithCustomer>
    > enrichOrders(
        Serde<Order> orderSerde,
        Serde<Customer> customerSerde
    ) {
        return (orders, customers) -> {
            KStream<String, Order> ordersByCustomer = orders
                .selectKey((orderId, order) -> order.customerId())
                .repartition(
                    Repartitioned.<String, Order>with(
                            Serdes.String(), orderSerde
                        )
                        .withName("orders-by-customer")
                        .withNumberOfPartitions(12)
                );

            KStream<String, Customer> customersById = customers
                .repartition(
                    Repartitioned.<String, Customer>with(
                            Serdes.String(), customerSerde
                        )
                        .withName("customers-by-id")
                        .withNumberOfPartitions(12)
                );

            return ordersByCustomer.join(
                customersById,
                (order, customer) ->
                    new OrderWithCustomer(order, customer),
                JoinWindows.ofTimeDifferenceWithNoGrace(
                    Duration.ofMinutes(10)
                ),
                StreamJoined.with(
                    Serdes.String(),
                    orderSerde,
                    customerSerde
                )
            );
        };
    }
}
~~~

Đây là ví dụ KStream-KStream windowed join: hai sự kiện cùng customerId phải đến trong cửa sổ 10 phút theo timestamp của record để tạo kết quả. Trong ứng dụng thực tế, hãy chọn cửa sổ và grace period phù hợp với độ trễ sự kiện; ví dụ dùng ofTimeDifferenceWithNoGrace để minh họa việc cấu hình cửa sổ mà không chờ thêm grace period.

Việc repartition cả hai phía về 12 partition tạo cùng số partition và dùng cùng key Serde String. Nếu topic đầu vào đã co-partitioned và không cần đổi key, có thể bỏ các bước repartition để giảm chi phí.

## 10. Dùng GlobalKTable khi phù hợp

GlobalKTable là lựa chọn cho bảng tham chiếu nhỏ hoặc vừa cần tra cứu từ mọi partition. Kafka Streams sao chép toàn bộ dữ liệu của GlobalKTable tới từng instance ứng dụng. Vì mỗi instance có bản sao đầy đủ, KStream có thể join với GlobalKTable mà không yêu cầu co-partitioning.

| KTable | GlobalKTable |
|---|---|
| Mỗi partition dữ liệu được xử lý ở task tương ứng | Mỗi instance có bản sao toàn bộ bảng |
| Join theo primary key cần co-partition | Không cần co-partition |
| Phù hợp bảng lớn được chia partition | Phù hợp dữ liệu tham chiếu nhỏ hơn |
| Ít dữ liệu phải sao chép đến mỗi instance | Tốn bộ nhớ, network và thời gian đồng bộ trên từng instance |

Không dùng GlobalKTable chỉ để né việc thiết kế partition. Nếu bảng tham chiếu lớn, việc sao chép toàn bộ đến mọi instance có thể làm tăng đáng kể chi phí vận hành.

## 11. Key Serde và partitioner phải nhất quán

Co-partitioning phụ thuộc vào byte key và partitioner, không chỉ tên trường trong Java object. Hai producer có thể cùng dùng customerId=c-42 nhưng serialize thành byte khác nhau hoặc dùng partitioner khác nhau; kết quả là chúng có thể ghi vào partition khác nhau.

Các điều kiện cần kiểm tra:

- Cùng kiểu key logic ở các topic tham gia join.
- Cùng Serde hoặc serializer tạo ra byte representation nhất quán.
- Cùng partitioner hoặc cùng StreamPartitioner.
- Cùng số partition.
- Không dùng một producer tùy chỉnh có cách phân phối key khác các producer còn lại.

Ví dụ nếu key là String, các input binding có thể dùng Serdes.String(). Nếu key là một kiểu Avro hoặc custom object, cần bảo đảm các producer và Kafka Streams binder dùng cùng schema/Serde và quy tắc serialize.

### 11.1. Cấu hình Serde theo binding trong Kafka Streams Binder

Spring Cloud Stream Kafka Streams Binder có thể suy luận Serde từ kiểu của function và các bean Serde. Khi kiểu phức tạp hoặc có nhiều input khác nhau, khai báo Serde rõ ràng cho từng binding giúp tránh giải mã sai.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.raw
        enrichOrders-in-1:
          destination: customers.raw
        enrichOrders-out-0:
          destination: orders.with-customer
    kafka:
      streams:
        bindings:
          enrichOrders-in-0:
            consumer:
              keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
              valueSerde: com.example.OrderSerde
          enrichOrders-in-1:
            consumer:
              keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
              valueSerde: com.example.CustomerSerde
          enrichOrders-out-0:
            producer:
              keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
              valueSerde: com.example.OrderWithCustomerSerde
~~~

Tên binding được tạo từ tên function enrichOrders: enrichOrders-in-0, enrichOrders-in-1 và enrichOrders-out-0. Hai input cần key Serde tương thích vì phép join sử dụng customerId. Value Serde có thể khác nhau vì hai topic mang hai kiểu dữ liệu khác nhau.

Nếu dùng bean Serde và binder có thể suy luận từ kiểu generic của function, không nhất thiết phải khai báo class name ở mọi binding. Khi cần kiểm soát rõ, dùng property theo binding như ví dụ. Kiểm tra cấu hình theo đúng phiên bản Kafka Streams Binder của dự án.

## 12. Phân biệt repartition của Kafka Streams với partitioning của Spring Cloud Stream

Spring Cloud Stream có cơ chế partitioning chung cho binder, thường dùng partitionKeyExpression và partitionCount trên output binding. Cơ chế đó hữu ích cho các middleware cần binder tự tính partition hoặc khi ứng dụng muốn dùng custom partition key.

Kafka Streams DSL có cơ chế riêng:

- selectKey đổi record key.
- groupByKey, groupBy hoặc join có thể kích hoạt repartition.
- repartition(Repartitioned) tạo internal topic và phân phối lại theo key/partitioner.
- Kafka Streams quản lý các internal repartition topic trong topology.

Không nhầm spring.cloud.stream.bindings.<binding>.producer.partitionKeyExpression với thao tác repartition bên trong topology Kafka Streams. Cấu hình partitioning của output binding quyết định nơi record đầu ra được ghi; KStream.repartition() tạo ranh giới phân phối lại trước các phép xử lý tiếp theo.

Nếu cần tùy chỉnh cách gửi dữ liệu từ output binding của Kafka Streams Binder, có thể cung cấp bean StreamPartitioner và tham chiếu bằng streamPartitionerBeanName ở producer binding. Đây là cấu hình partition của sink output; nó không thay thế việc repartition trước aggregate hoặc join.

## 13. Internal repartition topic và vận hành

Internal repartition topic do Kafka Streams tạo ra có tên gắn với application.id và tên processor/repartition. Topic được dùng để ghi record sau khi đổi key rồi đọc lại ở bước downstream.

Đặc điểm:

- Kafka Streams quản lý vòng đời internal topic.
- Số partition có thể được chỉ định bằng Repartitioned.withNumberOfPartitions.
- Key/value Serde của repartition topic phải phù hợp với kiểu dữ liệu sau khi đổi key.
- Internal topic làm tăng network, disk I/O và độ trễ.
- Internal topic cần replication factor và quyền broker phù hợp.

Có thể đặt replication factor cho internal topics qua cấu hình Kafka Streams:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              replication.factor: 3
~~~

Đây là cấu hình cấp binder và áp dụng cho các processor dùng binder đó. Nếu ứng dụng có nhiều function với cấu hình riêng, có thể dùng cấu hình theo function theo khả năng của phiên bản binder.

Principal chạy Kafka Streams cần quyền đọc topic đầu vào, ghi topic đầu ra, tạo/đọc/ghi internal repartition topic và quản lý state changelog topic theo cách cluster authorizer yêu cầu. Không chỉ cấp quyền cho các topic nghiệp vụ rồi bỏ qua internal topics.

## 14. Thay đổi số partition có thể làm thay đổi key placement

Khi số partition của topic thay đổi, cách ánh xạ key sang partition cũng có thể thay đổi. Ví dụ một key trước đây vào partition 2 trong topic sáu partition có thể vào partition khác sau khi topic tăng lên mười hai partition.

Điều này ảnh hưởng:

- Thứ tự tương đối của các sự kiện cùng key qua thời điểm thay đổi partition.
- Co-partitioning giữa các topic tham gia join.
- Phân phối state store và task của Kafka Streams.
- Kế hoạch khôi phục state/changelog khi topology hoặc partition count thay đổi.

Không tăng partition cho một phía của join mà quên phía còn lại. Nếu các topic cần co-partition, hãy lập kế hoạch thay đổi cùng nhau và xác minh lại partitioner. Với ứng dụng stateful đang chạy production, cần đánh giá chiến lược migrate hoặc rebuild state trước khi thay đổi partition count.

Kafka không hỗ trợ giảm partition count của một topic theo thao tác quản trị thông thường. Nếu cần thay đổi số partition theo hướng giảm, thường phải tạo topic mới, chuyển dữ liệu và chuyển ứng dụng sang topic mới theo kế hoạch migration.

## 15. Xử lý key null và dữ liệu không hợp lệ

Các phép toán group và join dựa trên key. Record có key null không thể được phân nhóm theo customerId hoặc match với record cùng key ở phía còn lại.

Trước khi repartition:

- Xác thực trường dùng làm key không null hoặc rỗng.
- Xác định cách xử lý record thiếu customerId: reject, DLQ, quarantine hoặc dùng một key nghiệp vụ hợp lệ khác.
- Không gán mọi record thiếu key vào một chuỗi chung như unknown nếu điều đó khiến tất cả dữ liệu lỗi dồn vào một partition.
- Kiểm tra giá trị key có phân phối đều hay không; một khách hàng chiếm phần lớn traffic có thể tạo hot partition.

Một key có quá nhiều record có thể làm một partition và một task quá tải. Repartition không tự giải quyết hot key nếu mọi record vẫn dùng cùng key. Khi nghiệp vụ cho phép, có thể chia khóa thành các shard phụ, rồi thực hiện bước tổng hợp cuối để ghép các shard.

## 16. Kiểm thử repartition và co-partitioning

Nên tách kiểm thử logic đổi key khỏi kiểm thử topology và broker.

### 16.1. Kiểm thử logic bằng TopologyTestDriver

TopologyTestDriver có thể kiểm tra:

1. selectKey tạo key customerId chính xác.
2. mapValues không thay đổi key.
3. Aggregate gom các record cùng customerId.
4. Join tạo kết quả khi hai phía có key tương ứng và timestamp phù hợp.
5. Record null key hoặc dữ liệu không hợp lệ được xử lý theo chính sách.

TopologyTestDriver kiểm tra logic topology trong bộ nhớ; nó không thay thế việc xác minh broker thực tế tạo đúng partition hoặc phân phối record qua internal topic.

### 16.2. Integration test với Kafka thật

Dùng Kafka Testcontainers hoặc cluster integration để kiểm tra:

- Topic đầu vào có đúng số partition.
- Các producer gửi cùng key vào cùng partition trên mọi topic join.
- Internal repartition topic được tạo với số partition mong muốn.
- Key Serde và value Serde có thể serialize/deserialize dữ liệu thật.
- Join không lỗi do số partition không tương thích.
- Record cùng key ở hai topic đến cùng task và tạo kết quả.
- Thay đổi partition count được phát hiện trong quy trình triển khai.

Có thể dùng lệnh:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic orders.raw

kafka-topics.sh --bootstrap-server localhost:9092 \
  --describe --topic customers.raw
~~~

So sánh số partition của hai topic và kiểm tra internal topic được tạo theo application.id. Để kiểm tra partition thực tế, gửi một số key mẫu vào cả hai topic và đọc metadata/partition của từng record.

## 17. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Aggregate cho cùng customerId tạo nhiều kết quả độc lập | Đổi key nhưng không repartition trước grouping/stateful operation | Dùng selectKey rồi groupByKey hoặc repartition |
| Join không tìm thấy record cùng key | Hai topic không co-partition hoặc dùng partitioner khác nhau | Kiểm tra partition count, key Serde và partitioner |
| Kafka Streams báo lỗi partition khi join | Số partition của hai nguồn khác nhau | Repartition một hoặc cả hai phía về cùng số partition |
| Internal topic không được tạo | Thiếu ACL, Serde sai hoặc broker không cho phép tạo topic | Kiểm tra broker log, ACL và Serde |
| Dữ liệu sau repartition không giải mã được | Key/value Serde của internal topic không tương thích | Khai báo Serde đúng kiểu sau khi đổi key |
| Một partition có lag lớn | Key skew hoặc hot key | Phân tích phân phối key, cân nhắc shard theo nghiệp vụ |
| Sau khi tăng partition, join sai | Các topic join được tăng partition không đồng bộ hoặc partitioner khác | Lập kế hoạch co-partition và migration cùng nhau |
| Processor API đổi key nhưng state vẫn sai | Không có auto-repartition sau custom processor | Gọi repartition tường minh |

## 18. Quy trình thiết kế đổi key và join

1. Xác định key hiện tại của từng input topic.
2. Xác định key nghiệp vụ cần dùng cho aggregate hoặc join.
3. Kiểm tra key mới có null, skew hoặc không ổn định không.
4. Dùng selectKey hoặc groupBy để tạo key mới.
5. Để DSL tự repartition tại điểm grouping/join khi có thể; dùng repartition tường minh nếu cần đặt số partition, Serde, tên hoặc partitioner.
6. Xác minh các topic join có cùng số partition.
7. Xác minh các producer dùng cùng cách serialize key và cùng partitioning strategy.
8. Cấu hình Serde cho input, output và internal repartition topic.
9. Kiểm tra quyền tạo/đọc/ghi internal topic và changelog topic.
10. Kiểm thử bằng TopologyTestDriver và Kafka thật.
11. Theo dõi partition lag, task distribution, state store và internal topic.
12. Lập kế hoạch migration nếu cần thay đổi partition count trong production.

## Tài liệu tham khảo chính thức

- [Apache Kafka Streams DSL](https://kafka.apache.org/44/streams/developer-guide/dsl-api/): selectKey, groupByKey, groupBy, tự động repartition và các phép join.
- [Apache Kafka Streams - KStream API](https://kafka.apache.org/40/javadoc/org/apache/kafka/streams/kstream/KStream.html): yêu cầu co-partition, hành vi join và repartition.
- [Apache Kafka - Repartitioned API](https://kafka.apache.org/43/javadoc/org/apache/kafka/streams/kstream/Repartitioned.html): cấu hình key/value Serde, tên và số partition cho internal repartition topic.
- [Spring Cloud Stream Kafka Streams Binder Reference](https://docs.spring.io/spring-cloud-stream-binder-kafka/docs/current/reference/html/kafka-streams.html): functional binding, Serde inference, stateful processing và Kafka Streams integration.
- [Spring Cloud Stream Kafka Streams Binder - Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html): cấu hình Serde theo input/output binding, application ID và StreamPartitioner.
