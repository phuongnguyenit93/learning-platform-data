# LockRegistry và lock theo key

Khi một hệ thống Spring Integration xử lý nhiều message đồng thời, hai message có thể cùng sửa trạng thái của **một đối tượng nghiệp vụ**. Ví dụ, một đơn hàng nhận hai cập nhật gần như cùng lúc: message thứ nhất xác nhận thanh toán, message thứ hai yêu cầu hoàn tiền. Nếu cả hai handler đều đọc trạng thái cũ rồi ghi kết quả, thứ tự cập nhật có thể sai dù mỗi handler riêng lẻ đều hoạt động đúng.

**Lock theo key** cho phép tuần tự hóa vùng xử lý của các message **cùng một khóa**, trong khi vẫn để những khóa khác xử lý song song. Spring Integration cung cấp giao diện **<code>LockRegistry</code>** để lấy <code>java.util.concurrent.locks.Lock</code> theo khóa. Có triển khai trong một JVM và triển khai phân tán dùng tài nguyên chung.

Bài thuộc chương **Lock registry** của module **SPRING_INTEGRATION_RUNTIME**. Ta sẽ thực hành khóa theo key khi message đi qua channel, endpoint, consumer, poller và executor; phân tích cách lock tương tác với transaction, retry, message store, correlation, error flow và các chỉ số runtime.

> **Giới hạn quan trọng:** Lock kiểm soát quyền vào vùng tới hạn. Lock **không tự đảm bảo** transaction commit, message chỉ được giao đúng một lần hoặc side effect chỉ xảy ra đúng một lần. Muốn xử lý an toàn khi retry và redelivery, vẫn cần transaction, idempotency và hợp đồng lưu trữ phù hợp.

## 1. Vấn đề: nhiều message, cùng một khóa nghiệp vụ

Một ví dụ điển hình:

~~~text
Message 1: tenant=T1, order=O42, action=PAY
Message 2: tenant=T1, order=O42, action=REFUND
Message 3: tenant=T1, order=O93, action=PAY
~~~

Với <code>ExecutorChannel</code> hoặc một consumer được gọi từ nhiều thread, message 1 và 2 có thể vào cùng handler đồng thời. Ta muốn message 1 và 2 **không chồng lên nhau** khi cập nhật O42, nhưng message 3 vẫn có thể xử lý song song.

~~~mermaid
flowchart LR
    C["ExecutorChannel"] --> M1["PAY O42"]
    C --> M2["REFUND O42"]
    C --> M3["PAY O93"]
    M1 --> K1["Lock key: T1:O42"]
    M2 --> K1
    M3 --> K2["Lock key: T1:O93"]
    K1 --> S1["Vùng xử lý O42<br/>từng message một"]
    K2 --> S2["Vùng xử lý O93<br/>có thể song song"]
~~~

Nếu không có ranh giới khóa, mô hình **read → check → write** dễ gặp race:

~~~text
Thread A: đọc O42 = NEW
Thread B: đọc O42 = NEW
Thread A: ghi O42 = PAID
Thread B: ghi O42 = REFUNDED (không kiểm tra trạng thái PAID)
~~~

Một khóa cùng key giúp không có hai thread cùng vào đoạn xử lý cần loại trừ trong **phạm vi registry**. Nhưng nếu node khác dùng một registry riêng, hoặc service cập nhật database mà không thông qua cùng quy tắc, khóa cục bộ không đủ bảo vệ toàn bộ hệ thống.

## 2. LockRegistry là gì và API cốt lõi

Giao diện <code>org.springframework.integration.support.locks.LockRegistry</code> khai báo:

~~~java
Lock obtain(Object lockKey);
~~~

<code>obtain(...)</code> **lấy đối tượng khóa gắn với key**, chưa đồng nghĩa đã giành quyền xử lý. Phải gọi một thao tác của <code>Lock</code>:

| API của <code>Lock</code> | Ý nghĩa | Lưu ý |
|---|---|---|
| <code>lock()</code> | Chờ cho đến khi giành được khóa | Có thể chờ không giới hạn; không phản hồi interrupt trong lúc chờ theo hợp đồng <code>Lock</code> |
| <code>lockInterruptibly()</code> | Chờ khóa nhưng cho phép interrupt | Ném <code>InterruptedException</code>; cần khôi phục cờ interrupt nếu chuyển thành lỗi unchecked ở tầng ứng dụng |
| <code>tryLock()</code> | Thử lấy ngay lập tức | Trả <code>false</code> nếu đang bị giữ |
| <code>tryLock(timeout, unit)</code> | Chờ tối đa một khoảng thời gian | Trả <code>false</code> khi hết hạn; có thể ném <code>InterruptedException</code> |
| <code>unlock()</code> | Trả khóa sau vùng tới hạn | Chỉ gọi sau khi đã lấy thành công, thường trong <code>finally</code> |

