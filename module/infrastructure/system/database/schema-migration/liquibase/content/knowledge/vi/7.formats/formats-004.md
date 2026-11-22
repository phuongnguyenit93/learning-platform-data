# Viết formatted SQL với changeset và chỉ thị Liquibase

**Formatted SQL** là cách viết changelog Liquibase ngay trong tệp SQL: người phát triển dùng cú pháp SQL quen thuộc để thay đổi schema hoặc dữ liệu, đồng thời chèn các **chỉ thị Liquibase** dưới dạng comment có cấu trúc. Nhờ các chỉ thị này, Liquibase có thể nhận diện từng changeset, xác định điều kiện áp dụng, phân biệt nội dung SQL chính với rollback và ghi lịch sử triển khai vào DATABASECHANGELOG.

Bài học thuộc chương **Định dạng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng tới việc nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào **cách viết và đọc formatted SQL**, là một trong những lựa chọn định dạng changelog của Liquibase.

Sau khi học, bạn có thể tự tạo tệp formatted SQL hợp lệ, giải thích từng chỉ thị quan trọng, thiết kế migration có rollback và precondition, xử lý delimiter cho SQL phức tạp, và kiểm tra changeset trước khi phát hành qua nhiều môi trường.

## 1. Formatted SQL khác SQL thuần như thế nào?

Một tệp SQL thuần có thể chỉ gồm câu lệnh:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
~~~

Nếu một công cụ thực thi SQL trực tiếp chạy lại tệp này trên cùng database, câu lệnh có thể thất bại vì bảng đã tồn tại. Tệp không tự mô tả đơn vị migration, người tạo, lịch sử đã thực thi hay cách rollback.

Tệp **Liquibase formatted SQL** bổ sung một header và marker changeset:

~~~sql
--liquibase formatted sql

--changeset db-team:20261119-001
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);

--rollback DROP TABLE customer;
~~~

Các dòng bắt đầu bằng **hai dấu gạch ngang** là comment hợp lệ của SQL, nhưng Liquibase nhận diện những comment có cú pháp chỉ thị riêng. Trong ví dụ:

- **--liquibase formatted sql** nhận diện định dạng tệp.
- **--changeset db-team:20261119-001** bắt đầu một changeset, với author là **db-team** và id là **20261119-001**.
- **CREATE TABLE ...** là phần SQL được áp dụng khi changeset đủ điều kiện chạy.
- **--rollback DROP TABLE customer;** khai báo SQL đảo ngược cho changeset.

Khi chạy **update**, Liquibase đọc changelog, đối chiếu changeset với DATABASECHANGELOG và xử lý những thay đổi cần thiết. Sau khi thành công, Liquibase ghi lại thông tin changeset trên database đích. Khi chạy **rollback**, Liquibase dùng thông tin rollback hoặc cơ chế rollback được hỗ trợ; không thể mặc định rằng mọi câu lệnh SQL tùy ý đều có rollback tự động.

### Khi nào nên dùng formatted SQL?

Nên cân nhắc formatted SQL khi nhóm làm việc chủ yếu bằng SQL, cần kiểm soát chính xác câu lệnh theo DBMS hoặc muốn người quản trị database dễ review mã SQL gốc. Nó rất phù hợp cho một số index, view, procedure, migration dữ liệu và thao tác mà SQL thủ công diễn đạt rõ nhất.

Các định dạng YAML, XML và JSON có ưu thế khi muốn dùng những change type trừu tượng của Liquibase, chẳng hạn **createTable**, **addColumn** hoặc **createIndex**, để Liquibase sinh SQL phù hợp hơn giữa các DBMS. Formatted SQL đòi hỏi người viết tự chịu trách nhiệm nhiều hơn về cú pháp SQL, khả năng tương thích, transaction và rollback.

| Khía cạnh | Formatted SQL | Changelog YAML/XML/JSON |
|---|---|---|
| Phần thay đổi chính | Câu lệnh SQL do người viết kiểm soát | Thường dùng change type của Liquibase; cũng có thể chứa SQL |
| Đơn vị quản lý | Marker **--changeset** | Phần tử hoặc object **changeSet** |
| Tham số thực thi | Comment chỉ thị sau marker | Thuộc tính trong cấu trúc khai báo |
| Rollback | Thường khai báo SQL rollback | Có thể dùng change type hoặc SQL rollback |
| Khả năng đa DBMS | Phụ thuộc SQL được viết | Một số change type được Liquibase chuyển đổi theo DBMS |
| Cách review | Gần với SQL thực thi | Dễ tập trung vào ý nghĩa thay đổi và metadata |

Cả hai cách đều có thể tham gia một hệ thống migration được quản lý bằng Liquibase.

## 2. Cấu trúc tối thiểu và quy tắc nhận diện

Tệp formatted SQL nên bắt đầu trực tiếp bằng dòng:

~~~sql
--liquibase formatted sql
~~~

Dòng này phải ở đầu tệp để bộ đọc của Liquibase nhận diện định dạng đúng. Trong thực tế nên lưu **UTF-8**, không thêm byte order mark (BOM), dòng trống hay comment tùy ý trước header nếu chưa kiểm tra khả năng nhận diện của phiên bản đang dùng.

Sau header là một hoặc nhiều changeset, thường theo mẫu:

~~~text
--liquibase formatted sql

--changeset AUTHOR:ID [thuộc-tính:tùy-chọn ...]
<CÁC CÂU LỆNH SQL>

--rollback <CÂU LỆNH ĐẢO NGƯỢC>
~~~

**AUTHOR:ID** là cặp bắt buộc trong marker changeset. Dấu hai chấm ngăn cách tác giả và ID. Ví dụ:

~~~sql
--changeset billing-team:add-payment-reference-001
~~~

Không nên thay marker bằng comment thông thường kiểu:

~~~sql
-- migration 001: create payment table
~~~

Vì Liquibase sẽ không tự coi comment mô tả đó là một marker changeset.

### 2.1. Một tệp có thể chứa nhiều changeset

Ví dụ có hai thay đổi liên tiếp:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-001
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
--rollback DROP TABLE customer;

--changeset customer-team:20261119-002
CREATE INDEX idx_customer_email ON customer (email);
--rollback DROP INDEX idx_customer_email;
~~~

Liquibase xử lý các changeset theo thứ tự xuất hiện trong tệp trong luồng changelog đã được nạp, đồng thời xem xét lịch sử, context, label, DBMS và các điều kiện liên quan. Nếu changeset đầu chưa tạo bảng thì changeset tạo index không thể chạy thành công; thứ tự là một phần của thiết kế migration.

### 2.2. Vì sao phải đặt marker đúng vị trí?

Ranh giới changeset được nhận diện từ marker **--changeset** tới marker tiếp theo hoặc cuối tệp. Chỉ thị rollback thuộc về changeset tương ứng. Nếu đặt marker nhầm giữa một câu lệnh SQL nhiều dòng, Liquibase có thể tách nội dung thành changeset không mong muốn. Nếu bỏ marker, phần SQL không được quản lý như changeset có danh tính rõ ràng.

Nên dùng mỗi changeset cho một thao tác có mục đích và phương án kiểm chứng riêng. Không cần ép mỗi câu lệnh thành một file, nhưng tránh trộn những thay đổi độc lập khiến rollback và điều tra sự cố khó hơn.

## 3. Định danh changeset: author, id và đường dẫn tệp

Liquibase thường nhận diện changeset bằng tổ hợp:

**ID + AUTHOR + FILENAME**

Trong formatted SQL:

- **ID** là phần sau dấu hai chấm trong marker.
- **AUTHOR** là phần trước dấu hai chấm.
- **FILENAME** là đường dẫn changelog mà Liquibase dùng khi lưu lịch sử, hoặc đường dẫn logic được cấu hình phù hợp.

Ví dụ:

~~~text
ID       : 20261119-001
AUTHOR   : db-team
FILENAME : db/changelog/releases/2026/11/001-create-customer.sql
~~~

Ba giá trị giúp Liquibase đối chiếu với các bản ghi DATABASECHANGELOG. Nếu cùng id và author nhưng tệp bị di chuyển tới đường dẫn mới, Liquibase có thể xem đó là một changeset khác.

### Quy ước đặt ID và tên tệp

Một cách đặt tên có thể áp dụng:

~~~text
db/changelog/releases/2026/11/
  001-create-customer.sql
  002-add-customer-status.sql
  003-backfill-customer-status.sql
~~~

Tương ứng:

~~~sql
--changeset customer-team:20261119-001
~~~

Tên tệp giúp con người tìm kiếm và review, còn bộ định danh của changeset giúp Liquibase theo dõi lịch sử. Không bắt buộc ID phải trùng số trên tên tệp, nhưng nên có quy tắc để truy vết dễ dàng.

Sau khi một changeset được triển khai, nên xem ID, author, đường dẫn logic và phần nội dung thực thi là những yếu tố cần giữ ổn định. Khi cần thay đổi schema tiếp, thông thường hãy thêm changeset mới. Đừng đổi tên tệp hoặc sửa changeset cũ để che lỗi checksum.

### logicalFilePath

Liquibase hỗ trợ cơ chế **logicalFilePath** để ổn định đường dẫn logic dùng nhận diện changeset khi cấu trúc tệp thay đổi. Khả năng khai báo trực tiếp trong formatted SQL hoặc ở changelog bao ngoài có thể khác theo phiên bản. Nếu cần di chuyển file đã phát hành, hãy kiểm tra giá trị FILENAME thật trong DATABASECHANGELOG, xác định cách cấu hình logicalFilePath ở phiên bản đang dùng và chạy thử trên database có lịch sử tương đương production.

Không nên dùng việc sửa tay DATABASECHANGELOG làm cách đổi tên tệp đã chạy.

## 4. Các chỉ thị quan trọng trong formatted SQL

Bảng sau tập hợp những thành phần thường gặp. Tên thuộc tính và mức hỗ trợ cụ thể phải được kiểm tra với phiên bản Liquibase triển khai.

| Chỉ thị hoặc thuộc tính | Vai trò | Mẫu |
|---|---|---|
| **--liquibase formatted sql** | Nhận diện định dạng changelog | Dòng đầu tệp |
| **--changeset** | Bắt đầu changeset và chỉ định author:id | **--changeset db-team:001** |
| **--comment:** | Ghi mô tả changeset cho người đọc/lịch sử | **--comment: Create orders table** |
| **--rollback** | Khai báo SQL đảo ngược | **--rollback DROP TABLE orders;** |
| **dbms:** | Giới hạn changeset theo DBMS | **dbms:postgresql** |
| **contextFilter:** hoặc **context:** | Lọc theo context tùy phiên bản/cú pháp hỗ trợ | **contextFilter:dev** |
| **labels:** | Gắn nhãn để lọc changeset | **labels:reference-data** |
| **runOnChange:** | Cho chạy lại khi checksum thay đổi theo quy tắc Liquibase | **runOnChange:true** |
| **runAlways:** | Cho chạy lại mỗi lần update đủ điều kiện | **runAlways:true** |
| **runInTransaction:** | Điều khiển việc Liquibase dùng transaction cho changeset | **runInTransaction:false** |
| **splitStatements:** | Điều khiển việc tách câu SQL | **splitStatements:false** |
| **endDelimiter:** | Định nghĩa ký hiệu kết thúc câu SQL | **endDelimiter:GO** |
| **stripComments:** | Điều khiển loại bỏ comment SQL khi thực thi | **stripComments:true** |
| **--preconditions** | Khai báo chính sách xử lý precondition | **--preconditions onFail:HALT** |
| **--precondition-sql-check** | Kiểm tra một giá trị trả về từ SQL | **--precondition-sql-check expectedResult:0 SELECT ...** |

