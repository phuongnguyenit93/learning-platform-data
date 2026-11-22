# Pending statistics, khóa thống kê và phục hồi thống kê cũ

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Bộ tối ưu và thống kê  
> **Mục tiêu:** Hiểu vòng đời optimizer statistics trong Oracle; thu thập pending statistics để thử nghiệm trước khi công bố; bật pending statistics trong một session kiểm thử; publish hoặc xóa thống kê đang chờ; khóa và mở khóa statistics để kiểm soát việc tự động thu thập; phục hồi statistics cũ từ lịch sử hoặc statistics table; đánh giá ảnh hưởng đến execution plan, cursor invalidation và vận hành production.

## 1. Vì sao cần quản lý vòng đời statistics?

Oracle Optimizer sử dụng statistics để ước lượng số hàng, độ chọn lọc predicate, số block, phân bố giá trị và chi phí của các access path. Từ đó optimizer chọn execution plan cho SQL statement.

Statistics có thể thay đổi sau khi:

- Dữ liệu được nạp hoặc xóa hàng loạt.
- Phân bố giá trị trong cột thay đổi.
- Tạo hoặc thay đổi index.
- Partition được thêm, truncate, exchange hoặc nạp dữ liệu.
- Automatic statistics gathering chạy.
- DBA hoặc ứng dụng gọi DBMS_STATS.

Một bộ statistics mới thường giúp optimizer phản ánh dữ liệu hiện tại tốt hơn. Tuy nhiên, statistics mới cũng có thể khiến một số câu SQL chọn plan kém hơn, nhất là khi histogram, cardinality, bind value hoặc tương quan giữa các cột ảnh hưởng đến ước lượng.

Oracle cung cấp các cơ chế để kiểm soát thay đổi statistics:

1. **Pending statistics:** thu thập bộ statistics mới nhưng chưa công bố cho mọi session.
2. **Statistics lock:** khóa statistics của object để tránh bị thay đổi bởi lần gather thông thường.
3. **Statistics history và restore:** giữ lịch sử, rồi khôi phục bộ statistics tại một thời điểm trước đó.
4. **Statistics table export/import:** lưu bản sao statistics độc lập để backup hoặc di chuyển.

Các cơ chế này phục vụ mục đích khác nhau. Pending statistics là vùng thử nghiệm; lock ngăn cập nhật statistics; restore đưa metadata statistics về phiên bản trước. Không cơ chế nào tự rollback dữ liệu trong bảng.

## 2. Published statistics và pending statistics

Thông thường, sau khi DBMS_STATS thu thập statistics, bộ statistics mới được publish và trở thành bộ optimizer sử dụng cho các session theo cấu hình thông thường.

Pending statistics cho phép tách hai bước:

- Gather: tính toán và lưu bộ statistics mới ở trạng thái pending.
- Publish: công bố bộ statistics đó thành statistics chính thức.

Khi pending statistics chưa được publish, session thông thường tiếp tục dùng published statistics. Session kiểm thử có thể bật tham số OPTIMIZER_USE_PENDING_STATISTICS để thử kế hoạch dựa trên bộ pending.

Sơ đồ:

~~~text
Statistics đang được publish
          |
          | DBMS_STATS.GATHER_TABLE_STATS
          | với PUBLISH = FALSE
          v
Pending statistics
          |
          +---- Session thử nghiệm bật
          |     OPTIMIZER_USE_PENDING_STATISTICS = TRUE
          |             |
          |             v
          |       Đánh giá execution plan
          |
          +---- Nếu chấp nhận
          |       PUBLISH_PENDING_STATS
          |             |
          |             v
          |       Statistics mới được publish
          |
          +---- Nếu không chấp nhận
                  DELETE_PENDING_STATS
                          |
                          v
                  Published statistics giữ nguyên
~~~

Pending statistics hữu ích khi cần kiểm tra plan mới trên workload đại diện trước khi ảnh hưởng đến toàn hệ thống.

## 3. Thiết lập PUBLISH preference

DBMS_STATS có preference PUBLISH để quyết định statistics được gather sẽ tự động publish hay được lưu dưới dạng pending.

Mặc định, PUBLISH thường là TRUE. Có thể thay đổi preference ở cấp table:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );
END;
/
~~~

Sau khi đặt PUBLISH = FALSE, lần gather statistics tiếp theo cho bảng ORDERS tạo pending statistics thay vì tự động công bố.

Kiểm tra preference:

~~~sql
SELECT DBMS_STATS.GET_PREFS(
           pname   => 'PUBLISH',
           ownname => 'APP',
           tabname => 'ORDERS'
       ) AS publish_preference
FROM dual;
~~~

