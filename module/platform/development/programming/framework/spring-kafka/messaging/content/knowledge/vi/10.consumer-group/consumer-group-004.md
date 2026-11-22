# Group instance id và static membership

Trong consumer group, mỗi consumer thường tham gia group với một định danh thành viên do Kafka cấp. Khi consumer dừng hoặc mất kết nối, group có thể rebalance để phân phối lại partition. Với các ứng dụng chạy nhiều instance và thường xuyên restart theo rolling deployment, những lần rời group ngắn có thể tạo ra rebalance không cần thiết, làm listener tạm dừng và tăng consumer lag.

Kafka hỗ trợ **static membership** thông qua thuộc tính `group.instance.id`. Thay vì chỉ dựa vào member ID tạm thời do coordinator cấp, consumer khai báo một định danh ổn định cho một instance logic. Khi instance khởi động lại trong khoảng thời gian session còn hiệu lực, nó có thể tham gia lại group với danh tính cũ và tiếp tục giữ assignment, giúp tránh một số lần rebalance do restart ngắn hạn.

Static membership hữu ích cho các consumer chạy lâu dài, có danh tính instance ổn định như StatefulSet, VM hoặc worker được định danh theo ordinal. Cơ chế này cần được cấu hình cẩn thận: mỗi instance trong cùng group phải có `group.instance.id` duy nhất, ID phải ổn định qua restart và `session.timeout.ms` cần phù hợp với thời gian phục hồi thực tế.

## 1. Dynamic membership và static membership

Theo dynamic membership thông thường, consumer tham gia group bằng `group.id`; coordinator cấp member ID cho phiên tham gia. Khi một consumer rời group hoặc bị xem là mất kết nối, group có thể rebalance để giao partition cho thành viên còn lại. Nếu một tiến trình được restart ngắn hạn, việc rời và tham gia lại có thể tạo ra một lần rebalance dù instance đó chỉ tạm thời gián đoạn.

Static membership bổ sung `group.instance.id`, một định danh do ứng dụng cung cấp và được giữ ổn định giữa các lần chạy của cùng instance. Coordinator có thể nhận ra đây là thành viên tĩnh đã từng tham gia group. Khi instance bị gián đoạn ngắn, coordinator giữ trạng thái thành viên trong khoảng `session.timeout.ms` thay vì lập tức phân phối lại partition. Nếu instance quay lại đúng hạn với cùng ID, nó có thể tiếp tục tham gia mà không cần một đợt rebalance do restart đó gây ra.

| Tiêu chí | Dynamic membership | Static membership |
|---|---|---|
| Định danh thành viên | Kafka cấp member ID cho lần tham gia | Ứng dụng cung cấp `group.instance.id` ổn định |
| Restart ngắn hạn | Có thể gây rebalance khi member rời và tham gia lại | Có thể giữ assignment trong thời gian session còn hiệu lực |
| Yêu cầu ID ổn định | Không cần ID instance do ứng dụng quản lý | Cần ID duy nhất cho mỗi instance trong cùng group |
| Phát hiện instance chết | Theo heartbeat và session timeout | Cũng dựa trên heartbeat và session timeout; việc thu hồi partition có thể bị trì hoãn tới khi session hết hạn |
| Mở rộng số instance | Thành viên mới tham gia sẽ làm group điều chỉnh assignment | Thành viên tĩnh mới vẫn có thể làm group rebalance để phân phối lại partition |
| Rủi ro cấu hình | Ít nguy cơ trùng ID do ứng dụng quản lý | Trùng `group.instance.id` có thể khiến một thành viên bị fencing |

Static membership không tắt rebalance. Group vẫn cần rebalance khi thêm hoặc xóa partition, thay đổi subscription, thay đổi số thành viên thực tế hoặc khi một static member không quay lại trước khi session timeout hết hạn. Cơ chế này chủ yếu giảm rebalance do gián đoạn ngắn của một instance có danh tính ổn định.

## 2. group.instance.id là gì?

`group.instance.id` là thuộc tính cấu hình của Kafka consumer, có kiểu chuỗi. Khi được đặt, consumer trở thành static member. Giá trị này phải duy nhất trong phạm vi một consumer group đang hoạt động. Hai consumer thuộc cùng `group.id` không được đồng thời dùng chung một `group.instance.id`.

