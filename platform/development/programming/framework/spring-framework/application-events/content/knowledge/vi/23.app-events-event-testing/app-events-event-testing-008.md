# Kiểm thử số lần phát event trong Spring Framework

## 1. Mục đích: đếm đúng thứ mình cần kiểm chứng

Trong ứng dụng hướng sự kiện, một command hợp lệ có thể cần phát đúng một domain event. Phát thiếu khiến consumer không cập nhật; phát thừa có thể làm gửi thông báo hai lần, tính phí lặp, ghi audit lặp hoặc đẩy thêm công việc vào queue. Vì vậy kiểm thử **số lần phát event** phải là một phần của hợp đồng nghiệp vụ, không chỉ kiểm tra loại event.

Cần phân biệt năm đại lượng:

| Đại lượng | Cách đo | Ý nghĩa |
| --- | --- | --- |
| **Publisher calls** | Mockito `verify(publisher, times(n))` | Tầng service đã gọi API publish bao nhiêu lần |
| **Event recordings** | Spring Test `ApplicationEvents.stream(EventType.class).count()` | Có bao nhiêu event/payload thuộc type được ghi nhận trong test |
| **Listener calls** | Spy, counter hoặc mock listener | Một listener cụ thể được gọi bao nhiêu lần |
| **After-commit handler calls** | Spy hoặc kiểm tra side effect sau commit thật | Listener transaction phase chạy bao nhiêu lần |
| **Broker delivery / consumer side effects** | Integration test với broker, outbox, dedup | Bao nhiêu bản tin/giao dịch được nhận và áp dụng sau retry |

**Một lần publish không đồng nghĩa một lần xử lý listener toàn hệ thống.** Một event có thể được ba listener nhận. Ngược lại, một listener sử dụng `@Async` có thể chưa chạy khi publisher trả về. Event được phát trong transaction sau đó rollback vẫn có thể được `ApplicationEvents` đếm, trong khi listener `AFTER_COMMIT` không bao giờ chạy.

Sơ đồ đơn giản:

```text
SubmitOrder("O-100")
    |
    v
Application service
    |
    +-- validate domain
    +-- repository/persistence boundary
    +-- publishEvent(OrderSubmitted)  <-- publisher calls: 1
             |
             +-- Listener A            <-- listener A calls: 1
             +-- Listener B            <-- listener B calls: 1

Tổng listener calls = 2, nhưng số lần phát event = 1.
```

## 2. Viết hợp đồng về số lần trước khi viết test

| Tình huống | Số `OrderSubmitted` cần publish | Diễn giải |
| --- | ---: | --- |
| Một command hợp lệ | 1 | Một sự thật nghiệp vụ đã được chấp nhận |
| Input vi phạm invariant | 0 | Không có success event |
| Hai command hợp lệ độc lập | 2 | Mỗi command tạo một event |
| Một command đi qua nhiều helper method | Thường 1 | Không publish lặp ở nhiều tầng |
| Cùng idempotency key được retry | Phụ thuộc thiết kế, thường không tạo fact mới | Cần state lưu key và chính sách rõ |
| Transaction rollback sau khi gọi publisher | Có thể đã gọi 1 | Publish count không phải committed count |
| Một event tới hai listeners | 1 publisher call, hai listener calls | Đếm không được cộng số handler |

Mốc đếm cần rõ: theo một command, một aggregate, một lần transaction, một window test, hay một batch. Một domain operation đôi khi phát **nhiều loại event hợp lệ**; không ép mọi bài toán về số 1.

## 3. Unit test: Mockito verify(times(n)) và ArgumentCaptor

Nếu muốn kiểm tra trực tiếp rằng service gọi `ApplicationEventPublisher.publishEvent(...)` đúng số lần, test bằng mock publisher là cách ít tốn kém nhất. Không cần Spring context.

```java
ApplicationEventPublisher publisher = mock(ApplicationEventPublisher.class);
SubmissionService service = new SubmissionService(publisher);

service.submit("O-10", 1200);

ArgumentCaptor<OrderSubmitted> captor =
        ArgumentCaptor.forClass(OrderSubmitted.class);
verify(publisher, times(1)).publishEvent(captor.capture());
assertEquals("O-10", captor.getValue().orderId());
verifyNoMoreInteractions(publisher);
```

Đây là **trích đoạn**; project hoàn chỉnh với class và import ở mục 5. `ArgumentCaptor` giúp xác nhận payload, không chỉ type. `verifyNoMoreInteractions` phát hiện những lời gọi publisher khác mà test chưa xác nhận.

