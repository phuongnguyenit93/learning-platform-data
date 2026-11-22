# Chuyển đổi và bổ sung dữ liệu cũ trước khi siết ràng buộc

## 1. Vấn đề cốt lõi: schema mới phải tiếp nhận được dữ liệu đã tồn tại

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase giúp quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Quy trình học còn bao gồm migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Với một hệ thống đang hoạt động, việc thêm ràng buộc dữ liệu không chỉ là chạy một lệnh DDL: **các bản ghi cũ và những bản ghi mới phát sinh trong khi triển khai đều phải thỏa quy tắc mới**.

Giả sử bảng `customer_account` trước đây có cột `status_text` kiểu chuỗi, cho phép các giá trị `active`, `enabled`, `disabled`, `suspended`, chuỗi rỗng và `NULL`. Phiên bản mới muốn dùng cột `status_code` với đúng ba mã `ACTIVE`, `SUSPENDED`, `PENDING`, không cho phép `NULL` và có khóa ngoại đến bảng danh mục `account_status_catalog`.

Nếu tạo cột mới rồi lập tức thêm `NOT NULL`, migration sẽ thất bại vì mọi hàng cũ đang có `status_code = NULL`. Nếu đổi dữ liệu bằng một câu `UPDATE` chưa được kiểm tra, các giá trị lạ có thể bị mất nghĩa hoặc được gán nhầm. Nếu backfill xong rồi một phiên bản ứng dụng cũ tiếp tục ghi dữ liệu thiếu `status_code`, lệnh siết ràng buộc ở bước sau vẫn có thể thất bại.

Vì vậy, thứ tự đáng tin cậy là:

```text
Khảo sát dữ liệu cũ + thống nhất quy tắc nghiệp vụ
                    |
                    v
EXPAND: thêm cấu trúc mới còn tương thích
                    |
                    v
Chuẩn hóa và bổ sung dữ liệu (backfill)
                    |
                    v
VERIFY: đối soát và ngăn dữ liệu sai mới phát sinh
                    |
                    v
CONSTRAIN: thêm NOT NULL / FK / UNIQUE / CHECK
                    |
                    v
CONTRACT: ngừng dùng và loại bỏ cấu trúc cũ khi an toàn
```

Quy trình này thường được gọi là **expand–migrate–contract**. Trong thực tế có thể phải lặp lại backfill và đối soát khi dữ liệu vẫn đang được ghi, hoặc tách mỗi giai đoạn thành một lần phát hành.

## 2. Phân biệt chuyển đổi, bổ sung và siết ràng buộc

Ba nhóm thao tác bổ trợ nhau nhưng giải quyết những vấn đề khác nhau:

| Nhóm | Ví dụ | Điều phải chứng minh trước khi tiếp tục |
|---|---|---|
| Chuyển đổi dữ liệu | `"enabled" → "ACTIVE"`, chuỗi ngày thành ngày chuẩn, số tiền text thành numeric | Biểu diễn mới giữ đúng ý nghĩa nghiệp vụ, không mất dữ liệu ngoài quy tắc đã phê duyệt |
| Bổ sung dữ liệu cũ | Điền `status_code` cho các hàng đã tồn tại, tạo danh mục trạng thái, bổ sung khóa tham chiếu | Không còn bản ghi chưa được xử lý; bản ghi mới tiếp tục được điền đúng |
| Siết ràng buộc | `NOT NULL`, `FOREIGN KEY`, `UNIQUE`, `CHECK` | Toàn bộ dữ liệu hiện tại đạt điều kiện, ứng dụng có khả năng tiếp tục duy trì điều kiện ấy |

**Schema migration** mô tả thay đổi cấu trúc, còn **data migration** mô tả thay đổi các giá trị trong bảng. Một changeset Liquibase có thể chứa DDL và DML, nhưng với những bước có rủi ro, nên tách rõ để có thể kiểm chứng, điều phối thời điểm triển khai và phân tích lỗi.

Mọi quy tắc gán giá trị thay thế phải xuất phát từ nghiệp vụ. Ví dụ, `NULL` có thể nghĩa là “chưa xác định”, “đang xử lý” hoặc “trạng thái cũ không được ghi”; **không được tự suy rằng `NULL` luôn tương đương `PENDING`**. Trong ví dụ xuyên suốt của bài này, giả định nhóm nghiệp vụ **đã phê duyệt** quy tắc `NULL`/chuỗi rỗng → `PENDING`. Nếu không có phê duyệt đó, phải giữ dữ liệu chưa rõ trong danh sách ngoại lệ hoặc khoanh vùng xử lý thủ công.

## 3. Khảo sát dữ liệu cũ trước khi viết changeset

Bước đầu tiên là hiểu chính xác dữ liệu thực tế, không chỉ dựa vào kiểu cột và tài liệu API. Ví dụ các truy vấn dưới đây dùng PostgreSQL; với DBMS khác, cú pháp hàm và catalog có thể khác.

### 3.1. Kiểm kê giá trị và mức độ bất thường

```sql
SELECT
    CASE
        WHEN status_text IS NULL THEN '<NULL>'
        WHEN btrim(status_text) = '' THEN '<BLANK>'
        ELSE lower(btrim(status_text))
    END AS normalized_legacy_status,
    COUNT(*) AS row_count
FROM customer_account
GROUP BY 1
ORDER BY row_count DESC;
```

Truy vấn này giúp nhận diện các trường hợp chưa dự kiến, chẳng hạn `"waiting"` hoặc `"terminated"`. Cũng cần xem dữ liệu theo thời gian, vùng nghiệp vụ hoặc nhóm khách hàng để tránh coi một giá trị ít xuất hiện là giá trị lỗi rồi tùy tiện chuyển nó thành trạng thái mặc định.

### 3.2. Công bố bảng ánh xạ được duyệt

Trong ví dụ, quy tắc chuyển đổi đã được chấp thuận là:

| `status_text` cũ sau trim/lowercase | `status_code` mới | Lý do |
|---|---|---|
| `active`, `enabled` | `ACTIVE` | Cùng biểu diễn tài khoản hoạt động |
| `suspended`, `disabled` | `SUSPENDED` | Cùng biểu diễn tài khoản bị tạm dừng |
| `NULL` hoặc chuỗi rỗng | `PENDING` | Quyết định nghiệp vụ đã được xác nhận |
| Bất kỳ giá trị nào khác | Không tự chuyển | Phải xác minh hoặc sửa nguồn dữ liệu |