Một marker có thể có nhiều thuộc tính:

~~~sql
--changeset db-team:create-audit-view dbms:postgresql runOnChange:true labels:reporting
~~~

Chú ý các điểm cú pháp:

- Các thuộc tính thường viết ngay trên dòng marker changeset, ngăn cách bằng khoảng trắng.
- Một số thuộc tính và tên alias thay đổi qua các thế hệ Liquibase; ví dụ hệ thống có thể thấy **context:** trong tài liệu cũ và **contextFilter:** trong tài liệu mới.
- Chỉ thị cần khớp chính tả và dấu phân tách mà parser của phiên bản đang dùng nhận diện. Comment SQL bình thường không trở thành chỉ thị chỉ vì có từ giống tên thuộc tính.
- Các giá trị label, context và biểu thức lọc có cú pháp riêng; không suy luận rằng mọi giá trị gồm khoảng trắng đều có thể viết tùy ý.

## 5. Viết một changeset DDL hoàn chỉnh

Ví dụ dùng cú pháp PostgreSQL để thêm bảng ghi nhận thanh toán:

~~~sql
--liquibase formatted sql

--changeset billing-team:20261119-001 dbms:postgresql labels:payments
--comment: Create payment table for customer orders
CREATE TABLE payment (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_payment_amount_nonnegative CHECK (amount >= 0)
);

--rollback DROP TABLE payment;
~~~

Trong ví dụ:

1. **Header** nhận diện formatted SQL.
2. **Author và ID** xác định changeset; tên file sẽ bổ sung phần FILENAME khi Liquibase ghi lịch sử.
3. **dbms:postgresql** giới hạn changeset cho PostgreSQL.
4. **labels:payments** giúp lọc thay đổi theo chính sách triển khai; label tự nó không đổi database đích.
5. **--comment:** mô tả lý do và phạm vi thay đổi.
6. Câu **CREATE TABLE** là thay đổi chính.
7. **--rollback** mô tả thao tác đảo ngược.

Rollback ở đây chỉ phù hợp khi có thể xóa bảng mà không mất dữ liệu cần giữ hoặc gây hỏng quan hệ phụ thuộc. Trong production, lệnh DROP TABLE có thể phá hủy dữ liệu thật; vì thế phải xét kỹ mức độ an toàn trước khi cho phép rollback.

### 5.1. Đảm bảo tính tương thích giữa DBMS

SQL trong ví dụ dùng **GENERATED BY DEFAULT AS IDENTITY** và **TIMESTAMPTZ**, nên cần kiểm tra phiên bản PostgreSQL đích. Với MySQL, SQL Server hoặc Oracle, các kiểu dữ liệu và cơ chế tự tăng có thể khác.

Chỉ thị **dbms:** ngăn changeset chạy ở DBMS không khớp. Nó **không** chuyển đổi SQL PostgreSQL thành SQL của DBMS khác, cũng không bảo đảm cú pháp hợp lệ trên mọi phiên bản PostgreSQL.

Nếu ứng dụng phải hỗ trợ nhiều DBMS, có thể:

- Dùng change type YAML/XML/JSON để Liquibase sinh SQL theo DBMS khi phù hợp.
- Tách changeset theo DBMS và lọc bằng **dbms:**.
- Dùng SQL đủ tương thích, rồi xác minh riêng trên từng DBMS được hỗ trợ.

## 6. Rollback trong formatted SQL

Formatted SQL cho phép khai báo rollback ngay cạnh SQL chính. Cách phổ biến là sử dụng một hoặc nhiều dòng **--rollback**.

Ví dụ thêm cột:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-002
ALTER TABLE customer ADD COLUMN status VARCHAR(24);

--rollback ALTER TABLE customer DROP COLUMN status;
~~~

Một changeset có thể cần nhiều bước đảo ngược:

~~~sql
--liquibase formatted sql

--changeset db-team:20261119-003
CREATE TABLE migration_example (
    id BIGINT PRIMARY KEY
);
CREATE INDEX idx_migration_example_id ON migration_example (id);

--rollback DROP INDEX idx_migration_example_id;
--rollback DROP TABLE migration_example;
~~~

Cần đánh giá thứ tự rollback phù hợp với DBMS và đối tượng phụ thuộc. Một số DBMS có cú pháp **DROP INDEX** khác; ví dụ có nơi cần thêm tên bảng hoặc schema.

### 6.1. Rollback không phải cơ chế khôi phục mọi dữ liệu

Với SQL migration dữ liệu:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-004
UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

Không thể viết một rollback đúng cho mọi dữ liệu chỉ bằng cách đặt lại status thành NULL: sau khi cập nhật, không còn cách nào phân biệt giá trị ACTIVE vừa sinh ra với ACTIVE vốn có nếu không có thông tin bổ sung.

Với migration dữ liệu, những lựa chọn thực tế gồm:

- Ghi lại trạng thái trước khi sửa trong bảng audit hoặc bảng backup được quản lý.
- Thiết kế thao tác đảo ngược chỉ đối với tập dòng được đánh dấu xác định.
- Sao lưu database và kiểm thử khôi phục theo chính sách vận hành.
- Chấp nhận **forward fix** có kiểm soát khi rollback dữ liệu không khả thi.

