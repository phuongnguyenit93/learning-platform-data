# Phạm vi khóa, chỉ mục và ảnh hưởng tới tải đồng thời

## 1. Tại sao một câu SQL có thể làm chậm nhiều request?

Giả sử ứng dụng Spring Framework đồng thời xử lý nhiều yêu cầu cập nhật đơn hàng, tồn kho hoặc số dư. Một request giữ khóa trên bản ghi mà request khác muốn sửa. Request thứ hai có thể phải **chờ khóa**, gặp **lock timeout**, trở thành deadlock victim hoặc được xử lý sau khi transaction thứ nhất hoàn tất.

Tác động của khóa đến concurrency phụ thuộc **ba thành phần gắn với nhau**:

1. **Phạm vi khóa (lock footprint):** thao tác SQL thực sự khóa những hàng, index records, khoảng chỉ mục hoặc đối tượng nào?
2. **Đường tìm dữ liệu:** `WHERE`, `JOIN`, `ORDER BY` và **index/query plan** làm database tìm đúng những hàng nào, quét nhiều hay ít?
3. **Thời gian giữ khóa (lock hold time / transaction lifetime):** khóa được lấy khi nào và chỉ giải phóng khi transaction commit/rollback hay có cơ chế khác? Trong thời gian ấy, có bao nhiêu transaction cần khóa xung đột?

Một index tốt có thể giúp định vị hàng nhanh, giảm thao tác quét và đôi khi **thu hẹp phạm vi index-record/gap locks**; nhưng một hot row vẫn có thể gây contention dù được truy vấn bằng primary key. Ngược lại, một transaction giữ khóa quá lâu do gọi HTTP bên trong `@Transactional` có thể làm mọi request liên quan phải đợi dù truy vấn đã tối ưu.

**Spring quy định transaction boundary, không tự quyết định mọi row/gap lock.** Các lock modes cụ thể do DBMS, storage engine, isolation, query plan và câu SQL quyết định. Không được áp dụng một câu như “thiếu index thì khóa toàn bảng” cho mọi DB.

### Mục tiêu bài học

- Phân biệt result set, scan range, lock footprint và thời gian transaction.
- Hiểu row/record lock, relation/table lock, intention lock, gap/next-key lock, MVCC và locking read.
- Phân tích tác động của primary key index, composite index, range predicate, non-sargable predicate và optimizer plan.
- Biết vì sao cùng một câu `SELECT ... FOR UPDATE` có thể có tác động khác nhau trên PostgreSQL, MySQL/InnoDB và H2.
- Chạy ví dụ **Java 17+, Spring Boot, Spring JDBC, H2** có hai transaction vật lý chồng lấn: inner thử sửa cùng row đang bị khóa sẽ timeout, inner sửa row khác sẽ commit được.
- Đọc dữ liệu sau transaction để chứng minh kết quả, thay vì chỉ nhìn exception.
- Chẩn đoán lock waits, deadlock, connection pool starvation và tối ưu tải đồng thời mà vẫn giữ đúng business invariant.

Bài thuộc nhóm **Khóa và đồng thời**, trong module **Spring Framework — transaction-management**, với đề bài trực tiếp là **“Phạm vi khóa, chỉ mục và ảnh hưởng tới tải đồng thời”**.

## 2. Bốn khái niệm không được đánh đồng

### 2.1. Result set — hàng mà SQL thực sự chọn/cập nhật

`SELECT ... WHERE id = 101` có thể trả một row. `UPDATE ... WHERE tenant_id = 42` có thể cập nhật hàng nghìn row. Đây là kết quả logic của điều kiện SQL, không tự cho biết các khóa mà engine đã đặt.

### 2.2. Scan range — dữ liệu engine phải duyệt để tìm kết quả

Nếu truy vấn lọc bằng `id` là primary key, B-tree index thường giúp tìm nhanh đến một hàng. Nếu lọc bằng cột không có index phù hợp, optimizer có thể quét nhiều record dù chỉ vài record match.

**Scan nhiều không mặc nhiên đồng nghĩa khóa tất cả row đã scan.** Trên một số locking scans của InnoDB, phạm vi index scan có ảnh hưởng đáng kể đến record/gap locks. PostgreSQL có semantics khác: với `SELECT ... FOR UPDATE` top-level, các row khóa liên quan những row được chọn, không phải quy tắc “mọi row đã scan đều bị khóa”.

### 2.3. Lock footprint — đối tượng bị khóa thật sự

Lock footprint bao gồm **đối tượng**, **loại khóa**, **mode**, **thời điểm lấy** và **thời điểm thả**. Database có thể vừa giữ khóa hàng vừa giữ khóa cấp bảng mang tính phối hợp.

| Khái niệm | Tác dụng khái quát | Cảnh báo |
| --- | --- | --- |
| Row/record lock | Ngăn thao tác ghi/locking read xung đột lên hàng | Không phải DB nào cũng có cùng mode |
| Table/relation lock | Điều phối thao tác trên relation, DDL, DML | Có lock cấp bảng không đồng nghĩa khóa độc quyền toàn bảng |
| Intention lock | Phối hợp nhiều cấp khóa trong một số DB như InnoDB | Không nhất thiết chặn đọc thông thường |
| Gap lock | Bảo vệ một khoảng trong thứ tự index | Có thể chặn INSERT dù chưa có row trong khoảng |
| Next-key lock | Gồm record lock và gap lock, thường được nhắc trong InnoDB | Phụ thuộc isolation và search condition |
| Predicate/serialization tracking | Phục vụ isolation cao hoặc phát hiện xung đột | Không phải lúc nào cũng hiển thị như row lock |
| Advisory lock | Application chủ động khóa theo khóa quy ước | Không tự có từ annotation `@Transactional` |