Có thể dùng preference ở các phạm vi khác nhau theo API DBMS_STATS, nhưng nên đặt ở phạm vi hẹp nhất phù hợp với mục tiêu thử nghiệm. Không thay đổi preference toàn database chỉ để thử một bảng.

### 3.1. Preference không phải trạng thái statistics

PUBLISH = FALSE chỉ quy định cách xử lý lần gather tiếp theo. Nó không tự chuyển published statistics hiện tại thành pending, cũng không xóa bộ statistics đã công bố.

Muốn tạo pending statistics, phải chạy một thao tác gather sau khi preference được đặt.

### 3.2. Trả preference về mặc định

Sau thử nghiệm, cần xem xét khôi phục preference ban đầu. Nếu trước đó PUBLISH là TRUE, có thể đặt lại:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'TRUE'
    );
END;
/
~~~

Nếu môi trường có preference riêng được quản lý tập trung, hãy khôi phục theo cấu hình chuẩn của DBA thay vì mặc định tự ý thay đổi.

## 4. Thu thập pending statistics

Ví dụ thu thập statistics cho ORDERS:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Nếu PUBLISH preference của bảng đang là FALSE, kết quả được lưu ở pending state.

Các tham số đáng chú ý:

- ESTIMATE_PERCENT: tỷ lệ lấy mẫu; AUTO_SAMPLE_SIZE để Oracle chọn phương pháp phù hợp.
- METHOD_OPT: chính sách thu thập column statistics và histogram.
- CASCADE: có thu thập index statistics hay không; AUTO_CASCADE để Oracle quyết định.
- NO_INVALIDATE: chính sách invalidation cursor phụ thuộc statistics.
- GRANULARITY: quan trọng với partitioned table, quyết định mức global/partition/subpartition statistics.
- DEGREE: mức parallelism khi gather, cần cân nhắc tải hệ thống.

Không dùng một bộ tham số giống nhau cho mọi bảng mà không xét workload, partitioning và data distribution.

### 4.1. Xem pending table statistics

Trong schema sở hữu bảng:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       sample_size,
       last_analyzed,
       global_stats,
       user_stats
FROM user_tab_pending_stats
WHERE table_name = 'ORDERS';
~~~

Các view theo phạm vi quyền gồm USER_TAB_PENDING_STATS, ALL_TAB_PENDING_STATS và DBA_TAB_PENDING_STATS. Dùng view tương ứng với quyền của tài khoản đang kiểm tra.

Pending index statistics có thể xem qua USER_IND_PENDING_STATS hoặc view ALL/DBA tương ứng.

Nếu view không có hàng cho ORDERS, có thể chưa có pending statistics, preference PUBLISH không được đặt như mong muốn, hoặc lần gather chưa tạo pending set.

### 4.2. So sánh published và pending

Có thể xem published table statistics:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       sample_size,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

Sau đó xem USER_TAB_PENDING_STATS để so sánh NUM_ROWS, BLOCKS, AVG_ROW_LEN và SAMPLE_SIZE.

Không so sánh chỉ một trường NUM_ROWS. Histogram, column density, index statistics, extended statistics và partition/global statistics cũng có thể làm plan thay đổi.

### 4.3. Pending statistics không phải backup

Pending set chỉ là bộ statistics chưa publish. Nó không thay thế stats history hoặc bản export. Nếu pending bị xóa hoặc bị thay thế bởi lần gather khác, không nên coi nó là bản sao lưu lâu dài của bộ statistics cũ.

## 5. Thử pending statistics trong session riêng

Để optimizer sử dụng pending statistics trong session kiểm thử:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

Tham số này có hiệu lực trong session hiện tại. Session khác vẫn dùng published statistics theo cấu hình thông thường.

Sau đó chạy các câu SQL đại diện cho workload cần đánh giá. Ví dụ:

~~~sql
SELECT /* test_pending_orders */
       customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM app.orders
WHERE status = 'OPEN'
  AND order_date >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

Xem execution plan và runtime statistics nếu có thể:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Để có actual row counts, cần thu thập runtime plan statistics bằng cách phù hợp trong môi trường kiểm thử, chẳng hạn GATHER_PLAN_STATISTICS hint hoặc cấu hình thống kê runtime được phê duyệt.

### 5.1. So sánh plan cũ và plan mới

Một quy trình thực tế:

1. Ghi nhận plan và thời gian của câu SQL khi dùng published statistics.
2. Trong session test, bật OPTIMIZER_USE_PENDING_STATISTICS.
3. Chạy lại cùng câu SQL với bind values và dữ liệu đại diện.
4. Ghi nhận estimated rows, actual rows, join order, access path, buffer gets và elapsed time.
5. Lặp lại với các bind values quan trọng.
6. So sánh kết quả với plan baseline/SQL Plan Management nếu hệ thống đang dùng.

