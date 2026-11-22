# Transaction phase BEFORE_COMMIT trong Spring Framework Application Events

## 1. Mục tiêu của bài học

`TransactionPhase.BEFORE_COMMIT` cho phép một listener xử lý sự kiện **ngay trước khi Spring thực hiện commit transaction hiện tại**. Đây là một giai đoạn cụ thể của vòng đời transaction, thường được dùng cho kiểm tra điều kiện cuối, chuẩn bị hoặc bổ sung dữ liệu phải nằm **trong cùng transaction**, và các tác vụ phù hợp khi commit vẫn còn khả năng diễn ra.

Sau bài này, bạn có thể:

- Xác định chính xác thời điểm listener `BEFORE_COMMIT` chạy so với `publishEvent(...)`, lúc kết thúc phương thức nghiệp vụ và thao tác commit database.
- Khai báo `@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)`.
- Giải thích sự khác nhau giữa `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`.
- Phân tích tác động khi listener ném exception, transaction rollback, hoặc sự kiện được phát ngoài transaction.
- Viết và chạy ví dụ Java 17+ sử dụng Spring Framework, JDBC transaction và H2, kiểm chứng cả commit thành công lẫn rollback.
- Chọn giai đoạn xử lý phù hợp, tránh gửi tác dụng phụ không thể rollback trước khi database commit.

**Điểm cốt lõi:** “Đã chạy `BEFORE_COMMIT`” có nghĩa **Spring đã đi đến bước chuẩn bị commit**, **không có nghĩa transaction đã commit thành công**.

## 2. `@TransactionalEventListener` và bốn transaction phase

Spring hỗ trợ các phương thức lắng nghe event thông thường bằng `@EventListener` và các listener gắn với transaction bằng `@TransactionalEventListener`.

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreated event) {
    // Được gọi trước commit của transaction chứa thời điểm publish event.
}
~~~

Đây là **một đoạn phương thức minh họa**, chưa phải chương trình Java độc lập: `OrderCreated` cần được định nghĩa, phương thức cần nằm trong bean Spring và phải có transaction tương thích đang hoạt động lúc sự kiện được phát.

Phần `phase` là một giá trị thuộc enum `TransactionPhase`:

| Phase | Thời điểm callback | Dùng khi |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước thao tác commit, khi transaction và tài nguyên liên quan chưa hoàn tất | Kiểm tra cuối cùng, bổ sung/flush dữ liệu cùng transaction |
| `AFTER_COMMIT` | Sau khi commit thành công | Phản ứng với kết quả đã commit; lưu ý khi ghi database thêm cần transaction mới phù hợp |
| `AFTER_ROLLBACK` | Sau khi rollback | Theo dõi hoặc phản ứng với giao dịch thất bại |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, commit hoặc rollback | Dọn dẹp hoặc ghi nhận kết quả chung |

Nếu **không chỉ định `phase`**, `@TransactionalEventListener` mặc định dùng **`AFTER_COMMIT`**. Muốn logic thực thi trước commit phải khai báo `BEFORE_COMMIT` một cách tường minh.

Các phase này mô tả **lúc callback được gọi**, không phải một thứ tự tùy ý do `@Order` quyết định. Ví dụ, một listener `AFTER_COMMIT @Order(-100)` không thể chạy trước `BEFORE_COMMIT @Order(100)` chỉ nhờ giá trị order nhỏ hơn.

## 3. Vòng đời sự kiện khi transaction commit

Giả sử service gọi `publishEvent(...)` trong một transaction đang hoạt động và Spring sử dụng một `PlatformTransactionManager` quản lý transaction theo thread.

~~~text
Bắt đầu transaction
       |
       v
Service thay đổi dữ liệu qua repository/JdbcTemplate
       |
       v
publishEvent(new OrderCreated(...))
       |
       +--> Spring nhận diện @TransactionalEventListener
       |    và đăng ký transaction synchronization
       |
       +--> publishEvent(...) trả về
       |
       v
Service hoàn tất phần thân phương thức
       |
       v
Transaction manager bắt đầu quy trình commit
       |
       +--> BEFORE_COMMIT listener chạy
       |    (vẫn có thể truy cập tài nguyên transaction)
       |
       +--> beforeCompletion callbacks
       |
       +--> Thực hiện commit tài nguyên thực tế
       |
       +--> AFTER_COMMIT nếu commit thành công
       |         hoặc AFTER_ROLLBACK nếu rollback
       |
       +--> AFTER_COMPLETION
       |
       v
