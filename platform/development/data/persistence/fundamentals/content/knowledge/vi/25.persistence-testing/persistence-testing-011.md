# Kiểm thử migration và khả năng đọc dữ liệu phiên bản cũ

Một ứng dụng Java có thể chạy đúng trên database mới tạo nhưng thất bại khi triển khai lên hệ thống đã vận hành nhiều năm. Database production chứa dữ liệu do nhiều phiên bản chương trình ghi: những hàng thiếu trường mới, enum cũ, giá trị `NULL` từng hợp lệ, JSON theo schema cũ hoặc các bản ghi đã được backfill một phần. Migration có thể thực thi thành công nhưng làm mất nghĩa dữ liệu hoặc khiến chương trình cũ không còn đọc được trong lúc rolling deployment.

**Kiểm thử migration và khả năng đọc dữ liệu phiên bản cũ** là việc chứng minh rằng hệ thống có thể đi từ **một trạng thái dữ liệu/schema đã tồn tại** sang trạng thái mới, mà không phá bất biến nghiệp vụ, không mất bản ghi, không làm sai ngữ nghĩa và vẫn bảo đảm đường đọc/ghi của những phiên bản ứng dụng còn được hỗ trợ.

Bài thuộc chương **Kiểm thử lưu trữ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Nội dung nối kiến thức về Java/JDBC/JPA, thiết kế lược đồ, truy vấn, chỉ mục, giao dịch, cô lập, đồng thời, xử lý lỗi kết nối, tiến hóa schema, bảo mật backup và khả năng phục hồi. Trọng tâm không chỉ là chạy SQL migration mà là xây dựng **bằng chứng kiểm thử** để quyết định khi nào thay đổi được phép phát hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt kiểm thử schema mới trên database rỗng với kiểm thử nâng cấp trên dữ liệu lịch sử.
2. Xây dựng ma trận tương thích giữa schema, reader/writer, data format và application release.
3. Chuẩn bị fixture dữ liệu cũ với trường hợp biên, dữ liệu bất thường và trạng thái migration dở dang.
4. Thiết lập kiểm thử JUnit, JDBC, Flyway/Liquibase và PostgreSQL/Testcontainers cho migration versioned.
5. Xác nhận không chỉ DDL mà cả ràng buộc, foreign key, tổng tiền và ngữ nghĩa dữ liệu.
6. Thử backfill có idempotency, transaction, checkpoint và writer đồng thời.
7. Kiểm tra expand–migrate–contract trong rolling deployment.
8. Phân biệt khả năng rollback code, roll-forward dữ liệu và phục hồi từ backup.
9. Đánh giá sự tương thích của event JSON, cache, search projection và dữ liệu ngoài DB.
10. Thiết kế CI quality gate và rehearsal với khả năng xác minh sau lỗi.

## 2. Vì sao test database rỗng không đủ?

Giả sử service v1 lưu đơn hàng:

~~~sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Ứng dụng cũ mặc định `total_amount` luôn là VND. Phiên bản v2 hỗ trợ thêm tiền tệ và migration bổ sung cột:

~~~sql
ALTER TABLE orders ADD COLUMN currency VARCHAR(3);
~~~

Nếu một test dựng database mới với schema v2 cuối cùng rồi insert các hàng do v2 tạo, mỗi hàng có thể đã có `currency` hợp lệ. Test sẽ không phát hiện lỗi với hàng triệu đơn v1 còn `currency IS NULL` sau lần ALTER. Code v2 nếu coi currency bắt buộc sẽ ném exception hoặc diễn giải sai.

### 2.1. Bốn loại bài test khác nhau

| Loại | Trả lời câu hỏi | Không tự chứng minh |
|---|---|---|
| Fresh install | Migration tạo được schema mới từ DB rỗng? | Có chuyển được dữ liệu cũ không |
| Upgrade path | Từ schema v1 có dữ liệu v1 sang v2 có đúng? | App cũ/mới chạy đồng thời có đúng |
| Rolling compatibility | App cũ/mới đọc/ghi cùng schema chuyển tiếp được? | Mọi backfill/recovery đã hoàn tất |
| Restore/replay | Từ backup/sự kiện lịch sử có phục hồi và đọc đúng? | Hệ thống bên ngoài cùng thời điểm |

Một bộ test chất lượng cần kiểm chứng những điều liên quan đến rủi ro dự án ở cả bốn loại. Test `repository.save()` và đọc lại một entity mới chỉ bao phủ phần nhỏ.

### 2.2. Schema version khác data version

