# Cập nhật theo số lượng changeset bằng update-count

## 1. Khi nào cần cập nhật một phần changelog?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Người học cần thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Thông thường, lệnh `update` đưa database qua **toàn bộ các changeset đang đủ điều kiện chờ chạy** trong changelog. Nhưng có những lần phát hành cần dừng có chủ đích sau một số changeset để kiểm tra dữ liệu, nâng cấp ứng dụng hoặc chờ phê duyệt bước tiếp theo.

Liquibase cung cấp lệnh **`update-count`** để áp dụng một **số lượng changeset giới hạn** thay vì tiếp tục đến hết tập changeset có thể áp dụng. Đây là công cụ triển khai theo từng bước có kiểm soát, không phải công cụ tự động nhận biết mốc nghiệp vụ.

Ví dụ, một migration dữ liệu gồm sáu changeset theo thứ tự:

```text
001  Tạo bảng danh mục trạng thái
002  Nạp ba mã trạng thái chuẩn
003  Bổ sung cột status_code cho bảng khách hàng
004  Backfill dữ liệu trạng thái cũ
005  Siết NOT NULL cho status_code
006  Tạo khóa ngoại status_code -> bảng danh mục
```

Nhóm có thể dùng `update-count` để áp dụng 001–002, dừng kiểm tra; tiếp theo áp dụng 003–004, triển khai ứng dụng và kiểm tra backfill; sau cùng áp dụng 005–006. Tuy nhiên, điều này **chỉ an toàn khi** thứ tự changeset và mốc dừng đã được thiết kế, bộ lọc ở từng lần chạy không thay đổi ngoài dự kiến, và lịch sử database được đối chiếu trước khi chạy tiếp.

Sau bài này, bạn sẽ biết cú pháp CLI, cách Liquibase lựa chọn changeset, tương tác với bộ lọc và `DATABASECHANGELOG`, cách kiểm chứng trước/sau, rủi ro khi thất bại giữa chừng và cách rollback hoặc tiếp tục một chuỗi triển khai.

## 2. Phân biệt update, update-count và các lệnh xem trước

| Lệnh | Mục đích chính | Điều quan trọng |
|---|---|---|
| `update` | Áp dụng mọi changeset đang đủ điều kiện chờ chạy | Không tự dừng tại một mốc nghiệp vụ giữa changelog |
| `update-count` | Áp dụng một số lượng changeset giới hạn | Số đếm không đồng nghĩa số file, số SQL statement hay số hàng dữ liệu |
| `update-sql` | Sinh SQL dự kiến cho lệnh update đầy đủ, không áp dụng | Dùng để review tác động nhưng có thể dài hơn đợt triển khai mong muốn |
| `update-count-sql` | Sinh SQL dự kiến cho một lần cập nhật giới hạn theo count, ở phiên bản hỗ trợ | Phải dùng đúng cùng số count, changelog, DBMS và bộ lọc như lần chạy thật |
| `status --verbose` | Kiểm tra những changeset chưa chạy theo cấu hình hiện hành | Giúp xác định candidate, nhưng không thay thế review SQL hoặc kiểm chứng dữ liệu |
| `history` | Xem lịch sử changeset đã áp dụng | Hỗ trợ kiểm tra kết quả của đợt triển khai |
| `rollback-count` | Hoàn tác một số changeset theo cơ chế rollback phù hợp | Không mặc nhiên đảo ngược đúng “batch” trước nếu lịch sử có thêm thay đổi |

Cú pháp tên lệnh và tham số có thể khác giữa các phiên bản Liquibase. Bài dùng tên CLI dạng kebab-case như `update-count` và `update-count-sql`. Nếu dự án dùng phiên bản cũ với tên dạng camelCase như `updateCount`, cần đối chiếu lệnh được phiên bản đó hỗ trợ; không trộn cú pháp của hai đời CLI mà không kiểm chứng.

**Giới hạn cần ghi nhớ:** `update-count` giới hạn **số changeset được Liquibase xử lý để cập nhật**, không có cơ chế tự hiểu rằng “hai changeset đầu tiên tạo đủ schema” hoặc “chờ ứng dụng nâng cấp”. Logic nghiệp vụ và điểm dừng do người vận hành thiết kế.

## 3. Cú pháp cơ bản của update-count

Một lệnh ví dụ với hai changeset:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count --count=2
```

Ý nghĩa các phần:

- `--changelog-file` chỉ root changelog Liquibase sẽ duyệt.
- `update-count` yêu cầu cập nhật một số changeset được giới hạn.
- `--count=2` chỉ định số lượng thay đổi tối đa cho lần gọi theo cơ chế của phiên bản CLI đang dùng.

Cấu hình kết nối tới database (URL, username, password, schema, driver, search path) cần được cung cấp qua cấu hình Liquibase hoặc tham số tương ứng. Ví dụ trên **không chứa credentials thật** và không nên được chạy khi chưa xác nhận database đích.

Xem trước SQL của một lần cập nhật giới hạn bằng lệnh hỗ trợ tương ứng:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count-sql --count=2
```

Lệnh xem trước không áp dụng DDL/DML. Cần review nội dung SQL được sinh ra và so sánh với kỳ vọng trước khi chạy `update-count`. Nếu phiên bản hiện dùng không nhận dạng lệnh `update-count-sql` hoặc cách đặt tùy chọn `--count`, hãy kiểm tra tài liệu/trợ giúp của **chính phiên bản đã khóa trong dự án**, không suy đoán rằng nâng cấp CLI là vô hại.

