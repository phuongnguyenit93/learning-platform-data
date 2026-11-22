# Data dictionary, static dictionary view và dynamic performance view trong Oracle

Khi làm việc với **Oracle Database**, lập trình viên thường cần biết “bảng này có những cột nào?”, “khóa ngoại tham chiếu bảng nào?”, “user hiện tại được phép truy cập object gì?”. DBA và người vận hành lại thường hỏi “session nào đang chạy?”, “câu SQL nào tiêu thụ nhiều tài nguyên?”, “instance khởi động lúc nào?”, “database đang chờ I/O hay lock?”. Oracle cung cấp hai nhóm view quan trọng để trả lời những câu hỏi đó:

- **Static data dictionary views** (view từ điển dữ liệu tĩnh): trình bày **metadata được lưu và quản lý bởi Oracle**, như schema, object, cột, constraint, index, user, role, quyền, tablespace và thông tin thống kê được ghi nhận. Những view thường có tiền tố **`USER_`**, **`ALL_`**, **`DBA_`** hoặc **`CDB_`**.
- **Dynamic performance views** (view hiệu năng động): trình bày **trạng thái hoạt động và thống kê trong lúc Oracle đang chạy**, như instance, session, SQL cursor, wait event, tài nguyên và tham số đang có hiệu lực. Những view thường có tên **`V$...`** hoặc **`GV$...`**.

Hai nhóm đều cho phép truy vấn bằng SQL `SELECT`, nhưng **không cùng nguồn dữ liệu, ngữ nghĩa thời gian, quyền truy cập hay phạm vi container/instance**. Một điều dễ nhầm là từ *static* không có nghĩa nội dung bất biến: sau một lệnh `CREATE TABLE`, metadata trong dictionary cũng thay đổi. “Static” được dùng để phân biệt metadata có tính cấu trúc/lâu dài với số liệu vận hành biến động trong các dynamic view.

## 1. Bức tranh tổng thể: Oracle lưu và trình bày những gì?

```text
                       ORACLE DATABASE
                              |
            +-----------------+------------------+
            |                                    |
      DATA DICTIONARY                    RUNTIME / INSTANCE
      metadata về database              trạng thái hoạt động
      - user, role, grant                - session, cursor
      - table, column, index             - wait, lock, memory
      - constraint, view                 - process, resource
      - tablespace, object               - SQL statistics
            |                                    |
            v                                    v
      Static dictionary views            Dynamic performance views
      USER_* / ALL_*                      V$SESSION / V$SQL
      DBA_* / CDB_*                       V$INSTANCE / V$PARAMETER
      DICTIONARY / DICT                   GV$SESSION / GV$SQL
            |                                    |
            +-----------------+------------------+
                              |
                        SQL SELECT
                              |
              Developer / DBA / Operations
```

**Data dictionary** là tập metadata mà Oracle dùng để mô tả chính database và các đối tượng bên trong. Nó bao gồm định nghĩa và thông tin quản lý object; đây **không phải một schema nghiệp vụ để ứng dụng tự sửa dữ liệu**. Trong Oracle, nhiều bảng nền tảng thuộc schema hệ thống `SYS`; Oracle cung cấp các view có kiểm soát để người dùng truy vấn thông tin phù hợp với quyền của mình.

Các dynamic performance view thường phơi bày thông tin từ những cấu trúc vận hành và thống kê được Oracle duy trì khi instance hoạt động. Nhiều tên `V$...` người dùng truy vấn là **public synonym** trỏ tới view do `SYS` sở hữu, có dạng `V_$...`; tương tự, `GV$...` thường trỏ tới `GV_$...`. Synonym làm tên dễ sử dụng, nhưng **không tự cấp quyền `SELECT`** trên dữ liệu của view.

| Khía cạnh | Static dictionary view | Dynamic performance view |
|---|---|---|
| Câu hỏi chính | “Database được định nghĩa, cấp quyền và tổ chức ra sao?” | “Oracle đang hoạt động và tiêu thụ tài nguyên như thế nào?” |
| Dữ liệu đại diện | Metadata của bảng, cột, constraint, user, role, object, storage | Session, cursor SQL, thời gian xử lý, wait, process, tài nguyên, trạng thái instance |
| Ví dụ | `USER_TABLES`, `ALL_TAB_COLUMNS`, `DBA_OBJECTS`, `CDB_USERS` | `V$SESSION`, `V$SQL`, `V$INSTANCE`, `GV$SESSION` |
| Tính cập nhật | Thay đổi khi metadata hoặc thông tin lưu trữ liên quan được Oracle cập nhật | Có thể thay đổi liên tục trong lúc đọc; nhiều chỉ số là bộ đếm tích lũy |
| Phạm vi | Theo owner, quyền nhìn object, container và nhóm view | Theo view, instance, container và quyền chẩn đoán |
| Công việc tiêu biểu | Khám phá schema, kiểm tra migration, phân quyền, đối chiếu cấu trúc | Theo dõi tải, tra SQL/session, điều tra chờ, giới hạn tài nguyên |
| Hiểu nhầm cần tránh | “Static nghĩa là không đổi sau DDL” | “Một truy vấn V$ cho lịch sử đầy đủ và ảnh chụp nhất quán mọi thời điểm” |

## 2. Data dictionary: metadata do Oracle quản lý

Ví dụ câu lệnh:

```sql
CREATE TABLE orders (
    order_id   NUMBER PRIMARY KEY,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

Sau khi tạo bảng thành công, Oracle lưu thông tin cần thiết để biết object `ORDERS` thuộc user/schema nào, có những cột và kiểu dữ liệu gì, constraint nào được khai báo, object có trạng thái ra sao và được quản lý lưu trữ thế nào. Ứng dụng hoặc công cụ IDE **không cần tự đọc các bảng nền của `SYS`**; có thể đọc metadata qua view được Oracle hỗ trợ.

Chẳng hạn, account sở hữu bảng có thể kiểm tra:

```sql
SELECT table_name
FROM user_tables
WHERE table_name = 'ORDERS';

