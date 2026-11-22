# Native compilation, tối ưu PL/SQL và đo trước khi thay đổi

Tối ưu PL/SQL hiệu quả bắt đầu bằng việc đo. Một procedure chạy chậm có thể mất thời gian trong vòng lặp PL/SQL, trong câu SQL bên trong procedure, khi chờ I/O, khi tranh chấp khóa, hoặc khi trao đổi dữ liệu giữa PL/SQL engine và SQL engine. Native compilation chỉ tác động tới phần thực thi PL/SQL; nó không tự làm câu SQL bên trong nhanh hơn và cũng không loại bỏ thời gian chờ database.

Vì vậy, quy trình đúng là:

1. Đo thời gian và tài nguyên của workload hiện tại.
2. Xác định phần chậm nằm ở PL/SQL hay SQL/database wait.
3. Chọn kỹ thuật phù hợp với bottleneck đã đo.
4. Thay đổi một yếu tố trong mỗi lần thử.
5. Đo lại trên dữ liệu và tải tương đương.
6. Chỉ triển khai khi kết quả đúng, ổn định và có lợi ích thực tế.

Bài học giải thích native compilation, các tham số compiler, profiling, SQL tracing, bulk processing, giảm context switch và cách tổ chức một thí nghiệm hiệu năng có thể lặp lại. Các ví dụ dùng cú pháp Oracle Database 19c làm mốc tham chiếu; quyền thực thi và một số chi tiết công cụ có thể khác theo phiên bản và cấu hình.

## 1. Trước tiên: PL/SQL chậm ở đâu?

PL/SQL là ngôn ngữ thủ tục chạy trong Oracle Database. Một chương trình PL/SQL thường phối hợp hai engine:

- PL/SQL engine xử lý biến, điều kiện, vòng lặp, gọi procedure/function và logic.
- SQL engine phân tích, tối ưu và thực thi SELECT, INSERT, UPDATE, DELETE, MERGE.

Ví dụ:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = rec.salary * 1.05
        WHERE employee_id = rec.employee_id;
    END LOOP;
END;
/
~~~

Thời gian của block có thể gồm:

1. Thực thi câu SELECT lấy dữ liệu.
2. Chuyển từng hàng từ SQL engine sang PL/SQL engine.
3. Chạy logic PL/SQL trong mỗi vòng lặp.
4. Gọi SQL engine cho từng câu UPDATE.
5. Đọc/ghi block, undo/redo và chờ khóa hoặc I/O.

Nếu phần lớn thời gian nằm ở UPDATE hoặc chờ I/O, native compilation không giải quyết nguyên nhân. Nếu phần lớn thời gian nằm trong tính toán PL/SQL thuần CPU, native compilation hoặc tối ưu thuật toán có thể hữu ích.

### 1.1 Ba nhóm bottleneck

| Nhóm | Dấu hiệu | Hướng điều tra |
|---|---|---|
| PL/SQL CPU | Vòng lặp, xử lý chuỗi/số, thuật toán tiêu tốn CPU | DBMS_HPROF, DBMS_PROFILER, tối ưu thuật toán, native compilation |
| SQL execution | SQL có nhiều logical reads, physical reads, join/sort lớn | Actual execution plan, SQL trace, DBMS_XPLAN, thống kê |
| Wait/concurrency | Chờ I/O, lock, latch, network hoặc tài nguyên khác | Session wait, SQL trace, ASH/AWR nếu được cấp phép, kiểm tra concurrency |

Một procedure có thể đồng thời gặp nhiều loại bottleneck. Hãy đo phần đóng góp của từng phần trước khi chọn giải pháp.

### 1.2 Thời gian tổng không đủ để tìm nguyên nhân

Nếu một procedure mất 20 giây, con số đó chưa nói được:

- PL/SQL dùng 18 giây CPU hay chỉ 0,2 giây?
- SQL chiếm 15 giây do full scan hay do chờ lock?
- Procedure gọi một function 100.000 lần?
- Một câu SQL duy nhất chiếm gần hết thời gian?
- Thời gian tăng do parse nhiều lần hay do thực thi?

Cần kết hợp phép đo end-to-end với profiler và thống kê SQL.

## 2. Quy trình đo trước khi tối ưu

Một phép đo có giá trị phải có baseline rõ ràng và có thể lặp lại.

### 2.1 Xác định workload

Ghi lại:

- Procedure/package và đường gọi thực tế.
- Input đại diện: số hàng, kích thước collection, độ dài chuỗi, loại nghiệp vụ.
- Số lần thực thi.
- Tần suất chạy và mức đồng thời.
- Trạng thái dữ liệu và thống kê.
- Kết quả đầu ra cần giữ nguyên.
- Ranh giới transaction và cách commit.

Đừng chỉ benchmark một input rất nhỏ nếu production thường xử lý hàng trăm nghìn hàng. Cũng đừng chỉ dùng input cực đại nếu phần lớn workload nằm ở kích thước nhỏ.

### 2.2 Đo baseline nhiều lần

Chạy nhiều lần với điều kiện tương đương:

- Thực hiện một lượt warm-up nếu có ảnh hưởng của cache hoặc load object.
- Chạy đủ số lần để nhận diện biến động.
- Ghi median và phân vị cao như p95 nếu workload có nhiều lần chạy.
- Giữ cùng kiểu bind, dữ liệu, session settings và concurrency.
- Tách thời gian setup/test data khỏi vùng đang đo.
- Không thay đổi nhiều tham số giữa hai lần thử.

Không kết luận từ một lần chạy nhanh hơn vài mili giây. Chênh lệch có thể do cache, background activity hoặc tải hệ thống.

### 2.3 Chọn metric

Ít nhất nên ghi:

| Metric | Câu hỏi trả lời |
|---|---|
| Elapsed time | Caller phải chờ bao lâu? |
| CPU time | Database tiêu tốn bao nhiêu CPU? |
| Logical reads/buffer gets | Cần truy cập bao nhiêu block trong buffer cache? |
| Physical reads | Có bao nhiêu lần đọc từ storage? |
| Rows processed | Workload thực tế xử lý bao nhiêu hàng? |
| Executions | Câu SQL/procedure được gọi bao nhiêu lần? |
| Parse calls | Có đang parse lặp lại không? |
| Wait events | Thời gian bị chờ ở đâu? |
| Memory/collection size | Có nguy cơ tăng bộ nhớ khi bulk không? |

Elapsed time là trải nghiệm caller. CPU time và wait time giúp giải thích vì sao elapsed time thay đổi.

### 2.4 Giữ kết quả nghiệp vụ tương đương

Sau tối ưu, cần xác nhận:

- Số hàng đầu vào/đầu ra giống nhau.
- Giá trị số, quy tắc làm tròn và thứ tự xử lý đúng.
- Exception và mã lỗi vẫn theo hợp đồng.
- Transaction/commit/rollback không đổi ngoài ý muốn.
- Side effect như audit hoặc message không bị mất hoặc lặp.