### 2.4. Lock hold time — thời gian giữ đến khi transaction kết thúc

Với các row locks thông thường trong transaction vật lý, **commit hoặc rollback** là mốc quan trọng giải phóng khóa, chứ không phải khi helper method Java return.

Ví dụ:

```text
BEGIN T
  UPDATE inventory id=10       <- bắt đầu giữ row lock
  validate các bước tiếp theo
  gọi HTTP 2 giây
  INSERT order_history
COMMIT T                       <- row lock được thả
```

Nếu một request khác cần cập nhật `inventory id=10` trong thời gian T mở, nó có thể đợi. Việc UPDATE đầu chạy chỉ 2 ms không quan trọng bằng thời điểm T giải phóng khóa.

## 3. MVCC: “đọc” không nhất thiết là “chờ write lock”

Nhiều database hiện đại dùng **Multi-Version Concurrency Control (MVCC)**. Một truy vấn đọc thông thường có thể đọc snapshot đã commit mà không chờ row lock do transaction khác giữ; một `UPDATE`, `DELETE` hoặc `SELECT ... FOR UPDATE` trên cùng hàng có thể phải chờ.

Ví dụ trên PostgreSQL dưới các điều kiện MVCC thông dụng:

```sql
-- Session A
BEGIN;
UPDATE inventory SET quantity = quantity - 1 WHERE id = 10;
-- Chưa COMMIT.

-- Session B, kết nối khác:
SELECT quantity FROM inventory WHERE id = 10;
-- Có thể đọc version đã commit trước đó, không cần chờ row lock UPDATE.

-- Session C, kết nối khác:
UPDATE inventory SET quantity = quantity - 1 WHERE id = 10;
-- Có thể phải đợi session A hoàn tất.
```

Đây là **ba phiên riêng được đặt chung để giải thích**, không chạy nguyên khối như một script duy nhất. Giá trị chính xác Session B đọc còn tùy isolation và snapshot; nó không nhìn thấy dữ liệu chưa commit của A chỉ vì B và A cùng dùng Spring.

Không viết các quy tắc tuyệt đối như “SELECT luôn khóa row” hoặc “SELECT không bao giờ lấy khóa”: nhiều DB lấy relation lock phục vụ phối hợp, và câu SQL có thể dùng `FOR SHARE`, `FOR UPDATE` hoặc isolation cao.

## 4. Primary key, unique index và phạm vi cập nhật

Giả sử bảng:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

Một thao tác cập nhật đúng item:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE id = 501 AND quantity >= 1;
```

Cách viết này có hai ý nghĩa:

- `id = 501` là điều kiện định vị bằng primary key, thường rất chọn lọc.
- `quantity >= 1` giữ điều kiện nghiệp vụ “không trừ khi hết hàng” trong **cùng một câu UPDATE**, tránh kiểu “đọc rồi update không điều kiện” vốn dễ bị lost update khi concurrency cao.

Trong Spring JDBC:

```java
int affected = jdbc.update(
    "UPDATE inventory SET quantity = quantity - 1 " +
    "WHERE id = ? AND quantity >= 1",
    inventoryId
);
if (affected != 1) {
    throw new IllegalStateException("Not found or out of stock");
}
```

Đây là **mảnh Java minh họa**, không phải class chạy độc lập; biến `jdbc` và `inventoryId` cần được cung cấp bởi service. Nếu đơn hàng cần thêm nhiều bước ghi atomic, method vẫn cần transaction boundary phù hợp.

**Tuy nhiên, index không giúp hai transaction sửa cùng hàng 501 song song mà không có tranh chấp.** Khi cả hai đều cần write lock trên cùng row, chúng có thể phải serialize, chờ hoặc xử lý conflict. Đây là *hot row*.

## 5. Composite index và range query

Giả sử tác vụ chọn các đơn hàng sẵn sàng xử lý:

```sql
SELECT id
FROM orders
WHERE tenant_id = 42
  AND status = 'READY'
ORDER BY created_at, id
LIMIT 20
FOR UPDATE;
```

Một composite index ứng viên:

```sql
CREATE INDEX idx_orders_tenant_status_time
ON orders(tenant_id, status, created_at, id);
```

Điều kiện equality `tenant_id` + `status` cùng ORDER BY có thể phù hợp với index này. Nếu bảng lớn, query plan được phép tìm nhanh các row ưu tiên thay vì quét và sắp xếp lượng dữ liệu rộng. Nhưng cần kiểm chứng bằng `EXPLAIN` trên dữ liệu thật:

- Optimizer **có thể chọn Seq Scan** trên bảng nhỏ dù đã tạo index.
- Một cột có cardinality thấp hoặc phân bố bị lệch có thể làm index kém chọn lọc.
- `LIMIT 20` không phải bảo đảm duy nhất 20 row/index entries được truy cập trong mọi execution plan.
- `FOR UPDATE` vẫn cần khóa các hàng theo semantics database. Index không biến locking read thành đọc không khóa.
- `OFFSET` có thể dẫn đến đọc/bỏ qua nhiều dòng; trên PostgreSQL, locking clause top-level có thể khóa cả row được bỏ qua bởi OFFSET.

### 5.1. Index cột đơn không luôn thay composite index

Index chỉ trên `tenant_id` có thể trả nhiều row chưa lọc `status`; index chỉ trên `created_at` không nhất thiết giúp điều kiện tenant/status. Composite index cần xét thứ tự prefix, equality/range, selectivity và ORDER BY theo DBMS.

Không tự chọn index bằng trực giác “đặt cột nhiều giá trị nhất lên đầu trong mọi trường hợp”. Workload gồm nhiều query khác nhau; thứ tự tốt cho một query có thể không tốt cho query khác.

### 5.2. Sargability: viết WHERE thuận lợi cho index

Ví dụ:

```sql
-- Có thể ngăn sử dụng B-tree index range seek thông thường:
WHERE DATE(updated_at) = DATE '2026-10-30'

