# Mock ApplicationEventPublisher trong kiểm thử Spring Application Events

## 1. Vì sao cần mock ApplicationEventPublisher?

Trong ứng dụng Spring, một use case có thể lưu trạng thái rồi phát sự kiện nghiệp vụ để các thành phần khác phản ứng:

~~~text
PlaceOrder command
        |
        v
   OrderService
       |             +---------------------+
       +-- save ---->| OrderRepository     |
       |             +---------------------+
       |
       +-- publish --> OrderPlaced
                           |
                           +--> AuditListener
                           +--> EmailListener
                           +--> SearchProjectionListener
~~~

Khi kiểm thử riêng `OrderService`, mục tiêu thường là xác nhận:

- Với input hợp lệ, service gọi lưu đúng dữ liệu.
- Service phát **đúng loại sự kiện** và **đúng payload**.
- Thứ tự giữa lưu và publish đúng với hợp đồng ở tầng application service.
- Với input không hợp lệ hoặc lỗi lưu trực tiếp, service **không phát sự kiện thành công**.
- Không phát thừa hoặc phát nhiều lần ngoài ý muốn.

Ta **không cần khởi tạo ApplicationContext thật** để xác nhận các lời gọi đó. Thay vào đó, truyền một `ApplicationEventPublisher` giả được tạo bằng Mockito vào constructor của service, gọi method cần kiểm thử, rồi dùng `verify(...)` và `ArgumentCaptor`.

**Giới hạn rất quan trọng:** mock chứng minh **lời gọi đến publisher**, không chứng minh Spring multicaster đã dispatch event, listener đã chạy, transaction đã commit hay công việc đã được giao bền vững. Những yêu cầu đó cần integration test hoặc contract test tương ứng.

Bài học này thuộc nhóm **Kiểm thử event** của Spring Framework Application Events. Trọng tâm là mock `ApplicationEventPublisher` bằng Mockito đúng cách, không phải giới thiệu Mockito chung chung.

## 2. ApplicationEventPublisher là ranh giới phù hợp cho unit test

`ApplicationEventPublisher` là interface do Spring cung cấp để công bố event. Hai overload quan trọng:

~~~java
void publishEvent(Object event);
void publishEvent(ApplicationEvent event); // default overload
~~~

Spring Framework cho phép publish một object thường, bao gồm Java `record`, từ Spring 4.2. Với object không kế thừa `ApplicationEvent`, implementation của context có thể bọc payload bằng `PayloadApplicationEvent` để xử lý nội bộ. Vì vậy domain event **không bắt buộc** phải extends `ApplicationEvent`.

Một service dễ kiểm thử nên nhận publisher qua **constructor injection**:

~~~java
public final class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = repository;
        this.publisher = publisher;
    }
}
~~~

Đoạn trên chỉ minh họa thành phần của class; tệp đầy đủ sẽ có ở phần 5. Do dependency được đưa từ bên ngoài vào, unit test có thể tạo object bằng `new OrderService(mockRepository, mockPublisher)`. Spring container, bean scanning, multicaster, database thật và listener thật **không cần được khởi động**.

Điều này giữ test nhanh, phạm vi nhỏ và cho lỗi dễ hiểu. Test không kiểm tra API framework; nó kiểm tra việc application code của chúng ta sử dụng API đúng ý định.

### 2.1. Nên kiểm tra hợp đồng nào?

| Hợp đồng của use case | Unit test với Mockito kiểm tra được? |
| --- | --- |
| Đã gọi `publisher.publishEvent(...)` một lần | Có |
| Event có đúng order ID, số tiền, thông tin cần thiết | Có |
| Không publish nếu input sai | Có |
| Repository được gọi trước publisher | Có, bằng `InOrder` |
| Exception từ repository làm không publish | Có, khi mô phỏng lỗi gọi repository |
| Listener `@EventListener` thực tế nhận được event | **Không** với publisher mock |
| Event đã được xử lý ở `AFTER_COMMIT` | **Không** |
| Database transaction đã commit | **Không** |
| Event đi qua executor async đúng cách | **Không** |
| Event đã được ghi bền vững vào outbox/broker | **Không** |

Không đánh giá chất lượng một test dựa trên số lượng lời gọi `verify`. Điều quan trọng là test bảo vệ **hợp đồng có giá trị nghiệp vụ** và tránh khóa chặt những chi tiết triển khai có thể thay đổi mà không làm thay đổi kết quả mong muốn.

## 3. Chiến lược thiết kế test: Arrange, Act, Assert

Một test mock publisher thường gồm:

1. **Arrange:** tạo mock `OrderRepository` và `ApplicationEventPublisher`.
2. **Act:** gọi method nghiệp vụ trên `OrderService`.
3. **Assert:** kiểm tra trạng thái/lời gọi repository và event được publish đúng.

Ví dụ ý tưởng:

~~~java
OrderRepository repository = mock(OrderRepository.class);
ApplicationEventPublisher publisher =
    mock(ApplicationEventPublisher.class);

OrderService service = new OrderService(repository, publisher);
service.place(101L, 12000L);

verify(publisher).publishEvent(new OrderPlaced(101L, 12000L));
~~~

