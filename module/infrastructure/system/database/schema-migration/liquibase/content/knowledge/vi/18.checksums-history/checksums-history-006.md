# Đối chiếu runOnChange với đối tượng SQL có thể thay thế

## 1. Hai cơ chế giải quyết hai câu hỏi khác nhau

Trong module `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`, người học quản lý thay đổi schema và dữ liệu bằng Liquibase qua **changelog, changeset, precondition, checksum và lịch sử triển khai**, đồng thời thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Với view, function, procedure, trigger hoặc các đối tượng SQL có định nghĩa dài, một nhu cầu phổ biến là cập nhật định nghĩa đã tồn tại mà không tự xóa rồi tạo lại thiếu kiểm soát.

Hai khái niệm cần phân biệt:

- **`runOnChange`** là chính sách thực thi ở cấp **changeset của Liquibase**. Liquibase so sánh checksum với nội dung changeset đã ghi trong lịch sử; nếu nội dung thay đổi theo cách làm checksum thay đổi, changeset có thể được chạy lại.
- **Đối tượng SQL có thể thay thế** (*replaceable SQL object*) là khả năng ở cấp **DBMS/DDL** để thay định nghĩa một đối tượng đang tồn tại, chẳng hạn `CREATE OR REPLACE VIEW`, `CREATE OR REPLACE FUNCTION` hoặc cú pháp tương ứng của hệ quản trị.

Một cơ chế trả lời câu hỏi **khi nào Liquibase chạy lại changeset**; cơ chế kia trả lời **câu lệnh DDL xử lý đối tượng đã tồn tại như thế nào**. Chúng bổ trợ nhau, không thay thế nhau.

Ví dụ, `runOnChange: true` có thể khiến Liquibase chạy lại changeset định nghĩa view khi phần truy vấn thay đổi. Nhưng nếu SQL bên trong chỉ là `CREATE VIEW v_report AS ...`, database có thể báo view đã tồn tại. Ngược lại, `CREATE OR REPLACE VIEW` có thể thay định nghĩa view nếu được chạy trực tiếp, nhưng nếu changeset Liquibase đã được ghi nhận và không có chính sách chạy lại, Liquibase thường bỏ qua nó trong lần `update` tiếp theo. Kết hợp đúng hai lớp mới tạo ra quy trình cập nhật có chủ đích.

## 2. Checksum và vòng đời changeset

### 2.1. Danh tính và lịch sử

Một changeset thông thường được nhận diện bằng `id`, `author` và danh tính file changelog (đường dẫn/filename theo quy tắc Liquibase; `logicalFilePath` có thể giữ danh tính logic khi tổ chức file thay đổi). Khi thực thi, Liquibase ghi thông tin vào `DATABASECHANGELOG`, thường gồm `ID`, `AUTHOR`, `FILENAME`, `DATEEXECUTED`, `ORDEREXECUTED`, `EXECTYPE` và `MD5SUM`.

Checksum là dấu vết để đối chiếu nội dung changeset đã thực thi với nội dung hiện tại theo thuật toán và quy tắc của phiên bản Liquibase. Không nên hiểu checksum là phép băm byte-for-byte đơn giản của cả file. Liquibase có quy tắc chuẩn hóa và xử lý theo change type; một số thay đổi chỉ về khoảng trắng hoặc comment không làm checksum thay đổi theo cách kích hoạt `runOnChange`.

### 2.2. Hành vi mặc định

Ví dụ changeset tạo view:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-customer-summary
      author: database-team
      changes:
        - createView:
            viewName: v_customer_summary
            selectQuery: |
              SELECT customer_id, COUNT(*) AS order_count
              FROM purchase_order
              GROUP BY customer_id
~~~

Sau khi changeset đã chạy, nếu nhóm sửa câu truy vấn nhưng không bật `runOnChange`, Liquibase thường phát hiện checksum không còn khớp và báo lỗi thay vì tự coi đó là một lần cập nhật hợp lệ. Đây là cơ chế bảo vệ lịch sử: changeset đã triển khai được kỳ vọng là bất biến.

### 2.3. Bật runOnChange

Nếu việc thay định nghĩa view là một phần có chủ đích của quy trình phát hành, có thể dùng:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-customer-summary
      author: database-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_summary
            selectQuery: |
              SELECT customer_id, COUNT(*) AS order_count
              FROM purchase_order
              GROUP BY customer_id
~~~