Ánh xạ **nhiều-một** có thể làm mất phân biệt giữa dữ liệu ban đầu: sau khi chỉ còn `ACTIVE`, không thể biết bản ghi vốn là `active` hay `enabled`. Đây là nguyên nhân rollback dữ liệu có thể **không đảo ngược được**, ngay cả khi schema cũ vẫn tồn tại.

### 3.3. Đếm những dòng không thể chuyển theo quy tắc

```sql
SELECT COUNT(*) AS unmapped_rows
FROM customer_account
WHERE status_text IS NOT NULL
  AND btrim(status_text) <> ''
  AND lower(btrim(status_text)) NOT IN
      ('active', 'enabled', 'suspended', 'disabled');
```

Kỳ vọng `unmapped_rows = 0` trước khi tự động backfill. Nếu kết quả khác 0, cần sửa dữ liệu bằng một thay đổi có thể truy vết hoặc dùng quy trình phê duyệt ngoại lệ. Không dùng `ELSE 'PENDING'` cho tất cả giá trị lạ chỉ để migration hoàn tất.

Ngoài giá trị cột, cần khảo sát số dòng, tốc độ ghi, index, foreign key, default, trigger và các job xử lý dữ liệu vì chúng có thể ảnh hưởng lock, thời gian chạy và khả năng áp dụng thay đổi.

## 4. Thiết kế các bất biến để kiểm chứng

Một migration an toàn nên công bố **bất biến (invariant)** trước khi triển khai. Đối với ví dụ:

1. Mọi hàng trong `customer_account` có `status_code` thuộc `ACTIVE`, `SUSPENDED` hoặc `PENDING`.
2. Mọi `status_code` tồn tại trong `account_status_catalog.code`.
3. Sau backfill, không còn `status_code IS NULL`.
4. Giá trị mới tương ứng với quy tắc ánh xạ legacy đã phê duyệt tại thời điểm chuyển đổi.
5. Các giao dịch tạo/cập nhật tài khoản từ ứng dụng không phát sinh giá trị mới vi phạm bất biến.
6. Không làm mất hoặc làm thay đổi nhầm bản ghi không thuộc phạm vi migration.
7. Trên mỗi môi trường, Liquibase vẫn nhận diện đúng changeset qua `id`, `author` và đường dẫn changelog.

Không nhất thiết nhồi mọi bất biến vào `preConditions` của Liquibase. Một số có thể đo bằng truy vấn hậu kiểm, test nghiệp vụ hoặc giám sát ứng dụng. Tuy vậy, điều kiện **bắt buộc phải đúng trước khi thêm constraint** nên có cổng kiểm tra rõ ràng và dừng an toàn nếu không đạt.

## 5. Giai đoạn EXPAND: chuẩn bị cấu trúc mà chưa phá vỡ ứng dụng cũ

Giả sử bảng `customer_account` hiện có khóa chính `id` và cột `status_text`; nó chưa có `status_code`. Đầu tiên tạo bảng mã trạng thái, nạp dữ liệu tham chiếu và thêm cột mới **cho phép NULL**.

### 5.1. Tạo danh mục và dữ liệu tham chiếu

Ví dụ changelog YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-create-account-status-catalog
      author: migration-team
      changes:
        - createTable:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  type: varchar(20)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: varchar(100)
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: account_status_catalog

  - changeSet:
      id: 20261119-02-seed-account-status-catalog
      author: migration-team
      changes:
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: ACTIVE
              - column:
                  name: display_name
                  value: Active
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: SUSPENDED
              - column:
                  name: display_name
                  value: Suspended
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: PENDING
              - column:
                  name: display_name
                  value: Pending
      rollback:
        - delete:
            tableName: account_status_catalog
            where: "code IN ('ACTIVE', 'SUSPENDED', 'PENDING')"
```

Dữ liệu danh mục `ACTIVE`/`SUSPENDED`/`PENDING` là **dữ liệu tham chiếu bắt buộc**, không phải dữ liệu thử nghiệm. Nó cần xuất hiện trên các môi trường sử dụng schema này, bao gồm production.

Rollback dữ liệu danh mục chỉ an toàn khi các bản ghi không còn được bảng khác tham chiếu và không chứa thông tin phát sinh sau đó. Sau khi đã tạo khóa ngoại và có dữ liệu nghiệp vụ, không thể tùy ý xóa ba mã này chỉ vì rollback một changeset.

### 5.2. Thêm cột mới nullable

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-03-add-status-code
      author: migration-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: status_code
                  type: varchar(20)
      rollback:
        - dropColumn:
            tableName: customer_account
            columnName: status_code
```

Không thêm `NOT NULL` trong cùng bước này: các hàng cũ chưa có giá trị. Cũng không vội xóa `status_text`: các phiên bản ứng dụng cũ có thể vẫn đọc và ghi cột này trong giai đoạn rolling deployment.

Nếu muốn thêm giá trị mặc định cho các bản ghi **mới**, Liquibase hỗ trợ `addDefaultValue`. Tuy nhiên, giá trị mặc định ở schema không tự chứng minh dữ liệu cũ đã được gán đúng nghiệp vụ, và hành vi với dữ liệu cũ phụ thuộc DBMS/cách thực hiện DDL. Không dùng default để che giấu những trạng thái lịch sử chưa xác định.

## 6. Giai đoạn MIGRATE: backfill có kiểm tra và xử lý ngoại lệ

Backfill là quá trình điền dữ liệu vào cấu trúc mới dựa trên dữ liệu đã có. Với bảng nhỏ và khoảng thời gian triển khai được kiểm soát, có thể thực hiện bằng một changeset chứa `sql`. Với bảng lớn, nên chia lô (phần 10).

### 6.1. Chặn dữ liệu ngoài bảng ánh xạ trước khi cập nhật

Ví dụ PostgreSQL:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-04-backfill-status-code
      author: migration-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer_account
        - columnExists:
            tableName: customer_account
            columnName: status_code
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account
              WHERE status_code IS NULL
                AND status_text IS NOT NULL
                AND btrim(status_text) <> ''
                AND lower(btrim(status_text)) NOT IN
                    ('active', 'enabled', 'suspended', 'disabled')
      changes:
        - sql:
            sql: |
              UPDATE customer_account
              SET status_code =
                  CASE
                      WHEN status_text IS NULL
                        OR btrim(status_text) = ''
                        THEN 'PENDING'
                      WHEN lower(btrim(status_text)) IN
                           ('active', 'enabled')
                        THEN 'ACTIVE'
                      WHEN lower(btrim(status_text)) IN
                           ('suspended', 'disabled')
                        THEN 'SUSPENDED'
                  END
              WHERE status_code IS NULL;
