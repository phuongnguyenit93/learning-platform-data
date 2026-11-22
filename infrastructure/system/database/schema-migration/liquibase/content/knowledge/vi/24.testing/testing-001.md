# Thiết kế các lớp kiểm thử cho migration

Một migration có thể vượt qua kiểm tra cú pháp nhưng vẫn thất bại khi chạy trên database thật. Chẳng hạn, changelog hợp lệ về YAML nhưng SQL không tương thích phiên bản MySQL đang dùng; CREATE INDEX chạy được trên database rỗng nhưng khóa bảng production quá lâu; precondition báo thành công nhưng dữ liệu chưa được backfill; hoặc rollback không khôi phục được trạng thái nghiệp vụ. Vì vậy, kiểm thử migration cần nhiều lớp, mỗi lớp trả lời một nhóm câu hỏi và bổ sung bằng chứng cho lớp tiếp theo.

Bài học thuộc chương **Kiểm thử** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Phạm vi module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Trọng tâm của bài là thiết kế một chiến lược kiểm thử có hệ thống cho changelog và changeset: từ kiểm tra tĩnh, kiểm tra cấu trúc, kiểm thử tích hợp trên DBMS đích, xác minh dữ liệu, rollback, tương thích ứng dụng, hiệu năng, concurrency đến tự động hóa trong CI/CD.

Sau bài học, bạn có thể:

1. Phân biệt các lớp kiểm thử migration và hiểu bằng chứng mà mỗi lớp cung cấp.
2. Thiết kế kiểm thử cho cả database mới và database đang nâng cấp từ phiên bản trước.
3. Dùng validate, status và update-sql đúng mục đích, không nhầm chúng với kiểm thử thực thi.
4. Xác minh schema, dữ liệu và DATABASECHANGELOG sau migration.
5. Kiểm thử rollback, retry, precondition, checksum và trường hợp thất bại giữa chừng.
6. Chọn DBMS/version, dữ liệu và môi trường test đủ đại diện.
7. Tổ chức test database cách ly, tích hợp Spring Boot và quality gate CI/CD.

## 1. Vì sao migration cần nhiều lớp kiểm thử?

Migration là thay đổi có trạng thái. Kết quả của nó phụ thuộc vào nhiều yếu tố:

- Changelog và nội dung changeset.
- Trạng thái schema/dữ liệu trước khi chạy.
- DBMS, phiên bản server và JDBC driver.
- Quyền của tài khoản migration.
- Transaction, implicit commit và lock.
- Context, labels, dbms filter và precondition.
- Thứ tự include và các changeset đã triển khai trước đó.
- Ứng dụng đang chạy và cách ứng dụng sử dụng schema.

Một bài kiểm thử chỉ gọi validate không thể chứng minh SQL sẽ chạy thành công. Một bài kiểm thử chỉ chạy update trên database trống cũng không chứng minh upgrade production an toàn. Một bài test rollback thành công không chứng minh dữ liệu phát sinh trong lúc vận hành sẽ được bảo toàn.

### 1.1. Mô hình các lớp kiểm thử

~~~mermaid
flowchart TD
    A[Changelog và thay đổi migration] --> B[Static checks và review]
    B --> C[Liquibase validate / status / SQL preview]
    C --> D[Unit tests cho logic tùy chỉnh]
    D --> E[Integration tests trên DBMS thật]
    E --> F[Upgrade và schema/data assertions]
    F --> G[Rollback, retry và failure tests]
    G --> H[Application compatibility]
    H --> I[Performance, locking, security]
    I --> J[CI/CD release gate]
~~~

Các lớp không nhất thiết chạy theo một pipeline duy nhất hoặc có cùng chi phí. Kiểm tra rẻ nên chạy thường xuyên; kiểm thử tích hợp tốn tài nguyên có thể chạy theo pull request, nightly hoặc trước phát hành. Tuy nhiên, những thay đổi có rủi ro cao cần kiểm thử DBMS thực tế trước khi được phê duyệt.

## 2. Xác định mục tiêu và phạm vi test trước khi viết test

Không nên bắt đầu bằng việc viết test cho mọi changeset theo cùng một mẫu. Trước tiên cần phân loại migration:

| Loại thay đổi | Rủi ro cần kiểm tra |
|---|---|
| Thêm bảng/cột | Kiểu dữ liệu, default, nullability, dependency |
| Thêm constraint | Dữ liệu hiện có có thỏa điều kiện không, lock và validation |
| Tạo index | SQL dialect, thời gian tạo, lock, index invalid |
| Thay đổi datatype | Mất dữ liệu, truncate, cast và tương thích ứng dụng |
| Backfill dữ liệu | Phạm vi hàng, idempotency, thời gian, tính nhất quán |
| Đổi tên/xóa cột | Ứng dụng cũ/mới, dependency và khả năng rollback |
| View/function/procedure | SQL body, delimiter, dependency và hành vi runtime |
| Permission/grant | Quyền tối thiểu và khả năng ứng dụng truy cập |
| DDL vendor-specific | Phiên bản DBMS, transaction và executor |
| Baseline/legacy adoption | Schema thực tế, history và khả năng dựng database mới |

Từ phân loại này, xác định lớp test cần thiết. Ví dụ thêm một cột nullable đơn giản có thể không cần performance test chuyên sâu; thay đổi datatype trên bảng hàng trăm triệu dòng cần test dữ liệu, lock và thời gian chạy trên dữ liệu đại diện.

### 2.1. Viết tiêu chí chấp nhận có thể kiểm tra

Một tiêu chí tốt mô tả trạng thái quan sát được.

Ví dụ thay vì viết:

~~~text
Migration thêm status thành công.
~~~

Hãy định nghĩa:

~~~text
- orders.status tồn tại trong schema app.
- Kiểu dữ liệu là varchar(24).
- Cột nullable theo thiết kế.
- Không có default ngoài dự kiến.
- Changeset có đúng ID/AUTHOR/FILENAME trong DATABASECHANGELOG.
- Các hàng cũ được backfill theo mapping đã thống nhất.
- Ứng dụng phiên bản hiện tại vẫn đọc và ghi được orders.
~~~

