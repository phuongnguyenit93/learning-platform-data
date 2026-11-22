
# Tách câu lệnh bằng splitStatements và endDelimiter trong Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase dùng changelog và changeset để quản lý thay đổi schema, dữ liệu, precondition, checksum, rollback và lịch sử triển khai. Khi một changeset chứa SQL viết tay, Liquibase cần biết **đâu là ranh giới giữa các câu lệnh** trước khi gửi chúng cho JDBC driver hoặc công cụ thực thi SQL. Hai cấu hình quan trọng nhất trong bối cảnh này là **splitStatements** và **endDelimiter**.

Bài thuộc chương **SQL và đối tượng** giải thích cơ chế tách câu lệnh, cách sử dụng với sql, sqlFile và formatted SQL, các tình huống procedure/function/trigger, sự khác nhau giữa dấu kết thúc SQL và dấu kết thúc do Liquibase cấu hình, cũng như cách kiểm chứng migration trong Spring Boot hoặc CI/CD. Điểm cần nắm không chỉ là cú pháp: **tách sai có thể khiến một migration hợp lệ về nghiệp vụ thất bại, hoặc tệ hơn là chỉ thực thi một phần và để database ở trạng thái khó khôi phục**.

## 1. Hiểu đúng ba tầng: changelog, changeset và SQL statement

Trong Liquibase, một **changelog** chứa các changeset; một **changeset** có thể chứa một hay nhiều change; một change loại **sql** hoặc **sqlFile** có thể chứa nhiều câu SQL.

~~~text
Master changelog
    |
    +-- changeset 001
    |      +-- createTable
    |
    +-- changeset 002
           +-- sql / sqlFile
                   |
                   +-- SQL statement A
                   +-- SQL statement B
                   +-- SQL statement C
~~~

Ba phạm vi này không đồng nghĩa:

- **Changeset** là đơn vị có định danh id + author + đường dẫn changelog, được Liquibase đối chiếu với DATABASECHANGELOG.
- **SQL statement** là một đơn vị cú pháp mà database/JDBC có thể thực thi, chẳng hạn một lệnh CREATE TABLE hoặc UPDATE.
- **Delimiter** là tín hiệu giúp xác định điểm kết thúc statement trong văn bản SQL. Một số delimiter dùng trong công cụ client, không phải cú pháp SQL mà database nhận trực tiếp.

Nếu một changeset chứa ba statement, điều đó **không tạo ra ba bản ghi lịch sử changeset**. Liquibase vẫn ghi nhận kết quả ở phạm vi changeset. Ngược lại, nếu một statement thất bại sau khi statement khác đã thành công, việc phục hồi phụ thuộc transaction, DBMS và cấu hình migration, không phụ thuộc số lượng bản ghi trong changelog.

## 2. splitStatements thực sự điều khiển điều gì?

**splitStatements** là thuộc tính boolean của các change SQL thích hợp, quy định Liquibase có chia một khối SQL thành nhiều statement trước khi gửi đến tầng thực thi hay không.

| Cấu hình | Ý nghĩa | Dùng khi nào |
|---|---|---|
| splitStatements: true | Liquibase phân tích khối SQL và tách theo quy tắc delimiter đang áp dụng | Các tệp chứa nhiều lệnh DDL/DML thông thường |
| splitStatements: false | Không chủ động tách khối SQL thành nhiều statement qua cơ chế này; chuyển khối cho executor theo cách tương ứng | SQL procedural, block có dấu chấm phẩy nội bộ hoặc executor xử lý script riêng |
| Không khai báo | Dựa vào mặc định của change type, định dạng changelog và phiên bản/cách sinh changelog | Chỉ nên để mặc định khi hành vi đã được kiểm chứng |

Với SQL nhiều câu lệnh viết tay, nên **khai báo tường minh** thay vì dựa vào một mặc định có thể khác khi đổi từ YAML sang formatted SQL hoặc khi một công cụ sinh changelog.

**splitStatements: false không làm nhiều câu lệnh trở thành một câu SQL hợp lệ.** Nếu Liquibase gửi nguyên khối gồm hai câu lệnh tới JDBC, driver và DBMS có thể chấp nhận hoặc từ chối. Không dùng false như giải pháp chung khi chỉ đơn giản muốn chạy hai lệnh độc lập; hãy dùng true và delimiter phù hợp.

## 3. endDelimiter làm gì và không làm gì?

**endDelimiter** chỉ định chuỗi được Liquibase sử dụng để xác định nơi một statement kết thúc trong những tình huống nó đang chịu trách nhiệm tách SQL. Giá trị thường gặp:

- Dấu chấm phẩy **;** cho các statement SQL thông thường.
- Một token tùy chọn như **$$** khi dấu chấm phẩy đã xuất hiện bên trong thân thủ tục/hàm.
- Một delimiter theo quy ước DBMS hoặc công cụ thực thi, ví dụ **GO** ở một dòng riêng trong một số kịch bản SQL Server, với hành vi cụ thể phải kiểm tra theo phiên bản Liquibase.

Ví dụ cấu hình trong YAML:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-simple-sql
      author: schema-team
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              CREATE TABLE audit_event (
                  id BIGINT PRIMARY KEY,
                  event_type VARCHAR(50) NOT NULL
              );
              CREATE INDEX idx_audit_event_type
                  ON audit_event (event_type);
~~~

