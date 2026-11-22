# LockRegistry và đồng bộ group

Trong Spring Integration, **correlation** xác định những message thuộc cùng một công việc; **group** là trạng thái tích lũy của những message có chung correlation key. Aggregator và resequencer có thể nhận nhiều message cùng nhóm gần như đồng thời từ <code>ExecutorChannel</code>, poller hoặc nhiều instance ứng dụng. Nếu hai consumer cùng cập nhật, kiểm tra điều kiện release hoặc hoàn tất một group thiếu đồng bộ, hệ thống có thể ghép thiếu dữ liệu, release hai lần hoặc lưu metadata sai.

Bài học thuộc chương **Correlation runtime** của **SPRING_INTEGRATION_RUNTIME**. Trọng tâm là <code>LockRegistry</code>: cách Spring Integration khóa các thao tác trên group, khác biệt giữa khóa trong một JVM và khóa phân tán, cũng như liên hệ với <code>MessageGroupStore</code>, transaction, retry, timeout, error flow, threading, hiệu năng và lifecycle.

> **Điểm cần nhớ:** <code>LockRegistry</code> bảo vệ *critical section* khi thao tác với một group. Nó **không tự tạo transaction**, không bảo đảm mỗi message chỉ được giao một lần và không thể thay thế idempotency hoặc ràng buộc duy nhất của nghiệp vụ.

## 1. Vì sao correlation group cần đồng bộ?

Một aggregator có thể gom ba mảnh của cùng một batch:

~~~text
batchId = B-42
  ├─ fragment A đến từ executor thread-1
  ├─ fragment B đến từ executor thread-2
  └─ fragment C đến từ executor thread-3
       ↓
  cùng một MessageGroup(B-42)
       ↓
  release khi đủ ba fragment
~~~

Trạng thái nhóm được duy trì trong một <code>MessageGroupStore</code>, thường bao gồm message đã nhận, condition, trạng thái hoàn tất và metadata phục vụ resequencing hoặc expiration. Khi một message đến, correlating handler thực hiện về mặt khái niệm:

1. Tính **correlation key** từ message (mặc định có thể dùng header <code>correlationId</code>, hoặc một strategy tùy chỉnh).
2. Lấy lock tương ứng với key của group.
3. Kiểm tra/truy xuất group trong <code>MessageGroupStore</code>.
4. Thêm message, cập nhật group và đánh giá <code>ReleaseStrategy</code>.
5. Nếu đủ điều kiện, chuẩn bị kết quả, đánh dấu/giải phóng group theo chính sách.
6. Hoàn tất phần xử lý trong phạm vi khóa và trả lock theo logic của handler.

~~~mermaid
sequenceDiagram
    participant T1 as Thread-1
    participant T2 as Thread-2
    participant L as LockRegistry
    participant S as MessageGroupStore
    participant A as Aggregator
    T1->>L: lock("B-42")
    L-->>T1: acquired
    T2->>L: lock("B-42")
    Note over T2,L: Thread-2 chờ cùng group
    T1->>S: add(fragment A)
    T1->>A: kiểm tra release
    T1->>L: unlock("B-42")
    L-->>T2: acquired
    T2->>S: add(fragment B)
    T2->>A: kiểm tra release
    T2->>L: unlock("B-42")
~~~

Nếu không có khóa bao quanh **toàn bộ quyết định đọc–sửa–đánh giá**, hai thread có thể đều nhìn thấy group chưa đủ, ghi đè metadata hoặc cùng cho rằng mình là thread đầu tiên release. Chỉ dùng một cấu trúc lưu trữ thread-safe cho từng thao tác <code>add</code> đơn lẻ chưa chắc bảo đảm tính nguyên tử cho một chuỗi thao tác.

## 2. Ba khái niệm phải tách biệt

| Khái niệm | Bảo vệ điều gì? | Điều không được bảo đảm |
|---|---|---|
| <code>LockRegistry</code> | Quyền độc quyền xử lý cùng lock key tại cùng một thời điểm trong phạm vi registry | Không rollback DB, không bảo đảm message không được gửi lại |
| <code>MessageGroupStore</code> | Lưu message/metadata của group; có thể bền vững theo backend | Persistent store không có nghĩa thao tác đa bước tự được đồng bộ giữa các node |
| Transaction manager | Commit/rollback các tài nguyên có tham gia transaction | Không tự khóa tất cả correlation group; không giao dịch nguyên tử xuyên broker/API độc lập |
| Idempotency nghiệp vụ | Chặn side effect trùng khi retry/redelivery hoặc nhóm được tạo lại | Không thay thế lock khi nhiều thread cần sửa metadata cùng lúc |