Tiêu chí phải phù hợp DBMS và thiết kế thực tế. Chỉ kiểm tra tên cột là chưa đủ nếu kiểu, nullability, default hoặc constraint quan trọng.

## 3. Lớp 1 — Static checks và code review

Lớp đầu tiên kiểm tra những vấn đề có thể phát hiện từ repository mà không cần thực thi migration lên database.

Nội dung thường gồm:

- File YAML/XML/JSON/formatted SQL có cấu trúc hợp lệ.
- File changeset được include vào root changelog.
- Đường dẫn include tồn tại.
- Không còn Git conflict marker.
- ID/author và logical path tuân theo quy ước.
- Không sửa changeset đã triển khai ngoài chính sách.
- Context, labels, dbms và runInTransaction có chủ đích.
- Có rollback hoặc phương án forward fix được mô tả.
- Không chứa secret trong changelog.
- SQL được review theo DBMS mục tiêu.

### 3.1. Review dependency

Ví dụ changeset tạo index phụ thuộc cột status:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-501-add-status"
      author: "orders-team"
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)

  - changeSet:
      id: "ORD-502-index-status"
      author: "orders-team"
      changes:
        - createIndex:
            tableName: orders
            indexName: idx_orders_status
            columns:
              - column:
                  name: status
~~~

Static review phải xác nhận changeset thêm cột được nạp trước changeset tạo index. YAML có thể hợp lệ ngay cả khi thứ tự dependency sai.

### 3.2. Static checks không chứng minh SQL chạy được

Một script có thể xác nhận ID không trùng, nhưng không biết datatype có hợp lệ trên Oracle hay không. Parser YAML có thể thành công, nhưng SQL trong formatted SQL vẫn có thể lỗi. Vì vậy static checks là lớp sàng lọc, không phải bằng chứng cuối cùng.

## 4. Lớp 2 — Liquibase validate

Lệnh **validate** kiểm tra changelog theo các quy tắc Liquibase hỗ trợ, chẳng hạn cấu trúc, include, định danh và checksum liên quan.

Ví dụ:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  validate
~~~

Nên chạy validate trong pull request và trước khi phát hành. Nếu dự án dùng nhiều changelog root, mỗi root được triển khai cần có bước validate tương ứng.

### 4.1. Validate có thể phát hiện gì?

- Changelog có cấu trúc không hợp lệ.
- Include hoặc đường dẫn không thể phân giải.
- Changeset identity có vấn đề theo quy tắc Liquibase.
- Checksum của changeset đã triển khai không khớp nội dung hiện tại trong những trường hợp được kiểm tra.
- Một số cấu hình change type hoặc thuộc tính không hợp lệ.

Phạm vi chính xác phụ thuộc phiên bản Liquibase và cách dự án tổ chức changelog.

### 4.2. Validate không kiểm tra điều gì?

Validate không đảm bảo:

- SQL thực thi thành công trên DBMS đích.
- Tài khoản có đủ quyền DDL.
- Dữ liệu hiện có thỏa constraint mới.
- Migration không giữ lock quá lâu.
- Rollback có thể khôi phục dữ liệu.
- Ứng dụng tương thích với schema sau update.
- SQL tùy chỉnh có đúng logic nghiệp vụ.

Một changelog validate thành công vẫn cần integration test trên database phù hợp.

## 5. Lớp 3 — status và update-sql trước khi thực thi

**status --verbose** cho biết changeset nào còn pending trong phạm vi changelog và filter hiện tại.

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  status --verbose
~~~

**update-sql** sinh SQL dự kiến cho lần update:

~~~bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-sql
~~~

Hai lệnh hỗ trợ review nhưng có vai trò khác nhau:

| Lệnh | Bằng chứng |
|---|---|
| status | Changeset nào được xem là chưa áp dụng |
| update-sql | SQL nào được dự kiến thực thi |
| update | Thực thi migration thật |

Không gọi status hoặc update-sql là integration test. Chúng không thực thi DDL/DML dự kiến và không chứng minh database sẽ chấp nhận SQL.

### 5.1. Kiểm tra filter

Kết quả pending chịu ảnh hưởng của context, labels, dbms và cấu hình runtime. CI phải chạy với filter giống môi trường triển khai hoặc ghi rõ khác biệt. Nếu test dùng context khác production, có thể bỏ sót changeset hoặc chọn nhầm tập migration.

## 6. Lớp 4 — Unit tests cho logic tùy chỉnh

Liquibase change type tiêu chuẩn thường được kiểm chứng tốt nhất bằng integration test trên DBMS. Tuy nhiên, dự án có thể chứa logic tùy chỉnh như:

- Custom Liquibase Change.
- Custom precondition.
- Java migration hoặc helper.
- Logic tạo dữ liệu mẫu.
- Bộ chuyển đổi tên/schema.
- Code xây dựng changelog động.

Phần logic thuần có thể có unit test để kiểm tra đầu vào/đầu ra và các nhánh điều kiện.

Ví dụ, một hàm ánh xạ trạng thái legacy:

~~~java
String mapLegacyStatus(String oldValue) {
    if (oldValue == null) {
        return "UNKNOWN";
    }
    return switch (oldValue.trim().toUpperCase()) {
        case "A", "ACTIVE" -> "ACTIVE";
        case "I", "INACTIVE" -> "INACTIVE";
        default -> "UNKNOWN";
    };
}
~~~

Unit test có thể kiểm tra NULL, chữ thường, khoảng trắng và giá trị không nhận diện.

Nhưng unit test không chứng minh SQL UPDATE gọi hàm đúng, transaction đúng hoặc dữ liệu database được chuyển đổi đúng. Cần integration test cho đường đi từ migration tới kết quả thật.

### 6.1. Không mock database để chứng minh migration

Mock JDBC hoặc mock Liquibase có thể hữu ích cho logic điều phối, nhưng không kiểm tra dialect, constraint, lock, implicit commit và catalog của DBMS. Không dùng mock làm bằng chứng duy nhất cho changeset DDL/DML.

