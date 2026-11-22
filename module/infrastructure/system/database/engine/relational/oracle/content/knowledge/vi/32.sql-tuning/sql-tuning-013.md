# SQL Profile, SQL Patch, SQL Tuning Advisor và kiểm tra điều kiện giấy phép

## 1. Bối cảnh: xử lý SQL có execution plan chưa phù hợp

Khi một câu SQL chạy chậm, trước hết cần xác định nguyên nhân bằng SQL text, bind values, execution plan và số liệu runtime. Các nguyên nhân có thể gồm statistics thiếu hoặc cũ, cardinality estimate sai, access path không phù hợp, join order/join method chưa tốt, SQL viết chưa hợp lý hoặc plan thay đổi sau một lần triển khai.

Oracle cung cấp một số cơ chế hỗ trợ điều chỉnh cách optimizer xử lý câu SQL mà không nhất thiết phải sửa mã ứng dụng:

- **SQL Tuning Advisor** phân tích câu SQL và đưa ra khuyến nghị tuning.
- **SQL Profile** bổ sung thông tin thống kê riêng cho câu SQL để optimizer ước lượng cardinality/selectivity tốt hơn.
- **SQL Patch** gắn các optimizer hint với câu SQL để tác động đến quá trình tối ưu hóa.
- **SQL Plan Baseline** quản lý tập execution plan được chấp nhận nhằm kiểm soát plan regression.

Các cơ chế này có mục đích khác nhau. SQL Tuning Advisor là công cụ phân tích và đề xuất; SQL Profile và SQL Patch là các đối tượng được optimizer sử dụng khi tối ưu câu SQL; SQL Plan Baseline tập trung vào việc kiểm soát plan được phép sử dụng. Không nên coi chúng là các tên gọi khác nhau của cùng một tính năng.

## 2. SQL Profile

### 2.1. SQL Profile là gì?

SQL Profile là một database object chứa thông tin thống kê bổ sung dành cho một câu SQL. Có thể hình dung nó giống như statistics ở cấp câu truy vấn: optimizer sử dụng thông tin này cùng với object statistics, system statistics, bind values và môi trường hiện tại để ước lượng chi phí và chọn execution plan.

SQL Profile thường được SQL Tuning Advisor đề xuất khi quá trình phân tích cho thấy ước lượng của optimizer khác đáng kể so với số liệu thu được từ sampling hoặc thực thi một phần câu SQL. Profile có thể chứa các điều chỉnh cardinality để optimizer ước lượng số dòng phù hợp hơn.

Ví dụ, optimizer có thể ước lượng điều kiện kết hợp trên hai cột trả về 100 dòng, trong khi dữ liệu thực tế cho thấy khoảng 20.000 dòng. Nếu ước lượng thấp như vậy, optimizer có thể chọn nested loops và index access trong tình huống hash join hoặc full scan sẽ phù hợp hơn. SQL Profile có thể bổ sung thông tin giúp optimizer sửa ước lượng và cân nhắc lại plan.

### 2.2. SQL Profile không khóa cứng một execution plan

SQL Profile không phải là một chỉ thị bắt buộc optimizer phải dùng một plan hash cụ thể. Nó cung cấp thông tin thống kê phụ trợ; optimizer vẫn có thể chọn plan khác khi dữ liệu, index, statistics, bind values hoặc môi trường thay đổi.

Điểm này khác với SQL Plan Baseline. Profile chủ yếu sửa thông tin đầu vào cho optimizer; baseline kiểm soát các plan được chấp nhận. Nếu mục tiêu là cải thiện cardinality estimate, hãy xem xét Profile. Nếu mục tiêu là hạn chế plan regression và duy trì một plan đã kiểm chứng, hãy đánh giá SQL Plan Management.

### 2.3. Khi nào nên xem xét SQL Profile?

SQL Profile có thể hữu ích khi:

- SQL có sai lệch lớn giữa estimated rows và actual rows.
- Optimizer đánh giá sai selectivity của predicate hoặc cardinality sau join.
- Statistics thông thường đã được xem xét nhưng vẫn chưa mô tả tốt đặc điểm dữ liệu của câu SQL.
- Câu SQL có nhiều điều kiện tương quan, biểu thức phức tạp hoặc bind values khiến ước lượng khó chính xác.
- Advisor kiểm tra trên dữ liệu đại diện và đưa ra profile có kết quả tốt hơn trong phép thử.

