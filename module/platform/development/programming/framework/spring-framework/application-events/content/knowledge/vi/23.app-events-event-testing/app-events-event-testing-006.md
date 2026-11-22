# Tiêm ApplicationEvents vào test để kiểm thử Spring Framework Application Events

## 1. Vấn đề: làm sao khẳng định application event đã được phát?

Trong ứng dụng Spring, một service có thể phát sự kiện bằng `ApplicationEventPublisher.publishEvent(...)` để các `@EventListener` hoặc `ApplicationListener` xử lý. Khi viết test, ta thường muốn kiểm tra **đúng loại sự kiện, đúng payload và đúng số lần phát** mà không cần tự chế một event bus giả hay phụ thuộc vào việc đọc console.

Ví dụ, khi tiếp nhận đơn hàng:

~~~java
public record OrderSubmitted(String orderId) {}

@Service
public class OrderService {
    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void submit(String orderId) {
        // Thực hiện xử lý nghiệp vụ...
        publisher.publishEvent(new OrderSubmitted(orderId));
    }
}
~~~

Đây là đoạn **minh họa tích hợp**, không phải chương trình độc lập. Một test có thể hỏi:

- `OrderSubmitted` có thật sự được publish không?
- Nó mang đúng `orderId` không?
- Sau một lệnh submit, có đúng **một** `OrderSubmitted` hay bị phát trùng?
- Nếu validation thất bại trước publication, có còn event nào được phát không?
- Nếu listener tạo ra event con, event con có được publish và được ghi nhận không?
- Nếu listener chạy sau commit, test đã thực sự commit chưa?

Spring TestContext Framework cung cấp sẵn giải pháp: **`@RecordApplicationEvents` kết hợp với `ApplicationEvents`** trong module `spring-test`. Công cụ này ghi nhận các application events được publish vào `ApplicationContext` trong vòng đời **từng test method**, rồi cho phép truy vấn chúng bằng `Stream`.

Ví dụ cách dùng cốt lõi:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@RecordApplicationEvents
class OrderServiceTest {

    @Autowired
    OrderService service;

    @Test
    void shouldPublishOrderSubmitted(ApplicationEvents events) {
        service.submit("ORD-257");

        long count = events.stream(OrderSubmitted.class).count();
        assertEquals(1L, count);
    }
}
~~~

Đây là **đoạn phác thảo**, cần `OrderTestConfig`, imports và JUnit dependencies. Ví dụ hoàn chỉnh chạy được xuất hiện ở mục 6.

**Nhớ ngay:** `ApplicationEvents` trong bài này là **API test-only thuộc `org.springframework.test.context.event`**, không phải `ApplicationEventPublisher` dùng để phát sự kiện trong production.

## 2. Các thành phần tham gia

| Thành phần | Package | Trách nhiệm |
|---|---|---|
| `ApplicationEventPublisher` | `org.springframework.context` | Phát một event/payload vào Spring context |
| `@EventListener` | `org.springframework.context.event` | Đánh dấu phương thức nhận một kiểu event |
| `ApplicationEvents` | `org.springframework.test.context.event` | Truy vấn các event **đã ghi trong test hiện tại** |
| `@RecordApplicationEvents` | `org.springframework.test.context.event` | Bật tính năng ghi nhận event cho test class |
| `ApplicationEventsTestExecutionListener` | `org.springframework.test.context.event` | Quản lý việc tạo/đăng ký collector theo vòng đời test |
| `SpringExtension` | `org.springframework.test.context.junit.jupiter` | Cầu nối Spring TestContext với JUnit Jupiter |
| `@SpringJUnitConfig` | `org.springframework.test.context.junit.jupiter` | Kết hợp SpringExtension và cấu hình context test |
| `@SpringBootTest` | `org.springframework.boot.test.context` | Khởi động Spring Boot test context nếu ứng dụng dùng Boot |

Khả năng ghi event đã có trong Spring Framework từ **5.3.3**, nên không bắt buộc dùng Spring Boot. Trong Spring Framework 6.2, có thể dùng trực tiếp `spring-context`, `spring-test` và JUnit Jupiter.

Sơ đồ quan hệ:

~~~text
JUnit Jupiter @Test
    |
    +-- SpringExtension + Spring TestContext
    |       |
    |       +-- @RecordApplicationEvents
    |       +-- ApplicationEventsTestExecutionListener
    |               |
    |               +-- collector dành cho test method hiện tại
    |
    +-- gọi OrderService.submit("ORD-257")
    |       |
    |       +-- ApplicationEventPublisher.publishEvent(OrderSubmitted)
    |                  |
    |                  +-- ApplicationContext dispatch events
    |                  +-- các @EventListener xử lý (tùy config)
    |                  +-- collector test ghi event
    |
    +-- assert events.stream(OrderSubmitted.class)
    |
    +-- kết thúc test -> collector không còn là lịch sử global
~~~

**Lưu ý:** thứ tự gọi listener sản xuất và listener ghi nhận test không phải một contract nghiệp vụ cần dựa vào. Khi kiểm thử listener exception, async hoặc transaction, phải hiểu trạng thái cuối cùng thay vì suy rằng cứ gọi `publishEvent` là mọi listener đã xử lý thành công.

## 3. Ba bước tối thiểu để inject ApplicationEvents

### Bước 1: Tích hợp với Spring TestContext

Với JUnit Jupiter, dùng:

~~~java
@SpringJUnitConfig(classes = MyConfig.class)
class MyTest {
    // ...
}
~~~

`@SpringJUnitConfig` là annotation tiện lợi kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. Trong ứng dụng Spring Boot, có thể dùng `@SpringBootTest` để tạo context, nhưng **`@RecordApplicationEvents` vẫn là annotation của `spring-test`**, không phải một cơ chế ghi event riêng do Boot phát minh.

