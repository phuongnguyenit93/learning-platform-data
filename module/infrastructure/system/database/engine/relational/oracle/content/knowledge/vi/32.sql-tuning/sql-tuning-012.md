# SQL Plan Management, baseline và kiểm soát hồi quy kế hoạch

Một câu SQL có thể có nhiều execution plan hợp lệ. Khi statistics, dữ liệu, bind values, index, optimizer parameters hoặc phiên bản Oracle thay đổi, optimizer có thể chọn một plan khác. Plan mới đôi khi tốt hơn, nhưng cũng có thể chậm hơn đáng kể và làm ứng dụng bị hồi quy hiệu năng. **SQL Plan Management (SPM)** giúp kiểm soát thay đổi này bằng cách lưu giữ các plan đã được chấp nhận cho một SQL statement và hướng optimizer ưu tiên những plan đã biết là phù hợp.

Thành phần trung tâm của SPM là **SQL plan baseline**. Baseline không phải một execution plan được đóng băng tuyệt đối. Nó là tập hợp các plan đã được ghi nhận và chấp nhận cho một câu SQL. Optimizer có thể dùng plan trong baseline nếu plan đó còn được bật và có thể tái tạo trong môi trường hiện tại. Khi xuất hiện plan mới, SPM có thể giữ plan đó ở trạng thái chưa chấp nhận để kiểm tra/evolve trước khi đưa vào tập plan được phép sử dụng.

SPM hữu ích nhất khi được vận hành như một quy trình: xác định SQL quan trọng, ghi nhận plan tốt, theo dõi thay đổi, kiểm tra plan ứng viên, rồi mới chấp nhận hoặc cố định plan khi có bằng chứng hiệu năng. Baseline không sửa SQL kém, không thay thế statistics/index tuning và không tự chứng minh một plan tốt với mọi bind value.

Bài học thuộc nhóm **Tối ưu SQL** của Database Engine Relational Oracle. Nội dung tập trung vào SQL plan history và baseline, automatic/manual capture, accepted/enabled/fixed, evolve, các API DBMS_SPM, kiểm tra bằng data dictionary và DBMS_XPLAN, kiểm soát regression, transport baseline và quy trình rollout.

Sau bài này, bạn có thể:

- Giải thích SQL Plan Management và vai trò của SQL plan baseline.
- Phân biệt SQL plan history, accepted plan và unaccepted plan.
- Hiểu các thuộc tính ENABLED, ACCEPTED, FIXED, REPRODUCED và AUTOPURGE.
- Bật/tắt automatic plan capture và kiểm tra cấu hình SPM.
- Nạp plan đã biết tốt từ cursor cache hoặc nguồn được hỗ trợ.
- Dùng DBMS_SPM để xem, evolve, bật/tắt, cố định và xóa baseline.
- Kiểm tra plan thực thi bằng V$SQL và DBMS_XPLAN.
- Phân biệt plan hash khác nhau với performance regression thực sự.
- Xác định vì sao baseline không thể tái tạo hoặc không được optimizer chọn.
- Đánh giá plan ứng viên bằng workload và bind values đại diện.
- Chuyển baseline giữa môi trường bằng staging table.
- Thiết kế rollout, rollback và giám sát để hạn chế hồi quy kế hoạch.

> **Phạm vi ví dụ:** Các ví dụ chủ yếu theo Oracle Database 19c. Một số view/API có thể yêu cầu quyền DBA hoặc license phù hợp. Đọc tài liệu đúng release/RU và chính sách licensing của tổ chức trước khi dùng AWR, SQL Tuning Set hoặc tính năng quản trị hiệu năng liên quan.

## 1. Vì sao execution plan có thể thay đổi?

Optimizer chọn cách truy cập và kết hợp dữ liệu dựa trên thông tin hiện có. Cùng một câu SQL có thể chạy bằng nhiều kế hoạch khác nhau:

- Full table scan hoặc index range scan.
- Nested loops hoặc hash join.
- Join order khác nhau.
- Partition pruning hoặc không pruning.
- Parallel execution hoặc serial execution.
- Khác cách xử lý subquery, view merging hoặc predicate pushdown.

### 1.1. Những yếu tố làm plan thay đổi

| Yếu tố | Tác động có thể có |
| --- | --- |
| Statistics được thu thập lại | Cardinality estimate và cost thay đổi |
| Dữ liệu tăng/giảm hoặc phân bố thay đổi | Plan cũ có thể không còn phù hợp |
| Index được tạo, drop hoặc rebuild | Optimizer có thêm hoặc mất access path |
| Bind values khác nhau | Selectivity khác nhau, có thể sinh child cursor/plan khác |
| Optimizer parameters thay đổi | Search space và costing thay đổi |
| Database upgrade/RU | Optimizer behavior hoặc transformation thay đổi |
| Schema/object definition thay đổi | Plan cũ có thể không còn tái tạo được |
| System load và resource thay đổi | Thời gian thực thi thay đổi dù plan giống nhau |

### 1.2. Plan mới không mặc nhiên là regression

Plan hash khác nhau chỉ cho biết cấu trúc plan được biểu diễn khác nhau. Nó không đủ để kết luận plan mới chậm hơn. Một plan mới có thể:

- Dùng index khác nhưng đọc ít block hơn.
- Dùng hash join thay nested loops và nhanh hơn trên tập dữ liệu lớn.
- Có thêm operation nhưng giảm elapsed time.
- Tăng CPU nhưng giảm I/O và cải thiện latency.

Ngược lại, cùng plan hash vẫn có thể chạy chậm hơn do dữ liệu, concurrency, I/O, cache, bind values hoặc resource contention.

### 1.3. Performance regression là gì?

Performance regression xảy ra khi một thay đổi làm SQL chạy kém hơn theo tiêu chí quan trọng, ví dụ:

- Elapsed time tăng đáng kể.
- CPU time tăng.
- Buffer gets hoặc physical reads tăng.
- Số lần thực thi hoặc số hàng xử lý thay đổi ngoài dự kiến.
- Throughput giảm hoặc latency percentile tăng.
- SQL vượt SLA hoặc gây nghẽn cho workload khác.

Không chỉ so sánh plan hash. Cần so sánh số liệu thực thi trong điều kiện tương đương.

## 2. SQL Plan Management là gì?

SQL Plan Management là cơ chế Oracle kiểm soát các plan được optimizer sử dụng cho một SQL statement bằng cách lưu giữ plan history và plan baselines.

### 2.1. Mục tiêu

- Giảm nguy cơ plan mới chưa được kiểm chứng gây regression.
- Giữ lại plan đã có hiệu năng tốt.
- Cho phép optimizer tiếp tục tìm plan mới nhưng quản lý việc chấp nhận.
- Hỗ trợ chuyển plan đã kiểm chứng giữa môi trường.
- Tạo quy trình có thể quan sát và audit khi thay đổi plan.

### 2.2. SQL plan baseline

Một SQL plan baseline gắn với SQL statement và chứa một hoặc nhiều plan được chấp nhận. Optimizer dùng baseline để giới hạn lựa chọn vào các plan được phép và có thể tái tạo.

Baseline thường chứa:

- SQL handle nhận diện statement.
- Plan name.
- Plan outline/hints dùng để tái tạo plan.
- Plan hash value và metadata liên quan.
- Trạng thái enabled/accepted/fixed.
- Nguồn tạo, thời điểm tạo, lần xác minh gần nhất và thống kê sử dụng.

### 2.3. Baseline không phải plan pin tuyệt đối

Baseline không đảm bảo Oracle sẽ thực thi đúng một plan trong mọi hoàn cảnh:

- Plan phải còn ENABLED.
- Plan phải ACCEPTED để được dùng như plan được phê duyệt.
- Plan cần REPRODUCED trong môi trường hiện tại.
- SQL text phải được nhận diện là cùng statement theo cơ chế signature/matching.
- Các điều kiện optimizer và object metadata phải cho phép tái tạo plan.

