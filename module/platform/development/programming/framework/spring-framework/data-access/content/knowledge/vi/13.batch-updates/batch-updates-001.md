# Batch giảm số lượt trao đổi cho nhiều thao tác tương tự

## 1. Batch giải quyết vấn đề gì?

Khi một ứng dụng Spring cần thực hiện hàng trăm hoặc hàng nghìn lệnh INSERT, UPDATE hoặc DELETE có **cùng cấu trúc SQL nhưng khác tham số**, cách lặp từng lệnh thường tạo ra nhiều lần trao đổi giữa ứng dụng và cơ sở dữ liệu. **JDBC batch** gom nhiều bộ tham số vào cùng một lần gọi thực thi batch của driver để giảm chi phí trao đổi và quản lý câu lệnh.

Ví dụ cập nhật trạng thái cho 1.000 đơn hàng:

~~~text
Không batch:
Ứng dụng -> DB: UPDATE ... WHERE id = 1
Ứng dụng -> DB: UPDATE ... WHERE id = 2
...
Ứng dụng -> DB: UPDATE ... WHERE id = 1000

Có batch, batchSize = 200:
Ứng dụng -> JDBC driver: 200 bộ tham số -> executeBatch()
                         200 bộ tham số -> executeBatch()
                         ... (5 batch)
~~~

Nhờ batching, driver có cơ hội gộp/đường ống hóa lệnh và giảm các round trip trên mạng. **Năm lần gọi executeBatch() không đồng nghĩa chắc chắn chỉ có năm gói tin hay năm round trip vật lý**: chi tiết do driver, giao thức, cấu hình và database quyết định.

### Phân biệt ba khái niệm

| Cách làm | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| Gọi `jdbcTemplate.update(...)` trong vòng lặp | Mỗi phần tử là một lần gọi cập nhật riêng | Vài bản ghi, logic mỗi thao tác khác nhau |
| `jdbcTemplate.batchUpdate(...)` | Nhiều bộ tham số cho một mẫu SQL; JDBC driver thực thi theo batch | Nhiều INSERT/UPDATE/DELETE tương tự |
| Một lệnh SQL xử lý hàng loạt, chẳng hạn `UPDATE ... WHERE ...` hoặc `INSERT ... VALUES (...), (...)` | Bản thân database xử lý nhiều dòng bằng một câu SQL | Có thể biểu diễn toàn bộ yêu cầu bằng một câu lệnh set-based |

Batch JDBC **không biến 1.000 câu UPDATE thành một UPDATE duy nhất**. Database vẫn phải thực thi logic tương ứng từng bộ tham số. Nếu một câu SQL set-based có thể giải quyết nghiệp vụ đúng cách thì cần cân nhắc nó trước.

## 2. Cơ chế JDBC và tác động đến round trip

JDBC cung cấp `PreparedStatement` để cố định SQL và thay đổi dữ liệu qua tham số. Khi dùng batch, ý tưởng tương đương:

~~~java
// Minh họa JDBC thuần; dataSource được ứng dụng cung cấp.
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "UPDATE task SET status = ? WHERE id = ?")) {
    for (StatusChange change : changes) {
        ps.setString(1, change.status());
        ps.setLong(2, change.id());
        ps.addBatch();
    }
    int[] updateCounts = ps.executeBatch();
}
~~~

Đây là **đoạn minh họa**, không phải file Java tự chạy: `dataSource`, `StatusChange` và `changes` thuộc ngữ cảnh gọi. Với Spring, `JdbcTemplate` quản lý việc lấy/trả kết nối, tạo/đóng statement và chuyển `SQLException` thành `DataAccessException`.

- `addBatch()` xếp một bộ tham số vào batch; `executeBatch()` yêu cầu driver xử lý các mục đã xếp.
- SQL phải có cấu trúc phù hợp để tái sử dụng `PreparedStatement`; chỉ giá trị tham số thay đổi.
- Driver có thể tối ưu, gửi lệnh gộp hoặc rơi về thực thi riêng lẻ nếu không hỗ trợ batch. **Không có đảm bảo tốc độ tăng theo một hệ số cố định.**
- Batch giảm overhead truyền thông/statement. Nó không bỏ qua parse/execute, ràng buộc UNIQUE/FOREIGN KEY, trigger, index update, lock hay chi phí ghi log của database.