```

**Các quyết định kỹ thuật cần hiểu:**

- `dbms: postgresql` làm rõ ví dụ dùng cú pháp `btrim` và các lựa chọn SQL của PostgreSQL; nếu hỗ trợ nhiều DBMS, cần viết và kiểm thử SQL tương ứng.
- `sqlCheck` trả về số lượng dòng ngoài bảng ánh xạ; `expectedResult: "0"` chặn migration nếu còn dữ liệu chưa thể phân loại.
- `onFail: HALT` dừng có chủ đích. Không thay bằng `MARK_RAN` vì đánh dấu changeset hoàn tất khi dữ liệu chưa được điền sẽ làm lịch sử khác trạng thái thực tế.
- `WHERE status_code IS NULL` hạn chế ghi đè những giá trị đã điền trước đó. Tuy nhiên, nó **không đủ** để giải quyết mọi trường hợp thay đổi nguồn hoặc chạy đồng thời.
- Nếu có các giá trị legacy lạ trong những dòng đã có `status_code`, precondition trên không bắt buộc chặn; cần đối soát toàn bảng sau backfill và điều tra sự khác biệt.

Với chuyển đổi nhiều-một, không thể tự viết rollback để khôi phục chính xác `active` so với `enabled` nếu cột cũ đã bị xóa. Vì vậy, ví dụ trên **không khai báo rollback SQL giả tạo** cho thao tác dữ liệu. Trước khi cho phép rollback tự động qua changeset này, cần có phương án khôi phục/snapshot được phê duyệt, hoặc thực hiện migration bù đã được kiểm chứng.

### 6.2. Vì sao không chọn mặc định cho giá trị lỗi?

Xét một bản ghi có `status_text = 'closed'`. Nếu logic dùng `ELSE 'PENDING'`, nó có thể biến một tài khoản đã đóng thành tài khoản chờ kích hoạt, làm sai nghiệp vụ và thậm chí ảnh hưởng quyền truy cập.

Quy trình đúng là ghi nhận số lượng và ID bị ảnh hưởng, phân loại lỗi, lấy quyết định nghiệp vụ và áp dụng thay đổi riêng có thể review. Nếu cần sửa nhiều giá trị lịch sử, có thể xây dựng bảng ánh xạ dữ liệu được quản lý phiên bản hoặc dùng `loadData`/`loadUpdateData` với file CSV rõ nguồn gốc, chú ý encoding, dấu phân cách, kiểu và khóa đối chiếu.

## 7. Giai đoạn VERIFY: xác minh dữ liệu trước khi siết constraint

Sau backfill, đừng coi thông báo “changeset executed” là chứng cứ duy nhất. Cần đo trạng thái thực.

### 7.1. Không còn NULL hoặc mã không có trong danh mục

```sql
SELECT COUNT(*) AS unresolved_count
FROM customer_account c
WHERE c.status_code IS NULL
   OR NOT EXISTS (
       SELECT 1
       FROM account_status_catalog s
       WHERE s.code = c.status_code
   );
```

Kỳ vọng `unresolved_count = 0`. Truy vấn này bắt cả `NULL` lẫn mã không có trong bảng danh mục, tương ứng hai ràng buộc sắp được thêm.

### 7.2. Đối soát với quy tắc ánh xạ legacy

Trong PostgreSQL, có thể kiểm tra những dòng vẫn giữ `status_text`:

```sql
SELECT COUNT(*) AS mismatch_count
FROM customer_account c
WHERE c.status_code IS DISTINCT FROM
    CASE
        WHEN c.status_text IS NULL
          OR btrim(c.status_text) = ''
          THEN 'PENDING'
        WHEN lower(btrim(c.status_text)) IN ('active', 'enabled')
          THEN 'ACTIVE'
        WHEN lower(btrim(c.status_text)) IN ('suspended', 'disabled')
          THEN 'SUSPENDED'
    END;
```

Kỳ vọng `mismatch_count = 0` **nếu** ứng dụng còn duy trì `status_text` theo cùng ngữ nghĩa và không có bản ghi nguồn chưa phân loại. Khi hệ thống đã chuyển sang `status_code` làm nguồn dữ liệu chính, cột legacy có thể không được cập nhật nữa; lúc đó không thể tiếp tục dùng phép so sánh này như tiêu chí tuyệt đối. Cần xác định rõ thời điểm snapshot, quy tắc đồng bộ và những trường hợp được chấp nhận.

Có thể kiểm tra phân bố sau chuyển đổi:

```sql
SELECT status_code, COUNT(*) AS row_count
FROM customer_account
GROUP BY status_code
ORDER BY status_code;
```

So sánh số lượng trước/sau, một số mẫu dữ liệu biên và các bất biến nghiệp vụ. Với dữ liệu tài chính hoặc định danh, đối soát còn phải bao gồm tổng tiền, số bản ghi, khóa logic và những giá trị có khả năng mất thông tin do chuyển đổi.

### 7.3. Xác minh các ứng dụng còn tạo dữ liệu mới

Báo cáo `unresolved_count = 0` vào lúc 10:00 không bảo đảm vẫn bằng 0 lúc 10:05. Nếu một phiên bản ứng dụng cũ tiếp tục INSERT mà không điền `status_code`, có thể lại phát sinh NULL. Cần kiểm soát writer bằng một hoặc nhiều cách:

1. Triển khai ứng dụng chuyển tiếp ghi cả `status_text` và `status_code` trong một transaction phù hợp.
2. Backfill lại những dòng phát sinh trước khi cutover, có checkpoint và đối soát.
3. Tạm giới hạn ghi ở thời điểm siết ràng buộc, nếu hệ thống cho phép.
4. Dùng cơ chế đồng bộ ở database khi thực sự cần, nhưng phải kiểm thử trigger và vòng đời vận hành.
5. Chỉ thêm constraint khi phiên bản ứng dụng đang chạy đã tương thích.

Precondition kiểm tra dữ liệu và thao tác DDL không mặc nhiên tạo một “khoảng thời gian không có ghi đồng thời”. Tính nguyên tử và hành vi khóa phụ thuộc DBMS, isolation và cách chia transaction của changeset.

## 8. Giai đoạn CONSTRAIN: thêm NOT NULL và khóa ngoại sau khi đã sạch dữ liệu

Sau khi đã đối soát và kiểm soát writer, mới siết ràng buộc.

### 8.1. Siết NOT NULL với chốt kiểm tra

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-05-require-status-code
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account
              WHERE status_code IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer_account
            columnName: status_code
            columnDataType: varchar(20)
      rollback:
        - dropNotNullConstraint:
            tableName: customer_account
            columnName: status_code
            columnDataType: varchar(20)
```

