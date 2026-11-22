# Maintenance window, auto task và kiểm soát thời điểm bảo trì trong Oracle Database

Oracle Database có các cơ chế lập lịch để thực hiện công việc bảo trì định kỳ. Maintenance window là khoảng thời gian được Scheduler xác định để các tác vụ bảo trì tự động có thể chạy theo chính sách tài nguyên. Automatic Maintenance Tasks sử dụng các window này để thu thập optimizer statistics, phân tích segment và thực hiện các tác vụ SQL tuning được cấu hình.

Trong vận hành thực tế, DBA còn phải điều phối các hoạt động do con người hoặc hệ thống triển khai thực hiện: backup, patching, thay đổi schema, rebuild index, kiểm tra recovery, chuyển dịch vụ và bảo trì hệ điều hành. Những công việc này cần một lịch bảo trì rõ ràng, có người chịu trách nhiệm, giới hạn thời gian, tiêu chí dừng và phương án rollback.

Cần phân biệt ba lớp:

- **Scheduler maintenance window:** đối tượng lịch trong Oracle Scheduler, có thời gian bắt đầu, thời lượng, resource plan và trạng thái.
- **Automatic Maintenance Tasks:** các client bảo trì do Oracle quản lý, được phép chạy trong maintenance window nếu client và window được bật.
- **Maintenance window của tổ chức:** khoảng thời gian DBA/operations thống nhất với ứng dụng, người dùng, backup, network và hệ điều hành để triển khai thay đổi.

Mở một Scheduler window không tự động đưa ứng dụng vào maintenance mode, không ngăn DML/DDL và không bảo đảm mọi job hoàn tất. Đây là cơ chế lập lịch và quản lý tài nguyên; việc phối hợp dịch vụ vẫn cần runbook riêng.

Bài học lấy Oracle Database 19c làm mốc, giải thích lịch cửa sổ mặc định, nhóm window, các auto task, cách kiểm tra lịch và lịch sử, điều chỉnh thời điểm bảo trì, xử lý xung đột, quản lý timezone và xây dựng một quy trình bảo trì có thể kiểm soát.

## 1. Maintenance window là gì?

### 1.1. Scheduler window

Oracle Scheduler quản lý window như một đối tượng lịch. Một window xác định:
- Khi nào window bắt đầu.
- Window lặp lại theo lịch nào.
- Window kéo dài bao lâu.
- Resource Manager plan nào được áp dụng khi window mở.
- Độ ưu tiên của window khi lịch chồng lấn.
- Trạng thái enabled/disabled và lịch sử mở/đóng.

Window có thể được dùng để xác định thời điểm chạy các job phụ thuộc window, bao gồm automatic maintenance tasks.

### 1.2. Window không phải một khoảng khóa database

Khi maintenance window mở:
- Database vẫn có thể phục vụ ứng dụng.
- User session vẫn có thể kết nối và chạy SQL nếu service/database đang mở.
- Các auto task đủ điều kiện có thể được Scheduler khởi chạy.
- Resource Manager có thể áp dụng resource plan gắn với window.
- Các job Scheduler khác có thể được lập lịch theo quy tắc riêng.

Window không tự:
- Chặn user đăng nhập.
- Dừng transaction đang chạy.
- Ngăn ứng dụng ghi dữ liệu.
- Tắt service hoặc listener.
- Tạo backup.
- Patch Oracle home.
- Bảo đảm tất cả job bảo trì được chạy.

Nếu cần downtime, DBA phải phối hợp với application/service management, drain connection, kiểm tra transaction, backup và quy trình thay đổi.

### 1.3. Ba lớp thời gian cần quản lý

| Lớp | Ví dụ | Công cụ/quy trình |
| --- | --- | --- |
| Oracle auto maintenance | Thu thập statistics, Segment Advisor | Scheduler windows, DBMS_AUTO_TASK_ADMIN |
| Job vận hành do DBA tạo | Kiểm tra backup, purge staging, validate dữ liệu | DBMS_SCHEDULER, runbook |
| Maintenance của toàn hệ thống | Patch database/OS, nâng cấp, chuyển storage | Change management, application downtime, backup/recovery plan |

Không gộp mọi hoạt động vào một Scheduler window duy nhất. Mỗi công việc có thể có thời lượng, mức rủi ro, quyền và yêu cầu downtime khác nhau.

## 2. Các maintenance window mặc định trong Oracle

### 2.1. Maintenance window group

Oracle cung cấp các Scheduler window và window group phục vụ maintenance. Các tên thường gặp trong database 19c là:
- MONDAY_WINDOW đến FRIDAY_WINDOW.
- SATURDAY_WINDOW và SUNDAY_WINDOW.
- WEEKNIGHT_WINDOW.
- WEEKEND_WINDOW.
- MAINTENANCE_WINDOW_GROUP.

Các window trong tuần thường được nhóm vào WEEKNIGHT_WINDOW; cửa sổ cuối tuần được nhóm vào WEEKEND_WINDOW. MAINTENANCE_WINDOW_GROUP tập hợp các nhóm/cửa sổ mà automatic maintenance tasks sử dụng.

Không giả định lịch mặc định chưa bị DBA thay đổi. Luôn đọc metadata trong database hiện tại trước khi lập lịch.

### 2.2. Mẫu lịch mặc định thường gặp

Nhiều database giữ lịch Oracle mặc định theo mô hình:
- Các ngày trong tuần bắt đầu khoảng 22:00, kéo dài khoảng 4 giờ.
- Saturday và Sunday bắt đầu khoảng 06:00, kéo dài khoảng 20 giờ.

Đây là mẫu lịch phổ biến, không phải cam kết về trạng thái hiện tại của mọi hệ thống. Lịch có thể đã được sửa theo múi giờ, yêu cầu ứng dụng hoặc phiên bản/cấu hình. Các truy vấn Scheduler ở phần sau mới là nguồn xác nhận.

### 2.3. Xem danh sách window

~~~sql
SELECT window_name,
       resource_plan,
       duration,
       repeat_interval,
       enabled,
       active,
       next_start_date,
       last_start_date
FROM   dba_scheduler_windows
ORDER  BY window_name;
~~~

Các cột cho biết:
- WINDOW_NAME: tên window.
- RESOURCE_PLAN: Resource Manager plan được gắn với window.
- DURATION: thời lượng mỗi lần mở.
- REPEAT_INTERVAL: biểu thức lịch lặp.
- ENABLED: window có được bật không.
- ACTIVE: window có đang mở không.
- NEXT_START_DATE/LAST_START_DATE: lịch kế tiếp và lần bắt đầu gần nhất.