Changeset chạy lần đầu như bình thường. Ở các lần `update` sau, nếu checksum thay đổi theo quy tắc Liquibase, changeset có thể được chạy lại. Nếu chỉ thay đổi khoảng trắng hoặc comment trong những trường hợp Liquibase loại bỏ khỏi phép tính checksum, changeset không nhất thiết chạy lại.

Khi chạy lại, Liquibase vẫn dùng danh tính changeset hiện có; đây không phải một changeset mới chỉ vì nội dung SQL thay đổi. Lịch sử có thể ghi nhận execution type như `RERAN`. Vì vậy `DATABASECHANGELOG` **không phải kho lưu đầy đủ mọi phiên bản source của view/procedure**. Muốn biết định nghĩa nào được phát hành ở từng release, cần giữ source trong Git, tag/commit và artifact phát hành.

### 2.4. runOnChange khác runAlways

| Thuộc tính | Điều kiện chạy lại | Mục đích điển hình |
|---|---|---|
| Mặc định | Chạy một lần; checksum thay đổi sau khi đã chạy thường gây lỗi | Migration schema/dữ liệu bất biến |
| `runOnChange: true` | Chạy lại khi checksum thay đổi theo quy tắc Liquibase | Định nghĩa view, procedure, function cập nhật theo source |
| `runAlways: true` | Được thực thi lại trong mỗi lần update phù hợp | Một số thao tác lặp có chủ đích, cần idempotency rõ |

Không dùng `runAlways` chỉ để “đảm bảo view luôn mới”. Nó có thể chạy lại ngay cả khi source không thay đổi, tăng thời gian deploy và tác động database. Với object SQL thay đổi theo nội dung, `runOnChange` thường phù hợp hơn vì nó phản ứng với checksum.

## 3. Đối tượng SQL có thể thay thế

Một số DBMS hỗ trợ DDL thay định nghĩa đối tượng hiện có mà không yêu cầu người viết thực hiện riêng hai bước `DROP` và `CREATE`. Ví dụ:

~~~sql
CREATE OR REPLACE VIEW v_customer_summary AS
SELECT customer_id, COUNT(*) AS order_count
FROM purchase_order
GROUP BY customer_id;
~~~

Hoặc với function trên PostgreSQL:

~~~sql
CREATE OR REPLACE FUNCTION customer_order_count(p_customer_id BIGINT)
RETURNS BIGINT
LANGUAGE SQL
AS $$
    SELECT COUNT(*)
    FROM purchase_order
    WHERE customer_id = p_customer_id
$$;
~~~

Đây là ví dụ SQL theo hệ quản trị cụ thể. Không phải mọi DBMS, phiên bản hoặc loại object đều hỗ trợ cùng cú pháp `CREATE OR REPLACE`. Có hệ quản trị dùng `CREATE OR ALTER`; có loại object cần drop/create hoặc có giới hạn khi thay kiểu trả về, danh sách cột, chữ ký tham số hay thuộc tính bảo mật.

### 3.1. Replace không đồng nghĩa xóa và tạo lại mọi thứ

Một lệnh replace/alter có thể giữ định danh object và tránh khoảng thời gian object không tồn tại, nhưng hành vi cụ thể phụ thuộc DBMS:

- Có thể giữ một số quyền, thuộc tính hoặc liên kết phụ thuộc.
- Có thể làm object phụ thuộc bị invalid và cần compile lại.
- Có thể từ chối thay đổi cấu trúc không tương thích, ví dụ đổi kiểu cột view đã công bố.
- Có thể yêu cầu quyền khác với quyền tạo object lần đầu.
- Có thể khóa metadata hoặc chờ giao dịch khác.

Không suy ra `CREATE OR REPLACE` luôn an toàn hơn `DROP` + `CREATE` trong mọi tình huống. Cần kiểm tra hành vi với loại object và DBMS thực tế.

### 3.2. replaceIfExists trong Liquibase

Một số change type Liquibase, chẳng hạn `createView` hoặc `createProcedure` trong những phiên bản hỗ trợ, có thuộc tính `replaceIfExists`. Thuộc tính này yêu cầu Liquibase tạo câu lệnh thay thế object hiện có theo khả năng của DBMS và change type.

~~~yaml
databaseChangeLog:
  - changeSet:
      id: publish-customer-summary-view
      author: database-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_summary
            replaceIfExists: true
            selectQuery: |
              SELECT customer_id, COUNT(*) AS order_count
              FROM purchase_order
              GROUP BY customer_id
~~~

