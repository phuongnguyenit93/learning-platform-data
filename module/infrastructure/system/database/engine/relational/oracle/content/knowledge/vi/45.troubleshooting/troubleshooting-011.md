# ORA-01000, ORA-04030, ORA-04031 và tài nguyên cursor/bộ nhớ

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Xử lý sự cố  
> **Mục tiêu:** Phân biệt ba lỗi tài nguyên thường gặp trong Oracle; chẩn đoán giới hạn open cursor theo session, bộ nhớ riêng của process và vùng nhớ SGA; tìm nguồn rò rỉ cursor trong PL/SQL, JDBC, connection pool và ORM; phân tích PGA/SGA pressure; điều chỉnh tham số và workload có căn cứ; xây dựng runbook xử lý sự cố và phòng ngừa tái diễn.

## 1. Phân biệt ba lỗi trước khi xử lý

ORA-01000, ORA-04030 và ORA-04031 đều có thể xuất hiện khi workload tăng, nhưng chúng báo ba loại giới hạn khác nhau:

| Lỗi | Tài nguyên bị thiếu/đạt giới hạn | Phạm vi thường gặp | Hướng điều tra chính |
|---|---|---|---|
| ORA-01000: maximum open cursors exceeded | Số cursor mở vượt OPEN_CURSORS | Một database session | Cursor leak, statement/result set chưa đóng, số cursor đồng thời |
| ORA-04030: out of process memory | Process không cấp phát được bộ nhớ riêng | Một Oracle process | PGA/process memory, workarea, PL/SQL collection, OS memory |
| ORA-04031: unable to allocate bytes of shared memory | Không cấp phát được vùng nhớ trong SGA pool | SGA pool/instance | Shared pool/large pool, fragmentation, hard parse, pool sizing |

Ba lỗi có thể liên quan. Ví dụ ứng dụng mở quá nhiều cursor có thể làm tăng private session/process memory và shared SQL cursor usage. Tuy nhiên, tăng OPEN_CURSORS không sửa được ORA-04030 do PGA tăng quá mức, và tăng PGA_AGGREGATE_TARGET không sửa được ORA-04031 do shared pool thiếu vùng cấp phát.

**Luôn xác định đúng tài nguyên và process/session trước khi thay tham số.**

## 2. Cursor trong Oracle là gì?

Cursor là handle và trạng thái thực thi mà session dùng để làm việc với SQL hoặc PL/SQL statement. Một SQL statement được parse và thực thi qua các cấu trúc cursor; ứng dụng JDBC thường tạo cursor tương ứng khi tạo Statement, PreparedStatement hoặc CallableStatement.

Cần phân biệt:

- **SQL cursor/shared cursor:** phần thông tin SQL đã parse và có thể được chia sẻ trong library cache của SGA.
- **Session cursor:** trạng thái cursor mà một session sử dụng, bao gồm handle và trạng thái thực thi riêng.
- **Open cursor:** cursor đang được session giữ mở.
- **Cached cursor:** cursor đã đóng ở phía ứng dụng nhưng được giữ trong session cursor cache để tái sử dụng theo cấu hình.
- **REF CURSOR:** cursor variable được PL/SQL trả cho client hoặc caller; caller cần tiêu thụ và đóng result set đúng vòng đời.

Một câu SQL giống nhau có thể dùng shared SQL area chung, nhưng mỗi session vẫn có trạng thái cursor riêng. Vì vậy, nhiều session chạy cùng SQL không có nghĩa tất cả dùng chung một open cursor handle.

### 2.1. Vòng đời SQL/JDBC cursor

Một flow đơn giản:

~~~text
Connection / Session
       |
       v
Prepare SQL
       |
       v
Parse / cursor handle
       |
       v
Execute
       |
       v
Fetch rows
       |
       v
Close ResultSet
       |
       v
Close Statement
       |
       v
Cursor resources released or cached
~~~

Khi ứng dụng không đóng ResultSet/Statement, session có thể giữ cursor lâu hơn dự kiến. Lặp qua hàng nghìn request hoặc vòng lặp batch có thể dần chạm OPEN_CURSORS.

## 3. ORA-01000: maximum open cursors exceeded

ORA-01000 xảy ra khi một session mở số cursor vượt giới hạn OPEN_CURSORS được cấu hình cho instance/database. Giới hạn được áp dụng theo session; đây không phải tổng số cursor toàn database.

### 3.1. OPEN_CURSORS

Xem giá trị hiện tại:

~~~sql
SHOW PARAMETER open_cursors;
~~~

Hoặc:

~~~sql
SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name = 'open_cursors';
~~~

OPEN_CURSORS quy định số cursor mà một session có thể mở đồng thời. Giá trị cần đủ cho workload thực tế, bao gồm statement của ứng dụng, PL/SQL, framework và các cursor hoạt động đồng thời.

Không có một giá trị tối ưu áp dụng cho mọi hệ thống. Tăng quá thấp gây ORA-01000; tăng rất cao mà không kiểm soát leak có thể che lỗi quản lý tài nguyên và làm tăng memory footprint.

### 3.2. SESSION_CACHED_CURSORS khác OPEN_CURSORS

Xem:

~~~sql
SHOW PARAMETER session_cached_cursors;
~~~

SESSION_CACHED_CURSORS điều khiển số cursor đã đóng mà session có thể giữ trong session cursor cache để tái sử dụng, giảm parse overhead. Nó không phải giới hạn open cursor và không thay thế OPEN_CURSORS.

Một cursor được cache sau khi close vẫn có thể xuất hiện trong một số view về cursor. Do đó, không chỉ đếm số dòng V$OPEN_CURSOR rồi kết luận đó là số cursor đang mở thật.

### 3.3. Đo số cursor hiện tại theo session

View V$SESSTAT có statistic opened cursors current:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.status,
       st.value AS opened_cursors_current
FROM v$sesstat st
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
JOIN v$session s
  ON s.sid = st.sid
WHERE sn.name = 'opened cursors current'
ORDER BY st.value DESC;
~~~

Đây là chỉ số hữu ích để xác định session nào đang giữ nhiều cursor tại thời điểm quan sát.