Ví dụ hai worker cùng đọc topic `orders`:

```text
group.id = orders-worker

Instance A: group.instance.id = orders-worker-0
Instance B: group.instance.id = orders-worker-1
Instance C: group.instance.id = orders-worker-2
```

Mỗi instance giữ ID của mình qua các lần restart. Khi instance A khởi động lại, nó dùng lại `orders-worker-0`. Khi scale thêm instance D, instance mới cần một ID chưa được sử dụng, ví dụ `orders-worker-3`.

`group.instance.id` khác `group.id`:

- `group.id` xác định nhóm consumer cùng chia sẻ việc đọc partition và offset đã commit.
- `group.instance.id` xác định một instance cụ thể bên trong group đó.
- Cùng một instance ID có thể được dùng trong group khác vì tính duy nhất được xét theo từng group, nhưng một ID không được chia sẻ giữa hai consumer đang hoạt động trong cùng group.

`group.instance.id` cũng khác `client.id`. `client.id` chủ yếu dùng để nhận diện client trong log, metric và quota; nó không thay thế danh tính static member. Đặt `client.id` giống nhau không tạo static membership, và đặt `group.instance.id` không thay thế `group.id`.

## 3. Vì sao static membership giảm rebalance?

Giả sử một consumer đang giữ partition `orders-0` và `orders-1`. Pod của consumer được restart trong một đợt triển khai. Với dynamic membership, coordinator có thể nhận thấy thành viên rời group và bắt đầu phân phối lại partition. Khi pod mới lên, nó tham gia lại và có thể gây thêm một đợt rebalance.

Với static membership, pod mới dùng lại cùng `group.instance.id`. Coordinator giữ thành viên tĩnh trong thời gian session timeout. Nếu pod mới quay lại trước khi session hết hạn, coordinator nhận ra instance cũ và có thể giữ nguyên assignment. Các consumer còn lại không cần dừng để phân phối lại partition chỉ vì lần restart ngắn này.

Một hệ quả cần tính đến là khi static member đóng consumer một cách bình thường, client không rời group ngay theo cách dynamic member thường làm. Coordinator giữ danh tính và partition của static member cho tới khi session timeout hết hạn hoặc member đó tham gia lại. Điều này có lợi cho rolling restart, nhưng khi scale down hoặc dừng hẳn một instance, partition có thể được giao lại chậm hơn. Vì vậy, static membership cần được thiết kế cùng quy trình triển khai và thời gian failover.

Sơ đồ minh họa:

```text
Dynamic membership
------------------
Consumer chạy
    |
    v
Restart -> member rời group -> rebalance
    |
    v
Consumer mới tham gia -> rebalance/assignment lại

Static membership
-----------------
Consumer chạy với group.instance.id cố định
    |
    v
Restart ngắn -> coordinator giữ member trong session timeout
    |
    v
Instance khởi động lại với cùng ID
    |
    v
Tiếp tục assignment nếu quay lại đúng hạn
```

Đây là lợi ích về tính ổn định của membership, không phải cam kết rằng partition luôn thuộc về một instance trong mọi tình huống. Nếu instance không quay lại kịp, group vẫn phải thu hồi membership và phân phối partition để các consumer còn lại tiếp tục công việc.

## 4. Cấu hình KafkaConsumer thuần

Static membership được bật bằng cách đặt `ConsumerConfig.GROUP_INSTANCE_ID_CONFIG` trong cấu hình consumer:

```java
Properties props = new Properties();
props.put(ConsumerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ConsumerConfig.GROUP_ID_CONFIG, "orders-worker");
props.put(ConsumerConfig.GROUP_INSTANCE_ID_CONFIG, "orders-worker-0");
props.put(ConsumerConfig.SESSION_TIMEOUT_MS_CONFIG, 45_000);
props.put(ConsumerConfig.HEARTBEAT_INTERVAL_MS_CONFIG, 15_000);
props.put(ConsumerConfig.MAX_POLL_INTERVAL_MS_CONFIG, 300_000);
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);
props.put(ConsumerConfig.KEY_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());
props.put(ConsumerConfig.VALUE_DESERIALIZER_CLASS_CONFIG,
        StringDeserializer.class.getName());

KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props);
```

