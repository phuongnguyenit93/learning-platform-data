# Sử dụng sql cho thay đổi không thuận tiện với change type trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Chương **SQL và đối tượng** tập trung vào những tình huống mà một thay đổi database cần được diễn đạt bằng câu lệnh SQL cụ thể thay vì change type tiêu chuẩn.

Liquibase có nhiều change type như createTable, addColumn, createIndex, addForeignKeyConstraint hoặc createView. Những change type này thường dễ đọc, có thể chuyển đổi sang SQL phù hợp với nhiều hệ quản trị và hỗ trợ một số chức năng rollback. Tuy nhiên, không phải đặc tính nào của DBMS cũng được biểu đạt đầy đủ bằng các thuộc tính trừu tượng. Khi đó, change type **sql** cho phép đặt SQL trực tiếp bên trong changeset.

Nguyên tắc là: **dùng change type chuyên dụng khi nó thể hiện đúng ý định, dùng sql khi có lý do kỹ thuật rõ ràng, và vẫn tuân thủ toàn bộ kỷ luật migration của Liquibase**. Viết raw SQL không có nghĩa bỏ qua lịch sử, checksum, precondition, rollback hoặc kiểm soát môi trường.

## 1. Khi nào nên dùng sql thay vì change type có sẵn?

Hãy đánh giá xem một change type hiện có có đủ khả năng diễn tả thay đổi hay không trước khi dùng raw SQL.

| Nhu cầu | Ưu tiên ban đầu | Khi nào cân nhắc sql |
|---|---|---|
| Tạo bảng, thêm cột, khai báo primary key | createTable, addColumn, addPrimaryKey | Khi cần cú pháp DBMS đặc biệt mà change type không mô tả được |
| Tạo index thông thường | createIndex | Khi cần index có predicate, tùy chọn vật lý hoặc cú pháp đặc thù không được hỗ trợ đầy đủ |
| Thay đổi dữ liệu đơn giản | update, insert, loadData | Khi cần UPDATE nhiều bảng, CTE, hàm cửa sổ hoặc xử lý dữ liệu phức tạp |
| View | createView hoặc thay đổi được hỗ trợ | Khi cần cú pháp tạo/thay view đặc thù và kiểm soát toàn bộ SQL |
| Stored procedure/function | createProcedure hoặc cách triển khai được hỗ trợ | Khi cần toàn quyền trên định nghĩa function/procedure, body phức tạp hoặc ngôn ngữ đặc thù |
| Trigger, policy, extension, materialized view | Change type phù hợp nếu có và hỗ trợ DBMS đích | Khi không có change type tương ứng hoặc cần cú pháp vendor-specific |
| Cấu hình vật lý và thao tác vận hành đặc biệt | Tìm change type hoặc công cụ vận hành phù hợp | Khi SQL là cách được DBMS hỗ trợ và đã xác định lock, transaction, rollback |

Không chọn sql chỉ vì quen viết SQL. Nếu createTable hoặc addColumn đã đủ và migration cần hỗ trợ nhiều DBMS, change type chuyên dụng thường dễ bảo trì hơn. Ngược lại, ép một tính năng riêng của PostgreSQL/Oracle/SQL Server vào change type thiếu thuộc tính cần thiết có thể tạo SQL sai với yêu cầu.

### 1.1. Ưu điểm của sql

- Chủ động sử dụng cú pháp do DBMS hỗ trợ, kể cả các tính năng mới.
- Có thể dùng CTE, window function, DML nhiều bước hoặc DDL đặc thù.
- Kiểm soát chính xác tùy chọn index, view, function, policy hoặc trigger.
- Thuận tiện đưa đoạn SQL đã được DBA kiểm tra vào lịch sử triển khai.
- Vẫn đặt SQL trong changeset có id, author, precondition, checksum và lịch sử DATABASECHANGELOG.

### 1.2. Cái giá phải trả

- **Tính di động thấp hơn:** SQL của PostgreSQL không mặc nhiên chạy trên MySQL, Oracle hoặc SQL Server.
- **Rollback có thể phải viết thủ công:** Liquibase không thể suy ngược an toàn mọi câu SQL tự do.
- **Khó phân tích ngữ nghĩa:** Liquibase không hiểu đầy đủ đối tượng và quan hệ phụ thuộc bên trong một đoạn SQL bất kỳ.
- **Dễ lỗi delimiter và statement splitting:** đặc biệt với function/procedure có dấu chấm phẩy trong thân.
- **Tác động transaction phụ thuộc DBMS:** một số DDL tự commit hoặc bị cấm chạy trong transaction.
- **Trách nhiệm kiểm chứng cao hơn:** cần chủ động xem SQL, điều kiện trước/sau, dữ liệu và độ an toàn vận hành.

## 2. Khai báo sql trong YAML changelog

Ví dụ PostgreSQL cần một **partial index** chỉ lập chỉ mục các đơn hàng đang mở. Một index có mệnh đề WHERE như ví dụ này có thể không biểu đạt được bằng các thuộc tính của change type createIndex trong cấu hình dự án đang dùng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-2026-001-partial-index
      author: db-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: orders
      changes:
        - sql:
            comment: Index chỉ cho các đơn hàng đang mở
            sql: |
              CREATE INDEX idx_orders_open_created
              ON app.orders (created_at)
              WHERE status = 'OPEN';
      rollback:
        - sql:
            sql: |
              DROP INDEX app.idx_orders_open_created;
~~~

Ý nghĩa:

1. **changeSet.id và author:** định danh lịch sử. Cùng với đường dẫn logic changelog, chúng xác định một changeset riêng biệt.
2. **dbms: postgresql:** giới hạn thay đổi vào DBMS phù hợp, tránh gửi SQL PostgreSQL sang hệ quản trị khác.
3. **preConditions:** dừng với HALT nếu bảng app.orders chưa tồn tại. Đó mới chỉ là một điều kiện; môi trường thực tế còn phải có cột created_at và status.
4. **changes → sql → sql:** chứa nguyên văn câu lệnh cần DBMS thực thi.
5. **rollback:** cung cấp câu lệnh đảo ngược để xóa index nếu rollback phù hợp.

