# Chia một luồng xử lý dài thành các đoạn giao dịch rõ ràng bằng TransactionTemplate

## 1. Tình huống: một nghiệp vụ dài không nên là một transaction khổng lồ

Giả sử một hệ thống xử lý đơn hàng theo chuỗi bước:

1. Ghi nhận yêu cầu và tạo mã xử lý.
2. Kiểm tra tồn kho hoặc thực hiện tác vụ tính toán.
3. Gọi dịch vụ ngoài để xác nhận thanh toán hay vận chuyển.
4. Cập nhật kết quả vào database.
5. Ghi trạng thái lỗi để có thể thử lại nếu một bước thất bại.

Nếu bao **toàn bộ** luồng bằng một phương thức `@Transactional`, transaction có thể tồn tại trong cả khoảng chờ mạng, retry, xử lý file hoặc công việc CPU lâu. Trong khi đó, connection và một số locks có thể bị giữ, khiến các transaction khác phải chờ.

Ví dụ thiết kế **không nên dùng mặc định**:

~~~java
@Transactional
public void process(long jobId) {
    insertInitialState(jobId);
    callRemotePaymentService();  // Có thể tốn nhiều giây hoặc timeout.
    transformLargeDocument();    // CPU hoặc I/O ngoài database.
    updateFinalState(jobId);
}
~~~

Đây là **đoạn code minh họa**, chưa phải chương trình Java độc lập. Một transaction rộng đôi khi cần thiết nếu tất cả thao tác **trên cùng DB** thực sự phải atomic; nhưng nó **không biến HTTP request hoặc CPU computation thành thao tác rollback được**. Bọc một lời gọi HTTP trong DB transaction không làm dịch vụ HTTP tham gia commit của database.

Với luồng được phép tiến hành từng chặng và có cơ chế phục hồi, có thể chuyển sang nhiều **transaction ngắn, rõ phạm vi** bằng `org.springframework.transaction.support.TransactionTemplate`:

~~~text
TX-1: ghi checkpoint PREPARED -> COMMIT
       |
       v
Công việc lâu / remote I/O, KHÔNG giữ transaction
       |
       v
TX-2: ghi kết quả DONE -> COMMIT
       |
       +-- nếu lỗi -> ROLLBACK TX-2
                      |
                      v
              TX-3: ghi trạng thái RETRY -> COMMIT
~~~

Điều quan trọng nhất: **tách thành các transaction nghĩa là chấp nhận partial commit**. TX-1 đã commit thì lỗi ở TX-2 không tự hoàn tác TX-1. Vì vậy thiết kế cần **state machine, idempotency, cơ chế retry hoặc compensation** thay vì giả định mọi bước sẽ rollback cùng nhau.

## 2. TransactionTemplate dùng để làm gì?

`TransactionTemplate` là API **programmatic transaction management** của Spring cho code imperative, tương tự cách `JdbcTemplate` che đi phần boilerplate JDBC.

Nó cần một `PlatformTransactionManager`. Trong phương thức `execute(...)` hoặc `executeWithoutResult(...)`:

1. TransactionTemplate yêu cầu transaction manager lấy hoặc mở transaction theo `TransactionDefinition`.
2. Chạy callback do ứng dụng cung cấp.
3. Khi callback hoàn tất bình thường, Spring cố commit transaction do scope sở hữu (trừ khi đã đánh dấu rollback-only).
4. Khi callback ném unchecked exception, Spring thực hiện rollback theo semantics của manager rồi truyền exception về caller.
5. Trong các trường hợp lỗi commit, rollback hoặc transaction system, caller vẫn có thể nhận exception; việc callback đã return **chưa đủ** để khẳng định commit thành công.

Cú pháp có kết quả trả về:

~~~java
TransactionTemplate template = new TransactionTemplate(transactionManager);
String value = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO audit_record (event_name) VALUES (?)", "STARTED");
    return "recorded";
});
~~~

Đây là **mảnh minh họa**, cần có `transactionManager`, `jdbcTemplate` và bảng tương ứng. Khi transaction manager mở một transaction mới và `execute` trả về bình thường, phạm vi commit/rollback đã được xử lý; nếu `execute` chỉ **tham gia transaction ngoài**, commit vật lý cuối cùng vẫn thuộc outer.

Với callback không cần trả giá trị:

~~~java
template.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "UPDATE work_item SET state = ? WHERE id = ?",
        "PREPARED", 10);
});
~~~

`executeWithoutResult` là cách viết gọn, có từ Spring Framework 5.2. Nó cho phép lambda truy cập `TransactionStatus` để chủ động `setRollbackOnly()`. Cả hai đoạn là **ví dụ sử dụng API**, không phải chương trình hoàn chỉnh.

### Không cần `@Transactional` để TransactionTemplate hoạt động

Với `TransactionTemplate`, transaction boundary được tạo khi code gọi `execute(...)` qua chính template; không phụ thuộc self-invocation của Spring AOP. Ví dụ gọi một helper `private` từ một method public vẫn ổn **nếu helper thực sự gọi template**. Tuy vậy service vẫn cần một transaction manager thích hợp và các truy cập JDBC/JPA phải sử dụng resource được Spring quản lý.

Điều này khác annotation-driven `@Transactional`, vốn thường chỉ được áp khi lời gọi đi qua Spring proxy.

## 3. Vì sao chia một luồng dài thành các transaction ngắn?

| Yếu tố | Một transaction bao toàn luồng | Nhiều transaction ngắn bằng TransactionTemplate |
| --- | --- | --- |
| Connection và locks | Có thể bị giữ suốt chặng chờ mạng/CPU | Mỗi TX có phạm vi ngắn và dọn tài nguyên giữa các chặng |
| Tính nguyên tử | Các SQL trong **cùng physical transaction** commit/rollback cùng nhau | Chỉ **các SQL trong từng chặng** commit/rollback cùng nhau |
| Nếu bước cuối thất bại | Các thay đổi SQL trong transaction rộng có thể rollback | Bước đã commit trước vẫn tồn tại |
| Khả năng phục hồi | Có thể phải chạy lại toàn bộ thao tác | Có thể retry từ checkpoint đã commit |
| Tác vụ ngoài DB | Không tự rollback được | Được để ngoài TX rõ ràng, không tạo cảm giác atomic giả |
| Isolation/timeout | Một scope có thể kéo dài quá lâu | Có thể đặt policy phù hợp cho từng chặng mới |
| Khả năng quan sát | Khó biết đã qua mốc bền vững nào | State machine và operation ID diễn tả tiến độ |
| Độ phức tạp nghiệp vụ | Dễ hiểu nếu tất cả là SQL atomic | Cần xử lý trạng thái trung gian, retry, idempotency, compensation |

