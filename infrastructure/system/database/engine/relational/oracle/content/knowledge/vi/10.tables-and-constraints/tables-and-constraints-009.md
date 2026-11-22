# ALTER TABLE: thêm, đổi, xóa cột và chuyển đổi dữ liệu trong Oracle Database

Trong vòng đời ứng dụng, cấu trúc bảng luôn có thể thay đổi: một màn hình cần thêm email, cột tên khách hàng quá ngắn, thuộc tính cũ phải đổi tên, hoặc một trường giá tiền đang lưu dưới dạng văn bản cần chuyển thành `NUMBER`. Oracle sử dụng lệnh **`ALTER TABLE`** để thay đổi định nghĩa bảng mà không nhất thiết phải tạo lại toàn bộ bảng. Tuy nhiên, **thay đổi định nghĩa cột không đồng nghĩa tự động chuyển đổi dữ liệu và mã ứng dụng**. Một thao tác DDL có thể hoàn thành trong vài giây ở bảng nhỏ nhưng tác động đáng kể đến khóa, redo/undo, constraint và những thành phần phụ thuộc ở bảng lớn.

Bài học thuộc nhóm **Bảng và ràng buộc** của Oracle Database, tập trung vào bốn nhóm thao tác: **thêm cột**, **sửa/đổi tên cột**, **xóa cột** và **chuyển đổi dữ liệu hiện hữu**. Phần chuyển đổi nhấn mạnh quy trình *expand → backfill → validate → cutover → contract*, hữu ích khi nâng cấp schema mà ứng dụng đang sử dụng.

Sau khi hoàn thành, bạn có thể:

- Viết `ALTER TABLE ... ADD`, `MODIFY`, `RENAME COLUMN`, `DROP COLUMN`, `SET UNUSED` và `DROP UNUSED COLUMNS`.
- Phân biệt **đổi tên cột**, **đổi datatype/độ dài** và **đổi dữ liệu thực sự**.
- Hiểu ảnh hưởng của `DEFAULT`, `NOT NULL`, `CHECK`, khóa, chỉ mục, view, trigger và code ứng dụng.
- Chuyển một cột `VARCHAR2` chứa số thành cột `NUMBER` bằng cách thêm cột mới, kiểm tra dữ liệu và backfill có kiểm soát.
- Kiểm tra cấu trúc trước/sau thay đổi qua `USER_TAB_COLUMNS`, `USER_CONSTRAINTS` và các data dictionary view liên quan.
- Giải thích vì sao Oracle DDL có **implicit commit**, tại sao không thể trông đợi `ROLLBACK` để hoàn tác thay đổi cấu trúc, và cách lập kế hoạch migration an toàn.

> **Cảnh báo phạm vi:** SQL trong bài sử dụng bảng lab `ALTER_TABLE_LAB` do chính bạn tạo trong một **PDB/schema thực hành**. Không chạy `DROP COLUMN`, `SET UNUSED` hay script đổi datatype trên bảng production chỉ để thử cú pháp. Các thao tác này có thể làm mất dữ liệu hoặc phá vỡ mã ứng dụng; quyền sở hữu bảng và kế hoạch triển khai phải được xác định trước.

## 1. Bản đồ thao tác `ALTER TABLE`

Oracle hỗ trợ nhiều kiểu thay đổi bảng. Những thao tác liên quan trực tiếp đến cột có thể phân nhóm:

| Mục tiêu | Cú pháp tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Thêm cột | `ALTER TABLE t ADD (new_col VARCHAR2(100 CHAR));` | Bổ sung thuộc tính mới |
| Thêm cột mặc định và bắt buộc | `ALTER TABLE t ADD (status VARCHAR2(20) DEFAULT 'NEW' NOT NULL);` | Giá trị mặc định, ràng buộc không NULL |
| Tăng độ dài | `ALTER TABLE t MODIFY (name VARCHAR2(200 CHAR));` | Sửa đặc tính cột đang có |
| Thay giá trị mặc định | `ALTER TABLE t MODIFY (status DEFAULT 'PENDING');` | Áp dụng cho lần insert sau, theo quy tắc default |
| Bắt buộc không NULL | `ALTER TABLE t MODIFY (name NOT NULL);` | Không cho phép giá trị NULL nếu dữ liệu hiện hữu thỏa điều kiện |
| Đổi tên cột | `ALTER TABLE t RENAME COLUMN old_name TO new_name;` | Đổi identifier, không tự biến đổi dữ liệu |
| Xóa cột trực tiếp | `ALTER TABLE t DROP COLUMN old_name;` | Loại bỏ cột và dữ liệu của nó |
| Đánh dấu cột không sử dụng | `ALTER TABLE t SET UNUSED (old_name);` | Ẩn/loại cột khỏi mô hình logic trước khi thu hồi vật lý |
| Thu hồi cột đã unused | `ALTER TABLE t DROP UNUSED COLUMNS;` | Dọn những cột đã `SET UNUSED` |

Đây không phải toàn bộ ngữ pháp `ALTER TABLE`: Oracle còn hỗ trợ partition, storage, index-related operations, constraints và nhiều loại thay đổi khác. Trong bài này, ta chỉ xử lý **column evolution** và dữ liệu phụ thuộc trực tiếp.

### 1.1. Một bảng có nhiều tầng liên quan

~~~text
                   UNG DUNG / JDBC / REPORT
                            |
                  SQL tham chieu ten cot
                            |
                            v
                     TABLE DEFINITION
          +-----------------+--------------------+
          | column names    | datatype/length    |
          | NULL/DEFAULT    | CHECK/PK/FK/UNIQUE  |
          +-----------------+--------------------+
                            |
                 DU LIEU THUC TRONG HANG
                            |
                indexes, views, triggers,
              procedures, grants, statistics
~~~

Ví dụ đổi tên cột có thể không thay đổi byte dữ liệu trong các row, nhưng **câu SQL của ứng dụng dùng tên cũ sẽ hỏng**. Ngược lại, chuyển giá tiền dạng chuỗi thành số đòi hỏi đọc, diễn giải, kiểm tra và ghi lại dữ liệu. Vì vậy luôn phân biệt **schema migration** với **data migration**.

### 1.2. `ALTER TABLE` là DDL, không phải DML

`ALTER TABLE` thuộc **Data Definition Language (DDL)**. Trong Oracle, DDL thường thực hiện **implicit COMMIT trước khi chạy và sau khi thực hiện thành công**. Không thể coi nó như `UPDATE` thông thường mà chạy `ROLLBACK` là khôi phục cấu trúc cũ.

~~~sql
-- Vi du minh hoa, KHONG can chay trong phien dang co DML chua commit.
UPDATE some_lab_table
SET remark = 'changed'
WHERE id = 1;

ALTER TABLE some_lab_table ADD (new_flag NUMBER);

ROLLBACK;
~~~

Ở đây `ROLLBACK` sau DDL không phải công cụ đảo ngược `ADD COLUMN`. Đáng chú ý, DML chưa commit **trước DDL** có thể đã được commit vì implicit commit trước câu DDL. Không trộn DDL với giao dịch nghiệp vụ chưa commit trong cùng một phiên.

DDL cũng cần các loại khóa để thay đổi metadata. Nếu có session đang sử dụng bảng hoặc giao dịch kéo dài, thao tác có thể chờ, thất bại do thiếu khóa, hoặc ảnh hưởng hoạt động. Thời gian và mức độ khóa phụ thuộc thao tác, phiên bản Oracle, dữ liệu và tải thực tế.

## 2. Chuẩn bị bảng lab và quan sát metadata

### 2.1. Xác nhận đúng schema/PDB

Trước khi tạo hoặc đổi bảng, chạy:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Trong CDB/PDB, hãy kết nối đến **PDB thực hành**, không dùng `CDB$ROOT` hoặc schema hệ thống để tạo bảng nghiệp vụ. Tài khoản lab cần các quyền thích hợp như `CREATE TABLE` và quota trên tablespace. Nếu đang làm trên schema người khác, quyền `ALTER` phải được cấp phù hợp; các ví dụ giả định bạn là **owner của bảng**.

### 2.2. Tạo dữ liệu mẫu

Đoạn dưới đây dùng một bảng nhỏ có ba đơn hàng. Giá tiền đang là **chuỗi** để sau đó thực hành chuyển sang `NUMBER`; hàng thứ ba cố ý có một giá trị không hợp lệ:

~~~sql
CREATE TABLE alter_table_lab (
    order_id      NUMBER
                  CONSTRAINT pk_alter_table_lab PRIMARY KEY,
    customer_name VARCHAR2(80 CHAR) NOT NULL,
    amount_text   VARCHAR2(30 CHAR),
    legacy_note   VARCHAR2(100 CHAR),
    created_at    TIMESTAMP WITH TIME ZONE
                  DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO alter_table_lab
    (order_id, customer_name, amount_text, legacy_note)
VALUES (1, 'Nguyễn An', '1250.50', 'Ghi chú cũ A');

INSERT INTO alter_table_lab
    (order_id, customer_name, amount_text, legacy_note)
VALUES (2, 'Trần Bình', '90.00', NULL);

INSERT INTO alter_table_lab
    (order_id, customer_name, amount_text, legacy_note)
VALUES (3, 'Lê Chi', 'unknown', 'Cần đối chiếu');

COMMIT;

SELECT order_id, customer_name, amount_text, legacy_note
FROM alter_table_lab
ORDER BY order_id;
~~~

Lý do dùng `VARCHAR2(30 CHAR)` cho `AMOUNT_TEXT` là để **minh họa dữ liệu legacy chưa chuẩn hóa**, không phải khuyến nghị lưu giá tiền bằng text. Dữ liệu tiền tệ thường phù hợp hơn với `NUMBER(p,s)` cộng quy ước đơn vị tiền và làm tròn rõ ràng.

Nếu bảng `ALTER_TABLE_LAB` đã tồn tại trong schema hiện tại, **không chạy lại `CREATE TABLE` rồi xóa bảng hiện có**. Hãy dùng một schema/bảng lab mới và thay tên nhất quán trong các ví dụ.

### 2.3. Xem danh sách cột hiện tại

~~~sql
SELECT
    column_id,
    column_name,
    data_type,
    data_length,
    char_length,
    char_used,
    nullable,
    data_default
FROM user_tab_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY column_id;
~~~

Một số cột metadata đáng chú ý:

| Cột dictionary | Ý nghĩa |
| --- | --- |
| `COLUMN_NAME` | Tên cột Oracle lưu (unquoted thường thành chữ hoa) |
| `DATA_TYPE` | Kiểu dữ liệu Oracle |
| `DATA_LENGTH` | Độ dài tối đa tính bằng byte đối với một số kiểu, không phải byte đang dùng trong từng row |
| `CHAR_LENGTH` | Độ dài theo ký tự đối với kiểu ký tự có liên quan |
| `CHAR_USED` | `B` nếu dùng BYTE semantics, `C` nếu dùng CHAR semantics |
| `NULLABLE` | Cột có cho phép NULL theo metadata hay không |
| `DATA_DEFAULT` | Biểu thức mặc định được lưu trong metadata |

`DATA_DEFAULT` có kiểu đặc biệt (`LONG`) ở một số dictionary view/phiên bản, nên tránh giả định mọi thao tác chuỗi, nhóm hoặc lọc lên cột này đều hoạt động giống `VARCHAR2`. Truy vấn trên chủ yếu nhằm **xem metadata**.

Để xem ràng buộc trên bảng:

~~~sql
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY constraint_name;

SELECT constraint_name, column_name, position
FROM user_cons_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY constraint_name, position;
~~~

Ràng buộc `PK_ALTER_TABLE_LAB` gắn với `ORDER_ID`. Không nên xóa cột có khóa/ràng buộc quan trọng mà chưa đối chiếu chúng và các khóa ngoại tham chiếu từ bảng khác.

## 3. Thêm cột bằng `ALTER TABLE ... ADD`

### 3.1. Thêm cột cho phép NULL

Thêm email vào bảng mẫu:

~~~sql
ALTER TABLE alter_table_lab
ADD (email VARCHAR2(200 CHAR));
~~~

Đây là dạng phổ biến nhất. Các hàng cũ sẽ có **giá trị logic `NULL`** tại cột mới, vì trước đây chúng không có thông tin email. Có thể cập nhật sau:

~~~sql
UPDATE alter_table_lab
SET email = 'an@example.com'
WHERE order_id = 1;

COMMIT;
~~~

Sau đó:

~~~sql
SELECT order_id, customer_name, email
FROM alter_table_lab
ORDER BY order_id;
~~~

Nếu đang tạo nhiều cột cùng lúc:

~~~sql
ALTER TABLE alter_table_lab
ADD (
    phone_number VARCHAR2(30 CHAR),
    note_text    VARCHAR2(300 CHAR)
);
~~~

Các kiểu, độ dài và semantics nên phản ánh ý nghĩa nghiệp vụ. Số điện thoại thường nên dùng `VARCHAR2` thay vì `NUMBER` vì có thể có số 0 đầu, dấu cộng và mã quốc gia; còn cột thực sự cần tính toán số học thì dùng kiểu số.

### 3.2. Thêm cột `DEFAULT`

Một trạng thái đơn hàng có thể cần giá trị mặc định:

~~~sql
ALTER TABLE alter_table_lab
ADD (order_status VARCHAR2(12 CHAR) DEFAULT 'NEW');
~~~

Khi một lệnh `INSERT` mới **không chỉ định** `ORDER_STATUS`, Oracle áp dụng default theo định nghĩa của cột. Mặc định kiểu này không có nghĩa mọi lệnh insert `NULL` tường minh sẽ tự chuyển thành `'NEW'`. Với một số phiên bản, `DEFAULT ON NULL` là tính năng riêng có semantics khác.

Trên bảng đã có dữ liệu, cột thêm với default có thể được Oracle triển khai thông qua metadata optimization tùy phiên bản và điều kiện. Không mặc định mọi `ADD ... DEFAULT` đều đọc/ghi lại toàn bộ bảng, cũng không bảo đảm mọi trường hợp đều là thao tác “zero cost”.

### 3.3. Thêm cột `DEFAULT ... NOT NULL`

Nếu muốn mọi đơn hàng luôn có trạng thái:

~~~sql
-- Vi du tren bang lab chua co cot ORDER_STATUS.
ALTER TABLE alter_table_lab
ADD (
    order_status VARCHAR2(12 CHAR)
    DEFAULT 'NEW' NOT NULL
);
~~~

Chú ý: đoạn này là **biến thể thay thế** cho lệnh thêm `ORDER_STATUS` ở mục 3.2. Nếu đã thực hiện mục 3.2, không được chạy lại `ADD` với cùng tên cột; thay vào đó, sau khi xử lý giá trị NULL:

~~~sql
UPDATE alter_table_lab
SET order_status = 'NEW'
WHERE order_status IS NULL;

COMMIT;

ALTER TABLE alter_table_lab
MODIFY (order_status NOT NULL);
~~~

Thêm cột `NOT NULL` **không có default** vào bảng đã có hàng thường không hợp lệ vì những hàng đó không có giá trị cho cột mới. Oracle có thể báo `ORA-01758` (*table must be empty to add mandatory column*). Quy trình an toàn hơn là:

1. Thêm cột **cho phép NULL**.
2. Backfill dữ liệu cho các hàng hiện có theo quy tắc nghiệp vụ.
3. Xác nhận không còn NULL ở những hàng cần bắt buộc.
4. Áp `NOT NULL` và thêm `DEFAULT` nếu phù hợp.

Trình tự này đặc biệt hữu ích khi backfill phải dựa trên phép tính hoặc dữ liệu từ bảng khác, thay vì một giá trị default giống nhau cho mọi hàng.

### 3.4. Thêm constraint ngay khi khai báo cột

Ví dụ, trường phần trăm giảm giá có thể được giới hạn:

~~~sql
ALTER TABLE alter_table_lab
ADD (
    discount_pct NUMBER(5,2) DEFAULT 0 NOT NULL
        CONSTRAINT ck_alter_lab_discount
        CHECK (discount_pct BETWEEN 0 AND 100)
);
~~~

`NUMBER(5,2)` cho phép tối đa 5 chữ số có ý nghĩa với 2 chữ số thập phân; constraint giới hạn giá trị hợp lệ trong khoảng 0–100. Đừng nhầm datatype với constraint: `NUMBER(5,2)` tự nó không ngăn giá trị âm.

Khi thêm constraint cho bảng có dữ liệu, Oracle có thể cần kiểm tra các hàng hiện hữu. Nếu dữ liệu đang vi phạm, thao tác có thể thất bại; không tự tắt kiểm tra hoặc đặt `NOVALIDATE` chỉ để migration “chạy qua” mà chưa hiểu rủi ro.

## 4. Sửa định nghĩa cột bằng `ALTER TABLE ... MODIFY`

### 4.1. Tăng độ dài cột ký tự

Ban đầu `CUSTOMER_NAME` có kiểu `VARCHAR2(80 CHAR)`. Nếu nghiệp vụ cần tối đa 160 ký tự:

~~~sql
ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(160 CHAR));
~~~

