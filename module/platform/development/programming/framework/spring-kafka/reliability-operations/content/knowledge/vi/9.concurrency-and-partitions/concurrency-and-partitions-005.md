# alwaysClientIdSuffix trong Spring Kafka

`alwaysClientIdSuffix` là thuộc tính của `ConcurrentMessageListenerContainer`, dùng để quyết định có luôn thêm hậu tố vào `client.id` của consumer con hay không khi container chạy với concurrency bằng 1.

Khi một concurrent container quản lý nhiều consumer, Spring Kafka cần tạo `client.id` riêng cho từng consumer con để dễ nhận diện metrics, log và hoạt động phía broker. Hậu tố thường có dạng `-0`, `-1`, `-2` theo chỉ số consumer. Khi concurrency lớn hơn 1, hậu tố được thêm để các consumer con có ID riêng. `alwaysClientIdSuffix` điều khiển trường hợp đặc biệt concurrency chỉ bằng 1: giữ hậu tố `-0` hay bỏ nó đi.

Thuộc tính này phục vụ nhận diện và quan sát consumer. Nó không tăng số consumer, không tạo thêm partition, không thay đổi consumer group và không quyết định cách Kafka phân bổ partition.

## 1. Vì sao cần hậu tố client ID?

Một `ConcurrentMessageListenerContainer` có thể quản lý nhiều `KafkaMessageListenerContainer` con. Mỗi child container tạo và điều khiển một Kafka consumer riêng.

Giả sử listener được cấu hình với:

- `clientIdPrefix = "orders-consumer"`
- `concurrency = 3`

Spring Kafka tạo ba consumer. Để phân biệt chúng, client ID có thể là:

| Consumer con | Client ID |
|---:|---|
| 0 | `orders-consumer-0` |
| 1 | `orders-consumer-1` |
| 2 | `orders-consumer-2` |

Nhờ ID riêng, nhóm vận hành có thể nhìn thấy consumer nào đang có lag, consumer nào đang xử lý partition nào và consumer nào có metrics bất thường.

Nếu không có hậu tố, các consumer con có thể dùng cùng một client ID prefix. Điều này làm giảm khả năng phân biệt chúng trong log và metrics, đồng thời có thể làm các chính sách quota theo client ID khó kiểm soát hơn.

## 2. Phân biệt client.id với group.id

Hai thuộc tính này thường xuất hiện cạnh nhau trong cấu hình consumer nhưng có mục đích khác nhau.

| Thuộc tính | Vai trò | Ảnh hưởng chính |
|---|---|---|
| `group.id` | Xác định consumer group | Group membership, partition assignment, committed offset |
| `client.id` | Định danh một Kafka client | Broker logs, metrics và quota theo client ID |
| `clientIdPrefix` | Tiền tố Spring Kafka dùng để tạo client ID | Tên client ID của consumer do container tạo |
| `alwaysClientIdSuffix` | Quyết định có giữ hậu tố khi concurrency bằng 1 hay không | Cách định dạng client ID của child consumer |

Ví dụ:

- Hai consumer có cùng `group.id` có thể tham gia cùng consumer group và chia sẻ trách nhiệm đọc partition.
- Hai consumer có cùng `client.id` không vì thế mà thuộc cùng consumer group.
- Đổi `alwaysClientIdSuffix` không đổi `group.id`, committed offset hoặc quy tắc partition assignment.

Kafka dùng `group.id` để điều phối các consumer cùng nhóm. `client.id` là tên nhận diện client ở tầng giao tiếp với broker. Không dùng client ID thay cho group ID khi thiết kế consumer group.

## 3. alwaysClientIdSuffix hoạt động như thế nào?

`alwaysClientIdSuffix` là thuộc tính của `ConcurrentMessageListenerContainer`. Trong tài liệu Spring Kafka hiện hành, giá trị mặc định là `true`. Khi concurrency bằng 1, giá trị `true` vẫn thêm hậu tố `-0`; đặt `false` sẽ bỏ hậu tố trong trường hợp này.

