# Kế hoạch cắt chuyển, go/no-go và giới hạn của rollback hoặc downgrade

Một lần nâng cấp hoặc di chuyển Oracle Database chỉ được xem là hoàn tất khi ứng dụng hoạt động trên đích, dữ liệu đã được xác nhận, các hệ thống phụ thuộc kết nối đúng và đội vận hành có thể xử lý sự cố sau cutover. Kế hoạch cutover phải mô tả rõ thời điểm chuyển traffic, điều kiện cho phép tiếp tục, người có quyền quyết định, bằng chứng xác nhận và cách quay lui nếu kết quả không đạt.

Điểm dễ gây nhầm lẫn là từ **rollback** thường được dùng cho nhiều hành động khác nhau:

- **Application rollback:** đưa traffic về phiên bản ứng dụng cũ.
- **Traffic rollback:** chuyển DNS, service, connection pool hoặc load balancer về endpoint cũ.
- **Database recovery/restore:** khôi phục database từ backup hoặc flashback về một mốc trước đó.
- **Data rollback/reconciliation:** xử lý các giao dịch đã ghi vào database mới sau cutover.
- **Database downgrade:** hạ database từ Oracle release mới về release cũ bằng quy trình downgrade được hỗ trợ.
- **Forward fix:** giữ database mới và sửa lỗi bằng thay đổi tiếp theo.

Những hành động này không tương đương nhau. Đổi traffic về ứng dụng cũ không làm database tự quay lại schema cũ; restore database có thể làm mất các giao dịch mới; downgrade release có thể không còn được hỗ trợ sau khi sử dụng tính năng mới hoặc nâng COMPATIBLE. Vì vậy, phương án fallback phải được thiết kế theo từng mốc thay đổi và phải được diễn tập trước khi thực hiện trên production.

## 1. Mục tiêu và phạm vi cutover

### 1.1. Cutover là gì?

Cutover là thời điểm hệ thống chuyển từ môi trường nguồn sang môi trường đích hoặc từ database release cũ sang release mới. Cutover thường bao gồm:

1. Ngừng hoặc giới hạn ghi trên hệ thống nguồn.
2. Đồng bộ phần dữ liệu cuối cùng.
3. Chuyển role/service/connection endpoint.
4. Khởi động hoặc mở traffic trên ứng dụng đích.
5. Kiểm tra giao dịch và dữ liệu.
6. Theo dõi ổn định sau chuyển đổi.

Cutover không chỉ là thay connection string. Nó là một thay đổi đồng bộ giữa database, ứng dụng, batch jobs, integrations, credentials, network routes và vận hành.

### 1.2. Go/no-go

- **GO:** tiếp tục sang bước tiếp theo vì tất cả điều kiện bắt buộc đã đạt và người có thẩm quyền xác nhận.
- **NO-GO:** dừng trước một điểm không thể quay lại an toàn, giữ hệ thống ở trạng thái đã xác định và kích hoạt phương án fallback hoặc sửa lỗi.
- **HOLD:** tạm dừng để thu thập thêm bằng chứng hoặc xử lý một điều kiện chưa rõ. HOLD không được kéo dài vô hạn; phải có owner và thời hạn quyết định.

Go/no-go là quyết định dựa trên bằng chứng, không phải cảm nhận rằng hệ thống “có vẻ ổn”.

### 1.3. Định nghĩa thành công

Trước change window, định nghĩa rõ:

- Ứng dụng nào phải hoạt động.
- Database nào là writer duy nhất sau cutover.
- Những luồng nghiệp vụ nào bắt buộc pass.
- Row counts/control totals nào phải khớp.
- Ngưỡng latency/error rate/throughput chấp nhận được.
- Những background jobs nào được phép chạy.
- RPO và RTO thực tế.
- Thời gian quan sát trước khi đóng cửa sổ rollback.
- Ai ký xác nhận kỹ thuật và nghiệp vụ.

### 1.4. Phạm vi thay đổi

Phân biệt loại thay đổi:

| Loại thay đổi | Ví dụ | Điểm cần kiểm soát |
|---|---|---|
| Application release | Deploy Spring Boot mới | Tương thích schema và rollback binary |
| Schema change | Thêm/đổi cột, index, constraint | Tương thích cả ứng dụng cũ và mới |
| Database upgrade | Nâng Oracle release | Dictionary, COMPATIBLE, components, feature |
| Migration | Chuyển sang database/host mới | Data consistency, endpoint, delta sync |
| Platform change | OS, storage, RAC, cloud | Driver, network, performance, recovery |
| Security change | TDE, wallet, credentials | Khả năng mở database và kết nối ứng dụng |

Một đợt cutover có thể kết hợp nhiều loại thay đổi. Càng nhiều biến thay đổi cùng lúc, càng khó xác định nguyên nhân khi có lỗi. Tách các thay đổi độc lập thành các đợt riêng nếu lịch trình và kiến trúc cho phép.

## 2. Phân biệt rollback, restore, downgrade và forward fix

### 2.1. Application rollback

Application rollback đưa binary/configuration về phiên bản trước. Nó chỉ an toàn nếu phiên bản cũ vẫn tương thích với schema và dữ liệu đang tồn tại.

Ví dụ:

- Ứng dụng mới chỉ thêm một cột nullable, ứng dụng cũ vẫn hoạt động.
- Ứng dụng mới ghi vào cột mới mà ứng dụng cũ không hiểu.
- Migration đã xóa/đổi tên cột cũ mà ứng dụng cũ vẫn cần.

Hai trường hợp đầu có thể có mức tương thích khác nhau; trường hợp cuối có thể khiến application rollback thất bại. Vì vậy schema change nên dùng mô hình expand-and-contract.

### 2.2. Traffic rollback

Traffic rollback chuyển client về endpoint cũ. Việc này có thể nhanh nhưng chỉ đúng nếu database cũ vẫn là nguồn dữ liệu có thẩm quyền và đã nhận mọi thay đổi cần thiết.

Nếu database mới đã nhận giao dịch sau cutover, chỉ đổi DNS/connection string về database cũ có thể làm mất các giao dịch mới hoặc tạo hai nhánh dữ liệu phân kỳ.

### 2.3. Database restore/recovery

Restore/recovery đưa database về trạng thái có thể phục hồi từ backup, archived redo, flashback logs hoặc snapshot phù hợp. Đây là phương án phục hồi database, không phải thao tác đơn giản để undo một DDL.

Restore có thể:

- Khôi phục toàn database hoặc một phần theo phương pháp được hỗ trợ.
- Yêu cầu downtime và thời gian apply redo.
- Làm mất các thay đổi sau recovery point nếu không có cách giữ/chuyển chúng.
- Cần khôi phục đồng bộ TDE wallet, control files, parameter files và các phụ thuộc.

