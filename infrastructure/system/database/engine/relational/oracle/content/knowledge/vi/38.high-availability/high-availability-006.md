# Protection mode, apply lag, transport lag và kiểm chứng dữ liệu

Oracle Data Guard duy trì một hoặc nhiều standby database từ redo của primary database. Tuy nhiên, có standby không đồng nghĩa tự động không mất dữ liệu. Mức bảo vệ thực tế phụ thuộc protection mode, redo transport, độ trễ mạng, khả năng ghi standby redo log, tốc độ Redo Apply và việc DBA có kiểm chứng được trạng thái dữ liệu hay không.

Ba protection mode thường gặp là Maximum Protection, Maximum Availability và Maximum Performance. Chúng thể hiện đánh đổi giữa tính sẵn sàng của primary, mức đồng bộ redo và khả năng mất dữ liệu khi primary gặp sự cố. Trong vận hành hằng ngày, hai chỉ số quan trọng là **transport lag** (redo chưa được nhận tại standby) và **apply lag** (redo đã nhận nhưng chưa được apply). Hai chỉ số này giúp xác định vấn đề nằm ở network/transport hay ở standby apply.

Bài học đi từ semantics bảo vệ dữ liệu đến cấu hình, monitoring, xử lý lag/gap và kiểm chứng. Kiểm chứng gồm xác nhận trạng thái Data Guard, kiểm tra tính liên tục của redo, phát hiện block corruption và so sánh dữ liệu logic khi yêu cầu nghiệp vụ cần bằng chứng độc lập.

Sau bài học, bạn có thể:

- Phân biệt protection mode với redo transport mode.
- Giải thích Maximum Protection, Maximum Availability và Maximum Performance.
- Hiểu SYNC/ASYNC và AFFIRM/NOAFFIRM ảnh hưởng commit latency và durability thế nào.
- Chọn protection mode theo RPO, RTO và yêu cầu uptime.
- Phân biệt transport lag, apply lag, archive gap và apply throughput.
- Theo dõi Data Guard bằng V$DATAGUARD_STATS, V$ARCHIVE_DEST_STATUS và các view liên quan.
- Hiểu vai trò standby redo logs và real-time apply.
- Dùng Data Guard Broker để xem trạng thái và validate configuration.
- Xử lý transport failure, apply backlog và missing archived log.
- Kiểm chứng block/datafile và dữ liệu logic giữa primary/standby.
- Thiết kế monitoring threshold, alert, failover drill và operational runbook.

> Cú pháp, broker feature và các cột dynamic performance view thay đổi theo Oracle release. Ví dụ dùng Data Guard physical standby phổ biến; kiểm tra Data Guard Concepts and Administration/Database Reference của đúng release, topology RAC/CDB và licensing trước khi áp dụng.

## 1. Data Guard và mục tiêu sẵn sàng cao

### 1.1. Primary và standby

Primary database phục vụ read/write workload và tạo redo cho các thay đổi. Standby database nhận redo từ primary, sau đó apply redo để duy trì trạng thái gần với primary.

Các kiểu standby thường gặp:

- Physical standby: duy trì bản sao vật lý bằng Redo Apply.
- Logical standby: áp dụng SQL tương ứng với redo theo cơ chế SQL Apply, với các giới hạn datatype/feature.
- Snapshot standby: có thể mở read/write tạm thời trong một số kịch bản test, sau đó convert lại physical standby và apply redo tiếp.

Bài học chủ yếu dùng physical standby vì protection mode, transport lag và apply lag thường được vận hành quanh redo transport và Redo Apply.

### 1.2. Data Guard không phải backup

Standby có thể bảo vệ trước một số lỗi host/site và hỗ trợ role transition. Tuy nhiên, thao tác xóa nhầm dữ liệu, lỗi logic hoặc corruption có thể được truyền qua redo tới standby. Vì vậy, Data Guard không thay thế backup độc lập, retention và restore testing.

### 1.3. RPO và RTO

- RPO (Recovery Point Objective): lượng dữ liệu tối đa tổ chức chấp nhận mất khi xảy ra sự cố.
- RTO (Recovery Time Objective): thời gian tối đa để khôi phục dịch vụ.

Protection mode ảnh hưởng RPO khi primary mất đột ngột. Quy trình failover, detection, client reconnect, DNS/service relocation và application recovery ảnh hưởng RTO.

### 1.4. Hai đường đi của redo

```text
PRIMARY DATABASE
      |
      v
Online Redo Log / LGWR
      |
      v
Redo Transport (SYNC hoặc ASYNC)
      |
      v
STANDBY REDO LOG (SRL)
      |
      v
Redo Apply
      |
      v
PHYSICAL STANDBY DATAFILES

Transport lag: redo chưa tới standby
Apply lag: redo tới standby nhưng chưa được apply
```

### 1.5. Sẵn sàng cao là hệ thống nhiều thành phần

Khả năng phục hồi còn phụ thuộc:

- Network giữa primary và standby.
- Storage và I/O latency của cả hai site.
- Standby redo log configuration.
- Redo Apply process và CPU capacity.
- Archive log retention và gap resolution.
- Broker/Clusterware và failover policy.
- Application service, connection pool và client failover.
- Backup, monitoring và người vận hành.

Một protection mode mạnh không thể bù cho standby đã offline, thiếu storage hoặc không có quy trình failover được diễn tập.

## 2. Protection mode và transport mode

### 2.1. Protection mode

Protection mode xác định mục tiêu bảo vệ dữ liệu của primary khi truyền redo tới standby. Ba mode chính:

- Maximum Protection.
- Maximum Availability.
- Maximum Performance.

Mode là chính sách ở cấp database configuration, không chỉ là một tham số network.

### 2.2. Redo transport mode

Redo transport có hai kiểu chính:

- SYNC: primary chờ acknowledgment từ standby theo semantics transport đã cấu hình trước khi xác nhận commit tương ứng.
- ASYNC: primary không chờ standby nhận redo cho mỗi commit; redo được gửi bất đồng bộ.

SYNC và ASYNC là thuộc tính transport destination. Protection mode quy định mức đồng bộ cần đạt và cách primary phản ứng khi standby không đáp ứng.

### 2.3. AFFIRM và NOAFFIRM

AFFIRM yêu cầu standby ghi redo vào standby redo log trước khi xác nhận theo transport semantics. NOAFFIRM cho phép acknowledgment trước khi redo được ghi bền vững vào SRL. Điều này có thể giảm latency, nhưng nếu standby host/storage gặp sự cố ngay sau acknowledgment và trước khi redo được persist, mức bảo vệ có thể khác AFFIRM.

SYNC/AFFIRM có semantics durability mạnh hơn nhưng tăng commit latency do network round trip và standby I/O. SYNC/NOAFFIRM giảm phần chờ ghi disk tại standby nhưng thay đổi mức bảo vệ khi standby gặp sự cố đồng thời trước khi redo được ghi bền vững.

### 2.4. Kết hợp thường gặp

| Protection mode | Transport thường dùng | Ý nghĩa |
| --- | --- | --- |
| Maximum Protection | SYNC AFFIRM | Không xác nhận commit nếu redo chưa được bảo vệ bền vững tại standby đồng bộ; primary dừng nếu không còn standby đáp ứng |
| Maximum Availability | SYNC AFFIRM hoặc SYNC NOAFFIRM tùy cấu hình/release | Ưu tiên không mất dữ liệu khi standby đồng bộ, nhưng primary tiếp tục hoạt động khi mất kết nối standby |
| Maximum Performance | Thường ASYNC NOAFFIRM | Ưu tiên hiệu năng primary; có thể mất redo chưa được chuyển tới standby khi failover |

Đây là cách kết hợp phổ biến, không phải danh sách cấu hình duy nhất được hỗ trợ. Xác nhận yêu cầu cụ thể của protection mode và Oracle release.

### 2.5. Vì sao không thể chỉ nhìn chữ SYNC?

SYNC cho biết primary đợi acknowledgment, nhưng AFFIRM/NOAFFIRM xác định thời điểm standby gửi acknowledgment so với việc ghi redo xuống SRL. Ngoài ra, protection mode và trạng thái standby quyết định database có đang đạt mức protection mong muốn hay không.

### 2.6. Protection mode và protection level

V$DATABASE có:

- PROTECTION_MODE: mode được cấu hình.
- PROTECTION_LEVEL: mức bảo vệ thực tế hiện đạt tại thời điểm quan sát.

Hai giá trị có thể khác nhau. Ví dụ cấu hình Maximum Availability nhưng standby đồng bộ không khả dụng; database có thể tạm hoạt động ở mức thấp hơn. Monitoring phải cảnh báo protection level suy giảm, không chỉ kiểm tra mode cấu hình.

## 3. Maximum Protection

### 3.1. Mục tiêu

Maximum Protection đặt ưu tiên cao nhất vào việc không mất dữ liệu đã commit do primary failure, bằng cách yêu cầu redo được chuyển đồng bộ và bảo vệ theo cấu hình trước khi commit được xác nhận.

Trong cấu hình chuẩn, cần ít nhất một standby đáp ứng SYNC/AFFIRM và phải duy trì standby đồng bộ để primary tiếp tục hoạt động.

### 3.2. Hành vi khi standby mất kết nối

Nếu không còn standby đáp ứng mức bảo vệ yêu cầu, primary sẽ shutdown thay vì tiếp tục commit mà không có bảo vệ tương ứng. Hành vi này bảo vệ RPO nhưng làm giảm availability của primary khi network/standby gặp sự cố.

### 3.3. Đánh đổi

Ưu điểm:

- Mức bảo vệ dữ liệu cao nhất trong các protection mode chuẩn.
- Giảm nguy cơ mất transaction đã commit khi primary gặp sự cố, nếu standby synchronous và hạ tầng đáp ứng semantics cấu hình.

Nhược điểm:

- Primary có thể dừng khi standby/network không sẵn sàng.
- Commit latency chịu ảnh hưởng network round trip và standby I/O.
- Cần thiết kế network, standby và storage có độ tin cậy cao.
- Không phù hợp nếu ưu tiên uptime primary hơn RPO gần bằng 0.

### 3.4. Khi nào dùng?

Chỉ dùng khi business yêu cầu bảo vệ dữ liệu rất nghiêm ngặt và chấp nhận primary ngừng phục vụ nếu standby synchronous không đáp ứng. Phải có standby site/network đủ tin cậy, monitoring và runbook phục hồi nhanh.

### 3.5. Maximum Protection không thay backup

Maximum Protection không bảo vệ khỏi mọi lỗi logic, thao tác xóa nhầm được redo replicate, corruption logic hoặc mất toàn bộ các bản sao cùng failure domain. Vẫn cần backup độc lập, immutable/offsite copy và kiểm thử restore.

## 4. Maximum Availability

### 4.1. Mục tiêu

Maximum Availability hướng tới không mất dữ liệu trong điều kiện standby synchronous khả dụng, nhưng ưu tiên giữ primary tiếp tục hoạt động nếu standby hoặc network tạm thời mất kết nối.

### 4.2. Khi standby synchronous hoạt động

Khi standby synchronous đáp ứng, commit được phối hợp với redo transport theo cấu hình SYNC. Với SYNC/AFFIRM, acknowledgment phụ thuộc redo đã được ghi bền vững vào standby redo log.

### 4.3. Khi standby/network không khả dụng

Primary có thể tiếp tục xử lý transaction thay vì shutdown. Trong khoảng thời gian không đồng bộ, protection level có thể suy giảm và nếu primary cũng gặp sự cố trước khi redo được chuyển, có thể mất phần redo chưa tới standby.

Vì vậy, Maximum Availability không phải cam kết tuyệt đối zero data loss trong mọi trạng thái lỗi. Điều kiện synchronous protection phải được phục hồi và monitoring phải phát hiện thời gian suy giảm.

### 4.4. Đánh đổi

Ưu điểm:

- Khi standby synchronous khỏe, mức bảo vệ dữ liệu rất cao.
- Primary có thể tiếp tục phục vụ khi standby/network tạm mất.
- Thường cân bằng tốt giữa RPO và availability cho production.

Nhược điểm:

- Commit latency cao hơn ASYNC.
- Khi standby bị gián đoạn, RPO thực tế tạm thời không còn như lúc đồng bộ.
- Phải giám sát protection level và thời gian không đồng bộ.

### 4.5. Khi nào dùng?

Phù hợp với hệ thống yêu cầu RPO rất thấp nhưng không muốn primary tự dừng ngay khi standby mất kết nối tạm thời. Cần định nghĩa rõ thời gian chấp nhận degraded protection và quy trình xử lý khi vượt ngưỡng.

## 5. Maximum Performance

### 5.1. Mục tiêu

Maximum Performance ưu tiên hiệu năng và availability của primary. Redo thường được truyền ASYNC để commit không phải chờ standby nhận redo.

### 5.2. Hành vi

Primary có thể xác nhận commit trước khi redo tương ứng tới standby. Nếu primary gặp sự cố, standby có thể thiếu phần redo cuối cùng chưa được truyền/nhận/apply.

### 5.3. Đánh đổi

Ưu điểm:

- Commit latency ít phụ thuộc round trip tới standby.
- Primary tiếp tục hoạt động khi standby/network gián đoạn.
- Phù hợp khoảng cách địa lý lớn hoặc workload nhạy latency.

Nhược điểm:

- Có thể mất dữ liệu mới nhất khi failover.
- RPO phụ thuộc transport lag và redo chưa được bảo vệ ở standby.
- Phải có monitoring lag và quyết định failover dựa trên data-loss exposure.

### 5.4. Khi nào dùng?

Phù hợp khi hiệu năng/availability primary được ưu tiên và business chấp nhận RPO khác zero. Cần định lượng mức mất dữ liệu tối đa chấp nhận được và bảo đảm lag alert/response hoạt động.

### 5.5. Không đồng nghĩa “không an toàn”

Maximum Performance có thể là lựa chọn đúng nếu RPO được chấp nhận và standby được giám sát. Vấn đề là vận hành không biết lag hoặc không kiểm thử failover, chứ không phải ASYNC luôn sai.

## 6. So sánh protection mode theo RPO/RTO

### 6.1. Bảng lựa chọn

| Tiêu chí | Maximum Protection | Maximum Availability | Maximum Performance |
| --- | --- | --- | --- |
| Ưu tiên | Bảo vệ dữ liệu cao nhất | Cân bằng bảo vệ và availability | Hiệu năng/availability primary |
| Transport điển hình | SYNC AFFIRM | SYNC AFFIRM/NOAFFIRM theo thiết kế | ASYNC |
| Commit chờ standby | Có | Có khi synchronous standby hoạt động | Không chờ mỗi commit |
| Khi standby mất | Primary shutdown nếu không còn standby đủ điều kiện | Primary tiếp tục, protection có thể giảm | Primary tiếp tục |
| Data loss khi primary fail | Tránh trong điều kiện mode/standby đáp ứng | Tránh khi standby đồng bộ; có thể có trong thời gian degraded | Có thể mất redo chưa được chuyển |
| Latency | Cao nhất thường gặp | Cao hơn ASYNC khi sync active | Thấp hơn do không đợi sync ack |

### 6.2. RPO không chỉ là một protection mode

RPO thực tế còn phụ thuộc:

- Transport lag tại thời điểm lỗi.
- Redo đã được nhận hay chỉ nằm trên network.
- Standby redo log đã được ghi bền vững hay chưa.
- Apply lag và khả năng standby mở read/write sau failover.
- Có thể lấy phần redo cuối từ primary/online redo log hay không.
- Kiểu failure: primary process, host, site, network hay storage.

### 6.3. RTO không được quyết định bởi protection mode một mình

RTO còn phụ thuộc detection, failover decision, broker/observer, startup/recovery, service relocation, DNS/network và application reconnect. Một hệ thống Maximum Protection vẫn có thể có RTO dài nếu không có quy trình failover nhanh.

### 6.4. Xây dựng service-level objective

Ví dụ mục tiêu vận hành:

| Mục tiêu | Chỉ số |
| --- | --- |
| RPO | Data loss tối đa được business chấp nhận |
| RTO | Thời gian từ incident tới service healthy |
| Transport lag | Độ trễ redo chưa nhận |
| Apply lag | Độ trễ redo chưa apply |
| Protection level | Mức bảo vệ thực tế hiện đạt |
| Availability | Tỷ lệ thời gian service sẵn sàng |

Đặt threshold theo workload và SLA, không sao chép ngưỡng từ hệ thống khác.

## 7. SYNC, ASYNC, AFFIRM và NOAFFIRM

### 7.1. SYNC

SYNC yêu cầu primary đợi phản hồi từ destination synchronous theo semantics redo transport. Điều này đưa network latency và standby write latency vào commit path.

Nếu primary cách standby xa, round-trip latency có thể làm tăng thời gian commit. Thiết kế vị trí standby, network path, bandwidth và QoS ảnh hưởng trực tiếp trải nghiệm OLTP.

### 7.2. ASYNC

ASYNC gửi redo bất đồng bộ. Primary không chờ acknowledgment của standby cho mỗi commit, nhờ đó giảm ảnh hưởng network latency lên commit.

Nếu redo generation nhanh hơn transport throughput, transport lag tăng. Khi primary fail trước khi redo backlog được gửi, phần chưa tới standby có thể bị mất trong failover.

### 7.3. AFFIRM

AFFIRM yêu cầu standby ghi redo vào standby redo log trước khi xác nhận theo transport semantics. Nó tăng bảo đảm redo đã được ghi bền vững trên standby storage, nhưng làm commit chờ cả network và standby I/O.

### 7.4. NOAFFIRM

NOAFFIRM cho phép acknowledgment trước khi redo được ghi bền vững vào SRL. Điều này có thể giảm latency, nhưng nếu standby host/storage gặp sự cố ngay sau acknowledgment và trước khi redo được persist, mức bảo vệ có thể khác AFFIRM.

### 7.5. Ví dụ LOG_ARCHIVE_DEST_n

Ví dụ cấu hình destination synchronous:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_2 =
  'SERVICE=stby_sync
   SYNC AFFIRM
   VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE)
   DB_UNIQUE_NAME=STBY'
  SCOPE=BOTH;
```

Ví dụ destination asynchronous:

```sql
ALTER SYSTEM SET LOG_ARCHIVE_DEST_2 =
  'SERVICE=stby_async
   ASYNC NOAFFIRM
   VALID_FOR=(ONLINE_LOGFILES,PRIMARY_ROLE)
   DB_UNIQUE_NAME=STBY'
  SCOPE=BOTH;
