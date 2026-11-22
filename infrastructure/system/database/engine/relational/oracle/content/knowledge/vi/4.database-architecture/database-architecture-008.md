# Datafile, control file, online redo log và archived redo log trong Oracle Database

Oracle Database không lưu mọi thông tin trong một tệp duy nhất. Dữ liệu của bảng và chỉ mục được tổ chức trong **datafile**; thông tin nhận diện và cấu trúc vật lý database nằm trong **control file**; các thay đổi cần cho phục hồi được ghi vào **online redo log**; và khi bật chế độ lưu trữ redo, những redo log đã hoàn tất được giữ lại dưới dạng **archived redo log**. Bốn thành phần phối hợp để Oracle vừa xử lý giao dịch nhanh, vừa khôi phục trạng thái nhất quán sau sự cố.

Trong bài học thuộc chủ đề **Kiến trúc Oracle Database**, chúng ta sẽ theo dõi đường đi của một giao dịch, hiểu từng loại tệp ở cả trạng thái hoạt động bình thường lẫn khi xảy ra lỗi, đồng thời dùng các truy vấn chỉ đọc để quan sát các file trên một hệ thống Oracle thực tế.

Sau khi học, bạn có thể:

- Phân biệt nơi lưu dữ liệu lâu dài, nơi lưu siêu dữ liệu cấu trúc và nơi lưu thông tin phục hồi.
- Giải thích quan hệ giữa **tablespace và datafile**, **redo log group và member**, **online redo và archived redo**.
- Mô tả vai trò của **DBWR, LGWR, CKPT và ARCn** trong ghi dữ liệu, commit, checkpoint, log switch và archiving.
- Phân biệt **instance/crash recovery** với **media recovery**, hiểu tại sao phải có backup và redo cần thiết.
- Đọc các view `V$DATAFILE`, `V$CONTROLFILE`, `V$LOG`, `V$LOGFILE`, `V$DATABASE` và `V$ARCHIVED_LOG`.
- Nhận ra những cấu hình mang rủi ro, chẳng hạn thiếu bản sao control file, chỉ có một redo member hoặc vùng lưu archived log bị đầy.

> Các lệnh minh họa chủ yếu là **truy vấn chỉ đọc**. Những thao tác như chuyển chế độ `ARCHIVELOG`, chuyển log group hoặc sửa cấu hình file đều có tác động thực tế và chỉ nên thực hiện trên **database lab riêng có quyền quản trị** sau khi hiểu hậu quả. Ví dụ dùng thuật ngữ chung cho Oracle hiện đại; đường dẫn, tên tablespace và số log group có thể khác theo phiên bản/cài đặt.

## 1. Bức tranh kiến trúc: dữ liệu và khả năng phục hồi được lưu ở đâu?

Hãy hình dung người dùng thực hiện:

`UPDATE accounts SET balance = balance - 100 WHERE account_id = 10;`

và sau đó `COMMIT`. Oracle phải bảo đảm một giao dịch đã commit có thể được phục hồi sau khi tiến trình hoặc máy chủ gặp sự cố, ngay cả khi thay đổi trên block dữ liệu chưa được DBWR ghi xuống datafile.

~~~text
                           ORACLE INSTANCE
                    +----------------------------+
SQL UPDATE/COMMIT ->| Database Buffer Cache      |
                    |   (cac block du lieu)      |
                    |                            |
                    | Redo Log Buffer            |
                    |   (ban ghi thay doi redo)  |
                    +---------------+------------+
                                    |
                    +---------------+-------------------+
                    |                                   |
                    v                                   v
                 DBWR                                LGWR
                    |                                   |
                    v                                   v
             +-------------+                  +--------------------+
             | DATAFILES   |                  | ONLINE REDO LOGS   |
             | du lieu     |                  | group 1, 2, 3...   |
             +-------------+                  +----------+---------+
                                                        |
                                               log switch / ARCn
                                                        |
                                                        v
                                             +--------------------+
                                             | ARCHIVED REDO LOGS |
                                             | lich su redo duoc  |
                                             | giu lai (ARCHIVELOG)|
                                             +--------------------+

   CONTROL FILE: danh tinh database, danh sach datafile/redo,
   checkpoint va metadata can de mount, quan ly va phuc hoi.
~~~

**Điểm mấu chốt:** `COMMIT` không yêu cầu Oracle ghi ngay mọi block đã sửa xuống datafile. Cơ chế **write-ahead logging** cho phép Oracle ghi redo phục vụ phục hồi trước; DBWR có thể ghi các block đã sửa vào datafile sau đó. Vì vậy **redo không phải bản sao của datafile** và **datafile không phải transaction log**.

### 1.1. Bảng đối chiếu bốn loại tệp

| Thành phần | Nội dung chính | Được ghi/cập nhật khi nào? | Vai trò khi sự cố |
| --- | --- | --- | --- |
| **Datafile** | Các block dữ liệu của tablespace, gồm bảng, chỉ mục, undo segment và metadata lưu trữ phù hợp | DBWR ghi các dirty buffer và nhiều thao tác quản trị file | Là nơi phục hồi các block dữ liệu; file hỏng/mất thường cần restore từ backup |
| **Control file** | Nhận dạng database, tên/vị trí datafile và redo log, thông tin checkpoint, log sequence và metadata quản trị/phục hồi | Database cập nhật khi cấu trúc, checkpoint hoặc trạng thái redo thay đổi | Cần thiết để mount database và tổ chức recovery |
| **Online redo log** | Các bản ghi redo mô tả thay đổi để có thể tái áp dụng khi phục hồi | LGWR ghi liên tục, tái sử dụng theo vòng các group | Cho **instance recovery**; có thể chứa redo mới nhất chưa được archive |
| **Archived redo log** | Bản lưu của **online redo log group đã hoàn tất**, giữ theo log sequence | ARCn lưu sau log switch trong `ARCHIVELOG` mode | Cung cấp lịch sử redo để **media recovery**, phục hồi theo thời điểm, tạo bản sao dự phòng |

