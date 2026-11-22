# Listener không được gọi trong Spring Framework Application Events — quy trình chẩn đoán

## 1. Nhận diện đúng triệu chứng

Khi gọi:

```java
publisher.publishEvent(new OrderSubmitted("O-101"));
```

nhưng không thấy phương thức `@EventListener` chạy, có ít nhất **bốn khả năng khác nhau**:

1. **Không có event thực sự được publish** trên đường thực thi cần kiểm tra: nhánh `if` không tới, exception xảy ra trước lời gọi hoặc code gọi nhầm publisher/context.
2. **Listener không được Spring đăng ký**: bean nằm ngoài component scan, không phải Spring-managed bean, được khai báo lazy hoặc hạ tầng nhận annotation chưa được khởi tạo.
3. **Event đã được công bố nhưng không khớp listener**: sai Java type/generic, điều kiện SpEL cho kết quả `false`, listener nằm ở context không nhận event nguồn.
4. **Listener đã được đăng ký nhưng chưa đến lúc chạy / không đủ điều kiện chạy**: `@TransactionalEventListener` đang chờ commit hoặc bị bỏ qua vì không có transaction, listener async vẫn đang chờ executor, hoặc exception đã bị xử lý/log ở thread khác.

Hai câu hỏi đầu tiên nên tách riêng:

- **Publisher có phát đúng event không?** Xác minh `publishEvent` được gọi, loại và payload chính xác.
- **Event có được listener mục tiêu nhận/xử lý không?** Xác minh bean đăng ký, event type, context, filter, transaction phase và thời điểm thực thi.

Một dòng log không xuất hiện **chưa đủ chứng minh** listener hoàn toàn không được gọi. Log có thể bị lọc mức, gửi sang logger khác hoặc việc xử lý bất đồng bộ vẫn chưa hoàn thành.

Bài này tập trung vào ứng dụng Spring Framework sử dụng `ApplicationEventPublisher`, `ApplicationListener`, `@EventListener` và `@TransactionalEventListener`. Các lưu ý Spring Boot được trình bày riêng vì thứ tự khởi động Boot có thêm những event rất sớm.

## 2. Nắm luồng xử lý trước khi sửa code

Đường đi của một event trong ứng dụng có thể hình dung:

```text
Business code
  |
  +-- ApplicationEventPublisher.publishEvent(EventA)
          |
          +-- ApplicationContext nhận event
                  |
                  +-- ApplicationEventMulticaster
                          |
                          +-- Tìm listener đã đăng ký
                          |
                          +-- Lọc theo event type / generic
                          |
                          +-- Kiểm tra condition (nếu có)
                          |
                          +-- @EventListener thường:
                          |       gọi handler đồng bộ (mặc định)
                          |       hoặc submit task async
                          |
                          +-- @TransactionalEventListener:
                                  đăng ký callback theo transaction phase
                                  và chỉ chạy khi điều kiện phase thỏa
```

Spring mặc định sử dụng `SimpleApplicationEventMulticaster` và dispatch **đồng bộ trên publisher thread**. Khi cấu hình executor cho multicaster hoặc dùng `@Async`, đường đi trở thành bất đồng bộ và cần kiểm tra riêng.

**`publishEvent` trả về `void`**: không trả số listener đã gọi, không trả kết quả xử lý và không xác nhận các side effect (DB, email, HTTP) đã thành công. Nếu code có custom multicaster hoặc error handler, hành vi báo lỗi cũng có thể khác mặc định.

Bảng xác định nhanh:

| Bằng chứng đã có | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| Spy/mock thấy `publishEvent(OrderA)` | Business code đã gọi publisher | Spring context đã dispatch đến listener thật |
| `@RecordApplicationEvents` thấy `OrderA` | Spring Test context đã ghi nhận event được công bố | Listener async đã xử lý xong |
| Breakpoint vào handler | Handler thực sự được gọi | Transaction đã commit hoặc side effect đã hoàn tất |
| Log từ listener `AFTER_COMMIT` | Callback hậu commit đã được kích hoạt | Task async/bên ngoài được lưu bền vững |
| Không thấy log | Chưa có bằng chứng trực quan | Không đủ để khẳng định event chưa được phát |

## 3. Quy trình chẩn đoán ít bước, có kiểm chứng

Thay vì đổi annotation ngẫu nhiên, nên đi theo thứ tự:

1. **Kiểm tra publisher:** đặt breakpoint ngay trước/sau `publishEvent`, log **event class** và ID nghiệp vụ; loại trừ nhánh code không chạy.
2. **Kiểm tra bean listener:** xác nhận class listener là Spring-managed bean trong context mục tiêu, không bị `@Lazy` khiến method listener chưa đăng ký.
3. **Kiểm tra kiểu event:** đối chiếu kiểu runtime của object được publish với tham số `@EventListener` hoặc generic `ApplicationListener<T>`; đặc biệt chú ý wrapper và generic.
4. **Kiểm tra `condition`:** bỏ tạm filter trong một test cô lập hoặc kiểm tra SpEL với đúng payload/argument.
5. **Kiểm tra context:** event và listener có ở cùng `ApplicationContext` hoặc theo hướng propagation cha/con phù hợp không?
6. **Kiểm tra transaction:** listener có `@TransactionalEventListener` không? Event được publish **bên trong** transaction còn hoạt động chứ? Transaction kết thúc bằng commit hay rollback?
7. **Kiểm tra async:** listener có dùng `@Async`/executor không? Có bị từ chối submit, có exception trong worker, test có chờ hoàn tất không?
8. **Xác minh bằng test:** viết một test có thể tái hiện và quan sát event; chỉ sau đó mới thay đổi thiết kế.

Cách này giảm khả năng sửa nhầm một listener đang hoạt động bình thường nhưng **chưa đến phase chạy**.

## 4. Nguyên nhân 1: listener không phải bean được Spring quản lý

