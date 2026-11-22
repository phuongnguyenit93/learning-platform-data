# Kiểm thử trực tiếp ApplicationListener bằng JUnit 5 trong Spring

## 1. Kiểm thử trực tiếp ApplicationListener là gì?

Trong Spring Application Events, một bean có thể triển khai `ApplicationListener<E>` để nhận một loại sự kiện cụ thể. Khi Spring phát sự kiện bằng `ApplicationEventPublisher.publishEvent(...)`, hạ tầng multicaster tìm các listener phù hợp rồi gọi phương thức:

```java
void onApplicationEvent(E event);
```

**Kiểm thử trực tiếp** (*direct unit test*) là tạo một đối tượng listener như một Java object bình thường, tạo event thật, sau đó **tự gọi `listener.onApplicationEvent(event)`**. Bài test không cần khởi động Spring container, không cần database, không cần web server và không cần thực sự publish qua Spring.

Ví dụ tối giản:

```java
ReceiptGateway fake = orderId -> System.out.println(orderId);
ReceiptListener listener = new ReceiptListener(fake);

listener.onApplicationEvent(
        new ReceiptRequestedEvent("test", "ORD-1", true));
```

Đoạn này chỉ minh họa cách gọi; các kiểu `ReceiptGateway`, `ReceiptListener` và `ReceiptRequestedEvent` sẽ được định nghĩa đầy đủ trong ví dụ chạy được ở mục 5.

Điểm cốt lõi: **đang kiểm thử logic của callback**, không phải kiểm thử hạ tầng dispatch của Spring. Việc gọi trực tiếp chứng minh rằng với một event nhất định, listener thực hiện đúng nhánh, gọi đúng dependency, xử lý lỗi đúng yêu cầu; nó **không chứng minh** rằng Spring sẽ tự phát hiện bean và gọi listener khi một event được publish.

## 2. Khi nào nên chọn direct unit test?

Trực tiếp gọi `onApplicationEvent(...)` phù hợp khi listener có logic tương đối độc lập, chẳng hạn:

- Với event `OrderPaidEvent`, gọi dịch vụ gửi biên nhận đúng mã đơn.
- Khi một field cho biết không cần thông báo, bỏ qua side effect.
- Khi dependency ném exception, listener phải truyền lỗi lên hoặc chuyển lỗi sang handler theo hợp đồng.
- Khi event không hợp lệ, xác minh xử lý có chủ đích.
- Khi listener nhận một event hai lần, xác minh việc lặp lại sẽ gây gì và liệu có cần idempotency.

Ưu điểm: test nhanh, không phụ thuộc khởi động context hay profile, không mở kết nối thật, dữ liệu kiểm soát được và lỗi assertion có vị trí rõ ràng.

Tuy vậy, direct test **không bao trùm**:

| Câu hỏi | Direct call | Cần kiểm tra thêm |
| --- | --- | --- |
| Logic của `onApplicationEvent` đúng? | Có | Unit test với fake/mock |
| Truyền đúng field cho dependency? | Có | Assertion trên lời gọi |
| Exception được callback xử lý đúng? | Có | `assertThrows` và state |
| Spring tìm thấy listener bean? | Không | Integration test có context |
| `publishEvent(...)` có chọn đúng listener theo kiểu? | Không | Integration test dispatch |
| `@Order` có tác dụng khi có nhiều listener? | Không | Test thông qua multicaster |
| `@Async` chạy trên executor? | Không | Test qua Spring proxy và executor |
| `@TransactionalEventListener` đợi commit? | Không | Test với transaction thật |
| Lỗi từ listener ảnh hưởng publisher thế nào? | Không đầy đủ | Test qua `ApplicationEventPublisher` |
| Event gửi ra broker có được lưu/retry? | Không | Test integration/outbox/broker |

Nên dùng **hai tầng kiểm thử**: nhiều unit test trực tiếp, cộng một số integration test có context để xác nhận wiring/dispatch và những behavior phụ thuộc hạ tầng.

## 3. Hiểu đúng ApplicationListener và kiểu event

Trong Spring Framework 6.x, generic interface có dạng:

```java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {

    void onApplicationEvent(E event);
}
```

Tức là khi triển khai `ApplicationListener<OrderPaidEvent>`, kiểu `OrderPaidEvent` phải **kế thừa `org.springframework.context.ApplicationEvent`**.