### 3.1. Count phải là số lượng hợp lệ

Giá trị `count` phải theo quy tắc của CLI (một số nguyên dương cho số changeset muốn áp dụng). Không truyền một biểu thức như `2+3`, tên file, tag hoặc tên changeset vào `--count`. Tránh dựa vào `count=0` hoặc count âm để có hành vi “không làm gì”; nếu chỉ muốn xem trạng thái, dùng các lệnh đọc/preview thay vì cố tạo một lần cập nhật rỗng.

Nếu số lượng changeset đang đủ điều kiện ít hơn count, Liquibase không thể tạo ra changeset mới chỉ để đủ số. Trước khi chạy, cần kiểm tra số lượng và **danh tính** candidate thực tế; đừng diễn giải việc lệnh hoàn tất như bằng chứng rằng đã áp dụng chính xác count changeset.

### 3.2. Vì sao đếm changeset, không đếm SQL statement?

Một changeset có thể chứa nhiều change:

```yaml
databaseChangeLog:
  - changeSet:
      id: 010-create-customer-and-index
      author: schema-team
      changes:
        - createTable:
            tableName: customer_account
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
        - createIndex:
            tableName: customer_account
            indexName: idx_customer_email
            columns:
              - column:
                  name: email
```

Dù Liquibase tạo nhiều câu SQL để thực hiện hai change, **đây vẫn là một changeset** với một bộ định danh. `--count=1` không có nghĩa “chỉ chạy câu SQL đầu tiên”; nó xem changeset là đơn vị cập nhật được ghi lịch sử.

Tương tự, một change `loadData` có thể nạp hàng nghìn dòng CSV, nhưng bản thân nó nằm trong một changeset. Count cũng không phải số hàng insert/update.

## 4. Changeset nào được tính vào đợt cập nhật?

Tập candidate mà Liquibase xử lý phụ thuộc vào nhiều yếu tố. Có thể hình dung:

```text
Root changelog
      |
      v
Thứ tự changeset theo include/includeAll và khai báo
      |
      v
Bộ lọc context, label, DBMS và các điều kiện phù hợp
      |
      v
Đối chiếu với DATABASECHANGELOG
      |
      v
Tập changeset Liquibase cần xử lý tại lần chạy này
      |
      v
update-count giới hạn số lượng được cập nhật
```

Đây là mô hình tư duy, không phải mô tả chính xác thứ tự đánh giá nội bộ của tất cả phiên bản. Điểm mấu chốt là **count áp dụng lên việc xử lý changeset theo điều kiện ở thời điểm thực thi**, chứ không đơn thuần cắt đúng N dòng đầu của file changelog.

### 4.1. Thứ tự và include quan trọng hơn tên id

Liquibase duyệt changelog theo thứ tự các mục được nạp. Nếu root khai báo:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-catalog.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-seed-catalog.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-add-status-column.yaml
      relativeToChangelogFile: true
```

thì thứ tự include xác định trình tự nạp file con. Giá trị `id` như `001`, `002` giúp người đọc theo dõi nhưng không phải bộ máy tự sắp xếp mọi changeset theo số. Nếu dùng `includeAll`, các thay đổi trong thư mục được duyệt theo cơ chế sắp xếp của Liquibase; phải kiểm tra thứ tự file thực tế, tránh dựa vào tên thư mục hoặc giả định chỉ cần đánh số là đủ.

### 4.2. Bộ định danh và lịch sử quyết định thay đổi đã chạy hay chưa

Liquibase nhận diện changeset bằng tổ hợp `id`, `author` và đường dẫn logic của file changelog. Thông tin này xuất hiện trong `DATABASECHANGELOG`, cùng checksum, thời gian và kiểu thực thi.

Giả sử lần trước đã chạy changeset `001` và `002`. Lần kế tiếp gọi `update-count --count=2` với cùng changelog không có nghĩa Liquibase chạy lại 001–002. Nó đối chiếu lịch sử và thường tiếp tục xử lý những changeset chưa được áp dụng, tùy thuộc các thuộc tính đặc biệt như `runAlways` hoặc `runOnChange`.

**Không đổi `id`, `author`, đường dẫn logic hoặc sửa nội dung changeset đã triển khai chỉ để thay đổi kết quả đếm.** Các thay đổi đó có thể khiến Liquibase coi changeset cũ là mới hoặc phát sinh lỗi checksum.

### 4.3. Context, label và DBMS có thể làm thay đổi tập được chọn

Một changeset khai báo:

```yaml
databaseChangeLog:
  - changeSet:
      id: 020-test-seed
      author: migration-team
      contextFilter: "@test"
      labels: test-data
      dbms: postgresql
      changes:
        - insert:
            tableName: audit_marker
            columns:
              - column:
                  name: marker
                  value: fixture
