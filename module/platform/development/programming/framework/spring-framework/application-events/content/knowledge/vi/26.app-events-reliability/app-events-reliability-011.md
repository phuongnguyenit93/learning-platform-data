# Đảm bảo thứ tự khi event có phụ thuộc trong Spring Framework

## 1. Bài toán: event A phải hoàn tất trước khi xử lý event B

Một ứng dụng thường tách công việc thành các sự kiện:

```text
OrderSubmitted
    |
    +-- ReserveInventory
    |
    +-- AuthorizePayment
    |
    +-- CreateInvoice
```

Giả sử yêu cầu nghiệp vụ là **chỉ tạo hóa đơn sau khi kho đã giữ được hàng và thanh toán đã được xác nhận**. Nếu ba listener độc lập cùng nghe `OrderSubmitted`, việc chúng được gọi theo thứ tự A, B, C **không tự bảo đảm** các thao tác hoàn tất theo thứ tự đó. Đặc biệt khi dùng `@Async`, thread pool, transaction callback, retry hoặc broker, hai handler có thể chạy chồng lên nhau và kết thúc theo thứ tự khác.

Trong nhóm **Độ tin cậy** của Spring Framework Application Events, “đảm bảo thứ tự” phải được phát biểu chính xác:

- **Thứ tự publish:** producer gọi `publishEvent(E1)` trước `publishEvent(E2)`.
- **Thứ tự dispatch/invocation:** multicaster bắt đầu gọi listener X trước listener Y.
- **Thứ tự hoàn tất:** công việc và side effect của X thật sự thành công trước khi Y thực thi phần phụ thuộc.
- **Thứ tự commit:** thay đổi dữ liệu của E1 được commit trước thay đổi liên quan E2.
- **Thứ tự delivery/consume:** E1 đến và được consumer áp dụng trước E2, kể cả retry, nhiều worker và restart.
- **Thứ tự theo aggregate:** E1 của đơn O-1 phải đi trước E2 của **cùng đơn O-1**; không nhất thiết cần khóa toàn hệ thống giữa các đơn khác nhau.

Đây là các hợp đồng **khác nhau**. Không một annotation `@Order` hay việc tăng số thread của executor có thể thay thế tất cả.

**Nguyên tắc chính:** Khi B thật sự phụ thuộc vào **kết quả thành công** của A, hãy biểu diễn ranh giới ấy bằng một event kết quả như `InventoryReserved` hoặc một trạng thái durable. Chỉ bắt đầu B khi điều kiện tiền đề đã được xác minh.

## 2. `@Order` giải quyết vấn đề nào, chưa giải quyết vấn đề nào?

Spring Framework hỗ trợ `@Order` trên các method `@EventListener` để sắp xếp **thứ tự gọi listener**:

```java
@Order(10)
@EventListener
public void validate(OrderSubmitted event) {
    // Kiểm tra dữ liệu.
}

@Order(20)
@EventListener
public void reserve(OrderSubmitted event) {
    // Giữ hàng.
}
```

Đây là **mã minh họa**, không phải ứng dụng độc lập; cần các bean Spring, import `org.springframework.core.annotation.Order` và `org.springframework.context.event.EventListener`.

Với **multicaster mặc định đồng bộ**, listener `validate` được gọi trước listener `reserve` theo ordering. Nếu `validate` chạy và trả về bình thường, `reserve` mới được gọi trong đường dispatch thông thường. Điều này có thể hữu ích với những thao tác nhỏ, đồng bộ, ở cùng context và event.

Tuy nhiên:

1. `@Order` **không tạo transaction boundary** và không buộc dữ liệu đã commit.
2. Nó không thể bảo đảm callback ngoài hệ thống (HTTP, email, broker) đã thành công nếu listener chỉ **submit** tác vụ rồi trả về.
3. Với `@Async`, phương thức được gọi qua proxy có thể chỉ **đưa task vào executor**; handler khác được dispatch tiếp trong khi task trước còn đang chạy/chưa bắt đầu.
4. Nếu event A và B được publish từ **hai thread/producer khác nhau**, `@Order` giữa các listener của một event không định nghĩa total order giữa A và B.
5. Với custom multicaster sử dụng executor, listener invocation và completion có thể không cùng thứ tự.
6. `@Order` chỉ sắp xếp các listener được Spring nhận biết trong một cơ chế dispatch/phase tương ứng; nó không định nghĩa thứ tự xử lý xuyên service, broker, JVM restart hoặc nhiều node.

Bảng quyết định:

| Công cụ | Bảo đảm hữu ích | Không nên suy luận |
| --- | --- | --- |
| `@Order` + listener đồng bộ | Thứ tự invocation trong cùng dispatch; method trước hoàn tất bình thường rồi method sau được gọi | DB commit, durable delivery, thứ tự toàn cục |
| `@Order` + `@Async` | Thứ tự Spring **gọi/submit** listener theo ordering ở dispatcher phù hợp | Task async hoàn tất theo thứ tự đó |
| Executor một worker | Thực thi tuần tự **các task đã được nhận trên chính executor**, theo semantics queue/policy | Nhiều producer phát đúng thứ tự nghiệp vụ; không có task fail/crash |
| Event `ACompleted` phát sau A thành công | B chỉ **được kích hoạt** khi mốc A được công bố theo code | Event/side effect được lưu bền vững qua crash |
| `@TransactionalEventListener(AFTER_COMMIT)` | Handler chờ commit thành công của transaction đã phát event | Tất cả handler hậu commit hoàn tất hoặc được retry |
| Transactional outbox + sequence + ordered worker | Nền tảng cho delivery đáng tin và ordering theo aggregate nếu triển khai đúng | Exactly-once side effect tự động, ordering xuyên mọi aggregate |

