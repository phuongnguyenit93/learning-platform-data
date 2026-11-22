# Lock timeout và tryLock trong Spring Integration Runtime

## Mục tiêu bài học

Trong **SPRING_INTEGRATION_RUNTIME**, nhiều channel, consumer, poller và executor có thể cùng xử lý message thuộc một đơn hàng hoặc một nhóm correlation. Khi hai thread hoặc hai application instance cùng cập nhật một trạng thái, thao tác đọc–kiểm tra–ghi dễ xảy ra race condition. **LockRegistry** hỗ trợ lấy lock theo khóa để phối hợp những đoạn xử lý cần thực thi độc quyền.

Bài thuộc chương **Lock registry**, tập trung vào **Lock timeout và tryLock**: cách thử lấy lock không chờ, chờ có giới hạn, quyết định khi hết thời gian, và xử lý đúng khi backend lock là một dịch vụ phân tán.

Sau bài này, bạn có thể:

- Giải thích **LockRegistry.obtain(lockKey)** và các cách gọi **Lock.lock()**, **Lock.tryLock()**, **Lock.tryLock(timeout, unit)**.
- Phân biệt **thời gian chờ lock**, **thời gian giữ lock**, **transaction timeout**, **message deadline** và **lease/TTL của distributed lock**.
- Viết handler luôn **unlock trong finally**, giữ đúng quyền sở hữu và xử lý **InterruptedException**.
- Chọn giữa **fail-fast**, **chờ có giới hạn**, **retry sau** hoặc **đẩy message sang recovery** khi lock đang bận.
- Biết giới hạn của **DefaultLockRegistry** trong một JVM và yêu cầu bổ sung khi dùng Redis, JDBC hoặc ZooKeeper.
- Kiểm thử contention, timeout, interrupt, crash, lease expiration, transaction rollback và message redelivery.

> **Nguyên tắc:** Lấy được lock chỉ bảo đảm phần việc được bảo vệ theo **phạm vi và thời hạn mà implementation cho phép**. Lock không tự biến HTTP, DB, broker hay MessageStore thành một transaction duy nhất.

## 1. Vì sao một message flow cần lock?

Ví dụ hai consumer nhận yêu cầu cập nhật cùng đơn hàng O-42:

~~~text
Consumer A: đọc trạng thái đơn = NEW
Consumer B: đọc trạng thái đơn = NEW
Consumer A: chuyển sang RESERVED, ghi sự kiện
Consumer B: chuyển sang RESERVED, ghi thêm một sự kiện trùng
~~~

Trong một JVM, **synchronized** hoặc lock cục bộ có thể bảo vệ một phần state. Khi Spring Integration scale thành nhiều instance, mỗi JVM có bộ nhớ và monitor riêng; vì thế synchronized của A không ngăn được B.

~~~mermaid
flowchart LR
    A["Instance A<br/>worker-1"] --> K["Lock key:<br/>order:O-42"]
    B["Instance B<br/>worker-3"] --> K
    K --> L[("Shared LockRegistry")]
    L --> S[("Shared state<br/>MessageStore / DB")]
~~~

Điều kiện để sơ đồ thực sự bảo vệ được dữ liệu:

1. Mọi bên thay đổi cùng tài nguyên đều sử dụng **cùng quy tắc tạo lockKey**.
2. Chúng dùng **cùng miền đồng bộ hóa**: cùng JVM đối với lock local, hoặc cùng backend/namespace với distributed lock.
3. Mỗi bên chỉ thao tác trạng thái được bảo vệ **sau khi lấy được lock** và tuân thủ quy tắc release.
4. Dữ liệu sống lâu hoặc phục vụ nhiều instance còn cần **transaction, optimistic locking, unique constraint hoặc idempotency** phù hợp.

**Lock key không phải MessageHeaders.ID.** Một message bị redelivery có thể nhận ID kỹ thuật mới. Nếu mục tiêu là tuần tự xử lý theo đơn hàng, hãy dùng **orderId** hoặc **correlation key ổn định**.

## 2. API cơ bản: LockRegistry và java.util.concurrent.locks.Lock

Spring Integration định nghĩa **org.springframework.integration.support.locks.LockRegistry**. Hợp đồng sử dụng chính là:

~~~java
import java.util.concurrent.locks.Lock;
import org.springframework.integration.support.locks.LockRegistry;

Lock lock = lockRegistry.obtain("order:O-42");
~~~

**obtain(key)** cung cấp một đối tượng **java.util.concurrent.locks.Lock** đại diện cho khóa. Việc lấy đối tượng Lock **chưa có nghĩa** là bạn đang giữ quyền độc quyền; phải gọi **lock()**, **tryLock()** hoặc **tryLock(timeout, unit)**.

| API của Lock | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| **lock()** | Cố lấy lock và chờ tới khi lấy được, theo contract của implementation | Chỉ khi thời gian chờ không giới hạn là chấp nhận được và đã hiểu interruption/shutdown |
| **tryLock()** | Thử lấy ngay; trả **true/false**, không chờ lock được giải phóng | Handler phải phản hồi nhanh khi tài nguyên đang bận |
| **tryLock(timeout, unit)** | Đợi tối đa khoảng thời gian chỉ định để thử lấy; trả true/false, có thể ném **InterruptedException** | Cần giới hạn lock wait để bảo vệ latency và thread pool |
| **lockInterruptibly()** | Chờ lock với khả năng phản ứng khi thread bị interrupt | Cần hỗ trợ shutdown/cancel trong lúc chờ |
| **unlock()** | Giải phóng lock đã lấy | Luôn nằm trong **finally** khi đã acquire thành công |

