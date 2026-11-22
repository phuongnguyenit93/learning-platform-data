# Giá trị trả về của @EventListener: phát event tiếp theo và tạo chuỗi event

Trong Spring Framework Application Events, method gắn `@EventListener` không bắt buộc phải trả về `void`. **Nếu một listener đồng bộ trả về một đối tượng, Spring có thể phát đối tượng đó như một application event mới.** Khi trả về một `Collection` hoặc một mảng, **mỗi phần tử** được phát thành một event riêng. Nhờ vậy, ta có thể biểu diễn một chuỗi xử lý đơn giản: nhận event A → tạo event B → listener của B tiếp tục tạo C.

Điều này khác với “trả dữ liệu cho người gọi” trong một Java method thông thường. Giá trị trả về được bộ điều hợp `@EventListener` (listener adapter) xử lý **khi method được gọi bởi cơ chế event của Spring**; nó không phải HTTP response, không phải kết quả trả về trực tiếp của `ApplicationEventPublisher.publishEvent(...)`, và cũng không phải một hàng đợi event bền vững.

Bài học trình bày chính xác ngữ nghĩa của một đối tượng, `null`, `void`, mảng, `Collection`, giới hạn của `@Async`, cách tránh vòng lặp event và một bộ kiểm thử Java 17+ chạy bằng Spring Test/JUnit 5.

## 1. Cơ chế: listener trả về gì, Spring làm gì?

Spring đăng ký các method `@EventListener` của bean được quản lý và gọi chúng khi có event khớp với kiểu tham số. Trong chế độ phát event đồng bộ mặc định, trình tự khái niệm là:

~~~text
publisher.publishEvent(StartRequested)
    |
    +-- @EventListener onStart(StartRequested)
            |
            +-- return StartChecked
                      |
                      +-- Spring phát StartChecked
                                |
                                +-- @EventListener onChecked(StartChecked)
                                        |
                                        +-- return AuditRequested
                                                  |
                                                  +-- Spring phát AuditRequested
                                                            |
                                                            +-- @EventListener onAudit(...)
~~~

Các `return` này cho phép một listener biến **kết quả nghiệp vụ** của bước đang xử lý thành một event khác. Spring sẽ tra các listener của event mới giống như khi application code tự gọi `publishEvent(new ...)`.

| Giá trị của method `@EventListener` | Cách xử lý điển hình | Ghi chú |
| --- | --- | --- |
| `new NextEvent(...)` | Phát **một** `NextEvent` | Event mới tiếp tục qua hệ thống listener |
| `List.of(eventA, eventB)` | Phát **hai** event riêng | Không coi cả `List` là một event nghiệp vụ |
| `new Object[] { eventA, eventB }` | Phát từng phần tử của mảng | Có thể là nhiều kiểu event khác nhau |
| `Collections.emptyList()` | Không phát event tiếp theo | Phù hợp với nhánh không có kết quả |
| `null` từ method có return type | Không phát event tiếp theo | Dùng có chủ đích, tránh để nhầm lẫn |
| `void` | Không có event phát sinh từ return | Listener vẫn có thể tự gọi publisher tường minh |
| Một scalar không phải `ApplicationEvent` | Spring xử lý như **payload event** | Spring cho phép event là đối tượng Java bất kỳ |

Spring Framework cho phép publish không chỉ `ApplicationEvent` mà còn bất kỳ đối tượng thường (payload). Vì vậy một Java record không kế thừa `ApplicationEvent` vẫn dùng được làm event, ví dụ `record PaymentAccepted(String id) {}`.

**Không có giá trị “đặc biệt” cần trả về để xác nhận đã tiêu thụ event.** Spring không dùng `true`/`false` từ method như một cơ chế ack/nack mặc định. Nếu listener trả về `Boolean.TRUE`, nó có thể bị publish như một payload event kiểu `Boolean` — thường không phải thiết kế mong muốn.

## 2. Trả về một event: chuỗi A → B

Ví dụ một đơn đặt hàng cần kiểm tra trước khi phát yêu cầu ghi nhận:

~~~java
record OrderSubmitted(String orderId) {}
record OrderValidated(String orderId) {}

