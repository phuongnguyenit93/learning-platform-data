# Phân bổ nhiều instance và trạng thái đang giữ trong bộ nhớ

> Phạm vi: mở rộng ứng dụng Spring Messaging theo chiều ngang, phân biệt trạng thái cục bộ và trạng thái dùng chung, xử lý kết nối RSocket dài hạn, chia tải consumer và bảo đảm tính đúng đắn khi nhiều instance cùng xử lý message.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao biến trong bộ nhớ của một instance không tự chia sẻ cho instance khác.
- Phân loại trạng thái theo request, connection, session, cache và dữ liệu nghiệp vụ.
- Thiết kế ứng dụng stateless để có thể thêm hoặc bỏ instance an toàn.
- Chọn giữa shared store, cache phân tán, partitioning, sticky connection và replication.
- Hiểu tác động của kết nối RSocket dài hạn, reconnect và session resumption.
- Mở rộng consumer Spring AMQP/Spring Integration mà vẫn kiểm soát ordering, prefetch và duplicate.
- Dùng shared message store và distributed lock khi một quy trình cần trạng thái hoặc quyền sở hữu chung.
- Xử lý idempotency, retry, rolling deployment và instance failure.

## 2. Vì sao trạng thái trong bộ nhớ trở thành vấn đề?

Một Spring Boot application instance có JVM, heap, thread pool, singleton bean, cache và các cấu trúc dữ liệu riêng. Khi triển khai ba instance, hệ thống có ba bản sao độc lập của những vùng nhớ đó.

Ví dụ:

```java
@Service
class ConnectionRegistry {
    private final Map<String, ClientState> clients = new ConcurrentHashMap<>();

    void register(String clientId, ClientState state) {
        clients.put(clientId, state);
    }

    ClientState find(String clientId) {
        return clients.get(clientId);
    }
}
```

Bean `ConnectionRegistry` là singleton trong một Spring ApplicationContext, nhưng singleton chỉ có phạm vi instance/JVM đó. Nếu request đầu tiên được xử lý bởi pod A và request tiếp theo đi tới pod B, map ở B không chứa entry đã lưu ở A.

Tăng số instance làm tăng năng lực xử lý, nhưng cũng làm rõ các giả định sai về local memory. Một hệ thống một node có thể vô tình hoạt động vì mọi request đều thấy cùng một map; khi chạy nhiều node, kết quả trở nên phụ thuộc vào instance nhận request.

Local memory vẫn rất hữu ích cho dữ liệu tạm, cache hoặc state gắn với connection. Điều quan trọng là xác định rõ phạm vi, thời hạn và cách khôi phục của nó.

## 3. Phân loại trạng thái trước khi scale

Không phải mọi state đều cần đưa vào Redis hoặc database. Hãy phân loại trước:

| Loại state | Ví dụ | Phạm vi đúng | Khi instance mất thì sao? |
| --- | --- | --- | --- |
| Request-local | Biến local, DTO, validation result | Một lần xử lý | Có thể bỏ; client retry nếu cần |
| Connection-local | RSocket requester, subscription, connection attributes, flow-control state | Một kết nối đang sống | Kết nối mất; client reconnect và khôi phục theo protocol/ứng dụng |
| Process-local cache | Lookup cache, cấu hình đã load, compiled metadata | Một JVM | Cache được nạp lại; không được là nguồn dữ liệu chuẩn |
| User/session state | Đăng nhập, giỏ hàng tạm, workflow của người dùng | Một user/session qua nhiều request | Phải có nơi lưu chung nếu cần chuyển node hoặc sống qua restart |
| Shared coordination state | Lock, leader, claim, message group, idempotency key | Nhiều instance | Phải được lưu ở hệ thống phối hợp dùng chung |
| Durable business state | Đơn hàng, thanh toán, trạng thái xử lý | Nhiều instance và nhiều phiên bản ứng dụng | Phải được lưu bền vững và phục hồi sau restart |

Một nguyên tắc hữu ích: nếu mất một instance mà dữ liệu đó không thể mất, local memory không thể là nơi lưu duy nhất.

## 4. Stateless instance và horizontal scaling

### 4.1. Mô hình stateless

