# Xây dựng publisher và listener tối thiểu với Spring Framework Application Events

## 1. Mục tiêu thực hành

Bài học triển khai một luồng sự kiện **trong cùng Spring ApplicationContext** bằng Java 17:

- Tạo một event `OrderSubmitted` dưới dạng Java `record`.
- Tạo service publisher sử dụng `ApplicationEventPublisher` qua constructor injection.
- Tạo listener bằng phương thức `@EventListener` trên một Spring bean.
- Khởi động Spring context không cần Spring Boot, phát hai event hợp lệ và nhận chúng.
- Kiểm tra một input không hợp lệ không tạo event.
- Xem stdout và bộ đếm để xác nhận chính xác những gì xảy ra.

Mô hình nhỏ này cho thấy giá trị của cơ chế Observer nội bộ: publisher **không cần biết listener cụ thể**. Tuy nhiên sự kiện Spring không tự là broker, queue bền vững, transaction hoặc hệ thống gửi thông báo bảo đảm giao hàng.

## 2. Các thành phần cần hiểu

| Thành phần | Vai trò | Trong ví dụ |
| --- | --- | --- |
| Event | Mô tả điều vừa xảy ra; mang payload cần thiết | `OrderSubmitted(orderId, amountInCents)` |
| Publisher | Tạo event và nhờ Spring phân phối | `OrderService.submit(...)` |
| API phát | Tách service khỏi các listener | `ApplicationEventPublisher.publishEvent(...)` |
| Listener | Nhận event phù hợp và phản ứng | `OrderSubmittedListener.onSubmitted(...)` |
| Multicaster | Tìm và gọi listener đã đăng ký | `SimpleApplicationEventMulticaster` mặc định |
| Container | Tạo bean, inject và đăng ký method listener | `AnnotationConfigApplicationContext` |

Dòng chảy:

```text
main()
   |
   v
OrderService.submit("ORD-001", 1250)
   |
   +-- validate orderId, amount
   +-- new OrderSubmitted(...)
   +-- publisher.publishEvent(event)
                    |
                    v
          Spring event multicaster
                    |
                    v
          @EventListener onSubmitted(event)
                    |
                    +-- đọc event.orderId()
                    +-- tăng receivedCount
                    +-- ghi dòng output
                    |
                    v
          publishEvent(...) trả về
   |
   v
OrderService tiếp tục xử lý
```

Ví dụ chạy **đồng bộ theo mặc định**: listener được gọi trên publisher thread. Đây là đặc tính của cấu hình multicaster thông thường, không phải lời hứa rằng mọi cấu hình `publishEvent` luôn đồng bộ. Nếu sau này dùng executor hoặc `@Async`, thứ tự và cơ chế xử lý lỗi sẽ khác.

## 3. Chuẩn bị môi trường

Yêu cầu:

- JDK **17 trở lên** (bao gồm `javac`).
- Apache Maven.
- Một terminal và editor Java.
- Có thể tải Maven dependencies ở lần chạy đầu.

Kiểm tra:

```bash
java -version
javac -version
mvn -version
```

Lưu ý Maven cũng phải chạy bằng Java 17+, không chỉ lệnh `java -version`. Ví dụ dưới đây dùng **Spring Framework 6.2.8**. Không cần Spring Boot, HTTP server, database hoặc message broker để phát và nghe application events.

## 4. Cấu trúc thư mục Maven

```text
minimal-spring-events/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── MinimalEventDemo.java
```

Tên `package demo;` trong source phải khớp thư mục `demo`. Tên `public class MinimalEventDemo` phải khớp tên file.

### 4.1. Nội dung pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>minimal-spring-events</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.MinimalEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` cung cấp `ApplicationEventPublisher`, `@EventListener`, `@Configuration`, `@Bean` và `AnnotationConfigApplicationContext`. Maven tải các dependency transitive cần thiết. Không cần import Spring Boot starter để dùng Spring Application Events.