Không chỉ nhìn cost estimate. Cost là ước lượng nội bộ của optimizer, không phải thời gian chạy thực tế. Cần đối chiếu actual rows, logical I/O, CPU, elapsed time và concurrency.

### 5.2. Tắt pending statistics trong session

Sau thử nghiệm, trả tham số session về FALSE:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = FALSE;
~~~

Hoặc kết thúc session test. Không để session dùng pending statistics ngoài phạm vi thử nghiệm vì kết quả có thể khác session ứng dụng production.

### 5.3. Pending statistics không mô phỏng mọi môi trường production

Plan còn chịu ảnh hưởng của:

- Bind values và bind peeking/adaptive cursor sharing.
- Optimizer parameters.
- System statistics.
- SQL Plan Baselines và SQL Profiles.
- Dynamic sampling.
- Schema/object metadata.
- Statistics của bảng join và index liên quan.
- Concurrency, cache và workload.

Vì vậy, một session test dùng pending statistics là bước kiểm soát hữu ích, nhưng không thay thế kiểm thử workload và release procedure đầy đủ.

## 6. Publish hoặc xóa pending statistics

Khi đã đánh giá và chấp nhận bộ statistics mới:

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Sau khi publish, pending set được công bố thành statistics chính thức. Các session thông thường có thể sử dụng statistics mới theo cơ chế cursor invalidation và optimizer.

Nếu plan mới không tốt, có thể xóa pending statistics:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Xóa pending statistics không xóa published statistics hiện tại.

### 6.1. Publish không phải rollback

PUBLISH_PENDING_STATS thay đổi bộ statistics chính thức. Nếu sau đó workload suy giảm, có thể dùng stats history để restore phiên bản cũ nếu còn trong retention, hoặc import từ statistics table backup.

Không nhầm DELETE_PENDING_STATS với RESTORE_TABLE_STATS: một thao tác xóa bản đang chờ; thao tác kia khôi phục bộ statistics đã lưu trong lịch sử.

### 6.2. Kiểm tra sau publish

Sau khi publish:

- Kiểm tra LAST_ANALYZED và các thống kê mới trong USER_TAB_STATISTICS.
- Kiểm tra pending view không còn bộ cần publish.
- Chạy workload kiểm thử bằng session không bật pending stats.
- Theo dõi SQL plan, elapsed time, buffer gets và lỗi.
- Theo dõi cursor invalidation/parse tăng nếu chính sách NO_INVALIDATE dẫn tới thay đổi cursor.

Không publish một bộ statistics chỉ vì số hàng hoặc sample size có vẻ hợp lý. Quyết định nên dựa trên plan và workload.

## 7. Statistics lock: khóa thống kê để tránh bị gather ghi đè

Statistics lock ngăn thao tác gather thông thường thay đổi statistics của object đã khóa. Nó thường được dùng khi DBA đã xác nhận một bộ statistics ổn định và muốn tránh automatic statistics gathering hoặc job khác ghi đè.

Khóa statistics của một bảng:

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Mở khóa:

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
~~~

Các API phạm vi rộng hơn gồm LOCK_SCHEMA_STATS/UNLOCK_SCHEMA_STATS và LOCK_DATABASE_STATS/UNLOCK_DATABASE_STATS. Dùng phạm vi rộng chỉ khi có chính sách vận hành rõ; khóa cả schema hoặc database có thể ảnh hưởng nhiều đối tượng và job thống kê.

### 7.1. Kiểm tra trạng thái lock

Xem table statistics:

~~~sql
SELECT table_name,
       stattype_locked,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

STATTYPE_LOCKED cho biết trạng thái khóa statistics theo loại. Các view partition/subpartition có trường trạng thái tương ứng tùy object.

Có thể kiểm tra index/table metadata bằng các view USER/ALL/DBA tương ứng. Nếu object có partition, kiểm tra cả mức table, partition và subpartition; không giả định khóa ở một mức có nghĩa mọi mức khác đang ở cùng trạng thái.

### 7.2. Lock statistics không khóa dữ liệu

LOCK_TABLE_STATS không ngăn INSERT, UPDATE hoặc DELETE trên ORDERS. Nó khóa việc thay đổi optimizer statistics theo cơ chế DBMS_STATS, không khóa hàng hay bảng cho DML ứng dụng.

Dữ liệu vẫn thay đổi trong khi statistics bị khóa. Theo thời gian, NUM_ROWS, NDV, histogram và clustering assumptions có thể trở nên stale so với dữ liệu thật.