```

Đây là cú pháp minh họa. Tên service, DB_UNIQUE_NAME, NET_TIMEOUT, REOPEN, MAX_FAILURE, compression, encryption và các attribute phải theo thiết kế thực tế. Không ghi đè destination đang dùng bởi Data Guard Broker nếu Broker quản lý cấu hình.

### 7.6. NET_TIMEOUT

NET_TIMEOUT xác định thời gian chờ phản hồi redo transport synchronous trước khi xử lý timeout theo cơ chế Oracle. Giá trị quá thấp có thể gây timeout giả khi network jitter; quá cao làm phát hiện lỗi chậm và kéo dài commit/session wait.

Chọn timeout dựa trên latency phân vị cao, network SLA và failure detection objective; kiểm tra semantics đúng release.

### 7.7. Bandwidth và redo generation

ASYNC không loại bỏ nhu cầu bandwidth. Nếu average/peak redo generation lớn hơn throughput network ổn định, transport backlog sẽ tích lũy. SYNC cũng cần bandwidth đủ để giữ latency thấp; nếu link bị saturation, commit latency tăng.

Đo redo bytes/sec, network throughput, packet loss, retransmission và latency theo giờ cao điểm.

## 8. Standby redo logs (SRL)

### 8.1. Vai trò

Standby redo logs nhận redo từ primary trước khi redo được archive tại standby. Với real-time apply, Redo Apply có thể đọc redo đang được ghi vào SRL, giảm độ trễ so với chờ log được archive xong.

### 8.2. SRL và archived log

SRL là log group dành cho standby để nhận redo stream. Khi một SRL đầy/được switch, nó được archive thành archived redo log trên standby. SRL không phải bản backup và không thay thế archive log retention.

### 8.3. Sizing và số lượng

Nguyên tắc cấu hình thường dùng:

- Mỗi redo thread cần đủ SRL group cho transport và log switch.
- Oracle khuyến nghị số SRL group mỗi thread nhiều hơn số online redo log group tương ứng ít nhất một group.
- Kích thước SRL phải bằng hoặc lớn hơn kích thước online redo log lớn nhất của thread.
- Với RAC, tạo SRL cho từng thread cần hỗ trợ trên standby, không chỉ thread của instance hiện tại.

Kiểm tra Oracle Data Guard documentation cho số lượng chính xác trong topology và release.

### 8.4. Kiểm tra SRL

```sql
SELECT
    thread#,
    group#,
    sequence#,
    bytes,
    archived,
    status
FROM v$standby_log
ORDER BY thread#, group#;
```

So sánh với online redo logs trên primary:

```sql
SELECT
    thread#,
    group#,
    sequence#,
    bytes,
    members,
    archived,
    status
FROM v$log
ORDER BY thread#, group#;
```

### 8.5. Real-time apply

Real-time apply cho phép standby apply redo từ SRL trong khi redo vẫn đang được nhận, thay vì đợi archive log hoàn tất. Cấu hình và cú pháp bật apply thay đổi theo release; các phiên bản mới thường tự dùng real-time apply khi SRL hiện diện và điều kiện phù hợp. Các bản cũ có thể dùng USING CURRENT LOGFILE.

Ví dụ thường gặp để bắt đầu managed recovery:

```sql
ALTER DATABASE RECOVER MANAGED STANDBY DATABASE
  DISCONNECT FROM SESSION;
```

Không thêm/bỏ USING CURRENT LOGFILE theo thói quen; xác nhận release và trạng thái Broker. Với Broker-managed database, điều khiển apply qua Broker sẽ nhất quán hơn.

### 8.6. Kiểm tra Redo Apply process

```sql
SELECT
    name,
    role,
    action,
    thread#,
    sequence#
FROM v$dataguard_process
ORDER BY name;
```

V$DATAGUARD_PROCESS là view được dùng trên các release hiện đại để xem Data Guard processes. Một số bản cũ dùng V$MANAGED_STANDBY; kiểm tra view được hỗ trợ trên phiên bản.

### 8.7. SRL thiếu hoặc sai kích thước

Thiếu SRL có thể ngăn real-time apply hoặc làm transport behavior không đạt thiết kế. SRL nhỏ hơn online redo log có thể gây vấn đề khi nhận log lớn hơn. Kiểm tra từng thread và tạo group phù hợp trong maintenance window.

## 9. Transport lag

### 9.1. Định nghĩa

Transport lag mô tả độ trễ giữa thời điểm redo được tạo trên primary và thời điểm redo tương ứng được nhận tại standby. Nếu primary tiếp tục sinh redo nhưng standby không nhận kịp, transport lag tăng.

Transport lag thường liên quan:

- Network latency, packet loss hoặc bandwidth saturation.
- Listener/service hoặc redo transport connection bị lỗi.
- Standby không ghi nhận redo vào SRL/archive destination.
- Primary tạo redo đột biến vượt khả năng truyền.
- Standby destination/storage không sẵn sàng.

### 9.2. Transport lag khác archive gap

Transport lag là độ trễ thời gian/redo giữa primary và standby. Archive gap là thiếu một hoặc nhiều archived log sequence cần thiết để tiếp tục recovery/apply. Gap có thể làm apply dừng; transport lag có thể tăng khi transport bị nghẽn dù chưa có gap được ghi nhận rõ.

### 9.3. Xem V$DATAGUARD_STATS

Trên standby:

```sql
SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN (
    'transport lag',
    'apply lag',
    'apply finish time',
    'estimated startup time'
)
ORDER BY name;
```

VALUE thường được biểu diễn dạng thời gian. TIME_COMPUTED cho biết lúc metric được tính; DATUM_TIME liên quan mốc dữ liệu redo nhận được từ primary. Nếu DATUM_TIME không tiến triển qua nhiều lần polling, standby có thể không nhận redo mới hoặc dữ liệu metric không được cập nhật.

### 9.4. Xem destination ở primary

```sql
SELECT
    dest_id,
    status,
    type,
    database_mode,
    recovery_mode,
    protection_mode,
    destination,
    error
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Đối chiếu với V$ARCHIVE_DEST để xem attribute destination và cấu hình. Cột có thể khác theo release; chọn các cột có trong phiên bản đang chạy.

### 9.5. Kiểm tra archive gap trên standby

```sql
SELECT
    thread#,
    low_sequence#,
    high_sequence#
FROM v$archive_gap;
```

V$ARCHIVE_GAP thường cho biết gap đang chặn recovery hiện tại. Không có row không chứng minh toàn bộ archive history đều đầy đủ; nó chỉ phản ánh gap được view xác định ở thời điểm truy vấn.

### 9.6. Đọc lag theo thời gian

Một giá trị lag bằng 0 tại một lần polling không chứng minh standby luôn đồng bộ. Thu thập chuỗi metric có timestamp, theo dõi peak, thời gian degraded và tốc độ hồi phục sau burst.

### 9.7. Phân biệt network delay và redo backlog

Nếu transport lag tăng đồng thời network throughput/latency xấu, điều tra link và transport process. Nếu network ổn định nhưng redo generation tăng đột biến, tính lại bandwidth và transport capacity. Nếu primary báo destination error, kiểm tra service, authentication, TNS, listener và standby storage.

## 10. Apply lag

### 10.1. Định nghĩa

Apply lag mô tả khoảng thời gian redo đã được nhận tại standby nhưng chưa được apply vào standby datafiles, so với thời điểm tương ứng trên primary. Apply lag có thể tăng dù transport lag gần bằng 0.

### 10.2. Nguyên nhân phổ biến

- Redo Apply throughput thấp hơn redo generation rate.
- Standby thiếu CPU hoặc storage IOPS.
- Datafile write latency cao.
- SQL Apply/Redo Apply bị dừng hoặc lỗi.
- Recovery process bị nghẽn bởi contention hoặc workload read-only.
- Archive gap khiến apply không thể tiếp tục.
- Standby đang thực hiện workload reporting gây tranh chấp CPU/I/O.

### 10.3. Apply lag và transport lag cùng tăng

Nếu cả hai tăng, trước hết điều tra transport. Standby chưa nhận redo mới thì apply không thể theo kịp. Khi transport phục hồi, apply có thể cần thêm thời gian để xử lý backlog.

### 10.4. Transport lag thấp, apply lag cao

Đây thường là dấu hiệu redo đã tới standby nhưng apply chậm. Kiểm tra apply process, CPU, I/O, SRL/archive log, gap và standby workload. Tăng network bandwidth sẽ không giải quyết bottleneck nếu transport đã theo kịp.

### 10.5. Apply finish time

V$DATAGUARD_STATS có thể cung cấp apply finish time, là ước lượng thời gian cần để apply redo đã nhận tới thời điểm metric được tính. Đây là estimate thay đổi theo backlog và throughput, không phải SLA đảm bảo.

### 10.6. Đo xu hướng

Theo dõi:

- Apply lag theo thời gian.
- Redo generation rate trên primary.
- Apply throughput trên standby.
- CPU utilization và I/O latency.
- Archive gap và trạng thái recovery process.
- Workload read-only/backup chạy trên standby.

Nếu backlog tăng liên tục, standby capacity không theo kịp primary workload.

## 11. Monitoring lag và redo throughput

### 11.1. Lấy snapshot định kỳ

Thu thập V$DATAGUARD_STATS ở standby theo chu kỳ ngắn phù hợp với SLA, ví dụ mỗi 30–60 giây. Ghi timestamp của lần lấy dữ liệu ở hệ thống monitoring để tính duration và trend.

### 11.2. Transport destination ở primary

```sql
SELECT
    dest_id,
    status,
    destination,
    error,
    synchronization_status,
    db_unique_name
FROM v$archive_dest_status
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Một số cột trạng thái đồng bộ có thể khác theo release. Nếu câu truy vấn không tương thích, kiểm tra DESC V$ARCHIVE_DEST_STATUS và chọn cột được hỗ trợ. Không bỏ qua ERROR chỉ vì STATUS hiện VALID.

### 11.3. Redo generation rate

Có thể ước lượng redo bytes sinh ra từ thống kê system:

```sql
SELECT
    name,
    value
FROM v$sysstat
WHERE name IN (
    'redo size',
    'redo entries',
    'redo writes'
);
```

Lấy hai snapshot cách nhau một khoảng thời gian để tính delta redo size/second. Reset instance, counter reset hoặc thay đổi thời gian phải được xử lý khi tính.

### 11.4. Log switch rate

```sql
SELECT
    thread#,
    COUNT(*) AS switches,
    MIN(first_time) AS first_switch,
    MAX(first_time) AS last_switch
FROM v$log_history
WHERE first_time >= SYSDATE - 1/24
GROUP BY thread#
ORDER BY thread#;
```

Log switch rate cao có thể tăng số archive files và áp lực archiver/standby. Cân nhắc redo log size, workload batch và transaction rate trước khi thay đổi log size.

### 11.5. Lịch sử lag

```sql
SELECT
    name,
    time,
    unit,
    count,
    last_time_updated
