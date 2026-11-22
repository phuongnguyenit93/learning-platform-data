# Sai kiểu event hoặc sai generic khi xử lý Spring Application Events

## 1. Bài toán: đã publish nhưng listener không chạy

Trong Spring Framework, nhiều sự cố nghe event bắt nguồn từ việc **kiểu mà publisher thực sự phát ra không khớp với kiểu mà listener đăng ký nhận**. Một số lỗi bị compiler chặn; một số khác chỉ xuất hiện ở runtime, khiến `publishEvent(...)` trả về bình thường nhưng callback không được gọi.

Ví dụ, một service phát record `InvoicePaidPayload`:

```java
publisher.publishEvent(new InvoicePaidPayload("INV-101"));
```

Trong khi listener được viết:

```java
public final class InvoicePaidListener
        implements ApplicationListener<InvoicePaidEvent> {
    @Override
    public void onApplicationEvent(InvoicePaidEvent event) {
        // Chỉ xử lý InvoicePaidEvent, không phải InvoicePaidPayload.
    }
}
```

Hai class có tên và ý nghĩa tương tự **không đồng nghĩa với cùng kiểu Java**. Dù chúng cùng mang mã hóa đơn, Spring không tự suy luận đây là cùng sự kiện để chuyển đổi.

Một nguồn lỗi khó hơn là generic:

```java
@EventListener
public void onStringChanged(ValueChangedEvent<String> event) {
    // Muốn nhận thay đổi kiểu String.
}
```

Tại runtime, Java áp dụng **type erasure**; nếu event không cung cấp thông tin kiểu generic đủ rõ, cơ chế matching có thể không phân biệt được `ValueChangedEvent<String>` và `ValueChangedEvent<Integer>` như người viết kỳ vọng.

Bài học này chỉ ra cách nhận diện vấn đề thuộc **kiểu event, generic bound, wrapper, khả năng resolve generic** hay **hạ tầng đăng ký/dispatch khác**; sau đó tái hiện và sửa bằng ví dụ Spring Framework 6.2 + Java 17 và bài test.

## 2. Sơ đồ chẩn đoán nhanh

```text
publisher.publishEvent(something)
            |
            v
"something" thực sự có kiểu gì?
            |
     +------+------------------+
     |                         |
     v                         v
ApplicationEvent           POJO / record
     |                         |
     v                         v
Giữ kiểu event          Spring có thể bọc bằng
đã khai báo             PayloadApplicationEvent<T>
     |                         |
     +------------+------------+
                  |
                  v
Listener muốn nhận kiểu gì?
  - ApplicationListener<E extends ApplicationEvent>
  - @EventListener method param
  - GenericApplicationListener / điều kiện khác
                  |
                  v
Kiểu/generic runtime có tương thích?
                  |
           +------+------+
           |             |
          CÓ           KHÔNG
           |             |
           v             v
Kiểm tra bean,       Sửa signature,
condition, timing,   wrapper hoặc
async/transaction    generic metadata
```

Cần ghi lại **hai phía** trước khi sửa code:

1. Kiểu Java của object tại điểm publish (bao gồm type parameters có thể đã bị xóa).
2. Kiểu khai báo của listener: interface generic hoặc tham số của phương thức có `@EventListener`.

Đừng thay tất cả kiểu listener thành `ApplicationEvent` hoặc `Object` chỉ để "nghe cho được": cách này có thể nhận quá nhiều event, che giấu lỗi thiết kế và đưa logic xử lý dữ liệu không liên quan vào callback.

## 3. ApplicationListener<E>: generic bound bắt buộc

Spring Framework định nghĩa interface listener theo dạng:

```java
public interface ApplicationListener<E extends ApplicationEvent>
        extends EventListener {
    void onApplicationEvent(E event);
}
```

Ý nghĩa: `E` **phải là kiểu con của `org.springframework.context.ApplicationEvent`**.

### 3.1. Cách đúng với event kế thừa ApplicationEvent

```java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;

public final class InvoicePaidEvent extends ApplicationEvent {
    private final String invoiceId;

    public InvoicePaidEvent(Object source, String invoiceId) {
        super(source);
        this.invoiceId = invoiceId;
    }

    public String getInvoiceId() {
        return invoiceId;
    }
}

public final class InvoicePaidListener
        implements ApplicationListener<InvoicePaidEvent> {
    @Override
    public void onApplicationEvent(InvoicePaidEvent event) {
        System.out.println(event.getInvoiceId());
    }
}
```

Đây là **hai class minh họa về chữ ký**, không phải project demo hoàn chỉnh ở mục 7. Khi đăng ký một instance `InvoicePaidListener` vào Spring context và publish đúng `InvoicePaidEvent`, listener có thể được dispatch.

### 3.2. Cách sai với record thuần Java

```java
record InvoicePaidPayload(String invoiceId) {
}

// KHÔNG BIÊN DỊCH:
class WrongListener
        implements ApplicationListener<InvoicePaidPayload> {
    @Override
    public void onApplicationEvent(InvoicePaidPayload event) {
    }
}
```

