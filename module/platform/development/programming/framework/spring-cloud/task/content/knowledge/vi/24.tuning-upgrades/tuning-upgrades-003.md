# Tối ưu kết nối JDBC cho tác vụ chạy ngắn

**Spring Cloud Task** xây dựng các ứng dụng Spring Boot có vòng đời hữu hạn: khởi động, thực hiện công việc, ghi trạng thái vào **TaskRepository** và thoát. Một Task nhập dữ liệu, kết xuất báo cáo hoặc bảo trì CSDL có thể chỉ chạy vài giây nhưng vẫn phải lấy kết nối JDBC để ghi `TaskExecution`, thao tác dữ liệu nghiệp vụ và, nếu có **Spring Batch**, ghi checkpoint vào `JobRepository`.

Đối với tác vụ ngắn, kết nối JDBC là một chi phí đáng chú ý: khởi tạo pool, bắt tay TLS, xác thực, chờ cấp kết nối và dọn tài nguyên có thể chiếm tỷ lệ đáng kể trong tổng thời gian. Đặc biệt, nhiều CronJob/Pod cùng khởi động có thể làm PostgreSQL hết connection dù mỗi Task chỉ thực hiện một vài truy vấn. Bài thuộc chương **Tối ưu và nâng cấp**, hướng dẫn đo chi phí, thiết kế ngân sách connection, cấu hình HikariCP, tối ưu transaction và quản lý vòng đời pool mà không phá tính đúng đắn của Spring Cloud Task.

**Phạm vi:** Ví dụ dùng Spring Boot với **HikariCP**, Spring Cloud Task và PostgreSQL, có bổ sung tình huống Spring Batch/Kubernetes. Các thông số minh họa không phải giá trị khuyến nghị chung cho mọi hệ thống; cần đối chiếu BOM, JDBC driver, schema và giới hạn DB của phiên bản thực tế. Mọi điều chỉnh phải được kiểm chứng bằng benchmark và thử lỗi.

## 1. Tối ưu cái gì: startup, connection hay SQL?

Một Task đọc một tệp nhỏ và ghi 500 dòng có thể có vòng đời:

~~~mermaid
flowchart TD
  A["CronJob hoặc API khởi chạy"] --> B["JVM và Spring Context khởi động"]
  B --> C["DataSource / HikariCP khởi tạo"]
  C --> D["TaskRepository: ghi START"]
  D --> E["Runner: đọc, xử lý, ghi SQL"]
  E --> F["TaskRepository: ghi END"]
  F --> G["Đóng Context và Hikari pool"]
  G --> H["Container trả exit code"]
~~~

Trong mô hình này, thời gian chạy gồm nhiều phần, không chỉ SQL nghiệp vụ:

~~~text
T_total ≈ T_JVM_Context
        + T_first_JDBC_connection
        + T_TaskRepository_START_END
        + T_business_processing
        + T_shutdown
~~~

Phép cộng chỉ là cách **phân tích chi phí**. Từng pha có thể chồng lấn hoặc chứa nhiều truy vấn/connection attempts nên cần đo mốc thực tế thay vì coi chúng là số đo framework có sẵn.

Ví dụ số liệu **giả định**:

| Giai đoạn | Thời gian |
| --- | ---: |
| JVM và Spring Context | 1,8 giây |
| Lấy kết nối JDBC đầu tiên | 0,8 giây |
| Ghi metadata Task | 0,3 giây |
| Xử lý nghiệp vụ | 1,1 giây |
| Dọn tài nguyên | 0,2 giây |
| **Tổng** | **4,2 giây** |

Nếu chỉ tối ưu một query nhanh hơn 20%, tổng thời gian có thể giảm rất ít. Nhưng nếu 30 Pod cùng chờ DB, thời gian lấy connection tăng từ dưới giây lên hàng chục giây, thậm chí lỗi hàng loạt.

**Câu hỏi trước khi chỉnh pool:** Task chậm vì startup, vì chờ `getConnection()`, vì SQL/lock, hay vì backend không đủ connection? Mỗi nguyên nhân cần cách sửa khác nhau.

## 2. Hai trách nhiệm JDBC: metadata và nghiệp vụ

Spring Cloud Task ghi một `TaskExecution` lúc bắt đầu và cập nhật kết quả khi kết thúc. Metadata gồm execution ID, task name, start/end time, exit code, exit message và arguments. Vì thế, **TaskRepository cần JDBC ngay cả khi runner không truy vấn CSDL nghiệp vụ**.

Nếu Task kết hợp Spring Batch, các `JobExecution`, `StepExecution`, tham số và checkpoint còn được ghi vào **JobRepository**. Chúng không phải các bản ghi giống nhau.

| Thành phần | Công việc JDBC | Đặc điểm tải |
| --- | --- | --- |
| TaskRepository | Tạo/cập nhật `TASK_EXECUTION`, lưu arguments | Ít câu lệnh nhưng quan trọng ở đầu/cuối vòng đời |
| Spring Batch JobRepository | Ghi trạng thái Job/Step, ExecutionContext | Tần suất phụ thuộc chunk/step/restart |
| Business DAO | Đọc, xử lý, batch insert/update | Có thể chiếm phần lớn thời gian và số connection |
| Migration hoặc schema initializer | Kiểm tra/tạo bảng ở startup | Có thể gây DDL lock nếu nhiều Pod cùng chạy |
| Listener nghiệp vụ | Audit, exit summary, outbox | Không nên giữ connection lâu khi Task sắp thoát |

