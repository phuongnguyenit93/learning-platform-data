# Sự kiện nội bộ bất đồng bộ không thay thế hàng đợi bền vững

## 1. Vấn đề cần phân biệt: xử lý lệch thời điểm và bảo đảm không mất việc

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(...)` cho phép một bean phát sự kiện để các listener bên trong `ApplicationContext` phản ứng. Có thể dùng `@EventListener` cùng `@Async` hoặc cấu hình `ApplicationEventMulticaster` để chuyển xử lý sang thread pool. Cách làm này phù hợp với thông báo nội bộ, giảm coupling và đưa công việc không cấp thiết ra khỏi request thread.

Nhưng **“đã giao việc sang thread khác” không đồng nghĩa “đã lưu việc vào hàng đợi bền vững”**. Một `ThreadPoolTaskExecutor` thường giữ các `Runnable` đang chờ trong bộ nhớ của JVM. Khi JVM chết đột ngột, container bị kill, máy hết điện hoặc tiến trình được thay thế mà chưa kịp xử lý, **những task chỉ nằm trong bộ nhớ không được bảo đảm tự phục hồi**. Nếu listener ném exception, Spring event infrastructure thông thường cũng không tự cung cấp cơ chế lưu trạng thái, retry sau restart, dead-letter hay audit bền vững cho từng sự kiện.

Tương tự, `@TransactionalEventListener(phase = AFTER_COMMIT)` giúp xử lý listener *sau khi transaction của publisher commit thành công*, nhưng **không tự biến event thành bản ghi bền vững**. Có khoảng rủi ro: dữ liệu nghiệp vụ đã commit, trong khi JVM chết trước khi xử lý listener hoặc chuyển được tác vụ tới nơi lưu an toàn.

Đặt câu hỏi theo hai lớp:

1. **Asynchronous execution:** caller có cần chờ listener thực thi xong không? Có muốn giảm thời gian request và điều phối các module trong cùng ứng dụng không?
2. **Durable delivery:** nếu tiến trình chết ở bất kỳ thời điểm nào, có thể tìm lại những event chưa xử lý, retry có kiểm soát, tránh xử lý trùng và quan sát tiến độ không?

`@Async` giải quyết chủ yếu lớp thứ nhất. Lớp thứ hai cần **thiết kế lưu bền và giao nhận**: transactional outbox, một event publication registry bền vững hoặc broker/queue được cấu hình độ bền phù hợp, cùng consumer idempotent.

## 2. Bốn khái niệm không được đánh đồng

| Khái niệm | Có nghĩa là gì? | Không tự bảo đảm |
| --- | --- | --- |
| Spring application event | Gửi thông báo tới listener trong `ApplicationContext` | Lưu bền, phát lại sau restart, giao giữa nhiều process |
| `@Async` hoặc executor bất đồng bộ | Giao callback cho executor để xử lý theo lịch của nó | Task đã hoàn tất, dữ liệu đã commit, task tồn tại qua crash |
| `@TransactionalEventListener(AFTER_COMMIT)` | Gắn callback với giai đoạn transaction commit thành công | Một record event được lưu để recovery sau sự cố |
| Durable broker/queue/event log | Lưu thông điệp ngoài bộ nhớ của ứng dụng theo hợp đồng hạ tầng | “Exactly once” ở mức side effect nghiệp vụ, hoặc tự đồng bộ atomically với DB nguồn |
| Transactional outbox / publication registry | Lưu ý định phát sự kiện trong một kho bền vững, thường cùng giao dịch dữ liệu nghiệp vụ | Bên nhận không bao giờ thấy bản phát trùng; phải có relay/retry/idempotency |

**Độ bền không phải một thuộc tính nhị phân chỉ nhìn tên sản phẩm.** Một broker có thể lưu message bền vững hay không tùy cấu hình message persistence, replication/quorum, producer acknowledgement, consumer acknowledgement, retention, TTL và chính sách vận hành. Hàng đợi bền vững không mặc nhiên bảo đảm mọi consumer side effect được thực hiện đúng một lần.

## 3. Mặc định Spring events là đồng bộ, @Async mới thay đổi lịch thực thi

Trong Spring Framework thông thường, `ApplicationEventMulticaster` mặc định sử dụng cách phát sự kiện đồng bộ. Khi publisher gọi:

```java
events.publishEvent(new OrderPlaced(orderId));
```

listener có `@EventListener` thường được gọi ngay trên **thread của publisher** trước khi `publishEvent` trả về. Nếu publisher đang ở trong một transaction imperative, listener đồng bộ có thể tham gia chính thread và transaction context ấy theo cấu hình tương ứng. Điều này có thể hữu ích với một hành vi nội bộ phải hoàn tất cùng đường xử lý nhưng cũng có thể kéo dài thời gian transaction/request.

Nếu listener được đánh dấu `@Async("eventPool")` và bật `@EnableAsync`, lời gọi listener phù hợp đi qua Spring async advice và được gửi vào executor được chọn. Caller có thể tiếp tục trước khi listener thực thi xong.

Hai tình huống cần phân biệt:

```text
A. @EventListener bình thường (mặc định)

publisher --publishEvent--> listener chạy trên publisher thread
                                |
                                +-- xong/lỗi --> publishEvent trở về

B. @Async @EventListener (có @EnableAsync, proxy, executor phù hợp)

