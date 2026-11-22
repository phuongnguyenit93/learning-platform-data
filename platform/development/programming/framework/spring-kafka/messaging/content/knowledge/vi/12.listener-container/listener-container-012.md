# ContainerCustomizer trong Spring Kafka

`ContainerCustomizer` là hook cho phép tùy chỉnh listener container sau khi `KafkaListenerContainerFactory` tạo và cấu hình container. Nhờ hook này, ứng dụng có thể thiết lập những thuộc tính vận hành ở cấp container mà không cần viết một listener container riêng hoặc lặp lại cấu hình trong từng phương thức `@KafkaListener`.

Trong Spring Kafka, factory chịu trách nhiệm tạo container cho các endpoint. `ContainerCustomizer` nhận container vừa được tạo để bổ sung cấu hình như poll timeout, acknowledgment mode hoặc khoảng thời gian phát idle event. Vì customizer gắn với factory, nó được áp dụng cho các container do factory đó tạo.

## 1. ContainerCustomizer nằm ở đâu trong kiến trúc?

Một phương thức `@KafkaListener` khai báo endpoint nhận record. Spring Kafka chuyển endpoint thành listener container thông qua `KafkaListenerContainerFactory`. Factory dùng `ConsumerFactory` để tạo Kafka consumer và áp dụng các thiết lập vận hành. `ContainerCustomizer` là điểm mở rộng để điều chỉnh container sau bước cấu hình của factory.

```mermaid
flowchart TD
    A[@KafkaListener endpoint] --> B[KafkaListenerContainerFactory]
    B --> C[Tạo listener container]
    C --> D[Áp dụng cấu hình factory và endpoint]
    D --> E[ContainerCustomizer.configure(container)]
    E --> F[Listener container hoàn chỉnh]
    F --> G[ConsumerFactory tạo Kafka consumer]
    G --> H[Subscribe, poll và gọi listener]
```

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `@KafkaListener` | Khai báo topic, group ID, kiểu listener và các tùy chọn theo endpoint |
| `ConsumerFactory` | Tạo Kafka consumer với bootstrap server, deserializer và Kafka client properties |
| `KafkaListenerContainerFactory` | Tạo listener container và áp dụng các cấu hình chung cho listener |
| `ContainerCustomizer` | Chỉnh sửa container sau khi factory đã tạo và cấu hình nó |
| `MessageListenerContainer` | Quản lý vòng đời consumer, poll, listener invocation và acknowledgment |
| `ContainerProperties` | Chứa các thuộc tính vận hành của container như ack mode, poll timeout và idle event |

`ContainerCustomizer` không thay thế `ConsumerFactory`, không tự tạo topic và cũng không thay thế logic xử lý trong listener. Nó tác động tới container mà factory tạo ra.

## 2. Khai báo ContainerCustomizer cơ bản

Interface `ContainerCustomizer<C extends MessageListenerContainer>` có một phương thức `configure(C container)`. Có thể truyền lambda trực tiếp vào factory:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);

        factory.setContainerCustomizer(container -> {
            container.getContainerProperties().setPollTimeout(2_000L);
            container.getContainerProperties()
                    .setAckMode(ContainerProperties.AckMode.RECORD);
        });

        return factory;
    }
}
```

Trong ví dụ:

- `setContainerCustomizer(...)` đăng ký hàm tùy chỉnh với factory.
- `container` là listener container mà factory vừa tạo.
- `getContainerProperties()` trả về cấu hình vận hành của container.
- `setPollTimeout(2_000L)` đặt thời gian chờ tối đa cho thao tác poll theo đơn vị millisecond.
- `AckMode.RECORD` yêu cầu container commit sau khi xử lý thành công từng record, theo cơ chế acknowledgment và commit đang cấu hình.

Để listener sử dụng factory này, khai báo tên bean trong annotation:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    // Xử lý sự kiện.
}
```