Mô hình ước lượng để hiểu xu hướng (không phải công thức đo chính xác):

- `N`: số thao tác; `k`: số mục mỗi batch; `L`: overhead trao đổi; `E`: thời gian thực thi trung bình mỗi mục.
- Không batch: `T ≈ N × (L + E)`.
- Batch: `T ≈ ceil(N/k) × L + N × E + chi phí đóng/gửi batch`.

Phần giảm nhiều nhất thường là `L`, nhất là khi database ở xa và mỗi lệnh nhỏ. Với database bận CPU/I/O, lock hoặc trigger nặng, lợi ích có thể hạn chế.

## 3. Spring JDBC: ví dụ chạy được với Java 17+

Ví dụ sau dùng Spring Boot 3.3.x, Spring JDBC và H2 trong bộ nhớ. Hai bản ghi bắt đầu ở trạng thái `NEW`; service cập nhật cùng mẫu SQL thành `DONE` qua một batch. Tách `@Transactional` sang service được Spring quản lý để lời gọi đi qua transaction proxy.

Cấu trúc file:

~~~text
batch-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/BatchDemoApplication.java
    └── resources/application.properties
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'batch-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**src/main/resources/application.properties**

~~~properties
spring.datasource.url=jdbc:h2:mem:batchdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
~~~

**src/main/java/demo/BatchDemoApplication.java**

~~~java
package demo;

import java.util.Arrays;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@SpringBootApplication
public class BatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TaskBatchWriter writer) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE task (
                        id BIGINT PRIMARY KEY,
                        status VARCHAR(20) NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO task (id, status) VALUES (?, ?)",
                    1L, "NEW");
            jdbc.update(
                    "INSERT INTO task (id, status) VALUES (?, ?)",
                    2L, "NEW");

            List<StatusChange> changes = List.of(
                    new StatusChange(1L, "DONE"),
                    new StatusChange(2L, "DONE")
            );

            int[][] counts = writer.updateStatuses(changes);
            int[] sizes = Arrays.stream(counts)
                    .mapToInt(batch -> batch.length)
                    .toArray();
            System.out.println("Batch sizes: " + Arrays.toString(sizes));

            Integer done = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM task WHERE status = ?",
                    Integer.class, "DONE");
            System.out.println("DONE rows: " + done);
        };
    }
}

record StatusChange(long id, String status) {}

@Service
class TaskBatchWriter {
    private static final int BATCH_SIZE = 100;
    private final JdbcTemplate jdbc;

    TaskBatchWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public int[][] updateStatuses(List<StatusChange> changes) {
        if (changes.isEmpty()) {
            return new int[0][];
        }

        return jdbc.batchUpdate(
                "UPDATE task SET status = ? WHERE id = ?",
                changes,
                BATCH_SIZE,
                (ps, change) -> {
                    ps.setString(1, change.status());
                    ps.setLong(2, change.id());
                });
    }
}
~~~

Tại thư mục dự án, dùng Gradle 8.x và JDK 17+ (hoặc wrapper nếu đã có):

~~~bash
gradle bootRun
~~~

Hai dòng do chương trình in ra (ngoài log khởi động Spring Boot):

~~~text
Batch sizes: [2]
DONE rows: 2
~~~

**Giải thích chính xác:**

1. `JdbcTemplate.batchUpdate(sql, collection, batchSize, setter)` lấy cùng mẫu SQL, duyệt phần tử và bind tham số theo `ParameterizedPreparedStatementSetter`.
2. `BATCH_SIZE = 100` là giới hạn số mục trong một nhóm; vì ví dụ chỉ có 2 mục nên kết quả có một mảng con gồm 2 update count. Nó không chứng minh database đã dùng đúng một round trip.
3. Giá trị trả về là `int[][]`: mỗi mảng con ứng với một nhóm, mỗi số bên trong ứng với một mục. **Số phần tử của mảng** không phải tổng số dòng được sửa.
4. `@Transactional` áp dụng khi `CommandLineRunner` gọi method public của `TaskBatchWriter` qua bean Spring. Nếu lỗi dữ liệu gây `DataAccessException` đi ra ngoài method, Spring mặc định đánh dấu rollback cho transaction đó.
5. Trong ví dụ, hai lệnh `jdbc.update` tạo dữ liệu mẫu nằm **ngoài** transaction của `updateStatuses`; ứng dụng thực tế cần đặt ranh giới transaction theo đúng nghiệp vụ.