Nếu plan cũ không thể tái tạo sau khi schema/index thay đổi, baseline không thể buộc Oracle thực thi một plan không còn hợp lệ.

## 3. Plan history và plan baseline

Plan history là nơi ghi nhận các plan đã quan sát cho một SQL statement. Plan baseline là tập các plan được chấp nhận để optimizer xem xét.

### 3.1. Accepted plan

Plan có ACCEPTED = YES là plan được chấp nhận vào baseline. Nếu ENABLED = YES và REPRODUCED = YES, optimizer có thể xem xét plan đó theo quy tắc SPM.

### 3.2. Unaccepted plan

Plan có ACCEPTED = NO là plan đã được ghi nhận nhưng chưa được chấp nhận. Nó không được dùng như một plan đã phê duyệt trong baseline thông thường. Plan này có thể được kiểm tra qua evolve process.

### 3.3. ENABLED

ENABLED = YES cho phép plan tham gia lựa chọn. Nếu ENABLED = NO, plan bị vô hiệu hóa và optimizer không sử dụng nó từ baseline.

### 3.4. FIXED

FIXED = YES đánh dấu plan cố định. Khi có fixed plans hợp lệ, optimizer ưu tiên fixed plans theo quy tắc SPM thay vì lựa chọn plan không fixed chỉ vì cost ước tính thấp hơn.

Không đặt FIXED = YES cho mọi baseline. Fixed plan làm giảm khả năng optimizer chọn plan khác trong tập baseline và có thể giữ một plan cũ dù workload đã thay đổi.

### 3.5. REPRODUCED

REPRODUCED cho biết Oracle có thể tái tạo plan từ baseline trong môi trường hiện tại hay không. Nếu REPRODUCED = NO, cần điều tra thay đổi object, index, optimizer environment hoặc dependency khiến plan không thể được tạo lại.

### 3.6. AUTOPURGE

AUTOPURGE điều khiển việc baseline có được xem xét xóa tự động theo cơ chế retention của SQL Management Base hay không. Tắt autopurge có thể giữ baseline lâu hơn nhưng tiêu thụ thêm không gian.

### 3.7. Các thuộc tính không thể dùng thay nhau

| Thuộc tính | Câu hỏi trả lời |
| --- | --- |
| ENABLED | Plan có được phép tham gia lựa chọn không? |
| ACCEPTED | Plan đã được chấp nhận vào baseline chưa? |
| FIXED | Plan có được ưu tiên như plan cố định không? |
| REPRODUCED | Optimizer có tái tạo được plan không? |
| AUTOPURGE | Plan có thể bị dọn tự động theo retention không? |

## 4. SPM lưu thông tin ở đâu?

SQL Plan Management sử dụng SQL Management Base (SMB), nằm trong SYSAUX tablespace. SMB lưu các thông tin quản lý SQL như plan baselines và các dữ liệu quản trị liên quan.

### 4.1. Theo dõi không gian

SPM có budget và cơ chế quản lý dung lượng cho SQL Management Base. DBA cần theo dõi:

- SYSAUX tablespace còn đủ không gian không.
- Số lượng SQL statements và plans đang được lưu.
- Plan history có tăng nhanh bất thường không.
- Retention/autopurge có phù hợp không.
- Baseline nào cần giữ lâu dài vì SLA hoặc workload quan trọng.

### 4.2. SQL Management Base không phải AWR

SMB và AWR là hai khái niệm khác nhau:

- SMB lưu thông tin quản lý SQL, bao gồm plan baselines.
- AWR lưu workload repository và lịch sử thống kê theo snapshot.
- SPM có thể nạp plan từ nguồn như cursor cache, AWR hoặc SQL Tuning Set qua các API tương ứng, nhưng dữ liệu nguồn và yêu cầu licensing vẫn riêng biệt.

Không nhầm việc baseline được lưu trong SMB với việc SQL plan history trong AWR.

## 5. Cách optimizer dùng SQL plan baseline

Khi parse SQL, optimizer nhận diện statement và tìm baseline phù hợp.

Quy trình khái quát:

~~~text
SQL statement được parse
          |
          v
Tìm SQL plan baseline phù hợp
          |
          v
Lọc plan ENABLED + ACCEPTED
          |
          v
Kiểm tra có tái tạo được plan không
          |
          v
Cost và lựa chọn theo quy tắc SPM
          |
          v
Thực thi plan được chọn
~~~

Nếu không có baseline phù hợp hoặc không có plan baseline nào tái tạo được, optimizer có thể tối ưu theo cách thông thường. Do đó, SPM không phải cơ chế chặn SQL chạy khi baseline không dùng được.

### 5.1. Nhiều accepted plans

Một baseline có thể chứa nhiều accepted plans. Khi đó optimizer có thể chọn plan có cost phù hợp trong số các plan được chấp nhận và tái tạo được.

### 5.2. Fixed plan và non-fixed plan

Fixed plan được ưu tiên theo quy tắc SPM. Nếu có nhiều fixed plans, optimizer so sánh cost giữa chúng. Nếu không có fixed plan tái tạo được, optimizer có thể xét non-fixed accepted plans còn hợp lệ.

### 5.3. Baseline không đảm bảo cùng runtime

Ngay cả khi cùng một baseline plan được chọn:

- Bind values khác nhau có thể làm số hàng thực tế thay đổi.
- Cache nóng/lạnh làm I/O khác nhau.
- Concurrent sessions có thể tạo contention.
- Dữ liệu tăng có thể làm elapsed time tăng.
- Storage, CPU hoặc resource manager có thể thay đổi.

SPM kiểm soát lựa chọn plan; nó không cố định thời gian chạy hoặc tài nguyên hệ thống.

## 6. Automatic plan capture

Oracle có thể tự động capture SQL plans vào SPM khi tính năng được bật và statement đáp ứng tiêu chí capture.

### 6.1. Kiểm tra tham số

~~~sql
SHOW PARAMETER optimizer_capture_sql_plan_baselines
SHOW PARAMETER optimizer_use_sql_plan_baselines
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'optimizer_capture_sql_plan_baselines',
    'optimizer_use_sql_plan_baselines'
)
ORDER BY name;
~~~

Thông thường:

- OPTIMIZER_CAPTURE_SQL_PLAN_BASELINES điều khiển automatic capture.
- OPTIMIZER_USE_SQL_PLAN_BASELINES điều khiển optimizer có sử dụng baselines hay không.

Kiểm tra giá trị thực tế vì cấu hình có thể đã được DBA thay đổi.

### 6.2. Bật automatic capture

~~~sql
ALTER SYSTEM SET optimizer_capture_sql_plan_baselines = TRUE
SCOPE = BOTH;
~~~

Đây là thay đổi system-wide, cần DBA và change approval. Không bật trên production chỉ để thử một câu SQL.

### 6.3. Tắt automatic capture

~~~sql
ALTER SYSTEM SET optimizer_capture_sql_plan_baselines = FALSE
SCOPE = BOTH;
~~~

Tắt capture không đồng nghĩa tắt việc sử dụng baseline đã có. OPTIMIZER_USE_SQL_PLAN_BASELINES là tham số riêng.

### 6.4. Automatic capture không lưu mọi SQL

Oracle dùng tiêu chí capture để tránh lưu mọi câu SQL một lần hoặc SQL không đáng kể. Cấu hình và hành vi chi tiết phụ thuộc release. Có thể dùng DBMS_SPM.CONFIGURE để cấu hình các thuộc tính capture/retention trong phạm vi được hỗ trợ.

### 6.5. Automatic capture và evolve

Plan đầu tiên được capture cho một SQL có thể được chấp nhận theo quy tắc capture; các plan mới khác có thể được ghi nhận ở trạng thái chưa chấp nhận để evolve. Quy trình evolve đánh giá xem plan mới có tốt hơn plan đã chấp nhận không.