**Không phải cứ chia nhỏ là tốt hơn.** Nếu hai lệnh chuyển tiền trong cùng một database phải **cùng commit hoặc cùng rollback**, tách chúng thành hai physical transactions là sai về nguyên tử tài chính. Nếu công việc chỉ gồm vài câu SQL nhanh cần bảo đảm atomicity chung, giữ một transaction là hợp lý.

Hãy tách khi có **ranh giới nghiệp vụ hợp lệ**: một trạng thái trung gian có ý nghĩa và có thể được phục hồi an toàn.

## 4. Mô hình trạng thái trước khi viết transaction

Giả sử một tác vụ có các trạng thái:

~~~text
              TX chuẩn bị
          (idempotent request key)
                  |
                  v
               PREPARED
                  |
       external step thành công
                  |
                  v
              TX hoàn tất
                  |
                  +---- COMMIT ------> DONE
                  |
                  +---- ROLLBACK ----> vẫn PREPARED
                                             |
                                      TX đánh dấu lỗi
                                             |
                                             v
                                            RETRY
                                             |
                                    worker retry an toàn
                                             |
                                             v
                                            DONE
~~~

`PREPARED` **không** nghĩa là nghiệp vụ đã hoàn tất; nó chỉ xác nhận đã ghi checkpoint. `RETRY` biểu thị còn việc phải xử lý; `DONE` chỉ được ghi khi điều kiện nghiệp vụ tương ứng đã được đáp ứng.

Bộ trạng thái ở đây là **mô hình giản lược** để học transaction. Hệ thống production thường cần thêm `PROCESSING`, `FAILED`, `CANCELLED`, mã lỗi, version, timestamps, lease/lock ownership và số lần thử lại.

### Quy tắc thiết kế mốc commit

Một chặng transaction tốt cần trả lời được:

1. **Nó bảo vệ bất biến nào?** Ví dụ “tạo một bản ghi yêu cầu với operation ID duy nhất”.
2. **Sau khi commit, dữ liệu trung gian có hợp lệ không?** `PREPARED` phải là trạng thái mà hệ thống có thể đọc và xử lý.
3. **Nếu chương trình chết ngay sau commit thì sao?** Phải có cơ chế quét/resume các bản ghi chưa DONE.
4. **Nếu callback ném exception trước commit thì sao?** Có thể retry mà không tạo record trùng?
5. **Nếu commit thành công nhưng client mất kết nối chưa nhận được xác nhận thì sao?** Không tự suy rollback; phải kiểm tra trạng thái bằng idempotency key.
6. **Nếu gọi remote thành công nhưng DB update thất bại thì sao?** Phải có cơ chế reconcile/compensation; không giả định rollback DB hoàn tác remote request.
7. **Nếu hai workers xử lý cùng job thì sao?** Cần concurrency control và guarded state transition.

Vì vậy transaction boundary và **ngữ nghĩa trạng thái** phải được thiết kế đồng thời.

## 5. Chọn phạm vi từng template

`TransactionTemplate` triển khai `TransactionDefinition`. Bạn có thể thiết lập propagation, isolation, read-only, timeout và tên transaction ngay lúc khởi tạo.

~~~java
TransactionTemplate prepareTx = new TransactionTemplate(transactionManager);
prepareTx.setName("work-prepare");
prepareTx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
prepareTx.setTimeout(5); // 5 giây, không phải 5 ms.

TransactionTemplate finishTx = new TransactionTemplate(transactionManager);
finishTx.setName("work-finish");
finishTx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
finishTx.setTimeout(5);
~~~

Đây là cấu hình minh họa; bản ví dụ hoàn chỉnh ở mục 7 sử dụng đúng các thuộc tính này. Sau khi đã cấu hình, **không thay đổi cấu hình của một TransactionTemplate shared đang được các threads khác dùng**. Spring ghi nhận template không giữ conversational state nên có thể được chia sẻ, nhưng nó giữ **configuration state**; mỗi policy khác nhau cần một instance template riêng.

### Mặc định `REQUIRED` có một điều kiện sống còn

`TransactionTemplate` mặc định sử dụng propagation `REQUIRED`. Nếu **không có transaction từ caller**, mỗi lần gọi `execute(...)` sẽ bắt đầu và hoàn tất một physical transaction riêng:

~~~text
Caller KHÔNG có transaction:
  prepareTx.execute(...) -> TX-A -> COMMIT
  externalWork()         -> ngoài TX
  finishTx.execute(...)  -> TX-B -> COMMIT/ROLLBACK
~~~

Nhưng nếu caller **đã mở `@Transactional` bao ngoài**, hai template `REQUIRED` có thể **tham gia cùng physical transaction ngoài**:

~~~text
Caller ĐÃ có @Transactional:
  outer TX-X BEGIN
    prepareTx.execute(...) -> JOIN TX-X (chưa commit vật lý)
    externalWork()         -> vẫn nằm trong TX-X!
    finishTx.execute(...)  -> JOIN TX-X
  outer TX-X COMMIT/ROLLBACK
~~~

Trong trường hợp sau, thiết kế **không còn** là ba chặng độc lập! Đây là nguyên nhân thường gặp khi nhóm phát triển tưởng đã tách transaction chỉ bằng việc thêm nhiều lời gọi template.

**Nguyên tắc cho bài demo:** orchestrator **không có `@Transactional` bên ngoài** và được gọi từ `main` khi thread chưa có transaction. Trong production, kiểm tra call graph/test. Nếu thực sự cần tách biệt bất chấp caller có outer transaction, cân nhắc `PROPAGATION_REQUIRES_NEW` và hiểu chi phí/ảnh hưởng về connection pool, locks, visibility.

## 6. Flow đúng: công việc ngoài database nằm giữa hai transaction

Thiết kế ưu tiên:

~~~text
Request
  |
  +-- TX-A [ngắn]: INSERT work_item(id, PREPARED) --> COMMIT
  |
  +-- [KHÔNG CÓ TX]: xử lý file / HTTP API / tính toán lâu
  |
  +-- TX-B [ngắn]: UPDATE work_item(id, DONE) --> COMMIT
  |
  '-- Response

Nếu TX-B lỗi:
  TX-B ROLLBACK (work_item vẫn PREPARED)
  TX-C [ngắn]: UPDATE work_item(id, RETRY) --> COMMIT
  ghi nhận alert/retry theo policy
~~~

