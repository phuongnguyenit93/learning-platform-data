# Chuyển tên input, output cũ sang tên binding theo hàm

Khi nâng cấp ứng dụng Spring Cloud Stream từ mô hình annotation cũ sang mô hình hàm (`Supplier`, `Function`, `Consumer`), một thay đổi rất dễ bị bỏ sót là **tên binding**. Trước đây, các interface như `Source`, `Sink` và `Processor` thường có tên binding là `output` hoặc `input`. Với mô hình hàm, tên mặc định được tạo từ **tên bean hàm**, hướng dữ liệu và chỉ số cổng.

Đổi tên binding logic **không có nghĩa phải đổi tên Kafka topic, RabbitMQ exchange/queue hoặc Pulsar topic**. Nếu chỉ sửa Java code mà bỏ quên các khóa cấu hình, ứng dụng có thể tự kết nối đến một destination không mong muốn hoặc không áp dụng consumer group, retry, DLQ, partition và binder đã dùng trước đó. Bài này hướng dẫn cách chuyển đổi có kiểm soát, bảo toàn đường đi của message và kiểm thử trước khi triển khai.

## 1. Phân biệt ba loại tên

| Loại tên | Ví dụ | Ý nghĩa |
|---|---|---|
| **Tên bean hàm** | `uppercase` | Bean `Function`, `Consumer` hoặc `Supplier` do Spring quản lý |
| **Tên binding** | `uppercase-in-0`, `uppercase-out-0` | Khóa logic mà Spring Cloud Stream dùng để chọn destination, group, binder và các thuộc tính |
| **Tên destination** | `orders.raw`, `orders.normalized` | Địa chỉ trên broker: topic, exchange, queue hoặc destination tương ứng |

Một function tên `uppercase` có thể có binding `uppercase-in-0` trỏ đến topic `orders.raw`, và binding `uppercase-out-0` trỏ đến topic `orders.normalized`. Không có yêu cầu tên binding phải giống tên broker destination.

Khi cấu hình:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
        uppercase-out-0:
          destination: orders.normalized
~~~

`uppercase-in-0` và `uppercase-out-0` là khóa binding; `orders.raw` và `orders.normalized` là destination. Giữ phân biệt này xuyên suốt quá trình migration.

## 2. Quy tắc đặt tên binding theo hàm

Spring Cloud Stream dùng quy tắc mặc định:

~~~text
Input  = <functionBeanName>-in-<index>
Output = <functionBeanName>-out-<index>
~~~

Chỉ số `0` ứng với input/output đầu tiên. Với hàm thông thường có một input và một output, chỉ số là 0 ở cả hai đầu.

| Kiểu bean hàm | Ví dụ bean | Input binding | Output binding |
|---|---|---|---|
| `Supplier<T>` | `publishOrder` | Không có | `publishOrder-out-0` |
| `Function<T,R>` | `normalizeOrder` | `normalizeOrder-in-0` | `normalizeOrder-out-0` |
| `Consumer<T>` | `storeOrder` | `storeOrder-in-0` | Không có |
| `BiFunction<...>` với Kafka Streams | `joinOrders` | `joinOrders-in-0`, `joinOrders-in-1` | `joinOrders-out-0` |

Tên dùng để tạo binding là **tên bean được đăng ký**. Nếu phương thức Java là `transformOrder` nhưng khai báo `@Bean("normalizeOrder")`, binding sẽ dựa trên `normalizeOrder`. Không lấy tên class, topic hoặc tên method tùy ý để đoán.

## 3. Mô hình annotation cũ sử dụng input/output như thế nào?

Trong ứng dụng cũ, `Processor` đại diện cho một input channel và một output channel. Ví dụ sau dùng các annotation của mô hình legacy; chỉ đọc để nhận diện khi nâng cấp, **không dùng làm code mới**:

~~~java
// Legacy Spring Cloud Stream annotation-based programming model.
@EnableBinding(Processor.class)
public class LegacyOrderApplication {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String uppercase(String order) {
        return order.toUpperCase(Locale.ROOT);
    }
}
~~~