Ví dụ giả định schema app và bảng orders đã tồn tại, cột created_at/status có kiểu phù hợp, chưa có index trùng tên và tài khoản migration có quyền. Trước khi chạy, cần kiểm tra các điều kiện thực tế và review SQL trên chính phiên bản PostgreSQL đang sử dụng.

Không thêm IF NOT EXISTS một cách máy móc để né lỗi. Nếu đã có index cùng tên nhưng định nghĩa khác, câu lệnh này có thể bỏ qua thay đổi và làm lịch sử Liquibase ghi nhận một trạng thái không đúng mong muốn. Kiểm tra cấu trúc index thực tế và quyết định phương án chuyển đổi rõ ràng.

## 3. Tổ chức sql trong XML và formatted SQL

### 3.1. XML changelog

Trong XML, SQL được đặt trong phần tử sql bên trong changeset:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<databaseChangeLog
    xmlns="http://www.liquibase.org/xml/ns/dbchangelog"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      http://www.liquibase.org/xml/ns/dbchangelog
      https://www.liquibase.org/xml/ns/dbchangelog/dbchangelog-latest.xsd">

    <changeSet id="orders-2026-001-partial-index"
               author="db-team"
               dbms="postgresql">
        <sql>
            CREATE INDEX idx_orders_open_created
            ON app.orders (created_at)
            WHERE status = 'OPEN';
        </sql>
        <rollback>
            <sql>DROP INDEX app.idx_orders_open_created;</sql>
        </rollback>
    </changeSet>
</databaseChangeLog>
~~~

Chọn schemaLocation/XSD phù hợp với phiên bản Liquibase và quy tắc XML của dự án. Trong ví dụ này, ký tự đặc biệt trong XML phải được escape nếu câu SQL có nội dung xung đột cú pháp XML, chẳng hạn dấu nhỏ hơn hoặc dấu và.

### 3.2. Formatted SQL changelog

Một file .sql có thể là changelog được Liquibase đọc trực tiếp nếu dùng định dạng **formatted SQL**:

~~~sql
--liquibase formatted sql

--changeset db-team:orders-2026-001-partial-index dbms:postgresql
CREATE INDEX idx_orders_open_created
ON app.orders (created_at)
WHERE status = 'OPEN';

--rollback DROP INDEX app.idx_orders_open_created;
~~~

Các dòng bắt đầu bằng marker đặc biệt của Liquibase như --liquibase formatted sql, --changeset và --rollback là cú pháp điều khiển changelog; chúng không chỉ là comment SQL bình thường khi Liquibase nhận diện file là formatted SQL.

**Phân biệt:** một file SQL được dùng như *formatted SQL changelog* tự chứa ranh giới changeset; còn một file SQL được nhúng bằng change type sqlFile thường là nội dung SQL của một changeset đã được định nghĩa ở YAML/XML/JSON. Không tự ý đổi cách nạp file nếu điều đó làm thay đổi định danh và lịch sử của changeset đã chạy.

## 4. sql, sqlFile và formatted SQL khác nhau thế nào?

| Cách dùng | Vị trí định nghĩa changeset | Vị trí chứa SQL | Phù hợp khi |
|---|---|---|---|
| sql | YAML/XML/JSON changelog | Trực tiếp trong khối sql | SQL ngắn hoặc vừa, muốn thấy SQL ngay khi review changeset |
| sqlFile | YAML/XML/JSON changelog | File SQL ngoài được tham chiếu | SQL dài, cần syntax highlighting chuyên biệt hoặc DBA bàn giao script |
| Formatted SQL | Chính file .sql | Ngay sau marker changeset trong file | Nhóm muốn quản lý toàn bộ changelog bằng SQL có marker Liquibase |

Ví dụ tham chiếu sqlFile trong một changelog YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-2026-002-create-trigger
      author: db-team
      dbms: postgresql
      changes:
        - sqlFile:
            path: sql/postgresql/create_orders_trigger.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
      rollback:
        - sqlFile:
            path: sql/postgresql/drop_orders_trigger.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: false
~~~

Đây là **ví dụ minh họa đường dẫn**, không yêu cầu tạo thêm file trong bài học này. Trong dự án thực, các file được tham chiếu phải tồn tại và được đóng gói vào cùng artifact triển khai.

Các thuộc tính quan trọng:

- **path:** vị trí file SQL.
- **relativeToChangelogFile:** cách giải quyết đường dẫn so với file changelog hiện tại.
- **encoding:** mã hóa nội dung, nên thống nhất UTF-8 khi phù hợp.
- **splitStatements:** Liquibase có chia nội dung thành nhiều câu lệnh hay không.
- **rollback:** nên được khai báo rõ nếu thay đổi có phương án đảo ngược.

Dù sử dụng sql hay sqlFile, file/changelog sau khi phát hành vẫn cần được coi là lịch sử bất biến. Không sửa file SQL bên ngoài của một changeset đã triển khai rồi bỏ qua tác động checksum hoặc logic triển khai.

## 5. Các thuộc tính quan trọng khi dùng sql

SQL raw có thể chứa những cú pháp đặc thù khiến Liquibase phải biết cách xử lý chuỗi trước khi gửi cho JDBC/database. Một số tùy chọn được dùng thường xuyên:

| Thuộc tính | Cấp cấu hình thông dụng | Tác dụng |
|---|---|---|
| sql | change type sql | Nội dung câu lệnh SQL |
| dbms | changeset hoặc change sql ở định dạng hỗ trợ | Giới hạn DBMS có thể nhận SQL |
| splitStatements | sql/sqlFile | Quy định việc Liquibase chia khối SQL thành các câu riêng |
| endDelimiter | sql/sqlFile | Quy định dấu kết thúc câu lệnh khi Liquibase tách SQL |
| stripComments | sql/sqlFile | Kiểm soát việc loại bỏ comment trước khi gửi SQL |
| runInTransaction | changeset | Quyết định Liquibase có cố chạy changeset trong transaction hay không |
| runOnChange / runAlways | changeset | Điều khiển các tình huống changeset chạy lại có chủ đích |
| preConditions | changeset/changelog theo vị trí cho phép | Kiểm tra điều kiện trước khi thực thi |
| rollback | changeset | Định nghĩa cách đảo ngược thay đổi |