Ở đây Liquibase được yêu cầu tách hai statement theo dấu **;**. Nó không có nghĩa Liquibase tạo hai changeset, cũng không tự định nghĩa một transaction cho từng câu.

**Không nhầm endDelimiter với lệnh DELIMITER của MySQL CLI.** Trong MySQL client, DELIMITER $$ là chỉ thị để **client** thay đổi ký hiệu phân tách, không phải câu lệnh DDL tiêu chuẩn của server. Với Liquibase JDBC, thường cấu hình endDelimiter trong changelog và không gửi chỉ thị DELIMITER của client như một statement SQL.

## 4. Delimiter mặc định và những giả định cần kiểm tra

Đối với quá trình tách SQL thường gặp, Liquibase hỗ trợ dấu **;** và có thể nhận diện **GO** khi token này nằm trên một dòng riêng. Tuy nhiên, quy tắc phân tích thực tế còn tùy phiên bản, loại changelog và executor.

Không nên suy luận chỉ dựa trên tên delimiter rằng mọi dấu chấm phẩy ở mọi vị trí trong text đều sẽ bị cắt ngay. Với một số cách phân tích, dấu chấm phẩy ở cuối dòng là tín hiệu quan trọng; dấu nằm trong string literal hoặc procedural block cần được kiểm tra riêng.

Ví dụ những dòng này có ý nghĩa khác nhau:

~~~sql
INSERT INTO audit_event (id, event_type)
VALUES (1, 'user;created');

INSERT INTO audit_event (id, event_type)
VALUES (2, 'user-updated');
~~~

Dấu chấm phẩy **trong chuỗi** 'user;created' là dữ liệu, không phải dấu kết thúc statement. Một parser phù hợp cần nhận biết ngữ cảnh của chuỗi. Dù vậy, không mặc định mọi dialect, dollar-quote, comment hoặc cú pháp procedural đều được bộ tách của mọi phiên bản Liquibase hiểu giống nhau.

**Quy tắc thực hành:** với SQL đơn giản, dùng dấu ; và splitStatements: true. Với procedural SQL chứa dấu ; nội bộ, hãy chọn một cơ chế rõ ràng hơn và kiểm chứng trên đúng DBMS.

## 5. Ví dụ YAML: hai statement trong một change sql

Giả sử bảng customer đã tồn tại và có các cột id, status. Nhóm cần cập nhật dữ liệu cũ và tạo index, có thể viết:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-01-customer-status-migration
      author: schema-team
      comment: >-
        Chuẩn hóa các giá trị status cũ và thêm index hỗ trợ tra cứu.
        Việc thay đổi dữ liệu cần được kiểm chứng trước khi chạy production.
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            stripComments: false
            sql: |
              UPDATE customer
              SET status = 'ACTIVE'
              WHERE status IS NULL;

              CREATE INDEX idx_customer_status
              ON customer (status);
~~~

Với cấu hình này, Liquibase sẽ phân tách và đưa các statement đến executor theo trình tự. Thao tác UPDATE và CREATE INDEX vẫn thuộc **cùng một changeset**.

Đây chỉ là ví dụ giảng giải. Đối với migration thực tế, thường nên tách bước sửa dữ liệu và tạo index thành hai changeset để dễ review, dễ tái chạy trong các trường hợp đặc biệt và tránh một precondition/rollback chung bao phủ hai mục đích.

Nếu một câu DDL sau UPDATE thất bại, dữ liệu có tự được khôi phục hay không còn phụ thuộc DBMS và khả năng transaction đối với DDL. Không thể kết luận rollback chỉ từ splitStatements: true.

## 6. sql và sqlFile: cùng ý nghĩa, khác nơi đặt nội dung

**sql** chứa câu lệnh ngay trong changelog. **sqlFile** trỏ đến tệp SQL bên ngoài. Cả hai đều cần xem xét splitStatements và endDelimiter khi xử lý nhiều câu lệnh.

### 6.1. SQL inline

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-02-create-index-inline
      author: schema-team
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              CREATE INDEX idx_customer_email
              ON customer (email);
~~~

### 6.2. SQL nằm trong file riêng

Cấu trúc tham khảo:

~~~text
src/main/resources/db/changelog/
  db.changelog-master.yaml
  changes/
    20261119-03-load-data.yaml
  scripts/
    20261119-03-load-data.sql
~~~

Nội dung changes/20261119-03-load-data.yaml:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-03-load-data
      author: schema-team
      changes:
        - sqlFile:
            path: ../scripts/20261119-03-load-data.sql
            relativeToChangelogFile: true
            encoding: UTF-8
            splitStatements: true
            endDelimiter: ";"
            stripComments: false
~~~

Nội dung scripts/20261119-03-load-data.sql:

~~~sql
INSERT INTO customer_type (code, description)
VALUES ('INDIVIDUAL', 'Khách hàng cá nhân');

INSERT INTO customer_type (code, description)
VALUES ('BUSINESS', 'Khách hàng tổ chức');
~~~

Giả định bảng customer_type và khóa dữ liệu đã được thiết kế phù hợp. Đường dẫn **relativeToChangelogFile: true** được giải quyết từ tệp YAML chứa sqlFile, không phải mặc định từ thư mục chạy ứng dụng. Tệp script phải được đóng gói hoặc tồn tại trong search path/classpath mà Liquibase sử dụng.

Điểm cần kiểm tra thêm: encoding thực tế của script, ký tự BOM, xuống dòng CRLF/LF, cách executor đọc tài nguyên và trường hợp tệp nằm trong JAR. Một script đọc được tại local nhưng không đi vào artifact có thể khiến migration thất bại trong Spring Boot/CI.