Vì rollback là một phần quan trọng của mô hình Liquibase, mỗi migration nên có quyết định rõ ràng: rollback tự viết, khả năng rollback tự động đã được xác nhận hay kế hoạch khôi phục thay thế.

### 6.2. SQL rollback có thể cần delimiter riêng

Nếu rollback là khối SQL phức tạp hoặc stored procedure, việc tách câu lệnh có thể khác SQL update. Khả năng cấu hình **rollbackEndDelimiter** hoặc các thuộc tính liên quan phụ thuộc phiên bản. Hãy xác minh SQL rollback được Liquibase sinh ra trong đúng môi trường; đừng suy luận rằng delimiter của update luôn phù hợp với rollback.

## 7. Precondition: kiểm tra điều kiện trước khi chạy SQL

Precondition giúp phát hiện giả định sai trước khi thực thi migration. Với formatted SQL, ví dụ thường gặp là **sqlCheck**.

Giả sử chỉ muốn tạo bảng **customer** nếu bảng chưa tồn tại trên schema **public** của PostgreSQL:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-005 dbms:postgresql
--preconditions onFail:HALT onError:HALT
--precondition-sql-check expectedResult:0 SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'customer';
CREATE TABLE public.customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);

--rollback DROP TABLE public.customer;
~~~

Ý nghĩa:

- **--preconditions** thiết lập cách xử lý khi điều kiện không đạt hoặc khi kiểm tra phát sinh lỗi.
- **--precondition-sql-check expectedResult:0** yêu cầu SQL trả về một giá trị khớp **0**. Ở đây, giá trị 0 nghĩa là không tìm thấy bảng theo truy vấn.
- **onFail:HALT** dừng tiến trình khi precondition trả về kết quả không mong đợi.
- **onError:HALT** dừng tiến trình khi bản thân phép kiểm tra gây lỗi.

**Lưu ý:** Trong thực tế không nhất thiết dùng lại tên **customer** nếu bảng đã được tạo bởi changeset khác. Mỗi ví dụ trong bài là một tình huống minh họa độc lập; không nên gộp tất cả vào cùng một changelog rồi chạy tuần tự.

### 7.1. onFail:HALT, MARK_RAN và CONTINUE

Các chính sách xử lý precondition cần được lựa chọn có chủ đích:

| Chính sách | Ý nghĩa khái quát | Khi cần thận trọng |
|---|---|---|
| **HALT** | Dừng update khi điều kiện không đạt | Phù hợp khi trạng thái DB sai cần được điều tra |
| **MARK_RAN** | Đánh dấu changeset như đã xử lý mà không chạy phần thay đổi | Có thể che giấu sự thiếu hụt schema nếu dùng sai |
| **CONTINUE** | Bỏ qua changeset trong lần chạy theo quy tắc tương ứng | Changeset có thể còn pending ở lần update sau |
| **WARN** | Ghi cảnh báo theo chính sách rồi tiếp tục xử lý | Có thể không ngăn thay đổi nguy hiểm |

Khả năng áp dụng tùy theo phạm vi precondition và phiên bản Liquibase. Không chọn MARK_RAN chỉ vì muốn pipeline “xanh”: dòng EXECTYPE=MARK_RAN trong DATABASECHANGELOG không chứng minh DDL/DML đã thực sự chạy.

### 7.2. Giới hạn của precondition

Precondition kiểm tra một điều kiện tại thời điểm thực thi. Nó không biến mọi migration thành thao tác an toàn khi chạy đồng thời, không bảo đảm dữ liệu không đổi trong suốt quá trình chạy và không thay thế khóa của Liquibase hoặc cơ chế transaction của DBMS.

Một số loại precondition có hỗ trợ khác nhau giữa formatted SQL và YAML/XML/JSON, đặc biệt ở các phiên bản cũ. Nếu điều kiện cần kiểm tra quá phức tạp hoặc parser formatted SQL chưa hỗ trợ, có thể đặt precondition ở changelog định dạng khác hoặc sử dụng cách phù hợp với phiên bản đang triển khai.

## 8. Context, label và DBMS: chọn changeset để áp dụng

Các thuộc tính này quyết định **changeset nào** được Liquibase xét trong kết nối đã chọn. Chúng không tự thay JDBC URL hoặc chọn database đích.

Ví dụ minh họa một changeset chỉ dùng để nạp dữ liệu thử nghiệm:

~~~sql
--liquibase formatted sql

--changeset seed-team:dev-customer-001 contextFilter:dev labels:test-data
INSERT INTO customer (id, email)
VALUES (900001, 'example.dev@invalid.test');

--rollback DELETE FROM customer WHERE id = 900001;
~~~

Trong cấu hình chạy update, đội triển khai có thể chỉ định context và label filter. Nếu filter không khớp, changeset thường không được áp dụng trong lần đó; điều này không đồng nghĩa nó đã được ghi nhận là EXECUTED.

**contextFilter** là tên thuộc tính trong những phiên bản Liquibase mới; nhiều ví dụ cũ dùng **context**. Cần xác minh cách phiên bản đang sử dụng đọc thuộc tính trong formatted SQL. Đối với nhãn, dùng **labels** trên changeset và cấu hình lọc label tại lúc chạy.

### Khi cần dùng dbms:

~~~sql
--liquibase formatted sql

--changeset db-team:pg-index-001 dbms:postgresql labels:performance
CREATE INDEX idx_customer_email ON customer (email);

--rollback DROP INDEX idx_customer_email;
~~~

Bộ lọc **dbms:postgresql** giúp SQL không bị áp dụng cho SQL Server hoặc MySQL nếu cùng changelog được dùng đa DBMS. Tuy vậy, nếu kết nối nhầm một **database PostgreSQL khác**, điều kiện DBMS vẫn khớp; vì vậy phải kiểm tra endpoint/schema đích riêng.

