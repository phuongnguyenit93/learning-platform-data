# Mô hình multitenant và quan hệ giữa CDB root, seed và PDB trong Oracle Database

Oracle Database hỗ trợ kiến trúc **multitenant** để một **container database (CDB)** chứa nhiều **pluggable database (PDB)**. Mỗi PDB cung cấp một môi trường cơ sở dữ liệu tương đối độc lập cho ứng dụng, trong khi các PDB cùng chia sẻ hạ tầng quản lý và tài nguyên của CDB. Đây là sự thay đổi quan trọng so với mô hình một database gắn trực tiếp với một tập đối tượng ứng dụng: một Oracle instance có thể phục vụ nhiều PDB, và các thao tác quản trị phải xác định **đúng container**.

Một CDB cơ bản bao gồm ba loại container: **CDB root** (`CDB$ROOT`), **PDB seed** (`PDB$SEED`), và **các PDB do người dùng tạo**. Chúng liên quan mật thiết nhưng có trách nhiệm khác nhau. Nắm được mối quan hệ này giúp bạn kết nối đúng PDB, tạo schema đúng nơi, hiểu file dữ liệu được phân chia như thế nào và tránh thao tác nhầm tại root.

Sau bài học, bạn có thể:

- Phân biệt **CDB**, **instance**, **CDB root**, **PDB seed**, **user-created PDB** và **service name**.
- Giải thích root chứa những gì, seed được dùng để tạo PDB như thế nào và tại sao ứng dụng nên làm việc trong một PDB.
- Xác định container hiện tại bằng SQL*Plus, `SYS_CONTEXT` và các dynamic performance view.
- Phân biệt tài khoản **common** với **local**, phạm vi data dictionary và các đối tượng ứng dụng.
- Mô tả vòng đời PDB: tạo, mở, đóng, lưu trạng thái mở, clone, unplug/plug ở mức khái niệm.
- Hiểu tác động của việc dùng chung instance, bộ nhớ, redo, control file và tài nguyên vật lý.

> **Phạm vi thực hành:** Ví dụ dưới đây sử dụng CDB giả định tên `ORCLCDB`, PDB ứng dụng `LABPDB` và một listener chấp nhận service `LABPDB`. Tên và trạng thái thực tế phụ thuộc phiên bản, cách cài đặt và cấu hình của máy. Phần lớn lệnh là **truy vấn chỉ đọc**; các lệnh tạo hoặc mở PDB được đặt riêng cho môi trường lab do bạn quản trị.

## 1. Từ database truyền thống đến mô hình multitenant

### 1.1. Vấn đề mà multitenant giải quyết

Giả sử một tổ chức có ba ứng dụng: bán hàng, nhân sự và báo cáo. Mỗi ứng dụng muốn có bảng, người dùng, quyền, cấu hình và vòng đời dữ liệu riêng. Một cách triển khai truyền thống là tạo ba database độc lập, mỗi database có instance và cấu trúc quản lý riêng. Cách này tạo sự độc lập mạnh hơn ở cấp tiến trình nhưng kéo theo nhiều thành phần phải khởi động, giám sát và bảo trì.

Trong mô hình multitenant, DBA có thể đặt ba môi trường ứng dụng vào ba PDB cùng thuộc một CDB:

~~~text
                         ORACLE INSTANCE
                    SGA + background processes
                              |
                              v
+------------------------------------------------------------------+
|                    CONTAINER DATABASE (CDB)                       |
|                                                                  |
|  +------------------+       +--------------------+                |
|  | CDB$ROOT         |       | PDB$SEED           |                |
|  | shared metadata  |       | read-only template |                |
|  | CDB admin        |       | for creating PDBs  |                |
|  +------------------+       +--------------------+                |
|                                                                  |
|  +------------------+  +------------------+  +------------------+ |
|  | SALES_PDB        |  | HR_PDB           |  | REPORT_PDB       | |
|  | sales users      |  | HR users         |  | report users     | |
|  | tables, indexes  |  | tables, indexes  |  | tables, indexes  | |
|  | own datafiles    |  | own datafiles    |  | own datafiles    | |
|  +------------------+  +------------------+  +------------------+ |
+------------------------------------------------------------------+
                   Shared CDB-level infrastructure
                  (for example, control/redo logging)
~~~

PDB không phải một schema đơn lẻ. **Một PDB có thể chứa nhiều schema**, các bảng, chỉ mục, view, procedure, tài khoản, role và dữ liệu tương ứng. Từ góc nhìn phần lớn ứng dụng, kết nối vào PDB giống như kết nối vào một database thông thường.

Tuy nhiên, PDB cũng không phải một Oracle instance độc lập: trong CDB một instance, nhiều PDB dùng chung bộ nhớ SGA và các tiến trình nền. Vì vậy multitenant cung cấp **phân tách ở cấp database/container**, chứ không tự động bảo đảm mỗi ứng dụng có tài nguyên phần cứng hay tiến trình hệ điều hành riêng.

### 1.2. Phân biệt bốn khái niệm hay bị lẫn

| Khái niệm | Ví dụ | Bản chất |
| --- | --- | --- |
| **Oracle instance** | Instance có SID `ORCLCDB` | SGA cùng các tiến trình nền phục vụ database |
| **CDB** | Database `ORCLCDB` | Database vật lý gồm root, seed, các PDB; có control file và online redo log của CDB |
| **PDB** | `LABPDB` | Container chứa dữ liệu, schema và metadata riêng phục vụ một hoặc nhiều ứng dụng |
| **Database service** | `LABPDB`, hoặc tên dịch vụ khác do DBA tạo | Tên để client kết nối và được định tuyến vào PDB/container đích |

Tên **SID**, **CDB**, **PDB** và **service** đôi lúc trùng nhau do cách cài đặt, nhưng về ý nghĩa thì khác nhau. Ví dụ `sqlplus / as sysdba` trên máy server có thể kết nối local vào instance và bắt đầu ở `CDB$ROOT`, còn `sqlplus app_user@//db-host:1521/LABPDB` kết nối qua listener đến **service của PDB**. Việc đặt `ORACLE_SID=LABPDB` không biến PDB thành một instance riêng.