Nếu listener không chỉ định `containerFactory`, Spring Kafka sử dụng factory mặc định theo quy ước, thường là `kafkaListenerContainerFactory`. Đảm bảo tên trong annotation trùng chính xác tên bean đã đăng ký.

## 3. Tùy chỉnh ContainerProperties

`ContainerProperties` là nơi cấu hình nhiều hành vi của listener container. Customizer có thể lấy đối tượng này từ container và điều chỉnh các giá trị cần thiết.

Một số thuộc tính thường được quan tâm:

| Thuộc tính | Ý nghĩa | Ảnh hưởng vận hành |
|---|---|---|
| `pollTimeout` | Thời gian chờ cho một lần poll | Ảnh hưởng thời gian container chờ dữ liệu và độ phản hồi khi poll rỗng |
| `ackMode` | Cách container commit offset | Quyết định thời điểm commit sau khi listener xử lý |
| `idleEventInterval` | Khoảng thời gian phát idle event khi container không nhận record | Hỗ trợ phát hiện listener ít hoặc không có dữ liệu |
| `shutdownTimeout` | Thời gian chờ khi container dừng | Ảnh hưởng thời gian chờ xử lý shutdown |

Ví dụ cấu hình thêm idle event:

```java
factory.setContainerCustomizer(container -> {
    ContainerProperties properties = container.getContainerProperties();
    properties.setPollTimeout(1_500L);
    properties.setAckMode(ContainerProperties.AckMode.RECORD);
    properties.setIdleEventInterval(60_000L);
});
```

Idle event có thể hữu ích để quan sát listener không nhận record trong một khoảng thời gian. Nó không chứng minh consumer bị lỗi: topic có thể đơn giản là không có dữ liệu. Ứng dụng nên phân biệt trạng thái idle với lỗi kết nối hoặc consumer lag tăng.

Các setter và kiểu dữ liệu của `ContainerProperties` có thể thay đổi theo phiên bản Spring Kafka. Hãy đối chiếu API của phiên bản đang dùng trước khi áp dụng cấu hình cụ thể.

## 4. Đăng ký customizer thành bean riêng

Khi logic tùy chỉnh dài hoặc cần tái sử dụng, có thể khai báo `ContainerCustomizer` thành bean riêng thay vì viết lambda trực tiếp trong factory:

```java
@Bean
public ContainerCustomizer<ConcurrentMessageListenerContainer<String, OrderCreated>>
        ordersContainerCustomizer() {

    return container -> {
        ContainerProperties properties = container.getContainerProperties();
        properties.setPollTimeout(2_000L);
        properties.setAckMode(ContainerProperties.AckMode.RECORD);
        properties.setIdleEventInterval(30_000L);
    };
}
```

Sau đó inject customizer vào factory:

```java
@Bean
public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        ordersListenerContainerFactory(
                ConsumerFactory<String, OrderCreated> consumerFactory,
                ContainerCustomizer<ConcurrentMessageListenerContainer<String, OrderCreated>>
                        ordersContainerCustomizer) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(ordersContainerCustomizer);
    return factory;
}
```

Kiểu generic của customizer cần tương thích với kiểu container mà factory tạo ra. Với `ConcurrentKafkaListenerContainerFactory<K,V>`, container tương ứng thường là `ConcurrentMessageListenerContainer<K,V>`.

Tách customizer thành bean riêng giúp cấu hình dễ kiểm thử và dễ đọc hơn, đặc biệt khi cần inject một dependency chỉ phục vụ việc thiết lập container. Với một vài dòng cấu hình đơn giản, lambda trực tiếp trong factory thường dễ hiểu hơn.

## 5. Thời điểm customizer được gọi

Customizer được factory gọi trong quá trình tạo listener container, sau khi factory đã áp dụng cấu hình của factory và endpoint. Container được tùy chỉnh trước khi bắt đầu xử lý record.

Luồng khái quát:

1. Spring phát hiện `@KafkaListener` và tạo endpoint.
2. Endpoint chọn `KafkaListenerContainerFactory` tương ứng.
3. Factory tạo listener container.
4. Factory áp dụng cấu hình chung và các tùy chọn endpoint.
5. `ContainerCustomizer.configure(container)` được gọi.
6. Container được đăng ký và khởi động theo lifecycle/`autoStartup`.
7. Consumer bắt đầu subscribe và poll khi container chạy.

Vì customizer chạy lúc tạo container, nó không phải callback được gọi mỗi lần poll hoặc mỗi lần nhận record. Không đặt logic nghiệp vụ xử lý message, gọi API từ xa hoặc truy vấn dữ liệu nặng trong `configure`.

Nếu cấu hình được thay đổi sau khi container đã tạo, customizer không tự chạy lại. Muốn áp dụng cấu hình mới, ứng dụng cần cập nhật container theo API được hỗ trợ hoặc tạo lại container theo quy trình lifecycle phù hợp.

## 6. Phạm vi áp dụng: factory và listener

Một `ContainerCustomizer` gắn với factory sẽ được áp dụng cho các listener container được tạo từ factory đó. Nếu nhiều listener dùng cùng factory, customizer có thể ảnh hưởng tới tất cả chúng.

Ví dụ:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
        sharedListenerContainerFactory(
                ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderEvent>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(container ->
            container.getContainerProperties().setPollTimeout(2_000L));
    return factory;
}
```

Hai listener cùng chọn `sharedListenerContainerFactory` sẽ cùng nhận thiết lập poll timeout này:

```java
@KafkaListener(
        topics = "orders.created",
        groupId = "order-projection",
        containerFactory = "sharedListenerContainerFactory"
)
public void project(OrderCreated event) {
    // ...
}

@KafkaListener(
        topics = "orders.updated",
        groupId = "order-projection",
        containerFactory = "sharedListenerContainerFactory"
)
public void update(OrderUpdated event) {
    // ...
}
```

Nếu hai nhóm listener cần cấu hình container khác nhau, tạo factory riêng cho từng nhóm và gắn customizer tương ứng. Cách này thể hiện phạm vi cấu hình rõ ràng và tránh các nhánh điều kiện khó kiểm soát trong một customizer dùng chung.

## 7. Phân biệt cấu hình factory, annotation và customizer

Spring Kafka có nhiều lớp cấu hình. Cần chọn đúng nơi để tránh ghi đè ngoài ý muốn:

| Nơi cấu hình | Phạm vi | Ví dụ |
|---|---|---|
| `ConsumerFactory` | Kafka consumer được tạo ra | bootstrap server, deserializer, `max.poll.records`, security |
| `KafkaListenerContainerFactory` | Các container được tạo từ factory | concurrency mặc định, common error handler, record converter |
| `@KafkaListener` | Một endpoint cụ thể | topics, group ID, auto startup, container factory |
| `ContainerCustomizer` | Container được tạo bởi factory | thiết lập bổ sung trên `ContainerProperties` hoặc container |
| Listener method | Logic nghiệp vụ của record | validate event, gọi service, ghi dữ liệu |

Ví dụ, `max.poll.records` là Kafka consumer property nên thường đặt trong `ConsumerFactory`/consumer properties. `pollTimeout` là thuộc tính container nên đặt ở `ContainerProperties`. `topics` là subscription của endpoint nên đặt ở `@KafkaListener`.

Không dùng customizer để thay thế toàn bộ cấu hình consumer. Cũng không đặt logic nghiệp vụ vào customizer vì hook này chỉ chuẩn bị container, không xử lý từng record.

## 8. Thứ tự cấu hình và tránh ghi đè

Factory có thể áp dụng giá trị mặc định, annotation có thể cung cấp giá trị riêng cho endpoint, và customizer có thể điều chỉnh container sau khi các cấu hình đó được áp dụng. Vì customizer là bước tùy chỉnh sau khi container được tạo, các giá trị nó đặt có thể ghi đè thiết lập trước đó trên chính container.

Ví dụ, nếu factory đặt `AckMode.BATCH`, nhưng customizer đặt lại thành `AckMode.RECORD`, container cuối cùng sẽ dùng giá trị sau cùng được áp dụng. Điều này có thể khiến hành vi khác với cấu hình đọc từ factory hoặc annotation.

Để tránh khó truy vết:

- Chọn một nguồn cấu hình có trách nhiệm rõ ràng cho mỗi thuộc tính.
- Dùng customizer cho thiết lập thật sự cần hook ở cấp container.
- Không đặt cùng một thuộc tính ở factory, annotation và customizer nếu không có lý do cụ thể.
- Ghi chú rõ khi customizer cố ý ghi đè một giá trị mặc định.
- Kiểm tra container thực tế trong integration test nếu thứ tự cấu hình ảnh hưởng tới commit hoặc lifecycle.

Khi nâng cấp Spring Kafka, nên kiểm tra lại thứ tự áp dụng cấu hình trong phiên bản mới, đặc biệt nếu ứng dụng dựa vào việc ghi đè các thuộc tính giữa annotation và customizer.

## 9. Phân chia customizer theo nhóm listener

Vì customizer gắn với factory, cách rõ ràng nhất để tạo cấu hình khác nhau cho các nhóm listener là dùng factory riêng. Ví dụ, nhóm listener cần poll ngắn và nhóm listener xử lý batch có thể dùng hai factory:

```java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        fastOrdersFactory(ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(container ->
            container.getContainerProperties().setPollTimeout(500L));
    return factory;
}

