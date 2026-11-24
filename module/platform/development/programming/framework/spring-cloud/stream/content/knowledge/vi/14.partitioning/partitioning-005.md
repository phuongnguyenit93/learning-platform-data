# Cấu hình phía nhận với partitioned, instanceCount và instanceIndex

Phân vùng message chỉ phát huy tác dụng khi phía nhận được cấu hình phù hợp với cách producer phân vùng dữ liệu. Trong Spring Cloud Stream, consumer binding có thuộc tính `partitioned`; ứng dụng còn có thể khai báo `instanceCount` và `instanceIndex` để mô tả tổng số instance tham gia xử lý và vị trí của instance hiện tại trong mô hình phân vùng của binder.

Ba thuộc tính này không phải ba cách viết khác nhau của cùng một ý nghĩa. `partitioned` bật chế độ nhận biết phân vùng cho binding. `instanceCount` cho biết có bao nhiêu instance ứng dụng tham gia nhóm xử lý. `instanceIndex` xác định chỉ số của một instance cụ thể. Các instance phải được cấu hình nhất quán để message được chuyển đến đúng nhóm xử lý và không bị bỏ sót hoặc xử lý chồng lặp ngoài dự kiến.

Bài thuộc chương **Phân vùng** của module `SPRING_CLOUD_STREAM`, tập trung vào cấu hình phía nhận trong mô hình hàm `Supplier`/`Function`/`Consumer` và binder cho Kafka, RabbitMQ hoặc Pulsar. Ta sẽ xem cách cấu hình binding, gán chỉ số cho từng replica, mở rộng số instance, xử lý restart và phân biệt cơ chế phân vùng chung với cơ chế phân vùng gốc của từng broker.

## 1. Vì sao consumer cần biết về partition?

Partitioning chia một luồng dữ liệu thành nhiều phần để tăng khả năng xử lý song song. Producer thường chọn partition dựa trên một khóa nghiệp vụ như `orderId`, `customerId` hoặc `accountId`. Các message có cùng khóa có thể được đưa vào cùng partition để giữ thứ tự trong phạm vi khóa đó.

Ở phía nhận, nhiều instance cùng tham gia xử lý một destination và một consumer group. Nếu binder sử dụng mô hình phân vùng của Spring Cloud Stream, consumer cần biết:

- Binding có tham gia luồng partitioned hay không.
- Tổng số instance đang tham gia.
- Instance hiện tại mang chỉ số nào.

Ví dụ có sáu partition và ba instance:

```text
Destination: orders.events

Partition 0 ----+
Partition 1 ----+----> Instance 0

Partition 2 ----+
Partition 3 ----+----> Instance 1

Partition 4 ----+
Partition 5 ----+----> Instance 2
```

Sơ đồ chỉ minh họa việc chia công việc theo instance. Cách broker hoặc binder gán partition thực tế phụ thuộc binder, subscription type, consumer group và cấu hình producer. Không nên suy ra rằng mọi binder đều dùng cùng một thuật toán gán partition.

Nếu producer gửi message theo khóa nhưng consumer không tham gia cùng mô hình phân vùng, ứng dụng vẫn có thể nhận message, nhưng không nhất thiết đạt được cách phân phối hoặc thứ tự mà thiết kế mong muốn. Vì vậy, cần xem cấu hình producer và consumer như hai nửa của cùng một hợp đồng.

## 2. Ba thuộc tính phía nhận

### `partitioned`

`partitioned` là thuộc tính của consumer binding, khai báo rằng binding nhận dữ liệu theo mô hình partitioned. Trong YAML, thuộc tính được đặt dưới `consumer` của binding:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-in-0:
          consumer:
            partitioned: true
