# DBMS_STATS: thu thập thống kê theo bảng, schema hoặc database

Oracle Database Cost-Based Optimizer (CBO) dùng thống kê để ước lượng số hàng, độ chọn lọc của điều kiện lọc, cardinality của phép join, chi phí truy cập index và chi phí thực thi các bước trong SQL statement. Package **DBMS_STATS** cung cấp API để thu thập, quản lý, sao lưu, khôi phục và kiểm soát thống kê optimizer.

Thống kê không làm thay đổi dữ liệu nghiệp vụ trong bảng. Chúng mô tả đặc điểm dữ liệu tại một thời điểm, chẳng hạn số hàng, số block, số giá trị phân biệt, phân bố giá trị cột, histogram và thống kê index. Khi dữ liệu thay đổi đáng kể, thống kê có thể trở nên cũ; optimizer khi đó có thể chọn execution plan không còn phù hợp.

DBMS_STATS cho phép thu thập ở nhiều phạm vi:

- **Bảng:** chỉ cập nhật thống kê cho một table, các partition hoặc index liên quan.
- **Schema:** xử lý nhiều table/index thuộc một schema.
- **Database:** thu thập thống kê trên phạm vi toàn database theo lựa chọn.

Chọn phạm vi nhỏ nhất đủ đáp ứng nhu cầu, đặt sampling và histogram phù hợp với phân bố dữ liệu, rồi kiểm tra kết quả trước khi kết luận hiệu năng đã cải thiện. Không nên chạy gather toàn database chỉ vì một câu SQL chậm.

Bài học thuộc chủ đề **Bộ tối ưu và thống kê** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Vai trò của optimizer statistics và DBMS_STATS.
- Thu thập thống kê theo bảng, schema và database.
- Sampling, histogram, index statistics, degree và partition granularity.
- Phân biệt GATHER, GATHER STALE và GATHER AUTO.
- Stale statistics, automatic statistics gathering và preferences.
- Khóa, pending statistics, export/import và restore.
- Giám sát bằng data dictionary và kiểm soát thay đổi execution plan.
- Bài thực hành SQL/PLSQL và lỗi thường gặp.

## 1. Optimizer statistics là gì?

Optimizer statistics là metadata mô tả bảng, cột, index và một số thành phần hệ thống. CBO dùng các thông tin này để ước lượng chi phí của những phương án thực thi SQL.

Ví dụ một truy vấn:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 1001;
~~~

Optimizer cần ước lượng:

- Bảng ORDERS có bao nhiêu hàng?
- CUSTOMER_ID có bao nhiêu giá trị khác nhau?
- Một khách hàng thường có bao nhiêu đơn hàng?
- Phân bố CUSTOMER_ID có đều hay bị lệch?
- Có index phù hợp không, và index đó có chọn lọc đủ tốt không?
- Đọc index rồi truy cập table có rẻ hơn full table scan không?

Nếu thống kê cho rằng CUSTOMER_ID có phân bố đồng đều trong khi thực tế một số khách hàng có lượng đơn rất lớn, optimizer có thể đánh giá sai cardinality và chọn plan không tối ưu.

### Các nhóm thống kê chính

| Nhóm | Thông tin thường gặp | Tác dụng |
| --- | --- | --- |
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Ước lượng kích thước bảng và số hàng. |
| Column statistics | NUM_DISTINCT, NUM_NULLS, LOW_VALUE, HIGH_VALUE, density | Ước lượng selectivity của predicate. |
| Histogram | Phân bố tần suất hoặc bucket của giá trị cột | Mô tả dữ liệu skew, giúp ước lượng predicate cụ thể. |
| Index statistics | BLEVEL, LEAF_BLOCKS, DISTINCT_KEYS, CLUSTERING_FACTOR | Ước lượng chi phí truy cập index và table. |
| Partition statistics | Thống kê từng partition/subpartition và global | Hỗ trợ partition pruning và ước lượng truy vấn partitioned table. |
| System statistics | CPU/I/O characteristics | Hỗ trợ mô hình chi phí phần cứng và I/O. |
| Fixed object statistics | Thống kê các dynamic performance/fixed tables | Giúp optimizer lập plan cho truy vấn dictionary/fixed objects. |

### Thống kê không phải dữ liệu thực tế

NUM_ROWS có thể khác số hàng hiện tại nếu thống kê chưa được cập nhật. Giá trị LOW_VALUE/HIGH_VALUE là thông tin thống kê, không phải ràng buộc dữ liệu. Histogram mô tả phân bố tại lúc thu thập; nó không tự cập nhật theo từng INSERT.

Thống kê có thể bị stale hoặc không còn đại diện cho workload hiện tại. Vì vậy, luôn xem thời điểm thu thập, số thay đổi kể từ đó và đặc điểm dữ liệu.

## 2. DBMS_STATS và các API chính

DBMS_STATS là package PL/SQL do Oracle cung cấp để quản lý optimizer statistics. Các thủ tục thường dùng:

| API | Phạm vi |
| --- | --- |
| GATHER_TABLE_STATS | Một bảng, có thể chỉ định partition/subpartition. |
| GATHER_SCHEMA_STATS | Các object thuộc một schema. |
| GATHER_DATABASE_STATS | Phạm vi database. |
| GATHER_DICTIONARY_STATS | Dictionary objects. |
| GATHER_FIXED_OBJECTS_STATS | Fixed tables/dynamic performance views. |
| GATHER_SYSTEM_STATS | Thống kê đặc điểm CPU/I/O của hệ thống. |
| EXPORT_TABLE_STATS / IMPORT_TABLE_STATS | Sao lưu/nhập thống kê một bảng. |
| EXPORT_SCHEMA_STATS / IMPORT_SCHEMA_STATS | Sao lưu/nhập thống kê schema. |
| RESTORE_TABLE_STATS | Khôi phục thống kê bảng từ history nếu còn retention. |

DBMS_STATS nên được ưu tiên thay cho lệnh ANALYZE ... COMPUTE/ESTIMATE STATISTICS trong quản lý optimizer statistics thông thường. ANALYZE vẫn có một số mục đích khác như VALIDATE STRUCTURE, nhưng không nên dùng nó làm quy trình gather stats thay thế DBMS_STATS.

### Quyền thực thi

Schema có thể thu thập thống kê trên object của chính mình theo quyền phù hợp. Thu thập cho schema khác hoặc toàn database thường cần quyền quản trị/privilege thích hợp. Trong môi trường production, giao thao tác rộng cho DBA hoặc job vận hành được kiểm soát; không cấp quyền quản trị chỉ để một ứng dụng chạy gather stats tùy ý.

### Xem package và tham số theo phiên bản

Chữ ký API, default và một số option có thể thay đổi giữa Oracle releases. Có thể xem tài liệu package trong database:

~~~sql
DESC DBMS_STATS
~~~