## 2. Ba loại container và quan hệ của chúng

| Đặc điểm | `CDB$ROOT` | `PDB$SEED` | User PDB, ví dụ `LABPDB` |
| --- | --- | --- | --- |
| Vai trò | Gốc của CDB và nơi quản trị thông tin dùng chung | Mẫu hệ thống chuẩn để tạo PDB mới | Môi trường chứa dữ liệu và đối tượng ứng dụng |
| Tên mặc định | `CDB$ROOT` | `PDB$SEED` | DBA/người tạo đặt tên |
| `CON_ID` điển hình | `1` | `2` | Từ `3` trở lên |
| Chứa data dictionary? | Có, gồm metadata chung của CDB | Có nền metadata mẫu để clone | Có metadata riêng của PDB và khả năng tham chiếu metadata chung |
| Datafile | Có các file hệ thống của root | Có file hệ thống seed | Có file của chính PDB (SYSTEM, SYSAUX và dữ liệu/tablespace tùy cấu hình) |
| Chứa bảng ứng dụng? | Thông thường **không** | **Không dùng** để tạo dữ liệu ứng dụng | **Có**, đây là nơi phù hợp |
| Trạng thái mở | Root mở để phục vụ CDB | Được duy trì ở dạng read-only theo thiết kế | Có thể `MOUNTED`, `READ ONLY` hoặc `READ WRITE` tùy thời điểm |
| Thao tác thường gặp | Quản lý PDB, common users, tài nguyên chung | Oracle sử dụng làm mẫu khi tạo PDB | DDL/DML, backup/recovery theo phạm vi PDB, quản lý schema và users |

Lưu ý về `CON_ID`: trong nhiều dynamic performance view, `CON_ID=0` biểu thị dữ liệu áp dụng cho **toàn CDB** hoặc toàn database theo ngữ cảnh của view; `1` tương ứng root, `2` tương ứng seed. Không được hiểu `CON_ID=0` là một PDB thứ tư.

### 2.1. `CDB$ROOT`: container gốc và nơi quản trị chung

**CDB root** là container trung tâm chứa metadata và những thành phần do Oracle quản lý để phối hợp các PDB. Nó bao gồm:

- Các đối tượng data dictionary chung, thông tin nhận diện và cấu trúc của CDB.
- Metadata về các PDB, thông tin quản trị tài nguyên và các đối tượng chung theo cơ chế Oracle.
- Common users/roles và các quyền được khai báo ở phạm vi phù hợp.
- Hạ tầng để thực hiện các lệnh quản trị CDB như xem danh sách PDB hoặc mở/đóng PDB.

Root thường có tablespace hệ thống riêng như `SYSTEM` và `SYSAUX`. Việc một đối tượng metadata được dùng chung **không có nghĩa toàn bộ dữ liệu của các PDB đều nằm trong root**. Mỗi PDB vẫn có file và cấu trúc lưu trữ riêng.

**Nguyên tắc quan trọng:** Đừng dùng `CDB$ROOT` như database ứng dụng. DBA thao tác ở root để quản trị CDB và PDB; bảng nghiệp vụ, schema ứng dụng và user ứng dụng nên được tạo trong PDB được chỉ định. Nhầm container khi chạy DDL có thể tạo sai loại user, lỗi quyền hoặc thao tác phạm vi rộng hơn dự định.

Root không được tạo từ seed như một user PDB. Root là thành phần lõi có từ lúc CDB được khởi tạo, còn seed cung cấp điểm xuất phát cho **các PDB mới**.

### 2.2. `PDB$SEED`: khuôn mẫu read-only của CDB

**PDB seed** là một PDB hệ thống được Oracle cung cấp bên trong CDB để làm **mẫu tạo PDB**. Seed có nền cấu trúc và data dictionary cần thiết cho PDB mới, nhờ đó quy trình tạo PDB có thể dùng một bộ khởi đầu nhất quán.

Quan hệ điển hình:

~~~text
                       CDB$ROOT
                          |
                   quan ly cac PDB
                          |
         +----------------+--------------------+
         |                                     |
         v                                     v
  PDB$SEED (mau)                     PDB hien co trong CDB
         |                                     ^
         | CREATE PLUGGABLE DATABASE           |
         +------> clone/tao file he thong ------+
                       cua PDB moi
~~~

Seed thường có tên cố định `PDB$SEED` và `CON_ID=2`. Nó được bảo vệ ở chế độ **read-only**, không dành cho kết nối ứng dụng hoặc chỉnh dữ liệu như một PDB thông thường. Không tạo user, table nghiệp vụ hoặc tự ý chỉnh datafile seed để “đặt mặc định” cho mọi PDB mới.

Khi tạo PDB theo cách mặc định từ seed, Oracle tạo bản sao/khởi tạo các file cần thiết và metadata của PDB mới (cách copy vật lý có thể tùy loại storage). Từ đó PDB có **danh tính, datafile và vòng đời riêng**. Những thay đổi bạn thực hiện trong PDB mới **không quay lại sửa seed**, và những DML trong PDB này không tự động lan sang các PDB khác.

Seed **không phải**:

- Bộ backup của toàn bộ CDB hoặc của PDB đang chạy.
- Một database test để thử DML.
- Nơi giữ mọi dữ liệu chung của ứng dụng.
- Bản đồng bộ liên tục của các user PDB.

### 2.3. User PDB: môi trường database cho ứng dụng

Một user PDB như `LABPDB` chứa:

- Các user, role và quyền **local**; một số đối tượng common có thể được nhìn thấy theo cơ chế Oracle.
- Schema objects: table, index, view, sequence, package, procedure, trigger và nhiều đối tượng khác.
- Tablespace và datafile riêng cho dữ liệu của PDB; các file hệ thống riêng phù hợp.
- Metadata của đối tượng và cài đặt áp dụng ở phạm vi PDB.
- Service để các client kết nối; mỗi PDB có thể có nhiều service được cấu hình.

