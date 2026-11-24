# Hàm curried cho topology có nhiều hơn hai đầu vào

Kafka Streams binder của Spring Cloud Stream cho phép một hàm xử lý nhiều luồng Kafka đầu vào. Với hai đầu vào, có thể dùng **BiFunction**. Khi topology cần ba đầu vào trở lên, mô hình hàm curried biểu diễn mỗi đầu vào bằng một lớp **Function** lồng nhau: hàm nhận luồng thứ nhất và trả về hàm chờ luồng thứ hai; hàm tiếp theo lại chờ luồng kế tiếp cho tới khi nhận đủ đầu vào và tạo ra topology cuối cùng.

Currying giúp giữ một chữ ký hàm rõ ràng khi số lượng input binding lớn hơn hai. Kafka Streams binder ánh xạ từng tham số theo thứ tự vào các binding **functionName-in-0**, **-in-1**, **-in-2**... và ánh xạ kết quả cuối cùng tới output binding. Thứ tự khai báo trong chữ ký hàm vì vậy là một phần của hợp đồng cấu hình.

Bài học này giải thích cách viết hàm curried cho ba hoặc nhiều KStream, cách đặt tên binding, cấu hình Serde, cách kết hợp luồng bằng merge hoặc join, cùng các vấn đề về key, partition, state, kiểm thử và triển khai.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích currying và lý do dùng nó khi topology có hơn hai đầu vào.
- Phân biệt BiFunction cho hai đầu vào với Function lồng nhau cho ba đầu vào trở lên.
- Viết chữ ký hàm curried nhận ba KStream và trả về một KStream.
- Ánh xạ đúng thứ tự tham số với các input binding -in-0, -in-1, -in-2.
- Cấu hình destination và Serde cho từng input/output binding.
- Phân biệt merge các luồng với join các sự kiện theo key và thời gian.
- Hiểu tác động của partitioning, ordering, state store và application ID.
- Kiểm thử topology độc lập và kiểm thử wiring của binder.

## 1. Vì sao topology cần nhiều đầu vào?

Một ứng dụng xử lý sự kiện thường tổng hợp dữ liệu từ nhiều topic. Ví dụ, hệ thống thương mại điện tử có thể nhận:

- **orders**: sự kiện tạo hoặc cập nhật đơn hàng.
- **payments**: sự kiện thanh toán.
- **shipments**: sự kiện giao vận.

Một topology có thể hợp nhất ba luồng để xây dựng một dòng sự kiện thống nhất, hoặc kết hợp chúng để tạo trạng thái đơn hàng đầy đủ. Mỗi topic là một đầu vào riêng của function.

Kafka Streams binder ánh xạ input binding thành các KStream, KTable hoặc kiểu đầu vào Kafka Streams tương ứng. Khi có nhiều hơn hai đầu vào, chữ ký hàm cần thể hiện từng nguồn một cách tường minh.

### Hai đầu vào: BiFunction

Với đúng hai đầu vào, có thể dùng BiFunction:

~~~java
@Bean
BiFunction<
        KStream<String, String>,
        KStream<String, String>,
        KStream<String, String>> mergeTwoSources() {

    return (orders, payments) ->
        orders.merge(payments);
}
~~~

BiFunction<T1, T2, R> nhận hai tham số độc lập và trả về một kết quả. Kiểu này không mở rộng trực tiếp thành ba hoặc nhiều tham số.

### Ba đầu vào: Function lồng nhau

Currying biểu diễn hàm ba đầu vào thành một chuỗi hàm một tham số:

~~~java
Function<A, Function<B, Function<C, R>>>
~~~

Có thể đọc theo từng bước:

1. Hàm ngoài cùng nhận giá trị kiểu A.
2. Hàm trả về nhận tiếp giá trị kiểu B.
3. Hàm tiếp theo nhận giá trị kiểu C.
4. Khi đã có đủ ba đầu vào, hàm cuối cùng tạo kết quả kiểu R.

Với Kafka Streams, thay A, B, C bằng các kiểu KStream cụ thể.

~~~mermaid
flowchart LR
    A["Function nhận KStream 0"] --> B["Function nhận KStream 1"]
    B --> C["Function nhận KStream 2"]
    C --> D["Tạo topology và trả KStream đầu ra"]
~~~

Currying là cách biểu diễn nhiều tham số của cùng một function. Nó không phải là nối nhiều bean function bằng function composition như **functionA|functionB**.

## 2. Chữ ký curried cho ba KStream

