# @RecordApplicationEvents và ApplicationEvents

## 1. Mục tiêu và phạm vi

Khi một Spring Boot service phát **application event**, điều cần kiểm thử không chỉ là “ApplicationEventPublisher.publishEvent(...) đã được gọi” mà còn là **event nào được công bố, payload có đúng các trường nghiệp vụ, có bao nhiêu event được phát ra trong một tình huống, có bị phát khi input không hợp lệ, và listener nào thực sự xử lý**. Trong nhóm **Sự kiện và observability**, Spring TestContext cung cấp **@RecordApplicationEvents** cùng **ApplicationEvents** để quan sát events **bên trong ApplicationContext trong vòng đời một test method**.

Bài học dùng **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter và spring-boot-starter-test**. Ví dụ gồm một PaymentService phát record payload **PaymentRecordedEvent**, một listener đồng bộ ghi dữ liệu quan sát vào in-memory projection, các **@SpringBootTest + @RecordApplicationEvents** integration tests và một nhóm Mockito unit tests không cần context. Chúng ta cũng phân biệt **event publication** với **async listener completion**, **@TransactionalEventListener AFTER_COMMIT**, các sự kiện do Spring TestContext phát ra, và giới hạn của event recorder khi test chạy qua thread/HTTP khác.

**Điểm mấu chốt:** **@RecordApplicationEvents chứng minh một application event đã được publish trong phạm vi mà TestContext recorder ghi nhận, không tự chứng minh broker nhận message, DB đã commit, listener async đã hoàn tất hay hệ thống có observability metrics/traces.** Đó là các hợp đồng khác phải kiểm thử riêng.

Các đoạn source đầy đủ bên dưới được thiết kế có thể biên dịch với Java 17 và Spring Boot 3.4.5. Không có kết quả Gradle thực thi thực tế được giả định trong quá trình biên soạn.

## 2. Tại sao dùng event trong Spring?

**ApplicationEventPublisher** cho phép một component công bố sự kiện tới các listeners trong cùng Spring ApplicationContext, giảm coupling trực tiếp giữa business service và các hành vi theo sau. Ví dụ:

~~~text
HTTP/controller hoặc command
       |
       v
 PaymentService.recordPayment(paymentId, amountMinor)
       |
       +--> validate input
       |
       +--> publisher.publishEvent(PaymentRecordedEvent)
                        |
                        v
           Spring ApplicationEventMulticaster
                        |
             +----------+-----------+
             |                      |
             v                      v
    PaymentAuditProjection    NotificationListener
      @EventListener          @EventListener/@Async
             |                      |
             v                      v
        in-memory view        notification action
~~~

Một **event record** thường mang dữ liệu thuộc về một business fact đã xảy ra. Bài demo dùng PaymentRecordedEvent(String paymentId, long amountMinor), không phải Kafka record hay JPA entity.

**Spring application event là cơ chế in-process.** Nếu JVM dừng hoặc service chạy thành nhiều replicas, event không tự được lưu durable hay gửi tới replica khác. Với reliable cross-service messaging, cần broker/outbox/integration test phù hợp; chỉ quan sát sự kiện Spring không tạo bảo đảm delivery.

### Event dạng ApplicationEvent subclass và dạng POJO payload

Spring có hai cách công bố phổ biến:

1. **Subclass ApplicationEvent:** tạo class kế thừa org.springframework.context.ApplicationEvent, có source và các fields. Khi stream() trả các ApplicationEvent objects, subclass đó là event object.
2. **POJO/record payload:** gọi publisher.publishEvent(new PaymentRecordedEvent(...)) với một Java record không kế thừa ApplicationEvent. Spring có thể **bọc payload bằng PayloadApplicationEvent** khi dispatch. **ApplicationEvents.stream(PaymentRecordedEvent.class)** giúp lấy lại payload đúng kiểu, thay vì ép raw ApplicationEvent sang Java record.

Trong bài, dùng **Java record payload** vì dễ biểu đạt domain data và không buộc business event phụ thuộc class ApplicationEvent. Trường hợp có custom ApplicationEvent subclass sẽ được minh họa ở phần sau.

### Publish không có nghĩa delivery đã hoàn thành

Mặc định, Spring event listeners được gọi **đồng bộ trên publishing thread** khi dùng multicaster mặc định không có async executor. Nhưng nếu @Async hoặc custom ApplicationEventMulticaster dùng TaskExecutor, listener có thể chạy thread khác. Và với **@TransactionalEventListener(phase=AFTER_COMMIT)**, listener được defer tới transaction commit, không chạy tại thời điểm publish.

Vì vậy test phải xác định nó đang kiểm **publication**, **listener invocation**, **side effect**, **commit**, hay **remote delivery**; không nhập những bằng chứng khác nhau thành một phép assert count.

## 3. @RecordApplicationEvents làm gì?

**org.springframework.test.context.event.RecordApplicationEvents** là annotation **đặt trên test class** (có thể dùng meta-annotation). Nó yêu cầu Spring TestContext Framework ghi nhận application events được publish trong ApplicationContext trong phạm vi một test method. Spring Framework cung cấp **ApplicationEventsTestExecutionListener**, mặc định đã đăng ký trong bộ TestExecutionListener của TestContext.

Dùng với JUnit Jupiter:

~~~java
@SpringBootTest
@RecordApplicationEvents
class PaymentEventsIntegrationTest {

    @Test
    void recordsPublishedPayment(
            ApplicationEvents events) {
        // events là recorder thuộc test method hiện tại.
    }
}
~~~

**Import chính xác:**

~~~java
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.event.ApplicationEvents;
~~~

Annotation **không phải** org.springframework.context.event.RecordApplicationEvents, cũng không phải Micrometer annotation. API này nằm trong **spring-test**, được kéo vào test scope qua **spring-boot-starter-test**.

**Phải có Spring TestContext/JUnit Jupiter SpringExtension.** @SpringBootTest và @SpringJUnitConfig cung cấp integration đó. Một JUnit test thuần MockitoExtension không tự tạo ApplicationEvents recorder chỉ vì bạn thêm @RecordApplicationEvents mà không có Spring context.

### Cách nhận ApplicationEvents

**Ưu tiên method parameter** trong @Test, @BeforeEach hoặc @AfterEach khi dùng SpringExtension:

~~~java
@Test
void example(ApplicationEvents events) {
    events.clear();
    // ...
}
~~~

Hoặc inject field:

~~~java
@Autowired
private ApplicationEvents events;
~~~

**Không inject ApplicationEvents vào constructor của test class.** Nó là dependency scoped theo **current test method lifecycle**, chưa sẵn sàng tại test constructor creation. Với JUnit Jupiter, parameter injection theo method là lựa chọn rõ ràng nhất.

**@RecordApplicationEvents không làm tự ghi một file log.** Nó cung cấp recorder trong memory để truy vấn và assert events trong test. Nó không thay thế application logs, Micrometer Observation, tracing hoặc audit log bền vững.

## 4. ApplicationEvents cung cấp những phương thức nào?

Trong Spring Framework 6.2, interface **ApplicationEvents** có ba phương thức chính:

| API | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| **stream()** | Stream các **ApplicationEvent** đã được ghi nhận trong test | Kiểm raw event wrapper/type hoặc inspect lifecycle events |
| **stream(Class<T> type)** | Stream các event hoặc **payloads** thuộc type yêu cầu | Phổ biến nhất cho domain record events |
| **clear()** | Xóa các events hiện có trong recorder này | Đặt baseline trước hành động đang kiểm thử |

**Không có API ApplicationEvents.count(), getEvents(), size() hay await()** trong interface chính của Spring Framework 6.2. Muốn đếm:

~~~java
long count = events.stream(PaymentRecordedEvent.class).count();
~~~

Muốn lấy payload cụ thể:

~~~java
List<PaymentRecordedEvent> payments =
    events.stream(PaymentRecordedEvent.class).toList();
~~~

Muốn lọc theo identity:

~~~java
List<PaymentRecordedEvent> matching =
    events.stream(PaymentRecordedEvent.class)
        .filter(event -> event.paymentId().equals(paymentId))
        .toList();
~~~

**Lưu ý:** stream(Class<T>) lọc **cả event instances và event payloads** đúng type. Khi công bố Java record không kế thừa ApplicationEvent, nó vẫn được tìm thấy qua **stream(PaymentRecordedEvent.class)**. Với raw **stream()**, recorder cung cấp Stream<ApplicationEvent>, nên POJO payload thường xuất hiện thông qua **PayloadApplicationEvent**.

### clear() không hủy event đã được xử lý

**events.clear() chỉ xóa danh sách quan sát được của test recorder.** Nó:
- Không gọi undo trên business action;
- Không xóa in-memory listener projection;
- Không rollback database transaction;
- Không cancel @Async tasks hoặc event delivery;
- Không xóa Spring context cache;
- Không ngăn những event mới xuất hiện ngay sau đó.

Khi test cần đếm chính xác events do **một business action**, có thể gọi events.clear() **ngay đầu test method, trước action**. Không chỉ tin rằng raw stream ban đầu hoàn toàn rỗng: Spring TestContext có thể công bố lifecycle events trong các giai đoạn before-test, và @RecordApplicationEvents có thể ghi nhận những events đó.

## 5. Các mức bằng chứng trong event tests

| Câu hỏi | Kiểm thử phù hợp | Điều chưa chứng minh |
| --- | --- | --- |
| Service có quyết định publish đúng payload? | Mockito unit test ApplicationEventPublisher | Spring context/event multicaster |
| Event đã được published trong test Spring context? | @RecordApplicationEvents + ApplicationEvents.stream(Type) | Listener async xong hay DB commit |
| Listener đồng bộ có thực thi side effect? | @SpringBootTest + assert listener's observable state | Reliability nếu JVM crash |
| @EventListener được đăng ký và nhận đúng payload? | Spring context integration | Broker delivery |
| Listener AFTER_COMMIT có chạy sau commit? | Transaction integration với commit thực | Chạy được khi rollback hoặc no transaction |
| Listener @Async đã xong? | Await trạng thái/completion với bounded timeout | Event recorder tự chờ task |
| Kafka/RabbitMQ đã nhận event? | Broker integration + consumer assertions | Chỉ có Spring ApplicationEvents |
| Business audit durable? | Database/outbox/transaction integration | In-memory projection test |
| Metrics/trace của event? | Micrometer ObservationRegistry/trace assertions | ApplicationEvents không phải ObservationRegistry |
| Cross-node event propagation? | Distributed/broker integration | ApplicationEventPublisher chỉ local JVM |

Một test xanh chỉ chứng minh những assertions mà test đã quan sát thực sự. Nếu requirement nói “gửi hóa đơn tới queue sau khi DB commit”, chỉ stream(OrderPaidEvent).count() == 1 là chưa đủ; phải kiểm transaction/outbox/producer ack hoặc consumer behavior ở cấp thích hợp.

## 6. Dự án runnable Java 17 / Spring Boot 3.4.5

Dự án chọn domain nhỏ: **ghi nhận một khoản thanh toán** và phát **PaymentRecordedEvent**. Một listener đồng bộ cập nhật in-memory audit projection. Không dùng DB, Kafka hoặc HTTP vì chủ đề chính là **ApplicationEvents recorder**.

### 6.1. Cây file

~~~text
settings.gradle
build.gradle
src/main/java/com/example/eventqa/EventQaApplication.java
src/main/java/com/example/eventqa/PaymentRecordedEvent.java
src/main/java/com/example/eventqa/PaymentService.java
src/main/java/com/example/eventqa/PaymentAuditProjection.java
src/test/java/com/example/eventqa/PaymentServiceUnitTest.java
src/test/java/com/example/eventqa/PaymentEventsIntegrationTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'spring-application-events-testing'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter** mang Spring core/context, lifecycle và logging. **spring-boot-starter-test** có spring-test, JUnit Jupiter, Mockito và các test helpers. Không cần spring-boot-starter-web nếu không mở HTTP controller. Không thêm Kafka/Testcontainers chỉ để đếm một Spring application event.

Để sử dụng **./gradlew** cần có Gradle Wrapper scripts trong project; nếu chưa tạo, dùng Gradle cài sẵn hoặc tạo Wrapper trước. Code files được trình bày đầy đủ; không mặc nhiên tuyên bố Gradle Wrapper đã tồn tại.

### 6.4. EventQaApplication.java

**src/main/java/com/example/eventqa/EventQaApplication.java**

~~~java
package com.example.eventqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EventQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(EventQaApplication.class, args);
    }
}
~~~

Application class nằm trong cùng root package, để component scanning tìm PaymentService và PaymentAuditProjection. @SpringBootTest có thể xác định @SpringBootConfiguration từ class này. Không có embedded web server vì project không dùng starter-web.

### 6.5. PaymentRecordedEvent.java

**src/main/java/com/example/eventqa/PaymentRecordedEvent.java**

~~~java
package com.example.eventqa;

public record PaymentRecordedEvent(
        String paymentId,
        long amountMinor) {
}
~~~

Java record này **không extends ApplicationEvent**. Spring sẽ publish nó như một **payload event**. Vì vậy **events.stream(PaymentRecordedEvent.class)** là cách thích hợp để lấy payload trong tests; còn **events.stream()** duyệt Spring ApplicationEvent wrappers.

**paymentId** cho phép lọc đúng sự kiện cần kiểm tra ngay cả khi có nhiều events cùng loại trong một context. **amountMinor** là giá trị số nguyên theo đơn vị nhỏ nhất đã được định nghĩa bởi hợp đồng ứng dụng, không dùng double để biểu diễn tiền.

### 6.6. PaymentService.java

**src/main/java/com/example/eventqa/PaymentService.java**

~~~java
package com.example.eventqa;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ApplicationEventPublisher publisher;

    public PaymentService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void recordPayment(String paymentId, long amountMinor) {
        if (paymentId == null || paymentId.isBlank()) {
            throw new IllegalArgumentException(
                    "paymentId must not be blank");
        }
        if (amountMinor <= 0) {
            throw new IllegalArgumentException(
                    "amountMinor must be positive");
        }

        publisher.publishEvent(
                new PaymentRecordedEvent(paymentId, amountMinor));
    }
}
~~~