### Bước 2: Bật recording trên test class

~~~java
@RecordApplicationEvents
@SpringJUnitConfig(classes = MyConfig.class)
class MyTest {
}
~~~

Annotation **`@RecordApplicationEvents`** áp dụng ở cấp **lớp test** hoặc là meta-annotation. Nó yêu cầu Spring TestContext ghi các application events phát trong quá trình thực thi từng test.

`ApplicationEventsTestExecutionListener` được đăng ký **mặc định** khi dùng tập test listeners mặc định. Nếu tự khai báo `@TestExecutionListeners` thay thế toàn bộ danh sách, có thể vô tình bỏ listener này: khi đó recording không hoạt động như mong đợi.

### Bước 3: Lấy ApplicationEvents trong test

**Cách nên dùng với JUnit Jupiter: parameter injection**

~~~java
@Test
void capturesEvent(ApplicationEvents events) {
    // events tồn tại trong phạm vi method test đang chạy.
}
~~~

Spring cũng hỗ trợ tham số ở `@BeforeEach` và `@AfterEach`:

~~~java
@BeforeEach
void resetEvents(ApplicationEvents events) {
    events.clear();
}
~~~

**Cách thay thế: field injection**

~~~java
@Autowired
ApplicationEvents events;
~~~

Dùng trường khi muốn tham chiếu đối tượng từ nhiều test/lifecycle methods mà không cần lặp tham số, nhưng phải hiểu dữ liệu được quản lý theo **từng lần chạy test method**, chứ không phải một kho tích lũy xuyên suốt cả class.

**Không tiêm vào constructor của test class:**

~~~java
// Không làm theo: @RecordApplicationEvents chưa bảo đảm
// ApplicationEvents sẵn sàng trong test constructor.
class MyTest {
    MyTest(ApplicationEvents events) {
    }
}
~~~

Đây là **phản ví dụ có chủ đích**. Spring reference nêu rõ `ApplicationEvents` là một *resolvable dependency* gắn với vòng đời test method nên không truy cập được ngoài phạm vi đó và **không thể `@Autowired` vào constructor của test class**.

## 4. ApplicationEvents API: stream, stream(Class) và clear

API cốt lõi nằm ở:

~~~java
import org.springframework.test.context.event.ApplicationEvents;
~~~

Ba phương thức quan trọng:

| Method | Kết quả | Khi nào sử dụng |
|---|---|---|
| `stream()` | `Stream<ApplicationEvent>` của toàn bộ recorded events | Kiểm tra envelope hoặc lọc nhiều event của Spring |
| `stream(Class<T> type)` | `Stream<T>` của event **hoặc payload** theo kiểu `T` | Khẳng định loại event nghiệp vụ; nên dùng mặc định |
| `clear()` | Xóa nội dung collector của test hiện tại | Loại các event setup hoặc chia pha assert trong cùng test |

Ví dụ:

~~~java
long submittedCount = events.stream(OrderSubmitted.class).count();

boolean includesOrder = events.stream(OrderSubmitted.class)
    .anyMatch(e -> e.orderId().equals("ORD-257"));

List<String> ids = events.stream(OrderSubmitted.class)
    .map(OrderSubmitted::orderId)
    .toList();

events.clear();
~~~

Đây là các đoạn tích hợp: cần record `OrderSubmitted`, biến `events` và `java.util.List`. `Stream` của Java là **single-use**; gọi terminal operation như `count()` rồi muốn query tiếp thì **gọi lại `events.stream(...)`**, không tái sử dụng một stream đã tiêu thụ.

### Vì sao stream(Class) vẫn dùng được với POJO payload?

Spring cho phép `publishEvent(Object)` nhận một object **không kế thừa `ApplicationEvent`**, ví dụ Java record:

~~~java
public record OrderSubmitted(String orderId) {}

publisher.publishEvent(new OrderSubmitted("ORD-257"));
~~~

Spring có thể đóng gói object này trong `PayloadApplicationEvent` để truyền qua hệ thống. `ApplicationEvents.stream(OrderSubmitted.class)` vẫn trả về các **payload `OrderSubmitted`**, không bắt người viết test phải cast envelope.

Nếu cần kiểm tra chính `PayloadApplicationEvent`:

~~~java
events.stream()
    .filter(e -> e instanceof PayloadApplicationEvent<?>)
    .forEach(e -> {
        // Quan sát envelope khi thực sự cần.
    });
~~~

Đây là **mã minh họa** với import `org.springframework.context.PayloadApplicationEvent`. Trong phần lớn test nghiệp vụ, kiểm tra payload theo kiểu cụ thể giúp code rõ hơn và ít phụ thuộc vào envelope internals.

### clear() không làm những việc gì?

`events.clear()` chỉ **xóa lịch sử quan sát được trong test collector**. Nó **không**:

- Hủy event đã được phát.
- Đảo ngược side effect của `@EventListener`.
- Rollback transaction.
- Xóa message khỏi broker.
- Hủy công việc async đang chạy.
- Reset state của singleton bean hoặc database.

Nếu test cần kiểm soát trạng thái nghiệp vụ, phải reset repository/mock/fixture riêng. `clear()` chỉ giúp phân biệt các event đã ghi trước/sau một mốc trong test.

## 5. Tại sao mỗi test nên sử dụng collector riêng?

Spring có thể **cache ApplicationContext** để nhiều test dùng lại cùng một context, nhưng `ApplicationEvents` không có nghĩa là log tích lũy từ lúc context được tạo đến khi JVM tắt. Spring TestContext quản lý nó theo vòng đời **một test method**.

Các lợi ích:

- Tránh test A phải biết test B trước đó phát bao nhiêu event.
- Có thể test nhiều luồng nghiệp vụ với assert độc lập.
- Khi dùng tham số method, người đọc biết collector thuộc test hiện tại.
- Đỡ phải tự đăng ký một listener global và tháo nó sau mỗi test.

Nhưng cần hiểu “cùng một test” không có nghĩa “chỉ có event do dòng service cần kiểm tra phát ra”. Một số `@BeforeEach`, helper, setup method hoặc TestContext listeners có thể publish event trong lúc test hoạt động.

**Thực hành an toàn:**

1. Lọc theo **event type nghiệp vụ**, ví dụ `OrderSubmitted.class`.
2. Dùng `events.clear()` trong `@BeforeEach` nếu cần bỏ event của setup.
3. Với test nhiều bước, có thể `clear()` giữa các bước khi muốn assert riêng từng giai đoạn.
4. Không assert số lượng của **tất cả** event qua `events.stream().count()` trừ khi thật sự kiểm soát được mọi event của context.
5. Không phụ thuộc thứ tự thực thi các test method để nhận một danh sách sự kiện mong đợi.

## 6. Ví dụ hoàn chỉnh chạy được: Java 17, Spring Framework 6.2 và JUnit Jupiter

Ví dụ này dùng:

- Java **17+**, Maven.
- `spring-context` và `spring-test` phiên bản **6.2.8**.
- JUnit Jupiter **5.12.2**, Maven Surefire **3.5.3**.
- Không cần Spring Boot, database, web server hoặc message broker.

Ứng dụng nhỏ có ba loại hành vi:

1. `OrderService.submit(...)` validate ID rồi phát `OrderSubmitted`.
2. `OrderFollowUpListener` nhận `OrderSubmitted` và trả về một `OrderAcknowledged`; Spring phát tiếp event này thông qua cơ chế return-value của listener đồng bộ.
3. Test được inject `ApplicationEvents` để chứng minh cả **event gốc và event phát tiếp** đã xuất hiện; test khác chứng minh `clear()` và nhánh validation không phát event.

### Cấu trúc dự án

~~~text
application-events-test/
├── pom.xml
└── src/test/java/demo/ApplicationEventsInjectionTest.java
~~~

Không có mã production ngoài thư mục `src/test` vì ví dụ chủ ý mô tả cấu hình tối thiểu cho bài kiểm thử event. Trong dự án thật, chuyển các service/event sang `src/main/java` và giữ test trong `src/test/java`.

### pom.xml

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
~~~

### src/test/java/demo/ApplicationEventsInjectionTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = ApplicationEventsInjectionTest.Config.class)
@RecordApplicationEvents
class ApplicationEventsInjectionTest {

    @Autowired
    OrderService service;

    // Cách 1: field injection, cũng được Spring TestContext hỗ trợ.
    @Autowired
    ApplicationEvents fieldEvents;

    // Cách 2: lifecycle parameter injection.
    @BeforeEach
    void resetRecordedEvents(ApplicationEvents events) {
        events.clear();
    }

    @Test
    void methodParameterReceivesPayloadAndFollowUp(ApplicationEvents events) {
        service.submit("ORD-257");

        assertEquals(1L, events.stream(OrderSubmitted.class).count());
        assertEquals(
            List.of("ORD-257"),
            events.stream(OrderSubmitted.class)
                .map(OrderSubmitted::orderId)
                .toList()
        );

        // Event thứ hai do một @EventListener đồng bộ trả về.
        assertEquals(1L, events.stream(OrderAcknowledged.class).count());
        OrderAcknowledged ack = events.stream(OrderAcknowledged.class)
            .findFirst()
            .orElseThrow();
        assertEquals("ORD-257", ack.orderId());
        assertEquals("ACCEPTED", ack.status());
    }

    @Test
    void autowiredFieldCanBeUsedAndCleared() {
        service.submit("ORD-258");

        assertTrue(
            fieldEvents.stream(OrderSubmitted.class)
                .anyMatch(e -> e.orderId().equals("ORD-258"))
        );
        assertEquals(1L, fieldEvents.stream(OrderAcknowledged.class).count());

        fieldEvents.clear();
        assertEquals(0L, fieldEvents.stream(OrderSubmitted.class).count());
        assertEquals(0L, fieldEvents.stream(OrderAcknowledged.class).count());
    }

    @Test
    void rejectedCommandPublishesNoOrderEvent(ApplicationEvents events) {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.submit(" ")
        );

        assertEquals(0L, events.stream(OrderSubmitted.class).count());
        assertEquals(0L, events.stream(OrderAcknowledged.class).count());
    }

    public record OrderSubmitted(String orderId) {
    }

    public record OrderAcknowledged(String orderId, String status) {
    }

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(String orderId) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException("orderId is blank");
            }
            publisher.publishEvent(new OrderSubmitted(orderId));
        }
    }

    public static final class OrderFollowUpListener {
        @EventListener
        public OrderAcknowledged acknowledge(OrderSubmitted event) {
            return new OrderAcknowledged(event.orderId(), "ACCEPTED");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public OrderFollowUpListener orderFollowUpListener() {
            return new OrderFollowUpListener();
        }
    }
}
~~~

### Chạy và xác nhận

Đứng tại thư mục `application-events-test`:

~~~bash
mvn test
~~~

Khi dependencies được tải và test chạy thành công, kết quả cần kiểm trong báo cáo Maven Surefire:

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là **hai dòng kết quả trọng tâm cần đạt**, không cam kết toàn bộ log của Maven giống nhau giữa các môi trường. Chi tiết test report nằm trong thư mục `target/surefire-reports/` sau khi chạy.

### Vì sao bộ test này có ý nghĩa?

**Test 1 — parameter injection:**

