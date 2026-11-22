# Tạo và thay thế view

## 1. Vì sao view cần được quản lý như một migration?

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Bên cạnh tạo bảng và sửa cột, một dự án còn phải duy trì **view** — đối tượng SQL trình bày kết quả của một truy vấn dưới một tên có thể sử dụng lại. Việc tạo và thay thế view cũng cần có thứ tự thực thi, kiểm chứng, khả năng rollback và chính sách triển khai nhất quán giữa các môi trường, Spring Boot hoặc CI/CD.

Giả sử ứng dụng có hai bảng `customer_account` và `billing_invoice`. Thay vì để mỗi API và báo cáo tự viết câu lệnh JOIN, nhóm xây dựng view `v_customer_invoice_summary` để cung cấp số hóa đơn và tổng tiền đã thanh toán theo khách hàng. Khi nghiệp vụ thay đổi, định nghĩa view có thể phải được cập nhật. Việc sửa thủ công view trên production sẽ khiến môi trường và lịch sử triển khai lệch nhau; thay vào đó, phải biểu diễn định nghĩa bằng migration có phiên bản và kiểm chứng được.

Bài này giải thích cách dùng `createView`, `replaceIfExists` và `runOnChange`, khi nào nên tạo changeset mới, cách kiểm soát phụ thuộc và quyền truy cập, cũng như giới hạn của rollback khi view đã được nhiều thành phần sử dụng.

**Kết quả mong đợi:** sau bài học, bạn có thể tổ chức changelog tạo view, cập nhật định nghĩa an toàn, giải thích vì sao `CREATE OR REPLACE VIEW` không tương đương với `DROP VIEW` rồi `CREATE VIEW`, và chọn quy trình triển khai phù hợp.

## 2. Bản chất của view và những giới hạn cần biết

Một **view thông thường** là đối tượng được định nghĩa từ một truy vấn SQL. Nó cho phép ứng dụng truy vấn như một bảng:

```sql
SELECT customer_id, invoice_count, paid_total
FROM v_customer_invoice_summary
WHERE customer_id = 1001;
```

Trong nhiều DBMS, view thường không lưu riêng toàn bộ dòng kết quả như một bảng vật lý; hệ quản trị kết hợp định nghĩa của nó vào quá trình thực thi truy vấn. Điều này có một số hệ quả:

- Thay đổi bảng nguồn có thể làm view không còn hợp lệ hoặc khiến kết quả khác ý định.
- Hiệu năng chủ yếu phụ thuộc truy vấn nguồn, index, thống kê và optimizer, chứ không chỉ tên view.
- View tạo ranh giới truy cập thuận tiện, nhưng quyền `SELECT` trên view **không tự đảm bảo** an toàn dữ liệu hoặc chặn mọi cách truy cập bảng nền. Cần kiểm soát quyền, chính sách và hành vi bảo mật theo DBMS.
- Kiểu và tên cột đầu ra của view trở thành một **hợp đồng dữ liệu** mà ứng dụng, JDBC/JPA, báo cáo hoặc hệ thống downstream có thể phụ thuộc.

**Không nhầm view thông thường với materialized view.** Materialized view lưu kết quả theo cơ chế riêng và có quy tắc refresh, lưu trữ, index khác nhau. `createView` dành cho view thông thường; khi cần materialized view phải xem change type/câu SQL hỗ trợ riêng của DBMS và phiên bản Liquibase, không giả định chỉ đổi tên là tương đương.

### 2.1. Khi nào nên dùng view?

| Trường hợp | Lợi ích | Điều phải cân nhắc |
|---|---|---|
| Chuẩn hóa JOIN/aggregation dùng ở nhiều nơi | Tránh sao chép logic truy vấn | Truy vấn phức tạp có thể tăng tải |
| Ổn định hợp đồng đọc khi schema nền thay đổi | Che bớt thay đổi cấu trúc nội bộ | Cột đầu ra vẫn cần tương thích với consumer |
| Cấp quyền đọc tập cột được kiểm soát | Giúp tập trung điểm truy cập | Phải xét quyền DBMS và dữ liệu nhạy cảm |
| Hỗ trợ báo cáo/BI | Tên và biểu diễn dữ liệu nhất quán | Thống kê, index, tải đồng thời |
| Cầu nối khi đổi tên bảng/cột | Hỗ trợ chuyển tiếp bản ứng dụng | Cần kế hoạch bỏ hợp đồng cũ về sau |

Một view không phải giải pháp mặc định cho mọi truy vấn. Nếu logic rất riêng của một API, khó tối ưu hoặc thay đổi quá thường xuyên, cần cân nhắc triển khai ở lớp ứng dụng. Nếu truy vấn tốn thời gian và dữ liệu cho phép đọc theo snapshot, có thể đánh giá materialized view — một bài toán triển khai khác.

## 3. Tạo view trực tiếp bằng SQL để hiểu mục tiêu

Giả sử schema nguồn có:

```text
customer_account
  id             BIGINT PRIMARY KEY
  email          VARCHAR(320)

billing_invoice
  id             BIGINT PRIMARY KEY
  customer_id    BIGINT
  status         VARCHAR(20)
  amount_decimal NUMERIC(14,2)
```

View tổng hợp:

```sql
CREATE VIEW v_customer_invoice_summary AS
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    COUNT(i.id) AS invoice_count,
    COALESCE(
        SUM(
            CASE
                WHEN i.status = 'PAID' THEN i.amount_decimal
                ELSE 0
            END
        ),
        0
    ) AS paid_total
FROM customer_account c
LEFT JOIN billing_invoice i
       ON i.customer_id = c.id
GROUP BY c.id, c.email;
```

**Đọc đúng ngữ nghĩa:**

1. `LEFT JOIN` giữ khách hàng dù chưa có hóa đơn.
2. `COUNT(i.id)` đếm các hóa đơn có `id` khác NULL, không nhầm một dòng của khách hàng chưa có invoice thành một hóa đơn.
3. `CASE` chỉ cộng `amount_decimal` của hóa đơn có `status = 'PAID'`.
4. `COALESCE` trả về 0 khi kết quả tổng hợp là NULL.
5. `GROUP BY` dùng các cột khách hàng được chọn; tên cột đầu ra được đặt rõ bằng `AS`.

Trong thực tế, cần xác nhận cách xử lý số tiền âm, tiền tệ khác nhau, hóa đơn hoàn trả, NULL amount và chính sách ghi nhận thanh toán. Ví dụ chỉ minh họa cách tạo view, **không phải định nghĩa nghiệp vụ hoàn chỉnh** cho mọi hệ thống hóa đơn.

Việc truy vấn thành công trên database thử nghiệm chưa chứng minh hiệu năng sản xuất. Khi số bản ghi tăng lớn, cần xem `EXPLAIN` hoặc công cụ kế hoạch truy vấn tương đương, kiểm tra index trên khóa JOIN và đo tải thực tế.

## 4. Dùng Liquibase createView thay vì chạy SQL thủ công

Change type `createView` diễn đạt việc tạo view trong changelog. Ví dụ YAML:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-create-customer-invoice-view
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer_account
        - tableExists:
            tableName: billing_invoice
      changes:
        - createView:
            viewName: v_customer_invoice_summary
            selectQuery: |
              SELECT
                  c.id AS customer_id,
                  c.email AS customer_email,
                  COUNT(i.id) AS invoice_count,
                  COALESCE(
                      SUM(
                          CASE
                              WHEN i.status = 'PAID'
                              THEN i.amount_decimal
                              ELSE 0
                          END
                      ),
                      0
                  ) AS paid_total
              FROM customer_account c
              LEFT JOIN billing_invoice i
                     ON i.customer_id = c.id
              GROUP BY c.id, c.email
      rollback:
        - dropView:
            viewName: v_customer_invoice_summary
```

Ở đây:

- `viewName` là tên view mà Liquibase cần tạo.
- `selectQuery` chứa phần truy vấn sau `AS`; không cần viết `CREATE VIEW` trong chuỗi này.
- `preConditions` kiểm tra các bảng nguồn trước khi chạy. `onFail: HALT` làm migration dừng nếu thiếu bảng; nó không tự tạo bảng còn thiếu.
- Phần rollback khai báo rõ `dropView` để loại bỏ view nếu cần quay lại trạng thái chưa có view.

Tùy DBMS, việc không chỉ định `schemaName` khiến view được tạo trong schema mặc định của kết nối. Trong hệ thống có nhiều schema hoặc nhiều tenant, hãy xác định rõ schema nguồn, schema đích và quyền truy cập; không giả định `search_path` hoặc default schema ở mọi môi trường giống nhau.

### 4.1. createView trong XML hoặc JSON

Ý nghĩa change type được giữ nguyên khi dùng định dạng khác. Ví dụ XML tối giản:

```xml
<changeSet id="20261119-01-create-customer-invoice-view"
           author="db-team">
    <createView viewName="v_customer_invoice_summary">
        SELECT c.id AS customer_id,
               c.email AS customer_email
        FROM customer_account c
    </createView>
</changeSet>
```

Đây chỉ là đoạn minh họa bên trong một changelog XML hợp lệ. Khi đưa vào dự án, phải bổ sung phần tử gốc `databaseChangeLog`, namespace và schemaLocation phù hợp. Nếu đã có cùng changeset ở YAML, **không include thêm bản XML minh họa** vào một root changelog, vì định danh có thành phần đường dẫn file và có nguy cơ tạo migration trùng chức năng.

## 5. Thay thế view: replaceIfExists và các giới hạn của DBMS

Khi thay đổi logic một view đã tồn tại, Liquibase hỗ trợ thuộc tính `replaceIfExists` của `createView` ở những DBMS và phiên bản hỗ trợ. Ý định thường là sinh câu lệnh tương tự `CREATE OR REPLACE VIEW` thay vì tạo mới và nhận lỗi vì tên view đã có.

Ví dụ nâng cấp view để bổ sung cột thống kê `open_invoice_count` mà vẫn giữ nguyên các cột cũ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-02-add-open-invoice-count
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer_account
        - tableExists:
            tableName: billing_invoice
      changes:
        - createView:
            viewName: v_customer_invoice_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  c.id AS customer_id,
                  c.email AS customer_email,
                  COUNT(i.id) AS invoice_count,
                  COALESCE(
                      SUM(
                          CASE
                              WHEN i.status = 'PAID'
                              THEN i.amount_decimal
                              ELSE 0
                          END
                      ),
                      0
                  ) AS paid_total,
                  COUNT(i.id) FILTER
                      (WHERE i.status = 'OPEN')
                      AS open_invoice_count
              FROM customer_account c
              LEFT JOIN billing_invoice i
                     ON i.customer_id = c.id
              GROUP BY c.id, c.email
```