Phương thức `@EventListener` trên một object tự tạo bằng `new` **không tự đăng ký** với Spring event infrastructure:

```java
public class OrderObserver {

    @EventListener
    public void onSubmitted(OrderSubmitted event) {
        System.out.println("submitted " + event.id());
    }
}

// Trong code khác:
OrderObserver observer = new OrderObserver(); // Không tạo listener trong context.
```

Đây là **mã minh họa**, chưa phải chương trình độc lập. Spring chỉ tự phát hiện phương thức annotation trên **bean thuộc ApplicationContext** được cấu hình tương ứng.

Cách phổ biến trong Spring Boot:

```java
@Component
public class OrderObserver {

    @EventListener
    public void onSubmitted(OrderSubmitted event) {
        // Được đăng ký nếu bean nằm trong vùng component scan.
    }
}
```

Cần import `org.springframework.stereotype.Component` và `org.springframework.context.event.EventListener`.

Hoặc khai báo bean bằng Java configuration:

```java
@Configuration
public class EventsConfig {

    @Bean
    OrderObserver orderObserver() {
        return new OrderObserver();
    }
}
```

Đây là đoạn minh họa; cần import `Configuration` và `Bean`. Chọn **một** cách đăng ký hợp lý, không cố vừa tạo bean thủ công vừa component scan nhiều bản sao mà không kiểm soát.

### 4.1. Sai phạm vi component scan

`@SpringBootApplication` bao gồm component scan bắt đầu từ package chứa main/configuration class và các package con, theo mặc định. Nếu handler nằm ở package anh em hoặc ngoài phạm vi, nó sẽ không trở thành bean trừ khi bạn mở rộng cấu hình.

Ví dụ:

```text
com.example.app.MainApplication
com.example.app.orders.OrderService
com.example.events.OrderObserver   <- có thể nằm ngoài scan mặc định
```

Không nên sửa bằng cách scan tất cả package ở root hệ thống. Hãy đặt configuration ở package cha thích hợp hoặc khai báo `@ComponentScan`/`@Import` có chủ đích. Trong ứng dụng Spring Framework thuần, bảo đảm đã `@ComponentScan` hoặc `@Import` đúng package, hoặc định nghĩa `@Bean`.

**Kiểm tra được:** nếu dùng context xác định, có thể kiểm tra `context.getBean(OrderObserver.class)` hoặc xem tên bean trong `getBeanNamesForType`, thay vì chỉ nhìn sự hiện diện của annotation trong source. Tuy nhiên có bean **chưa đủ** nếu listener không khớp event hoặc chưa đăng ký method.

### 4.2. `@Lazy` là bẫy riêng đối với `@EventListener`

Spring Framework lưu ý **không nên định nghĩa bean listener `@EventListener` thành lazy**: context sẽ tôn trọng lazy initialization và **không đăng ký phương thức để lắng nghe event** trong đường xử lý thường dùng.

Ví dụ dễ bỏ sót:

```java
@Component
@Lazy
public class LazyOrderObserver {

    @EventListener
    public void handle(OrderSubmitted event) {
        // Có thể không được đăng ký làm event listener.
    }
}
```

Đây là mã minh họa; cần import `Lazy` và `Component`. Không dùng `@Lazy` như một cách tối ưu hóa không kiểm tra cho các bean có event handler quan trọng. Nếu ứng dụng bật global lazy initialization, cần kiểm tra tác động tới bean listener và bảo đảm eager initialization ở nơi cần.

Lời khuyên thực tế: thử một bean listener tối giản, không lazy, được khởi tạo bởi context; nếu event được nhận, tiếp tục điều tra cấu hình bean thực tế.

### 4.3. Hạ tầng xử lý `@EventListener`

`@EventListener` được hỗ trợ bởi cơ chế bean post-processing của Spring, trong đó có `EventListenerMethodProcessor`. Với `AnnotationConfigApplicationContext` hoặc cấu hình Boot thông thường, hạ tầng annotation cần thiết đã được đăng ký.

Nếu bạn tự dựng một `GenericApplicationContext` rất tối giản, đăng ký bean definitions thủ công mà **không đăng ký các annotation configuration processors**, đừng mặc định `@EventListener` sẽ tự được quét như trong Boot. Sửa bằng cách cấu hình Spring annotation infrastructure đúng cách, không tự gọi method listener để "giả" rằng event bus hoạt động.

## 5. Nguyên nhân 2: event type hoặc generic không khớp

Spring lọc listener theo **kiểu event**. Hai class trùng tên đơn giản nhưng khác package vẫn là hai kiểu khác nhau.

```java
public record OrderCreated(String id) {}
public record OrderConfirmed(String id) {}

@EventListener
public void onConfirmed(OrderConfirmed event) {
    // Không nhận một OrderCreated được publish.
}
```

Mã minh họa: `publisher.publishEvent(new OrderCreated("O-1"))` không khiến `onConfirmed` chạy.

### 5.1. `ApplicationEvent` subclass và object payload

Spring hỗ trợ cả:

```java
public class OrderCreatedEvent extends ApplicationEvent {
    public OrderCreatedEvent(Object source) {
        super(source);
    }
}
```

và payload Java thông thường:

```java
public record OrderCreated(String id) {}
```

Nếu object không kế thừa `ApplicationEvent`, Spring có thể bọc trong `PayloadApplicationEvent` để dispatch. Nhưng một handler `@EventListener` nhận **chính payload type** vẫn là cách thông dụng:

```java
@EventListener
public void onCreated(OrderCreated event) {
    // Nhận payload record.
}
```

Đừng vô tình viết `@EventListener` chỉ nhận `OrderCreatedEvent` nếu publisher lại phát `OrderCreated` record. Cũng đừng tự bọc payload bằng một wrapper khác rồi kỳ vọng listener typed cho payload bên trong luôn được unwrap tùy ý.