Profile không thay thế việc sửa statistics ở cấp bảng/cột khi statistics nguồn đang thiếu hoặc stale. Nếu nguyên nhân là dữ liệu thay đổi nhưng chưa gather statistics, hãy xử lý nguồn statistics trước rồi đánh giá lại.

### 2.4. Xem SQL Profile hiện có

Các view thường dùng gồm `DBA_SQL_PROFILES` và `USER_SQL_PROFILES`:

```sql
SELECT name,
       category,
       status,
       force_matching,
       created,
       description
FROM dba_sql_profiles
ORDER BY created DESC;
```

`STATUS` cho biết Profile đang được bật hay tắt; `FORCE_MATCHING` cho biết phạm vi khớp SQL có chuẩn hóa literal hay không. Cần kiểm tra cả SQL text/signature và câu SQL thực tế mà Profile áp dụng, thay vì chỉ nhìn tên object.

## 3. SQL Patch

### 3.1. SQL Patch là gì?

SQL Patch là database object gắn một tập optimizer hint với một câu SQL được nhận diện bằng SQL text hoặc SQL_ID. Khi câu SQL phù hợp được parse, Oracle có thể áp dụng các hint từ patch như một phần thông tin tối ưu hóa.

SQL Patch hữu ích khi DBA cần tác động đến lựa chọn của optimizer mà không sửa câu SQL trong ứng dụng. Ví dụ, sau khi phân tích plan và thử nghiệm, DBA có thể muốn áp dụng một hint để thay đổi access path hoặc join method cho một câu SQL cụ thể.

SQL Patch cũng được SQL Repair Advisor sử dụng để đưa ra workaround cho một số lỗi nghiêm trọng khi compile hoặc execute SQL. Trong tình huống đó, patch có thể khiến optimizer chọn một execution plan khác để tránh lỗi. Mục đích này khác với SQL Tuning Advisor, vốn tập trung phân tích hiệu năng và đưa ra các khuyến nghị tuning.

### 3.2. SQL Patch khác SQL Profile như thế nào?

| Tiêu chí | SQL Profile | SQL Patch |
|---|---|---|
| Nội dung chính | Thông tin thống kê bổ sung, điều chỉnh estimate | Optimizer hint gắn với câu SQL |
| Mục tiêu | Cải thiện cardinality/selectivity estimate | Tác động trực tiếp đến quyết định tối ưu hóa bằng hint |
| Khóa một plan cụ thể? | Không | Không phải cơ chế quản lý plan ổn định tuyệt đối; hiệu quả phụ thuộc hint được áp dụng |
| Thay đổi SQL trong ứng dụng? | Không cần | Không cần |
| Cách tạo phổ biến | SQL Tuning Advisor đề xuất rồi DBA chấp nhận | Tạo bằng `DBMS_SQLDIAG.CREATE_SQL_PATCH` hoặc chấp nhận patch do SQL Repair Advisor đề xuất |

Nếu optimizer estimate sai, thêm hint bằng SQL Patch có thể che khuất nguyên nhân gốc và tạo plan kém phù hợp khi dữ liệu thay đổi. Trước khi tạo patch, cần xác định hint giải quyết vấn đề gì và thử trên workload đại diện.

### 3.3. Tạo SQL Patch thủ công

Oracle cung cấp `DBMS_SQLDIAG.CREATE_SQL_PATCH`, nhận SQL text hoặc SQL_ID cùng chuỗi hint:

```sql
DECLARE
  l_patch_name VARCHAR2(128);
BEGIN
  l_patch_name := DBMS_SQLDIAG.CREATE_SQL_PATCH(
    sql_id      => 'SQL_ID_HERE',
    hint_text   => 'FULL(o)',
    name        => 'PATCH_ORDERS_FULL',
    description => 'Test full scan for the target SQL',
    category    => 'DEFAULT',
    validate    => TRUE
  );

  DBMS_OUTPUT.PUT_LINE(l_patch_name);
END;
/
```