Vì `Processor.INPUT` và `Processor.OUTPUT` lần lượt có tên `input`, `output`, cấu hình cũ có thể là:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        output:
          destination: orders.normalized
          content-type: text/plain
~~~

Mô hình `@EnableBinding`/`@StreamListener` được khuyến nghị thay bằng functional programming từ Spring Cloud Stream 3.x. Khi nâng cấp, hãy làm rõ phiên bản đang dùng và không để code annotation legacy tồn tại lẫn lộn với function mới như hai consumer độc lập ngoài ý định.

## 4. Cách chuyển trực tiếp sang tên functional binding (khuyến nghị)

Thay xử lý legacy bằng một bean `Function`:

~~~java
import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderFunctions {

    @Bean
    Function<String, String> uppercase() {
        return order -> order.toUpperCase(Locale.ROOT);
    }
}
~~~

Khai báo function definition tường minh và đổi khóa `input`/`output` sang `uppercase-in-0`/`uppercase-out-0`:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        uppercase-out-0:
          destination: orders.normalized
          content-type: text/plain
~~~

**Kết quả:** tên binding thay đổi nhưng destination `orders.raw`, `orders.normalized` và consumer group `order-normalizer` được giữ nguyên. Broker vẫn sử dụng các topic/queue/exchange đã cấu hình, miễn là các thông số binder khác không bị đổi ngoài ý định.

Trong mô hình hàm, nếu ứng dụng chỉ có một bean `Supplier`/`Function`/`Consumer` được phát hiện, có thể không cần `spring.cloud.function.definition`. Tuy nhiên nên cấu hình tường minh khi nâng cấp, nhất là nếu sau này xuất hiện thêm function.

## 5. Cách chuyển từng bước: giữ tên input/output bằng alias

Nếu đang có nhiều file cấu hình theo môi trường, dashboard hoặc script sử dụng `bindings.input` và `bindings.output`, có thể giữ các tên đó trong giai đoạn chuyển tiếp bằng ánh xạ **implicit binding name → explicit binding name**:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      function:
        bindings:
          uppercase-in-0: input
          uppercase-out-0: output
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        output:
          destination: orders.normalized
          content-type: text/plain
~~~

Thuộc tính sử dụng là:

~~~text
spring.cloud.stream.function.bindings.<implicitBindingName>=<explicitBindingName>
~~~

Trong ví dụ, `uppercase-in-0` được đổi tên hiệu lực thành `input`; `uppercase-out-0` được đổi tên hiệu lực thành `output`. **Sau khi alias, mọi thuộc tính binding phải tham chiếu tên hiệu lực** `input`/`output`. Đừng cấu hình `spring.cloud.stream.bindings.uppercase-in-0.destination` đồng thời kỳ vọng framework sẽ gộp với `spring.cloud.stream.bindings.input.destination`.

Đây là đường migration được tài liệu Spring Cloud Stream hỗ trợ, nhưng thêm một lớp ánh xạ cần được duy trì. Với ứng dụng mới hoặc sau khi ổn định, tên mặc định theo function thường dễ theo dõi và ít gây nhầm hơn.

## 6. Hai lựa chọn migration: ưu và nhược điểm

| Tiêu chí | Đổi trực tiếp sang tên theo hàm | Alias giữ tên cũ |
|---|---|---|
| Khóa cấu hình chính | `bindings.uppercase-in-0` | `bindings.input` |
| Có cần `function.bindings` không? | Không | Có |
| Đọc log và Actuator | Dễ liên hệ với function | Phải tra ánh xạ alias |
| Số thay đổi ở file cấu hình cũ | Nhiều hơn | Ít hơn |
| Phù hợp | Đích nâng cấp bền vững | Chuyển tiếp, hệ thống có nhiều config phụ thuộc |
| Rủi ro chính | Bỏ sót một khóa thuộc tính cũ | Lẫn tên implicit và tên alias |

Không sử dụng hai chiến lược song song cho **cùng một binding**. Chọn một phương án, lập bảng mapping và kiểm tra tại thời điểm runtime. Nếu alias chỉ là giải pháp tạm, ghi rõ thời điểm dự kiến bỏ alias và chuyển hết cấu hình sang tên theo hàm.

