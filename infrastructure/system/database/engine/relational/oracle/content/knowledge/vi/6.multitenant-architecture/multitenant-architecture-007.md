# Clone, plug, unplug và kiểm tra điều kiện tương thích PDB

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** CDB và PDB  
> **Mục tiêu:** Hiểu và thực hành vòng đời của một **Pluggable Database (PDB)** trong kiến trúc Oracle Multitenant: tạo bản sao bằng **clone**, tách PDB bằng **unplug**, gắn PDB bằng **plug**, kiểm tra tính tương thích với **DBMS_PDB** và xử lý các cảnh báo trước khi đưa PDB vào sử dụng.

## 1. Bối cảnh: PDB có thể được sao chép và chuyển giữa các CDB

Trong kiến trúc Oracle Multitenant, một **Container Database (CDB)** cung cấp phần hạ tầng dùng chung, còn mỗi **Pluggable Database (PDB)** chứa đối tượng và dữ liệu của các ứng dụng hoặc nhóm người dùng được phân tách về mặt logic.

Một CDB điển hình gồm:

```text
CDB_PROD
├── CDB$ROOT        : root container; quản trị instance, metadata chung
├── PDB$SEED        : khuôn mẫu để tạo PDB mới
├── APP_PDB         : PDB đang vận hành ứng dụng
└── REPORT_PDB      : PDB phục vụ báo cáo
```

PDB không giống schema:

- **Schema** là tập hợp các đối tượng thuộc một database user, ví dụ `ORDERS`, `CUSTOMERS`, index và sequence.
- **PDB** có tập hợp metadata, schema, datafiles và trạng thái mở riêng trong phạm vi CDB.
- **CDB** chứa các PDB và thực thi nhiều tiến trình, cấu trúc quản lý dùng chung ở tầng instance/root.

Khả năng di chuyển PDB là một lợi ích lớn của Multitenant: có thể tạo môi trường kiểm thử gần giống môi trường nguồn, chuyển một PDB sang CDB khác, hoặc gắn lại PDB đã tách mà không phải xuất từng bảng thủ công.

Tuy nhiên, các thao tác này **không đồng nghĩa** với một bản sao lưu độc lập. Việc tạo bản sao, di chuyển, lưu trữ file và phục hồi dữ liệu phải được phân biệt rõ.

## 2. Phân biệt clone, unplug và plug

| Thao tác | Ý nghĩa | PDB nguồn sau thao tác | Dữ liệu ở nơi đích |
|---|---|---|---|
| **Clone** | Tạo **PDB mới** từ một PDB hiện có | Thường tiếp tục tồn tại, có thể hoạt động theo điều kiện clone | Bản sao logic/vật lý theo phương pháp clone |
| **Unplug** | Tách một PDB khỏi CDB và tạo mô tả metadata để gắn nơi khác | Trở thành trạng thái **UNPLUGGED**, không dùng như PDB đang mở | Tạo manifest XML hoặc archive PDB; chưa tự gắn vào CDB đích |
| **Plug** | Tạo PDB trong CDB đích từ metadata và các datafile phù hợp | Tùy quy trình chuyển dữ liệu; nguồn có thể đã được tháo khỏi CDB cũ | PDB được đăng ký vào CDB đích; phải mở và xác minh |
| **Refreshable PDB clone** | Bản sao có thể nhận các thay đổi tiếp theo từ nguồn theo cơ chế refresh được hỗ trợ | Nguồn vẫn hoạt động | Bản sao có mối quan hệ refresh với nguồn; khác clone độc lập |
| **Snapshot copy** | Bản sao sử dụng khả năng snapshot/copy-on-write của lưu trữ, khi được hỗ trợ | Nguồn vẫn tồn tại; có phụ thuộc riêng tùy cấu hình | Có thể tiết kiệm dung lượng ban đầu nhưng không giống copy datafile độc lập |

Sơ đồ tư duy:

```text
                   ┌── Clone ────────────> PDB_B mới
PDB_A trong CDB_1 ─┤                         (nguồn PDB_A vẫn còn)
                   │
                   └── Unplug ───> Manifest + datafiles
                                     │
                                     │ Plug
                                     v
                                  CDB_2
                                   └── PDB_A hoặc tên mới
```

**Lựa chọn theo mục tiêu:**

- Muốn tạo môi trường lab/test song song: thường dùng **clone**.
- Muốn chuyển PDB sang CDB khác: dùng **unplug → chuyển metadata và datafiles → kiểm tra tương thích → plug**.
- Muốn môi trường đọc để báo cáo hoặc DR có khả năng cập nhật từ nguồn: tìm hiểu **refreshable PDB** và điều kiện của phiên bản.
- Muốn phục hồi từ hỏng hóc hoặc mất dữ liệu: cân nhắc **RMAN backup/recovery** và chiến lược phục hồi chính thức; clone hoặc unplug không thay thế backup.

## 3. Chuẩn bị môi trường Oracle Multitenant

Các ví dụ dùng tên giả định:

| Tham số | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| CDB nguồn | `CDB1` | Container Database đang chứa PDB |
| PDB nguồn | `LAB_SRC` | PDB cần clone hoặc chuyển |
| PDB bản sao | `LAB_CLONE` | PDB mới để kiểm thử |
| CDB đích | `CDB2` | Container Database sẽ nhận PDB |
| PDB sau plug | `LAB_MOVED` | Tên PDB dùng tại CDB đích |
| Metadata unplug | `/u03/pdbstage/lab_src.xml` | File XML do Oracle ghi ở filesystem của **database server** |
| Vùng dữ liệu nguồn | `/u02/oradata/CDB1/lab_src/` | Ví dụ đường dẫn chứa datafiles của PDB nguồn |
| Vùng dữ liệu đích | `/u02/oradata/CDB2/lab_moved/` | Ví dụ đường dẫn datafiles cho PDB đích |

Đây chỉ là tên mẫu. Trên Windows hoặc hệ thống dùng **ASM/OMF (Oracle Managed Files)**, các đường dẫn có thể rất khác, ví dụ vị trí có dấu `+DATA`. Cần dùng đường dẫn thật do DBA hoặc hệ thống cung cấp.

### 3.1. Công cụ và quyền cần có

Để chạy các lệnh thay đổi PDB, cần tài khoản có quyền quản trị CDB phù hợp, thường thực hiện dưới quyền `SYSDBA` trong **`CDB$ROOT`**, hoặc tài khoản quản trị được cấp quyền thích hợp như `CREATE PLUGGABLE DATABASE` và quyền liên quan. Một local user của PDB không thể tự di chuyển mọi PDB trong CDB.

Các câu lệnh minh họa cho môi trường lab ở máy chủ Linux:

```bash
sqlplus / as sysdba
```

Sau khi vào SQL*Plus:

```sql
SHOW CON_NAME;
SHOW PDBS;
```

Kết quả `SHOW CON_NAME` phải là `CDB$ROOT` trước các thao tác cấp CDB. Nếu đang ở một PDB khác, với quyền thích hợp:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
```

Không nhầm `CDB$ROOT` với service name của PDB. Một session ứng dụng thông thường nên kết nối thẳng service PDB, còn các bước quản trị dưới đây được thực hiện trong root.

### 3.2. Kiểm tra CDB, PDB và trạng thái mở

```sql
SELECT name, open_mode, cdb
FROM v$database;

SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;
```

Các trạng thái quan trọng:

- **MOUNTED:** PDB được nhận biết nhưng chưa mở cho người dùng truy vấn thông thường.
- **READ ONLY:** PDB mở đọc, không cho thay đổi dữ liệu như trạng thái read-write.
- **READ WRITE:** PDB mở cho hoạt động đọc và ghi.
- **UNPLUGGED:** PDB đã được tách; không thể sử dụng như một PDB đang mở trong CDB cũ.
- **RESTRICTED:** trạng thái hạn chế kết nối có thể xuất hiện khi cần xử lý vấn đề tương thích hoặc bảo trì.

Một PDB có thể có một số tùy chọn mở và trạng thái bổ sung tùy phiên bản. Luôn quan sát giá trị thực thay vì giả định mọi PDB sau khi tạo đều sẵn sàng.

### 3.3. Kiểm tra đường dẫn file và tài nguyên

Xem datafiles hiện tại (cần quyền truy cập dynamic performance view):

```sql
SELECT con_id, file#, name
FROM v$datafile
ORDER BY con_id, file#;
```

Đường dẫn trong cú pháp `FILE_NAME_CONVERT` phải khớp với dữ liệu thực tế, tránh ghi đè vào thư mục nguồn.

Kiểm tra các điều kiện khác trước khi thực hành:

1. CDB đích có **đủ dung lượng datafiles, tempfiles** và cho phép thêm PDB hay không.
2. Phiên bản Oracle/patch/option của CDB nguồn và đích có phù hợp.
3. Có chính sách cấp phát file tên tự động **OMF** hay phải chỉ định `FILE_NAME_CONVERT`.
4. Có dùng **TDE encryption** hoặc wallet/keystore hay không.
5. Có cần tạo bản sao độc lập và bảo đảm rollback bằng backup hay không.
6. Có người dùng/ứng dụng đang kết nối PDB nguồn, cần bảo trì hoặc thông báo downtime hay không.

> **Mọi lệnh `CLOSE`, `UNPLUG`, `DROP` và `MOVE` trong bài chỉ nên thao tác với PDB lab hoặc sau quy trình thay đổi được phê duyệt.** Đây là thay đổi cấu trúc database, có thể cắt kết nối ứng dụng và tác động dữ liệu vật lý.

## 4. Clone một PDB trong cùng CDB

### 4.1. Clone hoạt động như thế nào?

**Local PDB cloning** tạo một PDB mới từ PDB nguồn đang thuộc cùng CDB. Oracle lấy metadata và dữ liệu cần thiết từ nguồn để tạo PDB đích; kết quả thông thường là một PDB riêng có thể vận hành độc lập với PDB nguồn.

Ví dụ:

```text
CDB1
├── CDB$ROOT
├── PDB$SEED
├── LAB_SRC    ─── clone ──┐
└── LAB_CLONE <────────────┘
```

Nguồn vẫn giữ tên và dữ liệu của nó. Bản sao có **định danh PDB riêng**, dữ liệu có thể bắt đầu từ cùng trạng thái như thời điểm clone, nhưng những thay đổi tiếp theo trên bản sao không tự lan sang nguồn.

### 4.2. Chọn cold clone để dễ hiểu

Với quy trình thông dụng hỗ trợ rộng trong các bản Oracle Multitenant, chuẩn bị PDB nguồn ở chế độ **READ ONLY** trước khi clone. Trên CDB root:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE lab_src OPEN READ ONLY;
```

Kiểm tra:

```sql
SELECT name, open_mode
FROM v$pdbs
WHERE name = 'LAB_SRC';
```

Dự kiến `OPEN_MODE = READ ONLY`.

**Tác động:** Các session đang dùng `LAB_SRC` có thể bị ngắt khi đóng PDB và ứng dụng không được ghi dữ liệu trong thời gian PDB ở `READ ONLY`. Đây là thao tác chỉ thích hợp trong maintenance window hoặc môi trường lab.

### 4.3. Tạo bản sao bằng FILE_NAME_CONVERT

Nếu CDB **chưa** có cấu hình OMF phù hợp, có thể chỉ định cách đổi tên/đường dẫn file cho PDB mới:

```sql
CREATE PLUGGABLE DATABASE lab_clone
FROM lab_src
FILE_NAME_CONVERT = (
    '/u02/oradata/CDB1/lab_src/',
    '/u02/oradata/CDB1/lab_clone/'
);
```

Ý nghĩa:

- `LAB_CLONE`: tên PDB mới.
- `FROM LAB_SRC`: clone từ PDB nguồn.
- `FILE_NAME_CONVERT`: ánh xạ đường dẫn cũ sang đường dẫn file mới, tránh dùng lại file của PDB nguồn.

**Chú ý:** Đường dẫn chỉ là ví dụ. Không chạy nguyên văn nếu máy của bạn dùng đường dẫn khác. Nếu các datafiles không cùng thư mục, có thể cần nhiều cặp ánh xạ hoặc sử dụng OMF tùy môi trường.

Với hệ thống đã cấu hình **Oracle Managed Files**, có thể chỉ cần:

```sql
CREATE PLUGGABLE DATABASE lab_clone FROM lab_src;
```

Oracle sẽ tự quản lý tên file trong vị trí OMF được cấu hình. Hai mẫu tạo PDB trên là các **phương án thay thế**, không chạy cả hai để tạo cùng `LAB_CLONE`.

### 4.4. Mở PDB mới, đưa nguồn trở lại READ WRITE

```sql
ALTER PLUGGABLE DATABASE lab_clone OPEN READ WRITE;

ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE lab_src OPEN READ WRITE;

SELECT name, open_mode
FROM v$pdbs
WHERE name IN ('LAB_SRC', 'LAB_CLONE')
ORDER BY name;
```

Sau khi tạo, PDB mới có thể cần thêm các thao tác quản trị theo phiên bản và trạng thái plugin. Trong môi trường lab bình thường, `OPEN READ WRITE` là mục tiêu.

Nếu muốn PDB tự mở ở những lần khởi động CDB sau, khi PDB đã mở đúng trạng thái:

```sql
ALTER PLUGGABLE DATABASE lab_clone SAVE STATE;
ALTER PLUGGABLE DATABASE lab_src SAVE STATE;
```

Lưu trạng thái không thay thế thiết lập listener/service hoặc kiểm tra kết nối ứng dụng.

### 4.5. Xác minh clone đã độc lập

Kết nối bằng service của PDB mới và kiểm tra container:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb
FROM dual;
```

Ví dụ trong PDB mới, nếu đã có schema lab với quyền phù hợp:

```sql
CREATE TABLE clone_marker (
    id NUMBER PRIMARY KEY,
    note_text VARCHAR2(100)
);

INSERT INTO clone_marker VALUES (1, 'Chỉ tạo trong LAB_CLONE');
COMMIT;
```

Quay sang PDB nguồn bằng service riêng của nguồn rồi kiểm tra bảng marker không tự xuất hiện do thay đổi sau clone. Bảng marker chỉ là ví dụ; hãy dùng schema riêng và không tạo trong `SYS`.

## 5. Clone một PDB đang READ WRITE: hot clone

Trong các phiên bản Oracle hỗ trợ **hot cloning**, có thể clone từ PDB đang mở **READ WRITE** mà không nhất thiết phải đóng nguồn vào `READ ONLY`. Điều này giúp giảm downtime khi tạo bản sao.

Tuy vậy, khả năng hot clone và các điều kiện của nó phụ thuộc **phiên bản, loại CDB, local undo mode, ARCHIVELOG mode và hình thức clone (local/remote)**. Ví dụ các phiên bản Oracle mới hỗ trợ online PDB clone khi đáp ứng các điều kiện về local undo và redo lưu giữ cần thiết.

Luồng ở mức khái niệm:

```text
LAB_SRC đang READ WRITE
    |
    | ứng dụng tiếp tục phát sinh thay đổi
    |
    +---- hot clone ----> LAB_CLONE
                            |
                            +-- dữ liệu nhất quán tại mốc clone phù hợp
