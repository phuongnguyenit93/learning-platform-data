# Ranh giới sao lưu, phục hồi và bảo trì CDB/PDB trong Oracle Database

Trong kiến trúc **Oracle Multitenant**, một **Container Database (CDB)** có thể chứa nhiều **Pluggable Database (PDB)**. Mỗi PDB cung cấp không gian dữ liệu và nhiều đối tượng quản trị riêng cho ứng dụng, nhưng vẫn chia sẻ một phần quan trọng của cơ sở hạ tầng database. Vì thế, khi thiết kế **backup, recovery và maintenance**, ranh giới “PDB nào sở hữu dữ liệu?” không luôn trùng với “thành phần nào phải được sao lưu, phục hồi hoặc bảo trì cùng nhau?”.

Ví dụ: một CDB chứa `PDB_SALES` cho bán hàng và `PDB_HR` cho nhân sự. Nếu người dùng xóa nhầm bảng trong `PDB_SALES`, có thể cần khôi phục đúng PDB đó mà giữ nguyên `PDB_HR`. Nhưng nếu mất **control file** hoặc xảy ra lỗi khiến toàn CDB không mở được, tình huống đã vượt ra khỏi phạm vi một PDB. Việc nâng cấp phần mềm Oracle hoặc quản lý **archived redo logs** cũng không thể coi là hai hệ thống độc lập hoàn toàn.

Bài học giải thích cách xác định đúng phạm vi tác động trong Oracle Multitenant, cách lập chiến lược RMAN backup/restore/recover theo CDB hoặc PDB, và các loại bảo trì cần thực hiện ở cấp toàn CDB hay từng PDB.

## 1. Mô hình thành phần và mức độ cô lập

Một CDB thường gồm:

- **`CDB$ROOT`**: root container, giữ metadata chung và hạ tầng cần thiết cho toàn CDB; không phải nơi dành cho bảng nghiệp vụ riêng của ứng dụng.
- **`PDB$SEED`**: template PDB do Oracle quản lý, dùng làm cơ sở tạo PDB mới theo cơ chế được hỗ trợ.
- **PDB ứng dụng**: ví dụ `PDB_SALES`, `PDB_HR`, mỗi PDB có đối tượng schema và dữ liệu nghiệp vụ riêng.
- **Application root/application PDB**, nếu dùng application container: mô hình quản lý đối tượng ứng dụng chung và các PDB thành viên, có thêm quan hệ phụ thuộc riêng cần xem xét khi bảo trì.

Sơ đồ:

~~~text
                        ORACLE CDB
        +------------------------------------------+
        | CDB$ROOT (thông tin chung, thành phần hệ thống)
        |                                          |
        | PDB$SEED (template)                      |
        |                                          |
        | +--------------+  +------------------+   |
        | | PDB_SALES    |  | PDB_HR           |   |
        | | schema/data  |  | schema/data      |   |
        | | tablespaces  |  | tablespaces      |   |
        | +--------------+  +------------------+   |
        +------------------------------------------+
             |             |               |
             +-------------+---------------+
                           |
                 Hạ tầng vật lý chung:
          control file, online redo, instance,
          archived redo, cấu hình nhiều thành phần
~~~

Sơ đồ giản lược: những chi tiết như nhiều instance RAC, ASM, local undo, TDE keystore hoặc standby có thể thay đổi hình thức triển khai nhưng không làm biến mất các phụ thuộc CDB chung.

### 1.1 Ranh giới dữ liệu logic và ranh giới vật lý

| Thành phần | Phạm vi điển hình | Ý nghĩa với backup/recovery |
|---|---|---|
| Bảng, index, schema ứng dụng | Thuộc một PDB | Có thể cần phục hồi một tablespace hoặc một PDB thay vì toàn CDB |
| Datafile của tablespace ứng dụng | Liên kết với PDB sở hữu tablespace | Có thể đưa vào backup/restore chọn lọc cho PDB |
| Datafile của root | Thuộc `CDB$ROOT` | Hỏng thành phần quan trọng của root có thể ảnh hưởng nhiều/tất cả PDB |
| Seed datafiles | Thuộc `PDB$SEED` | Cần được quản lý đúng trong bảo vệ CDB và quy trình tạo PDB |
| Control file | Cấp CDB | Chứa cấu trúc database và thông tin cần thiết cho recovery; mất/hỏng có thể tác động toàn CDB |
| Online redo logs | Cấp CDB/instance (hoặc thread trong RAC) | Ghi redo của thay đổi thuộc nhiều container |
| Archived redo logs | Cấp CDB | Phục vụ khả năng recovery, kể cả khi chỉ muốn khôi phục một PDB |
| SPFILE và nhiều cấu hình instance | Chủ yếu CDB/instance | Cần backup cấu hình; mất cấu hình có thể ảnh hưởng việc khởi động toàn CDB |
| TDE keystore/keys | Phụ thuộc united/isolated keystore và kiến trúc đã chọn | Phải bảo vệ đủ khóa để đọc dữ liệu mã hóa sau restore |
| Temporary tablespace / undo | Có ranh giới container và biến thể theo local/shared undo | Hỗ trợ runtime/recovery; không thể suy “mọi thứ là riêng PDB” |

Điểm mấu chốt: **PDB có khả năng quản lý và khôi phục dữ liệu ứng dụng theo phạm vi PDB**, nhưng nó **không phải một Oracle database hoàn toàn độc lập về mọi lớp vật lý**.

## 2. Những khái niệm cần phân biệt trước khi thiết kế phương án

### 2.1 Backup, restore, recover và open

Các thuật ngữ thường bị dùng thay cho nhau:

**Backup** là tạo bản sao có quản lý của datafile và các thành phần cần thiết để bảo vệ dữ liệu, thường do **RMAN (Recovery Manager)** thực hiện. Backup có thể là backupset, image copy, full/incremental và có chính sách retention riêng.

**Restore** là lấy bản sao đã sao lưu đưa datafile hoặc đối tượng được hỗ trợ trở lại vị trí/cấu hình phục hồi. Restore một datafile từ tối qua không có nghĩa dữ liệu tự trở lại đến đúng thời điểm hiện tại.

**Recover** là áp dụng các thay đổi cần thiết, thường từ incremental backup và redo được lưu giữ, để đưa dữ liệu đến trạng thái nhất quán ở thời điểm mục tiêu.

**Open** là đưa PDB hoặc CDB vào trạng thái hoạt động phù hợp sau khi đã thỏa các điều kiện recovery. Có thể cần thao tác mở PDB riêng; restore/recover thành công không đồng nghĩa ứng dụng đã kết nối bình thường.

~~~text
Backup đã có ──────► RESTORE các datafile phù hợp
                           |
Redo / incremental ────────┤
                           v
                       RECOVER
                           |
                           v
                 Kiểm tra, OPEN, xác nhận ứng dụng
~~~

Các hoạt động trên không tự động tương đương **flashback**, **clone** hoặc **unplug/plug** PDB.

### 2.2 RPO và RTO

- **RPO (Recovery Point Objective)**: mức độ mất dữ liệu tối đa có thể chấp nhận, đo bằng khoảng cách thời gian giữa sự cố và điểm dữ liệu phục hồi được.
- **RTO (Recovery Time Objective)**: thời gian tối đa mục tiêu để khôi phục dịch vụ sau sự cố.

Ví dụ nghiệp vụ bán hàng yêu cầu **RPO tối đa 5 phút, RTO tối đa 30 phút**. Việc backup PDB mỗi đêm **không tự nó** đảm bảo RPO 5 phút. Muốn phục hồi gần thời điểm sự cố cần chuỗi redo/archivelog khả dụng hoặc cơ chế bảo vệ bổ sung, và phải tính khả năng mất online redo nếu mất cả hệ thống.

