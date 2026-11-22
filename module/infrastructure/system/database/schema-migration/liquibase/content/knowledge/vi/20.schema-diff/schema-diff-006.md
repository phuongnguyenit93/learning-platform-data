# Giới hạn nhận diện đổi tên và ý nghĩa nghiệp vụ

## 1. Vì sao schema diff không thể tự kết luận ý định?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Công việc thực tế còn cần migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Khi đối chiếu hai database, nhóm thường muốn biết bảng, cột, index hay constraint nào đã thay đổi. Tuy nhiên, **khác biệt cấu trúc không tự giải thích ý nghĩa nghiệp vụ**, và thay đổi ý nghĩa nghiệp vụ cũng có thể không tạo ra khác biệt cấu trúc.

Ví dụ, schema cũ có bảng `customer` với cột `name`; schema mới có bảng `client` với cột `display_name`. Đây có thể là đổi tên bảng và cột, nhưng cũng có thể là mô hình client mới, không còn cùng vòng đời hoặc cùng ý nghĩa với customer cũ. Một công cụ so sánh có thể báo đối tượng cũ không tồn tại ở target và đối tượng mới xuất hiện; nó không có đủ thông tin để khẳng định đây là cùng một thực thể logic.

Chiều ngược lại cũng quan trọng. Cột `status VARCHAR(20)` vẫn giữ tên, kiểu và nullability, nhưng quy ước giá trị đổi từ `A`/`D` sang `ACTIVE`/`DISABLED`. Schema diff có thể không báo khác biệt, dù dữ liệu và hợp đồng ứng dụng đã thay đổi đáng kể.

Bài học này giải thích giới hạn nhận diện rename và ý nghĩa nghiệp vụ khi dùng Liquibase `diff` và `diff-changelog`. Sau bài học, bạn có thể phân biệt khác biệt cấu trúc với semantic change, hiểu hướng reference/target, nhận diện trường hợp rename có thể bị biểu diễn thành drop/create, review changelog sinh tự động và thiết kế migration giữ dữ liệu, dependency cùng ứng dụng nhất quán.

## 2. Phân biệt diff, diff-changelog và generate-changelog

| Lệnh | Mục đích | Kết quả |
|---|---|---|
| `diff` | So sánh reference database với target database | Báo cáo các đối tượng khác nhau theo phạm vi diff |
| `diff-changelog` | Sinh changelog mô tả thay đổi để target tiến gần reference | Changelog nháp từ kết quả so sánh |
| `generate-changelog` | Sinh changelog mô tả schema của một database hiện có | Bản mô tả trạng thái schema, thường dùng khi bắt đầu quản lý database bằng Liquibase |

Các lệnh này không tự xác định ý nghĩa nghiệp vụ. `diff` giúp quan sát khác biệt; `diff-changelog` hỗ trợ tạo migration; `generate-changelog` mô tả trạng thái schema hiện có. Chúng không thay thế việc thiết kế migration, kiểm thử dữ liệu hay review của người hiểu domain.

### 2.1. Reference và target: hướng so sánh phải rõ ràng

Với cấu hình CLI thông dụng:

- `--reference-url` chỉ database được xem là trạng thái tham chiếu.
- `--url` chỉ database mục tiêu cần so sánh hoặc đồng bộ theo hướng reference.

Ví dụ:

```bash
liquibase \
  --reference-url="$REFERENCE_JDBC_URL" \
  --url="$TARGET_JDBC_URL" \
  diff
```

Cần cung cấp credentials và driver qua cấu hình an toàn; không đặt secret trực tiếp trong lệnh có thể lưu lại trong shell history hoặc log pipeline.

Báo cáo thường phân loại:

- **Missing ở target:** đối tượng có trong reference nhưng không được tìm thấy ở target.
- **Unexpected ở target:** đối tượng có trong target nhưng không có trong reference.
- **Changed:** thuộc tính được so sánh của đối tượng có khác biệt.

Tên nhóm và mức chi tiết phụ thuộc phiên bản, DBMS và loại đối tượng. “Missing” chỉ có nghĩa là không tìm thấy trong snapshot target theo phạm vi hiện tại; nó không chứng minh đối tượng đã bị xóa có chủ đích.

### 2.2. diff-changelog không thực thi migration

Ví dụ:

```bash
liquibase \
  --reference-url="$REFERENCE_JDBC_URL" \
  --url="$TARGET_JDBC_URL" \
  diff-changelog \
  --changelog-file=build/generated/schema-diff.yaml
```