Khi ứng dụng chỉ có **một DataSource**, Spring Cloud Task thường sử dụng nguồn đó cho TaskRepository. Với **nhiều DataSource**, cần cấu hình riêng phù hợp, ví dụ một implementation của `TaskConfigurer`, thay vì mặc định Spring sẽ chọn đúng kho metadata.

~~~mermaid
flowchart TB
    T["Spring Cloud Task"] --> R["TaskRepository"]
    T --> A["ApplicationRunner"]
    A --> W["Business Writer"]
    A --> B["Spring Batch (nếu có)"]
    B --> J["JobRepository"]
    R --> D1[("Metadata DB")]
    J --> D1
    W --> D2[("Business DB")]
~~~

Sơ đồ minh họa phương án tách metadata và nghiệp vụ. **Hai DB hoặc hai pool không tự động tăng hiệu năng**; chúng còn làm tăng cấu hình, mật khẩu, transaction managers và tổng số connection. Nếu cả hai pool trỏ đến cùng PostgreSQL, ngân sách DB phải tính **tổng số connection của cả hai**.

### 2.1. Vì sao TaskRepository phải được ưu tiên đúng mức?

Giả sử nghiệp vụ đã commit thành công nhưng mọi connection đều bị giữ bởi các thread đang chờ API ngoài. Callback kết thúc không mượn được connection để cập nhật `TaskExecution.END_TIME`. Người vận hành có thể thấy Task chưa hoàn tất, rồi chạy lại và vô tình nhập dữ liệu hai lần.

Vì vậy, không được để giao dịch SQL dài hoặc thread đồng thời chiếm cạn pool trong suốt vòng đời; phải kiểm tra khả năng ghi metadata cuối, đồng thời dùng **idempotency theo business key** để an toàn khi retry.

## 3. HikariCP và các giá trị mặc định cần hiểu đúng

Spring Boot ưu tiên **HikariCP** khi có trên classpath; `spring-boot-starter-jdbc` thường mang theo thư viện này. HikariCP duy trì một connection pool **bên trong mỗi JVM**, không chia sẻ connection giữa Pod.

Theo cấu hình HikariCP được dự án mô tả, các giá trị thường gặp:

| Thuộc tính | Mặc định HikariCP được tài liệu công bố | Ý nghĩa |
| --- | --- | --- |
| `maximumPoolSize` | **10** | Số connection tối đa trong pool một JVM |
| `minimumIdle` | Mặc định bằng `maximumPoolSize` | Pool cố duy trì số connection idle này khi có thể |
| `connectionTimeout` | **30.000 ms** | Thời gian tối đa chờ mượn connection |
| `validationTimeout` | **5.000 ms** | Thời gian tối đa kiểm tra connection còn sống |
| `initializationFailTimeout` | **1 ms**, sau giới hạn `connectionTimeout` | Quyết định pool có fail-fast khi không tạo được connection đầu tiên |
| `idleTimeout` | **600.000 ms** | Thời gian retire connection idle **vượt** mức minimumIdle |
| `maxLifetime` | **1.800.000 ms** | Tuổi tối đa của connection; không ngắt connection đang được mượn |
| `keepaliveTime` | **120.000 ms** trong README HikariCP hiện hành | Kiểm tra connection idle còn sống để tránh timeout của mạng/DB |
| `leakDetectionThreshold` | **0** (tắt) | Cảnh báo khi một connection bị mượn quá lâu |

Các giá trị trên là **HikariCP defaults**, không phải lời bảo đảm rằng mọi phiên bản Spring Boot sẽ luôn để nguyên: ứng dụng, profile, environment hoặc framework có thể override.

Không hiểu `maximumPoolSize=10` thành “tạo ngay mười connection lúc startup”. Nó là **giới hạn**, còn tốc độ/phương thức tạo connection phụ thuộc `minimumIdle` và nhu cầu. Nhưng khi 30 Pod đều muốn duy trì nhiều idle connection, tổng áp lực phía DB có thể đáng kể.

### 3.1. Cấu hình nào ít có tác dụng với Task cực ngắn?

- **`idleTimeout=10 phút`:** không giải quyết Task chỉ sống 10 giây. Thậm chí `idleTimeout` không có tác dụng khi `minimumIdle` bằng `maximumPoolSize`.
- **`maxLifetime=30 phút`:** không ảnh hưởng lớn nếu process kết thúc sau vài giây. Không đặt quá ngắn; HikariCP có giới hạn tối thiểu.
- **`keepaliveTime=2 phút`:** không giúp Task 10 giây; chỉ ping connection **idle** trong pool.
- **Tăng `maximumPoolSize`:** không làm một SQL tuần tự chạy nhanh hơn; có thể chỉ tăng connection pressure lên DB.

Ưu tiên xác định nhu cầu **connection đồng thời thật sự** thay vì tối ưu từng thuộc tính nhỏ một cách máy móc.

## 4. Kích thước pool phải tính trên toàn bộ Pod

Giả sử có nhiều Task hoặc worker chạy cùng lúc. Ta đặt:

~~~text
C_db        = ngân sách connection hữu ích của DB
C_other     = connection dành cho ứng dụng khác
C_reserved  = connection dành cho quản trị, migration, dự phòng
N           = số Pod Task đồng thời
P           = maximumPoolSize cho mỗi Pod
~~~

Điều kiện sàng lọc công suất:

~~~text
N × P + C_other + C_reserved ≤ C_db
~~~

Nếu có **nhiều pool cùng nối một database** trong mỗi Pod, thay `P` bằng tổng giới hạn của các pool; nếu có nhiều loại Task khác nhau, cộng `N_i × P_i`. Công thức này tính **giới hạn tiềm năng**, không phải dự đoán tất cả connection đều mở cùng lúc.

### 4.1. Bài toán mẫu

Một cụm PostgreSQL dành được **160 connection** cho workload, trong đó web services cần 40 và cần giữ 20 connection cho quản trị/monitoring/dự phòng. Như vậy Task còn ngân sách 100 connection. Nếu **25 Pod** cùng chạy:

| Pool mỗi Pod | Tổng tối đa 25 Pod | Nhận xét |
| --- | ---: | --- |
| 10 | 250 | Vượt xa ngân sách 100 |
| 4 | 100 | Chạm giới hạn, thiếu biên dự phòng |
| 3 | 75 | Có biên cho biến động |
| 1 | 25 | Tiết kiệm connection nhưng có thể nghẽn thread |

Không vì bảng trên mà mặc định chọn `maximumPoolSize=3` cho mọi Task. Nếu Task có bốn Step song song và các metadata transaction xảy ra đồng thời, pool ba connection có thể quá nhỏ. Ngược lại, một Task tuần tự với một transaction mỗi thời điểm có thể chỉ cần 2–3 connection.

**Cách chọn:** (1) tính ngân sách trên toàn cụm; (2) biết số luồng JDBC đồng thời; (3) kiểm tra p95/p99 thời gian chờ connection; (4) giảm/tăng pool bằng thử nghiệm thực tế; (5) đối chiếu tổng số kết nối và throughput database.

### 4.2. Đừng nhầm Forbid với giới hạn connection

`concurrencyPolicy: Forbid` của Kubernetes CronJob chỉ ngăn chồng lấn Job của **cùng CronJob**. Hai mươi CronJob khác nhau cùng chạy lúc 02:00 vẫn có thể tạo hai mươi Pod. Một Spring Batch Job remote partitioning có thể còn có nhiều worker.

Cần cân nhắc **phân tán lịch khởi động**, giới hạn đồng thời ở scheduler, giới hạn thread/partition, đặt pool size phù hợp, và dùng backoff/jitter khi xảy ra lỗi DB. Không tăng PostgreSQL `max_connections` vô hạn; mỗi backend session dùng tài nguyên.

## 5. Cấu hình tham khảo cho một Task ngắn dùng PostgreSQL

Ví dụ `application.yml` cho một Task chủ yếu chạy tuần tự:

~~~yaml
spring:
  application:
    name: invoice-import-task
  main:
    web-application-type: none
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
    hikari:
      pool-name: invoice-import-jdbc
      maximum-pool-size: 3
      minimum-idle: 0
      connection-timeout: 5000
      validation-timeout: 2000
      initialization-fail-timeout: 1
      idle-timeout: 60000
      max-lifetime: 600000
      keepalive-time: 0
  cloud:
    task:
      initialize-enabled: false
      closecontext-enabled: true
~~~

**Đây là điểm khởi đầu để thử nghiệm, không phải cấu hình chuẩn cho tất cả ứng dụng.** Các giá trị timeout HikariCP ở đây dùng **mili giây**. Biến môi trường phải được cấp bằng Secret/configuration phù hợp; không truyền mật khẩu DB qua CLI vì Spring Cloud Task có thể lưu command-line arguments.

| Lựa chọn | Vì sao thử? | Cần kiểm tra |
| --- | --- | --- |
| `maximum-pool-size=3` | Giảm mức connection tối đa per Pod | Có đủ cho metadata và nghiệp vụ khi cùng hoạt động không? |
| `minimum-idle=0` | Tránh cố duy trì nhiều connection idle | Có tăng độ trễ tạo connection vào lúc cần không? |
| `connection-timeout=5000` | Phát hiện pool cạn sớm hơn mặc định | Có gây lỗi giả khi database bình thường nhưng chậm không? |
| `validation-timeout=2000` | Giới hạn validation | Phải nhỏ hơn `connectionTimeout` |
| `initialization-fail-timeout=1` | Giữ fail-fast khi pool không sẵn sàng | HikariCP tính thêm thời gian này sau `connectionTimeout` |
| `idle-timeout=60000` | Retire connection dư nếu Task sống đủ lâu | Không quan trọng nếu Task kết thúc trước 60 giây |
| `max-lifetime=600000` | Đặt tuổi connection tối đa 10 phút | Hầu như không tác động Task 10 giây |
| `keepalive-time=0` | Tắt ping idle định kỳ trong một Task ngắn | Cần xem lại với Task chạy lâu |
| `closecontext-enabled=true` | Đóng context ở cuối Task | Không thay thế quản lý thread/transaction đúng |
| `initialize-enabled=false` | Tránh tự init metadata schema mỗi lần | Chỉ dùng khi migration đã tạo schema |

HikariCP cho phép `minimumIdle=0` nhưng **không có nghĩa pool sẽ không bao giờ lấy connection lúc startup**: cơ chế fail-fast vẫn có thể thử kết nối ban đầu. Cũng không nên đổi `initializationFailTimeout=-1` chỉ để “startup nhanh”: điều đó bỏ qua thử kết nối ban đầu, còn TaskRepository/runner vẫn sẽ lỗi khi thật sự cần DB.