FROM v$standby_event_histogram
WHERE name IN ('transport lag', 'apply lag')
ORDER BY name, time;
```

View histogram có thể không có dữ liệu ở mọi release/configuration. Nó giúp xem phân bố các khoảng lag đã ghi nhận, không thay thế chuỗi time-series monitoring bên ngoài.

### 11.6. Data Guard process

```sql
SELECT
    name,
    role,
    action,
    thread#,
    sequence#,
    block#,
    blocks
FROM v$dataguard_process
ORDER BY name;
```

Xem process có hoạt động, chờ, hoặc xử lý sequence nào. Tên process và action có thể thay đổi theo release; đọc cùng alert log và broker status.

### 11.7. Alert log và status messages

```sql
SELECT
    timestamp,
    severity,
    message
FROM v$dataguard_status
WHERE timestamp > SYSTIMESTAMP - INTERVAL '2' HOUR
ORDER BY timestamp;
```

V$DATAGUARD_STATUS ghi các message liên quan Data Guard. Kết hợp với alert log để tìm lỗi network, gap, apply stopped hoặc destination error.

## 12. Đặt threshold và cảnh báo lag

### 12.1. Không dùng một ngưỡng cho mọi database

Một hệ thống OLTP RPO thấp có thể cần threshold vài giây; hệ thống reporting ở khoảng cách xa có thể chấp nhận lag dài hơn. Ngưỡng phải xuất phát từ RPO, RTO, redo generation và khả năng recovery.

### 12.2. Cảnh báo theo nhiều mức

Ví dụ mô hình:

| Mức | Điều kiện minh họa | Hành động |
| --- | --- | --- |
| Notice | Lag tăng nhẹ trong thời gian ngắn | Ghi nhận trend |
| Warning | Lag vượt SLA cảnh báo trong nhiều lần polling | Kiểm tra transport/apply và capacity |
| Critical | Lag vượt RPO budget hoặc tăng liên tục | Escalate DBA/on-call, đánh giá failover exposure |
| Recovery | Lag giảm về dưới ngưỡng ổn định | Xác nhận backlog đã được xử lý |

Các giá trị thực tế phải do owner hệ thống xác định. Dùng hysteresis để tránh alert flapping khi metric dao động quanh ngưỡng.

### 12.3. Alert theo protection level

Ngoài lag, cảnh báo khi PROTECTION_LEVEL thấp hơn mức business yêu cầu hoặc destination synchronous không còn synchronized. Đây là dấu hiệu quan trọng trong Maximum Protection/Availability.

### 12.4. Phân biệt stale metric với lag bằng 0

Nếu DATUM_TIME không cập nhật, không coi VALUE bằng 0 là standby khỏe. Alert nên kiểm tra tuổi của datum/time_computed cùng giá trị lag.

### 12.5. Alert theo backlog growth

Một lag 30 giây đang giảm có thể ít nguy hiểm hơn lag 10 giây nhưng tăng liên tục. Theo dõi slope:

- Lag hiện tại.
- Lag lớn nhất trong window.
- Delta lag theo phút.
- Thời gian vượt threshold liên tục.
- Redo generation và apply throughput.

## 13. Phân tích transport bottleneck

### 13.1. Network

Kiểm tra latency, packet loss, retransmission, bandwidth, routing, firewall timeout và network congestion. Với SYNC, round-trip latency ảnh hưởng trực tiếp commit. Với ASYNC, bandwidth không đủ làm backlog tích lũy.

### 13.2. Service và kết nối

Kiểm tra TNS alias/service, listener, authentication, password file, DB_UNIQUE_NAME và LOG_ARCHIVE_DEST_n. Nếu Broker quản lý Data Guard, kiểm tra cấu hình qua Broker trước khi sửa tham số trực tiếp.

### 13.3. Standby storage

Redo transport có thể bị chậm nếu SRL storage latency cao hoặc archive destination không ghi được. Kiểm tra I/O latency, ASM disk group, filesystem, space và alert log.

### 13.4. Redo generation spike

Batch update, index rebuild, bulk load, ETL hoặc maintenance có thể tạo redo đột biến. So sánh redo bytes/sec với network throughput và archive generation. Có thể cần điều chỉnh lịch batch, tăng bandwidth hoặc cải thiện transport architecture.

### 13.5. Transport process

Kiểm tra Data Guard process state, destination error và broker warnings. Không kill LNS/ARCn process để “reset lag”; tìm nguyên nhân transport trước và dùng lệnh quản trị Data Guard phù hợp.

### 13.6. Far Sync

Far Sync instance có thể nhận redo đồng bộ gần primary rồi forward tới remote standby bất đồng bộ, giảm ảnh hưởng WAN latency lên primary trong một số kiến trúc. Far Sync không phải database standby có datafiles đầy đủ để mở như physical standby; nó là thành phần redo transport. Cần thiết kế availability và protection semantics riêng.

## 14. Phân tích apply bottleneck

### 14.1. Redo Apply process

Xác nhận managed recovery đang chạy và không có error. Với Broker, xem apply state và broker log. Với SQL-managed configuration, kiểm tra V$DATAGUARD_PROCESS và alert log.

### 14.2. CPU

Apply có thể bị giới hạn CPU khi redo rate cao, nhiều block thay đổi hoặc workload standby cạnh tranh CPU. Kiểm tra host CPU, run queue, Oracle process utilization và apply throughput.

### 14.3. I/O

Standby cần ghi datafile blocks và đọc redo/archive logs. Storage latency cao, queue depth, ASM contention hoặc shared storage bận có thể làm apply chậm.

### 14.4. Standby read workload

Nếu physical standby mở read-only với Active Data Guard, reporting query có thể cạnh tranh CPU/I/O với Redo Apply. Theo dõi resource usage và cân nhắc Resource Manager, giới hạn workload hoặc chuyển report sang thời điểm khác.

### 14.5. Parallel Redo Apply

Một số release hỗ trợ parallel apply và tự điều chỉnh mức parallelism. Việc tăng parallelism không luôn tăng throughput nếu storage/CPU đã bão hòa hoặc workload có phụ thuộc tuần tự. Đo trước/sau và dùng tham số/command được hỗ trợ của release.

### 14.6. Gap và apply stop

Nếu thiếu archived log, apply có thể dừng dù CPU/I/O còn dư. Kiểm tra V$ARCHIVE_GAP và Data Guard status trước khi tăng resource.

### 14.7. Apply rate và redo rate

Ước lượng backlog:

```text
Redo generated: 80 MB/s
Redo received: 80 MB/s
Redo applied: 55 MB/s

Backlog grows by approximately 25 MB/s
```

Đây là ví dụ số học. Nếu apply throughput luôn thấp hơn redo generation, apply lag sẽ tăng cho tới khi workload giảm hoặc capacity được cải thiện.

## 15. Archive gap và xử lý gap

### 15.1. Gap là gì?

Gap là một đoạn redo còn thiếu trong chuỗi cần thiết cho standby apply. Gap có thể do network interruption, archive log bị xóa sớm, destination lỗi, storage mất file hoặc log không được backup/chuyển đúng.

### 15.2. Xác định gap

Trên standby:

```sql
SELECT thread#, low_sequence#, high_sequence#
FROM v$archive_gap;
```

Trên primary kiểm tra V$ARCHIVED_LOG để xác định các sequence tương ứng còn tồn tại hay không. Với RAC, xác định đúng thread.

### 15.3. Automatic gap resolution

Data Guard có cơ chế fetch missing archived logs từ primary khi cấu hình và file còn sẵn. FAL (Fetch Archive Log) và các cơ chế transport hiện đại hỗ trợ xử lý gap. Không phải gap nào cũng tự giải quyết nếu log nguồn đã bị xóa hoặc destination không thể truy cập.

### 15.4. Manual gap resolution

Nếu tự động fetch không thành công:

1. Xác định DBID/incarnation, thread và sequence bị thiếu.
2. Tìm archive file ở primary, FRA, backup hoặc standby copy khác.
3. Chuyển file tới vị trí standby có thể đọc.
4. Catalog/register log theo quy trình của release.
5. Khởi động lại hoặc tiếp tục Redo Apply.
6. Xác nhận gap đã biến mất và apply lag giảm.

Không copy file có cùng sequence nhưng thuộc incarnation khác.

### 15.5. Khi archive log không còn

Nếu không thể tìm được redo cần thiết, standby có thể cần incremental roll-forward từ primary hoặc rebuild/recreate standby theo Data Guard procedure. Chọn phương án dựa trên gap size, backup availability, downtime và release.

### 15.6. Không bỏ qua gap tùy tiện

Không đăng ký archived log khác sequence để làm recovery tiến tiếp, không reset standby chỉ để xóa trạng thái lỗi và không mở standby read/write ngoài quy trình. Xử lý phải bảo toàn tính nhất quán redo.

## 16. Data Guard Broker

### 16.1. Vai trò

Data Guard Broker quản lý configuration, database members, redo transport, apply state, switchover/failover và observer/FSFO khi được cấu hình. Broker cung cấp một giao diện quản trị nhất quán thay vì thay đổi nhiều tham số trực tiếp.

### 16.2. Kết nối DGMGRL

```text
dgmgrl /
```

Hoặc dùng kết nối bảo mật theo chính sách DBA. Không lưu credential dạng rõ trong script.

### 16.3. Xem configuration

```text
SHOW CONFIGURATION;
SHOW CONFIGURATION VERBOSE;
```

Output cho biết configuration status, protection mode và warning/error tổng thể.

### 16.4. Xem từng database

```text
SHOW DATABASE VERBOSE 'PRIMARY_DB';
SHOW DATABASE VERBOSE 'STANDBY_DB';
```

Thay bằng DB_UNIQUE_NAME thực tế. Xem transport/apply state, lag, properties và lỗi.

### 16.5. Validate configuration

Broker có lệnh VALIDATE DATABASE và VALIDATE NETWORK CONFIGURATION ở các release hỗ trợ. Dùng cú pháp đúng release để kiểm tra prerequisite, static connect identifier, redo transport, SRL và readiness cho role transition.

Validation thành công là bằng chứng cấu hình đáp ứng các kiểm tra Broker thực hiện; nó không thay thế restore test, data comparison hoặc failover drill thực tế.

### 16.6. Thay đổi protection mode qua Broker

Trong môi trường Broker-managed, thay protection mode qua DGMGRL theo cú pháp release, ví dụ:

```text
EDIT CONFIGURATION SET PROTECTION MODE AS MAXAVAILABILITY;
```

Các mode Broker thường có tên MAXPROTECTION, MAXAVAILABILITY và MAXPERFORMANCE. Trước khi đổi, kiểm tra synchronous standby, transport attributes, availability và yêu cầu restart/state. Không chạy ví dụ trực tiếp nếu configuration chưa đáp ứng prerequisite.

### 16.7. Broker và SQL parameter trực tiếp

Nếu Broker quản lý configuration, thay LOG_ARCHIVE_DEST_n trực tiếp có thể làm Broker state khác với ý định vận hành hoặc bị Broker ghi đè. Dùng Broker làm source of truth cho cấu hình được Broker quản lý; chỉ sửa SQL parameter trực tiếp theo runbook và đồng bộ lại Broker.

## 17. Kiểm tra protection mode và trạng thái database

### 17.1. V$DATABASE

Trên primary:

```sql
SELECT
    name,
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    protection_level,
    switchover_status
