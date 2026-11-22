# Admin client và mô hình bất đồng bộ của kết quả quản trị

Ứng dụng Kafka đôi khi cần tạo topic, xem partition và replica, kiểm tra cấu hình broker, thay đổi cấu hình topic hoặc quản lý consumer group. Những thao tác này thuộc nhóm quản trị cluster, khác với việc gửi và nhận record thông thường. Kafka cung cấp Admin API để ứng dụng Java thực hiện các thao tác đó thông qua `AdminClient`.

Điểm quan trọng khi dùng Admin API là lời gọi quản trị thường có mô hình bất đồng bộ. Phương thức như `createTopics()` trả về một đối tượng kết quả ngay sau khi client khởi tạo request; kết quả thực tế được biểu diễn bằng một hoặc nhiều `KafkaFuture`. Ứng dụng cần quyết định khi nào chờ, chờ bao lâu, xử lý lỗi theo từng resource ra sao và đóng client khi hoàn tất.

## 1. AdminClient làm gì?

`AdminClient` là client quản trị Kafka. Nó kết nối tới cluster thông qua `bootstrap.servers`, lấy metadata cần thiết và gửi các request quản trị đến broker phù hợp. Một số nhóm API thường dùng:

| Nhóm thao tác | API tiêu biểu | Mục đích |
|---|---|---|
| Topic | `createTopics`, `deleteTopics`, `describeTopics`, `listTopics`, `createPartitions` | Tạo, xóa, liệt kê và xem thông tin topic, partition |
| Cấu hình | `describeConfigs`, `alterConfigs`, `incrementalAlterConfigs` | Đọc hoặc thay đổi cấu hình broker/topic |
| Cluster | `describeCluster` | Xem cluster ID, broker nodes và controller |
| Consumer group | `listConsumerGroups`, `describeConsumerGroups`, `deleteConsumerGroups`, `listConsumerGroupOffsets` | Kiểm tra group, thành viên và offset đã commit |
| ACL | `describeAcls`, `createAcls`, `deleteAcls` | Quản lý quyền truy cập khi cluster bật authorization |

Admin API cần quyền phù hợp trên cluster. Ví dụ, ứng dụng có thể được phép `describe` topic nhưng không được `create` hoặc `delete` topic. Không nên cấp quyền quản trị toàn cluster cho mọi service chỉ vì service cần kiểm tra metadata.

`AdminClient` không thay thế `KafkaProducer`, `KafkaConsumer` hay `KafkaTemplate`. Nó phục vụ control plane: quản lý tài nguyên và đọc trạng thái cluster. Producer/consumer phục vụ data plane: truyền và xử lý record.

## 2. Tạo và tái sử dụng AdminClient

Có thể tạo client từ `Properties` hoặc `Map` cấu hình. Ví dụ:

```java
Properties props = new Properties();
props.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(AdminClientConfig.CLIENT_ID_CONFIG, "order-service-admin");
props.put(AdminClientConfig.DEFAULT_API_TIMEOUT_MS_CONFIG, "30000");

AdminClient admin = AdminClient.create(props);
```

Các cấu hình thường cần chú ý:

| Cấu hình | Ý nghĩa |
|---|---|
| `bootstrap.servers` | Danh sách broker để client khởi tạo kết nối và lấy metadata |
| `client.id` | Tên nhận diện client trong log và metric phía broker |
| `default.api.timeout.ms` | Thời hạn mặc định cho một thao tác Admin API |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request mạng |
| `retry.backoff.ms` | Khoảng nghỉ giữa các lần retry nội bộ khi gặp lỗi có thể thử lại |
| `security.protocol` và cấu hình SASL/TLS | Cách xác thực và mã hóa kết nối tới cluster |

`request.timeout.ms` và `default.api.timeout.ms` phục vụ hai mức khác nhau. Một thao tác Admin có thể gồm nhiều request hoặc cần retry; thời hạn API là ngân sách tổng cho thao tác, trong khi request timeout giới hạn một request mạng. Nếu đặt API timeout quá ngắn so với thời gian broker thực hiện thao tác, ứng dụng dễ nhận timeout dù cluster đang bận xử lý.