Precondition giảm nguy cơ tiến hành sai, nhưng chính ràng buộc ở database mới là cơ chế bắt buộc các ghi mới tuân thủ `NOT NULL`. Trước khi áp dụng vào bảng lớn, cần xem SQL sinh ra, thời gian kiểm tra dữ liệu và loại lock của DBMS.

### 8.2. Thêm khóa ngoại để bảo vệ tập giá trị

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-06-add-status-reference
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account c
              WHERE c.status_code IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1
                    FROM account_status_catalog s
                    WHERE s.code = c.status_code
                )
      changes:
        - addForeignKeyConstraint:
            constraintName: fk_customer_account_status
            baseTableName: customer_account
            baseColumnNames: status_code
            referencedTableName: account_status_catalog
            referencedColumnNames: code
      rollback:
        - dropForeignKeyConstraint:
            baseTableName: customer_account
            constraintName: fk_customer_account_status
```

Ràng buộc khóa ngoại đảm bảo mỗi mã trạng thái tồn tại trong danh mục; nó **không** tự cấm NULL, nên cả `NOT NULL` và FK đều cần thiết theo yêu cầu. Cần đảm bảo kiểu dữ liệu của cột tham chiếu tương thích, bảng danh mục có khóa được tham chiếu hợp lệ và chính sách `ON UPDATE`/`ON DELETE` phù hợp nghiệp vụ.

Việc chia thành changeset riêng giúp biết bước nào thất bại. Tuy nhiên, không được đổi `id`/`author` hoặc nội dung changeset đã chạy để “sửa nhanh” ở production: Liquibase dựa vào bộ định danh và checksum để theo dõi lịch sử. Sửa lỗi sau triển khai thường cần changeset mới.

### 8.3. Có nên thêm CHECK nữa không?

Nếu FK đã ràng buộc `status_code` đến bảng danh mục, CHECK dạng `status_code IN ('ACTIVE','SUSPENDED','PENDING')` có thể lặp lại cùng mục tiêu và gây khó khăn khi bổ sung trạng thái mới. Dùng FK nếu tập giá trị là dữ liệu tham chiếu có thể phát triển; dùng CHECK nếu quy tắc đơn giản, ổn định và phù hợp với thiết kế. Một số hệ thống có thể cần cả hai cho các bất biến khác nhau, nhưng không nên thêm hai ràng buộc tương đương mà thiếu lý do.

## 9. Các ràng buộc khác cũng cần backfill và làm sạch dữ liệu

### 9.1. UNIQUE: phải xử lý trùng dữ liệu trước

Ví dụ cần đảm bảo email duy nhất sau chuẩn hóa. Trước khi tạo unique constraint, kiểm tra trùng theo quy tắc nghiệp vụ:

```sql
SELECT lower(btrim(email)) AS normalized_email,
       COUNT(*) AS occurrences
FROM customer_account
WHERE email IS NOT NULL
  AND btrim(email) <> ''
GROUP BY lower(btrim(email))
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;
```

Không tự xóa tất cả bản ghi “trùng” vì mỗi dòng có thể có đơn hàng, quyền hoặc lịch sử riêng. Cần xác định bản ghi chính, cách hợp nhất dữ liệu, khóa ngoại tham chiếu và lưu lại mapping ID để đối soát.

**Chú ý:** `UNIQUE(email)` thông thường không nhất thiết có cùng ngữ nghĩa với duy nhất theo `lower(btrim(email))`. Nếu nghiệp vụ cần duy nhất không phân biệt hoa thường, có thể cần cột email chuẩn hóa hoặc functional index / collation tương ứng theo DBMS, đồng thời điều chỉnh ứng dụng để duy trì chuẩn hóa. Phải kiểm chứng quy tắc NULL và collation của hệ quản trị.

Sau khi dữ liệu đạt điều kiện của ràng buộc muốn tạo, Liquibase hỗ trợ `addUniqueConstraint` cho các trường hợp phù hợp. Không thêm nó trước bước phân tích duplicate.

### 9.2. CHECK: kiểm chứng giá trị cũ và semantics của NULL

Ví dụ ràng buộc `amount >= 0` yêu cầu kiểm tra dữ liệu âm và NULL. Trong SQL, `CHECK (amount >= 0)` có thể chấp nhận NULL vì biểu thức cho kết quả UNKNOWN; nếu NULL bị cấm thì cần thêm `NOT NULL` riêng. Kiểm tra bằng dữ liệu hiện tại và xác định có chấp nhận khoản hoàn tiền âm hay không trước khi siết constraint.

### 9.3. NOT NULL: mặc định không đồng nghĩa với backfill đúng

Thêm `DEFAULT` cho một cột có thể hỗ trợ các lệnh INSERT mới không truyền giá trị, nhưng không thay thế việc kiểm tra dữ liệu cũ. Liquibase có tùy chọn như `defaultNullValue` của `addNotNullConstraint` ở các trường hợp được hỗ trợ; nếu dùng, cần hiểu nó có thể thay NULL bằng một giá trị cụ thể. Với dữ liệu nghiệp vụ, nên chuyển đổi tường minh và đối soát, tránh tự động gán một trạng thái gây mất nghĩa.

### 9.4. Khóa ngoại: phát hiện bản ghi mồ côi

Trước khi thêm FK cho cột `customer_id` ở bảng `orders`, tìm các dòng có mã tham chiếu không tồn tại. Không thay chúng hàng loạt bằng một ID “unknown customer” nếu chưa có quyết định rõ về mô hình dữ liệu, quyền riêng tư và báo cáo nghiệp vụ.

```sql
SELECT COUNT(*) AS orphan_orders
FROM orders o
WHERE o.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM customer_account c
      WHERE c.id = o.customer_id
  );