## 7. Bảng chuyển Source, Sink, Processor

Các interface legacy có số cổng khác nhau; không phải loại nào cũng có cả `input` và `output`.

| Legacy interface | Tên legacy | Bean hàm thay thế | Tên binding mới ví dụ |
|---|---|---|---|
| `Source` | `output` | `Supplier<OrderEvent> publishOrder` | `publishOrder-out-0` |
| `Sink` | `input` | `Consumer<OrderEvent> saveOrder` | `saveOrder-in-0` |
| `Processor` | `input`, `output` | `Function<OrderEvent,OrderEvent> normalizeOrder` | `normalizeOrder-in-0`, `normalizeOrder-out-0` |
| Custom `@Input("ordersIn")` | `ordersIn` | `Consumer<OrderEvent> processOrder` | `processOrder-in-0` |
| Custom `@Output("alertsOut")` | `alertsOut` | `Supplier<Alert> publishAlert` | `publishAlert-out-0` |

Đối với `Supplier`, hãy kiểm tra cách polling/scheduling nguồn phát được tổ chức ở version mới; tên output được suy ra theo quy tắc `-out-0`. Đối với `Consumer`, chỉ có input binding, không nên tạo `-out-0` chỉ để giữ cấu hình cũ không còn dùng.

Nếu legacy dùng custom interface với tên tùy ý, mapping alias cũng có thể trỏ đến các tên đó:

~~~yaml
spring:
  cloud:
    stream:
      function:
        bindings:
          processOrder-in-0: ordersIn
          publishAlert-out-0: alertsOut
~~~

Chỉ cấu hình `bindings.ordersIn` và `bindings.alertsOut` nếu đã chọn chiến lược alias.

## 8. Di chuyển toàn bộ cấu hình, không chỉ destination

Các trường cấu hình cần kiểm tra khi đổi tên gồm:

| Nhóm cấu hình | Trước migration | Sau migration (trực tiếp) |
|---|---|---|
| Destination | `bindings.input.destination` | `bindings.uppercase-in-0.destination` |
| Group | `bindings.input.group` | `bindings.uppercase-in-0.group` |
| Content type | `bindings.output.content-type` | `bindings.uppercase-out-0.content-type` |
| Consumer concurrency | `bindings.input.consumer.concurrency` | `bindings.uppercase-in-0.consumer.concurrency` |
| Retry | `bindings.input.consumer.max-attempts` | `bindings.uppercase-in-0.consumer.max-attempts` |
| Partition key | `bindings.output.producer.partition-key-expression` | `bindings.uppercase-out-0.producer.partition-key-expression` |
| Binder instance | `bindings.input.binder` | `bindings.uppercase-in-0.binder` |
| Kafka consumer extension | `kafka.bindings.input.consumer.*` | `kafka.bindings.uppercase-in-0.consumer.*` |
| Rabbit producer extension | `rabbit.bindings.output.producer.*` | `rabbit.bindings.uppercase-out-0.producer.*` |

Các tiền tố ở bảng nằm dưới `spring.cloud.stream`. Nếu dùng alias, cột cấu hình sau migration sẽ tiếp tục mang tên alias `input`/`output`, **kể cả khi dùng thuộc tính mở rộng theo binder**.

Ví dụ chuyển một số Kafka binding-specific properties:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
          binder: kafka
          consumer:
            concurrency: 3
            max-attempts: 4
        uppercase-out-0:
          destination: orders.normalized
          binder: kafka
      kafka:
        bindings:
          uppercase-in-0:
            consumer:
              enable-dlq: true
          uppercase-out-0:
            producer:
              sync: false
~~~

`destination`, `group`, `binder` và các thuộc tính mở rộng vẫn cần được giữ nguyên giá trị nghiệp vụ nếu bản nâng cấp chưa có chủ đích đổi semantics. Kiểm tra thực tế thuộc tính có được hỗ trợ trong phiên bản binder đích; nâng cấp phiên bản thư viện có thể tạo ra thay đổi ngoài việc đổi tên.