Một instance stateless không phụ thuộc vào dữ liệu chỉ tồn tại trong bộ nhớ của chính nó để xử lý request tiếp theo. Nó có thể giữ cache cục bộ hoặc dữ liệu tạm, nhưng nguồn dữ liệu có thẩm quyền nằm ở nơi dùng chung hoặc được tái tạo được.

Một luồng xử lý phổ biến:

1. Load balancer chọn một instance khỏe.
2. Instance xác thực request và đọc dữ liệu cần thiết từ database/cache dùng chung.
3. Instance thực hiện nghiệp vụ trong transaction hoặc theo một state machine bền vững.
4. Kết quả được lưu ở shared store.
5. Response trả về client; request kế tiếp có thể tới instance khác.

Với mô hình này, scale-out chủ yếu là thêm instance và cập nhật service discovery/load balancer. Scale-in có thể bỏ một instance sau khi ngừng nhận request mới và hoàn tất các request đang chạy.

### 4.2. Điều gì nên ở local memory?

Có thể giữ trong local memory:

- Cache dữ liệu tham chiếu có thể reload.
- Object được tạo trong một request hoặc một lần xử lý message.
- Buffer và state tạm của một stream đang chạy.
- Connection state gắn với một kết nối cụ thể.
- Circuit breaker, rate limiter local hoặc metric registry có phạm vi process, nếu chấp nhận semantics theo từng instance.

Không nên chỉ giữ trong local memory:

- Trạng thái thanh toán hoặc đơn hàng đã commit.
- Idempotency key cần chống xử lý trùng giữa các instance.
- Session cần tiếp tục sau khi request được chuyển node.
- Trạng thái aggregator/message group phải được nhiều consumer nhìn thấy.
- Lock dùng để bảo đảm một hành động chỉ xảy ra một lần trên toàn cluster.
- Trạng thái workflow phải tồn tại sau rolling restart hoặc crash.

### 4.3. Tránh static map như một distributed store

`static ConcurrentHashMap` chỉ chia sẻ trong một classloader/JVM. Nó không tự chia sẻ qua pod, container hoặc máy khác. Static map cũng không giải quyết persistence, eviction, memory bound, schema migration hoặc đồng bộ.

Nếu dùng local cache, đặt TTL/maximum size, theo dõi hit rate và xác định cách invalidation. Với dữ liệu thay đổi ở node khác, cache cục bộ có thể stale. Chọn TTL, event invalidation hoặc version check theo yêu cầu nhất quán.

## 5. Chọn nơi lưu trạng thái dùng chung

| Nhu cầu | Lựa chọn thường gặp | Đặc tính cần cân nhắc |
| --- | --- | --- |
| Dữ liệu nghiệp vụ cần transaction và durability | Relational database | Transaction, constraint, optimistic locking, backup và schema migration |
| Session hoặc ephemeral shared state | Redis hoặc distributed cache | TTL, eviction, persistence mode, failover và consistency |
| Message group/aggregator state | Spring Integration `MessageGroupStore` dùng JDBC/Redis hoặc store phù hợp | Correlation, expiry, cleanup, lock và query pattern |
| Coordination/critical section | Database lock, RedisLockRegistry, ZooKeeper hoặc hệ thống coordination | Lease, TTL, owner, fencing, failover và lock expiry |
| Event history và replay | Durable message log/event store | Retention, partition key, ordering và consumer offset |
| File hoặc payload lớn | Object storage | Object version, checksum, access control và lifecycle |

Không chọn Redis chỉ vì nó nhanh. Dữ liệu nào cần transaction nhiều record, ràng buộc uniqueness hoặc lịch sử bền vững thường phù hợp với database. Cache chỉ là bản sao có thể tái tạo; không dùng cache làm nguồn chuẩn nếu hệ thống không có kế hoạch xử lý eviction hoặc mất cache.

### 5.1. Session dùng chung với Spring Session

Nếu ứng dụng WebFlux cần `WebSession` dùng chung qua nhiều instance, Spring Session có thể lưu session trong Redis:

```java
@Configuration
@EnableRedisWebSession
class SessionConfiguration {
}
```

Cần cấu hình `ReactiveRedisConnectionFactory` phù hợp và dependency Spring Session Redis tương thích với phiên bản Spring Boot. Sau khi bật, Spring Session cung cấp `WebSession` backed by Redis thay cho session store cục bộ của web server.