Các thuộc tính hỗ trợ cụ thể có thể khác theo định dạng changelog, phiên bản Liquibase và executor. Đặc biệt, khi dùng **native executor** của Liquibase Pro cho công cụ như psql, SQLcl hoặc sqlcmd, cách tách câu lệnh được công cụ native xử lý; không áp dụng máy móc splitStatements/endDelimiter dành cho JDBC.

### 5.1. splitStatements: chia hoặc giữ nguyên khối SQL

Khi bật splitStatements, Liquibase có thể tách khối SQL dựa trên delimiter như dấu chấm phẩy hoặc dòng GO theo quy tắc parser. Điều này thuận tiện cho script gồm những câu lệnh đơn giản:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: demo-001-basic-sql
      author: db-team
      changes:
        - sql:
            splitStatements: true
            sql: |
              UPDATE app.orders SET status = 'OPEN'
              WHERE status IS NULL;

              UPDATE app.orders SET reviewed = FALSE
              WHERE reviewed IS NULL;
~~~

Đoạn trên chỉ là minh họa trong database đã có các cột liên quan. Hai UPDATE có thể tạo lock và sửa nhiều dòng; cần đánh giá quy mô dữ liệu và transaction trước khi dùng production.

**Không coi parser của Liquibase là SQL parser hoàn chỉnh cho mọi phương ngữ.** Đoạn function có BEGIN/END và nhiều dấu chấm phẩy bên trong có thể bị tách sai nếu dùng cấu hình không phù hợp.

Khi toàn bộ body là **một câu lệnh phức tạp** mà DBMS tự xử lý dấu chấm phẩy bên trong, hãy cân nhắc splitStatements: false.

### 5.2. endDelimiter: dấu kết thúc phù hợp với script

endDelimiter giúp xác định dấu kết thúc cho việc chia SQL. Một số DBMS dùng delimiter khác dấu chấm phẩy khi chạy script; cũng có công cụ CLI cho phép đổi delimiter ở lớp client.

Cần lưu ý:

- Dấu delimiter dùng trong công cụ SQL client không nhất thiết là cú pháp được DBMS chấp nhận qua JDBC.
- Không đặt một delimiter tùy ý vào thân SQL rồi kỳ vọng database hiểu nó.
- Với function PostgreSQL có thân dollar-quoted, thường hữu ích hơn là giữ một câu lệnh duy nhất bằng splitStatements: false.
- Với native executor, ưu tiên để công cụ native thực hiện việc tách câu lệnh theo quy tắc riêng.
- Cấu hình nên được thử bằng update-sql và thực thi trên database thử nghiệm đúng DBMS.

### 5.3. stripComments: comment có thể mang ý nghĩa

Một số comment SQL chỉ dùng để giải thích, nhưng có hệ quản trị sử dụng comment dạng hint để tác động execution plan. Nếu bật stripComments, comment có thể bị loại bỏ trước khi gửi SQL.

Do đó, phải xem nội dung script và DBMS trước khi quyết định. Không mặc định comment hoàn toàn vô hại hoặc luôn cần xóa. Với formatted SQL, các marker của Liquibase cần được xử lý theo quy tắc của định dạng changelog; không nhầm chúng với comment ứng dụng thông thường.

### 5.4. runInTransaction: kiểm soát ranh giới transaction

runInTransaction là thuộc tính của changeset, không phải thuộc tính của câu SQL đơn lẻ. Thông thường Liquibase cố gắng chạy changeset trong transaction trên những DBMS hỗ trợ; nhưng nhiều loại DDL có quy tắc commit riêng và một số thao tác không được phép chạy trong transaction.

Khi phải đặt runInTransaction: false, nên ưu tiên **một thao tác có thể kiểm chứng cho mỗi changeset**. Nếu chứa nhiều câu SQL và câu cuối thất bại, những câu trước có thể đã thay đổi database trong khi lịch sử chưa ghi nhận hoàn tất, làm quy trình phục hồi khó khăn.

## 6. Ví dụ PostgreSQL: tạo index CONCURRENTLY

Trong một hệ thống có lưu lượng ghi lớn, tạo index thông thường có thể gây tác động lock ngoài mong đợi. PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY để giảm một số kiểu khóa đối với thao tác ghi, nhưng lệnh này **không được chạy bên trong transaction block**. Đây là tình huống phù hợp cho sql với runInTransaction: false.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-2026-003-index-online
      author: db-team
      dbms: postgresql
      runInTransaction: false
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: orders
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

**Đây là phương án thay thế** cho ví dụ partial index không CONCURRENTLY ở mục 2, không được đưa cả hai changeset tạo cùng một index vào một changelog thực tế.

### 6.1. Các rủi ro vẫn còn

CREATE INDEX CONCURRENTLY không có nghĩa thao tác không ảnh hưởng đến vận hành. Nó có thể chạy lâu, tiêu thụ I/O, chờ transaction khác và thất bại vì dữ liệu hoặc session. Nếu bị ngắt, PostgreSQL có thể để lại một **invalid index**; một lần chạy lại chỉ dựa vào IF NOT EXISTS có thể bỏ qua index cùng tên nhưng chưa hợp lệ.

Quy trình cần:

1. Xác nhận cấu trúc bảng, cột, predicate và tên index.
2. Kiểm tra mức tải và cửa sổ triển khai; có đủ tài nguyên và thời gian chờ.
3. Xác minh không có index tương đương hoặc invalid index cần xử lý.
4. Review update-sql với đúng cấu hình transaction.
5. Chạy migration chuyên trách, theo dõi tiến độ và log.
6. Sau chạy, kiểm tra index thực sự hợp lệ qua catalog PostgreSQL.
7. Nếu thất bại, chẩn đoán index còn lại và lịch sử Liquibase trước khi chạy lại.
8. Kiểm tra rollback trong môi trường thử nghiệm; câu DROP INDEX CONCURRENTLY cũng có giới hạn transaction.

Vì runInTransaction: false, không nên bổ sung thêm UPDATE hoặc nhiều lệnh DDL vào cùng changeset mà không có kế hoạch xử lý trạng thái trung gian. Cơ chế lock của Liquibase không biến toàn bộ thay đổi ngoài transaction thành một giao dịch nguyên tử.

## 7. Ví dụ PL/pgSQL: function chứa nhiều dấu chấm phẩy