Hoặc truy vấn ALL_ARGUMENTS/DBA_ARGUMENTS khi cần xác nhận tên, kiểu và thứ tự tham số. Luôn dùng tài liệu đúng phiên bản database đang chạy trước khi đưa lệnh vào deployment script.

## 3. Thu thập thống kê cho một bảng

GATHER_TABLE_STATS là API phù hợp khi một bảng cụ thể vừa được nạp nhiều dữ liệu, thay đổi phân bố hoặc cần cập nhật thống kê sau một thao tác bảo trì.

Cú pháp ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'SALES',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Các tham số quan trọng:

- `ownname`: owner/schema chứa bảng; tên object thường được truyền dạng chữ hoa nếu được tạo không có quoted identifier.
- `tabname`: tên bảng.
- `estimate_percent`: tỷ lệ sample; AUTO_SAMPLE_SIZE để Oracle tự chọn.
- `method_opt`: chính sách thu thập column statistics và histogram.
- `cascade`: có thu thập index statistics liên quan hay không; AUTO_CASCADE để Oracle quyết định.
- `degree`: mức parallelism; AUTO_DEGREE để Oracle tự quyết định.
- `no_invalidate`: cách xử lý cursor phụ thuộc khi statistics thay đổi; AUTO_INVALIDATE để Oracle quản lý thời điểm invalidation.

Không cần đặt mọi tham số trong mỗi lệnh. Với phần lớn trường hợp, bắt đầu bằng AUTO_SAMPLE_SIZE, method_opt có SIZE AUTO, và để Oracle tự quản lý cascade/degree/invalidation theo chính sách.

### Thu thập một bảng trong schema hiện tại

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => TRUE
    );
END;
/
~~~

CASCADE TRUE yêu cầu thu thập index statistics cùng bảng. Nếu bảng có nhiều index hoặc workload đang nhạy cảm với tài nguyên, cân nhắc để AUTO_CASCADE hoặc thu thập có chủ đích.

### Thu thập một partition

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        partname => 'P_2026_10',
        granularity => 'PARTITION',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

PARTNAME chỉ định partition; GRANULARITY điều khiển loại thống kê partition/global được thu thập. Với partitioned table, chọn granularity theo workload và cách optimizer sử dụng global/partition statistics. Không giả định gather một partition sẽ tự động tạo đầy đủ mọi thống kê global cần thiết trong mọi cấu hình.

### Thu thập lại sau bulk load

Sau khi nạp một lượng lớn dữ liệu vào bảng, thống kê cũ có thể không còn đại diện. Có thể chạy gather cho bảng sau khi load hoàn tất:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'STAGING',
        tabname => 'FACT_SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Nếu load theo partition, cân nhắc incremental statistics và gather partition phù hợp thay vì quét toàn bộ bảng rất lớn.

## 4. Thu thập thống kê theo schema

GATHER_SCHEMA_STATS thu thập thống kê cho các bảng và object thống kê liên quan trong một schema. Đây là lựa chọn khi nhiều bảng trong cùng schema vừa được nạp dữ liệu, thay đổi đáng kể hoặc cần cập nhật theo một lịch bảo trì.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        options          => 'GATHER AUTO',
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

### Tham số quan trọng

- OWNNAME: schema cần thu thập; không phải tên database.
- ESTIMATE_PERCENT: sampling cho các table statistics; AUTO_SAMPLE_SIZE để Oracle chọn.
- METHOD_OPT: chính sách column statistics và histogram.
- CASCADE: có thu thập index statistics cùng table hay không.
- DEGREE: parallelism cho công việc gather.
- OPTIONS: phạm vi object được chọn, chẳng hạn GATHER, GATHER STALE, GATHER EMPTY hoặc GATHER AUTO.
- NO_INVALIDATE: chính sách invalidation cursor sau khi statistics thay đổi.

GATHER_SCHEMA_STATS không có nghĩa là tạo một bản snapshot schema hoặc thu thập mọi metadata trong dictionary. Nó xử lý các object thống kê thuộc schema theo lựa chọn và trạng thái hiện tại.

### Thu thập toàn bộ object cần thiết trong schema

Nếu muốn gather mọi table trong schema, dùng OPTIONS => 'GATHER':

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => DBMS_STATS.AUTO_CASCADE,
        options => 'GATHER'
    );
END;
/
~~~

Lệnh này có thể tốn tài nguyên nếu schema lớn. Trước khi chạy, xem số lượng bảng, partition, dung lượng dữ liệu và khung giờ bảo trì.

### Chỉ xử lý object stale hoặc thiếu thống kê

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        options => 'GATHER AUTO'
    );
END;
/
~~~

GATHER AUTO để Oracle chọn các object cần gather theo trạng thái thống kê. GATHER STALE chỉ nhắm các object được xác định là stale; GATHER EMPTY nhắm các object chưa có thống kê. Chọn options theo mục tiêu thay vì luôn gather toàn bộ.

### Thu thập schema hiện tại

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => USER,
        options => 'GATHER AUTO'
    );
END;
/
~~~

USER trả về tên schema hiện tại. Với stored procedure hoặc job chạy dưới owner khác, xác nhận effective user và quyền trước khi dùng.

## 5. Thu thập thống kê toàn database

GATHER_DATABASE_STATS có phạm vi rộng, phù hợp với kế hoạch quản trị database hoặc sau thay đổi lớn trên nhiều schema. Đây không phải lựa chọn mặc định cho một bảng có vấn đề.