Không giả định bật automatic capture đồng nghĩa mọi plan mới sẽ được chấp nhận ngay.

## 7. Manual capture từ cursor cache

Trong vận hành, cách phổ biến là capture một plan đã quan sát và được xác nhận tốt từ cursor cache.

### 7.1. Tìm SQL_ID và plan hash

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    rows_processed,
    sql_plan_baseline,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%FROM ORDERS%'
  AND sql_text NOT LIKE '%v$sql%'
ORDER BY last_active_time DESC;
~~~

Điều chỉnh filter để tìm đúng statement. SQL_TEXT có thể bị cắt ngắn; với SQL dài, dùng SQL_FULLTEXT hoặc truy vấn theo SQL_ID đã biết. Một SQL_ID có thể có nhiều child cursors và nhiều plan hash values.

### 7.2. Xác nhận plan tốt trước khi capture

Xem plan runtime:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => 'SQL_ID_VALUE',
        cursor_child_no => 0,
        format => 'ALLSTATS LAST +PEEKED_BINDS +OUTLINE +NOTE'
    )
);
~~~

Thay SQL_ID và child number bằng giá trị thực tế. ALLSTATS LAST hữu ích khi statement đã thu thập runtime plan statistics; nếu không có statistics, một số cột actual rows/starts có thể không hiển thị.

### 7.3. Load một plan cụ thể

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
        sql_id          => 'SQL_ID_VALUE',
        plan_hash_value => 1234567890,
        fixed           => 'NO',
        enabled         => 'YES'
    );

    DBMS_OUTPUT.PUT_LINE('Plans loaded=' || l_loaded);
END;
/
~~~

API trả về số plan được load. Nếu cần chỉ định parsing schema hoặc các filter khác, xem overload trong package specification của đúng release.

### 7.4. Không capture plan chỉ vì nó đang có trong cache

Cursor cache có thể chứa:

- Plan đang chạy tốt.
- Plan chỉ chạy với một bind value đặc biệt.
- Plan thử nghiệm.
- Child cursor có environment khác.

Trước khi load, xác nhận SQL text, parsing schema, plan hash, bind values, executions và runtime metrics.

## 8. Xem baseline trong data dictionary

View quan trọng là DBA_SQL_PLAN_BASELINES. User có thể dùng USER_SQL_PLAN_BASELINES hoặc ALL_SQL_PLAN_BASELINES theo quyền và phạm vi.

### 8.1. Xem các baseline

~~~sql
SELECT
    sql_handle,
    plan_name,
    origin,
    enabled,
    accepted,
    fixed,
    reproduced,
    autopurge,
    last_verified,
    last_executed,
    created,
    plan_hash_value,
    optimizer_cost
FROM dba_sql_plan_baselines
ORDER BY created DESC;
~~~

DBA_SQL_PLAN_BASELINES cần quyền xem dictionary. Nếu không có DBA access, thử USER_SQL_PLAN_BASELINES.

### 8.2. Tìm baseline theo SQL text

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    plan_hash_value,
    sql_text
FROM dba_sql_plan_baselines
WHERE UPPER(sql_text) LIKE '%ORDERS%'
ORDER BY sql_handle, plan_name;
~~~

Filter theo SQL_TEXT chỉ là cách tìm sơ bộ. Với môi trường lớn, dùng SQL_HANDLE hoặc signature đã xác định để tránh lấy nhầm statement tương tự.

### 8.3. Xem plan của baseline

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE'
    )
);
~~~

Có thể chỉ định plan name nếu cần xem một plan cụ thể theo overload được hỗ trợ. Output hiển thị plan outline và các thông tin giúp đánh giá baseline.

### 8.4. Xem SQL đang dùng baseline nào

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    sql_plan_baseline,
    executions,
    elapsed_time,
    buffer_gets
FROM v$sql
WHERE sql_plan_baseline IS NOT NULL
ORDER BY last_active_time DESC;
~~~

Tên cột và khả năng hiển thị có thể khác theo view/release; kiểm tra V$SQL reference của database đích.

## 9. Kiểm tra plan runtime và baseline note

### 9.1. DISPLAY_CURSOR

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_VALUE',
        0,
        'ALLSTATS LAST +OUTLINE +NOTE'
    )
);
~~~

Phần NOTE có thể cho biết SQL plan baseline được sử dụng hoặc optimizer đã xử lý baseline ra sao.

### 9.2. DISPLAY_SQL_PLAN_BASELINE

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE',
        plan_name  => 'SQL_PLAN_NAME'
    )
);
~~~

Đây là plan được lưu trong baseline, không phải số liệu runtime của lần chạy gần nhất. Để biết thực tế, đối chiếu DISPLAY_CURSOR và V$SQL.

### 9.3. Plan hash value

PLAN_HASH_VALUE giúp nhận diện cấu trúc plan trong nhiều view. Tuy nhiên:

- Không đại diện cho toàn bộ runtime conditions.
- Không bảo đảm hai lần chạy có cùng elapsed time.
- Không phải khóa duy nhất của mọi chi tiết plan.
- Một SQL_ID có thể có nhiều plan hash values.

## 10. Evolve baseline

Evolve là quy trình đánh giá plan chưa được chấp nhận để quyết định có nên đưa vào baseline hay không.

### 10.1. Vì sao cần evolve?

Sau khi statistics hoặc schema thay đổi, optimizer có thể tìm ra plan mới. Không nên tự động chấp nhận plan mới chỉ vì optimizer ước tính cost thấp hơn. Evolve giúp so sánh plan ứng viên với plan đã accepted bằng quy trình verification của Oracle.

### 10.2. Evolve một SQL handle

~~~sql
SET LONG 100000
SET LONGCHUNKSIZE 100000

SELECT DBMS_SPM.EVOLVE_SQL_PLAN_BASELINE(
           sql_handle => 'SQL_HANDLE_VALUE',
           time_limit => 300,
           verify     => 'YES',
           commit     => 'NO'
       ) AS evolve_report
FROM dual;
~~~

Ví dụ dùng COMMIT = NO để xem report trước. Sau khi đọc report và xác nhận kết quả, có thể chạy lại với COMMIT = YES hoặc dùng quy trình accept phù hợp của tổ chức. Tham số/overload cụ thể cần đối chiếu package reference của release.

### 10.3. Evolve có thể mất thời gian

Verification có thể thực thi SQL để so sánh plan. Cần:

- Đặt time_limit hợp lý.
- Chạy trong maintenance window nếu SQL nặng.
- Dùng bind values đại diện.
- Đảm bảo dữ liệu và workload test phản ánh production.
- Theo dõi tài nguyên và side effects của SQL được kiểm tra.

Không chạy evolve hàng loạt trên mọi SQL mà không giới hạn thời gian và phạm vi.

### 10.4. Đọc evolve report

Report có thể thể hiện:

- Plan nào được kiểm tra.
- Plan nào được chấp nhận hoặc bị từ chối.
- So sánh hiệu năng.
- Lý do verification không hoàn tất.
- Thời gian hoặc giới hạn khiến quá trình dừng.

Không chỉ nhìn dòng “accepted”; cần hiểu plan nào được so sánh, test có đủ đại diện không và điều kiện môi trường có tương đương không.

### 10.5. Evolve không thay thế kiểm thử nghiệp vụ

Plan verification đánh giá hiệu năng SQL theo cơ chế Oracle. Nó không kiểm tra kết quả nghiệp vụ có đúng hay không. Trước khi đưa plan vào production, ứng dụng vẫn cần regression tests và data correctness checks.

## 11. Quản lý baseline bằng DBMS_SPM

DBMS_SPM là package quản trị SQL Plan Management. Các API thường dùng gồm:

- LOAD_PLANS_FROM_CURSOR_CACHE.
- LOAD_PLANS_FROM_AWR.
- LOAD_PLANS_FROM_SQLSET.
- EVOLVE_SQL_PLAN_BASELINE.
- ALTER_SQL_PLAN_BASELINE.
- DROP_SQL_PLAN_BASELINE.
- CREATE_STGTAB_BASELINE.
- PACK_STGTAB_BASELINE.
- UNPACK_STGTAB_BASELINE.

Tên overload và tham số có thể khác theo release; luôn xem package reference tương ứng.

### 11.1. Bật/tắt một baseline plan

~~~sql
DECLARE
    l_changed PLS_INTEGER;
BEGIN
    l_changed := DBMS_SPM.ALTER_SQL_PLAN_BASELINE(
        sql_handle      => 'SQL_HANDLE_VALUE',
        plan_name       => 'SQL_PLAN_NAME',
        attribute_name  => 'ENABLED',
        attribute_value => 'NO'
    );

    DBMS_OUTPUT.PUT_LINE('Changed=' || l_changed);
END;
/
~~~

Đổi NO thành YES để bật lại. Kiểm tra return value và truy vấn DBA_SQL_PLAN_BASELINES sau thao tác.

### 11.2. Đặt FIXED

~~~sql
DECLARE
    l_changed PLS_INTEGER;
BEGIN
    l_changed := DBMS_SPM.ALTER_SQL_PLAN_BASELINE(
        sql_handle      => 'SQL_HANDLE_VALUE',
        plan_name       => 'SQL_PLAN_NAME',
        attribute_name  => 'FIXED',
        attribute_value => 'YES'
    );

    DBMS_OUTPUT.PUT_LINE('Changed=' || l_changed);
END;
/
~~~

Chỉ đặt fixed sau khi plan đã được xác nhận tốt trên workload đại diện. Khi muốn optimizer có thêm tự do lựa chọn giữa accepted plans, đặt FIXED = NO.

### 11.3. Đổi AUTOPURGE

~~~sql
DECLARE
    l_changed PLS_INTEGER;
BEGIN
    l_changed := DBMS_SPM.ALTER_SQL_PLAN_BASELINE(
        sql_handle      => 'SQL_HANDLE_VALUE',
        plan_name       => 'SQL_PLAN_NAME',
        attribute_name  => 'AUTOPURGE',
        attribute_value => 'NO'
    );
END;
/
~~~

Tắt autopurge làm baseline không bị dọn tự động theo cơ chế này. Theo dõi dung lượng SMB và chỉ áp dụng với plan thực sự cần giữ.

### 11.4. Xóa baseline

~~~sql
DECLARE
    l_dropped PLS_INTEGER;
BEGIN
    l_dropped := DBMS_SPM.DROP_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE',
        plan_name  => 'SQL_PLAN_NAME'
    );

    DBMS_OUTPUT.PUT_LINE('Dropped=' || l_dropped);
END;
/
~~~

Nếu bỏ plan_name theo overload được hỗ trợ, có thể xóa toàn bộ baseline của SQL handle. Trước khi drop, lưu thông tin plan cần giữ và xác nhận SQL handle chính xác.

### 11.5. Kiểm tra sau mỗi thay đổi

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    autopurge,
    last_verified
FROM dba_sql_plan_baselines
WHERE sql_handle = 'SQL_HANDLE_VALUE'
ORDER BY plan_name;
~~~

Không coi lời gọi API trả về số dương là bằng chứng duy nhất. Kiểm tra metadata sau khi thay đổi.

## 12. Load plan từ AWR hoặc SQL Tuning Set

Ngoài cursor cache, DBMS_SPM có thể nạp plan từ các nguồn khác.

### 12.1. Load từ AWR

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_AWR(
        begin_snap   => 100,
        end_snap     => 120,
        basic_filter => q'[sql_id = 'abc123xyz4567']'
    );

    DBMS_OUTPUT.PUT_LINE('Plans loaded=' || l_loaded);
END;
/
~~~

Ví dụ minh họa filter theo SQL_ID và snapshot range. Cần kiểm tra signature của API và view AWR trong release đang dùng.

### 12.2. Licensing AWR

Truy cập AWR và các tính năng liên quan có thể thuộc Oracle Diagnostics Pack. Việc dùng DBMS_SPM.LOAD_PLANS_FROM_AWR không miễn trừ yêu cầu license của nguồn AWR. Xác nhận hợp đồng/license của tổ chức trước khi truy vấn DBA_HIST_* hoặc dùng tính năng yêu cầu pack.

### 12.3. Load từ SQL Tuning Set

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_SQLSET(
        sqlset_name => 'APP_SQLSET',
        basic_filter => q'[sql_id = 'abc123xyz4567']'
    );

    DBMS_OUTPUT.PUT_LINE('Plans loaded=' || l_loaded);
END;
/
~~~

SQL Tuning Set có thể chứa SQL statements, execution statistics và plan information. Việc tạo/quản lý STS và nguồn dữ liệu có yêu cầu quyền và licensing riêng; kiểm tra Oracle Tuning Pack/Diagnostics Pack applicability.

### 12.4. Chọn nguồn phù hợp

| Nguồn | Khi phù hợp | Điều cần xác minh |
| --- | --- | --- |
| Cursor cache | Plan vừa chạy và đã xác nhận trên database hiện tại | SQL_ID, child, plan hash, binds, runtime metrics |
| AWR | Cần khôi phục plan lịch sử từ snapshots | Snapshot range, SQL_ID, licensing |
| SQL Tuning Set | Cần vận chuyển/tập hợp SQL và plan giữa môi trường | STS content, SQL profile/plan metadata, licensing |

## 13. Chuyển baseline giữa môi trường

Baseline được lưu trong SMB của database. Để chuyển plan từ TEST sang PROD, Oracle hỗ trợ staging table và các API pack/unpack.

### 13.1. Tạo staging table

Trên database nguồn:

~~~sql
BEGIN
    DBMS_SPM.CREATE_STGTAB_BASELINE(
        table_name  => 'SPM_STGTAB',
        table_owner => 'SPM_ADMIN',
        tablespace_name => 'USERS'
    );
END;
/
~~~

Tên owner/tablespace phải tồn tại và user có quyền phù hợp. Bảng staging là nơi đóng gói metadata baseline để vận chuyển.

### 13.2. Pack baseline

~~~sql
DECLARE
    l_packed PLS_INTEGER;
BEGIN
    l_packed := DBMS_SPM.PACK_STGTAB_BASELINE(
        table_name  => 'SPM_STGTAB',
        table_owner => 'SPM_ADMIN',
        sql_handle  => 'SQL_HANDLE_VALUE'
    );

    DBMS_OUTPUT.PUT_LINE('Packed=' || l_packed);
END;
/
~~~

Có thể dùng filter/plan_name theo overload được hỗ trợ để pack đúng SQL/plan cần chuyển.

### 13.3. Export/import staging table

Dùng Data Pump hoặc phương thức được DBA phê duyệt để chuyển staging table. Không copy trực tiếp internal SMB tables.

### 13.4. Unpack ở database đích

~~~sql
DECLARE
    l_unpacked PLS_INTEGER;
BEGIN
    l_unpacked := DBMS_SPM.UNPACK_STGTAB_BASELINE(
        table_name  => 'SPM_STGTAB',
        table_owner => 'SPM_ADMIN'
    );

    DBMS_OUTPUT.PUT_LINE('Unpacked=' || l_unpacked);
END;
/
~~~

Sau unpack:

- Kiểm tra SQL handle và plan name.
- Kiểm tra ENABLED/ACCEPTED/FIXED.
- Xem REPRODUCED.
- Chạy SQL với bind values đại diện.
- Xác nhận baseline được dùng qua DBMS_XPLAN.

### 13.5. Baseline không đảm bảo plan giống nhau giữa hai môi trường

TEST và PROD có thể khác:

- Table/index definitions.
- Statistics và data distribution.
- Partitioning.
- Optimizer parameters.
- Database version/RU.
- Object privileges hoặc parsing schema.