Với distributed implementation, một lần **tryLock()** không chờ **khóa được thả**, nhưng thao tác liên lạc Redis/DB/ZooKeeper vẫn có latency và có thể ném exception vì hạ tầng. **Timeout của timed tryLock** là giới hạn chờ lock theo implementation; không phải một **deadline bảo đảm** cho toàn bộ lời gọi network và nghiệp vụ.

### Thử lấy lock ngay

~~~java
Lock lock = lockRegistry.obtain("order:O-42");
if (!lock.tryLock()) {
    // Có người khác đang xử lý cùng khóa.
    // Quyết định: retry sau, phát tín hiệu BUSY hoặc chuyển recovery.
    throw new LockBusyException("order O-42 is busy");
}

try {
    processOrder("O-42");
} finally {
    lock.unlock();
}
~~~

Ở đây, **false** là kết quả cạnh tranh lock có thể dự kiến, không phải thành công nghiệp vụ. Nếu handler **return bình thường** khi false, poller/broker có thể hiểu rằng message đã được xử lý xong, tùy acknowledgement và transaction.

### Thử lấy lock có giới hạn thời gian

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;

Lock lock = lockRegistry.obtain("order:O-42");
boolean acquired = false;

try {
    acquired = lock.tryLock(300, TimeUnit.MILLISECONDS);
    if (!acquired) {
        throw new LockBusyException("Timeout waiting for order O-42");
    }
    processOrder("O-42");
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Thread interrupted while waiting for lock",
            interrupted);
} finally {
    if (acquired) {
        lock.unlock();
    }
}
~~~

Điểm bắt buộc:

- **unlock chỉ khi acquired == true**; gọi unlock khi chưa sở hữu lock có thể gây lỗi.
- Không **nuốt InterruptedException**: khôi phục interrupt flag hoặc chuyển cho tầng trên theo hợp đồng để shutdown/cancel hoạt động.
- **LockBusyException** trong ví dụ là exception ứng dụng, không phải class mặc định của Spring Integration.
- Không dùng return success hoặc ack message chỉ vì hết thời gian chờ.
- Lock có thể không lấy được do **contention**, nhưng backend cũng có thể ném exception vì mất kết nối; phân loại riêng hai tình huống.

## 3. Ví dụ handler có lock và idempotency

Đoạn dưới minh họa bảo vệ từng **orderId** trong một service activator. Nó sử dụng API chung của **LockRegistry**, nên phần lấy lock giống nhau dù ứng dụng cấu hình DefaultLockRegistry hay một implementation phân tán.

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.support.locks.LockRegistry;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

record OrderCommand(String orderId, String eventId, String targetStatus) {}

interface OrderRepository {
    // Cần triển khai atomic/idempotent (ví dụ unique eventId và DB transaction).
    void applyIfNew(OrderCommand command);
}

class LockBusyException extends RuntimeException {
    LockBusyException(String message) {
        super(message);
    }
}

@Component
class OrderUpdateHandler {
    private final LockRegistry lockRegistry;
    private final OrderRepository repository;

    OrderUpdateHandler(LockRegistry lockRegistry, OrderRepository repository) {
        this.lockRegistry = lockRegistry;
        this.repository = repository;
    }

    @ServiceActivator(inputChannel = "orderUpdates")
    public void handle(Message<OrderCommand> input) {
        OrderCommand command = input.getPayload();
        if (command.orderId() == null || command.orderId().isBlank()
                || command.eventId() == null || command.eventId().isBlank()) {
            throw new IllegalArgumentException("Missing orderId or eventId");
        }

        String lockKey = "order-update:" + command.orderId();
        Lock lock = lockRegistry.obtain(lockKey);
        boolean acquired = false;

        try {
            acquired = lock.tryLock(250, TimeUnit.MILLISECONDS);
            if (!acquired) {
                throw new LockBusyException("Busy lockKey=" + lockKey);
            }

            // Phần cập nhật nghiệp vụ phải chịu được duplicate/redelivery.
            repository.applyIfNew(command);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                    "Interrupted while acquiring " + lockKey, interrupted);
        } finally {
            if (acquired) {
                lock.unlock();
            }
        }
    }
}
~~~

Đây là một **ví dụ hợp đồng**, chưa phải flow deploy hoàn chỉnh. Cần khai báo bean **LockRegistry**, repository, các channel và source/consumer. Một implementation của **OrderRepository.applyIfNew** phải tự bảo vệ atomicity của DB, xử lý duplicate **eventId** và transaction đúng phạm vi; Java lock không thay thế các điều kiện đó.

**Vì sao giữ lock trong thời gian ngắn?** Khi xử lý theo orderId, các đơn khác vẫn có thể chạy song song. Nếu giữ lock trong một HTTP request mất 10 giây, các message cùng orderId sẽ chờ lâu; nếu backend distributed lock có lease ngắn, quyền sở hữu lock còn có thể hết trước khi HTTP hoàn tất.

## 4. Phân biệt bốn loại timeout dễ bị nhầm

Trong Spring Integration Runtime, “timeout” có thể chỉ những đồng hồ khác nhau:

| Đồng hồ | Đo điều gì? | Hết hạn thì sao? |
| --- | --- | --- |
| **Lock wait timeout** | Chờ **lấy** lock, ví dụ 250 ms | Timed tryLock trả false hoặc bị interrupt; chưa vào critical section |
| **Lock lease / TTL** | Thời gian một distributed lock được backend coi là còn hiệu lực | Backend có thể cho bên khác lấy cùng khóa dù worker cũ chưa xong |
| **Transaction timeout** | Thời gian transaction có thể hoạt động theo transaction manager | Transaction có thể bị rollback/đánh dấu rollback-only; không tự release mọi external side effect |
| **Message deadline / gateway timeout** | Tổng thời gian caller chờ hoàn tất nghiệp vụ | Caller có thể timeout và phát lại trong khi worker cũ còn chạy |

Ngoài ra còn có **poller receive timeout**, **executor queue wait**, **group timeout của aggregator** và **HTTP connect/read timeout**. Chúng không tự chia sẻ một thời hạn tổng.

### Ví dụ: chờ lock 300 ms, lease 5 giây

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant L as Distributed lock
    participant B as Worker B
    A->>L: obtain K + acquire (lease 5 s)
    L-->>A: acquired
    B->>L: tryLock(K, 300 ms)
    L-->>B: false (lock đang bận)
    Note over A: Công việc bị treo hoặc dừng GC quá 5 s
    Note over L: Lease hết hạn
    B->>L: tryLock(K) ở lần mới
    L-->>B: acquired
    Note over A,B: Có nguy cơ hai worker cùng tác động dữ liệu!
~~~

**Lock wait timeout = 300 ms** không kéo dài **lease = 5 giây**. Khi lease hết, implementation có thể thu hồi quyền sở hữu; điều này phụ thuộc backend và cấu hình heartbeat/renewal. Nếu worker A không biết mình đã mất lease nhưng vẫn ghi DB, lock phân tán **không còn bảo đảm độc quyền** cho thao tác đó.

Đối với tài nguyên cần tính nhất quán mạnh, hãy kết hợp:

- **Fencing token** hoặc **version/epoch tăng đơn điệu** để kho dữ liệu từ chối writer cũ.
- **Optimistic locking/version condition** trong DB (ví dụ cập nhật khi version hiện tại còn đúng).
- **Idempotency key / unique constraint** cho các thao tác nghiệp vụ có thể bị lặp.
- **Deadline** cho critical section và xử lý mất quyền sở hữu.

Không tự giả định tất cả LockRegistry đều cấp fencing token, hoặc tự gia hạn lease vô thời hạn. Cần đọc hợp đồng của **implementation cụ thể** được chọn.

## 5. Chọn LockRegistry đúng phạm vi

Spring Integration có nhiều implementation của **LockRegistry**. Lựa chọn phụ thuộc số instance, hạ tầng, độ trễ và bảo đảm cần thiết:

| Implementation | Phạm vi phối hợp | Phù hợp khi | Điều cần xác minh |
| --- | --- | --- | --- |
| **DefaultLockRegistry** | **Một JVM** | Test, ứng dụng một instance, state chỉ cục bộ | Không khóa được JVM khác; restart làm mất lock state |
| **JdbcLockRegistry** | Nhiều JVM dùng chung **DB** | Đã có RDBMS và cần distributed lock | Bảng lock, transaction, thời gian sống lock, polling contention, cleanup |
| **RedisLockRegistry** | Nhiều JVM dùng chung **Redis** | Độ trễ thấp, hạ tầng Redis sẵn có | TTL, renewal, failover, network partition, ownership và unlock |
| **ZookeeperLockRegistry** | Nhiều JVM dùng chung **ZooKeeper** | Hệ thống đã dùng coordination service | Session expiry, connection loss, watch/ownership và phục hồi |

Cấu hình tối giản cho **một JVM**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.integration.support.locks.LockRegistry;

@Configuration
class LocalLockConfiguration {
    @Bean
    LockRegistry lockRegistry() {
        return new DefaultLockRegistry();
    }
}
~~~

**Không sao chép cấu hình trên vào một service scale nhiều replica** rồi mong nó bảo vệ group chung: mỗi replica tạo một DefaultLockRegistry riêng. Nếu nhiều bean hoặc nhiều flow cần phối hợp trên **cùng một JVM**, chúng cũng phải dùng cùng registry instance hoặc cơ chế lock nhất quán.

Với distributed implementation, việc khởi tạo bean có thể cần dependency module riêng, bảng lock/chính sách schema, RedisConnectionFactory hoặc ZooKeeper client. Các tham số TTL, renewal và cleanup khác nhau giữa phiên bản Spring Integration; hãy cấu hình theo tài liệu của loại registry và phiên bản thực dùng, sau đó kiểm thử failure mode bằng hạ tầng thật.

## 6. Quy tắc tạo lock key

Một lock key tốt cần **ổn định, đủ hẹp và không xung đột ngữ nghĩa**:

~~~text
order-update:v1:tenant-A:O-42
order-update:v1:tenant-A:O-43
order-update:v1:tenant-B:O-42
~~~

Các sai lầm hay gặp:

- **Khóa toàn cục** bằng một chuỗi "orders" khiến tất cả đơn phải xếp hàng, giảm throughput.
- **Khóa quá hẹp** bằng MessageHeaders.ID mới mỗi lần send khiến hai message cùng đơn đi vào hai lock khác nhau.
- Thiếu **tenantId**, environment hoặc namespace nên hai ứng dụng độc lập tranh lock một cách không cần thiết.
- Thêm **retry attemptId** vào lockKey khiến mỗi retry tránh được lock của lần trước, phá ý nghĩa độc quyền.
- Dùng khóa không chuẩn hóa: "O-42", "o-42" hoặc chuỗi có khoảng trắng vô tình đại diện cùng một đơn nhưng lock khác nhau.
- Sử dụng một lockKey cho nhiều tài nguyên không liên quan, hoặc hai loại lockKey khác nhau cho cùng một invariant.