~~~sql
BEGIN
    DBMS_STATS.GATHER_DATABASE_STATS(
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.AUTO_DEGREE,
        options          => 'GATHER AUTO',
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Database-wide gathering có thể đọc lượng dữ liệu lớn, tiêu thụ CPU/I/O và ảnh hưởng workload đang chạy. Thực hiện trong maintenance window, theo dõi thời gian và tài nguyên, đồng thời xác định rõ phạm vi object được xử lý.

### Khi nào dùng GATHER_DATABASE_STATS?

- Sau một đợt migration hoặc bulk load ảnh hưởng nhiều schema.
- Khi triển khai database mới và cần thu thập thống kê trên phạm vi rộng.
- Theo kế hoạch quản trị đã kiểm thử, có cửa sổ bảo trì phù hợp.
- Khi DBA cần đồng bộ trạng thái thống kê của nhiều schema sau thay đổi hạ tầng hoặc dữ liệu lớn.

Không chạy database gather theo phản xạ khi một SQL statement chậm. Trước hết kiểm tra plan, thống kê của bảng liên quan và dữ liệu thay đổi.

### GATHER_DICTIONARY_STATS

Thống kê dictionary phục vụ truy vấn các object thuộc data dictionary. Oracle có thủ tục riêng:

~~~sql
BEGIN
    DBMS_STATS.GATHER_DICTIONARY_STATS;
END;
/
~~~

Đây là công việc quản trị, thường được thực hiện theo khuyến nghị của Oracle hoặc sau thay đổi lớn ảnh hưởng dictionary. Không thay thế bằng việc tự gather tùy tiện các bảng SYS.

### GATHER_FIXED_OBJECTS_STATS

Fixed tables là các cấu trúc nội bộ được truy cập qua dynamic performance views, thường có tên V$. Có API riêng:

~~~sql
BEGIN
    DBMS_STATS.GATHER_FIXED_OBJECTS_STATS;
END;
/
~~~

Thống kê fixed objects nên được thu thập khi workload đại diện đã chạy, vì số liệu hoạt động và số hàng quan sát được có thể thay đổi theo giai đoạn vận hành. Không nhất thiết chạy ngay khi database vừa khởi động với workload gần như bằng không.

### GATHER_SYSTEM_STATS

System statistics mô tả đặc điểm CPU/I/O mà optimizer dùng trong mô hình chi phí. Thu thập hoặc thiết lập system statistics là thao tác chuyên biệt; chỉ thực hiện theo quy trình DBA, với workload đại diện và hiểu rõ chế độ NOWORKLOAD/WORKLOAD theo phiên bản. Không nhầm system stats với table stats.

## 6. Chọn phạm vi gather

| Tình huống | API thường phù hợp | Lưu ý |
| --- | --- | --- |
| Một bảng vừa bulk load | GATHER_TABLE_STATS | Có thể gather index và partition liên quan. |
| Một partition vừa được nạp | GATHER_TABLE_STATS với PARTNAME | Chọn GRANULARITY và incremental stats. |
| Nhiều bảng trong một schema stale | GATHER_SCHEMA_STATS với GATHER STALE/AUTO | Tránh quét các schema không liên quan. |
| Nhiều schema sau migration lớn | GATHER_DATABASE_STATS | Cần maintenance window và theo dõi tài nguyên. |
| Truy vấn dictionary chậm sau thay đổi lớn | GATHER_DICTIONARY_STATS | Là công việc DBA. |
| Truy vấn V$ và fixed objects cần thống kê | GATHER_FIXED_OBJECTS_STATS | Thu thập khi workload đại diện đã hoạt động. |
| Optimizer cost model cần điều chỉnh theo phần cứng | GATHER_SYSTEM_STATS | Cần quy trình đo và DBA đánh giá. |

Một quy trình tốt thường bắt đầu từ object cụ thể trong execution plan, kiểm tra stale/missing statistics, rồi mới mở rộng phạm vi khi có bằng chứng.

## 7. Sampling, estimate_percent và method_opt

Thu thập thống kê có thể đọc toàn bộ dữ liệu hoặc dùng sampling. DBMS_STATS cung cấp AUTO_SAMPLE_SIZE để Oracle chọn cách lấy mẫu phù hợp. Trong phần lớn trường hợp, đây là lựa chọn tốt để bắt đầu; không cần tự đặt một tỷ lệ nhỏ chỉ để gather chạy nhanh.

### ESTIMATE_PERCENT

- AUTO_SAMPLE_SIZE: Oracle tự chọn phương pháp/kích thước sample nhằm tạo thống kê phù hợp.
- Một số cụ thể từ 0 đến 100: yêu cầu tỷ lệ sample do người vận hành chọn.
- NULL trong các API có thể có semantics riêng theo phiên bản; kiểm tra tài liệu thay vì tự suy diễn.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
~~~

Sample quá nhỏ có thể bỏ sót giá trị hiếm hoặc phân bố lệch, dẫn đến cardinality estimate sai. Sample 100% không mặc nhiên là tốt nhất: nó có thể tốn I/O/CPU hơn nhiều mà không tạo khác biệt đáng kể cho plan. Hãy đo và dùng AUTO_SAMPLE_SIZE trước khi can thiệp.

### BLOCK_SAMPLE

BLOCK_SAMPLE điều khiển lấy mẫu theo block thay vì theo hàng. Sampling theo block có thể nhanh hơn trong một số trường hợp nhưng nếu dữ liệu được sắp xếp theo block, mẫu có thể không đại diện tốt cho toàn bộ phân bố. Không bật chỉ vì muốn giảm thời gian gather; cân nhắc layout và tính phân bố dữ liệu.

### METHOD_OPT và histogram

METHOD_OPT xác định cột nào nhận column statistics và histogram:

~~~sql
method_opt => 'FOR ALL COLUMNS SIZE AUTO'
~~~

SIZE AUTO để Oracle quyết định cột nào cần histogram dựa trên thông tin workload/usage và đặc điểm dữ liệu. Đây thường là lựa chọn hợp lý hơn việc tạo histogram cho mọi cột.

Một số dạng:

- FOR ALL COLUMNS SIZE 1: thu thập column stats mà không tạo histogram.
- FOR ALL COLUMNS SIZE AUTO: Oracle tự quyết định histogram.
- FOR COLUMNS SIZE 254 STATUS: chỉ định histogram cho cột STATUS với số bucket tối đa yêu cầu.
- FOR COLUMNS SIZE REPEAT STATUS: lặp lại lựa chọn histogram trước đó cho cột theo semantics của phiên bản.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

### Histogram dùng để làm gì?

Giả sử ORDERS.STATUS có 90% hàng là CLOSED và 10% là OPEN. Nếu optimizer giả định phân bố đồng đều giữa các giá trị, nó có thể ước lượng sai số hàng cho:

~~~sql
SELECT *
FROM orders
WHERE status = 'OPEN';
~~~

Histogram cung cấp thông tin về phân bố giá trị để optimizer ước lượng predicate cụ thể tốt hơn. Các loại histogram phổ biến gồm frequency, top-frequency, height-balanced và hybrid; loại được tạo phụ thuộc phiên bản, số distinct values, sample và cách Oracle quyết định.

### Không tạo histogram hàng loạt một cách máy móc

Histogram có thể giúp một số query nhưng cũng làm optimizer chọn plan khác nhau theo literal/bind value, ảnh hưởng adaptive cursor sharing và độ ổn định plan. Histogram không cần thiết cho mọi cột, đặc biệt cột có phân bố đều hoặc không được dùng trong predicate quan trọng.

Ưu tiên SIZE AUTO, theo dõi workload và chỉ đặt histogram thủ công khi đã chứng minh phân bố skew và query cần thông tin đó.

### Column usage và workload

Oracle có thể ghi nhận cách cột được dùng trong predicate/join/grouping để hỗ trợ quyết định histogram với SIZE AUTO. Thu thập stats ngay sau khi tạo bảng nhưng trước khi workload chạy có thể chưa có đủ thông tin usage. Với hệ thống mới, chạy workload đại diện trước khi gather lại nếu cần histogram theo usage.

## 8. Index statistics, cascade và granularity

### CASCADE

CASCADE xác định có thu thập thống kê cho các index liên quan khi gather table stats hay không:

- TRUE: gather index stats cùng table.
- FALSE: không yêu cầu gather index stats.
- DBMS_STATS.AUTO_CASCADE: để Oracle quyết định theo chính sách.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        cascade => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

Index stats như LEAF_BLOCKS, BLEVEL, DISTINCT_KEYS và CLUSTERING_FACTOR ảnh hưởng ước lượng chi phí index access. Nếu index vừa rebuild hoặc dữ liệu thay đổi nhiều, xem xét gather lại table/index stats theo phạm vi cần thiết.

### DEGREE

DEGREE điều khiển parallelism trong quá trình gather. Có thể chỉ định số cụ thể, DEFAULT hoặc AUTO_DEGREE tùy phiên bản. Parallel gather giảm thời gian trong một số workload nhưng tăng cạnh tranh CPU/I/O và có thể ảnh hưởng query production.

Không đặt degree thật lớn mà không đo tải. Nếu gather chạy trong maintenance window, cân nhắc mức parallelism theo tài nguyên còn trống và giới hạn Resource Manager.

### GRANULARITY với partitioned table

Các lựa chọn granularity có thể gồm:

- AUTO: Oracle chọn mức phù hợp.
- GLOBAL: chỉ global statistics.
- PARTITION: thống kê từng partition.
- SUBPARTITION: thống kê từng subpartition.
- GLOBAL AND PARTITION: cả global và partition statistics.
- ALL: tất cả mức phù hợp, bao gồm subpartition trong các trường hợp được hỗ trợ.

Tên option và hành vi chi tiết phụ thuộc loại partitioning/version; kiểm tra package docs. Với bảng partitioned lớn, global stats và partition stats phục vụ những kiểu truy vấn khác nhau. Query lọc theo partition key có thể hưởng lợi từ partition stats; query truy cập nhiều partition có thể cần global stats.

### INCREMENTAL statistics

Với partitioned table lớn, incremental statistics có thể giảm chi phí duy trì global statistics bằng cách dùng synopses cho partition. Cấu hình ở table preference:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'FACT_SALES',
        pname => 'INCREMENTAL',
        pvalue => 'TRUE'
    );