Một function PostgreSQL có dấu chấm phẩy trong thân, nên không thể nhìn vào từng dấu chấm phẩy để tách thành nhiều câu SQL độc lập.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-2026-004-normalize-code-function
      author: db-team
      dbms: postgresql
      runOnChange: true
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE OR REPLACE FUNCTION app.normalize_order_code(input_code TEXT)
              RETURNS TEXT
              LANGUAGE plpgsql
              AS $$
              BEGIN
                  RETURN UPPER(TRIM(input_code));
              END;
              $$;
~~~

Những điều cần hiểu:

- splitStatements: false giúp gửi **toàn bộ câu lệnh tạo function** cho database xử lý.
- AS $$ ... $$ là cú pháp dollar-quoted string của PostgreSQL.
- CREATE OR REPLACE FUNCTION được dùng khi thay đổi định nghĩa phù hợp với các quy tắc của PostgreSQL.
- runOnChange: true cho phép Liquibase thực thi lại changeset khi định nghĩa có thay đổi được nhận diện, thích hợp với một số đối tượng có thể thay thế toàn phần.
- Không áp dụng runOnChange cho mọi raw SQL, đặc biệt là INSERT/UPDATE không idempotent hoặc ALTER TABLE chạy một lần.

### 7.1. Rollback cho function chạy lại

Ví dụ trên cố ý chưa khai báo rollback tự động. Nếu function được cập nhật từ phiên bản A sang phiên bản B, thao tác DROP FUNCTION không khôi phục định nghĩa A. Muốn rollback đúng, phải lưu hoặc tạo được **định nghĩa function trước đó**, xem xét dependency và triển khai một phương án đảo ngược có kiểm chứng.

Đối với function có thể thay thế toàn phần, một số nhóm chọn triển khai phiên bản mới bằng changeset khác thay vì chỉnh một changeset runOnChange. Chọn chiến lược nhất quán theo mục tiêu audit và rollback; một changeset chạy lại có lịch sử khác với một chuỗi changeset bất biến chạy một lần.

### 7.2. Procedure và script có batch delimiter riêng

Với SQL Server, batch separator GO là cú pháp của công cụ client, không phải một câu SQL chuẩn gửi trực tiếp cho mọi JDBC driver. Với Oracle, dấu gạch chéo dùng sau block PL/SQL trong một số client cũng cần phân biệt với nội dung statement thực tế.

Trước khi đưa script của DBA vào Liquibase, phải xác định script dành cho SQL client nào, có cần endDelimiter đặc biệt không, có chứa nhiều statement hoặc khối procedural không, và executor đang dùng là JDBC hay native. Không sao chép nguyên script của công cụ client vào change sql rồi giả định Liquibase phân giải đúng.

## 8. Ví dụ DML phức tạp: backfill có kiểm soát

Giả sử bảng app.orders được bổ sung cột priority ở changeset trước, và cần gán giá trị cho các hàng chưa có priority theo tổng tiền. Một câu UPDATE có biểu thức CASE có thể được viết bằng sql:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-2026-005-backfill-priority
      author: db-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - columnExists:
            schemaName: app
            tableName: orders
            columnName: priority
      changes:
        - sql:
            sql: |
              UPDATE app.orders
              SET priority = CASE
                  WHEN total_amount >= 1000000 THEN 'HIGH'
                  ELSE 'NORMAL'
              END
              WHERE priority IS NULL;
~~~

Ví dụ giả định cột total_amount tồn tại và dữ liệu đáp ứng kiểu so sánh. Không xác định rollback bằng cách đơn giản đặt mọi priority về NULL: thao tác đó không phân biệt dữ liệu được tạo ở migration này với dữ liệu đã có trước đó và có thể xóa thông tin hợp lệ.

Với dữ liệu production:

- Kiểm tra số dòng cần cập nhật trước khi chạy.
- Xem xét index, lock, transaction log/WAL và thời gian thực thi.
- Chọn batch/backfill theo tiến trình riêng nếu bảng rất lớn; một changeset SQL dài không tự có khả năng resume.
- Xác định xử lý NULL và giá trị ngoài miền nghiệp vụ.
- Có truy vấn hậu kiểm về số hàng còn NULL, phân bố HIGH/NORMAL và các bất biến nghiệp vụ.
- Ghi nhận khả năng rollback thực tế: snapshot/bảng audit, backup hoặc forward-fix nếu không đảo ngược dữ liệu an toàn.
- Không chạy lại bằng runAlways hoặc runOnChange trừ khi chủ đích và idempotency đã được chứng minh.

Raw SQL giúp linh hoạt, nhưng không thay thế việc thiết kế thay đổi dữ liệu có kiểm toán và kiểm tra hậu điều kiện.

## 9. Precondition, context, label và dbms khi dùng sql

SQL tự do vẫn nằm trong một changeset Liquibase, vì vậy có thể phối hợp với các cơ chế kiểm soát thực thi.

### 9.1. Precondition bảo vệ giả định

Ví dụ chỉ tạo index nếu bảng tồn tại là một điều kiện cơ bản. Có thể bổ sung kiểm tra bằng sqlCheck khi precondition có sẵn chưa biểu đạt đủ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: orders-2026-006-guarded-update
      author: db-team
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: orders
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.orders
              WHERE total_amount < 0;
      changes:
        - sql:
            sql: |
              UPDATE app.orders
              SET reviewed = TRUE
              WHERE status = 'CLOSED'
                AND reviewed IS DISTINCT FROM TRUE;
~~~

Ở đây sqlCheck chỉ kiểm tra điều kiện được viết ra; nó không tự chứng minh toàn bộ database đúng. Ví dụ giả định cột total_amount, status và reviewed đã tồn tại. Cần kiểm tra kiểu dữ liệu, số hàng cập nhật và tác động tới ứng dụng.

Với precondition thất bại, onFail: HALT thường phù hợp khi tiếp tục chạy có thể gây sai dữ liệu. Dùng onFail: MARK_RAN cần đặc biệt thận trọng: Liquibase có thể ghi changeset đã xử lý dù SQL chưa chạy. Không dùng MARK_RAN để che lỗi schema hoặc bỏ qua migration chưa thực hiện.