Thông thường việc **nới rộng** cột ký tự tương thích có thể thực hiện mà không cần chuyển từng giá trị hiện hữu sang kiểu mới theo cách ứng dụng tự viết. Tuy vậy vẫn là DDL, có khóa và có thể ảnh hưởng thành phần phụ thuộc. Kiểm tra lại metadata:

~~~sql
SELECT column_name, data_type, char_length, char_used
FROM user_tab_columns
WHERE table_name = 'ALTER_TABLE_LAB'
  AND column_name = 'CUSTOMER_NAME';
~~~

`VARCHAR2(160 CHAR)` giới hạn theo ký tự, nhưng vẫn chịu trần byte của `VARCHAR2` theo `MAX_STRING_SIZE` và character set. Đổi cột từ `BYTE` sang `CHAR` không tự sửa encoding của dữ liệu đã bị lỗi trước đó.

### 4.2. Thu nhỏ độ dài: phải xem dữ liệu đang có

Giả sử bạn muốn hạ giới hạn tên xuống 40 ký tự. Trước hết:

~~~sql
SELECT
    MAX(LENGTH(customer_name)) AS max_chars,
    MAX(LENGTHB(customer_name)) AS max_bytes
FROM alter_table_lab;
~~~

Sau đó nếu thực sự phù hợp mới cân nhắc:

~~~sql
-- Chi chay khi da xac nhan khong mat du lieu va phu thuoc.
ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(40 CHAR));
~~~

Nếu có giá trị vượt kích thước mới, Oracle có thể báo `ORA-01441` (*cannot decrease column length because some value is too big*). Không xử lý bằng cách cắt chuỗi tên khách hàng tự động nếu nghiệp vụ không cho phép. Ngoài ra, giới hạn của ràng buộc, chỉ mục và hình thức thay đổi datatype cũng phải được xem xét.

### 4.3. Đổi `DEFAULT`

Nếu `ORDER_STATUS` hiện có và muốn các đơn hàng mới bắt đầu ở `PENDING`:

~~~sql
ALTER TABLE alter_table_lab
MODIFY (order_status DEFAULT 'PENDING');
~~~

Lệnh đổi **default cho các lần ghi tiếp theo** theo semantics của cột, **không được xem là lệnh backfill tất cả hàng cũ**. Nếu nghiệp vụ muốn đổi trạng thái của một số hàng hiện hữu, dùng DML tường minh và điều kiện đủ chặt:

~~~sql
UPDATE alter_table_lab
SET order_status = 'PENDING'
WHERE order_status = 'NEW';

COMMIT;
~~~

Trước khi chạy `UPDATE` trong ứng dụng thực, cần biết liệu các hàng `NEW` đã giao cho workflow khác hay chưa; không đánh đồng thay đổi default với thay đổi trạng thái nghiệp vụ.

### 4.4. Thêm hoặc bỏ `NOT NULL`

Nếu cột đã có dữ liệu:

~~~sql
SELECT COUNT(*) AS null_email_count
FROM alter_table_lab
WHERE email IS NULL;
~~~

Muốn bắt buộc có email, bạn cần xử lý các hàng chưa có email theo chính sách dữ liệu rồi mới chạy:

~~~sql
-- Chi thuc hien sau khi NULL_EMAIL_COUNT = 0 va da duyet quy tac.
ALTER TABLE alter_table_lab
MODIFY (email NOT NULL);
~~~

Nếu còn NULL, Oracle không thể xác nhận constraint; có thể gặp `ORA-02296` (*cannot enable ... null values found*).

Để cho phép NULL trở lại (nếu không xung đột ràng buộc như primary key):

~~~sql
ALTER TABLE alter_table_lab
MODIFY (email NULL);
~~~

Thay đổi `NULL/NOT NULL` không phải là cách gán giá trị mới cho dữ liệu. `NOT NULL` kiểm soát tính hợp lệ của row, còn `DEFAULT` quyết định hành vi khi insert không truyền giá trị (hoặc theo cú pháp `DEFAULT ON NULL` nếu được khai báo). Hai cơ chế có liên quan nhưng không giống nhau.

### 4.5. Sửa precision/scale hoặc datatype: không nên đoán

Ví dụ có cột `NUMBER(8,2)` và muốn thành `NUMBER(12,2)`, hoặc muốn giảm scale. Các ràng buộc của Oracle với `NUMBER` phụ thuộc kiểu thay đổi và trạng thái dữ liệu. Thu hẹp precision/scale khi cột đang có giá trị có thể dẫn tới lỗi như `ORA-01440`. Không nên tự kết luận “toàn bộ giá trị hiện tại vừa giới hạn mới thì mọi thay đổi NUMBER đều được cho phép”.

Đặc biệt, đổi `VARCHAR2` sang `NUMBER` hoặc `DATE` trực tiếp trên cột **có dữ liệu** thường bị hạn chế; Oracle có thể báo `ORA-01439` (*column to be modified must be empty to change datatype*). Có những chuyển đổi datatype tương thích được Oracle cho phép, nhưng **không dùng sự tồn tại của chúng làm chiến lược chuyển dữ liệu nghiệp vụ**.

Mẫu rủi ro:

~~~sql
-- Khong dung cho cot AMOUNT_TEXT co du lieu trong lab:
ALTER TABLE alter_table_lab
MODIFY (amount_text NUMBER(12,2));
~~~

Cách bền vững cho tình huống này là **tạo cột số mới, chuyển giá trị bằng `TO_NUMBER` sau khi làm sạch, đối chiếu, rồi đổi tên/xóa cột cũ**. Chi tiết ở Mục 7.

## 5. Đổi tên cột bằng `RENAME COLUMN`

Đổi tên là thao tác thay **identifier của cột**, không tự thay nội dung từng row:

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_note TO legacy_comment;
~~~

Sau lệnh, mã SQL muốn đọc cột cần dùng tên mới:

~~~sql
SELECT order_id, legacy_comment
FROM alter_table_lab
ORDER BY order_id;
~~~

Truy vấn `SELECT legacy_note FROM alter_table_lab` sẽ không còn tham chiếu được tên cũ và thường báo `ORA-00904`.

### 5.1. Tác động lên ứng dụng và đối tượng phụ thuộc

Oracle cập nhật metadata của cột trong bảng; một số ràng buộc và cấu trúc nội bộ được Oracle duy trì theo khả năng hỗ trợ. Tuy nhiên, **không được giả định mọi view, trigger, package, stored procedure, report và SQL ở ứng dụng đều tự đổi theo**:

- SQL trong Java/JDBC hoặc ORM có thể vẫn gọi `LEGACY_NOTE`.
- View, PL/SQL object hoặc object phụ thuộc có thể bị invalid hoặc cần biên dịch/sửa.
- Quyền và logic liên quan đến cột cần được rà soát theo loại object và phiên bản Oracle.
- Các công cụ xuất CSV, JSON mapping và API có thể đang sử dụng tên cột cũ.

Một tên đã được dùng rộng rãi thường cần kế hoạch **tương thích chuyển tiếp**. Đổi tên trực tiếp trong một hệ thống có nhiều phiên bản ứng dụng hoạt động đồng thời có thể làm ứng dụng cũ lỗi ngay sau DDL.

### 5.2. Tên quoted và case sensitivity

Nếu chạy:

~~~sql
-- Vi du cu phap; khong can chay trong lab chinh.
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_comment TO "LegacyComment";
~~~

tên mới là `LegacyComment`, không phải `LEGACYCOMMENT`. Mọi SQL phải dùng `"LegacyComment"` đúng chữ hoa/thường. Với schema mới, nên dùng **unquoted uppercase-normalized identifiers** theo một quy ước thống nhất để tránh phát sinh lỗi.