**Trách nhiệm service:** validate input rồi publish event. Không có transaction, persistence hoặc deduplication trong ví dụ. **Hai lời gọi với cùng paymentId tạo hai lần publication**; đó không phải lỗi của ApplicationEvents mà là giới hạn rõ của business implementation.

**Nếu listener đồng bộ throw exception, publishEvent có thể ném lỗi về caller** tùy multicaster/error handler. Nếu listener async, publisher có thể return trước khi listener xử lý và exception async không tự propagate tới call stack này.

### 6.7. PaymentAuditProjection.java

**src/main/java/com/example/eventqa/PaymentAuditProjection.java**

~~~java
package com.example.eventqa;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentAuditProjection {

    private final ConcurrentHashMap<String, PaymentRecordedEvent> items =
            new ConcurrentHashMap<>();

    @EventListener
    public void onPaymentRecorded(PaymentRecordedEvent event) {
        items.put(event.paymentId(), event);
    }

    public Optional<PaymentRecordedEvent> find(String paymentId) {
        return Optional.ofNullable(items.get(paymentId));
    }
}
~~~

Đây là listener **đồng bộ mặc định**, chưa gắn @Async và không có custom multicaster. Khi PaymentService.publishEvent trở về bình thường, listener đã được gọi theo mặc định, nên test có thể inspect projection ngay sau publication.

**Projection này không durable.** Nó lưu last event theo paymentId trong ConcurrentHashMap. Nếu cùng paymentId được publish hai lần, map vẫn có một key nhưng **ApplicationEvents recorder có thể ghi hai occurrences**. Đừng coi số rows trong projection là số events đã được publish.

Giá trị paymentId trong mỗi integration test được sinh riêng (UUID), tránh phụ thuộc data từ method trước dù Spring TestContext cache ApplicationContext/bean state.

## 7. Unit test không cần Spring context: Mockito publisher

**src/test/java/com/example/eventqa/PaymentServiceUnitTest.java**

~~~java
package com.example.eventqa;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class PaymentServiceUnitTest {

    @Mock
    private ApplicationEventPublisher publisher;

    private PaymentService service;

    @BeforeEach
    void setUp() {
        service = new PaymentService(publisher);
    }

    @Test
    void validPaymentPublishesExactPayload() {
        service.recordPayment("pay-101", 2500L);

        ArgumentCaptor<PaymentRecordedEvent> captor =
                ArgumentCaptor.forClass(PaymentRecordedEvent.class);

        verify(publisher).publishEvent(captor.capture());

        PaymentRecordedEvent event = captor.getValue();
        assertEquals("pay-101", event.paymentId());
        assertEquals(2500L, event.amountMinor());
    }

    @Test
    void invalidInputPublishesNothing() {
        assertThrows(IllegalArgumentException.class,
                () -> service.recordPayment(" ", 2500L));

        assertThrows(IllegalArgumentException.class,
                () -> service.recordPayment("pay-102", 0L));

        verifyNoInteractions(publisher);
    }

    @Test
    void synchronousPublisherFailurePropagates() {
        IllegalStateException cause =
                new IllegalStateException("listener rejected event");

        doThrow(cause).when(publisher)
                .publishEvent(any(PaymentRecordedEvent.class));

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                () -> service.recordPayment("pay-103", 2500L));

        assertSame(cause, actual);
    }
}
~~~

**Chứng minh được:** valid input phát một Java record với đúng paymentId/amountMinor; invalid input không gọi publisher; lỗi khi publishEvent trả về qua mock được propagate thay vì bị service nuốt.

**Chưa chứng minh:** Spring thực sự dispatch tới @EventListener, PayloadApplicationEvent wrapper được tạo, recorder hoạt động hay listener side effect thành công. Vì test không chạy Spring context, nó chỉ bảo vệ business decision/boundary.

**Mockito overload lưu ý:** ApplicationEventPublisher có publishEvent(ApplicationEvent) và publishEvent(Object); **PaymentRecordedEvent là record POJO**, nên lời gọi compile-time chọn overload Object. ArgumentCaptor<PaymentRecordedEvent> và any(PaymentRecordedEvent.class) giúp Mockito bắt đúng overload trong tests.

## 8. Integration test thật với @RecordApplicationEvents

**src/test/java/com/example/eventqa/PaymentEventsIntegrationTest.java**

~~~java
package com.example.eventqa;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@RecordApplicationEvents
class PaymentEventsIntegrationTest {

    @Autowired
    private PaymentService service;

    @Autowired
    private PaymentAuditProjection audit;

    @Test
    void recordsSingleEventWithExactPayload(
            ApplicationEvents events) {

        // Loại những framework/startup events đã ghi trước action.
        events.clear();

        String id = "pay-" + UUID.randomUUID();
        service.recordPayment(id, 4000L);

        List<PaymentRecordedEvent> recorded =
                events.stream(PaymentRecordedEvent.class)
                    .filter(event -> event.paymentId().equals(id))
                    .toList();

        assertEquals(1, recorded.size());
        assertEquals(id, recorded.get(0).paymentId());
        assertEquals(4000L, recorded.get(0).amountMinor());

        // @EventListener đồng bộ đã cập nhật projection.
        PaymentRecordedEvent projected =
                audit.find(id).orElseThrow();
        assertEquals(4000L, projected.amountMinor());
    }

    @Test
    void invalidCommandProducesNoPaymentEvent(
            ApplicationEvents events) {

        events.clear();

        org.junit.jupiter.api.Assertions.assertThrows(
            IllegalArgumentException.class,
            () -> service.recordPayment(" ", -1L));

        assertEquals(0L,
            events.stream(PaymentRecordedEvent.class).count());
    }

    @Test
    void streamByPayloadTypeUnwrapsPojoEvent(
            ApplicationEvents events) {

        events.clear();

        String id = "pay-" + UUID.randomUUID();
        service.recordPayment(id, 10L);

        // Typed API trả Java record payload.
        assertEquals(1L,
            events.stream(PaymentRecordedEvent.class)
                .filter(event -> event.paymentId().equals(id))
                .count());

        // Raw API trả ApplicationEvent wrapper.
        assertEquals(1L,
            events.stream()
                .filter(event ->
                    event instanceof PayloadApplicationEvent<?> payload
                    && payload.getPayload()
                        instanceof PaymentRecordedEvent payment
                    && payment.paymentId().equals(id))
                .count());
    }

    @Test
    void recorderClearDoesNotUndoListenerSideEffect(
            ApplicationEvents events) {

        events.clear();

        String id = "pay-" + UUID.randomUUID();
        service.recordPayment(id, 50L);

        assertEquals(1L,
            events.stream(PaymentRecordedEvent.class)
                .filter(event -> event.paymentId().equals(id))
                .count());

        events.clear();

        // Recorder trống, nhưng listener state vẫn còn.
        assertEquals(0L,
            events.stream(PaymentRecordedEvent.class).count());
        assertTrue(audit.find(id).isPresent());
    }

    @Test
    void twoPublicationsAppearAsTwoOccurrences(
            ApplicationEvents events) {

        events.clear();

        String id = "pay-" + UUID.randomUUID();

        service.recordPayment(id, 100L);
        service.recordPayment(id, 100L);

        assertEquals(2L,
            events.stream(PaymentRecordedEvent.class)
                .filter(event -> event.paymentId().equals(id))
                .count());

        // Projection map chỉ giữ giá trị mới nhất cho key.
        assertTrue(audit.find(id).isPresent());
    }