SELECT column_name, data_type, nullable
FROM user_tab_columns
WHERE table_name = 'ORDERS'
ORDER BY column_id;
```

Các tên object được tạo **không đặt trong dấu ngoặc kép** thường được Oracle chuẩn hóa thành chữ hoa trong dictionary; vì vậy điều kiện `WHERE table_name = 'ORDERS'` thường phù hợp cho bảng `orders` được tạo như ví dụ. Object tạo bằng quoted identifier có thể giữ chữ hoa/chữ thường đặc biệt; khi đó phải dùng đúng tên thực tế.

### 2.1. Dictionary không chỉ chứa danh sách bảng

| Loại thông tin | Một số view thường dùng | Ý nghĩa |
|---|---|---|
| Object/schema | `USER_OBJECTS`, `ALL_OBJECTS`, `DBA_OBJECTS` | Bảng, view, package, index, sequence, thời điểm DDL, trạng thái object |
| Bảng/cột | `USER_TABLES`, `ALL_TABLES`, `USER_TAB_COLUMNS`, `ALL_TAB_COLUMNS` | Định nghĩa và thuộc tính bảng/cột nằm trong phạm vi được nhìn thấy |
| Constraint | `USER_CONSTRAINTS`, `USER_CONS_COLUMNS`, `ALL_CONSTRAINTS` | Primary key, unique, foreign key, check và các cột tham gia |
| Index | `USER_INDEXES`, `USER_IND_COLUMNS`, `DBA_INDEXES` | Tên index, tính unique, cột/thứ tự cột và thuộc tính index |
| View và mã PL/SQL | `USER_VIEWS`, `USER_SOURCE`, `ALL_SOURCE`, `USER_ERRORS` | Định nghĩa hoặc thông tin lỗi biên dịch của object có quyền xem |
| User/role/grant | `DBA_USERS`, `DBA_ROLES`, `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS`, `DBA_TAB_PRIVS` | Danh tính, role, system/object privileges và role membership |
| Storage | `DBA_TABLESPACES`, `DBA_DATA_FILES`, `DBA_SEGMENTS`, `DBA_EXTENTS`, `DBA_FREE_SPACE` | Tablespace, datafile, dung lượng segment/extent và không gian chưa cấp |
| Metadata nhiều PDB | `CDB_OBJECTS`, `CDB_USERS`, `CDB_TABLES` | Thêm thông tin container để quan sát nhiều PDB theo quyền từ root |

Không phải view nào cũng có đầy đủ mọi biến thể tiền tố. Hãy dùng tài liệu Oracle hoặc danh mục view thực tế để tìm đúng tên và cột cho phiên bản đang chạy, thay vì tự ghép `USER_` với bất kỳ hậu tố nào.

### 2.2. Không cập nhật trực tiếp bảng nền dictionary

Các thao tác hợp lệ để thay đổi metadata là **DDL** và các API quản trị được Oracle hỗ trợ, ví dụ `CREATE TABLE`, `ALTER TABLE`, `CREATE USER`, `GRANT` hoặc các gói quản trị phù hợp. Không dùng `INSERT`, `UPDATE` hoặc `DELETE` trực tiếp vào bảng nền do `SYS` sở hữu để “sửa dictionary”. Việc can thiệp kiểu đó có thể phá tính toàn vẹn và khả năng hỗ trợ của database.

Nhiều lệnh Oracle DDL thông thường thực hiện **implicit commit**. Vì thế migration làm thay đổi dictionary cần được kiểm thử và triển khai có kiểm soát; không giả định có thể hoàn tác toàn bộ bằng `ROLLBACK` như một giao dịch DML.

## 3. Các nhóm static dictionary view: `USER_`, `ALL_`, `DBA_`, `CDB_`

### 3.1. `USER_*`: những object thuộc schema hiện tại

Đây là điểm bắt đầu thuận tiện cho developer khi khám phá **đối tượng mình sở hữu**. Nhiều view `USER_*` không có cột `OWNER`, vì chủ sở hữu đã được xác định theo ngữ cảnh của user/schema tương ứng.

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_type IN ('TABLE', 'VIEW', 'PACKAGE', 'INDEX')
ORDER BY object_type, object_name;
```

`STATUS` có ý nghĩa với từng loại object, ví dụ `VALID`/`INVALID` với view hoặc package khi Oracle xác định trạng thái biên dịch/phụ thuộc. `LAST_DDL_TIME` không phải “thời điểm sửa dòng dữ liệu cuối cùng”: DML như `UPDATE` bảng không nhất thiết thay đổi thời điểm DDL của object.

```sql
SELECT table_name, tablespace_name, partitioned
FROM user_tables
ORDER BY table_name;
```

`USER_TABLES` giúp trả lời bảng nào tồn tại trong schema thuộc phạm vi view. Nếu một table được tạo nhưng chưa có segment do deferred segment creation, bảng vẫn có thể hiện diện trong `USER_TABLES` trong khi chưa có dòng tương ứng trong `USER_SEGMENTS`.

### 3.2. `ALL_*`: những object user được phép nhìn/truy cập

Nhóm `ALL_*` phục vụ câu hỏi: **“Trong container này, object nào nằm trong phạm vi truy cập của tài khoản đang dùng?”** Nó có thể bao gồm object thuộc schema khác mà user được cấp quyền hoặc được Oracle cho phép thấy, không có nghĩa user sở hữu tất cả các object đó.

```sql
SELECT owner, table_name
FROM all_tables
WHERE owner = 'APP_OWNER'
ORDER BY table_name;
```

```sql
SELECT owner, table_name, column_name, data_type, nullable
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

Điều kiện `OWNER` rất hữu ích khi nhiều schema có bảng trùng tên. Lưu ý: việc một object hiện diện trong `ALL_*` **không bảo đảm mọi thao tác trên object đều được phép**. User có thể chỉ được `SELECT`, chỉ được `EXECUTE` package, hoặc truy cập được thông qua một cơ chế quyền cụ thể. Muốn biết quyền thao tác, phải xem grant và ngữ cảnh SQL thực thi.

### 3.3. `DBA_*`: metadata rộng trong container đang kết nối

Nhóm `DBA_*` cung cấp phạm vi quan sát rộng hơn, thường dành cho DBA hoặc tài khoản được cấp quyền catalog phù hợp:

```sql
-- Dành cho người có quyền đọc dictionary tương ứng.
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'APP_OWNER'
ORDER BY object_type, object_name;
```

Không phải tên `DBA_` có nghĩa chỉ account mang role `DBA` mới được truy vấn; quyền được quyết định bởi privilege/grant cụ thể và chính sách Oracle. Ngược lại, một tài khoản ứng dụng thông thường **không nên được cấp `DBA`** chỉ để liệt kê một bảng.

Trong kiến trúc **CDB/PDB**, khi chạy tại PDB A, `DBA_*` chủ yếu mô tả metadata trong **container A**. Truy vấn `DBA_OBJECTS` ở PDB A không mặc nhiên liệt kê đầy đủ mọi object ở PDB B. Để quan sát nhiều container từ root, Oracle cung cấp nhóm `CDB_*`.

### 3.4. `CDB_*`: dictionary view có chiều container

Ở `CDB$ROOT`, DBA có thể dùng view `CDB_*` để quan sát dữ liệu metadata của nhiều container theo quyền truy cập và khả năng hiển thị được Oracle cho phép. Các view này thường có thêm **`CON_ID`** để xác định nơi chứa dòng metadata.

```sql
-- Chạy từ CDB$ROOT bằng account có quyền thích hợp.
SELECT con_id, owner, object_name, object_type, status
FROM cdb_objects
WHERE owner = 'APP_OWNER'
  AND object_type = 'TABLE'
