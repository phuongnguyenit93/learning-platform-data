# Chọn change type dùng chung và SQL đặc thù

## 1. Mục tiêu và bối cảnh

Liquibase hỗ trợ nhiều hệ quản trị cơ sở dữ liệu (DBMS), nhưng không phải mọi câu lệnh SQL đều có cùng cú pháp hoặc cùng hành vi trên PostgreSQL, MySQL, MariaDB, SQL Server, Oracle và H2. Một migration tạo bảng, thêm cột hay tạo khóa ngoại thường có thể diễn đạt bằng **change type** của Liquibase. Trong khi đó, một thao tác như tạo index theo chế độ online, khai báo function, cấu hình extension hoặc dùng cú pháp đặc thù của một DBMS có thể cần **SQL trực tiếp**.

Lựa chọn sai làm changelog khó bảo trì theo hai hướng. Nếu viết toàn bộ bằng SQL của một DBMS, nhóm mất khả năng triển khai trên các hệ quản trị khác. Nếu cố ép mọi tính năng vào change type dùng chung, có thể không biểu đạt được hành vi cần thiết hoặc vô tình bỏ qua một khác biệt quan trọng giữa các DBMS.

Bài thuộc chương **Nhiều cơ sở dữ liệu** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào cách **chọn change type dùng chung và SQL đặc thù** để cân bằng tính khả chuyển, độ chính xác và khả năng kiểm soát khi một sản phẩm hỗ trợ nhiều DBMS.

Sau bài học, bạn cần có thể:

1. Phân biệt change type dùng chung, change type có giới hạn DBMS và SQL đặc thù.
2. Chọn change type cho DDL/DML phổ biến và nhận diện khi nào cần SQL riêng.
3. Tổ chức changeset theo DBMS mà không làm sai lịch sử triển khai.
4. Quản lý SQL trong YAML, SQL file và formatted SQL changelog.
5. Cấu hình delimiter, splitStatements và transaction phù hợp với function, procedure hoặc DDL đặc biệt.
6. Viết precondition, rollback và quy tắc kiểm thử cho từng DBMS.
7. Kiểm tra SQL được sinh ra trên đúng phiên bản DBMS, JDBC driver và Liquibase.
8. Đưa ma trận DBMS vào CI/CD và giữ changelog có thể truy vết.

## 2. Nguyên tắc chọn cách biểu diễn

Hãy chọn **cách diễn đạt rõ nhất cho ý định migration**, sau đó mới tối ưu tính ngắn gọn.

Một thứ tự cân nhắc thực tế:

1. **Change type dùng chung** nếu Liquibase biểu diễn đúng ý định và các DBMS mục tiêu hỗ trợ hành vi tương đương.
2. **Change type kết hợp thuộc tính DBMS** nếu change type có sẵn nhưng chỉ phù hợp một số hệ quản trị hoặc cần tùy chỉnh.
3. **SQL đặc thù theo DBMS** nếu tính năng, cú pháp hoặc hành vi không thể diễn đạt chính xác bằng change type.
4. **Job/bootstrap do nền tảng quản lý** nếu thao tác liên quan tới tài khoản hạ tầng, extension, quyền quản trị hoặc cấu hình toàn database không nên thuộc vòng đời schema của ứng dụng.

Không chọn change type chỉ vì nó có tên giống câu SQL đang cần. Cần kiểm tra SQL mà Liquibase sinh ra và hành vi thực tế trên DBMS mục tiêu.

### 2.1. Change type không đồng nghĩa một câu SQL cố định

Ví dụ createTable có thể được Liquibase chuyển thành cú pháp tạo bảng phù hợp với từng DBMS. Nhưng kết quả cụ thể còn phụ thuộc:

- Phiên bản Liquibase.
- DBMS và phiên bản DBMS.
- JDBC driver.
- Kiểu dữ liệu và thuộc tính được khai báo.
- Schema/catalog mặc định.
- Các giới hạn hoặc tính năng mà DBMS hỗ trợ.

Do đó, change type giúp **trừu tượng hóa một phần khác biệt**, không cam kết mọi DBMS có cùng khả năng hoặc cùng hiệu năng.

### 2.2. SQL đặc thù không phải lựa chọn xấu

SQL trực tiếp phù hợp khi nhóm cần một tính năng vendor-specific hoặc phải kiểm soát chính xác câu lệnh được gửi đến DBMS. Ví dụ: PostgreSQL CREATE INDEX CONCURRENTLY, SQL Server ONLINE = ON trong một số thao tác index được hỗ trợ, hoặc PL/SQL block của Oracle.

Điều quan trọng là ghi rõ phạm vi DBMS, giải thích lý do, review SQL sinh ra, thử trên đúng phiên bản và có cách xử lý rollback/thất bại.

## 3. Bảng quyết định: dùng change type hay SQL?

| Nhu cầu | Lựa chọn ưu tiên | Khi nào dùng SQL riêng? |
|---|---|---|
| Tạo bảng, cột | createTable, addColumn | Cần table option, storage clause hoặc cú pháp riêng |
| Thêm khóa chính/ngoại | addPrimaryKey, addForeignKeyConstraint | DBMS cần thao tác đặc thù hoặc online validation |
| Thêm unique/check/not-null | addUniqueConstraint, addNotNullConstraint, addCheckConstraint nếu phiên bản hỗ trợ | Cần cú pháp riêng, trạng thái validate hoặc constraint option đặc biệt |
| Tạo index | createIndex | Cần concurrent/online, partial index hoặc index method đặc thù |
| Thay đổi kiểu dữ liệu | modifyDataType hoặc change type phù hợp | Cần cast, using expression, collation hoặc conversion đặc thù |
| Thêm/cập nhật dữ liệu | insert, update, delete, loadData | Cần upsert, merge, CTE hoặc hàm DBMS |
| Tạo sequence | createSequence | Cần tùy chọn cache/cycle/order hoặc cơ chế riêng |
| Tạo view | createView hoặc sql | Định nghĩa dùng cú pháp riêng hoặc cần tùy chọn DBMS |
| Function/procedure/trigger | Change type nếu có và phù hợp; nếu không, sql/sqlFile | Thường cần SQL/PL/SQL riêng và delimiter phù hợp |
| Cấp quyền | sql hoặc SQL file | GRANT/REVOKE có mô hình khác nhau theo DBMS |
| Extension/plugin | Quy trình bootstrap hoặc SQL đặc thù | Cần quyền quản trị, cài đặt trên server hoặc phối hợp DBA |