Ví dụ ba topic có cùng kiểu key/value là String:

~~~java
Function<
    KStream<String, String>,
    Function<
        KStream<String, String>,
        Function<
            KStream<String, String>,
            KStream<String, String>
        >
    >
>
~~~

Đọc chữ ký từ trái sang phải:

- Input 0: KStream<String, String>.
- Input 1: KStream<String, String>.
- Input 2: KStream<String, String>.
- Output: KStream<String, String>.

Có thể khai báo trong Spring configuration:

~~~java
import java.util.function.Function;

import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MultiInputTopology {

    @Bean
    Function<
            KStream<String, String>,
            Function<
                    KStream<String, String>,
                    Function<
                            KStream<String, String>,
                            KStream<String, String>>>> combineEvents() {

        return orders -> payments -> shipments ->
            orders
                .mapValues(value -> "ORDER|" + value)
                .merge(payments.mapValues(value -> "PAYMENT|" + value))
                .merge(shipments.mapValues(value -> "SHIPMENT|" + value));
    }
}
~~~

Hàm nhận ba stream theo thứ tự, chuẩn hóa giá trị bằng tiền tố loại sự kiện rồi hợp nhất thành một output stream. Đây là ví dụ merge đơn giản; trong ứng dụng thực tế, nên dùng một schema chung như EventEnvelope thay vì nối chuỗi nếu cần xử lý dữ liệu có cấu trúc.

Các lambda lồng nhau được áp dụng khi binder xây dựng topology. Chúng không có nghĩa ứng dụng chờ một message từ topic thứ nhất rồi mới gọi hàm để lấy message từ topic thứ hai. Kafka Streams tạo topology từ các stream source, sau đó runtime xử lý record trên các nhánh đã khai báo.

## 3. Ánh xạ input binding theo thứ tự tham số

Giả sử bean function tên combineEvents. Kafka Streams binder tạo các binding theo tên function:

| Vị trí tham số trong hàm | Binding | Destination ví dụ |
|---:|---|---|
| Tham số thứ nhất | combineEvents-in-0 | orders |
| Tham số thứ hai | combineEvents-in-1 | payments |
| Tham số thứ ba | combineEvents-in-2 | shipments |
| Kết quả hàm | combineEvents-out-0 | unified-events |

Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: combineEvents
    stream:
      bindings:
        combineEvents-in-0:
          destination: orders
        combineEvents-in-1:
          destination: payments
        combineEvents-in-2:
          destination: shipments
        combineEvents-out-0:
          destination: unified-events
~~~

Tên binding phải khớp chính xác với tên function và chỉ số input/output. Nếu đổi thứ tự tham số trong chữ ký nhưng không đổi destination tương ứng, dữ liệu có thể đi vào nhánh sai mà ứng dụng vẫn khởi động thành công.

### Vì sao thứ tự là hợp đồng?

Giả sử chữ ký thay đổi từ:

~~~java
Function<A, Function<B, Function<C, R>>>
~~~

sang:

~~~java
Function<B, Function<A, Function<C, R>>>
~~~

Khi đó input 0 và input 1 đổi vị trí. Binder vẫn dùng các binding theo chỉ số; nó không suy luận topic nào có ý nghĩa nghiệp vụ nào. Vì vậy, thay đổi thứ tự input là thay đổi hợp đồng cấu hình và cần được review cùng YAML, test và deployment.

## 4. Cấu hình Serde cho từng binding

Kafka Streams dùng Serde (serializer/deserializer) để chuyển key/value giữa byte array trong Kafka và kiểu Java của topology. Với ví dụ KStream<String, String>, có thể cấu hình String Serde cho từng input và output.

~~~yaml
spring:
  cloud:
    function:
      definition: combineEvents
    stream:
      bindings:
        combineEvents-in-0:
          destination: orders
        combineEvents-in-1:
          destination: payments
        combineEvents-in-2:
          destination: shipments
        combineEvents-out-0:
          destination: unified-events
      kafka:
        streams:
          bindings:
            combineEvents-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-2:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Cấu hình Serde nằm ở namespace Kafka Streams binder, không phải chỉ ở binding chung. Mỗi input có thể cần Serde riêng nếu kiểu dữ liệu khác nhau. Output cần Serde tương ứng với kiểu key/value mà topology phát ra.

### Serde khác với contentType