Đây là ví dụ minh họa: thay `SQL_ID_HERE` bằng SQL_ID thật và `o` bằng alias của bảng trong câu SQL. Hint phải tham chiếu đúng alias và query block. Nếu câu SQL có nhiều query block, cần kiểm tra tên query block và cách viết hint theo tài liệu Oracle/MOS tương ứng. `VALIDATE => TRUE` yêu cầu Oracle kiểm tra hint được cung cấp; việc tạo object thành công vẫn cần được theo dõi bằng execution plan để xác nhận hint thực sự có tác dụng.

Một cách khác là truyền `sql_text` thay vì `sql_id`:

```sql
DECLARE
  l_patch_name VARCHAR2(128);
BEGIN
  l_patch_name := DBMS_SQLDIAG.CREATE_SQL_PATCH(
    sql_text  => q'[
      SELECT o.order_id, o.amount
      FROM orders o
      WHERE o.customer_id = :customer_id
    ]',
    hint_text => 'INDEX(o IX_ORDERS_CUSTOMER)',
    name      => 'PATCH_ORDERS_CUSTOMER',
    validate  => TRUE
  );
END;
/
```

Tên index trong ví dụ phải tồn tại và alias `o` phải đúng với SQL thực tế. Không dùng hint chỉ dựa trên phỏng đoán; hãy xác nhận plan và số liệu runtime sau khi áp dụng.

### 3.4. Xem, tắt, bật và xóa SQL Patch

View `DBA_SQL_PATCHES` liệt kê các SQL Patch trong database:

```sql
SELECT name,
       category,
       status,
       force_matching,
       created,
       description
FROM dba_sql_patches
ORDER BY created DESC;
```

Có thể tắt một patch để kiểm tra tác động:

```sql
BEGIN
  DBMS_SQLDIAG.ALTER_SQL_PATCH(
    name            => 'PATCH_ORDERS_FULL',
    attribute_name  => 'STATUS',
    attribute_value => 'DISABLED'
  );
END;
/
```

Bật lại bằng `attribute_value => 'ENABLED'`. Khi không còn cần thiết, có thể xóa:

```sql
BEGIN
  DBMS_SQLDIAG.DROP_SQL_PATCH(
    name => 'PATCH_ORDERS_FULL'
  );
END;
/
```

Các thao tác thay đổi trạng thái hoặc xóa patch cần quyền quản trị phù hợp. Theo tài liệu package, `ALTER_SQL_PATCH` yêu cầu quyền `ALTER ANY SQL PATCH`; `DROP_SQL_PATCH` yêu cầu `DROP ANY SQL PATCH`. Package `DBMS_SQLDIAG` có security model yêu cầu role `ADVISOR`; quyền cụ thể còn tùy subprogram và thao tác.

### 3.5. Exact matching, force matching và category

SQL Patch gắn với định danh/signature của SQL text. Khi dùng `ACCEPT_SQL_PATCH` cho patch được SQL diagnosis task đề xuất, tham số `FORCE_MATCH` có thể yêu cầu chuẩn hóa literal thành bind variable để patch áp dụng cho các câu SQL có cấu trúc giống nhau sau chuẩn hóa. Khi `FALSE`, literal không được chuẩn hóa theo cách này.

Ví dụ, hai câu SQL:

```sql
SELECT * FROM orders WHERE customer_id = 1001;
SELECT * FROM orders WHERE customer_id = 1002;
```

có thể được xem xét theo matching khác nhau tùy lựa chọn exact/force matching. Force matching mở rộng phạm vi áp dụng, vì vậy có thể ảnh hưởng các giá trị bind/literal có selectivity khác nhau. Không bật force matching nếu chưa kiểm tra các nhóm dữ liệu và plan liên quan.

SQL Patch còn có `CATEGORY`. Session phải sử dụng category tương ứng thông qua tham số `SQLDIAGNOSE_CATEGORY` thì patch thuộc category đó mới được xét sử dụng. Category mặc định là `DEFAULT`. Hãy kiểm tra cấu hình session và category khi patch đã tồn tại nhưng plan không thay đổi.

