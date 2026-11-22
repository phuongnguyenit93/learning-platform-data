# Phục hồi CDB/PDB và kiểm tra điều kiện của bản Oracle

## 1. Kiến trúc multitenant và phạm vi phục hồi

Oracle Multitenant tổ chức database theo mô hình **container database (CDB)**. Một CDB chứa container gốc `CDB$ROOT`, pluggable database mẫu `PDB$SEED` và một hoặc nhiều PDB phục vụ ứng dụng.

- `CDB$ROOT` lưu metadata và các thành phần dùng chung để quản lý CDB.
- `PDB$SEED` là PDB mẫu chỉ đọc, được Oracle dùng làm khuôn để tạo PDB mới.
- Mỗi PDB là một container có data dictionary và dữ liệu ứng dụng riêng, được quản lý bên trong CDB.

Phục hồi trong môi trường multitenant cần xác định rõ phạm vi hỏng:

| Phạm vi | Mục tiêu phục hồi | Ảnh hưởng |
|---|---|---|
| Toàn CDB | Khôi phục root, seed và các PDB thuộc CDB về trạng thái nhất quán | Có thể ảnh hưởng tất cả PDB và dịch vụ trên CDB |
| Một PDB | Khôi phục dữ liệu của PDB được chọn | Các PDB khác thường tiếp tục hoạt động, tùy loại thao tác và điều kiện phục hồi |
| Một tablespace/datafile trong PDB | Khôi phục một phần dữ liệu của PDB | Phạm vi nhỏ hơn, nhưng cần giữ nhất quán với phần còn lại của PDB |
| Control file/SPFILE | Khôi phục metadata điều khiển và cấu hình instance | Có thể cần mount/restart và thực hiện lại các bước restore/recover |

Không nên bắt đầu bằng lệnh `RESTORE DATABASE` khi chỉ một PDB bị lỗi. Phục hồi toàn CDB có phạm vi tác động lớn hơn nhiều so với phục hồi một PDB. Trước tiên phải xác định container, datafile, thời điểm lỗi và mục tiêu nghiệp vụ cần khôi phục.

## 2. Kiểm tra phiên bản và điều kiện trước khi phục hồi

### 2.1. Xác định release Oracle đang chạy

Kết nối database và xem thông tin phiên bản:

```sql
SELECT banner
FROM v$version
ORDER BY banner;

SELECT instance_name,
       version,
       status,
       database_status
FROM v$instance;
```

`V$VERSION` hiển thị phiên bản và thành phần Oracle; `V$INSTANCE` cho biết phiên bản instance cùng trạng thái hiện tại. Khi lập kế hoạch restore sang máy chủ khác hoặc sau nâng cấp, cần ghi lại release, Release Update (RU), platform và Oracle Home đang sử dụng.

Ở cấp hệ điều hành, DBA có thể kiểm tra inventory patch của Oracle Home bằng `opatch lsinventory`. Sau khi cài patch có phần SQL, cần kiểm tra quá trình datapatch và lịch sử trong database:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Oracle Home binary patch và SQL patch registry là hai thông tin khác nhau. Một Oracle Home có thể đã được cập nhật binary nhưng phần SQL patch chưa được áp dụng thành công. Trước khi restore/upgrade hoặc chẩn đoán lỗi dictionary, cần đối chiếu cả hai.

### 2.2. Xác định database có phải CDB không

```sql
SELECT name,
       dbid,
       cdb,
       open_mode,
       log_mode,
       database_role
FROM v$database;
```

`CDB='YES'` cho biết database đang dùng kiến trúc container. Nếu là non-CDB, các lệnh và quy trình phục hồi PDB không áp dụng. Không được giả định một database là CDB chỉ vì release hỗ trợ multitenant.

Liệt kê container và trạng thái PDB:

```sql
SHOW CON_NAME;

SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$containers
ORDER BY con_id;

SELECT name,
       open_mode,
       restricted,
       recovery_status
FROM v$pdbs
ORDER BY con_id;
```

`SHOW CON_NAME` cho biết container hiện tại của session. Các truy vấn quản trị toàn CDB nên được thực hiện từ `CDB$ROOT` với quyền phù hợp; không kết nối nhầm vào PDB rồi chạy lệnh RMAN cho toàn database.

### 2.3. Kiểm tra COMPATIBLE