## 9. Ví dụ hai môi trường: alias và trực tiếp

Giả sử cùng một ứng dụng triển khai trong môi trường staging và production bằng cấu hình được gộp từ nhiều nguồn. Một lỗi thường gặp là cấu hình chung dùng tên mới nhưng file production vẫn ghi đè tên cũ:

~~~yaml
# application.yml, đã chuyển sang tên mới
spring:
  cloud:
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
~~~

~~~yaml
# application-prod.yml, còn khóa cũ; KHÔNG được tự áp dụng cho uppercase-in-0
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.raw.prod
~~~

Nếu không có alias, `bindings.input.destination` không phải cấu hình của `uppercase-in-0`. Vì vậy runtime có thể đọc sai topic, tạo destination khác hoặc bỏ qua giá trị production mong đợi.

Lộ trình:

1. Liệt kê tất cả file `application*.yml`, biến môi trường, chart Helm, Config Server và tham số command line đang chứa `bindings.input` hoặc `bindings.output`.
2. Chọn một phương án: đổi toàn bộ sang `uppercase-...` hoặc alias toàn bộ về tên cũ.
3. Kiểm tra cấu hình sau khi Spring Boot merge profiles và các nguồn property, đặc biệt ở production.
4. Chạy test kết nối broker và xác nhận topic/group thật trước khi cutover.

Ví dụ trên chỉ để minh họa sai lệch cấu hình; không dùng hai đoạn mâu thuẫn trong một deployment.

## 10. Nhiều function trong một ứng dụng

Khi có hai function bean, cần chọn rõ function nào phải được bind. Dấu `;` trong `spring.cloud.function.definition` cho phép khai báo nhiều function độc lập:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: "uppercase;reverse"
    stream:
      bindings:
        uppercase-in-0:
          destination: uppercase.request
        uppercase-out-0:
          destination: uppercase.response
        reverse-in-0:
          destination: reverse.request
        reverse-out-0:
          destination: reverse.response
~~~

Đây là **hai pipeline độc lập**. Không gán cả hai function vào alias `input`/`output` nếu chúng cần broker destinations khác nhau. Mỗi binding cần tên hiệu lực duy nhất, hoặc alias riêng có thể theo dõi được.

Nếu chỉ khai báo `spring.cloud.function.definition: uppercase` thì function `reverse` không tự tạo cặp binding riêng theo cấu hình này. Không coi việc Java bean tồn tại đồng nghĩa đã được chọn để bind.

## 11. Function composition cũng tác động tên binding

Nếu muốn chạy hai function thành một pipeline liên tiếp, dùng `|` thay vì `;`:

~~~yaml
spring:
  cloud:
    function:
      definition: "uppercase|reverse"
~~~

`uppercase;reverse` tạo hai luồng độc lập, còn `uppercase|reverse` tạo một function tổng hợp mà output của `uppercase` chuyển tiếp sang `reverse`.

Tên binding được hình thành từ tên function tổng hợp. Với **Kafka Streams Binder**, tài liệu mô tả ví dụ `foo|bar` có tên binding mặc định `foobar-in-0` và `foobar-out-0`. Các ví dụ đời cũ của Spring Cloud Function có thể thể hiện tên composition khác theo phiên bản và cách khai báo. Vì vậy, khi đổi thành composition, hãy kiểm tra binding name thực tế trong log/Actuator trước khi chuyển toàn bộ cấu hình.

Không mặc định rằng `uppercase-in-0` và `reverse-out-0` sẽ là tên binding ngoài cùng sau composition. Nếu cần một tên ổn định, có thể dùng alias cho binding của **function tổng hợp thực tế** hoặc bọc composition trong một bean có tên rõ ràng, tùy binder và yêu cầu topology.

## 12. Nhiều input/output trong Kafka Streams

Với Kafka Streams Binder, một function có thể có nhiều input và/hoặc output. Ví dụ:

~~~java
@Bean
BiFunction<KStream<String, OrderEvent>,
           KTable<String, Customer>,
           KStream<String, EnrichedOrder>> joinOrders() {
    return (orders, customers) ->
        orders.leftJoin(customers,
            (order, customer) -> new EnrichedOrder(order, customer));
}
~~~