Một số cột có thể hiển thị NULL nếu window chưa từng chạy hoặc không có lịch kế tiếp. Quyền truy cập DBA_SCHEDULER_WINDOWS phụ thuộc tài khoản.

### 2.4. Xem thành viên của window group

~~~sql
SELECT window_group_name,
       window_name
FROM   dba_scheduler_wingroup_members
WHERE  window_group_name IN (
           'MAINTENANCE_WINDOW_GROUP',
           'WEEKNIGHT_WINDOW',
           'WEEKEND_WINDOW'
       )
ORDER  BY window_group_name, window_name;
~~~

Truy vấn này cho biết các window hoặc group nào là thành viên của từng group. Có thể có group chứa group khác, vì vậy cần đọc cấu trúc đầy đủ nếu lịch được tùy chỉnh.

### 2.5. Xem window group

~~~sql
SELECT group_name,
       enabled,
       number_of_members
FROM   dba_scheduler_window_groups
ORDER  BY group_name;
~~~

Nếu view/cột không có trong release hoặc quyền hiện tại, dùng DESC trên view tương ứng và Oracle Database Reference. Không sửa group mặc định trước khi xác nhận membership và tác động tới auto task.

## 3. Automatic Maintenance Tasks

### 3.1. Ba client bảo trì phổ biến

Oracle 19c cung cấp các automatic maintenance task client chính:

| Automatic task | Tên client thường dùng | Mục đích |
| --- | --- | --- |
| Automatic Optimizer Statistics Collection | auto optimizer stats collection | Thu thập statistics cho object cần cập nhật để optimizer ước lượng tốt hơn |
| Automatic Segment Advisor | auto space advisor | Phân tích segment và đưa ra khuyến nghị về không gian có thể thu hồi hoặc quản lý |
| Automatic SQL Tuning Advisor | sql tuning advisor | Phân tích SQL và đưa ra khuyến nghị tuning theo cấu hình/licensing |

Tên client phải được xác nhận từ DBA_AUTOTASK_CLIENT trong chính database. Không hardcode tên client từ một môi trường khác nếu dictionary trả về tên khác.

### 3.2. Automatic Optimizer Statistics Collection

Optimizer statistics mô tả bảng, cột, index và phân bố dữ liệu. Khi statistics stale hoặc thiếu, optimizer có thể ước lượng cardinality sai và chọn execution plan không phù hợp.

Automatic Optimizer Statistics Collection có thể:
- Xác định object cần thu thập hoặc cập nhật statistics.
- Thu thập table/index/column statistics theo chính sách Oracle.
- Dùng tài nguyên trong maintenance window.
- Tạo ra thay đổi statistics có thể ảnh hưởng kế hoạch thực thi SQL.

Tác động vận hành:
- Có thể dùng CPU và I/O trong thời gian chạy.
- Statistics mới có thể khiến một số cursor được invalidated/reoptimized.
- Plan có thể thay đổi sau khi statistics được cập nhật.
- Object có statistics bị khóa hoặc có preference riêng có thể được xử lý khác.

Không tắt auto stats chỉ vì thấy một plan thay đổi. Xác định object, statistics, SQL bị ảnh hưởng và so sánh plan/runtime trước khi quyết định.

### 3.3. Automatic Segment Advisor

Segment Advisor phân tích tình trạng sử dụng không gian của segment và có thể đưa ra khuyến nghị thu hồi không gian. Nó hữu ích khi:
- Bảng/index có nhiều vùng trống do delete/update.
- Segment tăng dung lượng nhanh.
- DBA cần đánh giá khả năng shrink hoặc reorganize.
- Cần lập kế hoạch quản lý dung lượng tablespace.

Khuyến nghị của advisor không có nghĩa Oracle tự động shrink mọi segment. DBA phải xem loại segment, row movement, index dependency, lock, downtime và mức độ phù hợp trước khi thực hiện thao tác reclaim.

### 3.4. Automatic SQL Tuning Advisor

SQL Tuning Advisor phân tích SQL được chọn và có thể đưa ra khuyến nghị như statistics, access path, SQL profile hoặc thay đổi cấu trúc truy vấn. Mức độ tự động và khả năng triển khai khuyến nghị phụ thuộc cấu hình, quyền và phiên bản.

Các tính năng Automatic SQL Tuning/SQL Tuning Advisor có yêu cầu license Oracle Diagnostics Pack/Tuning Pack tương ứng. Xác nhận quyền sử dụng trong hợp đồng trước khi bật hoặc khai thác các báo cáo thuộc pack.

### 3.5. Auto task không phải tất cả job trong database

Các job do DBA hoặc ứng dụng tạo bằng DBMS_SCHEDULER không tự động trở thành Automatic Maintenance Tasks. Chúng có lịch, owner, credential, job class và chính sách lỗi riêng.

Vì vậy:
- DBA_AUTOTASK_CLIENT mô tả các client auto task.
- DBA_SCHEDULER_JOBS mô tả Scheduler jobs.
- DBA_SCHEDULER_JOB_RUN_DETAILS ghi lịch sử thực thi job.
- DBA_AUTOTASK_JOB_HISTORY cung cấp lịch sử job thuộc automatic task khi có dữ liệu.

Dùng đúng view theo loại công việc cần điều tra.

## 4. Kiểm tra trạng thái auto task

### 4.1. Xem danh sách client

~~~sql
SELECT client_name,
       status,
       resource_consumer_group,
       window_group
FROM   dba_autotask_client
ORDER  BY client_name;
~~~

STATUS thường cho biết client đang ENABLED hoặc DISABLED. RESOURCE_CONSUMER_GROUP và WINDOW_GROUP cho biết nhóm tài nguyên/lịch được gắn với client theo metadata.

Nếu một client không chạy, kiểm tra cả trạng thái client, window group, window schedule, resource plan và job history.

### 4.2. Xem client theo từng window

~~~sql
SELECT window_name,
       window_next_time,
       window_start_time,
       window_duration,
       window_active,
       optimizer_stats,
       segment_advisor,
       sql_tune_advisor
FROM   dba_autotask_window_clients
ORDER  BY window_name;
~~~

View này hữu ích để thấy các auto task client được bật hay tắt trong từng window. Nó có thể cho biết window nào sắp chạy và task nào được phép hoạt động.

### 4.3. Xem lịch sử auto task

~~~sql
SELECT client_name,
       job_name,
       job_start_time,
       job_duration,
       job_status,
       job_error,
       job_info