ORDER BY con_id, object_name;
```

Nếu `APP_OWNER.ORDERS` tồn tại ở hai PDB, hai dòng có thể có cùng `OWNER`, `OBJECT_NAME` nhưng **khác `CON_ID`**. Không ghép hoặc so sánh metadata nhiều PDB chỉ dựa vào tên object.

Một số ý nghĩa thường gặp của `CON_ID`:

| `CON_ID` | Diễn giải |
|---|---|
| `0` | Dòng mang ý nghĩa ở phạm vi toàn CDB hoặc không gắn một container đơn lẻ, tùy view |
| `1` | `CDB$ROOT` |
| `2` | `PDB$SEED` trong kiến trúc CDB thường gặp |
| `3` trở lên | Các PDB hoặc container khác theo catalog hiện tại |

Không nên hard-code rằng `CON_ID = 3` luôn là PDB ứng dụng tên cụ thể. Khi thao tác quản trị, đối chiếu `CON_ID` với catalog container do DBA cung cấp; việc thấy hoặc không thấy PDB trong kết quả còn phụ thuộc quyền, trạng thái và phiên bản Oracle.

### 3.5. Bảng phân biệt phạm vi truy cập

| Tiền tố | Phạm vi cần hình dung | Tình huống áp dụng |
|---|---|---|
| `USER_` | Object/schema của user đang làm việc trong container hiện tại | Developer tự xem bảng, cột, index của schema |
| `ALL_` | Object mà user hiện tại có thể nhìn/truy cập theo quyền | Developer kiểm tra bảng hoặc view ở schema khác |
| `DBA_` | Metadata rộng trong container hiện tại, cần quyền catalog | DBA rà soát user, object, tablespace và grant |
| `CDB_` | Metadata nhiều container từ root với cột `CON_ID`, phụ thuộc quyền | DBA so sánh các PDB hoặc kiểm tra common/local user |

**Lưu ý:** phạm vi *schema*, *container* và *quyền nhìn metadata* là ba yếu tố khác nhau. Một user có thể có cùng tên ở nhiều PDB nhưng là các **local user độc lập**; truy vấn từ PDB này không tự có quyền xem PDB khác.

## 4. Tự khám phá static dictionary view và cột của chúng

Không cần nhớ thuộc lòng hàng trăm view. Oracle cung cấp những cơ chế khám phá metadata của chính dictionary.

### 4.1. Tìm view qua `DICTIONARY` hoặc `DICT`

```sql
SELECT table_name, comments
FROM dictionary
WHERE table_name IN (
    'USER_OBJECTS', 'ALL_TABLES', 'DBA_OBJECTS', 'V$SESSION'
)
ORDER BY table_name;
```

`DICTIONARY` (thường có synonym `DICT`) liệt kê các dictionary view/table cùng mô tả mà account được phép thấy theo phạm vi của Oracle. Việc một tên xuất hiện trong danh mục không phải bảo đảm user có quyền đọc toàn bộ dữ liệu của view đó; hãy thử truy vấn được cấp phép hoặc hỏi DBA.

```sql
SELECT table_name, column_name, comments
FROM dict_columns
WHERE table_name = 'USER_OBJECTS'
ORDER BY column_name;
```

`DICT_COLUMNS` giúp tìm tên cột và mô tả. Cũng có thể dùng chức năng **Describe** của SQLcl/SQL*Plus/SQL Developer hoặc metadata API của JDBC. Khi học một bản phát hành Oracle cụ thể, nên đối chiếu tên view/cột thực tế vì các phiên bản có thể thêm cột hoặc thay đổi khả năng hiển thị.

### 4.2. Xem định nghĩa object bằng API được hỗ trợ

Để lấy DDL của object do mình sở hữu, có thể dùng `DBMS_METADATA.GET_DDL` nếu được cấp quyền phù hợp:

```sql
SELECT DBMS_METADATA.GET_DDL('TABLE', 'ORDERS', USER)
FROM dual;
```

Kết quả là nội dung DDL dạng `CLOB` và có thể chứa thuộc tính lưu trữ; format phụ thuộc tùy chọn của package/công cụ. Đây là API đọc metadata, không phải đọc trực tiếp cấu trúc bảng nền dictionary. Khi dùng cho schema khác, quyền và chính sách bảo vệ metadata phải được tôn trọng.

## 5. Đọc metadata của một schema từ bảng đến constraint và index

Giả sử ứng dụng có bảng `APP_OWNER.ORDERS`. Lập trình viên cần hiểu ranh giới dữ liệu trước khi thay đổi migration. Các truy vấn sau chỉ đọc và dùng `ALL_*` để có thể làm việc với một object thuộc schema khác trong phạm vi đã được cấp quyền.

### 5.1. Tìm cột và kiểu dữ liệu

```sql
SELECT column_id, column_name, data_type,
       data_length, data_precision, data_scale, nullable
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'ORDERS'
ORDER BY column_id;
```

Không chỉ nhìn `DATA_TYPE`: với `NUMBER`, cần chú ý `DATA_PRECISION`/`DATA_SCALE`; với `VARCHAR2`, cần xem length semantics và độ dài. Đừng suy diễn đơn giản rằng `DATA_LENGTH` luôn là số ký tự người dùng có thể nhập, vì nó có thể thể hiện **byte** trong khi cột dùng ngữ nghĩa `CHAR`.

### 5.2. Đọc constraint

```sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.column_name,
       cc.position,
       c.r_constraint_name
FROM all_constraints c
LEFT JOIN all_cons_columns cc
  ON cc.owner = c.owner
 AND cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.owner = 'APP_OWNER'
  AND c.table_name = 'ORDERS'
ORDER BY c.constraint_name, cc.position;
```

Một số loại `CONSTRAINT_TYPE` thường gặp: `P` (primary key), `R` (referential/foreign key), `U` (unique), `C` (check, bao gồm những ràng buộc kiểm tra liên quan `NOT NULL`), v.v. Với foreign key, `R_CONSTRAINT_NAME` trỏ đến constraint được tham chiếu; phải kết hợp **owner** và metadata tương ứng để định vị đúng object, nhất là khi nhiều schema có tên constraint giống nhau.

`STATUS` và `VALIDATED` cho biết những đặc tính khác nhau: constraint có đang được enable và dữ liệu trước đó đã được xác nhận đáp ứng constraint chưa. Không mặc định rằng một constraint có tên là luôn đang được thực thi theo cách bạn tưởng.

### 5.3. Đọc index và thứ tự cột

```sql
SELECT i.owner, i.index_name, i.uniqueness,
       ic.column_name, ic.column_position
FROM all_indexes i
JOIN all_ind_columns ic
  ON ic.index_owner = i.owner
 AND ic.index_name = i.index_name
WHERE i.table_owner = 'APP_OWNER'
  AND i.table_name = 'ORDERS'
