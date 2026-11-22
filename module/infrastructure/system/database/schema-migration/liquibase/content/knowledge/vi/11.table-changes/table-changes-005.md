# Thay đổi kiểu dữ liệu và kiểm tra tính tương thích

## 1. Vì sao thay đổi kiểu dữ liệu là một migration có rủi ro?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu thông qua changelog, changeset, precondition, checksum và lịch sử triển khai. Việc thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD đặc biệt quan trọng khi thay đổi kiểu dữ liệu của một cột đã có bản ghi.

Ví dụ, bảng `billing_invoice` đang lưu số tiền bằng `VARCHAR(32)`. Nhóm phát triển muốn chuyển sang `NUMERIC(14,2)` để tính toán và kiểm soát độ chính xác. Nếu chạy lệnh đổi kiểu trực tiếp mà không kiểm tra, migration có thể gặp giá trị `"N/A"`, ký hiệu tiền tệ, dấu phẩy phân tách hàng nghìn, số có quá nhiều chữ số hoặc dữ liệu bị bỏ trống. Nếu việc đổi kiểu thành công nhưng ứng dụng vẫn ghi chuỗi định dạng cũ, hệ thống có thể lỗi ngay sau khi triển khai.

Bài học thuộc chương **Thay đổi bảng** này trả lời bốn câu hỏi liên quan nhau:

1. Liquibase biểu diễn thao tác đổi kiểu như thế nào?
2. Dữ liệu hiện hữu có thể chuyển đổi chính xác và không mất thông tin hay không?
3. Ứng dụng, ràng buộc và các đối tượng phụ thuộc có còn tương thích không?
4. Làm sao kiểm chứng, triển khai theo giai đoạn và phục hồi khi phát sinh lỗi?

**Ý chính:** `modifyDataType` mô tả thay đổi schema, nhưng không tự đảm bảo dữ liệu sạch, tính tương thích của ứng dụng hoặc khả năng rollback. Quy trình an toàn phải kiểm tra cả cấu trúc và dữ liệu trước khi áp dụng.

## 2. Phân loại thay đổi kiểu dữ liệu theo mức độ rủi ro

Một thay đổi kiểu có thể là mở rộng phạm vi giá trị, thu hẹp phạm vi, chuyển đổi biểu diễn hoặc thay đổi ngữ nghĩa nghiệp vụ.

| Thay đổi | Rủi ro điển hình | Điều cần kiểm tra |
|---|---|---|
| `VARCHAR(100) → VARCHAR(255)` | Thường thấp, nhưng có thể khóa bảng hoặc ảnh hưởng index/DDL tùy DBMS | Giới hạn thực tế, index, lock, phiên bản database |
| `INTEGER → BIGINT` | Thường mở rộng dải giá trị, nhưng có thể thay kiểu trả về và kích thước index | ORM/JDBC, khóa ngoại, index, thao tác DDL |
| `BIGINT → INTEGER` | Tràn số nếu dữ liệu vượt dải 32 bit | `MIN`, `MAX`, ràng buộc, mã ứng dụng |
| `DECIMAL(10,2) → DECIMAL(14,2)` | Tăng precision thường tương đối an toàn, nhưng vẫn cần xét DDL | Tổng chữ số, constraints, thời gian khóa |
| `DECIMAL(14,4) → DECIMAL(14,2)` | Làm tròn hoặc mất hai chữ số thập phân | Scale thực tế, quy tắc làm tròn, đối soát tiền |
| `VARCHAR → INTEGER/NUMERIC` | Chuỗi không hợp lệ, định dạng địa phương, tràn độ chính xác | Regex/parse, khoảng giá trị, NULL, dữ liệu lỗi |
| `TEXT → UUID` | Chuỗi không đúng định dạng UUID | Dữ liệu invalid, chuẩn hóa, phụ thuộc khóa |
| `TIMESTAMP → TIMESTAMP WITH TIME ZONE` | Diễn giải lại thời điểm nếu sai timezone giả định | Timezone nguồn, UTC, dữ liệu mùa giờ, driver |
| `VARCHAR → BOOLEAN` | Ý nghĩa của `"Y"`, `"N"`, `"1"`, `"0"` không thống nhất | Mapping rõ ràng, giá trị ngoài tập, NULL |
| `DATE → TIMESTAMP` | Mất hoặc tự giả định giờ trong ngày | Múi giờ, nghiệp vụ, quy ước mặc định |
| Đổi collation/charset | Thứ tự so sánh, unique và index có thể thay đổi | Dữ liệu Unicode, so sánh chuỗi, ràng buộc unique |

Một kiểu đích rộng hơn **không đồng nghĩa** thay đổi luôn chạy nhanh hoặc không khóa. PostgreSQL, MySQL, SQL Server, Oracle và những hệ quản trị khác có quy tắc chuyển đổi, lock và hỗ trợ DDL khác nhau. Không dùng kết quả trên H2 hoặc một database thử nghiệm khác loại để kết luận về hành vi của production.

### 2.1. Tính tương thích phải xét ở nhiều tầng

| Tầng | Câu hỏi đánh giá |
|---|---|
| Dữ liệu | Tất cả giá trị đang có có chuyển sang kiểu mới mà không lỗi hoặc mất nghĩa không? |
| Schema | Default, NOT NULL, CHECK, UNIQUE, FK, index, generated column, view, procedure có chịu ảnh hưởng không? |
| Database/driver | DBMS có hỗ trợ phép đổi kiểu, câu lệnh CAST, transaction, lock và rollback DDL như dự kiến không? |
| Ứng dụng | Entity/JPA, DTO, validation, serialization, mapping JDBC và các phiên bản ứng dụng đang chạy có hiểu kiểu mới không? |
| Tích hợp | API, ETL, BI, CDC, job nền, báo cáo và các hệ thống đọc dữ liệu có còn xử lý đúng không? |
| Vận hành | Migration có đủ nhanh, có thể chạy lại an toàn, được giám sát và có phương án khôi phục không? |