### 9.2. Context và label phân vùng mục đích

Context và label giúp chọn tập changeset theo môi trường hoặc mục đích phát hành. Ví dụ một script seed dữ liệu demo có thể chỉ dành cho môi trường development. Nhưng lọc changeset không có nghĩa SQL trở nên an toàn: vẫn cần DBMS phù hợp, quyền, precondition và dữ liệu đích.

Tránh sử dụng context hoặc label để khiến cùng một id/author/file path có những định nghĩa SQL khác nhau ở các môi trường. Nếu cấu trúc thực sự khác nhau theo DBMS, quản lý những changeset có dbms xác định và test trên từng engine.

### 9.3. DBMS-specific không đồng nghĩa mọi DBMS đều được hỗ trợ

Trong ví dụ PostgreSQL, dbms: postgresql bảo đảm Liquibase chỉ chọn changeset cho DBMS đó theo quy tắc lọc. Tuy nhiên, nếu cùng một ứng dụng hỗ trợ PostgreSQL và Oracle, cần có phương án thay thế hợp lệ cho Oracle; chỉ đơn thuần bỏ qua changeset PostgreSQL không chứng minh feature nghiệp vụ đã được tạo ở Oracle.

Có thể dùng changeset riêng cho từng DBMS với định danh khác nhau hoặc thay đổi kiến trúc để dùng change type chung. Hãy document ma trận tương thích và kiểm tra schema đầu ra từng DBMS.

## 10. SQL và changelog properties

Một số thay đổi dùng schema hoặc tên đối tượng theo môi trường. Liquibase hỗ trợ **property substitution** trong changelog, nhưng thay thế property là xử lý chuỗi, không phải bind parameter SQL an toàn.

Ví dụ ý tưởng: một job chạy với appSchema = commerce_test và SQL dùng giá trị đó trong tên schema. Cần kiểm soát chặt nguồn cấu hình. Nếu property đưa vào SQL nguyên văn không được kiểm tra, nó có thể làm SQL sai cú pháp, nhắm nhầm schema hoặc tạo nguy cơ SQL injection.

Đặc biệt:

- Không đưa giá trị nhận trực tiếp từ request người dùng vào tên bảng/schema trong migration.
- Dùng danh sách tên schema/đối tượng cho phép, không ghép SQL từ chuỗi tùy ý.
- Phân biệt tham số cấu hình Liquibase với placeholder của Spring Boot trong application.yml.
- Kiểm tra SQL sau phân giải bằng update-sql trước khi chạy.
- Không nhét secret/password vào SQL rồi lưu trong log hoặc báo cáo pipeline.
- Giữ lại tập cấu hình không nhạy cảm đi kèm bản phát hành để có thể tái tạo.

Thay đổi property không tự biến thành một migration mới cho changeset đã chạy. Nếu cần thay đổi cấu trúc thực tế, hãy tạo changeset bổ sung thay vì sửa giá trị parameter rồi hy vọng Liquibase chạy lại lịch sử.

## 11. Transaction, lock và thao tác chạy ngoài giao dịch

Đối với changeset có SQL:

1. **Mặc định mong muốn:** một changeset nhỏ, rõ mục đích, có khả năng thực thi nguyên tử khi DBMS hỗ trợ.
2. **DDL có auto-commit:** một số DBMS tự commit khi chạy DDL; Liquibase không thể đảo ngược bằng transaction như DML thông thường.
3. **Thao tác cấm transaction:** CREATE INDEX CONCURRENTLY trên PostgreSQL là ví dụ phải xem xét runInTransaction: false.
4. **Thao tác kéo dài:** có thể chiếm lock, dung lượng transaction log, I/O và ảnh hưởng giao dịch ứng dụng.
5. **Changeset có nhiều statement:** nếu không transactional và một statement thất bại, database có thể bị sửa một phần.
6. **Lịch sử Liquibase:** DATABASECHANGELOG ghi nhận trạng thái Liquibase xử lý, nhưng không tự sửa schema còn dang dở nếu DBMS đã commit từng phần.

Không nên gom nhiều lệnh phụ thuộc phức tạp vào cùng một changeset chỉ vì có thể viết chúng trong một khối sql. Chia thành nhiều changeset với hậu điều kiện rõ ràng thường giúp tái chạy, chẩn đoán và phục hồi dễ hơn.

### 11.1. Đừng dùng failOnError: false tùy tiện

Nếu một thay đổi quan trọng thất bại, im lặng tiếp tục có thể khiến pipeline thành công giả và database ở trạng thái không dự kiến. Với DDL/DML mang tính bắt buộc, nên để lỗi được báo rõ, dùng precondition để dừng sớm và triển khai phương án sửa có kiểm chứng.

Chỉ dùng các hành vi bỏ qua lỗi trong kịch bản có chủ đích, được review kỹ và có hậu kiểm độc lập; không biến việc bỏ qua lỗi thành “idempotency”.

## 12. Rollback cho raw SQL: phải thiết kế tường minh

Đối với nhiều change type chuyên dụng, Liquibase biết một số cách đảo ngược phổ biến. Với **raw SQL**, khả năng tự sinh rollback rất hạn chế; cần chủ động viết rollback hoặc xác định quy trình phục hồi khác.

### 12.1. Trường hợp dễ đảo ngược

Tạo một index mới, không ảnh hưởng dữ liệu chính, có thể rollback bằng DROP INDEX nếu đáp ứng yêu cầu DBMS và không có dependency chưa xử lý.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: demo-010-create-index
      author: db-team
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX idx_orders_created_at
              ON app.orders (created_at);
      rollback:
        - sql:
            sql: |
              DROP INDEX app.idx_orders_created_at;
~~~

Rollback phải nhắm đúng index/schema. Nếu index cũ đã tồn tại và changeset vô tình tạo trùng hoặc dùng IF NOT EXISTS, câu DROP INDEX rollback có thể xóa một đối tượng không phải do changeset tạo; vì vậy phải xác minh tiền đề.

### 12.2. Trường hợp không dễ đảo ngược

