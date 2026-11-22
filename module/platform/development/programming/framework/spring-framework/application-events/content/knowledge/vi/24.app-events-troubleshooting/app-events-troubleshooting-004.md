# Method listener không hợp lệ trong Spring Application Events: chẩn đoán và khắc phục

## 1. Vấn đề cần nhận diện

Spring Framework cho phép viết một phương thức xử lý application event bằng `@EventListener`. Thông thường chỉ cần đặt annotation trên một method của Spring bean, Spring sẽ tìm phương thức đó, xác định loại event và đăng ký nó thành một `ApplicationListener` nội bộ.

Nhưng không phải **mọi chữ ký method** đều là một event listener hợp lệ. Một số cấu hình khiến `ApplicationContext` **khởi tạo thất bại**; số khác cho phép ứng dụng chạy nhưng listener **không nhận event**, hoặc chỉ gây lỗi **khi event thực sự được phát**.

Ví dụ hai lỗi chữ ký thường gặp:

~~~java
// SAI: không có tham số, không có classes để chỉ định loại event.
@EventListener
public void onSomething() {}

// SAI: listener khai báo hai tham số event.
@EventListener
public void onOrder(OrderCreated created, PaymentCaptured captured) {}
~~~

Spring không diễn giải method thứ hai như một bộ ghép hai event. Event listener được kích hoạt bởi **một event tại một thời điểm**, không phải endpoint tự điền nhiều tham số nghiệp vụ.

Bài học nằm trong chủ đề **Chẩn đoán sự cố** của Spring Framework Application Events. Mục tiêu là biết cách đọc lỗi, phân biệt nhóm nguyên nhân, sửa chữ ký, kiểm tra Spring bean/proxy và xác minh với một chương trình Java 17+ độc lập.

Sau bài, bạn sẽ:

1. Nêu được các chữ ký `@EventListener` hợp lệ và không hợp lệ.
2. Phân biệt lỗi **startup/registration**, lỗi **runtime/invocation** và trường hợp **listener không được gọi**.
3. Hiểu vai trò của `EventListenerMethodProcessor` và `ApplicationListenerMethodAdapter`.
4. Sử dụng đúng `classes`, `condition`, kiểu payload, return value, `@Async` và `@TransactionalEventListener`.
5. Chẩn đoán các tình huống proxy/JDK interface, generic event, component scan, annotation processing và transaction.
6. Chạy demo Spring Framework 6.2.x có listener hợp lệ lẫn hai trường hợp Spring từ chối ở startup.

## 2. Cơ chế Spring nhận diện và đăng ký listener

Khi sử dụng Java configuration hoặc annotation configuration của Spring, cơ chế xử lý `@EventListener` thường được đăng ký tự động.

~~~text
AnnotationConfigApplicationContext.refresh()
      |
      +-- đọc bean definitions
      +-- tạo/configure beans
      +-- EventListenerMethodProcessor
              |
              +-- tìm methods có @EventListener
              +-- đọc classes / tham số event
              +-- xác định method có thể invoke qua bean/proxy
              +-- tạo ApplicationListenerMethodAdapter
              +-- đăng ký vào ApplicationEventMulticaster
      |
      +-- ứng dụng publishEvent(event)
              |
              +-- multicaster chọn listener khớp event type
              +-- adapter đánh giá condition
              +-- adapter gọi method listener
~~~

Các thành phần quan trọng:

- **`EventListenerMethodProcessor`**: rà soát các bean để tìm method có `@EventListener` và đăng ký listener adapter. Nếu method không thể đăng ký, việc refresh context có thể thất bại với `BeanInitializationException`/lỗi lồng bên trong.
- **`ApplicationListenerMethodAdapter`**: giữ metadata về method, xác định loại event được hỗ trợ, chuẩn bị arguments, đánh giá điều kiện SpEL và gọi method tương ứng.
- **`ApplicationEventMulticaster`**: phân phối event đến các listener. Với `SimpleApplicationEventMulticaster` mặc định, listener thông thường được gọi đồng bộ.
- **`ApplicationEventPublisher`**: API cho ứng dụng phát event bằng `publishEvent(...)`; không tự sửa chữ ký listener hay tự inject nhiều tham số.

Một bean **không được Spring quản lý** hoặc một context **không có cơ chế xử lý annotation event listener** có thể khiến method không được phát hiện; đây khác với trường hợp processor phát hiện method nhưng báo **invalid signature**.

## 3. Quy tắc chữ ký `@EventListener`

### 3.1. Một loại event, một tham số: cách đơn giản nhất