Đoạn `COUNT(...) FILTER (WHERE ...)` là cú pháp PostgreSQL; để dùng trong migration thật, thêm `dbms: postgresql` vào changeset hoặc viết biểu thức tương thích DBMS đích và kiểm chứng SQL. Ví dụ này minh họa một **changeset mới** thay thế định nghĩa view đã tồn tại.

### 5.1. CREATE OR REPLACE không phải DROP rồi CREATE

| Vấn đề | CREATE OR REPLACE (nếu DBMS hỗ trợ) | DROP rồi CREATE |
|---|---|---|
| Sự tồn tại của object trong quá trình cập nhật | Có thể duy trì object logic, tùy DBMS | Có khoảng thời gian object không tồn tại hoặc thay đổi nguyên tử trong transaction hỗ trợ |
| Phụ thuộc | Có thể bị giới hạn bởi cột/kiểu và đối tượng dùng view | Có thể bị chặn bởi dependency hoặc phải dùng CASCADE gây tác động dây chuyền |
| Quyền/grant | Có thể được giữ trong một số DBMS | Có nguy cơ phải cấp quyền lại |
| Kiểu và thứ tự cột | Nhiều DBMS áp đặt hạn chế khi replace | Tạo lại linh hoạt hơn nhưng đòi hỏi kiểm soát phụ thuộc |
| Khả năng rollback | Cần lưu định nghĩa cũ nếu muốn khôi phục chính xác | Cần tạo lại view và quyền/phụ thuộc cũ |

**Với PostgreSQL**, `CREATE OR REPLACE VIEW` nhìn chung yêu cầu các cột đã tồn tại phải được giữ cùng tên, thứ tự và kiểu; thường có thể thêm cột mới ở cuối. Không nên dựa vào replace để xóa, đổi tên hoặc đổi kiểu cột đầu ra đã có. Đối với các loại thay đổi đó, cần lập kế hoạch chuyển tiếp hoặc tạo view phiên bản mới.

**Với DBMS khác**, hành vi `REPLACE`, `ALTER VIEW` hoặc `CREATE OR ALTER VIEW` có thể khác; cần chạy `liquibase update-sql` trên đúng hệ quản trị và kiểm tra câu lệnh được sinh ra. Đừng giả định `replaceIfExists: true` luôn hỗ trợ trong mọi DBMS, và cũng đừng giả định Liquibase tự xử lý mọi dependency.

### 5.2. Chú ý khi chạy SQL phụ thuộc DBMS

Nếu buộc phải dùng cú pháp riêng, có thể khai báo changeset giới hạn DBMS và sử dụng `sql`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-03-replace-view-postgresql
      author: db-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE OR REPLACE VIEW v_customer_invoice_summary AS
              SELECT
                  c.id AS customer_id,
                  c.email AS customer_email
              FROM customer_account c
      rollback:
        - sql:
            sql: |
              DROP VIEW IF EXISTS v_customer_invoice_summary
```

Đây là ví dụ độc lập về cú pháp SQL, **không phải migration tiếp nối trực tiếp** cho view tổng hợp ở phần trước, vì nó loại bỏ những cột đầu ra cũ và có thể bị PostgreSQL từ chối. Khi cần cập nhật view đang dùng thật, giữ tương thích các cột hiện hữu hoặc thiết kế view mới có tên khác. Tùy trường hợp, `sqlFile` cũng hữu ích để tách SQL dài khỏi changelog.

## 6. runOnChange: tự chạy lại khi nội dung view thay đổi

Một cách quản lý view phổ biến là sử dụng `runOnChange: true` trên changeset. Liquibase lưu checksum của changeset trong `DATABASECHANGELOG` và cho phép thực thi lại changeset khi nội dung có ảnh hưởng tới checksum được chỉnh sửa. View thường là ứng viên phù hợp cho cách này vì định nghĩa của nó có thể được **thay thế toàn bộ**.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-view-customer-summary
      author: db-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_invoice_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  c.id AS customer_id,
                  c.email AS customer_email
              FROM customer_account c
```

Quy trình kỳ vọng:

1. Lần chạy đầu tiên, changeset được áp dụng và Liquibase ghi lịch sử/checksum.
2. Các lần chạy sau, nếu nội dung liên quan đến checksum không thay đổi, changeset thường không chạy lại.
3. Khi định nghĩa view được chỉnh sửa có ý nghĩa, checksum thay đổi và Liquibase có thể chạy lại changeset theo `runOnChange`.
4. `replaceIfExists: true` cho phép tạo hoặc thay định nghĩa view theo khả năng hỗ trợ của DBMS, tránh lỗi “view đã tồn tại”.

**Đừng nhầm `runOnChange` với `runAlways`.** `runAlways` yêu cầu thực thi lại thường xuyên theo cơ chế của Liquibase, kể cả khi nội dung không đổi; phần lớn view không cần làm vậy. `runOnChange` thích hợp hơn với định nghĩa có tính khai báo và được cập nhật theo nội dung.

### 6.1. Hạn chế quan trọng của runOnChange