```

Giá trị `true` cho binder biết consumer cần tham gia cách xử lý partition-aware mà binder hỗ trợ. Nó không tự tạo thêm partition ở producer, không thay thế consumer group và không tự quyết định số replica đang chạy.

### `instanceCount`

`instanceCount` là tổng số instance của ứng dụng tham gia cùng một mô hình xử lý. Ví dụ ứng dụng triển khai ba replica thì `instanceCount` là `3` trên cả ba replica.

Đây là số instance ứng dụng, không phải số thread xử lý trong một JVM, không phải số partition của topic và cũng không phải số lượng message trong một batch.

### `instanceIndex`

`instanceIndex` là chỉ số của instance hiện tại. Chỉ số thường bắt đầu từ `0` và phải duy nhất trong phạm vi tổng số instance đã khai báo. Với ba instance, các chỉ số hợp lệ là `0`, `1` và `2`.

| Instance | `instanceCount` | `instanceIndex` |
|---|---:|---:|
| Replica A | 3 | 0 |
| Replica B | 3 | 1 |
| Replica C | 3 | 2 |

Các giá trị này phải được truyền riêng cho từng replica. Nếu cả ba replica đều dùng `instanceIndex: 0`, cấu hình không còn mô tả ba instance riêng biệt. Nếu một instance khai báo `instanceCount: 2` trong khi các instance còn lại khai báo `3`, binder có thể tính toán hoặc định tuyến khác nhau giữa các tiến trình.

## 3. Cấu hình consumer binding hoàn chỉnh

Giả sử một ứng dụng có hàm `projectOrder` nhận sự kiện đơn hàng. Binding đầu vào là `projectOrder-in-0`:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderEvent(String orderId, String customerId, String status) {}

@Configuration
class OrderProjectionConfiguration {

    @Bean
    Consumer<OrderEvent> projectOrder(OrderProjection projection) {
        return event -> projection.apply(event);
    }
}
```

Cấu hình chung của ứng dụng:

```yaml
spring:
  cloud:
    function:
      definition: projectOrder
    stream:
      instance-count: ${INSTANCE_COUNT:3}
      instance-index: ${INSTANCE_INDEX:0}
      bindings:
        projectOrder-in-0:
          destination: orders.events
          group: order-projection
          content-type: application/json
          consumer:
            partitioned: true
```

Trong cấu hình này:

- `projectOrder` là function được kích hoạt.
- `projectOrder-in-0` là consumer binding.
- `destination` là luồng message mà binder kết nối.
- `group` xác định nhóm consumer phối hợp xử lý.
- `partitioned: true` khai báo binding nhận theo mô hình partitioned.
- `instance-count` và `instance-index` được lấy từ biến môi trường để mỗi replica có thể nhận giá trị riêng.

`instance-count` và `instance-index` là thuộc tính cấp ứng dụng dưới `spring.cloud.stream`, không đặt bên trong `consumer` của binding. Trong YAML, Spring Boot dùng dạng kebab-case; tên thuộc tính Java thường được viết `instanceCount` và `instanceIndex`.

## 4. Gán chỉ số cho từng replica

Với ba replica, cấu hình môi trường cần có cùng tổng số instance và chỉ số khác nhau:

```text
Replica A:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=0

Replica B:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=1

Replica C:
  INSTANCE_COUNT=3
  INSTANCE_INDEX=2
```

Trong Kubernetes, có thể dùng StatefulSet để có ordinal ổn định cho từng pod, sau đó ánh xạ ordinal sang `INSTANCE_INDEX`. Nếu dùng Deployment với tên pod thay đổi và không có cơ chế cấp chỉ số riêng, không nên gán tất cả pod cùng một giá trị mặc định. Cần một cơ chế điều phối hoặc cấu hình runtime bảo đảm chỉ số duy nhất và nhất quán.

Ví dụ cấu hình trong manifest có thể truyền biến môi trường từ trường ordinal hoặc từ một cơ chế khởi tạo riêng. Cách lấy ordinal cụ thể phụ thuộc nền tảng triển khai; phần quan trọng là mỗi tiến trình phải nhận đúng `INSTANCE_INDEX` của nó và cùng `INSTANCE_COUNT`.

Không nên dùng `INSTANCE_INDEX: 0` làm giá trị mặc định trong production cho mọi replica. Giá trị mặc định hữu ích khi chạy local một instance, nhưng nếu nhiều replica cùng khởi động mà không được cấp biến môi trường, chúng sẽ cùng khai báo index `0`.

## 5. Phối hợp với cấu hình producer

Consumer partitioned chỉ hoạt động đúng khi producer phát message theo cùng quy ước phân vùng. Ví dụ producer dùng `orderId` làm khóa:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          content-type: application/json
          producer:
            partition-key-expression: payload.orderId
            partition-count: 6
