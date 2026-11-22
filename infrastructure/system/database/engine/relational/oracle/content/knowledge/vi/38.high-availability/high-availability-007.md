# Switchover, failover, reinstate và kế hoạch diễn tập

Oracle Data Guard duy trì một hoặc nhiều standby databases để bảo vệ primary database trước sự cố và hỗ trợ chuyển đổi vai trò khi cần. Ba thao tác vận hành quan trọng là **switchover**, **failover** và **reinstate**. Chúng có mục tiêu và điều kiện khác nhau:

- **Switchover:** chuyển đổi vai trò có kế hoạch. Primary trở thành standby, standby được chọn trở thành primary. Đây là quy trình thường dùng cho bảo trì, nâng cấp hoặc chuyển workload sang trung tâm dữ liệu khác. Khi thực hiện đúng quy trình Data Guard, switchover bảo đảm không mất dữ liệu.
- **Failover:** chuyển một standby thành primary khi primary gặp sự cố và không thể khôi phục kịp thời. Có thể mất dữ liệu tùy protection mode, redo transport, transport lag và redo mà standby đã nhận.
- **Reinstate:** đưa primary cũ trở lại làm standby của primary mới sau failover. Data Guard Broker có thể thực hiện việc này bằng Flashback Database nếu các điều kiện cần thiết được đáp ứng.

Một quy trình chuyển đổi vai trò chỉ hoàn tất khi database roles, redo transport, redo apply, application services và kết nối ứng dụng đều hoạt động đúng. Lệnh DGMGRL trả về thành công mới chỉ xác nhận bước chuyển đổi database; DBA vẫn phải xác minh ứng dụng đã phục vụ giao dịch trên primary mới và standby mới tiếp tục nhận/apply redo.

Bài học thuộc nhóm **Sẵn sàng cao** của Database Engine Relational Oracle. Nội dung tập trung vào switchover, failover, reinstate và cách xây dựng kế hoạch diễn tập có thể lặp lại, đo được RTO/RPO và có phương án quay lui.

Sau bài này, bạn có thể:

- Phân biệt planned switchover, manual failover và fast-start failover.
- Hiểu điều kiện sẵn sàng của primary và standby trước khi chuyển vai trò.
- Chọn standby đích dựa trên apply lag, transport lag và loại standby.
- Dùng Data Guard Broker qua DGMGRL để kiểm tra, validate và chuyển vai trò.
- Thực hiện switchover và xác minh primary/standby sau chuyển đổi.
- Phân biệt complete failover với immediate failover.
- Nhận biết nguy cơ split-brain và cách fence primary cũ.
- Hiểu tác động của Maximum Protection, Maximum Availability và Maximum Performance.
- Reinstate primary cũ bằng Flashback Database và DGMGRL.
- Nhận biết khi nào phải tạo lại standby thay vì reinstate.
- Khôi phục các standby phụ bị disable sau failover.
- Kiểm tra role-based services, listener, application pools và workload.
- Xây dựng kế hoạch diễn tập switchover, failover, reinstate và failback.
- Đo RTO/RPO, ghi nhận bằng chứng và cải thiện runbook sau mỗi lần diễn tập.

> **Phạm vi ví dụ:** Các ví dụ dùng Oracle Database 19c và Data Guard Broker. Tên database trong ví dụ là giả định: PROD_SITE là primary ban đầu, DR_SITE là physical standby, REPORT_SITE là standby phụ. Hãy thay bằng DB_UNIQUE_NAME, service name và cấu hình thật. Không chạy lệnh role transition trên production nếu chưa có change approval, runbook và người chịu trách nhiệm điều phối.

## 1. Mô hình Data Guard và vai trò database

Data Guard duy trì một hoặc nhiều bản sao standby của primary database. Redo generated trên primary được truyền đến standby qua redo transport services và được áp dụng bằng Redo Apply hoặc SQL Apply tùy loại standby.

### 1.1. Primary database

Primary database là database nhận giao dịch đọc/ghi của ứng dụng. Các thay đổi được ghi vào redo. Redo transport services gửi redo đến các standby theo cấu hình.

### 1.2. Physical standby

Physical standby duy trì bản sao vật lý của primary bằng cách áp dụng redo. Với physical standby, Redo Apply có thể chạy ở chế độ real-time apply khi có standby redo logs phù hợp.

Physical standby thường là lựa chọn ưu tiên cho switchover/failover vì nó có bản sao vật lý đầy đủ của database và phù hợp cho nhiều kiểu role transition.

### 1.3. Logical standby

Logical standby áp dụng redo bằng SQL Apply. Nó có thể có cấu trúc hoặc dữ liệu khác primary trong phạm vi được hỗ trợ. Một số object hoặc operation có thể không được SQL Apply xử lý theo cách giống physical standby.

Switchover/failover sang logical standby có thêm tác động tới các physical/snapshot standby khác. Các physical và snapshot standby trong cấu hình có thể bị broker disable và cần được tạo lại từ primary mới trước khi tiếp tục làm standby.

### 1.4. Snapshot standby

Snapshot standby là standby được mở read/write để kiểm thử hoặc thực hiện công việc tạm thời. Redo nhận từ primary được giữ lại để apply khi chuyển snapshot standby về physical standby.

Snapshot standby không thể là target của switchover hoặc fast-start failover. Với manual failover, broker có thể chuyển snapshot standby về physical standby và apply redo tích lũy trước khi failover.

### 1.5. Bystander standby

Bystander standby là standby không trực tiếp tham gia role transition. Sau switchover, các bystander standby thường tiếp tục hoạt động và bắt đầu nhận redo từ primary mới. Sau failover, một số bystander standby có thể bị disable nếu chúng đã apply redo vượt quá điểm redo mà primary mới có.

### 1.6. Far Sync và Observer

- Far Sync instance nhận redo từ primary và chuyển tiếp redo đến standby; nó không phải database và không thể trở thành primary.
- Observer là tiến trình giám sát dùng trong Fast-Start Failover. Observer theo dõi primary và target standby để quyết định khi nào tự động failover theo các điều kiện đã cấu hình.

## 2. Switchover, failover và reinstate khác nhau thế nào?

| Tiêu chí | Switchover | Failover | Reinstate |
| --- | --- | --- | --- |
| Mục tiêu | Hoán đổi vai trò có kế hoạch | Đưa standby lên primary khi primary lỗi | Đưa primary cũ trở lại làm standby |
| Tình trạng primary cũ | Đang hoạt động và phối hợp role transition | Có thể không truy cập được hoặc đã bị dừng | Đã được sửa và có thể khởi động ở MOUNT |
| Dữ liệu | Không mất dữ liệu khi switchover thành công theo quy trình | Có thể mất dữ liệu | Đồng bộ lại theo primary mới |
| Thời điểm | Planned maintenance, migration, test | Disaster hoặc primary outage | Sau failover |
| Lệnh Broker | SWITCHOVER TO | FAILOVER TO | REINSTATE DATABASE |
| Điều kiện then chốt | Primary/standby khỏe, redo lag thấp | Chọn target tốt, primary cũ được fence | Flashback logs đủ và có kết nối tới primary mới |

### 2.1. Switchover không phải failover có kiểm soát

Switchover là role reversal giữa hai database đang phối hợp. Primary cũ chuyển sang standby và target standby trở thành primary. Broker điều phối cả hai phía, cập nhật configuration và khởi động các dịch vụ phù hợp.

Failover là quyết định phục hồi sau sự cố. Primary cũ có thể không thể tham gia phối hợp. Standby trở thành primary dựa trên redo đã nhận và apply. Việc primary cũ có thể quay lại sau đó là một quy trình riêng.

