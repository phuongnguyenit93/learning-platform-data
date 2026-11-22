# Auto statistics, stale statistics và thời điểm cập nhật

Oracle Optimizer dựa vào thống kê (optimizer statistics) để ước lượng số hàng, số giá trị phân biệt, độ chọn lọc của điều kiện lọc, kích thước dữ liệu và chi phí của các phương án thực thi. Nếu thống kê thiếu hoặc không còn phản ánh dữ liệu hiện tại, optimizer có thể chọn join order, join method, access path hoặc parallelism không phù hợp.

Oracle có cơ chế **automatic optimizer statistics collection** để tự thu thập thống kê cho các object thiếu hoặc có thống kê stale. Tuy nhiên, “auto statistics” không có nghĩa cứ có DML là Oracle lập tức gather stats, cũng không có nghĩa mọi thay đổi dữ liệu đều cần gather ngay. Oracle theo dõi mức độ thay đổi, đánh giá thống kê theo ngưỡng stale, rồi thực hiện tác vụ trong các maintenance window theo lịch và tài nguyên được cấp.

Bài học này trình bày:

- Optimizer statistics gồm những gì và vì sao thời điểm cập nhật quan trọng.
- Cách Oracle nhận diện statistics thiếu hoặc stale.
- STALE_PERCENT, DBA_TAB_MODIFICATIONS và DBA_TAB_STATISTICS.
- Automatic Optimizer Statistics Collection và maintenance windows.
- Cách theo dõi, bật/tắt và điều chỉnh AutoTask.
- Gọi DBMS_STATS thủ công sau bulk load hoặc thay đổi dữ liệu lớn.
- Thời điểm gather, locking, history, incremental stats và tác động đến execution plan.
- Lab kiểm tra stale stats và thực hành gather đúng thời điểm.

Các ví dụ dùng Oracle Database 19c. Một số tên view, preference và hành vi có thể thay đổi theo release; hãy đối chiếu tài liệu đúng phiên bản và kiểm tra trên môi trường thử nghiệm trước khi thay đổi lịch thu thập thống kê production.

## 1. Optimizer statistics là gì?

Optimizer statistics là metadata mô tả đặc điểm dữ liệu và object để cost-based optimizer (CBO) ước lượng chi phí thực thi SQL. Statistics không phải dữ liệu nghiệp vụ và cũng không phải execution plan; chúng là đầu vào cho quá trình optimizer chọn plan.

Các nhóm thống kê thường gặp:

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Ước lượng kích thước bảng và số hàng |
| Column statistics | NUM_DISTINCT, NUM_NULLS, LOW_VALUE, HIGH_VALUE, density | Ước lượng selectivity của predicate |
| Histogram | Frequency, height-balanced, top-frequency, hybrid | Mô tả phân bố lệch của giá trị cột |
| Index statistics | LEAF_BLOCKS, DISTINCT_KEYS, CLUSTERING_FACTOR, BLEVEL | Ước lượng chi phí truy cập index |
| Partition statistics | Thống kê từng partition và global | Tối ưu truy vấn partitioned table |
| System statistics | CPU speed, I/O characteristics | Ước lượng chi phí CPU và I/O |

Ví dụ, optimizer cần chọn giữa:

- Full table scan: đọc nhiều block liên tiếp.
- Index range scan: đọc index rồi truy cập các row tương ứng.
- Nested loops join: phù hợp khi outer row source nhỏ và inner lookup rẻ.
- Hash join: thường phù hợp khi join lượng dữ liệu lớn hơn.

Nếu NUM_ROWS, NDV hoặc histogram không phản ánh dữ liệu hiện tại, ước lượng cardinality có thể sai. Khi cardinality sai, các quyết định ở phía trên plan tree cũng có thể sai.

### 1.1. Statistics không phải lúc nào cũng cần cập nhật sau mỗi DML

Một INSERT nhỏ vào bảng vài triệu hàng có thể không làm thay đổi đáng kể ước lượng của đa số truy vấn. Ngược lại, một lần DELETE hoặc UPDATE tác động vào một nhóm giá trị quan trọng có thể làm phân bố dữ liệu thay đổi mạnh dù tổng số hàng không đổi nhiều.

Vì vậy, thời điểm gather cần xét:

- Tỷ lệ số hàng thay đổi.
- Kiểu thay đổi: INSERT, UPDATE hay DELETE.
- Phân bố dữ liệu có thay đổi đáng kể không.
- Cột nào được dùng trong predicate/join.
- Truy vấn quan trọng có nhạy với histogram/cardinality không.
- Chi phí gather và thời điểm workload chạy.

## 2. Missing statistics và stale statistics

Hai trạng thái quan trọng:

- **Missing statistics**: object chưa có thống kê cần thiết hoặc chưa từng được gather.
- **Stale statistics**: đã có thống kê, nhưng lượng thay đổi dữ liệu vượt ngưỡng mà Oracle dùng để xem thống kê không còn mới.

Automatic Optimizer Statistics Collection tìm object có thống kê thiếu hoặc stale để thu thập lại trong maintenance window.

### 2.1. STALE_PERCENT mặc định

Oracle mặc định xem table statistics là stale khi số hàng được INSERT, UPDATE hoặc DELETE vượt ngưỡng phần trăm của số hàng trong bảng tại lần gather gần nhất. Giá trị mặc định của preference STALE_PERCENT là 10%.

Ví dụ minh họa:

- Bảng có 100.000 hàng tại lần gather gần nhất.
- STALE_PERCENT là 10.
- Hơn khoảng 10.000 hàng bị thay đổi có thể khiến statistics được đánh dấu stale.

Đây là ngưỡng đánh giá, không phải lịch chạy gather. Khi vượt ngưỡng, Oracle có thể đánh dấu stale; AutoTask chỉ gather khi task được chạy và object đủ điều kiện.