RTO cũng phụ thuộc tổng kích thước dữ liệu phải restore, tốc độ storage/network, thời gian recover redo, mở PDB và kiểm tra ứng dụng. Backup đúng loại mà chưa từng thử restore có thể không đạt RTO đã cam kết.

### 2.3 Complete recovery và point-in-time recovery (PITR)

| Kiểu phục hồi | Mục tiêu | Tình huống |
|---|---|---|
| **Complete recovery** | Khôi phục dữ liệu đến điểm nhất quán mới nhất có thể bằng backup và redo khả dụng | Mất một datafile do lỗi storage nhưng muốn giữ các giao dịch đã commit |
| **Point-in-time recovery (PITR)** | Đưa dữ liệu về một thời điểm/SCN trước một sự kiện gây lỗi | Ứng dụng xóa hàng hoặc chạy sai batch lúc 10:15, cần dữ liệu trước 10:15 |

PITR cố ý bỏ qua những thay đổi sau điểm chọn **trong phạm vi được phục hồi**. Nó đòi hỏi chiến lược xử lý các giao dịch hợp lệ sau thời điểm đó, đặc biệt nếu có tích hợp ứng dụng bên ngoài.

## 3. Phạm vi sao lưu: toàn CDB hay từng PDB?

RMAN có thể làm việc với dữ liệu **toàn CDB** hoặc **một hay một nhóm PDB** theo những tính năng/giới hạn của Oracle release hiện hành. Việc chọn scope quyết định những gì được bảo vệ trực tiếp bởi công việc đó.

### 3.1 Backup toàn CDB

Khi kết nối RMAN tới **CDB root** với quyền phù hợp, cú pháp minh họa:

~~~rman
BACKUP DATABASE;
~~~

Ở cấp root, lệnh backup database nhằm bảo vệ các datafile thuộc CDB theo phạm vi và chế độ backup đó, gồm root/seed/PDB theo cấu hình và trạng thái hỗ trợ. Trong một kế hoạch backup vận hành, cần bảo vệ **archived redo logs, control file, SPFILE** và những phần tử ngoài database có liên quan; không mặc định chỉ dòng `BACKUP DATABASE` đã đáp ứng toàn bộ chiến lược khôi phục.

Ví dụ minh họa một policy tổng quát:

~~~rman
-- Chạy khi đã xác định đúng CDB root và cấu hình RMAN.
BACKUP DATABASE PLUS ARCHIVELOG;
~~~

Phần `PLUS ARCHIVELOG` yêu cầu công việc backup chú ý đến archived redo theo cơ chế RMAN. Dù vậy, một chính sách production còn phải xác định retention, frequency, backup repository/catalog, control file/SPFILE autobackup, backup encryption, media management, khả năng khôi phục offsite và giám sát job. Không đưa một lệnh ví dụ thành quy trình backup hoàn chỉnh của doanh nghiệp.

**Điểm mạnh:** bảo vệ được bức tranh vật lý CDB rộng hơn, cần thiết cho các sự cố ảnh hưởng root hoặc toàn hệ thống.

**Giới hạn:** tốn thời gian/dung lượng nếu nhiều PDB lớn; yêu cầu backup và retention của từng ứng dụng có thể khác nhau. Có thể dùng full/incremental và chọn lọc, nhưng mọi tối ưu phải giữ khả năng khôi phục toàn hệ thống.

### 3.2 Backup một PDB cụ thể

Kết nối RMAN trong ngữ cảnh **CDB root** với quyền phù hợp:

~~~rman
BACKUP PLUGGABLE DATABASE pdb_sales;
~~~

Lệnh minh họa yêu cầu backup phần datafile thuộc `PDB_SALES`, thay vì tất cả PDB. Tùy phiên bản, RMAN còn hỗ trợ lựa chọn nhiều PDB, backup tablespace của một PDB hoặc các hình thức incremental.

Tuy nhiên:

- **Redo phục vụ recovery không tách riêng thành một hệ thống redo của từng PDB.** Archived redo là tài nguyên CDB chung.
- Bản backup datafile PDB có thể cần thông tin về CDB metadata, file structure, control file/catalog và redo liên quan để recover.
- Chỉ backup PDB không thay thế nhiệm vụ bảo vệ control file, SPFILE, root và seed khi toàn CDB gặp sự cố.
- Backup PDB phải được thử restore trong bối cảnh cấu hình thật, đặc biệt nếu chuyển đích hoặc có TDE.

Nhiều release hỗ trợ kết nối RMAN trực tiếp tới một PDB cho một số thao tác. **Tập lệnh, quyền, khả năng quản trị metadata/repository và phạm vi recovery trong kết nối PDB có giới hạn riêng**, vì thế đội vận hành thường thiết kế backup tập trung từ CDB root; không suy rằng mọi lệnh RMAN chạy ở root đều được phép chạy khi target là một PDB.

### 3.3 Bảng so sánh scope backup

| Tiêu chí | Backup CDB | Backup PDB |
|---|---|---|
| Dữ liệu được nhắm tới | Nhiều/toàn bộ container trong cùng CDB | Datafile của PDB được chọn |
| Phục vụ sự cố hỏng root/metadata chung | Là thành phần cốt lõi của chiến lược | **Không đủ khi đứng một mình** |
| Phục vụ restore một PDB bị mất datafile | Có thể dùng backup dữ liệu tương ứng theo khả năng RMAN | Phù hợp cho bảo vệ có chọn lọc của PDB |
| Chi phí backup | Thường lớn hơn nếu nhiều PDB | Có thể tối ưu theo nhu cầu từng ứng dụng |
| Redo/controlfile/SPFILE | Vẫn phải bảo vệ theo policy | Vẫn phụ thuộc thành phần cấp CDB |
| Quản trị | Cần quyền và định danh CDB/root rõ ràng | Cần đúng tên/định danh PDB và ngữ cảnh hỗ trợ |

Một kế hoạch tốt có thể **kết hợp** backup toàn CDB định kỳ, backup PDB theo SLA và backup archived redo đủ thường xuyên. Điều quan trọng là mọi nhánh đều tạo thành **chuỗi khôi phục được** cho những sự cố cần bảo vệ.

## 4. Redo, undo và các phụ thuộc chung khiến ranh giới phục hồi phức tạp

### 4.1 Redo thuộc phạm vi CDB

Các thay đổi dữ liệu tạo redo để Oracle duy trì khả năng recover. Trong một CDB, online redo/archived redo là cơ sở hạ tầng chung, có thể chứa thông tin thay đổi của nhiều container. Với RAC, có nhiều redo thread thuộc các instance nhưng vẫn nằm trong kiến trúc quản lý chung của database.

Ví dụ:

~~~text
10:00 - PDB_SALES: thêm đơn #1001
10:01 - PDB_HR:    cập nhật nhân viên
10:02 - PDB_SALES: cập nhật trạng thái đơn
                  |
                  v
            Redo infrastructure CDB
                  |
                  v
            Archived redo logs
~~~

Muốn recover `PDB_SALES` tới một thời điểm, Oracle cần các thành phần phục hồi tương ứng và redo cần thiết. Không có nghĩa phải khôi phục dữ liệu `PDB_HR` về cùng thời điểm khi chỉ thực hiện PDB PITR, nhưng không thể quản lý archived redo như những file hoàn toàn tách biệt chỉ theo tên PDB.

### 4.2 Local undo và shared undo

Multitenant hỗ trợ các kiến trúc undo khác nhau tùy release/chế độ:

- **Local undo:** mỗi PDB có vùng undo của riêng nó (ngoài undo thuộc root theo tổ chức của CDB), hỗ trợ nhiều hoạt động cô lập PDB.
- **Shared undo:** undo được chia sẻ theo cơ chế cũ; một số tính năng riêng PDB có thể bị hạn chế hoặc có quy trình khác.

