# Tra cứu CDB_*, DBA_*, ALL_* và USER_* trong môi trường Oracle Multitenant

Trong Oracle Database, khi cần kiểm tra một bảng tồn tại ở đâu, một schema sở hữu những đối tượng gì hoặc một user được phép truy cập bảng nào, ta thường tra cứu các **data dictionary views**. Trong môi trường **Container Database (CDB)** có nhiều **Pluggable Databases (PDBs)**, cách chọn view và ngữ cảnh kết nối quyết định phạm vi dữ liệu nhận được.

Một truy vấn như `SELECT * FROM DBA_TABLES` không có nghĩa “liệt kê bảng ở mọi PDB”. Nếu chạy trong một PDB, nó phản ánh metadata theo **PDB hiện tại**. Nếu chạy ở `CDB$ROOT`, họ `DBA_*` phản ánh ngữ cảnh root, không tự động tổng hợp tất cả PDB. Khi cần tra cứu liên container, họ `CDB_*` thường là lựa chọn phù hợp, đi kèm `CON_ID` và các yêu cầu về quyền.

Bài học này hướng dẫn cách phân biệt bốn họ view `CDB_*`, `DBA_*`, `ALL_*` và `USER_*`; cách xác định container hiện tại; cách viết truy vấn có `CON_ID` để tránh nhầm hai bảng trùng tên ở các PDB khác nhau; và những giới hạn về quyền truy cập metadata. Các ví dụ sử dụng SQL*Plus/SQLcl và cú pháp Oracle Database 19c trở lên, trong bối cảnh kiến trúc multitenant.

## 1. Bối cảnh: CDB, PDB và metadata

### 1.1. Vì sao Multitenant làm thay đổi cách tra cứu?

Một **CDB** gồm một root và có thể chứa nhiều PDB:

- **`CDB$ROOT`**: container gốc, giữ metadata và hạ tầng chung ở mức CDB.
- **`PDB$SEED`**: PDB mẫu do Oracle quản lý để tạo các PDB mới.
- **Các PDB ứng dụng**: ví dụ `SALES_PDB`, `HR_PDB`, nơi các bảng, schema và ứng dụng có thể hoạt động độc lập về mặt logic.

```text
                   Oracle CDB
                       |
          +------------+-------------+
          |            |             |
      CDB$ROOT     PDB$SEED      Application PDBs
                                      |
                              +-------+-------+
                              |               |
                           SALES_PDB        HR_PDB
                              |               |
                           APP.ORDERS       APP.ORDERS
```

Trong ví dụ trên, hai bảng cùng có tên `APP.ORDERS`, nhưng thuộc **hai PDB khác nhau**. Để định danh chính xác đối tượng khi tra cứu toàn CDB, cần biết **container**, **owner** và **object name**; một số loại đối tượng còn có thêm namespace hoặc subobject.

### 1.2. Data dictionary view là gì?

**Data dictionary** là tập metadata mô tả cấu trúc và trạng thái đối tượng database: bảng, cột, chỉ mục, users, roles, grants, tablespaces, constraints, v.v. Oracle cung cấp các view để người dùng tra cứu theo phạm vi và quyền.

Ví dụ:

- `USER_TABLES`: các bảng thuộc user hiện tại.
- `ALL_TABLES`: các bảng thuộc phạm vi mà user hiện tại có quyền truy cập/nhìn thấy.
- `DBA_TABLES`: thông tin bảng theo phạm vi database/container đang kết nối, nếu có quyền xem metadata tương ứng.
- `CDB_TABLES`: view phục vụ tra cứu bảng ở nhiều containers, với cột `CON_ID`, khi truy vấn và quyền phù hợp.

Các view này chứa **metadata**, không phải toàn bộ dữ liệu nghiệp vụ của bảng. Đọc `DBA_TABLES` không tương đương đọc mọi dòng trong `APP.ORDERS`.

### 1.3. Bốn câu hỏi cần trả lời trước khi chọn view

1. **Đang kết nối vào container nào?** Root hay một PDB?
2. **Cần xem đối tượng của ai?** Chính mình, các đối tượng có quyền truy cập, mọi đối tượng trong PDB hay across PDBs?
3. **Có quyền xem metadata đến đâu?** Quyền hệ thống, quyền trên view hoặc quyền được cấp qua role có thể ảnh hưởng.
4. **Cần định danh container không?** Một tên bảng, user hoặc tablespace có thể xuất hiện ở nhiều PDB.

Nếu bỏ qua một trong những câu hỏi này, truy vấn có thể chạy thành công nhưng diễn giải kết quả sai.

## 2. So sánh CDB_*, DBA_*, ALL_* và USER_*

### 2.1. Bảng phân biệt nhanh

| Họ view | Phạm vi thông tin điển hình | Ai thường sử dụng? | Cột nhận diện quan trọng |
| --- | --- | --- | --- |
| **`USER_*`** | Đối tượng **do database user hiện tại sở hữu** trong ngữ cảnh container hiện tại | Developer, schema owner | Thường không cần cột `OWNER` vì owner là user đang kết nối |
| **`ALL_*`** | Đối tượng user hiện tại **có thể truy cập** theo các quyền và quy tắc visibility của view | Ứng dụng, developer, user báo cáo | Thường có `OWNER` để phân biệt schema |
| **`DBA_*`** | Metadata của **database/container hiện tại**, không chỉ của user đăng nhập | DBA trong PDB hoặc root | Thường có `OWNER`; không mặc định có `CON_ID` |
| **`CDB_*`** | Metadata từ nhiều containers trong một CDB, **trong phạm vi quyền và khả năng nhìn thấy được phép** | DBA trung tâm, common user được cấp quyền | **`CON_ID`**, thường cùng `OWNER` |

Dấu `*` trong tên họ view là **ký hiệu quy ước**, không phải wildcard hợp lệ để truy vấn SQL. Ví dụ phải viết `SELECT ... FROM CDB_TABLES` hoặc `SELECT ... FROM DBA_OBJECTS`, không viết `FROM CDB_*`.

### 2.2. Phân biệt bằng một trường hợp cụ thể

Giả sử:

- `SALES_PDB` có `APP.ORDERS`, `APP.CUSTOMERS` và `REPORT.SALES_SUMMARY`.
- `HR_PDB` có `APP.EMPLOYEES` và một bảng khác cũng tên `APP.ORDERS`.
- User `APP` đăng nhập vào `SALES_PDB`.
- User `REPORT_USER` có quyền `SELECT` trên `APP.ORDERS` của `SALES_PDB`, nhưng không sở hữu bảng.