@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
        batchOrdersFactory(ConsumerFactory<String, OrderCreated> consumerFactory) {

    var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
    factory.setConsumerFactory(consumerFactory);
    factory.setContainerCustomizer(container ->
            container.getContainerProperties().setPollTimeout(3_000L));
    return factory;
}
```

Mỗi listener chọn factory theo nhu cầu:

```java
@KafkaListener(topics = "orders.fast", containerFactory = "fastOrdersFactory")
public void handleFast(OrderCreated event) {
    // ...
}

@KafkaListener(topics = "orders.batch", containerFactory = "batchOrdersFactory")
public void handleBatch(OrderCreated event) {
    // ...
}
```

Cách này làm rõ phạm vi cấu hình ngay tại annotation. Một số phiên bản container có thể cung cấp listener ID để customizer phân nhánh, nhưng cần kiểm tra API thực tế trước khi phụ thuộc vào khả năng đó. Không nên tạo nhiều nhánh dựa trên topic hoặc tên bean nếu hai nhóm listener có thể dùng factory riêng.

## 10. Phân biệt hook ở tầng container và consumer

`ContainerCustomizer` tác động lên listener container do factory tạo ra. Nó chạy ở tầng Spring Kafka container, sau khi endpoint được cấu hình.

Kafka consumer có thể có các hook hoặc cơ chế cấu hình khác để điều chỉnh client khi consumer được tạo. Những cơ chế đó thuộc tầng Kafka consumer, thường liên quan tới `ConsumerFactory` hoặc consumer properties.

Phân biệt theo mục tiêu:

- Muốn thay đổi bootstrap server, deserializer, security hoặc `max.poll.records`: cấu hình consumer factory/properties.
- Muốn điều chỉnh `ContainerProperties`, lifecycle hoặc hành vi ở cấp listener container: dùng factory hoặc `ContainerCustomizer`.
- Muốn thay đổi dữ liệu từng record trước/sau listener: xem xét record interceptor hoặc message converter phù hợp.
- Muốn xử lý lỗi nghiệp vụ: cấu hình error handler/retry/recovery phù hợp.

Không nên dùng customizer cho công việc mà một thành phần chuyên biệt đã quản lý tốt hơn.

## 11. Tích hợp ContainerCustomizer với Spring Boot

Spring Boot thường tạo `ConcurrentKafkaListenerContainerFactory` mặc định từ `spring.kafka.*`. Khi cần customizer, có thể khai báo một factory riêng và chọn factory đó ở listener.

Ví dụ:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory = new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();
        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);
        factory.setContainerCustomizer(container -> {
            ContainerProperties properties = container.getContainerProperties();
            properties.setPollTimeout(2_000L);
            properties.setAckMode(ContainerProperties.AckMode.RECORD);
        });
        return factory;
    }
}
```