ORDER BY i.index_name, ic.column_position;
```

Thứ tự cột có thể quyết định khả năng phục vụ truy vấn của composite index. Ví dụ `(CUSTOMER_ID, CREATED_AT)` không hoàn toàn tương đương `(CREATED_AT, CUSTOMER_ID)`. Metadata cho biết **index được định nghĩa thế nào**; có dùng index trong một câu SQL cụ thể hay không còn phụ thuộc optimizer, statistics, phân bố dữ liệu và execution plan.

### 5.4. Hiểu giới hạn của thống kê trong dictionary

Một số view `USER_TABLES`/`DBA_TABLES` có các cột như `NUM_ROWS` và `LAST_ANALYZED`. `NUM_ROWS` thông thường là **optimizer statistics ở lần thu thập gần nhất**, không phải bộ đếm hàng luôn được cập nhật ngay sau mỗi `INSERT`/`DELETE`.

```sql
SELECT table_name, num_rows, last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
```

Nếu vừa insert 10.000 dòng nhưng `NUM_ROWS` chưa đổi, không được kết luận insert thất bại. Để kiểm tra số dòng chính xác theo ngữ nghĩa đọc nhất quán của giao dịch hiện tại, có thể chạy `SELECT COUNT(*)` trên bảng nếu có quyền, với lưu ý rằng quét bảng lớn có chi phí tài nguyên đáng kể. Kết quả dictionary statistics và số liệu runtime phục vụ những mục đích khác nhau.

## 6. Dynamic performance view: quan sát Oracle đang chạy

Nhóm dynamic performance view thường có tiền tố **`V$`**. Ví dụ:

- `V$INSTANCE`: trạng thái và danh tính instance, thời điểm startup.
- `V$DATABASE`: thông tin database và một số trạng thái vận hành quan trọng.
- `V$SESSION`: session, user, trạng thái, sự kiện chờ và SQL liên quan.
- `V$SQL`: SQL cursor trong shared SQL area, số lần thực thi và thống kê liên quan.
- `V$SQL_PLAN`: thông tin plan của cursor có trong cache theo SQL ID/child.
- `V$PARAMETER`: giá trị tham số instance/session hiện đang có hiệu lực theo ngữ cảnh view.
- `V$RESOURCE_LIMIT`: mức sử dụng hiện tại/cao nhất và giới hạn của một số tài nguyên.
- `V$SESSION_EVENT`, `V$SYSTEM_EVENT`: thống kê wait event được tích lũy theo phạm vi tương ứng.
- `V$LOCK`: thông tin lock/đề nghị lock có thể hỗ trợ điều tra blocking.

Không phải dynamic view nào cũng chứa “giá trị thời điểm hiện tại” theo cùng cách: có view phản ánh trạng thái đang tồn tại, có view chứa thống kê từ khi session/cursor/instance bắt đầu. Các giá trị có thể đổi giữa hai lần `SELECT`; **nhiều cột không tạo thành một snapshot đồng bộ tuyệt đối** của cả hệ thống.

### 6.1. Nhìn instance đang hoạt động

```sql
-- Cần quyền đọc dynamic performance view tương ứng.
SELECT instance_name, host_name, status, startup_time
FROM v$instance;
```

Thông tin này hữu ích khi xác định instance vừa restart hoặc ứng dụng đang truy cập vào môi trường nào. `STARTUP_TIME` không phải ngày tạo database và không cho biết trực tiếp PDB cụ thể đã mở lúc nào. Trong Oracle RAC, một CDB/database có thể có **nhiều instance** trên nhiều node.

### 6.2. Quan sát session ứng dụng

```sql
SELECT sid, serial#, username, status,
       sql_id, wait_class, event, con_id
FROM v$session
WHERE username = 'APP_RUNTIME'
ORDER BY sid;
```

Một session được nhận dạng thực tế bằng các thông tin như **instance**, `SID` và `SERIAL#`, không chỉ bởi `SID` đơn lẻ. Session có thể đổi SQL hoặc kết thúc ngay sau thời điểm truy vấn. `STATUS = 'ACTIVE'` không có nghĩa chắc chắn session đang tiêu thụ CPU liên tục: nó có thể đang thực hiện một database call và phải chờ I/O/lock/network. Trường `EVENT` khi session không đang chờ có thể phản ánh sự kiện chờ gần đây; cần đọc thêm trạng thái wait và bối cảnh trước khi kết luận.

`V$SESSION` giúp trả lời “những session nào đang tồn tại, thuộc account nào, đang gắn với SQL nào?”. Nó **không tự nói được nguyên nhân gốc** của mọi yêu cầu API chậm; nên ghép với log/trace và thông tin connection pool của ứng dụng.

### 6.3. Quan sát SQL cursor và mức tiêu thụ tương đối

```sql
-- Mã ví dụ chỉ dùng khi đã được cấp quyền chẩn đoán.
SELECT sql_id,
       child_number,
       executions,
       buffer_gets,
       disk_reads,
       ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds
FROM v$sql
WHERE parsing_schema_name = 'APP_RUNTIME'
ORDER BY elapsed_time DESC
FETCH FIRST 10 ROWS ONLY;
```

`ELAPSED_TIME` ở đây được trình bày theo **microsecond** trong nhiều phiên bản Oracle, nên ví dụ chia cho `1.000.000` để biểu diễn giây. Đây là **thời gian tích lũy liên quan cursor**, không phải thời lượng của một lần chạy gần nhất. `EXECUTIONS` cho biết số lần thực thi được ghi nhận theo cursor tương ứng; dữ liệu có thể thay đổi khi cursor được load lại, bị aged out khỏi shared pool, hoặc instance restart. SQL ID có thể có nhiều **child cursor** với plan/thống kê khác nhau; không cộng hoặc chia số liệu một cách tùy tiện nếu chưa xét ranh giới này.

Thông tin SQL trong view có thể bao gồm **SQL text và literal chứa dữ liệu nhạy cảm**. Chỉ đọc/trích xuất những trường cần thiết, tránh đưa nguyên văn câu SQL của người dùng vào ticket/chat không có quyền kiểm soát. Những thống kê `V$SQL` không phải lịch sử vô hạn: một câu SQL cũ có thể không còn trong shared pool.

### 6.4. Xem cấu hình và giới hạn tài nguyên hiện tại

```sql
SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name IN ('open_cursors', 'sessions', 'processes')
ORDER BY name;
```

```sql
SELECT resource_name,
       current_utilization,
       max_utilization,
       limit_value
FROM v$resource_limit
WHERE resource_name IN ('sessions', 'processes')
ORDER BY resource_name;
```

Một ứng dụng gặp vấn đề tạo connection có thể cần đối chiếu số connection pool nhân với số replica với giới hạn database. Tuy nhiên `CURRENT_UTILIZATION` hoặc một thời điểm sử dụng cao không tự chứng minh nguyên nhân mất kết nối; vẫn phải kiểm tra mã ORA, log và workload. Việc sửa tham số instance cần DBA thực hiện theo quy trình thay đổi, không phải trách nhiệm tự động của developer.

### 6.5. Khi nào dùng `V$SQL_PLAN`?

