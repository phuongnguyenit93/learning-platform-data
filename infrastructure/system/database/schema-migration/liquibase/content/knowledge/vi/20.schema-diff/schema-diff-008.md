# Rà soát thứ tự DDL, nguy cơ mất dữ liệu và khả năng hoàn tác

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta học cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở chương **So sánh lược đồ**, việc rà soát thứ tự DDL, nguy cơ mất dữ liệu và khả năng hoàn tác giúp bảo đảm một thay đổi database có thể triển khai an toàn trên trạng thái thực tế, không phá vỡ ứng dụng đang chạy và có phương án phục hồi rõ ràng.

Một changeset có thể hợp lệ về cú pháp nhưng vẫn nguy hiểm khi chạy: tạo foreign key trước khi bảng đích tồn tại, đổi kiểu cột làm mất dữ liệu, thêm NOT NULL khi vẫn có hàng NULL, drop cột đang được ứng dụng sử dụng hoặc rollback không thể khôi phục dữ liệu đã xóa. Vì vậy, review DDL phải trả lời ba câu hỏi:

1. **Thứ tự:** đối tượng nào phải tồn tại trước, và thao tác nào phụ thuộc thao tác nào?
2. **Tác động:** DDL/DML ảnh hưởng dữ liệu, lock, transaction, ứng dụng và các môi trường ra sao?
3. **Khả năng phục hồi:** có thể rollback thật sự, cần backup/forward-fix, hay thay đổi không thể đảo ngược?

## 1. Phân biệt DDL, DML và thay đổi vận hành

DDL (Data Definition Language) thay đổi cấu trúc database; DML (Data Manipulation Language) đọc hoặc thay đổi các dòng dữ liệu. Một migration thường kết hợp cả hai.

| Loại thao tác | Ví dụ | Rủi ro cần review |
|---|---|---|
| Tạo đối tượng | CREATE TABLE, CREATE SEQUENCE, CREATE VIEW | Thứ tự dependency, quyền, schema đích |
| Sửa cấu trúc | ALTER TABLE ADD/ALTER COLUMN, ADD CONSTRAINT | Lock, compatibility, dữ liệu hiện hữu |
| Tạo index | CREATE INDEX, CREATE UNIQUE INDEX | Thời gian xây dựng, ghi đồng thời, dung lượng, lock |
| Xóa đối tượng | DROP TABLE, DROP COLUMN, DROP INDEX | Mất dữ liệu, dependency, khả năng khôi phục |
| Chuyển dữ liệu | UPDATE, INSERT, DELETE, backfill | Số hàng, tính đúng đắn, transaction log, rollback |
| Thay đổi quyền | GRANT, REVOKE, đổi owner | Ứng dụng/job mất quyền hoặc quyền quá rộng |
| Thay đổi logic database | View, function, procedure, trigger | Tương thích ứng dụng, thứ tự tạo, dependency và phiên bản định nghĩa |

DDL không phải lúc nào cũng là thao tác tức thời hoặc chỉ thay đổi metadata. Một ALTER TABLE có thể quét toàn bộ bảng, viết lại dữ liệu, giữ lock lâu hoặc cần dung lượng tạm. Một DROP COLUMN có thể loại bỏ dữ liệu không thể phục hồi nếu không có bản sao.

Trong Liquibase, change type như createTable, addColumn, addForeignKeyConstraint, createIndex hoặc modifyDataType giúp mô tả ý định có cấu trúc. Khi dùng sql/sqlFile cho DDL đặc thù, trách nhiệm review câu lệnh, transaction, rollback và tính di động càng quan trọng.

## 2. Rà soát dependency để quyết định thứ tự DDL

Không nên sắp xếp changeset chỉ theo tên file hoặc ngày tạo. Hãy dựng đồ thị dependency của đối tượng và thao tác.

Một chuỗi thường gặp:

~~~text
Schema / quyền / sequence cần thiết
             |
             v
Bảng nền tảng và bảng tham chiếu
             |
             v
Cột + khóa chính / unique
             |
             v
Bảng phụ thuộc và foreign key
             |
             v
Dữ liệu tham chiếu / backfill
             |
             v
Index / view / function / trigger
             |
             v
Ứng dụng dùng cấu trúc mới
             |
             v
Loại bỏ cấu trúc cũ sau khi không còn consumer
~~~

Đây là sơ đồ khái quát, không phải thứ tự bắt buộc cho mọi DBMS. Ví dụ index có thể cần tạo trước hoặc sau backfill tùy quy mô và kế hoạch truy vấn; trigger có thể cần tồn tại trước khi bắt đầu ghi dữ liệu mới; constraint có thể cần thêm sau khi đã làm sạch dữ liệu.

### 2.1. Các dependency thường gặp

| Đối tượng/thao tác | Phụ thuộc thường thấy |
|---|---|
| CREATE TABLE | Schema tồn tại, quyền tạo đối tượng |
| PRIMARY KEY | Bảng và cột tồn tại; dữ liệu không NULL/trùng nếu áp dụng trên bảng có dữ liệu |
| FOREIGN KEY | Bảng/cột nguồn và bảng/cột tham chiếu tồn tại; kiểu dữ liệu tương thích |
| UNIQUE constraint/index | Cột tồn tại; dữ liệu hiện tại không vi phạm tính duy nhất |
| DEFAULT/identity | Cột tồn tại; sequence/generator phải có nếu dùng sequence riêng |
| VIEW | Các bảng, cột, view/function được tham chiếu tồn tại |
| FUNCTION/PROCEDURE | Kiểu dữ liệu, schema và dependency cần thiết |
| TRIGGER | Bảng và function/procedure mà trigger gọi tồn tại |
| DROP TABLE/COLUMN | Consumer, FK, view, trigger, procedure và ứng dụng không còn phụ thuộc |
| GRANT | User/role và đối tượng đích tồn tại |

### 2.2. Tạo theo dependency, xóa theo chiều ngược

Một quy tắc hữu ích là **tạo đối tượng theo thứ tự dependency từ nền tảng đến consumer; xóa theo chiều ngược từ consumer về nền tảng**.

Ví dụ: nếu orders có foreign key tới customers, cần tạo customers trước orders và foreign key. Khi dọn schema, phải xử lý constraint/consumer trước khi drop bảng customers. Không dùng CASCADE tùy tiện để vượt lỗi dependency vì có thể xóa thêm đối tượng mà nhóm không dự định tác động.