Lệnh tạo changelog nháp để đưa target đồng bộ với reference theo các khác biệt được nhận diện. Nó **không áp dụng changelog vào target**. File được sinh phải được review, quản lý phiên bản và kiểm tra trước khi chạy `update`.

Nếu output đề xuất `dropTable` cho bảng cũ và `createTable` cho bảng mới, không chạy ngay chỉ vì cấu trúc cuối cùng có vẻ đúng. Nếu thực chất chỉ cần rename, drop/create có thể xóa dữ liệu và phá dependency.

### 2.3. generate-changelog không tái tạo lịch sử

`generate-changelog` mô tả schema tại thời điểm chụp. Nó không tự tái tạo chính xác những bước đã đưa database từ trạng thái ban đầu đến hiện tại, cũng không suy ra ai đổi tên đối tượng hoặc vì sao nghiệp vụ đổi.

Khi đưa database hiện hữu vào Liquibase, cần thiết kế baseline và đồng bộ lịch sử riêng. Changelog sinh từ schema hiện tại không phải bằng chứng rằng các môi trường khác đã chạy cùng migration.

## 3. Schema diff nhìn thấy những gì?

Tùy DBMS, driver, phiên bản Liquibase và loại diff được hỗ trợ, công cụ có thể so sánh các nhóm đối tượng như:

- Catalog, schema và bảng.
- Cột, kiểu dữ liệu, nullability và default.
- Primary key, foreign key, unique constraint và check constraint.
- Index.
- View và một số đối tượng SQL như sequence, procedure hoặc trigger khi được hỗ trợ.
- Các nhóm bổ sung tùy extension/edition và cấu hình.

Có thể giới hạn phạm vi bằng tham số loại diff, ví dụ:

```bash
liquibase \
  --reference-url="$REFERENCE_JDBC_URL" \
  --url="$TARGET_JDBC_URL" \
  --diff-types=tables,columns,primarykeys,foreignkeys,indexes,views \
  diff
```

Danh sách diff type và cú pháp option cần được xác nhận với phiên bản Liquibase đang dùng. Loại một nhóm khỏi diff chỉ có nghĩa nhóm đó không được báo cáo trong lần so sánh; **không có nghĩa nhóm đó không khác nhau**.

### 3.1. Diff phụ thuộc vào snapshot metadata

Liquibase đọc metadata từ hai database để tạo snapshot đối tượng. Kết quả có thể bị ảnh hưởng bởi:

- Tài khoản kết nối có quyền nhìn thấy schema/đối tượng nào.
- Default schema, schema/catalog và search path.
- Quy tắc hoa/thường, identifier có quote và tên phân biệt hoa thường.
- Phiên bản DBMS, JDBC driver, Liquibase và extension.
- Loại đối tượng được hỗ trợ hoặc bị lọc.
- Khác biệt cách biểu diễn default, kiểu dữ liệu hoặc metadata giữa các hệ quản trị.

Nếu tài khoản reference không nhìn thấy một view, báo cáo có thể cho thấy view đó missing dù nó vẫn tồn tại. Trước khi kết luận drift, xác nhận quyền metadata và cấu hình kết nối của cả hai phía.

### 3.2. Schema diff không xác nhận ý nghĩa dữ liệu

Schema diff không tự chứng minh rằng:

- Mọi hàng dữ liệu có cùng ý nghĩa.
- Giá trị trạng thái đã được chuyển đúng.
- Tổng tiền, số lượng đơn hàng hoặc quan hệ nghiệp vụ được bảo toàn.
- Hai cột cùng kiểu có cùng đơn vị đo hoặc quy ước.
- Ứng dụng và API hiểu giống nhau về dữ liệu.

Một số khả năng so sánh dữ liệu có thể phụ thuộc edition, extension hoặc công cụ riêng. Dù có data comparison, việc diễn giải ý nghĩa nghiệp vụ vẫn cần quy tắc và kiểm chứng domain.

## 4. Vì sao công cụ khó kết luận một đối tượng đã được đổi tên?

Để nhận diện rename chắc chắn, công cụ phải biết đối tượng trước và sau là cùng một thực thể logic. Nhưng schema chủ yếu cung cấp tên, kiểu, thuộc tính, ràng buộc và quan hệ. Nó không lưu đầy đủ ý định như:

- “Bảng này đổi tên vì thuật ngữ nghiệp vụ mới.”
- “Hai cột này cùng chứa mã khách hàng, dù tên và kiểu khác nhau.”
- “Cột cũ bị bỏ vì dữ liệu được tách sang hai cột mới.”
- “Bảng mới là aggregate khác, không phải bảng cũ đổi tên.”
- “Giá trị cũ cần được quy đổi theo một mapping nghiệp vụ.”