### 2.2. Reinstate không phải switchback

Reinstate đưa database cũ trở lại làm standby của primary mới. Sau khi database cũ đã reinstate, có thể thực hiện một switchover khác để đưa workload về site ban đầu. Đó là switchback/failback.

Trình tự đúng sau failover thường là:

~~~text
Primary ban đầu gặp sự cố
          |
          v
Failover standby được chọn
          |
          v
Standby trở thành primary mới
          |
          v
Sửa và reinstate primary cũ
          |
          v
Primary cũ chạy lại như standby
          |
          v
Đồng bộ redo và kiểm tra cấu hình
          |
          v
Switchover có kế hoạch nếu muốn switchback
~~~

## 3. Vai trò của Data Guard Broker

Data Guard Broker quản lý cấu hình Data Guard tập trung và điều phối các thao tác role transition. DGMGRL là command-line interface để quản lý broker.

### 3.1. Lợi ích

Broker giúp:

- Kiểm tra trạng thái toàn configuration.
- Hiển thị transport lag và apply lag.
- Validate database trước role transition.
- Điều phối switchover/failover trên nhiều database.
- Khởi động redo transport và Redo Apply sau role change.
- Phối hợp với Oracle Clusterware và Global Data Services để quản lý services.
- Hỗ trợ reinstate database khi điều kiện Flashback Database cho phép.

### 3.2. Kiểm tra broker

Kết nối DGMGRL bằng tài khoản có quyền SYSDBA hoặc SYSDG phù hợp:

~~~text
$ dgmgrl
DGMGRL> CONNECT sys@PROD_SITE;
DGMGRL> SHOW CONFIGURATION;
~~~

Kiểm tra một database:

~~~text
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

Kiểm tra lag:

~~~text
DGMGRL> SHOW CONFIGURATION LAG;
~~~

Kết quả cần được đọc cùng với trạng thái database và lỗi broker. Configuration status SUCCESS là tín hiệu tốt, nhưng vẫn cần kiểm tra target cụ thể trước khi chuyển vai trò.

### 3.3. Các trạng thái quan trọng

| Trạng thái | Ý nghĩa vận hành |
| --- | --- |
| TRANSPORT-ON | Primary đang gửi redo theo trạng thái broker |
| APPLY-ON | Standby đang chạy apply service theo trạng thái broker |
| APPLY-OFF | Redo Apply đang dừng |
| SUCCESS | Broker không báo lỗi trong phạm vi configuration |
| WARNING | Có cảnh báo cần đọc và đánh giá |
| ERROR | Có lỗi cần xử lý trước role transition |

Đối với switchover, broker yêu cầu primary được enable và ở trạng thái TRANSPORT-ON, target standby được enable và ở trạng thái APPLY-ON.

### 3.4. Không trộn Broker với thao tác SQL thủ công

Nếu configuration do Broker quản lý, nên dùng DGMGRL để thực hiện role transition. Không tự chạy các câu ALTER DATABASE role transition trên một database trong lúc Broker đang điều phối cùng thao tác. Thao tác thủ công có thể làm broker configuration không phản ánh đúng role thực tế.

Nếu môi trường không dùng Broker, quy trình SQL thủ công có cú pháp và thứ tự riêng theo loại standby, Oracle release và kiến trúc. Hãy dùng đúng chương Data Guard Concepts and Administration cho phiên bản đó và không trộn hai runbook.

## 4. Protection mode, redo transport và RPO

Khả năng mất dữ liệu khi failover phụ thuộc cách redo được gửi và xác nhận.

### 4.1. Maximum Protection

Maximum Protection hướng tới zero data loss. Primary cần ít nhất một standby đồng bộ nhận redo theo cơ chế synchronous phù hợp. Nếu primary không thể ghi redo tới standby cần thiết, primary sẽ dừng thay vì tiếp tục giao dịch mà không bảo đảm mức bảo vệ đã cấu hình.

### 4.2. Maximum Availability

Maximum Availability dùng synchronous redo transport để hướng tới zero data loss khi standby đồng bộ khả dụng. Nếu standby tạm thời không thể xác nhận redo, primary có thể tiếp tục trong trạng thái suy giảm theo cơ chế của protection mode.

### 4.3. Maximum Performance

Maximum Performance thường dùng asynchronous redo transport để giảm ảnh hưởng tới hiệu năng primary. Khi primary gặp sự cố, standby có thể chưa nhận một phần redo mới nhất, vì vậy có nguy cơ mất dữ liệu.

### 4.4. So sánh

| Protection mode | Mục tiêu | Rủi ro khi standby không nhận redo |
| --- | --- | --- |
| Maximum Protection | Ưu tiên zero data loss | Primary có thể dừng để giữ cam kết bảo vệ |
| Maximum Availability | Zero data loss khi đồng bộ khả dụng, ưu tiên availability | Có thể hoạt động suy giảm khi mất liên lạc standby |
| Maximum Performance | Ưu tiên hiệu năng primary | Có thể mất phần redo chưa truyền khi failover |

Không nên chỉ nhìn tên protection mode để kết luận một failover cụ thể không mất dữ liệu. Phải kiểm tra transport mode, destination attributes, redo đã gửi, redo đã nhận và redo đã apply.

### 4.5. Transport lag và apply lag

- Transport lag: độ trễ redo từ primary tới standby.
- Apply lag: độ trễ apply redo trên standby so với primary.

Một standby có transport lag thấp nhưng apply lag cao vẫn có thể cần thời gian để apply redo đã nhận. Với switchover, chọn standby có lượng unapplied redo nhỏ nhất để giảm thời gian chuyển đổi. Với failover, ưu tiên standby có transport lag nhỏ nhất để giảm lượng redo có thể bị mất.

Kiểm tra trên database:

~~~sql
SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Nếu datum_time cũ hoặc lag không được cập nhật, không dùng số liệu đó như trạng thái thời gian thực. Kiểm tra network, redo transport và broker logs.

### 4.6. RPO không chỉ là transport lag hiển thị

RPO là lượng dữ liệu mà tổ chức chấp nhận mất tính từ thời điểm sự cố. Transport lag là một chỉ báo vận hành quan trọng, nhưng RPO thực tế còn phụ thuộc:

- Thời điểm giao dịch được commit trên primary.
- Redo đã được truyền và ghi bền vững tại standby.
- Redo đã apply hay còn trong standby redo logs/archive logs.
- Tình trạng primary và network lúc failover.
- Loại failover được thực hiện.

Không báo cáo RPO bằng một con số lag cũ mà không ghi thời điểm đo.

## 5. Điều kiện chuẩn bị trước switchover

Switchover là một thay đổi có kế hoạch. Chuẩn bị trước giúp tránh tình trạng primary cũ không thể chạy như standby sau khi chuyển vai trò.

### 5.1. Kiểm tra sức khỏe configuration

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

Giải quyết lỗi ERROR và đánh giá mọi WARNING. Không chỉ nhìn trạng thái configuration tổng thể; cần xác nhận chính primary và target standby.

### 5.2. Validate target

~~~text
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

Kết quả có thể cho biết:

- Database role.
- Primary database hiện tại.
- Ready for Switchover.
- Ready for Failover.
- Cảnh báo về standby hoặc cấu hình có thể bị disable sau role transition.

Có thể dùng VERBOSE để xem thêm các mục kiểm tra:

~~~text
DGMGRL> VALIDATE DATABASE VERBOSE 'DR_SITE';
~~~

### 5.3. Redo lag phải thấp

Kiểm tra:

~~~text
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE 'DR_SITE';
~~~

Chọn physical standby có lượng unapplied redo thấp nhất khi có thể. Không bắt đầu switchover khi apply lag đang tăng liên tục hoặc redo transport bị lỗi.