### 2.3. Include order trong changelog phải có chủ đích

Ví dụ root changelog:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/001-create-customers.yaml
  - include:
      file: db/changelog/002-create-orders.yaml
  - include:
      file: db/changelog/003-add-order-constraints.yaml
  - include:
      file: db/changelog/004-create-report-view.yaml
~~~

Các file trên chỉ là cấu trúc minh họa. Khi dùng includeAll, phải hiểu quy tắc sắp xếp file của phiên bản Liquibase và đảm bảo thứ tự không phụ thuộc vào hành vi không ổn định của filesystem hoặc build artifact. Nếu dependency quan trọng, include tường minh dễ review hơn.

Không di chuyển hoặc đổi đường dẫn logic của changeset đã triển khai mà không có kế hoạch bảo toàn định danh lịch sử. Chỉnh thứ tự include cũng cần kiểm tra liệu changeset đã chạy có bị thay đổi thứ tự ở database mới hay không.

## 3. Dựng ví dụ dependency giữa customers và orders

Giả sử ứng dụng có hai bảng:

- customers chứa khách hàng.
- orders chứa đơn hàng và tham chiếu customers.id.

Một changelog minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: ddl-001-create-customers
      author: database-team
      changes:
        - createTable:
            schemaName: app
            tableName: customers
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_code
                  type: VARCHAR(40)
                  constraints:
                    nullable: false
                    unique: true

  - changeSet:
      id: ddl-002-create-orders
      author: database-team
      changes:
        - createTable:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    nullable: false

  - changeSet:
      id: ddl-003-add-orders-customer-fk
      author: database-team
      changes:
        - addForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: orders
            baseColumnNames: customer_id
            referencedTableSchemaName: app
            referencedTableName: customers
            referencedColumnNames: id
            constraintName: fk_orders_customers
~~~

Trong ví dụ này, thứ tự tạo customers → orders → foreign key là hợp lý. Nếu foreign key được tạo trước khi orders hoặc customers tồn tại, migration sẽ thất bại. Nếu bảng orders đã có dữ liệu, cột customer_id phải có giá trị tham chiếu hợp lệ trước khi constraint được thêm.

Đây là ví dụ DDL minh họa; kiểu autoIncrement, schemaName, cách đặt constraint và SQL được sinh cần kiểm tra trên DBMS đích. Nếu ứng dụng yêu cầu dữ liệu ban đầu, cần có changeset seed/reference data riêng và kiểm tra thứ tự của nó.

## 4. Thêm constraint trên bảng đã có dữ liệu

Một DDL có thể đúng với bảng rỗng nhưng thất bại khi chạy trên bảng có hàng hiện hữu.

Ví dụ thêm NOT NULL:

~~~yaml
- changeSet:
    id: ddl-010-add-required-status
    author: database-team
    changes:
      - addColumn:
          schemaName: app
          tableName: orders
          columns:
            - column:
                name: status
                type: VARCHAR(20)
                defaultValue: NEW
                constraints:
                  nullable: false
~~~

Cách này có thể phù hợp trong một số DBMS và quy mô dữ liệu, nhưng không được giả định rằng việc thêm cột với default sẽ luôn rẻ hoặc không khóa bảng. DBMS có thể viết lại bảng, áp dụng default theo cách khác hoặc có giới hạn riêng.

Trước khi thêm constraint trên bảng đã có dữ liệu, cần biết:

- Bảng có bao nhiêu dòng và tốc độ ghi hiện tại?
- Có giá trị NULL hoặc duplicate vi phạm constraint không?
- Default được áp dụng cho dữ liệu cũ theo cách nào ở DBMS đó?
- Thay đổi có cần quét bảng hoặc rewrite dữ liệu không?
- Có thể triển khai online mà không khóa lâu không?
- Phiên bản ứng dụng cũ có hiểu cột mới không?

### 4.1. Chiến lược an toàn hơn cho bảng lớn

Với hệ thống cần duy trì hoạt động, có thể tách thành nhiều giai đoạn:

1. **Expand:** thêm cột nullable, chưa bắt buộc ứng dụng ghi ngay.
2. **Deploy compatible application:** ứng dụng mới có thể đọc cả dữ liệu cũ và mới; bắt đầu ghi giá trị mới.
3. **Backfill:** cập nhật các dòng cũ theo batch, có checkpoint và kiểm tra.
4. **Validate:** xác nhận không còn NULL hoặc giá trị không hợp lệ.
5. **Enforce:** thêm NOT NULL/constraint khi dữ liệu đã đạt.
6. **Cleanup:** loại bỏ fallback cũ sau khi mọi phiên bản ứng dụng tương thích.

Ví dụ changeset đầu tiên:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-020-add-status-nullable
      author: database-team
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: status
                  type: VARCHAR(20)
~~~

Sau khi backfill hoàn tất và đã kiểm tra:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-021-enforce-status-not-null
      author: database-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.orders
              WHERE status IS NULL
      changes:
        - addNotNullConstraint:
            schemaName: app
            tableName: orders
            columnName: status
            columnDataType: VARCHAR(20)
~~~

Ví dụ precondition giúp dừng nếu còn NULL. Cần điều chỉnh cú pháp SQL, kiểu dữ liệu và khả năng hỗ trợ theo DBMS. Precondition không thay thế việc đánh giá lock, thời gian quét và tác động của ALTER TABLE.

## 5. Phân tích nguy cơ mất dữ liệu trước khi viết DDL

Mọi thay đổi cần được phân loại theo mức độ ảnh hưởng đến dữ liệu và khả năng đảo ngược.

| Thao tác | Nguy cơ | Câu hỏi bắt buộc |
|---|---|---|
| ADD COLUMN nullable | Thấp đến trung bình | Có ảnh hưởng lock/storage/ORM không? |
| ADD COLUMN NOT NULL | Trung bình đến cao | Dữ liệu cũ được lấp thế nào? Có rewrite/scan không? |
| ALTER TYPE | Trung bình đến rất cao | Có mất độ chính xác, truncate, lỗi cast hoặc rewrite không? |
| DROP COLUMN | Rất cao | Dữ liệu còn cần cho ứng dụng, báo cáo hoặc rollback không? |
| DROP TABLE | Rất cao | Có dữ liệu cần giữ, FK, view hoặc consumer nào không? |
| DELETE/UPDATE | Tùy số hàng và logic | WHERE có đúng? Có lưu bản gốc? |
| ADD UNIQUE | Trung bình đến cao | Dữ liệu hiện tại có duplicate không? |
| ADD FOREIGN KEY | Trung bình đến cao | Có orphan rows không? |
| CREATE INDEX | Trung bình | Lock, dung lượng, thời gian và ảnh hưởng ghi? |
| DROP INDEX | Trung bình đến cao | Query nào đang phụ thuộc hiệu năng vào index? |

