# Listener sau commit không rollback được transaction đã xong

Trong Spring Framework, một listener đánh dấu `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` được xử lý **sau khi transaction phát event đã commit thành công**. Vì dữ liệu của transaction gốc đã được xác nhận ở tầng cơ sở dữ liệu, lỗi xảy ra trong listener ở thời điểm này **không thể quay ngược và rollback chính transaction gốc**.

Đây là khác biệt cốt lõi giữa hai câu hỏi:

- **Transaction gốc có thành công không?** Quyết định ở bước commit của transaction.
- **Công việc phát sinh sau commit có thành công không?** Là kết quả riêng của listener, chẳng hạn gửi email, gọi webhook, cập nhật chỉ mục tìm kiếm hoặc lưu bản ghi theo dõi.

Ví dụ: giao dịch tạo đơn hàng đã commit, sau đó listener gửi email gặp lỗi mạng. Đơn hàng **vẫn tồn tại**; email gửi thất bại cần một cơ chế xử lý hoặc thử lại riêng. Không thể “ném exception để rollback đơn hàng” khi commit đã hoàn tất.

## 1. Vị trí của `AFTER_COMMIT` trong vòng đời transaction

Xét luồng tạo đơn hàng:

```text
Service bắt đầu transaction T1
  |
  +-- INSERT orders (chưa commit)
  |
  +-- publishEvent(OrderCreated)
  |     +-- Spring đăng ký listener AFTER_COMMIT với T1
  |         (listener chưa thực thi ở thời điểm publish)
  |
  +-- Phương thức nghiệp vụ kết thúc bình thường
  |
  +-- Transaction manager COMMIT T1 thành công
  |     +-- orders trở thành dữ liệu đã commit
  |
  +-- Chạy listener AFTER_COMMIT
        +-- Gửi email / gọi API / cập nhật dữ liệu phụ
        +-- Nếu lỗi, T1 vẫn đã commit
```

`@TransactionalEventListener` ràng buộc listener với một pha của transaction. Pha mặc định là `AFTER_COMMIT`, vì vậy hai khai báo sau có cùng ý nghĩa:

```java
@TransactionalEventListener
public void onOrderCreated(OrderCreated event) {
    // Sau khi transaction nguồn commit thành công.
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    // Cùng pha như khai báo mặc định.
}
```

*Đây là hai cách khai báo thay thế nhau, không đăng ký cả hai phương thức cùng lúc nếu chỉ muốn xử lý một lần.*

Phân biệt các pha:

| Pha | Thời điểm | Lỗi có thể làm transaction nguồn rollback? |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit, khi transaction chưa kết thúc | Có thể làm commit thất bại và dẫn đến rollback; còn phụ thuộc luồng và transaction manager |
| `AFTER_COMMIT` (mặc định) | Sau khi commit thành công | **Không**: transaction nguồn đã commit |
| `AFTER_ROLLBACK` | Sau khi transaction đã rollback | **Không**: rollback đã xảy ra |
| `AFTER_COMPLETION` | Sau khi kết thúc, bất kể commit hay rollback | **Không**: kết quả transaction nguồn đã được quyết định |

Lưu ý: Spring triển khai listener `AFTER_COMMIT` thông qua cơ chế đồng bộ hoàn tất transaction; không nên suy ra rằng listener được gọi từ `TransactionSynchronization.afterCommit()` chỉ vì tên pha giống nhau. Điều cần dựa vào là hợp đồng của `@TransactionalEventListener`: callback xử lý sau khi transaction nguồn đã commit thành công.

## 2. Vì sao exception trong listener không hoàn tác commit?