FROM   dba_autotask_job_history
ORDER  BY job_start_time DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Lịch sử giúp xác định task:
- Đã chạy hay chưa.
- Bắt đầu lúc nào.
- Chạy trong bao lâu.
- Thành công, lỗi hay bị dừng.
- Có thông tin bổ sung gì.

Các cột có thể khác theo release. Nếu câu truy vấn không khớp dictionary của môi trường, dùng DESC DBA_AUTOTASK_JOB_HISTORY để kiểm tra schema view.

### 4.4. Xem Scheduler job đang chạy

~~~sql
SELECT owner,
       job_name,
       job_subname,
       session_id,
       running_instance,
       elapsed_time,
       cpu_used
FROM   dba_scheduler_running_jobs
ORDER  BY elapsed_time DESC;
~~~

Đây là snapshot các Scheduler job đang chạy. Không phải mọi auto task đều xuất hiện dưới một tên dễ nhận biết; liên kết với client/job history và session khi cần.

### 4.5. Xem lịch sử Scheduler job

~~~sql
SELECT log_date,
       owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM   dba_scheduler_job_run_details
WHERE  log_date >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY log_date DESC;
~~~

View này bao gồm lịch sử Scheduler job trong phạm vi retention của Scheduler log. Dùng JOB_NAME, OWNER và thời gian để tìm job tương ứng; không giả định tất cả auto task có cùng cách đặt tên.

## 5. Quan hệ giữa maintenance window và Resource Manager

### 5.1. Resource plan của window

Một Scheduler window có thể gắn Resource Manager plan. Khi window mở, Oracle có thể kích hoạt plan được chỉ định để điều phối tài nguyên cho workload trong thời gian đó.

Các window bảo trì mặc định thường gắn DEFAULT_MAINTENANCE_PLAN. Plan này nhằm điều tiết tài nguyên giữa maintenance consumer groups và workload khác theo thiết kế Oracle.

### 5.2. Xem resource plan của window

~~~sql
SELECT window_name,
       resource_plan,
       active,
       enabled,
       duration,
       repeat_interval
FROM   dba_scheduler_windows
ORDER  BY window_name;
~~~

Xem plan đang hoạt động:

~~~sql
SELECT name,
       is_top_plan
FROM   v$rsrc_plan;
~~~

Nếu không có dòng, có thể không có Resource Manager plan đang active hoặc tài khoản không có quyền xem. Đối chiếu với thời điểm window mở và cấu hình instance.

### 5.3. Vì sao maintenance plan quan trọng?

Trong giờ bảo trì, optimizer stats job hoặc Segment Advisor có thể tiêu thụ CPU/I/O. Resource Manager giúp giới hạn/phân bổ tài nguyên theo consumer group, giảm nguy cơ maintenance task chiếm hết tài nguyên của ứng dụng.

Tuy nhiên, resource plan không thay thế capacity planning. Nếu hệ thống đã bão hòa CPU/I/O, một maintenance plan không thể tạo thêm tài nguyên vật lý.

### 5.4. Không đổi resource plan mà chưa hiểu consumer group

Trước khi thay DEFAULT_MAINTENANCE_PLAN hoặc gán plan tùy chỉnh:
- Xem plan directive và consumer group.
- Xác định user/session auto task chạy trong group nào.
- Kiểm tra CPU utilization và active session pool.
- Đánh giá mức ưu tiên của OLTP và maintenance.
- Thử trên môi trường tương đương.
- Có rollback plan.

Một resource plan sai có thể làm task không hoàn thành hoặc làm ứng dụng chậm hơn.

## 6. Kiểm tra lịch, timezone và thời điểm mở window

### 6.1. Repeat interval

Scheduler dùng calendaring syntax để mô tả lịch lặp. Ví dụ:

~~~text
freq=weekly;byday=SAT;byhour=1;byminute=0;bysecond=0
~~~

Có nghĩa lịch lặp hàng tuần vào thứ Bảy lúc 01:00. Thời điểm thực tế còn phụ thuộc start_date và timezone của schedule.

### 6.2. Xem thời gian hiện tại và timezone

~~~sql
SELECT SYSTIMESTAMP AS database_host_timestamp,
       CURRENT_TIMESTAMP AS session_timestamp,
       DBTIMEZONE AS database_timezone,
       SESSIONTIMEZONE AS session_timezone
FROM   dual;
~~~

SYSTIMESTAMP phản ánh thời gian hệ thống host/database với timezone offset. CURRENT_TIMESTAMP theo timezone của session. DBTIMEZONE và SESSIONTIMEZONE có ý nghĩa riêng; không mặc định chúng giống nhau.

### 6.3. Timezone của Scheduler

Scheduler lưu thời điểm lịch và repeat interval theo ngữ cảnh timezone của schedule/start date. Khi lập lịch dài hạn:
- Ưu tiên timezone region như Asia/Ho_Chi_Minh hoặc khu vực vận hành tương ứng khi cần bám theo giờ địa phương.
- Tránh giả định offset cố định luôn đúng nếu vùng có daylight saving time.
- Kiểm tra NEXT_START_DATE sau khi thay repeat interval.
- Xác nhận lịch qua các ngày chuyển DST nếu hệ thống đặt ở vùng có DST.
- Đồng bộ thời gian giữa database host, application host và hệ thống monitoring.

Nếu lịch phải chạy theo UTC, hãy định nghĩa và ghi rõ UTC trong quy trình thay đổi.

### 6.4. Kiểm tra lịch kế tiếp

~~~sql
SELECT window_name,
       repeat_interval,
       duration,
       next_start_date,
       last_start_date,
       enabled,
       active
FROM   dba_scheduler_windows
ORDER  BY next_start_date NULLS LAST;
~~~

Sau khi sửa lịch, kiểm tra NEXT_START_DATE và xác nhận nó nằm trong maintenance window mà operations đã thống nhất.

### 6.5. Window chồng lấn

Nhiều window có thể được lập lịch gần nhau hoặc chồng lấn. Scheduler dùng window priority và quy tắc window để xác định window active. Hãy xem PRIORITY, lịch lặp, duration và window log để hiểu điều gì xảy ra khi lịch xung đột.

Không tạo thêm window với duration dài mà không kiểm tra lịch hiện có. Việc chồng lấn có thể khiến một window bị thay thế/đóng theo quy tắc Scheduler hoặc làm resource plan thay đổi ngoài dự kiến.

## 7. Điều chỉnh lịch bảo trì mặc định

### 7.1. Thay đổi repeat interval

