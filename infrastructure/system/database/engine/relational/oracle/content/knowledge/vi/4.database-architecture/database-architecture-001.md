# Phân biệt database vật lý, instance và các đối tượng logic

Khi làm việc với Oracle Database, ba khái niệm thường xuất hiện cùng nhau nhưng có vai trò khác nhau:

- **Database vật lý** là tập các file bền vững dùng để lưu dữ liệu và thông tin cần thiết để khôi phục, mở database.
- **Instance** là phần Oracle đang hoạt động: vùng nhớ và các tiến trình xử lý truy vấn, giao dịch, đọc/ghi dữ liệu.
- **Các đối tượng logic** là cách Oracle tổ chức và trình bày dữ liệu để người dùng thao tác, chẳng hạn *pluggable database* (PDB), schema, bảng, view, index, tablespace và segment.

Ví dụ, lệnh `SELECT * FROM APP_ORDERS` nhắc đến **bảng logic** `APP_ORDERS`. Oracle instance xử lý câu lệnh, tìm các block cần đọc trong bộ nhớ hoặc file. Các bản ghi tồn tại bền vững trong **datafile** dù instance tắt bình thường. Do đó, “bảng”, “database trên ổ đĩa” và “database đang chạy” không phải cùng một thực thể.

## 1. Nhìn tổng thể: ba lớp phối hợp như thế nào?

Một mô hình Oracle phổ biến có thể hình dung như sau:

```text
Ứng dụng / SQL client (JDBC, SQLcl, SQL Developer)
                     |
               Host + Port + Service
                     |
             Listener / kết nối
                     |
        +------------v----------------+
        | ORACLE INSTANCE             |
        | - SGA (vùng nhớ dùng chung)  |
        | - Các background processes  |
        | - Server processes phục vụ  |
        |   phiên làm việc            |
        +------------+----------------+
                     | Đọc/ghi và quản lý
        +------------v----------------+
        | ORACLE DATABASE             |
        | - Datafiles                 |
        | - Control files             |
        | - Online redo log files     |
        +-----------------------------+

Trong database dạng multitenant (CDB):
  CDB$ROOT    : metadata và quản trị dùng chung
  PDB$SEED    : PDB mẫu phục vụ tạo PDB mới
  APP_PDB     : PDB của ứng dụng
    Schema APP
      TABLE APP_ORDERS, INDEX, VIEW, PROCEDURE...
    Tablespaces -> segments -> extents -> data blocks
    Dữ liệu của các đối tượng được lưu trong datafiles.
```

Sơ đồ được đơn giản hóa: **PDB, schema, bảng và tablespace là những góc nhìn logic**, không phải các tiến trình riêng đứng cạnh instance. Các PDB có datafile thuộc phạm vi của mình nhưng dùng chung một số thành phần vật lý cấp CDB như control file và online redo log.

| Khái niệm | Bản chất | Ví dụ | Cần nhớ |
| --- | --- | --- | --- |
| Database vật lý | Tập file lưu trữ bền vững | `system01.dbf`, control file, redo log | Vẫn còn sau khi instance dừng, nếu file không bị xóa/hỏng |
| Instance | Bộ nhớ + tiến trình đang chạy | SGA, DBWn, LGWR | Được tạo khi khởi động; mất trạng thái bộ nhớ khi tắt |
| CDB / PDB | Ranh giới tổ chức database trong kiến trúc multitenant | `CDB$ROOT`, `APP_PDB` | PDB **không mặc nhiên là một instance riêng** |
| Schema | Không gian tên chứa các đối tượng thuộc một database user | `APP`, `HR` | Schema không đồng nghĩa với tablespace |
| Đối tượng SQL | Đối tượng người dùng thao tác theo tên | Table, view, index, sequence, package | Một số có segment chứa dữ liệu, một số chỉ có định nghĩa |
| Tablespace | Nhóm lưu trữ logic ánh xạ tới các file | `USERS`, `SYSTEM`, `TEMP` | Không phải thư mục hệ điều hành |
| Segment / extent / block | Các đơn vị cấp phát không gian dữ liệu | Segment của bảng hoặc index | Kết nối đối tượng logic với các block trong datafile |