Giao dịch hoàn tất
~~~

Hai mốc thời gian hay bị nhầm:

1. **Lúc phát sự kiện:** `publishEvent(event)` thường đưa sự kiện đến cơ chế đăng ký listener transaction; phần thân `BEFORE_COMMIT` chưa được gọi ngay tại đây.
2. **Lúc transaction chuẩn bị commit:** callback `BEFORE_COMMIT` được gọi bởi cơ chế synchronization khi transaction manager tiến hành commit, sau khi phần xử lý nghiệp vụ bên trong transaction đã kết thúc.

Nếu bên ngoài còn một transaction lớn hơn, chẳng hạn phương thức `@Transactional(propagation = REQUIRED)` tham gia transaction đã có, listener gắn với **transaction thực sự chứa lúc phát event** và được gọi khi transaction đó tiến tới commit. Nó không nhất thiết chạy ngay khi phương thức con trả về.

Trong mô hình transaction theo thread, quá trình này dựa trên `TransactionSynchronizationManager` và callback `TransactionSynchronization.beforeCommit(boolean readOnly)`. `BEFORE_COMMIT` xảy ra **trước** `beforeCompletion()` và trước thao tác commit tài nguyên thực tế. Lưu ý: thứ tự tương tác với các synchronization khác có thể còn chịu tác động của `Ordered` và hạ tầng transaction.

### Thế nào là “trước commit”?

- Transaction vẫn đang trong tiến trình kết thúc; các thay đổi JDBC thông thường dùng cùng transaction/resource có thể trở thành một phần của commit nếu mọi thứ thành công.
- Listener có thể ném exception trước commit, khiến quy trình commit bị hủy và transaction rollback.
- Sau khi listener chạy, transaction **vẫn có thể thất bại** do lỗi flush, constraint, kết nối database, deadlock hoặc quyết định rollback khác.
- Vì vậy, không được coi `BEFORE_COMMIT` là bằng chứng dữ liệu đã lưu bền vững.

## 4. Cấu hình đúng cho `BEFORE_COMMIT`