Tên change type và thuộc tính khả dụng có thể thay đổi theo phiên bản Liquibase. Trước khi chọn, hãy kiểm tra tài liệu đúng phiên bản và thử trên từng DBMS được công bố hỗ trợ.

## 4. Change type dùng chung cho schema phổ biến

### 4.1. Ví dụ tạo bảng và ràng buộc

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: platform-team
      changes:
        - createTable:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: customer_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_customer
                    nullable: false
              - column:
                  name: display_name
                  type: VARCHAR(150)
                  constraints:
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(255)
      rollback:
        - dropTable:
            schemaName: app
            tableName: customer
~~~

Ví dụ này diễn đạt ý định tạo bảng, khóa chính và cột bắt buộc mà không viết câu CREATE TABLE cho từng DBMS. Liquibase sẽ sinh SQL phù hợp với những DBMS và kiểu dữ liệu mà phiên bản đang dùng hỗ trợ.

Tuy nhiên, rollback dropTable sẽ xóa cả dữ liệu trong bảng. Nó phù hợp với bài tập hoặc một bảng mới chưa chứa dữ liệu cần giữ; production cần đánh giá backup và khả năng phục hồi trước khi dùng.

### 4.2. Ví dụ thêm cột và index

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-customer-created-at
      author: platform-team
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: created_at
                  type: TIMESTAMP
        - createIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_created_at
            columns:
              - column:
                  name: created_at
      rollback:
        - dropIndex:
            schemaName: app
            tableName: customer
            indexName: ix_customer_created_at
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: created_at
~~~

Tách thành hai changeset có thể phù hợp hơn nếu cần phát hành cột và index ở các thời điểm khác nhau hoặc nếu index phải được tạo bằng một kỹ thuật online riêng. Cũng cần kiểm tra cột đã tồn tại chưa, dữ liệu mặc định, thời gian khóa và khả năng rollback.

### 4.3. Ví dụ DML có cấu trúc

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 003-insert-order-status
      author: platform-team
      changes:
        - insert:
            schemaName: app
            tableName: order_status
            columns:
              - column:
                  name: code
                  value: ACTIVE
              - column:
                  name: display_name
                  value: Đang hoạt động
      rollback:
        - delete:
            schemaName: app
            tableName: order_status
            where: "code = 'ACTIVE'"
~~~

Change type có cấu trúc giúp Liquibase biết bảng và các cột được thao tác, đồng thời xử lý một số khác biệt về SQL và kiểu dữ liệu. Tuy vậy, rollback delete chỉ an toàn nếu dòng ACTIVE do chính changeset tạo và không bị thay đổi hoặc được tham chiếu theo cách khiến việc xóa gây mất dữ liệu.

Không nên dùng change type chung cho một câu upsert phức tạp nếu hành vi conflict của DBMS khác nhau và không thể diễn đạt đúng. Khi đó, hãy tách SQL theo DBMS hoặc dùng một quy trình dữ liệu riêng.

## 5. Chọn kiểu dữ liệu có tính khả chuyển

Một trong những nguồn khác biệt lớn nhất là kiểu dữ liệu. Liquibase cho phép khai báo kiểu trong change type, nhưng **tên kiểu không bảo đảm cùng dung lượng, cách làm tròn hoặc ngữ nghĩa ở mọi DBMS**.

| Ý định dữ liệu | Kiểu thường cân nhắc | Điểm cần xác minh |
|---|---|---|
| Số nguyên lớn | BIGINT | Giới hạn, identity/auto increment |
| Số tiền | DECIMAL(p,s) hoặc NUMERIC(p,s) | Độ chính xác, scale và phép tính |
| Chuỗi ngắn | VARCHAR(n) | Đơn vị ký tự/byte, giới hạn tối đa |
| Văn bản dài | CLOB, TEXT hoặc kiểu phù hợp | Mapping theo DBMS, khả năng index |
| Ngày giờ | DATE, TIMESTAMP | Time zone, độ chính xác, cách lưu |
| Boolean | BOOLEAN hoặc kiểu tương đương | DBMS có kiểu boolean thật hay mapping khác |
| UUID | UUID hoặc kiểu tương đương | Hỗ trợ native, representation, index |
| JSON | JSON, JSONB hoặc kiểu văn bản | Khả năng query, index, validation và semantics |
| Nhị phân | BLOB, BYTEA hoặc kiểu tương ứng | Giới hạn kích thước và lưu trữ |

Ví dụ BOOLEAN có thể được hỗ trợ trực tiếp ở một DBMS nhưng được ánh xạ sang dạng khác ở DBMS khác. TIMESTAMP có thể không biểu diễn cùng một ngữ nghĩa về múi giờ. JSON và JSONB của PostgreSQL có đặc tính khác nhau; không nên thay thế lẫn nhau chỉ vì cùng lưu dữ liệu JSON.

### 5.1. Chọn kiểu theo ý nghĩa, không theo tên