```

sẽ không có cùng điều kiện chọn ở các lần chạy context `test` và `prod`. Nếu đặt `--count=2` nhưng thay đổi `--context-filter` hoặc `--label-filter` giữa những lần chạy, hai changeset được chọn có thể hoàn toàn khác với danh sách dự kiến. Không đưa dữ liệu test vào root production và chỉ dựa vào count như một lớp bảo vệ.

Ngoài ra, việc không truyền bộ lọc context/label không mặc nhiên có nghĩa Liquibase chỉ chạy changeset không có nhãn. Những context thông thường có thể được xét khi không truyền filter, trong khi `@test` yêu cầu context được chỉ định tường minh. Vì vậy phải có chính sách filter rõ ràng ở pipeline.

### 4.4. Precondition, MARK_RAN và các cơ chế chạy lại

Precondition có thể dừng quá trình bằng `HALT`, bỏ qua changeset để thử lại khi `CONTINUE`, hoặc đánh dấu lịch sử bằng `MARK_RAN` tùy nơi khai báo và thuộc tính. Một changeset được ghi `MARK_RAN` có thể xuất hiện trong `DATABASECHANGELOG` dù SQL thay đổi không được thực thi.

Các thuộc tính như `runAlways` và `runOnChange` cũng có thể khiến changeset đã có lịch sử được xử lý lại. Khi dùng `update-count` với các cơ chế này, không nên tự suy luận rằng count luôn tương ứng với N changeset **hoàn toàn mới** và N thay đổi cấu trúc khác nhau. Hãy kiểm tra candidate và SQL dự kiến theo phiên bản Liquibase thực dùng.

## 5. Ví dụ xuyên suốt: sáu changeset và ba đợt cập nhật

Giả định database đã có bảng `customer_account(id, legacy_status)` với dữ liệu lịch sử. Ứng dụng mới muốn dùng cột `status_code` và bảng danh mục `account_status_catalog`. Trước khi siết ràng buộc, cần chuẩn hóa dữ liệu và đảm bảo các writer ứng dụng không tiếp tục tạo NULL hoặc mã ngoài danh mục.

Thiết kế sáu changeset:

| ID | Thay đổi | Tiền đề và rủi ro |
|---|---|---|
| 001 | Tạo bảng `account_status_catalog` | Bảng chưa tồn tại và user deploy có quyền DDL |
| 002 | Nạp các mã `ACTIVE`, `SUSPENDED`, `PENDING` | Có bảng danh mục; không có mã trùng |
| 003 | Thêm cột `status_code` nullable | Bảng `customer_account` đã tồn tại |
| 004 | Backfill từ `legacy_status` | Giá trị cũ ánh xạ được và quy tắc nghiệp vụ đã phê duyệt |
| 005 | Thêm `NOT NULL` cho `status_code` | Không còn NULL, mọi writer tương thích |
| 006 | Thêm FK đến bảng danh mục | Không có mã mồ côi, kiểu cột tương thích |

### 5.1. Ví dụ khai báo cấu trúc và danh mục

Các đoạn YAML dưới đây là **minh họa về nội dung changeset** của một changelog, không phải toàn bộ dự án cần tạo trong bài tập.

```yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-status-catalog
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

  - changeSet:
      id: 002-seed-status-catalog
      author: migration-team
      changes:
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: ACTIVE
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: SUSPENDED
        - insert:
            tableName: account_status_catalog
            columns:
              - column:
                  name: code
                  value: PENDING

  - changeSet:
      id: 003-add-status-code
      author: migration-team
      changes:
        - addColumn:
            tableName: customer_account
            columns:
              - column:
                  name: status_code
                  type: varchar(20)
```

Bước 003 cố ý **chưa thêm `NOT NULL`** để các hàng cũ và ứng dụng cũ vẫn có thể tồn tại trong giai đoạn chuyển tiếp.

### 5.2. Backfill và siết ràng buộc

Ví dụ thêm ba changeset vào phần cuối changelog. SQL backfill dưới đây dành cho PostgreSQL:

```yaml
  - changeSet:
      id: 004-backfill-status-code
      author: migration-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM customer_account
              WHERE legacy_status IS NOT NULL
                AND btrim(legacy_status) <> ''
                AND lower(btrim(legacy_status)) NOT IN
                    ('active', 'enabled',
                     'disabled', 'suspended')
      changes:
        - sql:
            sql: |
              UPDATE customer_account
              SET status_code = CASE
                  WHEN legacy_status IS NULL
                    OR btrim(legacy_status) = ''
                    THEN 'PENDING'
                  WHEN lower(btrim(legacy_status)) IN
                       ('active', 'enabled')
                    THEN 'ACTIVE'
                  WHEN lower(btrim(legacy_status)) IN
                       ('disabled', 'suspended')
                    THEN 'SUSPENDED'
              END
              WHERE status_code IS NULL;

  - changeSet:
      id: 005-require-status-code
      author: migration-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*) FROM customer_account
              WHERE status_code IS NULL
      changes:
        - addNotNullConstraint:
            tableName: customer_account
            columnName: status_code
            columnDataType: varchar(20)

  - changeSet:
      id: 006-reference-status-catalog
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
            constraintName: fk_customer_status_code
            baseTableName: customer_account
            baseColumnNames: status_code
            referencedTableName: account_status_catalog
            referencedColumnNames: code
```

**Giả định nghiệp vụ:** `legacy_status = NULL` hoặc chuỗi rỗng được phép chuyển thành `PENDING`. Nếu quy tắc đó chưa được phê duyệt, không dùng migration này; phải phân loại dữ liệu chưa biết thay vì gán trạng thái mặc định tùy tiện.

**Giới hạn ví dụ:** ba changeset 004–006 được viết nối tiếp phần YAML trước để minh họa một changelog sáu changeset. Nếu triển khai trong nhiều file, cần đặt mỗi đoạn vào cấu trúc `databaseChangeLog` hợp lệ và điều phối include tương ứng. Dùng một SQL riêng PostgreSQL trong 004 có nghĩa các môi trường dùng DBMS khác cần giải pháp backfill tương đương; không được bỏ qua 004 rồi tiếp tục siết constraint như thể dữ liệu đã sẵn sàng.

## 6. Triển khai bằng ba đợt update-count có kiểm chứng

Giả định database chưa chạy bất kỳ changeset nào trong sáu changeset ví dụ, tất cả đều đủ điều kiện theo bộ lọc và không có changeset khác chen vào giữa. Đây là điều kiện cần để những lệnh count minh họa bên dưới tương ứng đúng với các ID dự kiến.

### Đợt A — count=2: tạo và nạp dữ liệu danh mục

Xem trước:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count-sql --count=2
```

