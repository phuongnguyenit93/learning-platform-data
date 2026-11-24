# Function, Consumer, BiFunction và hàm nhiều đầu vào

Kafka Streams binder của Spring Cloud Stream cho phép viết topology bằng các hàm Java quen thuộc thay vì tự tạo và quản lý listener cho từng topic. Kiểu chữ ký của bean cho binder biết topology cần bao nhiêu đầu vào, có đầu ra hay không, và mỗi binding cần được biểu diễn dưới dạng KStream, KTable hoặc GlobalKTable.

Ba kiểu thường gặp là Function, Consumer và BiFunction. Function nhận một đầu vào và trả kết quả; Consumer nhận đầu vào nhưng không tạo binding đầu ra; BiFunction nhận hai đầu vào và trả kết quả. Khi topology cần ba đầu vào trở lên, có thể dùng các Function lồng nhau theo kỹ thuật currying. Với hai đầu vào nhưng không có đầu ra, dùng BiConsumer.

Điều quan trọng là các hàm này làm việc với abstraction của Kafka Streams như KStream và KTable, không phải với từng Spring Message riêng lẻ. Binder tạo binding và kết nối topic; phần thân hàm mô tả cách kết hợp, lọc, biến đổi hoặc tiêu thụ dữ liệu.

## 1. Kafka Streams binder và mô hình hàm

Kafka Streams binder là binder chuyên dụng cho Kafka Streams DSL. Nó tạo và quản lý Kafka Streams runtime, gắn các topic đầu vào/đầu ra với topology, đồng thời ánh xạ chữ ký hàm sang binding.

Ứng dụng thường cần dependency của Kafka Streams binder:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-streams</artifactId>
</dependency>
~~~

Trong mô hình hàm:

- Bean có kiểu Consumer nhận dữ liệu để xử lý hoặc ghi nhận, không khai báo output binding.
- Bean có kiểu Function nhận dữ liệu và trả một KStream hoặc KTable làm output.
- Bean có kiểu BiFunction nhận hai input binding, thường dùng để kết hợp stream với table hoặc hai stream.
- Bean có kiểu Function lồng nhau có thể khai báo nhiều input binding theo thứ tự tham số.

Binder sử dụng tên bean làm cơ sở tạo tên binding. Ví dụ bean tên process có input binding process-in-0 và output binding process-out-0. Với hai đầu vào, các binding mặc định lần lượt là process-in-0 và process-in-1.

Mô hình này khác với consumer/function của Kafka message-channel binder thông thường. Kafka Streams binder truyền vào topology các đối tượng KStream, KTable hoặc GlobalKTable để ứng dụng xây dựng xử lý liên tục; nó không gọi hàm riêng cho từng Message như mô hình message channel.

## 2. KStream, KTable và GlobalKTable trong chữ ký hàm

Trước khi chọn kiểu hàm, cần chọn đúng abstraction cho từng đầu vào:

| Kiểu | Ý nghĩa | Vai trò thường gặp |
|---|---|---|
| KStream<K, V> | Chuỗi sự kiện key/value; mỗi record là một sự kiện độc lập | Sự kiện đơn hàng, click, thanh toán, thay đổi trạng thái |
| KTable<K, V> | Bảng trạng thái được cập nhật theo key từ changelog topic | Bảng khách hàng, cấu hình, trạng thái mới nhất theo ID |
| GlobalKTable<K, V> | Bản sao đầy đủ của bảng được phân phối đến mỗi instance Kafka Streams | Dữ liệu tra cứu dùng chung, bảng tham chiếu có kích thước phù hợp |

KStream phù hợp khi mọi sự kiện đều có ý nghĩa và cần được xử lý theo dòng thời gian. KTable biểu diễn trạng thái hiện tại theo key; record mới cập nhật giá trị của key, còn tombstone có thể xóa key khỏi bảng. GlobalKTable cũng biểu diễn bảng trạng thái, nhưng toàn bộ dữ liệu được sao chép đến mọi instance của ứng dụng.

KStream có thể dùng làm input hoặc output. KTable và GlobalKTable thường được bind làm input; khi cần xuất trạng thái, ứng dụng có thể chuyển KTable thành KStream bằng toStream hoặc dùng KTable làm kết quả của Function theo hỗ trợ của binder.