- Checksum được tính theo cơ chế của Liquibase, **không phải mọi chỉnh sửa khoảng trắng/chú thích** đều chắc chắn làm chạy lại changeset. Cần kiểm chứng khi thay đổi nội dung.
- Một changeset `runOnChange` đã chạy nhiều phiên bản không tự lưu lại **định nghĩa view của từng phiên bản** để rollback. Rollback mặc định hoặc khai báo cũ có thể chỉ xóa view chứ không khôi phục phiên bản trước.
- Dùng `runOnChange` để sửa view đã triển khai có thể thay đổi hợp đồng cột ngay trong một artifact, nhưng các phiên bản ứng dụng cũ vẫn đang chạy. Phải quản lý compatibility như các migration khác.
- Không dùng `runOnChange` như giải pháp chung để sửa changeset tạo bảng, xóa cột hoặc DML không idempotent. Những thay đổi đó thường cần changeset mới.

### 6.2. Lựa chọn giữa runOnChange và changeset mới

| Chiến lược | Điểm mạnh | Điểm cần kiểm soát |
|---|---|---|
| Một changeset view có `runOnChange: true` và `replaceIfExists: true` | Định nghĩa hiện hành tập trung một nơi, tiện bảo trì đối tượng có thể thay thế | Rollback theo phiên bản khó hơn; phải theo dõi tác động với ứng dụng |
| Mỗi lần đổi định nghĩa tạo changeset mới | Lịch sử tiến hóa rõ theo từng phát hành; dễ mô tả chính xác rollback sang phiên bản trước | Định nghĩa SQL có thể lặp lại giữa các changeset |
| Tạo view tên mới theo phiên bản, ví dụ `v_customer_summary_v2` | Cho phép consumer cũ và mới cùng tồn tại | Phải quản lý quyền, phụ thuộc, lộ trình ngừng view cũ |

**Gợi ý vận hành:** Với view nội bộ đơn giản, không thay đổi hợp đồng cột và có khả năng replace an toàn, `runOnChange` là lựa chọn hợp lý. Khi view có nhiều consumer, cần rollback có kiểm toán hoặc thay đổi phá vỡ compatibility, ưu tiên changeset tường minh hoặc view phiên bản mới.

## 7. Tách SQL view dài ra file riêng

View nhiều JOIN, CTE, xử lý JSON hoặc hàm cửa sổ thường khó đọc nếu đặt toàn bộ SQL trong YAML/XML. Liquibase cho phép tham chiếu nội dung view từ file bằng một số thuộc tính của `createView` như `path` và `relativeToChangelogFile`, tùy khả năng hỗ trợ của phiên bản.

Cấu trúc ví dụ:

```text
src/main/resources/db/changelog/
├── db.changelog-master.yaml
├── changes/
│   └── 030-customer-invoice-view.yaml
└── sql/
    └── views/
        └── v_customer_invoice_summary.sql
```

File `changes/030-customer-invoice-view.yaml`:

```yaml
databaseChangeLog:
  - changeSet:
      id: 030-customer-invoice-view
      author: db-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_invoice_summary
            replaceIfExists: true
            path: ../sql/views/v_customer_invoice_summary.sql
            relativeToChangelogFile: true
```

File SQL được tham chiếu chứa **phần truy vấn** của view, không phải toàn bộ DDL:

```sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    COUNT(i.id) AS invoice_count
FROM customer_account c
LEFT JOIN billing_invoice i
       ON i.customer_id = c.id
GROUP BY c.id, c.email
```

`relativeToChangelogFile: true` khiến đường dẫn `../sql/views/...` được giải quyết từ thư mục `changes` — đúng với cây thư mục minh họa. Nếu SQL chứa đầy đủ câu lệnh `CREATE VIEW ... AS ...`, cần xem thuộc tính `fullDefinition` của `createView` và cú pháp mà phiên bản Liquibase hỗ trợ; không đưa full DDL vào file trong khi Liquibase cũng tự thêm `CREATE VIEW`, vì có thể tạo câu SQL trùng tiền tố.

Trong một số phiên bản, khả năng dùng file ngoài, `fullDefinition` và xử lý checksum có thể có chi tiết khác nhau. Hãy kiểm tra bằng `validate` và `update-sql` với đúng Liquibase version trước khi áp dụng.

### 7.1. createView path khác với sqlFile thế nào?

- `createView` với `path`: Liquibase biết thao tác là tạo/thay view và có thể sinh DDL phù hợp qua change type.
- `sqlFile`: Liquibase đọc câu SQL trong file như nội dung của changeset; người viết chịu trách nhiệm câu lệnh `CREATE/ALTER/REPLACE VIEW` và giới hạn DBMS.
- Formatted SQL changelog: chứa chỉ thị `--liquibase formatted sql` và `--changeset author:id`, là một **changelog** độc lập. Đừng nhầm nó với file SQL thường được dùng qua `sqlFile`.

File SQL được sử dụng qua `path` hoặc `sqlFile` cần được đóng gói cùng ứng dụng nếu chạy từ classpath. Nó không trở thành changeset độc lập chỉ vì có phần mở rộng `.sql`.

## 8. Thứ tự tạo view và quan hệ phụ thuộc

Một view phụ thuộc vào bảng, cột và đôi khi view khác. Vì vậy, root changelog phải nạp changeset theo thứ tự tương thích.

```text
001-create-customer-table.yaml
              |
              v
002-create-invoice-table.yaml
              |
              v
030-create-customer-invoice-view.yaml
              |
              v
040-grant-view-access.yaml
```

Ví dụ root changelog:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer-table.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-invoice-table.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/030-create-customer-invoice-view.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/040-grant-view-access.yaml
      relativeToChangelogFile: true