Để xem số cursor đã mở tích lũy trong session:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       st.value AS opened_cursors_cumulative
FROM v$sesstat st
JOIN v$statname sn
  ON sn.statistic# = st.statistic#
JOIN v$session s
  ON s.sid = st.sid
WHERE sn.name = 'opened cursors cumulative'
ORDER BY st.value DESC;
~~~

Cumulative tăng theo hoạt động trong vòng đời session; nó không phải số cursor hiện đang mở.

### 3.4. Xem cursor theo session

~~~sql
SELECT sid,
       user_name,
       cursor_type,
       COUNT(*) AS cursor_count
FROM v$open_cursor
GROUP BY sid, user_name, cursor_type
ORDER BY cursor_count DESC;
~~~

Xem SQL cụ thể của một session:

~~~sql
SELECT sid,
       cursor_type,
       sql_id,
       sql_text
FROM v$open_cursor
WHERE sid = :sid
ORDER BY cursor_type, sql_id;
~~~

V$OPEN_CURSOR có thể hiển thị cursor đang mở và một số loại cursor được cache. Đọc CURSOR_TYPE cùng opened cursors current; đừng xem mọi dòng trong view như một resource leak.

### 3.5. Tìm SQL lặp lại trong cursor list

~~~sql
SELECT sid,
       sql_id,
       cursor_type,
       COUNT(*) AS copies
FROM v$open_cursor
WHERE sid = :sid
GROUP BY sid, sql_id, cursor_type
ORDER BY copies DESC;
~~~

Một SQL xuất hiện nhiều lần có thể do child cursor, cursor cache hoặc cách ứng dụng tạo statement. Cần xem SQL_ID, child cursor và session statistics trước khi kết luận.

## 4. Nguyên nhân ORA-01000

Các nguyên nhân phổ biến:

1. Không đóng PreparedStatement hoặc Statement sau khi dùng.
2. Không đóng ResultSet.
3. Tạo statement mới trong vòng lặp thay vì tái sử dụng hợp lý.
4. Mở nhiều REF CURSOR nhưng không đóng result set phía client.
5. PL/SQL mở explicit cursor nhưng exception path không CLOSE.
6. DBMS_SQL cursor không gọi DBMS_SQL.CLOSE_CURSOR.
7. ORM hoặc framework giữ result stream/scrollable result lâu.
8. Connection pool giữ session lâu, làm cursor leak tích lũy qua nhiều request.
9. Ứng dụng có nhiều statement thực sự đồng thời và OPEN_CURSORS quá thấp.
10. Dynamic SQL tạo nhiều cursor không cần thiết hoặc literal SQL làm tăng parse.

### 4.1. JDBC không đóng Statement

Ví dụ không an toàn:

~~~java
for (Order order : orders) {
    PreparedStatement ps = connection.prepareStatement(
        "update orders set status = ? where order_id = ?"
    );

    ps.setString(1, "DONE");
    ps.setLong(2, order.getId());
    ps.executeUpdate();

    // Statement is never closed.
}
~~~

Mỗi vòng lặp tạo statement/cursor mới. Nếu không close, session có thể tích lũy cursor cho đến khi chạm giới hạn.

Cách quản lý đúng:

~~~java
String sql =
    "update orders set status = ? where order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Order order : orders) {
        ps.setString(1, "DONE");
        ps.setLong(2, order.getId());
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

Tùy workload, batch có thể giảm round trips. Nếu cần execute từng statement, vẫn phải đóng statement bằng try-with-resources.

### 4.2. Không đóng ResultSet

ResultSet thường gắn với Statement. Khi dùng xong, đóng cả ResultSet và Statement. Đóng Statement thường đóng ResultSet hiện tại theo JDBC contract, nhưng khai báo cả hai bằng try-with-resources giúp ownership rõ ràng.

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "select order_id, status from orders where status = ?")) {

    ps.setString(1, "OPEN");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process row.
        }
    }
}
~~~

### 4.3. Connection pool làm leak tồn tại lâu hơn

Trong pool, Connection.close() thường trả logical connection về pool thay vì đóng physical Oracle session. Nếu Statement/ResultSet không được đóng, resource có thể vẫn gắn với session được tái sử dụng.

Đóng Connection không phải cách thay thế cho đóng Statement/ResultSet. Đóng từng resource theo đúng ownership trước khi trả connection.

### 4.4. PL/SQL explicit cursor

Ví dụ cần đóng cursor cả success và exception path:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'OPEN';

    l_order_id orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders INTO l_order_id;
        EXIT WHEN c_orders%NOTFOUND;

        -- Process row.
        NULL;
    END LOOP;

    CLOSE c_orders;

EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        RAISE;
END;
/
~~~

PL/SQL cursor FOR loop tự quản lý OPEN/FETCH/CLOSE:

~~~sql
BEGIN
    FOR r IN (
        SELECT order_id
        FROM orders
        WHERE status = 'OPEN'
    ) LOOP
        -- Process row.
        NULL;
    END LOOP;
END;
/
~~~

Cursor FOR loop thường an toàn và ngắn gọn hơn khi không cần kiểm soát vòng đời explicit.

### 4.5. DBMS_SQL và REF CURSOR

Nếu dùng DBMS_SQL, phải đóng cursor number bằng DBMS_SQL.CLOSE_CURSOR trong exception-safe cleanup.

Nếu procedure trả SYS_REFCURSOR, phía JDBC cần đọc và đóng ResultSet/CallableStatement đúng thứ tự. Đóng package call mà vẫn giữ ResultSet mở có thể làm mất khả năng fetch hoặc giữ tài nguyên.

## 5. Xử lý ORA-01000 đúng cách

Thứ tự điều tra:

1. Ghi nhận SID, SERIAL#, username, service, module/action và thời điểm lỗi.
2. Đọc opened cursors current theo session.
3. Xem V$OPEN_CURSOR và CURSOR_TYPE.
4. Xác định SQL/PLSQL call path tạo cursor.
5. Kiểm tra ứng dụng có close ResultSet/Statement không.
6. Kiểm tra REF CURSOR, DBMS_SQL và dynamic SQL.
7. Xem pool/session lifetime và số cursor tăng theo thời gian.
8. Chỉ sau khi loại trừ leak mới đánh giá tăng OPEN_CURSORS.