-- Dạng range thường thuận lợi hơn cho index updated_at:
WHERE updated_at >= TIMESTAMP '2026-10-30 00:00:00'
  AND updated_at < TIMESTAMP '2026-10-31 00:00:00'
```

Đây là **mảnh SQL minh họa điều kiện**. Cần kiểm tra kiểu dữ liệu/time zone trước khi thay thế để giữ nguyên ý nghĩa. Một số DB có expression/functional index nên biểu thức ở dạng thứ nhất **không phải lúc nào** cũng gây scan.

Các dạng thường cần xem xét khác: ép kiểu không phù hợp, `LIKE '%keyword'` với B-tree thông thường, hàm lên cột trong WHERE, điều kiện OR rộng, JOIN không có index trên key. Đừng kết luận query chậm vì thiếu index nếu chưa xem plan.

### 5.3. Chỉ mục có chi phí

Mỗi index mới có thể khiến INSERT/DELETE hoặc UPDATE các cột liên quan tốn thêm công việc duy trì cấu trúc index. Nó tăng disk/memory overhead và có thể tạo điểm nóng ghi mới. Chỉ thêm index khi query performance, lock waits hoặc scan cost được chứng minh đáng cải thiện; ưu tiên loại bỏ index trùng lặp không cần thiết khi an toàn.

## 6. PostgreSQL so với MySQL/InnoDB: khác biệt phải ghi rõ

### 6.1. PostgreSQL: row lock thường áp dụng lên row được chọn

PostgreSQL `SELECT ... FOR UPDATE` khóa các row theo câu truy vấn, ngăn thao tác `UPDATE`/`DELETE`/locking read xung đột lên chính row đó cho đến khi transaction kết thúc. PostgreSQL cũng có relation-level lock modes để phối hợp truy cập bảng.

**Không được suy ra một `Seq Scan` khóa toàn bộ row đã scan.** Một query lọc ra vài row có thể đọc rất nhiều page vì thiếu index, nhưng việc nó khóa row nào còn phụ thuộc semantics câu SQL. Theo tài liệu PostgreSQL, với locking clause ở top-level, row được khóa liên quan row được trả về, với chi tiết về `JOIN`/`LIMIT`/`OFFSET` và row thay đổi trong lúc query.

Với isolation cao như `SERIALIZABLE`, PostgreSQL còn có cơ chế phát hiện xung đột và có thể báo serialization error; đừng ép suy luận bằng row lock đơn giản.

### 6.2. InnoDB: index range có thể quyết định phạm vi record/gap locks

Trong InnoDB, các locking reads, `UPDATE` và `DELETE` thường khóa các **index records được quét** theo execution plan; dưới isolation `REPEATABLE READ` (mặc định thường gặp của InnoDB), engine có thể dùng **next-key locks**: record lock + gap lock trên khoảng trước record.

Khác biệt:

```sql
-- Primary key equality: phạm vi tìm kiếm rất hẹp.
SELECT id FROM inventory WHERE id = 501 FOR UPDATE;