Migration `V2__add_currency.sql` hoàn tất nhưng backfill có thể mới xử lý một phần:

~~~text
Schema: V2, currency column exists and is nullable.
Data:   65% legacy orders have currency; 35% still NULL.
Writer: Some application v1 instances still write old shape.
Reader: v2 must support legacy row and explicit currency.
~~~

**Không được đồng nhất một con số migration version với trạng thái chuyển đổi toàn bộ dữ liệu.** Một job backfill có checkpoint riêng, feature flag và thời điểm nâng cấp writer; bài test cần tái hiện các trạng thái trung gian được phép tồn tại.

## 3. Kiểm thử cấu trúc và ngữ nghĩa

### 3.1. Cấu trúc có thể kiểm tra bằng metadata

Những thay đổi như thêm cột, đổi kiểu, thêm foreign key, unique, check, not-null, index hoặc view có thể kiểm tra bằng truy vấn metadata/schema catalog và thử SQL thật.

Nhưng chỉ biết cột `amount` tồn tại không chứng minh nó vẫn có đúng **đơn vị và ý nghĩa**.

### 3.2. Lỗi ngữ nghĩa thường không sinh exception

Ví dụ:

- Cột `amount BIGINT` trước lưu đồng nhỏ nhất, nay code hiểu thành đơn vị tiền chính.
- `created_at` trước là giờ địa phương, nay mặc định UTC.
- Enum `PAID` trước có nghĩa đã ủy quyền, nay hiểu là đã thanh toán hoàn tất.
- `NULL` trước là chưa biết, bản mới coi là không áp dụng.
- `total_amount` trước bao gồm thuế, nay dùng cho giá chưa thuế.

Các thay đổi này vẫn có thể đọc được qua JDBC nhưng cho kết quả nghiệp vụ sai. Test phải có **expected business outcome độc lập** với chính hàm chuyển đổi đang kiểm tra.

### 3.3. Hợp đồng bảo toàn dữ liệu

Ví dụ với đơn hàng:

~~~text
Legacy order:
  - Chỉ được suy ra currency=VND nếu đã xác minh lịch sử.
  - total_amount giữ nguyên giá trị theo quy tắc đã công bố.

New order:
  - currency hợp lệ phải được giữ lại.
  - backfill không được ghi đè currency=USD bằng VND.

During rolling deploy:
  - Không cho writer mới tạo dữ liệu USD khi reader cũ còn hiểu VND.
~~~

Nếu nguồn lịch sử có đơn không xác định currency, test phải xác nhận chúng được phân loại/cách ly, không âm thầm gán VND để đạt `NOT NULL`.

## 4. Ma trận tương thích giữa phiên bản

Quy ước:

- `A1`: ứng dụng v1 chỉ hiểu VND.
- `A2`: ứng dụng v2 đọc currency nullable, có fallback được xác minh; chưa ghi USD.
- `A3`: ứng dụng v3 đọc currency bắt buộc, hỗ trợ USD.
- `S1`: schema không có cột currency.
- `S2`: schema có currency nullable, default VND.
- `S3`: currency NOT NULL, backfill hoàn tất.

| Scenario | Code | Schema | Dữ liệu | Kết quả kỳ vọng |
|---|---|---|---|---|
| Baseline | A1 | S1 | Hàng cũ VND | PASS |
| Expand | A1 | S2 | Cũ và mới đều VND | PASS nếu A1 không phụ thuộc tên cột mới |
| Expand | A2 | S2 | Một phần hàng NULL | PASS nhờ reader tương thích |
| Rolling | A1 + A2 | S2 | Chưa có USD | PASS nếu mọi đường ghi có hợp đồng |
| Backfill dở | A2 | S2 | Một phần NULL | PASS, chưa được bỏ fallback |
| Sau contract | A3 | S3 | Không NULL | PASS với ràng buộc và ngữ nghĩa |
| Bật USD sớm | A1 + A3 | S2 | Có USD | FAIL về ngữ nghĩa; phải cấm cấu hình |
| Xóa field sớm | A1 | Schema đã bỏ cột A1 dùng | Bất kỳ | FAIL; contract chưa được phép |

### 4.1. Reader và writer đều phải được test

Một reader cũ có thể bỏ qua cột mới; điều đó không bảo đảm đường **UPDATE** không ghi đè nó. ORM `merge()` hoặc câu UPDATE từ một snapshot cũ có thể làm mất giá trị mới khi hai phiên bản cùng chạy.

Thử theo từng đường:

1. A1 insert → A2 read.
2. A2 insert dữ liệu còn tương thích → A1 read.
3. A1 update → A2 read và xác minh field mới không mất.
4. A2 update → A1 read giữ đúng ý nghĩa nghiệp vụ.
5. A1 và A2 cập nhật đồng thời → bảo toàn version/invariant.
6. Sau bật định dạng không tương thích, A1 bị loại khỏi traffic hoặc được bảo vệ thích hợp.

**PASS không có nghĩa “không ném exception”**; phải đúng nghiệp vụ.

### 4.2. Tương thích có thời hạn nhưng phải có bằng chứng

Không bắt buộc hỗ trợ mọi phiên bản mãi mãi. Tuy vậy, trước khi xóa trường cũ, phải chứng minh không còn worker, replica, consumer, job theo lịch hoặc đường restore đang phụ thuộc vào nó. Các client mobile và sự kiện đã lưu có thể tồn tại lâu hơn vòng deploy backend.

## 5. Fixture đại diện cho dữ liệu lịch sử

### 5.1. Trường hợp biên cần có

| Nhóm | Fixture cần chuẩn bị |
|---|---|
| Thiếu dữ liệu mới | Cột còn NULL, default cũ, field JSON không tồn tại |
| Kiểu số | Zero, giá trị lớn nhất, scale lẻ, số âm từng hợp lệ |
| Chuỗi | Rỗng, whitespace, Unicode, ký tự đặc biệt, độ dài giới hạn |
| Thời gian | DST, timezone, ngày cuối năm, offset khác nhau |
| Enum | Value đã bỏ, value mới chưa được reader cũ hỗ trợ |
| Quan hệ | Nhiều con, FK, orphan do dữ liệu legacy |
| Trùng lặp | Business key bị trùng trước khi có unique constraint |
| Dữ liệu nửa chừng | Một phần hàng đã chuyển, phần còn lại chưa |
| Đồng thời | Hàng sửa trong lúc job backfill chạy |
| JSON/event | Payload schema v1, field optional và unknown field |

Một fixture “đẹp” chỉ có giá trị hợp lệ theo schema mới sẽ bỏ sót mục tiêu của bài học.

### 5.2. Golden dataset và expected outcome

Trong schema v1:

~~~sql
INSERT INTO orders (id, total_amount, created_at)
VALUES
    (101, 0.00,       TIMESTAMPTZ '2020-01-10 09:00:00+00'),
    (102, 120000.00,  TIMESTAMPTZ '2021-06-15 12:30:00+00'),
    (103, 9999999.99, TIMESTAMPTZ '2022-12-31 23:59:00+00');
~~~

Kết quả mong đợi sau migration, **chỉ trong giả định dữ liệu cũ được xác minh là VND**:

~~~text
101 -> amount 0.00       / currency VND
102 -> amount 120000.00  / currency VND
103 -> amount 9999999.99 / currency VND
~~~

Giá trị kỳ vọng phải được định nghĩa từ quy tắc nghiệp vụ, không lấy bằng đúng hàm transform đang được test. Khi kiểm tra `BigDecimal`, sử dụng phép so sánh có tính đến scale theo hợp đồng: `compareTo` so sánh giá trị số, còn `equals` còn xét scale.

### 5.3. Không đưa dữ liệu raw production vào CI

Nếu cần phân bố thực để test migration hay hiệu năng:

- Ưu tiên fixture/synthetic data.
- Nếu cần dữ liệu production, restore trong enclave được bảo vệ tương đương và có phê duyệt.
- Mask/minimize trước khi mở quyền developer hoặc CI; quét cả JSON, ghi chú, event, log, file.
- Vô hiệu hóa email, webhook, payment, worker ngoài và chặn egress.
- Bảo vệ bản dump tạm, snapshot và khóa; xóa đúng hạn.
- Tránh in PII trong log khi migration lỗi.

Dữ liệu đã hash định danh vẫn có thể tái định danh qua tổ hợp thông tin hoặc nguồn phụ trợ. Bộ dữ liệu test phải giảm rủi ro nhưng vẫn giữ quan hệ, skew và trường hợp biên cần thiết.

## 6. Migration versioned phải được dùng đúng cách trong test

Với Java, Flyway hoặc Liquibase có thể quản lý các thay đổi theo version. Bài kiểm thử upgrade cần chạy **cùng artifact migration đã phát hành**, không dựng thủ công schema mới rồi gọi đó là migration test.

### 6.1. Ví dụ các bước Flyway

~~~text
src/main/resources/db/migration/
  V1__create_orders.sql
  V2__add_currency.sql
  V3__backfill_currency.sql
  V4__require_currency.sql