Cấu hình binding theo chỉ số:

~~~yaml
spring:
  cloud:
    function:
      definition: joinOrders
    stream:
      bindings:
        joinOrders-in-0:
          destination: orders.events
        joinOrders-in-1:
          destination: customers.table
        joinOrders-out-0:
          destination: orders.enriched
~~~

Nếu interface legacy có tên `ordersInput` và `customersInput`, xác định chính xác input nào tương ứng `-in-0` và `-in-1`. Mapping nhầm thứ tự khiến processor đọc sai stream/table, có thể gây lỗi deserialization hoặc sai join.

Có thể dùng alias khi cần tên dễ đọc:

~~~yaml
spring:
  cloud:
    stream:
      function:
        bindings:
          joinOrders-in-0: ordersInput
          joinOrders-in-1: customersInput
          joinOrders-out-0: enrichedOutput
      bindings:
        ordersInput:
          destination: orders.events
        customersInput:
          destination: customers.table
        enrichedOutput:
          destination: orders.enriched
~~~

Hãy ghi rõ mapping giữa tham số hàm, binding index và destination, nhất là với Kafka Streams khi KTable/KStream có semantics khác nhau.

## 13. Output `StreamBridge` không nhất thiết là output function

Một số code cũ gọi trực tiếp `MessageChannel` hoặc `Source.OUTPUT` để phát message từ HTTP endpoint, scheduler hoặc service không có input stream. Với mô hình hiện tại, có thể dùng `StreamBridge`:

~~~java
@RestController
class OrderPublisher {
    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    void publish(@RequestBody OrderEvent event) {
        streamBridge.send("ordersOutput", event);
    }
}
~~~

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersOutput
      bindings:
        ordersOutput:
          destination: orders.events
~~~

`spring.cloud.stream.output-bindings` chủ động tạo output binding không gắn với `Supplier`/`Function`, thường dùng cùng `StreamBridge`. Nó **khác** `spring.cloud.stream.function.bindings`: cái thứ nhất tạo binding tường minh, cái thứ hai đổi tên binding implicit của một function. Không máy móc đổi mọi `output` thành `<someFunction>-out-0` nếu đường phát message không còn do function điều khiển.

## 14. Chuẩn hóa cấu hình theo binder khi nâng cấp

Một dự án SPRING_CLOUD_STREAM có thể dùng Kafka, RabbitMQ hoặc Pulsar, thậm chí nhiều binder cùng lúc. Tên binding được suy ra từ function, nhưng **binder-specific properties vẫn nằm dưới nhánh binder riêng**:

~~~text
spring.cloud.stream.bindings.<bindingName>...
spring.cloud.stream.kafka.bindings.<bindingName>...
spring.cloud.stream.rabbit.bindings.<bindingName>...
spring.cloud.stream.pulsar.bindings.<bindingName>...
~~~

Nếu chuyển từ `input` sang `normalizeOrder-in-0`, tìm cả các nhánh cấu hình mở rộng. Ví dụ một Kafka DLQ setting còn nằm dưới `kafka.bindings.input.consumer.enable-dlq` sẽ không tự được xem là cấu hình cho `normalizeOrder-in-0` trong chiến lược đổi tên trực tiếp.

Với ứng dụng nhiều binder, giữ đúng:

- `bindings.<name>.binder`: named binder instance đã chọn.
- `bindings.<name>.destination`: destination broker hiện có.
- `bindings.<name>.group`: group ứng dụng đang dùng.
- Các thuộc tính partition, retry, DLQ, schema và content-type của từng binding.
- Cấu hình Kafka Streams `application.id`, state store/changelog và các tham số topology liên quan nếu nâng cấp Kafka Streams.

Đổi consumer group hoặc Kafka Streams application ID ngoài ý định có thể tạo một nhóm đọc mới với offset khác hoặc một bộ state mới. Đây là thay đổi semantics cần kế hoạch replay/migration riêng, không phải hệ quả bắt buộc của đổi tên binding.