## 7. Formatted SQL: cấu hình trên dòng changeset

Với Liquibase formatted SQL changelog, metadata đặt trong comment đặc biệt, ví dụ:

~~~sql
--liquibase formatted sql

--changeset schema-team:20261119-04 splitStatements:true endDelimiter:;
--comment: Tạo bảng audit và index liên quan.
CREATE TABLE audit_event (
    id BIGINT PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL
);
CREATE INDEX idx_audit_event_type
ON audit_event (event_type);

--rollback DROP INDEX idx_audit_event_type;
--rollback DROP TABLE audit_event;
~~~

Dòng **--changeset** chứa id/author và các thuộc tính Liquibase. Các dòng **--rollback** trong formatted SQL khai báo SQL rollback theo cách định dạng này hỗ trợ. Dấu -- trong SQL thông thường không biến mọi comment thành metadata; chỉ những marker có cú pháp phù hợp mới được Liquibase xử lý.

Khi dùng formatted SQL, cần đặc biệt phân biệt:

- **--liquibase formatted sql** xác định loại changelog.
- **--changeset** bắt đầu changeset và khai báo các tùy chọn, trong đó có splitStatements/endDelimiter.
- **--rollback** mô tả SQL hoàn tác chứ không phải một câu SQL của update thông thường.
- Delimiter trong phần update và rollback có thể có yêu cầu khác nhau nếu rollback là block/procedure.

Tùy phiên bản Liquibase, có thể có thuộc tính riêng để quy định delimiter cho rollback của formatted SQL. Không giả định rằng thay đổi endDelimiter của forward SQL luôn xử lý được cú pháp rollback. Hãy validate và preview cả hai chiều theo phiên bản đang dùng.

## 8. Vì sao thủ tục, hàm và trigger dễ bị tách sai?

Trong một SQL statement có cấu trúc phức tạp, bên trong có thể xuất hiện nhiều dấu chấm phẩy:

~~~text
CREATE PROCEDURE ...
BEGIN
    UPDATE ...;
    INSERT ...;
    IF ... THEN
        ...;
    END IF;
END;
~~~

Toàn bộ khối CREATE PROCEDURE có thể là **một statement được database hiểu**, còn các dấu ; bên trong phân tách các câu lệnh thuộc thân procedure. Nếu Liquibase tách nhầm theo ; ở bên trong, JDBC có thể nhận được nửa câu CREATE PROCEDURE, lỗi cú pháp hoặc các câu SQL rời rạc không hợp lệ.

Hai cách xử lý phổ biến:

1. **Không tách (splitStatements: false)** khi khối SQL thực sự là một statement phức tạp và executor/driver có thể gửi nguyên khối đến DBMS.
2. **Dùng một endDelimiter riêng** như $$, đặt token đó sau toàn bộ definition, giữ splitStatements: true. Dùng cách này khi cú pháp và executor của dự án hỗ trợ.

Không có lựa chọn duy nhất cho mọi DBMS. PostgreSQL có dollar-quoted string, MySQL có cú pháp stored routine riêng, Oracle có PL/SQL block và SQL Server có khái niệm batch. Cần thử với đúng database và công cụ thực thi.

## 9. PostgreSQL: DO block với dấu chấm phẩy nội bộ

Ví dụ một khối PostgreSQL:

~~~sql
DO $block$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = 'idx_customer_email'
    ) THEN
        RAISE NOTICE 'Index does not exist';
    END IF;
END
$block$;
~~~

Đây là **một DO statement** theo cú pháp PostgreSQL nhưng bên trong có các dấu chấm phẩy. Nếu công cụ tách SQL theo dấu ; mà không hiểu ngữ cảnh dollar-quote, nội dung có thể bị cắt sai.

Một cách khai báo thử nghiệm là:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-05-pg-do-block
      author: schema-team
      dbms: postgresql
      comment: Kiểm tra khối SQL procedural được gửi như một đơn vị
      changes:
        - sql:
            splitStatements: false
            sql: |
              DO $block$
              BEGIN
                  RAISE NOTICE 'Liquibase procedural block';
              END
              $block$;
~~~

Với cấu hình này, Liquibase không cố tách khối qua splitStatements. Nhưng thành công vẫn phụ thuộc PostgreSQL driver, quyền truy cập và cú pháp cụ thể. Nếu tệp chứa nhiều DO block độc lập, đừng mặc định splitStatements: false sẽ thực thi tất cả đúng ý.

Đặc biệt, dấu **$$** hoặc **$block$** còn là ký hiệu dollar-quote trong PostgreSQL; nó không tự đồng nghĩa với endDelimiter của Liquibase. Khi quyết định endDelimiter riêng, cần bảo đảm token lựa chọn không va chạm với nội dung bên trong khối.

## 10. MySQL: đặt delimiter riêng cho CREATE PROCEDURE

Trong MySQL, một CREATE PROCEDURE có thể chứa nhiều statement bên trong BEGIN ... END. Ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-06-mysql-procedure
      author: schema-team
      dbms: mysql
      comment: Tạo thủ tục tổng hợp trạng thái đơn hàng
      changes:
        - sql:
            splitStatements: true
            endDelimiter: "$$"
            sql: |
              CREATE PROCEDURE sp_refresh_order_status()
              BEGIN
                  UPDATE purchase_order
                  SET status = 'PENDING'
                  WHERE status IS NULL;

                  UPDATE purchase_order
                  SET updated_at = CURRENT_TIMESTAMP
                  WHERE status = 'PENDING';
              END$$
      rollback:
        - sql:
            sql: DROP PROCEDURE IF EXISTS sp_refresh_order_status