Trước khi chọn kiểu, trả lời:

- Dữ liệu có thể vượt phạm vi số nguyên nào?
- Có cần giữ độ chính xác thập phân tuyệt đối không?
- Timestamp biểu diễn thời điểm toàn cầu hay thời gian địa phương?
- Chuỗi có thể chứa Unicode và dài bao nhiêu?
- JSON chỉ lưu trữ hay cần truy vấn/index theo thuộc tính?
- Ứng dụng Java ánh xạ kiểu đó thành kiểu nào?
- Tất cả DBMS mục tiêu có thể biểu diễn cùng bất biến dữ liệu không?

Nếu một DBMS không hỗ trợ kiểu mong muốn, có thể chọn một biểu diễn chung hoặc tách migration theo DBMS. Cần kiểm thử chuyển đổi và đọc/ghi dữ liệu qua ứng dụng trên từng hệ quản trị.

## 6. Những khác biệt không thể che bằng change type

Một change type có thể sinh SQL hợp lệ nhưng không bảo đảm hành vi vận hành tương đương. Ví dụ:

- Tạo index thường có thể khóa ghi ở mức khác nhau.
- DDL có thể commit ngầm ở một DBMS nhưng tham gia transaction ở DBMS khác.
- Tạo khóa ngoại có thể kiểm tra toàn bộ dữ liệu ngay hoặc hỗ trợ trạng thái chưa validate tùy hệ quản trị.
- Thay đổi kiểu dữ liệu có thể cần cast expression riêng.
- Identity/sequence có quy tắc cấp phát khác nhau.
- Quyền schema, role và ownership khác nhau.
- Function/procedure và trigger có ngôn ngữ, delimiter và mô hình quyền khác nhau.

Vì vậy, hãy phân biệt **tính khả chuyển cú pháp** với **tính tương đương hành vi**. Một migration chỉ được xem là hỗ trợ đa DBMS khi đã kiểm thử các thuộc tính quan trọng như dữ liệu, ràng buộc, khóa, transaction, hiệu năng và quyền.

## 7. Khi cần SQL đặc thù: tổ chức changeset theo DBMS

Liquibase cho phép giới hạn changeset theo loại DBMS bằng thuộc tính dbms hoặc precondition dbms, tùy cách tổ chức changelog.

Ví dụ cùng mục tiêu tạo index trên bảng app.orders nhưng cách thực thi khác nhau:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 010-orders-index-postgresql
      author: platform-team
      dbms: postgresql
      runInTransaction: false
      changes:
        - sql:
            sql: |
              CREATE INDEX CONCURRENTLY ix_orders_created_at
              ON app.orders (created_at);
      rollback:
        - sql:
            sql: |
              DROP INDEX CONCURRENTLY IF EXISTS app.ix_orders_created_at;

  - changeSet:
      id: 011-orders-index-mysql
      author: platform-team
      dbms: mysql
      changes:
        - sql:
            sql: |
              CREATE INDEX ix_orders_created_at
              ON orders (created_at);
      rollback:
        - sql:
            sql: DROP INDEX ix_orders_created_at ON orders;
~~~

Hai changeset dùng **ID khác nhau**, cùng author và cùng changelog, nhưng mỗi database chỉ áp dụng nhánh tương ứng. Đừng dùng cùng một danh tính changeset cho hai nội dung khác nhau theo DBMS; một database chỉ nên có một định nghĩa ổn định cho một changeset đã được nhận diện.

Ví dụ có các giả định cần kiểm chứng:

- PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY; lệnh này không được chạy trong transaction block, vì vậy runInTransaction: false được đặt cho changeset riêng.
- Nếu lệnh PostgreSQL thất bại, có thể còn index không hợp lệ; cần kiểm tra metadata trước retry và dọn dẹp có kiểm soát.
- MySQL có cú pháp DROP INDEX ... ON table; không thể dùng nguyên lệnh DROP INDEX của PostgreSQL.
- Hỗ trợ online DDL của MySQL phụ thuộc engine, phiên bản và điều kiện cụ thể; ví dụ trên không cam kết tạo index không khóa.
- Cả hai nhánh phải được thử trên đúng phiên bản DBMS và dữ liệu đại diện.

**Không dùng dbms để che một thay đổi bắt buộc khỏi môi trường không hỗ trợ.** Nếu sản phẩm công bố hỗ trợ MySQL và PostgreSQL, mỗi nhánh phải tạo ra kết quả nghiệp vụ tương đương hoặc phải nêu rõ giới hạn sản phẩm.

### 7.1. dbms attribute và precondition dbms

Có thể dùng thuộc tính dbms trên changeset để xác định DBMS áp dụng. Một lựa chọn khác là precondition:

~~~yaml
preConditions:
  - onFail: HALT
  - onError: HALT
  - dbms:
      type: postgresql
~~~

Khác biệt trong cách dùng:

- Thuộc tính dbms phù hợp khi changeset chỉ dành cho một hệ quản trị.
- Precondition phù hợp khi muốn thể hiện điều kiện chạy cùng các kiểm tra khác, và định nghĩa rõ chính sách onFail/onError.
- Một changeset dùng SQL PostgreSQL nên dừng rõ ràng trên DBMS khác nếu nó được chọn để chạy; không để SQL không tương thích bị gửi đi.
- Cú pháp, khả năng kết hợp và hành vi khi changeset bị bỏ qua phải được kiểm chứng theo phiên bản Liquibase.

## 8. Một changelog chung với nhiều nhánh DBMS

Một dự án đa DBMS thường giữ một master changelog và phân nhánh ở những chỗ cần thiết. Cấu trúc minh họa:

~~~text
db/changelog/
  db.changelog-master.yaml
  common/
    001-create-customer.yaml
    002-add-customer-email.yaml
  postgresql/
    010-create-customer-index.yaml
    011-create-customer-function.yaml
  mysql/
    010-create-customer-index.yaml
    011-create-customer-procedure.yaml
~~~

Master changelog có thể include các file theo thứ tự được review. Từng file nhánh dùng dbms-specific changeset hoặc điều kiện phù hợp. Đây là cấu trúc khái niệm, không yêu cầu mỗi DBMS phải có một bản sao đầy đủ của toàn bộ changelog.

### 8.1. Giữ phần chung ở một nơi

Không sao chép toàn bộ changeset chung sang mỗi folder DBMS. Việc sao chép tạo ra nhiều nguồn sự thật, khiến bug fix hoặc thay đổi schema dễ bị áp dụng không đồng đều.

Nên giữ:

- Bảng, cột, khóa và dữ liệu tham chiếu phổ biến ở phần common.
- Function, index đặc thù hoặc DDL cần SQL riêng ở nhánh DBMS.
- Cấu hình môi trường như URL, user, password ở ngoài changelog.
- Khác biệt được thiết kế trong một ma trận hỗ trợ được review.

Nếu cùng một yêu cầu cần hai cách thực thi, hãy đặt chúng cạnh nhau trong tài liệu hoặc nhóm folder rõ ràng để reviewer có thể so sánh đầu ra.

### 8.2. ID changeset và lịch sử triển khai

Mỗi changeset cần ID/author/path ổn định. Đừng đổi ID hoặc di chuyển file sau khi đã triển khai nếu không có kế hoạch quản lý logicalFilePath và lịch sử.

Một database PostgreSQL không chạy changeset chỉ dành cho MySQL, và ngược lại. Tuy nhiên, vẫn phải xác minh lịch sử DATABASECHANGELOG của từng DBMS và không tái sử dụng cùng một danh tính cho nội dung thay đổi khác nhau.

Khi một DBMS mới được bổ sung vào sản phẩm, không chỉ thêm nhánh SQL. Cần kiểm tra database mới có baseline tương ứng, thứ tự changeset và lịch sử triển khai đúng.

## 9. Dùng change type chung trước, rồi bổ sung SQL riêng khi cần

Một chiến lược thường hiệu quả là:

1. Tạo bảng bằng createTable.
2. Tạo khóa chính/ngoại bằng change type tương ứng.
3. Tạo index chung bằng createIndex nếu hành vi mặc định đáp ứng yêu cầu.
4. Chỉ thêm SQL riêng cho những tối ưu hoặc tính năng không thể biểu diễn chung.
5. Dùng precondition kiểm tra đối tượng và DBMS.
6. Có rollback riêng cho nhánh DBMS.
7. Kiểm tra schema cuối cùng phải có cùng ý nghĩa trên mọi DBMS.

Ví dụ, phần bảng chung:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 020-create-order-audit
      author: platform-team
      changes:
        - createTable:
            schemaName: app
            tableName: order_audit
            columns:
              - column:
                  name: audit_id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_order_audit
                    nullable: false
              - column:
                  name: order_id
                  type: BIGINT
                  constraints:
                    nullable: false
              - column:
                  name: event_name
                  type: VARCHAR(100)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
~~~

Phần SQL riêng có thể thêm một index đặc thù nếu DBMS cần tùy chọn khác. Không tạo lại bảng ở nhánh riêng; chỉ thêm đúng phần khác biệt.

## 10. SQL trong change type sql

Khi cần câu SQL riêng ngắn, change type sql có thể đặt trực tiếp trong YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 030-create-customer-function
      author: platform-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE FUNCTION app.normalize_code(value text)
              RETURNS text
              LANGUAGE sql
              IMMUTABLE
              AS $body$
                SELECT UPPER(BTRIM(value));
              $body$;
      rollback:
        - sql:
            sql: DROP FUNCTION IF EXISTS app.normalize_code(text);
~~~

Ví dụ này dùng PostgreSQL function với dollar-quoted body. splitStatements: false ngăn Liquibase tách nội dung theo dấu chấm phẩy bên trong function. Cần thử trên đúng phiên bản Liquibase/driver; cách phân tách và delimiter có thể phụ thuộc loại script và cấu hình.

Rollback DROP FUNCTION xóa function, không tự khôi phục định nghĩa cũ. Nếu function đã được ứng dụng sử dụng, cần xem xét việc giữ định nghĩa tương thích hoặc tạo function version mới thay vì drop trực tiếp.

### 10.1. Tránh ghép SQL từ dữ liệu không tin cậy

Changelog parameter có thể thay thế tên schema hoặc một số giá trị cấu hình, nhưng không phải prepared statement. Không lấy tên bảng, role, câu WHERE hoặc cả đoạn SQL tùy ý từ request/người dùng rồi ghép vào SQL migration.

- Identifier động phải được giới hạn bởi allowlist.
- Giá trị dữ liệu nên dùng change type có cấu trúc khi phù hợp.
- Không đưa password/token vào SQL, changelog hoặc output update-sql.
- Review câu SQL sau khi Liquibase resolve parameter.
- Dùng quyền DBMS tối thiểu cho tài khoản migration.

## 11. SQL file với sqlFile

Khi câu SQL dài, nhiều function/procedure hoặc nhóm muốn review SQL bằng công cụ chuyên biệt, có thể tách SQL khỏi YAML và tham chiếu qua sqlFile.

Ví dụ changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 031-create-reporting-function
      author: platform-team
      dbms: postgresql
      changes:
        - sqlFile:
            path: sql/postgresql/create-reporting-function.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
      rollback:
        - sql:
            sql: DROP FUNCTION IF EXISTS app.reporting_total(date, date);