- DELETE hoặc UPDATE nhiều dòng không lưu bản gốc.
- Chuyển dữ liệu từ cấu trúc cũ sang mới theo phép không song ánh.
- DROP COLUMN/TABLE làm mất dữ liệu.
- Thay đổi permission/policy phức tạp có thể phụ thuộc trạng thái cũ.
- Sửa function bằng CREATE OR REPLACE mà không có định nghĩa trước.
- Thao tác ngoài transaction làm thay đổi một phần trước khi lỗi.

Trong các trường hợp này, một câu SQL “đảo” đơn giản có thể không khôi phục được trạng thái trước đó. Cần backup, bản sao dữ liệu, chiến lược forward-fix hoặc kế hoạch rollback nhiều bước. Review rollback-sql trên database thử nghiệm ở đúng phiên bản cần quay về; không coi rollback là bảo đảm khôi phục mọi dữ liệu.

### 12.3. Chạy rollback theo phạm vi được chọn

Chỉ rollback khi biết chính xác tập changeset sẽ bị đảo ngược. Có thể quản lý phạm vi bằng tag hoặc các cơ chế rollback được Liquibase hỗ trợ. Trước khi chạy thật, xem SQL đảo ngược, lock, dependency và độ tương thích với bản ứng dụng còn hoạt động.

Không tự xóa dòng DATABASECHANGELOG để buộc Liquibase chạy lại một thay đổi. Sửa bảng lịch sử thủ công có thể tạo sai lệch giữa lịch sử và schema.

## 13. Checksum và nguyên tắc bất biến của SQL đã triển khai

Khi một changeset chứa sql hoặc sqlFile được triển khai, Liquibase ghi nhận định danh và checksum trong DATABASECHANGELOG. Sau khi đã chạy trên một môi trường dùng chung, **không chỉnh nội dung SQL lịch sử như thể chưa từng triển khai**.

Ví dụ changeset A tạo partial index. Sau vài tuần, muốn thay predicate từ status = 'OPEN' sang status IN ('OPEN', 'PENDING'). Không nên sửa SQL bên trong A để mọi môi trường cùng mang một định danh nhưng có hai định nghĩa index khác nhau.

Phương án thường phù hợp:

1. Giữ changeset A và file SQL đã phát hành nguyên vẹn.
2. Tạo changeset B thay index theo thứ tự phù hợp với DBMS; có thể tạo index mới, chuyển đổi rồi drop index cũ khi an toàn.
3. Kiểm chứng SQL, thời gian lock, hậu điều kiện và rollback/forward-fix.
4. Đưa B vào bản phát hành mới, đối chiếu lịch sử giữa các môi trường.

### 13.1. Khi nào dùng runOnChange?

Với function hoặc view được thiết kế từ đầu để **thay thế toàn bộ** khi nội dung đổi, runOnChange có thể phù hợp. SQL phải chạy lại an toàn và DBMS phải hỗ trợ cú pháp thay thế. Thay đổi chỉ ở comment/khoảng trắng có thể không kích hoạt chạy lại, tùy xử lý checksum.

Không bật runOnChange hàng loạt để né lỗi checksum. DDL chạy một lần, data backfill, ALTER TABLE hoặc INSERT không idempotent không nên tự nhiên trở thành thay đổi chạy lại.

### 13.2. Không dùng clear-checksums để che lỗi

Khi báo checksum mismatch, cần so sánh file/commit đã triển khai, định nghĩa hiện tại, lịch sử và schema thực tế. Lệnh clear-checksums có tác động đến checksum được lưu, **không sửa schema và không biến một thay đổi sai thành đúng**.

Tương tự, validCheckSum chỉ cho phép chấp nhận checksum đã biết trong trường hợp phù hợp; không tự chạy nội dung mới. Chỉ sử dụng các cơ chế này sau khi đã xác minh nguyên nhân và có quyết định kỹ thuật rõ ràng.

## 14. Kiểm chứng SQL trước và sau migration

Trước khi chạy SQL tùy chỉnh trên database đích, nên có một quy trình ít nhất như sau:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Sau khi xác định đúng database, schema, bộ lọc context/label và thay đổi đã được review:

~~~bash
liquibase update
liquibase history
~~~

**Giới hạn của các lệnh:**

- validate kiểm tra tính hợp lệ của changelog và những điều kiện thuộc phạm vi Liquibase; không chứng minh SQL sẽ đúng với dữ liệu thật.
- status cho biết changeset nào còn pending theo cấu hình hiện tại; không tự kiểm tra mọi schema drift.
- update-sql hiển thị SQL dự kiến; không bảo đảm DBMS sẽ chấp nhận SQL và không luôn phản ánh mọi tác động runtime, lock hoặc hành vi executor đặc thù.
- history cho biết lịch sử được Liquibase ghi nhận; cần kết hợp truy vấn metadata và dữ liệu thực tế để xác nhận hậu điều kiện.

### 14.1. Ví dụ kiểm tra index PostgreSQL

Sau khi tạo index, có thể kiểm tra thông tin catalog:

~~~sql
SELECT ns.nspname AS schema_name,
       tbl.relname AS table_name,
       idx.relname AS index_name,
       pg_index.indisvalid AS is_valid,
       pg_index.indisready AS is_ready
FROM pg_index
JOIN pg_class idx ON idx.oid = pg_index.indexrelid
JOIN pg_class tbl ON tbl.oid = pg_index.indrelid
JOIN pg_namespace ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'app'
  AND tbl.relname = 'orders'
  AND idx.relname = 'idx_orders_open_created';
~~~

Với partial index, cần kiểm tra thêm định nghĩa/predicate thực tế; có thể tham khảo pg_get_indexdef của PostgreSQL:

~~~sql
SELECT pg_get_indexdef(indexrelid) AS index_definition
FROM pg_index
WHERE indexrelid = 'app.idx_orders_open_created'::regclass;
~~~

Đây là truy vấn kiểm tra metadata. Với các DBMS khác, phải dùng catalog tương ứng. Không giả định tên index tồn tại thì index đã hợp lệ sau một lần CREATE INDEX CONCURRENTLY thất bại.

### 14.2. Kiểm tra dữ liệu sau UPDATE

Nếu raw SQL backfill một cột trạng thái, thiết lập các hậu điều kiện như:

- Số dòng còn NULL sau cập nhật.
- Số dòng được phân loại theo mỗi trạng thái.
- Số dòng vi phạm constraint hoặc invariant nghiệp vụ.
- Số hàng đã cập nhật khớp với quy mô dự kiến.
- Application smoke test có thể đọc và ghi dữ liệu sau migration.