END;
/
~~~

Khi bật incremental, gather partition có thể cập nhật synopses và hỗ trợ tính global stats mà không phải scan lại mọi partition. Hiệu quả phụ thuộc partitioning, loại thống kê, phiên bản Oracle và cách load dữ liệu. Kiểm tra thêm INCREMENTAL_LEVEL, INCREMENTAL_STALENESS và preference liên quan nếu cần.

## 9. GATHER, GATHER STALE, GATHER EMPTY và GATHER AUTO

Các giá trị OPTIONS của GATHER_SCHEMA_STATS/GATHER_DATABASE_STATS giúp chọn object cần thu thập:

| OPTIONS | Ý nghĩa khái quát |
| --- | --- |
| GATHER | Thu thập thống kê cho phạm vi object được chỉ định, kể cả object đã có stats. |
| GATHER STALE | Chọn object có thống kê được xác định là stale. |
| GATHER EMPTY | Chọn object chưa có thống kê. |
| GATHER AUTO | Để Oracle chọn object cần gather, bao gồm trường hợp stale/empty theo quy tắc của API. |

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => 'SALES',
        options => 'GATHER STALE'
    );
END;
/
~~~

GATHER STALE hữu ích cho công việc định kỳ hoặc sau khi nhiều bảng thay đổi. GATHER EMPTY hữu ích khi khởi tạo thống kê cho object chưa có stats. GATHER AUTO là lựa chọn tự động thường dùng cho maintenance; vẫn phải theo dõi thời gian và phạm vi thực tế.

### GATHER_TABLE_STATS không dùng OPTIONS giống schema/database

Đừng sao chép tham số OPTIONS từ GATHER_SCHEMA_STATS sang GATHER_TABLE_STATS nếu chữ ký API không hỗ trợ. Với một bảng cụ thể, gọi GATHER_TABLE_STATS trực tiếp. Muốn kiểm tra trạng thái stale trước, đọc dictionary views hoặc để schema/database gather chọn object.

### GATHER AUTO không có nghĩa mọi thứ đều được gather

Oracle có thể bỏ qua object không cần thu thập hoặc bị khóa stats. Không kết luận gather thất bại chỉ vì một số bảng không có LAST_ANALYZED mới. Xem output operation, object status, preferences và trạng thái lock.

## 10. Stale statistics và theo dõi thay đổi dữ liệu

Statistics được xem là stale khi dữ liệu đã thay đổi đủ nhiều kể từ lần thu thập gần nhất theo ngưỡng/policy của Oracle. Thống kê stale không đồng nghĩa chắc chắn sai; đó là tín hiệu để cân nhắc thu thập lại.

Oracle theo dõi thay đổi DML trên các bảng được monitoring. Các thông tin insert/update/delete được ghi nhận và có thể được xem qua DBA_TAB_MODIFICATIONS hoặc USER_TAB_MODIFICATIONS tùy quyền.

### Xem thời điểm và trạng thái thống kê bảng

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
ORDER BY table_name;
~~~

STALE_STATS và STATTYPE_LOCKED có thể có giá trị NULL hoặc khác nhau tùy object, partition và phiên bản. Với schema khác, dùng ALL_TAB_STATISTICS/DBA_TAB_STATISTICS.

### Xem số thay đổi DML được ghi nhận

~~~sql
SELECT table_name,
       inserts,
       updates,
       deletes,
       timestamp,
       truncated,
       drop_segments
FROM user_tab_modifications
ORDER BY timestamp DESC;
~~~

View này cung cấp thông tin thay đổi kể từ lần gather stats gần nhất theo cơ chế monitoring. Số liệu có thể chưa được phản ánh tức thì trong view; Oracle tổng hợp thông tin monitoring theo cơ chế nội bộ.

Nếu cần flush thông tin monitoring để kiểm tra:

~~~sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

Thủ tục này đẩy thông tin monitoring trong bộ nhớ vào dictionary views. Đây là thao tác hỗ trợ quan sát, không phải gather stats và không cập nhật NUM_ROWS/HISTOGRAM.

### Ngưỡng STALE_PERCENT

DBMS_STATS có table preference STALE_PERCENT để điều chỉnh ngưỡng thay đổi khiến statistics được coi là stale. Mặc định thường là 10% trong các cấu hình phổ biến, nhưng có thể được thay đổi ở cấp table/schema/global và hành vi phụ thuộc phiên bản.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'STALE_PERCENT',
        pvalue => '15'
    );
END;
/
~~~

Không tăng/giảm ngưỡng chỉ để giảm số lần gather. Bảng nhỏ, bảng append-only, bảng có dữ liệu skew hoặc bảng thay đổi mạnh theo partition có thể cần chính sách khác nhau.

### STALE_STATS khác với thống kê không có

- EMPTY: object chưa có thống kê.
- STALE: đã có thống kê nhưng thay đổi đủ nhiều theo ngưỡng.
- FRESH: thống kê hiện tại chưa bị đánh dấu stale theo monitoring.