Một event class thường có cấu trúc:

```java
public final class OrderPaidEvent extends ApplicationEvent {
    private final String orderId;

    public OrderPaidEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

Đây là **đoạn minh họa**, cần import `ApplicationEvent` và đặt trong file Java tương ứng. `source` là object phát sinh/ngữ cảnh nguồn mà `ApplicationEvent` giữ lại qua `getSource()`; source không được `null`.

Phân biệt ba kiểu listener:

1. **`ApplicationListener<MyEvent>`:** viết phương thức `onApplicationEvent(MyEvent)`; rất phù hợp để gọi trực tiếp trong unit test.
2. **`@EventListener` trên một method bean:** không cần implement `ApplicationListener`; với direct test, có thể gọi method như Java thường, nhưng không kiểm thử cơ chế annotation của Spring.
3. **`ApplicationListener<PayloadApplicationEvent<MyPayload>>`:** dùng khi cần bắt payload POJO được Spring bọc trong `PayloadApplicationEvent`. Có thể gọi trực tiếp bằng wrapper thích hợp, nhưng Spring không tự bọc payload khi ta tự gọi method.

**Không viết** `implements ApplicationListener<MyRecord>` với một record thuần Java nếu `MyRecord` không extends `ApplicationEvent`: lỗi generic bound khi biên dịch. Nếu muốn event record không phụ thuộc framework, dùng `@EventListener` nhận record trực tiếp, hoặc dùng `PayloadApplicationEvent<MyRecord>` tại interface listener.

## 4. Quy trình một unit test trực tiếp

Một test tuân theo **Arrange – Act – Assert**:

1. **Arrange:** dựng fake/mock cho dependency, tạo listener bằng constructor, chuẩn bị event có dữ liệu xác định.
2. **Act:** gọi trực tiếp đúng một lần `listener.onApplicationEvent(event)`, hoặc nhiều lần nếu đang kiểm tra lặp.
3. **Assert:** kiểm tra side effect, số lần gọi, dữ liệu truyền đi, exception và trạng thái cuối.

Điểm thiết kế giúp dễ test là listener không tự tạo dependency bằng `new` và không gọi dịch vụ tĩnh/global tùy tiện. Ưu tiên **constructor injection**:

```java
public ReceiptListener(ReceiptGateway gateway) {
    this.gateway = Objects.requireNonNull(gateway);
}
```

Nhờ vậy, test tạo `ReceiptGateway` giả không có kết nối mạng. Khi triển khai thật, Spring có thể cung cấp một bean implementation của `ReceiptGateway`.

Một listener đơn giản thường có cấu trúc:

```text
ReceiptRequestedEvent
        |
        v
ReceiptListener.onApplicationEvent(event)
        |
        +--> không yêu cầu receipt --> return
        |
        +--> yêu cầu receipt --> ReceiptGateway.sendReceipt(orderId)
                                      |
                                      +--> thành công
                                      +--> ném exception
```

Bài test cần kiểm tra **cả nhánh xảy ra side effect và nhánh bỏ qua**, chứ không chỉ happy path.

## 5. Ví dụ dự án Java 17+ và JUnit 5 chạy được

Ví dụ sử dụng **Spring Framework 6.2.13**, Java 17+, JUnit Jupiter 5.11.4 và Maven. Không yêu cầu Spring Boot. Chính sách nghiệp vụ **giả định trong ví dụ**: nếu một event có `receiptRequired=true`, listener phải gọi gateway gửi biên nhận; nếu `false`, không gọi. Mọi đơn và gateway đều được mô phỏng; không gửi email thật.

### 5.1. Cấu trúc

```text
direct-application-listener-test/
├── pom.xml
├── src/main/java/example/events/
│   ├── ReceiptRequestedEvent.java
│   ├── ReceiptGateway.java
│   └── ReceiptListener.java
└── src/test/java/example/events/
    ├── ReceiptListenerTest.java
    └── ReceiptListenerIntegrationTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>direct-application-listener-test</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
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
```

### 5.3. ReceiptRequestedEvent.java

```java
package example.events;

import org.springframework.context.ApplicationEvent;

public final class ReceiptRequestedEvent extends ApplicationEvent {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final boolean receiptRequired;

    public ReceiptRequestedEvent(
            Object source, String orderId, boolean receiptRequired) {
        super(source);

        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must be present");
        }

