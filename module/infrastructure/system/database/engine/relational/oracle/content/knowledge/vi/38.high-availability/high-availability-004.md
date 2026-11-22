# Data Guard: primary, physical standby và redo transport/apply

Oracle Data Guard là tập hợp công nghệ giúp duy trì một hoặc nhiều database standby để bảo vệ database primary trước lỗi phần cứng, storage, sự cố tại trung tâm dữ liệu hoặc một số lỗi vận hành. Với **physical standby**, database standby duy trì bản sao vật lý của primary bằng cách nhận và áp dụng redo. Redo transport chuyển redo từ primary tới standby; redo apply sử dụng redo đó để cập nhật các data block trên standby.

Ba khái niệm cốt lõi:

- **Primary database**: database đang phục vụ workload chính và tạo redo cho các thay đổi.
- **Physical standby database**: bản sao vật lý được duy trì bằng cách áp dụng redo từ primary.
- **Redo transport và redo apply**: transport chuyển redo tới standby; apply áp dụng redo vào standby datafiles để giữ dữ liệu đồng bộ.

Luồng tổng quát:

~~~text
Ứng dụng ghi dữ liệu
       |
       v
Primary database
       |
       +--> LGWR ghi online redo log
       |
       +--> Redo transport services
                    |
                    v
             Network / Oracle Net
                    |
                    v
             Standby RFS process
                    |
                    v
          Standby Redo Log (SRL)
                    |
                    v
             Redo Apply (MRP)
                    |
                    v
          Physical standby datafiles
~~~

Data Guard không đơn giản là sao chép file theo lịch. Redo transport và apply có thể hoạt động liên tục hoặc gần liên tục, theo cấu hình đồng bộ hoặc bất đồng bộ. Độ trễ, khả năng chịu lỗi và nguy cơ mất dữ liệu phụ thuộc protection mode, transport mode, network, standby redo log, tốc độ apply và cách vận hành.

Bài học tập trung vào primary/physical standby, pipeline redo transport/apply, cấu hình cơ bản, protection mode, giám sát lag, xử lý archive gap, Data Guard Broker và các thao tác switchover/failover.

## 1. Data Guard bảo vệ database như thế nào?

Data Guard duy trì một hoặc nhiều standby database để có thể chuyển vai trò khi primary gặp sự cố hoặc khi cần bảo trì có kế hoạch.

### 1.1. Primary database

Primary là database nhận kết nối ghi chính. Khi transaction thay đổi dữ liệu:

1. Oracle tạo redo mô tả các thay đổi cần phục hồi.
2. LGWR ghi redo từ redo log buffer vào online redo log.
3. Redo transport chuyển redo tới standby destination đã cấu hình.
4. Primary tiếp tục hoạt động theo semantics của transport/protection mode.

Redo là thông tin cần thiết để tái tạo thay đổi; nó không phải bản sao trực tiếp của từng datafile block tại thời điểm gửi.

### 1.2. Physical standby database

Physical standby có cấu trúc file và nội dung block tương ứng với primary. Redo apply sử dụng redo nhận được để cập nhật standby datafiles.

Physical standby có thể ở các trạng thái vận hành khác nhau:

- MOUNTED và đang chạy managed recovery.
- OPEN READ ONLY khi không apply redo.
- OPEN READ ONLY với apply đồng thời trong cấu hình Active Data Guard được hỗ trợ và có license phù hợp.
- Tạm dừng apply để xử lý bảo trì hoặc sự cố theo runbook.

Không nhầm physical standby với logical standby. Physical standby áp dụng redo ở mức vật lý/block; logical standby chuyển redo thành các thay đổi logic/SQL và có giới hạn tương thích riêng.

### 1.3. Một primary có thể có nhiều standby

Data Guard có thể duy trì nhiều standby database. Mỗi standby có DB_UNIQUE_NAME riêng, network service riêng, transport destination riêng trên primary, trạng thái transport/apply riêng và storage/archive policy riêng.

Không giả định mọi standby đều có cùng lag hoặc cùng khả năng chuyển role. Một standby có thể đồng bộ trong khi standby khác bị chậm do network, storage hoặc apply throughput.

### 1.4. Data Guard không thay thế backup

Standby có thể bảo vệ khỏi một số sự cố primary, nhưng lỗi logic bị replicate cũng có thể lan sang standby. Ví dụ, người dùng xóa nhầm dữ liệu hoặc chạy DDL sai có thể được redo apply tái hiện.

Backup độc lập vẫn cần thiết để phục hồi dữ liệu bị xóa/hỏng logic, khôi phục tới thời điểm trước thao tác sai, phục hồi khi cả primary và standby cùng bị ảnh hưởng và đáp ứng retention/audit.

## 2. Các thành phần trong pipeline redo transport/apply

Hiểu vai trò từng process giúp xác định lỗi nằm ở primary, network, standby hay apply.

### 2.1. LGWR trên primary

LGWR ghi redo từ redo log buffer vào online redo log. Trong các cấu hình transport dùng redo từ LGWR, redo transport lấy dữ liệu redo từ luồng này để gửi tới standby.

LGWR vẫn chịu trách nhiệm ghi redo cục bộ. Data Guard không thay thế online redo log của primary.

### 2.2. Redo transport services

Redo transport services chuyển redo từ primary tới standby. Cấu hình thường được khai báo qua LOG_ARCHIVE_DEST_n với thuộc tính SERVICE, VALID_FOR, DB_UNIQUE_NAME và transport attributes.

Các process cụ thể và đường truyền có thể khác theo Oracle release, transport mode và cấu hình. Với các luồng LGWR transport, LNS process tham gia gửi redo; ARCn có thể tham gia vận chuyển archived redo hoặc xử lý các luồng archive/fallback theo cấu hình.

### 2.3. Network

Redo được gửi qua Oracle Net tới service của standby. Các yếu tố ảnh hưởng:

- Network latency và bandwidth.
- Packet loss/retransmission.
- Listener/service availability.
- DNS/TNS resolution.
- Firewall/port.
- Encryption/compression.
- Số standby cùng nhận redo.
- Mức độ đồng thời của workload.

Với SYNC transport, network round-trip time có thể ảnh hưởng trực tiếp tới commit latency. Với ASYNC, primary không đợi standby xác nhận từng commit theo cùng cách, nhưng standby có thể bị lag nếu network hoặc receiver không theo kịp.

### 2.4. RFS trên standby

Remote File Server (RFS) nhận redo từ primary. Khi standby redo log được cấu hình, RFS ghi redo vào Standby Redo Log (SRL). Sau đó redo có thể được archive và đưa vào tiến trình apply.

RFS là thành phần quan trọng khi điều tra:
- Standby có nhận redo không?
- SRL có được ghi không?
- Network connection có ổn định không?
- Có archive log bị thiếu hoặc không thể tạo không?

### 2.5. Standby Redo Log (SRL)

SRL là nhóm redo log dành cho standby. Nó cho phép standby nhận redo trực tiếp khi primary đang ghi online redo log, hỗ trợ real-time apply và các protection mode cần xác nhận redo tới standby.

SRL khác online redo log:

- Online redo log phục vụ redo generation tại database đang là primary.
- Standby redo log nhận redo được transport tới database đang là standby.
- Một database có thể cần cả hai loại vì sau switchover, nó có thể đổi role.

### 2.6. MRP và redo apply