Tham số `COMPATIBLE` xác định mức tương thích định dạng và hành vi database được phép sử dụng. Nó ảnh hưởng đến khả năng sử dụng một số tính năng và khả năng tương thích của file/database với release khác.

```sql
SELECT name, value, isdefault, issys_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

Không nên tự động đặt `COMPATIBLE` bằng số release của Oracle Home. Một database đã nâng cấp software có thể vẫn giữ `COMPATIBLE` ở mức cũ để bảo toàn khả năng tương thích trong giai đoạn chuyển đổi. Tăng giá trị này có thể làm thay đổi khả năng quay lại release cũ; cần đọc hướng dẫn upgrade của đúng phiên bản và có backup/rollback plan trước khi thay đổi.

`COMPATIBLE` không phải là phép kiểm tra duy nhất cho khả năng restore. Cần xem thêm phiên bản backup, control file, platform, endian, encryption wallet, cấu hình CDB/PDB và đường nâng cấp được Oracle hỗ trợ.

### 2.4. Kiểm tra trạng thái PDB và plug-in compatibility

Với PDB đã được plug vào CDB, xem các vấn đề compatibility:

```sql
SELECT name,
       cause,
       type,
       status,
       message,
       action
FROM pdb_plug_in_violations
ORDER BY name, time;
```

View này ghi nhận các vi phạm/cảnh báo khi plug PDB hoặc khi kiểm tra compatibility. Cần phân biệt lỗi phải xử lý với warning được chấp nhận theo tài liệu release. Không được xóa hoặc bỏ qua violation chỉ để PDB mở được.

Nếu đang chuẩn bị plug PDB từ XML manifest, có thể gọi `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` trước khi tạo PDB:

```sql
SET SERVEROUTPUT ON
DECLARE
  l_compatible BOOLEAN;
BEGIN
  l_compatible := DBMS_PDB.CHECK_PLUG_COMPATIBILITY(
    pdb_descr_file => '/u01/backup/pdb1.xml',
    pdb_name       => 'PDB1'
  );

  IF l_compatible THEN
    DBMS_OUTPUT.PUT_LINE('PDB is compatible');
  ELSE
    DBMS_OUTPUT.PUT_LINE('PDB has compatibility violations');
  END IF;
END;
/
```

Đây là kiểm tra plug-in compatibility, không phải kiểm tra tính toàn vẹn của RMAN backup. Sau khi plug, vẫn cần xem `PDB_PLUG_IN_VIOLATIONS` và xử lý các mục còn tồn tại.

### 2.5. Điều kiện theo release và platform

Trước khi phục hồi hoặc di chuyển CDB/PDB giữa máy chủ, cần xác nhận:

- Release nguồn và đích có nằm trong đường restore/upgrade/plug được Oracle hỗ trợ hay không.
- Backup được tạo bằng release nào, và RMAN target có tương thích với metadata/backup đó hay không.
- `COMPATIBLE` của database nguồn và đích có đáp ứng yêu cầu của tính năng/đường chuyển đổi hay không.
- Platform và endian có giống nhau không; nếu khác, có cần cross-platform conversion/transportable database hoặc tablespace hay không.
- CDB/PDB có cùng kiến trúc và trạng thái cần thiết cho thao tác dự kiến không.
- Oracle Home, RU, timezone file, character set, national character set và TDE wallet/key có sẵn, tương thích không.

Không suy luận rằng có thể restore trực tiếp backup của release mới vào Oracle Home cũ. Với thao tác khác phiên bản, hãy theo đúng hướng dẫn upgrade, downgrade, transport hoặc plug/unplug của từng release. Restore backup và nâng cấp database là hai quy trình khác nhau; không dùng một lệnh RMAN để thay thế quy trình upgrade được hỗ trợ.

## 3. Điều kiện cần có cho RMAN recovery

### 3.1. Backup và archived redo

Để phục hồi tới thời điểm sau backup, cần backup hợp lệ và các archived redo log bao phủ khoảng thời gian từ backup tới mục tiêu recovery. Nếu thiếu archived log ở giữa chuỗi, recovery có thể dừng trước mục tiêu.

Kiểm tra chế độ archive:

```sql
ARCHIVE LOG LIST;