Không diễn giải 10% như quy tắc rằng “cứ đúng 10% thì lập tức gather”. Bộ đếm thay đổi có thể chưa được flush vào dictionary, AutoTask có thể chưa đến maintenance window, task có thể bị disable hoặc object có statistics bị lock.

### 2.2. Thay đổi nào được theo dõi?

Oracle theo dõi các thay đổi DML như INSERT, UPDATE và DELETE để đánh giá statistics. Thông tin này được phản ánh qua các view modification như USER_TAB_MODIFICATIONS, ALL_TAB_MODIFICATIONS và DBA_TAB_MODIFICATIONS.

Các thao tác bulk load, truncate, partition maintenance hoặc exchange partition có thể có quy tắc/metadata riêng. Sau thao tác lớn, không nên chỉ dựa vào một con số modification đơn giản; hãy kiểm tra statistics ở cả table, partition và global level.

### 2.3. STALE_PERCENT là preference

Có thể xem preference hiện tại:

~~~sql
SELECT DBMS_STATS.GET_PREFS(
           'STALE_PERCENT',
           'HR',
           'EMPLOYEES'
       ) AS stale_percent
FROM dual;
~~~

Thay HR và EMPLOYEES bằng owner/table thực tế. Nếu table chưa có preference riêng, giá trị trả về có thể kế thừa từ cấp cao hơn hoặc default.

Đặt ngưỡng riêng cho một table:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'HR',
        tabname => 'EMPLOYEES',
        pname   => 'STALE_PERCENT',
        pvalue  => '15'
    );
END;
/
~~~

Ngưỡng 15% làm Oracle chờ tỷ lệ thay đổi lớn hơn trước khi xem table stale. Chỉ tăng ngưỡng khi đã hiểu workload và chấp nhận thời gian statistics có thể cũ lâu hơn. Giảm ngưỡng có thể làm gather thường xuyên hơn, tiêu tốn tài nguyên hơn.

Không thay đổi STALE_PERCENT toàn database chỉ để giải quyết một bảng có hành vi đặc biệt. Dùng table preference có phạm vi hẹp và ghi lại lý do.

## 3. Xem statistics và trạng thái stale

Oracle cung cấp các view dictionary để xem thống kê hiện tại.

### 3.1. USER_TAB_STATISTICS

~~~sql
SELECT
    table_name,
    num_rows,
    blocks,
    sample_size,
    last_analyzed,
    stale_stats,
    stattype_locked
FROM user_tab_statistics
ORDER BY table_name;
~~~

Các cột quan trọng:

- NUM_ROWS: số hàng ước lượng tại lần gather.
- BLOCKS: số block được thống kê.
- SAMPLE_SIZE: số hàng đã dùng làm mẫu.
- LAST_ANALYZED: thời điểm statistics được thu thập.
- STALE_STATS: YES/NO nếu Oracle đánh giá statistics stale.
- STATTYPE_LOCKED: trạng thái khóa statistics nếu có.

View USER_TAB_STATISTICS chỉ hiển thị object trong schema hiện tại. DBA có thể dùng DBA_TAB_STATISTICS; user có quyền phù hợp có thể dùng ALL_TAB_STATISTICS.

### 3.2. Xem thống kê của một bảng

~~~sql
SELECT
    owner,
    table_name,
    partition_name,
    num_rows,
    blocks,
    sample_size,
    last_analyzed,
    stale_stats,
    stattype_locked
FROM dba_tab_statistics
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY partition_name NULLS FIRST;
~~~

Với bảng không partition, PARTITION_NAME thường NULL. Với bảng partitioned, có thể có thống kê ở từng partition và thống kê global cho table; kiểm tra đúng cấp thống kê mà query sử dụng.

### 3.3. Xem column statistics

~~~sql
SELECT
    column_name,
    num_distinct,
    num_nulls,
    density,
    histogram,
    num_buckets,
    last_analyzed
FROM dba_tab_col_statistics
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY column_name;
~~~

Nếu truy vấn lọc theo STATUS hoặc DEPARTMENT_ID, column statistics và histogram của các cột này có thể ảnh hưởng trực tiếp tới cardinality estimate.

### 3.4. Xem index statistics

~~~sql
SELECT
    index_name,
    blevel,
    leaf_blocks,
    distinct_keys,
    clustering_factor,
    num_rows,
    last_analyzed
FROM dba_ind_statistics
WHERE owner = 'HR'
  AND table_name = 'EMPLOYEES';
~~~

Table statistics mới nhưng index statistics cũ vẫn có thể khiến optimizer ước lượng chi phí index không chính xác. DBMS_STATS với cascade phù hợp có thể thu thập cả index statistics.

## 4. DBA_TAB_MODIFICATIONS và bộ đếm thay đổi

DBA_TAB_MODIFICATIONS ghi nhận lượng thay đổi DML mà Oracle theo dõi cho table/partition. Các cột thường dùng gồm:

- INSERTS
- UPDATES
- DELETES
- TIMESTAMP
- TRUNCATED
- DROP_SEGMENTS
- TABLE_OWNER, TABLE_NAME, PARTITION_NAME

### 4.1. Xem modification counters

~~~sql
SELECT
    table_owner,
    table_name,
    partition_name,
    inserts,
    updates,
    deletes,
    timestamp,
    truncated
FROM dba_tab_modifications
WHERE table_owner = 'HR'
  AND table_name = 'EMPLOYEES'
ORDER BY partition_name;
~~~

USER_TAB_MODIFICATIONS là lựa chọn khi chỉ cần kiểm tra schema hiện tại.

### 4.2. Vì sao số liệu có thể chưa cập nhật ngay?