### 5.1. Dependency mẫu

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Mẫu cần `parent`/`dependencyManagement` cho Spring Boot và Spring Cloud release train tương thích. `spring-boot-starter-jdbc` thường mang theo HikariCP. Nếu ứng dụng đã có starter JDBC tương ứng, không cần thêm một pool khác.

## 6. Phân biệt các timeout — một điểm rất dễ cấu hình sai

`spring.datasource.hikari.connection-timeout` giới hạn **thời gian chờ lấy connection**, không giới hạn thời gian câu SQL chạy. Một SQL giữ connection 90 giây sẽ không tự bị hủy vì bạn đặt `connection-timeout: 5000`.

| Loại timeout | Áp dụng cho | Không đảm bảo |
| --- | --- | --- |
| Hikari `connectionTimeout` | Chờ mượn connection từ pool | Không ngắt SQL đang chạy |
| Hikari `validationTimeout` | Kiểm tra connection sống | Không giới hạn Task |
| Hikari `initializationFailTimeout` | Fail-fast khi khởi tạo pool | Không phải retry policy |
| Driver `connectTimeout` | Thiết lập kết nối tới DB server | Không phải chờ pool rảnh |
| Driver `socketTimeout` | Chờ thao tác socket JDBC | Không phải timeout nghiệp vụ toàn Job |
| Query/statement timeout | Một câu SQL | Không giới hạn toàn bộ workflow |
| Spring `@Transactional(timeout=...)` | Transaction do transaction manager phù hợp quản lý | Không tự giới hạn API HTTP bên ngoài |
| Kubernetes `activeDeadlineSeconds` | Tổng thời gian Kubernetes Job hoạt động | Không giới hạn từng connection acquisition |

Ví dụ **thuộc tính PGJDBC**, nếu muốn kiểm soát cả TCP/driver:

~~~yaml
spring:
  datasource:
    hikari:
      data-source-properties:
        connectTimeout: 3
        socketTimeout: 30
        ApplicationName: invoice-import-task
~~~

Ở PGJDBC, `connectTimeout` và `socketTimeout` được khai báo bằng **giây**, khác với Hikari connection timeout bằng mili giây. Giá trị quá thấp có thể cắt các query hợp lệ; phải kiểm tra hệ quản trị DB, driver và network. Không copy thuộc tính PostgreSQL sang MySQL/Oracle mà không xem tài liệu riêng.

### 6.1. Cần fail-fast nhưng không gây retry storm

Với Task bắt buộc phải ghi TaskRepository, database bị lỗi là sự cố thực sự. Thường nên báo lỗi sớm với timeout hợp lý để Kubernetes Job/scheduler quản lý retry có **giới hạn, backoff và jitter**.

Nếu `initialization-fail-timeout=-1`, pool có thể khởi tạo mà chưa kiểm tra DB; Task vẫn có khả năng lỗi ở lần gọi JDBC đầu tiên, đôi khi chưa kịp tạo metadata. Một Task “khởi động nhanh” nhưng không thể ghi TaskRepository không phải một tối ưu đúng.

## 7. Tránh khởi tạo schema lặp ở mỗi Pod

Mỗi lần một Task mới khởi động, Spring Boot/Spring Cloud Task có thể thực hiện thao tác khởi tạo schema nếu tính năng bật và các điều kiện được đáp ứng. Trong production với nhiều Pod, đừng biến mỗi lần chạy nghiệp vụ thành một đợt DDL/migration tranh khóa.

Nếu schema đã được quản lý bởi **Flyway, Liquibase hoặc pipeline migration riêng**, có thể dùng:

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
  sql:
    init:
      mode: never
  batch:
    jdbc:
      initialize-schema: never
~~~

Ba cờ có vai trò khác nhau:

- `spring.cloud.task.initialize-enabled=false`: tắt schema initializer của Spring Cloud Task.
- `spring.sql.init.mode=never`: tắt generic SQL initialization của Spring Boot.
- `spring.batch.jdbc.initialize-schema=never`: tắt Spring Batch metadata schema initialization qua Boot nếu có Batch.

**Chỉ tắt sau khi schema đã tồn tại, đúng DDL và version.** Tắt nhầm trên DB rỗng sẽ gây lỗi bảng `TASK_EXECUTION` hoặc `BATCH_JOB_EXECUTION` không tồn tại. Dùng một tài khoản migration có quyền DDL riêng; tài khoản runtime chỉ cần quyền DML.

Nếu chỉ dùng `JdbcTemplate`, tránh mang thêm cả ORM/JPA startup khi không có nhu cầu. Nhưng không loại bỏ JPA đang phục vụ nghiệp vụ chỉ để giảm vài mili giây mà chưa kiểm tra toàn bộ transaction và mapping.

## 8. Tránh giữ connection khi chỉ đang chờ API hoặc xử lý CPU

Một kết nối được mượn từ pool không nhất thiết đang thực hiện SQL. Nếu transaction mở rồi chờ HTTP 90 giây, connection có thể bị giữ suốt khoảng đó.

~~~text
BEGIN TRANSACTION
  SELECT dữ liệu
  HTTP call tới đối tác (chờ 60 giây)
  Tính toán CPU (30 giây)
  UPDATE dữ liệu
COMMIT
~~~

Nếu ba thread đều làm vậy với pool tối đa ba connection, thread thứ tư sẽ chờ rồi có thể timeout. Cách sửa thường không phải tăng pool vô hạn mà là **thu hẹp transaction**, khi nghiệp vụ cho phép:

~~~text
HTTP fetch / CPU transform (không giữ JDBC transaction)
    → BEGIN TRANSACTION
      ghi một chunk dữ liệu
      COMMIT
    → lặp cho chunk tiếp theo
~~~

Nguyên tắc:

1. Dùng transaction ngắn có ranh giới rõ, không bao quanh công việc I/O mạng/CPU kéo dài.
2. Ghi theo batch/chunk để giảm round trips nhưng vẫn có checkpoint/rollback hợp lý.
3. Đóng `Connection`, `PreparedStatement`, `ResultSet` theo try-with-resources khi dùng JDBC trực tiếp; ưu tiên `JdbcTemplate` để quản lý tài nguyên.
4. Không tạo một `HikariDataSource` mới cho từng tệp hoặc từng dòng.
5. Nếu dùng `@Transactional` qua Spring proxy, tránh self-invocation khiến transaction advice không có hiệu lực.
6. Không thực hiện cả Job trong một transaction khổng lồ chỉ để giảm số commit.

### 8.1. Ví dụ JdbcTemplate.batchUpdate với transaction theo chunk

Dưới đây là một service PostgreSQL dùng `JdbcTemplate` để ghi nhiều dòng vào bảng đã có unique key `(source_id, external_id)`.

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record OrderRow(String sourceId, String externalId, BigDecimal amount) {}

@Service
public class OrderBatchWriter {
    private final JdbcTemplate jdbc;

    public OrderBatchWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeChunk(List<OrderRow> rows) {
        if (rows.isEmpty()) {
            return;
        }

        jdbc.batchUpdate("""
            INSERT INTO order_import (source_id, external_id, amount)
            VALUES (?, ?, ?)
            ON CONFLICT (source_id, external_id) DO NOTHING
            """,
            rows,
            rows.size(),
            (ps, row) -> {
                ps.setString(1, row.sourceId());
                ps.setString(2, row.externalId());
                ps.setBigDecimal(3, row.amount());
            });
    }
}
~~~

Ví dụ giả định bảng và constraint đã được tạo, ứng dụng có `JdbcTemplate` và transaction manager của đúng DataSource. `writeChunk` phải được gọi qua **Spring-managed bean**, không tự gọi `this.writeChunk(...)` từ một method trong cùng class nếu muốn proxy transaction hoạt động. Số dòng của chunk phải có giới hạn rõ; ở đây `rows.size()` chỉ là kích thước một chunk đã được giới hạn trước.

Phương thức này không gọi API ngoài trong transaction. Nếu muốn nhập tệp 100.000 dòng, một service khác có thể đọc/chuẩn hóa ngoài transaction rồi gọi `writer.writeChunk(...)` nhiều lần. Cần tránh giữ toàn bộ nguồn trong RAM nếu dữ liệu lớn.

### 8.2. Chọn chunk size bằng số liệu

| Chunk quá nhỏ | Chunk quá lớn |
| --- | --- |
| Nhiều lượt round trip và commit | Giữ connection/lock lâu |
| Overhead mỗi batch cao | Rollback và retry cả chunk tốn kém |
| Khôi phục từng phần nhỏ đơn giản | Có nguy cơ vượt timeout, tăng WAL/CPU |
| Có thể bỏ lỡ lợi ích batching | Có thể làm nghẽn JobRepository và các Task khác |

Có thể thử kích thước 100, 500 và 1.000 rồi đo throughput, transaction duration, p95 mượn connection và tỉ lệ lỗi. Nếu dùng Spring Batch, chunk size và checkpoint liên quan trực tiếp khả năng restart; không bỏ transaction chỉ vì muốn giảm thời gian khóa.

## 9. Pool nhỏ và TaskRepository cần connection ở cuối vòng đời

Một tình huống nguy hiểm:

~~~text
Task bắt đầu và ghi START thành công
    → Runner ghi dữ liệu nghiệp vụ và COMMIT
    → Thread khác giữ hết connection / DB mất kết nối
    → TaskRepository không ghi được END
    → Scheduler thấy lỗi/chưa rõ kết quả
    → Người vận hành retry
    → Dữ liệu nghiệp vụ có thể được tạo lại
~~~

Cơ chế **TaskRepository theo dõi lần chạy**, không đảm bảo exactly-once cho bảng nghiệp vụ. Luôn dùng business key, unique constraint, idempotent upsert hoặc outbox khi có tác dụng phụ; không dựa vào `TaskExecution ID` làm khóa chống trùng.

Nếu tách metadata DB khỏi business DB, hãy kiểm tra transaction boundaries rõ ràng. Hai transaction manager khác nhau không tự tạo một giao dịch nguyên tử xuyên database. Khi một phía commit và phía còn lại thất bại, phải có quy trình recovery/reconciliation.

## 10. Pooling bên ngoài: PgBouncer, proxy và serverless DB

Khi nhiều Task chạy ngắn, tạo/đóng rất nhiều TCP/TLS session có thể là áp lực lớn lên database. Một proxy như **PgBouncer** có thể hỗ trợ quản lý kết nối backend, nhưng không phải lựa chọn mặc định trong mọi hệ thống.

**Cần đánh giá tương thích nếu dùng transaction pooling:**