publisher --publishEvent--> async advice --> submit vào executor
           |                                      |
           +-- có thể tiếp tục                    +--> worker thực thi listener sau đó
                                                       (task có thể đang chờ trong RAM)
```

Lưu ý: `publishEvent(...)` được định nghĩa là thao tác **bàn giao thông báo cho event multicaster**, không phải biên nhận “toàn bộ listener đã xử lý và commit side effect”. Thực thi cụ thể đồng bộ/bất đồng bộ còn phụ thuộc multicaster, listener và framework configuration.

Spring cho phép cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)` để chạy nhiều listener một cách async; đây là cách khác với việc gắn `@Async` cho một listener cụ thể. Với Spring 6.2.x, các listener tuyên bố không hỗ trợ async execution, chẳng hạn transaction-synchronized listener, vẫn cần xử lý trên thread phát event để đăng ký transaction synchronization đúng. Vì vậy **đừng kết luận rằng chỉ cấu hình một multicaster async là mọi listener đều chạy thread khác**.

## 4. Ví dụ Spring Framework 6.2.9 + Java 17+ chạy thật

Ví dụ minh họa event nội bộ được giao cho một worker của `ThreadPoolTaskExecutor`. Chúng ta dùng `CountDownLatch` để chờ có thời hạn, vì nếu chỉ gọi `publishEvent` rồi lập tức kiểm tra biến, worker có thể chưa bắt đầu. Dữ liệu quan sát được đặt trong một bean `Probe` riêng để tránh nhầm state nội bộ của AOP proxy với state trong target bean.

Cấu trúc Maven:

```text
local-event-demo/
├── pom.xml
└── src/main/java/demo/LocalEventDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>local-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/LocalEventDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class LocalEventDemo {

    @Bean("eventPool")
    public ThreadPoolTaskExecutor eventPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("event-worker-");
        return pool;
    }

    public record OrderPlaced(long id) {}

    // Bean riêng để kiểm thử, không phải outbox hoặc event store.
    public static class Probe {
        final CountDownLatch done = new CountDownLatch(1);
        volatile long seen;
        volatile String worker;
    }

    @Bean
    public Probe probe() {
        return new Probe();
    }

    @Bean
    public Receiver receiver(Probe probe) {
        return new Receiver(probe);
    }

    public static class Receiver {
        private final Probe probe;

        public Receiver(Probe probe) {
            this.probe = probe;
        }

        @Async("eventPool")
        @EventListener
        public void on(OrderPlaced event) {
            probe.seen = event.id();
            probe.worker = Thread.currentThread().getName();
            probe.done.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(LocalEventDemo.class)) {
            Probe probe = context.getBean(Probe.class);
            String caller = Thread.currentThread().getName();

            context.publishEvent(new OrderPlaced(7L));

            if (!probe.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener timed out");
            }

            System.out.println("order id = " + probe.seen);
            System.out.println("pool worker = "
                    + probe.worker.startsWith("event-worker-"));
            System.out.println("different thread = "
                    + !caller.equals(probe.worker));
        }
    }
}
```

Chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LocalEventDemo
```

Stdout do chương trình in:

```text
order id = 7
pool worker = true
different thread = true
```

**Giải thích:**

1. `@EnableAsync` bật hạ tầng async proxy. `@Async("eventPool")` chọn executor bean cụ thể cho listener.
2. `context.publishEvent(new OrderPlaced(7L))` giao sự kiện nội bộ cho application context; callback được lên lịch trên `eventPool`.
3. `CountDownLatch` cho phép main chờ tối đa 5 giây để xác nhận callback đã chạy. Nếu không chờ, phép đo kết quả có thể chạy đua với worker.
4. `Receiver` ghi ID và tên thread vào `Probe`; hai kiểm tra xác nhận target listener chạy trên worker của pool thay vì caller.
5. Sau `try`, application context được đóng, executor bean được quản lý theo lifecycle của Spring.

Đã kiểm chứng đường chạy tương đương với Spring 6.2.9/JDK trong JShell: ba dòng kết quả khớp. Ví dụ **không có database, broker, outbox hay cơ chế recovery**, nên chỉ chứng minh event được xử lý trên worker **khi ứng dụng vẫn hoạt động**, tuyệt đối không chứng minh giao nhận bền vững. Nếu đặt một event khác trong queue rồi kill process trước khi worker nhận, queue trong RAM không có hợp đồng tự phát lại sau restart.

## 5. Các cửa sổ lỗi: vì sao callback trong RAM có thể bị mất?

Xét yêu cầu tạo đơn hàng:

```text
HTTP request
    |
    +-- ghi order vào database
    |
    +-- publishEvent(OrderPlaced)
    |
    +-- worker gửi email / cập nhật hệ thống phụ