### 2.4. Flashback Database

Flashback Database dùng flashback logs để đưa database về một thời điểm hoặc restore point trước đó trong phạm vi được hỗ trợ. Đây có thể là fallback hữu ích cho một số nâng cấp, nhưng phải kiểm tra prerequisites, dung lượng Fast Recovery Area (FRA), thời gian giữ flashback logs và hướng dẫn của Oracle release.

Flashback Database không phải backup độc lập. Nó không thay thế RMAN backup, không hoàn tác email/payment/API đã gửi ra ngoài, không khôi phục file ngoài database và không tự đồng bộ lại các hệ thống phụ thuộc.

### 2.5. Downgrade database

Downgrade là quy trình đưa database từ release mới về release cũ bằng đường đi Oracle hỗ trợ. Nó khác restore một backup cũ và khác application rollback.

Downgrade có thể bị giới hạn bởi:

- Source/target release không có đường downgrade được hỗ trợ.
- Database đã nâng COMPATIBLE lên mức mới.
- Đã sử dụng feature hoặc datatype không tồn tại ở release cũ.
- Các thay đổi dictionary/component không downgrade được.
- PDB/CDB, RAC, Data Guard hoặc option có quy trình riêng.
- Các thao tác sau upgrade đã làm mất điều kiện downgrade.

Không giả định mọi Oracle upgrade đều có thể downgrade chỉ vì có script downgrade trong Oracle Home.

### 2.6. Forward fix

Forward fix giữ database đích và sửa lỗi bằng application patch, schema change bổ sung, cấu hình hoặc data repair. Đây có thể là phương án ít rủi ro hơn restore nếu database mới đã nhận nhiều giao dịch hợp lệ và lỗi có phạm vi hẹp.

Forward fix vẫn cần đánh giá dữ liệu, kiểm thử và phê duyệt. Không dùng nó để trì hoãn quyết định khi đang có corruption hoặc mất tính nhất quán dữ liệu.

## 3. Chiến lược tương thích schema: expand-and-contract

### 3.1. Vì sao cần tương thích hai chiều?

Trong rolling deployment, có thể đồng thời tồn tại ứng dụng cũ và mới. Nếu schema thay đổi ngay lập tức theo cách chỉ phiên bản mới hiểu, ứng dụng cũ có thể lỗi trong thời gian rollout hoặc khi cần rollback.

Expand-and-contract chia schema change thành các giai đoạn:

1. **Expand:** thêm cột/bảng/index mới theo cách tương thích với ứng dụng cũ.
2. **Deploy:** triển khai ứng dụng mới có thể đọc/ghi schema mới, đồng thời giữ tương thích nếu cần.
3. **Migrate data:** backfill dữ liệu và kiểm tra.
4. **Switch:** chuyển toàn bộ traffic sang logic mới.
5. **Observe:** theo dõi đủ lâu và xác nhận không còn consumer cũ.
6. **Contract:** xóa cột/logic cũ trong release riêng sau khi không còn cần rollback về app cũ.

### 3.2. Ví dụ thêm cột

Giả sử ứng dụng cần thay CUSTOMER_NAME thành DISPLAY_NAME.

Giai đoạn expand:

```sql
ALTER TABLE APP.CUSTOMER
    ADD DISPLAY_NAME VARCHAR2(200 CHAR);
```

Ứng dụng mới có thể ghi cả cột cũ và mới trong giai đoạn chuyển tiếp. Backfill:

```sql
UPDATE APP.CUSTOMER
SET DISPLAY_NAME = CUSTOMER_NAME
WHERE DISPLAY_NAME IS NULL;
COMMIT;
```

Sau khi xác nhận mọi consumer dùng DISPLAY_NAME và rollback window kết thúc, mới cân nhắc contract bằng release riêng. Không xóa CUSTOMER_NAME trong cùng change window nếu vẫn cần quay lại binary cũ.

### 3.3. Dual-write và consistency

Dual-write hai cột giúp app cũ/mới cùng hoạt động nhưng tạo nguy cơ hai giá trị lệch nhau. Phải xác định:

- Cột nào là source of truth.
- Thứ tự ghi và transaction boundary.
- Xử lý lỗi khi một lần ghi thất bại.
- Backfill và delta capture.
- Cách phát hiện mismatch.
- Thời điểm dừng ghi cột cũ.

Không bật dual-write chỉ bằng cách thêm hai câu UPDATE mà thiếu cơ chế reconciliation.

### 3.4. Destructive schema changes

Các thao tác như DROP COLUMN, đổi datatype không tương thích, đổi meaning của cột, drop table, rename object hoặc thay constraint theo cách ứng dụng cũ không hiểu có thể làm application rollback không còn khả thi.

Đưa destructive changes sang giai đoạn contract sau khi:

- Tất cả app instances đã nâng cấp.
- Batch/integration cũ đã dừng.
- Không còn consumer dùng object cũ.
- Rollback window đã đóng theo phê duyệt.
- Có backup/recovery point và migration evidence.

## 4. Lựa chọn cutover strategy

### 4.1. Big-bang cutover

Tất cả traffic được chuyển trong một cửa sổ duy nhất:

- Dừng ghi source.
- Export/sync delta cuối.
- Import/validate target.
- Chuyển endpoint.
- Mở traffic.

Ưu điểm là kiến trúc và đồng bộ dữ liệu tương đối đơn giản. Nhược điểm là downtime tập trung, áp lực change window cao và rollback sau khi target nhận writes khó hơn.

### 4.2. Blue-green

Blue là môi trường hiện tại, green là môi trường đích. Green được chuẩn bị và kiểm tra trước; traffic được chuyển theo bước hoặc một lần.

Blue-green giúp giữ môi trường cũ sẵn sàng trong giai đoạn đầu, nhưng không tự giải quyết data divergence. Cần xác định database nào nhận writes và cách đồng bộ khi đổi chiều.

### 4.3. Canary hoặc traffic split

Một phần traffic được đưa sang đích để kiểm chứng. Phù hợp khi ứng dụng và data model cho phép chia traffic an toàn. Nếu hai database cùng nhận writes cho cùng một entity mà không có cơ chế consistency, canary có thể tạo hai nguồn dữ liệu phân kỳ.

### 4.4. Data Guard switchover

Với kiến trúc Data Guard, switchover chuyển primary role có kiểm soát sang standby đã đồng bộ. Đây là role transition, không phải downgrade release hay rollback ứng dụng.

Trước switchover cần kiểm tra:

- Transport/apply lag.
- Protection mode/level.
- Broker status và validation.
- Standby redo logs.
- Service relocation và client reconnect.
- Database role sau chuyển đổi.