Với Servlet stack, Spring Session có integration tương ứng cho `HttpSession`. Hai integration này giải quyết HTTP session. Chúng không tự động biến state của một RSocket connection hoặc `@ConnectMapping` thành state chia sẻ. Nếu RSocket chạy qua WebSocket, session của HTTP handshake và state của RSocket connection vẫn là hai phạm vi cần thiết kế rõ.

Một session dùng chung cần có timeout, serialization ổn định, namespace và chính sách thu hồi. Khi nhiều instance cùng đọc/ghi một session, hãy xác định cách xử lý update đồng thời và flush mode.

### 5.2. Shared message group trong Spring Integration

Các component như aggregator và resequencer có thể giữ trạng thái nhóm message. Nếu mỗi instance dùng một `SimpleMessageGroupStore` trong memory, mỗi node chỉ nhìn thấy phần group nó đã nhận.

Khi cần group state dùng chung, dùng một persistent `MessageGroupStore` như JDBC-backed store hoặc Redis-backed store, và cấu hình các instance dùng cùng backend cùng namespace/table prefix. Spring Integration cung cấp `JdbcMessageStore` cho message/group state và các implementation Redis phù hợp.

Một shared store cho phép nhiều instance nhìn thấy cùng group state, nhưng không tự giải quyết mọi race condition. Khi nhiều node có thể cập nhật cùng group, cần phối hợp lock, transaction hoặc cơ chế claim phù hợp.

## 6. RSocket connection và load balancing

### 6.1. Một RSocketRequester gắn với một kết nối

`RSocketRequester` cung cấp API để thực hiện request trên một `io.rsocket.RSocket`. Khi tạo bằng `RSocketRequester.builder().tcp(...)` hoặc `.webSocket(...)`, kết nối được thiết lập khi có request đầu tiên và được tái sử dụng cho các request tiếp theo.

Điều này có nghĩa một requester thông thường là một kết nối tới một server endpoint. Nếu load balancer chọn pod A khi TCP/WebSocket connection được thiết lập, các request multiplexed trên connection đó tiếp tục đi tới pod A. Load balancer không chọn pod mới cho từng message trên cùng một TCP/WebSocket connection.

### 6.2. Cân bằng tải tại thời điểm tạo kết nối

Với RSocket TCP, có thể đặt L4 load balancer trước các server instance hoặc dùng service discovery để chọn endpoint khi tạo connection. Với RSocket qua WebSocket, HTTP/WebSocket load balancer chọn backend trong handshake; kết nối WebSocket sau đó tồn tại với backend đã chọn.

Spring Cloud LoadBalancer cung cấp abstraction chọn service instance, gồm các implementation round-robin và random. Tuy nhiên, `RSocketRequester.Builder` không tự động trở thành load-balanced requester chỉ vì thêm dependency Spring Cloud LoadBalancer. Nếu muốn chọn instance bằng service discovery ở phía client, ứng dụng cần tích hợp việc chọn `ServiceInstance`, quản lý connection/pool và xử lý reconnect.

Một chiến lược có thể là tạo pool các RSocketRequester, mỗi requester nối tới một instance đã chọn. Khi mượn requester từ pool, cân nhắc tải hiện tại, số connection, health, timeout và chính sách loại bỏ connection lỗi. Không tạo connection mới cho từng message nếu mục tiêu là tận dụng multiplexing.

### 6.3. Sticky sessions và connection affinity

Connection affinity tự nhiên xuất hiện với TCP và WebSocket vì một kết nối tồn tại trên một backend. Sticky session ở HTTP layer có thể giúp các request HTTP liên quan quay về cùng node, nhưng không thay thế shared state.

Ưu điểm của affinity là state cục bộ gắn với connection có thể tiếp tục được tìm thấy khi request đi qua cùng connection. Nhược điểm:

- Khi node chết, state local mất cùng connection.
- Rolling deployment có thể buộc client reconnect sang node khác.
- Một node có thể nóng hơn các node còn lại nếu một số client có connection lâu và traffic không đều.
- Không giải quyết request từ một client khác hoặc background worker cần truy cập cùng state.

Dùng affinity khi cần thiết cho connection-local state hoặc tối ưu cache, nhưng state quan trọng vẫn phải có cơ chế phục hồi.