**Kết luận:** `@Order` là công cụ sắp xếp callback, không phải cơ chế orchestration workflow có phụ thuộc.

## 3. Phản ví dụ: hai listener cùng nghe một event

Giả sử cả kho và thanh toán đều xử lý `OrderSubmitted`:

```java
@Component
class InventoryListener {
    @Async("eventExecutor")
    @Order(0)
    @EventListener
    public void reserve(OrderSubmitted event) {
        inventoryApi.reserve(event.orderId());
    }
}

@Component
class PaymentListener {
    @Order(10)
    @EventListener
    public void charge(OrderSubmitted event) {
        paymentApi.charge(event.orderId());
    }
}
```

Đây là **đoạn minh họa, không độc lập**; cần `@EnableAsync`, executor, các API service và Spring-managed beans.

Diễn biến hợp lệ:

```text
Thread publisher                 Worker thread
      |
      +-- dispatch InventoryListener (@Order 0)
      |       |
      |       +-- submit reserve task --------->
      |
      +-- dispatch PaymentListener (@Order 10)
      |       |
      |       +-- paymentApi.charge(...)
      |                                      reserve() vẫn chưa hoàn tất
      |
      +-- publisher tiếp tục
```

Ngay cả khi `@Order(0)` đã được dispatcher xét trước, nó **không chờ** công việc `reserve()` trên executor hoàn tất. Nếu payment cần có hàng đã giữ, hệ thống có race condition.

Một số cách “sửa” không đủ:

- `@Order(-100)` thay cho `@Order(0)`: chỉ đổi priority invocation.
- `Thread.sleep(100)` trong payment listener: độ trễ I/O và scheduler không dự đoán được.
- Tăng thread pool: có thể làm race xuất hiện thường xuyên hơn.
- Dùng `AtomicBoolean reserved` rồi `while (!reserved) {}`: busy-wait, không durable, không đủ cho nhiều event/order.
- Coi việc `publishEvent()` trả về như tín hiệu mọi handler async đã thành công: không đúng hợp đồng API.

Cần **một quan hệ happens-before có ý nghĩa nghiệp vụ**: khi reservation thành công, producer/handler tạo **`InventoryReserved`**; consumer thực hiện bước phụ thuộc chỉ lắng nghe `InventoryReserved`, không lắng nghe `OrderSubmitted`.

## 4. Thiết kế event chain theo mốc hoàn tất

Mô hình hợp lý hơn:

```text
OrderSubmitted
    |
    +-- InventoryService.reserve(orderId)
            |
            +-- THÀNH CÔNG và trạng thái cần thiết đã được ghi nhận
                    |
                    +-- publish InventoryReserved(orderId, reservationId)
                            |
                            +-- PaymentService.authorize(...)
                                    |
                                    +-- THÀNH CÔNG
                                            |
                                            +-- publish PaymentAuthorized
                                                    |
                                                    +-- InvoiceService.create(...)
```

Mỗi event kết quả diễn đạt **một sự thật nghiệp vụ đã đạt được**, thay vì “đang bắt đầu làm việc”.

Với in-memory synchronous service, khi một bước thành công và `publishEvent` được gọi trong handler, event tiếp theo được dispatch theo đường Spring. Với async, handler phải **tự gọi publisher** sau khi công việc hoàn tất:

```java
@Async("eventExecutor")
@EventListener
public void onSubmitted(OrderSubmitted event) {
    Reservation reservation = inventory.reserve(event.orderId());

    // Chỉ publish khi reserve() thực sự thành công.
    publisher.publishEvent(new InventoryReserved(
            event.orderId(), reservation.id()));
}
```

Đây là **mã minh họa**; `inventory`, `Reservation` và event classes thuộc ứng dụng.

Hai điều kiện quan trọng:

1. `inventory.reserve(...)` phải có contract rõ: khi trả về thành công, resource có thật sự được giữ chưa? Nếu chỉ trả một future hoặc “accepted”, phải chờ **đúng completion**, không publish “reserved” quá sớm.
2. `publishEvent(new InventoryReserved(...))` xảy ra **sau thành công của bước trước** nhưng nếu yêu cầu durability qua crash, cần event store/outbox. Việc gọi publisher trong RAM không bảo đảm event kế tiếp được phục hồi sau restart.

Một event thất bại nên có contract riêng như `InventoryReservationFailed`, hoặc một durable workflow state; không phát `InventoryReserved` trong `finally` bất kể kết quả.

## 5. Ví dụ chạy được: `@Order` không chờ async, event kết quả giải quyết phụ thuộc

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.12** và Gradle 8+. Không cần Spring Boot, web server, database hay message broker.

Chúng ta cố tình tạo hai listener của **cùng event** `OrderSubmitted`:

- `AsyncInventoryListener` có `@Order(0)` và `@Async("eventExecutor")`; công việc giữ hàng bị chặn bằng `CountDownLatch`.
- `DirectInvoiceListener` có `@Order(10)` và xử lý **ngay** `OrderSubmitted`; nó đọc trạng thái giữ hàng, dù đã được xếp sau trong dispatch.
- `ChainedInvoiceListener` **không** nghe `OrderSubmitted`, mà nghe `InventoryReserved` chỉ được phát sau khi bước giữ hàng hoàn tất.

Kết quả sẽ chứng minh rằng listener dùng `@Order(10)` vẫn có thể chạy khi công việc async với `@Order(0)` chưa xong; trong khi listener dựa vào event kết quả chỉ chạy khi điều kiện tiền đề đã đạt.

### 5.1. Cấu trúc dự án

```text
spring-dependent-events-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/DependentEventsDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-dependent-events-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.DependentEventsDemo'
}
```