```

Không nên hiểu hot clone là “Oracle copy file đang thay đổi bằng lệnh `cp` của hệ điều hành”: Oracle xử lý metadata, redo và tính nhất quán theo cơ chế của database.

Lệnh clone có thể dùng cùng dạng:

```sql
CREATE PLUGGABLE DATABASE lab_clone
FROM lab_src;
```

Nhưng **chỉ thực thi khi môi trường đáp ứng điều kiện hot clone**, ví dụ CDB đã có OMF hoặc file mapping và cấu hình redo/undo phù hợp. Nếu không rõ phiên bản/cấu hình, chọn quy trình **READ ONLY** ở mục 4 hoặc làm theo tài liệu cloning của chính phiên bản đang vận hành.

Các kiểm tra nguồn thường được DBA thực hiện gồm:

```sql
SELECT log_mode
FROM v$database;

SELECT property_name, property_value
FROM database_properties
WHERE property_name = 'LOCAL_UNDO_ENABLED';
```

Giá trị/cột thể hiện trạng thái local undo có thể được kiểm tra bằng các view hoặc thuộc tính khác phù hợp phiên bản. Chỉ quan sát cấu hình chưa đủ để kết luận hot clone chắc chắn hoạt động; cần đối chiếu điều kiện của phiên bản cụ thể.

## 6. Clone PDB từ một CDB khác

**Remote PDB clone** tạo PDB trong CDB đích từ một PDB thuộc CDB nguồn. Oracle sử dụng một **database link** từ CDB đích để kết nối tới database nguồn trong quá trình clone.

Sơ đồ:

```text
CDB1                               CDB2
└── LAB_SRC  ─── Oracle Net ─────> └── LAB_REMOTE
                 / database link       (PDB mới)
```

Mẫu SQL ở CDB đích:

```sql
CREATE PLUGGABLE DATABASE lab_remote
FROM lab_src@cdb_source_link;
```

`cdb_source_link` phải được tạo/cấu hình **từ trước** với các quyền thích hợp, và CDB đích phải có chiến lược đặt datafiles (OMF hoặc file mapping hợp lệ). Không dùng database link vào PDB bất kỳ rồi mặc định coi là đủ; remote cloning yêu cầu tài khoản, quyền và kết nối đáp ứng quy tắc Multitenant của phiên bản.

Để triển khai, DBA cần kiểm tra:

- Kết nối Oracle Net từ **CDB đích** tới **CDB nguồn**.
- Quyền của tài khoản qua database link và quyền tạo PDB ở đích.
- Phiên bản/character set/compatibility.
- Yêu cầu source `READ ONLY` hoặc điều kiện hot clone tương ứng.
- Băng thông và dung lượng vì dữ liệu có thể lớn.
- Vấn đề bảo mật của database link: thông tin đăng nhập, mạng và audit.

**Remote clone khác với unplug/plug:** Clone tạo một PDB mới trong đích và giữ nguồn; unplug/plug thường phục vụ **di chuyển** PDB đã tách khỏi CDB cũ.

## 7. Snapshot copy và refreshable clone: hai biến thể cần phân biệt

### 7.1. Snapshot copy

Oracle hỗ trợ những hình thức **snapshot copy** trong các môi trường/phiên bản và công nghệ lưu trữ phù hợp. Thay vì tạo ngay bản sao độc lập của mọi block, snapshot có thể dựa vào cơ chế copy-on-write hoặc dữ liệu gốc trên lưu trữ.

Ưu điểm thường gặp là tốc độ khởi tạo và dung lượng ban đầu. Đổi lại, bản sao có **điều kiện về công nghệ lưu trữ** và có thể có phụ thuộc vào snapshot/nguồn. Không coi snapshot copy là bản sao độc lập có thể di chuyển tự do bằng cách chép một thư mục bất kỳ.

Ví dụ cú pháp tùy phiên bản hỗ trợ:

```sql
CREATE PLUGGABLE DATABASE lab_snapshot
FROM lab_src
SNAPSHOT COPY;
```

Ví dụ chỉ để nhận diện tính năng. Không chạy khi chưa xác nhận storage và phiên bản hỗ trợ.

### 7.2. Refreshable PDB clone

Refreshable clone có thể định kỳ nhận thay đổi từ nguồn thông qua cơ chế refresh PDB. Đây không phải snapshot tĩnh: nguồn tiếp tục thay đổi và bản sao giữ thông tin liên hệ để cập nhật về sau.

Những ràng buộc thường cần xét:

- Bản sao trong giai đoạn refresh thường hoạt động theo ngữ nghĩa **read-only** phù hợp với chế độ refresh.
- Cấu hình network/link, lưu giữ redo và thời gian refresh.
- Điều kiện phiên bản, undo mode và source/target compatibility.
- Cơ chế chuyển đổi sang PDB độc lập khi không cần refresh nữa.

Các tùy chọn `REFRESH MODE` và `REFRESH` cần tra cú pháp của bản Oracle đang triển khai. Bài này tập trung chủ yếu vào **clone độc lập** và **unplug/plug**, là hai quy trình nền tảng.

## 8. Unplug: tách PDB và xuất metadata

### 8.1. Unplug tạo ra những gì?

Khi **unplug**, Oracle tạo tệp mô tả về PDB để dùng khi **plug** vào CDB tương thích. Manifest thông dụng là file **XML**; một số phiên bản còn hỗ trợ định dạng **PDB archive** có phần mở rộng `.pdb`.

Ví dụ:

```text
CDB1
└── LAB_SRC
     |
     +-- UNPLUG INTO '/u03/pdbstage/lab_src.xml'
     |
     +--> lab_src.xml       (metadata/manifest)
     +--> datafiles        (vẫn còn ở vị trí lưu trữ)
```

**XML không chứa toàn bộ dữ liệu bảng.** File XML chứa thông tin mô tả/đường dẫn và các chi tiết cần thiết để Oracle nhận diện PDB; **datafiles vẫn phải hiện diện và có thể truy cập** khi plug.

Đây là điểm quan trọng nhất khi chuyển máy: chỉ copy `lab_src.xml` sang server mới sẽ **không đủ** để mở lại PDB có dữ liệu.

### 8.2. Quy trình unplug PDB bằng XML

Ví dụ giả định `LAB_SRC` là **PDB lab** do bạn quản lý. Đầu tiên, sao lưu hợp lệ và xác nhận không còn phiên ứng dụng cần phục vụ. Trên CDB root:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;
```

Khi PDB đã đóng, tạo XML manifest:

```sql
ALTER PLUGGABLE DATABASE lab_src
UNPLUG INTO '/u03/pdbstage/lab_src.xml';
```

File được tạo trên **filesystem mà tiến trình Oracle Database server có thể ghi**; nó không tự xuất hiện trong máy laptop chạy SQL Developer. Đường dẫn cần tồn tại và OS user chạy Oracle phải có quyền ghi.

Kiểm tra trạng thái:

```sql
SELECT name, open_mode
FROM v$pdbs
WHERE name = 'LAB_SRC';
```

Sau khi unplug, PDB không dùng như một PDB đang mở bình thường. Metadata của PDB vẫn có thể xuất hiện trong CDB nguồn cho tới khi được xóa khỏi CDB catalog.

### 8.3. DROP ... KEEP DATAFILES sau unplug

Nếu mục tiêu là chuyển PDB sang CDB khác, cần xử lý metadata còn lại trong CDB nguồn. Sau khi unplug thành công, với **đúng PDB lab**:

```sql
DROP PLUGGABLE DATABASE lab_src KEEP DATAFILES;
```

Lệnh này loại bỏ metadata PDB khỏi CDB nguồn nhưng **giữ các datafiles** để có thể plug ở nơi khác. Đây là lựa chọn phù hợp khi dữ liệu vẫn cần được di chuyển.

**Không thay `KEEP DATAFILES` bằng `INCLUDING DATAFILES`** trong quy trình chuyển PDB: `INCLUDING DATAFILES` có thể xóa datafiles vật lý, khiến bộ dữ liệu dự định chuyển đi bị mất. Trước khi drop, xác nhận XML đã tạo thành công và có kế hoạch bảo toàn/di chuyển datafiles.