### 6.4. RSocket session resumption

RSocket có extension session resumption để phục hồi kết nối sau một số trường hợp mất mạng. Resumption cần trạng thái protocol được giữ lại ở hai đầu. Nó không phải cơ chế tự động di chuyển connection sang bất kỳ pod nào.

Nếu connection reconnect tới instance khác, instance mới phải có state resumption phù hợp mới có thể tiếp tục session. Không giả định state đó được chia sẻ giữa các instance chỉ vì chúng cùng chạy một ứng dụng Spring. Hãy kiểm tra khả năng của RSocket Java version, transport, resume store và topology; nếu không đáp ứng được, thiết kế reconnect mới ở tầng ứng dụng.

Khi reconnect ở tầng ứng dụng, client có thể xác thực lại, tạo requester mới, đăng ký lại subscription và lấy trạng thái nghiệp vụ từ shared store. Các command chưa biết đã được xử lý hay chưa cần idempotency key.

## 7. Mở rộng consumer của message broker

### 7.1. Competing consumers

Với broker hỗ trợ queue và competing consumers, nhiều consumer trên nhiều instance có thể đọc từ cùng một queue. Broker phân phối message cho consumer đang đăng ký, giúp tăng năng lực xử lý tổng thể.

Một cách triển khai Spring AMQP là chạy cùng `@RabbitListener` trên mọi instance và cấu hình concurrency:

```java
@RabbitListener(queues = "orders")
public void handle(OrderMessage message) {
    orderService.process(message);
}
```

Ví dụ cấu hình listener container:

```java
@Bean
SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    var factory = new SimpleRabbitListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    factory.setConcurrentConsumers(2);
    factory.setMaxConcurrentConsumers(8);
    factory.setPrefetchCount(20);
    return factory;
}
```

Đây là cấu hình minh họa. Khi thêm nhiều application instance, tổng consumer là tổng concurrency của các listener container trên tất cả instance. Cần tính tổng số consumer, channel, connection và khả năng xử lý của broker cùng database downstream.

### 7.2. Prefetch và bộ nhớ

Prefetch là số delivery chưa ACK mà broker có thể gửi trước cho một consumer. Prefetch cao có thể tăng throughput khi handler nhanh, nhưng cũng làm nhiều message nằm trong bộ nhớ client và có thể làm phân phối không đều.

Spring AMQP có default prefetch 250 từ version 2.0; giá trị này có thể cần giảm khi message lớn, xử lý chậm hoặc cần ordering nghiêm ngặt. Với nhiều consumer, prefetch 1 giúp phân phối công việc sát hơn nhưng có thể giảm throughput do tăng round trip/idle time.

Hãy benchmark theo kích thước message, thời gian xử lý, số consumer và số message in-flight. Prefetch là số message chứ không phải giới hạn byte, nên message lớn có thể làm memory tăng nhanh.

### 7.3. Ordering và partitioning

Khi có nhiều consumer xử lý song song, không nên giả định thứ tự hoàn tất bằng thứ tự publish. Hai message cùng entity có thể được giao cho hai consumer khác nhau và xử lý với thời gian khác nhau.

Nếu cần thứ tự theo một key như `accountId` hoặc `orderId`, hãy dùng partition/shard theo key hoặc một cơ chế single-consumer cho partition đó. Mọi message cùng key cần đi qua cùng partition/serial executor để giữ thứ tự cần thiết.

Partitioning có trade-off: key phân bố lệch sẽ tạo hot partition; một partition thường giới hạn concurrency của key đó. Không cần ordering toàn cục nếu nghiệp vụ chỉ cần ordering theo aggregate key.

### 7.4. Scale listener không làm shared state tự động

Nếu listener dùng `HashMap` để giữ trạng thái tổng hợp, mỗi consumer instance có một map riêng. Cùng một group message có thể bị chia giữa nhiều node và không instance nào nhìn thấy toàn bộ group.

Dùng persistent shared `MessageGroupStore` hoặc partitioning để bảo đảm các message cùng group được xử lý theo một chiến lược nhất quán. Với aggregator, cần thêm lock/claim để ngăn hai instance cùng release hoặc cập nhật một group đồng thời.

## 8. Coordination giữa nhiều instance

### 8.1. Local lock không phải distributed lock

