# DBMS_PROFILER, DBMS_HPROF và truy tìm đoạn mã tốn thời gian

Khi một procedure hoặc package PL/SQL chạy chậm, chỉ đo tổng thời gian của lời gọi thường chưa đủ để tìm nguyên nhân. Thời gian có thể nằm trong một vòng lặp, một hàm được gọi hàng nghìn lần, một nhánh ít được chú ý hoặc một câu SQL nằm giữa luồng PL/SQL.

Oracle cung cấp hai công cụ profiling quan trọng:

- **DBMS_PROFILER:** đo số lần thực thi và thời gian tại từng dòng PL/SQL có mã được sinh. Kết quả được lưu trong các bảng profiler để truy vấn và tìm dòng nóng.
- **DBMS_HPROF:** hierarchical profiler, ghi nhận cây lời gọi subprogram. Công cụ phân biệt thời gian của chính subprogram với thời gian của toàn bộ cây con, đồng thời tách phần thực thi SQL và PL/SQL.

Hai công cụ bổ trợ cho nhau. DBMS_PROFILER giúp tìm dòng mã tốn thời gian; DBMS_HPROF giúp hiểu ai gọi subprogram, gọi bao nhiêu lần, thời gian nằm trong chính nó hay trong các hàm con, và phần nào thuộc SQL. Khi đã tìm thấy SQL chậm, cần tiếp tục xem execution plan hoặc SQL trace để điều tra ở tầng SQL.

## 1. Profiling là gì?

Profiling là quá trình thu thập số liệu trong khi chương trình chạy để xác định nơi tiêu tốn thời gian hoặc tài nguyên. Với PL/SQL, profiling có thể trả lời:

- Procedure nào chiếm phần lớn thời gian?
- Function nào được gọi quá nhiều lần?
- Dòng PL/SQL nào có tổng thời gian thực thi cao?
- Một subprogram tốn thời gian vì xử lý nội bộ hay vì gọi các subprogram khác?
- SQL được gọi từ PL/SQL chiếm bao nhiêu thời gian?
- Một thay đổi mã nguồn có làm giảm thời gian ở đúng đoạn cần tối ưu không?

Profiling khác với benchmark:

| Hoạt động | Mục đích |
|---|---|
| Benchmark | Đo tổng thời gian và throughput của một workload |
| Profiling | Phân rã workload thành các phần để tìm bottleneck |
| Tracing | Ghi lại trình tự sự kiện hoặc lời gọi để hiểu luồng thực thi |
| Code coverage | Xác định đoạn mã nào đã được thực thi trong tập kiểm thử |

Một lần profiling không thay thế benchmark. Profiler có overhead, vì vậy kết quả cần được đối chiếu với phép đo không bật profiler.

## 2. Chọn công cụ phù hợp

Oracle có nhiều công cụ liên quan đến hiệu năng PL/SQL. Không nên dùng một công cụ cho mọi câu hỏi.

| Công cụ | Mức quan sát | Trả lời câu hỏi |
|---|---|---|
| DBMS_PROFILER | Dòng PL/SQL | Dòng nào chạy nhiều hoặc tốn thời gian? |
| DBMS_HPROF | Cây gọi subprogram và SQL | Ai gọi hàm chậm, thời gian self/subtree và SQL/PLSQL ra sao? |
| DBMS_TRACE | Trình tự lời gọi/sự kiện PL/SQL | Subprogram nào được gọi theo thứ tự nào? |
| SQL Trace / TKPROF | Câu SQL | SQL nào parse, execute, fetch nhiều hoặc đọc nhiều block? |
| DBMS_XPLAN | Execution plan | Optimizer chọn access path và join method nào? |
| DBMS_APPLICATION_INFO | Module/action của session | Công việc nào của ứng dụng đang chạy trong session? |

### 2.1 DBMS_PROFILER

DBMS_PROFILER thu thập số lần một dòng được thực thi, tổng thời gian, thời gian nhỏ nhất và lớn nhất. Dữ liệu được ghi vào các bảng như:

- PLSQL_PROFILER_RUNS
- PLSQL_PROFILER_UNITS
- PLSQL_PROFILER_DATA

Đây là profiler dạng flat (không có cây gọi đầy đủ). Nó phù hợp để tìm các dòng nóng trong một unit đã biết.

### 2.2 DBMS_HPROF

DBMS_HPROF tổ chức kết quả theo cây gọi. Với mỗi subprogram, có thể xem:

- Số lần gọi.
- Function time hoặc self time: thời gian ở chính subprogram, không tính thời gian các subprogram con.
- Subtree time: thời gian của subprogram cộng thời gian của các subprogram con.
- Quan hệ parent-child: subprogram nào gọi subprogram nào.
- SQL statement được thực thi từ PL/SQL và thời gian SQL tương ứng.

Đây thường là lựa chọn tốt khi chưa biết bottleneck nằm ở procedure nào trong một call chain dài.

### 2.3 DBMS_TRACE

DBMS_TRACE ghi nhận trình tự thực thi các subprogram theo mức tracing được chọn. Nó hữu ích khi cần hiểu luồng gọi, nhưng không thay thế profiler thời gian. Một trace có thể rất lớn nếu bật ở phạm vi rộng.

### 2.4 SQL Trace và DBMS_XPLAN

Nếu HPROF cho thấy SQL statement chiếm nhiều thời gian, cần điều tra SQL ở tầng riêng:

- Dùng SQL_ID để tìm câu SQL trong shared SQL area.
- Dùng DBMS_XPLAN.DISPLAY_CURSOR để xem plan và runtime statistics.
- Dùng SQL Trace/TKPROF khi cần phân tích parse, execute, fetch, waits và I/O.

Không kết luận rằng PL/SQL chậm chỉ vì dòng chứa SELECT xuất hiện trong báo cáo DBMS_PROFILER. Một câu SQL có thể là một thao tác đơn lẻ ở mức dòng PL/SQL nhưng bên trong SQL engine có nhiều bước xử lý.

## 3. Quy trình profiling có thể lặp lại

Một quy trình thực tế nên được thực hiện theo vòng lặp:

~~~text
Xác định workload chậm
        |
        v
Ghi baseline không profiler
        |
        v
Warm-up package và dữ liệu
        |
        v
Bật profiler cho đúng session/workload
        |
        v
Chạy input đại diện
        |
        v
Dừng profiler và lưu kết quả
        |
        v
Đọc dòng nóng / call tree / SQL time
        |
        v
Chọn một bottleneck có bằng chứng
        |
        v