Nếu không dùng Spring Boot, vẫn có thể khởi tạo `JdbcTemplate` bằng `DataSource` và gọi các API batch tương tự; ví dụ trên dùng Boot để có cấu hình chạy tối thiểu.

## 4. Các API batch của Spring JDBC

### 4.1. `BatchPreparedStatementSetter`: toàn quyền bind theo chỉ số

Với danh sách đã có trong bộ nhớ:

~~~java
// Mảnh method đặt trong class đã có field JdbcTemplate jdbc.
int[] updateStatuses(List<StatusChange> changes) {
    return jdbc.batchUpdate(
            "UPDATE task SET status = ? WHERE id = ?",
            new org.springframework.jdbc.core.BatchPreparedStatementSetter() {
                @Override
                public void setValues(
                        java.sql.PreparedStatement ps, int i)
                        throws java.sql.SQLException {
                    StatusChange change = changes.get(i);
                    ps.setString(1, change.status());
                    ps.setLong(2, change.id());
                }

                @Override
                public int getBatchSize() {
                    return changes.size();
                }
            });
}
~~~

API này trả về `int[]` cho một lần gọi, nhưng danh sách rất lớn có thể làm batch quá to. Có thể tự chia danh sách hoặc dùng overload có tham số `batchSize` như ví dụ chạy được ở trên.

### 4.2. Overload có `batchSize`: thuận tiện khi dữ liệu nhiều

~~~java
int[][] counts = jdbc.batchUpdate(
        "UPDATE task SET status = ? WHERE id = ?",
        changes,
        200,
        (ps, item) -> {
            ps.setString(1, item.status());
            ps.setLong(2, item.id());
        });
~~~

Nếu có 450 mục và `batchSize = 200`, dạng nhóm mong đợi là **200, 200, 50**. Các giá trị update count bên trong vẫn phụ thuộc driver; đừng suy luận một mục luôn tác động đúng một dòng.

### 4.3. `NamedParameterJdbcTemplate`: dễ đọc khi nhiều cột

~~~java
// Mảnh method đặt trong class đã có field NamedParameterJdbcTemplate named.
org.springframework.jdbc.core.namedparam.SqlParameterSource[] params =
        changes.stream()
                .map(item -> new org.springframework.jdbc.core.namedparam.MapSqlParameterSource()
                        .addValue("status", item.status())
                        .addValue("id", item.id()))
                .toArray(
                    org.springframework.jdbc.core.namedparam.SqlParameterSource[]::new);

int[] counts = named.batchUpdate(
        "UPDATE task SET status = :status WHERE id = :id",
        params);
~~~

Tham số tên giúp giảm nhầm thứ tự ở SQL có nhiều trường. Có thể dùng `SqlParameterSourceUtils.createBatch(...)` khi bean/map có tên trường tương ứng. Khi bind `null` khó suy ra kiểu, cân nhắc `MapSqlParameterSource.addValue(name, value, sqlType)` hoặc `PreparedStatement.setNull(index, sqlType)` để tránh lỗi kiểu dữ liệu/phát sinh metadata query không cần thiết.

### 4.4. INSERT và DELETE cũng dùng batch được

Chỉ cần cấu trúc SQL giống nhau giữa các phần tử:

~~~sql
INSERT INTO task (id, status) VALUES (?, ?)
DELETE FROM task WHERE id = ?
~~~

Những lệnh có cấu trúc SQL khác nhau (khác bảng, số cột, biểu thức) không thể gom vào **cùng một PreparedStatement batch** theo mẫu trên. Có thể phân loại theo mẫu SQL rồi batch riêng từng nhóm.