Một phiên bản nhanh hơn nhưng bỏ sót một số hàng hoặc thay đổi hành vi exception không phải là tối ưu hợp lệ.

## 3. Đo thời gian đơn giản trong PL/SQL

### 3.1 Dùng SYSTIMESTAMP

SYSTIMESTAMP trả về TIMESTAMP WITH TIME ZONE. Có thể lấy thời điểm đầu/cuối và trừ để nhận INTERVAL:

~~~sql
DECLARE
    l_start   TIMESTAMP WITH TIME ZONE;
    l_finish  TIMESTAMP WITH TIME ZONE;
    l_elapsed INTERVAL DAY TO SECOND;
BEGIN
    l_start := SYSTIMESTAMP;

    -- Đặt workload cần đo tại đây.
    order_api.recalculate_order(p_order_id => 1001);

    l_finish := SYSTIMESTAMP;
    l_elapsed := l_finish - l_start;

    DBMS_OUTPUT.PUT_LINE(
        'Elapsed: ' || TO_CHAR(l_elapsed)
    );
END;
/
~~~

Đây là phép đo thời gian thực từ góc nhìn session, không phải phép đo CPU riêng. Nó bao gồm thời gian chờ SQL, I/O, lock và các hoạt động khác trong vùng đo.

### 3.2 Dùng DBMS_UTILITY.GET_TIME

DBMS_UTILITY.GET_TIME trả về số centisecond từ một mốc nội bộ:

~~~sql
DECLARE
    l_start_cs PLS_INTEGER;
    l_end_cs   PLS_INTEGER;
BEGIN
    l_start_cs := DBMS_UTILITY.GET_TIME;

    order_api.recalculate_order(p_order_id => 1001);

    l_end_cs := DBMS_UTILITY.GET_TIME;

    DBMS_OUTPUT.PUT_LINE(
        'Elapsed seconds: ' ||
        (l_end_cs - l_start_cs) / 100
    );
END;
/
~~~

GET_TIME hữu ích cho phép đo đơn giản trong PL/SQL. Độ phân giải centisecond không phù hợp để so sánh các đoạn rất ngắn; cần chạy nhiều lần hoặc đo một batch đủ dài.

### 3.3 Không đo bằng DBMS_OUTPUT trong vòng lặp

DBMS_OUTPUT và các thao tác ghi log có thể làm thay đổi thời gian thực thi. Không in từng hàng trong vùng benchmark nếu production không làm như vậy.

Thay vì:

~~~sql
FOR i IN 1 .. 100000 LOOP
    DBMS_OUTPUT.PUT_LINE(i);
    l_total := l_total + i;
END LOOP;
~~~

hạn chế output:

~~~sql
FOR i IN 1 .. 100000 LOOP
    l_total := l_total + i;
END LOOP;

DBMS_OUTPUT.PUT_LINE('Total=' || l_total);
~~~

Đo đúng workload mà ứng dụng thật sự thực hiện.

## 4. PL/SQL Profiler: đo từng subprogram và dòng lệnh

Profiler giúp tìm đoạn code đang tiêu tốn thời gian thay vì đoán theo độ dài source.

### 4.1 DBMS_PROFILER

DBMS_PROFILER thu thập thông tin theo đơn vị PL/SQL và dòng source. Nó hữu ích khi cần biết:

- Procedure/function nào tốn thời gian.
- Dòng lệnh nào được thực thi nhiều lần.
- Dòng nào có thời gian thực thi lớn.
- Đường đi thực tế có khác dự đoán không.

Các bảng profiler cần được cài đặt và cấp quyền theo hướng dẫn Oracle trong môi trường mục tiêu. Tên bảng thường gặp là PLSQL_PROFILER_RUNS, PLSQL_PROFILER_UNITS và PLSQL_PROFILER_DATA.

Ví dụ khung chạy:

~~~sql
BEGIN
    DBMS_PROFILER.START_PROFILER(
        run_comment => 'Baseline order calculation'
    );

    order_api.recalculate_order(p_order_id => 1001);

    DBMS_PROFILER.STOP_PROFILER;
END;
/
~~~

Nếu workload phát sinh exception, cần bảo đảm profiler được dừng trong nhánh exception:

~~~sql
BEGIN
    DBMS_PROFILER.START_PROFILER(
        run_comment => 'Order calculation test'
    );

    BEGIN
        order_api.recalculate_order(p_order_id => 1001);
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_PROFILER.STOP_PROFILER;
            RAISE;
    END;

    DBMS_PROFILER.STOP_PROFILER;
END;
/
~~~

Đoạn này minh họa quản lý profiler trong bài thử. Trong harness thực tế, hãy tránh gọi STOP_PROFILER hai lần và xử lý riêng trường hợp START_PROFILER không thành công.

### 4.2 Đọc dữ liệu profiler

Sau khi profiler chạy, dữ liệu được ghi vào các bảng profiler đã cài đặt. Có thể nối run, unit và line data để tìm dòng có số lần thực thi và thời gian cao.

Ví dụ khung truy vấn:

~~~sql
SELECT u.unit_name,
       d.line#,
       d.total_occur,
       d.total_time
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
WHERE d.runid = :run_id
ORDER BY d.total_time DESC;
~~~

Tên cột và cách lưu thời gian phụ thuộc phiên bản/cài đặt profiler. Kiểm tra metadata của bảng profiler được cài trong schema trước khi sử dụng truy vấn báo cáo; không coi truy vấn khung là script triển khai dùng cho mọi phiên bản.

### 4.3 DBMS_HPROF: hierarchical profiler

DBMS_HPROF thu thập thời gian theo cấu trúc gọi phân cấp. Nó hữu ích để biết thời gian nằm ở:

- Subprogram được gọi trực tiếp.
- Các subprogram con.
- SQL được thực thi trong luồng gọi.
- Một nhánh được gọi nhiều lần từ nhiều nơi.

Khác biệt khái quát:

| Công cụ | Trọng tâm |
|---|---|
| DBMS_PROFILER | Dòng source và đơn vị PL/SQL |
| DBMS_HPROF | Cây lời gọi và thời gian theo subprogram |
| SQL Trace/TKPROF | Parse, execute, fetch, wait và SQL statistics |

Để dùng DBMS_HPROF, DBA cần cấu hình directory object và quyền đọc/ghi phù hợp. Ví dụ khung:

~~~sql
BEGIN
    DBMS_HPROF.START_PROFILING(
        location => 'PLSQL_PROF_DIR',
        filename => 'order_profile.trc'
    );

    order_api.recalculate_order(p_order_id => 1001);

    DBMS_HPROF.STOP_PROFILING;
END;
/
~~~

PLSQL_PROF_DIR là directory object ở phía database server, không phải thư mục trên máy client. File profile được tạo ở đường dẫn server đã gắn với object. Việc phân tích trace và lưu báo cáo cần package/table hỗ trợ được cài theo phiên bản Oracle.

### 4.4 Profiler có overhead

Profiler thêm công việc để ghi số liệu. Vì vậy:

- Dùng profiler để tìm hotspot tương đối.
- Không lấy elapsed time của một lần chạy đang profiling làm benchmark cuối cùng.
- Sau khi tìm được bottleneck, chạy lại phép đo end-to-end không bật profiler.
- Dùng cùng workload trước và sau để so sánh.

## 5. Đo SQL bên trong PL/SQL

Nếu procedure chậm vì SQL, cần điều tra câu SQL cụ thể.

### 5.1 Gắn module và action

DBMS_APPLICATION_INFO giúp đặt MODULE và ACTION trong session:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'RECALCULATE'
    );

    order_api.recalculate_order(p_order_id => 1001);

    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => NULL,
        action_name => NULL
    );
END;
/
~~~

MODULE/ACTION giúp DBA nhận diện workload trong các view giám sát và trace. Nếu ứng dụng dùng connection pool, cần đặt lại module/action khi đổi request để không gán nhầm hoạt động của request trước.

Có thể dùng SET_ACTION để đổi action trong từng giai đoạn:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION('VALIDATE');
    -- Validate input.

    DBMS_APPLICATION_INFO.SET_ACTION('UPDATE_ORDER');
    -- Execute DML.

    DBMS_APPLICATION_INFO.SET_ACTION('WRITE_AUDIT');
    -- Write audit.
END;
/
~~~

### 5.2 Xem actual execution plan

Để xem số hàng và buffer thực tế của SQL, có thể dùng GATHER_PLAN_STATISTICS trong môi trường kiểm thử:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       salary
FROM employees
WHERE department_id = 10;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

Trong plan, so sánh E-Rows và A-Rows, Starts, Buffers, Reads và Predicate Information. Nếu SQL bên trong procedure dùng bind variable, cần kiểm tra plan của cursor thực tế tương ứng với bind values và child cursor đang chạy.

### 5.3 SQL Trace và TKPROF

SQL Trace thu thập thông tin parse, execute, fetch và wait cho session hoặc workload được chọn. TKPROF định dạng trace thành báo cáo dễ đọc.

Ví dụ bật/tắt trace cho session hiện tại:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/

BEGIN
    order_api.recalculate_order(p_order_id => 1001);
END;
/

BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

Trace file được ghi trên database server. DBA hoặc người có quyền phù hợp dùng TKPROF để phân tích. Binds được tắt trong ví dụ để tránh ghi dữ liệu đầu vào; chỉ bật bind tracing khi cần thiết và đã đánh giá quyền riêng tư/bảo mật.

### 5.4 Không nhầm SQL time với PL/SQL time

Một procedure có thể gọi một SQL statement 10.000 lần. SQL Trace sẽ cho thấy số executions lớn và tổng elapsed/CPU của statement. DBMS_HPROF có thể cho thấy lời gọi subprogram chứa vòng lặp. Kết hợp hai nguồn giúp xác định nguyên nhân là:

- Vòng lặp PL/SQL quá nhiều lần.
- SQL được gọi theo từng hàng.
- Mỗi lần SQL chạy có plan đắt.
- Một hàm PL/SQL được gọi nhiều lần từ SQL.

## 6. Native compilation là gì?

PL/SQL có thể được biên dịch theo hai dạng chính:

- INTERPRETED: PL/SQL được biên dịch sang dạng trung gian và được PL/SQL engine thực thi.
- NATIVE: PL/SQL được biên dịch thành mã native phù hợp với nền tảng database để thực thi trực tiếp hơn.

Tham số compiler điều khiển là PLSQL_CODE_TYPE:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
~~~

hoặc:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = NATIVE;
~~~

Native compilation nhằm giảm overhead thực thi của phần PL/SQL. Nó phù hợp hơn với chương trình CPU-bound có nhiều phép tính, vòng lặp hoặc thao tác dữ liệu trong bộ nhớ.

### 6.1 Native compilation không biên dịch SQL thành mã native của PL/SQL

Trong một procedure:

~~~sql
BEGIN
    l_total := calculate_tax(l_amount);

    UPDATE orders
    SET tax_amount = l_total
    WHERE order_id = p_order_id;
END;
~~~

Native compilation có thể tác động tới phần PL/SQL như gọi hàm, phép tính và điều khiển luồng. Câu UPDATE vẫn được SQL engine parse, optimize và execute theo cơ chế SQL của Oracle.

Nếu UPDATE mất 95% tổng thời gian, native compilation không phải giải pháp chính.

### 6.2 Khi nào native compilation có thể hữu ích?

Các workload có thể hưởng lợi:

- Tính toán số học trong PL/SQL với số vòng lặp lớn.
- Xử lý chuỗi hoặc dữ liệu trong bộ nhớ mà không gọi SQL liên tục.
- Thuật toán PL/SQL thuần CPU.
- Các subprogram được gọi rất nhiều lần và phần overhead PL/SQL đáng kể.

Các workload thường ít hưởng lợi:

- Chờ disk I/O.
- SQL có execution plan kém.
- Chờ row lock hoặc contention.
- Gọi remote service.
- Chuyển dữ liệu quá lớn giữa client và database.
- Procedure chủ yếu thực hiện một câu SQL set-based vốn đã nhanh.

### 6.3 Native compilation không tự động làm mọi procedure nhanh hơn

Lợi ích phụ thuộc:

- Tỷ lệ thời gian CPU thuộc PL/SQL.
- Số lần gọi và độ lớn workload.
- Thuật toán và kiểu dữ liệu.
- Phiên bản Oracle, kiến trúc và cấu hình.
- Compiler settings.
- Overhead compile và triển khai.

Hãy benchmark interpreted và native trên cùng một workload. Không bật native trên toàn hệ thống chỉ vì tên gọi nghe có vẻ nhanh hơn.

## 7. Cấu hình PLSQL_CODE_TYPE

### 7.1 Kiểm tra setting hiện tại của object

View USER_PLSQL_OBJECT_SETTINGS cho biết các compiler setting của PL/SQL object trong schema:

~~~sql
SELECT name,
       type,
       plsql_code_type,
       plsql_optimize_level,
       plsql_warnings
FROM user_plsql_object_settings
ORDER BY name, type;
~~~

Có thể lọc một object:

~~~sql
SELECT name,
       type,
       plsql_code_type,
       plsql_optimize_level
FROM user_plsql_object_settings
WHERE name = UPPER('ORDER_API');
~~~

Tên object thường được lưu uppercase nếu không tạo bằng quoted identifier.

### 7.2 Đổi session setting rồi biên dịch lại object

Ví dụ thử native compilation cho procedure trong schema kiểm thử:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = NATIVE;

ALTER PROCEDURE recalculate_order COMPILE;
~~~

Với package, cần biên dịch phần phù hợp:

~~~sql
ALTER PACKAGE order_api COMPILE BODY;
~~~

Sau đó kiểm tra lại USER_PLSQL_OBJECT_SETTINGS để xác nhận code type của object đã biên dịch. Thay đổi ALTER SESSION không tự chuyển các object đã biên dịch trước đó sang native; cần compile lại object dưới setting mong muốn.