Ví dụ chuyển MONDAY_WINDOW sang bắt đầu lúc 01:00 thứ Hai:

~~~sql
BEGIN
    DBMS_SCHEDULER.SET_ATTRIBUTE(
        name      => 'MONDAY_WINDOW',
        attribute => 'REPEAT_INTERVAL',
        value     => 'freq=daily;byday=MON;byhour=1;byminute=0;bysecond=0'
    );
END;
/
~~~

Lệnh thay đổi lịch của window hiện có. Hãy xác nhận tên window, quyền và thời điểm mới với operations trước khi chạy.

### 7.2. Thay đổi duration

Ví dụ đặt thời lượng thành ba giờ:

~~~sql
BEGIN
    DBMS_SCHEDULER.SET_ATTRIBUTE(
        name      => 'MONDAY_WINDOW',
        attribute => 'DURATION',
        value     => NUMTODSINTERVAL(3, 'HOUR')
    );
END;
/
~~~

Duration là khoảng thời gian window mở mỗi lần theo lịch. Nếu ngắn hơn thời gian cần thiết, auto task có thể không hoàn thành trong window. Nếu dài quá, maintenance có thể tranh chấp tài nguyên với workload giờ làm việc.

### 7.3. Xác nhận sau thay đổi

~~~sql
SELECT window_name,
       repeat_interval,
       duration,
       next_start_date,
       resource_plan,
       enabled
FROM   dba_scheduler_windows
WHERE  window_name = 'MONDAY_WINDOW';
~~~

Sau thay đổi, xác nhận cả repeat interval, duration, next start date và resource plan. Ghi lại giá trị trước/sau trong change record.

### 7.4. Disable và enable window

Tạm tắt một window:

~~~sql
BEGIN
    DBMS_SCHEDULER.DISABLE('MONDAY_WINDOW');
END;
/
~~~

Bật lại:

~~~sql
BEGIN
    DBMS_SCHEDULER.ENABLE('MONDAY_WINDOW');
END;
/
~~~

DISABLE ngăn window được Scheduler mở theo lịch sau khi thao tác có hiệu lực. Nó không đồng nghĩa đã hủy mọi job đang chạy trong window. Kiểm tra running jobs và job log trước khi kết luận công việc đã dừng.

### 7.5. Không sửa lịch hệ thống tùy tiện

Các window mặc định là một phần của cấu hình quản trị database. Trước khi thay đổi:
- Lưu lại repeat interval, duration, resource plan và group membership.
- Xác định auto task nào phụ thuộc window.
- Kiểm tra lịch backup, batch, ETL và ứng dụng.
- Đánh giá PDB/CDB nếu multitenant.
- Thực hiện trong change window.
- Xác nhận lịch kế tiếp và lịch sử sau thay đổi.
- Chuẩn bị lệnh rollback về giá trị cũ.

## 8. Tạo custom maintenance window

### 8.1. Khi nào nên tạo window riêng?

Tạo custom window khi:
- Lịch mặc định không phù hợp với giờ tải thấp.
- Có một khoảng bảo trì dành riêng cho một nhóm công việc.
- Cần resource plan hoặc duration khác.
- Muốn tách maintenance task khỏi một lịch vận hành hiện có.

Trước tiên quyết định custom window chỉ dành cho job do DBA quản lý hay cần cho automatic maintenance tasks. Nếu muốn auto task chạy trong window mới, cần cấu hình membership trong MAINTENANCE_WINDOW_GROUP và kiểm tra trạng thái client/window.

### 8.2. Tạo window

Ví dụ tạo window thứ Bảy lúc 01:00, kéo dài bốn giờ:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_WINDOW(
        window_name     => 'SATURDAY_CUSTOM_WINDOW',
        resource_plan   => 'DEFAULT_MAINTENANCE_PLAN',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'freq=weekly;byday=SAT;byhour=1;byminute=0;bysecond=0',
        duration        => NUMTODSINTERVAL(4, 'HOUR'),
        window_priority => 'HIGH',
        comments        => 'Custom maintenance window for approved tasks'
    );
END;
/
~~~

Đây là ví dụ cần được điều chỉnh theo timezone, lịch backup và maintenance policy. DEFAULT_MAINTENANCE_PLAN phải tồn tại và được cấu hình phù hợp trong database.

### 8.3. Thêm window vào maintenance group

Nếu muốn automatic maintenance tasks xem custom window là một thành viên của maintenance window group:

~~~sql
BEGIN
    DBMS_SCHEDULER.ADD_GROUP_MEMBER(
        group_name => 'MAINTENANCE_WINDOW_GROUP',
        member     => 'SATURDAY_CUSTOM_WINDOW'
    );
END;
/
~~~

Thao tác này làm thay đổi lịch mà auto task có thể sử dụng. Không thêm custom window vào group nếu chỉ muốn chạy một job riêng của DBA.

Trước khi thêm, xem membership hiện tại để tránh thêm trùng hoặc tạo lịch bảo trì vượt quá thời lượng mong muốn.

### 8.4. Bật window và kiểm tra

~~~sql
BEGIN
    DBMS_SCHEDULER.ENABLE('SATURDAY_CUSTOM_WINDOW');
END;
/
~~~

Kiểm tra:

~~~sql
SELECT window_name,
       resource_plan,
       duration,
       repeat_interval,
       enabled,
       active,
       next_start_date
FROM   dba_scheduler_windows
WHERE  window_name = 'SATURDAY_CUSTOM_WINDOW';
~~~

### 8.5. Gỡ window khi không còn sử dụng

Nếu window đã nằm trong group, gỡ membership trước:

~~~sql
BEGIN
    DBMS_SCHEDULER.REMOVE_GROUP_MEMBER(
        group_name => 'MAINTENANCE_WINDOW_GROUP',
        member     => 'SATURDAY_CUSTOM_WINDOW'
    );
END;
/
~~~

Sau đó disable/drop window theo quy trình:

~~~sql
BEGIN
    DBMS_SCHEDULER.DISABLE('SATURDAY_CUSTOM_WINDOW');
    DBMS_SCHEDULER.DROP_WINDOW(
        window_name => 'SATURDAY_CUSTOM_WINDOW',
        force       => TRUE
    );
END;
/
~~~

DROP_WINDOW force cần được dùng thận trọng. Kiểm tra window có đang active hoặc được job/group khác tham chiếu trước khi xóa.

## 9. Bật và tắt từng Automatic Maintenance Task

### 9.1. Disable một client trên mọi window

Ví dụ tạm tắt Automatic Segment Advisor:

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto space advisor',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