Đoạn trên là **anti-pattern cố ý sai**, không đưa vào project chạy được. Compiler báo kiểu tương tự `Type parameter ... is not within its bound; should extend ApplicationEvent` vì `InvoicePaidPayload` không extends `ApplicationEvent`.

Đừng tìm cách bỏ generic để vượt compiler. Sửa theo đúng mục đích:

- Nếu muốn interface `ApplicationListener<InvoicePaidEvent>`, định nghĩa event kế thừa `ApplicationEvent`.
- Nếu muốn giữ record/POJO thuần Java, dùng method `@EventListener` nhận chính record đó.
- Nếu cần interface listener cho POJO, có thể dùng `ApplicationListener<PayloadApplicationEvent<InvoicePaidPayload>>` để nhận wrapper phù hợp; lưu ý khác biệt giữa wrapper và payload.

Đây là **lỗi ở thời gian biên dịch**. Nó không phải một event đã được publish nhưng bị Spring "nuốt mất".

## 4. ApplicationEvent và payload POJO/record không giống nhau

Từ Spring Framework 4.2, publisher chấp nhận event object mà không yêu cầu kế thừa `ApplicationEvent`.

### 4.1. Phát ApplicationEvent truyền thống

```java
publisher.publishEvent(
        new InvoicePaidEvent(this, "INV-101"));
```

Khi đó Spring xử lý event theo class `InvoicePaidEvent`. Một bean `ApplicationListener<InvoicePaidEvent>` hoặc method `@EventListener` nhận class đó là những cách khai báo phù hợp.

### 4.2. Phát payload thuần Java

```java
public record InvoicePaidPayload(String invoiceId) {
}

publisher.publishEvent(new InvoicePaidPayload("INV-102"));
```

Với POJO/record không phải `ApplicationEvent`, Spring dùng `PayloadApplicationEvent` để bọc nội dung phục vụ hạ tầng event. Có thể nhận payload trực tiếp bằng method:

```java
@EventListener
public void onInvoicePaid(InvoicePaidPayload event) {
    System.out.println(event.invoiceId());
}
```

Spring có cơ chế matching payload, nên method `@EventListener` nhận record là hợp lệ. Không phải tự đổi record thành subclass `ApplicationEvent` chỉ để dùng annotation.

Nếu muốn làm việc với wrapper:

```java
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;

public class InvoicePayloadListener
        implements ApplicationListener<
                PayloadApplicationEvent<InvoicePaidPayload>> {

    @Override
    public void onApplicationEvent(
            PayloadApplicationEvent<InvoicePaidPayload> event) {
        InvoicePaidPayload payload = event.getPayload();
        System.out.println(payload.invoiceId());
    }
}
```

Đây là **class minh họa**, cần định nghĩa record `InvoicePaidPayload` và đăng ký class thành bean/instance listener. Với cách này, callback nhận `PayloadApplicationEvent<InvoicePaidPayload>`, **không** phải chính `InvoicePaidPayload`.

### 4.3. Sai đối tượng nguồn và nội dung payload

```java
var event = new PayloadApplicationEvent<>(
        "publisher-source", new InvoicePaidPayload("INV-102"));
```

Trong wrapper:
- `event.getSource()` trả về object nguồn được truyền lúc tạo wrapper.
- `event.getPayload()` trả về record `InvoicePaidPayload`.
- Hai giá trị có thể là các object khác nhau.

Khi `publishEvent(Object)` nhận POJO, Spring tự bọc nó với source thích hợp. Đừng viết listener giả định `getSource()` luôn là payload hoặc ép kiểu source thành class nghiệp vụ mà không kiểm tra hợp đồng.

**Tín hiệu debug quan trọng:** log class của object vừa gọi `publishEvent(...)`, và nếu đang xem wrapper, log thêm `getPayload().getClass()`. Tránh chỉ log tên biến hoặc tên event trong message.

## 5. Khác biệt giữa @EventListener và ApplicationListener

| Cách đăng ký | Chữ ký thường gặp | Event cần có |
| --- | --- | --- |
| Implement interface | `ApplicationListener<InvoicePaidEvent>` | `InvoicePaidEvent extends ApplicationEvent` |
| Method annotation | `@EventListener void on(InvoicePaidEvent e)` | `InvoicePaidEvent` |
| Method annotation | `@EventListener void on(InvoicePaidPayload p)` | Payload record/POJO |
| Interface nhận wrapper | `ApplicationListener<PayloadApplicationEvent<InvoicePaidPayload>>` | Spring wrapper cho payload tương ứng |
| Generic listener nâng cao | `GenericApplicationListener` | Filter theo `ResolvableType` và source type theo cấu hình |

**Một kiểu không tự động tương đương kiểu khác.** `InvoicePaidEvent` và `InvoicePaidPayload` có thể cùng field `invoiceId` nhưng Spring vẫn phân biệt chúng.

Nếu một method được annotate:

```java
@EventListener
public void on(InvoicePaidEvent event) {
    // ...
}
```

... và publisher phát `InvoicePaidPayload`, callback này không phù hợp; đổi method sang `InvoicePaidPayload` hoặc chuyển producer sang phát `InvoicePaidEvent` tùy hợp đồng nghiệp vụ đã thống nhất.