Managed Recovery Process (MRP) áp dụng redo trên physical standby. Tên process thường thấy là MRP0. MRP đọc redo từ standby redo log hoặc archived redo log theo trạng thái và cấu hình, rồi cập nhật standby datafiles.

Nếu transport khỏe nhưng apply chậm, redo vẫn đến standby nhưng chưa được áp dụng kịp. Nếu apply dừng, standby có thể tích lũy backlog dù network không có lỗi.

## 3. Transport lag và apply lag

Hai loại lag đo hai đoạn khác nhau trong pipeline.

### 3.1. Transport lag

Transport lag phản ánh độ trễ giữa redo được tạo trên primary và redo đã được nhận tại standby. Lag tăng có thể do network chậm/mất kết nối, standby listener/service không sẵn sàng, RFS không nhận hoặc ghi kịp, SRL/archive destination có vấn đề hoặc primary gửi redo nhanh hơn khả năng nhận của standby.

### 3.2. Apply lag

Apply lag phản ánh độ trễ giữa redo đã phát sinh trên primary và redo đã được apply vào standby datafiles.

Apply lag có thể tăng khi MRP bị dừng, apply throughput thấp hơn redo generation rate, standby CPU/I/O không đủ, recovery process bị ảnh hưởng bởi workload đọc hoặc có archive gap.

### 3.3. Đọc hai lag cùng nhau

| Transport lag | Apply lag | Diễn giải ban đầu |
| --- | --- | --- |
| Thấp | Thấp | Transport và apply đang theo kịp |
| Cao | Cao | Redo chưa tới standby đầy đủ; apply cũng bị chậm theo |
| Thấp | Cao | Redo đã tới nhưng apply không theo kịp hoặc apply bị dừng |
| Cao | Thấp/không cập nhật | Kiểm tra freshness của metric, MRP state và thời điểm tính lag |

Một giá trị lag thấp tại một thời điểm không bảo đảm không có spike. Ghi nhận chuỗi mẫu, thời gian computed và trạng thái process.

### 3.4. Lag không phải trực tiếp là số byte mất dữ liệu

Transport lag/apply lag thường biểu diễn độ trễ thời gian theo thống kê Data Guard. Chúng không trực tiếp cho biết chính xác số byte chưa nhận hoặc số transaction có thể mất. Để đánh giá exposure, cần xem sequence/SCN, redo generation rate, transport state và protection mode.

## 4. Standby Redo Log: cấu hình và nguyên tắc

SRL là điều kiện quan trọng cho real-time apply và cấu hình đồng bộ.

### 4.1. Kích thước SRL

Kích thước SRL nên bằng hoặc lớn hơn kích thước online redo log lớn nhất của primary để có thể nhận đầy đủ redo từ log tương ứng.

Ví dụ, nếu primary có online redo log lớn nhất 1 GB, SRL nên có size tối thiểu 1 GB. Nếu các thread có kích thước khác nhau, tính theo log lớn nhất có thể gửi tới standby.

### 4.2. Số lượng SRL

Nguyên tắc cấu hình phổ biến là tạo ít nhất một SRL group nhiều hơn số online redo log groups cho mỗi redo thread. Cần áp dụng cho từng thread trong RAC.

Ví dụ primary có 3 online redo log groups cho thread 1, standby nên có ít nhất 4 SRL groups cho thread 1. Đây là baseline cấu hình; có thể cần nhiều hơn tùy số group đang active, transport concurrency và hướng dẫn phiên bản.

### 4.3. Tạo SRL trong ASM/OMF

Ví dụ dùng Oracle Managed Files:

~~~sql
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
ALTER DATABASE ADD STANDBY LOGFILE THREAD 1 SIZE 1G;
~~~

Tên file được Oracle quản lý nếu OMF destination đã cấu hình. Cú pháp thực tế phụ thuộc storage layout và phiên bản.

Ví dụ chỉ định group/member rõ ràng trên filesystem:

~~~sql
ALTER DATABASE ADD STANDBY LOGFILE
  THREAD 1 GROUP 11
  ('/u03/oradata/standby/srl11.log') SIZE 1G;
~~~

Đây là đường dẫn minh họa. Không dùng cùng tên file với online redo log hoặc file đã tồn tại.

### 4.4. Kiểm tra SRL

~~~sql
SELECT group#,
       thread#,
       sequence#,
       bytes / 1024 / 1024 AS size_mb,
       archived,
       status
FROM v$standby_log
ORDER BY thread#, group#;
~~~

Kiểm tra online redo log để so kích thước và thread:

~~~sql
SELECT group#,
       thread#,
       bytes / 1024 / 1024 AS size_mb,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

### 4.5. Cấu hình SRL trên cả hai site

Sau switchover, standby có thể trở thành primary và primary cũ trở thành standby. Vì vậy, mỗi database nên được chuẩn bị SRL phù hợp với online redo log mà nó có thể nhận khi giữ vai trò standby.

Không chỉ tạo SRL trên standby hiện tại rồi quên primary. Kiểm tra SRL ở mọi member của Data Guard configuration.

## 5. Các protection mode

Protection mode xác định mức độ ưu tiên giữa bảo đảm không mất dữ liệu và tính sẵn sàng của primary.

### 5.1. Maximum Protection

Mục tiêu là bảo đảm zero data loss cho các transaction đã commit trong failure model và cấu hình được hỗ trợ. Primary yêu cầu redo được xác nhận bởi standby đồng bộ theo chế độ bảo vệ. Nếu không còn standby phù hợp để bảo vệ, primary có thể tự shutdown thay vì tiếp tục commit mà vi phạm mục tiêu protection.

Đặc điểm:
- Ưu tiên bảo vệ dữ liệu tối đa.
- Cần ít nhất một standby được cấu hình đồng bộ và đủ điều kiện.
- Có thể ảnh hưởng availability nếu standby/network không sẵn sàng.
- Cần thiết kế network, storage và standby redundancy phù hợp.

### 5.2. Maximum Availability

Mục tiêu là zero data loss khi standby đồng bộ còn khả dụng, nhưng vẫn ưu tiên primary tiếp tục hoạt động khi standby tạm thời mất kết nối. Trong thời gian không có standby đồng bộ, protection có thể tạm giảm xuống mức tương đương Maximum Performance; khi standby trở lại, protection được khôi phục theo điều kiện cấu hình.

Đặc điểm:
- Cân bằng availability và data protection.
- Thường dùng SYNC transport.
- Commit latency phụ thuộc network và cấu hình AFFIRM/NOAFFIRM.
- Cần giám sát thời gian primary ở trạng thái protection bị giảm.

### 5.3. Maximum Performance

Ưu tiên hiệu năng và tính sẵn sàng của primary. Redo thường được gửi bất đồng bộ (ASYNC), nên primary không phải đợi standby xác nhận redo cho mỗi commit theo cách của SYNC.

Đặc điểm:
- Ít tác động network latency lên commit path.
- Standby có thể bị transport lag.
- Khi primary mất đột ngột, có thể mất các transaction chưa được transport tới standby.
- Cần đo redo generation rate, network throughput và lag để hiểu data-loss exposure.

### 5.4. So sánh