## 2. Database vật lý: những gì thực sự nằm trên đĩa

Theo mô hình kiến trúc cơ bản, một Oracle database có ba loại file cốt lõi:

### 2.1. Datafiles — file chứa nội dung dữ liệu

**Datafile** chứa các Oracle data block của tablespace: dữ liệu bảng, index, dữ liệu từ điển, undo và những nội dung lưu trữ khác tùy loại tablespace. Tên thường có đuôi `.dbf`, nhưng tên file không phải tiêu chí xác định bản chất. Cùng một tablespace có thể sử dụng nhiều datafile; một datafile thuộc một tablespace tại một thời điểm.

Ví dụ mô tả một cách bố trí file (chỉ là đường dẫn minh họa):

```text
/u02/oradata/DEMO/system01.dbf   -> tablespace SYSTEM
/u02/oradata/DEMO/sysaux01.dbf   -> tablespace SYSAUX
/u02/oradata/DEMO/users01.dbf    -> tablespace USERS
/u02/oradata/DEMO/users02.dbf    -> cũng có thể thuộc USERS
```

Với **PDB**, datafile có thể nằm trong cấu trúc thư mục do Oracle quản lý riêng cho PDB; tên và vị trí thực tế phụ thuộc cách cài, Oracle Managed Files (OMF), ASM hoặc storage cloud. Không nên suy đoán đường dẫn từ tên schema.

**Tempfile** là file vật lý phục vụ temporary tablespace, chẳng hạn cho sắp xếp, hash operation hoặc xử lý tạm trong SQL. Tempfile có vai trò và cách phục hồi khác datafile lưu dữ liệu bền vững; nó không phải nơi lưu bảng ứng dụng lâu dài.

### 2.2. Control files — thông tin điều khiển cấu trúc database

Control file lưu các thông tin cần thiết để Oracle nhận diện và quản lý database, chẳng hạn định danh database, cấu trúc/datafile, checkpoint và metadata phục vụ recovery. Khi database ở trạng thái **MOUNT**, Oracle đã mở control file nhưng chưa mở database để sử dụng thông thường.

Control file thường được **multiplex** thành nhiều bản sao trên các vị trí lưu trữ phù hợp, theo cấu hình quản trị. Mất toàn bộ control file có thể cản trở việc mount/mở database dù các file dữ liệu vẫn tồn tại.

### 2.3. Online redo log files — ghi nhận thay đổi để phục hồi

Redo ghi thông tin thay đổi dùng cho khôi phục sau sự cố. Oracle ghi redo từ redo log buffer xuống **online redo log**; khi commit thành công, bản ghi redo cần thiết cho giao dịch đã được ghi bền vững theo cơ chế commit của Oracle.

Điểm quan trọng: **không bắt buộc mọi block dữ liệu sửa đổi đã được DBWn ghi vào datafile đúng tại thời điểm commit**. Nếu instance gặp sự cố, Oracle có thể dùng redo để thực hiện *instance recovery*. Online redo log cũng thường được cấu hình thành các nhóm và member để bảo vệ trước mất file.

Trong chế độ `ARCHIVELOG`, các redo log đầy có thể được lưu thành **archived redo logs**, phục vụ chiến lược backup và media recovery. Đây là các file quan trọng đối với vận hành nhưng không thay thế datafile/control file.

### 2.4. Những file hỗ trợ không nên đánh đồng

| Thành phần | Công dụng | Phân biệt |
| --- | --- | --- |
| `SPFILE` / `PFILE` | Tham số khởi động instance | Không phải nơi lưu dòng dữ liệu ứng dụng |
| Password file | Xác thực các kết nối quản trị đặc quyền phù hợp | Không phải schema hay bảng |
| Archived redo logs | Redo đã lưu để hỗ trợ phục hồi | Khác online redo đang hoạt động |
| Tempfiles | Không gian tạm cho thao tác SQL | Không lưu dữ liệu ứng dụng bền vững |
| Backup/RMAN pieces | Bản sao phục vụ phục hồi | Là kết quả của kế hoạch backup, không phải datafile đang mở |
| Alert/trace logs | Thông tin chẩn đoán hoạt động | Không phải bản sao của bảng SQL |