Nếu dùng:

```java
@EventListener({InvoicePaidEvent.class, ContextRefreshedEvent.class})
public void onEither() {
    // Nhiều kiểu event được khai báo qua annotation, method không có param.
}
```

Đây là **đoạn minh họa**, cần import các kiểu liên quan. Khi một method muốn nhận nhiều event type qua attribute của annotation, nên dùng method **không có tham số**, vì không thể đưa hai class không cùng loại vào một tham số có kiểu cụ thể. Nếu muốn phân nhánh theo event và sử dụng dữ liệu của chúng, thường dễ đọc hơn khi tách thành hai method typed riêng.

## 6. Generic type erasure: lỗi âm thầm tại runtime

### 6.1. Vấn đề

Giả sử muốn một event có kiểu payload thay đổi được:

```java
class ValueChangedEvent<T> extends ApplicationEvent {
    private final T value;

    ValueChangedEvent(Object source, T value) {
        super(source);
        this.value = value;
    }

    T getValue() {
        return value;
    }
}
```

Mục tiêu:

```java
@EventListener
public void onText(ValueChangedEvent<String> event) {
    // Chỉ giá trị String.
}

@EventListener
public void onNumber(ValueChangedEvent<Integer> event) {
    // Chỉ giá trị Integer.
}
```

Hai method có generic khác nhau **ở source code**. Nhưng JVM không giữ type argument cụ thể trong instance `new ValueChangedEvent<>("source", "ready")` theo cách có thể suy ra một cách chắc chắn chỉ từ class runtime. Class của instance thường là cùng một `ValueChangedEvent`.

Theo tài liệu Spring, filtering generic hoạt động khi framework **resolve được** tham số generic của event, chẳng hạn từ subclass cụ thể hoặc từ `ResolvableTypeProvider`. Nếu runtime type không cung cấp thông tin đó, filtering có thể không như ý; đừng giả định Spring suy ra `T` chỉ từ cú pháp diamond operator `<>` ở chỗ `new`.

### 6.2. Cách A: subclass cố định generic

```java
class StringValueChangedEvent extends ValueChangedEvent<String> {
    StringValueChangedEvent(Object source, String value) {
        super(source, value);
    }
}
```

Đây là **class minh họa**; giả sử `ValueChangedEvent<T>` đã định nghĩa và constructor/visibility cho phép subclass. Hierarchy của subclass cố định `T = String`, giúp Spring đọc thông tin generic từ khai báo type. Cách này hợp lý khi số loại event ít và mỗi loại có ý nghĩa riêng.

### 6.3. Cách B: ResolvableTypeProvider

Nếu tạo nhiều event cùng class generic, dùng interface `org.springframework.core.ResolvableTypeProvider` để cung cấp thông tin kiểu cho Spring:

```java
@Override
public ResolvableType getResolvableType() {
    return ResolvableType.forClassWithGenerics(
            ValueChangedEvent.class,
            ResolvableType.forInstance(value));
}
```

Đoạn này là **method minh họa** nằm trong class `ValueChangedEvent<T>`; class phải implement `ResolvableTypeProvider` và import `ResolvableType`. Khi `value` là một `String`, type được báo là `ValueChangedEvent<String>`; khi là `Integer`, type được báo là `ValueChangedEvent<Integer>`.

**Giới hạn cần hiểu:**
- `ResolvableType.forInstance(value)` nhìn vào kiểu runtime của giá trị. Với `List<String>` được tạo thành `ArrayList`, type argument `String` có thể vẫn không resolve được chỉ từ instance do erasure.
- Khi value là proxy hoặc object subtype, kiểu runtime có thể khác generic contract kỳ vọng. Nếu cần chính xác, lưu một `ResolvableType`/type token được cung cấp rõ từ constructor.
- Khi value `null`, suy ra kiểu từ instance không được; nên cấm null hoặc truyền metadata generic tường minh.
- Không ép mọi generic event phải dùng provider; nếu generic chỉ phục vụ type safety trong domain và không cần Spring filter theo `T`, một class event bình thường có thể đã đủ.

### 6.4. Phân biệt Java generic với event type runtime

Mặc dù cú pháp:

```java
new ValueChangedEvent<String>("source", "ready")
```

có generic rõ tại compile time, Spring không nhận được nguyên dòng source code này khi dispatch runtime. Thông tin generic phải có một đường đi **đọc được**: class hierarchy, `ResolvableTypeProvider` hoặc cơ chế metadata tương ứng.

Do đó, khi listener `ValueChangedEvent<String>` không chạy, hãy kiểm tra cách event báo `ResolvableType` trước khi bỏ annotation `@EventListener` hoặc đổi event thành kiểu `Object`.

## 7. Dự án chạy được: kiểm tra 4 đường event khác nhau

Project dùng **Java 17+, Spring Framework 6.2.13 và Maven**. Không cần Spring Boot/web/DB; đây là một ví dụ Spring `ApplicationContext` đơn giản. Nó chứng minh:

1. `ApplicationListener<InvoicePaidEvent>` nhận event kế thừa `ApplicationEvent`.
2. `@EventListener` nhận một record thuần Java khi record được publish trực tiếp.
3. Hai `@EventListener` phân biệt `ValueChangedEvent<String>` và `ValueChangedEvent<Integer>` nhờ `ResolvableTypeProvider`.
4. Bài test xác nhận các handler không bị gọi lẫn nhau và một record không liên quan không kích hoạt listener nghiệp vụ.

### 7.1. Cấu trúc thư mục

```text
event-type-diagnostics/
├── pom.xml
└── src/
    ├── main/java/example/events/EventTypeDiagnostics.java
    └── test/java/example/events/EventTypeDiagnosticsTest.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-type-diagnostics</artifactId>
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
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. EventTypeDiagnostics.java

```java
package example.events;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.ResolvableType;
import org.springframework.core.ResolvableTypeProvider;

public class EventTypeDiagnostics {

    // Kiểu truyền thống: một ApplicationEvent thật sự.
    public static final class InvoicePaidEvent extends ApplicationEvent {
        private final String invoiceId;

        public InvoicePaidEvent(Object source, String invoiceId) {
            super(source);
            this.invoiceId = Objects.requireNonNull(invoiceId);
        }

        public String getInvoiceId() {
            return invoiceId;
        }
    }

    // Kiểu payload: record KHÔNG extends ApplicationEvent.
    public record InvoicePaidPayload(String invoiceId) {
    }

    public record UnrelatedPayload(String value) {
    }

    // Generic event: cung cấp runtime ResolvableType cho Spring.
    public static final class ValueChangedEvent<T> extends ApplicationEvent
            implements ResolvableTypeProvider {

        private final T value;

        public ValueChangedEvent(Object source, T value) {
            super(source);
            this.value = Objects.requireNonNull(value);
        }

        public T getValue() {
            return value;
        }

        @Override
        public ResolvableType getResolvableType() {
            return ResolvableType.forClassWithGenerics(
                    ValueChangedEvent.class,
                    ResolvableType.forInstance(value));
        }
    }

    public static final class EventLog {
        private final List<String> messages = new ArrayList<>();

        public void add(String value) {
            messages.add(value);
            System.out.println(value);
        }

        public List<String> snapshot() {
            return List.copyOf(messages);
        }
    }

    public static final class ClassicListener
            implements ApplicationListener<InvoicePaidEvent> {

        private final EventLog log;

        public ClassicListener(EventLog log) {
            this.log = log;
        }

        @Override
        public void onApplicationEvent(InvoicePaidEvent event) {
            log.add("CLASSIC invoice=" + event.getInvoiceId());
        }
    }

    public static final class PayloadHandler {
        private final EventLog log;

        public PayloadHandler(EventLog log) {
            this.log = log;
        }

        @EventListener
        public void onPaid(InvoicePaidPayload event) {
            log.add("PAYLOAD invoice=" + event.invoiceId());
        }
    }

    public static final class GenericHandlers {
        private final EventLog log;

        public GenericHandlers(EventLog log) {
            this.log = log;
        }

        @EventListener
        public void onText(ValueChangedEvent<String> event) {
            log.add("GENERIC string=" + event.getValue());
        }

        @EventListener
        public void onNumber(ValueChangedEvent<Integer> event) {
            log.add("GENERIC integer=" + event.getValue());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExampleConfig {

        @Bean
        EventLog eventLog() {
            return new EventLog();
        }

        @Bean
        ClassicListener classicListener(EventLog log) {
            return new ClassicListener(log);
        }

        @Bean
        PayloadHandler payloadHandler(EventLog log) {
            return new PayloadHandler(log);
        }

        @Bean
        GenericHandlers genericHandlers(EventLog log) {
            return new GenericHandlers(log);
        }
    }

    public static void publishSamples(
            AnnotationConfigApplicationContext context) {
        context.publishEvent(new InvoicePaidEvent("app", "INV-1"));
        context.publishEvent(new InvoicePaidPayload("INV-2"));
        context.publishEvent(new ValueChangedEvent<>("app", "ready"));
        context.publishEvent(new ValueChangedEvent<>("app", 7));
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ExampleConfig.class)) {
            publishSamples(context);
        }
    }
}
```

Chương trình này có hai nhóm listener độc lập về kiểu:

- `ClassicListener` đăng ký qua interface `ApplicationListener<InvoicePaidEvent>`, nên khi publish record `InvoicePaidPayload`, nó không được chọn.
- `PayloadHandler` đăng ký qua `@EventListener`, nhận payload class thực tế dù Spring bọc record trong `PayloadApplicationEvent` nội bộ.
- `GenericHandlers` có hai method `@EventListener` với type argument khác nhau. `ValueChangedEvent.getResolvableType()` trả về type tương ứng với `String` hoặc `Integer`; Spring dùng metadata này khi chọn method.

Một chi tiết thiết kế: `EventLog` chỉ lưu vào `ArrayList` không có đồng bộ. Demo dùng dispatch **đồng bộ trên cùng thread**, nên phù hợp để minh họa. Nếu dùng async/multicaster executor, thay bằng sink thread-safe và kiểm thử có đồng bộ rõ.

### 7.4. Chạy main và stdout

Tại thư mục có `pom.xml`, dùng Maven 3.9+ và JDK 17+:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.EventTypeDiagnostics
```