Nếu primary/standby đang ở các release hoặc trạng thái upgrade khác nhau, chỉ dùng quy trình role transition được hỗ trợ cho topology đó.

### 4.5. Rolling upgrade

Một số kiến trúc Oracle hỗ trợ rolling upgrade bằng phương pháp được Oracle tài liệu hóa, chẳng hạn quy trình dựa trên Data Guard/Transient Logical Standby hoặc công cụ AutoUpgrade trong các release phù hợp. Không tự thiết kế rolling upgrade bằng cách chạy hai database version độc lập cùng ghi dữ liệu nếu không có cơ chế được hỗ trợ.

### 4.6. So sánh

| Chiến lược | Downtime | Độ phức tạp dữ liệu | Điểm cần lưu ý |
|---|---|---|---|
| Big-bang | Thường tập trung | Thấp hơn nếu freeze đầy đủ | Cửa sổ dài, fallback sau writes khó |
| Blue-green | Có thể ngắn | Cao nếu có writes sau cutover | Cần xác định một writer và data sync |
| Canary | Có thể rất thấp | Cao nếu traffic ghi bị chia | Cần routing theo dữ liệu và consistency |
| Data Guard switchover | Thường ngắn nếu chuẩn bị tốt | Redo apply duy trì đồng bộ | Phải validate role transition và service |
| Rolling upgrade | Có thể giảm downtime | Phụ thuộc phương pháp Oracle hỗ trợ | Có giới hạn version/feature cụ thể |

## 5. Lập kế hoạch recovery trước change window

### 5.1. Backup phải có thể restore

Trước thay đổi, xác nhận:

- RMAN backup đầy đủ và backup pieces đọc được.
- Archived redo logs đủ để phục hồi tới mốc cần thiết.
- Control file và SPFILE được bảo vệ.
- Password file và TDE wallet/keystore được lưu an toàn.
- Backup nằm ở storage/site độc lập theo thiết kế.
- Có đủ dung lượng và quyền truy cập để restore.
- Restore test đã được thực hiện hoặc có bằng chứng gần nhất phù hợp.

Một RMAN job báo COMPLETED không tự chứng minh database có thể restore trong thời gian mục tiêu. Cần kiểm tra backup, metadata và khả năng phục hồi thực tế.

### 5.2. Lấy backup baseline

Ghi lại DBID, DB_UNIQUE_NAME, database role, Oracle release, COMPATIBLE, character sets, timezone file version, control file locations, datafiles, redo logs, FRA và TDE configuration.

Ví dụ:

```sql
SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level
FROM v$database;

SELECT name, value
FROM v$parameter
WHERE name IN (
    'compatible',
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
);

SELECT * FROM v$timezone_file;
```

### 5.3. RMAN backup

Ví dụ lệnh minh họa:

```text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> BACKUP CURRENT CONTROLFILE;
RMAN> BACKUP SPFILE;
```

Lệnh và chiến lược backup phải phù hợp database mode, retention policy, catalog và môi trường. Nếu TDE được dùng, bảo vệ keystore/wallet và xác nhận có thể mở key trên host phục hồi.

### 5.4. Restore rehearsal

Diễn tập restore trên host hoặc môi trường cô lập:

1. Xác định backup cần dùng.
2. Khôi phục control file/SPFILE theo runbook.
3. Restore datafiles.
4. Recover bằng archived redo logs phù hợp.
5. Open database theo phương pháp được hỗ trợ.
6. Kiểm tra object, data và application connectivity.
7. Đo thời gian thực tế.

Không thực hiện restore rehearsal đè lên source production đang hoạt động.

### 5.5. Guaranteed restore point

Với một số database upgrade, guaranteed restore point (GRP) có thể tạo mốc Flashback Database để quay lại trạng thái trước upgrade nếu điều kiện hỗ trợ được đáp ứng.

Trước khi dựa vào GRP:

- Xác nhận Flashback Database và ARCHIVELOG prerequisites theo release.
- Kiểm tra FRA đủ dung lượng cho lượng thay đổi trong toàn change window.
- Xác nhận restore point tồn tại và được guarantee.
- Xác định cách flashback/reopen database đúng release.
- Diễn tập hoặc xác nhận quy trình với DBA chịu trách nhiệm.
- Giám sát FRA liên tục trong thời gian giữ GRP.

GRP có thể làm FRA tăng nhanh; nếu FRA đầy, hoạt động database có thể bị ảnh hưởng. Không tạo GRP rồi quên xóa sau khi rollback window đã kết thúc và đã được phê duyệt.

### 5.6. Restore point không phải downgrade

Flashback về GRP khôi phục database về một trạng thái trước đó. Downgrade chuyển dictionary/database về release cũ bằng quy trình downgrade. Hai cơ chế khác nhau và có điều kiện riêng. GRP cũng không hoàn tác side effects ở hệ thống bên ngoài database.

### 5.7. Storage snapshot

Snapshot ở SAN/VM/cloud có thể hỗ trợ recovery nhanh nhưng phải xác nhận tính nhất quán của database, control/data/redo files và mọi disk group liên quan. Snapshot crash-consistent không nhất thiết tương đương backup được Oracle hỗ trợ. Phối hợp với storage vendor và Oracle recovery procedures.

## 6. Các giới hạn của downgrade Oracle Database

### 6.1. Downgrade path phụ thuộc release

Oracle chỉ hỗ trợ downgrade giữa một số release/source-target combinations và theo các điều kiện được tài liệu hóa. Không thể suy luận rằng nâng từ release A lên B thì luôn hạ ngược từ B về A. Kiểm tra downgrade guide của đúng release, patch level, architecture và installed components.

### 6.2. COMPATIBLE

COMPATIBLE điều khiển mức tương thích tính năng database. Nâng COMPATIBLE lên mức mới có thể loại bỏ khả năng downgrade theo quy trình chuẩn về release cũ.

Không nâng COMPATIBLE ngay sau upgrade chỉ để “đồng bộ version”. Chỉ nâng khi:

- Upgrade đã hoàn tất.
- Ứng dụng và database đã được kiểm chứng.
- Không còn yêu cầu downgrade theo đường được hỗ trợ.
- Change owner chấp nhận việc đóng downgrade path.
- Backup/recovery strategy sau nâng COMPATIBLE đã được xác nhận.

### 6.3. Sử dụng feature mới

Nếu database mới đã tạo hoặc sử dụng datatype, dictionary metadata, SQL feature, index type hoặc component không có ở release cũ, downgrade có thể bị chặn hoặc không giữ được dữ liệu/behavior.

Ngay cả khi chưa nâng COMPATIBLE, việc sử dụng feature mới có thể làm một số object hoặc dữ liệu không downgrade được. Kiểm tra downgrade restrictions và feature usage trước khi sử dụng.