Thay đổi một điểm và chạy lại benchmark
        |
        v
So sánh baseline, profile và kết quả mới
~~~

### 3.1 Xác định workload đại diện

Trước khi bật profiler, xác định:

- Procedure hoặc transaction cần phân tích.
- Input có kích thước và phân bố gần với production.
- Số lần lặp hoặc số dòng xử lý.
- Các nhánh nghiệp vụ cần được chạy.
- Trạng thái cache và dữ liệu ban đầu.
- Phiên bản package và thời điểm thu thập.

Nếu test chỉ chạy một nhánh nhỏ, profiler không thể chỉ ra chi phí của các nhánh chưa được thực thi.

### 3.2 Warm-up trước khi đo

Lần đầu gọi một package có thể bao gồm chi phí load PL/SQL bytecode, khởi tạo package, đọc metadata hoặc làm nóng buffer cache. Oracle khuyến nghị chạy workload một lần không bật profiler trước khi thu thập để tránh gộp chi phí khởi động vào kết quả.

Warm-up không có nghĩa xóa cache tùy tiện. Mục tiêu là đo cùng trạng thái hệ thống mà workload thực tế thường gặp. Ghi lại rõ benchmark đo cold-start hay steady-state.

### 3.3 Giữ điều kiện đo ổn định

Khi so sánh hai lần chạy:

- Dùng cùng input và số dòng.
- Dùng cùng phiên bản dữ liệu và package.
- Hạn chế workload không liên quan trong lúc đo.
- Chạy nhiều lần nếu workload có biến động.
- Ghi lại thời gian tổng, CPU, logical reads và physical reads nếu có.
- Không thay đổi nhiều yếu tố cùng lúc.

### 3.4 Chỉ profile phạm vi cần thiết

Bật profiler cho đúng session và trong khoảng thời gian ngắn cần thiết. Profile toàn bộ ứng dụng hoặc session dài có thể tạo lượng dữ liệu lớn và làm tăng overhead.

## 4. DBMS_PROFILER: cách hoạt động

DBMS_PROFILER thu thập dữ liệu ở mức PL/SQL virtual machine. Dữ liệu có thể cho biết:

- Dòng nào được thực thi.
- Dòng đó được thực thi bao nhiêu lần.
- Tổng thời gian được ghi nhận cho dòng.
- Thời gian nhỏ nhất và lớn nhất của một lần thực thi dòng.

Các giá trị thời gian trong PLSQL_PROFILER_DATA và RUN_TOTAL_TIME được lưu theo nanosecond. Đây là số đo profiler, không phải cam kết rằng đồng hồ có độ phân giải thực tế đến từng nanosecond.

### 4.1 Cài đặt bảng lưu profiler

DBMS_PROFILER ghi kết quả vào các bảng profiler trong schema. Script Oracle cung cấp thường nằm tại:

~~~sql
@?/rdbms/admin/proftab.sql
~~~

Script này tạo các bảng và cấu trúc cần thiết để lưu run, unit và line statistics. **Lưu ý:** PROFTAB.SQL có thể DROP các bảng profiler đã tồn tại trước khi tạo lại. Chỉ chạy trong schema profiler mới hoặc sau khi đã sao lưu và xác nhận dữ liệu cũ có thể xóa. Không chạy script này như một bước cài đặt vô hại trên schema đã có kết quả cần giữ.

Từ Oracle Database 10g trở đi, package DBMS_PROFILER được cài tự động khi tạo database; PROFLOAD.SQL không còn cần thiết trong các phiên bản đó. Việc tạo các bảng lưu kết quả vẫn là bước riêng.

### 4.2 Quyền cần thiết

Người chạy profiler cần:

- EXECUTE trên DBMS_PROFILER.
- Quyền cần thiết để ghi vào các bảng profiler và sequence tương ứng.
- Quyền CREATE trên các PL/SQL unit được profile theo mô hình bảo mật của DBMS_PROFILER.

Quyền EXECUTE ONLY trên unit không đủ để profile unit đó. Nếu package thuộc schema khác, cần DBA thiết kế quyền phù hợp thay vì cấp quyền rộng tùy tiện.

### 4.3 Biên dịch unit ở chế độ DEBUG

Oracle khuyến nghị compile các unit cần profile với DEBUG để profiler có thêm thông tin. Ví dụ:

~~~sql
ALTER PACKAGE profile_demo COMPILE DEBUG BODY;
~~~

DBMS_PROFILER không yêu cầu mọi unit phải được compile DEBUG mới có thể chạy, nhưng compile DEBUG có thể cung cấp thông tin hữu ích hơn. Unit được compile ở NATIVE mode sẽ không tạo output profiler theo quy tắc bảo mật/khả năng của DBMS_PROFILER; trong trường hợp đó cần kiểm tra compilation mode trước khi kết luận profiler không hoạt động.

## 5. Thu thập dữ liệu với DBMS_PROFILER

### 5.1 Bắt đầu một run

START_PROFILER bắt đầu thu thập trong session hiện tại. Có overload trả về run number qua OUT parameter:

~~~sql
DECLARE
    l_run_id PLS_INTEGER;
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.START_PROFILER(
        run_comment  => 'profile_demo baseline input=10000',
        run_comment1 => 'Build 1.0, test scenario A',
        run_number   => l_run_id
    );

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Cannot start DBMS_PROFILER. Status=' || l_status
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE('Profiler run id=' || l_run_id);
END;
/
~~~

Giá trị trả về bằng 0 nghĩa là thành công; giá trị khác 0 là trạng thái lỗi. Có thể lưu run ID để truy vấn dữ liệu sau đó.

### 5.2 Chạy chương trình cần đo

Sau khi START_PROFILER thành công, chạy procedure hoặc workload mục tiêu trong cùng session:

~~~sql
BEGIN
    profile_demo.run_workload(10000);
END;
/
~~~

Profiler thu thập các unit được thực thi trong session theo phạm vi quyền của người dùng.

### 5.3 Dừng profiler và flush dữ liệu

~~~sql
DECLARE
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.STOP_PROFILER;

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Cannot stop DBMS_PROFILER. Status=' || l_status
        );
    END IF;
END;
/
~~~

STOP_PROFILER kết thúc run và flush dữ liệu đã thu thập vào các bảng profiler. Dữ liệu đang nằm trong cấu trúc bộ nhớ của session không tự động được lưu chỉ vì session disconnect; cần gọi STOP_PROFILER hoặc FLUSH_DATA.