| Mode | Mục tiêu | Transport thường dùng | Rủi ro chính |
| --- | --- | --- | --- |
| Maximum Protection | Bảo vệ dữ liệu cao nhất | SYNC với xác nhận phù hợp | Primary có thể dừng nếu mất standby đồng bộ |
| Maximum Availability | Zero data loss khi standby đồng bộ sẵn sàng, ưu tiên primary availability | SYNC | Có thể tạm giảm protection khi standby mất kết nối |
| Maximum Performance | Tối ưu hiệu năng primary | ASYNC | Có thể mất redo chưa transport khi primary gặp sự cố |

Mode và transport attribute cụ thể cần kiểm tra theo Oracle release, cấu hình và yêu cầu RPO/RTO. Không chọn protection mode chỉ vì tên nghe an toàn hơn; phải đánh giá latency, network topology và hành vi khi standby mất kết nối.

## 6. SYNC, ASYNC, AFFIRM và NOAFFIRM

Các thuộc tính transport điều khiển thời điểm primary nhận xác nhận từ standby và cách standby xác nhận redo đã được ghi.

### 6.1. SYNC

SYNC yêu cầu primary đồng bộ với standby theo giao thức transport. Trong commit path, primary chờ phản hồi theo semantics của transport để bảo đảm redo đã được nhận ở standby theo cấu hình.

SYNC phù hợp với yêu cầu bảo vệ dữ liệu cao, nhưng network round-trip time và standby I/O có thể ảnh hưởng commit latency.

### 6.2. ASYNC

ASYNC gửi redo mà không chờ standby xác nhận cho từng commit theo cùng cách SYNC. Primary có thể tiếp tục xử lý transaction trong khi redo được transport nền.

ASYNC giảm ảnh hưởng network latency tới commit, nhưng standby có thể tụt lại khi redo generation rate cao, network throughput thấp, standby receiver không theo kịp hoặc SRL/storage bị nghẽn.

### 6.3. AFFIRM

AFFIRM yêu cầu standby xác nhận sau khi redo đã được ghi bền vững vào standby redo log theo semantics Oracle. Điều này tăng mức đảm bảo dữ liệu đã được lưu trên standby trước khi primary nhận acknowledgment, nhưng có thể thêm I/O latency vào commit path.

### 6.4. NOAFFIRM

NOAFFIRM cho phép standby gửi acknowledgment trước khi redo được ghi bền vững xuống SRL theo cách AFFIRM yêu cầu. Nó có thể giảm latency nhưng thay đổi mức bảo vệ trong các tình huống lỗi đồng thời.

Không xem NOAFFIRM như tương đương AFFIRM. Đánh giá rủi ro theo protection mode, failure model và Oracle documentation của release.

### 6.5. Bảng lựa chọn khái quát

| Transport attribute | Primary chờ xác nhận đồng bộ? | Standby xác nhận ghi bền vững? | Tác động chính |
| --- | --- | --- | --- |
| SYNC AFFIRM | Có | Có | Bảo vệ cao, latency nhạy với network và I/O |
| SYNC NOAFFIRM | Có | Không đợi durable write theo AFFIRM | Có thể giảm latency, cần hiểu failure exposure |
| ASYNC AFFIRM | Không chờ mỗi commit | Standby dùng AFFIRM khi xác nhận nhận redo | Commit ít phụ thuộc RTT, transport vẫn có thể lag |
| ASYNC NOAFFIRM | Không chờ mỗi commit | Không đợi durable write theo AFFIRM | Throughput tốt hơn trong nhiều trường hợp, exposure phụ thuộc lag |

Các tổ hợp được phép và cách sử dụng phụ thuộc version, protection mode và cấu hình. Fast Sync là biến thể NOAFFIRM được hỗ trợ trong một số cấu hình Maximum Availability; nó không làm mọi failure scenario tương đương SYNC AFFIRM. Hãy kiểm tra tài liệu Oracle cho đúng release trước khi triển khai.

## 7. Cấu hình cơ bản primary/physical standby

Cấu hình thực tế phải được thiết kế theo DB_UNIQUE_NAME, network, storage, file naming và database role. Ví dụ dưới đây minh họa các tham số chính; không phải script có thể chạy nguyên xi trên mọi hệ thống.

### 7.1. Điều kiện tiên quyết

Trước khi cấu hình:
- Primary database đang hoạt động và có backup hợp lệ.
- DB_NAME giống nhau giữa primary và physical standby.
- DB_UNIQUE_NAME khác nhau cho mỗi database.
- Oracle Net service kết nối hai chiều theo yêu cầu vận hành.
- Password file và quyền SYSDBA phù hợp.
- Storage cho datafile, online redo log, SRL, archive và FRA đã sẵn sàng.
- ARCHIVELOG mode được bật.
- FORCE LOGGING được bật hoặc có chính sách bảo đảm mọi thay đổi cần thiết được ghi redo.
- Standby có cấu hình memory/process đủ cho workload apply.
- Time synchronization và DNS/network ổn định.

### 7.2. Bật ARCHIVELOG và FORCE LOGGING

Kiểm tra log mode:

~~~sql
SELECT log_mode,
       force_logging
FROM v$database;
~~~

Nếu cần bật ARCHIVELOG, database phải được MOUNT:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
ALTER DATABASE ARCHIVELOG;
ALTER DATABASE FORCE LOGGING;
ALTER DATABASE OPEN;
~~~

Lập kế hoạch backup và archive destination trước khi bật ARCHIVELOG. FORCE LOGGING giúp bảo đảm các thao tác không logging thông thường vẫn tạo redo cần cho standby, nhưng cần đánh giá tác động hiệu năng và các trường hợp đặc biệt theo Oracle documentation.

### 7.3. Tham số nhận diện database

Ví dụ trên primary:

~~~sql
ALTER SYSTEM SET db_unique_name='PROD_PRI' SCOPE=SPFILE;
ALTER SYSTEM SET log_archive_config='DG_CONFIG=(PROD_PRI,PROD_STBY)' SCOPE=BOTH;
~~~

Ví dụ trên standby:

~~~sql
ALTER SYSTEM SET db_unique_name='PROD_STBY' SCOPE=SPFILE;
ALTER SYSTEM SET log_archive_config='DG_CONFIG=(PROD_PRI,PROD_STBY)' SCOPE=BOTH;
~~~

DB_NAME thường giống nhau vì standby là database cùng identity logic; DB_UNIQUE_NAME phân biệt từng member. Nếu thay DB_UNIQUE_NAME trong SPFILE, có thể cần restart tùy tham số và cách cấu hình.

### 7.4. Cấu hình local archive destination

Ví dụ:

~~~sql
ALTER SYSTEM SET log_archive_dest_1=
 'LOCATION=USE_DB_RECOVERY_FILE_DEST
  VALID_FOR=(ALL_LOGFILES,ALL_ROLES)
  DB_UNIQUE_NAME=PROD_PRI'
 SCOPE=BOTH;
~~~

Trên standby, DB_UNIQUE_NAME trong local destination phải là tên unique của chính standby. Dùng FRA hoặc filesystem location phù hợp với thiết kế.

### 7.5. Cấu hình remote redo transport

Ví dụ primary gửi redo bất đồng bộ tới physical standby:

~~~sql
ALTER SYSTEM SET log_archive_dest_2=
 'SERVICE=PROD_STBY
  ASYNC NOAFFIRM
  VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE)
  DB_UNIQUE_NAME=PROD_STBY'
 SCOPE=BOTH;

ALTER SYSTEM SET log_archive_dest_state_2=ENABLE SCOPE=BOTH;
~~~