Undo phục vụ rollback và read consistency, có quan hệ với phục hồi, nhưng **không phải bản sao backup có thể thay thế archived redo**. Một số khả năng PDB PITR, flashback, unplug/relocate và hot clone phụ thuộc release và local undo. Khi xây runbook không được bỏ qua trạng thái undo mode của CDB.

### 4.3 Control file và SPFILE không thuộc một PDB ứng dụng

Control file lưu thông tin cấu trúc và recovery quan trọng của database. SPFILE chứa tham số khởi động/cấu hình instance. Nếu mất chúng, khả năng đưa CDB và các PDB trở lại hoạt động bị ảnh hưởng. Vì thế:

- Thiết kế **control file autobackup** hoặc quy trình tương đương theo hướng dẫn RMAN.
- Bảo vệ SPFILE và thông tin cấu hình liên quan.
- Lưu độc lập nơi đặt backup/metadata phục hồi khi máy chủ chính hỏng.
- Giữ hồ sơ DBID, DB_UNIQUE_NAME, DB_NAME, cấu hình ASM/storage, đường dẫn và quyền truy cập cần thiết.

Backup riêng một PDB có thể hữu ích cho lỗi PDB, nhưng không bảo vệ đầy đủ toàn bộ các thành phần cấp CDB này.

## 5. Các cấp độ restore/recover trong CDB

Một sự cố có thể xử lý ở nhiều cấp, từ một đối tượng logic đến toàn database. Nên chọn **phạm vi nhỏ nhất có khả năng phục hồi đúng đắn**, đồng thời xác nhận các phụ thuộc thực tế.

| Mức phục hồi | Đối tượng/tình huống | Ranh giới tác động |
|---|---|---|
| Khôi phục dữ liệu logic | Một bảng, một tập hàng hoặc lỗi ứng dụng | Có thể dùng Flashback Query, export/import, phục hồi sang môi trường phụ nếu phù hợp; không luôn cần PITR |
| Datafile/tablespace thuộc PDB | Hỏng datafile của một tablespace ứng dụng | Có thể chỉ đưa đối tượng hoặc PDB liên quan vào phạm vi thao tác |
| Whole-PDB restore/recovery | Datafile PDB bị mất/hỏng ở phạm vi rộng | Phục hồi PDB được chọn, không mặc định khôi phục mọi PDB |
| PDB point-in-time recovery | Xóa nhầm dữ liệu ở một PDB lúc 10:15 | Đưa PDB đó về thời điểm trước lỗi; PDB khác tiếp tục ở trạng thái của chúng |
| CDB/root-level recovery | Mất root datafile, control file hoặc sự cố toàn CDB | Phạm vi chung, có thể ảnh hưởng tất cả PDB |
| CDB point-in-time recovery | Cần đưa toàn CDB về mốc chung | Các container thuộc phạm vi CDB bị ảnh hưởng bởi mốc phục hồi |

### 5.1 Trường hợp mất datafile của một PDB

Giả sử một datafile ở `PDB_SALES` bị hỏng, các thành phần chung và `PDB_HR` vẫn hoạt động. Mục tiêu là lấy lại dữ liệu của `PDB_SALES` và áp dụng redo tới điểm hợp lệ mới nhất mà không khiến HR quay về quá khứ.

Một runbook ở mức khái niệm:

1. Xác định chính xác CDB, PDB, datafile/tablespace bị ảnh hưởng và trạng thái lỗi.
2. Kiểm tra backup datafile và archived redo cần thiết, tình trạng storage và quyền truy cập.
3. Cô lập phạm vi lỗi, chuẩn bị ngừng kết nối ứng dụng hoặc đóng PDB/tablespace theo quy trình phù hợp.
4. Dùng RMAN restore phần dữ liệu hỏng và recover đến trạng thái nhất quán.
5. Mở lại đối tượng/PDB, xác nhận dữ liệu và dịch vụ ứng dụng.
6. Kiểm tra những backup và trạng thái recovery sau sự cố.

Các lệnh `RESTORE PLUGGABLE DATABASE` và `RECOVER PLUGGABLE DATABASE` có thể nằm trong quy trình khôi phục toàn PDB, nhưng **không được đưa nguyên ví dụ xuống production** khi chưa xác định lỗi, phiên bản và trạng thái PDB. Với lỗi chỉ một datafile, phương án mức datafile/tablespace có thể phù hợp hơn.

### 5.2 Trường hợp xóa nhầm dữ liệu: PDB PITR

Giả sử `PDB_SALES` có một batch xóa dữ liệu sai lúc 10:15; `PDB_HR` vẫn ghi dữ liệu quan trọng trong suốt thời gian đó. Nếu không thể sửa bằng cách đảo tác động hoặc phục hồi đối tượng logic, có thể cân nhắc **PDB point-in-time recovery** để đưa riêng Sales về trước 10:15.

Sơ đồ thời gian:

~~~text
                     10:10         10:15            10:30
                       |             |                |
PDB_SALES:  ----------- OK ---------- X sai ---------- DML mới
                       |
                  PDB PITR chọn mốc 10:10
                       |
PDB_SALES sau PITR: dữ liệu tại mốc 10:10 (và quy trình mở hợp lệ)

PDB_HR:     ----------- OK ---------- OK ------------- OK
                          (giữ tiến trình riêng)
~~~

PDB PITR không phải “xóa đúng một câu SQL sai rồi giữ nguyên tất cả thay đổi khác”. Các giao dịch hợp lệ của Sales sau mốc PITR cũng phải được đối chiếu và có thể cần áp dụng lại qua ứng dụng hoặc cơ chế phục hồi chọn lọc khác.

RMAN có quy trình hỗ trợ **PDB PITR** với dữ liệu sao lưu, redo, môi trường phụ/auxiliary khi cần, và các bước phục hồi/mở PDB theo release. Cú pháp và tính khả dụng phụ thuộc phiên bản, undo mode, backup configuration và hiện trạng database; runbook phải được thử trên hệ thống tương đương. Khi Oracle dùng auxiliary instance/destination, cần thêm không gian lưu trữ và tài nguyên trong thời gian recovery.

### 5.3 Vì sao whole-CDB PITR có blast radius lớn hơn?

Nếu tiến hành recovery ở phạm vi toàn CDB về 10:10, dữ liệu của nhiều PDB có thể cùng trở lại trạng thái tại mốc đó. Điều này làm mất hoặc đòi hỏi đối soát các giao dịch sau 10:10 ở các hệ thống không hề gây ra lỗi ban đầu.

Vì vậy:

- Với lỗi logic khu trú ở một PDB, ưu tiên đánh giá phương án **PDB PITR hoặc object-level recovery**.
- Với mất mát cấu trúc CDB/điều kiện phải phục hồi toàn database, tính đến tác động của mọi PDB, các luồng tích hợp và thời điểm khôi phục chung.
- Trong mọi trường hợp phải xác định **RPO/RTO và nghiệp vụ cần đối soát sau recovery**, không chỉ xác định được lệnh RMAN.

### 5.4 Lỗi root/control file không thể coi là lỗi một PDB

Nếu root datafile hoặc control file cần thiết bị mất/hỏng, tính sẵn sàng của toàn CDB có thể bị ảnh hưởng. Lúc này backup riêng `PDB_SALES` hoặc `PDB_HR` không đủ cho việc dựng lại hệ thống. Cần chiến lược backup/recovery toàn CDB gồm metadata, datafile chung, archived redo, cấu hình và các dependency ngoài database.

## 6. Flashback trong Multitenant: hữu ích nhưng có ranh giới

**Flashback** là nhóm cơ chế đưa dữ liệu hoặc trạng thái database về trước một sự kiện, nhưng mỗi biến thể khác nhau rất nhiều về phạm vi.