Đặc biệt, **tương thích schema** và **tương thích triển khai** là hai vấn đề khác nhau. Database có thể chấp nhận kiểu mới, nhưng nhiều instance ứng dụng cũ vẫn hoạt động trong thời gian rolling deployment. Khi đó, đổi kiểu trực tiếp có thể tạo ra cửa sổ không tương thích.

## 3. Liquibase hỗ trợ thay đổi kiểu bằng modifyDataType

Change type `modifyDataType` cho phép mô tả kiểu mới của một cột. Ví dụ mở rộng cột email từ `VARCHAR(160)` sang `VARCHAR(320)`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-widen-customer-email
      author: schema-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer
        - columnExists:
            tableName: customer
            columnName: email
      changes:
        - modifyDataType:
            tableName: customer
            columnName: email
            newDataType: varchar(320)
```

Trong ví dụ này:

- `tableName` và `columnName` chọn cột cần thay đổi.
- `newDataType` chỉ định kiểu đích. Cách biểu diễn kiểu có thể phụ thuộc DBMS.
- Precondition giúp phát hiện thiếu bảng/cột trước khi chạy, nhưng **không xác nhận** mọi ràng buộc và chương trình phụ thuộc đã tương thích.
- Changeset có `id`, `author` và đường dẫn changelog ổn định để Liquibase quản lý lịch sử.

Đây là ví dụ thay đổi theo hướng mở rộng. Nó không chứng minh mọi hệ quản trị đều thực hiện thao tác không cần rewrite bảng hoặc không khóa lâu. Hãy tạo SQL dự kiến bằng `update-sql` trên đúng DBMS và kiểm tra kế hoạch vận hành.

Một cách biểu diễn tương đương bằng XML:

```xml
<changeSet id="20261119-01-widen-customer-email" author="schema-team">
    <modifyDataType tableName="customer"
                    columnName="email"
                    newDataType="varchar(320)"/>
</changeSet>
```

Đoạn XML minh họa phần changeset; khi dùng thực tế, phải đặt nó trong file changelog XML hợp lệ với phần tử `databaseChangeLog` và khai báo namespace thích hợp. Không đưa đồng thời bản XML và YAML có cùng mục đích vào changelog thực thi, vì chúng là hai khai báo có đường dẫn khác nhau và có thể bị coi là hai changeset riêng.

### 3.1. Khi nào không nên dùng modifyDataType trực tiếp?

Với các chuyển đổi cần biểu thức đặc thù, ví dụ `VARCHAR → NUMERIC` trong PostgreSQL đòi hỏi `USING` để chỉ rõ cách parse dữ liệu, `modifyDataType` có thể không sinh được SQL phù hợp. Khi đó có thể dùng `sql` hoặc `sqlFile` được giới hạn bởi `dbms` và có kiểm chứng trước.

`modifyDataType` cũng không tự làm sạch chuỗi `"1,250.50"` thành giá trị số, không tự suy ra timezone đúng và không quyết định chính sách làm tròn. Những quy tắc này phải được thiết kế, kiểm thử và ghi thành thay đổi dữ liệu riêng nếu cần.

## 4. Kiểm tra dữ liệu trước khi quyết định đổi kiểu

Trước khi soạn changeset, cần khảo sát schema và dữ liệu thực tế trên database đại diện cho production. Không dùng dữ liệu mẫu nhỏ làm căn cứ duy nhất.

### 4.1. Xác nhận kiểu và ràng buộc hiện tại

Một truy vấn thông dụng qua `information_schema` để xem thông tin cột (chi tiết có thể khác theo DBMS):

```sql
SELECT column_name,
       data_type,
       character_maximum_length,
       numeric_precision,
       numeric_scale,
       is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'billing_invoice'
ORDER BY ordinal_position;
```

Sau đó kiểm tra thêm:

- Primary key, foreign key, unique, check và index có tham chiếu cột.
- View, stored procedure, trigger, generated column và các báo cáo đọc/ghi cột.
- Mức độ phân vùng, độ lớn bảng, số dòng, tốc độ ghi đồng thời và khả năng lock.
- Driver JDBC, ORM và code mapping của ứng dụng, kể cả bản đang chạy trước khi deploy.

Chỉ xem `information_schema.columns` chưa đủ để xác định tất cả dependency; cần truy vấn catalog riêng của DBMS hoặc dùng công cụ phân tích phụ thuộc phù hợp.

### 4.2. Dùng truy vấn thống kê để phát hiện dữ liệu không tương thích

Giả sử `billing_invoice.amount_text` chứa số tiền dưới dạng chuỗi. Trước khi chuyển sang `NUMERIC(14,2)`, có thể kiểm tra tổng số dòng, NULL, chuỗi rỗng và những chuỗi có định dạng không phù hợp trên PostgreSQL:

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(*) FILTER (WHERE amount_text IS NULL) AS null_rows,
       COUNT(*) FILTER (
           WHERE amount_text IS NOT NULL
             AND btrim(amount_text) = ''
       ) AS blank_rows,
       COUNT(*) FILTER (
           WHERE amount_text IS NOT NULL
             AND btrim(amount_text) !~
                 '^-?[0-9]{1,12}(\.[0-9]{1,2})?$'
       ) AS invalid_rows
FROM billing_invoice;
```