```

Đây là sơ đồ phụ thuộc minh họa, không yêu cầu tạo thêm những file đó trong nhiệm vụ hiện tại. Các changeset tạo bảng phải được áp dụng trước changeset view; grant quyền nên chỉ diễn ra sau khi object tồn tại.

`includeAll` có thể quét thư mục theo quy tắc và thứ tự tên, nhưng với view phụ thuộc nhiều bảng hoặc view khác, `include` tường minh thường dễ kiểm soát. Không giả định Liquibase tự lập topo-sort dựa trên SQL JOIN hay tên đối tượng.

### 8.1. Precondition kiểm tra điều kiện tiên quyết

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: 035-create-view-only-when-sources-exist
      author: db-team
      preConditions:
        - onFail: HALT
        - tableExists:
            tableName: customer_account
        - tableExists:
            tableName: billing_invoice
      changes:
        - createView:
            viewName: v_customer_invoice_summary
            selectQuery: |
              SELECT c.id AS customer_id,
                     c.email AS customer_email
              FROM customer_account c
```

Precondition giúp fail sớm nếu thiếu bảng, nhưng chưa đủ để xác minh chính xác các cột, kiểu dữ liệu, quyền tạo view hoặc tính tương thích của consumer. Nếu view có cột nguồn dễ thay đổi, có thể dùng thêm `columnExists` và các kiểm tra schema khác phù hợp.

**Không dùng `onFail: MARK_RAN` chỉ để bỏ qua việc tạo view đang thiếu tiền đề.** Điều đó có thể ghi lịch sử “đã chạy” dù view chưa tồn tại. Với đối tượng schema bắt buộc, dừng lại và sửa thứ tự migration thường an toàn hơn.

## 9. Thay đổi cột đầu ra: coi view như một hợp đồng API

Khi ứng dụng query `v_customer_invoice_summary`, tên và kiểu cột là giao diện giữa database với code. Hãy xem việc đổi chúng như phiên bản API:

| Thay đổi view | Ảnh hưởng có thể gặp | Cách làm thường an toàn hơn |
|---|---|---|
| Thêm cột cuối | Nhiều consumer chọn cột tường minh vẫn hoạt động; consumer dùng `SELECT *` có thể bị ảnh hưởng | Review mapper, DTO; kiểm thử với ứng dụng cũ và mới |
| Đổi tên cột | Query hoặc ORM mapping cũ lỗi | Giữ tên cũ trong giai đoạn chuyển tiếp hoặc tạo view v2 |
| Đổi kiểu cột | JDBC/ORM serializer, aggregate và BI có thể xử lý khác | Bổ sung cột mới hoặc view v2, migrate consumer |
| Bỏ cột | Consumer đang dùng cột sẽ lỗi | Deprecate, đo sử dụng, sau đó contract |
| Đổi điều kiện lọc/JOIN | Giá trị hoặc số dòng trả về thay đổi, dù schema view giống nhau | Kiểm thử nghiệp vụ và đối soát dữ liệu |
| Đổi quyền truy cập | Role ứng dụng có thể không query được | Kiểm thử GRANT/revoke theo nguyên tắc đặc quyền tối thiểu |

Ví dụ cần đổi `customer_email` thành `contact_email`. Thay vì ngay lập tức đổi tên cột trong view đang dùng, có thể tạo `v_customer_invoice_summary_v2` với hợp đồng mới, cấp quyền cho ứng dụng mới và giữ view cũ trong một khoảng thời gian có kiểm soát.

Quy trình chuyển tiếp:

1. Tạo view v2 từ bảng nguồn hiện có, giữ view v1.
2. Kiểm thử v1 và v2 trên cùng database.
3. Triển khai ứng dụng mới chuyển sang v2.
4. Xác nhận không còn consumer v1 (ứng dụng, job, BI, báo cáo).
5. Thu hồi quyền hoặc xóa v1 bằng changeset riêng trong đợt sau.

Đây là chiến lược expand–contract áp dụng cho view. Nó giúp tránh sự thay đổi phá vỡ hợp đồng trong lúc có nhiều phiên bản ứng dụng cùng chạy.

## 10. Rollback: khôi phục trạng thái nào?

Rollback view không đơn thuần là “DROP VIEW” trong mọi trường hợp. Cần xét view đang được tạo lần đầu, bị thay định nghĩa hay đang có consumer khác.

### 10.1. View mới chưa có dữ liệu riêng

Với changeset chỉ tạo một view mới, rollback `dropView` có thể phù hợp:

```yaml
rollback:
  - dropView:
      viewName: v_customer_invoice_summary
```

Cần đảm bảo không còn view khác, function, báo cáo hay ứng dụng phụ thuộc. Nếu DBMS chặn việc drop vì dependency, không được dùng `CASCADE` một cách tùy tiện vì có thể xóa nhiều đối tượng ngoài dự kiến.

### 10.2. View đã tồn tại và vừa được thay định nghĩa

Nếu dùng changeset mới để thay v1 bằng v2, rollback đúng về mặt nghiệp vụ thường là **khôi phục SQL của v1**, không phải xóa hoàn toàn view. Ví dụ thay định nghĩa một view trên PostgreSQL:

```yaml
databaseChangeLog:
  - changeSet:
      id: 050-add-view-open-invoice-count
      author: db-team
      dbms: postgresql
      changes:
        - createView:
            viewName: v_customer_invoice_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  c.id AS customer_id,
                  c.email AS customer_email,
                  COUNT(i.id) AS invoice_count,
                  COALESCE(
                      SUM(CASE WHEN i.status = 'PAID'
                               THEN i.amount_decimal ELSE 0 END),
                      0
                  ) AS paid_total,
                  COUNT(i.id) FILTER
                      (WHERE i.status = 'OPEN')
                      AS open_invoice_count
              FROM customer_account c
              LEFT JOIN billing_invoice i
                     ON i.customer_id = c.id
              GROUP BY c.id, c.email
      rollback:
        - createView:
            viewName: v_customer_invoice_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  c.id AS customer_id,
                  c.email AS customer_email,
                  COUNT(i.id) AS invoice_count,
                  COALESCE(
                      SUM(CASE WHEN i.status = 'PAID'
                               THEN i.amount_decimal ELSE 0 END),
                      0
                  ) AS paid_total
              FROM customer_account c
              LEFT JOIN billing_invoice i
                     ON i.customer_id = c.id
              GROUP BY c.id, c.email
```

Mẫu này minh họa ý định rollback về định nghĩa cũ. **Cảnh báo đặc biệt với PostgreSQL:** nếu v2 đã thêm cột đầu ra mới, câu `CREATE OR REPLACE VIEW` trong rollback có thể không được phép xóa cột đó. Khi đó, rollback ở trên **không chắc chạy thành công**, dù được viết đúng cú pháp Liquibase. Phải thử trước trên đúng DBMS và xem chiến lược an toàn: giữ cột mới tương thích, tạo view v2 riêng, hoặc có kế hoạch xử lý dependencies và quyền trước khi drop/recreate.

Một rollback đúng phải được kiểm chứng bằng `rollback-sql` và thử trên database có schema/lịch sử đại diện. Không ghi `dropView` như rollback mặc định của một changeset thay thế nếu hệ thống cần giữ lại view trước đó.

### 10.3. runOnChange và rollback

Nếu một changeset `runOnChange` đã được chạy lại qua nhiều phiên bản, lịch sử checksum không tự cung cấp nội dung SQL của v1 và v2 để tái tạo mọi phiên bản theo thời điểm. Muốn rollback chính xác, cần lưu phiên bản định nghĩa trong hệ thống quản lý mã nguồn, chọn tag/phiên bản triển khai và chuẩn bị migration bù hoặc thay đổi được review. Đừng giả định revert commit Git rồi chạy rollback Liquibase sẽ tự khôi phục toàn bộ object.

## 11. Quyền truy cập, schema và bảo mật khi thay view

View thường có người sử dụng không trực tiếp là tài khoản deploy migration. Vì vậy, cần kiểm tra:

- **Schema đích:** view nằm trong schema nào, ứng dụng đặt `search_path` ra sao và tên object có cần schema-qualified hay không.
- **Quyền tạo/sửa view:** tài khoản migration có đặc quyền phù hợp; quyền sở hữu và vai trò của người tạo có thể ảnh hưởng thao tác replace.
- **Quyền SELECT:** role của ứng dụng, BI hoặc job có được truy cập sau khi thay thế không.
- **Quyền trên bảng nền:** cách DBMS áp dụng quyền qua view phụ thuộc engine, owner và cấu hình bảo mật; không suy từ một DBMS sang DBMS khác.
- **Rò rỉ thông tin:** view có đang làm lộ cột nhạy cảm qua `SELECT *` hoặc phép JOIN không.

Tránh dùng `SELECT *` trong định nghĩa view dùng làm hợp đồng lâu dài: việc thêm cột ở bảng nền có thể tạo hành vi khác nhau theo DBMS, và schema đầu ra khó được kiểm soát. Liệt kê cột cụ thể giúp review thay đổi thuận tiện.

Quyền truy cập có thể được quản lý bằng changeset SQL riêng nếu công cụ và DBMS yêu cầu, nhưng SQL GRANT/REVOKE là thao tác bảo mật cần kiểm chứng trên đúng môi trường. Không giả định DROP/CREATE sẽ giữ được owner và mọi grant đã có.

## 12. Kiểm chứng trước và sau migration view

Một quy trình kiểm chứng tốt gồm nhiều mức:

### 12.1. Kiểm tra changelog và SQL dự kiến

Sau khi cấu hình root changelog và database đích, có thể chạy:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
```

- `validate` kiểm tra cấu trúc changelog và một số điều kiện hợp lệ, nhưng không bảo đảm view chạy nhanh hoặc dữ liệu trả về đúng.
- `status --verbose` giúp xác định changeset còn pending theo lịch sử và bộ lọc hiện tại.
- `update-sql` hiển thị câu lệnh Liquibase dự kiến tạo ra; kiểm tra đúng `CREATE VIEW` hay `CREATE OR REPLACE VIEW`, schema, tên cột và thứ tự.

Các câu lệnh trên cần cùng cấu hình kết nối, root changelog, context, label, phiên bản Liquibase và DBMS với lần `update` thực tế. Nếu dùng `runOnChange`, cần đặc biệt chú ý changeset cũ có được chọn chạy lại hay không.

### 12.2. Kiểm tra sự tồn tại và hợp đồng cột

Trên PostgreSQL hoặc hệ quản trị có `information_schema` tương thích, có thể đọc metadata:

```sql
SELECT table_schema, table_name, view_definition
FROM information_schema.views
WHERE table_name = 'v_customer_invoice_summary';