### 8.4. Unplug vào PDB archive

Ở các bản Oracle hỗ trợ PDB archive, có thể dùng:

```sql
ALTER PLUGGABLE DATABASE lab_src
UNPLUG INTO '/u03/pdbstage/lab_src.pdb';
```

Định dạng archive giúp đóng gói metadata cùng các tệp liên quan vào gói để vận chuyển thuận tiện hơn, nhưng yêu cầu đủ dung lượng, quyền filesystem và có thể có hạn chế đối với loại datafile/tính năng. Hãy đối chiếu chi tiết phiên bản trước khi dùng. XML và archive là hai **lựa chọn thay thế** trong một lần unplug; không thực hiện hai lệnh lên cùng PDB đã unplug.

Ngay cả khi dùng archive, vẫn cần kiểm tra tương thích với CDB đích, trạng thái TDE và các yêu cầu hậu plug.

## 9. Chuyển bộ dữ liệu PDB sang máy/CDB đích

Trong kịch bản unplug XML, việc chuyển PDB thường gồm:

1. **Đóng nguồn và tạo manifest** bằng `UNPLUG INTO`.
2. Đảm bảo các **datafiles** liên quan được giữ lại; nhận diện file theo metadata và vị trí thực tế.
3. Sao chép hoặc chuyển manifest **và** các datafiles cần thiết tới nơi CDB đích có thể truy cập.
4. Phân quyền filesystem/ASM, bảo đảm không có process khác còn mở hoặc thay đổi bộ file.
5. Trên CDB đích, chạy `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` và xem các vi phạm.
6. Nếu tương thích, thực hiện `CREATE PLUGGABLE DATABASE ... USING` với lựa chọn file phù hợp.
7. Mở PDB, kiểm tra trạng thái/vi phạm và kết nối ứng dụng.

Nếu XML tham chiếu tới đường dẫn `/u02/oradata/CDB1/lab_src/system01.dbf` nhưng trên server đích datafile nằm ở `/u04/incoming/lab_src/system01.dbf`, cần có cơ chế ánh xạ **đường dẫn nguồn** đúng theo cú pháp của phiên bản (chẳng hạn `SOURCE_FILE_NAME_CONVERT` khi thích hợp, cùng `FILE_NAME_CONVERT` cho file đích) hoặc chuẩn hóa vị trí staging để các file được Oracle nhận diện.

**Không sửa tay XML để “đổi tên cho nhanh”** khi chưa theo đúng quy trình/documentation, vì manifest chứa nhiều metadata nội bộ và thông tin kiểm tra.

Với ASM, RAC, ACFS, TDE hoặc storage đa node, thao tác vận chuyển datafile có thể có các điều kiện riêng. Không áp dụng nguyên vẹn lệnh copy của filesystem thường cho ASM diskgroup.

### Chỉ XML hay cả datafiles?

| Trường hợp | Cần gì ở đích? | Ý nghĩa |
|---|---|---|
| `UNPLUG INTO ...xml` | Manifest XML **và** tất cả datafiles cần dùng, truy cập được từ DB server đích | XML chỉ mô tả PDB |
| `UNPLUG INTO ...pdb` | PDB archive hợp lệ, phiên bản hỗ trợ và đủ dung lượng để giải nén/plug | Archive có thể đóng gói metadata/file |
| **Clone qua database link** | Link và điều kiện remote clone; Oracle sao chép dữ liệu theo cơ chế SQL clone | Không yêu cầu thủ công unplug XML trước |
| **Snapshot copy** | Lưu trữ/snapshot backend hỗ trợ và các dependency của bản sao | Không tương đương copy hoàn chỉnh mọi datafile |

## 10. Kiểm tra điều kiện tương thích trước khi plug

Không phải mọi PDB từ một CDB đều plug được vào một CDB bất kỳ. Oracle kiểm tra nhiều thông tin metadata và trạng thái hệ thống để bảo đảm PDB có thể hoạt động đúng tại nơi nhận.

### 10.1. Các nhóm điều kiện cần đối chiếu

| Nhóm | Vấn đề cần xem | Ví dụ tác động |
|---|---|---|
| **Phiên bản database** | Release/patch level của source PDB và target CDB | PDB từ bản mới không thể tùy ý plug xuống bản cũ; chuyển lên bản mới có thể cần upgrade |
| **COMPATIBLE** | Mức tương thích định dạng dữ liệu và tính năng đã dùng | CDB đích không hỗ trợ mức tương thích của PDB nguồn |
| **Character set** | Database character set và national character set; quy tắc Multitenant theo phiên bản | PDB và CDB đích phải thỏa điều kiện tương thích ký tự |
| **Installed components/options** | Các thành phần, option và trạng thái cài đặt/patch SQL | PDB dùng component mà CDB đích thiếu hoặc không tương thích |
| **Time zone file/version** | Tương thích phiên bản timezone data | Có thể phát sinh cảnh báo hoặc cần nâng cấp timezone |
| **Nền tảng và dữ liệu vật lý** | Platform, endian/format, block size, transportability | Datafiles không sử dụng trực tiếp ở đích khi điều kiện không phù hợp |
| **TDE** | Encryption keys, wallet/keystore và cơ chế chuyển khóa | PDB có dữ liệu mã hóa nhưng thiếu key hợp lệ sẽ không dùng được bình thường |
| **Datafile paths/space** | File có thể đọc/ghi, mapping, thiếu dung lượng hoặc trùng tên | `CREATE ... USING` thất bại hoặc đụng file của PDB khác |
| **Giới hạn CDB** | Số PDB được phép, tài nguyên, chính sách edition | Không thể tạo PDB mới hoặc không thể mở cùng số PDB mong muốn |
| **Metadata/conflicts** | PDB name, GUID/DBID, các thông tin nội bộ và phụ thuộc | Cần tạo lại/đổi tên hoặc xử lý ràng buộc trước khi plug |

Bảng là danh sách hướng kiểm tra. **Quy tắc tương thích cụ thể phụ thuộc release, RU và cấu hình thực tế**. Không suy luận rằng chỉ cần hai bên cùng mang nhãn “Oracle 19c” là đã tương thích hoàn toàn.

### 10.2. DBMS_PDB.CHECK_PLUG_COMPATIBILITY

Oracle cung cấp package `DBMS_PDB` để đọc metadata của PDB và kiểm tra khả năng plug vào **CDB đích**.

Trước tiên, đặt manifest XML trên đường dẫn **database server đích** có thể truy cập được. Đăng nhập vào **`CDB$ROOT`** của CDB đích bằng quyền phù hợp:

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
SET SERVEROUTPUT ON SIZE UNLIMITED
```

Chạy phép kiểm tra:

```sql
DECLARE
    l_compatible BOOLEAN;