Các import và phần subscribe/poll được lược bớt để tập trung vào static membership. Client và broker cần hỗ trợ thuộc tính này; static membership được giới thiệu trong Kafka 2.3. Hãy dùng Kafka client tương thích với broker và kiểm tra phiên bản thực tế của cluster trước khi bật.

Trong ví dụ, `orders-worker-0` là ID ổn định của instance số 0. Không tạo một UUID ngẫu nhiên mới mỗi lần ứng dụng khởi động, vì coordinator sẽ coi đó là một thành viên khác và lợi ích giữ membership cũ sẽ mất. Cũng không hard-code cùng một giá trị cho mọi replica của deployment.

## 5. Cấu hình trong Spring Boot và Spring Kafka

Spring Kafka dùng Kafka consumer client bên dưới, nên có thể cấu hình static membership qua consumer properties:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
      properties:
        "[group.instance.id]": orders-worker-0
        "[session.timeout.ms]": 45000
        "[heartbeat.interval.ms]": 15000
        "[max.poll.interval.ms]": 300000
```

Spring Boot chuyển các thuộc tính trong `consumer.properties` tới Kafka client. Cú pháp bracket giữ nguyên tên property có dấu chấm trong YAML. Trong môi trường triển khai nhiều instance, giá trị `group.instance.id` cần được cấp riêng cho từng instance thay vì dùng cùng `orders-worker-0` ở mọi pod.

Listener có thể khai báo group ID như bình thường:

```java
@Component
public class OrderListener {

    private final OrderService orderService;

    public OrderListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @KafkaListener(
            id = "ordersListener",
            topics = "orders",
            groupId = "orders-worker")
    public void onMessage(String payload) {
        orderService.handle(payload);
    }
}
```

`groupId` của listener phải khớp với group mà static member tham gia. `group.instance.id` là cấu hình consumer, không phải thuộc tính của message hoặc của từng record.

### Sử dụng concurrency

Một `ConcurrentMessageListenerContainer` có thể tạo nhiều child container, mỗi child sở hữu một KafkaConsumer. Vì mỗi consumer trong cùng group cần `group.instance.id` riêng, không thể để mọi child sử dụng cùng một ID. Các phiên bản Spring Kafka hỗ trợ static membership cho concurrent container có cơ chế thêm hậu tố vào ID gốc cho từng child container để tránh trùng lặp. Ví dụ:

```java
@KafkaListener(
        id = "ordersListener",
        topics = "orders",
        groupId = "orders-worker",
        concurrency = "3")
public void onMessage(String payload) {
    orderService.handle(payload);
}
```

Nếu ID gốc của instance là `orders-worker-pod-0`, các child consumer có thể được tạo với ID riêng theo hậu tố do Spring Kafka quản lý. Hành vi cụ thể phụ thuộc phiên bản Spring Kafka; hãy xác minh cách container tạo ID trước khi triển khai concurrency lớn. Khi tự tạo nhiều `ConsumerFactory` hoặc nhiều listener container, cần bảo đảm mỗi consumer có ID riêng trong group.

## 6. Cấp ID ổn định cho các instance

Một static member cần có danh tính bền vững qua restart. Cách cấp ID phụ thuộc nền tảng triển khai:

| Nền tảng | Cách cấp ID gợi ý | Lưu ý |
|---|---|---|
| Kubernetes StatefulSet | Dùng tên pod/ordinal như `orders-worker-0` | Pod được tạo lại theo cùng ordinal sẽ giữ danh tính; tránh chạy đồng thời hai pod cùng ordinal |
| VM hoặc máy chủ cố định | Dùng tên node hoặc mã instance ổn định | Không tái sử dụng ID cho hai tiến trình cùng group chạy đồng thời |
| Worker có registry | Lưu một ID ổn định trong registry/configuration store | Cần xử lý vòng đời cấp phát và thu hồi ID |
| Deployment với pod name ngẫu nhiên | Cần cơ chế tạo danh tính ổn định riêng | Tên pod mới sau restart thường không giữ được ID cũ |

Ví dụ với Kubernetes StatefulSet, hostname của pod thường chứa tên StatefulSet và ordinal. Có thể truyền biến môi trường vào ứng dụng:

```yaml
env:
  - name: KAFKA_GROUP_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