Ví dụ tối giản:

~~~java
LockRegistry registry = new DefaultLockRegistry();
Lock lock = registry.obtain("tenant:T1:order:O42");

lock.lock();
try {
    // Đọc trạng thái, kiểm tra và cập nhật O42.
} finally {
    lock.unlock();
}
~~~

**Luôn trả khóa bằng <code>finally</code>** nếu đã lấy thành công, kể cả khi code nghiệp vụ ném exception. Nếu dùng <code>tryLock</code>, phải kiểm tra cờ <code>acquired</code> trước khi <code>unlock()</code>; gọi <code>unlock()</code> khi chưa sở hữu có thể ném lỗi và che mất exception gốc.

### executeLocked() từ Spring Integration 6.2

Từ phiên bản 6.2, <code>LockRegistry</code> có các phương thức mặc định <code>executeLocked(...)</code> giúp gói vùng tới hạn:

~~~java
public void applyWithLock(
        LockRegistry registry,
        String businessKey,
        Runnable action) throws InterruptedException {

    registry.executeLocked(businessKey, () -> action.run());
}
~~~

Một biến thể nhận <code>Duration</code> giới hạn thời gian chờ:

~~~java
public void applyWithTimeout(
        LockRegistry registry,
        String businessKey,
        Runnable action) throws InterruptedException, TimeoutException {

    registry.executeLocked(
        businessKey,
        Duration.ofSeconds(2),
        () -> action.run()
    );
}
~~~

<code>executeLocked</code> xử lý việc lấy/trả khóa, truyền exception của hành động bên trong ra caller; biến thể có <code>Duration</code> ném <code>TimeoutException</code> nếu không giành được khóa trước hạn. <code>InterruptedException</code> vẫn cần được caller xử lý; các đoạn code giả định đã import <code>java.time.Duration</code> và <code>java.util.concurrent.TimeoutException</code>.

<code>executeLocked</code> giúp giảm lỗi quên <code>unlock</code>, nhưng không loại bỏ yêu cầu thiết kế **key đúng** và **vùng xử lý đúng**.

## 3. Chọn key: quyết định quan trọng nhất

Khóa phải biểu thị **đúng tài nguyên cần loại trừ đồng thời**. Ví dụ, <code>orderId</code> không đủ nếu các tenant khác nhau có thể cùng dùng một ID.

| Key | Nhận xét |
|---|---|
| <code>orderId</code> | Có thể đụng giữa các tenant |
| <code>tenantId + ":" + orderId</code> | Tốt hơn, nhưng cần quy tắc escaping nếu giá trị chứa dấu <code>:</code> |
| <code>tenant:T1:order:O42</code> | Key có namespace theo loại đối tượng |
| <code>message.getHeaders().getId()</code> | Thường không phù hợp: mỗi message có ID riêng nên hai message cùng đơn vẫn không chia lock |
| <code>correlationId</code> | Phù hợp khi key correlation thực sự chính là đơn vị cần khóa; chưa chắc trùng khóa nghiệp vụ |
| <code>UUID.randomUUID()</code> | Sai cho khóa chia sẻ: mỗi lần gọi lấy một key mới |

Có thể thiết kế một hàm tạo key thống nhất:

~~~java
public final class BusinessLockKeys {
    private BusinessLockKeys() {}

    public static String forOrder(String tenantId, String orderId) {
        if (tenantId == null || tenantId.isBlank()
                || orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Thiếu tenantId/orderId");
        }

        // Mã hóa bằng độ dài từng thành phần để không nhập nhằng dấu phân cách.
        return "orders/" + tenantId.length() + ":" + tenantId
             + "/" + orderId.length() + ":" + orderId;
    }
}
~~~

Key phải được tạo **nhất quán tại mọi nơi** sử dụng registry. Khi nhiều bản triển khai cùng hoạt động trong một đợt rolling deployment, việc thay đổi chuẩn hóa key có thể làm hai phiên bản khóa khác nhau cho cùng đơn hàng.

Quy tắc thực hành:

1. Dùng khóa dựa trên đối tượng **cần được bảo vệ**, không dựa trên một lần gửi message.
2. Có namespace theo nghiệp vụ (<code>orders</code>, <code>accounts</code>) và tenant nếu cần.
3. Dùng dữ liệu bất biến; nếu dùng key object, triển khai <code>equals()</code>/<code>hashCode()</code> ổn định. Với lock phân tán, chuỗi key chuẩn hóa thường dễ bảo đảm đồng nhất hơn.
4. Không đưa toàn bộ payload, thông tin nhạy cảm hoặc giá trị không có giới hạn kích thước vào key backend.
5. Dùng **cùng key** cho tất cả code path có thể sửa cùng tài nguyên, kể cả flow phát lại/retry.