Có thể ghi lại các truy vấn hậu kiểm và kết quả trong log phát hành. Không chỉ dựa vào việc lệnh update báo exit code 0.

## 15. Tích hợp Spring Boot và CI/CD

Trong Spring Boot, Liquibase có thể được cấu hình để chạy changelog khi ứng dụng khởi động:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

Nếu changelog YAML có change sql, Spring Boot không “diễn dịch lại” nó thành một change type khác; Liquibase vẫn xử lý SQL theo cấu hình và DBMS. Nếu ứng dụng chạy nhiều instance, các instance phải cùng dùng bộ changelog và bảng metadata để lock hoạt động nhất quán.

Với thay đổi SQL có thể chặn ứng dụng hoặc cần runInTransaction: false, thường dễ kiểm soát hơn nếu pipeline chạy một migration job chuyên trách trước khi đưa phiên bản ứng dụng mới vào phục vụ. Khi đó việc có bật Liquibase tự động ở runtime hay không phải được thiết kế và cấu hình thống nhất.

### 15.1. Các cổng kiểm tra CI/CD cần có

| Bước | Kiểm tra |
|---|---|
| Review pull request | Có thật sự cần raw SQL? SQL dành cho DBMS nào? |
| Validate | Changelog parse được, id/author/đường dẫn ổn định, checksum không bất thường |
| Static review | DDL/DML có side effect gì, có secret, injection hoặc sai cú pháp không? |
| Database test | Thử cả database mới và database có lịch sử cũ, dữ liệu đủ lớn/đại diện |
| SQL preview | Review update-sql với cùng config sẽ dùng khi update |
| Transaction review | Xác định runInTransaction, DDL auto-commit, lock và timeout |
| Recovery review | Có rollback thực tế, backup hoặc forward-fix được kiểm chứng |
| Deploy | Một tiến trình phụ trách, dùng quyền phù hợp và có giám sát |
| Post-deploy | Xác minh DATABASECHANGELOG, schema, dữ liệu và ứng dụng |
| Audit | Lưu commit, artifact, SQL thay đổi, kết quả kiểm tra và người phê duyệt |

Không để CI/CD chạy raw SQL tùy ý với quyền DBA toàn cục nếu chỉ cần quyền hạn chế trên một schema. Với DDL đặc thù và security object, cấp quyền tối thiểu và phối hợp với DBA theo quy trình tổ chức.

## 16. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Việc cần kiểm tra |
|---|---|---|
| SQL bị tách giữa thân function/procedure | splitStatements hoặc delimiter không phù hợp | Kiểm tra dấu chấm phẩy trong thân, cấu hình sql/sqlFile và executor |
| PostgreSQL báo CREATE INDEX CONCURRENTLY cannot run inside a transaction block | Changeset còn chạy trong transaction | Xem runInTransaction, đổi thành changeset chuyên trách nếu cần |
| Chạy lại tạo index báo đã tồn tại | Changelog đã chạy một phần hoặc có index từ trước | Kiểm tra catalog, trạng thái index và DATABASECHANGELOG |
| Index có tên đúng nhưng không được planner dùng | Index invalid, predicate không khớp hoặc thống kê/planner | Kiểm tra pg_index và pg_get_indexdef, truy vấn thực tế |
| SQL chạy dev nhưng lỗi production | Khác DBMS/version/schema/permission | So sánh môi trường và review cú pháp đặc thù |
| Không tìm thấy function/view sau update | Changeset bị lọc bởi dbms/context/label hoặc SQL chạy schema khác | Kiểm tra status, history, schema và filter |
| DML cập nhật quá nhiều dòng | WHERE thiếu/hạn chế sai hoặc dữ liệu khác dự kiến | Tạm dừng, kiểm tra backup, số hàng và log transaction |
| Rollback chạy được nhưng mất dữ liệu | Câu đảo ngược không thể phục hồi bản gốc | Dùng backup/audit/forward-fix đã thiết kế |
| Checksum mismatch | SQL trong changeset cũ bị sửa hoặc thay đổi parser/format | So sánh artifact đã deploy, phục hồi lịch sử, tạo changeset mới |
| SQL có dấu placeholder chưa phân giải | Property chưa cấu hình hoặc tên sai | Kiểm tra tham số đầu vào và SQL được sinh |
| SQL trong file ngoài không được tìm thấy | Sai path hoặc relativeToChangelogFile | Kiểm tra cách đóng gói artifact và vị trí file |
| Rollback tạo lỗi cú pháp | SQL rollback khác cú pháp DBMS hoặc sai transaction boundary | Test rollback-sql, review trên DBMS thực |

### 16.1. Phân biệt lỗi parser, quyền và trạng thái

Khi lỗi xảy ra, đừng thay đổi ngẫu nhiên splitStatements hoặc clear-checksums.

1. **Lỗi parser/syntax:** kiểm tra SQL đã gửi, delimiter, dấu quote, XML escaping và phiên bản DBMS.
2. **Lỗi quyền:** kiểm tra user migration, schema, role, quyền tạo/đổi đối tượng và quyền với dependency.
3. **Lỗi trạng thái:** kiểm tra đối tượng có sẵn, dữ liệu đã được chuyển một phần, lock còn hoạt động hay không và lịch sử Liquibase.
4. **Lỗi cấu hình:** kiểm tra URL, catalog/schema, context/label/dbms, đường dẫn sqlFile và property values.
5. **Lỗi vận hành:** kiểm tra transaction dài, lock wait, timeout, deadlock, log và áp lực tài nguyên.

Không tự sửa/xóa dòng DATABASECHANGELOG hoặc DATABASECHANGELOGLOCK để “hết lỗi” khi chưa biết migration nào đã chạy và database thực tế đang ở đâu.

## 17. Bài thực hành: dùng sql để tạo partial index

**Mục tiêu:** học cách chọn raw SQL khi change type không biểu đạt đủ tính năng, viết rollback, xem SQL trước khi triển khai và kiểm tra index thật. Chỉ sử dụng PostgreSQL thử nghiệm; không chạy production.

### Bước 1. Chuẩn bị bảng thử nghiệm