Rollback chỉ có thể tác động tới một transaction đang ở trạng thái có thể hoàn tác. Khi database đã xác nhận `COMMIT` của T1, những thay đổi của T1 đã thuộc về trạng thái bền vững của database. Một exception xảy ra **sau** thời điểm đó không có quyền đảo ngược quyết định commit vừa hoàn thành.

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendNotification(OrderCreated event) {
    throw new IllegalStateException("Email provider unavailable");
}
```

Đoạn trên minh họa callback có lỗi. Tùy đường đi callback và cách Spring/ứng dụng xử lý exception, lỗi có thể được ghi log hoặc được phản ánh ở lớp gọi; **không có nhánh nào biến lỗi sau commit thành rollback của T1**. Không nên diễn giải một HTTP 500 trả về sau cùng là bằng chứng database đã rollback: client có thể nhận lỗi trong khi dữ liệu thực tế đã commit.

Một hệ quả thực tế là **trạng thái của request và trạng thái transaction có thể khác nhau**. Nếu client nhận lỗi rồi thử gọi lại, phải có cơ chế chống tạo đơn trùng (idempotency key, unique constraint hoặc kiểm tra mã yêu cầu) thay vì giả định “request lỗi nghĩa là chưa lưu”.

## 3. Ví dụ Java 17+ có thể chạy: email lỗi nhưng đơn hàng vẫn được commit

Ví dụ dùng Spring Framework, Spring JDBC và cơ sở dữ liệu H2 trong bộ nhớ. `TransactionTemplate` tạo transaction thật, `JdbcTemplate` ghi dữ liệu, còn `@TransactionalEventListener` nhận event ở pha sau commit. Không cần Spring Boot.

Cấu trúc thư mục:

```text
after-commit-demo/
├── pom.xml
└── src/main/java/AfterCommitDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>after-commit-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <configuration>
                    <mainClass>AfterCommitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/AfterCommitDemo.java`:

```java
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class AfterCommitDemo {

    public record OrderCreated(long orderId) {}

    public static class NotificationListener {

        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void onOrderCreated(OrderCreated event) {
            // Mô phỏng một dịch vụ gửi thông báo đang bị lỗi.
            try {
                sendEmail(event.orderId());
            } catch (IllegalStateException ex) {
                System.out.println("AFTER_COMMIT: email failed for " + event.orderId());
            }
        }

        private void sendEmail(long orderId) {
            throw new IllegalStateException("Mail server unavailable");
        }
    }

    public static void main(String[] args) {
        var dataSource = new JdbcDataSource();
        dataSource.setURL("jdbc:h2:mem:ordersdb;DB_CLOSE_DELAY=-1");
        dataSource.setUser("sa");

        var jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY)");

        var manager = new DataSourceTransactionManager(dataSource);
        var tx = new TransactionTemplate(manager);

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(NotificationListener.class);
            context.refresh();

            // T1: lưu đơn thành công; gửi email sau commit bị lỗi.
            tx.executeWithoutResult(status -> {
                jdbc.update("INSERT INTO orders (id) VALUES (?)", 42L);
                context.publishEvent(new OrderCreated(42L));
                System.out.println("T1: inserted and published order 42");
            });

            Long count42 = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders WHERE id = 42",
                    Long.class
            );
            System.out.println("T1: committed orders with id 42 = " + count42);

            // T2: lỗi TRƯỚC khi commit; listener AFTER_COMMIT không chạy.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update("INSERT INTO orders (id) VALUES (?)", 43L);
                    context.publishEvent(new OrderCreated(43L));
                    System.out.println("T2: inserted and published order 43");
                    throw new IllegalStateException("Business rule rejected");
                });
            } catch (IllegalStateException ex) {
                System.out.println("T2: rolled back");
            }

            Long count43 = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders WHERE id = 43",
                    Long.class
            );
            System.out.println("T2: committed orders with id 43 = " + count43);
        }
    }
}
```

Từ thư mục dự án, chạy (cần JDK 17+, Maven và khả năng tải dependency lần đầu):

```bash
mvn -q compile exec:java
```

Những dòng chính do chương trình in ra, theo thứ tự:

```text
T1: inserted and published order 42
AFTER_COMMIT: email failed for 42
T1: committed orders with id 42 = 1
T2: inserted and published order 43
T2: rolled back
T2: committed orders with id 43 = 0
```

Giải thích kết quả:

1. Với **T1**, bản ghi đơn `42` được commit. Listener chạy sau commit, mô phỏng gửi email thất bại rồi bắt lỗi; query sau transaction vẫn thấy **một** đơn mang ID `42`.
2. Với **T2**, lỗi được ném ngay trong phần công việc **trước commit**. `TransactionTemplate` thực hiện rollback; listener `AFTER_COMMIT` cho đơn `43` không chạy; query thấy **không có** đơn `43`.
3. Ví dụ bắt exception ngay trong listener để stdout gọn và dễ tái hiện. Nếu để exception thoát ra ngoài, điều đó cũng **không thể rollback T1** vì commit đã hoàn tất; cách báo lỗi cho caller/logging có thể khác tùy đường đi đồng bộ transaction.

Ví dụ dùng record `OrderCreated` làm event payload thông thường; `@TransactionalEventListener` có thể nhận kiểu object này. `NotificationListener` được đăng ký thành Spring bean nên Spring phát hiện annotation. `JdbcTemplate` và `DataSourceTransactionManager` dùng **cùng** `DataSource` để câu INSERT tham gia đúng transaction.

## 4. Cạm bẫy: sau commit vẫn truy cập được tài nguyên transaction

Một hiểu lầm nguy hiểm là: “Đã ở `AFTER_COMMIT` thì mọi thao tác repository tự động mở transaction mới”.

Trong transaction dựa trên thread (ví dụ `DataSourceTransactionManager` hoặc `JpaTransactionManager`), **resource của transaction gốc đôi khi vẫn được bind vào thread và có thể truy cập** trong callback sau commit. Vì vậy, mã truy cập database có thể trông như đang tham gia transaction cũ, nhưng **không còn lượt commit tiếp theo** dành cho transaction đó. Hậu quả là thao tác ghi trong listener có thể không được lưu như người lập trình kỳ vọng.

Đoạn mã sau **chỉ minh họa vấn đề**, giả định `auditRepository` là repository đã được cấu hình:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    auditRepository.save(new AuditLog(event.orderId(), "CREATED"));
    // Không nên mặc định rằng lệnh ghi này chắc chắn được COMMIT.
}
```