SELECT column_name, data_type, ordinal_position
FROM information_schema.columns
WHERE table_name = 'v_customer_invoice_summary'
ORDER BY ordinal_position;
```

Truy vấn metadata có thể phụ thuộc quyền và schema hiển thị. Khi có nhiều schema cùng tên view, phải lọc thêm `table_schema`. Một view tồn tại nhưng có cột đầu ra sai tên hoặc sai kiểu vẫn là migration không đạt yêu cầu.

### 12.3. Kiểm tra dữ liệu và hành vi nghiệp vụ

Truy vấn view với nhiều trường hợp:

```sql
SELECT customer_id, customer_email, invoice_count, paid_total
FROM v_customer_invoice_summary
ORDER BY customer_id;
```

Dùng bộ dữ liệu thử nghiệm có ít nhất:

1. Khách hàng không có invoice.
2. Khách hàng có một invoice PAID.
3. Khách hàng có cả PAID và OPEN.
4. Invoice có giá trị tiền âm hoặc NULL, nếu nghiệp vụ cho phép.
5. Khách hàng có nhiều invoice để phát hiện đếm sai do JOIN.

So sánh với truy vấn tham chiếu độc lập hoặc kết quả mong đợi đã định nghĩa. Không dùng một lần `SELECT` thành công làm bằng chứng duy nhất; cần test các trường hợp biên, chi phí query và quyền của role ứng dụng.

### 12.4. Kiểm tra lịch sử và ứng dụng

Liquibase ghi những changeset đã áp dụng trong `DATABASECHANGELOG`, thường với `ID`, `AUTHOR`, `FILENAME`, `MD5SUM`, `DATEEXECUTED`, `EXECTYPE`. Kiểm tra view changeset có được ghi nhận đúng, không bị coi là thay đổi mới chỉ vì đổi đường dẫn file. Nếu dùng `runOnChange`, phân tích xem lần chạy lại có được ghi nhận theo hành vi tương ứng hay không.

Sau đó chạy integration test với **đúng version ứng dụng** và role database của runtime, không chỉ tài khoản Liquibase có quyền cao. Với view dùng trong JPA/ORM, xác minh mapping, kiểu cột, result set và pagination nếu có.

## 13. Tích hợp Spring Boot và CI/CD

Spring Boot có thể nạp root changelog từ classpath:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Các changelog con và file SQL tham chiếu qua `createView.path` hoặc `sqlFile` phải có mặt trong artifact. File nằm tại `src/main/resources/db/changelog/...` thường được đóng gói dưới đường dẫn tài nguyên `db/changelog/...`; không thêm `src/main/resources` vào tên classpath.

Với CI/CD, một lộ trình đề xuất:

1. Review thay đổi definition SQL, đặc biệt tên/kiểu/thứ tự cột và quyền truy cập.
2. Đảm bảo file view được nạp từ đúng root changelog; SQL path có thể tìm thấy trong artifact.
3. Kiểm tra thứ tự: bảng/cột nguồn trước, view sau, grant/quyền sau cùng.
4. Chạy `validate` và `status --verbose` với cấu hình deploy.
5. Sinh `update-sql`, review DDL replace/drop/create và rủi ro dependency.
6. Thử migration trên database cùng DBMS, phiên bản và schema gần production.
7. Chạy các truy vấn so sánh dữ liệu, metadata và kiểm thử ứng dụng cũ/mới.
8. Thử `rollback-sql` và rollback trên môi trường thử nghiệm; ghi lại giới hạn chưa thể hoàn tác.
9. Triển khai với quyền, thời điểm và phương án khôi phục đã phê duyệt.
10. Hậu kiểm view, role truy cập, thời gian truy vấn và lịch sử `DATABASECHANGELOG`.

Nếu hệ thống có nhiều instance Spring Boot cùng khởi động, cần thống nhất một cơ chế chạy migration (pipeline riêng hoặc quy tắc khởi động nhất quán). `DATABASECHANGELOGLOCK` giúp đồng bộ việc thực thi Liquibase, nhưng không bảo vệ khỏi thay đổi view phá vỡ compatibility khi các instance ứng dụng cũ vẫn đang chạy.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
|---|---|---|
| Tạo view thất bại vì bảng nguồn không tồn tại | Thứ tự changeset sai hoặc filter bỏ qua migration tạo bảng | Kiểm tra include, status, precondition và bảng thực tế |
| View đã tồn tại nên createView báo lỗi | Chưa cấu hình `replaceIfExists` hoặc chưa thiết kế changeset thay thế | Xem DBMS hỗ trợ và thay đổi có cần migration mới không |
| CREATE OR REPLACE thất bại khi đổi cột | DBMS hạn chế đổi tên, loại hoặc thứ tự/kiểu cột | Chọn view v2 hoặc thiết kế contract migration |
| View tạo thành công nhưng không trả kết quả mong muốn | JOIN, GROUP BY, NULL hoặc quy tắc nghiệp vụ sai | Kiểm thử dữ liệu biên và đối soát truy vấn |
| Ứng dụng báo thiếu cột | View đổi hợp đồng trong khi app cũ còn chạy | Giữ compatibility hoặc dùng view phiên bản mới |
| Role ứng dụng bị từ chối SELECT | Thiếu GRANT, owner hoặc schema bị thay đổi | Kiểm tra quyền bằng role runtime và lịch sử DDL |
| runOnChange không chạy lại như kỳ vọng | Nội dung ảnh hưởng checksum chưa đổi, hoặc cấu hình/lịch sử khác | Kiểm tra checksum, file được nạp và log Liquibase |
| Migration sau deploy chạy lại view như mới | Đổi `id`, `author` hoặc `FILENAME` do đổi đường dẫn | Kiểm tra tuple danh tính, dùng `logicalFilePath` khi phù hợp |
| SQL file không tìm thấy trong JAR | Đường dẫn `path`/classpath sai hoặc file không được đóng gói | Kiểm tra artifact, `relativeToChangelogFile`, cấu hình build |
| Rollback xóa view thay vì phục hồi định nghĩa trước | Chỉ khai báo `dropView` cho changeset thay thế | Lập kế hoạch rollback có phiên bản, kiểm thử DBMS |
| Drop view bị chặn vì dependency | View/đối tượng khác đang phụ thuộc | Xác định đồ thị phụ thuộc, không dùng CASCADE tùy tiện |
| View chậm sau khi thay | Kế hoạch truy vấn, index hoặc lượng dữ liệu thay đổi | Kiểm tra execution plan và đo tải thật |

## 15. Bài thực hành: tạo, thay và kiểm chứng view

**Đề bài.** Trong một database thử nghiệm độc lập có bảng `customer_account(id, email)` và `billing_invoice(id, customer_id, status, amount_decimal)`:

1. Viết changeset `createView` tạo `v_customer_invoice_summary` với ba cột `customer_id`, `customer_email` và `invoice_count`.
2. Dùng `tableExists` để dừng nếu thiếu một trong hai bảng.
3. Thêm một changeset mới dùng `replaceIfExists: true`, bổ sung cột `paid_total` mà vẫn giữ tên/kiểu các cột cũ.
4. Kiểm tra SQL dự kiến bằng `update-sql`, không chạy trực tiếp trên production.
5. Đưa dữ liệu kiểm thử: một khách hàng không có invoice, một khách hàng có invoice PAID, một khách hàng có cả PAID và OPEN.
6. Truy vấn view, xác nhận `invoice_count` và `paid_total` đúng.
7. Giả lập tình huống app cũ chỉ đọc ba cột đầu và app mới đọc thêm `paid_total`; giải thích rủi ro của consumer dùng `SELECT *`.
8. Chuẩn bị rollback có khả năng khôi phục định nghĩa cũ **trên DBMS đã chọn**, và kiểm chứng thực tế thay vì chỉ viết `dropView`.
9. Thử một phiên bản khác có `runOnChange: true` trên môi trường tách biệt, quan sát hành vi khi sửa SQL nhưng không đổi `id`/`author`/đường dẫn changelog.
10. Kiểm tra lịch sử trong `DATABASECHANGELOG` và giải thích vì sao không nên đổi tên file changeset sau khi đã triển khai.

**Tiêu chí hoàn thành:** không có changeset cũ bị nhận diện thành mới; view có đúng hợp đồng và dữ liệu đầu ra; việc replace không vô tình phá consumer; SQL, rollback và quyền truy cập đã được kiểm tra với đúng DBMS.

## 16. Checklist trước khi merge và deploy

- [ ] Đã chọn rõ view thông thường, không nhầm với materialized view.
- [ ] Định nghĩa truy vấn đúng logic nghiệp vụ, có alias và cột đầu ra tường minh.
- [ ] Các bảng/cột nguồn đã tồn tại trước changeset view.
- [ ] `createView` dùng đúng `viewName`, `selectQuery` hoặc `path`; không bị trùng `CREATE VIEW`.
- [ ] Khi thay thế, `replaceIfExists` đã được kiểm chứng trên DBMS/phiên bản đang dùng.
- [ ] Nếu dùng `runOnChange`, hiểu rõ checksum, hành vi chạy lại và giới hạn rollback.
- [ ] Không thay changeset lịch sử một cách tùy tiện; `id`, `author`, đường dẫn logic được giữ ổn định.
- [ ] Cột view hiện hữu tương thích với các consumer; thay đổi phá vỡ hợp đồng có kế hoạch view v2.
- [ ] Có đánh giá quyền SELECT/GRANT, owner, schema và đặc quyền runtime.
- [ ] Có kiểm thử dữ liệu biên, NULL, JOIN, aggregation và hiệu năng truy vấn.
- [ ] Đã kiểm tra phụ thuộc view khác, function, báo cáo và ORM.
- [ ] `validate`, `status --verbose` và `update-sql` được chạy với đúng cấu hình.
- [ ] Rollback được thiết kế theo trạng thái trước đó, không mặc định drop view là đủ.
- [ ] File SQL được đóng gói vào classpath và đường dẫn tham chiếu hoạt động trong CI/CD.
- [ ] Đã hậu kiểm định nghĩa view, cột, quyền ứng dụng và lịch sử triển khai.

Tạo và thay thế view bằng Liquibase là quản lý **một hợp đồng SQL có phiên bản**, không chỉ gửi lệnh `CREATE VIEW` tới database. `createView` giúp biểu diễn đối tượng trong changelog, `replaceIfExists` hỗ trợ cập nhật định nghĩa ở những DBMS phù hợp và `runOnChange` phục vụ các view được thay thế theo nội dung. Độ an toàn vẫn phụ thuộc vào thứ tự tạo đối tượng, tính tương thích của các cột, quyền truy cập, khả năng kiểm chứng và rollback trên đúng môi trường thực tế.