### 6.4. Database components

Các component như JVM, XML DB, Spatial, Text, OLAP hoặc option khác có thể có quy trình upgrade/downgrade riêng. Component status INVALID hoặc phiên bản component không tương thích có thể ảnh hưởng downgrade.

Kiểm tra:

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

### 6.5. CDB/PDB

Multitenant có các điều kiện riêng cho CDB root, seed và PDB. Không giả định downgrade một PDB có thể thực hiện độc lập trong mọi trường hợp. Kiểm tra release guide và trạng thái tất cả container.

### 6.6. RAC, Data Guard và các option

RAC, ASM, Data Guard, GoldenGate, TDE và các integration có thể cần sequence thao tác riêng. Downgrade database không tự động hạ version của Oracle Grid Infrastructure, client, JDBC driver, application hoặc agent.

### 6.7. Time zone file

Timezone file upgrade là thay đổi riêng có thể ảnh hưởng TSTZ data. Kiểm tra timezone downgrade support và dữ liệu đã chuyển đổi. Không hạ timezone file thủ công bằng cách copy file .dat cũ hoặc đổi DBTIMEZONE.

### 6.8. Data Pump VERSION không phải downgrade

Data Pump VERSION chỉ điều khiển metadata export trong phạm vi tương thích. Nó không hạ database dictionary, COMPATIBLE, timezone file hay feature đã dùng. Export một dump có VERSION thấp không biến database mới thành database cũ.

### 6.9. Backup/restore khác downgrade

Restore backup của release cũ có thể đưa hệ thống về trạng thái trước upgrade, nhưng đó là recovery từ backup chứ không phải downgrade database mới. Cần có backup, archived logs, TDE keys, thời gian và môi trường tương thích.

## 7. Giới hạn rollback sau khi target nhận writes

### 7.1. Trước khi mở traffic

Nếu target chưa nhận giao dịch nghiệp vụ, rollback thường đơn giản hơn:

- Chuyển endpoint về source.
- Giữ target để điều tra.
- Hủy hoặc lặp lại import theo kế hoạch.
- Không cần reconcile các giao dịch production mới trên target.

### 7.2. Sau khi target nhận writes

Ngay khi target nhận giao dịch mới, source và target bắt đầu phân kỳ nếu không có replication hai chiều hoặc delta capture. Nếu chuyển traffic về source mà không chuyển các giao dịch mới, dữ liệu mới sẽ bị mất hoặc không xuất hiện ở hệ thống nguồn.

### 7.3. Hai nguồn ghi đồng thời

Không cho phép source và target cùng nhận writes cho cùng một miền dữ liệu nếu chưa có thiết kế conflict resolution, key allocation và transaction consistency. Hai database có thể tạo cùng business transaction hoặc cập nhật một entity theo thứ tự khác nhau.

### 7.4. Reverse replication

Một số kiến trúc có thể giữ replication/reverse capture để đưa thay đổi từ target về source trong rollback window. Cần thiết kế trước:

- Hỗ trợ datatype/schema của hai phía.
- Capture/apply latency.
- Conflict detection/resolution.
- Sequence/key generation.
- DDL synchronization.
- Transaction ordering.
- Failover behavior khi replication bị lỗi.

Không bật reverse replication tùy tiện sau khi đã phát sinh writes; nó không tự giải quyết mọi xung đột.

### 7.5. Restore về trước cutover có thể làm mất dữ liệu

Nếu target nhận 30 phút giao dịch rồi bị restore về GRP trước cutover, các giao dịch 30 phút đó sẽ bị loại khỏi database đã phục hồi. Cần có cách giữ và replay/reconcile chúng nếu nghiệp vụ yêu cầu.

### 7.6. External side effects

Database rollback không thể tự thu hồi:

- Email/SMS đã gửi.
- Payment đã gửi tới payment gateway.
- Message đã publish lên Kafka/queue.
- File đã tạo trên object storage.
- API request đã gửi tới đối tác.
- Job đã chạy trên hệ thống ngoài.

Ứng dụng cần idempotency key, outbox/inbox pattern, compensation workflow hoặc reconciliation để xử lý side effects. Không giả định database transaction bao trùm hệ thống bên ngoài.

## 8. Ma trận lựa chọn fallback

| Thời điểm phát hiện lỗi | Phương án thường xem xét | Rủi ro/điều kiện |
|---|---|---|
| Trước khi import | Dừng change, giữ source | Thường dễ quay lại |
| Import xong, chưa mở traffic | Sửa/re-import hoặc bỏ target | Kiểm tra target chưa có external writes |
| App mới lỗi nhưng schema còn tương thích | Application rollback | Binary cũ phải chạy được với schema hiện tại |
| Traffic đã chuyển nhưng target chưa nhận writes | Chuyển endpoint về source | Xác nhận không có background writer |
| Target đã nhận writes, source vẫn còn | Reverse sync/reconcile hoặc forward fix | Không chỉ đổi connection string |
| DDL đã destructive | Restore/forward fix/recreate object | App cũ có thể không tương thích schema |
| Upgrade lỗi trước khi mở database | GRP/restore/downgrade theo guide | Prerequisites và release path |
| Upgrade hoàn tất, chưa nâng COMPATIBLE | Downgrade nếu Oracle hỗ trợ; hoặc restore | Phải kiểm tra feature usage và downgrade guide |
| COMPATIBLE đã nâng | Thường ưu tiên forward fix hoặc restore backup/GRP nếu hỗ trợ | Standard downgrade có thể không còn khả thi |
| Target đã phát sinh nhiều writes | Forward fix hoặc reverse data migration | RPO, conflict và side effects |

Ma trận là khung quyết định. Change plan cụ thể phải điền release, database role, recovery point, owner và thời gian cho từng nhánh.

## 9. Go/no-go gates

### Gate 1 — Readiness trước change window

GO khi:

- Change scope và owner được phê duyệt.
- Upgrade/migration path được Oracle hỗ trợ.
- Source/target compatibility đã kiểm tra.
- Backup/recovery plan có bằng chứng.
- Restore rehearsal đáp ứng RTO.
- Application compatibility và schema changes đã review.
- Cutover và fallback runbook đã được diễn tập.
- Monitoring, access và escalation đã sẵn sàng.

NO-GO nếu backup không đọc được, downgrade/restore assumptions chưa rõ, hoặc có dependency quan trọng chưa xác định.

### Gate 2 — Pre-cutover

GO khi:

- Target database mở đúng role/mode.
- Components và invalid objects ở trạng thái chấp nhận.
- Data Pump/upgrade logs không có lỗi chưa giải thích.
- Data reconciliation đạt tiêu chí.
- Constraints/indexes/sequences/grants đúng.
- Network, listener, service và credentials hoạt động.
- Batch jobs được kiểm soát.
- Business owner sẵn sàng xác nhận.