## 15. Migration có làm thay đổi topic hoặc consumer offset không?

**Chỉ đổi tên binding logic** và giữ `destination`, `group`, binder configuration, serializer/deserializer và các thuộc tính xử lý thì **không mặc nhiên tạo topic mới hoặc reset consumer offset**.

Ngược lại, nếu cấu hình mới thiếu `destination`, Spring Cloud Stream có thể dùng tên binding làm destination mặc định. Với function `uppercase`, `uppercase-in-0` sẽ không tự đọc từ `orders.raw` nếu giá trị destination cũ không được chuyển. Broker/binder có thể tạo destination mới theo chính sách provisioning, dẫn đến hiện tượng ứng dụng chạy nhưng không nhận message từ topic cũ.

Nếu thay đổi `group`, semantics của consumer group và offset có thể thay đổi. Với RabbitMQ, đổi group thường đổi tên queue được tạo/quản lý. Với Kafka, group mới có offset riêng; bắt đầu đọc từ đâu phụ thuộc cấu hình auto offset reset và trạng thái topic.

Không kết luận migration thành công chỉ vì ứng dụng start được. Cần xác minh topic, queue, group và dòng message thực tế.

## 16. Kế hoạch chuyển đổi an toàn theo từng bước

1. **Kiểm kê:** lập bảng mọi binding legacy, direction, destination, group, binder, content type, consumer/producer options và môi trường áp dụng.
2. **Chọn function bean:** chuyển logic `@StreamListener` hoặc channel handler sang `Supplier`/`Function`/`Consumer` tương ứng.
3. **Quyết định tên:** dùng tên implicit theo function hoặc alias cho giai đoạn chuyển tiếp; ghi một mapping 1:1.
4. **Chuyển cấu hình:** di chuyển toàn bộ `bindings.*` và binder-specific `kafka/rabbit/pulsar.bindings.*`; giữ destination và group.
5. **Chọn function definition:** dùng `spring.cloud.function.definition` để kiểm soát những function phải được bind.
6. **Kiểm tra startup:** xác nhận binding thực tế bằng log và, nếu có, endpoint Actuator `/actuator/bindings`.
7. **Kiểm thử message:** gửi event vào destination cũ, xác nhận function mới xử lý và output đến destination cũ.
8. **Kiểm thử failure path:** retry, DLQ, error channel, acknowledgement, partition key, consumer lag và offset khi restart.
9. **Cutover:** triển khai bằng chiến lược rolling/blue-green phù hợp, tránh vô tình chạy hai đường xử lý cùng ghi một kết quả không idempotent.
10. **Dọn legacy:** sau khi xác nhận, gỡ annotation/interface/channel cũ và các khóa không còn dùng; ghi lại mapping migration.

Một biểu mẫu kiểm kê:

| Legacy binding | Function binding mới | Destination giữ nguyên | Group giữ nguyên | Binder |
|---|---|---|---|---|
| `input` | `uppercase-in-0` | `orders.raw` | `order-normalizer` | Kafka |
| `output` | `uppercase-out-0` | `orders.normalized` | Không áp dụng | Kafka |
| `ordersIn` | `processOrders-in-0` | `orders.pending` | `fulfillment` | RabbitMQ |
| `alertsOut` | `publishAlert-out-0` | `alerts.events` | Không áp dụng | Pulsar |

## 17. Kiểm thử nhanh với Spring Cloud Stream Test Binder

Test Binder giúp kiểm tra function và binding của ứng dụng trong JVM, không cần broker thật. Ví dụ dùng `InputDestination` và `OutputDestination` với cấu hình **đổi trực tiếp**:

~~~java
@SpringBootTest(
    classes = UppercaseBindingMigrationTest.TestApplication.class,
    properties = {
    "spring.cloud.function.definition=uppercase",
    "spring.cloud.stream.bindings.uppercase-in-0.destination=orders.raw",
    "spring.cloud.stream.bindings.uppercase-out-0.destination=orders.normalized"
})
@EnableTestBinder
class UppercaseBindingMigrationTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void stillUsesOriginalDestinations() {
        input.send(
            new GenericMessage<>("abC".getBytes(StandardCharsets.UTF_8)),
            "orders.raw"
        );