Vì vậy, nói “backup database” đòi một chiến lược phục hồi nhất quán, không đơn giản là sao chép tùy ý một file `.dbf` khi instance đang chạy.

## 3. Instance: Oracle đang vận hành trong RAM và các tiến trình

Một **Oracle instance** gồm vùng nhớ dùng chung **SGA (System Global Area)** và một tập **background processes**. Khi có phiên kết nối, Oracle còn có *server processes* xử lý yêu cầu của phiên theo cấu hình kết nối. Instance mở và thao tác với database vật lý.

### 3.1. Thành phần bộ nhớ

| Khu vực | Vai trò tiêu biểu |
| --- | --- |
| **Database buffer cache** (trong SGA) | Giữ các bản sao data block được đọc từ datafile hoặc được chỉnh sửa trong bộ nhớ |
| **Shared pool** | Lưu cấu trúc SQL đã phân tích, execution plan, dictionary cache và các thông tin dùng chung |
| **Redo log buffer** | Giữ thông tin redo trước khi LGWR ghi ra online redo log |
| **PGA (Program Global Area)** | Bộ nhớ riêng gắn với tiến trình, phục vụ trạng thái xử lý và các vùng làm việc riêng; **không thuộc SGA** |

Tùy cấu hình Oracle còn có những vùng nhớ khác; không cần thuộc mọi tên vùng nhớ để phân biệt **dữ liệu bền vững trong file** với **trạng thái đang xử lý trong RAM**.

### 3.2. Một số background processes tiêu biểu

| Tiến trình | Việc chính |
| --- | --- |
| **DBWn** (Database Writer) | Ghi các data block đã thay đổi từ buffer cache xuống datafiles theo cơ chế của Oracle |
| **LGWR** (Log Writer) | Ghi redo từ redo log buffer vào online redo log |
| **CKPT** (Checkpoint) | Điều phối checkpoint, cập nhật thông tin checkpoint; **không trực tiếp làm công việc ghi toàn bộ data block thay DBWn** |
| **SMON** (System Monitor) | Thực hiện những công việc giám sát/phục hồi hệ thống theo chức năng của phiên bản Oracle |
| **PMON** (Process Monitor) | Giám sát và dọn dẹp những tài nguyên/tiến trình lỗi theo kiến trúc tiến trình hiện hành |
| **ARCn** (Archiver) | Lưu redo thành archived redo logs trong cấu hình `ARCHIVELOG` |

### 3.3. Luồng xử lý một giao dịch

Giả sử chương trình chạy:

```sql
UPDATE app_orders
   SET amount = amount + 100
 WHERE order_id = 42;

COMMIT;
```

Ở mức khái niệm:

1. Server process tiếp nhận SQL qua phiên kết nối, phân tích câu lệnh và tìm block liên quan.
2. Block có thể đã nằm trong **buffer cache** hoặc được đọc từ **datafile** vào buffer cache.
3. Oracle cập nhật trạng thái dữ liệu cần thiết trong bộ nhớ và tạo **redo records** mô tả thay đổi.
4. Tại `COMMIT`, redo cần thiết được LGWR ghi vào online redo log theo quy tắc bền vững của Oracle; ứng dụng nhận kết quả commit.
5. **DBWn có thể ghi data block xuống datafile vào thời điểm khác**. Điều đó không có nghĩa giao dịch đã commit sẽ bị mất khi có instance recovery bình thường: redo được dùng để khôi phục trạng thái hợp lệ.

Ví dụ này cho thấy **instance xử lý**, **file lưu bền vững**, còn **bảng `APP_ORDERS` là tên đối tượng logic** được truy vấn. Các bước ghi thực tế có tối ưu, cache, undo và cơ chế đồng thời phức tạp hơn; đây là mô hình giải thích, không phải thứ tự bắt buộc cho mọi I/O.