Trong ứng dụng chạy lâu dài, nên tạo một `AdminClient` dùng chung và tái sử dụng. Client có các luồng nền và tài nguyên kết nối; tạo mới cho từng HTTP request hoặc từng record Kafka sẽ gây overhead và làm khó quản lý kết nối. Đóng client khi ứng dụng dừng hoặc khi phạm vi sử dụng kết thúc.

```java
try (AdminClient admin = AdminClient.create(props)) {
    // Thực hiện các thao tác quản trị cần thiết.
}
```

Trong service Spring, thường khai báo `AdminClient` như một bean và đóng bean khi application context shutdown. Không đóng client dùng chung sau mỗi lần gọi API.

## 3. Vì sao kết quả Admin API là bất đồng bộ?

Khi gọi một phương thức như `createTopics()`, client chuẩn bị và gửi request đến cluster. Việc broker xử lý request diễn ra độc lập với luồng gọi của ứng dụng. Thay vì bắt luồng gọi phải chờ ngay, Kafka trả về một result object chứa các future.

Ví dụ:

```java
CreateTopicsResult result = admin.createTopics(List.of(
        new NewTopic("orders", 6, (short) 3)
));

KafkaFuture<Void> topicCreated = result.values().get("orders");
```

Ở đây có hai lớp:

- `CreateTopicsResult` là đối tượng kết quả của toàn bộ lệnh tạo topic.
- `KafkaFuture<Void>` trong `values()` đại diện cho kết quả tạo topic cụ thể.

Lời gọi `createTopics()` trả về không đồng nghĩa topic đã sẵn sàng. Future chỉ hoàn tất khi client nhận được kết quả của thao tác tương ứng hoặc xác định thao tác thất bại/hết thời hạn.

### Chờ kết quả bằng get()

Nếu chương trình cần kết quả ngay tại bước tiếp theo, có thể chờ future:

```java
try {
    topicCreated.get(35, TimeUnit.SECONDS);
    System.out.println("Topic orders đã được tạo");
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    System.err.println("Không tạo được topic: " + cause);
} catch (TimeoutException e) {
    System.err.println("Đã hết thời gian chờ kết quả tạo topic");
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Luồng bị interrupt khi chờ Admin API", e);
}
```

`get()` không có tham số sẽ chờ vô hạn cho đến khi future hoàn tất. Dùng `get(timeout, unit)` giúp giới hạn thời gian chờ của luồng gọi. Trong ứng dụng server, không nên chờ vô hạn vì có thể giữ thread xử lý request hoặc làm nghẽn worker.

### Xử lý callback khi không muốn chặn luồng gọi

`KafkaFuture` hỗ trợ callback qua `whenComplete`. Cách này phù hợp khi ứng dụng có thể tiếp tục công việc khác trong lúc broker xử lý:

```java
CreateTopicsResult result = admin.createTopics(topics);

result.values().forEach((topicName, future) ->
        future.whenComplete((ignored, error) -> {
            if (error == null) {
                logger.info("Created topic {}", topicName);
            } else {
                logger.error("Cannot create topic {}", topicName, error);
            }
        })
);
```

Callback được gọi khi future hoàn tất. Nên giữ callback ngắn; nếu cần xử lý lâu như gọi HTTP, ghi database hoặc chạy quy trình tiếp theo, hãy chuyển công việc sang executor phù hợp. Không dùng callback để thực hiện tác vụ nặng trên luồng hoàn tất của client.

## 4. Một lệnh có thể có nhiều future

Admin API thường nhận danh sách resource. Ví dụ `createTopics()` có thể tạo nhiều topic trong một lần gọi và trả về map future theo tên topic. Các topic không nhất thiết thành công hoặc thất bại cùng nhau.

```java
List<NewTopic> topics = List.of(
        new NewTopic("orders", 6, (short) 3),
        new NewTopic("payments", 3, (short) 3),
        new NewTopic("inventory", 6, (short) 3)
);

CreateTopicsResult result = admin.createTopics(topics);

result.values().forEach((name, future) -> {
    try {
        future.get(30, TimeUnit.SECONDS);
        logger.info("Topic {} created", name);
    } catch (Exception e) {
        logger.error("Topic {} was not created", name, e);
    }
});
```