contentType của Spring Cloud Stream hỗ trợ message conversion trong mô hình message-based. Kafka Streams binder làm việc trực tiếp với Kafka Streams types và Serde. Không nên giả định đặt contentType: application/json sẽ tự thay thế mọi cấu hình Serde trong topology.

Với record hoặc object nghiệp vụ, chọn một Serde JSON có cấu hình type rõ ràng, schema-based Serde hoặc Serde tùy chỉnh. Kiểm thử cả serialization và deserialization trên từng binding. Nếu các topic có schema khác nhau, đừng dùng chung một Serde chỉ vì chúng cùng chứa JSON.

## 5. Merge ba luồng thành một luồng

KStream.merge() hợp nhất hai stream cùng kiểu key/value thành một stream. Có thể nối nhiều lần để hợp nhất ba hoặc nhiều đầu vào.

~~~java
KStream<String, String> allEvents =
    orders
        .mapValues(value -> "ORDER|" + value)
        .merge(payments.mapValues(value -> "PAYMENT|" + value))
        .merge(shipments.mapValues(value -> "SHIPMENT|" + value));
~~~

Merge có các đặc điểm:

- Không ghép hai record thành một record duy nhất.
- Không đợi các record có cùng key hoặc cùng timestamp.
- Không tự sắp xếp toàn cục theo thời gian.
- Giữ từng record từ các nguồn trong cùng output stream.
- Có thể dùng chung key để downstream partitioning theo khóa nghiệp vụ.

Nếu cần phân biệt nguồn, thêm loại sự kiện vào payload hoặc header trước khi merge. Với dữ liệu có cấu trúc, dùng envelope có trường eventType, eventId, occurredAt và payload.

Ví dụ envelope:

~~~java
public record EventEnvelope(
    String eventId,
    String eventType,
    String aggregateId,
    Instant occurredAt,
    String payload
) {}
~~~

Các stream nguồn có thể chuyển thành cùng kiểu envelope trước khi merge. Khi đó output có schema thống nhất và consumer downstream không cần suy đoán topic nguồn.

## 6. Join nhiều đầu vào theo key

Merge phù hợp khi muốn giữ tất cả sự kiện. Nếu cần kết hợp dữ liệu liên quan thành một kết quả, dùng join. Join có ngữ nghĩa khác merge.

### Stream-stream join

Join giữa hai KStream thường cần:
- Key tương ứng giữa hai luồng.
- Window xác định khoảng thời gian cho phép ghép record.
- Serde cho key và giá trị trung gian.
- Partitioning tương thích giữa hai nguồn.

Ví dụ minh họa với hai stream:

~~~java
KStream<String, OrderEvent> orders = ...;
KStream<String, PaymentEvent> payments = ...;

KStream<String, OrderWithPayment> paidOrders =
    orders.join(
        payments,
        OrderWithPayment::new,
        JoinWindows.ofTimeDifferenceWithNoGrace(Duration.ofMinutes(5))
    );
~~~

Ví dụ dùng API stream-stream join có window. Chữ ký overload cụ thể có thể yêu cầu thêm StreamJoined để chỉ định Serde, tùy phiên bản Kafka Streams. Với topology production, cấu hình rõ Serde cho key, value và kết quả join.

Để kết hợp ba nguồn, có thể join hai nguồn trước rồi join kết quả trung gian với nguồn thứ ba. Chữ ký curried vẫn nhận từng input stream; phần thân hàm xây dựng các bước join.

~~~java
return orders -> payments -> shipments ->
    orders
        .join(
            payments,
            OrderWithPayment::new,
            JoinWindows.ofTimeDifferenceWithNoGrace(Duration.ofMinutes(5))
        )
        .join(
            shipments,
            OrderPaymentWithShipment::new,
            JoinWindows.ofTimeDifferenceWithNoGrace(Duration.ofMinutes(10))
        );
~~~

Đây là phác thảo topology để minh họa cách nối join. Kiểu đầu vào/kết quả, overload API, window và Serde cần được điều chỉnh theo model thực tế. Không phải mọi record có cùng key đều có thể join nếu chúng không nằm trong window phù hợp.

### KStream-KTable và KStream-GlobalKTable

Nếu một nguồn là dữ liệu trạng thái hiện tại, có thể biểu diễn bằng KTable. Ví dụ stream đơn hàng được enrich với bảng thông tin khách hàng. KStream-KTable join tra cứu giá trị bảng theo key; nó không có cùng semantics window như stream-stream join.