Ví dụ tắt automatic optimizer stats collection:

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

Tên client phải lấy từ DBA_AUTOTASK_CLIENT. Tắt một client ảnh hưởng mọi maintenance window trong phạm vi chỉ định; cần đánh giá hậu quả trước khi thực hiện.

### 9.2. Disable client trong một window cụ thể

Nếu chỉ muốn tắt một client trong một window:

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.DISABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => 'MONDAY_WINDOW'
    );
END;
/
~~~

Cách này cho phép giữ auto stats trong các window khác. Kiểm tra DBA_AUTOTASK_WINDOW_CLIENTS sau khi thay đổi.

### 9.3. Enable lại client

~~~sql
BEGIN
    DBMS_AUTO_TASK_ADMIN.ENABLE(
        client_name => 'auto optimizer stats collection',
        operation   => NULL,
        window_name => NULL
    );
END;
/
~~~

Nếu client chỉ bị disable ở một window, truyền đúng window_name để khôi phục phạm vi tương ứng. Không enable toàn bộ client khi chỉ cần khôi phục một window nếu chính sách yêu cầu phạm vi hẹp.

### 9.4. Disable auto task khác với disable Scheduler window

| Thao tác | Tác động |
| --- | --- |
| DBMS_AUTO_TASK_ADMIN.DISABLE | Ngăn một auto task client chạy trong phạm vi chỉ định |
| DBMS_SCHEDULER.DISABLE(window) | Ngăn Scheduler mở window theo lịch |
| DBMS_SCHEDULER.CLOSE_WINDOW | Đóng window đang active |
| DBMS_SCHEDULER.STOP_JOB | Yêu cầu dừng một Scheduler job cụ thể |

Không thay thế các thao tác này cho nhau. Nếu tắt window, mọi công việc phụ thuộc window có thể bị ảnh hưởng; nếu chỉ tắt một client, các client khác vẫn có thể chạy.

### 9.5. Không để auto stats bị tắt vô thời hạn

Nếu phải tạm tắt Automatic Optimizer Statistics Collection vì sự cố:
- Ghi lý do và thời điểm bắt đầu.
- Xác định bảng/object cần statistics.
- Lên lịch thu thập thủ công hoặc thời điểm bật lại.
- Theo dõi stale statistics và plan regression.
- Đặt owner và deadline khôi phục.

Statistics cũ kéo dài có thể khiến optimizer chọn plan kém khi dữ liệu thay đổi.

## 10. Mở và đóng window thủ công

### 10.1. OPEN_WINDOW

Scheduler hỗ trợ mở window theo yêu cầu:

~~~sql
BEGIN
    DBMS_SCHEDULER.OPEN_WINDOW(
        window_name => 'SATURDAY_CUSTOM_WINDOW',
        duration    => NUMTODSINTERVAL(2, 'HOUR'),
        force       => TRUE
    );
END;
/
~~~

OPEN_WINDOW có thể dùng cho một tình huống vận hành được phê duyệt, nhưng không nên dùng như cách chạy auto task tùy tiện. Kiểm tra window, resource plan, lịch chồng lấn và job phụ thuộc trước khi mở.

### 10.2. CLOSE_WINDOW

~~~sql
BEGIN
    DBMS_SCHEDULER.CLOSE_WINDOW('SATURDAY_CUSTOM_WINDOW');
END;
/
~~~

CLOSE_WINDOW đóng window đang mở. Đóng window không nhất thiết hủy mọi job đã bắt đầu; hành vi của job phụ thuộc thuộc tính Scheduler và loại task. Kiểm tra DBA_SCHEDULER_RUNNING_JOBS và lịch sử sau thao tác.

### 10.3. OPEN_WINDOW không thay thế downtime

Nếu cần patch database hoặc OS:
- Dừng/drain application service theo runbook.
- Xác nhận transaction và session.
- Xác nhận backup/recovery.
- Thực hiện patch theo quy trình Oracle.
- Kiểm tra database/service sau bảo trì.
- Mở traffic trở lại khi tiêu chí nghiệm thu đạt.

Mở Scheduler window chỉ điều khiển lịch/resource plan; nó không tạo trạng thái downtime cho ứng dụng.

## 11. Theo dõi lịch sử window

### 11.1. Window log

~~~sql
SELECT log_date,
       window_name,
       operation,
       status,
       actual_start_date,
       actual_duration
FROM   dba_scheduler_window_log
ORDER  BY log_date DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Window log giúp xác định window đã mở/đóng, thời điểm thực tế và trạng thái operation. Nếu window không chạy như mong đợi, đối chiếu:
- ENABLED và ACTIVE.
- REPEAT_INTERVAL.
- NEXT_START_DATE.
- Window group membership.
- Scheduler log.
- Resource plan.
- Lịch window khác có overlap.

### 11.2. Tìm auto task thất bại

~~~sql
SELECT client_name,
       job_name,
       job_start_time,
       job_duration,
       job_status,
       job_error,
       job_info
FROM   dba_autotask_job_history
WHERE  job_status <> 'SUCCEEDED'
ORDER  BY job_start_time DESC;
~~~

Nếu view lưu nhiều trạng thái hoặc giá trị trạng thái khác nhau, xem dữ liệu thực tế và lọc phù hợp. Job lỗi có thể do resource, object lock, không gian, quyền hoặc task bị dừng khi window đóng.

### 11.3. Kiểm tra job Scheduler lỗi

~~~sql
SELECT log_date,
       owner,
       job_name,
       status,
       error#,
       actual_start_date,
       run_duration,
       additional_info
FROM   dba_scheduler_job_run_details
WHERE  status <> 'SUCCEEDED'
ORDER  BY log_date DESC;
~~~

Một job thất bại cần xem ERROR#, ADDITIONAL_INFO và job action. Không chỉ enable lại job lặp đi lặp lại khi chưa hiểu lỗi.

### 11.4. Theo dõi session của auto task

~~~sql
SELECT sid,
       serial#,
       username,
       module,
       action,
       client_identifier,
       sql_id,
       event,
       wait_class,
       status
FROM   v$session
WHERE  status = 'ACTIVE'
ORDER  BY username, module, action;
~~~

Module/action có thể giúp nhận diện job hoặc component. Giá trị thực tế phụ thuộc phiên bản và task; kết hợp SQL_ID, job metadata và session program.

## 12. Kiểm soát xung đột với workload khác

### 12.1. Maintenance và batch window