### 7.3 Setting cấp hệ thống

DBA có thể đặt PLSQL_CODE_TYPE ở cấp hệ thống để điều khiển các lần compile trong tương lai:

~~~sql
ALTER SYSTEM SET PLSQL_CODE_TYPE = NATIVE SCOPE = BOTH;
~~~

Đây là thay đổi cấu hình database, cần quyền quản trị và kế hoạch triển khai. Nó không có nghĩa mọi PL/SQL object hiện hữu tự động được biên dịch lại ngay lập tức.

Đối với một thí nghiệm, ưu tiên dùng session setting trong schema kiểm thử để tránh ảnh hưởng compile của workload khác.

### 7.4 Phiên bản và triển khai native code

Chi tiết cơ chế tạo/lưu mã native đã thay đổi qua các phiên bản Oracle. DBA cần làm theo tài liệu đúng phiên bản và nền tảng, kiểm tra cấu hình compiler/runtime và quy trình backup/upgrade. Không áp dụng hướng dẫn thư mục hoặc C compiler của phiên bản cũ cho database mới nếu chưa xác nhận.

## 8. PLSQL_OPTIMIZE_LEVEL

PLSQL_OPTIMIZE_LEVEL điều khiển mức tối ưu hóa của compiler PL/SQL.

Các mức phổ biến:

| Mức | Ý nghĩa khái quát |
|---:|---|
| 0 | Hạn chế/không thực hiện các tối ưu hóa compiler thông thường |
| 1 | Tối ưu hóa cơ bản, thận trọng |
| 2 | Mức tối ưu tiêu chuẩn và là mặc định phổ biến |
| 3 | Mức tối ưu hóa cao hơn, compiler có thể thực hiện thêm biến đổi |

Kiểm tra:

~~~sql
SHOW PARAMETER PLSQL_OPTIMIZE_LEVEL
~~~

Trong PL/SQL:

~~~sql
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
~~~

### 8.1 Level 2 là điểm bắt đầu thông thường

Level 2 là mức mặc định phổ biến cho code production. Compiler có thể thực hiện các tối ưu hóa tiêu chuẩn như loại bỏ công việc không cần thiết và biến đổi code phù hợp.

Không hạ xuống level 0 chỉ để debug rồi quên biên dịch lại production. Không tăng level 3 chỉ vì số cao hơn; hãy đo và regression test.

### 8.2 Level 3 cần kiểm thử

Level 3 cho phép compiler thực hiện nhiều tối ưu hóa hơn. Điều này có thể cải thiện một số workload nhưng cũng làm thay đổi cách sắp xếp/triển khai các thao tác nội bộ.

Hãy kiểm thử:

- Kết quả nghiệp vụ.
- Exception và vị trí phát sinh lỗi quan sát được.
- Code phụ thuộc side effect hoặc thứ tự đánh giá biểu thức.
- Hiệu năng trên nhiều kích thước input.

Không dựa vào một thứ tự đánh giá biểu thức mà ngôn ngữ không bảo đảm.

### 8.3 Setting compiler có hiệu lực khi compile

PLSQL_OPTIMIZE_LEVEL là compiler setting. Thay đổi session setting không làm thay đổi mã của object đã compile. Cần biên dịch lại object dưới setting mới và kiểm tra metadata sau compile.

## 9. PLSQL_WARNINGS và chất lượng code

Compiler warnings giúp phát hiện một số vấn đề trước runtime, ví dụ biến không dùng, code không thể thực thi hoặc cấu trúc đáng nghi.

Bật warnings:

~~~sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
~~~

Biên dịch lại:

~~~sql
ALTER PROCEDURE recalculate_order COMPILE;
~~~

Xem lỗi/cảnh báo:

~~~sql
SELECT name,
       type,
       line,
       position,
       attribute,
       message_number,
       text
FROM user_errors
WHERE name = UPPER('RECALCULATE_ORDER')
ORDER BY sequence;
~~~

Trong SQL*Plus hoặc SQLcl, có thể dùng:

~~~sql
SHOW ERRORS PROCEDURE recalculate_order
~~~

Warnings không thay thế unit test, profiler hoặc review. Chúng là một lớp phản hồi bổ sung từ compiler.

### 9.1 Cấu hình warnings theo policy

Có thể bật/tắt một nhóm warning cụ thể theo mã cảnh báo. Ví dụ:

~~~sql
ALTER SESSION SET PLSQL_WARNINGS =
    'ENABLE:ALL', 'DISABLE:06002';
~~~

Không tắt warning chỉ để build sạch nếu chưa hiểu nguyên nhân. Ghi lại policy trong quy trình build để các môi trường compile nhất quán.

## 10. PRAGMA INLINE và tối ưu lời gọi subprogram

Khi một subprogram nhỏ được gọi rất nhiều lần, overhead của lời gọi có thể trở thành phần đáng kể. Compiler có thể inline một số lời gọi; PRAGMA INLINE cho phép yêu cầu compiler thử inline tại vị trí gọi.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_batch AS
    FUNCTION add_tax(p_amount NUMBER)
        RETURN NUMBER
    IS
    BEGIN
        RETURN p_amount * 1.08;
    END;

    l_total NUMBER := 0;
BEGIN
    FOR i IN 1 .. 100000 LOOP
        PRAGMA INLINE(add_tax, 'YES');
        l_total := l_total + add_tax(i);
    END LOOP;
END;
/
~~~

PRAGMA INLINE là một yêu cầu tối ưu hóa; compiler có thể không inline nếu không thể hoặc không phù hợp. Cần kiểm tra kết quả trên đúng phiên bản và đo hiệu năng. Inline cũng có thể làm code lớn hơn hoặc thay đổi đặc tính debug.

Không inline mọi function theo mặc định. Function lớn hoặc chỉ được gọi ít lần thường không có lý do để ép inline.

## 11. PRAGMA UDF khi function được gọi từ SQL

Khi SQL gọi một PL/SQL function cho nhiều hàng, có chi phí chuyển đổi giữa SQL engine và PL/SQL engine. PRAGMA UDF thông báo function chủ yếu được gọi từ SQL và có thể giúp giảm overhead này trong các phiên bản hỗ trợ.

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION calculate_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    IF p_region_code = 'VN' THEN
        RETURN 0.10;
    ELSE
        RETURN 0.08;
    END IF;
END;
/
~~~

Truy vấn:

~~~sql
SELECT order_id,
       amount,
       amount * calculate_tax_rate(region_code) AS tax_amount
FROM orders;
~~~

PRAGMA UDF không làm cho function trở thành SQL macro, không biến nó thành một biểu thức SQL thuần và không loại bỏ mọi chi phí gọi PL/SQL. Nếu logic có thể biểu diễn trực tiếp bằng SQL, hãy so sánh với biểu thức SQL thuần trước.

Chỉ dùng khi function thực sự được gọi từ SQL và profiler/benchmark cho thấy overhead đáng kể.

