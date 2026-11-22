# Xử lý dấu chú thích, dấu chấm phẩy và khối SQL nhiều câu trong Liquibase

Một migration có vẻ đơn giản có thể gặp lỗi ngay khi Liquibase tách SQL thành những câu lệnh gửi đến JDBC: dấu **;** trong thân function bị xem là kết thúc câu lệnh, từ **GO** bị đưa nguyên vào database, hoặc một đoạn comment chứa chỉ thị quan trọng bị xóa ngoài ý muốn. Với SQL nhiều câu, chỉ cần sai một ranh giới tách lệnh là cả changeset có thể thất bại hoặc áp dụng dở dang.

Bài học thuộc chương **SQL và đối tượng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu của module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Nội dung tập trung vào ba vấn đề liên quan chặt chẽ: **comment trong SQL**, **dấu phân cách câu lệnh** và **khối SQL nhiều câu**. Những ví dụ được trình bày để người học hiểu cách Liquibase phân tích và chạy SQL; SQL cuối cùng phải được kiểm chứng trên chính phiên bản Liquibase, JDBC driver và DBMS đang dùng.

**Sau bài học, bạn có thể:**

1. Phân biệt SQL comment với comment đóng vai trò chỉ thị của Liquibase.
2. Giải thích ảnh hưởng của các thuộc tính **splitStatements**, **endDelimiter** và **stripComments**.
3. Viết SQL nhiều câu bằng change type **sql**, **sqlFile** hoặc **formatted SQL**.
4. Xử lý dấu chấm phẩy trong PostgreSQL function, khối PL/SQL Oracle, dấu **GO** trong SQL Server và script MySQL.
5. Thiết kế changeset có ranh giới rõ ràng, rollback phù hợp và kiểm soát khả năng chạy dở dang.
6. Kiểm tra **validate**, **status**, **update-sql** và SQL thực thi trên database thử nghiệm trước khi triển khai.

## 1. Những lớp phân tích cần phân biệt

Trong một luồng Liquibase thường có nhiều lớp xử lý:

- **Parser changelog:** đọc YAML/XML/JSON/formatted SQL và xác định changeset, thuộc tính, SQL hoặc đường dẫn SQL file.
- **Bộ phân tích SQL của Liquibase:** có thể tách một chuỗi SQL thành nhiều statement, nhận diện delimiter và bỏ comment tùy cấu hình.
- **SQL generator hoặc executor:** chuẩn bị câu SQL hoặc chạy câu SQL được cung cấp qua cơ chế tương ứng.
- **JDBC driver hoặc công cụ native:** nhận SQL và gửi yêu cầu thực thi đến DBMS.
- **Database:** phân tích cú pháp, kiểm tra quyền, transaction và thay đổi schema/dữ liệu.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A[Changelog Liquibase] --> B[Xác định changeset]
    B --> C[Đọc SQL từ sql / sqlFile / formatted SQL]
    C --> D[splitStatements, endDelimiter, stripComments]
    D --> E[Executor hoặc JDBC driver]
    E --> F[DBMS phân tích và thực thi]
    F --> G[Kiểm tra kết quả và ghi DATABASECHANGELOG]
~~~

**Ranh giới giữa các lớp là nguồn gốc của nhiều lỗi.** Một câu lệnh chạy được trong psql, SQL*Plus, mysql CLI hoặc sqlcmd không có nghĩa nó chạy nguyên vẹn qua JDBC: những công cụ terminal có thể tự xử lý các chỉ thị như **GO**, **DELIMITER** hoặc dấu slash **/**, trong khi DBMS không nhất thiết hiểu các chỉ thị ấy như SQL thông thường.

Một thay đổi trong Liquibase có thể chứa nhiều statement nhưng vẫn thuộc **một changeset**. Không được nhầm ranh giới SQL statement với ranh giới changeset trong lịch sử triển khai.

## 2. Ba hình thức viết SQL trong Liquibase

| Hình thức | SQL đặt ở đâu? | Ranh giới changeset | Tình huống phù hợp |
|---|---|---|---|
| **sql** | Ngay trong YAML/XML/JSON changelog | changeSet bao ngoài | SQL ngắn hoặc khối SQL có cấu hình rõ |
| **sqlFile** | Tệp SQL được changeSet tham chiếu | changeSet bao ngoài; tệp SQL không tự chia changeset | Script SQL dài hơn, muốn tách file |
| **formatted SQL changelog** | Tệp SQL có header và các chỉ thị Liquibase | Marker **--changeset author:id** | Nhóm muốn quản lý migration trực tiếp bằng SQL |

Ví dụ ba cách đều có thể tạo index, nhưng **cách xác định changeset** khác nhau.

Nếu dùng **sqlFile** với SQL thường, nhiều câu lệnh trong file nhìn từ Liquibase vẫn thường được quản lý trong cùng một changeset của changelog cha. Ngược lại, một file formatted SQL có thể chứa nhiều changeset độc lập với ID và lịch sử riêng.

Chọn hình thức theo nhu cầu review, rollback, khả năng kiểm soát dialect và số lượng statement; không chọn chỉ vì muốn giảm số file.

## 3. Dấu comment trong SQL

Hai kiểu comment phổ biến:

~~~sql
-- Comment một dòng

/* Comment
   kéo dài nhiều dòng */
~~~

Một số DBMS còn hỗ trợ cú pháp riêng, ví dụ dấu **#** ở MySQL. Đừng giả định mọi kiểu comment đều được parser SQL của Liquibase và mọi DBMS hỗ trợ giống nhau.

Ví dụ:

~~~sql
-- Bảng phục vụ lưu lịch sử thanh toán
CREATE TABLE payment_audit (
    id BIGINT PRIMARY KEY,
    payment_id BIGINT NOT NULL
);

/*
  Index hỗ trợ lọc payment_id.
  Dấu ; trong phần comment chỉ là văn bản.
*/
CREATE INDEX idx_payment_audit_payment
ON payment_audit (payment_id);
~~~

Khi chạy SQL:

- Comment thường không phải là lệnh thay đổi dữ liệu.
- Comment có thể được Liquibase giữ lại hoặc bỏ đi tùy **stripComments**.
- Dấu **;** nằm trong comment không nên bị xem là ranh giới câu lệnh SQL.
- Comment có thể chứa ký hiệu hoặc từ khóa trùng delimiter; cần kiểm thử parser nếu cú pháp phức tạp.

### 3.1. Comment trong string literal không phải SQL comment

Ví dụ:

~~~sql
INSERT INTO migration_note (id, note_text)
VALUES (100, 'Chuỗi này chứa -- và /* */ và dấu ;');
~~~

Dấu **--**, **/* */** và **;** bên trong một chuỗi được quote hợp lệ là **dữ liệu**, không phải comment hay ký hiệu kết thúc statement. Tuy vậy, cú pháp string literal còn tùy DBMS; một SQL splitter không được cấu hình thích hợp cho cú pháp đặc thù có thể nhận diện sai.

Ví dụ với dấu nháy đơn trong PostgreSQL và nhiều DBMS:

~~~sql
INSERT INTO migration_note (id, note_text)
VALUES (101, 'Ghi chú của O''Reilly; không phải câu SQL thứ hai');
~~~

Hai dấu nháy đơn liên tiếp dùng để biểu diễn một dấu nháy đơn trong string literal. Để tránh lỗi parser, luôn kiểm tra **update-sql** và chạy thử thực tế trên DBMS đích khi có chuỗi phức tạp.

### 3.2. Comment đặc biệt có thể ảnh hưởng cú pháp

Không phải mọi comment đều được viết chỉ để giải thích. Chẳng hạn **optimizer hint** của Oracle thường có dạng **/*+ ... */** và được DBMS xử lý đặc biệt.

~~~sql
SELECT /*+ FULL(c) */ c.id
FROM customer c;
~~~

Nếu bật **stripComments:true**, comment/hint có thể bị lược bỏ khi Liquibase chuẩn bị câu lệnh. Khi dùng hint, comment chứa chỉ dẫn công cụ hoặc cú pháp vendor-specific, không được bật stripComments một cách máy móc.

## 4. Comment thường và chỉ thị Liquibase là hai thứ khác nhau

Formatted SQL dùng **SQL comment có cấu trúc đặc biệt** để đánh dấu metadata của changeset.

~~~sql
--liquibase formatted sql

--changeset orders-team:20261119-001
--comment: Add audit table for order changes
CREATE TABLE order_audit (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
);