### 5.4 FLUSH_DATA, PAUSE_PROFILER và RESUME_PROFILER

- FLUSH_DATA ghi dữ liệu profiler đã thu thập đến thời điểm gọi vào bảng, đồng thời giải phóng một phần cấu trúc dữ liệu trong bộ nhớ.
- PAUSE_PROFILER tạm dừng thu thập.
- RESUME_PROFILER tiếp tục thu thập.

Ví dụ:

~~~sql
DECLARE
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.PAUSE_PROFILER;
    -- Thực hiện phần công việc không muốn tính vào profile.
    l_status := DBMS_PROFILER.RESUME_PROFILER;
END;
/
~~~

Kiểm tra status của các function trước khi tiếp tục. Nếu cần xử lý lỗi, không bỏ qua trạng thái lỗi khi flush hoặc stop vì dữ liệu profiler có thể chưa được lưu đầy đủ.

## 6. Đọc dữ liệu DBMS_PROFILER

### 6.1 Ba bảng chính

| Bảng | Nội dung |
|---|---|
| PLSQL_PROFILER_RUNS | Một dòng cho mỗi run: run ID, owner, thời gian bắt đầu, comment, tổng thời gian |
| PLSQL_PROFILER_UNITS | Các PL/SQL library unit được profile trong run |
| PLSQL_PROFILER_DATA | Số lần thực thi và timing theo từng dòng trong từng unit |

Các cột quan trọng:

| Bảng/cột | Ý nghĩa |
|---|---|
| RUNS.RUNID | Mã run |
| RUNS.RUN_OWNER | Người chạy profiler |
| RUNS.RUN_DATE | Thời điểm bắt đầu |
| RUNS.RUN_COMMENT | Mô tả benchmark |
| RUNS.RUN_TOTAL_TIME | Tổng elapsed time của run, nanosecond |
| UNITS.UNIT_NUMBER | Mã unit trong run |
| UNITS.UNIT_OWNER / UNIT_NAME / UNIT_TYPE | Chủ sở hữu, tên và loại unit |
| DATA.LINE# | Số dòng trong source unit |
| DATA.TOTAL_OCCUR | Số lần dòng được thực thi |
| DATA.TOTAL_TIME | Tổng thời gian ghi nhận tại dòng, nanosecond |
| DATA.MIN_TIME / MAX_TIME | Thời gian nhỏ nhất/lớn nhất của một lần thực thi dòng |

PLSQL_PROFILER_UNITS.TOTAL_TIME được cung cấp cho công cụ phân tích, nhưng profiler không tự đặt giá trị cột này. Khi cần tổng hợp theo unit, hãy tính từ PLSQL_PROFILER_DATA.

### 6.2 Xem các run gần đây

~~~sql
SELECT runid,
       run_owner,
       run_date,
       run_comment,
       run_total_time / 1000000 AS total_elapsed_ms
FROM plsql_profiler_runs
ORDER BY runid DESC;
~~~

Chia nanosecond cho 1.000.000 để biểu diễn millisecond. Giữ nguyên run ID khi so sánh nhiều phiên bản.

### 6.3 Tìm dòng có tổng thời gian cao nhất

~~~sql
SELECT u.unit_owner,
       u.unit_name,
       u.unit_type,
       d.line# AS line_no,
       d.total_occur,
       ROUND(d.total_time / 1000000, 3) AS total_ms,
       ROUND(d.min_time / 1000000, 3) AS min_ms,
       ROUND(d.max_time / 1000000, 3) AS max_ms
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
WHERE d.runid = :p_run_id
ORDER BY d.total_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Đây là điểm bắt đầu để tìm dòng nóng. Dòng có tổng thời gian cao có thể do mỗi lần chạy chậm hoặc do được chạy quá nhiều lần. So sánh TOTAL_TIME với TOTAL_OCCUR và MAX_TIME.

### 6.4 Tổng hợp theo unit

~~~sql
SELECT u.unit_owner,
       u.unit_name,
       u.unit_type,
       SUM(d.total_occur) AS line_occurrences,
       ROUND(SUM(d.total_time) / 1000000, 3) AS total_ms
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
WHERE d.runid = :p_run_id
GROUP BY u.unit_owner, u.unit_name, u.unit_type
ORDER BY SUM(d.total_time) DESC;
~~~

Tổng theo unit giúp thu hẹp phạm vi trước khi đọc từng dòng. Một unit được gọi nhiều lần có thể đứng đầu dù từng lần thực thi không quá chậm.

### 6.5 Ghép line statistics với source code

Nếu người dùng có quyền đọc source qua ALL_SOURCE:

~~~sql
SELECT u.unit_owner,
       u.unit_name,
       u.unit_type,
       s.line,
       s.text,
       d.total_occur,
       ROUND(d.total_time / 1000000, 3) AS total_ms
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
JOIN all_source s
  ON s.owner = u.unit_owner
 AND s.name = u.unit_name
 AND s.type = u.unit_type
 AND s.line = d.line#
WHERE d.runid = :p_run_id
ORDER BY d.total_time DESC;
~~~

Nếu source đã thay đổi sau lần profile, line number có thể không còn khớp với source hiện tại. Nên ghi lại timestamp/version của unit và chỉ phân tích source tương ứng với run.

### 6.6 Diễn giải TOTAL_OCCUR và TOTAL_TIME

Ví dụ:

| Dòng | TOTAL_OCCUR | TOTAL_TIME | Cách đọc |
|---:|---:|---:|---|
| 20 | 1 | 500 ms | Một lần chạy rất tốn thời gian |
| 35 | 100.000 | 300 ms | Mỗi lần nhỏ nhưng số lần gọi lớn |
| 50 | 10 | 250 ms | Có thể là thao tác nặng trong một số nhánh |

Đừng chỉ sắp xếp theo tổng thời gian. Một dòng có MAX_TIME lớn nhưng TOTAL_OCCUR nhỏ có thể là outlier; một dòng có TOTAL_OCCUR cực lớn có thể là cơ hội tối ưu bằng cách giảm số lần gọi hoặc batch hóa.

## 7. Những giới hạn khi đọc DBMS_PROFILER

### 7.1 Một câu SQL nhiều dòng có thể chỉ được ghi nhận tại một dòng

PL/SQL chuyển câu SQL đã xử lý sang SQL engine như một thao tác. Vì vậy câu SQL nhiều dòng có thể được quy về một dòng trong profiler, thường là dòng đầu. Không phải mọi dòng trong đoạn SQL đều có một record riêng.