### 5.2. Generic type erasure

Ví dụ:

```java
public class EntityChanged<T> extends ApplicationEvent {
    public EntityChanged(T entity) {
        super(entity);
    }
}

@EventListener
public void onCustomerChanged(EntityChanged<Customer> event) {
    // Phụ thuộc generic metadata có thể phân giải ở runtime.
}
```

Đây là **mã minh họa**, cần định nghĩa `Customer`. Do Java generic type erasure, Spring không luôn biết `EntityChanged<Customer>` từ một `new EntityChanged<>(customer)` đơn thuần. Nếu cần lọc theo generic, dùng subtype cố định như `CustomerChangedEvent extends EntityChanged<Customer>` hoặc `ResolvableTypeProvider` theo tài liệu chính thức.

**Chẩn đoán:** tạm dùng một listener cho event concrete class cụ thể trong test để xác minh dispatch; sau đó mới bổ sung generic filter.

### 5.3. Annotation method và chữ ký

Phương thức `@EventListener` đơn giản nhất nhận **một tham số event**, hoặc không tham số khi chỉ định event types trên annotation:

```java
@EventListener(OrderCreated.class)
public void createdWithoutArgument() {
    // Không yêu cầu parameter vì đã chỉ rõ class.
}
```

Mã minh họa. Với method có một tham số, Spring thường suy ra event type từ chính tham số. Phương thức có nhiều tham số không tương thích contract `@EventListener` có thể làm cấu hình thất bại hoặc không hoạt động như bạn tưởng. Kiểm tra lỗi startup thực tế; đừng đổi sang nhiều tham số như một controller method.

## 6. Nguyên nhân 3: `condition` SpEL loại event

Một listener có thể **được đăng ký đúng** nhưng expression trong `condition` cho `false`:

```java
@EventListener(condition = "#a0.state() == 'READY'")
public void onReady(TicketEvent event) {
    // Chỉ nhận event có state() == "READY".
}
```

Mã minh họa với `TicketEvent` là record có phương thức `state()`; `#a0` tham chiếu đối số đầu tiên, tránh phụ thuộc tên parameter được lưu trong bytecode.

Nếu publish `new TicketEvent("T-1", "REJECTED")`, listener **không chạy là hành vi đúng**.

Cần kiểm tra:

- Giá trị thực trong event: `"READY"` khác `"ready"` hoặc `"READY "`.
- Expression gọi đúng property/method trong payload type không?
- `#a0`, `#p0`, tên tham số hay `#root.event` được dùng đúng ngữ cảnh chưa?
- Code có build option `-parameters` nếu expression phụ thuộc tên parameter không?
- Nếu event là payload object, `#root.event` có thể là `PayloadApplicationEvent`, không phải record trực tiếp.
- Có exception trong evaluation expression không? Nếu có, kiểm tra stack trace, không diễn giải là filter đơn thuần.

Trong một test cô lập, so sánh một listener **không có condition** với listener **có condition**. Nếu listener đầu chạy và listener sau không, gần như đã khoanh vùng được vấn đề vào expression hoặc dữ liệu đầu vào.

## 7. Nguyên nhân 4: publish sai `ApplicationContext` hoặc sai hướng propagation

Spring event infrastructure gắn với **ApplicationContext**. Trong hệ thống có parent/child contexts (ví dụ cấu hình web cũ, nhiều servlet contexts hoặc test dựng hai context), listener có thể nằm trong context **khác** với publisher.

Hướng propagation quan trọng:

```text
Parent ApplicationContext
  |
  +-- listeners của Parent
  |
  +-- Child ApplicationContext
         |
         +-- listeners của Child
```

- Event publish ở **Child** thường được xử lý trong Child và sau đó propagate **lên Parent**.
- Event publish ở **Parent** **không mặc định truyền xuống Child**.
- Hai context độc lập không có quan hệ cha/con **không có một bus event chung**.
- Listener ở cả Parent và Child hoặc event được republish có thể gây quan sát trùng; đó là vấn đề khác với "không được gọi".

Ví dụ phản ví dụ:

```java
try (var first = new AnnotationConfigApplicationContext(FirstConfig.class);
     var second = new AnnotationConfigApplicationContext(SecondConfig.class)) {

    first.publishEvent(new OrderCreated("O-1"));
    // Bean listener chỉ đăng ký trong second sẽ không nhận event này.
}
```

Đây là mã minh họa; `FirstConfig`, `SecondConfig` do ứng dụng định nghĩa. Đừng tạo một `new AnnotationConfigApplicationContext` phụ trong service để phát event rồi kỳ vọng listener của Boot application context chính nhận được.

**Chẩn đoán:** ghi `ApplicationContext.getId()` ở publisher và listener nếu có thể, xác minh object context và quan hệ cha/con. Với listener không chạy, so sánh bean registrations trong đúng context, không suy đoán từ một context khác.

## 8. Nguyên nhân 5: `@TransactionalEventListener` cần transaction và đúng phase

Đây là nguyên nhân thường gặp nhất khi code "publish thành công nhưng listener không hề log".

```java
@TransactionalEventListener
public void afterCommit(OrderCreated event) {
    // Mặc định phase = TransactionPhase.AFTER_COMMIT.
}
```

Nếu event được phát **ngoài transaction**, listener transactional mặc định **không chạy**. Hành vi đó được chủ ý thiết kế: không có transaction đang hoạt động thì Spring không thể xác định pha commit/rollback của event.