```

Nếu dùng `@Async @EventListener` thông thường, có các rủi ro khác nhau:

| Thời điểm hỏng | Điều có thể xảy ra | Spring event nội bộ mặc định có tự sửa không? |
| --- | --- | --- |
| Sau khi gửi event nhưng trước khi listener được chạy | Task chỉ còn trong queue RAM; crash làm mất task chưa xử lý | Không có replay bền vững |
| Sau khi listener bắt đầu nhưng trước side effect | Worker mất tiến trình; không có record công việc đang dở | Không có cơ chế retry sau restart mặc định |
| Listener gọi external API thành công nhưng JVM chết trước khi ghi trạng thái hoàn tất | Trạng thái không được lưu; nếu tự retry có thể làm side effect lần hai | Không có idempotency tự động |
| Executor đầy queue và pool không nhận thêm task | Có thể phát sinh rejection ở đường dispatch, tùy cách cấu hình | Không biến rejection thành backlog bền vững |
| Listener ném exception khi chạy async | Lỗi không tự quay lại caller để rollback business transaction | Cần handler, log, retry và kiểm soát nghiệp vụ |
| Deploy/scale down với xử lý dài | Graceful shutdown có thể chờ một phần tác vụ theo cấu hình nhưng bị giới hạn thời gian | Không bảo đảm qua `kill -9`/OOM/power loss |

Không nên suy diễn rằng **mọi restart đều làm mất mọi task**. Nếu shutdown có grace period đủ dài, một số task có thể hoàn tất. Điểm thiết kế là **không có cam kết khôi phục những task chưa hoàn tất khi process bị chấm dứt không kiểm soát**.

Một HTTP response thành công hoặc một lời gọi `publishEvent` đã trả về chỉ chứng minh những bước mà API đó cam kết; **không phải biên nhận của bên nhận** và càng không phải bằng chứng dữ liệu đã được ghi bền vững ở một nơi độc lập.

## 6. Giao dịch: @EventListener không phải @TransactionalEventListener

Khi đang ở một phương thức `@Transactional`:

```java
@Transactional
public void placeOrder(CreateOrder command) {
    Order order = repository.save(new Order(command.customerId()));
    events.publishEvent(new OrderPlaced(order.getId()));
}
```

Đây là **mảnh code tích hợp Spring Data/transaction**, không phải Java tự chạy. Phương thức `placeOrder` phải thật sự được gọi qua Spring transactional proxy và có transaction manager. Nếu listener đồng bộ thông thường, listener có thể chạy **trước khi transaction commit**. Nếu listener gửi email ngay, sau đó transaction rollback, email đã ra ngoài nhưng order không tồn tại: một lỗi tính nhất quán.

Thêm `@Async` không tự chữa điều này. Một listener chạy trên thread khác có thể bắt đầu **trước commit**, không có transaction context của publisher, và khi truy vấn database có thể chưa thấy order theo isolation level của DB.

Spring cung cấp:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Chạy khi transaction publisher commit thành công.
}
```

Đây là **mảnh method trong Spring-managed bean**, cần import `@TransactionalEventListener` và `TransactionPhase`. Phase mặc định của annotation là `AFTER_COMMIT`, nên khai báo tường minh giúp người đọc nhìn rõ ý định.

Các phase khác gồm `BEFORE_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Nếu **không có transaction đang chạy**, listener transaction-bound **không được gọi** trừ khi cấu hình `fallbackExecution = true`; khi bật fallback, semantics phụ thuộc tình huống và cần quy định rõ.

Với Spring Framework 6.2.x, listener transaction-bound dùng cơ chế synchronization đăng ký trên thread có transaction. Một `@TransactionalEventListener` không nên bị suy diễn là tự chạy trên worker chỉ vì multicaster toàn cục được cấu hình async. Nếu muốn listener business chạy async sau commit, có thể kết hợp `@Async`/executor đúng cách, nhưng **phase after-commit không biến queue RAM thành durable queue**.

## 7. AFTER_COMMIT sửa thứ tự nhưng không đóng khoảng cách mất sự kiện

So sánh hai bước:

```text
T0   Bắt đầu transaction DB
T1   Ghi order
T2   Đăng ký event / listener AFTER_COMMIT
T3   COMMIT dữ liệu order thành công
T4   Spring bắt đầu gọi callback sau commit / submit async task
T5   Worker thực hiện side effect
```

Nếu tiến trình chết **giữa T3 và T4**, dữ liệu order đã được commit, nhưng callback chưa được giao tới một nơi lưu bền vững. Nếu chết **giữa T4 và T5**, task có thể đã nằm trong executor RAM nhưng chưa hoàn tất. Hai trường hợp đều không có cam kết tự phục hồi chỉ nhờ `@TransactionalEventListener`.

Điều này có nghĩa:

- `AFTER_COMMIT` rất có ích để **không phản ứng với transaction bị rollback** và tránh đọc dữ liệu chưa commit.
- Nó **không lưu một thông điệp vào DB/broker** như một phần của transaction nguồn.
- Nếu callback sau commit ghi dữ liệu mới vào DB, cần hiểu resource/transaction boundary. Trong một số ngữ cảnh thread-bound, resource của transaction cũ có thể còn được gắn ngắn hạn; cần một giao dịch mới rõ ràng, thường `@Transactional(propagation = REQUIRES_NEW)` trên một Spring-managed service/worker phù hợp, thay vì mong các write sau commit tự được commit.
- Nếu event chạy trong worker khác, transaction của publisher **không tự truyền** sang worker. Worker cần transactional boundary riêng nếu nghiệp vụ đòi.

**Đừng hiểu “sau commit” thành “đã ghi vào queue”.** Nó chỉ xác định thời điểm xử lý callback trong lifecycle giao dịch.

## 8. Mẫu bền vững: transactional outbox

Khi một hành động phụ bắt buộc được xử lý sau khi đơn hàng đã tồn tại — chẳng hạn phát thông báo đến kho hàng, thanh toán hoặc hệ thống tích hợp — cần ghi lại **ý định phát sự kiện** ở nơi khôi phục được.

Mẫu phổ biến:

```text
                     MỘT DB TRANSACTION
