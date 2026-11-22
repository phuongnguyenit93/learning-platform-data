# Khôi phục tài nguyên giao dịch ngoài sau khi `REQUIRES_NEW` hoàn tất

## Mục tiêu học tập

Trong Spring Framework, `Propagation.REQUIRES_NEW` cho phép một phương thức mở **giao dịch vật lý độc lập** ngay cả khi caller đang có giao dịch. Trong lúc giao dịch mới thực thi, giao dịch ngoài được **tạm ngưng (suspend)**. Khi giao dịch bên trong commit hoặc rollback, Spring dọn dẹp tài nguyên của giao dịch bên trong và **khôi phục (resume)** ngữ cảnh tài nguyên của giao dịch ngoài, để caller tiếp tục đúng transaction ban đầu.

Bài học tập trung vào bước **khôi phục sau khi giao dịch bên trong hoàn tất**. Học xong, bạn có thể:

1. Xác định những dữ liệu ngữ cảnh Spring cần lưu khi suspend và phục hồi khi resume: resource binding, transaction synchronization, tên transaction, read-only, isolation và cờ actual transaction.
2. Mô tả thứ tự suspend → begin inner → commit/rollback inner → cleanup inner → resume outer.
3. Giải thích vì sao outer vẫn là giao dịch cũ sau khi inner đã commit/rollback; phân biệt tiếp tục outer với “tạo outer mới”.
4. Phân tích cả đường thành công, unchecked exception được outer bắt, unchecked exception truyền tiếp, và lỗi khi bắt đầu giao dịch mới.
5. Viết và chạy ví dụ Java 17 + Spring JDBC để kiểm chứng transaction context và sự khôi phục cùng resource, không dựa vào suy đoán từ annotation.
6. Nhận diện các giới hạn: Spring AOP self-invocation, connection pool/lock, khác biệt transaction manager, nhiều nguồn dữ liệu, thread mới và reactive context.

## 1. Bối cảnh: hai giao dịch vật lý nhưng một call stack

Giả sử `CheckoutService.checkout()` có transaction A. Trong phương thức này, service gọi `AuditService.record()` dùng `REQUIRES_NEW` để ghi một bản ghi audit cần commit độc lập. Khi gọi `record()` thông qua Spring AOP proxy, Spring phải tránh để transaction B vô tình dùng connection/transaction A đang gắn với thread hiện tại.

```text
Caller
  |
  v
CheckoutService.checkout()     Transaction A đang hoạt động
  |
  +-- AuditService.record()   @Transactional(REQUIRES_NEW)
  |      |
  |      +-- suspend A
  |      +-- begin B
  |      +-- chạy INSERT audit trong B
  |      +-- commit hoặc rollback B
  |      +-- cleanup B
  |      +-- resume A
  |
  +-- tiếp tục xử lý checkout trong transaction A
  |
  +-- commit hoặc rollback A
```

Điểm quan trọng:

- **Transaction B** có vòng đời commit/rollback độc lập; hoàn tất B không có nghĩa A đã hoàn tất.
- **Transaction A** không bị commit, rollback, reset về đầu hoặc thay thế bằng transaction khác khi B chạy. A vẫn tồn tại và có thể giữ connection/lock của chính nó.
- Sau khi B hoàn tất, Spring *rebind* tài nguyên A vào ngữ cảnh xử lý để những lệnh JDBC tiếp theo của outer tiếp tục dùng A.
- Khi việc resume thành công, outer không phải tự mở lại transaction bằng `@Transactional` khác. Việc khôi phục là trách nhiệm của transaction manager.

Tài liệu Spring mô tả `REQUIRES_NEW` là một **independent physical transaction**; do đó B có thể commit trong khi A rollback sau đó, và các thiết lập isolation/timeout/read-only của B không bị kế thừa từ A.

## 2. Phân biệt ba thứ dễ bị gọi nhầm là “transaction”