Bảng `customer` biến mất và `client` xuất hiện có thể là rename; cũng có thể là drop một bảng thử nghiệm và tạo bảng độc lập. Cấu trúc tương đồng chỉ là dấu hiệu để con người điều tra, không phải bằng chứng.

**Không giả định `diff` hoặc `diff-changelog` luôn nhận diện rename theo ý định nghiệp vụ.** Hãy xem chúng như công cụ tìm khác biệt cấu trúc. Nếu kết quả có dấu hiệu rename, cần xác nhận bằng khóa, dữ liệu, dependency, migration history và yêu cầu domain.

### 4.1. Rename có thể xuất hiện thành missing và unexpected

Ví dụ:

```text
Reference:
  table: client
  columns: id, display_name

Target:
  table: customer
  columns: id, name
```

Báo cáo có thể thể hiện theo hướng bảng `client` missing và bảng `customer` unexpected; ở mức cột, những tên khác nhau cũng có thể được biểu diễn như khác biệt đối tượng. Cách biểu diễn chính xác phụ thuộc snapshot và loại diff.

Nếu `diff-changelog` sinh drop/create, đó là đề xuất dựa trên khác biệt được nhận diện. Nó có thể đúng nếu muốn thay thế đối tượng; nó có thể phá hủy dữ liệu nếu thực chất chỉ cần rename.

### 4.2. Cấu trúc giống nhau không chứng minh cùng ý nghĩa

Hai bảng có cùng số cột, kiểu dữ liệu và khóa chính có thể là ứng viên rename. Nhưng chúng cũng có thể chứa hai tập thực thể độc lập. Ngược lại, rename kèm thay đổi kiểu, tách cột hoặc thay khóa có thể không còn giống nhau về hình thức.

Không xây quy trình tự động “nếu cấu trúc giống thì rename”. Cần mapping và xác nhận từ owner domain.

## 5. Thu thập bằng chứng trước khi kết luận rename

Khi báo cáo có một đối tượng missing và một đối tượng unexpected, hãy đối chiếu nhiều nguồn:

| Bằng chứng | Câu hỏi | Giá trị xác minh |
|---|---|---|
| Khóa chính | Hai đối tượng có cùng khóa định danh hoặc mapping khóa không? | Gợi ý quan hệ nhưng không đủ kết luận |
| Dữ liệu | Số hàng, giá trị, phân bố và mẫu dữ liệu có khớp quy tắc không? | Phát hiện mất hoặc đổi dữ liệu |
| Foreign key | Các quan hệ tham chiếu cũ chuyển sang đối tượng mới thế nào? | Phát hiện dependency bị bỏ sót |
| Index/constraint | Ràng buộc có được giữ đúng hoặc thay đổi có chủ đích không? | Đánh giá tính toàn vẹn và hiệu năng |
| View/procedure/trigger | Đối tượng SQL nào phụ thuộc tên cũ? | Xác định ảnh hưởng ngoài bảng |
| Ứng dụng | Entity, repository, native SQL, API và batch job đã đổi tên chưa? | Xác nhận consumer |
| Migration history | Có changeset rename hoặc quyết định domain đã review không? | Truy vết ý định |
| Owner nghiệp vụ | Đối tượng mới có cùng ý nghĩa, vòng đời và quyền sở hữu không? | Xác nhận semantic identity |

Một mapping có thể được ghi rõ:

```text
customer.name  -> client.display_name
customer.id    -> client.id
customer       -> client

Quy tắc:
- Giữ nguyên dữ liệu và khóa.
- Chỉ đổi tên vật lý.
- Không thay đổi ý nghĩa của tên hoặc giá trị.
```

Nếu chỉ một phần dữ liệu được chuyển, hoặc bảng mới hợp nhất nhiều nguồn, đây không còn là rename thuần túy. Cần thiết kế data migration riêng với mapping, xử lý ngoại lệ và đối soát.

## 6. Phân biệt rename, drop/create và thay đổi mô hình

| Trường hợp | Dấu hiệu | Hướng migration cần cân nhắc |
|---|---|---|
| Rename thuần túy | Cùng thực thể, cùng dữ liệu, chỉ thay tên vật lý | Change type rename tường minh, kiểm tra dependency |
| Drop/create có chủ đích | Đối tượng cũ hết vòng đời, đối tượng mới độc lập | Tạo/xóa theo kế hoạch, backup và migration dữ liệu nếu cần |
| Tách một bảng thành nhiều bảng | Dữ liệu cũ phân phối sang nhiều thực thể | Expand, mapping, backfill và contract |
| Gộp nhiều bảng | Nhiều nguồn hợp nhất vào một mô hình | Quy tắc hợp nhất, xử lý xung đột khóa và provenance |
| Đổi tên kèm đổi kiểu | Tên và biểu diễn thay đổi cùng lúc | Rename/modify type có thứ tự, kiểm tra CAST và consumer |
| Đổi ý nghĩa nhưng giữ schema | Cấu trúc giống, semantics đổi | Data migration, versioning hợp đồng, kiểm thử domain |