Không chỉ xem câu lệnh có thể rollback về mặt cú pháp. Hãy đánh giá **giá trị dữ liệu có thể phục hồi hay không**. DROP COLUMN rồi ADD COLUMN cùng tên không khôi phục nội dung đã xóa; đó là một cột mới rỗng.

### 5.1. DROP, TRUNCATE và DELETE không giống nhau

- **DROP TABLE:** loại bỏ đối tượng bảng và dữ liệu trong bảng.
- **TRUNCATE:** loại bỏ toàn bộ dòng theo ngữ nghĩa DBMS; thường có ảnh hưởng đến identity/sequence, trigger hoặc FK tùy engine.
- **DELETE:** xóa các dòng thỏa điều kiện; có thể giới hạn theo WHERE nhưng vẫn cần kiểm tra số hàng và transaction.
- **DROP COLUMN:** loại bỏ cột và dữ liệu trong cột.
- **ALTER TYPE:** có thể chuyển đổi, làm tròn, truncate hoặc từ chối dữ liệu không tương thích.

Cú pháp và transaction behavior khác nhau giữa DBMS. Không dùng một câu rollback chung cho mọi engine.

### 5.2. Những dạng mất dữ liệu khó nhận ra

- VARCHAR(200) đổi thành VARCHAR(50) có thể làm lỗi hoặc cắt dữ liệu tùy DBMS/cách chuyển đổi.
- DECIMAL(18,4) đổi thành DECIMAL(12,2) có thể mất độ chính xác hoặc vượt giới hạn.
- Timestamp đổi timezone hoặc precision có thể thay đổi ý nghĩa.
- Đổi collation/case sensitivity có thể làm unique constraint phát hiện xung đột.
- Thay đổi encoding có thể làm ký tự không biểu diễn được.
- Thêm NOT NULL với default sai có thể gán cùng giá trị không đúng cho mọi dòng cũ.
- Drop constraint quá sớm có thể cho phép dữ liệu không hợp lệ xuất hiện trong lúc rollout.

## 6. Rà soát ALTER TYPE và chuyển đổi dữ liệu

Ví dụ thay đổi cột amount từ DECIMAL(18,2) sang DECIMAL(10,2) có vẻ chỉ là đổi kiểu, nhưng miền giá trị tối đa giảm mạnh. Nếu có bản ghi vượt giới hạn mới, DDL có thể thất bại; nếu quy tắc chuyển đổi làm tròn hoặc cắt, dữ liệu có thể thay đổi.

Trước khi đổi type:

1. Truy vấn MIN/MAX và kiểm tra precision/scale hiện tại.
2. Xác định giá trị ngoài miền mới.
3. Đánh giá cast có mất dữ liệu hay không.
4. Xem index, constraint, view, function, procedure và ứng dụng phụ thuộc.
5. Xem DDL có rewrite bảng hoặc giữ lock không.
6. Chuẩn bị chuyển đổi theo batch nếu cần.
7. Lưu snapshot/backup nếu thay đổi có nguy cơ không đảo ngược.
8. Xác minh dữ liệu sau chuyển đổi bằng truy vấn nghiệp vụ.

Ví dụ kiểm tra trước khi thu hẹp precision:

~~~sql
SELECT COUNT(*) AS out_of_range_count
FROM app.invoice_line
WHERE amount >= 100000000;
~~~

Ngưỡng trên chỉ minh họa cho một miền giá trị cụ thể; phải tính đúng theo precision/scale, dấu âm và quy tắc làm tròn của DBMS. Không dùng truy vấn mẫu mà chưa xác định miền giá trị nghiệp vụ.

### 6.1. Dùng changeset mới cho chuyển đổi

Nếu cột đã được tạo trong một changeset đã triển khai, không sửa changeset cũ để thay type. Thêm changeset mới:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: invoice-030-adjust-amount-precision
      author: database-team
      changes:
        - modifyDataType:
            schemaName: app
            tableName: invoice_line
            columnName: amount
            newDataType: DECIMAL(18,2)
~~~

Ví dụ này minh họa một thay đổi được review; không phải khuyến nghị đổi precision trong mọi hệ thống. Liquibase có thể sinh SQL khác nhau tùy DBMS, và khả năng rollback tự động không bảo đảm khôi phục giá trị đã bị mất.

## 7. Rename column/table: thay đổi tên cũng là thay đổi hợp đồng

Đổi tên cột hoặc bảng có thể không xóa dữ liệu, nhưng dễ phá ứng dụng đang chạy:

- Bản ứng dụng cũ vẫn truy vấn tên cột cũ.
- Batch job, report, view hoặc stored procedure còn phụ thuộc tên cũ.
- ORM mapping chưa được cập nhật.
- Consumer bên ngoài hoặc ETL dùng SQL trực tiếp.
- Rollback ứng dụng cũ không tương thích schema mới.

Ví dụ rename trực tiếp:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customers-040-rename-display-name
      author: database-team
      changes:
        - renameColumn:
            schemaName: app
            tableName: customers
            oldColumnName: display_name
            newColumnName: full_name
            columnDataType: VARCHAR(160)
~~~

Thay đổi trực tiếp có thể phù hợp khi downtime được chấp nhận và mọi consumer được triển khai đồng bộ. Với deployment rolling hoặc nhiều service, nên dùng expand-contract:

1. Thêm cột mới full_name.
2. Deploy ứng dụng ghi/đọc tương thích cả hai cột.
3. Backfill full_name từ display_name.
4. Đồng bộ các ghi mới trong giai đoạn chuyển tiếp.
5. Xác minh hai cột nhất quán.
6. Chuyển toàn bộ consumer sang full_name.
7. Chờ phiên bản cũ và job cũ ngừng hoạt động.
8. Drop display_name trong một release sau.

**Không drop cột cũ trong cùng release mà ứng dụng cũ còn cần nó.** Rollback ứng dụng không thể khôi phục cột đã bị drop nếu migration phá hủy đã chạy.