### 7.2 Nhiều statement trên cùng một dòng bị gộp

Nếu viết nhiều câu lệnh trên cùng một dòng source, profiler có thể gộp occurrence và time. Khi có IF/ELSE cùng dòng, báo cáo khó cho biết nhánh nào đã chạy. Nên đặt mỗi statement trên một dòng riêng khi muốn phân tích chi tiết.

### 7.3 Không có record không luôn có nghĩa dòng chưa chạy

PLSQL_PROFILER_DATA ghi các dòng có mã được sinh. Nếu không có record cho một dòng, có thể không có mã được sinh cho dòng đó. Nếu có record với TOTAL_OCCUR = 0, không có mã gắn với dòng đó được thực thi trong run. Cần đọc cả source và metadata, không suy luận coverage chỉ từ việc thiếu dòng dữ liệu.

### 7.4 Tối ưu hóa compiler ảnh hưởng mapping

Compiler có thể tối ưu hoặc gộp mã. Đối với mục đích coverage, Oracle lưu ý PLSQL_OPTIMIZE_LEVEL=1 để dễ diễn giải dữ liệu coverage; điều này không đồng nghĩa phải hạ optimize level trong production chỉ để profiling hiệu năng. Nếu thay compile settings, phải ghi nhận cấu hình và đo riêng vì nó có thể thay đổi hiệu năng.

### 7.5 DBMS_PROFILER không phải SQL profiler

DBMS_PROFILER cho biết dòng PL/SQL chứa SQL có thời gian đáng chú ý, nhưng không cung cấp phân tích đầy đủ các operation bên trong SQL engine. Dùng DBMS_HPROF để xem SQL và PL/SQL time tách biệt; sau đó dùng SQL_ID, DBMS_XPLAN hoặc SQL Trace khi cần.

## 8. DBMS_HPROF: hierarchical profiler

DBMS_HPROF thu thập call events và return events để xây dựng cây gọi. Kết quả cho biết không chỉ subprogram nào tốn thời gian mà còn subprogram đó được gọi từ đâu.

### 8.1 Self time và subtree time

Hai chỉ số quan trọng:

- **Function elapsed time (self time):** thời gian thực thi bên trong subprogram, không tính thời gian của các subprogram con.
- **Subtree elapsed time:** thời gian của subprogram cộng thời gian của toàn bộ subprogram con được gọi bên dưới.

Ví dụ:

~~~text
process_order                         subtree = 900 ms
  validate_order                      subtree = 100 ms
  calculate_price                     subtree = 600 ms
    load_price_rules                  subtree = 450 ms
      SQL statement                   subtree = 400 ms
  write_audit                         subtree = 150 ms
~~~

Nếu calculate_price có subtree 600 ms nhưng self time chỉ 150 ms, phần lớn thời gian nằm trong các hàm con. Tối ưu riêng calculate_price mà không xem load_price_rules có thể không giải quyết được bottleneck.

### 8.2 HPROF phân biệt SQL và PL/SQL

Hierarchical profiler có hai namespace chính:

- PLSQL: lời gọi subprogram, trigger, anonymous block, package initialization...
- SQL: câu SQL được thực thi từ PL/SQL, bao gồm static SQL, dynamic SQL và SQL fetch.

Vì vậy HPROF giúp nhận ra thời gian bị tiêu tốn trong SQL engine so với phần xử lý PL/SQL. SQL statement có thể được biểu diễn bằng các tên đặc biệt như static SQL tại dòng N, dynamic SQL tại dòng N hoặc fetch tại dòng N.

### 8.3 HPROF không đo từng dòng PL/SQL

HPROF dùng line number để chỉ vị trí khai báo subprogram trong source và phân biệt overload. Nó không đo thời gian của từng dòng như DBMS_PROFILER. Nếu cần tìm dòng cụ thể trong một function đã xác định, dùng DBMS_PROFILER bổ sung.

### 8.4 Không cần chuẩn bị source hoặc compile đặc biệt

Theo tài liệu Oracle, HPROF không yêu cầu chuẩn bị source hoặc compile-time đặc biệt để thu thập call profile. Điều này hữu ích khi muốn khảo sát một call graph mà không thay đổi mã nguồn.

## 9. Cài đặt và quyền cho DBMS_HPROF

DBMS_HPROF có hai cách lưu raw profiler data tùy phiên bản và API:

1. Lưu raw trace ra file trong directory object, sau đó phân tích file.
2. Lưu raw trace vào bảng profiler, sau đó phân tích theo trace ID.

### 9.1 Bảng HPROF trong các phiên bản mới

Trong các phiên bản hỗ trợ CREATE_TABLES, có thể tạo bảng profiler trong schema:

~~~sql
BEGIN
    DBMS_HPROF.CREATE_TABLES(force_it => FALSE);
END;
/
~~~

Các bảng phân tích chính gồm:

- DBMSHP_RUNS
- DBMSHP_FUNCTION_INFO
- DBMSHP_PARENT_CHILD_INFO

Ở chế độ lưu raw trace trong bảng, Oracle còn quản lý raw profiler data table và cấu trúc liên quan.

Không đặt FORCE_IT = TRUE trên schema đã có dữ liệu cần giữ: tùy chọn này có thể drop và tạo lại các bảng profiler hiện có.

### 9.2 Script DBMSHPTAB.SQL và khác biệt phiên bản

Trong các phiên bản cũ, Oracle hướng dẫn chạy:

~~~sql
@?/rdbms/admin/dbmshptab.sql
~~~

Script DBMSHPTAB.SQL đã bị deprecated từ Oracle Database 18c. Với phiên bản có DBMS_HPROF.CREATE_TABLES, ưu tiên API này theo tài liệu đúng phiên bản. Script cũ cũng có thể drop các bảng profiler đã tồn tại, nên phải kiểm tra trước khi chạy.

### 9.3 Quyền cần thiết

Để dùng DBMS_HPROF, cần EXECUTE trên package. Nếu dùng file mode:

- START_PROFILING cần WRITE trên directory object.
- ANALYZE file cần READ trên directory object.
- Đường dẫn vật lý phải tồn tại trên database server và Oracle OS user phải có quyền phù hợp.

Ví dụ DBA tạo directory object và cấp quyền:

~~~sql
CREATE OR REPLACE DIRECTORY plshprof_dir
AS '/u01/app/oracle/plshprof';

GRANT READ, WRITE ON DIRECTORY plshprof_dir TO app_user;
~~~