```

Các dòng mồ côi cần được xử lý có truy vết: khôi phục bản ghi cha hợp lệ, sửa khóa tham chiếu đúng, tách vào hàng đợi ngoại lệ hoặc xử lý theo chính sách nghiệp vụ.

## 10. Backfill trên bảng lớn: theo lô, kiểm soát ghi đồng thời và khả năng tiếp tục

Một lệnh `UPDATE` toàn bảng có thể tạo transaction dài, ghi nhiều WAL/redo, tăng lock, tải I/O hoặc làm chậm replication. Khi quy mô dữ liệu lớn, thường cần một công việc backfill có checkpoint và quan sát được.

Ví dụ ý tưởng chia lô theo ID trên PostgreSQL:

```sql
UPDATE customer_account
SET status_code =
    CASE
        WHEN status_text IS NULL
          OR btrim(status_text) = '' THEN 'PENDING'
        WHEN lower(btrim(status_text)) IN
             ('active', 'enabled') THEN 'ACTIVE'
        WHEN lower(btrim(status_text)) IN
             ('suspended', 'disabled') THEN 'SUSPENDED'
    END
WHERE id >= :batch_start
  AND id < :batch_end
  AND status_code IS NULL;
```

`:batch_start` và `:batch_end` là tham số minh họa do công việc backfill cung cấp, **không phải một lệnh SQL độc lập chạy ngay**. Mỗi lô cần được kiểm tra dữ liệu chưa ánh xạ, ghi nhận khoảng ID, số hàng cập nhật, thời gian thực thi và kết quả đối soát. Không chỉ dựa vào số hàng UPDATE vì có thể có dòng đã được dual-write trước đó.

Một quy trình backfill có thể:

1. Ghi lại phiên bản schema và quy tắc ánh xạ đang dùng.
2. Chọn một lô có biên ID hoặc mốc thời gian ổn định.
3. Kiểm tra và phân loại những dòng không hợp lệ trong lô.
4. Cập nhật những dòng chưa có dữ liệu đích theo quy tắc đã phê duyệt.
5. Commit lô, lưu checkpoint và số lượng đã xử lý.
6. Tiếp tục đến khi hết dữ liệu, rồi quét bù các dòng mới phát sinh.
7. Chạy đối soát toàn bảng hoặc theo snapshot đáng tin cậy.
8. Chỉ thêm constraint sau khi các writer đã tương thích và không còn dữ liệu sai.

Nếu backfill chạy **ngoài** Liquibase (ví dụ batch job của ứng dụng), cần một bước xác minh trong pipeline trước khi cho phép changeset siết constraint. Không đánh dấu một changeset Liquibase là “đã chạy” khi batch job còn dở. Nếu backfill được chia thành nhiều changeset, phải thiết kế khóa định danh, thứ tự, transaction và khả năng tiếp tục phù hợp; tránh tạo vô số changeset thay cho cơ chế checkpoint chuyên dụng.

### 10.1. Idempotency không tự giải quyết mọi lỗi

`WHERE status_code IS NULL` giúp thao tác backfill thường không ghi đè giá trị đã điền khi chạy lại. Tuy nhiên, nếu một lô dở hoặc ứng dụng ghi `status_code` sai, chạy lại có thể bỏ qua bản ghi sai đó. Do vậy cần **hậu kiểm tính đúng đắn**, không chỉ kiểm tra lệnh có thể chạy lại mà không phát sinh lỗi.

### 10.2. Ngăn race condition ở ranh giới giữa kiểm tra và constraint

Một lần `SELECT COUNT(*) = 0` không ngăn INSERT/UPDATE mới phát sinh NULL ngay sau đó. Ràng buộc DDL cuối cùng vẫn có thể thất bại hoặc chặn ứng dụng cũ. Các biện pháp gồm nâng cấp tất cả writer, dual-write trong cùng transaction, áp dụng constraint trung gian khi DBMS hỗ trợ và dùng lịch bảo trì ở bước cutover. Cần kiểm thử hành vi concurrent writes và loại lock thay vì dựa vào giả định.

## 11. PostgreSQL: thêm ràng buộc và xác thực theo giai đoạn

Với PostgreSQL, một số constraint hỗ trợ `NOT VALID` và `VALIDATE CONSTRAINT`, hữu ích khi muốn **bắt các dòng mới tuân thủ** trong khi xác minh dần dữ liệu cũ. Đây là **phương án thay thế có điều kiện**, không phải hướng dẫn áp dụng nguyên xi cho mọi DBMS hoặc thay đồng thời cho các changeset `addNotNullConstraint`/FK ở phần 8.

### 11.1. CHECK để chuẩn bị NOT NULL

```sql
ALTER TABLE customer_account
ADD CONSTRAINT ck_customer_status_code_present
CHECK (status_code IS NOT NULL) NOT VALID;

ALTER TABLE customer_account
VALIDATE CONSTRAINT ck_customer_status_code_present;

ALTER TABLE customer_account
ALTER COLUMN status_code SET NOT NULL;
```

Trong PostgreSQL, một CHECK `NOT VALID` vẫn được áp dụng cho các dòng mới hoặc dòng được cập nhật sau khi tạo constraint, nhưng chưa quét xác nhận toàn bộ dữ liệu tồn tại tại thời điểm thêm. `VALIDATE CONSTRAINT` xác nhận dữ liệu cũ; nếu phát hiện NULL, bước validate thất bại và phải xử lý dữ liệu trước khi thử lại. Ở những phiên bản PostgreSQL phù hợp, CHECK đã validate có thể giúp thao tác `SET NOT NULL` tránh quét bảng lại, nhưng không được kết luận toàn bộ quá trình không có lock. Từng câu ALTER vẫn có thể cần khóa; kiểm thử trên phiên bản và tải thực tế.

Sau khi áp dụng `NOT NULL`, có thể xem xét loại bỏ CHECK trung gian nếu nó chỉ lặp lại cùng quy tắc và không có phụ thuộc khác. Phải lập kế hoạch thay đổi này thành changeset rõ ràng nếu thực thi qua Liquibase.

### 11.2. Khóa ngoại theo giai đoạn

```sql
ALTER TABLE customer_account
ADD CONSTRAINT fk_customer_account_status
FOREIGN KEY (status_code)
REFERENCES account_status_catalog(code)
NOT VALID;