**Tại sao đây là “chia một luồng” chứ không chỉ là nhiều câu SQL?** Vì mỗi dấu `COMMIT` là một **mốc bền vững rõ**. Công việc tiếp theo không cần giữ transaction trước đó. Quy trình có thể được resume từ database state, thay vì trông chờ một transaction mở suốt vòng đời request.

Ví dụ rollback trong TX-B:

~~~text
TX-A: INSERT id=102, state=PREPARED       -> COMMIT
        |
        v
External step                              -> SUCCESS
        |
        v
TX-B: UPDATE id=102, state=DONE
      throw IllegalStateException          -> ROLLBACK TX-B
        |
        v
Database vẫn: id=102, state=PREPARED
        |
        v
TX-C: UPDATE id=102, state=RETRY          -> COMMIT
~~~

**Đánh đổi:** remote step có thể đã thành công, trong khi DB cần retry/reconcile. `RETRY` không nhất thiết có nghĩa **gọi lại remote nguyên xi**; worker phải kiểm tra external operation ID hoặc cơ chế idempotency trước khi lặp tác dụng phụ.

## 7. Demo Java 17+ chạy được với Spring Framework, JDBC và H2

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.5**, **H2 2.2.224** và Maven. Không sử dụng Spring Boot, không cần một database server bên ngoài.

Điểm quan trọng:

- `prepareTx`, `finishTx` và `recoveryTx` được khởi tạo một lần với cùng một `PlatformTransactionManager`.
- `FlowRunner.runJob(...)` **không** có `@Transactional`; chính mỗi `TransactionTemplate` tạo transaction boundary.
- Công việc mô phỏng remote nằm **ngoài** template; ví dụ không thực hiện HTTP thật để stdout ổn định.
- Hai job được chạy: job 101 thành công; job 102 bị lỗi **sau lệnh UPDATE trong TX-B**.
- Sau lỗi TX-B, truy vấn trực tiếp từ ngoài transaction chứng minh row 102 vẫn `PREPARED`; tiếp đó TX-C chuyển sang `RETRY`.
- Không có sleep, HTTP hay side effect không thể tái tạo trong mã demo.

### 7.1. Cấu trúc thư mục

~~~text
transaction-template-stages/
  pom.xml
  src/main/java/demo/StageTransactionsDemo.java
~~~

### 7.2. Tạo `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-template-stages</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` cung cấp `ApplicationContext` và JavaConfig; `spring-jdbc` cung cấp `JdbcTemplate` cùng JDBC transaction manager; `spring-tx` cung cấp `TransactionTemplate`/`TransactionDefinition`. H2 là database trong bộ nhớ. Các phiên bản được cố định nhằm dễ lặp lại ví dụ.

### 7.3. Tạo `src/main/java/demo/StageTransactionsDemo.java`

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class StageTransactionsDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            FlowRunner runner = context.getBean(FlowRunner.class);

            jdbc.execute("""
                CREATE TABLE work_item (
                    id INT PRIMARY KEY,
                    state VARCHAR(24) NOT NULL
                )
                """);

            runner.runJob(101, false);
            runner.runJob(102, true);

            System.out.println("FINAL 101=" + runner.readState(101)
                    + " 102=" + runner.readState(102));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:stage_demo;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public FlowRunner flowRunner(
                JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new FlowRunner(jdbc, manager);
        }
    }

    public static class FlowRunner {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate prepareTx;
        private final TransactionTemplate finishTx;
        private final TransactionTemplate recoveryTx;

        public FlowRunner(JdbcTemplate jdbc, PlatformTransactionManager manager) {
            this.jdbc = jdbc;
            this.prepareTx = configured(manager, "prepare-stage");
            this.finishTx = configured(manager, "finish-stage");
            this.recoveryTx = configured(manager, "recovery-stage");
        }

        private static TransactionTemplate configured(
                PlatformTransactionManager manager, String name) {
            var template = new TransactionTemplate(manager);
            template.setName(name);
            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);
            template.setTimeout(5); // Mỗi transaction mới tối đa 5 giây.
            return template;
        }

        public void runJob(int jobId, boolean failFinalization) {
            // TX-A: ghi checkpoint. Khi executeWithoutResult trả về
            // bình thường và không có outer TX, TX-A đã được commit.
            prepareTx.executeWithoutResult(status -> {
                System.out.println("prepare.tx=" + active());
                jdbc.update(
                        "INSERT INTO work_item (id, state) VALUES (?, ?)",
                        jobId, "PREPARED");
            });

            System.out.println("after_prepare[" + jobId + "]="
                    + readState(jobId));

            // KHÔNG ở trong template nào: không giữ DB transaction.
            simulateExternalStep(jobId);

            try {
                // TX-B: cập nhật kết quả.
                finishTx.executeWithoutResult(status -> {
                    System.out.println("finish.tx=" + active());
                    int changed = jdbc.update(
                        "UPDATE work_item SET state = ? "
                        + "WHERE id = ? AND state = ?",
                        "DONE", jobId, "PREPARED");

                    if (changed != 1) {
                        throw new IllegalStateException("invalid state");
                    }

                    if (failFinalization) {
                        throw new IllegalStateException("simulated finish error");
                    }
                });

                System.out.println("after_finish[" + jobId + "]="
                        + readState(jobId));
            } catch (IllegalStateException ex) {
                // Exception thoát khỏi callback: TX-B đã rollback.
                System.out.println("finish.error[" + jobId + "]="
                        + ex.getMessage());
                System.out.println("after_rollback[" + jobId + "]="
                        + readState(jobId));

                // TX-C độc lập sau khi TX-B đã kết thúc.
                recoveryTx.executeWithoutResult(status -> {
                    System.out.println("recovery.tx=" + active());
                    int changed = jdbc.update(
                        "UPDATE work_item SET state = ? "
                        + "WHERE id = ? AND state = ?",
                        "RETRY", jobId, "PREPARED");

                    if (changed != 1) {
                        throw new IllegalStateException("recovery conflict");
                    }
                });

                System.out.println("after_recovery[" + jobId + "]="
                        + readState(jobId));
            }
        }

        private void simulateExternalStep(int jobId) {
            System.out.println("external[" + jobId + "].tx=" + active());
            // Thực tế có thể gọi HTTP hoặc xử lý file.
            // Bài demo không thực hiện tác dụng phụ bên ngoài.
        }

        public String readState(int jobId) {
            return jdbc.queryForObject(
                    "SELECT state FROM work_item WHERE id = ?",
                    String.class, jobId);
        }

        private static boolean active() {
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        }
    }
}
~~~

### 7.4. Vì sao đoạn code tạo ra ba transaction rõ ràng?