PROD_STBY là Oracle Net service name phân giải tới standby. Cần kiểm tra tnsnames/listener và kết nối SYSDBA từ primary tới standby. Không đưa mật khẩu vào script hoặc log.

### 7.6. Các tham số standby thường dùng

~~~sql
ALTER SYSTEM SET standby_file_management=AUTO SCOPE=BOTH;
ALTER SYSTEM SET fal_server='PROD_PRI' SCOPE=BOTH;
~~~

STANDBY_FILE_MANAGEMENT=AUTO cho phép standby tự động xử lý một số thay đổi file được redo ghi nhận, ví dụ thêm datafile, theo semantics được hỗ trợ. FAL_SERVER chỉ định nguồn để standby yêu cầu archived log còn thiếu trong cấu hình truyền thống; Data Guard Broker có thể quản lý một phần cấu hình này.

Nếu đường dẫn file primary và standby khác nhau, cấu hình DB_FILE_NAME_CONVERT hoặc dùng OMF/DB_CREATE_FILE_DEST phù hợp. Với OMF, tránh thêm chuyển đổi đường dẫn không cần thiết.

### 7.7. Kiểm tra destination

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error,
       valid_now
FROM v$archive_dest
WHERE dest_id <= 10
ORDER BY dest_id;
~~~

V$ARCHIVE_DEST_STATUS cung cấp trạng thái runtime chi tiết hơn. Khi có lỗi, xem ERROR, STATUS, DESTINATION và alert log ở cả primary lẫn standby.

## 8. Tạo physical standby

Physical standby có thể được tạo từ backup hoặc duplicate from active database bằng RMAN. Quy trình cụ thể phụ thuộc dung lượng, network, phiên bản và chiến lược backup.

### 8.1. Chuẩn bị standby instance

- Cài Oracle software tương thích.
- Tạo password file phù hợp.
- Tạo PFILE/SPFILE với DB_NAME, DB_UNIQUE_NAME và các tham số cần thiết.
- Chuẩn bị storage location.
- Cấu hình Oracle Net/listener.
- Đảm bảo primary có thể được kết nối từ standby.
- Chuẩn bị backup hoặc đường truyền active duplicate.

### 8.2. RMAN duplicate from active database

Mẫu minh họa:

~~~text
RMAN> CONNECT TARGET sys@PROD_PRI;
RMAN> CONNECT AUXILIARY sys@PROD_STBY;

RMAN> DUPLICATE TARGET DATABASE
       FOR STANDBY
       FROM ACTIVE DATABASE
       DORECOVER
       SPFILE
       SET DB_UNIQUE_NAME='PROD_STBY';
~~~

Đây là skeleton minh họa. Cần điều chỉnh password file, channel, section size, file name conversion, OMF, encryption, network compression, DB_FILE_NAME_CONVERT và các tham số khác theo release/storage. Thực hiện trong môi trường đã được chuẩn bị và có quyền phù hợp.

### 8.3. Tạo từ backup

Có thể restore backup primary trên host standby rồi recover tới trạng thái phù hợp. Phải bảo đảm backup, control file và archived redo đủ để dựng standby. Dùng RMAN duplicate/restore theo quy trình được kiểm thử.

### 8.4. Xác nhận database role

Trên standby:

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode,
       controlfile_type
FROM v$database;
~~~

Kỳ vọng DATABASE_ROLE là PHYSICAL STANDBY. Nếu role khác, dừng và xác minh trước khi bật apply.

## 9. Bật Redo Apply trên physical standby

Khi standby đã MOUNT và SRL được cấu hình, có thể khởi động managed recovery.

### 9.1. Managed recovery ở MOUNT

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
DISCONNECT FROM SESSION;
~~~

Oracle chạy managed recovery process nền. Trên physical standby, MRP thường xuất hiện trong V$DATAGUARD_PROCESS hoặc V$MANAGED_STANDBY tùy phiên bản.

### 9.2. Real-time apply

Khi SRL được cấu hình và transport ghi redo vào SRL, real-time apply cho phép standby áp dụng redo từ SRL trước khi archived log hoàn tất, giảm apply lag.

Ở một số phiên bản cũ, ví dụ có cú pháp USING CURRENT LOGFILE:

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
USING CURRENT LOGFILE
DISCONNECT FROM SESSION;
~~~

Cú pháp và mặc định real-time apply đã thay đổi qua các release; ở các phiên bản hiện đại, USING CURRENT LOGFILE thường không còn cần thiết. Kiểm tra tài liệu phiên bản thay vì copy cú pháp cũ.

### 9.3. Dừng Redo Apply

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE CANCEL;
~~~

Chỉ dừng apply khi có mục tiêu vận hành rõ như mở read-only không có Active Data Guard, bảo trì hoặc xử lý sự cố. Khi apply dừng, backlog có thể tăng và standby có thể tụt lại.

### 9.4. Mở physical standby READ ONLY

Không có Active Data Guard, physical standby có thể được mở READ ONLY khi không chạy managed recovery theo mô hình truyền thống:

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE CANCEL;
ALTER DATABASE OPEN READ ONLY;
~~~

Để tiếp tục apply theo mô hình Active Data Guard được hỗ trợ:

~~~sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
DISCONNECT FROM SESSION;
~~~

Open read-only đồng thời apply là tính năng Active Data Guard; cần xác nhận license và điều kiện phiên bản/cấu hình. Không nhầm việc mở READ ONLY đơn thuần với Active Data Guard.

## 10. Theo dõi transport và apply

Giám sát cần kiểm tra cả primary và standby. Một query đơn lẻ không đủ xác định toàn bộ pipeline.

### 10.1. Trạng thái database và protection

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status,
       force_logging
FROM v$database;
~~~

Kiểm tra:
- DATABASE_ROLE: PRIMARY hoặc PHYSICAL STANDBY.
- OPEN_MODE: READ WRITE, MOUNTED, READ ONLY hoặc trạng thái đặc thù.
- PROTECTION_MODE/LEVEL: mode cấu hình và mức protection thực tế.
- SWITCHOVER_STATUS: thông tin về khả năng chuyển role.
- FORCE_LOGGING: trạng thái force logging.

### 10.2. Transport lag và apply lag

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Các trường TIME_COMPUTED và DATUM_TIME giúp đánh giá độ mới của metric. Nếu datum time không cập nhật, một giá trị lag thấp có thể là số liệu cũ chứ không phải trạng thái hiện tại.

### 10.3. Data Guard processes

~~~sql
SELECT name,
       role,
       action,
       thread#,
       sequence#,
       block#
FROM v$dataguard_process
ORDER BY name;
~~~

V$DATAGUARD_PROCESS có trên các release hỗ trợ. Ở một số phiên bản/công cụ cũ, DBA thường dùng V$MANAGED_STANDBY:

~~~sql
SELECT process,
       status,
       thread#,
       sequence#,
       block#
FROM v$managed_standby
ORDER BY process;
~~~

V$MANAGED_STANDBY đã được thay thế/deprecate trong một số release; ưu tiên view được khuyến nghị cho phiên bản đang chạy.

### 10.4. Archive destination status

Trên primary:

~~~sql
SELECT dest_id,
       status,
       target,
       destination,
       error,
       archived_thread#,
       archived_seq#
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
~~~

Kiểm tra destination standby có ERROR hay không, sequence gần nhất đã archive/transport và thời điểm cập nhật.

### 10.5. Standby redo log status