## 12. RESULT_CACHE và DETERMINISTIC

Một function tốn chi phí tính toán nhưng trả cùng kết quả cho cùng input có thể là ứng viên cho caching, nếu phụ thuộc dữ liệu và semantics cho phép.

### 12.1 RESULT_CACHE

Function result cache có thể lưu kết quả của function và tái sử dụng khi input tương ứng được gọi lại. Oracle quản lý invalidation dựa trên các phụ thuộc dữ liệu được hỗ trợ.

Ví dụ khung:

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER
RESULT_CACHE
IS
BEGIN
    -- Đọc bảng cấu hình thuế hoặc tính giá trị phù hợp.
    RETURN 0.10;
END;
/
~~~

Ví dụ chỉ minh họa vị trí mệnh đề RESULT_CACHE. Function thực tế phải có semantics an toàn cho caching, không phụ thuộc session state không được quản lý hoặc side effect.

### 12.2 DETERMINISTIC không phải cache

DETERMINISTIC là lời khai báo rằng function trả cùng kết quả cho cùng input. Oracle có thể dùng thông tin này trong một số tối ưu hóa, nhưng từ khóa này không tự tạo một cache kết quả chung.

Không khai báo DETERMINISTIC nếu function đọc dữ liệu thay đổi, phụ thuộc SYSDATE, package global, session context hoặc trạng thái ngoài input mà không bảo đảm cùng kết quả.

### 12.3 Khi nào caching không phù hợp?

- Input gần như luôn khác nhau.
- Dữ liệu thay đổi liên tục.
- Function phụ thuộc NLS/session context.
- Function có side effect.
- Chi phí lookup cache lớn hơn chi phí tính lại.
- Cần tính toán theo snapshot nghiệp vụ riêng.

Đo hit rate và tính đúng đắn trước khi đưa caching vào production.

## 13. Tối ưu SQL trước khi tối ưu vòng lặp PL/SQL

Một nguyên tắc quan trọng là chuyển công việc về SQL set-based khi phù hợp.

### 13.1 Row-by-row processing

Ví dụ xử lý từng nhân viên:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = rec.salary * 1.05
        WHERE employee_id = rec.employee_id;
    END LOOP;
END;
/
~~~

Mỗi vòng lặp gọi một câu UPDATE. Nếu có 50.000 hàng, SQL engine có thể nhận 50.000 lần DML.

### 13.2 Dùng một câu UPDATE set-based

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

SQL engine xử lý toàn bộ tập hàng trong một statement. Đây thường là cách đơn giản và hiệu quả hơn nếu logic áp dụng được cho cả tập dữ liệu.

### 13.3 Dùng MERGE khi cần upsert

Nếu cần cập nhật hàng đã có và thêm hàng chưa có, cân nhắc MERGE thay vì vòng lặp SELECT rồi INSERT/UPDATE từng hàng:

~~~sql
MERGE INTO employee_summary target
USING employee_stage source
   ON (target.employee_id = source.employee_id)
WHEN MATCHED THEN
    UPDATE SET target.salary = source.salary
WHEN NOT MATCHED THEN
    INSERT (employee_id, salary)
    VALUES (source.employee_id, source.salary);
~~~

MERGE không tự động luôn nhanh hơn mọi cách khác; cần xem constraint, nguồn dữ liệu, số hàng và plan. Nhưng nó giúp biểu diễn thao tác tập hợp trong một statement.

## 14. Context switch giữa PL/SQL và SQL

Mỗi lần PL/SQL gọi SQL, dữ liệu và điều khiển được chuyển giữa hai engine. Một lần chuyển đổi thường nhỏ, nhưng hàng trăm nghìn hoặc hàng triệu lần có thể tạo overhead đáng kể.

Mẫu thường gặp:

~~~text
PL/SQL loop
   |
   +--> SQL UPDATE one row
   |
   +--> SQL UPDATE one row
   |
   +--> SQL UPDATE one row
   |
   +--> ... repeated many times
~~~

Các kỹ thuật giảm context switch:

- Dùng một câu SQL set-based nếu có thể.
- Dùng BULK COLLECT để lấy nhiều hàng mỗi lần.
- Dùng FORALL để gửi nhiều DML trong một lần bulk binding.
- Không gọi function PL/SQL từ SQL hàng triệu lần nếu có biểu thức SQL tương đương.
- Tránh SELECT trong vòng lặp chỉ để lấy dữ liệu có thể join trong một truy vấn.

## 15. BULK COLLECT và FORALL

### 15.1 BULK COLLECT

BULK COLLECT lấy nhiều hàng từ SQL vào collection:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Fetched=' || l_ids.COUNT);
END;
/
~~~

Thay vì chuyển từng hàng một, bulk collect lấy một tập hàng vào bộ nhớ PL/SQL.

### 15.2 Dùng LIMIT để kiểm soát bộ nhớ

Không nên BULK COLLECT toàn bộ bảng rất lớn vào collection nếu không cần. Dùng cursor và LIMIT:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 10;

    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_ids
        LIMIT 500;

        EXIT WHEN l_ids.COUNT = 0;

        DBMS_OUTPUT.PUT_LINE(
            'Batch size=' || l_ids.COUNT
        );
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
~~~

LIMIT giúp giới hạn số hàng mỗi batch và kiểm soát bộ nhớ. Giá trị 500 chỉ là ví dụ; cần benchmark với kích thước hàng, PGA và workload thực tế.

### 15.3 FORALL

FORALL gửi DML theo collection index:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);
END;
/
~~~

FORALL giảm số lần chuyển đổi giữa PL/SQL và SQL cho DML lặp theo collection. Nó không phải vòng lặp PL/SQL thông thường và không hỗ trợ mọi cấu trúc điều khiển bên trong như LOOP.

### 15.4 SAVE EXCEPTIONS

Nếu một số lần DML trong FORALL có thể lỗi nhưng muốn tiếp tục các phần tử khác, có thể dùng SAVE EXCEPTIONS và đọc SQL%BULK_EXCEPTIONS:

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids := t_ids(1001, 1002, 999999);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', code=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;
END;
/
~~~

SAVE EXCEPTIONS thay đổi cách lỗi của từng lần DML được báo lại. Phải thiết kế rõ phần tử thành công/thất bại, rowcount và transaction policy; không mặc định toàn batch đã rollback.

## 16. Chọn batch size

Batch size quá nhỏ làm tăng số lần fetch và bulk execution. Batch size quá lớn làm tăng bộ nhớ và có thể ảnh hưởng PGA/concurrency.

Hãy thử một số kích thước đại diện, ví dụ 100, 500, 1.000 và 5.000, nhưng không coi đây là các ngưỡng chuẩn. Đo:

- Elapsed time.
- CPU.
- PGA/memory pressure.
- Số batch.
- Số hàng xử lý.
- Waits và tác động tới session khác.

Chọn batch size dựa trên workload và giới hạn bộ nhớ của môi trường, không dựa vào một con số phổ biến trên Internet.

## 17. Tối ưu thuật toán PL/SQL