Trong một hệ thống tin cậy, **khóa để tránh race**, **transaction để bảo đảm thay đổi dữ liệu nhất quán** và **idempotency để sống chung với redelivery** cần phối hợp.

## 3. LockRegistry API và khóa theo group ID

Spring Integration định nghĩa <code>org.springframework.integration.support.locks.LockRegistry</code>:

~~~java
LockRegistry registry = new DefaultLockRegistry();
Lock lock = registry.obtain("B-42");

lock.lock();
try {
    // Thao tác cần loại trừ đồng thời theo B-42
} finally {
    lock.unlock();
}
~~~

<code>obtain(Object lockKey)</code> trả về một <code>java.util.concurrent.locks.Lock</code>. Với một correlating handler, key được dùng cho việc khóa gắn với **group ID đã resolve**. Vì vậy:

- Message có **cùng** group ID tranh cùng lock và được xử lý tuần tự trong phạm vi được khóa.
- Message có **khác** group ID có khả năng xử lý đồng thời nếu registry phân bổ lock riêng.
- Một key phải ổn định, có <code>equals()</code>/<code>hashCode()</code> hợp lý và có biểu diễn nhất quán trên các node.
- Một nhóm chỉ an toàn trên cluster khi **mọi instance** cùng tôn trọng cùng không gian khóa.

Từ Spring Integration **6.2**, <code>LockRegistry</code> có tiện ích <code>executeLocked(...)</code> để giảm nguy cơ quên <code>unlock()</code>:

~~~java
LockRegistry registry = new DefaultLockRegistry();

registry.executeLocked("B-42", () -> {
    updateSomeSharedState();
});
~~~

Đoạn này minh họa API cho **một critical section do ứng dụng tự quản lý**. Khi cấu hình <code>LockRegistry</code> cho aggregator, framework đã quản lý việc lấy/trả lock; thông thường **không cần** tự khóa thêm quanh mọi lời gọi gửi message.

### DefaultLockRegistry không phải “một ReentrantLock cho mỗi group”

<code>DefaultLockRegistry</code> là registry in-memory dựa trên các <code>ReentrantLock</code> được chia theo *stripe*. Cấu hình mặc định sử dụng 256 lock; khóa được chọn từ hash của key. Vì thế, **hai key khác nhau vẫn có thể va vào cùng một stripe** và phải chờ nhau. Điều này không sai về tính nhất quán, nhưng tạo contention và có thể giới hạn throughput trong tải cao.

<code>DefaultLockRegistry</code> chỉ đồng bộ những thread dùng **cùng registry instance trong một JVM**. Hai pod chạy hai JVM riêng biệt, dù mỗi pod có một bean cùng tên, vẫn có hai bộ lock độc lập.

## 4. Ví dụ Java DSL: nhiều fragment cùng batch trong một instance

Ví dụ dưới đây dùng Java 17+ và Spring Integration 6.x. Mỗi batch có ba fragment; hai batch khác nhau có thể được xử lý đồng thời, còn fragment của cùng batch được đồng bộ khi cập nhật group. Output aggregator mặc định là một message chứa tập hợp các payload fragment.

~~~java
public record Fragment(String fragmentId, String value) {}

@Configuration
@EnableIntegration
public class BatchFlowConfig {

    @Bean(name = "fragments.input")
    MessageChannel fragmentsInput() {
        return new DirectChannel();
    }

    @Bean(name = "fragments.completed")
    PollableChannel fragmentsCompleted() {
        return new QueueChannel();
    }

    @Bean
    MessageGroupStore fragmentGroupStore() {
        return new SimpleMessageStore();
    }

    @Bean
    LockRegistry fragmentGroupLocks() {
        return new DefaultLockRegistry();
    }

    @Bean
    IntegrationFlow fragmentFlow(
            @Qualifier("fragments.input") MessageChannel input,
            MessageGroupStore fragmentGroupStore,
            LockRegistry fragmentGroupLocks) {
        return IntegrationFlow.from(input)
            .aggregate(a -> a
                .messageStore(fragmentGroupStore)
                .lockRegistry(fragmentGroupLocks)
                .correlationStrategy(
                    message -> message.getHeaders().get("batchKey"))
                .releaseStrategy(group -> group.size() >= 3)
                .expireGroupsUponCompletion(false)
                .releaseLockBeforeSend(true))
            .channel("fragments.completed")
            .get();
    }
}
~~~