BEGIN
    l_compatible := DBMS_PDB.CHECK_PLUG_COMPATIBILITY(
        pdb_descr_file => '/u03/pdbstage/lab_src.xml',
        pdb_name       => 'LAB_MOVED'
    );

    IF l_compatible THEN
        DBMS_OUTPUT.PUT_LINE('COMPATIBLE: co the tiep tuc xem violations.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('INCOMPATIBLE: can xu ly vi pham truoc.');
    END IF;
END;
/
```

Hai tham số chính:

- `PDB_DESCR_FILE`: đường dẫn manifest XML của PDB.
- `PDB_NAME`: tên PDB dự định sử dụng khi plug vào CDB đích.

Kết quả kiểu `BOOLEAN` cho biết đánh giá tương thích tổng quát. Tuy nhiên, kết quả `TRUE` **không có nghĩa không còn bất cứ cảnh báo hoặc việc hậu plug nào**. Luôn kiểm tra view vi phạm.

### 10.3. PDB_PLUG_IN_VIOLATIONS

Trên CDB đích, sau khi chạy phép check, truy vấn:

```sql
SELECT time,
       name,
       cause,
       type,
       message,
       status,
       action
FROM pdb_plug_in_violations
WHERE name = 'LAB_MOVED'
ORDER BY time;
```

Tùy phiên bản và thời điểm kiểm tra, các trường thường giúp nhận diện:

- `NAME`: PDB bị ảnh hưởng hoặc tên dự định.
- `CAUSE`: nhóm nguyên nhân tương thích.
- `TYPE`: mức độ, ví dụ `ERROR` hoặc `WARNING`.
- `MESSAGE`: giải thích vấn đề được Oracle phát hiện.
- `STATUS`: trạng thái giải quyết, chẳng hạn còn `PENDING` hay đã `RESOLVED`, tùy loại báo cáo.
- `ACTION`: hướng dẫn hành động để khắc phục khi Oracle cung cấp.

**Cần ưu tiên các mục `TYPE='ERROR'` và chưa giải quyết.** Một số cảnh báo có thể cho phép plug nhưng PDB cần bước khắc phục, nâng cấp hoặc xác minh trước khi dùng cho ứng dụng.

Ví dụ lọc các mục cần chú ý:

```sql
SELECT type, cause, message, status, action
FROM pdb_plug_in_violations
WHERE name = 'LAB_MOVED'
  AND status <> 'RESOLVED'
ORDER BY type, cause;
```

Không tự sửa nội dung datafile/metadata để vượt check; làm theo hành động phù hợp của Oracle và chính sách vận hành của môi trường.

### 10.4. Nếu CHECK_PLUG_COMPATIBILITY trả FALSE

Nếu `FALSE`, quy trình đúng là:

1. Đọc đầy đủ `PDB_PLUG_IN_VIOLATIONS` và phân loại lỗi/chỉ cảnh báo.
2. Đối chiếu version/RU/COMPATIBLE, components, character set, timezone, TDE và file path.
3. Nếu cần, chuẩn bị CDB đích khác phù hợp hơn hoặc thực hiện upgrade/patch/keystore migration theo quy trình hỗ trợ.
4. Sau khi xử lý điều kiện, **chạy lại phép check**.
5. Chỉ thực hiện plug khi điều kiện phù hợp đã được xác minh.

Đổi tên PDB hay đổi vị trí file **không** thể tự sửa chênh lệch phiên bản, component hoặc key mã hóa.

## 11. Plug PDB từ XML vào CDB đích

### 11.1. NOCOPY: sử dụng các datafiles hiện có

Khi manifest và datafiles đã ở vị trí cuối cùng, và đường dẫn trong metadata tương ứng với file thực tế, một phương án là **`NOCOPY`**:

```sql
CREATE PLUGGABLE DATABASE lab_moved
USING '/u03/pdbstage/lab_src.xml'
NOCOPY
TEMPFILE REUSE;
```

Ý nghĩa:

- `USING`: đọc mô tả PDB từ XML.
- `NOCOPY`: dùng các datafiles tại vị trí đã có; Oracle không nhân bản dữ liệu file sang nơi khác.
- `TEMPFILE REUSE`: cho phép xử lý tái sử dụng tempfile khi phù hợp với cấu hình.

**Điều kiện rất quan trọng:** Vì `NOCOPY` dùng lại datafiles, các file đó **không được đồng thời thuộc một PDB khác còn đang hoạt động**. Không dùng NOCOPY như cách “tạo hai PDB cùng trỏ vào một bộ datafiles”; điều đó không phải clone hợp lệ và có nguy cơ phá hủy dữ liệu.

Nếu datafile đã chuyển sang đường dẫn khác với manifest, cần cơ chế mapping phù hợp; ví dụ này giả định file đã đúng đường dẫn.

### 11.2. COPY: tạo bản sao file ở đích

Khi nguồn datafiles vẫn còn ở nơi có thể đọc được nhưng muốn PDB đích sở hữu **bản copy riêng**, dùng `COPY` cùng mapping được chuẩn bị:

```sql
CREATE PLUGGABLE DATABASE lab_moved
USING '/u03/pdbstage/lab_src.xml'
COPY
FILE_NAME_CONVERT = (
    '/u02/oradata/CDB1/lab_src/',
    '/u02/oradata/CDB2/lab_moved/'
);
```

Cú pháp này giả định:

- Các file nguồn được XML tham chiếu vẫn có thể truy cập theo đường dẫn nguồn.
- Cặp mapping thực sự phản ánh đường dẫn file Oracle đang cần dùng.
- CDB đích có quyền tạo file trong thư mục đích và không có file trùng nguy hiểm.

`COPY` và `NOCOPY` là những lựa chọn với ý nghĩa khác nhau. Khi dùng `COPY`, phải dự trù đủ dung lượng để copy datafiles. Tùy phiên bản có thể có phương án `MOVE`, OMF hoặc các clause khác; tham khảo câu lệnh `CREATE PLUGGABLE DATABASE ... USING` của đúng bản Oracle.

### 11.3. Nếu đang sử dụng OMF

Nếu CDB đích đã cấu hình Oracle Managed Files, Oracle có thể tự tạo đường dẫn file đích theo `DB_CREATE_FILE_DEST` và cấu hình liên quan. Đừng ghép tùy tiện `FILE_NAME_CONVERT` với cơ chế OMF nếu quy tắc đặt tên file của hệ thống có thể tự giải quyết.

Kiểm tra trên CDB đích:

```sql
SHOW PARAMETER db_create_file_dest
SHOW PARAMETER pdb_file_name_convert
```

Lựa chọn cụ thể cần dựa trên điều kiện nguồn–đích và phiên bản. **Không tự đổi tham số toàn CDB** chỉ để chạy một ví dụ khi chưa đánh giá tác động lên các PDB khác.

### 11.4. Plug từ PDB archive

Nếu được hỗ trợ, có thể dùng archive file `.pdb` làm nguồn:

```sql
CREATE PLUGGABLE DATABASE lab_moved
USING '/u03/pdbstage/lab_src.pdb';
```

Các tùy chọn file location, extract/copy và khả năng truy cập có thể khác với `USING ...xml` theo phiên bản. Chỉ áp dụng khi CDB đích hỗ trợ định dạng archive và đã đối chiếu hướng dẫn PDB archive tương ứng; phép check trong mục 10 sử dụng XML manifest là quy trình minh họa chính.

## 12. Mở PDB sau plug và xử lý cảnh báo

Sau khi `CREATE PLUGGABLE DATABASE ... USING` thực hiện thành công, PDB có thể đang ở trạng thái `MOUNTED`. Xem trạng thái:

```sql
SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LAB_MOVED';
```

Kiểm tra lại vi phạm:

```sql
SELECT type, cause, message, status, action
FROM pdb_plug_in_violations
WHERE name = 'LAB_MOVED'
ORDER BY time;
```

Nếu không có lỗi chưa xử lý và môi trường đã phù hợp, mở PDB:

```sql
ALTER PLUGGABLE DATABASE lab_moved OPEN READ WRITE;
```

Xác minh:

```sql
SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LAB_MOVED';
```

Mục tiêu cho môi trường lab hoạt động bình thường là:

```text
NAME        OPEN_MODE      RESTRICTED
----------- -------------- ----------
LAB_MOVED   READ WRITE     NO
```

Ví dụ chỉ là kết quả kỳ vọng, không phải bằng chứng rằng PDB thực tế chắc chắn mở được. Nếu PDB mở ở **RESTRICTED** hoặc phát sinh lỗi, đọc thông báo và `PDB_PLUG_IN_VIOLATIONS`; một số trường hợp cần thực hiện upgrade, xử lý patch SQL hoặc thành phần cụ thể trước khi cho ứng dụng truy cập.

Khi cần giữ trạng thái mở qua lần CDB khởi động lại:

```sql
ALTER PLUGGABLE DATABASE lab_moved SAVE STATE;
```

### 12.1. Kiểm tra service và kết nối của ứng dụng

PDB tên `LAB_MOVED` thường có service mặc định tương ứng theo cấu hình Multitenant, nhưng ứng dụng có thể dùng **service name riêng** do DBA quản lý. Hãy xác nhận service nào đang được publish trong môi trường thật.

Trong CDB root, kiểm tra service:

```sql
SELECT name, network_name, pdb
FROM v$active_services
WHERE UPPER(pdb) = 'LAB_MOVED'
ORDER BY name;
```

Trên máy chủ listener:

```bash
lsnrctl services
```

Từ client (thay host, port, service name và username bằng giá trị thực):

```bash
sqlplus app_user@//db-target.example:1521/LAB_MOVED
```

Trong session, chạy:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_pdb,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS current_service,
       USER AS connected_user
FROM dual;

SELECT 1 AS connection_ok FROM dual;
```

Kết nối SQL chứng minh đường đi đến PDB đã hoạt động. Với hệ thống thật, cần tiếp tục kiểm tra application objects, người dùng, jobs, scheduler, directory objects, database links, external integrations và quyền theo môi trường đích.

### 12.2. Hậu plug có thể cần các bước nâng cấp

Nếu PDB nguồn ở phiên bản/patch khác với CDB đích, PDB có thể cần **upgrade/dictionary patching** bằng quy trình và công cụ Oracle hỗ trợ. Những ví dụ thường gặp là chạy công cụ upgrade thích hợp hoặc `datapatch` để đồng bộ SQL patch metadata; với trường hợp chuyển non-CDB sang PDB ở các phiên bản cũ còn có quy trình chuyển đổi riêng.

**Không tự chạy `noncdb_to_pdb.sql` cho mọi PDB-to-PDB plug**: script này liên quan tình huống chuyển **non-CDB** thành PDB, khác trường hợp tách một PDB đã có từ CDB nguồn. Chỉ dùng thủ tục được tài liệu của bản Oracle và các cảnh báo tương thích yêu cầu.

### 12.3. TDE keystore và encryption keys

Nếu nguồn có dữ liệu mã hóa bằng **Transparent Data Encryption (TDE)**, việc chuyển datafiles và XML không tự bảo đảm CDB đích có key cần thiết.

Cần tính tới:

- Keystore/wallet tại CDB nguồn và đích.
- Cách quản lý TDE master keys và export/import keys theo phiên bản, chế độ isolated/united keystore.
- Quyền truy cập keystore, tình trạng mở keystore và backup key.
- Các hạn chế khi clone/plug ở bản Free/edition hoặc cấu hình khác nhau.

Không đưa mật khẩu keystore hoặc bản sao key vào manifest công khai, mã nguồn hay log. Nếu kiểm tra tương thích trả cảnh báo liên quan mã hóa, xử lý thông qua quy trình quản trị TDE trước khi cho PDB phục vụ người dùng.

## 13. Ví dụ thực hành tổng hợp: unplug rồi plug lại một PDB lab

Phần này mô phỏng quy trình **trên cùng host hoặc môi trường có thể truy cập lại chính bộ datafiles gốc**, nhằm làm rõ thay đổi metadata. Ví dụ dành cho **LAB_SRC** là PDB lab được phép dừng và tháo khỏi CDB, không áp dụng lên PDB production.

### Điều kiện ban đầu

- Có CDB lab với PDB `LAB_SRC` chứa một ít dữ liệu thử.
- Không có ứng dụng quan trọng phụ thuộc `LAB_SRC`.
- Tài khoản quản trị có quyền thao tác PDB.
- Thư mục `/u03/pdbstage` tồn tại trên database server và Oracle OS user có quyền ghi.
- Có backup hoặc bản copy dữ liệu phục hồi trước khi thao tác.
- Datafiles gốc sẽ được giữ lại tại cùng đường dẫn sau khi drop metadata.

### Bước 1 — Xác nhận trạng thái ban đầu

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

SELECT name, open_mode
FROM v$pdbs
WHERE name = 'LAB_SRC';

SELECT con_id, name
FROM v$datafile
WHERE con_id = (
    SELECT con_id FROM v$pdbs WHERE name = 'LAB_SRC'
)
ORDER BY name;
```

Ghi lại đường dẫn datafiles. Điều này giúp kiểm tra bộ file sau unplug vẫn còn.

### Bước 2 — Đóng và unplug

```sql
ALTER PLUGGABLE DATABASE lab_src CLOSE IMMEDIATE;

ALTER PLUGGABLE DATABASE lab_src
UNPLUG INTO '/u03/pdbstage/lab_src.xml';
```

Xác nhận lệnh thành công, file XML tồn tại trên server và lưu trữ không báo lỗi. Không mở lại PDB đã unplug.

### Bước 3 — Loại metadata nguồn nhưng giữ file

```sql
DROP PLUGGABLE DATABASE lab_src KEEP DATAFILES;
```

Lệnh này là bước có tác động lớn; không chạy cho bất kỳ PDB nào khác. Sau thao tác, bộ datafiles gốc phải còn nguyên nếu muốn gắn lại bằng NOCOPY.

### Bước 4 — Kiểm tra tương thích trong CDB nhận

Trong bài lab này, CDB nhận chính là CDB ban đầu. Nếu mục tiêu là CDB khác, trước hết chuyển XML và datafiles, chạy các bước sau tại CDB **đích**.

```sql
SET SERVEROUTPUT ON SIZE UNLIMITED

DECLARE
    l_ok BOOLEAN;
BEGIN
    l_ok := DBMS_PDB.CHECK_PLUG_COMPATIBILITY(
        pdb_descr_file => '/u03/pdbstage/lab_src.xml',
        pdb_name       => 'LAB_SRC'
    );

    IF l_ok THEN
        DBMS_OUTPUT.PUT_LINE('COMPATIBLE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('INCOMPATIBLE');
    END IF;
END;
/
```

Kiểm tra các vi phạm:

```sql
SELECT type, cause, message, status, action
FROM pdb_plug_in_violations
WHERE name = 'LAB_SRC'
ORDER BY type, cause;
```

Nếu check không đạt hoặc có lỗi chưa giải quyết, **dừng ở đây** để xử lý tương thích. Không cố plug bằng cách bỏ qua thông báo.

### Bước 5 — Plug lại datafiles hiện có

Vì PDB cũ đã bị loại khỏi CDB bằng `KEEP DATAFILES` và file vẫn nằm ở đường dẫn manifest ghi nhận, có thể dùng NOCOPY:

```sql
CREATE PLUGGABLE DATABASE lab_src
USING '/u03/pdbstage/lab_src.xml'
NOCOPY
TEMPFILE REUSE;
```

Không dùng lệnh này nếu PDB cũ vẫn còn trong CDB hoặc datafiles đã được một database khác mở sử dụng.

### Bước 6 — Mở và xác nhận dữ liệu

```sql
ALTER PLUGGABLE DATABASE lab_src OPEN READ WRITE;

SELECT name, open_mode, restricted
FROM v$pdbs
WHERE name = 'LAB_SRC';

ALTER PLUGGABLE DATABASE lab_src SAVE STATE;
```

Kết nối tới service PDB bằng user lab, xác nhận:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
       USER AS connected_user
FROM dual;
```

Truy vấn một bảng ứng dụng đã tồn tại trước khi unplug và đối chiếu số dòng/khóa kiểm tra mà bạn đã ghi lại trước thao tác. Nếu dữ liệu đúng, việc unplug/plug đã hoàn tất theo mục tiêu lab.

### Bước 7 — Nếu làm trên hai CDB

Quy trình từ bước 2 đến bước 6 vẫn giữ cấu trúc, nhưng có các khác biệt:

- Phải chuyển XML **và datafiles** hoặc PDB archive tới server/storage đích.
- Dùng tên `LAB_MOVED` nếu cần đổi tên PDB tại CDB đích.
- Kiểm tra tương thích **trên CDB2**, không phải CDB1.
- Dùng mapping file phù hợp và chọn `COPY` hay `NOCOPY` dựa trên vị trí file.
- Xử lý listener/service, TDE keys và cảnh báo sau plug trong CDB2.
- Chỉ mở ứng dụng sang PDB đích sau khi các bước xác nhận hoàn tất.

## 14. Xử lý sự cố thường gặp

| Dấu hiệu/lỗi | Nguyên nhân cần điều tra | Hướng xử lý |
|---|---|---|
| Không thể clone vì source đang mở READ WRITE | Bản/kiểu clone không hỗ trợ hot clone với cấu hình hiện tại | Dùng quy trình read-only clone hoặc cấu hình hỗ trợ hot clone theo tài liệu |
| `FILE_NAME_CONVERT` không tạo được file | Đường dẫn source mapping sai, thư mục đích không tồn tại, OS permission hoặc file trùng | Kiểm tra `V$DATAFILE`, filesystem/ASM, quyền và chọn OMF nếu phù hợp |
| `UNPLUG INTO` báo không ghi được XML | Đường dẫn server sai, không có quyền ghi, không đủ dung lượng | Tạo staging dir đúng trên DB server; kiểm tra OS user của Oracle |
| Unplug xong chỉ đem XML sang server mới | Thiếu datafiles thực tế | Chuyển đủ datafiles hoặc dùng PDB archive được hỗ trợ |
| `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` trả `FALSE` | Phiên bản, component, charset, timezone, TDE hoặc điều kiện khác không tương thích | Đọc `PDB_PLUG_IN_VIOLATIONS` rồi xử lý nguyên nhân |
| Plug thành công nhưng PDB mở `RESTRICTED` | Còn vi phạm hoặc công việc nâng cấp/cập nhật SQL components | Xem violations và alert log; chạy quy trình hậu plug được yêu cầu |
| Không mở được PDB mã hóa | Key/wallet/keystore không đúng hoặc chưa chuyển key | Xử lý TDE migration theo quản trị bảo mật |
| Không có service trong listener | PDB chưa mở hoặc service chưa đăng ký/cấu hình | Kiểm tra `V$PDBS`, `V$ACTIVE_SERVICES`, `lsnrctl services` |
| ORA-01017 khi kết nối PDB đã plug | Sai credentials, service hoặc PDB | Kiểm tra user tồn tại đúng PDB, thông số auth và service |
| PDB mới có name conflict | Tên PDB đã tồn tại trong CDB đích | Chọn tên mới và kiểm tra metadata/tên file |
| Tệp datafile đích trùng với tệp đang sử dụng | Mapping sai, dùng NOCOPY khi file vẫn thuộc database khác | Không tiếp tục; kiểm tra ownership vật lý và dùng COPY/đường dẫn riêng |
| Clone chạy lâu, dung lượng tăng mạnh | PDB lớn, I/O chậm, dùng copy đầy đủ thay vì snapshot | Ước lượng dung lượng, kiểm tra storage và chọn phương án phù hợp |

Thông báo Oracle có thể xuất hiện với các mã như `ORA-650xx`, `ORA-651xx` hoặc lỗi filesystem, nhưng mã cụ thể tùy tình huống và phiên bản. Nên lưu **toàn bộ thông báo**, SQL vừa chạy, thời điểm và môi trường, thay vì chỉ dựa vào một mã số không đủ ngữ cảnh.

## 15. Các nguyên tắc bảo vệ dữ liệu khi làm việc với PDB

### 15.1. Unplug không có nghĩa là backup

Unplug tạo manifest và đưa PDB ra khỏi CDB, nhưng **không tự tạo một backup độc lập được kiểm tra khả năng restore**. XML và datafiles có thể cùng nằm trên một thiết bị hỏng; khi đó unplug không giúp khôi phục.

Đối với dữ liệu quan trọng, cần có chiến lược RMAN backup và kiểm thử restore trước các thao tác thay đổi cấu trúc. Kiểm tra backup cùng với chính sách retention, encryption và lưu trữ ngoài vị trí nguồn.

### 15.2. Tránh để hai CDB cùng quản lý một bộ datafiles

Lựa chọn `NOCOPY` chỉ hợp lý khi bộ file hiện có được bàn giao độc quyền cho PDB trong CDB đích. Trỏ hai PDB/CDB hoạt động đồng thời vào cùng bộ datafiles không phải cách clone và có thể gây lỗi nghiêm trọng.

Để có hai môi trường tồn tại song song, dùng **clone**, `COPY`, bản sao RMAN hợp lệ hoặc phương án snapshot được Oracle hỗ trợ.

### 15.3. Metadata cũng cần bảo mật

Manifest XML có thể chứa cấu trúc, metadata và đường dẫn nội bộ. File archive có thể chứa datafiles, trong đó có dữ liệu nhạy cảm. Cần:

- Hạn chế quyền đọc/ghi file staging.
- Truyền file qua đường bảo mật.
- Bảo vệ TDE keystore/keys bằng quy trình riêng.
- Xóa bản staging theo chính sách sau khi đối chiếu đã hoàn thành.
- Tránh đưa nội dung XML hoặc datafile lên repository công khai.

### 15.4. Cân nhắc định danh và tích hợp ngoài PDB

Một PDB chứa schema và dữ liệu, nhưng ứng dụng còn phụ thuộc các thành phần ngoài dữ liệu:

- Service name và routing của listener/SCAN.
- Jobs Scheduler, database links, directory objects, external tables.
- Hostname/path, ACL network và quyền filesystem.
- Secret management, TDE keystore và hệ thống xác thực ngoài.
- Các cấu hình connection pool, ví dụ service name hoặc port trong JDBC.
- Data Guard, backup/monitoring và quy trình vận hành sau khi chuyển.

Vì vậy, “PDB đã OPEN READ WRITE” là điều kiện kỹ thuật quan trọng, nhưng **chưa tự chứng minh toàn bộ ứng dụng đã chuyển thành công**.

## 16. Kiểm tra nhanh trạng thái và cấu hình sau thao tác

Trên CDB root, với quyền phù hợp, một bộ truy vấn quan sát hữu ích là:

```sql
SELECT name, open_mode, cdb
FROM v$database;

SELECT con_id, name, open_mode, restricted
FROM v$pdbs
ORDER BY con_id;

SELECT name, network_name, pdb
FROM v$active_services
WHERE UPPER(pdb) IN ('LAB_SRC', 'LAB_CLONE', 'LAB_MOVED')
ORDER BY pdb, name;

SELECT time, name, type, cause, status, message
FROM pdb_plug_in_violations
WHERE name IN ('LAB_CLONE', 'LAB_MOVED', 'LAB_SRC')
ORDER BY time;
```

Khi cần đối chiếu file:

```sql
SELECT con_id, file#, name
FROM v$datafile
ORDER BY con_id, file#;
```

Còn trên chính PDB, xác nhận:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       USER AS username
FROM dual;
```

Đặt tên và truy vấn thật của ứng dụng vào bước cuối thay vì chỉ dựa trên việc mở PDB thành công.

## 17. Mô hình quyết định: dùng cách nào?

```text
Bạn muốn làm gì với PDB?
|
+-- Tạo bản sao để chạy test song song?
|      |
|      +--> CLONE
|            |-- Nguồn READ ONLY: quy trình đơn giản, dễ kiểm soát
|            |-- Nguồn READ WRITE: chỉ khi hot clone được hỗ trợ
|            +-- Cần ít dữ liệu sao chép: xem điều kiện snapshot copy
|
+-- Muốn bản sao được cập nhật định kỳ từ nguồn?
|      |
|      +--> REFRESHABLE PDB CLONE (nếu được hỗ trợ)
|
+-- Muốn di chuyển PDB sang CDB khác?
|      |
|      +--> UNPLUG
|             |
|             +--> XML + DATAFILES, hoặc PDB ARCHIVE
|             |
|             +--> Chuyển file/staging đến môi trường đích
|             |
|             +--> DBMS_PDB.CHECK_PLUG_COMPATIBILITY
|             |       |
|             |       +-- FALSE/ERROR: xử lý tương thích
|             |       +-- TRUE: vẫn đọc violations
|             |
|             +--> CREATE PLUGGABLE DATABASE ... USING
|             |
|             +--> OPEN + kiểm tra violations + service + SQL
|
+-- Cần khôi phục dữ liệu sau sự cố?
       |
       +--> RMAN BACKUP/RECOVERY và chiến lược DR thích hợp
```

Nhìn vào sơ đồ này, cần nhớ **clone là tạo bản sao**, còn **unplug/plug là tháo/gắn PDB cùng metadata và dữ liệu vật lý thích hợp**. Phần kiểm tra tương thích là một bước độc lập, không được bỏ qua khi chuyển PDB giữa CDB hoặc phiên bản khác nhau.

## 18. Bài thực hành và câu hỏi ôn tập

### Bài 1 — Tạo clone độc lập

**Bối cảnh:** Bạn có một PDB lab tên `LAB_SRC` trong CDB, cần tạo `LAB_CLONE` để kiểm thử mà không làm thay đổi dữ liệu của nguồn.

Yêu cầu:

1. Xác nhận CDB root và trạng thái `LAB_SRC`.
2. Chuẩn bị nguồn `READ ONLY` nếu không dùng hot clone.
3. Clone `LAB_SRC` thành `LAB_CLONE` bằng OMF hoặc `FILE_NAME_CONVERT` phù hợp.
4. Mở clone `READ WRITE`, trả nguồn về `READ WRITE`.
5. Tạo một đối tượng thử riêng trong clone, chứng minh đối tượng đó không xuất hiện trong nguồn do thay đổi sau clone.
6. Ghi lại mọi đường dẫn file và service name đã sử dụng.

**Câu hỏi:** Vì sao copy thư mục datafile bằng lệnh hệ điều hành khi PDB đang mở không tương đương với `CREATE PLUGGABLE DATABASE ... FROM`?

**Gợi ý:** Oracle cần bảo đảm metadata, định danh PDB, tính nhất quán, redo và các điều kiện quản lý file; copy filesystem tùy ý không cung cấp bảo đảm này.

### Bài 2 — Unplug và plug lại cùng CDB

**Bối cảnh:** Chỉ dùng PDB thử `LAB_SRC` có backup và được phép dừng.

Yêu cầu:

1. Ghi tên datafiles trước thao tác.
2. Đóng PDB, unplug vào XML.
3. Chỉ khi XML/datafiles an toàn, drop metadata bằng `KEEP DATAFILES`.
4. Chạy `DBMS_PDB.CHECK_PLUG_COMPATIBILITY`.
5. Truy vấn `PDB_PLUG_IN_VIOLATIONS`.
6. Nếu tương thích, plug lại bằng `NOCOPY`.
7. Mở PDB, xác minh dữ liệu và kết nối SQL.

**Câu hỏi:** Nếu chỉ lưu manifest XML, bỏ mất datafiles, vì sao không thể coi đó là một bản backup?

**Gợi ý:** Metadata mô tả cấu trúc/định danh và file; dữ liệu thật nằm trong datafiles.

### Bài 3 — Phân tích kết quả compatibility check

Giả sử `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` trả về `FALSE` và `PDB_PLUG_IN_VIOLATIONS` có thông báo:

```text
TYPE    CAUSE             MESSAGE (minh họa)
ERROR   OPTION            Component version mismatch
WARNING TIMEZONE_VERSION  Timezone version differs
```

Hãy trả lời:

1. Có nên tiếp tục `CREATE ... USING` ngay không?
2. Loại thông tin nào cần DBA kiểm tra?
3. Việc đổi `LAB_MOVED` thành tên PDB khác có sửa được lỗi component mismatch không?

**Định hướng:** Không tiếp tục khi còn lỗi nghiêm trọng; cần đối chiếu phiên bản, patches/components và hướng dẫn của Oracle; đổi tên không giải quyết xung đột phiên bản/component.

### Bài 4 — Lựa chọn COPY hay NOCOPY

Cho hai tình huống:

- **A:** Chuyển PDB sang CDB khác trên cùng storage, datafiles gốc đã được giải phóng khỏi CDB nguồn và có thể dùng nguyên vị trí.
- **B:** Giữ một bộ file staging và muốn tạo một bản sao datafiles độc lập tại thư mục của CDB đích.

**Đáp án định hướng:** A có thể cân nhắc `NOCOPY` nếu đáp ứng độc quyền sở hữu file và mapping; B có thể chọn `COPY` và `FILE_NAME_CONVERT`/OMF phù hợp.

### Bài 5 — Sự cố sau plug

PDB `LAB_MOVED` đã xuất hiện trong `V$PDBS` nhưng SQL Developer báo service không tồn tại. Hãy trình bày thứ tự kiểm tra.

**Gợi ý:** Xem `OPEN_MODE`/`RESTRICTED`, `PDB_PLUG_IN_VIOLATIONS`, service trong `V$ACTIVE_SERVICES`, listener `lsnrctl services`, hostname/port và đúng service name trong kết nối client. Không mặc định tạo user mới hoặc mở firewall khi chưa biết lớp lỗi.

## 19. Kết luận về khả năng di chuyển PDB

Oracle Multitenant giúp quản lý PDB như các đơn vị độc lập tương đối trong một CDB:

- **Clone** để tạo môi trường song song từ dữ liệu nguồn.
- **Unplug** để đóng gói thông tin mô tả và tách một PDB ra khỏi CDB.
- **Plug** để gắn bộ PDB hợp lệ vào CDB đích.
- **DBMS_PDB.CHECK_PLUG_COMPATIBILITY** cùng **PDB_PLUG_IN_VIOLATIONS** giúp xác định và xử lý chênh lệch trước/sau khi gắn PDB.

Muốn thao tác an toàn, cần nắm đồng thời **trạng thái mở PDB, định danh và datafiles, phiên bản database, cấu hình lưu trữ, TDE, listener/services và quyền quản trị**. Dù câu lệnh SQL ngắn, một lần chuyển PDB hoàn chỉnh luôn cần kiểm tra dữ liệu, kết nối và các phụ thuộc ứng dụng.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Oracle Database Multitenant Administrator's Guide](https://docs.oracle.com/en/database/) — Creating, cloning, unplugging, plugging and managing PDBs.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Cú pháp `CREATE PLUGGABLE DATABASE`, `ALTER PLUGGABLE DATABASE`, `DROP PLUGGABLE DATABASE`.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — Package `DBMS_PDB` và `CHECK_PLUG_COMPATIBILITY`.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — `V$PDBS`, `V$ACTIVE_SERVICES`, `PDB_PLUG_IN_VIOLATIONS`.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/) — TDE, keystore và các yêu cầu chuyển keys trong Multitenant.

Khi dùng Oracle 19c, 21c, 23ai hoặc 26ai, nên xem đúng bộ tài liệu của **phiên bản và patch level đã triển khai**, vì các khả năng hot clone, snapshot copy, archive, tính tương thích và thao tác hậu plug có thể khác nhau.