### 5.2. `src/main/java/demo/DependentEventsDemo.java`

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class DependentEventsDemo {

    public record OrderSubmitted(String orderId) {}
    public record InventoryReserved(String orderId) {}

    // Trạng thái chỉ dành cho demo, không phải state store production.
    public static class Probe {
        final CountDownLatch inventoryStarted = new CountDownLatch(1);
        final CountDownLatch allowInventory = new CountDownLatch(1);
        final CountDownLatch invoiceObserved = new CountDownLatch(1);

        final AtomicBoolean inventoryDone = new AtomicBoolean(false);
        final AtomicBoolean directSawDone = new AtomicBoolean(true);
        final AtomicBoolean chainedSawDone = new AtomicBoolean(false);
        final AtomicReference<String> invoicedOrder =
                new AtomicReference<>();
        final AtomicReference<Throwable> workerError =
                new AtomicReference<>();
    }

    public static class AsyncInventoryListener {
        private final Probe probe;
        private final ApplicationEventPublisher publisher;

        public AsyncInventoryListener(
                Probe probe, ApplicationEventPublisher publisher) {
            this.probe = probe;
            this.publisher = publisher;
        }

        @Order(0)
        @Async("eventExecutor")
        @EventListener
        public void reserve(OrderSubmitted event) {
            probe.inventoryStarted.countDown();
            try {
                // Chặn công việc để chứng minh @Order KHÔNG chờ async.
                if (!probe.allowInventory.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "inventory release timeout");
                }

                // Mô phỏng reservation đã thành công.
                probe.inventoryDone.set(true);

                // Event kế tiếp chỉ được publish SAU khi xong bước A.
                publisher.publishEvent(
                        new InventoryReserved(event.orderId()));
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                probe.workerError.compareAndSet(null, ex);
            } catch (RuntimeException ex) {
                probe.workerError.compareAndSet(null, ex);
            }
        }
    }

    // Sắp sau trong dispatch nhưng KHÔNG đồng nghĩa sau khi A hoàn tất.
    public static class DirectInvoiceListener {
        private final Probe probe;

        public DirectInvoiceListener(Probe probe) {
            this.probe = probe;
        }

        @Order(10)
        @EventListener
        public void onSubmitted(OrderSubmitted event) {
            probe.directSawDone.set(probe.inventoryDone.get());
        }
    }

    // Chỉ kích hoạt bằng event biểu diễn bước trước đã thành công.
    public static class ChainedInvoiceListener {
        private final Probe probe;

        public ChainedInvoiceListener(Probe probe) {
            this.probe = probe;
        }

        @EventListener
        public void onInventoryReserved(InventoryReserved event) {
            probe.chainedSawDone.set(probe.inventoryDone.get());
            probe.invoicedOrder.set(event.orderId());
            probe.invoiceObserved.countDown();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("events-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        AsyncInventoryListener asyncInventoryListener(
                Probe probe, ApplicationEventPublisher publisher) {
            return new AsyncInventoryListener(probe, publisher);
        }

        @Bean
        DirectInvoiceListener directInvoiceListener(Probe probe) {
            return new DirectInvoiceListener(probe);
        }

        @Bean
        ChainedInvoiceListener chainedInvoiceListener(Probe probe) {
            return new ChainedInvoiceListener(probe);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            Probe probe = context.getBean(Probe.class);

            try {
                context.publishEvent(new OrderSubmitted("O-42"));

                if (!probe.inventoryStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "async inventory did not start");
                }

                // Thread async đang bị giữ; listener @Order(10)
                // đã được dispatch trên publisher thread.
                System.out.println("direct saw inventory done="
                        + probe.directSawDone.get());
                System.out.println("inventory done before release="
                        + probe.inventoryDone.get());
            } finally {
                // Nếu phát sinh lỗi, vẫn giải phóng worker để shutdown.
                probe.allowInventory.countDown();
            }

            if (!probe.invoiceObserved.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "dependent event was not observed");
            }
            if (probe.workerError.get() != null) {
                throw new IllegalStateException(
                        "inventory worker failed",
                        probe.workerError.get());
            }

            System.out.println("chained saw inventory done="
                    + probe.chainedSawDone.get());
            System.out.println("invoiced order="
                    + probe.invoicedOrder.get());
        }
    }
}
```

### 5.3. Chạy thử

Với JDK 17+ và Gradle đã cài:

```bash
gradle -q run
```

Các dòng `System.out.println` mong đợi:

```text
direct saw inventory done=false
inventory done before release=false
chained saw inventory done=true
invoiced order=O-42
```

Gradle và thư viện có thể in log khác tùy cấu hình; bốn dòng trên là kết quả do chương trình chủ động in.

### 5.4. Tại sao output này xác định?

1. `@EnableAsync` tạo async interceptor cho bean `AsyncInventoryListener`. Spring event infrastructure gọi listener qua Spring bean proxy, nên `reserve(...)` được submit vào `eventExecutor`.
2. Listener `@Order(0)` được dispatch trước listener `@Order(10)` trong hệ thống listener của `OrderSubmitted`, nhưng **công việc reserve được chạy trên thread khác**.
3. `inventoryStarted.countDown()` báo worker đã bắt đầu, rồi worker dừng ở `allowInventory.await(...)`; vì thế `inventoryDone` **chưa thể true** khi main in hai dòng đầu.
4. Listener `DirectInvoiceListener` vẫn chạy trong đường dispatch của `OrderSubmitted`, đọc `false` vì không có bước chờ reservation thành công.
5. `finally` thả latch; worker đặt `inventoryDone=true` rồi gọi `publisher.publishEvent(new InventoryReserved(...))` tường minh.
6. `ChainedInvoiceListener` nghe `InventoryReserved` và được gọi bởi multicaster mặc định đồng bộ trên thread vừa publish event mới; nó đọc `inventoryDone=true`, lưu order ID và mở `invoiceObserved`.
7. Main chỉ in hai dòng cuối **sau** khi latch xác nhận handler phụ thuộc đã quan sát event kết quả. Không dùng `Thread.sleep()` để đoán thứ tự scheduler.

**Giới hạn của demo:** `AtomicBoolean` ở đây chỉ mô phỏng một bước nghiệp vụ đã hoàn tất trong bộ nhớ, **không phải reservation DB hay bảo đảm giao hàng qua crash**. Hệ thống production phải gắn việc publish `InventoryReserved` với **điều kiện lưu trạng thái thành công** và có thiết kế retry/idempotency phù hợp.

## 6. Chọn cách bảo đảm thứ tự theo mức độ phụ thuộc

Không phải mọi event cần cùng một mô hình. Cần phân biệt các tình huống:

| Trường hợp | Cơ chế nên cân nhắc |
| --- | --- |
| Hai thao tác nhỏ, đồng bộ, cùng event, cùng thread | `@Order` + thiết kế handler đơn giản, hoặc gọi service tường minh nếu A bắt buộc trước B |
| B chỉ được khởi động khi A async thành công | Phát `ACompleted` sau A, để B lắng nghe `ACompleted` |
| A và B phải nằm trong **một transaction DB** | Service/orchestrator gọi A rồi B trong cùng `@Transactional`; event không thay thế tính nguyên tử của transaction |
| B cần dữ liệu A đã commit | Publish trong transaction A, tiêu thụ tại `@TransactionalEventListener(AFTER_COMMIT)` hoặc outbox |
| Nhiều events của **cùng aggregate** phải áp dụng theo thứ tự | Monotonic `aggregateSequence`, ordered dispatch theo key, version/gap checking ở consumer |
| Các aggregate độc lập có thể song song | Partition/serialize theo `aggregateId`, cho phép nhiều keys chạy concurrent |
| B cần cả A và C hoàn thành | Durable state machine/join barrier với trạng thái từng tiền đề, không đơn giản trông chờ invocation order |
| Hệ thống nhiều service, crash/retry và yêu cầu bền vững | Transactional outbox + ordered relay + idempotent consumer, hoặc workflow engine |

Ví dụ rất quan trọng: nếu **kiểm tra tồn kho** và **xác thực thanh toán** cùng là tiền đề của **tạo hóa đơn**, chúng có thể chạy song song nhưng cần một **join condition**:

```text
                   +-- InventoryReserved(orderId)
