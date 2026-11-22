# Đo chi phí flush, dirty checking và cập nhật dư thừa trong Spring Data JPA

## 1. Mục tiêu và mô hình chi phí

Khi tối ưu một ứng dụng dùng **Spring Data JPA + Hibernate**, cần phân biệt ba câu hỏi:

1. **Hibernate mất bao nhiêu công để kiểm tra thay đổi?** Đây là phần *dirty checking* trên các entity đang được quản lý trong *persistence context*.
2. **Một lần `flush()` mất bao lâu?** Flush đồng bộ các thay đổi đang chờ sang SQL theo thứ tự thích hợp. Một lần flush có thể không phát sinh lệnh `UPDATE` nào.
3. **Database phải xử lý bao nhiêu cập nhật, kể cả cập nhật dư thừa?** SQL gửi đi có thể tạo chi phí network, parse/execute, locking, WAL/redo log, index maintenance, replication hoặc trigger.

Đừng đánh đồng `repository.save()`, `entityManager.flush()` và `COMMIT`:

| Thao tác | Tác dụng chính | Điều cần đo |
| --- | --- | --- |
| Sửa thuộc tính của entity *managed* | Thay đổi trạng thái trong bộ nhớ; Hibernate thường hoãn SQL đến flush | Chi phí dirty checking và số bản ghi thực sự thay đổi |
| `save(entity)` trong Spring Data JPA | Gọi `persist` hoặc `merge` theo cách xác định entity mới/cũ; không phải lệnh SQL `UPDATE` tức thì trong mọi trường hợp | SELECT/MERGE phát sinh, thời điểm SQL, entity có đang managed không |
| `flush()` | Đồng bộ các thao tác đang chờ với DB nhưng **chưa tự commit transaction** | Thời gian flush, số flush, số SQL và entity update |
| `saveAndFlush(...)` | Lưu rồi yêu cầu flush ngay trong transaction | Chi phí flush thêm, khả năng giảm hiệu quả batching |
| `commit` | Kết thúc transaction; thông thường sẽ flush các thay đổi còn chờ trước khi commit | Thời gian và kết quả giao dịch tổng thể |
| JPQL bulk `UPDATE` hoặc native `UPDATE` | Gửi SQL cập nhật trực tiếp, bỏ qua cơ chế dirty checking từng entity | DML thực chạy, khóa DB, số hàng, lệch dữ liệu trong persistence context |

**Nguyên tắc:** `flushCount > 0` không suy ra `UPDATE > 0`; ngược lại một JPQL bulk update có thể chạy SQL dù thống kê `entityUpdateCount` của Hibernate không tăng như khi cập nhật từng entity.

## 2. Hibernate dirty checking hoạt động thế nào?

Trong một transaction:

```text
SELECT account -> entity MANAGED trong persistence context
                        |
                        v
              đổi một hay nhiều field
                        |
                        v
            flush / auto-flush / commit
                        |
                        v
          Hibernate xác định trạng thái dirty
                  /                  \
              không dirty           dirty
                  |                    |
             không UPDATE          tạo SQL UPDATE
                                       |
                                  JDBC -> database
```

Với cách theo dõi thay đổi dựa trên *snapshot*, Hibernate giữ trạng thái đã nạp và so sánh với giá trị hiện tại khi flush. Hibernate cũng có các cơ chế theo dõi thay đổi được tăng cường bằng bytecode, vì thế không nên khẳng định mọi phiên bản/cấu hình đều so sánh mọi thuộc tính theo cách giống nhau. Phần việc liên quan đến dirty checking phụ thuộc số lượng entity managed, số thuộc tính, kiểu dữ liệu, collection và cấu hình enhancement.

Điểm cần nhớ:

- Entity `new`, `managed`, `detached` và `removed` có quy tắc riêng. Dirty checking tự động chủ yếu áp dụng cho entity **managed** trong persistence context hiện tại. Thay đổi đối tượng detached không tự sinh SQL; `merge` có quy tắc và chi phí riêng.
- Đối với thuộc tính đơn giản, đặt lại **cùng giá trị** thường không tạo `UPDATE` khi flush. Nhưng setter, custom type, callback, collection hoặc cơ chế theo dõi thay đổi có thể ảnh hưởng hành vi thực tế; cần xác nhận bằng SQL.
- Nếu một entity thực sự dirty, Hibernate mặc định có thể sinh `UPDATE` chứa nhiều cột có thể cập nhật, kể cả cột không thay đổi. `@DynamicUpdate` có thể giới hạn cột trong `SET`, nhưng tăng số dạng SQL và có thể giảm khả năng reuse/batching; chỉ áp dụng sau khi đo.
- Dirty checking và flush không phải một lần truy vấn theo từng entity. Hibernate có thể kiểm tra nhiều entity trong bộ nhớ rồi chỉ phát SQL cho một số ít entity. Ngược lại, SQL native/JPQL bulk có thể cập nhật mà không đi qua cơ chế dirty checking của entity.
- `@Version` phục vụ optimistic locking khi ORM cập nhật entity; bulk JPQL/native update thường **không tự tăng version** và không tự đồng bộ các entity đã load, nên phải thiết kế riêng nếu dùng bulk DML.

**Ví dụ:** đã load 1.000 entity, đổi một tên, gọi `flush()`. Thống kê có thể ghi nhận một lần flush, một entity update, nhưng Hibernate vẫn phải quản lý tập entity đã load. Muốn biết thời gian CPU do dirty checking, phải đo đoạn flush có kiểm soát và/hoặc profiler; đếm SQL đơn thuần không đủ.

## 3. Xác định metric trước khi tối ưu

| Chỉ số | Cách thu thập | Ý nghĩa và giới hạn |
| --- | --- | --- |
| Số lần flush | `Statistics.getFlushCount()` | Đếm sự kiện full flush của Hibernate; **không** đo số SQL hay thời gian mỗi lần |
| Số entity update | `Statistics.getEntityUpdateCount()` | Đếm update được Hibernate xử lý qua cơ chế entity; **không bao quát mọi JPQL/native bulk DML** |
| Số prepared statement | `Statistics.getPrepareStatementCount()` | Lần chuẩn bị statement theo thống kê Hibernate; gồm cả SELECT/INSERT/UPDATE, không tương đương số network round-trip |
| Thời gian của `entityManager.flush()` | `System.nanoTime()` quanh đoạn flush trong test | Gồm dirty checking, tạo/bind SQL, DB I/O nếu có; **không thuần CPU dirty checking** |
| Số SQL `UPDATE`, tổng thời gian SQL | SQL log, JDBC instrumentation, APM, metric phía DB | Xác nhận SQL thực thi; log nhiều ảnh hưởng hiệu năng, metric có thể tính theo lần batch/statement khác nhau |
| DB load: lock, I/O, WAL, index | PostgreSQL `pg_stat_statements`, `EXPLAIN (ANALYZE, BUFFERS)` khi phù hợp, DB monitoring | Cho thấy chi phí phía database; cần scope và quyền truy cập thích hợp |
| Allocations, stack CPU, GC | Java Flight Recorder (JFR) hoặc profiler | Giúp định vị chi phí Java/Hibernate; phải quan sát trên workload đại diện |

`org.hibernate.stat.Statistics` thuộc **SessionFactory**, tức các counter là tổng hợp cho toàn factory, không riêng một request. Trong thử nghiệm nên chạy tuần tự, không có traffic khác, lấy hiệu số trước–sau; **không gọi `statistics.clear()` trên hệ thống nhiều người dùng** chỉ để lấy số liệu cho một yêu cầu. Với production, dùng metrics có nhãn giao dịch/tác vụ, JDBC telemetry và các phép đo riêng phía database.

Có thể bật thống kê Hibernate để làm thí nghiệm:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
# Bật SQL log chỉ khi cần kiểm chứng trong môi trường thử nghiệm:
logging.level.org.hibernate.SQL=DEBUG
# Hibernate 6 - xem bind values khi cần, lưu ý dữ liệu nhạy cảm:
# logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

Thống kê và log đều có overhead; không dùng kết quả benchmark có bật log dày đặc để suy ra latency production.

