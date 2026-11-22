# External table để đọc file và xử lý dữ liệu theo SQL

Oracle External Table cho phép database truy vấn dữ liệu đang nằm trong file bên ngoài database bằng câu lệnh SQL thông thường. Thay vì phải nạp file vào một bảng vật lý trước rồi mới lọc, nối hoặc tổng hợp, ta định nghĩa metadata mô tả cấu trúc file và cách Oracle đọc file. Sau đó có thể dùng `SELECT`, `JOIN`, `WHERE`, `GROUP BY`, view và các phép biến đổi SQL trên dữ liệu đó.

External table đặc biệt hữu ích cho quy trình nhập dữ liệu, đối soát file, xử lý dữ liệu trao đổi với hệ thống khác và đọc các tập dữ liệu lớn theo batch. Nó tạo ra một lớp truy cập SQL trên file, giúp tận dụng bộ tối ưu truy vấn, kiểu dữ liệu, hàm SQL và các công cụ kiểm tra dữ liệu của Oracle.

Điểm cần nhớ là **dữ liệu của external table vẫn nằm trong file ở hệ điều hành hoặc storage bên ngoài**. Database lưu định nghĩa bảng và metadata, còn mỗi lần truy vấn Oracle đọc dữ liệu từ file theo access driver được khai báo. External table thông thường là read-only đối với SQL; nếu cần lưu dữ liệu đã làm sạch hoặc phục vụ truy vấn lặp lại, thường sẽ nạp kết quả vào bảng staging hoặc bảng nghiệp vụ.

## 1. External table là gì?

Một external table là một database object có cấu trúc cột như bảng thông thường nhưng dữ liệu được lấy từ nguồn bên ngoài. Định nghĩa external table chỉ ra:

- File hoặc các file cần đọc.
- Directory object đại diện cho thư mục trên máy chủ database.
- Access driver dùng để diễn giải dữ liệu.
- Định dạng bản ghi và trường dữ liệu.
- Cách ánh xạ dữ liệu file vào các cột SQL.
- Chính sách xử lý bản ghi lỗi và giới hạn lỗi cho phép.

Ví dụ, một hệ thống nhận file `orders.csv` từ ứng dụng bán hàng. Ta tạo external table `EXT_ORDERS` mô tả các trường trong file. Sau đó có thể truy vấn:

```sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID';
```

Oracle đọc file theo định nghĩa external table khi thực hiện câu SQL. Không có thao tác tự động sao chép toàn bộ file vào một table segment chỉ vì external table đã được tạo.

### 1.1. External table khác bảng thông thường như thế nào?

| Đặc điểm | Bảng thông thường | External table |
|---|---|---|
| Nơi lưu dữ liệu | Datafile do Oracle quản lý | File bên ngoài database |
| Dữ liệu được lưu trong table segment | Có | Không theo mô hình external table thông thường |
| Tạo bằng `CREATE TABLE` | Có | Có, kèm `ORGANIZATION EXTERNAL` |
| Truy vấn bằng SQL | Có | Có |
| DML `INSERT`, `UPDATE`, `DELETE` trực tiếp | Có, nếu có quyền | Không hỗ trợ như bảng thường với `ORACLE_LOADER` |
| Index database trên dữ liệu | Có thể tạo | Không tạo index như bảng vật lý thông thường |
| Constraint lưu trữ và thực thi như bảng thường | Có | Không nên dựa vào external table để thay thế constraint của bảng đích |
| Dữ liệu thay đổi | Qua transaction/database | Thay đổi khi file nguồn được thay hoặc nội dung file đổi |
| Transaction rollback | Có với DML transactional | Không thể rollback thay đổi file nguồn bằng `ROLLBACK` SQL |

External table phù hợp làm nguồn đọc và lớp tích hợp. Bảng vật lý phù hợp lưu dữ liệu đã kiểm tra, lập chỉ mục, áp constraint và phục vụ truy vấn nghiệp vụ thường xuyên.

### 1.2. Các thành phần trong kiến trúc

```text
             File trên máy chủ / shared storage
                         |
                         v
                  DIRECTORY object
                         |
                         v
                External table metadata
                  +--------------+
                  | Cột SQL      |
                  | Access driver|
                  | File location|
                  | Access params|
                  +--------------+
                         |
                         v
                    SQL statement
             SELECT / JOIN / GROUP BY / VIEW
                         |
                         v
                 Kết quả cho ứng dụng
```

Directory object là tên logic trong database trỏ tới một đường dẫn trên máy chủ. Access driver chịu trách nhiệm đọc và diễn giải file. Optimizer lập kế hoạch SQL trên external table giống như với các row source khác, trong phạm vi thông tin và khả năng mà driver cung cấp.

## 2. Access driver và các loại external table

Access driver xác định cách Oracle trao đổi dữ liệu với file hoặc nguồn bên ngoài. Các driver thường gặp gồm:

| Driver | Mục đích chính |
|---|---|
| `ORACLE_LOADER` | Đọc dữ liệu dạng văn bản như CSV, delimiter-separated, fixed-width hoặc record format được hỗ trợ |
| `ORACLE_DATAPUMP` | Đọc và ghi định dạng file nhị phân riêng của Oracle Data Pump external table |
| `ORACLE_HDFS`, `ORACLE_HIVE` và các driver liên quan | Truy cập nguồn big data trong các cấu hình/phiên bản và sản phẩm hỗ trợ |

Với bài toán đọc file văn bản do ứng dụng hoặc hệ thống khác xuất ra, `ORACLE_LOADER` là lựa chọn phổ biến. Tên driver có chữ `LOADER` nhưng khi dùng external table, ta đang truy vấn dữ liệu qua SQL; không cần chạy SQL*Loader command line cho mỗi lần đọc.

`ORACLE_DATAPUMP` dùng định dạng binary riêng, thường hữu ích khi cần unload dữ liệu từ database ra file hoặc đọc lại dữ liệu đã unload. File của driver này không phải CSV và không nên chỉnh sửa bằng text editor. Các driver big data phụ thuộc phiên bản Oracle, cấu hình và sản phẩm được triển khai.

## 3. Chuẩn bị file và DIRECTORY object

### 3.1. File phải nằm trên máy chủ database

File của external table được database server đọc. Đường dẫn file là đường dẫn mà tiến trình Oracle Database trên máy chủ nhìn thấy, không phải đường dẫn trên máy tính chạy SQL Developer, SQLcl hoặc ứng dụng client.

Ví dụ file được đặt tại:

```text
/u01/app/oracle/extdata/orders.csv
```