### 5.4. Standby redo logs

Primary cũ sẽ trở thành standby sau switchover. Vì vậy, primary cần được chuẩn bị như một standby:

- Có standby redo logs phù hợp với số lượng/size online redo logs.
- Redo transport properties được cấu hình đúng.
- Các destination có thể gửi redo sau role change.
- Các file và đường dẫn cần thiết có sẵn.

Không chỉ kiểm tra standby hiện tại. Cả hai database đều phải sẵn sàng cho vai trò mới.

### 5.5. Kiểm tra các Broker properties

Các property có thể ảnh hưởng đến redo transport và apply:

- LogXptMode.
- NetTimeout.
- StandbyArchiveLocation.
- StandbyAlternateLocation.
- RedoRoutes.
- DelayMins.

Broker không cho phép switchover đến standby có apply delay khác 0. Nếu dùng DelayMins cho mục đích vận hành, phải lập kế hoạch loại bỏ delay trước switchover theo runbook.

### 5.6. Temporary files

Đảm bảo tempfile tương ứng với temporary tablespaces trên standby đích tồn tại. Kiểm tra tempfile trên cả hai phía vì database sẽ đổi vai trò.

### 5.7. Services và application connectivity

Kiểm tra:

- Role-based services được cấu hình cho PRIMARY/STANDBY.
- Oracle Clusterware hoặc Oracle Restart quản lý service đúng.
- Listener, SCAN, DNS và connect descriptors trỏ đúng.
- Application pool có khả năng phát hiện session bị đóng và reconnect.
- Job scheduler và batch process không tiếp tục ghi vào site cũ.

### 5.8. Fast-Start Failover đang bật

Nếu FSFO được bật:

- Switchover chỉ được thực hiện tới target standby đã định trước.
- Target phải đồng bộ hoặc nằm trong lag limit theo protection mode.
- Cần kiểm tra Observer và điều kiện FSFO trước role transition.

### 5.9. Xác nhận change window

Trước khi bắt đầu:

- Có change ticket và người điều phối.
- Có thông báo cho application owner.
- Có cửa sổ bảo trì phù hợp.
- Có tiêu chí dừng/rollback.
- Có quyền truy cập cả hai site.
- Có đủ nhân sự DBA, hệ thống, network và ứng dụng.

## 6. Thực hiện switchover bằng DGMGRL

Giả sử:

- PROD_SITE là primary ban đầu.
- DR_SITE là physical standby đích.
- Sau chuyển đổi, DR_SITE sẽ là primary và PROD_SITE là physical standby.

### 6.1. Kiểm tra trước khi chuyển đổi

~~~text
DGMGRL> CONNECT sys@PROD_SITE;
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

Xác nhận primary TRANSPORT-ON, standby APPLY-ON và target báo Ready for Switchover: Yes.

### 6.2. Thực hiện

~~~text
DGMGRL> SWITCHOVER TO 'DR_SITE';
~~~

Broker điều phối:

1. Kiểm tra trạng thái primary và target standby.
2. Chuyển primary cũ sang standby role.
3. Cập nhật broker configuration.
4. Khởi động lại primary cũ nếu chuyển đổi sang physical standby.
5. Mở primary mới ở chế độ READ WRITE.
6. Khởi động redo transport từ primary mới.
7. Khởi động Redo Apply trên standby mới.
8. Kiểm tra trạng thái role transition.

Primary mới không cần restart như primary cũ trong trường hợp chuyển sang physical standby.

### 6.3. Xác minh sau switchover

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
~~~

Kỳ vọng:

- DR_SITE có role PRIMARY.
- PROD_SITE có role PHYSICAL STANDBY.
- Configuration không còn lỗi.
- Redo transport từ DR_SITE tới PROD_SITE hoạt động.
- Redo Apply trên PROD_SITE chạy.

Kiểm tra trực tiếp trên từng database:

~~~sql
SELECT
    db_unique_name,
    database_role,
    open_mode,
    protection_mode,
    switchover_status
FROM v$database;
~~~

Trên primary mới, kỳ vọng DATABASE_ROLE = PRIMARY và OPEN_MODE = READ WRITE. Trên physical standby, kỳ vọng DATABASE_ROLE = PHYSICAL STANDBY và trạng thái open phù hợp cấu hình, ví dụ MOUNTED hoặc READ ONLY WITH APPLY.

### 6.4. Kiểm tra application services

Không chỉ kiểm tra database role. Hãy:

1. Xác nhận service giao dịch chạy trên primary mới.
2. Kết nối ứng dụng bằng connect descriptor production.
3. Thực hiện một giao dịch ghi có thể kiểm soát.
4. Đọc lại dữ liệu vừa ghi.
5. Xác nhận redo được truyền và apply trên standby mới.
6. Kiểm tra batch, scheduler, monitoring và backup jobs.

### 6.5. Switchback có kế hoạch

Sau khi DR_SITE đang là primary và PROD_SITE đã chạy như standby, có thể chuyển lại:

~~~text
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> SWITCHOVER TO 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

Chỉ switchback khi hai database đồng bộ, trạng thái ổn định và change window cho phép. Không switchback chỉ vì primary mới đang nằm ở site DR.

## 7. Failover: khi nào phải chuyển Standby thành Primary?

Failover được dùng khi primary database bị lỗi và không thể khôi phục trong thời gian chấp nhận được.

Ví dụ:

- Site primary mất điện kéo dài.
- Storage primary bị hỏng.
- Database primary bị corruption nghiêm trọng.
- Hạ tầng primary không thể khôi phục trong RTO.
- Primary database không thể được mở hoặc phục hồi kịp thời.

Không failover chỉ vì một session ứng dụng bị timeout hoặc một node RAC bị lỗi nếu database vẫn có thể tiếp tục phục vụ. Cần xác định phạm vi sự cố trước khi thay đổi role.

### 7.1. Rủi ro split-brain

Split-brain xảy ra khi primary cũ và primary mới cùng mở READ WRITE và cùng nhận giao dịch độc lập. Khi đó hai database có thể tạo ra hai nhánh dữ liệu không thể hợp nhất đơn giản.

Trước manual failover:

- Nếu primary cũ còn truy cập được, dừng database theo quy trình phù hợp.
- Nếu primary cũ không truy cập được, fence nó ở tầng hạ tầng: power, cluster, network hoặc storage theo thiết kế.
- Xác nhận ứng dụng không thể ghi vào primary cũ.
- Chỉ sau khi đảm bảo primary cũ không tiếp tục nhận giao dịch mới, mới thực hiện failover.

Không coi việc standby không kết nối được primary là bằng chứng primary đã chết. Mất network có thể khiến hai site vẫn hoạt động độc lập.

### 7.2. Chọn target standby

Khi có nhiều standby:

- Ưu tiên standby có transport lag nhỏ nhất.
- Kiểm tra apply lag và trạng thái Redo Apply.
- Ưu tiên physical standby khi phù hợp.
- Kiểm tra database có lỗi apply, corruption hoặc archive gaps không.
- Kiểm tra năng lực CPU, memory, storage và network tại site dự kiến trở thành primary.

Không chọn target chỉ vì nó ở gần người vận hành hoặc có tên DR.

### 7.3. Validate failover readiness

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

VALIDATE DATABASE có thể hiển thị Ready for Failover và cảnh báo nếu primary vẫn đang chạy. Khi failover, phải đánh giá trạng thái thực tế của primary cũ và nguy cơ split-brain.

## 8. Complete failover và immediate failover

Data Guard Broker hỗ trợ hai kiểu manual failover.

### 8.1. Complete failover