### 4.2. Nội dung MinimalEventDemo.java hoàn chỉnh

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class MinimalEventDemo {

    // 1. Event payload bất biến, không cần extends ApplicationEvent.
    public record OrderSubmitted(String orderId, long amountInCents) {}

    // 2. Publisher là service được Spring quản lý.
    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void submit(String orderId, long amountInCents) {
            if (orderId == null || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "orderId must not be blank");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            System.out.println("publisher: accepted " + orderId);
            OrderSubmitted event =
                    new OrderSubmitted(orderId, amountInCents);
            publisher.publishEvent(event);
            System.out.println("publisher: returned " + orderId);
        }
    }

    // 3. Listener nhận đúng kiểu OrderSubmitted.
    public static final class OrderSubmittedListener {
        private final AtomicInteger received = new AtomicInteger();

        @EventListener
        public void onSubmitted(OrderSubmitted event) {
            int call = received.incrementAndGet();
            System.out.println(
                    "listener: order=" + event.orderId()
                    + " amount=" + event.amountInCents()
                    + " call=" + call);
        }

        public int receivedCount() {
            return received.get();
        }
    }

    // 4. Đăng ký cả publisher và listener thành Spring beans.
    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        OrderSubmittedListener orderSubmittedListener() {
            return new OrderSubmittedListener();
        }
    }

    // 5. Chạy hai lệnh hợp lệ và một lệnh bị từ chối.
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            OrderService service =
                    context.getBean(OrderService.class);
            OrderSubmittedListener listener =
                    context.getBean(OrderSubmittedListener.class);

            service.submit("ORD-001", 1250);
            service.submit("ORD-002", 2200);

            try {
                service.submit("ORD-003", 0);
            } catch (IllegalArgumentException ex) {
                System.out.println(
                        "main: rejected " + ex.getMessage());
            }

            int received = listener.receivedCount();
            System.out.println("main: handled=" + received);

            if (received != 2) {
                throw new IllegalStateException(
                        "Expected exactly 2 events");
            }
        }
    }
}
```

**Giải thích code:**

1. `record OrderSubmitted` có hai trường; compiler tạo constructor và accessor `orderId()`, `amountInCents()`.
2. `OrderService` **chỉ nhận interface `ApplicationEventPublisher`**, không import hoặc gọi trực tiếp class listener.
3. Sau khi validate input, service tạo event rồi `publishEvent(event)`. Nếu input sai, method ném exception **trước khi publish**.
4. `OrderSubmittedListener` có `@EventListener`; Spring đăng ký method này nhờ bean `orderSubmittedListener()`.
5. `AtomicInteger` trong demo đếm số invocation; đây là đếm trong RAM, không đại diện cho message đã giao bền vững.
6. `@Configuration` và `@Bean` tạo đủ các thành phần mà không cần `@ComponentScan` hoặc Spring Boot.
7. `AnnotationConfigApplicationContext` tạo và refresh context; khi `main` lấy beans, listener đã được đăng ký.
8. Context được đóng bằng `try`-with-resources khi kết thúc; không cần web server.
9. Cuối chương trình, điều kiện `received == 2` kiểm tra luồng cơ bản; nếu listener không hoạt động, chương trình báo lỗi thay vì âm thầm coi như thành công.

## 5. Chạy và kiểm tra stdout

Từ thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java
```

Các dòng do **chương trình Java** in ra, không kể log tùy môi trường của Maven:

```text
publisher: accepted ORD-001
listener: order=ORD-001 amount=1250 call=1
publisher: returned ORD-001
publisher: accepted ORD-002
listener: order=ORD-002 amount=2200 call=2
publisher: returned ORD-002
main: rejected amount must be positive
main: handled=2
```

| Quan sát | Ý nghĩa |
| --- | --- |
| `publisher: accepted ORD-001` | Service đã xác thực command thứ nhất |
| `listener: ... call=1` | Listener nhận event ORD-001 |
| `publisher: returned ORD-001` | Lần gọi publish đã trả về |
| `listener: ... call=2` | Listener nhận event ORD-002 |
| `main: rejected ...` | Command ORD-003 không hợp lệ nên không publish |
| `main: handled=2` | Có đúng hai event được listener xử lý |

Trong **cấu hình này**, dòng listener xuất hiện trước `publisher: returned` vì Spring gọi listener đồng bộ. Không áp dụng thứ tự đó cho mọi cấu hình async.