--rollback DROP TABLE order_audit;
~~~

Các dòng mang ý nghĩa riêng:

| Dòng | Liquibase hiểu là gì? |
|---|---|
| **--liquibase formatted sql** | Header nhận diện changelog dạng formatted SQL |
| **--changeset orders-team:20261119-001** | Bắt đầu changeset có author và id |
| **--comment:** | Metadata mô tả changeset |
| **--rollback** | Khai báo SQL rollback |
| **-- nội dung thông thường** | Comment SQL thông thường |

**Quy tắc quan trọng:** Marker formatted SQL được parser changelog nhận diện **trước khi phần SQL chính được thực thi**. Vì vậy, không thể suy luận rằng **stripComments:true** sẽ biến mọi chỉ thị changelog thành dữ liệu bị xóa; đây là hai giai đoạn xử lý khác nhau.

Ngược lại, đừng đặt marker **--changeset** bên trong tệp SQL thuần được tham chiếu bằng **sqlFile** rồi mặc định rằng Liquibase sẽ tự tạo changeset mới. Nếu cần ranh giới changeset ngay trong file SQL, hãy sử dụng **formatted SQL changelog** đúng cách.

### 4.1. Header phải được nhận diện đúng

Với formatted SQL, nên đặt header ở **dòng đầu**:

~~~sql
--liquibase formatted sql
~~~

Tránh thêm dòng comment khác, byte order mark không mong muốn hoặc nội dung tùy ý trước header nếu chưa kiểm tra bộ đọc của phiên bản Liquibase đang dùng. Lưu file bằng UTF-8 và xác minh parser đọc đúng marker trước khi chạy update.

### 4.2. Không tùy ý biến comment thành chỉ thị

Ví dụ:

~~~sql
-- Đây là thay đổi thứ hai nhưng không có marker changeset
CREATE INDEX idx_order_audit_order_id
ON order_audit (order_id);
~~~

Đây vẫn có thể chỉ là SQL nằm trong changeset hiện tại. Muốn index có ID độc lập, cần khai báo marker mới:

~~~sql
--changeset orders-team:20261119-002
CREATE INDEX idx_order_audit_order_id
ON order_audit (order_id);
~~~

Các ranh giới changeset cần thể hiện rõ thay đổi nào được ghi riêng trong DATABASECHANGELOG và có rollback riêng.

## 5. Dấu chấm phẩy làm dấu kết thúc câu lệnh

Trong SQL thông thường, dấu **;** được dùng để kết thúc statement:

~~~sql
CREATE TABLE migration_example (
    id BIGINT PRIMARY KEY,
    description VARCHAR(100)
);

CREATE INDEX idx_migration_example_description
ON migration_example (description);
~~~

Đây là **hai câu SQL**, nhưng có thể nằm trong **một changeset**. Khi Liquibase bật chế độ tách statement, nó có thể gửi hai câu SQL riêng tới executor.

**Dấu chấm phẩy không đồng nghĩa ranh giới changeset.** Nếu cả hai câu ở trong một changeset, Liquibase thường ghi **một dòng lịch sử** tương ứng, không phải hai dòng.

### 5.1. Cách parser nhận biết delimiter

Liquibase hỗ trợ tách statement theo những dấu phân cách mà nó nhận diện, thường gồm **;** và trong nhiều trường hợp **GO** trên dòng riêng. Cơ chế nhận diện delimiter, xét vị trí cuối dòng, comment và SQL dialect có thể thay đổi theo phiên bản và executor.

Đừng viết một quy tắc “Liquibase luôn tách ở mọi dấu ;” cho mọi trường hợp: dấu chấm phẩy có thể nằm trong string, block function, comment hoặc cú pháp đặc thù của DBMS.

### 5.2. Lỗi phổ biến khi nhầm dấu chấm phẩy

Giả sử một script chứa:

~~~sql
CREATE TABLE sample_a (id BIGINT PRIMARY KEY);
CREATE TABLE sample_b (id BIGINT PRIMARY KEY);
~~~

Nếu chạy với **splitStatements:false**, toàn bộ đoạn có thể được gửi tới driver như một khối. Một số driver hoặc DBMS chấp nhận nhiều statement trong một lần gửi, nhưng nhiều trường hợp không chấp nhận hoặc cần chế độ cấu hình riêng.

Do đó, **splitStatements:false không có nghĩa “chạy nhiều SQL an toàn hơn”**. Nó chủ yếu hữu ích khi một khối cần được gửi **nguyên vẹn như một đơn vị SQL**, chẳng hạn định nghĩa function/procedure có dấu chấm phẩy nội bộ.

## 6. Thuộc tính splitStatements

**splitStatements** xác định việc Liquibase có tách một đoạn SQL thành các statement độc lập trước khi gửi tới executor hay không.

| Giá trị | Ý nghĩa | Khi cân nhắc dùng |
|---|---|---|
| **true** | Liquibase chủ động tách theo delimiter được cấu hình/nhận diện | Script có nhiều lệnh DDL/DML độc lập |
| **false** | Liquibase không tự tách chuỗi SQL thành nhiều statement | Function/procedure, SQL block phức tạp cần giữ nguyên |

Một số phiên bản và kiểu changelog có mặc định khác nhau. Đối với migration có delimiter phức tạp, hãy **khai báo tường minh** thay vì phụ thuộc mặc định.

Ví dụ YAML tách hai lệnh độc lập:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-create-audit"
      author: "db-team"
      changes:
        - sql:
            splitStatements: true
            stripComments: false
            endDelimiter: ";"
            sql: |
              CREATE TABLE audit_log (
                  id BIGINT PRIMARY KEY,
                  actor_id BIGINT NOT NULL
              );
              CREATE INDEX idx_audit_log_actor
              ON audit_log (actor_id);
      rollback:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              DROP INDEX idx_audit_log_actor;
              DROP TABLE audit_log;
~~~

Ví dụ mô tả ý tưởng rollback **trên hệ quản trị chấp nhận cú pháp DROP INDEX như trên** (chẳng hạn PostgreSQL). Với DBMS yêu cầu tên bảng khi DROP INDEX hoặc cú pháp khác, phải điều chỉnh SQL và kiểm chứng.

### 6.1. splitStatements:false không thay thế transaction

Giữ nguyên SQL block trước khi gửi tới driver không tự biến nhiều statement thành một giao dịch nguyên tử. Cách DBMS xử lý commit, rollback và DDL mới quyết định kết quả.

Nếu một câu SQL thành công rồi câu sau thất bại, database có thể ở trạng thái **đã thay đổi một phần**, nhất là với DBMS có DDL tự commit hoặc changeset chạy không dùng transaction. Cần đánh giá riêng về **runInTransaction** và cơ chế của DBMS.

### 6.2. Cấu hình này thuộc phạm vi nào?

Trong **sql** và **sqlFile**, thuộc tính thường nằm trên change type. Trong **formatted SQL**, thuộc tính có thể được đặt ở marker changeset, ví dụ:

~~~sql
--changeset db-team:20261119-002 splitStatements:true
~~~

Dù vậy, thay đổi cách parser tách SQL sau khi changeset đã triển khai có thể làm thay đổi nội dung/định nghĩa migration được ghi nhận. Không sửa tùy tiện changeset cũ trên production chỉ để xử lý một lỗi tách câu.

## 7. Thuộc tính endDelimiter

**endDelimiter** chỉ định chuỗi đánh dấu kết thúc statement trong cách Liquibase xử lý SQL. Mặc định phổ biến là dấu **;**, nhưng những script có block lồng nhau hoặc cú pháp client riêng có thể cần delimiter khác.

Ví dụ tường minh:

~~~yaml
- sql:
    splitStatements: true
    endDelimiter: ";"
    sql: |
      INSERT INTO audit_log (id, actor_id) VALUES (1, 100);
      INSERT INTO audit_log (id, actor_id) VALUES (2, 200);
~~~

Đây là đoạn minh họa của một change **sql**, cần đặt bên trong **changes** của một changeset hợp lệ.

Đừng chọn một delimiter chỉ vì nó hiếm gặp. Cần xác định:

1. Delimiter có xuất hiện trong string literal hoặc comment không?
2. Nó có phải dấu dùng **trong SQL thực** hay chỉ là lệnh của công cụ client?
3. Liquibase có loại bỏ delimiter trước khi gửi JDBC không?
4. Định dạng changelog và phiên bản Liquibase có nhận diện delimiter như mong đợi không?
5. Rollback SQL có cần delimiter riêng không?