### 6.1 Flashback Query / Flashback Table

Với các tính năng và quyền phù hợp, có thể truy vấn dữ liệu lịch sử từ một thời điểm hoặc thực hiện thao tác flashback bảng ở phạm vi đối tượng. Ví dụ minh họa cú pháp Flashback Query trong PDB:

~~~sql
SELECT order_id, status
FROM orders AS OF TIMESTAMP (
    TO_TIMESTAMP('2026-11-14 09:50:00', 'YYYY-MM-DD HH24:MI:SS')
)
WHERE order_id = :p_order_id;
~~~

Điều này phụ thuộc khả năng cung cấp phiên bản dữ liệu từ undo và điều kiện của đối tượng. **Undo retention không phải một cam kết tuyệt đối** rằng mọi thời điểm lịch sử đều có thể query; các DDL hoặc thay đổi cấu trúc cũng có giới hạn.

Phù hợp với mục tiêu tìm lại một số hàng, kiểm tra dữ liệu trước khi ứng dụng cập nhật sai hoặc phục hồi logic chọn lọc nếu khả dụng.

### 6.2 PDB Flashback

Ở những Oracle release và chế độ undo hỗ trợ, có khả năng **flashback riêng một PDB** thay vì toàn CDB. Kỹ thuật này có thể cần Flashback Database, restore points, đủ flashback logs và điều kiện khởi tạo/cấu hình phù hợp.

Tuy nhiên **PDB Flashback không phải PDB PITR bằng RMAN**. Flashback phụ thuộc khả năng còn dữ liệu lịch sử trong flashback infrastructure và các giới hạn tính năng; PITR thường dựa vào backup cùng redo và có quy trình khác. Mỗi cơ chế có điều kiện về PDB state, undo và restore point; không nên coi chúng hoán đổi được.

### 6.3 CDB Flashback

Flashback ở phạm vi toàn CDB có thể tác động nhiều container. Nó phục vụ một loại sự cố khác với việc chỉ muốn quay lại bảng của một PDB.

| Nhu cầu | Cơ chế cần cân nhắc | Câu hỏi kiểm tra |
|---|---|---|
| Xem phiên bản cũ của vài dòng | Flashback Query | Undo có còn phiên bản cần đọc không? |
| Quay lại một đối tượng trong PDB | Flashback Table hoặc phục hồi logic | Bảng và quyền có đáp ứng điều kiện không? |
| Quay lại riêng PDB | PDB Flashback hoặc PDB PITR | Release, undo mode, restore point, backup/redo, trạng thái PDB thế nào? |
| Quay lại toàn database | CDB Flashback hoặc CDB PITR | Các PDB khác có chấp nhận mất thay đổi sau mốc đó không? |

**Không dùng Flashback làm cơ chế backup duy nhất**: mất storage chứa dữ liệu và flashback logs có thể khiến cả dữ liệu lẫn lịch sử cần flashback không còn. Backup độc lập với cấu trúc lưu trữ và kiểm thử restore vẫn cần thiết.

## 7. Unplug/plug, clone, snapshot và backup khác nhau ra sao?

Multitenant cung cấp thao tác tạo PDB mới, clone, relocate, unplug/plug để triển khai và chuyển dữ liệu. Chúng có thể xuất hiện trong phương án bảo trì hoặc di chuyển, nhưng không tự động thay thế backup/recovery.

### 7.1 Unplug và plug

Một PDB có thể được **unplug** với metadata manifest và các file dữ liệu cần thiết rồi **plug** vào CDB đích theo quy trình hỗ trợ. Các giới hạn về phiên bản/charset/option, trạng thái file, keystore, plug-in violations và tên/định danh PDB cần kiểm tra.

Một manifest XML không chứa toàn bộ dữ liệu bảng. Chỉ giữ file XML mà mất datafile không tạo ra backup đầy đủ. Ngược lại, giữ datafile mà không có thông tin cần thiết để khôi phục/plug hợp lệ cũng chưa đảm bảo khả năng phục hồi theo yêu cầu.

### 7.2 Clone/refreshable PDB

Clone có thể tạo bản sao phục vụ kiểm thử, phát triển hoặc trường hợp dùng được hỗ trợ. Refreshable clone có cơ chế làm mới từ nguồn theo những điều kiện nhất định. Nhưng:

- Bản clone có thể chứa cùng dữ liệu sai nếu lỗi đã được đồng bộ.
- Clone có thể phụ thuộc storage hoặc nguồn theo từng phương án.
- Có thể cần dừng refresh/điều khiển trạng thái và quyền hoạt động.
- Việc có clone **không chứng minh** chuỗi backup + archived redo có thể recover đến một SCN mục tiêu.

Clone có thể bổ sung khả năng vận hành, nhưng không thay thế việc thiết kế RPO/RTO và DR.

### 7.3 Storage snapshot

Snapshot ở tầng lưu trữ có thể hữu ích nếu có cơ chế bảo đảm database consistency và khả năng phối hợp với Oracle phù hợp. Một snapshot file system chụp tùy ý khi database đang ghi không tự động là bản RMAN backup hợp lệ. Phải hiểu khả năng khôi phục từ snapshot, redo và tính nhất quán của các thành phần CDB chung.

## 8. Ranh giới bảo trì: thao tác nào ảnh hưởng PDB, thao tác nào ảnh hưởng CDB?

Các hoạt động bảo trì gồm thay đổi schema, thu thập thống kê, cấp quyền, quản lý tablespace, cấu hình tham số, vá phần mềm, nâng cấp và chuyển PDB giữa các hệ thống. Mỗi loại có phạm vi tác động riêng.

### 8.1 Bảo trì schema và dữ liệu thuộc PDB

Trong một PDB, người quản trị có quyền phù hợp có thể làm việc với:

- Tạo/sửa bảng, index, view, procedure trong schema thuộc PDB.
- Thu thập thống kê optimizer cho bảng/schema của PDB.
- Quản lý tablespace/datafile thuộc PDB theo điều kiện/quyền được hỗ trợ.
- Quản lý local user/role và quota, profile phù hợp.
- Bảo trì dữ liệu ứng dụng, phân vùng, index hoặc job theo phạm vi PDB.

Ví dụ khi đã kết nối đúng dịch vụ PDB bằng tài khoản có quyền:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container,
       USER AS current_user
FROM dual;
~~~

Sau đó có thể chạy thao tác DDL/DML **trong đúng PDB** theo quy trình được cấp quyền. Một bảng tên `ORDERS` ở `PDB_SALES` khác bảng cùng tên ở `PDB_HR`; thay đổi đối tượng local của Sales thường không thay đổi bảng local của HR.

Nhưng nếu nhiều ứng dụng chung CPU/I/O/memory/storage trên CDB, một thao tác dữ liệu nặng của Sales vẫn có thể làm HR chậm. **Cô lập namespace không đồng nghĩa cô lập tài nguyên vật lý tuyệt đối.**

### 8.2 Bảo trì ở CDB root / instance

Nhiều nhiệm vụ phải được quản lý ở root hoặc cấp instance:

- Quản lý online redo, archived redo và cấu hình RMAN liên quan toàn CDB.
- Bảo vệ/khôi phục control file, SPFILE và các cấu hình nền tảng.
- Một số tham số `ALTER SYSTEM` ảnh hưởng instance/CDB, không chỉ PDB.
- Tác vụ software patching/upgrade của Oracle Database Home và thành phần chung.
- Điều khiển instance, listener, RAC, Data Guard/standby tùy kiến trúc.
- Quản lý common users/roles và quyền có phạm vi nhiều container theo chính sách.
- Chính sách giám sát/cấp phát tài nguyên cấp CDB, ví dụ giới hạn tài nguyên giữa PDB.