Ví dụ:

~~~text
CDB: ORCLCDB
 |
 +-- CDB$ROOT                (quan tri CDB)
 +-- PDB$SEED                (mau read-only)
 +-- LABPDB                  (PDB thuc hanh)
 |    +-- LAB_USER schema
 |    |    +-- ORDERS
 |    |    +-- ORDER_ITEMS
 |    +-- AUDIT_USER schema
 |    +-- SYSTEM / SYSAUX / USERS tablespaces
 |
 +-- REPORTPDB               (PDB bao cao rieng)
      +-- REPORT_USER schema
      +-- REPORTS table
~~~

`LAB_USER` và `AUDIT_USER` chỉ là ví dụ về **schema/user trong một PDB**. Việc tách các user thành các schema **không tạo thêm PDB**. Ngược lại, việc tạo `REPORTPDB` tạo một container mới với phạm vi metadata, users và dữ liệu của riêng nó.

## 3. Ranh giới giữa phần dùng chung và phần riêng

### 3.1. Chia sẻ instance, tách dữ liệu ở cấp container

Trong CDB với **một instance**, các PDB chia sẻ:

- SGA, background processes và hạ tầng xử lý database của instance.
- Control file của CDB và hệ thống online redo log ở cấp CDB.
- Hạ tầng quản trị, monitoring và nhiều cơ chế backup/recovery của Oracle.
- CPU, bộ nhớ, I/O và tài nguyên vật lý theo chính sách phân bổ của môi trường.

Mỗi PDB có:

- Datafile, tablespace và object data/metadata gắn với container của nó.
- User/schema local, các đối tượng và privilege tương ứng.
- Trạng thái `OPEN`/`MOUNTED` và service kết nối của riêng PDB.
- Một số tham số có thể thay đổi ở phạm vi PDB theo những giới hạn Oracle cho phép.

~~~text
                    SHARED INSTANCE / CDB
          +-------------------------------------+
          | SGA, LGWR, DBWR, SMON, PMON, ...   |
          | CDB control file, online redo logs  |
          +------------------+------------------+
                             |
          +------------------+------------------+
          |                  |                  |
          v                  v                  v
      CDB$ROOT           PDB: SALES        PDB: REPORT
     datafiles           datafiles          datafiles
     root metadata       user objects       user objects
~~~

Vì redo được quản lý ở cấp CDB, một online redo log có thể chứa redo liên quan đến nhiều PDB. Dữ liệu nghiệp vụ vẫn nằm trong các datafile của container liên quan. Kiến trúc lưu trữ PDB có nhiều chi tiết hơn theo phiên bản (ví dụ local undo versus shared undo); không mặc định mọi loại cấu trúc bên trong đều có một tệp duy nhất trên mỗi PDB.

**Hệ quả vận hành:** Nếu instance hoặc một thành phần cấp CDB gặp lỗi nghiêm trọng, nhiều PDB có thể cùng bị ảnh hưởng. Phân tách logic giữa PDB không thay thế sao lưu, phân quyền và thiết kế tính sẵn sàng ở cấp hệ thống.

### 3.2. Data dictionary: chung nhưng vẫn có ranh giới

Oracle data dictionary gồm thông tin về đối tượng, user, quyền, tablespace, database và nhiều metadata khác. Trong multitenant:

- Root lưu các đối tượng và metadata dùng chung ở cấp CDB.
- PDB có metadata riêng về các đối tượng của nó.
- Oracle có cơ chế **metadata links** và **data links** cho một số đối tượng chung, giúp tránh sao chép không cần thiết và cung cấp cách nhìn phù hợp trong từng container.
- Một PDB thường nhìn dữ liệu của **container hiện tại** qua các `DBA_*`, `ALL_*`, `USER_*` view; nhiều `CDB_*` view trong root có thể tổng hợp dữ liệu từ nhiều container và cung cấp cột `CON_ID`.

Không suy luận rằng root có thể xem mọi bảng nghiệp vụ bằng một lệnh `SELECT * FROM table` như thể schema nào cũng nằm trong root. Việc xem metadata và dữ liệu xuyên PDB vẫn phải tuân thủ cơ chế view, đặc quyền, trạng thái mở của PDB và chính sách container-data của tài khoản.

### 3.3. Phân tách bảo mật và tài nguyên

PDB giúp cách ly user/schema, cấu hình và nhiều thao tác quản lý. Tuy vậy:

- **Common user** có thể có phạm vi hoạt động trên nhiều container nếu được cấp quyền phù hợp.
- Common/system privileges không được mặc định trao cho user ứng dụng.
- PDB dùng chung instance nên vẫn có thể ảnh hưởng tài nguyên lẫn nhau nếu không có Resource Manager và giới hạn phù hợp.
- Quyền host, quyền filesystem và quản trị CDB là các ranh giới quan trọng ngoài phân quyền SQL trong PDB.

Vì vậy dùng PDB là một cách tổ chức nhiều môi trường database trong cùng CDB, **không phải cam kết rằng chúng độc lập hoàn toàn như các máy chủ tách biệt**.

## 4. Kết nối: từ client đến đúng PDB

### 4.1. Vì sao kết nối đến PDB qua service?

Client bên ngoài không cần biết tên datafile hay vị trí seed. Nó kết nối tới listener bằng địa chỉ và **service name** do database đăng ký hoặc DBA cấu hình. Service xác định môi trường database đích.

~~~text
Client SQL*Plus
    |
    | user@//db-host.example.com:1521/LABPDB
    v
Oracle Net Listener
    |
    +--- service LABPDB ---> PDB LABPDB
    |
    +--- service REPORT_SVC ---> PDB REPORTPDB
~~~