~~~sql
SELECT group#,
       thread#,
       sequence#,
       status,
       archived,
       bytes
FROM v$standby_log
ORDER BY thread#, group#;
~~~

Xem RFS có ghi vào SRL và SRL có được chuyển trạng thái phù hợp sau log switch hay không.

## 11. Archive gap và FAL

Archive gap là khoảng sequence archived redo bị thiếu trên standby. Nếu thiếu redo, MRP có thể dừng tại điểm không thể tiếp tục apply.

### 11.1. Phát hiện gap

Trên physical standby:

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

V$ARCHIVE_GAP hiển thị gap đang chặn recovery. Sau khi xử lý một gap, có thể xuất hiện gap tiếp theo; lặp kiểm tra tới khi không còn gap.

### 11.2. FAL (Fetch Archive Log)

FAL là cơ chế standby yêu cầu archived redo còn thiếu từ nguồn phù hợp. FAL_SERVER thường được cấu hình trong standby để xác định service nguồn.

Nếu FAL không hoạt động, kiểm tra:
- TNS alias và listener.
- Password file/SYS authentication.
- FAL_SERVER.
- LOG_ARCHIVE_CONFIG.
- DB_UNIQUE_NAME.
- Archive log có còn trên primary/FRA không.
- Network ACL/firewall và service registration.

### 11.3. Copy archived log thủ công

Nếu log không còn tự động được fetch, DBA có thể phải lấy archived log từ backup hoặc primary và đăng ký trên standby theo quy trình recovery. Ví dụ:

~~~sql
ALTER DATABASE REGISTER LOGFILE
  '/u04/arch/1_12345_987654321.arc';
~~~

Đây chỉ là ví dụ hình thức. Xác minh đúng thread, sequence, resetlogs ID và file integrity trước khi register. Không đăng ký một file có tên sequence giống nhưng thuộc incarnation khác.

### 11.4. Không xóa archive cần cho standby

Archive log có thể còn cần cho standby chưa nhận, standby đã nhận nhưng chưa apply, FAL gap resolution, backup/recovery policy hoặc downstream standby.

Deletion policy phải xét mọi standby cần bảo vệ, không chỉ standby gần nhất.

## 12. Đánh giá redo generation và apply capacity

Standby chỉ theo kịp nếu khả năng nhận và apply redo đủ lớn so với tốc độ primary tạo redo.

### 12.1. Redo generation rate

Có thể lấy delta statistic redo size từ V$SYSSTAT trên primary để ước lượng byte/second:

\[
RedoRate = \frac{\Delta redo\_size}{ElapsedSeconds}
\]

Dùng cùng instance và cùng vòng đời counter. Trong RAC, đo riêng từng instance/thread rồi tổng hợp có kiểm soát.

### 12.2. Transport throughput

Theo dõi:
- Redo generation rate.
- Network throughput giữa primary và standby.
- Transport lag.
- Archive destination errors.
- RFS activity.
- Standby redo log writes.

Nếu redo generation cao hơn network throughput bền vững, backlog sẽ tăng.

### 12.3. Apply throughput

Theo dõi:
- Apply lag và apply rate.
- MRP process state.
- Standby CPU.
- Datafile I/O latency.
- Parallel recovery configuration.
- Standby workload nếu open read-only.
- Storage contention.

Nếu transport lag thấp nhưng apply lag tăng, ưu tiên điều tra apply throughput thay vì tăng network bandwidth một cách mù quáng.

### 12.4. Peak và backlog recovery time

Không chỉ đo average redo rate. Một batch có thể tạo redo gấp nhiều lần bình thường. Ước lượng thời gian catch-up:

\[
CatchUpTime \approx \frac{RedoBacklog}{ApplyRate - IncomingRedoRate}
\]

Công thức chỉ có ý nghĩa khi ApplyRate lớn hơn IncomingRedoRate và các đại lượng dùng cùng đơn vị. Nếu apply rate không vượt incoming rate, standby sẽ không tự bắt kịp khi workload tiếp tục chạy.

## 13. Data Guard Broker

Data Guard Broker là lớp quản lý cấu hình và role transition tập trung. Broker giúp quản lý database members, transport/apply state, switchover/failover và monitoring.

### 13.1. Bật Broker

Broker thường được bật qua tham số:

~~~sql
ALTER SYSTEM SET dg_broker_start=TRUE SCOPE=BOTH;
~~~

Thực hiện trên các database members theo thiết kế. Cần kiểm tra listener, broker configuration files và network connectivity.

### 13.2. Kết nối DGMGRL

~~~text
DGMGRL> CONNECT sys@PROD_PRI;
~~~

Tạo configuration minh họa:

~~~text
DGMGRL> CREATE CONFIGURATION 'PROD_DG'
         AS PRIMARY DATABASE IS 'PROD_PRI'
         CONNECT IDENTIFIER IS PROD_PRI;

DGMGRL> ADD DATABASE 'PROD_STBY'
         AS CONNECT IDENTIFIER IS PROD_STBY
         MAINTAINED AS PHYSICAL;

DGMGRL> ENABLE CONFIGURATION;
~~~

Đây là skeleton. Tên database và connect identifier phải khớp DB_UNIQUE_NAME/service được cấu hình. Xác nhận cú pháp với DGMGRL help và tài liệu release.

### 13.3. Kiểm tra Broker configuration

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_PRI';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_STBY';
DGMGRL> VALIDATE DATABASE 'PROD_STBY';
~~~

Broker có thể báo WARNING/ERROR khi transport/apply lag vượt threshold hoặc cấu hình không đồng bộ. Đọc status và error detail trước khi sửa property.

### 13.4. Broker properties

Một số property thường được quản lý:
- LogXptMode.
- ApplyLagThreshold.
- TransportLagThreshold.
- NetTimeout.
- ReopenSecs.
- StandbyFileManagement.
- PreferredApplyInstance trong RAC tùy cấu hình.

Property name, giá trị và khả năng hỗ trợ phụ thuộc phiên bản. Dùng SHOW DATABASE VERBOSE và EDIT DATABASE theo tài liệu, tránh tự đặt giá trị chưa xác minh.

## 14. Switchover: chuyển role có kế hoạch

Switchover là chuyển vai trò primary và standby có kế hoạch. Nó thường dùng cho bảo trì primary hoặc kiểm thử quy trình DR. Mục tiêu là chuyển role có kiểm soát và không mất dữ liệu khi standby được đồng bộ đầy đủ.

### 14.1. Điều kiện trước switchover

- Primary và standby đều khỏe.
- Transport/apply lag bằng 0 hoặc đạt điều kiện chấp nhận.
- Không có archive gap.
- Standby đã apply toàn bộ redo cần thiết.
- Có SRL và cấu hình transport phù hợp trên cả hai site.
- Network và listener ổn định.
- Services, client routing và monitoring có kế hoạch chuyển.
- Đã xác nhận backup/recovery state.
- Có cửa sổ thay đổi và người chịu trách nhiệm.

### 14.2. Switchover bằng Broker

Ví dụ:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> VALIDATE DATABASE 'PROD_STBY';
DGMGRL> SWITCHOVER TO 'PROD_STBY';
~~~

Broker điều phối role transition theo cấu hình. Sau chuyển đổi, kiểm tra database cũ đã trở thành physical standby và redo transport/apply hoạt động theo hướng mới.

### 14.3. Switchover thủ công