@Component
class OrderValidationListener {

    @EventListener
    public OrderValidated validate(OrderSubmitted event) {
        // Kiểm tra nghiệp vụ, rồi tạo kết quả.
        return new OrderValidated(event.orderId());
    }
}
~~~

Đây là **trích đoạn** trong ứng dụng Spring: cần import `org.springframework.stereotype.Component` và `org.springframework.context.event.EventListener`. Khi `OrderSubmitted` được publish và `validate` chạy qua Spring listener adapter, đối tượng `OrderValidated` trả về sẽ được publish như event thứ hai. Một listener khác có thể nghe `OrderValidated`.

Nếu chỉ gọi trực tiếp `new OrderValidationListener().validate(event)` bằng Java, phương thức vẫn trả về record, **nhưng sẽ không có bước tự động publish** vì lời gọi không đi qua hệ thống event của Spring.

Từ góc nhìn domain, hãy đặt tên các event theo điều đã xảy ra hoặc kết quả có nghĩa. Không nên đặt `OrderValidated` chỉ vì muốn ghép ba method; nếu đây là một bước bắt buộc của một command, gọi service trực tiếp có thể dễ kiểm thử, trace và quản lý lỗi hơn.

### Return value không phải kết quả của publishEvent

~~~java
publisher.publishEvent(new OrderSubmitted("ORD-01"));
~~~

`ApplicationEventPublisher.publishEvent(...)` là API phát event và có kiểu trả về `void`; nó không trả `OrderValidated` cho caller. Dù listener có trả `OrderValidated`, sự kiện đó được Spring xử lý qua lần phát event khác, không tạo một `Future<OrderValidated>` hay một giá trị có thể nhận trực tiếp từ lệnh publish.

## 3. Trả về Collection hoặc mảng: một event đầu vào, nhiều event đầu ra

Ví dụ khi một đơn hàng được chấp nhận, cần phát hai event phục vụ hai trách nhiệm tách biệt: cập nhật audit và yêu cầu gửi thông báo.

~~~java
record OrderAccepted(String orderId) {}
record AuditRequested(String orderId) {}
record NotificationRequested(String orderId) {}

@Component
class FanOutListener {

    @EventListener
    public List<Object> split(OrderAccepted event) {
        return List.of(
            new AuditRequested(event.orderId()),
            new NotificationRequested(event.orderId())
        );
    }
}
~~~

Đây là trích đoạn, cần import `java.util.List`, `@Component`, `@EventListener`. Spring không gửi một sự kiện duy nhất có payload là `List<Object>` trong trường hợp method trả về `Collection`; nó duyệt các phần tử và publish **từng event riêng**. Dùng `List<Object>` ở đây cho phép phần tử thuộc nhiều event class; nếu mọi phần tử cùng kiểu, có thể chọn `List<AuditRequested>`.

Tương đương về mặt số lượng, method có thể trả mảng:

~~~java
@EventListener
public Object[] splitAsArray(OrderAccepted event) {
    return new Object[] {
        new AuditRequested(event.orderId()),
        new NotificationRequested(event.orderId())
    };
}
~~~

Đây là **phương án thay thế** cho method `split`, không nên đăng ký cả hai listener cùng nhận `OrderAccepted` nếu nghiệp vụ chỉ mong hai event. Khi cùng đăng ký cả hai, chúng sẽ tạo ra bốn sự kiện từ một đầu vào.

Một `Set` cũng là `Collection` nhưng không nên dựa vào thứ tự phần tử của mọi loại `Set`. Nếu thứ tự phân nhánh quan trọng, chọn cấu trúc có thứ tự, nhưng vẫn phải hiểu rằng các listener khác, async executor hay các transaction riêng có thể khiến **thứ tự hoàn tất** khác thứ tự phát.

**Không tự hiểu `Map`, `Optional`, `CompletableFuture` hay `Mono` như danh sách event con.** Hợp đồng return-value chuẩn được tài liệu hóa cho đối tượng, mảng, `Collection`; nếu muốn kiểm soát rõ nhiều event, dùng `Collection`/mảng hoặc publish thủ công trong bước thực thi thích hợp.