Ví dụ `customer.name` trước đây lưu tên pháp lý, còn `client.display_name` lưu tên hiển thị tùy chỉnh. Hai cột có thể chứa chuỗi giống nhau ở dữ liệu hiện tại nhưng không có cùng ý nghĩa. Dùng rename thay cho mapping sẽ làm dữ liệu được diễn giải sai.

## 7. Viết rename tường minh trong Liquibase

Nếu đã xác nhận thay đổi chỉ là đổi tên và DBMS hỗ trợ, biểu diễn ý định bằng change type phù hợp thay vì chấp nhận drop/create tự động.

### 7.1. Đổi tên bảng

Ví dụ YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: 040-rename-customer-to-client
      author: schema-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
      changes:
        - renameTable:
            oldTableName: customer
            newTableName: client
      rollback:
        - renameTable:
            oldTableName: client
            newTableName: customer
```

Rollback có thể hợp lý nếu không có đối tượng khác chiếm tên cũ và không có migration xen vào gây xung đột. Cần khai báo schema/catalog khi dự án không dùng schema mặc định, và kiểm tra tên object trên DBMS đích.

### 7.2. Đổi tên cột

```yaml
databaseChangeLog:
  - changeSet:
      id: 041-rename-customer-name
      author: schema-team
      preConditions:
        - onFail: HALT
        - columnExists:
            tableName: client
            columnName: name
      changes:
        - renameColumn:
            tableName: client
            oldColumnName: name
            newColumnName: display_name
            columnDataType: varchar(200)
      rollback:
        - renameColumn:
            tableName: client
            oldColumnName: display_name
            newColumnName: name
            columnDataType: varchar(200)
```

`columnDataType` được đưa vào ví dụ để hỗ trợ những DBMS/kiểu change cần thông tin kiểu. Hãy xác nhận thuộc tính bắt buộc, khả năng hỗ trợ và SQL sinh ra ở phiên bản Liquibase đang dùng. Không copy nguyên changelog giữa PostgreSQL, Oracle, MySQL và SQL Server mà không kiểm thử.

### 7.3. Rename không tự cập nhật ứng dụng

Sau khi đổi tên vật lý, cần tìm mọi consumer:

- JPA entity và mapping `@Table`/`@Column`.
- Spring Data repository, native query, JPQL hoặc query builder.
- Stored procedure, trigger, view và function.
- Batch job, ETL, CDC, BI và báo cáo.
- API response, serializer, DTO và integration contract.
- Script vận hành và truy vấn hỗ trợ production.

Liquibase thay đổi database; nó không tự sửa source code, câu SQL nằm trong ứng dụng hoặc consumer ở hệ thống khác. Đổi tên trong database mà code cũ vẫn query tên cũ sẽ gây lỗi runtime.

## 8. Review changelog được sinh tự động

Giả sử diff-changelog đề xuất một thay đổi có ý tưởng như sau:

```yaml
databaseChangeLog:
  - changeSet:
      id: generated-1
      author: liquibase
      changes:
        - dropTable:
            tableName: customer

  - changeSet:
      id: generated-2
      author: liquibase
      changes:
        - createTable:
            tableName: client
            columns:
              - column:
                  name: id
                  type: bigint
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: display_name
                  type: varchar(200)