## 4. Thí nghiệm có thể chạy: cùng giá trị, giá trị mới và bulk update dư thừa

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate 6 và H2**. Trong một project Spring Boot đã cấu hình plugin, thêm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
```

File `src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:flush_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
# Dùng trong phòng lab, không giữ create-drop với database thật.
```

### 4.1. Entity có optimistic version

File `src/main/java/com/example/flushlab/DemoAccount.java`:

```java
package com.example.flushlab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "demo_account")
public class DemoAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    @Column(nullable = false, length = 120)
    private String displayName;

    protected DemoAccount() { }

    public DemoAccount(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

### 4.2. Repository có bulk update cố ý dư thừa

File `src/main/java/com/example/flushlab/DemoAccountRepository.java`:

```java
package com.example.flushlab;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DemoAccountRepository
        extends JpaRepository<DemoAccount, Long> {

    @Modifying
    @Query("""
        update DemoAccount a
           set a.displayName = a.displayName
         where a.id = :id
        """)
    int redundantBulkUpdate(@Param("id") Long id);
}
```

Lệnh bulk ở trên **cố ý** đặt cột bằng chính giá trị cũ để minh họa sự khác biệt: nó vẫn là một câu SQL `UPDATE` được gửi đến database nếu hàng khớp điều kiện. DB có thể tối ưu vài công việc nội bộ, nhưng không được giả định câu lệnh này miễn phí. Thống kê `getEntityUpdateCount()` cũng không phản ánh đầy đủ lệnh bulk này.

### 4.3. Service: mỗi kịch bản là một transaction thật

File `src/main/java/com/example/flushlab/AccountScenarioService.java`:

```java
package com.example.flushlab;

import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountScenarioService {
    private final DemoAccountRepository repository;
    private final EntityManager entityManager;

    public AccountScenarioService(
            DemoAccountRepository repository,
            EntityManager entityManager) {
        this.repository = repository;
        this.entityManager = entityManager;
    }

    @Transactional
    public Long seed() {
        return repository.saveAndFlush(new DemoAccount("An")).getId();
    }

    @Transactional
    public void assignSameValue(Long id) {
        DemoAccount account = repository.findById(id).orElseThrow();
        account.setDisplayName(account.getDisplayName());
        entityManager.flush();
    }

    @Transactional
    public void assignNewValue(Long id) {
        DemoAccount account = repository.findById(id).orElseThrow();
        account.setDisplayName("Binh");
        entityManager.flush();
    }

    @Transactional
    public void executeRedundantBulkUpdate(Long id) {
        int affected = repository.redundantBulkUpdate(id);
        if (affected != 1) {
            throw new IllegalStateException("Unexpected affected row count");
        }
    }
}
```

Các method `@Transactional` được gọi qua một Spring bean khác, nên transaction proxy có hiệu lực. Không dùng `this.assignNewValue(...)` từ cùng class làm bằng chứng hoạt động của `@Transactional`.

Ở `assignSameValue`, đơn giản gán lại đúng tên cũ; trên mapping này, kỳ vọng không có entity update. Ở `assignNewValue`, entity dirty và Hibernate sinh UPDATE tại flush. Ở `executeRedundantBulkUpdate`, JPQL trực tiếp phát DML ngay khi `executeUpdate` chạy qua repository; cơ chế dirty checking entity không phải nơi quyết định có UPDATE hay không.

### 4.4. Đo hiệu số thống kê và latency

File `src/main/java/com/example/flushlab/FlushMetricsRunner.java`:

```java
package com.example.flushlab;

import java.util.Locale;
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class FlushMetricsRunner implements CommandLineRunner {
    private final AccountScenarioService scenarios;
    private final Statistics statistics;

    public FlushMetricsRunner(
            AccountScenarioService scenarios,
            EntityManagerFactory entityManagerFactory) {
        this.scenarios = scenarios;
        this.statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();
    }

    @Override
    public void run(String... args) {
        Long id = scenarios.seed(); // Nằm ngoài cả ba mẫu đo.
        measure("same-value", () -> scenarios.assignSameValue(id));
        measure("changed-value", () -> scenarios.assignNewValue(id));
        measure("bulk-same-value",
                () -> scenarios.executeRedundantBulkUpdate(id));
    }

    private void measure(String name, Runnable action) {
        long beforeFlush = statistics.getFlushCount();
        long beforeUpdates = statistics.getEntityUpdateCount();
        long beforeStatements = statistics.getPrepareStatementCount();

        long started = System.nanoTime();
        action.run(); // Trả về sau khi transaction hoàn tất.
        long elapsedNanos = System.nanoTime() - started;

        long flushes = statistics.getFlushCount() - beforeFlush;
        long updates = statistics.getEntityUpdateCount() - beforeUpdates;
        long statements =
                statistics.getPrepareStatementCount() - beforeStatements;

        System.out.printf(Locale.ROOT,
                "%s | ms=%.3f | flush=%d | entityUpdate=%d | prepared=%d%n",
                name, elapsedNanos / 1_000_000.0,
                flushes, updates, statements);
    }
}
```

File `src/main/java/com/example/flushlab/FlushLabApplication.java`:

```java
package com.example.flushlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlushLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(FlushLabApplication.class, args);
    }
}
```

Chạy từ thư mục dự án Spring Boot có Gradle wrapper:

```bash
./gradlew bootRun
```

Đối với Windows PowerShell, chạy `.\gradlew.bat bootRun`. Các file Java trên được viết cho cùng package `com.example.flushlab`. Bài thử độc lập khi được đặt vào project Spring Boot có các dependencies đã nêu; không phải chương trình Java SE chạy chỉ bằng `javac` mà không có Spring/Hibernate.

### 4.5. Cách đọc kết quả

Giá trị `ms` và `prepared` phụ thuộc máy, JDBC, transaction manager, Hibernate version, warmup và môi trường. **Không có một stdout cố định hợp lệ để chép vào tài liệu.** Kết quả nên kiểm tra theo quan hệ sau:

| Kịch bản | Entity dirty? | `entityUpdate` kỳ vọng | DML thực tế |
| --- | --- | --- | --- |
| `same-value` | Không, với trường `String` đơn giản và mapping này | 0 | SELECT để load; thường không có UPDATE |
| `changed-value` | Có | 1 | SELECT rồi UPDATE khi flush |
| `bulk-same-value` | Không đi qua dirty checking từng entity | Có thể 0 | SQL UPDATE trực tiếp vẫn được thực thi |

Đối chiếu SQL log để thấy `UPDATE` có thực sự xuất hiện. Lưu ý `prepared` bao gồm SELECT và những statement khác, `flush` còn phụ thuộc auto-flush/commit, nên **không áp đặt một con số flush hay prepared tuyệt đối** cho mọi môi trường.

Dùng ít nhất hai phép xác nhận độc lập: counter Hibernate và số SQL thực chạy/JDBC telemetry. Khi cần chi phí phía DB, thêm số hàng bị ảnh hưởng, latency lệnh SQL và DB metrics. Nếu chỉ nhìn `entityUpdate=0` ở bulk DML mà kết luận không có cập nhật là sai.

## 5. Đo riêng phần flush và ảnh hưởng của persistence context

Thời gian đo quanh toàn bộ `service.assignNewValue(id)` bao gồm mở transaction, SELECT, thao tác Java, flush, DB update và commit. Nếu mục tiêu là **chi phí flush**, đặt timer **ngay quanh `entityManager.flush()`**:

```java
// Đặt bên trong một method @Transactional thực sự:
DemoAccount account = entityManager.find(DemoAccount.class, id);
account.setDisplayName("Binh");

long started = System.nanoTime();
entityManager.flush();
long flushNanos = System.nanoTime() - started;
// Đưa flushNanos ra báo cáo sau khi transaction kết thúc thành công.
```

Đây vẫn là **thời gian flush tổng thể**, có thể bao gồm round-trip database. Để khảo sát riêng overhead kiểm tra entity không thay đổi, preload entity rồi chỉ đo flush:

```java
// Minh họa cho method @Transactional trong service:
public long measureCleanFlush(java.util.List<Long> ids) {
    for (Long id : ids) {
        entityManager.find(DemoAccount.class, id);
    }
    long started = System.nanoTime();
    entityManager.flush(); // Không chủ động đổi thuộc tính nào.
    return System.nanoTime() - started;
}
```

Đoạn thứ hai là **một phần method**, cần đặt trong bean service cùng `EntityManager` và chú thích `@Transactional` lên method. Danh sách ID phải chứa các dòng đã tồn tại. Việc load các entity được cố ý đặt ngoài khoảng đo; mỗi lần thử vẫn phải dùng transaction/persistence context mới để có điều kiện so sánh tương đồng.

Thiết kế phép đo theo nhóm `N = 0, 100, 1.000, 5.000` entity managed, lặp nhiều lần với warmup và trình tự thử được hoán đổi; thống kê median/p95 thay vì một số đơn lẻ. Trường hợp không có thay đổi, số entity update nên bằng 0, nhưng thời gian flush có thể thay đổi theo kích thước persistence context, cấu hình tracking và JVM. Dùng **JFR/profiler** xem thời gian CPU trong các stack liên quan `flush`/`dirtyCheck` nếu muốn quy kết chi phí cho Hibernate, thay vì lấy chênh lệch thời gian rồi gọi đó là “dirty-checking cost” một cách tuyệt đối.

Để phép đo đáng tin:

- **Tách warmup khỏi measurement** để tránh ảnh hưởng JIT, khởi tạo pool/metadata và cache lạnh.
- Dùng dữ liệu cùng kích thước, cùng index, isolation level, cùng cấu hình JDBC batch và cùng số lượng entity dirty.
- Tránh chạy benchmark cùng traffic thật; bộ đếm `Statistics` là toàn cục cho `SessionFactory`.
- Đo **flush**, **transaction end-to-end** và **SQL DB time** thành các thành phần riêng. Hiệu số giữa chúng chỉ là gợi ý, không phải một phép tách CPU hoàn hảo.
- Lặp có phân phối (median/p95), ghi JVM/DB version và settings; GC, connection pool, lock, disk cache và logging đều có thể làm lệch mẫu.
- Không so sánh `@Transactional(readOnly=true)` với transaction ghi để rút kết luận dirty checking: với một số tích hợp Spring/Hibernate, read-only thay đổi flush mode và chính sách tracking.

Nếu chỉ có vài bản ghi và chi phí đo thấp hơn nhiễu của JVM, kết luận phù hợp là “chưa có bằng chứng khác biệt có ý nghĩa”, không phải mặc định “tối ưu thành công”.

## 6. Các nguồn cập nhật dư thừa phổ biến

### 6.1. Gán cùng giá trị so với DML bắt buộc

```java
// Entity đã managed; nếu giá trị đơn giản không đổi,
// thông thường Hibernate không cần UPDATE:
account.setDisplayName(account.getDisplayName());

// Trái lại, JPQL bulk DML vẫn gửi UPDATE khi WHERE khớp:
repository.redundantBulkUpdate(account.getId());
```

Phân biệt cập nhật *thực sự dư thừa* với cập nhật có chủ đích (ví dụ ghi `last_seen_at`, bump version, tạo audit signal). DB có trigger, audit, replication và policy riêng; hai lệnh cùng giá trị chưa chắc có cùng hiệu ứng.

Với bulk update theo điều kiện, có thể tránh gửi UPDATE không cần thiết bằng mệnh đề điều kiện “giá trị khác”, nhưng cú pháp so sánh null-safe khác nhau giữa DB:

```sql
-- PostgreSQL; ví dụ một tham số :new_name:
UPDATE demo_account
   SET display_name = :new_name
 WHERE id = :id
   AND display_name IS DISTINCT FROM :new_name;
```

Nếu `rowCount=0`, có thể do hàng không tồn tại **hoặc** giá trị đã bằng nhau; nghiệp vụ phải phân biệt khi cần. Đối với các cột có version/optimistic locking, bulk UPDATE phải chứa điều kiện version và tăng version một cách có chủ đích, đồng thời kiểm tra row count; nó không tự có toàn bộ bảo vệ ORM.

### 6.2. `save()` và `saveAndFlush()` trong vòng lặp

```java
// Thường không cần thiết khi entity đã managed:
for (DemoAccount a : managedAccounts) {
    a.setDisplayName("New");
    repository.saveAndFlush(a); // Nhiều flush, cản trở gom lệnh.
}

// Trong cùng @Transactional, thường chỉ cần:
for (DemoAccount a : managedAccounts) {
    a.setDisplayName("New");
}
entityManager.flush(); // Flush có chủ đích một lần nếu thực sự cần.
```

Ví dụ là minh họa riêng, giả định `managedAccounts` là entity managed trong transaction; không phải phương thức độc lập. Hibernate sẽ tự flush khi transaction commit nếu cấu hình thông thường cho phép; có thể **không cần** gọi `flush()` thủ công ở cuối. Nếu cần xử lý dữ liệu lớn theo batch, cân nhắc flush + clear theo từng nhóm với giới hạn memory, nhưng phải quản lý entity detached, thứ tự xử lý và transaction boundary.

`saveAll(...)` không mặc nhiên tương đương SQL bulk insert/update. Với update, nó có thể gọi nhiều thao tác persist/merge. Hiệu quả JDBC batching cần cấu hình và kiểm chứng SQL/batch metrics thực tế, nhất là với IDENTITY generation và thứ tự statement.

### 6.3. Load quá nhiều entity vào persistence context

Đọc hàng chục nghìn entity managed chỉ để tính một aggregate có thể tạo overhead bộ nhớ, hydration, snapshot và các hoạt động flush không cần thiết. Nếu tác vụ chỉ xem dữ liệu, chọn DTO projection/aggregate query/stream có quản lý tài nguyên phù hợp. Nếu cần cập nhật tập lớn, đánh giá bulk SQL hoặc JDBC batching sau khi cân nhắc domain events, callback, optimistic locking và dữ liệu đang được quản lý.

Không dùng `entityManager.clear()` như một “tối ưu miễn phí”: nó detach toàn bộ entity trong context, có thể làm mất các thay đổi chưa flush và thay đổi hành vi phần code tiếp theo. Khi dùng batch, thường flush trước rồi clear theo chiến lược có kiểm soát.

### 6.4. Cập nhật toàn bộ cột khi chỉ đổi một trường

Với entity dirty, câu SQL UPDATE do Hibernate sinh có thể gán nhiều cột, kể cả chỉ một trường thay đổi. `@DynamicUpdate` có thể giảm dữ liệu ghi/chi phí một số trường hợp:

```java
import org.hibernate.annotations.DynamicUpdate;

@DynamicUpdate
@Entity
public class SomeEntity {
    // Các field, @Id và constructor hợp lệ...
}
```

Đây là **minh họa annotation**, không phải class độc lập có thể chạy. Quyết định dựa trên SQL đo được và tần suất thay đổi từng cột. `@DynamicUpdate` có thể tạo nhiều shape SQL, làm giảm statement reuse và batching; không áp dụng đại trà trước khi benchmark.

## 7. Flush mode, transaction và các tác dụng phụ của phép đo

Hibernate/JPA có các chế độ flush khác nhau. Ở `AUTO`, flush có thể xảy ra trước truy vấn cần dữ liệu nhất quán và trước commit, ngoài các lần gọi `flush()` tường minh. Chuyển sang `COMMIT` hay `MANUAL` có thể thay đổi lúc truy vấn thấy dữ liệu chưa flush; **không phải giải pháp mặc định** cho mọi vấn đề hiệu năng. Một lệnh `flush()` chỉ gửi SQL, vẫn có thể bị rollback cho đến khi transaction commit.

Đặc biệt:

1. `repository.findById` có thể dùng entity đang ở persistence context hoặc phát SELECT tùy trạng thái; đối chiếu SQL thay vì đếm lời gọi repository.
2. JPQL/criteria query có thể kích hoạt auto-flush; thời gian của “query chậm” có thể chứa chi phí flush. Nếu profiler chỉ nhìn thời gian query method, dễ quy sai chi phí.
3. Ghi SQL log hoặc bật thống kê chi tiết có thể tăng latency. Khi so sánh production, giữ cùng mức instrumentation giữa hai phương án.
4. Một bulk update bypass persistence context; nếu entity cùng hàng đã load, dữ liệu trong bộ nhớ có thể cũ. Sau bulk DML phải xác định ranh giới `flush`/`clear`/`refresh` phù hợp; đừng vô tình ghi đè dữ liệu mới bằng trạng thái cũ.
5. Đếm `UPDATE` thôi chưa thấy row lock, index churn, WAL, trigger hoặc replication delay. Với PostgreSQL, kết hợp metric database và `pg_stat_statements` (nếu extension được bật) để biết statement nào thật sự tốn công.

Đối với SQL cần phân tích, chạy `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường thử nghiệm có dữ liệu đại diện. `ANALYZE` **thực thi statement**, kể cả UPDATE, nên chuẩn bị transaction rollback hoặc bản sao dữ liệu; không dùng tùy tiện với lệnh ghi production.

## 8. Kế hoạch kiểm chứng tối ưu

| Ca kiểm thử | Cách thực hiện | Dấu hiệu đạt |
| --- | --- | --- |
| Gán đúng giá trị cũ | Load entity rồi set cùng giá trị, flush | Không có entity UPDATE không cần thiết; kết quả DB giữ nguyên |
| Sửa một giá trị | Load rồi sửa field, flush | Một thay đổi hợp lệ được commit; version đúng nếu có `@Version` |
| JPQL bulk update dư thừa | Chạy `SET col = col` | SQL UPDATE thật được ghi nhận dù entityUpdate statistic có thể bằng 0 |
| Flush nhiều entity sạch | Tăng `N` entity managed nhưng không đổi dữ liệu | Đo phân phối thời gian flush và CPU profile; không suy luận từ update count |
| Flush trong vòng lặp | So với thay đổi nhiều entity rồi flush có chủ đích | Đếm flush/SQL, latency, JDBC batch; đầu ra nghiệp vụ giống nhau |
| Dùng `@DynamicUpdate` | So với SQL mặc định trên cùng dữ liệu | Quan sát cột trong SET, số SQL shape, batching và latency, không chỉ byte SQL |
| JPQL bulk + entity đã load | Load entity, bulk update, đọc lại | Phát hiện stale persistence context; giải pháp refresh/clear rõ ràng |
| Đồng thời và optimistic lock | Hai transaction sửa cùng hàng | Không mất dữ liệu; xung đột version hoặc update có điều kiện được xử lý đúng |

Với các ca dựa trên transaction/SQL, dùng integration test trên **cùng loại DB với production** khi đánh giá locking, batching hay plan thực tế. H2 thuận tiện để chạy ví dụ minh họa API; H2 không đại diện đầy đủ hành vi lock, MVCC, planner và chi phí WAL của PostgreSQL/MySQL.

Một báo cáo benchmark tối thiểu nên có: tên kịch bản, số entity managed, số entity dirty, số transaction, số flush, số entity update, số SQL DML, thời gian flush median/p95, thời gian transaction median/p95, DB/driver/version và cấu hình thống kê. So sánh **giá trị nghiệp vụ sau chạy** trước khi chấp nhận một thay đổi hiệu năng.

## 9. Quy trình tối ưu dựa trên chứng cứ

1. **Lập baseline:** xác định request/job chậm, transaction boundary, số entity managed, SQL thực chạy và chi phí DB.
2. **Tìm nguyên nhân:** flush lặp quá nhiều, persistence context quá lớn, DML không có điều kiện, update nhiều cột hay truy vấn tự kích hoạt auto-flush.
3. **Chọn thay đổi nhỏ nhất:** bỏ `saveAndFlush` thừa; chỉ update khi giá trị khác; dùng projection cho tác vụ đọc; cân nhắc batch/`@DynamicUpdate` khi có chứng cứ.
4. **Đo lại với cùng workload:** latency, CPU, allocations, number of statements, row locks và DB resources. Không dựa vào một lần chạy hoặc mỗi `getEntityUpdateCount()`.
5. **Kiểm tra đúng nghiệp vụ:** optimistic locking, callbacks, event listeners, cache, audit và tính nhất quán sau bulk update.
6. **Triển khai có quan sát:** theo dõi chênh lệch trên workload thật, có cách hoàn tác khi số liệu hoặc hành vi xấu đi.

**Điểm cốt lõi:** `flush` là một mốc đồng bộ, *dirty checking* là quá trình xác định entity đã đổi, còn *redundant update* là tác động ghi không cần thiết vào DB. Muốn biết tối ưu có hiệu quả, phải **đo từng lớp đúng bằng metric thích hợp**, xác nhận SQL thực chạy và kiểm chứng bất biến nghiệp vụ; giảm số lời gọi `save()` hay `flush()` tự nó chưa chứng minh giảm chi phí database.