Trong nhiều cài đặt, khi tạo một PDB, Oracle tạo service mặc định có tên phù hợp với PDB. Hệ thống thực tế có thể sử dụng service do DBA định nghĩa với tên **khác tên PDB**, do đó luôn kiểm tra thông tin service đúng thay vì tự đoán.

Ví dụ kết nối tới PDB qua SQL*Plus:

~~~bash
# Chay tren may co SQL*Plus client; thay host, service, user theo he thong.
sqlplus lab_user@//db-host.example.com:1521/LABPDB
~~~

SQL*Plus sẽ yêu cầu mật khẩu cho `lab_user`; không đặt mật khẩu trực tiếp trong tham số lệnh. Tài khoản `lab_user` phải tồn tại tại container/service được nhắm tới và có quyền `CREATE SESSION` phù hợp.

Khi kết nối thành công:

~~~sql
SHOW CON_NAME;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Kết quả mong đợi trong ví dụ là `CONTAINER_NAME = LABPDB` và `SESSION_USER = LAB_USER`. Kiểm tra container đặc biệt hữu ích khi bạn có nhiều môi trường dev/test/prod dùng schema name giống nhau.

### 4.2. Kết nối local dành cho DBA

Trên **máy chủ database** với Oracle Home/SID và tài khoản hệ điều hành có quyền OSDBA tương ứng:

~~~bash
# Ket noi local; chi danh cho nguoi co quyen quan tri.
sqlplus / as sysdba
~~~

Với CDB, phiên quản trị local thường bắt đầu ở `CDB$ROOT`:

~~~sql
SHOW CON_NAME;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

Nếu kết quả là `CDB$ROOT`, bạn đang ở **root**; không chạy lệnh tạo bảng, user ứng dụng hoặc xóa đối tượng nghiệp vụ như thể đã vào PDB. Trong các môi trường remote hoặc cấu hình xác thực khác, kết quả container ban đầu phụ thuộc cách kết nối; luôn kiểm tra thay vì tin vào tên SID.

### 4.3. Thao tác chuyển container của tài khoản quản trị

Một common administrative user có quyền cần thiết có thể thay đổi container hiện tại:

~~~sql
-- Chi thuc hien trong phien quan tri duoc cap quyen.
SHOW CON_NAME;

ALTER SESSION SET CONTAINER = LABPDB;
SHOW CON_NAME;

-- Quay lai root neu tai khoan va quyen cho phep.
ALTER SESSION SET CONTAINER = CDB$ROOT;
SHOW CON_NAME;
~~~

`ALTER SESSION SET CONTAINER` không phải quyền mặc định của một local user. Ứng dụng nên **kết nối trực tiếp đến service PDB**, không tự chuyển container qua quyền quản trị CDB. Trong phiên `SYSDBA`, tên user/schema và đặc quyền có phạm vi nhạy cảm; không sử dụng loại phiên này cho thao tác DML thông thường của ứng dụng.

## 5. Kiểm tra cấu trúc CDB bằng các truy vấn chỉ đọc

Các ví dụ sau dành cho SQL*Plus hoặc công cụ SQL tương thích, thường cần tài khoản DBA hoặc quyền được cấp để đọc `V$`/`CDB_*` view. Nếu đang học trên hệ thống chia sẻ, hãy nhờ DBA cung cấp các kết quả tương đương; không cấp `SYSDBA` cho tài khoản ứng dụng chỉ để đọc một số view.

### 5.1. Xác nhận đây là CDB

~~~sql
SELECT name, cdb, open_mode
FROM v$database;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
~~~

Trong `V$DATABASE`, cột `CDB` thường trả `YES` đối với container database. `OPEN_MODE` phản ánh trạng thái database; trạng thái mở của **từng PDB** cần xem riêng. Các hệ thống legacy có thể có cấu hình non-CDB; khi `CDB=NO`, các khái niệm root/seed/PDB ở bài này không áp dụng theo cùng cách.

### 5.2. Liệt kê root, seed và user PDB

Thực hiện ở root với quyền phù hợp:

~~~sql
SELECT con_id, name, open_mode, restricted
FROM v$containers
ORDER BY con_id;

SHOW PDBS;
~~~

Một kết quả **minh họa**, không phải kết quả bắt buộc trên mọi máy:

~~~text
CON_ID  NAME       OPEN_MODE
------  ---------  ----------
1       CDB$ROOT   READ WRITE
2       PDB$SEED   READ ONLY
3       LABPDB     READ WRITE
4       REPORTPDB  MOUNTED
~~~

Các mốc nhận diện:

- `CON_ID=1`: root.
- `CON_ID=2`: seed; thường ở trạng thái `READ ONLY`.
- `CON_ID>=3`: các PDB khác, ID được Oracle gán trong CDB.
- `OPEN_MODE=MOUNTED`: PDB chưa được mở để phục vụ truy vấn ứng dụng bình thường.
- `OPEN_MODE=READ ONLY`: PDB được mở để đọc.
- `OPEN_MODE=READ WRITE`: PDB được mở để thực hiện DML/DDL nếu người dùng có quyền.

`CON_ID` là định danh trong ngữ cảnh CDB, **không phải khóa định danh kinh doanh bền vững khi chuyển PDB giữa CDB**. Các định danh khác như PDB GUID được sử dụng trong một số tác vụ quản trị di chuyển/phục hồi.

### 5.3. Liệt kê PDB và thời điểm mở

~~~sql
SELECT con_id, name, open_mode, restricted, open_time
FROM v$pdbs
ORDER BY con_id;
~~~

`V$PDBS` là view chuyên về các PDB; trong phiên quản trị root, nó cho phép quan sát PDB seed và những user PDB hiện có. Nếu PDB đang `MOUNTED`, điều đó **không mặc nhiên là lỗi**: có thể PDB chưa được mở sau lần khởi động instance hoặc đã được DBA đóng có chủ đích.

### 5.4. Xem datafile thuộc container nào