Lưu ý: `CREATE_SQL_PATCH` và `ACCEPT_SQL_PATCH` có chữ ký tham số khác nhau. `FORCE_MATCH` được mô tả trong API `ACCEPT_SQL_PATCH`; không tự thêm tham số này vào ví dụ `CREATE_SQL_PATCH`.

## 4. SQL Tuning Advisor

### 4.1. Vai trò

SQL Tuning Advisor là công cụ phân tích SQL có tải cao và đưa ra khuyến nghị để cải thiện hiệu năng. Advisor sử dụng Automatic Tuning Optimizer để phân tích câu SQL và có thể đề xuất:

- Gather hoặc sửa statistics còn thiếu/stale.
- Tạo index phù hợp.
- Viết lại câu SQL.
- Tạo SQL Profile.
- Tạo SQL Plan Baseline hoặc đề xuất plan phù hợp trong các trường hợp được hỗ trợ.

Advisor trả về finding, lý do, lợi ích hiệu năng ước lượng và câu lệnh/API triển khai khuyến nghị. Khuyến nghị cần được DBA xem xét trước khi áp dụng, nhất là khi thay đổi ảnh hưởng đến nhiều ứng dụng hoặc nhiều nhóm bind values.

### 4.2. Nguồn đầu vào

SQL Tuning Advisor có thể phân tích SQL lấy từ nhiều nguồn, ví dụ:

- Shared SQL area/cursor cache.
- Automatic Database Diagnostic Monitor (ADDM).
- Automatic Workload Repository (AWR).
- SQL Tuning Set (STS).

Khi chọn nguồn đầu vào, cần hiểu cả điều kiện dữ liệu và điều kiện giấy phép của nguồn đó. AWR, ADDM và nhiều view lịch sử thuộc Oracle Diagnostics Pack; việc đọc dữ liệu này có yêu cầu license riêng. Không nên dùng AWR chỉ vì Advisor có khả năng nhận đầu vào từ AWR.

### 4.3. Tạo và chạy tuning task bằng DBMS_SQLTUNE

Ví dụ tạo task cho SQL_ID đang có trong cursor cache:

```sql
DECLARE
  l_task_name VARCHAR2(128);
BEGIN
  l_task_name := DBMS_SQLTUNE.CREATE_TUNING_TASK(
    sql_id     => 'SQL_ID_HERE',
    scope      => 'COMPREHENSIVE',
    time_limit => 300,
    task_name  => 'TUNE_ORDERS_SQL'
  );

  DBMS_SQLTUNE.EXECUTE_TUNING_TASK(
    task_name => l_task_name
  );
END;
/
```

Xem báo cáo:

```sql
SELECT DBMS_SQLTUNE.REPORT_TUNING_TASK(
         task_name => 'TUNE_ORDERS_SQL'
       ) AS report
FROM dual;
```

Task có thể mất thời gian tùy scope, thời gian giới hạn, độ phức tạp của SQL và nguồn dữ liệu. Nên chạy trên hệ thống thử nghiệm hoặc trong cửa sổ phù hợp khi workload production nhạy cảm.

### 4.4. Chấp nhận SQL Profile được Advisor đề xuất

Nếu báo cáo có SQL Profile finding và kết quả thử nghiệm cho thấy cải thiện phù hợp, DBA có thể chấp nhận Profile:

```sql
BEGIN
  DBMS_SQLTUNE.ACCEPT_SQL_PROFILE(
    task_name => 'TUNE_ORDERS_SQL',
    name      => 'PROFILE_ORDERS_SQL',
    replace   => TRUE
  );
END;
/
```

Không phải mọi task đều có đề xuất SQL Profile. Chỉ gọi `ACCEPT_SQL_PROFILE` khi task report có recommendation tương ứng. Với task chạy on-demand, DBA quyết định có chấp nhận hay không. Automatic SQL Tuning có thể được cấu hình chấp nhận Profile tự động theo tham số của maintenance task; cần kiểm tra chính sách hệ thống trước khi bật.

Khi cần loại bỏ Profile, có thể dùng:

```sql
BEGIN
  DBMS_SQLTUNE.DROP_SQL_PROFILE(
    name => 'PROFILE_ORDERS_SQL'
  );
END;
/
```

Việc xóa Profile cũng cần đánh giá tác động đến execution plan và workload trước khi thực hiện.

## 5. Phân biệt SQL Profile, SQL Patch và SQL Plan Baseline

Ba đối tượng có thể cùng ảnh hưởng đến cách optimizer chọn plan, nhưng giải quyết các bài toán khác nhau:

| Cơ chế | Thông tin lưu | Cách tác động | Khi nên xem xét |
|---|---|---|---|
| SQL Profile | Auxiliary statistics, cardinality adjustments | Cải thiện ước lượng của optimizer | Estimate sai dù statistics thông thường đã được xem xét |
| SQL Patch | Optimizer hints | Gắn hint với câu SQL | Cần thử một chỉ dẫn cụ thể mà không sửa SQL ứng dụng |
| SQL Plan Baseline | Các plan được chấp nhận và trạng thái plan | Kiểm soát plan optimizer được phép chọn | Cần hạn chế plan regression sau thay đổi môi trường |

Ví dụ, nếu optimizer chọn nested loops vì ước lượng số dòng quá thấp, SQL Profile có thể sửa estimate để optimizer tự chọn lại plan. Nếu đã xác định một hint cụ thể giải quyết vấn đề và muốn gắn hint với câu SQL, có thể xem xét SQL Patch. Nếu một plan đã được kiểm chứng và yêu cầu vận hành là tránh chuyển sang plan chưa được chấp nhận, SQL Plan Baseline phù hợp hơn.

Không nên chồng nhiều cơ chế lên cùng câu SQL mà không biết chúng tương tác ra sao. Khi có Profile, Patch và Baseline cùng tồn tại, cần xem execution plan thực tế, SQL management views và trạng thái từng object để hiểu optimizer đang sử dụng thông tin nào.

## 6. Kiểm tra điều kiện giấy phép Oracle

### 6.1. Xác định đúng edition và deployment

Quyền sử dụng phụ thuộc vào edition, cách triển khai và hợp đồng cụ thể. Oracle Database 19c Licensing Information phân biệt các nhóm như:

- **Standard Edition 2 (SE2):** bảng tính năng 19c không cho phép Oracle Tuning Pack.
- **Enterprise Edition (EE) và EE trên Engineered Systems (EE-ES) on-premises:** Oracle Tuning Pack là management pack tính phí bổ sung.
- **Một số dịch vụ Oracle Cloud:** tài liệu licensing có các gói Base Database Service EE/EE-HP/EE-EP và Exadata Database Service có Tuning Pack được bao gồm theo offering tương ứng.

Không suy luận quyền sử dụng chỉ từ việc package tồn tại trong database hoặc user có thể gọi API. Hãy xác định chính xác offering, vùng triển khai, license đã mua/BYOL và điều khoản hợp đồng đang áp dụng.

### 6.2. SQL Tuning Advisor và SQL Profile cần Tuning Pack

Oracle Database 19c Licensing Information liệt kê **SQL Tuning Advisor** và **SQL Profiles** trong các tính năng của Oracle Tuning Pack. Tài liệu cũng nêu Oracle Tuning Pack yêu cầu Oracle Diagnostics Pack.

Đối với EE/EE-ES on-premises, Tuning Pack là gói tính phí bổ sung; với một số dịch vụ cloud, quyền này có thể được bao gồm trong offering. Tài liệu cũng nêu mọi cách truy cập chức năng Tuning Pack, kể cả Enterprise Manager, command-line API hoặc truy cập dữ liệu nền, đều cần license Tuning Pack.

Do đó, không chỉ thao tác bấm nút trong Enterprise Manager mới bị tính là sử dụng Advisor/Profile. Gọi `DBMS_SQLTUNE`, bật Automatic SQL Tuning hoặc triển khai SQL Profile cũng phải được xem xét theo điều kiện license tương ứng.

### 6.3. SQL Patch cần được xác minh riêng