## 4. Một database và một instance có luôn tương ứng 1–1?

**Không.** Đây là điểm dễ nhầm khi chuyển từ máy cá nhân sang hệ thống doanh nghiệp.

### Single-instance

Trong một cấu hình thường gặp ở môi trường học:

```text
Instance A (SGA + background processes)
            |
            v
Database A (datafiles + control files + redo logs)
```

Một instance mở một database. Nếu tắt instance theo đúng quy trình, các file database vẫn ở trên storage và có thể được mở lại sau.

### Oracle RAC (Real Application Clusters)

Trong hệ thống **Oracle RAC**, nhiều instance trên các node khác nhau có thể truy cập **cùng một database vật lý** trên storage dùng chung:

```text
Node 1: Instance A ---------+
                            |
                            +---- Database chung
                            |     (datafiles, control files...)
Node 2: Instance B ---------+
```

Mỗi instance có SGA và background processes riêng. Cơ chế RAC phối hợp truy cập block và redo giữa các instance; những chi tiết này không thể mô phỏng bằng cách tùy ý cho hai Oracle instance thông thường trỏ tới cùng một thư mục chứa datafile.

| Cấu hình | Instance | Database vật lý | Điểm khác biệt |
| --- | --- | --- | --- |
| Single-instance | Thường 1 | 1 | Mô hình học phổ biến |
| RAC | Nhiều | 1 database chung | Cần kiến trúc và quyền sử dụng RAC phù hợp |
| Nhiều database độc lập trên một host | Mỗi database có instance của mình khi chạy | Nhiều | Không đồng nghĩa với một database có nhiều schema |

**PDB không phải instance RAC**. Một CDB có nhiều PDB thường vẫn được phục vụ bởi một instance ở mô hình single-instance; khi triển khai RAC, có thể có nhiều instance mở cùng CDB.

## 5. CDB, PDB, schema: các ranh giới logic khác nhau

Các release Oracle hiện đại sử dụng kiến trúc **multitenant**:

- **CDB (Container Database)** là database chứa các container, có cấu trúc vật lý và các file cấp CDB. Nó bao gồm **CDB root**, **PDB seed** và các **PDB** ứng dụng.
- **`CDB$ROOT`** chứa metadata và các thành phần quản trị dùng chung; không phải nơi mặc định tạo bảng nghiệp vụ của từng ứng dụng.
- **`PDB$SEED`** là khuôn mẫu Oracle dùng khi tạo PDB, không phải khu vực học viên tự tạo dữ liệu ứng dụng.
- **PDB (Pluggable Database)** là môi trường database logic tương đối độc lập trong CDB, có metadata, schema và datafiles của mình; người dùng thường kết nối qua **service của PDB**.
- **Schema** là tập các đối tượng thuộc một database user trong container tương ứng. Nhiều schema có thể tồn tại trong một PDB.

Ví dụ:

```text
CDB: TRAINING_CDB                     -> database vật lý + instance mở CDB
  CDB$ROOT                            -> container gốc
  PDB$SEED                            -> container mẫu
  PDB: SALES_PDB                      -> một môi trường ứng dụng
    Schema SALES_APP                  -> user + các đối tượng của user
      SALES_APP.CUSTOMERS             -> table
      SALES_APP.ORDERS                -> table
      SALES_APP.IX_ORDERS_DATE        -> index
    Schema REPORT_APP                 -> schema khác trong cùng PDB
      REPORT_APP.ORDER_REPORT         -> view
  PDB: TRAINING_PDB                   -> PDB khác, không phải instance mới
    Schema LAB_STUDENT
      LAB_STUDENT.EXERCISE_01         -> table
```

Một PDB có thể có **datafile riêng**, nhưng các PDB của cùng CDB chia sẻ các thành phần và instance cấp CDB. Khi kết nối nhầm `CDB$ROOT` thay vì `SALES_PDB`, câu lệnh tạo user/schema có thể khác hành vi hoặc bị từ chối; khi kết nối vào PDB khác, bảng cùng tên có thể hoàn toàn không tồn tại.

### Service name, SID và schema không giống nhau