        this.orderId = orderId;
        this.receiptRequired = receiptRequired;
    }

    public String getOrderId() {
        return orderId;
    }

    public boolean isReceiptRequired() {
        return receiptRequired;
    }
}
```

Lớp này cố định dữ liệu qua các field `final`, dùng constructor validate mã đơn và kế thừa `ApplicationEvent` để tương thích với `ApplicationListener<ReceiptRequestedEvent>`.

### 5.4. ReceiptGateway.java

```java
package example.events;

public interface ReceiptGateway {
    void sendReceipt(String orderId);
}
```

Đây là **cổng phụ thuộc** (*port*) do listener gọi. Ứng dụng thực có thể triển khai bằng email provider/notification service. Unit test sẽ cung cấp fake trong bộ nhớ để xác minh có gọi hay không, không phát request thật.

### 5.5. ReceiptListener.java

```java
package example.events;

import java.util.Objects;

import org.springframework.context.ApplicationListener;

public final class ReceiptListener
        implements ApplicationListener<ReceiptRequestedEvent> {

    private final ReceiptGateway gateway;

    public ReceiptListener(ReceiptGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway);
    }

    @Override
    public void onApplicationEvent(ReceiptRequestedEvent event) {
        if (!event.isReceiptRequired()) {
            return;
        }

        gateway.sendReceipt(event.getOrderId());
    }
}
```

Không gắn `@Component` cho `ReceiptListener` trong ví dụ này vì unit test sẽ tạo trực tiếp. Integration test ở mục 7 khai báo nó là bean bằng `@Bean`. Hai cách cùng dùng **một** lớp production; không cần thêm logic đặc biệt chỉ để test.

### 5.6. ReceiptListenerTest.java — unit test trực tiếp

```java
package example.events;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReceiptListenerTest {

    // Fake đơn giản, không cần Mockito hoặc Spring TestContext.
    static final class RecordingGateway implements ReceiptGateway {
        final List<String> sentOrderIds = new ArrayList<>();
        int callCount;
        boolean shouldFail;

        @Override
        public void sendReceipt(String orderId) {
            callCount++;

            if (shouldFail) {
                throw new IllegalStateException("provider unavailable");
            }

            sentOrderIds.add(orderId);
        }
    }

    @Test
    void requiredEventInvokesGatewayWithCorrectOrderId() {
        RecordingGateway gateway = new RecordingGateway();
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-101", true);

        listener.onApplicationEvent(event);

        assertEquals(1, gateway.callCount);
        assertEquals(List.of("ORD-101"), gateway.sentOrderIds);
    }

    @Test
    void optionalEventDoesNotCallGateway() {
        RecordingGateway gateway = new RecordingGateway();
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-102", false);

        listener.onApplicationEvent(event);

        assertEquals(0, gateway.callCount);
        assertTrue(gateway.sentOrderIds.isEmpty());
    }

    @Test
    void dependencyFailurePropagatesFromDirectInvocation() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.shouldFail = true;
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-103", true);

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> listener.onApplicationEvent(event));

        assertEquals("provider unavailable", error.getMessage());
        assertEquals(1, gateway.callCount);
        assertTrue(gateway.sentOrderIds.isEmpty());
    }

    @Test
    void callingTwiceCausesTwoGatewayCallsWithoutDeduplication() {
        RecordingGateway gateway = new RecordingGateway();
        ReceiptListener listener = new ReceiptListener(gateway);
        ReceiptRequestedEvent event =
                new ReceiptRequestedEvent(this, "ORD-104", true);

        listener.onApplicationEvent(event);
        listener.onApplicationEvent(event);

        assertEquals(2, gateway.callCount);
        assertEquals(
                List.of("ORD-104", "ORD-104"),
                gateway.sentOrderIds);
    }

    @Test
    void eventRejectsBlankOrderId() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new ReceiptRequestedEvent(this, " ", true));
    }
}
```

Những assertion này chứng minh:

1. **Required:** đúng một lần gọi gateway và đúng mã đơn.
2. **Optional:** listener bỏ qua event, không phát side effect.
3. **Failure:** exception của dependency đi lên caller trực tiếp, không được Spring tự chuyển thành retry hay recovery.
4. **Duplicate call:** listener hiện tại **không có idempotency**; gọi cùng event hai lần thì gửi hai lần. Test này cố ý mô tả hành vi thực, không ngụ ý hành vi đó phù hợp production.
5. **Validation:** event bị từ chối từ constructor khi mã đơn trống.

Tất cả đều là **unit test trực tiếp**: test không gọi `publishEvent(...)`, không khởi động Spring và không cần mock framework.

### 5.7. Chạy bài test

Dùng JDK 17+ và Maven tại thư mục chứa `pom.xml`:

```bash
mvn test
```

Có thể chạy riêng lớp unit test:

```bash
mvn -Dtest=ReceiptListenerTest test
```

Khi tất cả file ví dụ đã được tạo đúng, Maven Surefire sẽ phát hiện **5 test methods** trong `ReceiptListenerTest`. Với cả dự án (có thêm test integration mục 7), tổng cộng **6 test methods**. Một lần chạy thành công kết thúc với `BUILD SUCCESS` và `0 failures / 0 errors`; định dạng dòng báo cáo chi tiết của Surefire có thể thay đổi theo cách chạy.

Không cung cấp một stdout số liệu đo thời gian cố định, vì thời gian chạy, log Maven và đường dẫn local phụ thuộc môi trường. Điều quan trọng là số test được thực thi và các assertion qua được; bài không cần port, DB hoặc API key.

## 6. Kiểm thử exception và hành vi khi callback lỗi

Với direct call, Java xử lý exception như bất kỳ method nào:

```java
assertThrows(
        IllegalStateException.class,
        () -> listener.onApplicationEvent(event));