- Session variables, temporary tables, session-level advisory locks và prepared statements có thể phụ thuộc connection backend ổn định.
- Driver PostgreSQL có thể dùng server-side prepared statements theo ngưỡng/config riêng.
- Transaction dài làm giảm khả năng chia sẻ connection backend.
- Pool ứng dụng vẫn cần giới hạn; proxy cũng có connection/client/queue limits.
- TaskRepository và Spring Batch restart/locking phải được kiểm thử với cấu hình proxy thật.

Đừng kích hoạt transaction pooling chỉ để làm đẹp số lượng connection. Hãy chứng minh dữ liệu không sai dưới retry, session state không bị hiểu nhầm và query vẫn chạy được với pooling mode đã chọn.

Nếu database **serverless** có cold start hoặc phải thức dậy từ trạng thái nghỉ, connection đầu tiên có thể chậm bất thường. Đo riêng cold/warm startup; chọn driver timeout/`connectionTimeout` và policy retry có giới hạn. Không tắt TLS hoặc để password trong JDBC URL để “giảm overhead”.

## 11. Kết thúc Task và đóng Hikari pool đúng cách

Spring Cloud Task hỗ trợ:

~~~properties
spring.cloud.task.closecontext-enabled=true
~~~

Sau khi runner hoàn tất và TaskRepository cập nhật kết quả, đóng `ApplicationContext` giúp gọi destroy callbacks trên bean. Khi `HikariDataSource` do Spring quản lý được đóng, pool giải phóng các connection của nó.

**Không tự gọi `dataSource.close()` từ `ApplicationRunner`** nếu TaskRepository vẫn cần ghi trạng thái kết thúc. Đóng quá sớm có thể khiến `END_TIME` không được cập nhật. Cũng không để runner submit một việc bất đồng bộ rồi trả về ngay: context có thể đóng khi thread còn đang sử dụng JDBC.

~~~java
@Bean
ApplicationRunner safeRunner(ExecutorService executor) {
    return args -> {
        Future<?> task = executor.submit(() -> performImport());
        task.get(); // Đợi xử lý hoàn tất hoặc nhận exception.
    };
}
~~~

Đây chỉ là mã ý tưởng: cần định nghĩa executor, `performImport()`, xử lý interrupt, cancellation, timeout và shutdown executor. Trong production, không chờ vô hạn: cần một deadline nghiệp vụ phù hợp.

### 11.1. SIGTERM khác SIGKILL

| Tình huống | Điều có thể xảy ra |
| --- | --- |
| Thoát bình thường | Context đóng, pool dọn connection và Task có cơ hội ghi END |
| SIGTERM | Có thể có graceful shutdown trong khoảng cấu hình; cần kiểm thử |
| SIGKILL / OOM / node mất | Không bảo đảm `finally`, destroy callback hoặc ghi END được gọi |
| DB bị cắt mạng | Connection phía DB có thể cần thời gian để phát hiện peer đã chết |

Với Kubernetes Job, cân đối `terminationGracePeriodSeconds`, `activeDeadlineSeconds`, thời gian transaction và thời gian đóng. Không đánh giá “không còn connection trong `pg_stat_activity`” ngay khi Pod bị kill là điều chắc chắn tức thời.

## 12. Quan sát và đo pool trong tác vụ hữu hạn

Spring Boot Actuator có thể cung cấp **DataSource metrics** với tiền tố `jdbc.connections` và metric riêng của Hikari với tiền tố `hikaricp`, nếu có registry/instrumentation phù hợp. Tên metric sau khi xuất sang Prometheus/OTLP có thể được chuẩn hóa khác nhau.

| Chỉ số | Ý nghĩa | Nguồn |
| --- | --- | --- |
| Active/idle/pending connections | Pool có hết connection hay giữ quá nhiều idle? | Hikari/Micrometer |
| Connection acquire time | Thời gian chờ mượn connection | Hikari metrics |
| Connection creation time | Cold connection có đắt? | Hikari metrics và log |
| Số connection tới DB | Có vượt ngân sách khi fan-out? | DB monitoring |
| Task startup/total duration | Pool tuning có tác động tổng thể? | Task observation và Kubernetes Job timestamps |
| SQL/query/lock wait | DB hay app là bottleneck? | Database metrics/traces |
| `TASK_EXECUTION.END_TIME`/exit code | Metadata kết thúc có được ghi? | TaskRepository |
| Retry/Pod failures | Pool timeout làm Job retry? | Kubernetes Job/Pod |

**Task chạy vài giây có thể kết thúc trước khi Prometheus scrape endpoint.** Không kết luận “pool không có connection” chỉ vì dashboard trống; dùng logs, telemetry push đã kiểm chứng hoặc giám sát DB/Kubernetes ngoài tiến trình.

### 12.1. PostgreSQL: xem connection theo application_name

Có thể cấp application name không nhạy cảm cho PGJDBC bằng `data-source-properties.ApplicationName`. Sau đó, truy vấn thống kê:

~~~sql
SELECT application_name,
       state,
       COUNT(*) AS connections
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state
ORDER BY application_name, state;
~~~

Chạy bằng tài khoản có quyền quan sát phù hợp. Với Task rất ngắn, một snapshot có thể bỏ lỡ đỉnh kết nối; dùng lấy mẫu theo thời gian hoặc metrics DB. Nếu nhiều Pod cùng tên application, tổng số connection ở cùng nhóm giúp nhận diện áp lực nhưng không tách từng Pod; chỉ thêm Pod ID vào thông tin quan sát nếu không làm lộ dữ liệu nhạy cảm.

TaskRepository có thể được đối chiếu riêng:

~~~sql
SELECT TASK_EXECUTION_ID,
       TASK_NAME,
       START_TIME,
       END_TIME,
       EXIT_CODE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'invoice-import-task'
ORDER BY START_TIME DESC
LIMIT 20;
~~~

Nếu `END_TIME` rỗng, Task có thể đang chạy hoặc đã chết trước khi cập nhật; đối chiếu thêm Pod status, DB connectivity và log.

## 13. Quy trình benchmark trước/sau tối ưu

**Không kết luận cấu hình mới tốt hơn chỉ vì số connection giảm.** Cần so sánh độ đúng dữ liệu, throughput và thời gian chạy.

### 13.1. Chuẩn bị phép thử

1. Chuẩn bị môi trường tương đương production về PostgreSQL, network, schema, số Pod, dữ liệu và version JDBC driver.
2. Chọn workload cố định: ví dụ nhập 10.000 bản ghi qua vài chunk và một TaskRepository START/END hoàn chỉnh.
3. Tách **cold DB/cold JVM** khỏi các lượt thử đã ấm.
4. Gắn correlation ID không nhạy cảm để nối log Task, Job, Pod và DB.
5. Đo mốc khởi động process, first connection, first query, last business commit, TaskRepository END, process exit.
6. Chạy nhiều lượt với **một Pod** và **nhiều Pod đồng thời**; đo p50/p95 và đỉnh connection.
7. Xác minh tổng số bản ghi, checksum, idempotency và số lần retry không bị thay đổi ngoài dự kiến.

### 13.2. Ma trận thử nghiệm

| Kịch bản | Cấu hình | Pod đồng thời | Điều cần kiểm tra |
| --- | --- | ---: | --- |
| A — Baseline | Mặc định HikariCP | 1 | Startup/first connection/total Task |
| B — Nhỏ hơn | max=3, minIdle=0 | 1 | Có chậm SQL đầu tiên không? |
| C — Fan-out baseline | Mặc định | 20 | Peak DB sessions và lỗi |
| D — Fan-out giới hạn | max=3, minIdle=0 | 20 | Pool pending, connection count, p95 |
| E — Pool quá nhỏ | max=1 | 20, worker song song | Timeout hoặc metadata END bị nghẽn? |
| F — Batch size | max=3, chunk 100/500/1000 | 5–20 | Throughput, lock/transaction wait |
| G — DB chậm/không sẵn sàng | max=3 | 10 | Fail-fast, timeout, backoff |
| H — Dừng Pod | max=3 | 1 | END_TIME và connection cleanup |
| I — Schema initialization | Init tự động vs migration sẵn | 20 | Startup time, DDL contention |

Một kết quả giả định: baseline 20 Pod có 110 connection đỉnh và 4 Task lỗi; pool nhỏ còn 48 connection và không có Task lỗi. Đây là tín hiệu tốt **chỉ nếu** SLA, throughput và dữ liệu nghiệp vụ vẫn đúng. Nếu pool một connection tăng thời gian chạy gấp ba, hãy phân tích metadata/transaction concurrency thay vì cố ép pool nhỏ nhất.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `HikariPool ... Connection is not available` | Pool hết connection hoặc DB chậm | Xem active/pending, transaction dài, timeout |
| `too many clients already` | Nhiều Pod/pool vượt ngân sách DB | Giới hạn fan-out và pool size, tính cả ứng dụng khác |
| Task fail khi startup | DB/TLS/credential/schema lỗi | Kiểm tra JDBC driver, migration, kết nối thật |
| Khởi động nhanh với init fail timeout âm nhưng JDBC vẫn lỗi | Đã dời lỗi từ startup sang lần mượn connection | Không coi đây là tối ưu thành công; sửa DB |
| `minimumIdle=0` làm first SQL chậm | Cold connection phải tạo theo nhu cầu | Benchmark và cân nhắc minimum idle nhỏ hơn max |
| `idleTimeout` không tác dụng | minIdle=maxPoolSize hoặc Task quá ngắn | Hiểu scope; không tối ưu vô ích |
| Task đã commit dữ liệu nhưng metadata không có END | DB cạn connection hoặc Pod bị kill | Đối chiếu business key và logs trước retry |
| Tăng pool nhưng throughput giảm | DB lock/CPU/I/O bottleneck | Tối ưu SQL, giảm concurrency, đo DB |
| Task không thoát sau runner | Executor/context còn sống | Chờ worker, đóng context đúng vòng đời |
| Leak warnings khi query dài | Giữ connection lâu hoặc leak thật | Thu hẹp transaction, xem stack trace, kiểm thử |
| Chạy qua PgBouncer gặp lỗi session | Transaction pooling không tương thích session state | Điều chỉnh driver/transaction mode, kiểm thử |
| Mỗi Pod cố tạo bảng Task | Schema init chưa chuyển sang migration riêng | Migrate trước, rồi tắt init |
| Metric Hikari không xuất hiện | Task kết thúc trước exporter/scrape | Quan sát DB và logs, kiểm thử telemetry push |

`leakDetectionThreshold` chỉ ghi cảnh báo connection giữ lâu và có thể tạo **false positive** cho giao dịch Batch hợp lệ. Nó không tự dọn connection bị leak. Bật khi chẩn đoán có kiểm soát, không coi là một công cụ sửa lỗi.

## 15. An toàn và nâng cấp kết nối JDBC