Thông tin modification có thể được ghi nhận bất đồng bộ và chưa được flush vào dictionary view tại thời điểm bạn truy vấn. Vì vậy, kết quả trống hoặc số lượng thấp không nhất thiết có nghĩa không có DML.

Để đồng bộ thông tin monitoring trước khi kiểm tra:

~~~sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

Thủ tục này flush modification monitoring information cho database. Nó không tự gather statistics cho tất cả bảng. Sau đó, truy vấn lại DBA_TAB_MODIFICATIONS và DBA_TAB_STATISTICS.

Quyền thực thi và phạm vi quan sát phụ thuộc tài khoản. Trong môi trường production, DBA cần cân nhắc tác động và quyền cần thiết trước khi chạy thao tác ở phạm vi database.

### 4.3. Modification counters không phải bảng audit DML

Các bộ đếm này phục vụ thống kê optimizer, không phải lịch sử chi tiết giao dịch. Chúng không cho biết user nào sửa hàng nào hoặc giá trị cũ/mới. Không dùng DBA_TAB_MODIFICATIONS để thay thế audit nghiệp vụ.

## 5. Automatic Optimizer Statistics Collection

Oracle có automated maintenance task tên **auto optimizer stats collection**. Task này kiểm tra object thiếu hoặc stale statistics và thu thập statistics theo chính sách nội bộ trong maintenance window.

### 5.1. Task chạy khi nào?

Trong Oracle 19c, automated maintenance tasks được lập lịch trong các maintenance window. Các window mặc định thường được định nghĩa theo lịch ngày/tuần và có thể được DBA điều chỉnh. Auto optimizer stats collection dùng thời gian/tài nguyên được cấp trong window; nó không nhất thiết chạy ngay khi một table vừa stale.

Luồng khái quát:

~~~text
DML / bulk load / partition maintenance
                |
                v
Oracle ghi nhận modification metadata
                |
                v
Statistics được đánh giá missing hoặc stale
                |
                v
Maintenance window bắt đầu
                |
                v
Auto Optimizer Stats Collection chọn object đủ điều kiện
                |
                v
DBMS_STATS thu thập statistics
                |
                v
Dictionary statistics được cập nhật
                |
                v
Optimizer dùng statistics mới cho hard parse phù hợp
~~~

Đây là luồng khái niệm. Việc chọn object, sample size, parallelism và thứ tự thực hiện do Oracle quản lý dựa trên trạng thái database và cấu hình.

### 5.2. Auto stats thường được bật mặc định

Kiểm tra trạng thái client:

~~~sql
SELECT
    client_name,
    status,
    window_group
FROM dba_autotask_client
ORDER BY client_name;
~~~

Tìm client có tên AUTO OPTIMIZER STATS COLLECTION. STATUS cho biết task được bật hay disable.

### 5.3. Kiểm tra task theo maintenance window

~~~sql
SELECT
    window_name,
    optimizer_stats,
    window_active
FROM dba_autotask_window_clients
ORDER BY window_name;
~~~

View DBA_AUTOTASK_WINDOW_CLIENTS cho biết client nào được bật trong từng window và window có đang active hay không. Tên cột có thể khác giữa các release; nếu view trong bản cài đặt có cấu trúc khác, xem ALL_TAB_COLUMNS hoặc Reference đúng phiên bản.

### 5.4. Kiểm tra lịch maintenance window

~~~sql
SELECT
    window_name,
    repeat_interval,
    duration,
    enabled,
    active
FROM dba_scheduler_windows
ORDER BY window_name;
~~~

Window disabled hoặc thời lượng quá ngắn có thể ảnh hưởng thời điểm task chạy. Không chỉnh lịch chỉ dựa vào suy đoán; xem lịch workload, maintenance window, Resource Manager plan và lịch backup/ETL.

### 5.5. Kiểm tra lịch sử AutoTask

Có thể xem lịch sử chạy của các automated maintenance task:

~~~sql
SELECT
    client_name,
    window_name,
    window_start_time,
    window_duration,
    job_status
FROM dba_autotask_job_history
ORDER BY window_start_time DESC;
~~~

Nếu view hoặc cột khác với phiên bản đang dùng, kiểm tra metadata dictionary. Có thể dùng DBA_AUTOTASK_CLIENT_HISTORY và các view Scheduler job run details để bổ sung thông tin.

Lịch sử giúp trả lời:

- Auto stats có được chạy trong window gần nhất không?
- Job hoàn tất hay bị lỗi?
- Window có đủ thời gian không?
- Task có bị disable hay bị giới hạn tài nguyên?
- Thống kê của object có thay đổi sau thời điểm job chạy không?

## 6. Maintenance window và thời điểm cập nhật

Maintenance window là khoảng thời gian database dành cho automated maintenance tasks. Auto stats cạnh tranh tài nguyên với các task khác và workload đang chạy; Resource Manager có thể giới hạn tài nguyên của maintenance task.

### 6.1. Vì sao không gather ngay sau mỗi DML?

Gather statistics có chi phí CPU, I/O và có thể đọc lượng lớn dữ liệu. Nếu gather liên tục sau từng batch nhỏ, database có thể dành quá nhiều tài nguyên cho statistics thay vì workload nghiệp vụ.

Oracle dùng modification tracking và maintenance window để cân bằng:

- Statistics đủ mới cho optimizer.
- Chi phí thu thập được gom vào thời điểm phù hợp.
- Nhiều object được xử lý trong một lần maintenance.
- Tài nguyên của workload chính được kiểm soát.

### 6.2. Maintenance window không bảo đảm mọi bảng được gather

Một object stale có thể chưa được gather ngay nếu:

- Auto optimizer stats collection bị disable.
- Window tương ứng bị disable hoặc không chạy.
- Window hết thời gian trước khi object được xử lý.
- Object statistics bị lock.
- Object không thuộc phạm vi task hoặc có điều kiện đặc biệt.
- Job lỗi hoặc bị resource limit.