| Thành phần | Vai trò trong ví dụ A → B → A |
|---|---|
| **Physical transaction A** | Giao dịch thực trên JDBC connection của outer; chưa kết thúc khi B chạy |
| **Physical transaction B** | Giao dịch thực khác, có thể dùng JDBC connection khác, commit/rollback riêng |
| **Thread-bound transaction context** | Các thông tin Spring lưu cho thread (resource map, synchronization và metadata) để lớp truy cập dữ liệu biết hiện tại đang tham gia giao dịch nào |

Với `JdbcTransactionManager`/`DataSourceTransactionManager`, transaction manager làm việc với `DataSource`. Spring có thể gắn một `ConnectionHolder` vào `TransactionSynchronizationManager` theo key là datasource; các API Spring-aware như `JdbcTemplate` lấy connection đang bind để tham gia transaction.

Khi **suspend A**, Spring có thể **tạm tháo binding A khỏi thread** rồi lưu đối tượng resource đó trong holder phục vụ resume. Resource của A vẫn thuộc giao dịch A và chưa được “thả về pool” chỉ vì tạm ngưng. Khi **begin B**, Spring ràng buộc resource của B vào thread để JDBC call trong inner không nhầm sang A. Khi **resume A**, Spring tháo resource B đã hoàn tất và bind lại chính resource A.

Đừng diễn giải việc “tạm ngưng” thành tạm đóng kết nối A hay giải phóng lock của A. Với database có lock đang được A giữ, B có thể bị chặn nếu cần cùng hàng/bảng. Tạm ngưng ở tầng Spring chủ yếu là **tạm chuyển ngữ cảnh giao dịch đang nhìn thấy**, không phải lệnh SQL buộc DB nhả lock.

## 3. Thứ tự thực tế của suspend và resume

Với cơ chế nền tảng `AbstractPlatformTransactionManager` và một manager hỗ trợ suspension, luồng khái quát khi outer đang có transaction:

```text
[Thread hiện tại]
A: actual=true; datasource -> holder A; sync A
    |
    | Inner method được gọi QUA PROXY, propagation=REQUIRES_NEW
    v
suspend(A):
    1. Gọi suspend() trên TransactionSynchronization đang đăng ký cho A
    2. Tạm dừng/clear synchronization của A trên thread
    3. doSuspend(A): transaction manager gỡ resource A
    4. Lưu metadata của A: name, readOnly, isolation, wasActive
    |
    v
begin(B):
    5. doBegin(B): tạo/bind resource mới cho B
    6. Đặt synchronization/metadata của B
    |
    v
execute inner:
    7. Thực thi thao tác database trong B
    |
    v
complete(B):
    8. Commit B hoặc rollback B theo kết quả và chính sách
    9. Clear synchronization + doCleanupAfterCompletion(B)
    |
    v
resume(A):
   10. doResume(A): bind lại resource đã lưu của A
   11. Khôi phục name, readOnly, isolation, actual-transaction flag của A
   12. Khởi tạo lại synchronization A, gọi resume() trên từng callback
    |
    v
A: actual=true; datasource -> holder A; sync A
    |
    v
Outer tiếp tục trên cùng physical transaction A
```

Sơ đồ mô tả hành vi chuẩn trong Spring Framework 6.x với `AbstractPlatformTransactionManager`. Các subclass transaction manager chịu trách nhiệm hiện thực những thao tác chuyên biệt `doSuspend`/`doResume`. Nếu transaction manager không hỗ trợ suspend (hoặc hệ thống transaction bên dưới thiếu khả năng cần thiết), việc dùng `REQUIRES_NEW` khi đang có transaction có thể thất bại; không được coi sơ đồ là bảo đảm mọi manager đều thực hiện thành công.

**Phân biệt hai lớp callback:**

- `TransactionSynchronization.suspend()` và `resume()` dành cho **synchronization được đăng ký**; một implementation quản lý thêm resource có thể tự unbind/rebind resource của mình tại các callback này.
- `AbstractPlatformTransactionManager.doSuspend(...)` và `doResume(...)` là **template methods** của manager để tạm tháo/gắn lại resource transaction chính (ví dụ `ConnectionHolder`).
  