Nếu chạy sai, kiểm tra: JDK/Maven version, tên file và `package`, kiểu event, việc đăng ký listener bean, dấu `@EventListener` và stack trace của Maven.

## 6. Tại sao record event không cần extends ApplicationEvent?

Spring có hai nhóm cách định nghĩa event:

- **POJO/record:** `record OrderSubmitted(...)`; gọi `publishEvent(Object)`; Spring có thể bọc payload thành `PayloadApplicationEvent` để phân phối.
- **Subclass của `ApplicationEvent`:** kiểu truyền thống, có `source` và có thể dùng interface `ApplicationListener<YourEvent>`.

Một event subclass truyền thống:

```java
// Trích đoạn: đặt vào file/package tương ứng nếu muốn dùng.
import org.springframework.context.ApplicationEvent;

public final class OrderSubmittedEvent extends ApplicationEvent {
    private final String orderId;

    public OrderSubmittedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
```

Đoạn này không dùng trong project chính, chỉ giúp phân biệt cơ chế cũ và mới. Với Java 17, record kết hợp `@EventListener` là cách rất đơn giản.

Không viết `ApplicationListener<OrderSubmitted>` cho record thường: generic type của `ApplicationListener<E>` yêu cầu `E extends ApplicationEvent`. Muốn nhận payload record, cứ dùng `@EventListener` như ví dụ.

## 7. Spring tìm được listener như thế nào?

Cơ chế annotation listener dựa trên các Spring-managed beans:

1. Context đọc `Config` và tạo bean `OrderService`/`OrderSubmittedListener`.
2. Spring xử lý metadata `@EventListener` thông qua hạ tầng `EventListenerMethodProcessor` và listener adapter.
3. Khi publisher phát event, multicaster lựa chọn adapter phù hợp theo **event type**.
4. Adapter gọi method `onSubmitted(OrderSubmitted)` với record payload.
5. Listener thực hiện logic phản ứng và trả về `void`.

Một class có `@EventListener` nhưng bị tạo thủ công bên ngoài Spring container **không tự được đăng ký**:

```java
// Minh họa lỗi thường gặp, không cần thêm vào chương trình chính.
OrderSubmittedListener listener = new OrderSubmittedListener();
// Bean này do "new" tạo ra, không được Spring tự phát hiện listener.
```

Trong code chính, dùng `@Bean` để Spring sở hữu lifecycle. Nếu dùng `@Component`, phải cấu hình component scanning đúng package; bản demo không cần scanning vì đã đăng ký bean trực tiếp.

Tránh lạm dụng lazy initialization cho listener phương thức: Spring documentation lưu ý bean listener định nghĩa lazy có thể không được đăng ký để nhận sự kiện theo cách bạn mong đợi.

## 8. Publisher không nên phụ thuộc trực tiếp vào các listener

Với cách gọi trực tiếp:

```java
// Trích đoạn minh họa, không dùng trong ví dụ chạy.
auditListener.handle(order);
emailListener.handle(order);
cacheListener.handle(order);
```

Service phải biết cả ba component. Khi bổ sung thêm listener mới, service phải thay đổi. Đôi khi orchestration trực tiếp là đúng, nhất là khi cần kết quả và thứ tự bắt buộc; nhưng nó không thể hiện cơ chế observer.

Với publisher:

```java
publisher.publishEvent(new OrderSubmitted(orderId, amountInCents));
```

`OrderService` chỉ nói rằng một sự kiện đã xảy ra. Các module khác có thể đăng ký phản ứng mà không sửa logic publisher. Đổi lại, mối liên hệ giữa publisher và listeners **ít hiện rõ ở call graph hơn**, nên cần đặt tên event tốt, viết test và quản lý exception/error policy.

Đừng dùng event bus chỉ để che giấu một lời gọi nghiệp vụ bắt buộc: nếu phần xử lý B phải hoàn tất để A hợp lệ, dependency trực tiếp hoặc một workflow orchestration có thể chính xác và dễ kiểm thử hơn.

## 9. Mở rộng: thêm một listener thứ hai

Giả sử cần ghi audit sau khi nhận `OrderSubmitted`. Ta có thể thêm một bean khác:

```java
// Trích đoạn bổ sung bên trong MinimalEventDemo.
public static final class AuditListener {
    @EventListener
    public void onOrderSubmitted(OrderSubmitted event) {
        System.out.println("audit: accepted " + event.orderId());
    }
}

// Trong Config, thêm:
@Bean
AuditListener auditListener() {
    return new AuditListener();
}
```

Đây chỉ là các đoạn thay đổi, **không phải file độc lập**. Khi đã thêm, một `publishEvent` có thể làm **cả `OrderSubmittedListener` và `AuditListener` chạy**.

Cần phân biệt:

| Đại lượng | Một listener | Hai listeners cùng type |
| --- | ---: | ---: |
| Số lần `publishEvent` cho một command | 1 | 1 |
| `OrderSubmittedListener` được gọi | 1 | 1 |
| `AuditListener` được gọi | 0 | 1 |
| Tổng số handler invocations | 1 | 2 |

Không kết luận "Spring phát hai event" chỉ vì thấy hai dòng log của hai listeners. Nếu cần ràng buộc thứ tự giữa listener methods, có thể dùng `@Order`; không dựa vào thứ tự đăng ký bean ngẫu nhiên, đặc biệt khi đổi sang async.

Hãy chạy ví dụ gốc và xác minh output **trước** khi thêm listener này, vì stdout sau khi mở rộng đương nhiên có thêm dòng audit.

## 10. Xử lý lỗi và cấu hình đồng bộ

Trong ví dụ gốc, listener chạy trong publisher thread. Nếu listener ném unchecked exception, nó có thể truyền ngược qua `publishEvent(...)` tới `submit(...)`:

```java
// Trích đoạn minh họa, không thay toàn bộ code chính.
@EventListener
public void onSubmitted(OrderSubmitted event) {
    if ("ORD-FAIL".equals(event.orderId())) {
        throw new IllegalStateException("listener failed");
    }
}
```

Khi không có `ErrorHandler` đặc biệt nuốt exception, method `submit` có thể dừng tại `publishEvent` và không in `publisher: returned ORD-FAIL`. Điều này giúp hiểu vì sao event **mặc định không phải fire-and-forget**.

Những điểm cần lưu ý:

- Một listener không nên tự ý nuốt mọi exception rồi báo success giả.
- Nếu có nhiều listeners, listener trước có thể đã thực hiện side effect trước khi listener sau thất bại.
- Nếu nằm trong một transaction, unchecked exception lan qua transaction boundary có thể gây rollback theo chính sách của Spring; **nhưng demo không có transaction**.
- Một HTTP request/email đã gửi ra ngoài không tự được rollback cùng database.
- Không retry mù toàn bộ `publishEvent` khi một listener lỗi vì có thể gọi lại những listener đã thành công.

Hãy tách rõ **event dispatch** khỏi **nghiệp vụ bắt buộc** và chính sách xử lý side effect.

## 11. Nếu cần xử lý bất đồng bộ?

Bài tập này **không bật async**. Trong Spring, có thể dùng `@Async` trên listener với `@EnableAsync` và executor phù hợp, hoặc cấu hình `SimpleApplicationEventMulticaster` dùng task executor.

So sánh:

| Hành vi | Đồng bộ mặc định | Async cần cấu hình |
| --- | --- | --- |
| Listener thread | Thường là publisher thread | Có thể là worker thread |
| `publishEvent` trả về | Sau khi handler sync hoàn tất | Có thể trước khi handler hoàn tất |
| Thứ tự stdout | Dễ dự đoán với một listener | Không bảo đảm như demo |
| Exception | Có thể lan về publisher | Cần async error handling |
| Transaction context | Có thể cùng thread | Không tự chuyển transaction thread-bound |
| Test invocation count | Assert ngay có thể hợp lý | Cần chờ completion signal |

Nếu tự thêm `@Async`, đừng giữ assertion `receivedCount() == 2` ngay sau lệnh publish và cho rằng nó luôn đúng; worker có thể chưa xử lý xong. Test nên dùng `CountDownLatch`, future hoặc một cơ chế await với deadline.