Vì vậy, hãy kiểm tra cả trạng thái stale, task status, window và job history thay vì chỉ chờ.

### 6.3. Chọn thời điểm gather thủ công

Gather thủ công thường hợp lý khi:

- Vừa nạp một lượng dữ liệu lớn trước giờ workload quan trọng.
- Vừa truncate/reload hoặc thay đổi phân bố dữ liệu mạnh.
- Vừa hoàn tất ETL/partition exchange.
- Tạo bảng mới rồi chuẩn bị đưa vào truy vấn production.
- Có bằng chứng statistics cũ làm cardinality estimate sai.
- Cần kiểm thử plan trước khi mở workload hoặc release.

Tránh gather thủ công trên diện rộng vào giờ cao điểm nếu không có lý do và đánh giá tài nguyên. Với table rất lớn, hãy ước lượng thời gian, parallelism, I/O và tác động tới cursor plan trước khi chạy.

## 7. DBMS_STATS để cập nhật thủ công

DBMS_STATS là package chính để thu thập và quản lý optimizer statistics. Dùng AUTO_SAMPLE_SIZE thay cho tự chọn sample percent nếu không có yêu cầu đặc biệt.

### 7.1. Gather statistics cho một table

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'HR',
        tabname          => 'EMPLOYEES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Ý nghĩa:

- AUTO_SAMPLE_SIZE: Oracle chọn sample phù hợp.
- METHOD_OPT: quy định thu thập column statistics và histogram.
- AUTO_CASCADE: Oracle quyết định thu thập index statistics phù hợp.
- AUTO_DEGREE: Oracle chọn parallel degree.
- AUTO_INVALIDATE: Oracle quản lý invalidation dependent cursors theo chính sách tự động.

Các tham số có thể thay đổi theo phiên bản và workload. Không mặc định rằng gather với degree lớn nhất luôn nhanh hơn; parallel gather có thể cạnh tranh I/O/CPU.

### 7.2. Gather schema statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'HR',
        options          => 'GATHER AUTO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE
    );
END;
/
~~~

GATHER AUTO hướng tới object thiếu hoặc stale statistics theo quy tắc DBMS_STATS. Nó phù hợp hơn gather toàn bộ schema không cần thiết sau mỗi lần deploy. Dù vậy, hãy đánh giá phạm vi schema và thời lượng trước khi chạy trên production.

### 7.3. GATHER STALE và GATHER EMPTY

DBMS_STATS hỗ trợ các lựa chọn:

- GATHER: thu thập theo phạm vi yêu cầu.
- GATHER AUTO: thu thập object thiếu hoặc stale và áp dụng các quyết định tự động liên quan.
- GATHER STALE: thu thập object được đánh giá stale.
- GATHER EMPTY: thu thập object chưa có statistics.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'HR',
        options => 'GATHER STALE'
    );
END;
/
~~~

Hãy đọc DBMS_STATS Reference cho chính xác lựa chọn OPTIONS của procedure đang dùng. GATHER AUTO và GATHER STALE không đồng nghĩa hoàn toàn; AUTO có thể áp dụng logic tự động bổ sung cho missing/stale object.

### 7.4. Gather database statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_DATABASE_STATS(
        options          => 'GATHER AUTO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE
    );
END;
/
~~~

Đây là thao tác phạm vi rộng. Không chạy chỉ để “làm mới mọi thứ” nếu chỉ một bảng hoặc schema có vấn đề. Ưu tiên gather đúng object cần thiết và có kế hoạch tài nguyên.

### 7.5. Sau khi gather, kiểm tra lại

~~~sql
SELECT
    table_name,
    num_rows,
    sample_size,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'EMPLOYEES';
~~~

Kiểm tra thêm column/index statistics và execution plan của các SQL quan trọng. LAST_ANALYZED mới không tự chứng minh plan đã tốt hơn; phải so sánh cardinality estimate và runtime.

## 8. Gather statistics sau bulk load và ETL

Bulk load có thể làm phân bố dữ liệu thay đổi rất nhanh. Chờ maintenance window tiếp theo có thể quá muộn nếu ứng dụng bắt đầu truy vấn ngay sau load.

### 8.1. Sau direct-path load

Sau SQL*Loader direct path, INSERT /*+ APPEND */, CTAS hoặc bulk ETL, kiểm tra statistics có được thu thập tự động trong thao tác load hay không. Một số thao tác hỗ trợ online statistics gathering cho table statistics, nhưng không nên giả định mọi column histogram, index statistics và global/partition statistics đều đầy đủ.

Sau load:

1. Kiểm tra LAST_ANALYZED và STALE_STATS.
2. Kiểm tra NUM_ROWS và partition/global statistics.
3. Xem execution plan của query quan trọng.
4. Gather thủ công phần còn thiếu nếu cần.

### 8.2. Sau truncate và reload

TRUNCATE làm thay đổi số hàng về 0 nhưng không giống DELETE từng hàng. Khi reload một bảng, statistics cũ có thể không phản ánh số hàng mới. Nếu workload chạy ngay sau reload, gather phù hợp sau khi dữ liệu đã nạp xong.

### 8.3. Sau partition exchange

Partition exchange thường được dùng để nạp dữ liệu nhanh vào partition. Statistics ở partition, global table và index partition cần được xem xét. Với bảng partition lớn, incremental statistics có thể giúp cập nhật global stats mà không phải quét lại mọi partition.

### 8.4. Incremental statistics

Với partitioned table, incremental statistics sử dụng synopses để hỗ trợ duy trì global statistics từ partition statistics. Có thể cấu hình preference:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'DW',
        tabname => 'SALES',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
~~~