Trong Oracle, cả bốn đều là **thành phần vật lý** của môi trường database, nhưng tác dụng hoàn toàn khác nhau. Tablespace, schema, segment là các khái niệm **logic**; SGA và background process thuộc **instance** chứ không phải tệp dữ liệu.

## 2. Datafile: nơi các block dữ liệu được lưu bền vững

### 2.1. Quan hệ giữa tablespace và datafile

Oracle tổ chức dung lượng theo nhiều cấp:

~~~text
Database (hoac PDB)
  |
  +-- Tablespace USERS
  |     +-- Datafile users01.dbf
  |     +-- Datafile users02.dbf
  |          +-- Segment: table ACCOUNTS
  |          +-- Segment: index ACCOUNTS_PK
  |
  +-- Tablespace SYSTEM
  |     +-- Datafile system01.dbf
  |
  +-- Tablespace UNDOTBS1
        +-- Datafile undotbs01.dbf
~~~

Một **tablespace** là đơn vị lưu trữ logic. Một tablespace permanent hoặc undo có **một hay nhiều datafile**; một datafile thuộc về **một tablespace** tại một thời điểm. Bên trong tablespace, đối tượng sử dụng segment; segment gồm các extent; extent gồm các data block.

Ví dụ:

- `SYSTEM`, `SYSAUX` chứa nhiều thông tin nội bộ của Oracle.
- `USERS` thường dành cho đối tượng ứng dụng hoặc thực hành, tùy cấu hình.
- Tablespace undo chứa các **undo segment** dùng cho rollback và read consistency; block undo vẫn nằm trong **datafile**, còn redo mô tả cả những thay đổi cần thiết đối với undo.
- Tablespace **temporary** dùng **tempfile** để chứa dữ liệu tạm khi cần sort/hash/work area lớn. Tempfile khác datafile thường và có cách phục hồi riêng; không kết luận mọi file kết thúc bằng `.dbf` đều là datafile.

**Tên đuôi file chỉ là quy ước.** Oracle có thể quản lý file qua Oracle Managed Files (OMF), ASM hoặc filesystem. File không bắt buộc có hậu tố `.dbf` và không nên suy đoán ý nghĩa chỉ từ đường dẫn.

### 2.2. Điều gì xảy ra khi câu lệnh thay đổi dữ liệu?

Khi một phiên cập nhật một hàng, Oracle thường:

1. Tìm hoặc nạp block cần thao tác vào **database buffer cache** của SGA.
2. Thay đổi bản sao block trong bộ nhớ và tạo thông tin undo phù hợp.
3. Tạo các **redo records** mô tả thay đổi cần thiết để tái lập.
4. LGWR ghi redo theo các điều kiện flush, trong đó **COMMIT** yêu cầu redo của giao dịch được bền vững theo cơ chế commit thông thường.
5. **DBWR** ghi những block bị thay đổi (*dirty buffers*) xuống datafile theo nhu cầu cache, checkpoint và các điều kiện khác, có thể **sau thời điểm COMMIT**.

Điều này giải thích tại sao một datafile có thể chưa chứa ngay hình ảnh mới nhất của mọi block nhưng giao dịch commit vẫn được bảo vệ bởi redo. Khi startup sau instance crash, Oracle có thể đọc redo còn cần thiết để khôi phục.

### 2.3. Datafile header và checkpoint

Các datafile có metadata ở phần header, bao gồm thông tin nhận dạng và trạng thái phục vụ tính nhất quán/phục hồi. Oracle cũng lưu thông tin checkpoint liên quan trong control file.

**Checkpoint** đánh dấu tiến độ để database có thể xác định phạm vi redo cần xử lý khi instance recovery. Tiến trình **CKPT** điều phối hoặc báo hiệu checkpoint và cập nhật metadata checkpoint ở những nơi cần thiết; **DBWR** mới là tiến trình chủ yếu ghi các dirty buffer xuống datafile. Không hiểu nhầm rằng CKPT tự ghi toàn bộ dữ liệu bảng hoặc mọi commit phải chờ một checkpoint.

### 2.4. Quan sát datafile trên hệ thống

Với tài khoản được cấp quyền đọc các dynamic performance view (trên máy thực hành quản trị có thể dùng `SYSDBA`), chạy:

~~~sql
SELECT file#, name, status,
       ROUND(bytes / 1024 / 1024) AS size_mb
FROM v$datafile
ORDER BY file#;

SELECT file#, name, status,
       ROUND(bytes / 1024 / 1024) AS size_mb
FROM v$tempfile
ORDER BY file#;
~~~

Hai truy vấn cố ý tách **datafile** và **tempfile**. Trong CDB, thông tin ở một số `V$` view có thể bao gồm nhiều container; khi cần xác định phạm vi PDB, xem thêm ngữ cảnh phiên hoặc cột `CON_ID` ở view có hỗ trợ. Đường dẫn có thể là filesystem, ASM (ví dụ `+DATA/...`) hoặc tên do OMF quản lý.

## 3. Control file: bản đồ cấu trúc và trạng thái của database

### 3.1. Control file chứa gì?

Một **control file** là tệp nhị phân quan trọng mà Oracle cần để nhận diện và **mount** database. Thông tin điển hình gồm:

- **DB_NAME, DBID** và các thông tin nhận dạng database.
- Danh sách, tên và vị trí **datafile**.
- Danh sách **online redo log group/member** và thông tin redo liên quan.
- Thông tin **checkpoint**, redo log sequence, log history và archived redo log.
- Metadata backup/recovery được control file lưu trong vùng bản ghi quản lý theo chính sách tái sử dụng.
- Các thông tin hỗ trợ thay đổi cấu trúc và recovery, chẳng hạn lịch sử `RESETLOGS`/incarnation phù hợp.

Đừng nhầm control file với:

| Tệp/thành phần | Khác control file như thế nào? |
| --- | --- |
| `spfile` / `pfile` | Lưu **tham số khởi tạo instance**, chẳng hạn cấu hình bộ nhớ hoặc `CONTROL_FILES`; không thay thế control file |
| Data dictionary | Metadata logic về table, column, user, privilege… nằm trong các datafile hệ thống, không phải toàn bộ nội dung control file |
| RMAN recovery catalog | Kho metadata backup tùy chọn bên ngoài target database; không phải bản sao đơn giản của control file |
| Datafile | Chứa dữ liệu block; control file chỉ chứa bản đồ và trạng thái cần quản lý các file đó |

### 3.2. Vai trò qua các giai đoạn khởi động

~~~text
STARTUP
   |
   +--> NOMOUNT
   |      Doc SPFILE/PFILE, tao SGA va background processes.
   |
   +--> MOUNT
   |      Doc control file, nhan dien database,
   |      datafiles va online redo log files.
   |
   +--> OPEN
          Mo va kiem tra nhung file can thiet;
          thuc hien instance recovery neu can;
          cho phep truy cap database phu hop.
~~~

Trong mô hình CDB/PDB, việc **OPEN CDB** không tự đảm bảo mọi PDB đang ở trạng thái `READ WRITE`. Khi thực hành truy vấn dữ liệu trong PDB, cần kiểm tra đúng container.

Nếu Oracle không truy cập được **bất kỳ bản control file hợp lệ nào**, database không thể mount bình thường. Trong khi đó, nếu một datafile của tablespace ứng dụng bị mất, tùy phạm vi hỏng và chế độ vận hành có thể thực hiện các quy trình phục hồi file/tablespace thay vì phục hồi lại toàn bộ database.

### 3.3. Multiplex control file

Một khuyến nghị vận hành là có **nhiều bản control file được Oracle duy trì đồng bộ** trên những vị trí lưu trữ có khả năng chịu lỗi khác nhau:

~~~text
CONTROL_FILES
    |
    +-- /disk_a/oradata/DB/control01.ctl
    +-- /disk_b/oradata/DB/control02.ctl
~~~

Oracle ghi nội dung quản lý vào các bản control file đã cấu hình. Đây là **multiplexing**, không phải tạo các control file độc lập cho từng PDB. Việc đặt hai file trên cùng một đĩa vật lý không mang lại khả năng chịu lỗi đĩa tương đương hai thiết bị riêng.

Tham số `CONTROL_FILES` xác định danh sách file được sử dụng:

~~~sql
SHOW PARAMETER control_files;

SELECT name, status
FROM v$controlfile;
~~~

`SHOW PARAMETER` là lệnh của SQL*Plus; truy vấn `V$CONTROLFILE` dùng SQL. Thay đổi danh sách file control cần quy trình phù hợp với môi trường đang hoạt động và có thể yêu cầu khởi động lại instance; không đổi `CONTROL_FILES` như một biến tùy ý trong phiên lab đang phục vụ giao dịch.

**Multiplex không thay thế backup.** Sai sót logic, mất toàn bộ thiết bị lưu trữ, hỏng cấu hình hoặc cả hai copy cùng bị ảnh hưởng vẫn có thể làm mất metadata cần cho recovery. RMAN control file autobackup hoặc chính sách backup phù hợp giúp bảo vệ khả năng khôi phục; khi mất toàn bộ control file, quy trình restore/recreate và xử lý incarnation cần DBA kiểm soát.

## 4. Online redo log: nhật ký phục hồi đang được ghi theo vòng

### 4.1. Redo record lưu gì?

**Redo** là thông tin đủ để Oracle tái áp dụng những thay đổi cần thiết trong quá trình recovery. Nó mô tả thay đổi đối với các cấu trúc database theo định dạng redo nội bộ, **không phải bản sao đầy đủ của hàng dữ liệu ở dạng SQL** hay danh sách các lệnh `INSERT/UPDATE` gốc của người dùng.

Một giao dịch chưa commit cũng có thể tạo redo và redo đó đã được ghi xuống disk. Khi recovery, Oracle có thể sử dụng redo để roll forward những thay đổi rồi xử lý các giao dịch chưa commit bằng undo để bảo đảm tính nhất quán. Vì vậy:

- **Redo** trả lời: “Cần tái áp dụng những thay đổi gì sau sự cố?”
- **Undo** giúp rollback các giao dịch chưa hoàn thành và cung cấp dữ liệu lịch sử cần cho read consistency.
- **Commit** không có nghĩa datafile đã ghi ngay; redo của giao dịch đã được ghi bền vững theo cơ chế commit thông thường.

### 4.2. Cấu trúc group, member và vòng ghi

Online redo log được chia thành các **group**. Một group có **một hoặc nhiều member**; các member trong cùng group chứa cùng dòng redo. `LGWR` ghi tuần tự vào **group hiện tại** (*CURRENT*), sau đó chuyển sang group kế tiếp khi log switch.

~~~text
                        LGWR
                          |
           +--------------+--------------+
           |                             |
           v                             v
    REDO GROUP 1                   REDO GROUP 2
    member 1a                      member 2a
    member 1b                      member 2b
         ^                              |
         |                              v
         +----------- REDO GROUP 3 -----+
                     member 3a
                     member 3b
~~~

Sơ đồ chỉ biểu diễn vòng chuyển group, không phải ba group được ghi đồng thời. Trong một group, **các member là bản sao đồng thời**. Khi group đầy hoặc có lệnh log switch, Oracle dùng group tiếp theo nếu group đó có thể được tái sử dụng.

**Hai khái niệm dễ nhầm:**

1. **Nhiều group** tạo đủ chỗ để LGWR luân phiên và cho phép archiving/checkpoint theo kịp.
2. **Nhiều member trong một group** tạo bản sao dự phòng cho chính group đó, giảm rủi ro khi một redo member hoặc thiết bị lưu trữ bị hỏng.