Xác nhận SQL chỉ chứa tạo bảng danh mục và nạp ba mã. Sau đó chạy trên database thử nghiệm:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count --count=2
```

Kiểm chứng:

```sql
SELECT code
FROM account_status_catalog
ORDER BY code;
```

Kỳ vọng có đúng `ACTIVE`, `PENDING` và `SUSPENDED`; kiểm tra `DATABASECHANGELOG` cho hai ID 001 và 002. Nếu lệnh đã chạy một phần rồi lỗi, không tự động gọi lại mà không kiểm tra trạng thái.

### Đợt B — count=2: thêm cột và backfill

Trước đợt này, phải đánh giá khả năng ánh xạ dữ liệu cũ. Sau khi xem trước SQL và xác nhận 003–004 là hai changeset pending kế tiếp, chạy:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count --count=2
```

Đợt B tạo `status_code` nullable và điền dữ liệu. Tiếp tục kiểm tra:

```sql
SELECT COUNT(*) AS unresolved_rows
FROM customer_account
WHERE status_code IS NULL;
```

Đồng thời so sánh mã mới với quy tắc ánh xạ legacy và đếm những mã không có trong danh mục. Chỉ khi kết quả đúng, mới chuyển sang triển khai ứng dụng sử dụng cột mới hoặc chuẩn bị siết ràng buộc.

**Mốc dừng có chủ đích:** trước đợt C, toàn bộ code ghi dữ liệu phải tương thích với `status_code`. Nếu ứng dụng cũ vẫn INSERT/UPDATE khiến cột này NULL, backfill đã hoàn tất lúc trước không bảo đảm ràng buộc ở đợt C sẽ thành công.

### Đợt C — count=2: NOT NULL và khóa ngoại

Sau khi ứng dụng và dữ liệu đã đáp ứng điều kiện:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count-sql --count=2

liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count --count=2
```

Kỳ vọng Liquibase xử lý 005–006. Kiểm tra metadata ràng buộc, lịch sử triển khai và thử một giao dịch test phù hợp để xác nhận DBMS ngăn NULL hoặc mã không có trong bảng danh mục.

### 6.1. Vì sao không chạy count=6 ngay từ đầu?

Dù cùng sáu changeset, `count=6` có thể đưa database đi thẳng từ schema cũ đến constraint mới mà **không có khoảng thời gian triển khai ứng dụng chuyển tiếp và đối soát**. Với production có ghi đồng thời, điểm dừng nghiệp vụ quan trọng hơn sự tiện lợi của một lệnh.

### 6.2. Vì sao không mặc định đợt sau vẫn là cùng hai changeset?

Giả sử một worker thêm changeset `002b-fix-status-catalog` vào changelog giữa hai lần deploy. Hoặc pipeline dùng thêm một label, DBMS khác hay một database đã chạy một số bước từ trước. Count=2 ở đợt B có thể chọn 002b–003 thay vì 003–004.

**Do đó, mỗi đợt phải kiểm chứng danh sách ID/AUTHOR/FILENAME pending** trước khi chạy, không chỉ truyền count mà bỏ qua kiểm tra thứ tự thực tế.

## 7. Checklist trước khi ra lệnh: xác minh đúng tập changeset

Một lần chạy `update-count` an toàn nên xác nhận bốn nhóm điều kiện:

1. **Đúng đích:** database URL, username, schema/catalog, DBMS, phiên bản Liquibase.
2. **Đúng nguồn:** root changelog, các file include, đường dẫn logic và commit/artifact.
3. **Đúng bộ lọc:** context, label, cấu hình DBMS và các thay đổi có điều kiện.
4. **Đúng mốc:** ID/author/file của N changeset dự kiến và trạng thái dữ liệu trước khi áp dụng.

Sau khi thiết lập kết nối và bộ lọc, dùng:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  validate

liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  status --verbose
```

`validate` giúp phát hiện các vấn đề cấu trúc/changelog mà Liquibase có khả năng kiểm tra, nhưng không chứng minh DDL sẽ chạy nhanh hoặc dữ liệu đạt điều kiện nghiệp vụ. `status --verbose` giúp xem candidate, song phải đối chiếu thêm lịch sử và tác động SQL nếu hệ thống dùng `runAlways`, `runOnChange`, hoặc precondition có thể thay đổi việc thực thi thực tế.

Trước khi cập nhật, tạo bản preview tương ứng chính xác với count và cấu hình định dùng:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  update-count-sql --count=2
```

Không xem `update-sql` (không count) là preview chính xác của `update-count --count=2`, vì tập thay đổi hiển thị có thể dài hơn.

## 8. Bộ lọc context và label trong đợt giới hạn

Ví dụ deployment test chỉ chọn các changeset phù hợp với context và label cụ thể:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --context-filter=test \
  --label-filter=integration \
  update-count-sql --count=2
```

Sau review, lệnh thực thi phải giữ nguyên hai filter:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  --context-filter=test \
  --label-filter=integration \
  update-count --count=2