- `SpringExtension` cung cấp `ApplicationEvents` cho **chính test method**.
- `OrderService.submit("ORD-257")` publish một payload `OrderSubmitted`.
- `OrderFollowUpListener` nhận event, trả một `OrderAcknowledged`; Spring phát tiếp object trả về.
- Collector ghi nhận cả hai loại event. Test kiểm tra **số lượng lẫn nội dung**.

**Test 2 — field injection và clear:**

- `@Autowired ApplicationEvents fieldEvents` cung cấp cách dùng thay thế.
- Test xác nhận sự kiện với ID `ORD-258`, rồi gọi `fieldEvents.clear()`.
- Sau `clear()`, collection test không còn sự kiện. Việc service đã phát hoặc listener đã chạy **không bị đảo ngược**.

**Test 3 — nhánh lỗi trước khi publish:**

- `service.submit(" ")` bị validate và ném exception **trước khi gọi publisher**.
- Test khẳng định không có `OrderSubmitted` và `OrderAcknowledged` được tạo.
- Đây là negative test ổn định, không bị ảnh hưởng bởi câu hỏi exception trong listener có làm collector bỏ lỡ event hay không.

Ba method test độc lập; chúng không dựa vào thứ tự thực thi test class. `@BeforeEach` xóa dữ liệu collector để các assertion có ý nghĩa ngay cả khi setup/framework có phát một số event không liên quan.

## 7. Phân biệt test đã publish event với test listener thật sự thành công

Một trong những ngộ nhận nguy hiểm nhất là:

> “`events.stream(OrderSubmitted.class).count() == 1` nên listener xử lý thành công.”

Không đúng. `ApplicationEvents` ghi các event được **publish** và quan sát trong TestContext, không phải một bảng durable tracking mỗi listener.

Ví dụ:

~~~java
@EventListener
public void handle(OrderSubmitted event) {
    emailGateway.send(event.orderId()); // Có thể throw hoặc timeout.
}
~~~

Nếu chỉ assert `OrderSubmitted` xuất hiện, test chưa chứng minh email đã gửi, hệ thống ngoài đã nhận, hoặc listener đã kết thúc thành công.

Có ba tầng kiểm thử khác nhau:

| Tầng cần chứng minh | Assertion thích hợp |
|---|---|
| Service phát đúng event | `ApplicationEvents.stream(EventType.class)`, payload và count |
| Listener được gọi đúng | Spy/fake collaborator, counter được quản lý trong test, hoặc event con chỉ phát khi listener xử lý |
| Tác dụng nghiệp vụ hoàn thành | Kiểm tra DB/query/API fake/outbox state hoặc acknowledgment thực tế |

Ví dụ test `OrderAcknowledged` ở mục 6 tạo sự kiện tiếp theo từ listener **sau khi phương thức trả về**. Vì thế nó có thêm bằng chứng rằng listener đã chạy tới điểm trả kết quả trong đường xử lý đồng bộ mặc định. Tuy nhiên, nó vẫn không bảo đảm một side effect bên ngoài JVM đã được lưu bền, trừ khi có assertion riêng.

Một test tích hợp tốt có thể kết hợp recorder và fake collaborator, ví dụ xác nhận số lần gọi của email adapter, rồi kiểm tra event độc lập. Đừng thay thế mọi mock hoặc integration assertion chỉ bằng `ApplicationEvents`.

## 8. Field injection, method injection và constructor injection

So sánh rõ để tránh nhầm API của test:

| Vị trí | Hợp lệ? | Ghi chú |
|---|---|---|
| Tham số `@Test` | **Có — khuyến nghị** | Collector gắn với method hiện tại |
| Tham số `@BeforeEach` | **Có** | Hữu ích để `clear()` sau setup |
| Tham số `@AfterEach` | **Có** | Hữu ích để assert sự kiện tại cuối test |
| Trường `@Autowired ApplicationEvents` | **Có** | Được TestContext resolve theo phạm vi method |
| Constructor của test class | **Không** | Test-scoped dependency không có sẵn ở thời điểm khởi tạo test instance |
| Constructor của production singleton bean | **Không dùng** | `ApplicationEvents` là API test-only, không phải dependency production |
| `@BeforeAll`/`@AfterAll` | **Không nên dựa vào** | Nằm ngoài lifecycle của **một test method** |
| Test không dùng Spring TestContext | **Không tự có** | Plain JUnit/Mockito unit test cần chiến lược khác |

Đối với Java/JUnit Jupiter, cú pháp parameter injection rất ngắn:

~~~java
@Test
void createsEvent(ApplicationEvents events) {
    service.submit("ORD-257");
    assertEquals(1L, events.stream(OrderSubmitted.class).count());
}
~~~

Hãy chọn field injection khi test có nhiều phương thức helper/lifecycle cần nhìn collector hiện tại, nhưng không lưu field này vào biến static hoặc sử dụng sau khi test đã hoàn thành.

### Vì sao không nên dùng static ApplicationEvents?

Collector không phải một singleton event store. Nếu lấy một instance rồi giữ vào static field/đưa cho thread sống quá thời gian test, assertions có thể đọc sai lifecycle, test bị rò rỉ dữ liệu hoặc không còn collector hợp lệ. Giữ việc truy cập trong test method và helper đồng bộ phù hợp.

## 9. Tùy chỉnh TestExecutionListeners mà không đánh mất recording

`ApplicationEventsTestExecutionListener` mặc định có sẵn trong bộ listener chuẩn của TestContext. Nhưng cấu hình sau có thể vô tình làm mất nó:

~~~java
@TestExecutionListeners(MySpecialListener.class)
@SpringJUnitConfig(classes = MyConfig.class)
@RecordApplicationEvents
class CustomTest {
}
~~~