Các dòng do **chương trình** in ra (không tính log tùy môi trường):

```text
CLASSIC invoice=INV-1
PAYLOAD invoice=INV-2
GENERIC string=ready
GENERIC integer=7
```

Lý do thứ tự như trên: ứng dụng publish lần lượt từng event; cấu hình `AnnotationConfigApplicationContext` ví dụ sử dụng event multicaster đồng bộ mặc định, không có executor hoặc `@Async`. Mỗi event chỉ khớp callback dự kiến nên không có dòng log thừa.

Nếu thấy callback generic nhận sai loại, cần kiểm tra rằng `getResolvableType()` đã đúng và listener khai báo generic tương ứng; không "sửa" bằng cách ép kiểu trong method `onNumber(...)`.

## 8. Integration test tái hiện đường phát và lọc

File `src/test/java/example/events/EventTypeDiagnosticsTest.java`:

```java
package example.events;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class EventTypeDiagnosticsTest {

    @Test
    void eachEventMatchesOnlyItsExpectedHandler() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             EventTypeDiagnostics.ExampleConfig.class)) {

            EventTypeDiagnostics.publishSamples(context);

            var log = context.getBean(
                    EventTypeDiagnostics.EventLog.class);

            assertEquals(
                    List.of(
                            "CLASSIC invoice=INV-1",
                            "PAYLOAD invoice=INV-2",
                            "GENERIC string=ready",
                            "GENERIC integer=7"),
                    log.snapshot());
        }
    }

    @Test
    void unrelatedPayloadDoesNotTriggerAnyBusinessHandler() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             EventTypeDiagnostics.ExampleConfig.class)) {

            context.publishEvent(
                    new EventTypeDiagnostics.UnrelatedPayload("OTHER"));

            var log = context.getBean(
                    EventTypeDiagnostics.EventLog.class);

            assertTrue(log.snapshot().isEmpty());
        }
    }

    @Test
    void directCallTestsCallbackButNotSpringDispatch() {
        var log = new EventTypeDiagnostics.EventLog();
        var listener = new EventTypeDiagnostics.ClassicListener(log);

        listener.onApplicationEvent(
                new EventTypeDiagnostics.InvoicePaidEvent(
                        this, "INV-DIRECT"));

        assertEquals(
                List.of("CLASSIC invoice=INV-DIRECT"),
                log.snapshot());
    }
}
```

Chạy:

```bash
mvn test
```

Hoặc chỉ chạy class này:

```bash
mvn -Dtest=EventTypeDiagnosticsTest test
```

Dự án định nghĩa **3 JUnit test methods**. Khi toàn bộ assertion qua, Maven Surefire báo tests thành công; thời lượng và log cụ thể phụ thuộc môi trường nên không coi là stdout cố định.

**Ý nghĩa ba test:**

1. `eachEventMatchesOnlyItsExpectedHandler` xác minh **Spring dispatch thật**, bao gồm matching class, wrapper payload và generic bằng `ResolvableTypeProvider`.
2. `unrelatedPayloadDoesNotTriggerAnyBusinessHandler` xác minh rằng event không liên quan không vô tình lọt vào các listener typed.
3. `directCallTestsCallbackButNotSpringDispatch` chứng minh rằng gọi `onApplicationEvent` thủ công kiểm tra logic callback, **không kiểm tra registration/matching của Spring**.

Nếu một unit test trực tiếp pass nhưng integration test publish fail, khả năng cao vấn đề nằm ở đăng ký bean, kiểu event hoặc cấu hình dispatch; vì thế loại test thứ nhất có giá trị đặc biệt trong chẩn đoán.

## 9. Khi generic thật sự không resolve được

Với event dùng generic tùy biến, cần làm rõ type nào đã được lưu trong runtime.

### 9.1. Kiểm tra ResolvableType của chính event

Trong debug code có thể kiểm tra:

```java
ValueChangedEvent<String> event =
        new ValueChangedEvent<>("source", "ready");

System.out.println(event.getResolvableType());
```

Đây là **đoạn minh họa**, giả định đang ở cùng project mục 7 và đã import/nest class phù hợp. `getResolvableType()` trả về một `ResolvableType` đại diện cho `ValueChangedEvent<java.lang.String>`. Cách biểu diễn chuỗi của `ResolvableType` có thể khác theo phiên bản; đừng viết assertion phụ thuộc chính xác `toString()` nếu mục tiêu chỉ là kiểm tra generic.

Một assertion tốt hơn trong test:

```java
assertEquals(
        String.class,
        event.getResolvableType().getGeneric(0).resolve());
```

Với event số nguyên, generic tương ứng là `Integer.class`. Đây mới là dữ kiện cho biết Spring có đủ thông tin tách các method listener typed hay không.