SELECT log_mode
FROM v$database;
```

Database ở `ARCHIVELOG` mode cho phép lưu redo log đã đầy để phục hồi media recovery tới thời điểm phù hợp. Với `NOARCHIVELOG`, lựa chọn phục hồi bị giới hạn; thông thường phải dựa vào consistent backup và có thể mất thay đổi sau backup. Không nên dùng NOARCHIVELOG cho hệ thống cần khả năng phục hồi giao dịch đến thời điểm gần hiện tại.

Ví dụ tạo backup CDB:

```rman
CONFIGURE CONTROLFILE AUTOBACKUP ON;
BACKUP DATABASE PLUS ARCHIVELOG;
```

Khi kết nối RMAN tới CDB, backup `DATABASE` từ root bao gồm database trong phạm vi CDB theo cách RMAN định nghĩa, gồm root, seed và các PDB. Có thể tạo backup riêng cho PDB:

```rman
BACKUP PLUGGABLE DATABASE salespdb;
```

Backup riêng PDB không thay thế yêu cầu bảo vệ control file, SPFILE, archived redo và các thành phần chung cần cho recovery. Hãy duy trì cả chiến lược backup toàn CDB lẫn backup PDB nếu RPO/RTO yêu cầu phục hồi độc lập.

### 3.2. Control file, SPFILE và DBID

Control file lưu thông tin cấu trúc database, checkpoint, datafile, redo log và metadata backup. SPFILE lưu tham số khởi tạo instance. Nếu control file hoặc SPFILE bị mất, quy trình khôi phục cần có bản backup/autobackup tương ứng.

DBID là định danh database dùng trong một số tình huống khôi phục control file/SPFILE từ autobackup khi không còn control file để tra cứu metadata. DBA cần ghi lại DBID trong hồ sơ vận hành.

Ví dụ xem DBID:

```sql
SELECT name, dbid
FROM v$database;
```

### 3.3. Các điều kiện vận hành khác

Trước khi chạy restore/recover, xác nhận:

- Backup piece và archived log còn tồn tại, đọc được từ disk/tape/object storage.
- RMAN target kết nối đúng CDB và đúng DBID.
- Có đủ dung lượng cho datafile, control file, redo log, FRA và auxiliary destination nếu PITR cần auxiliary instance.
- Đường dẫn file, ASM disk group, channel, SBT library và credential lưu trữ được cấu hình đúng.
- Password file, TDE keystore/wallet và encryption keys sẵn sàng nếu database dùng mã hóa.
- Có quyền SYSDBA/SYSBACKUP và quyền hệ điều hành phù hợp để thực hiện thao tác.
- Có thời điểm mục tiêu rõ ràng: SCN, timestamp hoặc log sequence; tránh chọn thời điểm tùy ý.
- Có bản sao backup trước khi thay đổi cấu hình hoặc thực hiện thao tác có khả năng ghi đè dữ liệu.

## 4. Kiểm tra khả năng khôi phục trước khi restore

### 4.1. Kiểm tra repository và backup

Kết nối RMAN tới CDB target, thông thường với quyền `SYSBACKUP` hoặc quyền quản trị phù hợp, rồi kiểm tra:

```rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST ARCHIVELOG ALL;
REPORT SCHEMA;
```

Với một PDB cụ thể:

```rman
LIST BACKUP OF PLUGGABLE DATABASE salespdb;
```

Repository có thể nằm trong control file hoặc recovery catalog. Nếu dùng control file làm repository, metadata backup cũ có thể bị ghi đè theo thời gian; recovery catalog giúp lưu lịch sử dài hơn và quản lý nhiều database.

### 4.2. CROSSCHECK

`CROSSCHECK` đối chiếu metadata trong RMAN repository với sự tồn tại của backup piece/archived log trên storage:

```rman
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
```

Lệnh này cập nhật trạng thái repository thành `AVAILABLE` hoặc `EXPIRED` theo kết quả kiểm tra. Nó không tự xóa backup vật lý. Không chạy `DELETE EXPIRED` như một bước dọn dẹp máy móc nếu chưa xác nhận backup piece thực sự không còn cần thiết.

### 4.3. PREVIEW và VALIDATE

Xem RMAN dự định dùng backup nào:

```rman
RESTORE DATABASE PREVIEW;
```

Kiểm tra RMAN có thể đọc các backup piece cần thiết:

```rman
RESTORE DATABASE VALIDATE;
```

Đối với PDB:

```rman
RESTORE PLUGGABLE DATABASE salespdb PREVIEW;
RESTORE PLUGGABLE DATABASE salespdb VALIDATE;
```

`PREVIEW` hiển thị lựa chọn backup theo repository; `VALIDATE` đọc/kiểm tra backup được chọn mà không ghi đè datafile đích như thao tác restore thực tế. Ngoài ra, `VALIDATE DATABASE` có thể kiểm tra block database theo cú pháp RMAN được phiên bản hỗ trợ. Một lần validate thành công làm tăng độ tin cậy của backup nhưng không thay thế diễn tập restore đầy đủ.

## 5. Phục hồi toàn bộ CDB

### 5.1. Khi nào cần restore/recover toàn CDB?

Phục hồi toàn CDB được xem xét khi lỗi ảnh hưởng đến các thành phần chung hoặc nhiều PDB, chẳng hạn:

- Mất/hỏng control file hoặc datafile hệ thống quan trọng.
- Mất nhiều datafile thuộc nhiều container.
- Cần phục hồi CDB về một thời điểm trước thao tác gây hỏng trên phạm vi toàn database.
- Database bị mất hoặc hỏng trên host và cần dựng lại từ backup.

Nếu chỉ một PDB có lỗi logic hoặc mất datafile riêng, hãy đánh giá PDB recovery trước để tránh rollback các PDB khác.

### 5.2. Kết nối đúng container và mount database

Để restore/recover toàn CDB, RMAN phải kết nối tới CDB target; các thao tác khởi động/mount được điều khiển ở cấp instance/CDB. Nếu database đang mở và cần restore toàn bộ, DBA có thể phải shutdown và startup mount theo trạng thái lỗi và loại recovery.

```sql
SHOW CON_NAME;
-- Cần ở CDB$ROOT khi thực hiện tác vụ quản trị CDB.
```

Trong RMAN, luồng tổng quát khi control file còn dùng được:

```rman
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