    @Test
    void typedStreamCanFilterDifferentBusinessIds(
            ApplicationEvents events) {

        events.clear();

        String first = "pay-" + UUID.randomUUID();
        String second = "pay-" + UUID.randomUUID();

        service.recordPayment(first, 1000L);
        service.recordPayment(second, 2000L);

        List<PaymentRecordedEvent> result =
                events.stream(PaymentRecordedEvent.class)
                    .filter(event -> event.paymentId().equals(second))
                    .toList();

        assertEquals(1, result.size());
        assertEquals(2000L, result.get(0).amountMinor());
    }
}
~~~

### Đọc chính xác các assertions

**recordsSingleEventWithExactPayload:** events.stream(PaymentRecordedEvent.class) trả đúng một event cho paymentId đang test. Assert fields, không chỉ assert count. Sau đó inspect listener projection để chứng minh **@EventListener đồng bộ** đã thực hiện side effect.

**invalidCommandProducesNoPaymentEvent:** service validation ném exception trước publish. Assert **0 domain events đúng type**. Không assert stream() có 0 raw events vì Spring TestContext có thể phát lifecycle events khác loại.

**streamByPayloadTypeUnwrapsPojoEvent:** chứng minh typed stream trả record payload; raw stream() bao gồm **PayloadApplicationEvent**. Không ép cast Java record từ stream() nếu chưa unwrap.

**recorderClearDoesNotUndoListenerSideEffect:** clear() chỉ xóa recorder, còn audit map vẫn có entry; đây là ranh giới rõ giữa **quan sát publication** và **thay đổi state**.

**twoPublicationsAppearAsTwoOccurrences:** nếu service publish hai lần cùng paymentId, recorder đếm 2. Không suy từ Map projection chỉ có 1 key rằng business đã chống duplicate event. Trong production cần idempotent processing nếu requirement yêu cầu.

**typedStreamCanFilterDifferentBusinessIds:** cùng một context có thể có nhiều events; filter theo type và identity giúp test chính xác, không lấy vị trí phần tử thứ N trong raw global events.

### Vì sao gọi events.clear() ở đầu mỗi test method?

Recorder ghi events theo lifecycle test; TestContext có thể phát lifecycle events như BeforeTestMethodEvent/BeforeTestExecutionEvent hoặc component khác publish events trước business action. **events.clear() thiết lập baseline trong chính test method**, sát thời điểm action cần quan sát. Khi muốn kiểm một setup event, đừng clear event đó trước assertion; thay vào đó lọc theo type/correlation ID.

**Test methods độc lập:** mỗi method tự tạo UUID, không dùng @TestMethodOrder, không dựa vào audit projection đang chứa data từ test trước. Context có thể được Spring cache và projection là singleton, nhưng tests không đếm toàn bộ map và không dùng keys cố định nên không phụ thuộc thứ tự.

## 9. Event loại subclass ApplicationEvent

Khi event kế thừa ApplicationEvent, không cần PayloadApplicationEvent wrapper để biểu diễn payload. Ví dụ **minh họa độc lập, không nằm trong runnable tree**:

~~~java
public final class PaymentSettledEvent
        extends org.springframework.context.ApplicationEvent {

    private final String paymentId;

    public PaymentSettledEvent(
            Object source, String paymentId) {
        super(source);
        this.paymentId = paymentId;
    }

    public String getPaymentId() {
        return paymentId;
    }
}
~~~

Tại một Spring-managed component:

~~~java
publisher.publishEvent(
    new PaymentSettledEvent(this, "pay-200"));
~~~

Test có thể dùng:

~~~java
assertEquals(1L,
    events.stream(PaymentSettledEvent.class)
        .filter(event -> event.getPaymentId().equals("pay-200"))
        .count());
~~~

Đây là các **trích đoạn minh họa**, chưa có imports/class test hoàn chỉnh và không cần thêm vào dự án chính. Chúng giúp phân biệt hai kiểu:

| Event dạng | Object gửi publishEvent | Kết quả typed stream | Raw stream |
| --- | --- | --- | --- |
| Java record/POJO | new PaymentRecordedEvent(...) | PaymentRecordedEvent payload | Thường có PayloadApplicationEvent |
| ApplicationEvent subclass | new PaymentSettledEvent(source,...) | PaymentSettledEvent instance | ApplicationEvent subclass |
| Framework lifecycle event | ApplicationReadyEvent hoặc TestContext event | Event type tương ứng | ApplicationEvent subclass |

**Không nhầm PayloadApplicationEvent với business event type.** Khi dùng stream(PaymentRecordedEvent.class), Spring Test API đã cho truy cập payload đúng type, giúp code test sạch hơn.

## 10. @RecordApplicationEvents ghi nhận trong phạm vi nào?

Theo TestContext Framework, recorder là **test-method scoped** và gắn với thread-local/inheritable context cho test. Mục tiêu là events do **test thread hoặc các descendant threads** phát trong vòng đời test.

Điều đó có các hệ quả quan trọng:

1. **Bắt buộc có @RecordApplicationEvents trên class/meta-annotation** để TestContext kích hoạt recording.
2. **Phải có ApplicationEventsTestExecutionListener.** Nó được đăng ký mặc định; một @TestExecutionListeners custom với replace defaults có thể vô tình loại bỏ listener này.
3. **Event được publish trước khi recorder bắt đầu** (ví dụ nhiều application startup events khi context được cache/khởi tạo trước test) không nên coi là chắc chắn xuất hiện.
4. **Event được publish sau khi test kết thúc** không nằm trong lifecycle để assert theo recorder của method đó.
5. **Thread pool có sẵn** và servlet container threads không nhất thiết là descendants của test thread, nên events publish tại đó **có thể không được ghi đúng vào recorder test**.
6. **Parallel tests chia sẻ ApplicationContext** có thể quan sát events từ test khác trong một số kịch bản; tránh đếm global events và chia sẻ mutable state.
7. **@TestInstance(PER_CLASS) kết hợp @RecordApplicationEvents và chạy test methods parallel** không được hỗ trợ trong các phiên bản Spring TestContext; nên dùng default PER_METHOD, @Execution(SAME_THREAD) khi cần hoặc tắt parallel execution.

**Không dùng ApplicationEvents như một global event bus hook để giám sát mọi thread của ứng dụng chạy thực.** Nó là tiện ích kiểm thử scoped. Nếu integration test phát request HTTP tới **RANDOM_PORT** server thread, event có thể nằm ngoài scope recorder; thay vào đó assert state bền vững, dùng test listener/queue đồng bộ thread-safe hoặc test message broker có tín hiệu hoàn tất.

### @TestExecutionListeners custom

Mặc định TestContext đăng ký ApplicationEventsTestExecutionListener. Nếu test class khai báo listener custom nhưng vô tình thay toàn bộ mặc định, recorder có thể không hoạt động. Giữ defaults bằng merge mode khi phù hợp:

~~~java
@TestExecutionListeners(
    listeners = CustomListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
~~~

Đây là **trích đoạn**, cần class CustomListener có thật và imports; không nằm trong runnable sample. Một lựa chọn khác là đăng ký các listeners cần thiết tường minh, nhưng merge defaults thường ít sai sót hơn. Tránh xóa các TestExecutionListeners khác chỉ vì muốn thêm logging.

## 11. @BeforeEach, @AfterEach, field injection và constructor scope

Trong JUnit Jupiter + SpringExtension, có thể inject ApplicationEvents vào methods:

~~~java
@BeforeEach
void before(ApplicationEvents events) {
    events.clear();
}

@Test
void test(ApplicationEvents events) {
    // Gọi service rồi assert stream(...)
}

@AfterEach
void after(ApplicationEvents events) {
    // Có thể inspect recorded events ở cuối lifecycle.
}
~~~

**Lưu ý timing:** nếu @BeforeEach clear recorder, các event do Spring TestContext phát sau @BeforeEach (ví dụ before-test-execution) vẫn có thể vào raw stream. Vì vậy với requirement đếm raw events do đúng một action, gọi **events.clear() ngay trước action trong @Test method** hoặc lọc theo business event type/identity.

Field injection cũng được hỗ trợ:

~~~java
@Autowired
private ApplicationEvents recordedEvents;
~~~

Nhưng **test constructor parameter ApplicationEvents không được bảo đảm** vì recorder chỉ active trong current test method lifecycle. Method parameter injection khiến tính scoped trở nên rõ hơn, tránh việc giữ tham chiếu dài hạn khi @TestInstance(PER_CLASS) hoặc nested/parallel tests.

**@AfterEach** có thể xác nhận events được publish trong test, nhưng không nên giả định một listener async đã hoàn tất trước @AfterEach. Cần tín hiệu completion/timeout hoặc durable state riêng để kiểm chứng asynchronous behavior.

## 12. @EventListener đồng bộ và listener bất đồng bộ

Mặc định, Spring ApplicationEventMulticaster gọi listeners **đồng bộ** trong publishing thread. Trong project mẫu, PaymentAuditProjection.onPaymentRecorded chạy trước khi PaymentService.recordPayment(...) trả về (nếu không có multicaster async custom).

Vì vậy sau:

~~~java
service.recordPayment(id, 4000L);
assertEquals(1L,
    events.stream(PaymentRecordedEvent.class)
        .filter(e -> e.paymentId().equals(id))
        .count());
assertTrue(audit.find(id).isPresent());
~~~

hai assertions là các bằng chứng khác nhau:
- recorder có event: **publication**;
- audit map có entry: **listener đã thực hiện side effect đồng bộ**.

### Nếu listener có @Async

Một listener:

~~~java
@Async
@EventListener
public void sendNotification(PaymentRecordedEvent event) {
    // External notification hoặc CPU work.
}
~~~

là **trích đoạn minh họa**, cần @EnableAsync/TaskExecutor và implementation thực để chạy. @Async làm công việc trên executor thread, nên:
- publishEvent có thể return trước khi listener hoàn thành;
- exception trong async listener không tự propagate về publisher thread;
- event recorder không phải latch/await utility;
- test cần quan sát **observable completion** bằng CompletableFuture, CountDownLatch, Awaitility hoặc trạng thái durable với bounded timeout;
- khi executor thread tái sử dụng không phải descendant thực của test thread, scoped ApplicationEvents recorder có thể không nhìn thấy event được publish tiếp bên trong async listener;
- MDC/trace context không tự truyền qua arbitrary thread boundaries; dùng context propagation phù hợp nếu observability là yêu cầu.

**Không dùng Thread.sleep(300) rồi assert count**: test dễ flaky theo tải máy. Nếu cần test listener async, dùng test-controlled executor, bounded wait và assertion tại downstream side effect. Đặt recorder test riêng cho publication ở caller thread.

### Async multicaster khác @Async listener

Một **SimpleApplicationEventMulticaster** được cấu hình TaskExecutor có thể dispatch nhiều listeners bất đồng bộ. @Async trên method là cơ chế khác. Nếu project tự cấu hình multicaster global, thậm chí listener thường cũng có thể chạy trên thread khác; đừng mặc định assertion audit map ngay lập tức luôn hợp lệ. Cần biết scheduler/executor thực của app trước khi viết test.

## 13. @TransactionalEventListener: event đã publish nhưng commit chưa xảy ra

**@TransactionalEventListener** mặc định chạy ở phase **AFTER_COMMIT** khi event được publish trong transaction đang hoạt động. Nó khác @EventListener thông thường.

~~~java
@Component
class ReceiptSender {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    public void afterPaymentCommitted(
            PaymentRecordedEvent event) {
        // Gọi một service/send adapter phù hợp.
    }
}
~~~

Đây là **trích đoạn kiến trúc**, không thuộc runnable project vì demo không tạo transaction manager hay database. Cần imports org.springframework.transaction.event.TransactionalEventListener và org.springframework.transaction.event.TransactionPhase.

**Điểm quan trọng:**
- **events.stream(PaymentRecordedEvent.class)** có thể đã thấy event ngay khi service gọi publishEvent **trước commit**.
- **@TransactionalEventListener(AFTER_COMMIT)** chỉ xử lý sau khi transaction thực sự commit thành công, không chạy khi rollback.
- Nếu publish **không có active transaction**, listener mặc định **không chạy** trừ khi đặt **fallbackExecution=true**.
- **@TransactionalEventListener(BEFORE_COMMIT)**, **AFTER_ROLLBACK**, **AFTER_COMPLETION** có semantics khác, cần test riêng khi dùng.
- Với reactive transaction, transaction context ở Reactor Context chứ không mặc định là ThreadLocal; trong Spring Framework 6.1+ dùng cách publish/propagate transaction context phù hợp, không áp dụng mù quáng kiến thức thread-bound.
- Sau AFTER_COMMIT/AFTER_COMPLETION, transactional resources có thể còn accessible nhưng commit đã hoàn tất; nếu listener cần ghi DB mới, thường cần **REQUIRES_NEW** hoặc cơ chế outbox/transaction riêng đúng contract.

### Cạm bẫy @Transactional trên test

Spring TestContext mặc định **rollback test-managed transaction** của một test @Transactional sau khi method hoàn thành. Nếu bạn publish event trong transaction đó và assertion chạy **trước rollback**, recorder vẫn có thể thấy event, nhưng **AFTER_COMMIT listener sẽ không chạy**. Không lấy stream count=1 làm bằng chứng sau-commit notification đã gửi.

Muốn test AFTER_COMMIT:
1. Dùng database và transaction manager thật hoặc test-specific fixture.
2. Thực hiện business operation **trong transaction có commit thực**, ví dụ TransactionTemplate.executeWithoutResult, kết thúc transaction trước khi assert listener side effect.
3. Bảo đảm test không được bao ngoài bởi một @Transactional test transaction đang rollback; nếu không, TransactionTemplate mặc định có thể tham gia outer transaction mà vẫn chưa commit.
4. Assert side effect của listener, không chỉ ApplicationEvents stream.
5. Dọn dữ liệu durable theo test-only DB, không trỏ vào shared production database.

Một sketch có chủ đích:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    paymentService.recordPayment(id, 1000L);
});