Async chỉ thay đổi execution; nó **không tạo hàng đợi bền vững**. Khi có yêu cầu bảo đảm delivery qua process crash, cần kiến trúc khác như transactional outbox, broker hoặc job queue phù hợp.

## 12. Phân biệt event thường, transactional event và integration event

- **Spring application event:** cơ chế truyền thông báo giữa beans trong cùng context, như ví dụ ở đây.
- **`@TransactionalEventListener`:** phản ứng event theo transaction phase, mặc định `AFTER_COMMIT`. Nếu không có transaction, listener loại này mặc định không chạy trừ khi `fallbackExecution=true`.
- **Integration event:** hợp đồng chia sẻ giữa các ứng dụng, thường phải quan tâm schema version, serialization, broker, auth, retry và idempotency.
- **Transactional outbox:** mô hình ghi intent phát message trong cùng transaction với thay đổi state, giúp relay tiếp tục sau crash.

Không đánh đồng `publishEvent` với lệnh `KafkaTemplate.send`. Một Spring event có thể được bridge sang broker bởi listener tự viết, nhưng lúc đó phải thiết kế tính nhất quán: gửi ra broker trước commit có thể tạo message cho một transaction sau đó rollback. `AFTER_COMMIT` cho đúng thời điểm nhưng tự nó chưa bảo đảm durable delivery.

Trong bài tối thiểu chưa có DB, do đó `OrderSubmitted` chỉ được hiểu là service **đã chấp nhận lệnh submit**; không được tuyên bố "đã lưu đơn hàng" hay "đã thanh toán" khi không có persistence hoặc payment thật.

## 13. Thiết kế payload và tên event tốt

`OrderSubmitted` nên được đặt tên ở quá khứ hoặc mô tả rõ fact mà system đã xác nhận. Đừng gọi sự kiện `EmailSent` khi mới gửi yêu cầu email vào queue; đó là việc khác với email đã gửi thực tế.

Payload tối thiểu giúp giảm coupling:

- Chỉ chứa những giá trị mà listeners cần để phản ứng.
- Tránh copy cả request DTO/JPA entity có nhiều field không liên quan.
- Không đưa password, OTP, access token, khóa bí mật, số thẻ hoặc PII không cần thiết.
- Dùng record/immutable DTO; chú ý record là **shallow immutable**. Nếu record chứa `List` mutable, nội dung collection vẫn có thể thay đổi; defensive copy khi cần.
- Nếu một listener cần current state, cân nhắc tham chiếu ID và tra cứu có phân quyền. ID vẫn có thể là dữ liệu cá nhân gián tiếp nếu liên kết được với chủ thể.
- Khi có nhiều consumer hoặc broker, xác định snapshot semantics, version và retention rõ.

Trong demo, `amountInCents` là số nguyên đơn vị nhỏ của **một quy ước giả định**. Với sản phẩm nhiều tiền tệ cần quy ước Money/`amountMinor + currency` chính xác, không dùng cents cho mọi loại tiền.

## 14. Kiểm thử sự kiện theo từng tầng

Ngay trong `main`, chương trình xác minh:

1. Hai command hợp lệ được service chấp nhận.
2. Mỗi command gọi publisher một lần theo logic đã viết.
3. Listener nhận và đếm cả hai event trong cấu hình sync.
4. Input amount bằng 0 bị từ chối **trước khi publish**.
5. Kiểm tra cuối cùng ném `IllegalStateException` nếu listener count không đạt 2.

Khi có framework test, chia trách nhiệm rõ:

**Unit test của publisher:** dùng Mockito mock `ApplicationEventPublisher`. Ví dụ ý tưởng (không phải class test đầy đủ):

```java
ApplicationEventPublisher mockPublisher =
        mock(ApplicationEventPublisher.class);
OrderService service = new OrderService(mockPublisher);

service.submit("ORD-001", 1250);

verify(mockPublisher, times(1))
        .publishEvent(any(OrderSubmitted.class));
verifyNoMoreInteractions(mockPublisher);
```