Sau đó dùng biến môi trường trong cấu hình Spring Boot:

```yaml
spring:
  kafka:
    consumer:
      properties:
        "[group.instance.id]": ${KAFKA_GROUP_INSTANCE_ID}
```

Đây là ví dụ minh họa cách đưa tên pod vào cấu hình. Hãy bảo đảm StatefulSet dùng tên/ordinal ổn định, và nếu concurrency lớn hơn một thì xử lý thêm ID cho từng child consumer theo cơ chế Spring Kafka.

Không dùng một giá trị fallback chung trong production cho nhiều replica. Ví dụ `${KAFKA_GROUP_INSTANCE_ID:orders-worker}` tiện cho chạy local một instance, nhưng nếu nhiều pod cùng thiếu biến môi trường, tất cả sẽ dùng chung ID và gây fencing. Nên để ứng dụng fail fast khi thiếu ID bắt buộc ở môi trường nhiều replica.

## 7. group.instance.id phải duy nhất

Nếu hai consumer đang hoạt động trong cùng group sử dụng cùng `group.instance.id`, coordinator không thể xem chúng là hai static member riêng biệt. Một member có thể bị fencing khi member khác dùng cùng ID tham gia group. Ứng dụng có thể nhận lỗi như `FencedInstanceIdException` hoặc lỗi tương đương tùy phiên bản client/protocol.

Ví dụ cấu hình sai:

```text
group.id = orders-worker

Pod A: group.instance.id = orders-worker
Pod B: group.instance.id = orders-worker   <-- trùng ID
```

Cấu hình đúng cần ID riêng:

```text
group.id = orders-worker

Pod A: group.instance.id = orders-worker-0
Pod B: group.instance.id = orders-worker-1
```

Khi gặp fencing, kiểm tra các instance đang chạy, giá trị cấu hình thực tế và cách tạo ID trong deployment. Không khắc phục bằng cách tạo ID ngẫu nhiên mỗi lần retry vì điều đó che giấu lỗi cấp phát danh tính và có thể để lại static member cũ tồn tại đến khi session timeout hết hạn.

## 8. session.timeout.ms và thời gian phục hồi

`session.timeout.ms` là khoảng thời gian coordinator chờ heartbeat trước khi xem consumer đã mất liên lạc. Với static membership, khi instance tạm thời mất kết nối hoặc restart, partition có thể được giữ lại cho member đó đến khi session timeout hết hạn. Vì vậy, session timeout ảnh hưởng trực tiếp tới khoảng thời gian ứng dụng có thể phục hồi mà không gây rebalance.

| Giá trị session timeout | Tác động |
|---|---|
| Quá ngắn | Restart hoặc sự cố mạng ngắn có thể vượt ngưỡng; group thu hồi member sớm và rebalance |
| Vừa đủ | Cho phép instance khởi động lại trong thời gian dự kiến, đồng thời phát hiện lỗi trong thời gian chấp nhận được |
| Quá dài | Giảm rebalance do gián đoạn ngắn nhưng nếu instance chết hẳn, partition có thể bị giữ lâu trước khi giao cho consumer khác |

Giá trị được broker chấp nhận còn phụ thuộc `group.min.session.timeout.ms` và `group.max.session.timeout.ms`. Client gửi giá trị ngoài khoảng broker cho phép có thể bị từ chối khi tham gia group. `heartbeat.interval.ms` thường được đặt nhỏ hơn `session.timeout.ms`; tài liệu Kafka thường khuyến nghị heartbeat interval không vượt quá khoảng một phần ba session timeout trong cấu hình phổ biến.

Ví dụ `session.timeout.ms=45000` và `heartbeat.interval.ms=15000` tạo cửa sổ session 45 giây. Đây không phải cấu hình bắt buộc cho mọi hệ thống. Hãy đo thời gian startup thực tế, thời gian phục hồi khi broker/network gián đoạn và yêu cầu thời gian failover để chọn giá trị.

## 9. Phân biệt session timeout và max.poll.interval.ms

Hai thuộc tính thường bị nhầm lẫn:

| Thuộc tính | Theo dõi | Khi vượt giới hạn |
|---|---|---|
| `session.timeout.ms` | Heartbeat từ consumer tới group coordinator | Coordinator xem member đã mất liên lạc sau khi hết thời gian chờ |
| `max.poll.interval.ms` | Tiến độ ứng dụng gọi `poll()` | Client được xem là không còn tiến triển trong xử lý; nó ngừng heartbeat/rời group theo semantics của membership |

`session.timeout.ms` phát hiện mất liên lạc; `max.poll.interval.ms` phát hiện consumer không gọi poll kịp. Một consumer có thể vẫn kết nối mạng nhưng listener xử lý batch quá lâu và không poll tiếp. Static membership không làm cho listener được phép xử lý vô hạn.

Với dynamic member, khi vượt `max.poll.interval.ms`, consumer có thể rời group và partition được phân phối lại theo cơ chế thông thường. Với static member, client ngừng gửi heartbeat khi vượt giới hạn poll; coordinator thường giữ membership đến khi `session.timeout.ms` hết hạn rồi mới thu hồi và phân phối lại partition. Điều này giúp giảm rebalance do một số lần gián đoạn ngắn, nhưng cũng có thể kéo dài thời gian phát hiện một instance bị kẹt.

Vì vậy, cần cấu hình cả hai giá trị theo hai mục tiêu khác nhau: `max.poll.interval.ms` phải đủ cho thời gian xử lý tối đa của một chu kỳ poll; `session.timeout.ms` phải đủ cho cửa sổ phục hồi mong muốn và vẫn đáp ứng SLA failover. Kết hợp với `max.poll.records` và timeout của DB/HTTP để tránh listener bị chặn quá lâu.

## 10. Static membership trong rolling deployment và autoscaling

Static membership đặc biệt hữu ích khi triển khai tuần tự các instance có danh tính ổn định. Ví dụ StatefulSet có ba pod `orders-worker-0`, `orders-worker-1`, `orders-worker-2`. Khi cập nhật pod ordinal 1, pod mới có thể dùng lại ID `orders-worker-1`; nếu nó quay lại trước khi session timeout hết hạn, group có cơ hội giữ assignment hiện tại.

Khi scale up, mỗi instance mới cần một ID chưa có trong group. Việc thêm member mới có thể làm group rebalance để phân phối lại partition. Khi scale down, static member đã bị xóa sẽ còn được giữ đến khi session timeout hết hạn; vì vậy partition của nó có thể chưa được giao ngay cho member khác.

Với Deployment có pod name ngẫu nhiên, static membership khó phát huy tác dụng nếu mỗi lần restart tạo một ID mới. Có thể xây dựng cơ chế cấp ID ổn định từ ordinal hoặc registry, nhưng phải xử lý trường hợp instance cũ chưa dừng mà instance mới đã nhận cùng ID. Hai tiến trình cùng dùng ID sẽ gây fencing.

Không nên bật static membership chỉ vì có nhiều replica. Hãy cân nhắc:

1. Instance có danh tính ổn định qua restart hay không.
2. Thời gian restart/rolling update thực tế có nằm trong session timeout hay không.
3. Thời gian chấp nhận được khi instance chết và partition chưa được giao lại.
4. Cách hệ thống cấp ID khi scale up, scale down và thay node.
5. Cấu hình concurrency có tạo nhiều consumer trong cùng group trên một instance hay không.

## 11. Những thay đổi vẫn có thể gây rebalance

Static membership không giữ assignment bất kể điều gì xảy ra. Các tình huống sau vẫn có thể khiến group phải phân phối lại partition:

- Thêm hoặc xóa partition của topic mà group đang subscribe.
- Thay đổi subscription hoặc pattern khiến tập topic được đăng ký thay đổi.
- Thêm static member mới với ID khác vào group.
- Một static member không quay lại trước khi `session.timeout.ms` hết hạn.
- Coordinator hoặc broker thay đổi trạng thái khiến group cần khôi phục membership.
- Thay đổi partition assignor hoặc giao thức group theo cách yêu cầu tính toán assignment lại.

Static membership cũng không bảo đảm consumer giữ đúng partition cũ nếu assignment cần thay đổi vì topology của group đã thay đổi. Hãy coi nó là cơ chế giảm rebalance do restart ngắn hạn, không phải cơ chế pin partition vĩnh viễn.