Biểu thức này cố ý chấp nhận một dấu trừ tùy chọn, tối đa 12 chữ số phần nguyên và 1–2 chữ số thập phân, hoặc không có phần thập phân. Đây là **quy tắc minh họa** cho `NUMERIC(14,2)`, không phải bộ parser tiền tệ tổng quát. Nó từ chối dấu cộng, dấu phân cách hàng nghìn, chữ số khoa học và các chuỗi có dấu phẩy; nếu dữ liệu nguồn dùng những định dạng đó thì phải định nghĩa quy tắc chuẩn hóa có kiểm chứng.

Không chỉ kiểm tra dữ liệu “có parse được” mà phải kiểm tra dữ liệu có **giữ đúng ý nghĩa** sau đổi kiểu hay không. Ví dụ `"000123"` có thể là mã định danh cần giữ số 0 ở đầu, không nên đổi thành số nguyên `123`. Với tiền tệ, phải xác nhận đơn vị, số chữ số thập phân và quy tắc làm tròn trước khi thay đổi.

### 4.3. Xác định tiêu chí chặn migration

Một số tiêu chí trước triển khai có thể là:

| Tiêu chí | Yêu cầu ví dụ |
|---|---|
| Dữ liệu không hợp lệ | `invalid_rows = 0` |
| Dữ liệu bắt buộc | Không còn NULL hoặc chuỗi rỗng nếu cột đích sẽ `NOT NULL` |
| Precision/scale | Không có giá trị vượt `NUMERIC(14,2)` hoặc cần làm tròn ngoài ý định |
| Đối soát | Tổng số tiền hoặc tổng số dòng sau chuyển đổi khớp quy tắc được chấp nhận |
| Ứng dụng | Bản cũ và bản mới đều hoạt động trong giai đoạn chuyển tiếp |
| Vận hành | Đã thử migration trên database có dữ liệu và kích thước đại diện |

Precondition giúp **tự động hóa một phần** tiêu chí; kiểm tra nghiệp vụ, hiệu năng và hành vi ứng dụng cần thêm bước xác minh riêng.

## 5. Hai chiến lược: đổi kiểu trực tiếp và mở rộng rồi thu hẹp

### 5.1. Đổi kiểu trực tiếp

Cách này thay kiểu của chính cột đang có. Thích hợp hơn khi thay đổi được kiểm chứng là tương thích, số lượng dữ liệu cho phép, có cửa sổ bảo trì hoặc DBMS hỗ trợ thao tác phù hợp.

```text
customer.email VARCHAR(160)
         |
         | modifyDataType
         v
customer.email VARCHAR(320)
```

Ưu điểm: changelog ngắn, ít bước phối hợp với ứng dụng. Rủi ro: lock, rewrite, lỗi CAST, phụ thuộc schema và ứng dụng phiên bản cũ.

### 5.2. Expand–migrate–contract

Khi đổi ngữ nghĩa dữ liệu hoặc hỗ trợ rolling deployment, một chiến lược dễ kiểm soát hơn là:

```text
Giai đoạn 1 — EXPAND
  thêm cột mới, giữ nguyên cột cũ
            |
            v
Giai đoạn 2 — MIGRATE
  ứng dụng dual-write/dual-read + backfill có kiểm chứng
            |
            v
Giai đoạn 3 — VERIFY
  đối soát, theo dõi và xác nhận các phiên bản ứng dụng
            |
            v
Giai đoạn 4 — CONTRACT
  dừng dùng cột cũ, thêm constraint mới, xóa cột cũ về sau
```

Ưu điểm: cho phép ứng dụng chuyển tiếp có kiểm soát và giảm rủi ro phải sửa kiểu trực tiếp trên một bảng lớn. Đổi lại cần thêm code ứng dụng, thời gian duy trì hai biểu diễn và phương án đồng bộ dữ liệu.

**Không dùng một changeset lớn để làm tất cả các giai đoạn** nếu ứng dụng cần được triển khai giữa các bước. Mỗi lần deploy cần có một trạng thái trung gian hợp lệ, có thể vận hành trước khi bước tiếp theo diễn ra.

## 6. Ví dụ đầy đủ: chuyển chuỗi số tiền sang NUMERIC(14,2)

Giả sử hệ thống có bảng:

```text
billing_invoice
├── id              BIGINT PRIMARY KEY
└── amount_text     VARCHAR(32)
```

Ứng dụng hiện có dùng `amount_text`, nhưng chức năng thanh toán mới cần `amount_decimal NUMERIC(14,2)` để tính toán. Ví dụ dưới đây áp dụng cho PostgreSQL. Các bước được tách để biểu diễn giai đoạn migration; khi triển khai thực tế, cần chọn thời điểm tương ứng với việc nâng cấp ứng dụng.

### 6.1. Bước 1: Thêm cột mới, cho phép NULL trong giai đoạn chuyển tiếp

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-10-add-amount-decimal
      author: schema-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: billing_invoice
        - columnExists:
            tableName: billing_invoice
            columnName: amount_text
      changes:
        - addColumn:
            tableName: billing_invoice
            columns:
              - column:
                  name: amount_decimal
                  type: numeric(14,2)
      rollback:
        - dropColumn:
            tableName: billing_invoice
            columnName: amount_decimal
```

Việc thêm cột cho phép NULL giúp bản ứng dụng cũ tiếp tục hoạt động khi nó chưa biết cột mới. Rollback `dropColumn` chỉ phù hợp **trước khi** cột mới trở thành nguồn dữ liệu cần bảo toàn và trước khi code ứng dụng phụ thuộc vào cột đó. Nếu ứng dụng mới đã ghi dữ liệu chỉ có ở cột mới, xóa cột sẽ làm mất dữ liệu.

Với PostgreSQL, nếu tên bảng hoặc cột nằm trong schema khác `public`, phải cấu hình `schemaName` hoặc search path tương ứng thay vì ngầm giả định default schema.

### 6.2. Bước 2: Kiểm tra dữ liệu trước khi backfill

Dùng precondition `sqlCheck` để chặn giá trị không thể chuyển đúng quy tắc đã chọn:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-11-backfill-amount-decimal
      author: schema-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM billing_invoice
              WHERE amount_text IS NOT NULL
                AND btrim(amount_text) !~
                    '^-?[0-9]{1,12}(\.[0-9]{1,2})?$'
      changes:
        - sql:
            sql: |
              UPDATE billing_invoice
              SET amount_decimal =
                  btrim(amount_text)::numeric(14,2)
              WHERE amount_text IS NOT NULL
                AND amount_decimal IS NULL;
```