```

Nếu lần preview chọn `test` nhưng lần update chọn `prod`, count=2 có thể áp dụng vào hai candidate khác nhau. Cần kiểm soát điều này bằng tham số pipeline được version-control, tránh nhập tay không nhất quán.

### 8.1. Đợt deploy không phải là một context

Một nhãn như `release-2026-11` có thể giúp phân nhóm changeset, nhưng **label không thay cho count** và count không thay cho label. Nếu doanh nghiệp thực sự cần một mốc nghiệp vụ cố định, nên kết hợp cách tổ chức changelog/label rõ ràng với bước kiểm duyệt ID cụ thể, thay vì tin rằng “hai changeset tiếp theo” luôn đúng.

### 8.2. Filter có thể khiến changeset phụ thuộc không được chọn

Nếu 004 backfill thuộc context `data-fix` nhưng 005 NOT NULL không có context, một lần chạy chọn `prod` có thể bỏ qua 004 và vẫn xem xét 005. Kết quả là precondition của 005 dừng, hoặc nếu thiết kế thiếu guard thì DDL có thể thất bại.

Bộ lọc phải được review theo **chuỗi phụ thuộc**, không chỉ từng changeset riêng lẻ. Các changeset tạo schema nền và backfill bắt buộc thường không nên bị loại ngẫu nhiên bởi filter không phù hợp.

## 9. Lịch sử DATABASECHANGELOG giúp xác nhận những gì đã thực thi

Liquibase lưu lịch sử trong bảng `DATABASECHANGELOG` của database đích. Các trường quan trọng thường gồm `ID`, `AUTHOR`, `FILENAME`, `DATEEXECUTED`, `ORDEREXECUTED`, `EXECTYPE` và `MD5SUM`.

Truy vấn chỉ đọc, với tên bảng mặc định:

```sql
SELECT ID,
       AUTHOR,
       FILENAME,
       DATEEXECUTED,
       ORDEREXECUTED,
       EXECTYPE,
       MD5SUM
FROM DATABASECHANGELOG
ORDER BY ORDEREXECUTED, DATEEXECUTED;
```

Không mặc định tất cả dự án dùng chung schema cho `DATABASECHANGELOG`; cấu hình Liquibase có thể chỉ định schema và tên bảng metadata khác nhau. Kiểm tra đúng bảng lịch sử của database mà lệnh vừa tác động.

### 9.1. Phân biệt số changeset trong changelog và số bản ghi lịch sử

- Changelog chứa toàn bộ các changeset đã thiết kế, gồm thay đổi cũ và mới.
- Lịch sử cho biết changeset nào đã được thực thi hoặc đánh dấu theo cơ chế Liquibase.
- Một changeset có `runOnChange` hoặc `runAlways` có hành vi chạy lại đặc biệt; không nên suy số lần thực thi chỉ từ việc đếm ID duy nhất.
- `EXECTYPE` có thể phản ánh `EXECUTED`, `MARK_RAN` hoặc `RERAN` tùy thao tác và phiên bản.

Đừng chỉ đếm hàng `DATABASECHANGELOG` tăng thêm đúng count. Một changeset được xử lý theo precondition hoặc cơ chế chạy lại có thể khiến số bản ghi mới không khớp với số SQL thay đổi đã thực thi. Hãy **đối chiếu danh tính changeset và hiệu ứng schema/dữ liệu**.

### 9.2. Khi lịch sử khác giữa các môi trường

Staging có thể đã chạy 001–004 trong khi production mới chạy 001–002. Dù dùng cùng root changelog và count=2, hai môi trường sẽ xử lý những candidate khác nhau. Phải coi danh sách pending của từng database là nguồn kiểm chứng riêng, không sao chép giả định của staging sang production.

## 10. Phản ứng đúng khi một đợt update-count thất bại

`update-count` không tự biến nhiều changeset thành một transaction toàn cục bảo đảm “cả đợt cùng thành công hoặc cùng rollback”. Liquibase thường quản lý transaction theo changeset khi DBMS hỗ trợ, nhưng DDL ở một số hệ quản trị có thể commit ngầm hoặc không rollback được như mong đợi. Vì vậy, một lần cập nhật count=3 có thể đã áp dụng thành công một phần trước khi gặp lỗi.

Giả sử đợt B dự kiến 003–004 nhưng 004 backfill gặp dữ liệu legacy không thể ánh xạ:

1. **Dừng pipeline.** Không tiếp tục ngay sang 005–006.
2. **Xem log** để xác định changeset lỗi, câu SQL hoặc precondition liên quan.
3. **Đọc `DATABASECHANGELOG`** xem 003 đã được ghi nhận chưa; không suy từ dòng cuối log.
4. **Kiểm tra schema và dữ liệu thực** xem 003 đã thêm cột, 004 có cập nhật một phần hay không.
5. **Phân loại lỗi**: dữ liệu chưa sạch, thiếu quyền, SQL không hợp lệ, lock, timeout, cấu hình sai DBMS hoặc thay đổi đồng thời.
6. **Chọn hướng tiếp tục hoặc phục hồi** theo khả năng transaction và ảnh hưởng dữ liệu, có phê duyệt cần thiết.
7. **Xem lại tập pending và preview** trước khi chạy tiếp; số count sau sự cố có thể không còn tương ứng với các ID ban đầu.

Nếu transaction của 004 được rollback hoàn toàn, có thể sửa dữ liệu nguồn bằng thay đổi được kiểm soát và chạy lại changeset chưa thành công. Nếu DBMS đã commit một phần, cần đối soát và thiết kế quy trình tiếp tục an toàn. Không xóa bừa bản ghi `DATABASECHANGELOG` hoặc dùng `clearCheckSums` để làm đẹp trạng thái.

### 10.1. Đừng mặc định chạy lại cùng count là idempotent

Một lần chạy lại `update-count --count=2` sau đợt A thành công **không lặp lại chính đợt A** trong điều kiện thông thường; nó có thể tiếp tục sang đợt B. Đây là điểm đặc biệt nguy hiểm khi job CI/CD bị retry tự động mà không kiểm tra trạng thái.

Vì vậy, job phải kiểm tra **ID dự kiến và trạng thái hiện có** trước khi chạy; khi nhận được retry, kiểm tra liệu mục tiêu của đợt đã đạt hay chưa rồi mới quyết định không làm gì, chạy bù, hoặc dừng để điều tra.

## 11. Rollback-count không phải nút Undo mặc định

Liquibase có lệnh `rollback-count` để hoàn tác một số changeset theo cơ chế rollback và lịch sử. Ví dụ ý tưởng:

```bash
liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-count-sql --count=2