Có thể cấu hình:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void afterCommitOrFallback(OrderCreated event) {
    // Có thể xử lý cả khi không có transaction.
}
```

Nhưng `fallbackExecution=true` **không tạo ra một commit giả**. Nó có thể cho phép listener chạy khi không có transaction, nên phải kiểm tra nghĩa nghiệp vụ trước khi bật. Với logic "chỉ gửi xác nhận nếu DB commit", giữ mặc định `false` thường an toàn hơn và bảo đảm publisher nằm đúng trong transaction.

### 8.1. Phase của listener và kết quả transaction

| Listener phase | Chạy khi nào? | Vì sao không thấy chạy? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Callback trước commit, transaction chưa hoàn tất | Transaction bị rollback trước commit |
| `AFTER_COMMIT` (**mặc định**) | Sau commit thành công | Không có transaction hoặc transaction rollback |
| `AFTER_ROLLBACK` | Sau transaction rollback | Transaction lại commit thành công |
| `AFTER_COMPLETION` | Sau commit hoặc rollback | Không có transaction để đăng ký hoặc callback chưa tới thời điểm |

Phân biệt **event đã publish** và **transaction đã hoàn tất**. Một listener thường `@EventListener` có thể chạy ngay trong transaction, còn transactional listener chỉ đăng ký callback và chờ pha phù hợp.

### 8.2. Lỗi self-invocation của `@Transactional`

```java
@Service
public class OrderService {

    public void createOrder() {
        this.saveAndPublish(); // Bỏ qua proxy theo cơ chế mặc định.
    }

    @Transactional
    public void saveAndPublish() {
        publisher.publishEvent(new OrderCreated("O-1"));
    }
}
```

Đây là **mã minh họa**, cần `publisher` inject và các import phù hợp. Ở chế độ proxy-based transaction mặc định, lời gọi `this.saveAndPublish()` không đi qua proxy nên transaction advice có thể không được áp dụng.

Kết quả: event vẫn được publish, listener thường có thể nhận, nhưng `@TransactionalEventListener` có `fallbackExecution=false` **bị bỏ qua vì không có transaction**.

Cách sửa: gọi transactional method **qua Spring proxy từ bean khác**, hoặc dùng `TransactionTemplate` tạo transaction lập trình. Đừng thêm `@Transactional` lên chính listener rồi nghĩ nó làm event publish trước đó trở thành transaction-bound; transaction phải tồn tại **khi event được phát**.

### 8.3. `@Async` làm mất transaction context của publisher thread

Với transaction imperative do `PlatformTransactionManager` quản lý, context transaction thường được giữ ở `ThreadLocal`. Nếu chuyển `publishEvent()` sang executor thread không có transaction, listener transaction-bound không thấy transaction đó.

```text
Thread A:
  BEGIN T1
  submit async task
      |
      +-- Thread B:
              publishEvent(E)
              không có transaction T1 thread-bound
  COMMIT T1
```

Đây là minh họa, không phải bảo đảm mọi async call có transaction. Nếu cần event gắn với commit của T1, **publish event trong T1** rồi dùng `@TransactionalEventListener(AFTER_COMMIT)`; nếu muốn xử lý hậu commit async, có thể gắn `@Async` cho handler với cấu hình phù hợp. Tránh đưa entity JPA/request object mutable sang worker thread.

Spring reactive transaction dùng Reactor Context; từ Spring 6.1, transaction-bound event hỗ trợ reactive nhưng cần mang ngữ cảnh transaction theo cơ chế `TransactionalEventPublisher` thích hợp. Không dùng `ThreadLocal` như tiêu chuẩn chẩn đoán cho reactive flow.

## 9. Nguyên nhân 6: `@Async` listener chưa chạy, bị từ chối hoặc lỗi ở worker

Khi handler dùng:

```java
@Async("eventExecutor")
@EventListener
public void handle(OrderCreated event) {
    // Chạy trên executor thread.
}
```

thì publisher có thể trả về trước khi worker bắt đầu thực thi. Lỗi trong `void @Async` method **không tự truyền về caller**. Ngoài ra, nếu thiếu `@EnableAsync`, bean không qua proxy hoặc executor cấu hình sai, kỳ vọng về thread/time sẽ không khớp.

Những trường hợp cần phân biệt:

- **Chưa chạy:** task còn trong queue.
- **Không submit được:** executor shutdown/queue đầy/rejection policy.
- **Đã chạy nhưng lỗi:** exception ở worker bị logging/`AsyncUncaughtExceptionHandler` xử lý.
- **Đã chạy ở thread khác:** bạn đang xem log/debugger của thread publisher hoặc thiếu trace/MDC.
- **Đã chạy ngay:** `@Async` không được áp dụng vì thiếu configuration hoặc self-invocation, không nhất thiết là "listener không gọi".
- **Không có context:** worker thiếu `RequestContextHolder`, MDC, `SecurityContextHolder` hoặc JDBC transaction, khiến handler thất bại khi truy cập tài nguyên.

Nên kiểm thử bằng `CountDownLatch`/`CompletableFuture`/Awaitility có timeout, tránh `Thread.sleep(100)` rồi khẳng định listener bị bỏ qua. Kiểm tra executor metrics, task rejection và uncaught exception handler. Nếu dùng custom `applicationEventMulticaster`, kiểm tra `TaskExecutor` và `ErrorHandler` đã cấu hình.

### 9.1. Self-invocation của `@Async`

```java
@Component
class AsyncService {

    void start() {
        this.process(); // Không đi qua Spring async proxy.
    }