Với nghiệp vụ đa bước, xác định invariant trước khi chọn khóa. Ví dụ **orderId** phù hợp nếu mọi thay đổi của đơn phải tuần tự; **skuId** phù hợp nếu mọi lần trừ tồn kho cùng SKU phải cạnh tranh cùng lock. Nhưng nếu một thao tác thay đổi **hai SKU**, một lock trên orderId không bảo vệ được bất biến tồn kho.

**Tránh deadlock khi lấy nhiều lock:** Chọn thứ tự khóa nhất quán, ví dụ sắp xếp SKU rồi acquire theo thứ tự; đặt timeout và giải phóng các lock đã lấy nếu lock kế tiếp thất bại. Với nhiều tài nguyên DB, transaction và optimistic locking thường dễ quản lý hơn việc ghép lock ứng dụng thủ công.

## 7. Khi tryLock trả false: quyết định gì?

**tryLock false không phải lỗi kỹ thuật ngẫu nhiên**: nó biểu thị không lấy được lock trong thời gian cho phép. Hành vi đúng tùy loại message và hợp đồng nguồn.

~~~mermaid
flowchart TD
    A["Message đến handler"] --> L{"tryLock thành công?"}
    L -- "Có" --> W["Xử lý trong critical section"]
    W --> U["unlock trong finally"]
    U --> OK["Kết quả / ack theo contract"]
    L -- "Không" --> D{"Có thể chờ hoặc retry?"}
    D -- "Có, còn budget" --> R["Backoff / reschedule"]
    D -- "Không" --> E["Business BUSY / quarantine / alert"]
    R --> A
~~~

### Ba cách thường dùng

**A. Fail-fast (tryLock())**: ưu tiên khi cần giữ thread ít lâu, caller hiểu được trạng thái BUSY, hoặc message có thể đưa vào delayed retry. Phù hợp trong hệ thống throughput cao với hàng chờ bền vững; cần tránh retry nóng.

**B. Timed wait (tryLock(250, MILLISECONDS))**: chấp nhận contention ngắn, nhưng không chiếm executor vô thời hạn. Hợp đồng vẫn phải có **deadline đầu-cuối** và kế hoạch khi không lấy được lock.

**C. Chờ không giới hạn (lock())**: chỉ cân nhắc khi thật sự cho phép chờ và đã thiết kế shutdown, thread capacity, lease/network failure. Trong flow polling hoặc executor hạn chế, một lock() bị giữ lâu có thể làm hết thread xử lý.

| Tình huống khi không lấy được lock | Phản ứng phù hợp có thể chọn | Rủi ro cần tránh |
| --- | --- | --- |
| API đồng bộ yêu cầu phản hồi nhanh | Trả BUSY/CONFLICT có hợp đồng rõ | Trả HTTP 200 và coi như hoàn tất |
| Broker consumer có redelivery | Ném exception hoặc nack để phát lại có backoff theo adapter | Nack vô hạn trong vòng lặp nóng |
| Polling endpoint đọc từ DB | Rollback/giữ message trong nguồn theo transaction | Đã lấy khỏi nguồn rồi return bình thường làm mất message |
| Hàng đợi retry bền vững | Delay/requeue có giới hạn và giữ cùng idempotency key | Reset attempt budget sau mỗi lần phát lại |
| Công việc không còn giá trị sau deadline | Ghi trạng thái expired hoặc business failure | Giữ thread chờ lock sau khi request đã hết hạn |

**Quan trọng:** Với QueueChannel, poller, JMS/AMQP/Kafka adapter, cách **ack/commit/offset/redelivery** thay đổi theo nguồn và cấu hình. Không suy diễn “ném LockBusyException là message chắc chắn được giao lại” nếu chưa kiểm tra transaction và acknowledgement của adapter tương ứng.

## 8. Lock timeout liên quan thế nào tới retry và error handling?

Một message bị lock contention có thể đi qua nhiều tầng retry:

~~~text
Broker redelivery: tối đa 4 deliveries
  → Handler RetryAdvice: tối đa 3 attempts
      → tryLock(250 ms) trong mỗi attempt
~~~

Nếu mọi lần đều chờ hết hạn, **tối đa 12 lần chờ lock** có thể xảy ra cho cùng một nghiệp vụ (chưa kể scheduler phát lại và caller retries). Chỉ riêng phần chờ đã có thể lên đến **12 × 250 ms = 3 giây** khi chạy tuần tự, chưa tính backoff, dispatch, I/O và điều kiện chồng lấn.

Để tránh retry storm:

1. Chỉ định **retry owner** cho lock contention: tại handler, broker hoặc scheduled replay; thống nhất giới hạn tổng.
2. Dùng **backoff + jitter** nếu nhiều consumer đang tranh cùng một lock.
3. Giữ cùng **business idempotency key** qua mọi attempt và redelivery.
4. Đặt **timeout theo ngân sách còn lại**, không đặt 250 ms mới vô hạn lần khi caller đã hết deadline.
5. Sau khi hết budget, ghi **FailureJournal/DLQ/quarantine** hoặc trạng thái nghiệp vụ rõ ràng.
6. Đừng retry mọi exception giống nhau: dữ liệu sai hoặc permission denied thường không cải thiện khi chờ lock.