+----------------------------------------------------+
| UPDATE orders SET status='PLACED' ...              |
| INSERT INTO outbox(event_id, type, payload, ...)  |
| COMMIT                                             |
+----------------------------------------------------+
                       |
                       v
              Outbox rows đã bền vững
                       |
                       v
              Background relay / CDC
                       |
                       v
             Broker lưu message (có ack)
                       |
                       v
             Consumer nhận, xử lý, ack
                       |
                       +--> Dedup by event_id
                       +--> Retry / DLQ / monitoring
```

Điều kiện then chốt: **ghi state nghiệp vụ và outbox record trong cùng một transaction của cùng hệ thống lưu trữ có atomic commit**. Khi transaction rollback, cả order lẫn outbox record rollback; khi commit, cả hai cùng tồn tại bền vững theo cam kết của DB. Relay có thể chạy sau, kể cả sau một restart.

Ví dụ dữ liệu outbox nên có ít nhất: `event_id` duy nhất, `aggregate_type`, `aggregate_id`, `event_type`, `schema_version`, `payload` hoặc reference, `created_at` và trạng thái/attempt metadata khi dùng polling. Nên tạo `event_id` ổn định cho **một ý định nghiệp vụ**, không phát ID mới vô hạn trên mỗi lần retry.

Để mô hình dễ hiểu, đây là **pseudo-SQL cho PostgreSQL**, tên bảng/columns chỉ minh họa:

```sql
BEGIN;

UPDATE orders
SET status = 'PLACED'
WHERE id = 42;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, status
) VALUES (
    'c44a7b4e-1fd0-4a4e-85c2-f11fa35a8368',
    42,
    'OrderPlaced',
    '{"orderId":42,"version":1}',
    'PENDING'
);

COMMIT;
```

Hai câu lệnh cùng commit mới tạo tính chất atomic business+outbox. Không dùng riêng hai DB transaction độc lập rồi gọi chúng là outbox nhất quán; thiếu distributed transaction phù hợp thì vẫn có khoảng commit một bên mà bên kia không.

### Relay phải xác nhận rồi mới đánh dấu đã gửi

Một relay polling thường:

1. Claim một nhóm record `PENDING` có khóa/lease, bảo đảm nhiều relay không lấy trùng vô kiểm soát.
2. Publish từng message tới broker với persistence/confirmation phù hợp.
3. **Chỉ sau khi có producer confirm/ack đủ mạnh**, đánh dấu record đã gửi (hoặc chuyển sang trạng thái đã được broker nhận).
4. Nếu publish/confirm thất bại, không đánh dấu thành công; retry với backoff.
5. Thu thập metric backlog, tuổi event lâu nhất, số lần retry và trạng thái lỗi lâu ngày.

Một relay có thể chết **sau khi broker đã nhận message nhưng trước khi đánh dấu outbox SENT**. Sau restart, relay sẽ gửi lại record. Đây là một trong các lý do **at-least-once delivery thường phải đi cùng consumer idempotent**. Không được đánh dấu SENT trước broker confirm, vì nếu broker không nhận thì mất event.

Hàng đợi bền vững không loại bỏ chuyện duplicates; nó cho cơ hội replay an toàn nếu thiết kế đầy đủ.

## 9. Consumer idempotent: chấp nhận có duplicate

Ngay cả broker bền vững cũng có thể redeliver:

```text
Consumer nhận message E
    |
    +--> Ghi DB side effect thành công
    |
    +--> Consumer chết TRƯỚC khi ack broker
    |
    +--> Broker gửi lại E
```

Không có dedup thì hệ thống có thể tính tiền hai lần, gửi email hai lần hoặc cộng tồn kho hai lần. Vì vậy nên thiết kế **idempotency** dựa trên `event_id`/business key theo loại side effect:

- Với DB, dùng bảng `processed_events(consumer_name, event_id)` có **unique constraint**. Trong cùng DB transaction với side effect, insert marker có điều kiện; nếu marker đã tồn tại, coi là đã xử lý và không áp dụng side effect lần nữa.
- Với external API, sử dụng **idempotency key được API hỗ trợ** hoặc một business operation ID ổn định. Chỉ check trong DB của mình **không tự ngăn** external API thực hiện hai lần nếu trạng thái phía mình và phía ngoài không commit atomically.
- Với thông báo/email, cân nhắc dedup ở bước dispatch hoặc nhà cung cấp, và xác định chấp nhận được duplicate đến mức nào.
- Ack broker **sau khi** phần xử lý cần đảm bảo đã bền vững, không ack ngay khi vừa nhận thông điệp.

Ví dụ ý tưởng PostgreSQL cho một consumer (mảnh minh họa, phải chạy trong cùng transaction với side effect):

```sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_id)
VALUES ('inventory', 'c44a7b4e-1fd0-4a4e-85c2-f11fa35a8368')
ON CONFLICT DO NOTHING;