Đây là **mã minh họa nguy cơ**: nếu cấu hình mới thay thế danh sách mặc định và không đăng ký `ApplicationEventsTestExecutionListener`, việc recording có thể không hoạt động.

Một cách để giữ các listener mặc định là **merge**:

~~~java
@TestExecutionListeners(
    listeners = MySpecialListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
@RecordApplicationEvents
@SpringJUnitConfig(classes = MyConfig.class)
class CustomTest {
}
~~~

Đây là **đoạn cấu hình**, cần `MySpecialListener` và `MyConfig` do ứng dụng định nghĩa, imports `TestExecutionListeners`/JUnit. Không đưa vào ví dụ runnable ở mục 6 nếu không cần custom execution listener.

Một lựa chọn khác là tự khai báo danh sách đầy đủ và bao gồm `ApplicationEventsTestExecutionListener`, nhưng cách đó dễ bỏ sót các listener khác như dependency injection, transaction hoặc test context setup. Với đa số dự án, **giữ defaults** đơn giản và an toàn nhất.

### ApplicationEventsTestExecutionListener khác EventPublishingTestExecutionListener

Hai loại dễ nhầm vì tên gần nhau:

- `ApplicationEventsTestExecutionListener` quản lý **recorded ApplicationEvents** cho test hiện tại.
- `EventPublishingTestExecutionListener` phát **các sự kiện vòng đời TestContext** như `BeforeTestMethodEvent`, `AfterTestMethodEvent` để các Spring bean khác có thể quan sát.

Một listener phát sự kiện vòng đời test **không thay thế** recorder; hai thành phần giải quyết nhiệm vụ khác nhau. Khi dùng `events.stream()` tổng quát, có thể gặp event framework ngoài event nghiệp vụ, nên lọc theo class cụ thể trong assertion.

## 10. Kiểm thử nội dung event: đừng chỉ đếm

Một test yếu:

~~~java
assertEquals(1L, events.stream(OrderSubmitted.class).count());
~~~

Nó chứng minh có đúng một event kiểu `OrderSubmitted`, nhưng có thể event sai `orderId`, thiếu `version` hoặc phát cho tenant khác.

Test tốt hơn:

~~~java
List<OrderSubmitted> submitted =
    events.stream(OrderSubmitted.class).toList();

assertEquals(1, submitted.size());
assertEquals("ORD-257", submitted.get(0).orderId());
~~~

Đây là đoạn tích hợp; cần import `java.util.List` và assertions của JUnit Jupiter.

Với event chứa nhiều trường, thêm assertion về:

- **Aggregate ID**: entity nào thay đổi?
- **Event ID**: lần publication nào, có ổn định khi retry?
- **Version**: snapshot nào của aggregate, có bị stale không?
- **Occurred-at timestamp**: có hợp lệ/thuộc khoảng chấp nhận được không? Tránh assert đúng một instant nếu do clock runtime tạo ra.
- **Correlation/causation ID**: có giữ quan hệ với command hoặc event cha không?
- **Tenant ID**: có giữ đúng isolation boundary?
- **Các field nghiệp vụ**: số tiền, trạng thái, loại hành động, không chỉ định danh.

Không log toàn bộ PII hoặc secret vào output test để debug. Nếu cần so sánh payload phức tạp, có thể dùng AssertJ recursive comparison hoặc JSON schema test, nhưng hãy giữ test assertion phù hợp với contract event thay vì phụ thuộc mọi chi tiết triển khai.

### Event mutable có thể làm assertion bị lừa

Nếu event payload chứa một entity mutable:

~~~java
OrderEntity order = ...;
publisher.publishEvent(new OrderChanged(order));
order.setStatus("PAID");
~~~

Trong ví dụ này, record/event có thể giữ **cùng tham chiếu OrderEntity**, nên sau đó collector nhìn thấy status đã thay đổi, dù lúc publication status khác. Vì vậy, để test giá trị **tại thời điểm event được phát**, nên dùng payload immutable/snapshot phù hợp. `ApplicationEvents` không tự chụp ảnh sâu mọi object được publish.

## 11. Transaction: recorded event không đồng nghĩa đã commit

Một test có thể quan sát:

~~~java
long published = events.stream(OrderPlaced.class).count();
~~~

nhưng vẫn chưa biết:

- Transaction T1 đã **commit** chưa?
- Có lỗi khiến T1 **rollback** sau khi phát event không?
- `@TransactionalEventListener(AFTER_COMMIT)` đã chạy chưa?
- Một broker/outbox message đã gửi bền chưa?

Hãy phân biệt **publication** và **transaction completion**.

### Bẫy phổ biến: test method @Transactional

Trong Spring Test, phương thức test đánh dấu `@Transactional` thường chạy trong transaction do TestContext quản lý và **rollback ở cuối test**. Nếu service phát event trong transaction đó, `ApplicationEvents` vẫn có thể ghi nhận publication, nhưng listener:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    notification.send(event.orderId());
}
~~~

**không chạy khi test transaction rollback**, vì không có commit thành công. Một assertion chỉ kiểm tra `OrderPlaced` đã publish không chứng minh listener `AFTER_COMMIT` được gọi.

Khi muốn test đúng hành vi hậu commit, chọn một trong hai hướng:

1. Không đánh dấu chính test method là transactional; gọi Spring service có `@Transactional` và để method service kết thúc/commit trước assertion.
2. Trong test có transaction, dùng `TestTransaction` để kết thúc transaction có chủ đích:

~~~java
@Test
@Transactional
void afterCommitShouldRun(ApplicationEvents events) {
    orderService.createOrder("ORD-257");

    assertEquals(1L, events.stream(OrderPlaced.class).count());

    TestTransaction.flagForCommit();
    TestTransaction.end();

    // Tại đây mới assert kết quả callback AFTER_COMMIT
    // qua fake adapter, repository riêng hoặc event con tương ứng.
}
~~~