Đây là **mã minh họa bên trong một test method**. Phải có import Mockito và các type `OrderService`, `OrderRepository`, `OrderPlaced`. Phần 5 có dự án Java 17+ đầy đủ với Maven và test chạy được.

Mockito ghi nhận invocation của interface. Bởi `OrderPlaced` là Java `record`, `equals/hashCode` dựa trên các component được tự tạo, nên `verify(publisher).publishEvent(new OrderPlaced(...))` có thể so sánh nội dung một cách dễ hiểu.

Nếu event là object mutable không có `equals` phù hợp, việc so sánh trực tiếp bằng một instance mới có thể thất bại dù các field đúng. Khi đó dùng `ArgumentCaptor` hoặc matcher cho đúng trường, nhưng về thiết kế nên ưu tiên payload event bất biến.

## 4. Vì sao không mock cả Spring context trong unit test?

Có nhiều cách đưa event vào code: inject `ApplicationEventPublisher`, inject `ApplicationContext` hoặc gọi một service phát event được bọc riêng. Với unit test của một service thuần, inject interface hẹp `ApplicationEventPublisher` thường tốt hơn inject `ApplicationContext` rộng với rất nhiều chức năng không liên quan.

### Không cần mở context để kiểm tra một lời gọi

Nếu test chỉ cần xác nhận `publishEvent`, việc khởi tạo `AnnotationConfigApplicationContext` hoặc `@SpringJUnitConfig` làm test phụ thuộc vào bean scanning, cấu hình, lifecycle, proxy và listener không thuộc phạm vi test.

Mẫu dùng trực tiếp mock:

~~~text
JUnit test
   |
   +-- Mockito.mock(OrderRepository.class)
   +-- Mockito.mock(ApplicationEventPublisher.class)
   |
   +-- new OrderService(repository, publisher)
   |
   +-- service.place(...)
   |
   +-- verify(...) / capture(...)
~~~

**Lợi ích:** nhanh, chạy độc lập, lỗi rõ và không cần `@SpringBootTest`. Nhưng khi muốn kiểm tra **sự kiện có thực sự được Spring dispatch**, hãy dùng integration test với context thật (phần 7).

### Vì sao không thay publisher của cả context bằng mock?

Trong Spring integration test, nếu thay thế `ApplicationEventPublisher` thành một Mockito mock, lời gọi đến mock không tự đi qua multicaster. Điều này có thể khiến test “publish đã gọi” vẫn PASS dù listener hoàn toàn không chạy. Ngoài ra, việc thay các bean lõi của Spring có thể làm thay đổi hành vi context/lifecycle.

Khi test tích hợp cần chứng minh listener chạy, **giữ publisher thật** và ghi nhận event bằng `@RecordApplicationEvents`/`ApplicationEvents` hoặc spy listener/đo outcome. Tránh mock publisher khi điều bạn muốn kiểm chứng là chính cơ chế dispatch.

## 5. Dự án Java 17+ chạy được: unit test bằng Mockito

Dự án sau không cần Spring Boot. Nó sử dụng:

- Spring Framework 6.2.8 cho `ApplicationEventPublisher` và `@EventListener`.
- JUnit Jupiter 5.11.4 để viết test.
- Mockito 5.15.2 để tạo mock, `verify`, `InOrder`, `ArgumentCaptor`.
- Spring Test 6.2.8 để chạy một integration test với event recorder.
- Maven Surefire 3.5.2 để chạy JUnit 5 bằng lệnh `mvn test`.

### 5.1. Cấu trúc thư mục

~~~text
event-publisher-testing/
├── pom.xml
└── src
    ├── main
    │   └── java/example/events
    │       ├── Order.java
    │       ├── OrderPlaced.java
    │       ├── OrderRepository.java
    │       └── OrderService.java
    └── test
        └── java/example/events
            ├── OrderServiceTest.java
            └── RecordingIntegrationTest.java
~~~

Mỗi lớp public nằm trong một file trùng tên với `package example.events`. Hai lớp test có trách nhiệm **khác nhau**: `OrderServiceTest` kiểm tra publisher mock, `RecordingIntegrationTest` kiểm tra dispatch Spring thật.

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-publisher-testing</artifactId>
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
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>5.15.2</version>
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
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. Domain object: Order.java

~~~java
package example.events;

public record Order(long id, long totalCents) { }
~~~

Trong ví dụ, `Order` lưu ID và tổng tiền dạng số nguyên cents. Đây là mô hình đơn giản dành cho test, không phải mẫu thiết kế tài chính đầy đủ (chưa có currency, decimal rounding, state transition…).

### 5.4. Event payload: OrderPlaced.java

~~~java
package example.events;

public record OrderPlaced(long orderId, long totalCents) { }
~~~

`OrderPlaced` là một **fact** được publish sau khi repository chấp nhận lời gọi lưu. Là record, nó có `equals` theo giá trị, rất thuận tiện cho Mockito assertion. Nó **không extends ApplicationEvent**, nên khi phát qua publisher sẽ chọn overload `publishEvent(Object)`.

### 5.5. Repository port: OrderRepository.java

~~~java
package example.events;

public interface OrderRepository {
    void save(Order order);
}
~~~

Đây là port của ứng dụng, không phụ thuộc database. Trong unit test, Mockito mock interface này; trong integration test về dispatch, dùng một implementation in-memory tối giản.