Nếu đã có `SQL_ID` của câu SQL trong cache, có thể kiểm tra plan/cursor liên quan hoặc dùng `DBMS_XPLAN.DISPLAY_CURSOR` khi được cấp quyền phù hợp. Execution plan cho biết Oracle dự kiến/thực hiện đường truy cập như thế nào theo dữ liệu quan sát của công cụ, nhưng **plan của một cursor không giải thích mọi lần thực thi** hoặc thay thế việc đối chiếu dữ liệu, bind, thống kê, phiên bản SQL và wait event. Những thủ tục/option chẩn đoán sâu có thể có điều kiện quyền và cấp phép riêng.

## 7. `V$` và `GV$`: một instance và nhiều instance

Trong Oracle Real Application Clusters (**RAC**), một database có thể được nhiều instance phục vụ đồng thời. **`V$...`** tập trung vào dữ liệu dynamic view theo ngữ cảnh instance đang kết nối; **`GV$...`** (*global dynamic performance view*) thường hợp nhất thông tin tương ứng từ các instance và thêm cột **`INST_ID`**.

```text
            ORACLE RAC DATABASE
          +---------------------+
          |                     |
   Instance 1              Instance 2
      SID 25                  SID 25
      SID 46                  SID 81
          |                     |
      V$SESSION             V$SESSION
          \                     /
           \                   /
             GV$SESSION
        INST_ID + SID + SERIAL#
```

`SID = 25` có thể xuất hiện ở **hai instance khác nhau**; khi điều tra một session RAC, cần xem `INST_ID` cùng `SID`/`SERIAL#` và container nếu phù hợp.

```sql
SELECT inst_id, sid, serial#, username,
       status, sql_id, event, con_id
FROM gv$session
WHERE username = 'APP_RUNTIME'
ORDER BY inst_id, sid;
```

Không phải database nào cũng triển khai RAC. Trên hệ thống single-instance, `GV$` có thể vẫn có ý nghĩa nhưng việc đọc `INST_ID` không mang lại cấu trúc nhiều node thực tế. Một số dynamic view không có đối ứng hoặc cột hoàn toàn giống nhau giữa mọi phiên bản; phải xem catalog của phiên bản đang sử dụng.

### 7.1. `CON_ID` khác `INST_ID`

| Cột | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| `CON_ID` | Dòng metadata/runtime này thuộc **container/PDB nào**? | PDB `SALES_APP` có `CON_ID = 4` trong CDB đang xét |
| `INST_ID` | Dòng runtime được thu thập từ **instance nào**? | Instance RAC số `1` hoặc `2` |
| `SID` + `SERIAL#` | Session cụ thể trong instance ở thời điểm quan sát? | Kết hợp với `INST_ID` trong RAC |
| `OWNER`, `USERNAME` | Đối tượng/schema hoặc tài khoản nào? | `APP_OWNER`, `APP_RUNTIME` |

**CDB/PDB và RAC là hai trục khác nhau.** Một PDB có thể được phục vụ qua nhiều instance RAC; một instance cũng có thể phục vụ nhiều PDB. Vì vậy điều tra nên nêu đủ **PDB, instance, session, SQL ID và mốc thời gian** thay vì chỉ một ID.

## 8. Metadata và số liệu động trong môi trường CDB/PDB

Với kiến trúc multitenant, developer thường kết nối thẳng vào **service của PDB ứng dụng**. Trong khi đó, DBA có thể làm việc tại `CDB$ROOT` để quan sát nhiều PDB. Cùng một view có thể trả về phạm vi và số dòng khác nhau tùy container, quyền và cách Oracle triển khai view đó.

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

Truy vấn xác minh session này nên chạy **trước khi diễn giải kết quả** từ `DBA_*` hay `V$...`. Nếu user đang ở PDB A, một kết quả `DBA_OBJECTS` thiếu bảng thuộc PDB B có thể là hành vi hoàn toàn đúng.

Một DBA ở root có quyền phù hợp có thể xem container:

```sql
-- Ví dụ từ CDB$ROOT, tùy quyền và phiên bản.
SELECT con_id, name, open_mode
FROM v$pdbs
ORDER BY con_id;
```

Khi đặt truy vấn metadata từ `CDB_OBJECTS` cạnh truy vấn session từ `GV$SESSION`, cần **join hoặc nhóm theo đúng các khóa phù hợp**, không join mọi thứ chỉ bằng `USERNAME` hay `OBJECT_NAME`. Một bảng `ORDERS` ở PDB A và bảng `ORDERS` ở PDB B là hai đối tượng khác nhau mặc dù tên giống nhau.

Để tránh nhầm bối cảnh, báo cáo kỹ thuật nên ghi:

```text
Environment: TEST
Database service: order_test_service
Container/PDB: ORDER_TEST_PDB
Instance: instance_1
Schema owner: ORDER_OWNER
Session user: ORDER_RUNTIME
Observed at: 2026-11-14 10:20 +07
```

Thông tin là ví dụ minh họa. Không ghi credential, mật khẩu, wallet hoặc SQL có dữ liệu nhạy cảm trong báo cáo.

## 9. Quyền truy cập dictionary và dynamic view

Có thể truy vấn metadata **không có nghĩa được truy cập toàn bộ catalog**. Oracle giới hạn quyền để tránh lộ thông tin cấu trúc database, user, SQL text hoặc trạng thái session của ứng dụng khác.

| Tài khoản | Nhu cầu điển hình | Đường truy cập thích hợp |
|---|---|---|
| Developer/schema owner | Kiểm tra bảng, cột, index và constraint của mình | `USER_*`, `ALL_*` trong phạm vi được grant |
| Ứng dụng runtime | Chạy SQL nghiệp vụ | Thường không cần quyền đọc `DBA_*`, `V$SQL` hay `V$SESSION` toàn hệ thống |
| CI/migration identity | Đối chiếu schema version và tính hợp lệ sau migration | `USER_*` hoặc metadata cụ thể theo quyền có kiểm soát |
| Monitoring account | Thu thập số liệu instance/session/tài nguyên đã định nghĩa | Chỉ cấp `SELECT` trên những dynamic view cần thiết theo chính sách |
| DBA/on-call được ủy quyền | Điều tra metadata rộng, session, wait, tài nguyên | Quyền catalog/chẩn đoán tương ứng, audit và thời hạn truy cập phù hợp |

### 9.1. Tên view công khai không đồng nghĩa quyền công khai

Tên `V$SESSION` thường được cung cấp qua synonym, nhưng user không được grant thích hợp có thể gặp `ORA-00942` hoặc lỗi quyền khi truy vấn. Đây không phải bằng chứng rằng database thiếu view đó. DBA có thể cấp quyền đọc đúng view gốc (ví dụ **`SYS.V_$SESSION`**) hoặc một cơ chế vai trò/catalog thích hợp cho identity giám sát đã được phê duyệt; chi tiết cấp quyền còn phụ thuộc phiên bản và chính sách.

Các đặc quyền rộng như **`SELECT ANY DICTIONARY`**, role như **`SELECT_CATALOG_ROLE`** hoặc quyền quản trị `DBA` mở ra phạm vi đáng kể. Không cấp cho tài khoản web application chỉ để khắc phục một câu query chẩn đoán. Trong PL/SQL **definer-rights**, các quyền qua role thường không thay thế direct grant khi biên dịch và thực thi; cần kiểm tra ngữ cảnh quyền thực tế.