- Đừng truyền `spring.datasource.password` qua command-line arguments vì Spring Cloud Task có thể ghi nó vào `TASK_EXECUTION_PARAMS`. Dùng Secret/credential provider.
- Tách quyền runtime với migration: tài khoản Task không cần DDL nếu schema đã được migrate.
- Không tắt TLS để giảm thời gian connect nếu môi trường yêu cầu mã hóa đường truyền.
- Theo dõi JDBC driver, HikariCP, Spring Boot và Spring Cloud Task tương thích bằng BOM; kiểm tra release notes khi nâng cấp vì default/binding có thể thay đổi.
- Nếu đổi pool implementation hoặc DataSource beans, xác minh **TaskRepository vẫn dùng đúng database** và dữ liệu lịch sử không mất.
- Không log raw connection strings, password hoặc toàn bộ environment để chẩn đoán pool.
- Chạy test **khởi động thất bại**, retry, timeout, dừng Pod, schema cũ và pool exhausted trước nâng cấp production.
- Giữ migration và rollout theo thứ tự: schema tương thích trước, image mới sau; có rollback plan và kiểm tra TaskExecution/Batch metadata.
- Khi Task chạy ngắn, **connection count phải đo trên toàn cụm**, không chỉ trong một process.

## 16. Bài tập thực hành

Một nền tảng chạy **30 Pod Task** đồng thời, mỗi Task nhập CSV khoảng 15 giây và có Spring Batch chunk-oriented Step. PostgreSQL cấp ngân sách 140 connection cho tất cả workload; web services và hệ thống giám sát dùng 70 connection, để lại 70 connection cho Task và dự phòng. Mỗi Pod có hai thread có thể mượn JDBC connection trong cùng một thời điểm.

1. Tính giới hạn connection tiềm năng nếu mỗi Pod dùng pool mặc định max 10; giải thích rủi ro.
2. Tính giới hạn nếu max=3 và max=2. Chọn cấu hình thử ban đầu, có biên ngân sách và lý do về hai thread.
3. Viết `application.yml` chứa `maximum-pool-size`, `minimum-idle`, `connection-timeout`, `validation-timeout`, `closecontext-enabled` và `initialize-enabled`.
4. Giải thích vì sao `connection-timeout=5000` không hủy câu SQL đang chạy 12 giây.
5. Tách HTTP fetch/CPU transform khỏi JDBC transaction; tạo một `writeChunk` với `JdbcTemplate.batchUpdate`.
6. Thiết kế thử nghiệm 1, 10, 30 Pod cùng chạy. Đo pool active/pending, DB connections, total Task duration và % Task thất bại.
7. Cho DB không sẵn sàng lúc startup, so sánh fail-fast và `initializationFailTimeout=-1`.
8. Dừng một Pod trước khi TaskRepository ghi END; giải thích vì sao retry cần unique business key.
9. Kiểm tra schema initializer đã tắt **sau khi** migration tạo đủ Task/Batch tables.
10. Giả sử một DataSource thứ hai được thêm cho business DB; tính lại ngân sách connection và kiểm tra transaction manager.
11. Thử tăng chunk size 100 → 500 → 1.000 và đo transaction duration, throughput, lock wait, rollback.
12. Trình bày policy timeout/retry khi PostgreSQL lỗi, bảo đảm không tạo retry storm.

**Tiêu chí đạt:** đề xuất pool size dựa trên số Pod và ngân sách connection thực, không chỉ sao chép cấu hình mặc định; đồng thời chứng minh TaskRepository/JobRepository cập nhật đúng, thời gian chạy đáp ứng SLA và kết quả nghiệp vụ an toàn khi lỗi.

## 17. Tổng kết

1. **Task chạy ngắn vẫn cần JDBC** để ghi TaskExecution và có thể cần JobRepository của Spring Batch.
2. **Pool HikariCP nằm trong một JVM**, còn PostgreSQL phục vụ tất cả Pod. Ngân sách kết nối phải tính theo số Pod đồng thời và tất cả pool/ứng dụng.
3. HikariCP mặc định **max=10**, `minimumIdle` mặc định bằng max; cấu hình này không mặc nhiên phù hợp CronJob chỉ chạy vài giây.
4. `minimumIdle=0` có thể giảm idle connections nhưng tăng chi phí kết nối theo nhu cầu; đừng áp dụng nếu chưa đo.
5. **`connectionTimeout` chỉ giới hạn chờ mượn connection**; cần timeout riêng cho driver, SQL, transaction và Kubernetes Job.
6. Tối ưu lớn thường đến từ **transaction ngắn, batching hợp lý, không giữ connection trong HTTP call** và tránh init schema ở mọi Pod.
7. Đóng `ApplicationContext` ở cuối Task giúp giải phóng pool, nhưng không gọi `DataSource.close()` trước khi TaskRepository ghi kết quả cuối.
8. SIGKILL/OOM có thể ngăn ghi `END_TIME`; TaskExecution không thay thế idempotency của bảng nghiệp vụ.
9. **Benchmark cả một Pod và nhiều Pod**: connection peak, p95 acquire, tổng thời lượng, số retry, độ đúng dữ liệu và trạng thái metadata.

### Tài liệu tham khảo chính thức

- [Spring Cloud Task — Features: DataSource và TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Boot — SQL Databases và cấu hình DataSource](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Common Application Properties: Hikari](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [HikariCP — Configuration Knobs, defaults và caveats](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Spring Boot — Actuator Metrics cho JDBC và HikariCP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Batch — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