### 5.6. Use case: OrderService.java

~~~java
package example.events;

import java.util.Objects;
import org.springframework.context.ApplicationEventPublisher;

public final class OrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = Objects.requireNonNull(repository);
        this.publisher = Objects.requireNonNull(publisher);
    }

    public void place(long id, long totalCents) {
        if (id <= 0 || totalCents <= 0) {
            throw new IllegalArgumentException(
                "Order id and total must be positive"
            );
        }

        Order order = new Order(id, totalCents);
        repository.save(order);

        // Java record không extends ApplicationEvent, nên chọn
        // overload publishEvent(Object).
        publisher.publishEvent(
            new OrderPlaced(order.id(), order.totalCents())
        );
    }
}
~~~

Luồng này chủ động gọi `repository.save` trước `publishEvent`. Khi `save` ném exception, lệnh publish không được thực thi. **Nhưng** khi repository thực tế được bọc trong một transaction, lời gọi `save` không bảo đảm transaction đã commit tại đúng thời điểm publish. Phần transaction sẽ được phân tích ở mục 9.

## 6. Unit test đầy đủ: verify, ArgumentCaptor, InOrder và negative cases

Tệp `src/test/java/example/events/OrderServiceTest.java`:

~~~java
package example.events;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class OrderServiceTest {

    // Mỗi test method có một instance lớp test mới theo mặc định JUnit.
    private final OrderRepository repository =
        mock(OrderRepository.class);

    private final ApplicationEventPublisher publisher =
        mock(ApplicationEventPublisher.class);

    private final OrderService service =
        new OrderService(repository, publisher);

    @Test
    void validOrderPublishesExactlyOneCorrectEventAfterSave() {
        service.place(101L, 12_000L);

        InOrder calls = inOrder(repository, publisher);
        calls.verify(repository).save(new Order(101L, 12_000L));

        // Dùng Object captor để kiểm tra đúng overload POJO.
        ArgumentCaptor<Object> eventCaptor =
            ArgumentCaptor.forClass(Object.class);

        calls.verify(publisher).publishEvent(
            eventCaptor.capture()
        );
        calls.verifyNoMoreInteractions();

        OrderPlaced event = assertInstanceOf(
            OrderPlaced.class, eventCaptor.getValue()
        );

        assertEquals(101L, event.orderId());
        assertEquals(12_000L, event.totalCents());
    }

    @Test
    void invalidOrderDoesNotSaveOrPublish() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.place(-1L, 12_000L)
        );
        assertThrows(
            IllegalArgumentException.class,
            () -> service.place(101L, 0L)
        );

        verifyNoInteractions(repository, publisher);
    }

    @Test
    void repositoryFailurePreventsPublishing() {
        doThrow(new IllegalStateException("storage down"))
            .when(repository).save(any(Order.class));

        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.place(101L, 12_000L)
        );

        assertEquals("storage down", error.getMessage());
        verify(repository).save(new Order(101L, 12_000L));
        verifyNoInteractions(publisher);
    }
}
~~~

### 6.1. Test thứ nhất chứng minh điều gì?

- `service.place(...)` thực hiện nhánh thành công.
- `InOrder` kiểm tra lời gọi `repository.save(new Order(...))` đã xảy ra **trước** `publisher.publishEvent(...)`.
- `ArgumentCaptor<Object>` bắt object được truyền cho publisher.
- `assertInstanceOf(OrderPlaced.class, ...)` xác nhận loại event.
- Hai `assertEquals` xác nhận ID và số tiền chính xác.
- `calls.verifyNoMoreInteractions()` bảo đảm không có tương tác ngoài hai lời gọi đã kiểm tra, bao gồm không publish lần thứ hai.

Mockito không chạy listener thật; nó chỉ thu các invocation.

### 6.2. Test thứ hai chứng minh điều gì?

Hai input không hợp lệ bị chặn trước khi gọi repository và publisher. `verifyNoInteractions(repository, publisher)` bảo đảm không có side effect qua hai dependency được mock.

Đây là test quan trọng đối với event ở dạng quá khứ như `OrderPlaced`: command bị từ chối **không được công bố sự thật “đã đặt đơn”**.

### 6.3. Test thứ ba chứng minh điều gì?

Mockito cấu hình `repository.save(...)` ném `IllegalStateException`. Vì use case thực hiện save trước publish, exception làm phương thức dừng ngay và `publisher.publishEvent(...)` không được gọi.

**Không suy diễn quá mức:** test này mô phỏng **save ném lỗi ngay khi gọi**; nó không mô phỏng một transaction manager báo lỗi **ở thời điểm commit sau khi method trả về**. Nếu commit thất bại về sau, use case có thể đã gọi publisher trước đó. Cần test transaction thật và policy after-commit/outbox nếu nghiệp vụ yêu cầu.

## 7. Integration test: dùng publisher thật và @RecordApplicationEvents

Một unit test mock publisher có thể PASS ngay cả khi hệ thống thực tế không đăng ký listener, cấu hình sai `@EventListener` hoặc event type không khớp. Khi muốn xác nhận **Spring dispatch thật**, sử dụng Spring TestContext thay vì mock publisher.

Spring Framework cung cấp:

- `@SpringJUnitConfig`: kết hợp JUnit Jupiter extension với cấu hình Spring context.
- `@RecordApplicationEvents`: bật ghi nhận các application event trong phạm vi từng test.
- `ApplicationEvents`: đọc các event đã được publish và lọc theo kiểu qua `events.stream(OrderPlaced.class)`.

### 7.1. Tệp RecordingIntegrationTest.java

Tệp `src/test/java/example/events/RecordingIntegrationTest.java`:

~~~java
package example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(RecordingIntegrationTest.Config.class)
@RecordApplicationEvents
class RecordingIntegrationTest {

    public static class CapturingListener {
        private final List<OrderPlaced> received =
            new CopyOnWriteArrayList<>();

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            received.add(event);
        }

        public List<OrderPlaced> received() {
            return List.copyOf(received);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        OrderRepository orderRepository() {
            // Chỉ mô phỏng save để test dispatch, không có DB.
            return order -> { };
        }

        @Bean
        OrderService orderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher
        ) {
            return new OrderService(repository, publisher);
        }

        @Bean
        CapturingListener capturingListener() {
            return new CapturingListener();
        }
    }

    @Test
    void realSpringContextRecordsAndDispatchesEvent(
            @Autowired OrderService service,
            @Autowired CapturingListener listener,
            ApplicationEvents events
    ) {
        service.place(202L, 34_000L);

        assertEquals(
            1L,
            events.stream(OrderPlaced.class).count()
        );
        assertEquals(
            List.of(new OrderPlaced(202L, 34_000L)),
            listener.received()
        );
    }
}
~~~

### 7.2. Vì sao cần cả hai assertion?

- `events.stream(OrderPlaced.class).count()` chứng minh event kiểu `OrderPlaced` đã được publish và được Spring TestContext ghi nhận trong phạm vi test.
- `listener.received()` chứng minh một listener `@EventListener` thực sự được Spring đăng ký **và đã xử lý event** trong cấu hình dispatch đồng bộ của ví dụ.

Nếu chỉ kiểm tra `ApplicationEvents`, test chưa chứng minh một listener cụ thể đã nhận. Nếu chỉ kiểm tra listener, ta chưa khai thác được API ghi nhận event toàn cục. Hai assertion bổ trợ nhau.

**Lưu ý:** `@RecordApplicationEvents` ghi event trong phạm vi test method và `ApplicationEvents` được truy cập tại lifecycle test tương ứng. Nó không phải một event store production; việc lọc theo `OrderPlaced.class` tránh đếm nhầm các context event khác của framework.

### 7.3. Chạy toàn bộ dự án

Từ thư mục `event-publisher-testing`:

~~~bash
mvn test
~~~

Với các tệp như trên và môi trường có JDK 17+, Maven cùng dependency được tải thành công, kỳ vọng **ba unit test và một integration test** đều PASS. Maven Surefire ghi kết quả trong `target/surefire-reports`.

~~~text
OrderServiceTest:
  validOrderPublishesExactlyOneCorrectEventAfterSave     PASS
  invalidOrderDoesNotSaveOrPublish                      PASS
  repositoryFailurePreventsPublishing                   PASS

RecordingIntegrationTest:
  realSpringContextRecordsAndDispatchesEvent            PASS

Tổng: 4 tests, 0 failures, 0 errors
~~~

Khối trên là **bảng kết quả kỳ vọng do tài liệu diễn giải**, không phải chuỗi stdout nguyên văn của Maven. Đầu ra Maven có thể khác theo phiên bản plugin và môi trường. Nếu test fail, cần xem stacktrace/Surefire report; đừng sửa assertion để làm test xanh khi hợp đồng đang sai.

## 8. Một bẫy Java quan trọng: publishEvent có overload

`ApplicationEventPublisher` có overload nhận `ApplicationEvent` và overload nhận `Object`. Loại Java **tĩnh** của đối số quyết định overload được compiler chọn.

Với Java record:

~~~java
public record OrderPlaced(long id) { }

publisher.publishEvent(new OrderPlaced(42L));
~~~

Record không kế thừa `ApplicationEvent`, nên compiler chọn `publishEvent(Object)`. Mockito verification tương ứng:

~~~java
verify(publisher).publishEvent(
    new OrderPlaced(42L)
);
~~~

Nhưng nếu bạn định nghĩa sự kiện kiểu kế thừa `ApplicationEvent`:

~~~java
public final class OrderPlacedEvent extends ApplicationEvent {
    public OrderPlacedEvent(Object source) {
        super(source);
    }
}
~~~

Thì lời gọi:

~~~java
publisher.publishEvent(new OrderPlacedEvent(this));
~~~

thường chọn **overload nhận ApplicationEvent** ở compile time. Trong Mockito mock thuần, đừng mặc định `verify(publisher).publishEvent(any(Object.class))` sẽ kiểm tra mọi overload theo đúng cách. Có thể cần:

~~~java
verify(publisher).publishEvent(
    any(ApplicationEvent.class)
);
~~~

Các đoạn này **chỉ minh họa**, cần import Mockito/Spring và class context phù hợp. Nếu phát theo `(Object) event`, compiler lại chọn overload Object. Khi test fail vì “Wanted but not invoked”, kiểm tra overload trước khi kết luận service không hề publish.