### 5.1. So sánh cursor current theo thời gian

Chụp opened cursors current theo SID nhiều lần, cùng thời điểm request/load. Nếu một session tăng dần và không giảm sau khi workload hoàn tất, có thể có leak hoặc workload giữ cursor lâu.

Nếu số cursor tăng theo tải rồi giảm khi request kết thúc, đó có thể là concurrency bình thường. Cần so sánh với baseline và OPEN_CURSORS.

### 5.2. Tăng OPEN_CURSORS khi nào?

Có thể tăng OPEN_CURSORS nếu:

- Ứng dụng đóng tài nguyên đúng.
- Workload có nhiều cursor đồng thời hợp lệ.
- Số cursor current đạt gần giới hạn trong peak.
- Memory và session capacity còn đủ.
- Thay đổi được thử nghiệm và theo dõi.

Không tăng tham số để che một leak rõ ràng. Tăng giới hạn có thể chỉ làm lỗi xuất hiện muộn hơn.

## 6. ORA-04030: out of process memory

ORA-04030 báo Oracle process không cấp phát được lượng bộ nhớ riêng cần thiết. Bộ nhớ process thường liên quan PGA (Program Global Area) và các vùng private memory khác của process.

Khác với SGA được chia sẻ giữa các process, PGA là vùng nhớ riêng của server process. Với dedicated server, session workarea/private state thường nằm trong PGA. Với shared server, UGA có thể nằm trong SGA large pool hoặc shared pool tùy cấu hình.

### 6.1. PGA dùng cho việc gì?

PGA có thể chứa:

- Sort workarea.
- Hash join workarea.
- Bitmap merge workarea.
- Session/private SQL state.
- PL/SQL runtime memory.
- Collection, array và package state.
- Cursor private state.
- Một số buffer và memory structure của process.

Một query sort/hash lớn, PL/SQL collection phình to hoặc ứng dụng tải dữ liệu quá lớn vào process có thể làm PGA tăng.

### 6.2. PGA_AGGREGATE_TARGET và PGA_AGGREGATE_LIMIT

Xem cấu hình:

~~~sql
SHOW PARAMETER pga_aggregate_target;
SHOW PARAMETER pga_aggregate_limit;
~~~

- PGA_AGGREGATE_TARGET là mục tiêu quản lý tổng PGA; Oracle dùng nó để điều chỉnh workarea allocation trong các trường hợp phù hợp.
- PGA_AGGREGATE_LIMIT là giới hạn cứng tổng PGA theo cơ chế Oracle; khi vượt, Oracle có thể hủy một số call/session để đưa usage xuống dưới limit và phát sinh lỗi liên quan như ORA-04036.

ORA-04030 là lỗi cấp phát bộ nhớ riêng của process. Nó không đồng nghĩa PGA_AGGREGATE_LIMIT đã bị vượt. Một process có thể không cấp phát được bộ nhớ vì OS/container limit, address space, fragmentation hoặc một allocation lớn dù tổng PGA chưa chạm aggregate limit.

Không xử lý ORA-04030 bằng cách chỉ tăng PGA_AGGREGATE_TARGET. Cần xác định process và allocation cụ thể.

### 6.3. Xem tổng quan PGA

~~~sql
SELECT name,
       value,
       unit
FROM v$pgastat
ORDER BY name;
~~~

Các statistic thường quan tâm:

- aggregate PGA target parameter.
- aggregate PGA auto target.
- total PGA allocated.
- maximum PGA allocated.
- total PGA inuse.
- over allocation count.
- extra bytes read/written.
- global memory bound.

Tên statistic có thể khác theo release; query toàn bộ V$PGASTAT giúp kiểm tra đúng môi trường.

### 6.4. Tìm process có PGA lớn

~~~sql
SELECT p.spid,
       s.sid,
       s.serial#,
       s.username,
       s.program,
       s.module,
       p.pga_used_mem,
       p.pga_alloc_mem,
       p.pga_freeable_mem,
       p.pga_max_mem
FROM v$process p
LEFT JOIN v$session s
  ON s.paddr = p.addr
ORDER BY p.pga_alloc_mem DESC;
~~~

Các cột:

- PGA_USED_MEM: bộ nhớ PGA đang được process sử dụng.
- PGA_ALLOC_MEM: bộ nhớ PGA đã được cấp phát cho process.
- PGA_FREEABLE_MEM: phần có thể được giải phóng theo cơ chế Oracle.
- PGA_MAX_MEM: mức PGA lớn nhất process từng sử dụng.

PGA_ALLOC_MEM và PGA_USED_MEM không giống nhau. Process có thể giữ allocation để tái sử dụng dù phần đang dùng thấp hơn.

### 6.5. Xem PGA theo category

~~~sql
SELECT pid,
       serial#,
       category,
       allocated,
       used,
       max_allocated
FROM v$process_memory
ORDER BY allocated DESC;
~~~

Các category có thể bao gồm SQL, PL/SQL, OLAP, JAVA, Freeable và Other tùy workload/release. Category giúp khoanh vùng loại memory, nhưng không tự xác định câu SQL gây lỗi.

### 6.6. Liên kết process với session và SQL

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.sql_id,
       s.prev_sql_id,
       s.module,
       s.action,
       p.spid,
       p.pga_used_mem,
       p.pga_alloc_mem,
       p.pga_max_mem
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY p.pga_alloc_mem DESC;
~~~

SQL_ID hiện tại có thể không phải SQL gây allocation đỉnh nếu lỗi xảy ra sau một thao tác trước đó hoặc trong PL/SQL. Dùng trace/incident data và lịch sử session để điều tra.

## 7. Nguyên nhân ORA-04030

Các nguyên nhân thường gặp:

### 7.1. Sort hoặc hash join lớn

Query sort nhiều hàng hoặc hash join dữ liệu lớn có thể cần workarea đáng kể. Nếu không đủ memory, Oracle có thể spill ra TEMP; nếu process cần allocation lớn mà không cấp được, có thể gặp lỗi.

Kiểm tra SQL plan, cardinality estimate, workarea, TEMP và dữ liệu đầu vào.