## 5. Transaction: batch không đồng nghĩa atomic

**Batch là cách gửi/thực thi lệnh; transaction là ranh giới commit/rollback.** Hai cơ chế giải quyết hai vấn đề khác nhau.

- **Có `@Transactional` đúng ranh giới:** các batch trong method tham gia cùng transaction trên DataSource hỗ trợ transaction; khi một `DataAccessException` không bị nuốt và thoát ra ngoài, cấu hình Spring mặc định rollback các thay đổi chưa commit trong transaction.
- **Không có transaction bao quanh:** tùy cấu hình connection/autocommit và driver, một số mục hoặc nhóm có thể đã commit trước khi nhóm khác lỗi.
- **Bắt lỗi rồi không ném lại:** transaction có thể tiếp tục và commit phần thành công nếu không bị đánh dấu rollback; hãy chủ động quyết định chính sách xử lý.
- **Checked exception:** mặc định `@Transactional` rollback khi gặp `RuntimeException` hoặc `Error`, không tự động với checked exception; có thể cấu hình `rollbackFor` khi nghiệp vụ đòi hỏi.
- **Gọi nội bộ trong cùng bean:** `this.updateStatuses(...)` thường không đi qua proxy của Spring, nên `@Transactional` có thể không được áp dụng. Hãy gọi qua bean/service khác hoặc thiết kế lại ranh giới.

Giả sử 2.500 dòng được chia thành 25 batch, cùng thực thi trong **một** method `@Transactional`: đó có thể vẫn là **một transaction**, không phải 25 transaction. Ngược lại, tạo 25 transaction riêng giúp giới hạn thời gian giữ lock nhưng không còn đảm bảo all-or-nothing cho 2.500 mục.

Nếu cần retry sau lỗi, cần xác định batch có thể đã commit hay chưa, dùng transaction phù hợp, và thiết kế thao tác idempotent (khóa định danh/upsert/điều kiện trạng thái) để không nhân đôi hiệu ứng ngoài ý muốn.

## 6. Hiểu update count và lỗi khi thực thi

JDBC trả về update count cho từng mục. Trong các phương thức Spring JDBC thường gặp, kết quả là `int[]` hoặc `int[][]` tùy overload.

| Giá trị count | Ý nghĩa |
| --- | --- |
| `0` | Không có dòng được cập nhật theo kết quả driver; với UPDATE theo id có thể id không tồn tại |
| Số dương | Số dòng ảnh hưởng mà driver báo cho mục đó |
| `Statement.SUCCESS_NO_INFO` = `-2` | Driver cho biết mục thành công nhưng không xác định số dòng |
| `Statement.EXECUTE_FAILED` = `-3` | Báo mục thất bại trong thông tin kết quả batch, nếu driver cung cấp |

`BatchUpdateException` từ JDBC có thể chứa mảng count của các mục đã xử lý; driver có thể dừng ngay hoặc xử lý tiếp sau mục lỗi. Spring JDBC thường chuyển lỗi SQL thành một `DataAccessException`. Do đó, **không dựa vào việc mảng kết quả luôn có đầy đủ count khi batch thất bại**.

Khi cần đảm bảo mọi id đều tồn tại, phải kiểm tra kết quả theo yêu cầu nghiệp vụ: số `0` có thể là lỗi logic; `-2` không thể dùng để kết luận chính xác số dòng. Với UPDATE có optimistic locking (chẳng hạn `WHERE id = ? AND version = ?`), count `0` có thể chỉ ra xung đột phiên bản.

Bắt và xử lý exception đúng tầng, ghi log **mã nhóm, số phần tử, id liên quan và nguyên nhân**, tránh ghi toàn bộ dữ liệu nhạy cảm. Một batch lỗi không mặc nhiên cho biết mục nào thất bại nếu driver không trả đủ thông tin; khi cần xác định có thể tái chạy trên tập con trong môi trường kiểm soát và theo chính sách transaction.

## 7. Chọn batch size theo dữ liệu và giới hạn hệ thống

Một batch không nên mặc định chứa toàn bộ một triệu bản ghi.