### 7.1. endDelimiter không phải thay toàn bộ cú pháp DBMS

Chọn **endDelimiter:GO** không biến cú pháp PostgreSQL thành SQL Server. Nó chỉ điều chỉnh cách Liquibase xác định ranh giới câu lệnh. Tên bảng, kiểu dữ liệu, function body và transaction vẫn phải đúng với DBMS đích.

### 7.2. Tránh delimiter va chạm nội dung

Nếu script chứa rất nhiều ký hiệu **/** hoặc **$$**, dùng chính ký hiệu đó làm delimiter có thể tạo ranh giới ngoài ý muốn. Với PostgreSQL dollar-quoted function, thường dễ kiểm soát hơn khi giữ **toàn bộ CREATE FUNCTION** trong một changeset không tách câu, thay vì chọn **$$** làm endDelimiter.

## 8. Thuộc tính stripComments

**stripComments** cho biết Liquibase có loại bỏ comment SQL trước khi gửi statement đến database hay không.

Ví dụ:

~~~yaml
- sql:
    splitStatements: true
    stripComments: true
    sql: |
      -- Index này phục vụ tra cứu đơn hàng
      CREATE INDEX idx_orders_created_at
      ON orders (created_at);
~~~

Khi bật **stripComments:true**, comment giải thích có thể bị loại bỏ khỏi SQL gửi đi. Nếu để **false**, comment có thể được giữ lại trong câu SQL tương ứng.

**Không nên nhầm stripComments với việc xóa chỉ thị changeset** trong formatted SQL. Chỉ thị Liquibase thuộc lớp parser changelog, còn stripComments tác động phần SQL thực thi theo cách triển khai của change type/parser.

### 8.1. Vì sao không luôn bật stripComments:true?

Có những comment chứa thông tin mà DBMS hoặc executor cần:

- Oracle optimizer hint dạng **/*+ ... */**.
- Comment mang ý nghĩa cho công cụ hoặc cơ chế phân tích riêng.
- Một số chú thích trong script phức tạp có liên quan đến cú pháp hoặc vị trí delimiter.

Ví dụ:

~~~sql
SELECT /*+ INDEX(o idx_orders_created_at) */ o.id
FROM orders o
WHERE o.created_at >= CURRENT_DATE;
~~~

Nếu Liquibase loại bỏ hint, SQL có thể vẫn chạy nhưng kế hoạch truy vấn thay đổi. Cần phân biệt comment chỉ để đọc với comment được DBMS giải thích.

### 8.2. stripComments không phải cách sửa SQL sai

Nếu script chứa **GO** hoặc **DELIMITER** là chỉ thị của công cụ client, việc bật stripComments có thể không giải quyết được vấn đề vì các từ khóa đó không nhất thiết là comment SQL. Hãy xác định đúng vai trò của delimiter và cấu hình/tái cấu trúc script cho Liquibase.

## 9. Thay đổi nhiều câu SQL bằng sql trong YAML

Dạng **sql** nhúng SQL trực tiếp trong changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-order-status"
      author: "orders-team"
      dbms: postgresql
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: orders
      changes:
        - sql:
            splitStatements: true
            stripComments: false
            endDelimiter: ";"
            sql: |
              -- Ghi metadata mới trước khi chạy các bước chuyển dữ liệu
              ALTER TABLE public.orders
              ADD COLUMN lifecycle_status VARCHAR(24);

              UPDATE public.orders
              SET lifecycle_status = 'NEW'
              WHERE lifecycle_status IS NULL;
      rollback:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              ALTER TABLE public.orders
              DROP COLUMN lifecycle_status;
~~~

Ví dụ có hai câu SQL được tách bởi dấu chấm phẩy, nhưng chỉ **một changeset**. Điều này tạo ra lợi ích gắn kết logic, song cũng tạo rủi ro:

- Nếu UPDATE thất bại sau ALTER TABLE, khả năng rollback transaction phụ thuộc DBMS và cấu hình Liquibase.
- Việc xóa cột trong rollback sẽ xóa dữ liệu mới có trong cột.
- UPDATE toàn bộ bảng lớn có thể giữ khóa lâu; cần cân nhắc tách DDL và backfill.
- Nếu cột đã tồn tại, changeset có thể thất bại; nên thêm precondition phù hợp nếu migration phải xử lý database đã có trạng thái không đồng nhất.

**Thực hành tốt hơn khi rủi ro cao:** tách **thêm cột**, **backfill**, **thêm constraint** thành các changeset có mục đích và phương án phục hồi riêng; không gộp chỉ vì file ngắn.

### 9.1. YAML block scalar và xuống dòng

Đoạn **sql: |** trong YAML bảo toàn các xuống dòng của khối SQL theo quy tắc YAML. Sai thụt đầu dòng có thể khiến parser không đọc đúng SQL hoặc coi thuộc tính khác là nội dung string.

Vì thế:

- Thụt đầu dòng nhất quán.
- Không chèn tab tùy tiện trong cấu trúc YAML.
- Dùng editor có khả năng hiển thị whitespace nếu cần.
- Chạy **validate** trước **update-sql**.
- Đọc output để chắc chắn nội dung và thứ tự câu SQL khớp ý định.

## 10. Sử dụng sqlFile cho script dài

Với script nhiều dòng hoặc được DBA chuẩn bị riêng, change type **sqlFile** cho phép tham chiếu tới tệp SQL:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-004-import-reference"
      author: "data-team"
      changes:
        - sqlFile:
            path: sql/20261119-004-import-reference.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            stripComments: false
            endDelimiter: ";"
~~~

Cấu trúc minh họa:

~~~text
db/changelog/
  db.changelog-master.yaml
  sql/
    20261119-004-import-reference.sql
~~~

Nội dung giả định của tệp SQL:

~~~sql
-- Danh mục trạng thái dùng chung
INSERT INTO reference_status (code, label)
VALUES ('NEW', 'Mới tạo');

INSERT INTO reference_status (code, label)
VALUES ('DONE', 'Hoàn thành');
~~~

Đây là hai statement trong **một sqlFile change**, nằm trong **một changeset**. Liquibase không tự tạo hai bản ghi DATABASECHANGELOG vì script có hai dấu **;**.

### 10.1. Những thuộc tính quan trọng

| Thuộc tính | Vai trò |
|---|---|
| **path** | Đường dẫn tệp SQL |
| **relativeToChangelogFile** | Giải quyết đường dẫn tương đối từ changelog chứa khai báo |
| **encoding** | Cách đọc ký tự, ví dụ UTF-8 |
| **splitStatements** | Có tách SQL thành statement hay không |
| **endDelimiter** | Dấu kết thúc statement |
| **stripComments** | Có bỏ comment SQL trước khi chạy hay không |

Cần kiểm tra file SQL thực sự được đóng gói trong artifact chạy Liquibase. Trên Spring Boot, classpath/resource path của ứng dụng đóng gói có thể khác cách chạy CLI từ thư mục làm việc.

### 10.2. Đừng dựa vào comment marker trong SQL file thường

Nếu tệp được tham chiếu qua **sqlFile** chứa:

~~~sql
--changeset data-team:second-statement
~~~

không nên kỳ vọng marker đó tự sinh changeset thứ hai. **Ranh giới changeset** đã do YAML/XML/JSON bao ngoài xác định. Muốn nhiều changeset trong một tệp SQL, dùng formatted SQL đúng định dạng và đưa vào changelog qua cơ chế phù hợp.

### 10.3. Khi nào không nên gom nhiều SQL vào một sqlFile?

Nếu script tạo bảng, chuyển dữ liệu, xây index và xóa bảng cũ trong cùng một changeset dài, lỗi ở giữa có thể khó khôi phục và khó xác định bước nào đã áp dụng. Hãy cân nhắc:

- Tách theo phụ thuộc và khả năng rollback.
- Dùng một changeset cho mỗi thao tác quan trọng.
- Có precondition kiểm tra schema và dữ liệu.
- Tránh script không idempotent được thực thi lại ngoài ý muốn.

## 11. Formatted SQL với nhiều changeset và chỉ thị comment

Ví dụ đầy đủ:

~~~sql
--liquibase formatted sql

--changeset audit-team:20261119-005 splitStatements:true stripComments:false
--comment: Create order event table
CREATE TABLE order_event (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL
);
--rollback DROP TABLE order_event;