## 8. Expand-contract cho thay đổi phá vỡ tương thích

Mô hình expand-contract đặc biệt hữu ích khi schema và ứng dụng được triển khai ở các thời điểm khác nhau.

~~~text
Giai đoạn 1: EXPAND
  Thêm cấu trúc mới, giữ cấu trúc cũ
          |
          v
Giai đoạn 2: COMPATIBLE APP
  Ứng dụng mới đọc/ghi tương thích cả hai
          |
          v
Giai đoạn 3: MIGRATE
  Backfill và xác minh dữ liệu
          |
          v
Giai đoạn 4: SWITCH
  Chuyển consumer sang cấu trúc mới
          |
          v
Giai đoạn 5: CONTRACT
  Loại bỏ cấu trúc cũ sau khi không còn sử dụng
~~~

Mỗi giai đoạn có thể cần một changeset hoặc một bản phát hành riêng. Không cần cố gắng hoàn thành mọi thứ trong một transaction nếu việc đó tạo lock dài hoặc làm rollout không tương thích.

### 8.1. Tương thích ngược và xuôi

Trong giai đoạn rolling deployment:

- Ứng dụng cũ có thể đang chạy trên schema đã expand.
- Ứng dụng mới có thể đọc dữ liệu cũ và mới.
- Backfill có thể đang chạy song song với traffic.
- Một rollback ứng dụng có thể đưa code cũ quay lại nhưng schema mới vẫn còn.

Vì vậy, mỗi thay đổi cần xác định **phiên bản ứng dụng thấp nhất có thể chạy với schema mới** và **schema thấp nhất mà phiên bản ứng dụng mới hỗ trợ**. Chỉ contract khi không còn consumer cần cấu trúc cũ.

### 8.2. Khi nào không cần expand-contract?

Với database nhỏ, ứng dụng có downtime, release đồng bộ và rollback rõ, một changeset rename/alter trực tiếp có thể đủ. Quyết định dựa trên thời gian khóa, dữ liệu, dependency và chiến lược rollout, không phải áp dụng expand-contract máy móc cho mọi DDL.

## 9. Rà soát thứ tự DROP và dependency khi cleanup

Các thao tác xóa nên được lập danh sách dependency ngược. Ví dụ:

~~~text
Trigger / view / procedure sử dụng bảng
                  |
                  v
Foreign key và constraint phụ thuộc
                  |
                  v
Bảng con
                  |
                  v
Bảng cha / sequence độc lập
~~~

Thứ tự cụ thể tùy dependency thực tế. Có sequence được sở hữu bởi cột, có sequence độc lập được nhiều bảng sử dụng; không drop sequence trước khi xác nhận ownership và consumer.

Ví dụ drop constraint trước khi drop bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: cleanup-010-drop-orders-fk
      author: database-team
      changes:
        - dropForeignKeyConstraint:
            baseTableSchemaName: app
            baseTableName: orders
            constraintName: fk_orders_customers

  - changeSet:
      id: cleanup-011-drop-orders-table
      author: database-team
      changes:
        - dropTable:
            schemaName: app
            tableName: orders
~~~

Đây là ví dụ cleanup trên môi trường có kế hoạch xóa bảng và dữ liệu được phê duyệt. Nếu bảng còn dữ liệu cần giữ, phải archive/export/verify trước khi drop. Không dùng cascade để làm cho changelog chạy qua mà không biết đối tượng nào sẽ bị xóa theo.

### 9.1. Consumer có thể không nằm trong database

Một cột có thể được dùng bởi:

- Ứng dụng Spring Boot hoặc service khác.
- BI/reporting, ETL, data warehouse.
- Stored procedure bên ngoài schema ứng dụng.
- Job định kỳ, script quản trị hoặc công cụ vận hành.
- CDC, replication, logical decoding hoặc hệ thống đồng bộ.
- Người dùng phân tích truy vấn trực tiếp.

Catalog database không thể liệt kê đầy đủ mọi consumer bên ngoài. Review cần kết hợp tìm kiếm repository, telemetry, query logs và xác nhận chủ sở hữu hệ thống.

## 10. Index và constraint: xem cả thứ tự lẫn thời gian triển khai

Tạo index có thể giúp truy vấn nhưng tiêu thụ tài nguyên và ảnh hưởng ghi. Thêm unique constraint hoặc foreign key trên bảng lớn có thể cần quét dữ liệu và giữ lock tùy DBMS.

Trước khi tạo unique index:

~~~sql
SELECT normalized_email, COUNT(*) AS duplicate_count
FROM app.customer
GROUP BY normalized_email
HAVING COUNT(*) > 1;
~~~

Truy vấn chỉ minh họa; cần xác định NULL, collation, case sensitivity và cách normalize giống với định nghĩa unique index. Nếu có duplicate, migration thêm unique constraint có thể thất bại.

### 10.1. Tạo index online/concurrently

Một số DBMS có chế độ tạo index giảm thời gian chặn ghi. Ví dụ PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY nhưng lệnh này không được chạy trong transaction block và có thể để lại invalid index khi thất bại.

Một changeset Liquibase minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-050-create-open-index
      author: database-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE INDEX CONCURRENTLY idx_orders_open_created
              ON app.orders (created_at)
              WHERE status = 'OPEN';
      rollback:
        - sql:
            splitStatements: false
            sql: |
              DROP INDEX CONCURRENTLY app.idx_orders_open_created;
~~~

Ví dụ dành riêng PostgreSQL. Trước khi chạy cần kiểm tra bảng, cột, index trùng tên/invalid, thời gian, tài nguyên và trạng thái sau thực thi. Vì changeset không chạy trong transaction, phải lập kế hoạch phục hồi nếu SQL thất bại một phần.

### 10.2. Thêm foreign key sau khi dữ liệu đã được làm sạch

Trước khi thêm FK, kiểm tra orphan rows:

~~~sql
SELECT COUNT(*) AS orphan_count
FROM app.orders o
LEFT JOIN app.customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Nếu DBMS cho phép thêm constraint ở chế độ chưa validate hoặc validate sau, có thể sử dụng chiến lược nhiều giai đoạn để giảm ảnh hưởng. Nhưng cú pháp và semantics khác nhau giữa PostgreSQL, Oracle và các DBMS khác; cần kiểm tra tài liệu engine và Liquibase change type.