Listener tham chiếu factory riêng:

```java
@KafkaListener(
        id = "orders-listener",
        topics = "orders",
        groupId = "orders-service",
        containerFactory = "ordersListenerContainerFactory"
)
public void onOrder(OrderCreated event) {
    // ...
}
```

Nếu muốn tùy chỉnh factory mặc định, có thể cấu hình bean theo cách phù hợp với cơ chế auto-configuration của phiên bản Spring Boot đang dùng. Cần kiểm tra điều kiện tạo bean mặc định và tránh vô tình làm mất các cấu hình Boot đã bind từ `application.yml`.

Khi tạo factory riêng, ứng dụng chịu trách nhiệm cấu hình đầy đủ các thành phần cần thiết, ví dụ consumer factory, converter, error handler, transaction manager hoặc các tùy chọn khác mà listener cần. Không giả định factory tự khai báo sẽ tự động nhận mọi thiết lập từ factory mặc định.

## 12. Tác động của cấu hình container tới xử lý record

Customizer có thể tác động gián tiếp tới cách record được tiêu thụ. Ví dụ:

- Đổi `AckMode` làm thay đổi thời điểm commit offset.
- Đổi `pollTimeout` ảnh hưởng thời gian chờ dữ liệu trong poll.
- Đổi idle event interval ảnh hưởng tần suất phát sự kiện idle để quan sát.
- Đổi shutdown timeout ảnh hưởng thời gian chờ container dừng.

Không nên thay đổi acknowledgment mode chỉ để giảm số lần commit mà chưa đánh giá hậu quả khi xử lý lỗi. Với `RECORD`, container commit sau từng record xử lý thành công theo cơ chế đã cấu hình. Với `BATCH`, container commit sau khi xử lý batch theo quy tắc của container. Nếu record lỗi, error handler và recovery quyết định retry, recovery và commit tiếp theo.

Tương tự, tăng poll timeout không làm tăng `max.poll.records` và không tự làm consumer xử lý nhanh hơn. Đây là hai cấu hình thuộc hai tầng khác nhau: một bên là thời gian chờ của container, bên kia là giới hạn số record Kafka client trả về trong một lần poll.

## 13. Kiểm thử ContainerCustomizer

Nên kiểm tra customizer được gắn vào đúng factory và các thuộc tính container nhận giá trị mong muốn. Có thể dùng integration test với Spring context và broker embedded/Testcontainers.

Ví dụ kiểm tra cấu hình container qua registry:

```java
@SpringBootTest
@EmbeddedKafka(partitions = 1, topics = "orders")
class ContainerCustomizerIntegrationTest {

    @Autowired
    private KafkaListenerEndpointRegistry registry;

    @Test
    void shouldApplyContainerCustomizer() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        assertThat(container).isNotNull();
        assertThat(container.getContainerProperties().getPollTimeout())
                .isEqualTo(2_000L);
        assertThat(container.getContainerProperties().getAckMode())
                .isEqualTo(ContainerProperties.AckMode.RECORD);
    }
}
```

Test cần listener có ID `orders-listener` và dùng đúng factory đã đăng ký customizer. Nếu container chạy với concurrency lớn hơn một, cần hiểu rằng registry trả container cha; thuộc tính chung có thể được đọc từ container đó, còn hành vi của consumer con cần được xác minh thêm khi phù hợp.

Các tình huống nên kiểm thử:

- Customizer được gọi khi factory tạo container.
- Listener dùng factory có customizer nhận cấu hình tương ứng.
- Listener dùng factory khác không bị ảnh hưởng ngoài ý muốn.
- Thuộc tính customizer ghi đè giá trị mặc định theo đúng chủ đích.
- Ack mode và xử lý lỗi vẫn cho kết quả commit/retry mong muốn.
- Container shutdown hoàn tất trong giới hạn thời gian đã cấu hình.

Không chỉ kiểm tra giá trị property. Với cấu hình ảnh hưởng đến commit, retry hoặc lifecycle, cần có integration test chứng minh hành vi thực tế của listener.

## 14. Các lỗi thường gặp

**Customizer không được gọi:** listener đang dùng factory khác với factory đã gắn customizer. Kiểm tra thuộc tính `containerFactory` và tên bean.

**Generic type không khớp:** customizer khai báo cho kiểu container khác với factory đang tạo. Dùng kiểu container tương ứng với `ConcurrentKafkaListenerContainerFactory<K,V>`.

**Dùng nhầm ConsumerFactory:** `ContainerCustomizer` không thay đổi bootstrap server hoặc deserializer. Đưa cấu hình đó về consumer factory.

**Cấu hình bị ghi đè:** factory hoặc annotation đặt một giá trị, customizer đặt giá trị khác sau đó. Xác định nguồn cấu hình cuối cùng và kiểm thử.

**Một customizer ảnh hưởng mọi listener:** nhiều listener dùng chung factory nên cùng nhận cấu hình. Tách factory nếu cần hành vi khác nhau.

**Đặt logic nghiệp vụ trong configure:** customizer chạy lúc tạo container, không chạy theo từng record. Chuyển logic nghiệp vụ sang listener hoặc interceptor phù hợp.

**Thực hiện I/O chậm trong customizer:** thời gian khởi tạo container tăng và startup có thể bị trì hoãn. Chỉ cấu hình thuộc tính; chuẩn bị dependency ở lifecycle riêng.

**Cho rằng thay customizer sẽ cập nhật container đang chạy:** customizer chỉ được gọi trong quá trình tạo container. Cần quy trình cập nhật hoặc tạo lại container.

**Tăng poll timeout để giải quyết consumer lag:** poll timeout không thay thế `max.poll.records`, `max.poll.interval.ms` hoặc tối ưu xử lý downstream.

**Chỉ test cấu hình mà không test hành vi:** giá trị cấu hình đúng chưa đảm bảo commit, retry hoặc shutdown hoạt động đúng trong thực tế.

## 15. Checklist thiết kế

- Listener có thực sự cần tùy chỉnh ở cấp container hay cấu hình factory/consumer đã đủ?
- Listener đang dùng đúng `KafkaListenerContainerFactory` có gắn customizer không?
- Kiểu generic của `ContainerCustomizer` khớp kiểu container factory tạo ra không?
- Thuộc tính cần tùy chỉnh thuộc `ContainerProperties` hay Kafka consumer properties?
- Customizer có chỉ làm công việc cấu hình nhanh, xác định và không có I/O nặng không?
- Nhiều listener dùng chung factory có nên nhận cùng thiết lập không?
- Có factory riêng khi các nhóm listener cần cấu hình khác nhau không?
- Có kiểm tra xung đột giữa factory defaults, annotation và customizer không?
- Thay đổi ack mode đã được đánh giá cùng retry, recovery và commit chưa?
- Integration test đã xác minh cấu hình cuối cùng và hành vi container chưa?
- Phiên bản Spring Kafka đang dùng có hỗ trợ các API/setter trong ví dụ không?

`ContainerCustomizer` là điểm mở rộng ở tầng listener container. Dùng nó để hoàn thiện cấu hình container sau khi factory tạo endpoint, giữ cấu hình consumer ở `ConsumerFactory` và giữ logic xử lý ở listener. Khi phạm vi factory rõ ràng và các giá trị ghi đè được kiểm thử, ứng dụng có thể chuẩn hóa hành vi container mà vẫn duy trì cấu hình dễ hiểu.