Nếu ETL, backup, index maintenance và auto stats cùng chạy trong một khoảng, chúng có thể cạnh tranh:
- CPU.
- Datafile I/O.
- Redo log I/O.
- TEMP.
- PGA.
- Undo.
- Network hoặc storage bandwidth.

Lập lịch theo dependency, không chỉ chọn giờ ít người đăng nhập.

### 12.2. Bản đồ công việc theo thời gian

Ví dụ lịch minh họa:

| Thời gian | Công việc | Tài nguyên cần chú ý |
| --- | --- | --- |
| 00:00–01:00 | Backup incremental | Datafile read, storage/network |
| 01:00–02:00 | Auto optimizer stats | CPU, I/O, cursor invalidation |
| 02:00–03:00 | ETL batch | CPU, redo, undo, TEMP |
| 03:00–04:00 | Segment review/reclaim đã phê duyệt | I/O, locks, space |
| 04:00–05:00 | Validation và kiểm tra backup | I/O, CPU |

Đây chỉ là ví dụ. Lịch thật cần dựa trên thời lượng đo được, dependency và capacity.

### 12.3. Backup và auto stats

Backup full/incremental có thể đọc nhiều data block. Auto stats cũng có thể đọc bảng/index. Chạy đồng thời có thể tăng I/O và kéo dài cả hai.

Có thể tách lịch hoặc giới hạn resource plan nếu đo được tranh chấp. Không tắt auto stats dài hạn chỉ để backup nhanh hơn mà chưa có kế hoạch thay thế.

### 12.4. Batch DML và undo/redo

Batch DML lớn có thể tạo nhiều redo/undo. Nếu chạy đồng thời với backup, archive hoặc các tác vụ khác, có thể gây:
- log file sync/log file parallel write pressure.
- archive destination pressure.
- Undo tablespace pressure.
- TEMP spill từ sort/hash.
- Storage queue tăng.

Lập lịch batch theo capacity và chia transaction hợp lý.

### 12.5. Index rebuild và schema change

Rebuild index có thể dùng CPU, I/O, TEMP và không gian bổ sung. Một số thao tác cần lock hoặc ảnh hưởng DML tùy cách chạy và edition/license.

Trước khi đưa vào maintenance window, tính:
- Segment size và free space.
- Online/offline requirement.
- Lock impact.
- Redo/undo generation.
- Backup và rollback plan.
- Thời gian thực tế trên dữ liệu đại diện.

## 13. Maintenance window trong CDB/PDB

### 13.1. Xác định container

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM   dual;
~~~

Trong multitenant database, cần xác định đang thao tác ở CDB root hay PDB. Auto task và Scheduler object có phạm vi quản trị theo container và cấu hình cụ thể.

### 13.2. Không giả định một window có cùng tác động mọi PDB

Một số tác vụ có thể được quản lý ở CDB level, trong khi object/task gắn với PDB. Khi thay đổi lịch:
- Xác định policy quản trị common/local.
- Kiểm tra container hiện tại.
- Xem các PDB có maintenance workload riêng không.
- Đánh giá resource plan ở cấp CDB/PDB.
- Kiểm tra trạng thái và lịch sử trong đúng container.

### 13.3. CDB views

DBA có thể dùng CDB-level views để tổng hợp Scheduler/auto task metadata qua container khi có quyền phù hợp. Giữ CON_ID trong báo cáo để phân biệt các PDB có cùng tên job hoặc user.

Không chạy câu lệnh thay đổi ở root với giả định nó chỉ ảnh hưởng một PDB. Luôn xác nhận CON_NAME trước khi thực hiện.

## 14. Quản lý job vận hành riêng

### 14.1. Tạo Scheduler job

Ví dụ tạo job chạy một procedure kiểm tra dữ liệu vào mỗi Chủ nhật lúc 02:00:

~~~sql
BEGIN
    DBMS_SCHEDULER.CREATE_JOB(
        job_name        => 'OPS_WEEKLY_VALIDATION',
        job_type        => 'STORED_PROCEDURE',
        job_action      => 'OPS_VALIDATE_DATA',
        start_date      => SYSTIMESTAMP,
        repeat_interval => 'freq=weekly;byday=SUN;byhour=2;byminute=0;bysecond=0',
        enabled         => FALSE,
        auto_drop       => FALSE,
        comments        => 'Weekly validation during approved maintenance period'
    );
END;
/
~~~

Job được tạo disabled để DBA kiểm tra action, owner, privilege và lịch trước khi enable.

### 14.2. Enable job

~~~sql
BEGIN
    DBMS_SCHEDULER.ENABLE('OPS_WEEKLY_VALIDATION');
END;
/
~~~

Kiểm tra:

~~~sql
SELECT owner,
       job_name,
       job_type,
       job_action,
       repeat_interval,
       enabled,
       state,
       next_run_date
FROM   dba_scheduler_jobs
WHERE  job_name = 'OPS_WEEKLY_VALIDATION';
~~~

### 14.3. Gắn job vào job class

Job class cho phép nhóm job theo resource consumer group và logging policy. DBA có thể tạo job class phù hợp để tách batch/maintenance workload. Resource Manager plan và job class cần được thiết kế cùng nhau; đừng gán job vào consumer group không tồn tại.

### 14.4. Đặt lịch job phụ thuộc window

Scheduler job có thể được lập lịch theo window hoặc window group thông qua schedule phù hợp. Dùng schedule/window group giúp job chỉ chạy trong thời điểm được phép. Kiểm tra cú pháp CREATE_JOB/CREATE_SCHEDULE của release và đảm bảo window group được bật.

Một job có lịch thời gian đơn thuần không tự động bị giới hạn vào maintenance window. Nếu cần phụ thuộc window, hãy khai báo dependency rõ ràng.

### 14.5. Retry và failure handling

Với job quan trọng:
- Định nghĩa retry/raise event phù hợp.
- Ghi log ứng dụng và kết quả.
- Đảm bảo action idempotent nếu có retry.
- Không để retry tạo dữ liệu trùng.
- Cảnh báo owner khi job thất bại.
- Xác định thời điểm bỏ qua để không chạy trễ vào giờ production.

## 15. Quy trình thiết kế maintenance window

### 15.1. Thu thập yêu cầu

Ghi lại:
- Service/database/PDB liên quan.
- Công việc phải chạy.
- Tần suất.
- Thời lượng trung bình và p95.
- CPU, I/O, TEMP, undo, redo.
- Dependency với backup, ETL và ứng dụng.
- Downtime có cần thiết không.
- Thời gian tối đa được phép.
- Người phê duyệt và người vận hành.

### 15.2. Chọn thời điểm