-- Range predicate: có thể quét một dải index.
SELECT id FROM inventory
WHERE tenant_id = 42 AND sku >= 'A'
FOR UPDATE;
```

Trên InnoDB dưới các điều kiện phù hợp, tìm bằng **unique index và unique search condition** thường chỉ cần index-record lock của row tìm được mà không có gap lock trước nó; một range search có thể có next-key locks trải trên index range, khiến INSERT vào khoảng cũng bị chặn. Nếu thiếu index phù hợp, locking scan có thể khóa rất nhiều entries.

Tuy nhiên, dưới `READ COMMITTED`, InnoDB thay đổi cách giữ gap/record locks: gap locks cho nhiều search/index scans được giảm hoặc tắt, ngoại trừ những trường hợp như foreign-key hoặc duplicate-key checks. Bản chất lock còn phụ thuộc optimizer plan và câu SQL cụ thể. Không áp dụng nguyên xi quy tắc này cho PostgreSQL hoặc H2.

### 6.3. Vì sao “index làm hẹp khóa” là một nhận định có điều kiện?

| Đặc điểm | PostgreSQL | MySQL/InnoDB |
| --- | --- | --- |
| Tìm đúng row bằng unique index | Thường nhanh hơn so với scan lớn | Có thể giảm scanned index records và lock range |
| Quét rộng do thiếu index | Có thể tăng thời gian query và thời gian giữ transaction | Có thể tăng cả scan work lẫn record/gap locks của locking statements |
| Locking range scan | Row locking theo semantics PostgreSQL; không đồng nhất với toàn bộ scan | Next-key/gap locking có thể quan trọng, tùy isolation |
| Có index nhưng tất cả request sửa cùng hot row | Vẫn tranh chấp | Vẫn tranh chấp |
| Optimizer không chọn index | Scan work có thể vẫn cao | Locking scan có thể vẫn rộng |
| Câu SELECT thông thường dưới MVCC | Không giống `FOR UPDATE` | Consistent read cũng khác locking read |

Khi đưa ra kết luận chính thức cho một hệ thống, cần ghi **DB engine, version, isolation, câu SQL, các index và EXPLAIN**. Không được chỉ dựa vào tên `@Transactional` hay một mô phỏng H2.

## 7. Chạy demo Java 17+: cùng hàng sẽ chờ, hàng khác có thể commit

Để hiểu khóa ở mức transaction, ta dựng ứng dụng **Spring Boot 3.3.13 + Spring JDBC + H2 in-memory** có một outer transaction cập nhật row `id=1`. Trong khi outer chưa commit, hai inner transactions `REQUIRES_NEW` lần lượt:

1. Cố UPDATE **cùng row id=1** — cần khóa mà outer vẫn giữ, H2 báo lock timeout.
2. UPDATE **row id=2** — không có tranh chấp row id=1 và có thể commit riêng.

Outer sau đó ném `IllegalStateException`, Spring rollback thay đổi của row 1; row 2 đã commit bởi transaction khác vẫn còn. Demo có **hai physical transactions chồng lấn thời gian** dù các lời gọi Java chạy tuần tự trong một thread: `REQUIRES_NEW` suspend outer, lấy connection khác, mở transaction mới; việc suspend outer không nhả khóa DB của outer.

Đây là thử nghiệm **row contention** trên H2, **không** phải kiểm chứng next-key/gap locks của InnoDB hoặc row-lock implementation của PostgreSQL.

### 7.1. Cấu trúc project

```text
lock-footprint-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/locks/
    │   ├── LockApplication.java
    │   ├── OuterService.java
    │   └── InnerService.java
    └── resources/
        ├── application.properties
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'lock-footprint-demo'
```

**`build.gradle`**

```groovy
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

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    runtimeOnly 'com.h2database:h2'
}
```

**`src/main/resources/application.properties`**

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:footprint;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=300
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=4
spring.sql.init.mode=always
```

H2 `LOCK_TIMEOUT=300` đặt thời gian chờ lock theo mili giây, chỉ để ví dụ nhanh. Pool 4 connection đủ cho demo **một call stack tuần tự** nơi outer giữ một connection và inner cần connection riêng; không phải cấu hình khuyến nghị cho production.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE item (
    id INT PRIMARY KEY,
    qty INT NOT NULL
);

INSERT INTO item(id, qty) VALUES (1, 10);
INSERT INTO item(id, qty) VALUES (2, 10);
```

`id` là primary key được index. Hai row không có foreign key/trigger để tác động lẫn nhau; việc update id2 thành công nhằm chứng minh nó không phải chờ row lock id1 trong điều kiện demo.

### 7.2. InnerService — các transaction REQUIRES_NEW

**`src/main/java/demo/locks/InnerService.java`**

```java
package demo.locks;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void sameRow() {
        jdbc.update(
            "UPDATE item SET qty = qty + 1 WHERE id = ?",
            1
        );
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void otherRow() {
        jdbc.update(
            "UPDATE item SET qty = qty + 1 WHERE id = ?",
            2
        );
    }
}
```

Mỗi method public non-final được transaction interceptor áp dụng khi outer gọi qua injected Spring bean. `REQUIRES_NEW` tạo transaction vật lý riêng; nếu outer đang active thì resource context của nó tạm suspend, không phải commit.

### 7.3. OuterService — giữ khóa, thử tranh chấp và rollback

**`src/main/java/demo/locks/OuterService.java`**

```java
package demo.locks;