FRESH không bảo đảm histogram hoặc sample đại diện cho mọi query. Nếu phân bố dữ liệu thay đổi mà monitoring chưa đánh dấu stale, plan vẫn có thể cần đánh giá thủ công.

## 11. Automatic optimizer statistics gathering

Oracle có automatic maintenance task để thu thập optimizer statistics cho object cần thiết. Trong các phiên bản phổ biến, task có tên hiển thị **auto optimizer stats collection** và được Scheduler chạy trong maintenance window.

Task có thể chọn các object có statistics stale hoặc chưa có stats. Nó giảm nhu cầu DBA tự gather toàn bộ schema/database theo lịch cố định, nhưng không thay thế việc theo dõi những bảng đặc biệt hoặc workload cần kiểm soát.

### Xem trạng thái automatic task

~~~sql
SELECT client_name,
       status,
       window_group
FROM dba_autotask_client
WHERE client_name = 'auto optimizer stats collection';
~~~

Thông tin cửa sổ:

~~~sql
SELECT window_name,
       window_group,
       enabled
FROM dba_scheduler_windows
ORDER BY window_name;
~~~

Tên task/window và quyền truy cập dictionary phụ thuộc phiên bản. Dùng DBA_AUTOTASK_CLIENT/DBA_AUTOTASK_WINDOW_CLIENTS và Scheduler views để kiểm tra thay vì giả định task luôn chạy.

### Xem lịch sử gather operations

~~~sql
SELECT operation,
       target,
       start_time,
       end_time,
       status
FROM dba_optstat_operations
ORDER BY start_time DESC;
~~~

DBA_OPTSTAT_OPERATIONS cung cấp lịch sử thao tác optimizer statistics. Có thể xem chi tiết task nếu cần:

~~~sql
SELECT *
FROM dba_optstat_operation_tasks
ORDER BY start_time DESC;
~~~

Cấu trúc cột của các view có thể khác giữa release; dùng DESC để xem trước khi tạo script giám sát.

### Có nên tắt automatic stats gathering?

Không tắt automatic optimizer stats collection chỉ vì một lần gather gây chậm. Trước tiên xác định object, khung giờ, thời lượng và mức tài nguyên. Nếu cần điều chỉnh, DBA có thể thay đổi maintenance window, preference hoặc policy cho object cụ thể. Tắt task toàn hệ thống có thể khiến nhiều bảng stale kéo dài và làm optimizer chọn plan kém.

## 12. DBMS_STATS preferences

DBMS_STATS cho phép đặt preferences để điều khiển cách thu thập thống kê theo global, database, schema hoặc table. Preference giúp giữ chính sách nhất quán mà không phải truyền lại mọi tham số trong từng lệnh.

Một số preference thường gặp:

| Preference | Mục đích |
| --- | --- |
| ESTIMATE_PERCENT | Tỷ lệ sample mặc định. |
| METHOD_OPT | Cách thu thập column stats/histogram. |
| DEGREE | Mức parallelism. |
| CASCADE | Chính sách gather index stats. |
| GRANULARITY | Mức table/partition/subpartition stats. |
| STALE_PERCENT | Ngưỡng thay đổi để đánh dấu stale. |
| INCREMENTAL | Bật incremental statistics cho partitioned table. |
| PUBLISH | Tự động publish stats mới hay giữ ở trạng thái pending. |
| NO_INVALIDATE | Chính sách invalidation cursor. |

### Xem preference

~~~sql
SELECT DBMS_STATS.GET_PREFS(
           pname => 'METHOD_OPT',
           ownname => 'SALES',
           tabname => 'ORDERS'
       ) AS method_opt
FROM dual;
~~~

Có thể dùng GET_PREFS để kiểm tra preference cụ thể của object; giá trị trả về có thể kế thừa từ mức cao hơn nếu object không có override.

### Đặt preference cho một bảng

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'METHOD_OPT',
        pvalue => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Preference được lưu cho object và ảnh hưởng các lần gather sau, không tự thu thập stats ngay khi SET_TABLE_PREFS được gọi.

### Đặt preference cho schema

~~~sql
BEGIN
    DBMS_STATS.SET_SCHEMA_PREFS(
        ownname => 'SALES',
        pname => 'ESTIMATE_PERCENT',
        pvalue => 'DBMS_STATS.AUTO_SAMPLE_SIZE'
    );
END;
/
~~~

Pvalue là chuỗi; giá trị hợp lệ phải phù hợp với preference và release. Với biểu thức hằng package, kiểm tra cách API diễn giải preference trên phiên bản đang dùng. Khi không chắc, đặt giá trị bằng API cụ thể hoặc xem GET_PREFS sau khi set.

### Xóa preference override

~~~sql
BEGIN
    DBMS_STATS.DELETE_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'METHOD_OPT'
    );
END;
/
~~~

DELETE_TABLE_PREFS xóa override ở cấp table để object kế thừa preference từ schema/global. Không nhầm xóa preference với xóa thống kê của bảng.

## 13. Khóa và mở khóa statistics

Có thể khóa statistics của table/schema/database để automatic gather hoặc thao tác gather thông thường không thay đổi chúng. Khóa stats đôi khi hữu ích cho bảng rất ổn định hoặc hệ thống đã kiểm soát plan chặt chẽ, nhưng khóa quá lâu có thể khiến optimizer dùng thống kê cũ.

### Khóa statistics một bảng

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

### Mở khóa

~~~sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

Có các API tương ứng cho schema/database, ví dụ LOCK_SCHEMA_STATS, UNLOCK_SCHEMA_STATS, LOCK_DATABASE_STATS và UNLOCK_DATABASE_STATS. Chỉ dùng khóa phạm vi rộng khi có kế hoạch quản trị rõ ràng.

### Kiểm tra trạng thái lock

~~~sql
SELECT table_name,
       stattype_locked,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
ORDER BY table_name;
~~~

STATTYPE_LOCKED cho biết loại thống kê bị khóa theo metadata. Kiểm tra cả table/partition khi làm việc với bảng partitioned.

### FORCE khi gather

Một số API gather có tham số FORCE để cho phép thao tác ngay cả khi stats đang bị khóa. FORCE là override chủ đích; không dùng để vượt qua lock mà không hiểu lý do lock được đặt. Trước khi force, xác định owner, phạm vi và kế hoạch khôi phục.

## 14. Pending statistics: thử trước khi publish

Pending statistics cho phép thu thập thống kê mới nhưng chưa công bố làm thống kê đang dùng mặc định. DBA có thể kiểm tra execution plan trong session bật OPTIMIZER_USE_PENDING_STATISTICS trước khi publish.

### Bật chế độ giữ pending stats

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'PUBLISH',
        pvalue => 'FALSE'
    );
END;
/
~~~

### Thu thập thống kê mới

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Vì PUBLISH=FALSE, thống kê mới được giữ dưới dạng pending thay vì thay thế ngay published stats.

### Dùng pending stats trong session thử nghiệm

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;