`StageTransactionsDemo.main(...)` lấy bean từ context nhưng **không nằm trong `@Transactional`**. `FlowRunner.runJob(...)` cũng không có outer transaction. Vì thế ba `TransactionTemplate` mặc định `PROPAGATION_REQUIRED` lần lượt mở physical transactions riêng khi được gọi:

- `prepareTx.executeWithoutResult(...)` → TX-A mới; commit trước khi chạy công việc ngoài.
- `simulateExternalStep(...)` → chạy khi không có actual transaction của Spring trên thread.
- `finishTx.executeWithoutResult(...)` → TX-B mới; commit hoặc rollback; khi ném unchecked exception, lỗi đi ra caller sau khi template xử lý rollback.
- `recoveryTx.executeWithoutResult(...)` → TX-C mới, chỉ được gọi sau khi TX-B đã thất bại và kết thúc.

**Không cần `@EnableTransactionManagement` trong ví dụ này**, vì ta không sử dụng declarative transaction advice; chính template gọi `PlatformTransactionManager`. Spring vẫn phải tạo đúng `DataSource`/`JdbcTransactionManager` để `JdbcTemplate` sử dụng cùng JDBC resource.

### 7.5. Lệnh chạy

Ở thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StageTransactionsDemo
~~~

Các dòng do `System.out` của chương trình in ra, bỏ qua thông báo Maven/driver/framework:

~~~text
prepare.tx=true
after_prepare[101]=PREPARED
external[101].tx=false
finish.tx=true
after_finish[101]=DONE
prepare.tx=true
after_prepare[102]=PREPARED
external[102].tx=false
finish.tx=true
finish.error[102]=simulated finish error
after_rollback[102]=PREPARED
recovery.tx=true
after_recovery[102]=RETRY
FINAL 101=DONE 102=RETRY
~~~

### 7.6. Đọc kết quả từng dòng

**Job 101 — đường thành công**

1. `prepare.tx=true`: template thứ nhất đã mở transaction.
2. Callback chèn row 101 ở trạng thái `PREPARED`; template commit khi callback hoàn tất.
3. `after_prepare[101]=PREPARED`: một truy vấn ở ngoài transaction quan sát checkpoint đã lưu.
4. `external[101].tx=false`: luồng xử lý ngoài không còn giữ transaction JDBC từ bước chuẩn bị.
5. `finish.tx=true`: template thứ hai mở transaction mới, đổi `PREPARED -> DONE`.
6. `after_finish[101]=DONE`: transaction thứ hai đã hoàn tất và kết quả đã được quan sát từ ngoài scope.

**Job 102 — bước hoàn tất thất bại**

1. TX-A chèn row 102 và commit checkpoint `PREPARED`.
2. Remote step giả lập chạy khi `tx=false`.
3. TX-B đổi tạm thời `PREPARED -> DONE` nhưng sau đó ném `IllegalStateException`.
4. TransactionTemplate rollback **cả thay đổi của TX-B**. `after_rollback[102]=PREPARED` chứng minh trạng thái đã lưu từ TX-A không bị mất.
5. TX-C đánh dấu `RETRY` trong transaction riêng, commit, và `after_recovery[102]=RETRY`.
6. Cuối cùng DB có job 101 `DONE` và job 102 `RETRY`.

**Điều cần hiểu chính xác:** job 102 không trở lại trạng thái “chưa từng có yêu cầu”. TX-A đã commit nên checkpoint bền vững còn nguyên. Đây **chính là đánh đổi** để có thể phục hồi theo chặng.

## 8. Chia chặng đúng không có nghĩa bọc mọi hàm bằng template

Một lỗi thường gặp là:

~~~java
template.executeWithoutResult(status -> {
    createCheckpoint();
    callRemoteService(); // Sai mục tiêu tách transaction!
    finalizeRecord();
});
~~~

Dù đã dùng `TransactionTemplate`, **toàn bộ callback vẫn nằm trong một transaction**. Việc đổi từ `@Transactional` sang template không tự khiến transaction ngắn đi.

Tương tự, ví dụ sau vẫn có outer transaction nếu method chứa nó đang `@Transactional`:

~~~java
@Transactional
public void outer() {
    template.executeWithoutResult(status -> saveCheckpoint());
    doSlowWork();
    template.executeWithoutResult(status -> finalizeData());
}
~~~

Nếu `template` dùng `PROPAGATION_REQUIRED`, các callback có thể chỉ **join outer**, nên không tạo hai commit độc lập. Khi muốn chặng thật sự tách khỏi outer, cần bỏ outer boundary hoặc thiết kế lại call graph. `REQUIRES_NEW` có thể dùng khi có lý do rõ, nhưng tạm treo outer không giải phóng tất cả locks/resources và có thể tốn thêm connection.

**Thực hành tốt:** hãy vẽ timeline gồm `BEGIN -> SQL -> COMMIT/ROLLBACK -> external work` và viết test chứng minh trạng thái DB **sau mỗi boundary**, thay vì chỉ đọc log `isActualTransactionActive()`.

## 9. Phân biệt throw exception, bắt exception và setRollbackOnly

`TransactionTemplate` không có `rollbackFor` như `@Transactional`. Callback nhận `TransactionStatus` và có thể đưa ra quyết định rollback bằng hai cách chính:

### 9.1. Để unchecked exception thoát khỏi callback

~~~java
template.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "UPDATE work_item SET state = ? WHERE id = ?",
        "DONE", 102);
    throw new IllegalStateException("cannot finalize");
});
~~~

Đây là ví dụ minh họa. Spring sẽ rollback transaction của callback theo semantics của manager và **rethrow unchecked exception**. Caller có thể bắt lỗi **bên ngoài `executeWithoutResult`**, lúc transaction template đã xử lý sự kiện rollback tương ứng.

Nếu transaction template **tham gia outer transaction**, việc rollback có thể là đánh dấu outer rollback-only, không phải rollback vật lý ngay. Đừng rút ra kết luận độc lập nếu chưa biết propagation.

### 9.2. Bắt lỗi bên trong callback và chủ động đánh dấu rollback-only

~~~java
boolean accepted = template.execute(status -> {
    try {
        performBusinessValidationAndWrites();
        return true;
    } catch (ExpectedBusinessException ex) {
        status.setRollbackOnly();
        return false;
    }
});
~~~

Đây là **mảnh minh họa**, chưa định nghĩa các method và exception. Với transaction mới do template sở hữu, `status.setRollbackOnly()` khiến phạm vi được xử lý rollback khi callback trả về. Caller vẫn có thể nhận kết quả `false` thay vì exception; cần thiết kế contract rõ ràng.