```

Đây là ví dụ minh họa một đề xuất có thể xuất hiện khi khác biệt được diễn giải là xóa/thêm; không khẳng định mọi phiên bản Liquibase luôn sinh đúng các change này cho cùng tình huống.

Trước khi áp dụng, reviewer phải hỏi:

1. Bảng `customer` có dữ liệu cần giữ không?
2. `client` đã có dữ liệu độc lập chưa?
3. Hai bảng có cùng khóa và cùng semantics không?
4. Có FK, index, view, trigger, grant hoặc job phụ thuộc không?
5. Drop/create có làm mất sequence, identity, permission hoặc comment không?
6. Có thể thay bằng `renameTable` và `renameColumn` không?
7. Ứng dụng cũ có cần giai đoạn tương thích không?
8. Rollback có khôi phục đúng dữ liệu hay chỉ tạo lại bảng rỗng?

Nếu đây là rename thuần túy, chuyển đề xuất thành changeset rename được review. Nếu đây là mô hình mới, hãy thiết kế migration dữ liệu tường minh thay vì dùng drop/create như phép chuyển dữ liệu.

## 9. Semantic change có thể không xuất hiện trong schema diff

### 9.1. Mã trạng thái đổi quy ước

Trước đây:

```text
status VARCHAR(20)
"A" = Active
"D" = Disabled
```

Sau khi thống nhất domain:

```text
status VARCHAR(20)
"ACTIVE"   = tài khoản đang hoạt động
"DISABLED" = tài khoản bị vô hiệu hóa
```

Tên và kiểu cột vẫn giống nhau. Schema diff có thể không báo khác biệt, nhưng ứng dụng và dữ liệu cần migration. Phải có bảng mapping, truy vấn phát hiện mã ngoài tập, quy tắc chuyển đổi và kiểm tra consumer.

Ví dụ mapping PostgreSQL:

```sql
UPDATE customer_account
SET status = CASE status
    WHEN 'A' THEN 'ACTIVE'
    WHEN 'D' THEN 'DISABLED'
END
WHERE status IN ('A', 'D');
```

Trước khi chạy, xác minh không còn mã khác như `P` hoặc `X` và hiểu ý nghĩa nghiệp vụ của từng giá trị. Không dùng `ELSE 'ACTIVE'` để gán mọi dữ liệu chưa biết thành trạng thái hợp lệ.

### 9.2. Cột cùng kiểu nhưng khác đơn vị

`weight NUMERIC(10,2)` có thể lưu kilogram ở một hệ thống và pound ở hệ thống khác. Schema diff không biết đơn vị. Thay đổi ý nghĩa từ kg sang lb cần chuyển đổi giá trị theo hệ số, cập nhật tên/hợp đồng nếu cần và kiểm tra số liệu biên. Chỉ đổi comment hoặc tên cột không đủ.

### 9.3. Khóa ngoại cùng kiểu nhưng đổi thực thể tham chiếu

`customer_id BIGINT` có thể trước đây tham chiếu `customer.id`, sau đó được hiểu là `billing_account.id`. Kiểu dữ liệu và tên cột có thể không đổi, nhưng FK, dữ liệu và nghiệp vụ thay đổi. Cần xác định mapping thực thể, sửa ràng buộc và kiểm tra orphan.

### 9.4. Đổi ý nghĩa của NULL hoặc default

Một cột nullable có thể trước đây dùng NULL để biểu diễn “chưa biết”, nhưng nay được hiểu là “không áp dụng”. Diff chỉ nhìn thấy nullability/default, không suy ra cách ứng dụng diễn giải. Đây là thay đổi contract cần được tài liệu hóa và kiểm thử riêng.

## 10. Kiểm tra dữ liệu và semantics ngoài schema diff

Khi có thay đổi ý nghĩa nghiệp vụ, bổ sung kiểm tra data-oriented:

- Phân bố giá trị trước/sau.
- NULL, chuỗi rỗng và giá trị ngoài mapping.
- Min/max, precision/scale và đơn vị đo.
- Số lượng bản ghi, duplicate, orphan và quan hệ khóa.
- Đối soát tổng tiền, số lượng, trạng thái hoặc chỉ số nghiệp vụ.
- Mẫu dữ liệu theo thời gian và các trường hợp biên.
- So sánh đầu ra API/report giữa phiên bản cũ và mới.

Ví dụ kiểm tra trạng thái ngoài tập cho phép:

```sql
SELECT status, COUNT(*) AS row_count
FROM customer_account
WHERE status IS NULL
   OR status NOT IN ('ACTIVE', 'DISABLED')