Complete failover là lựa chọn mặc định và được Oracle khuyến nghị. Broker chờ standby apply phần redo chưa apply còn có thể sử dụng trước khi chuyển database sang primary.

Lệnh:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE';
~~~

Các bước khái quát:

1. Xác nhận target standby được enable.
2. Chờ apply phần redo còn lại.
3. Dừng Redo Apply/SQL Apply.
4. Chuyển standby thành primary.
5. Mở database mới ở READ WRITE.
6. Khởi động redo transport đến các standby còn đủ điều kiện.
7. Đánh giá các standby phụ có thể tiếp tục phục vụ configuration hay phải reinstate/re-create.

Complete failover cố gắng thu hồi lượng redo lớn nhất có thể. Nó có thể không mất dữ liệu nếu redo transport đã chuyển đủ redo, nhưng không bảo đảm zero data loss trong mọi protection/transport configuration.

### 8.2. Immediate failover

Immediate failover không chờ apply phần redo còn lại. Broker dừng Redo Apply/SQL Apply ngay và chuyển standby thành primary.

Lệnh:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE' IMMEDIATE;
~~~

Đây là lựa chọn có nguy cơ mất dữ liệu cao hơn. Oracle khuyến nghị chỉ dùng khi complete failover không thể thực hiện hoặc trong các trường hợp lỗi đặc biệt được tài liệu hóa, chẳng hạn ORA-752 hoặc ORA-600 [3020] do lost write đã được xác định.

Immediate failover cũng khiến các database khác trong configuration bị disable; chúng phải được reinstate hoặc tạo lại trước khi tiếp tục làm standby cho primary mới.

### 8.3. So sánh

| Tiêu chí | Complete | Immediate |
| --- | --- | --- |
| Apply redo còn lại | Có, nếu redo còn sẵn và có thể apply | Không chờ apply thêm |
| Thời gian | Có thể lâu hơn do apply backlog | Nhanh hơn |
| Data loss | Có thể zero loss tùy redo transport | Thường có nguy cơ mất dữ liệu |
| Bystander standbys | Broker đánh giá khả năng tiếp tục dùng | Tất cả database khác bị disable |
| Lựa chọn | Mặc định, ưu tiên | Chỉ dùng khi có lý do kỹ thuật rõ ràng |

Không dùng IMMEDIATE chỉ để tiết kiệm vài phút nếu complete failover vẫn có thể hoàn tất.

## 9. Thực hiện manual failover bằng DGMGRL

Giả sử PROD_SITE đã bị sự cố và DR_SITE là physical standby được chọn.

### 9.1. Xác nhận primary cũ đã được fence

Đây là bước bắt buộc của runbook. Nếu primary cũ còn hoạt động, phải đảm bảo nó không thể tiếp tục nhận giao dịch trước khi đưa DR_SITE lên primary.

### 9.2. Kết nối target standby

Oracle hướng dẫn kết nối DGMGRL tới target standby được chọn và thực hiện failover:

~~~text
$ dgmgrl
DGMGRL> CONNECT sys@DR_SITE;
DGMGRL> SHOW CONFIGURATION;
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

### 9.3. Thực hiện complete failover

~~~text
DGMGRL> FAILOVER TO 'DR_SITE';
~~~

Chỉ khi complete failover không thể thực hiện và đã xác định điều kiện phù hợp mới cân nhắc:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE' IMMEDIATE;
~~~

### 9.4. Xác minh primary mới

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

SQL:

~~~sql
SELECT
    db_unique_name,
    database_role,
    open_mode,
    protection_mode
FROM v$database;
~~~

Kỳ vọng DR_SITE có DATABASE_ROLE = PRIMARY và OPEN_MODE = READ WRITE.

### 9.5. Kiểm tra bảo vệ dữ liệu sau failover

Sau manual failover, nếu protection mode trước đó là Maximum Protection, broker sẽ hạ protection mode về Maximum Performance. DBA cần kiểm tra mode mới và lập kế hoạch khôi phục mức bảo vệ sau khi standby được tái thiết lập.

Không giả định primary mới đã có đầy đủ disaster protection ngay sau khi failover. Nếu các standby còn lại bị disable hoặc chưa đồng bộ, configuration đang ở trạng thái bảo vệ suy giảm.

### 9.6. Chuyển application services

Sau khi database mới mở READ WRITE:

- Khởi động role-based services trên primary mới.
- Đảm bảo listener và connect descriptors trỏ đến site mới.
- Cho application pool tạo lại connection.
- Xác minh request ghi và đọc.
- Kiểm tra scheduler, batch và job không chạy đồng thời ở primary cũ.
- Ghi lại thời điểm ứng dụng phục vụ trở lại.

## 10. Reinstate primary cũ

Sau failover, primary cũ không thể đơn giản khởi động READ WRITE và gia nhập lại configuration. Nó có thể nằm trên một nhánh redo khác với primary mới.

Reinstate đưa database cũ về trạng thái phù hợp để làm standby cho primary mới.

### 10.1. Điều kiện reinstate

Để Broker reinstate thành công:

- Flashback Database đã được bật trên database cần reinstate trước khi failover.
- Có đủ flashback logs để flashback về điểm cần thiết.
- Database cũ có thể khởi động ở trạng thái MOUNT.
- Database cũ kết nối mạng được với primary mới.
- Broker configuration còn nhận diện database và có thể điều phối thao tác.

Oracle khuyến nghị cấu hình Flashback Database trên tất cả database để có thể phục hồi các standby bị disable sau role transition.

### 10.2. Trạng thái ORA-16661

Nếu database có thể reinstate, Broker có thể báo:

~~~text
ORA-16661: the standby database needs to be reinstated
~~~

Đây là trạng thái cho biết database cần được reinstate trước khi có thể tiếp tục được quản lý như standby.

### 10.3. Đưa database cũ về MOUNT

Trên host của primary cũ, sau khi đã xác nhận không còn instance READ WRITE hoạt động:

~~~sql
SHUTDOWN IMMEDIATE;
STARTUP MOUNT;
~~~

Trong môi trường RAC, thực hiện theo quy trình Clusterware/SRVCTL và đảm bảo mọi instance cũ được xử lý đúng. Không khởi động database cũ ở READ WRITE sau khi failover.

### 10.4. Chạy REINSTATE DATABASE

Kết nối DGMGRL tới một database trong configuration, ngoại trừ database đang cần reinstate:

~~~text
DGMGRL> CONNECT sys@DR_SITE;
DGMGRL> REINSTATE DATABASE 'PROD_SITE';
~~~

Broker sẽ dùng Flashback Database để đưa PROD_SITE về trạng thái phù hợp và cấu hình nó thành standby của DR_SITE. Broker tự động enable database sau khi reinstate thành công.

### 10.5. Xác minh sau reinstate

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
~~~

Kỳ vọng:

- DR_SITE vẫn là PRIMARY.
- PROD_SITE trở thành PHYSICAL STANDBY nếu standby trước failover là physical.
- Broker quản lý lại PROD_SITE.
- Redo transport từ DR_SITE đến PROD_SITE hoạt động.
- Redo Apply trên PROD_SITE chạy và lag giảm dần.

### 10.6. Reinstate không phải lúc nào cũng thành công

Nếu Flashback Database không được bật trước failover hoặc flashback logs không đủ, Broker có thể không reinstate được. Khi đó database có thể chuyển sang trạng thái:

~~~text
ORA-16795: the standby database needs to be re-created
~~~

Cần tạo lại standby từ bản sao của primary mới và enable lại trong Broker configuration.

### 10.7. Trường hợp không được reinstate

