# ErrorHandler của ApplicationEventMulticaster trong Spring Framework

## 1. Bài toán: một listener lỗi thì những listener còn lại ra sao?

`ApplicationEventPublisher.publishEvent(...)` cho phép một thành phần trong ứng dụng Spring công bố sự kiện để nhiều listener độc lập cùng phản ứng. Trong cấu hình mặc định, Spring sử dụng `SimpleApplicationEventMulticaster` để phân phối sự kiện **đồng bộ trên thread của publisher**. Một vấn đề quan trọng xuất hiện khi một listener ném exception:

- Exception có được chuyển về nơi gọi `publishEvent(...)` không?
- Các listener còn lại của **cùng một event** có được gọi tiếp không?
- Transaction hiện tại commit hay rollback?
- Có thể log lỗi mà không làm hỏng luồng nghiệp vụ chính không?
- Cách xử lý có thay đổi khi dùng `@Async` hoặc executor cho multicaster không?

`SimpleApplicationEventMulticaster.setErrorHandler(...)` là điểm cấu hình cho chính sách **xử lý lỗi phát sinh trong lúc multicaster gọi listener**. Interface `org.springframework.util.ErrorHandler` chỉ có một phương thức:

~~~java
void handleError(Throwable t);
~~~

Khi listener ném lỗi, multicaster có thể bàn giao lỗi đó cho `ErrorHandler` đã cài. **Nếu handler trở về bình thường, lỗi được xem là đã xử lý ở tầng multicast và những listener khác có cơ hội tiếp tục chạy. Nếu handler ném lại exception, ngoại lệ tiếp tục lan ra ngoài đường gọi thích hợp.**

**Tác động lên transaction không được quyết định chỉ bằng việc có `ErrorHandler`.** Nó phụ thuộc vào transaction manager, pha xử lý, kiểu exception, ranh giới `@Transactional` và việc lỗi cuối cùng có thoát khỏi phương thức giao dịch hay không. Đặc biệt, một handler ghi log rồi bỏ qua lỗi có thể khiến giao dịch chính **vẫn commit dù một listener đã thất bại**.

## 2. ApplicationEventMulticaster nằm ở đâu trong luồng xử lý?

Các thành phần liên quan:

| Thành phần | Chức năng |
| --- | --- |
| `ApplicationEventPublisher` | API phát sự kiện từ application code; `publishEvent` trả `void`. |
| `ApplicationEventMulticaster` | Hạ tầng phân phối event tới các `ApplicationListener` tương ứng. |
| `SimpleApplicationEventMulticaster` | Cách triển khai mặc định, hỗ trợ executor tùy biến và `ErrorHandler`. |
| `ApplicationListener<E>` | Listener kiểu giao diện, nhận sự kiện qua `onApplicationEvent(E)`. |
| `@EventListener` | Annotation đánh dấu phương thức listener; Spring đăng ký adapter để phương thức đó tham gia multicaster. |
| `ErrorHandler` | Callback `handleError(Throwable)` cho lỗi xảy ra trong quá trình listener được multicaster gọi. |
| `TaskExecutor` | Có thể chạy một số listener bất đồng bộ nếu được cấu hình cho multicaster. |

Sơ đồ mặc định, **không có ErrorHandler và không có async**:

~~~text
OrderService
    |
    | publisher.publishEvent(OrderSubmitted)
    v
SimpleApplicationEventMulticaster
    |
    +--> listener A: thành công
    |
    +--> listener B: throw IllegalStateException
    |           |
    |           +-- exception thoát khỏi listener
    |
    X--> listener C: không được gọi trong lượt multicast này
    |
    v
publishEvent(...) ném exception về caller
~~~

Javadoc của `SimpleApplicationEventMulticaster.setErrorHandler(...)` nêu rõ **mặc định không có ErrorHandler**: lỗi từ một listener sẽ dừng lượt multicast hiện tại và được chuyển về publisher. Đây là mặc định cho đường gọi listener đồng bộ. Nếu dùng executor riêng, exception có thể xảy ra trong thread của executor nên không thể mặc định trông chờ publisher nhận được nó.

Khi cài handler **log và suppress**:

~~~text
OrderService
    |
    | publisher.publishEvent(OrderSubmitted)
    v
SimpleApplicationEventMulticaster
    |
    +--> listener A: thành công
    |
    +--> listener B: throw IllegalStateException
    |           |
    |           v
    |       ErrorHandler.handleError(error)
    |           |
    |           +-- ghi log/metric và KHÔNG ném lại
    |
    +--> listener C: vẫn được gọi
    |
    v
publishEvent(...) có thể trả về bình thường
~~~

**Đây không phải cơ chế retry.** Handler được gọi khi có lỗi; Spring không tự gọi lại listener lỗi, không phục hồi side effect đã chạy một phần và không tự đưa thông điệp sang dead-letter queue.

## 3. Chính sách lỗi phổ biến: propagate và suppress