Đây là những cơ chế liên quan nhưng khác trách nhiệm. Không tự gọi chúng bằng business code; hãy để Spring transaction interceptor và transaction manager xử lý.

## 4. Chính xác những gì được khôi phục?

`TransactionSynchronizationManager` quản lý các thông tin gắn với thread cho transaction đồng bộ. Khi A tạm ngưng, Spring giữ thông tin cần thiết để trả lại đúng ngữ cảnh sau B:

| Thành phần | Khi A chạy | Khi B chạy | Sau B, khi A resume |
|---|---|---|---|
| Resource theo datasource | Holder/connection A bind vào thread | A tạm unbind; holder/connection B bind vào thread | Holder/connection A được bind lại |
| Actual transaction flag | `true` | `true` cho B | `true` của A |
| Tên transaction | Tên của A (nếu có) | Tên của B | Tên A được khôi phục |
| Read-only metadata | Cờ read-only của A | Cờ read-only B | Cờ A được khôi phục |
| Isolation metadata | Mức A | Mức B | Mức A được khôi phục |
| Synchronization callbacks | Danh sách callback A | Danh sách callback B riêng | Callback A được đăng ký lại, `resume()` được gọi |

Trong nhiều ví dụ annotation-driven, tên transaction lấy từ method giao dịch. Tên có thể khác hoặc không có trong các cấu hình chuyên biệt; không xây dựng logic nghiệp vụ dựa vào chuỗi tên.

Một số giá trị như **timeout deadline của transaction A** không thể “đặt lại đồng hồ” chỉ bằng resume; transaction A vẫn mở và thời gian B chạy có thể góp vào tổng thời gian giữ resource của A. B cũng có thể có isolation, timeout và read-only riêng. Việc Spring khôi phục metadata không đồng nghĩa hai transaction đã sử dụng chung cấu hình hay cùng physical connection.

**Đừng nhầm:** `isSynchronizationActive()` cho biết Spring đang quản lý synchronization trên thread; nó có thể `true` ngay cả khi không có actual database transaction trong một số propagation khác. Muốn kiểm tra trong demo JDBC, nên dùng `isActualTransactionActive()` kết hợp việc so sánh resource và trạng thái transaction.

## 5. Resume xảy ra khi inner commit, rollback hoặc ném exception

Với lời gọi qua proxy, cơ chế transaction xử lý hoàn tất trước khi điều khiển quay về caller:

### 5.1. Inner hoàn tất bình thường

1. Inner trả về không ném lỗi → interceptor của B quyết định commit B.
2. Spring gọi cleanup cho B: clear metadata/synchronization của B và dọn resource B.
3. Spring resume A (khôi phục holder và synchronization).
4. Chỉ sau đó lời gọi `innerService.inner()` mới trả về cho outer.
5. Outer tiếp tục và cuối cùng tự commit hoặc rollback A.

Nếu B đã commit dữ liệu, rollback A **không xóa dữ liệu đã commit trong B**. Đây là tính độc lập chủ đích của `REQUIRES_NEW`.

### 5.2. Inner ném unchecked exception, outer bắt và tiếp tục

1. Inner ném `RuntimeException`; chính sách rollback mặc định khiến Spring rollback B.
2. Spring cleanup B và resume A trước khi exception đi đến `catch` của outer.
3. Outer bắt lỗi, xử lý và tiếp tục làm việc với tài nguyên A đã được khôi phục.
4. Outer có thể commit A nếu chính A không bị đánh dấu rollback-only và không gặp lỗi khác.

Nguyên tắc này khác `REQUIRED`: khi inner `REQUIRED` tham gia A và làm A rollback-only, outer có thể gặp `UnexpectedRollbackException` khi cố commit. Inner `REQUIRES_NEW` rollback B **không tự động đánh dấu A rollback-only**. Tuy nhiên outer vẫn có thể chủ động rollback hoặc bị buộc rollback vì một lỗi khác.