**ErrorMessage** trên errorChannel chỉ biểu thị lỗi đã được publish qua cơ chế phù hợp; nó không tự làm message quay lại input channel. Khi lỗi phát sinh sau **ExecutorChannel**, caller có thể đã hoàn thành send. Error flow cần đọc **failedMessage/originalMessage** nếu có để tìm business key, correlationId, attempt và nguyên nhân.

### Timeout khi chờ lock không phải transaction rollback tự động

Nếu handler tự catch timeout rồi trả về bình thường, transaction phía ngoài có thể commit theo cấu hình. Ngược lại, exception ném ra **có thể** khiến transaction rollback, nhưng còn phụ thuộc rollback rules và transaction boundary. Phải test cụ thể chuỗi **poller → channel → handler → store → adapter**.

## 9. Lock và transaction: giữ được điều gì?

Lock bảo vệ **critical section** theo khóa và implementation; transaction bảo vệ **atomicity** của tập thao tác trên resource tương thích. Chúng giải quyết hai vấn đề có liên hệ nhưng không thay thế nhau.

Ví dụ:

~~~text
T1: lấy lock(order:O-42)
T2: mở/đang ở transaction DB
T3: kiểm tra trạng thái → update DB
T4: DB commit
T5: unlock
~~~

Thứ tự này thường dễ hiểu: quyền độc quyền được giữ **qua thời điểm commit**. Nhưng nếu code dùng **@Transactional** bao quanh method còn lock được giải phóng trong phần thân method **trước khi proxy transaction commit**, có thể tạo một khoảng hở: worker khác lấy lock trong lúc thay đổi DB chưa commit. Cần rà lại **transaction interceptor nằm ngoài hay trong đoạn lock** và dùng DB concurrency control khi tính đúng đắn phụ thuộc commit.

**Ví dụ rủi ro:**

~~~text
@Transactional proxy bắt đầu transaction
  → handle(): acquire lock → update DB → unlock → return
@Transactional proxy mới commit transaction

Worker B lấy lock sau unlock nhưng trước commit của worker A.
~~~

Với việc cập nhật DB quan trọng, ưu tiên **unique constraint**, **optimistic locking** hoặc giao dịch có điều kiện để tính đúng đắn không phụ thuộc hoàn toàn vào lock ở tầng ứng dụng. Không đặt giao dịch dài chứa HTTP call vô hạn trong lock.

### Lock không tự chạy xuyên thread boundary

~~~mermaid
flowchart LR
    P["Poller / transaction A"] --> D["DirectChannel"]
    D --> H["Handler giữ lock"]
    P --> E["ExecutorChannel"]
    E --> W["Worker thread B<br/>transaction B nếu cấu hình"]
~~~

- **DirectChannel** gọi đồng bộ trong thread sender. Có thể dùng cùng transaction khi resource/advice phù hợp; nhiều sender khác nhau vẫn có thể gọi handler đồng thời.
- **ExecutorChannel** chuyển sang thread pool. Transaction và ThreadLocal của sender không tự truyền qua; lock chỉ được giữ nếu có code cụ thể giữ/acquire lock ở worker.
- **QueueChannel** và polling endpoint thường tạo lần tiêu thụ/transaction mới; timeout của lock ở consumer không nhất thiết quay về producer.

Đừng acquire lock trên thread A rồi giao critical section sang thread B và để B gọi unlock. Với nhiều **Lock** implementation, quyền sở hữu gắn với thread đã acquire; unlock từ thread khác có thể lỗi hoặc vi phạm contract. Chọn lock ở đúng vị trí thực thi phần nghiệp vụ.

## 10. LockRegistry trong aggregator và MessageGroupStore

**Aggregator**, **resequencer** và correlating endpoints thường có state theo **groupId** trong **MessageGroupStore**. Hai message cùng groupId đến đồng thời có thể đụng nhau khi add, đánh giá release strategy hoặc mark group complete.

~~~mermaid
flowchart TD
    M1["Message A<br/>groupId=O-42"] --> L["Lock theo groupId"]
    M2["Message B<br/>groupId=O-42"] --> L
    L --> S[("MessageGroupStore")]
    S --> R{"ReleaseStrategy<br/>đã đủ?"}
    R -- "Chưa" --> S
    R -- "Đủ" --> G["MessageGroupProcessor + output"]
~~~

Với correlating handler, Spring Integration có cơ chế sử dụng **LockRegistry** để đồng bộ thao tác nhóm. **LockRegistry mặc định thường chỉ có phạm vi JVM**; khi nhiều instance cùng truy cập store persistent, phải xem **distributed locking** hoặc cơ chế concurrency có thể thay thế được.

Không nên tự thêm lock ở service activator với **key khác groupId** rồi cho rằng aggregator đã an toàn: code của aggregator phải thực sự được bảo vệ bằng cơ chế mà endpoint sử dụng. Cũng không nên bọc một lock thủ công bên ngoài một aggregator dùng loại lock khác mà không phân tích **thứ tự acquire**, vì dễ gây deadlock.

**Nhớ phân biệt các trạng thái:**

- **Release**: release strategy cho phép group tạo output.
- **Complete**: group được đánh dấu hoàn tất.
- **Expire**: group/metadata bị xóa theo chính sách.
- **Late arrival**: message đến sau completion có thể bị discard hoặc tạo group mới nếu metadata đã xóa.

Lock bảo vệ vùng cập nhật state; nó **không** quyết định release condition, expiry, deduplication hoặc khả năng sống sót sau crash. MessageStore persistent và idempotency vẫn cần thiết để xử lý đúng trong runtime.

## 11. Lease hết hạn và stale writer: bài toán khó nhất