ALTER TABLE customer_account
VALIDATE CONSTRAINT fk_customer_account_status;
```

Cơ chế `NOT VALID` của PostgreSQL giúp tránh quét toàn bộ dữ liệu cũ ngay khi thêm FK; nó vẫn kiểm soát những thao tác mới trong phạm vi được DBMS áp dụng. Sau khi backfill đạt yêu cầu, `VALIDATE CONSTRAINT` xác nhận dữ liệu hiện hữu. Các lệnh cần được tách, thử và giám sát theo khả năng lock trên database thật.

Nếu dùng SQL riêng này trong Liquibase, hãy đặt trong changeset có `dbms: postgresql`, chỉ định SQL rõ ràng, không kết hợp với changeset FK thông thường để vô tình tạo cùng constraint hai lần. Với Oracle, SQL Server, MySQL hoặc DBMS khác, phải nghiên cứu cơ chế tương đương thay vì sao chép `NOT VALID`.

## 12. Rollback và phục hồi: dữ liệu có thể không đảo ngược

Rollback một data migration khác rollback một thay đổi cấu trúc đơn giản. Trong ví dụ, ánh xạ `enabled → ACTIVE` và `active → ACTIVE` là nhiều-một. Nếu xóa `status_text`, không thể tự suy ngược giá trị gốc chỉ từ `status_code`.

### 12.1. Phân tích rollback theo từng giai đoạn

| Giai đoạn | Rollback có thể làm gì? | Nguy cơ |
|---|---|---|
| Tạo bảng danh mục | Drop bảng nếu chưa có phụ thuộc và dữ liệu quan trọng | FK hoặc ứng dụng có thể đã dùng dữ liệu |
| Thêm cột nullable | Drop cột khi chưa là nguồn dữ liệu chính | Mất ghi mới nếu ứng dụng đã sử dụng |
| Backfill | Khôi phục từ nguồn cũ hoặc snapshot, migration bù có kiểm chứng | Mất phân biệt legacy, ghi đồng thời và biến đổi không đảo ngược |
| Thêm NOT NULL/FK | Bỏ constraint nếu có kế hoạch vận hành phù hợp | Ứng dụng cũ có thể bắt đầu ghi dữ liệu sai trở lại |
| Xóa cột cũ | Chỉ khôi phục giá trị từ backup/snapshot hoặc nguồn lưu giữ thích hợp | Không thể chỉ ADD COLUMN để khôi phục dữ liệu cũ |

Nếu trong một changeset chứa SQL không có rollback an toàn, không nên bịa câu `UPDATE ... SET status_code = NULL` để lật lại toàn bộ backfill: nó có thể xóa những giá trị hợp lệ mới được ứng dụng tạo. Thay vào đó, cần chốt phạm vi dữ liệu, snapshot, phương án phục hồi hoặc một changeset bù với điều kiện cụ thể.

### 12.2. Forward fix đôi khi an toàn hơn rollback dữ liệu

Sau khi ứng dụng mới đã ghi dữ liệu và các hệ thống khác tiêu thụ mã mới, rollback toàn bộ về dữ liệu cũ có thể không còn khả thi. Khi đó có thể cần **forward fix**: thêm changeset mới để sửa bản ghi sai, bổ sung mapping hoặc điều chỉnh constraint theo thay đổi nghiệp vụ. Quyết định này cần dựa trên tác động dữ liệu, trạng thái ứng dụng và phương án phục hồi đã được phê duyệt.

Không tự xóa dòng `DATABASECHANGELOG`, chạy `clearCheckSums` hay đánh dấu `MARK_RAN` để né lỗi chuyển dữ liệu. `DATABASECHANGELOG` ghi nhận lịch sử thực thi; sửa metadata không đảo ngược SQL đã áp dụng và có thể khiến dữ liệu, schema và lịch sử không đồng nhất.

## 13. Thiết kế precondition có kiểm chứng thay vì che giấu lỗi

Precondition ở cấp changeset là công cụ mạnh nhưng cần chọn đúng điều kiện:

| Điều kiện | Ví dụ mục tiêu | Hành vi đề xuất khi sai |
|---|---|---|
| `tableExists` | Bảng nguồn hoặc danh mục đã tồn tại | `HALT` để tìm nguyên nhân |
| `columnExists` | Cột legacy và cột mới có mặt đúng giai đoạn | `HALT` nếu migration tiền đề thiếu |
| `sqlCheck` đếm dữ liệu chưa ánh xạ | Số dòng invalid bằng 0 | `HALT` và lập danh sách xử lý |
| `sqlCheck` đếm NULL | Không còn dòng chưa backfill | `HALT` trước `NOT NULL` |
| `sqlCheck` đếm orphan | Mọi FK tìm thấy bản ghi tham chiếu | `HALT` trước FK |
| `sqlCheck` tìm duplicate | Không còn khóa trùng theo quy tắc duy nhất | `HALT` trước UNIQUE |

`onFail` diễn tả khi điều kiện trả về không đạt; `onError` xử lý lỗi trong lúc đánh giá điều kiện. `WARN` chỉ cảnh báo, `CONTINUE` bỏ qua changeset lần này, và `MARK_RAN` đánh dấu đã chạy mà không thực thi nội dung theo cơ chế Liquibase. Với điều kiện dữ liệu ảnh hưởng trực tiếp tới tính đúng của constraint, `HALT` thường an toàn hơn vì buộc sửa nguyên nhân.

Precondition không thay thế kiểm tra data quality liên tục. Nếu tập dữ liệu quá lớn, việc `COUNT(*)` nhiều lần cũng tốn thời gian; cần chọn index, phương pháp thống kê, checkpoint và cổng vận hành phù hợp, nhưng vẫn phải có kiểm chứng cuối cùng trước khi bật ràng buộc.

## 14. Cấu trúc changelog và phối hợp môi trường

Một cấu trúc migration dễ kiểm soát:

```text
db/changelog/
├── db.changelog-master.yaml
├── changes/
│   ├── 001-create-status-catalog.yaml
│   ├── 002-seed-reference-status.yaml
│   ├── 003-add-status-code.yaml
│   ├── 004-backfill-status-code.yaml
│   ├── 005-require-status-code.yaml
│   └── 006-add-status-fk.yaml
└── sql/
    └── status-backfill-postgresql.sql