Vì vậy, lock lâu dài có thể giữ plan ổn định trong ngắn hạn nhưng khiến optimizer ước lượng ngày càng sai khi dữ liệu tăng hoặc phân bố thay đổi.

### 7.3. Automatic statistics gathering và object bị khóa

Automatic statistics gathering thường không cập nhật object đã lock theo cơ chế thông thường. Điều này hữu ích để tránh job tự động thay đổi bộ statistics đã được quản trị.

Tuy nhiên, nếu bảng có tải dữ liệu lớn, stats lock có thể khiến statistics không còn phản ánh dữ liệu hiện tại. Phải có người chịu trách nhiệm theo dõi và mở khóa/gather khi cần.

## 8. Gather statistics khi object đang bị khóa

DBMS_STATS có tham số FORCE ở các thủ tục gather phù hợp để ghi đè trạng thái lock. Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        cascade => DBMS_STATS.AUTO_CASCADE,
        force => TRUE
    );
END;
/
~~~

FORCE = TRUE cho phép gather ngay cả khi statistics đang bị khóa. Đây là thao tác có chủ đích để vượt qua lock, không phải cách dùng mặc định.

Trước khi dùng FORCE:

- Xác định ai/điều gì đã khóa statistics.
- Xác nhận cần thay bộ statistics hiện tại.
- Ghi nhận bộ cũ hoặc xác nhận stats history còn khả dụng.
- Đánh giá ảnh hưởng đến execution plan.
- Lập kế hoạch publish, kiểm thử và rollback statistics nếu cần.

Không dùng FORCE chỉ để làm job hết lỗi ORA-20005 mà không hiểu lý do khóa.

### 8.1. ORA-20005 và object statistics locked

Khi DBMS_STATS cố gather object đang bị lock, có thể nhận lỗi ORA-20005 cho biết object statistics đang bị khóa. Kiểm tra STATTYPE_LOCKED và quy trình quản trị trước khi quyết định UNLOCK hoặc FORCE.

Không tự động mở khóa toàn bộ schema trong script xử lý lỗi. Một số lock có thể được đặt có chủ đích để bảo vệ plan của workload quan trọng.

## 9. Statistics history: Oracle giữ phiên bản cũ

Oracle có thể lưu lịch sử thay đổi table statistics. Khi cần quay lại bộ statistics trước đó, DBMS_STATS.RESTORE_TABLE_STATS có thể khôi phục từ stats history nếu phiên bản còn trong khoảng lưu giữ và chưa bị purge.

Xem lịch sử table statistics:

~~~sql
SELECT table_name,
       stats_update_time
FROM user_tab_stats_history
WHERE table_name = 'ORDERS'
ORDER BY stats_update_time DESC;
~~~

DBA có thể dùng DBA_TAB_STATS_HISTORY hoặc view phù hợp để xem object thuộc schema khác.

Lịch sử này là lịch sử statistics, không phải bản sao dữ liệu bảng. Nó lưu thông tin thống kê theo thời điểm, không lưu các hàng dữ liệu đã bị UPDATE/DELETE.

### 9.1. Kiểm tra thời gian retention

Có thể xem thời gian lưu lịch sử:

~~~sql
SELECT DBMS_STATS.GET_STATS_HISTORY_RETENTION() AS retention_days
FROM dual;
~~~

Có thể xem thời điểm cũ nhất còn khả dụng:

~~~sql
SELECT DBMS_STATS.GET_STATS_HISTORY_AVAILABILITY() AS oldest_available_time
FROM dual;
~~~

Thời gian retention có thể được cấu hình; không giả định mọi database đều giữ cùng số ngày. Stats history sử dụng tài nguyên repository trong database, thường liên quan SYSAUX, nên retention cần cân bằng giữa khả năng restore và dung lượng.

### 9.2. Thay đổi retention

Ví dụ đặt retention thành 45 ngày:

~~~sql
BEGIN
    DBMS_STATS.ALTER_STATS_HISTORY_RETENTION(45);
END;
/
~~~

Chỉ thay đổi khi có kế hoạch dung lượng và chính sách vận hành. Tăng retention có thể giữ nhiều metadata statistics hơn; giảm retention làm mất khả năng restore các mốc cũ sau khi purge.

### 9.3. Purge lịch sử cũ

DBMS_STATS.PURGE_STATS có thể xóa stats history cũ hơn một thời điểm:

~~~sql
BEGIN
    DBMS_STATS.PURGE_STATS(
        before_timestamp =>
            SYSTIMESTAMP - INTERVAL '45' DAY
    );
END;
/
~~~