Có thêm member **không làm tăng thời gian lịch sử redo lưu trong nhóm**: tất cả member của group chứa cùng redo, không nối tiếp nhau.

Một database hoạt động bình thường cần ít nhất hai online redo log group; kích thước và số lượng group được chọn theo khối lượng redo, tốc độ archive, yêu cầu phục hồi và loại hạ tầng. Trong hệ thống RAC còn có khái niệm **redo thread** gắn với instance; không suy luận rằng mỗi database chỉ có duy nhất một redo thread.

### 4.3. LGWR và nguyên tắc write-ahead logging

Quá trình rút gọn:

~~~text
UPDATE tren block trong buffer cache
        |
        +--> Sinh redo vao redo log buffer
        |
       COMMIT
        |
        v
LGWR flush redo can thiet vao online redo log
        |
        v
Commit duoc xac nhan theo co che durability mac dinh
        |
        v
DBWR co the ghi dirty data block ve datafile sau do
~~~

LGWR có thể ghi redo do nhiều nguyên nhân khác ngoài commit, chẳng hạn buffer/log pressure, thời điểm định kỳ hoặc log switch; Oracle cũng sử dụng kỹ thuật **group commit** để tối ưu nhiều giao dịch. Một số tùy chọn commit có thể thay đổi thời điểm xác nhận và ngữ nghĩa durability; bài này nói về cơ chế commit thông thường.

Nếu Oracle instance dừng đột ngột **sau khi commit đã được ghi bền vững nhưng trước khi DBWR cập nhật datafile**, redo cho phép instance recovery đưa datafile về trạng thái nhất quán.

### 4.4. Trạng thái log group và log switch

Các trạng thái thường gặp trong `V$LOG`:

| Trạng thái | Ý nghĩa chính |
| --- | --- |
| `CURRENT` | Group đang được LGWR ghi cho redo thread tương ứng |
| `ACTIVE` | Group không còn current nhưng vẫn có thể cần cho instance recovery; chưa được phép tái sử dụng |
| `INACTIVE` | Group không cần cho instance recovery; có thể được tái sử dụng nếu các điều kiện khác, ví dụ archiving, đã thỏa mãn |
| `UNUSED` | Group chưa từng được ghi sau khi tạo hoặc theo ngữ cảnh trạng thái hiện tại |
| `CLEARING` / `CLEARING_CURRENT` | Trạng thái đặc biệt khi database đang xử lý clear log; không coi là vòng đời bình thường của mọi group |

Trong chế độ `ARCHIVELOG`, group cần được **archive trước khi ghi đè**; group còn ACTIVE cũng chưa thể tái sử dụng. Vì thế database có thể tạm chờ dù đã có nhiều group nếu checkpoint hoặc archiver không theo kịp.

Ví dụ minh họa dòng thời gian:

~~~text
T1:  group 1 = CURRENT
T2:  group 1 day, log switch -> group 2 = CURRENT
T3:  ARCn archive group 1 (neu ARCHIVELOG)
T4:  group 1 het can cho instance recovery -> INACTIVE
T5:  sau cac group khac, LGWR co the tai su dung group 1
~~~

Thứ tự checkpoint và archiving thực tế có thể xen kẽ; không mặc định rằng ngay sau log switch, group cũ lập tức thành `INACTIVE` hoặc được archive xong.

### 4.5. Quan sát online redo log

~~~sql
SELECT group#, thread#, sequence#,
       ROUND(bytes / 1024 / 1024) AS size_mb,
       members, archived, status
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member, status
FROM v$logfile
WHERE type = 'ONLINE'
ORDER BY group#, member;
~~~

Ý nghĩa các cột:

- `GROUP#`: số group của online redo log.
- `THREAD#`: redo thread, quan trọng trong RAC.
- `SEQUENCE#`: số tuần tự của redo log trong thread/incarnation tương ứng.
- `MEMBERS`: số member của group.
- `ARCHIVED`: chỉ thị redo của group đã được archive hay chưa trong ngữ cảnh view.
- `STATUS` ở `V$LOG`: trạng thái **group**; `STATUS` ở `V$LOGFILE`: tình trạng **member**, là hai loại thông tin khác nhau.

Nếu cùng một `GROUP#` xuất hiện ở hai dòng `V$LOGFILE` với hai đường dẫn member, đó là **multiplexing của một group**. Không xóa file member trực tiếp ở hệ điều hành để “dọn dung lượng”; các thay đổi redo log cấu trúc phải đi qua quy trình database hỗ trợ.

## 5. Archived redo log: giữ lịch sử thay đổi sau log switch

### 5.1. Tại sao online redo log là chưa đủ?

Online redo log có **số group hữu hạn** và được **ghi đè luân phiên**. Nếu datafile hỏng và cần khôi phục từ một backup cũ, redo cần thiết có thể đã bị ghi đè từ lâu. Muốn phục hồi từ thời điểm backup đến thời điểm gần hiện tại, cần lưu lịch sử redo đã hoàn tất bên ngoài vòng online log.

Đó là vai trò của **archived redo log**. Khi database ở `ARCHIVELOG` mode, background process **ARCn** (archiver) ghi bản lưu của các online redo log group đã hoàn tất đến destination cấu hình trước khi group được tái sử dụng.

~~~text
REDO GROUP 1 (sequence 100)  -- log switch --> REDO GROUP 2 (seq 101)
              |
              +-- ARCn archive sequence 100
                         |
                         v
                   archived redo log
                   thread 1 / sequence 100

REDO GROUP 2 (sequence 101)  -- log switch --> REDO GROUP 3 (seq 102)
              |
              +-- ARCn archive sequence 101
                         |
                         v
                   archived redo log
                   thread 1 / sequence 101
~~~

Archived redo log là **bản lưu của redo đã được tạo**, không phải tệp sao chép toàn bộ bảng hoặc database và cũng không phải bản backup độc lập của datafile. Mỗi archive có metadata như thread, sequence và thông tin `RESETLOGS`/incarnation để Oracle xác định thứ tự áp dụng chính xác khi recovery.