Đó là lý do DBA của từng PDB không thể tự vận hành một PDB như một máy chủ database độc lập hoàn toàn.

### 8.3 Một số tham số có thể có phạm vi PDB

Oracle cho phép một số tham số được đặt ở PDB và giữ lại theo cơ chế hỗ trợ; các tham số khác chỉ có hiệu lực ở root hoặc cấp instance. Khi làm việc với `ALTER SYSTEM`, có thể tồn tại ngữ nghĩa `CONTAINER=CURRENT` / `CONTAINER=ALL` đối với những đối tượng/cấu hình phù hợp, nhưng **không áp dụng thống nhất cho mọi parameter**.

Không nên tự suy rằng “đã ở PDB thì mọi `ALTER SYSTEM` chỉ đổi PDB này”. Phải kiểm tra metadata của tham số, phiên bản và quyền, cũng như ảnh hưởng lên các container khác.

## 9. Vá lỗi và nâng cấp: tại sao PDB không hoàn toàn tự chủ?

### 9.1 Patching phần mềm có phạm vi instance/CDB

Oracle Database sử dụng phần mềm executable và thư viện của Oracle Home (hoặc hạ tầng tương ứng), thường được nhiều PDB trong cùng CDB chia sẻ. Một **Release Update (RU)** hoặc bản vá nhị phân có thể yêu cầu thao tác trên Oracle Home/instance và ảnh hưởng tính sẵn sàng của tất cả PDB sử dụng nó.

Trong RAC, có thể có phương án rolling patch cho những bản vá/kiến trúc đủ điều kiện; không mặc định mọi RU đều rolling được hoặc không gây ngừng dịch vụ. Cần đọc yêu cầu của bản vá và kế hoạch gián đoạn/khôi phục thực tế.

### 9.2 Datapatch và thay đổi SQL bên trong CDB/PDB

Sau khi cập nhật binary, một số thay đổi SQL dictionary/metadata cần áp dụng bằng công cụ thích hợp, ví dụ `datapatch`, theo hướng dẫn patch tương ứng. Trong Multitenant, trạng thái root và các PDB cần được xử lý phù hợp; có thể cần **mở các PDB đúng trạng thái** để script patch áp dụng được.

Không nên tuyên bố “patch xong CDB$ROOT thì tất cả PDB đã cập nhật đầy đủ” mà bỏ qua trạng thái SQL patch của các PDB. Khi một PDB không mở/không được áp dụng patch vào đúng thời điểm, có thể phải hoàn tất bước còn thiếu theo quy trình hỗ trợ.

### 9.3 Version compatibility khi plug/clone PDB

Di chuyển PDB giữa CDB hoặc từ môi trường backup/clone sang đích phải xét:

- Phiên bản Oracle và hướng nâng cấp/hạ cấp được hỗ trợ.
- Character set và các yêu cầu tương thích khác.
- Tùy chọn/component sử dụng trong PDB so với CDB đích.
- Kiểu endian/storage/đường dẫn và khả năng chuyển đổi file cần thiết.
- TDE keys và keystore để mở dữ liệu mã hóa.
- Plug-in violations, SQL patch level và các bước hậu triển khai.

PDB “đã có datafile” chưa chắc được phép mở trong CDB đích. Kiểm tra trước thao tác và giữ nguyên bản sao phục hồi là một phần của kế hoạch bảo trì.

## 10. Backup và bảo trì metadata/cấu hình bên ngoài PDB

Một lỗi phổ biến khi xây dựng kế hoạch disaster recovery là sao lưu hết datafile nhưng thiếu những thành phần cần thiết để đưa dịch vụ trở lại.

| Thành phần ngoài dữ liệu bảng PDB | Vì sao cần bảo vệ? |
|---|---|
| **Control file, SPFILE** | Xây dựng lại cấu trúc và cấu hình database/instance |
| **Archived redo logs** | Complete recovery/PITR đến điểm mong muốn |
| **RMAN recovery catalog/repository info** | Quản lý và tra cứu lịch sử backup, trong cấu hình sử dụng catalog; cần có phương án nếu mất catalog |
| **TDE wallet/keystore và các khóa cần thiết** | Không có khóa phù hợp thì backup của dữ liệu mã hóa có thể không đọc được |
| **Oracle Net/listener/services** | Đưa ứng dụng kết nối trở lại đúng PDB sau recovery |
| **ASM/storage/network config** | Định vị datafile/backup và cấp quyền truy cập |
| **Scripts, job scheduler ngoài database, secret/config ứng dụng** | Khôi phục toàn bộ dịch vụ nghiệp vụ, không chỉ bytes của bảng |
| **External tables, directory objects, BFILE, file đính kèm ngoài DB** | Đối tượng Oracle có thể tham chiếu tệp ngoài datafile; backup database không nhất thiết bảo vệ các tệp đó |
| **Tài liệu runbook và định danh môi trường** | Tránh restore nhầm CDB/DBID/tenant, thiếu tham số hoặc thao tác sai scope |

### 10.1 TDE: phải sao lưu cả khả năng giải mã

Nếu một PDB sử dụng **Transparent Data Encryption (TDE)**, datafile backup được mã hóa/được bảo vệ theo cơ chế liên quan. Restore file mà mất keystore hoặc khóa thích hợp có thể khiến PDB không mở hoặc không đọc được dữ liệu cần thiết. Với Multitenant, tồn tại các mô hình keystore như **united** và **isolated** tùy phiên bản/cấu hình.

Chính sách backup phải bảo vệ keystore/keys ở nơi an toàn, quản lý thay đổi mật khẩu/rotation và thử restore để xác nhận có thể truy cập dữ liệu mã hóa. Không để bản sao khóa trong cùng điểm lỗi duy nhất với hệ thống chính, và không đưa secret thực vào log/chỗ công khai.

### 10.2 Dữ liệu ngoài database

Ví dụ bảng trong `PDB_SALES` có cột lưu đường dẫn file chứng từ trên object storage. RMAN backup bảng chỉ bảo vệ **giá trị đường dẫn trong database**, không tự sao lưu nội dung file bên ngoài. Nếu phục hồi riêng PDB về thời điểm 10:00 nhưng object storage vẫn có tệp từ 10:30, cần quy trình đối soát và phục hồi file tương ứng.

Đây là một trong những lý do backup/recovery của PDB phải gắn với **ranh giới nghiệp vụ và hệ thống bên ngoài**, không chỉ ranh giới file Oracle.

## 11. SQL đọc trạng thái CDB/PDB trước khi thao tác

Các truy vấn dưới đây có tính chất **quan sát**. Một số view cần quyền quản trị hoặc quyền truy cập dynamic performance views; không tự nâng quyền ứng dụng thành `SYSDBA` chỉ để xem.

### 11.1 Xác minh đang ở container nào

~~~sql
SHOW CON_NAME
~~~

Trong SQL*Plus/SQLcl, `SHOW CON_NAME` hiển thị container của session. Đây là lệnh của client; trong ứng dụng hoặc công cụ SQL khác có thể dùng:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
       USER AS session_user
FROM dual;
~~~

Đừng dựa duy nhất vào tên schema: cùng tên user local có thể tồn tại ở các PDB khác nhau, và kết nối qua service khác sẽ dẫn tới dữ liệu khác.

### 11.2 Xem CDB, role và chế độ archived redo

Trong ngữ cảnh đủ quyền:

~~~sql
SELECT name,
       dbid,
       cdb,
       database_role,
       open_mode,
       log_mode
FROM v$database;
~~~

Thông tin `CDB` và `DBID` giúp định danh database, `DATABASE_ROLE` cho biết primary/standby trong môi trường có Data Guard, và `LOG_MODE` giúp nhận diện tình trạng ARCHIVELOG/NOARCHIVELOG. Chiến lược backup online và khả năng PITR có yêu cầu phù hợp với chế độ redo; không mặc định mọi CDB đang cấu hình ARCHIVELOG.