Directory object chỉ là alias trong database; nó không tự tạo thư mục trên hệ điều hành. Tài khoản hệ điều hành chạy Oracle phải có quyền đọc/ghi thư mục thực.

## 10. DBMS_HPROF với raw trace lưu trong bảng

Đây là cách thuận tiện ở các phiên bản có API table-based.

### 10.1 Bắt đầu profiling

~~~sql
DECLARE
    l_trace_id NUMBER;
BEGIN
    l_trace_id := DBMS_HPROF.START_PROFILING(
        run_comment => 'profile_demo hierarchical run A'
    );

    DBMS_OUTPUT.PUT_LINE('Trace id=' || l_trace_id);
END;
/
~~~

START_PROFILING trả về trace ID của dữ liệu raw. Đây là trace ID, chưa phải run ID của các bảng phân tích.

### 10.2 Chạy workload và dừng profiling

~~~sql
BEGIN
    profile_demo.run_workload(10000);
END;
/

BEGIN
    DBMS_HPROF.STOP_PROFILING;
END;
/
~~~

Nên dừng profiler ngay sau workload mục tiêu để trace không chứa các thao tác không liên quan.

### 10.3 Phân tích trace

~~~sql
DECLARE
    l_run_id NUMBER;
    l_trace_id NUMBER := :p_trace_id;
BEGIN
    l_run_id := DBMS_HPROF.ANALYZE(
        trace_id    => l_trace_id,
        run_comment => 'profile_demo analyzed run A'
    );

    DBMS_OUTPUT.PUT_LINE('Analyzed run id=' || l_run_id);
END;
/
~~~

ANALYZE đọc raw trace và ghi kết quả vào các bảng hierarchical profiler. Run ID được trả về để truy vấn DBMSHP_RUNS, DBMSHP_FUNCTION_INFO và DBMSHP_PARENT_CHILD_INFO.

### 10.4 Phân biệt trace ID và run ID

| ID | Ý nghĩa |
|---|---|
| Trace ID | Định danh raw profiler data vừa thu thập |
| Run ID | Định danh kết quả đã được ANALYZE lưu trong các bảng phân tích |

Không dùng nhầm hai loại ID khi truy vấn dữ liệu. Một trace ID được phân tích sẽ tạo một run ID tương ứng.

## 11. DBMS_HPROF với raw trace lưu trong file

File mode thường xuất hiện trong các ví dụ và phiên bản API cũ. Cách gọi cụ thể phụ thuộc phiên bản Oracle.

### 11.1 Bắt đầu ghi file

~~~sql
BEGIN
    DBMS_HPROF.START_PROFILING(
        location => 'PLSHPROF_DIR',
        filename => 'profile_run_a.trc'
    );
END;
/
~~~

### 11.2 Chạy chương trình và dừng

~~~sql
BEGIN
    profile_demo.run_workload(10000);
END;
/

BEGIN
    DBMS_HPROF.STOP_PROFILING;
END;
/
~~~

### 11.3 Phân tích file

~~~sql
DECLARE
    l_run_id NUMBER;
BEGIN
    l_run_id := DBMS_HPROF.ANALYZE(
        location    => 'PLSHPROF_DIR',
        filename    => 'profile_run_a.trc',
        run_comment => 'profile_demo file run A'
    );

    DBMS_OUTPUT.PUT_LINE('Run id=' || l_run_id);
END;
/
~~~

### 11.4 Phiên bản Oracle

API file-based với location/filename có trong tài liệu các phiên bản cũ. Các phiên bản mới bổ sung API table-based, START_PROFILING trả trace ID và ANALYZE nhận trace ID; DBMSHPTAB.SQL đã deprecated từ 18c. Trước khi sao chép block vào môi trường thật, kiểm tra package specification và tài liệu đúng phiên bản database đang chạy. Không trộn tham số của hai overload khác nhau trong cùng một ví dụ.

## 12. Đọc dữ liệu DBMS_HPROF

### 12.1 Các bảng phân tích

| Bảng | Nội dung |
|---|---|
| DBMSHP_RUNS | Thông tin tổng quát về run đã phân tích |
| DBMSHP_FUNCTION_INFO | Thông tin từng subprogram hoặc SQL operation trong run |
| DBMSHP_PARENT_CHILD_INFO | Thống kê quan hệ giữa caller và callee |

Các cột quan trọng trong DBMSHP_FUNCTION_INFO:

| Cột | Ý nghĩa |
|---|---|
| RUNID | Run đã phân tích |
| SYMBOLID | Định danh subprogram trong run |
| OWNER / MODULE / TYPE | Schema, module và loại unit |
| FUNCTION | Tên subprogram hoặc tên operation đặc biệt |
| LINE# | Dòng khai báo subprogram trong module |
| HASH | Hash chữ ký, giúp phân biệt overload |
| NAMESPACE | PLSQL hoặc SQL |
| CALLS | Số lần gọi |
| FUNCTION_ELAPSED_TIME | Self time, microsecond |
| SUBTREE_ELAPSED_TIME | Inclusive time, microsecond |
| SQL_ID / SQL_TEXT | Định danh và phần đầu SQL text khi là SQL operation |

DBMSHP_PARENT_CHILD_INFO lưu số lần gọi và timing của một child khi được gọi từ một parent cụ thể. Đây là dữ liệu cần thiết để xác định cùng một function có đắt ở mọi caller hay chỉ khi được gọi từ một nhánh nhất định.

### 12.2 Xem các run gần đây

~~~sql
SELECT runid,
       run_timestamp,
       run_comment,
       total_elapsed_time
FROM dbmshp_runs
ORDER BY runid DESC;
~~~

### 12.3 Tìm subprogram có subtree time cao

~~~sql
SELECT owner,
       module,
       type,
       function,
       line# AS definition_line,
       namespace,
       calls,
       ROUND(function_elapsed_time / 1000, 3) AS self_ms,
       ROUND(subtree_elapsed_time / 1000, 3) AS subtree_ms,
       sql_id,
       sql_text
FROM dbmshp_function_info
WHERE runid = :p_run_id
ORDER BY subtree_elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Các thời gian trong bảng HPROF là microsecond; chia 1.000 để biểu diễn millisecond. Nếu subtree lớn nhưng self nhỏ, xem các function con. Nếu self lớn, chính subprogram hoặc SQL operation đó cần được điều tra.

### 12.4 Xem các SQL operation

~~~sql
SELECT function,
       line#,
       calls,
       ROUND(function_elapsed_time / 1000, 3) AS sql_time_ms,
       sql_id,
       sql_text