Khi concurrency lớn hơn 1, Spring Kafka vẫn thêm hậu tố để phân biệt từng consumer con, kể cả khi `alwaysClientIdSuffix` là `false`.

| Concurrency | alwaysClientIdSuffix | Client ID được tạo từ prefix `orders-consumer` |
|---:|---|---|
| 1 | `true` | `orders-consumer-0` |
| 1 | `false` | `orders-consumer` |
| 3 | `true` | `orders-consumer-0`, `orders-consumer-1`, `orders-consumer-2` |
| 3 | `false` | `orders-consumer-0`, `orders-consumer-1`, `orders-consumer-2` |

Có thể nhớ quy tắc như sau:

- Concurrency bằng 1: thuộc tính quyết định có thêm `-0` hay không.
- Concurrency lớn hơn 1: suffix vẫn được thêm để mỗi consumer con có ID riêng.
- Concurrency là số consumer con tối đa mà concurrent container quản lý; suffix không phải số partition.

Thuộc tính `setAlwaysClientIdSuffix(boolean)` có từ Spring Kafka 2.2.14. Khi triển khai trên phiên bản cũ hơn, kiểm tra API tương ứng trước khi sử dụng.

## 4. Cấu hình với @KafkaListener

Với listener được tạo bởi `ConcurrentKafkaListenerContainerFactory`, có thể dùng `ContainerCustomizer` để cấu hình concurrent container sau khi factory tạo nó.

Ví dụ sau đặt concurrency bằng 1 và giữ suffix cho client ID:

```java
@Configuration
public class OrdersKafkaConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            ordersListenerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(1);

        factory.setContainerCustomizer(container ->
                container.setAlwaysClientIdSuffix(true)
        );

        return factory;
    }
}
```

Listener khai báo prefix:

```java
@Component
public class OrdersListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "orders-service",
        clientIdPrefix = "orders-consumer",
        containerFactory = "ordersListenerFactory"
    )
    public void onOrderCreated(OrderCreated event) {
        // Xử lý event
    }
}
```

Với concurrency bằng 1 và suffix được bật, client ID của consumer là `orders-consumer-0`.

`ContainerCustomizer` cho phép chỉnh sửa container sau khi factory đã tạo và cấu hình container. API này có từ Spring Kafka 2.3.4. Nếu dùng phiên bản từ 2.2.14 đến trước 2.3.4, có thể cấu hình trực tiếp trên `ConcurrentMessageListenerContainer` do ứng dụng tự tạo.

Nếu ứng dụng có nhiều listener factory, customizer chỉ áp dụng cho factory được cấu hình. Hãy xác nhận listener có khai báo đúng `containerFactory`.

## 5. Khi nào nên tắt suffix?

Giá trị mặc định `true` thường hữu ích vì giữ quy tắc đặt tên nhất quán giữa các listener chạy với concurrency 1 và listener có concurrency lớn hơn 1.

Có thể tắt suffix nếu một hệ thống giám sát, quota hoặc quy ước vận hành đang phụ thuộc vào client ID không có hậu tố khi chỉ có một consumer.

Ví dụ:

```java
factory.setContainerCustomizer(container ->
        container.setAlwaysClientIdSuffix(false)
);
```

Với concurrency bằng 1 và prefix `orders-consumer`, client ID sẽ là `orders-consumer`.

Nếu sau này concurrency tăng lên 3, các client ID vẫn có hậu tố:

```text
orders-consumer-0
orders-consumer-1
orders-consumer-2
```

Do đó, đặt `false` không có nghĩa là tắt suffix trong mọi trường hợp. Nó chỉ suppress suffix khi concurrency bằng 1.

Không nên tắt suffix chỉ để tên client ID ngắn hơn nếu nhóm vận hành đang dùng suffix để phân biệt metrics hoặc quota. Trước khi đổi, hãy xác định nơi nào đang dựa vào client ID hiện tại.