### 5.2. `ARCHIVELOG` và `NOARCHIVELOG` mode

| Tiêu chí | `ARCHIVELOG` | `NOARCHIVELOG` |
| --- | --- | --- |
| Online redo group | Vẫn tồn tại và được LGWR dùng | Vẫn tồn tại và được LGWR dùng |
| Giữ redo sau khi group hoàn tất | Có archiving theo cấu hình | Không tự lưu lịch sử redo thành archive theo cơ chế thường dùng |
| Instance recovery sau crash khi file còn nguyên | Có thể dùng online redo cần thiết | Có thể dùng online redo cần thiết |
| Media recovery từ backup cũ đến thời điểm sau backup | Có thể nếu backup và **mọi redo cần thiết** còn đủ | Bị hạn chế lớn do redo đã ghi đè không được giữ lại |
| Online/hot backup theo chiến lược RMAN thông thường | Hỗ trợ khi đáp ứng điều kiện backup | Không thể dựa vào cùng chiến lược online backup để bảo đảm nhất quán |
| Nhu cầu quản trị dung lượng archive | Phải giám sát và backup/dọn theo retention | Không phát sinh archive của redo theo cách tương tự |

**Bật `ARCHIVELOG` không tự sinh backup tốt.** Để phục hồi đầy đủ, vẫn cần backup datafile/control file đáng tin cậy, archived redo log liên tục cho khoảng cần phục hồi, online redo cuối nếu có và quy trình kiểm chứng khả năng restore/recover.

### 5.3. Vị trí lưu archive và Fast Recovery Area

Archived redo log có thể được ghi vào các đích archive được khai báo, trong đó thường gặp **Fast Recovery Area (FRA)**. FRA là vùng lưu trữ do Oracle quản lý cho các đối tượng phục hồi như archived redo log, RMAN backup pieces, control file autobackup và các thành phần phục hồi khác tùy cấu hình.

Các tham số hữu ích để quan sát:

- `DB_RECOVERY_FILE_DEST`: vị trí FRA.
- `DB_RECOVERY_FILE_DEST_SIZE`: hạn mức dung lượng FRA.
- `LOG_ARCHIVE_DEST_n`: các archive destination và thuộc tính tương ứng trong cấu hình.

~~~sql
SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER db_recovery_file_dest_size;
SHOW PARAMETER log_archive_dest;
~~~

Nếu FRA hoặc archive destination đầy, **ARCn có thể không archive được log hoàn tất**. Khi các group online không được tái sử dụng vì chưa archive, giao dịch có thể bị chặn và xuất hiện lỗi liên quan archiver như `ORA-00257`. Đây là lỗi dung lượng/luồng archive, không phải bằng chứng datafile đã đầy.

Không xóa archive tùy ý bằng trình quản lý file. Oracle/RMAN cần biết bản nào đã được backup, còn cần cho recovery hoặc Data Guard standby và chính sách retention/deletion. Quy trình xóa phải dựa trên trạng thái backup/restore, khả năng phục hồi và yêu cầu tổ chức; **FRA cũng không thay thế một bản backup an toàn ở hệ thống lưu trữ độc lập**.

### 5.4. Quan sát chế độ và lịch sử archived redo log

~~~sql
SELECT name, log_mode, open_mode
FROM v$database;

SELECT thread#, sequence#, name,
       first_time, next_time, completion_time
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY completion_time DESC
FETCH FIRST 20 ROWS ONLY;
~~~

`LOG_MODE` cho biết `ARCHIVELOG` hoặc `NOARCHIVELOG`. `V$ARCHIVED_LOG` là metadata về các archive/log copy mà control file ghi nhận; **một sequence có thể xuất hiện nhiều dòng** do nhiều destination/copy hoặc lịch sử thao tác. Không lấy số dòng của view để suy luận số group redo hay số bản sao datafile.

Nếu database ở `NOARCHIVELOG`, query thứ hai có thể không có các archived log thông thường. Nếu archive đã được backup rồi xóa khỏi đĩa, view metadata vẫn có thể giữ record tương ứng trong một thời gian; trường `NAME` hoặc dòng metadata **không chứng minh file vẫn đọc được**. Việc xác minh backup/archive còn sử dụng được thuộc quy trình RMAN.

## 6. Các tiến trình nền phối hợp với bốn loại tệp

| Thành phần | Việc chủ yếu | Cần tránh hiểu nhầm |
| --- | --- | --- |
| **DBWR** | Ghi dirty data blocks trong buffer cache xuống **datafile** | Không phải tiến trình ghi online redo |
| **LGWR** | Ghi redo từ redo log buffer xuống **online redo log** | Không ghi trực tiếp bản sao bảng vào datafile mỗi lần commit |
| **CKPT** | Điều phối/báo hiệu checkpoint và cập nhật metadata checkpoint | Không tự thay DBWR ghi mọi data block |
| **ARCn** | Archive các redo group đã hoàn tất khi database ở `ARCHIVELOG` | Không tạo lại dữ liệu đã mất nếu thiếu backup/redo |
| **LREG** | Đăng ký thông tin instance/service với listener (vai trò mạng) | Không tham gia chuỗi ghi datafile/redo trong sơ đồ này |

Đặc biệt, **checkpoint** và **log switch** là hai khái niệm khác nhau:

- **Checkpoint:** tiến độ ghi/synchronization để giới hạn lượng redo cần xét khi instance recovery; liên quan DBWR/CKPT, file header và control file.
- **Log switch:** LGWR đổi sang online redo group khác; group cũ có thể được archive trong `ARCHIVELOG` mode.

Log switch có thể thúc đẩy các hoạt động checkpoint, nhưng **không đồng nghĩa mọi dirty buffer đã được ghi hết trước lúc switch**, cũng không đồng nghĩa archived redo đã hoàn tất tức thì.