Incremental statistics hữu ích khi dữ liệu được nạp theo partition và chỉ một số partition thay đổi. Cần kiểm tra granularity, synopses, global stats và workload trước khi bật; không phải mọi kiểu partition maintenance đều được hưởng lợi như nhau.

## 9. Histogram và thay đổi phân bố dữ liệu

Table stale threshold chủ yếu dựa vào lượng modification, nhưng cardinality estimate còn phụ thuộc phân bố giá trị. Một cột có skew lớn có thể cần histogram.

Ví dụ cột ORDER_STATUS:

- 95% hàng là CLOSED.
- 4% hàng là PAID.
- 1% hàng là PENDING.

Truy vấn WHERE status = 'PENDING' có selectivity khác nhiều so với status = 'CLOSED'. Nếu optimizer chỉ dùng giả định phân bố đều, ước lượng có thể sai.

### 9.1. METHOD_OPT

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => 'APP',
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

SIZE AUTO cho phép Oracle quyết định histogram dựa trên workload/column usage và thống kê. Không nên tạo histogram cho mọi cột bằng SIZE 254 một cách máy móc; histogram có thể làm plan phụ thuộc giá trị bind và thay đổi plan giữa các truy vấn.

### 9.2. Khi row count thay đổi ít nhưng skew thay đổi mạnh

Ví dụ một đợt UPDATE chuyển phần lớn đơn hàng từ PENDING sang CLOSED. Tổng số hàng không đổi, nhưng phân bố STATUS thay đổi đáng kể. Modification tracking có thể xem UPDATE count để đánh giá stale, nhưng quyết định gather vẫn phụ thuộc ngưỡng và lịch.

Nếu truy vấn nhạy với STATUS và plan suy giảm, DBA có thể gather statistics sớm dù chưa chờ stale threshold mặc định.

## 10. Lock statistics và trường hợp không tự cập nhật

Oracle cho phép lock statistics để ngăn gather tự động hoặc thủ công ghi đè thống kê của object.

### 10.1. Kiểm tra trạng thái lock

~~~sql
SELECT
    table_name,
    stattype_locked,
    stale_stats,
    last_analyzed
FROM user_tab_statistics
WHERE stattype_locked IS NOT NULL;
~~~

### 10.2. Lock table statistics

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'HR',
        tabname => 'EMPLOYEES'
    );
END;
/
~~~

Statistics bị lock sẽ không được gather theo cách thông thường. Đây là công cụ hữu ích khi cần giữ stats đã kiểm chứng, nhưng có thể làm statistics trở nên cũ nếu dữ liệu tiếp tục thay đổi.

### 10.3. Unlock

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'HR',
        tabname => 'EMPLOYEES'
    );
END;
/
~~~

Sau unlock, object có thể được gather lại khi stale hoặc khi DBA yêu cầu. Không lock statistics chỉ để giữ execution plan mà không có quy trình kiểm soát và đánh giá tác động.

### 10.4. Khi cần giữ plan ổn định

Nếu mục tiêu là kiểm soát execution plan, hãy đánh giá SQL Plan Management (SQL Plan Baseline), SQL patch/profile và kiểm soát release thay vì phụ thuộc lâu dài vào statistics cũ. Lock stats là một công cụ đặc thù, không phải cơ chế quản trị plan toàn diện.

## 11. Statistics history và khả năng khôi phục

Oracle lưu lịch sử statistics trong một khoảng retention để có thể khôi phục statistics trước đó nếu lần gather mới làm plan xấu đi.

### 11.1. Xem statistics history

~~~sql
SELECT
    table_name,
    stats_update_time
FROM user_tab_stats_history
WHERE table_name = 'EMPLOYEES'
ORDER BY stats_update_time DESC;
~~~

View tương ứng ở cấp DBA/ALL có thể dùng để xem object ngoài schema hiện tại.

### 11.2. Khôi phục statistics theo timestamp

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'HR',
        tabname         => 'EMPLOYEES',
        as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY,
        force           => TRUE
    );
END;
/
~~~

Ví dụ minh họa khôi phục stats về thời điểm một ngày trước; phải chọn timestamp thực tế trước lần gather gây vấn đề. FORCE có thể ghi đè trạng thái lock trong một số trường hợp, nên không dùng tùy tiện.

### 11.3. Retention

Xem retention:

~~~sql
SELECT DBMS_STATS.GET_STATS_HISTORY_RETENTION
FROM dual;
~~~

Có thể điều chỉnh bằng DBMS_STATS.ALTER_STATS_HISTORY_RETENTION. Tăng retention làm tăng lượng metadata history cần lưu; chọn thời gian đủ cho quy trình điều tra và rollback statistics của tổ chức.

### 11.4. Khôi phục stats không phải rollback dữ liệu

RESTORE_TABLE_STATS khôi phục optimizer statistics. Nó không rollback INSERT/UPDATE/DELETE và không phục hồi dữ liệu bảng. Nếu cần khôi phục dữ liệu, dùng cơ chế backup/recovery hoặc Flashback phù hợp.

## 12. Statistics mới và execution plan

Khi statistics được publish, optimizer có thể dùng chúng cho hard parse tiếp theo. Cursor đang chạy không nhất thiết lập tức đổi plan; dependent cursor có thể bị invalidation theo chính sách no_invalidate.

### 12.1. AUTO_INVALIDATE

DBMS_STATS hỗ trợ no_invalidate => DBMS_STATS.AUTO_INVALIDATE. Đây là lựa chọn mặc định thường phù hợp để Oracle tự quản lý invalidation thay vì ép invalidate đồng loạt ngay lập tức.

Không nên đặt no_invalidate => FALSE trên schema lớn mà không đánh giá tác động, vì invalidating nhiều cursor có thể tạo hard parse spike.

### 12.2. Kiểm tra plan trước và sau