Thư mục này phải tồn tại trên máy chủ database và OS account chạy Oracle phải có quyền đọc file. Nếu driver cần tạo log, bad file hoặc discard file, OS account cũng cần quyền ghi phù hợp.

Trong RAC, file cần có sẵn tại đường dẫn tương ứng trên mọi node có thể chạy truy vấn external table. Thông thường nên đặt file trên shared filesystem hoặc storage được mount nhất quán. Nếu file chỉ có trên một node nhưng truy vấn có thể chạy ở node khác, việc đọc file có thể thất bại tùy instance thực thi.

### 3.2. Tạo DIRECTORY object

DBA hoặc user có quyền tạo directory object có thể khai báo đường dẫn:

```sql
CREATE OR REPLACE DIRECTORY ext_data_dir
AS '/u01/app/oracle/extdata';
```

`EXT_DATA_DIR` là tên object trong database. Chuỗi đường dẫn là đường dẫn trên server. Việc tạo directory object không tự tạo thư mục vật lý và cũng không tự cấp quyền đọc/ghi trên hệ điều hành.

### 3.3. Cấp quyền trên DIRECTORY

User tạo và truy vấn external table cần quyền thích hợp trên directory object. Với external table đọc file, cấp `READ`:

```sql
GRANT READ ON DIRECTORY ext_data_dir TO app_loader;
```

Nếu Oracle Loader cần tạo log, bad file hoặc discard file trong directory, cấp thêm `WRITE`:

```sql
GRANT WRITE ON DIRECTORY ext_data_dir TO app_loader;
```

Quyền database trên DIRECTORY và quyền OS là hai lớp riêng. Có `READ ON DIRECTORY` nhưng OS account không đọc được file thì truy vấn vẫn lỗi. Ngược lại, OS account đọc được file nhưng user database không có quyền `READ` trên directory object cũng không đủ.

Không nên cấp `READ`/`WRITE` trên directory chứa file nhạy cảm cho `PUBLIC`. Nên dùng một thư mục riêng cho dữ liệu external table và cấp quyền cho đúng schema/service cần sử dụng.

### 3.4. Kiểm tra quyền và metadata directory

Một số view thường dùng:

```sql
SELECT directory_name,
       directory_path
FROM all_directories
ORDER BY directory_name;
```

```sql
SELECT grantee,
       table_name AS directory_name,
       privilege,
       grantable
FROM all_tab_privs
WHERE type = 'DIRECTORY'
ORDER BY table_name, grantee, privilege;
```

Phạm vi thông tin phụ thuộc quyền của user. DBA có thể dùng các view `DBA_DIRECTORIES` và `DBA_TAB_PRIVS` để xem toàn database.

## 4. Tạo external table đầu tiên bằng ORACLE_LOADER

Giả sử file `orders.csv` chứa dữ liệu:

```csv
1001,501,2026-10-01,1250.50,PAID
1002,502,2026-10-02,800.00,NEW
1003,501,2026-10-03,420.75,PAID
```

Mỗi dòng có năm trường theo thứ tự:

1. `ORDER_ID`
2. `CUSTOMER_ID`
3. `ORDER_DATE`
4. `TOTAL_AMOUNT`
5. `ORDER_STATUS`

Tạo external table:

```sql
CREATE TABLE ext_orders (
    order_id       NUMBER,
    customer_id    NUMBER,
    order_date     DATE,
    total_amount   NUMBER(12,2),
    order_status   VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY ext_data_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        BADFILE 'orders.bad'
        LOGFILE 'orders.log'
        FIELDS TERMINATED BY ','
        MISSING FIELD VALUES ARE NULL
        (
            order_id       INTEGER EXTERNAL,
            customer_id    INTEGER EXTERNAL,
            order_date     CHAR(10) DATE_FORMAT DATE MASK "YYYY-MM-DD",
            total_amount   CHAR(20),
            order_status   CHAR(20)
        )
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT 100;
```

Các thành phần đáng chú ý:

- `ORGANIZATION EXTERNAL`: khai báo đây là external table.
- `TYPE ORACLE_LOADER`: dùng driver đọc dữ liệu văn bản.
- `DEFAULT DIRECTORY`: directory object mặc định cho file.
- `RECORDS DELIMITED BY NEWLINE`: mỗi record kết thúc bằng dấu xuống dòng.
- `FIELDS TERMINATED BY ','`: các trường được phân cách bằng dấu phẩy.
- `MISSING FIELD VALUES ARE NULL`: trường bị thiếu được diễn giải là `NULL` theo quy tắc loader.
- `BADFILE`, `LOGFILE`: nơi ghi record bị lỗi và thông tin quá trình đọc.
- `LOCATION`: tên file nguồn trong directory.
- `REJECT LIMIT`: số record lỗi tối đa được chấp nhận trong một lần truy cập trước khi statement bị lỗi.

Ví dụ trên giả định định dạng số và ngày phù hợp với cấu hình đã khai báo. Với dữ liệu trao đổi từ nhiều hệ thống, nên cân nhắc đọc các trường ban đầu dưới dạng ký tự rồi chuyển đổi bằng SQL sau khi kiểm tra.

### 4.1. Truy vấn external table

Sau khi tạo table và file có sẵn, truy vấn giống bảng thông thường:

```sql
SELECT order_id,
       customer_id,
       order_date,
       total_amount,
       order_status
FROM ext_orders;
```

Lọc dữ liệu:

```sql
SELECT order_id,
       order_date,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID'
  AND order_date >= DATE '2026-10-01'
  AND order_date <  DATE '2026-11-01';
```

Kết hợp với bảng trong database:

```sql
SELECT e.order_id,
       c.customer_name,
       e.total_amount
FROM ext_orders e
JOIN app.customers c
  ON c.customer_id = e.customer_id
WHERE e.order_status = 'PAID';
```

Có thể dùng external table trong view, CTE, subquery, aggregate và các biểu thức SQL thông thường. Các phép biến đổi được thực hiện theo execution plan mà optimizer chọn.

## 5. Định dạng record và field trong ORACLE_LOADER

`ACCESS PARAMETERS` mô tả cấu trúc vật lý của file. Định nghĩa này phải khớp với cách hệ thống tạo file. Nếu delimiter, record terminator, quote hoặc kiểu dữ liệu không khớp, dữ liệu có thể bị lệch cột hoặc bị reject.

### 5.1. Record kết thúc bằng newline

Định dạng phổ biến nhất là mỗi dòng file chứa một record:

```sql
RECORDS DELIMITED BY NEWLINE
```

Trên các hệ điều hành khác nhau, newline có thể có dạng LF hoặc CRLF. Oracle Loader hỗ trợ record delimiter theo quy tắc của driver; nếu file đến từ hệ thống khác, cần kiểm tra line ending khi có lỗi đọc dòng cuối hoặc ký tự carriage return bị giữ lại.

### 5.2. Field phân cách bằng delimiter

Ví dụ file phân cách bằng dấu `|`:

```text
1001|501|2026-10-01|1250.50|PAID
1002|502|2026-10-02|800.00|NEW
```

Access parameters:

```sql
FIELDS TERMINATED BY '|'
(
    order_id       INTEGER EXTERNAL,
    customer_id    INTEGER EXTERNAL,
    order_date     CHAR(10) DATE_FORMAT DATE MASK "YYYY-MM-DD",
    total_amount   CHAR(20),
    order_status   CHAR(20)
)
```

Các cột được ánh xạ theo thứ tự field trong file. Không nên giả định thứ tự cột trong câu `SELECT` ảnh hưởng đến cách Oracle đọc field; mapping vật lý được mô tả trong danh sách field của access parameters.

### 5.3. Field được bao bởi dấu nháy kép

CSV thường cho phép một field chứa delimiter nếu được đặt trong dấu nháy kép:

```csv
1001,501,"01, Main Street",PAID
1002,502,"Warehouse A",NEW
```

Có thể khai báo:

```sql
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
(
    order_id      INTEGER EXTERNAL,
    customer_id   INTEGER EXTERNAL,
    address       CHAR(200),
    order_status  CHAR(20)
)
```

`OPTIONALLY ENCLOSED BY` cho phép field được bao bởi ký tự enclosure. Quy tắc escape dấu nháy nằm bên trong field cần thống nhất với bên tạo file và kiểm tra theo khả năng của Oracle Loader; không nên giả định mọi biến thể CSV của mọi ứng dụng đều tương thích hoàn toàn.

### 5.4. File fixed-width

Không phải file nào cũng dùng delimiter. Một số hệ thống xuất record có độ dài cố định:

```text
00001001JOHN      0001250.50
00001002MARIA     0000800.00
```

Với fixed-width file, khai báo vị trí và độ dài field bằng cú pháp field position được Oracle Loader hỗ trợ, thay vì dùng `FIELDS TERMINATED BY`. Ví dụ khái niệm:

```sql
ACCESS PARAMETERS (
    RECORDS FIXED 32
    FIELDS (
        order_id      POSITION(1:8)  CHAR(8),
        customer_name POSITION(9:18) CHAR(10),
        amount_text   POSITION(19:28) CHAR(10)
    )
)
```

Độ dài record và vị trí phải khớp chính xác với định dạng file thực tế. Cần tính theo byte hay ký tự theo quy tắc encoding của file và driver; với ký tự đa byte, không nên tự suy luận vị trí chỉ từ số ký tự hiển thị.

### 5.5. Bỏ qua header

Nếu file có dòng tiêu đề:

```csv
ORDER_ID,CUSTOMER_ID,ORDER_DATE,TOTAL_AMOUNT,ORDER_STATUS
1001,501,2026-10-01,1250.50,PAID
```

có thể cấu hình bỏ qua record đầu tiên:

```sql
ACCESS PARAMETERS (
    RECORDS DELIMITED BY NEWLINE
    SKIP 1
    FIELDS TERMINATED BY ','
    (
        order_id      INTEGER EXTERNAL,
        customer_id   INTEGER EXTERNAL,
        order_date    CHAR(10),
        total_amount  CHAR(20),
        order_status  CHAR(20)
    )
)
```

Chỉ dùng `SKIP 1` nếu mọi file đều có đúng một header record. Nếu file không có header hoặc số dòng đầu thay đổi, cấu hình này sẽ bỏ nhầm dữ liệu.

### 5.6. Giá trị thiếu, khoảng trắng và NULL

File văn bản có thể biểu diễn giá trị rỗng theo nhiều cách: field không có ký tự, chỉ có khoảng trắng, hai dấu phân cách liên tiếp hoặc một token như `NULL`/`N/A`. Cần xác định quy tắc của nguồn dữ liệu.

`MISSING FIELD VALUES ARE NULL` giúp diễn giải field bị thiếu là `NULL`. Với token cụ thể, có thể dùng điều kiện `NULLIF` trong field specification theo cú pháp loader phù hợp. Ví dụ minh họa:

```sql
FIELDS TERMINATED BY ','
(
    order_id    CHAR(20),
    amount_txt  CHAR(20) NULLIF amount_txt = 'NULL',
    status_txt  CHAR(20)
)
```

Với dữ liệu có khoảng trắng đầu/cuối, có thể dùng trim directive phù hợp của Oracle Loader hoặc xử lý bằng `TRIM` trong SQL. Cần phân biệt chuỗi rỗng và `NULL`: trong Oracle SQL, chuỗi ký tự độ dài zero được xử lý như `NULL` đối với kiểu character thông thường.

## 6. Đọc raw text rồi chuyển đổi bằng SQL

Trong pipeline nhập dữ liệu, một cách thiết kế linh hoạt là định nghĩa external table với các cột văn bản. Sau đó dùng SQL để kiểm tra và chuyển đổi sang kiểu dữ liệu nghiệp vụ. Cách này giúp tách lỗi định dạng file khỏi lỗi quy tắc nghiệp vụ và cho phép báo cáo record không hợp lệ có chủ đích.

Ví dụ file:

```csv
1001,501,2026-10-01,1250.50,PAID
1002,502,not-a-date,800.00,NEW
1003,501,2026-10-03,invalid,PAID
```

Tạo external table raw:

```sql
CREATE TABLE ext_orders_raw (
    order_id_txt      VARCHAR2(30),
    customer_id_txt   VARCHAR2(30),
    order_date_txt    VARCHAR2(30),
    amount_txt        VARCHAR2(30),
    status_txt        VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY ext_data_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        BADFILE 'orders_raw.bad'
        LOGFILE 'orders_raw.log'
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            order_id_txt     CHAR(30),
            customer_id_txt  CHAR(30),
            order_date_txt   CHAR(30),
            amount_txt       CHAR(30),
            status_txt       CHAR(20)
        )
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
```

Sau đó chuẩn hóa khoảng trắng và chuyển đổi:

```sql
SELECT TO_NUMBER(TRIM(order_id_txt)) AS order_id,
       TO_NUMBER(TRIM(customer_id_txt)) AS customer_id,
       TO_DATE(TRIM(order_date_txt), 'YYYY-MM-DD') AS order_date,
       TO_NUMBER(TRIM(amount_txt), '999999999999D99',
                 'NLS_NUMERIC_CHARACTERS=''.,''') AS total_amount,
       UPPER(TRIM(status_txt)) AS order_status
FROM ext_orders_raw;
```

Truy vấn trên sẽ phát sinh lỗi nếu một giá trị không chuyển đổi được. Với pipeline cần tiếp tục xử lý các dòng hợp lệ và tách dòng lỗi, hãy kiểm tra định dạng trước khi gọi hàm chuyển đổi.

### 6.1. Kiểm tra conversion trước khi chuyển đổi

Trong các phiên bản Oracle hỗ trợ `VALIDATE_CONVERSION` (Oracle Database 12.2 trở lên), có thể kiểm tra dữ liệu:

```sql
SELECT order_id_txt,
       order_date_txt,
       amount_txt,
       CASE
           WHEN VALIDATE_CONVERSION(TRIM(order_id_txt) AS NUMBER) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(order_date_txt) AS DATE,
                    'YYYY-MM-DD'
                ) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(amount_txt) AS NUMBER,
                    '999999999999D99',
                    'NLS_NUMERIC_CHARACTERS=''.,'''
                ) = 1
           THEN 'VALID'
           ELSE 'INVALID'
       END AS validation_status
FROM ext_orders_raw;
```

`VALIDATE_CONVERSION` trả về 1 nếu biểu thức có thể chuyển đổi và 0 nếu không thể; xử lý `NULL` theo quy tắc của hàm. Cần bổ sung kiểm tra business rule như số tiền không âm, trạng thái thuộc danh sách cho phép và khóa ngoại tồn tại.

Với phiên bản hỗ trợ `DEFAULT ... ON CONVERSION ERROR`, có thể dùng để kiểm soát lỗi chuyển đổi trong một số biểu thức, nhưng không nên thay thế báo cáo dữ liệu lỗi bằng một giá trị mặc định khiến dữ liệu sai bị âm thầm chấp nhận.

### 6.2. Tách dòng hợp lệ và dòng lỗi

Có thể tạo view phân loại:

```sql
CREATE OR REPLACE VIEW v_orders_validated AS
SELECT order_id_txt,
       customer_id_txt,
       order_date_txt,
       amount_txt,
       status_txt,
       CASE
           WHEN VALIDATE_CONVERSION(TRIM(order_id_txt) AS NUMBER) = 1
            AND VALIDATE_CONVERSION(TRIM(customer_id_txt) AS NUMBER) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(order_date_txt) AS DATE,
                    'YYYY-MM-DD'
                ) = 1
            AND VALIDATE_CONVERSION(
                    TRIM(amount_txt) AS NUMBER,
                    '999999999999D99',
                    'NLS_NUMERIC_CHARACTERS=''.,'''
                ) = 1
           THEN 'Y'
           ELSE 'N'
       END AS is_valid
FROM ext_orders_raw;
```

Đọc các dòng cần xử lý:

```sql
SELECT *
FROM v_orders_validated
WHERE is_valid = 'Y';
```

Đọc các dòng cần điều tra:

```sql
SELECT *
FROM v_orders_validated
WHERE is_valid = 'N';
```

Trong thực tế, nên ghi lại tên file, batch ID, số dòng, lý do lỗi và thời điểm nạp vào bảng reject riêng để có thể đối soát và xử lý lại. Không nên chỉ trả về nhãn `INVALID` nếu quy trình vận hành cần biết lỗi cụ thể ở cột nào.

## 7. Xử lý record lỗi: LOGFILE, BADFILE, DISCARDFILE và REJECT LIMIT

Oracle Loader có thể ghi các file hỗ trợ chẩn đoán khi đọc external table.

| Thành phần | Mục đích |
|---|---|
| Log file | Ghi thông tin về lần truy cập/đọc file và lỗi loader |
| Bad file | Ghi record bị từ chối do lỗi định dạng, chuyển đổi hoặc điều kiện loader |
| Discard file | Ghi record bị loại bởi điều kiện discard/WHEN được cấu hình nếu có |
| Reject limit | Số record lỗi tối đa cho phép trước khi câu truy vấn bị dừng |

Ví dụ khai báo:

```sql
ACCESS PARAMETERS (
    RECORDS DELIMITED BY NEWLINE
    BADFILE 'orders.bad'
    LOGFILE 'orders.log'
    DISCARDFILE 'orders.dsc'
    FIELDS TERMINATED BY ','
    (
        order_id_txt  CHAR(30),
        amount_txt    CHAR(30),
        status_txt    CHAR(20)
    )
)
```

Các file này được ghi ở directory được chỉ định theo quy tắc của external table/loader. User database cần quyền `WRITE` trên directory tương ứng và OS account chạy Oracle cần quyền ghi thư mục.

### 7.1. REJECT LIMIT

Ví dụ:

```sql
REJECT LIMIT 10;
```

Nếu số record bị reject vượt giới hạn, câu truy vấn có thể kết thúc với lỗi external table. Có thể dùng:

```sql
REJECT LIMIT UNLIMITED;
```

để cho phép truy vấn tiếp tục bất kể số record reject, theo semantics của driver. `UNLIMITED` không có nghĩa record lỗi trở thành hợp lệ; nó chỉ thay đổi ngưỡng dừng do reject. Quy trình vẫn phải theo dõi bad file và log để không bỏ qua dữ liệu bị loại.

Không nên mặc định dùng `UNLIMITED` cho mọi batch. Nếu file có lỗi định dạng hàng loạt, truy vấn có thể chạy hết nhưng tạo ra kết quả thiếu dữ liệu. Chọn reject limit theo SLA, chất lượng nguồn và khả năng kiểm soát số dòng lỗi.

### 7.2. Phân biệt lỗi loader và lỗi nghiệp vụ

Bad file thường phản ánh record không thể được loader ánh xạ theo access parameters. Nhưng các giá trị sai về nghiệp vụ như trạng thái `UNKNOWN`, mã khách hàng không tồn tại hoặc số tiền âm có thể vẫn được loader đọc thành công.

Vì vậy, cần hai lớp kiểm tra:

1. **File/format validation:** record có đúng cấu trúc, delimiter, encoding và kiểu dữ liệu mà loader có thể đọc không?
2. **Business validation:** giá trị có hợp lệ theo quy tắc nghiệp vụ và quan hệ dữ liệu không?

