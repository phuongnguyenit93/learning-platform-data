# Liên kết tham số hàm với đúng destination và applicationId

Trong Kafka Streams Binder của Spring Cloud Stream, một function bean mô tả topology xử lý dữ liệu; các tham số đầu vào và giá trị trả về của function được liên kết với các binding. Mỗi binding cần trỏ đến đúng Kafka topic thông qua `destination`. Đồng thời, Kafka Streams application cần một `applicationId` ổn định để Kafka quản lý consumer group, offset và các tài nguyên state nội bộ.

Ba khái niệm này có vai trò khác nhau: **tên function** xác định topology được chọn; **tên binding và destination** xác định dữ liệu đi vào/đi ra topic nào; **applicationId** xác định danh tính của một Kafka Streams application. Nếu liên kết sai một trong các phần này, ứng dụng có thể đọc nhầm topic, ghi nhầm output, không khôi phục đúng state hoặc chạy thành một consumer group độc lập ngoài ý muốn.

Bài thuộc chương **Kafka Streams** của module `SPRING_CLOUD_STREAM`. Nội dung tập trung vào mô hình hàm `Function`/`BiFunction`, cách tham số thứ nhất/thứ hai ánh xạ sang `-in-0`/`-in-1`, cách output ánh xạ sang `-out-0`, cấu hình `destination`, `applicationId`, Serde, nhiều topology, triển khai nhiều replica và thay đổi định danh an toàn.

## 1. Ba lớp định danh cần tách biệt

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| Function name | Topology/function bean nào được kích hoạt? | `enrichOrders` |
| Binding name | Đầu vào hoặc đầu ra nào của function đang được cấu hình? | `enrichOrders-in-0` |
| Destination | Binding đọc hoặc ghi Kafka topic nào? | `orders.created` |
| `applicationId` | Các instance nào thuộc cùng một Kafka Streams application logic? | `order-enrichment-v1` |

Function name không phải topic name. Binding name cũng không phải topic name. Destination là tên topic logic được cấu hình cho binding. `applicationId` không xác định topic đầu vào hay đầu ra; nó định danh ứng dụng Kafka Streams và được dùng cho consumer group cùng các tài nguyên nội bộ.

```text
Function bean: enrichOrders
       |
       +-- tham số 1 --> enrichOrders-in-0 --> destination: orders.created
       |
       +-- tham số 2 --> enrichOrders-in-1 --> destination: customers.current
       |
       +-- kết quả ----> enrichOrders-out-0 --> destination: orders.enriched

Kafka Streams applicationId: order-enrichment-v1
       |
       +-- consumer group của topology
       +-- offset và task coordination
       +-- tên/định danh tài nguyên state nội bộ
```

Tách biệt các lớp định danh giúp đọc cấu hình dễ dàng và tránh lỗi khi đổi tên bean hoặc đổi topic. Đổi function name có thể làm thay đổi binding name được sinh ra; đổi destination làm thay đổi topic mà binding kết nối; đổi application ID tạo ra một danh tính Kafka Streams application khác.

## 2. Cách Spring Cloud Stream sinh binding name

Với functional model, Spring Cloud Stream dùng tên function bean để tạo tên binding theo quy ước:

- Input đầu tiên: `<functionName>-in-0`.
- Input thứ hai: `<functionName>-in-1`.
- Các input tiếp theo: `-in-2`, `-in-3`, ...
- Output đầu tiên: `<functionName>-out-0`.
- Nếu function có nhiều output được hỗ trợ bởi kiểu trả về tương ứng, mỗi output có index riêng.

Ví dụ function một đầu vào, một đầu ra:

```java
@Bean
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
    filterOrders() {
    return orders -> orders
        .filter((key, event) -> event.total() > 0);
}
```

Các binding được tạo:

```text
filterOrders-in-0
filterOrders-out-0
```

Ví dụ function hai đầu vào:

```java
BiFunction<
    KStream<String, OrderEvent>,
    KTable<String, Customer>,
    KStream<String, EnrichedOrder>
> enrichOrders;
```

Đây là chữ ký rút gọn để nhìn thấy thứ tự hai tham số; ví dụ triển khai đầy đủ nằm ở phần tiếp theo.

Các binding đầu vào:

```text
enrichOrders-in-0  <- tham số thứ nhất: KStream<String, OrderEvent>
enrichOrders-in-1  <- tham số thứ hai: KTable<String, Customer>
enrichOrders-out-0 <- giá trị trả về: KStream<String, EnrichedOrder>
```

Thứ tự tham số là quan trọng. `in-0` gắn với tham số đầu tiên trong chữ ký hàm; `in-1` gắn với tham số thứ hai. Không suy ra thứ tự từ tên biến, tên topic hoặc tên kiểu dữ liệu.

## 3. `destination` liên kết binding với Kafka topic

`destination` được khai báo trong `spring.cloud.stream.bindings`. Với Kafka Streams Binder, input binding trỏ đến topic nguồn; output binding trỏ đến topic đích.

Ví dụ function một input và một output:

```yaml
spring:
  cloud:
    function:
      definition: filterOrders
    stream:
      bindings:
        filterOrders-in-0:
          destination: orders.created
        filterOrders-out-0:
          destination: orders.validated
```

Function `filterOrders` đọc topic `orders.created` và ghi kết quả sang `orders.validated`. Nếu không khai báo `destination` cho output, framework có thể dùng tên binding làm destination mặc định; vì vậy nên đặt tên topic tường minh để tránh ghi vào topic ngoài dự kiến.

Tên binding phải khớp chính xác với function name và index. Một lỗi gõ như `filterOrder-in-0` thay vì `filterOrders-in-0` có thể khiến cấu hình không áp dụng vào binding đang hoạt động.

## 4. Liên kết nhiều tham số với nhiều destination

Xét topology làm giàu đơn hàng bằng thông tin khách hàng. Function nhận một `KStream` chứa sự kiện đơn hàng và một `KTable` chứa trạng thái khách hàng mới nhất:

```java
import java.math.BigDecimal;
import java.util.function.BiFunction;

import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.KTable;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String customerId, BigDecimal total) {}

record Customer(String customerId, String displayName) {}

record EnrichedOrder(
    String orderId,
    String customerId,
    String customerName,
    BigDecimal total
) {}

@Configuration
class OrderTopologyConfiguration {

    @Bean
    BiFunction<
        KStream<String, OrderEvent>,
        KTable<String, Customer>,
        KStream<String, EnrichedOrder>
    > enrichOrders() {
        return (orders, customers) -> orders
            .selectKey((orderId, event) -> event.customerId())
            .join(customers, (event, customer) -> new EnrichedOrder(
                event.orderId(),
                event.customerId(),
                customer.displayName(),
                event.total()
            ));
    }
}
```

`selectKey` đổi key của stream sang `customerId` để khớp key của KTable. Kafka Streams có thể cần repartition stream trước phép join nếu key mới khác key hiện tại. Trong ví dụ này, join tạo ra `EnrichedOrder` chứa tên khách hàng tại thời điểm topology xử lý sự kiện.

Cấu hình binding:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
        enrichOrders-in-1:
          destination: customers.current
        enrichOrders-out-0:
          destination: orders.enriched
```

Ánh xạ:

| Binding | Tham số/giá trị hàm | Destination |
|---|---|---|
| `enrichOrders-in-0` | Tham số 1: `KStream<String, OrderEvent>` | `orders.created` |
| `enrichOrders-in-1` | Tham số 2: `KTable<String, Customer>` | `customers.current` |
| `enrichOrders-out-0` | Giá trị trả về: `KStream<String, EnrichedOrder>` | `orders.enriched` |

Nếu đảo thứ tự hai tham số trong Java, phải xem lại binding index và Serde tương ứng. Đừng chỉ đổi tên destination trong YAML mà không đối chiếu chữ ký function.

## 5. Dùng `spring.cloud.function.definition` để chọn đúng function

Ứng dụng có thể có nhiều function bean. `spring.cloud.function.definition` xác định function hoặc chuỗi function được kích hoạt bởi Spring Cloud Stream.

Ví dụ:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders
```