**Key của lock khác key idempotency.** Hai message cùng <code>orderId</code> có thể là hai thao tác hợp lệ cần chạy tuần tự; idempotency key phải phân biệt việc một thao tác cụ thể bị gửi lại.

## 4. DefaultLockRegistry: khóa trong một JVM và striped locking

<code>DefaultLockRegistry</code> là triển khai in-memory dùng các <code>ReentrantLock</code>. Khi khởi tạo, nó tạo một mảng khóa; key được ánh xạ tới phần tử mảng thông qua phép masking trên <code>hashCode()</code>.

~~~java
LockRegistry registry = new DefaultLockRegistry();       // 256 stripes
LockRegistry wider = new DefaultLockRegistry(0x3ff);      // 1024 stripes
~~~

Tham số <code>mask</code> phải có dạng <code>2^n - 1</code>. <code>0xff</code> (255) cho 256 phần tử, <code>0x3ff</code> (1023) cho 1024 phần tử.

~~~mermaid
flowchart TD
    K1["key: order:O42"] --> H1["hashCode & mask"]
    K2["key: order:O93"] --> H2["hashCode & mask"]
    K3["key: order:O12"] --> H3["hashCode & mask"]
    H1 --> L1["ReentrantLock stripe 17"]
    H2 --> L2["ReentrantLock stripe 83"]
    H3 -. "Có thể va chạm" .-> L1
~~~

**Không phải mỗi key khác nhau luôn nhận một lock riêng.** Hai key có hash rơi vào cùng stripe cũng phải chờ nhau; đây là *false contention*, không phải lỗi về đúng/sai dữ liệu. Tăng số stripe khi có bằng chứng va chạm gây nghẽn, không mặc định tăng tối đa vì cần đánh đổi tài nguyên và kiểm thử tải.

<code>DefaultLockRegistry</code> có các tính chất:

- Khóa có tác dụng giữa các thread **dùng cùng instance registry** trong cùng JVM.
- Khóa local theo cơ chế <code>ReentrantLock</code>, nên cùng thread có thể lấy lại lock tương ứng; phải <code>unlock</code> đủ số lần đã khóa.
- JVM/pod khác có mảng khóa độc lập. Hai pod cùng tạo <code>new DefaultLockRegistry()</code> **không đồng bộ với nhau**.
- Khóa không tự bảo vệ một transaction đang commit trên cơ sở dữ liệu ở node khác.

Nếu một hệ thống chỉ có một JVM xử lý tài nguyên đó và không có đường cập nhật bên ngoài, local registry thường là điểm khởi đầu hợp lý.

## 5. Ví dụ: khóa theo order key trong Service Activator

Giả sử inbound adapter tạo message chứa <code>OrderCommand</code> rồi đưa vào <code>orders.input</code>. Nhiều worker có thể gọi handler cùng lúc.

**Bước 1 — command và service nghiệp vụ:**

~~~java
public record OrderCommand(String tenantId, String orderId, String operation) {}

@Service
public class OrderService {
    @Transactional
    public void apply(OrderCommand command) {
        // Đọc trạng thái, kiểm tra nghiệp vụ và ghi database.
        // Thêm ràng buộc DB/idempotency tương ứng trong ứng dụng thật.
    }
}
~~~

**Bước 2 — khóa ở runtime adapter trước khi gọi service:**

~~~java
@Component
public class KeyedOrderHandler {
    private final LockRegistry registry;
    private final OrderService service;

    public KeyedOrderHandler(LockRegistry registry, OrderService service) {
        this.registry = registry;
        this.service = service;
    }

    @ServiceActivator(inputChannel = "orders.input")
    public void handle(OrderCommand command) {
        String key = BusinessLockKeys.forOrder(
            command.tenantId(), command.orderId());
        Lock lock = registry.obtain(key);
        boolean acquired = false;

        try {
            acquired = lock.tryLock(2, TimeUnit.SECONDS);
            if (!acquired) {
                throw new IllegalStateException("Hết thời gian chờ khóa: " + key);
            }
            service.apply(command);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Bị ngắt khi chờ khóa: " + key, ex);
        } finally {
            if (acquired) {
                lock.unlock();
            }
        }
    }
}
~~~

**Bước 3 — wiring Spring Integration:**

~~~java
@Configuration
@EnableIntegration
public class OrderLockConfig {
    @Bean
    LockRegistry orderLockRegistry() {
        return new DefaultLockRegistry();
    }