Ở root, khi cần biết datafile gắn với root/seed/PDB, có thể dùng:

~~~sql
SELECT con_id, file#, name, status
FROM v$datafile
ORDER BY con_id, file#;
~~~

Ví dụ, một số dòng có `CON_ID=1` thuộc root; `CON_ID=2` thuộc seed; `CON_ID=3` có thể thuộc `LABPDB` nếu PDB đó đang mang ID 3. Đường dẫn file có thể là filesystem, Oracle Managed Files (OMF) hoặc ASM (bắt đầu bằng `+DATA`…). **Không chuyển/xóa file trực tiếp ở hệ điều hành** theo kết quả truy vấn; Oracle quản lý metadata và consistency của các file này.

### 5.5. Nhận biết phạm vi metadata trong root

Nhiều CDB dictionary view có cột `CON_ID`, giúp người quản trị biết một bản ghi thuộc container nào. Ví dụ, nếu quyền và trạng thái PDB cho phép:

~~~sql
SELECT con_id, username, common
FROM cdb_users
WHERE username IN ('SYS', 'SYSTEM', 'LAB_USER')
ORDER BY con_id, username;
~~~

Cùng một tên `SYS` hoặc `SYSTEM` có thể xuất hiện trong nhiều container với `CON_ID` khác nhau do tính chất common/system account và cơ chế metadata. `LAB_USER` nếu được tạo local tại `LABPDB` chỉ thuộc phạm vi PDB đó. Kết quả thực tế còn phụ thuộc quyền truy vấn, PDB mở hay đóng và các chính sách liên quan.

## 6. Common users, local users và ranh giới quyền

### 6.1. Local user

**Local user** thuộc một PDB. Ví dụ, `LAB_USER` có thể sở hữu bảng `ORDERS` trong `LABPDB`. Local user không trở thành user của root hoặc các PDB khác chỉ vì các container cùng nằm trong một CDB.

Người quản trị PDB có thể được cấp quyền phù hợp để tạo user local, cấp role và quản lý schema trong PDB. Khi tạo user trong PDB, lệnh có tác dụng **trong PDB hiện tại**; trước mỗi thao tác quản trị nên kiểm tra `SHOW CON_NAME`.

### 6.2. Common user

**Common user** là tài khoản được quản lý ở phạm vi CDB và có thể tồn tại trong nhiều container, với quyền hoạt động phụ thuộc các đặc quyền và cách cấp quyền. Trong cấu hình mặc định, common user do DBA tạo ở CDB root thường phải có tiền tố như `C##` (theo giá trị `COMMON_USER_PREFIX`); Oracle cung cấp các common/system accounts riêng.

Điều này lý giải lỗi thường gặp khi người mới học đăng nhập vào `CDB$ROOT` và thử tạo user ứng dụng bình thường:

~~~sql
-- VI DU KHONG NEN CHAY: trong root, lenh tao local user
-- co the bi tu choi do quy tac common-user name.
CREATE USER app_user IDENTIFIED BY "example_password";
~~~

Trên các bản cài phổ biến, lỗi `ORA-65096: invalid common user or role name` có thể xuất hiện do đang tạo user ở root mà tên không tuân theo quy tắc common user. **Giải pháp cho schema ứng dụng là chuyển đến đúng PDB bằng service hoặc qua phiên quản trị, không phải sửa `COMMON_USER_PREFIX` để lách quy tắc.**

Quyền `CONTAINER=ALL` và `CONTAINER=CURRENT` trong một số thao tác common user/privilege là các cơ chế quản trị khác nhau; đừng giả định một quyền được cấp tại root mặc nhiên cho ứng dụng đầy đủ quyền trong mọi PDB. Common users cần được cấp quyền tối thiểu, đặc biệt trên môi trường có dữ liệu của nhiều nhóm.

### 6.3. Local role và common role

Tương tự users, một role có thể là local hoặc common theo nơi tạo/phạm vi. Role local dùng trong PDB, common role được thiết kế để sử dụng trong nhiều container khi quản trị đúng cách. Nhìn tên role chưa đủ để biết phạm vi; có thể tra các dictionary view thích hợp và cột `COMMON`.

### 6.4. Kiểm tra container trước DDL

Thói quen an toàn:

~~~sql
SHOW CON_NAME;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;

-- Chi sau khi xac dinh dung PDB va quyen moi chay DDL.
~~~

Khi vận hành nhiều PDB có cùng schema/table name, kiểm tra tên container là một phần của quy trình bảo vệ dữ liệu, không chỉ là thao tác tiện ích.

## 7. Vòng đời của một PDB

### 7.1. Tạo PDB từ seed

Một quy trình khái niệm để tạo một user PDB mới là:

~~~text
CDB$ROOT
    |
    | CREATE PLUGGABLE DATABASE ...
    v
PDB$SEED lam mau
    |
    | Oracle tao datafile va metadata cho PDB moi
    v
LABPDB moi (ban dau thuong MOUNTED)
    |
    | ALTER PLUGGABLE DATABASE LABPDB OPEN
    v
LABPDB READ WRITE
    |
    +--> tao local users, schema, tablespace, ung dung
~~~

Một **PDB tạo từ seed** không phải bản sao của một user PDB khác. Khi clone từ một PDB nguồn, Oracle dùng metadata/datafile của PDB nguồn theo quy trình riêng; còn khi unplug/plug, PDB được đưa ra/nhập vào CDB phù hợp. Cả ba đều có thể dẫn đến một PDB, nhưng **nguồn và điều kiện thao tác khác nhau**.

Về mặt thực hành, việc tạo PDB mới cần:

- Tài khoản DBA có quyền quản trị tại `CDB$ROOT`.
- CDB đã mở và cấu hình môi trường tạo file phù hợp (Oracle Managed Files, ASM hoặc quy tắc file-name conversion).
- Dung lượng lưu trữ, tương thích phiên bản và quyền sử dụng theo chính sách của hệ thống.
- Kế hoạch cấp service, user admin, backup và giới hạn tài nguyên khi sử dụng.