SQL Patch được Oracle mô tả trong tài liệu `DBMS_SQLDIAG` với các API như `CREATE_SQL_PATCH`, `ACCEPT_SQL_PATCH`, `ALTER_SQL_PATCH` và `DROP_SQL_PATCH`. Trong bảng tính năng Oracle Tuning Pack của tài liệu Licensing Information 19c, Oracle liệt kê SQL Tuning Advisor và SQL Profiles nhưng không liệt kê SQL Patch thành một mục riêng.

Không được suy ra từ việc SQL Patch không xuất hiện như một dòng riêng rằng mọi cách tạo, chấp nhận hoặc sử dụng patch đều được miễn license. Cần phân biệt thao tác tạo patch thủ công bằng API với việc chạy SQL Repair Advisor hoặc các công cụ quản trị có thể có điều kiện license khác. Khi triển khai thật, hãy xác nhận đường API và offering cụ thể với hợp đồng Oracle/Oracle License Management Services.

### 6.4. Diagnostics Pack và các nguồn dữ liệu lịch sử

Oracle Diagnostics Pack bao gồm các chức năng như AWR, ADDM và ASH. Nhiều view lịch sử `DBA_HIST_*` cũng thuộc Diagnostics Pack, ngoại trừ các view được tài liệu licensing nêu rõ là ngoại lệ.

Nếu SQL Tuning Advisor được chạy với SQL lấy từ AWR/ADDM hoặc người vận hành truy vấn dữ liệu thuộc Diagnostics Pack, cần có entitlement Diagnostics Pack. Vì Tuning Pack yêu cầu Diagnostics Pack, việc sử dụng Advisor/Profile trên on-premises EE thường cần cả hai gói.

### 6.5. CONTROL_MANAGEMENT_PACK_ACCESS không phải giấy phép

Tham số `CONTROL_MANAGEMENT_PACK_ACCESS` điều khiển việc bật/tắt chức năng Diagnostics Pack và Tuning Pack ở mức kỹ thuật:

| Giá trị | Ý nghĩa |
|---|---|
| `DIAGNOSTIC+TUNING` | Cho phép chức năng Diagnostics Pack và Tuning Pack được bật trong database |
| `DIAGNOSTIC` | Chỉ bật chức năng Diagnostics Pack |
| `NONE` | Tắt cả Diagnostics Pack và Tuning Pack |