Một record có thể qua lớp thứ nhất nhưng thất bại ở lớp thứ hai. Những lỗi nghiệp vụ nên được ghi vào bảng reject hoặc báo cáo kiểm tra riêng.

## 8. Nhiều file trong LOCATION và quản lý batch

External table có thể đọc một hoặc nhiều file được khai báo trong `LOCATION`. Ví dụ:

```sql
LOCATION (
    'orders_20261001.csv',
    'orders_20261002.csv',
    'orders_20261003.csv'
)
```

Các file phải nằm trong directory được chỉ định và có định dạng phù hợp với cùng một định nghĩa external table. Nếu các file có schema hoặc delimiter khác nhau, nên tách external table hoặc chuẩn hóa file trước.

### 8.1. File name và quy ước batch

Một quy trình ổn định nên có quy ước tên file chứa loại dữ liệu, ngày/batch và trạng thái:

```text
orders_20261114_batch001.csv
orders_20261114_batch002.csv
```

Nên quản lý metadata batch trong bảng database, gồm tên file, kích thước, checksum, thời điểm nhận, số record kỳ vọng, trạng thái xử lý và số record đã nạp. External table chỉ mô tả cách đọc; nó không tự tạo cơ chế kiểm soát file đã được xử lý hay chống nạp trùng.

### 8.2. Tránh thay file trong khi truy vấn đang chạy

File nguồn cần ổn định trong suốt thời gian truy vấn. Nếu một tiến trình khác ghi đè hoặc thay file trong lúc Oracle đang đọc, kết quả có thể không nhất quán hoặc phát sinh lỗi I/O. Quy trình nên ghi file vào tên tạm, hoàn tất và đóng file, sau đó rename/atomic move sang tên chính thức mà external table sử dụng.

Không xóa hoặc di chuyển file nguồn ngay sau khi bắt đầu query nếu chưa chắc database đã đọc xong. Hãy để job orchestration quản lý vòng đời file và chỉ đánh dấu batch hoàn tất sau khi SQL đã thành công.

## 9. Kết hợp external table với SQL và bảng staging

External table thường là lớp đầu vào của một pipeline. Một luồng xử lý điển hình:

```text
File nhận từ hệ thống ngoài
          |
          v
   External table (raw)
          |
          v
   Kiểm tra format và dữ liệu
       /           \
      v             v
  Dòng hợp lệ    Dòng lỗi
      |             |
      v             v
  Staging table   Reject table
      |
      v
  Transform / JOIN / MERGE
      |
      v
  Bảng nghiệp vụ
```

### 9.1. Nạp dữ liệu hợp lệ vào staging

Ví dụ bảng staging:

```sql
CREATE TABLE stg_orders (
    batch_id       NUMBER NOT NULL,
    order_id       NUMBER NOT NULL,
    customer_id    NUMBER NOT NULL,
    order_date     DATE NOT NULL,
    total_amount   NUMBER(12,2) NOT NULL,
    order_status   VARCHAR2(20) NOT NULL,
    source_file    VARCHAR2(255),
    loaded_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

Nạp các dòng đã được xác nhận hợp lệ:

```sql
INSERT INTO stg_orders (
    batch_id,
    order_id,
    customer_id,
    order_date,
    total_amount,
    order_status,
    source_file
)
SELECT :batch_id,
       TO_NUMBER(TRIM(order_id_txt)),
       TO_NUMBER(TRIM(customer_id_txt)),
       TO_DATE(TRIM(order_date_txt), 'YYYY-MM-DD'),
       TO_NUMBER(TRIM(amount_txt), '999999999999D99',
                 'NLS_NUMERIC_CHARACTERS=''.,'''),
       UPPER(TRIM(status_txt)),
       :source_file