### 9.2. Chỉ dùng ResolvableTypeProvider khi cần

Nếu application chỉ cần event riêng cho `InvoicePaid` và `InvoiceCancelled`, hai class cụ thể thường dễ đọc hơn một class `GenericBusinessEvent<T>` với nhiều cấp nested generic. Không lạm dụng generic để giảm số lượng class nhưng phải trả giá bằng việc chẩn đoán khó và hợp đồng nghiệp vụ mơ hồ.

Nếu generic chứa collection hoặc interface, hãy lưu type token thật (ví dụ `ResolvableType` dựng từ `ParameterizedTypeReference`/metadata tường minh) nếu muốn lọc sâu hơn. `value.getClass()` không đủ để khôi phục mọi type argument đã bị erasure.

### 9.3. Có thể nhận generic qua subclass rõ ràng

Spring có thể resolve generic từ hierarchy như:

```java
final class InvoiceStringChanged
        extends ValueChangedEvent<String> {
    InvoiceStringChanged(Object source, String value) {
        super(source, value);
    }
}
```

Đây là **minh họa theo giải pháp subclass**; không đặt vào demo vì `ValueChangedEvent` demo được khai báo `final`. Muốn dùng giải pháp này, phải định nghĩa một base generic event **không final** và cho subclass hợp lệ. Đổi thiết kế theo một trong hai hướng; không sao chép đoạn này vào demo rồi kỳ vọng vẫn biên dịch.

Mục tiêu là giữ type argument cụ thể trong class hierarchy — không phải tạo subclass chỉ để "thỏa mãn" cú pháp.

## 10. Sai generic do interface trung gian hoặc raw type

### 10.1. Mất thông tin generic trong abstraction

Ví dụ một hierarchy như:

```java
interface ListenerPort<T> {
    void handle(T event);
}

abstract class BaseListener<T> {
    public abstract void handle(T event);
}
```

Đây là **các kiểu Java minh họa**, không trực tiếp được Spring coi là `ApplicationListener`. Khi viết adapter chuyển kiểu giữa `T` và `ApplicationEvent`, phải bảo đảm loại event thực tế được khai báo/resolve ở bean cuối cùng. Nếu interface/base class quá chung chung, runtime metadata có thể không chứa thông tin cần cho Spring.

Khi refactor từ `ApplicationListener<InvoicePaidEvent>` sang class generic như `abstract class BaseEventListener<T extends ApplicationEvent> implements ApplicationListener<T>`, hãy kiểm tra subclass có cố định `T` hay chưa. Một bean raw generic không bảo đảm Spring biết chính xác nó nhận sự kiện nào.

### 10.2. Raw ApplicationListener và ép kiểu nguy hiểm

```java
// Anti-pattern: dùng raw type rồi cast tùy tiện.
ApplicationListener listener = event -> {
    InvoicePaidEvent paid = (InvoicePaidEvent) event;
    System.out.println(paid.getInvoiceId());
};
```

Đây là **mảnh minh họa có unchecked/raw warning**, không phải một listener an toàn để đăng ký. Nếu listener nhận sự kiện khác, cast có thể gây `ClassCastException` tại runtime. Raw type làm mất type safety và có thể khiến event filtering của framework không rõ ràng.

Sửa bằng:

```java
ApplicationListener<InvoicePaidEvent> listener =
        event -> System.out.println(event.getInvoiceId());
```

Khi đăng ký bằng instance lambda, việc Spring suy ra generic type từ runtime của lambda có thể kém rõ hơn class cụ thể. Đối với code cần lọc type nghiêm ngặt và chẩn đoán dễ, ưu tiên class có generic declaration rõ hoặc đăng ký qua API `ApplicationListener.forPayload(...)` theo đúng mục đích.

### 10.3. Wildcard và kiểu quá rộng

```java
@EventListener
public void onAny(ApplicationEvent event) {
    // Nhận nhiều loại ApplicationEvent, kể cả lifecycle events.
}
```

Method này rộng hơn `@EventListener void on(InvoicePaidEvent e)`: nó có thể nhận event hệ thống mà handler không được thiết kế để xử lý. Với payload POJO được Spring bọc, nó có thể nhìn thấy wrapper chứ không phải record. Nếu code sau đó downcast không kiểm tra, rủi ro runtime cao.

Đặt listener theo **loại sự kiện nhỏ nhất** cần nhận, không dùng Object/ApplicationEvent như cách khắc phục triệt để cho lỗi mismatch.

## 11. Không phải listener "mất event" nào cũng do kiểu

Một quy trình chẩn đoán tốt phải loại trừ các nguyên nhân có cùng biểu hiện:

| Biểu hiện | Nguyên nhân có thể | Cách xác minh |
| --- | --- | --- |
| `publishEvent` không lỗi, listener không chạy | Kiểu event khác; generic không match | In class publisher, chữ ký listener, `ResolvableType` |
| Listener viết đúng class nhưng vẫn không chạy | Bean không được đăng ký/scan | Kiểm tra context config và integration test |
| `@EventListener` chỉ có trên một object tạo bằng `new` | Object không phải bean Spring | Đăng ký bean, không tự tạo bên ngoài |
| Listener đợi `AFTER_COMMIT` không chạy | Không có transaction active hoặc rollback | Kiểm tra transaction phase, `fallbackExecution` |
| Listener `@Async` có log xuất hiện muộn | Dispatch sang executor/queue | Log thread, executor và kết quả task |
| Listener có `condition` không chạy | Biểu thức SpEL false hoặc lỗi evaluate | Kiểm tra điều kiện và input |
| Event phát rất sớm trong bootstrap | Listener bean chưa được tạo/đăng ký | Đăng ký sớm với `SpringApplication.addListeners(...)` khi phù hợp |
| Class giống tên nhưng khác package/classloader | Runtime class khác nhau | In qualified class name và classloader khi cần |
| Multiple listeners xuất hiện gọi lặp | Có thể đăng ký trùng bean/instance | Kiểm tra bean graph/điểm đăng ký |
| `ClassCastException` trong listener | Raw generic hoặc cast sai wrapper/source | Loại raw type, dùng type-safe signatures |

Đặc biệt:

- **`@TransactionalEventListener`** không chạy ngoài transaction đang hoạt động nếu `fallbackExecution=false`, ngay cả khi event type đúng. Đừng đổi generic để sửa lỗi transaction.
- **`@Async`** có thể chạy sau khi publisher trả về; test phải có cơ chế chờ với timeout thay vì `Thread.sleep(...)` may rủi.
- **Event bootstrap sớm** như `ApplicationEnvironmentPreparedEvent` xảy ra trước khi context bean được khởi tạo; `@Component @EventListener` trong context đó thường không kịp nhận. Cần đăng ký listener từ `SpringApplication` trước `run(...)`.
- **Listener của context cha/con** có thể nhận event được propagate theo hierarchy; cần phân biệt source/context để tránh xử lý nhiều lần không mong muốn. Kiểu đúng không có nghĩa mọi lần nhận đều là cùng một event nghiệp vụ.

## 12. Quy trình debug từng bước trong môi trường thực

### Bước 1: bắt đầu từ chính lời gọi publish

Tại nơi phát, kiểm tra:

```java
Object event = buildEvent();
log.info("Publishing event runtimeType={}",
        event.getClass().getName());
publisher.publishEvent(event);
```

Đây là **đoạn minh họa**, giả định đã định nghĩa `buildEvent()`, logger và publisher. Đừng log nguyên event nếu có PII, password hoặc token. Runtime type là thông tin cần thiết; tên biến `event` không giúp xác định gì.

### Bước 2: kiểm tra listener signature

Mở đúng class được đăng ký, xác nhận:

- Interface là `ApplicationListener<ConcreteEvent>`, không phải một kiểu khác.
- Class `ConcreteEvent` thực sự extends `ApplicationEvent`.
- Nếu dùng `@EventListener` nhận POJO, parameter là **payload class** chứ không vô tình là wrapper không đúng ý.
- Nếu dùng wrapper, hãy xác định generic `PayloadApplicationEvent<T>` tương ứng.
- Với generic event, kiểm tra `T` đã được resolve từ subclass/provider.
- Không sử dụng raw type hoặc cast rộng để che lỗi.

### Bước 3: đối chiếu bằng một integration test nhỏ

Một test có `AnnotationConfigApplicationContext` và bean listener thật thường là cách nhanh nhất. Publish **cùng kiểu object** mà production phát, assert callback được gọi đúng số lần. Nếu test trực tiếp `listener.onApplicationEvent(...)` pass nhưng test publish fail, nghi vấn nằm ở wiring hoặc type routing.

### Bước 4: đo event metadata và ResolvableType

Với event implement `ResolvableTypeProvider`, thử kiểm tra `getResolvableType().getGeneric(0).resolve()`. Nếu type không resolve, cung cấp metadata rõ hoặc chuyển sang class cụ thể.

Nếu event là POJO, phân biệt runtime payload class với `PayloadApplicationEvent` nội bộ. Không giả định `event.getSource()` là object nghiệp vụ.

### Bước 5: xác minh bean và các filter

Kiểm tra bean có thuộc context thực sự phát event không. Với `@EventListener(condition = "...")`, xác nhận condition đúng cho payload đó. Nếu có `@Order`, nhớ rằng nó ảnh hưởng thứ tự xử lý chứ không biến kiểu event không phù hợp thành phù hợp.

### Bước 6: xác minh async/transaction

Ghi thread name và trạng thái transaction tại đầu callback nếu cần. Với `@Async`, xác minh executor nhận task; với `@TransactionalEventListener`, kiểm tra phase, commit và rollback. Đừng cho rằng `publishEvent(...)` đã trả về tức là listener bất đồng bộ đã hoàn tất.

### Bước 7: chốt bằng test chống tái phát

Khi sửa, thêm test:
- Event đúng type được nhận.
- Event gần giống nhưng không phải cùng type **không được nhận**.
- Generic `String` và `Integer` không bị xử lý chéo.
- Payload record đi qua đúng method `@EventListener`.
- Khi có parent/child context, async hoặc transaction, test riêng cơ chế liên quan.