```

Nếu `gateway.sendReceipt(...)` ném `IllegalStateException` và listener không catch, exception đi lên chính bài test. **Không có Spring multicaster, error handler, retry proxy, transaction interceptor hay async error handler** trong đường gọi trực tiếp này.

Trong runtime thực:

- Nếu dùng multicaster đồng bộ mặc định, exception không được bắt có thể lan tới lời gọi `publishEvent(...)`, tùy cấu hình error handler.
- Nếu dùng multicaster executor, lỗi có thể xuất hiện trên worker thread thay vì publisher.
- Nếu method listener chạy qua `@Async`, exception của method `void` thường không đi ngược về caller; cần handler/metrics/log riêng.
- Nếu listener nằm trong một transaction hoặc có `@TransactionalEventListener`, hành vi rollback/phase không thể kết luận chỉ từ direct call.

**Cần quyết định hợp đồng lỗi** cho listener. Với event chỉ phục vụ telemetry, thất bại có thể không được phép phá nghiệp vụ gốc; với event cần thực thi điều kiện quan trọng, có thể phải làm transaction fail hoặc lưu trạng thái xử lý lại. Direct test chỉ chứng minh code xử lý exception như đã viết, không tự xác nhận chính sách runtime.

### Kiểm thử nhánh recovery (khi có)

Nếu listener có policy:

```java
try {
    gateway.sendReceipt(event.getOrderId());
} catch (TemporaryGatewayException ex) {
    failedJobStore.record(event.getOrderId());
}
```

Đây là **mảnh minh họa**, giả định hai dependency và loại exception tồn tại; không thuộc project chạy ở mục 5. Unit test tương ứng cần xác minh:

- Khi `gateway` thành công, không gọi `failedJobStore`.
- Khi ném đúng `TemporaryGatewayException`, ghi công việc thất bại đúng một lần.
- Khi `failedJobStore` cũng lỗi, đường lỗi cuối đúng theo hợp đồng, không nuốt exception vô điều kiện.

Nếu code dùng `@Retryable` qua Spring AOP, **gọi method trực tiếp trên đối tượng `new` không kiểm thử retry annotation**. Khi ấy, unit test cho logic bên trong method và integration test qua proxy là hai yêu cầu riêng.

## 7. Integration test tối thiểu: xác nhận Spring thật sự dispatch

Một class `ReceiptListener` có thể qua toàn bộ unit test nhưng lại **không được đăng ký thành bean** trong ứng dụng. Để kiểm tra wiring/dispatch, thêm một test riêng dùng `AnnotationConfigApplicationContext`.

File `src/test/java/example/events/ReceiptListenerIntegrationTest.java`:

```java
package example.events;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ReceiptListenerIntegrationTest {

    static final class TestReceiptGateway implements ReceiptGateway {
        final List<String> sentOrderIds = new ArrayList<>();

        @Override
        public void sendReceipt(String orderId) {
            sentOrderIds.add(orderId);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        TestReceiptGateway receiptGateway() {
            return new TestReceiptGateway();
        }

        @Bean
        ReceiptListener receiptListener(
                TestReceiptGateway receiptGateway) {
            return new ReceiptListener(receiptGateway);
        }
    }

    @Test
    void springDispatchesEventToRegisteredApplicationListener() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             TestConfig.class)) {

            context.publishEvent(
                    new ReceiptRequestedEvent(this, "ORD-201", true));

            TestReceiptGateway gateway =
                    context.getBean(TestReceiptGateway.class);

            assertEquals(
                    List.of("ORD-201"),
                    gateway.sentOrderIds);
        }
    }
}
```

**Test này khác direct test như thế nào?**

- Nó tạo context, đọc cấu hình `@Configuration` và đăng ký `ReceiptListener` dưới dạng bean.
- Khi gọi `context.publishEvent(...)`, Spring sử dụng multicaster để tìm bean `ApplicationListener<ReceiptRequestedEvent>` phù hợp.
- Test assertion rằng đúng gateway nhận `ORD-201`.
- Context được đóng nhờ `try-with-resources`, tránh để resource sống sau test.

Integration test bổ sung bằng chứng về **registration và dispatch**, nhưng **không** tự kiểm tra async executor, transaction rollback, bộ nhớ bền vững hay hiệu ứng bên ngoài. Nó vẫn chỉ dùng `spring-context` và JUnit, không cần full Spring Boot.

Một bộ test thực tế có thể cần thêm event không cùng kiểu để kiểm tra filter, nhiều listener để kiểm tra thứ tự, hoặc test với cấu hình multicaster tùy chỉnh của ứng dụng. Những trường hợp đó thuộc tầng integration, không nên nhét vào direct unit test đơn thuần.

## 8. Dùng mock hay fake cho dependency?

Trong ví dụ trên, `RecordingGateway` là **fake**: một implementation nhỏ lưu lời gọi đã nhận. Fake phù hợp khi:

- Interface nhỏ, hành vi đơn giản.
- Muốn hiểu rõ callback đang làm gì và vì sao test pass/fail.
- Muốn tránh kết hợp nhiều annotation/mock infrastructure chỉ để kiểm tra một lời gọi.

Với Mockito, cách viết có thể ngắn hơn:

```java
ReceiptGateway gateway = Mockito.mock(ReceiptGateway.class);
ReceiptListener listener = new ReceiptListener(gateway);