Đoạn này cần dependency Mockito, static imports và các class demo. Nó xác nhận **lời gọi publisher**, không chạy Spring listener thật. Với input invalid, dùng `verifyNoInteractions(mockPublisher)`. Có thể dùng `ArgumentCaptor<OrderSubmitted>` để assert payload.

**Integration test của Spring:** dùng Spring TestContext, `@RecordApplicationEvents` và `ApplicationEvents.stream(OrderSubmitted.class)` để record/đếm event được publish trong test method. Kèm listener spy/counter nếu cần chứng minh handler invocation. Lưu ý recorder đếm event đã publish chứ không tự đồng nghĩa event đã commit hoặc broker delivery.

**Nếu async:** đợi xử lý hoàn tất với timeout, không `Thread.sleep(500)` và đoán. Nếu có nhiều listeners, tổng handler invocations có thể lớn hơn số publisher calls.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy dòng `listener: ...` | Listener không phải Spring bean | Xác nhận `@Bean orderSubmittedListener()` hoặc component scan |
| Listener không nhận event | Parameter type sai | `onSubmitted(OrderSubmitted event)` đúng class/package |
| `@EventListener` không có tác dụng | Tạo listener bằng `new` ngoài container; lazy bean | Đưa listener vào Spring-managed context |
| Chỉ thấy `publisher: accepted` | Listener ném exception | Kiểm tra stack trace, error policy |
| Maven không compile | JDK cũ hoặc sai tên file/package | `mvn -version`, `MinimalEventDemo.java`, `package demo` |
| `NoClassDefFoundError` | Dependencies không đúng | Xem POM, Maven resolve và classpath |
| `mainClass not found` | `exec-maven-plugin` trỏ nhầm | `demo.MinimalEventDemo` |
| Listener chạy nhiều lần | Publisher gọi nhiều lần hoặc nhiều nguồn phát | Đếm publisher calls và event IDs |
| Mất thứ tự log khi thêm async | Worker chạy thread khác | Chờ completion, không phụ thuộc thứ tự |
| Không thấy event sau crash | Chỉ lưu trong JVM | Cần durable outbox/queue nếu hợp đồng yêu cầu |

Đừng tìm một annotation `@EnableEvents`: với annotation-configured Spring ApplicationContext, không cần annotation này để dùng `@EventListener`. `@EnableAsync` chỉ liên quan khi muốn kích hoạt hỗ trợ async qua annotation.

### Vì sao không gọi listener trực tiếp?

`listener.onSubmitted(event)` là method call bình thường, không chứng minh Spring registration/dispatch hoạt động. Có thể gọi trực tiếp nếu semantics là orchestration bắt buộc; để học Spring events, gọi `publisher.publishEvent(event)` như demo.

### Có thể có không listener nào không?

Có. Nếu không có bean/method phù hợp, một event có thể được publish mà không có business listener nào xử lý. `publishEvent` không mặc định báo lỗi "không ai nhận". Vì vậy nếu event là thiết yếu cho business correctness, cần thiết kế thêm validation/observability và architecture phù hợp thay vì cho rằng event bus bảo đảm có consumer.

## 16. Bài luyện tập mở rộng

**Bài 1 — Thêm một event hợp lệ.** Gọi `service.submit("ORD-004", 3300)` trước lệnh invalid, điều chỉnh self-check thành 3. Kỳ vọng listener count là 3, còn invalid vẫn không phát event.

**Bài 2 — Kiểm tra order ID rỗng.** Gọi `service.submit("", 100)` trong `try/catch`; không có dòng listener mới. Thay input bằng `null` và kiểm tra service từ chối tương tự.

**Bài 3 — Thêm audit listener.** Tạo bean `AuditListener` với `@EventListener` nhận `OrderSubmitted`. Một event làm hai handlers phản ứng nhưng publisher vẫn chỉ gọi `publishEvent` một lần. Nếu cần thứ tự giữa các listener, nghiên cứu `@Order`.

**Bài 4 — Thêm event type khác.** Tạo `record OrderCancelled(String orderId) {}` và listener dành riêng cho nó. Kiểm tra `OrderSubmittedListener` không bị gọi khi chỉ publish `OrderCancelled`.