```

Ở đây producer chọn khóa từ `payload.orderId` và khai báo số partition dự kiến là `6`. Cấu hình phía nhận cần phù hợp với topology thực tế và cách binder xử lý partition. `partition-count` ở producer không phải `instance-count` ở consumer:

| Thuộc tính | Phía | Ý nghĩa |
|---|---|---|
| `partition-count` | Producer | Số partition mà producer dùng khi tính toán hoặc cấu hình phân vùng |
| `partitioned` | Consumer binding | Khai báo consumer tham gia chế độ nhận phân vùng |
| `instance-count` | Consumer/application | Tổng số instance ứng dụng tham gia |
| `instance-index` | Consumer/application | Chỉ số của instance hiện tại |

Ví dụ sáu partition và ba instance cho thấy mỗi instance có thể xử lý nhiều partition. Không cần số partition bằng số instance. Nếu số partition nhỏ hơn số instance, có thể có instance không được gán partition hoặc không nhận được dữ liệu theo cơ chế broker. Nếu số partition lớn hơn số instance, mỗi instance có thể nhận nhiều partition.

Producer và consumer phải thống nhất destination, group/subscription, số partition và khóa định tuyến. Nếu producer thay đổi cách tạo partition key hoặc số partition, cần đánh giá tác động đến thứ tự và trạng thái dữ liệu hiện có.

## 6. Ý nghĩa của `instanceCount` và `instanceIndex` khi mở rộng

Giả sử hệ thống ban đầu có ba instance, sau đó tăng lên bốn. Với mô hình cần `instanceCount` và `instanceIndex`, các instance phải cùng chuyển sang `instanceCount: 4` và có index `0`, `1`, `2`, `3`.

Không nên chỉ thêm replica thứ tư với `instanceIndex: 3` trong khi ba replica cũ vẫn khai báo `instanceCount: 3`. Trong giai đoạn chuyển tiếp, các instance sẽ không cùng nhìn thấy một mô hình phân vùng. Tùy binder, điều này có thể làm phân phối không nhất quán hoặc để lại partition không được nhận.

Quy trình scale có kiểm soát:

1. Xác định số partition hiện có và khả năng phục vụ của broker.
2. Chọn số instance mới phù hợp với throughput và giới hạn tài nguyên.
3. Cập nhật `instanceCount` nhất quán cho toàn bộ instance tham gia.
4. Cấp `instanceIndex` duy nhất trong khoảng từ `0` đến `instanceCount - 1`.
5. Triển khai theo chiến lược tránh để hai cấu hình không tương thích cùng tiêu thụ lâu dài.
6. Xác minh binding, group, partition assignment và backlog sau khi scale.

Việc giảm số instance cũng cần phối hợp tương tự. Không để hai tiến trình cùng dùng một index trong khi tiến trình cũ vẫn hoạt động. Cần có thời điểm chuyển giao, drain message đang xử lý và xác nhận consumer cũ đã rời nhóm trước khi tái sử dụng index.

## 7. Phân biệt instance với concurrency

`instanceCount` là số tiến trình/replica ứng dụng tham gia. `instanceIndex` là chỉ số của tiến trình hiện tại. `concurrency` thường là số consumer thread hoặc listener song song mà binder tạo trong một tiến trình. Hai khái niệm này không thay thế nhau.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      instance-count: 3
      instance-index: 1
      bindings:
        projectOrder-in-0:
          destination: orders.events
          group: order-projection
          consumer:
            partitioned: true
            concurrency: 2
```

Ứng dụng ở ví dụ là instance số `1` trong tổng số ba instance. Binding còn yêu cầu concurrency `2`, nếu binder hỗ trợ thuộc tính này. Concurrency có thể tạo nhiều consumer hoặc listener trong cùng process; nó không biến process thành hai `instanceIndex` khác nhau.

Tăng concurrency không tự tăng số partition. Nếu topic có ba partition và tổng cộng chín consumer thread trong một group, nhiều thread có thể không được gán partition. Cần xác định giới hạn song song từ partition count, số replica, concurrency và khả năng của binder.

## 8. Khác biệt theo binder

Spring Cloud Stream cung cấp mô hình cấu hình chung, nhưng cơ chế phân phối partition thực tế phụ thuộc broker:

| Binder | Cách phân phối thường gặp | Vai trò của cấu hình phía nhận |
|---|---|---|
| Kafka | Kafka consumer group coordinator phân phối topic partition cho consumer trong cùng group | Group và số consumer/concurrency là trọng tâm; Kafka tự quản lý assignment và rebalance. `instanceIndex` không thay thế cơ chế assignment gốc của Kafka |
| RabbitMQ | Binder có thể triển khai partitioned queue/routing theo topology và thuộc tính instance | `partitioned`, `instanceCount` và `instanceIndex` có thể tham gia việc xác định queue hoặc phần dữ liệu dành cho instance theo cấu hình binder |
| Pulsar | Consumer nhận message qua subscription; cách chia tải phụ thuộc subscription type và key/partition | Subscription type, topic partition và key-shared behavior quyết định phân phối; không giả định `instanceIndex` thay thế assignment của Pulsar |

Với Kafka, nhiều instance dùng cùng consumer group sẽ được Kafka phân phối partition tự động. Khi số instance thay đổi, Kafka thực hiện rebalance. Không cần tự gán partition bằng `instanceIndex` như thể Kafka không có group coordinator. Hãy kiểm tra tài liệu của phiên bản Kafka binder đang dùng để xác định thuộc tính generic nào được áp dụng.

Với RabbitMQ, partitioning có thể được thực hiện qua các queue riêng và routing key. Khi bật partitioned consumer, binder cần biết số instance và index để ánh xạ phần dữ liệu cho đúng instance. Cần kiểm tra tên queue, exchange, binding và topology mà binder tạo ra.

Với Pulsar, subscription type là quyết định quan trọng. `Exclusive`, `Failover`, `Shared` và `Key_Shared` có cách phối hợp consumer khác nhau. Nếu yêu cầu giữ thứ tự theo key, phải chọn kiểu subscription và ordering key phù hợp. `instanceCount`/`instanceIndex` không tự biến một subscription thành Key_Shared.

Do đó, cấu hình generic ở trên là ví dụ cho mô hình partition-aware của Spring Cloud Stream; không sao chép nguyên xi sang mọi binder mà không kiểm tra semantics của binder và phiên bản dependency.

## 9. Consumer group và partition là hai khái niệm khác nhau

Consumer group xác định tập consumer phối hợp chia tải trên một luồng. Partition chia luồng thành các phần có thể xử lý song song. Trong Kafka, group coordinator gán partition cho các consumer trong cùng group. Group khác có thể đọc lại cùng topic độc lập với offset riêng.

Trong các binder khác, khái niệm group có thể được ánh xạ sang queue hoặc subscription. Partitioning có thể được triển khai qua routing key, queue topology hoặc subscription type. Vì vậy, cần phân biệt:

- `group`: tên nhóm tiêu thụ và phạm vi phối hợp.
- `partitioned`: binding có tham gia mô hình nhận dữ liệu phân vùng hay không.
- `instanceCount`: số instance của ứng dụng trong mô hình đó.
- `instanceIndex`: vị trí của instance cụ thể.
- `concurrency`: mức song song consumer bên trong một instance, nếu binder hỗ trợ.

Nếu các replica dùng group khác nhau, chúng có thể nhận các bản sao độc lập của luồng thay vì chia tải chung. Cấu hình `instanceIndex` không sửa được lỗi group bị đặt khác nhau giữa các replica.

## 10. Điều gì xảy ra khi instance restart hoặc mất kết nối?

Một instance có thể bị restart do nâng cấp, lỗi tiến trình hoặc node gặp sự cố. Khi đó, broker/binder sẽ áp dụng cơ chế phục hồi riêng:

- Kafka: consumer rời group hoặc heartbeat hết hạn, partition được rebalance sang consumer còn lại. Offset và cơ chế commit quyết định message nào được đọc lại.
- RabbitMQ: consumer channel đóng, message chưa ack có thể được requeue theo cấu hình; queue và topology partition vẫn cần đúng.
- Pulsar: consumer disconnect, subscription cursor và subscription type quyết định message được giao lại cho consumer còn hoạt động.

`instanceIndex` không tự lưu trạng thái xử lý message và cũng không thay thế offset, acknowledgement hay subscription cursor. Nó mô tả danh tính/vị trí của instance trong cấu hình partition-aware. Việc bảo đảm message không mất hoặc không bị áp dụng hai lần vẫn cần cơ chế giao nhận và consumer idempotent.

Khi restart một instance, hãy bảo đảm index được cấp lại đúng và không có hai process cùng hoạt động với một index nếu mô hình binder yêu cầu index duy nhất. Nếu ứng dụng dùng StatefulSet, ordinal ổn định có thể giúp tái sử dụng index sau khi instance cũ đã dừng hoàn toàn.