Nhánh từ chối:

```java
assertThrows(IllegalArgumentException.class,
        () -> service.submit("O-10", 0));
verifyNoInteractions(publisher);
```

Kiểm thử 0 lần giúp bắt regression khi code phát success event *trước khi* validate input.

Lưu ý `ApplicationEventPublisher` có hai overload `publishEvent(ApplicationEvent)` và `publishEvent(Object)`. Với domain event là Java record không kế thừa `ApplicationEvent`, lệnh gọi `publishEvent(record)` chọn overload `Object`. Trong test dùng captor đúng kiểu event để Mockito match chính xác.

**Giới hạn của Mockito:** mock xác nhận lời gọi của service, không chứng minh event được Spring dispatch, listener đăng ký đúng, transaction commit hoặc broker nhận message.

## 4. Spring TestContext: @RecordApplicationEvents

Spring Framework hỗ trợ ghi lại application events trong thời gian thực thi **một test method**. Cách dùng:

1. Đặt `@RecordApplicationEvents` trên test class.
2. Sử dụng `@SpringJUnitConfig` hoặc SpringExtension với cấu hình tương đương.
3. Nhận `ApplicationEvents` qua tham số `@Test`.
4. Gọi hành vi cần test rồi đếm `events.stream(OrderSubmitted.class).count()`.

```java
@Test
void publishesOne(@Autowired SubmissionService service,
                  ApplicationEvents events) {
    events.clear();
    service.submit("O-10", 1200);
    assertEquals(1L, events.stream(OrderSubmitted.class).count());
}
```

Đoạn trên chỉ là minh họa, dùng các class/import của ví dụ đầy đủ bên dưới.

`ApplicationEvents.stream(Class<T>)` lọc cả `ApplicationEvent` hoặc **payload object** của type đó. Điều này quan trọng vì khi `publishEvent(Object)` nhận POJO, Spring có thể bọc thành `PayloadApplicationEvent`, nhưng vẫn có thể truy vấn stream theo kiểu payload gốc.

`ApplicationEvents.clear()` bắt đầu một cửa sổ quan sát mới. Nó chỉ xóa **bản ghi event của test recorder**, không xóa event đã gửi, không hoàn tác listener hay rollback transaction.

Recorder được scope cho từng test method, nên cách khai báo tham số method thích hợp hơn giữ object lâu dài. Nếu context có event framework như `ContextRefreshedEvent`, nên lọc type cụ thể, không dùng `events.stream().count()` rồi cho rằng mọi sự kiện đều là event nghiệp vụ.

## 5. Ví dụ Maven + Java 17 chạy đầy đủ

Dự án dùng Spring Framework 6.2.8, JUnit Jupiter 5.12.2 và Mockito 5.18.0. Một service thực thi command, một listener đồng bộ đếm số lần nhận. Có 3 unit tests và 3 integration tests.

### 5.1. Cấu trúc

```text
spring-event-count-test/
├── pom.xml
├── src/main/java/demo/EventCountApp.java
├── src/test/java/demo/EventPublicationUnitTest.java
└── src/test/java/demo/EventPublicationIntegrationTest.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-count-test</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.8</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.18.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.3</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/java/demo/EventCountApp.java

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventCountApp {

    public record OrderSubmitted(String orderId, long amountInCents) {}

    public static final class SubmissionService {
        private final ApplicationEventPublisher publisher;

        public SubmissionService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(String orderId, long amountInCents) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId required");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            publisher.publishEvent(
                    new OrderSubmitted(orderId, amountInCents));
        }
    }

    public static final class CountingListener {
        private final AtomicInteger counter = new AtomicInteger();

        @EventListener
        public void onSubmitted(OrderSubmitted event) {
            counter.incrementAndGet();
        }

        public int calls() {
            return counter.get();
        }

        public void reset() {
            counter.set(0);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        SubmissionService submissionService(
                ApplicationEventPublisher publisher) {
            return new SubmissionService(publisher);
        }

        @Bean
        CountingListener countingListener() {
            return new CountingListener();
        }
    }
}
```

