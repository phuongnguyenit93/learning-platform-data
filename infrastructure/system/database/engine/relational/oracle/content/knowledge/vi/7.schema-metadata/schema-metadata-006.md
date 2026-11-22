# Tra cứu bảng, cột, ràng buộc, chỉ mục và thống kê

Khi tiếp nhận một Oracle Database chưa quen, câu hỏi đầu tiên thường không phải “viết truy vấn nào?”, mà là **database hiện có những bảng gì, các cột được định nghĩa thế nào, dữ liệu bị ràng buộc bởi quy tắc nào, chỉ mục nào đang tồn tại và Oracle đang có thống kê gì để tối ưu SQL?** Những thông tin này được lưu trong **data dictionary** (từ điển dữ liệu) và có thể tra cứu bằng các **dictionary views**.

Ví dụ, trước khi viết câu SQL nối `ORDERS` với `CUSTOMERS`, lập trình viên cần biết:

1. Hai bảng nằm trong **schema** và **PDB** nào?
2. Khóa chính, khóa ngoại và các cột liên kết được khai báo ra sao?
3. Cột `CUSTOMER_ID` là `NUMBER` hay `VARCHAR2`? Có được `NULL` không?
4. Có index phù hợp cho thao tác lọc/nối không?
5. Thống kê optimizer có phản ánh dữ liệu gần đây hay đã cũ?

Bài này hướng dẫn quy trình tra cứu metadata bằng SQL, từ các câu lệnh chỉ đọc đến một bài lab nhỏ có thể tự tạo schema mẫu. Các ví dụ sử dụng dictionary views phổ biến của Oracle Database, ưu tiên phạm vi mà người học có thể đọc bằng tài khoản ứng dụng; những view quản trị cần thêm quyền sẽ được ghi rõ.

## 1. Metadata trong Oracle là gì?

**Metadata** là dữ liệu mô tả cấu trúc và trạng thái quản lý của dữ liệu:

| Nội dung cần biết | Ví dụ metadata | Khác gì dữ liệu nghiệp vụ? |
| --- | --- | --- |
| Bảng | Tên bảng, chủ sở hữu, tablespace, kiểu tổ chức | Không phải các dòng đơn hàng trong bảng |
| Cột | Tên, thứ tự, kiểu dữ liệu, độ dài, độ chính xác, khả năng NULL | Không phải giá trị cụ thể của từng dòng |
| Ràng buộc | Primary key, foreign key, unique, check, trạng thái hiệu lực | Là quy tắc bảo vệ dữ liệu, không phải kết quả của truy vấn |
| Chỉ mục | Tên, loại, cột hoặc biểu thức, thứ tự, trạng thái, độ duy nhất | Là cấu trúc truy cập dữ liệu, không phải bản sao bảng theo nghĩa SQL |
| Thống kê | Số hàng ước lượng, số block, độ phân biệt giá trị, histogram, thời điểm thu thập | Là đầu vào cho optimizer, không phải phép đếm thời gian thực |

Oracle duy trì metadata nội bộ trong data dictionary. Các view như `USER_TABLES`, `ALL_TAB_COLUMNS`, `USER_CONSTRAINTS` và `USER_INDEXES` cung cấp giao diện SQL ổn định để tra cứu theo quyền. Người dùng thường không truy cập trực tiếp những bảng hệ thống nền tảng như `SYS.OBJ$` hoặc `SYS.TAB$` để tìm cấu trúc ứng dụng.

### Metadata tồn tại ở nhiều lớp

```text
Oracle Database / CDB
  |
  +-- PDB APP_PDB
       |
       +-- Schema SALES_APP
       |      +-- TABLE CUSTOMERS
       |      |      +-- columns
       |      |      +-- constraints
       |      |      +-- indexes liên quan
       |      +-- TABLE ORDERS
       |             +-- columns
       |             +-- constraints
       |             +-- indexes liên quan
       |             +-- optimizer statistics
       |
       +-- Schema REPORT_APP
              +-- VIEW ORDER_SUMMARY
```

**PDB**, **schema** và **table** là các ranh giới khác nhau. Cùng tên `ORDERS` có thể tồn tại ở hai schema hoặc hai PDB; tra metadata mà bỏ qua owner/container rất dễ dẫn tới kết luận sai.

## 2. Chọn đúng phạm vi: USER_, ALL_, DBA_ và CDB_

Oracle thường cung cấp các họ view với nội dung tương tự nhưng khác **phạm vi hiển thị**.

| Tiền tố | Phạm vi phổ biến | Có cột `OWNER`? | Khi nên dùng |
| --- | --- | --- | --- |
| **`USER_*`** | Đối tượng thuộc schema của người dùng hiện hành | Thông thường không cần `OWNER` vì chỉ một owner | Khảo sát các bảng/cột/index của chính schema |
| **`ALL_*`** | Đối tượng mà tài khoản hiện hành có quyền truy cập hoặc được phép thấy theo cơ chế Oracle | Thường có `OWNER` | Ứng dụng dùng bảng ở nhiều schema |
| **`DBA_*`** | Metadata của đối tượng trong database/container thuộc phạm vi quản trị | Có `OWNER` | DBA kiểm kê, kiểm soát cấu trúc và quyền toàn phạm vi được cấp |
| **`CDB_*`** | Metadata nhiều container trong một CDB, tùy quyền và container đang kết nối | Có `CON_ID` và các cột owner liên quan | Quản trị CDB/PDB xuyên container |

Ví dụ khi đăng nhập schema `SALES_APP`:

```sql
-- Bảng do chính user hiện tại sở hữu.
SELECT table_name
FROM user_tables
ORDER BY table_name;

-- Bảng mà user có thể thấy qua quyền truy cập.
SELECT owner, table_name
FROM all_tables
WHERE table_name = 'ORDERS'
ORDER BY owner, table_name;

-- Dành cho tài khoản có quyền đọc dictionary cấp DBA.
SELECT owner, table_name
FROM dba_tables
WHERE table_name = 'ORDERS'
ORDER BY owner, table_name;
```

**`ALL_*` không có nghĩa “mọi bảng trên toàn server”**: đó là tập metadata tài khoản được phép nhìn thấy. Thiếu kết quả có thể do không tồn tại đối tượng, sai PDB/schema, tên chữ hoa/chữ thường khác nhau hoặc thiếu quyền. Không nên xin quyền `SELECT ANY DICTIONARY` chỉ để chạy bài học SQL thông thường.