### 5.3. Đổi tên cột không phải đổi tên bảng

Hai lệnh khác nhau:

~~~sql
-- Doi ten mot cot:
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_note TO legacy_comment;

-- Doi ten ca bang (khong phai thao tac cot):
ALTER TABLE alter_table_lab
RENAME TO alter_table_lab_new;
~~~

Chỉ thực hiện **một ví dụ phù hợp với mục tiêu**. Nếu chạy lệnh đổi tên bảng thứ hai, những lệnh sau trong bài dùng tên `ALTER_TABLE_LAB` sẽ không còn chạy nếu bạn chưa sửa tên tương ứng.

## 6. Xóa cột: `DROP COLUMN` và `SET UNUSED`

### 6.1. Xóa trực tiếp bằng `DROP COLUMN`

Nếu cột `PHONE_NUMBER` đã được thêm trong lab và được xác nhận không còn cần:

~~~sql
ALTER TABLE alter_table_lab
DROP COLUMN phone_number;
~~~

Lệnh xóa cột loại bỏ giá trị của cột khỏi mô hình và có thể yêu cầu Oracle xử lý dữ liệu vật lý. Nó **không có `ROLLBACK` DDL** để lấy lại cột cùng dữ liệu như trước. Thời gian thực thi, redo/undo, locking và khả năng online tùy kích thước bảng/tính năng/cấu hình.

Một số giới hạn:

- Không thể xóa tùy tiện cột nằm trong primary key/unique/check/foreign key, virtual column hoặc các phụ thuộc mà Oracle không thể tự xử lý theo lệnh hiện tại.
- Có trường hợp cần bỏ/chỉnh ràng buộc và đối tượng phụ thuộc trước khi drop.
- Không xóa **cột cuối cùng** để biến một bảng thành không có cột.
- Nếu có khóa ngoại ở bảng khác tham chiếu key liên quan, việc dùng `CASCADE CONSTRAINTS` có thể xóa ràng buộc liên quan ở bảng khác; không dùng tùy tiện.

Ví dụ nhận diện cú pháp:

~~~sql
-- Can xem dependency truoc khi CASCADE; khong chay tren bang quan trong.
ALTER TABLE some_lab_table
DROP COLUMN some_column CASCADE CONSTRAINTS;
~~~

`CASCADE CONSTRAINTS` không có nghĩa Oracle tự sửa logic ứng dụng một cách an toàn. Đây là lựa chọn có thể phá vỡ tính toàn vẹn dữ liệu nếu không kiểm soát.

### 6.2. `SET UNUSED`: bỏ cột khỏi cách nhìn logic trước

Khi xóa một cột lớn, Oracle hỗ trợ đánh dấu **UNUSED**:

~~~sql
ALTER TABLE alter_table_lab
SET UNUSED (legacy_comment);
~~~

Sau thao tác này:

- Cột không còn được truy cập bằng tên cũ trong SQL thông thường.
- Nó không xuất hiện như cột sử dụng bình thường trong `USER_TAB_COLUMNS`.
- Nội dung vật lý có thể vẫn tồn tại để Oracle dọn ở thời điểm khác.
- Đây là một thay đổi schema có thể **không đảo ngược trực tiếp** về cột/dữ liệu cũ; không coi nó là “ẩn tạm an toàn để bật lại”.

`SET UNUSED` có thể hữu ích để tách **thời điểm loại bỏ cột khỏi giao diện logic** khỏi **thời điểm thu hồi không gian vật lý**, nhưng việc dọn sau đó vẫn cần kế hoạch.

### 6.3. Xóa vật lý các cột đã unused

~~~sql
ALTER TABLE alter_table_lab
DROP UNUSED COLUMNS;
~~~

Đây có thể là thao tác tốn tài nguyên với bảng rất lớn. Lên lịch và giám sát theo hướng dẫn phiên bản Oracle phù hợp; có những lựa chọn quản trị chuyên biệt hỗ trợ các tình huống drop bị gián đoạn hoặc xử lý theo checkpoint. **Không giả định `SET UNUSED` là backup hoặc thao tác hoàn toàn miễn phí**.

Oracle còn cung cấp thông tin số lượng cột unused:

~~~sql
SELECT table_name, count
FROM user_unused_col_tabs
WHERE table_name = 'ALTER_TABLE_LAB';
~~~

`COUNT` ở đây là số cột unused của bảng theo view, **không phải số hàng dữ liệu**. Nếu chưa `SET UNUSED`, truy vấn có thể không trả dòng cho bảng đó.

### 6.4. Khi nào chọn `DROP` hay `SET UNUSED`?

| Tiêu chí | `DROP COLUMN` | `SET UNUSED` rồi `DROP UNUSED COLUMNS` |
| --- | --- | --- |
| Loại cột khỏi SQL/metadata sử dụng | Có | Có ngay sau `SET UNUSED` |
| Cột còn có thể dùng bằng tên cũ | Không | Không |
| Thu hồi không gian vật lý | Tùy quá trình drop | Hoãn đến giai đoạn `DROP UNUSED` |
| Rủi ro mất dữ liệu | Có | Có, không xem là reversible |
| Phù hợp cho | Bảng nhỏ hoặc điều kiện quản trị cho phép drop trực tiếp | Tách pha bỏ logic và pha dọn vật lý ở bảng lớn |

Trước cả hai phương án, nên ngừng phụ thuộc vào cột, có backup cần thiết và xác nhận các báo cáo/script không còn sử dụng tên đó.

## 7. Chuyển đổi dữ liệu: từ `VARCHAR2` sang `NUMBER`

Đây là phần quan trọng nhất khi yêu cầu **“chuyển đổi dữ liệu”**. Giả sử cột `AMOUNT_TEXT` hiện chứa:

~~~text
ORDER_ID    AMOUNT_TEXT
--------    -----------
1           1250.50
2           90.00
3           unknown
~~~

Không thể an toàn chạy `MODIFY (amount_text NUMBER(12,2))` rồi kỳ vọng Oracle hiểu `unknown` cần chuyển thành giá trị nào. Ngay cả với các hàng trông như số, việc chuyển đổi còn phụ thuộc dấu thập phân và thiết lập NLS. Phải thiết kế **quy tắc làm sạch** trước.

### 7.1. Sơ đồ migration có kiểm soát

~~~text
PHASE 1 - EXPAND
  AMOUNT_TEXT VARCHAR2(30)      +      AMOUNT_NEW NUMBER(12,2)
                 |                             ^
                 |                             |
PHASE 2 - VALIDATE / BACKFILL  -----------------+
  Phat hien gia tri sai, chuan hoa dinh dang,
  TO_NUMBER vao cot moi; giu cot cu de doi chieu.
                 |
PHASE 3 - VERIFY
  Kiem tra so hang, gia tri, null, precision,
  cac quy tac nghiep vu va doi tuong phu thuoc.
                 |
PHASE 4 - CUTOVER
  Dung ghi khong dong bo; chuyen SQL/ung dung sang cot moi.
  Doi ten cot cu/moi neu can.
                 |
PHASE 5 - CONTRACT
  Sau thoi gian xac nhan, SET UNUSED/DROP cot cu,
  sao luu va cap nhat tai lieu schema.
~~~

Nếu hệ thống vẫn nhận DML trong khi backfill, bạn phải thiết kế cơ chế **dual-write, trigger đồng bộ có kiểm soát, batch/CDC, hoặc cửa sổ dừng ghi** phù hợp. Chỉ chạy một lệnh `UPDATE` không ngăn các hàng mới được insert vào cột cũ sau đó.

### 7.2. Bước 1 — Thêm cột đích

~~~sql
ALTER TABLE alter_table_lab
ADD (amount_new NUMBER(12,2));
~~~

Kiểu `NUMBER(12,2)` lưu số có tối đa 12 chữ số có ý nghĩa, trong đó 2 chữ số thập phân theo scale khai báo. Ví dụ `1250.50` là giá trị phù hợp. Việc Oracle làm tròn khi ghi giá trị có nhiều chữ số thập phân cần được xét theo nghiệp vụ; **không mặc định việc làm tròn là chấp nhận được đối với tiền**.

Chưa áp `NOT NULL` khi dữ liệu vẫn đang cần làm sạch, vì hàng `unknown` chưa có một giá trị số hợp lệ.

### 7.3. Bước 2 — Thống nhất định dạng nguồn