Khi đó, về mặt khái niệm:

| Ngữ cảnh truy vấn | View | Kết quả đáng chú ý |
| --- | --- | --- |
| `APP` trong `SALES_PDB` | `USER_TABLES` | Các bảng do `APP` sở hữu trong `SALES_PDB` |
| `REPORT_USER` trong `SALES_PDB` | `ALL_TABLES` | Có thể thấy `APP.ORDERS` nếu quyền/điều kiện visibility cho phép |
| DBA trong `SALES_PDB` | `DBA_TABLES` | Bảng của các schema trong `SALES_PDB` |
| DBA trong `CDB$ROOT` | `DBA_TABLES` | Metadata theo **root**, không phải danh sách gộp của `SALES_PDB` và `HR_PDB` |
| Common user đủ quyền trong `CDB$ROOT` | `CDB_TABLES` | Có thể thấy `APP.ORDERS` ở nhiều PDB, phân biệt bằng `CON_ID` |

`ALL_*` không có nghĩa “tất cả đối tượng trong database”. Chữ **ALL** ở đây cần hiểu theo **phạm vi đối tượng mà user được phép truy cập**. Đồng thời, `DBA_*` không có nghĩa một người bất kỳ có thể đọc được: việc xem các view thuộc họ `DBA_*` thường đòi hỏi quyền truy cập dictionary phù hợp.

## 3. Luôn xác định container trước khi truy vấn

### 3.1. Kiểm tra bằng SQL*Plus hoặc SQLcl

```sql
SHOW CON_NAME;
```

Ví dụ kết quả:

```text
CON_NAME
------------------------------
SALES_PDB
```

Nếu thấy `CDB$ROOT`, bạn đang ở root; nếu thấy `SALES_PDB`, bạn đang ở PDB đó.

Một lệnh SQL độc lập với SQL*Plus/SQLcl để lấy thêm thông tin:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME')      AS container_name,
       SYS_CONTEXT('USERENV', 'CON_ID')        AS container_id,
       SYS_CONTEXT('USERENV', 'SESSION_USER')  AS session_user,
       SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM   dual;
```

**`SESSION_USER`** là database user đã đăng nhập; **`CURRENT_SCHEMA`** là schema mặc định dùng để giải quyết tên đối tượng không đủ qualifier. Hai giá trị có thể khác nhau nếu session đã dùng `ALTER SESSION SET CURRENT_SCHEMA`. Chuyển `CURRENT_SCHEMA` không tự cấp quyền và không biến database user thành owner của đối tượng schema khác.

### 3.2. Liệt kê containers khi có quyền quản trị

Từ root, tài khoản có quyền đọc view động tương ứng có thể chạy:

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM   v$containers
ORDER  BY con_id;
```

Kết quả **minh họa**:

```text
CON_ID  NAME        OPEN_MODE   RESTRICTED
------  ----------  ----------  ----------
1       CDB$ROOT    READ WRITE  NO
2       PDB$SEED    READ ONLY   NO
3       SALES_PDB   READ WRITE  NO
4       HR_PDB      READ WRITE  NO
```

Các ID thường gặp:

- `CON_ID = 1`: `CDB$ROOT`.
- `CON_ID = 2`: `PDB$SEED`.
- `CON_ID >= 3`: các PDB ứng dụng hoặc container khác do Oracle quản lý theo kiến trúc.
- Một số **dynamic performance views** dùng `CON_ID = 0` để biểu thị dữ liệu của toàn CDB hoặc dữ liệu không gắn một container cụ thể. Không được áp dụng máy móc ý nghĩa đó cho mọi view và mọi dòng.

`CON_ID` là định danh container trong **CDB hiện tại**; không nên lưu cứng số 3 với ý nghĩa “SALES_PDB vĩnh viễn” trong một hệ thống khác hoặc sau các thao tác plug/unplug. Khi báo cáo, nên gắn với tên container qua view phù hợp.

### 3.3. Chuyển container khi được cấp quyền

Một tài khoản quản trị chung có quyền cần thiết có thể chuyển vào PDB:

```sql
-- Chỉ thực hiện nếu user có đặc quyền cần thiết.
ALTER SESSION SET CONTAINER = SALES_PDB;

SHOW CON_NAME;
```

Sau khi chuyển container, chính câu truy vấn `SELECT ... FROM DBA_TABLES` có thể trả về **bộ dữ liệu khác**, vì nó phản ánh ngữ cảnh container mới.

Không nên giả định mọi local user trong PDB được phép chuyển tùy ý sang PDB khác. Quyền `SET CONTAINER`, tính hợp lệ của user tại container đích và các chính sách bảo mật phải được đáp ứng.

## 4. Họ USER_*: metadata thuộc user hiện tại

### 4.1. Khi nào nên dùng?

Sử dụng `USER_*` nếu câu hỏi là:

- “Tài khoản đang đăng nhập sở hữu những bảng nào?”
- “Các index của schema tôi có là gì?”
- “Các cột và constraints trong bảng do tôi sở hữu?”
- “Các object của tôi đang VALID hay INVALID?”

Ví dụ, sau khi đăng nhập bằng user `APP` vào `SALES_PDB`:

```sql
SELECT table_name,
       tablespace_name,
       status
FROM   user_tables
ORDER  BY table_name;
```

Để xem các object nói chung:

```sql
SELECT object_type,
       object_name,
       status
FROM   user_objects
ORDER  BY object_type, object_name;
```

Một số view thuộc họ `USER_*` không có cột `OWNER`, vì chính user đang kết nối là chủ sở hữu. Đừng sao chép nguyên câu truy vấn `DBA_TABLES` có `OWNER` sang `USER_TABLES` rồi mặc định cột vẫn tồn tại.

### 4.2. Xem cấu trúc cột

```sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       nullable
FROM   user_tab_columns
WHERE  table_name = 'ORDERS'
ORDER  BY column_id;
```

Tên object không đặt trong double quotes được Oracle lưu theo dạng chữ hoa thông thường; vì vậy điều kiện `TABLE_NAME = 'ORDERS'` phù hợp cho bảng được tạo bằng tên không có quoted identifier. Nếu đã tạo bảng bằng tên phân biệt chữ hoa/chữ thường, phải dùng đúng tên được lưu.