EXPLAIN PLAN FOR
SELECT *
FROM sales.orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Session này có thể lập plan dựa trên pending stats. So sánh với plan khi OPTIMIZER_USE_PENDING_STATISTICS=FALSE và với execution thực tế trong môi trường thử nghiệm.

### Publish pending stats

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

Sau khi publish, thống kê pending trở thành published stats. Có thể trả preference PUBLISH về TRUE để các lần gather tiếp theo tự publish:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        pname => 'PUBLISH',
        pvalue => 'TRUE'
    );
END;
/
~~~

### Xóa pending stats

Nếu kết quả thử nghiệm không tốt:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS'
    );
END;
/
~~~

Pending stats giúp thử nghiệm có kiểm soát; nó không tự bảo đảm execution plan tốt hơn. Hãy dùng SQL workload đại diện và so sánh runtime metrics, không chỉ EXPLAIN PLAN.

## 15. Export, import và restore statistics

Trước một thay đổi lớn, có thể export statistics vào một statistics table để lưu bản snapshot. Đây là phương án sao lưu tường minh, độc lập với stats history.

### Tạo statistics table

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => 'SALES',
        stattab => 'STATS_BACKUP'
    );
END;
/
~~~

Statistics table là bảng do DBMS_STATS quản lý để chứa metadata thống kê. Nó không chứa bản sao dữ liệu nghiệp vụ.

### Export statistics một bảng

~~~sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid => 'ORDERS_BEFORE_CHANGE',
        cascade => TRUE
    );
END;
/
~~~

STATID giúp phân biệt nhiều snapshot trong cùng statistics table. Nếu cần export schema/database, có các API EXPORT_SCHEMA_STATS và EXPORT_DATABASE_STATS tùy phiên bản.

### Import statistics đã lưu

~~~sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid => 'ORDERS_BEFORE_CHANGE',
        cascade => TRUE,
        no_invalidate => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Import khôi phục các statistics đã export cho object tương ứng. Nó không rollback dữ liệu bảng, index hay DML; chỉ thay đổi optimizer statistics.

### Restore từ statistics history

Oracle duy trì lịch sử stats trong khoảng retention được cấu hình. Có thể khôi phục table stats về thời điểm trước:

~~~sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY,
        force => TRUE
    );
END;
/
~~~

RESTORE_TABLE_STATS dùng timestamp trong stats history. Nếu thời điểm nằm ngoài retention hoặc history không có entry tương ứng, thao tác không thể khôi phục như mong muốn. Kiểm tra retention và availability trước khi dựa vào history trong kế hoạch rollback.

### Điều chỉnh retention

DBMS_STATS có API ALTER_STATS_HISTORY_RETENTION để cấu hình thời gian lưu history. Tăng retention cần cân nhắc dung lượng SYSAUX và chính sách vận hành:

~~~sql
BEGIN
    DBMS_STATS.ALTER_STATS_HISTORY_RETENTION(31);
END;
/
~~~

Con số 31 là ví dụ số ngày, không phải khuyến nghị mặc định cho mọi database. Kiểm tra GET_STATS_HISTORY_RETENTION và GET_STATS_HISTORY_AVAILABILITY trước khi thay đổi.

### Dọn statistics table khi không cần nữa

~~~sql
BEGIN
    DBMS_STATS.DROP_STAT_TABLE(
        ownname => 'SALES',
        stattab => 'STATS_BACKUP'
    );
END;
/
~~~

Giữ bản export trong suốt giai đoạn thay đổi plan và chỉ xóa khi đã xác nhận không còn cần rollback.

## 16. Theo dõi thống kê trong data dictionary

Sau khi gather, hãy kiểm tra metadata để xác nhận object đã được xử lý, thời điểm cập nhật và những thuộc tính quan trọng.

### Thống kê bảng

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
ORDER BY table_name;
~~~

Với partitioned table, xem thêm PARTITION_NAME và GLOBAL_STATS/USER_STATS nếu cần. Dùng ALL_TAB_STATISTICS hoặc DBA_TAB_STATISTICS cho phạm vi rộng hơn.

### Thống kê cột và histogram

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
~~~

HISTOGRAM cho biết kiểu histogram được lưu, NUM_BUCKETS cho biết số bucket. Không suy ra chất lượng histogram chỉ từ số bucket; phải xem phân bố dữ liệu và query predicates.

### Thống kê index

~~~sql
SELECT index_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       clustering_factor,
       num_rows,
       last_analyzed
FROM user_ind_statistics
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

CLUSTERING_FACTOR phản ánh mức độ tương quan giữa thứ tự key của index và vị trí row trong table; nó ảnh hưởng ước lượng chi phí table access qua index.

### Partition statistics

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name = 'FACT_SALES'
ORDER BY partition_name;
~~~

Phân biệt row có PARTITION_NAME NULL (global/table-level tùy object) với từng partition. Khi kiểm tra partitioned table, không chỉ nhìn một row table-level.

### Lịch sử gather

~~~sql
SELECT operation,
       target,
       start_time,
       end_time,
       status
FROM user_optstat_operations
ORDER BY start_time DESC;
~~~

USER_OPTSTAT_OPERATIONS hiển thị các thao tác optimizer stats thuộc user hiện tại nếu phiên bản cung cấp view này. DBA_OPTSTAT_OPERATIONS dùng cho phạm vi quản trị rộng hơn.

## 17. Thống kê và execution plan

Gather stats có thể làm optimizer chọn execution plan khác. Điều đó không có nghĩa plan mới chắc chắn tốt hơn. Cần so sánh plan và runtime metrics trên workload đại diện.

### Lấy execution plan thực tế

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       *
FROM sales.orders
WHERE customer_id = 1001;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PEEKED_BINDS'
    )
);
~~~

GATHER_PLAN_STATISTICS yêu cầu thu thập row-source execution statistics cho cursor trong ví dụ. DISPLAY_CURSOR với ALLSTATS LAST cho phép so sánh E-Rows (ước lượng) và A-Rows (thực tế), cùng buffer/elapsed metrics nếu có. Cần quyền đọc fixed views phù hợp.

### So sánh trước và sau gather

1. Ghi lại SQL_ID, child number và plan hash value trước thay đổi.
2. Thu thập thống kê có kiểm soát hoặc dùng pending stats.
3. Chạy workload đại diện với bind values phù hợp.
4. Lấy plan thực tế, so sánh E-Rows với A-Rows.
5. Đo elapsed time, buffer gets, physical reads, CPU và concurrency.
6. Chỉ publish stats nếu kết quả tổng thể tốt hơn hoặc cải thiện mục tiêu đã xác định.

### NO_INVALIDATE

NO_INVALIDATE kiểm soát cursor invalidation sau khi statistics thay đổi:

- FALSE: invalidates dependent cursors ngay theo semantics của API.
- TRUE: không chủ động invalidate cursor theo thao tác gather.
- AUTO_INVALIDATE: để Oracle chọn thời điểm invalidation.