**Lưu ý về default method:** trên một implementation thực, overload `publishEvent(ApplicationEvent)` có thể ủy quyền qua `publishEvent(Object)`; trên Mockito mock, hành vi mặc định không nhất thiết được thực thi như một implementation thật. Test invocation theo **hợp đồng mà application code gọi**, không suy từ đường delegation của implementation.

### 8.1. Khi nào dùng ArgumentCaptor<Object>?

`ArgumentCaptor<Object>` là lựa chọn an toàn khi service phát POJO event và ta muốn phân tích kiểu runtime. Ví dụ:

~~~java
ArgumentCaptor<Object> captor =
    ArgumentCaptor.forClass(Object.class);

verify(publisher).publishEvent(captor.capture());

OrderPlaced event =
    assertInstanceOf(OrderPlaced.class, captor.getValue());
assertEquals(42L, event.orderId());
~~~

Nếu có nhiều publish trong cùng method, dùng `captor.getAllValues()` và `verify(publisher, times(n))` theo hợp đồng. Đừng chỉ lấy `getValue()` (thường cho lần capture cuối) rồi quên rằng có thể đã phát thêm event khác.

## 9. Kiểm tra thứ tự và số lần publish

### 9.1. Verify đúng một lần

Theo mặc định, `verify(mock).method(...)` yêu cầu invocation khớp đã xảy ra **một lần**. Có thể viết tường minh:

~~~java
verify(publisher, times(1)).publishEvent(
    new OrderPlaced(101L, 12_000L)
);
~~~

Đây là mảnh test, cần static import Mockito `verify` và `times`. Nếu policy cho phép nhiều event khác, không nên dùng `verifyNoMoreInteractions(publisher)` quá rộng; hãy xác định rõ event nào và số lần nào có ý nghĩa.

### 9.2. Không publish khi command bị từ chối

~~~java
verifyNoInteractions(publisher);
~~~

Đây là assertion mạnh: publisher **không có bất kỳ interaction nào**. Trong unit test cô lập chỉ có service cần kiểm tra, nó có ý nghĩa. Nhưng nếu cùng mock được chia sẻ qua các setup hoặc lời gọi khác, assert này có thể fail vì tương tác không thuộc đường xử lý đang xét.

Một kiểm tra hẹp hơn:

~~~java
verify(publisher, never()).publishEvent(
    any(OrderPlaced.class)
);
~~~

Khi event là POJO `OrderPlaced`, expression `any(OrderPlaced.class)` chọn overload Object, đúng cho kiểu event trong ví dụ. Với một loại event kế thừa `ApplicationEvent`, cần xem lại overload.

### 9.3. Test thứ tự bằng InOrder

~~~java
InOrder order = inOrder(repository, publisher);
order.verify(repository).save(expectedOrder);
order.verify(publisher).publishEvent(expectedEvent);
~~~

Thứ tự này có ích nếu thiết kế yêu cầu **không công bố sự kiện trước khi save được gọi**. Tuy nhiên, nó không chứng minh sự kiện chỉ xuất hiện **sau DB commit**. Đó là hai hợp đồng khác nhau.

### 9.4. Test không bị brittle

Không nên verify mọi lời gọi nội bộ nếu logic nghiệp vụ chỉ quan tâm một fact đầu ra. Ví dụ refactor repository thành hai helper vẫn có thể giữ hợp đồng publish đúng. Mockito test quá chi tiết sẽ làm việc refactor tốn kém.

Gợi ý kiểm thử đúng mức: với test của application service, ưu tiên ba điều **“đúng event, đúng payload, không phát khi thất bại”**. Chỉ kiểm tra `InOrder` khi trình tự thật sự là một bất biến của use case.

## 10. Mock publisher không tự kiểm tra transaction và rollback

Một use case thực tế có thể dùng:

~~~java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = domainService.place(command);
    repository.save(order);
    publisher.publishEvent(new OrderPlaced(order.getId()));
}
~~~

Đây là **mã phác thảo**, không thuộc dự án Maven demo, vì cần `PlaceOrder`, domain service, repository, các import và transaction manager cụ thể.

Trong transaction thường, `publishEvent(...)` được gọi **trước thời điểm commit cuối cùng**. Nếu transaction rollback sau đó, một listener đồng bộ đã có thể nhận event. Mockito verify vẫn PASS vì nó kiểm tra invocation; nó **không biết** transaction có commit không.

### 10.1. Khi listener chỉ chạy sau commit

Spring hỗ trợ:

~~~java
@Component
public class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        notificationService.notify(event);
    }
}
~~~

Đoạn này là minh họa, cần import `Component`, `TransactionalEventListener`, `TransactionPhase` và các bean/type tương ứng.

`AFTER_COMMIT` giúp listener chạy khi transaction gắn với event commit thành công; nếu transaction rollback, listener phase này không chạy. Nếu publish ngoài transaction, mặc định `@TransactionalEventListener` không được thực thi (trừ khi cấu hình `fallbackExecution=true`). Các hành vi này **không được chứng minh** bằng publisher mock.

Muốn kiểm tra phase, dùng integration test có transaction manager thật, thực hiện commit/rollback và đo outcome của listener. Chú ý `@Transactional` trên chính test method thường được rollback cuối test, nên cần chủ động quản lý transaction boundary trước khi assert event after-commit.