Nếu cần lưu thay đổi database **sau commit**, hãy thực hiện việc đó trong **một transaction mới có ranh giới rõ ràng**, chẳng hạn một Spring service riêng với `@Transactional(propagation = Propagation.REQUIRES_NEW)`:

```java
@Service
public class AuditService {
    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAudit(long orderId) {
        auditRepository.save(new AuditLog(orderId, "CREATED"));
    }
}

@Component
public class OrderAuditListener {
    private final AuditService auditService;

    public OrderAuditListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreated event) {
        auditService.saveAudit(event.orderId());
    }
}
```

Đây là **đoạn tích hợp minh họa cho ứng dụng Spring Data**, không phải phần bổ sung vào ví dụ Maven độc lập ở mục 3. Các lớp `AuditRepository` và `AuditLog` phải có trong ứng dụng thực tế; các annotation và kiểu như `@Service`, `@Component`, `@Transactional`, `Propagation` cần import tương ứng.

`REQUIRES_NEW` tạo **transaction vật lý độc lập** cho `saveAudit`, vì vậy bản ghi audit có thể được commit riêng. Nếu transaction audit thất bại, chỉ transaction audit bị rollback; **đơn hàng của T1 vẫn đã commit**. Đặt service ở một Spring bean khác còn giúp lời gọi đi qua proxy transaction của Spring; gọi `this.saveAudit(...)` trong chính cùng một bean theo cơ chế proxy mặc định sẽ bỏ qua interception nên không đạt hiệu quả mong muốn.

Cân nhắc cấu hình connection pool khi dùng `REQUIRES_NEW`: transaction mới cần tài nguyên riêng; lời gọi lồng trong một transaction còn giữ connection có thể làm tăng nhu cầu connection. Đối với callback sau commit, tài nguyên từ transaction gốc cũng có thể chưa được dọn dẹp hoàn toàn.

## 5. Thiết kế đúng nếu công việc sau commit thất bại