```

Root changelog có thể include các bước theo thứ tự phụ thuộc:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-status-catalog.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-seed-reference-status.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-status-code.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-backfill-status-code.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/005-require-status-code.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/006-add-status-fk.yaml
      relativeToChangelogFile: true
```

Cây trên minh họa **thứ tự logic**, không có nghĩa bắt buộc chạy sáu bước trong cùng một deployment. Khi application cần phiên bản chuyển tiếp, có thể chia thành nhiều release và kiểm soát lúc mở khóa bước tiếp theo. Chỉ thêm constraint khi đã có bằng chứng dữ liệu và writer đáp ứng.

**Lưu ý đường dẫn:** changeset được Liquibase nhận diện bằng `id`, `author` và đường dẫn logic changelog. Nếu di chuyển file đã chạy, lịch sử `DATABASECHANGELOG.FILENAME` có thể khác và Liquibase có nguy cơ coi nó như changeset mới. Phải giữ ổn định danh tính, dùng `logicalFilePath` phù hợp nếu cần và kiểm chứng mọi môi trường trước khi thay đổi cấu trúc file.

### 14.1. Môi trường có lịch sử khác nhau

Development thường có dữ liệu sạch hoặc ít; production có dữ liệu thật nhiều năm. Precondition có thể đạt ở staging nhưng thất bại ở production. Không suy ra “chạy được trên test” nghĩa là mọi legacy value đều đã được xử lý.

Context/label giúp chọn changeset theo môi trường hoặc đợt phát hành, nhưng không nên dùng để **bỏ qua** backfill bắt buộc ở production. Nếu cùng schema mục tiêu áp dụng cho nhiều môi trường, thay đổi tham chiếu và dữ liệu bắt buộc nên được đưa vào lịch triển khai nhất quán; dữ liệu thử nghiệm cần tách riêng.

## 15. Spring Boot và CI/CD: triển khai thay đổi dữ liệu theo nhiều phiên bản

Spring Boot thường cấu hình Liquibase bằng:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Khi thực hiện expand–migrate–contract, cần phối hợp changelog với code:

1. **Release A:** thêm `status_code` nullable và bảng danh mục, không phá vỡ mapping `status_text`.
2. **Release B:** triển khai ứng dụng chuyển tiếp. Khi tạo/cập nhật tài khoản, ghi `status_code` đúng theo quy tắc đã phê duyệt; trong thời gian còn consumer cũ, duy trì dữ liệu legacy cần thiết.
3. **Backfill:** cập nhật dữ liệu cũ theo lô hoặc changeset phù hợp, đối soát và giám sát.
4. **Release C:** ứng dụng chỉ còn phụ thuộc dữ liệu chuẩn, nhưng vẫn chịu được trạng thái chuyển tiếp nếu chưa siết constraint.
5. **Migration ràng buộc:** thêm `NOT NULL`, FK và các constraint khác sau khi đã xác minh.
6. **Release D:** bỏ cột cũ ở thời điểm không còn consumer và đã sẵn sàng phương án phục hồi.

Khi nhiều instance chạy song song, Liquibase có `DATABASECHANGELOGLOCK` để điều phối migration, nhưng lock này **không** đồng bộ logic dual-write của tất cả instance ứng dụng. Một job migration riêng trong CI/CD thường giúp kiểm soát thời điểm chạy DDL/DML rõ ràng hơn; nếu ứng dụng cũng tự chạy Liquibase khi khởi động, phải có một chiến lược sở hữu migration thống nhất.

### 15.1. Cổng kiểm chứng trong pipeline

Pipeline nên theo thứ tự:

1. Review thay đổi changelog, mapping dữ liệu và tác động tới schema/consumer.
2. Kiểm tra root changelog, phiên bản Liquibase, DBMS, credentials và context/label.
3. Chạy `liquibase validate` để kiểm tra cấu trúc changelog.
4. Chạy `liquibase status --verbose` để xem những changeset pending.
5. Chạy `liquibase update-sql` để review SQL sẽ được sinh.
6. Chạy migration trên database thử nghiệm có dữ liệu đại diện, đo lock/thời gian và đối soát.
7. Kiểm tra các bất biến bằng SQL, ghi số lượng invalid/NULL/orphan/duplicate.
8. Chỉ chạy `liquibase update` ở môi trường đích với cấu hình đã kiểm tra và kế hoạch rollback/phục hồi phù hợp.
9. Hậu kiểm `DATABASECHANGELOG`, số dòng, kết quả nghiệp vụ và tình trạng lỗi ứng dụng.
10. Không triển khai bước contract nếu còn instance, job hoặc API phụ thuộc biểu diễn cũ.