- Có thể bắt đầu đo với `batchSize` 100, 200, 500 hoặc 1.000; **đây là các giá trị thử nghiệm**, không phải cấu hình tối ưu phổ quát.
- Batch nhỏ: nhiều lần `executeBatch()`, overhead cao hơn nhưng bộ nhớ, kích thước request, thời gian giữ tài nguyên thấp hơn.
- Batch lớn: ít lần gọi hơn, nhưng có thể tăng bộ nhớ, thời gian lock/transaction, kích thước thông điệp, độ trễ khi lỗi và nguy cơ chạm giới hạn driver/database.
- Đối với dữ liệu lớn/streaming, đọc/chuyển đổi theo phần, batch từng nhóm; không tải toàn bộ dữ liệu vào RAM chỉ để lập batch.
- Cần xem xét giới hạn số tham số, packet/request, timeout, log/replication và khả năng DB xử lý đồng thời. Giới hạn cho một lệnh `INSERT` nhiều VALUES không nhất thiết giống giới hạn cho một `PreparedStatement` batch.
- Trong môi trường có nhiều request đồng thời, tính cả số connection, lock contention và tải chung của DB; tăng batch size riêng lẻ không chắc giúp throughput hệ thống.

Quy trình chỉnh kích thước hợp lý: giữ nguyên dataset và transaction semantics, chạy thử nhiều kích thước, đo p50/p95/p99 latency, rows/second, số lần gửi lệnh, CPU/I/O của DB, lock wait và lỗi. Chọn điểm cân bằng **thông lượng, thời gian phản hồi, bộ nhớ và độ ổn định** thay vì chỉ nhìn thời gian chạy của một lần import.

## 8. Spring Data JPA/Hibernate có tự batch khi `saveAll()` không?

**Không được mặc định hiểu `repository.saveAll(items)` là một SQL hoặc đã bật JDBC batch.** Với Spring Data JPA, cách triển khai `saveAll` thường duyệt phần tử và gọi `save` từng entity; Hibernate quyết định thời điểm flush và có gộp JDBC DML được không tùy cấu hình/entity/chiến lược tạo khóa.

Ví dụ cấu hình Hibernate qua Spring Boot:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

Tác dụng và giới hạn:

- `hibernate.jdbc.batch_size` cho phép Hibernate gom các DML tương tự vào JDBC batch khi phù hợp.
- Sắp xếp insert/update có thể giúp gom nhiều lệnh cùng cấu trúc hơn, nhưng cũng có chi phí và cần đo.
- Khi dùng chiến lược id `IDENTITY` cho INSERT, Hibernate thường không thể JDBC batch insert theo cách thông thường vì phải lấy id được sinh sau từng insert.
- Persistence context giữ các entity đang được quản lý; xử lý hàng rất lớn cần cân nhắc `flush()`/`clear()` theo từng nhóm, nhưng `clear()` detach entity và có thể làm thay đổi logic cascade/dirty checking.
- `saveAllAndFlush()` yêu cầu flush sau khi save, **không có nghĩa một câu SQL**; bulk JPQL `UPDATE`/`DELETE` và native SQL có semantics khác lifecycle/cascade của entity.

Với lượng lớn cập nhật đơn giản theo khóa mà không cần lifecycle ORM, Spring JDBC `batchUpdate` thường giúp kiểm soát SQL, batch size và count trực tiếp hơn. Nếu nghiệp vụ phụ thuộc entity graph, callback hoặc optimistic locking, xem xét JPA/Hibernate trước khi thay bằng SQL thuần.