GROUP BY status
ORDER BY row_count DESC;
```

Nếu `PENDING` là trạng thái hợp lệ, phải đưa nó vào tập được phép và định nghĩa rõ khi nào phát sinh. Truy vấn này chỉ là một phần kiểm tra dữ liệu, không thay thế schema diff.

### 10.1. Đối soát số lượng và mapping

| Chỉ số | Trước migration | Sau migration | Tiêu chí |
|---|---|---|---|
| Tổng số khách hàng | Đo từ nguồn | Đo từ đích | Khớp hoặc có chênh lệch được giải thích |
| Số ID duy nhất | Đo từ nguồn | Đo từ đích | Không mất/nhân bản ID |
| Số trạng thái theo nhóm | Phân bố cũ | Phân bố mới | Khớp mapping đã duyệt |
| Bản ghi không có parent | Đếm orphan | Đếm orphan | Không tăng ngoài quy tắc |
| Giá trị NULL | Đếm NULL | Đếm NULL | Đúng chính sách mới |

Không kết luận chỉ từ tổng số dòng bằng nhau. Hai tập dữ liệu có thể cùng số dòng nhưng mapping sai, trùng khóa hoặc mất quan hệ.

## 11. Cấu hình so sánh phải công bằng và tái lập được

Một diff đáng tin cậy cần reference và target được chụp trong điều kiện có thể so sánh. Cần thống nhất:

1. DBMS và phiên bản tương thích.
2. JDBC driver và Liquibase version.
3. Catalog, schema và default schema.
4. Quyền metadata của tài khoản kết nối.
5. Các object type được so sánh.
6. Include/exclude filters và phạm vi object.
7. Thời điểm snapshot, tránh database đang thay đổi DDL giữa lúc so sánh.
8. Extension, collation, type tùy chỉnh và metadata DBMS-specific.

Ví dụ giới hạn một số loại đối tượng:

```bash
liquibase \
  --reference-url="$REFERENCE_JDBC_URL" \
  --url="$TARGET_JDBC_URL" \
  --diff-types=tables,columns,primarykeys,foreignkeys,indexes,views \
  diff
```

Tên tùy chọn và danh sách type có thể khác theo phiên bản/edition. Nếu bỏ qua sequence hoặc view, không thể dùng báo cáo đó để kết luận những đối tượng ấy không bị drift.

### 11.1. Schema trùng tên và quyền metadata

Nếu reference và target đều có schema `public` nhưng user kết nối có search path khác, object được snapshot có thể không tương ứng. Cần chỉ định schema/catalog rõ bằng thuộc tính phiên bản hỗ trợ và xem log snapshot.

Tài khoản thiếu quyền nhìn thấy metadata cũng có thể tạo báo cáo sai. Hãy xác nhận quyền xem đối tượng ở cả hai database. Dùng tài khoản đủ quyền metadata nhưng vẫn tuân thủ nguyên tắc quyền tối thiểu; không cần mặc định dùng superuser.

## 12. Từ diff đến migration an toàn

```text
Chọn reference có nguồn gốc rõ ràng
                |
                v
Chọn target và xác nhận DBMS/schema/permissions
                |
                v
Chạy diff để phát hiện cấu trúc khác nhau
                |
                v
Phân loại: add / drop / alter / rename candidate / semantic change
                |
                v
Đối chiếu owner, dữ liệu, dependency, ứng dụng
                |
                v
Sinh diff-changelog nếu phù hợp
                |
                v
Review và chỉnh thành changeset có ý nghĩa rõ
                |
                v
validate + update-sql + test trên DB đại diện
                |
                v
Đối soát dữ liệu và kiểm thử consumer
                |
                v
Phê duyệt rồi triển khai có giám sát
```

Reference phải là trạng thái mong muốn đã được duyệt, không phải database tình cờ mới nhất. Target phải là database sẽ nhận migration. Báo cáo diff phải được phân loại thủ công; generated changelog là bản nháp kỹ thuật cần review tên changeset, author, precondition, rollback và thứ tự.

Nếu có rename, viết rename tường minh hoặc thiết kế expand–migrate–contract. Nếu có semantic change, bổ sung data migration và kiểm tra nghiệp vụ. SQL preview phải được tạo từ đúng DBMS và cấu hình gần môi trường triển khai.

## 13. Expand–migrate–contract cho rename phá vỡ compatibility

Nếu đổi tên trực tiếp sẽ làm ứng dụng cũ lỗi, có thể chia thành nhiều giai đoạn:

```text
EXPAND
  thêm cấu trúc mới hoặc view tương thích
       |
       v
MIGRATE
  ứng dụng đọc/ghi theo cách chuyển tiếp
  backfill và đối soát dữ liệu
       |
       v
CUTOVER
  chuyển consumer sang tên/ý nghĩa mới
       |
       v
VERIFY
  xác nhận không còn consumer cũ
       |
       v
CONTRACT
  bỏ cấu trúc cũ và quyền không còn dùng