Từ góc nhìn nghiệp vụ, có hai nhóm hành vi chính:

### 3.1. Propagate: giữ lỗi trong luồng gọi

Khi không có handler, hoặc handler ném lại lỗi:

- Listener ném exception → việc phân phối sự kiện đồng bộ bị ngắt ở lỗi đó.
- Lời gọi `publishEvent(...)` có thể ném exception ra caller.
- Nếu lỗi này thoát khỏi một phương thức `@Transactional` và khớp quy tắc rollback của Spring, transaction có thể bị rollback.
- Listener được gọi **trước** listener lỗi có thể đã tạo side effect; đừng mặc định cho rằng mọi thứ đều rollback được.

Một handler minh họa:

~~~java
multicaster.setErrorHandler(error -> {
    System.err.println("Listener failed: " + error.getMessage());
    if (error instanceof RuntimeException re) {
        throw re;
    }
    throw new IllegalStateException("Listener error", error);
});
~~~

*Đây là đoạn cấu hình minh họa, không phải một chương trình hoàn chỉnh. Chỉ dùng khi bạn thực sự muốn báo thất bại qua luồng gọi. Lỗi ở listener hoặc chính handler có thể ngăn các listener phía sau.*

### 3.2. Suppress: ghi nhận lỗi nhưng tiếp tục

Khi handler không ném lại:

- Multicaster tiếp tục xử lý những listener khác trong lượt phát event đó, theo cơ chế dispatch hiện hành.
- Publisher **không nhận biết lỗi đó bằng exception**.
- Transaction bao quanh có thể tiếp tục và commit, vì lỗi listener không còn thoát ra làm phương thức giao dịch thất bại.
- Người thiết kế phải có cách ghi log, metric, alert hoặc xử lý bù; nếu không, lỗi nghiệp vụ có thể bị che giấu.

~~~java
multicaster.setErrorHandler(error -> {
    // Minh họa: ghi nhận lỗi rồi trở về bình thường.
    System.err.println("Listener error: " + error.getMessage());
});
~~~

Không nên xem `suppress` là “an toàn hơn” trong mọi trường hợp. Ví dụ listener chỉ gửi một metric phụ thì log và tiếp tục có thể hợp lý; nhưng listener giữ một invariant bắt buộc của đơn hàng mà bị suppress thì việc commit dữ liệu chính có thể khiến hệ thống không nhất quán.

### 3.3. Hai handler mẫu của Spring

Spring cung cấp các strategy mẫu trong `org.springframework.scheduling.support.TaskUtils`:

- `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER`: ghi log lỗi rồi xử lý mà không chuyển tiếp exception.
- `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`: ghi log lỗi và chuyển tiếp exception.

Hai đối tượng này giúp phân biệt rõ **logging** với **propagation**. Log lỗi không đồng nghĩa rollback; việc báo lỗi cho caller hay executor mới ảnh hưởng tới luồng thực thi và có thể ảnh hưởng quy tắc rollback.

## 4. Cấu hình multicaster dùng bean name chuẩn

Một `ApplicationContext` mặc định có một multicaster. Khi cần thay đổi chiến lược, có thể cung cấp bean tên chính xác **`applicationEventMulticaster`**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

@Configuration
public class EventMulticasterConfig {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error -> {
            // Ví dụ minh họa: ghi nhận và suppress.
            System.err.println("Event listener failed: " + error);
        });

        return multicaster;
    }
}
~~~

*Đây là lớp cấu hình có thể tích hợp vào một ứng dụng Spring đang hoạt động. Ví dụ đầy đủ, có thể chạy với Java 17+ ở phần 5.*

**Quan trọng về tên bean:** Spring tìm multicaster với tên `applicationEventMulticaster` để sử dụng ở cấp `ApplicationContext`. Nếu đặt tên `myMulticaster` mà không cấu hình thêm cơ chế tích hợp, không thể chỉ dựa vào việc bean có đúng kiểu để kết luận nó sẽ thay thế multicaster mặc định.

Một số điểm cần cân nhắc:

- `setErrorHandler(...)` là cách cấu hình trên **`SimpleApplicationEventMulticaster`**, không phải phương thức của giao diện `ApplicationEventMulticaster`.
- Lớp `ErrorHandler` chỉ nhận `Throwable`, **không nhận trực tiếp event và tên listener**. Nếu muốn log `eventId`, correlation ID hoặc tên handler chính xác, cần cơ chế logging/tracing bổ sung tại listener hoặc lớp bọc phù hợp.
- Policy trên multicaster là policy ở phạm vi context, có thể ảnh hưởng **nhiều loại sự kiện khác nhau**, gồm event do framework phát; không phải chỉ một business listener.
- Không cần cấu hình `TaskExecutor` để dùng `ErrorHandler`. Mặc định executor đồng bộ là lựa chọn giúp người học thấy rõ đường đi exception.

## 5. Ví dụ hoàn chỉnh chạy được: mặc định và có ErrorHandler