Có thể dùng `result.all()` để chờ tất cả kết quả như một thao tác tổng hợp. Tuy nhiên, nếu chỉ chờ future tổng hợp, khi một resource lỗi ứng dụng có thể cần quay lại các future riêng để biết topic nào thành công và topic nào thất bại. Với quy trình quản trị nhiều resource, xử lý từng future giúp log, retry và báo cáo chính xác hơn.

Không nên giả định batch API là một transaction nguyên tử. Nếu tạo 3 topic và topic thứ hai lỗi, các topic khác vẫn có thể đã được tạo. Admin API không tự rollback các thay đổi đã thành công.

## 5. Ví dụ tạo topic và kiểm tra kết quả

`NewTopic` mô tả tên topic, số partition, replication factor và các cấu hình tùy chọn. Ví dụ:

```java
NewTopic orders = new NewTopic("orders", 6, (short) 3)
        .configs(Map.of(
                "cleanup.policy", "delete",
                "retention.ms", "604800000"
        ));

CreateTopicsResult createResult = admin.createTopics(List.of(orders));
createResult.values().get("orders").get(30, TimeUnit.SECONDS);

DescribeTopicsResult describeResult =
        admin.describeTopics(List.of("orders"));

TopicDescription description = describeResult
        .topicNameValues()
        .get("orders")
        .get(10, TimeUnit.SECONDS);

logger.info("Topic {} has {} partitions",
        description.name(), description.partitions().size());
```

Replication factor là số replica cho mỗi partition. Ví dụ replication factor 3 yêu cầu cluster có đủ broker phù hợp để đặt ba replica; nếu cluster không đáp ứng, thao tác có thể thất bại với lỗi replication factor. Số partition ảnh hưởng mức song song, ordering theo key và chi phí quản trị. Không nên tạo topic với giá trị tùy tiện chỉ vì API cho phép.

Sau khi topic được tạo, metadata có thể cần một khoảng ngắn để các client khác nhìn thấy qua quá trình refresh metadata. Nếu producer/consumer khác vừa khởi chạy và chưa nhận metadata mới, hãy xử lý lỗi metadata theo timeout/retry phù hợp thay vì coi mọi độ trễ ngắn là topic creation thất bại.

## 6. Đọc thông tin cluster và consumer group

AdminClient có thể truy vấn thông tin cluster:

```java
DescribeClusterResult clusterResult = admin.describeCluster();

String clusterId = clusterResult.clusterId().get(10, TimeUnit.SECONDS);
Node controller = clusterResult.controller().get(10, TimeUnit.SECONDS);
Collection<Node> brokers = clusterResult.nodes().get(10, TimeUnit.SECONDS);

logger.info("Cluster {} has {} brokers; controller={}",
        clusterId, brokers.size(), controller);
```

Các kết quả cluster cũng là future. Một request có thể cung cấp nhiều future độc lập cho cluster ID, controller và broker list. Nếu chỉ cần một trường, chờ đúng future đó thay vì chờ toàn bộ dữ liệu không cần thiết.

Có thể liệt kê consumer group rồi mô tả group cụ thể:

```java
Collection<ConsumerGroupListing> groups = admin
        .listConsumerGroups()
        .all()
        .get(10, TimeUnit.SECONDS);

DescribeConsumerGroupsResult groupResult = admin.describeConsumerGroups(
        List.of("order-service")
);

ConsumerGroupDescription group = groupResult
        .describedGroups()
        .get("order-service")
        .get(10, TimeUnit.SECONDS);
```

Thông tin group giúp điều tra thành viên, trạng thái và coordinator. Offset đã commit có thể đọc qua `listConsumerGroupOffsets()`. Đây là dữ liệu quan sát tại thời điểm truy vấn; group có thể rebalance ngay sau đó. Không dùng kết quả describe như một khóa đồng bộ để điều khiển consumer đang chạy.

## 7. Timeout: phân biệt hết thời gian chờ và thao tác thất bại

Timeout là một trong những điểm dễ xử lý sai nhất khi dùng Admin API. Có ít nhất hai trường hợp cần phân biệt:

1. **Luồng ứng dụng chờ quá thời gian:** `future.get(5, TimeUnit.SECONDS)` ném `TimeoutException` vì caller chỉ cho phép chờ 5 giây.
2. **Admin API hết thời hạn:** thao tác không hoàn tất trong `default.api.timeout.ms` hoặc timeout được đặt trong options của API; future có thể hoàn tất exceptionally với lỗi timeout.