`@TransactionalEventListener(AFTER_COMMIT)` phù hợp với các tác vụ phản ứng sau khi dữ liệu chính đã được lưu. Nó **không tự cung cấp** tính năng thử lại bền vững, xử lý trùng lặp, hàng đợi hoặc giao dịch nguyên tử giữa database và email/API ngoài.

### 5.1. Công việc phụ không cần bảo đảm tuyệt đối

Ví dụ: ghi metric best-effort hoặc gửi thông báo không quan trọng. Listener có thể bắt lỗi, ghi log có ngữ cảnh (ID sự kiện, ID đơn hàng), thu thập metric và để transaction chính giữ nguyên kết quả. Quyết định nuốt lỗi phải có chủ đích; nếu client phải biết email lỗi, hãy biểu diễn **trạng thái gửi thông báo riêng** thay vì trả về lỗi khiến client hiểu nhầm đơn hàng chưa được lưu.

### 5.2. Cần bảo đảm công việc sẽ được xử lý lại: Transactional Outbox

Với nghiệp vụ quan trọng (gửi sự kiện cho hệ thống khác, đồng bộ thanh toán, chuyển dữ liệu tới message broker), có một cửa sổ lỗi: database đã commit nhưng ứng dụng bị tắt trước khi callback hoàn tất. Nếu chỉ dựa vào in-memory listener, công việc đó có thể bị mất.

Mẫu **Transactional Outbox** giải quyết cửa sổ này:

1. **Trong cùng transaction T1**, ghi dữ liệu nghiệp vụ (ví dụ `orders`) và một bản ghi `outbox` có ID ổn định, loại event, payload cần thiết và trạng thái `PENDING`.
2. Chỉ khi **T1 commit thành công**, cả đơn hàng và thông điệp outbox mới tồn tại bền vững. Nếu T1 rollback, cả hai biến mất cùng nhau.
3. Một worker độc lập đọc outbox, gửi tới dịch vụ/broker, rồi cập nhật `SENT` bằng transaction riêng.
4. Nếu gửi thất bại hoặc tiến trình dừng, worker có thể thử lại với backoff. Consumer phải xử lý **idempotent** vì có thể gửi lặp khi worker gửi thành công nhưng chưa kịp đánh dấu `SENT`.

```text
T1: INSERT orders + INSERT outbox -> COMMIT
                                   |
                                   v
                       Outbox worker đọc PENDING
                                   |
                      gửi / retry / xử lý trùng lặp
                                   |
                      transaction riêng: SENT
```

Có thể dùng `AFTER_COMMIT` để đánh thức worker xử lý outbox nhanh hơn, nhưng **outbox đã lưu bền vững mới là nguồn bảo đảm phục hồi**; callback chỉ là tín hiệu tối ưu hóa.

### 5.3. Cần “tất cả cùng thành công hoặc không cái nào thành công”

Nếu nhiều bước **đều là thao tác cùng một database** và cần atomic, hãy thực hiện chúng **trước commit trong cùng một transaction** (thường qua một service điều phối), rồi commit một lần. Không thể đạt atomicity giữa việc đã commit đơn hàng và email gửi sau đó chỉ bằng `@Order`, `@Transactional` hoặc `@TransactionalEventListener`.

Nếu có dịch vụ bên ngoài và cần luồng nhiều bước có khả năng khôi phục, thiết kế trạng thái nghiệp vụ và hành động bù trừ (compensation/Saga) khi phù hợp. Bù trừ là một **thao tác nghiệp vụ mới**, không phải rollback kỹ thuật của transaction đã commit.

## 6. Những tình huống dễ nhầm

**Listener thông thường `@EventListener` khác với listener theo transaction.** `@EventListener` đồng bộ có thể được gọi ngay khi `publishEvent(...)` thực thi, khi transaction nguồn còn mở. Exception từ listener thông thường có thể lan truyền và khiến luồng nghiệp vụ trước commit thất bại. `@TransactionalEventListener(AFTER_COMMIT)` chủ động đợi kết quả commit thành công mới xử lý.