| Tên | Nó nhận diện điều gì? | Dùng ở đâu? |
| --- | --- | --- |
| **Service name** | Dịch vụ database phục vụ kết nối, thường gắn với PDB hoặc workload | JDBC URL / client connect string |
| **SID / instance name** | Instance cụ thể trong một môi trường Oracle | Cấu hình và chẩn đoán instance |
| **PDB name** | Container logic trong CDB | Phân tách database cho ứng dụng/lab |
| **Username / schema** | Chủ sở hữu các SQL objects | Xác thực và phân quyền, tên `SCHEMA.OBJECT` |

Ví dụ JDBC kiểu service name:

```text
jdbc:oracle:thin:@//localhost:1521/SALES_PDB
```

Đây chỉ là **mẫu cú pháp**; service name phải đúng với cấu hình đã đăng ký tại listener, không suy ra bằng cách ghép tên instance hoặc schema. Một PDB có thể được phục vụ bởi nhiều service khác nhau.

## 6. Các đối tượng logic: không gian tên và tổ chức lưu trữ

Cụm từ “đối tượng logic” được dùng ở hai tầng liên quan nhưng **không đồng nhất**:

1. **Đối tượng SQL**: bảng, view, index, sequence, trigger, procedure, package, synonym...
2. **Cấu trúc lưu trữ logic**: tablespace, segment, extent, data block — các đơn vị Oracle dùng để bố trí dữ liệu vào file.

### 6.1. Đối tượng SQL trong schema

| Đối tượng | Người học sử dụng để | Có segment dữ liệu riêng ngay lập tức? |
| --- | --- | --- |
| **Table** | Lưu hàng và cột | Thường có segment khi cấp phát dữ liệu; có thể trì hoãn cấp phát ban đầu |
| **Index** | Hỗ trợ truy xuất, một số ràng buộc | Thường có index segment nếu dữ liệu/định nghĩa yêu cầu |
| **View** | Đặt tên cho một truy vấn | **Không** lưu bản sao hàng theo mặc định |
| **Materialized view** | Lưu kết quả truy vấn đã vật hóa | **Có** vùng lưu kết quả được quản lý riêng |
| **Sequence** | Sinh giá trị số theo trình tự | Có metadata và trạng thái được Oracle quản lý; không phải một table segment người dùng thông thường |
| **Procedure / function / package** | Đóng gói mã PL/SQL | Lưu định nghĩa/metadata, không phải bảng chứa hàng ứng dụng |
| **Synonym** | Đặt bí danh tham chiếu đối tượng | Không biến đối tượng đích thành bản sao vật lý |

**Schema không phải một file.** Ví dụ bảng `SALES_APP.ORDERS` thuộc schema `SALES_APP` nhưng segment của bảng có thể ở tablespace `APP_DATA`; index của chính bảng đó có thể ở tablespace `APP_INDEX`. Nhiều schema cũng có thể cùng sử dụng một tablespace nếu được cấp quyền và quota phù hợp.

### 6.2. Tablespace → segment → extent → data block

Oracle mô tả các cấu trúc lưu trữ logic theo cấp phát không gian:

```text
TABLESPACE APP_DATA
  |-- quản lý một hay nhiều DATAFILE trên storage
  |
  |-- SEGMENT của bảng SALES_APP.ORDERS
  |      |-- EXTENT 1: nhiều Oracle data block liên tiếp
  |      |-- EXTENT 2: nhiều Oracle data block liên tiếp
  |      +-- ...
  |
  +-- SEGMENT của bảng SALES_APP.CUSTOMERS
         |-- EXTENT 1
         +-- ...
```