## 7. Ba kịch bản sự cố để hiểu vì sao cần từng loại file

### 7.1. Kịch bản A — Instance đột ngột tắt, datafile và redo vẫn còn

Giả sử giao dịch chuyển tiền đã `COMMIT` và LGWR đã flush redo, nhưng DBWR chưa ghi tất cả block liên quan xuống datafile thì máy chủ mất điện.

~~~text
Truoc crash:
  Datafile A: block o trang thai cu
  Online redo: redo cua UPDATE + COMMIT da luu

Sau restart:
  Oracle doc control file/datafile headers
  -> xac dinh redo can thiet
  -> roll forward cac thay doi
  -> xu ly giao dich chua commit (undo)
  -> database nhat quan
~~~

Đây là **instance recovery (crash recovery)**. Trong trường hợp file vật lý vẫn nguyên và redo còn đủ, Oracle thường tự xử lý trong quá trình mở database. Không cần khôi phục toàn bộ datafile từ backup chỉ vì tiến trình instance đã sập.

### 7.2. Kịch bản B — Một datafile bị mất hoặc hỏng

Giả sử `users01.dbf` bị mất do lỗi lưu trữ. Online redo và control file vẫn có thể còn, nhưng Oracle **không thể tự suy ra lại toàn bộ các block từ redo mới nhất** nếu không có nền dữ liệu phù hợp.

~~~text
Backup datafile o thoi diem T0
          |
          | archived redo sequence N, N+1, N+2, ...
          |
Online redo con can thiet (neu co)
          v
Restore datafile tu backup
       + apply redo lien tuc
          v
Phuc hoi toi muc thoi gian/SCN duoc phep
~~~

Đây là **media recovery**: thường phải **restore** bản backup datafile trước rồi **recover** bằng redo thích hợp. Nếu một archived redo log bắt buộc bị thiếu, khả năng phục hồi đến thời điểm mong muốn có thể không còn. Việc có `ARCHIVELOG` nhưng không giữ đủ archive, backup hoặc file quan trọng vẫn không bảo đảm khôi phục thành công.

### 7.3. Kịch bản C — Mất control file

Nếu một bản control file trong cấu hình multiplex bị hỏng, hệ thống có thể gặp lỗi đọc/ghi và cần xử lý theo quy trình DBA. Nếu **tất cả bản control file bị mất**, Oracle không có thông tin cấu trúc cần thiết để mount bình thường. Khôi phục control file từ backup và tiến hành recovery (có thể liên quan `RESETLOGS` theo kịch bản) là quy trình khác với việc restore một datafile.

**Không tự tạo mới một file tên `control01.ctl` rỗng**: control file có cấu trúc nhị phân và metadata nhất quán, không thể thay bằng file văn bản hay file rỗng.

### 7.4. Kịch bản D — Mất một member của online redo group

Nếu group có hai redo member đặt trên hai đĩa, hỏng một member có thể vẫn còn member khác dùng được, tùy tình trạng cụ thể. Nếu group chỉ có một member và member đó hỏng, hậu quả phụ thuộc nó có phải current/active, đã archive hay chưa, và có backup/redo liên quan hay không. Mất **current online redo** có thể đặc biệt nghiêm trọng do chứa các redo mới nhất chưa archive.

Vì vậy **multiplex redo member** nhằm tăng khả năng chịu lỗi của nhóm log hiện tại; **archiving** nhằm giữ lịch sử redo đã hoàn tất; hai cơ chế giải quyết rủi ro khác nhau.

## 8. Phân biệt backup, redo, undo và flashback log

| Khái niệm | Chức năng | Có thể thay thế backup datafile? |
| --- | --- | --- |
| Datafile | Nền dữ liệu vật lý hiện có | Không phải bản backup nếu vẫn nằm cùng hệ thống gặp lỗi |
| RMAN backup | Bản lưu datafile/control file/archived log theo chiến lược backup | Là nguồn **restore** khi bản gốc mất hoặc hỏng |
| Online redo | Redo gần hiện tại, vòng ghi được tái sử dụng | Không |
| Archived redo | Redo lịch sử để apply khi recovery | Không; cần dữ liệu nền/backup tương ứng |
| Undo data | Dữ liệu cần cho rollback/read consistency | Không |
| Flashback log | Phục vụ một số tính năng Flashback Database khi được cấu hình | Không thay chiến lược backup/archived redo hoàn chỉnh |

Một ví dụ cụ thể: **archived redo của ngày hôm nay không phải bản sao database hôm nay**. Muốn khôi phục máy mất toàn bộ datafile, bạn phải có backup/snapshot đúng yêu cầu cộng với redo cần thiết. Tương tự, chỉ có RMAN backup từ ba ngày trước nhưng không có redo liên tục thì thường không thể đưa database đến thời điểm trước khi hỏng chỉ bằng backup đó.

## 9. Thực hành quan sát bốn loại file

Các bước sau không sửa cấu hình database. Bạn cần một Oracle instance có sẵn và tài khoản có quyền xem dynamic performance view. Các view `V$` thường không được cấp mặc định cho schema ứng dụng; nếu chỉ có user thực hành thông thường, nhờ DBA cung cấp kết quả hoặc quyền đọc phù hợp. **Không cấp `SYSDBA` cho ứng dụng chỉ để chạy các truy vấn này.**

### Bước 1 — Nhận diện database và log mode

~~~sql
SELECT name, dbid, open_mode, log_mode
FROM v$database;

SELECT instance_name, status
FROM v$instance;
~~~

Ghi lại database name và `LOG_MODE`. Trong hệ thống có PDB, hai truy vấn phục vụ quan sát cấp database/instance; không đồng nhất `V$INSTANCE.INSTANCE_NAME` với tên PDB đang làm bài.

### Bước 2 — Liệt kê datafile và tempfile

~~~sql
SELECT file#, name, status
FROM v$datafile
ORDER BY file#;