Không cố reinstate primary cũ nếu failover target gặp ORA-752 hoặc ORA-600 [3020] liên quan lost write. Theo hướng dẫn Oracle, database cũ phải được tạo lại như standby từ bản sao primary mới.

Ngoài ra, nếu đã thực hiện nhiều role changes trước khi khởi động lại database cũ, database có thể không còn đủ điều kiện reinstate và cần tạo lại.

## 11. Tạo lại standby khi reinstate không khả thi

Khi không có đủ flashback logs hoặc database đã diverge, phải tạo lại standby từ primary mới.

### 11.1. Vì sao phải tạo lại từ primary mới?

Sau failover, primary mới là nguồn dữ liệu chính thức. Database cũ có thể chứa giao dịch đã commit trước failover nhưng không tồn tại trên primary mới, hoặc có redo branch không tương thích.

Tạo lại từ primary mới giúp đồng bộ lại toàn bộ database theo đúng timeline của primary hiện tại.

### 11.2. Phương án tạo lại

Tùy môi trường, DBA có thể:

- Dùng RMAN DUPLICATE FOR STANDBY.
- Restore backup của primary mới rồi recover.
- Dùng phương pháp tạo physical standby phù hợp với Oracle version và storage.
- Cấu hình lại redo transport và Broker properties.

Không copy thủ công một vài data files rồi mở database như standby. Phải bảo đảm control file, incarnation, redo thread, password file, parameter file, standby redo logs và archive destinations phù hợp.

### 11.3. Enable lại Broker

Sau khi standby được tạo lại và kiểm tra role:

~~~text
DGMGRL> ENABLE DATABASE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

Chỉ enable khi database đã được cấu hình đúng làm standby của primary mới. Nếu Broker vẫn báo ORA-16795, cần hoàn thành quy trình re-create theo tài liệu thay vì lặp ENABLE.

## 12. Bystander standbys sau failover

Failover không chỉ ảnh hưởng primary cũ và target standby. Các standby khác trong configuration cũng có thể bị disable.

### 12.1. Vì sao bystander bị disable?

Một bystander standby có thể đã apply redo vượt quá điểm redo mà target standby đã apply trước khi trở thành primary mới. Khi đó nó không thể tiếp tục nhận redo từ primary mới theo cùng timeline.

Broker có thể disable database đó để tránh apply trên một nhánh redo không còn phù hợp.

### 12.2. Trạng thái cần xử lý

- ORA-16661: cần reinstate.
- ORA-16795: cần tạo lại standby.

### 12.3. Reinstatement của bystander

Nếu Flashback Database được bật và còn đủ logs, có thể reinstate bystander theo quy trình Broker:

~~~text
DGMGRL> REINSTATE DATABASE 'REPORT_SITE';
~~~

Nếu không thể reinstate, tạo lại standby từ primary mới rồi enable trong Broker.

### 12.4. Kiểm tra toàn configuration

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'REPORT_SITE';
~~~

Không coi failover hoàn tất về mặt DR chỉ vì primary mới đang mở READ WRITE. Phải khôi phục lại ít nhất một standby khỏe và xác nhận redo apply.

## 13. Fast-Start Failover

Fast-Start Failover (FSFO) là khả năng tự động chuyển standby thành primary khi Observer và Broker phát hiện các điều kiện failover đã cấu hình.

### 13.1. Thành phần

- Primary database.
- Target standby database được cấu hình trước.
- Data Guard Broker.
- Observer process.
- Network/connectivity giữa các thành phần.

### 13.2. Khác manual failover

Manual failover do DBA quyết định và gọi DGMGRL FAILOVER. FSFO do Observer kích hoạt theo ngưỡng, protection mode, lag limit và điều kiện cấu hình.

### 13.3. Kiểm tra FSFO

~~~text
DGMGRL> SHOW FAST_START FAILOVER;
DGMGRL> SHOW CONFIGURATION;
~~~

Có thể kiểm tra readiness bằng:

~~~sql
SELECT
    database_role,
    fs_failover_status,
    fs_failover_current_target,
    fs_failover_observer_present
FROM v$database;
~~~

Tên/cột có thể khác theo release; đối chiếu V$DATABASE reference của database thực tế.

### 13.4. Observe-only mode

FSFO có observe-only mode để quan sát điều kiện failover mà không thực hiện role change:

~~~text
DGMGRL> ENABLE FAST_START FAILOVER OBSERVE ONLY;
~~~

Trong chế độ này, Broker/Observer ghi log khi điều kiện failover được đáp ứng và mô tả hành động sẽ thực hiện. Nó không tự chuyển role và không thay đổi application workload.

Đây là cách hữu ích để diễn tập/đánh giá observer detection trước khi bật FSFO thực sự. Tuy nhiên, observe-only không thay thế một bài kiểm thử failover thực tế trong môi trường được phê duyệt.

### 13.5. Auto reinstate

FSFO có thể tự động reinstate primary cũ trong một số điều kiện nếu Flashback Database và cấu hình phù hợp. Property FastStartFailoverAutoReinstate điều khiển khả năng này.

Không giả định mọi FSFO đều tự reinstate. Các điều kiện user-defined, mất kết nối observer, nhiều role changes hoặc thiếu flashback logs có thể khiến automatic reinstatement không xảy ra.

## 14. Application services sau role transition

Database role chuyển đổi không tự đảm bảo ứng dụng kết nối đúng nơi.

### 14.1. Role-based services

Service giao dịch thường được cấu hình chỉ chạy khi database có role PRIMARY. Service đọc báo cáo có thể chạy ở primary hoặc standby tùy thiết kế.

Sau switchover/failover, Oracle Clusterware và Broker có thể phối hợp để khởi động các services theo role.

### 14.2. Listener và connect descriptor

Kiểm tra:

- Service name vẫn đúng.
- DNS hoặc SCAN phân giải tới site mới.
- Listener đăng ký service đúng.
- TNS alias của ứng dụng không hard-code địa chỉ site cũ.
- Firewall và network route cho phép kết nối.

### 14.3. Connection pool

Session đang kết nối với primary cũ có thể bị đóng trong role transition. Ứng dụng cần:

- Detect connection failure.
- Tạo connection mới tới service primary.
- Retry có giới hạn.
- Không retry DML không idempotent một cách mù quáng.
- Xử lý transaction outcome chưa rõ.

### 14.4. Application Continuity và TAF

Application Continuity, Transparent Application Failover và Fast Application Notification có thể hỗ trợ khôi phục session hoặc reconnect tùy kiến trúc, driver, service configuration và loại giao dịch.

Không giả định mọi transaction đều được replay an toàn. Ứng dụng vẫn cần idempotency, transaction identifiers và xử lý trường hợp client không biết commit đã thành công hay chưa.

### 14.5. Kiểm tra dịch vụ sau chuyển đổi

Thực hiện tối thiểu:

1. Kết nối qua service production.
2. Đọc dữ liệu.
3. Ghi một giao dịch kiểm thử được kiểm soát.
4. Xác nhận dữ liệu được commit.
5. Xác nhận redo được gửi tới standby mới.
6. Xác nhận standby apply.
7. Kiểm tra job scheduler và batch ownership.

## 15. Kế hoạch diễn tập Data Guard

Một kế hoạch diễn tập tốt phải kiểm tra cả database, network, application và con người vận hành. Mục tiêu không chỉ là chứng minh câu lệnh DGMGRL chạy được mà còn xác minh dịch vụ thực sự phục hồi trong RTO/RPO.

### 15.1. Mục tiêu diễn tập