## 11. Transaction, auto-commit, lock và thời gian chạy DDL

Một thay đổi có rollback cú pháp chưa chắc có thể rollback bằng transaction. DDL có hành vi khác nhau giữa DBMS:

- PostgreSQL hỗ trợ transaction cho nhiều thao tác DDL, nhưng có ngoại lệ như CREATE INDEX CONCURRENTLY.
- MySQL có nhiều DDL gây implicit commit; khả năng atomic DDL tùy phiên bản và loại thao tác.
- Oracle DDL thường có implicit commit trước/sau theo quy tắc của engine.
- SQL Server hỗ trợ transaction cho nhiều thao tác DDL, nhưng vẫn phải kiểm tra từng lệnh, lock và tính năng cụ thể.

Đây là khái quát; không thay thế kiểm tra đúng phiên bản DBMS. Cần xác định:

1. Liquibase có chạy changeset trong transaction không?
2. DDL có tự commit hoặc bị cấm trong transaction không?
3. Nếu statement thứ hai thất bại, statement thứ nhất còn hiệu lực không?
4. Lock được giữ trong bao lâu và có chặn traffic không?
5. Có timeout, deadlock hoặc lock queue không?
6. Dung lượng transaction log/WAL/temp đủ không?
7. Có replication lag hoặc ảnh hưởng CDC không?
8. Có thể retry an toàn không?

### 11.1. Chia changeset theo ranh giới phục hồi

Một changeset có nhiều thao tác phụ thuộc có thể khó phục hồi nếu DBMS không hỗ trợ transaction. Chia theo đơn vị có hậu điều kiện rõ:

- Changeset A tạo đối tượng mới.
- Kiểm tra A thành công.
- Changeset B chuyển dữ liệu.
- Kiểm tra dữ liệu.
- Changeset C thêm constraint.
- Kiểm tra constraint và ứng dụng.

Không chia máy móc nếu transaction nguyên tử là yêu cầu; hãy thiết kế ranh giới theo khả năng thực tế của DBMS.

## 12. Khả năng rollback trong Liquibase

Rollback là khả năng đưa database về trạng thái trước một hoặc nhiều changeset theo logic đảo ngược được định nghĩa. Có ba trường hợp:

1. **Automatic rollback:** Liquibase có thể tạo rollback cho một số change type được hỗ trợ.
2. **Explicit rollback:** người viết khai báo các change/sql đảo ngược tường minh.
3. **No safe rollback:** thay đổi mất dữ liệu hoặc không có thông tin trạng thái trước; cần backup/restore hoặc forward-fix.

Không được giả định mọi change type đều có rollback tự động trên mọi DBMS. Raw sql/sqlFile thường cần rollback tường minh nếu muốn Liquibase biết cách đảo ngược.

### 12.1. Ví dụ rollback cho thay đổi có thể đảo ngược

Tạo index thông thường:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-060-add-created-index
      author: database-team
      changes:
        - createIndex:
            schemaName: app
            tableName: orders
            indexName: idx_orders_created_at
            columns:
              - column:
                  name: created_at
      rollback:
        - dropIndex:
            schemaName: app
            tableName: orders
            indexName: idx_orders_created_at
~~~

Rollback drop index có thể phù hợp nếu index được tạo bởi changeset này và không có dependency cần giữ. Nhưng nó không khôi phục dữ liệu bị ảnh hưởng bởi một thao tác khác. Trước khi rollback cần xác định đúng tag/changeset và xem SQL thực tế.

### 12.2. Ví dụ rollback cho thêm cột

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customers-061-add-middle-name
      author: database-team
      changes:
        - addColumn:
            schemaName: app
            tableName: customers
            columns:
              - column:
                  name: middle_name
                  type: VARCHAR(80)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: customers
            columnName: middle_name
~~~

Rollback này sẽ xóa cột và mọi dữ liệu được ghi vào cột đó kể từ lúc triển khai. Vì vậy, mặc dù DDL đảo ngược được, **dữ liệu trong cột không được khôi phục** nếu không có bản sao. Trên hệ thống đã ghi dữ liệu thật vào cột mới, rollback có thể không còn an toàn.

### 12.3. Rollback DML cần lưu trạng thái trước

Ví dụ UPDATE chuyển status từ OLD sang NEW. Rollback đơn giản đổi NEW về OLD có thể ghi đè những thay đổi hợp lệ phát sinh sau migration. Nếu cần đảo ngược, phải biết dòng nào được migration thay đổi và giá trị cũ của từng dòng.

Có thể cần bảng audit/staging, snapshot hoặc một mapping khóa → giá trị cũ. Nếu không thể phục hồi trạng thái chính xác, hãy lập forward-fix thay vì giả định câu SQL ngược là đủ.

## 13. Khi rollback không phải lựa chọn an toàn: forward-fix và restore

Một số thay đổi không thể đảo ngược thực tế:

- DROP TABLE/COLUMN đã xóa dữ liệu.
- UPDATE chuyển đổi mất thông tin gốc.
- Giảm precision làm mất phần thập phân.
- Xóa/ghép bản ghi và không lưu mapping.
- Thay đổi dữ liệu ngoài transaction rồi phát sinh side effect.
- Thay đổi schema đã được phiên bản ứng dụng mới sử dụng và ghi dữ liệu.

Các phương án:

| Phương án | Khi phù hợp | Giới hạn |
|---|---|---|
| Rollback changeset | Có rollback đúng và dữ liệu còn khôi phục được | Có thể xóa dữ liệu mới phát sinh |
| Forward-fix changeset | Cần sửa trạng thái hiện tại tiến về phía trước | Không tự phục hồi dữ liệu đã mất |
| Restore backup/snapshot | Cần khôi phục database hoặc dữ liệu đã mất | Có thể mất giao dịch sau thời điểm backup; cần phối hợp ứng dụng |
| Point-in-time recovery | DBMS/hạ tầng hỗ trợ và có log phù hợp | Cần quy trình vận hành, thời gian và kiểm tra consistency |
| Data repair từ nguồn khác | Có nguồn chuẩn hoặc audit log | Phải chứng minh nguồn và mapping đúng |

**Rollback code không đồng nghĩa rollback database.** Nếu ứng dụng mới đã chạy trên schema mới, quay lại binary cũ có thể không tương thích. Cần phối hợp rollback ứng dụng, database, message/event và dữ liệu.

## 14. Review rollback-sql và phạm vi rollback