FROM v$database;
```

Protection mode cho biết mục tiêu cấu hình; protection level cho biết mức đạt được hiện tại. Đưa cả hai vào dashboard.

### 17.2. Archive destination

Trên primary:

```sql
SELECT
    dest_id,
    status,
    target,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE'
ORDER BY dest_id;
```

Đối chiếu destination tương ứng standby và status/error. Một destination VALID không nhất thiết chứng minh apply đang theo kịp.

### 17.3. Standby database role/open mode

Trên standby:

```sql
SELECT
    name,
    database_role,
    open_mode,
    protection_mode,
    protection_level,
    switchover_status
FROM v$database;
```

Physical standby có thể ở MOUNTED hoặc READ ONLY WITH APPLY tùy cấu hình/licensing. Xác nhận trạng thái phù hợp với workload và release.

### 17.4. Managed recovery state

Kiểm tra V$DATAGUARD_PROCESS và Broker. Nếu không có apply process, xác định nó bị stop có chủ đích, đang restart hay gặp lỗi. Không chỉ nhìn open_mode để suy ra Redo Apply đang chạy.

## 18. Kiểm chứng redo và trạng thái apply

### 18.1. Xác nhận archived logs đã nhận

Trên standby:

```sql
SELECT
    thread#,
    sequence#,
    first_change#,
    next_change#,
    first_time,
    next_time,
    applied,
    deleted,
    status,
    name
FROM v$archived_log
ORDER BY thread#, sequence#;
```

V$ARCHIVED_LOG có thể chứa nhiều record cho cùng sequence do nhiều destination/copy. Phân biệt log đã nhận, đã archive, đã apply và bản copy đã bị xóa theo metadata.

### 18.2. APPLIED status

Trên physical standby, cột APPLIED trong V$ARCHIVED_LOG cho biết trạng thái apply theo metadata của archived log. Giá trị và cách diễn giải cần theo release; thường thấy YES, NO hoặc IN-MEMORY. IN-MEMORY có nghĩa redo đã được apply trong memory theo cơ chế real-time apply nhưng chưa nhất thiết đã được archive/apply theo cách thể hiện YES.

Không chỉ đếm số dòng APPLIED='YES'. Cần xem thread/sequence, SRL hiện hành, gap và apply lag.

### 18.3. Kiểm tra current apply sequence

Kết hợp V$DATAGUARD_PROCESS, V$ARCHIVED_LOG và V$DATAGUARD_STATS để xác định sequence đang được xử lý và độ trễ. Các process có thể đang apply SRL nên sequence hiện hành chưa xuất hiện như archived log hoàn tất.

### 18.4. Xác nhận không có gap hiện tại

```sql
SELECT * FROM v$archive_gap;
```

Không có row là dấu hiệu không có gap đang chặn recovery được view báo cáo tại thời điểm truy vấn. Vẫn cần kiểm tra lag, process state và redo continuity.

### 18.5. Kiểm tra redo transport messages

```sql
SELECT
    timestamp,
    severity,
    message
FROM v$dataguard_status
WHERE severity IN ('Error', 'Fatal', 'Warning')
ORDER BY timestamp DESC;
```

Nếu view không có cột hoặc severity khác trên release, dùng DESC và lọc theo schema thực tế. Giữ alert log làm nguồn chẩn đoán bổ sung.

## 19. Kiểm chứng block và datafile

### 19.1. Physical consistency

Physical standby duy trì các block bằng redo apply. Để kiểm chứng file/block, DBA có thể dùng RMAN VALIDATE, DBVERIFY, V$DATABASE_BLOCK_CORRUPTION và datafile header metadata.

### 19.2. RMAN VALIDATE

Ví dụ:

```text
RMAN> VALIDATE DATABASE;
RMAN> VALIDATE CHECK LOGICAL DATABASE;
```

VALIDATE kiểm tra khả năng đọc và phát hiện một số dạng block corruption. CHECK LOGICAL bổ sung kiểm tra logical block integrity. Các lệnh có thể tạo I/O lớn; chọn thời điểm và phạm vi phù hợp.

### 19.3. V$DATABASE_BLOCK_CORRUPTION

```sql
SELECT
    file#,
    block#,
    blocks,
    corruption_type,
    corruption_change#
FROM v$database_block_corruption
ORDER BY file#, block#;
```

View ghi nhận các block corruption Oracle đã phát hiện. Không có row không chứng minh toàn bộ datafile đã được đọc/validate; cần chạy validation thích hợp.

### 19.4. Datafile header

```sql
SELECT
    file#,
    status,
    error,
    recover,
    fuzzy,
    checkpoint_change#,
    checkpoint_time
FROM v$datafile_header
ORDER BY file#;
```

Trên standby đang lag, checkpoint/SCN có thể thấp hơn primary. Không yêu cầu header SCN của primary và standby luôn bằng nhau trong lúc redo đang được truyền/apply; cần xét apply state và target consistency.

### 19.5. RMAN validation trên standby

Khả năng và phạm vi validate phụ thuộc database role, open mode, release và quyền. Có thể thực hiện validation trên primary, standby hoặc bản clone phù hợp, nhưng phải xác nhận lệnh được hỗ trợ cho trạng thái hiện tại và kiểm soát I/O. Không chạy validation nặng đồng thời với workload peak nếu ảnh hưởng apply.

### 19.6. Block repair

Một số cấu hình Active Data Guard hỗ trợ automatic block media recovery: khi standby phát hiện block corruption, có thể lấy block tốt từ primary và sửa. Khả năng này phụ thuộc licensing, network, cấu hình và loại corruption. Không coi cơ chế này là thay thế backup hoặc validation định kỳ.

## 20. Kiểm chứng dữ liệu logic

### 20.1. Vì sao kiểm tra redo status chưa đủ?

Redo Apply không báo lỗi và apply lag thấp là bằng chứng mạnh về trạng thái đồng bộ physical standby, nhưng không trả lời mọi câu hỏi nghiệp vụ. DBA có thể cần xác nhận các bảng quan trọng, row count, khóa, tổng tiền hoặc các quy tắc nghiệp vụ sau migration/upgrade/role transition.

### 20.2. So sánh theo cùng một mốc dữ liệu

Khi so sánh primary và standby, cần xác định standby đã apply tới mốc redo tương ứng. Nếu primary vẫn ghi dữ liệu trong lúc lấy số liệu hai bên, kết quả có thể khác chỉ vì thời điểm snapshot khác nhau.

Các cách kiểm soát:

- Tạm dừng/đóng băng ghi trong maintenance window nếu nghiệp vụ cho phép.
- Chọn một SCN/restore point và so sánh dữ liệu theo cùng snapshot nếu object/undo retention hỗ trợ.
- Đợi standby apply tới mốc đã ghi nhận rồi mới so sánh.
- Dùng DBMS_COMPARISON hoặc quy trình đối soát có khóa/chia partition phù hợp.

Không so sánh hai query chạy ở hai thời điểm khác nhau rồi kết luận Data Guard sai.

### 20.3. Row count và aggregate

Các kiểm tra như COUNT(*), MIN/MAX key, SUM(amount) và count theo partition hữu ích để phát hiện chênh lệch lớn:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    SUM(total_amount) AS total_amount
FROM orders;
```

Chạy cùng snapshot/SCN ở primary và standby. Những con số tổng hợp không chứng minh từng row giống nhau; hai tập khác nhau có thể có cùng count hoặc sum.

### 20.4. Hash/checksum

Có thể tính hash theo key/partition để giảm dữ liệu phải truyền khi đối soát. Thiết kế hash phải:

- Bao gồm mọi cột có ý nghĩa nghiệp vụ.
- Chuẩn hóa NULL, datatype, timezone, collation và numeric format.
- Có thứ tự cột cố định.
- Chia nhỏ theo key/partition để khoanh vùng mismatch.
- Có cơ chế xử lý collision và xác minh row-level khi hash khác.

Hash không phải bằng chứng tuyệt đối không collision. Không dùng hash đơn lẻ làm tiêu chí duy nhất cho dữ liệu có giá trị cao.

### 20.5. DBMS_COMPARISON

DBMS_COMPARISON có thể so sánh dữ liệu giữa hai database object, thường dùng database link và comparison metadata. Nó giúp tìm row khác nhau theo key/column và lưu kết quả scan.

Quy trình khái quát:

1. Chọn bảng/object và key ổn định, duy nhất.
2. Tạo database link an toàn tới database còn lại.
3. Tạo comparison definition trong schema utility phù hợp.
4. Chạy COMPARE với scan mode phù hợp.
5. Xem scan status và row differences.
6. Phân tích mismatch; chỉ dùng CONVERGE khi có quyết định rõ về nguồn dữ liệu chuẩn và quyền ghi.

### 20.6. DBMS_COMPARISON trên physical standby

Physical standby thường ở read-only hoặc read-only with apply. Các package compare có thể cần ghi scan metadata vào schema local, vì vậy không nên giả định có thể chạy toàn bộ quy trình trực tiếp trên standby read-only. Có thể chạy từ một database utility/primary phù hợp, dùng database link tới standby và tuân thủ quyền/phiên bản.

### 20.7. Logical standby

Logical standby dùng SQL Apply và có giới hạn với một số datatype, DDL và feature. Kiểm chứng logic cần xét các object không được SQL Apply hỗ trợ, skip rules và SQL Apply errors. Không áp dụng giả định physical block-for-block consistency cho logical standby.

## 21. Data Guard Broker và role transition validation

### 21.1. VALIDATE DATABASE

Broker có thể kiểm tra readiness của database cho switchover/failover, transport/apply configuration và một số prerequisite. Dùng VALIDATE DATABASE với tên database theo cú pháp release, và đọc toàn bộ warning chứ không chỉ dòng SUCCESS.

### 21.2. VALIDATE NETWORK CONFIGURATION

Các release hỗ trợ có lệnh validate network configuration để kiểm tra connect identifier/communication giữa các member. Đây là kiểm tra network reachability theo Broker; nó không thay thế đo latency, bandwidth hoặc test packet loss liên tục.

### 21.3. Switchover readiness

Trước switchover, kiểm tra:

- Standby đã apply tới mức cần thiết.
- Không có archive gap.
- Transport/apply state bình thường.
- Broker configuration SUCCESS.
- Switchover status cho phép chuyển role.
- Services/client routing và capacity đã sẵn sàng.

### 21.4. Failover readiness

Failover có thể gây mất dữ liệu trong Maximum Performance hoặc khi Maximum Availability đã degraded. Trước khi quyết định, xác định primary có thể phục hồi không, standby nhận redo tới đâu, có cách lấy phần redo cuối từ primary không và business chấp nhận data loss nào.

### 21.5. Fast-Start Failover

Fast-Start Failover (FSFO) có thể tự động failover theo điều kiện Broker/Observer khi cấu hình và prerequisite đáp ứng. Observer cần network path và placement phù hợp. FSFO không loại bỏ nhu cầu theo dõi lag, protection level, data loss exposure và test application reconnect.

### 21.6. Sau role transition

Sau switchover/failover:

- Xác nhận database_role và protection_mode/level.
- Xác nhận redo transport destination đã đổi đúng role.
- Kiểm tra apply/transport process và lag.
- Kiểm tra service registration và client connect.
- Xác nhận backup, archive retention và FRA.
- Kiểm chứng dữ liệu nghiệp vụ tại target.
- Reconfigure/reinstate database cũ theo runbook.

## 22. Quy trình chẩn đoán theo triệu chứng

### 22.1. Transport lag tăng, apply lag cũng tăng

1. Kiểm tra V$ARCHIVE_DEST_STATUS và destination ERROR ở primary.
2. Kiểm tra network latency, bandwidth, packet loss và listener/service.
3. Kiểm tra redo generation spike.
4. Kiểm tra standby SRL/storage và archive destination.
5. Khôi phục transport trước, sau đó theo dõi apply bắt kịp.

### 22.2. Transport lag thấp, apply lag tăng

1. Xác nhận Redo Apply process đang chạy.
2. Kiểm tra V$ARCHIVE_GAP.
3. Kiểm tra CPU, I/O latency và standby workload.
4. Kiểm tra apply throughput và backlog.
5. Điều chỉnh resource/workload hoặc apply configuration theo bằng chứng.

### 22.3. Protection level thấp hơn mode

1. Kiểm tra destination synchronous và trạng thái synchronized.
2. Kiểm tra network/standby errors.
3. Kiểm tra mode và transport attributes thực tế.
4. Khôi phục standby đồng bộ theo runbook.
5. Xác nhận protection level trở lại yêu cầu.

### 22.4. Archive gap

1. Đọc V$ARCHIVE_GAP.
2. Xác định thread/sequence/incarnation.
3. Tìm archived log ở primary, FRA, backup hoặc node khác.
4. Restore/copy/catalog theo quy trình.
5. Tiếp tục apply và xác nhận gap biến mất.

### 22.5. Standby không nhận redo

Kiểm tra destination error, service, listener, TNS, password file, DB_UNIQUE_NAME, LOG_ARCHIVE_DEST_STATE_n, network route và alert log ở cả hai site. Nếu dùng Broker, xem Broker status và log trước khi thay cấu hình.

### 22.6. Apply process không chạy

Kiểm tra Broker apply state, V$DATAGUARD_PROCESS, alert log và lỗi recovery. Khởi động lại apply bằng Broker hoặc SQL theo đúng phương thức quản lý. Không chạy đồng thời hai cơ chế quản trị mâu thuẫn.

### 22.7. Mismatch dữ liệu logic


## 23. Ma trận monitoring vận hành

### 23.1. Những gì cần thu thập

| Nhóm | Nguồn | Câu hỏi cần trả lời |
| --- | --- | --- |
| Protection | V$DATABASE, Broker | Mode cấu hình và protection level hiện tại là gì? |
| Transport | V$ARCHIVE_DEST_STATUS, alert log | Primary có gửi redo và destination có lỗi không? |
| Transport lag | V$DATAGUARD_STATS | Redo mới nhất đã tới standby chưa? |
| Apply | V$DATAGUARD_PROCESS, Broker | Redo Apply có chạy không? |
| Apply lag | V$DATAGUARD_STATS | Redo đã nhận có được apply kịp không? |
| Gap | V$ARCHIVE_GAP, V$ARCHIVED_LOG | Có sequence/thread bị thiếu không? |
| SRL | V$STANDBY_LOG | Standby có đủ redo log group/kích thước không? |
| Integrity | RMAN, V$DATABASE_BLOCK_CORRUPTION | Có block corruption được phát hiện không? |
| Logical data | DBMS_COMPARISON, business checks | Các bảng trọng yếu có khớp tại cùng snapshot không? |
| Capacity | OS, storage, FRA | Network, CPU, I/O và archive storage còn headroom không? |

### 23.2. Polling frequency

Lag và process state thường cần polling thường xuyên hơn integrity scan. Ví dụ:

- Lag/protection status: mỗi 30–60 giây tùy SLA.
- Destination errors/process state: mỗi 1–5 phút và alert event-driven nếu có.
- FRA/storage capacity: mỗi vài phút.
- Block validation: theo lịch maintenance/backup window.
- Logical comparison: theo lịch nghiệp vụ, sau migration hoặc role transition.

Đây là gợi ý khởi điểm. Giảm polling nếu query monitoring gây tải đáng kể; tăng độ chi tiết khi có incident.

### 23.3. Correlate theo timestamp

Đồng bộ clock giữa primary, standby, observer, monitoring và OS. Nếu timestamp lệch, transport/apply lag và incident timeline có thể bị hiểu sai. Lưu cả source timestamp và collection timestamp.

### 23.4. Dashboard tối thiểu

Dashboard Data Guard nên hiển thị:

- Primary/standby role và open mode.
- Protection mode/level.
- Transport/apply lag hiện tại và peak.
- Destination status/error.
- Apply process state.
- Archive gap.
- Redo generation rate và apply throughput.
- FRA/storage usage.
- Last successful backup/validation.
- Last switchover/failover drill.

### 23.5. Alert phải có hành động

Một alert hữu ích nêu database, site, destination, thread/sequence nếu có, lag duration, trend, protection level và runbook. Tránh chỉ gửi thông báo “Data Guard lag high” mà không có context.

## 24. Thiết kế kiểm chứng dữ liệu theo tầng

### 24.1. Tầng 1 — Configuration validation

Xác nhận protection mode, transport attributes, destination, SRL, Broker configuration và role transition prerequisites. Tầng này trả lời cấu hình có đúng thiết kế không.

### 24.2. Tầng 2 — Operational state validation

Xác nhận destination hoạt động, redo được nhận, apply process chạy, lag trong SLA và không có gap. Tầng này trả lời redo pipeline có vận hành không.

### 24.3. Tầng 3 — Physical integrity

Dùng RMAN VALIDATE, CHECK LOGICAL, block corruption views và backup validation để phát hiện lỗi đọc/block. Tầng này trả lời block/file có dấu hiệu corruption không.

### 24.4. Tầng 4 — Logical data comparison

Đối chiếu row/key/column hoặc business aggregate tại cùng SCN/snapshot. Tầng này trả lời dữ liệu nghiệp vụ có khớp giữa hai database không.

### 24.5. Tầng 5 — Application validation

Thực hiện health check, read/write test sau role transition, đối soát transaction ID và xác nhận application service/connection pool hoạt động. Tầng này trả lời người dùng có thể sử dụng dịch vụ không.

### 24.6. Không thay tầng này bằng tầng khác

Broker configuration SUCCESS không chứng minh datafile không corrupt. RMAN VALIDATE không chứng minh application business rows đúng. Row count giống nhau không chứng minh từng row giống nhau. Cần chọn mức kiểm chứng theo mục tiêu và rủi ro.

## 25. Data comparison và đối soát nghiệp vụ

### 25.1. Chọn bảng trọng yếu

Ưu tiên bảng có giá trị nghiệp vụ cao hoặc được dùng để xác nhận consistency:

- Ledger/transaction journal.
- Order/payment.
- Customer/account master.
- Inventory/balance.
- Bảng mapping và reference quan trọng.

Không nhất thiết so sánh mọi bảng ở cùng tần suất; phân loại theo RPO, criticality và chi phí.

### 25.2. Chọn key