### 4.3. USER_* không phải toàn bộ PDB

Nếu `APP` không sở hữu `REPORT.SALES_SUMMARY`, `USER_TABLES` của `APP` không liệt kê bảng đó dù `APP` có thể được cấp quyền `SELECT` trên bảng.

Muốn liệt kê **các bảng có thể truy cập**, cân nhắc `ALL_TABLES`. Muốn kiểm kê mọi bảng trong PDB với quyền DBA, dùng `DBA_TABLES`.

### 4.4. USER_* trong từng PDB

Cùng một username (ví dụ `APP`) có thể tồn tại dưới dạng các **local users** khác nhau ở hai PDB, mỗi user có các object khác nhau. Đăng nhập vào `SALES_PDB` và chạy `USER_TABLES` không cho kết quả các bảng của user `APP` trong `HR_PDB`.

Điều này là chủ đích của multitenant: mỗi PDB có metadata và phạm vi bảo mật riêng. Không suy rằng trùng username đồng nghĩa cùng một tài khoản thống nhất ở mọi PDB.

## 5. Họ ALL_*: metadata của đối tượng user có thể truy cập

### 5.1. Sự khác biệt giữa ALL_* và USER_*

`ALL_*` hữu ích khi bạn **không sở hữu** object nhưng cần làm việc với object đã được cấp quyền. Ví dụ user `REPORT_USER` trong `SALES_PDB` được DBA cấp quyền truy cập bảng `APP.ORDERS`.

```sql
SELECT owner,
       table_name,
       tablespace_name
FROM   all_tables
WHERE  owner = 'APP'
ORDER  BY table_name;
```

Nếu user hiện tại có quyền cần thiết trên `APP.ORDERS`, bảng này có thể hiện trong `ALL_TABLES`; nó sẽ **không xuất hiện trong `USER_TABLES` của `REPORT_USER`** vì user đó không sở hữu bảng.

Phạm vi hiển thị của từng `ALL_*` view phụ thuộc loại metadata và định nghĩa view; không nên coi mọi `ALL_*` là một bộ lọc giống hệt nhau trên các quyền `SELECT`.

### 5.2. Truy vấn cột của một schema được cấp quyền

```sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       nullable
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
```

Cột `OWNER` rất quan trọng: cùng một PDB có thể có `APP.ORDERS` và `ARCHIVE.ORDERS`. Nếu lọc duy nhất `TABLE_NAME='ORDERS'`, truy vấn có thể trả về cột của nhiều bảng khác schema.

### 5.3. ALL_* không tự vượt biên giới PDB

`ALL_TABLES` trong `SALES_PDB` là view theo **ngữ cảnh PDB đang kết nối**, không tự tổng hợp những bảng user có thể nhìn thấy trong `HR_PDB`. Dù cùng một common user có quyền tại nhiều PDB, kết nối vào một PDB không biến `ALL_TABLES` thành truy vấn toàn CDB.

### 5.4. Kiểm tra quyền liên quan đến object

Khi cần xem các quyền object hiển thị trong ngữ cảnh user, có thể dùng view như `ALL_TAB_PRIVS`, với cột `OWNER`, `TABLE_NAME`, `GRANTEE` và `PRIVILEGE`:

```sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM   all_tab_privs
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY grantee, privilege;
```

Kết quả cần đọc theo định nghĩa của view và quyền xem metadata của user; không đồng nghĩa toàn bộ quyền hiệu lực chỉ được mô tả bởi các dòng grant trực tiếp. Quyền có thể đến từ role, quyền hệ thống hoặc những cơ chế bảo mật khác. Việc kiểm tra quyền hiệu lực của một session đôi khi cần thêm các view và ngữ cảnh phù hợp.

## 6. Họ DBA_*: metadata trong container đang kết nối

### 6.1. Khi kết nối vào PDB

Một DBA làm việc trong `SALES_PDB` có thể truy vấn:

```sql
SELECT owner,
       table_name,
       tablespace_name
FROM   dba_tables
WHERE  owner = 'APP'
ORDER  BY table_name;
```

Kết quả phản ánh các bảng `APP` trong **SALES_PDB**, không mặc nhiên kèm bảng từ `HR_PDB`.

Đây là cách phù hợp khi người quản trị muốn kiểm tra **tất cả schemas của một PDB cụ thể** nhưng không cần tra cứu cross-container.

### 6.2. Khi kết nối vào CDB$ROOT

Nếu DBA đang ở root và chạy:

```sql
SHOW CON_NAME;

SELECT owner,
       table_name
FROM   dba_tables
WHERE  owner = 'APP';
```

`DBA_TABLES` phản ánh **ngữ cảnh root**. Truy vấn không tự động tìm bảng `APP.ORDERS` ở `SALES_PDB` hoặc `HR_PDB`. Nếu muốn kiểm kê nhiều PDB cùng lúc, hãy dùng họ `CDB_*` trong ngữ cảnh và phạm vi quyền thích hợp.

### 6.3. Những DBA_* view thường dùng

| View | Metadata tiêu biểu | Ví dụ nhu cầu |
| --- | --- | --- |
| `DBA_TABLES` | Bảng theo owner, tablespace, thuộc tính lưu trữ | Kiểm kê bảng của các schema trong PDB |
| `DBA_OBJECTS` | Các object, loại object, trạng thái VALID/INVALID | Kiểm tra object invalid sau triển khai |
| `DBA_TAB_COLUMNS` | Cột và kiểu dữ liệu | Đọc cấu trúc bảng của schema khác |
| `DBA_INDEXES` | Index và trạng thái | Điều tra/index inventory |
| `DBA_CONSTRAINTS` | Primary key, foreign key, check, unique... | Kiểm tra mô hình ràng buộc |
| `DBA_USERS` | Danh sách và thuộc tính database users | Kiểm tra trạng thái account theo container |
| `DBA_ROLE_PRIVS`, `DBA_SYS_PRIVS` | Các grant liên quan roles và system privileges | Điều tra quyền |
| `DBA_TABLESPACES`, `DBA_DATA_FILES` | Tablespaces và datafiles theo phạm vi container | Kiểm tra cấu hình lưu trữ |

Các view có cột và tiêu chí hiển thị riêng; nên kiểm tra định nghĩa của từng view trong tài liệu Oracle, không dựa vào giả định rằng chúng có cùng danh sách cột.