FROM dbmshp_function_info
WHERE runid = :p_run_id
  AND namespace = 'SQL'
ORDER BY function_elapsed_time DESC;
~~~

Nếu có SQL_ID, có thể tiếp tục tra SQL text và execution plan. SQL_TEXT trong bảng HPROF chỉ lưu phần đầu câu SQL, không phải lúc nào cũng đủ để nhận diện toàn bộ câu lệnh.

### 12.5 Xem caller và callee

~~~sql
SELECT p.owner AS parent_owner,
       p.module AS parent_module,
       p.function AS parent_function,
       c.owner AS child_owner,
       c.module AS child_module,
       c.function AS child_function,
       pc.calls,
       ROUND(pc.function_elapsed_time / 1000, 3) AS child_self_ms,
       ROUND(pc.subtree_elapsed_time / 1000, 3) AS child_subtree_ms
FROM dbmshp_parent_child_info pc
JOIN dbmshp_function_info p
  ON p.runid = pc.runid
 AND p.symbolid = pc.parentsymid
JOIN dbmshp_function_info c
  ON c.runid = pc.runid
 AND c.symbolid = pc.childsymid
WHERE pc.runid = :p_run_id
ORDER BY pc.subtree_elapsed_time DESC;
~~~

Query này giúp phát hiện một child function chỉ chậm khi được gọi từ một parent cụ thể hoặc bị gọi quá nhiều lần từ một nhánh.

### 12.6 Phân biệt overloaded subprogram

Hai procedure/function cùng tên nhưng khác signature có thể xuất hiện thành các entry khác nhau. Dùng LINE# và HASH để phân biệt. Khi source thay đổi, line number có thể thay đổi; hash chữ ký thay đổi khi signature thay đổi. Không chỉ group theo FUNCTION nếu module có overload.

## 13. Diễn giải HPROF để tìm bottleneck

### 13.1 Subtree cao, self thấp

Ví dụ:

| Function | Calls | Self ms | Subtree ms |
|---|---:|---:|---:|
| process_invoice | 1 | 20 | 1.200 |
| load_tax_rules | 1 | 10 | 700 |
| execute_tax_query | 1 | 5 | 650 |

process_invoice không tự tiêu tốn 1.200 ms. Phần lớn thời gian nằm trong các function con, đặc biệt là SQL query phía dưới.

### 13.2 Self cao

Nếu một function có self time cao, kiểm tra:

- Vòng lặp và phép tính lặp lại.
- Chuyển đổi dữ liệu hoặc xử lý chuỗi.
- Tìm kiếm tuyến tính trên collection lớn.
- Gọi hàm lặp trong điều kiện.
- Thuật toán có độ phức tạp tăng nhanh theo kích thước input.

### 13.3 Calls cao nhưng mean time thấp

Một function có thể rất nhanh mỗi lần nhưng được gọi hàng trăm nghìn lần. Tính trung bình:

\[
\text{Mean self time} =
\frac{\text{Function elapsed time}}{\text{Calls}}
\]

Nếu function nhỏ bị gọi trong vòng lặp lớn, có thể giảm overhead bằng cách tính trước, truyền kết quả đã tính hoặc batch dữ liệu.

### 13.4 Một SQL statement chiếm phần lớn thời gian

Nếu HPROF cho thấy SQL namespace chiếm tỷ trọng cao:

1. Lấy SQL_ID.
2. Kiểm tra cursor và plan bằng DBMS_XPLAN.DISPLAY_CURSOR.
3. So sánh E-Rows với A-Rows.
4. Kiểm tra buffers, reads, waits và bind values.
5. Xem index, partition pruning, join method và thống kê.
6. Tối ưu SQL hoặc schema ở đúng tầng.

Đừng viết lại PL/SQL loop nếu thời gian chính nằm trong SQL engine.

## 14. Ví dụ package để thực hành profiling

Ví dụ tạo một package có nhiều tầng gọi. Mục tiêu là tạo workload dễ quan sát bằng cả DBMS_PROFILER và DBMS_HPROF.

### 14.1 Tạo package specification

~~~sql
CREATE OR REPLACE PACKAGE profile_demo AS
    PROCEDURE run_workload(p_iterations IN PLS_INTEGER);
END profile_demo;
/
~~~

### 14.2 Tạo package body

~~~sql
CREATE OR REPLACE PACKAGE BODY profile_demo AS
    FUNCTION normalize_value(p_value IN PLS_INTEGER)
        RETURN PLS_INTEGER
    IS
    BEGIN
        RETURN MOD(p_value * 17 + 13, 100003);
    END normalize_value;

    FUNCTION calculate_value(p_value IN PLS_INTEGER)
        RETURN NUMBER
    IS
        l_result NUMBER := 0;
        l_value  PLS_INTEGER;
    BEGIN
        FOR i IN 1 .. 20 LOOP
            l_value := normalize_value(p_value + i);
            l_result := l_result + SQRT(l_value + 1);
        END LOOP;

        RETURN l_result;
    END calculate_value;

    PROCEDURE run_workload(p_iterations IN PLS_INTEGER)
    IS
        l_total NUMBER := 0;
    BEGIN
        FOR i IN 1 .. p_iterations LOOP
            l_total := l_total + calculate_value(i);
        END LOOP;

        DBMS_OUTPUT.PUT_LINE('Total=' || l_total);
    END run_workload;
END profile_demo;
/
~~~

Package có ba tầng: run_workload gọi calculate_value; calculate_value gọi normalize_value nhiều lần. Đây là cấu trúc thích hợp để HPROF thể hiện call tree và DBMS_PROFILER cho biết các dòng vòng lặp có tổng thời gian cao.

### 14.3 Compile DEBUG nếu cần

~~~sql
ALTER PACKAGE profile_demo COMPILE DEBUG BODY;
~~~

### 14.4 Warm-up

~~~sql
BEGIN
    profile_demo.run_workload(1000);
END;
/
~~~

### 14.5 Chạy DBMS_PROFILER

Sau khi đã tạo bảng profiler bằng PROFTAB.SQL trong schema lab:

~~~sql
DECLARE
    l_run_id PLS_INTEGER;
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.START_PROFILER(
        run_comment => 'profile_demo line profile 1000',
        run_number  => l_run_id
    );

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Profiler start failed');
    END IF;

    profile_demo.run_workload(1000);

    l_status := DBMS_PROFILER.STOP_PROFILER;

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(-20011, 'Profiler stop failed');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Profiler run=' || l_run_id);
END;
/
~~~