### 5.3. Inner ném exception, outer không bắt

Spring vẫn hoàn tất B và khôi phục ngữ cảnh A trong đường xử lý bình thường, rồi chuyển exception cho outer. Vì lỗi unchecked thoát ra khỏi method outer, **transaction interceptor của outer** có thể rollback A theo quy tắc mặc định. Sự kiện “A cũng rollback” trong trường hợp này **không phải vì B rollback đã lan sang A**, mà vì exception đi qua ranh giới `@Transactional` của A.

### 5.4. Nếu bắt đầu B thất bại

Spring có đường xử lý khôi phục A khi bước begin B ném lỗi; `AbstractPlatformTransactionManager` có cơ chế resume sau begin exception. Tuy nhiên nếu lỗi ở chính việc suspend/resume hoặc resource/transaction manager bị hỏng, **không bảo đảm** ứng dụng sẽ tiếp tục bình thường. Đừng giả định một lỗi hệ thống nghiêm trọng chỉ cần `catch` là đã an toàn commit A.

## 6. Ví dụ Java 17: kiểm chứng đúng resource được resume

Ví dụ dùng Spring Framework 6.2.19, H2 in-memory, `JdbcTemplate`, `JdbcTransactionManager` và class-based AOP proxy. Ví dụ tập trung vào **chính sự khôi phục của A**, không phải chỉ chứng minh B commit độc lập.

Ba kịch bản:

- **B commit, A rollback:** sau inner, outer vẫn thấy đúng resource A; B đã commit thì còn dữ liệu.
- **B rollback, outer bắt lỗi rồi A commit:** A được resume trước `catch`; A vẫn tiếp tục ghi/commit.
- **B rollback, lỗi tiếp tục truyền ra outer:** dùng `finally` để kiểm tra A đã resume trước khi interceptor ngoài rollback A.

Để quan sát suspend/resume, outer tự đăng ký một `TransactionSynchronization` có hai callback in log. Mỗi outer method lưu tham chiếu tới resource binding của mình trước khi gọi B rồi so sánh **cùng instance** sau khi B kết thúc. Đây là phép kiểm chẩn đoán hợp lý với transaction manager JDBC trong demo; business code thông thường không nên phụ thuộc identity của `ConnectionHolder`.

### 6.1. Cấu trúc dự án

```text
spring-resume-demo/
├── pom.xml
└── src/main/java/com/example/tx/Main.java
```

### 6.2. Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-resume-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` và các dependency liên quan cung cấp Spring bean/AOP; `spring-jdbc` cung cấp transaction manager và JDBC helpers; H2 cung cấp database trong bộ nhớ. Ứng dụng không cần Spring Boot. Những phiên bản trong ví dụ được cố định để dễ tái hiện; ứng dụng thực nên sử dụng BOM đã kiểm thử và chính sách cập nhật phiên bản.

### 6.3. Tệp `src/main/java/com/example/tx/Main.java`