import java.sql.SQLException;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void compete() {
        // Outer T1 sửa id=1 và giữ row lock cho tới khi T1 kết thúc.
        jdbc.update(
            "UPDATE item SET qty = qty + 1 WHERE id = ?",
            1
        );

        boolean timedOut = false;
        try {
            // T2 mới cần cùng hàng mà T1 đang khóa.
            inner.sameRow();
        } catch (DataAccessException ex) {
            if (!isH2Timeout(ex)) {
                throw ex;
            }
            timedOut = true;
        }

        if (!timedOut) {
            throw new IllegalStateException(
                "Expected lock timeout on row 1");
        }
        System.out.println("sameRowLockTimeout=true");

        // T3 mới sửa hàng 2 và có thể commit riêng.
        inner.otherRow();

        // Transaction T1 rollback; transaction T3 đã commit không bị undo.
        throw new IllegalStateException("outer rolled back");
    }

    private static boolean isH2Timeout(Throwable error) {
        Throwable t = error;
        while (t != null) {
            if (t instanceof SQLException sql
                    && sql.getErrorCode() == 50200) {
                return true;
            }
            t = t.getCause();
        }
        return false;
    }
}
```

H2 sử dụng mã vendor `50200` cho lock timeout. Code chỉ xác nhận đúng lỗi chờ khóa mong đợi; nếu root cause khác, nó ném lại để không báo thử nghiệm thành công giả. Mỗi database có SQLState/vendor codes khác, nên **không** dùng `50200` làm retry rule chung của Spring.

**Cơ chế:** T1 giữ write lock row 1. T2 `REQUIRES_NEW` mở connection khác rồi cố UPDATE row 1, phải đợi T1, nhưng T1 đang bị suspend và không thể giải phóng khóa cho đến khi T2 kết thúc. H2 báo lock timeout, T2 rollback. T3 mới UPDATE row 2, không tranh chấp row 1 nên commit. Outer cuối cùng ném runtime exception, khiến T1 rollback row 1.

### 7.4. LockApplication — đọc DB sau transaction boundary

**`src/main/java/demo/locks/LockApplication.java`**

```java
package demo.locks;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class LockApplication {
    public static void main(String[] args) {
        SpringApplication.run(LockApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner verify(OuterService outer, JdbcTemplate jdbc) {
        return args -> {
            try {
                outer.compete();
            } catch (IllegalStateException ex) {
                System.out.println("outerFailure=" + ex.getMessage());
            }

            Integer q1 = jdbc.queryForObject(
                "SELECT qty FROM item WHERE id=1", Integer.class
            );
            Integer q2 = jdbc.queryForObject(
                "SELECT qty FROM item WHERE id=2", Integer.class
            );
            System.out.println(
                "afterRollback id1=" + q1 + " id2=" + q2);
        };
    }
}
```

`@EnableTransactionManagement` bật Spring AOP transaction infrastructure. `OuterService` gọi một **bean khác** `InnerService` qua injection để method `REQUIRES_NEW` không bị self-invocation bypass. `transactionManager` và `JdbcTemplate` sử dụng cùng `DataSource`. Runner không có `@Transactional` nên đọc lại DB **sau khi mọi transaction trên call stack đã kết thúc**.

Không thêm `@Transactional` lên runner vì điều đó thay đổi precondition của thí nghiệm. Trong production, việc tự tạo transaction độc lập lồng nhau dưới outer row lock có thể gây pool starvation/self-contention; ví dụ này chỉ cố tình tạo tình huống ấy để học.

### 7.5. Lệnh chạy và output dự kiến

Cần JDK 17+ và Gradle 8.x tương thích. Trong thư mục `lock-footprint-demo`:

```bash
gradle bootRun
```

Nếu dự án có wrapper, chạy `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Không biên dịch file Java với classpath JDK thuần vì phụ thuộc Spring/H2.

Bỏ qua log Spring, Gradle và Hikari. Các dòng `System.out.println` dự kiến:

```text
sameRowLockTimeout=true
outerFailure=outer rolled back
afterRollback id1=10 id2=11
```

Bảng diễn giải:

| Thời điểm | Row 1 | Row 2 | Vì sao? |
| --- | --- | --- | --- |
| Khởi tạo `schema.sql` | 10 | 10 | Giá trị gốc |
| T1 UPDATE id1, chưa commit | 11 trong T1 | 10 | T1 giữ write lock id1 |
| T2 cố UPDATE id1 | T2 timeout | 10 | Cùng row bị T1 khóa |
| T3 UPDATE id2 | T1 chưa commit | **11 đã commit** | Row khác, transaction mới |
| T1 ném exception và rollback | **10** | **11** | Rollback T1 không undo T3 đã commit |

Đây là **stdout dự kiến theo code**, không phải log từ một lượt build đã thực thi. Trong H2 theo cấu hình, kết quả minh họa *row-level contention + thời điểm release*; không dùng để suy ra PostgreSQL hay InnoDB có cùng gap-lock semantics.

## 8. Kiểm chứng trên PostgreSQL bằng hai hoặc ba SQL sessions

Chạy trên một database thử nghiệm riêng, không sử dụng bảng production. Cần **nhiều kết nối** vì chúng ta giữ transaction A đang mở trong khi B và C thao tác.

### 8.1. Chuẩn bị dữ liệu test

```sql
CREATE TABLE lock_lab (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    qty INT NOT NULL
);

INSERT INTO lock_lab(id, tenant_id, status, qty)
VALUES (1, 42, 'READY', 10),
       (2, 42, 'READY', 10),
       (3, 99, 'READY', 10);

CREATE INDEX idx_lab_tenant_status_time
ON lock_lab(tenant_id, status, created_at, id);
```

### 8.2. Session A — giữ lock row 1

```sql
BEGIN;
SELECT id FROM lock_lab WHERE id = 1 FOR UPDATE;
-- Giữ transaction mở để kết nối khác có thể cạnh tranh.
```

### 8.3. Session B — yêu cầu cùng row

```sql
BEGIN;
SET LOCAL lock_timeout = '500ms';
UPDATE lock_lab SET qty = qty + 1 WHERE id = 1;
-- Có thể lỗi lock timeout do session A đang giữ row 1.
ROLLBACK;
```

Nếu PostgreSQL đã báo lỗi trong transaction, cần `ROLLBACK` để thoát trạng thái aborted. Các lệnh ở các section là **dành cho những session khác nhau**, không dán hết vào một connection rồi kỳ vọng có tranh chấp.

### 8.4. Session C — row 2 độc lập

```sql
BEGIN;
UPDATE lock_lab SET qty = qty + 1 WHERE id = 2;
COMMIT;
```

Session C thông thường có thể commit row 2 khi A giữ row 1, nếu không có constraint/lock khác. Kết thúc bằng việc quay về A và `ROLLBACK`:

```sql
ROLLBACK;
```

Sau đó dùng connection khác đọc lại:

```sql
SELECT id, qty
FROM lock_lab
WHERE id IN (1, 2)
ORDER BY id;
```

Trong điều kiện test đã mô tả, `id=1` vẫn 10, `id=2` là 11.

### 8.5. EXPLAIN để xem index thực sự được chọn

```sql
EXPLAIN
SELECT id
FROM lock_lab
WHERE tenant_id = 42 AND status = 'READY'
ORDER BY created_at, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

`EXPLAIN` mặc định trả estimated plan. Trên bảng demo nhỏ, optimizer có thể chọn `Seq Scan` dù có index; điều này không đủ để kết luận index vô ích trên bảng triệu hàng.

`EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy câu SQL**. Với `FOR UPDATE`, nó có thể lấy row locks; với `UPDATE/DELETE` nó thật sự thay đổi dữ liệu trừ khi được rollback trong transaction test phù hợp. Không dùng `EXPLAIN ANALYZE` câu ghi dữ liệu trên production khi chưa kiểm soát tác dụng phụ.

Để đánh giá index, tạo dataset đại diện, cập nhật statistics, so sánh estimated/actual rows, buffers, scan method và lock waits dưới concurrency thật.

## 9. Quan sát lock waits trên PostgreSQL/InnoDB

### 9.1. PostgreSQL

Câu truy vấn quan sát có thể sử dụng:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    now() - xact_start AS tx_age,
    LEFT(query, 120) AS query_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY xact_start NULLS LAST;
```

Quyền xem toàn bộ session phụ thuộc PostgreSQL roles. Text query có thể chứa thông tin nhạy cảm; chỉ dùng trong môi trường giám sát được kiểm soát.

Một bẫy quan trọng: **row-level locks của PostgreSQL thường không hiện thành từng dòng `tuple` trong `pg_locks`**, vì thông tin row lock được lưu trên disk. Session đang chờ row lock có thể hiện là đợi **transaction ID** của holder. Vì thế “không thấy row lock trong `pg_locks`” không chứng minh không có contention.

Kết hợp `pg_blocking_pids`, wait events, tuổi transaction, query plan, `pg_locks` và application traces thay vì chỉ nhìn một view.

### 9.2. MySQL/InnoDB

Các nguồn theo dõi:

- `performance_schema.data_locks`: thông tin lock của InnoDB khi được hỗ trợ và có quyền.
- `performance_schema.data_lock_waits`: waiter/blocker đang tranh chấp.
- `SHOW ENGINE INNODB STATUS`: thông tin transaction/deadlocks.

Ví dụ trên MySQL 8.x:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_NAME = 'orders';
```

Các trường có thể biểu diễn record/gap locks, index và lock status; kết quả phụ thuộc phiên bản và thiết lập. Cần bảo vệ metadata nhạy cảm; không suy luận tuyệt đối từ một cột `LOCK_DATA` mà bỏ qua index range.

### 9.3. Spring logs không thay DB evidence

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

Log có thể cho biết method nào đã được intercept và khi nào Spring mở/commit/rollback physical transaction. Nhưng nó **không thể liệt kê hết những index records DB đang khóa**. Để chẩn đoán đúng cần ghép cả SQL plan, DB wait/blocking và metric application.

## 10. Transaction propagation, isolation và khóa trong Spring

### 10.1. REQUIRED và thời điểm release

Nếu `OrderService.placeOrder()` mở T rồi gọi `InventoryService.reserve()` dùng `@Transactional(REQUIRED)` qua proxy, inner tham gia T. Inner return **không commit riêng** và thông thường không làm nhả row lock thuộc T. Outer tiếp tục xử lý đến commit/rollback, nên lock duration có thể dài hơn thời gian method inner chạy.

### 10.2. REQUIRES_NEW không tự giải quyết tranh chấp

`REQUIRES_NEW` suspend outer và tạo transaction vật lý riêng. Nhưng outer bị suspend **không nhả row lock**, inner có thể chờ khóa do outer giữ. Đồng thời inner cần thêm connection; khi nhiều request đồng thời đều giữ outer connection và chờ thêm inner connection, pool có thể bị starve.

Đổi inner sang `REQUIRES_NEW` chỉ hợp lệ khi business cho phép inner commit/rollback độc lập. Không dùng như “mẹo” tăng throughput rồi vô tình làm mất atomicity.

### 10.3. NESTED và savepoint

`Propagation.NESTED` có thể dùng savepoint trong cùng transaction vật lý nếu JDBC manager/driver hỗ trợ. Nó không giống `REQUIRES_NEW`. Rollback đến savepoint có thể hoàn tác phần thay đổi trong scope nested; khả năng thả locks và quy tắc cụ thể phụ thuộc DBMS. Outer rollback về sau vẫn hủy toàn bộ transaction vật lý.

### 10.4. Isolation thay đổi lock behavior theo DBMS

`@Transactional(isolation = Isolation.READ_COMMITTED)` có thể yêu cầu isolation cho một transaction **mới** khi manager hỗ trợ. Inner `REQUIRED` tham gia transaction ngoài thường không ghi đè isolation vật lý đã có. `SERIALIZABLE` có thể tăng bảo đảm chống anomaly nhưng cũng dẫn tới serialization errors/retries hoặc loại contention khác.

Cẩn thận: giảm isolation chỉ để ít lock mà bỏ qua lost update/phantom có thể vi phạm invariant nghiệp vụ. Chọn isolation, SQL và locking strategy bằng test trên DB thật.

### 10.5. Timeout ở các tầng khác nhau

- Database lock timeout: thời gian chờ lock trước khi DB báo lỗi; H2 dùng `LOCK_TIMEOUT`, PostgreSQL có `lock_timeout`, InnoDB có `innodb_lock_wait_timeout`.
- Statement timeout: có thể giới hạn thời gian một câu query.
- Spring transaction timeout: áp dụng ở transaction manager khi điều kiện phù hợp.
- Hikari connection acquisition timeout: thời gian chờ mượn connection, **không phải lock wait**.
- HTTP timeout: thời gian chờ upstream, có thể giữ transaction/locks không cần thiết nếu gọi bên trong T.

Không phân loại mọi timeout là deadlock, và không retry vô hạn khi nguyên nhân là hot row hoặc pool thiếu connection.

## 11. Những chiến lược tối ưu phù hợp

### 11.1. Rút ngắn transaction trước tiên

Đặt validation không cần DB, serialization, tính toán tốn CPU và network calls **ngoài đoạn đang giữ DB row locks** khi business cho phép. Không “tách transaction” tùy tiện nếu cần atomicity: dùng trạng thái trung gian, idempotency và outbox/compensation nếu workflow kéo dài qua hệ thống ngoài.

### 11.2. Giới hạn row và range bằng predicate hợp lý

Dùng primary key/unique key khi cập nhật một entity; bổ sung tenant predicate nếu cần multi-tenant safety. Với batch, dùng WHERE chính xác và `LIMIT`/chunking theo cú pháp DB, kiểm soát semantics partial completion. Thêm index dựa trên execution plan, không dựa vào cảm tính.

### 11.3. Lock theo thứ tự ổn định

Deadlock có thể xảy ra:

```text
T1 lock account A, chờ B
T2 lock account B, chờ A
                     ↓
                 deadlock
```

Với chuyển khoản, khóa tài khoản theo thứ tự ID ổn định khi được phép để giảm chu kỳ chờ. Không hứa loại bỏ mọi deadlock vì còn FK, triggers và khóa khác. Retry deadlock victim phải có giới hạn và idempotency.

### 11.4. Optimistic locking nếu tranh chấp hiếm

Ví dụ:

```sql
UPDATE account
SET balance = :balance,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Số row update bằng 0 cho biết có conflict hoặc row không tồn tại. Trong JPA có thể dùng `@Version`; application phải xử lý conflict/retry/response rõ ràng. Trên hot row, optimistic retries có thể rất tốn chi phí; không phải “không có lock nên luôn nhanh hơn”.

### 11.5. Pessimistic locking khi cần tuần tự hóa

Sử dụng `SELECT ... FOR UPDATE`, JPA `LockModeType.PESSIMISTIC_WRITE` hoặc câu UPDATE atomic. Lấy lock trong một transaction vật lý và chỉ giữ trong thời gian cần thiết. Cân nhắc timeout và lock scope; đừng mở pessimistic lock rồi chờ external gateway kéo dài.

### 11.6. Phân tán hot row khi có thể

Một account/counter bị sửa ở mọi request sẽ contention dù primary key lookup nhanh. Có thể thiết kế sharded counter, gom events, queue theo business key hoặc batch writes. Nhưng phải chứng minh được tính đúng đắn khi hợp nhất dữ liệu; thay đổi hot row design không chỉ là vấn đề hiệu suất.

## 12. Kiểm thử tải đồng thời đúng cách

Demo H2 cố ý tạo 2 physical transactions chồng lấn để dễ giải thích, không phải benchmark. Trên production-like DB hãy test:

| Phép thử | Thay đổi một biến | Đo điều gì? |
| --- | --- | --- |
| Cùng một id | Hai writers cạnh tranh same row | Wait, timeout, serialization |
| Hai id khác nhau | Không có constraint chung | Khả năng tiến triển song song |
| Có/không composite index | Giữ SQL, dataset, isolation | Plan, scanned rows, lock waits |
| READ COMMITTED vs REPEATABLE READ | Đổi isolation trên DB test | Gap/next-key/predicate behavior |
| Transaction ngắn vs dài | Tăng thời gian xử lý giữa UPDATE và COMMIT | Lock hold time, pool wait, P95/P99 |
| Hot row vs IDs phân tán | Đổi phân bố business keys | Throughput và contention |
| Inner REQUIRES_NEW đụng row outer | Giữ outer lock | Self-contention và pool needs |
| Retry với idempotency | Giả lập lock timeout/deadlock | Không nhân đôi side effects |

Ghi thống kê P50/P95/P99 latency, throughput thành công, error rate, retry count, DB CPU/IO, active/waiting connections và lock-wait duration. Query nhanh hơn trung bình nhưng P99 tăng vì hot row vẫn chưa phải tối ưu đúng.

### 12.1. Test Spring tự rollback có thể đánh lừa

Spring TestContext có thể tự tạo transaction quanh test method mang `@Transactional` rồi rollback cuối test. Khi đó service `REQUIRED` tham gia transaction của test; thời điểm commit/rollback và lock lifetime khác API thật. Để kiểm chứng, dùng integration test không bị một outer test transaction vô tình bao ngoài; gọi service thật qua proxy, đọc lại sau khi physical transaction kết thúc.

### 12.2. Self-invocation làm mất propagation mong đợi

Trong Spring proxy mode, `this.innerMethod()` trong cùng bean bypass transaction advice của inner. Nếu muốn thử `REQUIRES_NEW`, gọi bean khác được inject qua Spring proxy. Không dùng self-invocation rồi kết luận REQUIRES_NEW không có tác dụng.

### 12.3. Không nhầm read-your-writes với commit

Một transaction có thể đọc thấy row chính nó vừa UPDATE dù chưa commit. Test nên đọc lại từ bên ngoài transaction sau commit/rollback để chứng minh trạng thái bền vững, thay vì chỉ assert dữ liệu ngay trong method đang giữ lock.

## 13. Checklist điều tra API chậm vì khóa

Khi thấy timeout hoặc P99 cao, thu thập:

1. DB engine/version, transaction isolation và manager/resource thực tế.
2. SQL đầy đủ (sau khi loại dữ liệu nhạy cảm), điều kiện WHERE/JOIN và các params làm giảm selectivity.
3. Index hiện có, `EXPLAIN` và estimated/actual rows; query có dùng index hay quét rộng?
4. Có hot row, range locking, gap locking hoặc xung đột FK/trigger nào không?
5. Waiter/blocker sessions, transaction age, lock modes và row/index objects đang chờ.
6. Code Spring nào mở `@Transactional`, có gọi HTTP chậm trong T, có `REQUIRED`/`REQUIRES_NEW`/self-invocation không?
7. Connection pool active/waiting; có transaction giữ connection lâu không?
8. Timeout/SQLState/vendor code nào, có retry vô hạn hoặc không idempotent không?
9. Business invariant có cho phép batching, optimistic lock hoặc transaction tách riêng không?
10. Sau thay đổi, throughput/latency/lock wait và dữ liệu nghiệp vụ có được verify cùng nhau không?

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao UPDATE theo primary key vẫn có lock contention?

**Đáp án:** Index giảm chi phí định vị, không cho phép hai transaction cùng ghi một row xung đột mà không phối hợp; một transaction có thể phải chờ transaction kia kết thúc.

**Câu 2.** Thiếu index có đồng nghĩa PostgreSQL khóa mọi row đã quét không?

**Đáp án:** Không. Scan range và lock footprint là hai khái niệm khác. PostgreSQL row locking semantics khác InnoDB; phải xét statement/plan/isolation.

**Câu 3.** Vì sao một locking range scan trên InnoDB có thể chặn INSERT vào khoảng không có row trả về?

**Đáp án:** Dưới các điều kiện như REPEATABLE READ, next-key/gap locks có thể bảo vệ khoảng index được quét.

**Câu 4.** Inner REQUIRES_NEW có thể chờ chính row outer đang khóa không?

**Đáp án:** Có. Suspend outer không nhả khóa; inner transaction mới dùng connection khác và phải chờ lock cho tới khi timeout, như demo.

**Câu 5.** Vì sao `EXPLAIN ANALYZE` không nên thử vô tư với UPDATE trên dữ liệu thật?

**Đáp án:** Vì nó thực thi statement. Cần môi trường test hoặc transaction/rollback được kiểm soát.

**Câu 6.** Đã có index đúng, nhưng P99 latency vẫn cao. Cần xem gì?

**Đáp án:** Hot row, transaction duration, lock wait, DB pool occupancy, remote calls trong transaction và retry bursts.

**Câu 7.** `FOR UPDATE SKIP LOCKED` thích hợp với trường hợp nào?

**Đáp án:** Queue workers có cơ chế claim/lease/retry và chấp nhận bỏ qua tạm thời row đang bị khóa; không thích hợp cho mọi báo cáo cần xem toàn bộ dữ liệu.

**Câu 8.** Vì sao cần đọc DB sau transaction trong test?

**Đáp án:** Một transaction có thể nhìn thấy thay đổi chưa commit của chính nó. Chỉ sau commit/rollback mới biết dữ liệu có bền vững hay đã được hủy.

## 15. Tài liệu tham khảo chính thức

- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Transactional Annotations: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- PostgreSQL — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL — SELECT locking clauses: https://www.postgresql.org/docs/current/sql-select.html
- PostgreSQL — `pg_locks`: https://www.postgresql.org/docs/current/view-pg-locks.html
- MySQL 8.4 — InnoDB Locking: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html
- MySQL 8.4 — InnoDB Locks Set by Different Statements: https://dev.mysql.com/doc/refman/8.4/en/innodb-locks-set.html
- MySQL 8.4 — Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- H2 — Advanced (MVCC / lock timeout): https://h2database.github.io/html/advanced.html
- H2 — Commands (`FOR UPDATE` và `SET LOCK_TIMEOUT`): https://h2database.github.io/html/commands.html

**Ghi nhớ:** lock footprint phụ thuộc SQL/index và DB engine; lock hold time phụ thuộc ranh giới transaction thật. Để tăng tải đồng thời mà vẫn đúng, phải **kiểm tra query plan, lock waits và DB state**, rút ngắn transaction hợp lý, giảm scan range khi có ích và tránh mở `REQUIRES_NEW` trên những row outer vẫn đang giữ khóa.