Ví dụ này dùng **Java 17+, Maven và Spring Framework 6.2.9**. Ta tạo hai `AnnotationConfigApplicationContext` tách biệt:

1. Context thứ nhất không khai báo `ErrorHandler`. Listener thứ hai ném lỗi; listener thứ ba không chạy; publisher bắt được exception.
2. Context thứ hai khai báo multicaster với handler ghi nhận rồi suppress. Listener thứ hai vẫn ném lỗi, nhưng handler xử lý và listener thứ ba được gọi.

Không cần Spring Boot, web server, database hoặc cấu hình executor nên kết quả do code in ra ổn định.

### 5.1. Cấu trúc thư mục

~~~text
multicaster-error-handler-demo/
├── pom.xml
└── src/main/java/EventErrorHandlerDemo.java
~~~

### 5.2. Tệp pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>multicaster-error-handler-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
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

### 5.3. Tệp src/main/java/EventErrorHandlerDemo.java

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;

public class EventErrorHandlerDemo {

    public record OrderSubmitted(String id) {}

    public static class Listeners {

        @EventListener
        @Order(10)
        public void first(OrderSubmitted event) {
            System.out.println("listener-1: " + event.id());
        }

        @EventListener
        @Order(20)
        public void fails(OrderSubmitted event) {
            System.out.println("listener-2: throws");
            throw new IllegalStateException("simulated failure");
        }

        @EventListener
        @Order(30)
        public void last(OrderSubmitted event) {
            System.out.println("listener-3: " + event.id());
        }
    }

    // Trường hợp A: dùng multicaster mặc định, không có ErrorHandler.
    @Configuration(proxyBeanMethods = false)
    public static class DefaultConfig {

        @Bean
        public Listeners listeners() {
            return new Listeners();
        }
    }

    // Trường hợp B: thay multicaster bằng bean cùng tên chuẩn.
    @Configuration(proxyBeanMethods = false)
    public static class SuppressConfig {

        @Bean
        public Listeners listeners() {
            return new Listeners();
        }

        @Bean(name = "applicationEventMulticaster")
        public ApplicationEventMulticaster applicationEventMulticaster() {
            SimpleApplicationEventMulticaster multicaster =
                    new SimpleApplicationEventMulticaster();

            multicaster.setErrorHandler(error ->
                System.out.println("ErrorHandler: " + error.getMessage())
            );

            return multicaster;
        }
    }

    public static void main(String[] args) {
        System.out.println("=== DEFAULT ===");
        try (var context =
                new AnnotationConfigApplicationContext(DefaultConfig.class)) {
            try {
                context.publishEvent(new OrderSubmitted("ORD-7"));
                System.out.println("publisher: returned");
            } catch (IllegalStateException ex) {
                System.out.println("publisher: caught " + ex.getMessage());
            }
        }

        System.out.println("=== SUPPRESS ===");
        try (var context =
                new AnnotationConfigApplicationContext(SuppressConfig.class)) {
            context.publishEvent(new OrderSubmitted("ORD-8"));
            System.out.println("publisher: returned");
        }
    }
}
~~~

### 5.4. Biên dịch và chạy

Tại thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventErrorHandlerDemo
~~~

Stdout do chương trình in ra; không tính thông báo của Maven:

~~~text
=== DEFAULT ===
listener-1: ORD-7
listener-2: throws
publisher: caught simulated failure
=== SUPPRESS ===
listener-1: ORD-8
listener-2: throws
ErrorHandler: simulated failure
listener-3: ORD-8
publisher: returned
~~~

### 5.5. Giải thích từng bước

**Trường hợp DEFAULT:**

1. `context.publishEvent(new OrderSubmitted("ORD-7"))` bàn giao payload cho multicaster.
2. Spring gọi các method có `@EventListener`, theo mức `@Order` đã khai báo. `first` in tên đơn trước.
3. `fails` in thông báo rồi ném `IllegalStateException`.
4. Không có ErrorHandler, exception thoát khỏi lượt multicast tới `publishEvent(...)`, được `catch` trong `main` bắt.
5. `last` chưa được gọi, do lượt multicast bị ngắt. Không có dòng `listener-3` hoặc `publisher: returned` trong phần DEFAULT.

**Trường hợp SUPPRESS:**

1. Context có bean tên `applicationEventMulticaster` nên dùng multicaster đã cấu hình.
2. Hai listener đầu vẫn chạy; `fails` vẫn ném `IllegalStateException`.
3. `ErrorHandler.handleError(Throwable)` được gọi, in `ErrorHandler: simulated failure` rồi **trở về bình thường**.
4. Multicaster tiếp tục gọi `last`, in `listener-3: ORD-8`.
5. Vì không còn exception lan ra `publishEvent(...)`, `main` in `publisher: returned`.

Ví dụ không có transaction, nên **không tồn tại commit/rollback trong hai trường hợp trên**. Phần 6 sẽ giải thích điều gì thay đổi nếu lời gọi publish nằm trong một phương thức transactional.