### 11.3 Liệt kê các PDB và trạng thái mở

Từ root với quyền đủ:

~~~sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
~~~

Hoặc quan sát các container:

~~~sql
SELECT con_id, name, open_mode
FROM v$containers
ORDER BY con_id;
~~~

Một PDB ở chế độ `MOUNTED`, `READ ONLY` hoặc `READ WRITE` có khả năng phục vụ ứng dụng/bảo trì khác nhau. Khi chạy backup, patch hoặc recovery, trạng thái container và quyền truy cập phải phù hợp với quy trình từng lệnh.

### 11.4 Liên kết datafile với container

Trong CDB root:

~~~sql
SELECT con_id, file#, name, status
FROM v$datafile
ORDER BY con_id, file#;
~~~

`CON_ID` giúp phân biệt file thuộc root, seed hoặc PDB tương ứng. Việc mapping này quan trọng trước khi restore chọn lọc: **sai datafile hoặc sai PDB có thể biến lỗi nhỏ thành sự cố diện rộng**.

### 11.5 Kiểm tra metadata backup bằng RMAN

Ở một kết nối RMAN có quyền và phạm vi CDB phù hợp:

~~~rman
SHOW ALL;
REPORT SCHEMA;
LIST BACKUP SUMMARY;
~~~

Các câu trên giúp xem cấu hình backup, cấu trúc dữ liệu và lịch sử backup được repository nhận biết. Chúng **không đảm bảo** từng backup vẫn đọc được từ storage hoặc đã chứa mọi archived redo cần thiết cho RPO. Phải có chính sách kiểm chứng vật lý và **thử restore**.

Một bước xác minh có thể dùng khả năng RMAN `VALIDATE`/`RESTORE ... VALIDATE` theo cú pháp và phạm vi hỗ trợ của release, nhưng validation cũng phát sinh I/O và không chứng minh toàn bộ quy trình startup/ứng dụng sau recovery sẽ thành công.

## 12. Minh họa cách phân biệt lệnh RMAN theo scope

Phần này nêu **mẫu cú pháp minh họa**, không phải runbook chạy thẳng. Một câu `RESTORE` hoặc `RECOVER` có thể thay đổi trạng thái dữ liệu nếu thực thi trên môi trường thật, vì vậy chỉ DBA đủ quyền dùng trong kế hoạch được kiểm chứng.

### 12.1 Mẫu backup từ root

~~~rman
-- RMAN target là CDB root, sau khi xác minh DBID và đúng môi trường.

-- Backup dữ liệu của toàn CDB theo cấu hình RMAN.
BACKUP DATABASE;

-- Backup dữ liệu của một PDB.
BACKUP PLUGGABLE DATABASE pdb_sales;

-- Backup archived redo ở phạm vi CDB theo chính sách phù hợp.
BACKUP ARCHIVELOG ALL;
~~~

Đây là các ví dụ **độc lập để thấy sự khác nhau về phạm vi**; không phải lời khuyên chạy cả ba liên tiếp theo đúng thứ tự cho mọi hệ thống. Việc thực thi production cần chính sách backup đầy đủ, chẳng hạn kết hợp full/incremental, retention, deduplication, backup window và offsite copy.

### 12.2 Mẫu restore/recover whole-PDB ở mức khái niệm

~~~text
Xác định PDB và các datafile hỏng
           |
           v
Kiểm tra backup + redo + dependency chung
           |
           v
Cô lập ứng dụng và đưa PDB vào trạng thái yêu cầu
           |
           v
RMAN RESTORE PLUGGABLE DATABASE <pdb>
           |
           v
RMAN RECOVER PLUGGABLE DATABASE <pdb>
           |
           v
Mở PDB theo quy trình được hỗ trợ
           |
           v
Kiểm tra consistency + dữ liệu + dịch vụ
~~~

Cú pháp cụ thể và trạng thái open/close phụ thuộc kiểu sự cố, release, restore method và cấu hình; phải theo hướng dẫn recovery hiện hành của Oracle cho môi trường thật. Với PDB PITR, luồng khác vì có **UNTIL SCN/TIME, auxiliary context, phục hồi chưa hoàn toàn và các bước hậu PITR**.

### 12.3 Vì sao không nên đưa ví dụ ALTER PLUGGABLE DATABASE CLOSE vào bài lab chung?

`ALTER PLUGGABLE DATABASE ... CLOSE` làm gián đoạn kết nối/dịch vụ liên quan. Trong một CDB có nhiều PDB, người mới học dễ nhầm container khi thử lệnh. Vì vậy phần thực hành nên dùng **truy vấn kiểm tra và mô phỏng runbook trên giấy hoặc bản sao lab**, chỉ chạy lệnh thay đổi trạng thái trong môi trường đã được cấp quyền và có kế hoạch.

## 13. Bảo trì theo lịch và quan hệ giữa CDB/PDB

Hệ thống có nhiều PDB thường phục vụ những ứng dụng với khung bảo trì khác nhau. Ví dụ:

| Công việc | Phạm vi chủ yếu | Có thể ảnh hưởng PDB khác không? |
|---|---|---|
| Thu thập statistics cho bảng của Sales | PDB_SALES | Có thể cạnh tranh CPU/I/O nhưng không đổi schema HR |
| Rebuild một index của Sales | PDB_SALES | Có thể dùng TEMP/I/O chung, ảnh hưởng độ trễ tải khác |
| Thay quota local user của Sales | PDB_SALES | Thường local, trừ những phụ thuộc/chính sách chung |
| Đóng/mở PDB_SALES để bảo trì | PDB_SALES | Ứng dụng Sales gián đoạn; PDB khác thường có thể tiếp tục nếu CDB ổn định |
| Backup riêng PDB_SALES | PDB_SALES về phạm vi dữ liệu | Có thể tạo I/O/CPU chung và cần archived redo cấp CDB |
| Quản lý archived redo/backup retention | CDB | Ảnh hưởng khả năng phục hồi nhiều PDB |
| Thay control file/SPFILE, sửa instance-level config | CDB/instance | Có thể ảnh hưởng toàn CDB |
| Patching Oracle binary / restart instance | CDB/instance | Thường liên quan nhiều/tất cả PDB của instance |
| PDB PITR của Sales | PDB_SALES | HR không bị đưa về cùng mốc, nhưng cần kiểm tra tích hợp chéo |
| Whole-CDB restore/PITR | CDB | Có thể ảnh hưởng tất cả PDB thuộc phạm vi phục hồi |

Trong một CDB có nhiều tenant/ứng dụng, đội vận hành nên duy trì lịch bảo trì tách biệt cho phần có thể tách và lịch toàn hệ thống cho phần dùng chung. **Lịch riêng PDB không thể xóa bỏ nhu cầu thống nhất cửa sổ bảo trì của CDB**.

### 13.1 Giới hạn tài nguyên để giảm ảnh hưởng chéo

Một PDB báo cáo có thể sử dụng nhiều CPU, I/O, PGA hoặc TEMP, khiến PDB giao dịch khác chậm dù không chia sẻ schema. Oracle cung cấp các cơ chế quản lý tài nguyên theo CDB/PDB tùy release/edition, và nền tảng triển khai có thể cung cấp chính sách quota/resource riêng.

Khi bảo trì nặng:

- Chọn thời điểm chạy thích hợp theo SLA của các PDB.
- Giới hạn đồng thời hoặc workload nếu có chính sách hỗ trợ.
- Theo dõi tổng tài nguyên CDB, không chỉ metric của PDB đang được bảo trì.
- Xác nhận không làm tăng RTO của tenant khác do chiếm băng thông backup/storage.

## 14. Ranh giới bảo vệ khi dùng Data Guard, standby và DR