Purge làm mất khả năng restore từ các mốc đã xóa. Không chạy purge tùy tiện trước khi xử lý một sự cố plan regression hoặc khi chưa xác nhận backup statistics khác.

## 10. Restore table statistics về thời điểm cũ

Giả sử lịch sử cho thấy bộ statistics tốt trước đây được cập nhật lúc một thời điểm đã xác định. Có thể khôi phục:

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'APP',
        tabname         => 'ORDERS',
        as_of_timestamp => TO_TIMESTAMP_TZ(
            '2026-11-13 18:30:00 +00:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        force           => TRUE
    );
END;
/
~~~

Thay timestamp ví dụ bằng thời điểm thực tế lấy từ USER_TAB_STATS_HISTORY/DBA_TAB_STATS_HISTORY và xác nhận múi giờ.

RESTORE_TABLE_STATS phục hồi statistics của bảng từ history. Tham số FORCE có thể cho phép restore trong tình huống statistics đang bị khóa; chỉ dùng khi có chủ đích và quyền phù hợp.

### 10.1. Restore schema hoặc database statistics

DBMS_STATS còn cung cấp các thủ tục restore ở phạm vi rộng hơn như RESTORE_SCHEMA_STATS và RESTORE_DATABASE_STATS. Chúng có thể ảnh hưởng nhiều object; phải xác định chính xác phạm vi và thời điểm trước khi gọi.

Không dùng restore database chỉ để sửa một bảng. Bắt đầu bằng restore table stats nếu sự cố giới hạn ở một object và dependency của nó.

### 10.2. Restore statistics không khôi phục dữ liệu

Giả sử trước đây ORDERS có 1 triệu hàng và hiện tại có 5 triệu hàng. Restore stats về thời điểm cũ có thể làm optimizer thấy NUM_ROWS cũ, nhưng bảng vẫn có 5 triệu hàng.

Điều này có thể hữu ích nếu bộ statistics mới tạo plan xấu, nhưng cũng có thể làm cardinality estimate sai so với dữ liệu hiện tại. Cần kiểm tra plan và actual row counts sau restore.

Không nhầm RESTORE_TABLE_STATS với FLASHBACK TABLE, Flashback Query hoặc point-in-time recovery. Chúng là các cơ chế phục hồi dữ liệu khác nhau.

### 10.3. Ảnh hưởng cursor invalidation

Sau khi statistics thay đổi, cursor phụ thuộc có thể cần được invalidated hoặc được xử lý theo policy NO_INVALIDATE. Việc invalidation có thể làm tăng hard parse khi workload tiếp tục.

DBMS_STATS hỗ trợ chính sách NO_INVALIDATE ở nhiều thủ tục:

- DBMS_STATS.AUTO_INVALIDATE: Oracle quyết định thời điểm invalidation.
- TRUE: không invalidate cursor theo thao tác đó.
- FALSE: invalidate ngay các cursor phụ thuộc theo semantics của API.

Cần đối chiếu signature và hành vi của thủ tục trong Oracle release đang dùng. Không đặt FALSE hàng loạt trong production nếu chưa đánh giá parse storm.

## 11. Export/import statistics bằng statistics table

Stats history có retention và có thể bị purge. Với thay đổi quan trọng, có thể export statistics vào một bảng riêng để lưu bản backup độc lập.

Tạo statistics table:

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => 'APP',
        stattab => 'STAT_BACKUP'
    );
END;
/
~~~

Export statistics của bảng ORDERS:

~~~sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STAT_BACKUP',
        statid  => 'BEFORE_RELEASE'
    );
END;
/
~~~

Khi cần import lại:

~~~sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STAT_BACKUP',
        statid  => 'BEFORE_RELEASE',
        cascade => TRUE,
        force   => TRUE
    );
END;
/
~~~

Tên tham số và tùy chọn chi tiết cần kiểm tra theo DBMS_STATS package specification của release. Statistics table phải được tạo và truy cập bởi owner/đối tượng có quyền phù hợp.

Export/import hữu ích khi:

- Muốn giữ snapshot trước release hoặc data migration.
- Stats history không đủ retention.
- Muốn chuyển statistics giữa môi trường theo quy trình kiểm soát.
- Cần phục hồi stats đã export sau khi thay đổi lớn.

Statistics table không phải backup dữ liệu nghiệp vụ và không thay thế RMAN/backup database.

## 12. Quy trình xử lý plan regression bằng statistics

Khi một câu SQL chậm đi sau khi gather statistics:

1. Ghi nhận SQL_ID, child cursor, plan hash value và thời điểm bắt đầu suy giảm.
2. Xác định object statistics nào thay đổi gần thời điểm đó.
3. Kiểm tra DBA_TAB_STATS_HISTORY và DBA_OPTSTAT_OPERATIONS.
4. So sánh NUM_ROWS, NDV, histogram, index stats, global/partition stats.
5. Dùng pending statistics hoặc môi trường clone để thử phương án mới.
6. Nếu xác định bộ cũ tốt hơn, restore từ history hoặc import backup.
7. Kiểm tra cursor invalidation và hard parse sau restore.
8. Chạy lại workload đại diện và xác nhận actual row counts.
9. Theo dõi sau thay đổi để phát hiện plan regression tái diễn.

Không restore stats chỉ vì plan hash value khác. Plan mới có thể khác nhưng nhanh hơn; cần so sánh hiệu năng và workload.

### 12.1. Xem operation thu thập statistics

Các view DBA_OPTSTAT_OPERATIONS và DBA_OPTSTAT_OPERATION_TASKS cung cấp thông tin về thao tác statistics tùy release và quyền. Có thể dùng chúng để xác định thời điểm job gather, object liên quan, trạng thái và thời lượng.

Ví dụ truy vấn tổng quan:

~~~sql
SELECT *
FROM dba_optstat_operations
ORDER BY start_time DESC;
~~~

Tên cột có thể khác theo release; kiểm tra data dictionary reference trước khi viết script vận hành cố định.

## 13. Statistics của partitioned table

Với bảng partitioned, statistics có thể tồn tại ở nhiều cấp:

- Table/global statistics.
- Partition statistics.
- Subpartition statistics.
- Index và index partition statistics.

Một lần gather partition statistics có thể làm thay đổi cả global stats tùy GRANULARITY, INCREMENTAL và các preference liên quan.

Nếu chỉ restore hoặc lock table statistics mà không hiểu partition state, optimizer có thể tiếp tục dùng bộ global/partition statistics không đồng nhất với mục tiêu.

### 13.1. Kiểm tra partition statistics

~~~sql
SELECT partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
WHERE table_name = 'ORDERS'
  AND object_type = 'PARTITION'
ORDER BY partition_name;
~~~

Tùy view và release, metadata partition có thể được truy vấn thêm qua USER_TAB_PARTITIONS hoặc USER_TAB_STATISTICS. Xem cả global row và partition row khi đánh giá.

### 13.2. Gather với GRANULARITY phù hợp

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname     => 'APP',
        tabname     => 'ORDERS',
        granularity => 'AUTO',
        cascade     => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

GRANULARITY AUTO để Oracle chọn mức thu thập phù hợp theo cấu trúc và preference. Các lựa chọn khác gồm GLOBAL, PARTITION, SUBPARTITION và các kết hợp theo API/release.

Với incremental statistics, Oracle có thể duy trì global statistics từ synopsis của partition để giảm chi phí gather toàn bảng. Cần kiểm tra preference INCREMENTAL và cấu trúc partition trước khi thay đổi.

### 13.3. Restore/lock partition stats

DBMS_STATS cung cấp thủ tục và tham số phù hợp để quản lý statistics ở mức partition. Khi có sự cố chỉ ở một partition, tránh restore hoặc gather toàn bảng nếu không cần.

Phải kiểm tra global stats sau khi thay đổi partition stats vì global statistics có thể cần được tính lại hoặc đồng bộ theo chính sách.

## 14. Lock, pending và restore: ba cơ chế không thay thế nhau

| Cơ chế | Mục đích | Tác động |
|---|---|---|
| Pending statistics | Thử statistics mới trước khi công bố | Chỉ session bật optimizer_use_pending_statistics dùng pending set |
| Statistics lock | Ngăn gather thông thường thay đổi stats | Statistics được bảo vệ; dữ liệu vẫn tiếp tục thay đổi |
| Restore statistics | Khôi phục bộ stats cũ từ history | Thay statistics hiện tại bằng phiên bản đã lưu |
| Export/import statistics | Backup và nạp lại stats từ statistics table | Lưu/khôi phục bản stats độc lập với history |

Ví dụ một release có thể dùng cả ba:

1. Export stats cũ để backup.
2. Set PUBLISH = FALSE.
3. Gather pending stats.
4. Test pending stats trong session riêng.
5. Publish nếu plan tốt.
6. Lock stats sau khi ổn định nếu chính sách yêu cầu.
7. Nếu có regression, unlock hoặc restore theo quy trình, kiểm tra plan.
8. Sau khi đã ổn định, quyết định lock lại hay để automatic stats gathering quản lý.

Không lock statistics trước khi gather pending nếu quy trình dự kiến cần gather thường và không dùng FORCE; lock có thể làm gather bị từ chối. Hãy xác định thứ tự thao tác trước.