### 5.6. Về @Order

Dùng `@Order(10)`, `@Order(20)`, `@Order(30)` giúp minh họa thứ tự các listener của cùng loại sự kiện khi xử lý đồng bộ. Không nên suy rộng rằng `@Order` bảo đảm một workflow xuyên nhiều thread, broker hoặc listener async luôn hoàn tất theo thứ tự.

## 6. Quan hệ giữa ErrorHandler và transaction rollback

Đây là điểm dễ nhầm nhất của chủ đề “Lỗi và rollback”.

### 6.1. Publish event trong một transaction imperative

Giả sử Spring đang quản lý một transaction JDBC/JPA với `PlatformTransactionManager`:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher events;

    public CheckoutService(OrderRepository repository,
                           ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void checkout(Order order) {
        repository.save(order);              // Chưa chắc đã commit.
        events.publishEvent(new OrderPlaced(order.getId()));
    }
}
~~~

*Đây là đoạn mã tích hợp minh họa. `OrderRepository`, `Order` và `OrderPlaced` do ứng dụng tự định nghĩa; cần các import `@Service`, `@Transactional`, `ApplicationEventPublisher`. Đoạn này không chạy độc lập như ví dụ phần 5.*

Nếu `OrderPlaced` được xử lý bằng listener đồng bộ và một listener ném `IllegalStateException`:

| Tình huống | Kết quả đối với publisher | Hệ quả transaction có thể xảy ra |
| --- | --- | --- |
| Không có `ErrorHandler`; runtime exception thoát khỏi phương thức `@Transactional` | Publisher thấy exception. | Với quy tắc mặc định rollback khi gặp `RuntimeException`/`Error`, Spring thường rollback transaction. |
| Handler **propagate** lỗi tiếp | Publisher thấy exception. | Thường tương tự hàng trên, nếu lỗi thoát khỏi transaction boundary. |
| Handler **suppress** lỗi | Publisher có thể trả về bình thường. | Phương thức giao dịch có thể hoàn tất và **commit** dù listener lỗi. |
| Code gọi publisher **catch exception** và tiếp tục | Exception không nhất thiết thoát khỏi service. | Không được kết luận chắc chắn rollback: còn phụ thuộc transaction đã bị đánh dấu rollback-only hay chưa và quy tắc nghiệp vụ. |
| Listener chạy trong thread khác | Publisher có thể không thấy exception trực tiếp. | Transaction thread gốc không tự rollback chỉ vì task bên ngoài ném lỗi. |

**Chú ý:** một số thao tác tài nguyên bên trong listener có thể đã đánh dấu transaction `rollback-only`, kể cả khi outer layer catch/suppress exception. Khi đó commit có thể thất bại hoặc ném `UnexpectedRollbackException`. Vì vậy “suppress → chắc chắn commit” là sai; kết luận chính xác chỉ là **suppress không còn tự đẩy exception của listener ra caller**.

### 6.2. Side effect đã xảy ra trước lỗi có tự rollback không?

Không thể kết luận chung:

- Ghi dữ liệu qua cùng transaction JDBC/JPA có thể rollback cùng transaction nếu ranh giới và resource participation đúng.
- Gửi email, HTTP request, file write hoặc publish sang broker ngoài transaction DB **không tự đảo ngược** khi DB rollback.
- Listener đã hoàn tất trước khi listener sau ném lỗi có thể đã tạo side effect ở hệ thống ngoài.
- Bắt exception rồi suppress không tự “khôi phục” listener lỗi hoặc hoàn tác các thao tác đã chạy một phần.

Nếu cần tính nguyên tử cho nhiều thay đổi dữ liệu, hãy gom logic quan trọng vào transaction của application service với lỗi được xử lý theo ý đồ. Nếu cần gửi message bền vững khi commit thành công, cân nhắc **transactional outbox** thay vì đặt toàn bộ trách nhiệm vào event listener nội bộ.

### 6.3. ErrorHandler không phải transaction manager

`ErrorHandler` quyết định **để lỗi tiếp tục lan đi hay không** trong đường gọi listener. Nó không có API `commit`, `rollback` hoặc `setRollbackOnly`; nó không biết tự động trạng thái database. Việc transaction commit/rollback do `PlatformTransactionManager`/`ReactiveTransactionManager` phối hợp với interceptor, resource và quy tắc rollback.

**Mẫu nguy hiểm:** dùng `ErrorHandler` toàn cục để nuốt lỗi của listener có nhiệm vụ thực thi invariant bắt buộc (chẳng hạn kiểm tra số dư hoặc bảo đảm không xuất hàng âm). Nếu bắt buộc thất bại phải rollback, việc suppress có thể làm sai semantics. Hãy chuyển kiểm tra invariant vào application service/transaction rõ ràng, không thiết kế nó như một “listener tùy chọn”.

## 7. AFTER_COMMIT, @TransactionalEventListener và thời điểm lỗi