### 6.4. Quyền truy cập DBA_* không mặc định

Một application user chỉ có quyền `CREATE SESSION` không nhất thiết truy vấn được `DBA_TABLES`. Các view này thường yêu cầu DBA cấp **quyền đọc dictionary phù hợp**, chẳng hạn thông qua một role dành cho tra cứu catalog hoặc các quyền đối tượng cần thiết theo chính sách hệ thống.

Không nên cấp `SELECT ANY DICTIONARY` hoặc các đặc quyền quản trị rộng chỉ để một ứng dụng đọc vài tên bảng. Với nghiệp vụ có thể giải quyết bằng `USER_*` hoặc `ALL_*`, dùng các họ view đó giúp giảm nhu cầu mở rộng quyền.

## 7. Họ CDB_*: tra cứu cross-container

### 7.1. Ý nghĩa của CDB_*

Trong Oracle Multitenant, nhiều view dạng `CDB_<tên>` cung cấp khả năng tra cứu metadata từ nhiều containers trong CDB. Ví dụ:

| View cấp container | View tương ứng trong container | Dữ liệu tiêu biểu |
| --- | --- | --- |
| `CDB_TABLES` | `DBA_TABLES` | Bảng ở các containers được phép nhìn thấy |
| `CDB_OBJECTS` | `DBA_OBJECTS` | Metadata objects, trạng thái và loại |
| `CDB_TAB_COLUMNS` | `DBA_TAB_COLUMNS` | Cột của các bảng/view trong containers |
| `CDB_USERS` | `DBA_USERS` | Database users theo container |
| `CDB_TABLESPACES` | `DBA_TABLESPACES` | Tablespace metadata theo container |
| `CDB_DATA_FILES` | `DBA_DATA_FILES` | Datafiles theo container |
| `CDB_ROLE_PRIVS` | `DBA_ROLE_PRIVS` | Grants cho roles theo container |

Không phải mọi `DBA_*` view đều có bản `CDB_*` tương ứng; cần xác nhận tên view và định nghĩa trong Oracle Database Reference của release đang chạy.

**Cột quan trọng nhất là `CON_ID`.** Khi tra cứu nhiều PDB, luôn đưa `CON_ID` vào báo cáo hoặc join với tên container để tránh gộp nhầm dữ liệu.

### 7.2. Ví dụ: tìm APP.ORDERS trên toàn CDB

Kết nối bằng tài khoản có quyền truy vấn cross-container ở `CDB$ROOT`:

```sql
SHOW CON_NAME;

SELECT con_id,
       owner,
       table_name,
       tablespace_name
FROM   cdb_tables
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY con_id;
```

Kết quả **minh họa**:

```text
CON_ID  OWNER  TABLE_NAME  TABLESPACE_NAME
------  -----  ----------  ---------------
3       APP    ORDERS      APP_DATA
4       APP    ORDERS      USERS
```

Hai dòng có cùng `OWNER` và `TABLE_NAME` nhưng khác `CON_ID`, nghĩa là chúng thuộc **hai container khác nhau**. Không nên suy chúng là hai bản sao đồng bộ của cùng một bảng; mỗi bảng có dữ liệu, quyền và vòng đời riêng.

### 7.3. Hiển thị tên PDB thay vì chỉ CON_ID

Có thể kết hợp `CDB_TABLES` với `V$CONTAINERS` trong root:

```sql
SELECT c.name             AS container_name,
       t.con_id,
       t.owner,
       t.table_name,
       t.tablespace_name
FROM   cdb_tables t
JOIN   v$containers c
       ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
AND    t.table_name = 'ORDERS'
ORDER  BY c.name, t.owner, t.table_name;
```

Kết quả dự kiến theo dữ liệu ví dụ:

```text
CONTAINER_NAME  CON_ID  OWNER  TABLE_NAME  TABLESPACE_NAME
--------------  ------  -----  ----------  ---------------
HR_PDB          4       APP    ORDERS      USERS
SALES_PDB       3       APP    ORDERS      APP_DATA
```

Khi làm báo cáo quản trị, **container name + owner + table name** thường rõ nghĩa hơn chỉ ghép `OWNER.TABLE_NAME`.

### 7.4. Đếm số bảng theo PDB và owner

```sql
SELECT c.name AS container_name,
       t.owner,
       COUNT(*) AS table_count
FROM   cdb_tables t
JOIN   v$containers c
       ON c.con_id = t.con_id
WHERE  t.owner IN ('APP', 'REPORT')
GROUP  BY c.name, t.owner
ORDER  BY c.name, t.owner;
```

Câu truy vấn trả về **số bảng mà session được phép nhìn thấy qua view**, không nhất thiết là tổng chính xác của toàn bộ PDBs nếu user bị hạn chế quyền/visibility.

`COUNT(*)` trên `CDB_TABLES` không phải số dòng dữ liệu trong bảng và không phải số physical segments hoặc dung lượng storage.

### 7.5. Tìm object INVALID ở nhiều PDB

```sql
SELECT c.name AS container_name,
       o.con_id,
       o.owner,
       o.object_type,
       o.object_name,
       o.status
FROM   cdb_objects o
JOIN   v$containers c
       ON c.con_id = o.con_id
WHERE  o.status = 'INVALID'
AND    o.owner NOT IN ('SYS', 'SYSTEM')
ORDER  BY c.name, o.owner, o.object_type, o.object_name;
```

Câu truy vấn hữu ích sau một đợt triển khai hoặc nâng cấp khi muốn phát hiện metadata object bị `INVALID` theo container.

Không nên hiểu mọi object có `STATUS='INVALID'` đều có cùng mức độ nghiêm trọng: cần xem loại object, các dependencies và nguyên nhân compile/validation. Metadata view báo trạng thái; nó không tự giải thích đầy đủ root cause.

### 7.6. Xem users theo PDB

```sql
SELECT c.name AS container_name,
       u.con_id,
       u.username,
       u.common,
       u.account_status
FROM   cdb_users u
JOIN   v$containers c
       ON c.con_id = u.con_id
WHERE  u.username IN ('APP', 'REPORT_USER', 'C##MONITOR')
ORDER  BY c.name, u.username;
```

Cột `COMMON` giúp phân biệt user chung (`YES`) và local (`NO`) theo metadata được báo cáo. Một common user có thể có dòng metadata trong nhiều containers; không nên coi mỗi dòng của `CDB_USERS` là một tài khoản OS hay một identity độc lập.