~~~

Với cách tổ chức này, Liquibase được yêu cầu tìm delimiter **$$** để nhận ra điểm kết thúc toàn bộ định nghĩa procedure thay vì cắt từng dấu chấm phẩy bên trong.

Ví dụ minh họa cơ chế, **chưa phải thủ tục sẵn dùng cho production**: giả định bảng purchase_order và các cột status/updated_at đã tồn tại, xem xét quyền CREATE ROUTINE, lock, rollback và dữ liệu thực tế. SQL body và tính tương thích phải được kiểm tra trên đúng MySQL version.

Nếu SQL được lấy từ script chạy thủ công trong MySQL CLI, script đó có thể chứa:

~~~sql
DELIMITER $$
CREATE PROCEDURE ...
BEGIN
    ...
END$$
DELIMITER ;
~~~

**DELIMITER là chỉ thị của MySQL client**, không phải phần bắt buộc khi chạy qua Liquibase JDBC. Thường nên loại bỏ hai dòng DELIMITER của client và khai báo endDelimiter ở metadata của Liquibase. Nếu dùng native executor gọi chính client, nguyên tắc có thể khác: phải theo hành vi của công cụ thực thi thực tế.

Không trộn dấu kết thúc $$ với ; một cách thiếu kiểm soát giữa các changeset. Tài liệu hóa delimiter của từng change và kiểm tra SQL được executor tiếp nhận.

## 11. SQL Server: GO là dấu chia batch, không phải lệnh T-SQL

Trong nhiều script SQL Server, **GO** được SQL Server tooling dùng như một batch separator:

~~~sql
CREATE TABLE dbo.audit_event (
    id BIGINT NOT NULL PRIMARY KEY,
    event_type NVARCHAR(50) NOT NULL
);
GO

CREATE INDEX idx_audit_event_type
ON dbo.audit_event (event_type);
GO
~~~

Trong SQL Server, GO thường **không phải câu lệnh được database engine thực thi trực tiếp qua JDBC**. Công cụ client phân chia script thành các batch trước khi gửi đến server. Liquibase có cơ chế nhận diện GO ở những tình huống tách SQL, nhưng không nên giả định mọi chuỗi “GO” trong văn bản đều là delimiter: vị trí trên dòng và chế độ parser có ý nghĩa.

Ví dụ SQL dùng GO trên dòng riêng nên được kiểm tra với splitStatements và phiên bản Liquibase cụ thể. Nếu đặt splitStatements: false rồi gửi nguyên script chứa GO qua JDBC, database có thể báo lỗi vì nhận thấy token GO không hợp lệ.

Một số statement SQL Server cần là câu lệnh đầu tiên trong batch. Khi gặp lỗi loại này, hãy kiểm tra **batch boundary** chứ không chỉ thêm dấu ;. Tách changeset hoặc script thành các khối nhỏ, được kiểm chứng trên SQL Server, thường dễ kiểm soát hơn sửa delimiter theo cảm tính.

## 12. Oracle và dấu gạch chéo riêng dòng

Các tệp Oracle PL/SQL thường chứa dấu ; bên trong khối và dấu **/** ở một dòng riêng theo quy ước của SQL*Plus để kết thúc/thi hành block. Ví dụ mô hình:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Migration sample');
END;
/
~~~

Dấu **/** này có thể mang ý nghĩa đặc biệt trong công cụ Oracle client. Với Liquibase, cách diễn giải slash đã có khác biệt giữa các phiên bản/cách xử lý và khi dùng native executor. Không nên kết luận rằng slash luôn là delimiter đúng cho mọi phiên bản Liquibase, hoặc cứ đặt endDelimiter: "/" là giải quyết xong.

Một quy trình phù hợp:

1. Xác định chạy bằng JDBC hay Oracle native executor.
2. Ghim và ghi nhận phiên bản Liquibase.
3. Xem cách phiên bản đó xử lý slash trên dòng riêng.
4. Chọn splitStatements/endDelimiter tương thích với script PL/SQL.
5. Kiểm tra preview SQL và chạy thử một procedure/block trên Oracle test.
6. Kiểm tra lại rollback, đặc biệt nếu thao tác thuộc DDL không có tính transaction như kỳ vọng.

Ví dụ dành cho Oracle phải được thử trên Oracle thật; không sử dụng H2 như bằng chứng rằng PL/SQL và slash sẽ hoạt động đúng.

## 13. endDelimiter không phải là ký tự phải thêm vào mọi file

Cấu hình endDelimiter: "$$" thể hiện một **quy ước phân tách**; nó chỉ hữu ích khi nội dung SQL và cách gọi Liquibase thống nhất với quy ước đó.

Ba tình huống cần phân biệt:

| Tình huống | Hệ quả cần chú ý |
|---|---|
| endDelimiter=";" và nội dung dùng ; giữa các câu SQL | Phù hợp với nhiều script DDL/DML thông thường |
| endDelimiter="$$" nhưng SQL không chứa $$ tại ranh giới mong muốn | Có thể không tách như dự kiến hoặc tạo khối không được xử lý đúng |
| endDelimiter="$$" nhưng $$ cũng xuất hiện bên trong string/procedure body | Có nguy cơ nhận nhầm ranh giới nếu parser và dialect không được xử lý phù hợp |