### 7.2. PL/SQL collection lớn

Ví dụ BULK COLLECT toàn bộ bảng vào collection:

~~~sql
SELECT *
BULK COLLECT INTO l_rows
FROM very_large_table;
~~~

Có thể làm process memory tăng mạnh. Dùng BULK COLLECT ... LIMIT để xử lý theo batch:

~~~sql
LOOP
    FETCH c_rows
    BULK COLLECT INTO l_rows
    LIMIT 1000;

    EXIT WHEN l_rows.COUNT = 0;

    -- Process a bounded batch.
END LOOP;
~~~

LIMIT phải được chọn theo kích thước record và memory budget, không chỉ theo số hàng.

### 7.3. Fetch quá nhiều dữ liệu trong ứng dụng

Ứng dụng có thể lấy hàng triệu row vào collection/List/Map trước khi xử lý. Dù dữ liệu nằm ở JVM heap chứ không phải PGA, fetch/concurrency có thể làm tăng số session, cursor và database memory. Cần phân biệt lỗi process memory phía Oracle với OutOfMemoryError phía JVM.

### 7.4. Nhiều session chạy query nặng đồng thời

Một query đơn lẻ có thể chạy tốt, nhưng hàng trăm session cùng sort/hash có thể làm tổng PGA tăng cao. Kiểm tra peak concurrency, Resource Manager, batch overlap và job schedule.

### 7.5. OS hoặc container memory limit

Oracle process cần bộ nhớ thực từ OS. Các giới hạn có thể đến từ:

- RAM/swap.
- Linux ulimit.
- cgroup/container memory limit.
- HugePages/address space configuration.
- Process count và OS resource.
- Memory fragmentation hoặc allocation pattern.

Kiểm tra cùng OS administrator. Không chỉ nhìn free memory tổng thể; cần xem giới hạn process/container và memory pressure theo thời điểm.

### 7.6. PL/SQL package state và session lifetime

Package global variables, large collections và session state có thể giữ memory lâu trong session pooled. Nếu session sống dài, memory có thể tích lũy hoặc không được giải phóng như mong muốn.

Review package state, DBMS_SESSION.RESET_PACKAGE khi phù hợp với lifecycle, và cách pool reset session. Không reset package state tùy tiện nếu ứng dụng dựa vào state đó.

## 8. Workarea và TEMP: phân biệt spill với process memory error

Oracle có thể dùng PGA cho sort/hash workarea. Khi memory không đủ, operation có thể spill ra TEMP.

Xem workarea đang hoạt động:

~~~sql
SELECT sid,
       operation_type,
       operation_id,
       policy,
       estimated_optimal_size,
       estimated_onepass_size,
       last_memory_used,
       last_execution,
       number_passes,
       tempseg_size
FROM v$sql_workarea_active
ORDER BY last_memory_used DESC;
~~~

Tên/cột có thể khác theo release. Xem V$SQL_WORKAREA để phân tích workarea lịch sử và execution mode.

Spill ra TEMP có thể làm query chậm nhưng không nhất thiết là lỗi ORA-04030. Ngược lại, tăng PGA có thể giảm spill nhưng tăng tổng memory pressure. Cần cân bằng theo workload và capacity.

### 8.1. Tối ưu query trước khi tăng memory

- Kiểm tra cardinality và execution plan.
- Giảm số hàng trước sort/join nếu logic cho phép.
- Tạo index phù hợp với predicate/join/order by sau khi đo.
- Tránh SELECT * khi không cần.
- Kiểm tra stale statistics.
- Tránh Cartesian join hoặc join condition sai.
- Chia batch khi xử lý dữ liệu lớn.
- Giới hạn concurrency của batch/report.

Không thêm index hoặc hint chỉ dựa trên ORA-04030; phải xem plan và workload.

## 9. ORA-04031: unable to allocate bytes of shared memory

ORA-04031 xảy ra khi Oracle không thể cấp phát một vùng nhớ trong SGA pool theo yêu cầu. Thông báo thường ghi số byte cần cấp và tên pool/heap/subheap liên quan.

Các vùng có thể gặp:

- Shared pool.
- Large pool.
- Java pool.
- Streams pool.
- Một số SGA memory area khác tùy release/configuration.

ORA-04031 không tự động có nghĩa toàn bộ SGA hết RAM. Có thể SGA còn free memory tổng thể nhưng pool/heap không có chunk phù hợp hoặc có fragmentation/pressure.

### 9.1. Shared pool dùng cho gì?

Shared pool chứa nhiều cấu trúc được chia sẻ, bao gồm:

- Library cache: parsed SQL, PL/SQL code và related metadata.
- Data dictionary cache/row cache.
- Shared SQL areas.
- Control structures và memory allocations khác.

Hard parse nhiều, SQL text biến thiên, child cursor tăng, invalidation hoặc shared pool pressure có thể làm shared pool sử dụng nhiều memory.

### 9.2. Large pool dùng cho gì?

Large pool là vùng SGA riêng cho một số allocation lớn, tránh cạnh tranh với shared pool trong các workload phù hợp, ví dụ:

- Shared server UGA.
- Parallel execution message buffers.
- Một số RMAN I/O buffers.
- Một số thao tác backup/restore hoặc execution theo cấu hình.

Nếu ORA-04031 ghi pool là large pool, điều tra shared server, parallel execution, RMAN và cấu hình large pool; không mặc định tăng shared pool.

### 9.3. Xem SGA memory theo pool

~~~sql
SELECT pool,
       name,
       bytes
FROM v$sgastat
ORDER BY pool, bytes DESC;
~~~

Tổng hợp:

~~~sql
SELECT pool,
       SUM(bytes) AS bytes
FROM v$sgastat
GROUP BY pool
ORDER BY bytes DESC;
~~~

V$SGASTAT cho biết allocation theo pool/name. Một snapshot không chứng minh fragmentation; lấy nhiều snapshot trong lúc workload và đối chiếu alert/trace.

### 9.4. Xem shared pool reserved

~~~sql
SELECT free_space,
       avg_free_size,
       used_space,
       avg_used_size,
       requests,
       request_misses,
       last_miss_size,
       max_miss_size