SELECT file#, name, status
FROM v$tempfile
ORDER BY file#;
~~~

Chú ý dữ liệu và file tạm được quản lý riêng. Không sửa hoặc di chuyển trực tiếp các file được liệt kê tại hệ điều hành khi database đang sử dụng.

### Bước 3 — Xem các bản control file

~~~sql
SHOW PARAMETER control_files;

SELECT name, status
FROM v$controlfile;
~~~

So sánh tên/vị trí file với cấu hình `CONTROL_FILES`. Nếu nhiều file nằm chung một storage hoặc cùng failure domain, số lượng file lớn hơn một chưa chắc đạt mục tiêu chịu lỗi.

### Bước 4 — Xem redo log group và member

~~~sql
SELECT group#, thread#, sequence#, status, archived,
       ROUND(bytes/1024/1024) AS size_mb, members
FROM v$log
ORDER BY thread#, group#;

SELECT group#, member, status
FROM v$logfile
WHERE type = 'ONLINE'
ORDER BY group#, member;
~~~

Tìm group có `STATUS = 'CURRENT'` trong `V$LOG`. Đếm member trong `V$LOGFILE` để hiểu multiplex. Nếu `MEMBERS = 2`, đừng nhầm rằng nhóm đã có hai sequence redo khác nhau; đây là hai file cho cùng group.

### Bước 5 — Xem archive destination và archived log

~~~sql
SELECT name, log_mode
FROM v$database;

SHOW PARAMETER db_recovery_file_dest;
SHOW PARAMETER log_archive_dest;

SELECT thread#, sequence#, name, completion_time
FROM v$archived_log
WHERE name IS NOT NULL
ORDER BY completion_time DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Nếu `LOG_MODE = 'ARCHIVELOG'` và có hoạt động phát sinh archive, bạn có thể thấy nhiều record lịch sử. Không khẳng định archive còn trên disk chỉ từ `NAME`; quá trình backup/xóa/copy có thể tạo thêm record hoặc thay đổi trạng thái lưu trữ.

### Bước 6 — Quan sát log switch trên database lab riêng (tùy chọn)

**Chỉ chạy nếu được giao quyền DBA trên một instance lab độc lập**, có đủ dung lượng lưu archive và chấp nhận phát sinh I/O/redo. Không thực hiện trên production hoặc môi trường chia sẻ.

Trước tiên ghi lại `SEQUENCE#` và `STATUS` từ `V$LOG` ở Bước 4. Sau đó trong phiên quản trị:

~~~sql
ALTER SYSTEM SWITCH LOGFILE;
~~~

Truy vấn `V$LOG` lại để quan sát group `CURRENT` và sequence đã thay đổi. Trong `ARCHIVELOG` mode, archiver có thể tiếp tục lưu group vừa hoàn tất; tùy thời điểm kiểm tra, `V$ARCHIVED_LOG` có thể chưa xuất hiện record mới ngay tức thì. Trong `NOARCHIVELOG` mode, chuyển group không tự tạo archived log.

Lệnh `ALTER SYSTEM SWITCH LOGFILE` **gây tác động thực sự**, không phải truy vấn chỉ đọc. Nó không trực tiếp kiểm tra restore/recover, cũng không buộc mọi dirty block trong database đã ghi xong. Sau thao tác, kiểm tra dung lượng archive/FRA nếu hệ thống có archiving.

## 10. Quy tắc vận hành khi thiết kế lưu trữ và backup

### 10.1. Bảo vệ control file và online redo

- Đặt các bản control file/multiplexed redo member trên những thiết bị hoặc failure domain phù hợp; hai đường dẫn trên cùng đĩa hỏng chung không đạt bảo vệ mong muốn.
- Không chỉnh sửa nhị phân hoặc di chuyển thủ công datafile/control file/redo member khi Oracle đang quản lý chúng.
- Theo dõi thông báo lỗi I/O và tình trạng từng member; lỗi một bản copy không có nghĩa có thể bỏ qua lâu dài.
- Với ASM, OMF, RAC hoặc storage replication, cách phân bổ bản sao và quản lý file cần tuân theo công cụ nền tảng; không bắt chước lệnh file hệ điều hành một cách máy móc.

### 10.2. Bảo vệ archived redo và backup

- Chọn chính sách backup **datafile, control file và archived redo log** đáp ứng RPO/RTO, retention và yêu cầu phục hồi đã thống nhất.
- Bảo đảm chuỗi archived redo đủ cho các điểm phục hồi dự định; lưu log quá ít có thể làm mất khả năng phục hồi dù database vẫn đang chạy tốt.
- Theo dõi dung lượng FRA/archive destinations, tốc độ sinh redo, tốc độ archive và thời gian backup. Dung lượng cần thiết phụ thuộc khối lượng thay đổi thực tế, không chỉ kích thước database.
- Chỉ xóa archived redo qua quy trình quản trị/RMAN đã kiểm chứng và có xét yêu cầu standby/Data Guard nếu có.
- Thử **restore và recover** định kỳ trên môi trường được phép; file backup tồn tại không tự chứng minh backup sử dụng được.

### 10.3. Bật `ARCHIVELOG` là thay đổi vận hành

Một database có thể được chuyển giữa `NOARCHIVELOG` và `ARCHIVELOG` bằng thao tác quản trị ở trạng thái thích hợp, thường yêu cầu database được **mount nhưng chưa open**, nên có ảnh hưởng đến availability. Người quản trị cần cấu hình archive destination/dung lượng trước, có kế hoạch downtime, bảo đảm backup sau thay đổi và kiểm chứng việc archive thực sự hoạt động.

Ví dụ cú pháp trên một database lab đơn instance, do DBA tự quản lý, chỉ để nhận biết trình tự:

~~~sql
-- Minh hoa thao tac quan tri co downtime, KHONG chay tren production.
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE OPEN;

SELECT log_mode
FROM v$database;
~~~