### 9.2. Metadata cũng có thể là thông tin nhạy cảm

Một số view có thể để lộ:

- Tên account, host, chương trình kết nối, service và sơ đồ phân quyền.
- SQL text hoặc bind/literal thể hiện định danh, dữ liệu cá nhân hoặc câu lệnh chứa bí mật.
- Topology, số session, resource limit, trạng thái hệ thống và hành vi workload.
- Thông tin object/schema mà chủ hệ thống không muốn chia sẻ qua môi trường DEV/TEST.

Vì vậy, khi thu thập log/ticket chỉ xuất **mã lỗi, metric, SQL ID, thời điểm, môi trường và số liệu thật sự cần thiết**. Không dump toàn bộ `V$SQL.SQL_FULLTEXT`, password, secret hoặc file cấu hình nhạy cảm ra báo cáo chung.

### 9.3. Cân nhắc tính năng và cấp phép chẩn đoán

Các dynamic performance view cơ bản và những tính năng chẩn đoán lịch sử/chuyên sâu **không đồng nghĩa về quyền sử dụng/cấp phép**. Chẳng hạn, AWR, ASH hoặc các khả năng tuning có thể phụ thuộc Oracle Diagnostics Pack/Tuning Pack và edition/điều khoản sử dụng. Đừng tự chạy báo cáo/feature chuyên sâu chỉ vì có thể nhìn thấy tên view/package. Hãy xác nhận quyền và license với DBA hoặc bộ phận quản lý Oracle trước khi dùng.

## 10. Kết hợp static và dynamic view để điều tra vấn đề

Một sự cố Oracle thường cần cả thông tin **“object là gì?”** và **“session đang làm gì?”**. Hai nhóm view hỗ trợ lẫn nhau, nhưng không thay thế dữ liệu từ log ứng dụng, connection pool, network hoặc trace.

### Tình huống A — `ORA-00942` khi chạy câu SQL nghiệp vụ

Ứng dụng đăng nhập thành công nhưng `SELECT * FROM APP_OWNER.ORDERS` báo `ORA-00942: table or view does not exist`.

1. Developer kiểm tra tên schema/table đã được khai báo và migration đã tạo object chưa.
2. Kiểm tra `ALL_TABLES`/`ALL_OBJECTS` từ **đúng account runtime và PDB** để biết object có hiện trong phạm vi user không.
3. DBA/chủ schema đối chiếu `DBA_OBJECTS`/object grants nếu user thường không thấy object; kiểm tra synonym nếu câu SQL không chỉ rõ owner.
4. Đối chiếu quyền `SELECT` thích hợp; không dùng tài khoản `SYS` để chứng minh account runtime có quyền.

Đây chủ yếu là **bài toán metadata và phân quyền**, không phải vấn đề CPU hay wait event. `V$SESSION` chỉ có thể hỗ trợ xác nhận session, không sửa được object chưa tồn tại hoặc grant thiếu.

### Tình huống B — Package bị `INVALID` sau migration

Sau khi thay một bảng hoặc cột, ứng dụng không gọi được PL/SQL package và có lỗi biên dịch/phụ thuộc.

```sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'ORDER_SERVICE_PKG';

SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'ORDER_SERVICE_PKG'
ORDER BY sequence;
```

`USER_OBJECTS`/`USER_ERRORS` giúp kiểm tra trạng thái object và thông tin lỗi trong schema sở hữu. Developer rà soát thay đổi DDL, dependency và quyền trực tiếp cần cho definer-rights PL/SQL. Những view dynamic về session có thể hỗ trợ đánh giá mức độ ảnh hưởng runtime, nhưng **nguyên nhân của object invalid nằm ở định nghĩa/phụ thuộc và quyền**.

### Tình huống C — API chậm và session có wait event

Ứng dụng báo độ trễ tăng sau release. Hướng điều tra:

```text
Application logs/metrics
  -> request ID, SQL ID nếu có, connection pool, release
             |
             v
V$SESSION / GV$SESSION
  -> session nào, SQL_ID nào, wait/event/instance/PDB
             |
             v
V$SQL / execution plan
  -> cursor, số lần chạy, buffer_gets, elapsed_time, plan
             |
             v
USER_/ALL_/DBA_ metadata
  -> index có tồn tại, constraint, schema, thống kê/DDL
             |
             v
Đưa ra giả thuyết và xác minh bằng đo đạc
```

Ví dụ, nếu `V$SESSION` cho thấy nhiều session của ứng dụng liên quan cùng SQL ID và wait trên I/O, developer có thể kiểm tra predicate, tần suất truy vấn và index. DBA dùng static dictionary để xác minh index thực sự tồn tại, trạng thái và thống kê; dùng dynamic view để xem các wait/resource. **Có wait I/O không tự chứng minh thiếu index**, và có index cũng không có nghĩa optimizer buộc phải dùng nó.

### Tình huống D — Kết nối mới lỗi do giới hạn session

Developer thấy pool timeout hoặc Oracle báo lỗi liên quan khả năng tạo session. DBA có thể nhìn `V$RESOURCE_LIMIT` để biết mức `sessions`/`processes`, và `V$SESSION`/`GV$SESSION` để đánh giá số session theo account/instance. Đồng thời operations kiểm tra replica, autoscale và retry; developer kiểm tra connection leak và pool size. `DBA_USERS`/dictionary có thể xác định account, profile hoặc quyền, nhưng **không đại diện trực tiếp cho số session đang hoạt động**.

### Tình huống E — Một PDB có bảng giống tên nhưng cấu trúc khác

Trong CDB, cùng tên `APP_OWNER.ORDERS` xuất hiện ở PDB DEV và TEST. Một migration bị sót tại TEST, dẫn đến thiếu cột.

DBA truy vấn `CDB_OBJECTS` hoặc metadata cột theo container để so sánh **`CON_ID` + `OWNER` + `OBJECT_NAME`**; developer xác nhận schema version bằng công cụ migration và chạy test đúng service PDB. Không dùng một kết quả `DBA_TAB_COLUMNS` ở root để kết luận cấu trúc mọi PDB đều giống nhau.

## 11. Bài thực hành: đọc dictionary rồi quan sát session

Bài lab có hai phần. **Phần A** chạy bằng user được quyền tạo bảng trong **DEV/PDB lab**; **phần B** đọc dynamic view, cần DBA cấp quyền chẩn đoán phù hợp. Không thực thi DDL trên production, không tự cấp quyền `DBA`/`SYSDBA` cho tài khoản lab.

### Phần A — Tạo object nhỏ và quan sát static dictionary

**Bước 1.** Xác minh container/user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

**Bước 2.** Trong một schema lab được cấp quota và quyền `CREATE TABLE`, tạo hai bảng có quan hệ:

```sql
CREATE TABLE lab_customers_meta (
    customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    full_name   VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_lab_customers_meta PRIMARY KEY (customer_id)
);

CREATE TABLE lab_orders_meta (
    order_id    NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id NUMBER NOT NULL,
    status      VARCHAR2(12 CHAR) DEFAULT 'NEW' NOT NULL,
    created_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_orders_meta PRIMARY KEY (order_id),
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers_meta (customer_id),
    CONSTRAINT ck_lab_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE INDEX ix_lab_orders_customer
    ON lab_orders_meta (customer_id);
```

Script này dành riêng cho schema chưa có các object lab cùng tên. Nếu đã chạy trước đó, không tự xóa bảng để làm lại khi chưa xác nhận dữ liệu đang thuộc bài lab của mình. Một primary key có thể tạo index hỗ trợ ràng buộc; vì vậy khi quan sát `USER_INDEXES`, số index không nhất thiết bằng số câu `CREATE INDEX` tự viết.

**Bước 3.** Quan sát bảng, cột và constraint:

```sql
SELECT table_name
FROM user_tables
WHERE table_name IN ('LAB_CUSTOMERS_META', 'LAB_ORDERS_META')
ORDER BY table_name;

SELECT table_name, column_id, column_name,
       data_type, nullable
FROM user_tab_columns
WHERE table_name = 'LAB_ORDERS_META'
ORDER BY column_id;

SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'LAB_ORDERS_META'
ORDER BY constraint_name;
```

**Bước 4.** Xác định index và quan hệ khóa ngoại:

```sql
SELECT i.index_name, i.uniqueness,
       ic.column_name, ic.column_position
FROM user_indexes i
JOIN user_ind_columns ic
  ON ic.index_name = i.index_name
WHERE i.table_name = 'LAB_ORDERS_META'
ORDER BY i.index_name, ic.column_position;

SELECT c.constraint_name, c.r_constraint_name,
       cc.column_name, cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.table_name = 'LAB_ORDERS_META'
  AND c.constraint_type = 'R'
ORDER BY cc.position;
```

Ghi nhận tên PK, FK, CHECK, tên index và thứ tự cột. Các kết quả này là **metadata định nghĩa**, chưa có thông tin session hay hiệu năng. Bản thân việc đọc dictionary không cần insert dữ liệu thật vào bảng.

### Phần B — Quan sát dynamic performance view nếu được cấp quyền

**Bước 5.** Tạo một hoạt động đọc đơn giản:

```sql
SELECT COUNT(*) AS order_count
FROM lab_orders_meta;
```

Sau đó, từ phiên có quyền được DBA cấp, xem thông tin instance/session:

```sql
SELECT instance_name, startup_time
FROM v$instance;

SELECT sid, serial#, username, status,
       sql_id, event, con_id
FROM v$session
WHERE username = SYS_CONTEXT('USERENV', 'SESSION_USER')
ORDER BY sid;
```

Tùy cách DBA cấp quyền, tài khoản lab có thể không đọc được các view này; đó là **ranh giới bảo mật được mong đợi**. Nếu không có quyền, phần thực hành dừng tại đây và có thể yêu cầu DBA cung cấp một kết quả đã được làm sạch để thảo luận. Không cấp `SELECT ANY DICTIONARY` chỉ để hoàn thành bài lab.

`SQL_ID` trong `V$SESSION` có thể rỗng hoặc đã đổi khi bạn đọc vì session đang idle/đang chạy câu khác. Kể cả truy vấn `COUNT(*)` đã thực thi, không có bảo đảm bạn luôn quan sát được nó trong một hàng `V$SQL` ở một thời điểm bất kỳ do cursor cache và các điều kiện vận hành.

**Bước 6.** Ghi lại câu trả lời cho ba câu hỏi:

1. `USER_TAB_COLUMNS` cho biết dữ liệu **được định nghĩa như thế nào**, hay **đang được xử lý nhanh/chậm ra sao**?
2. Trong `V$SESSION`, đâu là **danh tính session**, đâu là **trạng thái vận hành biến động**?
3. Nếu các PDB cùng chứa bảng `LAB_ORDERS_META`, vì sao phải xác minh **container** trước khi so sánh metadata?

**Bước 7.** Khi được phép thu dọn trong đúng schema **DEV**, có thể xóa object lab theo thứ tự phụ thuộc:

```sql
-- Chỉ chạy khi xác nhận đây là dữ liệu lab có thể xóa.
DROP TABLE lab_orders_meta PURGE;
DROP TABLE lab_customers_meta PURGE;
```

`DROP` là DDL có thể ảnh hưởng trực tiếp đến dữ liệu và thường implicit commit. Không dùng câu lệnh này trên production hoặc khi object chứa dữ liệu ngoài phạm vi bài thực hành.

## 12. Mẫu truy vấn thường dùng cho developer và DBA

### 12.1. Truy vấn nào nên chọn trước?

| Nhu cầu | Nguồn đề xuất ban đầu | Cần chú ý |
|---|---|---|
| Liệt kê bảng trong schema của mình | `USER_TABLES` | Không cần quyền catalog rộng |
| Tìm cột của bảng thuộc schema khác đã được cấp quyền | `ALL_TAB_COLUMNS` | Lọc `OWNER` và `TABLE_NAME` |
| Kiểm tra object invalid | `USER_OBJECTS`, `USER_ERRORS`; hoặc `DBA_OBJECTS` nếu có quyền | Trạng thái metadata và lỗi biên dịch cần xem cùng dependency |
| Tìm foreign key / primary key | `USER_CONSTRAINTS`, `USER_CONS_COLUMNS` | Với FK cần tham chiếu constraint đích |
| Xem index của bảng | `USER_INDEXES`, `USER_IND_COLUMNS` | Có index không chứng minh optimizer sẽ dùng |
| So sánh object ở nhiều PDB | `CDB_OBJECTS`/view CDB tương ứng | Cần `CON_ID`, quyền root phù hợp |
| Xem session Oracle | `V$SESSION` | Session thay đổi nhanh; xem username/PDB/SQL ID |
| Xem session nhiều instance RAC | `GV$SESSION` | Đọc thêm `INST_ID` |
| Xem SQL đang nằm trong cursor cache | `V$SQL` | Không phải lịch sử đầy đủ; tránh lộ SQL text |
| Xem thông số instance | `V$PARAMETER` | Không tự chỉnh tham số từ quan sát một thời điểm |
| Xem tài nguyên session/process | `V$RESOURCE_LIMIT` | Phân biệt current/max với giới hạn cấu hình |

### 12.2. Kết hợp dữ liệu tại mốc thời gian

Thông tin từ các view nên đi cùng **thời điểm thu thập, service/PDB, instance, release ứng dụng và mục đích đo**. Ví dụ, một lần lấy `V$SQL` cho biết cursor đang ở shared pool, nhưng nếu bạn so sánh với metadata index từ sau khi migration hoàn tất thì hai nguồn có thể phản ánh **hai trạng thái khác thời điểm**. Khi chẩn đoán biến động theo thời gian, cần nhiều mẫu đo và đối chiếu log thay vì suy luận xu hướng từ một ảnh chụp.