Native compilation không cứu được thuật toán có độ phức tạp quá cao.

Ví dụ tìm một giá trị bằng cách duyệt lồng nhau:

~~~sql
FOR i IN 1 .. l_left.COUNT LOOP
    FOR j IN 1 .. l_right.COUNT LOOP
        IF l_left(i) = l_right(j) THEN
            ...
        END IF;
    END LOOP;
END LOOP;
~~~

Với hai collection có N phần tử, cách làm này có thể thực hiện số phép so sánh tỷ lệ với N bình phương.

Nếu có thể đưa dữ liệu vào SQL, JOIN hoặc EXISTS có thể cho optimizer lựa chọn thuật toán join phù hợp. Nếu phải xử lý trong PL/SQL, cân nhắc cấu trúc dữ liệu tra cứu phù hợp, chẳng hạn associative array theo key.

Các câu hỏi khi tối ưu:

- Có lặp lại cùng một phép tính không?
- Có thể tính trước giá trị bất biến ngoài vòng lặp không?
- Có thể thay nested loop bằng lookup theo key không?
- Có thể giảm số lần parse hoặc gọi function không?
- Có thể tránh chuyển đổi kiểu trong vòng lặp không?
- Có thể xử lý cả tập bằng SQL thay vì từng hàng không?

## 18. Tránh công việc thừa trong PL/SQL

Một số điều chỉnh nhỏ có thể có ích khi profiler chứng minh chúng nằm trên đường nóng:

- Đưa biểu thức không đổi ra ngoài vòng lặp.
- Tránh gọi TO_CHAR/TO_NUMBER lặp lại nếu dữ liệu có thể giữ đúng kiểu.
- Tránh tạo chuỗi lớn nhiều lần bằng phép nối không cần thiết.
- Giảm gọi function lồng nhau trong đường nóng.
- Dùng PLS_INTEGER cho counter có miền 32-bit phù hợp.
- Không truy vấn lại dữ liệu đã có trong biến/collection.
- Tránh dùng exception như nhánh điều khiển bình thường trong vòng lặp lớn.

Không thay code chỉ vì nó trông gọn hơn. Hãy đo trước và sau.

## 19. Native compilation và bulk processing giải quyết hai vấn đề khác nhau

| Kỹ thuật | Vấn đề hướng tới | Không giải quyết trực tiếp |
|---|---|---|
| Native compilation | Overhead thực thi PL/SQL CPU-bound | SQL plan, I/O, lock waits |
| PLSQL_OPTIMIZE_LEVEL | Compiler optimization | Thuật toán tệ hoặc SQL đắt |
| BULK COLLECT | Nhiều lần fetch qua engine boundary | PGA quá nhỏ nếu batch không kiểm soát |
| FORALL | DML lặp theo collection/context switch | Logic cần xử lý từng hàng phức tạp hoặc SQL plan kém |
| Set-based SQL | Xử lý tập dữ liệu trong SQL engine | Side effect thủ tục không thể biểu diễn bằng SQL |
| PRAGMA UDF | Overhead function PL/SQL được gọi từ SQL | Function có logic/SQL bên trong vốn đã đắt |
| PRAGMA INLINE | Overhead lời gọi subprogram nhỏ | I/O và SQL execution |
| RESULT_CACHE | Tính lại kết quả ổn định, lặp lại | Input luôn khác hoặc dữ liệu thay đổi liên tục |

Không áp dụng nhiều kỹ thuật cùng lúc trong một lần benchmark, vì sẽ khó biết yếu tố nào tạo ra khác biệt.

## 20. Một quy trình benchmark native compilation

### Bước 1: Chọn workload đại diện

Chọn procedure CPU-bound đã được profiler xác định. Ghi input, số lần gọi, dữ liệu và kết quả mong đợi.

### Bước 2: Ghi baseline INTERPRETED

Đặt:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
~~~

Biên dịch lại object trong session với setting này:

~~~sql
ALTER PROCEDURE calculate_commission COMPILE;
~~~

Xác nhận setting trong USER_PLSQL_OBJECT_SETTINGS. Chạy warm-up và các lượt benchmark không bật profiler.

### Bước 3: Ghi baseline

Lưu:

- Elapsed time median/p95.
- CPU time nếu có.
- Kết quả nghiệp vụ.
- Số lần gọi.
- Input size.
- SQL metrics liên quan.
- Compiler settings.

### Bước 4: Compile NATIVE

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = NATIVE;
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;

ALTER PROCEDURE calculate_commission COMPILE;
~~~

Xác nhận code type của object đã là NATIVE trong view settings.

### Bước 5: Chạy cùng workload

Dùng cùng input, cùng session settings và cách đo. Không chạy profiler ở lượt benchmark cuối nếu baseline không bật profiler.

### Bước 6: So sánh và kiểm thử

So sánh elapsed, CPU, kết quả, lỗi và tác động concurrency. Nếu chênh lệch không đáng kể hoặc không ổn định, giữ cấu hình đơn giản hơn.

### Bước 7: Triển khai có kiểm soát

Lập danh sách object cần compile, xác nhận status VALID, kiểm tra dependent object và có phương án quay lại setting đã biết. Không thay PLSQL_CODE_TYPE toàn database khi chưa có phạm vi và kế hoạch.

## 21. Ví dụ so sánh interpreted và native

Ví dụ workload tính tổng trong bộ nhớ:

~~~sql
CREATE OR REPLACE PROCEDURE sum_values (
    p_iterations IN PLS_INTEGER,
    p_result OUT NUMBER
) AS
    l_total NUMBER := 0;
BEGIN
    FOR i IN 1 .. p_iterations LOOP
        l_total := l_total + SQRT(i);
    END LOOP;

    p_result := l_total;
END;
/
~~~

Procedure này minh họa workload CPU-bound, dù SQRT là hàm số học có thể có đặc tính riêng theo phiên bản. Có thể thử cùng số vòng lặp dưới hai code type.

Để benchmark tốt hơn:

- Chạy nhiều lượt với cùng p_iterations.
- Không in kết quả trong vòng lặp.
- Ghi p_result để xác nhận công việc không bị loại bỏ khỏi luồng sử dụng.
- So sánh CPU và elapsed.
- Chạy riêng với input nhỏ, vừa và lớn.
- Không kết luận từ một procedure tổng hợp rằng toàn ứng dụng sẽ nhanh hơn tương tự.

## 22. Đo và tối ưu function được gọi trong SQL

Một function PL/SQL có thể được gọi một lần cho mỗi hàng trong SQL:

~~~sql
SELECT order_id,
       calculate_discount(customer_id, amount)
FROM orders;
~~~

Nếu truy vấn trả 1 triệu hàng, function có thể được gọi rất nhiều lần. Cần xem:

1. Function có thể biểu diễn bằng SQL expression hoặc JOIN không?
2. Function có truy vấn SQL bên trong mỗi lần gọi không?
3. Có thể dùng PRAGMA UDF không?
4. Có thể cache kết quả an toàn không?
5. Function có phụ thuộc session context hoặc dữ liệu thay đổi không?