// Khi transaction đã commit, kiểm tra listener AFTER_COMMIT.
assertTrue(receiptStore.existsForPayment(id));
~~~

Đây **không phải standalone runnable code**: cần TransactionTemplate/transaction manager, receiptStore và database schema riêng. Nó minh họa **vị trí commit trước assertion**; main project phía trên không có transaction nên không giả làm một test AFTER_COMMIT đã chạy.

### Publication khác persistence và durable messaging

ApplicationEventPublisher phát trong cùng JVM; transaction-bound listener giúp gắn hành vi với commit nhưng **không bảo đảm exactly-once message gửi tới Kafka/email nếu process crash ngay sau DB commit**. Nếu cần DB + external event consistency, cân nhắc **transactional outbox** và idempotent consumer. Test recorder chỉ là một lớp bằng chứng về publication, không thay thế outbox/broker integration test.

## 14. Framework lifecycle events và vì sao không đếm raw stream bừa bãi

Trong một Spring Boot application context/test lifecycle có nhiều loại events không phải business events, ví dụ:
- ContextRefreshedEvent, ContextClosedEvent;
- Spring Boot ApplicationStartedEvent, ApplicationReadyEvent (tùy phase/context lifecycle);
- Spring TestContext test execution events như BeforeTestMethodEvent, BeforeTestExecutionEvent, AfterTestExecutionEvent, AfterTestMethodEvent;
- Events của các components khác trong application.

**Không mặc định events.stream().count() == 1** chỉ vì service publish một PaymentRecordedEvent. Có thể recorder chứa nhiều events không liên quan cùng test; thậm chí timing của chúng khác nhau.

Tốt hơn:

~~~java
long count = events.stream(PaymentRecordedEvent.class)
    .filter(event -> event.paymentId().equals(id))
    .count();

assertEquals(1L, count);
~~~

Đếm **đúng loại và identity** thay vì raw global list. Nếu muốn kiểm xem một context refresh event xuất hiện, phải hiểu recorder được kích hoạt ở thời điểm nào; startup events có thể xảy ra trước current test method scope, vì vậy TestContext recorder không phải cơ chế đáng tin để bắt **mọi** application-startup event.

**Event recording per method** khác việc Spring TestContext cache ApplicationContext. Context singleton có thể còn sống giữa các tests; recorder được tạo/scoped theo test method, nhưng listener state không tự reset. Đó là lý do project dùng UUID trong business event và không assert tổng kích thước projection map.

## 15. ApplicationEvents và observability: liên hệ nhưng không đồng nghĩa

Một ứng dụng có thể cần:
- **Application events**: những business facts/technical signals được publish in-process.
- **Audit log**: bản ghi bền vững về ai làm gì, khi nào, không thể dễ xóa, có retention.
- **Micrometer Observation**: thời lượng, spans, metrics/traces và context propagation.
- **Structured logging**: correlation IDs, requestId, paymentId, severity và error reason.
- **Message broker**: durable/remote event transport, ack, retry, DLT.
- **Domain event store/outbox**: transactionally persisted intent/events để recover sau crash.

**@RecordApplicationEvents chỉ quan sát Spring events**. Nó không tự sinh counter, span, trace ID hay audit record. Nếu có yêu cầu “metrics tăng một sau payment”, test với **MeterRegistry/ObservationRegistry** phù hợp; nếu yêu cầu “event PaymentRecordedEvent được publish với amountMinor đúng”, dùng ApplicationEvents. Nếu yêu cầu “email đã gửi sau commit”, test listener side effect/external adapter ở mức khác.

### Tránh lộ dữ liệu nhạy cảm qua application event

Events có thể chứa payment IDs, email, user IDs hoặc dữ liệu nhạy cảm. Không gắn toàn bộ password/token/card-number vào event payload hay tự log event.toString() trên production. Test fixtures nên dùng IDs giả, không sao chép dữ liệu khách hàng thật. Khi publish sang observability/telemetry, cân nhắc cardinality và redaction phù hợp.

## 16. Tình huống publish event nhiều lần, duplicate và thứ tự

Giả sử service gọi:

~~~java
publisher.publishEvent(
    new PaymentRecordedEvent("pay-A", 100L));
publisher.publishEvent(
    new PaymentRecordedEvent("pay-B", 200L));
~~~

Trong cùng publishing thread, nếu multicaster đồng bộ và không có listeners publish thêm events, recorder có thể thấy thứ tự A rồi B. Nhưng **không dùng thứ tự global của raw ApplicationEvents stream làm business invariant** khi:
- listener publish nested events;
- dùng custom async multicaster;
- nhiều threads/HTTP requests cùng publish;
- parallel tests chia sẻ context;
- @TransactionalEventListener trì hoãn xử lý tới phase khác;
- events khác được Spring/TestContext phát xen giữa.

Nên assert đúng **số lượng theo type/paymentId** và fields, hoặc viết integration test ordering theo contract thực khi ordering là yêu cầu.

**Duplicate business effect:** Nếu cùng paymentId được publish hai lần, recorder đếm hai events. Trong bài, audit projection dùng map và chỉ giữ bản ghi cuối cùng; điều đó **không** chứng minh consumer idempotent ngoài đời. Để có semantics “exactly one business action”, cần unique constraints/transaction/outbox và test các tình huống retry/concurrency.

### Event publication trong rollback

Ngay cả nếu sự kiện có ý nghĩa “PaymentConfirmed”, publish trong một transaction sau đó rollback vẫn có thể để recorder thấy event dù payment không commit. Nếu event thật sự phải phản ánh thành công durable, cân nhắc publish ở đúng boundary, @TransactionalEventListener hoặc outbox. Đặt tên event có trách nhiệm; không tạo sai lệch giữa application events và actual database truth.

## 17. Chọn lớp test theo mục đích

| Test intent | Công cụ | Ví dụ assertion |
| --- | --- | --- |
| Logic quyết định phát event | Mockito ApplicationEventPublisher | verify publishEvent exact event |
| DTO payload đúng | Mockito captor hoặc ApplicationEvents typed stream | paymentId/amountMinor |
| Spring dispatch thực sự có event | @SpringBootTest + @RecordApplicationEvents | typed stream count |
| Listener đồng bộ được gọi | Spring context + state của listener | audit.find(id) present |
| No event on invalid input | Unit + integration test | verifyNoInteractions / count0 |
| Raw POJO event wrapper | ApplicationEvents.stream() | PayloadApplicationEvent type |
| Recorder clear scope | ApplicationEvents.clear() | stream empty nhưng projection không đổi |
| @TransactionalEventListener AFTER_COMMIT | TransactionTemplate + commit thật | downstream side effect sau commit |
| Async event handling | Completion signal/await | side effect eventually, timeout |
| HTTP-triggered event qua real server thread | RANDOM_PORT integration + shared state/queue | response + side effect, không dựa recorder |
| Kafka downstream publication | EmbeddedKafka/Testcontainers/real broker | consumer nhận record |
| Observability metrics/traces | MeterRegistry/ObservationRegistry | counter/timer/span assertions |

**Không bật full @SpringBootTest cho pure domain logic chỉ cần biết một lời gọi publisher**. Nhưng **không mock toàn bộ ApplicationEventPublisher khi mục tiêu là Spring dispatch/registration**, vì như vậy sẽ bỏ qua ApplicationContext behavior cần kiểm.