## 8. Phạm vi container và quyền truy cập ảnh hưởng kết quả thế nào?

### 8.1. CDB_* không phải “xem tất cả bất kể quyền”

Để đọc metadata cross-container, user thường phải:

- Kết nối đúng **`CDB$ROOT`** với tài khoản phù hợp.
- Có **quyền SELECT trên view** hoặc quyền đọc dictionary được cấu hình phù hợp.
- Có **quyền nhìn thấy dữ liệu của các containers** cần truy vấn. Với common user, thuộc tính **`CONTAINER_DATA`** và các quy tắc Oracle áp dụng cho container data objects có thể giới hạn những container được trả về.
- Xét thêm trạng thái mở/khả năng truy cập của từng PDB và những ràng buộc release cụ thể.

Vì vậy, một truy vấn `CDB_TABLES` chạy thành công nhưng chỉ trả về một vài PDB **không đủ để kết luận** các PDB còn lại không có bảng. Có thể đơn giản là session không được thấy dữ liệu của chúng.

### 8.2. Common user và local user

**Common user** được định nghĩa ở cấp CDB và có thể tồn tại xuyên nhiều containers theo kiến trúc multitenant. Tên common user thông thường có tiền tố `C##` khi cấu hình mặc định áp dụng. **Local user** chỉ tồn tại trong PDB cụ thể.

| Đặc điểm | Common user | Local user |
| --- | --- | --- |
| Phạm vi danh tính | Mức CDB, có thể dùng trong nhiều containers | Một PDB |
| Mục tiêu thường gặp | Quản trị/giám sát các PDB hoặc tác vụ chung | Schema ứng dụng, user nghiệp vụ |
| Tra cứu cross-container | Có thể thực hiện khi được cấp đúng quyền và visibility | Không tự có quyền toàn CDB chỉ vì đăng nhập thành công |
| Thường được tạo ở đâu? | Root bằng cơ chế common user | PDB đích |

Sở hữu quyền truy vấn metadata trong một PDB không tự động cấp quyền tương tự trong PDB khác. Ngoài ra, quyền **common** và quyền **local** là hai khái niệm cần xem xét khi cấp grants.

### 8.3. CONTAINER_DATA là gì?

Oracle sử dụng thuộc tính `CONTAINER_DATA` để xác định phạm vi container mà một common user có thể nhìn thấy thông qua các **container data objects**, bao gồm các view liên container có liên quan.

Ví dụ về mặt khái niệm:

```text
CDB$ROOT
  |
  +-- SALES_PDB
  +-- HR_PDB
  +-- FINANCE_PDB

Common user C##MONITOR:
  Được phép nhìn dữ liệu container: CDB$ROOT, SALES_PDB
  Không được phép nhìn: HR_PDB, FINANCE_PDB
```

Nếu quyền SELECT trên `CDB_TABLES` đã hợp lệ nhưng `CONTAINER_DATA` chỉ cho phép một tập container hẹp, kết quả có thể chỉ chứa metadata của root và `SALES_PDB`. Việc mở rộng quyền đọc view không tự khắc bảo đảm mở rộng tập dữ liệu của mọi PDB.

Cấu hình `CONTAINER_DATA` thường thuộc trách nhiệm DBA quản lý bảo mật toàn CDB. Cú pháp và điều kiện thay đổi có thể khác nhau tùy loại container data object, kiểu user và phiên bản; không nên sửa thuộc tính chỉ để “làm đủ số dòng báo cáo” khi chưa có phê duyệt phạm vi dữ liệu.

### 8.4. Phân biệt quyền xem metadata và quyền thao tác object

Một user có thể được phép đọc `CDB_TABLES` và biết bảng `APP.ORDERS` tồn tại trong `HR_PDB` mà **không có quyền SELECT dữ liệu nghiệp vụ từ bảng đó**. Ngược lại, user có quyền `SELECT` trên một bảng trong `SALES_PDB` không nhất thiết có quyền đọc `DBA_TABLES` hoặc `CDB_TABLES`.

Hai nhóm quyền này phục vụ mục tiêu khác nhau:

- **Dictionary/catalog privilege**: xem metadata về database.
- **Object privilege**: thực thi thao tác như `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE` trên đối tượng nghiệp vụ.

Khi thiết kế tài khoản giám sát, chỉ cấp quyền cần thiết theo yêu cầu. Tránh dùng tài khoản `SYS` làm tài khoản đọc báo cáo metadata định kỳ.

### 8.5. Chú ý PDB đóng hoặc không sẵn sàng

Tình trạng `OPEN_MODE` và hạn chế truy cập có thể ảnh hưởng đến việc thu thập metadata từ PDB, nhất là trong công cụ và cơ chế truy vấn cross-container. Nếu thiếu dòng của PDB nào đó, nên kiểm tra:

```sql
SELECT name, open_mode, restricted
FROM   v$containers
ORDER  BY con_id;
```

Không được mở một PDB sản xuất chỉ để hoàn thiện báo cáo nếu chưa có quy trình vận hành cho phép. Khi không thể quan sát đầy đủ, kết quả phải ghi rõ phạm vi có thể đọc tại thời điểm truy vấn.

## 9. So sánh cùng một mục tiêu bằng bốn họ view

Giả sử muốn tìm bảng `ORDERS` của schema `APP`:

### 9.1. Người phát triển đăng nhập đúng schema APP trong SALES_PDB

```sql
-- APP là chủ sở hữu bảng.
SELECT table_name
FROM   user_tables
WHERE  table_name = 'ORDERS';
```

Câu truy vấn ngắn gọn, không cần quyền dictionary nâng cao. Nó không tìm bảng ngoài schema `APP`.

### 9.2. REPORT_USER được cấp quyền trên APP.ORDERS

```sql
SELECT owner,
       table_name
FROM   all_tables
WHERE  owner = 'APP'
AND    table_name = 'ORDERS';
```

Câu truy vấn nhìn theo phạm vi object user có thể truy cập trong `SALES_PDB`, không tự xem `HR_PDB`.

### 9.3. DBA quản trị SALES_PDB

```sql
SELECT owner,
       table_name
FROM   dba_tables
WHERE  owner = 'APP'
AND    table_name = 'ORDERS';
```