```java
package com.example.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class Main {

    private static boolean actualTx() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:resume_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        public OuterService outerService(
                JdbcTemplate jdbc, DataSource ds, InnerService inner) {
            return new OuterService(jdbc, ds, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void perform(boolean shouldFail) {
            boolean fresh = TransactionAspectSupport.currentTransactionStatus()
                    .isNewTransaction();
            System.out.println("B actual=" + actualTx() + " new=" + fresh);

            jdbc.update("INSERT INTO tx_events(label) VALUES (?)",
                    shouldFail ? "b-rollback" : "b-commit");

            if (shouldFail) {
                throw new IllegalStateException("inner failed");
            }
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, DataSource ds, InnerService inner) {
            this.jdbc = jdbc;
            this.dataSource = ds;
            this.inner = inner;
        }

        private Object getBoundResource() {
            return TransactionSynchronizationManager.getResource(dataSource);
        }

        private Object watchOuterTransaction() {
            Object holder = getBoundResource();
            if (holder == null || !actualTx()) {
                throw new IllegalStateException("outer transaction missing");
            }

            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void suspend() {
                        System.out.println("A sync suspend");
                    }

                    @Override
                    public void resume() {
                        System.out.println("A sync resume");
                    }
                }
            );
            return holder;
        }

        private void showRestored(Object holder, String label) {
            System.out.println(label + " same holder=" +
                    (holder == getBoundResource()) +
                    " actual=" + actualTx());
        }

        @Transactional
        public void innerCommitsOuterRollsBack() {
            Object holder = watchOuterTransaction();

            // A chưa sửa hàng/bảng nào; B tránh bị khóa bởi A trong demo.
            inner.perform(false);

            showRestored(holder, "A after B commit");
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", "a-rollback");
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void innerRollsBackOuterCommits() {
            Object holder = watchOuterTransaction();

            try {
                inner.perform(true);
            } catch (IllegalStateException ex) {
                System.out.println("A caught=" + ex.getMessage());
            }

            showRestored(holder, "A after B rollback");
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", "a-commit");
        }

        @Transactional
        public void innerFailurePropagates() {
            Object holder = watchOuterTransaction();

            try {
                inner.perform(true);
            } finally {
                showRestored(holder, "A in finally");
            }
        }
    }

    private static void scenario(
            String title, Runnable action, JdbcTemplate jdbc) {
        System.out.println("=== " + title + " ===");

        try {
            action.run();
        } catch (IllegalStateException ex) {
            System.out.println("caller caught=" + ex.getMessage());
        }

        System.out.println("rows=" + jdbc.queryForList(
                "SELECT label FROM tx_events ORDER BY id", String.class));
        jdbc.update("DELETE FROM tx_events");
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "CREATE TABLE tx_events (" +
                    "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
                    "label VARCHAR(40) NOT NULL)"
            );

            OuterService outer = context.getBean(OuterService.class);

            scenario("B_COMMIT_A_ROLLBACK",
                    outer::innerCommitsOuterRollsBack, jdbc);
            scenario("B_ROLLBACK_A_COMMIT",
                    outer::innerRollsBackOuterCommits, jdbc);
            scenario("B_ERROR_PROPAGATES",
                    outer::innerFailurePropagates, jdbc);
        }
    }
}
```

**Vì sao code được cấu trúc như vậy?**

- `@EnableTransactionManagement(proxyTargetClass = true)` bật class-based proxy. Không có interface là lựa chọn giản tiện của demo, không phải điều kiện bắt buộc của `REQUIRES_NEW`.
- `OuterService` gọi một bean `InnerService` khác do Spring quản lý. Nếu gọi `this.perform()` trong cùng class, self-invocation sẽ bỏ qua proxy và có thể không tạo transaction B.
- Cùng `DataSource` được truyền vào `JdbcTemplate` và `JdbcTransactionManager`. Điều này cho phép Spring gắn JDBC connection đúng với transaction của mình.
- `watchOuterTransaction()` lưu `ConnectionHolder` như một `Object` và đăng ký một synchronization thuộc A. Các callback `suspend()` và `resume()` được Spring gọi quanh B.
- `showRestored()` kiểm tra holder A trước/sau có **cùng identity** khi trở lại outer. Đây là quan sát cho cơ chế JDBC cụ thể, không phải hợp đồng nghiệp vụ rằng mọi transaction manager phải expose holder giống nhau.
- `InnerService.perform()` kiểm tra transaction B đang actual và có `isNewTransaction()=true`, rồi ghi dữ liệu. Với `shouldFail=true`, unchecked exception khiến transaction B rollback.
- `OuterService` không ghi vào bảng trước khi chạy B để demo H2 tránh tranh chấp lock giữa connection A và connection B trên cùng bảng. Trong thực tế, outer hoàn toàn có thể giữ lock trước khi gọi inner; đó là rủi ro cần thiết kế riêng.