Với nhiều loại đầu vào, chữ ký curried có thể lồng các kiểu Kafka Streams tương ứng nếu binder hỗ trợ kiểu đó. Hãy giữ kiểu generic cụ thể cho từng tham số để tránh raw type hoặc cast không an toàn.

## 7. Heterogeneous inputs: mỗi nguồn có kiểu riêng

Currying không yêu cầu mọi đầu vào phải cùng kiểu. Chữ ký có thể thể hiện các stream khác nhau:

~~~java
Function<
    KStream<String, OrderEvent>,
    Function<
        KStream<String, PaymentEvent>,
        Function<
            KStream<String, ShipmentEvent>,
            KStream<String, EventEnvelope>
        >
    >
>
~~~

Trong ví dụ này, ba input có value type khác nhau và output dùng một envelope chung. Phần thân hàm cần chuyển từng loại sự kiện thành envelope trước khi merge, hoặc join theo khóa nghiệp vụ.

Cấu hình Serde phải tương ứng với từng binding:
- combineEvents-in-0: Serde của OrderEvent.
- combineEvents-in-1: Serde của PaymentEvent.
- combineEvents-in-2: Serde của ShipmentEvent.
- combineEvents-out-0: Serde của EventEnvelope.

Đừng khai báo KStream<String, Object> cho mọi đầu vào chỉ để né kiểu dữ liệu. Kiểu rõ ràng giúp phát hiện sai schema và giảm cast runtime. Nếu cần JSON Serde, khai báo type cụ thể hoặc cấu hình type mapping an toàn.

## 8. Partitioning và co-partitioning khi join

Kafka Streams xử lý song song theo task gắn với partition. Với stream-stream join, các record có cùng key cần được đưa tới cùng task để ghép đúng. Vì vậy, hai nguồn join cần co-partitioned: cùng số partition và cùng quy tắc phân vùng cho key tương ứng, hoặc topology phải thực hiện repartition phù hợp.

Các điều cần kiểm tra:
- Cùng kiểu key và cùng serialization.
- Cùng partitioner hoặc chiến lược key partition tương thích.
- Số partition tương ứng giữa các topic được join.
- Có repartition step phát sinh sau thao tác đổi key hay không.
- Throughput và chi phí network khi repartition.

Merge không yêu cầu co-partitioning như stream-stream join vì nó không ghép các record theo key. Tuy nhiên, output partitioning vẫn ảnh hưởng đến thứ tự và mức song song của các bước downstream.

Nếu topology thay đổi key bằng selectKey, các thao tác join tiếp theo có thể cần repartition để đảm bảo các record cùng key đi cùng task. Hãy xác minh topology description và internal repartition topics khi kiểm thử.

## 9. Thứ tự xử lý và ý nghĩa của nhiều nguồn

Kafka bảo đảm thứ tự trong một partition, không có thứ tự toàn cục giữa nhiều partition hoặc nhiều topic. Khi merge ba stream, các record được xử lý theo lịch poll/task của Kafka Streams; không thể giả định mọi sự kiện từ orders sẽ xuất hiện trước payments hoặc shipments.

Nếu nghiệp vụ cần thứ tự theo aggregate:
- Dùng cùng aggregate key để các sự kiện liên quan đi cùng partition khi phù hợp.
- Đưa sequence hoặc aggregate version vào payload.
- Kiểm tra version trước khi cập nhật trạng thái.
- Thiết kế join window theo độ trễ thực tế của nguồn.
- Xử lý sự kiện đến muộn (late arrival) và sự kiện thiếu.

Không dùng timestamp làm thứ tự tuyệt đối nếu các producer có clock khác nhau hoặc record được backfill. Cần xác định timestamp nào là nguồn sự thật và cách xử lý dữ liệu đến muộn.

## 10. Chọn application ID và quản lý state

Kafka Streams application ID định danh ứng dụng xử lý, consumer group nội bộ và các tài nguyên liên quan như state store/changelog. Các instance của cùng một ứng dụng cần dùng cùng application ID để phối hợp xử lý; môi trường hoặc ứng dụng độc lập cần ID khác nhau.

Ví dụ cấu hình binder:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        streams:
          binder:
            applicationId: event-consolidator
~~~

Khi topology chỉ merge các luồng mà không dùng stateful operator, ứng dụng có thể không tạo state store nghiệp vụ. Khi dùng join, aggregation, window hoặc materialized table, Kafka Streams có thể tạo state store và changelog topic để khôi phục trạng thái.