## 7. Lớp 5 — Integration tests trên DBMS thật

Đây là lớp quan trọng nhất để xác nhận migration thực sự hoạt động. Test cần dùng DBMS tương ứng với production hoặc một phiên bản được xác định là tương thích.

Có thể sử dụng:

- Database container riêng cho mỗi CI job.
- Testcontainers trong dự án Java.
- Database ephemeral do CI provision.
- Instance test được tạo từ image/version chuẩn.
- Database schema riêng nếu isolation và cleanup được bảo đảm.

Ví dụ Testcontainers với PostgreSQL trong Java:

~~~java
@Testcontainers
class LiquibaseMigrationIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("migration_test")
            .withUsername("test")
            .withPassword("test");

    @Test
    void migrationRunsAgainstPostgres() {
        // Tạo datasource từ JDBC URL của container.
        // Chạy Liquibase update bằng changelog của dự án.
        // Truy vấn catalog và assertion schema/data.
    }
}
~~~

Đây là khung minh họa; cần thêm dependency, datasource và cách gọi Liquibase phù hợp với dự án. Không nên dùng tag image trôi nổi trong pipeline quan trọng; cố định phiên bản DBMS và cập nhật có chủ đích.

### 7.1. Vì sao phải dùng DBMS đích?

Các DBMS khác nhau về:

- DDL transaction và implicit commit.
- Kiểu dữ liệu, cast và default.
- Index và constraint.
- Cú pháp SQL, delimiter và batch.
- Locking và online DDL.
- Sequence/identity.
- Stored procedure và function.
- Driver metadata và executor.

Một migration chạy trên H2 không chứng minh nó chạy trên PostgreSQL, MySQL, Oracle hoặc SQL Server.

## 8. Hai đường kiểm thử bắt buộc: database mới và database nâng cấp

Một changelog có thể tạo schema mới thành công nhưng không nâng cấp được database cũ; hoặc upgrade thành công nhưng database trống không dựng được do thiếu baseline.

Do đó cần hai đường kiểm thử:

| Đường test | Trạng thái đầu | Mục tiêu |
|---|---|---|
| **Fresh install** | Database trống | Chạy toàn bộ changelog từ đầu |
| **Upgrade path** | Schema/data ở phiên bản phát hành trước | Chạy migration mới từ trạng thái thực tế cũ |

### 8.1. Fresh install

Quy trình:

1. Tạo database trống.
2. Xác nhận database/schema đúng.
3. Chạy validate.
4. Chạy update-sql để review.
5. Chạy update.
6. Kiểm tra schema và dữ liệu tham chiếu.
7. Kiểm tra DATABASECHANGELOG.
8. Khởi động ứng dụng hoặc chạy smoke test nếu cần.

Fresh install phát hiện thiếu changeset baseline, include sai thứ tự, object dependency chưa tồn tại và dữ liệu seed bắt buộc bị thiếu.

### 8.2. Upgrade path

Quy trình:

1. Tạo database từ artifact release cũ hoặc fixture tương đương.
2. Nạp dữ liệu đại diện cho trạng thái cũ.
3. Xác nhận history và schema baseline.
4. Đưa changelog mới vào.
5. Chạy status/update-sql.
6. Chạy update.
7. Kiểm tra schema, dữ liệu và ứng dụng.
8. So sánh với hợp đồng trạng thái mục tiêu.

Không dùng một database dev đã bị nhiều nhánh thay đổi thủ công làm fixture nâng cấp. Fixture phải có nguồn gốc và phiên bản xác định.

## 9. Lớp 6 — Schema assertions sau migration

Sau update, kiểm tra trạng thái thực tế qua catalog hoặc JDBC metadata. Không chỉ dựa vào DATABASECHANGELOG.

Ví dụ PostgreSQL xác minh cột:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

Xác minh index:

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'orders';
~~~

Xác minh constraint:

~~~sql
SELECT
    conname,
    contype,
    convalidated
FROM pg_catalog.pg_constraint
WHERE conrelid = 'app.orders'::regclass;
~~~

Đây là truy vấn PostgreSQL; DBMS khác có catalog riêng.

### 9.1. Kiểm tra đủ thuộc tính

Với cột mới, có thể cần xác minh:

- Tên và kiểu dữ liệu.
- Độ dài/precision/scale.
- Nullable hay NOT NULL.
- Default.
- Collation hoặc thuộc tính đặc thù.
- Constraint liên quan.

Với index, kiểm tra tên, cột và thứ tự cột, unique, predicate, phương thức và trạng thái hợp lệ nếu DBMS cung cấp.

Một assertion chỉ kiểm tra object tồn tại thường quá yếu.

## 10. Lớp 7 — Data assertions và tính đúng nghiệp vụ

Migration dữ liệu cần xác minh **nội dung sau chuyển đổi**, không chỉ số hàng.

Giả sử thêm cột status và backfill từ legacy_code:

~~~sql
UPDATE orders
SET status = CASE
    WHEN legacy_code = 'A' THEN 'ACTIVE'
    WHEN legacy_code = 'I' THEN 'INACTIVE'
    ELSE 'UNKNOWN'
END
WHERE status IS NULL;
~~~

Các assertion có thể gồm:

~~~sql
SELECT COUNT(*) AS missing_status
FROM orders
WHERE status IS NULL;
~~~

~~~sql
SELECT legacy_code, status, COUNT(*) AS row_count
FROM orders
GROUP BY legacy_code, status
ORDER BY legacy_code, status;
~~~

Cần kiểm tra:

- Không còn NULL ngoài dự kiến.
- Mapping giá trị đúng.
- Tổng số hàng trước/sau hợp lý.
- Không có hàng bị nhân đôi hoặc mất.
- Foreign key và uniqueness vẫn thỏa.
- Những ngoại lệ dữ liệu được xử lý theo quy tắc đã thống nhất.

### 10.1. Fixture phải bao phủ trường hợp biên