Phải kiểm tra tài liệu của **đúng phiên bản Liquibase** và SQL do `update-sql` sinh ra. Thuộc tính có thể không áp dụng cho mọi DBMS hoặc mọi object; không mặc định nó luôn chuyển thành đúng cú pháp `CREATE OR REPLACE`. Nếu change type không biểu đạt được nhu cầu, có thể dùng `sql`, `sqlFile` hoặc formatted SQL với DDL riêng cho DBMS.

## 4. Kết hợp runOnChange với replaceable object

### 4.1. View qua change type

~~~yaml
databaseChangeLog:
  - changeSet:
      id: customer-summary-view
      author: database-team
      runOnChange: true
      changes:
        - createView:
            viewName: v_customer_summary
            replaceIfExists: true
            selectQuery: |
              SELECT
                  c.id AS customer_id,
                  c.full_name,
                  COUNT(o.id) AS order_count
              FROM customer c
              LEFT JOIN purchase_order o
                  ON o.customer_id = c.id
              GROUP BY c.id, c.full_name
      rollback:
        - dropView:
            viewName: v_customer_summary
~~~

Khi lần đầu triển khai, Liquibase tạo view. Khi source thay đổi làm checksum đổi, `runOnChange` cho phép changeset được xét chạy lại; `replaceIfExists` yêu cầu change type thay định nghĩa hiện tại nếu được hỗ trợ. Hai thuộc tính có trách nhiệm riêng:

- `runOnChange`: quyết định changeset có được chạy lại khi nội dung đổi không.
- `replaceIfExists`: quyết định cách change type xử lý object đã tồn tại, trong phạm vi hỗ trợ.

Rollback `dropView` trong ví dụ chỉ phù hợp nếu mục tiêu là xóa view khi rollback một lần tạo mới và không cần khôi phục định nghĩa trước đó. Nếu changeset đã thay một view cũ bằng định nghĩa mới, `dropView` **không khôi phục định nghĩa cũ**; nó xóa view. Cần chọn chiến lược rollback phù hợp ở mục 8.

### 4.2. Stored procedure trong file riêng

Với procedure dài, nhóm thường giữ SQL trong file riêng để dễ review:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: recalculate-customer-balance
      author: database-team
      runOnChange: true
      changes:
        - createProcedure:
            procedureName: recalculate_customer_balance
            path: procedures/recalculate_customer_balance.sql
            relativeToChangelogFile: true
            replaceIfExists: true
~~~

Đây là ví dụ hình thức; xác nhận `replaceIfExists`, `path` và mức hỗ trợ của change type trong phiên bản Liquibase đang dùng. File SQL phải có DDL tương thích DBMS và được đóng gói cùng changelog. Nếu dùng `sqlFile` thay cho `createProcedure`, cần khai báo `splitStatements`, `endDelimiter` hoặc tùy chọn tương ứng phù hợp với body có nhiều dấu chấm phẩy.

Với SQL thủ công:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: recalculate-customer-balance
      author: database-team
      runOnChange: true
      dbms: postgresql
      changes:
        - sqlFile:
            path: procedures/recalculate_customer_balance.sql
            relativeToChangelogFile: true
            splitStatements: false
~~~

Ở ví dụ này, file SQL phải tự chứa DDL thay thế phù hợp PostgreSQL, ví dụ `CREATE OR REPLACE FUNCTION` hoặc procedure đúng cú pháp/chữ ký. `sqlFile` không tự biến `CREATE PROCEDURE` thành lệnh replace chỉ vì changeset có `runOnChange: true`.

### 4.3. Formatted SQL

~~~sql
--liquibase formatted sql

--changeset database-team:customer-summary-view runOnChange:true dbms:postgresql
CREATE OR REPLACE VIEW v_customer_summary AS
SELECT customer_id, COUNT(*) AS order_count
FROM purchase_order
GROUP BY customer_id;

--rollback DROP VIEW IF EXISTS v_customer_summary;
~~~

Đây là ví dụ PostgreSQL. Directive `runOnChange:true` thuộc metadata Liquibase; câu `CREATE OR REPLACE VIEW` là SQL DBMS. Nếu thay đổi view đã tồn tại và cần rollback về định nghĩa cũ, dòng rollback phải được thiết kế để **khôi phục source cũ** thay vì chỉ drop object. Nếu không có một định nghĩa cũ rõ ràng, nên chọn cách quản lý version khác.

## 5. Bảng đối chiếu hai lớp