Sau đó chạy query hottest lines ở phần 6.

### 14.6 Chạy DBMS_HPROF

Trong phiên bản hỗ trợ table-based API:

Tạo các bảng HPROF trước một lần bằng DBMS_HPROF.CREATE_TABLES(force_it => FALSE), nếu chúng chưa tồn tại. Block dưới đây giả định bước chuẩn bị đã hoàn tất; không gọi CREATE_TABLES cho mỗi run.

~~~sql
DECLARE
    l_trace_id NUMBER;
    l_run_id   NUMBER;
BEGIN
    l_trace_id := DBMS_HPROF.START_PROFILING(
        run_comment => 'profile_demo hierarchical 1000'
    );

    profile_demo.run_workload(1000);

    DBMS_HPROF.STOP_PROFILING;

    l_run_id := DBMS_HPROF.ANALYZE(
        trace_id    => l_trace_id,
        run_comment => 'profile_demo analyzed 1000'
    );

    DBMS_OUTPUT.PUT_LINE('Trace id=' || l_trace_id);
    DBMS_OUTPUT.PUT_LINE('Run id=' || l_run_id);
END;
/
~~~

Nếu các bảng HPROF đã tồn tại, CREATE_TABLES với FORCE_IT = FALSE có thể báo lỗi thay vì ghi đè. Tạo bảng một lần theo quy trình cài đặt của schema; không gọi CREATE_TABLES lặp lại như bước bắt buộc của mọi run.

Truy vấn DBMSHP_FUNCTION_INFO và DBMSHP_PARENT_CHILD_INFO để xem call tree, self time và subtree time.

## 15. So sánh kết quả trước và sau tối ưu

Profiling chỉ có ý nghĩa khi kết quả được dùng để kiểm chứng thay đổi.

### 15.1 Ghi baseline

Trước thay đổi, lưu:

- Tổng thời gian workload không bật profiler.
- Run ID của DBMS_PROFILER hoặc DBMS_HPROF.
- Input, số vòng lặp và số dòng dữ liệu.
- Phiên bản package và thời điểm compile.
- Thống kê chính về CPU, reads và elapsed time nếu có.

### 15.2 Tối ưu một bottleneck có bằng chứng

Ví dụ, HPROF cho thấy normalize_value được gọi 20 lần trong mỗi calculate_value. Có thể kiểm tra liệu kết quả có thể được tính một lần, cache trong phạm vi xử lý hay giảm số lần gọi.

Không tối ưu chỉ vì một function xuất hiện trong báo cáo. Cần xem tổng thời gian, số lần gọi, độ lớn input và tác động nghiệp vụ.

### 15.3 Chạy lại cùng workload

Sau thay đổi:

- Dùng cùng input.
- Warm-up lại.
- Chạy benchmark không profiler.
- Thu profile mới nếu cần xác nhận bottleneck đã chuyển.
- So sánh tổng thời gian, số lần gọi và phần thời gian liên quan.

Một tối ưu có thể làm function cũ nhanh hơn nhưng khiến function khác trở thành bottleneck. Vì vậy cần lặp lại chu trình.

### 15.4 Không so sánh run khác điều kiện

Hai run có cache state, dữ liệu, DOP hoặc tải hệ thống khác nhau không phải phép so sánh trực tiếp. Ghi lại các điều kiện và chạy nhiều lần nếu biến động lớn.

## 16. Overhead, độ chính xác và giới hạn

### 16.1 Profiler làm thay đổi thời gian chạy

Profiler thêm công việc ghi nhận sự kiện và timing. Do đó:

- Elapsed time khi bật profiler có thể cao hơn bình thường.
- Dùng profiler để xác định tỷ trọng và vị trí tương đối, sau đó benchmark lại khi tắt profiler.
- Không coi timing profiler là SLA production.

### 16.2 Timer resolution và workload quá ngắn

Một dòng chỉ chạy vài microsecond có thể khó được xếp hạng ổn định nếu workload quá ngắn hoặc profiler overhead lớn. Tăng số vòng lặp để tạo mẫu đủ dài, nhưng giữ input có tính đại diện.

### 16.3 Warm-up và package initialization

Lần gọi đầu có thể bao gồm package initialization và load metadata. Nếu mục tiêu là steady-state performance, warm-up trước khi bật profiler. Nếu mục tiêu là cold-start, phải đo và ghi rõ cold-start như một workload riêng.

### 16.4 Inlining và tối ưu hóa compiler

HPROF có thể không báo một subprogram đã bị compiler inline hoặc một deterministic function bị tối ưu loại bỏ. Điều này không có nghĩa source không có lời gọi; có thể lời gọi đã biến mất trong mã thực thi.

### 16.5 Source có thể đã thay đổi sau profile

Line number chỉ có ý nghĩa khi đối chiếu đúng source version. Nếu compile lại package hoặc deploy source mới, hãy ghi timestamp/version và không gắn số liệu cũ vào line number mới.

### 16.6 Profiling không thay thế giám sát production

Profiler thường phù hợp với benchmark có kiểm soát hoặc một session được chọn. Để quan sát ứng dụng production theo thời gian, cần kết hợp module/action instrumentation, SQL monitoring, tracing và công cụ giám sát phù hợp với chính sách hệ thống.

## 17. Kết hợp DBMS_APPLICATION_INFO và SQL tracing

DBMS_APPLICATION_INFO cho phép đặt MODULE và ACTION của session để nhận diện công việc đang chạy:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CONFIRM_ORDER'
    );

    profile_demo.run_workload(1000);

    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => NULL,
        action_name => NULL
    );
END;
/
~~~

Module/action giúp DBA hoặc công cụ tracing phân biệt hoạt động của ứng dụng. Nó không tự đo từng dòng PL/SQL như DBMS_PROFILER.

Nếu cần xem SQL chi tiết, có thể bật SQL Trace trong phạm vi session được kiểm soát và dùng TKPROF phân tích kết quả. SQL Trace cung cấp parse/execute/fetch và wait information; DBMS_HPROF cho biết SQL operation xuất hiện ở đâu trong call tree. Hai góc nhìn này bổ sung cho nhau.

## 18. Chọn DBMS_PROFILER hay DBMS_HPROF?