### 10.2. Không đồng nhất publish với durable delivery

Ngay cả khi listener ở `AFTER_COMMIT`, một process crash có thể làm mất công việc chưa được giao tới hệ thống ngoài. Khi event là thông tin phải truyền bền vững, cân nhắc **transactional outbox**:

~~~text
Transaction T1:
    save order
    insert outbox event row (eventId, payload)
commit T1
    |
    v
dispatcher -> broker / external consumer
            retry + idempotency
~~~

Mockito publisher mock không kiểm tra outbox hay retry. Các yêu cầu ấy nên có test tích hợp với database, worker dispatcher và failure scenarios.

## 11. Mock publisher không kiểm tra async listener

Giả sử listener:

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    emailService.send(event.orderId());
}
~~~

Đây là mã minh họa, cần cấu hình `@EnableAsync`, executor và các bean tương ứng. Khi publisher thật dispatch event, Spring có thể thực thi listener trên worker thread. Nhưng publisher mock **không schedule task** và không gọi listener, nên unit test chỉ có `verify(publisher)` sẽ không biết:

- `@Async` đã được bật chưa.
- Executor có được cấu hình đúng không.
- Listener có đang chạy đồng bộ vì proxy không hoạt động không.
- Worker lỗi có được xử lý qua `AsyncUncaughtExceptionHandler` hay không.
- Lỗi scheduling/rejection có được quan sát không.
- Shutdown có chờ task hoặc hủy công việc theo policy không.

Khi muốn test async dispatch, dùng context thật với listener quan sát được; kiểm tra kết quả bằng `CountDownLatch`/future/trạng thái bền vững có timeout. Không dùng `Thread.sleep(100)` rồi đoán tác vụ đã hoàn thành.

Với integration test dùng `@RecordApplicationEvents`, event được ghi nhận khi publish **không đồng nghĩa listener async đã hoàn tất**. Assertion về listener async phải chờ đúng outcome. `events.stream(...)` chỉ trả lời có event được ghi nhận, không phải mọi listener đã xử lý thành công.

## 12. Mock publisher và test listener là hai cấp độ khác nhau

Có ba test thường bổ trợ nhau:

### 12.1. Unit test producer

**System under test:** `OrderService`.

**Dependency mock:** `ApplicationEventPublisher` và `OrderRepository`.

**Assertion:** `OrderPlaced` được publish đúng khi logic chấp nhận order; không publish trong đường lỗi.

Đây là mục tiêu trực tiếp của bài học.

### 12.2. Unit test listener

**System under test:** `OrderAuditListener` hoặc `NotificationListener`.

Tạo event trực tiếp và gọi phương thức listener; mock dependency của listener như `AuditRepository`/`EmailClient`. Test **nội dung phản ứng của listener**, không cần publisher hoặc Spring event dispatch nếu method không phụ thuộc container behavior.

Ví dụ:

~~~java
OrderPlaced event = new OrderPlaced(101L, 12_000L);
listener.onOrderPlaced(event);
verify(auditRepository).appendFor(101L, 12_000L);
~~~

Đây là mảnh code minh họa có `listener`/`auditRepository`. Nó không kiểm tra việc Spring đăng ký listener, proxy, transaction phase hoặc async scheduling.

### 12.3. Integration test event dispatch

**System under test:** Spring ApplicationContext + producer + listener.

Dùng publisher thật và `@RecordApplicationEvents`, spy hoặc trạng thái cuối của listener. Test event đi qua framework đúng cấu hình; thêm transaction/async integration test khi chúng là phần của hợp đồng.

Ba lớp test có mục tiêu khác nhau, không thay thế lẫn nhau. Chỉ cần test phù hợp với rủi ro của tính năng, không nhất thiết nhân đôi cùng một assertion ở mọi cấp độ.

## 13. Fake publisher đơn giản khi không cần Mockito

Mockito giúp verify, capture và stub exception. Nhưng `ApplicationEventPublisher` là functional interface với một phương thức trừu tượng nhận `Object`, nên test đơn giản có thể dùng một **fake thu thập event**:

~~~java
List<Object> published = new ArrayList<>();

ApplicationEventPublisher fakePublisher =
    event -> published.add(event);

OrderService service =
    new OrderService(fakeRepository, fakePublisher);

service.place(101L, 12_000L);

assertEquals(
    List.of(new OrderPlaced(101L, 12_000L)),
    published
);
~~~

Đây là mảnh code test minh họa: cần import `List`, `ArrayList`, JUnit `assertEquals` và fake repository (ví dụ implementation chỉ ghi nhận dữ liệu). Một lambda được dùng thay vì Mockito để lưu các object event.

**Khác biệt:** fake tự ghi dữ liệu cần kiểm tra, Mockito tự ghi invocation và cung cấp `verify`/`ArgumentCaptor`/`InOrder`. Fake hữu ích khi muốn đọc một danh sách event; Mockito hữu ích khi có nhiều dependency hoặc phải kiểm tra thứ tự. Cả hai **không** dispatch qua Spring context.

## 14. Mockito matchers, ArgumentCaptor và những bẫy thường gặp

### 14.1. Dùng đúng typed matcher