Chọn kiểu input ảnh hưởng đến ngữ nghĩa xử lý. Ví dụ, nếu topic khách hàng là changelog và chỉ cần thông tin mới nhất của từng khách hàng, KTable phù hợp hơn KStream. Nếu cần xử lý từng lần khách hàng thay đổi địa chỉ như một sự kiện lịch sử, KStream có thể phù hợp hơn.

## 3. Consumer: một đầu vào, không có đầu ra

Consumer phù hợp với topology chỉ cần tiêu thụ stream và thực hiện thao tác cuối như kiểm tra, ghi metric, gọi một API có kiểm soát hoặc ghi vào một hệ thống khác thông qua Processor API.

Ví dụ Consumer nhận sự kiện đơn hàng và ghi audit:

~~~java
import java.util.function.Consumer;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(
        String orderId,
        String status,
        long totalMinorUnits) {}

@Configuration
class OrderAuditTopology {

    @Bean
    Consumer<KStream<String, OrderEvent>> auditOrders() {
        return orders -> orders.foreach((key, event) -> {
            System.out.printf(
                    "orderKey=%s orderId=%s status=%s total=%d%n",
                    key,
                    event.orderId(),
                    event.status(),
                    event.totalMinorUnits());
        });
    }
}
~~~

Bean auditOrders có một tham số KStream nên binder tạo một input binding mặc định auditOrders-in-0. Vì kiểu hàm là Consumer, binder không tạo output binding.

Cấu hình topic đầu vào:

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrders
    stream:
      bindings:
        auditOrders-in-0:
          destination: orders.events
~~~

Consumer không có giá trị trả về. Nếu cần biến đổi record rồi ghi sang topic khác, hãy dùng Function. Nếu cần nhận hai input binding nhưng vẫn không có output binding, dùng BiConsumer.

Không nên thực hiện side effect không idempotent tùy tiện trong foreach. Kafka Streams có thể xử lý lại record khi khởi động lại hoặc phục hồi task. Nếu thao tác cuối gọi dịch vụ ngoài, cần khóa idempotency hoặc một cơ chế ghi bền vững phù hợp.

## 4. Function: một đầu vào, một hoặc nhiều đầu ra

Function phù hợp khi topology nhận một KStream và trả ra một KStream hoặc KTable. Binder tạo một input binding và một output binding.