Sau khi media recovery hoàn tất, mở database theo đúng loại recovery. Nếu đây là complete recovery với current control file, có thể mở bình thường; nếu incomplete recovery hoặc dùng backup control file, thường cần `OPEN RESETLOGS`. Không áp dụng `RESETLOGS` một cách máy móc; xác định trạng thái recovery và hướng dẫn Oracle cho kịch bản cụ thể.

### 5.3. Mất control file

Nếu control file bị mất và có control file autobackup, DBA có thể cần khởi động instance ở NOMOUNT, đặt DBID rồi restore control file:

```rman
SET DBID 1234567890;
STARTUP NOMOUNT;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

`1234567890` chỉ là giá trị minh họa; dùng DBID thật. Nếu SPFILE cũng bị mất, cần khởi động bằng PFILE tối thiểu hoặc khôi phục SPFILE theo đúng quy trình trước khi mount database. Sau recovery bằng backup control file, thường phải mở database với `RESETLOGS`:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

Sau khi mở, kiểm tra toàn bộ PDB, datafile, service, invalid objects và thực hiện backup mới theo chiến lược sau RESETLOGS. Việc mở RESETLOGS tạo database incarnation mới; quản lý backup cũ và archived logs phải theo đúng RMAN recovery catalog.

### 5.4. Incomplete recovery / CDB point-in-time recovery

Nếu cần đưa toàn CDB về trước một thời điểm, có thể dùng SCN hoặc thời gian mục tiêu:

```rman
RUN {
  SET UNTIL SCN 123456789;
  RESTORE DATABASE;
  RECOVER DATABASE;
}
```

Sau đó:

```sql
ALTER DATABASE OPEN RESETLOGS;
```

Thao tác này phục hồi toàn database tới mục tiêu, nên mọi PDB chịu ảnh hưởng theo cùng mốc recovery. Các giao dịch sau SCN mục tiêu bị loại khỏi trạng thái database sau phục hồi. Phải chọn mốc dựa trên bằng chứng sự cố và yêu cầu nghiệp vụ; kiểm tra timezone khi dùng timestamp và ưu tiên SCN khi cần mốc chính xác.

## 6. Phục hồi một PDB

### 6.1. Khi nào dùng PDB-level recovery?

PDB-level recovery phù hợp khi sự cố giới hạn trong một PDB, ví dụ:

- Mất hoặc hỏng datafile thuộc PDB.
- Lỗi thao tác dữ liệu chỉ ảnh hưởng PDB đó và cần point-in-time recovery.
- Cần phục hồi PDB từ backup riêng trong khi các PDB khác vẫn hoạt động.

Các thao tác RMAN PDB được điều khiển từ CDB root. Trước khi chạy, xác định PDB name, `CON_ID`, datafile và trạng thái mở. Không nhầm tên PDB với tên service hoặc schema.

### 6.2. Restore/recover PDB đến hiện tại

Kết nối SQL*Plus tới `CDB$ROOT` với quyền thích hợp và đóng PDB bị ảnh hưởng:

```sql
ALTER PLUGGABLE DATABASE salespdb CLOSE IMMEDIATE;
```

Trong RMAN kết nối target CDB:

```rman
RESTORE PLUGGABLE DATABASE salespdb;
RECOVER PLUGGABLE DATABASE salespdb;
```

Sau complete recovery, mở lại PDB:

```sql
ALTER PLUGGABLE DATABASE salespdb OPEN;
```

Lệnh trên là mẫu cho tình huống PDB còn metadata trong CDB và backup/archived log cần thiết có sẵn. Trạng thái PDB, loại file bị mất và release cụ thể có thể yêu cầu thao tác bổ sung. Luôn kiểm tra output RMAN và trạng thái datafile trước khi mở PDB cho ứng dụng.

### 6.3. PDB point-in-time recovery (PDB PITR)

PDB PITR phục hồi một PDB về SCN/time mục tiêu mà không nhất thiết đưa toàn CDB về cùng thời điểm. RMAN có thể dùng auxiliary destination để dựng môi trường phụ trợ phục vụ quá trình PITR:

```rman
RECOVER PLUGGABLE DATABASE salespdb
  UNTIL SCN 123456789
  AUXILIARY DESTINATION '/u02/rman_aux';