Plan được pack từ TEST có thể không tái tạo được ở PROD. Phải xác minh sau unpack, không xem pack/unpack thành một thao tác bảo đảm tương đương runtime.

## 14. Kiểm soát regression khi statistics thay đổi

Statistics refresh là một nguyên nhân phổ biến làm optimizer chọn plan khác.

### 14.1. Quy trình trước khi gather statistics

1. Xác định SQL quan trọng và SQL_ID.
2. Ghi nhận plan hash và runtime metrics hiện tại.
3. Xác nhận plan baseline đang enabled/accepted/reproduced.
4. Ghi lại bind values đại diện.
5. Chạy workload benchmark trước thay đổi.

### 14.2. Gather statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'APP_OWNER',
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Statistics gathering cần được quản lý theo chính sách DBMS_STATS. Nếu dùng pending statistics, hãy hiểu quy trình publish/use pending stats của môi trường.

### 14.3. Kiểm tra sau statistics

- SQL có chọn plan hash mới không?
- Plan có được lấy từ baseline không?
- Actual rows có khác estimate đáng kể không?
- Elapsed time, CPU, buffer gets và physical reads thay đổi thế nào?
- Bind values nào bị ảnh hưởng?
- SQL khác có bị regression do thay đổi statistics không?

### 14.4. Baseline là lớp bảo vệ, không phải lý do bỏ statistics

Không ngừng gather statistics chỉ vì đã tạo baseline. Statistics vẫn cần phản ánh dữ liệu để optimizer chọn tốt giữa các accepted plans và tối ưu các SQL khác.

### 14.5. Statistics và plan evolution

Sau khi statistics thay đổi, optimizer có thể tìm plan mới. Có thể giữ plan cũ trong baseline, sau đó evolve plan mới bằng workload representative. Nếu plan mới tốt hơn, chấp nhận nó; nếu không, giữ baseline cũ.

## 15. Kiểm soát regression khi upgrade Oracle

Database upgrade/RU có thể thay đổi optimizer behavior và plan selection.

### 15.1. Trước upgrade

- Thu thập SQL workload quan trọng.
- Capture SQL plans hiện tại.
- Tạo/kiểm tra baselines cho SQL có SLA cao.
- Ghi lại optimizer parameters.
- Xác định SQL có bind-sensitive behavior.
- Lập danh sách SQL cần so sánh sau upgrade.

### 15.2. Sau upgrade

- Xác nhận baseline đã được chuyển/giữ theo kế hoạch.
- Kiểm tra REPRODUCED.
- Chạy workload đại diện.
- So sánh plan hash và runtime metrics.
- Dùng SQL Plan Management để hạn chế regression nếu baseline phù hợp.
- Evolve plan mới khi có bằng chứng tốt hơn.

### 15.3. Không ép baseline cũ vô điều kiện

Plan cũ có thể không phù hợp với optimizer version mới hoặc object metadata đã thay đổi. Nếu plan không tái tạo được, điều tra lý do. Có thể cần:

- Rebuild/recreate index hoặc object theo thiết kế.
- Sửa SQL.
- Nạp baseline phù hợp từ workload sau upgrade.
- Chấp nhận plan mới đã được kiểm chứng.

## 16. Bind variables và nhiều child cursors

Một SQL statement dùng bind variables có thể sinh nhiều child cursors vì bind metadata, bind sensitivity, optimizer environment hoặc các lý do khác.

### 16.1. Bind peeking

Optimizer có thể dùng bind value được peek tại hard parse để ước lượng selectivity. Nếu dữ liệu skewed, một plan có thể tốt cho giá trị hiếm nhưng tệ cho giá trị phổ biến, hoặc ngược lại.

### 16.2. Adaptive Cursor Sharing

Adaptive Cursor Sharing có thể tạo nhiều child cursors/plans cho các vùng bind selectivity khác nhau. SPM quản lý các plan ở cấp SQL statement nhưng không loại bỏ mọi vấn đề bind sensitivity.

### 16.3. Không capture một plan duy nhất khi workload có nhiều nhóm bind

Trước khi capture baseline:

- Chọn bind values đại diện.
- Kiểm tra V$SQL child cursors.
- So sánh executions, rows processed và runtime.
- Xác định có nhiều selectivity classes hay không.
- Tránh cố định plan chỉ tốt cho một bind value.

### 16.4. Kiểm tra child cursor

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    is_bind_sensitive,
    is_bind_aware,
    sql_plan_baseline
FROM v$sql
WHERE sql_id = 'SQL_ID_VALUE'
ORDER BY child_number;
~~~

Các cột bind-sensitive/aware phụ thuộc view/release. Kiểm tra V$SQL reference trước khi dùng.

## 17. Vì sao baseline không được dùng?

Có baseline không đồng nghĩa optimizer đang sử dụng nó.

### 17.1. OPTIMIZER_USE_SQL_PLAN_BASELINES = FALSE

Nếu tham số này tắt, optimizer không dùng SPM baseline theo cấu hình thông thường. Kiểm tra:

~~~sql
SHOW PARAMETER optimizer_use_sql_plan_baselines
~~~

### 17.2. Plan bị disable

ENABLED = NO khiến plan không được xem xét.

### 17.3. Plan chưa accepted

ACCEPTED = NO nghĩa plan chưa được đưa vào tập plan được phê duyệt. Cần evolve/accept theo quy trình.

### 17.4. Plan không reproduce được

REPRODUCED = NO có thể do:

- Index đã bị drop/đổi tên.
- Object hoặc partition structure thay đổi.
- SQL text/signature không còn match.
- Optimizer environment thay đổi.
- Dependency hoặc privilege thay đổi.

### 17.5. SQL không match baseline

SQL handle/signature phụ thuộc cách Oracle nhận diện statement. Thay đổi text, literal, whitespace/comment hoặc schema qualification có thể ảnh hưởng matching theo signature/force matching settings. Không sửa SQL text một cách tùy tiện sau khi baseline được tạo.

### 17.6. Plan baseline có fixed/non-fixed behavior

Một plan non-fixed có thể không được chọn nếu optimizer đánh giá plan accepted khác có cost tốt hơn. Nếu mục tiêu là cố định plan, cần hiểu FIXED và trade-off trước khi dùng.

## 18. Force matching và SQL signatures

Oracle nhận diện SQL statements bằng signature. SPM có cơ chế force matching để nhóm một số câu SQL khác literal nhưng có cấu trúc tương tự.

### 18.1. Exact matching

Exact matching gắn baseline với SQL text/signature tương ứng. Các thay đổi text có thể tạo statement khác theo cách Oracle nhận diện.

### 18.2. Force matching

Force matching có thể hữu ích khi ứng dụng phát sinh cùng một SQL template nhưng literal khác nhau. Tuy nhiên, không nên bật force matching mù quáng:

- Hai SQL có cùng cấu trúc nhưng semantics hoặc selectivity khác nhau.
- Một plan có thể không phù hợp cho mọi literal.
- Bind peeking/ACS vẫn cần được xem xét.

### 18.3. Kiểm tra SQL handle và signature

Các view/API SPM cung cấp SQL_HANDLE và thông tin statement. Dùng handle được trả về sau capture/load để quản lý đúng baseline. Không tự đoán SQL_HANDLE từ SQL_ID.

## 19. Đo lường hiệu năng và xác định regression

SPM giúp kiểm soát plan, nhưng quyết định chấp nhận plan phải dựa trên số liệu.

### 19.1. Các metric quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| ELAPSED_TIME | Tổng thời gian thực thi tích lũy |
| CPU_TIME | CPU time tích lũy |
| BUFFER_GETS | Logical reads |
| DISK_READS | Physical reads |
| ROWS_PROCESSED | Số hàng xử lý |
| EXECUTIONS | Số lần thực thi |
| FETCHES | Fetch calls |
| END_OF_FETCH_COUNT | Số lần fetch hoàn tất |