Dùng một changeset riêng để tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-create-orders
      author: learner
      changes:
        - createTable:
            schemaName: app
            tableName: lab_orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: status
                  type: VARCHAR(20)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  constraints:
                    nullable: false
~~~

Schema app phải được tạo sẵn bằng quy trình chuẩn của môi trường lab.

### Bước 2. Thêm partial index bằng sql

Thêm một changeset mới dưới changeset tạo bảng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-002-create-partial-index
      author: learner
      dbms: postgresql
      changes:
        - sql:
            sql: |
              CREATE INDEX idx_lab_orders_open_created
              ON app.lab_orders (created_at)
              WHERE status = 'OPEN';
      rollback:
        - sql:
            sql: |
              DROP INDEX app.idx_lab_orders_open_created;
~~~

Đây là **đoạn changeset minh họa để thêm vào cùng databaseChangeLog**, không tạo một databaseChangeLog thứ hai trong cùng file. Chú ý id/author rõ ràng, dbms giới hạn PostgreSQL, SQL tạo index và rollback xóa index.

### Bước 3. Validate và review SQL

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Kiểm tra:

- Không có syntax error khi parse YAML.
- SQL tạo bảng xuất hiện trước SQL tạo index trên database mới.
- SQL tạo index có đúng schema app, bảng lab_orders và predicate status = 'OPEN'.
- Không có SQL nhắm vào bảng nghiệp vụ ngoài phạm vi lab.
- Changelog trỏ đến đúng database thử nghiệm.

### Bước 4. Chạy và xác minh

Chạy update trên lab, sau đó kiểm tra lịch sử:

~~~bash
liquibase update
liquibase history
~~~

Kiểm tra index bằng catalog PostgreSQL:

~~~sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'app'
  AND tablename = 'lab_orders'
ORDER BY indexname;
~~~

So sánh định nghĩa idx_lab_orders_open_created với mục tiêu đã thiết kế. Có thể tạo thêm dữ liệu thử nghiệm để quan sát plan của câu truy vấn có predicate tương ứng; nhưng việc planner có chọn index hay không còn phụ thuộc thống kê, phân bố dữ liệu và kích thước bảng.

### Bước 5. Thảo luận rollback và transaction

Ở môi trường lab tách biệt, thử xem SQL rollback dự kiến theo cơ chế Liquibase của dự án và chỉ thực thi khi đã xác định phạm vi cần rollback. Kiểm tra index bị xóa mà bảng dữ liệu vẫn còn nguyên.

Sau đó so sánh với lựa chọn CREATE INDEX CONCURRENTLY: tại sao cần runInTransaction: false, tại sao thất bại có thể để lại invalid index, và vì sao một changeset chỉ chứa một thao tác sẽ dễ phục hồi hơn.

### Bước 6. Mở rộng: function chứa dấu chấm phẩy

Đọc ví dụ function ở mục 7 và giải thích tại sao splitStatements: false giúp tránh tách sai các dấu chấm phẩy bên trong BEGIN/END. Nếu thực hành trên database lab, thêm changeset riêng với id mới; không sửa một changeset đã chạy để thay đổi mục đích. Ghi lại SQL dự kiến, kết quả kiểm tra và phương án phục hồi.

## 18. Checklist trước khi phát hành raw SQL

- [ ] Đã kiểm tra change type chuyên dụng không thể hiện được yêu cầu hoặc không phù hợp.
- [ ] Đã ghi rõ SQL dành cho DBMS/phiên bản nào và dùng bộ lọc dbms phù hợp.
- [ ] SQL được đặt trong changeset có id, author và đường dẫn changelog ổn định.
- [ ] Đã xem splitStatements, endDelimiter và stripComments có phù hợp với nội dung SQL không.
- [ ] Nếu SQL có function/procedure, đã kiểm tra dấu chấm phẩy, quote và executor.
- [ ] Nếu có thao tác cấm transaction, đã thiết kế runInTransaction: false có kiểm soát.
- [ ] Đã kiểm tra bảng/cột/schema, quyền, dependency, tên đối tượng và dữ liệu hiện hữu.
- [ ] Đã review precondition và không dùng MARK_RAN để che lỗi.
- [ ] Không sử dụng property substitution từ nguồn không tin cậy để ghép raw SQL.
- [ ] Không ghi password, token hoặc dữ liệu nhạy cảm trong changelog/log pipeline.
- [ ] Có rollback đúng hoặc kế hoạch backup/forward-fix với thay đổi không đảo ngược.
- [ ] Không sửa raw SQL trong changeset đã triển khai; yêu cầu mới phải có thay đổi mới trừ ngoại lệ chạy lại được thiết kế từ đầu.
- [ ] Đã kiểm thử trên DBMS production tương ứng, cả dựng mới lẫn nâng cấp từ lịch sử cũ.
- [ ] Đã chạy validate, status, update-sql và review SQL trước update.
- [ ] Đã xác minh DATABASECHANGELOG, đối tượng database và dữ liệu sau update.
- [ ] Đã ghi lại commit, artifact, cấu hình không nhạy cảm và kết quả hậu kiểm.

## 19. Kết luận

Change type **sql** là lối mở có kiểm soát khi các change type trừu tượng không đủ biểu đạt một tính năng hoặc thao tác riêng của DBMS. Nó đặc biệt hữu ích với partial index, SQL DML phức tạp, function/procedure, trigger, policy và các thao tác DDL có yêu cầu vận hành đặc biệt. Cần lựa chọn giữa sql, sqlFile và formatted SQL dựa trên tính dễ review, cách đóng gói và sự ổn định của lịch sử.

Việc dùng SQL trực tiếp không làm mất trách nhiệm quản lý migration của Liquibase: định danh và checksum vẫn quan trọng, precondition và dbms giúp giới hạn thực thi, rollback/forward-fix phải được thiết kế rõ, còn transaction và delimiter phải phù hợp với SQL thực tế. Kết hợp kiểm chứng trước/sau triển khai, Spring Boot hoặc CI/CD quản lý cấu hình nhất quán và nguyên tắc changeset bất biến sẽ giúp các thay đổi đặc thù vẫn an toàn, có thể kiểm toán và tái tạo qua nhiều môi trường.