liquibase \
  --changelog-file=db/changelog/db.changelog-master.yaml \
  rollback-count --count=2
```

Tên lệnh SQL preview và các tùy chọn có thể khác theo phiên bản. Trước khi chạy rollback, cần đối chiếu khả năng hỗ trợ và định nghĩa rollback của từng changeset.

**Điều tuyệt đối không được suy diễn:** nếu lần gần nhất dùng `update-count --count=2` thì có thể an toàn chạy `rollback-count --count=2` ở bất cứ thời điểm nào để quay về trạng thái trước đó. Sau đợt update có thể đã có changeset khác chạy, kể cả từ pipeline khác. Rollback-count hoạt động trên lịch sử và cấu hình hiện hành; tập bị hoàn tác có thể không còn là chính hai thay đổi vừa triển khai.

Với backfill dữ liệu, rollback còn có nguy cơ mất thông tin hoặc không đảo ngược. Ví dụ ánh xạ `enabled` và `active` thành `ACTIVE` là nhiều-một; nếu dữ liệu cũ đã bị xóa, việc chạy lệnh UPDATE ngược không thể suy ra giá trị gốc.

### 11.1. Kiểm tra rollback theo ba tầng

1. **Đúng changeset cần đảo:** xác định ID/author/file và thứ tự lịch sử, không dựa đơn thuần vào count.
2. **Rollback SQL đúng:** kiểm tra preview, constraints, bảng phụ thuộc, phép chuyển dữ liệu.
3. **Ứng dụng còn tương thích:** rollback database có thể làm phiên bản ứng dụng mới lỗi; có khi cần rollback ứng dụng trước hoặc tiến hành forward fix.

Khi rollback không an toàn, có thể chọn migration bù mới được review, backup hoặc phương án phục hồi dữ liệu đã chuẩn bị. Trong CI/CD, việc đặt tag ở các mốc triển khai có thể hỗ trợ xác định trạng thái cần quay về, nhưng tag cũng phải được quản lý nhất quán trên từng database.

## 12. runOnChange, runAlways và precondition ảnh hưởng cách hiểu count

Một changeset tạo view có thể khai báo:

```yaml
databaseChangeLog:
  - changeSet:
      id: 030-customer-summary-view
      author: db-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_summary
            replaceIfExists: true
            selectQuery: |
              SELECT id, email
              FROM customer_account
```

Khi định nghĩa view thay đổi có ảnh hưởng đến checksum, Liquibase có thể xử lý lại changeset đã tồn tại trong lịch sử. Nếu changelog có changeset dạng này, công thức “count=2 nghĩa là chạy hai ID chưa từng thấy” không còn là giả định đáng tin cậy. Tương tự, `runAlways` và `MARK_RAN` thay đổi quan hệ giữa hành vi xử lý với số SQL thực tế.

Các khuyến nghị:

- Không lạm dụng `runAlways` cho DDL/DML không an toàn khi chạy lại.
- Không dùng `MARK_RAN` để né precondition kiểm chứng dữ liệu quan trọng.
- Với `runOnChange`, kiểm tra SQL và tác động của lần chạy lại trước khi đưa vào một batch đếm.
- Khi cần một batch có tập changeset cố định, hãy xem xét tách release rõ ràng hoặc dùng lựa chọn theo tag/label và quy trình kiểm chứng thay vì chỉ dựa vào count.

## 13. update-count và các bước triển khai ứng dụng Spring Boot

Spring Boot thường có tích hợp Liquibase, ví dụ:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Cấu hình này thường khiến Liquibase chạy quá trình **update** tự động khi ứng dụng khởi động, không mặc nhiên có giới hạn count theo cách CLI `update-count`. Nếu pipeline vừa chạy `update-count --count=2` xong rồi ứng dụng Spring Boot với Liquibase tự động được khởi động, quá trình startup có thể tiếp tục áp dụng **những changeset còn pending** — phá vỡ mốc dừng dự định.

Với chiến lược triển khai theo count, cần quyết định rõ ai sở hữu migration:

- **Pipeline sở hữu migration:** chạy các lệnh CLI có count và kiểm chứng ở từng mốc; cân nhắc tắt Liquibase tự động trong instance ứng dụng bằng `spring.liquibase.enabled: false` nếu phù hợp kiến trúc.
- **Ứng dụng sở hữu migration:** dùng chính sách startup nhất quán, thường áp dụng toàn bộ changeset phù hợp; muốn dừng theo count cần một cơ chế điều phối bên ngoài được thiết kế rõ ràng, không tự giả định Spring Boot có property count tương ứng.

Liquibase dùng `DATABASECHANGELOGLOCK` để điều phối nhiều tiến trình, nhưng lock **không bảo đảm** rằng một instance khởi động sau đó sẽ tôn trọng mốc count của pipeline. Lock chỉ giải quyết tranh chấp thao tác migration đồng thời, không phải logic phát hành.

## 14. CI/CD: đóng gói điểm dừng thành một release gate

Một pipeline dùng `update-count` nên có cơ chế xác minh **danh tính và thứ tự** thay vì chỉ số đếm.

```text
Build và kiểm tra changelog
             |
             v