## 9. Lỗi thiết kế phổ biến và cách sửa

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Gọi `jdbc.update` trong `for` rồi nghĩ `@Transactional` đã batch | Một transaction vẫn có nhiều lời gọi database | Dùng đúng `batchUpdate` |
| Đặt toàn bộ dữ liệu vào một batch khổng lồ | Tốn RAM, giữ lock lâu, lỗi khó cô lập | Chia nhóm và đo kích thước phù hợp |
| Ghép SQL bằng nối chuỗi dữ liệu | Nguy cơ SQL injection, khó tái sử dụng statement | PreparedStatement với bind parameter |
| Tin rằng mọi update count đều bằng `1` | Bỏ sót id không tồn tại hoặc driver trả `-2` | Kiểm tra `0`, `-2` theo yêu cầu nghiệp vụ |
| Nuốt exception trong `@Transactional` | Có thể commit dữ liệu dở dang | Để lỗi lan ra hoặc chủ động đánh dấu rollback |
| Lạm dụng nhiều giao dịch nhỏ trong import cần atomic | Dữ liệu có thể commit một phần | Xác định rõ transaction boundary |
| Kết luận batch tăng tốc mà không đo | Tối ưu ảo nếu bottleneck là index, lock hay I/O | Benchmark với dữ liệu, driver và DB thực tế |
| Nghĩ `saveAll` là batch JDBC | Hiệu năng thấp hơn kỳ vọng | Cấu hình và quan sát Hibernate/JDBC thực tế |

## 10. Quy trình áp dụng trong một ứng dụng thực tế

1. **Xác định công việc lặp lại:** cùng mẫu INSERT/UPDATE/DELETE, khác tham số; kiểm tra có SQL set-based đơn giản hơn không.
2. **Thiết kế đầu vào:** validate id/dữ liệu, tránh thao tác trùng ngoài ý muốn, chọn thứ tự cập nhật phù hợp; nếu có điều kiện version, kiểm tra optimistic locking.
3. **Chọn API:** `JdbcTemplate.batchUpdate` khi cần SQL và batch size rõ ràng; `NamedParameterJdbcTemplate` khi nhiều tên tham số; Hibernate batching nếu dùng entity lifecycle.
4. **Đặt ranh giới transaction:** một transaction cho cả nghiệp vụ cần atomic; chia transaction theo nhóm nếu chấp nhận partial commit và có cơ chế resume/retry.
5. **Thực thi và xác minh:** xử lý `DataAccessException`, xem update counts, kiểm tra số dòng sau thao tác, theo dõi log/metric; tách success/no-info/failure.
6. **Đo trước–sau:** cùng data volume, chỉ số và transaction semantics; quan sát round trip thực tế bằng driver/proxy/DB metrics khi cần, thay vì suy từ số nhóm API.

### Bài tập tự kiểm tra

1. Có 10.500 thao tác và `batchSize = 300`. Có **35 nhóm** theo cách chia trên; kết luận này **không** bảo đảm 35 round trip vật lý. Nếu thay `batchSize = 400`, số nhóm là **27** (26 nhóm đủ 400 và nhóm cuối 100).
2. Có 200 UPDATE nhưng 3 id không tồn tại. Nếu nghiệp vụ yêu cầu tất cả id phải được cập nhật, chỉ thực thi thành công chưa đủ: phải xem update count (`0` nếu driver báo được), hoặc xác minh hậu điều kiện; đừng coi `-2` là một dòng.
3. Một service gọi `saveAll(entities)` nhưng log vẫn hiện từng INSERT. Hãy kiểm tra `hibernate.jdbc.batch_size`, chiến lược sinh id, thứ tự statement, flush và việc dùng transaction thay vì mặc định tăng batch size vô hạn.
4. Một batch thứ ba gặp lỗi sau hai batch đã thành công. Kết quả cuối cùng phụ thuộc **transaction boundary và rollback**, không đơn thuần phụ thuộc `batchSize`.

## 11. Ghi nhớ

Batch giảm chi phí trao đổi khi nhiều thao tác có cùng SQL và thay đổi tham số. Để dùng đúng trong Spring Data Access, hãy phân biệt **JDBC batch**, **SQL set-based**, **transaction** và **ORM flush**. Thiết kế batch size theo tải thật, xử lý update count/exception đúng ngữ nghĩa và kiểm chứng bằng đo đạc trên driver/database của hệ thống.

**Tài liệu chính thức:**

- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html)
- [Spring Framework — Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Hibernate ORM — Batching](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#batch)
- [Spring Data JPA — SimpleJpaRepository.saveAll](https://github.com/spring-projects/spring-data-jpa/blob/main/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/support/SimpleJpaRepository.java)