    @Async
    public void process() {
        // Có thể thực thi trên thread gọi start().
    }
}
```

Đây là mã minh họa; nguyên nhân là proxy bị bỏ qua. Listener `@Async @EventListener` chuẩn được event infrastructure gọi trên bean do Spring quản lý sẽ qua async proxy thích hợp; nhưng tự gọi method async từ cùng instance có thể khác hoàn toàn. Không dùng `this.method()` làm phép thử tính bất đồng bộ.

## 10. Ví dụ Java 17+ chạy được: phân biệt listener thường, condition và transaction phase

Ví dụ sau dùng **Spring Framework 6.2.12**, `spring-jdbc`, H2 in-memory, Gradle và JDK 17+. Không cần Spring Boot hoặc web server. Đây là một chương trình console **có thể chạy độc lập** khi dependencies được tải.

Mục đích:

1. Phát `TicketEvent("N-1", "READY")` **ngoài transaction**.
2. Phát `TicketEvent("C-1", "READY")` trong transaction **commit**.
3. Phát `TicketEvent("R-1", "REJECTED")` trong transaction **rollback-only**.
4. Đếm bốn nhóm callback: `@EventListener` thường, listener có SpEL condition, listener `AFTER_COMMIT`, listener `AFTER_ROLLBACK`.
5. Tránh phụ thuộc thứ tự giữa hai `@EventListener` thường; mỗi lần chỉ so sánh **tổng counters sau khi bước kết thúc**.

### 10.1. Cấu trúc

```text
spring-listener-diagnostics/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/ListenerNotCalledDemo.java
    └── test/java/demo/EventDiagnosticsTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-listener-diagnostics'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
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
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'

    testImplementation 'org.springframework:spring-test:6.2.12'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

application {
    mainClass = 'demo.ListenerNotCalledDemo'
}

test {
    useJUnitPlatform()
}
```

`DriverManagerDataSource` chỉ phù hợp demo ngắn; production nên dùng connection pool có cấu hình giới hạn và timeout. Trong demo, H2 cung cấp một connection thật để `DataSourceTransactionManager` quản lý các transaction; không cần tạo bảng vì bài chỉ quan sát phase và không thao tác dữ liệu DB.

### 10.2. `src/main/java/demo/ListenerNotCalledDemo.java`

```java
package demo;