~~~

V1:

~~~sql
CREATE TABLE orders (
    id           BIGINT PRIMARY KEY,
    total_amount NUMERIC(14, 2) NOT NULL CHECK (total_amount >= 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

V2 mở rộng:

~~~sql
ALTER TABLE orders ADD COLUMN currency VARCHAR(3);
ALTER TABLE orders ALTER COLUMN currency SET DEFAULT 'VND';
~~~

`SET DEFAULT` áp dụng cho INSERT sau đó thiếu currency; không tự backfill các hàng cũ còn NULL.

V3 chuyển dữ liệu trong giả định đã xác minh lịch sử VND:

~~~sql
UPDATE orders SET currency = 'VND' WHERE currency IS NULL;
~~~

V4 siết ràng buộc:

~~~sql
ALTER TABLE orders ALTER COLUMN currency SET NOT NULL;
~~~

**Quan trọng:** V3 là một ví dụ cho fixture nhỏ, không phải kế hoạch chuyển hàng triệu hàng production trong một transaction. Với dữ liệu thật cần batching, checkpoint, lock budget, rollback policy và điều kiện writer đã sẵn sàng trước khi siết V4.

### 6.2. Chạy từ schema cũ có dữ liệu chứ không chỉ từ DB trắng

~~~mermaid
flowchart LR
    A["New isolated DB"] --> B["Run V1 migrations"]
    B --> C["Insert legacy fixtures via V1 schema"]
    C --> D["Verify before snapshot"]
    D --> E["Run V2-V4 migrations"]
    E --> F["Check schema + rows + invariants"]
    F --> G["Run current Java reader/service"]
~~~

Chạy Flyway một lượt từ V1 đến V4 trên database trống có thể phát hiện DDL sai, nhưng migration V3 không gặp dữ liệu lịch sử. Cả **fresh-install test** và **upgrade-path test** đều cần được phân biệt.

### 6.3. Không sửa migrations cũ để cho test xanh

File versioned đã áp dụng ở production có checksum và lịch sử. Nếu chỉnh lại V2 thay vì thêm migration mới, đường khôi phục từ bản backup V1 có thể chạy logic khác lịch sử. Nên giữ artifact đã phát hành bất biến; nếu cần repair history, phải được review và có lý do được ghi lại.

## 7. JUnit 5 + Testcontainers + Flyway: ví dụ upgrade test

Một bài test đáng tin cần engine thực cho những tính năng phụ thuộc PostgreSQL, như DDL lock, `TIMESTAMPTZ`, constraint, `ON CONFLICT`, transaction và isolation. H2 có thể dùng cho một số unit test nhưng không thay thế kiểm thử migration trên DBMS sản xuất.

### 7.1. Sơ đồ setup

~~~text
PostgreSQLContainer starts -> Flyway target V1
  -> JDBC insert legacy row
  -> Flyway migrate to latest
  -> JDBC assert amount/currency
  -> call reader/repository Java
  -> container cleanup
~~~

### 7.2. Kiểm thử tích hợp minh họa

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationVersion;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

class OrdersMigrationTest {

    @Test
    void preservesLegacyAmountAndBackfillsCurrency()
            throws Exception {
        try (PostgreSQLContainer<?> pg =
                 new PostgreSQLContainer<>("postgres:16-alpine")
                     .withDatabaseName("orders_test")) {
            pg.start();

            Flyway initial = Flyway.configure()
                .dataSource(pg.getJdbcUrl(),
                            pg.getUsername(), pg.getPassword())
                .locations("classpath:db/migration")
                .target(MigrationVersion.fromVersion("1"))
                .load();
            initial.migrate();

            try (Connection c = DriverManager.getConnection(
                    pg.getJdbcUrl(),
                    pg.getUsername(), pg.getPassword());
                 PreparedStatement ps = c.prepareStatement(
                    """
                    INSERT INTO orders (id, total_amount, created_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    """)) {
                ps.setLong(1, 102L);
                ps.setBigDecimal(2, new BigDecimal("120000.00"));
                assertEquals(1, ps.executeUpdate());
            }

            Flyway latest = Flyway.configure()
                .dataSource(pg.getJdbcUrl(),
                            pg.getUsername(), pg.getPassword())
                .locations("classpath:db/migration")
                .load();
            latest.migrate();

            try (Connection c = DriverManager.getConnection(
                    pg.getJdbcUrl(),
                    pg.getUsername(), pg.getPassword());
                 PreparedStatement ps = c.prepareStatement(
                    """
                    SELECT total_amount, currency
                    FROM orders WHERE id = ?
                    """)) {
                ps.setLong(1, 102L);
                try (ResultSet rs = ps.executeQuery()) {
                    assertTrue(rs.next());
                    assertEquals(0,
                        rs.getBigDecimal("total_amount")
                          .compareTo(new BigDecimal("120000.00")));
                    assertEquals("VND", rs.getString("currency"));
                    assertFalse(rs.next());
                }
            }
        }
    }
}
~~~

**Giới hạn:** đây là mẫu minh họa, không phải test đã chạy ở dự án này. Cần khai báo các dependency JUnit 5, Testcontainers, PostgreSQL JDBC và Flyway (kể cả mô-đun hỗ trợ PostgreSQL theo phiên bản Flyway). `postgres:16-alpine` chỉ là image thử nghiệm; dự án thật phải sử dụng major/minor phiên bản tương thích với production. Bộ migration minh họa V1–V4 phải tồn tại ở resource classpath.

Một test trên chỉ chứng minh một hàng legacy được chuyển đúng theo giả định VND. Cần mở rộng sang dữ liệu nhiều bảng, lỗi migrate, rolling release, concurrent writers, khôi phục từ backup và performance ở quy mô.

## 8. Kiểm thử reader Java với dữ liệu cũ

Migration thành công không đảm bảo JPA/JDBC mapping mới hiểu dữ liệu lịch sử.

### 8.1. Reader tương thích khi cột mới nullable

~~~java
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;

public record Money(BigDecimal amount, String currency) {}

public final class MoneyMapper {
    public Money read(ResultSet row) throws SQLException {
        String currency = row.getString("currency");

        if (currency == null) {
            // Chỉ dùng fallback khi dữ liệu lịch sử được xác minh là VND.
            currency = "VND";
        }

        return new Money(row.getBigDecimal("total_amount"), currency);
    }
}
~~~

Phải kiểm tra:

- Hàng legacy `currency=NULL` đọc đúng theo hợp đồng VND.
- Hàng mới `currency='USD'` giữ USD, không bị fallback vô điều kiện.
- Giá trị currency không hợp lệ bị từ chối hoặc phân loại rõ.
- `BigDecimal` không bị chuyển qua `double` làm sai precision.
- ResultSet có cột currency nhưng null **khác** với schema V1 hoàn toàn không có cột đó. Nếu reader cần chạy trên S1, nó phải dùng truy vấn/mapper phù hợp: `getString("currency")` không tự trả null khi cột không tồn tại.

### 8.2. ORM/JPA cần thêm bài kiểm tra

Với Jakarta Persistence/Hibernate:

- `@Column(nullable=false)` không thay thế validation dữ liệu và `NOT NULL` thực trên DB.
- `@Enumerated(EnumType.STRING)` có thể hỏng với enum tên cũ; ordinal có nguy cơ đổi nghĩa khi sắp lại.
- `@Version` giúp optimistic locking cho update entity phù hợp, nhưng bulk migration SQL không tự cập nhật version như ORM.
- `@ManyToOne` và `@OneToMany` cần dữ liệu khóa ngoại không bị hỏng sau migration.
- `merge` trên entity detached có thể ghi đè trường mới theo trạng thái cũ; thử concurrency.
- Lazy loading và query plan có thể thay đổi sau migration; test trong ranh giới transaction rõ.
- ORM schema validation không kiểm hết trigger, index, permission và semantic invariants.

### 8.3. Expected value phải độc lập

Sai lầm là so sánh hai đường code cùng dùng một hàm convert sai rồi kết luận đã đúng. Nên có golden outcome được định nghĩa độc lập theo nghiệp vụ; khi cần, đối soát tổng tiền, tập ID và trạng thái theo một thuật toán kiểm tra riêng.
## 9. Kiểm tra bất biến sau migration, không chỉ cột có tồn tại

Một migration có thể tạo đủ bảng/cột nhưng vẫn làm sai dữ liệu. Cần kiểm tra **invariants** được định nghĩa theo nghiệp vụ, bằng tập ID, giá trị, ràng buộc và truy vấn độc lập.

### 9.1. Số lượng và danh tính

Nếu chỉ bổ sung currency mà không xóa hoặc tách đơn:

~~~sql
SELECT COUNT(*) AS total_orders FROM orders;

SELECT COUNT(*) AS missing_currency
FROM orders WHERE currency IS NULL;
~~~

Đọc số hàng và tập khóa trước/sau migration. Chỉ so count có thể bỏ sót trường hợp mất một hàng và nhân đôi một hàng khác; test có thể so tập khóa, digest theo định dạng canonical hoặc mẫu được kiểm soát.

Nếu migration tách một bảng thành nhiều bảng, không mong số hàng mọi bảng bằng nhau. Cần **mapping cũ → mới** và bất biến quan hệ xác định trước.

### 9.2. Giá tiền và đơn vị

Một tập đơn chỉ có VND phải giữ đúng số tiền sau migration; khi hệ có nhiều currency, kiểm tra theo từng đơn vị:

~~~sql
SELECT currency, COUNT(*) AS n, SUM(total_amount) AS total
FROM orders
GROUP BY currency;
~~~

Không cộng VND và USD thành một số chung rồi kết luận đúng. Với chuyển kiểu từ floating point sang `NUMERIC`, test các giá trị sát giới hạn precision, rounding, số tiền đã quyết toán và kết quả tính thuế.

### 9.3. Foreign key và quan hệ

Ví dụ bảng `order_items(order_id, ...)`:

~~~sql
SELECT i.order_id, COUNT(*) AS orphan_count
FROM order_items AS i
LEFT JOIN orders AS o ON o.id = i.order_id
WHERE o.id IS NULL
GROUP BY i.order_id;
~~~

Trong migration tách/đổi khóa, test phải xác minh không tạo orphan, không gán item sai order và không xóa dòng cần giữ. Nếu dữ liệu legacy **đã có** orphan, xác định chính sách sửa được phê duyệt trước khi áp constraint mới.

### 9.4. Constraint phải từ chối dữ liệu không hợp lệ

Sau migration V4, database có thể vẫn có default `'VND'`; vì vậy thử INSERT không truyền currency **không chứng minh NOT NULL**, vì DB tự áp default. Muốn test, cố ghi `NULL` tường minh và kỳ vọng lỗi:

~~~sql
BEGIN;

INSERT INTO orders
  (id, total_amount, currency, created_at)
VALUES
  (999, 10.00, NULL, CURRENT_TIMESTAMP);

-- Trên PostgreSQL, lỗi khiến transaction cần ROLLBACK.

ROLLBACK;
~~~

Đoạn trên mang tính minh họa; test runner phải bắt exception rồi rollback connection hợp lệ. Thử thêm unique, foreign key, check giá âm và những giá trị ngoài miền.

### 9.5. Index và hiệu năng

Có thể đọc system catalog để khẳng định index được tạo, nhưng không khẳng định một query luôn phải dùng index scan. Query planner phụ thuộc thống kê, kích thước và chi phí. Rehearsal cần đo `EXPLAIN (ANALYZE, BUFFERS)` và thời gian DDL trên dữ liệu gần quy mô thật, đồng thời bảo vệ dữ liệu test.

## 10. Kiểm thử expand–backfill–contract từng pha

Đường chuyển đổi có rủi ro cao nhất khi một phần dữ liệu cũ, một phần mới và nhiều phiên bản ứng dụng cùng hoạt động.

~~~mermaid
flowchart LR
    A["Schema S1 + app A1"] --> B["EXPAND S2"]
    B --> C["A1/A2 cùng hoạt động"]
    C --> D["BACKFILL theo chunk"]
    D --> E["VERIFY toàn bộ invariant"]
    E --> F["CONTRACT S3"]
    F --> G["Bật tính năng mới A3"]
~~~

### 10.1. Pha expand

- Chạy DDL thêm cột khi bảng đã có dữ liệu.
- App cũ còn đọc/ghi được những thao tác cũ.
- App mới đọc được hàng `currency=NULL` và hàng có explicit currency.
- Không mất số tiền hoặc đổi ID.
- Chưa cho phép sinh dữ liệu mới mà reader cũ diễn giải sai.
- Kiểm tra quyền, thời gian lock và cơ chế migration history.

### 10.2. Pha backfill

- Job chỉ cập nhật những hàng cần chuyển.
- Chạy lại không biến đổi giá trị hai lần.
- Hàng writer mới đã cập nhật không bị ghi đè.
- Job dừng giữa batch vẫn restart an toàn.
- Các hàng mơ hồ được cách ly và báo cáo, không ép giá trị đoán.
- Kiểm tra tiến độ bằng dữ liệu thực, không chỉ log.

### 10.3. Pha contract

- Không còn writer tạo dữ liệu theo format cũ.
- Tập dữ liệu đạt các ràng buộc mới.
- App mới vẫn hoạt động khi bỏ fallback.
- Các worker/reporting/consumer cũ không còn cần field đã bỏ.
- Kịch bản restore từ backup cũ vẫn có đường nâng cấp có thể lặp lại.
- Feature flag chỉ bật hành vi không tương thích khi tất cả reader cần thiết đã sẵn sàng.

### 10.4. Đổi tên cột và dual-write

Đổi `customers.full_name` thành `display_name` bằng `ALTER TABLE ... RENAME` ngay có thể phá app cũ. Một quy trình chuyển tiếp thêm cột mới, cho reader fallback, cập nhật đồng bộ qua **một cơ chế có thẩm quyền**, backfill và sau đó bỏ cột cũ.

Test quan trọng là tình huống writer A1 cập nhật `full_name` trong lúc A2 ghi `display_name`. Nếu cả hai trường được coi là nguồn sự thật độc lập, có thể xảy ra race và dữ liệu lệch. Phải có policy ưu tiên, version và điều kiện ghi được kiểm chứng.

## 11. Backfill, idempotency và checkpoint

Backfill trên dữ liệu production là một writer đồng thời; cần kiểm thử như một chương trình xử lý giao dịch thật.

### 11.1. SQL cập nhật theo lô có điều kiện

PostgreSQL:

~~~sql
WITH chunk AS (
    SELECT id
    FROM orders
    WHERE currency IS NULL
    ORDER BY id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET currency = 'VND'
FROM chunk
WHERE o.id = chunk.id
  AND o.currency IS NULL
RETURNING o.id;
~~~

Đây là ví dụ cho **tập legacy đã được xác minh chỉ VND**, không phải công thức áp cho dữ liệu không biết đơn vị. Thực thi từng lượt trong transaction ngắn, có backpressure và theo dõi:

- `SKIP LOCKED` có thể bỏ qua những hàng đang bị khóa, cần lượt quét bù.
- Writer mới có thể điền currency trong lúc worker chạy.
- Khi không còn hàng null, cần bảo đảm writer không sinh thêm giá trị null.
- Giới hạn số worker và thời gian transaction để tránh contention.
- Không suy ra mọi ID nhỏ hơn checkpoint đã được xử lý nếu có late inserts.

### 11.2. Idempotency của phép chuyển đổi

`SET currency = 'VND' WHERE currency IS NULL` có tính chất chạy lại không làm thay đổi những hàng đã được điền giá trị. Ngược lại:

~~~sql
UPDATE accounts SET balance = balance * 100;
~~~

là phép biến đổi **không idempotent** nếu chạy lại; số dư sẽ tiếp tục nhân 100. Nếu nghiệp vụ quy định rõ biến đổi cần thiết, có thể gắn data version:

~~~sql
UPDATE accounts
SET balance = balance * 100,
    amount_format_version = 2
WHERE amount_format_version = 1;
~~~

Đây chỉ là kỹ thuật minh họa; migration tiền thật cần kiểm tra precision, rounding, overflow, khóa và khả năng khôi phục. Hai cột phải được cập nhật trong cùng transaction để không còn bản ghi có số tiền mới nhưng version cũ.

### 11.3. Checkpoint và restart

Cần chủ động crash ở những điểm:

1. Trước khi mở transaction.
2. Sau khi đọc batch nhưng chưa UPDATE.
3. Sau UPDATE trước `COMMIT`.
4. Sau commit nhưng trước khi ghi checkpoint ngoài DB.
5. Sau checkpoint rồi trước ghi metric.
6. Khi hai worker đang claim các hàng có thể chồng nhau.

Một checkpoint bên ngoài database có thể tiến trước hoặc tụt sau dữ liệu sau restore/commit. Kiểm thử phải có đường **reconcile** và write idempotent.

Nếu một worker đánh dấu `last_id=5000` nhưng hàng ID 4500 mới được cập nhật sau đó, chỉ quét `id > 5000` có thể bỏ sót. Có thể cần quét bù theo `WHERE currency IS NULL` hoặc dùng CDC/version tracking.

### 11.4. Batch nhỏ không tự bảo đảm atomicity của toàn migration

Một migration chia thành 100 transaction có thể commit 30 chunk rồi lỗi ở chunk 31. Điều này có thể chấp nhận nếu reader hỗ trợ trạng thái nửa chuyển. Nếu nghiệp vụ yêu cầu toàn tập phải nguyên tử, thiết kế chia chunk như vậy đã **thay đổi contract** và cần kiến trúc khác.

## 12. Kiểm thử concurrency: race và isolation

### 12.1. Hai session làm thay đổi cùng hàng

~~~text
T1 (backfill): đọc order 42 còn currency NULL.
T2 (API):      cập nhật order 42 thành currency USD.
T2:            COMMIT.
T1:            cố ghi VND từ snapshot cũ.

Kỳ vọng: currency cuối là USD; backfill không ghi đè.
~~~

Test có thể dùng hai `Connection` và `CountDownLatch`/barrier để điều khiển lịch chạy. Điều kiện `WHERE currency IS NULL` hoặc optimistic version check phải ngăn lost update theo SQL/DBMS thực.

### 12.2. JPA `@Version` và SQL bulk

Nếu entity có `@Version`, bulk SQL có thể không tăng version tự động. Khi migration thay đổi hàng được ORM quản lý, cần thiết kế optimistic locking cho mọi đường ghi quan trọng.

Ví dụ SQL:

~~~sql
UPDATE products
SET price = ?,
    version = version + 1
WHERE id = ?
  AND version = ?;
~~~

Test affected-row count và xử lý xung đột. Không trả success khi không có hàng nào khớp version cũ; tùy nghiệp vụ có thể rollback/đọc lại rồi thử mới.

### 12.3. Deadlock và retry toàn transaction

~~~text
T1: lock product 1.
T2: lock product 2.
T1: wait product 2.
T2: wait product 1.
=> DB có thể hủy một transaction do deadlock.
~~~

Mong đợi:

- Transaction bị hủy không được đánh dấu hoàn tất.
- Rollback trước khi thử lại.
- Retry **toàn transaction**, có giới hạn/backoff, nếu nghiệp vụ cho phép.
- Không nhân đôi side effect như gửi email hoặc charge payment.
- Giữ thông tin SQLSTATE/vendor code và cause để chẩn đoán.

### 12.4. Isolation không thay thế bất biến

Một job dùng `READ COMMITTED` có thể thấy snapshot khác nhau giữa các batch. `REPEATABLE READ` có thể cho snapshot ổn định hơn trong phạm vi transaction nhưng tăng thời gian giữ phiên bản dữ liệu nếu transaction dài. Chọn mức isolation theo yêu cầu thật, đồng thời viết test kiểm tra kết quả cuối và race thay vì chỉ nâng isolation một cách tùy tiện.

## 13. Dữ liệu legacy không hợp lệ: test phải biết dừng đúng

Một số migration thêm constraint sẽ thất bại với dữ liệu lịch sử như duplicate, orphan FK, null hoặc enum lạ.

| Đặc điểm legacy | Điều test cần xác nhận |
|---|---|
| NULL trong cột sắp NOT NULL | Phát hiện và xử lý trước contract |
| Duplicate ở business key mới UNIQUE | Phân loại và deduplicate theo quy tắc |
| Orphan foreign key | Không tự xóa hàng quan trọng để qua test |
| Enum cũ không còn | Adapter hoặc lỗi tương thích rõ |
| Amount không rõ đơn vị | Cách ly, không gán mặc định mù |
| Timestamp không rõ timezone | Xác minh nguồn trước khi chuyển |
| Chuỗi vượt VARCHAR mới | Không truncate im lặng |
| NUMERIC overflow | Phát hiện và xử lý theo quy tắc tài chính |
| JSON v1 thiếu field v2 | Converter hoặc fallback đã được test |

### 13.1. Kết quả đúng đôi khi là chặn migration

Không phải mọi đầu vào đều chuyển được một cách chính xác. Một nhóm user trùng email trước khi tạo unique constraint có thể sở hữu nhiều đơn/role/audit khác nhau. Xóa một user theo ID lớn hơn chỉ để constraint pass có thể làm mất dữ liệu nghiệp vụ.

Test tốt có thể yêu cầu migration dừng, xuất thống kê bản ghi ngoại lệ **không lộ dữ liệu cá nhân**, chờ phê duyệt cách merge, rồi mới tiếp tục.

### 13.2. Kiểm tra data quality trước khi siết

~~~sql
SELECT COUNT(*) AS null_count
FROM orders WHERE currency IS NULL;

SELECT currency, COUNT(*) AS row_count
FROM orders GROUP BY currency;
~~~

Sau khi dữ liệu hợp lệ và writer sẵn sàng, mới thêm constraint. Trên PostgreSQL, `NOT VALID`/`VALIDATE CONSTRAINT` có hỗ trợ tùy loại ràng buộc và phiên bản, nhưng việc `SET NOT NULL` vẫn có yêu cầu lock/validation riêng. Rehearsal phải đo trên DB có quy mô gần thực tế.