Xác nhận DB đích / artifact / filter / DBMS
             |
             v
validate + status --verbose
             |
             v
So sánh ID pending với manifest/mốc đã duyệt
             |
             v
update-count-sql --count=N
             |
             v
Review SQL / dữ liệu / lock / kế hoạch rollback
             |
             v
update-count --count=N
             |
             v
Đối chiếu DATABASECHANGELOG + schema/dữ liệu
             |
             v
Phê duyệt mở gate tiếp theo
```

Trong pipeline thực tế:

1. **Cố định artifact và phiên bản:** dùng cùng changelog và Liquibase version từ preview đến update. Không sửa file đã triển khai giữa hai đợt mà không review.
2. **Cố định DB đích:** URL, schema và credentials phải được xác nhận từ secret/config quản lý; dùng quyền tối thiểu.
3. **Cố định filter:** context, label, DBMS và include phải thống nhất; không chạy preview ở test rồi áp dụng lên prod mà bỏ qua đối chiếu lịch sử.
4. **Kiểm tra candidate:** lưu danh sách ID/AUTHOR/FILENAME, không chỉ “có hai changeset”.
5. **Kiểm tra SQL:** xem DDL, thay đổi dữ liệu, precondition, thao tác có lock và khả năng rollback.
6. **Chạy cập nhật:** chỉ khi candidate và dữ liệu tiền đề đã đạt điều kiện.
7. **Hậu kiểm:** xác nhận schema, dữ liệu, danh tính changeset và log ứng dụng; ghi lại commit/artifact, count, filter và kết quả.
8. **Chống retry vô thức:** nếu job bị chạy lại, phải xác minh mốc đã đạt để không tự động thực thi batch kế tiếp.

Một release gate có thể dựa vào phê duyệt thủ công hoặc điều kiện đo đạc, nhưng `update-count` tự thân không đặt lịch, chờ người dùng hoặc giám sát sức khỏe ứng dụng. Những cơ chế đó phải được pipeline hoặc quy trình triển khai cung cấp.

## 15. Những tình huống dễ hiểu sai

| Triệu chứng | Nguyên nhân cần xem xét | Hành động |
|---|---|---|
| `--count=2` chạy không đúng hai ID dự tính | Tập pending khác vì filter, lịch sử, include hoặc changeset mới chen vào | Đọc `status` và danh tính changeset, so sánh với mốc đã duyệt |
| Chạy lại cùng count áp dụng những thay đổi kế tiếp | Đợt đầu đã được ghi nhận, Liquibase chuyển sang candidate mới | Chặn retry không idempotent bằng kiểm tra mốc |
| Đợt A thành công nhưng đợt B fail | Precondition, dữ liệu legacy, DBMS, lock hoặc SQL backfill lỗi | Đọc log, lịch sử và trạng thái dữ liệu; sửa nguyên nhân có kiểm chứng |
| `update-count-sql` khác SQL đã chạy | Preview và update khác database, filter, artifact hoặc trạng thái lịch sử | Cố định cấu hình; sinh preview mới |
| Count đạt nhưng số SQL ít hơn mong đợi | Một changeset có nhiều/ít statement, hoặc `MARK_RAN`/cơ chế chạy lại | Xem `EXECTYPE`, SQL dự kiến và hậu kiểm trạng thái schema |
| Đợt B chạy thiếu backfill | Backfill bị lọc bởi context/dbms hoặc không đúng thứ tự | Review chuỗi phụ thuộc và filter; không tiếp tục constraint |
| Spring Boot chạy hết changelog dù pipeline vừa chạy hai changeset | Ứng dụng tự động gọi update khi startup | Thống nhất nơi sở hữu migration, cấu hình startup phù hợp |
| Rollback-count xóa không đúng tập vừa deploy | Có changeset khác được áp dụng sau đó hoặc lịch sử khác | Xác định tập rollback theo ID/tag, review SQL và dependency |
| Liquibase báo checksum mismatch | Chỉnh changeset lịch sử đã chạy | Khôi phục lịch sử và tạo changeset mới khi cần |
| Staging và production đếm khác nhau | Lịch sử, DBMS, dữ liệu hoặc context/label khác | Lập kế hoạch theo từng database đích |
| Lệnh update-count báo hoàn tất nhưng ứng dụng vẫn lỗi | Schema đã đổi nhưng app chưa tương thích, data quality chưa đạt | Kết hợp kiểm thử ứng dụng, đối soát và release gate |

Không chữa vấn đề bằng cách tăng `count` cho đến khi “đủ” hoặc bằng việc xóa trực tiếp `DATABASECHANGELOG`. Mọi thay đổi trạng thái cần có giải thích bằng changeset và dữ liệu thực tế.

## 16. Bài tập thực hành: triển khai ba đợt trên database thử nghiệm

**Đề bài:** một PostgreSQL database dùng riêng cho lab có bảng `customer_account(id, legacy_status)`. Changelog gồm sáu changeset từ phần 5. Người học cần triển khai theo ba đợt `count=2`, không dùng database production.

### Bước 1. Chuẩn bị và xác minh trạng thái ban đầu

- Tạo dữ liệu thử nghiệm với `active`, `enabled`, `disabled`, `suspended` và NULL.
- Kiểm tra những dữ liệu chưa thể ánh xạ; nếu thêm giá trị `closed`, precondition của backfill phải chặn thay vì tự suy mã.
- Kiểm tra `DATABASECHANGELOG` ban đầu và `status --verbose` để biết chính xác có bao nhiêu changeset pending.
- Xác nhận root changelog và các bộ lọc không bỏ qua bất kỳ bước tiền đề nào.

### Bước 2. Chạy đợt A

Preview `count=2`, xác nhận đúng 001–002; sau đó cập nhật. Kiểm tra bảng danh mục và lịch sử. Ghi lại ID, AUTHOR, FILENAME, EXECTYPE.

### Bước 3. Chạy đợt B

Preview 003–004. Nếu precondition chặn vì `closed`, xử lý ngoại lệ ở nguồn dữ liệu thử nghiệm, không sửa changeset đã chạy. Cập nhật, kiểm tra số NULL, đối soát mapping, quan sát transaction/lock khi có nhiều dòng.

### Bước 4. Đặt mốc chuyển tiếp ứng dụng

Giả lập một writer cũ có thể INSERT dòng mới không có `status_code`. Giải thích vì sao phải ngừng đường ghi cũ hoặc bổ sung dual-write trước khi đưa constraint vào. Backfill lại nếu cần và xác nhận toàn bộ dữ liệu đã đạt điều kiện.

### Bước 5. Chạy đợt C

Preview 005–006, kiểm tra SQL ràng buộc và khả năng rollback. Sau cập nhật, thử các trường hợp insert `status_code = NULL` và mã không có trong danh mục trên một transaction lab để xác nhận ràng buộc hoạt động.

### Bước 6. Kiểm tra retry

Gọi `status --verbose` lần nữa. Trả lời: nếu chạy lại `update-count --count=2` ngay lúc này trong khi changelog có thêm changeset 007–008, Liquibase có thể làm gì? Vì sao job CI/CD phải xác nhận danh tính changeset trước khi retry?

### Bước 7. Phân tích rollback

Xem `rollback-count-sql --count=2` và so sánh với lịch sử. Nêu lý do không nên chạy rollback thật nếu chưa phân tích rằng hai changeset cuối có dependency hoặc dữ liệu không thể phục hồi đúng.

**Tiêu chí hoàn thành:** mỗi đợt có danh sách ID dự kiến và bằng chứng hậu kiểm; không bỏ qua precondition, không lặp dữ liệu ngoài ý muốn, không giả định count tạo một transaction xuyên nhiều changeset.

## 17. Checklist trước khi dùng update-count trong production

- [ ] Đã xác nhận dùng `update-count` vì có điểm dừng triển khai thực sự, không chỉ vì thích chia nhỏ số lượng.
- [ ] Có danh sách ID/AUTHOR/FILENAME cụ thể tương ứng từng đợt, không chỉ số `count`.
- [ ] Root changelog, thứ tự include và chính sách bộ lọc được kiểm tra.
- [ ] DBMS, URL, schema và tài khoản migration trỏ đúng môi trường.
- [ ] `validate` và `status --verbose` được chạy với cấu hình triển khai thực tế.
- [ ] Preview `update-count-sql --count=N` đã được review theo phiên bản Liquibase đang dùng.
- [ ] Mỗi đợt có điều kiện tiền đề và hậu kiểm schema/dữ liệu cụ thể.
- [ ] Không có bước phụ thuộc bị tách sai hoặc bị lọc bỏ giữa hai đợt.
- [ ] Đã xét `runAlways`, `runOnChange` và precondition `MARK_RAN`/`CONTINUE` nếu có.
- [ ] Đã kiểm tra lịch sử `DATABASECHANGELOG` trước và sau; phân biệt count với số SQL statement.
- [ ] Job tự động retry không chuyển vô tình sang những changeset kế tiếp.
- [ ] Với Spring Boot, đã thống nhất ứng dụng hay pipeline chịu trách nhiệm chạy Liquibase.
- [ ] Có phương án xử lý khi đợt cập nhật chỉ thành công một phần; không giả định atomic toàn batch.
- [ ] Rollback-count được review riêng; không xem nó là phép đảo mặc định của update-count.
- [ ] Changelog đã chạy được giữ bất biến; không sửa checksum hoặc đường dẫn để điều chỉnh tập pending.
- [ ] Mỗi mốc phát hành có thể được kiểm chứng độc lập và được phê duyệt trước khi tiếp tục.

**Kết luận:** `update-count` cho phép Liquibase cập nhật database theo một số lượng changeset giới hạn, rất hữu ích khi cần dừng để kiểm tra dữ liệu, triển khai ứng dụng chuyển tiếp hoặc phê duyệt một giai đoạn migration. Giá trị của công cụ nằm ở **điểm dừng có kiểm soát**, không nằm ở con số count tự thân. Luôn xác nhận danh tính và thứ tự candidate, xem trước SQL, đối chiếu `DATABASECHANGELOG` và kiểm chứng trạng thái nghiệp vụ sau mỗi đợt; nếu bỏ qua những bước đó, cùng một `--count=2` có thể tạo ra kết quả khác nhau giữa các lần chạy hoặc các môi trường.