-- Chỉ thực hiện UPDATE stock nếu lần INSERT phía trên
-- thực sự thêm một record mới; nếu conflict thì bỏ qua side effect.

COMMIT;
```

Đoạn này **chưa phải consumer hoàn chỉnh**, bởi ứng dụng phải kiểm tra row count của INSERT và chỉ cập nhật tồn kho trong nhánh insert thành công. Cần bảo đảm transaction marker và transaction side effect atomic, xử lý rollback khi side effect thất bại. Nếu broker/driver hỗ trợ transaction riêng, vẫn phải làm rõ phạm vi atomicity giữa broker và DB.

Kết luận: mục tiêu thực tế thường là **at-least-once + idempotent processing**, không tuyên bố “exactly once” ở cấp ứng dụng chỉ vì broker có một tính năng giao dịch.

## 10. Ví dụ Spring service: ghi đơn hàng và outbox trong một transaction

Trong Spring Data JPA hoặc JDBC, điểm gửi event đáng tin không phải `ApplicationEventPublisher` mà là **ghi outbox record** cùng transaction nghiệp vụ. Mảnh kiến trúc sau dùng lớp/repository giả định của ứng dụng, **không phải file Java chạy độc lập**:

```java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderCommandService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public long placeOrder(NewOrderCommand command) {
        Order order = orders.save(Order.newFrom(command));

        OutboxEvent event = OutboxEvent.pending(
                UUID.randomUUID(),
                "OrderPlaced",
                order.getId(),
                1,
                "{\"orderId\":" + order.getId() + ",\"version\":1}"
        );

        outbox.save(event);
        return order.getId();
    }
}
```

Các kiểu `OrderRepository`, `OutboxRepository`, `Order`, `OutboxEvent` và `NewOrderCommand` là **domain abstractions cần tự triển khai**; đoạn này chỉ cho thấy **một transactional boundary** chứa cả business data và outbox. Với JPA, ID sinh tự động phải được cấp/flush đúng lúc trước khi dùng trong payload; ở dự án thật nên serialize có schema/version rõ, dùng Jackson hoặc thư viện tương ứng thay vì nối JSON thủ công.

Nếu `orders.save` thành công nhưng `outbox.save` làm transaction fail, **toàn bộ transaction rollback**, không tạo trạng thái “order đã lưu nhưng event không có” khi transaction manager và DB đúng như cấu hình. Caller trả thành công chỉ khi transaction commit đúng; API cũng cần phân biệt commit với việc consumer downstream đã xử lý.

Sau đó có một **outbox relay** độc lập, không đòi handler bên trong request transaction gửi thông điệp tới broker. Có thể dùng job theo lịch, worker riêng hoặc CDC, tùy khối lượng và yêu cầu latency. Nếu muốn đánh thức relay nhanh, một Spring event nội bộ vẫn có thể đóng vai **tín hiệu tối ưu độ trễ**, nhưng **outbox record mới là nguồn sự thật**: mất tín hiệu RAM không được làm mất công việc đã commit.

```text
DB transaction lưu order + outbox
              |
              +-- tín hiệu local event (tùy chọn, có thể mất)
              |
              +-- scheduled relay vẫn quét outbox bền vững