ReceiptRequestedEvent event =
        new ReceiptRequestedEvent(this, "ORD-301", true);
listener.onApplicationEvent(event);

Mockito.verify(gateway)
        .sendReceipt("ORD-301");
```

Đây là **đoạn minh họa**, không nằm trong project Maven ở mục 5 vì project chưa khai báo Mockito. Muốn biên dịch đoạn này phải thêm dependency `org.mockito:mockito-core` scope test và import `org.mockito.Mockito`, hoặc dùng `mockito-junit-jupiter` khi cần tích hợp JUnit.

Đối với nhánh bỏ qua:

```java
Mockito.verifyNoInteractions(gateway);
```

Chọn **một** cách phù hợp với phạm vi test. Không cần Mockito chỉ để khẳng định listener truyền đúng một string khi fake đơn giản đã đủ. Dù dùng mock hay fake, đừng test implementation detail quá chi tiết nếu nó không thuộc hợp đồng nghiệp vụ.

### Không kiểm tra mọi getter vô nghĩa

Ví dụ:

```java
assertEquals("ORD-301", event.getOrderId());
```

Assertion này chỉ kiểm tra getter đơn giản của event, **không chứng minh listener đã dùng mã đơn đó**. Test quan trọng hơn là gateway đã nhận đúng `ORD-301`. Nếu event có validation hoặc chuẩn hóa dữ liệu, test riêng những quy tắc đó có thể hữu ích.

## 9. Testing payload POJO và PayloadApplicationEvent

Không phải mọi Spring event đều là subclass của `ApplicationEvent`. Spring Framework cho phép:

```java
public record PaymentCaptured(String paymentId) {
}
```

Với event là record thuần Java, ứng dụng có thể:

```java
publisher.publishEvent(new PaymentCaptured("PAY-7"));
```

Khi sử dụng cơ chế publish object này, Spring có thể bọc payload thành `PayloadApplicationEvent<PaymentCaptured>` cho hạ tầng listener. Có hai cách đăng ký phổ biến:

**Cách A: @EventListener nhận POJO**

```java
@EventListener
public void on(PaymentCaptured event) {
    // Logic ứng dụng.
}
```

**Cách B: ApplicationListener nhận wrapper**

```java
public final class PaymentCapturedListener
        implements ApplicationListener<
                PayloadApplicationEvent<PaymentCaptured>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<PaymentCaptured> event) {
        PaymentCaptured payload = event.getPayload();
        // Logic ứng dụng.
    }
}
```

Các đoạn này là **minh họa độc lập**, chưa khai báo imports hay bean. Với cách B, khi kiểm thử trực tiếp, tạo wrapper:

```java
var payload = new PaymentCaptured("PAY-7");
var event = new PayloadApplicationEvent<>(this, payload);