## 15. Lỗi và lưu ý thường gặp

| Tình huống | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không thấy pending stats | PUBLISH vẫn TRUE hoặc chưa gather | Kiểm tra GET_PREFS và USER_TAB_PENDING_STATS |
| Session test vẫn dùng plan cũ | Chưa bật OPTIMIZER_USE_PENDING_STATISTICS | Kiểm tra tham số session |
| Session khác thấy plan mới trước khi publish | Có thay đổi stats khác hoặc test nhầm session/setting | Kiểm tra published stats và session parameter |
| Publish pending nhưng plan không đổi | Cursor, baseline, bind, optimizer setting hoặc predicate khác | Kiểm tra child cursor và DBMS_XPLAN |
| DELETE_PENDING_STATS không khôi phục plan cũ | Nó chỉ xóa pending set | Restore từ stats history/backup nếu đã publish |
| ORA-20005 | Object statistics đang locked | Kiểm tra STATTYPE_LOCKED; quyết định unlock hoặc FORCE |
| Gather chạy nhưng stats không đổi | Object locked, preference pending hoặc gather không có dữ liệu phù hợp | Kiểm tra preference, pending view và operation history |
| Restore không tìm thấy mốc cũ | History đã hết retention hoặc bị purge | Dùng statistics table backup nếu có |
| Restore stats nhưng SQL vẫn chậm | Dữ liệu/plan factors khác hoặc cursor chưa được xử lý như mong đợi | Kiểm tra plan, actual rows, invalidation và bind |
| Lock stats quá lâu | Dữ liệu tiếp tục thay đổi | Theo dõi stale stats và lập lịch unlock/gather |
| Hard parse tăng sau publish/restore | Cursor invalidation | Đánh giá NO_INVALIDATE và rollout |
| Partition stats không khớp global stats | Gather/restore ở các mức khác nhau | Kiểm tra granularity, incremental và partition metadata |

## 16. Lab: thử pending statistics

Chỉ thực hiện trong schema lab.

### 16.1. Tạo bảng có phân bố dữ liệu rõ

~~~sql
CREATE TABLE lab_orders AS
SELECT level AS order_id,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'RARE'
           ELSE 'COMMON'
       END AS status,
       MOD(level, 1000) AS customer_id,
       TRUNC(SYSDATE) - MOD(level, 365) AS order_date
FROM dual
CONNECT BY level <= 100000;

CREATE INDEX lab_orders_status_ix
ON lab_orders(status);
~~~

Thu thập statistics ban đầu và publish:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        cascade => TRUE
    );
END;
/
~~~

### 16.2. Thay đổi dữ liệu và đặt PUBLISH FALSE

~~~sql
UPDATE lab_orders
SET status = 'RARE'
WHERE order_id BETWEEN 1 AND 20000;

COMMIT;

BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'FALSE'
    );
END;
/
~~~

Gather lại:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Kiểm tra USER_TAB_STATS_HISTORY, USER_TAB_STATISTICS và USER_TAB_PENDING_STATS để thấy published/pending state.

### 16.3. So sánh hai session

Session A (mặc định):

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = FALSE;

SELECT COUNT(*)
FROM lab_orders
WHERE status = 'RARE';
~~~

Session B (test pending):

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;

SELECT COUNT(*)
FROM lab_orders
WHERE status = 'RARE';
~~~

Xem plan cho cùng query ở mỗi session. Có thể cần gather runtime plan stats và xem cursor tương ứng bằng DBMS_XPLAN.DISPLAY_CURSOR.

### 16.4. Publish hoặc xóa pending

Nếu chấp nhận:

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

Nếu không chấp nhận:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

Cuối cùng khôi phục preference PUBLISH theo cấu hình lab mong muốn.

## 17. Lab: lock và restore statistics

### 17.1. Lock table statistics

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

Kiểm tra:

~~~sql
SELECT table_name, stattype_locked, last_analyzed
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';
~~~

Thử gather thông thường và quan sát lỗi nếu statistics bị lock.

### 17.2. Unlock

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

### 17.3. Xem lịch sử và restore

~~~sql
SELECT table_name, stats_update_time
FROM user_tab_stats_history
WHERE table_name = 'LAB_ORDERS'
ORDER BY stats_update_time DESC;
~~~

Chọn một timestamp lịch sử phù hợp rồi gọi:

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        as_of_timestamp => TO_TIMESTAMP_TZ(
            '2026-11-13 18:30:00 +00:00',
            'YYYY-MM-DD HH24:MI:SS TZH:TZM'
        ),
        force => TRUE
    );
END;
/
~~~