## 6. Cấu hình container trực tiếp

Nếu không dùng `@KafkaListener` và tự tạo container, có thể gọi setter trực tiếp trên concurrent container:

```java
ContainerProperties containerProperties =
        new ContainerProperties("orders.created");

containerProperties.setClientId("orders-consumer");

ConcurrentMessageListenerContainer<String, OrderCreated> container =
        new ConcurrentMessageListenerContainer<>(
                consumerFactory,
                containerProperties
        );

container.setConcurrency(1);
container.setAlwaysClientIdSuffix(true);
container.setMessageListener(
        (MessageListener<String, OrderCreated>) record -> {
            orderService.process(record.value());
        }
);
```

Trong ví dụ này:

- `ContainerProperties.setClientId("orders-consumer")` đặt prefix cho `client.id`.
- `setConcurrency(1)` tạo một consumer con.
- `setAlwaysClientIdSuffix(true)` giữ hậu tố `-0`.
- Listener được gắn trực tiếp vào container.

Container cần được đăng ký và quản lý vòng đời phù hợp trong Spring, ví dụ khai báo thành bean để Spring quản lý start/stop. Không tạo container thủ công trong một phương thức request rồi bỏ quên việc dừng nó.

## 7. clientIdPrefix được lấy từ đâu?

Spring Kafka có thể nhận prefix từ nhiều vị trí cấu hình. Cần thống nhất một nguồn để tránh khó hiểu khi điều tra client ID thực tế.

### 7.1. Prefix trên @KafkaListener

`@KafkaListener` hỗ trợ thuộc tính `clientIdPrefix`:

```java
@KafkaListener(
    id = "ordersListener",
    topics = "orders.created",
    groupId = "orders-service",
    clientIdPrefix = "orders-consumer"
)
public void listen(OrderCreated event) {
    // ...
}
```

Đây là cách rõ ràng khi mỗi listener có một prefix riêng.

### 7.2. Prefix trên ContainerProperties

Với container được tạo trực tiếp, có thể đặt prefix trên `ContainerProperties`:

```java
ContainerProperties properties =
        new ContainerProperties("orders.created");

properties.setClientId("orders-consumer");
```

Theo tài liệu Spring Kafka, `ContainerProperties.clientId` là prefix cho consumer property `client.id` và có thể override giá trị `client.id` được cung cấp từ `ConsumerFactory`.

### 7.3. Prefix trong consumer factory

Kafka consumer factory cũng có thể nhận `ConsumerConfig.CLIENT_ID_CONFIG` trong properties. Nếu container có client ID prefix riêng, prefix từ container được dùng để tạo client ID theo quy tắc của listener container.

Không nên cấu hình nhiều prefix khác nhau cho cùng một listener mà không xác định rõ thứ tự ưu tiên. Khi cần chẩn đoán, quan sát client ID thực tế từ metrics hoặc log của consumer.

## 8. Mối quan hệ với concurrency và partition assignment

`alwaysClientIdSuffix` thường được nhắc trong chương concurrency vì mỗi consumer con cần một client ID có thể phân biệt. Tuy nhiên, suffix không quyết định concurrency.

Ví dụ topic `orders.created` có 4 partition:

```text
Topic: orders.created
Partitions: 0, 1, 2, 3
Concurrency: 3

orders-consumer-0  -> một hoặc nhiều partition
orders-consumer-1  -> một hoặc nhiều partition
orders-consumer-2  -> một hoặc nhiều partition
```

Partition assignment thực tế do group coordinator và partition assignor quyết định. Không thể kết luận consumer `-0` luôn nhận partition 0; chỉ số suffix là chỉ số child container, không phải partition number.

Nếu concurrency lớn hơn số partition, một số consumer con có thể không được gán partition. Những consumer này vẫn có client ID riêng, nhưng không xử lý record từ topic đó trong assignment hiện tại.