Đây là **đoạn tích hợp**, không nằm trong Maven demo ở mục 6: cần `spring-tx`, transaction manager, persistence layer, `OrderPlaced`, `orderService`, cấu hình Spring Test transaction và import `org.springframework.test.context.transaction.TestTransaction`. Đừng gọi `TestTransaction` khi không có transaction test đang active.

**Ranh giới tiếp theo:** mặc dù listener đã chạy `AFTER_COMMIT`, side effect hậu commit vẫn có thể thất bại và không rollback T1. Nếu yêu cầu độ bền, cần outbox/queue/idempotency và kiểm thử trạng thái durable đó.

### Reactive transaction

Nếu dùng R2DBC và `ReactiveTransactionManager`, transaction state sống trong Reactor Context. Với Spring Framework 6.1+, transactional event listener reactive cần event mang `TransactionContext` ở source, thường thông qua `TransactionalEventPublisher`. `ApplicationEvents` chỉ ghi các event mà test collector nhìn thấy; nó **không tự tạo reactive transaction**, không subscribe publisher và không buộc một `Mono` đã tạo phải chạy.

Với reactive test, phải **subscribe** (ví dụ `StepVerifier`) rồi mới assert recorded events và transaction outcomes theo đúng đường thực thi. Không lẫn `ApplicationEvents` của test với `TransactionContext` reactive của ứng dụng.

## 12. Async listener và thread khác: kiểm thử thế nào?

Một `@Async @EventListener` có thể chạy trên executor worker trong khi test thread tiếp tục. Vì vậy code sau có thể **race**:

~~~java
service.submit("ORD-257");
assertEquals(1L, events.stream(FollowUpCompleted.class).count());
~~~

Nếu `FollowUpCompleted` được phát từ một worker async, event này có thể chưa xuất hiện khi assert. Có hai vấn đề cần giải quyết:

1. **Hoàn tất:** đợi công việc async có tín hiệu hoàn thành rõ ràng, thay vì `Thread.sleep(...)` với thời gian đoán.
2. **Phạm vi ghi nhận:** `@RecordApplicationEvents` quản lý collector theo test và hỗ trợ events từ test thread cùng các thread con theo contract hiện hành, nhưng **không bảo đảm mọi thread pool có sẵn/reused thread hoặc task kết thúc sau test đều được gắn đúng collector**. Hãy kiểm chứng cơ chế context/ThreadLocal propagation thực tế của executor.

Ví dụ đơn giản đo việc listener đã chạy bằng collaborator:

~~~java
CountDownLatch done = new CountDownLatch(1);

@EventListener
public void on(OrderSubmitted event) {
    try {
        process(event);
    } finally {
        done.countDown();
    }
}

// Trong test:
service.submit("ORD-257");
assertTrue(done.await(3, TimeUnit.SECONDS));
~~~

Đây là **mã minh họa**, cần biến `done` trong một Spring-managed collaborator test, import `CountDownLatch`/`TimeUnit` và phương thức `process` thực. Nếu `@Async` được bật, cần quản lý executor riêng và cấu hình `@EnableAsync`. Không copy đoạn này vào demo đồng bộ mà không bổ sung bean, test state và import.

Nếu mục tiêu là assert **event mới được publish từ thread pool**, không chỉ assert task đã xong, cần một cách đo có thể quan sát được đúng thread/correlation. Có thể dùng fake collaborator/spy để test logic async, integration test với executor phù hợp hoặc trực tiếp cấu hình context propagation hỗ trợ. Đừng cho rằng việc gọi `events.stream(FollowUpCompleted.class)` sẽ luôn thấy event từ bất kỳ thread nào, bất kể timing và ranh giới collector.

### Khi @Async listener ném exception

Exception trong async worker thường không đi ngược về thread phát event; test phải quan sát future/handler hoặc trạng thái ghi nhận của worker. Đừng chỉ assert `OrderSubmitted` đã được publish rồi kết luận listener hoàn tất thành công. Nếu cần chắc chắn công việc sau commit chạy bền vững, `@Async` và recorder test vẫn không thay thế outbox/broker.

## 13. Test event chaining và collection fan-out

Spring cho phép phương thức `@EventListener` **trả về một object** để publish tiếp event mới. Nếu trả về `Collection` hoặc array, từng phần tử được publish như event riêng trong listener đồng bộ.

Ví dụ:

~~~java
@EventListener
public List<NotificationRequested> on(OrderSubmitted event) {
    return List.of(
        new NotificationRequested(event.orderId(), "EMAIL"),
        new NotificationRequested(event.orderId(), "DASHBOARD")
    );
}
~~~

Đây là đoạn tích hợp; `NotificationRequested` cần được định nghĩa và listener cần là bean Spring. Với `ApplicationEvents`, có thể assert:

~~~java
List<String> channels = events.stream(NotificationRequested.class)
    .map(NotificationRequested::channel)
    .toList();

assertEquals(List.of("EMAIL", "DASHBOARD"), channels);
~~~

Trong dispatcher đồng bộ mặc định, với đúng một listener fan-out và `List` có thứ tự, thứ tự event con thường theo thứ tự duyệt danh sách. Nhưng không dùng thứ tự này làm contract end-to-end khi có executor, async và nhiều node. Khi không có yêu cầu thứ tự, kiểm tra tập giá trị và số lượng sẽ vững hơn.

**Khác biệt quan trọng:** `@EventListener` **return List** tạo các publication theo từng phần tử; gọi `publisher.publishEvent(list)` trực tiếp phát **một payload object kiểu List**, không tự đồng nghĩa với nhiều event con. Test bằng `ApplicationEvents` có thể phát hiện sai lầm thiết kế này, vì `stream(NotificationRequested.class)` sẽ không có các item riêng.

