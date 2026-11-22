# ApplicationEventsTestExecutionListener: ghi nhận và kiểm thử Spring Application Events

## 1. Khái niệm và mục tiêu

`ApplicationEventsTestExecutionListener` là lớp thuộc **Spring TestContext Framework**, có tên đầy đủ:

`org.springframework.test.context.event.ApplicationEventsTestExecutionListener`

Nó là một `TestExecutionListener` hỗ trợ ghi nhận những application events được publish trong `ApplicationContext` **trong phạm vi một test method**, rồi cho phép bài test truy vấn các event đã ghi nhận thông qua API `ApplicationEvents`.

Đây là cơ chế **kiểm thử**; không phải bean listener nghiệp vụ dùng `@EventListener`. Trong hầu hết dự án Spring TestContext, lớp này **đã được đăng ký mặc định**. Tuy nhiên, chỉ đăng ký lớp listener thôi chưa đủ: test class phải được đánh dấu bằng **`@RecordApplicationEvents`**, nếu không listener hỗ trợ ghi nhận event về cơ bản không làm gì.

Sau bài học, bạn cần:

1. Hiểu vai trò của `ApplicationEventsTestExecutionListener` trong chu kỳ kiểm thử Spring.
2. Biết cách kích hoạt bằng `@RecordApplicationEvents` và cách nhận `ApplicationEvents` trong JUnit Jupiter.
3. Kiểm tra event POJO/`ApplicationEvent`, lọc theo kiểu, so khớp payload và reset bản ghi bằng `clear()`.
4. Chạy dự án Java 17+ có test JUnit 5 thực tế.
5. Phân biệt listener **ghi nhận events** với listener **phát test execution events**.
6. Tránh các lỗi về custom `@TestExecutionListeners`, phạm vi test method, transaction, async và context cache.

## 2. Những lớp/annotation cần phân biệt