Nếu callback **bắt lỗi rồi return bình thường mà không đánh dấu rollback-only**, transaction có thể được commit, miễn manager/DB chưa đánh dấu rollback-only vì lý do khác. Đây là nguồn gây sai dữ liệu khi nhóm viết `catch (Exception e) { log(e); }` ngay trong callback.

### 9.3. Checked exception và việc chuyển thành failure phù hợp

`TransactionCallback` không khai báo checked exception tùy ý. Khi gọi API có `IOException`, bạn có thể bắt checked exception **trong callback**, đánh dấu rollback-only, và trả kết quả có cấu trúc; hoặc chuyển thành một unchecked exception nghiệp vụ có ý nghĩa và để nó đi ra ngoài callback.

~~~java
template.executeWithoutResult(status -> {
    try {
        importOneSmallChunk();
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("chunk import failed", ex);
    }
});
~~~

**Mảnh minh họa**, method `importOneSmallChunk` phải được định nghĩa. Đừng hiểu nhầm “checked exception mặc định sẽ commit” trong `TransactionTemplate` giống hoàn toàn Spring declarative rollback rules: API programmatic dùng callback và cơ chế điều khiển lỗi khác, nên phải quyết định rõ xử lý checked exception.

### 9.4. Khi dùng nhiều template liên tiếp

Nếu callback TX-B ném exception, lỗi **không tự rollback TX-A đã commit**. Nếu callback TX-C phục hồi lại ném exception, TX-C có thể rollback, nhưng TX-A vẫn còn. Vì vậy tầng orchestration cần bảo đảm phát cảnh báo hoặc một worker đủ sức retry khi chính thao tác ghi trạng thái phục hồi thất bại.

## 10. Mỗi chặng có timeout, isolation và read-only riêng

Có thể tạo nhiều `TransactionTemplate` với cấu hình khác nhau:

~~~java
TransactionTemplate readTx = new TransactionTemplate(manager);
readTx.setReadOnly(true);
readTx.setTimeout(3); // 3 giây.

TransactionTemplate writeTx = new TransactionTemplate(manager);
writeTx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
writeTx.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
writeTx.setTimeout(5); // 5 giây.
~~~

Đây là **đoạn cấu hình minh họa**. Những thuộc tính này chủ yếu áp cho transaction **mới được tạo**. Nếu `REQUIRED` chỉ tham gia một outer transaction, isolation/timeout/read-only ở template trong không nhất thiết thay đổi physical transaction đã có.

**Timeout** không phải một Java thread timer luôn interrupt chính xác tại thời điểm hết hạn. Nó được transaction manager/driver áp theo cơ chế hỗ trợ. Nếu bước ngoài transaction có timeout HTTP riêng, cần cấu hình timeout của HTTP client **tách biệt**, không trông chờ transaction timeout bảo vệ chặng external.

**Read-only** là gợi ý cho transaction manager/driver/ORM, không phải quy tắc bảo mật chắc chắn cấm mọi DML. Chỉ khai báo read-only cho chặng thuần đọc.

### Thay `REQUIRED` bằng `REQUIRES_NEW` có phù hợp không?

~~~java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

Nếu caller đang có transaction, `REQUIRES_NEW` sẽ yêu cầu một physical transaction độc lập. Điều này có thể bảo đảm một chặng thật sự commit trước khi outer hoàn tất, nhưng kéo theo **partial commit**, khả năng cần connection thứ hai, lock contention và visibility của dữ liệu chưa commit.

**Ưu tiên thiết kế orchestrator không có outer transaction** khi mục tiêu chỉ là tách luồng dài. Dùng `REQUIRES_NEW` có chủ ý khi chặng phải độc lập ngay cả trong một outer transaction mà bạn kiểm soát được hệ quả.

## 11. External API không tham gia rollback của DB

Giả sử một chặng giao tiếp payment gateway:

~~~text
TX-A ghi PREPARED        -> COMMIT DB
Remote charge            -> SUCCESS bên ngoài DB
TX-B ghi CHARGED         -> COMMIT hoặc ROLLBACK DB
~~~

Nếu remote charge thành công nhưng TX-B rollback hoặc process chết, **DB chưa phản ánh kết quả thanh toán**, còn remote system đã thực hiện charge. Không có cách dùng `TransactionTemplate` thuần túy để rollback remote charge như rollback JDBC row.

Những cơ chế cần cân nhắc:

- **Idempotency key:** dùng cùng operation ID cho mọi lần retry, để remote provider không tạo charge trùng.
- **Reconciliation:** sau restart, hỏi remote system kết quả theo operation ID trước khi gọi lại.
- **Compensating action:** có thể gửi refund/cancel nếu quy tắc nghiệp vụ cho phép, nhưng compensation cũng có thể thất bại và phải được theo dõi.
- **Timeout/retry policy:** biết rõ lỗi “chưa thực hiện” khác lỗi “không rõ đã thực hiện hay chưa”.
- **Durable workflow state:** lưu checkpoint và trạng thái cần xử lý trong DB; không chỉ giữ một biến boolean trong RAM.

Sơ đồ state machine cần phân biệt “chưa gửi”, “đã gửi nhưng chưa rõ kết quả”, “remote đã xác nhận”, “DB đã xác nhận”. Một cột `RETRY` đơn giản như demo **không đủ** để vận hành payment thực; demo chỉ minh họa ranh giới transaction.

## 12. Transactional outbox: khi cần chuyển sự kiện sau commit

Một mẫu thường dùng:

~~~text
TX-A:
  INSERT business row (PREPARED)
  INSERT outbox event (PROCESS_WORK_ITEM)
COMMIT

Outbox publisher:
  đọc event đã commit
  gửi message/queue
  retry với event ID ổn định

Worker:
  xử lý external task
  TX-B ghi DONE hoặc trạng thái phục hồi
~~~

Vì business row và outbox event được ghi trong **cùng physical transaction**, không xảy ra trạng thái “business row commit nhưng ý định publish chưa được ghi”. Tuy vậy **gửi message** vẫn diễn ra sau commit và có thể bị lặp; consumer nên idempotent.

Nếu chỉ `publishMessage()` ngay trong callback của TX-A, message có thể đã ra broker trước lúc DB commit và không thể được transaction manager của JDBC rollback. Nếu chỉ publish bằng callback in-memory `afterCommit`, process chết sau DB commit có thể làm mất hành động publish. Outbox giải quyết **độ bền của ý định phát sự kiện**, không tạo distributed atomic commit với broker.