Những import chính:

~~~java
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.store.MessageGroupStore;
import org.springframework.integration.store.SimpleMessageStore;
import org.springframework.integration.support.locks.LockRegistry;
import org.springframework.integration.support.locks.DefaultLockRegistry;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.beans.factory.annotation.Qualifier;
~~~

Để gửi fragment:

~~~java
Message<Fragment> fragment = MessageBuilder
    .withPayload(new Fragment("F1", "data-A"))
    .setHeader("batchKey", "tenant-7:B-42")
    .build();

fragmentsInput.send(fragment);
~~~

<code>MessageBuilder</code> ở đây thuộc <code>org.springframework.integration.support</code>; <code>fragmentsInput</code> là bean <code>fragments.input</code>. Sau khi đủ ba message, có thể gọi <code>fragmentsCompleted.receive(timeout)</code> để lấy kết quả trong test.

**Ý nghĩa của cấu hình:**

1. <code>correlationStrategy</code> lấy <code>batchKey</code>, do đó tất cả fragment có header <code>tenant-7:B-42</code> được đưa vào một group.
2. <code>messageStore</code> giữ trạng thái group; ví dụ dùng <code>SimpleMessageStore</code> trong bộ nhớ.
3. <code>lockRegistry</code> quyết định khóa nào được lấy khi xử lý group.
4. <code>releaseStrategy</code> đánh giá điều kiện đủ ba phần; đây là **quy tắc release**, không phải chức năng của lock.
5. <code>expireGroupsUponCompletion(false)</code> giữ metadata hoàn tất để xử lý message đến muộn theo chính sách mặc định; cần chiến lược dọn metadata về sau.
6. <code>releaseLockBeforeSend(true)</code> giảm nguy cơ giữ group lock trong lúc gửi output đến downstream, đặc biệt nếu downstream có luồng gọi lại hoặc lock khác.

Đây là một bài thực hành cho **một JVM**. Không thể lấy bean <code>fragmentGroupLocks</code> ở mỗi pod khác nhau rồi suy ra hai pod đã đồng bộ trên cùng group.

### Khi có ExecutorChannel thì chuyện gì đổi?

Nếu message đi qua một <code>ExecutorChannel</code> trước aggregator, nhiều thread có thể đến handler cùng lúc. Khóa group vẫn giới hạn truy cập trạng thái của cùng key trong một JVM, nhưng mỗi thread có thể phải chờ. Executor không tạo một transaction chung cho mọi fragment; nếu mỗi message có transaction riêng, việc lock acquisition, ghi store, commit và retry phải được phân tích theo transaction manager thực tế.

## 5. Nhiều instance cùng MessageGroupStore: cần khóa phân tán

Giả sử hai replica A và B cùng dùng một <code>JdbcMessageStore</code>. Mỗi replica có local lock riêng:

~~~mermaid
flowchart TD
    PA["Replica A<br/>DefaultLockRegistry"] --> GA["Group B-42"]
    PB["Replica B<br/>DefaultLockRegistry"] --> GB["Group B-42"]
    GA --> S[("Shared JDBC MessageGroupStore")]
    GB --> S
    N["Hai JVM không dùng chung bộ ReentrantLock"] -.-> GA
    N -.-> GB
~~~

Replica A và B **đều có thể lấy local lock cùng lúc**, cùng đọc một trạng thái group và cùng quyết định release. Chuyển sang persistent store không giải quyết race này.

Giải pháp là cấu hình <code>LockRegistry</code> dùng tài nguyên chung, chẳng hạn:

| Registry | Nguồn đồng bộ | Khi thích hợp | Điều phải vận hành |
|---|---|---|---|
| <code>DefaultLockRegistry</code> | Bộ nhớ của một JVM | Một instance, hoặc group được phân vùng chắc chắn chỉ tới một JVM | Contention, kích thước stripe, lifecycle của process |
| <code>JdbcLockRegistry</code> | Bảng lock trong RDBMS qua <code>LockRepository</code> | Dùng chung database và muốn khóa giữa các replica | DDL, transaction manager, TTL, lock renewal, độ trễ DB |
| <code>RedisLockRegistry</code> | Key/lease trên Redis | Nhiều instance có Redis dùng chung | Lease expiry, renewal, failover, cache và network |
| <code>ZookeeperLockRegistry</code> | Coordination qua ZooKeeper | Hệ thống đã có ZooKeeper và cần phân quyền truy cập giữa các node | Session, kết nối và trạng thái cluster |