Nếu tên function không được chọn đúng, binder có thể không tạo các binding mà cấu hình đang nhắm đến. Khi ứng dụng có nhiều bean `Supplier`, `Function` hoặc `Consumer`, khai báo definition tường minh giúp tránh việc framework lựa chọn function ngoài dự kiến.

Tên trong `definition` phải khớp tên bean function, không phải destination hay application ID. Nếu dùng composition, cú pháp definition có thể kết hợp tên function theo cơ chế Spring Cloud Function; khi đó cần kiểm tra lại binding name được tạo cho function composition theo phiên bản framework.

## 6. Cấu hình `applicationId`

Kafka Streams cần `application.id` để định danh một ứng dụng xử lý luồng. Kafka Streams Binder cung cấp thuộc tính binder `applicationId`, thường được đặt dưới:

```text
spring.cloud.stream.kafka.streams.binder.applicationId
```

Ví dụ:

```yaml
spring:
  application:
    name: order-stream-service
  cloud:
    function:
      definition: enrichOrders
    stream:
      kafka:
        streams:
          binder:
            brokers: localhost:9092
            applicationId: order-enrichment-v1
```

Đặt `applicationId` tường minh giúp tên ứng dụng ổn định và không phụ thuộc vào tên artifact hoặc môi trường chạy. Nếu không khai báo, binder có thể dùng giá trị mặc định dựa trên cấu hình ứng dụng như `spring.application.name` hoặc cơ chế mặc định của phiên bản binder. Với production, nên khai báo rõ để tránh vô tình đổi danh tính khi đổi tên service.

`applicationId` là thuộc tính của Kafka Streams application, không phải `group` của Kafka Binder thông thường. Trong Kafka Streams, application ID được dùng làm consumer group ID và là một phần của danh tính stateful topology.

Ở tầng Kafka Streams client, tên cấu hình tương ứng là `application.id`. Kafka Streams Binder cung cấp `applicationId` ở namespace binder để đặt giá trị này. Tránh khai báo hai giá trị khác nhau giữa `binder.applicationId` và `binder.configuration.application.id`; hãy chọn một nguồn cấu hình rõ ràng theo phiên bản binder để không tạo ra danh tính ngoài dự kiến.

## 7. `applicationId` ảnh hưởng những gì?

Kafka Streams sử dụng application ID cho nhiều mục đích:

- Consumer group identity để các instance của cùng topology phối hợp chia task.
- Quản lý offset của các input topic.
- Tên các internal topic như changelog và repartition topic do topology tạo.
- Nhận diện state store và quá trình phục hồi state giữa các instance.
- Phân biệt metrics và client identity ở mức ứng dụng.

Vì vậy, application ID phải ổn định qua các lần restart của cùng topology. Nếu mỗi replica dùng một application ID khác nhau, chúng trở thành các Kafka Streams application độc lập; mỗi ứng dụng có thể đọc toàn bộ input topic và tạo output trùng.

Ngược lại, hai topology độc lập không nên dùng chung application ID nếu chúng cần offset, state store và vòng đời triển khai riêng. Dùng chung ID có thể khiến chúng tham gia cùng consumer group hoặc xung đột các tài nguyên nội bộ.

## 8. Tất cả replica của cùng topology phải dùng chung applicationId

Giả sử một topology `enrichOrders` chạy ba replica:

```text
Deployment: order-enrichment
applicationId: order-enrichment-v1

Replica A ------------------+
Replica B ------------------+---- cùng Kafka Streams application
Replica C ------------------+
```

Ba replica dùng cùng application ID. Kafka Streams phối hợp consumer group và phân phối task/partition giữa chúng. Khi một replica dừng, task có thể được chuyển cho replica còn lại; state cần thiết được khôi phục từ state store/changelog theo cơ chế Kafka Streams.