```

Ví dụ `customer.name` chuyển sang `client.display_name`:

1. Thêm cấu trúc mới ở trạng thái tương thích.
2. Triển khai code đọc dữ liệu mới và fallback có kiểm soát.
3. Dual-write trong cùng transaction hoặc cơ chế đồng bộ có bảo đảm.
4. Backfill dữ liệu cũ và đối soát từng nhóm.
5. Chuyển tất cả consumer sang tên mới.
6. Ngừng ghi/đọc tên cũ.
7. Xóa cột/bảng cũ trong release riêng sau khi đủ điều kiện.

Không mặc định dual-write an toàn: nếu hai lần ghi không cùng transaction hoặc retry không idempotent, dữ liệu có thể lệch. Cần cơ chế đồng bộ, log, checkpoint và quy trình sửa chênh lệch.

Nếu chỉ là rename thuần túy, `renameColumn`/`renameTable` có thể đơn giản hơn. Nếu thay đổi ý nghĩa hoặc cấu trúc sâu, expand–migrate–contract giúp kiểm soát cửa sổ tương thích.

## 14. Rollback khi rename hoặc semantic change

Rollback một rename thuần túy có thể là rename ngược nếu không có đối tượng khác chiếm tên cũ và không có DDL xen vào gây xung đột. Nhưng nếu sau rename đã có migration tạo cột/bảng cũ, thao tác ngược có thể thất bại.

Với semantic change, rollback khó hơn:

- Mapping nhiều-một không thể khôi phục chính xác giá trị cũ nếu không lưu nguồn.
- Chuyển đơn vị có thể gây sai số làm tròn.
- Hợp nhất bảng có thể mất provenance nếu không lưu mapping ID.
- Xóa cột cũ làm mất biểu diễn gốc.
- Consumer đã nhận dữ liệu mới có thể không tương thích với schema cũ.

Rollback cần được thiết kế cùng migration. Lưu mapping, snapshot hoặc bản sao dữ liệu theo chính sách; xác định khi nào forward fix an toàn hơn rollback. Không viết rollback giả định bằng một lệnh rename ngược nếu dữ liệu đã biến đổi.

## 15. Spring Boot và CI/CD

Spring Boot thường đọc root changelog từ classpath:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Trong CI/CD, có thể chia cổng kiểm soát:

1. Build artifact chứa changelog và file SQL phụ trợ.
2. Tạo reference database từ trạng thái đã duyệt hoặc database chuẩn đã khóa phiên bản.
3. Kết nối target bằng tài khoản có quyền metadata phù hợp.
4. Chạy `diff` và lưu báo cáo.
5. Phân loại missing/unexpected/changed, đánh dấu rename candidate và semantic change.
6. Sinh `diff-changelog` nếu hữu ích; không tự động chạy generated changelog.
7. Review/điều chỉnh thành changeset tường minh, bao gồm precondition và rollback.
8. Chạy `validate` và `update-sql` trên DBMS đại diện.
9. Kiểm thử data migration và ứng dụng cũ/mới.
10. Triển khai, kiểm tra `DATABASECHANGELOG` và đối soát dữ liệu/schema.

Nếu ứng dụng tự chạy Liquibase khi startup, cần thống nhất với pipeline để không có hai nguồn sở hữu migration. `DATABASECHANGELOGLOCK` điều phối tiến trình Liquibase đồng thời, nhưng không giải quyết semantic mismatch hoặc bảo đảm rename tương thích với mọi instance ứng dụng.

### 15.1. Bảo vệ thông tin kết nối

Dùng biến môi trường hoặc secret store cho URL/credentials. Không đưa password vào file generated, báo cáo diff hoặc log artifact. Output diff có thể tiết lộ tên schema, bảng, cột và đối tượng nội bộ; chỉ chia sẻ trong hệ thống có quyền truy cập phù hợp.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hành động phù hợp |
|---|---|---|
| Rename bị sinh thành drop/create | Diff không biết ý định domain | Review dữ liệu/dependency; thay bằng rename tường minh nếu đúng |
| Hai cột cùng kiểu nhưng ý nghĩa khác | Structural diff không mô tả đơn vị hoặc semantics | Data mapping, contract và test nghiệp vụ |
| Diff báo object missing nhưng object vẫn tồn tại | Thiếu quyền metadata, schema/default schema khác hoặc filter | Kiểm tra snapshot/config/permissions |
| Diff không báo thay đổi trạng thái | Cấu trúc cột không đổi, chỉ giá trị nghiệp vụ đổi | Truy vấn data quality và migration dữ liệu |
| diff-changelog sinh SQL phá hủy | Generated changelog mô tả chênh lệch bằng drop/create | Không chạy trực tiếp; chỉnh thành migration phù hợp |
| Rename thành công nhưng ứng dụng lỗi | Code, view, procedure hoặc job vẫn dùng tên cũ | Kiểm tra consumer, rollout tương thích |
| Schema diff sạch nhưng dữ liệu sai | Không có data mapping/semantic validation | Đối soát giá trị, tổng, NULL, duplicate và orphan |
| Staging và production diff khác nhau | Khác lịch sử, DBMS, schema, filter hoặc drift | So sánh từng target và xác định baseline đúng |
| Generated changelog quá lớn hoặc lộn xộn | Snapshot khác nhau hoặc phạm vi diff quá rộng | Giới hạn object/type và review reference |
| Rename cột làm mất grant/view/function | Dependency DBMS-specific chưa được quản lý | Lập dependency inventory, kiểm thử SQL và quyền |

Không xử lý bằng cách chạy lặp `diff-changelog` cho đến khi báo cáo hết khác biệt. Mục tiêu là đưa target về trạng thái mong muốn mà không làm sai dữ liệu và hợp đồng, không phải làm cho công cụ báo cáo sạch bằng mọi giá.

## 17. Bài thực hành: phân loại rename và semantic change

**Bối cảnh:** reference database có bảng `client(id, display_name, status_code)`; target database có bảng `customer(id, name, status)`. Hai bảng có số lượng dòng tương đương và cùng kiểu khóa chính. Thực hành trên database lab, không dùng production.

1. Chạy `diff` với reference/target rõ ràng; lưu báo cáo missing/unexpected/changed.
2. Xác nhận schema, quyền, DBMS, diff types và phiên bản.
3. Phân loại `customer` → `client` là rename candidate; `name` → `display_name` có thể là rename hoặc đổi ý nghĩa; `status` → `status_code` có thể thay quy ước giá trị.
4. So sánh khóa, mẫu dữ liệu, FK, index, view, consumer và yêu cầu domain.
5. Sinh `diff-changelog`, review các change drop/create/rename/alter. Không thực thi file sinh tự động.
6. Nếu rename thuần túy, viết changeset rename và rollback ngược. Nếu status đổi quy ước, thêm mapping, precondition, backfill và kiểm chứng.
7. Nếu consumer cần thời gian chuyển đổi, thiết kế expand–migrate–contract.
8. Chạy `validate`, `update-sql`, thử trên database lab có dữ liệu đại diện và đối soát số dòng/khóa/giá trị.
9. Thử rollback hoặc forward fix theo thiết kế.

**Tiêu chí hoàn thành:** giải thích được vì sao diff không đủ để kết luận rename; có mapping và bằng chứng nghiệp vụ; generated changelog đã được review; không làm mất dữ liệu hoặc phá consumer.

## 18. Checklist review schema diff

- [ ] Reference là trạng thái mong muốn có nguồn gốc và được phê duyệt.
- [ ] Target là đúng database/schema cần so sánh.
- [ ] DBMS, driver, Liquibase version, schema/catalog và quyền metadata được xác nhận.
- [ ] Diff types và include/exclude scope được ghi rõ; không kết luận về object đã bị loại.
- [ ] Báo cáo missing/unexpected/changed được đọc theo đúng hướng reference → target.
- [ ] Mọi rename candidate có mapping và xác nhận domain, không chỉ dựa vào cấu trúc tương đồng.
- [ ] Generated drop/create được review để tránh xóa dữ liệu khi thực chất cần rename.
- [ ] Semantic change được kiểm tra riêng bằng data query, mapping, đối soát và test consumer.
- [ ] Dependency của FK, index, view, trigger, procedure, grant và ứng dụng đã được xem xét.
- [ ] Changelog cuối cùng dùng changeset identity ổn định, precondition và rollback phù hợp.
- [ ] Có chiến lược expand–migrate–contract nếu thay đổi phá vỡ compatibility.
- [ ] `validate`, `update-sql` và kiểm thử trên DB đại diện đã đạt.
- [ ] Sau triển khai đã kiểm tra schema, dữ liệu, ứng dụng và `DATABASECHANGELOG`.
- [ ] Không dùng diff report làm bằng chứng duy nhất về ý nghĩa nghiệp vụ hoặc chất lượng dữ liệu.

**Kết luận:** Liquibase schema diff hữu ích để phát hiện cấu trúc khác nhau giữa reference và target, nhưng không thể tự biết ý định đổi tên hoặc hiểu ý nghĩa domain của dữ liệu. Hãy dùng `diff` để tìm dấu hiệu, `diff-changelog` để tạo bản nháp, rồi review bằng chứng, viết changeset rename/data migration tường minh và kiểm chứng ứng dụng. Một migration tốt không chỉ làm hai schema giống nhau; nó phải giữ đúng dữ liệu, quan hệ và hợp đồng nghiệp vụ trong suốt quá trình triển khai.