Các registry phân tán bảo đảm các instance **hợp tác theo cùng lock key và namespace**. Tính đúng còn phụ thuộc semantics của registry, điều kiện kết nối, thời hạn lease và cách các node xử lý khi mất quyền sở hữu lock.

### Ví dụ dùng JdbcLockRegistry cho hai replica

Đây là cấu hình một replica. Replica còn lại phải dùng **cùng database, cùng vùng store và vùng lock**, nhưng mỗi replica có bean <code>DefaultLockRepository</code> riêng do ứng dụng đó quản lý.

~~~java
@Configuration
public class SharedGroupInfrastructure {

    @Bean
    DefaultLockRepository groupLockRepository(
            DataSource dataSource,
            PlatformTransactionManager transactionManager) {
        DefaultLockRepository repository =
            new DefaultLockRepository(dataSource);
        repository.setRegion("batch-aggregator-lock");
        repository.setTransactionManager(transactionManager);
        return repository;
    }

    @Bean(name = "distributedGroupLocks")
    LockRegistry distributedGroupLocks(DefaultLockRepository groupLockRepository) {
        return new JdbcLockRegistry(groupLockRepository);
    }

    @Bean
    MessageGroupStore sharedGroupStore(
            DataSource dataSource,
            @Qualifier("distributedGroupLocks") LockRegistry groupLocks) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion("batch-aggregator");

        // Chỉ áp dụng khi dùng Spring Integration 6.5+.
        store.setLockRegistry(groupLocks);
        return store;
    }
}
~~~

Các kiểu bổ sung:

~~~java
import javax.sql.DataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.integration.jdbc.lock.DefaultLockRepository;
import org.springframework.integration.jdbc.lock.JdbcLockRegistry;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
~~~

Trong flow aggregator, thay <code>SimpleMessageStore</code> bằng bean <code>sharedGroupStore</code> và truyền bean <code>distributedGroupLocks</code> vào <code>.lockRegistry(...)</code>. Hai node phải dùng cùng quy tắc <code>batchKey</code>. Các schema bảng cho <code>JdbcMessageStore</code> và <code>DefaultLockRepository</code> cần được khởi tạo theo scripts dành cho RDBMS tương ứng trước khi chạy; cấu hình này không tự tạo bảng.

**Phân biệt theo phiên bản:** trước Spring Integration 6.5, <code>AbstractCorrelatingMessageHandler</code> đã có cấu hình <code>lockRegistry</code> cho thao tác group của handler. Từ **6.5**, <code>AbstractMessageGroupStore.setLockRegistry(...)</code> hỗ trợ khóa cho các thay đổi metadata/group ở tầng store. Chúng là **hai điểm bảo vệ liên quan nhưng không đồng nhất**. Nếu hệ thống dùng 6.5+, hãy đánh giá sử dụng registry nhất quán cho cả hai nơi trong khi tránh tự tạo những vòng lấy lock lồng nhau không cần thiết.

## 6. Lock key, correlation key và namespace phải nhất quán

Đối với group, **lock key hiệu quả** thường được hình thành từ correlation key đã resolve. Vì vậy một lỗi trong <code>CorrelationStrategy</code> có thể biến thành lỗi khóa hoặc sai dữ liệu:

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ dùng <code>orderId</code> khi các tenant có thể trùng ID | Ghép nhầm message của nhiều tenant | Dùng key gồm <code>tenantId</code> + <code>orderId</code> theo hợp đồng |
| Dùng đối tượng không ổn định/đổi <code>hashCode()</code> | Các thread hoặc node không cùng tìm đúng group/lock | Dùng kiểu bất biến, chuỗi/cặp giá trị ổn định |
| Mỗi node chuẩn hóa key khác nhau | Hai node cho rằng cùng batch là hai group | Đồng nhất format, case, encoding và version strategy |
| Hai aggregator độc lập dùng cùng store và key | Chồng nhóm, expiry callback có thể xử lý sai | Tách store region và lock namespace theo endpoint |
| Đổi region giữa các lần deploy | Không còn tìm thấy metadata/lock cũ theo cách trước | Có kế hoạch migration/cleanup và tương thích khi rolling deploy |
| Dùng <code>MessageHeaders.ID</code> làm correlation | Mỗi fragment tạo group riêng | Dùng khóa nghiệp vụ/batch ổn định; message ID không phải group ID |