### Thực hành nhiều môi trường

Với development, staging và production, nên triển khai cùng một artifact changelog. Các khác biệt về host, database, credential và bộ lọc phù hợp được cung cấp bởi cấu hình môi trường hoặc pipeline. Tránh sửa nội dung changeset cũ khi chuyển sang môi trường mới vì có thể làm đổi checksum.

## 9. Chỉ thị runOnChange và runAlways

Mặc định, một changeset đã được ghi nhận trong DATABASECHANGELOG sẽ không thực thi lại chỉ vì pipeline chạy update lần nữa. Hai thuộc tính thay đổi hành vi đó:

- **runOnChange:true**: cho phép Liquibase chạy lại changeset khi checksum thay đổi theo quy tắc của phiên bản đang dùng.
- **runAlways:true**: yêu cầu chạy changeset ở mỗi lần update mà nó đủ điều kiện.

Ví dụ với view PostgreSQL:

~~~sql
--liquibase formatted sql

--changeset reporting-team:customer-summary-view runOnChange:true dbms:postgresql
CREATE OR REPLACE VIEW customer_summary AS
SELECT id, email
FROM customer;

--rollback DROP VIEW customer_summary;
~~~

**runOnChange** hữu ích khi view hoặc stored procedure được thiết kế để thay thế định nghĩa toàn bộ. Không nên dùng nó cho thao tác thay đổi dữ liệu không lặp lại an toàn, ví dụ trừ tiền tài khoản hay tăng giá trị số đếm.

**runAlways** phù hợp với một số tác vụ có chủ đích lặp lại nhưng phải phân tích tác động, thời gian chạy, giao dịch và tính idempotent. Không dùng thuộc tính này để né việc đặt ID changeset mới.

### Checksum liên quan thế nào?

Liquibase ghi checksum của changeset trong cột MD5SUM của DATABASECHANGELOG. Khi sửa nội dung changeset đã triển khai mà không có cơ chế cho phép thay đổi, quá trình validate/update có thể phát hiện checksum mismatch.

Việc sửa comment mô tả hoặc thay đổi khoảng trắng có thể có các quy tắc ảnh hưởng checksum khác với SQL thực thi, tùy định dạng và phiên bản. Đừng dựa vào suy đoán rằng “chỉ sửa comment nên chắc chắn không đổi checksum”; hãy kiểm tra trên công cụ thực tế. Quy tắc an toàn chung là coi changeset đã triển khai là bất biến và tạo changeset mới cho thay đổi schema/dữ liệu mới.

## 10. Tách câu SQL: splitStatements và endDelimiter

Một changeset formatted SQL có thể chứa nhiều câu lệnh. Liquibase phải xác định chỗ kết thúc của từng câu trước khi gửi tới JDBC driver. Đối với SQL đơn giản, dấu chấm phẩy thường đủ. Với procedure, function, trigger hoặc SQL chứa dấu chấm phẩy bên trong thân, quy tắc tách câu có thể phức tạp hơn.

Hai thuộc tính thường được dùng:

- **splitStatements:true/false** điều khiển liệu Liquibase có tách SQL thành nhiều statement hay không.
- **endDelimiter:** quy định chuỗi kết thúc statement thay cho delimiter mặc định trong những trường hợp cần thiết.

Ví dụ nhiều câu SQL riêng:

~~~sql
--liquibase formatted sql

--changeset audit-team:20261119-006 splitStatements:true
CREATE TABLE audit_event (
    id BIGINT PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL
);
CREATE INDEX idx_audit_event_type ON audit_event (event_type);

--rollback DROP INDEX idx_audit_event_type;
--rollback DROP TABLE audit_event;
~~~

Nếu hai câu lệnh phải chạy như hai statement riêng, cần kiểm tra parser tách đúng và driver hỗ trợ từng câu tương ứng. Quy tắc tách statement có thể dựa vào dấu chấm phẩy hoặc dấu phân cách mà Liquibase nhận diện.

### 10.1. Function PostgreSQL chứa dấu chấm phẩy

Ví dụ PL/pgSQL có nhiều dấu chấm phẩy bên trong thân function:

~~~sql
--liquibase formatted sql

--changeset reporting-team:20261119-007 dbms:postgresql splitStatements:false runOnChange:true
CREATE OR REPLACE FUNCTION normalize_customer_email(input_email TEXT)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN lower(trim(input_email));
END;
$$;

--rollback DROP FUNCTION normalize_customer_email(TEXT);
~~~

Ở ví dụ này, **splitStatements:false** giúp Liquibase không cố tách function theo các dấu chấm phẩy bên trong thân. Hãy kiểm tra câu SQL cuối cùng được gửi cho JDBC driver và cú pháp thực tế của phiên bản PostgreSQL.

Một số hệ quản trị hoặc công cụ CLI dùng từ khóa như **GO**, dấu slash hoặc delimiter do công cụ client định nghĩa. Những ký hiệu này không luôn là SQL mà JDBC driver hiểu. Nếu dự án đặt **endDelimiter:GO**, cần xác minh Liquibase xử lý/loại delimiter đúng cách; không giả định rằng có thể copy nguyên script từ console database sang Liquibase mà không điều chỉnh.

### 10.2. Kiểm tra SQL khi thay delimiter

Trước khi chạy update:

1. Xác định SQL chứa bao nhiêu câu lệnh thật sự cần gửi tới driver.
2. Xác định delimiter có xuất hiện trong string literal, comment hoặc thân procedure hay không.
3. Chọn splitStatements và endDelimiter phù hợp cho driver và DBMS.
4. Chạy **update-sql** để xem SQL Liquibase tạo ra.
5. Thử trên database phát triển có cùng phiên bản DBMS.
6. Kiểm tra cả SQL rollback nếu changeset có rollback phức tạp.