### 5.4. src/test/java/demo/EventPublicationUnitTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class EventPublicationUnitTest {

    @Test
    void oneValidCommandPublishesOneEventWithCorrectPayload() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        var service = new EventCountApp.SubmissionService(publisher);

        service.submit("O-10", 1200);

        ArgumentCaptor<EventCountApp.OrderSubmitted> captor =
                ArgumentCaptor.forClass(
                        EventCountApp.OrderSubmitted.class);
        verify(publisher, times(1)).publishEvent(captor.capture());

        assertEquals("O-10", captor.getValue().orderId());
        assertEquals(1200L, captor.getValue().amountInCents());
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void invalidCommandPublishesNothing() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        var service = new EventCountApp.SubmissionService(publisher);

        assertThrows(IllegalArgumentException.class,
                () -> service.submit("O-11", 0));
        verifyNoInteractions(publisher);
    }

    @Test
    void twoCommandsPublishTwoEvents() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        var service = new EventCountApp.SubmissionService(publisher);

        service.submit("O-20", 100);
        service.submit("O-21", 200);

        verify(publisher, times(2)).publishEvent(
                any(EventCountApp.OrderSubmitted.class));
        verifyNoMoreInteractions(publisher);
    }
}
```

### 5.5. src/test/java/demo/EventPublicationIntegrationTest.java

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = EventCountApp.Config.class)
@RecordApplicationEvents
class EventPublicationIntegrationTest {

    @Test
    void oneCommandRecordedOnceAndListenerRunsOnce(
            @Autowired EventCountApp.SubmissionService service,
            @Autowired EventCountApp.CountingListener listener,
            ApplicationEvents events) {

        events.clear();
        listener.reset();

        service.submit("O-10", 1200);

        assertEquals(1L,
                events.stream(EventCountApp.OrderSubmitted.class).count());
        assertEquals("O-10",
                events.stream(EventCountApp.OrderSubmitted.class)
                        .findFirst().orElseThrow().orderId());
        assertEquals(1, listener.calls());
    }

    @Test
    void invalidCommandRecordsZeroEvents(
            @Autowired EventCountApp.SubmissionService service,
            @Autowired EventCountApp.CountingListener listener,
            ApplicationEvents events) {

        events.clear();
        listener.reset();

        assertThrows(IllegalArgumentException.class,
                () -> service.submit("O-11", -10));

        assertEquals(0L,
                events.stream(EventCountApp.OrderSubmitted.class).count());
        assertEquals(0, listener.calls());
    }

    @Test
    void twoCommandsRecordedExactlyTwice(
            @Autowired EventCountApp.SubmissionService service,
            @Autowired EventCountApp.CountingListener listener,
            ApplicationEvents events) {

        events.clear();
        listener.reset();

        service.submit("O-20", 100);
        service.submit("O-21", 200);

        List<String> ids =
                events.stream(EventCountApp.OrderSubmitted.class)
                        .map(EventCountApp.OrderSubmitted::orderId)
                        .toList();

        assertEquals(List.of("O-20", "O-21"), ids);
        assertEquals(2, listener.calls());
    }
}
```

### 5.6. Chạy và đọc kết quả

Trong thư mục chứa `pom.xml`, cần JDK 17+ và Maven:

```bash
mvn -q clean test
```

Dự án có **hai test classes và sáu test methods**. Khi assertions đúng, Maven trả **exit code 0**. Log/stdout của Maven có thể khác nhau theo cấu hình nên không bịa một block output cố định. Bỏ `-q` để xem summary thực tế của Surefire.

| Test | Publisher calls | Recorder events | Listener invocations |
| --- | ---: | ---: | ---: |
| Unit: 1 command hợp lệ | 1 | Không dùng | Không dùng |
| Unit: 1 command lỗi | 0 | Không dùng | Không dùng |
| Unit: 2 command hợp lệ | 2 | Không dùng | Không dùng |
| Integration: 1 command hợp lệ | 1 theo logic service | 1 | 1 |
| Integration: 1 command lỗi | 0 theo logic service | 0 | 0 |
| Integration: 2 command hợp lệ | 2 theo logic service | 2 | 2 |

`CountingListener` trong demo chạy **đồng bộ theo mặc định** nên sau lời gọi `submit(...)` có thể assert số invocations ngay. Nếu thay bằng `@Async`, assertion tức thời sẽ trở nên không đáng tin.

## 6. Đếm theo type chưa đủ: kiểm tra payload và phạm vi

Một lời gọi publish có thể đúng count nhưng sai order ID. Vì vậy trong unit test có `ArgumentCaptor`; trong integration test, `events.stream(...).map(OrderSubmitted::orderId)` xác nhận ID.

Có thể lọc theo một order cụ thể:

```java
long countForOrder = events.stream(EventCountApp.OrderSubmitted.class)
        .filter(event -> event.orderId().equals("O-10"))
        .count();
assertEquals(1L, countForOrder);
```