`synchronized`, `ReentrantLock` hoặc Spring Integration `DefaultLockRegistry` chỉ phối hợp thread trong cùng JVM/component. Hai instance có hai lock object độc lập; cả hai có thể cùng vào critical section.

Khi cần exclusive access trên toàn cluster, dùng cơ chế distributed coordination dựa trên shared backend, ví dụ database lock, Redis, ZooKeeper hoặc service coordination phù hợp.

Spring Integration cung cấp `LockRegistry` abstraction với các implementation như JDBC, Redis và ZooKeeper. `RedisLockRegistry` có thể phối hợp các instance khi dùng cùng Redis backend và cùng lock key.

### 8.2. Ví dụ LockRegistry

```java
@Service
class ReconciliationService {

    private final LockRegistry lockRegistry;

    ReconciliationService(LockRegistry lockRegistry) {
        this.lockRegistry = lockRegistry;
    }

    void reconcile(String accountId) {
        Lock lock = lockRegistry.obtain("reconcile:" + accountId);
        if (!lock.tryLock()) {
            return;
        }
        try {
            performReconciliation(accountId);
        } finally {
            lock.unlock();
        }
    }

    private void performReconciliation(String accountId) {
        // Read and update durable state using a transaction.
    }
}
```

Bean `LockRegistry` phải được cấu hình với implementation phù hợp. Nếu dùng `DefaultLockRegistry`, đoạn code chỉ khóa trong một JVM. Muốn khóa xuyên instance, hãy inject `RedisLockRegistry`, `JdbcLockRegistry` hoặc implementation distributed tương ứng.

### 8.3. TTL, lease và fencing

Distributed lock thường có TTL để lock tự hết hạn nếu process chết. TTL quá ngắn có thể hết hạn khi chủ lock vẫn đang chạy; một instance khác lấy lock và cả hai cùng thực hiện side effect. TTL quá dài làm phục hồi sau crash chậm.

Đối với thao tác quan trọng, cần xem xét fencing token hoặc version tăng đơn điệu. Storage đích chỉ chấp nhận thao tác từ token mới nhất, tránh một process cũ tiếp tục ghi sau khi lease đã hết hạn.

Không dùng distributed lock để thay thế transaction hoặc constraint của database. Nếu có thể, bảo vệ invariant bằng unique constraint, optimistic version hoặc atomic update ở nơi lưu dữ liệu chuẩn. Lock chỉ là một lớp coordination bổ sung.

### 8.4. Singleton job và leader election

Nếu một scheduled task chỉ được chạy trên một node, `@Scheduled` trên mọi instance sẽ chạy nhiều lần. Các lựa chọn gồm:

- Thiết kế task idempotent và cho phép mọi node chạy nếu thao tác có thể phân tán.
- Dùng distributed lock/leader election để chỉ một node giữ quyền chạy.
- Dùng scheduler hoặc workflow engine có persistence và ownership rõ ràng.

Nếu dùng lease/lock, cần xử lý node chết, TTL, renew, clock, fencing và trường hợp task chạy lâu hơn lease. Không dựa vào boolean `isLeader` trong local memory làm nguồn chân lý cho cả cluster.

## 9. Idempotency và xử lý message trùng

Khi scale nhiều instance, retry và redelivery là chuyện bình thường. Consumer có thể hoàn tất side effect nhưng chết trước khi ACK; broker giao lại message cho instance khác. Vì vậy, không giả định một message chỉ được xử lý đúng một lần.

Một mẫu idempotency:

1. Producer tạo `messageId` hoặc `idempotencyKey` ổn định cho một thao tác logic.
2. Consumer mở transaction và ghi key vào inbox/dedup table có unique constraint.
3. Nếu key đã tồn tại và đã xử lý, consumer không thực hiện side effect lần nữa.
4. Nếu chưa tồn tại, consumer cập nhật business state và ghi kết quả xử lý trong cùng transaction.
5. Sau commit, consumer ACK message.

Ví dụ schema:

```sql
CREATE TABLE processed_message (
    message_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Unique constraint là lớp bảo vệ cuối cùng khi hai instance đồng thời nhận cùng message. Nếu dedup record và business update nằm ở hai hệ thống khác nhau, cần thiết kế consistency/retry rõ ràng.

Với producer, transactional outbox giúp ghi business change và event-to-publish trong cùng database transaction. Một publisher riêng đọc outbox và gửi message; publisher có thể gửi trùng nên consumer vẫn cần idempotency.

## 10. Cache giữa nhiều instance

Local cache giúp giảm latency nhưng mỗi instance có thể giữ một giá trị khác nhau. Có ba chiến lược phổ biến:

| Chiến lược | Cách hoạt động | Trade-off |
| --- | --- | --- |
| Shared cache | Mọi instance đọc/ghi cùng Redis hoặc cache server | Network hop và cache backend trở thành dependency chung |
| Local cache + TTL | Mỗi node cache riêng trong thời gian ngắn | Có thể stale trong khoảng TTL |
| Local cache + invalidation event | Một node phát event để node khác evict/update | Cần xử lý event mất, duplicate, thứ tự và reconnect |

Cache invalidation event nên mang key hoặc version, không nên chỉ phát một object state có thể cũ. Nếu event bị mất, TTL hoặc periodic refresh phải đưa cache về trạng thái đúng.

Không cache authorization decision lâu hơn vòng đời quyền nếu việc thu hồi quyền phải có hiệu lực nhanh. Cần xác định TTL và invalidation cho dữ liệu bảo mật.

## 11. Failure, reconnect và rolling deployment

### 11.1. Khi một instance chết

Một instance có thể chết do OOM, crash, node failure, deployment hoặc bị health check loại khỏi load balancer. Hệ thống cần bảo đảm:

- Request mới được chuyển tới instance khỏe.
- Request đang chạy có timeout/cancel rõ ràng.
- Message chưa ACK có thể được broker giao lại.
- Local cache/connection state được tái tạo hoặc khôi phục.
- Shared business state không bị mất.
- Retry không tạo side effect trùng.

### 11.2. RSocket reconnect

Client cần có chiến lược reconnect với exponential backoff và jitter, giới hạn số lần thử hoặc thời gian retry, xác thực lại khi cần và tái đăng ký subscription. Khi tạo connection mới, load balancer có thể chọn instance khác; vì vậy mọi state cần tiếp tục phải được khôi phục từ shared store hoặc protocol resume state đã được hỗ trợ.

Không retry mọi request một cách mù quáng. Nếu request trước có thể đã được xử lý nhưng response bị mất, client cần idempotency key hoặc truy vấn trạng thái trước khi gửi lại command.

### 11.3. Graceful shutdown

Trong rolling deployment:

1. Đánh dấu instance không nhận kết nối/request mới theo cơ chế readiness/draining.
2. Ngừng nhận delivery mới hoặc dừng listener theo lifecycle phù hợp.
3. Hoàn tất request/handler đang chạy trong timeout cho phép.
4. ACK những message đã xử lý thành công; để message chưa hoàn tất được redeliver.
5. Đóng RSocket connection, channel, executor và resource có thứ tự.
6. Nếu không thể hoàn tất trước deadline, dừng có kiểm soát và dựa vào idempotency khi retry.

Không xóa state dùng chung chỉ vì một instance đang shutdown; cleanup cần dựa vào TTL, owner/lease hoặc trạng thái workflow.

## 12. Ví dụ kiến trúc

Một hệ thống Spring Messaging có thể chia thành các phần:

```text
                 +----------------------+
Client ----------> Load Balancer / Edge |
                 +----------+-----------+
                            |
              +-------------+-------------+
              |             |             |
         +----v----+   +----v----+   +----v----+
         | App A   |   | App B   |   | App C   |
         | local   |   | local   |   | local   |
         | cache   |   | cache   |   | cache   |
         +----+----+   +----+----+   +----+----+
              |             |             |
              +-------------+-------------+
                            |
              +-------------+-------------+
              | Shared DB / Redis / Store |
              +---------------------------+

              +---------------------------+
              | Message Broker / Queue    |
              +-------------+-------------+
                            |
                 consumers across A/B/C