NO-GO khi còn mismatch trọng yếu, data loss chưa giải thích hoặc target không có recovery path.

### Gate 3 — Mở traffic

GO khi:

- Source writes đã freeze hoặc delta cuối đã apply.
- Chỉ một database được xác định là writer.
- Connection endpoints trỏ đúng target.
- Smoke tests pass.
- Các luồng nghiệp vụ trọng yếu pass.
- Error rate và latency trong ngưỡng.
- Người có thẩm quyền ra quyết định GO.

NO-GO khi ứng dụng ghi nhầm database, có duplicate key, transaction lỗi hoặc control totals không khớp.

### Gate 4 — Sau cutover

GO để đóng rollback window khi:

- Traffic ổn định trong thời gian quan sát.
- Không có mismatch mới.
- Batch/integration chạy đúng.
- Monitoring và alerting hoạt động.
- Business sign-off được ghi nhận.
- Recovery artifacts được bảo vệ.

Chỉ xóa GRP, backup tạm hoặc reverse replication sau khi change owner phê duyệt và chính sách retention cho phép.

## 10. Tiêu chí go/no-go có thể đo được

Không dùng tiêu chí mơ hồ như “performance tốt” hoặc “không có lỗi đáng kể”. Đặt ngưỡng trước:

| Nhóm | Ví dụ tiêu chí | Bằng chứng |
|---|---|---|
| Availability | Listener/service mở, health checks pass | Connection test, monitoring |
| Data | Row counts/control totals đạt | Reconciliation report |
| Integrity | Không có duplicate/orphan ngoài ngoại lệ | Constraint/query report |
| Application | Luồng đăng nhập, tạo giao dịch, đọc báo cáo pass | Test evidence |
| Error rate | Không vượt ngưỡng đã thống nhất | APM/log metrics |
| Latency | P95/P99 dưới ngưỡng nghiệp vụ | APM/load test |
| Capacity | CPU, memory, I/O, FRA, tablespace còn headroom | Monitoring snapshot |
| Batch | Job trọng yếu hoàn thành đúng lịch | Scheduler/job logs |
| Security | TDE wallet, grants, secrets và audit đúng | Security checklist |
| Recovery | Có phương án và thời gian phục hồi đã kiểm chứng | Restore rehearsal |

Các con số cụ thể phải do hệ thống và nghiệp vụ xác định; không áp dụng một ngưỡng latency chung cho mọi database.

## 11. Runbook cutover chi tiết

### 11.1. T-7 ngày đến T-1 ngày

1. Xác nhận change ticket, owner, escalation tree và maintenance window.
2. Đóng băng các thay đổi schema không nằm trong scope.
3. Kiểm tra release/patch/COMPATIBLE/timezone/components.
4. Chạy preupgrade checks hoặc migration assessment phù hợp.
5. Kiểm tra backup, archive logs, wallet và restore rehearsal.
6. Kiểm tra target capacity, tablespace, FRA, TEMP, undo và network.
7. Diễn tập export/import hoặc upgrade trên dữ liệu đại diện.
8. Đo thời gian từng bước và cập nhật runbook.
9. Chuẩn bị application config, endpoint, secret, firewall và service.
10. Chuẩn bị dashboard và query đối soát.
11. Chốt go/no-go thresholds và người ra quyết định.
12. Gửi thông báo change window theo quy trình tổ chức.

### 11.2. T-60 phút

- Mở war room/bridge theo kế hoạch.
- Xác nhận người phụ trách từng bước có mặt.
- Kiểm tra monitoring và alert channels.
- Xác nhận backup/recovery artifacts truy cập được.
- Kiểm tra source/target status, listener, services và sessions.
- Xác nhận không có deployment hoặc job ngoài kế hoạch.
- Ghi timestamp bắt đầu change window.

### 11.3. T-30 phút

- Dừng hoặc drain các batch writers theo thứ tự.
- Ngăn user/application tạo giao dịch mới theo phương án freeze.
- Kiểm tra active transactions và session writers.
- Ghi SCN/watermark cuối hoặc trạng thái replication.
- Xác nhận source đã ở trạng thái chờ cutover.

### 11.4. T0 — Chốt dữ liệu

- Chạy export cuối hoặc apply delta.
- Đợi Data Guard/replication lag về mức yêu cầu nếu dùng.
- Kiểm tra redo gap/CDC backlog.
- Ghi SCN, timestamp và log.
- Không mở target writer trước khi data barrier được xác nhận.

### 11.5. T+ — Mở target

- Thực hiện role transition hoặc đổi endpoint theo runbook.
- Cập nhật service/DNS/connection configuration.
- Khởi động application instances theo thứ tự.
- Xác nhận runtime user, schema và database identity.
- Chạy smoke test read-only trước, sau đó test write có kiểm soát.
- Mở traffic theo từng nhóm nếu kiến trúc cho phép.

### 11.6. Quan sát sau cutover

Theo dõi:

- Connection failures và ORA errors.
- Transaction commit/rollback.
- P95/P99 latency.
- Connection pool saturation.
- CPU, memory, I/O, redo generation.
- Tablespace, TEMP, UNDO, FRA.
- Scheduler jobs và batch queues.
- Data Guard transport/apply nếu còn standby.
- Business control totals và duplicate keys.

### 11.7. Kết thúc change window

- Ghi nhận GO/NO-GO cuối cùng.
- Lưu logs, SCN, screenshots/metrics và reconciliation reports.
- Ghi các exception, owner và hạn xử lý.
- Xác nhận source database ở trạng thái đã thống nhất (read-only, stopped hoặc giữ để rollback).
- Giữ recovery artifacts theo retention.
- Không xóa restore point/reverse sync trước khi có phê duyệt.

## 12. Rollback decision runbook

### 12.1. Phân loại sự cố

Khi phát hiện lỗi, phân loại nhanh:

1. **Application-only:** lỗi binary/config nhưng database data/schema còn đúng.
2. **Connectivity:** service/listener/DNS/credentials.
3. **Data mismatch:** missing/duplicate/incorrect values.
4. **Schema/object:** INVALID, missing grants, unusable indexes.
5. **Performance/capacity:** latency, I/O, memory, FRA, tablespace.
6. **Database integrity:** corruption hoặc recovery issue.
7. **External integration:** message/payment/API side effects.

### 12.2. Khi chọn application rollback

Chọn khi lỗi nằm ở application và schema vẫn backward-compatible. Kiểm tra:

- Binary cũ có tương thích schema mới không?
- Có background job mới đang ghi dữ liệu theo format mới không?
- Có feature flag để tắt behavior mới không?
- Có side effects đã phát sinh không?