Trước khi rollback, xem SQL sẽ thực thi. Ví dụ Liquibase có thể hỗ trợ lệnh preview rollback theo tag hoặc số changeset tùy phiên bản và cấu hình:

~~~bash
liquibase rollback-sql --tag=before-schema-change
~~~

Sau khi review, mới quyết định chạy rollback tương ứng. Cú pháp chính xác và cách quản lý tag phải xác nhận với phiên bản CLI trong dự án.

Checklist khi review:

- Tag hoặc phạm vi rollback đúng chưa?
- Có changeset nào không có rollback?
- Thứ tự đảo ngược dependency có đúng không?
- SQL có DROP/DELETE hoặc xóa dữ liệu mới không?
- DBMS có cho chạy DDL trong transaction không?
- Ứng dụng đang chạy có còn phụ thuộc đối tượng sắp bị xóa không?
- Có backup/snapshot và phương án phục hồi không?
- Rollback có cần tắt writer hoặc phối hợp job khác không?
- Sau rollback, schema và dữ liệu được xác minh thế nào?

Không chạy rollback trên production chỉ vì update trước đó báo lỗi. Trước hết phải biết changeset nào đã hoàn thành, DDL nào đã commit và trạng thái thực tế của database.

## 15. Precondition và hậu điều kiện khi review DDL

Precondition xác nhận giả định trước khi changeset chạy. Ví dụ trước khi drop cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: cleanup-070-drop-obsolete-column
      author: database-team
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: customers
        - columnExists:
            schemaName: app
            tableName: customers
            columnName: obsolete_code
      changes:
        - dropColumn:
            schemaName: app
            tableName: customers
            columnName: obsolete_code
~~~

Precondition này chỉ chứng minh bảng và cột tồn tại. Nó **không chứng minh cột không còn được ứng dụng dùng, dữ liệu đã archive hay rollback có thể phục hồi**. Cần kiểm tra dependency ở application, report, ETL, job và catalog.

Hậu điều kiện nên xác minh sau khi chạy:

- Cột/constraint/index có trạng thái mong muốn.
- Dữ liệu không vi phạm invariant.
- Các foreign key còn hợp lệ.
- Ứng dụng đọc/ghi được.
- Không có dependency cũ còn hoạt động.
- Changeset được ghi nhận đúng trong DATABASECHANGELOG.

Không dùng MARK_RAN để vượt qua precondition của thao tác bắt buộc. MARK_RAN có thể ghi nhận changeset mà không thực thi SQL, khiến history không tương ứng với trạng thái schema mong đợi.

## 16. So sánh schema trước và sau bằng Liquibase diff

Trong chương So sánh lược đồ, cần biết công cụ diff hỗ trợ review nhưng không thay thế phân tích rủi ro DDL.

Một quy trình tham khảo:

1. Chuẩn bị reference database/snapshot phản ánh schema mong muốn.
2. Chuẩn bị target database hiện tại.
3. Chạy diff với đúng driver, schema/catalog và object filters.
4. Phân tích khác biệt: bảng, cột, type, constraint, index, sequence, view.
5. Chỉ tạo changelog từ diff sau khi review và chỉnh sửa.
6. Kiểm tra thứ tự dependency, dữ liệu và rollback trước khi triển khai.

Ví dụ lệnh dạng khái niệm:

~~~bash
liquibase diff
liquibase diff-changelog
~~~

Tên command, cách truyền reference/target URL và tham số có thể thay đổi theo phiên bản/edition. Cần dùng help của CLI thực tế và đảm bảo credentials được lấy từ secret source.

### 16.1. Diff không biết đầy đủ ý định nghiệp vụ

Một diff có thể cho biết cột bị thiếu hoặc type khác, nhưng không thể tự quyết định:

- Cột đó có chứa dữ liệu cần giữ không?
- Rename có đúng hơn drop + add không?
- Thay đổi có tương thích với phiên bản ứng dụng cũ không?
- Index cần tạo concurrently không?
- Constraint có thể validate ngay không?
- Dữ liệu cũ cần backfill thế nào?
- Rollback có phục hồi được dữ liệu không?

Diff là đầu vào cho review, không phải lệnh tự động áp dụng mọi thay đổi lên production.

### 16.2. Cẩn trọng với drop trong diff-generated changelog

Nếu target thiếu một đối tượng có trong reference hoặc ngược lại, diff-changelog có thể tạo thay đổi xóa/đổi tùy chiều so sánh. Cần xác nhận reference và target đúng vai trò trước khi sinh changelog. Không review một generated changelog chỉ bằng cách nhìn tên file.

## 17. Quy trình review DDL trước khi merge

Một pull request migration nên có đủ bằng chứng:

1. **Mục tiêu nghiệp vụ:** thay đổi nào cần thiết và consumer nào sử dụng?
2. **Dependency:** bảng, cột, constraint, index, sequence, view, function và trigger phụ thuộc ra sao?
3. **Thứ tự:** changeset nào phải chạy trước/sau và vì sao?
4. **Dữ liệu:** có truncate, cast, default, backfill, drop hoặc update hàng loạt không?
5. **Lock/hiệu năng:** thời gian chạy dự kiến, kích thước bảng, index, transaction log và timeout?
6. **Compatibility:** ứng dụng cũ và mới có chạy được trong giai đoạn rollout không?
7. **Rollback:** rollback SQL nào, có mất dữ liệu mới không, có backup/forward-fix không?
8. **Precondition:** giả định trước khi chạy được kiểm tra ra sao?
9. **Hậu điều kiện:** truy vấn nào xác minh kết quả?
10. **Môi trường:** DBMS/version nào đã được thử?
11. **Lịch sử:** changeset cũ có bị sửa không? id/author/path ổn định không?
12. **Quyền:** migration role và runtime role có đủ nhưng không quá rộng không?

### 17.1. Mẫu review ngắn

~~~text
Change objective:
Affected objects:
Dependency/order:
Existing data impact:
Lock / runtime estimate:
Application compatibility:
Preconditions:
Expected postconditions:
Rollback SQL / recovery plan:
DBMS and version tested:
Fresh-install test:
Upgrade-path test:
Approver:
~~~

Đây là mẫu review do nhóm có thể áp dụng, không phải file phải tạo trong bài này. Mọi kết luận phải dựa trên dữ liệu và test thực tế; không điền “rollback supported” nếu chưa thử.