    @Bean(name = "orders.input")
    MessageChannel ordersInput() {
        return new ExecutorChannel(orderExecutor());
    }

    @Bean
    TaskExecutor orderExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("order-");
        return executor;
    }
}
~~~

Các import chính: <code>org.springframework.integration.support.locks.LockRegistry</code>/<code>DefaultLockRegistry</code>, <code>org.springframework.integration.annotation.ServiceActivator</code>, <code>org.springframework.integration.channel.ExecutorChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.messaging.MessageChannel</code>, <code>org.springframework.core.task.TaskExecutor</code>, <code>org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor</code> và <code>java.util.concurrent.TimeUnit</code>.

Đoạn code cấu hình là một ví dụ rút gọn; Spring quản lý việc khởi tạo và hủy bean executor. Khi đưa vào ứng dụng thực nên inject bean executor được quản lý lifecycle vào cấu hình channel thay vì trực tiếp gọi factory method. Endpoint được khám phá khi Spring Integration xử lý annotation trong application context; không đăng ký thêm một endpoint Java DSL trỏ tới cùng method nếu không muốn tạo thêm consumer.

**Trình tự xử lý:** Thread worker lấy khóa <code>tenant:T1:order:O42</code>; trong vùng đã khóa, gọi service thông qua Spring proxy; nếu <code>@Transactional</code> mở transaction ngay tại service, quá trình commit/rollback của service thường hoàn tất **trước khi method trả về** và handler trả khóa. Nếu transaction được mở từ **caller phía ngoài handler**, việc trả khóa ở cuối handler có thể xảy ra **trước outer commit**. Khi đó phải đổi vị trí khóa hoặc transaction boundary để không có worker khác đọc trạng thái chưa commit.

## 6. Khóa trực tiếp bằng LockRequestHandlerAdvice (Spring Integration 6.5+)

Từ Spring Integration **6.5**, <code>LockRequestHandlerAdvice</code> hỗ trợ khóa theo key quanh một request handler invocation. Advice có thể tính key từ message, bằng giá trị tĩnh, biểu thức SpEL hoặc callback; đây là lựa chọn hữu ích khi muốn logic service không biết đến message runtime.

~~~java
@Configuration
public class OrderAdviceConfig {
    @Bean
    LockRegistry orderLocks() {
        return new DefaultLockRegistry();
    }

    @Bean
    LockRequestHandlerAdvice orderLockAdvice(LockRegistry orderLocks) {
        LockRequestHandlerAdvice advice = new LockRequestHandlerAdvice(
            orderLocks,
            message -> {
                OrderCommand cmd = (OrderCommand) message.getPayload();
                return BusinessLockKeys.forOrder(
                    cmd.tenantId(), cmd.orderId());
            }
        );
        advice.setWaitLockDurationExpressionString("'PT2S'");
        return advice;
    }
}

@Component
public class AdvisedOrderConsumer {
    private final OrderService service;

    public AdvisedOrderConsumer(OrderService service) {
        this.service = service;
    }

    @ServiceActivator(
        inputChannel = "orders.input",
        adviceChain = "orderLockAdvice"
    )
    public void apply(OrderCommand cmd) {
        service.apply(cmd);
    }
}
~~~

<code>LockRequestHandlerAdvice</code> thuộc <code>org.springframework.integration.handler.advice</code>. Đoạn trên là **một lựa chọn thay thế** cho <code>KeyedOrderHandler</code> ở mục trước: chỉ đăng ký **một** consumer trên <code>orders.input</code> cho use case này khi áp dụng ví dụ, để không xử lý cùng lệnh hai lần.

Lưu ý về advice:

- Advice được áp dụng tại handler có cấu hình tương ứng, **không** tự khóa transformer/upstream adapter hay toàn bộ flow trước đó.
- Nếu callback tính key trả <code>null</code>, advice mặc định **không lấy khóa**; có thể cấu hình <code>discardChannel</code> để chuyển message không có key theo chính sách.
- <code>waitLockDuration</code> đặt thời gian chờ lấy khóa, không phải TTL của khóa phân tán và không phải deadline hoàn tất nghiệp vụ.
- Cần kiểm tra phiên bản Spring Integration: không sử dụng <code>LockRequestHandlerAdvice</code> cho ứng dụng đang ở nhánh 6.4 hoặc cũ hơn.

## 7. Khi nào phải chuyển sang distributed LockRegistry?

Nếu các instance Spring Boot A và B cùng xử lý những message có thể sửa một tài nguyên chung, hai registry local **không** loại trừ được nhau.