**Nhất quán giữa các node** quan trọng hơn vẻ ngoài của key. Khi dùng <code>JdbcMessageStore</code>, <code>region</code> phân tách các nhóm trên cùng backend. Khi dùng <code>DefaultLockRepository</code> hoặc <code>RedisLockRegistry</code>, namespace/region của lock cần phân tách flow độc lập nhưng phải **trùng nhau giữa các replica của cùng flow**.

## 7. Deadlock khi nhiều group hoặc aggregator lồng nhau

Khóa group giúp tránh race, nhưng có thể gây deadlock khi chuỗi xử lý lấy nhiều lock theo **thứ tự khác nhau**.

~~~mermaid
flowchart LR
    T1["Thread 1<br/>giữ lock A"] --> W1["chờ lock B"]
    T2["Thread 2<br/>giữ lock B"] --> W2["chờ lock A"]
    W1 -.-> T2
    W2 -.-> T1
~~~

Ví dụ flow:

~~~text
... → aggregator-1 → DirectChannel → aggregator-2 → ...
~~~

Một thread đang giữ group lock của aggregator-1 rồi gửi đồng bộ đến aggregator-2, nên cần lock của aggregator-2. Trong khi đó, thread khác giữ lock của aggregator-2 và vì router/loop hoặc một luồng khác lại cần lock của aggregator-1. Cả hai chờ nhau; không có timeout nghiệp vụ nào tự phá deadlock Java.

Những cách hạn chế:

1. **Mỗi aggregator có lock namespace/registry thích hợp** thay vì vô tình chia sẻ một không gian khóa giữa các endpoint độc lập. Nếu một aggregator có nhiều replica, các replica vẫn phải dùng chung namespace của aggregator đó.
2. Dùng <code>.releaseLockBeforeSend(true)</code> để không giữ group lock trong lúc gửi output xuống downstream. Cần kiểm thử chuyện late arrival, retry và cách downstream xử lý khi trạng thái group đã hoàn tất.
3. Cân nhắc ranh giới <code>ExecutorChannel</code>/<code>QueueChannel</code> sau aggregator nếu muốn tránh chuỗi lock đồng bộ. Điều này **đổi transaction/thread/ACK semantics**, nên phải thiết kế tương ứng.
4. Nếu tự lấy nhiều lock, quy định **một thứ tự khóa toàn cục** (ví dụ theo tên endpoint rồi đến khóa group) và luôn giải phóng trong <code>finally</code>.
5. Hạn chế gọi HTTP, database chậm hoặc các API có thể block lâu trong vùng đang giữ group lock.

<code>releaseLockBeforeSend</code> giải quyết một trường hợp deadlock phổ biến, **không** bảo đảm mọi kiểu deadlock sẽ biến mất. Lock ở tầng store, database row lock, transaction và việc retry bên trong downstream vẫn có thể tạo vòng chờ khác.

## 8. TTL của khóa phân tán và lỗi mất quyền sở hữu

Một khóa phân tán thường có **lease/TTL** để node khác có thể lấy lại lock khi node đang giữ bị chết. Đây là TTL của **khóa**, không phải <code>groupTimeout</code> của aggregator.

~~~text
Node A: acquire lock(B-42) → bắt đầu cập nhật
                 |
          xử lý lâu hơn TTL
                 |
Lock lease hết hạn (trong backend)
                 |
Node B: acquire cùng lock(B-42)
                 |
  hai node có thể cùng chạy phần việc cũ nếu A chưa dừng
~~~

Với <code>JdbcLockRegistry</code> và <code>RedisLockRegistry</code>, phải đặt TTL đủ lớn so với *critical section* hoặc sử dụng cơ chế renewal được hỗ trợ. Tùy phiên bản, <code>RenewableLockRegistry</code> có các phương thức gia hạn lease; Redis có hỗ trợ cấu hình scheduler tự gia hạn. **Mất quyền sở hữu rồi mới gọi <code>unlock()</code> có thể ném exception**, và đó là tín hiệu nghiêm trọng vì tài nguyên đang bảo vệ có thể đã bị cập nhật đồng thời.

Không nên xem việc tăng TTL là sửa triệt để: TTL quá dài có thể khiến node khác chờ lâu sau crash. Trong các thao tác đòi hỏi bảo đảm mạnh, cần thêm **fencing token/version check** hoặc điều kiện cập nhật ở database, nếu backend và kiến trúc hỗ trợ. Khóa phân tán không có fencing kết hợp với tạm dừng JVM/network partition vẫn có rủi ro.