Một listener cơ bản:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public class OrderListeners {

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    @Order(-10)
    public void verify(OrderCreated event) {
        // Kiểm tra điều kiện trước khi commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    @Order(10)
    public void prepareAudit(OrderCreated event) {
        // Bổ sung một bản ghi cần commit chung nếu kiểm tra thành công.
    }
}
~~~

Đây là **đoạn minh họa**: cần khai báo bean Spring, định nghĩa `OrderCreated` và hệ thống transaction thực tế. `@Order(-10)` có mức ưu tiên cao hơn `@Order(10)` giữa các listener cùng phase; số nhỏ được xếp trước số lớn. Tuy nhiên, đừng thiết kế một chuỗi phụ thuộc nghiệp vụ phức tạp hoàn toàn dựa vào order. Ngoài ra, nếu listener trước ném exception, listener phía sau có thể không còn cơ hội chạy trong lần commit đó.

Để `BEFORE_COMMIT` hoạt động theo mô hình imperative thường cần:

- `@TransactionalEventListener` nằm trên **phương thức của bean Spring** được phát hiện bởi cơ chế event listener.
- `publishEvent(...)` xảy ra khi có transaction và synchronization đang hoạt động; ví dụ transaction tạo bởi `@Transactional` qua Spring proxy hoặc `TransactionTemplate`.
- Có `PlatformTransactionManager` phù hợp với resource (JDBC, JPA...) và dùng transaction manager thống nhất cho thao tác nghiệp vụ.
- Không làm mất ngữ cảnh transaction qua việc tự ý chuyển bước đăng ký event sang thread khác.

**Không cần `@EnableAsync`** chỉ để kích hoạt transaction event listener. `@EnableTransactionManagement` cần thiết cho những ví dụ sử dụng `@Transactional` qua proxy; trong chương trình đầy đủ ở mục 6, ta sử dụng `TransactionTemplate` nên không cần cấu hình proxy transaction.

## 5. Khi nào nên sử dụng BEFORE_COMMIT?

Các trường hợp phù hợp thường liên quan đến **nội dung transaction hiện tại**:

1. **Kiểm tra điều kiện cuối cùng:** xác minh tính nhất quán dựa trên dữ liệu đã được service cập nhật, trước khi chốt commit. Kiểm tra này có thể khiến transaction rollback khi ném exception thích hợp.
2. **Bổ sung dữ liệu cùng transaction:** ghi thêm audit nội bộ hoặc một bản ghi outbox dùng cùng database và cùng transaction manager, để những thay đổi này cùng commit hoặc cùng rollback.
3. **Flush/chuẩn bị dữ liệu:** một phần cơ chế hạ tầng có thể đồng bộ hoặc flush trạng thái trước commit. Khi dùng ORM, cần hiểu flush mode, thứ tự synchronization và transaction manager; không mặc định mọi query của listener đều thấy trạng thái chưa flush.
4. **Rà soát tính hợp lệ của một bước:** dùng khi đơn vị thay đổi nằm trong transaction và lỗi phải có khả năng cản commit.

Các trường hợp **không nên dùng trước commit**:

- Gửi email/SMS hoặc gọi API bên ngoài **không thể rollback** với yêu cầu “chỉ gửi nếu DB commit thành công”.
- Công bố message đã xử lý như thể commit đã chắc chắn thành công.
- Thực hiện tác vụ dài, chặn thread/transaction quá lâu, gây tăng thời gian giữ connection và lock.
- Dùng listener để thay thế quy trình nghiệp vụ nhiều bước có phụ thuộc rõ ràng: những bước cốt lõi nên được thể hiện minh bạch trong service.

Ví dụ: nếu gửi email ngay trong `BEFORE_COMMIT` rồi database commit thất bại, người nhận vẫn có thể nhận email về giao dịch chưa tồn tại. Khi cần tác dụng phụ sau commit, cân nhắc `AFTER_COMMIT`; khi cần độ bền và khả năng retry cao, tạo bản ghi **transactional outbox** trong transaction và dùng worker/broker gửi ra ngoài sau đó.

## 6. Ví dụ Java 17+ chạy được: BEFORE_COMMIT với H2 và rollback

Ví dụ này cố ý dùng **Spring Framework thuần** và database H2 trong bộ nhớ để có transaction thật, có thể kiểm chứng kết quả SQL. Có hai sự kiện tạo tài khoản:

- **Mai:** listener kiểm tra thành công, listener audit ghi thêm bảng `audit_log`; cả hai bảng được commit.
- **Lan:** listener kiểm tra ném `IllegalStateException` trước commit; transaction rollback, nên tài khoản Lan không có trong database.

Nhờ sử dụng `TransactionTemplate`, ví dụ không phụ thuộc vào việc gọi phương thức `@Transactional` qua proxy hoặc framework web.

### 6.1. Cấu trúc dự án

~~~text
before-commit-demo/
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── BeforeCommitDemo.java
~~~

Nội dung `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    implementation 'org.springframework:spring-jdbc:6.2.15'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'example.BeforeCommitDemo'
}
~~~

`spring-jdbc` kéo theo hạ tầng transaction cần thiết (`spring-tx`); H2 cung cấp JDBC database cho ví dụ. Hai dependency Spring được dùng **cùng phiên bản** để tránh lệch API. Ứng dụng thực tế dùng Spring Boot thường nên để Boot quản lý phiên bản tương thích.

### 6.2. Mã nguồn đầy đủ

Tạo file `src/main/java/example/BeforeCommitDemo.java`:

~~~java
package example;

import javax.sql.DataSource;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class BeforeCommitDemo {

    public record SignupRequested(String username, boolean reject) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:before_commit_demo;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public BeforeCommitHandlers beforeCommitHandlers(JdbcTemplate jdbc) {
            return new BeforeCommitHandlers(jdbc);
        }
    }

    public static class BeforeCommitHandlers {

        private final JdbcTemplate jdbc;

        public BeforeCommitHandlers(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        @Order(-10)
        public void validate(SignupRequested event) {
            System.out.println("BEFORE_COMMIT validate " + event.username());

            if (event.reject()) {
                throw new IllegalStateException("blocked " + event.username());
            }
        }

        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        @Order(10)
        public void audit(SignupRequested event) {
            jdbc.update(
                    "INSERT INTO audit_log (username) VALUES (?)",
                    event.username());
            System.out.println("BEFORE_COMMIT audit " + event.username());
        }
    }

    private static void register(
            TransactionTemplate transaction,
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher,
            String username,
            boolean reject) {

        transaction.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO user_accounts (username) VALUES (?)",
                    username);

            publisher.publishEvent(new SignupRequested(username, reject));
            System.out.println("published " + username);
        });
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table,
                Integer.class);
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransactionTemplate transaction =
                    context.getBean(TransactionTemplate.class);

            jdbc.execute(
                    "CREATE TABLE user_accounts (username VARCHAR(80) PRIMARY KEY)");
            jdbc.execute(
                    "CREATE TABLE audit_log (username VARCHAR(80) PRIMARY KEY)");

            System.out.println(
                    "initial users=" + count(jdbc, "user_accounts")
                    + ", audits=" + count(jdbc, "audit_log"));

            register(transaction, jdbc, context, "Mai", false);

            System.out.println(
                    "after Mai users=" + count(jdbc, "user_accounts")
                    + ", audits=" + count(jdbc, "audit_log"));

            try {
                register(transaction, jdbc, context, "Lan", true);
            } catch (IllegalStateException ex) {
                System.out.println("rollback Lan: " + ex.getMessage());
            }

            System.out.println(
                    "after Lan users=" + count(jdbc, "user_accounts")
                    + ", audits=" + count(jdbc, "audit_log"));
        }
    }
}
~~~

**Giải thích cấu hình:**

- `DriverManagerDataSource` tạo connection đến H2; `DataSourceTransactionManager` quản lý transaction JDBC trên `DataSource` đó.
- `JdbcTemplate` tham gia transaction hiện tại thông qua cơ chế quản lý connection của Spring. Vì thế, cập nhật `user_accounts` và `audit_log` có thể nằm chung một transaction.
- `TransactionTemplate.executeWithoutResult(...)` mở transaction và commit sau khi callback nghiệp vụ trả về. Nếu bước commit ném lỗi, transaction manager xử lý rollback khi có thể.
- `publishEvent(...)` đăng ký hai listener `BEFORE_COMMIT`. Lúc phát sự kiện, `validate` và `audit` chưa in gì vì đang chờ transaction đi đến giai đoạn commit.
- `@Order(-10)` ưu tiên `validate` chạy trước `audit`; nếu kiểm tra thất bại, callback kế tiếp không được thực thi trong luồng commit bình thường.
- Biến `reject` chỉ để mô phỏng trường hợp lỗi có kiểm soát; mã sản phẩm thật cần điều kiện nghiệp vụ phù hợp.

### 6.3. Chạy và dự đoán stdout

Tại thư mục `before-commit-demo`, với JDK 17+ và Gradle đã cài:

~~~bash
gradle -q run
~~~

Hoặc dùng Gradle Wrapper đã chuẩn bị: `./gradlew -q run` (Linux/macOS) hay `gradlew.bat -q run` (Windows).

Những dòng do chương trình in ra:

~~~text
initial users=0, audits=0
published Mai
BEFORE_COMMIT validate Mai
BEFORE_COMMIT audit Mai
after Mai users=1, audits=1
published Lan
BEFORE_COMMIT validate Lan
rollback Lan: blocked Lan
after Lan users=1, audits=1
~~~

**Phân tích kết quả:**

1. Bắt đầu có 0 tài khoản, 0 bản ghi audit.
2. `register(..., "Mai", false)` chèn tài khoản và phát event bên trong transaction. Dòng `published Mai` xuất hiện **trước** hai dòng listener.
3. Khi `TransactionTemplate` chuẩn bị commit, `BEFORE_COMMIT validate Mai` chạy; sau đó `audit` chèn thêm bản ghi audit bằng cùng JDBC transaction.
4. Commit thành công: truy vấn sau transaction thấy 1 tài khoản và 1 audit.
5. Với Lan, listener `validate` ném `IllegalStateException("blocked Lan")` ở giai đoạn trước commit. Transaction manager rollback, nên cả việc chèn tài khoản Lan cũng bị hủy. `audit` không chạy cho Lan.
6. Truy vấn cuối vẫn là `users=1, audits=1`: transaction của Mai đã commit trước đó và không bị ảnh hưởng bởi lần rollback của Lan.

Như vậy, điều kiện kiểm tra có thể từ chối commit, còn thao tác ghi audit nội bộ được gom vào cùng transaction. Ví dụ này sử dụng transaction thật; chỉ gọi ba phương thức theo thứ tự trong một `main` không thể minh họa chính xác tác dụng của `BEFORE_COMMIT`.

## 7. Lỗi trong BEFORE_COMMIT và rollback

### 7.1. Runtime exception từ listener

`BEFORE_COMMIT` tương ứng callback `TransactionSynchronization.beforeCommit(...)`. Theo hợp đồng Spring, một `RuntimeException` phát sinh tại đây được truyền cho phía gọi commit và **khiến transaction rollback** trong quá trình xử lý thông thường. Ví dụ mục 6 cho thấy ngoại lệ từ `validate` được đưa ra khỏi `TransactionTemplate`, đồng thời H2 không lưu hàng Lan.

Điều cần phân biệt:

- Lỗi trong phương thức nghiệp vụ **trước** khi kết thúc transaction có thể khiến Spring quyết định rollback **trước khi đến giai đoạn `BEFORE_COMMIT`**; trường hợp này listener `BEFORE_COMMIT` không được gọi.
- Lỗi phát sinh **trong** `BEFORE_COMMIT` có thể khiến transaction rollback.
- Ngay cả nếu **mọi** `BEFORE_COMMIT` listener đã chạy thành công, bước commit tài nguyên vẫn có thể lỗi. Thành công ở callback không bảo đảm thành công cuối cùng.
- Nếu catch và nuốt exception bên trong listener, nó sẽ không tự động buộc rollback; khi cần hủy commit phải ném lỗi phù hợp hoặc đánh dấu rollback-only theo cơ chế transaction.

Khi cần chính sách “không commit nếu điều kiện cuối không hợp lệ”, hãy dùng exception có nghĩa rõ ràng (thường là runtime exception) và bảo đảm lỗi không bị một lớp khác nuốt mất. Đừng dùng checked exception tùy ý hay kỳ vọng mọi exception có cách rollback giống nhau; ngữ nghĩa trong callback khác với quy tắc interceptor `@Transactional` cho exception thoát từ phương thức service.

### 7.2. Trường hợp transaction đã rollback-only

Nếu transaction đã được đánh dấu rollback-only hoặc luồng thực thi chủ động rollback, không có thao tác commit bình thường để gọi `BEFORE_COMMIT`. Khi đó, dùng `AFTER_ROLLBACK` để xử lý phản ứng sau rollback, không mong `BEFORE_COMMIT` luôn được chạy chỉ vì đã phát event.

### 7.3. Khi database commit thất bại sau callback

Giả sử `BEFORE_COMMIT` gọi một hệ thống bên ngoài thành công, nhưng bước commit JDBC/JPA sau đó gặp lỗi. Bạn có thể đã tạo một tác dụng phụ không thể hoàn tác trong khi dữ liệu database chưa được commit. Đây là lý do cần phân loại tác vụ “nội bộ cùng transaction” và “hệ thống ngoài” trước khi chọn phase.

## 8. Phát sự kiện khi không có transaction

Mặc định `@TransactionalEventListener` có `fallbackExecution = false`. Nếu `publishEvent(...)` xảy ra ngoài transaction được Spring quản lý, listener **bị bỏ qua** vì Spring không thể đáp ứng thời điểm BEFORE_COMMIT.

~~~java
publisher.publishEvent(new SignupRequested("An", false));
// Ngoài transaction: listener BEFORE_COMMIT mặc định không chạy.
~~~

Đây là đoạn minh họa với `publisher` và `SignupRequested` đã được định nghĩa. Nó không chèn dữ liệu, không tạo transaction và không chạy listener ở chương trình mục 6.

Có thể viết:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.BEFORE_COMMIT,
    fallbackExecution = true)
public void onEvent(SignupRequested event) {
    // Chạy ngay khi không có transaction để gắn callback.
}
~~~

Tuy nhiên, với `fallbackExecution = true`, trường hợp **không có transaction** chỉ là xử lý fallback, **không phải thực hiện một callback trước commit** vì không có commit nào đang chờ. Hãy bật tùy chọn này chỉ khi logic nghiệp vụ cho phép cả hai ngữ nghĩa. Đối với những kiểm tra bắt buộc nằm trong transaction, giữ mặc định `false` để tránh hiểu sai tính nhất quán.

## 9. Thời điểm với @Transactional, TransactionTemplate và propagation

Trong ứng dụng thực tế, event thường được phát từ service:

~~~java
@Service
public class RegistrationService {
    private final UserRepository repository;
    private final ApplicationEventPublisher publisher;

    public RegistrationService(UserRepository repository,
                               ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void register(String username) {
        repository.insert(username);
        publisher.publishEvent(new SignupRequested(username, false));
    }
}
~~~

Đây là **đoạn minh họa**, không thuộc chương trình đầy đủ ở mục 6: cần định nghĩa `UserRepository`, import Spring, cấu hình `@EnableTransactionManagement` hoặc hạ tầng transaction tương đương và gọi method thông qua Spring proxy.

Khi gọi `RegistrationService.register(...)` qua proxy `@Transactional`, transaction interceptor bắt đầu/điều phối transaction. Event đăng ký callback trong transaction đó và `BEFORE_COMMIT` được gọi khi transaction thực sự đi đến commit.

Lưu ý về propagation:

| Trường hợp | Transaction mà event gắn vào |
| --- | --- |
| `@Transactional(REQUIRED)` tạo transaction mới | Transaction mới được tạo |
| `REQUIRED` tham gia transaction đã có | Transaction đang tồn tại; listener chờ commit của transaction bên ngoài |
| `REQUIRES_NEW` tạo transaction độc lập | Transaction mới được suspend/resume tách biệt; listener gắn vào transaction mới |
| `TransactionTemplate` tạo transaction | Transaction do template và `PlatformTransactionManager` quản lý |
| Gọi service từ chính method cùng instance (self-invocation) với proxy `@Transactional` | Lời gọi có thể bỏ qua interceptor; nếu không có transaction khác, listener mặc định bị bỏ qua |
| `@Async` phát event trong thread khác | Chỉ gắn với transaction thực sự hoạt động trong thread phát sự kiện, nếu có |

Không suy luận “method có ghi `@Transactional`” nghĩa là chắc chắn đang có transaction; transaction manager, proxy invocation, propagation, loại hệ thống transaction và thread thực tế đều quan trọng.

## 10. BEFORE_COMMIT, thứ tự listener và async

### 10.1. `@Order` giúp sắp callback cùng phase

Nếu hai listener `BEFORE_COMMIT` có `@Order(-10)` và `@Order(10)`, Spring có thể sắp các callback theo độ ưu tiên của synchronization. Số nhỏ được ưu tiên trước; ví dụ mục 6 tận dụng điều đó để xác thực trước rồi ghi audit.

Nhưng order không phải công cụ để thiết kế một chuỗi nghiệp vụ dài, có nhiều resource và điều kiện phụ thuộc phức tạp. Một bước cốt lõi “A thành công rồi B mới được chạy” nên được thể hiện trực tiếp trong service khi yêu cầu nhất quán chặt.

### 10.2. Không dùng async để kỳ vọng giữ transaction gốc

Spring quản lý transaction imperative chủ yếu theo **thread-bound context**. Nếu chuyển callback sang executor/thread khác, code có thể không còn nhìn thấy transaction mà publisher đang sử dụng. Với `@TransactionalEventListener`, Spring xử lý việc đăng ký synchronization trên thread giao dịch; cơ chế multicaster không tự chuyển mọi listener transaction sang thread pool một cách tùy tiện.

Gắn `@Async` lên phương thức transaction listener cũng là lựa chọn có ngữ nghĩa khác: phần code được uỷ quyền có thể chạy bất đồng bộ, không còn khả năng hủy commit của transaction gốc bằng exception phát sinh sau đó. Vì thế, khi **mục tiêu là kiểm tra rồi quyết định commit hay rollback**, giữ `BEFORE_COMMIT` đồng bộ và tránh `@Async` ở chính bước đó.

### 10.3. Reactive transaction có cơ chế khác

Từ Spring Framework 6.1, transactional event listener còn hỗ trợ reactive transaction, nhưng ngữ cảnh giao dịch reactive được lưu trong **Reactor Context**, không tương đương ThreadLocal của `PlatformTransactionManager`. Với `ReactiveTransactionManager`, phải truyền ngữ cảnh transaction phù hợp qua event source theo API `TransactionalEventPublisher`. Ví dụ JDBC/`TransactionTemplate` ở bài này là **imperative transaction**; không dùng nó để suy luận nguyên xi về reactive transaction.

### 10.4. Event phát trong một BEFORE_COMMIT listener khác

Không nên mặc định rằng event được phát **ngay trong lúc** callback `BEFORE_COMMIT` đang chạy sẽ tạo thêm một callback `BEFORE_COMMIT` kịp thực thi trong chính vòng callback đó. Các transaction synchronizations thường đã được chụp/sắp danh sách cho lượt gọi hiện tại; việc đăng ký thêm callback ở giai đoạn quá muộn có thể không được xử lý tại đúng lượt mong đợi. Nếu có chuỗi nhiệm vụ nhiều bước, điều phối trước thời điểm commit hoặc dùng một listener tường minh thay cho việc tạo chuỗi event mới bên trong callback.

## 11. Đọc/ghi dữ liệu trong BEFORE_COMMIT: những giới hạn thực tế

Listener `BEFORE_COMMIT` có quyền truy cập tài nguyên transaction nhưng không có nghĩa mọi thay đổi sẽ luôn hành xử giống nhau:

- **JDBC với một DataSource/transaction manager:** thao tác qua `JdbcTemplate` sử dụng cùng connection transactional thường tham gia transaction gốc, như ví dụ mục 6.
- **JPA/Hibernate:** có persistence context, dirty checking và các thời điểm flush. Nếu listener đọc bằng SQL trực tiếp nhưng entity chưa flush, kết quả có thể khác với trạng thái object trong persistence context. Nên kiểm chứng với ORM và transaction manager cụ thể, tránh giả định flush tự động xảy ra trước một listener tùy ý.
- **Transaction read-only:** callback `beforeCommit(boolean readOnly)` còn truyền thông tin read-only; không nên lợi dụng listener để ghi dữ liệu nếu transaction được thiết kế chỉ đọc. Việc database có chặn ghi hay không tùy cấu hình.
- **Transaction dài:** listener chạy trước commit có thể làm lock/connection bị giữ lâu hơn; thao tác mạng lâu hoặc retry mù ở đây thường không phù hợp.
- **Dữ liệu nhạy cảm và side effect:** không nhồi password/token vào event; truyền dữ liệu cần thiết, tối thiểu, rõ ngữ nghĩa và tránh lộ thông tin khi log.
- **Idempotency:** khi transaction/service bị retry, sự kiện có thể được phát nhiều lần. Những listener ghi bản ghi cần cân nhắc khóa duy nhất hoặc cơ chế idempotent phù hợp với nghiệp vụ.

Mặc dù `BEFORE_COMMIT` có thể ghi một dòng outbox cùng transaction, **quá trình thực sự gửi message ra broker** nên do tác vụ độc lập xử lý các dòng outbox đã commit; việc xuất bản sang hệ thống bên ngoài trước commit không đem lại tính atomic giữa hai hệ thống.

## 12. Các lỗi hiểu sai thường gặp

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| `BEFORE_COMMIT` nghĩa là database đã lưu thành công | Chưa. Callback xảy ra trước commit và commit vẫn có thể thất bại |
| `publishEvent` gọi listener `BEFORE_COMMIT` ngay lập tức | Thông thường lúc publish chỉ đăng ký synchronization; listener chạy khi transaction tiến tới commit |
| Cứ phát event là `BEFORE_COMMIT` sẽ chạy | Cần transaction/synchronization phù hợp; không có transaction thì mặc định bỏ qua |
| Transaction rollback cũng sẽ chạy `BEFORE_COMMIT` | Nếu rollback đã được quyết định trước quy trình commit, listener này không chạy |
| Exception trong listener không ảnh hưởng transaction | Runtime exception trong `beforeCommit` có thể truyền ra và khiến rollback |
| `@TransactionalEventListener` mặc định là `BEFORE_COMMIT` | Mặc định là `AFTER_COMMIT`; phải đặt `phase` tường minh |
| `@Order(-10)` cao hơn `@Order(10)` nghĩa là transaction sẽ commit trước | Order chỉ sắp callback cùng giai đoạn; không thay đổi các phase hay thời điểm commit |
| Gửi email trong `BEFORE_COMMIT` là an toàn vì chuẩn bị commit | Database vẫn có thể rollback; email không thể rollback cùng database |
| `fallbackExecution=true` tạo transaction khi không có | Không. Listener fallback chạy mà không có commit thực tế |
| Thêm `@Async` mà vẫn mong exception hủy transaction gốc | Công việc async chạy ở ngữ cảnh khác; không bảo đảm can thiệp commit của publisher |

## 13. Hướng dẫn lựa chọn phase theo tình huống

| Yêu cầu | Gợi ý | Lý do |
| --- | --- | --- |
| Kiểm tra điều kiện cuối, sai thì rollback | `BEFORE_COMMIT` đồng bộ hoặc kiểm tra ngay trong service | Có cơ hội chặn commit trước khi hoàn tất |
| Cần ghi audit/outbox vào cùng JDBC transaction | Ghi trực tiếp trong service hoặc trong `BEFORE_COMMIT` với cùng resource/transaction manager | Thành công cùng commit; thất bại cùng rollback |
| Chỉ gửi thông báo nếu transaction đã commit | `AFTER_COMMIT` cho tác vụ phù hợp, hoặc outbox khi cần đảm bảo giao nhận | Tránh gửi thông báo trước kết quả commit |
| Xử lý hậu quả sau rollback | `AFTER_ROLLBACK` | Phản ứng đúng với transaction không thành công |
| Thu hồi tài nguyên/ghi trạng thái khi transaction kết thúc bất kể kết quả | `AFTER_COMPLETION` | Bao phủ cả commit lẫn rollback |
| Yêu cầu message không mất dù ứng dụng chết ngay sau commit | Transactional outbox và worker/message broker | Event nội bộ Spring không phải hàng đợi bền vững |

Không phải mọi thao tác “chuẩn bị trước commit” đều cần listener. Nếu một kiểm tra là **điều kiện cốt lõi để chấp nhận yêu cầu**, viết trực tiếp trong service thường dễ bảo trì, kiểm thử và quan sát lỗi hơn. `BEFORE_COMMIT` hữu ích khi muốn tách một mối quan tâm gắn với transaction khỏi phần code phát event, với hợp đồng thực thi đã được hiểu rõ.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Service phát event bên trong `TransactionTemplate`, sau đó in `"service done"` rồi kết thúc lambda. Listener `BEFORE_COMMIT` in `"listener"`. Dòng nào xuất hiện trước?

**Đáp án:** `"service done"` trước; listener đợi transaction manager tiến tới commit, sau khi lambda nghiệp vụ trả về.

**Câu 2.** Listener `BEFORE_COMMIT` đã gửi email xong, nhưng JDBC commit thất bại. Có thể mặc nhiên hủy email theo rollback không?

**Đáp án:** Không. Email là side effect hệ thống ngoài, không được rollback cùng JDBC transaction.

**Câu 3.** `BEFORE_COMMIT` listener ném `IllegalStateException`. Kết quả trong transaction JDBC thông thường do Spring quản lý là gì?

**Đáp án:** Exception được truyền ra khỏi callback, transaction manager rollback nếu có thể; bên gọi commit nhận lỗi. Không nên catch rồi nuốt lỗi nếu mong ngăn commit.

**Câu 4.** Event được publish ngoài transaction, listener `@TransactionalEventListener(BEFORE_COMMIT)` không có `fallbackExecution`. Có chạy không?

**Đáp án:** Không, mặc định không có transaction thì listener được bỏ qua.

**Câu 5.** Hai handler cùng phase lần lượt có order `20` và `-5`. Cái nào có độ ưu tiên cao hơn?

**Đáp án:** `-5` vì số nhỏ có ưu tiên cao hơn trong cơ chế ordering.

**Câu 6.** Listener `BEFORE_COMMIT` của một method `REQUIRED` tham gia transaction có sẵn chạy khi method con trả về hay khi transaction bao ngoài commit?

**Đáp án:** Khi transaction thực tế bao ngoài đi đến quy trình commit.

## 15. Tài liệu tham khảo

- Spring Framework Reference 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Javadoc `TransactionPhase` — ý nghĩa `BEFORE_COMMIT` và các phase khác: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionPhase.html
- Javadoc `TransactionalEventListener` — `phase`, `fallbackExecution`, transaction context: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
- Javadoc `TransactionSynchronization` — `beforeCommit(...)`, exception và rollback: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework Reference 6.2 — Declarative transaction management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework Javadoc `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework issue #35081 — đăng ký thêm event `BEFORE_COMMIT` trong chính callback `BEFORE_COMMIT`: https://github.com/spring-projects/spring-framework/issues/35081