~~~mermaid
flowchart TD
    A["Pod A<br/>DefaultLockRegistry"] --> DB["Shared database"]
    B["Pod B<br/>DefaultLockRegistry"] --> DB
    C["Không có lock chung<br/>vẫn có thể ghi đè"] -.-> DB
~~~

Spring Integration hỗ trợ nhiều backend distributed lock, chẳng hạn <code>JdbcLockRegistry</code>, <code>RedisLockRegistry</code>, <code>HazelcastLockRegistry</code> và <code>ZookeeperLockRegistry</code>. Với backend phân tán, các node phải cùng sử dụng **registry namespace và key** đại diện cho cùng tài nguyên.

| Triển khai | Phạm vi đồng bộ | Cần chú ý |
|---|---|---|
| <code>DefaultLockRegistry</code> | Các thread cùng JVM, cùng instance | Striped collisions; không dùng như cluster lock |
| <code>JdbcLockRegistry</code> | Các node cùng dùng JDBC lock repository | Bảng lock, transaction, DB latency, lease và renewal |
| <code>RedisLockRegistry</code> | Các node dùng cùng Redis/registry key | Hết hạn lock, network/Redis availability, cache/renewal |
| <code>HazelcastLockRegistry</code> | Theo cluster/backend Hazelcast được cấu hình | Topology và semantics cluster |
| <code>ZookeeperLockRegistry</code> | Các node dùng cùng ZooKeeper | Session và lỗi kết nối |

Ví dụ hạ tầng JDBC ở một node; node khác phải dùng cùng database và region:

~~~java
@Configuration
public class DistributedLockConfig {
    @Bean
    DefaultLockRepository orderLockRepository(DataSource dataSource) {
        DefaultLockRepository repository =
            new DefaultLockRepository(dataSource);
        repository.setRegion("order-processing");
        return repository;
    }

    @Bean
    LockRegistry orderLockRegistry(DefaultLockRepository orderLockRepository) {
        return new JdbcLockRegistry(orderLockRepository);
    }
}
~~~

Cần các bảng JDBC lock tương ứng theo script Spring Integration cho database đang dùng và transaction manager thích hợp. <code>DefaultLockRepository</code>/<code>JdbcLockRegistry</code> thuộc <code>org.springframework.integration.jdbc.lock</code>. Cấu hình này là phần hạ tầng chính; bean channel/handler ở ví dụ trước có thể dùng <code>LockRegistry</code> được inject mà không thay đổi business key.

**Không coi lease là một đảm bảo tuyệt đối.** Một node có thể bị pause lâu, mất kết nối hoặc giữ lock vượt thời hạn thuê; node khác có thể lấy được cùng lock sau expiry, trong khi node cũ chưa dừng xử lý. Tùy yêu cầu nhất quán, phải kết hợp version/fencing hoặc conditional update ở database để ngăn worker cũ ghi tiếp. Lock không thay thế điều kiện cập nhật ở tài nguyên được bảo vệ.

## 8. Timeout khi chờ khóa khác TTL của khóa

Hai khái niệm cần tách biệt:

| Thông số | Quyết định | Ví dụ |
|---|---|---|
| <code>tryLock(2, SECONDS)</code> | Thread chờ tối đa hai giây để giành khóa | Hết hạn thì từ chối/retry theo chính sách |
| Lease/TTL của distributed lock | Backend giữ dấu vết quyền sở hữu trong bao lâu | Node chết thì key có thể hết hạn để node khác giành lại |
| <code>groupTimeout</code> của aggregator | Đến hạn đánh giá/hoàn tất group đang thiếu message | Không phải lock wait, cũng không phải lock lease |
| <code>sendTimeout</code> / <code>receiveTimeout</code> của channel | Giới hạn chờ khi gửi/nhận message | Không khóa tài nguyên nghiệp vụ |
| Transaction timeout | Hạn thực hiện giao dịch transactional | Không tự chuyển một lock đã lấy sang node khác |

Chờ khóa thất bại phải được phân loại rõ:

~~~text
Acquired → chạy use case → commit/rollback → unlock
Timed out → không chạy use case → lỗi có thể retry/backoff
Interrupted → không chạy use case → giữ interrupt semantics
Lease lost → trạng thái quyền sở hữu không còn chắc chắn → alert/đánh giá nhất quán
~~~

Khi bắt <code>InterruptedException</code>, nếu code cần chuyển sang unchecked exception thì gọi <code>Thread.currentThread().interrupt()</code> trước. Đừng bắt lỗi rồi tiếp tục chạy thao tác nghiệp vụ **không có khóa**; như vậy phá hợp đồng loại trừ.