## 18. Kiểm chứng trên database rỗng và database có dữ liệu

DDL cần được thử ở hai trạng thái:

### Fresh database

- Tạo database/schema thử nghiệm mới.
- Chạy toàn bộ root changelog.
- Xác minh thứ tự, dependency và schema cuối.
- Kiểm tra reference data và đối tượng.
- Chạy update lần hai để kiểm tra tính ổn định.

### Database đã có lịch sử và dữ liệu

- Khôi phục snapshot/fixture đại diện có kích thước và phân bố gần thực tế.
- Chạy status và update-sql.
- Kiểm tra điều kiện dữ liệu trước DDL.
- Đo thời gian, lock, dung lượng và tác động ghi.
- Thực thi migration và hậu kiểm.
- Thử rollback/forward-fix trên bản sao có thể bỏ.
- Xác minh các phiên bản ứng dụng cũ/mới.

Một migration chạy thành công trên database rỗng **không chứng minh** nó an toàn với bảng hàng triệu dòng. Ngược lại, migration trên database có lịch sử cũ cũng không chứng minh root changelog có thể dựng mới database.

## 19. Spring Boot và rolling deployment

Khi Spring Boot chạy Liquibase lúc khởi động, thay đổi DDL có thể diễn ra trong lúc nhiều instance hoặc phiên bản ứng dụng đang được rollout. Cần quyết định:

- Migration chạy trong startup hay job riêng.
- Có bao nhiêu tiến trình được phép chạy Liquibase.
- Phiên bản ứng dụng cũ có tương thích schema sau expand không.
- Phiên bản mới có chạy được trước khi contract không.
- Nếu ứng dụng rollback, schema còn giữ cấu trúc tương thích không.
- Connection pool, startup timeout và lock behavior được kiểm soát ra sao.

Ví dụ cấu hình:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Đây chỉ là cấu hình tối thiểu. Trong môi trường production cần cấu hình database, credentials, profile, context, quyền và cách điều phối migration. Nhiều instance dùng cùng DATABASECHANGELOGLOCK có thể được Liquibase điều phối, nhưng điều đó không thay thế việc bảo đảm artifact và root changelog nhất quán.

Với thay đổi phá vỡ tương thích, nên cân nhắc migration job riêng, sau đó rollout ứng dụng tương thích, rồi contract ở release sau khi mọi consumer đã chuyển đổi.

## 20. CI/CD: kiểm soát thứ tự, dữ liệu và rollback bằng cổng kiểm tra

Một pipeline có thể áp dụng các bước:

~~~text
Pull request
    |
    v
Review changeset / dependency / destructive operations
    |
    v
Validate changelog
    |
    v
Test fresh database
    |
    v
Test upgrade database có dữ liệu đại diện
    |
    v
Review update-sql + lock / transaction
    |
    v
Review rollback-sql hoặc recovery plan
    |
    v
Phê duyệt triển khai
    |
    v
Update trên môi trường mục tiêu
    |
    v
Hậu kiểm schema + data + application
~~~

Các cổng tự động có thể:

- Phát hiện changeset cũ bị sửa/xóa/đổi định danh.
- Đánh dấu DROP, TRUNCATE, DROP COLUMN, giảm precision hoặc DELETE không có WHERE để review đặc biệt.
- Kiểm tra include order và dependency đã biết.
- Chạy validate, status và update-sql.
- Tạo database test sạch cho fresh install.
- Dùng bản sao dữ liệu synthetic/đã xử lý để thử migration trên bảng lớn.
- Kiểm tra số hàng trước/sau và invariant.
- Xác nhận có rollback hoặc recovery plan.
- Kiểm tra smoke test ứng dụng và các consumer quan trọng.
- Lưu log, commit, artifact, phiên bản Liquibase và kết quả đã redacted.

Không dựa hoàn toàn vào regex để xác định DDL an toàn. SQL có thể được viết qua sqlFile, stored procedure hoặc câu lệnh động; review người có chuyên môn vẫn cần thiết.

## 21. Những lỗi thường gặp khi rà soát thứ tự và rollback

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| FK tạo thất bại | Bảng/cột tham chiếu chưa tồn tại hoặc dữ liệu orphan | Sắp xếp dependency và kiểm tra dữ liệu trước constraint |
| ADD NOT NULL thất bại | Bảng có NULL | Backfill, validate rồi enforce |
| ALTER TYPE timeout | Rewrite/scan bảng hoặc lock lâu | Thử trên dữ liệu đại diện, chia bước hoặc dùng online strategy |
| DROP COLUMN làm ứng dụng lỗi | Consumer cũ vẫn dùng cột | Expand-contract, telemetry và chờ rollout hoàn tất |
| Unique constraint thất bại | Dữ liệu duplicate | Phân tích và xử lý duplicate có quy tắc nghiệp vụ |
| Rollback thêm cột làm mất dữ liệu | Rollback drop cột mới đã có ghi dữ liệu | Backup/forward-fix; không rollback mù |
| Rollback DML không khôi phục giá trị cũ | Không lưu trạng thái trước | Audit/snapshot hoặc forward-fix |
| Index concurrent bị invalid | CREATE INDEX CONCURRENTLY thất bại | Kiểm tra catalog và xử lý invalid index trước retry |
| Migration lỗi nhưng có DDL đã commit | DBMS không rollback DDL hoặc runInTransaction=false | Kiểm tra trạng thái thật trước retry |
| Diff sinh DROP không mong muốn | Chọn sai reference/target hoặc filter | Xác minh chiều diff và review từng thay đổi |
| Update lần hai tạo dữ liệu trùng | runAlways/seed không idempotent | Tách seed, kiểm soát unique key và cleanup |
| Checksum mismatch sau refactor | Sửa changeset đã triển khai hoặc đổi resource | Khôi phục history và tạo changeset mới |
| Chạy được trên H2 nhưng lỗi production | DBMS semantics khác | Test trên engine/version đại diện production |

## 22. Bài thực hành: review một migration có nguy cơ mất dữ liệu

**Điều kiện:** database thử nghiệm riêng, không chứa dữ liệu thật, có thể tạo lại. Bài tập không chạy trên production.

### Bước 1. Tạo trạng thái ban đầu

Tạo bảng orders có dữ liệu đại diện:

~~~sql
CREATE TABLE app.orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(40),
    legacy_code VARCHAR(30)
);