| Tiêu chí | runOnChange | Replaceable SQL object / replaceIfExists |
|---|---|---|
| Cấp độ | Chính sách changeset Liquibase | DDL/change type ở cấp object DBMS |
| Câu hỏi trả lời | Khi nào changeset đã chạy được phép chạy lại? | Object đã tồn tại thì câu lệnh thay định nghĩa bằng cách nào? |
| Điều kiện kích hoạt | Checksum thay đổi theo quy tắc Liquibase | Câu lệnh replace/alter được thực thi |
| Tự phát hiện source đổi? | Có, qua checksum changeset | Không; DDL không theo dõi file changelog |
| Tự chạy changeset? | Không; cần một lệnh Liquibase update phù hợp | Không; cần runner thực thi câu lệnh |
| Bảo đảm object tồn tại? | Không | Tùy DDL/change type và trạng thái DBMS |
| Portable giữa DBMS? | Chính sách có tính khái quát, nhưng checksum/change type theo phiên bản | Không; cú pháp và khả năng phụ thuộc DBMS |
| Bảo toàn grants/dependencies? | Không quyết định | Phụ thuộc DDL và DBMS |
| Rollback định nghĩa cũ? | Không tự lưu source cũ | Không tự lưu source cũ |
| Nhu cầu version control | Cần giữ source thay đổi | Cần giữ source/DDL thay thế và phiên bản object |

**Kết luận thực hành:** nếu cần Liquibase phát hiện source thay đổi và chạy lại changeset, dùng `runOnChange`; nếu DDL cần thay định nghĩa object đã tồn tại, dùng `CREATE OR REPLACE`, `CREATE OR ALTER`, `replaceIfExists` hoặc cơ chế DBMS phù hợp. Với view/procedure/function thay đổi thường xuyên, thường cần cả hai lớp.

## 6. Khác biệt theo hệ quản trị

Không có một câu SQL replaceable duy nhất cho mọi DBMS. Bảng dưới đây là định hướng; phải kiểm tra phiên bản, edition và loại object:

| Hệ quản trị | Cách tiếp cận thường gặp | Điều cần kiểm tra |
|---|---|---|
| PostgreSQL | `CREATE OR REPLACE VIEW`, `CREATE OR REPLACE FUNCTION`; procedure có cú pháp riêng theo phiên bản | View không thể tùy ý thay kiểu/tên cột hiện có; function có giới hạn chữ ký/return type; dependency |
| MySQL | `CREATE OR REPLACE VIEW` được hỗ trợ; stored routine thường cần quy trình drop/create theo khả năng cụ thể | Không giả định procedure/function có `OR REPLACE` như view; quyền, delimiter và tác động tới routine |
| SQL Server | Các phiên bản hiện đại có `CREATE OR ALTER VIEW/PROCEDURE` | Phiên bản tối thiểu, batch syntax; `GO` là batch separator của client, không phải T-SQL statement thông thường |
| Oracle | `CREATE OR REPLACE VIEW/PROCEDURE/FUNCTION/PACKAGE` theo loại object | Object phụ thuộc có thể invalid cần compile; chữ ký, edition, quyền và transaction DDL |

### 6.1. PostgreSQL

`CREATE OR REPLACE VIEW` thường phù hợp để cập nhật định nghĩa view, nhưng không cho phép mọi biến đổi cấu trúc. Thay kiểu một cột view hiện có hoặc đổi tên theo cách không tương thích có thể bị từ chối; một số thay đổi như thêm cột ở cuối có thể được hỗ trợ. Nếu cần thay đổi contract của view, hãy lập kế hoạch cho consumer, tạo view version mới hoặc migration chuyển tiếp.

Với function, thay body trong khi giữ chữ ký tương thích là tình huống điển hình. Đổi return type hoặc kiểu tham số có thể đòi hỏi drop/recreate và xem xét object phụ thuộc. Function/procedure có thể được gọi bởi view, trigger hoặc ứng dụng; phải kiểm tra dependency trước khi thay.

### 6.2. MySQL

MySQL hỗ trợ cú pháp replace cho view, nhưng không nên suy rộng rằng mọi stored procedure/function đều có cùng `CREATE OR REPLACE`. Với routine, có thể cần drop rồi tạo lại; việc này có thể ảnh hưởng quyền `EXECUTE`, metadata, dependency hoặc khoảng thời gian object không tồn tại. Cần xem xét `DELIMITER` của client và cách Liquibase tách statements; `DELIMITER` thường là lệnh của client MySQL chứ không phải câu SQL server thực thi.

### 6.3. SQL Server