V$SQL lưu số liệu tích lũy theo cursor. Khi so sánh, cần chia theo executions hoặc dùng delta giữa hai khoảng thời gian thay vì so tổng tuyệt đối.

### 19.2. Metric trung bình

~~~sql
SELECT
    sql_id,
    plan_hash_value,
    executions,
    ROUND(elapsed_time / NULLIF(executions, 0) / 1e6, 4)
        AS avg_elapsed_seconds,
    ROUND(cpu_time / NULLIF(executions, 0) / 1e6, 4)
        AS avg_cpu_seconds,
    ROUND(buffer_gets / NULLIF(executions, 0), 2)
        AS avg_buffer_gets,
    ROUND(disk_reads / NULLIF(executions, 0), 2)
        AS avg_disk_reads
FROM v$sql
WHERE sql_id = 'SQL_ID_VALUE'
ORDER BY plan_hash_value;
~~~

Các giá trị trong V$SQL là cumulative metrics cho cursor. Average không cho thấy phân phối latency; với SLA percentile, cần lấy dữ liệu runtime phù hợp.

### 19.3. So sánh trước/sau bằng delta

Ghi snapshot metric ở thời điểm bắt đầu và kết thúc, sau đó tính delta:

~~~text
delta_elapsed = elapsed_after - elapsed_before
delta_execs   = executions_after - executions_before
avg_elapsed   = delta_elapsed / delta_execs
~~~

Chỉ so sánh khi cursor không bị aged out hoặc reset giữa hai lần đọc. Nếu cursor mới được tạo, phải nhận diện đúng child cursor/plan.

### 19.4. Plan hash không thay thế runtime metrics

Hai plan hash khác nhau cần được đánh giá bằng:

- Actual rows và estimated rows.
- Starts và A-Rows theo operation.
- Logical/physical reads.
- CPU và elapsed time.
- Bind values.
- Concurrency và wait events.

Plan có hash khác nhưng nhanh hơn không phải regression.

### 19.5. AWR/ASH và SQL Monitor

AWR/ASH và SQL Monitor giúp phân tích workload và thời gian thực thi, nhưng có điều kiện licensing và quyền riêng. Dùng chúng theo license của tổ chức. Nếu không có Diagnostics/Tuning Pack, dùng các view và công cụ được phép như V$SQL, DBMS_XPLAN, SQL Trace/TKPROF theo cấu hình.

## 20. SQL Plan Management và các công cụ tối ưu khác

SPM không thay thế các cơ chế tối ưu khác.

| Công cụ | Vai trò | Khác SPM |
| --- | --- | --- |
| SQL Plan Baseline | Quản lý tập plan được chấp nhận | Kiểm soát plan selection |
| SQL Profile | Cung cấp auxiliary statistics để cải thiện cardinality estimates | Không trực tiếp cố định plan |
| SQL Patch | Gắn optimizer hints vào SQL | Thay đổi optimizer directives |
| SQL Tuning Advisor | Phân tích và đề xuất tuning | Công cụ tư vấn; licensing có thể áp dụng |
| SQL Plan Directive | Hỗ trợ optimizer với thông tin thống kê bổ sung theo release | Không phải baseline |
| SQL Plan Control/Outline | Các cơ chế khác hoặc legacy để ảnh hưởng plan | Không nên nhầm với SPM |

### 20.1. Baseline và SQL Profile

SQL Profile cải thiện ước lượng của optimizer. Baseline giới hạn các plan được phép sử dụng. Hai cơ chế có thể cùng tồn tại và giải quyết vấn đề khác nhau.

### 20.2. Baseline và SQL Patch

SQL Patch có thể gắn hints để hướng optimizer. Khi xử lý regression, không tạo patch và baseline chồng chéo mà không hiểu thứ tự/ảnh hưởng. Kiểm tra SQL notes, outline và các SQL management objects đang áp dụng.

### 20.3. Baseline và optimizer hints trong SQL

Hints viết trong SQL có thể ảnh hưởng optimizer. Baseline cũng lưu outline information. Nếu SQL text chứa hints mới hoặc schema thay đổi, baseline cũ có thể không còn được áp dụng như dự kiến. Kiểm tra actual plan và note.

## 21. Quy trình vận hành SPM trong production

### 21.1. Xác định SQL cần bảo vệ

Ưu tiên:

- SQL có SLA/latency nghiêm ngặt.
- SQL chạy thường xuyên và tiêu thụ tài nguyên lớn.
- SQL trong luồng thanh toán/đặt hàng/báo cáo quan trọng.
- SQL từng có regression sau statistics refresh hoặc upgrade.
- SQL có nhiều bind values và nhiều plan behavior.

Không cần baseline cho mọi SQL trong hệ thống.

### 21.2. Ghi nhận plan tốt

1. Xác định SQL_ID và SQL text.
2. Xác định parsing schema/module/action.
3. Xem child cursors và bind sensitivity.
4. Kiểm tra plan thực tế bằng DBMS_XPLAN.
5. Ghi nhận runtime metrics theo nhiều lần chạy.
6. Capture plan bằng DBMS_SPM.
7. Xác nhận baseline xuất hiện trong DBA_SQL_PLAN_BASELINES.

### 21.3. Theo dõi sau capture

- Optimizer có dùng baseline không?
- Plan có REPRODUCED = YES không?
- Có plan mới unaccepted xuất hiện không?
- Elapsed time/CPU/IO có thay đổi không?
- SQL có bị thay đổi text hoặc parsing schema không?

### 21.4. Evolve có kiểm soát

1. Xem plan ứng viên.
2. Xác định nguồn và thời điểm plan xuất hiện.
3. Kiểm tra bind values và workload đại diện.
4. Chạy evolve với giới hạn thời gian.
5. Đọc report.
6. Chấp nhận plan mới nếu kết quả và hiệu năng đạt yêu cầu.
7. Theo dõi production sau khi plan được enable.

### 21.5. Rollback plan

Nếu plan mới gây regression:

- Disable plan mới trong baseline.
- Bật lại plan cũ đã được xác nhận.
- Nếu cần, đặt plan cũ FIXED sau khi đánh giá.
- Kiểm tra optimizer note và plan hash.
- Ghi nhận SQL handle, plan name và thao tác đã thực hiện.

Không xóa plan cũ ngay sau khi plan mới được chấp nhận. Giữ đường rollback theo retention/change policy.

## 22. Quy trình xử lý một regression thực tế

Giả sử sau khi gather statistics, endpoint tra cứu đơn hàng tăng latency từ 100 ms lên 2 giây.

### Bước 1 — Xác nhận SQL và phạm vi

- Tìm SQL_ID từ application trace/log hoặc V$SQL.
- Xác định module/action, parsing schema và bind values.
- Kiểm tra SQL có nhiều child cursors không.

### Bước 2 — So sánh plan

- Ghi plan hash trước/sau nếu có.
- Dùng DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.
- So sánh join order, access paths, cardinality và actual rows.

### Bước 3 — Xác định nguyên nhân

- Statistics thay đổi?
- Bind value skew?
- Index bị drop/invalid?
- Optimizer parameter thay đổi?
- SQL text hoặc schema thay đổi?
- Có concurrency/resource issue khiến cùng plan chậm?

### Bước 4 — Kiểm tra baseline hiện tại

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    plan_hash_value
FROM dba_sql_plan_baselines
WHERE UPPER(sql_text) LIKE '%ORDER_ID%'
ORDER BY created;
~~~

Nếu chưa có baseline, xem lại cursor cache hoặc nguồn lịch sử để tìm plan đã được chứng minh tốt.

### Bước 5 — Capture plan tốt

Load plan từ cursor cache/AWR/SQL Tuning Set phù hợp. Xác minh plan được load và có thể tái tạo.

### Bước 6 — Kiểm tra bằng workload