Trong các trường hợp đơn giản:

~~~java
verify(publisher).publishEvent(
    argThat(event ->
        event instanceof OrderPlaced placed
        && placed.orderId() == 101L
        && placed.totalCents() == 12_000L
    )
);
~~~

Đoạn này là mảnh unit test; Java 17 hỗ trợ pattern matching cho `instanceof`. `argThat` là Mockito matcher. Vì overload Java tồn tại, kiểu suy luận của matcher có thể làm lời gọi trở nên mơ hồ trong một số trường hợp. Khi gặp vấn đề overload, `ArgumentCaptor<Object>` và assertion loại event sau khi capture thường dễ hiểu hơn.

### 14.2. Không trộn raw values và matchers sai quy tắc

Nếu method có nhiều tham số, khi đã dùng matcher cho một tham số thì các tham số khác nên được chỉ định qua matcher phù hợp (ví dụ `eq(...)`), không trộn một literal tùy tiện vào lời gọi Mockito. Với `publishEvent` chỉ có một tham số nên vấn đề này ít xuất hiện, nhưng vẫn cần hiểu khi test dependency khác.

### 14.3. Đừng mock final event nếu không cần

Event record là một giá trị dữ liệu. Test nên tạo `new OrderPlaced(...)` thật rồi kiểm tra nội dung. Mock event record làm giảm ý nghĩa contract vì test có thể chỉ xác nhận hành vi stub của một object giả.

### 14.4. Bắt tham số và xác minh chính xác

Với event có nhiều field, dùng captor để xác nhận `eventId`, `aggregateId`, `occurredAt`, `schemaVersion` theo đúng quy tắc. Nếu thời điểm do `Instant.now()` tạo ra, tránh assert bằng thời điểm “gần đúng” khó ổn định; hãy inject `Clock` cố định hoặc so sánh theo một khoảng có kiểm soát.

Ví dụ:

~~~java
Clock clock = Clock.fixed(
    Instant.parse("2026-01-01T00:00:00Z"),
    ZoneOffset.UTC
);
~~~

Đây là Java snippet minh họa, cần import `Clock`, `Instant` và `ZoneOffset`. Inject clock vào service sẽ giúp event timestamp có giá trị xác định trong test.

### 14.5. Đúng một event hay đúng một invocation?

`verify(publisher).publishEvent(...)` kiểm tra **lời gọi của code**, không đảm bảo Spring phát đến đúng một listener. Một event có thể có nhiều listener, một listener có thể được gọi lại, hoặc event có thể được retry ở broker bên ngoài. Đừng dùng số invocation của publisher làm thay thế cho xử lý exactly-once.

## 15. Lựa chọn test double phù hợp

| Công cụ | Hữu ích nhất khi | Không chứng minh được |
| --- | --- | --- |
| `Mockito.mock(ApplicationEventPublisher.class)` | Verify publish, payload, số lần, thứ tự | Listener dispatch, commit, async, durability |
| Fake `ApplicationEventPublisher` lưu danh sách | Thu event để kiểm tra nội dung dễ đọc | Spring annotation/proxy/dispatch |
| Mock listener dependency | Test logic xử lý event riêng lẻ | Listener được đăng ký thật |
| `@RecordApplicationEvents` | Ghi sự kiện trong integration test Spring | Mọi listener đều hoàn tất, durability |
| Capturing listener/spy với context thật | Chứng minh listener thực nhận/xử lý | Chính sách commit nếu không có transaction test |
| Test với transaction manager thật | Commit/rollback, after-commit | Delivery bền vững xuyên process crash |
| Test outbox/broker thật hoặc giả lập lỗi | Retry, idempotency, recovery | Không tự thay thế test ngữ nghĩa publisher |

**Khuyến nghị theo độ phức tạp:** bắt đầu bằng unit test producer dùng Mockito; thêm một integration test nhỏ chứng minh event wiring; bổ sung transaction/async/replay tests nếu tính năng yêu cầu. Tránh dùng một `@SpringBootTest` nặng cho mọi assertion chỉ cần mock.

## 16. Những sai lầm phổ biến