Không cấu hình application ID bằng pod name, hostname, UUID ngẫu nhiên hoặc chỉ số replica. Những giá trị này thay đổi theo lần triển khai và sẽ làm mỗi lần chạy trở thành một application khác, khiến offset/state không được dùng lại như mong muốn.

## 9. Nhiều topology độc lập cần applicationId riêng

Một ứng dụng Spring Boot có thể định nghĩa nhiều function Kafka Streams. Nếu chúng là các topology độc lập, mỗi topology cần danh tính ứng dụng riêng khi binder/phiên bản hỗ trợ cấu hình application ID theo function. Một số phiên bản Kafka Streams Binder cung cấp cấu hình theo function dưới dạng:

```text
spring.cloud.stream.kafka.streams.binder.functions.<functionName>.applicationId
```

Ví dụ minh họa cho hai function:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrders;calculateSales
    stream:
      kafka:
        streams:
          binder:
            functions:
              enrichOrders:
                applicationId: order-enrichment-v1
              calculateSales:
                applicationId: sales-aggregation-v1
```

Đây là cấu hình theo khả năng của phiên bản binder. Hãy xác nhận property metadata và tài liệu đúng release train trước khi dùng; nếu phiên bản không hỗ trợ application ID riêng theo function, triển khai topology độc lập trong các application/binder context được cấu hình riêng. Không gán một application ID duy nhất cho nhiều topology độc lập chỉ vì chúng nằm trong cùng một tiến trình.

Nếu các function thực sự là một chuỗi xử lý composition có chung lifecycle và topology logic, hãy xem xét chúng như một ứng dụng theo cách binder tạo topology và xác định application ID. Không áp dụng máy móc quy tắc “mỗi bean một ID” khi các function đã được compose thành một pipeline.

## 10. Cấu hình Serde phải khớp kiểu dữ liệu của tham số

Destination cho biết topic nào được đọc/ghi; Serde cho biết key/value bytes được chuyển thành kiểu Java nào. Hai cấu hình này phải nhất quán với chữ ký function.

Ví dụ function dùng:

```java
Function<KStream<String, OrderEvent>, KStream<String, OrderEvent>>
```

thì input key cần được deserialize thành `String`, value thành `OrderEvent`; output cũng cần serializer tương ứng.

Ví dụ cấu hình Serde mặc định cho key String:

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
```

Với payload phức tạp, cấu hình Serde riêng cho từng binding để `OrderEvent` và `Customer` được deserialize đúng kiểu. Ví dụ minh họa (các lớp Serde tự định nghĩa phải có trong classpath và có constructor/cấu hình mà binder yêu cầu):

```yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          bindings:
            enrichOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.OrderEventSerde
            enrichOrders-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.CustomerSerde
            enrichOrders-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.EnrichedOrderSerde
```

Tên Serde, constructor, trusted packages và schema compatibility phụ thuộc thư viện/phiên bản. Đừng giả định `content-type: application/json` tự động thay thế Serde của Kafka Streams; MessageConverter của Spring và Kafka Streams Serde là hai lớp khác nhau.

Nếu `enrichOrders-in-0` đọc `OrderEvent` nhưng topic chứa Avro bytes, cấu hình JsonSerde sẽ sai dù destination đúng. Tương tự, nếu tham số thứ hai là `KTable<String, Customer>` thì Serde của topic `customers.current` phải tương thích với `Customer`.

## 11. Đặt tên binding chính xác trong YAML

Một lỗi phổ biến là cấu hình destination dưới binding name không tồn tại. Đối chiếu chữ ký function với bảng sau trước khi chạy:

| Chữ ký | Binding đầu vào | Binding đầu ra |
|---|---|---|
| `Function<KStream<K,V>, KStream<K2,V2>> normalize` | `normalize-in-0` | `normalize-out-0` |
| `BiFunction<KStream<K,V>, KTable<K2,V2>, KStream<K3,V3>> enrich` | `enrich-in-0`, `enrich-in-1` | `enrich-out-0` |
| `BiFunction<KStream<K,V>, KStream<K2,V2>, KStream<K3,V3>> correlate` | `correlate-in-0`, `correlate-in-1` | `correlate-out-0` |
| `Consumer<KStream<K,V>> audit` | `audit-in-0` | Không có output binding |

Tên bean là gốc của binding name. Đổi `enrich` thành `enrichOrders` trong Java đòi hỏi cập nhật definition và các binding YAML tương ứng. Nếu chỉ đổi một phía, cấu hình có thể không được áp dụng vào function mong muốn.

## 12. Ví dụ cấu hình hoàn chỉnh cho một topology

```yaml
spring:
  application:
    name: order-enrichment
  cloud:
    function:
      definition: enrichOrders
    stream:
      bindings:
        enrichOrders-in-0:
          destination: orders.created
        enrichOrders-in-1:
          destination: customers.current
        enrichOrders-out-0:
          destination: orders.enriched
      kafka:
        streams:
          binder:
            brokers: kafka-1:9092,kafka-2:9092
            applicationId: order-enrichment-v1
            configuration:
              default.key.serde: org.apache.kafka.common.serialization.Serdes$StringSerde
          bindings:
            enrichOrders-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.OrderEventSerde
            enrichOrders-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.CustomerSerde
            enrichOrders-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: com.example.serde.EnrichedOrderSerde
```

Đọc cấu hình theo thứ tự:

1. `definition` chọn function bean `enrichOrders`.
2. Tham số thứ nhất là `KStream`, nên binding `enrichOrders-in-0` trỏ đến topic `orders.created`.
3. Tham số thứ hai là `KTable`, nên binding `enrichOrders-in-1` trỏ đến topic `customers.current`.
4. Function trả về `KStream`, nên `enrichOrders-out-0` ghi đến topic `orders.enriched`.
5. `applicationId` là `order-enrichment-v1` cho topology này.
6. Serde phải tương thích với key/value thực tế của từng topic; vì hai input có value type khác nhau, ví dụ dùng Serde riêng theo binding.

Không đặt `applicationId` vào `bindings.enrichOrders-in-0.destination`. Hai thuộc tính này thuộc hai nhánh cấu hình khác nhau và không thể thay thế cho nhau.

## 13. Phân biệt applicationId với consumer group của Kafka Binder thường

Spring Cloud Stream có Kafka Binder thông thường và Kafka Streams Binder. Cả hai dùng Kafka, nhưng danh tính consumer được cấu hình khác nhau:

| Mô hình | Cấu hình danh tính | Ý nghĩa |
|---|---|---|
| Kafka Binder thông thường | `spring.cloud.stream.bindings.<binding>.group` | Consumer group của input binding |
| Kafka Streams Binder | `spring.cloud.stream.kafka.streams.binder.applicationId` | Danh tính Kafka Streams application/topology |

Với Kafka Streams Binder, không dùng `group` của binding thông thường để thay cho application ID. Kafka Streams cần application ID để quản lý task, offset và state. Nếu chỉ đặt `group` nhưng application ID không đúng, topology vẫn có thể dùng application identity mặc định hoặc cấu hình khác với dự kiến.

## 14. Thay đổi destination có ảnh hưởng gì?

Đổi destination nghĩa là binding bắt đầu đọc từ topic khác hoặc ghi sang topic khác. Ví dụ:

```text
Trước: enrichOrders-in-0 -> orders.created.v1
Sau:   enrichOrders-in-0 -> orders.created.v2
```

Đây là thay đổi nguồn dữ liệu. Kafka Streams có thể bắt đầu đọc topic mới theo offset policy tương ứng; state store hiện có và changelog còn phụ thuộc application ID/topology. Đổi destination không tự động chuyển dữ liệu hoặc state từ topic cũ sang topic mới.