### Khác biệt theo phiên bản Spring Integration

- Spring Integration 6.2 có <code>LockRegistry.executeLocked(...)</code>.
- Spring Integration 6.5 có hỗ trợ <code>AbstractMessageGroupStore.setLockRegistry(...)</code> cho thao tác group metadata.
- Spring Integration 7.0 bổ sung <code>DistributedLock</code> với một số API TTL tùy chỉnh và mở rộng khả năng renewal cho JDBC/Redis.

Khi dùng Spring Integration 6.x, không sao chép trực tiếp các phương thức chỉ có ở 7.x vào code rồi cho rằng chúng đã tồn tại.

## 9. Transaction, retry, expiry và lifecycle tương tác với khóa ra sao?

### Transaction không thay thế khóa

Một transaction có thể rollback dữ liệu đã ghi, nhưng hai transaction ở hai replica vẫn có thể đọc cùng trạng thái group rồi cạnh tranh release. Khóa giúp tuần tự hóa quyết định xử lý; transaction bảo vệ thay đổi dữ liệu. Với JDBC store/lock registry, cần kiểm tra transaction manager, isolation, commit và thứ tự lock để không giữ distributed lock quá lâu hoặc mất quyền sở hữu trước khi commit.

### Retry/redelivery không bị loại bỏ bởi khóa

Sau khi thread A hoàn tất group và unlock, message trùng có thể đến lần nữa. Nó sẽ lấy được lock bình thường. Vì vậy:

- Lưu dấu vết group đã hoàn tất khi cần chặn **late-arriving message**.
- Dùng khóa nghiệp vụ/idempotency store để chống trùng khi group bị expire hoặc được tạo lại.
- Khi retry lỗi database, xác định lại transaction boundary; đừng tự động retry vô hạn các lỗi lock timeout.
- Nếu phát output rồi crash trước khi cập nhật trạng thái, xem xét outbox và kiểm soát duplicate downstream.

### Group timeout và reaper cũng phải được đồng bộ

<code>groupTimeout</code>, <code>forceComplete()</code> và <code>MessageGroupStoreReaper</code> có thể xảy ra song song với message mới đang đến. Luồng expiry không chỉ xóa dữ liệu: nó có thể release kết quả partial hoặc discard group. Do đó, các callback expiry cũng phải tôn trọng khóa và chính sách transaction/side effect của group; kiểm thử tình huống fragment cuối đến đúng lúc timeout.

### Stop/restart không giải phóng mọi công việc ngay lập tức

Khi <code>IntegrationFlow</code> hoặc polling endpoint stop, worker đã nhận message hoặc đang chờ lock có thể vẫn tồn tại cho tới khi task kết thúc. Với local lock, JVM crash làm mất lock trong bộ nhớ; với distributed lock, backend có thể giữ record/lease một thời gian. Khi ứng dụng start lại, persistent store có thể vẫn còn group dang dở nhưng lịch timeout trong bộ nhớ cần được tái lập hoặc dùng cơ chế dọn orphan.

## 10. Threading, throughput và kiểm soát contention

Một khóa theo group làm cho các thao tác trong *critical section* của cùng key được tuần tự hóa. Vì vậy tăng executor pool từ 8 lên 64 thread chưa chắc tăng throughput nếu 90% message cùng thuộc một batch: đa số thread chỉ đứng chờ cùng một group lock.

| Tình huống | Dấu hiệu | Điều chỉnh đáng cân nhắc |
|---|---|---|
| Một correlation key cực nóng | Nhiều worker chờ lock, throughput gần như không tăng | Phân vùng batch có kiểm soát hoặc giảm concurrency trên cùng key |
| Nhiều group khác nhau nhưng vẫn chờ nhau | Local lock stripes va chạm; backend lock có chi phí cao | Đánh giá cấu hình <code>DefaultLockRegistry</code> hoặc khóa phân tán theo tải thực |
| Lock giữ qua downstream chậm | Thời gian giữ lock dài, queue depth tăng | <code>releaseLockBeforeSend</code>, tách downstream, giảm side effect trong critical section |
| JDBC lock chậm | DB lock contention, query/connection pool căng | Đo p95/p99 lock wait; kiểm tra index, pool, transaction |
| Redis lock lease hết hạn | Exception khi unlock, nhiều replica xử lý cùng group | Gia hạn lease và kiểm tra thời gian xử lý lớn nhất |
| Chỉ một node có backlog | Sai routing/partition key hoặc một node giữ lock lâu | Quan sát distribution của key, thread dump và owner lock |