OrderSubmitted ----|
                   +-- PaymentAuthorized(orderId)
                              |
                    [trạng thái đơn đã có cả hai?]
                              |
                              +-- InvoiceRequested(orderId)
```

Cách an toàn là lưu một trạng thái per-order trong DB và chỉ phát `InvoiceRequested` khi cả hai cờ thành công, với **atomic update/optimistic locking hoặc unique constraint** để tránh hai listener đồng thời cùng phát hai hóa đơn. Không nên dùng một `HashMap` static và `if (inventory && payment)` không đồng bộ để quyết định trong hệ thống nhiều thread/node.

## 7. Đồng bộ một service và bảo đảm ordering của event là hai bài toán khác

Nếu yêu cầu nghiệp vụ thực sự là:

1. Kiểm tra tính hợp lệ;
2. Giữ hàng;
3. Ghi nhận thanh toán;
4. Lưu đơn đã xác nhận;

và toàn bộ thao tác nằm trong **cùng DB và cần tính nguyên tử**, nhiều khi code gọi service rõ ràng là giải pháp dễ kiểm soát hơn event choreography:

```java
@Transactional
public void checkout(CheckoutCommand command) {
    validation.validate(command);
    Reservation reservation = inventory.reserve(command);
    Payment payment = paymentRepository.record(
            command, reservation);

    orderRepository.confirm(command.orderId(),
            reservation.id(), payment.id());

    publisher.publishEvent(new OrderConfirmed(
            command.orderId()));
}
```

Đây là **đoạn minh họa**, các loại và services do ứng dụng định nghĩa. Những thao tác DB cùng transaction có thể rollback cùng nhau. Nhưng một lệnh gọi **hệ thống thanh toán HTTP bên ngoài** không tự tham gia transaction DB; khi có service ngoài, cần saga/compensation hoặc workflow với trạng thái.

**Quy tắc:** Event phù hợp để **thông báo mốc đã xảy ra và giảm coupling**, không nhất thiết phù hợp làm công cụ thay thế luồng điều khiển tuần tự khi các bước có phụ thuộc chặt chẽ, cần trả lỗi ngay hoặc phải chạy cùng transaction.

Ngay cả trong một luồng service tường minh, có thể publish một event `OrderConfirmed` sau khi trạng thái DB đã được xác lập, rồi dùng outbox/after-commit cho các tác vụ hậu xử lý.

## 8. `@TransactionalEventListener(AFTER_COMMIT)` giải quyết một loại thứ tự

Ví dụ:

```java
@Transactional
public void placeOrder(CreateOrder command) {
    repository.insert(command);
    publisher.publishEvent(new OrderStored(command.orderId()));
}
```

Listener:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void sendToWarehouse(OrderStored event) {
    warehouseClient.enqueue(event.orderId());
}
```

Đây là các **đoạn minh họa**, cần import Spring transaction annotations, bean services và event types do ứng dụng định nghĩa.

`@TransactionalEventListener(AFTER_COMMIT)` gắn handler vào **mốc transaction đã commit thành công**. Nếu transaction rollback, handler `AFTER_COMMIT` không được gọi. Đây là rào chắn đúng khi downstream cần dữ liệu đã commit.

Nhưng có những giới hạn:

- `AFTER_COMMIT` **không** làm tất cả listener hậu commit hoàn thành tuần tự.
- Nếu nhiều listener `AFTER_COMMIT` có `@Order`, Spring có thể ưu tiên callback trong cùng phase theo ordering, nhưng điều đó không thay thế completion của tác vụ `@Async` hay việc external service xác nhận thành công.
- Với transaction imperative, event cần được publish **khi transaction đang hoạt động trên thread thích hợp**. Publish trên worker thread ngoài transaction rồi mong gắn với transaction của HTTP thread sẽ không đúng.
- Khi không có transaction, listener transactional mặc định **không chạy** (`fallbackExecution=false`).
- Sau commit, JDBC/JPA transaction resources có thể vẫn còn liên kết thread trong giai đoạn callback. Nếu listener phải ghi DB mới, dùng `@Transactional(propagation = REQUIRES_NEW)` ở một service bean được gọi qua proxy hoặc transaction boundary tương đương.
- Nếu executor reject hoặc JVM chết sau DB commit trước khi callback hoàn thành, transaction gốc **không thể rollback** để cứu phần hậu xử lý.

### 8.1. `AFTER_COMMIT` và event B

Nếu listener hậu commit A chạy rồi publish event B trên thread **không còn transaction mới**, `@TransactionalEventListener` cho B có thể **không được gọi** vì không có transaction để đăng ký. Nếu B cần được gắn với commit của một thay đổi DB khác, cần:

```text
T1 commit OrderStored
    |
    +-- after-commit A
          |
          +-- service mở transaction T2 mới
                 |
                 +-- ghi kết quả bước A
                 +-- publish B khi T2 đang hoạt động
                 |
                 +-- T2 COMMIT
                      |
                      +-- listener AFTER_COMMIT của B
```

Không mặc định gọi `publishEvent(B)` ở callback hậu commit rồi đòi mọi transactional listener của B tự bắt được event.

## 9. Nhiều event của cùng aggregate: thứ tự theo `aggregateId` và sequence

Trong kiến trúc có queue/broker hoặc multi-instance, business ordering có thể phải vượt qua restart và retry.

Ví dụ một đơn O-42 thay đổi tuần tự:

```text
Order O-42
  E1: created         aggregateSequence=1
  E2: payment-approved aggregateSequence=2
  E3: shipped         aggregateSequence=3
```

Consumer phải tránh áp dụng E3 khi chưa xử lý các tiền đề cần thiết từ E1/E2.

Một envelope hữu ích:

```java
public record OrderedEvent<T>(
        String eventId,
        String aggregateId,
        long aggregateSequence,
        String eventType,
        String correlationId,
        Instant occurredAt,
        T payload) {}
```

Đây là **định nghĩa minh họa**, cần import `java.time.Instant`. Mỗi trường có vai trò:

- `eventId`: định danh riêng của **mỗi lần event nghiệp vụ được tạo**, phục vụ dedupe.
- `aggregateId`: khóa để phân vùng/serialize các event liên quan cùng entity/aggregate.
- `aggregateSequence`: số thứ tự **tăng đơn điệu cho mỗi event của aggregate**, tạo trong cùng transaction với thay đổi trạng thái/outbox.
- `eventType`: thông báo mốc nghiệp vụ, ví dụ `PaymentAuthorized`.
- `correlationId`: nối các event của cùng workflow/request.
- `occurredAt`: thời gian tham khảo/logging, **không phải cơ chế khóa hoặc total order**.
- `payload`: snapshot bất biến hoặc delta có schema rõ ràng.

**Quan trọng:** Nếu một aggregate version có thể tăng vì một thay đổi **không phát event**, đừng mặc nhiên yêu cầu event sequence phải liên tục bằng entity `@Version`. Có thể quản lý `aggregateSequence` riêng cho event stream hoặc có contract về gaps. Phân biệt `schemaVersion` (phiên bản cấu trúc payload) và `aggregateSequence` (thứ tự các event).

### 9.1. Phát hiện trùng, cũ và bị thiếu event

Một consumer xử lý theo key có thể lưu:

```text
lastAppliedSequence[aggregateId] = n
```

Với event đến có sequence `s`:

```text
s == n + 1 -> đủ điều kiện áp dụng nếu đúng business state,
              commit thay đổi và lastAppliedSequence atomically
s <= n     -> event cũ hoặc trùng; xử lý theo idempotency/contract
s > n + 1  -> có gap: giữ lại/retry/defer và điều tra event còn thiếu
```

Đây là **pseudocode**; phải kết hợp `eventId`, chính sách migration/replay và các trường hợp nghiệp vụ cho phép bỏ qua một số trạng thái. Không áp dụng công thức trên cứng nhắc nếu event stream không bảo đảm sequence liên tục hoặc consumer chủ động chỉ cần trạng thái mới nhất.

Nếu consumer cần từng bước lịch sử, không nên đơn giản “lấy event version lớn nhất rồi ghi đè” khi E1 chưa được xử lý. Nếu consumer chỉ xây dựng **current-state projection** từ snapshot đầy đủ, có thể chọn **last-write-wins theo version** và bỏ event cũ. Hai contract khác nhau, phải ghi rõ.

### 9.2. Atomic update để tránh race của hai consumer

Ví dụ logic SQL minh họa:

```sql
-- Tất cả trong transaction xử lý event của một aggregate.
SELECT last_sequence
FROM consumer_progress
WHERE consumer_name = :consumer AND aggregate_id = :aggregate_id
FOR UPDATE;

-- Chỉ khi incoming_sequence = last_sequence + 1 và event chưa xử lý:
-- 1) áp dụng side effect DB
-- 2) update last_sequence
-- 3) ghi processed_event(event_id) theo unique key
-- COMMIT
```

Đây là **SQL/pseudocode phụ thuộc database**, không phải script chạy được. Việc khóa bản ghi/tranh chấp/unique index phải được thiết kế theo database cụ thể; nếu chưa có dòng `consumer_progress`, cần xử lý tạo dòng và race lúc tạo bằng unique constraint/upsert phù hợp. Các tác vụ ngoài DB (email/HTTP) không tự rollback trong transaction này; dùng outbox/idempotency ở downstream.