Những điểm cần đọc kỹ:

- `dbms: postgresql` giới hạn changeset vì `!~`, `btrim` và cú pháp `::numeric` là cú pháp PostgreSQL.
- `sqlCheck` yêu cầu kết quả truy vấn đúng `"0"`, nghĩa là không có giá trị khác NULL bị quy tắc từ chối tại thời điểm kiểm tra.
- Điều kiện `amount_decimal IS NULL` giúp thao tác backfill **không ghi đè** giá trị đã có trong cột mới. Tuy nhiên, nếu nguồn thay đổi sau backfill, điều kiện này không tự đồng bộ lại; cần cơ chế dual-write hoặc quy trình bù.
- Các chuỗi NULL không được chuyển thành số; nếu nghiệp vụ yêu cầu mọi hóa đơn có số tiền, cần xử lý NULL và ràng buộc `NOT NULL` sau.
- Dữ liệu thực tế có thể thay đổi giữa thời điểm precondition và khi UPDATE chạy, tùy isolation và ghi đồng thời. Không xem precondition như cơ chế khóa toàn bộ nguồn dữ liệu.

**Cảnh báo về hiệu năng:** UPDATE toàn bảng có thể tạo transaction lớn, lock, WAL/redo và áp lực I/O. Với bảng nhiều triệu dòng, nên thiết kế backfill theo lô được giám sát, có checkpoint và đối soát từng đợt. Không tùy tiện chia một changeset thành nhiều thao tác ngoài transaction khi chưa xác định khả năng tiếp tục sau lỗi.

### 6.3. Bước 3: Phối hợp ứng dụng trong thời gian có hai cột

Một tiến trình deploy nhiều phiên bản có thể đi qua các trạng thái:

| Trạng thái | Ứng dụng đọc | Ứng dụng ghi | Điều kiện chuyển tiếp |
|---|---|---|---|
| Cũ | `amount_text` | `amount_text` | Chưa cần cột mới |
| Tương thích chuyển tiếp | Ưu tiên dữ liệu đã được kiểm chứng; có fallback được định nghĩa | Cả `amount_text` và `amount_decimal` | Ghi hai cột phải nhất quán trong cùng giao dịch nghiệp vụ |
| Sau backfill | `amount_decimal` | `amount_decimal`, đồng thời duy trì cột cũ nếu còn consumer cũ | Đối soát thành công; không còn instance cũ cần biểu diễn cũ |
| Sau contract | Chỉ `amount_decimal` | Chỉ `amount_decimal` | Đã ngừng phụ thuộc và loại bỏ cột cũ |

“Dual-write” có thể gây sai lệch nếu một lần ghi thành công ở một cột mà thất bại ở cột còn lại. Nếu hai cột nằm trong cùng bản ghi của một database, ưu tiên cập nhật trong cùng transaction nghiệp vụ. Với dữ liệu đồng bộ liên hệ thống, cần thêm chiến lược retry/idempotency và đối soát.

Không tự cho phép đọc fallback sang chuỗi cũ vô thời hạn. Hãy đặt mốc kết thúc và điều kiện hậu kiểm, nếu không hệ thống sẽ tích lũy hai nguồn sự thật.

### 6.4. Bước 4: Kiểm chứng dữ liệu sau backfill

Một truy vấn cơ bản:

```sql
SELECT COUNT(*) AS not_backfilled
FROM billing_invoice
WHERE amount_text IS NOT NULL
  AND amount_decimal IS NULL;
```

Kỳ vọng `not_backfilled = 0`, nhưng như vậy chưa đủ để chứng minh **giá trị đúng**. Với quy tắc chuyển đổi đã chọn, có thể đối chiếu những dòng vẫn giữ nguồn text hợp lệ:

```sql
SELECT COUNT(*) AS mismatch_count
FROM billing_invoice
WHERE amount_text IS NOT NULL
  AND btrim(amount_text) ~
      '^-?[0-9]{1,12}(\.[0-9]{1,2})?$'
  AND amount_decimal IS DISTINCT FROM
      btrim(amount_text)::numeric(14,2);
```

Kỳ vọng `mismatch_count = 0` ở thời điểm snapshot kiểm tra. Truy vấn này có thể tốn tài nguyên trên bảng lớn; cần thử trên staging và cân nhắc kiểm tra theo lô. Với dữ liệu đang thay đổi đồng thời, phải chọn thời điểm hoặc cơ chế snapshot nhất quán để kết quả đối soát có ý nghĩa.

Nếu phép chuyển đổi có quy tắc làm tròn hoặc chuẩn hóa phức tạp, đối soát phải theo **quy tắc nghiệp vụ đã công bố**, không chỉ so sánh lại bằng một phép CAST có thể che giấu lỗi gốc.

### 6.5. Bước 5: Siết ràng buộc ở thời điểm phù hợp

Sau khi ứng dụng đã ghi đầy đủ `amount_decimal` và nghiệp vụ xác nhận cột bắt buộc có giá trị, có thể thêm ràng buộc `NOT NULL` trong changeset riêng:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-12-require-amount-decimal
      author: schema-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM billing_invoice
              WHERE amount_decimal IS NULL
      changes:
        - addNotNullConstraint:
            tableName: billing_invoice
            columnName: amount_decimal
            columnDataType: numeric(14,2)
      rollback:
        - dropNotNullConstraint:
            tableName: billing_invoice
            columnName: amount_decimal
            columnDataType: numeric(14,2)