Trước khi thay đổi, xác định:

- Topic mới có tồn tại và có partition phù hợp không.
- Key/value schema và Serde có tương thích không.
- Consumer group/application ID sẽ đọc offset mới từ đâu.
- Có cần backfill dữ liệu hoặc rebuild state store không.
- Output topic có tiếp tục tương thích với downstream consumer không.
- Có cần chạy song song phiên bản cũ và mới trong thời gian migration không.

Nếu chỉ đổi tên topic nhưng vẫn dùng application ID cũ, Kafka Streams có thể tiếp tục sử dụng state/changelog của application hiện tại trong khi input topic thay đổi. Hãy xác định liệu state cũ còn hợp lệ với nguồn dữ liệu mới hay cần tạo application ID mới để rebuild có chủ đích.

## 15. Thay đổi applicationId có ảnh hưởng gì?

Đổi application ID tạo ra một Kafka Streams application identity mới. Ứng dụng mới có consumer group mới, offset riêng và các internal topic/state namespace mới. Khi không có offset đã commit cho group mới, hành vi bắt đầu đọc phụ thuộc `auto.offset.reset` hoặc cấu hình offset tương ứng.

Ví dụ:

```text
applicationId cũ: order-enrichment-v1
applicationId mới: order-enrichment-v2
```

Điều này có thể khiến ứng dụng v2 đọc lại từ `earliest` hoặc bắt đầu từ `latest` theo cấu hình, thay vì tiếp tục offset của v1. State store của v1 không tự được chuyển sang v2. Nếu v2 cần state đầy đủ, cần replay input hoặc thực hiện migration state có kế hoạch.

Không đổi application ID mỗi lần deploy. Chỉ đổi khi chủ đích tạo application identity mới, ví dụ rebuild projection, chạy song song một topology mới hoặc tách một ứng dụng logic. Trước khi bỏ v1, xác minh output, state, offset và tài nguyên internal topic cũ theo chính sách retention/cleanup.

## 16. Internal topics và quyền Kafka

Kafka Streams có thể tạo changelog topic và repartition topic cho stateful operations. Các topic nội bộ thường dựa trên application ID và tên store/operator. Vì vậy application ID ổn định giúp state restore hoạt động qua restart.

Principal Kafka của ứng dụng cần quyền phù hợp với:

- Read các input topic.
- Write các output topic.
- Read/write các internal topic do Kafka Streams sử dụng.
- Tham gia consumer group tương ứng.
- Tạo topic nội bộ nếu cluster cho phép ứng dụng tự tạo.

Trong production, topic nội bộ có thể được provision hoặc quản lý bằng ACL/quy trình hạ tầng. Không chỉ cấp quyền cho các topic nghiệp vụ rồi bỏ qua changelog/repartition topics. Ứng dụng có thể đọc được input nhưng lỗi khi khởi tạo state store hoặc thực hiện join do thiếu quyền với internal topic.

## 17. Partition count, task và applicationId

`applicationId` không phải số partition và không điều khiển trực tiếp số task. Kafka Streams tạo task dựa trên partition của input topic và topology. Các instance cùng application ID phối hợp chia task.

| Thành phần | Vai trò |
|---|---|
| `destination` | Chọn topic nguồn/đích |
| Partition count | Xác định số phân vùng của topic |
| Key | Xác định record thuộc partition nào theo partitioner |
| `applicationId` | Xác định nhóm ứng dụng Kafka Streams |
| Stream thread | Số luồng xử lý trong một instance |
| Task | Đơn vị xử lý gắn với partition của topology |

Nếu topic có sáu partition và ứng dụng chạy ba replica cùng application ID, Kafka Streams có thể phân phối các task giữa ba replica. Nếu mỗi replica dùng application ID khác nhau, mỗi replica trở thành một ứng dụng độc lập và có thể xử lý toàn bộ sáu partition.

## 18. Destination và applicationId theo môi trường