Trong lab, quy tắc nguồn được chọn rõ ràng:

- Số dương, phần nguyên dài từ **1 đến 10 chữ số**.
- Bắt buộc có dấu chấm `.` làm dấu thập phân.
- Phần thập phân có **đúng 2 chữ số**.
- Không có dấu phân nhóm hàng nghìn, đơn vị tiền hoặc chữ bổ sung.
- `NULL` có thể được xử lý riêng theo yêu cầu nghiệp vụ.

Quy tắc này cố ý hẹp để không âm thầm diễn giải sai `1,234` thành 1.234 hay 1234 tùy locale. Với dữ liệu thật, bộ quy tắc phải phản ánh định dạng nguồn, dấu âm, tiền tệ, số mũ, khoảng trắng và dữ liệu lịch sử.

Tìm các hàng không phù hợp:

~~~sql
SELECT order_id, amount_text
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND NOT REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  )
ORDER BY order_id;
~~~

Với dữ liệu lab, hàng `ORDER_ID=3` chứa `unknown` sẽ xuất hiện. Hãy **ghi nhận giá trị lỗi**, tra nguồn nghiệp vụ và quyết định có sửa hay không. Không tự thay chuỗi không hợp lệ bằng 0, vì 0 là số tiền thật và có ý nghĩa hoàn toàn khác “không rõ”.

### 7.4. Bước 3 — Backfill các hàng hợp lệ

Sau khi kiểm tra định dạng:

~~~sql
UPDATE alter_table_lab
SET amount_new = TO_NUMBER(
    TRIM(amount_text),
    '9999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
WHERE amount_text IS NOT NULL
  AND REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

COMMIT;
~~~

Trong `TO_NUMBER`:

- Format model `9999999999D99` diễn giải phần nguyên và hai chữ số thập phân.
- `D` dùng dấu thập phân theo NLS numeric characters.
- `'NLS_NUMERIC_CHARACTERS=''.,'''` chỉ định dấu chấm làm thập phân, dấu phẩy làm group separator cho phép chuyển đổi này, thay vì phụ thuộc mặc định phiên.

Không nên thay biểu thức bằng `TO_NUMBER(amount_text)` nếu dữ liệu có khả năng chạy trong các session NLS khác nhau hoặc từ hệ thống khác. SQL trên vẫn chỉ là ví dụ cho **định dạng đã xác nhận**, không phải bộ chuyển đổi đa định dạng tổng quát.

Trong lab, hai hàng hợp lệ sẽ có số `1250.50` và `90.00` ở `AMOUNT_NEW`. Hàng `unknown` còn `NULL` ở cột mới.

### 7.5. Bước 4 — Phát hiện hàng chưa chuyển thành công

~~~sql
SELECT order_id, amount_text, amount_new
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND amount_new IS NULL
ORDER BY order_id;
~~~

Không nên vội chạy `ALTER TABLE ... MODIFY (amount_new NOT NULL)` khi kết quả còn có hàng chưa chuyển. Để bài lab tiếp tục, giả sử bạn kiểm tra nguồn và xác nhận **giá trị đúng** của đơn hàng số 3 là `35.00`:

~~~sql
-- Vi du gia dinh da xac minh gia tri voi nguon nghiep vu.
UPDATE alter_table_lab
SET amount_text = '35.00'
WHERE order_id = 3;

UPDATE alter_table_lab
SET amount_new = TO_NUMBER(
    TRIM(amount_text),
    '9999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
WHERE amount_text IS NOT NULL
  AND amount_new IS NULL
  AND REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

COMMIT;
~~~

Trong sản phẩm thật, thay đổi giá tiền **phải có căn cứ nghiệp vụ và dấu vết kiểm toán**; không được tự bịa `35.00` nếu không có nguồn đáng tin.

### 7.6. Bước 5 — Đối chiếu trước cutover

~~~sql
SELECT
    order_id,
    amount_text,
    amount_new
FROM alter_table_lab
ORDER BY order_id;

SELECT COUNT(*) AS unconverted_rows
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND amount_new IS NULL;

SELECT COUNT(*) AS missing_numeric_rows
FROM alter_table_lab
WHERE amount_new IS NULL;
~~~

Hai câu `COUNT` có ý nghĩa khác nhau:

- `UNCONVERTED_ROWS`: hàng có dữ liệu nguồn nhưng chưa có số đích.
- `MISSING_NUMERIC_ROWS`: **mọi hàng** chưa có số đích, kể cả nguồn `NULL`.

Nếu cột số đích phải `NOT NULL`, chỉ khi đã giải quyết toàn bộ các hàng NULL (theo nghiệp vụ) mới được áp constraint. Với bảng có hàng được insert/update đồng thời, việc kiểm tra một lần không đủ chứng minh trạng thái không thay đổi trước cutover.

Đối chiếu tổng tiền trong lab có thể là:

~~~sql
SELECT COUNT(*) AS row_count,
       SUM(amount_new) AS total_amount
FROM alter_table_lab;
~~~

Không dùng tổng số tiền làm kiểm tra duy nhất vì hai giá trị sai có thể bù trừ nhau. Khi dữ liệu quan trọng, cần đối chiếu theo **khóa chính**, định dạng, giá trị và hàng ngoại lệ.

### 7.7. Bước 6 — Cutover tên cột

Khi ứng dụng đã chuẩn bị đổi từ `AMOUNT_TEXT` sang `AMOUNT`, có thể thực hiện trên **lab đã ngừng ghi**:

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN amount_text TO amount_text_legacy;

ALTER TABLE alter_table_lab
RENAME COLUMN amount_new TO amount;

-- Chi ap dung khi tat ca hang da co gia tri hop le:
ALTER TABLE alter_table_lab
MODIFY (amount NOT NULL);
~~~

Đổi tên không tự sửa Java/SQL của ứng dụng. Sau lệnh, các câu DML dùng `AMOUNT_TEXT` sẽ không còn hoạt động. Trên hệ thống có nhiều phiên bản ứng dụng cùng chạy, nên dùng thiết kế chuyển tiếp hỗ trợ cả hai phiên bản, cửa sổ triển khai hoặc giải pháp online redefinition phù hợp. Cũng cần cập nhật:

- SQL select/insert/update, stored procedures, view, trigger.
- ORM/JPA mapping, báo cáo, ETL, API contract.
- Constraint, index, permission cấp cột và code phát hiện schema bằng metadata.
- Job xử lý dữ liệu, dữ liệu đồng bộ và quy trình backup/recovery.

### 7.8. Bước 7 — Chỉ xóa cột cũ sau khi xác nhận

Sau một giai đoạn xác nhận ứng dụng đã dùng `AMOUNT`, có thể bỏ cột text cũ:

~~~sql
-- Chi chay khi da co backup/ke hoach recovery va khong con phu thuoc.
ALTER TABLE alter_table_lab
SET UNUSED (amount_text_legacy);

-- Thuc hien thu hoi vat ly vao thoi diem van hanh duoc phep.
ALTER TABLE alter_table_lab
DROP UNUSED COLUMNS;
~~~

Nếu trước đó đã `SET UNUSED` cột `LEGACY_COMMENT`, `DROP UNUSED COLUMNS` sẽ dọn **những cột đã unused của bảng**, không chỉ một cột tên cũ. Kiểm tra trạng thái bảng và nội dung cần giữ trước khi chạy.

**Nguyên tắc:** thêm cột mới là bước dễ có lựa chọn dự phòng hơn. Nhưng một khi xóa cột cũ hoặc dữ liệu nguồn, việc quay lại có thể đòi hỏi restore dữ liệu. Không đánh đồng “đã chạy DDL thành công” với “đã hoàn thành migration an toàn”.

## 8. Chuyển đổi từ chuỗi sang ngày giờ

Đổi `VARCHAR2` sang `DATE` cũng không nên dựa vào implicit conversion, vì có thể phụ thuộc `NLS_DATE_FORMAT` và văn bản nguồn có thể sai ngày.

Giả sử một bảng khác có cột `ORDER_DATE_TEXT` lưu chuỗi chuẩn `YYYY-MM-DD`, ví dụ `2026-11-14`. Quy trình khái niệm:

~~~sql
-- Vi du tren mot bang lab rieng co cot ORDER_DATE_TEXT.
ALTER TABLE order_date_lab
ADD (order_date DATE);

-- Oracle 12.2+ ho tro VALIDATE_CONVERSION.
SELECT order_id, order_date_text
FROM order_date_lab
WHERE order_date_text IS NOT NULL
  AND VALIDATE_CONVERSION(
      order_date_text AS DATE, 'FXYYYY-MM-DD'
  ) = 0;

UPDATE order_date_lab
SET order_date = TO_DATE(order_date_text, 'FXYYYY-MM-DD')
WHERE order_date_text IS NOT NULL
  AND VALIDATE_CONVERSION(
      order_date_text AS DATE, 'FXYYYY-MM-DD'
  ) = 1;

COMMIT;
~~~

Đây là **ví dụ mẫu**, không chạy được trong lab chính nếu bạn chưa tạo `ORDER_DATE_LAB`. `FX` yêu cầu sự khớp chính xác hơn với format (tránh parser chấp nhận biến thể không mong muốn), còn `VALIDATE_CONVERSION` giúp phát hiện ngày không hợp lệ mà không chuyển từng giá trị lỗi bằng `TO_DATE` trong `UPDATE`.

Ví dụ `2026-02-30` khớp cấu trúc chữ số và dấu gạch nối nhưng **không phải ngày tồn tại**, nên kiểm tra regex đơn thuần không đủ thay cho phép kiểm tra chuyển đổi ngày.

Với datetime có giờ và múi giờ, cân nhắc `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE` và `TO_TIMESTAMP`/`TO_TIMESTAMP_TZ` thay vì `DATE` nếu nghiệp vụ cần fractional seconds hoặc offset. Không chuyển chuỗi giờ địa phương thành UTC nếu chưa biết **timezone gốc**; một giá trị `2026-11-14 09:00:00` không tự chỉ một instant duy nhất.

### 8.1. Chuyển đổi kiểu ký tự BYTE/CHAR

Ngoài chuyển từ text sang số/ngày, có thể cần chuyển định nghĩa:

~~~sql
-- Vi du thay doi ngữ nghĩa do dai cua mot cot lab:
ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(160 CHAR));
~~~

Khi database dùng `AL32UTF8`, nhiều ký tự tiếng Việt có dấu chiếm hơn một byte. `VARCHAR2(100 BYTE)` không tương đương `VARCHAR2(100 CHAR)`; đồng thời `CHAR` semantics vẫn chịu giới hạn byte tối đa của `VARCHAR2`. Trước khi giảm kích thước hoặc đổi semantics, đo `LENGTH`, `LENGTHB` và xem `CHAR_USED` trong data dictionary.

### 8.2. Những trường không nên chuyển tùy tiện sang số

Đừng biến **số điện thoại, mã bưu chính, mã khách hàng hoặc số chứng từ** thành `NUMBER` chỉ vì chúng có toàn chữ số ở thời điểm hiện tại. Các giá trị đó là **định danh**, có thể có số 0 ở đầu, dấu `+`, ký tự phân cách và không cần phép toán số học.

Quy tắc chọn datatype là theo **ý nghĩa và phép toán nghiệp vụ**, không phải theo hình thức hiện thời của dữ liệu.

## 9. Phụ thuộc schema: constraint, index, view và PL/SQL

### 9.1. Xem constraint trước khi sửa hoặc xóa cột

~~~sql
SELECT
    c.constraint_name,
    c.constraint_type,
    c.status,
    cc.column_name,
    cc.position
FROM user_constraints c
JOIN user_cons_columns cc
    ON cc.constraint_name = c.constraint_name
   AND cc.table_name = c.table_name
WHERE c.table_name = 'ALTER_TABLE_LAB'
ORDER BY c.constraint_name, cc.position;
~~~

Những kiểu constraint thường gặp:

| `CONSTRAINT_TYPE` | Nhóm ràng buộc | Tác động khi đổi/xóa cột |
| --- | --- | --- |
| `P` | Primary key | Không được xóa cột key nếu chưa thiết kế lại định danh/tham chiếu |
| `U` | Unique | Index/constraint uniqueness có thể liên quan |
| `R` | Foreign key | Cần kiểm tra cả bảng con và bảng được tham chiếu |
| `C` | Check, thường bao gồm NOT NULL trong dictionary | Phải đáp ứng điều kiện dữ liệu trước khi bật/đổi constraint |

Oracle có thêm các loại constraint khác tùy tính năng. Vì vậy, trước khi xóa một cột, cần kiểm tra **constraint ở bảng hiện tại và foreign keys của bảng khác**.

### 9.2. Index có dùng cột định sửa không?

~~~sql
SELECT index_name, column_name, column_position
FROM user_ind_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY index_name, column_position;
~~~

Với function-based index, cần kiểm tra thêm biểu thức index và khả năng ảnh hưởng của việc đổi tên/đổi datatype. Khi một cột được dùng trong index key, việc đổi độ dài hoặc type có thể kéo theo giới hạn index key, chi phí rebuild hoặc hạn chế DDL. Không coi index là thành phần “tự sửa vô điều kiện”.

### 9.3. View, trigger và PL/SQL có thể tham chiếu tên cũ

~~~sql
SELECT name, type, referenced_name, referenced_type
FROM user_dependencies
WHERE referenced_name = 'ALTER_TABLE_LAB'
ORDER BY type, name;
~~~

Đây là một cách phát hiện **một số dependency được Oracle ghi nhận**; nó không tìm được mọi tham chiếu SQL trong Java, job, báo cáo, SQL động hoặc hệ thống ETL bên ngoài. Một số tham chiếu còn phụ thuộc schema hiện hành và privilege. Cần tra cứu mã ứng dụng/migration ngoài database theo quy trình triển khai.

Sau khi thay đổi cấu trúc, có thể quan sát những object invalid:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status <> 'VALID'
ORDER BY object_type, object_name;
~~~

Việc object ở trạng thái `INVALID` cần được điều tra; không tự động xác định mọi invalid object đều do thay đổi bảng vừa làm. Quy trình triển khai thực tế có thể cần biên dịch lại các đối tượng bị ảnh hưởng và chạy kiểm thử ứng dụng.

### 9.4. Column default và CHECK không chữa được dữ liệu sai

Ví dụ muốn tổng tiền luôn không âm:

~~~sql
ALTER TABLE alter_table_lab
ADD CONSTRAINT ck_alter_lab_amount
CHECK (amount >= 0);
~~~

Lệnh này chỉ hợp lý **sau khi cột `AMOUNT` đã tồn tại** ở giai đoạn cutover. `CHECK` đảm bảo các giá trị tương lai và hàng hiện có tuân thủ điều kiện khi constraint được xác nhận; nó **không tự sửa giá trị âm**. Tương tự, `DEFAULT 0` không phải cách xử lý những giá trị `unknown` cũ.

Với dữ liệu quan trọng, cần xác định rõ các trường hợp: NULL hợp lệ không? Số âm có ý nghĩa hoàn tiền không? Currency/scale có thống nhất chưa? Constraint phải mô tả đúng nghiệp vụ.

## 10. Thao tác DDL khi bảng lớn hoặc đang được truy cập

Một script chạy nhanh trên vài dòng không phản ánh chi phí với hàng triệu bản ghi. Phân biệt các nhóm công việc:

| Công việc | Tác động thường gặp | Lưu ý triển khai |
| --- | --- | --- |
| Thêm cột nullable | Có thể chủ yếu là metadata trong nhiều trường hợp | Vẫn cần DDL lock và rà soát code |
| Thêm cột có default | Có thể có metadata optimization tùy phiên bản/điều kiện | Không mặc định mọi biến thể đều không tốn I/O |
| Tăng `VARCHAR2` length | Thường đơn giản hơn việc đổi datatype | Kiểm tra index, dependency, lock và phiên bản |
| Đổi tên cột | Metadata change nhưng phá tên cũ | Đảm bảo phiên bản ứng dụng tương thích |
| Backfill hàng triệu dòng | Nhiều DML, redo/undo, locks, archive, I/O | Chia batch có kiểm soát, ghi nhận tiến độ và đối chiếu |
| `DROP COLUMN` | Có thể tốn tài nguyên xử lý dữ liệu vật lý | Lên lịch, bảo vệ backup và quy trình recovery |
| `SET UNUSED` | Tách phần bỏ logic khỏi dọn dữ liệu | Tên cột cũ mất hiệu lực ngay; drop unused sau vẫn tốn tài nguyên |

### 10.1. Mẫu triển khai expand/contract

Với ứng dụng không thể dừng lâu, chiến lược phổ biến là:

1. **Expand:** thêm cột đích, để cột nguồn hoạt động.
2. **Đồng bộ:** triển khai app/trigger/dual-write có kiểm soát để đảm bảo dữ liệu cũ và mới không lệch trong thời gian chuyển tiếp.
3. **Backfill:** chuyển dữ liệu lịch sử theo batch, xử lý lỗi và giám sát tài nguyên.
4. **Verify:** kiểm tra theo khóa chính, số lượng, hàng NULL và các bất biến nghiệp vụ.
5. **Cutover:** chuyển đọc/ghi sang cột mới tại thời điểm an toàn, kiểm thử các đường đi của ứng dụng.
6. **Contract:** xóa dữ liệu/cột cũ khi đã có kế hoạch phục hồi và hết nhu cầu tương thích.

Không có một công thức online duy nhất cho mọi database. Oracle cung cấp các khả năng như **online table redefinition (`DBMS_REDEFINITION`)** cho những trường hợp phù hợp, nhưng cần đánh giá điều kiện, khóa, dependent objects, privileges, thời gian và phiên bản trước khi sử dụng. Đây là quy trình quản trị riêng, không chỉ thay một dòng `MODIFY`.

### 10.2. Backfill theo batch và tránh mất dữ liệu đồng thời

Nếu bảng lớn, một lệnh:

~~~sql
UPDATE huge_table
SET new_col = expensive_conversion(old_col);
~~~

có thể tạo undo/redo lớn, giữ row locks lâu và ảnh hưởng hệ thống. DBA cùng nhóm ứng dụng có thể chia batch theo khóa chính, giới hạn số hàng mỗi batch, commit theo kế hoạch và lưu tiến độ. Tuy vậy, **commit theo batch không tự giải quyết race condition** khi ứng dụng còn update cột nguồn cùng lúc. Cần thiết kế cách các giá trị mới được đồng bộ và xử lý retry/idempotency.

Với bài lab nhỏ, một `UPDATE` có điều kiện rồi `COMMIT` là đủ để hiểu nguyên lý. Trên production, việc chạy batch cần theo lịch, mức tải và kiểm thử.

### 10.3. DDL lock và thời gian chờ

Nếu `ALTER TABLE` chờ một giao dịch lâu hoặc báo `ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired`, không nên lập tức giết session người dùng. DBA cần kiểm tra blockers, giao dịch đang chạy, cửa sổ maintenance và khả năng đặt `DDL_LOCK_TIMEOUT` trong phạm vi được phép.

Trong lab có thể xem tham số:

~~~sql
SHOW PARAMETER ddl_lock_timeout;
~~~

Tham số này chi phối thời gian đợi khóa DDL trong các trường hợp tương ứng; tăng timeout không làm mất tác động khóa và không bảo đảm thao tác trở thành online. Với production cần có kế hoạch dừng hoặc tương thích phù hợp.

### 10.4. Backup, rollback chiến lược và khả năng phục hồi

Do Oracle DDL implicit commit, chiến lược “nếu lỗi thì `ROLLBACK` tất cả” **không đúng**. Thay vào đó:

- Chuẩn bị script forward và kế hoạch **compensating migration** có thể chạy an toàn khi cần.
- Sao lưu dữ liệu/metadata liên quan và xác minh phương án restore/recover tương ứng với RPO/RTO.
- Giữ cột nguồn trong giai đoạn chuyển tiếp đủ lâu để đối chiếu và phục hồi dữ liệu khi cần.
- Không xóa cột cũ trước khi chắc chắn ứng dụng và downstream đã bỏ phụ thuộc.
- Thử thay đổi trong môi trường staging có schema và dữ liệu đại diện, gồm constraint, index, trigger và tải thực tế.

Nếu cột đã bị `DROP` hoặc `SET UNUSED`, không mặc định có cách rollback tức thời giữ toàn bộ giá trị cũ. Khôi phục có thể phải dùng backup, flashback hoặc phương thức DBA phù hợp tùy trạng thái và tính năng đang có.

## 11. Các mã lỗi Oracle thường gặp

| Lỗi | Tình huống điển hình | Hướng chẩn đoán |
| --- | --- | --- |
| `ORA-01430` | Cố `ADD` cột đã tồn tại | Xem `USER_TAB_COLUMNS`, tên/case của cột và script migration đã chạy chưa |
| `ORA-00904` | SQL dùng tên cột đã đổi/xóa hoặc sai tên | Kiểm tra tên metadata, quoted identifiers và ứng dụng đang dùng SQL cũ |
| `ORA-01758` | Thêm cột mandatory không default vào bảng không rỗng | Thêm nullable → backfill → `NOT NULL` hoặc dùng default phù hợp |
| `ORA-02296` | Bật `NOT NULL` khi dữ liệu còn NULL | Tìm NULL và quyết định xử lý theo nghiệp vụ |
| `ORA-01441` | Giảm độ dài cột nhưng có giá trị quá lớn | Đo độ dài dữ liệu trước; không cắt dữ liệu tùy tiện |
| `ORA-01440` | Thu hẹp precision/scale số khi dữ liệu/trạng thái cột không cho phép | Xem kiểu số, dữ liệu, constraint; dùng cột mới khi cần |
| `ORA-01439` | Đổi datatype khi cột chưa đủ điều kiện (thường còn dữ liệu) | Dùng chiến lược cột mới + chuyển đổi + cutover |
| `ORA-01722` | Chuyển chuỗi không phải số hợp lệ | Chẩn đoán format, NLS, dữ liệu lỗi; dùng `TO_NUMBER` explicit và validation |
| `ORA-01861` | Chuỗi ngày không khớp format | Dùng `TO_DATE`/`TO_TIMESTAMP` với format mask tường minh |
| `ORA-01843` | Giá trị tháng/định dạng ngày không hợp lệ | Kiểm tra dữ liệu thực và NLS date language |
| `ORA-12899` | Giá trị vượt byte/character length của cột đích | Đo `LENGTH`/`LENGTHB`, xem `CHAR_USED` và định nghĩa cột |
| `ORA-02449` | Thử drop đối tượng key được tham chiếu mà chưa xử lý khóa ngoại | Xem quan hệ PK/UK/FK trước DDL; không cascade mù quáng |
| `ORA-00054` | Không lấy được DDL lock trong điều kiện timeout | Xem blocking sessions, kế hoạch thực thi và cửa sổ maintenance |

Thông báo lỗi có thể thay đổi chi tiết theo phiên bản và câu lệnh. **Một mã lỗi không thay thế phân tích dữ liệu**, đặc biệt khi làm migration phức tạp.

### 11.1. Truy vấn nhanh khi thay đổi thất bại

~~~sql
-- Cau truc cot:
SELECT column_name, data_type, data_length,
       char_length, char_used, nullable
FROM user_tab_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY column_id;

-- Rang buoc:
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'ALTER_TABLE_LAB';

-- Index:
SELECT index_name, column_name, column_position
FROM user_ind_columns
WHERE table_name = 'ALTER_TABLE_LAB'
ORDER BY index_name, column_position;

-- Cot UNUSED:
SELECT table_name, count
FROM user_unused_col_tabs
WHERE table_name = 'ALTER_TABLE_LAB';
~~~

Nếu bảng thuộc schema khác, hãy sử dụng các view `ALL_*` hoặc `DBA_*` có quyền thích hợp, kèm owner/schema; `USER_*` chỉ quan sát phạm vi chủ sở hữu tương ứng.

## 12. Một chuỗi bài thực hành liền mạch

Để tránh chạy nhầm các **biến thể thay thế** trong tài liệu, bạn có thể thực hiện chuỗi sau trên bảng `ALTER_TABLE_LAB` đã tạo ở Mục 2:

### Giai đoạn A — Bổ sung thuộc tính

~~~sql
ALTER TABLE alter_table_lab
ADD (email VARCHAR2(200 CHAR));

ALTER TABLE alter_table_lab
ADD (order_status VARCHAR2(12 CHAR) DEFAULT 'NEW' NOT NULL);

ALTER TABLE alter_table_lab
MODIFY (customer_name VARCHAR2(160 CHAR));
~~~

Sau đó kiểm tra `USER_TAB_COLUMNS` và `SELECT` dữ liệu. Những hàng cũ sẽ có biểu diễn logic trạng thái `NEW` theo default được khai báo khi thêm cột.

### Giai đoạn B — Đổi tên cột legacy

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN legacy_note TO legacy_comment;

SELECT order_id, legacy_comment
FROM alter_table_lab
ORDER BY order_id;
~~~

Trong bước này, không chạy `ALTER TABLE ... RENAME TO` vì nó đổi cả tên bảng và làm các lệnh sau không còn tìm được `ALTER_TABLE_LAB`.

### Giai đoạn C — Chuyển giá tiền có dữ liệu lỗi

~~~sql
ALTER TABLE alter_table_lab
ADD (amount_new NUMBER(12,2));

SELECT order_id, amount_text
FROM alter_table_lab
WHERE amount_text IS NOT NULL
  AND NOT REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

UPDATE alter_table_lab
SET amount_new = TO_NUMBER(
    TRIM(amount_text),
    '9999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
WHERE amount_text IS NOT NULL
  AND REGEXP_LIKE(
      TRIM(amount_text),
      '^[0-9]{1,10}[.][0-9]{2}$'
  );

COMMIT;
~~~

Kết quả: hàng số 3 chưa được chuyển do `unknown`. Nếu đã xác minh nguồn trên lab, làm theo Mục 7.5 để sửa, backfill lại và đối chiếu.

### Giai đoạn D — Cutover

Sau khi tất cả giá trị đã được xác nhận:

~~~sql
ALTER TABLE alter_table_lab
RENAME COLUMN amount_text TO amount_text_legacy;

ALTER TABLE alter_table_lab
RENAME COLUMN amount_new TO amount;

ALTER TABLE alter_table_lab
MODIFY (amount NOT NULL);

SELECT order_id, customer_name, amount, order_status
FROM alter_table_lab
ORDER BY order_id;
~~~

Không chạy giai đoạn D nếu `AMOUNT_NEW` còn NULL ở hàng mà sau này cột phải bắt buộc. Đó là một điều kiện nghiệp vụ, không phải lỗi “cần bỏ qua”.

### Giai đoạn E — Dọn cột không sử dụng

Chỉ khi bạn xác nhận đã hoàn tất bài và không cần giá trị legacy:

~~~sql
ALTER TABLE alter_table_lab
SET UNUSED (legacy_comment, amount_text_legacy);

SELECT table_name, count
FROM user_unused_col_tabs
WHERE table_name = 'ALTER_TABLE_LAB';

ALTER TABLE alter_table_lab
DROP UNUSED COLUMNS;
~~~

Nếu muốn dùng `DROP COLUMN` thay vì `SET UNUSED`, bạn có thể xóa cột không quan trọng như `EMAIL` trên **bảng lab**, sau khi bảo đảm không cần dữ liệu:

~~~sql
ALTER TABLE alter_table_lab
DROP COLUMN email;
~~~

### Giai đoạn F — Dọn bảng lab (tùy chọn)

~~~sql
-- Chi chay khi day la bang lab cua ban va khong can du lieu nua.
DROP TABLE alter_table_lab PURGE;
~~~

`PURGE` bỏ qua recycle bin cho thao tác drop bảng, nên không thể trông đợi Flashback Drop để lấy lại bảng vừa purge. Đừng chạy bước này nếu muốn giữ kết quả thực hành hoặc có bất kỳ dữ liệu nào ngoài phạm vi lab.

## 13. Câu hỏi tự kiểm tra

1. `ALTER TABLE ... ADD (new_col VARCHAR2(100))` trên bảng đã có 100.000 hàng sẽ khiến các hàng cũ có giá trị logic nào ở cột nullable mới nếu không khai báo default?
2. Tại sao thêm cột `NOT NULL` không có default vào bảng đã có dữ liệu có thể thất bại?
3. `DEFAULT 'NEW'` và `NOT NULL` có vai trò giống nhau không?
4. Thay đổi `MODIFY (order_status DEFAULT 'PENDING')` có tự đổi `NEW` thành `PENDING` ở các hàng cũ không?
5. Đổi tên cột `LEGACY_NOTE` thành `LEGACY_COMMENT` có tự sửa mọi SQL của ứng dụng không?
6. Vì sao không thể trông chờ `ROLLBACK` sau `ALTER TABLE ... DROP COLUMN` để lấy lại dữ liệu?
7. Phân biệt `DROP COLUMN` và `SET UNUSED` về thời điểm loại cột khỏi SQL và thời điểm thu hồi lưu trữ.
8. Tại sao `ALTER TABLE t MODIFY (amount_text NUMBER(12,2))` không phải phương án an toàn khi `AMOUNT_TEXT` đã chứa `unknown`?
9. Trong migration từ `VARCHAR2` sang `NUMBER`, vì sao cần thống nhất dấu thập phân và NLS trước `TO_NUMBER`?
10. Khi nguồn có hàng `NULL`, vì sao điều kiện `amount_text IS NOT NULL AND amount_new IS NULL` chưa đủ để quyết định có thể áp `NOT NULL` trên cột mới?
11. Tại sao đổi kiểu số điện thoại từ `VARCHAR2` sang `NUMBER` có thể làm mất ý nghĩa dữ liệu?
12. Nếu script `ALTER TABLE` chạy chậm trên bảng lớn, hai loại tác động cần điều tra về lock và I/O là gì?
13. Vì sao một ứng dụng tiếp tục insert vào cột nguồn trong khi backfill có thể làm cột mới thiếu dữ liệu?
14. Bên cạnh `USER_TAB_COLUMNS`, bạn có thể dùng những view nào để phát hiện constraint, index và database dependencies?
15. Trước khi dọn `DROP UNUSED COLUMNS` trên production, tại sao phải có backup và kế hoạch phục hồi dù cột đã không còn xuất hiện trong SQL?

**Gợi ý trả lời:**

1. `NULL`.
2. Các hàng cũ không có giá trị để thỏa `NOT NULL`; cần default hoặc backfill trước.
3. Không. Default là giá trị cấp khi insert theo semantics đã khai báo; `NOT NULL` cấm NULL.
4. Không, muốn sửa dữ liệu đã có cần DML tường minh.
5. Không; tên cũ có thể còn trong Java, view, PL/SQL, job và báo cáo.
6. DDL implicit commit; drop là thay đổi cấu trúc có thể mất dữ liệu.
7. Cả hai làm mất khả năng truy cập cột qua SQL, nhưng `SET UNUSED` có thể hoãn dọn vật lý đến `DROP UNUSED`.
8. Oracle có ràng buộc đổi datatype trên cột chứa dữ liệu, và chuỗi không hợp lệ không thể chuyển thành số đúng.
9. Cùng một văn bản như `1,234` có thể có nghĩa khác nhau theo locale; phải định nghĩa format nguồn rõ ràng.
10. Nó bỏ qua hàng nguồn NULL; nếu đích bắt buộc, phải kiểm tra **mọi** NULL ở đích.
11. Số 0 đầu và các ký tự định danh như `+` không phải phép toán số học.
12. DDL lock/blocking và công việc đọc/ghi redo/undo/datafile có thể gây tác động.
13. Có race condition giữa backfill và DML mới; cần đồng bộ hoặc kiểm soát cửa sổ cutover.
14. `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `USER_IND_COLUMNS`, `USER_DEPENDENCIES`, `USER_OBJECTS`.
15. Cột unused không phải bản backup; dọn vật lý có thể không phục hồi được bằng rollback và có thể tốn tài nguyên.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): cú pháp thêm, sửa, đổi tên, xóa cột, unused columns và các ràng buộc.
- [Oracle Database SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Types.html): `VARCHAR2`, `NUMBER`, `DATE`, độ dài BYTE/CHAR và giới hạn datatype.
- [Oracle Database SQL Language Reference — TO_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_NUMBER.html): chuyển chuỗi sang số bằng format model và NLS numeric settings.
- [Oracle Database SQL Language Reference — VALIDATE_CONVERSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html): đánh giá khả năng chuyển đổi dữ liệu trước migration.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản trị bảng, storage, schema changes và các vấn đề vận hành.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): tra `USER_TAB_COLUMNS`, `USER_CONSTRAINTS`, `USER_IND_COLUMNS`, `USER_UNUSED_COL_TABS` và các view phụ thuộc.