Dữ liệu test nên có:

- NULL.
- Chuỗi rỗng và khoảng trắng.
- Chữ hoa/chữ thường.
- Giá trị legacy hợp lệ và không hợp lệ.
- Giá trị lớn/nhỏ ở biên datatype.
- Dữ liệu có quan hệ foreign key.
- Bản ghi trùng theo quy tắc unique.
- Dữ liệu đủ lớn để bộc lộ vấn đề hiệu năng.

Không cần đưa dữ liệu production nhạy cảm vào CI. Dùng fixture tổng hợp hoặc bản sao đã ẩn danh hóa theo chính sách.

## 11. Lớp 8 — Kiểm thử precondition

Precondition xác định điều kiện cần có trước khi changeset chạy. Nó nên được test với cả trường hợp điều kiện đạt và không đạt.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-601-add-status"
      author: "orders-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: app
            tableName: orders
        - not:
            - columnExists:
                schemaName: app
                tableName: orders
                columnName: status
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)
~~~

Các tình huống test:

| Trạng thái đầu | Kỳ vọng |
|---|---|
| Bảng tồn tại, cột chưa có | Changeset được phép thực thi |
| Bảng không tồn tại | HALT theo cấu hình |
| Cột đã tồn tại nhưng history chưa ghi | HALT để điều tra trạng thái lệch |
| User thiếu quyền đọc metadata | Lỗi/condition error được xử lý đúng |
| Schema khác default schema | Kiểm tra đúng schema được chỉ định |

### 11.1. MARK_RAN cần assertion riêng

Nếu dùng **onFail:MARK_RAN**, test phải xác nhận chính xác điều gì khiến changeset được đánh dấu mà không chạy. Không được coi MARK_RAN tương đương EXECUTED.

Một test có thể xác minh EXECTYPE và schema cùng lúc. Nếu history ghi MARK_RAN nhưng object không đạt trạng thái yêu cầu, bài test phải fail.

### 11.2. Precondition không loại bỏ race condition

Precondition kiểm tra trạng thái tại thời điểm đánh giá. Một tiến trình khác có thể thay đổi schema sau đó. Nếu database có nhiều tác nhân DDL, cần kiểm soát concurrency và quyền, không chỉ dựa vào precondition.

## 12. Lớp 9 — Kiểm thử changeset identity và checksum

Liquibase thường nhận diện changeset theo bộ ba ID, AUTHOR và FILENAME/logicalFilePath. Sau khi triển khai, nội dung changeset được quản lý qua checksum.

Test nên phát hiện:

- ID trùng hoặc thay đổi ngoài chủ đích.
- Filename/logicalFilePath bị đổi khiến identity khác.
- Nội dung changeset đã triển khai bị sửa.
- Checksum mismatch.
- Changeset bị include hai lần.
- Changelog release cũ không còn được nạp.

Ví dụ truy vấn history:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    MD5SUM,
    EXECTYPE,
    DATEEXECUTED
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Tên/cột metadata cần xác minh theo phiên bản và cấu hình.

### 12.1. Không dùng clear-checksums như một cách làm test xanh

Nếu checksum mismatch, test phải làm lộ lỗi. Không tự động chạy clear-checksums hoặc sửa bảng history để CI qua. Hãy xác định artifact đã triển khai, nội dung changeset và schema thực tế; thay đổi đã phát hành thường cần changeset mới.

## 13. Lớp 10 — Kiểm thử idempotency và update lặp lại

Với changeset thông thường đã được ghi nhận, chạy update lần thứ hai thường không nên thực thi lại các change đã hoàn tất.

Kịch bản:

~~~text
1. Database ở baseline S0.
2. Chạy update -> S1.
3. Chạy update lần hai -> S1 vẫn ổn định.
4. So sánh schema/data và history trước/sau lần hai.
~~~

Kỳ vọng:

- Không có duplicate table/column/index.
- Không có side effect dữ liệu lặp.
- Không có changeset ngoài chủ đích được chạy lại.
- Các changeset runAlways/runOnChange được nhận diện riêng.

### 13.1. SQL không idempotent

Ví dụ:

~~~sql
UPDATE account_balance
SET amount = amount + 100;
~~~

Nếu bị chạy hai lần, số dư tăng thêm 200. Vì vậy, kiểm thử update lặp lại phải phát hiện changeset có thuộc tính runAlways/runOnChange hoặc logic SQL khiến dữ liệu bị thay đổi lặp ngoài ý muốn.

Idempotency không tự xuất hiện chỉ vì Liquibase có DATABASECHANGELOG. Các script ngoài Liquibase, retry thủ công hoặc thay đổi identity có thể tạo ra tình huống chạy lại.

## 14. Lớp 11 — Kiểm thử rollback và re-update

Rollback cần được test như một luồng độc lập:

~~~text
S0 --update--> S1 --rollback--> S0' --update--> S1'
~~~

Kiểm tra ở mỗi trạng thái:

| Giai đoạn | Schema | Dữ liệu | History |
|---|---|---|---|
| S0 | Baseline | Fixture gốc | Baseline recorded |
| S1 | Đã áp dụng migration | Data đã chuyển đổi | Changeset được ghi nhận |
| S0' | Trở về baseline theo hợp đồng | Dữ liệu được bảo toàn/khôi phục theo thiết kế | Changeset rollback được xử lý theo Liquibase |
| S1' | Trạng thái sau update lại | Kết quả nghiệp vụ đúng | Changeset được ghi nhận lại |

Không phải mọi changeset đều có thể tự động rollback. SQL tùy chỉnh, data migration hoặc DDL phá hủy có thể cần rollback thủ công, snapshot hoặc forward fix.

### 14.1. Preview rollback trước khi chạy

Tùy phiên bản và phạm vi, có thể dùng rollback SQL preview phù hợp như rollback-sql hoặc rollback-count-sql. Review SQL trước khi thực thi trên database test.

**Không dùng update-testing-rollback trên production.** Lệnh này có giai đoạn rollback thật và có thể phá hủy dữ liệu.