Các lệnh dưới đây là minh họa; trước khi thực thi phải cung cấp URL, username, secret và changelog phù hợp:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
```

`validate` không kiểm tra được mọi giá trị runtime; `update-sql` chỉ sinh SQL dự kiến chứ không chạy trên toàn bộ dữ liệu cũ. Do đó, cần kết hợp các bước này với kiểm thử dữ liệu thực tế và quan sát migration ở staging.

## 16. Những lỗi và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Xử lý ưu tiên |
|---|---|---|
| `addNotNullConstraint` thất bại | Còn dữ liệu legacy NULL hoặc writer cũ tiếp tục tạo NULL | Đếm NULL, backfill lại và kiểm soát writer trước khi siết |
| `addForeignKeyConstraint` thất bại | Có mã không nằm trong danh mục hoặc kiểu tham chiếu không tương thích | Truy vấn orphan, sửa mapping/lookup, kiểm tra kiểu và constraint |
| `addUniqueConstraint` thất bại | Dữ liệu trùng sau trim/lowercase hoặc collation khác kỳ vọng | Xác minh quy tắc unique và xử lý duplicate có truy vết |
| Backfill xong nhưng bản ghi mới lại thiếu mã | App chưa dual-write hoặc job đồng bộ thất bại | Sửa đường ghi, thêm theo dõi và quét bù |
| Precondition HALT dù migration trước đã chạy | Dữ liệu vẫn còn ngoài mapping hoặc môi trường có lịch sử khác | Xem số lượng, ID lỗi và thay đổi phát sinh sau lần kiểm tra |
| Dữ liệu bị đổi sang trạng thái sai | Quy tắc `ELSE` mặc định hoặc mapping chưa được duyệt | Dừng triển khai; đối soát với nguồn/snapshot, lập migration bù |
| Rollback không khôi phục dữ liệu ban đầu | Ánh xạ nhiều-một hoặc đã xóa cột cũ | Dùng backup, snapshot hoặc quy trình phục hồi, không CAST ngược tùy tiện |
| Migration trên bảng lớn chạy rất lâu | UPDATE toàn bảng, transaction dài, lock hoặc ghi đồng thời | Chia lô, checkpoint, đo tải và điều phối thời điểm |
| Staging đạt nhưng production không đạt | Data drift, ghi đồng thời, DBMS/phiên bản hoặc config khác | So sánh các bất biến trên đúng database đích |
| Changeset cũ được nhận diện như mới | Đổi `id`, `author` hoặc đường dẫn changelog | Đối chiếu `DATABASECHANGELOG`; khôi phục danh tính logic phù hợp |

Một cách chẩn đoán hiệu quả là luôn hỏi: **Dữ liệu legacy nào chưa xử lý? Quy tắc nào chưa thỏa? Writer nào đang ghi sai? Constraint nào đang được áp dụng? Lịch sử Liquibase đã ghi nhận bước nào?** Không sửa lịch sử cho đẹp hoặc hạ điều kiện an toàn để vượt qua lỗi.

## 17. Bài thực hành end-to-end

**Đề bài:** một database PostgreSQL thử nghiệm có bảng `customer_account(id, status_text)`. Dữ liệu gồm `active`, `enabled`, `disabled`, `suspended`, `NULL`, chuỗi rỗng và một giá trị lạ `closed`. Nghiệp vụ muốn dùng `status_code` với `ACTIVE`, `SUSPENDED`, `PENDING` và buộc giá trị phải có trong bảng danh mục.

Hãy thực hiện theo trình tự:

1. Viết truy vấn phân bố giá trị `status_text` và phát hiện `closed` là dữ liệu chưa có mapping.
2. Không chuyển `closed` thành `PENDING`; xác định quy tắc với người phụ trách nghiệp vụ hoặc xử lý nó như ngoại lệ.
3. Tạo bảng `account_status_catalog` và dữ liệu tham chiếu.
4. Thêm `status_code` nullable, chưa áp dụng `NOT NULL`/FK.
5. Viết changeset backfill có `sqlCheck expectedResult: "0"` cho số bản ghi chưa ánh xạ, `onFail: HALT` và giới hạn `dbms: postgresql`.
6. Chạy trên bản sao database bằng `validate`, `status --verbose` và `update-sql` để kiểm tra tác động.
7. Thực hiện migration ở môi trường thử nghiệm, đối chiếu số NULL, mã mồ côi, mapping và tổng số dòng.
8. Giả lập một writer cũ chèn dòng mới thiếu `status_code`; giải thích vì sao cần phiên bản ứng dụng chuyển tiếp hoặc bước kiểm soát ghi.
9. Khi dữ liệu và writer đáp ứng, thêm `NOT NULL` và FK bằng changeset riêng, kiểm chứng trên PostgreSQL.
10. Lập kế hoạch rollback cho giai đoạn trước và sau khi xóa cột legacy; chỉ ra thông tin nào không thể khôi phục nếu không có snapshot.
11. So sánh phương án ALTER trực tiếp với phương án PostgreSQL `NOT VALID`/`VALIDATE CONSTRAINT` trong điều kiện bảng lớn.

**Tiêu chí hoàn thành:** không còn dữ liệu chưa ánh xạ, không tự chọn mặc định gây mất nghĩa; constraint mới phản ánh đúng bất biến, ứng dụng tiếp tục ghi dữ liệu hợp lệ, và có bằng chứng kiểm tra trước/sau cùng phương án phục hồi thực tế.

## 18. Checklist trước khi siết ràng buộc

- [ ] Đã định nghĩa chính xác invariant và ý nghĩa nghiệp vụ của mọi giá trị mặc định.
- [ ] Đã kiểm kê giá trị cũ, NULL, chuỗi rỗng, mã không hợp lệ, duplicate và orphan.
- [ ] Bảng ánh xạ được phê duyệt; dữ liệu chưa rõ không bị gán đại vào một mã.
- [ ] Cấu trúc mới được thêm theo hướng tương thích với ứng dụng cũ.
- [ ] Dữ liệu tham chiếu bắt buộc đã được nạp và kiểm chứng.
- [ ] Backfill có precondition, phạm vi UPDATE rõ ràng, chiến lược retry/checkpoint phù hợp.
- [ ] Đã đối soát số dòng, mã trạng thái, NULL và khóa tham chiếu sau backfill.
- [ ] Writer của ứng dụng đã tương thích; không còn đường ghi tạo dữ liệu sai.
- [ ] Constraint mới được áp dụng theo thứ tự hợp lý: dữ liệu sạch trước, ràng buộc sau.
- [ ] Đã xem xét UNIQUE/CHECK/FK/NOT NULL theo ngữ nghĩa thực tế và DBMS.
- [ ] Có kế hoạch lock, thời gian chạy và thay đổi theo lô cho bảng lớn.
- [ ] Changeset có định danh ổn định và không sửa nội dung lịch sử đã deploy.
- [ ] `validate`, `status` và `update-sql` dùng cùng cấu hình với lần `update`.
- [ ] Có phương án rollback/forward fix/backup, nhận diện rõ chuyển đổi không đảo ngược.
- [ ] Đã hậu kiểm `DATABASECHANGELOG`, ràng buộc và kết quả nghiệp vụ ở database đích.
- [ ] Chỉ xóa cấu trúc cũ khi không còn consumer phụ thuộc và đã đủ điều kiện khôi phục.

**Kết luận:** để siết ràng buộc an toàn, trước hết cần **biến dữ liệu cũ thành dữ liệu đúng theo quy tắc nghiệp vụ, bổ sung mọi giá trị thiếu và ngăn dữ liệu sai mới phát sinh**. Liquibase cung cấp changeset, precondition, thứ tự thực thi, lịch sử và công cụ kiểm chứng; trách nhiệm xác định mapping đúng, đối soát, kiểm soát ghi đồng thời và chuẩn bị phục hồi vẫn thuộc quy trình kỹ thuật của dự án. Tách expand, backfill, verify, constrain và contract thành những giai đoạn rõ ràng giúp triển khai dễ kiểm soát hơn, đặc biệt khi schema đang phục vụ ứng dụng liên tục.