```

Đường dẫn auxiliary destination phải tồn tại/đủ dung lượng và được Oracle/RMAN truy cập. Chọn SCN minh họa ở trên theo thời điểm cần phục hồi thực tế. Với PDB PITR, Oracle tạo trạng thái PDB theo incarnation mới; sau khi RMAN hoàn tất, mở PDB theo yêu cầu của quy trình PITR, thường là:

```sql
ALTER PLUGGABLE DATABASE salespdb OPEN RESETLOGS;
```

Không nhầm PDB PITR với restore/recover hoàn chỉnh tới hiện tại. PDB PITR loại bỏ thay đổi sau mốc đã chọn của PDB đó. Cần xem hướng dẫn đúng release về điều kiện auxiliary instance, PDB state, local undo/shared undo, application container và các hạn chế liên quan.

### 6.4. PDB tablespace/datafile recovery

Nếu chỉ một datafile hoặc tablespace trong PDB bị hỏng, có thể xem xét phục hồi ở phạm vi nhỏ hơn. RMAN có cú pháp hỗ trợ chỉ định PDB, tablespace hoặc datafile; ví dụ khái quát:

```rman
RESTORE DATAFILE 17;
RECOVER DATAFILE 17;
```

Datafile number phải được xác định từ `V$DATAFILE`/`CDB_DATA_FILES` và mapping `CON_ID`, không dùng số minh họa. Khi xử lý PDB, cần đảm bảo đúng container và trạng thái file; có thể cần đóng PDB hoặc đưa datafile/tablespace offline theo hướng dẫn release. Không chạy restore datafile của PDB mà chưa xác định chính xác file thuộc container nào.

## 7. Kiểm tra mapping PDB và datafile

Từ root, xem danh sách PDB:

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Xem datafile theo container:

```sql
SELECT con_id,
       file_id,
       tablespace_name,
       file_name,
       status
FROM cdb_data_files
ORDER BY con_id, file_id;
```

Với tempfiles:

```sql
SELECT con_id,
       file_id,
       tablespace_name,
       file_name,
       status