### 14.2. Rollback thành công không chứng minh dữ liệu được bảo toàn

Ví dụ rollback DROP TABLE có thể chạy thành công nhưng xóa mọi dữ liệu được ứng dụng ghi vào bảng sau update. Test phải kiểm tra dữ liệu và các invariant nghiệp vụ, không chỉ exit code.

## 15. Lớp 12 — Kiểm thử lỗi có chủ đích và phục hồi

Migration cần được thử với một số lỗi có kiểm soát trên database disposable:

- Thiếu quyền CREATE/ALTER.
- Bảng hoặc cột đã tồn tại.
- Constraint không thỏa dữ liệu.
- SQL syntax sai.
- Timeout hoặc lock timeout.
- Mất kết nối trong lúc chạy.
- Changeset ngoài transaction bị gián đoạn.
- DDL implicit commit để lại partial state.

Ví dụ changeset cố tạo cùng một bảng hai lần để mô phỏng lỗi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "TEST-001-duplicate-table"
      author: "test-team"
      changes:
        - createTable:
            tableName: retry_probe
            columns:
              - column:
                  name: id
                  type: bigint
        - createTable:
            tableName: retry_probe
            columns:
              - column:
                  name: id
                  type: bigint
~~~

Chỉ chạy trong database test được phép. Kết quả khác nhau theo DBMS và transaction behavior.

### 15.1. Kiểm tra schema sau khi lệnh lỗi

Đừng kết luận database chưa đổi chỉ vì Liquibase trả lỗi. Trên DBMS có implicit commit, một phần DDL có thể đã tồn tại. Sau lỗi, kiểm tra:

1. Schema catalog.
2. Dữ liệu bị tác động.
3. DATABASECHANGELOG.
4. DATABASECHANGELOGLOCK.
5. Log SQL/driver.
6. Transaction boundary và runInTransaction.

Chỉ retry khi đã xác định trạng thái thực tế và có kế hoạch reconciliation.

## 16. Lớp 13 — Kiểm thử tương thích ứng dụng

Migration thường diễn ra trong khi ứng dụng vẫn cần hoạt động. Một schema mới có thể đúng nhưng ứng dụng cũ không tương thích.

Ví dụ thêm cột NOT NULL không có default vào bảng đang được ứng dụng cũ insert có thể khiến phiên bản ứng dụng đó lỗi.

Kiểm thử tương thích cần xét:

- Phiên bản ứng dụng trước migration.
- Phiên bản ứng dụng sau migration.
- Các instance rolling deployment chạy đồng thời.
- Cách đọc/ghi cột mới.
- Null/default trong giai đoạn chuyển tiếp.
- View hoặc procedure mà ứng dụng phụ thuộc.
- Tính tương thích của rollback ứng dụng và database.

### 16.1. Expand–migrate–contract

Một chiến lược thường dùng:

1. **Expand:** thêm cấu trúc mới theo cách tương thích ngược.
2. **Deploy compatible app:** ứng dụng có thể đọc/ghi cả cấu trúc cũ và mới.
3. **Migrate:** backfill dữ liệu và xác minh.
4. **Switch:** chuyển ứng dụng sang cấu trúc mới.
5. **Contract:** loại bỏ cấu trúc cũ sau khi không còn instance phụ thuộc.

Test từng giai đoạn với phiên bản ứng dụng tương ứng. Không chỉ test trạng thái cuối khi mọi instance đã được nâng cấp.

## 17. Lớp 14 — Kiểm thử hiệu năng và thời gian khóa

Migration có thể chạy đúng trên database nhỏ nhưng gây downtime trên dữ liệu production.

Những thay đổi cần xem xét:

- ALTER TABLE trên bảng lớn.
- Tạo index.
- Backfill hàng triệu bản ghi.
- Thêm constraint cần scan dữ liệu.
- Rebuild table hoặc chuyển datatype.
- Update nhiều hàng trong một transaction dài.

Các chỉ số có thể thu thập:

- Tổng thời gian migration.
- Thời gian giữ lock và thời gian chờ lock.
- Số hàng đọc/ghi.
- WAL/redo hoặc transaction log tăng thêm.
- CPU, memory và I/O.
- Replication lag.
- Thời gian query ứng dụng bị chặn.
- Dung lượng index/table trước và sau.

### 17.1. Dữ liệu test phải đại diện

Nếu production có 100 triệu hàng, test với 100 hàng không thể chứng minh thời gian chạy hoặc lock behavior phù hợp. Dùng dataset tổng hợp có kích thước/phân bố gần thực tế hoặc bản sao đã xử lý dữ liệu nhạy cảm.

Không cần chạy performance test đầy đủ cho mọi thay đổi nhỏ; chọn theo mức rủi ro và quy mô đối tượng.

## 18. Lớp 15 — Kiểm thử concurrency và Liquibase lock

Nhiều pipeline có thể cùng cố chạy Liquibase trên một database. **DATABASECHANGELOGLOCK** giúp điều phối tiến trình Liquibase, nhưng không giải quyết mọi xung đột DDL.

Có thể kiểm thử:

- Hai tiến trình Liquibase cùng chạy update.
- Một tiến trình đang giữ lock, tiến trình khác phải chờ hoặc thất bại theo cấu hình.
- Tiến trình bị ngắt khi đang chạy.
- Lock còn lại sau sự cố.
- DBA hoặc ứng dụng chạy DDL ngoài Liquibase.

Kỳ vọng cần xác định:

- Chỉ một tiến trình được thực hiện migration tại một thời điểm theo cơ chế lock.
- Tiến trình còn lại không chạy chồng lấn ngoài kiểm soát.
- Sau failure, schema và history được điều tra.
- Không giải phóng lock thủ công khi vẫn còn tiến trình đang hoạt động.

### 18.1. Lock Liquibase khác lock DBMS

DATABASECHANGELOGLOCK điều phối Liquibase. DBMS còn có table lock, metadata lock, schema lock hoặc lock transaction riêng. Test lock Liquibase không chứng minh migration không chặn query ứng dụng.