import javax.sql.DataSource;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class ListenerNotCalledDemo {

    public record TicketEvent(String id, String state) {}

    public static class IssuerService {
        private final ApplicationEventPublisher publisher;

        public IssuerService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void issue(String id, String state) {
            publisher.publishEvent(new TicketEvent(id, state));
        }
    }

    public static class ListenerProbe {
        private final AtomicInteger any = new AtomicInteger();
        private final AtomicInteger ready = new AtomicInteger();
        private final AtomicInteger afterCommit = new AtomicInteger();
        private final AtomicInteger afterRollback = new AtomicInteger();

        @EventListener
        public void anyTicket(TicketEvent event) {
            any.incrementAndGet();
        }

        @EventListener(condition = "#a0.state() == 'READY'")
        public void readyTicket(TicketEvent event) {
            ready.incrementAndGet();
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void committedTicket(TicketEvent event) {
            afterCommit.incrementAndGet();
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBackTicket(TicketEvent event) {
            afterRollback.incrementAndGet();
        }

        public int any() { return any.get(); }
        public int ready() { return ready.get(); }
        public int committed() { return afterCommit.get(); }
        public int rolledBack() { return afterRollback.get(); }

        public String report() {
            return "any=" + any() + ", ready=" + ready()
                    + ", commit=" + committed()
                    + ", rollback=" + rolledBack();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl(
                    "jdbc:h2:mem:listener_diag;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager) {
            return new TransactionTemplate(manager);
        }

        @Bean
        IssuerService issuerService(ApplicationEventPublisher publisher) {
            return new IssuerService(publisher);
        }

        @Bean
        ListenerProbe listenerProbe() {
            return new ListenerProbe();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            IssuerService issuer = context.getBean(IssuerService.class);
            ListenerProbe probe = context.getBean(ListenerProbe.class);
            TransactionTemplate tx =
                    context.getBean(TransactionTemplate.class);

            // 1. Không có transaction: listener thường vẫn nhận.
            issuer.issue("N-1", "READY");
            System.out.println("no tx: " + probe.report());

            // 2. Transaction commit: AFTER_COMMIT được gọi.
            tx.executeWithoutResult(status ->
                    issuer.issue("C-1", "READY"));
            System.out.println("commit: " + probe.report());

            // 3. Transaction rollback: AFTER_ROLLBACK được gọi.
            tx.executeWithoutResult(status -> {
                issuer.issue("R-1", "REJECTED");
                status.setRollbackOnly();
            });
            System.out.println("rollback: " + probe.report());
        }
    }
}
```

### 10.3. Lệnh chạy và stdout dự kiến

```bash
gradle -q run
```

Các dòng **do chính chương trình in bằng `System.out.println`**:

```text
no tx: any=1, ready=1, commit=0, rollback=0
commit: any=2, ready=2, commit=1, rollback=0
rollback: any=3, ready=2, commit=1, rollback=1
```

Đây là kết quả của code và cấu hình đã trình bày. Gradle/logging có thể in thêm những dòng khác tùy môi trường.

### 10.4. Giải thích từng trường hợp

**Trường hợp N-1 (ngoài transaction):**

- `IssuerService.issue(...)` gọi publisher thật của context và phát `TicketEvent`.
- `@EventListener` thường nhận event, counter `any` tăng từ 0 lên 1.
- `state="READY"` nên `condition` thỏa, counter `ready` tăng lên 1.
- `@TransactionalEventListener` mặc định `fallbackExecution=false`; không có transaction để đăng ký, nên `commit` và `rollback` vẫn bằng 0.
- Đây là **hành vi đúng**, không phải listener hỏng.

**Trường hợp C-1 (transaction commit):**

- `TransactionTemplate.executeWithoutResult(...)` mở transaction JDBC do `DataSourceTransactionManager` quản lý.
- Event được publish **trong callback khi transaction hoạt động**. Hai listener thường chạy ngay, đưa `any=2`, `ready=2`.
- Listener phase `AFTER_COMMIT` được đăng ký với transaction; chỉ sau khi callback hoàn tất và transaction commit nó mới chạy, đưa `commit=1`.
- Listener `AFTER_ROLLBACK` không chạy vì transaction đã commit.

**Trường hợp R-1 (transaction rollback):**

- Trong transaction mới, publisher phát `TicketEvent("R-1", "REJECTED")`.
- `any` tăng lên 3, nhưng SpEL condition không khớp nên `ready` giữ nguyên 2.
- `status.setRollbackOnly()` khiến transaction rollback dù không ném exception.
- Listener `AFTER_COMMIT` không chạy, còn `AFTER_ROLLBACK` chạy và tăng counter `rollback=1`.

Ví dụ **không** sử dụng `@Async`, nhằm giữ stdout xác định và cô lập vấn đề event type, condition, phase. Với listener async, cần test chờ hoàn tất thay vì assert counter ngay sau khi publish. Nếu kết quả khác kỳ vọng, kiểm tra cấu hình dependency, Spring bean registration và version trước khi suy luận về bug framework.

## 11. Test xác định event có được publish trong `ApplicationContext` hay không

Spring TestContext Framework hỗ trợ `@RecordApplicationEvents` và `ApplicationEvents` để phân biệt:

- event **đã phát** nhưng transactional listener không chạy;
- event **đã phát** nhưng bị `condition` lọc;
- event **chưa từng được publish**.

`@RecordApplicationEvents` phải đặt trên test class; `ApplicationEvents` có thể được inject vào test method khi dùng `@SpringJUnitConfig`.

### 11.1. `src/test/java/demo/EventDiagnosticsTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(ListenerNotCalledDemo.AppConfig.class)
@RecordApplicationEvents
class EventDiagnosticsTest {

    @Autowired
    ListenerNotCalledDemo.IssuerService issuer;

    @Autowired
    ListenerNotCalledDemo.ListenerProbe probe;

    @Autowired
    TransactionTemplate tx;

    @Test
    void publishedEventsAreNotTheSameAsPhaseCallbacks(
            ApplicationEvents events) {

        issuer.issue("N-1", "READY");
        assertEquals(1, probe.any());
        assertEquals(1, probe.ready());
        assertEquals(0, probe.committed());
        assertEquals(0, probe.rolledBack());

        tx.executeWithoutResult(status ->
                issuer.issue("C-1", "READY"));
        assertEquals(1, probe.committed());

        tx.executeWithoutResult(status -> {
            issuer.issue("R-1", "REJECTED");
            status.setRollbackOnly();
        });

        // Cả ba event đã publish; phase listener có count khác.
        assertEquals(3L,
                events.stream(ListenerNotCalledDemo.TicketEvent.class)
                        .count());

        assertEquals(3, probe.any());
        assertEquals(2, probe.ready());
        assertEquals(1, probe.committed());
        assertEquals(1, probe.rolledBack());
    }
}
```

Chạy:

```bash
gradle -q test
```

Test này có **một phương thức `@Test`** và mong đợi JUnit Platform kết thúc thành công. Kết quả terminal có thể thay đổi theo Gradle, vì vậy không xem một dòng stdout cố định là hợp đồng test.

**Vì sao test có giá trị chẩn đoán?**

`ApplicationEvents.stream(TicketEvent.class).count() == 3` chứng minh **ba event kiểu `TicketEvent` đã được Spring Test ghi nhận là đã publish**. Trong cùng test:

- Listener thường nhận cả ba.
- Listener có condition chỉ nhận hai event `READY`.
- Listener hậu commit chỉ nhận event trong transaction commit.
- Listener hậu rollback chỉ nhận event trong transaction rollback.

Vậy **"không được gọi" phải luôn gắn với loại listener và điều kiện cụ thể**. Một event có thể đã được công bố thành công nhưng bị bỏ qua bởi chính quy tắc listener.

**Phạm vi test:** `ApplicationEvents` là recorder của Spring Test, không phải event store production. Đừng lưu đối tượng này sang thread lạ hoặc dùng qua nhiều test methods; Spring quản lý nó theo lifecycle test. Nếu test dùng custom `@TestExecutionListeners` thay thế defaults, cần bảo đảm `ApplicationEventsTestExecutionListener` được giữ/đăng ký.

## 12. Spring Boot: event quá sớm xảy ra trước khi bean listener tồn tại

Một trường hợp khác là dùng bean listener để nghe `ApplicationStartingEvent` hoặc `ApplicationEnvironmentPreparedEvent` **của Spring Boot**.

Những event này xảy ra **trước khi `ApplicationContext` có thể tạo bean `@Component`**, vì vậy:

```java
@Component
public class TooLateStartingListener {

    @EventListener
    public void handle(ApplicationStartingEvent event) {
        // Không thể nhận event đã phát trước khi bean được tạo.
    }
}
```

Đây là **phản ví dụ**. `ApplicationStartingEvent` thuộc package `org.springframework.boot.context.event`, không phải `ContextStartedEvent` của Spring Framework.

Nếu cần listener cho early Spring Boot events, đăng ký trước `SpringApplication.run(...)`:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.addListeners(new MyStartingListener());
app.run(args);
```

Đây là mã minh họa; `MyApplication` và `MyStartingListener` do ứng dụng định nghĩa. Listener cũng có thể được đăng ký trong `META-INF/spring.factories` bằng key `org.springframework.context.ApplicationListener` khi triển khai library/bootstrapping. Cần phân biệt cơ chế này với auto-configuration của Spring Boot 3 dùng `AutoConfiguration.imports`.

**Một cặp tên dễ nhầm:**

- `ApplicationStartedEvent` (**Spring Boot**) phát sau khi context refresh, trước runners.
- `ContextStartedEvent` (**Spring Framework**) phát khi gọi `ConfigurableApplicationContext.start()` rõ ràng; khởi động ứng dụng Boot thông thường không có nghĩa nó tự xảy ra.

Nếu listener nghe `ContextStartedEvent` nhưng ứng dụng chỉ `refresh()` và không gọi `start()`, việc handler không chạy cũng là hành vi đúng.

## 13. Kiểm tra log, metrics và breakpoints đúng cách

### 13.1. Ghi log tại publisher bằng dữ liệu tối thiểu

```java
log.debug("publish {} id={}",
        event.getClass().getName(), event.orderId());
publisher.publishEvent(event);
```

Đây là **mã minh họa**, giả định event có `orderId()` và logging dependency. Log class đầy đủ giúp phát hiện nhầm package/type. Không log toàn bộ entity, request, token hoặc payload nhạy cảm.

Gợi ý thêm `eventId`/correlation ID vào event DTO, nhất là khi xử lý async. Điều này cho phép nối log publisher với listener mà không dựa vào `ThreadLocal` MDC tự propagate.

### 13.2. Đặt breakpoint ở đúng nơi

Trong một test/ứng dụng local:

1. Breakpoint trước lời gọi `publishEvent`.
2. Breakpoint trong handler `@EventListener` tối giản không condition.
3. Nếu bước 1 chạy nhưng bước 2 không, kiểm tra registration/type/context.
4. Nếu handler thường chạy nhưng transactional handler không, kiểm tra transaction synchronization và phase.
5. Nếu listener `@Async`, dùng debugger quan sát **worker thread** và xác minh executor đã nhận task.

Không cần bước đầu tiên là debug vào nội bộ `SimpleApplicationEventMulticaster` ở mọi tình huống; các test nhỏ thường cô lập lỗi nhanh hơn. Nếu vẫn chưa rõ, đặt breakpoint ở multicaster `multicastEvent(...)` và listener adapter hoặc bật logging Spring có chọn lọc.

Với Spring Boot, có thể cấu hình logging theo nhu cầu chẩn đoán:

```properties
logging.level.org.springframework.context.event=DEBUG
logging.level.org.springframework.transaction=DEBUG
```

Đây là **cấu hình minh họa**, không bảo đảm framework sẽ log mọi event và mọi listener invocation. Debug logger là dữ liệu hỗ trợ; **không thay cho test quan sát event/counter trực tiếp**. Tránh bật debug toàn bộ hệ thống lâu dài khi lưu lượng lớn.

### 13.3. Kiểm tra multicaster tùy biến

Một bean tên chuẩn `applicationEventMulticaster` có thể thay thế multicaster mặc định:

```java
@Bean
ApplicationEventMulticaster applicationEventMulticaster(
        TaskExecutor executor) {

    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(executor);
    return m;
}
```

Đây là **đoạn minh họa**, cần import `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `TaskExecutor`. Với executor tùy biến, một số listener có thể chạy async và thứ tự/exception reporting thay đổi. Tùy phiên bản/loại listener, không phải mọi listener đều cho phép async execution bằng multicaster; riêng transaction-bound listeners cần được gọi đúng context transaction để đăng ký callback.

Khi nghi lỗi, so sánh với context tối giản sử dụng multicaster mặc định và listener không condition như ví dụ chính. Đừng đổi mọi listener sang async chỉ để "khắc phục" hiện tượng không thấy log.

## 14. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng chính | Cách chứng minh và sửa |
| --- | --- | --- |
| Không thấy `publishEvent` | Nhánh service chưa tới điểm phát; exception trước lời gọi | Breakpoint/test business branch và event contract |
| `@Component` listener không nhận event | Bean không nằm trong component scan hoặc không thuộc context | Kiểm tra bean registration, `@ComponentScan`/`@Import`/`@Bean` |
| Bean tồn tại nhưng `@EventListener` không nhận | Bean `@Lazy`, annotation infrastructure hoặc method signature không hợp lệ | Thử eager bean tối giản, xem startup logs |
| `ApplicationListener<T>` không chạy | Sai generic event type hoặc listener không được đăng ký | Đối chiếu runtime type/bean registrations |
| Listener nhận `OrderPaid` nhưng publisher phát `OrderCreated` | Khác event class | Kiểm tra FQCN và kiểu tham số |
| Handler generic chỉ nhận vài subtype | Type erasure / generic không resolve | Subtype concrete hoặc `ResolvableTypeProvider` |
| Listener có `condition` không chạy | Expression false hoặc sai argument | Test bỏ condition, thử `#a0` và dữ liệu đúng |
| Phát từ context A, listener ở B | Context độc lập hoặc hướng parent/child không phù hợp | So sánh context ID, cấu hình hierarchy |
| `AFTER_COMMIT` không chạy ngoài transaction | Mặc định `fallbackExecution=false` | Publish trong transaction đúng hoặc cân nhắc fallback theo nghiệp vụ |
| `AFTER_COMMIT` không chạy khi rollback | Commit không thành công | Đây là ngữ nghĩa đúng; dùng `AFTER_ROLLBACK` nếu cần |
| `AFTER_ROLLBACK` không chạy khi commit | Không có rollback | Đây là ngữ nghĩa đúng, không phải lỗi đăng ký |
| `@Transactional` trên method nhưng event không được gắn transaction | Self-invocation hoặc transaction proxy không hoạt động | Gọi qua Spring bean proxy hoặc `TransactionTemplate` |
| Listener async không thấy kết quả ngay | Task chưa hoàn tất hoặc queue đang bận | Chờ latch/future có timeout và kiểm tra executor |
| `@Async` listener lỗi không truyền về request thread | Worker exception xử lý riêng | `AsyncUncaughtExceptionHandler` và metrics |
| `@RequestScope`/MDC thiếu ở worker | ThreadLocal không auto-propagate | Đưa dữ liệu cần thiết vào immutable event, cấu hình context propagation khi thích hợp |
| Spring Boot early startup event không tới `@Component` | Listener được đăng ký quá muộn | `SpringApplication.addListeners` hoặc `spring.factories` |
| Nghe `ContextStartedEvent` nhưng chỉ refresh context | Không gọi `ConfigurableApplicationContext.start()` | Nghe `ContextRefreshedEvent` hoặc gọi start khi cần lifecycle |
| Test `@Transactional` không nhận `AFTER_COMMIT` | Test rollback mặc định hoặc assertion trước commit | `TestTransaction.flagForCommit(); end()` hoặc test không bọc transaction |
| Event đã publish nhưng side effect chưa có | Listener async, bị lỗi hoặc commit-phase chưa tới | Test riêng consumer/completion, không suy luận từ publisher |
| Không có event sau JVM restart | Spring Application Event không tự lưu bền vững | Transactional outbox, broker hoặc persisted queue |

## 15. Những bẫy trong test khiến bạn tưởng listener bị mất

### 15.1. Test chưa tạo đủ Spring context

Nếu unit test chỉ `new OrderService(mockPublisher)`, bạn đang kiểm tra business code gọi publisher, **không có hạ tầng listener Spring**. Muốn xác minh listener được gọi thật, dùng Spring Test `@SpringJUnitConfig` hoặc khởi tạo `AnnotationConfigApplicationContext` hợp lệ.

### 15.2. Test transaction rollback mặc định

Spring Test method gắn `@Transactional` thường được rollback khi test kết thúc. Nếu test publish event rồi assert `AFTER_COMMIT` **trước khi kết thúc transaction**, callback chưa chạy. Nếu test kết thúc bằng rollback, callback `AFTER_COMMIT` sẽ không được gọi.

Đối với test có transaction do Spring Test quản lý:

```java
TestTransaction.flagForCommit();
TestTransaction.end();

// Lúc này mới kiểm tra listener AFTER_COMMIT.
```

Đây là **đoạn minh họa**, cần `spring-test` và transaction manager thích hợp. Nếu không cần transaction ở test method, để service transactional thật tự commit và assert sau lời gọi service là một cách đơn giản hơn.

### 15.3. Event bị lọc trong test nhưng không phải production

Một test dùng configuration chỉ import `OrderService` mà quên import listener; production lại có component scan khác. Hoặc `@MockBean`/mocking khác làm thay bean listener. Luôn xác minh **context thực tế của test** và event type, thay vì suy luận từ production application class.

### 15.4. Recorder nhìn thấy publish, không bảo đảm listener thành công

`@RecordApplicationEvents` ghi nhận event được công bố. Nó không làm mọi listener async chạy xong và không thay transaction phase. Test nên dùng một observer/counter/latch do mình quản lý để chứng minh callback cụ thể đã xảy ra.

Nếu event có thể đến từ thread khác hoặc context phụ, đừng mặc định recorder quan sát mọi đường đi ngoài TestContext thread. Thiết kế test phù hợp ranh giới context và thread.

## 16. Cách sửa sau khi tìm đúng nguyên nhân

Đừng bật `fallbackExecution=true` hay bỏ `@Async` chỉ để "làm test xanh" nếu thay đổi đó làm sai ngữ nghĩa nghiệp vụ.

Một số quyết định đúng:

- **Bean đăng ký thiếu:** sửa component scan, `@Bean`, `@Import` và bỏ lazy initialization không phù hợp.
- **Type mismatch:** sửa hợp đồng event type và payload, không chỉ ép cast.
- **SpEL filter sai:** sửa expression và thêm negative-path tests.
- **Context sai:** inject đúng `ApplicationEventPublisher` từ context sở hữu flow hoặc thiết kế bridge giữa contexts có chủ đích.
- **Transaction thiếu:** dịch `publishEvent` vào transactional service hoặc dùng `TransactionTemplate`; không dùng fallback như phép giả lập commit.
- **Transaction rollback:** nếu nghiệp vụ chỉ làm khi commit, không nhận event là đúng; nếu cần xử lý thất bại, dùng pha rollback.
- **Async/exception:** thêm executor diagnostics, retry/error handling, latch trong test và correlation ID trong event.
- **Startup events:** đăng ký early listener trước khi context tạo bean.
- **Độ bền qua crash:** dùng outbox/persistent queue thay cho kỳ vọng Spring tự replay.

## 17. Checklist cuối cùng

Trước khi kết luận Spring "không gọi listener", xác nhận:

- [ ] Event được tạo và `publishEvent` thực sự được gọi?
- [ ] Event class runtime và payload khớp handler?
- [ ] Listener thuộc Spring-managed bean và context thích hợp?
- [ ] Bean có vô tình `@Lazy` hoặc nằm ngoài component scan?
- [ ] Hạ tầng `@EventListener` annotation đã được đăng ký?
- [ ] `condition` SpEL thực sự trả `true`?
- [ ] Có parent/child context hoặc một context phụ ngoài ý muốn?
- [ ] Nếu là `@TransactionalEventListener`, transaction hoạt động lúc publish?
- [ ] Phase listener khớp commit/rollback và callback đã tới chưa?
- [ ] Nếu là async, test đã chờ worker và xem error logs đúng thread?
- [ ] Có Spring Boot early event được phát trước lúc bean tạo không?
- [ ] Test đã phân biệt **event được phát** với **listener đã xử lý** chưa?

**Kết luận:** Hiện tượng "listener không được gọi" phải được phân tách thành **không publish**, **không đăng ký**, **không match**, hoặc **chưa/không đủ điều kiện xử lý**. Một test `@RecordApplicationEvents` kết hợp listener thường tối giản, kiểm tra `condition` và transaction phase như ví dụ trên sẽ nhanh chóng tìm đúng ranh giới lỗi. Khi đã xác định nguyên nhân, sửa đúng phần đăng ký/type/context/transaction/async thay vì thay đổi toàn bộ event architecture.

## Tài liệu chính thức

- [Spring Framework 6.2 — ApplicationContext Events: listener registration, `@Lazy`, SpEL, generic và async](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events, `fallbackExecution`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Testing Application Events và `@RecordApplicationEvents`](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — `@EventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — `@TransactionalEventListener` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework 6.2 — `ApplicationEventPublisher` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