FROM cdb_temp_files
ORDER BY con_id, file_id;
```

Kiểm tra file ở cấp database:

```sql
SELECT file#, name, status, enabled
FROM v$datafile
ORDER BY file#;
```

Các view CDB cần được truy vấn từ root và quyền phù hợp. Nếu đang ở một PDB, các view `CDB_*` có thể không hiển thị đầy đủ dữ liệu toàn CDB theo cách DBA mong đợi.

## 8. TDE, wallet và các điều kiện bảo mật

Nếu CDB/PDB dùng Transparent Data Encryption (TDE), backup của datafile không đủ để giải mã dữ liệu nếu thiếu keystore/wallet và encryption keys cần thiết. Trước khi restore sang host mới hoặc mở PDB sau recovery, cần:

- Xác định keystore type và vị trí cấu hình.
- Khôi phục/đưa wallet hoặc external keystore vào đúng môi trường theo quy trình bảo mật.
- Bảo đảm các master encryption keys cần thiết còn tồn tại và có thể mở.
- Kiểm tra trạng thái keystore trong container phù hợp.
- Không đưa wallet password hoặc key material vào script/log/chat không bảo vệ.

Việc PDB mở được không phải lúc nào cũng chứng minh tất cả dữ liệu mã hóa có thể truy cập. Hãy thử truy vấn đối tượng TDE sau recovery bằng tài khoản kiểm thử được kiểm soát.

## 9. Khác biệt giữa restore, recover, flashback và plug/unplug

| Cơ chế | Chức năng | Khi dùng |
|---|---|---|
| RMAN RESTORE | Sao chép backup datafile/control file/SPFILE về vị trí đích | File bị mất/hỏng hoặc cần dựng lại từ backup |
| RMAN RECOVER | Áp dụng archived redo/redo để đưa file/database đến mục tiêu nhất quán | Sau restore hoặc khi cần media recovery |
| Flashback Database | Quay database về thời điểm trước bằng flashback logs khi được cấu hình | Phục hồi nhanh một số lỗi logic mà không restore toàn bộ backup |
| PDB PITR | Đưa một PDB về SCN/time mục tiêu bằng RMAN | Lỗi logic chỉ ảnh hưởng một PDB |
| Unplug/plug PDB | Di chuyển PDB bằng XML manifest/datafiles hoặc archive | Di chuyển/clone PDB giữa CDB tương thích |
| Data Pump | Export/import logical objects và dữ liệu | Di chuyển logic hoặc phục hồi đối tượng ở mức schema/table |

`RESTORE` và `RECOVER` là hai bước khác nhau: restore lấy bản sao từ backup; recover áp dụng redo để tiến đến mục tiêu. `FLASHBACK` không thay thế chiến lược backup. Unplug/plug là di chuyển container và cần kiểm tra compatibility, không phải phương án thay thế RMAN media recovery.

## 10. Mở lại CDB/PDB và xác nhận sau phục hồi

Sau khi RMAN hoàn tất, kiểm tra trạng thái database:

```sql
SELECT name,
       open_mode,
       database_role,
       log_mode,
       resetlogs_change#,
       resetlogs_time
FROM v$database;

SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Kiểm tra datafile:

```sql
SELECT con_id,
       file#,
       status,
       error,
       recover
FROM v$datafile_header
ORDER BY con_id, file#;
```

Kiểm tra recovery status và các lỗi còn lại:

```sql
SELECT *
FROM v$recover_file;

SELECT name, cause, type, status, message, action
FROM pdb_plug_in_violations
ORDER BY name, time;
```

Sau đó xác nhận:

- PDB cần phục hồi đã mở đúng mode (`READ WRITE` hoặc mode được yêu cầu).
- Các PDB không liên quan vẫn ở trạng thái dự kiến.
- Không còn datafile cần recovery ngoài dự kiến.
- Service được đăng ký và ứng dụng kết nối đúng PDB/service.
- TDE keystore mở và dữ liệu mã hóa đọc được.
- Các câu SQL nghiệp vụ quan trọng trả dữ liệu đúng tại thời điểm phục hồi.
- Job, scheduler, database link, directory và external dependency hoạt động bình thường.
- Có backup mới sau thao tác PITR/RESETLOGS theo chính sách backup.

Nếu CDB/PDB vừa mở sau incomplete recovery hoặc resetlogs, cần kiểm tra database incarnation và catalog để RMAN chọn đúng backup/archived log cho các lần backup tiếp theo.

## 11. Những lỗi và tình huống cần chú ý

### 11.1. Không có archived log cần thiết

Nếu thiếu log trong chuỗi từ backup tới target SCN, RMAN không thể hoàn tất recovery tới mục tiêu. Có thể phục hồi tới SCN/time sớm hơn mà log còn đủ, nhưng phải đánh giá mất dữ liệu và consistency của ứng dụng.

### 11.2. Backup thuộc DBID hoặc incarnation khác

Backup piece có thể thuộc database khác hoặc incarnation khác. Kiểm tra DBID, `LIST INCARNATION`, repository và cấu hình catalog trước khi dùng. Không catalog hoặc restore backup không rõ nguồn gốc vào production.