## 19. Lớp 16 — Kiểm thử quyền và bảo mật

Tài khoản chạy migration thường có quyền DDL lớn hơn tài khoản ứng dụng. Cần kiểm thử:

- User migration có đủ quyền cho changeset cần chạy.
- User ứng dụng chỉ có quyền runtime cần thiết.
- Không ghi secret vào changelog hoặc log.
- Không cấp quyền DBA chỉ để test cho qua.
- Các object được tạo có owner/grant đúng.
- Stored procedure/function chạy với quyền dự kiến.
- Pipeline không dùng nhầm credential production trong test.

### 19.1. Test với quyền tối thiểu

Một test chỉ chạy bằng superuser có thể che giấu lỗi quyền của migration account thực tế. Nên có test sử dụng role tương đương môi trường triển khai, đồng thời tách test kiểm tra quyền khỏi test logic SQL nếu cần.

## 20. Kiểm thử nhiều DBMS và nhiều phiên bản

Nếu module hỗ trợ nhiều DBMS, cần xác định ma trận chính thức. Ví dụ:

| DBMS | Phiên bản test | Điều cần kiểm chứng |
|---|---|---|
| PostgreSQL | Phiên bản production và phiên bản nâng cấp kế tiếp | DDL transaction, index concurrent, JSON/sequence |
| MySQL | Phiên bản được hỗ trợ | Implicit commit, datatype, online DDL |
| MariaDB | Phiên bản được hỗ trợ | DDL behavior và dialect |
| Oracle | Phiên bản được hỗ trợ | DDL implicit commit, PL/SQL và sequence |
| SQL Server | Phiên bản được hỗ trợ | Batch, transaction, datatype và index |
| SQLite/H2 | Nếu thực sự là mục tiêu hỗ trợ | Giới hạn schema và khác biệt với production |

Không cần test mọi phiên bản tồn tại trên thị trường. Chọn phiên bản đang hỗ trợ, phiên bản đang vận hành và phiên bản đích của kế hoạch nâng cấp.

### 20.1. Test driver cũng quan trọng

Liquibase có thể tạo SQL khác nhau tùy DBMS và change type. JDBC driver ảnh hưởng metadata và thực thi. Khi cập nhật driver, nên chạy lại integration suite cho migration nhạy cảm.

## 21. Kiểm thử formatted SQL và sqlFile

Với SQL changelog hoặc sqlFile, cần kiểm tra:

- Encoding file.
- Relative path.
- splitStatements.
- endDelimiter.
- stripComments.
- SQL comment có chứa chỉ thị Liquibase hay không.
- Stored procedure/function body có dấu phân tách đặc biệt không.
- Executor có xử lý batch đúng không.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "PROC-101-create-refresh-procedure"
      author: "data-team"
      changes:
        - sqlFile:
            path: sql/create_refresh_procedure.sql
            relativeToChangelogFile: true
            splitStatements: false
            stripComments: false
~~~

Giá trị cụ thể phải phù hợp file SQL và DBMS. Test phải chạy bằng đúng executor/driver dự kiến; việc file tồn tại và YAML validate không chứng minh procedure tạo thành công.

## 22. Kiểm thử checksum và bất biến changelog

Một changeset đã triển khai cần được xem là bất biến. Test CI có thể phát hiện việc sửa file cũ theo policy:

- So sánh changeset trong pull request với nhánh nền.
- Xác định changeset đã được phát hành hoặc có trong history của môi trường.
- Báo lỗi khi sửa nội dung đã triển khai, trừ ngoại lệ có phê duyệt.
- Kiểm tra ID, author và filename/logicalFilePath.
- Không tự động chạy clear-checksums để bỏ qua mismatch.

Nếu changeset cũ cần điều chỉnh schema, thường tạo changeset mới. Integration test trên database có history thật sẽ giúp phát hiện checksum mismatch mà test database trống không thể thấy.

## 23. Kiểm thử data migration có tính chạy lại

Data migration cần đặc biệt chú ý tính **idempotent** và khả năng tiếp tục sau failure.

Ví dụ backfill theo batch có marker:

~~~sql
UPDATE orders
SET status = CASE
    WHEN legacy_status = 'A' THEN 'ACTIVE'
    WHEN legacy_status = 'I' THEN 'INACTIVE'
    ELSE 'UNKNOWN'
END
WHERE status IS NULL;
~~~

Test cần xác minh:

- Chạy lần đầu cập nhật đúng tập hàng.
- Chạy lại không làm thay đổi hàng đã hoàn tất ngoài dự kiến.
- Hàng NULL/legacy value được mapping đúng.
- Dữ liệu mới phát sinh trong lúc migration được xử lý.
- Có thể tiếp tục sau batch failure.
- Số hàng được xử lý và số ngoại lệ được ghi nhận.

Nếu migration dùng procedure hoặc external job, test cả tương tác với Liquibase và cơ chế vận hành của job đó.

## 24. Kiểm thử baseline và nâng cấp nhiều phiên bản

Ứng dụng lâu đời có thể cần hỗ trợ nâng cấp từ nhiều release cũ. Không chỉ test từ release ngay trước.

Ví dụ:

~~~text
v1.0 -> v1.1 -> v1.2 -> current
v1.1 -> v1.2 -> current
v1.2 -> current
empty -> current
~~~

Chọn những đường nâng cấp được hỗ trợ chính thức. Có thể dùng database fixture hoặc snapshot được tạo từ từng release.

Cần kiểm tra:

- History ban đầu.
- Schema/data baseline.
- Tập changeset pending.
- Kết quả update.
- Tương thích ứng dụng.
- Rollback hoặc forward fix theo chính sách.
- Khả năng tái tạo database từ changelog.

Không nên chỉ dựa vào một database dev đã chạy mọi changeset mà không biết xuất phát từ release nào.

## 25. Tích hợp với Spring Boot

Khi Spring Boot bật Liquibase auto-configuration, migration có thể chạy trong startup. Test cần xác nhận:

- Spring Boot nạp đúng changelog path.
- Datasource và Liquibase datasource trỏ đúng database.
- Context/labels đúng.
- Liquibase chạy trước khi component phụ thuộc schema được khởi tạo.
- Startup thất bại đúng khi migration lỗi.
- Nhiều application instance không gây chạy migration chồng lấn ngoài cơ chế điều phối.
- Tài khoản migration và tài khoản runtime có quyền phù hợp.

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_test
    username: app_runtime
    password: "<inject-at-runtime>"
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    user: migration_user
    password: "<inject-at-runtime>"
~~~

Đây là cấu hình minh họa; việc dùng datasource riêng cho Liquibase và cách truyền credential cần theo phiên bản Spring Boot, Liquibase và chính sách bảo mật của dự án.

### 25.1. Spring Boot integration test

Một test có thể khởi động application context với database container, sau đó kiểm tra:

- Liquibase đã áp dụng đúng changeset.
- Repository/JPA có thể truy vấn schema.
- Query và mapping không bị lỗi.
- Endpoint/service hoạt động với cấu trúc mới.

Không chỉ kiểm tra application context khởi động thành công; nên gọi ít nhất một đường truy cập dữ liệu đại diện.

## 26. Tổ chức CI/CD theo chi phí và rủi ro

Một pipeline có thể chia thành các tầng:

| Giai đoạn | Kiểm tra | Tần suất gợi ý |
|---|---|---|
| Pull request nhanh | Static checks, validate, identity, review | Mỗi PR |
| Pull request tích hợp | Fresh install và upgrade path trên DBMS chính | Mỗi PR có migration |
| Nightly | Ma trận DBMS/version, rollback, failure injection | Hằng ngày hoặc theo lịch |
| Release candidate | Performance, locking, data migration trên dữ liệu đại diện | Trước phát hành |
| Production rollout | Preflight, update-sql review, deployment verification | Mỗi lần phát hành |

Không phải dự án nào cũng cần đầy đủ tất cả giai đoạn, nhưng mọi migration cần ít nhất một lớp kiểm thử thực thi trên DBMS mục tiêu trước khi triển khai production.

### 26.1. Database riêng cho mỗi job

Một CI job nên có database/schema riêng để tránh:

- Job khác đã tạo object trước.
- Rollback của job này phá dữ liệu job kia.
- DATABASECHANGELOG bị chia sẻ ngoài ý muốn.
- Test phụ thuộc vào thứ tự chạy.
- Kết quả không tái lập.

Nếu dùng schema riêng thay vì database riêng, xác minh DBMS và Liquibase metadata/lock cũng được cô lập đúng. Không chỉ đổi default schema mà để hai job dùng chung DATABASECHANGELOGLOCK.

## 27. Lưu bằng chứng kiểm thử

Một kết quả migration test cần có thể truy vết.

Nên lưu:

- Commit hash hoặc artifact changelog.
- Liquibase version.
- DBMS/version.
- JDBC driver.
- Database fixture/baseline version.
- Context, labels và các filter.
- Kết quả validate/status/update-sql.
- Log update/rollback.
- Schema assertions và data assertions.
- DATABASECHANGELOG identity, EXECTYPE và deployment metadata nếu có.
- Thời gian migration, lock wait và metrics liên quan.
- Kết luận Pass/Fail và issue cần xử lý.

Không lưu password, token hoặc dữ liệu cá nhân trong log. Nếu log chứa hostname nội bộ hoặc tên schema nhạy cảm, áp dụng quyền truy cập và retention phù hợp.

## 28. Phân loại lỗi test và cách xử lý

| Nhóm lỗi | Ví dụ | Hướng điều tra |
|---|---|---|
| Cấu trúc | YAML sai, include thiếu | Static check/validate |
| Identity/history | Checksum mismatch, duplicate changeset | ID/author/path và DATABASECHANGELOG |
| Dialect | SQL sai trên Oracle/MySQL | DBMS/version/driver |
| Permission | User không có quyền ALTER | Role và grants |
| Data | NOT NULL/unique fail | Fixture, precondition, backfill |
| Transaction | Partial DDL sau lỗi | DBMS behavior, runInTransaction |
| Dependency | Index trước column | Include order và object graph |
| Locking | Migration chờ lâu | DBMS lock, concurrency, query workload |
| Rollback | Không đảo được SQL/data | Custom rollback, forward fix, backup |
| Application | ORM/query lỗi sau migration | Compatibility và integration test |
| CI isolation | Test phụ thuộc job khác | Database riêng và cleanup |
| Configuration | Sai URL/schema/filter | Connection identity và runtime config |

Khi test fail, giữ lại log và trạng thái database để điều tra. Đừng tự động reset database hoặc xóa history trước khi xác định nguyên nhân, đặc biệt khi test đang mô phỏng failure giữa chừng.

## 29. Ví dụ kiểm thử hoàn chỉnh cho changeset thêm cột

Changelog minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "ORD-701-add-status"
      author: "orders-team"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: app
            tableName: orders
        - not:
            - columnExists:
                schemaName: app
                tableName: orders
                columnName: status
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: status
                  type: varchar(24)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: orders
            columnName: status
~~~

### 29.1. Test trên database trống

Nếu database trống không có bảng orders, precondition sẽ HALT. Điều này có thể là đúng nếu changelog này chỉ dành cho upgrade từ baseline. Nếu mục tiêu là fresh install, cần chạy toàn bộ baseline trước.

### 29.2. Test trên database baseline

- Tạo bảng orders theo release trước.
- Nạp dữ liệu cũ.
- Chạy validate và status.
- Chạy update-sql.
- Chạy update.
- Xác minh status tồn tại và kiểu đúng.
- Xác minh dữ liệu cũ được giữ nguyên.
- Xác minh DATABASECHANGELOG ghi nhận đúng changeset.

### 29.3. Test precondition fail

Tạo fixture trong đó cột status đã tồn tại nhưng changeset chưa được ghi nhận. Kỳ vọng HALT, không tự MARK_RAN. Điều tra vì sao schema và history lệch nhau.