**RMAN backup** và **Data Guard/standby** giải quyết các nhu cầu có liên quan nhưng không giống nhau.

Với một CDB dùng physical standby theo cấu hình hỗ trợ, redo có thể được chuyển và áp dụng đến standby để phục vụ khả năng khôi phục/sẵn sàng ở site khác. Phạm vi standby thông thường gắn với **database/CDB**, nên phải xét toàn bộ container và cấu hình chung. Một số khả năng hoặc ngoại lệ PDB-level phụ thuộc release/tính năng, không nên tự giả định “Data Guard bảo vệ từng PDB như những primary/standby hoàn toàn riêng biệt”.

Ví dụ nếu `PDB_SALES` có batch xóa dữ liệu sai và sự thay đổi được gửi/applied sang standby, **standby cũng có thể chứa lỗi logic đó**. Một standby luôn mới không thay thế backup/PITR khi lỗi do người dùng hoặc ứng dụng. Ngược lại, backup PDB hằng ngày không tự tạo khả năng failover tức thì khi primary CDB bị mất.

| Mục tiêu | RMAN backup/recovery | Standby/DR |
|---|---|---|
| Phục hồi dữ liệu đã xóa nhầm từ quá khứ | Có thể dùng backup/PITR/khôi phục logic | Không chắc: lỗi logic có thể đã được replicate |
| Phục hồi khi mất storage CDB | Tùy thời gian restore/recover và backup/redo | Có thể hỗ trợ RTO/RPO tốt hơn nếu được thiết kế |
| Giữ điểm dữ liệu lịch sử lâu dài | Hữu ích với retention/backup chain | Standby đang đồng bộ thường không có mục tiêu chính là giữ lịch sử dài hạn |
| Chạy ứng dụng nhanh ở site dự phòng | Không phải tính năng chính của backup | Có thể là mục tiêu của DR architecture |
| Phục hồi đúng một PDB về mốc cũ | Các cơ chế PDB recovery được hỗ trợ | Cần xem tính năng cụ thể; không mặc nhiên tách mốc từng PDB |

Một chiến lược đáng tin cậy thường có **backup có thể phục hồi**, **redo/archivelog**, **DR nếu SLA yêu cầu**, và **kiểm thử tình huống mất dữ liệu logic lẫn mất hạ tầng**.

## 15. Kịch bản lỗi và cách chọn phạm vi

Giả sử CDB `PROD_CDB` chứa `PDB_SALES`, `PDB_HR` và `PDB_ANALYTICS`.

| Sự cố | Phạm vi điều tra đầu tiên | Phương án cần đánh giá |
|---|---|---|
| Ứng dụng Sales xóa nhầm 500 dòng | Bảng/schema trong `PDB_SALES` | Phục hồi logic/Flashback Query; nếu không đủ thì PDB PITR hoặc giải pháp có restore phụ |
| Datafile của Sales bị mất do storage lỗi | Datafile/tablespace thuộc Sales | RMAN restore/recover chọn lọc cho PDB/tablespace/datafile phù hợp |
| Sales hỏng phần lớn dữ liệu sau batch sai | `PDB_SALES` | PDB PITR; đối soát giao dịch sau mốc phục hồi |
| Hỏng control file hoặc root không mở được | Toàn CDB | Chiến lược CDB-level restore/recovery, metadata, redo, SPFILE |
| Mất archived redo cần cho recovery | CDB backup/redo chain | Đánh giá lại khả năng complete/PITR của các PDB; phục hồi bản archivelog hoặc chấp nhận mốc cũ hơn theo RPO |
| PDB backup có nhưng TDE key thất lạc | Keystore/keys liên quan | Khôi phục keys/keystore hợp lệ; backup datafile một mình có thể không dùng được |
| RU/datapatch chưa áp dụng ở một PDB | Software/SQL patch state trong CDB/PDB | Hoàn tất SQL patch theo quy trình phiên bản, kiểm tra plug-in violations |
| Chạy báo cáo khổng lồ ở Analytics làm Sales chậm | CPU/I/O/memory chung của CDB | Resource plan, scheduling, workload tuning, có thể phân tách hạ tầng |
| PDB clone chạy được nhưng mất toàn server | CDB/shared dependency và môi trường chứa clone | Không coi clone là backup toàn CDB; kiểm tra nơi lưu trữ độc lập và DR |

### 15.1 Phân tích chi tiết tình huống “Sales quay về hôm qua, HR giữ nguyên”

Tại 08:00, cả Sales và HR hoạt động bình thường. Đến 12:00, script lỗi làm thay đổi dữ liệu Sales; trong khi đó HR đã ghi 4 giờ giao dịch hợp lệ. Ban vận hành muốn Sales quay lại lúc 11:59 và giữ HR ở hiện tại.

**Mục tiêu logic:** chỉ Sales cần quay về điểm cũ; HR phải giữ nguyên.

**Phương án cần cân nhắc:** tìm hiểu mức độ lỗi, ưu tiên khôi phục chọn lọc dữ liệu nếu chỉ vài hàng; nếu tổn thất rộng, đánh giá PDB PITR của Sales.

**Không phù hợp:** whole-CDB PITR về 11:59 nếu không có nhu cầu tương ứng ở HR, vì sẽ tác động tới các thay đổi hợp lệ của HR và Analytics.

**Cần chú ý:** nếu Sales phát sự kiện đến hệ thống thanh toán hoặc kho ngoài database từ 11:59 đến 12:00, các hệ thống đó có thể tiếp tục giữ trạng thái mới. Sau PITR cần đối soát và bù giao dịch, không chỉ kiểm tra SQL trong Sales.

### 15.2 Nếu sự cố là mất toàn máy chủ?

Khi mất hạ tầng chạy CDB, một bản backup riêng `PDB_SALES` không giải quyết đầy đủ việc dựng lại `PROD_CDB` hoặc các dependency khác. Cần backup và thông tin phục hồi root, seed, control file/SPFILE, redo, keystore, cấu hình network/storage và phương án phục hồi các PDB khác.

Lựa chọn điểm phục hồi cho toàn CDB phải được thống nhất với nghiệp vụ và tính nhất quán giữa ứng dụng; không thể chỉ nhìn nhu cầu của PDB lớn nhất.

## 16. Thiết kế runbook backup/recovery có thể kiểm tra

Một runbook nên có ít nhất những thông tin sau:

| Nhóm thông tin | Nội dung cần ghi rõ |
|---|---|
| **Định danh mục tiêu** | CDB name, DBID/DB_UNIQUE_NAME, tên PDB, service, primary/standby, môi trường |
| **Phạm vi** | Backup/recover toàn CDB, một PDB, một tablespace hay vài datafile |
| **Mục tiêu nghiệp vụ** | RPO/RTO, thời điểm SCN/TIME, yêu cầu dữ liệu liên hệ ngoài DB |
| **Nguồn backup** | Loại full/incremental, vị trí, retention, offsite, khả năng đọc, catalogue |
| **Phần phụ thuộc** | Archived redo, control file, SPFILE, root, seed, keystore/TDE, file ngoài DB |
| **Trạng thái/điều kiện** | ARCHIVELOG, undo mode, PDB open mode, storage, version/edition, permission |
| **Thao tác** | Ai thực thi, lệnh theo release, thứ tự, checkpoint, cách dừng nếu lỗi |
| **Tác động** | Container nào mất dịch vụ, phạm vi quiesce/close, thời gian ước lượng đã đo |
| **Phục hồi khi lỗi giữa chừng** | Phương án quay về từ backup/restore point, tình trạng partial recovery |
| **Xác minh** | Open state, dữ liệu, ứng dụng, số giao dịch, TDE, job, replication, health check |
| **Lịch thử nghiệm** | Ngày thử restore gần nhất, kết quả, điểm yếu và người chịu trách nhiệm |