Các lệnh thủ công thay đổi theo release và trạng thái. Ở các phiên bản hỗ trợ, có thể dùng cú pháp ALTER DATABASE SWITCHOVER TO ... và tùy chọn VERIFY. Không dùng một sequence lệnh cũ cho mọi version.

Broker thường giảm nguy cơ bỏ sót bước và là lựa chọn nên cân nhắc nếu đã triển khai Broker. Nếu làm thủ công, phải theo đúng runbook Oracle release tương ứng.

### 14.4. Sau switchover

Xác nhận:
- DATABASE_ROLE trên cả hai site.
- OPEN_MODE.
- LOG_ARCHIVE_DEST_STATUS.
- MRP đang chạy trên standby mới.
- Transport/apply lag giảm về mục tiêu.
- Application service trỏ tới primary mới.
- Backup, monitoring và alert routing đã đổi role.
- PDB/service cần thiết đã mở và đăng ký.

Switchover hoàn tất về mặt database chưa có nghĩa toàn bộ ứng dụng đã chuyển xong.

## 15. Failover: chuyển role khi primary gặp sự cố

Failover là chuyển standby thành primary khi primary cũ không thể tiếp tục phục vụ. Đây là thao tác khẩn cấp có thể dẫn đến mất dữ liệu tùy protection mode và lượng redo chưa được transport/apply.

### 15.1. Trước failover

Xác định:
- Primary thực sự không thể phục hồi trong thời gian cho phép.
- Không còn khả năng primary tiếp tục ghi độc lập gây split brain.
- Standby nào có redo mới nhất.
- Transport/apply lag và archive gap.
- Các redo log chưa được nhận có thể lấy từ primary cũ hay không.
- RPO được chấp nhận và người có quyền quyết định failover.

Không failover chỉ vì ứng dụng không kết nối được primary; có thể lỗi nằm ở listener, service, network hoặc host tạm thời. Trước hết xác minh trạng thái primary và nguy cơ hai database cùng nhận ghi.

### 15.2. Failover bằng Broker

Ví dụ hình thức:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> FAILOVER TO 'PROD_STBY';
~~~

Cú pháp tùy tình trạng standby và phiên bản; Broker có thể hỗ trợ các loại failover khác nhau. Chỉ thực hiện theo incident runbook và quyền phê duyệt.

### 15.3. Complete hoặc immediate failover

Một số quy trình phân biệt failover cố gắng áp dụng mọi redo có thể lấy được với failover immediate bỏ qua một số bước apply còn lại. Tên option/cú pháp phụ thuộc release và Broker/manual mode.

- Cố gắng hoàn tất apply có thể giảm data loss nhưng mất thời gian.
- Immediate failover có thể khôi phục dịch vụ nhanh hơn nhưng chấp nhận nguy cơ mất thêm redo chưa apply.

Không chọn option chỉ dựa vào tốc độ. Đối chiếu RTO/RPO và redo có thể khôi phục.

### 15.4. Xử lý primary cũ sau failover

Sau khi standby trở thành primary:
- Không cho primary cũ tự mở READ WRITE và nhận traffic.
- Cô lập hoặc shutdown primary cũ để tránh split brain.
- Xác định có thể reinstate bằng Flashback Database và Broker hay phải rebuild.
- Cấu hình lại transport từ primary mới.
- Kiểm tra standby còn lại.
- Backup primary mới theo quy trình.
- Cập nhật client service/DNS/load balancer.
- Ghi nhận data-loss window nếu có.

Nếu Flashback Database đã được bật và điều kiện đáp ứng, Broker có thể hỗ trợ REINSTATE DATABASE để đưa primary cũ trở lại thành standby. Nếu không đủ flashback logs hoặc database incarnation không phù hợp, có thể phải dựng lại standby.

## 16. Role transition và ứng dụng

Data Guard chuyển database role, nhưng ứng dụng cũng phải được điều phối.

### 16.1. Services

Thiết kế database service để ứng dụng kết nối tới role phù hợp. Trong RAC, dùng Clusterware-managed services; trong Data Guard, role-based service có thể tự khởi động ở database role được chỉ định theo cấu hình.

### 16.2. Connection pool

Khi switchover/failover:
- Connection cũ có thể bị ngắt.
- Pool cần reconnect tới service primary mới.
- Retry phải có backoff.
- Transaction đang chạy có thể rollback hoặc cần application-level retry.
- Không retry thao tác không idempotent một cách mù quáng.

### 16.3. Client failover

Dùng Oracle Net/SCAN/service và cấu hình client failover phù hợp. Transparent Application Failover, Application Continuity hoặc Transaction Guard có khả năng và yêu cầu riêng; không giả định mọi ứng dụng tự chuyển kết nối mà không có cấu hình.

### 16.4. Kiểm thử định kỳ

Một DR plan chỉ đáng tin khi đã thử:
- Switchover có kế hoạch.
- Failover theo kịch bản.
- Client reconnect.
- Service start/stop theo role.
- Backup sau role transition.
- Reinstatement hoặc rebuild standby.
- Đo RTO/RPO thực tế.

## 17. Real-time apply và Active Data Guard

### 17.1. Real-time apply

Real-time apply cho phép MRP áp dụng redo ngay từ SRL trong khi primary vẫn đang ghi online redo log. Điều này giảm độ trễ so với chờ archived redo log hoàn tất rồi mới apply.

Điều kiện thường gồm:
- SRL được cấu hình đúng.
- Redo transport tới standby hoạt động.
- Managed recovery đang chạy.
- Standby storage và apply process đủ khả năng.

### 17.2. Active Data Guard

Active Data Guard cho phép physical standby được mở READ ONLY trong khi redo apply tiếp tục chạy, tùy phiên bản và cấu hình. Nó hỗ trợ offload một số workload đọc như reporting và analytics.

Cần:
- Xác nhận license Active Data Guard.
- Đánh giá workload đọc có ảnh hưởng apply không.
- Theo dõi apply lag.
- Đảm bảo query không làm standby quá tải.
- Kiểm tra các giới hạn của open read-only standby.

Không nhầm khả năng MOUNT + apply cơ bản của Data Guard với READ ONLY + apply đồng thời của Active Data Guard.

### 17.3. Standby reporting có thể ảnh hưởng DR readiness

Nếu standby phục vụ query nặng, CPU/I/O có thể bị chia sẻ với redo apply. Điều này làm apply lag tăng. Cần đặt resource plan, giới hạn workload và ngưỡng lag phù hợp với RPO.

## 18. Data Guard trong RAC

RAC và Data Guard giải quyết hai lớp availability khác nhau:
- RAC giúp nhiều instance cùng truy cập một database trong cluster.
- Data Guard duy trì database standby ở site/cluster khác để bảo vệ khỏi lỗi database/storage/site.

### 18.1. Redo thread

Mỗi RAC instance có redo thread riêng. Standby phải có SRL phù hợp cho từng thread có thể gửi redo.

~~~sql
SELECT thread#,
       group#,
       bytes,
       status
FROM v$log
ORDER BY thread#, group#;
~~~

Trên RAC dùng GV$LOG để thấy từng instance/thread khi phù hợp.

### 18.2. SRL theo thread

Tạo đủ SRL group cho từng thread. Không chỉ tạo SRL cho thread 1 nếu primary RAC có nhiều thread.

### 18.3. Apply instance