Metric hữu ích: **lock acquisition wait**, **lock hold duration**, số lần thất bại hoặc quá hạn khi lấy lock, số group đang mở, tuổi group cũ nhất, số lần release/expire, queue depth, active worker, độ trễ store và số lần downstream timeout. Nên gắn <code>correlationId</code>, tên endpoint và node ID vào trace/log, nhưng không ghi toàn bộ payload nhạy cảm.

## 11. Chẩn đoán runtime khi group bị treo hoặc kết quả bị lặp

1. **Kiểm tra correlation trước tiên:** xác nhận ba fragment thực sự có cùng key ổn định, cùng tenant/flow và cùng schema.
2. **Kiểm tra vị trí message:** inbound adapter → channel → endpoint → message store; đừng vội quy lỗi cho lock nếu message chưa tới aggregator.
3. **Kiểm tra topologies:** <code>DirectChannel</code>, executor, poller, số replica và việc chia sẻ store/registry giữa chúng.
4. **Đo thời gian chờ lock:** phân biệt thread bị block vì group lock với thread đang chờ database, queue receive hoặc HTTP downstream.
5. **Dùng thread dump** (<code>jstack</code>/<code>jcmd Thread.print</code> theo môi trường) để tìm <code>ReentrantLock</code> contention/deadlock. Với JDBC/Redis lock, phải kết hợp log/metric backend vì thread dump không thể tự chỉ ra đầy đủ owner của distributed lease.
6. **Kiểm tra release strategy và metadata:** group chưa đủ phần, đã hoàn tất nhưng tombstone còn, hay bị force complete khi timeout?
7. **Kiểm tra transaction/retry:** lỗi đã rollback chưa, message có được redeliver không, có side effect nào đã xảy ra trước rollback?
8. **Thử trên staging có điều kiện đồng thời:** nhiều fragment cùng group, hai replica, timeout/restart và lỗi mạng; quan sát một group chỉ release đúng theo hợp đồng.

### Phân biệt một số triệu chứng

| Triệu chứng | Giả thuyết cần kiểm tra | Bằng chứng cần có |
|---|---|---|
| Hai output cho cùng batch | Nhiều node local-lock trên shared store; hết TTL; group bị xóa rồi tạo lại | Log owner lock, group lifecycle, idempotency record |
| Một group mãi không release | Thiếu fragment, release strategy sai, consumer chưa start, lock contention | Số message/group, trạng thái endpoint, lock wait |
| Thread dump báo deadlock | Hai aggregator lấy lock khác thứ tự; call chain vòng | Stack trace hai thread, lock owner/target |
| <code>unlock()</code> ném lỗi ở Redis/JDBC | Lease hết hạn hoặc owner đã mất quyền | TTL, thời gian giữ lock, log gia hạn/backend |
| Khi restart bị “kẹt” nhóm cũ | Store persistent nhưng scheduler timeout không được tái kích hoạt | Tuổi group, cấu hình orphan purge/reaper |
| Tăng thread nhưng TPS không tăng | Hot key hoặc striped lock collision | Phân bố correlation key, lock hold/wait p95 |

## 12. Kiểm thử đồng bộ group

Unit test đơn luồng chỉ chứng minh logic release, **không** chứng minh concurrency safety. Cần ít nhất những ca sau:

| Trường hợp | Kết quả kỳ vọng |
|---|---|
| Ba fragment cùng key đến đồng thời | Group có đủ phần, release một lần, không mất fragment |
| Nhiều batch khác key đến đồng thời | Các group không lẫn message; concurrency đúng kỳ vọng |
| Message duplicate do retry/redelivery | Side effect không bị nhân đôi theo hợp đồng idempotency |
| Hai Spring context/replica cùng shared JDBC store | Group release một lần với **distributed** lock chung |
| Một instance có local registry, instance kia có registry khác | Test phải phát hiện thiết kế không có bảo đảm loại trừ trên cluster |
| Fragment cuối và <code>groupTimeout</code> xảy ra gần nhau | Group được release/expire theo chính sách, không mất hoặc nhân đôi không chủ ý |
| Downstream ném exception lúc release | Error path và transaction/retry không gây output trùng |
| Node crash khi đang giữ lock | Lease được thu hồi theo cấu hình, group có thể tiếp tục hoặc được quarantine |
| Một aggregator gọi đồng bộ aggregator khác | Không deadlock khi tải đồng thời hoặc có biện pháp tránh deadlock |