Ví dụ:

| Số partition | Concurrency | Số consumer có thể được gán partition |
|---:|---:|---:|
| 6 | 3 | Tối đa 3 |
| 3 | 3 | Tối đa 3 |
| 2 | 4 | Tối đa 2 |
| 1 | 4 | Tối đa 1 |

Bảng trên giả định chỉ xét một topic và một consumer group; assignment cụ thể còn phụ thuộc subscription, assignor và các topic khác mà consumer cùng subscribe.

Thay đổi `alwaysClientIdSuffix` không làm thay đổi các con số này. Muốn tăng khả năng xử lý song song, cần xem partition count, concurrency, năng lực xử lý và giới hạn dependency.

## 9. Dùng client ID để quan sát và vận hành

Client ID hữu ích khi nhóm vận hành cần xác định consumer nào tạo ra metrics hoặc request đến broker.

Các trường hợp sử dụng:

- Phân biệt metrics của từng consumer con.
- Tìm consumer tương ứng trong broker log.
- Theo dõi request rate và latency theo client.
- Áp dụng hoặc điều tra quota theo client ID.
- Liên hệ consumer con với partition assignment khi điều tra lag.
- So sánh hành vi giữa các child container trong cùng listener.

`ConcurrentMessageListenerContainer.metrics()` cung cấp metrics của các consumer con được nhóm theo client ID. Nhờ đó, nhóm vận hành có thể phân biệt metrics giữa `orders-consumer-0`, `orders-consumer-1` và các consumer khác.

Client ID chỉ là một phần của khả năng quan sát. Khi điều tra một consumer, kết hợp client ID với group ID, topic, partition, offset, host/pod, listener ID và thời điểm xảy ra sự cố.

### Client ID và quota

Kafka có thể áp dụng quota theo client ID. Khi đổi suffix, tên client ID thực tế cũng thay đổi. Nếu broker đang cấu hình quota cho một client ID cụ thể, cần xác nhận quy tắc quota có còn khớp với các ID mới hay không.

Ví dụ, quota đang áp dụng cho `orders-consumer` có thể không áp dụng theo cùng cách cho `orders-consumer-0` nếu broker cấu hình match theo tên client ID chính xác. Cần xem cấu hình quota thực tế và quy tắc match của cluster trước khi thay đổi.

### Client ID và nhiều instance ứng dụng

Suffix chỉ phân biệt các child container bên trong một concurrent container. Nếu ứng dụng chạy trên nhiều pod và mỗi pod dùng cùng prefix, mỗi pod vẫn có thể tạo các ID giống nhau như `orders-consumer-0`.

Nếu cần phân biệt client theo instance, hãy đưa một giá trị ổn định theo deployment instance vào prefix, ví dụ:

```text
orders-consumer-pod-a-0
orders-consumer-pod-b-0
```

Có thể dùng pod name hoặc một định danh instance phù hợp với nền tảng triển khai. Đảm bảo giá trị prefix không thay đổi liên tục ngoài ý muốn, vì điều đó làm metrics bị phân mảnh thành nhiều client ID khác nhau.

## 10. Kiểm tra client ID thực tế

Đừng chỉ suy ra client ID từ cấu hình. Hãy xác nhận giá trị được dùng khi consumer được tạo.

### 10.1. Bật log cấu hình container

Có thể bật log cấu hình container để hỗ trợ kiểm tra lúc khởi động:

```java
factory.getContainerProperties().setLogContainerConfig(true);
```

Log này hữu ích để xác nhận các thiết lập container, nhưng không thay thế việc xem metrics của Kafka consumer.

### 10.2. Xem metrics theo client ID

Với concurrent container, metrics được nhóm theo client ID:

```java
Map<String, Map<MetricName, ? extends Metric>> metrics =
        container.metrics();

metrics.forEach((clientId, clientMetrics) -> {
    log.info(
        "Kafka client id={}, metric count={}",
        clientId,
        clientMetrics.size()
    );
});
```