Với <code>RedisLockRegistry</code>, unlock một khóa đã hết hạn có thể ném exception nghiêm trọng vì tài nguyên đang bảo vệ có thể đã được node khác truy cập. Tính năng tự gia hạn lease trên Redis được bổ sung từ Spring Integration 6.4 qua <code>setRenewalTaskScheduler()</code>; version và cấu hình renewal cụ thể cần được kiểm tra trước khi dùng.

## 9. Lock, transaction, retry và idempotency

Một kết quả xử lý đúng phụ thuộc vào cách xếp các ranh giới:

~~~text
Message
  → lock theo business key
     → service transaction begin
        → kiểm tra trạng thái + ghi DB
     → commit/rollback
  → unlock
  → reply / publish event
~~~

Mô hình này giúp thao tác database của service hoàn tất trước khi khóa được nhả **nếu** không có outer transaction mở từ trước. Có ba ngoại lệ quan trọng:

1. **Transaction bao ngoài lock:** gọi handler trong một facade đang mở transaction; handler nhả khóa trước khi facade commit. Worker khác có thể giành khóa rồi truy cập DB khi transaction cũ chưa hoàn tất.
2. **Downstream bất đồng bộ:** handler có thể nhả khóa sau khi gửi vào <code>ExecutorChannel</code> hoặc <code>QueueChannel</code>, còn consumer downstream chưa xử lý. Muốn bảo vệ toàn bộ chuỗi phải thiết kế lại đơn vị công việc hoặc giao tiếp giữa các bước.
3. **Side effect ngoài DB:** gọi HTTP, gửi email hoặc publish một message ra broker thường không được rollback tự động với JDBC transaction. Cần idempotency và có thể dùng transactional outbox.

### Retry dưới khóa hay khóa cho từng lần retry?

| Cách sắp xếp | Hành vi | Hệ quả |
|---|---|---|
| Lock bao ngoài retry | Một worker giữ khóa qua tất cả attempt và backoff | Duy trì loại trừ nhưng giữ khóa lâu, dễ nghẽn |
| Retry bao ngoài lock | Mỗi attempt giành khóa rồi trả | Cho phép worker khác xen vào giữa các attempt; cần kiểm tra lại trạng thái mỗi lần |
| Retry của broker sau redelivery | Một message được đưa đến lại ở thời điểm khác | Lock không ngăn side effect trùng; cần khóa idempotency riêng |

Lỗi deadlock database, lock acquisition timeout hoặc backend tạm thời mất kết nối có thể retry có giới hạn; lỗi nghiệp vụ cố định như <code>quantity &lt;= 0</code> thường không đáng retry. Với lỗi không biết rõ transaction đã commit hay chưa, hãy kiểm tra idempotency trước khi thực hiện lại.

**Không đặt lock theo message ID** nếu mục tiêu là tuần tự hóa các thao tác cùng đối tượng: redelivery có thể tạo message ID khác, trong khi business key vẫn như cũ.

## 10. Lock tại endpoint có thay đổi thread và lifecycle không?

Lock **không tạo thread**, cũng không làm một flow thành đồng bộ theo nghĩa end-to-end:

| Topology | Lock chạy ở đâu? | Rủi ro |
|---|---|---|
| <code>DirectChannel</code> → handler | Thread của sender | Đợi lock kéo dài <code>send()</code> hoặc gateway request–reply |
| <code>ExecutorChannel</code> → handler | Worker thread sau handoff | Nhiều worker đứng chờ, làm đầy pool/queue |
| <code>QueueChannel</code> → poller → handler | Poller/scheduler thread | Lock wait kéo dài một poll cycle, giảm throughput |
| Hai replica cùng một broker | Thread của consumer tại từng replica | Cần distributed lock nếu cùng tài nguyên có thể được xử lý ở nhiều replica |

Khi stop <code>IntegrationFlow</code> hoặc endpoint, công việc đang chạy hay đang chờ lock có thể chưa kết thúc ngay. Nếu executor bị shutdown/interrupt, handler phải trả lock đúng cách; với distributed lock, việc lease hết hạn sau crash có thể tạo một thời gian chờ cho node khác.

Hãy giới hạn thời gian giành khóa theo SLA của request/poller. Với message không thể xử lý do hết hạn, quyết định rõ ràng: retry/backoff, trả lỗi tới caller, phát <code>ErrorMessage</code> ở error flow tương ứng hoặc chuyển sang queue xử lý sau. Chỉ đặt timeout mà không có đường xử lý thất bại sẽ dẫn tới mất message hoặc log không có recovery.

## 11. Hiệu năng: tranh khóa và hot key

Lock theo key giữ được concurrency giữa các tài nguyên khác nhau, nhưng không tăng throughput cho **một** tài nguyên nóng:

~~~text
100 message cùng order=O42
  → một lock key
  → tối đa một thread trong critical section tại một thời điểm

100 message trên 100 order khác nhau
  → nhiều lock key
  → có thể xử lý song song, tùy registry và số stripe/worker
~~~

Với local striped locks, những key khác nhau có thể tranh cùng stripe. Với distributed locks, độ trễ network, Redis/JDBC contention và thời gian gia hạn lease có thể lớn hơn chính việc xử lý nghiệp vụ.

Metric nên quan sát:

- **Lock wait time:** thời gian từ lúc bắt đầu chờ tới khi acquired; xem p50/p95/p99 theo endpoint và loại key.
- **Lock hold time:** thời gian giữ khóa, đặc biệt khi chứa database query hoặc external API.
- **Timeout/interrupt/lease lost count:** đếm nguyên nhân thất bại khi giành/trả khóa.
- **Executor saturation và queue depth:** worker chờ khóa nhiều có thể gây backlog.
- **Throughput theo business key:** phát hiện một key chiếm phần lớn tải.
- **DB optimistic conflict / retry count:** đánh giá cần thêm version check/idempotency.

Không gắn raw key mang thông tin nhạy cảm hoặc cardinality cực cao làm label cho metric hệ thống. Có thể dùng correlation ID trong trace/log có kiểm soát và tổng hợp metric theo endpoint, loại thao tác hoặc tenant đã được chuẩn hóa.

## 12. Chẩn đoán khi message bị kẹt hoặc xử lý trùng

| Triệu chứng | Nguyên nhân cần kiểm tra | Bằng chứng |
|---|---|---|
| Hai message cùng order vẫn chạy song song | Khác key, khác registry instance hoặc hai pod dùng local lock | Log key đã chuẩn hóa, node ID, registry type |
| Message chờ quá lâu | Hot key, giữ lock qua HTTP chậm, DB lock hoặc executor nghẽn | Lock wait/hold, thread dump, DB/Redis metrics |
| <code>tryLock</code> luôn timeout | Lock bị giữ lâu, lease chưa hết hoặc contention | Owner, timestamp, TTL, retry policy |
| Sau restart node khác chưa xử lý được | Distributed lease còn hiệu lực | TTL/renewal, backend state, connection logs |
| <code>unlock</code> ném exception | Trả khóa sai owner, chưa acquire hoặc lease hết hạn | Stack trace và log quyền sở hữu |
| Khóa đúng nhưng DB vẫn có bản ghi trùng | Redelivery sau unlock, code path khác, transaction/idempotency thiếu | Unique constraint, business event ID, retry logs |
| Tăng thread nhưng throughput không tăng | Một key quá nóng, striped collisions hoặc backend lock chậm | Phân bố key, thread pool active, lock wait p95 |
| Error channel không thấy lỗi | Lỗi bị bắt/nuốt hoặc xử lý đồng bộ ném về sender | Thread boundary, handler advice và đường exception |

Khi chẩn đoán, theo dõi một request bằng correlation ID và **business lock key được che dữ liệu**. Xác nhận mỗi log “lock acquired” có “lock released” hoặc kết thúc lỗi rõ ràng; đừng chỉ tăng timeout khi chưa tìm ra đoạn code giữ khóa.

## 13. Kiểm thử tính loại trừ theo key

Test cần chứng minh hai điều khác nhau: **cùng key không được chạy đồng thời**, còn **khác key có thể chạy đồng thời**. Một unit test tuần tự gọi handler hai lần không chứng minh được đặc tính khóa.

Ví dụ một test trực tiếp dùng registry local, JUnit 5 và executor:

~~~java
@Test
void sameKeyNeverEntersCriticalSectionConcurrently() throws Exception {
    LockRegistry registry = new DefaultLockRegistry();
    ExecutorService workers = Executors.newFixedThreadPool(8);
    CountDownLatch start = new CountDownLatch(1);
    AtomicInteger inside = new AtomicInteger();
    AtomicInteger peak = new AtomicInteger();
    List<Future<?>> tasks = new ArrayList<>();

    try {
        for (int i = 0; i < 20; i++) {
            tasks.add(workers.submit(() -> {
                start.await();
                Lock lock = registry.obtain("tenant:T1:order:O42");
                lock.lock();
                try {
                    int active = inside.incrementAndGet();
                    peak.accumulateAndGet(active, Math::max);
                    try {
                        Thread.sleep(5);
                    } finally {
                        inside.decrementAndGet();
                    }
                } finally {
                    lock.unlock();
                }
                return null;
            }));
        }

        start.countDown();
        for (Future<?> task : tasks) {
            task.get(10, TimeUnit.SECONDS);
        }
        assertEquals(1, peak.get());
    } finally {
        workers.shutdownNow();
    }
}
~~~