- Xác minh switchover hoàn tất không mất dữ liệu.
- Xác minh failover có thể đưa standby lên primary trong thời gian mục tiêu.
- Đo lượng dữ liệu có thể mất trong từng protection/transport mode.
- Xác minh application services chuyển sang site mới.
- Xác minh primary cũ có thể reinstate.
- Xác minh bystander standbys tiếp tục hoặc được tạo lại đúng cách.
- Kiểm tra communication giữa DBA, system, network và application teams.
- Cập nhật runbook dựa trên kết quả đo thực tế.

### 15.2. Xác định phạm vi

Trước khi diễn tập, xác định:

- Database/service nào nằm trong phạm vi.
- Site nào là primary và site nào là DR.
- Physical/logical/snapshot standby nào tham gia.
- Có dùng RAC, Far Sync, FSFO hay không.
- Application nào sẽ bị ảnh hưởng.
- Có job/batch nào phải pause hoặc reschedule.
- Bài diễn tập là planned switchover, manual failover hay FSFO.

### 15.3. Vai trò trong buổi diễn tập

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident/Exercise Commander | Điều phối, quyết định go/no-go, ghi timeline |
| DBA Lead | Kiểm tra Broker, thực hiện role transition, xác minh database |
| Infrastructure Lead | Network, host, storage, cluster, fencing |
| Application Lead | Service, connection pool, transaction validation |
| Observer/Recorder | Ghi timestamp, output, lỗi và số liệu RTO/RPO |
| Business Owner | Xác nhận mức gián đoạn và dữ liệu nghiệp vụ |

### 15.4. Định nghĩa tiêu chí thành công

Ví dụ:

| Chỉ số | Tiêu chí mẫu |
| --- | --- |
| Switchover | Hoàn tất trong change window, không mất dữ liệu |
| Failover RTO | Ứng dụng phục vụ lại trong 5 phút |
| Failover RPO | Không mất quá 30 giây giao dịch đã commit |
| Reinstate | Primary cũ trở lại làm standby trong 60 phút |
| Apply lag | Trở về ngưỡng mục tiêu trong 10 phút sau role transition |
| Application health | Read/write test thành công trên service mới |
| Broker | Configuration trở lại trạng thái SUCCESS |

Các con số chỉ là ví dụ. Business owner phải phê duyệt RTO/RPO thực tế cho từng ứng dụng.

## 16. Diễn tập switchover

Switchover drill là bài diễn tập ít rủi ro hơn failover vì hai database vẫn phối hợp và có thể đổi vai trò lại.

### 16.1. Trước buổi diễn tập

- Chọn ngày/giờ ít giao dịch.
- Thông báo application owners.
- Kiểm tra configuration và lag.
- Validate primary và standby.
- Kiểm tra standby redo logs trên cả hai database.
- Kiểm tra services và client routing.
- Ghi baseline application latency/throughput.
- Ghi SCN hoặc transaction marker để xác nhận không mất dữ liệu.

### 16.2. Thực hiện

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> VALIDATE DATABASE 'DR_SITE';
DGMGRL> SWITCHOVER TO 'DR_SITE';
~~~

### 16.3. Kiểm tra

- DR_SITE trở thành PRIMARY.
- PROD_SITE trở thành PHYSICAL STANDBY.
- Redo transport và apply hoạt động.
- Application service chạy tại DR_SITE.
- Giao dịch kiểm thử đọc/ghi thành công.
- Không có dữ liệu kiểm thử bị thiếu.

### 16.4. Switchback

Khi đã kiểm tra xong:

~~~text
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> SWITCHOVER TO 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

Xác nhận primary trở lại site ban đầu và standby tiếp tục apply.

## 17. Diễn tập failover

Failover drill có tác động lớn hơn vì nó mô phỏng primary bị mất và tạo primary mới. Chỉ thực hiện trong môi trường lab/staging hoặc production exercise được phê duyệt với kế hoạch fencing rõ ràng.

### 17.1. Chuẩn bị

- Xác định target standby.
- Kiểm tra transport lag/apply lag.
- Xác nhận Flashback Database trên các member.
- Xác nhận observer/FSFO state nếu có.
- Ghi transaction marker.
- Ghi thời điểm bắt đầu.
- Chuẩn bị lệnh fence primary.
- Xác định cách chuyển service và DNS.
- Xác định ai có quyền ra quyết định failover.

### 17.2. Mô phỏng sự cố

Trong lab, có thể mô phỏng mất site/network theo kịch bản được kiểm soát. Trong production, không tạo network partition hoặc tắt host nếu chưa có phê duyệt và cơ chế ngăn split-brain.

### 17.3. Fence primary cũ

Xác nhận primary cũ không thể nhận write. Nếu database còn truy cập được, dừng theo quy trình. Nếu không, dùng infrastructure/network/cluster fencing.

### 17.4. Failover

~~~text
DGMGRL> CONNECT sys@DR_SITE;
DGMGRL> VALIDATE DATABASE 'DR_SITE';
DGMGRL> FAILOVER TO 'DR_SITE';
~~~

Chỉ dùng IMMEDIATE nếu complete failover không khả thi và quyết định kỹ thuật đã được phê duyệt:

~~~text
DGMGRL> FAILOVER TO 'DR_SITE' IMMEDIATE;
~~~

### 17.5. Kiểm tra primary mới

- DATABASE_ROLE = PRIMARY.
- OPEN_MODE = READ WRITE.
- Application service sẵn sàng.
- Read/write test thành công.
- Transaction marker và dữ liệu đã commit được xác minh.
- Ghi nhận transaction cuối cùng có mặt để ước lượng RPO.

### 17.6. Khôi phục DR

- Kiểm tra PROD_SITE có thể reinstate không.
- Nếu đủ Flashback logs, chạy REINSTATE DATABASE.
- Nếu không, tạo lại standby từ DR_SITE.
- Khôi phục các bystander standbys.
- Kiểm tra transport/apply lag.
- Khôi phục protection mode khi configuration đã đủ điều kiện.

### 17.7. Kết thúc diễn tập

Không kết thúc bài diễn tập ngay khi ứng dụng chạy trên DR_SITE. Phải xác nhận configuration đã có standby khỏe và dữ liệu tiếp tục được bảo vệ. Nếu không, tổ chức đang chạy trên một primary duy nhất.

## 18. Kịch bản diễn tập và tiêu chí kiểm tra

| Kịch bản | Tác động mô phỏng | Kết quả cần đạt |
| --- | --- | --- |
| Planned switchover | Chuyển primary sang standby có kế hoạch | Role reversal, application reconnect, không mất dữ liệu |
| Primary host failure | Mất host primary | Failover tới standby đã chọn, ứng dụng phục vụ lại |
| Network isolation | Mất kết nối giữa site | Fencing đúng, không split-brain |
| Redo transport lag | Tăng transport lag | DBA chọn đúng target và đánh giá RPO |
| Apply lag | Standby nhận redo nhưng apply chậm | Đánh giá thời gian apply trước switchover |
| Immediate failover | Complete failover không thể thực hiện trong lab | Đo data loss và xử lý bystander standbys |
| Former primary recovery | Primary cũ quay lại sau failover | Reinstate hoặc re-create đúng cách |
| Observer outage | Observer mất kết nối | FSFO behavior đúng với thiết kế |
| Application pool stale connections | Session cũ bị đóng khi role change | Pool reconnect và transaction outcome được xử lý |
| Standby rebuild | Flashback logs không đủ | Re-create standby từ primary mới |

## 19. Đo RTO và RPO

### 19.1. RTO

Recovery Time Objective là khoảng thời gian tối đa business chấp nhận để khôi phục dịch vụ.

Đo RTO theo thời điểm:

1. T0: sự cố bắt đầu.
2. T1: incident được phát hiện.
3. T2: quyết định failover.
4. T3: failover command hoàn tất.
5. T4: database primary mới mở READ WRITE.
6. T5: application service sẵn sàng.
7. T6: giao dịch nghiệp vụ thành công.

RTO của dịch vụ thường là T6 - T0, không phải chỉ thời gian chạy câu lệnh FAILOVER.

### 19.2. RPO

Recovery Point Objective là lượng dữ liệu business chấp nhận mất khi phục hồi.

Để đo:

- Ghi transaction marker có timestamp/sequence trước diễn tập.
- Ghi nhận transaction cuối cùng đã commit trên primary cũ.
- Sau failover, xác định transaction marker cuối cùng có trên primary mới.
- So sánh khoảng thời gian hoặc số transaction bị thiếu.
- Đối chiếu với transport lag và redo state đã ghi nhận trước failover.

Không dùng SCN như một đồng hồ thời gian trực tiếp. SCN hữu ích để xác định thứ tự/điểm phục hồi, nhưng muốn báo cáo RPO theo thời gian cần correlation với timestamp và transaction marker.

### 19.3. Bảng ghi kết quả

| Mốc | Timestamp | Ghi chú |
| --- | --- | --- |
| Primary outage |  |  |
| Incident detected |  |  |
| Failover approved |  |  |
| Failover started |  |  |
| New primary open |  |  |
| Application service ready |  |  |
| First successful write |  |  |
| Old primary reinstated |  |  |
| Standby apply caught up |  |  |

### 19.4. Các số liệu bổ sung

- Transport lag trước sự cố.
- Apply lag trước sự cố.
- Redo generation rate.
- Apply rate.
- Thời gian khởi động database.
- Thời gian chuyển service.
- Thời gian application pool reconnect.
- Số transaction retry.
- Số transaction bị mất hoặc outcome chưa xác định.
- Thời gian reinstate/re-create.

## 20. Runbook diễn tập mẫu

### Giai đoạn A — Pre-check

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW CONFIGURATION LAG;
DGMGRL> SHOW DATABASE VERBOSE 'PROD_SITE';
DGMGRL> SHOW DATABASE VERBOSE 'DR_SITE';
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> VALIDATE DATABASE 'DR_SITE';
~~~

SQL:

~~~sql
SELECT
    db_unique_name,
    database_role,
    open_mode,
    protection_mode
FROM v$database;

SELECT
    name,
    value,
    unit,
    time_computed,
    datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
~~~

### Giai đoạn B — Planned switchover

~~~text
DGMGRL> SWITCHOVER TO 'DR_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

### Giai đoạn C — Application validation

- Kết nối bằng service production.
- Đọc dữ liệu.
- Ghi transaction marker.
- Xác minh commit.
- Xác minh redo apply trên standby.

### Giai đoạn D — Switchback

~~~text
DGMGRL> VALIDATE DATABASE 'PROD_SITE';
DGMGRL> SWITCHOVER TO 'PROD_SITE';
DGMGRL> SHOW CONFIGURATION;
~~~

### Giai đoạn E — Failover drill riêng

Trong môi trường failover drill đã được phê duyệt:

1. Fence primary.
2. Kết nối target standby.
3. Validate target.
4. Chạy complete failover.
5. Kiểm tra primary mới.
6. Chuyển application services.
7. Đo RTO/RPO.
8. Reinstate primary cũ hoặc re-create standby.
9. Kiểm tra bystander standbys.
10. Xác nhận configuration có lại standby khỏe.

Không gộp switchover drill và failover drill thành một lần chạy duy nhất nếu mục tiêu, tác động và tiêu chí phê duyệt khác nhau.

## 21. Troubleshooting

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| VALIDATE DATABASE báo chưa sẵn sàng switchover | Transport/apply chưa hoạt động hoặc lag/error | Kiểm tra Broker status, archive gap, redo transport và apply |
| SWITCHOVER bị từ chối | Primary không TRANSPORT-ON hoặc target không APPLY-ON | Kiểm tra ENABLED và intended state |
| Standby apply lag cao | Redo backlog hoặc tài nguyên apply không đủ | Chờ apply catch up, kiểm tra I/O/CPU và archive gaps |
| DelayMins khác 0 | Standby có apply delay | Gỡ delay theo kế hoạch trước switchover |
| Primary cũ không khởi động thành standby | Thiếu SRL, redo routes hoặc tempfile | Kiểm tra cấu hình role mới và alert log |
| FAILOVER complete không thành công | Apply error, lost-write error hoặc target không hợp lệ | Đọc alert/broker logs; không tự động chuyển sang IMMEDIATE |
| Immediate failover gây mất dữ liệu | Redo chưa apply bị bỏ qua | Đối chiếu transaction marker và báo cáo RPO |
| ORA-16661 | Database cần reinstate | Startup MOUNT và chạy REINSTATE DATABASE |
| ORA-16795 | Database cần tạo lại | Re-create standby từ primary mới |
| REINSTATE thất bại | Flashback không bật/không đủ logs/network | Kiểm tra flashback logs và connectivity; re-create nếu cần |
| Primary cũ vẫn mở READ WRITE | Nguy cơ split-brain | Fence ngay và không cho ứng dụng ghi |
| Bystander standby bị disable | Đã apply redo vượt target mới hoặc do immediate/logical failover | Reinstate hoặc re-create |
| Configuration status WARNING | Có warning hoặc member chưa đồng bộ | SHOW DATABASE VERBOSE và đọc alert/broker logs |
| Application vẫn kết nối site cũ | DNS/service/pool chưa chuyển | Kiểm tra role-based service, listener, connect descriptor và pool |
| Failover xong nhưng protection mode giảm | Maximum Protection reset về Maximum Performance | Khôi phục standby và cấu hình lại protection mode khi đủ điều kiện |

## 22. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Switchover và failover giống nhau | Switchover là planned role reversal; failover là xử lý primary failure |
| Failover luôn mất dữ liệu | Có thể không mất nếu standby đã nhận đủ redo; phụ thuộc transport/protection |
| Complete failover luôn zero data loss | Nó apply redo sẵn có tối đa; không thể apply redo chưa được truyền |
| Immediate failover chỉ là complete nhanh hơn | Nó bỏ qua redo chưa apply và có thể gây data loss |
| Reinstate là mở lại primary cũ | Reinstate đưa primary cũ về làm standby của primary mới |
| Có Flashback Database là chắc chắn reinstate được | Cần flashback logs đủ, network và các điều kiện Broker |
| ORA-16661 là database bị hỏng | Nó báo database cần reinstate |
| ORA-16795 có thể sửa bằng ENABLE DATABASE ngay | Database phải được re-create trước |
| Primary cũ có thể mở READ WRITE sau failover | Có nguy cơ split-brain và diverged redo |
| Broker SUCCESS nghĩa ứng dụng đã hoạt động | Phải kiểm tra services và transaction thực tế |
| Transport lag bằng 0 nghĩa application không mất giao dịch | Cần xét thời điểm commit, redo durability và transaction outcome |
| Failover xong là DR đã phục hồi | Phải khôi phục standby và redo protection |
| Switchover tới snapshot standby được hỗ trợ | Phải chuyển snapshot về physical standby trước |
| Có thể chọn bất kỳ standby nào | Chọn theo lag, type, health và năng lực site |

## 23. Checklist trước, trong và sau role transition

### Trước switchover

- [ ] Broker configuration khỏe.
- [ ] Primary TRANSPORT-ON.
- [ ] Target standby APPLY-ON.
- [ ] Transport/apply lag trong ngưỡng.
- [ ] VALIDATE DATABASE báo Ready for Switchover.
- [ ] Standby redo logs sẵn sàng trên cả hai database.
- [ ] DelayMins đã được xử lý.
- [ ] Tempfiles và redo routes đã được kiểm tra.
- [ ] Services và client routing có kế hoạch chuyển.
- [ ] Change window và người chịu trách nhiệm đã xác nhận.