### 11.3. Sai đường dẫn hoặc thiếu dung lượng

Restore có thể thất bại nếu ASM disk group, filesystem, channel hoặc auxiliary destination không sẵn sàng. Dự trù đủ dung lượng cho datafile, archived log, FRA và auxiliary files; xác nhận quyền OS và storage mount trước khi chạy.

### 11.4. PDB không tương thích với CDB đích

PDB plug-in có thể bị chặn do release, option, character set, endian hoặc component mismatch. Dùng `DBMS_PDB.CHECK_PLUG_COMPATIBILITY` và `PDB_PLUG_IN_VIOLATIONS`; xử lý lỗi theo hướng dẫn Oracle thay vì bỏ qua.

### 11.5. CDB/PDB chưa ở đúng trạng thái

Restore toàn CDB thường cần instance ở MOUNT; PDB-specific recovery có thể yêu cầu PDB đóng. Kiểm tra trạng thái hiện tại trước khi chạy. Không thực hiện recovery trên PDB đang nhận giao dịch nếu quy trình release yêu cầu đóng.

## 12. Quy trình diễn tập phục hồi

Một backup chỉ thực sự hữu ích khi có thể restore/recover trong thời gian đáp ứng RTO. Nên diễn tập trên môi trường không production:

1. Ghi nhận Oracle release, RU, DBID, CDB/PDB list, `COMPATIBLE`, platform và TDE configuration.
2. Tạo backup CDB/PDB cùng archived log; lưu control file/SPFILE autobackup và metadata RMAN.
3. Kiểm tra backup bằng `CROSSCHECK`, `PREVIEW`, `RESTORE ... VALIDATE`.
4. Tạo kịch bản mất một datafile trong PDB và thực hiện PDB recovery.
5. Tạo kịch bản lỗi logic và thực hiện PDB PITR tới SCN/time đã xác định.
6. Tạo kịch bản mất control file hoặc host và diễn tập CDB restore/recovery.
7. Đo thời gian từng bước, dung lượng auxiliary, thời gian mở PDB và thời gian ứng dụng kết nối lại.
8. Kiểm tra dữ liệu sau phục hồi, PDB violations, TDE, service và job.
9. Ghi lại lỗi gặp phải, lệnh đã dùng, quyền cần thiết, thời gian thực tế và điểm cần tự động hóa.
10. Cập nhật runbook theo đúng release/RU và kiểm tra lại sau các lần upgrade lớn.

## 13. Nguyên tắc cần ghi nhớ

- Luôn xác định phạm vi CDB, PDB, tablespace hay datafile trước khi restore.
- Thực hiện các thao tác quản trị CDB/PDB từ container và quyền phù hợp; RMAN PDB operations được điều khiển từ CDB root.
- Kiểm tra release, RU, `COMPATIBLE`, DBID, incarnation, platform/endian và PDB plug-in compatibility trước khi phục hồi/di chuyển.
- Có backup hợp lệ và archived redo log bao phủ đến SCN/time mục tiêu; kiểm tra control file, SPFILE và TDE keys.
- `RESTORE` lấy file từ backup; `RECOVER` áp dụng redo; `OPEN RESETLOGS` chỉ dùng khi loại recovery yêu cầu.
- PDB PITR giới hạn tác động vào PDB được chọn, nhưng làm mất các thay đổi sau mốc recovery của PDB đó.
- `PREVIEW` kiểm tra lựa chọn backup; `VALIDATE` kiểm tra khả năng đọc/khôi phục; diễn tập restore mới chứng minh quy trình vận hành.
- Sau recovery, xác nhận trạng thái datafile, PDB, service, TDE và dữ liệu nghiệp vụ; tạo backup mới theo chính sách.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Backup and Recovery User's Guide — RMAN Backup and Recovery of CDBs and PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/)
- [Oracle Database 19c Backup and Recovery Reference — RMAN Commands](https://docs.oracle.com/en/database/oracle/oracle-database/19/rcmrf/)
- [Oracle Database 19c Multitenant Administrator's Guide — Managing PDBs](https://docs.oracle.com/en/database/oracle/oracle-database/19/multi/)
- [Oracle Database 19c Reference — V$DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html)
- [Oracle Database 19c Reference — V$PDBS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-PDBS.html)
- [Oracle Database 19c Reference — PDB_PLUG_IN_VIOLATIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/PDB_PLUG_IN_VIOLATIONS.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_PDB](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_PDB.html)