Spring có `@TransactionalEventListener` để xử lý event theo pha transaction:

- `BEFORE_COMMIT`: trước commit.
- `AFTER_COMMIT`: sau khi commit thành công.
- `AFTER_ROLLBACK`: sau rollback.
- `AFTER_COMPLETION`: sau commit hoặc rollback.

Ví dụ:

~~~java
@Component
class AuditListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlaced event) {
        // Callback được thực thi sau khi transaction đã commit.
        sendAuditMessage(event);
    }
}
~~~

*Đoạn minh họa cần import `@Component`, `@TransactionalEventListener` và `TransactionPhase`. `sendAuditMessage` là phương thức nghiệp vụ giả định.*

Ở đây phải tách **hai thời điểm**:

1. Khi `publishEvent(...)` chạy trong transaction, Spring có thể chỉ **đăng ký transaction synchronization** cho listener.
2. Sau khi transaction commit, callback `AFTER_COMMIT` mới thực hiện code xử lý event.

Do đó **không được mặc định rằng `SimpleApplicationEventMulticaster.ErrorHandler` bắt được tất cả exception phát sinh trong callback AFTER_COMMIT**: code xử lý thực tế chạy tại một phase do transaction synchronization quản lý, không nhất thiết bên trong lời gọi listener của multicaster ở thời điểm publish. Error policy cho callback transaction-bound cần được thiết kế và kiểm thử riêng.

Quan trọng hơn: **đã commit thì không thể rollback transaction gốc** chỉ vì `AFTER_COMMIT` listener thất bại. Một exception sau commit có thể được ghi nhận hoặc ảnh hưởng luồng caller ở thời điểm completion tùy cơ chế, nhưng không làm commit trước đó “chưa xảy ra”.

Nếu cần cập nhật DB trong callback sau commit, cần một transaction mới thích hợp; nếu cần bảo đảm delivery bền vững, dùng outbox/broker kèm retry và idempotency. Không dùng `ErrorHandler` như cơ chế đảm bảo gửi event sau commit.

## 8. Điều gì đổi khi multicaster có TaskExecutor?

`SimpleApplicationEventMulticaster` có thêm API:

~~~java
multicaster.setTaskExecutor(taskExecutor);
~~~

*Đây là đoạn cấu hình minh họa; `taskExecutor` là một `Executor`/`TaskExecutor` được ứng dụng cấu hình và quản lý.*

Nếu đặt executor bất đồng bộ:

- Những listener **có hỗ trợ async execution** có thể được gửi tới thread của executor thay vì chạy trên thread publisher.
- Exception của listener xuất hiện trong task của executor; nó **không nhất thiết** được chuyển về thread gọi `publishEvent(...)`.
- `ErrorHandler` của multicaster vẫn có thể xử lý exception xảy ra trong đường gọi listener do multicaster thực hiện, nhưng kết quả handler được quan sát trong executor task. Việc rethrow sẽ đến cơ chế xử lý lỗi của executor/task chứ không tự trở về caller.
- Một listener lỗi không nhất thiết ngăn các listener đã được submit/chạy trên task khác.
- Thread-local transaction và logging context **không tự được chuyển nguyên vẹn** sang executor khác. Cần chủ động thiết kế context propagation, tránh giả định cùng transaction.
- **Không phải tất cả listener đều có thể chuyển sang async.** Một số `ApplicationListener` khai báo `supportsAsyncExecution() = false`, ví dụ transaction-synchronized listener, vẫn phải chạy trên thread gốc để bảo toàn ràng buộc phù hợp.

Bảng so sánh:

| Khía cạnh | Multicaster đồng bộ mặc định | Multicaster có async executor |
| --- | --- | --- |
| Nơi chạy | Thread của publisher. | Có thể là executor thread cho listener hỗ trợ. |
| ErrorHandler suppress | Thường tiếp tục gọi listener kế tiếp. | Lỗi được xử lý trong từng task; các task khác có thể đã chạy. |
| ErrorHandler rethrow | Có thể ném về publisher. | Có thể ném trong executor; publisher không nhất thiết thấy. |
| Thứ tự hoàn tất | Có thể dự đoán trong ví dụ đơn giản với `@Order`. | Không nên dựa vào thứ tự hoàn tất. |
| Transaction thread-local | Listener đồng bộ có thể thấy transaction hiện hành. | Listener trên thread khác không tự tham gia transaction đó. |
| Rollback do exception | Có thể xảy ra nếu exception thoát khỏi boundary. | Không tự rollback transaction thread gốc vì lỗi trong task async. |

Đừng dùng async chỉ để tránh exception lan ngược về publisher. Điều đó còn thay đổi thứ tự, transaction context, khả năng quan sát lỗi và vòng đời tác vụ.

## 9. Phân biệt multicaster ErrorHandler và @Async exception handling

Có hai cơ chế bất đồng bộ rất dễ bị nhầm:

### 9.1. Async do multicaster cấu hình

~~~java
SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(executor);
multicaster.setErrorHandler(error -> report(error));
~~~