### 6.4. Lệnh chạy và stdout dự kiến

Với JDK 17+ và Maven đã cài, vào thư mục dự án rồi chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.Main
```

Những dòng được **chính chương trình** in ra (không tính thông điệp Maven hoặc logging thêm của hạ tầng):

```text
=== B_COMMIT_A_ROLLBACK ===
A sync suspend
B actual=true new=true
A sync resume
A after B commit same holder=true actual=true
caller caught=outer failed
rows=[b-commit]
=== B_ROLLBACK_A_COMMIT ===
A sync suspend
B actual=true new=true
A sync resume
A caught=inner failed
A after B rollback same holder=true actual=true
rows=[a-commit]
=== B_ERROR_PROPAGATES ===
A sync suspend
B actual=true new=true
A sync resume
A in finally same holder=true actual=true
caller caught=inner failed
rows=[]
```

**Phân tích chính xác từng trường hợp:**

1. **B commit, A rollback:** `A sync suspend` xảy ra trước khi method B chạy. Sau B hoàn tất, `A sync resume` xuất hiện **trước khi outer in kết quả**, và `same holder=true`. Outer ném lỗi nên A rollback; hàng `b-commit` tồn tại vì B đã commit độc lập.
2. **B rollback, outer catch:** A đã resume **trước khi catch block trong outer chạy**. `same holder=true` cho thấy thao tác ghi `a-commit` tiếp tục cùng A; outer hoàn tất bình thường và commit. Hàng `b-rollback` đã bị rollback ở B.
3. **B rollback, lỗi truyền ra:** khối `finally` của outer vẫn quan sát A đã khôi phục. Sau đó lỗi unchecked đi qua transaction interceptor outer, khiến A rollback. Cơ chế resume của A vẫn xảy ra mặc dù outer không chọn xử lý exception.

Lưu ý trong demo, các nhãn A/B chỉ giúp đọc log. **Việc B rollback không tự làm A rollback-only**. Trường hợp (3) A rollback do chính exception đi qua ranh giới transaction ngoài. Nếu dùng connection pool, dấu hiệu lấy/giữ connection sẽ khác hạ tầng demo, nhưng nguyên tắc transaction không đổi.

## 7. Những điều Spring không “khôi phục” theo nghĩa tự động sửa trạng thái nghiệp vụ

### 7.1. Resume không hoàn tác dữ liệu B đã commit

`REQUIRES_NEW` tạo giao dịch vật lý mới, nên B commit trước rồi A rollback thì dữ liệu B vẫn ở database. Nếu thao tác B là audit, tình huống này có thể chủ đích. Nếu B là cập nhật số dư phụ thuộc trực tiếp vào một thao tác A chưa commit, dữ liệu có thể trở nên không nhất quán. Cần xác định đúng transaction boundary hoặc cân nhắc outbox và thiết kế eventual consistency.

### 7.2. Resume không giải phóng sớm lock/connection của A

A có thể tiếp tục giữ connection và các lock trong suốt lúc B chạy. B có thể cần connection thứ hai và đụng các row A đang khóa; khi đó inner có thể block hoặc timeout. Spring khuyên chuẩn bị connection pool đủ lớn khi dùng `REQUIRES_NEW` trong tải đồng thời; hướng dẫn tối thiểu phổ biến là kích thước pool vượt số thread đồng thời ít nhất một connection, và cần dự toán thêm nếu có nhiều tầng giao dịch độc lập.

Ví dụ thiết kế nguy hiểm:

```text
A: UPDATE accounts SET balance = ... WHERE id = 10
   (giữ row lock của id=10)
    |
    +-- B REQUIRES_NEW: UPDATE accounts SET ... WHERE id=10
                       (có thể đợi lock của A)
    |