Những kiểu được dùng: <code>Lock</code>, <code>ExecutorService</code>, <code>Executors</code>, <code>CountDownLatch</code>, <code>AtomicInteger</code>, <code>Future</code>, <code>ArrayList</code>, <code>List</code> và <code>TimeUnit</code>. Đây là test chứng minh tính loại trừ cho cùng key trong **một JVM**. Để chứng minh khác key không bị chặn, cần một bài test sử dụng hai key được xác nhận rơi vào hai stripe khác nhau và đồng bộ thời điểm tiến vào critical section.

Với cluster, cần **ít nhất hai process/application context**, cùng backend thực và cùng registry namespace; đo xem hai node có bao giờ xử lý cùng key đồng thời hay không. Cần bổ sung ca crash, TTL hết hạn, renewal, restart, retry và một request đến đồng thời ngay trước/đúng lúc commit database.

### Các tình huống nên có trong bộ test tích hợp

| Ca test | Kết quả mong đợi |
|---|---|
| 20 message cùng order trong một instance | Tối đa một handler giữ cùng lock tại một thời điểm |
| Nhiều key và nhiều thread | Có concurrency giữa key phù hợp, không có trộn trạng thái |
| Một thread giữ lock quá timeout | Thread chờ nhận timeout; không chạy service |
| Worker bị interrupt khi chờ | Thoát đúng, không mất interrupt semantics |
| Service ném exception | Lock được trả trong <code>finally</code>; worker khác tiếp tục được |
| Hai pod dùng cùng JDBC/Redis registry | Không có hai owner hợp lệ cùng critical section trong điều kiện backend hỗ trợ |
| Lock lease hết hạn trong lúc handler chạy | Phát hiện mất quyền sở hữu; tránh ghi đè dữ liệu không hợp lệ |
| Retry/redelivery cùng business event | Unique/idempotency bảo đảm không phát side effect trùng |
| Stop endpoint giữa lúc chờ lock | Không rò rỉ worker/lock; error path rõ |

## 14. Checklist trước khi đưa vào production

- [ ] Khóa đại diện đúng tài nguyên cần bảo vệ; key có namespace, ổn định và được tạo giống nhau trên mọi code path.
- [ ] Đã xác định rõ registry hoạt động trong một JVM hay trên nhiều instance; cluster dùng backend chung và cùng region/namespace.
- [ ] Mọi <code>lock()</code>/<code>tryLock()</code> có đường <code>unlock()</code> chắc chắn trong <code>finally</code>, chỉ sau khi acquired thành công.
- [ ] Có ngân sách chờ khóa, cách xử lý timeout/interrupt và chính sách retry phù hợp với SLA, poller và executor.
- [ ] Vùng xử lý cần bảo vệ có transaction boundary thích hợp; không nhả khóa trước commit nếu điều đó làm mất tính nhất quán.
- [ ] Không giữ khóa qua HTTP/IO chậm nếu có cách thiết kế transaction, queue hoặc workflow khác an toàn hơn.
- [ ] Có idempotency key hoặc unique constraint cho duplicate side effect; không nhầm lock với exactly-once delivery.
- [ ] Distributed lease/renewal và tình huống node mất lock đã được kiểm thử, có biện pháp chống stale writer khi cần.
- [ ] Theo dõi lock wait, hold, timeout, hot key, thread pool và error flow, đồng thời hạn chế lộ key nhạy cảm.
- [ ] Có test đồng thời một JVM và test nhiều node khi sản phẩm thật chạy nhiều replica.

**Kết luận:** <code>LockRegistry</code> cho phép Spring Integration và ứng dụng giữ **quyền xử lý độc quyền theo một key xác định**. Chọn key đúng, xác định registry local hay distributed, khóa đúng phạm vi, nhả khóa chắc chắn và kết hợp transaction/idempotency là các điều kiện để message flow hoạt động nhất quán khi tăng concurrency. Lock theo key là một phần của thiết kế runtime, không phải bảo đảm tự động cho toàn bộ flow phân tán.

## Tài liệu tham khảo

- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/6.5/distributed-locks.html)
- [Spring Integration Reference — Lock Advice (6.5)](https://docs.spring.io/spring-integration/reference/6.5/handler-advice/lock.html)
- [Spring Integration Javadoc — LockRegistry 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/locks/LockRegistry.html)
- [Spring Integration Javadoc — DefaultLockRegistry 6.5](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/support/locks/DefaultLockRegistry.html)
- [Spring Integration Reference — Redis Lock Registry](https://docs.spring.io/spring-integration/reference/redis.html)
- [Spring Integration Reference — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html)