### 12.3. Khi chọn traffic rollback

Trước khi chuyển về source:

- Xác nhận source có dữ liệu mới nhất hoặc có delta replay.
- Xác nhận target đã ngừng nhận writes.
- Xác nhận không có job/consumer tiếp tục ghi target.
- Kiểm tra idempotency và transaction duplication.
- Có quyết định rõ database writer nào có thẩm quyền.

### 12.4. Khi chọn restore/flashback

Chỉ chọn khi:

- Recovery point đã xác định.
- Có backup/flashback logs đủ.
- RPO của các giao dịch sau mốc được chấp nhận hoặc có kế hoạch replay.
- Có đủ thời gian thực hiện trong RTO.
- Các side effects bên ngoài có compensation/reconciliation.
- Có người có thẩm quyền phê duyệt.

### 12.5. Khi chọn downgrade

Chỉ chọn khi Oracle downgrade guide xác nhận source-target path, database state và feature usage cho phép. Kiểm tra COMPATIBLE, components, PDB/CDB, timezone file, Data Guard và các giới hạn khác. Nếu có bất kỳ điều kiện chưa rõ, không thử downgrade trên production để “xem có chạy không”.

### 12.6. Khi chọn forward fix

Chọn khi database mới vẫn nhất quán và lỗi có thể sửa an toàn. Xác định:

- Root cause.
- Phạm vi rows/objects bị ảnh hưởng.
- DDL/DML cần chạy.
- Lock/downtime.
- Roll-forward validation.
- Cách tránh tái phát.

## 13. Ví dụ: quyết định sau khi cutover

Giả sử hệ thống đã chuyển traffic sang target và nhận giao dịch trong 20 phút. Sau đó phát hiện báo cáo cuối ngày sai do ứng dụng mới xử lý timezone khác.

Không nên chỉ đổi endpoint về source vì target đã nhận 20 phút giao dịch. Các bước:

1. Dừng hoặc giới hạn luồng ghi bị ảnh hưởng.
2. Xác định giao dịch trong khoảng 20 phút và timezone conversion đã áp dụng.
3. Kiểm tra source có nhận được các giao dịch đó qua reverse replication hay không.
4. Nếu source chưa nhận, xác định cách export/replay hoặc reconcile theo business key.
5. Nếu không thể đồng bộ an toàn, cân nhắc giữ target và forward fix.
6. Nếu phải restore target, xác định giao dịch sẽ mất và quy trình replay/compensation.
7. Business owner phê duyệt quyết định theo RPO và tính toàn vẹn nghiệp vụ.

Ví dụ này cho thấy rollback traffic không đồng nghĩa rollback data.

## 14. Kiểm tra Oracle trước khi nâng cấp

### 14.1. Xác định release và database identity

```sql
SELECT banner
FROM v$version
ORDER BY banner;

SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode
FROM v$database;

SELECT name, value
FROM v$parameter
WHERE name IN ('compatible', 'cluster_database');
```

### 14.2. Kiểm tra components

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

Xử lý component lỗi trước upgrade theo hướng dẫn Oracle. Không tiếp tục nếu component cần thiết cho ứng dụng đang INVALID mà chưa hiểu nguyên nhân.

### 14.3. Kiểm tra invalid objects baseline

```sql
SELECT owner,
       object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
```

Lưu baseline để phân biệt invalid objects có sẵn với object mới INVALID sau upgrade. Không yêu cầu số INVALID bằng zero một cách máy móc nếu có object invalid được Oracle hoặc ứng dụng quản lý có chủ đích; phải phân loại rõ.

### 14.4. Kiểm tra timezone file

```sql
SELECT * FROM v$timezone_file;
```

Lập kế hoạch DBMS_DST riêng nếu timezone file upgrade nằm trong scope.

### 14.5. Kiểm tra Data Guard

```sql
SELECT database_role,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;

SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
```

Trên primary/standby, kiểm tra destination status, broker configuration và redo gaps bằng view/lệnh phù hợp release.

## 15. Upgrade tool và preupgrade checks

### 15.1. Preupgrade assessment

Trước khi nâng Oracle Database, chạy preupgrade checks bằng công cụ đúng release, chẳng hạn AutoUpgrade hoặc preupgrade.jar/script theo hướng dẫn của phiên bản. Báo cáo có thể nêu:

- Parameter cần điều chỉnh.
- Deprecated/obsolete parameters.
- Component issues.
- Invalid objects.
- Tablespace/capacity concerns.
- Time zone file requirements.
- Feature usage có thể ảnh hưởng upgrade/downgrade.

Không bỏ qua warning chỉ vì công cụ vẫn cho phép tiếp tục.

### 15.2. AutoUpgrade

AutoUpgrade hỗ trợ phân tích, fixup, upgrade và post-upgrade tasks trong các release Oracle được hỗ trợ. Cấu hình, mode và tùy chọn fallback thay đổi theo version. Dùng tài liệu đúng release và giữ log/config/output để audit.

### 15.3. Manual upgrade

Nếu dùng quy trình manual, follow đúng upgrade guide của release. Không trộn script từ Oracle Home khác version. Kiểm tra ORACLE_HOME, PATH, listener, environment và startup parameters trước khi chạy.

### 15.4. Post-upgrade tasks

Sau upgrade, thực hiện các task cần thiết như compile invalid objects, component validation, timezone tasks, optimizer statistics và application tests theo hướng dẫn Oracle. Không tự động chạy mọi script mà không hiểu thứ tự và tác động.

## 16. Data Guard và fallback

### 16.1. Standby là một phần của recovery design

Standby có thể giúp giảm RTO và hỗ trợ role transition, nhưng không tự động là bản rollback của database upgrade. Nếu cả primary và standby đã được nâng hoặc có schema/data changes mới, không thể giả định standby vẫn là release cũ sẵn sàng thay thế.

### 16.2. Switchover và failover

- Switchover là role transition có kế hoạch giữa primary và standby.
- Failover là chuyển standby thành primary khi primary không thể tiếp tục.
- Reinstatement/reinstate phụ thuộc cấu hình và trạng thái database.

Các hành động này không tương đương downgrade. Xác định rõ role và version của từng database sau mỗi bước.

### 16.3. Rolling upgrade với Data Guard

Oracle có quy trình rolling upgrade được hỗ trợ cho các release/topology nhất định. Nó có thể giảm downtime nhưng có preconditions về release, redo transport, logical standby hoặc transient logical standby và feature compatibility. Chỉ áp dụng đúng quy trình Oracle công bố.

### 16.4. Kiểm tra sau role transition

Xác nhận:

- Database role mới.
- Service đăng ký đúng instance.
- Transport destination hướng đúng.
- Apply process hoạt động.
- Application connection pool đã reconnect.
- Protection mode/level đạt mục tiêu.
- Không có redo gap hoặc data divergence chưa xử lý.