Một số lưu ý:
- Giữ application ID ổn định qua restart cùng một ứng dụng.
- Dùng application ID khác cho integration test hoặc môi trường độc lập.
- Không thay application ID chỉ để làm mới topology mà không đánh giá việc đọc lại dữ liệu.
- Khi reset input offsets, xem xét state store và changelog đồng thời.
- Không xóa internal topics thủ công khi chưa có quy trình phục hồi.

## 11. Cấu hình hoàn chỉnh cho topology ba đầu vào

Ví dụ kết hợp function, binding và Serde cho ba topic String:

~~~yaml
spring:
  cloud:
    function:
      definition: combineEvents
    stream:
      bindings:
        combineEvents-in-0:
          destination: orders
        combineEvents-in-1:
          destination: payments
        combineEvents-in-2:
          destination: shipments
        combineEvents-out-0:
          destination: unified-events
      kafka:
        streams:
          binder:
            applicationId: event-consolidator
          bindings:
            combineEvents-in-0:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-1:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-in-2:
              consumer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
            combineEvents-out-0:
              producer:
                keySerde: org.apache.kafka.common.serialization.Serdes$StringSerde
                valueSerde: org.apache.kafka.common.serialization.Serdes$StringSerde
~~~

Với function bean ở phần 2, cấu hình này tạo ba input bindings và một output binding. Trước khi chạy, cần bảo đảm:
- Ba input topic tồn tại và có dữ liệu dùng được với String Serde.
- Output topic có cấu hình partition phù hợp.
- Application ID không trùng ứng dụng độc lập khác.
- Broker credentials và ACL cho phép đọc input, ghi output và quản lý internal topics cần thiết.
- Các cấu hình Kafka Streams khác như replication factor cho internal topics được đặt theo môi trường production.

## 12. Kiểm thử topology curried

Nên kiểm thử hai lớp riêng: logic topology và wiring của Spring Cloud Stream binder.

### Unit test với TopologyTestDriver

TopologyTestDriver cho phép kiểm thử topology Kafka Streams mà không cần broker đang chạy. Tạo input topics tương ứng và kiểm tra output:

~~~java
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.kstream.Consumed;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Produced;

StreamsBuilder builder = new StreamsBuilder();

KStream<String, String> orders =
    builder.stream("orders", Consumed.with(Serdes.String(), Serdes.String()));
KStream<String, String> payments =
    builder.stream("payments", Consumed.with(Serdes.String(), Serdes.String()));
KStream<String, String> shipments =
    builder.stream("shipments", Consumed.with(Serdes.String(), Serdes.String()));

KStream<String, String> output =
    combineEvents.apply(orders).apply(payments).apply(shipments);

output.to("unified-events", Produced.with(Serdes.String(), Serdes.String()));

Topology topology = builder.build();
~~~

Trong test thực tế, tạo TopologyTestDriver với Properties có application.id và bootstrap.servers giả lập, sau đó tạo TestInputTopic cho từng nguồn và TestOutputTopic cho output. Gửi record từ cả ba input và xác minh:
- Output nhận đủ record.
- Prefix hoặc event type phản ánh đúng nguồn.
- Key được giữ nguyên như mong đợi.
- Không có record bị ghép nhầm do thay đổi thứ tự tham số.

Đoạn code trên giả định combineEvents là function bean đã được lấy ra từ Spring context hoặc tạo trực tiếp trong test. Khi dùng binder, test TopologyTestDriver không thay thế việc kiểm tra tên binding và cấu hình Serde thực tế.

### Integration test với Kafka

Dùng Kafka broker test hoặc Testcontainers để xác minh:
- Function definition được chọn đúng.
- Các binding -in-0, -in-1, -in-2 trỏ đúng topic.
- Output binding ghi đúng destination.
- Serde tương thích với payload thực tế.
- Application ID và consumer group hoạt động đúng.
- Rebalance và restart khôi phục topology/state theo mong đợi.