Không chọn một token dài, ngẫu nhiên rồi cho rằng parser sẽ luôn an toàn. Chọn delimiter rõ ràng, dễ kiểm tra trong code review và không xung đột với SQL body.

Nếu dùng shell để truyền delimiter như $$ qua tham số CLI, cần chú ý **shell quoting**: trong một số shell, ký hiệu $ có ý nghĩa đặc biệt, làm giá trị truyền đến Liquibase khác với chuỗi dự định. Khi cấu hình delimiter qua YAML/XML, giá trị thường dễ giữ nguyên hơn.

## 14. stripComments có liên quan gì đến tách câu lệnh?

**stripComments** điều khiển việc giữ hoặc loại bỏ SQL comments khi Liquibase xử lý SQL. Nó không tương đương splitStatements, nhưng **comment có thể làm người đọc hoặc bộ phân tích ranh giới câu lệnh hiểu nhầm**, nhất là khi script đặt dấu ; ở cuối comment.

Ví dụ:

~~~sql
-- Thêm nhãn trạng thái mặc định;
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Nếu một cơ chế tách SQL nhận nhầm delimiter ở comment, statement có thể bị cắt sai. Quy tắc cụ thể còn phụ thuộc parser và phiên bản. Cách viết dễ bảo trì là tránh chèn delimiter ở cuối dòng comment và dùng script được review.

Giữ stripComments: false có thể cần thiết cho các **SQL hints** đặc thù DBMS viết dưới dạng comment, ví dụ optimizer hints. Nếu bật loại bỏ comments mà không đánh giá, script có thể mất một gợi ý quan trọng hoặc thay đổi hành vi hiệu năng.

Ngược lại, stripComments: true không phải phương án chắc chắn sửa mọi lỗi parser. Nếu SQL body chứa trigger/procedure với delimiter nội bộ, cần xử lý ở cấp SQL script và executor, thay vì chỉ thay đổi việc loại bỏ comments.

## 15. Tách câu lệnh khác với transaction và rollback

Ba khái niệm thường bị gộp nhầm:

- **splitStatements:** Liquibase chia nội dung SQL thành các statement như thế nào.
- **runInTransaction:** Changeset có được Liquibase cố gắng thực thi trong transaction hay không, khi DBMS hỗ trợ.
- **rollback:** Những thao tác nào được dùng để hoàn tác thay đổi theo quy tắc Liquibase, DBMS và cách nhóm khai báo.

Giả sử có hai statement:

~~~sql
UPDATE customer SET status = 'ACTIVE' WHERE status IS NULL;
ALTER TABLE customer ADD CONSTRAINT ck_customer_status
    CHECK (status IN ('ACTIVE', 'INACTIVE'));
~~~

Với splitStatements: true, Liquibase có thể thực thi lần lượt hai statement. Nếu statement thứ hai lỗi, liệu UPDATE được rollback hay không phụ thuộc hỗ trợ transaction của DBMS đối với DML/DDL kết hợp và cấu hình hiện tại.

Một số thao tác cần không nằm trong transaction block. Ví dụ **CREATE INDEX CONCURRENTLY** trên PostgreSQL có yêu cầu riêng, và changeset có thể cần runInTransaction: false. Điều này **không có nghĩa** phải đặt splitStatements: false. Hai thuộc tính giải quyết hai bài toán khác nhau.

Khi dùng runInTransaction: false cho changeset có nhiều statement, nếu câu đầu thành công còn câu sau thất bại, database có thể ở trạng thái thực thi một phần; lịch sử changeset và schema có thể cần xử lý phục hồi đặc biệt. Nên giữ mỗi changeset đủ nhỏ và có quy trình kiểm chứng, không dùng false tùy tiện để “chạy được script”.

## 16. Rollback cũng có thể chứa nhiều câu SQL

Một changeset sql/sqlFile thường cần rollback **tường minh** nếu Liquibase không thể tự sinh rollback an toàn cho SQL viết tay. Rollback có thể dùng các change type đảo ngược hoặc đoạn SQL riêng.

Ví dụ viết rollback bằng change type:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261119-07-create-audit-objects
      author: schema-team
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              CREATE TABLE audit_event (
                  id BIGINT PRIMARY KEY,
                  event_type VARCHAR(50) NOT NULL
              );
              CREATE INDEX idx_audit_event_type
              ON audit_event (event_type);
      rollback:
        - dropIndex:
            indexName: idx_audit_event_type
            tableName: audit_event
        - dropTable:
            tableName: audit_event
~~~

Các change type rollback ở ví dụ giúp diễn đạt thứ tự đảo ngược: bỏ index rồi xóa bảng. Tuy vậy, **dropTable là thao tác phá hủy** và sẽ làm mất dữ liệu nếu bảng đã nhận bản ghi. Cần chọn mốc rollback và đánh giá dữ liệu trước khi thực thi trên database có dữ liệu thật.

Nếu rollback là một khối SQL riêng có nhiều statement hoặc procedure, quy tắc tách/delimiter của rollback cũng cần được cấu hình/kiểm tra phù hợp. Không mặc định forward SQL dùng $$ thì rollback SQL dùng ; sẽ tự được suy ra chính xác.

Trước rollback quan trọng, dùng lệnh sinh SQL rollback tương ứng với phiên bản Liquibase để review và thử trên database đại diện. Không chỉ nhìn vào việc changelog có khai báo rollback.