Nếu function thực hiện SELECT riêng cho từng hàng, vấn đề có thể là N+1 SQL pattern. Native compilation không loại bỏ số lần SELECT đó. Hãy thử JOIN hoặc set-based SQL.

## 23. Dynamic SQL, parse và bind variables

Tạo SQL text khác nhau cho mỗi giá trị đầu vào có thể làm tăng hard parse và shared pool pressure.

Không nên:

~~~sql
l_sql := 'SELECT salary FROM employees WHERE employee_id = ' ||
         TO_CHAR(p_employee_id);
EXECUTE IMMEDIATE l_sql INTO l_salary;
~~~

Nên bind:

~~~sql
l_sql := 'SELECT salary FROM employees WHERE employee_id = :id';

EXECUTE IMMEDIATE l_sql
INTO l_salary
USING p_employee_id;
~~~

Bind variables giúp tái sử dụng cursor khi SQL text tương thích và tránh ghép dữ liệu đầu vào vào SQL. Tên bảng/cột không thể bind như giá trị; nếu cần dynamic object name, phải kiểm soát bằng allowlist và xác thực phù hợp.

## 24. Phân biệt compile time và runtime

Các thao tác sau có mục đích khác nhau:

| Thao tác | Thời điểm tác động | Ý nghĩa |
|---|---|---|
| ALTER SESSION SET PLSQL_CODE_TYPE | Khi compile trong session | Chọn code type cho lần compile tiếp theo |
| ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL | Khi compile trong session | Chọn mức tối ưu compiler |
| ALTER PROCEDURE ... COMPILE | Compile time | Biên dịch lại procedure |
| DBMS_HPROF/DBMS_PROFILER | Runtime | Thu thập profile |
| SQL Trace | Runtime | Thu thập hoạt động SQL và waits |
| DBMS_XPLAN.DISPLAY_CURSOR | Sau/đang thực thi cursor | Xem execution plan và thống kê có sẵn |

Đổi tham số compiler mà không recompile object không thay đổi mã đã compile. Ngược lại, profiler không thay đổi code type; nó chỉ quan sát quá trình chạy và có overhead.

## 25. Cẩn thận khi tối ưu trên production

Một thay đổi compiler hoặc source có thể ảnh hưởng nhiều object phụ thuộc. Trước khi triển khai:

- Thử ở môi trường gần production.
- Xác nhận code type/optimize level theo object.
- Compile trong thời gian triển khai có kiểm soát.
- Kiểm tra USER_OBJECTS/DBA_OBJECTS để xác nhận object VALID.
- Kiểm tra USER_ERRORS/DBA_ERRORS.
- Kiểm thử luồng gọi từ ứng dụng.
- Theo dõi CPU, elapsed, waits và lỗi sau triển khai.
- Có kế hoạch recompile lại với setting trước đó nếu kết quả xấu.

Không chạy ALTER SYSTEM chỉ để thử một procedure. Không compile toàn bộ schema khi chưa biết phạm vi invalidation và tác động workload.

## 26. Cách đọc kết quả tối ưu

Ví dụ bảng benchmark:

| Phiên bản | Median elapsed | CPU | Buffers | Kết quả đúng? |
|---|---:|---:|---:|---|
| Baseline interpreted | 8,2 s | 7,4 s | 120.000 | Có |
| Native | 7,8 s | 7,0 s | 120.000 | Có |
| Bulk DML | 2,1 s | 1,7 s | 35.000 | Có |

Các con số chỉ là ví dụ minh họa, không phải benchmark Oracle thực tế. Nếu native giảm thời gian một ít nhưng bulk DML giảm mạnh cả CPU và buffers, dữ liệu gợi ý bottleneck chính là row-by-row/context switching hoặc SQL work.

Một kết quả tốt cần:

- Cùng workload và cùng điều kiện.
- Kết quả nghiệp vụ tương đương.
- Cải thiện lặp lại được.
- Không tạo regression cho input khác.
- Không tăng mạnh PGA, contention hoặc chi phí vận hành.

## 27. Sơ đồ chọn kỹ thuật tối ưu

~~~mermaid
flowchart TD
    A["Đo elapsed, CPU, waits và SQL metrics"] --> B{"Thời gian chủ yếu nằm ở SQL?"}
    B -->|Có| C["Xem actual plan, buffers, rows và waits"]
    C --> D["Tối ưu SQL, index, join hoặc set-based DML"]
    B -->|Không| E{"PL/SQL CPU-bound?"}
    E -->|Có| F["Dùng profiler tìm subprogram/dòng nóng"]
    F --> G{"Nhiều SQL call theo từng hàng?"}
    G -->|Có| H["Set-based SQL hoặc BULK COLLECT/FORALL"]
    G -->|Không| I["Tối ưu thuật toán và phép tính"]
    I --> J{"Overhead PL/SQL vẫn đáng kể?"}
    J -->|Có| K["Benchmark NATIVE và compiler settings"]
    J -->|Không| L["Giữ implementation đơn giản"]
    E -->|Không| M["Điều tra wait, lock, I/O và concurrency"]
    D --> N["Đo lại, regression test"]
    H --> N
    K --> N
    L --> N
    M --> N
~~~

## 28. Những lỗi thường gặp khi tối ưu

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Bật NATIVE cho toàn database vì nghĩ luôn nhanh | Tăng phạm vi thay đổi mà không biết lợi ích | Thử trên object CPU-bound và đo |
| Đổi PLSQL_CODE_TYPE nhưng không compile lại | Object vẫn chạy code đã compile trước | Recompile và kiểm tra object settings |
| Chỉ đo một lần | Kết quả bị ảnh hưởng bởi cache/tải | Chạy lặp và so median/p95 |
| Dùng elapsed để kết luận CPU bottleneck | Không phân biệt wait và CPU | Kết hợp CPU, waits, profiler |
| Tối ưu PL/SQL trong khi SQL plan kém | Bottleneck chính vẫn còn | Xem actual plan và SQL trace |
| Dùng BULK COLLECT không LIMIT trên bảng lớn | Tăng PGA, có thể thiếu bộ nhớ | Fetch theo batch |
| Dùng FORALL cho logic có thể làm bằng một UPDATE | Phức tạp hơn và vẫn không tối ưu bằng set-based SQL | Thử set-based trước |
| Tăng PLSQL_OPTIMIZE_LEVEL mà không regression test | Có thể phát sinh thay đổi hành vi quan sát được | Kiểm thử và benchmark |
| Dùng DETERMINISTIC cho function không thuần | Kết quả cache/optimization không còn đáng tin | Chỉ khai báo khi thật sự deterministic |
| Dùng RESULT_CACHE cho dữ liệu thay đổi liên tục | Hit rate thấp hoặc invalidation thường xuyên | Đo hit rate và dependency |
| Bật profiler trong benchmark cuối | Instrumentation làm thay đổi thời gian | Dùng profiler tìm hotspot, benchmark lại không profiler |
| Đo có DBMS_OUTPUT từng hàng | Đo overhead logging thay vì logic | Giảm output trong vùng đo |
| Thay nhiều kỹ thuật cùng lúc | Không biết yếu tố nào tạo cải thiện/regression | Thử từng thay đổi riêng |
| Chỉ so cost của EXPLAIN PLAN | Cost là ước lượng, không phải runtime | Xem actual rows, buffers, CPU, elapsed và waits |