## 4. Return null hoặc void để dừng chuỗi

Không phải event nào cũng phải sinh event tiếp theo:

~~~java
record ReviewRequested(String orderId, boolean approved) {}
record ReviewApproved(String orderId) {}

@Component
class ReviewListener {

    @EventListener
    public ReviewApproved onReview(ReviewRequested event) {
        if (!event.approved()) {
            return null; // Không phát ReviewApproved.
        }
        return new ReviewApproved(event.orderId());
    }
}
~~~

Đây là trích đoạn, cần import các annotation. Nếu một `ReviewRequested` không được duyệt, Spring không publish `ReviewApproved` từ giá trị `null`. Method `void` cũng không phát event thông qua return. Một `Collection` rỗng hữu ích khi method được thiết kế để phát nhiều event nhưng một nhánh không tạo gì.

Cần phân biệt **không phát event con** với **không xử lý event đầu vào**: Spring vẫn đã gọi listener, vẫn có thể có log, truy vấn hoặc tác dụng phụ trước khi return. Nếu muốn lọc listener không chạy với event nhất định, có thể cân nhắc `@EventListener(condition = "...")` với SpEL, nhưng đây là một cơ chế khác với trả `null`.

## 5. Ví dụ tích hợp hoàn chỉnh với Spring Test và JUnit 5

Ví dụ này chỉ cần **Spring Context và Spring Test**; không cần Spring Boot hay database. Ta mô phỏng ba loại chuỗi: một event ra một event; một event ra hai event bằng `List` hoặc mảng; và một nhánh trả `null`.

### 5.1. Cấu hình Gradle

Tạo project Java 17 với file `build.gradle`:

~~~groovy
plugins {
    id 'java'
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
    testImplementation platform('org.springframework:spring-framework-bom:6.2.9')
    testImplementation 'org.springframework:spring-context'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Bộ version là ví dụ thuộc Spring Framework 6.2 / Java 17; trong dự án Spring Boot hãy ưu tiên BOM đồng bộ do Boot quản lý. Với Gradle wrapper của project, không cần cài Gradle hệ thống.

### 5.2. File `src/test/java/example/events/EventListenerReturnValueTest.java`

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(EventListenerReturnValueTest.Config.class)
class EventListenerReturnValueTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired ChainListeners listeners;
    @Autowired Trace trace;

    @BeforeEach
    void clearTrace() {
        trace.clear();
    }

    @Test
    void oneReturnValueThenCollectionCreatesChainedEvents() {
        publisher.publishEvent(new StartRequested("A-1"));

        assertEquals(
            List.of(
                "start:A-1",
                "checked:A-1",
                "audit:A-1",
                "notify:A-1"
            ),
            trace.snapshot()
        );
    }

    @Test
    void arrayReturnCreatesIndividualEvents() {
        publisher.publishEvent(new BatchRequested("B-2"));

        assertEquals(
            List.of("batch:B-2", "first:B-2", "second:B-2"),
            trace.snapshot()
        );
    }

    @Test
    void nullReturnStopsThatBranch() {
        publisher.publishEvent(new DecisionRequested("C-3", false));
        assertEquals(
            List.of("decision:C-3:false"),
            trace.snapshot()
        );

        publisher.publishEvent(new DecisionRequested("D-4", true));
        assertEquals(
            List.of(
                "decision:C-3:false",
                "decision:D-4:true",
                "approved:D-4"
            ),
            trace.snapshot()
        );
    }

    @Test
    void directJavaCallDoesNotRepublishReturnValue() {
        CheckedEvent result = listeners.onStart(new StartRequested("E-5"));

        assertEquals("E-5", result.id());
        assertEquals(List.of("start:E-5"), trace.snapshot());
    }

    record StartRequested(String id) {}
    record CheckedEvent(String id) {}
    record AuditRequested(String id) {}
    record NotifyRequested(String id) {}

    record BatchRequested(String id) {}
    record FirstEvent(String id) {}
    record SecondEvent(String id) {}

    record DecisionRequested(String id, boolean approved) {}
    record ApprovedEvent(String id) {}

    static class Trace {
        private final List<String> lines = new ArrayList<>();

        void add(String value) {
            lines.add(value);
        }

        List<String> snapshot() {
            return List.copyOf(lines);
        }

        void clear() {
            lines.clear();
        }
    }

    static class ChainListeners {
        private final Trace trace;

        ChainListeners(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public CheckedEvent onStart(StartRequested event) {
            trace.add("start:" + event.id());
            return new CheckedEvent(event.id());
        }

        @EventListener
        public List<Object> onChecked(CheckedEvent event) {
            trace.add("checked:" + event.id());
            return List.of(
                new AuditRequested(event.id()),
                new NotifyRequested(event.id())
            );
        }

        @EventListener
        public void onAudit(AuditRequested event) {
            trace.add("audit:" + event.id());
        }

        @EventListener
        public void onNotify(NotifyRequested event) {
            trace.add("notify:" + event.id());
        }

        @EventListener
        public Object[] onBatch(BatchRequested event) {
            trace.add("batch:" + event.id());
            return new Object[] {
                new FirstEvent(event.id()),
                new SecondEvent(event.id())
            };
        }

        @EventListener
        public void onFirst(FirstEvent event) {
            trace.add("first:" + event.id());
        }

        @EventListener
        public void onSecond(SecondEvent event) {
            trace.add("second:" + event.id());
        }

        @EventListener
        public ApprovedEvent onDecision(DecisionRequested event) {
            trace.add(
                "decision:" + event.id() + ":" + event.approved()
            );
            if (!event.approved()) {
                return null;
            }
            return new ApprovedEvent(event.id());
        }

        @EventListener
        public void onApproved(ApprovedEvent event) {
            trace.add("approved:" + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        Trace trace() {
            return new Trace();
        }

        @Bean
        ChainListeners listeners(Trace trace) {
            return new ChainListeners(trace);
        }
    }
}
~~~

### 5.3. Chạy và đọc kết quả

Trên hệ thống có Gradle wrapper:

~~~bash
./gradlew test --tests "example.events.EventListenerReturnValueTest"
~~~

Trên Windows PowerShell, dùng `./gradlew.bat test --tests "example.events.EventListenerReturnValueTest"`.

Test không in dấu vết `start`, `checked`, `audit` hoặc `notify` ra stdout; những chuỗi đó được **assert** trong `Trace`. Khi các test thành công, ý nghĩa của chúng là:

- **Chuỗi một event và Collection:** `StartRequested` → `CheckedEvent` → mỗi phần tử của `List` tạo `AuditRequested` và `NotifyRequested`, được nhận theo thứ tự phát của danh sách trong mô hình đồng bộ có một listener cho mỗi kiểu.
- **Mảng:** `Object[]` được Spring trải ra từng event, không cần tự gọi `publishEvent` hai lần.
- **Null:** nhánh `DecisionRequested(..., false)` không tạo `ApprovedEvent`, còn nhánh `true` thì có.
- **Gọi method trực tiếp:** `listeners.onStart(...)` trả record Java bình thường nhưng không tự publish `CheckedEvent`; chỉ lời gọi qua hệ thống listener mới có cơ chế tạo event tiếp theo.

Các assertion về thứ tự ở ví dụ chỉ dựa trên **một listener cho mỗi kiểu event con** và cơ chế synchronous mặc định. Không suy ra một cam kết tổng quát về thứ tự completion giữa nhiều listeners độc lập khi có `@Async` hoặc executor.

## 6. Giới hạn quan trọng: @Async và event listener bất đồng bộ

Spring Framework ghi rõ: **listener bất đồng bộ không thể publish event tiếp theo bằng giá trị trả về**. Nếu dùng `@Async` trên `@EventListener`, bạn phải chủ động gọi `ApplicationEventPublisher` khi công việc bất đồng bộ tạo được kết quả.

Ví dụ minh họa trong một Spring bean có cấu hình `@EnableAsync`:

~~~java
@Component
class AsyncValidationListener {
    private final ApplicationEventPublisher publisher;

    AsyncValidationListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Async
    @EventListener
    public void validate(StartRequested event) {
        // Xử lý bất đồng bộ ...
        publisher.publishEvent(new CheckedEvent(event.id()));
    }
}
~~~

Đây là **trích đoạn**, cần các record và import `@Component`, `@Async`, `@EventListener`, `ApplicationEventPublisher`; cấu hình `@EnableAsync` cũng phải có. `publisher.publishEvent(...)` được gọi **tường minh** trong công việc async, thay vì `return new CheckedEvent(...)`. Không đưa trích đoạn này vào cùng context của test đồng bộ nếu không muốn tạo thêm listener nhận `StartRequested`.

Lưu ý khi async:

- `publishEvent()` của caller không đợi công việc async hoàn tất; test cần cơ chế await có timeout thay vì assert ngay sau publish.
- Exception của async listener không nhất thiết được truyền ngược đến người publish; cần chiến lược quan sát lỗi, logging và retry.
- `ThreadLocal`, MDC và transaction context không tự động truyền sang executor trong mọi cấu hình.
- Không dùng `@Async` chỉ để “giải quyết” vòng lặp event; nó thay đổi ranh giới lỗi, thời điểm hoàn tất và thứ tự xử lý, không tự cung cấp durable queue.

Nếu multicaster được cấu hình với `TaskExecutor` thay cho chế độ đồng bộ mặc định, cũng cần đánh giá lại ngữ nghĩa thứ tự, lỗi và thread của mỗi listener. Với yêu cầu chắc chắn tạo chuỗi công việc cần được chờ kết quả, dùng pipeline/orchestrator tường minh có thể phù hợp hơn phép nối ngầm qua event.

## 7. Thứ tự, tái nhập và vòng lặp event

### 7.1. Một return có thể tạo chuỗi lồng nhau ngay lập tức

Trong chế độ đồng bộ mặc định, method listener xử lý A xong và trả B; Spring có thể phát B **ngay trong call stack của lần publish A**. B tiếp tục sinh C, tạo một chuỗi lồng nhau. Điều này có lợi cho luồng ngắn, nhưng nếu chuỗi dài hoặc có nhánh lặp, call stack có thể tăng sâu, exception có thể lan ngược và khó debug.

~~~text
A --> listener A returns B
      B --> listener B returns C
            C --> listener C returns D
                  ...
~~~

Đây không phải replay engine và Spring không tự cung cấp số lần thử, durable checkpoint, hop-count limit hay cơ chế phát lại sau process crash.

### 7.2. Tránh chu kỳ A → B → A

Ví dụ thiết kế nguy hiểm:

~~~java
@EventListener
public BEvent onA(AEvent event) {
    return new BEvent(event.id());
}

@EventListener
public AEvent onB(BEvent event) {
    return new AEvent(event.id());
}
~~~

Hai method trên là **trích đoạn minh họa lỗi thiết kế**, không phải file độc lập. Nếu cả hai liên tục nhận event và trả event đối nghịch mà không có điều kiện dừng, quá trình publish có thể đệ quy mãi đến khi lỗi `StackOverflowError` hoặc cạn tài nguyên.

Cách khắc phục thường tốt hơn là thiết kế **luồng trạng thái hữu hạn**, phân biệt command và event, không để listener lặp lại cùng thao tác; nếu retry thật sự cần thiết, dùng cơ chế retry có giới hạn, backoff, dead-letter và idempotency ở layer phù hợp. Có thể kiểm soát một `correlationId`, `eventId` hoặc số lần xử lý khi có lý do nghiệp vụ, nhưng không xem chúng như một giải pháp duy nhất cho vòng lặp thiết kế.

### 7.3. @Order không thay thế chain semantics

`@Order` trên `@EventListener` giúp đặt ưu tiên invocation **giữa các listener của cùng một event** khi cơ chế dispatch có xét thứ tự. Nó không biến một `@EventListener` đang trả B thành listener đợi transaction commit; cũng không bảo đảm completion order khi listener chạy async.

Một chuỗi **A trả B** phụ thuộc vào loại event và kết quả method A. Một nhóm **nhiều listener nhận A** là fan-out của cùng một event. Hai cấu trúc khác nhau, nên đừng dùng `@Order` để mô phỏng phụ thuộc nghiệp vụ phức tạp giữa hàng loạt listeners.

## 8. Return event so với publishEvent tường minh

Cả hai cách có thể tạo event kế tiếp khi xử lý đồng bộ:

~~~java
// Cách 1: khai báo kết quả qua return.
@EventListener
public CheckedEvent onStart(StartRequested event) {
    return new CheckedEvent(event.id());
}

// Cách 2: publish có chủ đích trong thân listener.
@EventListener
public void onStartExplicit(StartRequested event) {
    publisher.publishEvent(new CheckedEvent(event.id()));
}
~~~

Đây là hai **phương án thay thế**, không đăng ký đồng thời cho cùng event nếu chỉ muốn một `CheckedEvent`. `publisher` ở cách 2 là `ApplicationEventPublisher` đã được inject.

So sánh:

| Tiêu chí | Return event | Publish tường minh |
| --- | --- | --- |
| Mã cho một bước chuyển đơn giản | Gọn, ít boilerplate | Dài hơn một chút |
| Nhiều event đầu ra | Trả `Collection`/mảng | Nhiều lệnh publish, có thể có điều kiện giữa các lệnh |
| Xử lý tại thời điểm quyết định trong method | Trả sau khi method hoàn thành | Có thể publish ở giữa method |
| Listener dùng `@Async` | **Không hỗ trợ** chuỗi bằng return | Là cách cần dùng khi thật sự muốn phát event con |
| Dễ nhìn ranh giới event trong code | Chỉ thấy thông qua return type | Thấy lệnh publish rõ ràng |
| Bền vững/retry qua process crash | Không tự có | Cũng không tự có; cần outbox/broker/registry riêng |

Chọn return event khi luồng đủ ngắn, kết quả có ý nghĩa domain và người đọc dễ theo dõi. Chọn publish tường minh khi cần kiểm soát thứ tự các tác dụng phụ trong method, dùng async, hoặc muốn thể hiện rõ nơi event được phát. Khi nghiệp vụ bắt buộc hoàn tất tuần tự với xử lý lỗi chặt chẽ, một application service gọi các bước bằng method thông thường có thể minh bạch hơn cơ chế event chaining.

## 9. Liên hệ transaction: return value không phải after-commit

Nếu event đầu được publish **bên trong một transaction**, listener đồng bộ thường chạy trong cùng thread và event mới được tạo từ return cũng có thể được phát **trước khi transaction gốc commit**.

~~~text
BEGIN DB TRANSACTION
  UPDATE orders ...
  publish OrderSubmitted
      @EventListener onSubmitted -> return OrderValidated
          @EventListener onValidated -> gửi email  [chưa commit]
  lỗi nghiệp vụ
ROLLBACK
=> email có thể đã gửi dù database rollback.
~~~

Vì vậy **đổi sang return event không sửa được lỗi transaction boundary**. Nếu một side effect chỉ được thực hiện khi transaction commit thành công, cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)` với contract phù hợp. Nếu cần giao message chắc chắn dù JVM chết sau commit, `AFTER_COMMIT` đơn thuần vẫn chưa đủ; transactional outbox hoặc event publication registry có cơ chế lưu/khôi phục là lựa chọn thích hợp hơn.

Đừng mặc định giá trị trả về của một `@TransactionalEventListener` sẽ tạo pipeline có transaction mới hoặc được đảm bảo giao nhận: hãy xử lý yêu cầu sau commit theo cơ chế transaction/bền vững riêng. Với reactive/async pipelines, luôn xem xét context, cách subscribe và cách propagate lỗi.

## 10. Sai lầm phổ biến và checklist

| Sai lầm | Vì sao gây lỗi | Cách làm phù hợp |
| --- | --- | --- |
| Trả một `String` chỉ để log và quên rằng return sẽ được publish | Nó có thể trở thành một payload event không mong đợi | Dùng `void` để không phát event, hoặc trả event type rõ ràng |
| Trả `List` và chờ một listener nhận nguyên danh sách | Spring xử lý `Collection` thành từng event | Nếu danh sách là một payload nghiệp vụ duy nhất, đóng gói vào một record khác |
| Trả `null` nhưng kỳ vọng listener sau chạy | Không có event được publish từ `null` | Trả đối tượng event cụ thể nếu nhánh cần tiếp tục |
| Gọi thẳng `listener.method()` và chờ publish tiếp | Java direct call không đi qua listener adapter | Publish event đầu qua `ApplicationEventPublisher` trong context thực |
| Dùng return event trong `@Async @EventListener` | Spring không hỗ trợ cơ chế đó | Inject publisher và publish event con thủ công |
| Tạo A → B → A không có điều kiện dừng | Có thể gây đệ quy vô hạn | Thiết kế trạng thái kết thúc, idempotency, không tạo cycle ẩn |
| Dùng `@Order` để đảm bảo transaction commit | Thứ tự listener không có nghĩa là kết cục transaction | Dùng transactional listener hoặc outbox |
| Assert ngay sau publish khi đã bật async | Async chưa chắc hoàn tất | Await bằng timeout và kiểm tra lỗi |
| Hiểu return event như một durable event log | Spring Application Events mặc định nằm trong bộ nhớ | Dùng hệ thống lưu/phát lại phù hợp nếu cần durability |

Checklist trước khi dùng giá trị trả về để tạo chuỗi:

1. Đã xác định **kiểu event mới** và có listener tương ứng chưa?
2. Method trả về `void`, `null`, một đối tượng, `Collection` hay mảng — kết quả đó có đúng số event mong muốn?
3. Listener có chạy đồng bộ không? Có `@Async` hoặc multicaster executor nào thay đổi ngữ nghĩa không?
4. Có nhánh lặp, listener chung kiểu dữ liệu, event trùng, hoặc phụ thuộc vòng tròn không?
5. Event mới có side effect bên ngoài database khi transaction chưa commit không?
6. Có integration test publish qua Spring context thật để xác nhận các event con được tạo không?

## 11. Câu hỏi tự kiểm tra

**Câu 1:** Method `@EventListener` trả về một `OrderValidated` thì điều gì xảy ra?

Khi method được Spring gọi như một listener đồng bộ, giá trị trả về được phát như một event `OrderValidated` mới. Nó không trở thành giá trị trả về của `ApplicationEventPublisher.publishEvent(...)`.

**Câu 2:** Trả `List.of(new A(), new B())` có tạo một event chứa danh sách không?

Không theo cơ chế return-value của `@EventListener`. Spring phát `A` và `B` như các event riêng. Muốn truyền nguyên danh sách như một payload, đóng gói nó trong một đối tượng event chuyên biệt.

**Câu 3:** Khi nào `null` hoặc `void` phù hợp?

Khi listener đã xử lý đầu vào nhưng không có yêu cầu phát event tiếp theo. `null` dừng nhánh return event; `void` thể hiện method không cung cấp kết quả event.

**Câu 4:** Vì sao `@Async @EventListener` không nên trả `NextEvent` để tạo chuỗi?

Vì Spring không hỗ trợ publish event tiếp theo từ return value của async listener. Muốn phát event mới khi xử lý async hoàn thành, hãy gọi `ApplicationEventPublisher.publishEvent(...)` tường minh.

**Câu 5:** Return event từ listener đồng bộ có đảm bảo DB commit trước khi listener con gửi email không?

Không. Nếu event đầu được publish trong transaction chưa commit, chain có thể chạy trước commit. Phải dùng transaction-phase semantics hoặc outbox tùy yêu cầu nghiệp vụ.

**Ghi nhớ:** `@EventListener` có thể trả **một event, Collection hoặc mảng để Spring phát các event tiếp theo**. Đây là tiện ích tạo chuỗi event trong ứng dụng, không phải cơ chế nhận kết quả của `publishEvent`, không phù hợp cho return-based async chaining và không bảo đảm event được lưu hoặc giao nhận bền vững.

## Tài liệu tham khảo

- [Spring Framework – ApplicationContext: Annotation-based Event Listeners, return values, asynchronous listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework – EventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework – ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