Mỗi comparison nên có primary key/unique key ổn định. Nếu không có key duy nhất, xác định composite key hoặc quy trình partitioned comparison. Không dùng ROWID làm định danh xuyên database cho dữ liệu được di chuyển/được tái tạo.

### 25.3. Snapshot consistency

Để so sánh chính xác, hai phía phải đại diện cùng một trạng thái logic. Có thể tạm dừng ghi, chọn common SCN và dùng consistent read/Flashback nếu object/undo retention hỗ trợ, hoặc chờ standby apply tới mốc đã ghi nhận.

Không so sánh primary đang ghi liên tục với standby có apply lag rồi kết luận Data Guard sai.

### 25.4. DBMS_COMPARISON

DBMS_COMPARISON hỗ trợ tạo comparison definition và scan object giữa database local/remote thông qua database link. Package có thể lưu kết quả scan, row differences và trạng thái comparison trong các data dictionary views tương ứng.

Các bước triển khai tổng quát:

1. Xác nhận datatype, collation và key của object được hỗ trợ.
2. Tạo database link có quyền tối thiểu tới database còn lại.
3. Tạo comparison bằng DBMS_COMPARISON.CREATE_COMPARISON với schema/object/key phù hợp.
4. Chạy DBMS_COMPARISON.COMPARE với scan mode phù hợp.
5. Xem DBA_COMPARISON, DBA_COMPARISON_SCAN và DBA_COMPARISON_ROW_DIF.
6. Xác minh từng difference với business owner.

### 25.5. COMPARE không đồng nghĩa CONVERGE

COMPARE phát hiện và ghi nhận khác biệt. CONVERGE có thể thay đổi dữ liệu ở một phía theo quy tắc được chỉ định. Với standby managed by Redo Apply, không dùng CONVERGE để ghi trực tiếp vào physical standby. Chỉ converge giữa các database writable và khi đã xác định nguồn dữ liệu chuẩn, transaction window và rollback.

### 25.6. Checksums theo partition

Với bảng rất lớn, chia theo ngày/partition/key range rồi tính row count và hash cho từng nhóm giúp khoanh vùng mismatch. Khi nhóm nào khác, so sánh row-level trong nhóm đó. Chuẩn hóa NULL, decimal, timestamp/time zone, character encoding và column order.

### 25.7. Business reconciliation

Một số kiểm tra có thể xác nhận invariants nghiệp vụ như:

- Tổng debit và credit cân bằng theo ledger.
- Số lượng order/payment theo trạng thái.
- Tổng balance theo account/branch.
- Không có orphan foreign key logic.
- Số giao dịch theo batch ID khớp nguồn.

Các kiểm tra này bổ sung cho physical integrity; chúng không chứng minh toàn bộ database giống nhau.

## 26. Failover drill và kiểm thử protection

### 26.1. Mục tiêu drill

Drill phải chứng minh cả database và application phục hồi theo RPO/RTO:

- Standby có thể nhận/apply redo.
- Broker/observer nhận biết sự cố.
- Role transition hoàn tất.
- Service chuyển tới primary mới.
- Client reconnect và xử lý transaction outcome đúng.
- Backup/redo transport được cấu hình lại sau role transition.

### 26.2. Test switchover định kỳ

Switchover có kiểm soát là cách kiểm tra readiness mà không giả lập mất primary. Lập kế hoạch, drain workload, kiểm tra lag/gap, chạy Broker validation và thực hiện switchover theo runbook. Đo thời gian từng bước.

### 26.3. Test failover trong môi trường phù hợp

Failover có thể gây mất dữ liệu tùy protection mode và trạng thái transport. Thử nghiệm trên môi trường test hoặc theo disaster recovery exercise được phê duyệt. Không ngắt primary production để “thử nhanh”.

### 26.4. Đo RPO

Ghi nhận transaction ID/SCN cuối cùng đã commit ở primary trước sự cố và transaction cuối cùng có ở standby sau failover. Đối chiếu business records để đo data loss thực tế. Chỉ nhìn transport lag tại dashboard không đủ chứng minh RPO.

### 26.5. Đo RTO

Đo từ thời điểm incident bắt đầu tới khi application phục vụ request thành công, không chỉ tới khi database OPEN. Bao gồm detection, decision, role transition, service relocation, pool reconnect, cache warm-up và application validation.

### 26.6. Sau drill

Ghi nhận vấn đề về DNS, service, firewall, wallet, broker, lag, backup và application retry. Cập nhật runbook, monitoring và capacity plan; lặp lại drill sau thay đổi kiến trúc lớn.

## 27. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Protection level thấp hơn protection mode | Synchronous destination không còn synchronized | Kiểm tra V$DATABASE, destination status, network và standby |
| Transport lag tăng | Network, service, destination hoặc redo rate | Kiểm tra destination ERROR, network throughput và redo generation |
| Apply lag tăng, transport lag thấp | Apply throughput thấp hoặc gap | Kiểm tra V$DATAGUARD_PROCESS, V$ARCHIVE_GAP, CPU/I/O |
| Apply process stopped | Broker/apply state, recovery error hoặc thao tác quản trị | Đọc alert log, Broker status và process state |
| Archive gap | Thiếu archived log sequence/thread | Tìm file ở primary, backup, FRA hoặc standby khác |
| ORA-16047 | DB_UNIQUE_NAME mismatch trong destination | Kiểm tra destination attribute và DB_UNIQUE_NAME |
| ORA-16055 | FAL/request hoặc archive gap fetch bị từ chối | Kiểm tra primary availability, FAL/transport config và alert log |
| ORA-16766 | Redo Apply không chạy theo Broker | Kiểm tra apply state, recovery error và Broker log |
| ORA-16778 | Redo transport error theo Broker | Kiểm tra destination status, network và authentication |
| ORA-16853 | Apply lag vượt threshold Broker | Kiểm tra apply throughput và lag trend |
| ORA-16855 | Transport lag vượt threshold Broker | Kiểm tra network/transport và redo rate |
| Standby lag sau batch | Redo generation spike | So sánh redo bytes/sec với transport/apply throughput |
| Standby không thể real-time apply | SRL thiếu/sai size hoặc apply config | Kiểm tra V$STANDBY_LOG và recovery state |
| Data comparison mismatch | Snapshot không đồng nhất hoặc object differences | Xác nhận SCN, key, SQL Apply rules và compare row-level |
| Block corruption | Storage/block corruption hoặc latent issue | Kiểm tra RMAN validate, V$DATABASE_BLOCK_CORRUPTION và repair plan |

### 27.1. ORA-16853 và ORA-16855

Các warning Broker này liên quan lag vượt threshold được cấu hình. Chúng không tự nói nguyên nhân là network hay apply. Đọc transport/apply lag riêng, process state và workload metrics để xác định bottleneck.

### 27.2. Destination error

Đọc toàn bộ ERROR trong V$ARCHIVE_DEST/V$ARCHIVE_DEST_STATUS. Kiểm tra listener/service, TNS, password file, DB_UNIQUE_NAME, LOG_ARCHIVE_DEST_STATE_n, network ACL/firewall và remote destination storage.

### 27.3. Broker configuration warning

SHOW CONFIGURATION có thể báo WARNING do lag vượt threshold hoặc một database có trạng thái không như mong đợi. Dùng SHOW DATABASE VERBOSE và VALIDATE DATABASE để xác định property/error cụ thể. Không disable Broker chỉ để xóa warning.

### 27.4. Apply bị dừng sau lỗi

Kiểm tra alert log để tìm sequence, datafile, block hoặc ORA error đầu tiên. Sửa nguyên nhân, xác nhận archived log cần thiết và tiếp tục apply qua Broker hoặc SQL theo phương thức đang quản lý. Không khởi động nhiều managed recovery session song song.

### 27.5. Data mismatch

Đầu tiên xác nhận hai bên cùng snapshot. Sau đó phân biệt:

- Redo chưa apply: chờ hoặc xử lý lag/gap.
- Object không được SQL Apply hỗ trợ/đã skip: kiểm tra logical standby rules.
- Logical corruption/block corruption: chạy validation và điều tra storage.
- Application data issue đã được replicate: xử lý nghiệp vụ/restore point, không kỳ vọng Data Guard tự sửa.

## 28. Runbook kiểm tra Data Guard hằng ngày

### 28.1. Xác nhận role và protection

```sql
SELECT
    name,
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    protection_level
FROM v$database;
```

So sánh protection level với yêu cầu RPO của service.

### 28.2. Kiểm tra transport

Trên primary, xem destination status/error và xác nhận destination standby đang VALID/được đồng bộ theo cấu hình. Kiểm tra alert log và redo generation rate.

### 28.3. Kiểm tra lag

Trên standby:

```sql
SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
```

Xem cả giá trị, tuổi metric và xu hướng qua nhiều lần polling.

### 28.4. Kiểm tra apply/gap

```sql
SELECT name, role, action, thread#, sequence#
FROM v$dataguard_process
ORDER BY name;

SELECT thread#, low_sequence#, high_sequence#
FROM v$archive_gap;
```

Nếu apply dừng hoặc gap xuất hiện, mở incident và xử lý theo runbook gap.

### 28.5. Kiểm tra SRL và capacity

Xác nhận SRL đủ theo từng thread, archive destination/FRA còn headroom và standby storage không có lỗi. Kiểm tra CPU/I/O nếu apply lag tăng.

### 28.6. Kiểm tra Broker

Nếu dùng Broker, chạy SHOW CONFIGURATION và SHOW DATABASE VERBOSE cho từng member. Xử lý warning theo nguyên nhân thay vì chỉ clear trạng thái.

### 28.7. Ghi nhận

Lưu timestamp, role, protection level, transport/apply lag, destination status, sequence/thread, gap, FRA usage, backup/validation status và incident ticket. Dùng time-series để so sánh peak theo ngày/tuần.

## 29. Lab: quan sát protection mode và lag