Đây là kiến trúc bổ sung cho bài TransactionTemplate, không phải một đặc tính tự động của `TransactionTemplate`.

## 13. Giảm thời gian giữ connection và lock một cách đúng nghĩa

Transaction ngắn thường giúp giảm thời gian giữ connection/locks, nhưng cần kiểm tra **nơi đang thực sự giữ resources**:

- Với `JdbcTransactionManager`, connection thường được Spring bind vào thread trong transaction, sau đó được dọn khi transaction hoàn tất.
- Nếu một outer transaction bao trùm cả orchestrator, các `REQUIRED` templates không làm connection/lock được giải phóng giữa các chặng.
- Một operation chậm **ngay trong callback** vẫn giữ transaction mở; tách code thành helper functions không tự rút ngắn transaction.
- Một callback chỉ đọc nhưng quét hàng triệu rows cũng có thể giữ tài nguyên lâu; dùng pagination/chunking thích hợp.
- Query isolation, pessimistic locking, `SELECT ... FOR UPDATE`, indexing và DB execution plan có ảnh hưởng lớn đến lock duration.
- Dùng `REQUIRES_NEW` bên trong outer có thể phải mượn connection thứ hai, khiến pool **cạn nhanh hơn**, thay vì giúp giải phóng connection của outer.
- Một transaction ngắn nhưng bị commit chậm vì DB/network cũng có thể gây contention.

**Không đoán hiệu năng.** Hãy quan sát connection pool wait time, active connections, transaction duration, lock waits, query latency, deadlocks, DB logs và p95/p99 throughput.

## 14. Retry, idempotency và concurrency

### 14.1. Vì sao retry phải nhìn trạng thái đã commit?

Job 102 trong demo còn `RETRY`. Một worker sau đó nên đọc state bằng transaction đọc ngắn, kiểm tra operation ID và **cố gắng claim job** theo cách an toàn trước khi làm lại.

Ví dụ câu SQL có điều kiện:

~~~sql
UPDATE work_item
SET state = 'PROCESSING'
WHERE id = 102 AND state = 'RETRY';
~~~

Đoạn SQL chỉ minh họa. Giá trị số hàng bị cập nhật phải được kiểm tra: `1` nghĩa là worker đã claim thành công theo điều kiện; `0` nghĩa là worker khác đã claim, hoặc state đã thay đổi. Hệ thống lớn có thể cần version column/optimistic locking, lease timestamp và cơ chế xử lý worker chết khi đang giữ `PROCESSING`.

**Không làm**:

~~~java
if ("RETRY".equals(readState(id))) {
    // Một worker khác có thể thay đổi state giữa read và update.
    executeAgainWithoutClaim(id);
}
~~~

Đây là anti-pattern minh họa. Read-then-act tách rời mà không có concurrency control có thể tạo double execution.

### 14.2. Chống tạo checkpoint trùng

Trong demo, `INSERT` sẽ bị lỗi duplicate key nếu gọi lại jobId cũ; đây là tính năng của primary key giúp lộ bug. Trong production, cần một **idempotency key** duy nhất và logic khi key đã tồn tại:

- Nếu `DONE`: trả lại kết quả đã hoàn thành.
- Nếu `PREPARED/PROCESSING`: không tạo job mới; chờ/kiểm tra trạng thái.
- Nếu `RETRY`: claim an toàn và thực hiện đúng quy trình resume.
- Nếu `FAILED` hoặc outcome không rõ: theo chính sách xác minh, không tự động bỏ qua.

Một request “create” bị mất response sau commit **có thể** đã tạo job. Nếu client gửi lại, hãy truy vấn bằng idempotency key trước khi quyết định insert tiếp.

### 14.3. Retry chặng thất bại, không nhất thiết chạy lại từ đầu

Nếu `PREPARED` đã commit và remote step đã có outcome bền vững, việc chạy lại từ bước đầu có thể bị duplicate. Thiết kế nên **resume từ checkpoint** với những transition phù hợp và xác minh external result.

Có thể giới hạn retry count, áp exponential backoff, dead-letter queue và cảnh báo. Những policy này thuộc **workflow orchestration**, không được `TransactionTemplate` tự cung cấp.

### 14.4. Transactional state transition dùng điều kiện

Trong mã demo, `UPDATE ... WHERE id = ? AND state = 'PREPARED'` được kiểm tra số rows là **1**. Đây là guard tránh ghi đè tùy tiện trạng thái ngoài mong đợi, nhưng chưa phải giải pháp concurrency hoàn chỉnh nếu các bước khác như remote call có thể chạy song song.

Một hệ thống production nên thiết kế state machine mà **mọi writer** tuân thủ, không cho một method đổi `DONE` thành `RETRY` do exception đến trễ.

## 15. Các thời điểm crash có thể xảy ra

Chia transaction thành các chặng giúp biết **đã commit gì**, nhưng tạo thêm các khoảng hở giữa chặng. Hãy kiểm tra từng điểm:

| Thời điểm sự cố | Dữ liệu DB có thể còn | Hướng phục hồi |
| --- | --- | --- |
| Trong TX-A trước commit | Job chưa được ghi | Caller có thể retry create với idempotency key |
| Ngay sau commit TX-A | `PREPARED` | Worker quét các checkpoint chưa xử lý |
| Trong remote call ngoài TX | `PREPARED`, remote outcome chưa rõ | Tra cứu remote theo operation ID, không gọi lại mù quáng |
| Remote thành công, trước TX-B | `PREPARED` | Reconcile remote outcome rồi hoàn tất DB state |
| Trong TX-B sau UPDATE, trước commit | DB có thể rollback về `PREPARED` | Query trạng thái sau exception, retry/compensate |
| TX-B commit nhưng response bị mất | Có thể đã `DONE` | Đọc lại DB theo operation ID, tránh duplicate |
| Trong TX-C ghi `RETRY` | Có thể vẫn `PREPARED` | Scanner phải xử lý cả PREPARED quá hạn |
| Process chết sau `RETRY` | `RETRY` bền vững | Worker claim/retry có kiểm soát |

**Không nên tin rằng mọi exception từ `execute(...)` đồng nghĩa DB chắc chắn rollback thành công.** Có loại lỗi tại thời điểm commit mà outcome phía database chưa xác định chắc chắn từ góc nhìn client. Sau lỗi commit không rõ kết quả, phải kiểm tra hoặc reconcile trạng thái bằng key ổn định.

## 16. So sánh TransactionTemplate và `@Transactional` khi chia luồng