Trong trường hợp thứ nhất, việc caller ngừng chờ không chứng minh broker đã hủy thao tác. Request có thể vẫn đang được xử lý và future có thể hoàn tất sau đó. Trong cả hai trường hợp, timeout không luôn chứng minh thay đổi chưa xảy ra ở cluster: broker có thể đã thực hiện thao tác nhưng phản hồi bị mất hoặc đến muộn.

Vì vậy, với thao tác có thể lặp lại nhưng không hoàn toàn idempotent theo kết quả mong muốn, hãy đọc lại trạng thái trước khi quyết định retry. Ví dụ, nếu `createTopics()` timeout, dùng `describeTopics()` để xác minh topic đã tồn tại chưa và kiểm tra số partition/cấu hình cần thiết. Không chỉ dựa vào exception để kết luận trạng thái cuối cùng.

Các API options thường cho phép đặt timeout riêng, ví dụ:

```java
CreateTopicsOptions options = new CreateTopicsOptions()
        .timeoutMs(20_000);

CreateTopicsResult result = admin.createTopics(
        List.of(new NewTopic("orders", 6, (short) 3)),
        options
);
```

Timeout cần được thiết kế theo thời gian broker thực hiện thao tác, thời gian retry nội bộ, độ trễ mạng và SLA của ứng dụng. `get(timeout)` là giới hạn chờ ở phía caller; `timeoutMs()`/`default.api.timeout.ms` điều khiển ngân sách thời gian của thao tác Admin API.

## 8. Xử lý lỗi theo từng resource

Các lỗi quản trị nên được phân loại theo nguyên nhân:

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `TopicExistsException` | Topic đã tồn tại khi gọi create | Describe topic và xác minh partitions/config; chỉ coi là trạng thái mong muốn nếu khớp yêu cầu |
| `UnknownTopicOrPartitionException` | Topic/partition không tồn tại hoặc metadata chưa ổn định | Kiểm tra tên, trạng thái tạo/xóa và thử lại có giới hạn khi phù hợp |
| `InvalidReplicationFactorException` | Replication factor không thể đáp ứng với cluster | Kiểm tra broker khả dụng và cấu hình yêu cầu |
| `ClusterAuthorizationException` hoặc `TopicAuthorizationException` | Principal không có quyền thao tác | Sửa ACL/role; retry không giải quyết được quyền thiếu |
| `TimeoutException` | Thao tác hoặc caller chờ quá hạn | Đọc lại trạng thái resource trước khi retry |
| `NotControllerException` hoặc lỗi retriable tương tự | Broker xử lý request không còn là controller hoặc cluster đang chuyển trạng thái | Kafka client thường tự retry lỗi retriable trong giới hạn API timeout; theo dõi nếu kéo dài |

`ExecutionException` bọc exception gốc từ future. Khi log, nên ghi `getCause()` để thấy loại lỗi Kafka cụ thể. Đừng bắt mọi exception rồi chỉ ghi “admin operation failed”; thông tin topic, operation, client ID và cause giúp phân biệt lỗi cấu hình, quyền, trạng thái resource và lỗi hạ tầng.

Đối với lệnh tạo topic, `TopicExistsException` không tự động có nghĩa hệ thống đã ở trạng thái mong muốn. Topic tồn tại có thể có số partition, replication hoặc retention khác với yêu cầu. Một quy trình reconcile nên describe và so sánh cấu hình trước khi báo thành công.

## 9. Không chặn luồng xử lý quan trọng

`KafkaFuture.get()` là thao tác blocking đối với thread gọi. Chờ kết quả có thể hợp lý trong startup, migration hoặc command-line tool, nơi bước tiếp theo thật sự phụ thuộc kết quả quản trị. Nhưng nếu gọi `get()` trong HTTP request thread hoặc Kafka listener, thời gian chờ sẽ giữ thread đó.

Trong Kafka listener, chờ Admin API quá lâu có thể làm listener xử lý chậm, tăng consumer lag và thậm chí ảnh hưởng `max.poll.interval.ms` nếu thread không poll đủ thường xuyên. Trong web server, nhiều request cùng chờ Admin API có thể chiếm hết worker pool.