## 12. Theo dõi và xử lý sự cố

Khi triển khai static membership, nên theo dõi:

- Số lần rebalance và nguyên nhân rebalance theo consumer group.
- Member ID, `group.instance.id` và partition assignment của từng instance.
- Consumer lag trong thời gian rolling deployment và sau khi scale.
- Thời gian khởi động lại thực tế so với `session.timeout.ms`.
- Lỗi `FencedInstanceIdException` hoặc lỗi trùng static member ID.
- Thời gian xử lý listener, số record mỗi poll và tình trạng vượt `max.poll.interval.ms`.
- Số lượng partition chưa được gán lại sau khi một static member ngừng hoạt động.

Có thể kiểm tra trạng thái group bằng Kafka CLI:

```bash
bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group orders-worker
```

Kết quả giúp xem member, client ID, host, partition assignment, current offset và lag. Tùy phiên bản Kafka, công cụ có thể cung cấp thêm thông tin thành viên tĩnh; nếu chưa thấy `group.instance.id`, hãy dùng log consumer hoặc công cụ quản trị tương thích để kiểm tra cấu hình thực tế.

Khi có fencing, trước tiên tìm tất cả tiến trình dùng cùng `group.instance.id` trong group. Khi partition được giao lại chậm sau khi pod chết, kiểm tra session timeout và log heartbeat. Khi rebalance vẫn xảy ra trong rolling deployment, xác nhận pod mới dùng đúng ID của pod cũ, thời gian restart có nằm trong session timeout và không có instance trùng ID chạy đồng thời.

## 13. Các lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `FencedInstanceIdException` | Hai consumer trong cùng group dùng cùng `group.instance.id` | Cấp ID riêng cho từng instance và dừng tiến trình trùng |
| Restart vẫn gây rebalance | ID mới sau restart, startup vượt session timeout hoặc có thay đổi topology | Giữ ID ổn định, đo startup time và kiểm tra nguyên nhân rebalance |
| Partition được giao lại chậm sau khi pod chết | Static member được giữ đến hết `session.timeout.ms` | Điều chỉnh session timeout theo SLA failover |
| Consumer bị loại khi xử lý batch lâu | Vượt `max.poll.interval.ms` | Giảm `max.poll.records`, tối ưu listener và cấu hình poll interval hợp lý |
| Nhiều child consumer có ID giống nhau | Cấu hình concurrency không tạo ID riêng hoặc phiên bản Spring Kafka chưa hỗ trợ cách suffix mong muốn | Kiểm tra phiên bản, ID thực tế của từng child và cấu hình factory |
| Client không tham gia được group | Broker/client không hỗ trợ hoặc session timeout ngoài giới hạn broker | Kiểm tra phiên bản Kafka và `group.min/max.session.timeout.ms` |

## Checklist trước khi đưa static membership vào production

- Broker và Kafka client hỗ trợ `group.instance.id`.
- Mỗi consumer trong cùng group có một `group.instance.id` duy nhất.
- ID được giữ ổn định qua restart của cùng instance.
- ID không bị dùng đồng thời bởi hai tiến trình hoặc hai pod.
- Nếu dùng Spring Kafka concurrency, đã xác minh mỗi child consumer có ID riêng.
- `session.timeout.ms` cân bằng giữa thời gian phục hồi và thời gian failover.
- `heartbeat.interval.ms` nằm trong giới hạn hợp lý và được broker chấp nhận.
- `max.poll.interval.ms` đủ cho chu kỳ xử lý, không bị dùng thay cho session timeout.
- Đã thử rolling restart, scale up, scale down và tình huống instance chết đột ngột.
- Có theo dõi rebalance, lag, static member ID và fencing error.

Static membership giúp consumer group ổn định hơn khi các instance có danh tính cố định bị restart ngắn hạn. Để tận dụng cơ chế này, ứng dụng cần cấp `group.instance.id` duy nhất và bền vững, phối hợp `session.timeout.ms` với thời gian phục hồi, đồng thời giữ `max.poll.interval.ms` phù hợp với thời gian xử lý. Khi triển khai đúng, group giảm được các lần rebalance không cần thiết mà vẫn có thể thu hồi partition khi một instance thực sự không quay lại.