Kiểu dữ liệu trả về chính xác có thể thay đổi theo phiên bản Kafka client/Spring Kafka. Ví dụ minh họa ý tưởng đọc map metrics; khi biên dịch, dùng đúng generic type của phiên bản dependency đang chạy.

### 10.3. Đối chiếu với broker metrics và log

Khi client kết nối đến broker, kiểm tra các metric hoặc log có gắn client ID. Xác nhận:

- Prefix đúng như cấu hình listener.
- Suffix có hoặc không có theo concurrency và `alwaysClientIdSuffix`.
- Các child consumer trong cùng container có ID riêng khi concurrency lớn hơn 1.
- Client ID không vô tình trùng với một listener khác nếu nhóm vận hành cần phân biệt metrics.
- Quota theo client ID vẫn áp dụng đúng sau thay đổi.

## 11. Những lỗi và hiểu nhầm thường gặp

**Nghĩ rằng alwaysClientIdSuffix là thuộc tính của ContainerProperties.** Thuộc tính này nằm trên `ConcurrentMessageListenerContainer`. Với listener tạo từ factory, dùng `ContainerCustomizer` hoặc cơ chế tùy biến container tương ứng.

**Đặt false và kỳ vọng suffix biến mất khi concurrency lớn hơn 1.** Setter chỉ suppress suffix khi concurrency bằng 1. Với concurrency lớn hơn 1, hậu tố vẫn cần thiết để phân biệt child consumers.

**Cho rằng suffix là partition number.** Suffix biểu thị chỉ số child container, không phải partition được Kafka assign. Partition assignment có thể thay đổi sau rebalance.

**Cho rằng suffix tạo thêm consumer.** `alwaysClientIdSuffix` chỉ thay đổi tên client ID. Số consumer do concurrency quyết định.

**Nhầm client.id với group.id.** Client ID phục vụ nhận diện client; group ID điều khiển membership và offset của consumer group. Đổi một thuộc tính không tự thay đổi thuộc tính còn lại.

**Dùng cùng prefix cho nhiều listener.** Hai listener có thể tạo các client ID giống nhau nếu prefix và suffix index trùng nhau. Chọn prefix riêng khi cần quan sát từng listener.

**Cho rằng suffix phân biệt các pod.** Suffix chỉ phân biệt child consumer trong cùng container. Các pod chạy cùng cấu hình vẫn có thể tạo client ID giống nhau; thêm định danh instance vào prefix nếu cần.

**Đổi suffix mà không kiểm tra quota.** Broker quota có thể dựa trên client ID. Sau khi đổi tên, quota match và cách phân bổ hạn mức có thể thay đổi.

**Cấu hình customizer trên factory không được listener sử dụng.** Xác nhận tên factory trong `@KafkaListener` và kiểm tra client ID runtime.

## 12. Kiểm thử alwaysClientIdSuffix

Nên kiểm thử cả trường hợp concurrency bằng 1 và concurrency lớn hơn 1. Việc chỉ xác nhận listener nhận message không chứng minh suffix được tạo đúng.

Một kịch bản integration test:

1. Khởi chạy Kafka broker dùng cho test.
2. Tạo topic với đủ partition cho concurrency thử nghiệm.
3. Tạo listener container factory có `clientIdPrefix` xác định.
4. Cấu hình concurrency bằng 1 và bật `alwaysClientIdSuffix`.
5. Khởi động container, đợi consumer được tạo và đọc metrics.
6. Xác nhận client ID kết thúc bằng `-0`.
7. Đổi sang `alwaysClientIdSuffix=false`, khởi động lại container và xác nhận suffix bị bỏ khi concurrency vẫn bằng 1.
8. Đặt concurrency bằng 3 và xác nhận các consumer con vẫn có hậu tố `-0`, `-1`, `-2` ngay cả khi thuộc tính là false.
9. Kiểm tra partition assignment riêng để chứng minh suffix không đại diện cho partition.
10. Nếu broker có quota theo client ID, xác nhận quota match đúng với tên client ID sau khi đổi.