### Trước failover

- [ ] Đã xác định primary không thể phục hồi kịp thời.
- [ ] Primary cũ đã được shutdown hoặc fence.
- [ ] Đã chọn target có transport lag nhỏ nhất phù hợp.
- [ ] Đã đánh giá apply lag và redo backlog.
- [ ] Đã xác định RPO dự kiến.
- [ ] Đã kiểm tra Broker và alert logs.
- [ ] Complete failover là lựa chọn mặc định.
- [ ] Immediate failover chỉ được chọn khi có lý do được phê duyệt.
- [ ] Application services và network routing sẵn sàng.

### Sau failover

- [ ] Target có role PRIMARY và OPEN READ WRITE.
- [ ] Application service hoạt động trên primary mới.
- [ ] Transaction test thành công.
- [ ] Đã ghi nhận RTO/RPO.
- [ ] Đã xác định trạng thái primary cũ.
- [ ] Đã reinstate hoặc re-create primary cũ.
- [ ] Bystander standbys đã được xử lý.
- [ ] Redo transport và apply hoạt động.
- [ ] Protection mode được đánh giá và phục hồi theo kế hoạch.
- [ ] Broker configuration trở lại trạng thái khỏe.

## 24. Câu hỏi tự kiểm tra

1. Switchover khác failover thế nào?
2. Reinstate giải quyết vấn đề gì sau failover?
3. Vì sao switchover cần cả primary và standby khỏe?
4. Vì sao primary cũ cần standby redo logs?
5. TRANSPORT-ON và APPLY-ON có ý nghĩa gì?
6. VALIDATE DATABASE giúp ích gì trước role transition?
7. Vì sao chọn standby có apply lag thấp cho switchover?
8. Vì sao chọn standby có transport lag thấp cho failover?
9. Maximum Protection, Maximum Availability và Maximum Performance khác nhau thế nào?
10. Complete failover thực hiện gì với redo chưa apply?
11. Immediate failover có rủi ro gì?
12. Vì sao phải fence primary cũ?
13. ORA-16661 có ý nghĩa gì?
14. ORA-16795 có ý nghĩa gì?
15. Điều kiện quan trọng để REINSTATE DATABASE thành công là gì?
16. Khi nào phải re-create standby?
17. Bystander standby có thể bị disable sau failover vì sao?
18. Vì sao manual failover có thể làm Maximum Protection chuyển thành Maximum Performance?
19. FSFO khác manual failover thế nào?
20. Observer có vai trò gì?
21. Observe-only mode có thực hiện failover thật không?
22. Vì sao role transition thành công chưa đủ để kết luận ứng dụng đã phục hồi?
23. Role-based services có vai trò gì?
24. Connection pool phải xử lý gì sau failover?
25. RTO đo từ thời điểm nào đến thời điểm nào?
26. RPO được xác định như thế nào?
27. Vì sao cần transaction marker trong failover drill?
28. Vì sao cần diễn tập reinstate?
29. Sau failover, khi nào có thể switchback?
30. Những bằng chứng nào cần lưu sau một bài diễn tập?

**Gợi ý trả lời:**

1. Switchover là planned role reversal; failover chuyển standby thành primary do primary lỗi.
2. Đưa primary cũ trở lại làm standby của primary mới.
3. Broker cần phối hợp hai database để chuyển vai trò mà không mất dữ liệu.
4. Vì primary cũ sẽ trở thành standby và cần nhận redo.
5. Primary đang gửi redo; standby đang apply redo.
6. Kiểm tra readiness, lag, lỗi và các điều kiện role transition.
7. Giảm thời gian phải apply redo còn tồn trước khi đổi vai trò.
8. Giảm lượng redo có thể bị mất tại thời điểm primary failure.
9. Mức ưu tiên giữa zero data loss và availability/performance khác nhau.
10. Chờ và apply redo đã nhận còn có thể sử dụng.
11. Bỏ qua redo chưa apply, có thể mất dữ liệu và disable các database khác.
12. Tránh hai primary cùng nhận giao dịch gây split-brain.
13. Database cần được reinstate.
14. Database cần được re-create.
15. Flashback đã bật trước failover, còn đủ logs, database ở MOUNT và có network tới primary mới.
16. Khi không đủ flashback logs, có lỗi lost-write đặc biệt hoặc reinstate thất bại.
17. Chúng có thể đã apply redo vượt quá điểm của primary mới.
18. Broker reset protection mode sau manual failover để tiếp tục hoạt động.
19. Manual do DBA quyết định; FSFO do Observer/Broker tự động kích hoạt.
20. Theo dõi primary và target standby để quyết định failover tự động.
21. Không, nó chỉ ghi log điều kiện và hành động dự kiến.
22. Ứng dụng còn cần service, listener, pool và transaction hoạt động.
23. Khởi động service trên database có role phù hợp.
24. Loại session cũ, reconnect và xử lý transaction outcome chưa rõ.
25. Từ lúc dịch vụ bị gián đoạn đến khi giao dịch nghiệp vụ hoạt động lại.
26. So sánh transaction cuối cùng đã commit với transaction cuối cùng tồn tại trên primary mới.
27. Để đo chính xác dữ liệu còn lại/mất đi.
28. Vì primary cũ phải trở thành standby để phục hồi khả năng DR.
29. Khi primary cũ đã reinstate, standby đồng bộ và runbook cho phép.
30. DGMGRL output, alert/broker logs, timestamps, transaction markers, RTO/RPO, application test và lỗi.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Data Guard Broker — Switchover and Failover Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/using-data-guard-broker-to-manage-switchovers-failovers.html): khái niệm, điều kiện, switchover, complete/immediate failover và reinstate.
- [Oracle Database 19c Data Guard Broker — Scenarios Using DGMGRL](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/examples-using-data-guard-broker-DGMGRL-utility.html): các ví dụ vận hành switchover và manual failover.
- [Oracle Database 19c Data Guard Broker — Troubleshooting](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/troubleshooting-oracle-data-guard-broker.html): xử lý lỗi Broker và role transition.
- [Oracle Database 19c Data Guard Concepts and Administration — Data Protection Modes](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/introduction-to-oracle-data-guard-concepts.html): protection mode, redo transport và khả năng bảo vệ dữ liệu.
- [Oracle Database 19c Data Guard Scenarios — Converting a Failed Primary into a Standby](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/examples-of-using-oracle-data-guard.html): Flashback Database và phục hồi primary cũ thành standby.
- [Oracle Database 19c Database Reference — V$DATAGUARD_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAGUARD_STATS.html): transport lag và apply lag.
- [Oracle Database 19c Database Reference — V$DATABASE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATABASE.html): database role, open mode, protection mode và switchover status.

**Nguyên tắc cần nhớ:** Switchover là role reversal có kế hoạch; failover là quyết định phục hồi khi primary không thể tiếp tục; reinstate đưa primary cũ trở lại làm standby. Complete failover là lựa chọn mặc định vì nó apply redo đã nhận còn có thể sử dụng; immediate failover bỏ qua redo chưa apply và có thể gây mất dữ liệu. Luôn fence primary cũ trước manual failover để tránh split-brain. Reinstate cần Flashback Database được bật trước failover và đủ flashback logs; nếu không, phải tạo lại standby từ primary mới. Một bài diễn tập chỉ thành công khi database role, redo transport/apply, application services, RTO/RPO và khả năng khôi phục DR đều được xác minh.