~~~java
// HỢP LỆ: kiểu event suy ra từ tham số đầu tiên và duy nhất.
@EventListener
public void onOrderCreated(OrderCreated event) {
    System.out.println(event.orderId());
}
~~~

Trong ví dụ này, `OrderCreated` có thể là một `ApplicationEvent` subclass hoặc một Java record/POJO được publish qua `ApplicationEventPublisher.publishEvent(Object)`.

Spring suy ra loại event từ tham số. Bạn **không cần** thêm `classes = OrderCreated.class` khi method đã có một tham số kiểu cụ thể.

### 3.2. Không có tham số nhưng chỉ định rõ `classes`

~~~java
// HỢP LỆ: không cần dữ liệu event, chỉ quan tâm việc event đã xảy ra.
@EventListener(classes = OrderCreated.class)
public void onAnyOrderCreated() {
    metrics.increment("order-created");
}
~~~

Vì method không có tham số để suy ra loại event, annotation phải khai báo loại event qua `classes` (hoặc alias `value`).

Có thể đăng ký nhiều loại event trên **cùng một method không tham số**:

~~~java
// HỢP LỆ trong mẫu Spring Framework 6.2.
@EventListener(classes = {OrderCreated.class, PaymentCaptured.class})
public void onBusinessActivity() {
    metrics.increment("business-activity");
}
~~~

Cần cân nhắc: method không có tham số **không biết event cụ thể nào** kích hoạt nó. Nếu hành vi cần phân biệt payload, viết hai method hoặc một event abstraction phù hợp thay vì cố yêu cầu Spring truyền hai event vào cùng lời gọi.

### 3.3. Hai tham số event: không hợp lệ

~~~java
// SAI: Spring @EventListener không phải một method argument resolver của MVC.
@EventListener
public void onBusinessEvent(OrderCreated order, PaymentCaptured payment) {
    // ...
}
~~~

Đối với method Java thông thường, Spring Framework 6.2 giới hạn **tối đa một tham số** để xác định event listener. Khi processor xử lý phương thức này, nguyên nhân trong exception thường chứa:

~~~text
Maximum one parameter is allowed for event listener method:
~~~

Muốn xử lý hai sự kiện riêng biệt, tạo hai listener:

~~~java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Xử lý event A.
}

@EventListener
public void onPaymentCaptured(PaymentCaptured event) {
    // Xử lý event B.
}
~~~

Nếu thật sự cần thông tin tổng hợp của A và B, dùng một **workflow/state machine**, repository hoặc aggregate tích lũy trạng thái trước khi tạo event tổng hợp. Không gắn một listener có hai tham số và trông đợi Spring chờ cả hai event xuất hiện.

### 3.4. Không tham số và không `classes`: không hợp lệ

~~~java
// SAI: Spring không có thông tin để biết listener xử lý loại event nào.
@EventListener
public void observe() {}
~~~

Khi processor gặp method này, nguyên nhân lỗi thường chứa:

~~~text
Event parameter is mandatory for event listener method:
~~~

Sửa theo một trong hai cách:

~~~java
// Cách 1: khai báo kiểu event bằng một tham số.
@EventListener
public void observe(OrderCreated event) {}

// Cách 2: chỉ định loại event trong annotation.
@EventListener(classes = OrderCreated.class)
public void observe() {}
~~~

**Chú ý về phiên bản:** các ví dụ và quy tắc trong bài được đặt trong phạm vi Spring Framework 6.2.x. Javadoc của các dòng Spring mới hơn có thể mở rộng/điều chỉnh cách diễn giải `classes` hoặc những trường hợp Kotlin; không dùng mô tả phiên bản khác để bỏ qua kiểm tra signature trong ứng dụng đang chạy.

### 3.5. Bảng đối chiếu chữ ký

| Chữ ký | Tình trạng | Lý do |
| --- | --- | --- |
| `@EventListener void on(OrderCreated e)` | Hợp lệ | Một tham số event |
| `@EventListener(classes=OrderCreated.class) void on()` | Hợp lệ | Loại event khai báo tường minh |
| `@EventListener(classes={A.class,B.class}) void on()` | Hợp lệ | Nhiều loại event, không yêu cầu payload làm tham số |
| `@EventListener void on()` | **Không hợp lệ** | Không suy ra loại event và không có `classes` |
| `@EventListener void on(A a, B b)` | **Không hợp lệ** | Nhiều hơn một tham số |
| `@EventListener String on(A a)` | Hợp lệ về chữ ký | Giá trị trả về **khác null** được Spring publish thành event khác |
| `@Async @EventListener void on(A a)` | Hợp lệ khi async được cấu hình | Chạy trên executor; không có kết quả trả về để Spring publish tiếp |