## 11. Cấu hình sai thường gặp

| Cấu hình hoặc tình huống | Hệ quả có thể xảy ra | Cách khắc phục |
|---|---|---|
| Tất cả replica có `instance-index: 0` | Nhiều instance cùng khai báo một vị trí | Cấp index duy nhất cho từng replica |
| `instance-count` khác nhau giữa các replica | Các tiến trình tính toán theo mô hình không nhất quán | Dùng cùng tổng số instance trên toàn nhóm |
| Index âm hoặc lớn hơn/equal count | Index nằm ngoài phạm vi hợp lệ | Kiểm tra `0 <= instanceIndex < instanceCount` |
| `partitioned` bị bỏ qua | Binder không bật chế độ consumer partition-aware theo mong muốn | Đặt `consumer.partitioned: true` nếu binder yêu cầu và hỗ trợ |
| Group khác nhau giữa replica | Các instance không còn phối hợp trong cùng một nhóm | Đồng nhất destination và group |
| Producer và consumer khác partition topology | Message có thể phân phối không như dự kiến | Đồng bộ partition count, key và cấu hình binder |
| Tăng replica mà không cập nhật count/index | Một số partition có thể không được gán hoặc mô hình định tuyến không nhất quán | Scale theo quy trình có kiểm soát |
| Nhầm concurrency với instanceCount | Cấu hình số consumer thread thay vì số replica | Quản lý hai thuộc tính riêng |
| Dùng instanceIndex để tự gán Kafka partition | Xung đột với cơ chế group assignment của Kafka | Để Kafka coordinator quản lý assignment; kiểm tra yêu cầu binder cụ thể |

## 12. Kiểm tra cấu hình lúc khởi động

Có thể kiểm tra các giá trị môi trường trước khi khởi tạo consumer để phát hiện cấu hình sai sớm. Ví dụ validator đơn giản:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import jakarta.annotation.PostConstruct;

@Component
class PartitionInstanceConfigurationCheck {

    private final int instanceCount;
    private final int instanceIndex;

    PartitionInstanceConfigurationCheck(
            @Value("${spring.cloud.stream.instance-count:1}") int instanceCount,
            @Value("${spring.cloud.stream.instance-index:0}") int instanceIndex) {
        this.instanceCount = instanceCount;
        this.instanceIndex = instanceIndex;
    }