### 2.1. Xác nhận ngữ cảnh phiên làm việc trước

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user_name,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema_name
FROM dual;
```

- **`SESSION_USER`** là danh tính user của phiên đăng nhập.
- **`CURRENT_SCHEMA`** là schema mặc định dùng để phân giải tên đối tượng không ghi prefix; nó có thể thay đổi bằng `ALTER SESSION SET CURRENT_SCHEMA = ...` mà **không đổi danh tính hoặc cấp thêm quyền**.
- **`CON_NAME`** giúp xác nhận đã vào đúng PDB. Đăng nhập vào CDB root thay vì PDB ứng dụng sẽ cho bộ metadata khác.
- **`DB_NAME`** giúp nhận diện database, nhưng riêng giá trị này chưa phân biệt hết các PDB cùng CDB.

Các view `USER_*` mô tả những đối tượng **thuộc user**, không tự trở thành view của một schema khác chỉ vì đổi `CURRENT_SCHEMA`. Nếu ứng dụng thay đổi default schema, nên sử dụng các view `ALL_*` có lọc `OWNER` để khảo sát schema khác được cấp quyền.

### 2.2. Tên đối tượng và chữ hoa/chữ thường

Oracle thường chuyển tên identifier **không có dấu nháy kép** thành chữ hoa trong dictionary:

```sql
CREATE TABLE orders (id NUMBER);
-- Dictionary thường ghi TABLE_NAME = 'ORDERS'.
```

Nếu một identifier được tạo **có dấu nháy kép**:

```sql
CREATE TABLE "OrdersMixed" ("OrderId" NUMBER);
-- Dictionary giữ chính xác TABLE_NAME = 'OrdersMixed'.
```

Do đó `WHERE TABLE_NAME = 'orders'` thường không tìm ra bảng `ORDERS` thông thường. Với object tạo bằng identifier có dấu nháy kép, tên phải khớp chính xác. Để giảm sự phức tạp khi thao tác bằng SQL và công cụ, schema ứng dụng thường ưu tiên tên không cần dấu nháy kép.

## 3. Bảng mẫu cho các truy vấn trong bài

Để các ví dụ có tên đối tượng cụ thể, có thể tự tạo hai bảng trong **schema thực hành riêng** với quyền `CREATE TABLE`, `CREATE INDEX` và quota tablespace phù hợp. Không chạy DDL trên schema sản xuất hoặc schema do người khác quản lý.

```sql
CREATE TABLE lab_customers (
    customer_id   NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_code VARCHAR2(20 CHAR)  NOT NULL,
    full_name     VARCHAR2(120 CHAR) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id),
    CONSTRAINT uk_lab_customers_code UNIQUE (customer_code)
);