| Thành phần | Package hoặc vai trò |
| --- | --- |
| `ApplicationEventsTestExecutionListener` | Hạ tầng Spring TestContext; quản lý khả năng ghi nhận events cho test |
| `@RecordApplicationEvents` | Annotation ở **test class**, yêu cầu Spring TestContext ghi nhận events |
| `ApplicationEvents` | API để test truy vấn/đọc/xóa những event đã ghi nhận |
| `ApplicationEventPublisher` | API trong ứng dụng dùng để **publish** event |
| `@EventListener` | Method trong Spring bean dùng để **xử lý** event |
| `EventPublishingTestExecutionListener` | Một listener **khác**: phát các sự kiện vòng đời test như `BeforeTestMethodEvent` |
| `SpringExtension` | Kết nối JUnit Jupiter với Spring TestContext |
| `@SpringJUnitConfig` | Annotation tiện ích kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration` |

**Tên dễ gây nhầm:** `ApplicationEventsTestExecutionListener` không phải một `ApplicationListener<OrderCreated>`. Nó không tự chạy nghiệp vụ của bạn. Nó hỗ trợ **bài test quan sát những gì đã được publish**.

Đừng tự `new ApplicationEventsTestExecutionListener()` rồi gọi `publishEvent` như thể đây là một event bus. Event bus là `ApplicationContext` / `ApplicationEventPublisher`, còn `TestExecutionListener` do TestContext framework quản lý.

## 3. Cơ chế chạy trong TestContext

Luồng khái quát khi JUnit 5 chạy một test:

~~~text
JUnit Jupiter
   |
   +-- SpringExtension
         |
         +-- TestContextManager / danh sách TestExecutionListener
         |
         +-- ApplicationEventsTestExecutionListener (mặc định)
         |       kiểm tra @RecordApplicationEvents
         |       đăng ký ApplicationEvents cho test hiện tại
         |
         +-- tạo/inject test instance, chuẩn bị test method
         |
         +-- @BeforeEach và @Test
         |       |
         |       +-- service gọi publisher.publishEvent(...)
         |       +-- ApplicationEvents ghi nhận event đã publish
         |       +-- test gọi events.stream(OrderCreated.class)
         |
         +-- @AfterEach, kết thúc lifecycle test
                 |
                 +-- dọn trạng thái ghi nhận riêng của test
~~~

Đây là **sơ đồ khái niệm**, không phải danh sách chính xác mọi callback của JUnit hay thứ tự mọi TestExecutionListener. Ví dụ, `prepareTestInstance`, `beforeTestMethod`, `beforeTestExecution` và các callback dọn dẹp nằm ở những pha riêng biệt của TestContext.

Điểm quan trọng là `ApplicationEvents` có phạm vi **lifecycle của test method hiện tại**, không phải một kho lưu event toàn JVM hoặc một bean singleton toàn suite. Một test khác không nên phải lọc các event nghiệp vụ do test trước tạo ra.

### 3.1. Listener được đăng ký khi nào?

Spring đăng ký `ApplicationEventsTestExecutionListener` trong tập các `TestExecutionListener` **mặc định**. Bạn thường chỉ cần:

~~~java
@SpringJUnitConfig
@RecordApplicationEvents
class MyEventTests {
    // Các @Test dùng ApplicationEvents.
}
~~~

Trong Spring Framework 6.2.x, listener này có `ORDER = 1800` (từ 6.2.3) và được sắp sau `DirtiesContextBeforeModesTestExecutionListener`, trước các listener injection phù hợp. Không dựa vào một con số thứ tự tùy ý để tự điều khiển việc capture events trừ khi thực sự cần custom TestContext setup.

### 3.2. Khi nào nó không ghi nhận?

`@RecordApplicationEvents` có thể được đặt trực tiếp hoặc thông qua **meta-annotation** ở test class. Nếu không có annotation ấy, `ApplicationEventsTestExecutionListener` đã đăng ký cũng không kích hoạt cơ chế ghi nhận thông thường.

Nếu bạn dùng `@TestExecutionListeners` tùy biến và **thay thế** toàn bộ default listeners, `ApplicationEventsTestExecutionListener` có thể không còn được đăng ký. Khi đó chỉ thêm `@RecordApplicationEvents` là chưa đủ; cần merge default listeners hoặc đăng ký listener còn thiếu một cách có chủ đích.

## 4. Điều kiện tiên quyết để sử dụng

Với JUnit Jupiter, quy trình thông thường:

1. Dùng `spring-test` và JUnit Jupiter trong dependencies test.
2. Cho test class chạy qua `SpringExtension`; cách ngắn nhất là `@SpringJUnitConfig` với config chứa Spring bean cần test.
3. Đặt `@RecordApplicationEvents` trên class.
4. Giữ `ApplicationEventsTestExecutionListener` trong danh sách TestExecutionListeners (mặc định đã có).
5. Nhận `ApplicationEvents` qua parameter trong `@Test`, `@BeforeEach` hoặc `@AfterEach`, hoặc field `@Autowired`.
6. Chạy use case làm Spring publish event, rồi assert `events.stream(...)`.

Ví dụ khai báo một method test:

~~~java
// Minh họa; OrderService, OrderSubmitted, cấu hình test được định nghĩa thêm.
@Test
void shouldPublishOrderSubmitted(
        @Autowired OrderService service,
        ApplicationEvents events) {

    events.clear(); // bỏ qua các event không liên quan đã ghi trước action
    service.submit(101L);

    assertEquals(
            1L,
            events.stream(OrderSubmitted.class).count());
}
~~~

`ApplicationEvents` được Spring TestContext hỗ trợ trong lifecycle test, còn `OrderService` được Spring inject làm tham số bằng `@Autowired`. `clear()` là tùy chọn, nhưng hữu ích nếu muốn đo **chính xác sự kiện do một hành động cụ thể tạo ra**, không bị nhiễu bởi các framework/test fixture events đã publish trước đó.

### Vì sao constructor injection không phải lựa chọn phù hợp?

Tài liệu Spring lưu ý `ApplicationEvents` là resolvable dependency có phạm vi **test method**. Nó không có sẵn ngoài lifecycle đó và **không thể được `@Autowired` vào constructor của test class**. Đừng giữ một `ApplicationEvents` lấy từ constructor rồi dùng như singleton.

Cách được khuyến nghị là parameter `ApplicationEvents events` ở `@Test`, `@BeforeEach` hoặc `@AfterEach`. Field `@Autowired ApplicationEvents` trong test class cũng được hỗ trợ trong lifecycle test, nhưng parameter injection làm giới hạn thời gian sử dụng rõ hơn.

`@BeforeAll` và `@AfterAll` nằm ngoài lifecycle của từng test method; không thiết kế phép ghi nhận test hiện tại dựa vào việc inject `ApplicationEvents` tại các hook cấp class này.

## 5. API `ApplicationEvents`

Giao diện `org.springframework.test.context.event.ApplicationEvents` hỗ trợ ba method cốt lõi:

| API | Ý nghĩa |
| --- | --- |
| `Stream<ApplicationEvent> stream()` | Lấy stream các `ApplicationEvent` đã ghi nhận |
| `<T> Stream<T> stream(Class<T> type)` | Lọc theo kiểu event hoặc kiểu **payload** và trả các đối tượng phù hợp |
| `void clear()` | Xóa các event đã ghi nhận trong instance hiện tại; event mới sau đó vẫn được ghi nhận |

### 5.1. Kiểm tra event truyền dưới dạng POJO

Từ Spring Framework 4.2, `ApplicationEventPublisher.publishEvent(Object)` có thể nhận một POJO hoặc record không kế thừa `ApplicationEvent`:

~~~java
// Minh họa trong một Spring-managed service.
publisher.publishEvent(new OrderSubmitted(101L));
~~~

Khi publish POJO, Spring có thể bao payload bằng `PayloadApplicationEvent` để phân phối. Do đó `events.stream()` trả về những đối tượng `ApplicationEvent` bao gồm wrapper, còn:

~~~java
List<OrderSubmitted> submitted =
        events.stream(OrderSubmitted.class).toList();
~~~

...cho bạn các **payload `OrderSubmitted`** đúng kiểu. Đây là phương án gọn để assert domain events, không cần phụ thuộc chi tiết wrapper.

### 5.2. Khi nào dùng `stream()` không tham số?

Khi cần kiểm tra sự tồn tại của một `ApplicationEvent` nguyên bản, phân tích wrapper hoặc quan sát nhiều kiểu event:

~~~java
// Minh họa bên trong @Test, sau khi đã có events.
boolean sawPayloadWrapper = events.stream()
        .anyMatch(event -> event instanceof PayloadApplicationEvent<?>);
~~~

Lưu ý: toàn bộ event stream có thể gồm các **test execution events** hoặc event framework khác. Không nên assert tổng số `events.stream().count()` bằng đúng 1 chỉ vì bạn gọi một lần `OrderService.submit()`. Lọc đúng kiểu domain event là cách xác minh đáng tin hơn.

### 5.3. Xóa event trước một action cụ thể

~~~java
events.clear();
service.submit(101L);
assertEquals(1L, events.stream(OrderSubmitted.class).count());
~~~

`clear()` **chỉ xóa dữ liệu đã ghi nhận** trong `ApplicationEvents`; nó không xóa queue, không hủy event đã publish, không rollback transaction và không gỡ các `@EventListener` khỏi context.

`stream()` trả Java Stream: nếu muốn kiểm tra nhiều phép toán, gọi `stream(...)` mới cho mỗi lần hoặc materialize thành `List`; một `Stream` đã tiêu thụ không thể tái sử dụng.

## 6. Ví dụ Java 17+ hoàn chỉnh: JUnit 5 ghi nhận domain events

Ví dụ này sử dụng:

- Java 17+ và Maven.
- Spring Framework **6.2.12**: `spring-context` và `spring-test`.
- JUnit Jupiter **5.11.4** và Maven Surefire **3.5.2**.
- Một `OrderService` Spring bean phát record `OrderSubmitted` bằng `ApplicationEventPublisher`.
- Test class được cấu hình bằng `@SpringJUnitConfig` và `@RecordApplicationEvents`.
- Hai phương thức test độc lập để kiểm tra `stream(Class)`, `stream()` và `clear()`.

Không cần Spring Boot, web server hoặc database; đây là ví dụ tập trung vào **Spring TestContext** và `ApplicationEventsTestExecutionListener`.

Cấu trúc thư mục:

~~~text
application-events-test/
├── pom.xml
└── src/test/java/demo/OrderEventTests.java
~~~

### 6.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>application-events-test</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.12</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
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

### 6.2. `src/test/java/demo/OrderEventTests.java`

~~~java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(classes = OrderEventTests.Config.class)
@RecordApplicationEvents
class OrderEventTests {

    // POJO/record payload: không kế thừa ApplicationEvent.
    record OrderSubmitted(long orderId) {}

    static final class OrderService {
        private final ApplicationEventPublisher publisher;

        OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        void submit(long orderId) {
            publisher.publishEvent(new OrderSubmitted(orderId));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class Config {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    @Test
    void recordsTypedPayload(
            @Autowired OrderService service,
            ApplicationEvents events) {

        // Không để events ở bước chuẩn bị test làm nhiễu assertion.
        events.clear();

        service.submit(101L);

        List<OrderSubmitted> recorded =
                events.stream(OrderSubmitted.class).toList();

        assertEquals(List.of(new OrderSubmitted(101L)), recorded);

        // POJO được Spring đưa qua một ApplicationEvent wrapper.
        assertTrue(events.stream().anyMatch(
                event -> event instanceof PayloadApplicationEvent<?>));
    }

    @Test
    void clearOnlyResetsTheRecording(
            @Autowired OrderService service,
            ApplicationEvents events) {

        events.clear();
        service.submit(201L);

        assertEquals(1L, events.stream(OrderSubmitted.class).count());

        // Xóa dữ liệu test đã ghi, không dừng ApplicationEventPublisher.
        events.clear();
        assertEquals(0L, events.stream(OrderSubmitted.class).count());

        service.submit(202L);

        assertEquals(
                List.of(new OrderSubmitted(202L)),
                events.stream(OrderSubmitted.class).toList());
    }
}
~~~

Chạy từ thư mục chứa `pom.xml`:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** Maven Surefire tìm thấy class `OrderEventTests` và chạy **2 test**, tất cả đều PASS (`Tests run: 2, Failures: 0, Errors: 0, Skipped: 0`). Dòng log/trật tự hiển thị có thể khác theo Maven/JUnit và môi trường; không có `System.out.println` trong test, nên không có stdout tự định nghĩa cần khớp từng dòng.

### 6.3. Tại sao ví dụ hoạt động?

- `@SpringJUnitConfig` bật SpringExtension và tạo ApplicationContext từ `Config`.
- `Config` khai báo một `OrderService`, còn Spring cung cấp `ApplicationEventPublisher` phù hợp cho bean.
- `@RecordApplicationEvents` yêu cầu TestContext ghi nhận events.
- `ApplicationEventsTestExecutionListener` đã nằm trong default listeners, nên test **không cần tự đăng ký listener**.
- JUnit gọi method test; Spring giải quyết tham số `@Autowired OrderService` và `ApplicationEvents`.
- Khi `service.submit` publish một `OrderSubmitted` record, TestContext ghi nhận event ấy.
- `stream(OrderSubmitted.class)` trích đúng payload dù event được Spring wrap bên trong `PayloadApplicationEvent`.
- Test thứ hai cho thấy `clear()` xóa dữ liệu recording trước đó, nhưng những event được publish sau đó vẫn được thêm mới.

Hai test **không phụ thuộc thứ tự chạy**. Không dùng `@TestMethodOrder` hoặc biến static để dựa vào kết quả test trước. Mỗi test tự clear trước action, vì thế ngay cả khi TestContext phát các sự kiện vòng đời test khác, assertion kiểu `OrderSubmitted` vẫn độc lập.

## 7. `@RecordApplicationEvents` và lifecycle từng test method

### 7.1. Test class, không phải riêng từng listener bean

`@RecordApplicationEvents` được đặt lên **test class** (cũng có thể dùng làm meta-annotation). Nó chỉ dẫn **Spring TestContext** ghi lại events trong khi test thực thi. Bạn không cần gắn annotation này lên `OrderService` hoặc những bean nghiệp vụ.

Khi một test class khác không có annotation, việc listener infrastructure vẫn tồn tại trong default configuration **không có nghĩa class ấy tự được cung cấp `ApplicationEvents` để assert**.

### 7.2. Dùng ở `@BeforeEach` và `@AfterEach`

Spring cho phép nhận `ApplicationEvents` ở các lifecycle methods của **mỗi test**:

~~~java
// Minh họa trong test class đã @SpringJUnitConfig và @RecordApplicationEvents.
@BeforeEach
void resetEventRecording(ApplicationEvents events) {
    events.clear();
}

@Test
void someTest(ApplicationEvents events) {
    // Thực hiện action và assert events.
}

@AfterEach
void inspectEvents(ApplicationEvents events) {
    // Có thể kiểm tra event phát trong test hoặc phần trước đó.
}
~~~

Đây là snippet minh họa; cần imports `@BeforeEach`, `@Test`, `@AfterEach` và cấu hình Spring test thực. Lưu ý events có thể được publish trong `@BeforeEach` hoặc `@AfterEach`; chọn vị trí `clear()` và thời điểm assertion phù hợp.

### 7.3. `@Autowired` field

Một lựa chọn khác là field injection trong class test:

~~~java
// Minh họa: ở trong test class có @RecordApplicationEvents.
@Autowired
ApplicationEvents applicationEvents;
~~~

Tài liệu Spring hỗ trợ cách này, nhưng **không khuyến nghị constructor injection** cho `ApplicationEvents` do phạm vi thực tế là test method. Nếu muốn tránh hiểu lầm lifecycle, method parameter thường minh bạch hơn.

### 7.4. Test context cache không phải test event store

Spring TestContext có thể cache một `ApplicationContext` dùng chung cho nhiều test methods hoặc test classes có cấu hình giống nhau. Điều đó **không có nghĩa** `ApplicationEvents` là một danh sách lưu toàn bộ event từ tất cả các test dùng chung context.

Bộ ghi nhận được quản lý theo lifecycle của **test hiện tại**, còn bản thân singleton beans hoặc database test fixture có thể vẫn được tái sử dụng. Đừng suy luận việc event recording riêng đồng nghĩa mọi state khác trong application context tự reset; test vẫn cần quản lý dữ liệu dùng chung và cô lập side effects.

## 8. Custom `@TestExecutionListeners`: nguồn lỗi cấu hình phổ biến

Theo tài liệu Spring, `ApplicationEventsTestExecutionListener` **được đăng ký mặc định**, nên thông thường không cần khai báo tường minh. Nhưng khi bạn có cấu hình:

~~~java
// Minh họa rủi ro: MyCustomListener cần được định nghĩa.
@TestExecutionListeners(MyCustomListener.class)
class MyCustomTests {
}
~~~

...nếu cấu hình này **thay thế default listeners**, cơ chế ghi nhận application events có thể biến mất, dù bạn vẫn giữ `@RecordApplicationEvents`. Hãy bảo toàn default listeners bằng merge mode phù hợp:

~~~java
// Minh họa: MyCustomListener cần được định nghĩa.
@TestExecutionListeners(
    listeners = MyCustomListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class MyCustomTests {
}
~~~

Khi đó custom listener được kết hợp với default set, bao gồm `ApplicationEventsTestExecutionListener`. Nếu dự án có hierarchy/nhiều meta-annotations, kiểm tra cách các cấu hình TestExecutionListeners hợp nhất và thứ tự chính xác thay vì chỉ nhìn một annotation cục bộ.

**Một anti-pattern khác:** tự cấu hình lại tất cả listener theo danh sách thủ công nhưng quên `DependencyInjectionTestExecutionListener`. Khi đó không chỉ `ApplicationEvents` có thể lỗi, việc inject bean vào test class cũng có thể bị ảnh hưởng.

## 9. Phân biệt với `EventPublishingTestExecutionListener`

Hai lớp rất dễ nhầm vì đều chứa chữ Event và TestExecutionListener:

| Đặc điểm | `ApplicationEventsTestExecutionListener` | `EventPublishingTestExecutionListener` |
| --- | --- | --- |
| Mục đích | **Ghi nhận** application events cho test assertion | **Phát** các sự kiện vòng đời test vào Spring ApplicationContext |
| Kích hoạt use case chính | `@RecordApplicationEvents` | Tương tác lifecycle test và context đã được load |
| API dùng trong test | `ApplicationEvents.stream(...)`, `clear()` | Các bean listener nhận `BeforeTestMethodEvent`, `AfterTestMethodEvent`, v.v. |
| Có phải bean `@EventListener`? | Không | Không; chính nó là TestExecutionListener hạ tầng |
| Đã có trong default listeners? | Có | Có |

Các test execution events được publish bởi `EventPublishingTestExecutionListener` gồm `BeforeTestClassEvent`, `PrepareTestInstanceEvent`, `BeforeTestMethodEvent`, `BeforeTestExecutionEvent`, `AfterTestExecutionEvent`, `AfterTestMethodEvent`, `AfterTestClassEvent`.

Không phải **mọi** sự kiện lifecycle test đều luôn xuất hiện: listener phát test execution event chỉ có thể publish khi `ApplicationContext` đã được load; tùy cache và thời điểm dựng context, một số event cấp class có thể không được phát. Vì vậy, khi kiểm thử một event domain duy nhất, **lọc theo kiểu domain event** thay vì assert tổng số event thô.

Ví dụ một Spring bean có thể lắng nghe test execution event:

~~~java
// Minh họa ý tưởng, cần imports và Spring bean khai báo phù hợp.
@EventListener
public void onBeforeTestMethod(BeforeTestMethodEvent event) {
    // Chạy khi Spring TestContext phát test execution event tương ứng.
}
~~~

Đừng dùng `EventPublishingTestExecutionListener` như cách “bật ghi nhận domain events”; nó giải quyết công việc khác.

## 10. Những giới hạn khi test event

### 10.1. Ghi nhận event khác với khẳng định listener đã thành công

Một assertion:

~~~java
assertEquals(1L, events.stream(OrderSubmitted.class).count());
~~~

...chứng minh `OrderSubmitted` đã được ghi nhận trong test context. Nó **không tự chứng minh** email đã gửi, database đã commit, `@Async` listener đã hoàn tất hoặc broker đã nhận integration event.

Để xác nhận **side effect** của listener, cần test riêng: kiểm tra repository state, mock interaction, message stub hoặc kết quả xử lý, với đồng bộ hóa/timeout phù hợp.

### 10.2. Event POJO và payload wrapper

`ApplicationEvents.stream(Class<T>)` có thể trả về event đối tượng hoặc **payload** của event theo kiểu truyền vào. Với POJO record, nên dùng `stream(OrderSubmitted.class)`, không mặc định viết `stream().map(event -> (OrderSubmitted) event)` vì một `PayloadApplicationEvent` không phải đối tượng `OrderSubmitted` trực tiếp.

Trường hợp bạn tạo một class subclass của `ApplicationEvent`, `stream(MyApplicationEvent.class)` cũng có thể lọc theo kiểu sự kiện ấy. Chọn một kiểu test rõ ràng thay vì assert dựa vào tên class qua string.

### 10.3. Transaction và `@TransactionalEventListener`

Khi một method publish event **trong transaction**, recording có thể thấy event ngay khi publish. Nhưng `@TransactionalEventListener(phase=AFTER_COMMIT)` chỉ chạy **nếu transaction commit thành công**. Hai sự thật không mâu thuẫn: event được publish và ghi nhận, còn callback transaction-bound có thể không thực thi.

Nếu test có `@Transactional` do Spring TestContext quản lý, transaction test **thường rollback mặc định**. Đừng assert `AFTER_COMMIT` đã chạy chỉ vì `events.stream(MyEvent.class)` có event. Muốn test callback after commit, cần tổ chức transaction commit rõ ràng, chẳng hạn test với giao dịch thật và `TestTransaction` nếu phù hợp.

Tương tự, `ApplicationEventsTestExecutionListener` không thay thế `TransactionalTestExecutionListener` và không tự thay đổi commit/rollback semantics.

### 10.4. Async và thread boundary

Annotation `@RecordApplicationEvents` ghi nhận events phát trong phạm vi test theo cơ chế quản lý test thread và các thread con được hỗ trợ. Nhưng một task chạy ở **thread pool có sẵn**, một scheduler, một worker bên ngoài hoặc process khác **không đương nhiên thuộc context ghi nhận của test**.

Nếu event được publish từ một executor/background worker, đừng mặc định `ApplicationEvents` chắc chắn quan sát mọi lần publish trong thread đó. Kiểm tra liệu recording context có được truyền đúng không; ưu tiên thiết kế test có synchronization rõ ràng hoặc publish event từ test thread khi mục tiêu chỉ là unit/integration test của publisher.

Ngược lại, việc `ApplicationEvents` đã ghi nhận **sự kiện nguồn** cũng không có nghĩa các `@Async @EventListener` đã hoàn tất xử lý. Dùng `CountDownLatch`, `CompletableFuture`, Awaitility hoặc công cụ đợi có timeout nếu cần assert side effect bất đồng bộ. Không dựa vào `Thread.sleep` tùy ý để chứng minh tính đúng đắn.

### 10.5. Đếm, ordering và duplicate

- Lọc đúng class domain event để tránh event hạ tầng làm sai tổng count.
- Không suy ra thứ tự của các listener bất đồng bộ từ thứ tự event stream.
- Nếu một action publish nhiều event cùng loại, lọc thêm `aggregateId`, `eventId` hoặc payload để tránh false positive.
- Với parent/child ApplicationContext, sự kiện có thể được chuyển tiếp lên parent; cần hiểu phạm vi context và tránh assert “chỉ một lần” trong những hệ thống có propagation.
- Với broker hoặc application ngoài JVM, `ApplicationEvents` trong Spring test không phải công cụ thu thập message phân tán; dùng test harness của broker/integration adapter.

## 11. Checklist chẩn đoán khi `ApplicationEvents` không có dữ liệu

1. **Test class có `@RecordApplicationEvents` không?** Annotation đặt trên class hoặc meta-annotation, không phải chỉ gắn trên bean service.
2. **Test có chạy với Spring TestContext không?** Với JUnit 5, dùng `@SpringJUnitConfig`, `@SpringBootTest` kết hợp SpringExtension hoặc cấu hình tương đương.
3. **`ApplicationEventsTestExecutionListener` có trong listener set không?** Mặc định có, trừ khi custom `@TestExecutionListeners` thay thế defaults.
4. **Có inject `ApplicationEvents` đúng lifecycle không?** Dùng test method / `@BeforeEach` / `@AfterEach`; không cố inject vào constructor.
5. **Event có thực sự được publish trong ApplicationContext test không?** Nếu code tự `new` một object ngoài Spring rồi không dùng publisher Spring, recording không thể tự tạo event.
6. **Bạn đang lọc đúng kiểu không?** POJO payload dùng `stream(PayloadType.class)`, không cast sai từ `ApplicationEvent`.
7. **Có gọi `clear()` sau khi publish mà trước assertion không?** Nó xóa recording của chính test.
8. **Publish xảy ra ở thread khác không?** Executor có thể không mang recording context sang worker.
9. **Có nhầm event publish với listener hoàn tất không?** Async side effect và transactional callbacks cần kiểm tra riêng.
10. **Context có hierarchy hoặc nhiều listeners không?** Kiểm tra nguồn phát, duplicate và thời điểm lifecycle phù hợp.

## 12. Thực hành nâng cao

### Bài tập 1 — Lọc event theo nội dung

Mở rộng `OrderSubmitted` thành:

~~~java
// Minh họa Java 17 record:
record OrderSubmitted(long orderId, String customerId) {}
~~~

Sau khi submit hai đơn hàng, lọc `events.stream(OrderSubmitted.class)` và dùng `filter(e -> e.orderId() == 101L)` để xác minh đúng business key thay vì chỉ nhìn tổng count.

### Bài tập 2 — Tạo custom TestExecutionListener

Viết một `AbstractTestExecutionListener` để ghi log trước/sau test. Cấu hình `@TestExecutionListeners(mergeMode=MERGE_WITH_DEFAULTS)`, bảo đảm `ApplicationEventsTestExecutionListener` vẫn hoạt động. Thử thay bằng mode replace (trên một test riêng) để quan sát sự khác biệt.

### Bài tập 3 — Trước và sau commit

Tạo service `@Transactional` publish event và listener `@TransactionalEventListener(AFTER_COMMIT)`. Chạy test trong transaction rollback rồi so sánh:

- `ApplicationEvents` có ghi nhận event publish không?
- Listener after commit có thực thi không?
- Sau khi commit thật, kết quả thay đổi thế nào?

Hãy giải thích vì sao một test chỉ assert `events.stream(...)` chưa đủ để chứng minh giao dịch đã commit.

### Bài tập 4 — Async listener

Thêm `@Async` listener có kết quả quan sát được. Dùng latch/Future để đợi hoàn tất, rồi assert side effect. Tách biệt assertion về **event được publish** với assertion về **listener đã xử lý**.

### Bài tập 5 — `@BeforeEach` và test instance

Viết `@BeforeEach` nhận `ApplicationEvents` và gọi `clear()`. Thêm hai test publish hai order IDs khác nhau. Xác nhận cả hai test độc lập, ngay cả khi Spring cache cùng một ApplicationContext.

## 13. Nguyên tắc sử dụng và sai lầm phổ biến

| Sai lầm | Vấn đề | Cách đúng |
| --- | --- | --- |
| Chỉ thêm `@RecordApplicationEvents` nhưng bỏ default TestExecutionListeners | Không có listener quản lý recording | Giữ default listeners hoặc đăng ký listener cần thiết |
| Gọi `new ApplicationEventsTestExecutionListener()` trong test | Không tự tích hợp với TestContextManager | Dùng SpringExtension / TestContext |
| Cố `@Autowired ApplicationEvents` vào constructor | Dependency chỉ có trong lifecycle test method | Nhận parameter trong test/`@BeforeEach`/`@AfterEach` |
| Dùng `events.stream().count()` để đếm domain events | Có event framework hoặc wrapper khác | Lọc `stream(MyEvent.class)` |
| Ép `PayloadApplicationEvent` thành POJO | `ClassCastException` | Dùng typed stream để lấy payload |
| Cho rằng `clear()` hủy publish/side effect | Chỉ recording bị xóa, nghiệp vụ vẫn đã chạy | Chỉ dùng clear để tạo mốc quan sát |
| Cho rằng event được ghi nhận tức listener đã hoàn tất | Async listener có thể còn chạy | Assert side effect và chờ có timeout |
| Cho rằng event được ghi tức DB đã commit | Event có thể phát trong transaction bị rollback | Kiểm tra after-commit và transaction thật |
| Test `ApplicationEvents` bên ngoài JUnit method lifecycle | Context ghi nhận chưa tồn tại | Dùng đúng lifecycle |
| Dùng listener ghi nhận event để test broker ngoài JVM | Không quan sát message ngoài ApplicationContext | Dùng broker integration test |
| Giả định tất cả events async ở pool đều được capture | Thread propagation không mặc định | Phân biệt publisher thread và background executor |

**Ghi nhớ:** `ApplicationEventsTestExecutionListener` là hạ tầng Spring TestContext **được đăng ký mặc định** để hỗ trợ `@RecordApplicationEvents`; nó cho phép kiểm thử những event mà ứng dụng **đã publish** bằng `ApplicationEvents.stream(...)`. Hãy lấy `ApplicationEvents` trong lifecycle của từng test, lọc theo kiểu domain event, dùng `clear()` trước action khi cần và kiểm thử riêng commit/async side effects.

## Tài liệu chính thức

- Spring Framework — TestContext **Application Events**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html
- Spring Framework — `@RecordApplicationEvents`: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-recordapplicationevents.html
- Spring Framework 6.2 — `ApplicationEventsTestExecutionListener` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/event/ApplicationEventsTestExecutionListener.html
- Spring Framework 6.2 — `ApplicationEvents` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html
- Spring Framework — `TestExecutionListener` configuration: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html
- Spring Framework — Test Execution Events (phân biệt `EventPublishingTestExecutionListener`): https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/test-execution-events.html