### 16.1 Kiểm thử restore là phép thử có giá trị

Chỉ báo “RMAN BACKUP completed” cho biết job đã chạy xong theo định nghĩa của công cụ, không chứng minh toàn bộ dịch vụ có thể phục hồi. Một buổi diễn tập trên môi trường cô lập nên thử:

1. Tìm đúng backup theo CDB/PDB và mốc RPO mục tiêu.
2. Dựng môi trường có đủ storage, phiên bản và keystore.
3. Restore/recover với archived redo cần thiết.
4. Mở database/PDB, kiểm tra các đối tượng và số liệu mẫu.
5. Kiểm tra kết nối ứng dụng, job và dữ liệu ngoài database.
6. Ghi nhận RTO thực đo cùng các lỗi gặp phải.

Nên thử **hai nhóm khác nhau**: phục hồi một PDB trong khi PDB khác cần giữ nguyên, và phục hồi toàn CDB khi mất hạ tầng. Chỉ thử một nhóm không chứng minh nhóm còn lại hoạt động.

### 16.2 Giữ lịch backup phù hợp lifecycle PDB

Khi tạo PDB mới, clone, plug hoặc drop PDB, chính sách backup phải theo kịp:

- PDB mới cần được đưa vào kiểm kê backup và RPO/RTO.
- PDB được plug có thể có trạng thái incarnation, metadata và các yêu cầu khôi phục riêng cần rà soát.
- PDB bị drop/unplug không đồng nghĩa mọi backup cũ được giữ hoặc xóa tự động đúng ý nghiệp vụ.
- Retention/archivelog deletion phải xét khả năng recovery của mọi PDB được bảo vệ, không chỉ một tenant.
- Người quản trị cần biết những bản sao nào vẫn chứa dữ liệu nhạy cảm sau khi tenant bị xóa ở hệ chính.

## 17. Bài thực hành quan sát an toàn

**Yêu cầu:** một CDB lab có ít nhất hai PDB và tài khoản được cấp quyền chỉ đọc những dynamic views cần thiết. Không thực hiện restore, recover, close, drop, flashback hoặc thay đổi tham số trên database đang có người sử dụng.

### Bước 1 — Nhận diện container

Chạy trong SQL Worksheet hoặc SQL*Plus:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name
FROM dual;
~~~

Ghi lại bạn đang ở root hay một PDB.

### Bước 2 — Nếu có quyền ở root, xem danh sách PDB

~~~sql
SELECT con_id, name, open_mode
FROM v$pdbs
ORDER BY con_id;
~~~

So sánh `PDB$SEED` với các PDB ứng dụng, trạng thái mở và định danh `CON_ID`.

### Bước 3 — Quan sát phạm vi file

~~~sql
SELECT con_id, file#, name
FROM v$datafile
ORDER BY con_id, file#;
~~~

Nhận diện datafile của root và datafile của các PDB. Nếu đang chạy ở PDB hoặc không được cấp quyền, tập dòng nhìn thấy có thể khác; không tự kết luận datafile không tồn tại chỉ vì không có quyền xem.

### Bước 4 — Phân loại các sự cố

Với mỗi tình huống, viết ra **thành phần bị lỗi**, **phạm vi backup cần có**, **phạm vi restore/recover phù hợp**, **PDB khác có bị ảnh hưởng không**, và **thành phần ngoài database cần bảo vệ**:

1. Mất datafile của một tablespace trong Sales.
2. Xóa nhầm dữ liệu Sales lúc 10:15.
3. Mất control file.
4. Mất TDE keystore liên quan đến dữ liệu mã hóa của HR.
5. Cài RU và áp dụng SQL patch nhưng một PDB đang không mở.
6. Bản clone của Analytics đã nhận lỗi dữ liệu từ nguồn.

### Bước 5 — Viết một runbook tối giản trên giấy

Chọn sự cố (2). Viết kế hoạch xác minh điểm phục hồi 10:14, kiểm tra chuỗi backup và redo, xác nhận điều kiện PDB PITR, bảo vệ giao dịch hợp lệ sau mốc và kiểm tra tích hợp sau mở PDB. So sánh với phương án whole-CDB PITR và giải thích vì sao phạm vi tác động khác nhau.

## 18. Những ngộ nhận cần tránh

**“Mỗi PDB có một bộ redo riêng nên backup PDB không cần quan tâm archived redo CDB.”** Không đúng. Redo infrastructure là thành phần chung quan trọng, và khả năng recovery cần redo tương ứng.

**“BACKUP PLUGGABLE DATABASE đủ để phục hồi khi mất cả CDB root và control file.”** Không đúng. Backup PDB chọn lọc không thay thế chiến lược bảo vệ hạ tầng toàn CDB.

**“PDB PITR chỉ hoàn tác những dòng sai.”** Không đúng. PITR đưa dữ liệu trong phạm vi được chọn về một điểm trong quá khứ; thay đổi hợp lệ sau điểm đó cũng cần được xử lý.

**“Muốn phục hồi một PDB thì phải phục hồi tất cả PDB về cùng thời điểm.”** Không đúng trong các môi trường có khả năng PDB-level recovery phù hợp. Nhưng không được suy rằng mọi release/cấu hình hỗ trợ một quy trình giống nhau.

**“Clone hoặc standby luôn thay thế backup.”** Không đúng. Lỗi logic có thể được sao chép; clone có thể có phụ thuộc nguồn; DR và lịch sử phục hồi là các mục tiêu khác nhau.

**“PDB bảo trì độc lập nên vá Oracle Home sẽ không ảnh hưởng PDB khác.”** Không đúng. Phần mềm và instance dùng chung khiến nhiều tác vụ patch/restart có phạm vi CDB hoặc hạ tầng.

**“Backup thành công là đã đạt RPO/RTO.”** Không đúng. Phải xét archived redo, offsite dependency, keystore, thời gian restore/recover và diễn tập.

**“Kết nối vào đúng schema là đủ để xác định đang ở đúng PDB.”** Chưa đủ. Cần xác minh container/service, CDB identity và role, đặc biệt khi nhiều PDB có schema cùng tên.

## 19. Ghi nhớ

Trong Oracle Multitenant, **PDB là ranh giới quản lý dữ liệu ứng dụng quan trọng**, cho phép nhiều tác vụ backup, restore, recovery và bảo trì được thực hiện có chọn lọc. Tuy nhiên, **CDB vẫn là ranh giới của nhiều cấu phần vật lý và vận hành dùng chung**, như control file, redo, instance, cấu hình nền tảng và phần mềm. Vì vậy, một kế hoạch chỉ bảo vệ datafile của từng PDB mà bỏ qua hạ tầng chung sẽ không đủ cho sự cố toàn CDB.

Khi gặp một yêu cầu phục hồi, hãy lần lượt xác định: **sự cố nằm ở đối tượng, PDB hay CDB; cần giữ dữ liệu đến thời điểm nào; backup và redo có đủ không; undo mode/version có hỗ trợ phương án không; PDB nào khác sẽ bị tác động; và ứng dụng bên ngoài cần đối soát điều gì**. Câu trả lời cho những câu hỏi đó mới quyết định lựa chọn khôi phục logic, PDB PITR, whole-PDB recovery hay whole-CDB recovery.

Với bảo trì cũng áp dụng cùng nguyên tắc: quản lý schema, statistics hoặc tablespace có thể được khoanh vùng ở PDB, trong khi patching, control file, redo, cấu hình instance và bảo vệ khóa mã hóa cần được thiết kế theo quan hệ phụ thuộc chung của CDB. **Ranh giới đúng là ranh giới đã được kiểm chứng bằng runbook và diễn tập recovery**, chứ không chỉ là tên container trong câu SQL.