## 17. Data Pump migration và rollback

### 17.1. Dump file không phải rollback point

Data Pump dump là bản export logic tại phạm vi và thời điểm cụ thể. Nó không thay thế RMAN backup, không chứa mọi trạng thái physical database và không tự đưa source về trạng thái cũ.

### 17.2. Giữ source

Sau Data Pump migration, giữ source database trong trạng thái đã thống nhất cho tới khi:

- Target reconciliation pass.
- Ứng dụng đã ổn định.
- Delta cuối được xử lý.
- Business sign-off hoàn tất.
- Rollback window đóng.

Không drop source ngay sau khi import thành công.

### 17.3. Delta sau export

Nếu source tiếp tục nhận writes sau snapshot, cần capture/apply delta. Nếu target đã nhận writes, phải quản lý cả hai hướng delta trong fallback plan. Không dùng row count cuối cùng mà không biết snapshot.

### 17.4. Data Pump VERSION

VERSION giúp tạo metadata export tương thích với release cũ trong phạm vi hỗ trợ; nó không tạo downgrade path cho database đã nâng cấp và không đảm bảo mọi feature source có thể import vào target.

## 18. RPO, RTO và thời gian rollback window

### 18.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa nghiệp vụ chấp nhận mất. Khi chọn restore point hoặc backup, xác định các giao dịch sau mốc có được replay hay không.

### 18.2. RTO

Recovery Time Objective là thời gian mục tiêu để dịch vụ trở lại. Đo cả:

- Detection và quyết định NO-GO.
- Stop traffic và drain sessions.
- Restore/flashback/downgrade hoặc switch endpoint.
- Data reconciliation/replay.
- Application startup và smoke tests.
- Business validation.

### 18.3. Rollback window

Rollback window là khoảng thời gian sau cutover mà fallback path còn được duy trì. Thời gian này cần dựa trên:

- Mức rủi ro của change.
- Chu kỳ batch/business.
- Thời gian đối soát.
- Khả năng giữ source và reverse sync.
- Dung lượng GRP/FRA.
- Thời gian cần để restore.

Không đóng rollback window chỉ vì ứng dụng mở được trang chủ.

### 18.4. Sau rollback window

Sau khi đóng rollback window, các hành động destructive như xóa source, xóa GRP, contract schema hoặc nâng COMPATIBLE cần change approval riêng. Ghi lại thời điểm và lý do đóng window.

## 19. Roles, responsibilities và decision authority

| Vai trò | Trách nhiệm |
|---|---|
| Change owner | Điều phối change, giữ timeline và decision log |
| DBA lead | Database upgrade, backup, recovery, data consistency |
| Application lead | Binary/config, compatibility, smoke tests |
| Infrastructure/network | Host, storage, network, DNS, load balancer |
| Security | TDE, wallet, credentials, access control |
| Business owner | Chấp nhận kết quả nghiệp vụ và data risk |
| Operations/NOC | Monitoring, alerting, incident response |
| Release manager | Phê duyệt deploy và change gates |

Chỉ định một người có quyền ra quyết định GO/NO-GO cuối cùng. Mỗi gate cần một người đề xuất, một người xác nhận và một người ghi nhận kết quả.

## 20. Decision log và bằng chứng

Mỗi quyết định phải ghi:

- Thời điểm và timezone.
- Gate đang đánh giá.
- GO/NO-GO/HOLD.
- Metrics/evidence.
- Người đề xuất và người phê duyệt.
- Rủi ro còn lại.
- Hành động tiếp theo.
- Deadline hoặc thời điểm đánh giá lại.

Giữ các artifact:

- Change plan/runbook version.
- Preupgrade reports.
- RMAN backup logs và restore test evidence.
- GRP identifier và FRA metrics.
- Export/import/upgrade logs.
- SCN/watermark và data reconciliation reports.
- Invalid object/component reports.
- Application/APM metrics.
- Test results và business sign-off.
- Rollback/forward-fix decision log.

## 21. Ví dụ decision matrix cho một Oracle upgrade

Giả sử database được nâng từ release cũ lên release mới, ứng dụng Spring Boot giữ nguyên trong đợt đầu.

| Gate | Điều kiện | Quyết định ví dụ |
|---|---|---|
| Readiness | Preupgrade checks còn lỗi component | NO-GO cho tới khi xử lý |
| Backup | RMAN backup xong nhưng chưa restore test | HOLD |
| Pre-cutover | Upgrade hoàn tất, invalid objects mới chưa phân loại | HOLD |
| Data | Control totals khớp, constraints pass | Có thể đề xuất GO |
| Application | Smoke tests pass, P99 latency trong ngưỡng | Có thể đề xuất GO |
| COMPATIBLE | Chưa nâng mức COMPATIBLE mới | Giữ downgrade path nếu Oracle còn hỗ trợ |
| Observation | Một chu kỳ batch chưa hoàn tất | Chưa đóng rollback window |
| Final | Business owner ký nhận và monitoring ổn định | GO đóng window theo change policy |

Ví dụ này minh họa cách ra quyết định; release thực tế có thể có điều kiện khác.

## 22. Bài thực hành: diễn tập cutover và rollback

Thực hiện trong lab/staging có dữ liệu đại diện. Không thử restore, flashback hoặc downgrade trực tiếp trên production.

### Bước 1 — Viết change scope

Ghi database release, schema changes, application version, host/service, target và dependencies.

### Bước 2 — Xác định fallback

Chọn rõ application rollback, traffic rollback, GRP, RMAN restore, downgrade được hỗ trợ hay forward fix. Với mỗi lựa chọn, ghi điều kiện và thời gian.

### Bước 3 — Chụp baseline

Lưu DB identity, COMPATIBLE, timezone file, components, invalid objects, row counts và business totals.

### Bước 4 — Backup và recovery rehearsal

Tạo backup phù hợp, kiểm tra backup pieces và diễn tập restore/flashback trên môi trường cô lập. Đo RTO.

### Bước 5 — Mô phỏng cutover

Freeze source, ghi SCN, apply delta, chuyển endpoint và mở traffic trên target.

### Bước 6 — Kiểm thử application rollback

Deploy phiên bản ứng dụng cũ trên schema mới. Xác nhận schema có backward compatibility hay không. Nếu không, ghi lại DDL gây incompatibility.

### Bước 7 — Mô phỏng writes sau cutover

Tạo một số giao dịch trên target, sau đó thử lập kế hoạch traffic rollback. Xác định cách replay/reverse sync để không mất dữ liệu.

### Bước 8 — Mô phỏng NO-GO