Đổi delimiter của một changeset đã triển khai cũng có thể ảnh hưởng cách Liquibase phân tích SQL; không sửa cấu hình tùy tiện trên file đã phát hành.

## 11. Transaction và chỉ thị runInTransaction

Theo mặc định, Liquibase thường cố gắng thực thi một changeset trong transaction khi DBMS hỗ trợ. Tuy nhiên, không phải mọi DDL ở mọi DBMS đều có thể rollback bằng transaction, và một số thao tác buộc phải thực thi bên ngoài transaction.

Ví dụ PostgreSQL yêu cầu **CREATE INDEX CONCURRENTLY** được thực thi ngoài transaction block:

~~~sql
--liquibase formatted sql

--changeset customer-team:20261119-008 dbms:postgresql runInTransaction:false
CREATE INDEX CONCURRENTLY idx_customer_email_concurrent
ON customer (email);

--rollback DROP INDEX CONCURRENTLY idx_customer_email_concurrent;
~~~

Ví dụ minh họa một tình huống yêu cầu cấu hình giao dịch theo DBMS; cần kiểm chứng phiên bản Liquibase, PostgreSQL và hành vi rollback cụ thể trước khi áp dụng.

**Rủi ro khi runInTransaction:false:** nếu changeset chứa nhiều statement và một statement thất bại sau khi statement trước đã thành công, database có thể ở trạng thái đã thay đổi một phần trong khi metadata Liquibase chưa được ghi nhận như mong đợi. Vì thế:

- Ưu tiên một thao tác có thể kiểm chứng trong mỗi changeset không dùng transaction.
- Hiểu rõ khả năng tự rollback của DBMS đối với thao tác cụ thể.
- Chuẩn bị cách kiểm tra trạng thái đối tượng sau lỗi.
- Thiết kế bước khôi phục hoặc migration sửa chữa có kiểm soát.
- Không cho rằng DATABASECHANGELOG luôn phản ánh toàn bộ những thao tác dở dang khi transaction bị tắt hoặc DDL tự commit.

## 12. Ghép formatted SQL vào changelog gốc

Một dự án có thể dùng tệp YAML/XML/JSON làm changelog gốc và include các tệp formatted SQL. Cách này giúp giữ thứ tự thay đổi rõ ràng nhưng vẫn cho đội database viết SQL trực tiếp.

Cấu trúc minh họa:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      releases/
        2026/
          11/
            001-create-customer.sql
            002-create-customer-summary-view.sql
~~~

Nội dung changelog gốc:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/11/001-create-customer.sql
      relativeToChangelogFile: true

  - include:
      file: releases/2026/11/002-create-customer-summary-view.sql
      relativeToChangelogFile: true
~~~

Mỗi tệp SQL con phải có header và marker changeset hợp lệ. Tệp SQL không có marker không tự trở thành formatted SQL chỉ vì phần mở rộng **.sql**.

Một số phiên bản Liquibase còn hỗ trợ khả năng include/includeAll ngay trong formatted SQL changelog; mức hỗ trợ và cú pháp có khác biệt theo phiên bản. Để giảm bất ngờ khi môi trường hỗ trợ không đồng nhất, root changelog YAML/XML/JSON với include tường minh là lựa chọn dễ review.

### Vì sao đường dẫn include quan trọng?

Đường dẫn được ghi vào FILENAME của DATABASECHANGELOG có thể phụ thuộc cách Liquibase giải quyết tệp nguồn và logicalFilePath. Đổi đường dẫn tệp đã phát hành, chuyển include sang cách viết đường dẫn khác hoặc đổi cấu trúc classpath đều cần kiểm tra xem định danh changeset còn khớp lịch sử hay không.

Đối với tệp đã triển khai, giữ nguyên đường dẫn đã xác nhận là cách bảo trì dễ kiểm soát.

## 13. Chạy formatted SQL bằng Liquibase CLI

Ví dụ giả sử changelog gốc là **db/changelog/db.changelog-master.yaml** và cấu hình kết nối đã được cung cấp qua CLI properties hoặc môi trường triển khai.

Các lệnh cơ bản:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Ý nghĩa:

- **validate** kiểm tra changelog theo các quy tắc parser/validator được hỗ trợ.
- **status --verbose** cho biết những changeset chưa được ghi nhận trên database đích theo cấu hình hiện tại.
- **update-sql** xem SQL dự kiến trước khi áp dụng.
- **update** áp dụng các changeset cần chạy và ghi nhận lịch sử khi thành công.

Cú pháp cờ CLI có thể khác giữa phiên bản Liquibase; cần dùng tài liệu đúng bản đang chạy. Các lệnh có liên quan tới database đích phải dùng URL, user, password, driver và schema phù hợp. Trong production không truyền secret bằng cách dễ bị ghi lại trong shell history hoặc CI log.

### 13.1. Kiểm tra lịch sử sau khi update

Có thể dùng SQL chỉ đọc:

~~~sql
SELECT
    ID,
    AUTHOR,
    FILENAME,
    DATEEXECUTED,
    EXECTYPE,
    MD5SUM,
    DEPLOYMENT_ID
FROM DATABASECHANGELOG
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Nếu dùng schema metadata riêng, thêm schema prefix phù hợp khi truy vấn. Các dòng trong bảng cho biết Liquibase đã ghi nhận những changeset nào. Đây là bằng chứng lịch sử, nhưng không chứng minh database không từng bị sửa thủ công sau đó.

### 13.2. Kiểm tra rollback