| Tình huống | TransactionTemplate | `@Transactional` |
| --- | --- | --- |
| Một service method có một transaction rõ ràng | Dùng được nhưng có thêm code | Thường gọn và dễ đọc |
| Một method dài cần **nhiều ranh giới TX ngắn trong cùng luồng** | **Rất phù hợp**: bao từng callback | Cần tách bean/method và proxy call graph đúng |
| Muốn bắt lỗi giữa các transaction và đánh dấu trạng thái phục hồi | Rõ ràng với `try/catch` **ngoài** callback | Có thể làm bằng service riêng, nhưng dễ nhầm self-invocation |
| Muốn thay propagation/timeout cho từng chặng | Mỗi template có cấu hình riêng | Từng method có annotation riêng |
| Muốn tránh self-invocation proxy pitfall | Callback template được gọi trực tiếp, không cần AOP interceptor | Phải bảo đảm lời gọi đi qua proxy |
| Muốn đặt transaction trong reactive pipeline | Không phù hợp cho reactive stream | Có reactive `@Transactional` hoặc `TransactionalOperator` |
| Muốn policy rollback theo nhiều loại checked exception | Chủ động xử lý/cấu trúc callback, `setRollbackOnly` | `rollbackFor`/`noRollbackFor` thuận tiện |
| Muốn test ranh giới chính xác | Dễ mock `TransactionOperations`, integration test actual DB | Integration test qua proxy |

**Khuyến nghị:** kết hợp hai cơ chế có chọn lọc. Dùng `@Transactional` cho các đơn vị service ngắn; dùng `TransactionTemplate` khi orchestration thật sự cần kiểm soát BEGIN/COMMIT/ROLLBACK **ở nhiều vị trí trong một luồng**. Không trộn hai tầng vô thức để tạo nested/participating transactions khó dự đoán.

### Khi nào nên dùng `TransactionOperations`?

`TransactionOperations` là interface của `TransactionTemplate`, có thể inject để dễ test. Khi service chỉ cần `execute(...)`/`executeWithoutResult(...)` mà không cần thay đổi template settings, lập trình hướng interface giúp mock/fake thuận tiện hơn.

Ví dụ:

~~~java
public class ReportService {
    private final TransactionOperations transactions;

    public ReportService(TransactionOperations transactions) {
        this.transactions = transactions;
    }

    public void rebuild() {
        transactions.executeWithoutResult(status -> rebuildOnePart());
    }
}
~~~

Đây là mẫu minh họa chưa có implementation `rebuildOnePart`. Trong ứng dụng thật, phải bảo đảm instance `TransactionOperations` được cung cấp có propagation/isolation/timeout phù hợp với ranh giới mong muốn.

## 17. Testing: kiểm tra trạng thái sau từng commit

Integration test cho transaction stages cần xác nhận **DB state sau khi template trả về**, không chỉ số lần callback được gọi.

Các case cần bao phủ:

1. **Toàn bộ thành công:** `PREPARED` sau TX-A, `DONE` sau TX-B.
2. **TX-A ném unchecked exception:** không có job row mới.
3. **External step lỗi:** TX-A còn `PREPARED`; một bước xử lý lỗi ghi trạng thái thích hợp, không giữ transaction DB khi gọi remote.
4. **TX-B update xong rồi ném exception:** rollback về `PREPARED`, không phải DONE.
5. **TX-C thành công:** `PREPARED -> RETRY` được commit trong transaction mới.
6. **TX-C cũng lỗi:** cần retry từ scanner hoặc báo động; checkpoint TX-A vẫn còn.
7. **Duplicate jobId/idempotency key:** không tạo trùng job hoặc duplicate remote side effect.
8. **Concurrent workers:** chỉ một worker claim được job thông qua guarded update/lock/lease.
9. **Caller bên ngoài vô tình có `@Transactional`:** test phát hiện hai template REQUIRED đang join outer và mất tính độc lập.
10. **Commit outcome không rõ:** đọc/reconcile bằng operation ID, không giả định cứ exception là chưa commit.

### Cẩn thận với `@Transactional` trên test method

Spring TestContext có thể bắt đầu một transaction ngoài cho `@Transactional` test và rollback lúc test kết thúc. Khi ấy các `TransactionTemplate` propagation `REQUIRED` của bạn **tham gia transaction test**, làm sai mục đích kiểm chứng các commit độc lập.

Với integration test xác minh boundary, **không** bọc test trong outer transaction mặc định; hoặc chủ động quản lý `TestTransaction`/kết thúc test transaction. Đọc DB sau mỗi boundary với context thực tế cần kiểm thử.

### Quan sát transaction thực tế

Trong debug, có thể in:

~~~java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

boolean sync =
        TransactionSynchronizationManager.isSynchronizationActive();
~~~

Đây là đoạn API minh họa. `active=true` cho biết một transaction Spring đang hoạt động trên thread; **không chứng minh** nó là transaction mới, cũng không chứng minh commit thành công. `sync=true` có thể xuất hiện ngay cả khi không có actual transaction.

Để đo tài nguyên, có thể bật logger `org.springframework.transaction` ở môi trường thử nghiệm và quan sát connection pool; không bật trace nhạy cảm hoặc log SQL bind parameters tùy tiện trên production.