```

`onFail: HALT` yêu cầu dừng nếu còn NULL. Trường hợp cần hỗ trợ nhiều DBMS, phải kiểm tra khả năng hỗ trợ và cú pháp ràng buộc của từng database. Precondition không thể bảo đảm dữ liệu không thay đổi ngay sau khi nó chạy; kế hoạch triển khai phải kiểm soát writer và thời điểm áp dụng constraint.

### 6.6. Bước 6: Xóa cột cũ sau khi đã hết phụ thuộc

Chỉ ở lần phát hành sau, khi không còn ứng dụng, ETL, API hay báo cáo sử dụng `amount_text`, mới cân nhắc:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-13-drop-legacy-amount-text
      author: schema-team
      changes:
        - dropColumn:
            tableName: billing_invoice
            columnName: amount_text
```

Đây là bước **contract**, thường khó hoàn tác an toàn vì xóa cột làm mất dữ liệu biểu diễn cũ. Cần có backup, thời gian lưu dữ liệu chuyển tiếp, phê duyệt phát hành và phương án phục hồi riêng. Không mặc định rollback `addColumn amount_text` có thể khôi phục lại các giá trị ban đầu.

## 7. Khi bắt buộc chuyển trực tiếp bằng SQL riêng của PostgreSQL

Có những trường hợp hệ thống chấp nhận cửa sổ bảo trì, dữ liệu nhỏ hoặc ứng dụng được nâng cấp đồng bộ, nên thay trực tiếp cột `amount_text` thành `NUMERIC(14,2)`. PostgreSQL có thể yêu cầu biểu thức `USING` để chuyển nội dung text sang số.

Ví dụ **phương án thay thế** cho quy trình expand–contract ở phần 6; không chạy cả hai phương án lên cùng schema:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-direct-convert-amount
      author: schema-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM billing_invoice
              WHERE amount_text IS NOT NULL
                AND btrim(amount_text) !~
                    '^-?[0-9]{1,12}(\.[0-9]{1,2})?$'
      changes:
        - sql:
            sql: |
              ALTER TABLE billing_invoice
              ALTER COLUMN amount_text TYPE numeric(14,2)
              USING btrim(amount_text)::numeric(14,2);
```

Lệnh này giữ tên cột `amount_text` nhưng đổi kiểu của nó. Trước khi chạy cần kiểm tra default hiện tại, index, constraint và các đối tượng phụ thuộc; một default dạng chuỗi không thể tự chuyển phù hợp có thể khiến ALTER thất bại và cần xử lý trong migration được thiết kế riêng.

Ngoài ra, việc `ALTER COLUMN TYPE` có thể rewrite bảng và giữ lock mạnh trong một khoảng thời gian đáng kể tùy loại chuyển đổi. Cần kiểm thử với kích thước dữ liệu và mức đồng thời gần production, có kế hoạch gián đoạn và giám sát lock. Không dùng sự thành công của `validate` để kết luận rằng lệnh ALTER sẽ hoàn thành trong thời gian chấp nhận được.

## 8. Những trường hợp tương thích dễ bị đánh giá sai

### 8.1. Thu hẹp VARCHAR hoặc thay collation

Chuyển `VARCHAR(320)` về `VARCHAR(160)` đòi hỏi kiểm tra độ dài:

```sql
SELECT COUNT(*) AS too_long_rows
FROM customer
WHERE email IS NOT NULL
  AND char_length(email) > 160;
```

Nếu `too_long_rows > 0`, không áp dụng thay đổi thu hẹp trước khi có chính sách xử lý dữ liệu. Truncation tự động có thể làm mất thông tin hoặc tạo giá trị trùng dẫn đến lỗi UNIQUE. Một số hệ quản trị đo độ dài theo ký tự, số khác có giới hạn theo byte hoặc quy ước kiểu; cần kiểm tra dữ liệu Unicode và collation thật.

### 8.2. INTEGER và BIGINT

Mở rộng `INTEGER → BIGINT` thường bảo toàn giá trị số, nhưng JPA entity kiểu `Integer`, JSON contract hoặc cột khóa ngoại tham chiếu có thể không còn tương thích. Khi thu hẹp, cần xác minh dải dữ liệu cho phép:

```sql
SELECT MIN(external_id) AS min_id,
       MAX(external_id) AS max_id