### 7.2. Ví dụ lệnh tạo/mở PDB trong một lab riêng

**Chỉ đọc đoạn này như mẫu thao tác quản trị.** Nếu được giao quyền trên **CDB lab độc lập**, sử dụng giá trị thực tế và tuân theo cách quản lý file của bản cài. Ví dụ dưới đây giả định Oracle Managed Files đã được cấu hình để Oracle xác định nơi tạo datafile:

~~~sql
-- Phien DBA tai CDB$ROOT tren lab rieng.
SHOW CON_NAME;
SHOW PARAMETER db_create_file_dest;

-- Thay mat khau mau bang mat khau manh va khong luu trong log/script chung.
CREATE PLUGGABLE DATABASE LABPDB
    ADMIN USER LAB_ADMIN IDENTIFIED BY "ReplaceWithStrongPassword_123";

-- Sau khi tao, PDB thuong can duoc mo.
ALTER PLUGGABLE DATABASE LABPDB OPEN READ WRITE;

-- Luu trang thai mo de Oracle co the khoi phuc sau restart instance.
ALTER PLUGGABLE DATABASE LABPDB SAVE STATE;
~~~

Nếu `DB_CREATE_FILE_DEST` không được cấu hình và Oracle không có cơ chế quản lý tên file thích hợp, mẫu `CREATE PLUGGABLE DATABASE` ở trên có thể không chạy; môi trường dùng filesystem có thể cần `FILE_NAME_CONVERT` hoặc cấu hình tạo file khác. **Không chạy lệnh chỉ để kiểm tra cú pháp trên production**, vì `CREATE PLUGGABLE DATABASE` thực sự tạo container và datafile, còn `OPEN`/`SAVE STATE` thay đổi trạng thái vận hành.

Mật khẩu ở ví dụ là giá trị minh họa bắt buộc phải thay trước khi sử dụng. Khi thiết kế môi trường thật, tránh đưa mật khẩu rõ vào tài liệu chia sẻ, lịch sử lệnh và log; dùng quy trình quản lý bí mật được tổ chức hỗ trợ.

### 7.3. Mở và đóng PDB

Một PDB có thể được DBA mở/đóng độc lập với các PDB khác ở mức phù hợp:

~~~sql
-- Chi danh cho phien DBA o root, khong chay tren PDB dang phuc vu user.
ALTER PLUGGABLE DATABASE LABPDB OPEN READ WRITE;

-- Dong PDB, lam gian doan phien/ung dung dang dung PDB nay:
ALTER PLUGGABLE DATABASE LABPDB CLOSE IMMEDIATE;
~~~

Lệnh đóng PDB có thể ngắt công việc đang chạy và gây lỗi cho ứng dụng. Không thực hiện trên PDB chia sẻ/production nếu chưa có kế hoạch. Tác động chính tập trung vào PDB được chỉ định, nhưng CDB và các thành phần hạ tầng vẫn là nguồn dùng chung.

Trạng thái `OPEN` của CDB **không đồng nghĩa mọi PDB đã mở**. Sau khi instance restart, một PDB có thể trở về `MOUNTED` nếu không có cơ chế lưu trạng thái/tự mở tương ứng. `ALTER PLUGGABLE DATABASE ... SAVE STATE` là một cách lưu ý định trạng thái mở đối với PDB; chi tiết phụ thuộc cấu hình và môi trường quản lý instance.

### 7.4. Clone, unplug và plug ở mức khái niệm

| Thao tác | Nguồn | Ý nghĩa |
| --- | --- | --- |
| **Create from seed** | `PDB$SEED` | Tạo PDB mới với nền hệ thống sạch, chưa chứa dữ liệu ứng dụng |
| **Clone PDB** | Một PDB nguồn | Tạo PDB mới dựa trên trạng thái/dữ liệu của PDB nguồn, tùy điều kiện clone |
| **Unplug PDB** | PDB hiện có | Chuẩn bị metadata và file để di chuyển/plug theo quy trình được hỗ trợ |
| **Plug PDB** | PDB đã unplug hoặc nguồn tương thích | Gắn PDB vào CDB khác hoặc cùng CDB theo điều kiện hỗ trợ |

Unplug/plug không chỉ là copy thư mục datafile bằng file explorer. Oracle yêu cầu metadata mô tả, kiểm tra tương thích và trình tự thao tác của database; đường dẫn, dịch vụ, charset, phiên bản, option, encryption và cấu hình lưu trữ có thể là điều kiện cần xử lý. Cần backup và kế hoạch chuyển đổi phù hợp trước khi thao tác với PDB quan trọng.

Ngoài user PDB thông thường, một số phiên bản/tính năng còn có **application container** với application root, application seed và application PDB. Đây là một cấp tổ chức đặc thù để quản lý ứng dụng dùng chung; không nhầm application root/application seed với **`CDB$ROOT`/`PDB$SEED`** vốn thuộc CDB chung.

## 8. Backup, recovery và ảnh hưởng đến các PDB

Vì nhiều PDB cùng dùng hạ tầng CDB, phạm vi sự cố và phạm vi recovery cần được phân biệt:

| Tình huống | Phạm vi ảnh hưởng thường gặp | Ý nghĩa |
| --- | --- | --- |
| Một user vô tình xóa table trong `LABPDB` | Dữ liệu/nghiệp vụ trong PDB liên quan | Khả năng khôi phục phụ thuộc backup/recovery, quyền và tính năng đang có |
| Datafile của một PDB bị mất | PDB/tablespace tương ứng có thể không hoạt động | Có thể cần restore/recover file hoặc PDB tùy sự cố |
| Instance crash | Tất cả PDB do instance đó phục vụ bị gián đoạn | Oracle dùng redo/control file và cơ chế instance recovery cấp CDB khi restart |
| Control file hoặc online redo quan trọng bị hỏng | Có thể ảnh hưởng toàn CDB | Không thể coi từng PDB là database vật lý hoàn toàn độc lập |
| Root hoặc hạ tầng CDB bị lỗi nghiêm trọng | Nhiều hoặc toàn bộ PDB có thể bị ảnh hưởng | Cần phương án bảo vệ/khôi phục CDB |