DBA tra cứu metadata trong PDB hiện tại. Kết quả có thể giống query `ALL_TABLES` ở trên về dòng `APP.ORDERS` nhưng **phạm vi quyền khác nhau**.

### 9.4. DBA trung tâm quản trị toàn CDB

```sql
SELECT c.name AS pdb_name,
       t.owner,
       t.table_name
FROM   cdb_tables t
JOIN   v$containers c ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
AND    t.table_name = 'ORDERS'
AND    c.name NOT IN ('CDB$ROOT', 'PDB$SEED')
ORDER  BY c.name;
```

Truy vấn này dự kiến liệt kê bảng `APP.ORDERS` của các PDB mà user đủ quyền nhìn thấy. Nó còn chủ động loại root và seed khỏi báo cáo tập trung vào PDB ứng dụng.

## 10. Truy vấn cấu trúc bảng và object theo đúng phạm vi

### 10.1. Khi chỉ có quyền ở cấp ứng dụng

Ví dụ user cần khám phá các cột của bảng được cấp quyền:

```sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       data_length
FROM   all_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
```

Dùng `ALL_TAB_COLUMNS` là lựa chọn điển hình cho công cụ khám phá schema chạy dưới account ứng dụng, miễn user có đủ quyền để metadata đó hiện ra.

### 10.2. Khi DBA cần xem mọi cột trong một PDB

```sql
SELECT owner,
       table_name,
       column_name,
       data_type
FROM   dba_tab_columns
WHERE  owner = 'APP'
AND    table_name = 'ORDERS'
ORDER  BY column_id;
```

Truy vấn dùng phạm vi dictionary của **container đang kết nối**.

### 10.3. Khi cần so sánh cấu trúc giữa các PDB

Trong root và có quyền phù hợp:

```sql
SELECT c.name AS container_name,
       tc.owner,
       tc.table_name,
       tc.column_id,
       tc.column_name,
       tc.data_type,
       tc.data_length,
       tc.nullable
FROM   cdb_tab_columns tc
JOIN   v$containers c ON c.con_id = tc.con_id
WHERE  tc.owner = 'APP'
AND    tc.table_name = 'ORDERS'
ORDER  BY c.name, tc.column_id;
```

Ví dụ này hỗ trợ phát hiện hai PDB có cấu trúc cột khác nhau dù cùng tên bảng. Chỉ so sánh tên và `DATA_TYPE` có thể chưa đủ cho các datatype đặc biệt; tùy yêu cầu cần xem thêm `DATA_PRECISION`, `DATA_SCALE`, `CHAR_USED`, `CHAR_LENGTH` và các thuộc tính khác.

### 10.4. Theo dõi object invalid trong đúng PDB

Nếu DBA chỉ quản lý `SALES_PDB`:

```sql
SELECT owner,
       object_type,
       object_name,
       status
FROM   dba_objects
WHERE  status = 'INVALID'
AND    owner = 'APP'
ORDER  BY object_type, object_name;
```

Nếu muốn theo dõi toàn CDB, chuyển sang `CDB_OBJECTS` và thêm `CON_ID`. Không dùng `DBA_OBJECTS` từ root rồi kết luận mọi PDB đã không còn object invalid.

## 11. Những lỗi diễn giải thường gặp

### 11.1. “Chạy DBA_TABLES trong root là thấy hết mọi PDB”

**Sai.** `DBA_TABLES` phản ánh dictionary theo container hiện tại. Ở root, muốn kiểm kê các PDB nên sử dụng `CDB_TABLES` với quyền phù hợp, hoặc kết nối riêng từng PDB để tra cứu `DBA_TABLES`.

### 11.2. “CDB_TABLES thấy hai APP.ORDERS nên có một bảng bị trùng”

**Sai.** Một dòng có `CON_ID=3`, dòng còn lại `CON_ID=4` có thể chỉ ra hai bảng độc lập ở hai PDB. Phải gắn tên container và owner trước khi so sánh hoặc báo cáo.

### 11.3. “ALL_TABLES liệt kê tất cả bảng trong database”

**Sai.** `ALL_TABLES` dựa trên phạm vi object user hiện tại có thể truy cập; một user thiếu quyền có thể thấy ít bảng hơn DBA dù họ ở cùng PDB.

### 11.4. “Không có dòng trong CDB_USERS nghĩa là PDB không có user”

**Chưa đủ bằng chứng.** Có thể common user đang truy vấn không có quyền/`CONTAINER_DATA` phù hợp, PDB có giới hạn trạng thái, hoặc điều kiện lọc username không đúng.

### 11.5. “USER_TABLES có cột OWNER giống DBA_TABLES”

**Không nên giả định.** Nhiều view `USER_*` bỏ cột `OWNER` vì owner đã là user hiện tại. Tra cứu danh sách cột của view trước khi chuyển một query từ họ này sang họ khác.

### 11.6. “Đổi CURRENT_SCHEMA thành APP là USER_TABLES thành của APP”

**Không thể suy như vậy.** `ALTER SESSION SET CURRENT_SCHEMA` thay đổi cách phân giải tên object không đủ qualifier; nó không đổi danh tính phiên đăng nhập hoặc tự cấp quyền sở hữu. Với mục tiêu kiểm tra schema khác, chọn `ALL_*` hoặc `DBA_*` theo quyền hiện tại.

### 11.7. “Có SELECT trên dictionary thì chắc chắn có SELECT trên mọi bảng nghiệp vụ”

**Sai.** Đọc metadata và đọc dữ liệu bảng là hai quyền khác nhau. Đừng thử sử dụng dữ liệu nghiệp vụ chỉ vì dictionary cho biết bảng tồn tại.

### 11.8. “CON_ID là tên PDB cố định giữa mọi môi trường”

**Sai.** `CON_ID` dùng để định danh container trong CDB hiện tại. Trong báo cáo so sánh giữa các CDB hoặc qua các thao tác quản trị, cần dựa vào tên/identity phù hợp của container, không ghép cứng ý nghĩa của một con số.

## 12. Chẩn đoán khi câu truy vấn cho kết quả bất ngờ

### 12.1. Không thấy bảng mong đợi

Ví dụ `ALL_TABLES` không trả dòng cho `APP.ORDERS`:

1. Kiểm tra `SHOW CON_NAME`: đã kết nối vào đúng PDB chưa?
2. Kiểm tra `SESSION_USER` và `CURRENT_SCHEMA`: đang dùng user nào, schema mặc định là gì?
3. Kiểm tra owner/table name: tên trong dictionary có thể khác kỳ vọng do quoted identifier.
4. Kiểm tra user có quyền truy cập object cần xem không.
5. Nếu cần kiểm kê độc lập với quyền của application user, nhờ DBA kiểm tra `DBA_TABLES` trong cùng PDB.

Không vội cho rằng bảng đã bị drop chỉ vì một user không thấy bảng trong `ALL_TABLES`.

### 12.2. CDB_* trả ít PDB hơn dự tính

Nếu truy vấn từ root chỉ trả metadata của `SALES_PDB`:

1. Xem danh sách các PDB và `OPEN_MODE` qua `V$CONTAINERS`.
2. Xác định truy vấn thực sự chạy tại `CDB$ROOT`.
3. Xem quyền đọc view và phạm vi **`CONTAINER_DATA`** của user theo chính sách hiện tại.
4. Kiểm tra điều kiện `WHERE` có loại bỏ PDB hoặc schema ngoài ý muốn không.
5. Chỉ kết luận số lượng đối tượng trên những PDB thực sự được quan sát; ghi rõ phạm vi thu thập.

### 12.3. Gặp lỗi ORA-00942 hoặc ORA-01031

- **`ORA-00942: table or view does not exist`**: đối tượng không tồn tại dưới tên đang tham chiếu hoặc user không có quyền truy cập thích hợp; cũng có thể đang ở container không đúng.
- **`ORA-01031: insufficient privileges`**: chưa đủ quyền để thực hiện thao tác được yêu cầu.

Việc một user đọc được `USER_TABLES` không có nghĩa user đó đọc được `DBA_TABLES` hoặc `CDB_TABLES`. Chỉ cấp thêm đúng quyền cần thiết và theo phạm vi được phê duyệt; không tự nâng đặc quyền hệ thống khi đang điều tra một truy vấn metadata.

### 12.4. Gặp lỗi khi chuyển PDB

Một lệnh `ALTER SESSION SET CONTAINER = ...` có thể thất bại do thiếu quyền, container đích không tồn tại/không sẵn sàng hoặc user không hợp lệ ở container đích. Việc tra cứu metadata từ một PDB không yêu cầu ứng dụng thông thường phải có quyền chuyển PDB; với ứng dụng, cách chuẩn là kết nối qua service của PDB tương ứng.

### 12.5. Câu SQL chạy được nhưng báo cáo đếm sai

Nguyên nhân điển hình:

- Đếm `COUNT(*)` theo `OWNER` mà quên `CON_ID`, khiến object ở nhiều PDB bị gộp.
- Join `CDB_*` view mà không đưa `CON_ID` vào điều kiện nối với dữ liệu container phù hợp.
- Không loại root/seed khi chỉ muốn thống kê PDB ứng dụng.
- Trộn bảng và partition/subobject khi chọn view khác họ hoặc khác loại metadata.
- Coi các dòng không hiển thị vì thiếu quyền như đối tượng không tồn tại.

Khi báo cáo, luôn ghi rõ **CDB/PDB nào**, **đăng nhập bằng user nào**, **quyền nhìn thấy metadata** và **timestamp** của lần kiểm tra.

## 13. Thực hành có hướng dẫn

Các bài tập dưới đây chỉ dùng truy vấn đọc metadata. Tên `SALES_PDB`, `HR_PDB`, `APP` và `ORDERS` là ví dụ; thay bằng giá trị thực ở môi trường học. Không cần tạo bảng mới để làm bài nếu đã có schema mẫu.

### Bài 1 — Xác định phạm vi của session

```sql
SELECT SYS_CONTEXT('USERENV','CON_NAME')       AS container_name,
       SYS_CONTEXT('USERENV','SESSION_USER')   AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM   dual;
```

**Câu hỏi:** Nếu kết quả là `SALES_PDB` và `SESSION_USER=APP`, `USER_TABLES` trả metadata của bảng nào?

**Gợi ý:** Các bảng thuộc database user `APP` trong `SALES_PDB`.

### Bài 2 — So sánh USER_TABLES và ALL_TABLES

```sql
SELECT table_name
FROM   user_tables
ORDER  BY table_name;

SELECT owner, table_name
FROM   all_tables
WHERE  owner = 'APP'
ORDER  BY table_name;
```

**Câu hỏi:** Vì sao số dòng có thể khác nhau khi thực hiện bằng `REPORT_USER`?

**Gợi ý:** `USER_TABLES` chỉ nói về bảng do `REPORT_USER` sở hữu, trong khi `ALL_TABLES` có thể cho biết bảng `APP` mà `REPORT_USER` có quyền truy cập.

### Bài 3 — Kiểm tra schema ở một PDB

Dùng tài khoản DBA thích hợp, kết nối trực tiếp đến `SALES_PDB` hoặc vào PDB qua phương thức được phép:

```sql
SHOW CON_NAME;

SELECT owner, COUNT(*) AS table_count
FROM   dba_tables
WHERE  owner IN ('APP', 'REPORT')
GROUP  BY owner
ORDER  BY owner;
```

**Câu hỏi:** Có thể dùng kết quả này để khẳng định số bảng của `APP` ở `HR_PDB` không?

**Gợi ý:** Không; đây là metadata trong container đang kết nối.

### Bài 4 — Thống kê cross-container

Với common user phù hợp ở root:

```sql
SHOW CON_NAME;

SELECT c.name AS container_name,
       t.owner,
       COUNT(*) AS table_count
FROM   cdb_tables t
JOIN   v$containers c
       ON c.con_id = t.con_id
WHERE  t.owner = 'APP'
GROUP  BY c.name, t.owner
ORDER  BY c.name, t.owner;
```

**Câu hỏi:** Nếu chỉ thấy `SALES_PDB`, có chắc `HR_PDB` không có user `APP`?

**Gợi ý:** Không. Trước tiên kiểm tra quyền, `CONTAINER_DATA`, trạng thái PDB và điều kiện lọc.

### Bài 5 — Đối chiếu cột của bảng cùng tên

```sql
SELECT c.name AS container_name,
       col.column_id,
       col.column_name,
       col.data_type
FROM   cdb_tab_columns col
JOIN   v$containers c
       ON c.con_id = col.con_id
WHERE  col.owner = 'APP'
AND    col.table_name = 'ORDERS'
ORDER  BY c.name, col.column_id;
```