**Bài 5 — Thử exception propagation.** Tạo nhánh listener ném `IllegalStateException` khi order ID là `ORD-FAIL`; quan sát có in `publisher: returned ORD-FAIL` hay không trong default sync setup. Không retry toàn bộ publication khi listener khác đã hoàn thành.

**Bài 6 — Viết JUnit integration test.** Dùng Spring TestContext `@RecordApplicationEvents` đếm 0/1/2 event theo các lệnh. Thêm Mockito unit test để xác nhận số lần gọi publisher và dữ liệu record.

**Bài 7 — Thử Boot sau khi hiểu core.** Thay context thủ công bằng Spring Boot application, đăng ký service/listener bằng `@Component` và dùng `ApplicationRunner` gọi service. Kiểm tra không có sự khác biệt bản chất về loại event và `@EventListener`.

**Bài 8 — Vạch ranh giới production.** Giả sử listener cần gửi email, hãy chọn giữa listener đồng bộ, after-commit hoặc outbox tùy yêu cầu. Nêu rõ transaction, retry, idempotency và thời điểm thật sự hoàn thành; không mặc định thêm `@Async` là đủ.

## 17. Checklist tự đánh giá

- [ ] Tạo đúng `pom.xml` và `src/main/java/demo/MinimalEventDemo.java`.
- [ ] Có JDK 17+ và chạy `mvn -q clean compile exec:java` thành công.
- [ ] Event là một Java record đơn giản, không cần `extends ApplicationEvent`.
- [ ] Publisher service inject `ApplicationEventPublisher` và phát event sau validation.
- [ ] Listener là Spring-managed bean, method có `@EventListener` và đúng parameter type.
- [ ] Application context đăng ký đầy đủ publisher và listener.
- [ ] Có hai lần `listener: ...` tương ứng ORD-001 và ORD-002.
- [ ] Command ORD-003 amount 0 bị từ chối trước publish.
- [ ] Kết quả cuối `main: handled=2`; self-check không ném exception.
- [ ] Hiểu vì sao listener đồng bộ chạy trước `publisher: returned` trong ví dụ.
- [ ] Phân biệt số lần publisher gọi với tổng số listener invocations.
- [ ] Biết rằng Spring in-process event không phải durable broker message.
- [ ] Biết nguyên tắc không đưa secrets và PII không cần thiết vào event.

## 18. Câu hỏi ôn tập

1. **Publisher và listener được nối với nhau ra sao?** — Qua Spring `ApplicationEventPublisher` và multicaster trong context.
2. **Vì sao publisher không import listener?** — Nó chỉ công bố event; listeners được đăng ký độc lập.
3. **Record có cần extends ApplicationEvent không?** — Không; `publishEvent(Object)` hỗ trợ POJO.
4. **Đặt @EventListener trên class không do Spring quản lý có chạy không?** — Không tự được đăng ký.
5. **Listener được chọn theo điều kiện nào trong demo?** — Kiểu event `OrderSubmitted`.
6. **Hai event hợp lệ và một lệnh sai tạo bao nhiêu callback?** — Hai callback cho một listener phù hợp trong default sync setup.
7. **Một event có ba listeners nghĩa là ba lần publish?** — Không, một lần publish có thể kích hoạt cả ba.
8. **Tại sao dòng listener xuất hiện trước publisher returned?** — Multicaster mặc định đồng bộ, với một listener.
9. **Listener ném exception có thể khiến publisher lỗi không?** — Có khi đồng bộ và không bị handler nuốt.
10. **@Async có làm event bền vững không?** — Không.
11. **@TransactionalEventListener(AFTER_COMMIT) có tự hoạt động ngoài transaction không?** — Mặc định không, trừ `fallbackExecution` phù hợp.
12. **Khi nào cần integration event riêng?** — Khi đưa sự kiện ra ứng dụng khác, cần contract/schema/delivery/security.
13. **Unit test mock publisher chứng minh điều gì?** — Số lần gọi publish và payload; không chứng minh listener thật đã chạy.
14. **Phải làm gì khi có thông tin nhạy cảm?** — Áp dụng payload minimization, authorization và chính sách logs/retention.

## Tài liệu tham khảo

- [Spring Framework — Application Events và Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2.8 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2.8 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