Chạy với bind values phổ biến và biên, so sánh latency/CPU/reads. Không chỉ chạy một bind value.

### Bước 7 — Rollout và theo dõi

Enable/accept baseline theo change process. Theo dõi SQL runtime và các statement liên quan. Nếu regression vẫn còn, baseline không giải quyết root cause; tiếp tục điều tra statistics, data skew, I/O, locking hoặc SQL design.

## 23. Những giới hạn và rủi ro của SPM

### 23.1. Baseline có thể lỗi thời

Plan được capture khi dữ liệu nhỏ có thể không còn tốt khi dữ liệu tăng. Giữ baseline cũ vô thời hạn có thể cản optimizer dùng plan tốt hơn.

### 23.2. Fixed plan làm giảm tính linh hoạt

FIXED = YES có thể giúp bảo vệ plan đã chứng minh tốt, nhưng cũng có thể ngăn optimizer dùng plan mới tốt hơn. Dùng fixed có thời hạn và review định kỳ.

### 23.3. Plan không reproduce được

Baseline phụ thuộc object metadata và optimizer environment. Sau schema migration hoặc upgrade, plan có thể không tái tạo được.

### 23.4. Bind values không đại diện

Capture một plan với bind value hiếm có thể bảo vệ plan không phù hợp với phần lớn workload.

### 23.5. Baseline không sửa cardinality/data model

Nếu query có predicate không sargable, thiếu index, join sai hoặc function gọi theo từng hàng, baseline chỉ có thể giữ một plan trong các lựa chọn hiện có. Có thể cần viết lại SQL hoặc thay đổi schema/index.

### 23.6. Baseline không ngăn runtime resource issues

CPU saturation, I/O latency, lock contention, network waits và storage problems vẫn có thể làm SQL chậm dù plan không đổi.

### 23.7. Dung lượng SMB

Capture quá nhiều plan và tắt autopurge không kiểm soát có thể làm tăng dung lượng SQL Management Base. Cần retention và housekeeping.

## 24. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Baseline tồn tại nhưng không được dùng | USE_SQL_PLAN_BASELINES tắt, plan disabled/unaccepted hoặc SQL không match | Kiểm tra parameters, flags, SQL handle và DBMS_XPLAN note |
| Plan mới không được chấp nhận | Evolve verification không đạt hoặc chưa chạy | Đọc evolve report, kiểm tra bind/workload và chạy evolve có kiểm soát |
| REPRODUCED = NO | Object/index/optimizer environment thay đổi | Xem plan outline và dependency, xác minh schema |
| Nạp từ cursor cache trả 0 | SQL_ID/plan hash không đúng, plan aged out hoặc filter không match | Kiểm tra V$SQL và child cursor hiện tại |
| Nạp baseline nhầm SQL | Dùng SQL_ID hoặc text filter quá rộng | Xác nhận SQL text, parsing schema và plan hash |
| Plan fixed gây chậm sau tăng dữ liệu | Fixed plan không còn phù hợp workload mới | Đánh giá plan khác, evolve và bỏ fixed khi phù hợp |
| Plan hash giống nhưng latency tăng | Resource, bind, data volume hoặc concurrency đổi | Phân tích runtime metrics/waits |
| Plan hash khác nhưng nhanh hơn | Optimizer chọn plan mới tốt hơn | Không gọi đó là regression; benchmark và cân nhắc evolve |
| Unpack baseline nhưng không reproduce | Môi trường đích khác object/index/stats/version | Đồng bộ schema cần thiết hoặc capture plan phù hợp tại đích |
| Evolve mất nhiều thời gian | SQL nặng hoặc time_limit lớn | Giới hạn phạm vi/thời gian, chạy trong window phù hợp |
| SMB tăng dung lượng | Quá nhiều plan history hoặc autopurge bị tắt | Review retention và dọn baseline không còn cần |
| Không truy cập DBA_SQL_PLAN_BASELINES | Thiếu quyền dictionary | Dùng USER_/ALL_ view hoặc xin quyền DBA read-only phù hợp |

## 25. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Baseline đóng băng plan tuyệt đối | Plan cần enabled, accepted và reproduce được |
| Một SQL chỉ có một baseline plan | Một SQL có thể có nhiều accepted/unaccepted plans |
| Plan hash khác nghĩa là regression | Cần so sánh runtime metrics |
| Plan hash giống nghĩa là hiệu năng không đổi | Runtime có thể khác do dữ liệu, bind và resource |
| Bật automatic capture sẽ capture mọi SQL | Capture có tiêu chí; không lưu mọi statement |
| Bật capture đồng nghĩa bật sử dụng baseline | Hai tham số capture/use độc lập |
| Unaccepted plan tự được optimizer dùng | Nó cần được chấp nhận theo quy trình SPM |
| FIXED = YES luôn tốt | Có thể khóa optimizer vào plan lỗi thời |
| Evolve chỉ so sánh cost | Verification có thể đánh giá hiệu năng thực thi |
| Baseline thay thế statistics | Statistics vẫn cần thiết |
| Baseline bảo vệ mọi bind values | Bind sensitivity và nhiều child cursors vẫn phải xét |
| Pack/unpack bảo đảm plan chạy giống nhau | Plan có thể không reproduce ở môi trường khác |
| SPM sửa SQL kém | SPM kiểm soát plan, không sửa query design |
| AWR là nguồn miễn phí không điều kiện | AWR/pack usage có yêu cầu licensing |

## 26. Checklist quản lý SQL Plan Baseline

**Trước khi capture**

- SQL có thực sự quan trọng không?
- Đã xác nhận SQL text, SQL_ID và parsing schema chưa?
- Đã xem child cursors và bind sensitivity chưa?
- Plan hiện tại có runtime metrics tốt và ổn định không?
- Có kiểm tra actual rows/estimated rows chưa?

**Khi capture**

- Nguồn plan là cursor cache, AWR hay SQL Tuning Set?
- Có load đúng plan hash không?
- Plan được bật/accepted theo ý định chưa?
- Có cần fixed không?
- Có ghi nhận SQL handle và plan name không?

**Sau capture**

- Optimizer có sử dụng baseline không?
- REPRODUCED có YES không?
- Runtime metrics có ổn định không?
- Có unaccepted plans mới cần evolve không?
- SMB có được theo dõi dung lượng không?

**Khi thay đổi**

- Đã review report trước khi commit evolve chưa?
- Có test bind values đại diện không?
- Có rollback plan cũ không?
- Có theo dõi sau rollout không?
- Có ghi lại lý do enable/disable/fixed/drop không?

## 27. Bài thực hành tổng hợp

Lab minh họa capture plan từ cursor cache và kiểm tra baseline. Chạy trên schema/database lab có quyền thực thi DBMS_SPM; không dùng trên production nếu chưa được phê duyệt.

### Bước 1 — Tạo bảng và dữ liệu

~~~sql
CREATE TABLE spm_orders_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    order_total NUMBER(12,2)
);

INSERT INTO spm_orders_lab
SELECT
    LEVEL,
    MOD(LEVEL, 10000) + 1,
    CASE WHEN MOD(LEVEL, 5) = 0 THEN 'PAID' ELSE 'NEW' END,
    MOD(LEVEL, 50000) + 1
FROM dual
CONNECT BY LEVEL <= 100000;

CREATE INDEX ix_spm_orders_customer_lab
ON spm_orders_lab(customer_id);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SPM_ORDERS_LAB',
        cascade => TRUE
    );
END;
/
~~~

### Bước 2 — Chạy SQL

~~~sql
SELECT /* SPM_ROW436_LAB */
       order_id, status, order_total
FROM spm_orders_lab
WHERE customer_id = 501;
~~~

### Bước 3 — Tìm SQL_ID và plan hash

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    elapsed_time,
    buffer_gets,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%SPM_ROW436_LAB%'
ORDER BY last_active_time DESC;
~~~