### 29.4. Test rollback và update lại

Trên database disposable:

- Review rollback-sql.
- Rollback changeset.
- Xác minh cột status không còn.
- Update lại.
- Xác minh cột và history trở lại đúng.

Nếu cột đã nhận dữ liệu cần giữ, rollback dropColumn có thể phá hủy dữ liệu; test cần xác nhận đây chỉ là fixture dùng cho schema test.

## 30. Ví dụ test data migration có assertion

Giả sử cột legacy_state chứa A/I/U và migration chuyển sang status:

~~~sql
UPDATE customer
SET status = CASE
    WHEN legacy_state = 'A' THEN 'ACTIVE'
    WHEN legacy_state = 'I' THEN 'INACTIVE'
    WHEN legacy_state = 'U' THEN 'UNKNOWN'
    ELSE 'UNKNOWN'
END
WHERE status IS NULL;
~~~

Test fixture:

| id | legacy_state | status trước | status mong đợi |
|---:|---|---|---|
| 1 | A | NULL | ACTIVE |
| 2 | I | NULL | INACTIVE |
| 3 | U | NULL | UNKNOWN |
| 4 | NULL | NULL | UNKNOWN |
| 5 | A | ACTIVE | ACTIVE |

Assertions:

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM customer
WHERE status IS NULL
   OR status NOT IN ('ACTIVE', 'INACTIVE', 'UNKNOWN');
~~~

Kỳ vọng invalid_rows bằng 0 nếu hợp đồng yêu cầu mọi hàng thuộc một trong ba giá trị.

Cũng cần xác nhận số hàng và mapping cụ thể. Nếu có giá trị legacy không nhận diện, test phải thể hiện chính sách xử lý, không để CASE mặc định che giấu dữ liệu bất thường mà không có báo cáo.

## 31. Những hiểu nhầm cần tránh

| Hiểu nhầm | Thực tế |
|---|---|
| validate pass nghĩa SQL chạy được | Validate không thực thi migration trên DBMS |
| update-sql pass nghĩa update sẽ pass | Preview không kiểm tra quyền, dữ liệu, lock và runtime |
| Test trên H2 đủ cho PostgreSQL/MySQL | Dialect và transaction behavior khác nhau |
| History có changeset nghĩa schema vẫn đúng | Có thể drift sau khi triển khai |
| Changeset rollback thành công nghĩa dữ liệu an toàn | Rollback có thể xóa dữ liệu phát sinh |
| Database trống test pass nghĩa upgrade pass | Upgrade path có trạng thái/data cũ khác |
| Mock JDBC đủ kiểm tra Liquibase | Mock không kiểm tra DBMS thật |
| Exit code 0 là đủ | Cần schema/data assertions và history |
| Chạy update hai lần luôn vô hại | runAlways/runOnChange hoặc SQL không idempotent có thể tạo side effect |
| DATABASECHANGELOGLOCK ngăn mọi xung đột | Chỉ điều phối tiến trình Liquibase trên metadata DB |
| Precondition bảo đảm không có race | Trạng thái có thể đổi sau khi kiểm tra |
| Test nhỏ chứng minh hiệu năng production | Dataset và workload không đại diện |
| MARK_RAN tương đương EXECUTED | Changeset có thể không chạy SQL |
| Clear-checksums là cách sửa migration | Không sửa schema hay khôi phục lịch sử |

## 32. Checklist thiết kế test strategy cho migration

- [ ] Đã phân loại loại migration và mức rủi ro.
- [ ] Có tiêu chí chấp nhận kiểm tra được cho schema và dữ liệu.
- [ ] Static checks và code review được chạy trên mỗi PR.
- [ ] Chạy Liquibase validate.
- [ ] Chạy status với filter phù hợp môi trường.
- [ ] Review update-sql trước khi thực thi.
- [ ] Có unit test cho logic custom/precondition khi phù hợp.
- [ ] Integration test dùng DBMS/version đại diện.
- [ ] Có test fresh install từ database trống.
- [ ] Có test upgrade từ baseline/release trước.
- [ ] Fixture chứa dữ liệu biên và quan hệ cần thiết.
- [ ] Có schema assertions sau update.
- [ ] Có data assertions và đối chiếu số hàng/mapping.
- [ ] Kiểm tra DATABASECHANGELOG và identity/checksum.
- [ ] Test precondition pass, fail và MARK_RAN nếu sử dụng.
- [ ] Test update lặp lại và idempotency.
- [ ] Test rollback/re-update trên database disposable.
- [ ] Có failure injection cho thay đổi rủi ro cao.
- [ ] Kiểm tra DBMS transaction và implicit commit.
- [ ] Đánh giá tương thích ứng dụng trong rolling deployment.
- [ ] Performance/lock test cho bảng lớn hoặc DDL nặng.
- [ ] Concurrency test khi nhiều pipeline có thể chạy migration.
- [ ] Permission test bằng tài khoản gần với production.
- [ ] CI database được cô lập theo job/branch.
- [ ] Log, artifact, DBMS version và kết quả test được lưu.
- [ ] Không dùng production làm nơi thử rollback hoặc failure injection.
- [ ] Có phương án forward fix/backup cho thay đổi không thể đảo ngược.

**Kết luận:** Kiểm thử migration hiệu quả là một hệ thống nhiều lớp. Static checks và validate phát hiện lỗi cấu trúc sớm; status/update-sql hỗ trợ xác định và review thay đổi; integration test trên DBMS thật xác nhận SQL; schema/data assertions xác nhận kết quả; rollback, retry, compatibility, performance và concurrency test đánh giá rủi ro vận hành. Hãy luôn kiểm tra cả database mới lẫn đường nâng cấp từ baseline, cô lập database cho từng CI job và lưu bằng chứng theo artifact/version cụ thể. Khi mỗi lớp có mục tiêu và tiêu chí Pass/Fail rõ ràng, nhóm có thể phát hiện lỗi migration trước phát hành và triển khai Liquibase đáng tin cậy qua nhiều môi trường.