Môi trường dev, staging và production thường cần topic và application ID tách biệt để tránh đọc/ghi chéo dữ liệu:

```yaml
spring:
  cloud:
    stream:
      bindings:
        enrichOrders-in-0:
          destination: ${ORDERS_INPUT_TOPIC:orders.created}
        enrichOrders-in-1:
          destination: ${CUSTOMERS_INPUT_TOPIC:customers.current}
        enrichOrders-out-0:
          destination: ${ORDERS_OUTPUT_TOPIC:orders.enriched}
      kafka:
        streams:
          binder:
            applicationId: ${KAFKA_STREAMS_APPLICATION_ID:order-enrichment-dev}
```

Ví dụ giá trị môi trường:

| Môi trường | Input topic | Output topic | Application ID |
|---|---|---|---|
| Local | `dev.orders.created` | `dev.orders.enriched` | `order-enrichment-local` |
| Staging | `staging.orders.created` | `staging.orders.enriched` | `order-enrichment-staging` |
| Production | `orders.created` | `orders.enriched` | `order-enrichment-prod` |

Tách application ID giữa các môi trường giúp offset và state của chúng độc lập. Tên topic cũng cần trỏ đúng cluster/môi trường; chỉ đổi application ID nhưng vẫn đọc topic production từ môi trường dev có thể gây tác động không mong muốn.

## 19. Các lỗi liên kết thường gặp

| Lỗi | Triệu chứng có thể gặp | Cách kiểm tra |
|---|---|---|
| Sai function definition | Function không được kích hoạt như mong muốn | Kiểm tra tên bean và `spring.cloud.function.definition` |
| Sai binding name | Destination không áp dụng vào input/output thực tế | Đối chiếu `<functionName>-in-N`/`-out-N` |
| Đảo thứ tự tham số | Input topic gắn nhầm kiểu `KStream`/`KTable` | Đối chiếu chữ ký function với index |
| Sai destination | Topology đọc/ghi topic khác dự kiến | Kiểm tra binding properties và broker topic |
| Thiếu output destination | Output binding không được nối đến topic mong muốn | Khai báo `<functionName>-out-0` |
| Application ID thay đổi theo pod | Mỗi replica thành application độc lập, xử lý trùng | Dùng application ID chung và ổn định |
| Dùng chung application ID cho topology độc lập | Offset/state/internal topics bị dùng chung ngoài ý muốn | Cấp application ID riêng cho mỗi topology logic |
| Dùng `group` thay application ID | Kafka Streams identity không theo dự kiến | Cấu hình Kafka Streams binder `applicationId` |
| Serde không khớp payload | Lỗi deserialize/serialize khi runtime xử lý | Kiểm tra key/value Serde của từng input/output |
| Đổi destination nhưng giữ state cũ không phù hợp | Kết quả join/aggregate sai hoặc thiếu dữ liệu | Đánh giá state restore, replay và migration |
| Đổi application ID không có offset plan | Ứng dụng đọc lại hoặc bỏ qua dữ liệu ngoài ý muốn | Kiểm tra `auto.offset.reset` và kế hoạch backfill |

## 20. Kiểm thử liên kết function, destination và applicationId

Nên xác minh cấu hình từ cả phía Spring context và Kafka broker:

| Kịch bản | Cách kiểm thử | Kết quả cần xác minh |
|---|---|---|
| Một input, một output | Gửi record vào input topic | Function nhận từ đúng `-in-0` và output đến đúng `-out-0` destination |
| Hai input | Gửi dữ liệu vào hai topic | Tham số 1 nhận từ `-in-0`, tham số 2 từ `-in-1` |
| Sai binding name | Cố ý đổi một suffix | Kiểm tra startup/configuration phát hiện binding không khớp |
| Sai destination | Trỏ input sang topic khác | Xác nhận topology đọc đúng topic được cấu hình |
| Replica cùng app ID | Chạy hai instance với cùng application ID | Hai instance chia task/partition của cùng application |
| Replica khác app ID | Chạy hai instance với ID khác nhau | Chúng hoạt động như hai application độc lập; phát hiện output trùng nếu cùng ghi |
| Restart cùng app ID | Dừng rồi chạy lại instance | Offset và state được phục hồi theo Kafka Streams |
| Đổi app ID | Chạy phiên bản với ID mới | Xác nhận group/offset/internal topics mới và offset reset behavior |
| Sai Serde | Cấu hình Serde không khớp payload | Lỗi serialization/deserialization được phát hiện |
| Internal topic ACL | Thu hồi quyền changelog/repartition | Xác minh lỗi khởi tạo hoặc xử lý state và quyền cần thiết |
| Nhiều topology | Mỗi function có application ID riêng nếu hỗ trợ | Offset và state của các topology độc lập |

`TopologyTestDriver` phù hợp để kiểm tra logic topology và mapping dữ liệu trong phạm vi test. Integration test với Kafka thật hoặc broker tương thích cần thiết để xác minh application ID, consumer group, offset, internal topic, partition assignment và state restoration.

## 21. Quy trình cấu hình an toàn

Khi liên kết một Kafka Streams function:

1. Chọn tên function bean ổn định và khai báo trong `spring.cloud.function.definition`.
2. Đọc chữ ký function để xác định số lượng và thứ tự input parameters.
3. Tạo binding name theo quy ước `<functionName>-in-0`, `-in-1`, ... và `<functionName>-out-0`.
4. Gán `destination` cho từng binding theo đúng topic nguồn/đích.
5. Chọn `applicationId` ổn định cho topology logic.
6. Dùng cùng application ID cho tất cả replica của cùng topology.
7. Dùng application ID riêng cho topology độc lập; kiểm tra hỗ trợ per-function ID của phiên bản binder.
8. Cấu hình Serde tương thích với key/value của từng topic và kiểu tham số.
9. Cấp ACL cho input, output, consumer group và internal topics.
10. Kiểm thử mapping input/output, partition assignment, restart và state restoration.
11. Lập kế hoạch riêng trước khi đổi destination hoặc application ID.
12. Theo dõi consumer lag, task assignment, restore time và lỗi serialization trong production.

## 22. Tự kiểm tra

- [ ] Phân biệt function name, binding name, destination và application ID.
- [ ] Tính đúng tên binding `-in-0`, `-in-1` và `-out-0` từ chữ ký hàm.
- [ ] Giải thích được tham số đầu tiên và thứ hai map vào input binding nào.
- [ ] Cấu hình được destination riêng cho từng input và output.
- [ ] Biết `spring.cloud.function.definition` chọn function bean.
- [ ] Giải thích được vai trò của Kafka Streams `applicationId`.
- [ ] Biết mọi replica của cùng topology phải dùng chung application ID.
- [ ] Biết topology độc lập cần application ID riêng khi được triển khai như ứng dụng riêng.
- [ ] Phân biệt application ID với `group` của Kafka Binder thông thường.
- [ ] Cấu hình Serde phù hợp với kiểu key/value của từng tham số.
- [ ] Hiểu tác động của việc đổi destination và application ID đến offset/state.
- [ ] Thiết kế được kiểm thử mapping, restart, internal topics và nhiều replica.

## Kết luận

Trong Kafka Streams Binder, chữ ký function quyết định các binding input/output: tham số thứ nhất gắn với `-in-0`, tham số thứ hai gắn với `-in-1`, còn giá trị trả về gắn với `-out-0`. Mỗi binding dùng `destination` để xác định topic tương ứng. `applicationId` định danh Kafka Streams application, consumer group, offset và state nội bộ; mọi replica của cùng topology phải dùng chung ID ổn định, còn topology độc lập cần danh tính riêng. Đối chiếu function signature, binding name, destination, Serde và application ID trước khi triển khai giúp tránh đọc nhầm topic, xử lý trùng, mất khả năng phục hồi state hoặc tạo internal topic ngoài dự kiến.