Với môi trường thử nghiệm, xác minh câu rollback tạo đúng SQL theo quy tắc phiên bản Liquibase và DBMS. Nếu dùng mốc tag, có thể xem trước rollback theo tag bằng lệnh tương ứng, sau đó thử thao tác với dữ liệu đại diện. Không chạy rollback chỉ dựa vào việc có dòng **--rollback** mà chưa hiểu dữ liệu có thể bị xóa hoặc trạng thái phụ thuộc sẽ thay đổi thế nào.

## 14. Tích hợp trong Spring Boot

Khi Spring Boot có dependency Liquibase phù hợp, ứng dụng có thể thực thi changelog trong quá trình khởi động, nếu tính năng Liquibase được bật.

Ví dụ:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db-dev.internal:5432/orders_dev
    username: orders_migrator
    password: "<inject-at-runtime>"
    driver-class-name: org.postgresql.Driver

  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
    default-schema: public
~~~

Changelog gốc sẽ include tệp formatted SQL. Spring Boot có thể dùng datasource ứng dụng hoặc cấu hình một kết nối Liquibase riêng tùy kiến trúc. Nếu sử dụng tài khoản migration khác tài khoản runtime, cấu hình kết nối và quyền cho Liquibase phải được kiểm tra rõ ràng.

Ở môi trường CI/CD, một quy trình phát hành có thể:

1. Lấy đúng artifact changelog từ phiên bản mã nguồn đã được review.
2. Kiểm tra driver, URL, schema, context và label của môi trường đích.
3. Chạy validate và xuất SQL dự kiến.
4. Kiểm tra rủi ro dữ liệu, transaction và rollback.
5. Chạy update theo cơ chế triển khai đã được phê duyệt.
6. Xác nhận đối tượng, dữ liệu và DATABASECHANGELOG sau migration.
7. Lưu log và deployment ID để điều tra khi cần.

Không nên tự sửa formatted SQL đã chạy giữa staging và production. Tốt nhất là phát hành một artifact bất biến, dùng cấu hình endpoint riêng và các filter có chủ đích cho từng môi trường.

## 15. Các lỗi thường gặp khi viết formatted SQL

| Hiện tượng | Nguyên nhân thường gặp | Cách điều tra |
|---|---|---|
| Liquibase không nhận diện file như formatted SQL | Header thiếu, sai hoặc không nằm ở vị trí parser yêu cầu | Kiểm tra dòng đầu tệp, encoding và header chính xác |
| Câu SQL không được ghi nhận như mong đợi | Thiếu hoặc sai marker --changeset | Kiểm tra cặp author:id và ranh giới marker |
| Update báo checksum mismatch | Nội dung changeset đã chạy bị sửa | So với artifact từng triển khai, ưu tiên changeset mới |
| Migration cũ bị xem là pending sau khi đổi tên file | FILENAME trong định danh thay đổi | Đối chiếu ID, AUTHOR, FILENAME và logicalFilePath |
| Stored procedure bị tách sai ở dấu chấm phẩy | splitStatements/delimiter chưa phù hợp | Xem update-sql, điều chỉnh trên changeset mới hoặc trước khi phát hành |
| SQL chạy được trong console nhưng lỗi qua JDBC | Console xử lý delimiter hoặc lệnh riêng của client | Phân biệt SQL thực với lệnh của công cụ client |
| Một changeset không chạy ở staging | context, label hoặc dbms filter không khớp | Kiểm tra giá trị filter và môi trường chạy |
| Bảng đã tồn tại nhưng changeset vẫn tạo bảng | Changelog đã di chuyển, lịch sử không khớp hoặc precondition thiếu | Đối chiếu DATABASECHANGELOG và schema thật |
| EXECTYPE là MARK_RAN nhưng không có bảng mới | Precondition cho phép đánh dấu mà không thực thi SQL | Kiểm tra onFail/onError và điều kiện ban đầu |
| Rollback báo lỗi hoặc mất dữ liệu | SQL rollback không tương thích DBMS hoặc thiếu chiến lược dữ liệu | Kiểm tra rollback-sql, dependency và bản sao database |
| Changeset không dùng transaction thất bại giữa chừng | Một statement đã áp dụng nhưng statement khác thất bại | Xem log, đối chiếu schema/data và thiết kế bước khôi phục |
| Password xuất hiện trong log | Secret được truyền vào command line hoặc câu SQL | Di chuyển secret sang cơ chế quản lý bí mật phù hợp |

Khi gặp lỗi, tránh sửa trực tiếp bảng DATABASECHANGELOG hoặc xóa checksum chỉ để vượt qua kiểm tra. Hãy xác định Liquibase đã ghi nhận gì, database thực tế ở trạng thái nào, tệp đã phát hành khác gì so với hiện tại và cần một changeset sửa chữa hay cách khôi phục nào.

## 16. Bài thực hành: tạo hai formatted SQL changeset

**Bối cảnh:** Hệ thống đơn hàng dùng PostgreSQL, Spring Boot và Liquibase. Cần tạo bảng **order_note** và thêm index để tra cứu theo **order_id**. Hai thay đổi phải có định danh, mô tả và SQL rollback rõ ràng.

Tạo một tệp changelog formatted SQL, chẳng hạn **20261119-001-order-note.sql**, với nội dung:

~~~sql
--liquibase formatted sql