Có thể lấy plan bằng DBMS_XPLAN:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => 'your_sql_id',
        cursor_child_no => 0,
        format => 'ALLSTATS LAST +PEEKED_BINDS'
    )
);
~~~

So sánh:

- E-Rows và A-Rows.
- Access path.
- Join order và join method.
- Buffers, reads và elapsed time.
- Bind values nếu có.

Plan có E-Rows lệch xa A-Rows là dấu hiệu cardinality estimate có vấn đề, nhưng không phải lúc nào nguyên nhân cũng chỉ là stale statistics. Có thể cần xem predicate correlation, bind sensitivity, skew, dynamic sampling hoặc SQL transformation.

### 12.3. Pending statistics

Oracle hỗ trợ pending statistics để kiểm thử stats mới trước khi publish cho toàn workload:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'HR',
        tabname => 'EMPLOYEES',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );
END;
/
~~~

Sau khi gather, statistics có thể ở trạng thái pending. Có thể bật optimizer session để dùng pending stats khi thử:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

Sau khi đánh giá, publish hoặc delete pending statistics bằng các thủ tục DBMS_STATS phù hợp. Khi hoàn tất, khôi phục preference PUBLISH về TRUE nếu đó là chính sách ban đầu. Pending statistics là công cụ kiểm thử có kiểm soát; cần quản lý rõ ai đang thấy stats nào.

## 13. Real-time statistics và automatic statistics

Oracle Database 19c có tính năng Real-Time Statistics để bổ sung thông tin thống kê trong quá trình một số thao tác DML conventional. Tính năng này giúp optimizer có thông tin mới hơn giữa các lần gather statistics đầy đủ.

Real-time statistics không thay thế DBMS_STATS hoặc automatic optimizer stats collection:

- Auto stats task vẫn cần thu thập/publish statistics đầy đủ theo lịch.
- Real-time statistics có phạm vi và điều kiện hỗ trợ riêng.
- Không phải mọi loại object, DML, column statistics hoặc histogram đều được cập nhật như một lần gather đầy đủ.
- Hãy xem NOTES trong dictionary statistics và tài liệu 19c để biết stats nào được tạo từ conventional DML.

Không giả định rằng bật real-time statistics đồng nghĩa không cần gather stats sau bulk load, partition exchange hoặc thay đổi dữ liệu lớn.

## 14. Kiểm soát AutoTask

Thông thường nên để automatic optimizer stats collection hoạt động theo maintenance policy. Chỉ thay đổi trạng thái khi đã có kế hoạch vận hành rõ ràng.

### 14.1. Disable client

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

Lệnh này disable client ở phạm vi chỉ định. Không dùng trong production chỉ để tránh một job chạy vào thời điểm không thuận tiện; trước tiên hãy xem window, Resource Manager, job history và object gây tốn thời gian.

### 14.2. Enable lại

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

Sau thay đổi, kiểm tra lại DBA_AUTOTASK_CLIENT và DBA_AUTOTASK_WINDOW_CLIENTS. Nếu chỉ disable cho một window, phải truyền đúng window name khi enable lại.

### 14.3. Thay đổi duration/window

Có thể điều chỉnh lịch Scheduler window, nhưng điều đó ảnh hưởng nhiều automated maintenance tasks. DBA cần phối hợp với lịch backup, ETL, batch và workload. Không thay đổi duration chỉ dựa vào thời gian gather của một bảng.

## 15. Quy trình quyết định thời điểm gather

Một quy trình thực tế:

### Trước khi gather

1. Xác định SQL/workload bị ảnh hưởng.
2. Kiểm tra LAST_ANALYZED, STALE_STATS, NUM_ROWS và sample size.
3. Flush modification monitoring nếu cần xác nhận counters.
4. Xem table/partition/global statistics.
5. Kiểm tra statistics có bị lock không.
6. Xem auto stats task và maintenance window có chạy gần đây không.
7. Kiểm tra execution plan và cardinality estimate hiện tại.

### Chọn hành động

| Tình huống | Hành động gợi ý |
| --- | --- |
| Table nhỏ, DML ít, plan ổn | Chờ AutoTask |
| Table vừa vượt stale threshold, workload không gấp | Theo dõi AutoTask/window tiếp theo |
| Bulk load lớn, query chạy ngay sau load | Gather đúng table/partition trước workload |
| Plan xấu và E-Rows lệch lớn | Điều tra column stats/skew; gather có kiểm soát |
| Statistics bị lock | Xác định lý do lock, phối hợp owner trước khi unlock |
| Partition exchange | Kiểm tra partition/global/index stats; cân nhắc incremental |
| Gather mới làm plan xấu | So sánh plan, cân nhắc restore stats hoặc pending stats |
| AutoTask không chạy | Kiểm tra client status, window, history và resource plan |

### Sau khi gather

1. Kiểm tra LAST_ANALYZED và STALE_STATS.
2. Xem table, column, index và partition statistics.
3. Kiểm tra plan bằng DBMS_XPLAN.
4. Chạy workload đại diện và so sánh elapsed time/buffers.
5. Theo dõi hard parse và invalidation.
6. Ghi lại command, timestamp, options và kết quả.

## 16. Lab: quan sát stale statistics

Lab dùng bảng riêng để không ảnh hưởng dữ liệu nghiệp vụ.

### 16.1. Tạo bảng

~~~sql
CREATE TABLE lab_stats_orders (
    order_id NUMBER PRIMARY KEY,
    status VARCHAR2(20),
    amount NUMBER(12, 2),
    created_at DATE
);
~~~

### 16.2. Nạp dữ liệu