CREATE TABLE lab_orders (
    order_id    NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id NUMBER NOT NULL,
    amount      NUMBER(12, 2) DEFAULT 0 NOT NULL,
    status      VARCHAR2(12 CHAR) DEFAULT 'NEW' NOT NULL,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers (customer_id),
    CONSTRAINT ck_lab_orders_amount CHECK (amount >= 0),
    CONSTRAINT ck_lab_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX ix_lab_orders_customer_created
    ON lab_orders (customer_id, created_at);
```

Sau đó tạo ít dữ liệu minh họa:

```sql
INSERT INTO lab_customers (customer_code, full_name)
VALUES ('C001', 'Nguyen An');

INSERT INTO lab_customers (customer_code, full_name)
VALUES ('C002', 'Tran Binh');

INSERT INTO lab_orders (customer_id, amount, status)
SELECT customer_id, 150000, 'NEW'
FROM lab_customers
WHERE customer_code = 'C001';

COMMIT;
```

Hai bảng có một quan hệ **cha – con**:

```text
LAB_CUSTOMERS                              LAB_ORDERS
  CUSTOMER_ID (PK)  <------------------+   ORDER_ID (PK)
  CUSTOMER_CODE (UNIQUE)               +-- CUSTOMER_ID (FK)
  FULL_NAME                                 AMOUNT (CHECK >= 0)
  CREATED_AT                                STATUS (CHECK tập giá trị)
                                            CREATED_AT

Index riêng: IX_LAB_ORDERS_CUSTOMER_CREATED
             (CUSTOMER_ID, CREATED_AT)
```

Các lệnh tra cứu dưới đây giả định bạn đang đăng nhập **chính schema đã tạo hai bảng**, hoặc điều chỉnh sang `ALL_*` với lọc `OWNER` nếu đăng nhập tài khoản khác.

## 4. Tra cứu danh sách bảng và thuộc tính lưu trữ

### 4.1. Liệt kê bảng trong schema

```sql
SELECT
    table_name,
    tablespace_name,
    temporary,
    partitioned,
    iot_type
FROM user_tables
WHERE table_name LIKE 'LAB_%'
ORDER BY table_name;
```

Giải thích:

| Cột metadata | Cách đọc |
| --- | --- |
| `TABLE_NAME` | Tên bảng do user hiện tại sở hữu |
| `TABLESPACE_NAME` | Tablespace được gắn với storage của bảng, khi có ý nghĩa đối với kiểu bảng đó |
| `TEMPORARY` | Bảng có phải temporary table theo metadata hay không |
| `PARTITIONED` | Bảng có phân vùng không |
| `IOT_TYPE` | Phân biệt một số dạng index-organized table và cấu trúc liên quan; bảng heap thông thường thường có giá trị `NULL` |

Một bảng có thể nằm trong tablespace khác với index của nó. `TABLESPACE_NAME` không phải đường dẫn datafile; nó là tên của một cấu trúc lưu trữ **logic**. Với bảng partitioned, IOT hoặc các đối tượng đặc biệt, thông tin storage có thể phải tra thêm các view chuyên biệt thay vì suy từ một dòng của `USER_TABLES`.

### 4.2. Tìm bảng của schema khác

```sql
SELECT
    owner,
    table_name,
    tablespace_name,
    temporary
FROM all_tables
WHERE owner = 'SALES_APP'
  AND table_name LIKE 'ORD%'
ORDER BY table_name;
```

Đổi `SALES_APP` thành **owner thật** mà tài khoản có quyền nhìn thấy. Đừng thay bằng tên PDB: `OWNER` chỉ schema, còn vị trí PDB là ngữ cảnh kết nối. Khi cần xem tất cả bảng ở mức quản trị, DBA có thể dùng `DBA_TABLES`; khi quản trị xuyên container, sử dụng `CDB_TABLES` và xét `CON_ID`.

### 4.3. Phân biệt table và view

`USER_TABLES` tra bảng, không phải danh sách mọi đối tượng tên giống bảng. Hãy kết hợp:

```sql
SELECT object_name, object_type, status, created, last_ddl_time
FROM user_objects
WHERE object_name LIKE 'LAB_%'
ORDER BY object_type, object_name;

SELECT view_name
FROM user_views
WHERE view_name LIKE 'LAB_%'
ORDER BY view_name;
```

`USER_OBJECTS` có thể chứa `TABLE`, `VIEW`, `INDEX`, `SEQUENCE`, `TRIGGER` và các object khác. `LAST_DDL_TIME` phản ánh một số thay đổi DDL/metadata của object; **không phải** thời điểm dòng dữ liệu cuối cùng được `INSERT` hoặc `UPDATE`.

Nếu cần phân tích một materialized view, external table hoặc partitioned table, hãy nhận diện đúng kiểu đối tượng và mở rộng sang view chuyên dụng thay vì mặc định nó giống heap table thông thường.

## 5. Tra cứu cấu trúc cột

### 5.1. Lấy danh sách cột theo đúng thứ tự

```sql
SELECT
    table_name,
    column_id,
    column_name,
    data_type,
    data_length,
    data_precision,
    data_scale,
    char_used,
    char_length,
    nullable
FROM user_tab_columns
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, column_id;
```

| Metadata | Ý nghĩa |
| --- | --- |
| `COLUMN_ID` | Vị trí hiển thị/định nghĩa của cột trong thứ tự thông thường |
| `COLUMN_NAME` | Tên cột |
| `DATA_TYPE` | Kiểu Oracle, ví dụ `NUMBER`, `VARCHAR2`, `TIMESTAMP(6)` |
| `DATA_LENGTH` | Độ dài tối đa theo **byte** của kiểu cột (không phải số ký tự hiển thị) |
| `DATA_PRECISION`, `DATA_SCALE` | Độ chính xác và scale cho kiểu số có khai báo, ví dụ `NUMBER(12,2)` |
| `CHAR_USED` | `B` là byte semantics, `C` là character semantics đối với kiểu ký tự thích hợp |
| `CHAR_LENGTH` | Chiều dài khai báo theo số ký tự, khi áp dụng |
| `NULLABLE` | Cột có cho phép NULL theo metadata không (`Y`/`N`) |

Với `VARCHAR2(20 CHAR)`, Oracle cho phép đến 20 **ký tự** phù hợp bộ mã, nhưng dung lượng byte thực tế còn phụ thuộc character set và giới hạn byte của kiểu. Không dùng riêng `DATA_LENGTH` để khẳng định “cột này chỉ chứa 20 ký tự”. Với `NUMBER` không khai báo precision/scale rõ, các trường tương ứng có thể `NULL`; điều đó không biến cột thành chuỗi.

### 5.2. Xem cột của bảng schema khác

```sql
SELECT
    owner,
    table_name,
    column_id,
    column_name,
    data_type,
    nullable
FROM all_tab_columns
WHERE owner = 'SALES_APP'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

Trong join các dictionary view `ALL_*`, thường cần ghép bằng **`OWNER` và `TABLE_NAME`**, vì hai schema có thể có bảng cùng tên. Chỉ join theo `TABLE_NAME` có nguy cơ ghép nhầm cột của schema khác.

### 5.3. Cột ẩn, invisible, virtual, identity và default

`USER_TAB_COLUMNS` thường lọc các cột hệ thống sinh ra và được ẩn theo cơ chế của Oracle. Khi cần kiểm tra sâu hơn, có thể dùng `USER_TAB_COLS`:

```sql
SELECT
    table_name,
    column_name,
    column_id,
    hidden_column,
    virtual_column,
    identity_column
FROM user_tab_cols
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_id NULLS LAST, column_name;
```

Lưu ý theo release:

- **Hidden/system-generated columns** có thể được Oracle dùng để hỗ trợ các tính năng nội bộ; không xem chúng như cột nghiệp vụ để ứng dụng tự ý sửa.
- **Invisible columns** là khái niệm về khả năng hiển thị trong các thao tác SQL như `SELECT *`; cần kiểm tra thuộc tính và cách các view dictionary của release thể hiện, không suy ngược chỉ từ `COLUMN_ID`.
- **Virtual columns** được tính theo biểu thức, không lưu giá trị giống một cột cơ sở thông thường.
- **Identity columns** dùng cơ chế sinh giá trị mà Oracle quản lý; có thể tra thêm `USER_TAB_IDENTITY_COLS` để xem đặc tính identity khi view đó được hỗ trợ.
- **Default expression** có thể được trình bày qua `DATA_DEFAULT`, nhưng trong một số dictionary view cột này có kiểu **LONG**. Không giả định mọi thao tác chuỗi như `SUBSTR(DATA_DEFAULT,...)` đều được SQL cho phép. Một số release cung cấp `DATA_DEFAULT_VC` với giới hạn chiều dài; với biểu thức dài hoặc khi cần DDL chính xác, dùng `DBMS_METADATA`.

Ví dụ xem identity metadata trong schema:

```sql
SELECT table_name, column_name, generation_type
FROM user_tab_identity_cols
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, column_name;
```

Tên view/cột và thông tin trả về có thể khác theo release; ví dụ bài lab hướng tới Oracle có hỗ trợ identity columns và multitenant thông dụng.

## 6. Tra cứu ràng buộc: Primary Key, Unique, Foreign Key và Check

Hai view quan trọng:

- **`USER_CONSTRAINTS`**: một dòng cho mỗi constraint, gồm tên, bảng, loại, trạng thái, điều kiện hoặc ràng buộc được tham chiếu.
- **`USER_CONS_COLUMNS`**: các cột góp mặt trong constraint và thứ tự của chúng.

### 6.1. Các mã `CONSTRAINT_TYPE`

| Mã | Loại constraint | Vai trò |
| --- | --- | --- |
| **`P`** | Primary key | Định danh hàng; các thành phần không được NULL và phải duy nhất |
| **`U`** | Unique | Ràng buộc tính duy nhất theo ngữ nghĩa Oracle, trong đó cần lưu ý cách xử lý NULL |
| **`R`** | Referential integrity / foreign key | Kiểm soát quan hệ tới khóa được tham chiếu |
| **`C`** | Check constraint | Kiểm soát biểu thức điều kiện; quy tắc `IS NOT NULL` cũng thường xuất hiện dưới dạng `C` |
| **`V` / `O`** | Các ràng buộc đặc thù liên quan view | Gặp trong `WITH CHECK OPTION` / `WITH READ ONLY` theo tài liệu release |

Không chỉ tìm `P` để nhận biết bảng có hợp lệ hay không. Một bảng có thể có nhiều `U`, `R`, `C` và một số constraint do hệ thống tự đặt tên `SYS_C...`.

### 6.2. Xem toàn bộ constraints của bảng

```sql
SELECT
    table_name,
    constraint_name,
    constraint_type,
    status,
    validated,
    deferrable,
    deferred,
    delete_rule
FROM user_constraints
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, constraint_type, constraint_name;
```

Giải thích những cột quan trọng:

| Trường | Cách diễn giải |
| --- | --- |
| `STATUS` | `ENABLED` hoặc `DISABLED` theo trạng thái constraint |
| `VALIDATED` | `VALIDATED` hay `NOT VALIDATED`, cho biết cách ràng buộc được kiểm chứng với dữ liệu |
| `DEFERRABLE` | Có cho phép hoãn kiểm tra theo transaction hay không |
| `DEFERRED` | Chế độ kiểm tra ban đầu: immediate/deferred theo metadata |
| `DELETE_RULE` | Quy tắc khi xóa hàng cha của foreign key, ví dụ `NO ACTION`, `CASCADE`, `SET NULL` theo cấu hình |

Một constraint **ENABLED NOVALIDATE** có thể có ý nghĩa khác **ENABLED VALIDATE** với dữ liệu đã tồn tại. Đừng chỉ đọc `STATUS = ENABLED` rồi kết luận toàn bộ dữ liệu lịch sử đã được kiểm chứng.

### 6.3. Xem cột tham gia constraint

```sql
SELECT
    c.table_name,
    c.constraint_name,
    c.constraint_type,
    cc.position,
    cc.column_name,
    c.status
FROM user_constraints c
LEFT JOIN user_cons_columns cc
    ON cc.constraint_name = c.constraint_name
   AND cc.table_name = c.table_name
WHERE c.table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY c.table_name, c.constraint_name, cc.position;
```

`POSITION` đặc biệt quan trọng với primary/unique/foreign key nhiều cột. Cặp khóa ghép `(A, B)` không tương đương về thứ tự với `(B, A)` trong nhiều tình huống tra cứu và thiết kế index. Với `CHECK` phức tạp, các cột liệt kê giúp nhận diện liên quan nhưng không thay thế việc đọc **biểu thức kiểm tra**.

### 6.4. Đọc điều kiện CHECK và NOT NULL

```sql
SELECT
    constraint_name,
    table_name,
    status,
    search_condition_vc
FROM user_constraints
WHERE table_name = 'LAB_ORDERS'
  AND constraint_type = 'C'
ORDER BY constraint_name;
```

Các điều kiện dự kiến gồm `AMOUNT >= 0`, `STATUS IN (...)` và các điều kiện `IS NOT NULL` được Oracle ghi cho cột bắt buộc. Trong Oracle, điều kiện `CHECK` cho phép trường hợp biểu thức đánh giá **UNKNOWN** do NULL; muốn chặn NULL thì cần `NOT NULL` hoặc một biểu thức check phù hợp. Ví dụ `CHECK (AMOUNT >= 0)` **một mình** không thay thế `AMOUNT NOT NULL`.

`SEARCH_CONDITION` thường có kiểu `LONG` và `SEARCH_CONDITION_VC` là dạng ký tự có **giới hạn độ dài** (có thể cắt bớt biểu thức dài), vì vậy khi cần dựng lại chính xác DDL nên dùng `DBMS_METADATA.GET_DDL`. Nếu release không cung cấp `SEARCH_CONDITION_VC`, sử dụng tài liệu view tương ứng và phương án đọc metadata của release đó.

### 6.5. Đi từ foreign key đến bảng cha và cột được tham chiếu

Một foreign key lưu **`R_CONSTRAINT_NAME`**, tức tên **constraint khóa P/U ở bảng cha** được tham chiếu, chứ không phải tên bảng cha. Hãy join tới constraint cha:

```sql
SELECT
    f.constraint_name   AS foreign_key_name,
    f.table_name        AS child_table,
    child_col.position  AS column_position,
    child_col.column_name AS child_column,
    parent.owner        AS parent_owner,
    parent.table_name   AS parent_table,
    parent_col.column_name AS parent_column
FROM user_constraints f
JOIN user_cons_columns child_col
  ON child_col.constraint_name = f.constraint_name
 AND child_col.table_name      = f.table_name
JOIN all_constraints parent
  ON parent.owner           = f.r_owner
 AND parent.constraint_name = f.r_constraint_name
JOIN all_cons_columns parent_col
  ON parent_col.owner           = parent.owner
 AND parent_col.constraint_name = parent.constraint_name
 AND parent_col.position        = child_col.position
WHERE f.constraint_type = 'R'
  AND f.table_name = 'LAB_ORDERS'
ORDER BY f.constraint_name, child_col.position;
```

Với lab, kết quả logic sẽ cho thấy:

```text
FK_LAB_ORDERS_CUSTOMER:
  LAB_ORDERS.CUSTOMER_ID
     -> LAB_CUSTOMERS.CUSTOMER_ID
```

**Vì sao phải join bằng owner và constraint name?** Constraint name không phải một định danh duy nhất xuyên mọi schema. Hơn nữa, foreign key có thể tham chiếu bảng ở **schema khác** nếu có quyền phù hợp. Với nhiều cột, phải ghép theo `POSITION` để không đảo sai các thành phần của khóa.

Nếu user không có quyền đọc metadata của parent qua `ALL_*`, kết quả có thể thiếu; đó là vấn đề phạm vi hiển thị, không nên kết luận quan hệ tham chiếu không tồn tại.

## 7. Tra cứu chỉ mục: định nghĩa, cột, biểu thức và trạng thái

Một **index** giúp Oracle có thêm đường truy cập tới dữ liệu; index không đảm bảo optimizer sẽ dùng nó trong mọi truy vấn. Nên đọc cả **định nghĩa**, **trạng thái** và **thống kê** trước khi đưa ra kết luận về hiệu năng.

Các view cơ bản:

| View | Cần tra gì? |
| --- | --- |
| `USER_INDEXES` | Tên, bảng, loại index, uniqueness, visibility, trạng thái |
| `USER_IND_COLUMNS` | Danh sách cột trong index và vị trí thứ tự |
| `USER_IND_EXPRESSIONS` | Biểu thức của function-based index |
| `USER_IND_STATISTICS` | Thống kê index phục vụ optimizer |
| `USER_IND_PARTITIONS` / `USER_IND_SUBPARTITIONS` | Metadata index phân vùng nếu có |

### 7.1. Liệt kê index của bảng

```sql
SELECT
    table_name,
    index_name,
    index_type,
    uniqueness,
    visibility,
    status,
    tablespace_name
FROM user_indexes
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY table_name, index_name;
```

Đối với lab, thường thấy index hỗ trợ khóa chính `PK_LAB_CUSTOMERS`, `PK_LAB_ORDERS`, unique constraint `UK_LAB_CUSTOMERS_CODE` và index được tạo rõ ràng `IX_LAB_ORDERS_CUSTOMER_CREATED`. Tên index thực tế và cách Oracle chọn/tái sử dụng index phục vụ constraint phụ thuộc những index đã tồn tại và DDL cụ thể.

Đọc các cột:

- **`INDEX_TYPE`:** ví dụ `NORMAL` (B-tree thông thường), `BITMAP` hoặc loại khác, tùy đối tượng và release.
- **`UNIQUENESS`:** `UNIQUE` hoặc `NONUNIQUE` ở mức index; **không phải** danh sách đầy đủ mọi unique constraint của bảng.
- **`VISIBILITY`:** index `VISIBLE` hay `INVISIBLE` đối với optimizer thông thường; invisible index vẫn có thể cần được duy trì khi DML, tùy cấu hình.
- **`STATUS`:** trạng thái index; với index phân vùng, cần xem thêm trạng thái partition/subpartition, vì một dòng cấp index có thể không đủ phản ánh mọi partition.
- **`TABLESPACE_NAME`:** nơi index được cấp phát lưu trữ, không bắt buộc trùng tablespace của bảng.

### 7.2. Thứ tự các cột trong index

```sql
SELECT
    i.table_name,
    i.index_name,
    i.uniqueness,
    ic.column_position,
    ic.column_name,
    ic.descend
FROM user_indexes i
JOIN user_ind_columns ic
  ON ic.index_name = i.index_name
 AND ic.table_name = i.table_name
WHERE i.table_name = 'LAB_ORDERS'
ORDER BY i.index_name, ic.column_position;
```

Với index `IX_LAB_ORDERS_CUSTOMER_CREATED`, thứ tự khai báo là:

```text
1. CUSTOMER_ID
2. CREATED_AT
```

Thứ tự này hữu ích khi phân tích prefix của composite B-tree index, điều kiện lọc `WHERE CUSTOMER_ID = :id` và việc sắp xếp/lọc theo `CREATED_AT`. Tuy nhiên việc index có được chọn còn phụ thuộc độ chọn lọc, thống kê, kích thước dữ liệu, cost model và SQL cụ thể.

### 7.3. Function-based index

Giả sử có index theo biểu thức:

```sql
CREATE INDEX ix_lab_customers_upper_name
ON lab_customers (UPPER(full_name));
```

Một số dictionary views có thể hiển thị tên **cột ẩn do hệ thống sinh ra** thay cho biểu thức gốc. Khi đó tra:

```sql
SELECT
    index_name,
    column_position,
    column_expression
FROM user_ind_expressions
WHERE table_name = 'LAB_CUSTOMERS'
ORDER BY index_name, column_position;
```

`COLUMN_EXPRESSION` có thể là kiểu `LONG` theo release, nên tránh giả định có thể dùng tất cả hàm xử lý chuỗi trực tiếp trên cột này. Function-based index còn có các yêu cầu về biểu thức, quyền, trạng thái và môi trường tính toán; việc nó tồn tại chưa chứng minh mọi `UPPER(FULL_NAME)` query chắc chắn dùng index.

### 7.4. Unique constraint và unique index có giống nhau?

**Không hoàn toàn.**

- **Unique/primary-key constraint** mô tả quy tắc dữ liệu và cách Oracle kiểm tra tính toàn vẹn.
- **Unique index** là cấu trúc lưu trữ/truy cập bảo đảm tính duy nhất của khóa index theo ngữ nghĩa riêng.
- Oracle thường dùng **index** để thực thi primary/unique constraint, và có thể **tái sử dụng index đã tồn tại** nếu phù hợp. Một constraint có thể được thực thi bằng **nonunique index** trong những trường hợp được hỗ trợ, chẳng hạn khi cần deferrable constraint.
- Ngược lại, tạo một index có `UNIQUENESS = UNIQUE` không tự tạo một dòng tương ứng trong `USER_CONSTRAINTS`.

Để liên hệ ràng buộc P/U với index đang phục vụ:

```sql
SELECT
    table_name,
    constraint_name,
    constraint_type,
    index_name,
    status,
    validated
FROM user_constraints
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
  AND constraint_type IN ('P', 'U')
ORDER BY table_name, constraint_name;
```

Một **foreign key** không mặc nhiên được Oracle tự tạo index riêng trên cột con. Index `IX_LAB_ORDERS_CUSTOMER_CREATED` của lab được tạo thủ công; việc cần index FK hay không phụ thuộc tần suất join, xóa/cập nhật hàng cha, mức đồng thời và kế hoạch truy vấn.

## 8. Thống kê optimizer: đọc đúng, đừng coi là dữ liệu thời gian thực

Oracle **cost-based optimizer (CBO)** dùng thống kê về bảng, cột, index và hệ thống để ước lượng cardinality/cost và chọn execution plan. Thống kê không phải bản sao chính xác và liên tục được cập nhật của mọi bảng.

### 8.1. Thống kê cấp bảng

```sql
SELECT
    table_name,
    object_type,
    num_rows,
    blocks,
    avg_row_len,
    sample_size,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
  AND object_type = 'TABLE'
ORDER BY table_name;
```

| Trường | Cách diễn giải |
| --- | --- |
| `NUM_ROWS` | Số hàng theo **thống kê optimizer** tại thời điểm thu thập; không phải `COUNT(*)` hiện tại |
| `BLOCKS` | Số block dùng cho dữ liệu bảng theo thống kê/cách tính của Oracle |
| `AVG_ROW_LEN` | Độ dài hàng trung bình theo thống kê, thường tính bằng byte |
| `SAMPLE_SIZE` | Số hàng mẫu được dùng để ước lượng, khi có |
| `LAST_ANALYZED` | Thời điểm thống kê được thu thập/cập nhật |
| `STALE_STATS` | Cờ nhận diện thống kê có thể đã cũ theo cơ chế Oracle; không phải phép xác minh tuyệt đối chất lượng plan |
| `OBJECT_TYPE` | Thông tin cấp TABLE/PARTITION/SUBPARTITION tùy dạng bảng |

Nếu bảng mới được tạo hoặc thống kê chưa được thu thập, `NUM_ROWS`/`LAST_ANALYZED` có thể `NULL`. Với partitioned table, cần xem cả thống kê partition/subpartition và global statistics, không chỉ một hàng cấp bảng.

Để thấy khác biệt giữa dữ liệu đang tồn tại và metadata:

```sql
-- Số dòng thực tại thời điểm truy vấn, theo tính nhất quán của Oracle.
SELECT COUNT(*) AS actual_rows
FROM lab_orders;

-- Giá trị thống kê gần nhất (nếu có).
SELECT num_rows, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS'
  AND object_type = 'TABLE';
```

Hai số **có thể khác nhau** ngay cả khi không có lỗi dữ liệu. `COUNT(*)` phải đọc dữ liệu theo kế hoạch truy vấn và snapshot thích hợp; `NUM_ROWS` chỉ đọc giá trị thống kê đã có. Nếu ứng dụng thêm 1.000.000 dòng sau khi thu thập thống kê, `NUM_ROWS` có thể chưa phản ánh các dòng đó.

### 8.2. Thống kê cấp cột

```sql
SELECT
    table_name,
    column_name,
    num_distinct,
    num_nulls,
    density,
    histogram,
    num_buckets,
    avg_col_len,
    last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_name;
```

- **`NUM_DISTINCT`:** số giá trị khác nhau mà optimizer ghi nhận/ước lượng.
- **`NUM_NULLS`:** số NULL theo thống kê, không phải kiểm tra chính xác trực tiếp ngay lúc truy vấn.
- **`DENSITY`:** giá trị liên quan ước lượng selectivity, cách sử dụng phụ thuộc histogram và thuật toán của release.
- **`HISTOGRAM`, `NUM_BUCKETS`:** thông tin phân bố giá trị khi Oracle thu thập histogram, hữu ích với dữ liệu lệch mạnh.
- **`AVG_COL_LEN`:** độ dài trung bình của dữ liệu cột theo thống kê.

Ví dụ `STATUS` có 99% giá trị `PAID` và 1% `CANCELLED`. Dùng phân bố đồng đều để dự đoán số hàng cho cả hai điều kiện sẽ thiếu chính xác. Histogram **có thể** giúp optimizer ước lượng tốt hơn, nhưng tạo histogram cho mọi cột không phải mặc định tối ưu: cần workload, mức độ skew, bind variables và cách Oracle xử lý theo release.

### 8.3. Thống kê cấp index

```sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor,
    last_analyzed
FROM user_ind_statistics
WHERE index_name IN (
    'IX_LAB_ORDERS_CUSTOMER_CREATED',
    'IX_LAB_CUSTOMERS_UPPER_NAME'
)
ORDER BY index_name;
```

| Metadata | Ý nghĩa khái quát |
| --- | --- |
| `BLEVEL` | Số mức branch giữa root và leaf trong cấu trúc B-tree theo thống kê |
| `LEAF_BLOCKS` | Số leaf blocks theo thống kê |
| `DISTINCT_KEYS` | Số giá trị khóa index khác nhau theo thống kê |
| `CLUSTERING_FACTOR` | Mức tương quan giữa thứ tự entry index và vị trí row trong bảng, quan trọng khi ước lượng I/O truy cập bảng qua index |
| `LAST_ANALYZED` | Thời điểm thu thập/thay đổi thống kê index |

**Clustering factor không phải phần trăm fragmentation**. Nó là đầu vào cho optimizer khi ước lượng chi phí lấy các hàng trong bảng theo thứ tự index. Một giá trị cao không tự chứng minh “index bị hỏng”; cách dữ liệu sắp xếp vật lý và mẫu truy cập có thể khiến chi phí đọc bảng cao.

### 8.4. Thu thập lại thống kê trong lab

Trên hai bảng **bạn tự tạo**, có thể dùng package `DBMS_STATS`:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
```

`cascade => TRUE` yêu cầu Oracle thu thập thống kê index liên quan theo cách package hỗ trợ. Các cơ chế thống kê tự động, incremental statistics, histogram, stats locking và real-time statistics (khi có) làm quá trình quản trị thực tế phong phú hơn ví dụ.

**Không thu thập lại thống kê production một cách tùy tiện.** Cập nhật thống kê có thể làm optimizer chọn execution plan khác, kéo theo thay đổi hiệu năng. Trên hệ thống thật cần xác định thời gian, phương thức, quyền và chính sách quản trị; bài học này chỉ dùng `DBMS_STATS` trên bảng lab do chính mình tạo.

### 8.5. Metadata khác execution plan

Biết bảng có index và thống kê còn mới chưa chứng minh một SQL sẽ sử dụng index đó. Để xem kế hoạch dự kiến của một SQL cụ thể, có thể chạy trong môi trường thực hành:

```sql
EXPLAIN PLAN FOR
SELECT order_id, amount
FROM lab_orders
WHERE customer_id = 1
ORDER BY created_at DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` là **kế hoạch dự kiến**, có thể khác cursor plan thực sự của lần chạy với bind/điều kiện runtime. Khi phân tích hiệu năng thật, DBA có thể cần `DBMS_XPLAN.DISPLAY_CURSOR` cùng runtime statistics và quyền thích hợp. Đừng kết luận index nào “không dùng” chỉ từ một câu lệnh `EXPLAIN PLAN` trong bảng lab chứa vài dòng.

## 9. Truy vấn tổng hợp để khảo sát một bảng nhanh

Khi gặp một bảng chưa biết, làm theo thứ tự sau.

### Bước 1 — Xác nhận bảng và owner

```sql
SELECT owner, table_name, tablespace_name, partitioned
FROM all_tables
WHERE table_name = 'ORDERS'
ORDER BY owner;
```

Nếu có nhiều dòng, chọn owner/PDB đúng. Đối với tên được tạo bằng dấu nháy kép, dùng chính xác tên trong dictionary.

### Bước 2 — Lấy các cột

```sql
SELECT owner, column_id, column_name, data_type,
       data_length, data_precision, data_scale, nullable
FROM all_tab_columns
WHERE owner = 'SALES_APP'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

### Bước 3 — Lấy constraints và cột của chúng

```sql
SELECT
    c.owner,
    c.constraint_name,
    c.constraint_type,
    cc.position,
    cc.column_name,
    c.status,
    c.validated
FROM all_constraints c
LEFT JOIN all_cons_columns cc
  ON cc.owner           = c.owner
 AND cc.constraint_name = c.constraint_name
 AND cc.table_name      = c.table_name
WHERE c.owner = 'SALES_APP'
  AND c.table_name = 'ORDERS'
ORDER BY c.constraint_name, cc.position;
```

### Bước 4 — Lấy các index và thứ tự cột

```sql
SELECT
    i.owner,
    i.index_name,
    i.uniqueness,
    i.status,
    ic.column_position,
    ic.column_name
FROM all_indexes i
LEFT JOIN all_ind_columns ic
  ON ic.index_owner = i.owner
 AND ic.index_name  = i.index_name
 AND ic.table_owner = i.table_owner
 AND ic.table_name  = i.table_name
WHERE i.table_owner = 'SALES_APP'
  AND i.table_name = 'ORDERS'
ORDER BY i.index_name, ic.column_position;
```

Ở các `ALL_IND_*` views, **index owner** có thể khác **table owner** trong các cấu hình đặc thù; sử dụng các khóa owner phù hợp, không tự cho rằng mọi metadata chỉ cần `INDEX_NAME`.

### Bước 5 — Xem thời điểm và giá trị thống kê

```sql
SELECT
    owner,
    table_name,
    num_rows,
    blocks,
    avg_row_len,
    last_analyzed,
    stale_stats
FROM all_tab_statistics
WHERE owner = 'SALES_APP'
  AND table_name = 'ORDERS'
  AND object_type = 'TABLE';
```

Nếu không có quyền xem, dừng ở dữ liệu nhìn thấy hợp lệ hoặc nhờ DBA thực hiện một truy vấn quản trị **chỉ đọc**. Đừng dùng tài khoản có quyền rộng để tự ý thay đổi mọi schema vì chỉ cần khảo sát metadata.

## 10. Lấy DDL để đọc đầy đủ cấu trúc

Dictionary views phù hợp cho **lọc, join và phân tích**; khi cần bản DDL tương đối đầy đủ của một đối tượng, có thể dùng package `DBMS_METADATA`:

```sql
-- Trong schema sở hữu bảng lab.
SELECT DBMS_METADATA.GET_DDL('TABLE', 'LAB_ORDERS', USER)
FROM dual;

SELECT DBMS_METADATA.GET_DDL('INDEX',
                            'IX_LAB_ORDERS_CUSTOMER_CREATED',
                            USER)
FROM dual;
```

Một số SQL client giới hạn cách hiển thị CLOB; cần bật hiển thị CLOB hoặc xuất kết quả đúng cách. Khi truy xuất DDL của object ở schema khác, quyền và chính sách metadata có thể giới hạn kết quả.

DDL tạo ra có thể chứa **storage clauses**, identity, constraint, tablespace, thông số tùy chọn và các tính năng gắn với release. Không chép nguyên DDL đó vào một database khác rồi chắc chắn chạy được: phải xem các tablespace, quyền, đặc tính edition và các phụ thuộc thực tế. `DBMS_METADATA` cung cấp tiện ích transform để điều chỉnh cách trình bày DDL trong phiên làm việc khi cần xuất cấu trúc.

### Khi nào tra view, khi nào lấy DDL?

| Mục tiêu | Cách phù hợp |
| --- | --- |
| Tìm tất cả bảng theo prefix và owner | `ALL_TABLES` / `USER_TABLES` |
| Tìm cột có kiểu hoặc độ dài nhất định | `ALL_TAB_COLUMNS` |
| Vẽ quan hệ PK/FK giữa các bảng | `ALL_CONSTRAINTS` + `ALL_CONS_COLUMNS` |
| Xem index nào có cột đầu tiên `CUSTOMER_ID` | `ALL_INDEXES` + `ALL_IND_COLUMNS` |
| Xem ước lượng hàng và thời điểm thu thập | `ALL_TAB_STATISTICS` |
| Đọc định nghĩa đầy đủ để kiểm tra/migration | `DBMS_METADATA.GET_DDL` |
| Biết truy vấn thực tế có nhanh hay không | Execution plan + runtime measurements, không suy ra chỉ từ metadata |

## 11. Những lỗi hay gặp khi tra cứu metadata

| Triệu chứng hoặc kết luận sai | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `USER_TABLES` không có bảng `SALES_APP.ORDERS` | Bạn đăng nhập bằng user khác | Dùng `ALL_TABLES` với `OWNER` hoặc vào đúng schema |
| `ALL_TABLES` trả nhiều bảng `ORDERS` | Nhiều schema có bảng trùng tên | Gắn thêm điều kiện `OWNER` và kiểm tra PDB |
| Không thấy bảng dù ứng dụng query được | Dùng synonym, wrong PDB, quyền hoặc identifier có dấu nháy kép | Xem `ALL_SYNONYMS`, `SYS_CONTEXT` và tên chính xác |
| Cột `DATA_LENGTH = 80` nên nghĩ luôn chứa 80 ký tự | Nhầm byte với char semantics | Đọc `CHAR_USED`, `CHAR_LENGTH` và kiểu dữ liệu |
| `USER_CONSTRAINTS` có một constraint `C` không tự tạo | Oracle sinh check cho `NOT NULL` | Đọc `SEARCH_CONDITION_VC` hoặc DDL |
| Tìm parent table FK bằng cách đọc `R_CONSTRAINT_NAME` như tên bảng | Đây là **tên constraint được tham chiếu** | Join tới `ALL_CONSTRAINTS` và `ALL_CONS_COLUMNS` |
| Thấy foreign key mà không thấy index tương ứng | Oracle không tự tạo FK index trong mọi trường hợp | Đánh giá nhu cầu index theo workload |
| Thấy `UNIQUE` ở `USER_INDEXES` nên cho rằng có unique constraint | Index và constraint là hai loại object/metadata khác nhau | Kiểm tra thêm `USER_CONSTRAINTS` |
| `NUM_ROWS` khác `COUNT(*)` | Optimizer stats là ảnh chụp/ước lượng tại lúc thu thập | Xem `LAST_ANALYZED`, `STALE_STATS` và chính sách `DBMS_STATS` |
| `INDEX_STATUS = VALID` nên chắc chắn query dùng index | Valid index không đồng nghĩa optimizer chọn index | Xem execution plan, thống kê và điều kiện SQL |
| Xem được metadata nhưng `SELECT` bảng báo thiếu quyền | Metadata visibility và quyền thao tác có phạm vi khác nhau | Kiểm tra grants, view scope và tên object thực |
| Query trên `DBA_*` báo thiếu quyền | View quản trị cần privilege | Dùng `USER_*`/`ALL_*` khi đủ, hoặc nhờ DBA chạy truy vấn được phê duyệt |
| Metadata có cột ẩn khó hiểu | Tính năng Oracle có thể sinh hidden/virtual columns | Xem `USER_TAB_COLS` và DDL; không chỉnh metadata hệ thống |

### Synonym không tạo ra một bản sao của bảng

Giả sử trong schema ứng dụng có synonym `ORDERS` trỏ tới `SALES_APP.ORDERS`. Truy vấn:

```sql
SELECT owner, synonym_name, table_owner, table_name, db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS'
ORDER BY owner;
```

Một synonym chỉ là **tên tham chiếu**, không phải table mới. Muốn đọc cột, constraint và index, đi tới **owner/table thật**. Nếu synonym qua database link, metadata và quyền trên remote database phải được xử lý theo giới hạn kết nối remote; không giả định local `ALL_TABLES` luôn chứa object remote đó.

### Có nên tin hoàn toàn vào tên constraint?

Tên như `PK_ORDERS`, `FK_ORDERS_CUSTOMER` hay `IX_ORDERS_CREATED` giúp đọc dễ dàng nhưng là **quy ước đặt tên**, không bảo đảm loại hoặc nội dung. Một constraint `SYS_C005432` vẫn có thể là khóa hoặc `NOT NULL` quan trọng. Luôn dựa vào `CONSTRAINT_TYPE`, join metadata cột và điều kiện thực tế thay vì đoán từ prefix.

## 12. Bài tập thực hành

### Bài 1 — Khảo sát bảng lab

Sau khi tạo hai bảng ở mục 3, hãy viết SQL trả lời:

1. Schema của phiên hiện tại là gì? PDB nào đang được kết nối?
2. Có bao nhiêu bảng bắt đầu bằng `LAB_` trong `USER_TABLES`?
3. Mỗi bảng có những cột nào, theo đúng `COLUMN_ID`?
4. Cột `AMOUNT` có precision/scale nào và có cho phép NULL không?
5. Cột `CUSTOMER_CODE` khai báo giới hạn theo **byte** hay **character**?

**Kết quả nên giải thích bằng metadata**, không chỉ chụp màn hình table grid của SQL client.

### Bài 2 — Vẽ quan hệ từ dictionary

Dùng `USER_CONSTRAINTS` và `USER_CONS_COLUMNS` để tìm:

- Primary key của mỗi bảng.
- Unique constraint ở `CUSTOMER_CODE`.
- Foreign key từ `LAB_ORDERS` tới `LAB_CUSTOMERS` và đúng tên cột liên kết.
- Check constraint giới hạn `AMOUNT` và `STATUS`.
- Những constraint `C` phát sinh từ yêu cầu `NOT NULL`.

Sau đó vẽ lại sơ đồ quan hệ chỉ dựa trên **dictionary**, không nhìn vào câu lệnh `CREATE TABLE` ban đầu. Điều này mô phỏng việc nhận bàn giao một schema mà bạn không được cung cấp script DDL.

### Bài 3 — Phân biệt constraint và index

1. Liệt kê `USER_INDEXES` cho `LAB_ORDERS`.
2. Dùng `USER_IND_COLUMNS` để ghi lại thứ tự các cột trong mỗi index.
3. Xem `USER_CONSTRAINTS.INDEX_NAME` cho khóa chính và unique.
4. Xác định `IX_LAB_ORDERS_CUSTOMER_CREATED` do câu `CREATE INDEX` nào sinh ra.
5. Thảo luận tại sao có foreign key trên `CUSTOMER_ID` không đồng nghĩa Oracle tự tạo index tên `FK_LAB_ORDERS_CUSTOMER`.

### Bài 4 — So sánh thống kê với số hàng thực tế

Trên bảng lab của mình:

```sql
SELECT COUNT(*) AS actual_rows FROM lab_orders;

SELECT num_rows, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS'
  AND object_type = 'TABLE';
```

Ghi lại cả hai giá trị, thu thập lại thống kê bằng `DBMS_STATS` ở mục 8.4, rồi đọc lại. Nếu các số vẫn khác hoặc thống kê chưa cập nhật theo kỳ vọng, hãy giải thích theo phương pháp lấy mẫu, phiên bản và trạng thái thu thập thay vì tự động coi đó là lỗi database.

### Bài 5 — Mô phỏng tình huống bàn giao schema

Bạn được giao kết nối tới `SALES_APP` nhưng đăng nhập là `REPORT_APP`. Lập checklist truy vấn chỉ đọc để xác định:

1. Đúng database/PDB/`SESSION_USER`/`CURRENT_SCHEMA` chưa?
2. Schema `SALES_APP` có bảng `ORDERS` mà tài khoản hiện thấy được không?
3. Bảng có những cột và constraints nào?
4. Index nào hỗ trợ điều kiện lọc `CUSTOMER_ID` và sắp xếp `CREATED_AT`?
5. Thống kê bảng được thu thập gần đây chưa?

Nếu `ALL_*` không trả về đối tượng cần xem, hãy trình bày **phạm vi quyền bị thiếu** và loại quyền phù hợp cần phối hợp với DBA; không tự dùng tài khoản `SYS` để bỏ qua quá trình phân quyền.

### Dọn dữ liệu lab

Chỉ xóa các bảng **do chính bạn tạo cho bài học**, trong đúng schema thực hành:

```sql
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
```

`PURGE` bỏ qua recycle bin của các bảng được xóa; đừng dùng trên dữ liệu mà bạn cần khôi phục. Các index và constraints thuộc bảng bị xóa sẽ được xử lý theo quy tắc DDL của Oracle. Nếu đã tạo thêm index/function-based index trong lab, chúng gắn với bảng và cũng bị loại bỏ khi drop bảng theo cơ chế Oracle.

## 13. Một quy trình đọc schema có thể dùng hàng ngày

Khi mở một database mới, trình tự thực tế nên là:

```text
1. Xác nhận CDB/PDB, SESSION_USER, CURRENT_SCHEMA
                         |
                         v
2. Tìm TABLE và OWNER trong USER_/ALL_TABLES
                         |
                         v
3. Đọc COLUMN_NAME, DATA_TYPE, NULLABLE trong *_TAB_COLUMNS
                         |
                         v
4. Đọc PK, UQ, FK, CHECK trong *_CONSTRAINTS
   + *_CONS_COLUMNS
                         |
                         v
5. Đọc INDEX_TYPE, COLUMNS, STATUS trong
   *_INDEXES + *_IND_COLUMNS / *_IND_EXPRESSIONS
                         |
                         v
6. Đọc NUM_ROWS, NUM_DISTINCT, HISTOGRAM,
   LAST_ANALYZED trong *_TAB/IND_STATISTICS
                         |
                         v
7. Dùng DBMS_METADATA để xem DDL đầy đủ nếu cần
                         |
                         v
8. Chỉ khi cần phân tích SQL cụ thể:
   đo execution plan và runtime I/O/cardinality
```

Cách làm này giúp tách ba câu hỏi: **cấu trúc đang được khai báo thế nào**, **optimizer đang biết gì về dữ liệu**, và **truy vấn thực tế đang chạy ra sao**. Ba câu trả lời liên quan nhưng không thay thế cho nhau.

## Tài liệu Oracle nên tham khảo

- [Oracle Database Reference – Data Dictionary](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — giải thích và liệt kê các dictionary views theo từng release.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — schema, bảng, index, data dictionary và thống kê trong kiến trúc Oracle.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — cú pháp `CREATE TABLE`, `CREATE INDEX`, constraints, identifiers và data types.
- [Oracle Database PL/SQL Packages and Types Reference – DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — cách thu thập, xem và quản lý optimizer statistics.
- [Oracle Database PL/SQL Packages and Types Reference – DBMS_METADATA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_METADATA.html) — truy xuất DDL và metadata của đối tượng.

Tên cột hoặc khả năng hiển thị của một số view có thể thay đổi theo release, edition, loại object và quyền truy cập. Khi khảo sát hệ thống cụ thể, luôn đối chiếu tài liệu đúng phiên bản Oracle được cài.