Một distributed lock có thể cần **lease TTL** để tránh giữ khóa mãi khi instance crash. Nhưng TTL cũng tạo tình huống worker cũ vẫn chạy sau khi lease hết:

~~~text
00:00  Instance A lấy lock K, lease 5 giây
00:02  A bắt đầu gọi DB, bị dừng do GC/network
00:05  Lease của A hết; backend cho phép lock được cấp lại
00:06  Instance B lấy lock K và cập nhật version 8
00:07  A hoạt động trở lại, cố ghi dữ liệu version 7
~~~

Nếu DB không biết writer nào đang cũ, A có thể ghi đè dữ liệu mới. **tryLock thành công trong quá khứ không chứng minh quyền sở hữu còn hợp lệ tại hiện tại**.

### Giảm rủi ro bằng version/fencing

Ví dụ một bản ghi có trường **version**:

~~~sql
UPDATE orders
SET status = :newStatus, version = version + 1
WHERE id = :orderId AND version = :expectedVersion;
~~~

Nếu A dùng expectedVersion=7 nhưng B đã cập nhật thành version=8, số dòng được cập nhật là **0** và A phải xử lý conflict thay vì ghi đè. Khi yêu cầu chống stale writer trên nhiều loại resource, **fencing token đơn điệu** được resource kiểm tra có thể phù hợp hơn nếu backend hỗ trợ.

**Phân biệt:** Version check của DB không giải quyết trọn vẹn việc A đã gọi HTTP bên ngoài trước đó. Với external side effect, cần idempotency key tại phía đích, đối soát hoặc cơ chế bù trừ. Các hệ thống phân tán có failure mode riêng như split-brain, mất kết nối và clock skew.

### Khi unlock thất bại

Một implementation distributed lock có thể không cho unlock nếu ownership đã hết hoặc backend không khả dụng. Không bỏ qua lỗi này:

- Ghi nhận nguyên nhân, lockKey, thread/instance và thời gian giữ lock.
- Phân biệt **lỗi thao tác nghiệp vụ** với **lỗi giải phóng lock**; tránh để exception ở finally vô tình che mất nguyên nhân ban đầu trong log/trace.
- Không thử unlock trên một thread khác một cách tùy tiện.
- Dùng health check, alert, cleanup/lease expiry theo đặc tính backend, không tự xóa lock đang thuộc về tiến trình khác.

Thời gian giữ lock lý tưởng càng ngắn càng tốt, nhưng phải đủ để bảo vệ **toàn bộ invariant quan trọng**. Chỉ giảm thời gian bằng cách unlock sớm khi DB vẫn chưa commit có thể khiến dữ liệu sai.

## 12. Kiểm thử tryLock và timeout trong một JVM

Đây là test JUnit 5 dùng **DefaultLockRegistry** để xác minh **timeout khi một thread khác đang giữ cùng key**. Dùng latch/future thay vì sleep cố định:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.*;
import java.util.concurrent.locks.Lock;
import org.junit.jupiter.api.Test;
import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.integration.support.locks.LockRegistry;

class LockTimeoutTest {

    @Test
    void timedTryLockFailsWhenAnotherThreadHoldsSameKey() throws Exception {
        LockRegistry registry = new DefaultLockRegistry();
        String key = "order:O-42";
        Lock primary = registry.obtain(key);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        primary.lock();
        try {
            Future<Boolean> attempted = pool.submit(() -> {
                Lock contender = registry.obtain(key);
                boolean acquired =
                        contender.tryLock(100, TimeUnit.MILLISECONDS);
                if (acquired) {
                    contender.unlock();
                }
                return acquired;
            });

            assertFalse(attempted.get(2, TimeUnit.SECONDS));
        } finally {
            primary.unlock();
            pool.shutdownNow();
        }

        // Sau release, một lần thử mới có thể lấy lock.
        Lock next = registry.obtain(key);
        assertTrue(next.tryLock());
        next.unlock();
    }
}
~~~

Test này có ý nghĩa vì hai thread **thực sự tranh cùng key**; nếu thử lấy lock hai lần liên tiếp trong cùng thread với một lock **reentrant**, lần thứ hai có thể thành công và test đưa kết luận sai.

**Các biến thể nên thêm:**

1. **tryLock() fail-fast:** thread B nhận false khi A đang giữ lock.
2. **Timed wait thành công:** A thả lock trước khi hết timeout của B; B lấy được và tự unlock.
3. **Interrupt:** B đang chờ timed tryLock bị interrupt; kiểm tra xử lý InterruptedException, không báo xử lý nghiệp vụ thành công.
4. **Khác key:** A giữ order:O-42 không chặn xử lý order:O-43.
5. **Exception trong critical section:** repository ném lỗi; lock vẫn được release bởi finally.
6. **Nhiều producer:** gửi các message cùng orderId vào handler trên nhiều worker, xác minh không có hai critical section cùng chạy.
7. **Không leak:** sau hàng nghìn lần lỗi, các message cùng key vẫn lấy lock được và không làm pool treo.

### Một test xác minh critical section không chồng lấn

Có thể dùng **AtomicInteger active** và **AtomicInteger maxActive** trong một fake repository. Mỗi lần bắt đầu xử lý, tăng active, cập nhật maxActive, rồi giảm active trong finally. Khi tất cả message **cùng key** được xử lý thành công, **maxActive phải bằng 1**. Với message khác key, cho phép maxActive lớn hơn 1 để chứng minh lock không vô tình khóa toàn hệ thống.