## 17. Native executor và JDBC executor: ai chịu trách nhiệm phân tách?

Liquibase có thể thực thi SQL bằng các cơ chế khác nhau tùy cách triển khai và tính năng được cấp phép:

| Cơ chế | Đặc điểm | Lưu ý về delimiter |
|---|---|---|
| JDBC executor | Liquibase phân tích SQL và gửi qua driver | splitStatements/endDelimiter có vai trò trực tiếp đối với sql/sqlFile |
| Native executor như psql, SQL*Plus, sqlcmd (khi được hỗ trợ) | SQL được chuyển cho công cụ client của DBMS | Công cụ native có quy tắc phân tách riêng; tránh xung đột do Liquibase tự tách |
| Công cụ triển khai SQL khác | Pipeline có thể chạy SQL được Liquibase sinh hoặc tệp bên ngoài | Phải hiểu rõ ai tách statement ở bước cuối cùng |

Khi dùng **native executor**, không nên bật splitStatements hoặc đặt endDelimiter một cách máy móc như với JDBC. Công cụ native thường tự xử lý delimiter/batch theo ngôn ngữ client, và việc yêu cầu Liquibase tách thêm có thể làm thay đổi script.

Nếu một thay đổi chỉ chạy được khi copy vào psql nhưng không chạy qua Liquibase JDBC, chưa chắc SQL sai; có thể script chứa những lệnh meta của psql hoặc ranh giới statement không tương thích JDBC. Ngược lại, script Liquibase có endDelimiter tùy chỉnh chưa chắc copy nguyên vẹn vào một SQL client là chạy được.

Vì vậy, **trước khi chỉnh delimiter phải xác định executor thực sự**. Quyết định này cũng ảnh hưởng lệnh validate, preview SQL, rollback và log chẩn đoán trong pipeline.

## 18. Chính sách delimiter chung và cấu hình ưu tiên

Trong dự án nhiều changelog, nhóm có thể muốn quy định delimiter mặc định theo công cụ hoặc cấu hình triển khai. Một số phiên bản/edition Liquibase hỗ trợ các tùy chọn delimiter ở phạm vi rộng hơn change, cùng quy tắc ưu tiên đối với endDelimiter tại changeset.

Tuy nhiên, không nên trộn một tùy chọn CLI/global mới với những ví dụ từ phiên bản khác rồi suy luận về thứ tự ưu tiên. Trước khi dựa vào delimiter toàn cục:

1. Ghim phiên bản Liquibase/edition đang sử dụng.
2. Xác định cấu hình được chấp nhận ở cấp **change**, **changeset** và **global** theo tài liệu phiên bản đó.
3. Kiểm tra giá trị hiệu lực trên các đường chạy CLI, Maven, Gradle và Spring Boot.
4. Test một file SQL đơn giản và một file procedural có delimiter riêng.
5. Ghi lại cấu hình trong runbook/CI, không chỉ trong máy cá nhân.

**Khuyến nghị cho bài học:** với sql/sqlFile đặc biệt, khai báo splitStatements/endDelimiter **cục bộ, tường minh**, tránh sự phụ thuộc vô hình vào biến môi trường hoặc flags chỉ tồn tại trên một runner.

Không sửa attributes của changeset đã triển khai tùy tiện: thay đổi nội dung hoặc cách parse có thể ảnh hưởng checksum và lịch sử; với migration đã chạy cần kiểm tra trên bản sao database trước khi thay đổi cấu hình.

## 19. Những sai lầm và triệu chứng phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Lỗi syntax gần BEGIN, IF hoặc END | Khối procedure bị tách theo dấu ; ở bên trong | Kiểm tra splitStatements và endDelimiter, thử block như một đơn vị |
| Lỗi syntax gần GO trên SQL Server | Token GO được chuyển thẳng cho JDBC thay vì được coi là batch separator | Xác minh executor và quy tắc nhận diện GO trên dòng riêng |
| Lỗi gần DELIMITER trong MySQL JDBC | Sao chép script chứa chỉ thị của MySQL CLI | Loại chỉ thị DELIMITER khỏi SQL gửi JDBC, dùng metadata endDelimiter |
| Procedure chưa hoàn chỉnh | Dùng ; làm delimiter khi thân procedure chứa ; | Dùng delimiter riêng hoặc splitStatements:false phù hợp |
| Không tách các lệnh CREATE TABLE và CREATE INDEX | Đặt splitStatements:false cho script nhiều statement | Đặt true và dấu phân tách tương ứng; hoặc tách thành change riêng |
| SQL file không được tìm thấy | Sai path/search path hoặc resource không đóng gói | Kiểm tra relativeToChangelogFile và artifact |
| Lỗi ký tự tiếng Việt hoặc BOM | Encoding script không khớp | Khai báo encoding, kiểm tra file UTF-8 và runner |
| Comment gây parse sai | Có delimiter ở cuối comment hoặc syntax comment đặc thù | Dọn comment, kiểm tra stripComments và SQL preview |
| Rollback lỗi dù update thành công | Rollback dùng delimiter/SQL dialect khác | Kiểm tra rollback SQL riêng trên DBMS đích |
| Migration chỉ chạy một phần | DDL autocommit hoặc runInTransaction:false | Đọc log, schema thật, lịch sử; lập phương án forward fix |
| Chạy local được nhưng CI lỗi | Executor, phiên bản Liquibase, driver hoặc quoting khác | Ghim versions và test trên cùng runner/configuration |
| Checksum mismatch sau khi chỉnh SQL | Đã sửa changeset được ghi nhận | Đối chiếu revision cũ; tạo changeset mới thay vì sửa migration đã phát hành |
| SQL có dấu ; trong string bị cắt sai | Parser/dialect hoặc quoting không được hiểu như dự kiến | Thu nhỏ case, thử SQL đúng DBMS, cân nhắc splitStatements:false |
| Native executor chạy khác JDBC | Một bên dùng delimiter client, một bên dùng Liquibase parser | Không trộn hai loại cấu hình; chọn cơ chế chạy chính |