FROM customer;
```

Dải `INTEGER` có dấu thông dụng là từ `-2147483648` đến `2147483647`, nhưng cần đối chiếu loại số cụ thể của DBMS và ứng dụng. Nếu mã định danh vượt dải, không thể thu hẹp mà không mất thông tin.

### 8.3. DECIMAL, NUMERIC và FLOAT

`NUMERIC(p,s)` biểu diễn tổng số chữ số `p`, trong đó `s` chữ số ở phần thập phân. Chuyển `NUMERIC(12,4)` sang `NUMERIC(12,2)` có thể làm tròn giá trị, trong khi chuyển từ `NUMERIC(12,2)` sang `NUMERIC(14,2)` cho phép phạm vi lớn hơn. Tránh dùng `FLOAT` để lưu số tiền cần đối soát chính xác theo đơn vị nhỏ nhất nếu nghiệp vụ yêu cầu số thập phân chính xác.

Đánh giá không chỉ `MAX` và `MIN` mà cả số chữ số trước dấu thập phân, scale và tổng sau chuyển đổi. Với tính toán tiền, quy tắc làm tròn phải được phê duyệt và kiểm thử bằng dữ liệu biên.

### 8.4. TIMESTAMP và timezone

Khi chuyển từ timestamp không timezone sang timestamp có timezone, phải xác định dữ liệu cũ được hiểu theo timezone nào. Nếu dữ liệu lưu giờ địa phương nhưng bị coi là UTC, các thời điểm có thể lệch hàng giờ.

Trong PostgreSQL, biểu thức `AT TIME ZONE` có thể được dùng trong câu lệnh chuyển đổi phù hợp, nhưng trước hết phải chứng minh giả định timezone từ dữ liệu và thiết kế ứng dụng. Cần kiểm tra thời điểm chuyển mùa giờ ở các vùng có DST, cách JDBC/ORM map `LocalDateTime` và `Instant`, cũng như định dạng API. Chuyển kiểu cú pháp thành công không có nghĩa thời gian nghiệp vụ được giữ nguyên.

### 8.5. Enum, boolean, UUID và JSON

Chuỗi `"yes"`, `"true"`, `"1"` có thể mang ý nghĩa boolean nhưng không nhất thiết được DBMS parse giống nhau. Chuỗi UUID cần được chuẩn hóa và kiểm tra tính hợp lệ. Với JSON, nên xem xét schema của tài liệu, giá trị thiếu và các consumer, thay vì chỉ kiểm tra CAST. Nếu định dạng đã là JSON text nhưng ứng dụng cần JSONB trên PostgreSQL, hành vi so sánh, index và thứ tự biểu diễn có thể thay đổi.

## 9. Quan hệ với constraint, index và đối tượng phụ thuộc

Đổi kiểu một cột không tách rời các đối tượng dùng cột đó. Trước migration nên tạo danh sách phụ thuộc:

- **Primary key và foreign key:** hai cột tham chiếu phải dùng kiểu tương thích theo DBMS; có thể cần đổi theo thứ tự và tạm điều chỉnh ràng buộc.
- **Unique, index và expression index:** thay đổi kiểu có thể ảnh hưởng kích thước, cách so sánh, collation hoặc yêu cầu rebuild index.
- **Default và check constraint:** biểu thức mặc định hay điều kiện so sánh của kiểu cũ có thể không còn hợp lệ.
- **View, trigger, function, stored procedure:** lời gọi CAST hoặc chữ ký tham số có thể bị ảnh hưởng.
- **Partitioning và generated column:** khóa phân vùng hay biểu thức sinh từ cột có thể giới hạn cách ALTER.
- **Ứng dụng:** validation và converter, bộ nhớ đệm, dữ liệu sự kiện, hợp đồng API có thể phụ thuộc kiểu cũ.

Không đặt mục tiêu “lệnh chạy thành công” làm tiêu chí duy nhất. Ví dụ cột `price` đã đổi sang numeric nhưng API vẫn xuất chuỗi theo định dạng tiền tệ cũ có thể làm hỏng client; cần xác định rõ hợp đồng API có đổi hay vẫn giữ tương thích.

## 10. Precondition, validate và update-sql: mỗi công cụ giải quyết điều gì?

| Công cụ | Kiểm tra được | Không tự bảo đảm |
|---|---|---|
| `liquibase validate` | Cấu trúc/khai báo changelog có hợp lệ theo Liquibase hay không | Dữ liệu có parse được, SQL có đủ nhanh, app có tương thích |
| `sqlCheck`/precondition | Một điều kiện SQL hoặc trạng thái schema tại thời điểm đánh giá | Không ngăn được mọi thay đổi đồng thời, không thay thế kiểm thử ứng dụng |
| `liquibase status --verbose` | Những changeset đang chờ theo lịch sử và bộ lọc hiện hành | Kết quả nghiệp vụ sau khi chạy |
| `liquibase update-sql` | SQL Liquibase dự kiến tạo ra cho DBMS/cấu hình tương ứng | Thời gian khóa, lỗi dữ liệu tại runtime, độ an toàn rollback |
| `liquibase update` | Thực thi migration và ghi lịch sử nếu thành công theo cơ chế Liquibase | Không tự bảo đảm không có mất mát thông tin hay lỗi ứng dụng sau deploy |
| Kiểm thử trên bản sao dữ liệu | Khả năng CAST, hiệu năng và bất biến nghiệp vụ trong điều kiện gần thực tế | Không thay thế giám sát khi production có ghi đồng thời |

Các lệnh minh họa sau cần có cấu hình kết nối và root changelog phù hợp:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
```

Nên chạy `validate`, `status` và `update-sql` trước, review SQL và chỉ thực hiện `update` bằng **cùng root changelog, phiên bản Liquibase, DBMS, database URL, context và label** đã dùng để kiểm tra. Đặc biệt với chuyển kiểu dữ liệu, cần chạy migration thực tế trên database thử nghiệm có dữ liệu đại diện, vì `update-sql` không thực hiện CAST trên những bản ghi đang tồn tại.

### 10.1. Lưu ý với checksum và lịch sử

Liquibase nhận diện một changeset bằng `id`, `author` và đường dẫn logic changelog, đồng thời lưu checksum và trạng thái triển khai trong `DATABASECHANGELOG`. Khi một changeset đã áp dụng trên môi trường dùng chung, không sửa `modifyDataType` cũ từ `varchar(160)` thành `varchar(320)` để “cập nhật” migration. Việc đó có thể gây lỗi checksum và tạo ra lịch sử khác nhau giữa các môi trường.

Muốn đổi kiểu thêm một lần, hãy tạo **changeset mới** với danh tính mới. Không dùng `clearCheckSums` hoặc sửa trực tiếp `DATABASECHANGELOG` để bỏ qua một vấn đề chuyển kiểu chưa được phân tích. Nếu di chuyển file changelog, phải kiểm tra `FILENAME` trong lịch sử và cân nhắc `logicalFilePath` phù hợp để giữ danh tính.