--changeset audit-team:20261119-006 splitStatements:true
--comment: Add index to search events by order
CREATE INDEX idx_order_event_order_id
ON order_event (order_id);
--rollback DROP INDEX idx_order_event_order_id;
~~~

Đây là **hai changeset** trong cùng một tệp formatted SQL. Mỗi changeset có author, id, nội dung SQL và rollback riêng.

Dấu **--comment:** là chỉ thị metadata. Dòng comment SQL khác có thể chỉ là chú giải thông thường:

~~~sql
-- Không xóa dữ liệu đã có trong bảng cũ
~~~

Nếu một SQL block chứa nhiều câu và cần tách, hãy đặt **splitStatements:true**; nếu chứa một định nghĩa function/procedure cần giữ nguyên, cân nhắc **splitStatements:false**.

### 11.1. Marker changeset không dựa trên dấu chấm phẩy

Nếu chỉ có một marker rồi ba câu SQL:

~~~sql
--liquibase formatted sql
--changeset db-team:20261119-007
INSERT INTO audit_settings (id, enabled) VALUES (1, TRUE);
INSERT INTO audit_settings (id, enabled) VALUES (2, TRUE);
INSERT INTO audit_settings (id, enabled) VALUES (3, FALSE);
~~~

thì đó vẫn là **một changeset**. Muốn quản lý rollback hoặc lịch sử riêng cho từng phần, cần thêm marker changeset mới chứ không phải thêm dấu chấm phẩy.

### 11.2. Rollback comment trong formatted SQL

Ví dụ:

~~~sql
--rollback DELETE FROM audit_settings WHERE id = 3;
--rollback DELETE FROM audit_settings WHERE id = 2;
--rollback DELETE FROM audit_settings WHERE id = 1;
~~~

Những dòng này mô tả rollback cho changeset tương ứng khi trình phân tích hỗ trợ. Nhưng DELETE có thể xóa dữ liệu bị cập nhật sau triển khai. Cần thiết kế rollback với khóa, tập dữ liệu và quy tắc nghiệp vụ rõ ràng, không coi rollback nhiều dòng mặc nhiên an toàn.

## 12. PostgreSQL: dấu chấm phẩy trong PL/pgSQL function

Định nghĩa function PostgreSQL thường chứa dấu chấm phẩy nội bộ:

~~~sql
CREATE OR REPLACE FUNCTION normalize_email(input_email TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $func$
BEGIN
    RETURN lower(trim(input_email));
END;
$func$;
~~~

Có ít nhất hai dấu chấm phẩy:

- Dấu sau **RETURN ...;** kết thúc câu lệnh bên trong PL/pgSQL.
- Dấu sau **END;** kết thúc khối PL/pgSQL.
- Dấu sau **$func$;** kết thúc toàn bộ lệnh CREATE FUNCTION ở lớp SQL bên ngoài.

Nếu một splitter tách máy móc ở từng dấu **;**, lệnh CREATE FUNCTION sẽ bị chia sai và database có thể báo lỗi chuỗi dollar quote chưa đóng hoặc cú pháp không hợp lệ.

### 12.1. Dùng splitStatements:false cho một function

Ví dụ trong formatted SQL:

~~~sql
--liquibase formatted sql

--changeset reporting-team:20261119-008 dbms:postgresql splitStatements:false
CREATE OR REPLACE FUNCTION normalize_email(input_email TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $func$
BEGIN
    RETURN lower(trim(input_email));
END;
$func$;

--rollback DROP FUNCTION normalize_email(TEXT);
~~~

Ở đây **splitStatements:false** giúp giữ nguyên toàn bộ phần CREATE FUNCTION thành một khối để executor/JDBC xử lý. Cần thử trên PostgreSQL thật, vì hành vi của driver và cách loại delimiter cuối cùng phụ thuộc phiên bản.

**Đặc biệt:** không ghép thêm CREATE INDEX hoặc UPDATE ngoài function vào cùng khối khi đã dùng splitStatements:false, trừ khi đã xác minh executor nhận được nhiều statement và xử lý đúng. Thông thường nên tạo changeset khác cho câu lệnh kế tiếp.

### 12.2. Dollar-quoted string không phải delimiter Liquibase

PostgreSQL dùng cặp **$tag$ ... $tag$** hoặc **$$ ... $$** để bao nội dung string, thường là thân function. Dấu **$$** lúc này là một phần của cú pháp PostgreSQL, không tự động là dấu phân cách statement của Liquibase.

Nếu chọn **endDelimiter:$$** trong khi function cũng dùng **$$**, parser có thể nhận diện sai vị trí kết thúc. Cấu hình cần được thiết kế theo cấu trúc SQL thực tế, không chỉ theo độ dài delimiter.

### 12.3. runOnChange cho function có ý nghĩa riêng

Function có thể được viết theo mẫu **CREATE OR REPLACE FUNCTION** và đôi khi dùng **runOnChange:true** nếu migration được thiết kế chạy lại khi nội dung thay đổi. Đây là một quyết định riêng về vòng đời changeset, không phải giải pháp cho lỗi splitStatements. Không dùng runOnChange để sửa mọi changeset cũ hoặc né checksum mismatch.

## 13. Oracle: khối PL/SQL và dấu slash

Trong SQL*Plus hoặc một số công cụ Oracle, dấu **/** đứng riêng trên một dòng có thể được dùng để yêu cầu client thực thi khối PL/SQL đã nhập. Dấu slash đó **không phải câu SQL thông thường** mà mọi JDBC driver sẽ chấp nhận.

Ví dụ kiểu script dùng trong client Oracle:

~~~sql
CREATE OR REPLACE PROCEDURE record_audit_message AS
BEGIN
    INSERT INTO audit_message (message_text)
    VALUES ('migration complete');
END;
/
~~~

Dấu chấm phẩy trong BEGIN/END có ý nghĩa trong PL/SQL, còn dấu slash cuối là ký hiệu của công cụ client.

### 13.1. Lựa chọn khi viết Liquibase

Có những hướng cần kiểm chứng:

1. Dùng một change **sql** hoặc formatted SQL với **splitStatements:false** để gửi toàn bộ định nghĩa procedure phù hợp cho JDBC.
2. Dùng **endDelimiter:"/"** và cách đặt dấu slash cuối dòng mà phiên bản Liquibase hỗ trợ.
3. Dùng change type/định dạng được Liquibase hỗ trợ cho đối tượng SQL chuyên biệt hoặc native executor phù hợp.

Ví dụ **ý tưởng cấu hình** (không cam kết tương thích mọi phiên bản Oracle/Liquibase):

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-009-create-audit-procedure"
      author: "oracle-team"
      dbms: oracle
      changes:
        - sql:
            splitStatements: true
            endDelimiter: "/"
            sql: |
              CREATE OR REPLACE PROCEDURE record_audit_message AS
              BEGIN
                INSERT INTO audit_message (message_text)
                VALUES ('migration complete');
              END;
              /
~~~

**Bắt buộc kiểm tra** cách dấu slash được nhận diện ở phiên bản Liquibase cụ thể. Một số phiên bản có sự khác biệt về yêu cầu dấu xuống dòng/trailing slash. Nếu bộ phân tích gửi nguyên **/** tới JDBC như một statement không hợp lệ, migration sẽ thất bại.

### 13.2. Rủi ro optimizer hint và comment Oracle

Oracle có thể dùng comment chứa hint, ví dụ **/*+ ... */**. Không chọn **stripComments:true** chỉ để SQL “sạch” nếu hint quan trọng với hiệu năng. Xem trực tiếp SQL dự kiến, rồi thử trên phiên bản Oracle và driver mục tiêu.

## 14. SQL Server: GO là ranh giới batch của client

Trong nhiều công cụ SQL Server, **GO** là ký hiệu kết thúc **batch**, được client như sqlcmd/SSMS xử lý. Bản thân SQL Server không xem từ GO là một lệnh T-SQL có thể gửi nguyên qua JDBC như statement độc lập.

Ví dụ script quen thuộc trong SSMS:

~~~sql
CREATE TABLE dbo.audit_event (
    id BIGINT PRIMARY KEY,
    event_type NVARCHAR(80) NOT NULL
);
GO

CREATE VIEW dbo.v_audit_event AS
SELECT id, event_type
FROM dbo.audit_event;
GO
~~~

Một số định nghĩa T-SQL yêu cầu bắt đầu batch theo quy tắc của SQL Server. GO giúp công cụ client chia batch hợp lệ.

### 14.1. Xử lý trong Liquibase

Nếu muốn Liquibase tách tại **GO**, cần xác nhận parser phiên bản đang dùng hỗ trợ cách nhận diện ấy hoặc cấu hình delimiter tường minh:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-sqlserver-view"
      author: "sqlserver-team"
      dbms: mssql
      changes:
        - sql:
            splitStatements: true
            endDelimiter: "GO"
            sql: |
              CREATE TABLE dbo.audit_event (
                  id BIGINT PRIMARY KEY,
                  event_type NVARCHAR(80) NOT NULL
              );
              GO
              CREATE VIEW dbo.v_audit_event AS
              SELECT id, event_type
              FROM dbo.audit_event;
              GO
~~~

Đây là ví dụ cần kiểm thử thực tế vì SQL Server có quy tắc batch riêng, cách Liquibase xử lý dấu chấm phẩy/GO và hỗ trợ DDL có thể khác theo phiên bản. Trong migration thật, **tách CREATE TABLE và CREATE VIEW thành hai changeset rõ ràng** thường dễ review và rollback hơn.

Nếu sau **update-sql** vẫn thấy **GO** được gửi như statement tới JDBC trong chế độ không phù hợp, cần điều chỉnh cách chia batch hoặc executor; không gửi nguyên script SSMS rồi giả định driver sẽ tự nhận GO.

### 14.2. GO trong comment và string

Ví dụ:

~~~sql
PRINT 'GO';
-- GO ở dòng này là comment; không phải batch separator
~~~

Một parser cần phân biệt delimiter được cấu hình với từ xuất hiện trong literal/comment. Khi script phức tạp, kiểm chứng bằng SQL preview và chạy thử thay vì dựa vào vị trí nhìn bằng mắt.

## 15. MySQL/MariaDB: lệnh DELIMITER là của client

Trong MySQL CLI, ta thường gặp:

~~~sql
DELIMITER //
CREATE PROCEDURE update_example()
BEGIN
    UPDATE example_table SET processed = 1 WHERE processed = 0;
END//
DELIMITER ;
~~~

**DELIMITER** ở đây là chỉ thị của công cụ client, giúp client không ngắt CREATE PROCEDURE ở các dấu chấm phẩy bên trong. Nó không phải một statement SQL chung để gửi nguyên qua JDBC.

### 15.1. Không copy nguyên script CLI

Nếu copy cả **DELIMITER //** vào tệp **sqlFile** rồi yêu cầu JDBC chạy, có thể nhận lỗi cú pháp. Thay vào đó:

- Bỏ các lệnh DELIMITER dành riêng cho client.
- Chọn **splitStatements:false** khi cần gửi một định nghĩa procedure nguyên khối.
- Hoặc cấu hình endDelimiter được Liquibase hỗ trợ để chia script đúng.
- Test với JDBC driver MySQL/MariaDB tương ứng.

Ví dụ ý tưởng một changeset chỉ chứa procedure:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-mysql-procedure"
      author: "mysql-team"
      dbms: mysql
      changes:
        - sql:
            splitStatements: false
            sql: |
              CREATE PROCEDURE mark_pending()
              BEGIN
                  UPDATE payment
                  SET processed = 0
                  WHERE processed IS NULL;
              END
~~~

Phải kiểm tra cú pháp/driver và ngữ nghĩa của stored procedure trong phiên bản MySQL cụ thể. Mục đích ví dụ là thể hiện **giữ nguyên một câu CREATE PROCEDURE**, không khẳng định câu SQL phù hợp mọi biến thể server.

### 15.2. SQL comment của MySQL có đặc điểm riêng

MySQL hỗ trợ comment **#** và có các quy tắc riêng quanh **--**. Script chạy được trong mysql CLI có thể không được parser bên ngoài xử lý y hệt. Để giảm bất ngờ, nên dùng kiểu comment phổ biến, đơn giản, hoặc kiểm tra trực tiếp SQL sau khi Liquibase xử lý.

## 16. JDBC executor và native executor khác nhau thế nào?

Liquibase có thể thực thi SQL thông qua cơ chế JDBC thông thường hoặc, trong những giải pháp/phiên bản có hỗ trợ, thông qua **native executor** sử dụng công cụ CLI của DBMS.

Điểm khác biệt:

| Khía cạnh | JDBC thông thường | Native executor |
|---|---|---|
| Nơi SQL được gửi | JDBC driver | Công cụ DBMS như psql/sqlcmd/SQL*Plus tùy hỗ trợ |
| Vai trò delimiter | Liquibase và JDBC cần nhận SQL phù hợp | Công cụ native có thể sở hữu cách chia statement/batch |
| Chỉ thị client (GO, /, DELIMITER) | Không mặc nhiên được driver hiểu | Có thể là một phần cơ chế của client tương ứng |
| Rủi ro | Split sai hoặc driver không nhận nhiều statement | Hai lớp cùng tách/lọc SQL không nhất quán |
| Kiểm chứng | SQL preview và chạy test qua JDBC | Cần test đúng native executor đã chọn |

Với native executor, một số cấu hình như **splitStatements**, **endDelimiter** hoặc **stripComments** có thể không phù hợp hoặc bị khuyến nghị không dùng vì công cụ native đã tự xử lý. Không áp dụng máy móc cấu hình của JDBC cho native executor.

**Nguyên tắc vận hành:** cùng một changelog có thể cho hành vi thực thi khác nếu đổi loại executor. Vì vậy, sử dụng đúng executor và phiên bản dự kiến của production trong CI/CD kiểm chứng.

## 17. Một SQL block và một changeset không phải một transaction tuyệt đối

Đây là một ngộ nhận nguy hiểm:

> “Nếu gộp ba câu SQL vào một changeset thì hoặc tất cả thành công, hoặc không câu nào có tác dụng.”

Trên thực tế:

- Liquibase thường cố chạy một changeset trong transaction khi DBMS cho phép.
- Một số DBMS tự commit một số lệnh DDL.
- Có thao tác yêu cầu chạy ngoài transaction.
- **runInTransaction:false** có thể dẫn đến trạng thái được áp dụng một phần.
- Một số driver/executor xử lý chuỗi nhiều statement theo cơ chế riêng.

Ví dụ:

~~~sql
ALTER TABLE orders ADD COLUMN status VARCHAR(24);
UPDATE orders SET status = 'NEW' WHERE status IS NULL;
CREATE INDEX idx_orders_status ON orders (status);
~~~

Nếu update thất bại sau khi ALTER đã chạy, kết quả trên database phụ thuộc transaction và DBMS. Nếu schema đã đổi nhưng Liquibase không ghi nhận changeset EXECUTED, chạy lại nguyên script có thể báo **column already exists** hoặc tạo ra side effect lặp lại.

### 17.1. Chọn ranh giới changeset theo mức độ phục hồi

Thường nên tách:

1. Thêm cột.
2. Backfill dữ liệu.
3. Tạo index hoặc constraint khi trạng thái đã sẵn sàng.

Mỗi changeset có thể có:

- Precondition phù hợp.
- Rollback hoặc forward fix được thiết kế riêng.
- Kiểm tra dữ liệu sau khi chạy.
- Metadata id, author và mô tả rõ ràng.

Việc tách changeset không tự tạo transaction phân tán, nhưng giúp theo dõi và vận hành từng bước tốt hơn.

## 18. Rollback của SQL nhiều câu

Nếu một changeset chứa nhiều thao tác, rollback phải xử lý các phụ thuộc **theo thứ tự ngược hợp lý**.

Ví dụ tạo bảng rồi tạo index:

~~~sql
--liquibase formatted sql

--changeset db-team:20261119-012 splitStatements:true
CREATE TABLE sample_note (
    id BIGINT PRIMARY KEY,
    note_text VARCHAR(200)
);
CREATE INDEX idx_sample_note_text ON sample_note (note_text);

--rollback DROP INDEX idx_sample_note_text;
--rollback DROP TABLE sample_note;
~~~

Cú pháp DROP INDEX khác nhau theo DBMS, và trên một số DBMS khi DROP TABLE thì index của bảng cũng bị xóa theo. Ví dụ cần điều chỉnh theo database đích.

### 18.1. Không được chỉ đếm số câu rollback

Số câu rollback không nhất thiết phải bằng số câu update. Một thao tác rollback có thể đảo ngược nhiều thay đổi, hoặc ngược lại cần nhiều bước.

Hãy hỏi:

- Có dữ liệu nào phát sinh sau migration có thể bị xóa không?
- Có foreign key, view, trigger hoặc index phụ thuộc không?
- SQL rollback có chạy được với delimiter và parser được cấu hình không?
- DBMS có cho rollback DDL không?
- Có thể dùng backup/restore hoặc forward fix an toàn hơn không?

### 18.2. Delimiter của rollback

Với rollback function hoặc procedure, phần SQL đảo ngược đôi khi có cấu trúc khác SQL cập nhật. Một số phiên bản Liquibase hỗ trợ thuộc tính **rollbackEndDelimiter** trong các ngữ cảnh cụ thể. Hãy kiểm tra tính khả dụng theo định dạng và phiên bản rồi xem **rollback-sql** khi có thể, thay vì suy luận rằng delimiter update luôn dùng được cho rollback.

### 18.3. SQL data migration không luôn đảo ngược được

Ví dụ:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Dùng rollback đặt status của tất cả dòng ACTIVE thành NULL có thể làm sai dữ liệu vốn đã là ACTIVE. Nếu cần rollback, phải có thông tin nhận diện đúng các dòng đã thay đổi hoặc một kế hoạch khôi phục riêng.

## 19. Kết hợp với context, label, dbms và precondition

Một changeset dùng SQL tùy DBMS nên có cơ chế xác định môi trường và điều kiện áp dụng rõ ràng.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-013-add-reporting-index"
      author: "reporting-team"
      dbms: postgresql
      labels: "reporting"
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            schemaName: public
            tableName: orders
        - columnExists:
            schemaName: public
            tableName: orders
            columnName: created_at
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              CREATE INDEX idx_orders_created_at
              ON public.orders (created_at);
      rollback:
        - sql:
            sql: |
              DROP INDEX idx_orders_created_at;
~~~

Trong ví dụ:

- **dbms** hạn chế changeset theo hệ quản trị.
- **labels** phân loại thay đổi để runtime có thể lọc.
- **preConditions** kiểm tra bảng và cột.
- **sql** chứa câu SQL cụ thể.
- **rollback** mô tả thao tác đảo ngược.

Nhưng context/label/filter **không chọn database đích**. Database được quyết định bởi JDBC URL, schema và tài khoản kết nối. Nếu trỏ nhầm sang một database PostgreSQL khác, điều kiện dbms vẫn có thể đạt. Vì vậy, kiểm tra endpoint và quyền riêng với việc kiểm tra SQL syntax.

## 20. Checksum và thay đổi delimiter sau khi triển khai

Liquibase theo dõi changeset trong bảng **DATABASECHANGELOG** qua ID, author, FILENAME/logicalFilePath và checksum theo cơ chế của nó.

Giả sử một changeset đã chạy, sau đó bạn thay:

~~~yaml
splitStatements: true
~~~

thành:

~~~yaml
splitStatements: false
~~~

hoặc sửa dấu delimiter, thêm/bỏ comment hay thay SQL trong changeset đã phát hành. Đây là thay đổi định nghĩa migration, có thể gây khác biệt checksum hoặc cách Liquibase thực thi nếu được chạy lại. Các quy tắc checksum đối với metadata, whitespace và comment phụ thuộc loại changelog và phiên bản.

**Quy tắc bảo trì:** sau khi changeset đã chạy trên môi trường được giữ lâu dài, đừng sửa nó chỉ để “làm parser hết lỗi” mà không đối chiếu lịch sử. Với migration mới hoặc bước sửa chữa, tạo changeset mới; với migration đã bị lỗi giữa chừng, xác minh trạng thái DB thật và chọn phương án khắc phục được kiểm soát.

Đừng đổi tên hoặc di chuyển SQL file đã triển khai mà không kiểm tra ảnh hưởng của **FILENAME/logicalFilePath** đối với danh tính changeset. Cùng SQL nhưng đường dẫn khác có thể bị xem là changeset chưa chạy.

## 21. Kiểm chứng SQL được sinh: validate, status, update-sql

Một quy trình review trước **update**:

### Bước 1: Xác nhận cấu hình kết nối

Kiểm tra:

- URL, host, port và database/service.
- Schema hoặc catalog đích.
- Username và quyền DDL/DML phù hợp.
- Driver, phiên bản DBMS và Liquibase.
- Context/label filter và loại executor.

Không dùng working directory của terminal để suy ra database đích.

### Bước 2: Validate changelog

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
~~~

**validate** có thể tìm lỗi cấu trúc changelog, thuộc tính không hợp lệ và các vấn đề mà Liquibase kiểm tra được. Nó **không chứng minh** SQL trong file sẽ chạy thành công trên mọi DBMS, cũng không đảm bảo delimiter hay transaction đúng trong mọi tình huống.

### Bước 3: Xem changeset pending

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
~~~

Các changeset đã ghi nhận trong DATABASECHANGELOG thường không được chạy lại, trừ trường hợp có cơ chế hỗ trợ như runAlways/runOnChange. Nếu một changeset không xuất hiện trong danh sách pending, có thể do lịch sử, filter hoặc changelog không include tệp như mong đợi.

### Bước 4: Sinh SQL dự kiến

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
~~~

Review đầu ra theo **các ranh giới statement**:

- Liệu CREATE FUNCTION có bị tách sau dấu **RETURN ...;** không?
- Dấu **GO**, **/** hoặc **DELIMITER** có bị gửi thành statement không hợp lệ không?
- Có lệnh DDL/DML nào không thuộc phạm vi changeset dự kiến không?
- Comment optimizer hint có còn nếu cần không?
- Tên schema và object đúng chưa?
- Các câu SQL có xuất hiện theo đúng thứ tự phụ thuộc không?
- Rollback có được thiết kế phù hợp không?

Đây là SQL preview, không phải bằng chứng cuối cùng rằng driver hoặc DBMS sẽ thực thi thành công.

### Bước 5: Chạy trên database đại diện

Thực hiện trên development hoặc bản sao có cùng DBMS, phiên bản driver và schema representative. Xem log, metadata và dữ liệu sau khi migration chạy. Đặc biệt kiểm tra các script procedure/function vì SQL output đôi khi không tái hiện hết hành vi executor thực tế.

### Bước 6: Chỉ update sau khi review

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Cú pháp cờ CLI có thể khác theo phiên bản Liquibase; dùng tài liệu của phiên bản được triển khai. Không đặt password trực tiếp trong command line hoặc log CI/CD nếu có thể dùng secret manager và cơ chế cấu hình an toàn.

## 22. Tình huống lỗi 1: function bị tách giữa chừng

**Bối cảnh:** PostgreSQL function chạy tốt trong psql, nhưng Liquibase báo lỗi cú pháp gần **RETURN** hoặc **END**.

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION is_positive(n INTEGER)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN n > 0;
END;
$$;
~~~

**Nguyên nhân có thể:** Liquibase đang tách SQL theo dấu chấm phẩy bên trong function body.

**Cách xử lý có kiểm chứng:**

1. Xác định function được khai báo trong **sql**, **sqlFile** hay formatted SQL.
2. Đặt **splitStatements:false** cho changeset chứa duy nhất định nghĩa function.
3. Kiểm tra script không gộp các DDL độc lập vào cùng khối.
4. Chạy validate/update-sql.
5. Chạy thử trên PostgreSQL có cùng phiên bản.
6. Xác minh function tồn tại và gọi được.
7. Chỉ cập nhật code chưa phát hành; nếu changeset đã chạy ở đâu đó, xử lý lịch sử và phục hồi riêng.

**Không nên:** chọn endDelimiter là **$$** mà không xét việc **$$** chính là dấu mở/đóng dollar-quoted string.

## 23. Tình huống lỗi 2: GO bị gửi tới JDBC

**Bối cảnh:** Script từ SSMS có các dòng GO. Liquibase chạy với JDBC và báo lỗi cú pháp gần GO.

**Nguyên nhân có thể:** GO là batch separator của client, không phải T-SQL statement được database server hiểu khi gửi nguyên.

**Hướng xử lý:**

- Tách các batch thành changeset riêng nếu hợp lý.
- Cấu hình delimiter/đường xử lý tương ứng với phiên bản Liquibase.
- Xác nhận output không gửi nguyên GO tới JDBC dưới dạng statement.
- Kiểm tra những câu lệnh yêu cầu bắt đầu batch có còn hợp lệ.
- Thử trên SQL Server thật và driver tương ứng.

Nếu chọn native executor sqlcmd, cách xử lý có thể khác; đừng đổi executor mà không kiểm chứng lại migration.

## 24. Tình huống lỗi 3: comment bị xóa hoặc giữ ngoài ý muốn

**Bối cảnh:** Script có optimizer hint, nhưng sau khi đi qua Liquibase, hint biến mất.

**Nguyên nhân có thể:** **stripComments:true** loại bỏ comment theo cách parser hỗ trợ.

**Hướng xử lý:**

1. Xác định comment đó chỉ để đọc hay có ảnh hưởng thực thi.
2. Nếu là hint quan trọng, đặt **stripComments:false** theo ngữ cảnh được hỗ trợ.
3. Xem SQL preview.
4. Kiểm tra execution plan hoặc hiệu năng khi cần.
5. Không sửa changeset đã chạy tùy tiện; tạo thay đổi được review phù hợp.

Chiều ngược lại, nếu script giữ comment chứa ký hiệu delimiter hoặc cú pháp vendor-specific, việc giữ nguyên comment cũng có thể làm lộ lỗi parser. Cần kiểm chứng trên DBMS đích chứ không chọn một giá trị chung cho mọi migration.

## 25. Tình huống lỗi 4: script SQL nhiều câu chạy dở dang

**Bối cảnh:** Một sqlFile chứa 20 statement, 15 statement đầu đã tác động database rồi statement thứ 16 lỗi. Lần chạy sau báo duplicate column hoặc duplicate table.

**Cần điều tra:**

1. Kiểm tra Liquibase báo lỗi ở statement nào.
2. Đối chiếu log transaction và DBMS có DDL auto-commit không.
3. Xem những đối tượng hoặc dữ liệu nào thực sự đã thay đổi.
4. Xác minh changeset đã/ chưa được ghi trong DATABASECHANGELOG.
5. Xác định transaction boundary và **runInTransaction**.
6. Xây dựng migration sửa chữa hoặc cách khôi phục có kiểm chứng.
7. Không xóa hàng DATABASECHANGELOG hay sửa checksum bằng tay để ép rerun.

Với script dài, rủi ro này là lý do nên chia theo thay đổi nghiệp vụ/khả năng rollback, thay vì gom tất cả vào một file để tiện quản lý.

## 26. Bảng xử lý sự cố nhanh

| Triệu chứng | Nguyên nhân thường gặp | Hành động |
|---|---|---|
| Lỗi tại dấu ; trong function | SQL bị split giữa thân procedure/function | Cân nhắc splitStatements:false; một function/changeset |
| Lỗi gần GO | GO là chỉ thị client, chưa được xử lý đúng | Chia batch/đặt endDelimiter và test JDBC |
| Lỗi gần DELIMITER | Copy chỉ thị mysql CLI sang JDBC | Bỏ DELIMITER, chọn cách tách SQL phù hợp |
| Lỗi gần / sau END; | Slash Oracle được gửi sai hoặc nhận diện sai | Kiểm tra phiên bản/endDelimiter và xuống dòng |
| Một block nhiều SQL không chạy được | splitStatements:false gửi nhiều statement cùng lúc | Bật splitStatements hoặc tách changeset |
| Comment/hint biến mất | stripComments:true | Review cấu hình và SQL sinh |
| SQL không nhận diện --changeset | Đang dùng sqlFile thông thường hoặc header sai | Dùng formatted SQL changelog đúng cách |
| Dấu ; trong string gây split sai | SQL dialect/escaping hoặc parser chưa nhận đúng | Kiểm tra quote, loại SQL và preview |
| SQL chạy được trong IDE nhưng lỗi qua Liquibase | IDE xử lý batch/client directive khác | So sánh SQL JDBC thực sự được gửi |
| Changeset không xuất hiện trong update-sql | Đã chạy, bị filter, thiếu include hoặc lỗi context | Xem status, DATABASECHANGELOG và changelog gốc |
| Cú pháp SQL đúng nhưng thiếu quyền | User Liquibase khác user IDE | Xác minh username/quyền và schema |
| Rollback không chạy đúng delimiter | Rollback có parser/DBMS khác update | Kiểm tra rollback SQL và cấu hình được hỗ trợ |
| Checksum mismatch sau khi sửa SQL | Đã chỉnh changeset từng triển khai | Đối chiếu artifact cũ, thêm changeset mới |
| DDL đã thực thi một phần | DBMS tự commit hoặc transaction không bao trùm | Điều tra schema/data, chọn kế hoạch khôi phục |

Không giải quyết lỗi chỉ bằng cách chuyển tất cả SQL sang **splitStatements:false** hoặc **stripComments:true**. Một lựa chọn giúp một loại script chạy được có thể làm hỏng loại script khác.

## 27. Bài thực hành 1: phân biệt nhiều statement và nhiều changeset

**Bối cảnh:** Dịch vụ đơn hàng dùng PostgreSQL. Cần thêm bảng lưu sự kiện và index tra cứu.

### 27.1. Cách A: một changeset chứa hai statement

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "practice-001"
      author: "training-team"
      dbms: postgresql
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              -- Tạo bảng sự kiện
              CREATE TABLE training_event (
                  id BIGINT PRIMARY KEY,
                  order_id BIGINT NOT NULL
              );
              -- Thêm index cho order_id
              CREATE INDEX idx_training_event_order
              ON training_event (order_id);
      rollback:
        - sql:
            splitStatements: true
            sql: |
              DROP INDEX idx_training_event_order;
              DROP TABLE training_event;
~~~

**Câu hỏi:** Có bao nhiêu statement được gửi đi nếu Liquibase tách đúng? Có bao nhiêu changeset được quản lý trong DATABASECHANGELOG?

**Đáp án dự kiến:** Hai statement DDL, nhưng chỉ **một changeset**. Điều này không đồng nghĩa thao tác tuyệt đối nguyên tử trên mọi DBMS.

### 27.2. Cách B: hai changeset riêng

~~~sql
--liquibase formatted sql

--changeset training-team:practice-002
CREATE TABLE training_event (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
);
--rollback DROP TABLE training_event;

--changeset training-team:practice-003
CREATE INDEX idx_training_event_order
ON training_event (order_id);
--rollback DROP INDEX idx_training_event_order;
~~~

**Câu hỏi:** Nếu bảng được tạo thành công nhưng index lỗi thì lịch sử ghi nhận khác gì so với cách A?

**Đáp án:** Trong cách B, changeset tạo bảng có thể được ghi nhận thành công độc lập trước khi changeset index gặp lỗi. Trong cách A, cả hai thao tác thuộc một changeset và trạng thái sau lỗi phụ thuộc DBMS/transaction. Vì vậy, cách chia changeset là một phần của thiết kế phục hồi.

**Không chạy A và B liên tiếp trên cùng database chưa reset schema**, vì cả hai đều cố tạo bảng cùng tên. Đây là hai phương án độc lập để so sánh.

## 28. Bài thực hành 2: sửa script chứa function

**Bối cảnh:** Người học nhận một file formatted SQL PostgreSQL bị cấu hình sai:

~~~sql
--liquibase formatted sql

--changeset training-team:practice-004 splitStatements:true
CREATE OR REPLACE FUNCTION has_text(input_value TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $body$
BEGIN
    RETURN input_value IS NOT NULL
       AND length(trim(input_value)) > 0;
END;
$body$;
~~~

### Yêu cầu

1. Giải thích vì sao splitStatements:true có thể tách sai phần PL/pgSQL.
2. Viết lại marker changeset để Liquibase giữ nguyên CREATE FUNCTION.
3. Đề xuất một rollback hợp lý.
4. Mô tả trình tự kiểm chứng trước production.

### Đáp án tham khảo

~~~sql
--liquibase formatted sql

--changeset training-team:practice-004 dbms:postgresql splitStatements:false
CREATE OR REPLACE FUNCTION has_text(input_value TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $body$
BEGIN
    RETURN input_value IS NOT NULL
       AND length(trim(input_value)) > 0;
END;
$body$;

--rollback DROP FUNCTION has_text(TEXT);
~~~

Phân tích:

- Phần thân function chứa dấu **;** nhưng là một định nghĩa function.
- **splitStatements:false** nhằm giữ nguyên định nghĩa function khi gửi tới PostgreSQL.
- DROP FUNCTION theo đúng chữ ký tham số là rollback ví dụ nếu function do changeset này tạo mới.
- Nếu function đã tồn tại trước khi CREATE OR REPLACE, rollback bằng DROP FUNCTION có thể làm mất định nghĩa trước đó. Muốn rollback đúng, cần lưu và khôi phục định nghĩa cũ hoặc có kế hoạch forward fix.

Trước update cần **validate → status → update-sql → chạy thử trên PostgreSQL → gọi function kiểm tra kết quả → đối chiếu DATABASECHANGELOG**.

## 29. Tích hợp Spring Boot và CI/CD

Spring Boot có thể tự chạy Liquibase lúc khởi động hoặc dự án có thể tách migration thành một bước riêng trong pipeline.

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-staging.internal:5432/orders
    username: orders_migrator
    password: "<inject-secret-at-runtime>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

Đây là ví dụ cấu hình, không chứa secret thật. Với migration có procedure/function hoặc SQL native đặc thù, pipeline cần bảo đảm SQL file nằm trong artifact ứng dụng và JDBC driver hoặc native executor đúng với cấu hình.

### 29.1. Chuỗi kiểm soát gợi ý

1. Kiểm tra code review cho mọi thay đổi changelog và SQL file.
2. Chạy validate trên phiên bản Liquibase của môi trường triển khai.
3. Chạy status với đúng database, context/label filter.
4. Sinh **update-sql** và review dấu phân cách, comment, ranh giới statement.
5. Thử trên DBMS và driver đại diện cho production.
6. Thử rollback hoặc phương án phục hồi trên dữ liệu thử nghiệm.
7. Kiểm tra kết quả đối tượng SQL, ví dụ gọi function hoặc truy vấn view.
8. Chạy update với artifact bất biến sau phê duyệt.
9. Ghi log và deployment ID để đối chiếu lịch sử.

Không tạo một bản SQL riêng cho từng môi trường bằng cách chỉnh sửa changeset cũ đã chạy. Nên giữ cùng artifact changelog, thay đổi cấu hình kết nối và filter thông qua cơ chế của từng môi trường.

### 29.2. Trường hợp SQL preview khác thực tế

Lệnh **update-sql** thường dùng để xem SQL dự kiến nhưng không chứng minh mọi tương tác giữa executor, JDBC và DBMS sẽ thành công. Chênh lệch có thể đến từ:

- Khác phiên bản Liquibase hoặc driver giữa preview và update.
- Khác bộ filter hoặc database history.
- DDL/procedure đặc thù được xử lý khác trong executor native.
- Schema/data đã thay đổi giữa lúc preview và lúc chạy.
- Transaction và quyền khác môi trường thử nghiệm.

Vì thế, kiểm thử thực thi thật trên môi trường đại diện vẫn cần thiết.

## 30. Câu hỏi tự kiểm tra

**Câu 1. Dấu ; trong SQL có tạo changeset mới không?**  
Không. Nó thường là dấu kết thúc statement, còn changeset được xác định bởi changelog hoặc marker **--changeset** trong formatted SQL.

**Câu 2. Vì sao comment chứa dấu ; không nên làm SQL bị tách?**  
Vì comment không phải câu lệnh thực thi. Tuy nhiên, parser/định dạng cụ thể vẫn phải được kiểm chứng khi có cú pháp đặc thù.

**Câu 3. Có thể dùng splitStatements:false cho script gồm 10 lệnh SQL độc lập không?**  
Có thể cấu hình, nhưng không bảo đảm JDBC/DBMS chấp nhận nhiều statement trong một khối. Với các lệnh độc lập, thường nên split rõ hoặc tách changeset.

**Câu 4. Khi nào cần splitStatements:false?**  
Thường khi một định nghĩa procedure/function hoặc khối SQL cần gửi nguyên vẹn và có dấu chấm phẩy nội bộ.

**Câu 5. endDelimiter có giúp SQL PostgreSQL chạy trên SQL Server không?**  
Không. Nó chỉ thay đổi cách Liquibase tách SQL; cú pháp DBMS vẫn phải đúng.

**Câu 6. Tại sao GO không giống SQL thông thường?**  
Nó là batch separator được một số client SQL Server xử lý, không phải câu T-SQL độc lập mà JDBC luôn hiểu.

**Câu 7. DELIMITER // của mysql CLI có được gửi nguyên qua JDBC không?**  
Không nên. Đây là chỉ thị của client, cần chuyển sang cấu hình tách SQL hoặc cách viết tương ứng của Liquibase.

**Câu 8. stripComments:true có luôn an toàn không?**  
Không. Có comment mang ý nghĩa thực thi, chẳng hạn optimizer hint, và loại bỏ chúng có thể thay đổi hành vi SQL.

**Câu 9. Một sqlFile chứa ba câu INSERT có bao nhiêu changeset?**  
Nếu được gọi từ một changeSet trong YAML/XML/JSON, đó vẫn thường là **một changeset**, trừ khi tổ chức changelog theo cách khác.

**Câu 10. Vì sao phải kiểm tra DATABASECHANGELOG sau script thất bại?**  
Để biết changeset được ghi nhận trạng thái gì, kết hợp với việc kiểm tra database đã thay đổi một phần hay chưa trước khi quyết định rerun hoặc sửa chữa.

**Câu 11. Có thể sửa splitStatements của changeset đã chạy rồi triển khai lại không?**  
Không nên làm tùy tiện. Cần đối chiếu lịch sử, checksum và trạng thái DB; thông thường viết changeset mới cho bước cần điều chỉnh.

**Câu 12. Có thể chỉ dùng validate để khẳng định function SQL chạy đúng không?**  
Không. Phải xem SQL preview và chạy thử với DBMS/driver đích; validate không thay thế kiểm thử thực thi.

## 31. Checklist trước khi phát hành SQL phức tạp

- [ ] Đã xác định hình thức SQL: sql, sqlFile hay formatted SQL.
- [ ] Ranh giới changeset được khai báo rõ và phù hợp khả năng rollback.
- [ ] Header và các marker formatted SQL đúng cú pháp khi dùng định dạng này.
- [ ] Không nhầm comment SQL với chỉ thị Liquibase.
- [ ] Các comment đặc biệt hoặc optimizer hint được giữ khi cần.
- [ ] **stripComments** được lựa chọn có chủ đích.
- [ ] **splitStatements** được lựa chọn theo cấu trúc SQL thật.
- [ ] **endDelimiter** không xung đột string, comment hoặc thân procedure.
- [ ] Các dấu ; bên trong function/procedure không gây tách sai.
- [ ] Các ký hiệu GO, /, DELIMITER được xử lý đúng với DBMS và executor.
- [ ] Không gửi nguyên chỉ thị client thành statement SQL không hợp lệ qua JDBC.
- [ ] SQL file được đọc bằng encoding và đường dẫn đúng trong artifact.
- [ ] Không gộp nhiều thao tác rủi ro vào một changeset khó phục hồi.
- [ ] Đã phân tích transaction, DDL auto-commit và runInTransaction.
- [ ] Rollback/forward fix phù hợp với phụ thuộc và dữ liệu hiện hữu.
- [ ] Các changeset đã phát hành không bị sửa ID, đường dẫn hoặc SQL tùy tiện.
- [ ] Đã xác minh DBMS, driver, user, schema và database đích.
- [ ] Chạy validate, status và update-sql với cùng filter và artifact dự kiến.
- [ ] Review SQL được sinh, delimiter và ranh giới statement.
- [ ] Đã thực thi thử trên database đại diện, kiểm tra đối tượng và dữ liệu.
- [ ] Đã lưu log deployment và đối chiếu DATABASECHANGELOG.
- [ ] Không đưa secret hoặc dữ liệu nhạy cảm vào comments/log.
- [ ] Có kế hoạch xử lý khi script chạy dở dang.

**Kết luận:** Dấu comment, dấu chấm phẩy và delimiter không chỉ là chi tiết trình bày trong SQL khi dùng Liquibase. Chúng quyết định **SQL được chia thành những statement nào, điều gì được gửi tới executor và những thay đổi nào được quản lý trong cùng một changeset**. Thiết kế tốt cần phân biệt SQL comment với chỉ thị Liquibase, dùng **splitStatements/endDelimiter/stripComments** theo đúng loại SQL và DBMS, và luôn xác minh SQL dự kiến cùng kết quả thực thi thật. Đó là nền tảng để quản lý view, function, procedure, script SQL nhiều câu và data migration một cách có thể kiểm chứng, rollback và triển khai nhất quán qua các môi trường.