    @PostConstruct
    void validate() {
        if (instanceCount < 1) {
            throw new IllegalStateException("instanceCount must be positive");
        }
        if (instanceIndex < 0 || instanceIndex >= instanceCount) {
            throw new IllegalStateException("instanceIndex is outside the configured range");
        }
    }
}
```

Validator này chỉ kiểm tra phạm vi số học của hai thuộc tính. Nó không thể xác nhận các replica khác đang dùng index duy nhất hay `instanceCount` giống nhau. Việc đó cần được bảo đảm bởi nền tảng triển khai, service discovery hoặc cơ chế điều phối tập trung.

Trong môi trường production, nên đưa `instanceCount` và `instanceIndex` vào cấu hình được quản lý tập trung hoặc sinh từ metadata của nền tảng. Log giá trị khi khởi động để dễ đối chiếu, nhưng không ghi thông tin bí mật.

## 13. Kiểm thử partition-aware consumer

Kiểm thử nên xác nhận cấu hình của từng instance và kết quả phân phối message:

| Kịch bản | Cách mô phỏng | Điều cần xác minh |
|---|---|---|
| Một instance | `instanceCount=1`, `instanceIndex=0` | Consumer khởi động và nhận message theo cấu hình |
| Ba instance hợp lệ | Count `3`, index `0`, `1`, `2` | Mỗi instance nhận phần dữ liệu phù hợp theo binder |
| Trùng index | Hai instance cùng index `1` | Cấu hình bị phát hiện hoặc hành vi xung đột được ghi nhận |
| Index ngoài phạm vi | Count `3`, index `3` | Validator từ chối cấu hình |
| Count không nhất quán | Hai instance dùng count `2`, một instance dùng count `3` | Deployment validation phát hiện sai lệch |
| Tăng số instance | Chuyển từ ba lên bốn | Partition assignment và backlog ổn định sau scale |
| Instance restart | Dừng một consumer rồi khởi động lại | Message được phục hồi theo semantics broker và index được cấp đúng |
| Producer đổi partition key | Thay key expression hoặc partition count | Kiểm tra thứ tự và phân phối của message mới |
| Broker-specific assignment | Chạy trên đúng Kafka/RabbitMQ/Pulsar | Xác nhận binder thực hiện đúng cơ chế phân vùng thực tế |

Unit test validator không thay thế integration test. Với Kafka, cần quan sát consumer group và partition assignment. Với RabbitMQ, kiểm tra queue, exchange, routing key và consumer thực tế. Với Pulsar, kiểm tra topic, subscription type và consumer assignment. Test binder chỉ kiểm tra abstraction của Spring, không chứng minh đầy đủ topology hoặc thuật toán của broker thật.

## 14. Quan sát và vận hành

Các chỉ số nên theo dõi:

- `instanceCount` và `instanceIndex` của từng replica khi khởi động.
- Số replica thực tế so với số instance đã cấu hình.
- Partition assignment hoặc queue/subscription assignment theo binder.
- Consumer lag, backlog và tuổi message cũ nhất.
- Throughput, thời gian xử lý, retry và số message giao lại.
- Số lần rebalance, consumer disconnect và thời gian phục hồi.
- Phân phối tải giữa các instance để phát hiện instance quá tải hoặc không nhận message.

Nếu một instance không nhận message, kiểm tra group, index, count, partition assignment và backlog trước khi kết luận producer không gửi. Nếu một instance nhận quá nhiều message, xem partition key có phân phối đều không; một khóa quá nóng có thể khiến một partition và instance chịu phần lớn tải.

Log cần có application instance ID, `instanceIndex`, destination, group và partition/queue/subscription identifier nếu binder cung cấp. Tránh đưa ID message hoặc tenant tùy ý thành nhãn metric có cardinality cao.

## 15. Quy trình triển khai đề xuất

Khi cấu hình consumer partitioned:

1. Xác định destination, consumer group và số partition thực tế.
2. Chọn khóa phân vùng ở producer sao cho các message cần giữ thứ tự có cùng key.
3. Xác định binder đang dùng và cách binder thực hiện partition assignment.
4. Bật `consumer.partitioned` khi mô hình binder yêu cầu.
5. Đặt `instanceCount` bằng tổng số replica tham gia cùng mô hình.
6. Cấp `instanceIndex` duy nhất, hợp lệ cho từng replica.
7. Giữ destination, group và count nhất quán giữa các replica.
8. Phân biệt số replica với `concurrency` bên trong mỗi process.
9. Kiểm thử scale up/down, restart, rebalance và lỗi broker.
10. Theo dõi assignment, lag, backlog và phân bố tải sau triển khai.

## 16. Tự kiểm tra

- [ ] Giải thích được vai trò của `consumer.partitioned`.
- [ ] Phân biệt `instanceCount` với số partition và số consumer thread.
- [ ] Giải thích được `instanceIndex` và phạm vi giá trị hợp lệ.
- [ ] Cấu hình được `spring.cloud.stream.instance-count` và `instance-index` bằng biến môi trường.
- [ ] Bảo đảm mọi replica dùng cùng `instanceCount` và index duy nhất.
- [ ] Phân biệt consumer group với partition.
- [ ] Giải thích được vì sao producer partition key và consumer topology phải tương thích.
- [ ] Phân biệt cơ chế assignment gốc của Kafka/Pulsar với mô hình partition-aware của binder.
- [ ] Thiết kế được quy trình scale, restart và kiểm thử cấu hình sai.
- [ ] Biết theo dõi partition assignment, lag và phân bố tải khi vận hành.

## Kết luận

Phía nhận cần được cấu hình theo đúng mô hình phân vùng mà binder hỗ trợ. `consumer.partitioned` khai báo binding tham gia xử lý partitioned; `instanceCount` mô tả tổng số instance và `instanceIndex` xác định vị trí của instance hiện tại. Các replica phải dùng cùng count và index duy nhất, đồng thời phối hợp với destination, group và cách producer chọn partition. Không nhầm số instance với số partition hoặc concurrency. Kafka và Pulsar có cơ chế assignment gốc của broker; RabbitMQ và các binder khác có thể dùng topology riêng. Vì vậy, cần kiểm thử trên đúng binder và quản lý scale/restart có kiểm soát để tránh phân phối sai, bỏ sót hoặc xử lý chồng lặp message.