- **Tablespace** là đơn vị quản lý không gian logic trong database/PDB. Một permanent tablespace ánh xạ đến **một hay nhiều datafile**; temporary tablespace sử dụng **tempfile**.
- **Segment** là không gian được cấp phát cho một cấu trúc lưu trữ như bảng, index, LOB hoặc partition. Không phải mọi SQL object có segment. Một bảng phân vùng có thể được ánh xạ tới nhiều segment, nên không có quy tắc “mỗi table = một segment”.
- **Extent** là một nhóm Oracle data block liên tiếp được cấp phát cho một segment trong một datafile. Segment có thể có nhiều extent, phân bố ở các datafile khác nhau thuộc cùng tablespace khi cấu hình cho phép.
- **Oracle data block** là đơn vị lưu trữ logic nhỏ nhất được Oracle dùng để tổ chức I/O dữ liệu. Kích thước block do cấu hình tablespace/database quyết định và không bắt buộc bằng block của hệ điều hành.

Quan hệ cần nắm:

```text
SQL object (table/index)
       |
       +--> segment(s) nếu đối tượng cần lưu dữ liệu vật hóa
                   |
                   +--> extent(s)
                           |
                           +--> Oracle data blocks
                                       |
                                       +--> nằm trong datafile
                                               |
                                               +--> thuộc tablespace
```

**Tablespace và schema là hai chiều phân loại độc lập:** schema trả lời “**ai sở hữu đối tượng?**”; tablespace trả lời “**không gian lưu trữ nào được dùng?**”. Tên bảng/index không cho biết ngay vị trí file vật lý của tất cả block chứa nó.

### 6.3. Ví dụ khác biệt giữa object và segment

Giả sử trong PDB `TRAINING_PDB`, user `LAB_STUDENT` có quyền tạo đối tượng và quota ở default tablespace. Chạy:

```sql
CREATE TABLE lab_orders (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    amount   NUMBER(12, 2) NOT NULL
);

INSERT INTO lab_orders (amount) VALUES (150.00);
COMMIT;

CREATE INDEX ix_lab_orders_amount ON lab_orders (amount);

CREATE VIEW v_lab_orders_positive AS
SELECT order_id, amount
  FROM lab_orders
 WHERE amount > 0;
```

Giờ xem những **SQL object** thuộc user:

```sql
SELECT object_name, object_type, status
  FROM user_objects
 WHERE object_name IN (
       'LAB_ORDERS',
       'IX_LAB_ORDERS_AMOUNT',
       'V_LAB_ORDERS_POSITIVE'
 )
 ORDER BY object_type, object_name;
```

Kết quả có thể thấy table, index và view. Sau đó xem **segment đã được cấp phát**:

```sql
SELECT segment_name, segment_type, tablespace_name, bytes
  FROM user_segments
 WHERE segment_name IN (
       'LAB_ORDERS',
       'IX_LAB_ORDERS_AMOUNT',
       'V_LAB_ORDERS_POSITIVE'
 )
 ORDER BY segment_name;
```

Khi đã có dữ liệu, bảng và index thường có segment; **view thông thường không có segment chứa kết quả truy vấn** nên không xuất hiện dưới tên view trong `USER_SEGMENTS`. Khóa chính ở ví dụ cũng có thể khiến Oracle tạo **index khác** để thực thi ràng buộc. Điều này cho thấy số lượng SQL objects và số lượng storage segments không nhất thiết bằng nhau.

Muốn biết bảng đang khai báo sử dụng tablespace nào:

```sql
SELECT table_name, tablespace_name
  FROM user_tables
 WHERE table_name = 'LAB_ORDERS';
```

Các view `USER_*` cho phép người dùng xem metadata của đối tượng thuộc mình mà thường không cần quyền DBA. `DBA_*` và nhiều `V$*` view có phạm vi sâu hơn, chỉ sử dụng khi được quản trị viên cấp quyền thích hợp.

## 7. Kiểm tra đang ở database, instance và container nào

Ở một SQL client kết nối vào Oracle, người dùng thông thường có thể bắt đầu bằng:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema,
    USER                                     AS login_user