## 18. @SpringJUnitConfig và context nhỏ thay @SpringBootTest khi phù hợp

Spring Boot full context hữu ích để chứng minh component scanning và auto-configuration. Nếu chỉ muốn test Spring event bus với vài beans, có thể dùng **@SpringJUnitConfig** và @Import/context classes cụ thể:

~~~java
@SpringJUnitConfig(classes = {
    PaymentService.class,
    PaymentAuditProjection.class
})
@RecordApplicationEvents
class MinimalEventContextExample {

    @Autowired
    PaymentService service;

    @Test
    void records(ApplicationEvents events) {
        events.clear();
        service.recordPayment("pay-min", 100L);
        assertEquals(1L,
            events.stream(PaymentRecordedEvent.class).count());
    }
}
~~~

Đây là **trích đoạn minh họa**, chưa khai imports vào một file runnable của project, nhưng các classes PaymentService/PaymentAuditProjection đã có trong source tree. SpringJUnitConfig kết hợp SpringExtension với context configuration. Nó có thể dùng để tránh kéo full Boot context nếu muốn kiểm event multicaster và listener registration đơn giản.

**Không ép phải dùng Spring Boot test runner để kiểm mọi event.** Cân nhắc chi phí context và evidence cần có. Nếu muốn chứng minh auto-configuration/context integration thực, @SpringBootTest vẫn có giá trị riêng.

## 19. Kiểm thử nested events và listener trả về event

Spring @EventListener có thể dùng return value để publish một event mới trong synchronous processing theo cơ chế framework. Tuy nhiên listener async không thể dựa vào return value này để publish follow-up event theo cùng semantics; cần inject ApplicationEventPublisher tường minh.

Một listener đồng bộ mẫu có thể biến PaymentRecordedEvent thành PaymentAuditedEvent, làm recorder ghi **hai business event types**: PaymentRecordedEvent và PaymentAuditedEvent. Khi test, không assert raw stream count1; cần assert count1 cho từng type với matching paymentId.

**Đừng tạo vòng lặp vô hạn:** listener nhận type A rồi publish A nữa không có stop condition có thể gây recursion/stack overflow. Type-specific event contracts giúp test không vô tình nhận events không liên quan.

Nếu listener ghi event qua async executor, việc theo dõi follow-up events bằng test-scoped recorder có thể không đáng tin vì thread boundary. Assert một side effect bền vững hoặc dùng test-controlled event collector có synchronization rõ.

## 20. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không inject được ApplicationEvents | Thiếu @RecordApplicationEvents/SpringExtension hoặc listener mặc định bị thay | Annotate test class, giữ TestContext listeners |
| ApplicationEvents trong test constructor bị unavailable | Test-method scope chưa active | Dùng @Test/@BeforeEach parameter hoặc @Autowired field |
| stream(PaymentRecordedEvent.class) trả 0 | Publisher mock, sai ApplicationContext, event khác thread, action không publish | Kiểm context/thread/real publisher |
| stream() trả PayloadApplicationEvent chứ không phải record | POJO được wrapped | Dùng typed stream hoặc getPayload() |
| Test count toàn stream nhiều hơn 1 | Có framework/test lifecycle events | Filter theo type/paymentId, clear trước action |
| events.clear() rồi audit vẫn có record | clear chỉ xóa recorder | Kiểm side effect riêng |
| @TransactionalEventListener không chạy | Test rollback hoặc publish không có transaction | Test commit thật, fallback policy |
| Event recorded nhưng email chưa gửi | Listener async hoặc after-commit | Await downstream completion/commit, không coi publish là delivery |
| MockMvc thấy event nhưng RANDOM_PORT recorder không thấy | Server thread không thuộc recorder scope | Assert state/queue bằng HTTP integration |
| @Async listener lỗi nhưng publishEvent không ném | Async exception không propagate | AsyncUncaughtExceptionHandler/completion monitoring |
| Raw event ordering test flaky | Concurrent publishers/listeners | Filter identity, test ordering ở đúng tầng |
| Test parallel PER_CLASS bị lỗi/không tin cậy | @RecordApplicationEvents per-method ThreadLocal scope | PER_METHOD/SAME_THREAD hoặc disable parallel |
| @DirtiesContext được thêm để “xóa recorder” | Đánh đồng context cache với test recorder | ApplicationEvents.clear() và unique IDs |
| @TestExecutionListeners custom làm mất defaults | Replace không merge | MERGE_WITH_DEFAULTS |
| Test mong startup event nhưng không thấy | Recorder bắt đầu theo test method lifecycle | Test startup events qua listener/instrumentation riêng |
| assert count1 rồi tuyên bố Kafka đã deliver | Spring event không phải broker | Broker integration |
| assert event count1 rồi tuyên bố DB committed | Publication trước commit/rollback | Transaction integration |
| Listener projection dùng static mutable list giữa tests | State rò/test order dependency | Unique IDs, fresh fixtures hoặc scoped cleanup |
| ApplicationEvents bị gọi ngoài test lifecycle | Recorder không còn active | Chỉ dùng trong test/lifecycle methods |
| Event chứa secrets khiến logs lộ dữ liệu | Payload không được redacted | Chỉ dùng IDs/metadata phù hợp |
| Unit test mock publisher nhưng bảo đảm listener wiring | Mock bypass Spring multicaster | Thêm @RecordApplicationEvents context test |

## 21. Chạy thử và expected results

Với JDK 17 và Gradle Wrapper tương thích:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.eventqa.PaymentServiceUnitTest
./gradlew test --tests com.example.eventqa.PaymentEventsIntegrationTest
./gradlew test --tests com.example.eventqa.PaymentEventsIntegrationTest.recordsSingleEventWithExactPayload
~~~

Trên Windows dùng **gradlew.bat** với arguments tương ứng. Main app có thể start không cần server/database; demo không tạo payments lúc startup.

Các kết quả sau là **kỳ vọng từ assertions**, không phải actual test run log:

| Test | Kết quả cần quan sát |
| --- | --- |
| validPaymentPublishesExactPayload | Captor: pay-101, amountMinor=2500 |
| invalidInputPublishesNothing | IllegalArgumentException, publisher zero interactions |
| synchronousPublisherFailurePropagates | Exception gốc không bị nuốt |
| recordsSingleEventWithExactPayload | 1 PaymentRecordedEvent cho UUID, audit projection chứa amount=4000 |
| invalidCommandProducesNoPaymentEvent | 0 PaymentRecordedEvent |
| streamByPayloadTypeUnwrapsPojoEvent | Typed stream 1 record; raw stream có 1 PayloadApplicationEvent phù hợp |
| recorderClearDoesNotUndoListenerSideEffect | Recorder count=0 sau clear; audit vẫn có payment |
| twoPublicationsAppearAsTwoOccurrences | 2 recorded events cùng ID |
| typedStreamCanFilterDifferentBusinessIds | Event second được lọc ra, amount=2000 |

### Cần quan sát gì nếu một test thất bại?