## 14. Spring Boot integration test và ApplicationEvents

Nếu dự án dùng Spring Boot, cú pháp test thường gọn như sau:

~~~java
@SpringBootTest
@RecordApplicationEvents
class CheckoutEventsTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void emitsCheckoutCompleted(ApplicationEvents events) {
        events.clear();

        checkoutService.completeCheckout("CHK-257");

        assertEquals(
            1L,
            events.stream(CheckoutCompleted.class).count()
        );
    }
}
~~~

Đây là **mẫu tích hợp**, không phải chương trình chạy độc lập. `CheckoutService` và `CheckoutCompleted` là kiểu ứng dụng phải định nghĩa. Import `@SpringBootTest` từ Spring Boot Test, còn `ApplicationEvents` và `@RecordApplicationEvents` vẫn từ Spring Framework TestContext.

Thêm test dependency phù hợp, thường là `spring-boot-starter-test` với dependency management của Boot; Spring Framework, JUnit và dependency tương thích cần được quản lý cùng phiên bản stack. Không trộn tùy tiện Spring 7.x với starter Spring Boot được xây cho thế hệ khác.

Sự khác nhau chính:

| Spring Framework thuần | Spring Boot |
|---|---|
| `@SpringJUnitConfig(Config.class)` | `@SpringBootTest` (hoặc test slice thích hợp) |
| `spring-test` và JUnit Jupiter | Boot starter test tích hợp Spring TestContext |
| `@RecordApplicationEvents` | **Giữ nguyên annotation này** |
| `ApplicationEvents` parameter/field | **Giữ nguyên API này** |
| `@Bean` cấu hình tối thiểu | Có thể dùng cấu hình ứng dụng thật, nhưng khởi động chậm hơn |

Đừng dùng `@SpringBootTest` nếu chỉ cần kiểm tra một service phát event và có thể cấu hình context nhỏ bằng `@SpringJUnitConfig`; test nhỏ chạy nhanh, ít phụ thuộc và dễ phân tích.

## 15. Đôi khi không cần Spring context: unit test với fake publisher

`ApplicationEvents` thích hợp khi bạn muốn kiểm tra **publication trong một Spring ApplicationContext thật** và cách TestContext ghi nhận event. Nhưng nếu mục tiêu chỉ là test một service có gọi `ApplicationEventPublisher.publishEvent(...)` với payload đúng không, unit test thuần Java có thể nhanh hơn:

~~~java
List<Object> emitted = new ArrayList<>();

ApplicationEventPublisher fakePublisher = emitted::add;

OrderService service = new OrderService(fakePublisher);
service.submit("ORD-257");

assertEquals(1, emitted.size());
assertEquals(
    new OrderSubmitted("ORD-257"),
    emitted.get(0)
);
~~~

Đây là đoạn minh họa (cần `OrderService` constructor, record `OrderSubmitted`, `List`, `ArrayList`, assertions). Không cần `@RecordApplicationEvents`/`SpringExtension` vì không có Spring TestContext. Tuy nhiên, nó **không kiểm thử dispatch `@EventListener`**, không mô phỏng thứ tự listener hoặc transaction phase.

Chọn công cụ theo mục tiêu:

- **Unit test:** kiểm tra logic phát event và payload trong một service, dùng fake/Mockito.
- **Spring integration test:** kiểm tra bean, wiring, event publication, return-value chaining qua `ApplicationEvents`.
- **Transaction integration test:** kiểm tra publish khi commit/rollback, side effect, database thực.
- **System test:** kiểm tra delivery bền vững qua outbox/broker, retries, idempotency.

Càng nhiều ranh giới, càng không thể chỉ dựa vào một `events.stream(...).count()`.

## 16. Các lỗi thường gặp khi inject ApplicationEvents

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
|---|---|---|
| `ApplicationEvents` không inject được | Thiếu `@RecordApplicationEvents` hoặc không dùng Spring TestContext | Thêm annotation + `@SpringJUnitConfig`/`@SpringBootTest` |
| Có `@RecordApplicationEvents` nhưng collector không hoạt động | Custom `@TestExecutionListeners` loại bỏ default listener | Merge defaults hoặc đăng ký `ApplicationEventsTestExecutionListener` |
| Inject vào constructor test thất bại | Dependency tồn tại theo test method, không phải constructor | Dùng parameter trong `@Test`/`@BeforeEach`/`@AfterEach` |
| `stream(OrderSubmitted.class)` rỗng | Service không phát, sai event type/context, xảy ra trước test lifecycle | Kiểm tra publisher, type, bean và thời điểm |
| `stream()` có nhiều event hơn mong đợi | Framework/test setup phát thêm events | Lọc `stream(EventType.class)`, `clear()` khi phù hợp |
| Nhiều event trùng | Service phát nhiều lần hoặc listener tạo event con cùng type | Assert payload/eventId và số lượng đúng, không chỉ boolean |
| Test A bị ảnh hưởng bởi trạng thái B | Chia sẻ DB/singleton/queue state chứ không phải recorder | Reset dependency/fixture, không chỉ gọi `clear()` |
| Test sau commit không thấy listener chạy | Test `@Transactional` mặc định rollback | Commit thật hoặc gọi transactional service ngoài test transaction |
| `@Async` khiến assert thất thường | Chưa đợi worker hoặc context không theo thread | Latch/await và xác minh cách propagation/collector |
| Stream bị `IllegalStateException` đã đóng | Tái sử dụng Java Stream sau terminal operation | Gọi lại `events.stream(...)` |
| Event đã publish nhưng listener thất bại | Recorder không phải báo cáo completion/side effect | Assert collaborator/DB/outbox riêng |
| Event payload trong collector đổi giá trị | Payload chứa object mutable cùng tham chiếu | Dùng event immutable/snapshot |
| Test không có event sau method khác | Collector theo từng method, không lưu toàn bộ JVM | Thiết kế assert trong test hiện tại |
| Plain Mockito test không có `ApplicationEvents` | Không có TestContext infrastructure | Dùng fake publisher hoặc tích hợp Spring TestContext |