*Đoạn code minh họa; `executor` và `report` là thành phần do ứng dụng định nghĩa.*

Trong trường hợp này, multicaster là bên **tổ chức việc gọi listener** trên executor và có thể bọc lời gọi bằng `ErrorHandler`. Nhưng caller vẫn không có cam kết nhận exception trong cùng thread.

### 9.2. Async ở chính phương thức @EventListener

~~~java
@Async
@EventListener
public void sendNotification(OrderPlaced event) {
    notificationGateway.send(event.orderId());
}
~~~

*Đoạn minh họa trong bean Spring; cần `@EnableAsync`, import `@Async`/`@EventListener` và khai báo `notificationGateway` theo ứng dụng.*

Ở đây multicaster gọi adapter của phương thức listener, còn `@Async` đưa phần xử lý thực tế sang executor qua cơ chế AOP. Exception xảy ra sau đó **không nhất thiết đi qua multicaster `ErrorHandler`**.

Với method `@Async void`, Spring có cơ chế `AsyncUncaughtExceptionHandler` để xử lý exception không được bắt. Nếu phương thức dùng kiểu trả về phù hợp như `CompletableFuture`, lỗi có thể được biểu diễn bằng future thất bại và được xử lý ở nơi quan sát future. Trường hợp `@EventListener @Async` cũng không hỗ trợ phát tiếp event chỉ bằng return value.

**Quy tắc:** khi tìm nguyên nhân “handler không bắt được lỗi”, trước tiên phải xác định exception xảy ra **trong lời gọi listener của multicaster**, **trong task executor của multicaster**, **trong invocation @Async được tách riêng**, hay **trong callback sau commit**. Chỉ nhìn tên annotation không đủ để khẳng định một ErrorHandler sẽ được gọi.

## 10. Chọn chính sách theo mức độ quan trọng của listener

Một chiến lược hợp lý không phải luôn “log and suppress” hay luôn “fail fast”; cần phân loại side effect:

| Loại công việc | Chính sách gợi ý |
| --- | --- |
| Kiểm tra invariant bắt buộc trước commit | Thường đặt trong application service/transaction, để exception được quản lý theo rollback policy; không dùng global suppress. |
| Cập nhật dữ liệu bắt buộc cùng transaction | Thực thi trong boundary rõ, propagate khi thất bại nếu nghiệp vụ yêu cầu. |
| Ghi metric hoặc telemetry tùy chọn | Có thể suppress có giám sát, vì lỗi metric không nhất thiết làm hỏng nghiệp vụ chính. |
| Gửi email, webhook, gọi hệ thống bên ngoài | Cân nhắc outbox/queue + retry/idempotency; đừng chỉ suppress và coi đã giao thành công. |
| Tạo projection có thể rebuild | Có thể xử lý độc lập/retry, nhưng phải có event nguồn bền vững và khả năng replay. |
| Listener sau commit | Định nghĩa chính sách lỗi cho callback/worker; không kỳ vọng rollback giao dịch đã commit. |

**Không nên đặt một ErrorHandler “nuốt mọi Throwable” trong production nếu có cả listener trọng yếu và listener phụ trợ.** `Throwable` bao gồm cả `Error` nghiêm trọng; chính sách suppress toàn cục cần cân nhắc kỹ. Thực tế thường xử lý lỗi có thể phục hồi ở ngay listener/adapter hoặc phân tách các loại listener theo kiến trúc, thay vì áp một policy mù cho mọi event của context.

Với nghiệp vụ có yêu cầu bảo đảm hoàn thành, ưu tiên **sự nhất quán rõ ràng và khả năng retry** hơn là một luồng publisher luôn trả về thành công.

## 11. Logging, metric và khả năng chẩn đoán lỗi

`ErrorHandler.handleError(Throwable)` không tự cung cấp `eventId`, event type, bean name hoặc tên phương thức listener. Việc log chuỗi exception đơn thuần thường thiếu ngữ cảnh. Nên bổ sung tại listener hoặc tầng instrumentation:

- `eventType`, `eventId`, `aggregateId`/`orderId` nếu có.
- Tên listener/handler và operation đang làm.
- Thời điểm xử lý, thời lượng, số lần thử.
- `traceId`/`correlationId`, nhưng cẩn thận thread propagation khi dùng async.
- Stack trace/loại exception và cách xử lý: suppressed, propagated, retried hay sent to DLQ.
- Metric về lỗi và alarm cho listener quan trọng; một suppress handler không được làm mất tín hiệu vận hành.

Ví dụ một listener tự bổ sung ngữ cảnh trước khi lỗi lan đi:

~~~java
@EventListener
public void reserveStock(OrderPlaced event) {
    try {
        stockService.reserve(event.orderId());
    } catch (RuntimeException ex) {
        logger.error("reserveStock failed for orderId={}",
                event.orderId(), ex);
        throw ex; // Nếu muốn giữ semantics propagate.
    }
}
~~~