        Message<byte[]> actual =
            output.receive(1_000, "orders.normalized");

        assertThat(actual).isNotNull();
        assertThat(new String(actual.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("ABC");
    }

    @SpringBootApplication
    static class TestApplication {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Đây là ví dụ test focused; cần các dependency `spring-cloud-stream-test-binder`, Spring Boot Test, JUnit và AssertJ phù hợp phiên bản dự án. Trong test nhiều function, chỉ định destination cho từng lời gọi `send` và `receive` để tránh nhầm output.

Test Binder xác minh wiring và logic trong JVM, **không chứng minh** consumer group, Kafka offset/partition, Rabbit queue binding, Pulsar subscriptions, retry/DLQ hoặc metadata broker đã được giữ đúng. Những phần đó cần integration test với Kafka/RabbitMQ/Pulsar thật.

## 18. Kiểm tra bằng Actuator và broker

Nếu có Spring Boot Actuator và đã expose endpoint `bindings` theo chính sách quản trị:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: bindings
~~~

Liệt kê binding:

~~~bash
curl http://localhost:8080/actuator/bindings
~~~

Trong phương án đổi trực tiếp, kiểm tra các binding tên `uppercase-in-0` và `uppercase-out-0`. Trong phương án alias, tên hiệu lực được sử dụng trong cấu hình là `input` và `output`; đối chiếu response đúng phiên bản đang chạy.

Sau đó kiểm tra trên broker:

- Kafka: topic có đúng tên không, group ID có đúng không, partition assignment, offset và consumer lag có bình thường không?
- RabbitMQ: exchange/queue/routing key đúng không, queue của group có bị tạo mới ngoài ý định không, số message ready/unacked có tăng bất thường không?
- Pulsar: topic, subscription name/type và schema có được giữ như trước không?
- Multi-binder: từng input/output đang kết nối đúng named binder instance và broker environment không?

Endpoint quản trị không nên expose công khai; bảo vệ bằng xác thực/phân quyền và mạng nội bộ.

## 19. Các lỗi migration phổ biến

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
|---|---|---|
| Ứng dụng chạy nhưng không tiêu thụ message | Không chuyển `bindings.input.destination` sang `uppercase-in-0.destination` | Kiểm tra destination thực của binding và topic/queue |
| Topic hoặc queue mới xuất hiện | Thiếu destination; binder tự lấy binding name | Gắn `destination` tường minh, kiểm tra auto-provision |
| Group/offset đổi sau deploy | Bỏ sót `group` hoặc đổi application ID | Giữ group/app ID hiện có nếu muốn giữ tiến độ |
| Retry/DLQ không còn hiệu lực | Thuộc tính mở rộng vẫn nằm dưới `kafka.bindings.input` | Chuyển cả binder-specific config sang tên hiệu lực |
| Output không đi đúng broker | Quên `binder` hoặc named binder configuration | Đối chiếu binder name, broker endpoint |
| Chỉ một trong nhiều function được bind | Thiếu tên trong `spring.cloud.function.definition` | Khai báo `"foo;bar"` cho các function độc lập |
| Hai function dùng chung alias `input` | Alias trùng nhau, cấu hình bị mơ hồ | Đặt alias độc lập hoặc chuyển sang tên implicit |
| Composition đọc sai destination | Đổi từ `foo;bar` sang `foo|bar` nhưng giữ cấu hình binding cũ | Xác định lại tên binding ngoài cùng của function tổng hợp |
| Nội dung sai schema sau nâng cấp | Chữ ký function hoặc conversion thay đổi | Kiểm tra content-type, serde/schema registry và headers |
| Test Binder đạt nhưng production sai | Không có broker metadata, group, offset, DLQ trong Test Binder | Bổ sung integration test với broker thật |
| `StreamBridge` gửi nhầm topic | Gọi `send` bằng binding name/destination nhầm | Dùng output binding tường minh và mapping rõ ràng |
| Các cấu hình environment khác nhau | Profiles/Config Server vẫn dùng khóa `input/output` | Rà toàn bộ nguồn properties, kiểm tra runtime merged config |

## 20. Bài thực hành chuyển đổi

Cho ứng dụng legacy dùng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: payments.created
          group: payment-audit
          consumer:
            max-attempts: 3
        output:
          destination: payments.checked
~~~

Yêu cầu chuyển nghiệp vụ sang bean:

~~~java
@Bean
Function<PaymentCreated, PaymentChecked> verifyPayment() {
    return event -> new PaymentChecked(
        event.paymentId(),
        event.amount() > 0
    );
}
~~~

Thực hiện hai phiên bản cấu hình:

1. **Phiên bản A:** không alias; thay `input` bằng `verifyPayment-in-0` và `output` bằng `verifyPayment-out-0`. Giữ destination, group, retry.
2. **Phiên bản B:** đặt `function.bindings.verifyPayment-in-0=input` và `function.bindings.verifyPayment-out-0=output`, giữ cấu hình binding cũ.
3. Kiểm tra startup xem chỉ có một cặp binding chức năng và hai destination mong đợi.
4. Gửi một message hợp lệ; xác nhận có output `payments.checked`.
5. Gửi message lỗi; xác nhận retry/error semantics vẫn giống yêu cầu cũ.
6. Kiểm tra Kafka consumer group hoặc Rabbit queue của group vẫn giữ nguyên nếu dùng các binder tương ứng.

Một bài được xem là đạt khi **hành vi broker không đổi ngoài các thay đổi có chủ đích**, các binding mang tên đúng phương án đã chọn, và mọi thuộc tính quan trọng được áp dụng ở runtime.

## 21. Checklist trước khi phát hành

- [ ] Đã kiểm kê mọi legacy `input`, `output` và custom `@Input`/`@Output`.
- [ ] Đã xác định đúng bean function và tên `-in-N`/`-out-N`.
- [ ] Đã chọn rõ phương án đổi trực tiếp hoặc alias; không trộn tên cho cùng binding.
- [ ] Đã khai báo `spring.cloud.function.definition` phù hợp với số function và composition.
- [ ] Đã giữ đúng destination, group, named binder và connection environment.
- [ ] Đã chuyển cả `bindings.*` lẫn các nhánh `kafka/rabbit/pulsar.bindings.*`.
- [ ] Đã kiểm tra content type, serializer/deserializer, schema, headers và key partition.
- [ ] Đã kiểm tra retry, DLQ, ack và idempotency khi ứng dụng restart.
- [ ] Nếu dùng Kafka Streams, đã xác định lại đúng input/output indices và giữ application ID/state semantics.
- [ ] Đã kiểm tra cấu hình ở tất cả profiles, biến môi trường, Helm/Config Server.
- [ ] Đã kiểm thử function với Test Binder và integration test với broker thật.
- [ ] Đã xác minh binding/runtime và destination trên Actuator/log/broker.
- [ ] Đã có kế hoạch cutover/rollback và tránh xử lý trùng không idempotent.
- [ ] Đã xóa annotation/interface/config legacy không dùng sau khi xác nhận.

**Nguyên tắc kết luận:** tên `input`/`output` là tên binding logic của mô hình cũ; trong mô hình hàm, Spring Cloud Stream tạo tên mặc định theo bean như `verifyPayment-in-0`/`verifyPayment-out-0`. Chuyển hết các khóa cấu hình sang tên mới là đích đến dễ bảo trì nhất. Khi cần giảm thay đổi trong giai đoạn nâng cấp, có thể dùng `spring.cloud.stream.function.bindings` để giữ alias cũ. Dù chọn cách nào, hãy kiểm tra rằng **destination, group, binder và semantics giao nhận** vẫn đúng trước khi triển khai production.

## Tài liệu tham khảo

- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding and Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-names.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Explicit Binding Creation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/explicit-binding-creation.html)
- [Spring Cloud Stream — Kafka Binder Tips: Override Default Binding Names](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Cloud Stream — Kafka Streams Binder Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