~~~sql
BEGIN
    FOR i IN 1 .. 10000 LOOP
        INSERT INTO lab_stats_orders (
            order_id,
            status,
            amount,
            created_at
        )
        VALUES (
            i,
            CASE WHEN MOD(i, 10) = 0 THEN 'PENDING' ELSE 'CLOSED' END,
            MOD(i, 5000) + 1,
            DATE '2025-01-01' + MOD(i, 365)
        );
    END LOOP;
    COMMIT;
END;
/
~~~

### 16.3. Gather baseline statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_STATS_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Kiểm tra:

~~~sql
SELECT
    table_name,
    num_rows,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_STATS_ORDERS';
~~~

### 16.4. Tạo thay đổi vượt ngưỡng

~~~sql
INSERT INTO lab_stats_orders (
    order_id,
    status,
    amount,
    created_at
)
SELECT
    10000 + LEVEL,
    'PENDING',
    9999,
    SYSDATE
FROM dual
CONNECT BY LEVEL <= 2500;

COMMIT;
~~~

Số hàng thêm vào tương đương khoảng 25% so với baseline 10.000 hàng. Nếu STALE_PERCENT mặc định 10%, table có khả năng được đánh dấu stale sau khi monitoring counters được cập nhật.

### 16.5. Flush và kiểm tra

~~~sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

~~~sql
SELECT
    table_name,
    inserts,
    updates,
    deletes,
    timestamp
FROM user_tab_modifications
WHERE table_name = 'LAB_STATS_ORDERS';
~~~

~~~sql
SELECT
    table_name,
    num_rows,
    last_analyzed,
    stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_STATS_ORDERS';
~~~

Quan sát counters và STALE_STATS. Kết quả có thể phụ thuộc phiên bản, timing và monitoring state; điều quan trọng là hiểu flush counters không đồng nghĩa gather.

### 16.6. Gather stale statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_STATS_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Kiểm tra LAST_ANALYZED, NUM_ROWS và STALE_STATS lần nữa. So sánh với baseline.

### 16.7. Thử threshold riêng

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_STATS_ORDERS',
        pname   => 'STALE_PERCENT',
        pvalue  => '30'
    );
END;
/
~~~

Thực hiện một lượng DML nhỏ hơn 30%, flush monitoring và quan sát stale state. Sau lab, có thể xóa preference riêng để quay về giá trị kế thừa:

~~~sql
BEGIN
    DBMS_STATS.DELETE_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_STATS_ORDERS',
        pname   => 'STALE_PERCENT'
    );
END;
/
~~~

## 17. Lab: kiểm tra AutoTask và lịch

Các truy vấn sau cần quyền dictionary phù hợp:

~~~sql
SELECT client_name, status, window_group
FROM dba_autotask_client
WHERE LOWER(client_name) LIKE '%optimizer stats%';
~~~

~~~sql
SELECT window_name, optimizer_stats, window_active
FROM dba_autotask_window_clients
ORDER BY window_name;
~~~

~~~sql
SELECT window_name, repeat_interval, duration, enabled, active
FROM dba_scheduler_windows
ORDER BY window_name;
~~~

~~~sql
SELECT client_name, window_name, window_start_time, job_status
FROM dba_autotask_job_history
ORDER BY window_start_time DESC;
~~~

Ghi lại client status, window status và job history. Nếu lab không có quyền DBA view, nhờ DBA cung cấp thông tin hoặc dùng các view ALL/USER tương ứng nếu có.

Không disable AutoTask trên database dùng chung để làm bài tập. Nếu cần thử enable/disable, chỉ làm trong database lab do bạn quản trị và bật lại sau khi quan sát.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Table stale nhưng chưa được gather | AutoTask chưa tới window hoặc bị disable | Kiểm tra client, window và job history |
| DML lớn nhưng STALE_STATS vẫn NO | Monitoring counters chưa flush hoặc ngưỡng chưa vượt | Flush monitoring rồi kiểm tra lại |
| LAST_ANALYZED mới nhưng plan vẫn xấu | Statistics không phản ánh skew/correlation hoặc SQL có vấn đề khác | Xem column stats, histogram và cardinality |
| Auto stats không cập nhật bảng | Statistics bị lock | Kiểm tra STATTYPE_LOCKED và lý do lock |
| Gather toàn schema mất quá lâu | Phạm vi quá rộng | Gather object stale hoặc object cần thiết |
| Plan đổi sau gather | Optimizer dùng cardinality/stats mới và chọn plan khác | So sánh plan/runtime, xem history/pending stats |
| Hard parse tăng sau gather | Cursor bị invalidation | Dùng AUTO_INVALIDATE và lập kế hoạch thời điểm |
| Sau bulk load query chạy chậm | AutoTask chưa chạy hoặc stats chưa đầy đủ | Gather table/partition trước workload |
| Partition stats mới nhưng global stats cũ | Chỉ gather partition mà không duy trì global stats | Xem granularity/incremental statistics |
| Modification counters bằng 0 | Monitoring metadata chưa flush hoặc object vừa gather | Flush và kiểm tra LAST_ANALYZED |
| STALE_PERCENT tăng làm job ít chạy | Threshold cao hơn | Đánh giá lại ngưỡng theo workload |
| Tạo histogram hàng loạt làm plan dao động | METHOD_OPT không phù hợp hoặc skew/bind sensitivity | Dùng SIZE AUTO và kiểm thử plan |
| Restore stats nhưng dữ liệu không đổi | Restore chỉ phục hồi statistics | Dùng recovery/flashback cho dữ liệu nếu cần |

## 19. Checklist vận hành

Trước khi kết luận Auto statistics không hoạt động:

- Kiểm tra NLS không liên quan; tập trung vào optimizer statistics dictionary.
- Xem DBA_TAB_STATISTICS và LAST_ANALYZED.
- Flush modification monitoring khi cần xác nhận bộ đếm.
- Kiểm tra DBA_TAB_MODIFICATIONS.
- Xem STALE_PERCENT table/global preference.
- Kiểm tra statistics có bị lock.
- Xem DBA_AUTOTASK_CLIENT.
- Kiểm tra DBA_AUTOTASK_WINDOW_CLIENTS và DBA_SCHEDULER_WINDOWS.
- Xem DBA_AUTOTASK_JOB_HISTORY và job error.
- Kiểm tra Resource Manager plan và thời lượng maintenance window.
- Sau gather, so sánh execution plan và runtime.
- Ghi lại thay đổi preference hoặc lịch để có thể hoàn tác.

## 20. Bài tập thực hành

Sử dụng LAB_STATS_ORDERS trong mục 16.

### Bài 1 — Baseline statistics

Gather statistics cho bảng lab. Ghi NUM_ROWS, BLOCKS, SAMPLE_SIZE và LAST_ANALYZED. Giải thích ý nghĩa từng cột.

### Bài 2 — Stale threshold

Thêm dữ liệu vượt 10% baseline. Flush monitoring rồi kiểm tra STALE_STATS và USER_TAB_MODIFICATIONS.

### Bài 3 — Table preference

Đặt STALE_PERCENT thành 30, thực hiện DML dưới ngưỡng, kiểm tra lại. Xóa table preference và xác nhận giá trị kế thừa.

### Bài 4 — GATHER AUTO và GATHER STALE

Chạy từng lựa chọn trên schema lab. Ghi object nào được gather và thời điểm LAST_ANALYZED. Giải thích khác biệt dựa trên DBMS_STATS Reference.

### Bài 5 — Histogram

Tạo phân bố STATUS lệch mạnh. Gather với SIZE AUTO, xem USER_TAB_COL_STATISTICS và truy vấn các giá trị phổ biến/hiếm. So sánh estimated rows.

### Bài 6 — Lock/unlock statistics

Lock stats của bảng lab, thực hiện DML vượt ngưỡng và quan sát. Unlock rồi gather. Chỉ thực hiện trong schema lab.

### Bài 7 — AutoTask

Truy vấn trạng thái auto optimizer stats collection, maintenance windows và job history. Viết nhận xét về thời điểm task có thể gather bảng lab.

### Bài 8 — Plan trước và sau gather

Chạy truy vấn lọc STATUS, xem DBMS_XPLAN.DISPLAY_CURSOR hoặc EXPLAIN PLAN trước và sau gather. So sánh cardinality, access path và runtime. Không kết luận chỉ dựa vào plan cost.

## 21. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
BEGIN
    DBMS_STATS.DELETE_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_STATS_ORDERS',
        pname   => 'STALE_PERCENT'
    );
END;
/

DROP TABLE lab_stats_orders PURGE;
~~~

Không xóa statistics hoặc thay đổi AutoTask của schema nghiệp vụ khi dọn lab. Nếu đã thay đổi preference khác, khôi phục giá trị ban đầu trước khi kết thúc.

## Tổng kết

Automatic Optimizer Statistics Collection tìm object thiếu hoặc stale statistics và thu thập trong maintenance window. Stale không đồng nghĩa gather ngay: Oracle dựa trên modification tracking và STALE_PERCENT, mặc định thường là 10%, còn thời điểm thực thi phụ thuộc AutoTask, window, resource và trạng thái object. DBA_TAB_MODIFICATIONS cho biết lượng INSERT/UPDATE/DELETE được theo dõi; FLUSH_DATABASE_MONITORING_INFO giúp đồng bộ counters trước khi kiểm tra. DBA_TAB_STATISTICS cho biết LAST_ANALYZED, STALE_STATS và trạng thái lock.

Sau bulk load, truncate/reload, partition exchange hoặc thay đổi phân bố dữ liệu lớn, có thể cần gather thủ công trước workload quan trọng thay vì chờ window kế tiếp. Dùng DBMS_STATS với AUTO_SAMPLE_SIZE và options phù hợp; xem xét histogram, index/partition/global stats, incremental stats và statistics lock. Statistics mới có thể làm thay đổi execution plan và invalidation cursor, vì vậy hãy so sánh cardinality estimate, runtime và history trước khi triển khai rộng. Auto stats là cơ chế bảo trì quan trọng, nhưng quyết định thời điểm gather vẫn cần dựa trên workload và tác động thực tế.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Tuning Guide — Gathering Optimizer Statistics (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/gathering-optimizer-statistics.html) — statistics, stale objects, automatic collection và DBMS_STATS.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — gather, preferences, history, locking và restore statistics.
- [Oracle Database Reference — DBA_TAB_STATISTICS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_STATISTICS.html) — table/partition statistics và STALE_STATS.
- [Oracle Database Reference — DBA_TAB_MODIFICATIONS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_TAB_MODIFICATIONS.html) — modification monitoring counters.
- [Oracle Database Reference — DBA_AUTOTASK_CLIENT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_CLIENT.html) — trạng thái automated maintenance clients.
- [Oracle Database Reference — DBA_AUTOTASK_WINDOW_CLIENTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_WINDOW_CLIENTS.html) — client theo maintenance window.
- [Oracle Database Reference — DBA_SCHEDULER_WINDOWS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SCHEDULER_WINDOWS.html) — lịch maintenance window.
- [Oracle Database Reference — DBA_AUTOTASK_JOB_HISTORY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_AUTOTASK_JOB_HISTORY.html) — lịch sử chạy automated maintenance task.
- [Oracle Database SQL Tuning Guide — Real-Time Statistics (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html) — thống kê optimizer và tính năng real-time statistics.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu SQL Tuning Guide, DBMS_STATS Reference và Data Dictionary Reference đúng phiên bản, đặc biệt stale threshold, AutoTask views, maintenance windows, incremental statistics và real-time statistics.