Oracle Recovery Manager (**RMAN**) có thể hỗ trợ các thao tác backup/recovery theo phạm vi CDB và PDB tùy phiên bản/cấu hình. Việc có một PDB riêng **không đồng nghĩa tự động có backup riêng**. Một thiết kế vận hành cần xem xét backup datafile, control file, archived redo, retention, RPO/RTO và kiểm thử restore.

Trong multitenant, online redo log được quản lý ở cấp CDB; các bản ghi redo có thể liên quan đến nhiều PDB. Do đó khả năng recover một PDB tại thời điểm nào đó vẫn phụ thuộc hạ tầng redo và điều kiện recovery mà Oracle hỗ trợ. Không được xóa archived redo chỉ vì “PDB của mình không dùng file này”.

## 9. Thực hành xác định quan hệ root, seed và PDB

Phần này ưu tiên **đọc và quan sát**, có thể thực hiện trên một CDB đã có sẵn. Bài thực hành không bắt buộc tạo PDB mới. Nếu tài khoản không được phép xem view quản trị, yêu cầu DBA thực hiện phần truy vấn tương ứng và cung cấp kết quả.

### Bước 1 — Xác định container của phiên hiện tại

Kết nối SQL*Plus hoặc công cụ SQL phù hợp, chạy:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Nếu có SQL*Plus, có thể chạy thêm `SHOW CON_NAME;`. Khi bạn nhận được tên một PDB như `LABPDB`, hãy ghi lại. Nếu kết quả là `CDB$ROOT`, đó là phiên ở root, không phù hợp để thực hành tạo bảng ứng dụng.

### Bước 2 — Quan sát toàn bộ container từ root

Dưới phiên quản trị đủ quyền:

~~~sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

Tìm ba nhóm: root (`1`), seed (`2`), các user PDB (`3` trở lên). Đếm số user PDB hiện có mà không tính root và seed. Không giả định số này cố định trên mọi môi trường.

### Bước 3 — Quan sát PDB seed

Từ kết quả `V$CONTAINERS` hoặc `SHOW PDBS`, xác nhận `PDB$SEED` được đánh dấu `READ ONLY` theo thiết kế. Không thử tạo bảng hay thay đổi user ở seed; bài thực hành chỉ cần giải thích **vì sao seed nên bất biến** đối với thao tác nghiệp vụ.

### Bước 4 — Xác nhận trạng thái PDB ứng dụng

Từ root:

~~~sql
SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LABPDB';
~~~

Nếu không trả dòng, `LABPDB` có thể không tồn tại hoặc không phải tên PDB trên hệ thống này. Thay `LABPDB` bằng tên thực tế. Nếu `OPEN_MODE=MOUNTED`, không tiếp tục kết nối ứng dụng cho đến khi DBA xác nhận PDB được phép mở.

### Bước 5 — Kết nối vào PDB bằng service

Từ máy client:

~~~bash
sqlplus lab_user@//db-host.example.com:1521/LABPDB
~~~

Sau khi đăng nhập và nhập mật khẩu theo nhắc lệnh:

~~~sql
SHOW CON_NAME;

SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    USER AS current_user
FROM dual;
~~~

Giải thích vì sao giá trị `CON_NAME` và `CURRENT_USER` ở đây khác phiên DBA tại root. Nếu ứng dụng có nhiều service trỏ vào cùng PDB, `SERVICE_NAME` có thể khác hẳn tên PDB trong khi `CON_NAME` vẫn là container mong đợi.

### Bước 6 — Đối chiếu cấu trúc datafile

Trong phiên root được cấp quyền:

~~~sql
SELECT con_id, COUNT(*) AS datafile_count,
       ROUND(SUM(bytes) / 1024 / 1024) AS datafile_mb
FROM v$datafile
GROUP BY con_id
ORDER BY con_id;
~~~

Kết quả cho thấy các container có nhóm datafile được quản lý riêng. Con số `DATAFILE_MB` là tổng kích thước datafile đang được kê khai, **không phải dung lượng dữ liệu ứng dụng thực tế** hay dung lượng còn trống.

### Bước 7 — Rút ra mô hình kiến trúc

Tự hoàn thành sơ đồ trên dữ liệu bạn vừa thấy:

~~~text
CDB thuc te: _______________________
Instance/SID: ______________________
Root: CDB$ROOT (CON_ID=1)
Seed: PDB$SEED (CON_ID=2)
User PDBs: _________________________
PDB dung de thuc hanh: ____________
Service dung de ket noi: __________
CON_NAME cua phien ung dung: ______
~~~

Định danh instance có thể lấy qua `V$INSTANCE` nếu được phép; **đừng suy từ service name**. Bài thực hành hoàn tất khi bạn giải thích được vì sao chỉ cần một CDB và một instance vẫn có thể thấy nhiều PDB độc lập về schema/dữ liệu.

## 10. Các lỗi hiểu nhầm và cách khoanh vùng