INSERT INTO app.orders (id, status, legacy_code)
VALUES
    (1, 'NEW', 'A-001'),
    (2, NULL, 'A-002'),
    (3, 'PAID', 'A-003');
~~~

Cú pháp DDL và quyền tạo schema phụ thuộc DBMS; chỉ dùng trên lab. Ghi nhận số dòng, NULL và giá trị hiện tại.

### Bước 2. Review thay đổi nguy hiểm

Yêu cầu giả định: đổi status thành NOT NULL, đổi độ dài xuống VARCHAR(10), rồi drop legacy_code.

Không chạy ngay. Phân tích:

- Có bao nhiêu dòng status NULL?
- Có giá trị status nào dài hơn 10 ký tự không?
- legacy_code có consumer nào không?
- Nếu drop cột, rollback có khôi phục nội dung A-001/A-002/A-003 không?
- DDL có lock/rewrite bảng không?
- Ứng dụng cũ có đang ghi legacy_code không?

Ví dụ truy vấn kiểm tra:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM app.orders
WHERE status IS NULL;

SELECT MAX(CHAR_LENGTH(status)) AS max_status_length
FROM app.orders;
~~~

Nếu DBMS dùng hàm khác cho độ dài chuỗi, điều chỉnh truy vấn theo engine. Đọc kết quả và kết luận thay đổi nào phải tách bước.

### Bước 3. Thiết kế expand/backfill/constraint

Thay vì thay đổi phá hủy ngay, thêm hoặc sửa dữ liệu theo từng bước đã review:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-backfill-status
      author: learner
      changes:
        - sql:
            sql: |
              UPDATE app.orders
              SET status = 'NEW'
              WHERE status IS NULL;

  - changeSet:
      id: lab-002-enforce-status
      author: learner
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.orders
              WHERE status IS NULL
      changes:
        - addNotNullConstraint:
            schemaName: app
            tableName: orders
            columnName: status
            columnDataType: VARCHAR(40)
~~~

Giá trị NEW chỉ là quy tắc ví dụ. Trong hệ thống thực, cần xác nhận giá trị mặc định đúng nghiệp vụ. Backfill hàng loạt có thể cần batch và transaction riêng.

### Bước 4. Đánh giá contract

Chưa drop legacy_code cho đến khi:

- Ứng dụng mới không còn đọc/ghi cột.
- Job/report/ETL không còn sử dụng.
- Backfill hoặc archive dữ liệu cần giữ đã hoàn tất.
- Đã quan sát traffic trong thời gian đủ đại diện.
- Rollback ứng dụng không cần cột cũ.
- Có phương án phục hồi nếu phát hiện consumer trễ.

Sau đó mới tạo changeset drop cột riêng với precondition và kế hoạch lưu dữ liệu nếu cần.

### Bước 5. Xem update-sql và rollback-sql

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Review SQL theo đúng DBMS. Xem rollback SQL cho từng changeset hoặc xác định rõ thay đổi nào không có rollback tự động. Nếu không thể khôi phục dữ liệu gốc, ghi recovery plan thay vì đánh dấu rollback an toàn.

### Bước 6. Kiểm tra sau triển khai

- Cột status không còn NULL.
- Dữ liệu status không bị cắt hoặc đổi ngoài quy tắc.
- Số dòng orders giữ nguyên nếu không có yêu cầu xóa.
- Constraint NOT NULL tồn tại.
- legacy_code chỉ bị loại bỏ khi đã được phê duyệt.
- Ứng dụng đọc/ghi bình thường.
- DATABASECHANGELOG ghi nhận changeset theo đúng thứ tự.
- Rollback/forward-fix đã được thử trên bản sao lab.

## 23. Checklist cuối cùng cho reviewer DDL

- [ ] Đã xác định dependency giữa schema, bảng, cột, sequence, constraint, index, view, function và trigger.
- [ ] Changeset được sắp xếp theo dependency; cleanup theo chiều ngược.
- [ ] Đã kiểm tra bảng có dữ liệu hay không và dữ liệu có vi phạm constraint mới không.
- [ ] Đã phân tích DROP, TRUNCATE, DELETE, thu hẹp kiểu, rename và thay đổi default.
- [ ] Đã đánh giá lock, rewrite, transaction log, timeout và tác động replication.
- [ ] Đã xác định ứng dụng cũ/mới, job, report và consumer ngoài database có tương thích không.
- [ ] Với thay đổi phá vỡ tương thích, đã có expand-contract và rollout nhiều bước.
- [ ] Precondition kiểm tra đúng giả định; không dùng MARK_RAN để che trạng thái sai.
- [ ] Hậu điều kiện xác minh schema, dữ liệu và hành vi ứng dụng.
- [ ] Rollback đã được review theo DBMS, không chỉ dựa vào tên change type.
- [ ] Dữ liệu bị xóa/chuyển đổi có backup, audit hoặc recovery plan phù hợp.
- [ ] Đã thử update-sql, rollback-sql hoặc phương án forward-fix trên database tương đương.
- [ ] Fresh-install và upgrade-path test đều đạt.
- [ ] Không sửa changeset đã triển khai; thay đổi mới có changeset mới và checksum/history nhất quán.
- [ ] CI/CD lưu artifact, log, exit code và bằng chứng hậu kiểm.
- [ ] Người chịu trách nhiệm dữ liệu và ứng dụng đã review tác động trước khi triển khai production.

## 24. Kết luận

Rà soát DDL phải bắt đầu từ **dependency và thứ tự**, tiếp tục bằng phân tích dữ liệu, lock, transaction và compatibility, rồi mới quyết định cách triển khai và phục hồi. Tạo đối tượng theo thứ tự phụ thuộc, xóa theo chiều ngược; kiểm tra dữ liệu trước khi thêm constraint hoặc thu hẹp kiểu; dùng expand-contract khi ứng dụng và database được rollout khác thời điểm.

Rollback phải được đánh giá theo khả năng khôi phục dữ liệu thật, không chỉ theo việc có thể viết câu SQL ngược. Với thao tác phá hủy hoặc không transactional, cần backup, forward-fix hoặc quy trình restore được thử nghiệm. Kết hợp Liquibase precondition, checksum, update-sql, diff, hậu kiểm schema/data và CI/CD trên DBMS đại diện sẽ giúp migration có thứ tự rõ ràng, hạn chế mất dữ liệu và có phương án phục hồi phù hợp.