Test binder có thể hữu ích để kiểm tra wiring Spring Cloud Stream ở mức nhất định, nhưng không mô phỏng đầy đủ partition assignment, broker protocol, state restoration và Kafka Streams runtime. Các hành vi đó cần integration test với Kafka thật.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chỉ có hai input được bind | Chữ ký function chưa lồng đủ lớp Function | Thêm Function cho từng input còn lại |
| Input 1 và 2 bị đảo dữ liệu | Thứ tự tham số không khớp binding index | Đối chiếu chữ ký với -in-0, -in-1, -in-2 |
| Function không được phát hiện | Tên bean hoặc spring.cloud.function.definition sai | Khai báo tên function rõ ràng |
| Serialization/deserialization lỗi | Serde không khớp kiểu key/value | Cấu hình Serde riêng từng binding |
| Merge tạo dữ liệu không phân biệt nguồn | Không gắn event type/envelope | Chuẩn hóa thành EventEnvelope |
| Join không tìm thấy record tương ứng | Key hoặc window không khớp | Kiểm tra key, timestamp và join window |
| Join báo lỗi co-partitioning | Số partition hoặc partitioner không tương thích | Đồng bộ partitioning hoặc repartition |
| Output không có record | Chưa cấu hình output binding hoặc topology không phát record | Kiểm tra -out-0, destination và topology |
| Restart xử lý lại dữ liệu | Offset/state bị reset hoặc application ID đổi | Kiểm tra committed offsets, application ID và state |
| Test pass nhưng production lỗi | Unit test không kiểm tra binder/broker wiring | Thêm Kafka integration test |
| Đổi thứ tự function làm sai luồng | Binding index là hợp đồng theo vị trí | Version hóa thay đổi chữ ký và cập nhật cấu hình |

## 14. Bài thực hành: hợp nhất ba nguồn sự kiện

Xây dựng topology combineEvents đọc ba topic orders, payments, shipments:

1. Khai báo function bean có ba lớp Function lồng nhau.
2. Dùng ba KStream<String, String> để bắt đầu đơn giản.
3. Gắn tiền tố ORDER|, PAYMENT| và SHIPMENT| cho từng nguồn.
4. Dùng merge() để hợp nhất thành một output stream.
5. Cấu hình spring.cloud.function.definition=combineEvents.
6. Ánh xạ ba input theo combineEvents-in-0, -in-1, -in-2.
7. Ánh xạ output tới combineEvents-out-0.
8. Cấu hình String Serde cho cả ba input và output.
9. Chọn application ID ổn định cho ứng dụng.
10. Dùng TopologyTestDriver gửi record vào từng input và xác minh output.
11. Chạy integration test với Kafka để xác minh binder, destination và Serde.
12. Mở rộng bài tập bằng cách chuyển payload sang EventEnvelope.
13. Thử join order và payment theo key/window, sau đó đánh giá co-partitioning.
14. Quan sát topology description, partition assignment và state store nếu có.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Curried signature | Có đúng một lớp Function cho mỗi input |
| Input order | Thứ tự tham số khớp binding index |
| Binding names | Có đủ -in-0, -in-1, -in-2 |
| Output binding | Kết quả cuối được bind đúng destination |
| Serde | Key/value Serde đúng cho từng topic |
| Merge/join | Chọn đúng semantics theo nghiệp vụ |
| Partitioning | Join inputs co-partitioned khi cần |
| Ordering | Không giả định thứ tự toàn cục giữa các topic |
| Application ID | Ổn định và không xung đột |
| Testing | Có topology test và broker integration test |
| Recovery | Offset và state được kiểm tra khi restart/reset |

## Kết luận

Khi topology Kafka Streams có hơn hai đầu vào, hàm curried dùng các lớp Function lồng nhau để nhận từng KStream theo thứ tự rồi tạo topology cuối cùng. Với function tên combineEvents, binder ánh xạ các tham số tới combineEvents-in-0, -in-1, -in-2 và kết quả tới combineEvents-out-0.

Hãy giữ chữ ký generic rõ ràng, đồng bộ thứ tự binding, cấu hình Serde cho từng nguồn và chọn merge hay join theo yêu cầu nghiệp vụ. Merge giữ các record riêng lẻ và không tạo thứ tự toàn cục; join cần key, window và partitioning tương thích. Kiểm thử topology bằng TopologyTestDriver, sau đó kiểm tra binder và broker bằng integration test để xác nhận toàn bộ topology nhiều đầu vào hoạt động đúng.

## Tài liệu tham khảo

- [Spring Cloud Stream Kafka Streams Binder – Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
- [Spring Cloud Stream Kafka Streams Binder – Binding Capabilities](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/binding.html)
- [Apache Kafka Streams – Developer Guide](https://kafka.apache.org/documentation/streams/)
- [Apache Kafka Streams – KStream API](https://kafka.apache.org/40/javadoc/org/apache/kafka/streams/kstream/KStream.html)
- [Apache Kafka Streams – Testing](https://kafka.apache.org/documentation/streams/developer-guide/testing.html)