Không đặt TRUE chỉ để tránh parse nếu plan cũ không còn phù hợp; cursor cũ có thể tiếp tục dùng plan dựa trên stats cũ. AUTO_INVALIDATE thường là lựa chọn hợp lý nếu không có yêu cầu đặc biệt.

### Bind peeking và adaptive cursor sharing

Histogram và bind variables có thể ảnh hưởng plan selection. Với dữ liệu skew, optimizer có thể cần phân biệt selectivity theo bind value; adaptive cursor sharing có thể tạo nhiều child cursors. Sau gather, kiểm tra nhiều bind values đại diện thay vì chỉ một giá trị.

### Statistics không thay thế SQL tuning

Nếu query có predicate không sargable, join sai thứ tự do điều kiện, implicit conversion hoặc index không phù hợp, gather stats có thể không giải quyết nguyên nhân gốc. Xem predicate information, access path, join cardinality, SQL profile/baseline và cấu trúc query trước khi kết luận.

## 18. Quy trình vận hành an toàn

Một lần gather stats trong production nên có kế hoạch:

1. Xác định SQL/object liên quan và mục tiêu thay đổi.
2. Kiểm tra LAST_ANALYZED, STALE_STATS, modification counts và histogram hiện tại.
3. Xác nhận object có bị khóa stats hoặc có preference đặc biệt không.
4. Chọn phạm vi table/schema/database nhỏ nhất.
5. Ưu tiên AUTO_SAMPLE_SIZE và SIZE AUTO, trừ khi có lý do đo lường rõ ràng để thay đổi.
6. Export stats hoặc xác nhận stats history đủ để restore.
7. Nếu plan risk cao, dùng pending stats và thử nghiệm trước khi publish.
8. Chọn maintenance window, degree và no_invalidate phù hợp.
9. Theo dõi DBMS_STATS operation, CPU/I/O, lock và cursor behavior.
10. So sánh execution plan cùng runtime metrics.
11. Nếu kết quả xấu, import hoặc restore stats đã lưu, rồi xác nhận cursor/plan sau rollback.

### Tránh gather stats liên tục

Không chạy gather sau mỗi batch nhỏ nếu dữ liệu thay đổi không đủ ảnh hưởng plan. Thu thập quá thường xuyên có thể tiêu tốn tài nguyên, invalidates cache/cursor và tạo biến động plan không cần thiết. Dựa trên modification monitoring, partition load boundary và workload.

### Không dùng stats lock như cách cố định plan duy nhất

Lock stats có thể giữ nguyên thống kê nhưng dữ liệu tiếp tục thay đổi, khiến stats càng ngày càng xa thực tế. Nếu mục tiêu là ổn định execution plan, đánh giá SQL Plan Management/baseline và quản lý stats như hai công cụ khác nhau.

## 19. Bài thực hành tổng hợp

Thực hiện trong schema học tập có quyền CREATE TABLE. Các lệnh DDL có implicit commit trong Oracle; không chạy gather schema/database trên production chỉ để thử nghiệm.

### Bước 1: tạo bảng mẫu

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_status VARCHAR2(20) NOT NULL,
    order_amount NUMBER(12,2) NOT NULL,
    created_at DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT ck_lab_orders_amount CHECK (order_amount >= 0)
);
~~~

### Bước 2: nạp dữ liệu mẫu

~~~sql
BEGIN
    FOR i IN 1 .. 10000 LOOP
        INSERT INTO lab_orders (
            order_id,
            customer_id,
            order_status,
            order_amount,
            created_at
        )
        VALUES (
            i,
            MOD(i, 500),
            CASE WHEN MOD(i, 10) = 0 THEN 'OPEN' ELSE 'CLOSED' END,
            MOD(i * 17, 100000) / 100,
            SYSDATE - MOD(i, 365)
        );
    END LOOP;
    COMMIT;
END;
/
~~~

Đây là dữ liệu minh họa có phân bố status lệch. Quy mô 10.000 hàng đủ để quan sát thống kê trong schema lab; không dùng vòng lặp row-by-row kiểu này để nạp dữ liệu production.

### Bước 3: thu thập table statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO',
        cascade => DBMS_STATS.AUTO_CASCADE
    );
END;
/
~~~

### Bước 4: xem table, column và index stats

~~~sql
SELECT table_name, num_rows, blocks, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';

SELECT column_name, num_distinct, num_nulls,
       histogram, num_buckets, last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_name;

SELECT index_name, blevel, leaf_blocks, distinct_keys,
       clustering_factor, last_analyzed
FROM user_ind_statistics
WHERE table_name = 'LAB_ORDERS';
~~~

Quan sát primary-key index và các column statistics. Histogram có thể có hoặc không tùy quyết định của Oracle, usage và dữ liệu.

### Bước 5: thay đổi dữ liệu và kiểm tra stale

~~~sql
INSERT INTO lab_orders (
    order_id, customer_id, order_status, order_amount, created_at
)
SELECT order_id + 10000,
       customer_id,
       'OPEN',
       order_amount,
       SYSDATE
FROM lab_orders
WHERE order_id <= 3000;

COMMIT;

BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/

SELECT table_name, inserts, updates, deletes, timestamp
FROM user_tab_modifications
WHERE table_name = 'LAB_ORDERS';

SELECT table_name, num_rows, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';
~~~

Modification monitoring và stale flag có thể được cập nhật theo cơ chế nội bộ, vì vậy không coi ngay một giá trị NULL là lỗi. Có thể cần chờ/flush monitoring hoặc kiểm tra qua DBA view.

### Bước 6: gather schema ở phạm vi lab

~~~sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname => USER,
        options => 'GATHER AUTO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Lệnh này có thể gather nhiều object trong schema lab, không chỉ LAB_ORDERS. Trước khi chạy ở schema dùng chung, hãy xem phạm vi object và thời gian thực thi.

### Bước 7: pending stats cho LAB_ORDERS

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Thử dùng pending stats trong session:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;

EXPLAIN PLAN FOR
SELECT *
FROM lab_orders
WHERE order_status = 'OPEN';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

So sánh với session hoặc lần chạy dùng published stats. Sau khi quyết định, publish hoặc xóa pending:

~~~sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );

    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'TRUE'
    );
END;
/
~~~

Nếu không muốn publish:

~~~sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        pname => 'PUBLISH',
        pvalue => 'TRUE'
    );
END;
/
~~~

### Bước 8: export snapshot statistics

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => USER,
        stattab => 'LAB_STATS_BACKUP'
    );

    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        stattab => 'LAB_STATS_BACKUP',
        statid => 'BEFORE_TEST_CHANGE',
        cascade => TRUE
    );
END;
/
~~~

Nếu statistics table đã tồn tại từ lần thử trước, không tạo lại; export vào statid khác hoặc dọn object theo quy trình.

### Bước 9: thử thay đổi stats và import lại

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        estimate_percent => 100,
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade => TRUE
    );
END;
/
~~~

Sau khi quan sát, import snapshot:

~~~sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS',
        stattab => 'LAB_STATS_BACKUP',
        statid => 'BEFORE_TEST_CHANGE',
        cascade => TRUE,
        no_invalidate => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Import chỉ khôi phục statistics, không xóa các hàng đã INSERT ở bước trước. Không nhầm rollback statistics với rollback dữ liệu.

### Bước 10: khóa và mở khóa stats

~~~sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/

SELECT table_name, stattype_locked
FROM user_tab_statistics
WHERE table_name = 'LAB_ORDERS';

BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_ORDERS'
    );
END;
/
~~~

### Bước 11: dọn object lab

~~~sql
DROP TABLE lab_orders PURGE;

BEGIN
    DBMS_STATS.DROP_STAT_TABLE(
        ownname => USER,
        stattab => 'LAB_STATS_BACKUP'
    );
END;
/
~~~

Chỉ chạy sau khi hoàn thành lab và không cần giữ dữ liệu/thống kê thử nghiệm.

## 20. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| ORA-20000 unable to analyze table | Thiếu quyền hoặc object không phù hợp | Kiểm tra owner, grants và trạng thái object. |
| ORA-20005 object statistics are locked | Table/schema stats đang bị lock | Xác nhận lý do lock; unlock có kiểm soát hoặc dùng FORCE nếu được phê duyệt. |
| Gather chạy lâu | Bảng lớn, sample/degree không phù hợp hoặc I/O cạnh tranh | Xem phạm vi, AUTO_SAMPLE_SIZE, partition strategy và resource limits. |
| Gather schema ảnh hưởng workload | Schema có nhiều object và gather quá rộng | Dùng table scope hoặc GATHER STALE/AUTO; chạy trong maintenance window. |
| Histogram không xuất hiện | SIZE AUTO không chọn cột hoặc usage chưa đủ | Kiểm tra column usage/skew; chỉ đặt histogram thủ công khi có bằng chứng. |
| Plan xấu sau gather | Histogram/cardinality thay đổi hoặc plan invalidation | So sánh plan thực tế; dùng pending stats, export/import hoặc restore. |
| STALE_STATS không đổi ngay | Monitoring chưa flush/tổng hợp hoặc chưa vượt ngưỡng | Kiểm tra USER_TAB_MODIFICATIONS và flush monitoring nếu cần. |
| Pending stats không được dùng | Session chưa bật OPTIMIZER_USE_PENDING_STATISTICS | Kiểm tra session parameter và pending stats có tồn tại. |
| Gather bỏ qua bảng | Stats bị khóa hoặc object không thuộc phạm vi/options | Kiểm tra STATTYPE_LOCKED, options và operation log. |
| Import stats thất bại | STATTable, STATID, owner hoặc object không khớp | Kiểm tra export snapshot và statown/statid. |
| Restore history không có dữ liệu | Timestamp ngoài retention hoặc không có snapshot | Dùng exported stats table nếu đã chuẩn bị. |
| Plan thay đổi ngay sau gather | Cursor bị invalidated hoặc AUTO_INVALIDATE chọn thời điểm | Theo dõi child cursor, no_invalidate và plan hash. |
| Database gather gây tải cao | Phạm vi toàn database và parallelism lớn | Dùng window, giảm degree hoặc thu thập object mục tiêu. |

## 21. Câu hỏi tự kiểm tra

1. **DBMS_STATS dùng để làm gì?** Thu thập và quản lý optimizer statistics cho bảng, cột, index và phạm vi hệ thống.
2. **CBO dùng statistics để làm gì?** Ước lượng cardinality/selectivity và chi phí execution plan.
3. **GATHER_TABLE_STATS dùng khi nào?** Khi cần cập nhật thống kê cho một bảng/partition cụ thể.
4. **GATHER_SCHEMA_STATS khác gì GATHER_DATABASE_STATS?** Một API giới hạn trong schema; API kia có phạm vi database rộng hơn.
5. **GATHER_DICTIONARY_STATS và GATHER_FIXED_OBJECTS_STATS phục vụ gì?** Thống kê data dictionary và fixed/dynamic performance objects.
6. **AUTO_SAMPLE_SIZE có tác dụng gì?** Để Oracle chọn sampling phù hợp thay vì tự đặt tỷ lệ cứng.
7. **METHOD_OPT điều khiển điều gì?** Column statistics và chính sách histogram.
8. **SIZE AUTO có nghĩa tạo histogram cho mọi cột không?** Không; Oracle tự chọn dựa trên dữ liệu/usage.
9. **CASCADE điều khiển gì?** Việc gather index statistics cùng table stats.
10. **GRANULARITY quan trọng khi nào?** Với partitioned table, để chọn global/partition/subpartition statistics.
11. **GATHER STALE là gì?** Chỉ chọn object được đánh dấu stale theo policy.
12. **GATHER EMPTY là gì?** Chọn object chưa có statistics.
13. **GATHER AUTO là gì?** Để Oracle chọn object cần gather theo trạng thái/policy.
14. **STALE_STATS là gì?** Tín hiệu thống kê đã cũ theo thay đổi và ngưỡng stale.
15. **AUTO optimizer stats collection chạy khi nào?** Trong maintenance window theo cơ chế automatic maintenance task.
16. **SET_TABLE_PREFS có tự gather stats không?** Không; nó đặt preference cho lần gather sau.
17. **LOCK_TABLE_STATS dùng để làm gì?** Ngăn gather thông thường thay đổi stats của bảng.
18. **Pending stats có ích gì?** Thử plan với stats mới trước khi publish cho workload mặc định.
19. **EXPORT_TABLE_STATS lưu gì?** Snapshot optimizer statistics vào statistics table, không lưu dữ liệu nghiệp vụ.
20. **RESTORE_TABLE_STATS lấy dữ liệu từ đâu?** Stats history còn trong retention.
21. **NO_INVALIDATE điều khiển gì?** Thời điểm/chính sách invalidation cursor phụ thuộc sau khi stats thay đổi.
22. **GATHER stats có bảo đảm plan tốt hơn không?** Không; cần so sánh plan và runtime metrics.
23. **Vì sao không gather database chỉ vì một query chậm?** Phạm vi quá rộng và có thể gây tải/plan changes không cần thiết.

DBMS_STATS giúp optimizer có thông tin đại diện để ước lượng cardinality và chi phí SQL. Dùng GATHER_TABLE_STATS cho object cụ thể, GATHER_SCHEMA_STATS cho phạm vi schema và GATHER_DATABASE_STATS cho công việc quản trị toàn database. AUTO_SAMPLE_SIZE và SIZE AUTO là điểm khởi đầu tốt; histogram, partition granularity, degree và cascade cần dựa trên dữ liệu/workload. Theo dõi stale stats và automatic task, dùng preferences để chuẩn hóa policy, pending stats để thử nghiệm, export/history để rollback và kiểm tra execution plan thực tế sau mỗi thay đổi có rủi ro.