Ví dụ phác thảo một test concurrent trong một Spring context (một số bean đã được cấu hình ở trên):

~~~java
ExecutorService workers = Executors.newFixedThreadPool(3);
CountDownLatch gate = new CountDownLatch(1);
List<Future<?>> tasks = new ArrayList<>();

for (int n = 1; n <= 3; n++) {
    int index = n;
    tasks.add(workers.submit(() -> {
        gate.await();
        Message<Fragment> message = MessageBuilder
            .withPayload(new Fragment("F" + index, "part-" + index))
            .setHeader("batchKey", "tenant-7:B-42")
            .build();
        fragmentsInput.send(message);
        return null;
    }));
}

gate.countDown();
for (Future<?> task : tasks) {
    task.get(10, TimeUnit.SECONDS);
}

Message<?> combined = fragmentsCompleted.receive(10_000);
assertNotNull(combined);
assertEquals(3, ((Collection<?>) combined.getPayload()).size());
assertNull(fragmentsCompleted.receive(0));
workers.shutdownNow();
~~~

Các kiểu dùng ở ví dụ: <code>Executors</code>, <code>ExecutorService</code>, <code>Future</code>, <code>CountDownLatch</code>, <code>TimeUnit</code>, <code>List</code>, <code>ArrayList</code> và <code>Collection</code> thuộc <code>java.util</code>/<code>java.util.concurrent</code>; assertion thuộc JUnit 5. Trong test production, đặt <code>shutdownNow()</code> vào <code>finally</code> hoặc dùng lifecycle quản lý executor để tránh rò rỉ thread nếu assertion thất bại.

Test này chứng minh behavior cho một JVM và một input flow. Nó **chưa** kiểm tra khóa phân tán, transaction của JDBC store hoặc hành vi khi lease hết hạn. Những trường hợp đó cần hai application context/process chia sẻ backend thật (có thể dùng Testcontainers), injection lỗi và quan sát dữ liệu sau commit.

## 13. Checklist áp dụng LockRegistry đúng cách

- [ ] Correlation key ổn định, có namespace tenant/flow khi cần, dùng cùng format trên mọi node.
- [ ] <code>MessageGroupStore</code> và <code>LockRegistry</code> có phạm vi phù hợp: local cho một JVM, distributed cho các replica dùng chung store.
- [ ] Mỗi correlating endpoint có region/namespace riêng; các replica của cùng endpoint dùng cùng region/namespace.
- [ ] Đã xác định chính xác phần nào của group mutation/release/expiry cần được khóa và transaction nào bảo vệ cập nhật store.
- [ ] Đã đánh giá <code>releaseLockBeforeSend</code>, ranh giới channel đồng bộ, nested aggregator và khả năng deadlock.
- [ ] TTL/renewal của distributed lock phù hợp với thời gian giữ lock; có hành vi xử lý khi mất quyền sở hữu.
- [ ] Retry/redelivery, late arrival và idempotency được kiểm thử độc lập với lock; không coi lock là đảm bảo exactly-once.
- [ ] Có metric về lock wait/hold, số group, timeout/expiry, queue depth, executor saturation và lỗi tại error channel.
- [ ] Có test đồng thời trong một JVM **và** test hai node dùng chung persistent store nếu ứng dụng chạy cluster.

**Kết luận:** Trong Spring Integration, <code>LockRegistry</code> là cơ chế giúp **mỗi correlation group được cập nhật và đánh giá release nhất quán khi có concurrency**. Với một JVM, <code>DefaultLockRegistry</code> thường đáp ứng yêu cầu ban đầu; khi nhiều instance cùng chia sẻ <code>MessageGroupStore</code>, cần một distributed registry và key/namespace thống nhất. Cần kết hợp khóa với transaction, chính sách expiry, idempotency, quản trị lease và quan sát runtime để giữ message flow ổn định trong điều kiện tải cao hoặc lỗi hệ thống.

## Tài liệu tham khảo

- [Spring Integration Reference — Aggregator, Lock Registry và Avoiding Deadlocks](https://docs.spring.io/spring-integration/reference/aggregator.html)
- [Spring Integration Reference — Distributed Locks](https://docs.spring.io/spring-integration/reference/distributed-locks.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/jdbc/lock-registry.html)
- [Spring Integration Reference — Redis Lock Registry](https://docs.spring.io/spring-integration/reference/redis.html)
- [Spring Integration Javadoc — CorrelationHandlerSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/CorrelationHandlerSpec.html)