*Đoạn code minh họa trong bean: `stockService`, `logger` và `OrderPlaced` là thành phần ứng dụng cần có; không phải chương trình độc lập.*

Nếu đặt log ở cả listener và ErrorHandler, tránh nhân đôi quá nhiều log cho cùng exception. Có thể dùng số đếm metric ở handler và log đầy đủ một lần ở nơi có đủ context.

## 12. Kiểm thử: không chỉ kiểm tra log, phải kiểm tra tác dụng phụ

Một bộ kiểm thử cho ErrorHandler nên xác minh **những điều quan sát được**, thay vì chỉ nhìn stdout:

1. **Không handler, đồng bộ:** listener B ném exception; publisher nhận lỗi; listener C chưa chạy.
2. **Handler suppress:** listener B ném lỗi nhưng handler được gọi một lần; listener C vẫn chạy; publisher không thấy lỗi B.
3. **Handler propagate:** listener B ném lỗi; handler ném lại; exception lan đến đường gọi phù hợp; listener C không chạy khi dùng sync.
4. **Có @Order:** khi cần kiểm thử listener nào là “sau”, đặt `@Order` rõ ràng trong kịch bản sync.
5. **Trong @Transactional:** kiểm tra dữ liệu sau commit/rollback bằng database thật hoặc transaction test, không suy từ việc exception có hay không mà bỏ qua rollback-only.
6. **Với async executor:** dùng `CountDownLatch` hoặc `Awaitility`/điều kiện chờ có timeout; đừng assert thứ tự không được đảm bảo.
7. **Với @Async void:** kiểm tra cơ chế `AsyncUncaughtExceptionHandler` chứ không mặc định chờ multicaster ErrorHandler xử lý.
8. **Với AFTER_COMMIT:** kiểm tra callback có được gọi, exception được ghi nhận ở đâu và transaction gốc đã commit như thế nào.
9. **Side effect bên ngoài:** thử lỗi giữa chừng và retry, xác minh không gửi trùng hoặc bỏ mất việc bắt buộc.
10. **Startup/shutdown events:** một cấu hình multicaster toàn cục có thể ảnh hưởng đến listener vòng đời framework; kiểm thử những hành vi quan trọng sau khi thay bean.

### Ví dụ test bằng trạng thái thay vì stdout

Khi viết test tích hợp, có thể thay các lời gọi `System.out.println` ở `Listeners` bằng một `List<String> calls` thuộc test fixture. Kịch bản mặc định kỳ vọng `["first", "fails"]` và exception; kịch bản suppress kỳ vọng `["first", "fails", "last"]` và một lỗi được ghi nhận. Với async, dùng collector thread-safe và await thay vì giả định các listener hoàn tất trước khi `publishEvent(...)` trả về.

Tránh cấu hình global `ErrorHandler` làm cho test “đều xanh” chỉ vì lỗi bị suppress; assert cả số lỗi/metric và dữ liệu kết quả.

## 13. Những lỗi cấu hình phổ biến

1. **Đặt sai tên bean**: `myEventMulticaster` thay vì `applicationEventMulticaster`; context có thể tiếp tục dùng multicaster mặc định.
2. **Nhầm logger với policy**: handler chỉ log rồi trở về là suppress, không phải propagate; transaction có thể tiếp tục.
3. **Coi lỗi listener đã được tự retry**: `ErrorHandler` không có retry queue hay persistence.
4. **Cho rằng listener sau luôn chạy**: nếu handler rethrow hoặc không có handler ở sync multicaster, multicast có thể dừng trước listener sau.
5. **Cho rằng listener trước được rollback hoàn toàn**: email/HTTP/các side effect ngoài transaction DB không tự rollback.
6. **Áp suppress cho invariant bắt buộc**: DB có thể commit dù một bước xử lý nghiệp vụ quan trọng đã thất bại.
7. **Nhầm async với sync**: exception ở thread executor không tự quay về publisher; `@Order` không bảo đảm thứ tự hoàn tất async.
8. **Kỳ vọng multicaster ErrorHandler xử lý mọi @Async exception**: method async được proxy thực thi sau đó có đường quản lý exception riêng.
9. **Kỳ vọng ErrorHandler rollback sau AFTER_COMMIT**: transaction gốc đã commit, không thể đảo ngược vì callback sau commit lỗi.
10. **Nuốt cả Throwable không phân loại**: có thể che lỗi hệ thống nghiêm trọng hoặc làm mất tín hiệu cảnh báo.
11. **Không đo lường lỗi bị suppress**: publisher thấy thành công nhưng consumer có thể không làm xong việc.
12. **Không kiểm tra callback transaction-bound**: nhiều lỗi xảy ra ngoài lời gọi multicaster tại thời điểm publish.
13. **Tưởng @Order đồng nghĩa atomic workflow**: thứ tự listener không làm fan-out thành một transaction message batch.
14. **Chỉ thử happy path**: cần kiểm tra no-handler, suppress, propagate, async, rollback và partial side effects.