Chọn thời gian dựa trên:
- Mức thấp của workload thực tế.
- Lịch batch và backup.
- Múi giờ người dùng và data center.
- SLA và RPO/RTO.
- Lịch của PDB/service khác.
- Khoảng thời gian dành cho validation/rollback.

Đừng chọn chỉ vì “nửa đêm ít người dùng”; batch, backup và ETL có thể tập trung đúng thời điểm đó.

### 15.3. Đặt duration có buffer

Nếu job thường chạy 90 phút, không nên đặt window 90 phút chính xác. Cần buffer cho:
- Biến động kích thước dữ liệu.
- I/O chậm.
- Retry.
- Validation.
- Cleanup.
- Rollback.

Duration quá ngắn khiến task không hoàn tất; duration quá dài có thể chạm giờ production. Dùng percentile thời gian chạy thay vì một lần chạy tốt nhất.

### 15.4. Kiểm soát concurrency

Xác định số job đồng thời và tổng resource budget. Có thể chạy các job tuần tự nếu chúng cùng tiêu thụ I/O hoặc TEMP. Resource Manager hỗ trợ giới hạn tài nguyên, nhưng lịch tuần tự vẫn hữu ích để tránh peak trùng nhau.

### 15.5. Xác định tiêu chí thành công

Mỗi công việc nên có:
- Điều kiện bắt đầu.
- Expected duration.
- Kết quả mong đợi.
- Kiểm tra sau chạy.
- Điều kiện dừng.
- Rollback/compensation.
- Người nhận cảnh báo.

Không đánh dấu bảo trì hoàn tất chỉ vì Scheduler job status là SUCCEEDED; cần xác nhận nghiệp vụ và database health.

## 16. Runbook trước, trong và sau maintenance

### Trước cửa sổ

1. Xác nhận change ticket, owner và người phê duyệt.
2. Xác nhận database, CDB/PDB, service và host đúng.
3. Xem lịch Scheduler windows, group membership và auto task clients.
4. Xem backup hoàn tất và khả năng restore theo yêu cầu.
5. Kiểm tra dung lượng tablespace, TEMP, undo, archive destination và filesystem.
6. Xác nhận job/batch không xung đột.
7. Kiểm tra resource plan và concurrency.
8. Ghi lại baseline DB time, CPU, I/O, redo, undo, TEMP.
9. Chuẩn bị script, lệnh rollback và validation.
10. Thông báo application owner nếu cần drain/downtime.

### Trong cửa sổ

1. Xác nhận đúng window đã mở hoặc job được phép bắt đầu.
2. Kiểm tra session/transaction và service state.
3. Theo dõi running jobs, SQL_ID, wait events và resource usage.
4. Kiểm tra alert log, Scheduler job log và application log.
5. Ghi nhận thời gian thực tế và thay đổi đã chạy.
6. Dừng/hoãn công việc nếu vượt ngưỡng hoặc ảnh hưởng SLA.
7. Không chạy thêm công việc ngoài scope đã phê duyệt.

### Sau cửa sổ

1. Xác nhận job kết thúc và không còn session/job ngoài dự kiến.
2. Kiểm tra database open state, service, listener và PDB.
3. Xác nhận backup/archive/standby theo phạm vi thay đổi.
4. Kiểm tra invalid objects, job failures và alert log.
5. Kiểm tra auto task/window đã được enable lại nếu có thay đổi tạm thời.
6. Đo lại DB time, CPU, I/O, redo, undo và TEMP.
7. Xác nhận ứng dụng smoke test và latency.
8. Ghi kết quả, sự cố, thời gian thực tế và follow-up.

## 17. Kiểm soát thay đổi và rollback

### 17.1. Lưu cấu hình trước khi thay đổi

Trước khi sửa window, xuất lại metadata:
- DBA_SCHEDULER_WINDOWS.
- DBA_SCHEDULER_WINGROUP_MEMBERS.
- DBA_AUTOTASK_CLIENT.
- DBA_AUTOTASK_WINDOW_CLIENTS.
- Resource plan và job class liên quan.

Có thể lưu kết quả truy vấn vào change record để biết giá trị gốc.

### 17.2. Rollback lịch window

Nếu thay repeat interval/duration, rollback bằng giá trị đã lưu trước đó. Không tự đặt lại lịch “mặc định” theo trí nhớ; database có thể đã dùng lịch tùy chỉnh từ trước.

### 17.3. Rollback auto task status

Nếu disable client tạm thời, ghi rõ:
- Client name.
- Window scope.
- Thời điểm disable.
- Người thực hiện.
- Thời điểm dự kiến enable lại.

Sau maintenance, chạy ENABLE đúng phạm vi và xác nhận DBA_AUTOTASK_CLIENT/DBA_AUTOTASK_WINDOW_CLIENTS.

### 17.4. Job chạy quá thời gian

Nếu job vượt duration:
- Xác định job còn chạy hay đã dừng.
- Xem DBA_SCHEDULER_RUNNING_JOBS và job run details.
- Kiểm tra STOP_ON_WINDOW_CLOSE/thuộc tính job nếu có liên quan.
- Xem job có thể hoàn tất an toàn sau window hay cần dừng.
- Xác định transaction/rollback impact trước khi stop.
- Không kill session chỉ vì đồng hồ đã vượt maintenance window.

### 17.5. Rollback thay đổi database

Với patching, schema change hoặc data migration, rollback có thể cần restore, flashback, reverse script hoặc failback. Maintenance window chỉ là lịch thời gian; nó không tự cung cấp rollback. Phải thiết kế phương án theo loại thay đổi trước khi bắt đầu.

## 18. Các lỗi và hiểu nhầm thường gặp

**“Maintenance window là database downtime.”** Không. Scheduler window không tự đóng database hoặc ngăn kết nối ứng dụng.

**“Window mở nghĩa là tất cả auto task sẽ chạy.”** Không. Client, window, group, resource và điều kiện task đều ảnh hưởng.

**“DBMS_AUTO_TASK_ADMIN.DISABLE tắt toàn bộ Scheduler.”** Không. Nó chỉ điều khiển client auto task được chỉ định trong phạm vi.

**“DBMS_SCHEDULER.DISABLE(window) dừng mọi job đang chạy.”** Không nên giả định như vậy. Kiểm tra running jobs và thuộc tính job.

**“Auto stats chạy vào giờ cố định giống nhau ở mọi database.”** Không. Lịch window có thể đã được tùy chỉnh; kiểm tra DBA_SCHEDULER_WINDOWS.