Không xử lý lỗi bằng cách xóa row trong DATABASECHANGELOG hoặc chỉnh EXECTYPE. Trước tiên xác định đúng changeset id/author/filename, revision changelog, câu SQL đã gửi, transaction và schema thực tế. Chỉ khi biết rõ trạng thái mới chọn rollback, forward fix hoặc phục hồi từ bản sao lưu.

## 20. Quy trình kiểm chứng trước khi chạy migration thật

Các bước kiểm chứng nên làm theo thứ tự, đặc biệt với procedure/trigger hoặc SQL nhiều statement:

**Bước 1 — Đọc changelog và xác định loại change.** Phân biệt change SQL inline, sqlFile và formatted SQL. Xác nhận splitStatements, endDelimiter, stripComments được khai báo ở vị trí phù hợp.

**Bước 2 — Xác định DBMS và executor.** Ghi nhận PostgreSQL/MySQL/Oracle/SQL Server, phiên bản DBMS và driver, Liquibase version, JDBC hay native executor.

**Bước 3 — Kiểm tra script thô.** Xác định dấu ; bên trong string, comment, function/procedure; các token GO, /, $$; mọi lệnh client không phải SQL.

**Bước 4 — Chạy validate.** Kiểm tra changelog có thể được parse; không đồng nhất validate thành công với việc database sẽ chấp nhận SQL.

**Bước 5 — Sinh SQL dự kiến.** Dùng lệnh update-sql/updateSQL theo công cụ và phiên bản; quan sát số lượng statement, thứ tự và nội dung. Lưu ý: SQL preview không phải lúc nào cũng thể hiện hoàn toàn từng thao tác nội bộ của native executor.

**Bước 6 — Chạy trên database thử nghiệm.** Dùng database cùng sản phẩm và phiên bản gần production. Kiểm tra sau thực thi có đúng bảng, index, function/procedure hay không.

**Bước 7 — Kiểm tra lịch sử.** Đối chiếu DATABASECHANGELOG; nếu update dừng giữa chừng, xác nhận những lệnh nào thực sự đã tác động đến schema và dữ liệu.

**Bước 8 — Kiểm tra rollback hoặc forward fix.** Với SQL phức tạp, sinh SQL rollback, thử trên bản sao và xác nhận dữ liệu được giữ đúng mức cần thiết.

**Bước 9 — Kiểm thử nâng cấp từ release trước.** Ngoài database trống, chạy migration trên bản database có dữ liệu và lịch sử Liquibase thực tế.

**Bước 10 — Promote cùng revision.** Chỉ phát hành changelog/artifact đã kiểm tra; không tự thay delimiter hoặc nội dung script giữa staging và production.

Mục tiêu là trả lời rõ ba câu hỏi trước khi update: **Liquibase sẽ phân tách ra những statement nào? Database có chấp nhận chúng không? Nếu thất bại, trạng thái có thể được xác minh và khôi phục thế nào?**

## 21. Tích hợp với Spring Boot, Maven, Gradle và CI/CD

Một dự án Spring Boot có thể khai báo master changelog:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USER}
    password: ${DB_PASSWORD}
  liquibase:
    change-log: classpath:db/changelog/db.changelog-master.yaml
    enabled: true
~~~

Từ master, Liquibase đọc các changeset sql/sqlFile kèm splitStatements/endDelimiter. Khi chạy cùng ứng dụng, cơ chế mặc định thường dùng JDBC qua datasource. Cách điều phối migration phải rõ ràng để tránh nhiều replica đồng thời cố thực thi thay đổi.

Nếu nhóm chạy Liquibase bằng Maven plugin, Gradle plugin hoặc CLI trong CI/CD, nên bảo đảm:

- Mọi cách chạy trỏ đến **cùng master changelog và revision đã review**.
- Cấu hình executor, resource path, encoding, phiên bản Liquibase và JDBC driver nhất quán.
- Pipeline tách bước **validate / status / update-sql / review / update**.
- Credentials được cấp từ secret store, không đưa vào changelog hoặc log.
- Không biến mọi lần build/package thành một lần tự động update database production.
- Với SQL procedural, có test trên DBMS thật và tài khoản quyền tương ứng.
- Với native executor, kiểm tra sớm sự khác biệt về delimiter thay vì chỉ thử JDBC local.

Giữ cùng một changelog không đủ nếu staging chạy bằng JDBC còn production chạy qua công cụ native với quy tắc batch khác. Sự khác biệt này phải được kiểm soát bằng thử nghiệm và cấu hình deployment.

## 22. Bài thực hành: ba trường hợp phân tách SQL

Thực hành chỉ trên database disposable và dưới quyền thích hợp, không dùng production.

### Tình huống A — Hai statement DDL thông thường

Khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-001-two-statements
      author: lab-team
      changes:
        - sql:
            splitStatements: true
            endDelimiter: ";"
            sql: |
              CREATE TABLE demo_event (
                  id BIGINT PRIMARY KEY,
                  event_code VARCHAR(40) NOT NULL
              );
              CREATE INDEX idx_demo_event_code
              ON demo_event (event_code);
      rollback:
        - dropIndex:
            indexName: idx_demo_event_code
            tableName: demo_event
        - dropTable:
            tableName: demo_event
~~~

Kỳ vọng: trên DBMS hỗ trợ cú pháp, Liquibase phân tách hai statement; cả bảng và index xuất hiện; DATABASECHANGELOG ghi **một changeset**, không phải hai.

### Tình huống B — Một block PostgreSQL có dấu ; nội bộ

Khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-002-pg-block
      author: lab-team
      dbms: postgresql
      changes:
        - sql:
            splitStatements: false
            sql: |
              DO $lab$
              BEGIN
                  RAISE NOTICE 'line 1';
                  RAISE NOTICE 'line 2';
              END
              $lab$;
~~~

Kỳ vọng: khối được gửi như một đơn vị phù hợp PostgreSQL. Kiểm tra log và bản ghi lịch sử. Không diễn giải hai dấu ; trong thân DO như hai changeset.

### Tình huống C — Một procedure MySQL có delimiter riêng

Khai báo:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: lab-003-mysql-procedure
      author: lab-team
      dbms: mysql
      changes:
        - sql:
            splitStatements: true
            endDelimiter: "$$"
            sql: |
              CREATE PROCEDURE sp_demo_event()
              BEGIN
                  SELECT 'first';
                  SELECT 'second';
              END$$
      rollback:
        - sql:
            sql: DROP PROCEDURE IF EXISTS sp_demo_event
~~~

Kỳ vọng: hai dấu ; trong thân procedure không làm block bị cắt thành các statement độc lập; token $$ được dùng làm điểm kết thúc procedure. Kiểm tra procedure thực sự được tạo và có thể gọi trên MySQL test.

Sau đó thử cố ý đổi endDelimiter về ; trong tình huống C trên một database thử nghiệm **mới**, rồi quan sát lỗi khi parser/executor tách sai. Không sửa một changeset đã được ghi nhận ở database chia sẻ chỉ để làm bài thực hành.

### Bảng kết quả nên tự ghi

| Tình huống | DBMS | splitStatements | endDelimiter | Kết quả mong đợi |
|---|---|---|---|---|
| A: hai DDL đơn giản | DBMS được change type/SQL hỗ trợ | true | ; | Tạo bảng và index; một changeset trong lịch sử |
| B: PostgreSQL DO block | PostgreSQL | false | Không cần delimiter riêng để Liquibase tách | DO block là một đơn vị thực thi |
| C: MySQL procedure | MySQL | true | $$ | Procedure được nhận như một định nghĩa hoàn chỉnh |

Các kịch bản độc lập; không nên chạy tuần tự trên cùng một database không có schema chuẩn bị tương ứng. Đặt expectation rõ ràng giúp phân biệt lỗi SQL với lỗi parser hoặc DBMS.

## 23. Checklist trước khi merge một changeset SQL

- [ ] Đã xác định change là sql, sqlFile hay formatted SQL.
- [ ] Đã biết executor thực tế là JDBC hay native.
- [ ] Đã ghi rõ splitStatements nếu có nhiều SQL statement hoặc procedural block.
- [ ] endDelimiter phù hợp nội dung SQL, không xung đột với string/body.
- [ ] Không nhầm chỉ thị DELIMITER/GO hoặc slash của client với SQL server thông thường.
- [ ] Đã kiểm tra dấu ; trong comment, string literal, procedure và trigger.
- [ ] Nếu dùng sqlFile, đường dẫn, encoding và resource trong artifact đều đúng.
- [ ] SQL nhánh chuyên biệt được lọc theo dbms phù hợp.
- [ ] Đã đánh giá runInTransaction và đặc điểm transaction/DDL của DBMS.
- [ ] Có rollback hoặc phương án forward fix được kiểm thử.
- [ ] Đã chạy validate và sinh SQL dự kiến với đúng configuration.
- [ ] Đã test trên DBMS/driver/executor giống môi trường triển khai.
- [ ] Đã test cả database mới và database có lịch sử, dữ liệu cũ.
- [ ] Không sửa SQL của changeset đã triển khai; thay đổi mới đi bằng changeset mới.
- [ ] Đã đối chiếu DATABASECHANGELOG và đối tượng database sau update.
- [ ] Quy trình CI/CD ghi lại revision, DBMS, executor và kết quả kiểm thử.
- [ ] Không đánh giá thành công chỉ từ việc Liquibase không báo lỗi; phải kiểm tra schema và dữ liệu.

**Ghi nhớ:** **splitStatements** xác định Liquibase có chủ động chia khối SQL hay không, còn **endDelimiter** giúp chỉ định ranh giới câu lệnh khi cơ chế tách được sử dụng. Dấu ; thường phù hợp với DDL/DML đơn giản, nhưng procedure, function, trigger, SQL Server batch và các script dành cho công cụ client đòi hỏi hiểu rõ DBMS và executor. Hãy dùng cấu hình tường minh, kiểm tra trên database thật, giữ changeset đã phát hành bất biến và có phương án rollback/forward fix có kiểm chứng.