Không nên suy ra rằng mọi cấu hình bị đánh dấu “hợp lệ” đều phù hợp nghiệp vụ. Một method có return value có thể vô tình tạo thêm event, còn async listener có semantics khác với callback đồng bộ.

## 4. Lỗi startup khác với lỗi chỉ xảy ra khi publish

### Lỗi trong quá trình đăng ký

Thông thường, Spring phát hiện invalid signature trong lúc `ApplicationContext.refresh()`. Một stack trace có thể có cấu trúc:

~~~text
BeanInitializationException:
  Failed to process @EventListener annotation on bean with name '...'
Caused by: IllegalStateException:
  Maximum one parameter is allowed for event listener method: ...
~~~

Thông điệp chính xác có thể khác giữa các bản Spring, proxy configuration hoặc method thực tế; **hãy đọc nguyên nhân sâu bên trong (`Caused by`)**, không chỉ dòng exception ngoài cùng.

Nếu lỗi xảy ra khi refresh, chưa thể kết luận event publisher hay event payload đang sai: thường việc **đăng ký listener** đã không hoàn tất.

### Lỗi khi listener thực sự được gọi

Một số method được đăng ký thành công nhưng gặp lỗi ở thời điểm event được phát, ví dụ:

- `condition` là SpEL expression sai hoặc tham chiếu field không tồn tại.
- Method chạy nhưng logic ném `RuntimeException`.
- Bean bị proxy hóa theo cách listener method không thể được gọi qua proxy đang tồn tại.
- Return value là event mới gây vòng lặp phát event.
- Listener dùng `@Async`, exception không quay về publisher thread; phải xem cơ chế xử lý lỗi của executor.

Cần xác định chính xác **thời điểm lỗi**: context refresh hay `publishEvent`/callback. Hai thời điểm dẫn tới những hướng sửa khác nhau.

### Không có exception nhưng listener không chạy

Nguyên nhân thường gặp:

- Class không được đăng ký thành **Spring bean**.
- Method được gọi trên object do `new` thủ công chứ không thông qua bean Spring.
- Thiếu annotation processing trong cấu hình legacy/XML.
- Kiểu event không khớp loại listener mong đợi.
- `condition` hợp lệ nhưng trả về `false`.
- `@TransactionalEventListener` đang đợi commit, hoặc bỏ qua event ngoài transaction.
- Event được publish ở một `ApplicationContext` khác, hoặc tại một thời điểm không phù hợp.
- Async listener còn đang xử lý hoặc đã fail trên executor.

Không vội sửa method signature khi context khởi tạo bình thường và không có exception. Hãy chứng minh bean được đăng ký, đúng kiểu event và đúng điều kiện trước.

## 5. Ví dụ chạy được với Java 17+ và Spring Framework 6.2.12

Mục tiêu của demo là kiểm chứng **cả cấu hình hợp lệ lẫn hai loại chữ ký sai**. Chương trình tạo ba `AnnotationConfigApplicationContext` riêng biệt:

1. Context có listener hợp lệ: một method nhận event `Ping`, một method không tham số nhận cả `Ping` và `Pong`.
2. Context có method `@EventListener` không tham số và không khai báo `classes` — phải bị từ chối khi `refresh()`.
3. Context có method nhận hai tham số — phải bị từ chối khi `refresh()`.

Để không phụ thuộc vào toàn bộ stack trace do Spring tạo ra, chương trình **kiểm tra chuỗi thông báo của nguyên nhân exception**, rồi in ba dòng tóm tắt xác định. Nếu Spring bất ngờ chấp nhận một cấu hình sai hoặc exception mang nguyên nhân khác, chương trình báo lỗi thay vì in kết quả giả.

Cấu trúc thư mục:

~~~text
invalid-event-listener-demo/
├── pom.xml
└── src/main/java/demo/InvalidEventListenerDemo.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>invalid-event-listener-demo</artifactId>
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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/java/demo/InvalidEventListenerDemo.java`

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class InvalidEventListenerDemo {

    public record Ping(String id) {}
    public record Pong(String id) {}

    public static class GoodListener {
        private int typed;
        private int multi;

        @EventListener
        public void onPing(Ping event) {
            typed++;
        }

        @EventListener(classes = {Ping.class, Pong.class})
        public void onPingOrPong() {
            multi++;
        }

        public String summary() {
            return "typed=" + typed + ", multi=" + multi;
        }
    }

    // Sai: không có tham số và không chỉ định event classes.
    public static class NoEventTypeListener {
        @EventListener
        public void onAnything() {
        }
    }

    // Sai: hai tham số, Spring listener chỉ nhận một event mỗi lần.
    public static class TwoArgumentsListener {
        @EventListener
        public void onBoth(Ping ping, Pong pong) {
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class GoodConfig {
        @Bean
        public GoodListener goodListener() {
            return new GoodListener();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class NoEventTypeConfig {
        @Bean
        public NoEventTypeListener badListener() {
            return new NoEventTypeListener();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoArgumentsConfig {
        @Bean
        public TwoArgumentsListener badListener() {
            return new TwoArgumentsListener();
        }
    }

    // Chỉ nhận cấu hình sai khi nguyên nhân đúng thông điệp đang kiểm tra.
    private static boolean hasCauseMessage(
            Throwable exception, String expected) {
        for (Throwable t = exception; t != null; t = t.getCause()) {
            if (t.getMessage() != null
                    && t.getMessage().contains(expected)) {
                return true;
            }
        }
        return false;
    }

    private static void assertRejected(
            String label, Class<?> configuration, String expectedCause) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext()) {
            context.register(configuration);
            context.refresh();

            // Nếu tới đây, cấu hình sai đã không bị từ chối như mong đợi.
            throw new AssertionError(
                    "Expected context startup to fail: " + label);
        } catch (RuntimeException exception) {
            if (!hasCauseMessage(exception, expectedCause)) {
                throw exception;
            }
            System.out.println(label + "=REJECTED");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(GoodConfig.class)) {
            GoodListener listener = context.getBean(GoodListener.class);

            context.publishEvent(new Ping("ping-1"));
            context.publishEvent(new Pong("pong-1"));

            String result = listener.summary();
            if (!"typed=1, multi=2".equals(result)) {
                throw new AssertionError(
                        "Unexpected event listener result: " + result);
            }
            System.out.println("good=" + result);
        }

        assertRejected(
                "zero-arg-no-classes",
                NoEventTypeConfig.class,
                "Event parameter is mandatory for event listener method");

        assertRejected(
                "two-event-args",
                TwoArgumentsConfig.class,
                "Maximum one parameter is allowed for event listener method");
    }
}
~~~

Chạy tại thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.InvalidEventListenerDemo
~~~

Ba dòng do chương trình tự in khi kiểm tra thành công:

~~~text
good=typed=1, multi=2
zero-arg-no-classes=REJECTED
two-event-args=REJECTED
~~~

Maven và Spring có thể in log/error metadata bổ sung (đặc biệt khi context cố ý khởi tạo lỗi). **Ba dòng trên là stdout do mã ví dụ tự in**, không phải lời cam kết toàn bộ terminal chỉ có ba dòng.

### 5.3. Giải thích vì sao ví dụ đúng

- `GoodConfig` tạo đúng một Spring bean `GoodListener`. Listener `onPing(Ping)` chỉ nhận event `Ping`, còn `onPingOrPong()` dùng `classes={Ping.class,Pong.class}` nên nhận cả hai loại.
- `ApplicationContext.publishEvent(new Ping(...))` và `publishEvent(new Pong(...))` gửi POJO/record; Spring có thể bọc chúng trong `PayloadApplicationEvent`, và adapter chọn đúng listener theo payload type.
- Với dispatch đồng bộ mặc định, sau hai lần publish, biến đếm ổn định: `typed=1`, `multi=2`. Ví dụ không yêu cầu thứ tự hai method listener vì chỉ kiểm tra tổng.
- `NoEventTypeConfig` đăng ký một method `@EventListener` không có tham số và không `classes`. Khi processor xử lý, Spring không thể xác định event type và từ chối.
- `TwoArgumentsConfig` có method hai tham số; adapter giới hạn số tham số và từ chối.
- Hàm `assertRejected` không coi **mọi lỗi startup** là thành công. Nó đi qua cause chain và đòi chuỗi nguyên nhân tương ứng. Nếu vì lý do khác mà context fail, exception được ném lại.
- Mỗi context được đóng qua `try-with-resources`; một context bị lỗi không làm thay đổi cấu hình của context hợp lệ, và ví dụ không cần database/web server.

**Giới hạn QA:** ví dụ được thiết kế theo API Spring 6.2.12 và đối chiếu chữ ký/tên exception bằng tài liệu/source Spring. Output là dự kiến từ mã, không phải kết quả đo trên máy khi chưa thực sự chạy Maven.

## 6. `classes` / `value`: khi nào dùng và khi nào không?

`@EventListener` cung cấp `classes` và alias `value`:

~~~java
// Hai cách tương đương khi chỉ định một event class.
@EventListener(classes = OrderCreated.class)
public void observeCreated() {}

@EventListener(OrderCreated.class)
public void observeCreatedAnotherWay() {}
~~~

Nếu method đã có một tham số `OrderCreated event`, không cần khai báo lại loại đó trong `classes`. Việc thêm một tập `classes` không tương thích với kiểu tham số hoặc dùng nhiều event classes trên method cần payload có thể dẫn tới dispatch không như mong đợi.

Nguyên tắc an toàn cho Spring 6.2:

- Muốn **nhận payload**: một method với **một tham số kiểu event cụ thể**.
- Muốn xử lý một event mà **không cần payload**: method không tham số, `classes=SomeEvent.class`.
- Muốn một callback phản ứng với **nhiều loại event** và không cần phân biệt chúng: method không tham số, `classes={A.class,B.class}`.
- Muốn phản ứng khác nhau với A/B: **hai method listener riêng** hoặc một abstraction kiểu dữ liệu chung thích hợp.

Không dùng `@EventListener` như `@RequestMapping` hay `@MessageMapping` với nhiều tham số có annotation injection tùy ý. Event method có quy tắc riêng của Spring Context, không phải argument resolver của web controller.

## 7. `condition` SpEL: cú pháp sai không phải lỗi signature

Một method có chữ ký đúng vẫn có thể không chạy do điều kiện:

~~~java
// Minh họa: OrderCreated có method amount().
@EventListener(condition = "#a0.amount() > 100")
public void onLargeOrder(OrderCreated event) {
    // Chỉ chạy với giá trị amount > 100.
}
~~~

Các biến được hỗ trợ trong điều kiện gồm:

- `#root.event`: event ở cấp `ApplicationEvent` của Spring; với POJO payload, có thể là wrapper.
- `#root.args` hoặc `args`: danh sách tham số method.
- `#a0`, `#p0`, `args[0]`: tham số đầu tiên.
- Tên tham số, ví dụ `#event`, nếu tên được giữ lại trong bytecode và cấu hình biên dịch phù hợp.