### Bước 4 — Xem plan runtime

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_VALUE',
        0,
        'ALLSTATS LAST +OUTLINE +NOTE'
    )
);
~~~

Thay SQL_ID_VALUE và child number theo kết quả thực tế.

### Bước 5 — Load plan vào baseline

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
        sql_id => 'SQL_ID_VALUE',
        plan_hash_value => 1234567890,
        fixed => 'NO',
        enabled => 'YES'
    );
    DBMS_OUTPUT.PUT_LINE('Loaded=' || l_loaded);
END;
/
~~~

### Bước 6 — Kiểm tra baseline

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    plan_hash_value
FROM user_sql_plan_baselines
ORDER BY created DESC;
~~~

### Bước 7 — Xem plan đã lưu

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE'
    )
);
~~~

### Bước 8 — Chạy lại SQL và kiểm tra note

~~~sql
SELECT /* SPM_ROW436_LAB */
       order_id, status, order_total
FROM spm_orders_lab
WHERE customer_id = 501;
~~~

Sau đó gọi DBMS_XPLAN.DISPLAY_CURSOR để xem optimizer có sử dụng baseline không.

### Bước 9 — Dọn baseline và bảng lab (tùy chọn)

~~~sql
DECLARE
    l_dropped PLS_INTEGER;
BEGIN
    l_dropped := DBMS_SPM.DROP_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE'
    );
END;
/

DROP TABLE spm_orders_lab PURGE;
~~~

Chỉ drop đúng SQL handle thuộc lab. Nếu database dùng chung, không xóa baseline của ứng dụng khác.

## 28. Câu hỏi tự kiểm tra

1. SQL Plan Management giải quyết vấn đề gì?
2. SQL plan baseline là gì?
3. Plan history khác baseline thế nào?
4. ACCEPTED và ENABLED khác nhau ra sao?
5. FIXED có tác động gì đến plan selection?
6. REPRODUCED = NO cho biết điều gì?
7. AUTOPURGE có vai trò gì?
8. Baseline được lưu ở đâu?
9. OPTIMIZER_CAPTURE_SQL_PLAN_BASELINES khác OPTIMIZER_USE_SQL_PLAN_BASELINES thế nào?
10. Automatic capture có lưu mọi SQL không?
11. Khi nào nên capture plan từ cursor cache?
12. Vì sao phải kiểm tra child cursors và bind values trước khi capture?
13. DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE dùng để làm gì?
14. DBA_SQL_PLAN_BASELINES cung cấp thông tin gì?
15. DBMS_XPLAN.DISPLAY_CURSOR khác DISPLAY_SQL_PLAN_BASELINE thế nào?
16. Plan hash khác nhau có đủ kết luận regression không?
17. Evolve baseline làm gì?
18. Vì sao nên dùng COMMIT = NO khi xem thử evolve report?
19. Fixed plan có thể gây rủi ro gì?
20. Có thể load baseline từ nguồn nào ngoài cursor cache?
21. AWR và SQL Tuning Set có điều kiện licensing nào cần xét?
22. Pack/unpack baseline có đảm bảo plan reproduce ở database đích không?
23. Vì sao statistics vẫn cần được gather khi đã có baseline?
24. Bind peeking và Adaptive Cursor Sharing ảnh hưởng việc chọn plan thế nào?
25. Những nguyên nhân nào làm baseline không được dùng?
26. SQL Profile khác SQL Plan Baseline thế nào?
27. Khi nào nên dùng SQL Patch thay vì baseline?
28. Các metric nào nên so sánh để xác định regression?
29. Cùng plan hash nhưng elapsed time tăng có thể do đâu?
30. Quy trình rollback khi plan mới gây regression gồm những gì?

**Gợi ý trả lời:**

1. Quản lý plan đã biết để giảm nguy cơ plan change gây hồi quy.
2. Tập plan được chấp nhận cho một SQL statement.
3. History ghi nhận plan; baseline chứa các plan được accepted để optimizer xem xét.
4. Accepted là được chấp nhận; enabled là đang được phép dùng.
5. Fixed plan được ưu tiên theo quy tắc SPM so với non-fixed plans.
6. Optimizer không tái tạo được plan từ baseline trong môi trường hiện tại.
7. Cho phép baseline được dọn theo retention/SMB policy.
8. SQL Management Base trong SYSAUX.
9. Một tham số điều khiển capture; tham số kia điều khiển sử dụng baseline.
10. Không; capture có tiêu chí.
11. Khi plan vừa chạy đã được xác nhận tốt bằng runtime metrics và bind đại diện.
12. Vì cùng SQL có thể có nhiều plan/child và selectivity khác nhau.
13. Nạp plan đang có trong cursor cache vào SQL plan baseline.
14. SQL handle, plan name, origin, trạng thái, plan hash, cost và metadata.
15. DISPLAY_CURSOR xem runtime cursor plan; DISPLAY_SQL_PLAN_BASELINE xem plan đã lưu trong baseline.
16. Không; cần so sánh runtime metrics.
17. Đánh giá plan ứng viên chưa accepted để quyết định chấp nhận.
18. Để xem report trước khi commit thay đổi baseline.
19. Giữ plan lỗi thời và ngăn optimizer chọn plan mới tốt hơn.
20. AWR và SQL Tuning Set.
21. AWR/SQL Tuning features có thể yêu cầu Diagnostics/Tuning Pack; xác nhận license.
22. Không; khác schema, index, statistics, optimizer environment có thể làm plan không reproduce.
23. Statistics giúp optimizer ước lượng và chọn giữa các accepted plans, cũng cần cho SQL khác.
24. Bind values có thể tạo child cursors/plan khác theo selectivity.
25. Baseline use tắt, plan disabled/unaccepted, SQL không match hoặc plan không reproduce.
26. SQL Profile hỗ trợ cardinality estimates; baseline quản lý tập plan được phép.
27. Khi cần gắn optimizer hints cụ thể và đã hiểu tương tác với baseline.
28. Elapsed time, CPU, buffer gets, disk reads, rows, executions và latency distribution.
29. Resource contention, data growth, bind values, I/O, cache hoặc waits.
30. Disable plan mới, bật plan cũ, xác minh plan/runtime, ghi change record và theo dõi.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Tuning Guide — Managing SQL Plan Baselines](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/overview-of-sql-plan-management.html): kiến trúc và quy trình SPM.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_SPM](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SPM.html): API capture, evolve, alter, drop và transport baselines.
- [Oracle Database Reference — DBA_SQL_PLAN_BASELINES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SQL_PLAN_BASELINES.html): metadata SQL plan baseline.
- [Oracle Database SQL Tuning Guide — Evolving SQL Plan Baselines](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/evolving-sql-plan-baselines.html): verification và evolve.
- [Oracle Database SQL Tuning Guide — Capturing SQL Plan Baselines](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/capturing-sql-plan-baselines.html): automatic và manual capture.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): hiển thị cursor plan và baseline plan.
- [Oracle Database Reference — V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html): runtime cursor statistics.
- [Oracle Database SQL Tuning Guide — SQL Tuning Sets](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-sql-tuning-sets.html): quản lý SQL Tuning Set.

**Nguyên tắc cần nhớ:** SQL Plan Management giảm rủi ro hồi quy bằng cách quản lý tập plan đã được chấp nhận cho một SQL statement. Một plan chỉ có thể được dùng khi được bật, được chấp nhận và tái tạo được trong môi trường hiện tại. Hãy capture plan đã được xác nhận bằng runtime metrics và bind values đại diện; dùng evolve để đánh giá plan mới; chỉ fixed khi có lý do vận hành rõ ràng. Plan hash khác nhau không tự chứng minh regression, và baseline không thay thế statistics, SQL tuning hoặc kiểm tra resource. Sau mỗi thay đổi, xác nhận baseline metadata, plan thực tế bằng DBMS_XPLAN và hiệu năng trong workload production-like.