Đừng coi test với DefaultLockRegistry là bằng chứng cho Redis/JDBC trong cluster. Distributed lock cần môi trường test thực tế hơn để kiểm chứng failover và network failure.

## 13. Kiểm thử distributed lock, crash và transaction

Các tình huống quan trọng cho test tích hợp:

| Ca | Cách tạo tình huống | Kết quả phải kiểm chứng |
| --- | --- | --- |
| Hai instance cùng key | A giữ lock K, B timed tryLock K | B không vào critical section trước khi được cấp lock |
| Hai instance khác key | A giữ K1, B lấy K2 | Hai xử lý có thể song song, không khóa quá rộng |
| Timeout chờ lock | A giữ lâu hơn wait timeout của B | B báo BUSY/timeout và đi đúng retry/recovery |
| Đóng instance đang giữ lock | Kill A sau acquire | Backend giải phóng/cho phép phục hồi theo contract của lease; không có deadlock vĩnh viễn |
| Mất kết nối DB/Redis | Ngắt kết nối đúng thời điểm acquire/unlock | Lỗi hạ tầng quan sát được, không coi như đã acquire |
| Lease hết khi A vẫn xử lý | A chậm quá lease, B lấy cùng key | Stale writer bị chặn bằng version/fencing/idempotency |
| Transaction commit chậm | A unlock trước khi commit | Test phát hiện và xử lý khoảng hở concurrency |
| Retry/redelivery | Cùng eventId được giao lại nhiều lần | Không tạo side effect trùng |
| Executor saturation | Nhiều message chờ cùng key | Pool/queue không bị chặn vô thời hạn, có backpressure |
| Restart flow với MessageStore | Message pending được phục hồi | Lock cũ hết hạn/được phục hồi; state vẫn nhất quán |

**Không chỉ xác minh boolean acquire.** Kiểm tra số bản ghi DB, event phát ra, phiên bản dữ liệu, trạng thái message store, số lần retry, lock ownership và tác dụng tại hệ thống ngoài. Một bài test chỉ biết B trả false không chứng minh B không ghi DB theo một nhánh code khác.

## 14. Quan sát runtime và chẩn đoán hiệu năng

Khi chẩn đoán “flow chạy chậm” hoặc “message bị kẹt”, lock contention là một nguyên nhân cần kiểm tra cùng với poller backlog, executor saturation và DB latency.

| Tín hiệu | Điều cần đặt câu hỏi |
| --- | --- |
| **lock wait latency p50/p95/p99** | Key nào bị tranh chấp? Deadline có đủ không? |
| **tryLock success/failure rate** | Hết thời gian chờ vì contention thật hay backend lỗi? |
| **lock hold duration** | Handler đang giữ lock qua HTTP/DB transaction bao lâu? |
| **active/blocked workers** | Có thread pool bị chiếm bởi lock() hoặc timed tryLock lâu không? |
| **backend lock errors** | Redis/DB/ZooKeeper có timeout, failover, session expiry không? |
| **stale lease / unlock failures** | Lease quá ngắn, process pause hay quyền sở hữu đã mất? |
| **broker redelivery / RetryAdvice attempts** | Retry do contention có tạo storm không? |
| **group release latency** | Aggregator chờ lock, chờ message hay ReleaseStrategy tính chậm? |
| **duplicate/conflict count** | Lock key không thống nhất hoặc store/idempotency chưa đủ? |

Ví dụ log có cấu trúc do ứng dụng chủ động phát:

~~~text
flow=orderUpdate endpoint=orderUpdateHandler
orderId=O-42 eventId=E-19 correlationId=checkout-42
lockKey=order-update:O-42
lockWaitMs=250 acquired=false
backend=redis thread=order-worker-8
decision=DELAYED_RETRY attempt=2
~~~

Nên log **lockKey đã rút gọn/an toàn**, tránh chứa PII hoặc token. Đo **thời gian giữ** và **thời gian chờ** riêng: tăng timeout có thể làm giảm tỷ lệ BUSY nhưng lại tăng latency, giữ nhiều thread và giảm throughput.

### Checklist chẩn đoán nhanh

1. **Có đúng registry không?** Mỗi instance có đang dùng một DefaultLockRegistry riêng trong khi state là DB chung?
2. **Có cùng key không?** Key có bị thêm attemptId, case khác hoặc thiếu namespace?
3. **Đang chờ gì?** tryLock timed, lock() vô hạn, DB transaction, HTTP call hay broker ack?
4. **Chờ bao lâu?** Lock wait timeout có lớn hơn caller deadline, poller interval hoặc executor budget?
5. **Ai còn giữ lock?** Thread bị treo, DB commit chậm, lease renewal thất bại hay lock đã hết TTL?
6. **Khi false thì sao?** Handler ném exception/retry, hay âm thầm return và đánh dấu message hoàn tất?
7. **Sau unlock thì sao?** DB đã commit chưa; worker cũ có thể ghi sau lease expiry không?
8. **Thông điệp lỗi ở đâu?** Có ErrorMessage, failedMessage, correlationId và idempotency key để điều tra không?

## 15. Bài thực hành: xử lý cập nhật đơn hàng an toàn

**Đề bài:** Một Spring Integration flow nhận cập nhật đơn hàng từ broker. Có ba worker trong mỗi instance, hai instance cùng truy cập DB. Một số message trùng eventId; có lúc một worker xử lý chậm 8 giây. Mỗi message có deadline 2 giây nếu request đồng bộ, nhưng event từ broker có thể retry bền vững sau đó.

Yêu cầu:

- Message cùng **orderId** không được cập nhật trạng thái song song sai nghiệp vụ.
- Message khác orderId không bị chặn bởi một lock toàn cục.
- Khi lock bận, không chiếm worker quá **200 ms** trong một lần thử.
- Không đếm hai lần cùng **eventId**.
- Nếu backend lock mất kết nối hoặc lease hết, hệ thống không ghi đè bản cập nhật mới.
- Nếu đã hết ngân sách retry, lỗi có trạng thái cuối rõ ràng.

**Hướng thiết kế:**

1. Dùng **LockRegistry phân tán** vì có hai instance; tạo lock key **order-update:{tenant}:{orderId}**.
2. Gọi **tryLock(200, MILLISECONDS)** tại consumer, trước khi chạy critical section.
3. Với false, trả lỗi có thể phân loại để scheduled retry/broker redelivery **có backoff**, theo một retry owner và ngân sách giới hạn.
4. Với true, thực hiện transaction/điều kiện DB có **unique eventId** và **version**; dùng exception/rollback đúng nghĩa.
5. Thời gian giữ lock phải được kiểm soát. Không gọi HTTP chậm trong lock trừ khi yêu cầu bắt buộc và cơ chế lease/ownership đủ an toàn.
6. Khi unlock/backend fail, ghi **lock outcome** và trạng thái nghiệp vụ riêng; có cảnh báo và quy trình đối soát.
7. Consumer downstream xử lý event idempotent; luồng phát event quan trọng dùng outbox nếu cần sống qua crash.
8. Test ít nhất hai JVM, các ca contention, timeout, retry, stale lease và restart.

### Các câu hỏi tự kiểm tra

**Câu 1:** Một worker gọi **tryLock(300, MILLISECONDS)**, nhận false rồi return bình thường. Message từ broker có chắc chắn được phát lại không?

**Trả lời:** **Không.** Tùy cấu hình adapter/ack/transaction, việc handler hoàn tất bình thường có thể được hiểu là đã xử lý. Muốn retry phải nêu rõ policy, ném exception hoặc tạo durable retry/recovery theo hợp đồng nguồn.

**Câu 2:** Worker lấy được distributed lock rồi chạy 10 giây, lease chỉ 5 giây. Nó có chắc vẫn là owner không?

**Trả lời:** **Không.** Backend có thể hết lease và cấp lock cho worker khác; cần xác minh renewal/ownership của implementation và bảo vệ DB bằng version/fencing/idempotency.

**Câu 3:** Nếu lock được thả trong finally nhưng DB transaction chỉ commit sau khi method trả về, hai worker có chắc không đọc trạng thái chưa commit không?

**Trả lời:** **Không.** Có khoảng hở giữa unlock và commit. Cần điều chỉnh ranh giới lock/transaction hoặc để DB thực thi invariant bằng concurrency control.

**Câu 4:** Vì sao test trong một JVM bằng DefaultLockRegistry chưa đủ để kết luận hoạt động đúng khi scale hai replica?

**Trả lời:** Vì hai replica có **registry và lock riêng**; chỉ distributed backend hoặc cơ chế concurrency chung mới có thể phối hợp giữa JVM. Cần test với ít nhất hai instance và nguồn dữ liệu dùng chung.

## 16. Checklist trước khi triển khai

- Lock key là **business/correlation key ổn định**, không phải message ID/attempt ID?
- Có phân biệt đúng **LockRegistry.obtain()** với việc đã acquire lock?
- Khi dùng tryLock(timeout), đã kiểm tra **true/false** và **InterruptedException**?
- Chỉ unlock trong **finally** sau acquire thành công, trên đúng thread sở hữu?
- Lock wait timeout, transaction timeout, HTTP timeout, message deadline và lease TTL đã được xác định riêng?
- Với nhiều JVM, có registry phân tán và kiểm thử failover thay vì DefaultLockRegistry?
- Có xử lý trường hợp lease hết khi worker còn chạy, bằng version/fencing và idempotency?
- Lock chỉ bảo vệ invariant cần thiết, không dùng một key toàn cục gây nghẽn không cần thiết?
- Khi không lấy được lock, message có đường **retry/recovery** rõ ràng, không bị ack thành công giả?
- Có tránh retry nóng/lồng nhiều tầng và giữ budget qua broker redelivery?
- Lock/transaction được đặt đúng thread và ranh giới **commit**?
- Aggregator, MessageGroupStore và các consumer cùng key có sử dụng cơ chế khóa thống nhất?
- Có log/metric cho contention, hold time, timeout, backend error, unlock failure và correlation?
- Có test fail-fast, timed wait, interrupt, concurrency, lease expiry, multi-instance và restart?

## Kết luận

**tryLock** là công cụ kiểm soát contention trong Spring Integration Runtime: có thể thử ngay hoặc chờ một khoảng hữu hạn, rồi đưa message qua nhánh retry/recovery nếu chưa lấy được lock. **LockRegistry** cung cấp lock theo khóa, còn implementation quyết định phạm vi JVM hay phân tán.

Thiết kế đúng cần nhìn cả **channel, endpoint, consumer, poller, executor, transaction, retry, message store và correlation**. Không nhầm **thời gian chờ lock** với **lease TTL**, không unlock trước khi invariant được bảo vệ, và không xem lock như bảo đảm exactly-once. Kết hợp **deadline, idempotency, DB concurrency control, observability và test đa instance** để flow có thể phục hồi an toàn khi contention hoặc backend lỗi.

## Tài liệu tham khảo

- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html)
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration API — LockRegistry](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/locks/LockRegistry.html)
- [Java SE API — Lock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html)