--changeset orders-team:create-order-note-001 dbms:postgresql
--comment: Create order note table
CREATE TABLE order_note (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

--rollback DROP TABLE order_note;

--changeset orders-team:create-order-note-index-002 dbms:postgresql
--comment: Add index to search notes by order
CREATE INDEX idx_order_note_order_id ON order_note (order_id);

--rollback DROP INDEX idx_order_note_order_id;
~~~

### 16.1. Giải thích thứ tự

Changeset tạo bảng phải xuất hiện trước changeset tạo index vì index phụ thuộc bảng. Khi rollback nhiều changeset, cần đảm bảo phạm vi và thứ tự rollback phù hợp với các đối tượng phụ thuộc. Nếu migration đã được triển khai có dữ liệu thật trong **order_note**, rollback tạo bảng sẽ xóa bảng và dữ liệu; phải đánh giá rủi ro theo chính sách phát hành.

### 16.2. Đăng ký vào changelog gốc

Ví dụ YAML:

~~~yaml
databaseChangeLog:
  - include:
      file: releases/2026/11/20261119-001-order-note.sql
      relativeToChangelogFile: true
~~~

Đường dẫn include phải trùng với vị trí thật của tệp, và nên giữ ổn định sau khi đã triển khai. Changelog gốc này là ví dụ riêng, không có nghĩa người học phải sửa file gốc của một hệ thống production hiện hữu để làm bài.

### 16.3. Các bước kiểm chứng

Trên database phát triển:

1. Xác nhận kết nối tới đúng database và schema.
2. Chạy validate để kiểm tra cú pháp changelog.
3. Chạy status --verbose để thấy hai changeset đang pending.
4. Chạy update-sql và kiểm tra thứ tự CREATE TABLE, CREATE INDEX.
5. Chạy update sau khi review.
6. Truy vấn DATABASECHANGELOG để xác nhận hai dòng có ID, AUTHOR, FILENAME dự kiến.
7. Chạy lại status để xác nhận chúng không còn pending, khi không có thay đổi khác.
8. Kiểm tra SQL rollback hoặc thử rollback trên database thử nghiệm, xác nhận ảnh hưởng dữ liệu.

Bài thực hành giúp thấy một tệp SQL có thể chứa nhiều changeset độc lập, mỗi changeset có lịch sử và rollback riêng.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Có thể thay dòng **--liquibase formatted sql** bằng comment **-- file SQL migration** không?

Không. Header có cú pháp đặc thù để Liquibase nhận diện formatted SQL. Comment thông thường chỉ mang thông tin cho người đọc.

**Câu 2.** Hai changeset có cùng ID và author nhưng nằm trong hai file khác nhau có nhất thiết là cùng một changeset không?

Không. Định danh còn phụ thuộc FILENAME hoặc đường dẫn logic. Nếu cùng file được nạp lại qua đường dẫn khác, có thể xuất hiện sai lệch lịch sử.

**Câu 3.** Vì sao stored procedure có dấu chấm phẩy bên trong có thể cần splitStatements:false?

Vì parser tách câu lệnh đơn giản theo dấu chấm phẩy có thể chia sai thân procedure/function. Cần kiểm tra kết quả bằng update-sql và thử trên DBMS thực tế.

**Câu 4.** Context và label có chọn database mà Liquibase kết nối không?

Không. Chúng lọc changeset sau khi kết nối đã được cấu hình. Database đích được chọn bằng JDBC URL và các thông số kết nối.

**Câu 5.** Có thể xem runOnChange:true là cách cho phép sửa mọi changeset cũ không?

Không. Thuộc tính này dành cho các thay đổi có thiết kế chạy lại an toàn theo quy tắc Liquibase, chẳng hạn thay thế view hoặc procedure. Với migration tạo bảng, thêm cột hoặc chuyển dữ liệu một lần, thường nên viết changeset mới.

**Câu 6.** Có chỉ thị --rollback nghĩa là rollback dữ liệu chắc chắn an toàn không?

Không. Liquibase chỉ biết câu lệnh đảo ngược được khai báo. Người viết vẫn phải kiểm tra tính đúng đắn, khả năng mất dữ liệu và phụ thuộc ở DBMS thực tế.

## 18. Checklist khi review formatted SQL

- [ ] Tệp bắt đầu bằng header **--liquibase formatted sql** hợp lệ.
- [ ] Mỗi thay đổi có marker **--changeset author:id** rõ ràng.
- [ ] ID, author, tên và đường dẫn file có quy ước ổn định.
- [ ] SQL đúng cú pháp và phiên bản DBMS cần hỗ trợ.
- [ ] Mỗi changeset có mục đích đủ rõ để review độc lập.
- [ ] Thuộc tính dbms, contextFilter/context và labels được hiểu đúng.
- [ ] runOnChange hoặc runAlways chỉ được dùng cho hành vi chạy lại đã phân tích.
- [ ] Precondition kiểm tra giả định và có onFail/onError phù hợp.
- [ ] splitStatements, endDelimiter và runInTransaction được kiểm tra nếu có SQL phức tạp.
- [ ] Rollback hoặc kế hoạch khôi phục phù hợp với schema và dữ liệu.
- [ ] Changeset đã phát hành không bị đổi tên, di chuyển hoặc sửa nội dung tùy tiện.
- [ ] validate và update-sql thành công trên công cụ/DBMS đại diện.
- [ ] Đã đối chiếu changeset pending và lịch sử DATABASECHANGELOG.
- [ ] Pipeline dùng đúng endpoint, quyền và secret của từng môi trường.
- [ ] Artifact changelog được giữ nguyên khi triển khai qua staging và production.

Formatted SQL kết hợp quyền kiểm soát trực tiếp câu lệnh SQL với cơ chế quản lý changeset của Liquibase. Khi dùng đúng header, marker, chỉ thị và quy tắc lịch sử, đội phát triển có thể đưa SQL vào quy trình migration có kiểm chứng mà vẫn truy vết được ai viết thay đổi, thay đổi nào đã chạy, thay đổi nào còn pending và cách xử lý khi triển khai gặp sự cố.