1. **Mock publisher rồi kết luận listener chạy:** mock chỉ ghi invocation, không dispatch.
2. **Đọc `verify(publisher)` như bảo đảm database đã commit:** transaction có thể rollback sau publish.
3. **Đặt event theo command chưa thành công:** `OrderPlaced` không được phát khi validation thất bại.
4. **Không kiểm tra payload:** test chỉ biết có event nhưng không biết sai order ID hay số tiền.
5. **Không kiểm tra nhánh lỗi:** service phát event dù repository ném exception.
6. **Nhầm overload `publishEvent(ApplicationEvent)` và `publishEvent(Object)`:** Mockito verify sai method signature.
7. **Dùng event mutable không có equals rồi verify bằng instance mới:** dễ fail hoặc che lỗi; dùng record/captor.
8. **Dùng `verifyNoInteractions` trên mock dùng chung cho nhiều đường khởi tạo:** assertion có thể nhạy với setup không liên quan.
9. **Verify mọi chi tiết internal call:** test brittle khi refactor nhưng contract vẫn đúng.
10. **Dùng `@SpringBootTest` chỉ để kiểm tra một method gọi publisher:** tốn thời gian mà không thêm giá trị.
11. **Thay publisher thật trong integration test bằng mock:** làm event bus không dispatch như production.
12. **Nghĩ `ApplicationEvents` ghi nhận event thì worker async đã hoàn tất:** phải đợi outcome thực tế.
13. **Để test kết thúc trong transaction tự rollback rồi mong AFTER_COMMIT chạy:** cần quản lý transaction boundary.
14. **Cho rằng @RecordApplicationEvents là event store:** nó chỉ ghi event trong phạm vi test.
15. **Không tách lỗi repository tức thời và lỗi commit:** mock save exception không mô phỏng mọi đường rollback.
16. **Dùng `Thread.sleep` cho async integration test:** flaky, phụ thuộc scheduler và tải CI.
17. **Không test event bị phát lặp:** consumer có thể nhận nhiều event không mong muốn dù API call chỉ có một.
18. **Dùng Mockito mock như bằng chứng delivery tin cậy:** chỉ outbox/broker/recovery test mới kiểm tra độ bền.
19. **Mock cả domain event:** test không xác nhận fact nghiệp vụ thực.
20. **Đổi tên event/schema mà không cập nhật integration contract:** phía ngoài có thể vẫn dựa vào type/version cũ.

## 17. Bài tập thực hành

1. Trong một use case `placeOrder`, vì sao unit test có thể dùng `mock(ApplicationEventPublisher.class)` mà không mở Spring context?
2. `verify(publisher).publishEvent(...)` chứng minh điều gì? Nó không chứng minh điều gì?
3. Khi nào nên dùng `ArgumentCaptor<Object>` thay vì `verify` với object event mới?
4. Phân biệt overload `publishEvent(Object)` và `publishEvent(ApplicationEvent)` trong Java.
5. Vì sao record `OrderPlaced` thuận tiện cho assertion dựa trên equals?
6. Nếu `repository.save` ném `RuntimeException` ngay, test nên mong publisher bị gọi không?
7. Nếu `repository.save` trả bình thường nhưng transaction commit thất bại về sau, unit test dùng publisher mock có phát hiện được không?
8. Vì sao cần `InOrder` khi thứ tự save/publish là hợp đồng, và vì sao nó không chứng minh after-commit?
9. Khi integration test muốn xác nhận listener `@EventListener` thực sự nhận event, nên giữ publisher thật hay mock?
10. `@RecordApplicationEvents` cung cấp loại quan sát nào? Nó có thay thế cho assertion listener outcome không?
11. Với một `@Async` listener, vì sao xác nhận đã publish không đủ để khẳng định đã gửi email?
12. Nếu event được giao lại sau process crash, Mockito unit test publisher có kiểm tra idempotency consumer không?
13. Tại sao một fake publisher lưu danh sách event đôi khi dễ đọc hơn một mock với nhiều matcher?
14. Khi event chứa `Instant.now()`, cách làm nào giúp test xác định và không flaky?

**Định hướng đáp án:** (1) interface được inject và mock, test thuần JVM; (2) có invocation, chưa có dispatch/commit/delivery; (3) muốn đọc đúng runtime type/field hoặc equals chưa phù hợp; (4) overload được compiler chọn theo kiểu Java của argument; (5) record có equals theo component; (6) không; (7) không; (8) kiểm tra gọi trước/sau nhưng không có DB commit; (9) publisher thật; (10) ghi event publish trong test, cần đo outcome listener riêng; (11) worker chạy sau và có thể lỗi; (12) không; (13) ít phụ thuộc thư viện, danh sách dễ assert; (14) inject Clock.fixed.

## 18. Tổng kết

**Mock `ApplicationEventPublisher`** là kỹ thuật nhanh và chính xác để unit test **producer** của domain event:

- Inject interface hẹp qua constructor.
- Dùng Mockito tạo mock publisher và repository.
- Dùng `verify`, `ArgumentCaptor` và `InOrder` để kiểm tra loại event, payload, số lần và thứ tự.
- Test nhánh không hợp lệ/lỗi repository để khẳng định không phát event thành công.
- Chú ý overload `publishEvent(Object)` và `publishEvent(ApplicationEvent)`.
- Không nhầm verify invocation với dispatch, commit, after-commit, async completion hoặc durable delivery.
- Khi cần xác nhận Spring event wiring, dùng publisher thật với `@RecordApplicationEvents`/`ApplicationEvents` và listener có outcome quan sát được.
- Khi cần kiểm tra transaction, async hoặc outbox, bổ sung integration tests đúng ranh giới thay vì cố ép publisher mock chứng minh hành vi mà nó không thực thi.

## Tài liệu tham khảo

- Spring Framework 6.2.8 Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Reference — *Application Events in TestContext*: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html
- Spring Framework 6.2.8 Javadoc — *RecordApplicationEvents*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html
- Spring Framework 6.2.8 Javadoc — *ApplicationEvents*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html
- Spring Framework Reference — *Annotation-based Event Listeners*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Mockito official API — *Mockito*: https://javadoc.io/doc/org.mockito/mockito-core/5.15.2/org/mockito/Mockito.html
- Mockito official API — *ArgumentCaptor*: https://javadoc.io/doc/org.mockito/mockito-core/5.15.2/org/mockito/ArgumentCaptor.html