**Không có transaction thì listener có thể không chạy.** Mặc định `fallbackExecution = false`, nếu event được phát khi không có transaction thích hợp, listener transaction-bound sẽ **không được gọi**. Cấu hình `fallbackExecution = true` cho phép thực thi khi không có transaction, nhưng khi ấy không còn bảo đảm “chỉ chạy sau một commit thực sự”. Nếu bài toán yêu cầu sau commit chặt chẽ, cần bảo đảm publisher thực sự chạy trong transaction.

**`@Async` không biến công việc sau commit thành một phần của T1.** Nếu thực thi bất đồng bộ, callback có thể chạy trên thread khác. Exception, retry và thứ tự hoàn tất phải được quản lý riêng; transaction context dạng thread-local không tự động đi theo mọi task được chuyển thread.

**`@Order` không sửa được vấn đề.** Dù các listener có thứ tự gọi được chỉ định, một listener chạy `AFTER_COMMIT` vẫn không thể rollback transaction đã commit. Đừng dùng thứ tự listener để thay thế cho ranh giới transaction và quan hệ phụ thuộc nghiệp vụ.

**Không nên xem HTTP 500 là rollback.** Một request có thể báo lỗi do phần hậu xử lý trong khi INSERT đã commit. Khi client gọi lại, dùng mã yêu cầu/idempotency key và unique constraint phù hợp để tránh nhân đôi dữ liệu.

**Không viết vào database sau commit rồi mặc định có commit thứ hai.** Tài nguyên transaction có thể còn truy cập được; dùng transaction mới rõ ràng (`REQUIRES_NEW` qua Spring proxy) cho thay đổi cần lưu độc lập, hoặc đưa phần ghi đó vào transaction gốc nếu bắt buộc atomic.

## 7. Cách kiểm thử và câu hỏi tự đánh giá

Với một bài kiểm thử tích hợp có database thực và transaction manager, nên kiểm chứng ba kịch bản:

| Kịch bản | Trạng thái transaction nguồn | Kỳ vọng |
| --- | --- | --- |
| Commit thành công, listener sau commit gửi email lỗi | Đã commit | Dữ liệu nghiệp vụ vẫn tồn tại; ghi nhận lỗi email riêng |
| Lỗi trong service trước commit | Rollback | Dữ liệu nghiệp vụ không tồn tại; listener `AFTER_COMMIT` không chạy |
| Commit thành công, listener ghi audit bằng transaction `REQUIRES_NEW` nhưng audit rollback | Transaction nguồn đã commit | Dữ liệu nghiệp vụ vẫn tồn tại; audit được xử lý lỗi/retry riêng |

Khi kiểm thử, nên query lại database bằng một kết nối/transaction độc lập sau khi luồng xử lý kết thúc để tránh nhầm dữ liệu còn trong persistence context với dữ liệu thực sự đã commit. Không dùng mỗi log in ra từ listener làm bằng chứng rollback/commit.

Tự kiểm tra:

1. **Nếu `@TransactionalEventListener(AFTER_COMMIT)` ném exception thì đơn hàng trước đó có tự rollback không?** Không, vì commit đã hoàn tất.
2. **Nếu cần ghi một bản ghi audit từ listener thì làm sao?** Dùng transaction độc lập (ví dụ service `REQUIRES_NEW`) hoặc ghi audit trong T1 nếu cần atomic với đơn hàng.
3. **Nếu ứng dụng chết ngay sau commit và trước khi gửi event ra broker thì sao?** Listener in-memory không bảo đảm phục hồi; cân nhắc outbox cùng transaction và worker có retry/idempotency.
4. **Nếu event được phát ngoài transaction thì sao?** Listener transaction-bound mặc định không chạy; `fallbackExecution = true` thay đổi hành vi nhưng không tạo commit giả.

## Tài liệu chính thức

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Javadoc — `@TransactionalEventListener`, cảnh báo về tài nguyên còn active sau completion](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Javadoc — `TransactionSynchronization`](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework Reference — Transaction Propagation (`REQUIRES_NEW`)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)