Nếu dùng `#event.amount()` nhưng parameter name không được giữ, evaluation có thể sai; `#a0.amount()` thường ổn định hơn khi method có một tham số.

**Khác biệt cần chẩn đoán:**

- `condition` trả `false`: listener **bị bỏ qua hợp lệ**, không có lỗi.
- `condition` tham chiếu thuộc tính không tồn tại hoặc expression sai: có thể phát sinh SpEL exception **khi event được đánh giá**.
- Method không có tham số và không khai báo `classes`: bị từ chối khi **đăng ký listener** trước khi có event.

Chọn mã fix theo nhóm lỗi, không sửa số tham số khi nguyên nhân thực tế là SpEL.

## 8. POJO event, wrapper và mismatch kiểu

Từ Spring 4.2, ứng dụng có thể publish object bất kỳ:

~~~java
// Ví dụ: record Java 17.
public record InvoiceIssued(long invoiceId) {}

publisher.publishEvent(new InvoiceIssued(17L));
~~~

Spring có thể biểu diễn nó bằng `PayloadApplicationEvent`, rồi adapter trích payload phù hợp với tham số listener:

~~~java
@EventListener
public void onInvoiceIssued(InvoiceIssued event) {
    // Nhận record, không cần tự cast từ wrapper.
}
~~~

Những nhầm lẫn phổ biến:

- Listener nhận `OrderCreated` nhưng publisher thật sự gửi `InvoiceIssued` nên method không được gọi.
- Dùng `ApplicationEvent` làm tham số trong khi muốn nhận payload cụ thể; listener có thể nhận nhiều loại event framework, dễ quá rộng.
- Listener nhận `PayloadApplicationEvent<InvoiceIssued>` nhưng kỳ vọng mọi cấu hình generic đều được phân giải như một record tham số trực tiếp; cần test với kiểu payload thật và generic metadata.
- Event được publish bởi một context khác hoặc child/parent context nên chỉ một phần listener thấy event.

Khi debug, in **kiểu thực tế của event được publish**, kiểu tham số listener, context source và có/không có payload wrapper. Không tự ép `PayloadApplicationEvent` thành record gốc.

## 9. Return value: chữ ký hợp lệ nhưng có thể gây lỗi logic

Một listener có thể trả một object khác `void`:

~~~java
// Minh họa: xuất event kết quả khi có OrderCreated.
@EventListener
public OrderIndexed onCreated(OrderCreated event) {
    return new OrderIndexed(event.orderId());
}
~~~

Spring sẽ phát giá trị trả về khác null như **một event mới**. Nếu trả array/collection, các phần tử có thể được publish riêng. Điều này hợp lệ về chữ ký nhưng dễ tạo:

- Chu kỳ A → B → A không có điểm dừng.
- Listener vô tình trả lại chính event đầu vào, gây recursion.
- Event mới bị xử lý trong cùng transaction/thread nếu multicaster đồng bộ, khiến lỗi và latency bất ngờ.
- Kết quả xử lý bị nhầm thành return value cho caller của `publishEvent` (publisher vẫn không nhận giá trị method callback).

Nếu không định phát event tiếp theo, khai báo return type là **`void`** và đừng trả dữ liệu chỉ để log/debug.

### `@Async @EventListener`: return event không phải phương thức publish hợp lệ

Theo hợp đồng Spring, listener bất đồng bộ **không hỗ trợ tạo subsequent event bằng return value**. Nếu cần phát event từ async callback, inject `ApplicationEventPublisher` và publish tường minh:

~~~java
// Minh họa trong Spring bean, với @EnableAsync và executor hợp lệ.
@Async("listenerExecutor")
@EventListener
public void processAsync(OrderCreated event) {
    OrderIndexed next = index(event);
    publisher.publishEvent(next);
}
~~~

Đoạn này chỉ minh họa việc chủ động publish; cần khai báo `publisher`, `index` và executor thực tế. Không coi một method trả `CompletableFuture<OrderIndexed>` là cơ chế Spring tự publish `OrderIndexed` sau khi Future hoàn tất.

## 10. Proxy, `@Transactional` và method không thể invoke

Có những trường hợp **chữ ký về số tham số hợp lệ**, nhưng AOP proxy khiến Spring không thể gọi listener method trên bean thực tế.

Một trường hợp phổ biến: bean bị tạo thành **JDK dynamic proxy** chỉ triển khai interface; method `@EventListener` lại chỉ tồn tại trên implementation class, không có trong interface exposed bởi proxy. Nếu adapter không tìm được một method có thể invoke trên proxy, có thể xảy ra `IllegalStateException` hoặc lỗi registration/invocation.

Một số hướng khắc phục, tùy thiết kế:

1. Ưu tiên **class-based proxy** nếu listener method cần được gọi trên concrete bean.
2. Đảm bảo method được khai báo theo public API/interface mà proxy expose khi dùng interface-based proxy, nếu phù hợp.
3. Tách listener thành một bean chuyên trách **không cần proxy phức tạp**, gọi một service khác thực hiện nghiệp vụ `@Transactional`.
4. Kiểm tra `proxyTargetClass`, method visibility, `final` class/method và các hạn chế AOP trước khi chỉnh toàn hệ thống.
5. Tránh self-invocation khi mong đợi `@Transactional`/`@Async` chạy qua proxy: gọi `this.someMethod()` trong cùng bean thường không đi qua proxy advice.

**Không nên khẳng định “mọi method private đều không phải EventListener”**. Cơ chế reflection/annotation detection có thể xử lý những method không public trong một số hoàn cảnh; nhưng khi cần Spring AOP advice hoặc JDK proxy, visibility/invocability là vấn đề riêng. Khi chẩn đoán, dùng method **public, một tham số, Spring bean đơn giản** làm baseline; sau đó mới thêm proxy.

Ví dụ thiết kế ít coupling:

~~~java
@Component
public class OrderEventsHandler {
    private final OrderAuditService auditService;

    public OrderEventsHandler(OrderAuditService auditService) {
        this.auditService = auditService;
    }

    @EventListener
    public void onCreated(OrderCreated event) {
        auditService.record(event.orderId());
    }
}
~~~

Đây là snippet minh họa, không phải chương trình độc lập. `OrderAuditService` là bean khác có thể áp dụng `@Transactional` theo nhu cầu.

## 11. `@TransactionalEventListener`: không chạy không đồng nghĩa chữ ký sai

`@TransactionalEventListener` là listener gắn với transaction phase:

~~~java
// Minh họa: nhận event sau commit thành công.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderCreated event) {
    notificationGateway.send(event.orderId());
}
~~~

Mặc định:

- Phase là `AFTER_COMMIT`.
- Event publish **ngoài transaction** bị bỏ qua trừ khi bật `fallbackExecution=true`.
- Event publish **trong transaction rồi rollback** không kích hoạt callback AFTER_COMMIT.
- Event có thể đã được phát khi `@EventListener` đồng bộ nhận nó nhưng transactional listener vẫn chưa chạy vì đang chờ completion phase.

Nếu `@TransactionalEventListener` không chạy, hãy kiểm tra transaction boundary thực tế thay vì tự động đổi method signature. Với `@Async`, worker thường không mang transaction context cũ; không cố copy toàn bộ `TransactionSynchronizationManager` sang worker bằng `ThreadLocal`.

## 12. Diagnostic checklist theo triệu chứng