Đây là trích đoạn cần biến `events` trong test. Với nhiều tenant hoặc aggregate, hãy phân biệt theo context/ID phù hợp. Một `@EventListener(condition = "...")` có thể bỏ qua event, nên số listener invocations nhỏ hơn số publisher calls mà không hẳn là lỗi.

Nếu có parent/child `ApplicationContext`, event có thể được truyền tới parent; cần chỉ rõ context nào và loại event nào nằm trong phạm vi đo. Nếu có nhiều listener cùng type, tổng số lần gọi listener có thể cao hơn số lần publish.

## 7. Transaction: event count không chứng minh commit

Trong một transaction:

```text
BEGIN
  update orders
  publishEvent(OrderSubmitted) <-- recorder có thể đếm được 1
  ...
ROLLBACK                         <-- bản ghi DB mất
                                 <-- AFTER_COMMIT handler không chạy
```

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` chỉ được kích hoạt sau commit thành công của transaction phù hợp. `ApplicationEvents` recorder ghi nhận **sự kiện đã publish**, không phải một danh sách "committed domain facts" được lưu bền vững.

Để test việc xử lý sau commit:

1. Dùng transaction manager/DB thực sự trong integration test.
2. Publish trong transaction, sau đó cho transaction commit hoặc rollback có kiểm soát.
3. Kiểm tra riêng số lần publisher được gọi, số event record và số lần callback after-commit thực thi.
4. Lưu ý nhiều test Spring có `@Transactional` tự rollback sau test; assert before commit có thể bỏ lỡ phase after-commit như thiết kế.
5. Không suy ra "không có event" chỉ vì `AFTER_COMMIT` không chạy sau rollback; event có thể đã được publish.

`@TransactionalEventListener` mặc định không chạy khi event được publish ngoài transaction, trừ khi cấu hình `fallbackExecution=true`. Với `AFTER_ROLLBACK`, callback đúng phase có thể chạy dù after-commit không chạy.

## 8. Async: kiểm thử listener count không được dựa vào sleep

Với `@Async` hoặc executor trên multicaster, publisher có thể trả về trước khi listener chạy. Assertion ngay lập tức:

```java
publisher.publishEvent(new OrderSubmitted("O-10", 100));
assertEquals(1, listener.calls()); // Có thể flaky nếu async.
```

không ổn định. Nên dùng `CountDownLatch` hoặc future/completion và timeout hữu hạn, không dùng `Thread.sleep(1000)` làm chiến lược chính.

```java
// Trích đoạn ý tưởng, cần listener và imports phù hợp.
CountDownLatch completed = new CountDownLatch(1);
// Listener gọi completed.countDown() khi xử lý xong.
assertTrue(completed.await(3, TimeUnit.SECONDS));
assertEquals(1, processedCounter.get());
```

Mỗi test phải đo đúng milestone: đã enqueue task, listener bắt đầu hay đã xử lý xong. Với `ApplicationEvents`, recorder thuộc vòng đời test method; việc publish từ thread pool riêng có thể liên quan tới cơ chế truyền context/test recorder khác nhau. Không mặc định mọi event phát ở bất kỳ executor nào cũng sẽ xuất hiện theo cùng cách.

Nếu dùng async, test cả kênh error handling. Một listener chạy hai lần do worker retry không chứng minh publisher gọi hai lần.

## 9. Broker, outbox và delivery count

`verify(publisher, times(1))` **không** chứng minh "exactly once" khi có broker và network.

Ví dụ transactional outbox:

```text
TX: insert outbox(eventId=E-1) -> COMMIT
relay attempt 1: broker accepted E-1
relay crashes before marking delivered
relay attempt 2: broker accepted E-1 again
consumer may see E-1 twice
```

Một business fact có đúng một outbox row nhưng broker có thể nhận nhiều bản sao sau retry. Cần kiểm tra:

- `eventId` ổn định, unique constraint hoặc idempotency key cho fact.
- State và outbox row commit/rollback nguyên tử trong cùng transaction.
- Relay có thể retry sau crash mà không mất event.
- Consumer nhận cùng event ID nhiều lần nhưng chỉ áp dụng side effect theo chính sách idempotent.
- Khi có ordering theo aggregate, test thứ tự và replay đúng hợp đồng; không coi count là bằng chứng bảo toàn thứ tự.

Không conflating số domain events được tạo, số publisher calls, số broker sends, số consumer receives và số lần side effect thành công.

## 10. Tránh flaky test và trạng thái nhiễu

**ApplicationContext caching:** Spring TestContext có thể cache context giữa các test. `CountingListener` của demo là singleton; vì thế test đã gọi `listener.reset()` trước khi đo. Nếu không reset, test sau có thể thấy số tích lũy từ test trước.

**Recorder scope:** `ApplicationEvents` theo test method, không nên giữ static field hoặc inject vào constructor test. Dùng method parameter; `events.clear()` khi muốn một window sạch.

**Framework events:** `ContextRefreshedEvent` và test lifecycle events có thể cùng xuất hiện. Lọc theo event type và payload, không dùng count tất cả event.

**Mock interaction:** `verifyNoInteractions(publisher)` dùng cho nhánh mà không có bất kỳ lời gọi publisher nào; `verifyNoMoreInteractions` dùng sau khi đã verify những lời gọi kỳ vọng, để bắt event thừa.

**Song song:** Nếu bật parallel test với một singleton listener mutable, reset có thể đụng nhau. Dùng instance/scope test riêng, counter phù hợp hoặc cách cô lập context/test resources; không mặc định demo đồng bộ sẽ an toàn khi chạy song song.

**Listener exception:** Một listener đồng bộ ném exception có thể khiến `publishEvent` thoát bất thường sau khi một số listener đã chạy. Số publisher calls, recorder events và listener calls có thể khác nhau. Test nguyên nhân và chính sách rollback/error handler riêng.

## 11. Chọn đúng mức kiểm thử

| Mức | Công cụ | Kết luận tin cậy |
| --- | --- | --- |
| Unit service | Mockito `times(n)`, captor | Code gọi publisher đúng n lần, payload đúng |
| Spring integration | `@RecordApplicationEvents`, `ApplicationEvents` | Context ghi nhận event/payload đúng type và count |
| Listener integration | Spy/counter và sync control | Listener cụ thể thực thi đúng số lần |
| Transaction integration | DB + transaction manager | Phân biệt before/after commit và rollback |
| Broker/outbox integration | Testcontainers/broker thật, relay, dedup | Kiểm tra delivery/retry/idempotency có ranh giới |

Trong hệ thống production, nên bổ sung metrics theo event type có cardinality thấp để phát hiện tình trạng số lần publish bất thường. Tuy nhiên metric không thay thế assertions của test và không được tự giả định một event tương ứng một span hay một message được giao thành công.

## 12. Checklist trước khi hoàn thành

- [ ] Viết rõ số lần event cần phát với từng command/batch.
- [ ] Có case **0**, **1** và **2/n** sự kiện.
- [ ] Verify event type **và** payload; không chỉ count.
- [ ] Unit test publisher qua `verify(times(n))`/`ArgumentCaptor`.
- [ ] Spring integration qua `@RecordApplicationEvents`/`ApplicationEvents.stream(type)`.
- [ ] Lọc sự kiện framework/lifecycle khỏi domain event count.
- [ ] Reset listener state hoặc cô lập test context khi cần.
- [ ] Không trộn số publisher invocations với số lần listener được gọi.
- [ ] Không coi publish trước rollback là after-commit success.
- [ ] Với async dùng đồng bộ hóa và timeout hữu hạn.
- [ ] Với outbox/broker test retry, duplicate và idempotent consumer.
- [ ] Không áp dụng "exactly once" cho tác dụng phụ chỉ nhờ một assert đơn lẻ.

## 13. Câu hỏi tự kiểm tra

1. **Một event có ba listener thì publisher calls là bao nhiêu?** — Có thể chỉ một, tùy code phát.
2. **Unit test dùng công cụ nào để đếm lời gọi publisher?** — Mockito `verify(..., times(n))`.
3. **Làm sao kiểm tra payload phát đúng?** — `ArgumentCaptor` hoặc đọc payload từ `ApplicationEvents` stream.
4. **Đếm event trong Spring TestContext dùng gì?** — `@RecordApplicationEvents` và `ApplicationEvents.stream(EventType.class).count()`.
5. **Vì sao cần `events.clear()`?** — Đặt mốc đếm trong test, không xóa publication thật.
6. **Một event đã publish rồi rollback có thể được recorder đếm không?** — Có.
7. **Listener AFTER_COMMIT có chạy sau rollback không?** — Không.
8. **Vì sao assert listener count tức thì có thể sai khi @Async?** — Worker có thể chưa xử lý xong.
9. **Mockito verify một lần có bảo đảm broker không giao trùng không?** — Không.
10. **Vì sao reset singleton listener trước test?** — Context caching có thể giữ counter giữa test methods.

## Tài liệu tham khảo

- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — ApplicationEvents API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Mockito Documentation](https://site.mockito.org/)