FROM dual;
```

Các giá trị minh họa có thể là:

```text
DATABASE_NAME | CONTAINER_NAME | CURRENT_SCHEMA | LOGIN_USER
--------------+----------------+----------------+-----------
TRAINING_CDB  | TRAINING_PDB   | LAB_STUDENT    | LAB_STUDENT
```

Tên thực tế thay đổi theo bản cài. Lệnh này đặc biệt hữu ích khi một câu lệnh báo “không tìm thấy bảng”: đôi khi người học đang kết nối **sai PDB**, đang dùng **schema khác** hoặc thiếu quyền đọc đối tượng.

Nếu được cấp quyền đọc các dynamic performance views, quản trị viên có thể quan sát database và instance:

```sql
-- Trạng thái instance đang kết nối tới.
SELECT instance_name, status
FROM v$instance;

-- Database và trạng thái mở database.
SELECT name, open_mode, cdb
FROM v$database;

-- Danh sách các PDB thuộc CDB (quyền và phạm vi hiển thị tùy user).
SELECT con_id, name, open_mode
FROM v$pdbs;
```

Ở RAC, quản trị viên có thể dùng `GV$INSTANCE` để quan sát nhiều instance. Việc không đọc được `V$INSTANCE` do thiếu quyền **không chứng minh instance bị lỗi**; phân quyền metadata là một vấn đề riêng.

## 8. Trạng thái khởi động giúp phân biệt instance và database

Một minh họa rõ nhất là chu trình khởi động của Oracle:

| Trạng thái | Instance | Database vật lý | Điều đang xảy ra |
| --- | --- | --- | --- |
| **SHUTDOWN** | Không hoạt động | File vẫn còn trên storage | Không có instance đang mở database |
| **NOMOUNT** | Đã khởi tạo SGA và background processes | Chưa mount control file | Có instance nhưng database chưa được mount |
| **MOUNT** | Đang hoạt động | Control file đã được mở/đọc | Có thể thực hiện một số thao tác DBA/recovery; database chưa open cho SQL thông thường |
| **OPEN** | Đang hoạt động | Datafiles và online redo được mở theo yêu cầu | Database sẵn sàng phục vụ các thao tác được cấp quyền |

Minh họa cho DBA với SQL*Plus (cần kết nối đặc quyền, không chạy bừa trên database dùng chung):

```sql
STARTUP NOMOUNT;
ALTER DATABASE MOUNT;
ALTER DATABASE OPEN;
```

Trong CDB, **OPEN CDB không đồng nghĩa mọi PDB ứng dụng đều đã OPEN**. DBA có thể cần mở PDB bằng lệnh riêng và lưu trạng thái mở phù hợp. Vì thế một instance ở trạng thái `OPEN` không tự đảm bảo service/PDB mà ứng dụng dùng đã sẵn sàng.

Nhìn từ chu trình trên, câu hỏi “database có tồn tại không?” và “instance/database có đang mở để nhận kết nối không?” là hai câu hỏi khác nhau. Các file có thể còn nguyên trong khi instance đã dừng; instance có thể chạy nhưng database mới ở `NOMOUNT`.

## 9. Chẩn đoán sự cố theo đúng lớp kiến trúc

| Hiện tượng | Lớp nên kiểm tra trước | Hướng tìm nguyên nhân |
| --- | --- | --- |
| Không kết nối được qua host/port, lỗi listener/service như `ORA-12514` | Mạng / listener / service / PDB | Host, port, service registration, PDB đã mở hay chưa |
| `ORA-01034: ORACLE not available` | Instance/trạng thái database | Instance đang chạy không, cấu hình môi trường và trạng thái mở |
| Database không mount/open vì thiếu hoặc lỗi file, ví dụ `ORA-01157` | File vật lý / storage | Datafile, quyền filesystem/ASM, mount disk, recovery |
| `ORA-00942: table or view does not exist` | PDB / schema / đối tượng / quyền | Container hiện tại, chủ sở hữu, tên object, quyền `SELECT` |
| Không tạo được table vì thiếu quota, ví dụ `ORA-01950` | Schema / tablespace / quyền | Default tablespace, quota được cấp, quyền tạo đối tượng |
| Bảng đã tạo nhưng không thấy tên view trong `USER_SEGMENTS` | Object logic so với segment vật lý | View thường không lưu kết quả; tên view không có table segment |
| Cùng database host nhưng ứng dụng A không nhìn thấy bảng của B | PDB / schema / quyền | A và B có vào cùng PDB? Có prefix schema? Có quyền truy cập? |

Đây là **gợi ý phân loại**, không phải chẩn đoán chắc chắn chỉ dựa trên một mã lỗi. Cần đọc thông báo đầy đủ và nhật ký phù hợp trước khi thay đổi database.

## 10. Bài thực hành tự kiểm chứng

### Bài 1 — Phân loại thành phần

Cho danh sách:

```text
SGA, LGWR, datafile, control file, online redo log,
PDB SALES_PDB, schema SALES_APP, table ORDERS,
view V_ORDERS, tablespace APP_DATA, segment ORDERS,
extent, data block, SQLcl.
```

Hãy chia các thành phần thành bốn nhóm: **instance**, **file vật lý**, **đối tượng/cấu trúc logic** và **công cụ khách**. Giải thích vì sao `SQLcl` không phải database và vì sao `PDB` không đồng nghĩa với `instance`.

### Bài 2 — Quan sát khác biệt object/segment

Trong một schema thực hành, chạy mã tạo `LAB_ORDERS`, `IX_LAB_ORDERS_AMOUNT` và `V_LAB_ORDERS_POSITIVE` ở mục 6. Sau đó:

1. Dùng `USER_OBJECTS` ghi lại những object tồn tại.
2. Dùng `USER_SEGMENTS` ghi lại segment nào đã được cấp phát và tablespace tương ứng.
3. Giải thích vì sao view có trong danh sách object nhưng không có segment riêng để lưu hàng.
4. Dùng `SYS_CONTEXT` kiểm tra database name, container name và current schema của phiên.

### Bài 3 — Giải thích một tình huống vận hành

Giả sử quản trị viên tắt instance có kiểm soát, nhưng tất cả datafile, control file và online redo log vẫn nằm trên storage.

- Dữ liệu ứng dụng có tự biến mất không? **Không**: dữ liệu bền vững nằm trong file, không phụ thuộc vào việc SGA còn tồn tại.
- Người dùng có thực hiện `SELECT` khi instance đã dừng không? **Không** qua instance đó: cần khởi động và mở database/PDB phù hợp.
- Có thể coi việc copy một datafile đơn lẻ là phương án backup toàn database không? **Không**: backup/recovery cần tập file, redo và sự nhất quán theo phương pháp được Oracle hỗ trợ.
- Nếu chuyển từ single-instance sang RAC, điều gì tăng? **Số instance có thể truy cập cùng database**, không nhất thiết tăng số database vật lý.

### Bài 4 — Vẽ đường đi của một truy vấn

Tự vẽ các mũi tên từ ứng dụng Java, service, instance, đối tượng `SALES_APP.ORDERS`, segment, extent, block đến datafile. Phân biệt mũi tên **kết nối**, **xử lý**, **tổ chức logic** và **lưu trữ vật lý**. Giải thích vì sao không thể xem tên schema là đường dẫn tới một file cụ thể.

## Kết luận kiến trúc

Một ứng dụng nhìn thấy **đối tượng logic** như `SCHEMA.TABLE` bên trong đúng **PDB**; **instance** dùng bộ nhớ và tiến trình để xử lý yêu cầu; dữ liệu bền vững cùng thông tin cần thiết cho vận hành/khôi phục nằm trong **các file database**. Trong nội bộ storage, **tablespace → segment → extent → block** giúp Oracle quản lý vị trí và cấp phát dữ liệu mà không bắt lập trình viên biết đường dẫn OS của từng hàng.

Hiểu rõ ba ranh giới này giúp đọc đúng sơ đồ Oracle, chọn service kết nối, phân quyền schema, giải thích commit/redo, phân tích lỗi và tránh nhầm một database có nhiều schema/PDB thành nhiều instance độc lập.

**Đọc thêm:** [Oracle Database Concepts (tài liệu chính thức, chọn đúng release đang sử dụng)](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/) — các phần *Oracle Database Architecture*, *Oracle Database Instance*, *Physical Storage Structures*, *Logical Storage Structures* và *Multitenant Architecture*.