| Triệu chứng | Khả năng nguyên nhân | Bước đầu tiên |
| --- | --- | --- |
| Startup báo “Maximum one parameter...” | Method có ít nhất hai tham số | Chỉ giữ một event parameter hoặc tách method |
| Startup báo “Event parameter is mandatory...” | Method không tham số và không `classes` | Bổ sung event param hoặc khai báo `classes` |
| Startup báo “Failed to process @EventListener annotation...” | Processor không thể đăng ký method/bean | Mở `Caused by` sâu nhất để xác định signature/proxy |
| Context chạy nhưng listener không bao giờ được gọi | Bean không thuộc context, sai event type, condition false | Kiểm tra bean registration, publish payload, SpEL |
| Listener chỉ fail khi event được publish | Condition SpEL, exception callback, proxy invocation | Debug stack trace tại `publishEvent` |
| Listener không chạy sau transaction | `AFTER_COMMIT` đợi commit hoặc bỏ event không transaction | Kiểm tra transaction active và phase |
| Async callback không thấy lỗi ở publisher | Exception chạy trên executor | Kiểm tra async handler, logs và task completion |
| Method return làm event lặp | Spring publish return value | Đổi return `void` hoặc tạo workflow có điểm dừng |
| Generic listener không bắt đúng event | Type erasure / generic type metadata | Chỉ định type cụ thể và test dispatch |
| Chỉ một context nhận event | Event propagation/context hierarchy | Kiểm tra publisher và listener context |

## 13. Quy trình debug từng bước

### Bước 1 — Xác định thời điểm lỗi

Chạy thử context startup **không publish event nghiệp vụ**. Nếu đã lỗi, tập trung vào bean registration, proxy và listener signature. Nếu startup ổn nhưng lỗi khi publish, tập trung vào callback body, `condition`, return-value event chain và executor.

### Bước 2 — Đọc nguyên nhân sâu nhất

Ghi lại:

- Class/method được Spring nêu trong stack trace.
- Số tham số method và `@EventListener(classes=...)` đang khai báo.
- Tên bean và class thực tế của bean/proxy.
- Thông điệp `IllegalStateException`/SpEL exception ở phần `Caused by`.
- Context đang startup và cấu hình annotation processor.

Không chỉ nhìn `BeanCreationException` ngoài cùng rồi sửa tất cả listeners; error chain thường chỉ đúng method sai.

### Bước 3 — Thu gọn thành một listener baseline

Chuyển method nghi vấn về dạng dễ kiểm chứng:

~~~java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // Tạm chỉ log hoặc tăng một biến đếm kiểm thử.
}
~~~

Đặt nó trong một bean đơn giản được khai báo `@Component` hoặc `@Bean`, bảo đảm Spring annotation support đã bật. Nếu baseline hoạt động, thêm lại `condition`, `@Async`, transaction và proxy **từng yếu tố một** để khoanh vùng.

### Bước 4 — Kiểm tra event type và điều kiện

In/quan sát tại publisher:

- Class của object được publish.
- Event ID, aggregate ID/correlation ID nếu có.
- Context nào publish.
- Có phải POJO wrapper hay `ApplicationEvent` subclass.
- Nếu có `condition`, thử thay tạm bằng `condition = "true"` để phân biệt signature với SpEL.

Không giữ thay đổi debug trong production khi nó làm mất điều kiện nghiệp vụ quan trọng.

### Bước 5 — Kiểm tra thread, transaction và completion

Nếu listener bị `@Async`, chờ task bằng `CountDownLatch`/`CompletableFuture` trong test, tránh `Thread.sleep` tùy ý. Nếu callback có transaction phase, test cả commit và rollback. Nếu bean bị JDK proxy, kiểm tra method thực sự có thể được gọi qua proxy.

### Bước 6 — Viết regression test

Test ít nhất ba trường hợp:

1. Context có listener hợp lệ refresh thành công và nhận đúng event.
2. Listener không tham số/không classes phải bị từ chối khi startup.
3. Listener nhiều hơn một event argument phải bị từ chối khi startup.

Khi sửa production code, test thêm SpEL condition, proxy configuration và startup theo cấu hình dependency injection thật.

## 14. Kiểm thử nâng cao với JUnit

Có thể chuyển ví dụ sang JUnit 5:

~~~java
// Snippet minh họa; cần dependency spring-test/JUnit và các class demo.
@Test
void invalidListenerShouldFailAtRefresh() {
    try (var context = new AnnotationConfigApplicationContext()) {
        context.register(NoEventTypeConfig.class);

        Exception exception = assertThrows(
                RuntimeException.class,
                context::refresh);

        assertTrue(hasCauseMessage(
                exception,
                "Event parameter is mandatory for event listener method"));
    }
}
~~~