SQL Server hiện đại hỗ trợ dạng `CREATE OR ALTER` cho một số object như view và procedure. Cú pháp có yêu cầu vị trí đầu batch; `GO` là dấu phân cách batch do client/tool hiểu, không phải câu lệnh T-SQL server. Khi dùng Liquibase, phải xác định `splitStatements`, `endDelimiter` và cách gửi batch. Không copy nguyên script SSMS có nhiều `GO` vào `sqlFile` rồi giả định Liquibase xử lý giống SSMS.

### 6.4. Oracle

Oracle có nhiều DDL `CREATE OR REPLACE` cho object lập trình. Thay procedure/package có thể khiến object phụ thuộc phải compile lại hoặc tạm ở trạng thái invalid cho đến khi dependency được xử lý. Kiểm tra catalog object, lỗi compile và grants theo quyền hiện hành. Với package specification/body, thứ tự cập nhật và compatibility giữa public contract với implementation đặc biệt quan trọng.

## 7. Giữ changeset ổn định và quản lý source

### 7.1. Giữ danh tính changeset

Một changeset `runOnChange` vẫn là cùng một changeset trong lịch sử. Không đổi `id`, `author` hoặc tùy tiện chuyển file chỉ để kích hoạt lần chạy mới. Nếu di chuyển file, danh tính `FILENAME` có thể thay đổi; cần đánh giá `logicalFilePath` và lịch sử đã triển khai.

Với object SQL được lưu trong file riêng, đường dẫn phải ổn định, file phải được đóng gói và nội dung được quản lý cùng release. Một file sửa trên máy developer nhưng không nằm trong artifact CI/CD sẽ làm kết quả giữa môi trường khác nhau.

### 7.2. runOnChange không phát hiện drift trong database

Nếu người quản trị sửa trực tiếp view/procedure trong database, Liquibase không tự đọc định nghĩa DBMS rồi đồng bộ ngược vào source. Lần `update` sau chỉ xét nội dung changelog và checksum; nếu checksum không đổi, changeset có thể không chạy lại dù object thực tế đã bị sửa thủ công.

Để phát hiện drift, cần quy trình so sánh định nghĩa object thực tế với source phát hành, hoặc dựng lại database từ changelog trong môi trường kiểm chứng. `runOnChange` không thay thế schema drift detection.

### 7.3. Whitespace, comment và checksum

Liquibase có quy tắc checksum bỏ qua một số khác biệt chỉ về khoảng trắng/comment; vì vậy chỉnh format SQL hoặc thêm comment không nhất thiết kích hoạt `runOnChange`. Đây là hành vi có chủ đích để tránh chạy lại object chỉ vì thay đổi trình bày. Nếu cần thay đổi thật, hãy thay nội dung logic; không thêm ký tự vô nghĩa để cố kích hoạt checksum.

### 7.4. Không dùng clearCheckSums để ép rerun

`clearCheckSums` làm Liquibase xóa các checksum đã lưu để tính lại ở lần chạy phù hợp tiếp theo; nó không phải cách chuẩn để phát hành định nghĩa view/procedure mới. Chạy lệnh này thiếu kiểm soát có thể che dấu thay đổi ngoài ý muốn trên nhiều changeset. Với object được quản lý bằng `runOnChange`, hãy sửa source có review và để Liquibase đối chiếu checksum theo chính sách.

## 8. Rollback: object thay thế không tự lưu phiên bản cũ

Khi `CREATE OR REPLACE VIEW` thay định nghĩa cũ, database thường giữ một object hiện tại với source mới; nó không tự lưu snapshot đầy đủ của source trước đó để Liquibase khôi phục.

### 8.1. Vì sao DROP VIEW không phải rollback đúng cho mọi lần rerun?

Giả sử release 1 tạo `v_customer_summary` với định nghĩa A, release 2 thay bằng B nhờ `runOnChange`, release 3 gặp sự cố và muốn quay lại A. Nếu rollback chỉ là `DROP VIEW v_customer_summary`, kết quả là view biến mất, **không phải** quay về A. Nếu rollback viết lại định nghĩa A, điều đó có thể phù hợp khi quay từ B về A, nhưng lại không phù hợp khi rollback lần đầu tạo object trên database chưa từng có A.

Phải xác định rollback mong muốn là:

1. Xóa object được tạo lần đầu.
2. Khôi phục định nghĩa source ngay trước release.
3. Khôi phục một contract version đã biết.
4. Thực hiện forward-fix bằng release mới thay vì rollback.

### 8.2. Hai chiến lược quản lý phiên bản