### 12.3. `SELECT *` có nên dùng không?

Trong lab nhỏ, `SELECT *` có thể giúp khám phá một view, nhưng trên hệ thống lớn nên **chỉ chọn cột cần thiết, lọc phạm vi schema/PDB/user và giới hạn số dòng**. Những view như `V$SQL` có thể có nhiều dòng và cột dài chứa thông tin nhạy cảm. Một truy vấn dictionary rộng hoặc dashboard giám sát chạy quá thường xuyên cũng có chi phí tài nguyên. Chỉ lấy đúng dữ liệu cần thiết và bảo vệ đầu ra.

## 13. Những nhầm lẫn phổ biến

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Static dictionary view không bao giờ thay đổi.” | Metadata thay đổi sau DDL/quản trị; *static* chỉ phân biệt với trạng thái runtime động. |
| “`USER_TABLES` cho thấy mọi bảng user có thể query.” | Nó tập trung vào bảng của schema user; dùng `ALL_TABLES` để tìm bảng có thể nhìn/truy cập ở schema khác. |
| “`ALL_TABLES` là tất cả các bảng của CDB.” | Nó phụ thuộc quyền của account và phạm vi container. |
| “`DBA_OBJECTS` ở PDB A luôn thấy object của PDB B.” | Thường cần quan sát nhiều container từ root qua `CDB_*` và quyền phù hợp. |
| “Có `V$SESSION` là xem được lịch sử toàn bộ session từ trước.” | Dynamic view phản ánh trạng thái/metric theo vòng đời runtime; session đã kết thúc có thể không còn. |
| “`V$SQL.ELAPSED_TIME` là thời gian của lần query cuối.” | Đây thường là thống kê tích lũy cho cursor/child, không phải duration một request đơn lẻ. |
| “`V$SQL` luôn chứa mọi câu SQL đã chạy.” | Cursor có thể bị aged out hoặc mất khi restart; cần công cụ lịch sử/quan sát phù hợp nếu được phép. |
| “`V$SESSION.STATUS = ACTIVE` nghĩa là CPU đang 100%.” | Session có thể đang chờ I/O, lock hoặc sự kiện khác trong khi database call active. |
| “`GV$SESSION` và `V$SESSION` là hai tên giống nhau.” | `GV$` thêm chiều instance (`INST_ID`), đặc biệt hữu ích với RAC. |
| “`CON_ID` và `INST_ID` là cùng một ID.” | `CON_ID` là container/PDB; `INST_ID` là instance. |
| “`USER_TABLES.NUM_ROWS` luôn bằng `COUNT(*)`.” | `NUM_ROWS` thường là optimizer statistics thu thập trước đó, có thể stale. |
| “Có public synonym `V$SQL` thì mọi user đều được đọc.” | Synonym không cấp privilege; cần quyền phù hợp trên view. |
| “Role `DBA` là cách tiện nhất để dashboard lấy metric.” | Cấp quyền rộng làm tăng rủi ro; nên giới hạn những view và dữ liệu cần thiết. |
| “AWR/ASH giống các view V$ cơ bản nên dùng mặc định.” | Một số tính năng chẩn đoán có điều kiện license/quyền; phải xác nhận trước khi dùng. |

## 14. Câu hỏi ôn tập

**Câu 1.** Bạn cần biết bảng `CUSTOMER` trong schema của mình có những cột nào. Nên bắt đầu với `USER_TAB_COLUMNS` hay `V$SESSION`?

**Đáp án:** `USER_TAB_COLUMNS` vì đây là metadata cấu trúc cột; `V$SESSION` mô tả session đang hoạt động.

**Câu 2.** User ứng dụng có quyền `SELECT` trên bảng `REPORTS` của schema `REPORT_OWNER`, nhưng không sở hữu bảng. Nên kiểm tra `USER_TABLES` hay `ALL_TABLES`?

**Đáp án:** `ALL_TABLES` với điều kiện `OWNER = 'REPORT_OWNER'`; sự hiện diện phụ thuộc quyền. Với `USER_TABLES`, bạn chủ yếu thấy bảng của schema mình.

**Câu 3.** DBA đang ở `CDB$ROOT` muốn phân biệt bảng `ORDERS` trong hai PDB. Cần thêm yếu tố nào ngoài `OWNER` và `OBJECT_NAME`?

**Đáp án:** `CON_ID`/container, kết hợp view `CDB_*` và quyền phù hợp.

**Câu 4.** Một session có `SID = 125` ở instance RAC 1 và instance RAC 2. Đây có phải cùng một session?

**Đáp án:** Không thể kết luận như vậy. Cần `INST_ID`, `SID`, `SERIAL#` và thời điểm/container tương ứng.

**Câu 5.** Sau khi `INSERT` 500 dòng, `USER_TABLES.NUM_ROWS` vẫn có giá trị cũ. Có phải Oracle không lưu dữ liệu?

**Đáp án:** Không. `NUM_ROWS` có thể là statistics chưa được làm mới; kiểm tra transaction và dữ liệu thực bằng SQL thích hợp nếu có quyền.

**Câu 6.** `V$SQL` báo một cursor có `EXECUTIONS = 100` và `ELAPSED_TIME = 2,000,000` microseconds. Có được coi mọi request đều mất chính xác 20 ms không?

**Đáp án:** Không. Đây là thống kê tích lũy trong ngữ cảnh cursor; con số trung bình đơn giản không phản ánh phân bố latency, thời gian từng request, các child cursor, tác động parallel hoặc giới hạn vòng đời cache.

**Câu 7.** Developer đọc `V$SESSION` gặp `ORA-00942`, dù tên view có trong tài liệu. Điều gì cần kiểm tra?

**Đáp án:** Quyền đọc dynamic view/synonym và ngữ cảnh container. Yêu cầu DBA cấp quyền tối thiểu hoặc cung cấp số liệu; không tự cấp `DBA` cho runtime account.

## Kết luận

Trong Oracle, **data dictionary** mô tả cấu trúc và metadata được quản lý của database; **static dictionary views** như `USER_*`, `ALL_*`, `DBA_*`, `CDB_*` cung cấp những góc nhìn có giới hạn quyền và container khác nhau lên metadata đó. **Dynamic performance views** như `V$SESSION`, `V$SQL`, `V$INSTANCE` cho thấy hoạt động và thống kê vận hành, còn `GV$...` bổ sung góc nhìn nhiều instance trong môi trường RAC.

Để đọc đúng kết quả, luôn xác định **user/schema, PDB/container, instance, thời điểm thu thập và quyền truy cập**. Hãy dùng dictionary để biết *đối tượng được định nghĩa như thế nào*, dynamic view để biết *database đang hoạt động ra sao*, và kết hợp cả hai với log, metric và kiểm chứng thực tế khi xử lý vấn đề. Không diễn giải metadata như số liệu tức thời, không coi số liệu V$ là lịch sử hoàn chỉnh và không cấp quyền catalog rộng chỉ để thuận tiện cho một truy vấn.