Bảng kết quả kỳ vọng:

| Test | Concurrency | alwaysClientIdSuffix | Kết quả kỳ vọng |
|---|---:|---|---|
| A | 1 | true | Một client ID có hậu tố `-0` |
| B | 1 | false | Một client ID không có hậu tố |
| C | 3 | true | Ba client ID có hậu tố `-0`, `-1`, `-2` |
| D | 3 | false | Ba client ID vẫn có hậu tố `-0`, `-1`, `-2` |

Khi đọc metrics, hãy chờ consumer khởi động và kết nối broker. Không kiểm tra map metrics ngay khi tạo factory vì consumer có thể chưa được tạo ở thời điểm đó.

## 13. Chọn cấu hình phù hợp cho production

Giữ suffix bật khi muốn client ID nhất quán và dễ phân biệt giữa các child container. Đây cũng là giá trị mặc định được tài liệu Spring Kafka hiện hành mô tả.

Chỉ tắt suffix ở concurrency bằng 1 khi có lý do vận hành cụ thể, chẳng hạn một hệ thống quota hoặc dashboard hiện tại phụ thuộc vào client ID không hậu tố. Trước khi đổi, kiểm tra broker quota, dashboard, alert và quy ước log.

Nếu cần nhận diện từng consumer qua nhiều pod, hãy kết hợp prefix với định danh instance. Không kỳ vọng suffix nội bộ tự tạo ra ID duy nhất trên toàn cluster.

Khi concurrency thay đổi theo tải hoặc theo cấu hình deployment, hãy kiểm tra client ID thực tế và partition assignment cùng lúc. Suffix giúp quan sát từng consumer; nó không bảo đảm một consumer luôn sở hữu cùng partition sau rebalance.

## 14. Tóm tắt quy tắc cần nhớ

- `alwaysClientIdSuffix` thuộc `ConcurrentMessageListenerContainer`.
- Thuộc tính quyết định việc có thêm suffix khi concurrency bằng 1.
- Giá trị mặc định trong Spring Kafka hiện hành là `true`.
- Với concurrency lớn hơn 1, suffix vẫn được thêm để phân biệt child consumers.
- `clientIdPrefix` cung cấp prefix cho `client.id`.
- `client.id` phục vụ nhận diện, metrics, logs và quota; `group.id` điều khiển consumer group.
- Suffix không phải partition ID và không thay đổi partition assignment.
- Dùng `ContainerCustomizer` từ factory để áp dụng cấu hình cho listener được tạo bởi `@KafkaListener`.
- Thêm định danh instance vào prefix nếu cần phân biệt consumer giữa các pod.

## 15. Tài liệu tham chiếu theo phiên bản

Khi triển khai, đối chiếu tài liệu đúng phiên bản Spring Kafka và Kafka client:

- Spring for Apache Kafka Reference — Listener Container Properties: mô tả `clientId`, `clientIdSuffix` và `alwaysClientIdSuffix`.
- Spring for Apache Kafka Reference — Container Factory: mô tả `ContainerCustomizer` và cách tùy biến container được tạo từ factory.
- Spring Kafka Javadoc — `ConcurrentMessageListenerContainer`: API `setAlwaysClientIdSuffix(boolean)`, `setConcurrency(int)` và metrics của child consumers.
- Apache Kafka documentation — Consumer Config: `client.id`, `group.id` và các thuộc tính consumer.

`setAlwaysClientIdSuffix(boolean)` được cung cấp từ Spring Kafka 2.2.14; `ContainerCustomizer` được cung cấp từ 2.3.4. Ưu tiên phiên bản Spring Kafka do Spring Boot dependency management quản lý và kiểm tra Javadoc tương ứng nếu ứng dụng đang dùng phiên bản cũ.