FROM v$shared_pool_reserved;
~~~

Các chỉ số request misses và last miss size có thể giúp đánh giá allocation lớn trong reserved pool. Ý nghĩa và cột có thể khác theo release.

Không tăng SHARED_POOL_RESERVED_SIZE chỉ vì thấy request_misses khác 0; phải đọc cùng workload, reserved list và error trace.

### 9.5. Xem library cache

~~~sql
SELECT namespace,
       gets,
       gethits,
       pins,
       pinhits,
       reloads,
       invalidations
FROM v$librarycache
ORDER BY namespace;
~~~

Reloads/invalidations tăng có thể là dấu hiệu library cache churn hoặc object invalidation. Cần so sánh delta theo thời gian và workload, không đánh giá chỉ bằng một con số tích lũy.

### 9.6. Kiểm tra SQL parse và child cursor

~~~sql
SELECT sql_id,
       version_count,
       parse_calls,
       executions,
       loads,
       invalidations,
       sql_text
FROM v$sqlarea
ORDER BY version_count DESC
FETCH FIRST 30 ROWS ONLY;
~~~

SQL tạo literal khác nhau có thể làm tăng số parent/child cursor. Dùng bind variables khi phù hợp và kiểm tra child cursor reason:

~~~sql
SELECT sql_id,
       child_number,
       unbound_cursor,
       optimizer_mismatch,
       bind_mismatch,
       language_mismatch,
       auth_check_mismatch
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
~~~

V$SQL_SHARED_CURSOR có nhiều cột reason tùy release. Chọn cột phù hợp phiên bản hoặc xem toàn bộ row. Không kết luận bind mismatch là nguyên nhân duy nhất của ORA-04031.

## 10. Nguyên nhân ORA-04031

### 10.1. Shared pool pressure

- Shared pool quá nhỏ so với workload.
- Hard parse nhiều.
- Literal SQL tạo nhiều cursor.
- Nhiều child cursor cho cùng SQL_ID.
- PL/SQL/package load và invalidation thường xuyên.
- Dictionary cache pressure.
- Allocation lớn hoặc phân mảnh.
- Shared pool bị ảnh hưởng bởi workload không ổn định.

### 10.2. Large pool pressure

- Parallel query quá nhiều hoặc DOP cao.
- Shared server session tăng.
- RMAN channels/buffers nhiều.
- Workload dùng large pool tăng đột biến.
- Large pool cấu hình chưa đủ trong trường hợp manual sizing.

### 10.3. Fragmentation

Tổng free bytes có thể lớn nhưng không có chunk liên tục đủ lớn cho request. Shared pool dùng các heap/subheap và allocation lifecycle phức tạp; fragmentation là một khả năng, nhưng cần evidence từ trace và pool statistics.

Không kết luận fragmentation chỉ vì V$SGASTAT có nhiều dòng free memory.

### 10.4. SQL churn và hard parse

Ứng dụng tạo SQL khác nhau theo literal:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 1001;

SELECT *
FROM orders
WHERE customer_id = 1002;
~~~

Dùng bind variable khi phù hợp:

~~~sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
~~~

Bind giúp tái sử dụng SQL cursor trong nhiều trường hợp và giảm parse overhead. Tuy nhiên, bind peeking/adaptive cursor sharing và data skew có thể tạo child cursor khác nhau; bind không phải giải pháp tuyệt đối cho mọi plan issue.

### 10.5. Cursor leak có liên quan nhưng không đồng nhất

Một open cursor giữ private state ở session/process và liên quan tới shared SQL area. Nhưng ORA-04031 là lỗi allocation SGA pool; ORA-01000 là vượt open cursor limit của session.

Nếu thấy cả hai, điều tra cursor lifecycle, shared pool pressure và PGA/session memory riêng. Không chỉ tăng cả OPEN_CURSORS và SHARED_POOL_SIZE cùng lúc.

## 11. Phân biệt SGA, PGA, UGA và cursor memory

| Vùng | Chia sẻ? | Dùng cho | Lỗi liên quan |
|---|---|---|---|
| SGA | Chia sẻ trong instance | Buffer cache, shared pool, large pool, redo buffer và cấu trúc instance | ORA-04031 |
| PGA | Riêng process | Workarea, private state, sort/hash, PL/SQL memory | ORA-04030 |
| UGA | Session state | Session memory, package state, cursor state | Vị trí phụ thuộc server mode |
| Session cursor state | Theo session | Open cursor handles và execution state | ORA-01000 |

Trong dedicated server, UGA thường nằm trong PGA của server process. Trong shared server, UGA có thể nằm trong SGA, thường dùng large pool nếu được cấu hình phù hợp.

Một cursor có thể dùng shared SQL area trong SGA và private/session state trong PGA/UGA. Do đó cursor workload có thể tạo áp lực nhiều vùng nhớ, nhưng mỗi ORA error chỉ ra một failure mode cụ thể.

## 12. Kết nối ORA-01000 với JDBC, Spring và ORM

Ứng dụng Java thường dùng connection pool. Một physical Oracle session có thể được tái sử dụng cho nhiều request; cursor leak trong một request có thể tích lũy qua nhiều lần mượn connection nếu statement/result set không được đóng.

### 12.1. Try-with-resources

~~~java
String sql =
    "select order_id, status from orders where customer_id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("status");
            // Process row.
        }
    }
}
~~~

Trong Spring transaction-managed code, không tự đóng connection do transaction manager sở hữu ngoài contract; dùng JdbcTemplate hoặc để framework quản lý connection. Nhưng Statement và ResultSet do code tạo vẫn phải được giải phóng.

### 12.2. Spring JdbcTemplate

JdbcTemplate tự quản lý Statement và ResultSet trong callback:

~~~java
List<OrderRow> rows = jdbcTemplate.query(
    "select order_id, status from orders where customer_id = ?",
    (rs, rowNum) -> new OrderRow(
        rs.getLong("order_id"),
        rs.getString("status")
    ),
    customerId
);
~~~

Không trả ResultSet/stream JDBC ra ngoài callback nếu resource đã được JdbcTemplate đóng. Nếu cần streaming large result, dùng API streaming có callback/lifecycle rõ ràng và đóng stream trước khi connection trả pool.