Chỉ thực hiện trên Data Guard lab/test được phép. Không đổi protection mode hoặc ngắt network trên production để thử nghiệm.

### 29.1. Xác nhận primary

Trên primary:

```sql
SELECT
    database_role,
    protection_mode,
    protection_level,
    switchover_status
FROM v$database;

SELECT
    dest_id,
    status,
    destination,
    error
FROM v$archive_dest
WHERE status <> 'INACTIVE';
```

### 29.2. Xác nhận standby

Trên standby:

```sql
SELECT
    database_role,
    open_mode,
    protection_mode,
    protection_level
FROM v$database;

SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats;
```

### 29.3. Tạo redo có kiểm soát

Trong schema lab, thực hiện một batch DML nhỏ rồi commit. Quan sát transport lag và apply lag qua nhiều lần polling. Không tạo workload lớn chỉ để ép lag.

### 29.4. Quan sát real-time apply

Kiểm tra SRL status và V$DATAGUARD_PROCESS trong lúc redo đang được gửi. Quan sát sequence/block tiến triển và archived log sau log switch.

### 29.5. So sánh lag

Tạo bảng time-series ngoài database hoặc ghi output theo timestamp:

| Thời điểm | Transport lag | Apply lag | Destination | Apply state |
| --- | --- | --- | --- | --- |
| T0 | | | | |
| T1 | | | | |
| T2 | | | | |

Xác định transport có theo kịp redo generation và apply có xử lý hết backlog hay không.

### 29.6. Thử nghiệm transport interruption

Chỉ trong lab có phương án khôi phục, mô phỏng gián đoạn network/destination ngắn theo hướng dẫn hạ tầng. Quan sát destination error, transport lag, protection level, Broker warning và quá trình resynchronize sau khi network trở lại.

Không cố tình làm Maximum Protection mất standby synchronous trên hệ thống dùng chung; primary có thể shutdown theo thiết kế.

## 30. Lab: kiểm chứng dữ liệu primary/standby

### 30.1. Chọn bảng thử nghiệm

Tạo một bảng lab có primary key, một số cột số/ngày/character và dữ liệu nhỏ. Không dùng bảng production hoặc dữ liệu nhạy cảm.

### 30.2. Tạo dữ liệu và ghi SCN

Trên primary, commit một batch có request ID rõ ràng. Ghi SCN/time sau commit theo công cụ DBA phù hợp và chờ standby apply tới mốc đó.

### 30.3. So sánh aggregate

Chạy cùng query trên primary và standby sau khi standby apply tới mốc:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(id) AS min_id,
    MAX(id) AS max_id,
    SUM(amount) AS total_amount
FROM dg_lab_orders;
```

So sánh kết quả. Đây là kiểm tra sơ bộ, không chứng minh row-level equality.

### 30.4. So sánh row-level

Dùng DBMS_COMPARISON trong môi trường phù hợp, có database link và scan definition. So sánh theo primary key, xem các row differences và xác minh nguyên nhân. Không dùng CONVERGE trên physical standby.

### 30.5. Kiểm tra block

Trong maintenance window, chạy RMAN VALIDATE phù hợp với release và trạng thái database. Kiểm tra V$DATABASE_BLOCK_CORRUPTION trước/sau. Lưu output và thời gian I/O.

### 30.6. Ghi nhận bằng chứng

Lưu SCN/snapshot, role, lag, query output, comparison scan result, corruption view và RMAN validation output. Bằng chứng phải cho biết dữ liệu được so sánh tại cùng trạng thái nào.

## 31. Nguyên tắc thực hành tốt

1. **Chọn protection mode theo RPO/RTO.** Không chọn chỉ theo tốc độ commit hoặc một benchmark ngắn.
2. **Phân biệt protection mode với transport attributes.** Mode quy định mục tiêu; SYNC/ASYNC/AFFIRM/NOAFFIRM điều khiển transport behavior.
3. **Theo dõi protection level.** Mode cấu hình có thể khác mức bảo vệ thực tế.
4. **Hiểu commit latency của SYNC.** Network round trip và standby I/O nằm trong đường commit.
5. **Định lượng data-loss exposure của ASYNC.** Transport lag và failure scenario quyết định redo có thể mất.
6. **Cấu hình SRL cho từng thread.** RAC cần xét tất cả redo thread và kích thước log.
7. **Dùng real-time apply khi phù hợp.** Xác nhận SRL và release behavior.
8. **Đo transport và apply riêng.** Hai lag có nguyên nhân và cách xử lý khác nhau.
9. **Theo dõi DATUM_TIME.** Metric stale không phải lag bằng zero.
10. **Kiểm tra gap.** Không có gap hiện tại chưa chứng minh toàn bộ archive history đầy đủ.
11. **Giữ archive retention phù hợp.** Không xóa log trước backup/apply requirements.
12. **Dùng Broker làm source of truth khi Broker quản lý.** Tránh thay đổi cấu hình trực tiếp gây lệch trạng thái.
13. **Kiểm chứng theo nhiều tầng.** Configuration, operational state, physical integrity, logical data và application.
14. **So sánh cùng snapshot.** Primary/standby có lag hoặc write workload khác thời điểm có thể cho kết quả khác hợp lệ.
15. **Không coi row count/hash là chứng minh tuyệt đối.** Dùng row-level compare cho dữ liệu trọng yếu.
16. **Data Guard không thay backup.** Bảo vệ backup độc lập và immutable/offsite copy.
17. **Diễn tập switchover/failover.** Đo RPO/RTO ở cấp application.
18. **Alert có trend và runbook.** Phân biệt lag tăng, lag stale và lag đang hồi phục.
19. **Không force failover chỉ vì lag cao.** Đánh giá primary, standby, redo cuối và data-loss exposure.
20. **Ghi nhận bằng chứng vận hành.** Timestamp, SCN, sequence/thread, role, protection level và validation results.

## 32. Câu hỏi tự kiểm tra

1. Protection mode khác redo transport mode như thế nào?
2. Maximum Protection phản ứng ra sao khi không còn standby synchronous?
3. Maximum Availability giữ primary hoạt động thế nào khi standby tạm mất?
4. Maximum Performance có thể mất redo nào khi failover?
5. SYNC và ASYNC ảnh hưởng commit latency ra sao?
6. AFFIRM và NOAFFIRM khác thời điểm acknowledgment như thế nào?
7. PROTECTION_MODE và PROTECTION_LEVEL khác nhau ra sao?
8. RPO và RTO được ảnh hưởng bởi những thành phần nào?
9. Transport lag đo điều gì?
10. Apply lag đo điều gì?
11. Có thể có transport lag thấp nhưng apply lag cao không? Vì sao?
12. Vì sao DATUM_TIME quan trọng?
13. V$ARCHIVE_GAP cho biết điều gì và giới hạn ra sao?
14. SRL khác archived redo log thế nào?
15. Vì sao RAC cần SRL theo từng thread?
16. Real-time apply sử dụng SRL như thế nào?
17. Khi nào dùng V$DATAGUARD_PROCESS thay V$MANAGED_STANDBY?
18. Broker giúp quản lý Data Guard ra sao?
19. VALIDATE DATABASE có chứng minh dữ liệu nghiệp vụ khớp không?
20. RMAN VALIDATE CHECK LOGICAL kiểm tra điều gì?
21. Vì sao row count giống nhau không chứng minh hai bảng giống nhau?
22. DBMS_COMPARISON hỗ trợ đối chiếu ra sao?
23. Vì sao không chạy CONVERGE trực tiếp trên physical standby?
24. Làm thế nào đảm bảo hai bên đang được so sánh tại cùng snapshot?
25. Vì sao Data Guard không thay backup?
26. Khi transport lag và apply lag cùng tăng, điều tra theo thứ tự nào?
27. Khi transport lag thấp nhưng apply lag cao, nên kiểm tra gì?
28. Sau failover cần kiểm chứng những thành phần application nào?
29. Làm thế nào đo RPO thực tế trong failover drill?
30. Làm thế nào đo RTO ở cấp dịch vụ?

## 33. Mô hình ghi nhớ

```text
BUSINESS REQUIREMENTS
       |
       +-- RPO: chấp nhận mất bao nhiêu dữ liệu?
       +-- RTO: phục hồi dịch vụ trong bao lâu?
       |
       v
PROTECTION MODE
       |
       +-- MAXIMUM PROTECTION
       |      SYNC/AFFIRM, primary dừng nếu mất bảo vệ
       |
       +-- MAXIMUM AVAILABILITY
       |      SYNC khi standby khỏe, primary tiếp tục khi standby mất
       |
       +-- MAXIMUM PERFORMANCE
              ASYNC, primary ưu tiên hiệu năng
       |
       v
REDO TRANSPORT
       |
       +-- SYNC / ASYNC
       +-- AFFIRM / NOAFFIRM
       +-- Network / SRL / Bandwidth
       |
       v
STANDBY
       |
       +-- Transport lag: redo chưa nhận
       +-- Apply lag: redo nhận rồi, chưa apply
       +-- Archive gap: thiếu sequence/thread
       +-- Real-time apply từ SRL
       |
       v
DATA VALIDATION
       |
       +-- Configuration / Broker validation
       +-- Redo process / gap / lag
       +-- RMAN / block corruption
       +-- DBMS_COMPARISON / business reconciliation
       +-- Application health
       |
       v
FAILOVER DRILL
       |
       +-- Đo RPO
       +-- Đo RTO
       +-- Kiểm tra service/client reconnect
       +-- Cập nhật runbook
```

**Điểm cần nhớ:** Protection mode xác định mức bảo vệ và phản ứng của primary; SYNC/ASYNC cùng AFFIRM/NOAFFIRM điều khiển cách redo được chuyển và xác nhận. Transport lag cho biết redo chưa tới standby, apply lag cho biết redo đã nhận nhưng chưa được apply. Kiểm chứng Data Guard cần nhiều tầng: cấu hình, trạng thái redo, block integrity, logical data comparison và application failover drill.
