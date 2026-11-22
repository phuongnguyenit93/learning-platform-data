# Kiểm tra không tồn tại rồi chèn nhưng thiếu ràng buộc duy nhất

Một mẫu code tưởng như an toàn là kiểm tra xem một bản ghi đã tồn tại chưa, nếu chưa thì INSERT:

~~~sql
SELECT id
FROM invitations
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';

-- Nếu không tìm thấy:
INSERT INTO invitations (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026');
~~~

Khi chỉ có một request, cách này có vẻ hoạt động. Nhưng nếu hai transaction chạy đồng thời, cả hai có thể cùng đọc kết quả không có bản ghi, rồi cùng INSERT. Nếu database không có ràng buộc duy nhất bảo vệ khóa nghiệp vụ, cả hai lần INSERT đều có thể thành công và tạo dữ liệu trùng.

Đây là **check-then-insert race condition**, còn gọi là lỗi TOCTOU (time of check to time of use): trạng thái được kiểm tra có thể thay đổi trước lúc ứng dụng sử dụng kết quả kiểm tra đó.

Quy tắc quan trọng là: **kiểm tra ở ứng dụng giúp đưa ra quyết định, còn ràng buộc duy nhất ở database mới cưỡng chế tính duy nhất trước mọi transaction cạnh tranh.** Ứng dụng nên thử INSERT và xử lý duplicate-key theo quy tắc nghiệp vụ.

## 1. Lỗi xuất hiện như thế nào?

Giả sử bảng invitations lưu mã mời trong phạm vi tenant. Hai request cùng muốn tạo mã WELCOME-2026 cho tenant 7.

Trạng thái ban đầu không có mã này.

~~~text
Transaction A                         Transaction B
-------------                         -------------
BEGIN                                 BEGIN

SELECT mã WELCOME-2026                SELECT mã WELCOME-2026
Kết quả: 0 dòng                       Kết quả: 0 dòng

Quyết định INSERT                     Quyết định INSERT

INSERT WELCOME-2026                   INSERT WELCOME-2026
COMMIT                                COMMIT
~~~

Nếu không có UNIQUE constraint, database có thể lưu hai bản ghi giống nhau:

| id | tenant_id | invitation_code |
|---:|---:|---|
| 101 | 7 | WELCOME-2026 |
| 102 | 7 | WELCOME-2026 |

Cả hai transaction đều đã kiểm tra trước khi bản ghi được tạo. Kết quả của câu SELECT là đúng tại thời điểm mỗi transaction đọc, nhưng không còn đúng tại thời điểm INSERT.

Đây không phải lỗi do hai câu SELECT trả kết quả sai. Đây là lỗi thiết kế vì ứng dụng coi một lần đọc là đủ để bảo đảm một điều kiện phải đúng trên toàn bộ transaction đồng thời.

## 2. Vì sao transaction và SELECT thông thường chưa đủ?

Một transaction bảo đảm các thuộc tính ACID trong phạm vi isolation level và cơ chế của database. Nhưng việc đặt hai câu lệnh trong cùng transaction không tự động làm cho chuỗi SELECT rồi INSERT trở thành một thao tác nguyên tử.

Ví dụ:

~~~sql
BEGIN;

SELECT id
FROM invitations
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';

-- Ứng dụng quyết định INSERT nếu SELECT không trả dòng.

INSERT INTO invitations (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026');

COMMIT;
~~~

Nếu hai transaction cùng chạy ở READ COMMITTED, cả hai có thể nhìn thấy trạng thái chưa có bản ghi. Sau đó chúng lần lượt hoặc đồng thời INSERT.

Ở các isolation level dựa trên MVCC, SELECT thông thường thường đọc snapshot mà không khóa một bản ghi chưa tồn tại. Database không thể khóa một row cụ thể khi row đó chưa được tạo.

Điều này không có nghĩa mọi isolation level đều cho cùng một kết quả. Một số engine có thể dùng key-range lock hoặc phát hiện serialization anomaly trong một số cấu hình. Nhưng ứng dụng không nên dựa vào giả định chung rằng SELECT kiểm tra sự vắng mặt sẽ khóa được khoảng trống trên mọi database.

## 3. Thực nghiệm hai session tái hiện race condition

Thực nghiệm sau dùng MySQL InnoDB để thấy rõ vấn đề. Mở hai kết nối độc lập đến cùng database, gọi là Session A và Session B.

### 3.1. Tạo bảng chưa có UNIQUE constraint

Chạy một lần trước khi bắt đầu:

~~~sql
DROP TABLE IF EXISTS invitations_lab;

CREATE TABLE invitations_lab (
    id BIGINT NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    invitation_code VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_tenant_code (tenant_id, invitation_code)
) ENGINE = InnoDB;
~~~

Bảng có index thường trên tenant_id và invitation_code để hỗ trợ tìm kiếm, nhưng chưa có UNIQUE constraint. Index thường không cấm hai dòng có cùng giá trị.

### 3.2. Session A kiểm tra mã

Chạy ở Session A:

~~~sql
START TRANSACTION;

SELECT id
FROM invitations_lab
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';
~~~

Kết quả là 0 dòng. Giữ transaction A mở.

### 3.3. Session B cũng kiểm tra mã

Chạy ở Session B:

~~~sql
START TRANSACTION;

SELECT id
FROM invitations_lab
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';
~~~

B cũng nhận 0 dòng vì A chưa INSERT và commit bản ghi nào. Giữ transaction B mở.

### 3.4. Cả hai session cùng INSERT

Ở Session A:

~~~sql
INSERT INTO invitations_lab (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026');
~~~

Ở Session B:

~~~sql
INSERT INTO invitations_lab (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026');
~~~

Vì chưa có UNIQUE constraint, cả hai INSERT có thể thành công. Commit cả hai:

~~~sql
-- Session A
COMMIT;
~~~

~~~sql
-- Session B
COMMIT;
~~~

Kiểm tra:

~~~sql
SELECT
    tenant_id,
    invitation_code,
    COUNT(*) AS duplicate_count
FROM invitations_lab
GROUP BY tenant_id, invitation_code
HAVING COUNT(*) > 1;
~~~

Kết quả có một nhóm với duplicate_count = 2.

Thực nghiệm chứng minh rằng index thường giúp tìm kiếm nhanh nhưng không bảo vệ tính duy nhất. Nếu muốn một mã chỉ xuất hiện một lần trong mỗi tenant, database phải có constraint thể hiện đúng quy tắc đó.

## 4. Cách sửa nền tảng: UNIQUE constraint

Nếu quy tắc nghiệp vụ là mỗi tenant chỉ có một invitation_code, hãy khai báo khóa duy nhất trên cặp cột:

~~~sql
ALTER TABLE invitations_lab
ADD CONSTRAINT uq_invitations_tenant_code
UNIQUE (tenant_id, invitation_code);
~~~

Nếu bảng đang có dữ liệu trùng, câu ALTER TABLE sẽ thất bại. Cần tìm và xử lý duplicate hiện có trước khi thêm constraint.

Truy vấn tìm nhóm trùng:

~~~sql
SELECT
    tenant_id,
    invitation_code,
    COUNT(*) AS duplicate_count
FROM invitations_lab
GROUP BY tenant_id, invitation_code
HAVING COUNT(*) > 1;
~~~

Sau khi xử lý dữ liệu cũ và thêm constraint thành công, database sẽ từ chối lần INSERT thứ hai cho cùng cặp tenant_id và invitation_code.

### Kết quả khi hai transaction cạnh tranh

~~~text
Transaction A                         Transaction B
-------------                         -------------
INSERT (7, WELCOME-2026)              INSERT (7, WELCOME-2026)

Được phép ghi                        Chờ kết quả xung đột
COMMIT
                                      Nhận duplicate-key error
                                      Không tạo bản ghi thứ hai
~~~

Nếu A rollback thay vì commit, B có thể tiếp tục và INSERT thành công. Database kiểm tra tính duy nhất tại thời điểm ghi, bao gồm cả xung đột với transaction đang chạy.

Constraint là lớp bảo vệ cuối cùng ngay cả khi:

- Có nhiều application instance.
- Có nhiều consumer xử lý cùng một event.
- Một batch job ghi trực tiếp vào database.
- Một service khác không chạy cùng code kiểm tra.
- Hai request đến từ các máy chủ khác nhau.
- Một request retry sau timeout.

Không có kiểm tra ở tầng Java nào có thể thay thế một UNIQUE constraint khi quy tắc duy nhất phải đúng trên toàn database.

## 5. Thử lại thực nghiệm sau khi thêm UNIQUE constraint

Xóa dữ liệu thử nghiệm trùng để bắt đầu trạng thái sạch. Thực hiện khi không còn transaction thực nghiệm mở:

~~~sql
DELETE FROM invitations_lab;

SELECT COUNT(*) AS row_count
FROM invitations_lab;
~~~

Xác nhận constraint đã tồn tại:

~~~sql
SHOW INDEX FROM invitations_lab;
~~~

Hoặc kiểm tra định nghĩa bảng:

~~~sql
SHOW CREATE TABLE invitations_lab;
~~~

Chạy lại trình tự:

1. A BEGIN và SELECT mã chưa tồn tại.
2. B BEGIN và SELECT cùng mã, cũng chưa thấy dòng.
3. A INSERT mã.
4. B INSERT cùng mã.
5. A COMMIT.
6. Quan sát B nhận duplicate-key error.
7. B xử lý lỗi theo chính sách ứng dụng rồi kết thúc transaction phù hợp.

Kết quả mong đợi là chỉ có một dòng:

~~~sql
SELECT *
FROM invitations_lab
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';
~~~

Một trong hai transaction thắng. Transaction còn lại phải nhận diện duplicate là trường hợp nghiệp vụ có thể xử lý, hoặc trả conflict nếu hai request không đại diện cho cùng một ý định.

## 6. Vì sao không nên chỉ dùng SELECT ... FOR UPDATE?

Một cách thường được thử là khóa kết quả tìm kiếm:

~~~sql
SELECT id
FROM invitations_lab
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026'
FOR UPDATE;
~~~

Câu lệnh này có thể khóa record hiện có. Nhưng nếu không tìm thấy row, hành vi bảo vệ khoảng trống phụ thuộc database engine, isolation level, index và execution plan.

### MySQL InnoDB

Ở REPEATABLE READ, locking read theo range có thể sử dụng gap lock hoặc next-key lock. Nếu truy vấn dùng index phù hợp, việc tìm khóa chưa tồn tại có thể bảo vệ gap nơi khóa mới sẽ được chèn.

Tuy nhiên:

- SELECT thông thường không có FOR UPDATE là consistent read và không lấy gap lock chỉ vì không tìm thấy row.
- Locking read trên một khóa không tồn tại có thể khóa gap tùy đường truy cập và isolation.
- Hai transaction có thể cùng giữ gap lock tương thích rồi cạnh tranh khi INSERT, dẫn đến lock wait hoặc deadlock.
- Ở READ COMMITTED, gap locking cho search thông thường giảm đi, nhưng vẫn có một số ngoại lệ như foreign-key và duplicate-key checking.
- Nếu không có index phù hợp, phạm vi khóa có thể rộng hơn dự kiến.

Vì vậy, SELECT FOR UPDATE có thể là một phần của chiến lược đồng bộ, nhưng không thay thế UNIQUE constraint.

### PostgreSQL

SELECT FOR UPDATE khóa các row được tìm thấy. Nếu không có row phù hợp, nó không tạo row lock trên một bản ghi không tồn tại và không cung cấp gap lock tổng quát như InnoDB.

Hai transaction có thể cùng SELECT không thấy dòng rồi cùng thử INSERT. UNIQUE constraint sẽ chọn một transaction thành công và từ chối transaction còn lại.

PostgreSQL SERIALIZABLE có thể phát hiện một số serialization anomaly và abort transaction cần thiết, nhưng unique constraint vẫn là cách trực tiếp để cưỡng chế tính duy nhất.

### SQL Server

Ở isolation level SERIALIZABLE, SQL Server có thể dùng key-range lock để bảo vệ phạm vi tìm kiếm, nếu execution plan và index cho phép. Các hint như UPDLOCK và HOLDLOCK có thể được dùng trong một giao thức khóa rõ ràng.

Nhưng nếu chỉ chạy SELECT thông thường ở READ COMMITTED, không thể giả định rằng khoảng khóa chưa tồn tại được bảo vệ.

Dù dùng key-range lock hay không, UNIQUE constraint vẫn nên là lớp bảo vệ dữ liệu cuối cùng.

## 7. Chọn đúng phạm vi của khóa duy nhất

Một lỗi thiết kế khác là tạo UNIQUE constraint trên sai cột.

Giả sử mã mời chỉ cần duy nhất trong từng tenant. Quy tắc là:

~~~text
(tenant_id, invitation_code) phải duy nhất
~~~

Constraint phù hợp:

~~~sql
UNIQUE (tenant_id, invitation_code)
~~~

Không nên chỉ dùng:

~~~sql
UNIQUE (invitation_code)
~~~

vì hai tenant khác nhau có thể hợp lệ khi dùng cùng một mã.

Ngược lại, nếu mã phải duy nhất trên toàn hệ thống, chỉ tạo UNIQUE trên invitation_code. Phạm vi constraint phải phản ánh chính xác phạm vi nghiệp vụ.

### Ví dụ các quy tắc duy nhất

| Quy tắc nghiệp vụ | UNIQUE constraint |
|---|---|
| Email duy nhất trên toàn hệ thống | UNIQUE(email) |
| Username duy nhất trong tenant | UNIQUE(tenant_id, username) |
| Một user chỉ có một membership trong một group | UNIQUE(group_id, user_id) |
| Một payment provider reference chỉ được ghi nhận một lần trong merchant | UNIQUE(merchant_id, provider_reference) |
| Một event chỉ được consumer xử lý một lần | UNIQUE(consumer_name, event_id) |
| Một sản phẩm chỉ có một SKU trong warehouse | UNIQUE(warehouse_id, sku) |

Trước khi tạo constraint, cần trả lời:

- Phạm vi duy nhất là toàn hệ thống, tenant, tổ chức hay một loại nghiệp vụ?
- Các cột nào cấu thành business key?
- Có phân biệt chữ hoa/chữ thường không?
- Có cho phép NULL không?
- Bản ghi đã xóa mềm có còn chiếm khóa không?
- Một request retry có phải cùng một ý định hay là một lần tạo mới?

## 8. NULL, collation và chuẩn hóa dữ liệu có thể làm thay đổi tính duy nhất

Một UNIQUE constraint chỉ bảo vệ theo semantics của database. Nếu ứng dụng và database hiểu khóa nghiệp vụ khác nhau, duplicate vẫn có thể lọt qua hoặc dữ liệu hợp lệ bị từ chối.

### 8.1. NULL trong unique key

Hành vi của NULL trong unique index khác nhau giữa các hệ quản trị.

- MySQL cho phép nhiều giá trị NULL trong một unique index.
- PostgreSQL mặc định xem các NULL là khác nhau cho mục đích unique, nên có thể có nhiều dòng NULL; PostgreSQL có tùy chọn NULLS NOT DISTINCT ở các phiên bản hỗ trợ.
- SQL Server có semantics khác cho unique index, thường chỉ cho một tổ hợp NULL tương ứng trong unique key đơn cột; filtered index có thể dùng khi quy tắc cho phép.

Nếu mã nghiệp vụ bắt buộc phải có, khai báo NOT NULL:

~~~sql
tenant_id BIGINT NOT NULL,
invitation_code VARCHAR(100) NOT NULL
~~~

Không dùng NULL để biểu diễn một khóa chưa xác định nếu nghiệp vụ yêu cầu mỗi bản ghi phải có mã.

### 8.2. Chữ hoa và chữ thường

Với collation không phân biệt hoa thường, các giá trị:

~~~text
Welcome
WELCOME
welcome
~~~

có thể được xem là bằng nhau trong unique index.

Với collation phân biệt hoa thường, chúng có thể được coi là các giá trị khác nhau.

Cần quyết định quy tắc nghiệp vụ:

- Mã có phân biệt chữ hoa/chữ thường không?
- Email có được chuẩn hóa trước khi lưu không?
- Có loại bỏ khoảng trắng đầu/cuối không?
- Unicode có cần chuẩn hóa về một dạng thống nhất không?

Đừng chỉ lowercase trong Java rồi tạo unique index với collation có semantics khác. Chuẩn hóa và constraint phải thống nhất.

### 8.3. Khoảng trắng và định dạng

Ví dụ mã có thể được nhập dưới các dạng:

~~~text
ABC-100
 ABC-100
ABC-100 
~~~

Tùy kiểu cột và collation, database có thể xử lý khoảng trắng cuối theo quy tắc riêng. Ứng dụng nên chuẩn hóa dữ liệu trước khi ghi và định nghĩa constraint trên giá trị chuẩn hóa nếu cần.

Với định danh quan trọng, có thể lưu một cột canonical_key đã chuẩn hóa và đặt UNIQUE trên cột đó.

## 9. Bản ghi xóa mềm và unique constraint

Giả sử bảng users có cột deleted_at. Một user bị xóa mềm vẫn còn trong bảng:

~~~sql
UPDATE users
SET deleted_at = CURRENT_TIMESTAMP
WHERE user_id = 10;
~~~

Nếu UNIQUE(email) áp dụng trên toàn bảng, email đó vẫn bị chiếm và không thể tạo user mới với cùng email.

Có hai quy tắc nghiệp vụ phổ biến:

1. Email phải duy nhất kể cả với user đã xóa mềm.
2. Email chỉ cần duy nhất trong các user đang hoạt động.

Nếu chọn quy tắc thứ hai, cần constraint có điều kiện theo database.

### PostgreSQL và SQL Server

PostgreSQL hỗ trợ partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_active_user_email
ON users (email)
WHERE deleted_at IS NULL;
~~~

SQL Server hỗ trợ filtered unique index:

~~~sql
CREATE UNIQUE INDEX uq_active_user_email
ON dbo.Users (Email)
WHERE DeletedAt IS NULL;
~~~

### MySQL

MySQL không có partial index với cú pháp tương tự PostgreSQL. Có thể thiết kế cột generated hoặc cột khóa hoạt động để chỉ các hàng chưa xóa tham gia unique key.

Ví dụ ý tưởng với generated column:

~~~sql
ALTER TABLE users
ADD COLUMN active_email VARCHAR(255)
    GENERATED ALWAYS AS (
        CASE
            WHEN deleted_at IS NULL THEN email
            ELSE NULL
        END
    ) STORED,
ADD UNIQUE KEY uq_active_user_email (active_email);
~~~

Thiết kế này cần kiểm tra kiểu dữ liệu, collation, giới hạn index và semantics NULL của phiên bản MySQL đang dùng. Nếu có thêm tenant scope, generated key phải bao gồm tenant theo cách phù hợp, hoặc dùng một cấu trúc khóa tổng hợp được thiết kế cẩn thận.

Không nên bỏ constraint chỉ để cho phép tái sử dụng email sau soft delete. Hãy biểu diễn chính xác quy tắc hoạt động bằng index hoặc mô hình dữ liệu phù hợp.

## 10. Cách xử lý duplicate-key đúng trong ứng dụng

Sau khi có UNIQUE constraint, ứng dụng cần chấp nhận rằng hai request cạnh tranh có thể dẫn đến một request thành công và một request nhận duplicate-key.

Đây là kết quả bình thường, không nhất thiết là lỗi hệ thống.

Quy trình tổng quát:

1. Chuẩn hóa business key.
2. Thử INSERT.
3. Nếu INSERT thành công, trả kết quả tạo mới.
4. Nếu gặp lỗi unique violation đúng constraint dự kiến, truy vấn bản ghi hiện có.
5. Xác định request hiện tại có đại diện cho cùng ý định với bản ghi đã có không.
6. Nếu cùng ý định, có thể trả lại kết quả hiện có như một thao tác idempotent.
7. Nếu dữ liệu khác hoặc key đang được dùng cho nghiệp vụ khác, trả conflict.
8. Các lỗi khác như mất kết nối, timeout, lỗi schema hoặc CHECK violation phải được xử lý theo nhóm riêng.

Không nên bắt mọi exception rồi coi như bản ghi đã tồn tại. Một lỗi database bất kỳ không chứng minh rằng request đã được xử lý trước đó.

### Phân biệt duplicate mong đợi với lỗi khác

Các mã thường gặp:

| Database | Duplicate/unique violation thường gặp |
|---|---|
| MySQL | Error 1062, SQLSTATE 23000 |
| PostgreSQL | SQLSTATE 23505 |
| SQL Server | Error 2601 hoặc 2627 |

SQLSTATE 23000 của MySQL là nhóm integrity constraint violation, không chỉ riêng duplicate key. Nên kiểm tra vendor error code và constraint/index liên quan để phân loại chính xác.

SQL Server 2601 thường liên quan đến duplicate key trong unique index; 2627 thường liên quan đến vi phạm PRIMARY KEY hoặc UNIQUE constraint. Hãy kiểm tra error number và tên constraint/index trong message.

## 11. PostgreSQL: INSERT ... ON CONFLICT

PostgreSQL hỗ trợ UPSERT bằng ON CONFLICT.

Nếu muốn tạo mới nhưng bỏ qua trường hợp key đã tồn tại:

~~~sql
INSERT INTO invitations (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026')
ON CONFLICT (tenant_id, invitation_code)
DO NOTHING
RETURNING id;
~~~

- Nếu INSERT thành công, RETURNING trả về id mới.
- Nếu xung đột với khóa duy nhất đã chỉ định, không có dòng nào được trả về.
- Ứng dụng có thể truy vấn bản ghi hiện có trong statement tiếp theo ở READ COMMITTED để lấy kết quả.

Nếu muốn cập nhật khi đã tồn tại:

~~~sql
INSERT INTO invitations (tenant_id, invitation_code, description)
VALUES (7, 'WELCOME-2026', 'Welcome campaign')
ON CONFLICT (tenant_id, invitation_code)
DO UPDATE
SET description = EXCLUDED.description
RETURNING id;
~~~

Chỉ dùng DO UPDATE nếu việc cập nhật bản ghi hiện có đúng với quy tắc nghiệp vụ. Nếu request trùng chỉ cần nhận lại kết quả cũ, cập nhật description hoặc các cột khác có thể tạo side effect ngoài ý muốn.

Trong PostgreSQL, ON CONFLICT yêu cầu một unique constraint hoặc unique index phù hợp làm arbiter. Nó không thay thế việc định nghĩa đúng business key.

Ở isolation level REPEATABLE READ hoặc SERIALIZABLE, thao tác cạnh tranh có thể phát serialization failure tùy lịch thực thi. Ứng dụng cần xử lý SQLSTATE 40001 bằng cách retry toàn bộ transaction.

## 12. MySQL: INSERT và xử lý duplicate-key

Với MySQL, cách đơn giản là thử INSERT và xử lý lỗi 1062 nếu đó là duplicate của business key dự kiến:

~~~sql
INSERT INTO invitations (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026');
~~~

Nếu duplicate-key, ứng dụng truy vấn bản ghi hiện có:

~~~sql
SELECT id
FROM invitations
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';
~~~

Nếu transaction đang ở READ COMMITTED, SELECT tiếp theo có thể thấy transaction thắng đã commit. Nếu transaction đang dùng snapshot cũ ở REPEATABLE READ, một consistent read trong cùng transaction có thể không thấy row vừa commit dù INSERT đã phát hiện xung đột. Khi đó cần hiểu isolation semantics và có thể phải rollback transaction rồi đọc lại trong transaction mới, hoặc dùng một câu lệnh/locking strategy phù hợp.

Có thể dùng:

~~~sql
INSERT INTO invitations (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026')
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(id);
~~~

Đây là một kỹ thuật MySQL thường dùng để lấy ID hiện có qua LAST_INSERT_ID(), nhưng cần cân nhắc:

- ON DUPLICATE KEY UPDATE kích hoạt nhánh UPDATE, kể cả khi chỉ gán lại giá trị.
- Trigger UPDATE có thể chạy.
- Affected rows có semantics riêng tùy client flags.
- Bảng có nhiều unique index có thể xung đột trên một key khác với key ứng dụng dự định.
- Câu lệnh có thể tạo side effect không mong muốn nếu update không thực sự là thao tác nghiệp vụ mong muốn.

INSERT IGNORE cũng có thể bỏ qua duplicate, nhưng nó có thể biến một số lỗi dữ liệu thành warning và tiếp tục xử lý. Không nên dùng INSERT IGNORE như một cách tổng quát để nuốt mọi lỗi INSERT.

Với nghiệp vụ cần phân biệt tạo mới và đã tồn tại, insert bình thường rồi bắt đúng duplicate-key error thường dễ diễn giải hơn.

## 13. SQL Server: unique constraint và xử lý insert cạnh tranh

Cách cơ bản là tạo unique constraint:

~~~sql
ALTER TABLE dbo.Invitations
ADD CONSTRAINT UQ_Invitations_Tenant_Code
UNIQUE (TenantId, InvitationCode);
~~~

Sau đó thực hiện INSERT và bắt lỗi duplicate:

~~~sql
BEGIN TRY
    INSERT INTO dbo.Invitations (TenantId, InvitationCode)
    VALUES (7, 'WELCOME-2026');
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() IN (2601, 2627)
    BEGIN
        -- Xác định đúng constraint/index bị xung đột.
        -- Đọc bản ghi hiện có hoặc trả conflict theo API contract.
    END
    ELSE
    BEGIN
        THROW;
    END
END CATCH;
~~~

Nếu muốn tuần tự hóa cả bước kiểm tra và tạo, SQL Server có thể dùng SERIALIZABLE hoặc table hint phù hợp:

~~~sql
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    IF NOT EXISTS (
        SELECT 1
        FROM dbo.Invitations WITH (UPDLOCK, HOLDLOCK)
        WHERE TenantId = 7
          AND InvitationCode = 'WELCOME-2026'
    )
    BEGIN
        INSERT INTO dbo.Invitations (TenantId, InvitationCode)
        VALUES (7, 'WELCOME-2026');
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
~~~

UPDLOCK yêu cầu update lock trong quá trình đọc; HOLDLOCK áp dụng semantics SERIALIZABLE cho table reference đó. Với index phù hợp, SQL Server có thể dùng key-range lock để bảo vệ khoảng tìm kiếm.

Dù dùng cách này, unique constraint vẫn cần thiết để bảo vệ dữ liệu trước mọi writer khác và các đường ghi không tuân thủ cùng giao thức.

Không nên coi MERGE là cách tự động loại bỏ mọi race condition. Nếu dùng MERGE, vẫn phải thiết kế khóa, unique constraint và xử lý xung đột theo semantics của phiên bản SQL Server đang triển khai.

## 14. Isolation level SERIALIZABLE có thay thế UNIQUE constraint không?

SERIALIZABLE yêu cầu kết quả transaction tương đương một thứ tự tuần tự hợp lệ. Nó có thể ngăn hai transaction cùng thành công khi lịch đọc/ghi tạo ra serialization anomaly.

Tuy nhiên, SERIALIZABLE không phải lý do để bỏ unique constraint:

- Constraint biểu diễn trực tiếp quy tắc dữ liệu.
- Constraint bảo vệ mọi đường ghi, kể cả script, batch job hoặc service khác.
- Constraint thường có chi phí và semantics dễ dự đoán hơn việc nâng toàn bộ transaction lên SERIALIZABLE.
- SERIALIZABLE có thể gây lock wait hoặc serialization failure và yêu cầu retry.
- Nếu transaction không thực hiện đúng các truy vấn kiểm tra hoặc phạm vi khóa, ứng dụng vẫn có thể xử lý sai nghiệp vụ dù isolation level cao.

Với unique business key, cách thiết kế rõ ràng thường là:

~~~text
UNIQUE constraint
       +
INSERT hoặc UPSERT có xử lý xung đột
       +
Retry transaction nếu engine báo serialization failure
~~~

Isolation level phù hợp vẫn quan trọng đối với các bất biến rộng hơn như giới hạn tổng số bản ghi, tổng ngân sách hoặc điều kiện liên quan đến nhiều hàng. Nhưng tính duy nhất của một key nên được database biểu diễn bằng unique index/constraint.

## 15. Nếu không thể tạo UNIQUE constraint thì sao?

Có những hệ thống cũ chưa thể thêm constraint ngay vì dữ liệu hiện tại có duplicate, nhiều writer hoặc schema chưa cho phép thay đổi.

Có thể dùng một điểm đồng bộ chung:

- Guard row cho mỗi business key hoặc nhóm khóa.
- Advisory lock theo định danh nghiệp vụ nếu database hỗ trợ.
- SERIALIZABLE transaction với retry.
- Bảng idempotency/claim có khóa chính duy nhất.
- Một service ghi duy nhất có cơ chế điều phối.

Ví dụ guard table:

~~~sql
CREATE TABLE business_key_guard (
    tenant_id BIGINT NOT NULL,
    invitation_code VARCHAR(100) NOT NULL,
    PRIMARY KEY (tenant_id, invitation_code)
);
~~~

Transaction đầu tiên INSERT guard key. Transaction cạnh tranh sẽ xung đột trên primary key hoặc phải chờ transaction đầu tiên. Sau khi chiếm được guard, ứng dụng kiểm tra bảng nghiệp vụ và thực hiện INSERT.

Tuy nhiên, guard table về bản chất cũng dùng unique key làm cơ chế đồng bộ. Nếu có thể biểu diễn quy tắc ngay trên bảng nghiệp vụ, constraint trực tiếp thường đơn giản hơn.

Advisory lock chỉ hiệu quả khi mọi writer đều tuân thủ cùng quy tắc lấy lock. Một script hoặc service bỏ qua lock có thể tạo duplicate nếu bảng không có constraint.

## 16. Idempotency key và chống tạo bản ghi trùng khi retry

Một request có thể bị retry do timeout hoặc mất response. Nếu mỗi lần retry đều chạy check-then-insert, ứng dụng có thể tạo nhiều bản ghi cho cùng một ý định.

Có thể dùng bảng idempotency:

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    result_id BIGINT,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, idempotency_key)
) ENGINE = InnoDB;
~~~

Quy trình trong một transaction:

1. INSERT idempotency key.
2. Nếu key mới, tạo bản ghi nghiệp vụ.
3. Ghi result_id và trạng thái hoàn tất.
4. COMMIT tất cả cùng nhau.
5. Nếu key đã tồn tại, đọc kết quả đã ghi và trả lại nếu request hash khớp.

Unique key trên (tenant_id, idempotency_key) bảo đảm hai request cùng key không đồng thời trở thành hai thao tác độc lập.

Nếu cùng key nhưng payload khác, ứng dụng nên trả conflict thay vì âm thầm dùng kết quả của request cũ.

Định danh phải ổn định qua các lần retry của cùng một ý định. Không tạo idempotency key mới chỉ vì client timeout hoặc không nhận được response.

## 17. Xử lý transaction thua cuộc sau duplicate-key

Khi database từ chối INSERT thứ hai, ứng dụng cần biết transaction còn hoạt động hay không.

- MySQL InnoDB thường rollback statement duplicate nhưng transaction có thể tiếp tục.
- PostgreSQL đánh dấu transaction block aborted sau lỗi unique violation nếu lỗi không nằm trong phạm vi savepoint có thể phục hồi. Có thể dùng ON CONFLICT hoặc SAVEPOINT để xử lý.
- SQL Server phụ thuộc loại lỗi và cấu hình XACT_ABORT; cần kiểm tra XACT_STATE() trước khi tiếp tục.

Ví dụ PostgreSQL dùng ON CONFLICT tránh tạo exception:

~~~sql
BEGIN;

INSERT INTO invitations (tenant_id, invitation_code)
VALUES (7, 'WELCOME-2026')
ON CONFLICT (tenant_id, invitation_code)
DO NOTHING;

SELECT id
FROM invitations
WHERE tenant_id = 7
  AND invitation_code = 'WELCOME-2026';

COMMIT;
~~~

Ở READ COMMITTED, câu SELECT tiếp theo lấy snapshot mới của statement và có thể thấy row đã thắng cuộc cạnh tranh. Ở isolation level khác, transaction có thể cần xử lý serialization failure hoặc đọc lại trong transaction mới.

Với JDBC, nếu nhận exception duplicate, không nên mặc định connection luôn sẵn sàng cho câu SELECT tiếp theo. Phải hiểu transaction state của engine và transaction manager. Nếu transaction đã aborted hoặc rollback-only, rollback toàn bộ hoặc rollback về savepoint trước khi tiếp tục.

## 18. Không phải mọi duplicate đều có nghĩa request trước đó thành công

Giả sử hai request cùng dùng idempotency key K nhưng payload khác nhau:

~~~text
Request A:
    key = K
    amount = 100

Request B:
    key = K
    amount = 500
~~~

Nếu chỉ coi duplicate key là thành công, request B có thể nhận nhầm kết quả của request A dù ý định nghiệp vụ khác.

Cần lưu request fingerprint/hash hoặc các trường quan trọng để so sánh:

- Tenant hoặc merchant.
- Operation type.
- Business entity.
- Amount/currency nếu có thanh toán.
- Payload version.
- Request hash.

Quy tắc:

| Tình huống | Kết quả phù hợp |
|---|---|
| Cùng key, cùng payload, thao tác đã hoàn tất | Trả lại kết quả đã lưu |
| Cùng key, cùng payload, thao tác đang xử lý | Trả trạng thái đang xử lý hoặc chờ theo contract |
| Cùng key, payload khác | Conflict |
| Key mới, business key mới | Tạo mới |
| Key mới, business key đã tồn tại | Duplicate nghiệp vụ; trả kết quả hiện có hoặc conflict theo quy tắc |

Idempotency key và business unique key có thể là hai constraint khác nhau vì chúng bảo vệ hai quy tắc khác nhau.

## 19. Những lỗi triển khai thường gặp

### 19.1. SELECT rồi INSERT nhưng không có unique constraint

Đây là lỗi gốc. Hai request có thể cùng thấy không có bản ghi và cùng tạo mới.

### 19.2. Có index thường và nghĩ rằng đã bảo vệ tính duy nhất

Index thường chỉ hỗ trợ truy vấn. Nó không ngăn các giá trị trùng.

### 19.3. Bắt mọi lỗi INSERT rồi coi như duplicate

Lỗi có thể là CHECK violation, foreign-key violation, mất kết nối, deadlock hoặc lỗi schema. Chỉ xử lý như duplicate khi mã lỗi và constraint đúng với trường hợp dự kiến.

### 19.4. Dùng INSERT IGNORE để che mọi lỗi

INSERT IGNORE có thể biến một số lỗi dữ liệu thành warning. Ứng dụng có thể tưởng thao tác thành công trong khi dữ liệu bị bỏ qua hoặc bị điều chỉnh theo cách không mong muốn.

### 19.5. Dùng SELECT FOR UPDATE và giả định mọi database khóa được row chưa tồn tại

Locking semantics khác nhau giữa InnoDB, PostgreSQL và SQL Server. Row chưa tồn tại không phải lúc nào cũng có một record lock để khóa.

### 19.6. Thêm UNIQUE constraint nhưng không xử lý dữ liệu cũ

ALTER TABLE có thể thất bại vì duplicate hiện hữu. Cần phát hiện, hợp nhất hoặc loại bỏ dữ liệu trùng theo quy tắc nghiệp vụ trước khi tạo constraint.

### 19.7. Tạo unique key trên sai phạm vi

Nếu username duy nhất theo tenant nhưng constraint chỉ trên username toàn cục, hệ thống sẽ từ chối các giá trị hợp lệ giữa tenant. Nếu cần duy nhất toàn cục nhưng chỉ tạo key theo tenant, duplicate vẫn có thể xuất hiện.

### 19.8. Dùng idempotency key mới mỗi lần retry

Mỗi retry trông như một yêu cầu mới, nên deduplication không hoạt động.

### 19.9. Không phân biệt duplicate cùng ý định và duplicate xung đột nghiệp vụ

Cùng key và cùng payload có thể trả lại kết quả cũ. Cùng key nhưng payload khác phải được xem là conflict.

### 19.10. Gửi side effect trước khi transaction tạo bản ghi commit

Nếu gửi email hoặc publish event rồi INSERT thất bại, hệ thống bên ngoài đã nhận một thông báo cho bản ghi không tồn tại. Dùng Transactional Outbox để ghi event cùng transaction, sau đó relay publish khi commit thành công.

## 20. Kiểm thử race condition bằng nhiều session

Một test đơn luồng không thể tái hiện lỗi check-then-insert. Cần tạo cạnh tranh thực sự.

### Kịch bản kiểm thử

1. Chuẩn bị business key chưa tồn tại.
2. Mở hai connection độc lập.
3. Dùng barrier để hai worker cùng hoàn thành bước kiểm tra trước khi worker nào INSERT.
4. Cho cả hai cùng INSERT.
5. Xác nhận không có hơn một bản ghi với business key đó.
6. Xác nhận một worker thành công, worker còn lại nhận kết quả duplicate/conflict đã dự kiến.
7. Kiểm tra transaction thua cuộc vẫn ở trạng thái có thể phục hồi hoặc đã rollback đúng cách.
8. Lặp lại với nhiều worker và nhiều tenant.

Pseudocode:

~~~text
Worker A                         Worker B
--------                         --------
BEGIN                            BEGIN
SELECT key                       SELECT key
Barrier: both observed absence   Barrier: both observed absence
INSERT key                       INSERT key
COMMIT or handle duplicate       COMMIT or handle duplicate
~~~

Không dùng một connection dùng chung cho hai worker vì transaction và session state sẽ không còn độc lập.

### Điều kiện cần xác nhận

| Kiểm tra | Khi chưa có UNIQUE | Sau khi có UNIQUE |
|---|---|---|
| Hai SELECT cùng thấy 0 dòng | Có thể | Có thể |
| Hai INSERT cùng thành công | Có thể | Không |
| Số dòng cùng business key | Có thể lớn hơn 1 | Tối đa 1 |
| Có duplicate-key error | Không bắt buộc | Transaction thua cuộc có thể nhận |
| Có thể retry request | Có rủi ro tạo thêm bản ghi | Có thể xử lý bằng idempotency và đọc kết quả hiện có |

### Truy vấn xác nhận duplicate

~~~sql
SELECT
    tenant_id,
    invitation_code,
    COUNT(*) AS row_count
FROM invitations_lab
GROUP BY tenant_id, invitation_code
HAVING COUNT(*) > 1;
~~~

Sau khi constraint được tạo, truy vấn này phải không trả về nhóm nào.

## 21. Migration an toàn khi bảng đã có duplicate

Trong hệ thống đang chạy, thêm unique constraint có thể thất bại nếu dữ liệu trùng đã tồn tại. Cần có quy trình migration:

1. Xác định business key và phạm vi duy nhất.
2. Chạy truy vấn GROUP BY/HAVING để tìm duplicate.
3. Xác định bản ghi chuẩn cần giữ theo quy tắc nghiệp vụ.
4. Hợp nhất quan hệ tham chiếu, lịch sử và dữ liệu phụ thuộc trước khi xóa bản ghi trùng.
5. Ngăn writer mới tạo duplicate trong thời gian migration bằng guard hoặc quy trình tạm thời.
6. Dọn dữ liệu trùng.
7. Tạo UNIQUE constraint/index.
8. Kiểm tra constraint đã tồn tại và được enable/valid.
9. Triển khai code xử lý duplicate-key.
10. Theo dõi lỗi duplicate, latency và transaction retry sau migration.

Không nên tùy tiện xóa mọi dòng có id lớn hơn hoặc nhỏ hơn. Một bản ghi trùng có thể đang được tham chiếu bởi payment, order, audit hoặc các bảng khác. Quy tắc hợp nhất phải bảo toàn quan hệ nghiệp vụ.

Một số database hỗ trợ tạo index online/concurrently với giới hạn riêng. Ví dụ PostgreSQL có CREATE UNIQUE INDEX CONCURRENTLY, nhưng lệnh này không chạy trong transaction block thông thường và vẫn có thể thất bại nếu phát hiện duplicate. SQL Server và MySQL có tùy chọn online DDL theo edition, phiên bản và loại thao tác. Hãy lập kế hoạch migration theo engine thực tế.

## 22. Chọn chiến lược theo nghiệp vụ

| Trường hợp | Cơ chế phù hợp |
|---|---|
| Mã phải duy nhất toàn hệ thống | UNIQUE trên mã |
| Mã duy nhất trong tenant | UNIQUE(tenant_id, code) |
| Một consumer xử lý một event một lần | UNIQUE(consumer_name, event_id) trong Inbox |
| Client retry tạo cùng một yêu cầu | Idempotency key duy nhất và lưu kết quả |
| Tài nguyên có trạng thái chưa tồn tại cần được tuần tự hóa | Guard row/advisory lock, kèm constraint nếu có thể |
| Bản ghi xóa mềm cho phép tái sử dụng business key | Partial/filtered unique index hoặc thiết kế generated key theo engine |
| Điều kiện duy nhất phụ thuộc nhiều cột và trạng thái | Unique index phù hợp hoặc mô hình dữ liệu lại để biểu diễn rõ quy tắc |
| Quy tắc liên quan nhiều hàng, không thể biểu diễn bằng unique key | SERIALIZABLE, guard row hoặc cơ chế concurrency chuyên biệt |

Không có một câu SELECT nào có thể thay thế việc xác định chính xác invariant. Hãy bắt đầu từ câu hỏi nghiệp vụ: “Hai bản ghi nào không được phép cùng tồn tại?” rồi biểu diễn câu trả lời bằng unique key hoặc cơ chế database phù hợp.

## Kết luận

Mẫu kiểm tra không tồn tại rồi INSERT dễ gặp race condition vì kết quả SELECT có thể trở nên lỗi thời trước khi INSERT chạy. Hai transaction có thể cùng thấy không có bản ghi rồi cùng tạo bản ghi trùng. Đặt hai câu lệnh trong transaction hoặc thêm index thường không tự giải quyết vấn đề.

Hãy biểu diễn business key bằng UNIQUE constraint với đúng phạm vi, chẳng hạn UNIQUE(tenant_id, invitation_code). Sau đó để INSERT/UPSERT xử lý cạnh tranh và phân loại duplicate-key theo constraint, payload và ý định nghiệp vụ. SELECT FOR UPDATE, SERIALIZABLE, guard row và advisory lock có thể hỗ trợ đồng bộ trong một số tình huống, nhưng semantics phụ thuộc database và chúng không thay thế lớp bảo vệ dữ liệu bằng constraint khi tính duy nhất là invariant.

Khi triển khai, xử lý dữ liệu trùng cũ trước migration, kiểm thử bằng hai hoặc nhiều connection thực sự đồng thời, xử lý transaction state sau duplicate theo từng engine và dùng idempotency key nếu request có thể được retry. Kết quả cần được xác nhận ở database: không có hai bản ghi cùng business key sau bất kỳ lịch thực thi đồng thời nào.