### 12.3. JPA Stream/Scrollable Results

JPA Stream hoặc Hibernate scrollable result có thể giữ JDBC cursor và connection mở trong lúc caller tiêu thụ dữ liệu. Dùng try-with-resources:

~~~java
try (Stream<OrderEntity> stream = repository.streamByStatus("OPEN")) {
    stream.forEach(this::process);
}
~~~

Phương thức repository cần transaction phù hợp và provider-specific behavior cần được kiểm tra. Không chuyển stream ra khỏi transaction rồi tiêu thụ sau khi transaction đóng.

### 12.4. Statement cache không thay close

Oracle JDBC implicit statement cache có thể giữ statement đã đóng để tái sử dụng. Đóng statement vẫn cần thiết; driver/pool có thể đưa nó vào cache thay vì hủy physical cursor ngay lập tức.

Phân biệt cursor cache có chủ đích với leak. Xem cursor type và session statistics trước khi tắt statement cache hoặc thay đổi cấu hình pool.

## 13. Xử lý ORA-04030 theo runbook

### Bước 1 — Thu thập process/session

Ghi:

- Instance và host.
- SID/SERIAL#.
- Username, service, module/action.
- SPID/process ID.
- SQL_ID/PREV_SQL_ID.
- PGA_USED_MEM, PGA_ALLOC_MEM, PGA_MAX_MEM.
- Thời điểm và workload đang chạy.

### Bước 2 — Xem process memory category

Query V$PROCESS_MEMORY và V$PGASTAT. Xác định category tăng mạnh và tổng PGA trend.

### Bước 3 — Xem execution plan/workarea

Kiểm tra SQL đang chạy, V$SQL_WORKAREA_ACTIVE, TEMP usage, row count và execution plan.

### Bước 4 — Kiểm tra PL/SQL và application

Tìm BULK COLLECT không LIMIT, collection tăng không giới hạn, package state, Java stored procedure, fetch quá lớn và concurrency.

### Bước 5 — Kiểm tra OS

Thu thập process RSS/virtual memory, ulimit, cgroup/container memory, swap, kernel logs và memory pressure tại đúng thời điểm. Phối hợp OS team.

### Bước 6 — Khôi phục và giảm tải

Tùy nguyên nhân:

- Giảm concurrency của batch/query.
- Chia batch bằng LIMIT.
- Giảm data volume trung gian.
- Tối ưu join/sort.
- Điều chỉnh workarea/PGA theo capacity.
- Sửa memory leak trong code.
- Khôi phục OS/container memory headroom.
- Đặt Resource Manager limits phù hợp nếu cần.

Không kill process chỉ vì PGA cao nếu chưa đánh giá transaction và business impact. Nếu process bị hủy, transaction có thể rollback và ứng dụng cần xử lý retry.

## 14. Xử lý ORA-04031 theo runbook

### Bước 1 — Đọc toàn bộ error message và trace

Ghi số byte yêu cầu, pool/heap/subheap, process/session, SQL_ID và incident trace. Tên pool trong error stack là manh mối quan trọng.

### Bước 2 — Xác định pool

- Shared pool: library cache, dictionary cache, SQL/PLSQL allocation.
- Large pool: shared server, parallel execution, RMAN buffers.
- Java pool/Streams pool: workload tương ứng.
- Pool khác: kiểm tra theo release và trace.

### Bước 3 — Lấy SGA snapshot

Query V$SGASTAT, V$SHARED_POOL_RESERVED và các view liên quan. Lấy nhiều snapshot trong workload, so sánh delta và free chunks.

### Bước 4 — Kiểm tra SQL/library cache

Xem hard parse, version_count, child cursor, invalidation, literal SQL, bind mismatch và object churn. Xác định thay đổi gần đây như deploy, stats gathering, DDL hoặc batch spike.

### Bước 5 — Kiểm tra SGA configuration

~~~sql
SHOW PARAMETER sga_target;
SHOW PARAMETER sga_max_size;
SHOW PARAMETER shared_pool_size;
SHOW PARAMETER large_pool_size;
SHOW PARAMETER memory_target;
~~~

Nếu dùng ASMM/AMM, Oracle quản lý dynamic component sizing theo cơ chế tương ứng. Manual sizing và minimum component size có thể ảnh hưởng kết quả. Không chỉnh một tham số mà không xem toàn bộ memory management mode.

### Bước 6 — Khôi phục

- Giảm hard parse và SQL churn.
- Giảm concurrency hoặc DOP nếu large pool pressure.
- Điều chỉnh shared/large pool theo workload và SGA capacity.
- Kiểm tra invalidation/deployment churn.
- Xem xét patch/known bug khi trace chỉ ra allocation failure có pattern cụ thể.
- Restart chỉ khi có kế hoạch và evidence cho thấy cần thiết.

Không dùng ALTER SYSTEM FLUSH SHARED_POOL như phản xạ. Flush có thể làm mất cached SQL/PLSQL, gây hard parse storm và làm tình hình tệ hơn.

## 15. Điều chỉnh memory có căn cứ

### 15.1. Không tăng tham số mù quáng

| Tham số | Tác động | Cần kiểm tra trước |
|---|---|---|
| OPEN_CURSORS | Tăng số cursor/session được phép mở | Leak, current cursor peak, PGA/session count |
| SESSION_CACHED_CURSORS | Tăng cursor cache per session | Parse workload, session count, memory |
| PGA_AGGREGATE_TARGET | Mục tiêu tổng PGA/workarea | Total PGA, concurrency, TEMP spill, OS RAM |
| PGA_AGGREGATE_LIMIT | Hard limit tổng PGA theo cơ chế Oracle | Workload peak và khả năng chịu memory |
| SGA_TARGET | Mục tiêu SGA tự động quản lý component | SGA_MAX_SIZE, host memory, component sizing |
| SHARED_POOL_SIZE | Kích thước/minimum shared pool tùy mode | Parse, library cache, SGA mode |
| LARGE_POOL_SIZE | Kích thước/minimum large pool tùy mode | PX, shared server, RMAN demand |

### 15.2. SGA/PGA và OS headroom