## 29. Bài thực hành tự kiểm tra

Các bài thực hành nên chạy trong schema thử nghiệm, với workload có thể lặp lại.

### Bài 1 — Baseline

Viết procedure CPU-bound và đo bằng SYSTIMESTAMP hoặc DBMS_UTILITY.GET_TIME. Chạy nhiều lần, ghi median, input size và kết quả.

### Bài 2 — DBMS_PROFILER

Cài profiler theo hướng dẫn DBA. Chạy procedure có nhiều helper function. Tìm unit và line có thời gian cao nhất. Đo lại sau khi tắt profiler.

### Bài 3 — DBMS_HPROF

Tạo cây gọi A -> B -> C. Profile bằng hierarchical profiler và xác định subprogram nào chiếm inclusive/exclusive time lớn.

### Bài 4 — SQL Trace

Bật trace cho session chạy procedure có nhiều SQL. Dùng TKPROF đọc executions, parse, CPU, elapsed và waits. Xác định SQL được gọi nhiều lần.

### Bài 5 — Interpreted và Native

Compile cùng một procedure với INTERPRETED rồi NATIVE. Kiểm tra USER_PLSQL_OBJECT_SETTINGS, chạy cùng workload nhiều lần và so CPU/elapsed.

### Bài 6 — Optimize level

So sánh level 1, 2 và 3 trong schema thử nghiệm. Xác nhận output/exception và đo trên nhiều kích thước input. Không thay đổi setting toàn database.

### Bài 7 — Row-by-row và set-based

Viết một vòng lặp UPDATE từng hàng, sau đó thay bằng một câu UPDATE. So sánh elapsed, CPU, buffers và số lần thực thi SQL.

### Bài 8 — BULK COLLECT LIMIT

Đọc dữ liệu theo batch với LIMIT 100, 500, 1.000 và 5.000. So sánh elapsed và mức sử dụng bộ nhớ.

### Bài 9 — FORALL

Thay DML trong vòng lặp bằng FORALL. Kiểm tra SQL%BULK_ROWCOUNT và SAVE EXCEPTIONS khi một số input không hợp lệ.

### Bài 10 — PRAGMA UDF

Tạo function được gọi từ SQL trên tập nhiều hàng. So sánh với PRAGMA UDF và biểu thức SQL tương đương nếu có. Kiểm tra kết quả và số lần gọi.

### Bài 11 — Bind variables

So sánh dynamic SQL ghép literal với dynamic SQL dùng bind. Theo dõi parse calls và executions.

### Bài 12 — Thí nghiệm một thay đổi

Chọn một hotspot đã được profiler xác nhận. Thay đúng một yếu tố, chạy regression test, đo lại và ghi kết luận. Nêu rõ vì sao chấp nhận hoặc từ chối thay đổi.

## 30. Checklist trước khi triển khai tối ưu

**Đo lường**

- Có baseline và workload đại diện?
- Có nhiều lần chạy và thống kê median/p95?
- Đã tách elapsed, CPU và wait time?
- Đã xác định SQL nào tốn thời gian?
- Đã dùng profiler đúng mục đích và tắt profiler khi benchmark cuối?

**Compiler**

- PLSQL_CODE_TYPE hiện tại của object là gì?
- Object đã được recompile dưới setting mới?
- PLSQL_OPTIMIZE_LEVEL có được ghi nhận?
- Warnings đã được xem xét?
- Có thay đổi setting toàn hệ thống không cần thiết?

**Thuật toán và SQL**

- Có thể thay row-by-row bằng set-based SQL?
- Có thể giảm context switch bằng BULK COLLECT/FORALL?
- Batch size có kiểm soát bộ nhớ?
- Có SQL lặp lại hoặc parse lặp?
- Có function PL/SQL được gọi nhiều lần từ SQL?

**Tính đúng đắn**

- Kết quả nghiệp vụ có giống baseline?
- Exception/error code có giữ hợp đồng?
- Transaction và commit/rollback không thay đổi?
- Side effect không bị mất hoặc lặp?
- Regression test chạy trên input nhỏ, trung bình và lớn?

**Triển khai**

- Object VALID sau compile?
- Có kế hoạch rollback/recompile về setting cũ?
- Có theo dõi CPU, waits và lỗi sau triển khai?
- Có ghi lại setting và kết quả benchmark?

## 31. Ghi nhớ

| Chủ đề | Điều cần nhớ |
|---|---|
| Measurement first | Đo và tìm bottleneck trước khi sửa |
| PL/SQL engine | Xử lý control flow, biến và logic thủ tục |
| SQL engine | Thực thi câu SQL và access path |
| DBMS_PROFILER | Phân tích thời gian theo dòng PL/SQL |
| DBMS_HPROF | Phân tích thời gian theo cây lời gọi |
| SQL Trace/TKPROF | Phân tích parse, execute, fetch và waits |
| PLSQL_CODE_TYPE | INTERPRETED hoặc NATIVE |
| Native compilation | Có thể giảm overhead PL/SQL CPU-bound; không tối ưu SQL tự động |
| PLSQL_OPTIMIZE_LEVEL | Điều khiển mức tối ưu compiler; level 2 là mặc định phổ biến |
| PLSQL_WARNINGS | Phát hiện vấn đề ở compile time |
| PRAGMA INLINE | Yêu cầu compiler inline lời gọi phù hợp |
| PRAGMA UDF | Gợi ý function chủ yếu được gọi từ SQL |
| RESULT_CACHE | Tái sử dụng kết quả khi semantics và dependency cho phép |
| Set-based SQL | Thường là lựa chọn đầu tiên cho xử lý tập dữ liệu |
| BULK COLLECT | Lấy nhiều hàng mỗi lần |
| FORALL | Gửi DML theo collection, giảm context switch |
| Bind variables | Giúp tái sử dụng cursor và tránh ghép dữ liệu vào SQL |
| Regression test | Tối ưu phải giữ kết quả và hợp đồng |

Native compilation là một công cụ tối ưu có mục tiêu, không phải công tắc tăng tốc cho toàn bộ database. Hãy dùng profiler để tìm phần PL/SQL thực sự tốn CPU, dùng SQL trace và actual plan để tìm chi phí SQL, rồi chọn kỹ thuật phù hợp. Set-based SQL và bulk processing thường tạo khác biệt lớn khi code đang xử lý từng hàng; native compilation chỉ nên được cân nhắc sau khi đã đo và xác nhận overhead PL/SQL còn đáng kể. Mỗi thay đổi cần có baseline, benchmark lặp lại và regression test trước khi triển khai.