| Tình huống | Công cụ nên bắt đầu |
|---|---|
| Đã biết package, muốn tìm dòng nóng | DBMS_PROFILER |
| Chưa biết procedure nào trong call chain chậm | DBMS_HPROF |
| Muốn biết một hàm bị gọi bởi những caller nào | DBMS_HPROF |
| Muốn tách SQL time và PL/SQL time | DBMS_HPROF |
| Muốn biết số lần thực thi của từng dòng | DBMS_PROFILER |
| Muốn xem câu SQL chậm và execution plan | SQL Trace / DBMS_XPLAN, có thể dùng SQL_ID từ HPROF |
| Muốn biết trình tự gọi subprogram | DBMS_TRACE hoặc HPROF |
| Muốn kiểm tra code path đã chạy | DBMS_PROFILER hoặc công cụ code coverage chuyên dụng |

Một workflow hiệu quả có thể dùng HPROF trước để tìm nhánh hoặc subprogram đáng chú ý, sau đó dùng DBMS_PROFILER trong unit đó để xác định dòng nóng.

## 19. Lỗi thường gặp khi profiling

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không có dữ liệu DBMS_PROFILER | Chưa tạo bảng, thiếu quyền hoặc unit compile NATIVE | Kiểm tra PROFTAB, quyền và compilation mode |
| Run không được lưu sau disconnect | Chưa STOP_PROFILER hoặc FLUSH_DATA | Dừng hoặc flush tường minh |
| Chạy PROFTAB.SQL làm mất dữ liệu cũ | Script tạo bảng có thể DROP bảng profiler hiện tại | Backup và chạy trong schema phù hợp |
| Kết quả lần đầu quá chậm | Đã tính cả package load/init và cache warm-up | Warm-up trước khi profile steady state |
| HPROF không có dòng source cụ thể | HPROF là hierarchical, không phải line profiler | Dùng DBMS_PROFILER |
| Chỉ xem subtree time rồi tối ưu sai hàm | Thời gian có thể nằm ở child subprogram | So sánh self time và parent-child |
| SQL chậm bị hiểu thành PL/SQL chậm | DBMS_PROFILER không phân rã SQL engine | Dùng HPROF, SQL_ID, SQL Trace và plan |
| Dùng nhầm HPROF trace ID với run ID | Một ID cho raw data, một ID cho kết quả analyze | Lưu riêng cả hai |
| File HPROF không được tạo | Thiếu WRITE hoặc OS path không hợp lệ | Kiểm tra directory object và OS permission |
| ANALYZE không đọc được file | Thiếu READ trên directory object | Cấp quyền READ đúng schema |
| CREATE_TABLES làm mất bảng HPROF | Dùng FORCE_IT = TRUE | Không force trên schema có dữ liệu |
| Không tìm được function overload | Chỉ group theo tên FUNCTION | Xem LINE# và HASH |
| Line number không khớp source | Package đã compile lại sau profile | Đối chiếu timestamp và source version |
| Kết quả giữa các run dao động | Input, cache hoặc tải nền khác nhau | Chuẩn hóa benchmark và lặp lại |

## 20. Checklist trước khi kết luận bottleneck

Trước khi sửa mã, hãy xác nhận:

1. Workload profile có đại diện cho tình huống chậm thực tế không?
2. Đã warm-up hoặc ghi rõ đang đo cold-start chưa?
3. Có chạy đúng session và đúng khoảng thời gian không?
4. DBMS_PROFILER đã STOP/FLUSH thành công chưa?
5. HPROF trace đã STOP và ANALYZE thành công chưa?
6. Đã lưu run ID, trace ID, source version và input chưa?
7. Có phân biệt tổng time với time trung bình mỗi lần gọi không?
8. Với HPROF, đã so self time và subtree time chưa?
9. Đã xem parent-child để biết ai gọi subprogram chậm chưa?
10. SQL namespace có chiếm phần lớn thời gian không?
11. Nếu SQL chậm, đã xem SQL_ID và execution plan chưa?
12. Source line có khớp với version đã profile không?
13. Kết quả có bị ảnh hưởng bởi compile mode, inlining hoặc warm-up không?
14. Đã benchmark lại khi tắt profiler chưa?
15. Sau tối ưu, bottleneck có chuyển sang nơi khác không?

## 21. Tổng kết

DBMS_PROFILER và DBMS_HPROF giúp truy tìm đoạn mã PL/SQL tốn thời gian từ hai góc nhìn:

- **DBMS_PROFILER** ghi số lần thực thi và timing theo dòng PL/SQL, lưu trong PLSQL_PROFILER_RUNS, PLSQL_PROFILER_UNITS và PLSQL_PROFILER_DATA. Dữ liệu timing được lưu theo nanosecond.
- **DBMS_HPROF** ghi call hierarchy, số lần gọi, self time và subtree time; đồng thời phân biệt SQL và PL/SQL execution time. Các bảng phân tích chính là DBMSHP_RUNS, DBMSHP_FUNCTION_INFO và DBMSHP_PARENT_CHILD_INFO.
- DBMS_PROFILER phù hợp để tìm dòng nóng; HPROF phù hợp để tìm bottleneck trong call tree và xác định SQL hay PL/SQL đang chiếm thời gian.
- HPROF có cả API file-based và table-based tùy phiên bản. CREATE_TABLES là cách tạo bảng ở phiên bản mới; DBMSHPTAB.SQL đã deprecated từ 18c.
- Profiler có overhead và phụ thuộc workload. Warm-up, input đại diện, điều kiện đo ổn định và benchmark không bật profiler là cần thiết để diễn giải kết quả.
- Khi HPROF chỉ ra SQL chậm, tiếp tục bằng SQL_ID, DBMS_XPLAN hoặc SQL Trace. Không tối ưu PL/SQL khi bottleneck nằm trong SQL engine.

Profiling hiệu quả không phải là tìm dòng có con số lớn nhất rồi sửa ngay. Hãy xác định đúng workload, đọc self/subtree hoặc line timing trong ngữ cảnh, lần theo caller và SQL liên quan, rồi xác nhận thay đổi bằng benchmark lặp lại.

## 22. Tài liệu Oracle tham khảo

- Oracle Database 26c PL/SQL Language Reference, “Profiling and Tracing PL/SQL Programs”: https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/profiling-and-tracing-pl-sql-programs.html
- Oracle Database 26c PL/SQL Packages and Types Reference, “DBMS_PROFILER”: https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/DBMS_PROFILER.html
- Oracle Database 26c Development Guide, “Using the PL/SQL Hierarchical Profiler”: https://docs.oracle.com/en/database/oracle/oracle-database/26/adfns/hierarchical-profiler.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_HPROF”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_HPROF.html