SGA và PGA cùng cạnh tranh RAM vật lý của host. Khi tăng SGA, có thể giảm headroom cho PGA và OS. Khi tăng PGA limit, concurrent process có thể dùng nhiều memory hơn.

Capacity planning phải tính:

- SGA.
- PGA aggregate peak.
- OS/kernel memory.
- Agent/monitoring process.
- Filesystem cache và workload khác.
- Container/cgroup limits.
- RAC node failure/degraded mode nếu có.

### 15.3. RAC và nhiều instance

V$ views thường phản ánh instance hiện tại. Trong RAC, dùng GV$ để tổng hợp nhiều instance và giữ INST_ID:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       sql_id,
       status
FROM gv$session
WHERE type = 'USER'
ORDER BY inst_id, sid;
~~~

OPEN_CURSORS là tham số instance/session áp dụng theo cấu hình; điều tra session lỗi trên đúng instance. PGA và SGA pressure cũng phải phân tích theo từng node.

## 16. Monitoring và cảnh báo sớm

Thiết lập baseline cho:

- Open cursors current theo session.
- Tỷ lệ session gần OPEN_CURSORS.
- PGA allocated/used/max theo process.
- Total PGA allocated và over allocation.
- SGA pool usage và free memory.
- Shared pool reserved request misses.
- Library cache reloads/invalidations.
- SQL version_count và hard parse.
- TEMP usage và active workarea.
- Connection pool active/idle/wait.
- Batch concurrency và execution duration.

### 16.1. Ngưỡng cảnh báo

Không dùng một ngưỡng chung cho mọi database. Có thể cảnh báo theo tỷ lệ:

- Session open cursors đạt tỷ lệ cao so với OPEN_CURSORS.
- Process PGA tăng nhanh hoặc vượt baseline.
- PGA aggregate tiến gần limit.
- Shared/large pool allocation miss tăng.
- Connection pool wait và active connection tăng đồng thời.

Dùng rolling window, delta và alert duration để tránh false positive. Cảnh báo cần chỉ ra SID/INST_ID/module/action và runbook tương ứng.

### 16.2. AWR/ASH và diagnostic licensing

AWR/ASH có thể hữu ích để xem lịch sử workload, SQL, wait và memory behavior, nhưng việc sử dụng các tính năng Diagnostic/Tuning Pack có yêu cầu licensing theo Oracle contract. Kiểm tra entitlement trước khi dùng. Có thể dùng dynamic performance views và trace hiện tại theo quyền sẵn có.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| ORA-01000 là shared pool hết | Đây là giới hạn open cursor theo session |
| V$OPEN_CURSOR đếm chính xác mọi cursor đang mở | Có thể bao gồm cursor cached; đọc CURSOR_TYPE và session statistic |
| SESSION_CACHED_CURSORS tăng OPEN_CURSORS | Hai tham số có mục đích khác nhau |
| Đóng Connection trong pool là đủ | Statement/ResultSet vẫn cần đóng đúng lifecycle |
| Tăng OPEN_CURSORS luôn sửa được lỗi | Có thể chỉ che cursor leak |
| ORA-04030 đồng nghĩa PGA_AGGREGATE_LIMIT bị vượt | Lỗi process allocation có thể do nhiều nguyên nhân |
| Tăng PGA_AGGREGATE_TARGET luôn sửa ORA-04030 | Cần xem process, OS và workload |
| ORA-04031 nghĩa toàn bộ RAM host hết | Lỗi cấp phát SGA pool; có thể do pool/heap/fragmentation |
| Shared pool và large pool là một | Hai pool có mục đích và workload khác nhau |
| Flush shared pool là cách chữa fragmentation | Có thể gây hard parse storm |
| Mọi cursor leak đều gây ORA-04031 | ORA-01000, PGA và SGA là các failure mode khác nhau |
| TEMP spill là ORA-04030 | Spill có thể chỉ làm query chậm; phải đọc error thực tế |
| Tăng memory không cần kiểm tra OS | SGA/PGA vẫn bị giới hạn bởi host/container |
| Restart database là cách xử lý đầu tiên | Restart có thể che triệu chứng và gây downtime; cần RCA |

## 18. Bài thực hành

Thực hiện trên database lab, không cố tình gây cạn tài nguyên production.

### Bài 1 — Quan sát OPEN_CURSORS

Xem OPEN_CURSORS, SESSION_CACHED_CURSORS và opened cursors current của session. Chạy một số query/statement rồi quan sát giá trị thay đổi.

### Bài 2 — Cursor lifecycle trong JDBC

Viết chương trình tạo PreparedStatement trong vòng lặp. So sánh khi không close và khi dùng try-with-resources. Dùng session statistics để quan sát.

### Bài 3 — Statement cache

Bật statement caching theo Oracle JDBC/pool configuration trong lab. Xác nhận statement vẫn được close ở API level và phân biệt cached cursor với leak.

### Bài 4 — PL/SQL cursor

Viết explicit cursor có exception path, kiểm tra %ISOPEN và CLOSE. So sánh với cursor FOR loop.

### Bài 5 — REF CURSOR

Trả SYS_REFCURSOR từ procedure, fetch qua JDBC ResultSet và đóng result set/call statement. Quan sát open cursor count.

### Bài 6 — PGA baseline

Chụp V$PGASTAT và V$PROCESS trước/sau một query sort/hash trong lab. Ghi process PGA và execution plan.

### Bài 7 — BULK COLLECT

Thử BULK COLLECT không giới hạn trên dữ liệu nhỏ, sau đó dùng LIMIT. So sánh memory và thời gian; không cố làm host hết RAM.

### Bài 8 — Workarea và TEMP

Chạy sort/hash query trên dữ liệu test, quan sát V$SQL_WORKAREA_ACTIVE và TEMP usage. Phân biệt one-pass/multipass với process memory error.

### Bài 9 — Shared pool observation

Theo dõi V$SGASTAT, V$SHARED_POOL_RESERVED và V$LIBRARYCACHE trong workload parse-heavy có kiểm soát. Không flush shared pool để tạo test.

### Bài 10 — Bind variables

So sánh SQL literal khác nhau với bind variable trong lab. Quan sát parse_calls, version_count và child cursor.