Có thể xem giá trị hiện tại:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'control_management_pack_access';
```

Tham số này chỉ là cơ chế kiểm soát truy cập kỹ thuật. Giá trị `DIAGNOSTIC+TUNING` không chứng minh tổ chức đã mua license; ngược lại, đặt `NONE` cũng không tự thay đổi điều khoản hợp đồng. DBA cần cấu hình tham số phù hợp với entitlement và chính sách vận hành.

### 6.6. Feature Usage Statistics không phải bằng chứng entitlement

Oracle cung cấp script `options_packs_usage_statistics.sql` để xem thông tin feature, option và management pack được phát hiện là đã sử dụng. Tài liệu Licensing Information ghi rõ kết quả script chỉ mang tính thông tin và **không đại diện cho entitlement hoặc yêu cầu license**.

Vì vậy, không dùng một báo cáo usage hoặc trạng thái tham số để tự kết luận tổ chức có hay không có quyền sử dụng. Khi có nghi vấn, đối chiếu hợp đồng, đơn hàng license, offering cloud và tài liệu licensing đúng phiên bản; liên hệ Oracle License Management Services hoặc đại diện Oracle khi cần xác nhận chính thức.

## 7. Phân biệt SQL Patch với bản vá phần mềm Oracle

Thuật ngữ “SQL Patch” dễ bị nhầm với bản vá phần mềm cài bằng OPatch/datapatch.

| Thuật ngữ | Ý nghĩa |
|---|---|
| SQL Patch (`DBMS_SQLDIAG`) | Object chứa hint gắn với câu SQL, ảnh hưởng đến optimizer |
| Oracle software patch | Bản vá cho Oracle Home/database binaries và SQL scripts, được cài theo quy trình patching |
| `DBA_SQL_PATCHES` | View liệt kê optimizer SQL Patch objects |
| `DBA_REGISTRY_SQLPATCH` | View ghi nhận các lần áp dụng/rollback SQL patch scripts bằng datapatch sau OPatch |

Ví dụ, `DBA_SQL_PATCHES` dùng để kiểm tra patch optimizer:

```sql
SELECT name, category, status, created
FROM dba_sql_patches
ORDER BY created DESC;
```

Trong khi đó, `DBA_REGISTRY_SQLPATCH` ghi nhận lịch sử cài đặt software patch:

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Hai view có tên gần giống nhưng phục vụ hai mục đích khác nhau. Không dùng `DBA_REGISTRY_SQLPATCH` để tìm optimizer hint patch của một SQL_ID.

## 8. Quy trình sử dụng an toàn trong môi trường thật

1. Thu thập SQL_ID, SQL text, bind values đại diện và child cursor/plan hash liên quan.
2. Dùng `DBMS_XPLAN.DISPLAY_CURSOR` với runtime statistics để xác định sai lệch estimated rows/actual rows, operation tốn buffer gets hoặc thời gian.
3. Kiểm tra table/index statistics, extended statistics, histogram, index, SQL text và môi trường optimizer trước khi áp dụng đối tượng SQL management.
4. Nếu cần phân tích tự động và đã xác nhận entitlement, chạy SQL Tuning Advisor; đọc report, rationale và benefit ước lượng.
5. Nếu Advisor đề xuất SQL Profile, kiểm tra trên workload đại diện và chấp nhận khi estimate được cải thiện mà không tạo regression cho nhóm bind values khác.
6. Nếu cần áp dụng hint cụ thể, đánh giá SQL Patch; xác định đúng SQL signature, alias/query block, category và phạm vi force matching.
7. Nếu mục tiêu là ổn định plan đã kiểm chứng, xem xét SQL Plan Baseline thay vì dùng Profile/Patch như một cách khóa plan.
8. Ghi lại người tạo, lý do, SQL_ID/signature, tên object, category, plan trước/sau, ngày triển khai và phương án rollback.
9. Theo dõi sau triển khai; tắt hoặc xóa Profile/Patch khi không còn cần thiết hoặc khi plan regression xuất hiện.
10. Kiểm tra entitlement trước khi sử dụng Advisor, Profile, AWR/ADDM/ASH hoặc API liên quan. Không coi tham số database hay báo cáo feature usage là giấy phép.

## 9. Checklist kiểm tra trước khi triển khai

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Đã xác định đúng SQL_ID và SQL text chưa? | Tránh áp dụng nhầm SQL hoặc nhiều câu SQL cùng chức năng |
| Đã có execution plan và runtime statistics chưa? | Có baseline đo lường trước thay đổi |
| Vấn đề là estimate, hint hay plan regression? | Chọn Profile, Patch hoặc Baseline đúng mục tiêu |
| Đã kiểm tra nhiều bind values chưa? | Tránh tối ưu cho một giá trị nhưng làm chậm nhóm khác |
| Patch có đúng query block/table alias không? | Hint phải thực sự được nhận diện và áp dụng |
| Category và force matching có phù hợp không? | Tránh áp dụng quá rộng hoặc không được session sử dụng |
| Có cách rollback không? | Biết cách disable/drop object và kiểm tra lại plan |
| Đã xác minh edition, cloud offering và license chưa? | Không dùng feature dựa trên việc API có thể gọi được |
| Có dùng AWR/ADDM/ASH hoặc SQL Tuning Advisor không? | Kiểm tra Diagnostics Pack/Tuning Pack tương ứng |

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Licensing Information — Management Packs and permitted features](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html)
- [Oracle Database 19c SQL Tuning Guide — Analyzing SQL with SQL Tuning Advisor](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/sql-tuning-advisor.html)
- [Oracle Database 19c SQL Tuning Guide — Managing SQL Profiles](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-sql-profiles.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SQLDIAG](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQLDIAG.html)
- [Oracle Database 19c Database Reference — DBA_SQL_PATCHES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SQL_PATCHES.html)
- [Oracle Database 19c Database Reference — DBA_REGISTRY_SQLPATCH](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_REGISTRY_SQLPATCH.html)