Tùy cấu hình và phiên bản, managed recovery có thể chạy trên một instance hoặc dùng các khả năng apply phù hợp với RAC. Data Guard Broker có property để điều khiển preferred apply instance trong một số môi trường. Kiểm tra cấu hình cụ thể và trạng thái process qua GV$ views.

### 18.4. Kiểm tra tất cả instance

Dùng GV$DATABASE, GV$INSTANCE, GV$ARCHIVE_DEST_STATUS và GV$DATAGUARD_PROCESS nếu view hỗ trợ. Giữ INST_ID để tránh gộp nhầm cùng một database member.

## 19. Giám sát end-to-end

Một dashboard Data Guard hữu ích nên cho biết trạng thái của cả hai site và pipeline.

### 19.1. Trên primary

Theo dõi:
- DATABASE_ROLE và PROTECTION_LEVEL.
- LOG_ARCHIVE_DEST_n status/error.
- Redo generation rate.
- Archive log switch rate.
- Network destination state.
- Broker configuration status.
- Primary alert log.

### 19.2. Trên standby

Theo dõi:
- DATABASE_ROLE và OPEN_MODE.
- MRP/RFS process.
- Transport lag và apply lag.
- Archive gap.
- SRL usage.
- Apply throughput.
- FRA/archive destination.
- Datafile/storage health.
- Standby alert log.

### 19.3. Lag threshold

Threshold cần theo RPO và workload:
- Warning khi lag vượt ngân sách bình thường.
- Critical khi lag tiến gần RPO hoặc tăng liên tục.
- Emergency khi transport/apply dừng hoặc archive gap không thể tự xử lý.

Không dùng cùng một số giây cho mọi database. Một hệ thống RPO 0 có yêu cầu khác hệ thống chấp nhận mất vài phút dữ liệu.

### 19.4. Freshness của metric

V$DATAGUARD_STATS có TIME_COMPUTED và DATUM_TIME. Kiểm tra hai timestamp để biết metric có được cập nhật. Một giá trị lag cũ không phải bằng chứng transport/apply hiện tại khỏe.

### 19.5. Alerting

Có thể dùng Enterprise Manager, Data Guard Broker health check hoặc hệ thống monitoring ngoài. Alert cần có DB_UNIQUE_NAME, role, INST_ID, transport/apply lag, last datum time, archive destination error, MRP/RFS state, archive gap và hướng xử lý/runbook.

## 20. Xử lý transport lag hoặc apply lag tăng

### 20.1. Transport lag tăng

Điều tra theo thứ tự:
1. Trên primary, kiểm tra LOG_ARCHIVE_DEST_STATUS và ERROR.
2. Kiểm tra Oracle Net service, listener và network route.
3. Kiểm tra standby listener/service.
4. Kiểm tra RFS process.
5. Kiểm tra SRL và archive destination storage.
6. So redo generation rate với network throughput.
7. Xem alert log hai bên.
8. Xác định có archive gap hoặc destination bị DEFER hay không.

Nếu network lỗi, khôi phục connectivity và xác nhận transport tiếp tục. Không xóa archive để reset lag.

### 20.2. Apply lag tăng nhưng transport lag thấp

Điều tra:
- MRP có chạy không?
- MRP đang chờ gap hay đang apply?
- Standby CPU có bão hòa?
- Datafile I/O latency có tăng?
- Standby đang chạy report/query nặng?
- Có recovery parallelism phù hợp?
- Có lỗi corruption hoặc datafile cần recovery?

Có thể cần giảm workload đọc, tăng tài nguyên standby hoặc xử lý recovery backlog.

### 20.3. MRP dừng

Kiểm tra V$DATAGUARD_PROCESS/V$MANAGED_STANDBY, V$DATAGUARD_STATUS, alert log, archive gap và file/storage errors. Sau khi sửa nguyên nhân, khởi động managed recovery theo trạng thái và runbook. Không chạy nhiều lệnh START/STOP apply lặp lại mà không kiểm tra process hiện tại.

### 20.4. Archive gap không tự giải quyết

- Xác định thread và sequence thiếu.
- Kiểm tra log còn ở primary/FRA/backup.
- Kiểm tra FAL/network/password file.
- Fetch hoặc restore đúng archived log.
- Register nếu quy trình yêu cầu.
- Xác nhận MRP tiếp tục và gap kế tiếp đã hết.

## 21. Các lỗi Data Guard thường gặp

| Lỗi/tình huống | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| ORA-16047 | DB_UNIQUE_NAME không khớp destination | LOG_ARCHIVE_DEST_n, DB_UNIQUE_NAME, LOG_ARCHIVE_CONFIG |
| ORA-12514 | Listener không biết service | TNS alias, listener services, service registration |
| ORA-12541 | Không có listener tại endpoint | Listener, host, port, network |
| ORA-12154 | Không phân giải được connect identifier | tnsnames.ora, naming method, service alias |
| ORA-16055 | FAL request bị từ chối | FAL source, archive availability, role/config |
| ORA-00279/ORA-00289 | Recovery yêu cầu archived log | Thread/sequence, archive location, gap |
| ORA-00308 | Không mở được archived log | File path, permission, storage, archive integrity |
| ORA-01153 | Recovery đang chạy hoặc xung đột recovery | MRP state và recovery command |
| ORA-01157/ORA-01110 | Không nhận diện/mở được datafile | Datafile path, storage, control file, file state |
| ORA-19809 | FRA vượt giới hạn | FRA usage, archive/backup retention |
| MRP không chạy | Apply dừng, lỗi file/gap hoặc cấu hình | Broker, alert log, V$DATAGUARD_PROCESS |
| Transport lag tăng | Network, RFS, destination hoặc redo rate | Destination status, network, RFS, SRL |
| Apply lag tăng | MRP/CPU/I/O không theo kịp | Apply process, storage latency, standby workload |
| Switchover không hợp lệ | Standby chưa synchronized hoặc prerequisite thiếu | Broker validate, lag, role/status, alert log |

Mã lỗi và hành vi có thể khác theo release và trạng thái. Luôn đọc toàn bộ error stack và alert log, không chỉ dựa vào tên lỗi.

## 22. Bảo mật và vận hành kết nối Data Guard

Redo transport sử dụng kết nối Oracle Net và quyền xác thực giữa các database. Cấu hình bảo mật cần được xem là một phần của DR design.

- Dùng password file đồng bộ theo yêu cầu và quản lý mật khẩu an toàn.
- Không hard-code mật khẩu trong script, shell history hoặc log.
- Hạn chế quyền SYSDBA và truy cập host.
- Dùng network encryption/TLS theo chính sách.
- Giới hạn network route và firewall rule tới các endpoint cần thiết.
- Theo dõi thay đổi certificate/wallet nếu dùng TLS.
- Bảo vệ backup, archived redo và standby storage.
- Kiểm tra quyền đọc/ghi trên ASM/filesystem.
- Đồng bộ thời gian hệ thống để log correlation đáng tin cậy.

Một Data Guard configuration khỏe nhưng có credential/network không được bảo vệ vẫn là rủi ro bảo mật nghiêm trọng.

## 23. Runbook kiểm tra Data Guard hằng ngày

### 23.1. Trên primary

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level
FROM v$database;
~~~

~~~sql
SELECT dest_id,
       status,
       error,
       destination
FROM v$archive_dest_status
WHERE status <> 'INACTIVE';
~~~

### 23.2. Trên standby

~~~sql
SELECT db_unique_name,
       database_role,
       open_mode