Mục tiêu là không cho **hai consumer xử lý song song cùng `aggregateId`** cùng tin rằng họ đang áp dụng sequence tiếp theo.

## 10. Transactional outbox: commit, ordering và retry

Để không mất event khi service crash giữa DB commit và publish, có thể dùng **transactional outbox**:

```text
Transaction T1
  |
  +-- cập nhật aggregate O-42
  +-- tăng aggregateSequence lên k
  +-- INSERT outbox(eventId, O-42, seq=k, payload, status=NEW)
  +-- COMMIT
        |
        +-- outbox relay lấy các hàng NEW đã commit
        +-- phát đến broker theo ordering phù hợp với O-42
        +-- cập nhật trạng thái gửi / retry nếu lỗi
               |
               +-- consumer dedupe, kiểm tra sequence, áp dụng effect
```

Với nhiều producer instance, sequence phải được cấp dưới một quy tắc nhất quán, ví dụ optimistic locking/row lock trên aggregate khi cập nhật cùng transaction. Nếu T1 ghi event E1 rồi rollback, không nên gửi E1; relay chỉ thấy các outbox rows đã commit.

**Outbox không tự bảo đảm ordering nếu relay triển khai tùy tiện.** Những lỗi điển hình:

- Hai relay đọc cùng aggregate và xử lý các outbox rows song song: E2 có thể được gửi/ack trước E1.
- Sử dụng `SELECT ... FOR UPDATE SKIP LOCKED` nhưng không ràng buộc per-aggregate ordering: worker thứ hai có thể bỏ qua E1 đang khóa để gửi E2.
- Retry E1 với backoff dài nhưng vẫn cho E2 vượt qua nếu nghiệp vụ yêu cầu thứ tự nghiêm ngặt.
- Xếp theo timestamp ứng dụng từ nhiều máy: đồng hồ không tạo ordering nghiệp vụ đáng tin.
- Sắp `ORDER BY id` toàn bảng khi ID không phản ánh thứ tự commit/cấp sequence của từng aggregate.
- Publish sang các partitions/queues khác nhau rồi mong broker giữ thứ tự toàn cục.

Nếu yêu cầu thứ tự mạnh theo aggregate, relay cần **mỗi key chỉ có một chuỗi gửi đang hoạt động** hoặc cơ chế version/gap buffer và ACK policy có kiểm soát. Đổi lại throughput per aggregate sẽ có giới hạn; các aggregates độc lập có thể chạy song song.

### Ví dụ cấu trúc outbox

```sql
CREATE TABLE outbox_events (
    event_id VARCHAR(80) PRIMARY KEY,
    aggregate_id VARCHAR(80) NOT NULL,
    aggregate_sequence BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload_json CLOB NOT NULL,
    status VARCHAR(20) NOT NULL,
    UNIQUE (aggregate_id, aggregate_sequence)
);
```

Đây là **DDL minh họa**; điều chỉnh type/index, retention và transaction isolation cho database thực. Unique `(aggregate_id, aggregate_sequence)` ngăn hai event cùng aggregate nhận cùng thứ tự, nhưng **không tự cấp sequence đúng** và **không tự ngăn E2 vượt E1 lúc relay**. Cần thuật toán ghi và dispatch tương ứng.

Cần theo dõi `eventId`, retry count, next attempt time, failure reason, trạng thái processing và trường hợp đã gửi ra broker nhưng worker crash trước khi đánh dấu hoàn tất. Consumer phải idempotent vì outbox relay có thể gửi trùng.

## 11. Ordering qua broker: key, partition và giới hạn

Với một message broker hỗ trợ ordering trong **một partition/queue cụ thể**, có thể định tuyến mọi event của **cùng aggregate** bằng cùng key:

```text
key = orderId
event = { eventId, orderId, aggregateSequence, eventType, payload }
```

Nhưng phải tách các điều kiện:

1. Producer/relay phải **gửi theo đúng sequence** của aggregate; broker không thể tự sửa thứ tự producer gửi sai.
2. Các event có cùng key phải được định tuyến đến **cùng tuyến ordering/partition** trong cấu hình được chọn.
3. Consumer cần xử lý tuần tự, hoặc bảo đảm không commit offset/ack vượt qua một event có dependency chưa xong.
4. Nếu dùng async callbacks hoặc nhiều worker xử lý message trong cùng partition, thứ tự **hoàn tất side effect** vẫn có thể khác thứ tự broker delivery.
5. Retry, rebalances, redelivery, DLQ và restart có thể tạo duplicates hoặc gaps cần xử lý.
6. Broker không tạo một total order đáng dùng giữa **các partitions/aggregates khác nhau**.

Vì vậy “cùng Kafka partition” (hay một hàng đợi tuần tự tương ứng của hệ thống khác) chỉ là **một thành phần** của contract. Trong nhiều tình huống, sequence check và idempotent consumer vẫn cần có.

Nếu B phải phụ thuộc event A của **hai aggregate khác nhau**, chỉ grouping theo `orderId` không giải quyết quan hệ chéo; dùng workflow coordinator/saga hoặc durable join state xác định hai điều kiện đã đạt.

## 12. Xử lý lỗi, timeout và retry mà không phá thứ tự

Một bước phụ thuộc có thể thất bại:

```text
OrderSubmitted
  |
  +-- ReserveInventory
        |
        +-- SUCCESS -> InventoryReserved -> tiếp tục Payment
        |
        +-- TRANSIENT FAILURE -> retry với backoff
        |
        +-- PERMANENT FAILURE -> ReservationFailed / compensation
```