A không thể tiếp tục đến commit để nhả lock
cho đến khi B hoàn tất.
```

Kết quả cụ thể phụ thuộc DB và isolation, nhưng đây là nguy cơ tự chặn giữa hai physical transaction, không phải lỗi khôi phục tài nguyên của Spring.

### 7.3. Resume không “tua lại” timeout của A

Transaction A không được tạo mới, nên thời gian giữ tài nguyên của A tiếp tục tích lũy. B có timeout riêng; resume A không có nghĩa A được cấp lại trọn timeout ban đầu. Nếu outer đã sát deadline hoặc inner chạy lâu, một thao tác A sau resume vẫn có thể bị timeout, dù bản thân B đã commit thành công.

### 7.4. Resume không xóa rollback-only của A

Nếu A đã rollback-only trước khi gọi B, việc B commit và A resume không làm A trở lại trạng thái có thể commit. `REQUIRES_NEW` chỉ đảm bảo transaction B riêng; nó không “chữa” một transaction outer đã không còn khả năng commit.

### 7.5. Resume không làm transaction của A tự chạy trên thread khác

`TransactionSynchronizationManager` của transaction imperative dựa vào ngữ cảnh **thread-bound**. Nếu tạo một thread mới, dùng `@Async` hoặc tự lên lịch task, tài nguyên A không tự theo thread đó. `REQUIRES_NEW` trong thread mới có thể tạo một transaction riêng khác, nhưng không phải continuation/resume của A. Phần code này cũng không thể dùng nguyên trạng cho R2DBC/reactive transaction, vốn gắn ngữ cảnh vào Reactor `Context`.

## 8. So sánh nhanh với các propagation khác để tránh nhầm

| Propagation của inner | Có tạm ngưng A? | Inner có physical transaction riêng? | Điều gì cần khôi phục? |
|---|---|---|---|
| `REQUIRED` | Không | Không, nếu A đã tồn tại | Không có suspend/resume outer; inner tham gia A |
| `REQUIRES_NEW` | **Có** | **Có**, transaction B riêng | Resource và synchronization/metadata của A sau B |
| `NOT_SUPPORTED` | Có, nếu A tồn tại | Không | Resource và synchronization/metadata của A sau đoạn non-transactional |
| `NESTED` | Thường không, nếu JDBC savepoint được hỗ trợ | Không; savepoint trong A | Không có transaction B riêng để resume như `REQUIRES_NEW` |

Mục tiêu của bảng là giải thích **có cần restore outer hay không**; mỗi propagation còn có những điều kiện riêng và được transaction manager quyết định. Không suy rộng `NESTED` sang mọi JPA/R2DBC manager. `NOT_SUPPORTED` có thể khiến câu SQL dùng connection auto-commit và không còn rollback theo A.

## 9. Lỗi thường gặp khi kiểm tra resume

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| B không tạo transaction riêng; vẫn cùng holder A | Self-invocation, lời gọi không qua proxy hoặc annotation không được xử lý | Gọi bean inner khác qua Spring proxy, bật transaction management |
| Sau B, code outer không thấy transaction A | Code chạy ở thread khác; transaction manager/data source khác; ngữ cảnh bị can thiệp thủ công | Giữ lời gọi sync qua proxy và cùng manager/resource, tránh đụng `TransactionSynchronizationManager` thủ công |
| B không mở được connection | Pool đã cạn vì A vẫn giữ connection | Xem lại `REQUIRES_NEW`, giới hạn đồng thời, sizing pool |
| B bị timeout khi update cùng dữ liệu với A | A giữ lock trong thời gian suspend | Rút ngắn A, thay thứ tự truy cập, tránh cập nhật hàng đang bị A khóa |
| B commit nhưng A rollback rồi audit vẫn còn | Hoạt động **đúng** của hai transaction độc lập | Chỉ dùng nếu business yêu cầu ghi độc lập |
| Inner ném lỗi, outer cũng rollback dù đã resume | Exception unchecked truyền tiếp qua interceptor của A | Nếu muốn A tiếp tục thì outer phải có chính sách xử lý lỗi hợp lệ; không bắt lỗi mù quáng |
| Inner rollback, A catch nhưng commit không được | A đã rollback-only vì lỗi khác hoặc chính outer đánh dấu rollback-only | Theo dõi trạng thái A và nguyên nhân rollback-only |
| Không thấy `suspend()/resume()` callback | Chưa đăng ký synchronization trên A, manager không dùng synchronization như giả định, hoặc proxy không hoạt động | Dùng đúng transaction manager và đăng ký callback trong transaction A, kiểm tra integration test |
| Resume thất bại | Manager/resource không hỗ trợ, transaction coordinator lỗi hoặc trạng thái connection hỏng | Xử lý như lỗi hệ thống, theo dõi transaction exception; không mặc định tiếp tục commit A |
| Test đơn lẻ chạy nhưng chạy nhiều request lại treo | Pool nhỏ, lock conflict hoặc concurrent transaction nesting | Stress test với pool/DB thật và đo số connection chờ |

**Chú ý về debug:** Có thể bật logging cho `org.springframework.transaction` và `org.springframework.jdbc.datasource` ở DEBUG/TRACE tùy phiên bản để quan sát tạo mới, suspend, resume và cleanup. Tuy nhiên hãy kết hợp log với kiểm tra dữ liệu sau commit/rollback; chỉ thấy `actualTx=true` trong outer chưa chứng minh resource A đã được restore chính xác.

**Ranh giới quản lý:** `TransactionSynchronizationManager.bindResource`, `unbindResource` và các callback synchronization là cơ chế hạ tầng. Đừng viết business code để tự tháo/bind connection với hy vọng điều khiển `REQUIRES_NEW` thủ công. Trong trường hợp cần kiểm soát transaction bằng lập trình, dùng `TransactionTemplate` với `PlatformTransactionManager` phù hợp; transaction manager vẫn thực hiện suspend/resume.

## 10. Bài tập kiểm tra hiểu biết

1. **B đã commit, A còn đang suspend. Sau B trở về A, A dùng connection nào?** Với local JDBC transaction manager trong ví dụ, Spring bind lại holder/connection A đã lưu; A không đổi thành connection B.
2. **B rollback, A bắt exception. A có nhất thiết rollback?** Không. A có thể tiếp tục/commit nếu chưa bị đánh dấu rollback-only và không còn lỗi gây rollback ở boundary A.
3. **B rollback, outer không bắt exception. Vì sao A thường rollback?** Vì unchecked exception thoát khỏi outer và bị transaction interceptor của A xử lý, không phải B tự truyền rollback-only sang A.
4. **Suspend có nhả lock DB của A không?** Không. Physical A vẫn mở và có thể giữ lock.
5. **`TransactionSynchronization.suspend()` có phải callback `afterCompletion` không?** Không. Suspend/resume dùng cho việc tạm tháo/khôi phục synchronization, trong khi completion callback phản ánh kết thúc transaction.
6. **`REQUIRES_NEW` khác `NESTED` ở điểm chính nào?** `REQUIRES_NEW` dùng physical transaction B độc lập và resume A; `NESTED` thường là savepoint trong cùng physical transaction A.
7. **Vì sao `@Async` không thể tự resume transaction A?** Vì context transaction imperative được quản lý trên thread hiện tại, không mặc nhiên truyền sang thread khác.
8. **Có thể kiểm chứng resume của A trong integration test bằng cách nào?** Giữ resource binding trước inner, kiểm tra synchronization suspend/resume và resource binding sau inner, rồi xác nhận kết quả commit/rollback trong DB.

## Tài liệu tham khảo chính thức

- Spring Framework — Transaction Propagation, phần `PROPAGATION_REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — `AbstractPlatformTransactionManager` Javadoc (`suspend`, `resume`, `doSuspend`, `doResume`): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework — `TransactionSynchronization` Javadoc (`suspend()`, `resume()`): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `DataSourceTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