Với listener hợp lệ, có thể dùng `@SpringJUnitConfig` và `@RecordApplicationEvents` để nhận `ApplicationEvents`, gọi service và `events.stream(OrderCreated.class)` để assert số event thật sự được publish. Cần nhớ **event được ghi nhận không chứng minh async listener đã hoàn tất hoặc transaction đã commit**.

### Cần kiểm tra những gì?

- Component scan có chứa package của listener bean không?
- Bean có thật sự là singleton/prototype Spring bean được quản lý không?
- Annotated method có đúng một tham số hoặc không tham số với `classes` không?
- Type của tham số có phù hợp với object event thực tế không?
- Có return value phát sinh event ngoài ý muốn không?
- SpEL condition có dùng `#a0`/metadata đúng không?
- `@Async` đã có `@EnableAsync` và executor phù hợp chưa?
- Nếu dùng JDK proxy, method có invocable trên proxy không?
- Nếu `@TransactionalEventListener`, phase và transaction boundary có đúng không?
- Test có assert **event dispatch** và **side effect** riêng rẽ không?

## 15. Các nhầm lẫn nên tránh

**“Method có hai tham số vì cần hai thông tin”** — Spring chỉ giải quyết event parameter, không tự lấy thêm repository, security context hay service làm tham số callback. Dependencies hãy inject vào bean qua constructor; dữ liệu nghiệp vụ cần thiết nên nằm trong event payload hoặc được tra cứu có kiểm soát.

**“Method không tham số nghĩa là luôn không hợp lệ”** — sai. Không tham số **vẫn hợp lệ nếu `classes` chỉ định loại event**.

**“Method không được gọi chắc chắn là method không hợp lệ”** — sai. Có thể đơn giản là event type không khớp, condition false, event ngoài transaction hoặc async chưa hoàn tất.

**“Return type khác void là lỗi compiler”** — không đúng. Return value thường được Spring tự publish thành event mới; đây là hành vi hợp lệ nhưng có thể gây vòng lặp nếu không hiểu.

**“`@Async` có return value thì Spring sẽ publish sau Future”** — không đúng theo hợp đồng event listener async. Muốn publish event tiếp theo từ async logic, phải publish tường minh.

**“Mọi method private/final đều giống nhau”** — proxy type, AOP interception, visibility và annotation introspection là những khía cạnh riêng. Dùng API công khai, bean đơn giản để chẩn đoán và dựa vào stack trace thực tế.

**“Chỉ cần retry khi startup fail”** — sai. Invalid listener signature là lỗi cấu hình/chương trình xác định; restart không thay đổi method. Cần sửa code/config và thêm regression test.

## 16. Checklist cuối

1. Xác định Spring Framework version đang chạy và ngữ cảnh đăng ký annotation listener.
2. Đọc lỗi sâu nhất: startup registration hay runtime invocation?
3. Xác nhận `@EventListener` method có **0 hoặc 1 tham số**, và trường hợp 0 tham số có `classes` rõ ràng.
4. Không dùng listener hai tham số để ghép hai event độc lập.
5. Kiểm tra `classes`/event payload type thực tế, nhất là POJO wrapped.
6. Kiểm tra `condition` SpEL riêng; dùng `#a0` khi không chắc tên tham số được giữ.
7. Kiểm tra bean thuộc Spring context, annotation processor hoạt động và method có thể invoke qua proxy.
8. Xác minh return type không vô tình publish thêm event.
9. Với `@Async` và `@TransactionalEventListener`, kiểm tra executor, transaction phase, callback completion.
10. Bổ sung một test startup và một test event dispatch để ngăn regression.

**Ghi nhớ:** Trong Spring Framework 6.2, `@EventListener` không hỗ trợ tùy ý nhiều tham số như controller method. Chữ ký an toàn nhất là **một tham số đúng kiểu event**, hoặc **không tham số nhưng có `classes`**. Khi xuất hiện lỗi, trước hết phân loại: đăng ký listener thất bại, gọi listener thất bại hay listener chưa từng được chọn. Việc phân loại đúng giúp sửa nguyên nhân mà không làm biến đổi lifecycle hoặc nghiệp vụ một cách không cần thiết.

## Tài liệu chính thức

- Spring Framework 6.2 — ApplicationContext events, @EventListener, return values và async: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — @EventListener Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework 6.2 — ApplicationListenerMethodAdapter Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/ApplicationListenerMethodAdapter.html
- Spring Framework 6.2 — EventListenerMethodProcessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListenerMethodProcessor.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