## 14. Tóm tắt quyết định theo một tình huống

Giả sử event `OrderSubmitted` có ba listener:

- `ValidateOrder`: xác minh invariant bắt buộc.
- `RecordMetric`: ghi số liệu thống kê.
- `SendReceipt`: gửi email xác nhận.

Không nên chỉ thiết lập global `ErrorHandler` suppress rồi để cả ba listener chạy tùy ý. Thiết kế rõ hơn:

1. Thực hiện `ValidateOrder` như bước bắt buộc trong application service/transaction để lỗi validation có thể ngăn commit.
2. `RecordMetric` có thể dùng error policy ghi metric/log mà không làm hỏng checkout nếu đó thực sự là tác vụ tùy chọn.
3. `SendReceipt` nên đi qua queue/outbox hoặc worker có retry/idempotency nếu không được phép mất email sau commit.
4. Nếu vẫn sử dụng multicaster handler toàn cục, cần document policy với từng loại listener và tránh vô tình che lỗi quan trọng.

Câu hỏi quyết định không phải “ErrorHandler nào làm code ít ném exception nhất?” mà là **“loại lỗi nào phải thất bại toàn bộ nghiệp vụ, loại nào có thể tiếp tục nhưng phải được ghi nhận và xử lý sau?”**

## 15. Tự kiểm tra kiến thức

**Câu 1.** Không cấu hình ErrorHandler, listener thứ hai trong một lượt multicast đồng bộ ném `IllegalStateException`. Có gì xảy ra?

**Đáp án:** Lỗi thường dừng lượt multicast hiện tại, lan tới publisher; listener sau chưa được gọi. Đây là hành vi mặc định của `SimpleApplicationEventMulticaster` khi không dùng async executor.

**Câu 2.** `setErrorHandler(error -> logger.error("...", error))` có làm Spring tự rollback transaction không?

**Đáp án:** Không. Handler log rồi trả về là suppress, nên lỗi listener không còn tự lan đến transaction interceptor. Transaction có thể tiếp tục/commit, trừ khi đã bị rollback-only hoặc còn lỗi khác. Không có giao dịch thì không có gì để rollback.

**Câu 3.** Vì sao một listener lỗi vẫn có thể khiến publisher trả về bình thường?

**Đáp án:** Một `ErrorHandler` đã bắt lỗi và trở về bình thường; multicaster coi exception đó được xử lý và có thể tiếp tục các listener khác.

**Câu 4.** Có thể dùng `ErrorHandler` để retry listener lỗi không?

**Đáp án:** Bản thân interface chỉ nhận `Throwable`, không chứa API retry/ack/replay. Muốn retry có thể cần logic riêng, queue/outbox hoặc framework phù hợp; không mặc định có sẵn.

**Câu 5.** `@Async @EventListener` ném lỗi sau khi phương thức đã được lên lịch. Multicaster ErrorHandler có chắc nhận lỗi không?

**Đáp án:** Không. Lỗi trong phương thức async được xử lý qua cơ chế async/executor; với `void` thường xem `AsyncUncaughtExceptionHandler`.

**Câu 6.** Listener `@TransactionalEventListener(AFTER_COMMIT)` lỗi thì có thể rollback transaction gốc không?

**Đáp án:** Không. Commit đã xảy ra trước callback. Thiết kế xử lý lỗi, retry và transaction mới riêng.

**Câu 7.** Khi multicaster có TaskExecutor, tại sao publisher không tự thấy exception của listener?

**Đáp án:** Lỗi có thể phát sinh trong task ở thread khác, sau khi phương thức `publishEvent(...)` đã trả về. Propagation trong executor khác propagation trong stack đồng bộ.

**Câu 8.** Hai handler `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `LOG_AND_PROPAGATE_ERROR_HANDLER` khác nhau thế nào?

**Đáp án:** Cả hai ghi log, nhưng handler suppress không ném lại lỗi; handler propagate tiếp tục chuyển lỗi lên đường gọi thích hợp. Trong trường hợp async, “đường gọi” có thể là executor task chứ không phải publisher.

## Tài liệu tham khảo

- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): `setErrorHandler`, mặc định xử lý exception, `setTaskExecutor` và giới hạn async.
- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): cấu hình bean `applicationEventMulticaster`, `@EventListener`, thứ tự, async và error handling.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): semantics `publishEvent` và cách bàn giao sự kiện.
- [Spring Framework Javadoc — ErrorHandler](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/util/ErrorHandler.html): interface `handleError(Throwable)`.
- [Spring Framework Javadoc — TaskUtils](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/support/TaskUtils.html): `LOG_AND_SUPPRESS_ERROR_HANDLER` và `LOG_AND_PROPAGATE_ERROR_HANDLER`.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): các phase của `@TransactionalEventListener` và điều kiện transaction.
- [Spring Framework Reference — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): mặc định rollback với RuntimeException/Error và cấu hình rollback rules.