Timestamp ở trên chỉ là ví dụ định dạng. Thay bằng thời điểm thực tế có trong history của lab.

Sau restore, kiểm tra USER_TAB_STATISTICS, execution plan và kết quả query. Nhớ rằng số hàng thực tế không thay đổi vì chỉ statistics được phục hồi.

## 18. Checklist vận hành

- [ ] Ghi nhận plan và statistics hiện tại trước thay đổi.
- [ ] Kiểm tra stats history retention và thời điểm cũ nhất còn khả dụng.
- [ ] Export stats quan trọng ra statistics table nếu cần backup độc lập.
- [ ] Dùng PUBLISH = FALSE ở phạm vi table khi muốn thử nghiệm.
- [ ] Gather pending statistics với method/estimate/cascade phù hợp.
- [ ] Xem USER_TAB_PENDING_STATS và USER_IND_PENDING_STATS.
- [ ] Bật OPTIMIZER_USE_PENDING_STATISTICS trong session test riêng.
- [ ] Kiểm thử SQL đại diện, bind values và actual row counts.
- [ ] Publish chỉ sau khi đánh giá workload.
- [ ] Xóa pending set nếu không chấp nhận.
- [ ] Khôi phục PUBLISH preference theo chính sách.
- [ ] Kiểm tra STATTYPE_LOCKED trước khi gather.
- [ ] Chỉ lock stats khi có lý do và kế hoạch cập nhật lại.
- [ ] Không dùng FORCE để vượt lock nếu chưa có phê duyệt/backup.
- [ ] Restore từ history đúng timestamp và đúng object scope.
- [ ] Phân biệt restore statistics với restore dữ liệu.
- [ ] Theo dõi cursor invalidation, hard parse và plan sau thay đổi.
- [ ] Với partitioned table, kiểm tra global, partition và subpartition stats.
- [ ] Ghi lại thay đổi DBMS_STATS trong runbook/migration.
- [ ] Kiểm thử trên môi trường đại diện trước khi thao tác production.

## 19. Ghi nhớ cốt lõi

- Optimizer statistics ảnh hưởng cardinality estimate và execution plan; thay đổi statistics có thể làm SQL nhanh hơn hoặc chậm hơn.
- Pending statistics cho phép gather trước, test trong session riêng rồi mới publish.
- PUBLISH preference FALSE làm lần gather tiếp theo tạo pending statistics thay vì công bố ngay.
- OPTIMIZER_USE_PENDING_STATISTICS = TRUE chỉ bật việc dùng pending statistics trong session thử nghiệm.
- PUBLISH_PENDING_STATS công bố bộ pending; DELETE_PENDING_STATS xóa bộ pending và giữ published statistics hiện tại.
- Statistics lock ngăn gather thông thường thay đổi stats; nó không khóa dữ liệu hay ngăn DML.
- STATTYPE_LOCKED giúp kiểm tra trạng thái lock; ORA-20005 thường báo object statistics đang bị khóa.
- FORCE = TRUE có thể vượt lock trong thao tác DBMS_STATS phù hợp; chỉ dùng có chủ đích.
- USER_TAB_STATS_HISTORY/DBA_TAB_STATS_HISTORY lưu mốc statistics cũ theo retention.
- RESTORE_TABLE_STATS khôi phục metadata statistics từ history, không phục hồi các hàng dữ liệu.
- Statistics history retention có thể cấu hình và purge; đừng giả định mọi mốc cũ đều còn.
- Statistics table export/import cung cấp bản sao statistics độc lập với stats history.
- NO_INVALIDATE ảnh hưởng cách cursor phụ thuộc statistics được invalidated; cần đánh giá hard parse.
- Partitioned table cần quản lý global, partition và subpartition statistics nhất quán.
- Pending, lock, restore và export/import là các cơ chế khác nhau; chọn theo mục tiêu và lập kế hoạch rollback rõ ràng.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — SET_TABLE_PREFS, GATHER_TABLE_STATS, pending statistics, lock/unlock, restore và statistics table.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — Optimizer statistics, cardinality estimates, execution plans và statistics management.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — USER_TAB_STATISTICS, USER_TAB_PENDING_STATS, USER_TAB_STATS_HISTORY, DBA_OPTSTAT_OPERATIONS và các dictionary views.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Automatic maintenance tasks, SYSAUX và database space management.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — Display execution plans và runtime plan statistics.

DBMS_STATS signatures, pending-statistics behavior, dictionary columns và partition options có thể khác theo Oracle release. Đối chiếu package specification/tài liệu đúng phiên bản; thử publish, lock, restore và cursor behavior trên schema lab trước khi thay đổi statistics production.