| Chiến lược | Cách làm | Phù hợp khi |
|---|---|---|
| Mutable definition với `runOnChange` | Một changeset quản lý source hiện hành; mỗi lần source đổi, Liquibase chạy lại | Object là implementation cập nhật thường xuyên; nhóm lưu source trong Git và có chiến lược rollback riêng |
| Immutable changeset theo release | Mỗi thay đổi định nghĩa là changeset mới, có rollback/forward version cụ thể | Cần audit từng lần thay đổi, rollback chính xác hoặc phê duyệt theo release |

Một view nội bộ có thể dùng mutable definition; procedure ảnh hưởng thanh toán hoặc báo cáo pháp lý có thể cần lịch sử release bất biến và rollback rõ ràng hơn.

### 8.3. Thiết kế rollback cho replaceable object

Với object có thể thay thế, rollback nên có định nghĩa source đích rõ ràng:

- Giữ source phiên bản trước trong Git và xây dựng rollback script được review.
- Dùng changeset release mới để phục hồi object về contract cũ.
- Nếu rollback lần đầu tạo object, drop object chỉ khi không có consumer/dependency và việc xóa là đúng mục đích.
- Với routine không thể thay thế trực tiếp trên DBMS, lập kế hoạch drop/create và quyền cần thiết.

Không viết rollback giả định có thể khôi phục bất kỳ phiên bản trước nào mà không lưu phiên bản đó. Nếu cần rollback lặp lại chính xác, immutable changeset hoặc release artifact có version thường minh bạch hơn.

## 9. Dependency, grants và tính tương thích

Một view hoặc routine có thể được nhiều thành phần sử dụng: view khác, function, procedure, trigger, job, ứng dụng Spring Boot, báo cáo BI hoặc script vận hành. Thay body có thể giữ nguyên tên object nhưng vẫn thay đổi contract: số cột, tên/kiểu cột, nullability, ý nghĩa kết quả, exception, side effect, thời gian chạy hoặc quyền cần thiết.

### 9.1. Implementation-only và contract change

**Implementation-only:** tối ưu câu truy vấn, thêm điều kiện nội bộ không đổi kết quả công bố, sửa thuật toán nhưng giữ chữ ký/contract. Đây là trường hợp phù hợp hơn với `runOnChange` + replace nếu DBMS hỗ trợ.

**Contract change:** đổi tên cột view, kiểu trả về, thứ tự tham số, quyền thực thi, semantics hoặc side effect. Đây thường là thay đổi ảnh hưởng consumer và nên được quản lý như migration có version, có giai đoạn chuyển đổi và kiểm thử tương thích.

### 9.2. Thứ tự dependency

Nếu view gọi function, function phải được tạo/cập nhật trước view trong luồng changelog. Nếu routine thay chữ ký, cần xem tất cả consumer phụ thuộc. Không để context/label filter loại mất changeset tạo dependency nhưng vẫn cho changeset replace object phía sau chạy.

Trên một số DBMS, replace object có thể đánh dấu object phụ thuộc invalid hoặc làm thay đổi metadata; kiểm tra compile status và thực thi smoke test sau deploy. Cũng cần kiểm tra grants: cách giữ hoặc thay quyền có thể khác giữa `CREATE OR REPLACE`, `CREATE OR ALTER` và drop/create.

## 10. Kiểm chứng trước và sau triển khai

### 10.1. Quy trình Liquibase

Với đúng cấu hình DBMS và changelog:

~~~bash
liquibase --defaults-file=config/liquibase-test.properties validate
liquibase --defaults-file=config/liquibase-test.properties status --verbose
liquibase --defaults-file=config/liquibase-test.properties update-sql
~~~

Đối với `runOnChange`, phải tạo tình huống kiểm chứng có source **đã thay đổi** so với checksum đã lưu. Nếu database thử nghiệm đã có changeset nhưng source giống hệt, preview có thể không chứa SQL thay thế — đó là kết quả đúng. Có thể dùng database bản sao ở trạng thái trước release để kiểm tra lần đầu và lần rerun.

### 10.2. Kiểm tra ba trạng thái

| Trạng thái database | Source changeset | Kết quả mong đợi ở mức khái niệm |
|---|---|---|
| Object/changelog chưa được triển khai | Source version A | Chạy lần đầu để tạo object |
| Đã triển khai version A | Source vẫn là A | Không rerun nếu checksum không đổi |
| Đã triển khai version A | Source chuyển sang B | `runOnChange` cho phép rerun nếu checksum khác; DDL phải thay object đúng cách |

Sau `update` thật, kiểm tra:

1. Object tồn tại, đúng owner/schema và trạng thái hợp lệ.
2. Định nghĩa object tương ứng source version mong muốn.
3. View trả đúng schema/cột/kết quả; procedure/function có chữ ký và quyền đúng.
4. Các consumer chính chạy được.
5. `DATABASECHANGELOG` ghi nhận changeset và lần rerun đúng dự kiến, chẳng hạn `EXECTYPE` phù hợp.
6. Metrics, lock, thời gian thực thi và lỗi compile nằm trong giới hạn.

### 10.3. Đối chiếu object thực tế

Ví dụ trên PostgreSQL:

~~~sql
SELECT schemaname, viewname, definition
FROM pg_views
WHERE viewname = 'v_customer_summary';

SELECT n.nspname, p.proname, pg_get_functiondef(p.oid)
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.proname = 'customer_order_count';
~~~

Tên catalog, quyền xem và truy vấn khác nhau giữa DBMS; không dùng truy vấn PostgreSQL trên SQL Server/Oracle/MySQL. Đối chiếu định nghĩa đã triển khai với source artifact và chạy smoke test với dữ liệu đại diện.

## 11. Spring Boot và CI/CD

### 11.1. Source object phải đi cùng artifact

Spring Boot có thể chạy Liquibase qua cấu hình:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
~~~

File SQL được tham chiếu phải có trong JAR/container ở đúng path. Một file tồn tại trên máy developer nhưng bị thiếu khỏi artifact có thể khiến production thất bại. CI cần kiểm tra packaging và digest của source SQL, không chỉ kiểm tra YAML.

### 11.2. Pipeline cho object dùng runOnChange

1. Review diff source view/procedure/function và changeset.
2. Kiểm tra contract: cột, kiểu, tham số, quyền, dependency và side effect.
3. Chạy `validate`, `status --verbose`, `update-sql` với đúng DBMS/version/context/label.
4. Thử triển khai lần đầu và lần source thay đổi trên database test.
5. Kiểm tra object definition, compile status, grants và smoke tests.
6. Tạo bản rollback/forward-fix và thử trên database an toàn.
7. Phát hành artifact bất biến, áp dụng migration bằng đúng Liquibase runner.
8. Đối chiếu `DATABASECHANGELOG` và object thực tế sau deploy.

### 11.3. Nhiều replica

Khi ứng dụng Spring Boot tự chạy Liquibase lúc startup, mọi replica cần dùng cùng artifact, phiên bản Liquibase, extension, cấu hình và database. `DATABASECHANGELOGLOCK` giúp tuần tự hóa runner cùng chia sẻ bảng lock, nhưng không giải quyết trường hợp một replica dùng source mới còn replica khác dùng source cũ hoặc khác context. Với object quan trọng, một job migration riêng trước rollout ứng dụng giúp kiểm soát thứ tự và phê duyệt rõ hơn.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Checksum mismatch sau khi sửa view/procedure | Changeset không bật `runOnChange` hoặc thay đổi không thuộc loại được cho phép | Xác định changeset đã phát hành; thêm changeset mới hoặc dùng chính sách `runOnChange` có chủ đích |
| `runOnChange` rerun nhưng báo object đã tồn tại | SQL dùng `CREATE` thường, không có replace/alter phù hợp | Dùng `replaceIfExists` được hỗ trợ hoặc DDL native đúng DBMS |
| Source đổi nhưng không rerun | Checksum không đổi do chỉ thay whitespace/comment hoặc file tham chiếu không được cập nhật | Kiểm tra checksum, source path, artifact và nội dung |
| `replaceIfExists` không sinh SQL như mong đợi | Change type/version/DBMS không hỗ trợ hoặc property không đúng vị trí | Xem tài liệu phiên bản và output `update-sql` |
| PostgreSQL từ chối replace view | Thay đổi cột/kiểu không tương thích với view hiện tại | Dùng view version mới hoặc migration contract theo giai đoạn |
| SQL Server lỗi batch/GO | SQL script dùng batch separator của client không tương thích runner | Thiết kế `endDelimiter`/`splitStatements` theo Liquibase và DBMS |
| MySQL routine bị gián đoạn khi deploy | Drop/create không có kế hoạch quyền hoặc failure giữa hai bước | Kiểm tra DDL, quyền, backup source và khoảng gián đoạn |
| Object invalid sau khi thay | Dependency hoặc compile error | Kiểm tra catalog, compile errors và thứ tự changeset |
| Rollback chỉ xóa object | Rollback dùng `dropView`/`dropProcedure` thay vì source cũ | Khôi phục định nghĩa version trước hoặc forward-fix |
| History chỉ có một row dù object thay nhiều lần | `runOnChange` giữ danh tính changeset, không lưu mọi source version | Dùng Git/tag/artifact; nếu cần audit từng release, dùng changeset bất biến |
| Local chạy nhưng production thiếu file SQL | Tài nguyên không được đóng gói hoặc path phụ thuộc working directory | Kiểm tra JAR/container và `relativeToChangelogFile` |