| Biểu hiện | Nguyên nhân có thể | Cách tiếp cận |
| --- | --- | --- |
| `ORA-65096` khi tạo user như `APP_USER` | Đang ở root và tên user không hợp lệ cho common user | `SHOW CON_NAME`; tạo local user trong đúng PDB theo quyền và quy trình |
| `ORA-65011` | Tên PDB được chỉ định không tồn tại trong CDB/ngữ cảnh tương ứng | Kiểm tra `V$PDBS`/`V$CONTAINERS` và chính tả tên PDB |
| `ORA-65040` | Thử thao tác không được phép trong PDB/container hiện tại | Xác định lệnh phải chạy ở root hay PDB; dùng tài khoản phù hợp |
| `ORA-12514` khi kết nối qua service PDB | Listener chưa biết service được yêu cầu | Xác nhận service name, trạng thái mở PDB, listener và đăng ký service |
| Đã mở CDB nhưng không kết nối được PDB | PDB vẫn `MOUNTED`, service không sẵn sàng hoặc user không hợp lệ | Xem `V$PDBS.OPEN_MODE`; kiểm tra service và thông tin đăng nhập |
| Đăng nhập thành công nhưng không thấy table | Đang ở PDB/schema khác hoặc thiếu quyền | Kiểm tra `CON_NAME`, `USER`, schema owner và privileges |
| DBA tạo bảng trong root, ứng dụng PDB không thấy | Đã chạy DDL sai container | Xem `SHOW CON_NAME` trước thao tác; tổ chức lại đối tượng theo quy trình DBA |
| Sau restart PDB trở lại `MOUNTED` | Chưa có cấu hình/lưu trạng thái mở hoặc cơ chế quản lý khác | DBA kiểm tra `SAVE STATE` và cách instance được khởi động |

Một số lỗi có nhiều nguyên nhân; mã lỗi giúp khoanh vùng nhưng không đủ để khẳng định ngay một cấu hình cụ thể. Nên quan sát container, service và trạng thái PDB **trước khi sửa tham số hay chạy lệnh quản trị**.

### 10.1. Sai lầm: “PDB chính là một schema”

Một PDB chứa nhiều schema; schema là tập các đối tượng do một user sở hữu. Chuyển schema không tạo PDB mới, còn tạo PDB mới tạo ra ranh giới container và file/metadata riêng.

### 10.2. Sai lầm: “Root là nơi chứa tất cả bảng ứng dụng”

Root chứa metadata và đối tượng dùng chung của CDB. Bảng nghiệp vụ nên ở PDB. Một CDB dictionary view tại root có thể hiển thị metadata của nhiều PDB theo quyền, nhưng điều đó **không biến root thành schema chung của tất cả PDB**.

### 10.3. Sai lầm: “Seed cập nhật tự động khi PDB thay đổi”

Seed là mẫu được Oracle quản lý. Mỗi PDB sau khi tạo có vòng đời và dữ liệu riêng; thao tác `INSERT/UPDATE` trong một PDB không sửa seed, root hoặc những PDB khác.

### 10.4. Sai lầm: “Mỗi PDB có instance và redo log riêng”

Trong một CDB instance đơn, các PDB dùng chung SGA, background processes, control file và online redo log ở cấp CDB. PDB có datafile và metadata riêng, nhưng không có instance độc lập như một database cài riêng trên hệ điều hành.

### 10.5. Sai lầm: “PDB mở khi CDB mở”

CDB được `OPEN` không có nghĩa mọi PDB đều `READ WRITE`. Quan sát `V$PDBS`/`V$CONTAINERS` và quản lý trạng thái PDB theo chính sách vận hành.

## 11. Câu hỏi ôn tập

1. CDB gồm những loại container nào? Vì sao `PDB$SEED` không được dùng làm database ứng dụng?
2. Khi tạo `LABPDB` từ seed, dữ liệu của `LABPDB` sau này có tự ghi ngược vào seed không?
3. Một PDB chứa hai schema `APP_USER` và `REPORT_USER`. Vậy trong PDB đó có bao nhiêu database/instance?
4. `CDB$ROOT` khác một user PDB về vai trò, metadata và nơi nên đặt table nghiệp vụ như thế nào?
5. `CON_ID=0` trong một số `V$` view có phải là tên của một PDB không?
6. Vì sao DBA cần kiểm tra `SHOW CON_NAME` trước khi `CREATE USER` hoặc `ALTER PLUGGABLE DATABASE`?
7. Nếu cả hai PDB `SALES_PDB` và `REPORT_PDB` nằm chung một CDB instance, việc instance crash ảnh hưởng những PDB nào?
8. Làm thế nào kết nối ứng dụng trực tiếp vào PDB bằng service thay vì dùng `ALTER SESSION SET CONTAINER`?
9. Vì sao cùng một PDB có thể có nhiều service name, và service name khác tên PDB vẫn có thể hợp lệ?
10. PDB đang `MOUNTED` có phục vụ truy vấn DML ứng dụng bình thường không? Trạng thái nào phù hợp?
11. Vì sao khi di chuyển PDB sang CDB khác không thể coi đây chỉ là thao tác copy datafile bằng hệ điều hành?
12. Một CDB có backup, nhưng user PDB không bao giờ được kiểm thử restore. Điều gì vẫn còn là rủi ro?

**Gợi ý trả lời:** (1) root, seed, user PDB; seed là mẫu read-only; (2) không; (3) một PDB chứa hai schema và dùng instance CDB đang phục vụ nó; (4) root quản trị chung, user PDB chứa nghiệp vụ; (5) không, thường biểu thị phạm vi toàn CDB; (6) tránh thao tác sai phạm vi; (7) các PDB do instance đó phục vụ đều có thể bị gián đoạn; (8) dùng chuỗi `user@//host:port/service`; (9) service là tên định tuyến có thể được DBA cấu hình; (10) không, cần PDB mở phù hợp, thường `READ WRITE` để DML; (11) cần metadata/compatibility/quy trình plug-in; (12) backup tồn tại không chứng minh restore và recovery thành công.

## Tài liệu tham khảo Oracle

- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): cơ sở về kiến trúc multitenant, instance và các thành phần database.
- [Oracle Multitenant Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/): quản lý CDB, root, seed, PDB, common/local user, lifecycle, clone và unplug/plug.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): tra cứu các view `V$DATABASE`, `V$CONTAINERS`, `V$PDBS`, `V$DATAFILE` và các tham số liên quan.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): cú pháp `CREATE PLUGGABLE DATABASE`, `ALTER PLUGGABLE DATABASE` và `ALTER SESSION`.