```

App A/B/C xử lý request stateless, giữ cache local có thể tái tạo và dùng shared store cho session/workflow/business state. Broker phân phối message cho consumer trên các node. Database là nguồn dữ liệu nghiệp vụ chuẩn; Redis hoặc coordination service giữ state phù hợp với semantics của nó.

## 13. Cách chẩn đoán lỗi khi scale

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Login thành công ở node A nhưng node B coi là anonymous | Session chỉ nằm trong memory của A | Kiểm tra session repository, cookie/session id và shared store |
| Client RSocket hoạt động đến khi pod bị restart | State hoặc connection chỉ tồn tại trong process | Kiểm tra reconnect, resubscribe và state recovery |
| Một message group bị xử lý thiếu phần tử | Group state nằm trong local MessageGroupStore | Dùng persistent shared MessageGroupStore hoặc partition key |
| Hai node cùng chạy một job | Chỉ dùng `synchronized`/local lock | Dùng distributed coordination hoặc thiết kế idempotent |
| Consumer throughput không tăng khi thêm pod | Bottleneck nằm ở broker, database, hot partition hoặc prefetch | Đo consumer capacity, downstream pool, queue depth và key skew |
| Message cùng order hoàn tất sai thứ tự | Nhiều consumer xử lý song song hoặc prefetch cao | Partition theo aggregate key, giới hạn concurrency phù hợp |
| Duplicate side effect sau retry | Consumer không idempotent hoặc ACK sau side effect bị lỗi | Dùng inbox/dedup key, transaction và kiểm thử redelivery |
| Một node có tải cao hơn nhiều | Connection lâu dài bị dồn vào một backend hoặc key partition nóng | Theo dõi connection count, traffic/instance và phân bố key |
| Redis lock hết hạn trong lúc job vẫn chạy | TTL quá ngắn hoặc process bị pause | Kiểm tra lease renewal, fencing token và thời gian critical section |

## 14. Checklist trước khi triển khai nhiều instance

- [ ] Đã phân loại request-local, connection-local, cache, session, coordination và durable business state.
- [ ] Không dùng local map/static field làm nguồn chân lý cho state cần chia sẻ.
- [ ] Business state được lưu ở database hoặc store có durability phù hợp.
- [ ] Session dùng chung có repository, TTL, serialization và namespace rõ ràng.
- [ ] RSocket connection được xem là long-lived và gắn với một backend tại thời điểm connect.
- [ ] Có kế hoạch load balancing cho connection mới, connection pool và reconnect.
- [ ] Không giả định Spring Cloud LoadBalancer tự động load-balance `RSocketRequester`.
- [ ] RSocket session resumption được kiểm tra theo implementation và topology thực tế.
- [ ] Message group/aggregator state được lưu dùng chung nếu nhiều instance cùng xử lý một group.
- [ ] Distributed lock dùng backend chung; TTL, renewal và fencing được xem xét.
- [ ] Consumer concurrency, prefetch, ordering và memory được benchmark.
- [ ] Có idempotency/deduplication cho retry và redelivery.
- [ ] Cache local có TTL/invalidation và không giữ quyền truy cập đã hết hiệu lực.
- [ ] Readiness, draining, graceful shutdown và reconnect đã được kiểm thử.
- [ ] Dashboard có metric theo từng instance và metric tổng hợp của cluster.

## 15. Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, shared connection, SETUP, session resumption và interaction models.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): service instance selection, round-robin/random, same-instance preference và sticky session capabilities.
- [Spring Session — WebSession Integration](https://docs.spring.io/spring-session/reference/web-session.html): chia sẻ WebFlux WebSession qua repository như Redis.
- [Spring Session — Redis Configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html): serialization, namespace, flush mode và session storage.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): persistent MessageStore/MessageGroupStore cho stateful integration patterns.
- [Spring Integration — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html): LockRegistry và các implementation JDBC, Redis, ZooKeeper.
- [Spring Integration — Redis Support](https://docs.spring.io/spring-integration/reference/redis.html): RedisLockRegistry và phối hợp lock giữa nhiều instance.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): tăng số consumer và điều chỉnh concurrency.
- [Spring AMQP — Listener Container Configuration](https://docs.spring.io/spring-amqp/reference/amqp/containerAttributes.html): prefetch, concurrency và acknowledgement settings.

Các chi tiết cấu hình và API phụ thuộc phiên bản Spring Boot, Spring Framework, Spring Integration, Spring AMQP, Spring Session và RSocket Java. Đối chiếu đúng dependency version của dự án và kiểm thử khi scale-out, reconnect hoặc rolling restart.