FROM v_orders_validated
WHERE is_valid = 'Y';
```

Sau khi nạp, có thể dùng constraint, index, thống kê và transaction của bảng staging để kiểm tra và xử lý dữ liệu. Tên file và batch ID giúp truy vết nguồn của từng dòng.

### 9.2. Dùng MERGE để đồng bộ vào bảng đích

Sau khi staging đã được xác thực, có thể dùng `MERGE`:

```sql
MERGE INTO app.orders t
USING (
    SELECT order_id,
           customer_id,
           order_date,
           total_amount,
           order_status
    FROM stg_orders
    WHERE batch_id = :batch_id
) s
ON (t.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET
        t.order_status = s.order_status,
        t.total_amount = s.total_amount
WHEN NOT MATCHED THEN
    INSERT (
        order_id,
        customer_id,
        order_date,
        total_amount,
        order_status
    )
    VALUES (
        s.order_id,
        s.customer_id,
        s.order_date,
        s.total_amount,
        s.order_status
    );
```

`MERGE` cho phép cập nhật dòng đã tồn tại và thêm dòng mới trong một câu lệnh. Quy tắc cập nhật cần được xác định rõ: ví dụ có cho phép file cũ ghi đè dữ liệu mới hơn hay không, và làm thế nào xử lý hai record cùng `ORDER_ID` trong một batch.

### 9.3. Transaction và khả năng chạy lại

Đọc external table không tạo transaction để khóa file như bảng database. Khi nạp staging, các DML vào staging và bảng đích tuân theo transaction SQL thông thường. Có thể `COMMIT` sau khi batch được xác nhận hoặc `ROLLBACK` nếu bước nạp database thất bại.

Tuy nhiên, `ROLLBACK` không hoàn tác file nguồn, không xóa bad file/log file và không đảo ngược thao tác của hệ thống bên ngoài. Quy trình cần có batch ID, trạng thái xử lý và cơ chế idempotency để tránh nạp trùng khi job được chạy lại.

Một thiết kế phổ biến là ghi nhận batch vào bảng control:

| Trường | Ý nghĩa |
|---|---|
| `BATCH_ID` | Khóa duy nhất của lần nhận file |
| `FILE_NAME` | Tên file nguồn |
| `FILE_CHECKSUM` | Mã kiểm tra nội dung file |
| `RECEIVED_AT` | Thời điểm nhận file |
| `STATUS` | RECEIVED, VALIDATING, LOADED, FAILED hoặc trạng thái tương đương |
| `ROW_COUNT` | Số record dự kiến/đã đọc/đã nạp |
| `ERROR_COUNT` | Số record lỗi hoặc bị reject |
| `COMPLETED_AT` | Thời điểm kết thúc |

## 10. Tối ưu hiệu năng khi đọc external table

External table không có buffer cache segment và index như bảng vật lý. Hiệu năng phụ thuộc file I/O, cách định dạng record, access driver, predicate, số cột được đọc, parallel execution và các phép xử lý phía trên.

### 10.1. Chỉ chọn cột cần thiết

Không nên truy vấn `SELECT *` nếu chỉ cần một vài cột. Projection rõ ràng giúp giảm dữ liệu chuyển qua các bước join, sort và aggregate, đồng thời tránh đọc/diễn giải các trường rộng không cần thiết khi driver có thể tối ưu việc đọc theo cột.

### 10.2. Đặt predicate rõ ràng

Lọc theo batch, ngày hoặc trạng thái càng gần nguồn càng tốt:

```sql
SELECT order_id,
       customer_id,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID'
  AND order_date >= :from_date
  AND order_date <  :to_date;
```

Optimizer có thể áp dụng predicate trong quá trình xử lý external row source nếu driver và định dạng cho phép. Tuy nhiên, với file văn bản tuần tự, lọc ít dòng không nhất thiết đồng nghĩa Oracle chỉ đọc một phần file; nhiều trường hợp vẫn phải scan file để tìm record thỏa điều kiện.

### 10.3. Parallel query

External table có thể được sử dụng trong parallel query khi cấu hình và driver hỗ trợ. Có thể khai báo thuộc tính parallel cho external table hoặc dùng parallel execution theo chính sách hệ thống:

```sql
ALTER TABLE ext_orders PARALLEL 4;
```

Parallel có thể giúp đọc và xử lý file lớn nhanh hơn nếu storage, CPU và định dạng cho phép chia công việc. Tuy nhiên, tăng degree không bảo đảm tăng tốc tuyến tính. Nó có thể làm tăng I/O đồng thời, CPU, số process và áp lực lên shared storage.

Khả năng chia file thành nhiều phần phụ thuộc record format, driver, vị trí file và phiên bản. Một số định dạng hoặc file nén không thể chia tùy ý tại mọi byte vì phải giữ ranh giới record. Hãy đo bằng dữ liệu đại diện và kiểm tra execution plan thực tế.

### 10.4. Dùng staging cho truy vấn lặp lại

Nếu cùng một file cần được join và aggregate nhiều lần, đọc external table lặp lại có thể gây I/O file lặp lại. Sau khi kiểm tra và chuẩn hóa, nạp dữ liệu vào staging table để có thể:

- Tạo index phù hợp.
- Thu thập optimizer statistics.
- Dùng partitioning nếu khối lượng lớn.
- Áp dụng constraint và kiểm soát transaction.
- Tái sử dụng dữ liệu mà không phải parse file ở mỗi truy vấn.

External table phù hợp cho bước đọc/ingest. Bảng staging phù hợp cho xử lý nội bộ nhiều bước và truy vấn lặp lại.

### 10.5. Execution plan và thống kê

Có thể xem plan:

```sql
EXPLAIN PLAN FOR
SELECT order_id,
       customer_id,
       total_amount
FROM ext_orders
WHERE order_status = 'PAID';
```

```sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Khi truy vấn thực tế đã chạy và cần runtime details, dùng `DBMS_XPLAN.DISPLAY_CURSOR` với runtime statistics phù hợp. So sánh số dòng ước lượng/thực tế, thời gian, I/O và operation external table. Optimizer có thể có ít thông tin phân bố hơn so với bảng vật lý; nếu external data có phân bố quan trọng cho join order, staging vào bảng có statistics có thể giúp plan ổn định hơn.

## 11. ORACLE_DATAPUMP external table

Ngoài text loader, Oracle hỗ trợ access driver `ORACLE_DATAPUMP` để đọc và ghi file theo định dạng Data Pump riêng. Nó hữu ích khi cần trao đổi tập dữ liệu giữa database hoặc unload dữ liệu ra file mà không tạo table segment trung gian theo cách thông thường.

Ví dụ khái niệm tạo external table bằng CTAS để unload dữ liệu:

```sql
CREATE TABLE orders_unload
ORGANIZATION EXTERNAL (
    TYPE ORACLE_DATAPUMP
    DEFAULT DIRECTORY ext_data_dir
    LOCATION ('orders_export_01.dmp')
)
AS
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM app.orders
WHERE order_date >= DATE '2026-10-01';
```

Trong trường hợp này Oracle ghi dữ liệu ra file theo định dạng của driver. File không phải dump file tổng quát có thể tùy ý thay bằng Data Pump `expdp`/`impdp`; nó là external table data file. External table `ORACLE_DATAPUMP` có thể được dùng để đọc file tương ứng theo định nghĩa tương thích.

Các thao tác và giới hạn cụ thể phụ thuộc phiên bản. Không nên trộn cú pháp `ORACLE_LOADER` như delimiter CSV với `ORACLE_DATAPUMP`, vì hai driver có định dạng và access parameter khác nhau.

## 12. Bảo mật khi dùng external table

External table mở đường truy cập từ database tới filesystem của máy chủ. Vì vậy, cần kiểm soát cả quyền database lẫn quyền OS.

### 12.1. Giới hạn directory

- Tạo directory object trỏ tới đúng thư mục cần dùng.
- Chỉ grant `READ` cho schema cần đọc file.
- Chỉ grant `WRITE` nếu thật sự cần tạo log/bad/discard file.
- Không dùng directory rộng như thư mục home hoặc thư mục chứa nhiều dữ liệu nhạy cảm.
- Không cấp `CREATE ANY DIRECTORY` cho tài khoản runtime.

### 12.2. Kiểm soát nguồn file

File cần đến từ nguồn tin cậy hoặc được xác thực trước khi xử lý. Nếu ứng dụng ngoài có thể ghi file, cần kiểm tra:

- Tên file và batch ID.
- Kích thước tối đa và số record dự kiến.
- Encoding, delimiter, header và schema version.
- Checksum hoặc chữ ký nếu quy trình yêu cầu.
- Nội dung bất thường, field quá dài và ký tự điều khiển.

Không ghép tên file do người dùng nhập trực tiếp vào DDL hoặc đường dẫn tùy ý. Directory object giới hạn đường dẫn logic nhưng vẫn cần kiểm soát quyền tạo/sửa directory và quyền filesystem.

### 12.3. Bảo vệ file log và bad file

Log/bad/discard file có thể chứa dữ liệu nhạy cảm hoặc giá trị đầu vào lỗi. Cần phân quyền, retention và cleanup phù hợp. Không để file lỗi tồn tại lâu trong thư mục mà nhiều user OS có thể đọc.

## 13. Quản lý thay đổi file và định nghĩa external table

External table lưu metadata trong database, còn file có thể thay đổi độc lập. Vì vậy, người vận hành cần quản lý phiên bản schema và vòng đời file.

### 13.1. Thay đổi cấu trúc file

Nếu hệ thống nguồn thêm cột, đổi thứ tự cột, đổi delimiter hoặc thay định dạng ngày, định nghĩa external table cũ có thể đọc sai hoặc reject dữ liệu. Nên có version cho file schema, ví dụ `ORDERS_V1`, `ORDERS_V2`, hoặc đưa version vào metadata batch.

Không nên âm thầm thay đổi thứ tự field trong CSV mà giữ nguyên external table definition. Cần phối hợp thay đổi giữa hệ thống tạo file và database consumer.

### 13.2. LOCATION và thay file

`LOCATION` chứa tên file hoặc danh sách file được external table đọc. Việc thay nội dung file dưới cùng tên có thể làm kết quả truy vấn thay đổi ngay lần đọc tiếp theo. External table không giữ snapshot dữ liệu như một bảng vật lý.

Để bảo đảm có thể chạy lại, nên lưu file gốc theo batch bất biến và ghi nhận checksum. Nếu cần xử lý lại, dùng đúng file và batch ID ban đầu thay vì một file đã bị ghi đè.

### 13.3. Xóa hoặc thay external table

Có thể xóa định nghĩa external table bằng `DROP TABLE`. Thao tác này xóa metadata object trong database; không nên giả định nó tự xóa file nguồn. Quản lý file vẫn thuộc quy trình filesystem hoặc job orchestration.

## 14. Data dictionary views cho external table

Oracle cung cấp các view metadata để xem external table và cấu hình:

| View | Nội dung |
|---|---|
| `USER_EXTERNAL_TABLES` | External table trong schema hiện tại |
| `ALL_EXTERNAL_TABLES` | External table mà user có thể xem metadata |
| `DBA_EXTERNAL_TABLES` | External table trong database |
| `USER_EXTERNAL_LOCATIONS` | File location của external table trong schema hiện tại |
| `ALL_EXTERNAL_LOCATIONS` | File location có thể xem |
| `DBA_EXTERNAL_LOCATIONS` | File location trong database |
| `USER_TAB_COLUMNS` / `ALL_TAB_COLUMNS` | Metadata cột của external table |
| `ALL_DIRECTORIES` / `DBA_DIRECTORIES` | Directory object và đường dẫn |

Ví dụ xem external table trong schema:

```sql
SELECT table_name,
       type_name,
       default_directory_name,
       reject_limit
FROM user_external_tables
ORDER BY table_name;
```

Xem file được khai báo:

```sql
SELECT table_name,
       location
FROM user_external_locations
ORDER BY table_name, location;
```

Tên cột có thể khác đôi chút theo phiên bản; kiểm tra mô tả data dictionary của môi trường thực tế nếu xây dựng script quản trị dùng lâu dài.

## 15. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `ORA-29913` khi truy cập external table | Lỗi trong external table access driver hoặc thao tác file | Xem lỗi đi kèm, log file, directory và OS permissions |
| `ORA-29400` | Lỗi data cartridge/driver được bọc bên ngoài | Đọc chi tiết lỗi kèm theo và log loader |
| `ORA-01031` | Thiếu quyền database trên directory hoặc quyền cần thiết khác | Kiểm tra `READ`/`WRITE` trên DIRECTORY và quyền tạo object |
| Không tìm thấy file | Sai `LOCATION`, directory path hoặc file không tồn tại trên database server | Kiểm tra `ALL_DIRECTORIES`, OS path và tên file chính xác |
| Không đọc được file dù đã grant READ | OS account Oracle không có quyền đọc hoặc mount không khả dụng | Kiểm tra permission, owner, mount và quyền trên từng thư mục cha |
| Nhiều dòng bị reject | Sai delimiter, quote, record terminator, encoding hoặc kiểu dữ liệu | Đọc log/bad file và đối chiếu access parameters với file mẫu |
| Ngày/số bị chuyển đổi sai | NLS không phù hợp hoặc format mask sai | Khai báo format rõ ràng, kiểm tra decimal/group separators |
| Ký tự tiếng Việt bị lỗi | Character set file không khớp | Xác định encoding và khai báo character set phù hợp |
| Truy vấn chậm | File lớn, I/O, format không chia được, conversion hoặc join tốn kém | Xem plan, số dòng, I/O, parallel và cân nhắc staging |
| Chạy được trên một RAC node nhưng lỗi node khác | File không có trên shared path hoặc quyền mount khác nhau | Kiểm tra khả năng truy cập file từ mọi node được phép chạy service |

Khi gặp lỗi, nên kiểm tra theo thứ tự:

1. External table metadata: đúng owner, table, driver và `LOCATION` chưa?
2. Directory object: tên và đường dẫn có đúng không?
3. Database privilege: user có `READ` và `WRITE` đúng nhu cầu không?
4. OS permission: Oracle process có đọc/ghi được thư mục và file không?
5. File format: delimiter, record terminator, quote, encoding, field length và date/number mask có khớp không?
6. Log/bad file: loader ghi nhận record lỗi cụ thể nào?
7. Runtime plan: có scan lặp, I/O nghẽn hoặc join/aggregate quá lớn không?

Không nên khắc phục lỗi bằng cách cấp quyền filesystem hoặc database quá rộng. Hãy xác định chính xác lớp đang từ chối truy cập.

## 16. Quy trình nhập file thực tế

Một quy trình nhập dữ liệu bằng external table có thể được tổ chức như sau:

1. **Nhận file:** đưa file vào thư mục nhận đã được phân quyền; chưa dùng tên file chính thức cho đến khi file ghi hoàn tất.
2. **Xác thực file:** kiểm tra kích thước, checksum, encoding, header, schema version và số record dự kiến.
3. **Công bố file:** rename/atomic move sang tên bất biến mà external table sử dụng.
4. **Tạo hoặc chọn batch metadata:** ghi `BATCH_ID`, tên file, checksum và trạng thái `RECEIVED`.
5. **Truy vấn external table:** kiểm tra số dòng, định dạng và dữ liệu mẫu.
6. **Validate:** kiểm tra conversion, mandatory fields, miền giá trị, duplicate và quan hệ tham chiếu.
7. **Tách lỗi:** ghi dòng không hợp lệ và lý do vào reject table; lưu bad/log file theo retention.
8. **Load staging:** nạp dòng hợp lệ vào bảng staging trong transaction có kiểm soát.
9. **Apply nghiệp vụ:** dùng `MERGE` hoặc DML phù hợp để cập nhật bảng đích.
10. **Đối soát:** so sánh số dòng nguồn, hợp lệ, lỗi, staging và kết quả cuối.
11. **Đánh dấu hoàn tất:** cập nhật batch status và thời gian xử lý.
12. **Lưu trữ/cleanup:** chuyển file nguồn sang archive theo chính sách; chỉ xóa khi retention và audit cho phép.

Quy trình này giúp external table trở thành một thành phần của data pipeline có thể kiểm soát, thay vì một câu `SELECT` phụ thuộc vào file thay đổi ngoài tầm theo dõi.

## 17. Bài thực hành hoàn chỉnh

### Bước 1: Tạo directory

DBA tạo directory trỏ đến thư mục server đã chuẩn bị:

```sql
CREATE OR REPLACE DIRECTORY inbound_orders
AS '/u01/app/oracle/inbound/orders';
```

### Bước 2: Cấp quyền

```sql
GRANT READ, WRITE ON DIRECTORY inbound_orders TO app_loader;
```

### Bước 3: Đặt file mẫu

File `orders_batch_001.csv`:

```csv
ORDER_ID,CUSTOMER_ID,ORDER_DATE,AMOUNT,STATUS
1001,501,2026-10-01,1250.50,PAID
1002,502,2026-10-02,800.00,NEW
1003,501,2026-10-03,420.75,PAID
```

### Bước 4: Tạo external table raw

```sql
CREATE TABLE ext_orders_batch (
    order_id_txt      VARCHAR2(30),
    customer_id_txt   VARCHAR2(30),
    order_date_txt    VARCHAR2(30),
    amount_txt        VARCHAR2(30),
    status_txt        VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY inbound_orders
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        SKIP 1
        BADFILE 'orders_batch_001.bad'
        LOGFILE 'orders_batch_001.log'
        FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            order_id_txt     CHAR(30),
            customer_id_txt  CHAR(30),
            order_date_txt   CHAR(30),
            amount_txt       CHAR(30),
            status_txt       CHAR(20)
        )
    )
    LOCATION ('orders_batch_001.csv')
)
REJECT LIMIT 10;
```

### Bước 5: Đếm và xem dữ liệu

```sql
SELECT COUNT(*) AS source_rows
FROM ext_orders_batch;
```

```sql
SELECT *
FROM ext_orders_batch
FETCH FIRST 10 ROWS ONLY;
```

Nếu cần thứ tự xác định, hãy thêm `ORDER BY`; external table không bảo đảm thứ tự record giống thứ tự vật lý trong file.

### Bước 6: Kiểm tra dữ liệu

```sql
SELECT COUNT(*) AS invalid_rows
FROM ext_orders_batch
WHERE VALIDATE_CONVERSION(TRIM(order_id_txt) AS NUMBER) = 0
   OR VALIDATE_CONVERSION(TRIM(customer_id_txt) AS NUMBER) = 0
   OR VALIDATE_CONVERSION(
          TRIM(order_date_txt) AS DATE,
          'YYYY-MM-DD'
      ) = 0
   OR VALIDATE_CONVERSION(
          TRIM(amount_txt) AS NUMBER,
          '999999999999D99',
          'NLS_NUMERIC_CHARACTERS=''.,'''
      ) = 0;
```

Ví dụ này kiểm tra khả năng chuyển đổi. Cần bổ sung kiểm tra NULL, số tiền âm, trạng thái không hợp lệ, duplicate và customer ID không tồn tại.

### Bước 7: Nạp vào staging

Sau khi xác nhận dòng hợp lệ, dùng `INSERT INTO ... SELECT ...` để nạp vào staging table đã tạo với kiểu dữ liệu và constraint phù hợp. Dùng batch ID để truy vết và bảo đảm job chạy lại không nạp trùng.

### Bước 8: Đối soát và lưu batch

Ghi nhận số record đọc được, số hợp lệ, số lỗi, số dòng staging và số dòng đã áp dụng vào bảng đích. Chỉ chuyển trạng thái batch sang `COMPLETED` khi các số liệu khớp với quy tắc đối soát.

## 18. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| External table lưu file vào database | File nằm bên ngoài; database lưu metadata để đọc file |
| Tạo DIRECTORY là tạo thư mục OS | DIRECTORY chỉ là object ánh xạ tới đường dẫn trên server |
| Grant READ trên DIRECTORY là đủ | OS account chạy Oracle cũng phải đọc được file |
| File nằm trên máy client là database tự đọc được | File phải nằm ở vị trí server database có thể truy cập |
| External table dùng DML như bảng thường | Với `ORACLE_LOADER`, external table chủ yếu là read-only; nạp vào staging để ghi dữ liệu |
| Mỗi lần SELECT đều dùng dữ liệu đã cache trong table segment | Oracle đọc file theo access driver; file thay đổi có thể làm kết quả truy vấn thay đổi |
| WHERE chọn ít dòng thì chắc chắn chỉ đọc ít byte file | File text tuần tự có thể vẫn phải scan để tìm record phù hợp |
| REJECT LIMIT UNLIMITED làm dữ liệu lỗi hợp lệ | Nó chỉ cho phép vượt ngưỡng reject; record lỗi vẫn cần được xử lý |
| Bad file chứa mọi lỗi nghiệp vụ | Lỗi nghiệp vụ cần được validate và ghi nhận riêng |
| LOCATION bảo đảm file bất biến | Quy trình bên ngoài phải quản lý thay file và batch |
| External table bảo đảm thứ tự file | Không có thứ tự kết quả nếu không `ORDER BY` |
| RAC chỉ cần file có trên một node | Mọi node có thể chạy truy vấn phải truy cập được file theo cấu hình |

External table giúp đưa dữ liệu file vào thế giới SQL của Oracle mà không cần nạp ngay vào table segment. Khi định nghĩa đúng directory, driver, record format và field mapping, ta có thể lọc, join, aggregate và kiểm tra dữ liệu trực tiếp bằng SQL. Trong quy trình sản xuất, nên dùng external table làm lớp đọc đầu vào, tách kiểm tra định dạng khỏi kiểm tra nghiệp vụ, nạp dữ liệu hợp lệ vào staging và quản lý file theo batch bất biến. Cách tổ chức này tận dụng được SQL của Oracle đồng thời giữ được khả năng truy vết, đối soát và chạy lại dữ liệu.