Đoạn này **không phải chỉ dẫn áp dụng tự động**. Trước khi chạy cần xác nhận cấu hình archive destination, quyền SYSDBA, phạm vi CDB/PDB, trạng thái dịch vụ, storage, backup và quy trình môi trường. RAC/Oracle Restart/Data Guard có điều kiện và trình tự riêng; không áp dụng máy móc bốn lệnh trên.

## 11. Những nhầm lẫn phổ biến

**“COMMIT nghĩa là datafile đã được ghi xong.”** Sai. Trong cơ chế commit thông thường, redo cần thiết được flush để bảo đảm durability; DBWR có thể ghi datafile muộn hơn. Đó là lý do redo rất quan trọng với instance recovery.

**“Control file chỉ chứa tên datafile.”** Chưa đủ. Nó còn chứa thông tin database identity, log, checkpoint, recovery và nhiều metadata khác. Mất toàn bộ control file là tình huống quản trị nghiêm trọng.

**“Online redo log chính là archived redo log.”** Sai. Online redo được LGWR ghi theo vòng và có thể tái sử dụng; archived redo là bản lưu của group đã hoàn tất, giữ lịch sử vượt ra ngoài vòng đó khi có archiving.

**“Group nhiều member nghĩa là có nhiều bản redo theo thời gian.”** Sai. Các member của một group là bản sao cùng nội dung nhằm chịu lỗi. Chuỗi thời gian gắn với các group/sequence thay nhau được ghi và archived log được lưu.

**“ARCHIVELOG tự bảo đảm khôi phục đến thời điểm bất kỳ.”** Sai. Khả năng khôi phục phụ thuộc backup, tính liên tục của redo, trạng thái control file, archive destinations và thời điểm/SCN cần phục hồi.

**“CKPT tự ghi toàn bộ dirty block.”** Sai. DBWR ghi block dữ liệu. CKPT quản lý phần công việc checkpoint/metadata theo cơ chế Oracle.

**“Archived redo log có thể xóa ngay khi log switch xong.”** Rất nguy hiểm. Archive có thể còn cần cho RMAN recovery, backup và Data Guard. Phải căn cứ retention/deletion policy và khả năng restore đã kiểm chứng.

**“Undo là một loại redo khác.”** Sai. Undo hỗ trợ rollback/read consistency; redo mô tả thay đổi phục vụ recovery, bao gồm thay đổi liên quan dữ liệu undo. Chúng có mục đích khác nhau.

## 12. Câu hỏi ôn tập và tình huống suy luận

1. Trong lúc `COMMIT` hoàn tất, datafile chưa được DBWR cập nhật toàn bộ. Vậy điều gì giúp Oracle phục hồi giao dịch nếu instance crash?
2. Một tablespace có thể có nhiều datafile không? Một datafile có đồng thời thuộc hai tablespace không?
3. Vì sao hai control file cùng nằm trên một ổ đĩa không cho mức bảo vệ tương đương hai control file ở hai vùng lưu trữ độc lập?
4. Group 2 có hai redo member và đang `CURRENT`. Điều này có nghĩa Oracle có hai sequence redo khác nhau trong group không?
5. Khác nhau giữa `ACTIVE` và `INACTIVE` trong `V$LOG` là gì?
6. Khi database ở `NOARCHIVELOG`, instance crash có nhất thiết khiến toàn bộ redo không sử dụng được không? Vì sao?
7. Một datafile mất, bạn có archived redo của hai ngày gần nhất nhưng không có backup datafile nào. Có thể xem archived redo là bản sao đầy đủ của datafile để restore không?
8. Vì sao FRA đầy có thể làm ứng dụng bị chặn dù vẫn còn dung lượng ở các datafile?
9. Khi cần khôi phục đến một SCN sau thời điểm backup, vì sao phải giữ đủ redo liên tục qua các log sequence?
10. Khác biệt giữa checkpoint và log switch; vai trò tương ứng của DBWR, CKPT, LGWR và ARCn là gì?

**Gợi ý trả lời:**

1. Redo được LGWR ghi bền vững vào online redo log giúp tái áp dụng thay đổi khi instance recovery.
2. Có thể có nhiều datafile trong một tablespace; một datafile thuộc một tablespace tại một thời điểm.
3. Chúng cùng chịu rủi ro hỏng thiết bị hoặc failure domain.
4. Không. Hai member cùng giữ nội dung redo của một group; sequence thuộc dòng redo của group/thread.
5. `ACTIVE` còn có thể cần cho instance recovery; `INACTIVE` không còn cần cho instance recovery nhưng việc tái sử dụng còn tùy archiving/điều kiện khác.
6. Không. Online redo vẫn dùng cho instance recovery khi file liên quan còn đủ; thiếu archived redo chủ yếu giới hạn lịch sử dành cho media recovery.
7. Không. Cần nền dữ liệu phù hợp từ backup và redo cần thiết; archived redo không phải bản sao datafile.
8. ARCn không thể lưu log cần archive, khiến online redo group chưa đủ điều kiện tái sử dụng.
9. Thiếu một đoạn redo có thể khiến recovery không thể áp dụng chuỗi thay đổi từ backup đến SCN mục tiêu.
10. Checkpoint liên quan tiến độ ghi datafile và metadata; log switch là đổi group ghi redo. DBWR ghi dirty block, CKPT điều phối checkpoint/metadata, LGWR ghi online redo, ARCn lưu redo đã hoàn tất.

## Tài liệu tham khảo Oracle

- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): kiến trúc vật lý, datafile, control file, redo log và quy trình nền.
- [Oracle Database Backup and Recovery User's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/): nguyên lý backup, restore, recovery, archived redo và RMAN.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): tra cứu chính xác cấu trúc `V$DATAFILE`, `V$CONTROLFILE`, `V$LOG`, `V$LOGFILE` và `V$ARCHIVED_LOG` theo phiên bản.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản trị physical files, checkpoint, archive mode và các cấu hình vận hành.