listener.onApplicationEvent(event);
```

Cần import `org.springframework.context.PayloadApplicationEvent`, `org.springframework.context.ApplicationListener`, định nghĩa `PaymentCapturedListener` và đăng ký bean nếu muốn Spring dispatch. Không gán trực tiếp `PaymentCaptured` cho method `onApplicationEvent(PayloadApplicationEvent<PaymentCaptured>)` vì sai kiểu.

**Giới hạn:** Direct test này bỏ qua bước Spring bọc object payload và matching generic event type. Nếu muốn chứng minh `publishEvent(payload)` thực sự đến đúng listener, hãy kiểm thử qua context bằng cách publish record thật.

## 10. Kiểm thử thứ tự và nhiều listener

Nếu ứng dụng có hai listener cho cùng event:

```text
OrderPaidEvent
  ├── AuditListener
  └── ReceiptListener
```

Unit test trực tiếp `audit.onApplicationEvent(event)` và `receipt.onApplicationEvent(event)` chỉ chứng minh **logic từng listener**. Nó không nói Spring sẽ dispatch listener nào trước. Khi cần thứ tự, dùng cơ chế ordering do Spring hỗ trợ, rồi kiểm thử qua multicaster.

Đừng cố chứng minh thứ tự bằng cách tự gọi listener theo thứ tự trong test:

```java
audit.onApplicationEvent(event);
receipt.onApplicationEvent(event);
```

Đây là **đoạn minh họa cách test không đầy đủ**: test đã tự ấn định thứ tự nên không hề kiểm tra Spring dispatch. Đặc biệt với async listeners, thứ tự nộp task và thứ tự hoàn thành là hai khái niệm khác nhau; ngay cả khi `@Order` ảnh hưởng thứ tự dispatch, không nên suy luận tất cả handler async hoàn thành theo thứ tự.

Khi dependency giữa listener là yêu cầu nghiệp vụ bắt buộc, thiết kế workflow/orchestrator rõ ràng thay vì chỉ dựa vào thứ tự event listener.

## 11. Unit test có chứng minh rollback và transaction không?

**Không.** Direct call không mở Spring transaction và không gọi transaction interceptor. Ví dụ:

```java
listener.onApplicationEvent(event);
```

Lời gọi này sẽ chạy Java method như bình thường. Nó **không kiểm tra**:

- `@Transactional` có thực sự mở transaction khi chạy qua Spring proxy không.
- Callback `@TransactionalEventListener(AFTER_COMMIT)` có được gọi sau commit hay không.
- Listener có bị bỏ qua khi không có transaction không (mặc định của `@TransactionalEventListener`).
- Khi exception phát sinh, transaction gốc commit hay rollback.
- Khi listener chạy async, transaction của publisher có được truyền sang worker hay không (imperative transaction thường gắn với thread và không tự truyền).

Với `@TransactionalEventListener`, Spring đăng ký callback dựa trên transaction synchronization; test bằng cách gọi trực tiếp phương thức xử lý **bypass hoàn toàn bước đăng ký đó**. Muốn kiểm tra phase phải publish event trong một transaction thật, commit/rollback và assert side effect sau đúng mốc.

Lưu ý khi dùng `@Transactional` trên test: nhiều cấu hình Spring Test sẽ rollback tự động sau test. Một bài test đặt `@Transactional` rồi chờ `AFTER_COMMIT` có thể không quan sát được callback vì **transaction chưa từng commit**. Khi đó dùng `TestTransaction` hoặc cách tạo transaction thật và commit có chủ đích.

Nếu callback sau commit còn cần ghi DB trong transaction mới, thiết kế qua một service có `@Transactional(propagation = Propagation.REQUIRES_NEW)` hoặc `TransactionTemplate` phù hợp; direct test chỉ kiểm tra logic bên trong service, không chứng minh proxy/transaction semantics.

## 12. Unit test có chứng minh @Async hoạt động không?

Cũng **không**. Một method có `@Async` được gọi trực tiếp trên instance thường **không đi qua proxy của Spring**. Do đó có thể thấy method chạy đồng bộ ngay trong thread của test, mặc dù ở runtime có executor.

Ví dụ:

```java
ReceiptListener listener = new ReceiptListener(fake);
listener.onApplicationEvent(event); // Chạy trực tiếp trên test thread.
```

Với listener async thực, test integration nên:

1. Tạo context có `@EnableAsync` và executor riêng.
2. Publish event qua `ApplicationEventPublisher`.
3. Dùng `CountDownLatch`, `CompletableFuture` hoặc polling có timeout để chờ công việc hoàn thành.
4. Kiểm tra thread/executor phù hợp khi đó là một phần yêu cầu.
5. Assert **kết quả** và exception handling, không chỉ việc task đã được submit.

Tránh `Thread.sleep(100)` rồi giả định handler chắc chắn hoàn thành: trong CI bận, test kiểu đó không ổn định. Cũng không yêu cầu callback phải chạy trên thread khác trong mọi executor configuration: executor đồng bộ hay fallback/rejection policy có thể thay đổi hành vi.

## 13. Chọn test data và assertion tốt

### Test tên sự kiện và dữ liệu đúng nghiệp vụ

Event nên chứa dữ liệu rõ ràng, và test dùng ID phân biệt như `ORD-101`, `ORD-102` thay vì mọi test đều là `id`. Không phụ thuộc vào thời gian hiện tại hoặc random khi không cần.

Nếu event có timestamp, dùng `Clock.fixed(...)` hoặc giá trị thời gian cố định để assertion ổn định; nếu có UUID, tạo UUID xác định trong fixture. Dữ liệu nhạy cảm không nên được sao chép nguyên văn vào test snapshot công khai.

### Kiểm tra "không làm gì" là kết quả có giá trị

Trong nhiều use case, quan trọng nhất là listener **không** gọi side effect khi điều kiện không hợp lệ. Với fake, kiểm tra `callCount == 0` và danh sách lời gọi rỗng. Với mock, dùng `verifyNoInteractions(...)` hoặc `never()` đúng scope.

### Kiểm tra idempotency phải theo hợp đồng

Trong ví dụ mục 5, test gọi cùng event hai lần và kỳ vọng hai lần gửi. Đó là mô tả **hành vi hiện tại**, chưa phải yêu cầu production. Nếu nghiệp vụ cần mỗi event chỉ thực thi một lần, triển khai idempotency tại adapter/service bằng `eventId`/unique key hoặc transaction phù hợp rồi **đổi test** để kỳ vọng một side effect.

Một biến `boolean` trong listener đủ cho demo một instance nhưng **không** bảo vệ nhiều instance, restart hay consumer retry. Với event quan trọng, cần sổ dedup bền vững hoặc downstream idempotency.

### Đừng test chỉ bằng "không ném exception"

Test như sau quá yếu:

```java
assertDoesNotThrow(() -> listener.onApplicationEvent(event));
```

Nó có thể pass ngay cả khi listener vô tình không gọi gateway. Cần assertion trên output hoặc interaction thực sự. Có thể kết hợp `assertDoesNotThrow` với các assertion khác nhưng đừng xem nó là bằng chứng đầy đủ.

## 14. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Nghĩ direct test đã kiểm tra event dispatch.** Gọi method thủ công không kiểm chứng bean registration, event type matching hoặc multicaster. Bổ sung integration test ngắn với context.

**Lỗi 2 — Tạo listener từ context cho mọi unit test.** Làm test chậm, phụ thuộc cấu hình rộng và khó cô lập logic. Với phần lớn nhánh xử lý, tạo listener trực tiếp với fake/mock.

**Lỗi 3 — Không inject dependency, tự `new` HTTP client bên trong listener.** Test phải gọi mạng thật hoặc hack global state. Tách port/interface, inject qua constructor.

**Lỗi 4 — Mock luôn chính listener.** Nếu method của listener bị mock, callback thật không chạy; test chỉ xác minh hành vi được lập trình trong mock. Mock các dependency, gọi listener thật.

**Lỗi 5 — Dùng record POJO làm generic của `ApplicationListener<E>`.** Generic E phải extends `ApplicationEvent`. Dùng subclass event, `PayloadApplicationEvent<Payload>` hoặc `@EventListener`.

**Lỗi 6 — Chỉ test nhánh thành công.** Bỏ qua event, dữ liệu không hợp lệ, exception và retry/recovery có thể chứa lỗi chính. Kiểm tra theo bảng quyết định.

**Lỗi 7 — Không assert lời gọi side effect.** Một test chỉ kiểm tra rằng không ném lỗi không đủ phát hiện gateway không bao giờ được gọi.

**Lỗi 8 — Kỳ vọng `@Async` hoặc `@Transactional` có hiệu lực khi gọi `new` listener.** Annotation phụ thuộc hạ tầng/proxy/transaction thật; cần test integration tương ứng.

**Lỗi 9 — Dùng thứ tự gọi trực tiếp để chứng minh `@Order`.** Test thủ công không chạy qua multicaster. Kiểm tra thứ tự bằng event publisher khi cần.

**Lỗi 10 — Dựa vào sleep và stdout.** Test dễ flaky và khó khẳng định side effect. Dùng fake/mock, latch có timeout và assertion có ý nghĩa.

**Lỗi 11 — Coi một lời gọi là bằng chứng listener idempotent.** Khi broker hay retry giao lại event, cùng callback có thể chạy lại. Test explicitly duplicate delivery và thiết kế dedup khi nghiệp vụ yêu cầu.

**Lỗi 12 — Test phụ thuộc toàn bộ DB/email.** Một unit test trực tiếp không cần resource ngoài; dùng fake. Đưa transaction, broker, persistence và network contracts sang các tầng integration/contract test riêng.

## 15. Checklist trước khi hoàn thành bài test

1. Listener có triển khai đúng `ApplicationListener<E extends ApplicationEvent>` không?
2. Tên test có diễn tả **hành vi** thay vì implementation detail?
3. Dữ liệu event/source đã cố định, validation được kiểm tra nếu cần?
4. Test có tạo listener thật và inject fake/mock dependency thay vì gọi hạ tầng thật?
5. Có assertion về **số lần gọi, tham số, kết quả** cho nhánh thành công?
6. Có assertion nhánh bỏ qua và các failure path quan trọng?
7. Khi có duplicate event, kỳ vọng idempotency/side effect đã được định nghĩa chưa?
8. Có phân biệt **direct test** với **integration test dispatch** rõ ràng?
9. Nếu dùng `@Async`, `@Retryable`, `@TransactionalEventListener`, đã có test qua Spring infrastructure cho behavior đó chưa?
10. Có tránh dựa vào thứ tự test, thread name cố định, timeout tùy tiện và log như assertion chính?
11. Có đóng context/resource trong integration test để tránh ảnh hưởng bài test khác không?
12. Một lần `mvn test` có chạy đúng các test dự định, không còn test bị skip hoặc phụ thuộc vào môi trường ngoài không?

**Kết luận:** Kiểm thử trực tiếp `ApplicationListener` là cách nhanh và tin cậy để xác nhận **logic của handler**: tạo listener thật, đưa event thật vào `onApplicationEvent(...)`, quan sát dependency bằng fake/mock và assert cả thành công lẫn thất bại. Nhưng vì nó bỏ qua container, cần thêm integration test khi muốn chứng minh Spring tự đăng ký listener, dispatch đúng kiểu, xử lý async, transaction hoặc ordering.

## Tài liệu tham khảo

- [Spring Framework API — ApplicationListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationListener.html): generic bound, callback và hợp đồng listener.
- [Spring Framework API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): publish event trong ApplicationContext.
- [Spring Framework API — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/PayloadApplicationEvent.html): wrapper cho payload POJO.
- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): listener, annotation, event multicaster và xử lý sự kiện.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): `@Test`, assertions và thực thi test.
- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): tích hợp Spring context khi logic unit test không đủ.