- **UnsatisfiedDependencyException khi inject ApplicationEvents**: test có @RecordApplicationEvents và TestContext listener mặc định hay không? Có cố inject vào constructor không?
- **Recorded count=0 nhưng unit captor pass**: bạn có đang dùng real publisher trong Spring context, hay @MockitoBean đã thay? Event có publish từ thread của test không?
- **Payload class bị cast fail**: raw stream chứa ApplicationEvent wrapper, dùng stream(PayloadType.class) hoặc unwrap.
- **Listener projection không cập nhật ngay**: listener có @Async/custom multicaster hoặc event transaction-bound không? Có đang chạy trong rollback transaction?
- **Lúc pass lúc fail khi tests chạy parallel**: kiểm JUnit lifecycle mode, static state, context cache, executor threads và test identity.
- **Event count tăng do setup/framework events**: clear sát action và filter type/ID; không assert total raw stream length một cách ngây thơ.

## 22. Checklist QA trước khi chốt

- Test class có **@RecordApplicationEvents** và SpringExtension/@SpringBootTest?
- Có dùng **ApplicationEvents** đúng package org.springframework.test.context.event?
- Test nhận ApplicationEvents bằng method parameter/field, không constructor injection?
- Có phân biệt **stream()** với **stream(MyPayload.class)**?
- Với POJO/record event, có hiểu **PayloadApplicationEvent** wrapper?
- Assertions kiểm **payload fields** và correlation ID, không chỉ count?
- Input invalid có test **không phát event**?
- events.clear() có được đặt **trước action** khi cần baseline rõ?
- Không dùng clear() như một phương thức rollback hoặc xóa listener state?
- Có phân biệt Spring TestContext lifecycle events với business events?
- Test records per method và không dựa vào dữ liệu method trước?
- Có tránh @TestInstance(PER_CLASS) chạy parallel với @RecordApplicationEvents?
- Có tránh đếm raw stream global trong shared context parallel tests?
- Listener đồng bộ/async có được xác định trước khi assert side effect?
- Với @Async/custom multicaster, có bounded wait và thread-safe observable state?
- Với @TransactionalEventListener, đã kiểm **commit thật** và transaction phase?
- Test @Transactional rollback có bị nhầm thành AFTER_COMMIT listener success?
- Với HTTP RANDOM_PORT, không mặc nhiên tin recorder thấy events từ server thread?
- Có hiểu event publication **không** tự chứng minh Kafka delivery, durable audit hay exactly-once?
- Có tách Spring events khỏi Micrometer Observation/metrics/tracing?
- Nếu custom @TestExecutionListeners, có giữ ApplicationEventsTestExecutionListener?
- Có kiểm context wiring riêng với pure Mockito publisher unit test?
- Test payload không chứa thông tin nhạy cảm, credentials hoặc dữ liệu khách hàng thật?
- Các source code files và imports thuộc Spring Boot 3.4/Spring Framework 6.2?
- Không bịa BUILD SUCCESSFUL, offset hoặc log từ runtime chưa thực thi?

## 23. Câu hỏi tự kiểm tra

**1.** @RecordApplicationEvents đặt trên đâu? **Test class** hoặc meta-annotation, không phải annotation business service.

**2.** ApplicationEvents dùng làm gì? **Truy vấn các Spring application events được ghi nhận trong test method lifecycle**.

**3.** ApplicationEvents có count() riêng không? **Không**; dùng events.stream(Type.class).count().

**4.** events.clear() có xóa data trong listener projection không? **Không**, chỉ xóa recorder buffer.

**5.** Java record không extends ApplicationEvent có publish được không? **Có**, qua publishEvent(Object).

**6.** Vì sao raw stream có PayloadApplicationEvent? Spring bọc POJO payload để dispatch như ApplicationEvent.

**7.** Cách lấy PaymentRecordedEvent trực tiếp? **events.stream(PaymentRecordedEvent.class)**.

**8.** Tại sao unit Mockito test chưa chứng minh listener wiring? Publisher đã được mock, Spring multicaster không chạy.

**9.** Tại sao context test cần @RecordApplicationEvents? Để TestContext tạo recorder scoped cho test.

**10.** ApplicationEvents có nên inject vào constructor test không? **Không**, ưu tiên @Test/@BeforeEach/@AfterEach method parameter.

**11.** @EventListener mặc định chạy thread nào? Thường **publishing thread** với multicaster đồng bộ mặc định.

**12.** @Async listener có làm publisher chờ đến khi xong không? **Không mặc định**.

**13.** Có nên dùng Thread.sleep để đợi @Async listener? **Không**, dùng observable completion và bounded wait.

**14.** @TransactionalEventListener mặc định phase nào? **AFTER_COMMIT**.

**15.** Event đã ghi nhận nhưng transaction rollback, AFTER_COMMIT listener có chạy không? **Không**, dù recorder có thể có event.

**16.** Publish ngoài transaction, listener transaction-bound mặc định có chạy không? **Không**, trừ fallbackExecution=true.

**17.** Vì sao test @Transactional mặc định dễ hiểu nhầm AFTER_COMMIT? Vì test thường rollback sau method, không commit.

**18.** Spring event có tự đi tới Kafka broker không? **Không**, nó là cơ chế in-process.

**19.** @RecordApplicationEvents có tự tạo metrics/trace không? **Không**, dùng Micrometer/Observation tools riêng.

**20.** Vì sao không assert events.stream().count()==1? Có framework events và nhiều event types khác.

**21.** Test phát event qua RANDOM_PORT server thread có được recorder luôn bắt không? **Không bảo đảm**, vì thread/lifecycle scope.

**22.** @TestInstance(PER_CLASS) với parallel @RecordApplicationEvents có an toàn không? **Không nên/kết hợp này không được hỗ trợ**, dùng PER_METHOD/SAME_THREAD.

**23.** Khi custom @TestExecutionListeners làm mất default recorder listener, sửa thế nào? **MERGE_WITH_DEFAULTS** hoặc đăng ký chính xác listener cần thiết.

**24.** Một event được ghi nhận hai lần cùng paymentId có tự cho biết duplicate là bug không? **Không**, phải xác định business idempotency contract; recorder chỉ phản ánh publication occurrences.

**25.** Khi cần chứng minh notification sau commit đã gửi, nên assert gì? **Commit thật và listener downstream side effect**, không chỉ ApplicationEvents stream.

**Kết luận:** **@RecordApplicationEvents + ApplicationEvents** là công cụ Spring TestContext chuyên để quan sát và assert các application events được publish trong một test method. Dùng typed stream để đếm/lọc đúng domain event payload; dùng clear() để cô lập action; kết hợp Mockito unit test và Spring context test để phân biệt business decision với event dispatch; kiểm listener side effect riêng khi cần. Quan trọng nhất là không coi **event đã được ghi nhận** đồng nghĩa **async listener đã xong**, **transaction đã commit**, **broker đã nhận message** hoặc **observability đã hoàn chỉnh**.

## Nguồn tham khảo chính thức

- Spring Framework 6.2 — Application Events trong TestContext: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html
- Spring Framework 6.2 — @RecordApplicationEvents: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html
- Spring Framework 6.2 — ApplicationEvents Javadoc (stream/stream(Class)/clear): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html
- Spring Framework 6.2 — RecordApplicationEvents Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html
- Spring Framework 6.2 — ApplicationContext events and @EventListener: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — Observability support: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