~~~

Tệp SQL minh họa có thể chứa:

~~~sql
CREATE OR REPLACE FUNCTION app.reporting_total(
    start_date date,
    end_date date
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $body$
    SELECT COALESCE(SUM(total_amount), 0)
    FROM app.orders
    WHERE created_at >= start_date
      AND created_at < end_date;
$body$;
~~~

Đây là ví dụ cấu trúc; đường dẫn phải tồn tại trong artifact thực tế khi triển khai. relativeToChangelogFile: true giúp phân giải đường dẫn tương đối với changelog chứa tham chiếu, tránh phụ thuộc thư mục làm việc của CLI.

splitStatements và endDelimiter cần được chọn theo nội dung:

- SQL đơn giản gồm nhiều câu kết thúc bằng dấu chấm phẩy có thể cần splitStatements true.
- Function/procedure có nhiều dấu chấm phẩy bên trong body thường cần tắt tách câu hoặc dùng delimiter được thiết kế phù hợp.
- Script Oracle PL/SQL hoặc SQL Server batch có thể cần delimiter đặc thù; phải kiểm tra phiên bản Liquibase và cách công cụ xử lý delimiter.
- Không mặc định mọi SQL file đều có thể chạy qua cùng cấu hình.

### 11.1. Quản lý đường dẫn và artifact

SQL file là một phần của migration, phải được commit và đóng gói cùng changelog. Nếu file không được đưa vào artifact triển khai, pipeline có thể chạy ở máy lập trình viên nhưng thất bại ở runner.

Khi di chuyển file, xem xét đường dẫn đã được ghi nhận và logicalFilePath của changeset. Không sửa tệp SQL đã được triển khai mà không tuân theo chính sách changeset bất biến.

## 12. Formatted SQL changelog

Liquibase hỗ trợ **formatted SQL changelog**, cho phép khai báo metadata changeset trong comment đặc biệt:

~~~sql
--liquibase formatted sql

--changeset platform-team:040-create-audit-view dbms:postgresql
CREATE OR REPLACE VIEW app.audit_summary AS
SELECT status, COUNT(*) AS total
FROM app.orders
GROUP BY status;

--rollback DROP VIEW IF EXISTS app.audit_summary;
~~~

Cách này phù hợp khi nhóm muốn SQL là nội dung chính và không cần YAML/XML để diễn đạt changeset. Cần chú ý:

- Header formatted SQL phải đúng định dạng Liquibase nhận diện.
- Comment changeset/rollback phải đúng cú pháp.
- Các thuộc tính như dbms, runInTransaction, splitStatements và endDelimiter phải được kiểm tra theo phiên bản.
- Không nhầm comment SQL thông thường với chỉ thị Liquibase.
- Cần kiểm tra SQL file được đưa vào master changelog đúng cách.

Formatted SQL không làm SQL trở nên khả chuyển. Nếu có cú pháp PostgreSQL, hãy giới hạn DBMS và có nhánh tương đương cho DBMS khác nếu sản phẩm tuyên bố hỗ trợ.

## 13. Delimiter và stored procedure/function

Các DBMS có quy tắc khác nhau khi định nghĩa function, procedure, trigger hoặc block:

- PostgreSQL có dollar-quoted body như $body$ ... $body$.
- Oracle PL/SQL thường có block BEGIN ... END; và công cụ SQL có thể dùng dấu / ở dòng riêng làm delimiter.
- SQL Server có batch separator GO trong một số script client, nhưng GO không phải câu lệnh SQL gửi trực tiếp tới server.
- MySQL có thể dùng DELIMITER trong client để đổi dấu kết thúc câu, nhưng DELIMITER không phải SQL server statement.

Liquibase phải biết cách phân tách statement đúng với loại file và phiên bản. Đừng copy nguyên script từ SQL client rồi giả định DELIMITER hoặc GO sẽ được JDBC thực thi.

### 13.1. Những thuộc tính cần xem xét

| Thuộc tính | Vai trò | Lưu ý |
|---|---|---|
| splitStatements | Cho phép Liquibase tách nội dung thành nhiều statement | Function body có dấu chấm phẩy bên trong có thể bị tách sai |
| endDelimiter | Xác định delimiter kết thúc statement trong một số cách chạy SQL | Không áp dụng tùy tiện cho mọi DBMS/script |
| runInTransaction | Điều khiển việc chạy changeset trong transaction theo hỗ trợ | Một số DDL không chạy được trong transaction; false tăng rủi ro trạng thái dở dang |
| stripComments | Kiểm soát xử lý comment trong SQL ở các trường hợp hỗ trợ | Không xóa comment chỉ để sửa checksum mà chưa review |
| relativeToChangelogFile | Phân giải đường dẫn sqlFile tương đối với changelog | Cần bảo đảm file được đóng gói đúng |

Một câu lệnh chạy thành công trong psql, sqlplus hoặc SSMS chưa chắc chạy được nguyên dạng qua JDBC. Kiểm thử phải dùng chính cách Liquibase sẽ gửi SQL.

## 14. Transaction và DDL khác nhau theo DBMS

Liquibase có thể quản lý transaction ở cấp changeset theo khả năng của DBMS. Nhưng hành vi DDL không giống nhau:

- PostgreSQL hỗ trợ transaction cho nhiều thao tác DDL, nhưng có ngoại lệ như CREATE INDEX CONCURRENTLY.
- MySQL có những DDL gây implicit commit hoặc có giới hạn atomic DDL phụ thuộc phiên bản/engine.
- Oracle có quy tắc implicit commit đối với nhiều DDL.
- SQL Server hỗ trợ transaction cho nhiều DDL, nhưng không phải mọi thao tác/tùy chọn đều có cùng hành vi.

Do đó:

1. Không giả định rollback tự động của transaction sẽ đảo ngược mọi DDL trên mọi DBMS.
2. Không đặt runInTransaction: false chỉ để né lỗi.
3. Tách thao tác không thể chạy trong transaction thành changeset riêng.
4. Nếu changeset có nhiều câu SQL không thể nguyên tử, cần kế hoạch kiểm tra trạng thái sau mỗi bước.
5. Có phương án cleanup/forward fix cho DDL thất bại một phần.
6. Kiểm tra thời gian khóa và tài nguyên trên dữ liệu đại diện.

Một changeset chứa CREATE INDEX CONCURRENTLY trên PostgreSQL là ví dụ cần xem xét runInTransaction: false; không được suy ra MySQL/Oracle cần cấu hình giống vậy.

## 15. Rollback cho SQL đặc thù

SQL thô thường đòi hỏi nhóm tự xác định rollback. Hãy tự hỏi:

- Có thể đảo ngược thao tác mà không mất dữ liệu không?
- Có thể phục hồi định nghĩa cũ của view/function không?
- Lệnh có ảnh hưởng đến object phụ thuộc hoặc quyền không?
- Nếu câu lệnh đầu thành công và câu thứ hai thất bại, trạng thái còn lại là gì?
- DBMS có rollback DDL trong transaction hiện tại không?
- Cần cleanup thủ công hoặc forward fix không?

Ví dụ thay đổi view:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 050-replace-order-summary
      author: platform-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE VIEW app.order_summary AS
              SELECT status, COUNT(*) AS total
              FROM app.orders
              GROUP BY status;
      rollback:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE VIEW app.order_summary AS
              SELECT status, COUNT(*) AS total
              FROM app.orders
              GROUP BY status;
~~~

Rollback trên chỉ minh họa cấu trúc, **không phải rollback có ý nghĩa** vì nó lặp lại định nghĩa mới. Trong thực tế, cần lưu/biết định nghĩa trước đó và đưa nội dung cũ vào rollback, hoặc thiết kế một migration forward-compatible. Không thể viết một rollback đáng tin cậy nếu nhóm không biết trạng thái trước thay đổi.

Với dữ liệu, rollback có thể cần phục hồi giá trị cũ thay vì xóa hàng. Với index/constraint, rollback có thể ảnh hưởng hiệu năng hoặc tính toàn vẹn. Với quyền, cần xem quyền đã tồn tại trước đó hay chưa. Hãy mô tả giới hạn rollback trong kế hoạch phát hành.

## 16. Preconditions cho nhánh SQL riêng

Precondition giúp ngăn SQL đặc thù chạy trên sai DBMS hoặc sai trạng thái đối tượng.

Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 060-create-postgresql-extension
      author: platform-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - dbms:
            type: postgresql
        - sqlCheck:
            expectedResult: "1"
            sql: |
              SELECT COUNT(*)
              FROM pg_database
              WHERE datname = current_database()
      changes:
        - sql:
            sql: CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

Ví dụ chỉ minh họa điều kiện DBMS và một truy vấn xác nhận ngữ cảnh database; pg_database có thể bị giới hạn quyền truy cập metadata và điều kiện này không chứng minh người dùng có quyền cài extension. Thao tác extension thường cần quyền quản trị/owner phù hợp và có thể nên được quản lý ở bước bootstrap của nền tảng thay vì migration ứng dụng.

Một precondition dbms không xác nhận database là dev hay production. Nếu SQL có rủi ro cao, cần kiểm tra cả host/database/schema/role ở tầng pipeline và quyền DBMS. onFail: HALT và onError: HALT giúp dừng khi điều kiện không đạt hoặc không thể đánh giá; không dùng MARK_RAN để che giấu nhánh bắt buộc chưa được áp dụng.

## 17. Tách SQL theo DBMS mà vẫn giữ kết quả nghiệp vụ tương đương

Khi có hai cách triển khai, hãy viết một bảng đối chiếu:

| Ý định nghiệp vụ | PostgreSQL | MySQL | Điều cần xác minh |
|---|---|---|---|
| Tạo index | CREATE INDEX / CONCURRENTLY | CREATE INDEX, tùy chọn online theo phiên bản | Lock, thời gian, trạng thái index khi lỗi |
| Tạo sequence | CREATE SEQUENCE hoặc identity | Auto increment thường dùng cho nhiều trường hợp | Cách sinh ID và quyền |
| JSON | JSON/JSONB | JSON | So sánh, index, validation, biểu diễn |
| Function | SQL/PLpgSQL | Stored function với cú pháp riêng | Ngôn ngữ, delimiter, quyền, deterministic |
| Cấp quyền schema | GRANT trên schema | Quyền database/table khác mô hình | Phạm vi truy cập và owner |
| Upsert | ON CONFLICT | ON DUPLICATE KEY UPDATE | Xung đột unique, giá trị cập nhật và affected rows |

Bảng này chỉ là gợi ý định hướng, không phải mapping đầy đủ. Từng câu lệnh phải được kiểm tra theo phiên bản DBMS và driver cụ thể.

Một tiêu chí quan trọng là **kết quả nghiệp vụ tương đương**. Ví dụ, hai nhánh upsert cần cùng quy tắc khi khóa trùng: cột nào được cập nhật, cột nào giữ nguyên, có ghi audit hay không, và xử lý cạnh tranh đồng thời như thế nào.

Nếu không thể giữ tương đương, hãy ghi rõ một DBMS có giới hạn chức năng hoặc không nằm trong ma trận hỗ trợ thay vì che khác biệt trong changelog.

## 18. Quản lý context, label và dbms riêng biệt

Ba khái niệm này giải quyết ba câu hỏi khác nhau:

- **DBMS**: thay đổi dành cho hệ quản trị nào?
- **Context**: thay đổi áp dụng trong ngữ cảnh triển khai/mục đích nào?
- **Label**: thay đổi thuộc nhóm chức năng hoặc phạm vi nào?

Ví dụ:

- PostgreSQL-specific index: dùng dbms: postgresql.
- Dữ liệu demo chỉ dành cho dev: dùng context được lựa chọn tường minh.
- Nhóm migration reporting: có thể dùng label reporting.

Không dùng context prod thay cho kiểm tra DBMS, hoặc dùng label để giả định SQL sẽ tự tương thích. Một changeset PostgreSQL không nên được chạy trên MySQL chỉ vì pipeline truyền context đúng.

Nếu có nhiều bộ lọc cùng lúc, hãy kiểm tra cách Liquibase kết hợp chúng theo phiên bản đang dùng và chạy status/update-sql cho từng tổ hợp môi trường.

## 19. Kiểm tra SQL được sinh ra trên từng DBMS

Không chỉ chạy validate một lần rồi kết luận changelog hỗ trợ đa DBMS. Cần thực hiện trên từng loại database:

1. Cố định phiên bản Liquibase và JDBC driver.
2. Dùng changelog giống artifact chuẩn bị phát hành.
3. Kết nối tới database thử nghiệm của từng DBMS.
4. Chạy validate để kiểm tra cấu trúc changelog và checksum.
5. Chạy status --verbose để xác định changeset được chọn.
6. Chạy update-sql để review SQL mà Liquibase dự kiến sinh.
7. Thử update trên database disposable hoặc bản sao.
8. Kiểm tra schema, dữ liệu, quyền, transaction và thời gian thực thi.
9. Thử rollback hoặc phương án forward fix.
10. Ghi nhận DBMS/version nào được hỗ trợ và ngoại lệ còn tồn tại.

Ví dụ lệnh:

~~~bash
liquibase --defaults-file=liquibase-postgresql.properties validate
liquibase --defaults-file=liquibase-postgresql.properties status --verbose
liquibase --defaults-file=liquibase-postgresql.properties update-sql
~~~

Với MySQL, dùng cấu hình kết nối riêng và lặp lại các bước trên. Cú pháp CLI và cách cung cấp nhiều defaults file phụ thuộc phiên bản; ví dụ trên chỉ minh họa ý tưởng dùng cấu hình theo DBMS.

**validate không chứng minh SQL đặc thù chạy được**, còn update-sql không chứng minh câu lệnh có thể lấy khóa hoặc hoàn thành trong thời gian production. Chỉ kiểm thử trên DBMS/version thật mới cho bằng chứng thực thi.

## 20. Ma trận kiểm thử đa DBMS

Nên duy trì ma trận tối thiểu theo tuyên bố hỗ trợ sản phẩm:

| Nhóm kiểm thử | PostgreSQL | MySQL/MariaDB | SQL Server | Oracle |
|---|---|---|---|---|
| Tạo bảng/cột/PK/FK | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| Kiểu dữ liệu và default | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| Index và online/concurrent | Kiểm tra riêng | Kiểm tra riêng | Kiểm tra riêng | Kiểm tra riêng |
| Sequence/identity | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| View/function/procedure | Kiểm tra cú pháp | Kiểm tra cú pháp | Kiểm tra cú pháp | Kiểm tra PL/SQL |
| GRANT/REVOKE/owner | Kiểm tra quyền hiệu lực | Kiểm tra quyền hiệu lực | Kiểm tra quyền hiệu lực | Kiểm tra quyền hiệu lực |
| Transaction/rollback DDL | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| Chạy lại và checksum | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |
| Dữ liệu NULL/trùng/constraint | Kiểm tra | Kiểm tra | Kiểm tra | Kiểm tra |

Không nhất thiết mọi sản phẩm phải hỗ trợ cả bốn DBMS. Ma trận phải phản ánh cam kết thực tế, phiên bản tối thiểu, loại change type và SQL riêng được phép.

Có thể dùng Testcontainers hoặc database ephemeral trong CI nếu có image/driver phù hợp. Nhưng một bài test trên H2 không chứng minh PostgreSQL/MySQL production tương thích: H2 có ngữ nghĩa và cú pháp riêng, kể cả khi chạy ở một compatibility mode.

## 21. Chẩn đoán khi change type chung thất bại

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| createTable chạy được trên DBMS A nhưng lỗi trên B | Kiểu dữ liệu, tên định danh, default hoặc thuộc tính không hỗ trợ | Xem SQL sinh ra, kiểm tra type mapping và version |
| addForeignKeyConstraint bị từ chối | Dữ liệu orphan hoặc khác quy tắc constraint | Kiểm tra dữ liệu và thứ tự migration |
| Index tạo thành công nhưng ứng dụng bị chậm | Kế hoạch index khác, thiếu thống kê hoặc lock | Đo query plan và workload trên DBMS thật |
| SQL function bị tách thành nhiều câu | splitStatements/delimiter không phù hợp | Chọn sqlFile, delimiter hoặc tắt splitStatements |
| runInTransaction: false để lại object dở dang | Một câu thành công, câu sau thất bại | Kiểm tra catalog và cleanup/forward fix trước retry |
| Một changeset bị chạy ở sai DBMS | Thiếu hoặc sai điều kiện dbms | Xem changeset attribute, precondition và status |
| SQL file không được tìm thấy | Đường dẫn không đóng gói trong artifact | Kiểm tra relative path và nội dung artifact |
| Checksum mismatch ở một môi trường | Changelog/path/parameter hoặc version khác | Đối chiếu Git, ID/author/FILENAME và cấu hình |
| DDL commit một phần trên một DBMS | Khác biệt transaction/implicit commit | Kiểm tra trạng thái thật; không giả định rollback tự động |
| SQL đúng nhưng quyền bị từ chối | Tài khoản migration không phải owner/thiếu quyền | Kiểm tra role và quyền; không nâng lên superuser tùy tiện |

Khi một nhánh thất bại, đừng sửa changeset đã triển khai ở nhánh khác rồi dùng lại ID. Hãy tạo changeset sửa lỗi mới và giữ lịch sử của từng database nhất quán.

## 22. Tình huống thực hành: một tính năng, hai DBMS

**Yêu cầu:** bảng app.orders cần index hỗ trợ truy vấn theo created_at. Sản phẩm hỗ trợ PostgreSQL và MySQL. Nhóm muốn dùng index concurrent ở PostgreSQL để giảm một số loại chặn ghi; nhánh MySQL dùng DDL phù hợp phiên bản triển khai.

### Bước 1. Phần schema chung

Dùng change type createTable hoặc createIndex cho những cấu trúc cơ bản có hành vi đáp ứng yêu cầu. Nếu chỉ mục thông thường đủ cho mọi DBMS, không cần tách SQL.

### Bước 2. Xác định yêu cầu vận hành

Nếu production PostgreSQL cần CREATE INDEX CONCURRENTLY, đây là một yêu cầu riêng: không chạy trong transaction block thông thường, có thể cần changeset runInTransaction: false và xử lý index không hợp lệ khi lỗi.

Với MySQL, xác minh phiên bản, storage engine và khả năng online DDL. Không tự giả định CREATE INDEX luôn không chặn ghi.

### Bước 3. Viết nhánh DBMS

Tạo hai changeset có ID riêng, dbms rõ ràng, rollback tương ứng và comment giải thích lý do. Không copy một câu SQL chung rồi dựa vào DBMS tự diễn giải khác nhau.

### Bước 4. Kiểm thử cả hai

- Chạy validate/status/update-sql cho PostgreSQL.
- Thử update trên database PostgreSQL disposable.
- Lặp lại với MySQL.
- Kiểm tra index tồn tại, định nghĩa cột, query plan và thời gian.
- Cố ý làm nhánh PostgreSQL thất bại trong môi trường thử để quan sát index có hợp lệ không.
- Thử rollback hoặc cleanup theo runbook.

### Bước 5. Công bố phạm vi hỗ trợ

Ghi rõ DBMS/version đã được thử, thao tác có giới hạn online nào, thời gian dự kiến và cách phục hồi. Không tuyên bố hỗ trợ một DBMS chỉ vì validate thành công.

## 23. Checklist trước khi chọn SQL đặc thù

- [ ] Change type dùng chung đã được xem xét và không đáp ứng đầy đủ yêu cầu.
- [ ] Lý do dùng SQL đặc thù được ghi rõ trong comment/tài liệu changeset.
- [ ] Changeset được giới hạn bằng dbms hoặc precondition thích hợp.
- [ ] Mỗi nhánh DBMS có ID/author/path ổn định và không dùng chung danh tính cho nội dung khác nhau.
- [ ] Kiểu dữ liệu, identifier, schema/catalog và default đã được kiểm tra.
- [ ] SQL được chạy thử bằng đúng Liquibase, JDBC driver và phiên bản DBMS.
- [ ] splitStatements, endDelimiter, relativeToChangelogFile và runInTransaction phù hợp nội dung.
- [ ] Function/procedure/trigger không bị tách sai delimiter.
- [ ] Rollback phản ánh trạng thái trước đó và không giả định dữ liệu có thể phục hồi tự động.
- [ ] Preconditions dừng rõ ràng khi sai DBMS hoặc thiếu đối tượng bắt buộc.
- [ ] Không ghép SQL/identifier từ đầu vào không tin cậy.
- [ ] SQL preview được review cho từng DBMS, không chỉ một môi trường.
- [ ] Ma trận kiểm thử có dữ liệu đại diện và kiểm tra quyền/transaction.
- [ ] Đã xác định hành vi khi DDL thất bại một phần và quy trình cleanup/forward fix.
- [ ] Artifact chứa đủ master changelog và các SQL file được tham chiếu.
- [ ] Changelog đã triển khai được giữ bất biến; sửa đổi sau này dùng changeset mới.

## 24. Kết luận

**Change type dùng chung** là lựa chọn phù hợp cho những thay đổi schema/dữ liệu phổ biến khi Liquibase có thể diễn đạt ý định và sinh SQL đáp ứng yêu cầu trên các DBMS mục tiêu. **SQL đặc thù** cần thiết khi hệ quản trị có tính năng, cú pháp hoặc hành vi riêng mà change type chung không thể mô tả chính xác.

Một changelog đa DBMS tốt giữ phần thay đổi chung ở một nơi, phân nhánh có chủ đích bằng dbms, quản lý SQL qua sql/sqlFile/formatted SQL khi cần, kiểm soát delimiter và transaction, đồng thời cung cấp rollback hoặc phương án phục hồi cho từng nhánh. Không đánh đồng khả năng parse/validate với khả năng thực thi an toàn: phải kiểm tra SQL sinh ra, dữ liệu, quyền, khóa và hành vi thật trên từng DBMS/version được hỗ trợ.

Cách lựa chọn này phục vụ mục tiêu của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**: quản lý changelog, changeset, precondition, checksum và lịch sử triển khai có thể kiểm chứng; phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD mà vẫn giữ được tính rõ ràng, khả chuyển ở nơi phù hợp và quyền kiểm soát đối với SQL đặc thù.