Ví dụ lọc các sự kiện đơn hàng có tổng tiền hợp lệ:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ValidOrderTopology {

    @Bean
    Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
    validOrders() {
        return orders -> orders
                .filter((key, event) -> event.totalMinorUnits() > 0);
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: validOrders
    stream:
      bindings:
        validOrders-in-0:
          destination: orders.received
        validOrders-out-0:
          destination: orders.valid
~~~

Binder đọc record từ orders.received thành KStream, áp dụng topology và ghi các record còn lại đến orders.valid. Các record không thỏa điều kiện filter không được đưa ra output stream.

Function cũng có thể trả KTable. Khi output là KTable, binder dùng biểu diễn stream tương ứng để ghi kết quả ra topic. Nếu downstream function nhận output này trong một chuỗi composition, chữ ký input của downstream phải là KTable, không thể tự giả định mọi output đều là KStream.

### Function với nhiều output

Kafka Streams hỗ trợ branching. Function có thể trả một mảng KStream để binder tạo nhiều output binding:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>[]>
routeOrders() {
    return orders -> {
        KStream<String, OrderEvent>[] branches = orders.branch(
                (key, event) -> "PAID".equals(event.status()),
                (key, event) -> "CANCELLED".equals(event.status()));
        return branches;
    };
}
~~~

Với hai nhánh, binder tạo routeOrders-out-0 và routeOrders-out-1. Cấu hình hai destination tương ứng:

~~~yaml
spring:
  cloud:
    function:
      definition: routeOrders
    stream:
      bindings:
        routeOrders-in-0:
          destination: orders.events
        routeOrders-out-0:
          destination: orders.paid
        routeOrders-out-1:
          destination: orders.cancelled
~~~

Mỗi output binding nhận một nhánh theo đúng thứ tự trong mảng. API branch với hai predicate chỉ đưa record vào nhánh đầu tiên có predicate đúng; record không khớp nhánh nào sẽ không xuất hiện ở output. Hãy bảo đảm số destination được cấu hình khớp số phần tử KStream mà topology trả về.

## 5. BiFunction: hai đầu vào, có đầu ra

Khi một topology cần kết hợp dữ liệu từ hai topic, BiFunction là lựa chọn trực tiếp. Tham số thứ nhất ánh xạ đến input binding thứ nhất, tham số thứ hai ánh xạ đến input binding thứ hai.

Một trường hợp phổ biến là kết hợp stream sự kiện với table tham chiếu. Ví dụ, topic clicks chứa số lượt click theo user, còn topic user-regions là changelog cập nhật vùng của từng user. Mục tiêu là gắn vùng vào mỗi sự kiện click:

~~~java
import java.util.function.BiFunction;

import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.kstream.Joined;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.apache.kafka.streams.KeyValue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record RegionTotal(String region, long clicks) {}

@Configuration
class RegionClickTopology {

    @Bean
    BiFunction<KStream<String, Long>, KTable<String, String>,
            KStream<String, RegionTotal>> clicksByRegion() {

        return (clicks, regions) -> clicks
                .leftJoin(
                        regions,
                        (count, region) -> new RegionTotal(
                                region == null ? "UNKNOWN" : region,
                                count),
                        Joined.with(
                                Serdes.String(),
                                Serdes.Long(),
                                Serdes.String()))
                .map((userId, regionTotal) ->
                        KeyValue.pair(regionTotal.region(), regionTotal));
    }
}
~~~

BiFunction tạo hai input binding: clicksByRegion-in-0 cho KStream và clicksByRegion-in-1 cho KTable. Kết quả KStream tạo output binding clicksByRegion-out-0.

Khai báo destination:

~~~yaml
spring:
  cloud:
    function:
      definition: clicksByRegion
    stream:
      bindings:
        clicksByRegion-in-0:
          destination: user.clicks
        clicksByRegion-in-1:
          destination: user.regions
        clicksByRegion-out-0:
          destination: clicks.by-region
~~~

KStream-KTable join tra cứu giá trị hiện tại trong table theo key của stream. Với KStream và KTable được phân vùng, hai phía thường phải co-partitioned: cùng key phải được định tuyến tương ứng đến cùng partition để phép join hoạt động đúng. Cần thống nhất key, partition count và partitioning strategy của hai topic.

leftJoin giữ click kể cả khi chưa có vùng tương ứng; khi đó ví dụ gán vùng UNKNOWN. Dùng join thay leftJoin nếu chỉ muốn giữ record có khóa khớp ở cả hai phía.

## 6. Hai đầu vào không có đầu ra: BiConsumer

Nếu topology cần hai input binding nhưng chỉ thực hiện thao tác cuối, dùng BiConsumer:

~~~java
import java.util.function.BiConsumer;

import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RegionAuditTopology {

    @Bean
    BiConsumer<KStream<String, Long>, KTable<String, String>>
    auditClickAndRegionState() {
        return (clicks, regions) -> {
            clicks.foreach((userId, count) ->
                    System.out.printf("user=%s clicks=%d%n", userId, count));

            regions.toStream().foreach((userId, region) ->
                    System.out.printf("user=%s region=%s%n", userId, region));
        };
    }
}
~~~

Binder tạo auditClickAndRegionState-in-0 và auditClickAndRegionState-in-1, không tạo output binding. Đây là topology có hai đầu vào độc lập; hai đoạn foreach không tự tạo quan hệ join giữa stream và table.

Nếu cần ghép dữ liệu và xuất kết quả, dùng BiFunction. Nếu chỉ cần quan sát cả hai đầu vào, BiConsumer có chữ ký diễn đạt đúng ý định.

## 7. Hàm nhiều đầu vào bằng currying

Java có BiFunction cho hai tham số. Với ba đầu vào trở lên, Kafka Streams binder hỗ trợ hàm lồng nhau, còn gọi là curried function. Mỗi Function bên trong nhận thêm một đầu vào; Function cuối cùng trả topology kết quả.

Ví dụ cần kết hợp:

- KStream đơn hàng.
- GlobalKTable khách hàng.
- GlobalKTable sản phẩm.

Kết quả là stream đơn hàng đã bổ sung thông tin khách hàng và sản phẩm:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.GlobalKTable;
import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Order(Long customerId, Long productId, int quantity) {}

record Customer(String name) {}

record Product(String name, long priceMinorUnits) {}

record CustomerOrder(Order order, Customer customer) {}

record EnrichedOrder(
        String customerName,
        String productName,
        int quantity,
        long totalMinorUnits) {}

@Configuration
class EnrichOrderTopology {

    @Bean
    Function<KStream<Long, Order>,
            Function<GlobalKTable<Long, Customer>,
                    Function<GlobalKTable<Long, Product>,
                            KStream<Long, EnrichedOrder>>>> enrichOrders() {

        return orders -> customers -> products ->
                orders.join(
                        customers,
                        (orderId, order) -> order.customerId(),
                        (order, customer) ->
                                new CustomerOrder(order, customer))
                .join(
                        products,
                        (orderId, customerOrder) ->
                                customerOrder.order().productId(),
                        (customerOrder, product) ->
                                new EnrichedOrder(
                                        customerOrder.customer().name(),
                                        product.name(),
                                        customerOrder.order().quantity(),
                                        product.priceMinorUnits()
                                                * customerOrder.order().quantity()));
    }
}
~~~

Chữ ký hàm được đọc từ ngoài vào trong:

1. Function đầu nhận KStream<Long, Order> và trả về một Function khác.
2. Function thứ hai nhận GlobalKTable<Long, Customer> và trả về Function tiếp theo.
3. Function thứ ba nhận GlobalKTable<Long, Product> và trả KStream<Long, EnrichedOrder>.

Binder tạo ba input binding theo thứ tự tham số: enrichOrders-in-0, enrichOrders-in-1 và enrichOrders-in-2. Kết quả cuối cùng tạo enrichOrders-out-0.

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders
        enrichOrders-in-1:
          destination: customers
        enrichOrders-in-2:
          destination: products
        enrichOrders-out-0:
          destination: orders.enriched
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: order-enrichment-v1
~~~

Trong ví dụ, orders là luồng sự kiện; customers và products là bảng tra cứu được nhân bản thành GlobalKTable. Việc dùng GlobalKTable cho phép tra cứu theo khóa được chọn từ record đơn hàng mà không yêu cầu hai topic bảng phải có cùng partitioning với topic orders. Đổi lại, toàn bộ bảng được sao chép đến từng instance, vì vậy cần đánh giá kích thước dữ liệu và chi phí mạng/lưu trữ.

Nếu ứng dụng có nhiều Kafka Streams processor trong cùng một tiến trình, mỗi processor cần application ID phù hợp và riêng biệt. Với một processor, có thể cấu hình applicationId ở binder level hoặc dùng tên ứng dụng theo hướng dẫn của phiên bản. Không dùng chung application ID giữa các topology độc lập nếu chúng không có chủ đích cùng chia sẻ trạng thái và group.

## 8. Thêm nhiều đầu vào: khi nào nên dừng?

Currying cho phép biểu diễn nhiều đầu vào, nhưng số binding tăng làm topology khó hiểu hơn:

| Số đầu vào | Kiểu hàm thường dùng | Số output có thể có |
|---:|---|---:|
| 1 | Consumer | 0 |
| 2 | BiConsumer | 0 |
| 1 | Function | 1 hoặc nhiều |
| 2 | BiFunction | 1 hoặc nhiều |
| Từ 3 trở lên | Curried Function | 0 hoặc nhiều, tùy kiểu cuối |

Không nên đưa mọi topic vào cùng một hàm chỉ vì binder hỗ trợ. Khi có quá nhiều input, hãy xem xét tách topology theo trách nhiệm: một processor chuẩn hóa dữ liệu tham chiếu, processor khác làm enrichment, processor tiếp theo tính toán nghiệp vụ.

Việc tách giúp giảm coupling giữa schema, partitioning, tốc độ cập nhật và vòng đời triển khai của các nguồn dữ liệu. Nó cũng giúp kiểm thử từng bước và quan sát lag theo từng input binding dễ hơn.

## 9. Đặt tên binding và kích hoạt function

Tên binding mặc định được suy ra từ tên bean và vị trí tham số:

| Chữ ký bean | Input mặc định | Output mặc định |
|---|---|---|
| Consumer<KStream<...>> process | process-in-0 | Không có |
| Function<KStream<...>, KStream<...>> process | process-in-0 | process-out-0 |
| BiFunction<KStream<...>, KTable<...>, KStream<...>> process | process-in-0, process-in-1 | process-out-0 |
| Curried Function có ba input enrichOrders | enrichOrders-in-0, in-1, in-2 | enrichOrders-out-0 |
| Function trả KStream[] gồm hai nhánh | process-in-0 | process-out-0, process-out-1 |

Nếu ứng dụng có nhiều bean Function/Consumer, hãy kích hoạt rõ bean cần chạy:

~~~yaml
spring:
  cloud:
    function:
      definition: auditOrders;validOrders;enrichOrders
~~~

Các định nghĩa được phân tách bằng dấu chấm phẩy khi muốn khởi chạy nhiều processor độc lập trong cùng ứng dụng. Với function composition tuyến tính, dấu gạch đứng có thể kết hợp các function theo thứ tự, ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrders|validOrders
~~~

Composition chỉ phù hợp khi kiểu đầu ra của bước trước khớp kiểu đầu vào của bước sau. Function có thể kết hợp với Function hoặc kết thúc bằng Consumer. BiFunction phải đứng đầu chuỗi composition; các bước tiếp theo là Function hoặc Consumer. Không thể nối một BiFunction khác sau BiFunction, không thể bắt đầu chuỗi bằng Consumer, và không thể đặt output dạng KStream[] ở giữa chuỗi.

Nếu function đầu ra là KTable, function tiếp theo phải nhận KTable. Binder không tự chuyển KTable thành KStream chỉ vì tên bean sau đó nhận KStream; nếu cần chuyển kiểu, hãy dùng toStream rõ ràng.

## 10. Cấu hình Serde cho từng input binding

Kafka Streams cần biết cách chuyển key/value giữa byte và kiểu Java. Binder có thể suy luận Serde từ chữ ký hàm và các Serde bean có sẵn. Các kiểu phổ biến như String, Long, Integer, UUID và byte[] có Serde tương ứng; các kiểu dữ liệu nghiệp vụ thường cần JSON Serde hoặc Serde riêng.

Với nhiều input, không nên giả định tất cả binding dùng chung một Serde. Ví dụ orders có value kiểu Order, customers có value kiểu Customer và products có value kiểu Product. Mỗi binding có thể cần cấu hình riêng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            enrichOrders-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$LongSerde
            enrichOrders-in-2:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$LongSerde
~~~

Ví dụ chỉ định key Serde Long cho ba input. Value Serde có thể được suy luận từ kiểu generic hoặc cấu hình riêng bằng valueSerde khi cần. Với Avro/Protobuf hoặc schema registry, cấu hình serializer/deserializer chuyên biệt theo đúng hợp đồng của từng topic.

Kafka Streams binder mặc định sử dụng native deserialization cho input. Nếu muốn dùng message conversion của Spring Cloud Stream, phải tắt native decoding cho từng input binding tương ứng; không giả định chỉ cấu hình một input sẽ thay đổi các input còn lại.

Nếu Serde không khớp dữ liệu thực tế, lỗi có thể xảy ra trước khi logic Function chạy. Hãy kiểm tra key/value type trong chữ ký, Serde bean, cấu hình binding và schema của producer.

## 11. KStream-KTable join và yêu cầu phân vùng

Khi dùng BiFunction để kết hợp KStream với KTable, key của hai phía cần tương thích. Với join phân vùng, Kafka Streams yêu cầu hai nguồn được co-partitioned để các record có cùng key có thể được xử lý trên cùng task.

Kiểm tra:

- Hai topic có số partition tương thích.
- Cùng key được serialize theo cùng định dạng.
- Cùng partitioning strategy hoặc cùng quy tắc hash.
- Nếu cần đổi key, dùng selectKey hoặc map trước join và đánh giá repartition.
- Không tăng partition count một phía mà không đánh giá lại topology.

GlobalKTable có semantics khác: toàn bộ bảng được replicate đến mỗi instance. KStream có thể dùng key selector để tra cứu một key bất kỳ trong GlobalKTable, không cần co-partitioning như KTable. Nhưng bảng lớn có thể làm tăng chi phí bộ nhớ, mạng và thời gian khôi phục.

## 12. Kiểm thử chữ ký hàm và topology

Kiểm thử nên xác nhận cả cách binder tạo binding lẫn kết quả xử lý:

1. Consumer một input: gửi record và xác nhận thao tác cuối được thực hiện, không có output binding.
2. Function một input: gửi record hợp lệ/không hợp lệ và xác nhận output.
3. BiFunction: gửi stream record cùng dữ liệu bảng và xác nhận join đúng key.
4. Curried function: gửi dữ liệu đến đủ các input binding theo đúng thứ tự.
5. KTable: cập nhật cùng một key nhiều lần và xác nhận giá trị mới nhất được dùng.
6. GlobalKTable: tra cứu dữ liệu ở key không cùng partition với KStream và xác nhận kết quả.
7. Branching: xác nhận số output binding khớp số KStream trả về.
8. Serde: kiểm tra key/value của từng input binding, gồm dữ liệu lỗi schema.
9. Composition: xác nhận kiểu đầu ra của bước trước tương thích kiểu đầu vào bước sau.

Có thể dùng TopologyTestDriver để kiểm tra topology Kafka Streams mà không cần broker cho các phép biến đổi thuần. Tuy nhiên, cần thêm integration test với Kafka broker để xác nhận binder tạo đúng binding, application ID, Serde, partition assignment và state store khi triển khai thực tế.

## 13. Lỗi thường gặp khi dùng nhiều input

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ có một topic được consume | Chỉ khai báo một tham số hoặc dùng nhầm Function thay BiFunction | Kiểm tra chữ ký bean và số input binding |
| Không tìm thấy binding in-1 hoặc in-2 | Curried Function chưa khai báo đủ tầng Function | Kiểm tra kiểu lồng nhau và tên binding |
| Join không trả kết quả | Key khác nhau, KTable chưa có dữ liệu hoặc input không co-partitioned | Kiểm tra key, Serde, partition và thời điểm cập nhật |
| Dữ liệu GlobalKTable cập nhật chậm | Bảng phải được replicate đến các instance | Theo dõi restore/replication và cân nhắc KTable nếu phù hợp |
| Consumer nhận sai kiểu value | Serde inference không phù hợp hoặc cấu hình binding bị thiếu | Khai báo valueSerde đúng cho từng input |
| Có output binding nhưng không có record | Function lọc hết dữ liệu hoặc trả topology rỗng | Kiểm tra predicate, join và dữ liệu đầu vào |
| Số output binding không khớp | Mảng KStream có số nhánh khác cấu hình | Kiểm tra số nhánh thực tế và cách xử lý record không khớp predicate |
| Function composition không khởi động | Kiểu input/output không tương thích hoặc BiFunction đặt sai vị trí | Kiểm tra giới hạn composition và chữ ký generic |
| Processor dùng chung state ngoài ý muốn | application ID trùng giữa topology độc lập | Đặt application ID riêng cho từng processor |

## 14. Checklist thiết kế function

- Xác định topology có bao nhiêu input và bao nhiêu output.
- Chọn Consumer khi chỉ nhận một stream và không phát output.
- Chọn Function khi một input tạo một hoặc nhiều output.
- Chọn BiFunction cho hai input có output; BiConsumer cho hai input không output.
- Dùng curried Function cho từ ba input trở lên.
- Chọn KStream, KTable hoặc GlobalKTable theo semantics của topic.
- Đặt destination cho từng binding in-0, in-1, in-2 và out-0.
- Kích hoạt đúng bean bằng function definition khi ứng dụng có nhiều processor.
- Cấu hình Serde phù hợp với key/value của từng input.
- Đánh giá co-partitioning cho KStream-KTable join và chi phí replicate của GlobalKTable.
- Đặt application ID phù hợp, tránh dùng chung giữa các processor độc lập.
- Kiểm thử cả topology logic và binding thật với Kafka.

Kafka Streams binder suy ra cấu trúc topology từ kiểu hàm: Consumer cho một input không output, Function cho một input có output, BiFunction cho hai input có output và curried Function cho nhiều input hơn. Việc chọn KStream, KTable hay GlobalKTable quyết định ngữ nghĩa dữ liệu mà hàm nhận; tên tham số và thứ tự lồng nhau quyết định input binding tương ứng. Khi thiết kế đúng chữ ký, binding, Serde và partitioning, ứng dụng có thể kết hợp nhiều topic thành một topology rõ ràng mà vẫn giữ được khả năng kiểm thử và vận hành.

## Tài liệu tham khảo

- [Spring Cloud Stream — Kafka Streams Binder Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream — Kafka Streams Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/configuration-options.html)
- [Spring Cloud Stream — Kafka Streams Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/overview.html)