**Câu hỏi:** Nếu `SALES_PDB` có cột `DISCOUNT_RATE` nhưng `HR_PDB` không có, có thể kết luận điều gì?

**Gợi ý:** Hai bảng cùng owner/table name ở hai PDB có cấu trúc khác nhau; cần phân tích quy trình triển khai/schema migration nếu mong muốn chúng giống nhau.

## 14. Checklist sử dụng khi viết báo cáo metadata

Trước khi gửi báo cáo cho nhóm quản trị hoặc phát triển, kiểm tra những điều sau:

| Câu hỏi | Cách xác minh |
| --- | --- |
| Báo cáo đang ở root hay PDB nào? | `SHOW CON_NAME`, `SYS_CONTEXT('USERENV','CON_NAME')` |
| Đang dùng user nào? | `SESSION_USER` |
| Cần xem object của mình hay object được cấp quyền? | Chọn `USER_*` hoặc `ALL_*` |
| Cần xem mọi schema của một PDB? | `DBA_*` từ đúng PDB, với quyền phù hợp |
| Cần xem nhiều PDB? | `CDB_*` từ root, theo quyền và phạm vi `CONTAINER_DATA` |
| Có thể có object trùng tên giữa các PDB? | Bao gồm `CON_ID` và tên container |
| Có chắc tất cả PDB đều được quan sát? | Đối chiếu `V$CONTAINERS`, trạng thái và quyền |
| Đang so sánh cùng loại metadata? | Kiểm tra định nghĩa view, cột và loại object |
| Kết quả không có dòng được hiểu thế nào? | Phân biệt không tồn tại với không có quyền/không đúng container |
| Có cần quyền mở rộng hơn không? | Xin quyền dictionary tối thiểu phục vụ mục tiêu, không tự mở rộng quyền nghiệp vụ |

**Mẫu tư duy chọn view:**

```text
Muốn xem metadata của đối tượng?
      |
      +-- Chỉ của user đang đăng nhập? ----> USER_*
      |
      +-- Các đối tượng user có thể truy cập? --> ALL_*
      |
      +-- Tất cả schema trong PDB hiện tại? --> DBA_* (đủ quyền)
      |
      +-- Nhiều PDB trong CDB?
               |
               +-- Kết nối ở CDB$ROOT
               +-- Có quyền dictionary/container phù hợp
               +-- Dùng CDB_* + CON_ID + tên container
```

## 15. Câu hỏi ôn tập

1. Tại sao `DBA_TABLES` chạy trong `CDB$ROOT` không thay thế được `CDB_TABLES` khi cần thống kê các PDB ứng dụng?
2. Một tài khoản ở `SALES_PDB` không sở hữu bảng `APP.ORDERS` nhưng có quyền `SELECT` trên bảng. Nên bắt đầu tra cứu bằng `USER_TABLES` hay `ALL_TABLES`?
3. Hai dòng `CDB_TABLES` cùng `OWNER='APP'` và `TABLE_NAME='ORDERS'` nhưng khác `CON_ID`. Có phải dữ liệu bị trùng không?
4. `ALL_TABLES` có nghĩa là xem được tất cả bảng của mọi schema trong CDB không?
5. Vì sao một common user ở root đọc được `CDB_USERS` nhưng vẫn có thể không thấy user ở một số PDB?
6. Có nên bỏ cột `CON_ID` khi xuất báo cáo `CDB_OBJECTS` ra CSV không?
7. Nếu user trong PDB chạy `SELECT * FROM DBA_TABLES` gặp `ORA-00942`, ta nên kiểm tra điều gì trước khi xin quyền quản trị rộng?
8. `ALTER SESSION SET CURRENT_SCHEMA=APP` có làm session thành user `APP` không?
9. Cần view nào để liệt kê tất cả object đang `INVALID` trong **một PDB**? Nếu muốn tra cứu nhiều PDB thì sao?
10. Vì sao phải ghi thêm tên PDB khi kiểm kê object hoặc user trùng tên?

**Gợi ý trả lời:**

1. `DBA_*` phản ánh container hiện tại; `CDB_*` cho phép nhìn metadata từ nhiều containers theo quyền.
2. `ALL_TABLES`; user không sở hữu bảng nên `USER_TABLES` không phù hợp.
3. Không; có thể là hai bảng độc lập ở hai PDB.
4. Không; chỉ trong phạm vi object user có thể truy cập tại container hiện tại.
5. Có thể bị giới hạn `CONTAINER_DATA`, quyền, trạng thái và khả năng quan sát container.
6. Không nên; mất `CON_ID` sẽ khó phân biệt object trùng tên giữa PDBs.
7. Xác định đúng container, xác minh tên view và quyền đọc dictionary hiện tại.
8. Không; chỉ đổi schema mặc định để phân giải tên.
9. `DBA_OBJECTS` trong PDB; `CDB_OBJECTS` từ root với quyền phù hợp để xem nhiều PDB.
10. Vì username/object name có thể trùng giữa các PDB; tên container xác định đúng nơi sở hữu.

## 16. Tài liệu Oracle để tra cứu tiếp

- [Oracle Database Concepts — Multitenant Architecture](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): nền tảng CDB, root, seed, PDB và phạm vi metadata.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): định nghĩa các data dictionary views và dynamic performance views.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản lý CDB/PDB, kết nối và điều hướng container.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): common/local users, quyền và phạm vi bảo mật trong môi trường multitenant.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): lệnh `ALTER SESSION` và các biểu thức SQL.
- [Oracle Database Reference — DBA_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TABLES.html): các cột và ý nghĩa metadata của bảng.
- [Oracle Database Reference — CDB_TABLES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/CDB_TABLES.html): tra cứu metadata bảng theo containers.
- [Oracle Database Reference — V$CONTAINERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-CONTAINERS.html): mã, tên và trạng thái các containers.

Khi tra cứu dictionary trong Oracle Multitenant, hãy xác định **container đang kết nối**, **phạm vi câu hỏi**, **quyền xem metadata** và **container ID của từng dòng kết quả**. Dùng `USER_*` để xem object mình sở hữu; `ALL_*` để xem object có thể truy cập; `DBA_*` để tra cứu metadata trong container hiện tại; và `CDB_*` kèm `CON_ID` khi cần báo cáo nhiều PDB với phạm vi quyền được phép.