## 18. Các lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng một template bao cả luồng dài | Transaction vẫn giữ connection/lock trong lúc gọi mạng | Đặt mỗi đoạn DB nhỏ trong một execute riêng |
| Tách code thành nhiều methods nhưng giữ outer `@Transactional` | Template REQUIRED join outer, không tạo commit độc lập | Bỏ outer boundary hoặc thiết kế propagation có chủ ý |
| Nghĩ mỗi lần gọi template luôn tạo TX mới | REQUIRED chỉ mở mới nếu chưa có outer | Xác định caller context và transaction definition |
| Cho HTTP call bên trong TX rồi nghĩ rollback được HTTP | External side effect không tham gia JDBC rollback | Gọi ngoài TX, idempotency và compensation |
| Nghĩ TX-B rollback sẽ rollback TX-A đã commit | Partial commit là hệ quả của tách chặng | Lưu checkpoint/recovery state |
| Catch lỗi **trong** callback rồi nuốt | Callback bình thường có thể dẫn đến commit | Rethrow unchecked hoặc `status.setRollbackOnly()` |
| Coi `setRollbackOnly()` tương đương exception bắt buộc | Callback có thể return bình thường; caller phải hiểu outcome | Trả result có cấu trúc/throw có chủ ý |
| Dùng một shared template rồi thay timeout tại runtime | Configuration state bị thay trong khi threads đang dùng | Cấu hình một lần, dùng template khác cho policy khác |
| Nhầm `timeout=5` với 5 milliseconds | Deadline sai | Spring transaction timeout tính bằng giây |
| Dùng `REQUIRES_NEW` để chữa mọi outer transaction | Có thể cạn connection pool và phá atomicity | Chỉ dùng khi ranh giới độc lập là ý định |
| Retry remote ngay sau timeout mơ hồ | Có thể double-charge/double-create | Dùng operation ID và reconcile |
| Chạy lại checkpoint bằng INSERT không idempotent | Duplicate key hoặc duplicate operation | Unique key + resume state machine |
| Cho hai workers cùng làm trên một job | Race condition, double effect | Guarded UPDATE/optimistic locking/lease |
| Ghi DONE trước khi xác minh remote outcome | DB nói thành công giả | Chọn đúng trạng thái và bước xác nhận |
| Dựa vào `isActualTransactionActive()` để kết luận commit | Flag chỉ nói trạng thái đang hoạt động | Query sau boundary và dùng commit callbacks đúng |
| Test được bọc `@Transactional` rồi tưởng template commit thật | Template REQUIRED join outer test transaction | Kiểm thử ngoài transaction test hoặc quản lý kết thúc rõ |
| Dùng `TransactionTemplate` cho reactive pipeline | Imperative thread-bound API không bao reactive context | Dùng `TransactionalOperator` và reactive manager |

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Một luồng gồm `createCheckpoint()`, HTTP call 10 giây, `finish()`. Vì sao không nên mặc định đặt `@Transactional` trên toàn bộ?

**Đáp án:** DB transaction có thể giữ connection/locks suốt HTTP call, trong khi HTTP side effect không rollback được theo JDBC. Nếu nghiệp vụ cho phép trạng thái trung gian, tách TX ngắn giúp giảm thời gian giữ tài nguyên và phục hồi từ checkpoint.

**Câu 2.** `TransactionTemplate.executeWithoutResult(...)` được gọi hai lần liên tiếp khi caller **không có transaction** và propagation REQUIRED. Có mấy physical transaction?

**Đáp án:** Thông thường hai transaction riêng, mỗi lần template mở rồi hoàn tất một boundary; không có outer bao lại.

**Câu 3.** Nếu caller được thêm `@Transactional` và hai template vẫn REQUIRED, còn hai commit độc lập không?

**Đáp án:** Không thể kết luận độc lập; chúng có thể cùng join một physical transaction của outer. Muốn tách phải sửa architecture hoặc propagation.

**Câu 4.** TX-A commit `PREPARED`, TX-B cập nhật `DONE` rồi ném unchecked exception. DB cuối là gì trước phục hồi?

**Đáp án:** `PREPARED`: TX-B rollback cập nhật của nó, TX-A đã commit không bị hoàn tác.

**Câu 5.** Remote payment thành công nhưng TX-B bị rollback. Có được gọi lại payment ngay bằng request mới không?

**Đáp án:** Không nên. Cần tra cứu outcome bằng operation/idempotency key, tránh double-charge; có thể reconcile rồi chỉ cập nhật DB.

**Câu 6.** Trong callback có `catch (Exception ex) { log(ex); }`, sau đó return bình thường. Spring luôn rollback không?

**Đáp án:** Không. Nếu không set rollback-only hoặc ném lỗi và manager/DB chưa có tình trạng rollback-only khác, template có thể cố commit.

**Câu 7.** Một template được dùng bởi nhiều service. Có thể đổi `setTimeout(...)` liên tục theo request không?

**Đáp án:** Không nên thay shared configuration trong khi sử dụng; tạo các template riêng cho những policy khác nhau, hoặc tổ chức cấu hình ổn định.

**Câu 8.** Khi retry chặng đã commit một phần, tại sao cần unique operation ID?

**Đáp án:** Request/commit response có thể bị mất; nếu không có ID ổn định, chạy lại có thể tạo job/side effect trùng. ID giúp tra cứu trạng thái, claim an toàn và idempotent remote calls.

**Câu 9.** Dùng `@Transactional` trên test method thì có thể kiểm tra đúng hai transaction độc lập với template REQUIRED không?

**Đáp án:** Không mặc định: outer test transaction có thể khiến cả hai template tham gia và bị rollback khi test kết thúc. Cần test boundary trong hoàn cảnh không có outer transaction tương ứng.

**Câu 10.** Nếu TX-C ghi `RETRY` cũng thất bại, TX-A đã commit có biến mất không?

**Đáp án:** Không. TX-A vẫn giữ `PREPARED`. Cần scanner/reconciliation và cảnh báo để nhận lại những job không hoàn tất.

## Ghi nhớ

- **TransactionTemplate giúp đặt ranh giới giao dịch một cách tường minh trong code imperative**, với `execute(...)` hoặc `executeWithoutResult(...)` và một `PlatformTransactionManager`.
- **Để chia luồng dài:** đặt các thao tác DB ngắn trong template riêng; đặt HTTP, file/CPU work ngoài transaction; ghi checkpoint có ý nghĩa, không chỉ đổi tên methods.
- **Mặc định REQUIRED không phải luôn độc lập:** chỉ khi không có outer transaction, mỗi execute mới tạo physical transaction riêng.
- **Commit của TX trước không bị rollback bởi TX sau.** Đây là ưu điểm để resume nhưng là đánh đổi atomicity; cần state machine, retry, idempotency, compensation/reconciliation.
- **Unchecked exception thoát khỏi callback thường kích hoạt rollback**; nếu bắt lỗi trong callback, dùng `TransactionStatus.setRollbackOnly()` khi muốn rollback.
- **TransactionTemplate không làm remote API atomic với DB**; outbox, idempotency và compensating actions giải quyết phần kiến trúc ngoài DB.
- **Luôn kiểm thử sau ranh giới commit/rollback thực tế**, nhất là khi có outer `@Transactional`, test transaction, nhiều transaction managers hoặc commit outcome chưa rõ.

## Tài liệu tham khảo chính thức

1. Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): sử dụng `TransactionTemplate`, callback, rollback-only và các thuộc tính transaction.
2. Spring Framework — [`TransactionTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): API, configuration state và thread safety.
3. Spring Framework — [`TransactionOperations` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html): `execute` và `executeWithoutResult`.
4. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED` và `REQUIRES_NEW`, physical vs logical transactions, connection pool.
5. Spring Framework — [Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptors và method boundary.
6. Spring Framework — [TransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html): propagation, isolation, read-only và timeout semantics.
7. Spring Framework — [`JdbcTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): JDBC transaction manager dùng trong demo.