## 17. Checklist kiểm tra chất lượng test

Một test ghi nhận event đạt chất lượng khi:

1. Có đúng Spring TestContext integration (`SpringExtension`, `@SpringJUnitConfig` hoặc Boot test).
2. Có `@RecordApplicationEvents` ở class hoặc qua composed annotation.
3. Các `TestExecutionListener` mặc định còn nguyên hoặc được merge đúng.
4. `ApplicationEvents` được inject đúng trong phạm vi method, ưu tiên parameter injection.
5. Kết quả được lọc theo event **nghiệp vụ** bằng `stream(Class)`.
6. Kiểm tra số lượng, ID và field quan trọng, không chỉ “có event”.
7. Tách test publication khỏi test listener side effect và transaction outcome.
8. Có negative test (không được phát event khi điều kiện không đạt).
9. Không dựa vào thứ tự chạy test, log hoặc thời gian sleep tùy ý.
10. Khi async, có completion signal và hiểu giới hạn thread/collector.
11. Khi `AFTER_COMMIT`, transaction test đã commit thật trước assertion.
12. Không đưa `ApplicationEvents` test-only vào production bean hoặc giữ tham chiếu static.
13. Không coi `clear()` là thao tác rollback/tái khởi tạo context.
14. Có chiến lược reset dữ liệu bên ngoài collector nếu context/test dùng chung resource.
15. Test là repeatable trên local/CI và không phụ thuộc vào dữ liệu từ lần chạy trước.

## 18. Câu hỏi ôn tập

**1. ApplicationEvents khác ApplicationEventPublisher thế nào?** `ApplicationEventPublisher` phát event trong ứng dụng; `ApplicationEvents` của `spring-test` cho test truy vấn các event đã được ghi nhận.

**2. Có cần Spring Boot không?** Không. `@RecordApplicationEvents` thuộc Spring Framework TestContext, có thể dùng với `@SpringJUnitConfig`.

**3. Có thể inject ApplicationEvents vào constructor test class không?** Không. Nó gắn với vòng đời từng test method; dùng field hoặc tham số test/lifecycle method.

**4. Nếu chỉ gọi `events.stream().count()` có đủ không?** Thường không vì có các event Spring/TestContext khác. Dùng `events.stream(OrderSubmitted.class)` và kiểm tra payload.

**5. Khi gọi `events.clear()`, event đã gửi sẽ biến mất khỏi hệ thống?** Không. Chỉ bộ nhớ recorded events của collector được xóa.

**6. Khi test method rollback, recorder còn thấy event phát trong transaction không?** Có thể thấy publication đã xảy ra; điều đó không chứng minh transaction commit hoặc `AFTER_COMMIT` chạy.

**7. Test listener async có thể assert ngay sau publish không?** Không nên. Phải đợi hoàn tất, xử lý ngoại lệ và bảo đảm collector thực sự quan sát được thread phát event.

**8. Vì sao `@EventListener` trả về event khác vẫn được ghi?** Spring publish đối tượng trả về như một event mới khi listener đồng bộ kết thúc phù hợp, nên collector có thể quan sát publication tiếp theo.

**9. `ApplicationEvents` có phải durable event store?** Không. Đây là tiện ích ghi nhận event cho phạm vi test, không dùng để replay giữa các lần chạy.

**10. Khi nào fake publisher hợp lý hơn?** Khi chỉ test việc service gọi `publishEvent` với payload đúng và không cần kiểm tra Spring dispatch hay transaction.

## 19. Tổng kết

Để **tiêm `ApplicationEvents` vào Spring test**, dùng `@RecordApplicationEvents` trên test class kết hợp `SpringExtension` (thường qua `@SpringJUnitConfig` hoặc `@SpringBootTest`), rồi nhận `ApplicationEvents` bằng **tham số `@Test`/`@BeforeEach`/`@AfterEach`** hoặc trường `@Autowired`. Ưu tiên tham số method vì collector gắn với vòng đời của từng test.

API `stream(EventType.class)` giúp xác minh loại event, số lần và payload; `clear()` chỉ xóa lịch sử ghi nhận trong test. Hãy phân biệt event **đã được publish** với listener **đã xử lý thành công**, transaction **đã commit**, hoặc message **đã giao bền vững**. Đối với async và transactional listeners, phải kiểm tra đúng completion/transaction phase thay vì kỳ vọng recorder tự xử lý mọi ngữ nghĩa đó.

### Tài liệu chính thức

- [Spring Framework 6.2 Reference — Application Events trong TestContext](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html) — hướng dẫn `@RecordApplicationEvents`, inject method parameter/field, giới hạn constructor.
- [Spring Framework 6.2 Javadoc — ApplicationEvents](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html) — `stream()`, `stream(Class)` và `clear()`.
- [Spring Framework 6.2 Javadoc — RecordApplicationEvents](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html) — vòng đời và scope của recording.
- [Spring Framework 6.2 Javadoc — ApplicationEventsTestExecutionListener](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/test/context/event/ApplicationEventsTestExecutionListener.html) — việc đăng ký collector trong TestContext.
- [Spring Framework 6.2 Reference — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html) — annotation và composed annotation.
- [Spring Framework 6.2 Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — `@TransactionalEventListener`, `AFTER_COMMIT` và rollback.
- [Spring Framework 6.2 Reference — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html) — hạn chế với shared test state.