## 11. Rollback: đổi kiểu về cũ không chắc khôi phục được dữ liệu cũ

Giả sử cột đã được mở rộng từ `VARCHAR(160)` sang `VARCHAR(320)` và ứng dụng mới đã ghi email dài 250 ký tự. Thao tác rollback bằng cách `modifyDataType` về `VARCHAR(160)` có thể thất bại hoặc gây mất dữ liệu tùy DBMS. Tương tự, sau khi `VARCHAR` đã chuyển sang `NUMERIC`, các số 0 đứng đầu, chuỗi rỗng hoặc định dạng ban đầu có thể không còn khôi phục được từ kiểu số.

Vì vậy, cần phân biệt:

1. **Rollback cấu trúc:** khôi phục cột, kiểu và constraint như trước.
2. **Rollback dữ liệu:** khôi phục đúng giá trị ban đầu, không chỉ một giá trị có thể CAST ngược.
3. **Rollback ứng dụng:** phiên bản trước có đọc/ghi được schema hiện tại không?
4. **Phục hồi vận hành:** dùng backup, snapshot, point-in-time recovery hoặc migration bù phù hợp khi rollback tự động không đủ.

Với mở rộng rồi thu hẹp, có thể trì hoãn xóa cột cũ để giữ khả năng quay về trong giai đoạn đầu. Sau khi xóa cột cũ, rollback dữ liệu có thể cần bản sao lưu hoặc quá trình khôi phục tốn thời gian. Khi dữ liệu trong hai cột không còn đồng bộ, giữ lại cột cũ cũng **không tự bảo đảm** rollback an toàn.

Ví dụ một change thu hẹp chỉ nên được phép khi đã kiểm tra các giá trị dài hơn giới hạn đích; một rollback tự động thu hẹp mà thiếu guard là phương án không phù hợp. Liquibase có thể tự tạo SQL rollback cho một số change type, nhưng không nên giả định `modifyDataType` sẽ luôn có rollback tự động an toàn trên mọi DBMS. Hãy thiết kế và thử `rollback-sql` hoặc phương án phục hồi riêng trong môi trường thử nghiệm.

## 12. Tích hợp Spring Boot và CI/CD

### 12.1. Spring Boot: schema và entity cần chuyển cùng một kế hoạch

Trong Spring Boot, Liquibase thường đọc root changelog từ classpath:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Một thay đổi `INTEGER → BIGINT` có thể buộc cập nhật Java entity từ `Integer` sang `Long`, method repository, DTO, JSON serializer và các phép kiểm tra dữ liệu. Thay đổi `VARCHAR amount → NUMERIC` có thể yêu cầu mapping sang `BigDecimal` thay vì `String`. Đừng đổi cả schema và code trong một deployment nếu các instance cũ vẫn có thể sống đồng thời và không còn tương thích.

Với chiến lược expand–contract, phiên bản ứng dụng chuyển tiếp nên đọc/ghi được cả hai biểu diễn hoặc có cơ chế đồng bộ có kiểm chứng. Khi tất cả instance đã dùng kiểu mới, có thể áp dụng constraint và sau đó loại bỏ cột cũ ở release riêng.

### 12.2. CI/CD: cổng kiểm chứng trước khi migration

Một pipeline triển khai thay đổi kiểu dữ liệu có thể gồm:

1. Review thay đổi changelog và tính bất biến của changeset đã triển khai.
2. Kiểm tra cú pháp changelog bằng `validate`.
3. Xác nhận root changelog, kết nối, schema và bộ lọc môi trường.
4. Dùng `status --verbose` để xác định các changeset pending.
5. Sinh SQL bằng `update-sql` và xem liệu lệnh có thể rewrite/lock bảng.
6. Chạy kiểm thử migration trên database có dữ liệu thật đã ẩn danh hoặc bản sao phù hợp; đo thời gian, lock và đối soát.
7. Xác minh ứng dụng cũ và mới tương thích với trạng thái schema chuyển tiếp.
8. Thực hiện migration production trong cửa sổ hoặc quy trình triển khai đã chọn.
9. Hậu kiểm cột, ràng buộc, dữ liệu, log ứng dụng và `DATABASECHANGELOG`.
10. Chỉ tiến hành bước contract sau khi đã hết các phụ thuộc vào kiểu/cột cũ.

Ở hệ thống nhiều replica, để một job migration riêng cập nhật schema thường giúp thời điểm thực thi rõ ràng hơn so với việc từng instance Spring Boot tự chạy khi khởi động. `DATABASECHANGELOGLOCK` giúp điều phối migration đồng thời, nhưng không tự sửa được vấn đề tương thích giữa ứng dụng và schema.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xác minh và xử lý |
|---|---|---|
| `modifyDataType` báo không thể CAST | Có dữ liệu nguồn không parse được hoặc DBMS cần biểu thức `USING` | Kiểm tra dữ liệu, xây quy tắc chuyển đổi, dùng SQL DBMS-specific có guard khi cần |
| Lỗi tràn precision hoặc scale | Giá trị vượt `NUMERIC(p,s)`, quy tắc làm tròn không phù hợp | Kiểm tra độ dài phần nguyên và thập phân, đối soát số tiền |
| Migration thành công nhưng ứng dụng lỗi | Entity/JDBC/API còn giả định kiểu cũ | Kiểm tra mapping, serialization, các phiên bản app và consumer |
| ALTER chạy lâu hoặc gây timeout | Table rewrite, lock, index/constraint rebuild, ghi đồng thời | Kiểm tra SQL thực tế, thử trên dữ liệu đại diện, điều chỉnh chiến lược |
| Không thể đổi kiểu vì constraint/default | Index, FK, check, view hoặc default không tương thích | Liệt kê dependency, tách changeset điều chỉnh theo thứ tự |
| Rollback không đưa dữ liệu về trạng thái cũ | Chuyển đổi đã làm mất biểu diễn hoặc xóa cột cũ | Dùng bản sao lưu/migration bù được thiết kế, không tin vào CAST ngược |
| Staging chạy được nhưng production thất bại | Khác dữ liệu, phiên bản DBMS, lock, schema, lịch sử hoặc context | So sánh môi trường và bản sao có dữ liệu đại diện |
| Checksum không khớp sau sửa changelog | Changeset đã chạy bị chỉnh nội dung | Khôi phục lịch sử bất biến và tạo changeset mới |
| `NOT NULL` thất bại | Backfill chưa đủ hoặc writer còn tạo NULL | Đối soát và chuyển writer trước khi thêm constraint |
| Dữ liệu hai cột lệch nhau | Dual-write thiếu transaction, backfill một lần trong lúc nguồn còn ghi | Thiết kế đồng bộ, kiểm tra snapshot và sửa lệch trước cutover |