Một số nguyên tắc:

- Dùng callback hoặc chuyển future sang executor khi có thể xử lý tiếp bất đồng bộ.
- Nếu phải chờ, đặt timeout hữu hạn và giới hạn số thao tác quản trị đồng thời.
- Không tạo `AdminClient` mới cho mỗi record hoặc mỗi request.
- Không chạy tác vụ nặng trong callback; dispatch sang executor của ứng dụng.
- Tránh gọi Admin API liên tục để kiểm tra điều kiện có thể theo dõi bằng metric hoặc cache metadata.
- Tách quyền quản trị khỏi service xử lý nghiệp vụ nếu service không cần thay đổi cluster.

## 10. Tích hợp với Spring Kafka

Spring Kafka cung cấp `KafkaAdmin` để khai báo tài nguyên Kafka theo kiểu Spring bean. Khi application context khởi động, `KafkaAdmin` có thể dùng AdminClient bên dưới để kiểm tra và tạo các `NewTopic` bean.

```java
@Configuration
public class KafkaTopicsConfig {

    @Bean
    KafkaAdmin kafkaAdmin() {
        Map<String, Object> configs = new HashMap<>();
        configs.put(AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
                "localhost:9092");
        return new KafkaAdmin(configs);
    }

    @Bean
    NewTopic ordersTopic() {
        return TopicBuilder.name("orders")
                .partitions(6)
                .replicas(3)
                .config(TopicConfig.RETENTION_MS_CONFIG, "604800000")
                .build();
    }
}
```

Đây là cách khai báo topic phù hợp với cấu hình ứng dụng. Spring Kafka có thể tự tạo topic nếu broker cho phép và tài khoản có quyền. Nếu topic đã tồn tại, hành vi mặc định không có nghĩa mọi cấu hình hiện tại sẽ được sửa để khớp với `NewTopic`; việc thay đổi cấu hình cần dùng cơ chế quản trị tương ứng.

Khi cần luồng quản trị động, xử lý nhiều resource, đọc trạng thái chi tiết hoặc phối hợp nhiều bước, có thể inject `AdminClient`/`Admin` trực tiếp như bean. `KafkaAdmin` thuận tiện cho khai báo tài nguyên khi startup; `AdminClient` phù hợp cho logic quản trị chủ động trong ứng dụng hoặc công cụ vận hành.

## 11. Mô hình vận hành và checklist

Một thao tác quản trị an toàn nên có đủ các bước: xác định resource mong muốn, gửi lệnh, quan sát future, xử lý từng kết quả, rồi đọc lại trạng thái nếu thao tác có thể timeout hoặc có kết quả không chắc chắn.

- Tạo và tái sử dụng AdminClient; đóng client khi ứng dụng dừng.
- Cấu hình bootstrap servers, client ID, security và timeout phù hợp.
- Hiểu result wrapper và future theo từng resource; không giả định batch API là transaction nguyên tử.
- Dùng `get(timeout)` khi cần chờ; dùng callback/executor khi cần giữ luồng gọi không bị block.
- Phân biệt timeout ở caller với timeout của Admin API; đọc lại trạng thái trước khi retry thao tác có kết quả chưa rõ.
- Xử lý `ExecutionException` bằng cách kiểm tra cause; log operation, resource và lỗi gốc.
- Kiểm tra quyền tối thiểu cần thiết cho create, describe, alter, delete và ACL.
- Với topic đã tồn tại, describe và so sánh partition/config thay vì chỉ coi `TopicExistsException` là thành công.
- Theo dõi latency, timeout, lỗi theo operation và số lần retry quản trị.
- Không gọi Admin API đồng bộ trong listener hoặc request path nhạy cảm nếu không cần thiết.

AdminClient giúp ứng dụng tự động hóa quản trị Kafka bằng các API có kết quả bất đồng bộ. Hiểu `KafkaFuture`, phạm vi từng resource, timeout và lỗi từng phần giúp ứng dụng biết chính xác thao tác nào đã hoàn thành, thao tác nào cần kiểm tra lại và khi nào nên retry. Đây là nền tảng để xây dựng công cụ provisioning, health check và vận hành Kafka an toàn trong Java/Spring.