```

Đừng biến tín hiệu local thành điều kiện duy nhất để relay hoạt động.

## 11. Khi nào cần broker, khi nào đủ event registry của ứng dụng?

Không phải mọi hệ thống cần dựng Kafka/RabbitMQ ngay. Sự lựa chọn phụ thuộc ranh giới tiến trình, khối lượng, SLA khôi phục và yêu cầu replay.

| Nhu cầu | Phương án thường phù hợp | Cảnh báo |
| --- | --- | --- |
| Cập nhật UI nội bộ không quan trọng, có thể tính lại | `@EventListener` hoặc `@Async @EventListener` | Chấp nhận mất một notification khi crash |
| Cache invalidation chỉ mang tính tối ưu | Local event có cache TTL/rebuild | Không coi cache event là source of truth |
| Gửi email đơn giản nhưng mất email là sự cố nghiệp vụ | Job record/outbox bền vững và retry | Email gửi thành công nhưng ack thất bại có thể gây duplicate |
| Giao tiếp giữa nhiều process/service | Broker/queue có cấu hình durable | Cần outbox hoặc cơ chế atomic publish phía nguồn |
| Workflow quan trọng trong modular monolith | Event publication registry bền vững hoặc outbox | Kiểm tra lưu state, recovery, idempotency của từng module |
| Cần replay, fan-out, retention dài | Event log/broker và consumer state | Cần schema evolution, offset/ack, quotas và quyền |
| Tác vụ nền có thể mất mà không ảnh hưởng dữ liệu | Executor in-memory là đủ nếu được chấp nhận | Ghi rõ SLA và cách tính lại |

**Spring Modulith Event Publication Registry** là một lựa chọn thuộc hệ sinh thái Spring cho modular monolith: registry có thể lưu bản ghi publication cho listener transaction-bound cùng transaction nguồn và đánh dấu hoàn tất sau khi listener thành công. Các phiên bản/tùy chọn cung cấp API resubmit; cấu hình recovery trên restart và monitor trạng thái phải được kiểm tra theo **phiên bản đang dùng**, không mặc định mọi starter bật auto-republication. Đây là **thành phần bổ sung cần cài và cấu hình**, không có sẵn chỉ bởi Spring Framework core hoặc một annotation `@EventListener`.

Broker bên ngoài cũng không tự giải bài toán dual-write. Ví dụ “DB commit order thành công; gửi Kafka thất bại” vẫn khiến event mất nếu không có outbox, transaction-coordination hoặc cơ chế bù/phục hồi khác. Hãy xem ranh giới transaction của hệ thống nguồn.

## 12. Phân biệt sự kiện nội bộ và thông điệp công khai giữa các service

Một local event có thể mang đối tượng Java trực tiếp:

```java
public record OrderPlaced(long orderId) {}
```

Trong cùng process, event này không cần serializer hay schema registry. Khi chuyển sang broker, một event thường phải:

- Có `eventId` độc nhất, `eventType`, `schemaVersion`, `occurredAt` hoặc metadata thời gian, `aggregateId`/business key.
- Mang **ID hoặc snapshot dữ liệu bất biến**, không mang JPA entity đang gắn `EntityManager`/`Session`, stream hoặc object phụ thuộc vòng đời request.
- Có schema tương thích khi producer/consumer nâng cấp độc lập; thay đổi field cần chính sách versioning rõ.
- Không chứa secret, token hay dữ liệu cá nhân dư thừa, vì broker có retention, replication và nhiều consumer.
- Định nghĩa ordering: ordering theo aggregate/partition key khi nghiệp vụ cần, nhưng **không giả định global ordering giữa nhiều partition**.
- Có timeout, retry và quyền truy cập cho publisher/consumer.

Một event payload chỉ chứa order ID cho consumer đọc lại DB sẽ cho phép lấy trạng thái mới nhất, **không nhất thiết trạng thái tại thời điểm event xảy ra**. Nếu nghiệp vụ cần snapshot lịch sử, hãy mang version hoặc các giá trị đã cố định trong event; nếu consumer fetch dữ liệu mới nhất, phải nhận thức tính **eventual consistency**.

## 13. Rejection và backpressure: không phải chỉ chọn queue dài hơn

Với `ThreadPoolTaskExecutor`, ba tham số quan trọng:

- `corePoolSize`: số worker lõi.
- `maxPoolSize`: trần thread mà pool có thể mở rộng.
- `queueCapacity`: dung lượng hàng đợi tác vụ.

Khi core bận, executor thường **ưu tiên enqueue** nếu queue còn chỗ. Khi queue đầy, pool mới thử tăng worker tới max; khi không nhận được tác vụ, có thể ném `TaskRejectedException` theo hợp đồng Spring.

Tăng queue chỉ giúp hấp thụ burst có giới hạn; **không tạo độ bền**. Một queue RAM chứa hàng nghìn event vẫn biến mất khi process chết đột ngột. Ngoài ra queue quá dài tăng latency, giữ memory và có thể làm thông báo quá hạn.

Khi dùng broker, backpressure cũng cần thiết:

1. Giới hạn in-flight messages, prefetch/concurrency và memory của consumer.
2. Nếu downstream quá tải, giảm tốc, retry với backoff/jitter và trần lần thử.
3. Dùng DLQ/quarantine cho poison message sau chính sách retries, với công cụ replay có kiểm soát.
4. Theo dõi `oldest_unprocessed_age`, queue depth, delivery lag, failure/retry count và thời gian thực hiện side effect.
5. Cảnh báo khi outbox backlog tăng dù HTTP requests vẫn thành công.

Nếu `publishEvent` nội bộ bị rejection, việc catch rồi “bỏ qua tạm” có thể là đúng **chỉ khi** nghiệp vụ đã tuyên bố event thuộc loại best-effort hoặc có outbox bền vững để khôi phục. Không biến mất event quan trọng thành “log warning” vô nghĩa.

## 14. Lỗi trong @Async listener không quay về caller như exception đồng bộ

Với listener:

```java
@Component
public class EmailListener {
    @Async("eventPool")
    @EventListener
    public void on(OrderPlaced event) {
        // Giả sử có IOException hoặc lỗi từ nhà cung cấp email.
        sendEmail(event.id());
    }
}
```

Đây là **mảnh minh họa cần `@Component`, imports, bean `eventPool` và method `sendEmail`**, không phải chương trình độc lập. Khi listener đã được giao cho worker, exception phát sinh trong xử lý **không tự ném trở lại** phương thức `publishEvent` của caller. Với `@Async void`, cần `AsyncUncaughtExceptionHandler` hoặc log/metrics thích hợp.

Một số điều cần tránh:

- **Chỉ dựa vào `try/catch` xung quanh `publishEvent`:** nó có thể bắt lỗi ở đường phát/gửi task, không bắt được mọi lỗi worker sau này.
- **Dùng `@Async` như retry framework:** Spring không tự persist delivery attempts và tự replay event sau restart.
- **Dùng return value của async `@EventListener` để publish event tiếp:** Spring docs nêu tính năng return-value publishing không hỗ trợ async listener; nếu cần phát event mới, inject `ApplicationEventPublisher` và publish rõ ràng, đồng thời xác định reliability riêng.
- **Tưởng `@Order` áp dụng đồng bộ thứ tự hoàn tất giữa các worker:** một số listener có thể được gọi theo thứ tự dispatch, nhưng thực thi async hoàn tất không bảo đảm cùng thứ tự.
- **Tưởng transaction ThreadLocal của publisher tự có trên worker:** không có bảo đảm; cần transaction mới ở worker nếu nghiệp vụ yêu cầu.

Đối với công việc quan trọng, việc quan sát lỗi qua `AsyncUncaughtExceptionHandler` chưa đủ nếu không có **persistent record + retry/recovery policy**.

## 15. Một phép thử sự cố thực tế nên bao phủ những gì?

Một kiểm thử “listener chạy khi mọi thứ đều tốt” chưa chứng minh delivery guarantee. Các tình huống bắt buộc cân nhắc:

| Kịch bản thử | Với local event + @Async | Với outbox + durable delivery đúng thiết kế |
| --- | --- | --- |
| Listener xử lý thành công khi JVM sống | Thường chạy được | Phải chạy được |
| Transaction business rollback | Listener thường có thể chạy sớm nếu không gắn phase | Outbox record cũng rollback cùng business state |
| Process chết sau DB commit nhưng trước listener chạy | Có nguy cơ mất event | Outbox record tồn tại, relay khôi phục sau restart |
| Process chết sau broker confirm trước outbox marked-sent | Không có trạng thái durable để suy luận | Relay có thể phát lại; consumer phải dedup |
| Consumer ghi DB thành công rồi chết trước broker ack | Không có broker ack tương ứng | Message có thể redeliver; consumer xử lý idempotent |
| Broker tạm thời down | In-memory listener không tự lưu retry qua restart | Relay giữ outbox PENDING và retry theo policy |
| Queue bị đầy | Có thể bị reject ngay | Có backlog/flow control nhưng vẫn cần giới hạn |
| Có nhiều instance và restart cuốn chiếu | Local event chỉ tồn tại trong context instance hiện tại | Kho event/broker chung có cơ chế claim/ack và durable storage |

Tạo fault-injection test trên môi trường được phép: dừng process ngay sau commit nhưng trước relay; ngắt mạng broker; kill consumer sau side effect nhưng trước ack; phát trùng cùng `eventId`; tạo event cũ với schema version trước; khởi động lại và so sánh **tất cả event đã commit** với tập event đã xử lý.

Một test bền vững nên có ít nhất các invariant:

- Mỗi business transaction thành công sinh **đúng một ý định event** trong outbox theo business key đã định nghĩa.
- Không có intent phát khi transaction rollback.
- Mọi intent chưa hoàn tất vẫn truy vấn được sau restart.
- Khi chạy retry/redelivery, external side effect không bị nhân đôi trái hợp đồng.
- Chỉ đánh dấu SENT/ACKED sau khi có bằng chứng phù hợp.
- Backlog cuối cùng giảm về trạng thái bình thường khi dependency được phục hồi.

Đừng thử crash trên production hoặc gửi tải không kiểm soát chỉ để chứng minh một pattern; cần isolation và teardown đúng.

## 16. Monitoring: nhìn delivery end-to-end, không chỉ log “event published”

Đối với event nội bộ, metric hữu ích gồm:

- Số event được publish và số event listener nhận; tách theo loại event.
- Executor active threads, queue size/capacity, rejection.
- Thời gian từ publish đến listener start và đến listener finish.
- Tỷ lệ listener failed/timeouts; mất/khôi phục context khi chạy async.

Đối với durable pipeline cần thêm:

- Số outbox records `PENDING`, `PROCESSING`, `FAILED`; tuổi record cũ nhất.
- Producer confirmations, lỗi publish, lần thử và thời gian retry.
- Consumer lag/prefetch/in-flight, ack/nack, DLQ volume.
- Số event deduplicated, schema-deserialization failures.
- Độ trễ từ **business commit đến side effect hoàn tất**, không chỉ HTTP response.
- Dữ liệu đối soát giữa business rows, outbox records và processed-events marker.

Nếu biết event đã commit nhưng chưa có trạng thái handled, một hệ thống bền vững phải có **cách replay và cảnh báo**. Một hệ thống chỉ có log “publish successful” mà không biết listener đã xử lý chưa là **best effort**, không thể cam kết delivery deadline.

Vì asynchronous processing cho phép sau commit mới làm tác vụ phụ, hệ thống có thể **eventually consistent**: order đã PLACED trong DB trong khi email hoặc inventory projection chưa cập nhật. API/UI cần phản ánh trạng thái `PENDING`/`IN_PROGRESS`/`FAILED` khi sự chậm trễ quan trọng, không chỉ trả một cờ “đã xong” dựa trên business commit.

## 17. Những sai lầm phổ biến

1. **Nói `@Async` là queue:** nó lập lịch công việc; queue của executor thường là cấu trúc bộ nhớ không tự replay.
2. **Nói `@EventListener` mặc định bất đồng bộ:** mặc định Spring application event thường được dispatch đồng bộ.
3. **Cho rằng `publishEvent()` trả về là listener đã xử lý thành công:** sai với async, và ngay cả synchronous dispatch cũng không phải durable acknowledgement.
4. **Nói `@TransactionalEventListener(AFTER_COMMIT)` bảo đảm message không thể mất:** chỉ gắn phase; JVM vẫn có thể crash trước khi handler được ghi nhận.
5. **Gọi API ngoài trong transaction trước commit rồi tưởng rollback hoàn tác API ấy:** side effects bên ngoài DB không tự rollback.
6. **Ghi DB rồi publish broker bằng hai bước độc lập, không xử lý dual-write gap:** một bước có thể thành công, bước khác thất bại.
7. **Đánh dấu outbox SENT trước producer confirm:** nếu publish fail có thể mất event mà DB nói đã gửi.
8. **Cho rằng “at least once” đồng nghĩa không bao giờ có duplicate:** resend sau crash là bình thường, cần idempotency.
9. **Đặt dedup marker khác transaction với DB side effect:** có thể có marker thành công nhưng side effect thất bại, hoặc ngược lại.
10. **Giữ entity JPA đang attached làm payload event gửi sang worker:** transaction/persistence context không tự đi theo thread, getter LAZY có thể lỗi.
11. **Tăng `queueCapacity` thật lớn để “bền vững hơn”:** chỉ tăng lượng công việc RAM, rủi ro memory/latency và mất khi crash vẫn còn.
12. **Không giám sát outbox lag và DLQ:** durable storage mà không relay/recovery runbook vẫn không đạt thời gian hoàn tất.
13. **Đồng nhất event publication registry với tính năng của Spring core:** registry bền vững cần dependency, storage và cấu hình riêng.
14. **Tưởng broker tự đảm bảo exactly once cho side effect HTTP/DB:** cần thiết kế transaction boundary, idempotency và recovery.
15. **Cho rằng restart êm sẽ giống crash:** graceful shutdown có thể drain, nhưng không phải bảo đảm cho sự cố bất ngờ.
16. **Không định nghĩa hợp đồng business về mất/trễ/trùng:** kỹ thuật chỉ đúng khi đáp ứng mức độ tin cậy nghiệp vụ chấp nhận.

## 18. Bài tập tình huống và câu hỏi tự kiểm tra

**Câu 1.** Một hệ thống dùng `@Async @EventListener` để gửi email sau khi nhận đơn hàng. Khi JVM bị kill trước khi worker lấy task từ queue, Spring có tự gửi email lại không?  
**Đáp án:** Không có cam kết mặc định. Queue in-memory không tồn tại qua crash; cần lưu intent bền vững và recovery.

**Câu 2.** Đổi listener thành `@TransactionalEventListener(AFTER_COMMIT)` có giải quyết hoàn toàn mất event không?  
**Đáp án:** Không. Nó giải quyết thứ tự với business commit và tránh xử lý khi rollback, nhưng không tự lưu publication. Crash ngay sau commit có thể làm mất callback.

**Câu 3.** Có thể làm sao để transaction lưu order và intent phát event đồng thời thành công/thất bại?  
**Đáp án:** Ghi order và outbox record trong **cùng DB transaction** có atomic commit.

**Câu 4.** Relay gửi thành công tới broker nhưng chết trước khi đánh dấu SENT. Điều gì xảy ra?  
**Đáp án:** Khi khởi động lại, relay có thể gửi lại cùng event. Consumer phải dùng event ID ổn định và idempotency/dedup.

**Câu 5.** Consumer đã ghi side effect trong DB rồi chết trước ack. Broker có thể phát lại không?  
**Đáp án:** Có theo at-least-once semantics. Dedup marker và DB side effect nên được commit trong cùng transaction phù hợp.

**Câu 6.** Dùng `@EventListener` bình thường trong `@Transactional` rồi gửi external HTTP call ngay, có an toàn khi business rollback không?  
**Đáp án:** Không. External side effect có thể đã thực hiện dù DB transaction rollback.

**Câu 7.** Spring Modulith Event Publication Registry có sẵn tự động mỗi khi bật `@EnableAsync` không?  
**Đáp án:** Không. Đây là subsystem bổ sung cần dependency và cấu hình persistent store/republication phù hợp.

**Câu 8.** Khi nào local async event vẫn đủ tốt?  
**Đáp án:** Khi nghiệp vụ **chấp nhận mất tín hiệu hoặc có cơ chế tính lại khác**, không cần replay qua restart, và đã biết giới hạn latency/rejection của executor.

**Câu 9.** Vì sao không gọi `publishEvent` là một thao tác “publish vào Kafka” nếu không có adapter riêng?  
**Đáp án:** `ApplicationEventPublisher` gốc giao event cho Spring ApplicationContext. Nó không có hợp đồng tự ghi message vào broker; adapter/outbox/externalization cần được thiết kế riêng.

**Câu 10.** Khi cần chắc chắn email được gửi cuối cùng, chỉ cần retry listener vô hạn trong RAM đúng không?  
**Đáp án:** Không. RAM không cứu được crash; retry không giới hạn còn gây áp lực và duplicate. Cần persistent intent, retry có giới hạn/backoff, idempotency và quan sát trạng thái.

**Ghi nhớ:** **Event nội bộ tách rời các bean; `@Async` tách thời điểm thực thi; `AFTER_COMMIT` gắn với thời điểm commit; outbox/registry/broker được cấu hình đúng mới tạo nền tảng lưu bền và recovery.** Luôn tính cả khoảng crash, duplicate và side effect khi nói tới độ tin cậy của sự kiện.

### Tài liệu tham khảo

- [Spring Framework — ApplicationContext events và @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — SimpleApplicationEventMulticaster JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Modulith — Working with Application Events / Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