Không phát `InventoryReserved` trong `finally`, vì `finally` chạy **cả khi reserve thất bại**. Không tự động retry **toàn bộ** command tạo đơn đã commit khi chỉ một hậu xử lý lỗi.

Các quyết định cần thiết:

- **Lỗi tạm thời:** retry một bước với backoff/jitter và giới hạn attempts; nếu ordering chặt, các event sau cùng aggregate có thể cần tạm giữ.
- **Lỗi vĩnh viễn:** cập nhật trạng thái thất bại, dead-letter hoặc compensation; không để queue chờ vô hạn không có tín hiệu.
- **Trùng message:** `eventId`/idempotency key; side effect trùng phải được ngăn hoặc an toàn.
- **Timeout ambiguous:** một external call có thể đã thành công dù client nhận timeout; retry phải sử dụng idempotency key hoặc xác minh remote state.
- **Process crash:** state và pending work phải được lưu bền vững nếu yêu cầu recovery; latch/`CompletableFuture` trong RAM không đủ.
- **Executor reject:** `TaskRejectedException` hoặc rejection policy khác xảy ra khi pool/queue đầy; event có thể đã publish nhưng handler không được nhận vào pool.
- **Async exception:** lỗi trong `@Async void` thường không truyền về publisher; cấu hình `AsyncUncaughtExceptionHandler`, metrics và recovery.
- **Chính sách thứ tự:** quyết định rõ “chặn tất cả event sau khi E1 lỗi” hay “cho phép event độc lập vượt E1”; chọn theo dependency graph, không tự áp dụng một total order cho toàn hệ thống.

**Đánh đổi:** ordering nghiêm ngặt có thể gây **head-of-line blocking** — E1 lỗi khiến E2/E3 cùng aggregate phải chờ. Đây có thể là điều đúng nếu E2 thực sự cần E1, nhưng không nên ép các event độc lập vào cùng một hàng chờ không cần thiết.

## 13. Context, thread và object payload

Một event dùng bởi listener async hoặc broker nên có **payload bất biến**:

```java
public record InventoryReserved(
        String eventId,
        String orderId,
        String reservationId,
        long aggregateSequence) {}
```

Đây là định nghĩa minh họa **riêng**, không thay record tối giản trong ví dụ runnable ở mục 5.

Tránh đưa thẳng vào event:

- Entity JPA mutable, Hibernate lazy proxy hoặc `EntityManager`;
- `HttpServletRequest`, `HttpSession`, `MultipartFile`/stream của request;
- `SecurityContext`, live `ThreadLocal`, MDC hoặc connection đang gắn thread;
- `List<MutableLine>` mà record chỉ giữ reference tới các phần tử mutable.

`@Async` không tự propagate imperative transaction, request context hoặc logging context; nếu cần correlation/tenant/user ID để xử lý nghiệp vụ, hãy capture **giá trị đã xác thực** vào immutable DTO khi publish. Cân nhắc `TaskDecorator`/context propagation cho observability, nhưng không dùng nó để kéo dài vòng đời Servlet request.

Một payload bất biến bảo đảm B nhận **dữ liệu nhất quán theo contract đã chụp**, chứ không tự bảo đảm thứ tự commit hoặc delivery. Cần giữ riêng các lớp trách nhiệm.

## 14. Cách kiểm thử thứ tự đáng tin cậy

### 14.1. Test không dùng thời gian ngẫu nhiên

Không dùng:

```java
publishEvent(A);
Thread.sleep(100);
assertTrue(bFinished);
```

Đây là **phản ví dụ**. Máy CI có thể chậm hơn, executor bận hơn hoặc scheduler chọn thread khác. Mô hình tốt hơn là dùng `CountDownLatch`, `Phaser`, future có timeout hoặc một test executor điều khiển được thứ tự.

Ví dụ mục 5 chứng minh đúng vấn đề bằng latch:

- Giữ worker A ở trạng thái chưa hoàn tất;
- Chứng minh handler nhận cùng event nhưng `@Order` lớn hơn vẫn có thể chạy;
- Thả worker A;
- Chờ event `InventoryReserved` và xác minh B chỉ thấy `inventoryDone=true`.

### 14.2. Test thất bại của bước A

Tạo một inventory service cố tình lỗi:

```text
OrderSubmitted -> InventoryReservationFailed
```

Assert **không có** `InventoryReserved`, **không có** `InvoiceRequested`. Nếu ứng dụng có retry, kiểm tra retry attempts và final state, không chỉ kiểm tra một exception.

### 14.3. Test transaction và rollback

Nếu việc công bố event B phụ thuộc DB commit:

- Publish event trong transaction T1, commit T1: B được phát theo đường đã thiết kế.
- Publish event trong T1 rồi rollback: không được có một event "đã commit" gửi cho downstream.
- Với `@TransactionalEventListener(AFTER_COMMIT)`, nếu test được bao bởi Spring Test `@Transactional` rollback mặc định, callback không tự chạy; dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` để kiểm tra mốc commit thật.
- Test sau commit nên kiểm tra trạng thái DB thật hoặc durable outbox, không suy luận từ thứ tự log.

### 14.4. Test cạnh tranh theo aggregate

Tạo hai workers nhận E1/E2 của cùng `aggregateId`, cố tình làm E1 chậm và E2 đến trước. Assert consumer **không áp dụng E2 vượt E1** khi contract yêu cầu sequence liên tục. Kiểm tra:

1. `eventId` đã xử lý không tạo side effect lại khi redelivery.
2. E2 có `sequence=2` phải chờ/được defer nếu `lastAppliedSequence=0`.
3. Sau E1 được áp dụng và commit, E2 mới có thể áp dụng.
4. Hai workers cùng muốn xử lý một event không thể cùng commit side effect nếu dùng unique constraint/locking đúng.
5. Khi E1 không thể xử lý, có DLQ/gap alert/compensation thay vì chờ vô hạn.
6. Các event của `aggregateId` **khác nhau** vẫn có thể chạy song song theo capacity.

### 14.5. Test fault injection cho outbox/broker

Các tình huống:

| Sự cố | Cần xác minh |
| --- | --- |
| T1 rollback | Không có outbox row đã commit gửi ra broker |
| Crash sau T1 commit trước relay | Outbox row còn đó và được khôi phục |
| Crash sau publish trước mark SENT | Có thể gửi trùng; consumer idempotent |
| E1 retry và E2 chờ | Đúng policy per-aggregate ordering |
| Consumer nhận E2 trước E1 | Detect gap, defer hoặc reconcile theo contract |
| Hai relay chạy song song | Không phá thứ tự gửi cùng aggregate |
| Worker thread pool đầy | Không coi rejected event là processing success |
| Rebalance/restart | State dedupe/progress tồn tại và phục hồi |

Một integration test chỉ ghi `@RecordApplicationEvents` có thể chứng minh event đã được Spring publish; **không tự chứng minh** tất cả async listeners đã hoàn tất, DB đã commit, hoặc broker đã bảo toàn ordering. Test phải quan sát đúng ranh giới muốn bảo đảm.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Listener `@Order(10)` chạy khi `@Order(0)` chưa xong | Listener trước dùng `@Async` hoặc chỉ submit task | B nghe event kết quả của A, hoặc gọi service tuần tự |
| Event E2 được publish sau E1 nhưng hoàn tất trước E1 | Executor nhiều worker, service time khác nhau | Serialize theo key hoặc chờ completion đúng condition |
| Đổi executor sang một thread vẫn sai ordering nghiệp vụ | Nhiều producer submit không đúng sequence hoặc side effect async con | Version/sequence cấp trong transaction, state machine |
| B đọc DB nhưng chưa thấy A | A chưa commit hoặc worker ở transaction khác | `AFTER_COMMIT` hoặc outbox, không dựa vào dispatch |
| Listener B `AFTER_COMMIT` không chạy | Event B phát ngoài transaction khi `fallbackExecution=false` | Publish trong transaction phù hợp hoặc thay thiết kế listener |
| E2 ghi đè trạng thái mới/đúng | E2 đến sai thứ tự hoặc update không kiểm tra version | Atomic sequence/version check |
| Outbox dùng nhiều relay bị đảo event | Concurrent workers/`SKIP LOCKED` vượt E1 | Per-key ordered relay, gap/sequence validation |
| Kafka cùng partition nhưng side effect bị đảo | Consumer tự đưa các message vào pool rồi xử lý song song | Serialize processing per key, ack/commit sau đúng boundary |
| Duplicate event sau retry | Relay crash sau publish, broker redelivery | `eventId`, idempotent consumer và unique constraints |
| Cần cả Inventory và Payment nhưng invoice phát quá sớm | Chỉ nghe một event hoặc kiểm tra flags không atomic | Durable join state và atomic transition |
| Chain dừng mà publisher không thấy lỗi | `@Async void` exception trên worker | Async error handler, metrics, failure event/state, retries |
| Event mất sau JVM crash | Chỉ dùng Spring Application Events trong RAM | Transactional outbox hoặc durable queue |
| Test thỉnh thoảng fail ordering | `sleep` hoặc assert ngay sau async publish | Latch/future/controlled executor với timeout |

## 16. Checklist thiết kế ordering cho event có phụ thuộc

Trước khi đưa một chuỗi event vào production:

- [ ] Đã định nghĩa “thứ tự” là **publish, invocation, completion, commit hay consume**?
- [ ] B phụ thuộc **mốc nào của A**: đã bắt đầu, đã xong thao tác, hay đã commit?
- [ ] Có đang hiểu nhầm `@Order` là bảo đảm completion của `@Async` không?
- [ ] Có một event `ACompleted`/`ACommitted` chỉ được phát **sau khi A thành công**?
- [ ] Nếu A và B cùng DB transaction, nên gọi service tuần tự thay vì dựng event chain phức tạp?
- [ ] Nếu A ngoài hệ thống, đã định nghĩa timeout, idempotency, retry và compensation?
- [ ] Nếu workflow có nhiều tiền đề, có durable join state và atomic transition?
- [ ] Nếu có nhiều instance, đã chọn `aggregateId` làm ordering key và cấp sequence đúng?
- [ ] Outbox relay có ngăn E2 vượt E1 của cùng aggregate?
- [ ] Consumer có dedupe, gap detection và lastAppliedSequence lưu bền vững?
- [ ] Broker/queue/worker có hiểu đúng phạm vi ordering (per partition/key, không phải global)?
- [ ] Có test race với latch và fault-injection cho retry/crash?
- [ ] Khi ordering gây head-of-line blocking, có SLO, alert và phương án giải quyết event kẹt?

**Tóm tắt:** Trong Spring Framework Application Events, `@Order` chỉ sắp thứ tự **gọi listener** theo bối cảnh dispatch; với `@Async`, nó không thể bảo đảm tác vụ trước đã hoàn tất. Khi event có quan hệ phụ thuộc, hãy phát event **đánh dấu bước trước hoàn thành thành công**, cho bước sau lắng nghe đúng event đó, hoặc dùng orchestrator/state machine nếu có nhiều điều kiện. Khi yêu cầu tồn tại qua commit, crash, nhiều instance và retry, bổ sung **transactional outbox, sequence theo aggregate, ordered processing và idempotent consumer**. Không nhầm thứ tự được gọi với tính đúng đắn của kết quả nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events, `@Order` và Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async`](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — `TransactionPhase.AFTER_COMMIT` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Transactional Outbox Pattern — microservices.io](https://microservices.io/patterns/data/transactional-outbox)