**“Segment Advisor tự động shrink mọi segment.”** Không. Advisor đưa khuyến nghị; DBA đánh giá và thực hiện thao tác phù hợp.

**“SQL Tuning Advisor luôn bật và miễn phí license.”** Không. Trạng thái cấu hình và điều kiện licensing phải được xác minh.

**“Tăng duration bảo đảm job hoàn thành.”** Không. Job còn phụ thuộc workload, resource plan, lỗi và điều kiện dữ liệu.

**“Thêm custom window tự động đưa auto task vào lịch đó.”** Không. Cần kiểm tra membership MAINTENANCE_WINDOW_GROUP và trạng thái client.

**“Scheduler window thay thế maintenance change window của tổ chức.”** Không. Application drain, downtime, backup, patching và approval vẫn cần quy trình riêng.

**“Tắt auto stats vài ngày không ảnh hưởng.”** Có thể ảnh hưởng cardinality estimate và plan khi dữ liệu thay đổi; cần kế hoạch thay thế và bật lại.

**“Không thấy job trong cửa sổ là Scheduler lỗi.”** Chưa chắc. Client có thể disabled, task không cần chạy, job chưa đủ điều kiện hoặc window/resource policy không cho chạy.

## 19. Bài thực hành

Các bài tập nên chạy trong database test hoặc môi trường được DBA cho phép. Không thay đổi lịch maintenance mặc định của production chỉ để thực hành.

### Bài 1 — Khám phá window

Truy vấn DBA_SCHEDULER_WINDOWS. Ghi lại repeat interval, duration, resource plan, enabled và next start date.

### Bài 2 — Khám phá window group

Truy vấn DBA_SCHEDULER_WINDOW_GROUPS và DBA_SCHEDULER_WINGROUP_MEMBERS. Vẽ quan hệ MAINTENANCE_WINDOW_GROUP, WEEKNIGHT_WINDOW và WEEKEND_WINDOW.

### Bài 3 — Xác nhận timezone

So sánh SYSTIMESTAMP, CURRENT_TIMESTAMP, DBTIMEZONE, SESSIONTIMEZONE và NEXT_START_DATE. Giải thích timezone ảnh hưởng lịch như thế nào.

### Bài 4 — Kiểm tra auto task clients

Truy vấn DBA_AUTOTASK_CLIENT và phân loại client enabled/disabled. Ghi lại window group của từng client.

### Bài 5 — Kiểm tra task theo window

Dùng DBA_AUTOTASK_WINDOW_CLIENTS để xem optimizer stats, Segment Advisor và SQL Tuning Advisor được bật ở window nào.

### Bài 6 — Xem lịch sử auto task

Truy vấn DBA_AUTOTASK_JOB_HISTORY. Tìm task chạy lâu hoặc thất bại và đối chiếu thời gian với window log.

### Bài 7 — Quan sát Resource Manager

Khi window active trong môi trường test, xem DBA_SCHEDULER_WINDOWS và V$RSRC_PLAN. Xác định resource plan nào đang được áp dụng.

### Bài 8 — Tạo custom window

Tạo một window test vào thời gian được phép, xác nhận next_start_date và duration. Không thêm vào MAINTENANCE_WINDOW_GROUP nếu mục tiêu chỉ là chạy job test riêng.

### Bài 9 — Thay duration

Thay duration custom window từ bốn giờ xuống hai giờ. Đọc lại metadata và khôi phục giá trị ban đầu.

### Bài 10 — Bật/tắt một auto task trong test

Disable một client trong một window test, truy vấn DBA_AUTOTASK_WINDOW_CLIENTS, rồi enable lại. Ghi nhận khác biệt giữa client status và window status.

### Bài 11 — Job vận hành theo lịch

Tạo Scheduler job test disabled, kiểm tra action/owner/repeat interval, sau đó enable và xem job run details.

### Bài 12 — Xung đột workload

Chạy hai job test có I/O hoặc CPU khác nhau trong cùng khoảng. Quan sát elapsed time, CPU, I/O và tác động khi tách lịch.

### Bài 13 — Kiểm tra window log

Xem DBA_SCHEDULER_WINDOW_LOG trước và sau một lần mở/đóng window test. So sánh scheduled time và actual time.

### Bài 14 — Viết runbook

Thiết kế maintenance window cho một lần cập nhật schema. Ghi lịch, backup, dependency, resource budget, downtime, validation, rollback và người chịu trách nhiệm.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database Administrator's Guide 19c — Managing Automatic Maintenance Tasks](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-automatic-maintenance-tasks.html): các automatic maintenance task và cách quản lý.
- [Oracle Database Administrator's Guide 19c — Managing Scheduler Windows](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/scheduling-jobs-with-oracle-scheduler.html): window, schedule, job và Scheduler administration.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_AUTO_TASK_ADMIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_AUTO_TASK_ADMIN.html): enable/disable automatic maintenance task clients.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_SCHEDULER](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SCHEDULER.html): create/alter/enable/disable/open/close Scheduler windows and jobs.
- [Oracle Database Reference — DBA_SCHEDULER_WINDOWS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SCHEDULER_WINDOWS.html): metadata các Scheduler window.
- [Oracle Database Reference — DBA_AUTOTASK_CLIENT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_CLIENT.html): trạng thái automatic maintenance clients.
- [Oracle Database Reference — DBA_AUTOTASK_WINDOW_CLIENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_WINDOW_CLIENTS.html): trạng thái client theo maintenance window.
- [Oracle Database Reference — DBA_AUTOTASK_JOB_HISTORY](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_JOB_HISTORY.html): lịch sử job của automatic maintenance tasks.
- [Oracle Database Administrator's Guide — Managing Resource Manager](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-resources-with-oracle-database-resource-manager.html): resource plan và quản lý tài nguyên.
- [Oracle Database Licensing Information User Manual 19c](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/): điều kiện license cho các tính năng quản trị và tuning.

Maintenance window xác định thời điểm Scheduler cho phép các công việc bảo trì được lập lịch; Automatic Maintenance Tasks dùng window để chạy statistics collection, Segment Advisor và SQL Tuning Advisor theo trạng thái/cấu hình. DBA cần kiểm tra window, group membership, client status, resource plan, timezone và job history trước khi điều chỉnh. Với bảo trì hệ thống, Scheduler chỉ là một phần của kế hoạch: backup, application coordination, downtime, validation và rollback vẫn phải được quản lý riêng. **Lập lịch bảo trì tốt là chọn đúng thời điểm, giới hạn đúng tài nguyên, quan sát được kết quả và khôi phục cấu hình có kiểm soát.**