### Bài 11 — Connection pool

Tạo load test có giới hạn, theo dõi pool active/idle/wait và opened cursors current theo session. Xác nhận mọi resource được đóng sau request.

### Bài 12 — Runbook simulation

Dùng trace/test harness hoặc snapshot dữ liệu đã thu thập để mô phỏng phân loại ORA-01000, ORA-04030 và ORA-04031. Viết nguyên nhân, evidence, hành động và postcheck.

## 19. Checklist xử lý sự cố

### ORA-01000

- [ ] Ghi SID/SERIAL#, INST_ID, service, module/action.
- [ ] Kiểm tra OPEN_CURSORS.
- [ ] Đọc opened cursors current và cumulative.
- [ ] Xem V$OPEN_CURSOR cùng CURSOR_TYPE.
- [ ] Kiểm tra JDBC Statement/PreparedStatement/ResultSet.
- [ ] Kiểm tra PL/SQL explicit cursor, REF CURSOR và DBMS_SQL.
- [ ] Kiểm tra pool/session lifetime.
- [ ] Phân biệt cursor cache với leak.
- [ ] Chỉ tăng OPEN_CURSORS sau khi chứng minh workload hợp lệ và memory đủ.

### ORA-04030

- [ ] Lưu error stack/trace và process ID.
- [ ] Liên kết SPID với SID/SERIAL#/SQL_ID.
- [ ] Kiểm tra PGA_USED/ALLOC/MAX.
- [ ] Kiểm tra V$PROCESS_MEMORY category.
- [ ] Kiểm tra V$PGASTAT và PGA limits.
- [ ] Kiểm tra workarea, TEMP và execution plan.
- [ ] Kiểm tra PL/SQL collections/BULK COLLECT/package state.
- [ ] Kiểm tra concurrency và Resource Manager.
- [ ] Kiểm tra OS/cgroup/ulimit/RAM/swap.
- [ ] Xác định remediation trước khi tăng memory hoặc kill process.

### ORA-04031

- [ ] Lưu đầy đủ pool/heap/bytes trong error.
- [ ] Xác định instance và session/process liên quan.
- [ ] Kiểm tra V$SGASTAT theo pool.
- [ ] Kiểm tra V$SHARED_POOL_RESERVED.
- [ ] Kiểm tra V$LIBRARYCACHE reload/invalidation.
- [ ] Kiểm tra SQL parse, version_count và child cursor.
- [ ] Kiểm tra large pool consumers như PX/RMAN/shared server.
- [ ] Kiểm tra SGA_TARGET, SGA_MAX_SIZE và memory mode.
- [ ] Lấy snapshot theo thời gian, không chỉ một điểm.
- [ ] Tránh flush shared pool hoặc restart khi chưa có RCA.

## 20. Ghi nhớ cốt lõi

- ORA-01000 là giới hạn open cursor theo session; kiểm tra OPEN_CURSORS và opened cursors current.
- ORA-04030 là process không cấp phát được private memory, thường liên quan PGA và OS allocation.
- ORA-04031 là không cấp phát được vùng nhớ trong một SGA pool; đọc pool/heap cụ thể trong error stack.
- Shared SQL cursor nằm trong library cache/SGA, còn session cursor state và private memory có phần riêng; một workload có thể tác động nhiều vùng.
- OPEN_CURSORS khác SESSION_CACHED_CURSORS; cursor cache không phải cursor leak.
- V$OPEN_CURSOR có thể hiển thị cả cursor cached; đối chiếu CURSOR_TYPE và V$SESSTAT.
- JDBC phải đóng ResultSet, Statement và PreparedStatement; connection pool không làm biến mất trách nhiệm cleanup.
- PL/SQL explicit cursor, REF CURSOR và DBMS_SQL cần được đóng trên cả success và exception path.
- Tăng OPEN_CURSORS chỉ khi workload cần nhiều cursor đồng thời hợp lệ và đã loại trừ leak.
- PGA_AGGREGATE_TARGET là target quản lý PGA; PGA_AGGREGATE_LIMIT là giới hạn aggregate theo cơ chế Oracle; ORA-04030 không đồng nghĩa đã vượt limit.
- BULK COLLECT không giới hạn, collection lớn, sort/hash và concurrency có thể làm process PGA tăng.
- TEMP spill có thể làm query chậm nhưng không tự đồng nghĩa ORA-04030.
- Large pool phục vụ một số workload như shared server, parallel execution và RMAN; không nhầm với shared pool.
- ORA-04031 có thể do pool pressure, fragmentation, hard parse, child cursor hoặc allocation pattern; không kết luận chỉ từ tổng free memory.
- Bind variables thường giảm SQL text churn và parse overhead nhưng cần đánh giá child cursor/plan behavior.
- Không flush shared pool như cách chữa mặc định vì có thể tạo hard parse storm.
- SGA và PGA cùng tiêu thụ RAM host; mọi thay đổi memory phải tính OS/container headroom.
- Trong RAC, dùng GV$ và INST_ID để xác định đúng instance.
- AWR/ASH và Diagnostic/Tuning Pack cần kiểm tra licensing trước khi sử dụng.
- Khắc phục gốc bằng resource lifecycle, SQL/workload tuning, capacity và monitoring; tăng tham số chỉ là một phần của remediation.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Error Messages](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/) — ORA-01000, ORA-04030, ORA-04031 and related diagnostics.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$SESSTAT, V$STATNAME, V$OPEN_CURSOR, V$PROCESS, V$PROCESS_MEMORY, V$PGASTAT, V$SGASTAT, V$SHARED_POOL_RESERVED and V$LIBRARYCACHE.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Cursor management, PGA/workarea, SGA and shared pool tuning.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/) — Memory architecture, initialization parameters and instance management.
- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/) — Explicit cursors, cursor FOR loops, REF CURSOR and DBMS_SQL.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — JDBC statement, result set and statement caching behavior.
- [Oracle Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/) — Diagnostic and Tuning Pack feature licensing.

View columns, memory management behavior and available parameters vary by Oracle release and deployment mode. Capture the complete error stack and trace, verify the exact database version/RU and use a representative non-production workload before changing cursor limits, PGA/SGA sizing or pool configuration.