Không xử lý lỗi bằng cách tắt precondition, đánh dấu `MARK_RAN` hoặc xóa dòng lịch sử chỉ để pipeline thành công. Những thao tác này có thể khiến Liquibase báo đã triển khai trong khi schema và dữ liệu thực tế chưa đạt trạng thái mong muốn.

## 14. Bài tập thực hành

**Đề bài:** bảng `customer_profile` có cột `loyalty_points VARCHAR(24)`, chứa các chuỗi số nguyên không âm, nhưng có thể tồn tại giá trị `"N/A"` hoặc chuỗi rỗng. Ứng dụng muốn dùng `BIGINT`.

Hãy thiết kế migration với các yêu cầu:

1. Truy vấn thống kê số lượng NULL, chuỗi rỗng, chuỗi không phải số nguyên không âm và giá trị vượt dải `BIGINT` của DBMS đích.
2. Đề xuất quy tắc xử lý `"N/A"`: NULL, giá trị mặc định hay lỗi nghiệp vụ. Không tự chọn giá trị `0` nếu nó có nghĩa “không có điểm”.
3. Xác định có thể đổi kiểu trực tiếp bằng `modifyDataType` hay cần thêm cột `loyalty_points_bigint` để chuyển theo giai đoạn.
4. Dùng precondition để chặn dữ liệu chưa đạt điều kiện, đồng thời viết truy vấn kiểm chứng sau backfill.
5. Mô tả cách ứng dụng dual-write và khi nào được thêm NOT NULL hoặc xóa cột cũ.
6. Nêu hai rủi ro rollback và cách chuẩn bị backup/phục hồi.
7. Chạy trên database thử nghiệm bằng chuỗi `validate → status → update-sql → update`, rồi đối chiếu lịch sử và dữ liệu.

**Tiêu chí hoàn thành:** migration không làm mất thông tin ngoài quy tắc nghiệp vụ đã chấp nhận, không chạy nhầm trên DBMS khác, tương thích qua giai đoạn triển khai và có bằng chứng kiểm chứng trước/sau.

## 15. Checklist trước khi merge và deploy

- [ ] Đã phân loại phép đổi kiểu: mở rộng, thu hẹp, chuyển biểu diễn hay đổi ngữ nghĩa.
- [ ] Đã khảo sát kiểu hiện tại, constraints, index, default, view, trigger và phụ thuộc.
- [ ] Đã kiểm tra toàn bộ giá trị nguồn với quy tắc parse, precision/scale, NULL và dữ liệu biên.
- [ ] Đã xác định hành vi chuyển đổi theo đúng DBMS/phiên bản sản xuất.
- [ ] Có quyết định rõ giữa đổi trực tiếp và expand–migrate–contract.
- [ ] Nếu dùng `modifyDataType`, đã xem SQL sinh ra và mức ảnh hưởng lock/rewrite.
- [ ] Nếu dùng SQL đặc thù, có giới hạn `dbms` và precondition phù hợp.
- [ ] Ứng dụng/ORM/API và các consumer dữ liệu đã được xem xét để bảo đảm tương thích.
- [ ] Backfill có chiến lược theo lô khi cần và có đối soát dữ liệu.
- [ ] Ràng buộc `NOT NULL`/UNIQUE/FK được thêm khi dữ liệu và writer đã đáp ứng.
- [ ] Changeset đã triển khai vẫn bất biến; thay đổi mới dùng changeset mới.
- [ ] `validate`, `status --verbose` và `update-sql` được kiểm tra với cùng cấu hình deploy.
- [ ] Đã thử migration trên database đại diện, theo dõi thời gian, lock và lỗi CAST.
- [ ] Rollback hoặc phục hồi dữ liệu có phương án thực tế, đã đánh giá những thông tin có thể mất.
- [ ] Bước xóa cột cũ chỉ diễn ra sau khi mọi ứng dụng và hệ thống phụ thuộc đã ngừng sử dụng.
- [ ] Có hậu kiểm schema, dữ liệu, trạng thái ứng dụng và `DATABASECHANGELOG` sau triển khai.

Thay đổi kiểu dữ liệu an toàn không dừng ở việc thay một thuộc tính `newDataType` trong changelog. Liquibase giúp quản lý thứ tự, điều kiện, lịch sử và khả năng kiểm chứng migration; người thiết kế vẫn phải bảo đảm giá trị dữ liệu được diễn giải đúng, chương trình tương thích ở từng giai đoạn và mọi bước phục hồi đều có cơ sở thực tế. Khi rủi ro cao, tách bước mở rộng, chuyển dữ liệu có đối soát và thu hẹp về sau sẽ giúp việc triển khai kiểm soát được hơn.