FROM v$database;
~~~

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

~~~sql
SELECT process,
       status,
       thread#,
       sequence#
FROM v$managed_standby;
~~~

Nếu release ưu tiên V$DATAGUARD_PROCESS, dùng view đó thay cho V$MANAGED_STANDBY.

### 23.3. Kiểm tra gap và Broker

~~~sql
SELECT thread#,
       low_sequence#,
       high_sequence#
FROM v$archive_gap;
~~~

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_PRI';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_STBY';
~~~

### 23.4. Ghi nhận kết quả

Daily check nên lưu timestamp, role/open mode từng member, transport/apply lag, last received/applied sequence hoặc SCN, destination errors, MRP/RFS state, archive gap, FRA/storage headroom, Broker status và các thay đổi từ lần kiểm tra trước.

## 24. Thiết kế RPO/RTO cho Data Guard

Data Guard cần gắn với mục tiêu nghiệp vụ.

### 24.1. RPO

Recovery Point Objective là lượng dữ liệu tối đa tổ chức chấp nhận mất khi xảy ra sự cố. Với ASYNC, redo chưa được transport có thể tạo data-loss exposure. Với synchronous protection được cấu hình đúng, mục tiêu có thể là zero data loss trong failure model tương ứng.

RPO không chỉ phụ thuộc protection mode; còn phụ thuộc standby thực sự synchronized hay không, network và standby availability, SRL/AFFIRM semantics, archive gap và loại sự cố.

### 24.2. RTO

Recovery Time Objective là thời gian tối đa để khôi phục dịch vụ. RTO gồm:
- Phát hiện sự cố.
- Quyết định failover.
- Thực hiện role transition.
- Mở database/services.
- Client reconnect.
- Health check và xác nhận ứng dụng.

Một standby đồng bộ nhưng chưa có runbook, service routing và người trực có thể vẫn không đáp ứng RTO.

### 24.3. Kiểm thử RPO/RTO

Đo trong DR exercise:
- Thời gian phát hiện.
- Thời gian quyết định.
- Thời gian failover/switchover.
- Thời gian ứng dụng kết nối lại.
- SCN/transaction cuối đã được apply.
- Lượng dữ liệu mất nếu có.
- Thời gian reinstate/rebuild primary cũ.

Không chỉ ghi Data Guard status SUCCESS; hãy đo kết quả phục hồi ở cấp ứng dụng.

## 25. Những nhầm lẫn thường gặp

**Physical standby là bản backup thay thế.** Không đúng. Standby có thể nhận cả thao tác xóa/sai logic; vẫn cần backup độc lập.

**Transport lag và apply lag là một.** Không đúng. Transport lag đo redo chưa nhận; apply lag đo redo chưa được áp dụng tới datafiles.

**Standby nhận archived redo nghĩa là apply đã xong.** Không đúng. Nhận và apply là hai giai đoạn khác nhau.

**Không cần Standby Redo Log nếu đã có online redo log.** Không đúng. SRL là nơi standby nhận redo trực tiếp và hỗ trợ real-time apply/transport protection.

**Chỉ cần tạo SRL trên standby hiện tại.** Không đúng. Database có thể đổi role; cần chuẩn bị SRL cho các member có thể trở thành standby.

**ASYNC bảo đảm zero data loss.** Không đúng. Redo chưa transport có thể mất khi primary gặp sự cố.

**SYNC luôn không ảnh hưởng latency.** Không đúng. Commit path có thể nhạy với network RTT và standby I/O.

**NOAFFIRM giống AFFIRM.** Không đúng. Acknowledgment và durable write semantics khác nhau.

**Lag bằng 0 tại một snapshot bảo đảm standby luôn đồng bộ.** Không đúng. Cần xem freshness và xu hướng nhiều mẫu.

**MRP chạy nghĩa là standby luôn bắt kịp.** Không đúng. MRP có thể chạy nhưng apply rate thấp hơn incoming redo rate.

**FAL thay thế backup.** Không đúng. FAL fetch archived redo còn sẵn; nó không tái tạo log đã mất khỏi mọi nguồn.

**Có thể xóa archived redo cũ bằng OS.** Không đúng. Có thể phá recovery chain hoặc standby; dùng RMAN policy.

**Switchover và failover giống nhau.** Không đúng. Switchover là chuyển role có kế hoạch; failover là phản ứng khi primary không thể tiếp tục phục vụ.

**Có thể mở primary cũ READ WRITE sau failover.** Không được tự ý. Phải cô lập và reinstate/rebuild để tránh split brain.

**CDB OPEN đồng nghĩa mọi PDB/service sẵn sàng.** Không đúng. Kiểm tra PDB và service riêng.

**Active Data Guard chỉ là tên khác của physical standby.** Không đúng. Một số khả năng như open read-only trong khi apply thuộc Active Data Guard và có yêu cầu license riêng.

## 26. Bài tập tự luyện

1. Giải thích vai trò của primary và physical standby.
2. Phân biệt physical standby và logical standby.
3. Vẽ pipeline từ LGWR tới RFS, SRL và MRP.
4. Vai trò của LNS và ARCn trong redo transport là gì?
5. Vì sao standby redo log khác online redo log?
6. Nêu nguyên tắc kích thước SRL.
7. Nêu nguyên tắc số lượng SRL cho mỗi redo thread.
8. Vì sao nên tạo SRL trên cả hai database members?
9. Phân biệt redo transport và redo apply.
10. Phân biệt transport lag và apply lag.
11. Nêu các nguyên nhân transport lag tăng.
12. Nêu các nguyên nhân apply lag tăng.
13. So sánh Maximum Protection, Maximum Availability và Maximum Performance.
14. Phân biệt SYNC và ASYNC.
15. Phân biệt AFFIRM và NOAFFIRM.
16. Vì sao SYNC có thể làm tăng commit latency?
17. Nêu vai trò DB_NAME và DB_UNIQUE_NAME.
18. Vì sao cần LOG_ARCHIVE_CONFIG DG_CONFIG?
19. Giải thích VALID_FOR trong LOG_ARCHIVE_DEST_n.
20. Vai trò STANDBY_FILE_MANAGEMENT=AUTO là gì?
21. FAL_SERVER dùng để giải quyết vấn đề nào?
22. Viết query kiểm tra V$DATAGUARD_STATS.
23. Viết query kiểm tra V$ARCHIVE_DEST_STATUS.
24. Viết query tìm archive gap.
25. Xử lý thế nào khi FAL không lấy được archived log?
26. Phân biệt real-time apply và apply từ archived log.
27. Data Guard Broker hỗ trợ những thao tác nào?
28. Phân biệt switchover và failover.
29. Vì sao phải cô lập primary cũ sau failover?
30. Thiết kế runbook DR gồm RPO/RTO, kiểm tra lag, role transition, client reconnect và reinstate/rebuild.

**Data Guard giữ physical standby theo kịp primary bằng hai chặng riêng: redo transport đưa redo tới standby, redo apply dùng redo đó để cập nhật datafiles.** Hãy cấu hình đúng DB_UNIQUE_NAME, network, archive destination và standby redo log; chọn protection/transport mode theo RPO, RTO và latency; giám sát transport lag cùng apply lag và freshness của metric. Khi chuyển role, phân biệt switchover có kế hoạch với failover khẩn cấp, cô lập primary cũ và kiểm thử cả database lẫn ứng dụng sau transition.