Tạo một lỗi test như service không đăng ký hoặc control total mismatch. Thực hiện decision tree, dừng mở traffic và ghi decision log.

### Bước 9 — Đánh giá downgrade path

Đọc downgrade guide đúng release, kiểm tra COMPATIBLE/feature usage và ghi rõ điều kiện nào đóng downgrade path. Không nhất thiết thực thi downgrade nếu không có môi trường test hỗ trợ.

### Bước 10 — Hoàn thiện runbook

Ghi thời gian từng bước, người thực hiện, lệnh, kết quả mong đợi, điểm dừng và phương án khôi phục.

## 23. Checklist trước change window

- [ ] Change scope, owner và maintenance window đã được phê duyệt.
- [ ] Đã xác định Oracle release/patch và đường upgrade/downgrade hỗ trợ.
- [ ] Đã chạy preupgrade assessment.
- [ ] Database components và invalid objects baseline đã được lưu.
- [ ] COMPATIBLE và thời điểm nâng COMPATIBLE đã được quyết định.
- [ ] Timezone file plan đã được xác nhận.
- [ ] Application/schema compatibility đã được review.
- [ ] Expand-and-contract plan được áp dụng cho destructive changes.
- [ ] RMAN backup và archived logs sẵn sàng.
- [ ] Control file/SPFILE/password file/TDE wallet được bảo vệ.
- [ ] Restore rehearsal đạt RTO.
- [ ] GRP/FRA prerequisites và capacity đã được kiểm tra nếu sử dụng.
- [ ] Data Guard/standby/replication status đạt tiêu chí.
- [ ] Data snapshot/SCN/delta plan đã rõ.
- [ ] Row counts và business control totals baseline đã lưu.
- [ ] Endpoint/DNS/service/connection pool change đã diễn tập.
- [ ] Batch jobs và external integrations có kế hoạch pause/resume.
- [ ] Application rollback và database fallback được mô tả riêng.
- [ ] Data writes sau cutover có reverse sync/reconciliation plan.
- [ ] RPO/RTO và rollback window được business owner phê duyệt.
- [ ] Go/no-go thresholds và decision authority đã chỉ định.
- [ ] War room, escalation và monitoring đã sẵn sàng.

## 24. Checklist tại cutover

- [ ] Đã xác nhận GO tại readiness gate.
- [ ] Đã drain writers và dừng batch theo runbook.
- [ ] Đã ghi SCN/watermark và thời điểm freeze.
- [ ] Đã apply delta cuối và kiểm tra lag/gap.
- [ ] Target role/open mode/service đúng.
- [ ] Không có hai database cùng nhận writes ngoài thiết kế.
- [ ] Connection endpoints và credentials đúng.
- [ ] Smoke tests và write tests có kiểm soát pass.
- [ ] Business control totals và key reconciliation pass.
- [ ] Constraints/indexes/sequences/grants đúng.
- [ ] Error rate, latency và capacity trong ngưỡng.
- [ ] GO/NO-GO decision được ghi nhận.

## 25. Checklist sau cutover và đóng rollback window

- [ ] Đã quan sát đủ thời gian và chu kỳ batch.
- [ ] Không còn lỗi ứng dụng/database chưa giải thích.
- [ ] Monitoring/alerting hoạt động.
- [ ] Data reconciliation cuối cùng pass.
- [ ] External side effects và integrations được xác nhận.
- [ ] Business owner ký nhận.
- [ ] Đã xác nhận database writer chính thức.
- [ ] Source cũ được giữ/xóa theo retention plan.
- [ ] Reverse replication được giữ hoặc dừng theo quyết định.
- [ ] GRP được giữ hoặc drop theo phê duyệt.
- [ ] Backup mới sau cutover đã hoàn thành và kiểm tra.
- [ ] COMPATIBLE chỉ được nâng khi downgrade path không còn cần và đã phê duyệt.
- [ ] Decision log, metrics và evidence được lưu.

## 26. Câu hỏi tự kiểm tra

1. Cutover khác deployment ứng dụng ở điểm nào?
2. GO, NO-GO và HOLD khác nhau như thế nào?
3. Application rollback khác database restore ra sao?
4. Vì sao đổi DNS về source không bảo đảm dữ liệu mới được giữ?
5. Downgrade Oracle khác restore backup như thế nào?
6. Forward fix phù hợp trong trường hợp nào?
7. Expand-and-contract giảm rủi ro rollback ứng dụng ra sao?
8. Vì sao destructive DDL nên tách khỏi giai đoạn deploy đầu?
9. Blue-green có giải quyết tự động data divergence không?
10. Khi nào canary traffic có thể gây hai nguồn ghi?
11. Data Guard switchover khác failover và downgrade thế nào?
12. Vì sao standby không tự động là rollback của database upgrade?
13. Backup RMAN cần những artifact nào ngoài datafiles?
14. Vì sao cần restore rehearsal thay vì chỉ xem backup job completed?
15. Guaranteed restore point hỗ trợ upgrade fallback ra sao?
16. GRP có những yêu cầu về FRA và flashback logs nào?
17. Vì sao GRP không phải backup độc lập?
18. COMPATIBLE ảnh hưởng khả năng downgrade như thế nào?
19. Feature mới đã sử dụng có thể cản downgrade ra sao?
20. Vì sao Data Pump VERSION không phải database downgrade?
21. TSTZ/timezone file upgrade cần kiểm tra gì trước fallback?
22. Vì sao rollback sau khi target nhận writes cần reverse sync hoặc reconciliation?
23. Những side effects nào database restore không thể tự undo?
24. RPO và RTO ảnh hưởng lựa chọn fallback thế nào?
25. Những tiêu chí nào cần có trong pre-cutover gate?
26. Ai nên có quyền ra quyết định GO/NO-GO cuối cùng?
27. Khi nào có thể đóng rollback window?
28. Vì sao cần giữ source trong một khoảng thời gian sau migration?
29. Khi nào nên chọn forward fix thay vì restore?
30. Một rollback rehearsal phải chứng minh những điều gì?

**Nguyên tắc cần nhớ:** Xác định trước một writer duy nhất, snapshot/delta strategy, RPO/RTO và fallback cho từng giai đoạn. Application rollback chỉ đổi binary; traffic rollback chỉ đổi endpoint; database restore/flashback quay dữ liệu về recovery point; downgrade là quy trình Oracle riêng và có giới hạn. Nâng COMPATIBLE hoặc sử dụng feature mới có thể đóng downgrade path. Sau khi target nhận writes, không chuyển traffic về source nếu chưa có kế hoạch reverse sync/reconciliation. Chỉ GO khi dữ liệu, ứng dụng, hạ tầng và recovery evidence đạt ngưỡng đã thống nhất; chỉ đóng rollback window sau business sign-off.