## 13. Những lỗi phổ biến và hướng sửa

**Lỗi 1 — `ApplicationListener<SomeRecord>` không biên dịch.** Interface yêu cầu `SomeRecord extends ApplicationEvent`. Sửa thành subclass event, `@EventListener` nhận record hoặc wrapper listener.

**Lỗi 2 — Publisher phát POJO, listener chờ subclass ApplicationEvent.** Hai kiểu không match. Thống nhất hợp đồng producer/consumer, không chỉ đổi tên class cho giống nhau.

**Lỗi 3 — Coi `PayloadApplicationEvent.getSource()` là payload.** Dùng `getPayload()`; source là đối tượng nguồn.

**Lỗi 4 — Mong `GenericEvent<String>` tự phân biệt chỉ nhờ dấu `<String>`.** Java xóa type argument ở runtime. Dùng subclass cố định generic hoặc `ResolvableTypeProvider`.

**Lỗi 5 — Dùng raw `ApplicationListener`.** Mất compile-time type safety và dễ cast sai. Khai báo concrete generic hoặc API listener phù hợp.

**Lỗi 6 — Gắn `@EventListener` lên object không nằm trong Spring container.** Annotation không tự tìm một object đã tạo bằng `new`. Đăng ký bean hoặc listener instance qua context.

**Lỗi 7 — Thấy listener không chạy rồi đổi parameter thành Object.** Làm mất ý nghĩa event contract, khiến callback có thể nhận cả loại không liên quan. Sửa đúng kiểu và metadata.

**Lỗi 8 — Đổi generic nhưng không kiểm tra provider.** Nếu event đã implement `ResolvableTypeProvider` sai, Spring vẫn có thể phân loại sai. Unit test `getResolvableType()` và integration test dispatch.

**Lỗi 9 — Test bằng cách gọi listener trực tiếp rồi kết luận Spring dispatch đúng.** Direct test chỉ gọi Java method. Cần test thật qua `context.publishEvent(...)`.

**Lỗi 10 — Không xét bean lifecycle, transaction và async.** Có những lỗi giống mismatch nhưng thật ra callback đăng ký muộn, đợi commit hoặc đang chạy trên worker.

**Lỗi 11 — Dùng tên class ngắn trong log.** Hai package hoặc classloader có thể có các class cùng simple name. Khi cần, log full qualified name và classloader/correlation ID.

**Lỗi 12 — Cast payload dựa vào nội dung trường.** Hai record có field giống nhau vẫn là hai kiểu Java khác. Dùng adapter/mapping rõ ràng nếu cần chuyển đổi event.

## 14. Checklist khi sửa lỗi event type hoặc generic

1. Đã xác định **class runtime** của object gửi vào `publishEvent(...)`?
2. Object đó **extends ApplicationEvent** hay là POJO/record?
3. Listener khai báo **`ApplicationListener<E>`**, `@EventListener` hay wrapper listener?
4. Với `ApplicationListener<E>`, `E extends ApplicationEvent` có đúng?
5. Khi nhận payload, đã phân biệt `PayloadApplicationEvent.getPayload()` với `getSource()`?
6. Với `GenericEvent<T>`, Spring có **đủ ResolvableType** để xác định `T`?
7. Có class/interface raw hoặc phép cast unchecked che mất thông tin kiểu?
8. Listener có được đăng ký trong **đúng ApplicationContext** và đúng thời điểm?
9. Có `condition`, async, transaction phase hoặc filter khác khiến callback không chạy?
10. Integration test có publish đúng object production sẽ phát và assert số lần nhận?
11. Test đã bao gồm event gần giống nhưng không hợp lệ, để tránh nhận nhầm?
12. Sau sửa, code có còn giữ hợp đồng nghiệp vụ rõ thay vì chuyển sang kiểu `Object` quá rộng?

**Ghi nhớ:** Spring không định tuyến event dựa vào tên biến, field giống nhau hay câu mô tả nghiệp vụ. Nó dựa trên **kiểu event có thể resolve được**, metadata generic phù hợp và cơ chế listener đã đăng ký. Hãy bắt đầu từ class runtime tại publisher, đối chiếu signature listener, kiểm tra erasure/`ResolvableTypeProvider` và xác nhận bằng integration test; chỉ sau đó mới điều tra các nguyên nhân khác như bean lifecycle, async hay transaction.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events và Generic Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): kiểu event, `@EventListener`, generic event và `ResolvableTypeProvider`.
- [Spring Framework API — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/ApplicationListener.html): `ApplicationListener<E extends ApplicationEvent>` và matching của listener.
- [Spring Framework API — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/PayloadApplicationEvent.html): wrapper cho POJO payload.
- [Spring Framework API — ResolvableTypeProvider](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/core/ResolvableTypeProvider.html): cung cấp runtime generic type metadata.
- [Spring Framework API — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.13/javadoc-api/org/springframework/context/event/GenericApplicationListener.html): lọc event/source type nâng cao.
- [JUnit 5 User Guide](https://docs.junit.org/5.11.4/user-guide/): test integration và assertions.