Không dùng `clearCheckSums`, đổi `id` hoặc sửa tay `DATABASECHANGELOG` để che một thay đổi chưa được review. Hãy xác định source nào được phát hành, object thực tế ra sao và trạng thái lịch sử trước khi sửa.

## 13. Chọn chiến lược theo loại object

| Object / tình huống | Chiến lược thường cân nhắc | Lý do |
|---|---|---|
| View nội bộ, definition thay đổi thường xuyên nhưng contract ổn định | `runOnChange` + `createView`/`replaceIfExists` nếu được hỗ trợ | Dễ cập nhật source theo checksum |
| Stored procedure có body thay đổi nhưng chữ ký ổn định | `runOnChange` + replace/alter DDL phù hợp DBMS | Giữ một source hiện hành, kiểm soát lần rerun |
| Function có return type/chữ ký thay đổi | Changeset mới hoặc versioned function | Có thể không thay thế trực tiếp được; cần chuyển consumer |
| View public được nhiều ứng dụng sử dụng | Immutable changeset/versioned view hoặc rollout theo contract | Cần audit và tương thích ngược |
| Trigger có side effect quan trọng | Review dependency, transaction và behavior kỹ; cân nhắc changeset bất biến | Thay đổi có thể ảnh hưởng mọi thao tác ghi |
| Object đặc thù DBMS | SQL native có `dbms` filter và test riêng | DDL không portable |
| Yêu cầu rollback chính xác từng release | Changeset mới cho mỗi version và rollback source rõ ràng | Lịch sử không phụ thuộc một source mutable |

## 14. Checklist trước khi merge

- [ ] Đã xác định đây là thay đổi implementation hay thay đổi public contract.
- [ ] Hiểu `runOnChange` là chính sách rerun theo checksum, không phải cú pháp replace object.
- [ ] Xác định change type có hỗ trợ `replaceIfExists` trên phiên bản/DBMS thực tế hay cần SQL native.
- [ ] DDL dùng đúng cú pháp `CREATE OR REPLACE`, `CREATE OR ALTER` hoặc drop/create theo DBMS.
- [ ] Giữ `id`, `author`, danh tính file và `logicalFilePath` ổn định.
- [ ] Source SQL và changelog được version hóa, đóng gói cùng artifact.
- [ ] Đã kiểm tra khác biệt checksum; không dựa vào thay đổi whitespace/comment để kích hoạt rerun.
- [ ] Đã rà soát dependency, grants, owner, chữ ký, kiểu trả về, cột view và consumer.
- [ ] `validate`, `status --verbose`, `update-sql` và thử rerun trên database test đạt.
- [ ] Đã xác minh object definition và smoke test sau update thật.
- [ ] Rollback khôi phục đúng version cũ hoặc có forward-fix được phê duyệt; không nhầm `DROP` với restore.
- [ ] Đã chọn mutable `runOnChange` hay immutable changesets theo yêu cầu audit/rollback.
- [ ] CI/CD và Spring Boot dùng cùng version Liquibase, DBMS, artifact, properties và filters.
- [ ] Không sửa changeset đã triển khai ngoài chính sách đã thống nhất, không sửa tay metadata để bỏ qua checksum.

**Kết luận:** `runOnChange` và đối tượng SQL có thể thay thế giải quyết hai lớp khác nhau. Liquibase dùng checksum để quyết định **có chạy lại changeset hay không**; DBMS và change type quyết định **cách thay định nghĩa object đã tồn tại**. Kết hợp chúng đúng cách giúp quản lý view, function và procedure thay đổi theo source, nhưng vẫn cần xét khả năng của từng DBMS, dependency, grants, checksum, lịch sử, rollback và version control. Với object có contract quan trọng hoặc yêu cầu audit/rollback chính xác, changeset bất biến theo release có thể phù hợp hơn một source mutable. Đây là cách đưa quản lý object SQL vào quy trình có kiểm chứng của `DATABASE_SCHEMA_MIGRATION_LIQUIBASE`.
